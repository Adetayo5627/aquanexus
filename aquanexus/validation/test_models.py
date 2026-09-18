"""
test_models.py

Sanity-check unit tests for AquaNexus core models. These are directional/
consistency tests (per project instructions), not validation against
real measured facility data -- see docs/limitations.md for what full
validation would require.

Run with: pytest validation/test_models.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from models.workload import WorkloadConfig, compute_workload
from models.cooling import CoolingTechParams, compute_cooling
from models.desalination import compute_desalination_energy
from models.water import WaterSourceMix, compute_water_demand
from models.energy import compute_total_energy
from models.carbon import compute_carbon
from models.cost import compute_operational_cost
from models.resilience import compute_weri


def test_workload_scales_with_utilization():
    low = compute_workload(WorkloadConfig(it_capacity_mw=50, utilization_pct=50))
    high = compute_workload(WorkloadConfig(it_capacity_mw=50, utilization_pct=90))
    assert high.it_power_mw > low.it_power_mw, "Higher utilization must not decrease IT power."


def test_workload_rejects_invalid_utilization():
    with pytest.raises(ValueError):
        compute_workload(WorkloadConfig(it_capacity_mw=50, utilization_pct=150))


def test_cooling_heatwave_increases_energy_for_sensitive_tech():
    tech = CoolingTechParams("Air-cooled", wue_l_per_kwh=0.05, pue_typical=1.5, ambient_temp_sensitivity="high")
    normal = compute_cooling(heat_load_mw=40, tech=tech, ambient_temp_c=35, ambient_temp_normal_c=35)
    heatwave = compute_cooling(heat_load_mw=40, tech=tech, ambient_temp_c=40, ambient_temp_normal_c=35)
    assert heatwave.cooling_energy_mwh_per_day > normal.cooling_energy_mwh_per_day, \
        "Ambient temperature increase must not improve cooling energy for a heat-sensitive technology."


def test_cooling_low_sensitivity_tech_less_affected_than_high_sensitivity():
    high_sens = CoolingTechParams("Air", 0.05, 1.5, "high")
    low_sens = CoolingTechParams("Immersion", 0.02, 1.07, "very_low")
    high_result = compute_cooling(40, high_sens, ambient_temp_c=40, ambient_temp_normal_c=35)
    low_result = compute_cooling(40, low_sens, ambient_temp_c=40, ambient_temp_normal_c=35)
    high_penalty = high_result.effective_pue - high_sens.pue_typical
    low_penalty = low_result.effective_pue - low_sens.pue_typical
    assert high_penalty > low_penalty, "Heat-sensitive technology should show a larger PUE penalty than a low-sensitivity one."


def test_desalination_energy_scales_with_water_and_sec():
    low_sec = compute_desalination_energy(1000, desal_share_pct=100, sec_kwh_per_m3=3.0)
    high_sec = compute_desalination_energy(1000, desal_share_pct=100, sec_kwh_per_m3=4.0)
    assert high_sec.desal_energy_mwh_per_day > low_sec.desal_energy_mwh_per_day


def test_water_demand_reduces_with_availability_stress_modeled_upstream():
    # water.py itself doesn't apply scenario multipliers (that's the dashboard's job),
    # but the split must sum back to the total.
    result = compute_water_demand(100, 5, WaterSourceMix(desal_share_pct=70, reclaimed_share_pct=30))
    assert abs((result.desal_water_m3_per_day + result.reclaimed_water_m3_per_day) - result.total_water_m3_per_day) < 0.01


def test_energy_no_double_counting():
    result = compute_total_energy(
        it_energy_mwh_per_day=100,
        cooling_energy_mwh_per_day=30,
        desal_energy_mwh_per_day=5,
        other_energy_mwh_per_day=2,
        renewable_penetration_pct=0,
    )
    assert abs(result.total_energy_mwh_per_day - 137) < 0.01
    assert abs(result.grid_energy_mwh_per_day - result.total_energy_mwh_per_day) < 0.01


def test_carbon_scales_with_grid_energy_and_intensity():
    low = compute_carbon(100, 200)
    high = compute_carbon(100, 400)
    assert high.grid_emissions_t_co2e_per_day > low.grid_emissions_t_co2e_per_day


def test_cost_rejects_negative_price():
    with pytest.raises(ValueError):
        compute_operational_cost(100, -0.1, 50, 2.0)


def test_resilience_higher_desal_share_lowers_weri_all_else_equal():
    low_desal = compute_weri(
        water_wue_l_per_kwh=1.0, desal_share_pct=20, regional_water_stress_score=100,
        grid_carbon_g_per_kwh=300, renewable_penetration_pct=30,
    )
    high_desal = compute_weri(
        water_wue_l_per_kwh=1.0, desal_share_pct=90, regional_water_stress_score=100,
        grid_carbon_g_per_kwh=300, renewable_penetration_pct=30,
    )
    assert high_desal.weri_score < low_desal.weri_score, \
        "Higher desalination reliance should not improve resilience, all else equal."


def test_resilience_rejects_bad_weights():
    with pytest.raises(ValueError):
        compute_weri(
            water_wue_l_per_kwh=1.0, desal_share_pct=50, regional_water_stress_score=50,
            grid_carbon_g_per_kwh=300, renewable_penetration_pct=30,
            weights={"water_dep": 0.5, "water_stress": 0.5, "carbon": 0.5, "grid_dep": 0.5},
        )
