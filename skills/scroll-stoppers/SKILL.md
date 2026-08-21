---
name: scroll-stoppers
description: Mines the hooks, angles, and exact customer language getting
  engagement across Reddit, YouTube, TikTok, and Instagram Reels, then writes a
  content brief telling you what to make next. Use when the user wants content
  ideas, hooks, ad angles, or research for a niche/product.
---

# Scroll Stoppers

Fetch with code, mine with Claude. `scripts/sources.py` and `scripts/analyze.py`
never try to interpret content — they only pull raw items and rank them by
engagement. All the creative judgment (what's actually a hook, what pain is
real, what's worth making next) is your job, applied to the ranked data.

## Prerequisites

Check these before running anything, and tell the user exactly what's missing
if they're not set:

- `APIFY_API_TOKEN` — required for YouTube, TikTok, and Instagram (all three
  run through Apify). Free tier at https://console.apify.com/settings/integrations
  has enough monthly credit to test this.
- `FIRECRAWL_API_KEY` — optional. Only used as a fallback when Reddit's public
  JSON endpoint gets rate-limited. Skip it if not set; Reddit still mostly works
  without it.
- Reddit needs no key at all.
- Python's `requests` package must be installed (`pip install requests`).

If `APIFY_API_TOKEN` is missing, tell the user and either wait for them to set
it or run with `--skip youtube,tiktok,instagram` to get a Reddit-only pass.

## Workflow

### 1. Resolve targets (this step needs your judgment, not the script)

From the user's niche/product request:

- Pick 2-4 relevant subreddits (no `r/` prefix). If you're not sure, `all` is
  an acceptable default — the script falls back to `r/all` when none are given.
- Resolve 5-8 real Instagram creator handles who actually post in this niche.
  **Do not use hashtags for Instagram** — hashtag scrapers return low-engagement
  brand spam. Handles that post real content in the niche give reels with real
  view counts. If you don't know specific handles, say so and skip Instagram
  for this run rather than guessing at handles that don't exist.

### 2. Run the engine

Invoke with the full plugin-relative path so it resolves correctly once this
skill is installed (the working directory after install is the user's project,
not the plugin folder):

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/scroll-stoppers/scripts/scroll_stoppers.py" \
  --niche "cold plunge tubs" \
  --subreddits coldplunge,biohackers \
  --creators icebarrel,coldplungecoach,thecoldplungeco \
  --output-dir "./.scroll-stoppers/cold-plunge-tubs"
```

This takes about 2-3 minutes. It prints a per-platform item count, any
errors/skips (e.g. missing creator handles, rate limits), and the top 5 items
by engagement to stderr, then prints the path to `ranked.json` on stdout.

Useful flags:
- `--max-results N` — per-platform cap (default 25)
- `--timeframe {hour,today,week,month,year}` — recency window for Reddit/YouTube (default month)
- `--skip reddit,youtube,tiktok,instagram` — comma list of platforms to skip

### 3. Mine `ranked.json` into `brief.json`

Read `ranked.json`. Each item has `platform`, `text`, `author`, `url`, `date`,
`age_days`, `engagement`, `engagement_log`, and `meta`. Items are already
sorted by engagement (log-scaled) first, recency second — but sorted isn't
mined. Read as a creative strategist, not a summarizer:

- **Hooks** — the literal opening line/title/caption that stopped the scroll.
- **Pain points** — problems in the customer's exact words. Don't sanitize them.
- **Desires** — the outcome they say they want.
- **Objections** — what makes them hesitate.
- **Formats** — the content structures that are winning.
- **Phrase bank** — copy-paste voice-of-customer lines for ads/emails.

**Never fabricate.** Every hook, quote, and number must trace back to an item
in `ranked.json` (keep the `url`). When the same pain point shows up on two or
more platforms independently, that's a validated angle, not a one-off — mark
it `"cross_platform": true`.

Write `brief.json` next to `ranked.json` with this shape (every list is
optional — omit sections you found nothing for rather than padding them):

```json
{
  "niche": "cold plunge tubs",
  "generated_at": "2026-08-20T12:00:00Z",
  "summary": "1-3 sentences on the overall content opportunity here.",
  "hooks": [
    {"text": "...", "platform": "tiktok", "engagement": 125000, "url": "...", "why_it_works": "..."}
  ],
  "pain_points": [
    {"quote": "...", "platform": "reddit", "url": "...", "cross_platform": true}
  ],
  "desires": [{"quote": "...", "platform": "youtube", "url": "..."}],
  "objections": [{"quote": "...", "platform": "instagram", "url": "..."}],
  "formats": [{"name": "...", "description": "...", "example_url": "..."}],
  "phrase_bank": ["exact phrase one", "exact phrase two"],
  "make_next": [
    {"idea": "...", "format": "...", "angle": "...", "based_on_urls": ["...", "..."]}
  ]
}
```

### 4. Render the dashboard

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/scroll-stoppers/scripts/render.py" \
  --brief "./.scroll-stoppers/cold-plunge-tubs/brief.json"
```

Writes `dashboard.html` next to `brief.json` — a single self-contained file
(inline CSS, no external dependencies) with platform-colored hook cards, pain
quotes, a phrase bank, and "make this next" cards. Opens in any browser.

### 5. Hand it back

Summarize the top 3-5 findings in chat (don't just say "done, see the file") and
point to the dashboard path so the user can open it. If entire platforms were
skipped (missing token, no creators resolved, rate-limited with no Firecrawl
fallback), say so plainly rather than presenting a partial brief as complete.

## Notes

- Every script path must go through `${CLAUDE_PLUGIN_ROOT}` once this is
  installed as a plugin — relative paths break because the working directory
  becomes the user's project, not this plugin's folder.
- Reddit is free — the public JSON API works without a key. Don't reach for
  Firecrawl or Apify for Reddit; it's only a fallback for rate limits.
- If the user just says "find scroll stoppers for X" or "what should I make
  about X", that's enough to run the full workflow above end to end.
