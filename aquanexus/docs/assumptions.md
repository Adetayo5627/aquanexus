# AquaNexus — assumptions

This document lists every material engineering assumption baked into the MVP, separate from the sourced/derived data in `data/sources.csv`.

| Assumption | Where used | Why |
|---|---|---|
| `Q_IT ≈ P_IT` (all IT power becomes heat) | `models/workload.py` | Standard first-approximation simplification for early-stage data-centre energy models; ignores second-order losses. |
| Ambient-temperature PUE penalty is linear per degree, by sensitivity class | `models/cooling.py` | No CFD/thermal simulation was built for this MVP; penalty coefficients are engineering placeholders, editable. |
| Hybrid water supply = 60% desalinated / 40% reclaimed | `app.py` | No public reference blend ratio found; chosen as a reasoned midpoint, clearly editable. |
| "Other" non-cooling water use = fixed 5 m3/day | `app.py` | Placeholder for auxiliary water use (sanitation, humidification); not derived from a real facility. |
| "Other" non-cooling energy = 2% of IT capacity | `app.py` | Placeholder for lighting/auxiliary loads; a common rough industry rule of thumb, not a cited figure. |
| Water cost = $2.00/m3 baseline, scaled by water-source relative cost | `app.py` | Indicative engineering estimate, not a real tariff. |
| Renewable penetration is a flat daily-average percentage, not an hourly dispatch simulation | `data/energy_profiles.yaml` | Full solar/battery dispatch modeling was out of scope for the MVP; documented as a stated simplification. |
| WERI weights (0.30 / 0.30 / 0.20 / 0.20) | `models/resilience.py` | A reasoned starting allocation reflecting water-stress and desalination dependence as the dominant MENA-specific risks; fully editable, not derived from a validated resilience science instrument. |
| Baseline configuration = evaporative cooling, 95% desalinated water, grid-only, normal climate | `app.py` | Chosen as a plausible "conventional" reference point for baseline-vs-optimized comparison, not a claim about any specific real facility. |

Every assumption above is implemented as an editable parameter or constant — none are hardcoded in a way that would require code restructuring to change.
