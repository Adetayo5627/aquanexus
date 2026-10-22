"""
policy.py  -  Policy Lab: what does a rule cost, and which design meets it?

Regulators can set limits on site WUE, PUE, non-potable water share or
renewable share. For a given rule set this finds the least-cost design among
those that satisfy it (and the scenario's physical limits), and compares it with
the least-cost design when no rule applies. The gap is the cost of compliance.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict


def site_wue(r) -> float:
    """Site WUE in L per kWh of IT energy: m3/day * 1000 L / (IT MW * 24 h * 1000 kWh/MWh)."""
    return r.total_water_m3_per_day / max(r.it_power_mw * 24.0, 1e-9)


def complies(r, wue_cap=None, pue_cap=None, min_nonpotable_pct=None, min_renewable_pct=None) -> bool:
    if wue_cap is not None and site_wue(r) > wue_cap + 1e-9: return False
    if pue_cap is not None and r.effective_pue > pue_cap + 1e-9: return False
    if min_nonpotable_pct is not None and (100.0 - r.effective_desal_share_pct) < min_nonpotable_pct - 1e-9: return False
    if min_renewable_pct is not None and r.renewable_penetration_pct < min_renewable_pct - 1e-9: return False
    return True


@dataclass
class PolicyOutcome:
    n_eligible: int
    n_compliant: int
    unregulated_key: Optional[tuple]
    unregulated: object
    compliant_key: Optional[tuple]
    compliant: object
    unregulated_complies: bool
    cost_premium_pct: Optional[float]
    water_change_pct: Optional[float]
    carbon_change_pct: Optional[float]


def _key(c):
    return (c.chip_key, c.rejection_key, c.water_key, c.energy_key)


def evaluate_policy(ctx, scenario_key="Normal", **rules) -> PolicyOutcome:
    from core.context import PRIORITY_PROFILES
    scr = ctx.screen(scenario_key, PRIORITY_PROFILES["Balanced"])
    elig = scr.eligible
    if not elig:
        return PolicyOutcome(0, 0, None, None, None, None, False, None, None, None)
    cheapest = min(elig, key=lambda c: c.result.total_cost_usd_per_day)
    ok = [c for c in elig if complies(c.result, **rules)]
    if not ok:
        return PolicyOutcome(len(elig), 0, _key(cheapest), cheapest.result, None, None, False, None, None, None)
    best = min(ok, key=lambda c: c.result.total_cost_usd_per_day)
    u, p = cheapest.result, best.result
    pct = lambda a, b: 0.0 if not b else (a - b) / b * 100
    return PolicyOutcome(len(elig), len(ok), _key(cheapest), u, _key(best), p, complies(u, **rules),
                         pct(p.total_cost_usd_per_day, u.total_cost_usd_per_day),
                         pct(p.total_water_m3_per_day, u.total_water_m3_per_day),
                         pct(p.carbon_t_co2e_per_day, u.carbon_t_co2e_per_day))


def wue_sweep(ctx, scenario_key="Normal", caps=(2.0, 1.5, 1.0, 0.75, 0.5, 0.3, 0.15, 0.05)) -> List[Dict]:
    """Cost premium of the cheapest compliant design as the site WUE cap tightens."""
    rows = []
    for cap in caps:
        o = evaluate_policy(ctx, scenario_key, wue_cap=cap)
        rows.append({"cap": cap, "compliant": o.n_compliant, "premium_pct": o.cost_premium_pct,
                     "key": o.compliant_key})
    return rows
