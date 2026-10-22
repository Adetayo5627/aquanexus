# AquaNexus — assumptions

Every material engineering assumption in the current version, separate from
the sourced/derived data in `data/sources.csv`. Assumptions added or changed
during the post-review rebuild are marked **(new)**.

| Assumption | Where used | Why |
|---|---|---|
| `Q_IT ≈ P_IT` (all IT power becomes heat) | `models/workload.py` | Standard first-approximation simplification. |
| Chip-side and heat-rejection PUE overheads, temperature thresholds, and degradation rates | `data/chip_side.yaml`, `data/heat_rejection.yaml` | Literature-derived typical ranges (ASHRAE-style inlet tolerances, general cooling-engineering judgment), not a specific facility study. **(new)** |
| Wet-bulb temperature via Stull (2011) approximation | `models/cooling.py` | A published, peer-reviewed meteorological approximation, not a project-specific formula; valid for standard atmospheric pressure and typical terrestrial ranges. **(new)** |
| Relative humidity "climate normal" per country | `data/country_profiles.yaml` | No sourced climatological humidity normal was located in this project's research; values are reasoned estimates based on coastal vs. inland geography (e.g. humid coastal Doha/Dubai vs. dry inland Riyadh). **(new)** |
| Baseline cooling-system capex of $1.5M per MW of IT capacity | `models/cost.py` | No public, cooling-system-specific capex breakdown was located; this is an explicit placeholder, editable, pending better data. **(new)** |
| Discount rate 8%, equipment lifetime 10 years (capital recovery factor) | `models/cost.py` | Common generic infrastructure-finance defaults, not a project-specific study. **(new)** |
| Solar LCOE $0.025/kWh, solar+storage blended LCOE $0.05/kWh | `data/energy_profiles.yaml` | Set above the real, publicly reported Al Dhafra solar PPA record ($0.0132-0.0135/kWh) to represent a generic regional estimate rather than claiming every facility matches that specific record project. **(new)** |
| Grid constraint caps import at 70% of baseline demand | `app.py` (`GRID_CONSTRAINT_FRACTION`) | No sourced per-country grid-headroom dataset was located; this is an illustrative, editable assumption so the scenario has a connected effect rather than none. **(new)** |
| Water-availability scenarios cap supply at (country baseline x scenario multiplier) | `app.py` | Uses each country's own baseline water use as the reference point, rather than an arbitrary global constant. **(new)** |
| Desalination volume reference ceiling of 3,000 m3/day for WERI normalization | `models/resilience.py` | Chosen as a round number above the highest volumes this MVP's scenarios typically produce at 100 MW IT capacity; editable. **(new)** |
| Heat vulnerability saturates 10C above a technology's temperature tolerance | `models/resilience.py` | Engineering assumption for how quickly heat risk should be treated as "maximal" in the index; editable. **(new)** |
| Hybrid water supply = 60% desalinated / 40% reclaimed | `app.py` | No public reference blend ratio found; a reasoned, editable midpoint. |
| "Other" non-cooling water use = fixed 5 m3/day; "other" energy = 2% of IT capacity | `app.py` | Placeholders for auxiliary loads, not derived from a real facility. |
| Baseline configuration = air chip-side + cooling tower rejection, 95% desalinated water, grid-only, climate normal | `app.py` | A plausible "conventional" reference point for comparison, not a claim about any specific real facility. |

| PV sized at 1.3 MW (solar) or 2.2 MW (solar+storage) per MW of average load; battery 4 hours of average load | `data/energy_profiles.yaml` | Illustrative sizing so the dispatch produces renewable shares near typical screening values; not optimized and not sourced. **(new, second review)** |
| Idealized clear-sky solar shape, flat facility load, no clouds, no grid export, battery charged only from surplus solar | `models/dispatch.py` | Keeps the dispatch a transparent screening model. **(new, second review)** |
| Battery round-trip efficiency 90%, charge/discharge limit 0.5C, $300/kWh installed | `models/dispatch.py`, `models/cost.py` | Generic engineering placeholders. **(new, second review)** |
| Reclaimed-water supply 12 m3/day per MW of IT capacity, derated by 85% reliability | `data/water_profiles.yaml` | PLACEHOLDER; no sourced figure. **(new, second review)** |
| Grid constraint = peak import limited to 85% of the conventional baseline's peak | `app.py` | Illustrative and editable; no per-country grid-headroom data was found. **(changed, second review)** |
| Design-day extreme = baseline ambient + 7 C | `app.py` | Illustrative, editable. **(new, second review)** |
| Uncertainty band of +/-30% on estimated inputs in the robustness check | `app.py` (slider) | A common screening range, user adjustable from 10% to 50%. **(new, second review)** |

Every assumption above is an editable parameter or constant, none require
code restructuring to change.