#!/usr/bin/env python3
"""
Renders a mined brief.json into a self-contained HTML dashboard.

brief.json schema (written by Claude, see SKILL.md):
{
  "niche": str,
  "generated_at": str,
  "summary": str,
  "hooks":        [{"text": str, "platform": str, "engagement": num, "url": str, "why_it_works": str}],
  "pain_points":  [{"quote": str, "platform": str, "url": str, "cross_platform": bool}],
  "desires":      [{"quote": str, "platform": str, "url": str}],
  "objections":   [{"quote": str, "platform": str, "url": str}],
  "formats":      [{"name": str, "description": str, "example_url": str}],
  "phrase_bank":  [str],
  "make_next":    [{"idea": str, "format": str, "angle": str, "based_on_urls": [str]}]
}

Every list is optional — missing sections are simply not rendered.
"""

import argparse
import html
import json
import sys
from pathlib import Path

PLATFORM_COLORS = {
    "reddit": "#ff4500",
    "youtube": "#ff0000",
    "tiktok": "#010101",
    "instagram": "#c13584",
}


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def platform_badge(platform):
    color = PLATFORM_COLORS.get((platform or "").lower(), "#555")
    return f'<span class="badge" style="background:{color}">{esc(platform)}</span>'


def render_hook_card(h):
    url = h.get("url")
    text = esc(h.get("text", ""))
    link = f'<a href="{esc(url)}" target="_blank" rel="noopener">source ↗</a>' if url else ""
    why = f'<p class="why">{esc(h.get("why_it_works", ""))}</p>' if h.get("why_it_works") else ""
    eng = h.get("engagement")
    eng_str = f'<span class="eng">{eng:,.0f} engagement</span>' if isinstance(eng, (int, float)) else ""
    return f"""
    <div class="card hook-card">
      {platform_badge(h.get("platform"))}
      <p class="hook-text">"{text}"</p>
      {why}
      <div class="card-footer">{eng_str}{link}</div>
    </div>"""


def render_quote_card(q, cls):
    url = q.get("url")
    link = f'<a href="{esc(url)}" target="_blank" rel="noopener">source ↗</a>' if url else ""
    cross = '<span class="cross-badge">validated on 2+ platforms</span>' if q.get("cross_platform") else ""
    return f"""
    <div class="card {cls}-card">
      {platform_badge(q.get("platform"))}
      <p class="quote-text">"{esc(q.get("quote", ""))}"</p>
      <div class="card-footer">{cross}{link}</div>
    </div>"""


def render_format_card(f):
    ex = f.get("example_url")
    link = f'<a href="{esc(ex)}" target="_blank" rel="noopener">example ↗</a>' if ex else ""
    return f"""
    <div class="card format-card">
      <h4>{esc(f.get("name", ""))}</h4>
      <p>{esc(f.get("description", ""))}</p>
      <div class="card-footer">{link}</div>
    </div>"""


def render_make_next_card(m):
    urls = m.get("based_on_urls") or []
    links = " · ".join(f'<a href="{esc(u)}" target="_blank" rel="noopener">source ↗</a>' for u in urls)
    return f"""
    <div class="card next-card">
      <h4>{esc(m.get("idea", ""))}</h4>
      <p><strong>Format:</strong> {esc(m.get("format", ""))}</p>
      <p><strong>Angle:</strong> {esc(m.get("angle", ""))}</p>
      <div class="card-footer">{links}</div>
    </div>"""


def render_section(title, items, render_fn, empty_note=None):
    if not items:
        if empty_note:
            return f'<section><h2>{esc(title)}</h2><p class="empty">{esc(empty_note)}</p></section>'
        return ""
    cards = "".join(render_fn(i) for i in items)
    return f'<section><h2>{esc(title)}</h2><div class="grid">{cards}</div></section>'


def render_phrase_bank(phrases):
    if not phrases:
        return ""
    chips = "".join(f'<span class="phrase-chip">{esc(p)}</span>' for p in phrases)
    return f'<section><h2>Phrase Bank</h2><div class="phrase-bank">{chips}</div></section>'


CSS = """
:root {
  --bg: #0f1115; --card-bg: #191c22; --text: #e8e8ea; --muted: #9a9aa2;
  --accent: #ffd447; --border: #2a2d35;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem clamp(1rem, 4vw, 3rem);
  background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.5;
}
header { margin-bottom: 2.5rem; }
h1 { font-size: 1.8rem; margin: 0 0 .25rem; }
.subtitle { color: var(--muted); font-size: .9rem; }
.summary { max-width: 70ch; margin-top: 1rem; font-size: 1.05rem; }
section { margin-bottom: 2.5rem; }
h2 { font-size: 1.1rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); border-bottom: 1px solid var(--border); padding-bottom: .5rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; margin-top: 1rem; }
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 1rem; }
.badge { display: inline-block; font-size: .7rem; font-weight: 600; text-transform: uppercase; color: #fff; padding: .15rem .5rem; border-radius: 999px; margin-bottom: .6rem; }
.hook-text, .quote-text { font-size: 1rem; font-style: italic; margin: 0 0 .5rem; }
.why { color: var(--muted); font-size: .85rem; margin: 0 0 .5rem; }
.card-footer { display: flex; gap: .75rem; align-items: center; font-size: .8rem; color: var(--muted); margin-top: .5rem; }
.card-footer a { color: var(--accent); text-decoration: none; }
.card-footer a:hover { text-decoration: underline; }
.cross-badge { background: #1f3a2a; color: #6fd68a; padding: .1rem .5rem; border-radius: 6px; font-weight: 600; }
.format-card h4, .next-card h4 { margin: 0 0 .4rem; }
.next-card { border-color: var(--accent); }
.phrase-bank { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: 1rem; }
.phrase-chip { background: var(--card-bg); border: 1px solid var(--border); border-radius: 999px; padding: .35rem .8rem; font-size: .85rem; }
.empty { color: var(--muted); font-style: italic; }
"""


def render_html(brief):
    niche = brief.get("niche", "")
    generated_at = brief.get("generated_at", "")
    summary = brief.get("summary", "")

    body = f"""
    <header>
      <h1>Scroll Stoppers: {esc(niche)}</h1>
      <div class="subtitle">Generated {esc(generated_at)}</div>
      {f'<p class="summary">{esc(summary)}</p>' if summary else ''}
    </header>
    {render_section("Hooks", brief.get("hooks"), render_hook_card, "No hooks mined yet.")}
    {render_section("Pain Points", brief.get("pain_points"), lambda q: render_quote_card(q, "pain"))}
    {render_section("Desires", brief.get("desires"), lambda q: render_quote_card(q, "desire"))}
    {render_section("Objections", brief.get("objections"), lambda q: render_quote_card(q, "objection"))}
    {render_section("Winning Formats", brief.get("formats"), render_format_card)}
    {render_phrase_bank(brief.get("phrase_bank"))}
    {render_section("Make This Next", brief.get("make_next"), render_make_next_card)}
    """

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Scroll Stoppers: {esc(niche)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>"""


def main(argv=None):
    p = argparse.ArgumentParser(description="Render a mined brief.json into a self-contained HTML dashboard.")
    p.add_argument("--brief", required=True, help="Path to brief.json")
    p.add_argument("--output", default=None, help="Path to write dashboard.html (default: alongside brief.json)")
    args = p.parse_args(argv)

    brief_path = Path(args.brief)
    if not brief_path.exists():
        sys.exit(f"Brief file not found: {brief_path}")
    brief = json.loads(brief_path.read_text(encoding="utf-8"))

    output_path = Path(args.output) if args.output else brief_path.parent / "dashboard.html"
    output_path.write_text(render_html(brief), encoding="utf-8")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
