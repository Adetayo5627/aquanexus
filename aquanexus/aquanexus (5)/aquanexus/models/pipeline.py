"""
pipeline.py

Ties the individual models together into a single simulate() call. This is
the one place the system boundary is assembled, avoiding double-counting.

Second-review changes:
  - Energy supply is now a 24-hour solar + battery + grid dispatch
    (models/dispatch.py), not a flat renewable percentage. Solar
    availability scenarios therefore flow through the SAME code path in the
    dashboard and in the optimizer (the previous version silently ignored
    them in the optimizer).
  - Reclaimed water has a finite, reliability-derated supply. Demand above
    it falls back to desalination, so source availability and reliability
    actually affect the result.
  - Grid constraint is a PEAK IMPORT cap (MW) evaluated hour by hour, so
    solar and batteries can genuinely relieve it.
  - Water availability remains a cap on total daily water use.
"""

from dataclasses import dataclass, field
from typing import Optional, List

from models.workload import WorkloadConfig, compute_workload
from models.cooling import ChipSideParams, HeatRejectionParams, compute_cooling
from models.desalination import compute_desalination_energy
from models.water import WaterSourceMix, compute_water_demand
from models.energy import compute_total_energy
from models.dispatch import simulate_day
from models.carbon import compute_carbon
from models.cost import compute_operational_cost
from models.resilience import compute_weri


@dataclass
class SimulationConfig:
    it_capacity_mw: float
    utilization_pct: float
    operating_hours_per_day: float
    dry_bulb_c: float
    relative_humidity_pct: float
    chip_side: ChipSideParams
    heat_rejection: HeatRejectionParams
    desal_share_pct: float                 # TARGET desalinated share before supply limits
    sec_kwh_per_m3: float
    other_water_m3_per_day: float
    other_energy_mwh_per_day: float
    pv_mw_per_avg_load_mw: float
    battery_hours: float
    solar_capacity_factor_pct: float
    solar_lcoe_usd_per_kwh: float
    grid_carbon_g_per_kwh: float
    electricity_price_usd_per_kwh: float
    water_cost_usd_per_m3: float
    regional_water_stress_score: Optional[float]
    solar_availability_multiplier: float = 1.0
    baseline_capex_usd_per_mw: float = 1_500_000.0
    battery_capex_usd_per_kwh: float = 300.0
    discount_rate: float = 0.08
    lifetime_years: float = 10.0
    reclaimed_capacity_m3_per_day: Optional[float] = None
    water_availability_cap_m3_per_day: Optional[float] = None
    grid_import_cap_mw: Optional[float] = None
    weri_weights: Optional[dict] = None


@dataclass
class SimulationResult:
    it_power_mw: float
    cooling_energy_mwh_per_day: float
    effective_pue: float
    wet_bulb_c: float
    total_water_m3_per_day: float
    desal_water_m3_per_day: float
    effective_desal_share_pct: float
    reclaimed_fallback_m3_per_day: float
    desal_energy_mwh_per_day: float
    total_energy_mwh_per_day: float
    grid_energy_mwh_per_day: float
    renewable_energy_mwh_per_day: float      # solar energy delivered to load
    solar_generated_mwh_per_day: float
    curtailed_mwh_per_day: float
    battery_capacity_mwh: float
    peak_grid_import_mw: float
    renewable_penetration_pct: float
    carbon_t_co2e_per_day: float
    total_opex_usd_per_day: float
    annualized_capex_usd_per_day: float
    battery_cost_usd_per_day: float
    total_cost_usd_per_day: float
    weri_score: float
    heat_vulnerability_score: float
    water_supply_exceeded: bool
    water_supply_shortfall_m3_per_day: float
    grid_import_exceeded: bool
    unmet_grid_demand_mwh_per_day: float
    hourly_load_mw: List[float] = field(default_factory=list)
    hourly_solar_mw: List[float] = field(default_factory=list)
    hourly_grid_mw: List[float] = field(default_factory=list)
    hourly_battery_soc_mwh: List[float] = field(default_factory=list)


def simulate(cfg: SimulationConfig) -> SimulationResult:
    workload = compute_workload(
        WorkloadConfig(cfg.it_capacity_mw, cfg.utilization_pct, cfg.operating_hours_per_day)
    )
    cooling = compute_cooling(
        heat_load_mw=workload.heat_load_mw, chip=cfg.chip_side, rejection=cfg.heat_rejection,
        dry_bulb_c=cfg.dry_bulb_c, relative_humidity_pct=cfg.relative_humidity_pct,
        operating_hours_per_day=cfg.operating_hours_per_day,
    )

    total_water = cooling.cooling_water_m3_per_day + cfg.other_water_m3_per_day

    # --- Source availability: reclaimed water is finite; shortfall falls back to desalination ---
    target_reclaimed = total_water * (100.0 - cfg.desal_share_pct) / 100.0
    reclaimed_fallback = 0.0
    effective_desal_share = cfg.desal_share_pct
    if cfg.reclaimed_capacity_m3_per_day is not None and target_reclaimed > cfg.reclaimed_capacity_m3_per_day:
        reclaimed_fallback = target_reclaimed - cfg.reclaimed_capacity_m3_per_day
        effective_desal_share = (total_water - cfg.reclaimed_capacity_m3_per_day) / total_water * 100.0

    water = compute_water_demand(
        cooling_water_m3_per_day=cooling.cooling_water_m3_per_day,
        other_water_m3_per_day=cfg.other_water_m3_per_day,
        source_mix=WaterSourceMix(effective_desal_share, 100.0 - effective_desal_share),
    )

    water_supply_exceeded = False
    water_shortfall = 0.0
    if cfg.water_availability_cap_m3_per_day is not None and water.total_water_m3_per_day > cfg.water_availability_cap_m3_per_day:
        water_supply_exceeded = True
        water_shortfall = round(water.total_water_m3_per_day - cfg.water_availability_cap_m3_per_day, 3)

    desal = compute_desalination_energy(water.total_water_m3_per_day, effective_desal_share, cfg.sec_kwh_per_m3)

    # Total facility energy (no renewable split here; the dispatch decides that)
    energy = compute_total_energy(
        it_energy_mwh_per_day=workload.it_energy_mwh_per_day,
        cooling_energy_mwh_per_day=cooling.cooling_energy_mwh_per_day,
        desal_energy_mwh_per_day=desal.desal_energy_mwh_per_day,
        other_energy_mwh_per_day=cfg.other_energy_mwh_per_day,
        renewable_penetration_pct=0.0,
    )
    avg_load_mw = energy.total_energy_mwh_per_day / 24.0
    pv_mw = cfg.pv_mw_per_avg_load_mw * avg_load_mw
    battery_mwh = cfg.battery_hours * avg_load_mw

    dispatch = simulate_day(
        daily_energy_mwh=energy.total_energy_mwh_per_day, pv_mw=pv_mw, battery_mwh=battery_mwh,
        solar_capacity_factor_pct=cfg.solar_capacity_factor_pct,
        solar_availability_multiplier=cfg.solar_availability_multiplier,
        grid_import_cap_mw=cfg.grid_import_cap_mw,
    )
    grid_exceeded = cfg.grid_import_cap_mw is not None and dispatch.unmet_over_cap_mwh > 1e-6

    carbon = compute_carbon(dispatch.grid_import_mwh, cfg.grid_carbon_g_per_kwh)

    cost = compute_operational_cost(
        grid_energy_mwh_per_day=dispatch.grid_import_mwh,
        electricity_price_usd_per_kwh=cfg.electricity_price_usd_per_kwh,
        renewable_energy_mwh_per_day=dispatch.solar_generated_mwh,
        renewable_lcoe_usd_per_kwh=cfg.solar_lcoe_usd_per_kwh,
        total_water_m3_per_day=water.total_water_m3_per_day,
        water_cost_usd_per_m3=cfg.water_cost_usd_per_m3,
        capex_relative=cfg.chip_side.capex_relative + cfg.heat_rejection.capex_relative,
        it_capacity_mw=cfg.it_capacity_mw,
        baseline_capex_usd_per_mw=cfg.baseline_capex_usd_per_mw,
        discount_rate=cfg.discount_rate, lifetime_years=cfg.lifetime_years,
        battery_capacity_mwh=battery_mwh, battery_capex_usd_per_kwh=cfg.battery_capex_usd_per_kwh,
    )

    resilience = compute_weri(
        water_wue_l_per_kwh=cfg.heat_rejection.wue_l_per_kwh,
        desal_share_pct=effective_desal_share,
        desal_volume_m3_per_day=water.desal_water_m3_per_day,
        regional_water_stress_score=cfg.regional_water_stress_score,
        grid_carbon_g_per_kwh=cfg.grid_carbon_g_per_kwh,
        renewable_penetration_pct=dispatch.renewable_penetration_pct,
        dry_bulb_c=cfg.dry_bulb_c, chip_temp_tolerance_c=cfg.chip_side.temp_tolerance_c,
        weights=cfg.weri_weights,
    )

    return SimulationResult(
        it_power_mw=round(workload.it_power_mw, 3),
        cooling_energy_mwh_per_day=cooling.cooling_energy_mwh_per_day,
        effective_pue=cooling.effective_pue, wet_bulb_c=cooling.wet_bulb_c,
        total_water_m3_per_day=water.total_water_m3_per_day,
        desal_water_m3_per_day=water.desal_water_m3_per_day,
        effective_desal_share_pct=round(effective_desal_share, 2),
        reclaimed_fallback_m3_per_day=round(reclaimed_fallback, 3),
        desal_energy_mwh_per_day=desal.desal_energy_mwh_per_day,
        total_energy_mwh_per_day=energy.total_energy_mwh_per_day,
        grid_energy_mwh_per_day=dispatch.grid_import_mwh,
        renewable_energy_mwh_per_day=dispatch.solar_used_mwh,
        solar_generated_mwh_per_day=dispatch.solar_generated_mwh,
        curtailed_mwh_per_day=dispatch.curtailed_mwh,
        battery_capacity_mwh=round(battery_mwh, 3),
        peak_grid_import_mw=dispatch.peak_grid_import_mw,
        renewable_penetration_pct=dispatch.renewable_penetration_pct,
        carbon_t_co2e_per_day=carbon.grid_emissions_t_co2e_per_day,
        total_opex_usd_per_day=cost.total_opex_usd_per_day,
        annualized_capex_usd_per_day=cost.annualized_capex_usd_per_day,
        battery_cost_usd_per_day=cost.battery_cost_usd_per_day,
        total_cost_usd_per_day=cost.total_cost_usd_per_day,
        weri_score=resilience.weri_score, heat_vulnerability_score=resilience.heat_vulnerability_score,
        water_supply_exceeded=water_supply_exceeded, water_supply_shortfall_m3_per_day=water_shortfall,
        grid_import_exceeded=grid_exceeded, unmet_grid_demand_mwh_per_day=dispatch.unmet_over_cap_mwh,
        hourly_load_mw=dispatch.hourly_load_mw, hourly_solar_mw=dispatch.hourly_solar_mw,
        hourly_grid_mw=dispatch.hourly_grid_mw, hourly_battery_soc_mwh=dispatch.hourly_battery_soc_mwh,
    )
