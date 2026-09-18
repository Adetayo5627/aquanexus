"""
recommendation.py

Translates the optimizer's chosen configuration into a plain-language
engineering explanation. The explanation is assembled from actual model
outputs and simple, documented rules -- not generated freeform, and not
fabricated. If you change the rule thresholds below, the explanation text
changes accordingly (it is not hardcoded to any one scenario).
"""

from dataclasses import dataclass
from optimization.optimizer import Candidate


@dataclass
class Recommendation:
    headline: str
    reasoning: str


def explain(best: Candidate, ambient_temp_c: float, ambient_temp_normal_c: float) -> Recommendation:
    r = best.result
    delta_t = ambient_temp_c - ambient_temp_normal_c

    reasons = []

    if delta_t >= 3:
        reasons.append(
            f"ambient temperature is currently {delta_t:.0f}C above the normal baseline, "
            f"which increases the energy penalty for temperature-sensitive cooling technologies"
        )
    if best.desal_share_pct >= 70:
        reasons.append(
            f"the configuration relies on desalination for {best.desal_share_pct:.0f}% of its water, "
            f"adding {r.desal_energy_mwh_per_day:.2f} MWh/day of desalination energy on top of cooling energy"
        )
    elif best.desal_share_pct <= 30:
        reasons.append(
            f"the configuration limits desalination reliance to {best.desal_share_pct:.0f}% of water demand, "
            f"reducing exposure to desalination-capacity constraints during water stress"
        )
    if best.renewable_penetration_pct >= 40:
        reasons.append(
            f"renewable penetration of {best.renewable_penetration_pct:.0f}% reduces grid dependency and "
            f"lowers operational carbon emissions to {r.carbon_t_co2e_per_day:.3f} tCO2e/day"
        )
    if r.weri_score >= 60:
        reasons.append(f"the resulting WERI resilience score of {r.weri_score:.0f}/100 is comparatively strong")
    elif r.weri_score < 40:
        reasons.append(
            f"the resulting WERI resilience score of {r.weri_score:.0f}/100 is comparatively weak, "
            f"indicating this configuration carries real trade-off risk rather than a clean win"
        )

    if not reasons:
        reasons.append(
            "this configuration produced the best balance across water, energy, cost, carbon, "
            "and resilience objectives under the current scenario, without any single factor dominating"
        )

    reasoning = (
        f"{best.cooling_tech_key.replace('_', ' ').title()} cooling with "
        f"{best.desal_share_pct:.0f}% desalinated water and "
        f"{best.energy_config_key.replace('_', ' ')} was selected because " + "; ".join(reasons) + "."
    )

    return Recommendation(
        headline=f"{best.cooling_tech_key.replace('_', ' ').title()} / {best.energy_config_key.replace('_', ' ').title()}",
        reasoning=reasoning,
    )
