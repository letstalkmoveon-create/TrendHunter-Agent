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


def render_pick(i, p):
    return f"""
    <div class="card pick-card">
      <h3>Pick {i}: {esc(p.get("title", ""))}</h3>
      <p class="subtitle">{esc(p.get("subtitle", ""))}</p>
      <p>{esc(p.get("pitch", ""))}</p>
      <p><strong>Why this is a top pick:</strong> {esc(p.get("why_this_one", ""))}</p>
    </div>"""


VERDICT_COLORS = {"go": "#2f6f4f", "test first": "#b5851d", "pass": "#9c2f2f"}


def render_recommendation(r):
    if not r:
        return ""
    color = VERDICT_COLORS.get((r.get("verdict") or "").strip().lower(), "#5a5347")
    rows = "".join(
        f'<tr><td class="sc-factor">{esc(f.get("factor"))}</td>'
        f'<td class="sc-grade">{esc(f.get("grade"))}</td><td>{esc(f.get("note"))}</td></tr>'
        for f in r.get("scorecard") or []
    )
    steps = "".join(f"<li>{esc(x)}</li>" for x in r.get("next_steps") or [])
    return f"""
    <section>
      <h2>Recommended Book This Week</h2>
      <div class="card rec-card">
        <span class="verdict" style="background:{color}">{esc(r.get("verdict"))}</span>
        <h3>{esc(r.get("title"))}</h3>
        <p class="subtitle">{esc(r.get("subtitle"))}</p>
        <p><strong>{esc(r.get("one_line"))}</strong></p>
        <table class="scorecard">{rows}</table>
        {f'<p><strong>Test it first:</strong> {esc(r.get("validation_piece"))}</p>' if r.get("validation_piece") else ""}
        {f'<p><strong>Next 30 days:</strong></p><ol class="steps">{steps}</ol>' if steps else ""}
      </div>
    </section>"""


def _fmt_rank(n):
    return f"#{n:,}" if isinstance(n, int) else esc(n or "—")


def render_market(m):
    comps = "".join(
        f'<li><a href="{esc(c.get("url"))}">{esc(c.get("title"))}</a> — BSR {_fmt_rank(c.get("bsr"))}, '
        f'{esc(c.get("reviews"))} reviews, {esc(c.get("year"))}</li>'
        for c in m.get("comp_titles") or []
    )
    return f"""
    <div class="card market-card">
      <h3>{esc(m.get("topic"))} <span class="site-tag">{esc(m.get("verdict"))}</span></h3>
      <p class="muted">Median rank {_fmt_rank(m.get("median_bsr"))} · best {_fmt_rank(m.get("best_bsr"))} ·
         {esc(m.get("entrenched_titles", 0))} entrenched title(s) with 500+ reviews</p>
      <p><strong>What readers complain about:</strong> {esc(m.get("reader_complaints"))}</p>
      {f'<ul class="comps">{comps}</ul>' if comps else ""}
    </div>"""


def render_platform_finding(p):
    return f"""
    <div class="card platform-card">
      <h3>{esc(p.get("platform", ""))}</h3>
      <p><strong>High demand:</strong> {esc(p.get("high_demand", ""))}</p>
      <p><strong>Gap:</strong> {esc(p.get("gap", ""))}</p>
      <p><strong>Underserved angle:</strong> {esc(p.get("underserved_angle", ""))}</p>
    </div>"""


def render_stakeholder(s):
    url = s.get("evidence_url")
    link = f'<a href="{esc(url)}">source</a>' if url else ""
    return f"""
    <div class="card stakeholder-card">
      <h3>{esc(s.get("name", ""))} <span class="site-tag">{esc(s.get("type", ""))}</span></h3>
      <p><strong>Role:</strong> {esc(s.get("role", ""))}</p>
      <p><strong>Why they know what sells:</strong> {esc(s.get("why_they_know", ""))}</p>
      <div class="footer">{link}</div>
    </div>"""


def render_source_proposal(s):
    return (
        f'<li><strong>{esc(s.get("name", ""))}</strong> '
        f'<span class="site-tag">{esc(s.get("status", ""))}</span>'
        f'<br><span class="muted">{esc(s.get("why", ""))}</span></li>'
    )


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
      {f'<p><strong>Timing:</strong> {esc(c.get("timing"))}</p>' if c.get("timing") else ""}
      {f'<p><strong>Series potential:</strong> {esc(c.get("series_link"))}</p>' if c.get("series_link") else ""}
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
.pick-card { border-left:4px solid #1f6f9c; background:#f4faff; }
.platform-card { border-left:4px solid #8a4fae; }
.stakeholder-card { border-left:4px solid #9c6b1f; }
.rec-card { border:2px solid #2a2621; background:#fffdf7; }
.rec-card h3 { font-size:1.3rem; margin-top:.5rem; }
.verdict { display:inline-block; color:#fff; font-size:.75rem; font-weight:bold; text-transform:uppercase; letter-spacing:.05em; padding:.2rem .6rem; border-radius:4px; }
table.scorecard { width:100%; border-collapse:collapse; margin:.6rem 0; font-size:.88rem; }
table.scorecard td { border-top:1px solid #eee3d3; padding:.45rem .4rem; vertical-align:top; }
.sc-factor { font-weight:bold; width:6.5rem; }
.sc-grade { width:6rem; color:#b5651d; font-weight:bold; }
.steps { margin:.2rem 0 0 1.2rem; padding:0; font-size:.92rem; }
.market-card { border-left:4px solid #c08a1e; }
.comps { font-size:.85rem; padding-left:1.1rem; margin:.4rem 0 0; }
.comps a { color:#b5651d; }
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
    picks = brief.get("top_3_picks") or []
    platform_findings = brief.get("platform_findings") or []
    proposed_sources = brief.get("proposed_new_sources") or []
    stakeholders = brief.get("stakeholders") or []
    recommendation_section = render_recommendation(brief.get("recommendation"))
    market = brief.get("amazon_market") or []
    market_section = ""
    if market:
        market_section = f"""
    <section>
      <h2>Amazon Market Check</h2>
      <p class="muted">Best Seller Rank is Amazon's sales rank (lower sells more): under ~20,000 is roughly 10+ copies a day, over ~300,000 rarely sells.</p>
      {"".join(render_market(m) for m in market)}
    </section>"""
    # brief["repeat_check"] / history bookkeeping is deliberately NOT rendered:
    # the novelty check is internal (ledger.py), not something the reader needs.

    stakeholders_section = ""
    if stakeholders:
        stakeholders_section = f"""
    <section>
      <h2>Key Stakeholders</h2>
      <p class="muted">People and organizations with first-hand context on what's selling in these topics — worth following, pitching, or reaching out to.</p>
      {"".join(render_stakeholder(s) for s in stakeholders)}
    </section>"""

    picks_section = ""
    if picks:
        picks_section = f"""
    <section>
      <h2>Proposal: Top 3 Picks</h2>
      <p class="muted">Plain-language summary of the strongest options from the 5 book concepts below — read this section first.</p>
      {"".join(render_pick(i + 1, p) for i, p in enumerate(picks))}
    </section>"""

    platforms_section = ""
    if platform_findings:
        platforms_section = f"""
    <section>
      <h2>New Platforms Checked</h2>
      <p class="muted">Instagram, Facebook, Draft2Digital and other author/reader platforms, each broken into what's in high demand, what's missing, and a specific underserved angle.</p>
      {"".join(render_platform_finding(p) for p in platform_findings)}
    </section>"""

    proposed_sources_section = ""
    if proposed_sources:
        proposed_sources_section = f"""
    <section>
      <h2>Proposed New Sources for Future Runs</h2>
      <ul class="sources">{"".join(render_source_proposal(s) for s in proposed_sources)}</ul>
    </section>"""

    body = f"""
    <div class="wrap">
    <h1>Self-Help &amp; Non-Fiction Market Gap Report</h1>
    <div class="subtitle-line">{esc(run_date)} · Topics scanned: {esc(topics)}</div>
    {f'<div class="summary">{esc(summary)}</div>' if summary else ''}
    {recommendation_section}
    {picks_section}
    {market_section}

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
    {stakeholders_section}
    {platforms_section}
    {proposed_sources_section}
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
