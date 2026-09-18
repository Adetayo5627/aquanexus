# AquaNexus methodology

## 1. Workload model

```
IT_power_MW = IT_capacity_MW * (utilization_pct / 100)
Q_IT ≈ P_IT   (assumption: all IT electricity becomes heat)
IT_energy_MWh_per_day = IT_power_MW * operating_hours_per_day
```

## 2. Cooling model

```
E_cooling (MWh/day) = heat_load_MW * (effective_PUE - 1) * operating_hours_per_day
Water_cooling (m3/day) = heat_load_MW * 1000 * WUE (L/kWh) * operating_hours_per_day / 1000
```

`effective_PUE` = `PUE_typical` adjusted by a simplified ambient-temperature penalty:

```
effective_PUE = PUE_typical * (1 + max(0, ΔT) * penalty_per_degree[sensitivity_class])
```

This penalty function is an MVP-level simplification, not a validated thermal/CFD model. See `docs/limitations.md`.

## 3. Desalination model

```
E_desal = Water_desalinated * SEC_desalination
```

Where `SEC_desalination` (specific energy consumption, kWh/m3) is a literature-derived typical range (3.0–4.0 kWh/m3 for modern SWRO), not a UAE-measured figure.

## 4. Water model

```
total_water_m3_per_day = cooling_water_m3_per_day + other_water_m3_per_day
desal_water = total_water * desal_share_pct / 100
reclaimed_water = total_water * (100 - desal_share_pct) / 100
```

This models water **consumption**, not withdrawal (see limitations).

## 5. Energy model

```
E_total = E_IT + E_cooling + E_desalination + E_other
grid_energy = E_total * (1 - renewable_penetration_pct / 100)
renewable_energy = E_total * renewable_penetration_pct / 100
```

No component is counted twice — `E_total` is assembled exactly once, in `models/pipeline.py`.

## 6. Cost model (operational, indicative)

```
electricity_cost = grid_energy_kWh * electricity_price_usd_per_kWh
water_cost = total_water_m3 * water_cost_usd_per_m3
total_opex = electricity_cost + water_cost
```

CAPEX is tracked separately as a relative multiplier in `cooling_technologies.yaml` and is **not** included in these daily OPEX figures.

## 7. Carbon model

```
Carbon_kg = grid_energy_kWh * grid_carbon_intensity_g_per_kWh / 1000
```

Renewable electricity is treated as zero direct operational emissions (lifecycle/embodied emissions of solar/battery hardware are out of scope for this MVP).

## 8. Resilience model — WERI (Water-Energy Resilience Index)

**WERI is an AquaNexus project-level decision metric, not an internationally established scientific index.**

```
water_dependency_score = 0.5 * min(100, WUE/2.5*100) + 0.5 * desal_share_pct
carbon_score = normalize(grid_carbon_g_per_kWh, 150, 550) -> 0-100

WERI = 100 - (
    0.30 * water_dependency_score
  + 0.30 * regional_water_stress_score
  + 0.20 * carbon_score
  + 0.20 * (100 - renewable_penetration_pct)
)
```

All weights are editable in `models/resilience.py`.

## 9. Optimization engine

The decision space (5 cooling technologies × 3 water mixes × 3 energy configurations = 45 combinations) is **fully enumerated** rather than solved with a continuous optimizer. This is mathematically exact for a discrete space of this size (guaranteed global optimum, no solver convergence risk).

**Pareto frontier**: a candidate is non-dominated if no other candidate is ≤ it on all 5 objectives (water, energy, cost, carbon, −resilience) and < on at least one.

**Weighted objective** (per the brief's formulation):

```
J = wW*water_norm + wE*energy_norm + wC*cost_norm + wCO2*carbon_norm - wR*resilience_norm
```

All objectives are min-max normalized across the candidate set before weighting. Lower J is better. All weights are user-editable in `app.py`.

## 10. Recommendation engine

`recommendation.py` converts the optimizer's chosen candidate into a plain-language explanation using simple, documented rule thresholds (e.g. "desal share ≥ 70% → flag desalination-energy dependency"). The explanation text is assembled from the actual model outputs of the winning candidate — it is not freeform-generated or scenario-hardcoded.
