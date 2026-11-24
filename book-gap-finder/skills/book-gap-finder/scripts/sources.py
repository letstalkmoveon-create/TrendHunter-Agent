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
import time

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

# Tier 1 — confirmed via Firecrawl site-scoped search (2026-11-23) to return
# real, non-fabricated results through the same fetch_site() mechanism as
# BOOKSTORE_SITES. Included by default alongside the 12 bookstore sites
# because they surface a different signal the bookstore search snippets
# can't: unprompted reader pain-point language (reddit, quora, facebook
# groups), social discovery/marketing trends (instagram, tiktok), and what
# authors/publishers are actively producing or pushing next (draft2digital,
# bookbub, netgalley, reedsy) rather than just what's already shelved.
AUTHOR_PLATFORM_SITES = {
    "reddit": "reddit.com",
    "quora": "quora.com",
    "facebook": "facebook.com",
    "instagram": "instagram.com",
    "tiktok": "tiktok.com",
    "draft2digital": "draft2digital.com",
    "bookbub": "bookbub.com",
    "netgalley": "netgalley.com",
    "reedsy": "reedsy.com",
}

# Tier 2 — also confirmed working, but lower reader-demand signal density
# (more author-craft/forum chatter and industry-trade content than direct
# pain-point or purchase-intent signal). Not run by default; pass their
# keys via --sites to include them for a deeper, slower pass.
EXTENDED_SITES = {
    "pinterest": "pinterest.com",
    "medium": "medium.com",
    "smashwords": "smashwords.com",
    "writtenwordmedia": "writtenwordmedia.com",
    "kobowritinglife": "kobowritinglife.com",
    "kboards": "kboards.com",
    "absolutewrite": "absolutewrite.com",
    "ingramspark": "ingramspark.com",
}

# Stakeholder signal — run by default (added 2026-11-24). These are where the
# people who decide and track what becomes a bestseller show up by name:
# trade press (Publishers Weekly), deal announcements naming the literary agent,
# acquiring editor and imprint for each new self-help/non-fiction book
# (Publishers Marketplace), the NYT advice/how-to list, podcast episodes
# where authors/hosts drive category sales (Apple Podcasts), and the
# booksellers' trade association (ABA). Used to fill the brief's
# `stakeholders` section; only names that appear in these results may be used.
STAKEHOLDER_SITES = {
    "publishersweekly": "publishersweekly.com",
    "publishersmarketplace": "publishersmarketplace.com",
    "nytbestsellers": "nytimes.com/books",
    "applepodcasts": "podcasts.apple.com",
    "bookweb": "bookweb.org",
}

ALL_SITES = {**BOOKSTORE_SITES, **AUTHOR_PLATFORM_SITES, **EXTENDED_SITES, **STAKEHOLDER_SITES}


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
        return [], [f"youtube: Apify run failed ({_redact(e)})"]

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

def fetch_site(site_key, domain, query, limit=8, max_retries=3, retry_wait=20):
    """
    max_retries/retry_wait: on a 429, sleep retry_wait seconds and try again,
    up to max_retries times, before giving up. Added 2026-11-23 after runs
    with 21 sites across 3+ topics needed a manual backfill pass for sites
    that got rate-limited later in the run even at 2.0s between requests —
    this makes that recovery automatic instead of a separate script.
    """
    key = _require_env(
        "FIRECRAWL_API_KEY",
        "Get one from your Firecrawl dashboard at https://www.firecrawl.dev (Settings/API Keys).",
    )
    attempt = 0
    while True:
        try:
            resp = requests.post(
                FIRECRAWL_SEARCH_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={"query": f"site:{domain} {query}", "limit": limit},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 401:
                raise ConfigError("FIRECRAWL_API_KEY was rejected (401). Double-check the key value.")
            if resp.status_code == 429 and attempt < max_retries:
                attempt += 1
                time.sleep(retry_wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        except requests.RequestException as e:
            if attempt < max_retries:
                attempt += 1
                time.sleep(retry_wait)
                continue
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


# ---------------------------------------------------------------------------
# Amazon sales evidence — Apify junglee/amazon-crawler (same APIFY_API_TOKEN)
# Best Seller Rank, review counts, star breakdown, publication date and
# Amazon's own review summary for the top book results of each topic. This is
# what turns "people talk about it" into "people pay for it".
# ---------------------------------------------------------------------------

# Movers & Shakers isn't supported by the bestsellers actor (tested 2026-11-24).
AMAZON_SELF_HELP_LISTS = {
    "best_sellers": "https://www.amazon.com/Best-Sellers-Books-Self-Help/zgbs/books/4736",
    "new_releases": "https://www.amazon.com/gp/new-releases/books/4736",
}


def _redact(e):
    """Apify puts the token in the request URL; keep it out of error text."""
    return re.sub(r"token=[^&\s)]+", "token=REDACTED", str(e))


def _amazon_run(start_urls, max_items):
    token = _require_env(
        "APIFY_API_TOKEN",
        "Get a free token at https://console.apify.com/settings/integrations",
    )
    url = f"{APIFY_BASE}/acts/junglee~amazon-crawler/run-sync-get-dataset-items"
    run_input = {
        "categoryOrProductUrls": [{"url": u} for u in start_urls],
        "maxItemsPerStartUrl": max_items,
        "scrapeProductDetails": True,
    }
    resp = requests.post(url, params={"token": token}, json=run_input, timeout=300)
    if resp.status_code == 401:
        raise ConfigError("APIFY_API_TOKEN was rejected (401). Double-check the token value.")
    resp.raise_for_status()
    return resp.json()


def _amazon_item(d):
    ranks = d.get("bestsellerRanks") or []
    overall = next((r.get("rank") for r in ranks if (r.get("category") or "").startswith("Books")), None)
    if overall is None:
        overall = next((r.get("rank") for r in ranks if "Kindle Store" in (r.get("category") or "")), None)
    pub = next((a.get("value") for a in (d.get("attributes") or [])
                if (a.get("key") or "").lower().startswith("publication date")), None)
    ai = d.get("aiReviewsSummary") or {}
    complaints = [
        {"theme": k.get("name"), "sentiment": k.get("sentiment"), "text": k.get("text")}
        for k in (ai.get("keywords") or []) if (k.get("sentiment") or "").lower() in ("negative", "mixed")
    ]
    price = d.get("price") or {}
    return {
        "source": "amazon_sales",
        "title": d.get("title") or "",
        "author": d.get("author"),
        "url": d.get("url"),
        "asin": d.get("asin"),
        "bsr": overall,
        "category_ranks": [{"rank": r.get("rank"), "category": r.get("category")} for r in ranks[1:4]],
        "reviews": d.get("reviewsCount") or 0,
        "stars": d.get("stars"),
        "stars_breakdown": d.get("starsBreakdown"),
        "price": price.get("value") if isinstance(price, dict) else price,
        "publication_date": pub,
        "review_summary": ai.get("text"),
        "review_complaints": complaints,
        "engagement": 0,
    }


def fetch_amazon(query, limit=10):
    """Top `limit` Amazon book results for `query`, with sales-rank evidence."""
    from urllib.parse import quote_plus
    # Department filters (i=stripbooks, rh=n:283155) make Amazon fall back to generic
    # bestsellers for many queries; a plain search with "book" appended stays on topic.
    search = f"https://www.amazon.com/s?k={quote_plus(query + ' book')}"
    try:
        raw = _amazon_run([search], limit)
    except requests.RequestException as e:
        return [], [f"amazon_sales: Apify run failed for '{query}' ({_redact(e)})"]
    items = [_amazon_item(d) for d in raw if isinstance(d, dict) and d.get("title")]
    # Amazon search pads results with loosely related bestsellers (coloring books
    # for "money anxiety"); flag them so the market score only uses on-topic books.
    stems = {w[:5] for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 3 and w not in _STOPWORDS}
    for i, d in zip(items, [d for d in raw if isinstance(d, dict) and d.get("title")]):
        text = " ".join(str(d.get(k) or "") for k in ("title", "bookDescription", "description")).lower()
        words = {w[:5] for w in re.findall(r"[a-z]+", text)}
        i["on_topic"] = len(stems & words) >= min(2, len(stems))
    return items, []


def fetch_amazon_lists(limit=20):
    """Self-Help Best Sellers and New Releases (top `limit` each) — what's
    selling right now and which new titles broke in, via junglee/amazon-bestsellers."""
    token = _require_env("APIFY_API_TOKEN", "Get a free token at https://console.apify.com/settings/integrations")
    url = f"{APIFY_BASE}/acts/junglee~amazon-bestsellers/run-sync-get-dataset-items"
    run_input = {"categoryUrls": list(AMAZON_SELF_HELP_LISTS.values()), "maxItemsPerStartUrl": limit}
    try:
        resp = requests.post(url, params={"token": token}, json=run_input, timeout=300)
        resp.raise_for_status()
        raw = resp.json()
    except requests.RequestException as e:
        return {}, [f"amazon_lists: Apify run failed ({_redact(e)})"]
    by_url = {v: k for k, v in AMAZON_SELF_HELP_LISTS.items()}
    out = {k: [] for k in AMAZON_SELF_HELP_LISTS}
    for d in raw:
        key = by_url.get(d.get("input"))
        if key and not d.get("error"):
            price = d.get("price") or {}
            out[key].append({
                "source": "amazon_" + key, "position": d.get("position"), "title": d.get("name") or "",
                "url": d.get("url"), "stars": d.get("stars"),
                "price": price.get("value") if isinstance(price, dict) else price,
            })
    return out, []
