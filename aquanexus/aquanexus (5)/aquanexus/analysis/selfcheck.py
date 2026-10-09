"""
selfcheck.py  -  internal-consistency checks that run LIVE in the app.

These test that the model obeys conservation and monotonicity properties and that
the dashboard and the optimiser agree. They do not validate the model against a
real facility (see analysis/benchmarks.py for plausibility against published figures).
"""
from itertools import product
from typing import List, Tuple

from core.context import PRIORITY_PROFILES, NORMAL, BASELINE_KEY

Check = Tuple[str, bool, str]


def _rel(a, b, tol=1e-3):
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-9)


def run_selfchecks(ctx) -> List[Check]:
    out: List[Check] = []
    keys = [(c, r, w, e) for c, r, w, e in product(ctx.lib.chips, ctx.lib.rejs, ctx.lib.water, ctx.lib.energy)]
    sims = {k: ctx.simulate_design(k, NORMAL, with_caps=False) for k in keys}

    bad = [k for k, r in sims.items() if not _rel(r.grid_energy_mwh_per_day + r.renewable_energy_mwh_per_day, r.total_energy_mwh_per_day, 2e-3)]
    out.append(("Energy balance: grid + solar delivered = facility energy (all 81 designs)", not bad, f"{len(keys) - len(bad)}/{len(keys)} pass"))

    bad = [k for k, r in sims.items() if not _rel(r.desal_water_m3_per_day, r.total_water_m3_per_day * r.effective_desal_share_pct / 100.0, 5e-3) or r.desal_water_m3_per_day > r.total_water_m3_per_day + 1e-6]
    out.append(("Water balance: desalinated + reclaimed = total water", not bad, f"{len(keys) - len(bad)}/{len(keys)} pass"))

    bad = [k for k, r in sims.items() if not _rel(r.carbon_t_co2e_per_day, r.grid_energy_mwh_per_day * ctx.grid_carbon / 1000.0, 5e-3)]
    out.append(("Carbon = grid energy x grid intensity (solar carries none)", not bad, f"{len(keys) - len(bad)}/{len(keys)} pass"))

    cap_bad = []
    for k, r in sims.items():
        cap = ctx.water_options()[k[2]]["reclaimed_capacity_m3_per_day"]
        if cap is not None and (r.total_water_m3_per_day - r.desal_water_m3_per_day) > cap + 1e-6:
            cap_bad.append(k)
    out.append(("Reclaimed water never exceeds its contracted supply", not cap_bad, f"{len(keys) - len(cap_bad)}/{len(keys)} pass"))

    mono_bad = []
    for c, r in product(ctx.lib.chips, ctx.lib.rejs):
        k = (c, r, "desalinated", "grid_only")
        prev = None
        for dt in (0, 3, 6, 9):
            res = ctx.at_capacity(ctx.it_capacity_mw)
            cc = type(ctx)(ctx.lib, ctx.location, ctx.it_capacity_mw, ctx.utilization_pct, ctx.dry_bulb_base + dt, ctx.rh_base)
            x = cc.simulate_design(k, NORMAL, with_caps=False)
            if prev is not None and (x.total_energy_mwh_per_day < prev[0] - 1e-6 or x.total_water_m3_per_day < prev[1] - 1e-6):
                mono_bad.append((c, r))
            prev = (x.total_energy_mwh_per_day, x.total_water_m3_per_day)
    out.append(("Hotter ambient never lowers energy or water use (9 cooling combinations)", not mono_bad, "monotonic" if not mono_bad else str(mono_bad[:2])))

    u_bad = False
    prev = 0
    for u in (30, 50, 70, 90):
        cc = type(ctx)(ctx.lib, ctx.location, ctx.it_capacity_mw, u, ctx.dry_bulb_base, ctx.rh_base)
        x = cc.simulate_design(BASELINE_KEY, NORMAL, with_caps=False).total_energy_mwh_per_day
        if x <= prev: u_bad = True
        prev = x
    out.append(("Higher utilisation raises energy use", not u_bad, "monotonic" if not u_bad else "violation"))

    k = ("direct_to_chip", "adiabatic", "reclaimed", "grid_plus_solar_plus_storage")
    n, rs = ctx.simulate_design(k, NORMAL, False), ctx.simulate_design(k, "Reduced solar availability", False)
    out.append(("Reduced solar means more grid import", rs.grid_energy_mwh_per_day > n.grid_energy_mwh_per_day, f"{n.grid_energy_mwh_per_day:.0f} to {rs.grid_energy_mwh_per_day:.0f} MWh/day"))

    scr = ctx.screen(NORMAL, PRIORITY_PROFILES["Balanced"])
    from optimization.optimizer import dominates
    el = scr.eligible
    dom = [c for c in scr.frontier if any(dominates(o.objectives(), c.objectives()) for o in el if o is not c)]
    out.append(("No Pareto-optimal design is dominated by another eligible design", not dom, f"{len(scr.frontier)} frontier designs checked"))

    if scr.best:
        re = ctx.simulate_design(scr.best_key, NORMAL, True)
        same = _rel(re.total_cost_usd_per_day, scr.best.result.total_cost_usd_per_day, 1e-9) and _rel(re.total_water_m3_per_day, scr.best.result.total_water_m3_per_day, 1e-9)
        out.append(("Dashboard and optimiser give identical results for the same design", same, "identical to 9 digits"))
        best_score = scr.scores[scr.candidates.index(scr.best)]
        out.append(("Selected design has the lowest weighted objective", all(s >= best_score - 1e-12 for s in scr.scores), "verified over all eligible"))
    return out
