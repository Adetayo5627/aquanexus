"""UI helpers: stylesheet, number formatting and small HTML components."""
import math
import html as _html
import streamlit as st

TEAL, TEAL_DARK, AMBER, SLATE, RED, GREY, GREEN = "#0f766e", "#115e59", "#d97706", "#334155", "#b91c1c", "#cbd5e1", "#15803d"

CSS = """
<style>
html, body, [class*="css"] {font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;}
.block-container {padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1280px;}
header[data-testid="stHeader"] {background: transparent;}
section[data-testid="stSidebar"] {background: #ffffff; border-right: 1px solid #e2e8f0;}
section[data-testid="stSidebar"] .block-container {padding-top: 1rem;}
h1, h2, h3, h4 {letter-spacing: -0.01em;}
.hero {background: linear-gradient(115deg, #0b3b4a 0%, #0f766e 60%, #14917f 100%); color: #fff; padding: 1.5rem 1.8rem; border-radius: 18px; margin-bottom: .9rem; position: relative; overflow: hidden;}
.hero:after {content:""; position:absolute; right:-60px; top:-60px; width:260px; height:260px; border-radius:50%; background: rgba(255,255,255,.07);}
.hero .eyebrow {font-size:.74rem; letter-spacing:.14em; text-transform:uppercase; opacity:.8; margin-bottom:.35rem;}
.hero h1 {margin:0; font-size:2.05rem; color:#fff; font-weight:750; line-height:1.15;}
.hero p {margin:.45rem 0 .9rem 0; font-size:1.02rem; opacity:.93; max-width: 62rem;}
.chip {display:inline-block; padding:.2rem .7rem; border-radius:999px; font-size:.76rem; margin:0 .4rem .3rem 0; background:rgba(255,255,255,.16); color:#fff; border:1px solid rgba(255,255,255,.28);}
.chip.ok {background:rgba(187,247,208,.22); border-color:rgba(187,247,208,.55);}
.chip.warn {background:rgba(254,243,199,.2); border-color:rgba(253,230,138,.55);}
.statstrip {display:grid; grid-template-columns: repeat(4, 1fr); gap:.8rem; margin:.4rem 0 1rem 0;}
.stat {background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:.8rem 1rem;}
.stat .n {font-size:1.45rem; font-weight:750; color:#0b3b4a; line-height:1.15;}
.stat .t {font-size:.8rem; color:#475569; margin-top:.15rem;}
.stat .s {font-size:.68rem; color:#94a3b8; margin-top:.3rem;}
.answer {background:#fff; border:1px solid #cfe7e3; border-left:7px solid #0f766e; border-radius:14px; padding:1.1rem 1.3rem; margin:.5rem 0 1rem 0; box-shadow:0 1px 2px rgba(15,23,42,.04);}
.answer .lab {font-size:.72rem; letter-spacing:.12em; text-transform:uppercase; color:#0f766e; font-weight:700;}
.answer .big {font-size:1.28rem; font-weight:700; color:#0f172a; margin:.25rem 0 .35rem 0; line-height:1.35;}
.answer .sub {color:#475569; font-size:.95rem; line-height:1.5;}
.kpis {display:grid; grid-template-columns: repeat(5, 1fr); gap:.8rem; margin-bottom:1rem;}
.kpi {background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:.9rem 1rem; box-shadow:0 1px 2px rgba(15,23,42,.04);}
.kpi .l {font-size:.78rem; color:#475569; font-weight:600;}
.kpi .v {font-size:2rem; font-weight:800; line-height:1.15; margin:.15rem 0;}
.kpi .v.good {color:#0f766e;} .kpi .v.bad {color:#b91c1c;} .kpi .v.flat {color:#334155;}
.kpi .a {font-size:.8rem; color:#334155;}
.kpi .r {font-size:.7rem; color:#64748b; margin-top:.4rem; padding-top:.4rem; border-top:1px dashed #e2e8f0;}
.card {background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:1rem 1.1rem; height:100%;}
.card h4 {margin:0 0 .35rem 0; font-size:1rem; color:#0b3b4a;}
.card p, .card li {font-size:.88rem; color:#334155; line-height:1.5;}
.card .tag {display:inline-block; font-size:.68rem; font-weight:700; padding:.1rem .5rem; border-radius:6px; background:#e6f4f1; color:#0f766e; margin-bottom:.4rem;}
.design {display:grid; grid-template-columns: repeat(4, 1fr); gap:.6rem; margin:.3rem 0 .8rem 0;}
.design div {background:#f0fdfa; border:1px solid #bfe6df; border-radius:12px; padding:.6rem .8rem;}
.design b {display:block; font-size:.68rem; letter-spacing:.08em; text-transform:uppercase; color:#0f766e;}
.design span {font-size:.9rem; color:#0f172a; font-weight:600;}
.sect {font-size:1.25rem; font-weight:750; color:#0b3b4a; margin:1.6rem 0 .1rem 0;}
.sectsub {color:#64748b; font-size:.9rem; margin-bottom:.6rem;}
.ok-row {color:#15803d; font-weight:600;} .bad-row {color:#b91c1c; font-weight:600;}
.note {background:#fff7ed; border:1px solid #fed7aa; color:#7c2d12; border-radius:12px; padding:.6rem .9rem; font-size:.85rem;}
div[data-testid="stMetric"] {background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:.7rem .9rem;}
button[data-baseweb="tab"] {font-size:.98rem; font-weight:600; padding:.55rem .9rem;}
.stTabs [data-baseweb="tab-list"] {gap:.2rem; border-bottom:1px solid #e2e8f0;}
@media (max-width: 900px) {.statstrip, .kpis, .design {grid-template-columns: repeat(2, 1fr);}}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def esc(s):
    return _html.escape(str(s))


def sig(value, digits=3):
    if not value:
        return 0.0
    d = digits - int(math.floor(math.log10(abs(value)))) - 1
    return round(value, max(d, 0))


def fmt(value, digits=3):
    """Number with sensible precision and thousands separators, no stray '.0'."""
    v = sig(value, digits)
    if abs(v) >= 100:
        return f"{v:,.0f}"
    s = f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 10 else f"{v:,.1f}".rstrip("0").rstrip(".")
    return s


def pct(value, plus=True):
    s = f"{value:+.0f}%" if plus else f"{value:.0f}%"
    return s.replace("-", "−")


def section(title, sub=""):
    st.markdown(f'<div class="sect">{esc(title)}</div>' + (f'<div class="sectsub">{esc(sub)}</div>' if sub else ""), unsafe_allow_html=True)


def kpi(label, value, tone, absolute, rng=None):
    r = f'<div class="r">{esc(rng)}</div>' if rng else ""
    return f'<div class="kpi"><div class="l">{esc(label)}</div><div class="v {tone}">{esc(value)}</div><div class="a">{esc(absolute)}</div>{r}</div>'


def show_df(df):
    try:
        st.dataframe(df, width="stretch", hide_index=True)
    except TypeError:
        st.dataframe(df, use_container_width=True, hide_index=True)


def show_chart(fig, container=None):
    t = container if container is not None else st
    try:
        t.plotly_chart(fig, width="stretch")
    except TypeError:
        t.plotly_chart(fig, use_container_width=True)


def style_fig(fig, height=360):
    fig.update_layout(height=height, template="plotly_white", margin=dict(t=30, b=10, l=10, r=10),
                      font=dict(family="-apple-system, Segoe UI, Roboto, Arial", size=13, color="#334155"),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=-0.22))
    return fig
