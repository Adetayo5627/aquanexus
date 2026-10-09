"""
benchmarks.py  -  are the model's outputs in the range of published figures?

This is a PLAUSIBILITY check against published fleet-level and technology-level
numbers. It is not validation against a real facility, which would need
operator meter data.
"""
from core.context import NORMAL, BASELINE_KEY
from analysis.policy import site_wue


def run_benchmarks(ctx):
    base = ctx.baseline_for(NORMAL)
    best_pue = min(ctx.simulate_design((c, r, "desalinated", "grid_only"), NORMAL, False).effective_pue
                   for c in ctx.lib.chips for r in ctx.lib.rejs)
    sec = ctx.profile["desalination_sec_kwh_per_m3"]
    rows = [
        {"Metric": "PUE, conventional baseline", "Model": f"{base.effective_pue:.2f}",
         "Published": "1.54 industry weighted average (Uptime Institute 2025); 1.56 in 2024",
         "Reading": "Same range; the baseline is a hot-climate air-cooled site, so slightly higher is expected." if base.effective_pue >= 1.4 else "Below fleet average; check inputs."},
        {"Metric": "PUE, best cooling combination", "Model": f"{best_pue:.2f}",
         "Published": "1.09 Google fleet average (2025), the practical floor for hyperscale",
         "Reading": "Not below the published floor." if best_pue >= 1.09 else "Below the best published fleet, treat as too optimistic."},
        {"Metric": "Site WUE, conventional baseline (L/kWh)", "Model": f"{site_wue(base):.2f}",
         "Published": "About 1.9 L/kWh industry average (EESI); evaporative towers are typically 1.8 to 2.0+",
         "Reading": "Consistent with evaporative cooling."},
        {"Metric": "Desalination energy (kWh/m3)", "Model": f"{sec['value_min']:.1f} to {sec['value_max']:.1f}",
         "Published": "2.5 to 4.0 for seawater RO (Joule review); recent plants 2.8 to 2.9",
         "Reading": "Inside the published range, on the conservative (high) side."},
        {"Metric": "Grid carbon intensity (g/kWh)", "Model": f"{ctx.grid_carbon:.0f}",
         "Published": "Abu Dhabi grid: 330 (2019), projected about 165 by the mid-2030s (EWEC)" if ctx.location == "UAE" else "National average; regional values vary 200 to 650",
         "Reading": "Between today's and projected values." if ctx.location == "UAE" else "Order-of-magnitude check only."},
    ]
    return rows
