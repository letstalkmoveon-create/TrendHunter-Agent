"""
Platform fetchers for scroll-stoppers.

Fetch with code, mine with Claude: everything in this file pulls raw items
and normalizes their shape. None of it tries to interpret or rank content
by quality — that judgment lives in the SKILL.md workflow, applied by
Claude after analyze.py has ranked the normalized output.

Every normalized item has this shape:
    {
        "platform": "reddit" | "youtube" | "tiktok" | "instagram",
        "text": str,        # caption / title / body used as the "hook"
        "author": str | None,
        "url": str | None,
        "date": str | None, # ISO 8601 if known
        "engagement": float,# raw engagement number, platform-specific formula
        "meta": dict,       # platform-specific extra fields, kept for context
    }
"""

import os
import sys

try:
    import requests
except ImportError:
    sys.exit(
        "Missing dependency 'requests'. Install it with:\n"
        "    pip install requests"
    )

APIFY_BASE = "https://api.apify.com/v2"
REDDIT_HEADERS = {"User-Agent": "scroll-stoppers/0.1 (content research tool)"}
REQUEST_TIMEOUT = 30


class ConfigError(Exception):
    """Raised when a required credential is missing, with a fix-it message."""


class SourceError(Exception):
    """Raised when a source fetch fails after retries/fallbacks are exhausted."""


def _require_env(name, help_text):
    val = os.environ.get(name)
    if not val:
        raise ConfigError(f"Missing environment variable {name}. {help_text}")
    return val


def _pick(d, keys, default=None):
    """Return the first present, non-None value among candidate keys."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


# ---------------------------------------------------------------------------
# Reddit — free public JSON API, no key required.
# ---------------------------------------------------------------------------

def fetch_reddit(query, subreddits=None, limit=25, timeframe="month"):
    """
    Search reddit.com/r/{sub}/search.json for `query`.
    Falls back to a Firecrawl site:reddit.com search if reddit rate-limits us
    and FIRECRAWL_API_KEY is set; otherwise that subreddit is silently skipped
    and the skip is recorded by the caller via the returned `errors` list.
    """
    targets = subreddits or ["all"]
    items = []
    errors = []

    for sub in targets:
        sub = sub.strip().lstrip("r/").lstrip("/")
        url = f"https://www.reddit.com/r/{sub}/search.json"
        params = {
            "q": query,
            "sort": "top",
            "t": timeframe,
            "limit": limit,
            "restrict_sr": "on" if sub != "all" else "",
        }
        try:
            resp = requests.get(url, headers=REDDIT_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                fb_items, fb_err = _reddit_via_firecrawl(query, sub)
                items.extend(fb_items)
                if fb_err:
                    errors.append(fb_err)
                continue
            resp.raise_for_status()
            data = resp.json()
            for child in data.get("data", {}).get("children", []):
                d = child.get("data", {})
                score = d.get("score", 0) or 0
                num_comments = d.get("num_comments", 0) or 0
                created = d.get("created_utc")
                items.append({
                    "platform": "reddit",
                    "text": d.get("title", ""),
                    "author": d.get("author"),
                    "url": "https://www.reddit.com" + d.get("permalink", ""),
                    "date": _epoch_to_iso(created),
                    "engagement": score + num_comments,
                    "meta": {
                        "subreddit": d.get("subreddit"),
                        "score": score,
                        "num_comments": num_comments,
                        "selftext": d.get("selftext", ""),
                    },
                })
        except requests.RequestException as e:
            fb_items, fb_err = _reddit_via_firecrawl(query, sub)
            items.extend(fb_items)
            if fb_items:
                errors.append(f"reddit: r/{sub} was blocked ({e}); recovered {len(fb_items)} item(s) via Firecrawl fallback")
            else:
                errors.append(fb_err or f"reddit: r/{sub} failed ({e}); no Firecrawl fallback available")

    return items, errors


def _reddit_via_firecrawl(query, sub):
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return [], f"reddit: r/{sub} was rate-limited and FIRECRAWL_API_KEY is not set, so it was skipped"
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v2/search",
            headers={"Authorization": f"Bearer {key}"},
            json={"query": f"site:reddit.com/r/{sub} {query}", "limit": 10},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        out = []
        for item in data.get("data", {}).get("web", []):
            out.append({
                "platform": "reddit",
                "text": item.get("title", ""),
                "author": None,
                "url": item.get("url"),
                "date": None,
                "engagement": 0,
                "meta": {"source": "firecrawl_fallback", "description": item.get("description", "")},
            })
        return out, None
    except requests.RequestException as e:
        return [], f"reddit: r/{sub} Firecrawl fallback also failed ({e})"


def _epoch_to_iso(epoch):
    if not epoch:
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Apify-backed sources: YouTube, TikTok, Instagram
# ---------------------------------------------------------------------------

def _apify_run(actor_id, run_input, timeout=180):
    token = _require_env(
        "APIFY_API_TOKEN",
        "Get a free token at https://console.apify.com/settings/integrations "
        "(free tier includes enough monthly credit to test this skill).",
    )
    url = f"{APIFY_BASE}/acts/{actor_id.replace('/', '~')}/run-sync-get-dataset-items"
    resp = requests.post(url, params={"token": token}, json=run_input, timeout=timeout)
    if resp.status_code == 401:
        raise ConfigError("APIFY_API_TOKEN was rejected (401). Double-check the token value.")
    resp.raise_for_status()
    return resp.json()


def fetch_youtube(query, limit=25, timeframe="month"):
    """Apify actor streamers/youtube-scraper."""
    run_input = {
        "searchKeywords": query,
        "maxResults": limit,
        "dateFilter": timeframe,
    }
    try:
        raw = _apify_run("streamers/youtube-scraper", run_input)
    except ConfigError:
        raise
    except requests.RequestException as e:
        return [], [f"youtube: Apify run failed ({e})"]

    items = []
    for d in raw:
        views = _pick(d, ["viewCount", "numberOfViews", "views"], 0) or 0
        likes = _pick(d, ["likes", "likeCount"], 0) or 0
        comments = _pick(d, ["commentsCount", "commentCount"], 0) or 0
        items.append({
            "platform": "youtube",
            "text": _pick(d, ["title"], ""),
            "author": _pick(d, ["channelName", "channelUsername"], None),
            "url": _pick(d, ["url", "videoUrl"], None),
            "date": _pick(d, ["date", "uploadDate", "publishedAt"], None),
            "engagement": float(views) + float(likes) + float(comments) * 2,
            "meta": {
                "views": views,
                "likes": likes,
                "comments": comments,
                "description": _pick(d, ["text", "description"], ""),
            },
        })
    return items, []


def fetch_tiktok(query, limit=25):
    """Apify actor clockworks/tiktok-scraper."""
    run_input = {
        "searchQueries": [query],
        "resultsPerPage": limit,
        "searchSection": "",
    }
    try:
        raw = _apify_run("clockworks/tiktok-scraper", run_input)
    except ConfigError:
        raise
    except requests.RequestException as e:
        return [], [f"tiktok: Apify run failed ({e})"]

    items = []
    for d in raw:
        plays = _pick(d, ["playCount"], 0) or 0
        likes = _pick(d, ["diggCount", "likesCount"], 0) or 0
        comments = _pick(d, ["commentCount", "commentsCount"], 0) or 0
        shares = _pick(d, ["shareCount"], 0) or 0
        author_meta = d.get("authorMeta") or {}
        items.append({
            "platform": "tiktok",
            "text": _pick(d, ["text", "desc"], ""),
            "author": author_meta.get("name") or _pick(d, ["authorName"], None),
            "url": _pick(d, ["webVideoUrl", "url"], None),
            "date": _pick(d, ["createTimeISO"], None),
            "engagement": float(plays) + float(likes) + float(comments) * 2 + float(shares) * 3,
            "meta": {"plays": plays, "likes": likes, "comments": comments, "shares": shares},
        })
    return items, []


def fetch_instagram(niche_keywords, creators, limit_per_creator=15):
    """
    Apify actor apify/instagram-reel-scraper, fed with creator handles
    (NOT hashtags — hashtag scrapers return low-engagement brand spam per
    the tutorial's lesson #1).

    A lightweight caption-relevance filter drops reels that don't mention
    any niche keyword, so an off-topic viral reel from a resolved creator
    doesn't pollute the brief.
    """
    if not creators:
        return [], ["instagram: skipped — no creator handles were provided (resolve 5-8 niche creators first)"]

    run_input = {
        "username": creators,
        "resultsLimit": limit_per_creator,
    }
    try:
        raw = _apify_run("apify/instagram-reel-scraper", run_input)
    except ConfigError:
        raise
    except requests.RequestException as e:
        return [], [f"instagram: Apify run failed ({e})"]

    keywords = [k.lower() for k in niche_keywords if k.strip()]
    items = []
    dropped = 0
    for d in raw:
        caption = _pick(d, ["caption", "text"], "") or ""
        if keywords and not any(kw in caption.lower() for kw in keywords):
            dropped += 1
            continue
        likes = _pick(d, ["likesCount", "likes"], 0) or 0
        comments = _pick(d, ["commentsCount", "comments"], 0) or 0
        plays = _pick(d, ["videoPlayCount", "playsCount", "viewCount"], 0) or 0
        items.append({
            "platform": "instagram",
            "text": caption,
            "author": _pick(d, ["ownerUsername", "username"], None),
            "url": _pick(d, ["url"], None),
            "date": _pick(d, ["timestamp"], None),
            "engagement": float(plays) + float(likes) + float(comments) * 2,
            "meta": {"plays": plays, "likes": likes, "comments": comments},
        })

    errors = []
    if dropped:
        errors.append(f"instagram: dropped {dropped} off-topic reel(s) via caption-relevance filter")
    return items, errors
