#!/usr/bin/env python3
"""Backfill social distribution for pages that were published but never queued.

Why this exists
---------------
scripts/authority_v4_autopilot.py used to enqueue social distribution with
`published[:LINKEDIN_DAILY_LIMIT]` and `x_pool[:X_DAILY_LIMIT]`. Because x_pool
was built item-outer/template-inner, all five X slots went to published[0]. The
result: exactly one page a day entered the queue, and 428 of 474 published pages
never entered it on any platform. The enqueue bug is fixed; this script recovers
the pages that were dropped while it was live.

Design choices
--------------
- One LinkedIn entry and one X entry per page, not the five X template variants
  the daily path uses. Five near-identical posts about a months-old page is
  spam; one is distribution.
- Idempotent: a page that already has an entry for a platform is skipped, so
  re-running never duplicates. Safe to run repeatedly.
- Daily platform rate limits are NOT touched. scripts/social_publisher.py drains
  this queue at its declared rate and leaves the remainder queued_for_auto_post,
  so backfilled items are deferred, never dropped.
- --write is required. Default is a dry run that reports what it would add.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANTRY = json.loads((ROOT / "content-bank/yearly-pantry.json").read_text(encoding="utf-8"))
QUEUE = ROOT / "data/social-queue.json"
REGISTRY = ROOT / "data/link-registry.json"

LI_TEMPLATE = "A useful resource does not need to pretend every answer is universal. {title} — built as a decision aid, not a fake ranking."
X_TEMPLATE = "Useful citation, not fake ranking: {title}."


def load(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def title_for(path: Path) -> str:
    try:
        html = (ROOT / path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    for tag in ("<h1>", "<title>"):
        start = html.find(tag)
        if start == -1:
            continue
        start += len(tag)
        end = html.find("</", start)
        if end != -1:
            return " ".join(html[start:end].split()).split(" | ")[0].strip()
    return ""


def publication_for(source_path: str):
    for key, pub in PANTRY["publications"].items():
        if source_path.startswith(pub["site_path"]):
            return key, pub
    return None, None


def main() -> int:
    write = "--write" in sys.argv
    queue = load(QUEUE, [])
    if isinstance(queue, dict):
        queue = queue.get("items", [])
    registry = load(REGISTRY, [])
    if isinstance(registry, dict):
        registry = registry.get("links", [])

    have = {(i.get("source_path"), i.get("platform")) for i in queue}
    seen, added, skipped_no_title = set(), [], 0

    for row in registry:
        source_path = row.get("source_path")
        if not source_path or source_path in seen:
            continue
        seen.add(source_path)
        key, pub = publication_for(source_path)
        if not pub:
            continue
        title = title_for(Path(source_path))
        if not title:
            skipped_no_title += 1
            continue
        import os
        domain = os.getenv(pub["domain_env"]) or pub["default_domain"]
        rel = str(Path(source_path).relative_to(pub["site_path"])).replace("index.html", "")
        source_url = f"https://{domain}/{rel}"
        for platform, tmpl in (("linkedin", LI_TEMPLATE), ("x", X_TEMPLATE)):
            if (source_path, platform) in have:
                continue
            added.append({
                "date": row.get("date"),
                "scheduled_content_date": row.get("scheduled_content_date") or row.get("date"),
                "platform": platform,
                "status": "queued_for_auto_post",
                "body": tmpl.format(title=title),
                "source_path": source_path,
                "source_url": source_url,
                "post_type": f"backfill_authority_resource_note_{platform}",
            })

    result = {
        "mode": "write" if write else "dry-run",
        "registry_pages": len(seen),
        "already_queued_pairs": len(have),
        "entries_to_add": len(added),
        "pages_backfilled": len({a["source_path"] for a in added}),
        "skipped_no_title": skipped_no_title,
    }
    if write and added:
        QUEUE.write_text(json.dumps(queue + added, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
