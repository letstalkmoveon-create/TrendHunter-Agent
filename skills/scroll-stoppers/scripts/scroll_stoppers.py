#!/usr/bin/env python3
"""
Orchestrator for scroll-stoppers.

Fetches Reddit, YouTube, TikTok, and Instagram for a niche, ranks the
results, and writes ranked.json. It does not interpret or mine the
content — that's Claude's job, reading ranked.json per the SKILL.md
workflow, and writing brief.json for render.py to turn into a dashboard.

Usage:
    python scroll_stoppers.py --niche "cold plunge tubs" \
        --subreddits coldplunge,biohackers \
        --creators icebarrel,coldplungecoach \
        --output-dir ./.scroll-stoppers/cold-plunge-tubs
"""

import argparse
import json
import sys
from pathlib import Path

import analyze
import sources
from sources import ConfigError


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Mine Reddit/YouTube/TikTok/Instagram for a niche.")
    p.add_argument("--niche", required=True, help="Niche or product, e.g. 'cold plunge tubs'")
    p.add_argument("--subreddits", default="", help="Comma-separated subreddit names (no r/). Defaults to r/all.")
    p.add_argument("--creators", default="", help="Comma-separated Instagram handles (no @). Required for Instagram results.")
    p.add_argument("--output-dir", default="./.scroll-stoppers", help="Directory to write ranked.json into.")
    p.add_argument("--max-results", type=int, default=25, help="Per-platform result cap (Reddit/YouTube/TikTok).")
    p.add_argument("--timeframe", default="month", choices=["hour", "today", "week", "month", "year"],
                    help="Recency window for Reddit and YouTube search.")
    p.add_argument("--skip", default="", help="Comma-separated platforms to skip, e.g. 'instagram'.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    niche = args.niche.strip()
    subreddits = [s.strip() for s in args.subreddits.split(",") if s.strip()]
    creators = [c.strip().lstrip("@") for c in args.creators.split(",") if c.strip()]
    skip = {s.strip().lower() for s in args.skip.split(",") if s.strip()}

    all_items = []
    all_errors = []

    def run_source(name, fn):
        if name in skip:
            all_errors.append(f"{name}: skipped by --skip flag")
            return
        try:
            items, errors = fn()
            all_items.extend(items)
            all_errors.extend(errors)
            print(f"  {name}: {len(items)} items", file=sys.stderr)
        except ConfigError as e:
            all_errors.append(f"{name}: {e}")
            print(f"  {name}: SKIPPED — {e}", file=sys.stderr)

    print(f"Mining '{niche}' across Reddit, YouTube, TikTok, Instagram...", file=sys.stderr)

    run_source("reddit", lambda: sources.fetch_reddit(
        niche, subreddits=subreddits or None, limit=args.max_results, timeframe=args.timeframe))
    run_source("youtube", lambda: sources.fetch_youtube(
        niche, limit=args.max_results, timeframe=args.timeframe))
    run_source("tiktok", lambda: sources.fetch_tiktok(
        niche, limit=args.max_results))
    run_source("instagram", lambda: sources.fetch_instagram(
        niche.split(), creators=creators, limit_per_creator=max(5, args.max_results // 2)))

    report = analyze.build_report(niche, all_items, all_errors)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ranked_path = output_dir / "ranked.json"
    ranked_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nWrote {report['item_count']} ranked items to {ranked_path}", file=sys.stderr)
    print(f"Platform breakdown: {report['platform_counts']}", file=sys.stderr)
    if report["errors"]:
        print("Notes/errors:", file=sys.stderr)
        for e in report["errors"]:
            print(f"  - {e}", file=sys.stderr)

    top = report["items"][:5]
    if top:
        print("\nTop 5 by engagement:", file=sys.stderr)
        for item in top:
            print(f"  [{item['platform']}] ({item['engagement']:.0f} engagement, {item['age_days']}d old) {item['text'][:80]}", file=sys.stderr)

    print(str(ranked_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
