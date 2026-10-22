"""
cooling.py

Cooling is modeled as two independent choices, per external review feedback
that conflating "how heat leaves the chip" with "how heat leaves the
building" produces unrealistic combinations (e.g. direct-to-chip cooling was
previously assumed to have near-zero water use, when in practice its water
use depends entirely on what it is paired with on the heat-rejection side):

    1. Chip-side heat removal (air / direct-to-chip / immersion)
    2. Heat rejection to ambient (dry cooler / adiabatic / cooling tower)

Effective PUE and water use are both functions of BOTH choices plus ambient
conditions, not of chip-side alone.

Temperature penalty model (threshold-based, replacing the previous
delta-from-normal model): each side has a temperature tolerance or
threshold. Above that threshold, PUE overhead grows linearly. This makes the
ABSOLUTE ambient temperature matter, not just how far it has moved from an
arbitrary "normal" baseline, which was a modeling gap identified in review
(a 45C day in Riyadh and a 20C day in Rabat previously produced identical
results if both were each country's "normal").

Wet-bulb temperature: water-based heat rejection (adiabatic, cooling tower)
responds to WET-BULB temperature, since evaporative heat rejection capacity
depends on humidity, not just dry-bulb heat. Estimated via Stull's (2011)
empirical approximation, a published meteorological formula (not a
project-specific invention):

    R. Stull, "Wet-Bulb Temperature from Relative Humidity and Air
    Temperature," Journal of Applied Meteorology and Climatology,
    50(11), 2267-2269 (2011).
"""

import math
from dataclasses import dataclass
from typing import Literal

TempBasis = Literal["dry_bulb", "wet_bulb"]


def wet_bulb_celsius(dry_bulb_c: float, relative_humidity_pct: float) -> float:
    """
    Stull (2011) empirical approximation of wet-bulb temperature from
    dry-bulb temperature (Celsius) and relative humidity (0-100%).
    Valid for standard atmospheric pressure and typical terrestrial
    humidity/temperature ranges; not valid for extreme pressure conditions.
    """
    t = dry_bulb_c
    rh = max(0.0001, min(100.0, relative_humidity_pct))  # guard domain
    tw = (
        t * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * (rh ** 1.5) * math.atan(0.023101 * rh)
        - 4.686035
    )
    return tw


@dataclass
class ChipSideParams:
    label: str
    pue_overhead_chip: float
    temp_tolerance_c: float
    degradation_per_degree_chip: float
    capex_relative: float


@dataclass
class HeatRejectionParams:
    label: str
    wue_l_per_kwh: float
    pue_overhead_rejection: float
    temp_basis: TempBasis
    threshold_c: float
    degradation_per_degree: float
    capex_relative: float


@dataclass
class CoolingResult:
    effective_pue: float
    cooling_energy_mwh_per_day: float
    cooling_water_m3_per_day: float
    wet_bulb_c: float  # reported even when not used, for transparency/debugging


def compute_cooling(
    heat_load_mw: float,
    chip: ChipSideParams,
    rejection: HeatRejectionParams,
    dry_bulb_c: float,
    relative_humidity_pct: float,
    operating_hours_per_day: float = 24.0,
) -> CoolingResult:
    """
    Compute cooling energy and water demand from a heat load, a chip-side
    heat removal choice, a heat-rejection choice, and absolute ambient
    conditions (not a delta from an arbitrary baseline).
    """
    if heat_load_mw < 0:
        raise ValueError("heat_load_mw cannot be negative.")
    if not (0 <= relative_humidity_pct <= 100):
        raise ValueError("relative_humidity_pct must be between 0 and 100.")

    tw = wet_bulb_celsius(dry_bulb_c, relative_humidity_pct)

    # Chip side always responds to dry-bulb (it's about inlet air/coolant
    # temperature entering the IT equipment, not evaporative performance).
    chip_excess = max(0.0, dry_bulb_c - chip.temp_tolerance_c)
    chip_overhead = chip.pue_overhead_chip * (1.0 + chip_excess * chip.degradation_per_degree_chip)

    rejection_temp = tw if rejection.temp_basis == "wet_bulb" else dry_bulb_c
    rejection_excess = max(0.0, rejection_temp - rejection.threshold_c)
    rejection_overhead = rejection.pue_overhead_rejection * (1.0 + rejection_excess * rejection.degradation_per_degree)

    effective_pue = 1.0 + chip_overhead + rejection_overhead

    cooling_energy_mwh_per_day = heat_load_mw * (effective_pue - 1.0) * operating_hours_per_day

    heat_load_kw = heat_load_mw * 1000.0
    cooling_water_l_per_day = heat_load_kw * rejection.wue_l_per_kwh * operating_hours_per_day
    cooling_water_m3_per_day = cooling_water_l_per_day / 1000.0

    return CoolingResult(
        effective_pue=round(effective_pue, 4),
        cooling_energy_mwh_per_day=round(cooling_energy_mwh_per_day, 3),
        cooling_water_m3_per_day=round(cooling_water_m3_per_day, 3),
        wet_bulb_c=round(tw, 2),
    )
