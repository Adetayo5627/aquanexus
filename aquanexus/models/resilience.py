"""
resilience.py

WATER-ENERGY RESILIENCE INDEX (WERI)

IMPORTANT: WERI is an AquaNexus project-level decision metric created for
this MVP. It is NOT an internationally established scientific index. It is
a transparent, documented, editable weighted composite designed to make
trade-offs visible to a decision-maker — not a validated resilience science
instrument.

Formulation (0-100 scale, higher = more resilient):

    WERI = 100 - (
        w_water_dep   * water_dependency_score
      + w_water_stress* regional_water_stress_score
      + w_carbon      * grid_carbon_score
      + w_grid_dep    * grid_dependency_score
    )

Where each component score is itself 0-100 (higher = worse on that
dimension), and weights sum to 1.0 by default but are fully editable.

Default weights (editable):
    w_water_dep    = 0.30   (technology + source water dependency)
    w_water_stress = 0.30   (regional/national water stress, e.g. WRI score)
    w_carbon       = 0.20   (grid carbon intensity, normalized)
    w_grid_dep     = 0.20   (dependency on grid vs. on-site/renewable energy)
"""

from dataclasses import dataclass


DEFAULT_WEIGHTS = {
    "water_dep": 0.30,
    "water_stress": 0.30,
    "carbon": 0.20,
    "grid_dep": 0.20,
}


@dataclass
class ResilienceResult:
    weri_score: float
    water_dependency_score: float
    water_stress_score: float
    carbon_score: float
    grid_dependency_score: float
    weights_used: dict


def normalize_carbon_score(grid_carbon_g_per_kwh: float, min_g: float = 150, max_g: float = 550) -> float:
    """Map grid carbon intensity to a 0-100 'badness' score. Bounds are
    engineering assumptions representing a plausible Gulf-region grid range."""
    clamped = min(max_g, max(min_g, grid_carbon_g_per_kwh))
    return round(((clamped - min_g) / (max_g - min_g)) * 100, 2)


def compute_weri(
    water_wue_l_per_kwh: float,
    desal_share_pct: float,
    regional_water_stress_score: float,
    grid_carbon_g_per_kwh: float,
    renewable_penetration_pct: float,
    weights: dict = None,
) -> ResilienceResult:
    """
    Compute the Water-Energy Resilience Index for a given configuration.
    All inputs producing "badness" scores are normalized to 0-100 before
    weighting so the index remains interpretable and editable.
    """
    w = weights or DEFAULT_WEIGHTS
    if abs(sum(w.values()) - 1.0) > 0.01:
        raise ValueError(f"Weights must sum to 1.0, got {sum(w.values())}")

    # Water dependency score: combines cooling water intensity and desal reliance.
    # WUE normalized against a plausible 0-2.5 L/kWh range (evaporative cooling ceiling).
    wue_score = min(100.0, (water_wue_l_per_kwh / 2.5) * 100.0)
    water_dependency_score = round((wue_score * 0.5) + (desal_share_pct * 0.5), 2)

    carbon_score = normalize_carbon_score(grid_carbon_g_per_kwh)

    grid_dependency_score = round(100.0 - renewable_penetration_pct, 2)

    weri = 100.0 - (
        w["water_dep"] * water_dependency_score
        + w["water_stress"] * regional_water_stress_score
        + w["carbon"] * carbon_score
        + w["grid_dep"] * grid_dependency_score
    )
    weri = max(0.0, min(100.0, weri))

    return ResilienceResult(
        weri_score=round(weri, 2),
        water_dependency_score=water_dependency_score,
        water_stress_score=regional_water_stress_score,
        carbon_score=carbon_score,
        grid_dependency_score=grid_dependency_score,
        weights_used=w,
    )
