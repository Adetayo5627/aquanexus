import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""
test_models.py

Sanity-check and regression tests for AquaNexus. Several tests here were
added specifically to catch the issues identified in external review and
ensure they do not regress:
  - test_absolute_temperature_matters: catches the "delta from normal"
    bug where absolute ambient temperature had no effect.
  - test_wet_bulb_*: validates the Stull approximation behaves physically.
  - test_cost_includes_capex / test_renewable_energy_is_not_free: catches
    the zero-cost-renewable and ignored-capex bugs that collapsed the
    Pareto frontier to one point.
  - test_optimizer_frontier_has_multiple_points: the actual end-to-end
    regression test for the collapsed-frontier bug.
  - test_water_cap_flags_infeasible / test_grid_cap_flags_infeasible: catch
    the previously-unconnected scenario bug.
  - test_missing_water_stress_is_conservative_not_neutral: catches the
    "missing data scores better than real data" WERI bug.
  - test_resilience_scales_with_desal_volume: catches the share-only (not
    volume-scaled) desalination dependency bug.

Run with: pytest validation/test_models.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from models.workload import WorkloadConfig, compute_workload
from models.cooling import ChipSideParams, HeatRejectionParams, compute_cooling, wet_bulb_celsius
from models.desalination import compute_desalination_energy
from models.water import WaterSourceMix, compute_water_demand
from models.energy import compute_total_energy
from models.carbon import compute_carbon
from models.cost import compute_operational_cost, capital_recovery_factor
from models.resilience import compute_weri
from models.pipeline import SimulationConfig, simulate
from models.dispatch import simulate_day, solar_profile
from optimization.optimizer import enumerate_candidates, pareto_frontier, weighted_score, apply_constraints
from analysis.robustness import one_at_a_time, monte_carlo


# ---------------- Workload ----------------

def test_workload_scales_with_utilization():
    low = compute_workload(WorkloadConfig(it_capacity_mw=50, utilization_pct=50))
    high = compute_workload(WorkloadConfig(it_capacity_mw=50, utilization_pct=90))
    assert high.it_power_mw > low.it_power_mw


def test_workload_rejects_invalid_utilization():
    with pytest.raises(ValueError):
        compute_workload(WorkloadConfig(it_capacity_mw=50, utilization_pct=150))


# ---------------- Cooling: wet-bulb physics ----------------

def test_wet_bulb_equals_dry_bulb_at_saturation():
    tw = wet_bulb_celsius(30.0, 100.0)
    assert abs(tw - 30.0) < 0.5


def test_wet_bulb_below_dry_bulb_in_dry_air():
    tw = wet_bulb_celsius(45.0, 15.0)
    assert tw < 45.0 - 10.0, "Dry desert air should produce a wet-bulb well below dry-bulb."


def test_wet_bulb_close_to_dry_bulb_in_humid_air():
    """This is the specific real-world phenomenon flagged in review: humid
    coastal Gulf conditions should make evaporative cooling's effective
    temperature basis close to dry-bulb, i.e. evaporative cooling gets
    little benefit there."""
    tw = wet_bulb_celsius(35.0, 80.0)
    assert (35.0 - tw) < 5.0


# ---------------- Cooling: absolute temperature now matters ----------------

def test_absolute_temperature_matters():
    """Regression test for the review-identified bug: previously, cooling
    energy depended only on (ambient - normal), so a hot country and a mild
    country at their respective 'normal' both produced delta=0 and
    identical results. Now, absolute dry-bulb temperature must produce
    different results even when both are each scenario's 'baseline'."""
    chip = ChipSideParams("Air", 0.35, 35, 0.02, 1.0)
    rejection = HeatRejectionParams("Dry cooler", 0.02, 0.25, "dry_bulb", 30, 0.02, 1.0)

    hot = compute_cooling(heat_load_mw=40, chip=chip, rejection=rejection, dry_bulb_c=45, relative_humidity_pct=15)
    mild = compute_cooling(heat_load_mw=40, chip=chip, rejection=rejection, dry_bulb_c=20, relative_humidity_pct=15)

    assert hot.effective_pue > mild.effective_pue, "A 45C day must cost more energy than a 20C day, even if both are 'normal' for their country."
    assert hot.cooling_energy_mwh_per_day > mild.cooling_energy_mwh_per_day


def test_heat_rejection_choice_affects_water_not_chip_side():
    """Chip-side choice should not by itself determine water use; water use
    comes from the heat-rejection choice, per the review's architectural fix."""
    air_chip = ChipSideParams("Air", 0.35, 35, 0.02, 1.0)
    dtc_chip = ChipSideParams("Direct-to-chip", 0.12, 45, 0.01, 1.6)
    tower = HeatRejectionParams("Cooling tower", 2.0, 0.08, "wet_bulb", 28, 0.01, 1.1)

    air_with_tower = compute_cooling(40, air_chip, tower, dry_bulb_c=30, relative_humidity_pct=40)
    dtc_with_tower = compute_cooling(40, dtc_chip, tower, dry_bulb_c=30, relative_humidity_pct=40)

    assert air_with_tower.cooling_water_m3_per_day == dtc_with_tower.cooling_water_m3_per_day, \
        "Water use should depend on heat-rejection choice, not chip-side choice, when rejection is held constant."


# ---------------- Desalination / water / energy / carbon (unchanged logic) ----------------

def test_desalination_energy_scales_with_water_and_sec():
    low_sec = compute_desalination_energy(1000, desal_share_pct=100, sec_kwh_per_m3=3.0)
    high_sec = compute_desalination_energy(1000, desal_share_pct=100, sec_kwh_per_m3=4.0)
    assert high_sec.desal_energy_mwh_per_day > low_sec.desal_energy_mwh_per_day


def test_water_demand_split_sums_to_total():
    result = compute_water_demand(100, 5, WaterSourceMix(desal_share_pct=70, reclaimed_share_pct=30))
    assert abs((result.desal_water_m3_per_day + result.reclaimed_water_m3_per_day) - result.total_water_m3_per_day) < 0.01


def test_energy_no_double_counting():
    result = compute_total_energy(100, 30, 5, 2, renewable_penetration_pct=0)
    assert abs(result.total_energy_mwh_per_day - 137) < 0.01


def test_carbon_scales_with_grid_energy_and_intensity():
    low = compute_carbon(100, 200)
    high = compute_carbon(100, 400)
    assert high.grid_emissions_t_co2e_per_day > low.grid_emissions_t_co2e_per_day


# ---------------- Cost: capex and renewable LCOE now matter ----------------

def test_renewable_energy_is_not_free():
    """Regression test: previously renewable energy was priced at zero,
    which made the most-solar option always win on cost."""
    zero_lcoe = compute_operational_cost(
        grid_energy_mwh_per_day=100, electricity_price_usd_per_kwh=0.08,
        renewable_energy_mwh_per_day=500, renewable_lcoe_usd_per_kwh=0.0,
        total_water_m3_per_day=50, water_cost_usd_per_m3=2.0,
        capex_relative=1.0, it_capacity_mw=50,
    )
    real_lcoe = compute_operational_cost(
        grid_energy_mwh_per_day=100, electricity_price_usd_per_kwh=0.08,
        renewable_energy_mwh_per_day=500, renewable_lcoe_usd_per_kwh=0.025,
        total_water_m3_per_day=50, water_cost_usd_per_m3=2.0,
        capex_relative=1.0, it_capacity_mw=50,
    )
    assert real_lcoe.total_opex_usd_per_day > zero_lcoe.total_opex_usd_per_day


def test_cost_includes_capex():
    low_capex = compute_operational_cost(
        grid_energy_mwh_per_day=100, electricity_price_usd_per_kwh=0.08,
        renewable_energy_mwh_per_day=0, renewable_lcoe_usd_per_kwh=0.0,
        total_water_m3_per_day=50, water_cost_usd_per_m3=2.0,
        capex_relative=1.0, it_capacity_mw=50,
    )
    high_capex = compute_operational_cost(
        grid_energy_mwh_per_day=100, electricity_price_usd_per_kwh=0.08,
        renewable_energy_mwh_per_day=0, renewable_lcoe_usd_per_kwh=0.0,
        total_water_m3_per_day=50, water_cost_usd_per_m3=2.0,
        capex_relative=2.2, it_capacity_mw=50,
    )
    assert high_capex.total_cost_usd_per_day > low_capex.total_cost_usd_per_day
    assert high_capex.annualized_capex_usd_per_day > low_capex.annualized_capex_usd_per_day
    # opex (non-capex) portion should be identical since only capex_relative changed
    assert abs(high_capex.total_opex_usd_per_day - low_capex.total_opex_usd_per_day) < 0.01


def test_capital_recovery_factor_positive_and_bounded():
    crf = capital_recovery_factor(0.08, 10)
    assert 0 < crf < 1


def test_cost_rejects_negative_price():
    with pytest.raises(ValueError):
        compute_operational_cost(100, -0.1, 0, 0.0, 50, 2.0, 1.0, 50)


# ---------------- Resilience: WERI rework ----------------

def test_missing_water_stress_is_conservative_not_neutral():
    """Regression test for the review-identified bug: missing data
    previously scored a neutral 50, which could beat a sourced, severe
    100/100 score. The fallback (None) must now score worse (lower WERI)
    than a country with a genuinely low/mild sourced score, and should not
    beat a high sourced score either."""
    missing = compute_weri(
        water_wue_l_per_kwh=1.0, desal_share_pct=50, desal_volume_m3_per_day=500,
        regional_water_stress_score=None, grid_carbon_g_per_kwh=300,
        renewable_penetration_pct=30, dry_bulb_c=35, chip_temp_tolerance_c=35,
    )
    mild_sourced = compute_weri(
        water_wue_l_per_kwh=1.0, desal_share_pct=50, desal_volume_m3_per_day=500,
        regional_water_stress_score=40, grid_carbon_g_per_kwh=300,
        renewable_penetration_pct=30, dry_bulb_c=35, chip_temp_tolerance_c=35,
    )
    assert missing.weri_score < mild_sourced.weri_score, \
        "Missing water-stress data must not score better than a genuinely mild sourced score."


def test_resilience_scales_with_desal_volume():
    """Regression test: a low-volume facility on mostly-desalinated water
    should no longer be penalized nearly as heavily as a high-volume one at
    the same share."""
    low_volume = compute_weri(
        water_wue_l_per_kwh=0.02, desal_share_pct=95, desal_volume_m3_per_day=25,
        regional_water_stress_score=100, grid_carbon_g_per_kwh=300,
        renewable_penetration_pct=30, dry_bulb_c=35, chip_temp_tolerance_c=35,
    )
    high_volume = compute_weri(
        water_wue_l_per_kwh=0.02, desal_share_pct=95, desal_volume_m3_per_day=2500,
        regional_water_stress_score=100, grid_carbon_g_per_kwh=300,
        renewable_penetration_pct=30, dry_bulb_c=35, chip_temp_tolerance_c=35,
    )
    assert high_volume.weri_score < low_volume.weri_score, \
        "A much higher desalinated volume at the same share must score worse resilience, not the same."


def test_heat_vulnerability_increases_above_tolerance():
    cool = compute_weri(
        water_wue_l_per_kwh=1.0, desal_share_pct=50, desal_volume_m3_per_day=500,
        regional_water_stress_score=50, grid_carbon_g_per_kwh=300,
        renewable_penetration_pct=30, dry_bulb_c=30, chip_temp_tolerance_c=35,
    )
    hot = compute_weri(
        water_wue_l_per_kwh=1.0, desal_share_pct=50, desal_volume_m3_per_day=500,
        regional_water_stress_score=50, grid_carbon_g_per_kwh=300,
        renewable_penetration_pct=30, dry_bulb_c=45, chip_temp_tolerance_c=35,
    )
    assert hot.heat_vulnerability_score > cool.heat_vulnerability_score
    assert hot.weri_score < cool.weri_score


def test_resilience_rejects_bad_weights():
    with pytest.raises(ValueError):
        compute_weri(
            water_wue_l_per_kwh=1.0, desal_share_pct=50, desal_volume_m3_per_day=500,
            regional_water_stress_score=50, grid_carbon_g_per_kwh=300,
            renewable_penetration_pct=30, dry_bulb_c=35, chip_temp_tolerance_c=35,
            weights={"water_dep": 0.5, "water_stress": 0.5, "carbon": 0.5, "grid_dep": 0.5, "heat_vulnerability": 0.5},
        )


# ---------------- Dispatch: 24-hour solar + battery model ----------------

def test_solar_profile_mean_equals_capacity_factor():
    p = solar_profile(22.0)
    assert abs(sum(p) / 24 * 100 - 22.0) < 0.01
    assert p[0] == 0 and p[23] == 0, "No solar at night."


def test_dispatch_energy_balance_closes():
    r = simulate_day(1200.0, pv_mw=70, battery_mwh=200, solar_capacity_factor_pct=22)
    assert abs((r.grid_import_mwh + r.solar_used_mwh) - 1200.0) < 0.5, "Grid + delivered solar must equal load."


def test_battery_reduces_grid_import():
    no_batt = simulate_day(1200.0, pv_mw=110, battery_mwh=0, solar_capacity_factor_pct=22)
    batt = simulate_day(1200.0, pv_mw=110, battery_mwh=200, solar_capacity_factor_pct=22)
    assert batt.grid_import_mwh < no_batt.grid_import_mwh


def test_reduced_solar_increases_grid_import():
    full = simulate_day(1200.0, pv_mw=110, battery_mwh=200, solar_capacity_factor_pct=22, solar_availability_multiplier=1.0)
    reduced = simulate_day(1200.0, pv_mw=110, battery_mwh=200, solar_capacity_factor_pct=22, solar_availability_multiplier=0.6)
    assert reduced.grid_import_mwh > full.grid_import_mwh


def test_grid_only_has_no_renewable():
    r = simulate_day(1200.0, pv_mw=0, battery_mwh=0, solar_capacity_factor_pct=22)
    assert r.renewable_penetration_pct == 0 and r.grid_import_mwh == 1200.0


# ---------------- Pipeline: constraints and water-source availability ----------------

def _base_sim_kwargs():
    return dict(
        it_capacity_mw=50, utilization_pct=80, operating_hours_per_day=24.0,
        dry_bulb_c=35, relative_humidity_pct=50,
        chip_side=ChipSideParams("Air", 0.35, 35, 0.02, 1.0),
        heat_rejection=HeatRejectionParams("Cooling tower", 2.0, 0.08, "wet_bulb", 28, 0.01, 1.1),
        desal_share_pct=95, sec_kwh_per_m3=3.5, other_water_m3_per_day=5.0, other_energy_mwh_per_day=1.0,
        pv_mw_per_avg_load_mw=0.0, battery_hours=0.0, solar_capacity_factor_pct=22.0, solar_lcoe_usd_per_kwh=0.0,
        grid_carbon_g_per_kwh=300, electricity_price_usd_per_kwh=0.08, water_cost_usd_per_m3=2.0,
        regional_water_stress_score=100,
    )


def test_water_cap_flags_infeasible_when_exceeded():
    kwargs = _base_sim_kwargs()
    unconstrained = simulate(SimulationConfig(**kwargs))
    constrained = simulate(SimulationConfig(**kwargs, water_availability_cap_m3_per_day=unconstrained.total_water_m3_per_day * 0.5))
    assert constrained.water_supply_exceeded is True
    assert constrained.water_supply_shortfall_m3_per_day > 0


def test_water_cap_not_flagged_when_sufficient():
    kwargs = _base_sim_kwargs()
    unconstrained = simulate(SimulationConfig(**kwargs))
    constrained = simulate(SimulationConfig(**kwargs, water_availability_cap_m3_per_day=unconstrained.total_water_m3_per_day * 2.0))
    assert constrained.water_supply_exceeded is False


def test_grid_peak_cap_flags_infeasible_when_exceeded():
    kwargs = _base_sim_kwargs()
    base = simulate(SimulationConfig(**kwargs))
    constrained = simulate(SimulationConfig(**kwargs, grid_import_cap_mw=base.peak_grid_import_mw * 0.5))
    assert constrained.grid_import_exceeded is True


def test_efficient_design_survives_grid_cap_that_baseline_fails():
    """A genuine resilience finding the old flag-only model could not express:
    a more efficient design draws less peak power and so survives an import
    limit that the conventional baseline cannot."""
    efficient = dict(_base_sim_kwargs())
    efficient["chip_side"] = ChipSideParams("Immersion", 0.05, 50, 0.005, 2.0)
    efficient["heat_rejection"] = HeatRejectionParams("Dry cooler", 0.02, 0.25, "dry_bulb", 30, 0.02, 1.0)
    base = simulate(SimulationConfig(**_base_sim_kwargs()))
    cap = base.peak_grid_import_mw * 0.95
    base_capped = simulate(SimulationConfig(**_base_sim_kwargs(), grid_import_cap_mw=cap))
    eff = simulate(SimulationConfig(**efficient, grid_import_cap_mw=cap))
    assert base_capped.grid_import_exceeded is True, "Conventional baseline should fail a 5% import limit."
    assert eff.grid_import_exceeded is False, "A more efficient design draws less peak power and should pass it."


def test_reclaimed_capacity_forces_desalination_fallback():
    """Regression for 'water source selection is cosmetic': a reclaimed
    option cannot supply more than its (reliability-derated) capacity."""
    kwargs = _base_sim_kwargs()
    kwargs["desal_share_pct"] = 10.0
    unlimited = simulate(SimulationConfig(**kwargs))
    limited = simulate(SimulationConfig(**kwargs, reclaimed_capacity_m3_per_day=100.0))
    assert limited.reclaimed_fallback_m3_per_day > 0
    assert limited.effective_desal_share_pct > unlimited.effective_desal_share_pct
    assert limited.desal_energy_mwh_per_day > unlimited.desal_energy_mwh_per_day


# ---------------- Optimizer: solar scenario, frontier, filters ----------------

def _load_options():
    import yaml as _yaml
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chip_raw = _yaml.safe_load(open(os.path.join(base, "data", "chip_side.yaml")))
    rej_raw = _yaml.safe_load(open(os.path.join(base, "data", "heat_rejection.yaml")))
    water_raw = _yaml.safe_load(open(os.path.join(base, "data", "water_profiles.yaml")))
    energy_raw = _yaml.safe_load(open(os.path.join(base, "data", "energy_profiles.yaml")))

    chips = {k: ChipSideParams(v["label"], v["pue_overhead_chip"], v["temp_tolerance_c"], v["degradation_per_degree_chip"], v["capex_relative"]) for k, v in chip_raw.items()}
    rejs = {k: HeatRejectionParams(v["label"], v["wue_l_per_kwh"], v["pue_overhead_rejection"], v["temp_basis"], v["threshold_c"], v["degradation_per_degree"], v["capex_relative"]) for k, v in rej_raw.items()}

    def desal_share(k):
        return 60.0 if k == "hybrid_supply" else (95.0 if k == "desalinated" else 10.0)

    water = {}
    for k, v in water_raw.items():
        cap = v.get("supply_capacity_m3_per_day_per_it_mw")
        water[k] = {"desal_share_pct": desal_share(k), "water_cost_usd_per_m3": 2.0 * v.get("relative_cost_per_m3", 1.0),
                    "reclaimed_capacity_m3_per_day": None if cap is None else cap * 50 * v.get("water_reliability_pct", 100) / 100}
    energy = {k: {"pv_mw_per_avg_load_mw": v["pv_mw_per_avg_load_mw"], "battery_hours": v["battery_hours"], "solar_lcoe_usd_per_kwh": v["solar_lcoe_usd_per_kwh"]} for k, v in energy_raw.items()}
    return chips, rejs, water, energy


def _opt_base_kwargs(solar_mult=1.0):
    return dict(
        it_capacity_mw=50, utilization_pct=80, operating_hours_per_day=24.0,
        dry_bulb_c=35, relative_humidity_pct=55, sec_kwh_per_m3=3.5,
        other_water_m3_per_day=5.0, other_energy_mwh_per_day=1.0,
        solar_capacity_factor_pct=22.0, solar_availability_multiplier=solar_mult,
        grid_carbon_g_per_kwh=280, electricity_price_usd_per_kwh=0.084, regional_water_stress_score=100,
    )


def test_optimizer_frontier_has_multiple_points():
    """Regression for the first review's headline finding (collapsed frontier)."""
    chips, rejs, water, energy = _load_options()
    candidates = enumerate_candidates(_opt_base_kwargs(), chips, rejs, water, energy)
    frontier = pareto_frontier(candidates)
    assert len(candidates) == 3 * 3 * 3 * 3
    assert len(frontier) > 1


def test_optimizer_respects_reduced_solar_scenario():
    """Regression for the second review's clearest software defect: the
    reduced-solar multiplier was applied to the dashboard but ignored by the
    optimizer. It is now an input to simulate(), so both paths agree."""
    chips, rejs, water, energy = _load_options()
    full = enumerate_candidates(_opt_base_kwargs(1.0), chips, rejs, water, energy)
    reduced = enumerate_candidates(_opt_base_kwargs(0.6), chips, rejs, water, energy)
    solar_full = [c for c in full if c.energy_key != "grid_only"]
    solar_red = [c for c in reduced if c.energy_key != "grid_only"]
    assert sum(c.result.grid_energy_mwh_per_day for c in solar_red) > sum(c.result.grid_energy_mwh_per_day for c in solar_full)
    grid_only_full = [c for c in full if c.energy_key == "grid_only"]
    grid_only_red = [c for c in reduced if c.energy_key == "grid_only"]
    assert sum(c.result.grid_energy_mwh_per_day for c in grid_only_red) == sum(c.result.grid_energy_mwh_per_day for c in grid_only_full)


def test_decision_filters_exclude_candidates():
    chips, rejs, water, energy = _load_options()
    candidates = enumerate_candidates(_opt_base_kwargs(), chips, rejs, water, energy)
    limit = sorted(c.result.total_water_m3_per_day for c in candidates)[len(candidates) // 2]
    apply_constraints(candidates, {"max_water_m3_per_day": limit})
    kept = [c for c in candidates if not c.infeasible]
    assert 0 < len(kept) < len(candidates)
    assert all(c.result.total_water_m3_per_day <= limit for c in kept)


def test_infeasible_candidates_never_selected_as_best():
    chips, rejs, water, energy = _load_options()
    candidates = enumerate_candidates(_opt_base_kwargs(), chips, rejs, water, energy)
    apply_constraints(candidates, {"max_water_m3_per_day": 100})
    scores = weighted_score(candidates, {"water": .25, "energy": .2, "cost": .2, "carbon": .15, "resilience": .2})
    best = min(range(len(scores)), key=lambda i: scores[i])
    assert not candidates[best].infeasible


# ---------------- Robustness analysis ----------------

def test_robustness_returns_rows_and_wins():
    chips, rejs, water, energy = _load_options()
    w = {"water": .25, "energy": .2, "cost": .2, "carbon": .15, "resilience": .2}
    nominal, rows = one_at_a_time(_opt_base_kwargs(), chips, rejs, water, energy, w)
    assert nominal is not None and len(rows) >= 14
    wins = monte_carlo(_opt_base_kwargs(), chips, rejs, water, energy, w, n=20)
    assert sum(wins.values()) == 20


def test_dimension_shares_sum_to_100_per_dimension():
    from collections import Counter
    from analysis.robustness import dimension_shares
    wins = Counter({("direct_to_chip", "adiabatic", "reclaimed", "grid_plus_solar"): 3,
                    ("immersion", "adiabatic", "reclaimed", "grid_plus_solar_plus_storage"): 1})
    shares = dimension_shares(wins)
    for dim, dist in shares.items():
        assert abs(sum(dist.values()) - 100.0) < 1e-6
    assert shares["water"]["reclaimed"] == 100.0
    assert abs(shares["chip"]["direct_to_chip"] - 75.0) < 1e-6


# ---------------- v3: site context, scale-up, policy, self-checks ----------------
def _ctx(loc="UAE"):
    import os
    from core.context import SiteContext, load_library
    return SiteContext(load_library(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), loc)


def test_context_matches_optimizer_for_best():
    from core.context import PRIORITY_PROFILES
    ctx = _ctx()
    s = ctx.screen("Normal", PRIORITY_PROFILES["Balanced"])
    r = ctx.simulate_design(s.best_key, "Normal", True)
    assert abs(r.total_cost_usd_per_day - s.best.result.total_cost_usd_per_day) < 1e-6


def test_all_countries_screen_and_beat_baseline_on_water():
    from core.context import PRIORITY_PROFILES, SiteContext, load_library
    import os
    lib = load_library(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for c in lib.countries:
        ctx = SiteContext(lib, c)
        s = ctx.screen("Normal", PRIORITY_PROFILES["Balanced"])
        assert s.best is not None
        assert s.best.result.total_water_m3_per_day < s.baseline.total_water_m3_per_day


def test_scale_up_positive_water_saving():
    from analysis.scaling import scale_up
    su = scale_up(_ctx(), ("direct_to_chip", "adiabatic", "reclaimed", "grid_plus_solar"), 100)
    assert su.water_saved_m3_per_year > 0 and su.people_equivalent > 0 and su.incremental_capex_usd > 0


def test_policy_cap_binds_and_costs_nonnegative():
    from analysis.policy import evaluate_policy, site_wue
    o = evaluate_policy(_ctx(), "Normal", wue_cap=0.5)
    assert o.compliant is not None and site_wue(o.compliant) <= 0.5 + 1e-9
    assert o.cost_premium_pct >= -1e-9
    assert evaluate_policy(_ctx(), "Normal", wue_cap=0.0001).compliant is None


def test_selfchecks_all_pass_everywhere():
    from analysis.selfcheck import run_selfchecks
    for c in ("UAE", "Algeria", "Jordan"):
        assert all(ok for _, ok, _ in run_selfchecks(_ctx(c)))


def test_headline_ranges_ordered():
    from analysis.robustness import headline_ranges
    r = headline_ranges(_ctx(), ("direct_to_chip", "adiabatic", "reclaimed", "grid_plus_solar"), n=40)
    for lo, md, hi in r.values():
        assert lo <= md <= hi
    assert r["water"][2] < -50
