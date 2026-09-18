"""
cost.py

Simplified OPERATIONAL cost model (OPEX only; CAPEX is tracked separately as
a relative multiplier in cooling_technologies.yaml and is NOT included in the
daily cost figures here). All costs are indicative engineering estimates,
NOT procurement prices.
"""

from dataclasses import dataclass


@dataclass
class CostResult:
    electricity_cost_usd_per_day: float
    water_cost_usd_per_day: float
    total_opex_usd_per_day: float


def compute_operational_cost(
    grid_energy_mwh_per_day: float,
    electricity_price_usd_per_kwh: float,
    total_water_m3_per_day: float,
    water_cost_usd_per_m3: float,
) -> CostResult:
    if grid_energy_mwh_per_day < 0 or total_water_m3_per_day < 0:
        raise ValueError("Energy and water inputs cannot be negative.")
    if electricity_price_usd_per_kwh < 0 or water_cost_usd_per_m3 < 0:
        raise ValueError("Prices cannot be negative.")

    grid_energy_kwh = grid_energy_mwh_per_day * 1000.0
    electricity_cost = grid_energy_kwh * electricity_price_usd_per_kwh
    water_cost = total_water_m3_per_day * water_cost_usd_per_m3

    return CostResult(
        electricity_cost_usd_per_day=round(electricity_cost, 2),
        water_cost_usd_per_day=round(water_cost, 2),
        total_opex_usd_per_day=round(electricity_cost + water_cost, 2),
    )
