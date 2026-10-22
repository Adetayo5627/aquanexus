"""
dispatch.py

Simple 24-hour solar + battery + grid dispatch, replacing the previous flat
"X% of daily energy is renewable" shortcut (identified in review as the
biggest conceptual weakness: it ignored hour of day, irradiance, installed
capacity, battery state of charge and curtailment).

Still a SCREENING-level model, deliberately simple:
  - Flat hourly facility load (no diurnal load or cooling swing).
  - Idealized clear-sky solar shape (half-sine between 06:00 and 18:00),
    scaled so the daily mean equals the country's solar capacity factor.
  - Greedy dispatch: solar serves load first; surplus charges the battery;
    battery discharges to cover remaining load; the grid covers the rest.
  - The battery is charged ONLY from surplus solar, never from the grid.
  - No cloud variability, degradation, grid export, or forecasting.

Equations per hour h:
    solar_h = PV_MW * profile_h * availability_multiplier
    direct_h = min(load_h, solar_h)
    surplus_h = solar_h - direct_h
    charge_h  = min(surplus_h, power limit, free battery capacity / eff_in)
    discharge_h = min(load_h - direct_h, power limit, stored energy * eff_out)
    grid_h = load_h - direct_h - discharge_h
    curtailed_h = surplus_h - charge_h
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional

HOURS = 24
SOLAR_START_HOUR = 6
SOLAR_END_HOUR = 18
BATTERY_ROUND_TRIP_EFFICIENCY = 0.90   # ENGINEERING ASSUMPTION
BATTERY_C_RATE = 0.5                   # max charge/discharge power = 0.5 x capacity per hour (2-hour rate), ENGINEERING ASSUMPTION


def solar_profile(capacity_factor_pct: float) -> List[float]:
    """Hourly PV output per MW of nameplate (0-1), half-sine between 06:00
    and 18:00, normalized so the 24-hour mean equals the capacity factor."""
    shape = []
    for h in range(HOURS):
        t = (h + 0.5 - SOLAR_START_HOUR) / (SOLAR_END_HOUR - SOLAR_START_HOUR)
        shape.append(math.sin(math.pi * t) if 0.0 < t < 1.0 else 0.0)
    total = sum(shape)
    target_daily = (capacity_factor_pct / 100.0) * HOURS
    return [s / total * target_daily for s in shape]


@dataclass
class DispatchResult:
    solar_generated_mwh: float
    solar_used_mwh: float          # direct + via battery (delivered to load)
    grid_import_mwh: float
    curtailed_mwh: float
    battery_throughput_mwh: float
    peak_grid_import_mw: float
    unmet_over_cap_mwh: float      # grid import above the cap, summed over hours
    renewable_penetration_pct: float
    hourly_load_mw: List[float] = field(default_factory=list)
    hourly_solar_mw: List[float] = field(default_factory=list)
    hourly_grid_mw: List[float] = field(default_factory=list)
    hourly_battery_soc_mwh: List[float] = field(default_factory=list)


def simulate_day(
    daily_energy_mwh: float,
    pv_mw: float,
    battery_mwh: float,
    solar_capacity_factor_pct: float,
    solar_availability_multiplier: float = 1.0,
    grid_import_cap_mw: Optional[float] = None,
) -> DispatchResult:
    if daily_energy_mwh < 0 or pv_mw < 0 or battery_mwh < 0:
        raise ValueError("Energy, PV and battery sizes cannot be negative.")
    if solar_availability_multiplier < 0:
        raise ValueError("solar_availability_multiplier cannot be negative.")

    load = daily_energy_mwh / HOURS
    profile = solar_profile(solar_capacity_factor_pct)
    eff_one_way = math.sqrt(BATTERY_ROUND_TRIP_EFFICIENCY)
    power_limit = battery_mwh * BATTERY_C_RATE

    soc = 0.0
    gen_total = used_total = grid_total = curtailed_total = throughput = 0.0
    peak_grid = unmet = 0.0
    h_load, h_solar, h_grid, h_soc = [], [], [], []

    for h in range(HOURS):
        solar = pv_mw * profile[h] * solar_availability_multiplier
        direct = min(load, solar)
        surplus = solar - direct
        free_capacity = battery_mwh - soc
        charge_in = min(surplus, power_limit, free_capacity / eff_one_way) if battery_mwh > 0 else 0.0
        soc += charge_in * eff_one_way
        curtailed = surplus - charge_in

        remaining = load - direct
        discharge_out = min(remaining, power_limit, soc * eff_one_way) if battery_mwh > 0 else 0.0
        soc -= discharge_out / eff_one_way if eff_one_way > 0 else 0.0
        grid = remaining - discharge_out

        gen_total += solar
        used_total += direct + discharge_out
        grid_total += grid
        curtailed_total += curtailed
        throughput += charge_in + discharge_out
        peak_grid = max(peak_grid, grid)
        if grid_import_cap_mw is not None and grid > grid_import_cap_mw:
            unmet += grid - grid_import_cap_mw

        h_load.append(load); h_solar.append(solar); h_grid.append(grid); h_soc.append(soc)

    total = load * HOURS
    penetration = (used_total / total * 100.0) if total > 0 else 0.0
    return DispatchResult(
        solar_generated_mwh=round(gen_total, 3),
        solar_used_mwh=round(used_total, 3),
        grid_import_mwh=round(grid_total, 3),
        curtailed_mwh=round(curtailed_total, 3),
        battery_throughput_mwh=round(throughput, 3),
        peak_grid_import_mw=round(peak_grid, 3),
        unmet_over_cap_mwh=round(unmet, 3),
        renewable_penetration_pct=round(penetration, 2),
        hourly_load_mw=h_load, hourly_solar_mw=h_solar,
        hourly_grid_mw=h_grid, hourly_battery_soc_mwh=h_soc,
    )
