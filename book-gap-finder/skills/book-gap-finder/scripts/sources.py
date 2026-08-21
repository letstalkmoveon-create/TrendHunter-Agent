"""
Data fetchers for book-gap-finder.

Fetch with code, mine with Claude: this file pulls raw items and does light
mechanical normalization only. It never judges whether something represents
a real pain point or market gap — that's Claude's job in the SKILL.md
workflow, reading the output this file produces.

Two families of sources:
  - YouTube (via Apify), which has real engagement numbers (views/likes/comments).
  - 12 book/review sites (via Firecrawl site-scoped search), which only return
    title/description/url from search snippets — no reliable engagement metric,
    so these are for landscape-mapping and market-gap evidence, not ranking.

Every normalized item has this shape:
    {
        "source": "youtube" | "goodreads" | "amazon" | ... (site key),
        "title": str,
        "description": str,
        "author": str | None,
        "url": str | None,
        "date": str | None,   # ISO 8601 if known (youtube only)
        "engagement": float,  # 0 for search-snippet sources; real number for youtube
    }
"""

import os
import re
import sys

try:
    import requests
except ImportError:
    sys.exit("Missing dependency 'requests'. Install it with:\n    pip install requests")

APIFY_BASE = "https://api.apify.com/v2"
FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"
REQUEST_TIMEOUT = 30

# Domain map for the 12 book/review sites named in the brief.
BOOKSTORE_SITES = {
    "goodreads": "goodreads.com",
    "lulu": "lulu.com",
    "applebooks": "books.apple.com",
    "amazon": "amazon.com",
    "barnesandnoble": "barnesandnoble.com",
    "indigo": "indigo.ca",
    "powells": "powells.com",
    "bookshop": "bookshop.org",
    "thriftbooks": "thriftbooks.com",
    "abebooks": "abebooks.com",
    "alibris": "alibris.com",
    "bookdepot": "bookdepot.com",
}


class ConfigError(Exception):
    """Raised when a required credential is missing, with a fix-it message."""


def _require_env(name, help_text):
    val = os.environ.get(name)
    if not val:
        raise ConfigError(f"Missing environment variable {name}. {help_text}")
    return val


def _pick(d, keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


# ---------------------------------------------------------------------------
# YouTube — Apify streamers/youtube-scraper (same actor scroll-stoppers uses)
# ---------------------------------------------------------------------------

def fetch_youtube(query, limit=15, timeframe="month"):
    token = _require_env(
        "APIFY_API_TOKEN",
        "Get a free token at https://console.apify.com/settings/integrations",
    )
    url = f"{APIFY_BASE}/acts/streamers~youtube-scraper/run-sync-get-dataset-items"
    run_input = {"searchKeywords": query, "maxResults": limit, "dateFilter": timeframe}
    try:
        resp = requests.post(url, params={"token": token}, json=run_input, timeout=180)
        if resp.status_code == 401:
            raise ConfigError("APIFY_API_TOKEN was rejected (401). Double-check the token value.")
        resp.raise_for_status()
        raw = resp.json()
    except requests.RequestException as e:
        return [], [f"youtube: Apify run failed ({e})"]

    items = []
    for d in raw:
        views = _pick(d, ["viewCount", "numberOfViews", "views"], 0) or 0
        likes = _pick(d, ["likes", "likeCount"], 0) or 0
        comments = _pick(d, ["commentsCount", "commentCount"], 0) or 0
        items.append({
            "source": "youtube",
            "title": _pick(d, ["title"], ""),
            "description": _pick(d, ["text", "description"], ""),
            "author": _pick(d, ["channelName", "channelUsername"], None),
            "url": _pick(d, ["url", "videoUrl"], None),
            "date": _pick(d, ["date", "uploadDate", "publishedAt"], None),
            "engagement": float(views) + float(likes) + float(comments) * 2,
        })
    return items, []


# ---------------------------------------------------------------------------
# Book/review sites — Firecrawl site-scoped search (no free APIs exist for these)
# ---------------------------------------------------------------------------

def fetch_site(site_key, domain, query, limit=8):
    key = _require_env(
        "FIRECRAWL_API_KEY",
        "Get one from your Firecrawl dashboard at https://www.firecrawl.dev (Settings/API Keys).",
    )
    try:
        resp = requests.post(
            FIRECRAWL_SEARCH_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={"query": f"site:{domain} {query}", "limit": limit},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 401:
            raise ConfigError("FIRECRAWL_API_KEY was rejected (401). Double-check the key value.")
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return [], [f"{site_key}: Firecrawl search failed ({e})"]

    items = []
    for item in data.get("data", {}).get("web", []):
        items.append({
            "source": site_key,
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "author": None,
            "url": item.get("url"),
            "date": None,
            "engagement": 0,
        })
    return items, []


def fetch_bookstores(query, sites=None, limit_per_site=8):
    """
    Query every site in `sites` (defaults to all 12 BOOKSTORE_SITES).
    Returns (items_by_site, errors) — items_by_site is {site_key: [items]}
    so the caller can see landscape breadth per site, not just a merged pile.
    """
    targets = sites or BOOKSTORE_SITES
    items_by_site = {}
    errors = []
    for site_key, domain in targets.items():
        items, errs = fetch_site(site_key, domain, query, limit=limit_per_site)
        items_by_site[site_key] = items
        errors.extend(errs)
    return items_by_site, errors


# ---------------------------------------------------------------------------
# Mechanical topic-frequency signal (counting, not interpreting)
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "how",
    "your", "you", "is", "are", "book", "books", "guide", "best", "top", "new",
    "self", "help", "self-help", "non-fiction", "nonfiction", "review", "reviews",
    "buy", "shop", "price", "list", "2025", "2026",
}


def topic_frequency(all_items, min_count=2, top_n=25):
    """
    Count how often significant words/bigrams repeat across titles+descriptions,
    tagged with which sources they appeared in. A term repeating across many
    independent sites is a mechanical demand signal worth surfacing to Claude —
    it is not itself a claim about what the demand means.
    """
    counts = {}
    for item in all_items:
        text = f"{item.get('title', '')} {item.get('description', '')}".lower()
        words = re.findall(r"[a-z][a-z\-]{2,}", text)
        words = [w for w in words if w not in _STOPWORDS]
        grams = list(words) + [f"{a} {b}" for a, b in zip(words, words[1:])]
        seen_in_item = set(grams)
        for g in seen_in_item:
            entry = counts.setdefault(g, {"count": 0, "sources": set()})
            entry["count"] += 1
            entry["sources"].add(item.get("source", "unknown"))

    ranked = [
        {"term": term, "count": v["count"], "sources": sorted(v["sources"])}
        for term, v in counts.items()
        if v["count"] >= min_count and len(v["sources"]) > 1
    ]
    ranked.sort(key=lambda x: (-x["count"], -len(x["sources"])))
    return ranked[:top_n]
