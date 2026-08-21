"""
Ranking/organization for book-gap-finder.

YouTube items get real engagement numbers, so they're log-scaled and ranked
the same way scroll-stoppers does. Bookstore/review-site items only have
search-snippet data (no engagement metric available), so they're organized
by site instead of ranked, plus a cross-site topic-frequency signal is
computed mechanically. None of this interprets what any of it *means* —
that synthesis is Claude's job per the SKILL.md workflow.
"""

import math
from datetime import datetime, timezone

import sources


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_days(date_str, now):
    dt = _parse_date(date_str)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 86400.0


def rank_youtube(items, now=None):
    now = now or datetime.now(timezone.utc)
    ranked = []
    for item in items:
        engagement = float(item.get("engagement", 0) or 0)
        age = _age_days(item.get("date"), now)
        enriched = dict(item)
        enriched["engagement_log"] = round(math.log10(engagement + 1), 2)
        enriched["age_days"] = round(age, 1) if age is not None else None
        ranked.append(enriched)
    ranked.sort(
        key=lambda x: (
            -round(x["engagement_log"], 1),
            x["age_days"] if x["age_days"] is not None else float("inf"),
        )
    )
    return ranked


def build_report(niche, youtube_items, bookstore_items_by_site, errors, now=None):
    now = now or datetime.now(timezone.utc)
    ranked_youtube = rank_youtube(youtube_items, now=now)

    all_bookstore_items = [i for items in bookstore_items_by_site.values() for i in items]
    topics = sources.topic_frequency(ranked_youtube + all_bookstore_items)

    site_counts = {site: len(items) for site, items in bookstore_items_by_site.items()}

    return {
        "niche": niche,
        "generated_at": now.isoformat(),
        "youtube": ranked_youtube,
        "bookstores": bookstore_items_by_site,
        "site_counts": site_counts,
        "topic_frequency": topics,
        "errors": errors,
    }
