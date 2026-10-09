"""
core/context.py

One place that turns "a site + a facility + a scenario" into model inputs.
The dashboard, the screening engine, the stress test, the scale-up, the policy
lab and the self-checks all go through SiteContext, so they cannot disagree
about what a scenario means (this was the root cause of the earlier
reduced-solar bug).
"""

import os
from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Dict, List, Optional, Tuple

import yaml

from models.cooling import ChipSideParams, HeatRejectionParams
from models.pipeline import SimulationConfig, simulate
from scenarios.stress_tests import SCENARIOS, ScenarioInputs
from optimization.optimizer import (Candidate, enumerate_candidates, pareto_frontier,
                                    weighted_score, apply_constraints)

GRID_CONSTRAINT_FRACTION = 0.85   # ENGINEERING ASSUMPTION: import limited to 85% of the conventional baseline's peak import
DESIGN_EXTREME_DELTA_C = 7.0      # ENGINEERING ASSUMPTION: design-day extreme = baseline ambient + 7C
NORMAL = "Normal"
BASELINE_KEY = ("air", "cooling_tower", "desalinated", "grid_only")

PRIORITY_PROFILES: Dict[str, Dict[str, float]] = {
    "Balanced": {"water": 0.25, "energy": 0.20, "cost": 0.20, "carbon": 0.15, "resilience": 0.20},
    "Water-first": {"water": 0.50, "energy": 0.10, "cost": 0.10, "carbon": 0.10, "resilience": 0.20},
    "Cost-first": {"water": 0.10, "energy": 0.15, "cost": 0.50, "carbon": 0.10, "resilience": 0.15},
    "Carbon-first": {"water": 0.10, "energy": 0.15, "cost": 0.10, "carbon": 0.50, "resilience": 0.15},
    "Resilience-first": {"water": 0.15, "energy": 0.10, "cost": 0.10, "carbon": 0.15, "resilience": 0.50},
}


def _load(path):
    with open(path) as f:
        return yaml.safe_load(f)


@dataclass
class Library:
    countries: dict
    chip_raw: dict
    rej_raw: dict
    water: dict
    energy: dict
    chips: Dict[str, ChipSideParams] = field(default_factory=dict)
    rejs: Dict[str, HeatRejectionParams] = field(default_factory=dict)

    def __post_init__(self):
        self.chips = {k: ChipSideParams(v["label"], v["pue_overhead_chip"], v["temp_tolerance_c"],
                                        v["degradation_per_degree_chip"], v["capex_relative"])
                      for k, v in self.chip_raw.items()}
        self.rejs = {k: HeatRejectionParams(v["label"], v["wue_l_per_kwh"], v["pue_overhead_rejection"],
                                            v["temp_basis"], v["threshold_c"], v["degradation_per_degree"],
                                            v["capex_relative"]) for k, v in self.rej_raw.items()}


def load_library(base_dir: str) -> Library:
    d = os.path.join(base_dir, "data")
    return Library(_load(os.path.join(d, "country_profiles.yaml")), _load(os.path.join(d, "chip_side.yaml")),
                   _load(os.path.join(d, "heat_rejection.yaml")), _load(os.path.join(d, "water_profiles.yaml")),
                   _load(os.path.join(d, "energy_profiles.yaml")))


@dataclass
class ScreenResult:
    scenario_key: str
    dry_bulb_c: float
    candidates: List[Candidate]
    frontier: List[Candidate]
    scores: List[float]
    best: Optional[Candidate]
    baseline: object

    @property
    def eligible(self):
        return [c for c in self.candidates if not c.infeasible]

    @property
    def best_key(self):
        b = self.best
        return None if b is None else (b.chip_key, b.rejection_key, b.water_key, b.energy_key)


@dataclass
class SiteContext:
    lib: Library
    location: str
    it_capacity_mw: float = 50
    utilization_pct: float = 80
    dry_bulb_base: Optional[float] = None
    rh_base: Optional[float] = None

    def __post_init__(self):
        if self.dry_bulb_base is None:
            self.dry_bulb_base = self.profile["ambient_temperature_normal_c"]
        if self.rh_base is None:
            self.rh_base = self.profile["relative_humidity_normal_pct"]

    # ---- site data ----
    @property
    def profile(self):
        return self.lib.countries[self.location]

    @property
    def grid_carbon(self):
        b = self.profile["grid_carbon_intensity_g_per_kwh"]
        return b["abu_dhabi"] if self.location == "UAE" else b["national"]

    @property
    def sec_mid(self):
        s = self.profile["desalination_sec_kwh_per_m3"]
        return (s["value_min"] + s["value_max"]) / 2

    def water_options(self):
        out = {}
        for k, v in self.lib.water.items():
            cap = v.get("supply_capacity_m3_per_day_per_it_mw")
            share = 60.0 if k == "hybrid_supply" else (95.0 if k == "desalinated" else 10.0)
            out[k] = {"desal_share_pct": share,
                      "water_cost_usd_per_m3": 2.0 * v.get("relative_cost_per_m3", 1.0),
                      "reclaimed_capacity_m3_per_day": None if cap is None else cap * self.it_capacity_mw * v.get("water_reliability_pct", 100) / 100.0}
        return out

    def energy_options(self):
        return {k: {"pv_mw_per_avg_load_mw": v["pv_mw_per_avg_load_mw"], "battery_hours": v["battery_hours"],
                    "solar_lcoe_usd_per_kwh": v["solar_lcoe_usd_per_kwh"]} for k, v in self.lib.energy.items()}

    # ---- scenarios ----
    def scenario_state(self, scenario_key):
        base = ScenarioInputs(ambient_temp_c=self.dry_bulb_base, water_availability_multiplier=1.0,
                              electricity_price_multiplier=1.0, workload_utilization_pct=self.utilization_pct,
                              grid_constrained=False, solar_availability_multiplier=1.0)
        return SCENARIOS[scenario_key](base)

    def common_kwargs(self, si):
        p = self.profile
        return dict(
            it_capacity_mw=self.it_capacity_mw, utilization_pct=si.workload_utilization_pct, operating_hours_per_day=24.0,
            dry_bulb_c=si.ambient_temp_c, relative_humidity_pct=self.rh_base, sec_kwh_per_m3=self.sec_mid,
            other_water_m3_per_day=5.0, other_energy_mwh_per_day=self.it_capacity_mw * 0.02,
            solar_capacity_factor_pct=p["solar_capacity_factor_pct"], solar_availability_multiplier=si.solar_availability_multiplier,
            grid_carbon_g_per_kwh=self.grid_carbon, electricity_price_usd_per_kwh=p["electricity_price_usd_per_kwh"] * si.electricity_price_multiplier,
            regional_water_stress_score=p["water_stress_score_0_100"])

    @cached_property
    def reference_baseline(self):
        si = self.scenario_state(NORMAL)
        return self._sim(BASELINE_KEY, si, caps=(None, None))

    def caps_for(self, si):
        ref = self.reference_baseline
        wc = ref.total_water_m3_per_day * si.water_availability_multiplier if si.water_availability_multiplier != 1.0 else None
        gc = ref.peak_grid_import_mw * GRID_CONSTRAINT_FRACTION if si.grid_constrained else None
        return wc, gc

    def _sim(self, key, si, caps):
        chip, rej, water, energy = key
        wopt, eopt = self.water_options()[water], self.energy_options()[energy]
        wc, gc = caps
        cfg = SimulationConfig(
            chip_side=self.lib.chips[chip], heat_rejection=self.lib.rejs[rej],
            desal_share_pct=wopt["desal_share_pct"], water_cost_usd_per_m3=wopt["water_cost_usd_per_m3"],
            reclaimed_capacity_m3_per_day=wopt["reclaimed_capacity_m3_per_day"],
            pv_mw_per_avg_load_mw=eopt["pv_mw_per_avg_load_mw"], battery_hours=eopt["battery_hours"],
            solar_lcoe_usd_per_kwh=eopt["solar_lcoe_usd_per_kwh"],
            water_availability_cap_m3_per_day=wc, grid_import_cap_mw=gc, **self.common_kwargs(si))
        return simulate(cfg)

    def simulate_design(self, key, scenario_key=NORMAL, with_caps=True):
        si = self.scenario_state(scenario_key)
        return self._sim(key, si, self.caps_for(si) if with_caps else (None, None))

    def baseline_for(self, scenario_key):
        """The conventional baseline in the same scenario (no caps: it is the yardstick)."""
        return self._sim(BASELINE_KEY, self.scenario_state(scenario_key), (None, None))

    def screen(self, scenario_key, weights, constraints=None) -> ScreenResult:
        si = self.scenario_state(scenario_key)
        wc, gc = self.caps_for(si)
        cands = enumerate_candidates(self.common_kwargs(si), self.lib.chips, self.lib.rejs, self.water_options(),
                                     self.energy_options(), water_availability_cap_m3_per_day=wc, grid_import_cap_mw=gc)
        if constraints:
            apply_constraints(cands, constraints)
        frontier = pareto_frontier(cands)
        scores = weighted_score(cands, weights)
        ok = [(i, s) for i, s in enumerate(scores) if s != float("inf")]
        best = cands[min(ok, key=lambda t: t[1])[0]] if ok else None
        return ScreenResult(scenario_key, si.ambient_temp_c, cands, frontier, scores, best, self.baseline_for(scenario_key))

    def stress_test(self, key):
        """Baseline vs a design across every scenario. Each row is a dict."""
        rows = []
        for sk in SCENARIOS:
            si = self.scenario_state(sk)
            caps = self.caps_for(si)
            base = self._sim(BASELINE_KEY, si, caps)
            des = self._sim(key, si, caps)
            rows.append({"scenario": sk, "baseline": base, "design": des})
        return rows

    # ---- labels ----
    def design_label(self, key):
        c, r, w, e = key
        return f"{self.lib.chips[c].label} + {self.lib.rejs[r].label} | {self.lib.water[w]['label']} | {self.lib.energy[e]['label']}"

    def short_label(self, key):
        c, r, w, e = key
        short = lambda s: s.split(" (")[0]
        return f"{short(self.lib.chips[c].label)} + {short(self.lib.rejs[r].label)}, {short(self.lib.water[w]['label'])}, {short(self.lib.energy[e]['label'])}"

    def at_capacity(self, mw):
        return replace(self, it_capacity_mw=mw)
