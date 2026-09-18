"""
app.py

AquaNexus dashboard entry point.
Run with: streamlit run app.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from models.cooling import CoolingTechParams
from models.pipeline import SimulationConfig, simulate
from models.live_data import fetch_live_climate
from scenarios.stress_tests import SCENARIOS, ScenarioInputs
from optimization.optimizer import enumerate_candidates, pareto_frontier, weighted_score
from recommendation import explain

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

st.set_page_config(page_title="AquaNexus", layout="wide")


@st.cache_data
def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


country_profiles = load_yaml(os.path.join(BASE_DIR, "data", "country_profiles.yaml"))
cooling_techs_raw = load_yaml(os.path.join(BASE_DIR, "data", "cooling_technologies.yaml"))
water_profiles = load_yaml(os.path.join(BASE_DIR, "data", "water_profiles.yaml"))
energy_profiles = load_yaml(os.path.join(BASE_DIR, "data", "energy_profiles.yaml"))

cooling_techs = {
    key: CoolingTechParams(
        label=v["label"],
        wue_l_per_kwh=v["wue_l_per_kwh"],
        pue_typical=v["pue_typical"],
        ambient_temp_sensitivity=v["ambient_temp_sensitivity"],
    )
    for key, v in cooling_techs_raw.items()
}

st.title("AquaNexus")
st.caption("Water-Energy-Climate Decision Engine for AI Data Centres. Covers all seven MENA countries in this dataset.")

st.sidebar.header("Configuration")

location = st.sidebar.selectbox("Location", options=list(country_profiles.keys()), index=0,
                                 format_func=lambda k: k.replace("_", " "))
profile = country_profiles[location]

with st.spinner(f"Fetching live weather for {location.replace('_', ' ')}..."):
    @st.cache_data(ttl=300, show_spinner=False)
    def get_live_climate_cached(capital_key: str):
        return fetch_live_climate(capital_key)

    live_climate = get_live_climate_cached(profile["capital_key"])

if live_climate is not None:
    ambient_normal = live_climate.temperature_c
    st.sidebar.success(f"Live temperature in {live_climate.city}: {live_climate.temperature_c:.1f}C, "
                        f"humidity {live_climate.relative_humidity_pct:.0f}%")
    climate_source_note = f"Live via Open-Meteo, {live_climate.city}, fetched this session"
else:
    ambient_normal = profile["ambient_temperature_normal_c"]
    st.sidebar.warning(
        f"Live weather unavailable. Using static baseline of {ambient_normal}C for "
        f"{location.replace('_', ' ')} instead."
    )
    climate_source_note = f"Static fallback ({profile['ambient_temperature_confidence']}), live fetch failed or unavailable"

it_capacity_mw = st.sidebar.slider("AI IT capacity (MW)", 1, 100, 50)
utilization_pct = st.sidebar.slider("Workload utilization (%)", 10, 100, 80)
climate_scenario_key = st.sidebar.selectbox("Climate / What-if scenario", options=list(SCENARIOS.keys()))
energy_config_key = st.sidebar.selectbox("Energy configuration", options=list(energy_profiles.keys()),
                                          format_func=lambda k: energy_profiles[k]["label"])
cooling_key = st.sidebar.selectbox("Cooling technology", options=list(cooling_techs.keys()),
                                    format_func=lambda k: cooling_techs[k].label)
water_key = st.sidebar.selectbox("Water source", options=list(water_profiles.keys()),
                                  format_func=lambda k: water_profiles[k]["label"])

with st.sidebar.expander("Data confidence for this country", expanded=False):
    st.caption(f"Climate: {climate_source_note}")
    st.caption(f"Electricity price: {profile['electricity_price_confidence']}")
    ws_conf = profile.get("water_stress_confidence", "unavailable")
    st.caption(f"Water stress score: {ws_conf}")
    if ws_conf == "unavailable":
        st.caption("No country-specific WRI score confirmed; using neutral 50/100 in resilience calc.")

grid_carbon_block = profile["grid_carbon_intensity_g_per_kwh"]
if location == "UAE":
    grid_carbon = grid_carbon_block["abu_dhabi"]
else:
    grid_carbon = grid_carbon_block["national"]

water_stress_score = profile["water_stress_score_0_100"]
if water_stress_score is None:
    water_stress_score = 50.0

sec_block = profile["desalination_sec_kwh_per_m3"]
sec_mid = (sec_block["value_min"] + sec_block["value_max"]) / 2
elec_price = profile["electricity_price_usd_per_kwh"]

base_inputs = ScenarioInputs(
    ambient_temp_c=ambient_normal,
    water_availability_multiplier=1.0,
    electricity_price_multiplier=1.0,
    workload_utilization_pct=utilization_pct,
    grid_constrained=False,
    solar_availability_multiplier=1.0,
)
scenario_inputs = SCENARIOS[climate_scenario_key](base_inputs)

water_source_mix = water_profiles[water_key]
if water_key == "hybrid_supply":
    desal_share = 60.0
else:
    desal_share = 95.0 if water_key == "desalinated" else 10.0

energy_conf = energy_profiles[energy_config_key]
renewable_pct = energy_conf["renewable_penetration_pct"]
if scenario_inputs.solar_availability_multiplier != 1.0:
    renewable_pct = renewable_pct * scenario_inputs.solar_availability_multiplier
if scenario_inputs.grid_constrained:
    st.sidebar.info("Grid constraint scenario active: grid energy availability is flagged as limited.")

effective_elec_price = elec_price * scenario_inputs.electricity_price_multiplier

sim_cfg = SimulationConfig(
    it_capacity_mw=it_capacity_mw,
    utilization_pct=scenario_inputs.workload_utilization_pct,
    operating_hours_per_day=24.0,
    ambient_temp_c=scenario_inputs.ambient_temp_c,
    ambient_temp_normal_c=ambient_normal,
    cooling_tech=cooling_techs[cooling_key],
    desal_share_pct=desal_share,
    sec_kwh_per_m3=sec_mid,
    other_water_m3_per_day=5.0,
    other_energy_mwh_per_day=it_capacity_mw * 0.02,
    renewable_penetration_pct=renewable_pct,
    grid_carbon_g_per_kwh=grid_carbon,
    electricity_price_usd_per_kwh=effective_elec_price,
    water_cost_usd_per_m3=2.0 * water_source_mix.get("relative_cost_per_m3", 1.0),
    regional_water_stress_score=water_stress_score,
)

result = simulate(sim_cfg)

baseline_cfg = SimulationConfig(
    it_capacity_mw=it_capacity_mw,
    utilization_pct=utilization_pct,
    operating_hours_per_day=24.0,
    ambient_temp_c=ambient_normal,
    ambient_temp_normal_c=ambient_normal,
    cooling_tech=cooling_techs["evaporative_cooling"],
    desal_share_pct=95.0,
    sec_kwh_per_m3=sec_mid,
    other_water_m3_per_day=5.0,
    other_energy_mwh_per_day=it_capacity_mw * 0.02,
    renewable_penetration_pct=0.0,
    grid_carbon_g_per_kwh=grid_carbon,
    electricity_price_usd_per_kwh=elec_price,
    water_cost_usd_per_m3=2.0,
    regional_water_stress_score=water_stress_score,
)
baseline_result = simulate(baseline_cfg)

st.subheader(f"System status: {location.replace('_', ' ')}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("IT load (MW)", f"{result.it_power_mw:.1f}")
c2.metric("Effective PUE", f"{result.effective_pue:.2f}")
c3.metric("Water use (m3/day)", f"{result.total_water_m3_per_day:.1f}")
c4.metric("WERI resilience", f"{result.weri_score:.0f}/100")

c5, c6, c7 = st.columns(3)
c5.metric("Total energy (MWh/day)", f"{result.total_energy_mwh_per_day:.1f}")
c6.metric("Operational cost (USD/day)", f"{result.total_opex_usd_per_day:,.0f}")
c7.metric("Carbon (tCO2e/day)", f"{result.carbon_t_co2e_per_day:.3f}")

st.divider()

st.subheader("Baseline vs. current configuration")
st.caption("Baseline = evaporative cooling, 95% desalinated water, grid-only energy, normal climate for this country.")

metrics = ["total_water_m3_per_day", "total_energy_mwh_per_day", "total_opex_usd_per_day",
           "carbon_t_co2e_per_day", "weri_score"]
labels = ["Water (m3/day)", "Energy (MWh/day)", "Cost (USD/day)", "Carbon (tCO2e/day)", "WERI (0-100)"]
baseline_vals = [getattr(baseline_result, m) for m in metrics]
current_vals = [getattr(result, m) for m in metrics]

fig = go.Figure()
fig.add_trace(go.Bar(name="Baseline", x=labels, y=baseline_vals, marker_color="#2a78d6"))
fig.add_trace(go.Bar(name="Current configuration", x=labels, y=current_vals, marker_color="#1baf7a"))
fig.update_layout(barmode="group", height=380)
st.plotly_chart(fig, use_container_width=True)

comparison_rows = []
for label, base_v, cur_v in zip(labels, baseline_vals, current_vals):
    abs_change = cur_v - base_v
    pct_change = (abs_change / base_v * 100) if base_v != 0 else float("nan")
    comparison_rows.append({"Metric": label, "Baseline": round(base_v, 3), "Current": round(cur_v, 3),
                             "Absolute change": round(abs_change, 3), "% change": round(pct_change, 1)})
st.dataframe(pd.DataFrame(comparison_rows), use_container_width=True, hide_index=True)

st.download_button(
    "Export comparison as CSV",
    pd.DataFrame(comparison_rows).to_csv(index=False),
    file_name=f"aquanexus_{location}_baseline_vs_current.csv",
    mime="text/csv",
)

st.divider()

st.subheader("Optimize configuration")
st.caption("Enumerates cooling technology x water source x energy configuration combinations and evaluates all five objectives for each.")

if st.button("Run optimization"):
    try:
        with st.spinner("Running optimization across all 45 configurations..."):
            base_kwargs = dict(
                it_capacity_mw=it_capacity_mw,
                utilization_pct=scenario_inputs.workload_utilization_pct,
                operating_hours_per_day=24.0,
                ambient_temp_c=scenario_inputs.ambient_temp_c,
                ambient_temp_normal_c=ambient_normal,
                sec_kwh_per_m3=sec_mid,
                other_water_m3_per_day=5.0,
                other_energy_mwh_per_day=it_capacity_mw * 0.02,
                grid_carbon_g_per_kwh=grid_carbon,
                electricity_price_usd_per_kwh=effective_elec_price,
                water_cost_usd_per_m3=2.0,
                regional_water_stress_score=water_stress_score,
            )
            water_options = {"desalinated": 95.0, "reclaimed": 10.0, "hybrid_supply": 60.0}
            energy_options = {k: v["renewable_penetration_pct"] for k, v in energy_profiles.items()}

            candidates = enumerate_candidates(base_kwargs, cooling_techs, water_options, energy_options)
            frontier = pareto_frontier(candidates)

            weights = {"water": 0.25, "energy": 0.2, "cost": 0.2, "carbon": 0.15, "resilience": 0.2}
            scores = weighted_score(candidates, weights)
            best_idx = scores.index(min(scores))
            best = candidates[best_idx]

            rec = explain(best, scenario_inputs.ambient_temp_c, ambient_normal)
    except Exception as e:
        st.error(f"Optimization failed with an error: {e}")
        st.exception(e)
        st.stop()

    st.markdown("### Recommended configuration")
    st.success(rec.headline)
    st.write(rec.reasoning)

    st.markdown("### Pareto frontier (non-dominated configurations)")
    frontier_rows = []
    for c in frontier:
        frontier_rows.append({
            "Cooling": cooling_techs[c.cooling_tech_key].label,
            "Water (desal %)": c.desal_share_pct,
            "Energy config": energy_profiles[c.energy_config_key]["label"],
            "Water (m3/day)": c.result.total_water_m3_per_day,
            "Energy (MWh/day)": c.result.total_energy_mwh_per_day,
            "Cost (USD/day)": c.result.total_opex_usd_per_day,
            "Carbon (tCO2e/day)": c.result.carbon_t_co2e_per_day,
            "WERI": c.result.weri_score,
        })
    frontier_df = pd.DataFrame(frontier_rows)
    st.dataframe(frontier_df, use_container_width=True, hide_index=True)
    st.download_button("Export Pareto frontier as CSV", frontier_df.to_csv(index=False),
                        file_name=f"aquanexus_{location}_pareto_frontier.csv", mime="text/csv")

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=[c.result.total_water_m3_per_day for c in candidates],
        y=[c.result.total_energy_mwh_per_day for c in candidates],
        mode="markers", name="All candidates", marker=dict(color="#c3c2b7", size=8),
    ))
    fig2.add_trace(go.Scatter(
        x=[c.result.total_water_m3_per_day for c in frontier],
        y=[c.result.total_energy_mwh_per_day for c in frontier],
        mode="markers", name="Pareto frontier", marker=dict(color="#1baf7a", size=11, symbol="diamond"),
    ))
    fig2.update_layout(xaxis_title="Water (m3/day)", yaxis_title="Energy (MWh/day)", height=420)
    st.plotly_chart(fig2, use_container_width=True)

st.divider()
st.caption(
    "AquaNexus is a prototype engineering decision-support tool built for scenario-based analysis. "
    "It is not a validated industrial control system. Climate data is fetched live via Open-Meteo where "
    "network access allows; electricity prices are sourced from GlobalPetrolPrices.com and other cited "
    "aggregators. See docs/limitations.md and data/sources.csv for full parameter provenance and confidence levels."
)
