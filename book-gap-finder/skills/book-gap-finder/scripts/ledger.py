#!/usr/bin/env python3
"""
Running tally of every prior Book Gap Finder run, so each run can deliver
information that's new compared to all the previous ones.

Why a git branch: cloud runs start from a fresh clone every time, so a
gitignored local file (the old .book-gap-finder/topics_history.json) never
survives from one Monday to the next. The ledger lives as ledger.json on a
dedicated `research-history` branch instead — each run pulls it, uses it,
appends its own record, and pushes it back. Code on `main` is never touched.

Subcommands (all mechanical — judging what's genuinely new stays with Claude):
  pull       fetch ledger.json from origin/research-history (empty ledger if none)
  summary    print every prior topic, trend, concept, angle and stakeholder
  mark-seen  flag every ranked.json item whose URL appeared in a prior run
  check      compare a draft brief.json against the ledger; exit 1 on repeats
  append     add this run's brief.json to the ledger (replaces same run_date)
  push       commit ledger.json to the research-history branch and push it

Ledger shape:
{"runs": [{"run_date", "topics", "summary", "trend_titles", "concepts":
  [{"title","subtitle"}], "angles", "stakeholders": [{"name","type"}],
  "source_urls"}]}
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BRANCH = "research-history"
LEDGER_FILE = "ledger.json"
STOP = {"the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "after", "your", "how"}


def _git(*args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def _load(path):
    p = Path(path)
    if not p.exists():
        return {"runs": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _save(path, ledger):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")


def _norm_url(u):
    if not u:
        return ""
    u = u.strip().lower().split("#")[0]
    u = re.sub(r"[?&](srsltid|utm_[a-z]+|itscg|itsct|mttnsubad)=[^&]*", "", u)
    return u.rstrip("/?&").replace("://www.", "://")


def _tokens(s):
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in STOP}


def _similar(a, b, threshold=0.6):
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


# ---------------------------------------------------------------------------

def cmd_pull(args):
    out = args.out
    try:
        _git("fetch", "origin", BRANCH)
        res = _git("show", f"origin/{BRANCH}:{LEDGER_FILE}")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(res.stdout, encoding="utf-8")
        n = len(json.loads(res.stdout).get("runs", []))
        print(f"Pulled ledger with {n} prior run(s) -> {out}", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"WARNING: could not read origin/{BRANCH}:{LEDGER_FILE} ({e.stderr.strip()}). "
              "Starting from an empty ledger — say so in the final run report, since this "
              "run can't be checked against prior research.", file=sys.stderr)
        _save(out, {"runs": []})
    print(out)


# The 12 audience segments the report serves, with keywords used to classify
# older runs that predate the explicit "segments" field.
SEGMENTS = {
    "self-development": ["self", "habit", "discipline", "procrastinat", "productiv", "purpose"],
    "growth mindset": ["mindset", "growth", "resilien", "confidence", "imposter"],
    "adults / life transitions": ["midlife", "retire", "empty nest", "caregiver", "aging", "downsiz", "over 50", "over 40"],
    "entrepreneurs": ["entrepreneur", "founder", "startup", "solopreneur", "side hustle", "creator"],
    "small business owners": ["small business", "business owner", "one-person"],
    "singles": ["dating", "single", "divorce", "breakup", "after 40"],
    "couples": ["couple", "marriage", "relationship", "partner", "blended", "stepfamily"],
    "healthy eaters": ["meal", "eating", "nutrition", "diet", "weight", "food", "menopause"],
    "mental health": ["anxiety", "burnout", "depress", "stress", "trauma", "emotional", "overthink", "lonel"],
    "change seekers / new mindset": ["reinvent", "starting over", "career change", "new chapter", "change"],
    "real estate investors": ["real estate", "landlord", "rental", "investor", "property", "flip"],
    "homeowners": ["homebuyer", "home buyer", "homeowner", "mortgage", "house"],
}


def _segments_for(run):
    if run.get("segments"):
        return run["segments"]
    text = " ".join(run.get("topics", [])).lower()
    return [seg for seg, kws in SEGMENTS.items() if any(k in text for k in kws)]


def cmd_summary(args):
    runs = _load(args.ledger).get("runs", [])
    if not runs:
        print("No prior runs in ledger.")
        return
    urls = set()
    print(f"{len(runs)} prior run(s):\n")
    for r in sorted(runs, key=lambda r: r.get("run_date", "")):
        urls.update(_norm_url(u) for u in r.get("source_urls", []))
        print(f"== {r.get('run_date')} ==")
        print("  topics:   " + "; ".join(r.get("topics", [])))
        if r.get("trend_titles"):
            print("  trends:   " + "; ".join(r["trend_titles"]))
        if r.get("concepts"):
            print("  concepts: " + "; ".join(
                f"{c.get('title')}" + (f" — {c['subtitle']}" if c.get("subtitle") else "")
                for c in r["concepts"]))
        if r.get("angles"):
            print("  angles:   " + "; ".join(r["angles"]))
        if r.get("stakeholders"):
            print("  stakeholders: " + "; ".join(f"{s.get('name')} ({s.get('type')})" for s in r["stakeholders"]))
    print(f"\n{len(urls)} distinct source URLs cited across all prior runs "
          "(run mark-seen to flag them in this run's ranked.json).")

    counts = {seg: 0 for seg in SEGMENTS}
    last = {seg: "" for seg in SEGMENTS}
    for r in runs:
        for seg in _segments_for(r):
            if seg in counts:
                counts[seg] += 1
                last[seg] = max(last[seg], r.get("run_date", ""))
    print("\nAudience-segment coverage (least covered first — favor the top of this list):")
    for seg in sorted(SEGMENTS, key=lambda g: (counts[g], last[g])):
        print(f"  {counts[seg]:>2} run(s)  last {last[seg] or 'never':<10}  {seg}")

    concepts = [(r.get("run_date"), c.get("title")) for r in runs for c in r.get("concepts", [])]
    if concepts:
        print("\nPrior book concepts available for series links (title, first proposed):")
        for d, t in sorted(concepts, key=lambda x: x[1] or ""):
            print(f"  {t}  ({d})")


def cmd_mark_seen(args):
    seen = set()
    for r in _load(args.ledger).get("runs", []):
        seen.update(_norm_url(u) for u in r.get("source_urls", []))
    data = json.loads(Path(args.ranked).read_text(encoding="utf-8"))
    new = old = 0

    def walk(node):
        nonlocal new, old
        if isinstance(node, dict):
            if "url" in node and "source" in node:
                flag = _norm_url(node.get("url")) in seen
                node["seen_before"] = flag
                old += flag
                new += not flag
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    Path(args.ranked).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{new} item(s) never cited before, {old} already cited in a prior run "
          "(marked seen_before: true in ranked.json).")


def cmd_check(args):
    runs = _load(args.ledger).get("runs", [])
    brief = json.loads(Path(args.brief).read_text(encoding="utf-8"))
    problems = []

    def against(kind, items, prior_getter, threshold):
        for item in items:
            for r in runs:
                if r.get("run_date") == brief.get("run_date"):
                    continue
                for prior in prior_getter(r):
                    if _similar(item, prior, threshold):
                        problems.append(f"{kind} '{item}' ~ '{prior}' ({r.get('run_date')})")

    against("topic", brief.get("topics_scanned", []), lambda r: r.get("topics", []), 0.6)
    against("concept title", [c.get("title", "") for c in brief.get("book_concepts", [])],
            lambda r: [c.get("title", "") for c in r.get("concepts", [])], 0.5)
    against("trend", [t.get("title", "") for t in brief.get("trends", [])],
            lambda r: r.get("trend_titles", []), 0.6)

    if problems:
        print("Overlap with prior research — revise these before sending:")
        for p in problems:
            print("  - " + p)
        sys.exit(1)
    print(f"No overlap with {len(runs)} prior run(s).")


def _record(brief):
    urls = []
    for s in brief.get("sources_consulted", []):
        urls.append(s.get("url"))
    for key in ("trends", "book_concepts"):
        for t in brief.get(key, []):
            urls.extend(t.get("evidence_urls", []))
    return {
        "run_date": brief.get("run_date"),
        "topics": brief.get("topics_scanned", []),
        "summary": brief.get("summary", ""),
        "segments": brief.get("segments", []),
        "recommended": (brief.get("recommendation") or {}).get("title", ""),
        "trend_titles": [t.get("title", "") for t in brief.get("trends", [])],
        "concepts": [{"title": c.get("title", ""), "subtitle": c.get("subtitle", "")}
                     for c in brief.get("book_concepts", [])],
        "angles": [a.get("name", "") for a in brief.get("angles", [])],
        "stakeholders": [{"name": s.get("name", ""), "type": s.get("type", "")}
                         for s in brief.get("stakeholders", [])],
        "source_urls": sorted({u for u in urls if u}),
    }


def cmd_append(args):
    ledger = _load(args.ledger)
    brief = json.loads(Path(args.brief).read_text(encoding="utf-8"))
    rec = _record(brief)
    ledger["runs"] = [r for r in ledger.get("runs", []) if r.get("run_date") != rec["run_date"]]
    ledger["runs"].append(rec)
    ledger["runs"].sort(key=lambda r: r.get("run_date", ""))
    _save(args.ledger, ledger)
    print(f"Ledger now holds {len(ledger['runs'])} run(s).")


def cmd_push(args):
    ledger_path = Path(args.ledger).resolve()
    run_date = _load(ledger_path)["runs"][-1].get("run_date", "") if _load(ledger_path)["runs"] else ""
    tmp = Path(tempfile.mkdtemp(prefix="ledger-"))
    wt = tmp / "wt"
    ident = ["-c", "user.name=Book Gap Finder", "-c", "user.email=book-gap-finder@users.noreply.github.com"]
    try:
        has_remote = _git("ls-remote", "--heads", "origin", BRANCH).stdout.strip() != ""
        if has_remote:
            _git("fetch", "origin", BRANCH)
            _git("worktree", "add", "--detach", str(wt), f"origin/{BRANCH}")
        else:
            _git("worktree", "add", "--detach", str(wt))
            _git("checkout", "--orphan", "tmp-ledger", cwd=wt)
            _git("rm", "-rf", "--quiet", ".", cwd=wt, check=False)
        shutil.copyfile(ledger_path, wt / LEDGER_FILE)
        _git("add", LEDGER_FILE, cwd=wt)
        if _git("diff", "--cached", "--quiet", cwd=wt, check=False).returncode == 0:
            print("Ledger unchanged; nothing to push.")
            return
        subprocess.run(["git", *ident, "commit", "-m", f"Ledger: add run {run_date}"],
                       cwd=wt, check=True, capture_output=True, text=True)
        _git("push", "origin", f"HEAD:refs/heads/{BRANCH}", cwd=wt)
        print(f"Pushed ledger to origin/{BRANCH}.")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: ledger push failed: {e.stderr.strip() or e}. This run's research was NOT "
              "recorded — say so in the final run report.", file=sys.stderr)
        sys.exit(1)
    finally:
        _git("worktree", "remove", "--force", str(wt), check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    p = argparse.ArgumentParser(description="Running tally of prior Book Gap Finder research.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pull"); s.add_argument("--out", default="./.book-gap-finder/ledger.json"); s.set_defaults(fn=cmd_pull)
    s = sub.add_parser("summary"); s.add_argument("--ledger", required=True); s.set_defaults(fn=cmd_summary)
    s = sub.add_parser("mark-seen"); s.add_argument("--ledger", required=True); s.add_argument("--ranked", required=True); s.set_defaults(fn=cmd_mark_seen)
    s = sub.add_parser("check"); s.add_argument("--ledger", required=True); s.add_argument("--brief", required=True); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("append"); s.add_argument("--ledger", required=True); s.add_argument("--brief", required=True); s.set_defaults(fn=cmd_append)
    s = sub.add_parser("push"); s.add_argument("--ledger", required=True); s.set_defaults(fn=cmd_push)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
