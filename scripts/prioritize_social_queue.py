#!/usr/bin/env python3
"""Retire duplicate social posts so the queue drains value, not volume.

Why this exists
---------------
scripts/authority_v4_autopilot.py used to enqueue five X posts per published
page, one per template. All five carried the SAME source URL and the SAME
headline. They differed only by a canned lead-in and, on the Approval Prep
path, a trailing "[1]".."[5]" counter whose only function was to get past X's
duplicate-content rejection -- a marker that the output was known to be
duplicate at the time it was written.

Five posts to one URL are not five units of reach. They are one unit of reach
and four units of evidence that the account is automated, which is exactly the
signal both platforms' spam heuristics score. The enqueue site is now fixed to
one post per page per platform; this retires the copies already sitting in the
queue so the drain spends its limited daily budget on distinct pages.

What it does NOT touch
----------------------
- The first variant of each page. Every page keeps exactly one X entry.
- LinkedIn entries. There was never a fan-out there.
- draft_requires_human_approval items. Those are a human's decision, not this
  script's, and they are not postable in the first place.
- Anything already posted.

Retired items stay in the queue with status `not_for_posting` and a recorded
`retired_reason`, so the decision is auditable and reversible rather than a
silent delete.

A second, narrower case: two distinct published pages that happen to carry the
same title generate word-for-word identical bodies. Different URLs, same text.
The account still emits two identical notes, so the later page's entry is
retired for the same reason the fan-out is.

--check is the registered validator mode: it fails if any page has more than
one postable entry on a platform, or if two postable entries share a body, so
neither shape can creep back in. It fails hard if it examines zero queue
entries -- a guard that iterates an empty list and reports PASS is worse than
no guard, because the green receipt gets believed.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "data/social-queue.json"

POSTABLE = {"queued_for_auto_post", "approved_for_auto_post"}
RETIRED = "not_for_posting"
REASON_SAME_PAGE = (
    "duplicate_of_same_page_same_platform: five X variants shared one URL and one "
    "headline, differing only by lead-in and a [n] counter added to defeat "
    "duplicate-post rejection. One post per page per platform is kept."
)
REASON_SAME_BODY = (
    "duplicate_body_different_page: two published pages carry the same title, so "
    "their generated posts are word-for-word identical. Posting both is two "
    "near-identical notes from one account; the earlier page keeps the slot."
)


def load_queue():
    if not QUEUE.exists():
        return []
    data = json.loads(QUEUE.read_text(encoding="utf-8"))
    return data.get("items", []) if isinstance(data, dict) else data


def group_key(item):
    return (item.get("platform"), item.get("source_path") or item.get("source_url"))


def body_key(item):
    return (item.get("platform"), re.sub(r"\s+", " ", (item.get("body") or "").strip().lower()))


def duplicates(queue):
    """Postable entries that repeat an earlier one, by page or by body.

    Two independent ways the same post reaches the account twice:

      same page  five queued variants of one URL, the original fan-out.
      same body  two distinct pages that happen to share a title, so the
                 generated text is identical even though the URLs differ.

    Both are caught here. The first postable entry for a page, and the first
    for a given body, keep their slot; later ones are retired.
    """
    first_page, first_body = {}, {}
    dupes = {}
    for i, item in enumerate(queue):
        if item.get("status") not in POSTABLE:
            continue
        pkey, bkey = group_key(item), body_key(item)
        if pkey[1] is None:
            continue
        if pkey in first_page:
            dupes[i] = REASON_SAME_PAGE
            continue
        first_page[pkey] = i
        if bkey[1] and bkey in first_body:
            dupes[i] = REASON_SAME_BODY
            continue
        first_body[bkey] = i
    return dupes, first_page


def main() -> int:
    write = "--write" in sys.argv
    check = "--check" in sys.argv
    queue = load_queue()

    # Rule 0: never pass by examining nothing.
    if not queue:
        print(json.dumps({
            "validator": "social_queue_priority",
            "status": "FAIL",
            "hard_failures": 1,
            "entries_examined": 0,
            "detail": "data/social-queue.json is empty or missing; this examined zero "
                      "queue entries and cannot vouch for anything.",
        }, indent=2))
        return 1

    dupes, first_seen = duplicates(queue)

    if check:
        by_page = defaultdict(int)
        for i in dupes:
            by_page[group_key(queue[i])] += 1
        by_reason = defaultdict(int)
        for reason in dupes.values():
            by_reason[reason.split(":")[0]] += 1
        worst = sorted(by_page.items(), key=lambda kv: -kv[1])[:5]
        result = {
            "validator": "social_queue_priority",
            "status": "FAIL" if dupes else "PASS",
            "hard_failures": 1 if dupes else 0,
            "entries_examined": len(queue),
            "postable_pages": len(first_seen),
            "duplicate_postable_entries": len(dupes),
            "by_reason": dict(by_reason),
            "worst_offenders": [
                {"platform": k[0], "source": k[1], "extra_postable_entries": n}
                for k, n in worst
            ],
            "remedy": "python3 scripts/prioritize_social_queue.py --write",
        }
        print(json.dumps(result, indent=2))
        return 1 if dupes else 0

    retired = []
    for i, reason in dupes.items():
        item = queue[i]
        item["status"] = RETIRED
        item["retired_reason"] = reason
        retired.append({
            "platform": item.get("platform"),
            "post_type": item.get("post_type"),
            "source_path": item.get("source_path"),
            "reason": reason.split(":")[0],
        })

    by_platform = defaultdict(int)
    by_reason = defaultdict(int)
    for r in retired:
        by_platform[r["platform"]] += 1
        by_reason[r["reason"]] += 1

    result = {
        "mode": "write" if write else "dry-run",
        "entries_examined": len(queue),
        "postable_pages_kept": len(first_seen),
        "entries_retired": len(retired),
        "retired_by_platform": dict(by_platform),
        "retired_by_reason": dict(by_reason),
        "status": RETIRED,
    }
    if write and retired:
        QUEUE.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
