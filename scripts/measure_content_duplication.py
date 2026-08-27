#!/usr/bin/env python3
"""Measure how much each page repeats another page, on <main> only.

Two consecutive daily pages on professionalresourcelibrary.com were measured at
0.727 vocabulary Jaccard with only 244 unique word types in a ~1,300-word page.
That is the failure mode of a template that re-rolls phrasing instead of saying
something different, and it is the reason a page can be long and still carry no
information a retriever would quote.

Sorensen-Dice over word bigrams of the <main> element, because:
  * <main> excludes the header, nav, breadcrumb and footer, which are supposed
    to be identical across a publication. Scoring whole documents would measure
    the chrome and hide the body.
  * Bigrams, not word sets, because two pages can share a vocabulary and still
    be written differently. Bigrams score phrasing, which is what duplication
    actually is.

Dice = 2|A n B| / (|A| + |B|), so 1.0 is identical phrasing and 0.0 shares no
two-word sequence.

    python3 scripts/measure_content_duplication.py
    python3 scripts/measure_content_duplication.py --threshold 0.80 --new-only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITES = ROOT / "sites"

MAIN_RE = re.compile(r"<main[^>]*>(.*?)</main>", re.I | re.S)
SCRIPT_STYLE_RE = re.compile(r"<(script|style|nav|footer)[^>]*>.*?</\1>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
WORD_RE = re.compile(r"[a-z0-9']+")


def main_text(html: str) -> str:
    match = MAIN_RE.search(html)
    body = match.group(1) if match else html
    body = SCRIPT_STYLE_RE.sub(" ", body)
    return " ".join(TAG_RE.sub(" ", body).split())


def bigrams(text: str) -> set[tuple[str, str]]:
    words = WORD_RE.findall(text.lower())
    return {(words[i], words[i + 1]) for i in range(len(words) - 1)}


def dice(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.80,
                        help="Pairs at or above this Dice score are reported as duplicates.")
    parser.add_argument("--only", default=None,
                        help="Only score pages whose path contains this substring, "
                             "each against every page in its own publication.")
    parser.add_argument("--json", dest="json_out", default="reports/content-duplication.json")
    args = parser.parse_args()

    pages: dict[str, list[tuple[str, set, int]]] = {}
    for path in sorted(SITES.rglob("*.html")):
        if path.name == "404.html":
            continue
        pub = path.relative_to(SITES).parts[0]
        text = main_text(path.read_text(encoding="utf-8", errors="ignore"))
        grams = bigrams(text)
        if len(grams) < 40:
            continue
        pages.setdefault(pub, []).append(
            (path.relative_to(ROOT).as_posix(), grams, len(WORD_RE.findall(text.lower()))))

    over: list[dict] = []
    summary = []
    for pub, rows in sorted(pages.items()):
        focus = [r for r in rows if args.only in r[0]] if args.only else rows
        worst = 0.0
        worst_pair = ("", "")
        scores: list[float] = []
        for i, (path_a, grams_a, _wa) in enumerate(focus):
            others = rows if args.only else rows[i + 1:]
            for path_b, grams_b, _wb in others:
                if path_a == path_b:
                    continue
                score = dice(grams_a, grams_b)
                scores.append(score)
                if score > worst:
                    worst, worst_pair = score, (path_a, path_b)
                if score >= args.threshold:
                    over.append({"publication": pub, "dice": round(score, 3),
                                 "a": path_a, "b": path_b})
        scores.sort()
        summary.append({
            "publication": pub,
            "pages_scored": len(focus),
            "pairs_compared": len(scores),
            "max_dice": round(worst, 3),
            "median_dice": round(scores[len(scores) // 2], 3) if scores else 0.0,
            "p95_dice": round(scores[int(len(scores) * 0.95)], 3) if scores else 0.0,
            "worst_pair": list(worst_pair),
            "pairs_at_or_over_threshold": sum(1 for s in scores if s >= args.threshold),
        })

    print(f"CONTENT DUPLICATION (Sorensen-Dice, <main> word bigrams, threshold {args.threshold})")
    for row in summary:
        print(f"\n  {row['publication']}: {row['pages_scored']} page(s), "
              f"{row['pairs_compared']} pair(s)")
        print(f"    median {row['median_dice']}   p95 {row['p95_dice']}   max {row['max_dice']}")
        print(f"    at/over {args.threshold}: {row['pairs_at_or_over_threshold']}")
        if row["worst_pair"][0]:
            print(f"    worst: {row['worst_pair'][0]}")
            print(f"           {row['worst_pair'][1]}")

    seen = set()
    unique_over = []
    for row in over:
        key = tuple(sorted((row["a"], row["b"])))
        if key not in seen:
            seen.add(key)
            unique_over.append(row)
    unique_over.sort(key=lambda r: -r["dice"])

    out = ROOT / args.json_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "schema_version": "1.0",
        "measurement": "sorensen-dice-main-bigrams",
        "threshold": args.threshold,
        "scope": args.only or "all",
        "summary": summary,
        "pairs_at_or_over_threshold": len(unique_over),
        "worst_offenders": unique_over[:50],
    }, indent=2) + "\n", encoding="utf-8")
    print(f"\n  wrote {args.json_out}")

    if unique_over:
        print(f"\nCONTENT DUPLICATION: {len(unique_over)} pair(s) at or over {args.threshold}")
        for row in unique_over[:10]:
            print(f"  {row['dice']}  {row['a']}\n         {row['b']}")
        return 1
    print("\nCONTENT DUPLICATION: no pair at or over threshold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
