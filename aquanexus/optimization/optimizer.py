"""
optimizer.py

AquaNexus optimization engine (MVP version).

APPROACH: Full enumeration (brute force) rather than a continuous solver.
With cooling now split into chip-side x heat-rejection (3 x 3 = 9
combinations, see models/cooling.py), the decision space is 9 cooling
combinations x 3 water source mixes x 3 energy configurations = 81
combinations. Still small enough for exact enumeration: guaranteed global
optimum, no solver convergence risk, every candidate transparently
inspectable.

External review identified that the Pareto frontier previously collapsed to
a single point because cost ignored capex and priced renewable energy and
all water sources identically. Both are fixed in models/cost.py and here:
each water option now carries its own cost per m3, each energy option its
own LCOE, and each cooling combination its own combined capex_relative, so
the "cost" objective now actually varies across candidates and produces a
genuine Pareto frontier with real trade-offs.

Two selection modes are provided:
    1. Pareto frontier: non-dominated solutions across 5 objectives
       (water, energy, cost, carbon, resilience).
    2. Weighted objective: single scalar score from user-editable weights.
"""

from dataclasses import dataclass
from itertools import product
from typing import List, Dict, Any

from models.cooling import ChipSideParams, HeatRejectionParams
from models.pipeline import SimulationConfig, simulate


@dataclass
class Candidate:
    chip_key: str
    rejection_key: str
    water_key: str
    desal_share_pct: float
    energy_key: str
    result: Any  # SimulationResult
    infeasible: bool = False
    infeasibility_reason: str = ""

    def objectives(self) -> Dict[str, float]:
        """5 objectives for Pareto comparison, all minimized (resilience
        negated). Uses total_cost_usd_per_day (opex + annualized capex),
        not opex alone, since capex now meaningfully differentiates
        technologies."""
        r = self.result
        return {
            "water_m3_per_day": r.total_water_m3_per_day,
            "energy_mwh_per_day": r.total_energy_mwh_per_day,
            "cost_usd_per_day": r.total_cost_usd_per_day,
            "carbon_t_per_day": r.carbon_t_co2e_per_day,
            "neg_resilience": -r.weri_score,
        }


def dominates(a: Dict[str, float], b: Dict[str, float]) -> bool:
    all_leq = all(a[k] <= b[k] for k in a)
    any_lt = any(a[k] < b[k] for k in a)
    return all_leq and any_lt


def pareto_frontier(candidates: List[Candidate]) -> List[Candidate]:
    """Return the non-dominated subset of FEASIBLE candidates. Infeasible
    candidates (water supply or grid import cap exceeded) are excluded
    entirely rather than being allowed to "win" by exceeding a constraint."""
    feasible = [c for c in candidates if not c.infeasible]
    frontier = []
    for i, cand_i in enumerate(feasible):
        obj_i = cand_i.objectives()
        dominated = False
        for j, cand_j in enumerate(feasible):
            if i == j:
                continue
            if dominates(cand_j.objectives(), obj_i):
                dominated = True
                break
        if not dominated:
            frontier.append(cand_i)
    return frontier


def normalize(values: List[float]) -> List[float]:
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def weighted_score(
    candidates: List[Candidate],
    weights: Dict[str, float],
) -> List[float]:
    """
    J = wW*water + wE*energy + wC*cost + wCO2*carbon - wR*resilience,
    computed over FEASIBLE candidates only. Infeasible candidates get +inf
    so they are never selected as "best" by a min() over the returned list,
    while still appearing at the correct index for any candidate that
    iterates the full list.
    """
    required = {"water", "energy", "cost", "carbon", "resilience"}
    if set(weights.keys()) != required:
        raise ValueError(f"weights must have exactly keys {required}, got {set(weights.keys())}")

    feasible_idx = [i for i, c in enumerate(candidates) if not c.infeasible]
    if not feasible_idx:
        return [float("inf")] * len(candidates)

    water = normalize([candidates[i].result.total_water_m3_per_day for i in feasible_idx])
    energy = normalize([candidates[i].result.total_energy_mwh_per_day for i in feasible_idx])
    cost = normalize([candidates[i].result.total_cost_usd_per_day for i in feasible_idx])
    carbon = normalize([candidates[i].result.carbon_t_co2e_per_day for i in feasible_idx])
    resilience = normalize([candidates[i].result.weri_score for i in feasible_idx])

    scores = [float("inf")] * len(candidates)
    for pos, i in enumerate(feasible_idx):
        scores[i] = (
            weights["water"] * water[pos]
            + weights["energy"] * energy[pos]
            + weights["cost"] * cost[pos]
            + weights["carbon"] * carbon[pos]
            - weights["resilience"] * resilience[pos]
        )
    return scores


def enumerate_candidates(
    base_cfg_kwargs: dict,
    chip_options: Dict[str, ChipSideParams],
    rejection_options: Dict[str, HeatRejectionParams],
    water_options: Dict[str, dict],      # {key: {"desal_share_pct", "water_cost_usd_per_m3", "reclaimed_capacity_m3_per_day"}}
    energy_options: Dict[str, dict],     # {key: {"pv_mw_per_avg_load_mw", "battery_hours", "solar_lcoe_usd_per_kwh"}}
    water_availability_cap_m3_per_day=None,
    grid_import_cap_mw=None,
) -> List[Candidate]:
    """
    Enumerate all combinations of chip-side x heat-rejection x water source
    x energy configuration, running the full simulation pipeline for each.
    """
    candidates = []
    for (chip_key, chip), (rej_key, rejection), (water_key, water_opt), (energy_key, energy_opt) in product(
        chip_options.items(),
        rejection_options.items(),
        water_options.items(),
        energy_options.items(),
    ):
        cfg = SimulationConfig(
            chip_side=chip,
            heat_rejection=rejection,
            desal_share_pct=water_opt["desal_share_pct"],
            water_cost_usd_per_m3=water_opt["water_cost_usd_per_m3"],
            reclaimed_capacity_m3_per_day=water_opt.get("reclaimed_capacity_m3_per_day"),
            pv_mw_per_avg_load_mw=energy_opt["pv_mw_per_avg_load_mw"],
            battery_hours=energy_opt["battery_hours"],
            solar_lcoe_usd_per_kwh=energy_opt["solar_lcoe_usd_per_kwh"],
            water_availability_cap_m3_per_day=water_availability_cap_m3_per_day,
            grid_import_cap_mw=grid_import_cap_mw,
            **base_cfg_kwargs,
        )
        result = simulate(cfg)
        infeasible = result.water_supply_exceeded or result.grid_import_exceeded
        reasons = []
        if result.water_supply_exceeded:
            reasons.append(f"exceeds water supply by {result.water_supply_shortfall_m3_per_day} m3/day")
        if result.grid_import_exceeded:
            reasons.append(f"exceeds the peak grid import cap by {result.unmet_grid_demand_mwh_per_day} MWh/day")

        candidates.append(
            Candidate(
                chip_key=chip_key,
                rejection_key=rej_key,
                water_key=water_key,
                desal_share_pct=water_opt["desal_share_pct"],
                energy_key=energy_key,
                result=result,
                infeasible=infeasible,
                infeasibility_reason="; ".join(reasons),
            )
        )
    return candidates


def apply_constraints(candidates: List[Candidate], constraints: Dict[str, float]) -> List[Candidate]:
    """
    Apply user decision filters in place (second-review item: a five-way
    Pareto frontier can contain many technically non-dominated but practically
    useless options, so decision-makers need hard limits).

    constraints may contain any of:
      max_cost_usd_per_day, max_water_m3_per_day, max_carbon_t_per_day, min_weri
    A candidate violating a filter is marked infeasible with a reason, exactly
    like a scenario constraint, so it is excluded from the frontier and from
    best-configuration selection.
    """
    for c in candidates:
        r = c.result
        reasons = []
        if "max_cost_usd_per_day" in constraints and r.total_cost_usd_per_day > constraints["max_cost_usd_per_day"]:
            reasons.append("cost above your limit")
        if "max_water_m3_per_day" in constraints and r.total_water_m3_per_day > constraints["max_water_m3_per_day"]:
            reasons.append("water use above your limit")
        if "max_carbon_t_per_day" in constraints and r.carbon_t_co2e_per_day > constraints["max_carbon_t_per_day"]:
            reasons.append("carbon above your limit")
        if "min_weri" in constraints and r.weri_score < constraints["min_weri"]:
            reasons.append("resilience score below your minimum")
        if reasons:
            c.infeasible = True
            c.infeasibility_reason = "; ".join(filter(None, [c.infeasibility_reason, *reasons]))
    return candidates
