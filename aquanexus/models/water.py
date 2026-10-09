"""
water.py

Aggregates total operational water demand and splits it by source.

IMPORTANT distinction (per project instructions):
This MVP models water CONSUMPTION (water removed from the local cycle via
evaporation), not water WITHDRAWAL (water extracted then returned, e.g. via
once-through cooling). Evaporative and hybrid cooling technologies are
consumption-dominated, so this simplification is reasonable for an MVP but
should be revisited for once-through or closed-loop-with-blowdown systems.
"""

from dataclasses import dataclass


@dataclass
class WaterSourceMix:
    desal_share_pct: float
    reclaimed_share_pct: float

    def __post_init__(self):
        total = self.desal_share_pct + self.reclaimed_share_pct
        if abs(total - 100.0) > 0.01:
            raise ValueError(
                f"desal_share_pct + reclaimed_share_pct must equal 100, got {total}"
            )


@dataclass
class WaterResult:
    total_water_m3_per_day: float
    desal_water_m3_per_day: float
    reclaimed_water_m3_per_day: float


def compute_water_demand(
    cooling_water_m3_per_day: float,
    other_water_m3_per_day: float,
    source_mix: WaterSourceMix,
) -> WaterResult:
    """
    Aggregate cooling water and other operational water demand, then split
    the total by source mix.
    """
    if cooling_water_m3_per_day < 0 or other_water_m3_per_day < 0:
        raise ValueError("Water demand values cannot be negative.")

    total = cooling_water_m3_per_day + other_water_m3_per_day
    desal_water = total * (source_mix.desal_share_pct / 100.0)
    reclaimed_water = total * (source_mix.reclaimed_share_pct / 100.0)

    return WaterResult(
        total_water_m3_per_day=round(total, 3),
        desal_water_m3_per_day=round(desal_water, 3),
        reclaimed_water_m3_per_day=round(reclaimed_water, 3),
    )
