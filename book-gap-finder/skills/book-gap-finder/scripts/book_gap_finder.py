#!/usr/bin/env python3
"""
Orchestrator for book-gap-finder.

Fetches YouTube plus 12 book/review sites across one or more resolved topics,
ranks/organizes the results, and writes ranked.json. Does not interpret the
content — that's Claude's job per SKILL.md, reading ranked.json to write
brief.json (the actual trends/titles/angles/TOC report).

Usage:
    python book_gap_finder.py \
        --topics "growth mindset habits,real estate investor mindset,couples communication" \
        --output-dir "./.book-gap-finder/2026-08-24"
"""

import argparse
import json
import sys
import time
from pathlib import Path

import analyze
import sources
from sources import ConfigError, BOOKSTORE_SITES


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Scan YouTube + book/review sites for self-help/non-fiction market gaps.")
    p.add_argument("--topics", required=True, help="Comma-separated search topics/keywords to scan this run.")
    p.add_argument("--output-dir", default="./.book-gap-finder", help="Directory to write ranked.json into.")
    p.add_argument("--max-results", type=int, default=15, help="Per-topic YouTube result cap.")
    p.add_argument("--per-site-results", type=int, default=6, help="Per-topic, per-bookstore-site result cap.")
    p.add_argument("--timeframe", default="month", choices=["hour", "today", "week", "month", "year"],
                    help="Recency window for YouTube search.")
    p.add_argument("--sites", default="", help="Comma-separated site keys to limit to (default: all 12).")
    p.add_argument("--skip", default="", help="Comma-separated sources to skip, e.g. 'youtube' or a site key.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    topics = [t.strip() for t in args.topics.split(",") if t.strip()]
    if not topics:
        sys.exit("--topics must contain at least one non-empty topic")

    skip = {s.strip().lower() for s in args.skip.split(",") if s.strip()}
    site_filter = [s.strip().lower() for s in args.sites.split(",") if s.strip()]
    sites = {k: v for k, v in BOOKSTORE_SITES.items() if not site_filter or k in site_filter}

    all_youtube = []
    all_bookstore_by_site = {k: [] for k in sites}
    all_errors = []

    print(f"Scanning {len(topics)} topic(s) across YouTube + {len(sites)} book/review sites...", file=sys.stderr)

    for topic in topics:
        print(f"  topic: {topic}", file=sys.stderr)

        if "youtube" not in skip:
            try:
                items, errors = sources.fetch_youtube(topic, limit=args.max_results, timeframe=args.timeframe)
                for i in items:
                    i["topic"] = topic
                all_youtube.extend(items)
                all_errors.extend(errors)
                print(f"    youtube: {len(items)} items", file=sys.stderr)
            except ConfigError as e:
                all_errors.append(f"youtube: {e}")
                print(f"    youtube: SKIPPED — {e}", file=sys.stderr)

        for site_key, domain in sites.items():
            if site_key in skip:
                all_errors.append(f"{site_key}: skipped by --skip flag")
                continue
            try:
                items, errors = sources.fetch_site(site_key, domain, topic, limit=args.per_site_results)
                for i in items:
                    i["topic"] = topic
                all_bookstore_by_site[site_key].extend(items)
                all_errors.extend(errors)
            except ConfigError as e:
                all_errors.append(f"{site_key}: {e}")
                print(f"    {site_key}: SKIPPED — {e}", file=sys.stderr)
            time.sleep(1.2)  # Firecrawl rate-limits back-to-back searches; space them out
        print(f"    bookstores: {sum(len(v) for v in all_bookstore_by_site.values())} total items so far", file=sys.stderr)

    report = analyze.build_report(
        niche=" | ".join(topics),
        youtube_items=all_youtube,
        bookstore_items_by_site=all_bookstore_by_site,
        errors=all_errors,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ranked_path = output_dir / "ranked.json"
    ranked_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    total_bookstore_items = sum(len(v) for v in report["bookstores"].values())
    print(f"\nWrote {len(report['youtube'])} YouTube items + {total_bookstore_items} bookstore items to {ranked_path}", file=sys.stderr)
    print(f"Site breakdown: {report['site_counts']}", file=sys.stderr)
    if report["topic_frequency"]:
        top_terms = ", ".join(f"{t['term']} ({t['count']}x, {len(t['sources'])} sources)" for t in report["topic_frequency"][:8])
        print(f"Top cross-site terms: {top_terms}", file=sys.stderr)
    if report["errors"]:
        print("Notes/errors:", file=sys.stderr)
        for e in report["errors"]:
            print(f"  - {e}", file=sys.stderr)

    print(str(ranked_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
