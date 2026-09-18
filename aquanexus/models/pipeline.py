"""
pipeline.py

Ties the individual models (workload -> cooling -> water -> desalination ->
energy -> carbon -> cost -> resilience) into a single simulate() call.
This is the module both the optimizer and the dashboard call, so there is
exactly one place where the system boundary is assembled -- avoiding
double-counting across the codebase.
"""

from dataclasses import dataclass

from models.workload import WorkloadConfig, compute_workload
from models.cooling import CoolingTechParams, compute_cooling
from models.desalination import compute_desalination_energy
from models.water import WaterSourceMix, compute_water_demand
from models.energy import compute_total_energy
from models.carbon import compute_carbon
from models.cost import compute_operational_cost
from models.resilience import compute_weri


@dataclass
class SimulationConfig:
    it_capacity_mw: float
    utilization_pct: float
    operating_hours_per_day: float
    ambient_temp_c: float
    ambient_temp_normal_c: float
    cooling_tech: CoolingTechParams
    desal_share_pct: float               # % of water from desalination (rest reclaimed)
    sec_kwh_per_m3: float
    other_water_m3_per_day: float
    other_energy_mwh_per_day: float
    renewable_penetration_pct: float
    grid_carbon_g_per_kwh: float
    electricity_price_usd_per_kwh: float
    water_cost_usd_per_m3: float
    regional_water_stress_score: float


@dataclass
class SimulationResult:
    it_power_mw: float
    cooling_energy_mwh_per_day: float
    effective_pue: float
    total_water_m3_per_day: float
    desal_water_m3_per_day: float
    desal_energy_mwh_per_day: float
    total_energy_mwh_per_day: float
    grid_energy_mwh_per_day: float
    renewable_energy_mwh_per_day: float
    carbon_t_co2e_per_day: float
    total_opex_usd_per_day: float
    weri_score: float


def simulate(cfg: SimulationConfig) -> SimulationResult:
    workload = compute_workload(
        WorkloadConfig(
            it_capacity_mw=cfg.it_capacity_mw,
            utilization_pct=cfg.utilization_pct,
            operating_hours_per_day=cfg.operating_hours_per_day,
        )
    )

    cooling = compute_cooling(
        heat_load_mw=workload.heat_load_mw,
        tech=cfg.cooling_tech,
        ambient_temp_c=cfg.ambient_temp_c,
        ambient_temp_normal_c=cfg.ambient_temp_normal_c,
        operating_hours_per_day=cfg.operating_hours_per_day,
    )

    water = compute_water_demand(
        cooling_water_m3_per_day=cooling.cooling_water_m3_per_day,
        other_water_m3_per_day=cfg.other_water_m3_per_day,
        source_mix=WaterSourceMix(
            desal_share_pct=cfg.desal_share_pct,
            reclaimed_share_pct=100.0 - cfg.desal_share_pct,
        ),
    )

    desal = compute_desalination_energy(
        total_water_m3_per_day=water.total_water_m3_per_day,
        desal_share_pct=cfg.desal_share_pct,
        sec_kwh_per_m3=cfg.sec_kwh_per_m3,
    )

    energy = compute_total_energy(
        it_energy_mwh_per_day=workload.it_energy_mwh_per_day,
        cooling_energy_mwh_per_day=cooling.cooling_energy_mwh_per_day,
        desal_energy_mwh_per_day=desal.desal_energy_mwh_per_day,
        other_energy_mwh_per_day=cfg.other_energy_mwh_per_day,
        renewable_penetration_pct=cfg.renewable_penetration_pct,
    )

    carbon = compute_carbon(
        grid_energy_mwh_per_day=energy.grid_energy_mwh_per_day,
        grid_carbon_intensity_g_per_kwh=cfg.grid_carbon_g_per_kwh,
    )

    cost = compute_operational_cost(
        grid_energy_mwh_per_day=energy.grid_energy_mwh_per_day,
        electricity_price_usd_per_kwh=cfg.electricity_price_usd_per_kwh,
        total_water_m3_per_day=water.total_water_m3_per_day,
        water_cost_usd_per_m3=cfg.water_cost_usd_per_m3,
    )

    resilience = compute_weri(
        water_wue_l_per_kwh=cfg.cooling_tech.wue_l_per_kwh,
        desal_share_pct=cfg.desal_share_pct,
        regional_water_stress_score=cfg.regional_water_stress_score,
        grid_carbon_g_per_kwh=cfg.grid_carbon_g_per_kwh,
        renewable_penetration_pct=cfg.renewable_penetration_pct,
    )

    return SimulationResult(
        it_power_mw=round(workload.it_power_mw, 3),
        cooling_energy_mwh_per_day=cooling.cooling_energy_mwh_per_day,
        effective_pue=cooling.effective_pue,
        total_water_m3_per_day=water.total_water_m3_per_day,
        desal_water_m3_per_day=water.desal_water_m3_per_day,
        desal_energy_mwh_per_day=desal.desal_energy_mwh_per_day,
        total_energy_mwh_per_day=energy.total_energy_mwh_per_day,
        grid_energy_mwh_per_day=energy.grid_energy_mwh_per_day,
        renewable_energy_mwh_per_day=energy.renewable_energy_mwh_per_day,
        carbon_t_co2e_per_day=carbon.grid_emissions_t_co2e_per_day,
        total_opex_usd_per_day=cost.total_opex_usd_per_day,
        weri_score=resilience.weri_score,
    )
