"""
energy.py

Aggregates total facility energy per the brief's equation:

    E_total = E_IT + E_cooling + E_desalination + E_other

The renewable_penetration_pct split below is kept for backward compatibility
and unit tests only; the pipeline calls it with 0% and the grid/solar split is
decided hour by hour in models/dispatch.py.
"""

from dataclasses import dataclass


@dataclass
class EnergyResult:
    total_energy_mwh_per_day: float
    grid_energy_mwh_per_day: float
    renewable_energy_mwh_per_day: float


def compute_total_energy(
    it_energy_mwh_per_day: float,
    cooling_energy_mwh_per_day: float,
    desal_energy_mwh_per_day: float,
    other_energy_mwh_per_day: float,
    renewable_penetration_pct: float,
) -> EnergyResult:
    """
    Sum all energy components once (no double-counting) and split by source.
    """
    for name, val in [
        ("it_energy_mwh_per_day", it_energy_mwh_per_day),
        ("cooling_energy_mwh_per_day", cooling_energy_mwh_per_day),
        ("desal_energy_mwh_per_day", desal_energy_mwh_per_day),
        ("other_energy_mwh_per_day", other_energy_mwh_per_day),
    ]:
        if val < 0:
            raise ValueError(f"{name} cannot be negative.")
    if not (0 <= renewable_penetration_pct <= 100):
        raise ValueError("renewable_penetration_pct must be between 0 and 100.")

    total = (
        it_energy_mwh_per_day
        + cooling_energy_mwh_per_day
        + desal_energy_mwh_per_day
        + other_energy_mwh_per_day
    )
    renewable = total * (renewable_penetration_pct / 100.0)
    grid = total - renewable

    return EnergyResult(
        total_energy_mwh_per_day=round(total, 3),
        grid_energy_mwh_per_day=round(grid, 3),
        renewable_energy_mwh_per_day=round(renewable, 3),
    )
