#!/usr/bin/env python3
"""When the API will not post, hand the owner a sheet she can post from.

The problem this solves
-----------------------
On 2026-08-29 the X account answered every write with

    HTTP 402 {"detail":"credits depleted",
              "type":"https://api.x.com/2/problems/credits-depleted"}

on the FIRST request of the FIRST run, with no successful post anywhere in this
repository's history. That is not a quota this account spent; it is X's
pay-per-use billing saying the enrolled account has no credits to fulfil the
request. No posting rate gets under it - not eight a day, not one a month - and
no amount of waiting resets it. Only funding the developer account does.

Meanwhile 581 published pages sit in data/social-queue.json with nothing
carrying them anywhere. A lane that answers "the API refused, so I deferred
everything" is a lane that exits 0 having done nothing, every run, forever.

So when a platform cannot get a post out through its API, this writes the day's
highest-value posts out as a copy-paste sheet: the exact text the API would
have sent, the URL, and nothing to assemble. Distribution still happens; it
happens by hand, and it goes back to automatic the moment the API can post.

Two ways a platform lands here
------------------------------
An OUTAGE - the platform is switched on and refuses, or has no credentials, or
spent its whole daily budget on failed attempts. Drafting stops by itself the
moment a post succeeds.

A PAUSE FOR POSTING - the platform is switched off on purpose, with
`pause_mode: "draft_by_hand"` in data/social-brand-policy.json, precisely
because its API cannot be used. X is here as of 2026-08-29: the owner decided
not to fund X's pay-per-use API, so the publisher makes ZERO requests to it, and
this sheet is the whole distribution route until she funds it.

What must never land here is a platform paused DORMANT - `pause_mode:
"dormant"`, which is LinkedIn. That switch says nothing is wanted from the
platform at all, and drafting it would quietly reverse it.

What it must never do
---------------------
Consume the queue. Drafting reads data/social-queue.json and writes nothing to
it. The 581 entries keep their `queued_for_auto_post` status, their attempt
counts and their order, so restoring API access restores automatic posting with
no un-drafting pass. Everything this module knows lives in its own ledger.

Marking drafts as posted
------------------------
One edit, not one edit per row - the same shape as the LinkedIn pause switch.
The ledger carries a single field, `marked_posted_through`. Set it to the batch
id printed at the top of the sheet and EVERY draft in that batch and every
batch before it is done: they are never offered again, and the next run cuts a
fresh batch. Done-ness is DERIVED from that one declaration; no per-row status
is ever stamped, so there is nothing to hunt down and reverse.

While a batch is still open the sheet is re-rendered unchanged on every run.
That is deliberate: a run must not pile a second batch on top of one she has
not posted yet, because 581 drafts are as useless as none.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lib import social_platforms, social_selection  # noqa: E402

LEDGER_SCHEMA = "authority-social-draft-ledger-v1"

# How many drafts one batch may hold when the platform declares no daily limit.
# A day's worth, never a backlog dump.
DEFAULT_BATCH_SIZE = 8

HOW_TO_MARK_KEY = "HOW_TO_MARK_DRAFTS_AS_POSTED"
HOW_TO_MARK = (
    "Set \"marked_posted_through\" below to the batch id printed at the top of "
    "reports/social-drafts.md, and commit. That is the whole change. Every draft in "
    "that batch and in every batch before it is then done: it is never offered again, "
    "and the next scheduled run writes a fresh batch of the next highest-value posts. "
    "Done-ness is derived from this one field -- no draft is ever stamped row by row, "
    "so there is nothing to un-mark if you change your mind. Leaving it alone is also "
    "safe: an unposted batch is re-rendered unchanged rather than piled on top of."
)


def ledger_path_default(queue_path):
    """Beside the queue it describes.

    Deriving it means a fixture run pointed at a temporary queue writes its
    ledger to that temporary directory too, so tests and validators cannot
    write over the committed one.
    """
    return Path(queue_path).parent / "social-draft-ledger.json"


def drafts_path_default(report_path):
    return Path(report_path).parent / "social-drafts.md"


def empty_ledger():
    return {
        "schema": LEDGER_SCHEMA,
        "purpose": (
            "Drafts handed to a human because the platform API would not accept a post. "
            "Separate from data/social-queue.json on purpose: drafting never consumes, "
            "retires or reorders a queue entry, so restoring API access restores "
            "automatic posting with no un-drafting pass."
        ),
        HOW_TO_MARK_KEY: HOW_TO_MARK,
        "marked_posted_through": None,
        "batches": [],
    }


def read_ledger(path):
    p = Path(path)
    if not p.exists():
        return empty_ledger()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return empty_ledger()
    if not isinstance(data, dict) or not isinstance(data.get("batches"), list):
        return empty_ledger()
    # Keep the instructions current even if an old ledger is on disk.
    data.setdefault("schema", LEDGER_SCHEMA)
    data[HOW_TO_MARK_KEY] = HOW_TO_MARK
    data.setdefault("marked_posted_through", None)
    return data


def write_ledger(path, ledger):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def fingerprint(item):
    """Stable identity for a queue entry, independent of its position.

    Position is not identity: the queue is reordered by priority on every run,
    and entries are appended continuously. Hashing what the post actually says
    means a draft she has already posted stays recognised however the file moves
    underneath it.
    """
    key = "|".join([
        str(item.get("platform") or ""),
        str(item.get("brand") or item.get("domain") or ""),
        str(item.get("source_url") or item.get("target_url") or ""),
        str(item.get("body") or ""),
    ])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def marked_index(ledger):
    """Index of the last batch declared posted, or -1. Derived, never stamped."""
    marker = ledger.get("marked_posted_through")
    if not marker:
        return -1
    for i, batch in enumerate(ledger.get("batches", [])):
        if batch.get("batch_id") == marker:
            return i
    return -1


def marker_is_stale(ledger):
    """True when marked_posted_through names a batch that does not exist."""
    marker = ledger.get("marked_posted_through")
    if not marker:
        return False
    return all(b.get("batch_id") != marker for b in ledger.get("batches", []))


def open_batches(ledger, platform=None):
    cut = marked_index(ledger)
    out = [b for b in ledger.get("batches", [])[cut + 1:]]
    if platform:
        out = [b for b in out if b.get("platform") == platform]
    return out


def emitted_fingerprints(ledger):
    """Every fingerprint ever offered, posted or not. Nothing is offered twice."""
    seen = set()
    for batch in ledger.get("batches", []):
        for entry in batch.get("items", []):
            fp = entry.get("fingerprint")
            if fp:
                seen.add(fp)
    return seen


def next_batch_id(ledger, platform, today):
    prefix = f"{platform}-{today}"
    n = 1 + sum(1 for b in ledger.get("batches", [])
                if str(b.get("batch_id", "")).startswith(prefix + "-"))
    return f"{prefix}-{n}"


def label_for(item):
    """Something a human recognises at a glance.

    Not every queue entry carries `brand` -- the autopilot lane enqueues some
    rows with only a URL -- and a sheet of eight posts all headed "unknown" is
    a sheet she has to read twice. The publishing host is the next best name.
    """
    name = item.get("brand") or item.get("domain")
    if name:
        return name
    url = item.get("source_url") or item.get("target_url") or ""
    host = urlparse(url).netloc
    return host or "unknown"


def draft_entry(item, index):
    return {
        "fingerprint": fingerprint(item),
        "queue_index_at_draft_time": index,
        "platform": item.get("platform"),
        "brand": label_for(item),
        "url": item.get("source_url") or item.get("target_url") or "",
        "text": social_selection.post_text(item),
    }


def cut_batch(ledger, queue, eligible_indices, platform, size, reason, now, today):
    """Take the next `size` unoffered entries for `platform`, in priority order."""
    seen = emitted_fingerprints(ledger)
    items, used = [], set()
    for index in eligible_indices:
        if len(items) >= size:
            break
        item = queue[index]
        if item.get("platform") != platform:
            continue
        if item.get("status") not in social_selection.POSTABLE_STATUSES:
            continue
        entry = draft_entry(item, index)
        if entry["fingerprint"] in seen or entry["fingerprint"] in used:
            continue
        if not entry["text"]:
            continue
        used.add(entry["fingerprint"])
        items.append(entry)
    if not items:
        return None
    return {
        "batch_id": next_batch_id(ledger, platform, today),
        "platform": platform,
        "generated_at": now,
        "reason": reason,
        "items": items,
    }


def platform_errors(queue, platform, limit=3):
    """What the platform actually said, straight from the queue's own records.

    Every DISTINCT response with a count, not just the most recent one. The most
    recent is the wrong answer here: on 2026-08-29 the last response was HTTP
    429, but the 429s were a consequence of a run that kept calling after the
    real answer - HTTP 402, credits depleted, on the very first request. Showing
    only the last one would point at rate limiting and hide the billing problem
    that is the actual cause.
    """
    counts = {}
    for item in queue:
        if item.get("platform") != platform or not item.get("last_error"):
            continue
        text = str(item["last_error"])
        counts[text] = counts.get(text, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return [{"error": text, "entries": n} for text, n in ordered]


def render_markdown(ledger, unavailable, now, today, errors=None):
    batches = open_batches(ledger)
    lines = [
        "# Post these by hand",
        "",
        f"_Generated {now}. Regenerated on every scheduled run; nothing here is lost._",
        "",
    ]
    if unavailable:
        lines.append("Automatic posting is not carrying these right now:")
        lines.append("")
        for platform, reason in sorted(unavailable.items()):
            lines.append(f"- **{platform}** — {reason}")
            for recorded in (errors or {}).get(platform) or []:
                lines.append(
                    f"  - {platform} answered this to {recorded['entries']} posts: "
                    f"`{recorded['error'][:220]}`")
        lines.append("")
        lines.append(
            "See `docs/SOCIAL-AUTOPOST-SECRETS.md` for what that means and what changes "
            "it. Nothing below is lost either way: the posting queue is untouched, and "
            "automatic posting resumes the moment the API can post again -- on its own "
            "after an outage, or by setting the platform's `enabled` back to true in "
            "`data/social-brand-policy.json` if it was paused for posting."
        )
        lines.append("")
    if not batches:
        lines += [
            "## Nothing to post by hand",
            "",
            "Either every platform is posting normally, or there is no queued content "
            "waiting. Nothing is being held back.",
            "",
        ]
        return "\n".join(lines) + "\n"

    ids = ", ".join(f"`{b['batch_id']}`" for b in batches)
    last_id = batches[-1]["batch_id"]
    lines += [
        "## When you have posted these",
        "",
        f"Open `data/social-draft-ledger.json`, set `\"marked_posted_through\"` to "
        f"`\"{last_id}\"`, and commit. One edit, and every draft below is done — they "
        "are never offered again and the next run writes the next batch. Nothing else "
        "needs changing, and the posting queue itself is untouched either way.",
        "",
        f"Open batches: {ids}",
        "",
    ]
    for batch in batches:
        lines += [
            "---",
            "",
            f"## Batch `{batch['batch_id']}` — {batch['platform']} — "
            f"{len(batch['items'])} posts",
            "",
        ]
        for n, entry in enumerate(batch["items"], 1):
            lines += [
                f"### {n}. {entry['brand']}",
                "",
                "```text",
                entry["text"],
                "```",
                "",
            ]
            if entry.get("url"):
                lines += [f"Link: {entry['url']}", ""]
    return "\n".join(lines) + "\n"


def run(queue, eligible_indices, unavailable, policy=None, ledger_path=None,
        drafts_path=None, now=None, today=None, batch_sizes=None, write=True):
    """Produce or reissue drafts for every platform that cannot post.

    Returns a receipt. Never touches `queue`.
    """
    policy = social_platforms.load_policy() if policy is None else policy
    now = now or datetime.now(timezone.utc).isoformat()
    today = today or date.today().isoformat()
    batch_sizes = batch_sizes or {}
    ledger = read_ledger(ledger_path)
    before = json.dumps(ledger, sort_keys=True)

    actions, drafted, reissued = {}, 0, 0
    for platform in sorted(unavailable):
        already_open = open_batches(ledger, platform)
        if already_open:
            actions[platform] = {
                "action": "reissued_open_batch",
                "batch_ids": [b["batch_id"] for b in already_open],
                "drafts": sum(len(b["items"]) for b in already_open),
                "detail": (
                    "A batch is already waiting to be posted. Re-rendered unchanged "
                    "rather than adding a second one -- a wall of drafts is as useless "
                    "as an empty queue. Mark it posted in "
                    "data/social-draft-ledger.json to release the next batch."
                ),
            }
            reissued += actions[platform]["drafts"]
            continue
        size = int(batch_sizes.get(platform)
                   or social_platforms.declared_daily_limit(platform, policy)
                   or DEFAULT_BATCH_SIZE)
        batch = cut_batch(ledger, queue, eligible_indices, platform, size,
                          unavailable[platform], now, today)
        if batch is None:
            actions[platform] = {
                "action": "no_queued_content",
                "drafts": 0,
                "detail": (
                    f"{platform} cannot post and nothing is queued for it that has not "
                    f"already been drafted. Nothing is being withheld."
                ),
            }
            continue
        ledger["batches"].append(batch)
        actions[platform] = {
            "action": "new_batch",
            "batch_ids": [batch["batch_id"]],
            "drafts": len(batch["items"]),
        }
        drafted += len(batch["items"])

    changed = json.dumps(ledger, sort_keys=True) != before
    markdown = render_markdown(
        ledger, unavailable, now, today,
        errors={p: platform_errors(queue, p) for p in unavailable})
    if write:
        if changed or not Path(ledger_path).exists():
            write_ledger(ledger_path, ledger)
        Path(drafts_path).parent.mkdir(parents=True, exist_ok=True)
        Path(drafts_path).write_text(markdown, encoding="utf-8")

    open_now = open_batches(ledger)
    return {
        "platforms_unavailable": dict(unavailable),
        "actions": actions,
        "drafts_written": drafted,
        "drafts_reissued": reissued,
        "open_drafts": sum(len(b["items"]) for b in open_now),
        "open_batches": [b["batch_id"] for b in open_now],
        "marked_posted_through": ledger.get("marked_posted_through"),
        "marker_is_stale": marker_is_stale(ledger),
        "ledger_path": str(ledger_path) if ledger_path else None,
        "drafts_path": str(drafts_path) if drafts_path else None,
        "queue_entries_read": len(queue),
    }


def unavailable_platforms(platform_states, halted_platforms, attempted, posted_run,
                          spent_today, posted_today):
    """Which platforms could not get a post out through the API, and why.

    Two families land here. A switched-ON platform whose API refused, or has no
    credentials, or burned its whole budget on failures -- an outage. And a
    platform paused specifically FOR POSTING, whose API is off on purpose while
    its distribution continues by hand. Both need the sheet; neither posts.

    A platform paused DORMANT is in neither family and is never drafted.

    Deliberately NOT "the daily budget is used up". A healthy day that has
    already posted its eight is not an outage and must not produce drafts; a day
    whose whole budget was spent on refusals is exactly the case that must.
    """
    out = {}
    for platform, state in (platform_states or {}).items():
        if state == social_platforms.STATE_PAUSED:
            # Paused DORMANT: a recorded decision that nothing is wanted from
            # this platform at all. LinkedIn is here. Drafting it would reverse
            # the owner's switch without anyone deciding to.
            continue
        if state == social_platforms.STATE_PAUSED_FOR_POSTING:
            # Paused FOR POSTING: the API lane is off but distribution
            # continues by hand. X is here. This is the whole reason the two
            # pause modes are distinguished -- see scripts/lib/social_platforms.py.
            out[platform] = (
                f"the {platform} API lane is switched off by a recorded decision "
                f"(pause_mode \"{social_platforms.PAUSE_DRAFT_BY_HAND}\"), so nothing is "
                f"sent to it and these are posted by hand instead"
            )
            continue
        if state == social_platforms.STATE_UNDOCUMENTED_OFF:
            continue  # Already a build failure elsewhere; not this lane's job.
        if state == social_platforms.STATE_UNCREDENTIALLED:
            out[platform] = (
                f"the {platform} switch is ON but its credentials are absent from "
                f"repository secrets, so nothing can be sent"
            )
            continue
        halt = (halted_platforms or {}).get(platform)
        if halt:
            out[platform] = f"the platform refused the account this run: {halt}"
            continue
        if (attempted or {}).get(platform, 0) > 0 and (posted_run or {}).get(platform, 0) == 0:
            out[platform] = (
                f"every {platform} attempt this run failed, so nothing was published"
            )
            continue
        if (spent_today or {}).get(platform, 0) > 0 and (posted_today or {}).get(platform, 0) == 0:
            out[platform] = (
                f"the whole {platform} budget for today was spent on attempts that all "
                f"failed, so this run had nothing left to try"
            )
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--platform", action="append",
                    help="Platform to draft for. Default: every switched-on platform.")
    ap.add_argument("--reason", default="requested_by_hand",
                    help="Why drafting was asked for, recorded on the batch.")
    args = ap.parse_args(argv)

    queue_path = Path(os.getenv("SOCIAL_QUEUE_PATH", str(ROOT / "data/social-queue.json")))
    report_path = Path(os.getenv("SOCIAL_REPORT_PATH",
                                 str(ROOT / "reports/social-publisher-report.json")))
    ledger_path = Path(os.getenv("SOCIAL_DRAFT_LEDGER_PATH", str(ledger_path_default(queue_path))))
    drafts_path = Path(os.getenv("SOCIAL_DRAFTS_PATH", str(drafts_path_default(report_path))))

    queue = json.loads(queue_path.read_text(encoding="utf-8")) if queue_path.exists() else []
    if isinstance(queue, dict):
        queue = queue.get("items", [])
    policy = social_platforms.load_policy()
    today = date.today()
    eligible = social_selection.eligible_in_priority_order(
        queue, policy, today.isoformat(), today.toordinal())

    # Switched-on platforms, plus every platform paused for POSTING -- those are
    # off precisely because their content has to go out by hand, so excluding
    # them here would make the manual lane the one thing that cannot draft X.
    platforms = args.platform or [
        p for p in social_platforms.PLATFORMS
        if social_platforms.is_enabled(p, policy)
        or social_platforms.drafts_by_hand(p, policy)
    ]
    unavailable = {p: args.reason for p in platforms}
    receipt = run(queue, eligible, unavailable, policy=policy,
                  ledger_path=ledger_path, drafts_path=drafts_path)
    receipt["mode"] = "manual"
    print(json.dumps(receipt, indent=2))
    # Rule 0: asked for drafts, produced none, and there was content to draft.
    if not receipt["drafts_written"] and not receipt["open_drafts"] and eligible:
        print("::error::Drafting was requested with queued content available but "
              "produced nothing.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
