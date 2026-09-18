"""
optimizer.py

AquaNexus optimization engine (MVP version).

APPROACH: Since the decision space is a small number of discrete choices
(5 cooling technologies x 3 water source mixes x 3 energy configurations =
45 combinations), the simplest robust MVP approach is a full enumeration
(brute-force scan) rather than a continuous solver like SciPy/Pyomo/OR-Tools.
This is explicitly simpler than the brief's suggested libraries but is
mathematically exact for this discrete problem (guaranteed global optimum,
no solver convergence risk) and transparent to a judge or reviewer.

A future version with continuous decision variables (e.g. variable desal
share, variable battery sizing) would warrant SciPy/Pyomo and is a stated
next step in docs/limitations.md.

Two selection modes are provided:
    1. Pareto frontier: non-dominated solutions across 5 objectives
       (water, energy, cost, carbon, resilience).
    2. Weighted objective: single scalar score from user-editable weights,
       per the brief's J formula.
"""

from dataclasses import dataclass, asdict
from itertools import product
from typing import List, Dict, Any

from models.cooling import CoolingTechParams
from models.pipeline import SimulationConfig, simulate


@dataclass
class Candidate:
    cooling_tech_key: str
    desal_share_pct: float
    energy_config_key: str
    renewable_penetration_pct: float
    result: Any  # SimulationResult

    def objectives(self) -> Dict[str, float]:
        """Return the 5 objectives used for Pareto comparison. Water, energy,
        cost, carbon are 'lower is better'; resilience (WERI) is 'higher is
        better' and is negated here so all objectives are minimized
        consistently."""
        r = self.result
        return {
            "water_m3_per_day": r.total_water_m3_per_day,
            "energy_mwh_per_day": r.total_energy_mwh_per_day,
            "cost_usd_per_day": r.total_opex_usd_per_day,
            "carbon_t_per_day": r.carbon_t_co2e_per_day,
            "neg_resilience": -r.weri_score,
        }


def dominates(a: Dict[str, float], b: Dict[str, float]) -> bool:
    """True if candidate a dominates candidate b (a is <= b on all objectives
    and strictly < on at least one)."""
    all_leq = all(a[k] <= b[k] for k in a)
    any_lt = any(a[k] < b[k] for k in a)
    return all_leq and any_lt


def pareto_frontier(candidates: List[Candidate]) -> List[Candidate]:
    """Return the non-dominated subset of candidates."""
    frontier = []
    for i, cand_i in enumerate(candidates):
        obj_i = cand_i.objectives()
        dominated = False
        for j, cand_j in enumerate(candidates):
            if i == j:
                continue
            if dominates(cand_j.objectives(), obj_i):
                dominated = True
                break
        if not dominated:
            frontier.append(cand_i)
    return frontier


def normalize(values: List[float]) -> List[float]:
    """Min-max normalize a list of values to 0-1. Constant lists map to 0."""
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def weighted_score(
    candidates: List[Candidate],
    weights: Dict[str, float],
) -> List[float]:
    """
    Compute J = wW*water + wE*energy + wC*cost + wCO2*carbon - wR*resilience
    using min-max normalized objectives across the candidate set, per the
    brief's weighted-objective formula. Lower J is better.
    """
    required = {"water", "energy", "cost", "carbon", "resilience"}
    if set(weights.keys()) != required:
        raise ValueError(f"weights must have exactly keys {required}, got {set(weights.keys())}")

    water = normalize([c.result.total_water_m3_per_day for c in candidates])
    energy = normalize([c.result.total_energy_mwh_per_day for c in candidates])
    cost = normalize([c.result.total_opex_usd_per_day for c in candidates])
    carbon = normalize([c.result.carbon_t_co2e_per_day for c in candidates])
    resilience = normalize([c.result.weri_score for c in candidates])  # higher raw = better

    scores = []
    for i in range(len(candidates)):
        j = (
            weights["water"] * water[i]
            + weights["energy"] * energy[i]
            + weights["cost"] * cost[i]
            + weights["carbon"] * carbon[i]
            - weights["resilience"] * resilience[i]
        )
        scores.append(j)
    return scores


def enumerate_candidates(
    base_cfg_kwargs: dict,
    cooling_options: Dict[str, CoolingTechParams],
    water_desal_share_options: Dict[str, float],
    energy_renewable_options: Dict[str, float],
) -> List[Candidate]:
    """
    Enumerate all combinations of cooling technology x water source mix x
    energy configuration, running the full simulation pipeline for each.
    """
    candidates = []
    for (tech_key, tech), (water_key, desal_share), (energy_key, renew_pct) in product(
        cooling_options.items(),
        water_desal_share_options.items(),
        energy_renewable_options.items(),
    ):
        cfg = SimulationConfig(
            cooling_tech=tech,
            desal_share_pct=desal_share,
            renewable_penetration_pct=renew_pct,
            **base_cfg_kwargs,
        )
        result = simulate(cfg)
        candidates.append(
            Candidate(
                cooling_tech_key=tech_key,
                desal_share_pct=desal_share,
                energy_config_key=energy_key,
                renewable_penetration_pct=renew_pct,
                result=result,
            )
        )
    return candidates
