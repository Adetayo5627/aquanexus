# AquaNexus — limitations

Honest, explicit limitations of this MVP, per project instructions to never overstate scientific rigor.

## Not yet done (Phases 5–6 of the development plan)

- **No formal validation report against published case studies.** `validation/test_models.py` contains 11 passing directional/consistency sanity tests (e.g. "heatwave must not decrease cooling energy"), not validation against measured real-facility data.
- **No literature/competitor gap analysis document** (`docs/novelty_gap.md`) has been produced yet. The brief explicitly requires this before any novelty claim is made — none is made in this version.
- **No sensitivity/tornado charts** have been implemented yet, though the architecture (all parameters as named, editable inputs) supports adding them without restructuring.
- **No Monte Carlo uncertainty analysis.** The model is fully deterministic in this version, as permitted for an MVP by the brief.

## Modeling simplifications

- **Ambient-temperature cooling penalty is a simplified linear model**, not a validated thermal/CFD simulation. It is directionally correct (verified by unit test) but not quantitatively validated.
- **Renewable energy is modeled as a flat daily-average penetration percentage**, not an hourly solar/battery dispatch simulation. A real facility's actual grid-vs-renewable split would vary significantly by hour and season.
- **Water modeling addresses consumption, not withdrawal.** Once-through or closed-loop-with-blowdown cooling systems, which withdraw and return water, are not modeled; this MVP assumes evaporative/consumptive loss dominates, which is reasonable for the cooling technologies modeled but not universal.
- **Only UAE has genuinely sourced country parameters.** The other six MENA country profiles are structural placeholders (`PLACEHOLDER — SOURCE REQUIRED`) and the dashboard blocks simulation for them rather than fabricating numbers.
- **Grid carbon intensity uses Abu Dhabi's EWEC-derived trajectory by default** even when "UAE" is selected broadly; Dubai's DEWA-estimated figure is present in the data file but the dashboard does not yet let the user pick between emirates. This is a known simplification, not an oversight.
- **Desalination share of UAE water supply has a genuinely wide, unresolved uncertainty band (40–95%)** in public reporting; this MVP does not attempt to resolve that conflict, only to represent it honestly.

## What real validation would require

- Measured energy/water data from an operating MENA data centre (even anonymized/aggregated) to validate the cooling and desalination-energy equations against ground truth.
- DEWA's own published Sustainability Report grid emission factor (not retrieved in this research pass — should be pulled directly from dewa.gov.ae before any Dubai-specific claim is made).
- A resolved, single authoritative figure for UAE desalination's share of municipal water supply (e.g. from FAO AQUASTAT or the UAE Ministry of Energy and Infrastructure).
- Verified country-level parameters for Saudi Arabia, Qatar, Jordan, Morocco, Algeria, and Tunisia before those profiles can be used for anything beyond structural demonstration.

## Explicit non-claims

This project does not claim: industrial-grade accuracy, validated experimental results, a scientifically established resilience index (WERI is explicitly project-level, not an external standard), or novelty pending the literature/competitor review required by the brief before such a claim could be responsibly made.
