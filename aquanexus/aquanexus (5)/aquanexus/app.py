"""
app.py  -  AquaNexus.   Run with: streamlit run app.py

A water-energy-climate decision engine for AI data centres in water-stressed
MENA. It SCREENS a defined set of cooling, water and energy designs on five
objectives under stated assumptions. It is not a predictive engineering model.
All scenario inputs flow through core.context.SiteContext so every tab agrees.
"""

import sys, os, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="AquaNexus", page_icon="💧", layout="wide")

from core.context import (SiteContext, load_library, PRIORITY_PROFILES, DESIGN_EXTREME_DELTA_C, NORMAL, BASELINE_KEY)
from models.live_data import fetch_live_climate
from scenarios.stress_tests import SCENARIOS
from analysis.robustness import one_at_a_time, monte_carlo, dimension_shares, headline_ranges
from analysis.scaling import scale_up, PIPELINE_MW
from analysis.policy import evaluate_policy, wue_sweep, site_wue
from analysis.selfcheck import run_selfchecks
from analysis.benchmarks import run_benchmarks
from analysis.briefing import build_brief_html
from recommendation import explain
from ui.style import (inject, section, kpi, fmt, pct, esc, show_df, show_chart, style_fig, TEAL, AMBER, SLATE, RED, GREY)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_COMBOS = 60
AMB_BASE, AMB_LIVE, AMB_DESIGN = "Baseline ambient", "Live conditions now", f"Design-day extreme (+{DESIGN_EXTREME_DELTA_C:.0f}°C)"
inject()


@st.cache_resource
def get_lib():
    return load_library(BASE_DIR)


@st.cache_data(ttl=300, show_spinner=False)
def live_climate(capital_key):
    return fetch_live_climate(capital_key)


@st.cache_data(show_spinner=False)
def cached_checks(location, mw, util, db, rh):
    return run_selfchecks(SiteContext(get_lib(), location, mw, util, db, rh))


@st.cache_data(show_spinner=False)
def cached_ranges(location, mw, util, db, rh, scenario, key, spread):
    return headline_ranges(SiteContext(get_lib(), location, mw, util, db, rh), key, scenario, n=150, spread=spread)


lib = get_lib()


def load_demo():
    st.session_state.update({"loc": "UAE", "mw": 50, "util": 80, "amb": AMB_BASE, "scn": "Extreme heatwave (+5C)", "prio": "Balanced"})


# =============================== SIDEBAR ===============================
sb = st.sidebar
sb.markdown("## 💧 AquaNexus")
sb.button("▶ Load judge demo", on_click=load_demo, help="UAE, 50 MW, extreme heatwave, balanced priorities")
sb.caption("One click to the showcase case: a 50 MW AI data centre in the UAE during an extreme heatwave.")
sb.markdown("**Site**")
location = sb.selectbox("Country (capital city as representative site)", list(lib.countries), key="loc", format_func=lambda k: k.replace("_", " "))
profile = lib.countries[location]
amb = sb.radio("Ambient conditions", [AMB_BASE, AMB_LIVE, AMB_DESIGN], key="amb",
               help="Baseline ambient is a representative estimate, not a 30-year climate normal. Heatwave scenarios add on top of the basis you choose.")
db, rh = profile["ambient_temperature_normal_c"], profile["relative_humidity_normal_pct"]
ambient_note = f"{db}°C, {rh}% RH baseline ambient"
if amb == AMB_LIVE:
    lv = live_climate(profile["capital_key"])
    if lv is not None:
        db, rh, ambient_note = lv.temperature_c, lv.relative_humidity_pct, f"live in {lv.city}: {lv.temperature_c:.0f}°C, {lv.relative_humidity_pct:.0f}% RH"
    else:
        sb.warning("Live weather is unavailable here; using baseline ambient.")
elif amb == AMB_DESIGN:
    db += DESIGN_EXTREME_DELTA_C
    ambient_note = f"design-day extreme {db:.0f}°C, {rh}% RH"

sb.markdown("**Facility**")
mw = sb.slider("AI IT capacity (MW)", 1, 100, 50, key="mw")
util = sb.slider("Workload utilization (%)", 10, 100, 80, key="util")
sb.markdown("**Situation**")
scenario = sb.selectbox("Stress scenario", list(SCENARIOS), key="scn")
prio = sb.selectbox("What matters most?", list(PRIORITY_PROFILES) + ["Custom"], key="prio")
if prio == "Custom":
    cw = {k: sb.slider(k.capitalize(), 0.0, 1.0, v, 0.05, key=f"w_{k}") for k, v in PRIORITY_PROFILES["Balanced"].items()}
    tot = sum(cw.values()) or 1.0
    weights = {k: v / tot for k, v in cw.items()}
else:
    weights = PRIORITY_PROFILES[prio]
with sb.expander("Hard limits (optional)"):
    f_cost = st.slider("Max cost (% of conventional)", 50, 300, 300, 5)
    f_water = st.slider("Max water (% of conventional)", 5, 200, 200, 5)
    f_carbon = st.slider("Max carbon (% of conventional)", 10, 150, 150, 5)
    f_weri = st.slider("Min resilience score", 0, 100, 0, 5)
    st.caption("A slider at its maximum is switched off.")

ctx = SiteContext(lib, location, mw, util, db, rh)
ref = ctx.baseline_for(scenario)
constraints = {}
if f_cost < 300: constraints["max_cost_usd_per_day"] = ref.total_cost_usd_per_day * f_cost / 100
if f_water < 200: constraints["max_water_m3_per_day"] = ref.total_water_m3_per_day * f_water / 100
if f_carbon < 150: constraints["max_carbon_t_per_day"] = ref.carbon_t_co2e_per_day * f_carbon / 100
if f_weri > 0: constraints["min_weri"] = f_weri

scr = ctx.screen(scenario, weights, constraints or None)
checks = cached_checks(location, mw, util, db, rh)
n_ok = sum(1 for _, ok, _ in checks if ok)

# =============================== HERO ===============================
st.markdown(f"""
<div class="hero">
  <div class="eyebrow">Energy–water nexus and climate resilience · MENA</div>
  <h1>AquaNexus</h1>
  <p>Which cooling, water and energy design lets an AI data centre keep running in a water-stressed, hot region, and what does it cost? Pick a site and get a quantified answer.</p>
  <span class="chip">{esc(location.replace('_', ' '))} · capital-city site</span>
  <span class="chip">{esc(ambient_note)}</span>
  <span class="chip">{mw} MW · {util}% utilization</span>
  <span class="chip ok">Model checks {n_ok}/{len(checks)} passing</span>
  <span class="chip warn">Screening model, not a design tool</span>
</div>""", unsafe_allow_html=True)

tab_imp, tab_exp, tab_scr, tab_pol, tab_rob, tab_meth = st.tabs(["📊 Impact", "🔬 Explorer", "🎯 Screening", "🏛️ Policy Lab", "🛡️ Robustness", "📚 Method & validation"])

best = scr.best
base = scr.baseline


# ------------------------------- IMPACT -------------------------------
with tab_imp:
    stat_water = profile["water_stress_score_0_100"]
    st.markdown(f"""
<div class="statstrip">
 <div class="stat"><div class="n">38 + 23</div><div class="t">UAE data centres operating + in the pipeline</div><div class="s">Arizton, 2026</div></div>
 <div class="stat"><div class="n">537 → 711 MW</div><div class="t">UAE data-centre capacity, 2025 to 2031</div><div class="s">Mordor Intelligence, 2026</div></div>
 <div class="stat"><div class="n">560 → 1,200 B L</div><div class="t">Global data-centre water use, 2023 to 2030</div><div class="s">IEA, via GPUSmith 2026</div></div>
 <div class="stat"><div class="n">{stat_water:.0f} / 100</div><div class="t">{esc(location.replace('_',' '))} projected water stress, 2040</div><div class="s">WRI Aqueduct 4.0 (rescaled from 0–5)</div></div>
</div>""", unsafe_allow_html=True)

    if best is None:
        st.error("No configuration satisfies the scenario's physical limits and your hard limits. Relax a limit in the sidebar or choose a milder scenario.")
    else:
        rec = explain(best, base, scenario, scr.dry_bulb_c)
        r, d, key = best.result, None, scr.best_key
        rng = cached_ranges(location, mw, util, db, rh, scenario, key, 0.30)
        st.markdown(f"""
<div class="answer"><div class="lab">Best-performing design under stated assumptions</div>
<div class="big">{esc(ctx.short_label(key))}</div>
<div class="sub">For a {mw} MW AI data centre in {esc(location.replace('_',' '))} under <b>{esc(scenario)}</b>: water {pct(rec.deltas['water'])}, energy {pct(rec.deltas['energy'])}, carbon {pct(rec.deltas['carbon'])}, cost {pct(rec.deltas['cost'])} against a conventional air-cooled, cooling-tower, desalinated-water, grid-only design.</div></div>""", unsafe_allow_html=True)

        def tone(delta, lower_better=True):
            if abs(delta) < 0.5: return "flat"
            return "good" if (delta < 0) == lower_better else "bad"

        def rtxt(k):
            lo, md, hi = rng[k]
            return f"±30% input uncertainty: {pct(lo)} to {pct(hi)}"
        kp = [
            kpi("Water use", pct(rec.deltas["water"]), tone(rec.deltas["water"]), f"{fmt(r.total_water_m3_per_day)} vs {fmt(base.total_water_m3_per_day)} m³/day", rtxt("water")),
            kpi("Total energy", pct(rec.deltas["energy"]), tone(rec.deltas["energy"]), f"{fmt(r.total_energy_mwh_per_day)} vs {fmt(base.total_energy_mwh_per_day)} MWh/day", rtxt("energy")),
            kpi("Carbon", pct(rec.deltas["carbon"]), tone(rec.deltas["carbon"]), f"{fmt(r.carbon_t_co2e_per_day)} vs {fmt(base.carbon_t_co2e_per_day)} tCO₂e/day", rtxt("carbon")),
            kpi("All-in cost", pct(rec.deltas["cost"]), tone(rec.deltas["cost"]), f"${fmt(r.total_cost_usd_per_day)} vs ${fmt(base.total_cost_usd_per_day)} per day", rtxt("cost")),
            kpi("Resilience score", f"{rec.deltas['weri']:+.0f} pts".replace("-", "−"), tone(-rec.deltas["weri"]), f"{base.weri_score:.0f} → {r.weri_score:.0f} out of 100", "Project-level index, see Method tab"),
        ]
        st.markdown('<div class="kpis">' + "".join(kp) + "</div>", unsafe_allow_html=True)

        c1, c2 = st.columns([1.15, 1])
        with c1:
            section("The recommended design", "Four choices, each one tested against alternatives.")
            c_, rj_, w_, e_ = key
            st.markdown(f"""<div class="design">
<div><b>Chip-side cooling</b><span>{esc(lib.chips[c_].label)}</span></div>
<div><b>Heat rejection</b><span>{esc(lib.rejs[rj_].label.split(' (')[0])}</span></div>
<div><b>Water source</b><span>{esc(lib.water[w_]['label'].split(' (')[0])}</span></div>
<div><b>Energy supply</b><span>{esc(lib.energy[e_]['label'])}</span></div></div>""", unsafe_allow_html=True)
            st.markdown("**Trade-offs to be aware of**")
            for t in rec.tradeoffs:
                st.markdown(f"- {t}")
        with c2:
            section("Against the conventional design", "Conventional = 100")
            labels = ["Water", "Energy", "Carbon", "Cost"]
            idx = [r.total_water_m3_per_day / base.total_water_m3_per_day * 100, r.total_energy_mwh_per_day / base.total_energy_mwh_per_day * 100,
                   r.carbon_t_co2e_per_day / base.carbon_t_co2e_per_day * 100, r.total_cost_usd_per_day / base.total_cost_usd_per_day * 100]
            fg = go.Figure()
            fg.add_trace(go.Bar(y=labels, x=[100] * 4, orientation="h", name="Conventional", marker_color=GREY))
            fg.add_trace(go.Bar(y=labels, x=idx, orientation="h", name="Recommended", marker_color=TEAL, text=[f"{v:.0f}" for v in idx], textposition="outside"))
            fg.update_layout(barmode="group", xaxis=dict(range=[0, max(idx + [100]) * 1.2], title="Index (lower is better)"), yaxis=dict(autorange="reversed"))
            show_chart(style_fig(fg, 320))

        # ---- stress test ----
        section("Does it hold up when conditions get worse?", "The recommended design is fixed and tested in all nine stress scenarios, against the conventional design under the same limits.")
        rows = ctx.stress_test(key)

        def status(x):
            if x.water_supply_exceeded: return "Breaches water limit"
            if x.grid_import_exceeded: return "Breaches grid limit"
            return "Within limits"
        sdf = pd.DataFrame([{"Scenario": s["scenario"],
                             "Conventional (m³/day)": fmt(s["baseline"].total_water_m3_per_day), "Conventional status": status(s["baseline"]),
                             "Recommended (m³/day)": fmt(s["design"].total_water_m3_per_day), "Recommended status": status(s["design"]),
                             "Cost vs conv.": pct((s["design"].total_cost_usd_per_day / s["baseline"].total_cost_usd_per_day - 1) * 100)} for s in rows])
        n_b = sum(1 for s in rows if s["baseline"].water_supply_exceeded or s["baseline"].grid_import_exceeded)
        n_d = sum(1 for s in rows if s["design"].water_supply_exceeded or s["design"].grid_import_exceeded)
        sc1, sc2 = st.columns([1.25, 1])
        with sc1:
            fs = go.Figure()
            fs.add_trace(go.Bar(x=[s["scenario"] for s in rows], y=[s["baseline"].total_water_m3_per_day for s in rows], name="Conventional", marker_color=GREY))
            fs.add_trace(go.Bar(x=[s["scenario"] for s in rows], y=[s["design"].total_water_m3_per_day for s in rows], name="Recommended", marker_color=TEAL))
            fs.update_layout(barmode="group", yaxis_title="Water use (m³/day)", xaxis=dict(tickangle=-30))
            fs = style_fig(fs, 420); fs.update_layout(legend=dict(orientation="h", y=1.08), margin=dict(t=40, b=10, l=10, r=10))
            show_chart(fs)
        with sc2:
            st.markdown(f'<div class="card"><div class="tag">STRESS RESULT</div><h4>Conventional: {9 - n_b} of 9 within limits<br>Recommended: {9 - n_d} of 9 within limits</h4>'
                        f'<p>Water-availability scenarios cap total water at a share of what the conventional design uses today. A design that already uses much less water simply is not exposed to that cap.</p>'
                        f'<p>{"The recommended design is chosen for the scenario selected in the sidebar. A design tuned for one scenario can be weaker in another, and the table shows where." if n_d else "No scenario pushes the recommended design past a limit."}</p></div>', unsafe_allow_html=True)
        show_df(sdf)

        # ---- scale-up ----
        section("What it is worth at national scale", "The same model re-run at the capacity expected to be built, compared with building it conventionally. Illustrative, not a forecast.")
        default_mw, mw_src = PIPELINE_MW[location]
        pipe = st.slider("New AI data-centre capacity to cover (MW)", 10, 600, default_mw, 10, key=f"pipe_{location}")
        st.caption(f"Default for {location.replace('_', ' ')}: {mw_src}.")
        su = scale_up(ctx, key, pipe, scenario)
        pb = "no payback on operating savings alone" if su.payback_years is None else (f"{su.payback_years:.1f} years" if su.payback_years > 0 else "no extra capex")
        cards = [
            kpi("Water saved per year", f"{su.water_saved_m3_per_year/1e6:,.1f} M m³", "good" if su.water_saved_m3_per_year > 0 else "bad", f"Daily domestic water for about {fmt(su.people_equivalent, 2):s} people", f"at {100:.0f} L per person per day"),
            kpi("Energy saved per year", f"{su.energy_saved_gwh_per_year:,.0f} GWh", "good" if su.energy_saved_gwh_per_year > 0 else "bad", "total facility energy"),
            kpi("Carbon avoided per year", f"{su.carbon_saved_t_per_year/1000:,.0f} kt", "good" if su.carbon_saved_t_per_year > 0 else "bad", "tCO₂e from grid electricity"),
            kpi("All-in cost per year", f"${abs(su.cost_saved_usd_per_year)/1e6:,.1f} M {'saved' if su.cost_saved_usd_per_year >= 0 else 'extra'}", "good" if su.cost_saved_usd_per_year >= 0 else "bad", "incl. annualized capex"),
            kpi("Extra up-front capex", f"${su.incremental_capex_usd/1e6:,.0f} M", "flat", f"Simple payback: {pb}", "Solar is bought at LCOE, so no PV capex"),
        ]
        st.markdown('<div class="kpis">' + "".join(cards) + "</div>", unsafe_allow_html=True)

        # ---- alignment ----
        section("Where this meets the UN Water agenda", "Theme: Energy–Water Nexus and Climate Resilience.")
        a = st.columns(4)
        al = [("SDG 6 · Target 6.4", "Water-use efficiency", f"Cuts data-centre freshwater demand {pct(rec.deltas['water'], False).lstrip('-').replace(chr(8722), '')} and shifts supply to reclaimed water."),
              ("SDG 7 · Targets 7.2, 7.3", "Clean, efficient energy", f"Raises the solar share to {r.renewable_penetration_pct:.0f}% of the day's load and lowers total energy."),
              ("SDG 9 · Target 9.4", "Resource-efficient infrastructure", "Treats cooling, water and power as one system when siting and sizing digital infrastructure."),
              ("SDG 13 · Target 13.1", "Climate resilience", "Stress-tests heatwaves, water scarcity, grid limits and low solar, and scores resilience explicitly.")]
        for col, (tag, ttl, txt) in zip(a, al):
            col.markdown(f'<div class="card"><div class="tag">{tag}</div><h4>{ttl}</h4><p>{txt}</p></div>', unsafe_allow_html=True)

        section("Who uses it")
        u = st.columns(3)
        us = [("Data-centre operators", "Screen all 81 designs for a site, see the Pareto trade-offs, test priorities and hard limits.", "Screening, Explorer"),
              ("Regulators and utilities", "Test a water or efficiency rule before writing it: what it costs and which designs comply.", "Policy Lab"),
              ("Investors and developers", "See how the choice behaves under uncertainty, and what the capex buys at scale.", "Robustness, scale-up above")]
        for col, (ttl, txt, tabs) in zip(u, us):
            col.markdown(f'<div class="card"><h4>{ttl}</h4><p>{txt}</p><p><b>Tabs:</b> {tabs}</p></div>', unsafe_allow_html=True)

        # ---- brief ----
        stress_brief = [{"scenario": s["scenario"], "base": f"{fmt(s['baseline'].total_water_m3_per_day)} ({status(s['baseline'])})", "design": f"{fmt(s['design'].total_water_m3_per_day)} ({status(s['design'])})"} for s in rows]
        kpis_brief = [{"label": "Water", "value": pct(rec.deltas["water"]), "abs": f"{fmt(r.total_water_m3_per_day)} vs {fmt(base.total_water_m3_per_day)} m³/day"},
                      {"label": "Energy", "value": pct(rec.deltas["energy"]), "abs": f"{fmt(r.total_energy_mwh_per_day)} vs {fmt(base.total_energy_mwh_per_day)} MWh/day"},
                      {"label": "Carbon", "value": pct(rec.deltas["carbon"]), "abs": f"{fmt(r.carbon_t_co2e_per_day)} vs {fmt(base.carbon_t_co2e_per_day)} t/day"},
                      {"label": "Cost", "value": pct(rec.deltas["cost"]), "abs": f"${fmt(r.total_cost_usd_per_day)} vs ${fmt(base.total_cost_usd_per_day)} per day"},
                      {"label": "Resilience", "value": f"{rec.deltas['weri']:+.0f} pts", "abs": f"{base.weri_score:.0f} to {r.weri_score:.0f} of 100"}]
        brief = build_brief_html({
            "site": location.replace("_", " "), "facility": f"{mw} MW at {util}% utilization", "scenario": scenario,
            "headline": rec.headline, "design": ctx.design_label(key), "kpis": kpis_brief, "tradeoffs": rec.tradeoffs, "stress": stress_brief,
            "range_note": "Ranges under ±30% uncertainty on estimated inputs: " + "; ".join(f"{k} {pct(v[0])} to {pct(v[2])}" for k, v in rng.items()) + ".",
            "scale": {"mw": pipe, "text": f"Covering {pipe} MW of new capacity with this design instead of the conventional one would save about {su.water_saved_m3_per_year/1e6:,.1f} million m3 of water, {su.energy_saved_gwh_per_year:,.0f} GWh of energy and {su.carbon_saved_t_per_year/1000:,.0f} kt of CO2 per year, for about ${su.incremental_capex_usd/1e6:,.0f} million of extra up-front capex."}})
        st.download_button("⬇ Download one-page decision brief (HTML, printable to PDF)", brief, file_name=f"aquanexus_brief_{location}.html", mime="text/html")


# ------------------------------- EXPLORER -------------------------------
with tab_exp:
    section("Explorer", "Pick designs yourself and compare them with the conventional one.")
    dflt = scr.best_key or BASELINE_KEY
    ec = st.columns(4)
    chip_keys = ec[0].multiselect("Chip-side cooling", list(lib.chips), default=[dflt[0]], format_func=lambda k: lib.chips[k].label.split(" (")[0])
    rej_keys = ec[1].multiselect("Heat rejection", list(lib.rejs), default=[dflt[1]], format_func=lambda k: lib.rejs[k].label.split(" (")[0])
    water_keys = ec[2].multiselect("Water source", list(lib.water), default=[dflt[2]], format_func=lambda k: lib.water[k]["label"].split(" (")[0])
    energy_keys = ec[3].multiselect("Energy supply", list(lib.energy), default=[dflt[3]], format_func=lambda k: lib.energy[k]["label"])
    scn_keys = st.multiselect("Scenarios", list(SCENARIOS), default=[scenario])
    if not (chip_keys and rej_keys and water_keys and energy_keys and scn_keys):
        st.warning("Select at least one option in every group.")
    elif len(chip_keys) * len(rej_keys) * len(water_keys) * len(energy_keys) * len(scn_keys) > MAX_COMBOS:
        st.error(f"More than {MAX_COMBOS} combinations selected. Narrow the selection.")
    else:
        combos = list(itertools.product(chip_keys, rej_keys, water_keys, energy_keys, scn_keys))
        res = [(c, ctx.simulate_design(c[:4], c[4], True), ctx.baseline_for(c[4])) for c in combos]
        k0, r0, b0 = res[0]
        st.markdown(f"**Showing the first of {len(res)} combination(s):** {esc(ctx.short_label(k0[:4]))} · {esc(k0[4])}")
        if r0.water_supply_exceeded: st.error(f"Exceeds available water by {fmt(r0.water_supply_shortfall_m3_per_day)} m³/day in this scenario.")
        if r0.grid_import_exceeded: st.error(f"Exceeds the grid-import limit by {fmt(r0.unmet_grid_demand_mwh_per_day)} MWh/day in this scenario.")
        if r0.reclaimed_fallback_m3_per_day > 0: st.info(f"Reclaimed supply is capped; {fmt(r0.reclaimed_fallback_m3_per_day)} m³/day falls back to desalination.")
        dl = lambda a, b: (a / b - 1) * 100 if b else 0
        kk = [kpi("Water", fmt(r0.total_water_m3_per_day), "flat", f"m³/day · {pct(dl(r0.total_water_m3_per_day, b0.total_water_m3_per_day))} vs conv."),
              kpi("Energy", fmt(r0.total_energy_mwh_per_day), "flat", f"MWh/day · {pct(dl(r0.total_energy_mwh_per_day, b0.total_energy_mwh_per_day))}"),
              kpi("Cost", f"${fmt(r0.total_cost_usd_per_day)}", "flat", f"per day · {pct(dl(r0.total_cost_usd_per_day, b0.total_cost_usd_per_day))}"),
              kpi("Carbon", fmt(r0.carbon_t_co2e_per_day), "flat", f"tCO₂e/day · {pct(dl(r0.carbon_t_co2e_per_day, b0.carbon_t_co2e_per_day))}"),
              kpi("Resilience", f"{r0.weri_score:.0f}", "flat", f"of 100 · conv. {b0.weri_score:.0f}")]
        st.markdown('<div class="kpis">' + "".join(kk) + "</div>", unsafe_allow_html=True)
        q = st.columns(4)
        q[0].metric("Effective PUE", fmt(r0.effective_pue)); q[1].metric("Renewable share", f"{r0.renewable_penetration_pct:.0f}%")
        q[2].metric("Peak grid import (MW)", fmt(r0.peak_grid_import_mw)); q[3].metric("Heat vulnerability", f"{r0.heat_vulnerability_score:.0f}/100")
        hrs = list(range(24))
        other = [max(l - g, 0) for l, g in zip(r0.hourly_load_mw, r0.hourly_grid_mw)]
        fh = go.Figure()
        fh.add_trace(go.Bar(x=hrs, y=r0.hourly_grid_mw, name="Grid import", marker_color=SLATE))
        fh.add_trace(go.Bar(x=hrs, y=other, name="Solar + battery to load", marker_color=AMBER))
        fh.add_trace(go.Scatter(x=hrs, y=r0.hourly_solar_mw, name="Solar generation", mode="lines", line=dict(color=TEAL, width=3)))
        fh.update_layout(barmode="stack", xaxis_title="Hour of day", yaxis_title="MW", title="A 24-hour day: how the load is served")
        show_chart(style_fig(fh, 340))
        rows = [{"Configuration": "Conventional baseline", "Scenario": NORMAL, "Feasible": "Yes", "Water (m³/day)": fmt(ctx.baseline_for(NORMAL).total_water_m3_per_day),
                 "Energy (MWh/day)": fmt(ctx.baseline_for(NORMAL).total_energy_mwh_per_day), "Cost ($/day)": fmt(ctx.baseline_for(NORMAL).total_cost_usd_per_day),
                 "Carbon (t/day)": fmt(ctx.baseline_for(NORMAL).carbon_t_co2e_per_day), "Resilience": fmt(ctx.baseline_for(NORMAL).weri_score, 2)}]
        for k, r_, b_ in res:
            rows.append({"Configuration": ctx.short_label(k[:4]), "Scenario": k[4], "Feasible": "No" if (r_.water_supply_exceeded or r_.grid_import_exceeded) else "Yes",
                         "Water (m³/day)": fmt(r_.total_water_m3_per_day), "Energy (MWh/day)": fmt(r_.total_energy_mwh_per_day), "Cost ($/day)": fmt(r_.total_cost_usd_per_day),
                         "Carbon (t/day)": fmt(r_.carbon_t_co2e_per_day), "Resilience": fmt(r_.weri_score, 2)})
        df = pd.DataFrame(rows)
        show_df(df)
        st.download_button("Export comparison (CSV)", df.to_csv(index=False), file_name=f"aquanexus_{location}_comparison.csv", mime="text/csv")
        if len(res) > 1:
            fc = go.Figure(go.Bar(x=[f"#{i+1}" for i in range(len(res))], y=[dl(r_.total_water_m3_per_day, b_.total_water_m3_per_day) for _, r_, b_ in res],
                                  marker_color=[GREY if (r_.water_supply_exceeded or r_.grid_import_exceeded) else TEAL for _, r_, _b in res]))
            fc.update_layout(yaxis_title="Water, % change vs conventional", xaxis_title="Combination (table order). Grey = infeasible")
            show_chart(style_fig(fc, 320))


# ------------------------------- SCREENING -------------------------------
with tab_scr:
    section("Screening: all 81 designs", f"3 chip-side × 3 heat rejection × 3 water × 3 energy, ranked for '{scenario}' with the “{prio}” priorities and your hard limits (sidebar).")
    if best is None:
        st.error("No eligible configuration. Relax the hard limits or choose a milder scenario.")
    else:
        rec = explain(best, base, scenario, scr.dry_bulb_c)
        st.markdown(f'<div class="answer"><div class="lab">Best under your priorities</div><div class="big">{esc(ctx.short_label(scr.best_key))}</div><div class="sub">{esc(rec.reasoning)}</div></div>', unsafe_allow_html=True)
        pw = ", ".join(f"{k} {v:.0%}" for k, v in weights.items())
        st.caption(f"Priority weights: {pw}.")
    n_bad = sum(1 for c in scr.candidates if c.infeasible)
    st.caption(f"{len(scr.candidates) - n_bad} of {len(scr.candidates)} designs are eligible (the rest breach a scenario constraint or a hard limit). {len(scr.frontier)} are Pareto-optimal: none beats them on all five objectives at once.")
    if scr.frontier:
        fdf = pd.DataFrame([{"Chip-side": lib.chips[c.chip_key].label.split(" (")[0], "Heat rejection": lib.rejs[c.rejection_key].label.split(" (")[0],
                             "Water source": lib.water[c.water_key]["label"].split(" (")[0], "Energy": lib.energy[c.energy_key]["label"],
                             "Water (m³/day)": fmt(c.result.total_water_m3_per_day), "Energy (MWh/day)": fmt(c.result.total_energy_mwh_per_day),
                             "Cost ($/day)": fmt(c.result.total_cost_usd_per_day), "Carbon (t/day)": fmt(c.result.carbon_t_co2e_per_day), "Resilience": fmt(c.result.weri_score, 2)}
                            for c in scr.frontier])
        show_df(fdf)
        st.download_button("Export Pareto set (CSV)", fdf.to_csv(index=False), file_name=f"aquanexus_{location}_pareto.csv", mime="text/csv")
        ok_c = scr.eligible
        pc = st.columns(2)
        for col, (xk, yk, xl, yl) in zip(pc, [("total_water_m3_per_day", "total_energy_mwh_per_day", "Water (m³/day)", "Energy (MWh/day)"),
                                              ("total_cost_usd_per_day", "carbon_t_co2e_per_day", "Cost ($/day)", "Carbon (tCO₂e/day)")]):
            g = go.Figure()
            g.add_trace(go.Scatter(x=[getattr(c.result, xk) for c in ok_c], y=[getattr(c.result, yk) for c in ok_c], mode="markers", name="Eligible", marker=dict(color=GREY, size=8)))
            g.add_trace(go.Scatter(x=[getattr(c.result, xk) for c in scr.frontier], y=[getattr(c.result, yk) for c in scr.frontier], mode="markers", name="Pareto-optimal", marker=dict(color=TEAL, size=11, symbol="diamond")))
            if best is not None:
                g.add_trace(go.Scatter(x=[getattr(best.result, xk)], y=[getattr(best.result, yk)], mode="markers", name="Best", marker=dict(color=AMBER, size=17, symbol="star")))
            g.update_layout(xaxis_title=xl, yaxis_title=yl)
            show_chart(style_fig(g, 360), col)


# ------------------------------- POLICY LAB -------------------------------
with tab_pol:
    section("Policy Lab", "Set a rule and see what it costs, which designs meet it, and what changes for water and carbon.")
    pcol = st.columns(4)
    use_wue = pcol[0].checkbox("Cap site water use (WUE)", value=True)
    wue_cap = pcol[0].slider("Max L per kWh of IT energy", 0.05, 2.5, 0.5, 0.05, disabled=not use_wue)
    use_pue = pcol[1].checkbox("Cap PUE", value=False)
    pue_cap = pcol[1].slider("Max PUE", 1.05, 1.6, 1.3, 0.01, disabled=not use_pue)
    use_np = pcol[2].checkbox("Require non-potable water", value=False)
    np_min = pcol[2].slider("Min non-potable share (%)", 0, 100, 50, 5, disabled=not use_np)
    use_re = pcol[3].checkbox("Require renewable share", value=False)
    re_min = pcol[3].slider("Min renewable share of load (%)", 0, 80, 20, 5, disabled=not use_re)
    rules = {}
    if use_wue: rules["wue_cap"] = wue_cap
    if use_pue: rules["pue_cap"] = pue_cap
    if use_np: rules["min_nonpotable_pct"] = float(np_min)
    if use_re: rules["min_renewable_pct"] = float(re_min)
    out = evaluate_policy(ctx, scenario, **rules)
    if not rules:
        st.info("Switch on at least one rule.")
    elif out.n_eligible == 0:
        st.error("No design is physically eligible in this scenario.")
    elif out.compliant is None:
        st.error(f"No design meets this rule set in '{scenario}'. The rule is too strict for the modeled options; relax one limit.")
    else:
        u, p = out.unregulated, out.compliant
        prem = out.cost_premium_pct
        verdict = ("The cheapest design already complies, so the rule costs nothing." if out.unregulated_complies else
                   f"The rule changes the cheapest choice and adds {abs(prem):.1f}% to the all-in daily cost." if prem >= 0 else f"The compliant design is {abs(prem):.1f}% cheaper.")
        st.markdown(f'<div class="answer"><div class="lab">Cost of compliance</div><div class="big">{esc(verdict)}</div>'
                    f'<div class="sub">{out.n_compliant} of {out.n_eligible} eligible designs comply. Least-cost compliant design: <b>{esc(ctx.short_label(out.compliant_key))}</b>.</div></div>', unsafe_allow_html=True)
        pk = [kpi("Cost premium", pct(prem), "bad" if prem > 0.5 else "flat", f"${fmt(p.total_cost_usd_per_day)} vs ${fmt(u.total_cost_usd_per_day)} per day"),
              kpi("Site WUE", f"{site_wue(p):.2f}", "flat", f"L/kWh · unregulated {site_wue(u):.2f}"),
              kpi("Water", pct(out.water_change_pct), "good" if out.water_change_pct < -0.5 else "flat", f"{fmt(p.total_water_m3_per_day)} vs {fmt(u.total_water_m3_per_day)} m³/day"),
              kpi("Carbon", pct(out.carbon_change_pct), "good" if out.carbon_change_pct < -0.5 else "flat", f"{fmt(p.carbon_t_co2e_per_day)} vs {fmt(u.carbon_t_co2e_per_day)} t/day"),
              kpi("PUE", f"{p.effective_pue:.2f}", "flat", f"unregulated {u.effective_pue:.2f}")]
        st.markdown('<div class="kpis">' + "".join(pk) + "</div>", unsafe_allow_html=True)
        st.caption(f"Unregulated least-cost design: {ctx.short_label(out.unregulated_key)}.")

    section("How the cost of a water-use cap grows as it tightens", "Cheapest compliant design for each site-WUE cap, other rules off.")
    sw = [r for r in wue_sweep(ctx, scenario, caps=(2.0, 1.0, 0.5, 0.3, 0.1, 0.05)) if r["premium_pct"] is not None]
    if sw:
        fsw = go.Figure(go.Bar(x=[f"≤ {r['cap']:g} L/kWh" for r in sw], y=[r["premium_pct"] for r in sw], marker_color=TEAL,
                               text=[f"{r['premium_pct']:+.1f}%" for r in sw], textposition="outside"))
        fsw.update_layout(yaxis_title="Cost premium vs least-cost design (%)", xaxis_title="Site WUE cap")
        show_chart(style_fig(fsw, 330))
        st.caption("For reference, evaporative cooling towers typically run near 2 L/kWh, so a cap of about 2 binds on the conventional design while looser values do not. Costs are all-in (operating plus annualized capex) from this screening model.")


# ------------------------------- ROBUSTNESS -------------------------------
with tab_rob:
    section("How stable is the answer?", "Most inputs are engineering estimates. This moves them and asks whether the recommendation survives.")
    spread = st.slider("Uncertainty band on estimated inputs (±%)", 10, 50, 30, 5) / 100.0
    n_mc = st.select_slider("Monte Carlo draws", [50, 100, 150, 300], value=150)
    if best is None:
        st.error("No eligible configuration to test.")
    elif st.button("▶ Run robustness check", type="primary"):
        with st.spinner("Re-screening under perturbed inputs..."):
            si = ctx.scenario_state(scenario); kw = ctx.common_kwargs(si); wc, gc = ctx.caps_for(si)
            nominal, oat = one_at_a_time(kw, lib.chips, lib.rejs, ctx.water_options(), ctx.energy_options(), weights, constraints or None, wc, gc, spread=spread)
            wins = monte_carlo(kw, lib.chips, lib.rejs, ctx.water_options(), ctx.energy_options(), weights, constraints or None, wc, gc, n=n_mc, spread=spread)
            st.session_state["robust"] = {"nominal": nominal, "oat": oat, "wins": wins, "spread": spread, "scn": scenario, "site": location}
    rb = st.session_state.get("robust")
    if rb and rb["nominal"] is not None:
        if (rb["scn"], rb["site"]) != (scenario, location):
            st.warning(f"This result was computed for {rb['site'].replace('_', ' ')} / {rb['scn']}. Re-run to refresh.")
        unchanged = sum(1 for r in rb["oat"] if not r["changed"])
        nom_share = rb["wins"].get(rb["nominal"], 0) / max(sum(rb["wins"].values()), 1) * 100
        st.markdown(f'<div class="answer"><div class="lab">Nominal best</div><div class="big">{esc(ctx.short_label(rb["nominal"]))}</div></div>', unsafe_allow_html=True)
        s1, s2 = st.columns(2)
        s1.metric("One-at-a-time checks where the best option holds", f"{unchanged} of {len(rb['oat'])}")
        s2.metric(f"Monte Carlo win share (±{rb['spread']*100:.0f}% on all inputs)", f"{nom_share:.0f}%")
        shares = dimension_shares(rb["wins"])
        names = {"chip": "Chip-side cooling", "rejection": "Heat rejection", "water": "Water source", "energy": "Energy supply"}
        looks = {"chip": lambda k: lib.chips[k].label.split(" (")[0], "rejection": lambda k: lib.rejs[k].label.split(" (")[0],
                 "water": lambda k: lib.water[k]["label"].split(" (")[0], "energy": lambda k: lib.energy[k]["label"]}
        decisive = [names[d] for d, v in shares.items() if v and max(v.values()) >= 80]
        neartie = [names[d] for d, v in shares.items() if v and max(v.values()) < 80]
        if nom_share >= 70 and unchanged >= 0.8 * len(rb["oat"]):
            st.success("The exact best-performing configuration is robust to these uncertainties.")
        elif decisive:
            st.warning(f"The exact combination is a near-tie, but some choices are stable: **{', '.join(decisive)}** win in at least 80% of draws"
                       + (f"; **{', '.join(neartie)}** are close calls." if neartie else ".") + " Treat the result as a short list of similar designs.")
        else:
            st.error("No single design choice is stable under these uncertainties. Treat the ranking as indicative only.")
        st.markdown("**Stability of each design choice** (share of Monte Carlo draws where the option is in the winning design)")
        for col, dim in zip(st.columns(4), ("chip", "rejection", "water", "energy")):
            with col:
                st.caption(names[dim])
                for choice, p_ in shares[dim].items():
                    st.progress(min(int(round(p_)), 100), text=f"{looks[dim](choice)}: {p_:.0f}%")
        top = rb["wins"].most_common(6)
        tl = [f"{ctx.short_label(k)}" + "\u200b" * i for i, (k, _) in enumerate(top)]
        fw = go.Figure(go.Bar(x=[w / max(sum(rb['wins'].values()), 1) * 100 for _, w in top][::-1], y=tl[::-1], orientation="h",
                              marker_color=[TEAL if k == rb["nominal"] else GREY for k, _ in top][::-1]))
        fw.update_layout(xaxis_title="Share of Monte Carlo draws in which it wins (%)")
        fw = style_fig(fw, 380); fw.update_layout(margin=dict(l=10, r=10, t=10, b=10)); fw.update_yaxes(automargin=True)
        show_chart(fw)
        with st.expander("One-at-a-time results"):
            show_df(pd.DataFrame([{"Input varied": r["parameter"], "Change": r["change"], "Best configuration then": ctx.short_label(r["best"]) if r["best"] else "none eligible",
                                   "Same as nominal?": "Yes" if not r["changed"] else "No"} for r in rb["oat"]]))
    elif best is not None:
        st.info("Press **Run robustness check** to test the ranking.")
    if best is not None:
        section("Uncertainty on the headline numbers", "Range of the recommended design's change vs conventional when estimated inputs move ±30% together.")
        rr = cached_ranges(location, mw, util, db, rh, scenario, scr.best_key, 0.30)
        show_df(pd.DataFrame([{"Metric": k.capitalize(), "Low (5th pct)": pct(v[0]), "Median": pct(v[1]), "High (95th pct)": pct(v[2])} for k, v in rr.items()]))
        st.caption("Water savings are structural (they come from the choice of reclaimed water and low-evaporation heat rejection), so they barely move. Cost savings depend on estimated prices and capex, and can shrink to near zero.")


# ------------------------------- METHOD & VALIDATION -------------------------------
with tab_meth:
    section("What this is, and is not")
    st.markdown("""
- **Is:** a transparent screening model that ranks a defined set of cooling, water and energy configurations on five objectives under stated assumptions.
- **Is not:** a predictive engineering model, a sizing tool, or a validated forecast. Equipment physics are reduced to a few coefficients.
- **Resilience score:** a project-level preference score with judgment-based weights, not an established index. The Robustness tab tests whether its weights change the answer.
- **Representative sites:** each country is its capital city. Results are site scenarios, not national averages.""")
    section("Live model checks", f"{n_ok} of {len(checks)} pass for the current site and settings. They test conservation and monotonicity, and that every tab agrees.")
    show_df(pd.DataFrame([{"Check": n, "Result": "✅ Pass" if ok else "❌ Fail", "Detail": dtl} for n, ok, dtl in checks]))
    section("Plausibility against published figures", "A range check, not validation against a real facility. Operator meter data would be needed for that.")
    st.table(pd.DataFrame(run_benchmarks(ctx)).set_index('Metric'))
    section("Data confidence for this country")
    show_df(pd.DataFrame([
        ["Ambient temperature and humidity (baseline)", profile["ambient_temperature_confidence"], "Single representative estimate, not a 30-year climate normal"],
        ["Electricity price", profile["electricity_price_confidence"], profile.get("electricity_price_source", "")],
        ["Water stress score", profile.get("water_stress_confidence", "n/a"), "WRI Aqueduct 4.0 projected 2040 country ranking"],
        ["Grid carbon intensity", "derived / generic", "Not a utility-published factor for most countries"],
        ["Cooling PUE and WUE coefficients", "estimated", "Literature-typical ranges, not a facility study"],
        ["Capex, solar LCOE, battery cost", "estimated", "Placeholders; see docs/assumptions.md"],
        ["Reclaimed-water supply capacity", "placeholder", "No sourced figure; editable in data/water_profiles.yaml"]], columns=["Input", "Confidence", "Note"]))
    with st.expander("Full source ledger"):
        try:
            show_df(pd.read_csv(os.path.join(BASE_DIR, "data", "sources.csv")))
        except Exception as e:
            st.caption(f"Could not load the source ledger: {e}")
    section("Roadmap")
    rm = st.columns(3)
    for col, (t, x) in zip(rm, [("Next: calibrate", "Fit PUE, WUE and load to operator meter data from one or two pilot sites; replace placeholder capex with quotes."),
                                ("Next: finer climate and grid", "Hourly weather files per city, hourly grid carbon, and more than one site per country."),
                                ("Next: portfolio and policy", "Multi-site portfolios, water-stress-aware siting across MENA, and policy scenarios co-designed with regulators.")]):
        col.markdown(f'<div class="card"><h4>{t}</h4><p>{x}</p></div>', unsafe_allow_html=True)
    st.caption("Documentation: docs/methodology.md · docs/assumptions.md · docs/limitations.md")
