"""
stress_tests.py

Defines the "What if?" scenario engine. Scenarios are explicit, labeled
perturbations applied to a base scenario's inputs -- NOT climate projections.
Per project instructions: these are stress-test scenarios for MVP
demonstration, not forecasts.
"""

from dataclasses import dataclass, replace
from typing import Callable, Dict


@dataclass
class ScenarioInputs:
    """Mutable bundle of inputs a scenario can perturb."""
    ambient_temp_c: float
    water_availability_multiplier: float   # 1.0 = normal, 0.8 = -20%, etc.
    electricity_price_multiplier: float    # 1.0 = normal, 1.3 = +30%, etc.
    workload_utilization_pct: float
    grid_constrained: bool
    solar_availability_multiplier: float   # 1.0 = normal


def scenario_normal(base: ScenarioInputs) -> ScenarioInputs:
    return replace(base)


def scenario_heatwave_3c(base: ScenarioInputs) -> ScenarioInputs:
    return replace(base, ambient_temp_c=base.ambient_temp_c + 3.0)


def scenario_extreme_heatwave_5c(base: ScenarioInputs) -> ScenarioInputs:
    return replace(base, ambient_temp_c=base.ambient_temp_c + 5.0)


def scenario_water_availability_minus_20(base: ScenarioInputs) -> ScenarioInputs:
    return replace(base, water_availability_multiplier=base.water_availability_multiplier * 0.8)


def scenario_water_availability_minus_30(base: ScenarioInputs) -> ScenarioInputs:
    return replace(base, water_availability_multiplier=base.water_availability_multiplier * 0.7)


def scenario_electricity_price_plus_30(base: ScenarioInputs) -> ScenarioInputs:
    return replace(base, electricity_price_multiplier=base.electricity_price_multiplier * 1.3)


def scenario_workload_plus_25(base: ScenarioInputs) -> ScenarioInputs:
    return replace(base, workload_utilization_pct=min(100.0, base.workload_utilization_pct * 1.25))


def scenario_grid_constraint(base: ScenarioInputs) -> ScenarioInputs:
    return replace(base, grid_constrained=True)


def scenario_reduced_solar(base: ScenarioInputs) -> ScenarioInputs:
    return replace(base, solar_availability_multiplier=base.solar_availability_multiplier * 0.6)


SCENARIOS: Dict[str, Callable[[ScenarioInputs], ScenarioInputs]] = {
    "Normal": scenario_normal,
    "Heatwave (+3C)": scenario_heatwave_3c,
    "Extreme heatwave (+5C)": scenario_extreme_heatwave_5c,
    "Water availability -20%": scenario_water_availability_minus_20,
    "Water availability -30%": scenario_water_availability_minus_30,
    "Electricity price +30%": scenario_electricity_price_plus_30,
    "AI workload +25%": scenario_workload_plus_25,
    "Grid constraint": scenario_grid_constraint,
    "Reduced solar availability": scenario_reduced_solar,
}
