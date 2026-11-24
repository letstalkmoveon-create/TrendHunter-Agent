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
import re
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


def _pub_year(s):
    m = re.search(r"(\d{4})", s or "")
    return int(m.group(1)) if m else None


def amazon_market_score(books, now=None):
    """Demand-vs-competition read for one topic's top Amazon results.

    Thresholds are rules of thumb used by KDP authors, not exact sales figures:
    an overall Books BSR under ~20k is roughly 10+ copies/day, under ~100k
    roughly 1+/day; 500+ reviews marks an entrenched title.
    """
    now = now or datetime.now(timezone.utc)
    books = [b for b in books if b.get("on_topic", True)]
    ranked = [b for b in books if isinstance(b.get("bsr"), int)]
    bsrs = sorted(b["bsr"] for b in ranked)
    if not bsrs:
        return {"verdict": "no data", "books_checked": len(books)}
    median = bsrs[len(bsrs) // 2]
    selling = sum(1 for r in bsrs if r <= 20000)
    entrenched = sum(1 for b in books if (b.get("reviews") or 0) >= 500)
    recent_winners = sum(1 for b in ranked
                         if b["bsr"] <= 100000 and (_pub_year(b.get("publication_date")) or 0) >= now.year - 2)
    if median > 150000 and selling == 0:
        verdict = "weak demand"
    elif entrenched >= 7:
        verdict = "saturated"
    elif selling >= 2 and entrenched <= 4 and recent_winners >= 1:
        verdict = "winnable"
    else:
        verdict = "contested"
    return {
        "verdict": verdict,
        "books_checked": len(books),
        "median_bsr": median,
        "best_bsr": bsrs[0],
        "titles_bsr_under_20k": selling,
        "titles_with_500plus_reviews": entrenched,
        "recent_titles_bsr_under_100k": recent_winners,
    }


def category_openings(books, top_n=3):
    """Sub-categories where a modest seller still ranks top-20.

    For each Amazon sub-category an on-topic book sits in, find the weakest
    overall sales rank (highest BSR) that still places top-20 there. The higher
    that number, the easier it is for a new book to rank and earn visibility.
    """
    best = {}
    for b in books:
        if not b.get("on_topic", True) or not isinstance(b.get("bsr"), int):
            continue
        for cr in b.get("category_ranks") or []:
            cat, pos = cr.get("category"), cr.get("rank")
            if not cat or not isinstance(pos, int) or pos > 20:
                continue
            cur = best.get(cat)
            if cur is None or b["bsr"] > cur["overall_rank_needed"]:
                best[cat] = {"category": cat, "category_position": pos,
                             "overall_rank_needed": b["bsr"], "example_title": b.get("title"),
                             "example_url": b.get("url")}
    return sorted(best.values(), key=lambda x: -x["overall_rank_needed"])[:top_n]
