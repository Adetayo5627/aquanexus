# AquaNexus

**A Water–Energy–Climate Decision Engine for AI Data Centres in Water-Stressed MENA**

*Prototype engineering decision-support tool. Built for a hackathon/university research context — not an industrial control system.*

## Purpose

AI data centres are expanding rapidly in water-stressed MENA, where high ambient temperatures, desalination-dependent water supply, and constrained electricity grids make cooling a genuinely coupled water–energy–climate problem rather than three separate ones. Most existing tools optimize one dimension (cooling efficiency, or energy, or water) in isolation.

AquaNexus instead evaluates the **system-level trade-off**: cooling technology × water source × energy configuration, jointly, under climate stress scenarios, and surfaces the trade-offs transparently rather than hiding them behind a single unexplained score.

## Research question

*What combination of cooling technology, water source, and energy configuration provides the best balance between water consumption, energy consumption, cost, carbon impact, and resilience for an AI data centre operating under MENA climate and water constraints?*

## System boundary

```
AI WORKLOAD -> IT POWER -> HEAT LOAD -> COOLING SYSTEM -> WATER + ENERGY
                                                              |
                                              DESALINATION ---+
                                                              |
                                         TOTAL WATER-ENERGY FOOTPRINT -> CLIMATE STRESS
                                                              |
                                    PREDICT -> SIMULATE -> OPTIMIZE -> RECOMMEND -> DASHBOARD
```

## Honest scope statement

This is a **Phase 1–4 MVP** (scientific model, optimization engine, scenario engine, dashboard). Phases 5–6 (full validation report, complete documentation set) are a documented next step — see `docs/limitations.md`. The demonstration case is the **United Arab Emirates**, the only country profile with genuinely sourced parameters in this version. Saudi Arabia, Qatar, Jordan, Morocco, Algeria, and Tunisia are structurally present in `data/country_profiles.yaml` but intentionally left as `PLACEHOLDER — SOURCE REQUIRED` — no fabricated numbers were inserted for them.

## Installation

```bash
python -m venv .venv
```

**Windows:**
```bash
.venv\Scripts\activate
```

**macOS/Linux:**
```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Running tests

```bash
pytest validation/test_models.py -v
```

## Methodology

See `docs/methodology.md` for the full mathematical formulation of every model (workload, cooling, water, desalination, energy, carbon, cost, resilience/WERI) and `docs/assumptions.md` / `docs/limitations.md` for what this MVP does and does not claim.

## Data provenance

Every parameter's source and confidence level (`sourced` / `derived` / `estimated` / `placeholder`) is documented in `data/sources.csv`. This is a feature of the project, not an afterthought: AquaNexus is explicit about the difference between what is measured, what is derived, and what is a labeled engineering assumption.

## Architecture

```
aquanexus/
├── app.py                        # Streamlit dashboard entry point
├── requirements.txt
├── README.md
├── data/
│   ├── country_profiles.yaml     # UAE sourced; others PLACEHOLDER — SOURCE REQUIRED
│   ├── cooling_technologies.yaml
│   ├── energy_profiles.yaml
│   ├── water_profiles.yaml
│   └── sources.csv               # provenance ledger for every parameter
├── models/
│   ├── workload.py
│   ├── cooling.py
│   ├── water.py
│   ├── energy.py
│   ├── desalination.py
│   ├── carbon.py
│   ├── cost.py
│   ├── resilience.py             # WERI (AquaNexus project-level metric)
│   └── pipeline.py                # ties all models into one simulate() call
├── optimization/
│   └── optimizer.py              # brute-force Pareto scan + weighted objective
├── scenarios/
│   └── stress_tests.py           # 9 "what-if" scenarios
├── recommendation.py             # rule-based explanation engine
├── validation/
│   └── test_models.py            # 11 passing sanity/consistency tests
└── docs/
    ├── methodology.md
    ├── assumptions.md
    └── limitations.md
```

## What a judge can do with this

1. Select UAE, set IT capacity and workload utilization.
2. Choose cooling technology, water source, and energy configuration.
3. Apply a climate/what-if scenario (heatwave, water stress, price shock, grid constraint).
4. See system status (IT load, PUE, water use, energy, cost, carbon, WERI).
5. Compare against a fixed baseline (bar chart + CSV export).
6. Click "Run optimization" to enumerate all 45 technology/water/energy combinations, see the Pareto frontier, and get a plain-language recommendation with its reasoning.

## No fabricated claims

This project does not claim to be "the world's first," "revolutionary," or to guarantee specific savings percentages. Results shown are prototype-model outputs from documented, editable assumptions — not measured facility performance.
