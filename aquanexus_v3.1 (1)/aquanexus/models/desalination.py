"""
desalination.py

Computes the energy required to produce desalinated water for cooling,
per the brief's explicit equation:

    E_desal = Water_desalinated * SEC_desalination

Where SEC_desalination (specific energy consumption) is a literature-derived
range (see data/sources.csv), NOT a UAE-measured figure.
"""

from dataclasses import dataclass


@dataclass
class DesalinationResult:
    desalinated_water_m3_per_day: float
    desal_energy_mwh_per_day: float
    sec_used_kwh_per_m3: float


def compute_desalination_energy(
    total_water_m3_per_day: float,
    desal_share_pct: float,
    sec_kwh_per_m3: float,
) -> DesalinationResult:
    """
    Compute the energy needed to produce the desalinated fraction of total
    water demand.

    Args:
        total_water_m3_per_day: total operational water demand.
        desal_share_pct: fraction (0-100) of that water sourced from
            desalination (vs. reclaimed/other).
        sec_kwh_per_m3: specific energy consumption of desalination, kWh/m3.
    """
    if total_water_m3_per_day < 0:
        raise ValueError("total_water_m3_per_day cannot be negative.")
    if not (0 <= desal_share_pct <= 100):
        raise ValueError("desal_share_pct must be between 0 and 100.")
    if sec_kwh_per_m3 < 0:
        raise ValueError("sec_kwh_per_m3 cannot be negative.")

    desalinated_water_m3 = total_water_m3_per_day * (desal_share_pct / 100.0)
    desal_energy_kwh = desalinated_water_m3 * sec_kwh_per_m3
    desal_energy_mwh = desal_energy_kwh / 1000.0

    return DesalinationResult(
        desalinated_water_m3_per_day=round(desalinated_water_m3, 3),
        desal_energy_mwh_per_day=round(desal_energy_mwh, 4),
        sec_used_kwh_per_m3=sec_kwh_per_m3,
    )
