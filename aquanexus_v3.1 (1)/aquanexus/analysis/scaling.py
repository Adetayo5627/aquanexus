"""
scaling.py  -  what the recommended design is worth at national pipeline scale.

Takes the per-site result and re-runs the SAME model at the pipeline capacity
(no separate "multiplier" shortcut), so reclaimed-water limits and battery
sizing scale consistently. Savings are reported against the conventional
baseline in the same scenario. Illustrative, not a forecast.
"""
from dataclasses import dataclass
from typing import Optional

LITRES_PER_PERSON_PER_DAY = 100.0   # ASSUMPTION: round figure for basic domestic use (WHO uses 50-100 L for basic access)

# Pipeline MW of NEW IT capacity to apply the design to. UAE: 537 -> 711 MW by 2031
# (Mordor Intelligence 2026) = 174 MW. Others are ILLUSTRATIVE round figures, flagged in the UI.
PIPELINE_MW = {
    "UAE": (174, "Mordor Intelligence (2026): 537 MW to 711 MW by 2031"),
    "Saudi_Arabia": (200, "Illustrative planning figure, not sourced"),
    "Qatar": (60, "Illustrative planning figure, not sourced"),
    "Jordan": (30, "Illustrative planning figure, not sourced"),
    "Morocco": (60, "Illustrative planning figure, not sourced"),
    "Algeria": (40, "Illustrative planning figure, not sourced"),
    "Tunisia": (30, "Illustrative planning figure, not sourced"),
}


@dataclass
class ScaleUp:
    mw: float
    water_saved_m3_per_year: float
    people_equivalent: float
    energy_saved_gwh_per_year: float
    carbon_saved_t_per_year: float
    cost_saved_usd_per_year: float          # all-in (opex + annualized capex); negative = extra cost
    incremental_capex_usd: float
    opex_saved_usd_per_year: float
    payback_years: Optional[float]
    baseline_water_m3_per_year: float


def scale_up(ctx, key, mw, scenario_key="Normal", base_capex_usd_per_mw=1_500_000.0, battery_usd_per_kwh=300.0) -> ScaleUp:
    big = ctx.at_capacity(mw)
    base = big.baseline_for(scenario_key)
    des = big.simulate_design(key, scenario_key, with_caps=False)
    chips, rejs = ctx.lib.chips, ctx.lib.rejs
    from core.context import BASELINE_KEY
    rel = lambda k: chips[k[0]].capex_relative + rejs[k[1]].capex_relative
    capex = max(0.0, rel(key) - rel(BASELINE_KEY)) * base_capex_usd_per_mw * mw + des.battery_capacity_mwh * 1000 * battery_usd_per_kwh
    opex_saved = (base.total_opex_usd_per_day - des.total_opex_usd_per_day) * 365
    water_saved = (base.total_water_m3_per_day - des.total_water_m3_per_day) * 365
    return ScaleUp(
        mw=mw, water_saved_m3_per_year=water_saved,
        people_equivalent=(base.total_water_m3_per_day - des.total_water_m3_per_day) * 1000 / LITRES_PER_PERSON_PER_DAY,
        energy_saved_gwh_per_year=(base.total_energy_mwh_per_day - des.total_energy_mwh_per_day) * 365 / 1000,
        carbon_saved_t_per_year=(base.carbon_t_co2e_per_day - des.carbon_t_co2e_per_day) * 365,
        cost_saved_usd_per_year=(base.total_cost_usd_per_day - des.total_cost_usd_per_day) * 365,
        incremental_capex_usd=capex, opex_saved_usd_per_year=opex_saved,
        payback_years=(capex / opex_saved if opex_saved > 0 and capex > 0 else (0.0 if capex == 0 and opex_saved > 0 else None)),
        baseline_water_m3_per_year=base.total_water_m3_per_day * 365)
