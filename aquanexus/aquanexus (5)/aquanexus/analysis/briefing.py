"""briefing.py - a self-contained, printable one-page decision brief (HTML)."""
import html
import datetime


def build_brief_html(d: dict) -> str:
    e = html.escape
    kp = "".join(f'<div class="k"><div class="l">{e(k["label"])}</div><div class="v">{e(k["value"])}</div><div class="a">{e(k["abs"])}</div></div>' for k in d["kpis"])
    trade = "".join(f"<li>{e(t)}</li>" for t in d["tradeoffs"])
    stress = "".join(f'<tr><td>{e(r["scenario"])}</td><td>{e(r["base"])}</td><td>{e(r["design"])}</td></tr>' for r in d["stress"])
    sc = d["scale"]
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>AquaNexus decision brief</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#0f172a;max-width:860px;margin:2rem auto;padding:0 1.2rem;line-height:1.5}}
h1{{font-size:1.6rem;margin:0}} .sub{{color:#475569;margin:.2rem 0 1rem}} h2{{font-size:1.05rem;color:#0b3b4a;border-bottom:2px solid #0f766e;padding-bottom:.2rem;margin-top:1.4rem}}
.hl{{background:#f0fdfa;border-left:6px solid #0f766e;padding:.8rem 1rem;border-radius:8px;font-size:1.05rem}}
.grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:.6rem}} .k{{border:1px solid #e2e8f0;border-radius:10px;padding:.6rem}}
.k .l{{font-size:.72rem;color:#475569}} .k .v{{font-size:1.4rem;font-weight:800;color:#0f766e}} .k .a{{font-size:.72rem;color:#475569}}
table{{border-collapse:collapse;width:100%;font-size:.88rem}} td,th{{border-bottom:1px solid #e2e8f0;padding:.35rem .5rem;text-align:left}}
.cav{{font-size:.8rem;color:#475569}} @media print{{body{{margin:0}}}}
</style></head><body>
<h1>AquaNexus decision brief</h1>
<div class="sub">{e(d["site"])} | {e(d["facility"])} | scenario: {e(d["scenario"])} | generated {datetime.date.today().isoformat()}</div>
<div class="hl"><b>{e(d["headline"])}</b><br>{e(d["design"])}</div>
<h2>Impact versus the conventional design</h2><div class="grid">{kp}</div>
<p class="cav">{e(d["range_note"])}</p>
<h2>Trade-offs to be aware of</h2><ul>{trade}</ul>
<h2>Stress test (water use, m3/day)</h2><table><tr><th>Scenario</th><th>Conventional</th><th>Recommended</th></tr>{stress}</table>
<h2>At pipeline scale ({sc["mw"]:.0f} MW of new capacity)</h2>
<p>{e(sc["text"])}</p>
<h2>How to read this</h2>
<p class="cav">AquaNexus is a configuration-screening model. It ranks a defined set of cooling, water and energy designs under stated assumptions. Inputs are literature-based estimates, each country is represented by its capital city, and the resilience score is a project-level decision metric, not an established index. Treat the output as a short list for detailed engineering study, not a design.</p>
</body></html>"""
