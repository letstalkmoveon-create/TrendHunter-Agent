"""
Ranking for scroll-stoppers.

Engagement scales are wildly different across platforms (a TikTok can pull
millions of plays, a Reddit thread a few thousand upvotes), so items are
ranked on a log10 scale to make them comparable. Age is attached to every
item so a two-year-old monster post doesn't get mistaken for something
trending now. Sort is engagement first, recency second — this file does
not interpret content, it only normalizes magnitude and orders it.
"""

import math
from datetime import datetime, timezone


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        # Handle both "...Z" and "+00:00" style ISO strings.
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


def rank(items, now=None):
    """
    Attach age_days and engagement_log to every item, then sort by
    (engagement_log desc, age_days asc). Items with unknown age sort last
    within their engagement bucket rather than being treated as fresh.
    """
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


def platform_counts(items):
    counts = {}
    for item in items:
        p = item.get("platform", "unknown")
        counts[p] = counts.get(p, 0) + 1
    return counts


def build_report(niche, items, errors, now=None):
    now = now or datetime.now(timezone.utc)
    ranked_items = rank(items, now=now)
    return {
        "niche": niche,
        "generated_at": now.isoformat(),
        "platform_counts": platform_counts(ranked_items),
        "item_count": len(ranked_items),
        "items": ranked_items,
        "errors": errors,
    }
