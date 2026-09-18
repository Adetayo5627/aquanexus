"""
carbon.py

Computes operational carbon emissions from grid electricity only.
Renewable electricity is treated as zero direct operational emissions in
this MVP (lifecycle/embodied emissions of solar/battery hardware are out of
scope — a stated limitation, not an oversight).

    Carbon (kg CO2e/day) = grid_energy_mwh_per_day * 1000 (MWh->kWh)
                            * grid_carbon_intensity_g_per_kwh / 1000 (g->kg)
"""

from dataclasses import dataclass


@dataclass
class CarbonResult:
    grid_emissions_kg_co2e_per_day: float
    grid_emissions_t_co2e_per_day: float


def compute_carbon(
    grid_energy_mwh_per_day: float,
    grid_carbon_intensity_g_per_kwh: float,
) -> CarbonResult:
    if grid_energy_mwh_per_day < 0:
        raise ValueError("grid_energy_mwh_per_day cannot be negative.")
    if grid_carbon_intensity_g_per_kwh < 0:
        raise ValueError("grid_carbon_intensity_g_per_kwh cannot be negative.")

    grid_energy_kwh = grid_energy_mwh_per_day * 1000.0
    emissions_g = grid_energy_kwh * grid_carbon_intensity_g_per_kwh
    emissions_kg = emissions_g / 1000.0
    emissions_t = emissions_kg / 1000.0

    return CarbonResult(
        grid_emissions_kg_co2e_per_day=round(emissions_kg, 2),
        grid_emissions_t_co2e_per_day=round(emissions_t, 4),
    )
