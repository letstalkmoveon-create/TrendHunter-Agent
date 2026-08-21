#!/usr/bin/env python3
"""
Renders a mined brief.json into the actual report — an email-safe HTML file
(inline-friendly styling, no external assets, since this gets sent as an
email body).

brief.json schema (written by Claude, see SKILL.md):
{
  "run_date": str,
  "topics_scanned": [str],
  "summary": str,
  "trends": [{"title": str, "description": str, "evidence_urls": [str]}],       # exactly 5
  "book_concepts": [{"title": str, "subtitle": str, "target_audience": str,
                      "core_promise": str, "market_gap": str, "evidence_urls": [str]}],  # exactly 5
  "angles": [{"name": str, "description": str, "why_it_sells": str,
               "market_gap_addressed": str}],                                   # exactly 2
  "table_of_contents": [{"chapter": int, "title": str, "description": str}],    # exactly 15
  "differentiation_notes": str,
  "sources_consulted": [{"site": str, "title": str, "url": str}]
}
"""

import argparse
import html
import json
import sys
from pathlib import Path


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def render_trend(i, t):
    urls = t.get("evidence_urls") or []
    links = " · ".join(f'<a href="{esc(u)}">source</a>' for u in urls)
    return f"""
    <div class="card">
      <h3>{i}. {esc(t.get("title", ""))}</h3>
      <p>{esc(t.get("description", ""))}</p>
      <div class="footer">{links}</div>
    </div>"""


def render_concept(i, c):
    urls = c.get("evidence_urls") or []
    links = " · ".join(f'<a href="{esc(u)}">source</a>' for u in urls)
    return f"""
    <div class="card">
      <h3>{i}. {esc(c.get("title", ""))}</h3>
      <p class="subtitle">{esc(c.get("subtitle", ""))}</p>
      <p><strong>Audience:</strong> {esc(c.get("target_audience", ""))}</p>
      <p><strong>Core promise:</strong> {esc(c.get("core_promise", ""))}</p>
      <p><strong>Market gap:</strong> {esc(c.get("market_gap", ""))}</p>
      <div class="footer">{links}</div>
    </div>"""


def render_angle(i, a):
    return f"""
    <div class="card angle-card">
      <h3>Angle {i}: {esc(a.get("name", ""))}</h3>
      <p>{esc(a.get("description", ""))}</p>
      <p><strong>Why it sells:</strong> {esc(a.get("why_it_sells", ""))}</p>
      <p><strong>Gap addressed:</strong> {esc(a.get("market_gap_addressed", ""))}</p>
    </div>"""


def render_toc(items):
    rows = "".join(
        f'<tr><td class="ch-num">{esc(c.get("chapter", ""))}</td>'
        f'<td><strong>{esc(c.get("title", ""))}</strong><br>'
        f'<span class="muted">{esc(c.get("description", ""))}</span></td></tr>'
        for c in items
    )
    return f'<table class="toc">{rows}</table>'


def render_sources(items):
    if not items:
        return '<p class="muted">No sources logged.</p>'
    rows = "".join(
        f'<li><span class="site-tag">{esc(s.get("site", ""))}</span> '
        f'<a href="{esc(s.get("url", ""))}">{esc(s.get("title") or s.get("url", ""))}</a></li>'
        for s in items
    )
    return f'<ul class="sources">{rows}</ul>'


CSS = """
body { margin:0; padding:0; background:#f4f3f0; font-family:Georgia, 'Times New Roman', serif; color:#2a2621; }
.wrap { max-width:720px; margin:0 auto; padding:2rem 1.5rem; }
h1 { font-size:1.6rem; margin:0 0 .25rem; }
.subtitle-line { color:#6b6255; font-size:.85rem; margin-bottom:1.5rem; }
.summary { background:#fff; border-left:4px solid #b5651d; padding:1rem 1.25rem; margin-bottom:2rem; font-size:1rem; }
section { margin-bottom:2.25rem; }
h2 { font-size:1rem; text-transform:uppercase; letter-spacing:.06em; color:#8a7f6e; border-bottom:1px solid #ddd7c9; padding-bottom:.4rem; }
.card { background:#fff; border:1px solid #e4dfd2; border-radius:8px; padding:1rem 1.25rem; margin-bottom:.9rem; }
.card h3 { margin:0 0 .4rem; font-size:1.05rem; }
.card p { margin:.3rem 0; font-size:.95rem; line-height:1.45; }
.subtitle { font-style:italic; color:#5a5347; }
.angle-card { border-left:4px solid #2f6f4f; }
.footer { margin-top:.6rem; font-size:.8rem; }
.footer a { color:#b5651d; text-decoration:none; }
table.toc { width:100%; border-collapse:collapse; background:#fff; }
table.toc td { border-bottom:1px solid #eee3d3; padding:.6rem .5rem; font-size:.9rem; vertical-align:top; }
.ch-num { width:2.2rem; font-weight:bold; color:#b5651d; }
.muted { color:#847a6a; font-size:.85rem; }
.sources { list-style:none; padding:0; font-size:.82rem; }
.sources li { padding:.25rem 0; border-bottom:1px solid #eee3d3; }
.site-tag { display:inline-block; background:#eee3d3; color:#5a5347; font-size:.7rem; text-transform:uppercase; padding:.1rem .4rem; border-radius:4px; margin-right:.4rem; }
.diff-notes { background:#fff; padding:1rem 1.25rem; border-radius:8px; font-size:.92rem; }
"""


def render_html(brief):
    run_date = brief.get("run_date", "")
    topics = ", ".join(brief.get("topics_scanned") or [])
    summary = brief.get("summary", "")
    trends = brief.get("trends") or []
    concepts = brief.get("book_concepts") or []
    angles = brief.get("angles") or []
    toc = brief.get("table_of_contents") or []
    diff = brief.get("differentiation_notes", "")
    sources = brief.get("sources_consulted") or []

    body = f"""
    <div class="wrap">
    <h1>Self-Help &amp; Non-Fiction Market Gap Report</h1>
    <div class="subtitle-line">{esc(run_date)} · Topics scanned: {esc(topics)}</div>
    {f'<div class="summary">{esc(summary)}</div>' if summary else ''}

    <section>
      <h2>5 High-Demand Trends</h2>
      {"".join(render_trend(i + 1, t) for i, t in enumerate(trends))}
    </section>

    <section>
      <h2>5 Book Concepts</h2>
      {"".join(render_concept(i + 1, c) for i, c in enumerate(concepts))}
    </section>

    <section>
      <h2>2 Angles Most Likely to Sell</h2>
      {"".join(render_angle(i + 1, a) for i, a in enumerate(angles))}
    </section>

    <section>
      <h2>Proposed Table of Contents (15 Chapters)</h2>
      {render_toc(toc)}
      {f'<p class="diff-notes"><strong>Why this differs from what exists:</strong> {esc(diff)}</p>' if diff else ''}
    </section>

    <section>
      <h2>Sources Consulted</h2>
      {render_sources(sources)}
    </section>
    </div>
    """

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Book Gap Report: {esc(run_date)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>"""


def main(argv=None):
    p = argparse.ArgumentParser(description="Render a mined brief.json into an email-safe HTML report.")
    p.add_argument("--brief", required=True, help="Path to brief.json")
    p.add_argument("--output", default=None, help="Path to write report.html (default: alongside brief.json)")
    args = p.parse_args(argv)

    brief_path = Path(args.brief)
    if not brief_path.exists():
        sys.exit(f"Brief file not found: {brief_path}")
    brief = json.loads(brief_path.read_text(encoding="utf-8"))

    output_path = Path(args.output) if args.output else brief_path.parent / "report.html"
    output_path.write_text(render_html(brief), encoding="utf-8")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
