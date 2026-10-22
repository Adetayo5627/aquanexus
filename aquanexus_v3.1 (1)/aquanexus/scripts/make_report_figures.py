"""Publication-style figures for the AquaNexus technical report, generated from the model code.

Usage (from the repository root):  python scripts/make_report_figures.py . figures/
"""
import sys, os, random
root, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
os.makedirs(out, exist_ok=True)

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch
from matplotlib.ticker import AutoMinorLocator

from core.context import SiteContext, load_library, PRIORITY_PROFILES, BASELINE_KEY
from models.cooling import compute_cooling
from analysis.robustness import _scaled, PARAMS
from analysis.policy import wue_sweep
from optimization.optimizer import enumerate_candidates

# ---------------- style ----------------
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans"], "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.minor.width": 0.4, "ytick.minor.width": 0.4,
    "xtick.direction": "in", "ytick.direction": "in", "xtick.top": True, "ytick.right": True,
    "xtick.major.size": 3, "ytick.major.size": 3, "xtick.minor.size": 1.5, "ytick.minor.size": 1.5,
    "legend.frameon": False, "legend.handlelength": 1.6, "lines.linewidth": 1.2,
    "savefig.dpi": 600, "savefig.bbox": "tight", "savefig.pad_inches": 0.03,
    "mathtext.default": "regular",
})
W = 6.3  # full text width, inches
NAVY, GREY, LGREY = "#1f3b63", "#8c8c8c", "#cfcfcf"
WATER, ENERGY, COST, CARBON = "#2a6bb0", "#2e9e8f", "#d9a03b", "#a63d40"
SOLAR, BATT = "#d9a03b", "#2a6bb0"


def panel(ax, letter):
    ax.text(-0.02, 1.02, f"({letter})", transform=ax.transAxes, ha="right", va="bottom", fontweight="bold")


def minor(ax, x=True, y=True):
    if x: ax.xaxis.set_minor_locator(AutoMinorLocator())
    if y: ax.yaxis.set_minor_locator(AutoMinorLocator())


def save(fig, name):
    fig.savefig(os.path.join(out, name))
    plt.close(fig)


lib = load_library(root)
ctx = SiteContext(lib, "UAE")
B = PRIORITY_PROFILES["Balanced"]
REC = ("direct_to_chip", "adiabatic", "reclaimed", "grid_plus_solar")
REC_ST = ("direct_to_chip", "adiabatic", "reclaimed", "grid_plus_solar_plus_storage")

# ================= Figure 1: system diagram =================
def fig_system():
    fig, ax = plt.subplots(figsize=(W, 2.7))
    ax.set_xlim(0, 100); ax.set_ylim(0, 44); ax.axis("off")
    bw, bh, fs = 15.8, 7.6, 6.2

    def box(x, y, text, fill="white", w=bw, h=bh):
        ax.add_patch(Rectangle((x, y), w, h, fc=fill, ec="black", lw=0.7))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, linespacing=1.3)

    def arrow(p, q, conn="arc3"):
        ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=6.5, lw=0.7, color="black",
                                     shrinkA=0, shrinkB=0, connectionstyle=conn))

    x0, gap = 13.0, 1.9
    xs = [x0 + i * (bw + gap) for i in range(5)]
    y1, y2, y3 = 33.0, 19.0, 3.0
    top = ["AI workload\n$P_{IT}$, $Q_{IT}$", "Cooling: chip-side\n× heat rejection", "Water demand\nand source split",
           "Desalination\nenergy", "Total facility\nenergy $E_{tot}$"]
    for x, t in zip(xs, top):
        box(x, y1, t)
    for a_, b_ in zip(xs[:-1], xs[1:]):
        arrow((a_ + bw, y1 + bh / 2), (b_, y1 + bh / 2))
    mid = {1: "Wet-bulb (Stull),\nthresholds, WUE", 2: "Reclaimed supply\nlimit, desal. fallback",
           3: "24-h solar, battery\nand grid dispatch", 4: "Carbon, all-in cost\nand WERI"}
    for i, t in mid.items():
        box(xs[i], y2, t, fill="#ededed")
    arrow((xs[1] + bw / 2, y2 + bh), (xs[1] + bw / 2, y1))
    arrow((xs[2] + bw / 2, y2 + bh), (xs[2] + bw / 2, y1))
    arrow((xs[4] + bw / 2, y1), (xs[3] + bw / 2, y2 + bh))
    arrow((xs[3] + bw, y2 + bh / 2), (xs[4], y2 + bh / 2))
    dw = (xs[4] + bw - x0 - 3.0) / 2
    box(x0, y3, "Decision layer: 81 designs enumerated, feasibility\nlimits, Pareto frontier, weighted ranking", w=dw)
    box(x0 + dw + 3.0, y3, "Analysis layer: 9 stress scenarios, OAT and\nMonte Carlo robustness, Policy Lab, scale-up", w=dw)
    arrow((xs[4] + bw / 2, y2), (xs[4] + bw / 2, y3 + bh))
    ymid = (y2 + y3 + bh) / 2
    ax.plot([xs[4] + 3.0, xs[4] + 3.0, x0 + dw / 2], [y2, ymid, ymid], color="black", lw=0.7)
    arrow((x0 + dw / 2, ymid), (x0 + dw / 2, y3 + bh))
    for y, lab in [(y1 + bh / 2, "Physical\nchain"), (y2 + bh / 2, "Supply and\nmetrics"), (y3 + bh / 2, "Decision and\nanalysis")]:
        ax.text(0.0, y, lab, ha="left", va="center", fontsize=fs, style="italic", linespacing=1.25)
    save(fig, "fig01_system.png")


# ================= Figure 3: cooling response =================
def fig_cooling():
    T = np.linspace(20, 55, 141)
    rh = 40.0
    combos = [(("air", "cooling_tower"), "Air + cooling tower", "-", "black"),
              (("direct_to_chip", "adiabatic"), "Direct-to-chip + adiabatic", "--", WATER),
              (("immersion", "dry_cooler"), "Immersion + dry cooler", "-.", CARBON)]
    fig, (a, b) = plt.subplots(1, 2, figsize=(W, 2.05))
    for (c, r), lab, ls, col in combos:
        y = [compute_cooling(50, lib.chips[c], lib.rejs[r], t, rh).effective_pue for t in T]
        a.plot(T, y, ls=ls, color=col, label=lab)
    a.set_xlabel("Dry-bulb temperature (°C)"); a.set_ylabel("Effective PUE (–)")
    a.legend(loc="upper left"); a.set_xlim(20, 55); minor(a); panel(a, "a")
    rejs = [("dry_cooler", "Dry cooler", "-", "black"), ("adiabatic", "Adiabatic", "--", WATER), ("cooling_tower", "Cooling tower", "-.", CARBON)]
    for r, lab, ls, col in rejs:
        y = [compute_cooling(50, lib.chips["air"], lib.rejs[r], t, rh).cooling_energy_mwh_per_day for t in T]
        b.plot(T, y, ls=ls, color=col, label=lab)
    b.set_xlabel("Dry-bulb temperature (°C)"); b.set_ylabel("Cooling energy (MWh d$^{-1}$)")
    b.legend(loc="upper left", title="Air-cooled racks with:", title_fontsize=7.5, alignment="left")
    b.set_xlim(20, 55); minor(b); panel(b, "b")
    fig.tight_layout(w_pad=2.5)
    save(fig, "fig03_cooling.png")


# ================= Figure 4: dispatch without / with storage =================
def fig_dispatch():
    fig, axs = plt.subplots(1, 2, figsize=(W, 2.1), sharey=True)
    h = np.arange(24)
    for ax, key, letter, ttl in [(axs[0], REC, "a", "Grid + solar PV"), (axs[1], REC_ST, "b", "Grid + solar PV + 4-h battery")]:
        r = ctx.simulate_design(key)
        load = np.array(r.hourly_load_mw); sol = np.array(r.hourly_solar_mw); grid = np.array(r.hourly_grid_mw)
        direct = np.minimum(load, sol)
        batt = load - direct - grid
        ax.bar(h, direct, width=1.0, color=SOLAR, ec="white", lw=0.3, label="Solar to load", align="edge")
        ax.bar(h, batt, bottom=direct, width=1.0, color=BATT, ec="white", lw=0.3, label="Battery to load", align="edge")
        ax.bar(h, grid, bottom=direct + batt, width=1.0, color=LGREY, ec="white", lw=0.3, label="Grid import", align="edge")
        ax.step(np.r_[h, 24], np.r_[sol, sol[-1]], where="post", color="black", lw=0.9, ls="--", label="Solar generation")
        ax.set_xlim(0, 24); ax.set_xticks(range(0, 25, 6)); ax.set_xlabel("Hour of day")
        ax.text(0.98, 0.95, ttl, transform=ax.transAxes, ha="right", va="top", fontsize=7.5)
        ax.set_ylim(0, 85); minor(ax, x=False); panel(ax, letter)
    axs[0].set_ylabel("Power (MW)")
    hdl, lab = axs[1].get_legend_handles_labels()
    fig.legend(hdl, lab, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.06))
    fig.tight_layout(w_pad=1.5)
    save(fig, "fig04_dispatch.png")


# ================= Figure 5: Pareto =================
def fig_pareto():
    s = ctx.screen("Normal", B)
    front = set(id(c) for c in s.frontier)
    fig, (a, b) = plt.subplots(1, 2, figsize=(W, 2.2))
    for ax, fx, fy, xl, yl, sx, sy in [
        (a, lambda r: r.total_water_m3_per_day, lambda r: r.total_energy_mwh_per_day, "Site water use (m$^3$ d$^{-1}$)", "Facility energy (MWh d$^{-1}$)", 1, 1),
        (b, lambda r: r.total_cost_usd_per_day / 1000, lambda r: r.carbon_t_co2e_per_day, "All-in cost (10$^3$ USD d$^{-1}$)", "Carbon (t CO$_2$e d$^{-1}$)", 1, 1)]:
        dom = [c for c in s.candidates if id(c) not in front]
        par = [c for c in s.candidates if id(c) in front]
        ax.scatter([fx(c.result) for c in dom], [fy(c.result) for c in dom], s=10, facecolor="white", edgecolor=GREY, lw=0.6, label="Dominated design", zorder=2)
        ax.scatter([fx(c.result) for c in par], [fy(c.result) for c in par], s=12, color=NAVY, lw=0, label="Pareto-optimal design", zorder=3)
        br, bs = s.best.result, s.baseline
        ax.scatter([fx(bs)], [fy(bs)], s=34, marker="s", facecolor="white", edgecolor="black", lw=0.9, zorder=4, label="Conventional design")
        ax.scatter([fx(br)], [fy(br)], s=46, marker="D", facecolor=COST, edgecolor="black", lw=0.7, zorder=5, label="Recommended (Balanced)")
        ax.set_xlabel(xl); ax.set_ylabel(yl); minor(ax)
    panel(a, "a"); panel(b, "b")
    hdl, lab = a.get_legend_handles_labels()
    fig.legend(hdl, lab, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.07))
    fig.tight_layout(w_pad=2.5)
    save(fig, "fig05_pareto.png")


# ================= Figure 6: cost structure =================
def comps(key):
    r = ctx.simulate_design(key)
    p = ctx.profile["electricity_price_usd_per_kwh"]
    wp = ctx.water_options()[key[2]]["water_cost_usd_per_m3"]
    lcoe = ctx.energy_options()[key[3]]["solar_lcoe_usd_per_kwh"]
    return {"Grid electricity": r.grid_energy_mwh_per_day * 1000 * p / 1000,
            "Solar electricity (LCOE)": r.solar_generated_mwh_per_day * 1000 * lcoe / 1000,
            "Water purchase": r.total_water_m3_per_day * wp / 1000,
            "Annualised cooling capex": r.annualized_capex_usd_per_day / 1000,
            "Battery capex": r.battery_cost_usd_per_day / 1000}, r.total_cost_usd_per_day / 1000


def fig_cost():
    rows = [("Conventional", BASELINE_KEY), ("Recommended", REC)]
    cols = {"Grid electricity": "#6e6e6e", "Solar electricity (LCOE)": SOLAR, "Water purchase": WATER,
            "Annualised cooling capex": NAVY, "Battery capex": CARBON}
    fig, ax = plt.subplots(figsize=(W * 0.72, 1.45))
    for i, (lab, key) in enumerate(rows[::-1]):
        c, tot = comps(key); left = 0
        for k, v in c.items():
            if v <= 0: continue
            ax.barh(i, v, left=left, height=0.55, color=cols[k], ec="white", lw=0.5, label=k if i == 1 or k == "Solar electricity (LCOE)" else None)
            left += v
        ax.text(left + 2, i, f"{tot:,.1f}", va="center", fontsize=7.5)
    ax.set_yticks([0, 1]); ax.set_yticklabels([r[0] for r in rows[::-1]])
    ax.set_xlim(0, 205); ax.set_xlabel("All-in cost (10$^3$ USD d$^{-1}$)"); minor(ax, y=False)
    ax.tick_params(axis="y", which="both", length=0)
    hdl, lab = ax.get_legend_handles_labels()
    order = [lab.index(k) for k in cols if k in lab]
    ax.legend([hdl[i] for i in order], [lab[i] for i in order], loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7)
    save(fig, "fig06_cost.png")


# ================= Figure 7: seven sites =================
def fig_sites():
    names = {"UAE": "UAE", "Saudi_Arabia": "Saudi Arabia", "Qatar": "Qatar", "Jordan": "Jordan", "Morocco": "Morocco", "Algeria": "Algeria", "Tunisia": "Tunisia"}
    data = {m: [] for m in ("Water", "Energy", "Cost", "Carbon")}
    for c in names:
        cx = SiteContext(lib, c); s = cx.screen("Normal", B); b, d = s.baseline, s.best.result
        data["Water"].append((d.total_water_m3_per_day / b.total_water_m3_per_day - 1) * 100)
        data["Energy"].append((d.total_energy_mwh_per_day / b.total_energy_mwh_per_day - 1) * 100)
        data["Cost"].append((d.total_cost_usd_per_day / b.total_cost_usd_per_day - 1) * 100)
        data["Carbon"].append((d.carbon_t_co2e_per_day / b.carbon_t_co2e_per_day - 1) * 100)
    fig, ax = plt.subplots(figsize=(W, 2.3))
    x = np.arange(len(names)); w = 0.19
    for i, (m, col) in enumerate(zip(data, (WATER, ENERGY, COST, CARBON))):
        ax.bar(x + (i - 1.5) * w, data[m], width=w, color=col, ec="none", label=m)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xticks(x); ax.set_xticklabels(list(names.values())); ax.tick_params(axis="x", which="both", length=0)
    ax.set_ylabel("Change against conventional design (%)"); ax.set_ylim(-105, 10); minor(ax, x=False)
    ax.legend(ncol=4, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    save(fig, "fig07_sites.png")
    return data


# ================= Figure 8: robustness (common vs technology-specific) =================
def fig_robust():
    designs = ["DTC + adiabatic, solar", "DTC + adiabatic, solar + battery", "Immersion + adiabatic, solar + battery",
               "Immersion + adiabatic, solar", "DTC + dry cooler, solar", "Immersion + dry cooler, solar + battery"]
    wc = [40.3, 20.7, 19.0, 14.0, 4.0, 0.0]; wi = [17.0, 17.3, 14.0, 10.7, 14.0, 12.0]
    rc = {"Water": (-79.8, -79.8, -79.7), "Energy": (-14.7, -12.6, -10.3), "Carbon": (-39.1, -37.6, -35.9), "Cost": (-15.7, -8.9, -2.0)}
    ri = {"Water": (-86.7, -79.9, -70.2), "Energy": (-20.0, -12.5, -5.0), "Carbon": (-42.9, -37.5, -32.2), "Cost": (-17.5, -9.2, -1.0)}
    fig, (a, b) = plt.subplots(1, 2, figsize=(W, 2.3), gridspec_kw={"width_ratios": [1.05, 1]})
    y = np.arange(len(designs))[::-1]; h = 0.38
    a.barh(y + h / 2, wc, h, color=LGREY, ec="none", label="Common factors")
    a.barh(y - h / 2, wi, h, color=NAVY, ec="none", label="Technology-specific factors")
    a.set_yticks(y); a.set_yticklabels(designs, fontsize=7); a.tick_params(axis="y", which="both", length=0)
    a.set_xlabel("Draws won (%)"); a.set_xlim(0, 45); minor(a, y=False); panel(a, "a")
    m = list(rc)[::-1]; yy = np.arange(len(m))
    for i, k in enumerate(m):
        for off, r, col in ((0.16, rc[k], GREY), (-0.16, ri[k], NAVY)):
            b.plot([r[0], r[2]], [yy[i] + off] * 2, color=col, lw=1.4, solid_capstyle="butt")
            b.plot([r[0], r[0]], [yy[i] + off - 0.07, yy[i] + off + 0.07], color=col, lw=0.8)
            b.plot([r[2], r[2]], [yy[i] + off - 0.07, yy[i] + off + 0.07], color=col, lw=0.8)
            b.plot(r[1], yy[i] + off, "o", ms=3.6, color=col, mec=col)
    b.axvline(0, color="black", lw=0.6, ls=":")
    b.set_yticks(yy); b.set_yticklabels(m); b.tick_params(axis="y", which="both", length=0)
    b.set_xlim(-92, 5); b.set_xlabel("Change against conventional design (%)"); minor(b, y=False); panel(b, "b")
    b.set_ylim(-0.6, len(m) - 0.4)
    hdl, lab = a.get_legend_handles_labels()
    fig.legend(hdl, lab, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.07))
    fig.tight_layout(w_pad=1.5)
    save(fig, "fig08_robustness.png")


# ================= Figure 9: tornado =================
def fig_tornado():
    sc = "Extreme heatwave (+5C)"; si = ctx.scenario_state(sc); kw0 = ctx.common_kwargs(si)
    def change(f):
        kw, ch, rj, en = _scaled(kw0, lib.chips, lib.rejs, ctx.energy_options(), f)
        def run(k):
            c, r, w, e = k
            return enumerate_candidates(kw, {c: ch[c]}, {r: rj[r]}, {w: ctx.water_options()[w]}, {e: en[e]})[0].result
        b, d = run(BASELINE_KEY), run(REC)
        return (d.total_cost_usd_per_day / b.total_cost_usd_per_day - 1) * 100
    nom = change({})
    rows = []
    for k, lab in PARAMS.items():
        rows.append((lab.replace(" (WUE)", ""), change({k: 0.7}), change({k: 1.3})))
    rows.sort(key=lambda t: abs(t[1] - t[2]))
    fig, ax = plt.subplots(figsize=(W * 0.78, 2.1))
    y = np.arange(len(rows))
    for i, (lab, lo, hi) in enumerate(rows):
        ax.barh(i, lo - nom, left=nom, height=0.6, color="#9dbbe0", ec="none", label="Input −30%" if i == len(rows) - 1 else None)
        ax.barh(i, hi - nom, left=nom, height=0.6, color=NAVY, ec="none", label="Input +30%" if i == len(rows) - 1 else None)
    ax.axvline(nom, color="black", lw=0.7)
    ax.text(nom + 0.12, len(rows) - 0.45, f"Nominal: {nom:.1f}%", ha="left", va="bottom", fontsize=7)
    ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows]); ax.tick_params(axis="y", which="both", length=0)
    ax.set_xlabel("Cost change of recommended vs. conventional design (%)"); minor(ax, y=False)
    ax.set_ylim(-0.6, len(rows) + 0.3)
    ax.legend(loc="lower left")
    save(fig, "fig09_tornado.png")
    return nom, rows


# ================= Figure 10: policy =================
def fig_policy():
    sw = [r for r in wue_sweep(ctx, "Normal", caps=(2.0, 1.0, 0.5, 0.3, 0.1, 0.05)) if r["premium_pct"] is not None]
    fig, ax = plt.subplots(figsize=(W * 0.62, 1.9))
    x = np.arange(len(sw))
    cols = [NAVY if r["key"][1] == "adiabatic" else WATER for r in sw]
    ax.bar(x, [r["premium_pct"] for r in sw], width=0.6, color=cols, ec="none")
    for i, r in enumerate(sw):
        ax.text(i, r["premium_pct"] + 0.12, f"+{r['premium_pct']:.1f}%", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(x); ax.set_xticklabels([f"≤ {r['cap']:g}" for r in sw]); ax.tick_params(axis="x", which="both", length=0)
    ax.set_xlabel("Site WUE cap (L kWh$^{-1}$)"); ax.set_ylabel("Cost of compliance (%)"); ax.set_ylim(0, 6.9); minor(ax, x=False)
    from matplotlib.patches import Patch
    ax.legend([Patch(color=NAVY), Patch(color=WATER)], ["Adiabatic rejection", "Dry cooler"], loc="upper center", ncol=2, title="Cheapest compliant design uses:", title_fontsize=7, fontsize=7, bbox_to_anchor=(0.5, 1.0))
    save(fig, "fig10_policy.png")
    return sw


if __name__ == "__main__":
    fig_system(); fig_cooling(); fig_dispatch(); fig_pareto(); fig_cost()
    d = fig_sites(); fig_robust(); t = fig_tornado(); p = fig_policy()
    print("sites", {k: [round(v) for v in vs] for k, vs in d.items()})
    print("tornado", t)
    print("policy", p)
