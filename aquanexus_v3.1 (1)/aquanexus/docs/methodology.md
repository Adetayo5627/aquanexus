# AquaNexus methodology

This version was substantially reworked following an external code review.
Where a change was made specifically in response to that review, it is
noted inline. See `docs/limitations.md` for what remains open.

## 1. Workload model

```
IT_power_MW = IT_capacity_MW * (utilization_pct / 100)
Q_IT ≈ P_IT
IT_energy_MWh_per_day = IT_power_MW * operating_hours_per_day
```
Unchanged from the previous version.

## 2. Cooling model (reworked)

Cooling is now two independent choices, not one, per review feedback that
conflating "how heat leaves the chip" with "how heat leaves the building"
produced unrealistic combinations:

- **Chip-side heat removal**: air / direct-to-chip / immersion
  (`data/chip_side.yaml`)
- **Heat rejection to ambient**: dry cooler / adiabatic / cooling tower
  (`data/heat_rejection.yaml`)

```
effective_PUE = 1.0 + chip_overhead + rejection_overhead

chip_overhead = pue_overhead_chip * (1 + max(0, dry_bulb_C - chip_temp_tolerance_C) * chip_degradation_rate)
rejection_overhead = pue_overhead_rejection * (1 + max(0, rejection_temp_C - rejection_threshold_C) * rejection_degradation_rate)

E_cooling (MWh/day) = heat_load_MW * (effective_PUE - 1) * operating_hours_per_day
Water_cooling (m3/day) = heat_load_MW * 1000 * WUE_rejection (L/kWh) * operating_hours_per_day / 1000
```

Water use effectiveness (WUE) now belongs entirely to the heat-rejection
choice, not the chip-side choice (review finding: "direct-to-chip cooling
paired with a cooling tower can reach a WUE close to that of evaporative
cooling").

**Absolute temperature now matters.** The previous version computed the
penalty as `ambient_temp_c - ambient_temp_normal_c`, which was zero
whenever the "normal" baseline was read from live weather, making the
absolute temperature irrelevant (identified in review as the most
important fix needed). This version uses each technology's temperature
THRESHOLD directly against absolute dry-bulb (chip-side, and dry-cooler
rejection) or wet-bulb (adiabatic and cooling-tower rejection) temperature.

**Wet-bulb temperature** is estimated from dry-bulb temperature and
relative humidity using Stull's (2011) published empirical approximation
(R. Stull, "Wet-Bulb Temperature from Relative Humidity and Air
Temperature," *Journal of Applied Meteorology and Climatology*, 50(11),
2267-2269), implemented in `models/cooling.py::wet_bulb_celsius`. This
directly addresses the review finding that humidity was fetched from the
weather API but never used, and that evaporative/water-based rejection
should respond to wet-bulb, not dry-bulb, temperature.

## 3-6. Desalination, water, energy, carbon models

Unchanged in form from the previous version (see `models/desalination.py`,
`models/water.py`, `models/energy.py`, `models/carbon.py` for exact
equations); carbon and energy aggregation still happen exactly once, in
`models/pipeline.py`, avoiding double-counting.

## 7. Cost model (reworked)

```
electricity_cost = grid_energy_kWh * electricity_price_usd_per_kWh
renewable_cost = solar_GENERATED_kWh * solar_LCOE_usd_per_kWh      (curtailed solar is still paid for)
battery_cost = battery_kWh * battery_capex_usd_per_kWh * CRF / 365
water_cost = total_water_m3 * water_cost_usd_per_m3
CRF = r(1+r)^n / ((1+r)^n - 1)
annualized_capex = combined_capex_relative * baseline_capex_usd_per_MW * IT_capacity_MW * CRF / 365
total_opex = electricity_cost + renewable_cost + water_cost
total_cost = total_opex + annualized_capex + battery_cost
```

Two fixes here, both identified in review: renewable electricity is now
priced at a nonzero levelized cost of energy (LCOE) instead of zero, and
capital expenditure (previously defined per technology but never used) is
now annualized via a capital recovery factor and added to daily cost. Both
`baseline_capex_usd_per_mw` and the LCOE figures are explicitly labeled
engineering assumptions in `models/cost.py` and `data/energy_profiles.yaml`,
not sourced procurement prices.

## 8. Resilience model — WERI (reworked)

**WERI remains an AquaNexus project-level decision metric, not an
internationally established scientific index.**

```
water_dependency_score = 0.3*WUE_score + 0.3*desal_share_pct + 0.4*desal_volume_score
heat_vulnerability_score = min(100, max(0, dry_bulb_C - chip_temp_tolerance_C) / 10 * 100)
carbon_score = normalize(grid_carbon_intensity, 150, 550)

WERI = 100 - (0.25*water_dependency_score + 0.25*water_stress_score
            + 0.15*carbon_score + 0.15*(100 - renewable_penetration)
            + 0.20*heat_vulnerability_score)
```

Three changes from the previous version, all from review feedback:

1. **Desalination dependency now blends share with actual volume**
   (`desal_volume_score`), not share alone, so a low-volume facility on
   mostly-desalinated water is no longer penalized almost as heavily as a
   high-volume one.
2. **A heat-vulnerability term was added**, since heat sensitivity was
   previously absent from the index despite being arguably the dominant
   regional climate risk.
3. **A country with no sourced water-stress score now defaults to a
   conservative 80/100**, not a neutral 50, so missing data can never
   outscore genuinely sourced data. In practice this fallback is no longer
   exercised for any of the 7 countries currently in scope, since real WRI
   2040 scores were located for all 7 (see `data/sources.csv`); it remains
   in the code as a safeguard for any future country added without a
   sourced figure.

All weights remain editable in `models/resilience.py`.

## 9. Water and grid constraint scenarios (newly connected)

Previously, the "Water availability -20%/-30%" and "Grid constraint"
scenarios changed values in `ScenarioInputs` that nothing downstream read,
so selecting them produced identical results to the Normal scenario. Now:

- Water availability scenarios compute a cap (`baseline water use for this
  country x multiplier`) and compare each candidate's total water use
  against it. Exceeding the cap sets `water_supply_exceeded=True` and a
  `water_supply_shortfall_m3_per_day`, and the optimizer excludes infeasible
  candidates from the Pareto frontier entirely rather than letting them win
  by ignoring the constraint.
- Grid constraint scenarios cap PEAK grid import (MW) at 85% of the
  conventional baseline's peak import (`GRID_CONSTRAINT_FRACTION`, an
  engineering assumption, editable). The cap is evaluated hour by hour in the
  dispatch model (section 12), so solar, batteries and simply a more
  efficient design can genuinely relieve it. Exceeding it makes the
  configuration infeasible.

## 10. Optimization engine

Decision space: 3 chip-side x 3 heat-rejection x 3 water sources x 3 energy
configurations = 81 combinations, still small enough for exact full
enumeration (guaranteed global optimum, no solver convergence risk).

With the cost and resilience fixes above, the Pareto frontier for the UAE
and Qatar test cases specifically checked in review now contains 18
non-dominated points each (previously exactly 1), with real, visible
trade-offs between water, energy, cost, and carbon across the frontier.

## 11. Recommendation engine

Converts the optimizer's chosen configuration into a plain-language
explanation using documented threshold rules operating on real output
values (heat vulnerability score, desalination share, renewable
penetration, WERI, and capex share of total cost), not freeform generation.

## 12. Energy supply: 24-hour solar + battery dispatch (second review)

The previous flat "X% of daily energy is renewable" shortcut was replaced by
`models/dispatch.py`. Each energy profile now sizes PV (MW per MW of average
load) and battery (hours of average load); a 24-hour greedy dispatch then
serves a flat facility load from solar first, then battery, then grid:

```
solar_h = PV_MW * profile_h * availability_multiplier
direct_h = min(load, solar_h);  surplus_h = solar_h - direct_h
battery charges from surplus only; discharges to cover the remaining load
grid_h = load - direct_h - discharge_h;  curtailed_h = surplus_h - charge_h
```

`profile_h` is an idealized clear-sky half-sine between 06:00 and 18:00,
scaled so its daily mean equals the country's solar capacity factor. The
realized renewable share is an OUTPUT of this dispatch (about 29% for the
solar profile and 48% for solar plus storage at a 22% capacity factor), not an
input. The reduced-solar scenario is now a parameter of `simulate()`, so the
dashboard and the screening engine cannot disagree about it.

## 13. Reclaimed water availability (second review)

Reclaimed water now has a finite supply
(`supply_capacity_m3_per_day_per_it_mw` x IT capacity x `water_reliability_pct`).
Demand above it falls back to desalination, raising the effective desalinated
share, desalination energy and the volume-scaled dependency in the resilience
score. The capacity figure is a placeholder (no sourced value was found).

## 14. Robustness analysis (second review)

`analysis/robustness.py` re-runs the screening under perturbed inputs:

1. **One-at-a-time:** WUE, cooling PUE overheads, electricity price, baseline
   capex, grid carbon, solar LCOE and battery cost each moved by a fixed
   fraction, plus alternative objective weights and alternative resilience
   score weights.
2. **Monte Carlo:** all of those drawn at once from a uniform band; the output
   is how often each configuration wins, and how often each individual
   design CHOICE (chip-side, heat rejection, water, energy) appears in the
   winner.

The exact winning combination can flip between near-ties while individual
choices stay stable; both are reported.

## 15. Decision filters

`apply_constraints` lets users impose hard limits (max cost, water and carbon
as a share of the baseline; minimum resilience score). Violating candidates
are marked infeasible and excluded from the Pareto set and from the best
configuration, exactly like scenario constraints.
