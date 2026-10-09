# AquaNexus — limitations

## Second external review (latest): what was fixed

1. **Reduced-solar scenario was ignored by the optimizer (critical defect).**
   The dashboard applied the multiplier but the optimizer evaluated normal
   solar. Every scenario input now flows through one shared builder and the
   multiplier is a parameter of `simulate()`. Regression test:
   `test_optimizer_respects_reduced_solar_scenario`.
2. **Renewable energy was a flat percentage.** Replaced by a 24-hour
   solar + battery + grid dispatch with PV and battery sizing, curtailment
   and a battery that charges only from surplus solar. Renewable share is now
   an output. See methodology section 12.
3. **Water source choice was largely cosmetic.** Reclaimed water now has a
   finite, reliability-derated supply; demand above it falls back to
   desalination. Regression test: `test_reclaimed_capacity_forces_desalination_fallback`.
4. **Grid constraint was only a flag.** It is now a peak-import cap evaluated
   hourly, so efficiency, solar and storage can relieve it.
5. **No uncertainty analysis.** Added one-at-a-time and Monte Carlo
   robustness checks with per-choice stability (Robustness tab).
6. **Five-way Pareto sets can be impractical.** Added decision filters.
7. **Explanations were post-hoc adjectives.** They are now quantitative
   changes against the baseline plus explicit trade-offs.
8. **Wording overstated the tool.** "Optimization" is now "configuration
   screening"; "Recommended configuration" is now "Best-performing
   configuration under stated assumptions"; "climate normal" is now
   "baseline ambient"; countries are described as capital-city
   representative sites.
9. **Live weather was display-only.** It is now an explicit choice:
   baseline ambient, live conditions, or design-day extreme.

A finding the new robustness check surfaced about the model itself: the top
configurations are near-ties (scores within about 0.01), so the exact winner
flips under +/-30% input changes, while some choices (notably reclaimed water
and a low-water heat-rejection method) stay stable.

### Still open after the second review

- Dispatch uses a flat facility load and an idealized clear-sky day; no
  seasonal or hourly weather, no part-load cooling behaviour.
- No sizing optimization (PV, battery, cooling capacity, desalination or
  reclaimed-water plant capacity); this is screening of fixed options.
- Water stress is a country-level score applied to a capital-city site.
- Capex, solar LCOE, battery cost, reclaimed capacity, climate baselines and
  the resilience weights remain engineering placeholders.
- No adaptation logic: when a water or grid limit is breached the option is
  marked infeasible rather than re-optimized (for example by switching to dry
  cooling or curtailing load).
- Cooling physics remain linear threshold coefficients, not equipment models.

---

## Earlier review (first round)

This version follows a round of external code review. Issues the review
raised that have been FIXED are listed first for transparency, followed by
what remains open.

## Fixed in this version, in response to external review

1. **Pareto frontier no longer collapses to one point.** Cost previously
   ignored capex entirely and priced renewable energy and all water sources
   identically, so the lowest-water/lowest-PUE option always won on every
   objective at once. Capex is now annualized via a capital recovery
   factor, renewable energy is priced at a nonzero LCOE, and water cost now
   varies correctly by source in the optimizer. The UAE and Qatar test
   cases specifically checked in review now produce 18-point frontiers
   (previously 1), verified by `test_optimizer_frontier_has_multiple_points`.
2. **Absolute temperature now affects results.** The cooling penalty
   previously depended on `ambient_temp - normal_temp`, which was zero
   whenever "normal" was read from live weather, so a 45C day and a 20C day
   produced identical results if both were each country's "normal." Cooling
   now uses absolute dry-bulb/wet-bulb temperature against each
   technology's threshold. Verified by `test_absolute_temperature_matters`.
3. **Humidity is now used.** Previously fetched but discarded. Water-based
   heat rejection now responds to wet-bulb temperature (Stull 2011
   approximation), so humid coastal sites correctly show evaporative/
   adiabatic rejection performing worse than in dry desert conditions.
4. **Water-availability and grid-constraint scenarios are now connected.**
   Previously they changed values nothing downstream read. They now cap
   water supply or grid import and flag exceeding configurations as
   infeasible, excluded from the Pareto frontier.
5. **Chip-side and heat-rejection are now separate choices**
   (`data/chip_side.yaml`, `data/heat_rejection.yaml`), so water use
   effectiveness correctly depends on heat-rejection choice, not chip-side
   choice alone.
6. **WERI no longer rewards missing data.** Jordan, Morocco, Algeria, and
   Tunisia now have real, sourced WRI 2040 water-stress scores (previously
   a neutral 50/100 substitute, which could outscore the UAE's genuinely
   sourced 100/100). A conservative 80/100 fallback remains in the code for
   any future country added without a sourced score.
7. **WERI now includes heat vulnerability**, previously absent despite
   being arguably the dominant regional climate risk.
8. **Desalination dependency is now volume-scaled, not share-only.** A
   low-volume facility on mostly-desalinated water is no longer penalized
   almost as heavily as a high-volume one at the same share.
9. **Optimizer weights are now user-editable sliders** in the dashboard,
   matching what the documentation always claimed.
10. **Baseline comparison chart shows % change from baseline**, so a large
    cost figure no longer makes every other bar invisible.
11. **Displayed values use 2-3 significant figures**, not false precision
    (e.g. no more "403.529 tCO2e" implying accuracy the inputs don't
    support).
12. **Documentation now matches actual app behavior.** All 7 countries run
    (previously this doc said 6 were blocked while the app actually ran
    all 7 and said so; that contradiction is resolved here).

## Still open

- **No formal validation against measured facility data.** All tests in
  `validation/test_models.py` are directional/consistency checks (34
  passing), not validation against real operating data.
- **No literature/competitor gap analysis** (`docs/novelty_gap.md`) has
  been produced; required before any novelty claim.
- **No sensitivity/tornado charts** implemented yet.
- **No Monte Carlo uncertainty analysis**; the model remains deterministic.
- **Capex and LCOE figures remain engineering placeholders**, not sourced
  procurement prices (see `docs/assumptions.md`). This is a direct
  trade-off of fixing the collapsed-frontier bug: real trade-offs now
  appear, but the exact capex/LCOE numbers driving them still need
  better sourcing.
- **Climate normals are single-point estimates**, not 30-year averages or
  an hourly design-year profile. Future climate projections (e.g. CMIP6
  SSP pathways for 2040/2050) were explicitly NOT added in this round:
  no real CMIP6 data was available to this project, and fabricating
  specific projected figures would violate this project's own standard of
  not inventing data. This remains a stated next step, not a silent gap.
- **Renewable energy remains a flat daily-average percentage**, not an
  hourly dispatch simulation.
- **Water modeling addresses consumption, not withdrawal**; once-through
  cooling systems are not modeled.
- **Grid carbon intensity for 6 of 7 countries remains a generic
  estimate**, not a country-specific sourced figure. Abu Dhabi's grid
  carbon trajectory is used as the UAE default regardless of which emirate
  a user conceptually means.
- **Indirect water use at thermal power plants is not modeled.** Many Gulf
  power plants use seawater cooling, which would reduce this effect, but
  this has not been confirmed for every grid modeled here, so it is
  neither included nor assumed negligible.
- **Water and grid constraint caps are single illustrative assumptions**
  (country-baseline-relative, or a flat 70% import fraction), not sourced
  infrastructure capacity data.

## What real validation would require

- Measured energy/water data from an operating MENA data centre.
- A specific, sourced cooling-system capex breakdown (vs. the current
  $1.5M/MW placeholder) and verified regional solar/storage LCOE figures
  (vs. the current $0.025-$0.05/kWh placeholders).
- DEWA's own published grid emission factor (not retrieved in this
  project's research).
- Sourced, country-specific grid carbon intensity for Saudi Arabia, Qatar,
  Jordan, Morocco, Algeria, and Tunisia.
- A resolved figure for UAE desalination's share of municipal water supply
  (currently a genuinely wide, unresolved 40-95% band in public reporting).
- Real climate projection data (e.g. CMIP6) to replace the current static
  climate-normal estimates with genuine future scenarios.

## Explicit non-claims

This project does not claim industrial-grade accuracy, validated
experimental results, a scientifically established resilience index (WERI
is explicitly project-level, not an external standard), or novelty pending
the required literature/competitor review.

## Added in v3
- Scale-up uses the pipeline MW as one facility; real portfolios are many sites. UAE pipeline MW is sourced (Mordor Intelligence 2026); other countries use illustrative round figures.
- Incremental capex counts cooling-system capex (relative factors x $1.5M/MW) and battery storage ($300/kWh). Solar is priced at LCOE, so no PV capex is added.
- The plausibility table compares model outputs with published fleet-level figures. It is not validation against a real facility.
- A design recommended for one scenario can breach a limit in another (for example a grid-import cap); the stress test reports this rather than hiding it.
