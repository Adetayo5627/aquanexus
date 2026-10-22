"""
robustness.py

Sensitivity and uncertainty analysis for the configuration screening.

Added in response to second review ("the model lacks uncertainty analysis...
if WUE is uncertain by +/-30%, the ranking of cooling systems could change").
Rather than reporting one number, this module asks the question a decision
maker actually cares about: HOW STABLE IS THE BEST-PERFORMING CONFIGURATION
when the uncertain inputs move?

Two analyses:
  1. One-at-a-time (OAT): each uncertain input is moved low/high by a fixed
     fraction while everything else is held; we record whether the best
     configuration changes.
  2. Monte Carlo: all uncertain inputs are drawn at once from a uniform
     +/-spread band; we record how often each configuration wins ("win share").

Uncertain inputs perturbed (all engineering estimates in this project):
  heat-rejection WUE, PUE overheads (chip + rejection), electricity price,
  baseline capex, grid carbon intensity, solar LCOE, battery cost.
Also compared: alternative objective weight sets and alternative WERI weights.

Decision filters (absolute thresholds) and scenario constraints are held fixed
across perturbations, so "best" always means best among options that satisfy
the same limits.
"""

import copy
import random
from collections import Counter
from dataclasses import replace
from typing import Dict, List, Tuple, Optional

from optimization.optimizer import enumerate_candidates, weighted_score, apply_constraints

PARAMS = {
    "wue": "Water use effectiveness (WUE)",
    "pue": "Cooling PUE overheads",
    "elec": "Electricity price",
    "capex": "Baseline capex",
    "carbon": "Grid carbon intensity",
    "lcoe": "Solar LCOE",
    "battery": "Battery cost",
}

WEIGHT_SETS = {
    "Balanced (your weights)": None,
    "Equal weights": {"water": 0.2, "energy": 0.2, "cost": 0.2, "carbon": 0.2, "resilience": 0.2},
    "Cost-focused": {"water": 0.10, "energy": 0.15, "cost": 0.50, "carbon": 0.10, "resilience": 0.15},
    "Water-focused": {"water": 0.50, "energy": 0.10, "cost": 0.10, "carbon": 0.10, "resilience": 0.20},
    "Resilience-focused": {"water": 0.15, "energy": 0.10, "cost": 0.10, "carbon": 0.15, "resilience": 0.50},
}

WERI_WEIGHT_SETS = {
    "Default WERI weights": None,
    "Equal WERI weights": {"water_dep": 0.2, "water_stress": 0.2, "carbon": 0.2, "grid_dep": 0.2, "heat_vulnerability": 0.2},
    "Heat-heavy WERI weights": {"water_dep": 0.15, "water_stress": 0.15, "carbon": 0.10, "grid_dep": 0.10, "heat_vulnerability": 0.50},
}

Key = Tuple[str, str, str, str]


def _scaled(base_kwargs, chip_options, rejection_options, energy_opts, f: Dict[str, float]):
    kwargs = dict(base_kwargs)
    kwargs["electricity_price_usd_per_kwh"] = base_kwargs["electricity_price_usd_per_kwh"] * f.get("elec", 1.0)
    kwargs["baseline_capex_usd_per_mw"] = base_kwargs.get("baseline_capex_usd_per_mw", 1_500_000.0) * f.get("capex", 1.0)
    kwargs["grid_carbon_g_per_kwh"] = base_kwargs["grid_carbon_g_per_kwh"] * f.get("carbon", 1.0)
    kwargs["battery_capex_usd_per_kwh"] = base_kwargs.get("battery_capex_usd_per_kwh", 300.0) * f.get("battery", 1.0)
    # Technology-specific factors ("wue@<rejection>", "pue@<chip or rejection>")
    # override the common factor when present (independent draws, v3.1).
    chips = {k: replace(v, pue_overhead_chip=v.pue_overhead_chip * f.get("pue@" + k, f.get("pue", 1.0)))
             for k, v in chip_options.items()}
    rejs = {k: replace(v, wue_l_per_kwh=v.wue_l_per_kwh * f.get("wue@" + k, f.get("wue", 1.0)),
                       pue_overhead_rejection=v.pue_overhead_rejection * f.get("pue@" + k, f.get("pue", 1.0)))
            for k, v in rejection_options.items()}
    energy = {k: dict(v, solar_lcoe_usd_per_kwh=v["solar_lcoe_usd_per_kwh"] * f.get("lcoe", 1.0)) for k, v in energy_opts.items()}
    return kwargs, chips, rejs, energy


def draw_factors(rng, spread, chip_keys=(), rejection_keys=(), independent=False) -> Dict[str, float]:
    """
    One Monte Carlo draw of the uncertain-input factors.

    independent=False (v3 behaviour): one common factor per input family, so
    e.g. every heat-rejection WUE moves together. The ratio of two designs'
    water use is then unaffected by WUE uncertainty.
    independent=True (v3.1): WUE and PUE overheads are drawn separately for
    every technology, so the relative performance of technologies is itself
    uncertain. This is the stricter test.
    """
    f = {k: rng.uniform(1 - spread, 1 + spread) for k in PARAMS}
    if independent:
        for k in rejection_keys:
            f["wue@" + k] = rng.uniform(1 - spread, 1 + spread)
            f["pue@" + k] = rng.uniform(1 - spread, 1 + spread)
        for k in chip_keys:
            f["pue@" + k] = rng.uniform(1 - spread, 1 + spread)
    return f


def _best(base_kwargs, chip_options, rejection_options, water_opts, energy_opts, weights,
          factors, constraints, water_cap, grid_cap) -> Optional[Key]:
    kwargs, chips, rejs, energy = _scaled(base_kwargs, chip_options, rejection_options, energy_opts, factors)
    cands = enumerate_candidates(kwargs, chips, rejs, water_opts, energy,
                                 water_availability_cap_m3_per_day=water_cap, grid_import_cap_mw=grid_cap)
    if constraints:
        apply_constraints(cands, constraints)
    scores = weighted_score(cands, weights)
    feasible = [(i, s) for i, s in enumerate(scores) if s != float("inf")]
    if not feasible:
        return None
    i = min(feasible, key=lambda t: t[1])[0]
    c = cands[i]
    return (c.chip_key, c.rejection_key, c.water_key, c.energy_key)


def one_at_a_time(base_kwargs, chip_options, rejection_options, water_opts, energy_opts, weights,
                  constraints=None, water_cap=None, grid_cap=None, spread=0.30) -> Tuple[Optional[Key], List[dict]]:
    nominal = _best(base_kwargs, chip_options, rejection_options, water_opts, energy_opts, weights, {}, constraints, water_cap, grid_cap)
    rows = []
    for pkey, plabel in PARAMS.items():
        for direction, factor in (("-%d%%" % (spread * 100), 1 - spread), ("+%d%%" % (spread * 100), 1 + spread)):
            best = _best(base_kwargs, chip_options, rejection_options, water_opts, energy_opts, weights,
                         {pkey: factor}, constraints, water_cap, grid_cap)
            rows.append({"parameter": plabel, "change": direction, "best": best, "changed": best != nominal})
    for name, w in WEIGHT_SETS.items():
        if w is None:
            continue
        best = _best(base_kwargs, chip_options, rejection_options, water_opts, energy_opts, w, {}, constraints, water_cap, grid_cap)
        rows.append({"parameter": "Objective weights", "change": name, "best": best, "changed": best != nominal})
    for name, w in WERI_WEIGHT_SETS.items():
        if w is None:
            continue
        kw = dict(base_kwargs, weri_weights=w)
        best = _best(kw, chip_options, rejection_options, water_opts, energy_opts, weights, {}, constraints, water_cap, grid_cap)
        rows.append({"parameter": "Resilience score weights", "change": name, "best": best, "changed": best != nominal})
    return nominal, rows


def monte_carlo(base_kwargs, chip_options, rejection_options, water_opts, energy_opts, weights,
                constraints=None, water_cap=None, grid_cap=None, n=150, spread=0.30, seed=7,
                independent=False) -> Counter:
    rng = random.Random(seed)
    wins: Counter = Counter()
    for _ in range(n):
        f = draw_factors(rng, spread, chip_options, rejection_options, independent)
        best = _best(base_kwargs, chip_options, rejection_options, water_opts, energy_opts, weights, f, constraints, water_cap, grid_cap)
        if best is not None:
            wins[best] += 1
    return wins


DIMENSIONS = ("chip", "rejection", "water", "energy")


def dimension_shares(wins: Counter) -> Dict[str, Dict[str, float]]:
    """
    Per-choice stability. The exact winning combination can flip between
    near-ties even when each individual design CHOICE is stable (e.g. every
    winner uses reclaimed water). This reports, for each of the four design
    dimensions, the share of Monte Carlo draws in which each option appears
    in the winning configuration.
    """
    total = max(sum(wins.values()), 1)
    out: Dict[str, Dict[str, float]] = {d: {} for d in DIMENSIONS}
    for key, n in wins.items():
        for dim, choice in zip(DIMENSIONS, key):
            out[dim][choice] = out[dim].get(choice, 0.0) + n / total * 100.0
    return {d: dict(sorted(v.items(), key=lambda kv: -kv[1])) for d, v in out.items()}


def headline_ranges(ctx, key, scenario_key="Normal", n=200, spread=0.30, seed=11, independent=False):
    """
    Uncertainty range on the headline claim. Draws the uncertain inputs (same
    set as the Monte Carlo) and, for each draw, re-simulates the conventional
    baseline and the chosen design, returning the p5 / p50 / p95 of the percent
    change in water, energy, cost and carbon. Answers: "how sure are we that it
    is a 80% water cut and not 20%?"
    """
    import numpy as np
    from core.context import BASELINE_KEY
    si = ctx.scenario_state(scenario_key)
    kw0 = ctx.common_kwargs(si)
    rng = random.Random(seed)
    water_opts, energy_opts = ctx.water_options(), ctx.energy_options()
    acc = {"water": [], "energy": [], "cost": [], "carbon": []}

    def run(k, kwargs, chips, rejs, energy):
        c, r, w, e = k
        cands = enumerate_candidates(kwargs, {c: chips[c]}, {r: rejs[r]}, {w: water_opts[w]}, {e: energy[e]})
        return cands[0].result

    for _ in range(n):
        f = draw_factors(rng, spread, ctx.lib.chips, ctx.lib.rejs, independent)
        kwargs, chips, rejs, energy = _scaled(kw0, ctx.lib.chips, ctx.lib.rejs, energy_opts, f)
        b, d = run(BASELINE_KEY, kwargs, chips, rejs, energy), run(key, kwargs, chips, rejs, energy)
        acc["water"].append((d.total_water_m3_per_day / b.total_water_m3_per_day - 1) * 100)
        acc["energy"].append((d.total_energy_mwh_per_day / b.total_energy_mwh_per_day - 1) * 100)
        acc["cost"].append((d.total_cost_usd_per_day / b.total_cost_usd_per_day - 1) * 100)
        acc["carbon"].append((d.carbon_t_co2e_per_day / b.carbon_t_co2e_per_day - 1) * 100)
    return {k: tuple(float(x) for x in np.percentile(v, [5, 50, 95])) for k, v in acc.items()}
