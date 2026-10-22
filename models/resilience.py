"""
resilience.py

WATER-ENERGY RESILIENCE INDEX (WERI)

IMPORTANT: WERI is an AquaNexus project-level decision metric created for
this MVP. It is NOT an internationally established scientific index.

Reworked after external review identified three real problems with the
original formulation, all addressed here:

  1. Countries with no sourced water-stress figure previously received a
     neutral 50/100, which could score them as MORE resilient than a
     country with a sourced, severe 100/100 score. Fixed in two ways: (a)
     real sourced WRI 2040 figures were found and added for Jordan,
     Morocco, Algeria, and Tunisia (see data/sources.csv), closing the gap
     for every country currently in scope; (b) the remaining fallback path
     (used only if a future country profile has no score at all) now
     defaults to a conservative 80/100 ("assume high risk when unknown"),
     not a neutral 50, so missing data can never outscore sourced data.
  2. Heat vulnerability was not represented anywhere in the index, despite
     being arguably the dominant regional climate risk. A heat_vulnerability
     term is now included, based on how far ambient dry-bulb temperature
     exceeds the selected chip-side cooling technology's temperature
     tolerance.
  3. Desalination dependency was scored by SHARE of water sourced from
     desalination, which penalized a low-volume facility on 95% desalinated
     water almost as heavily as a high-volume one, even though the absolute
     burden on desalination capacity differs by orders of magnitude. The
     water-dependency term now blends share with actual desalinated volume,
     normalized against a reasoned reference ceiling (editable).
"""

from dataclasses import dataclass

DEFAULT_WEIGHTS = {
    "water_dep": 0.25,
    "water_stress": 0.25,
    "carbon": 0.15,
    "grid_dep": 0.15,
    "heat_vulnerability": 0.20,
}

# Conservative fallback for a country with NO sourced water-stress figure at
# all. Deliberately higher than a neutral midpoint, per review feedback:
# missing data should never score better than sourced data.
MISSING_WATER_STRESS_FALLBACK = 80.0

# Reference ceiling for normalizing desalinated water VOLUME to a 0-100
# score. ENGINEERING ASSUMPTION, editable: chosen as a round number above
# the highest volumes this MVP's scenarios typically produce at 100 MW IT
# capacity with evaporative cooling and a desalinated water source.
DESAL_VOLUME_REFERENCE_CEILING_M3_PER_DAY = 3000.0

# Degrees above a chip-side technology's temperature tolerance at which heat
# vulnerability reaches its maximum (100) score. ENGINEERING ASSUMPTION,
# editable.
HEAT_VULNERABILITY_SATURATION_DEGREES = 10.0


@dataclass
class ResilienceResult:
    weri_score: float
    water_dependency_score: float
    water_stress_score: float
    carbon_score: float
    grid_dependency_score: float
    heat_vulnerability_score: float
    weights_used: dict


def normalize_carbon_score(grid_carbon_g_per_kwh: float, min_g: float = 150, max_g: float = 550) -> float:
    """Map grid carbon intensity to a 0-100 'badness' score."""
    clamped = min(max_g, max(min_g, grid_carbon_g_per_kwh))
    return round(((clamped - min_g) / (max_g - min_g)) * 100, 2)


def compute_heat_vulnerability_score(dry_bulb_c: float, chip_temp_tolerance_c: float) -> float:
    """
    0-100 'badness' score for how far ambient dry-bulb temperature exceeds
    the chip-side cooling technology's temperature tolerance. Zero when at
    or below tolerance; saturates at 100 once HEAT_VULNERABILITY_SATURATION_DEGREES
    above tolerance is reached.
    """
    excess = max(0.0, dry_bulb_c - chip_temp_tolerance_c)
    score = min(100.0, (excess / HEAT_VULNERABILITY_SATURATION_DEGREES) * 100.0)
    return round(score, 2)


def compute_weri(
    water_wue_l_per_kwh: float,
    desal_share_pct: float,
    desal_volume_m3_per_day: float,
    regional_water_stress_score,  # float or None
    grid_carbon_g_per_kwh: float,
    renewable_penetration_pct: float,
    dry_bulb_c: float,
    chip_temp_tolerance_c: float,
    weights: dict = None,
) -> ResilienceResult:
    """
    Compute the Water-Energy Resilience Index for a given configuration.
    Pass regional_water_stress_score=None to use the conservative missing-
    data fallback rather than a neutral midpoint.
    """
    w = weights or DEFAULT_WEIGHTS
    if abs(sum(w.values()) - 1.0) > 0.01:
        raise ValueError(f"Weights must sum to 1.0, got {sum(w.values())}")

    water_stress_score = (
        MISSING_WATER_STRESS_FALLBACK if regional_water_stress_score is None else regional_water_stress_score
    )

    wue_score = min(100.0, (water_wue_l_per_kwh / 2.5) * 100.0)
    desal_volume_score = min(100.0, (desal_volume_m3_per_day / DESAL_VOLUME_REFERENCE_CEILING_M3_PER_DAY) * 100.0)
    # Blend: share still matters (a facility fully committed to desal has less
    # flexibility even at low volume), but volume now carries the largest
    # single weight within this sub-score, per review feedback.
    water_dependency_score = round((wue_score * 0.3) + (desal_share_pct * 0.3) + (desal_volume_score * 0.4), 2)

    carbon_score = normalize_carbon_score(grid_carbon_g_per_kwh)
    grid_dependency_score = round(100.0 - renewable_penetration_pct, 2)
    heat_vulnerability_score = compute_heat_vulnerability_score(dry_bulb_c, chip_temp_tolerance_c)

    weri = 100.0 - (
        w["water_dep"] * water_dependency_score
        + w["water_stress"] * water_stress_score
        + w["carbon"] * carbon_score
        + w["grid_dep"] * grid_dependency_score
        + w["heat_vulnerability"] * heat_vulnerability_score
    )
    weri = max(0.0, min(100.0, weri))

    return ResilienceResult(
        weri_score=round(weri, 2),
        water_dependency_score=water_dependency_score,
        water_stress_score=water_stress_score,
        carbon_score=carbon_score,
        grid_dependency_score=grid_dependency_score,
        heat_vulnerability_score=heat_vulnerability_score,
        weights_used=w,
    )
