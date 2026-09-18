"""
cooling.py

Translates heat load + cooling technology parameters into cooling electricity
and cooling water demand, with a simplified ambient-temperature penalty.

Equations:
    E_cooling (MWh/day) = heat_load_mw * (PUE - 1) * operating_hours_per_day
        -> (PUE - 1) represents the "overhead" energy fraction beyond pure
           IT power that a facility with this PUE would need for cooling.

    Water_cooling (m3/day) = heat_load_mw * 1000 (kW) * WUE (L/kWh)
                              * operating_hours_per_day / 1000 (L->m3)

Ambient temperature penalty (simplified, MVP-level, NOT a validated thermal
model): technologies with higher ambient_temp_sensitivity see their effective
PUE increase under heatwave scenarios. This is a labeled engineering
simplification, not a CFD or thermodynamic simulation.
"""

from dataclasses import dataclass
from typing import Literal

SensitivityLevel = Literal["very_low", "low", "medium", "high"]

# Simplified PUE penalty multipliers per +1C of ambient temperature above the
# "normal" baseline, by sensitivity class. ENGINEERING ASSUMPTION — editable.
_SENSITIVITY_PENALTY_PER_DEGREE = {
    "very_low": 0.001,
    "low": 0.003,
    "medium": 0.006,
    "high": 0.012,
}


@dataclass
class CoolingTechParams:
    label: str
    wue_l_per_kwh: float
    pue_typical: float
    ambient_temp_sensitivity: SensitivityLevel


@dataclass
class CoolingResult:
    effective_pue: float
    cooling_energy_mwh_per_day: float
    cooling_water_m3_per_day: float


def compute_cooling(
    heat_load_mw: float,
    tech: CoolingTechParams,
    ambient_temp_c: float,
    ambient_temp_normal_c: float,
    operating_hours_per_day: float = 24.0,
) -> CoolingResult:
    """
    Compute cooling energy and water demand for a given heat load, cooling
    technology, and ambient temperature scenario.
    """
    if heat_load_mw < 0:
        raise ValueError("heat_load_mw cannot be negative.")

    delta_t = max(0.0, ambient_temp_c - ambient_temp_normal_c)
    penalty_per_degree = _SENSITIVITY_PENALTY_PER_DEGREE[tech.ambient_temp_sensitivity]
    effective_pue = tech.pue_typical + (delta_t * penalty_per_degree * tech.pue_typical)

    cooling_energy_mwh_per_day = heat_load_mw * (effective_pue - 1.0) * operating_hours_per_day

    heat_load_kw = heat_load_mw * 1000.0
    cooling_water_l_per_day = heat_load_kw * tech.wue_l_per_kwh * operating_hours_per_day
    cooling_water_m3_per_day = cooling_water_l_per_day / 1000.0

    return CoolingResult(
        effective_pue=round(effective_pue, 4),
        cooling_energy_mwh_per_day=round(cooling_energy_mwh_per_day, 3),
        cooling_water_m3_per_day=round(cooling_water_m3_per_day, 3),
    )
