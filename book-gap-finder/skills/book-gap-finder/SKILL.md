---
name: book-gap-finder
description: Researches the self-help and non-fiction book market across
  YouTube, Goodreads, and 10 other bookstore/review sites to find underserved
  pain points and market gaps, then proposes book concepts, titles, angles,
  and a differentiated table of contents. Runs on a Monday/Wednesday schedule
  and emails the report. Use when the user wants book market research,
  content-gap analysis for non-fiction/self-help publishing, or a fresh
  round of book concept ideas.
---

# Book Gap Finder

Fetch with code, mine with Claude. `scripts/sources.py` and `scripts/analyze.py`
only pull raw search results and count things (word frequency, engagement
numbers) — they never judge whether something is a real pain point or a real
gap. That judgment is entirely yours, applied to the data they produce.

## Prerequisites

- `APIFY_API_TOKEN` — for YouTube (via Apify's `streamers/youtube-scraper`).
- `FIRECRAWL_API_KEY` — for all 12 book/review sites (none of them have a free
  public API; Goodreads' was shut down years ago and Amazon's requires an
  approved affiliate account, so this goes through Firecrawl site-scoped
  search instead).
- `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` — for sending the report. The app
  password comes from https://myaccount.google.com/apppasswords (requires
  2-Step Verification on the account) — it is not the account's real password.
- Python's `requests` package (`pip install requests`).

If any of these are missing, say so plainly and either wait for the user to
set them or run whatever partial pipeline still works (e.g. skip email and
just produce the HTML report).

## Audience context (use this to judge what's worth surfacing)

This research serves people writing/publishing for: self-development seekers,
growth-mindset audiences, entrepreneurs and small business owners, single
individuals, couples, healthy eaters, people managing mental health, people
wanting a mindset shift or seeking change generally, real estate investors,
homeowners, and general non-fiction readers. A pain point or gap only counts
if it's plausibly relevant to at least one of these groups — don't force-fit
unrelated topics just because a search returned them.

## Workflow

### 1. Resolve topics

Pick 3-6 specific search topics for this run — not the whole audience list
verbatim, but concrete phrases people would actually search or that would
appear in book titles (e.g. "growth mindset habits," "real estate investor
mindset," "couples communication," "healthy eating for busy parents,"
"anxiety coping skills," "starting over after divorce"). Vary the topics
between runs so coverage broadens over time rather than repeating the same
scan twice a week. Use your own judgment on what's timely — you don't need
to ask the user unless this is the very first run and there's no prior
context to build on.

### 2. Fan out

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/book-gap-finder/scripts/book_gap_finder.py" \
  --topics "growth mindset habits,real estate investor mindset,couples communication" \
  --output-dir "./.book-gap-finder/$(date +%Y-%m-%d)"
```

This hits YouTube plus all 12 book/review sites (Goodreads, Lulu, Apple
Books, Amazon, Barnes & Noble, Indigo, Powell's, Bookshop.org, ThriftBooks,
AbeBooks, Alibris, Book Depot) for every topic, ranks YouTube results by
log-scaled engagement, organizes the book-site results by site (they only
have search-snippet data, so they're not ranked by a number — you rank them
by reading), and computes a cross-site term-frequency signal to help spot
what repeats across independent sources. Writes `ranked.json` and prints a
summary to stderr, path to stdout. Takes a few minutes depending on topic
count.

Useful flags: `--max-results` (YouTube cap per topic), `--per-site-results`
(bookstore cap per topic per site), `--sites` (restrict to specific site
keys), `--skip` (skip specific sources).

### 3. Rank and mine

Read `ranked.json`. Apply this three-part methodology (adapted from the pain-
point/market-gap research framework this skill is built on) to everything you
read — YouTube titles/descriptions, book-site search results, and the
`topic_frequency` list:

**Part 1 — Map the existing landscape.** From the book-site results, identify
the products/books currently serving each topic: what do they promise, what
price tier, what's the "standard package" every competitor offers, who are
the recognizable authors/publishers dominating it.

**Part 2 — Identify unaddressed pain points.** For each topic, work out: what
pain points existing books attempt to solve but leave customers still
complaining about (look for repeated phrasing across sites — that's the
`topic_frequency` signal earning its keep); what pain points no book seems to
address at all; what new problems show up only after someone's already tried
the existing solutions; and what sub-segments of the audience the mainstream
titles ignore entirely.

**Part 3 — Prioritize.** Rank the gaps you found by how strong an opportunity
each represents: how intense and common the pain is, how weak the existing
competition's answer is, and how clearly it maps to one of this skill's
target audience segments.

**Never fabricate a quote, title, or number** — everything must trace back to
an item in `ranked.json` with its URL kept for citation. **Avoid plagiarism,
copyright infringement, and clichéd/AI-sounding phrasing** — titles, angles,
and chapter names should read like they came from an editor who actually
knows this market, not a template.

### 4. Write the brief

Write `brief.json` next to `ranked.json` with this exact shape — the counts
are fixed requirements, not suggestions:

```json
{
  "run_date": "2026-08-24",
  "topics_scanned": ["growth mindset habits", "..."],
  "summary": "2-3 sentences on the strongest opportunity this run surfaced.",
  "trends": [
    {"title": "...", "description": "...", "evidence_urls": ["..."]}
  ],
  "book_concepts": [
    {"title": "...", "subtitle": "...", "target_audience": "...",
     "core_promise": "...", "market_gap": "...", "evidence_urls": ["..."]}
  ],
  "angles": [
    {"name": "...", "description": "...", "why_it_sells": "...",
     "market_gap_addressed": "..."}
  ],
  "table_of_contents": [
    {"chapter": 1, "title": "...", "description": "..."}
  ],
  "differentiation_notes": "How this TOC differs from what's already on shelves, specifically — name what existing books do instead.",
  "sources_consulted": [
    {"site": "goodreads", "title": "...", "url": "..."}
  ]
}
```

Requirements: exactly **5** `trends`, exactly **5** `book_concepts` (each with
a title AND subtitle), exactly **2** `angles`, exactly **15** chapters in
`table_of_contents`. Every `book_concept.market_gap` should point at a
specific Part 2 finding, not a generic claim. The table of contents must be
meaningfully different from the existing books you mapped in Part 1 — if
you can't articulate how it differs, keep revising it until you can, and say
so explicitly in `differentiation_notes`. `sources_consulted` should include
every meaningfully-cited link from `ranked.json`, not just the top handful —
this list is the audit trail the user asked for.

### 5. Render and send

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/book-gap-finder/scripts/render.py" \
  --brief "./.book-gap-finder/$(date +%Y-%m-%d)/brief.json"
```

Then email it — recipients and cadence are fixed by standing instruction, not
something to ask about each run:

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/book-gap-finder/scripts/send_email.py" \
  --to "felixngalla@yahoo.com,firstcallh@gmail.com" \
  --subject "Book Gap Report — $(date +%Y-%m-%d)" \
  --html "./.book-gap-finder/$(date +%Y-%m-%d)/report.html"
```

This runs on a Monday/Wednesday cloud schedule with no human review in the
loop before sending — which is exactly why steps 3-4's sourcing discipline
(never fabricate, cite everything) matters more here than in a skill someone
reviews before sharing.

## Notes

- Every script path must go through `${CLAUDE_PLUGIN_ROOT}` once installed as
  a plugin — the working directory becomes the user's project, not this
  plugin's folder.
- If `FIRECRAWL_API_KEY` or `APIFY_API_TOKEN` is missing, don't silently skip
  half the sources and send a report that looks complete — either wait for
  the credential or clearly flag in the email which sources were unavailable
  this run.
- If a run turns up genuinely nothing new worth reporting, say that plainly
  in the summary rather than padding out weak trends/concepts to hit the
  counts artificially.
