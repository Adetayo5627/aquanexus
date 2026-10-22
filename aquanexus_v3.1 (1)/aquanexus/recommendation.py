"""
recommendation.py

Explains the best-performing configuration in QUANTITATIVE terms relative to
the conventional baseline (second review: "the explanation is post-hoc
justification... a stronger system would say this option reduces water by
43%, increases cost by 8%..."). Every sentence below is computed from model
outputs; nothing is hardcoded to a scenario.

Framing note: this is a configuration SCREENING result. It says which modeled
alternative performs best under the stated assumptions and weights, not that
it is "the" optimal design.
"""

from dataclasses import dataclass
from typing import List
from optimization.optimizer import Candidate


@dataclass
class Recommendation:
    headline: str
    reasoning: str
    deltas: dict
    tradeoffs: List[str]


def _pct(new: float, base: float) -> float:
    return 0.0 if base == 0 else (new - base) / base * 100.0


def explain(best: Candidate, baseline, scenario_name: str, dry_bulb_c: float) -> Recommendation:
    r = best.result
    d = {
        "water": _pct(r.total_water_m3_per_day, baseline.total_water_m3_per_day),
        "energy": _pct(r.total_energy_mwh_per_day, baseline.total_energy_mwh_per_day),
        "cost": _pct(r.total_cost_usd_per_day, baseline.total_cost_usd_per_day),
        "carbon": _pct(r.carbon_t_co2e_per_day, baseline.carbon_t_co2e_per_day),
        "weri": r.weri_score - baseline.weri_score,
    }

    def phrase(name, pct, lower_is_better=True):
        verb = "reduces" if pct < 0 else "increases"
        return f"{verb} {name} by {abs(pct):.0f}%"

    parts = [
        phrase("water use", d["water"]), phrase("total energy", d["energy"]),
        phrase("carbon", d["carbon"]), phrase("daily cost", d["cost"]),
    ]
    sign = "+" if d["weri"] >= 0 else "-"
    parts.append(f"changes the resilience score by {sign}{abs(d['weri']):.0f} points ({baseline.weri_score:.0f} to {r.weri_score:.0f})")

    tradeoffs = []
    if d["cost"] > 0:
        tradeoffs.append(f"It costs {d['cost']:.0f}% more per day than the conventional baseline (annualized capex is ${r.annualized_capex_usd_per_day:,.0f} of ${r.total_cost_usd_per_day:,.0f}/day).")
    if d["water"] > 0:
        tradeoffs.append(f"It uses {d['water']:.0f}% more water than the baseline, so check it against your water limit.")
    if d["energy"] > 0:
        tradeoffs.append(f"It uses {d['energy']:.0f}% more total energy than the baseline.")
    if r.reclaimed_fallback_m3_per_day > 0:
        tradeoffs.append(f"Reclaimed supply cannot cover the full demand, so {r.reclaimed_fallback_m3_per_day:,.0f} m3/day falls back to desalination.")
    if r.curtailed_mwh_per_day > 0.05 * max(r.solar_generated_mwh_per_day, 1e-9):
        tradeoffs.append(f"{r.curtailed_mwh_per_day:,.0f} MWh/day of solar output is curtailed (paid for but unused).")
    if r.heat_vulnerability_score >= 50:
        tradeoffs.append(f"At {dry_bulb_c:.0f}C its chip-side cooling is heat-stressed (heat vulnerability {r.heat_vulnerability_score:.0f}/100).")
    if not tradeoffs:
        tradeoffs.append("No trade-off against the baseline was found on the five screened objectives under this scenario.")

    chip = best.chip_key.replace("_", " ")
    rej = best.rejection_key.replace("_", " ")
    energy = best.energy_key.replace("_", " ")
    water = best.water_key.replace("_", " ")

    reasoning = (
        f"Under the '{scenario_name}' scenario, {chip} chip-side cooling with {rej} heat rejection, "
        f"{water} water and {energy} " + ", ".join(parts[:-1]) + f", and {parts[-1]}, relative to the conventional baseline."
    )
    return Recommendation(
        headline=f"{chip.title()} + {rej.title()} / {water.title()} / {energy.title()}",
        reasoning=reasoning, deltas=d, tradeoffs=tradeoffs,
    )
