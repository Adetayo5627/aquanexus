# AquaNexus

**A Water–Energy–Climate Decision Engine for AI Data Centres in Water-Stressed MENA**

*Prototype engineering decision-support tool. Built for a hackathon/university research context — not an industrial control system.*

## Purpose

AI data centres are expanding rapidly in water-stressed MENA, where high ambient temperatures, desalination-dependent water supply, and constrained electricity grids make cooling a genuinely coupled water–energy–climate problem rather than three separate ones. Most existing tools optimize one dimension (cooling efficiency, or energy, or water) in isolation.

AquaNexus instead evaluates the **system-level trade-off**: cooling choice × water source × energy configuration, jointly, under climate stress scenarios, and surfaces the trade-offs transparently rather than hiding them behind a single unexplained score.

## Research question

*What combination of cooling technology, water source, and energy configuration provides the best balance between water consumption, energy consumption, cost, carbon impact, and resilience for an AI data centre operating under MENA climate and water constraints?*

## Second review (latest)

A second external review found a real defect (the reduced-solar scenario was ignored by the optimizer) and several modeling-validity problems. All were addressed: a 24-hour solar and battery dispatch replaces the flat renewable percentage, reclaimed water has a finite supply, the grid constraint is a peak-import cap, and a Robustness tab tests whether the answer survives uncertain inputs. The tool is now described as **configuration screening**, and its best result as **best-performing under stated assumptions**. See `docs/limitations.md`.

## Post-review rebuild (first round)

This version follows a round of external code review that identified several real modeling gaps, most importantly that the optimizer's Pareto frontier had collapsed to a single point because cost ignored capital expenditure and priced renewable energy and all water sources identically. All issues raised were addressed; see `docs/limitations.md` for the full list of what was fixed and what remains open. Headline fixes:

- Cooling is now **chip-side heat removal × heat-rejection method** (two independent choices), not one combined "cooling technology."
- Simulations use each country's **climate normal** for absolute temperature and humidity, not the live weather reading at page load, so absolute ambient conditions now genuinely affect results.
- Water-based heat rejection responds to **wet-bulb temperature** (Stull 2011 approximation), so humid coastal sites correctly show worse evaporative performance than dry desert sites.
- Cost includes **annualized capex and nonzero renewable LCOE**; the Pareto frontier now shows real trade-offs (18 non-dominated points for the UAE and Qatar test cases specifically checked in review, up from 1).
- Water-availability and grid-constraint scenarios now **cap results and flag infeasibility** instead of being silently ignored.
- All 7 MENA countries now have **real sourced WRI 2040 water-stress scores**, closing the gap where missing data scored better than sourced data.

## System boundary

```
AI WORKLOAD -> IT POWER -> HEAT LOAD -> CHIP-SIDE REMOVAL -> HEAT REJECTION -> WATER + ENERGY
                                                                                    |
                                                                   DESALINATION ----+
                                                                                    |
                                                     TOTAL WATER-ENERGY FOOTPRINT -> CLIMATE STRESS
                                                                                    |
                                               PREDICT -> SIMULATE -> OPTIMIZE -> RECOMMEND -> DASHBOARD
```

## Installation

```bash
python -m venv .venv
```

**Windows:** `.venv\Scripts\activate`
**macOS/Linux:** `source .venv/bin/activate`

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Running tests

```bash
pytest validation/test_models.py -v
```

35 tests, including several written specifically as regression tests for
issues found in two rounds of external review (e.g. `test_optimizer_frontier_has_multiple_points`,
`test_absolute_temperature_matters`, `test_missing_water_stress_is_conservative_not_neutral`).

## Methodology

See `docs/methodology.md` for the full mathematical formulation and
`docs/assumptions.md` / `docs/limitations.md` for what this MVP does and
does not claim.

## Data provenance

Every parameter's source and confidence level is documented in
`data/sources.csv`. All 7 MENA countries now have sourced electricity
prices and sourced WRI water-stress scores; grid carbon intensity and
desalination share remain generic estimates for 6 of 7 countries pending
better data (UAE has sourced/derived figures for both emirates covered).

## Architecture

```
aquanexus/
├── app.py                        # Streamlit dashboard entry point
├── requirements.txt
├── README.md
├── data/
│   ├── country_profiles.yaml     # all 7 countries, sourced electricity price + WRI water stress
│   ├── chip_side.yaml            # air / direct-to-chip / immersion
│   ├── heat_rejection.yaml       # dry cooler / adiabatic / cooling tower
│   ├── energy_profiles.yaml      # now includes LCOE per profile
│   ├── water_profiles.yaml
│   └── sources.csv               # provenance ledger for every parameter
├── models/
│   ├── workload.py
│   ├── cooling.py                # chip-side x heat-rejection, wet-bulb physics
│   ├── water.py
│   ├── energy.py
│   ├── desalination.py
│   ├── carbon.py
│   ├── cost.py                   # annualized capex + renewable LCOE
│   ├── resilience.py             # WERI: heat vulnerability + volume-scaled desal dependency
│   ├── dispatch.py               # 24-hour solar + battery + grid dispatch
│   ├── live_data.py               # live climate fetch (contextual only, not used in simulation)
│   └── pipeline.py                # ties all models into one simulate() call
├── optimization/
│   └── optimizer.py              # full enumeration + Pareto + weighted objective, infeasibility-aware
├── scenarios/
│   └── stress_tests.py           # 9 "what-if" scenarios, water/grid caps now connected
├── analysis/
│   └── robustness.py             # one-at-a-time + Monte Carlo stability checks
├── recommendation.py             # quantitative explanation vs baseline
├── validation/
│   └── test_models.py            # 35 passing tests, many added as review regression tests
└── docs/
    ├── methodology.md
    ├── assumptions.md
    └── limitations.md
```

## What a judge can do with this

1. Select any of the 7 MENA countries, set IT capacity and workload utilization.
2. Choose chip-side cooling, heat-rejection method, water source, and energy configuration independently.
3. Apply a climate/what-if scenario (heatwave, water stress, price shock, grid constraint) and see infeasible configurations flagged.
4. See a configuration summary in the main page (visible on mobile), with system status and a desalination-energy-share callout.
5. Compare against a fixed baseline, shown as % change so no single large metric dominates the chart.
6. Click "Run optimization" to enumerate all 81 combinations, adjust objective weights live, see the Pareto frontier, and get a plain-language recommendation with its reasoning.

## No fabricated claims

This project does not claim to be "the world's first," "revolutionary," or to guarantee specific savings percentages. Results shown are prototype-model outputs from documented, editable assumptions, not measured facility performance.


## v3 upgrade (final-stage release)

- **Impact tab first**: one headline sentence, five KPI cards with uncertainty ranges, a 9-scenario stress test (conventional vs recommended), scale-up to national pipeline capacity, UN Water / SDG alignment, and a downloadable one-page decision brief.
- **Policy Lab**: set a WUE cap, PUE cap, non-potable share or renewable share and see the cost of compliance.
- **Live model checks** (10 conservation / monotonicity / consistency tests) and a **plausibility table** against published PUE, WUE, desalination and grid-carbon figures.
- **Judge demo** button in the sidebar (UAE, 50 MW, extreme heatwave).
- Architecture: `core/context.py` (SiteContext) is the single source of truth for scenario inputs; `analysis/{scaling,policy,selfcheck,benchmarks,briefing}.py` are new; `ui/style.py` holds styling.
- 41 automated tests: `python -m pytest validation`.
