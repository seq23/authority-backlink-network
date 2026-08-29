#!/usr/bin/env python3
"""What the owner posted to X by hand, before there was a route. Read-only.

This is the last remaining piece of the hand-post lane, and it is a HISTORICAL
RECORD, not a workflow.

The lane it came from
---------------------
While X's API was pay-per-use and unfunded and Buffer was not yet connected,
`scripts/social_drafts.py` wrote the day's highest-value posts to
`reports/social-drafts.md` as copy-paste text, and the owner marked a batch done
by setting one field, `marked_posted_through`, in
`data/social-draft-ledger.json`.

It was retired on 2026-08-29 when the owner said, of that sheet: *"this means i
manually have to do it? i will never do it honestly."* A lane whose only
consumer will never consume it produces output nothing downstream acts on, so
the sheet, the batch cutter and the renderer are gone. Buffer carries X's posts
now, for nothing, and no surface in this repository asks her to post anything.

What survives, and why exactly this much
----------------------------------------
`marked_posted_through` still names a batch, and every draft in that batch and
in every batch before it is something she PUT ON X WITH HER OWN HANDS. Those
posts are live on the profile. If the ledger were simply deleted, the same
entries -- which were never consumed from `data/social-queue.json`, because
drafting deliberately never touched it -- would be handed to Buffer and posted a
second time on the same profile.

So this module reads that one declaration and answers one question:

    never_send(queue_item)   has she already posted this by hand?

It has no writer. `marked_posted_through` is never cleared, moved,
reinterpreted, or asked to be updated by anyone ever again; it only ever grows
more historical. Batches AFTER the marker are drafts she never posted, and those
are free to go out through Buffer -- that is the whole point of retiring the
sheet, and holding them back would freeze distribution waiting on a step she has
said she will not take.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

LEDGER_SCHEMA = "authority-social-draft-ledger-v1"
MARKER_FIELD = "marked_posted_through"


def ledger_path_default(queue_path):
    """Beside the queue it describes, so a fixture run cannot read the real one."""
    return Path(queue_path).parent / "social-draft-ledger.json"


def read_ledger(path):
    """The committed record, or an empty one. Never written back."""
    empty = {"schema": LEDGER_SCHEMA, MARKER_FIELD: None, "batches": []}
    p = Path(path) if path else None
    if not p or not p.exists():
        return empty
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return empty
    if not isinstance(data, dict) or not isinstance(data.get("batches"), list):
        return empty
    return data


def fingerprint(item):
    """Stable identity for a queue entry, independent of its position.

    Position is not identity: the queue is reordered by priority on every run
    and appended to continuously. Hashing what the post SAYS means a post she
    put on X by hand months ago is still recognised today. The key must stay
    byte-identical to the one the retired drafter used, or every historical
    fingerprint stops matching and the double-post guard silently opens.
    """
    key = "|".join([
        str(item.get("platform") or ""),
        str(item.get("brand") or item.get("domain") or ""),
        str(item.get("source_url") or item.get("target_url") or ""),
        str(item.get("body") or ""),
    ])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def marked_index(ledger):
    """Index of the last batch she declared posted, or -1. Derived, never stamped."""
    marker = ledger.get(MARKER_FIELD)
    if not marker:
        return -1
    for i, batch in enumerate(ledger.get("batches", [])):
        if batch.get("batch_id") == marker:
            return i
    return -1


def posted_by_hand_fingerprints(ledger):
    """Every fingerprint AT OR BEFORE the marker: live on X already.

    Nothing may ever send one of these anywhere again. Batches after the marker
    are deliberately NOT here: they were drafted and never posted, and they are
    free to leave through Buffer.
    """
    cut = marked_index(ledger)
    out = set()
    for batch in ledger.get("batches", [])[:cut + 1]:
        for entry in batch.get("items", []):
            if entry.get("fingerprint"):
                out.add(entry["fingerprint"])
    return out


def summary(ledger):
    """What the record holds, for the run report. No instruction to anyone."""
    cut = marked_index(ledger)
    batches = ledger.get("batches", [])
    return {
        "note": ("Historical only: what the owner posted to X by hand before Buffer "
                 "carried it. Read on every run so those posts are never sent again. "
                 "Nothing updates it and nothing asks her to."),
        MARKER_FIELD: ledger.get(MARKER_FIELD),
        "batches_recorded": len(batches),
        "batches_she_posted_by_hand": cut + 1,
        "posts_she_posted_by_hand": len(posted_by_hand_fingerprints(ledger)),
        "posts_drafted_but_never_posted": sum(
            len(b.get("items", [])) for b in batches[cut + 1:]),
    }
