# AquaNexus

**A Water–Energy–Climate Decision Engine for Cooling AI Data Centres in Water-Stressed MENA**

Team PAUWES CoolNEXUS (CMAT-00155) · Khalifa University–UNESCO Global Water Hackathon 2026 · Theme 5: Energy–Water Nexus and Climate Resilience
Registered project: *Water for AI: A Climate-Resilient Framework for Energy-Efficient Data Centre Cooling*

Live app: https://aquanexus.streamlit.app/ · Version 3.1 (October 2026)

> A configuration-screening tool built on literature-based estimates. It ranks alternatives under stated assumptions; it is **not** a validated model of a specific facility. See `docs/limitations.md`.

## The question

How can a climate-resilient, energy-efficient cooling framework for AI data centres in the UAE reduce freshwater and desalinated-water dependency while remaining technically and economically viable?

AquaNexus answers it operationally: for a facility of a given size at a given MENA site, which combination of **chip-side cooling × heat rejection × water source × energy supply** performs best on **water, energy, cost, carbon and resilience** together, how much better is it than conventional practice, and how reliable is that conclusion?

## Headline result (UAE, 50 MW, balanced priorities)

Best-performing design: direct-to-chip liquid cooling + adiabatic heat rejection + reclaimed water + grid and solar PV.
Against a conventional air-cooled, cooling-tower, desalinated, grid-only design: **water −80%, energy −11%, carbon −36%, all-in cost −8%**, resilience index 36 → 57.
Under ±30% uncertainty drawn separately for every technology (extreme heatwave, 300 draws): water −87% to −70% (5th–95th percentile), cheaper than conventional in 97% of draws.

## What the model covers

```
AI workload -> IT power -> heat load -> chip-side removal -> heat rejection -> cooling energy + water
                                                                                    |
                                     water source (desalinated / reclaimed, finite) -+-> desalination energy
                                                                                    |
                          total facility energy -> 24 h solar + battery + grid dispatch -> carbon, cost
                                                                                    |
                         resilience index (WERI) -> screening of 81 designs -> recommendation
```

- 3 chip-side × 3 heat-rejection × 3 water-source × 3 energy options = **81 designs**, enumerated exactly.
- Pareto frontier on 5 objectives, weighted ranking with 5 priority presets, user decision filters.
- 9 stress scenarios (heatwaves, water cuts, price shock, workload growth, grid peak cap, low solar).
- Robustness: one-at-a-time, Monte Carlo (common or technology-specific factors), headline uncertainty ranges.
- Policy Lab (cost of WUE / PUE / reuse / renewable rules) and national scale-up.
- 10 live self-consistency checks and a plausibility table against published PUE, WUE, desalination and grid-carbon figures.

## Install and run

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The dashboard re-screens all 81 designs on every input change (about 10 ms); there is no run button except for the optional robustness analysis. The sidebar has a **Load judge demo** button (UAE, 50 MW, extreme heatwave).

## Tests

```bash
python -m pytest validation -v
```

43 automated tests, including regression tests for every issue found in review (for example `test_optimizer_frontier_has_multiple_points`, `test_absolute_temperature_matters`, `test_optimizer_respects_reduced_solar_scenario`, `test_independent_mode_widens_water_range_but_keeps_saving`).

## Report figures

All figures of the technical report are regenerated from the model with

```bash
python scripts/make_report_figures.py . figures/
```

## Repository layout

```
aquanexus/
├── app.py                     Streamlit dashboard (Impact, Explorer, Screening, Policy Lab, Robustness, Method & validation)
├── core/context.py            SiteContext: the single builder of scenario inputs, caps and baselines
├── models/                    workload, cooling (Stull wet-bulb), water, desalination, energy,
│                              dispatch (24 h solar/battery/grid), carbon, cost (annualised capex), resilience (WERI), pipeline
├── optimization/optimizer.py  enumeration, feasibility, Pareto frontier, weighted score, decision filters
├── scenarios/stress_tests.py  the 9 stress scenarios
├── analysis/                  robustness, policy, scaling, selfcheck, benchmarks, briefing
├── recommendation.py          quantitative explanation against the conventional baseline
├── data/                      YAML parameters + sources.csv provenance ledger (confidence label per value)
├── docs/                      methodology, assumptions, limitations
├── scripts/                   make_report_figures.py (all report figures)
└── validation/test_models.py  43 tests
```

## Data provenance

Every parameter carries a confidence label (sourced, derived, estimated, generic) and is listed in `data/sources.csv`. Water-stress scores for all seven countries are WRI's projected 2040 country scores (Maddocks, Young & Reig, 2015). Electricity prices are sourced or derived for all seven countries. Grid carbon intensity is derived for Abu Dhabi and generic for the other six countries. Cooling coefficients, capex factors, solar LCOE, battery cost and reclaimed-water supply are engineering estimates and are the first targets for calibration.

## Version history

- **v1** – cooling split into chip-side removal × heat rejection; absolute-temperature thresholds and wet-bulb physics.
- **v2 (after first external review)** – annualised capex, non-zero solar LCOE and source-specific water prices (the Pareto frontier had collapsed to one point); sourced water-stress scores with a conservative fallback.
- **v3 (after second external review)** – one SiteContext for all tabs (the reduced-solar scenario had been ignored by the optimiser); 24 h dispatch; finite reclaimed supply; grid peak-import cap; robustness, Policy Lab, scale-up, live checks, benchmarks, decision brief.
- **v3.1 (this version)** – technology-specific uncertainty mode (each technology's WUE and PUE overhead drawn separately), used by default for headline ranges; Saudi water-stress score corrected to 99.8 (4.99/5) and water-stress source corrected to WRI 2015; documentation aligned with the code. No reported nominal result changes.

## Known limitations (summary)

Representative capital-city sites with a single temperature and humidity; WUE fixed per technology and heat rejected taken as the IT heat load only (so heatwave water does not rise, which makes savings conservative); flat load and clear-sky solar; with at most 4 h of storage the night sets the grid peak, so the grid-constraint scenario is in effect an efficiency limit; direct water only; WERI is a project-level index with judgement-based weights. Full list: `docs/limitations.md`.
