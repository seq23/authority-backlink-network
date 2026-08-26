"""Per-URL lastmod ledger: a sitemap date that tracks content, not build time.

Every sitemap emitter in this repo used to stamp one build-time date on every
URL in the file - `deterministic_build.py` used `BUILD_DATE`,
`authority_v4_autopilot.py` used `RELEASE_DATE`, and
`portfolio_backlink_engine.py` used `date.today()`. Any of them rewriting a
sitemap moved all 565 URLs to the same day, so `scripts/cadence_gate.js`
reported `uniform_lastmod: 565 of 565`.

That is worse than having no dates. `<lastmod>` is a claim to a crawler about
when a page changed, and freshness is the strongest single correlate of whether
an answer engine cites a page. A date that advances for every page on every
build carries no information about which page changed, and it is a false claim
about the 564 pages that did not.

The fix is to key the date on content instead of on the clock. This module keeps
a `{url: {hash, lastmod}}` ledger in `data/cadence/lastmod_ledger.json`, beside
the `known_urls.json` the cadence gate already keeps. On each build a URL whose
content hash is unchanged keeps its recorded date; only a URL whose content
actually changed - or a URL that has never been seen - advances to the build
date.

Seeding note: the ledger was first written with every entry stamped with the day
it was created, on the stated grounds that no per-page history existed. That was
not true - this repository has 143 commits going back to 2026-06-27 - and it left
`cadence_gate.js` correctly reporting `uniform_lastmod: 565 of 565`. It is now
reseeded by `scripts/reseed_lastmod_from_git.py`, which reads each page's real
commit history and takes the date its visible text last changed in a commit that
did not change more than a tenth of the published library at once. That
qualifier matters: 566 of 569 files share a most-recent-commit date, because
several commits edited the whole library in one pass, so the naive answer would
have laundered the tip date into every URL. Nothing invents a date; a file with
no history keeps the value it already had.

Determinism: `resolve()` is a pure read. It never writes, so a validator that
builds twice and compares hashes - which `deterministic_build.py` does - sees
identical output. Persistence is a separate, explicit `save()` call made only by
a step that is actually writing artifacts into the repository.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "data/cadence/lastmod_ledger.json"
SCHEMA = "lastmod-ledger-v1"

_NOTE = (
    "Per-URL content hash and the date that content last changed. lastmod only "
    "advances for a URL whose hash changed; see scripts/lib/lastmod_ledger.py. "
    "Dates were reseeded from real git history by "
    "scripts/reseed_lastmod_from_git.py: a page's lastmod is the date its visible "
    "text last changed in a commit that did not change more than a tenth of the "
    "published library at once, or the date the page was added where that never "
    "happened. No date here was invented."
)


def build_date() -> str:
    """The date a change observed by this build should be recorded under.

    Honours the repo's existing controlled-build-date convention so a backfill
    (`scripts/backfill_authority_v4.py` sets BUILD_DATE per simulated day) is
    recorded under the day it is replaying rather than under wall-clock today.
    """
    return os.getenv("BUILD_DATE") or date.today().isoformat()


def content_hash(payload: str | bytes) -> str:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load(path: Path = LEDGER_PATH) -> dict:
    if not path.exists():
        return {"schema": SCHEMA, "note": _NOTE, "seeded_on": None, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # A corrupt ledger must not silently become "everything changed today".
        raise SystemExit(f"lastmod ledger is not valid JSON: {path}")
    data.setdefault("entries", {})
    return data


def resolve(hashes: dict[str, str], ledger: dict | None = None, today: str | None = None) -> dict[str, str]:
    """Map {url: content_hash} to {url: lastmod}. Pure: reads, never writes."""
    ledger = load() if ledger is None else ledger
    today = today or build_date()
    entries = ledger.get("entries", {})
    out: dict[str, str] = {}
    for url, digest in hashes.items():
        prev = entries.get(url)
        if isinstance(prev, dict) and prev.get("hash") == digest and prev.get("lastmod"):
            out[url] = prev["lastmod"]
        else:
            out[url] = today
    return out


def updated(hashes: dict[str, str], ledger: dict | None = None, today: str | None = None) -> dict:
    """The ledger this build should persist. URLs no longer published are dropped."""
    ledger = load() if ledger is None else ledger
    today = today or build_date()
    resolved = resolve(hashes, ledger, today)
    return {
        "schema": SCHEMA,
        "note": _NOTE,
        "seeded_on": ledger.get("seeded_on") or today,
        # Provenance survives a rebuild, or the next --write would quietly erase
        # the record of where these dates came from.
        "reseeded_from_git_on": ledger.get("reseeded_from_git_on"),
        "entries": {
            url: {"hash": hashes[url], "lastmod": resolved[url]}
            for url in sorted(hashes)
        },
    }


def merge(hashes: dict[str, str], ledger: dict | None = None, today: str | None = None) -> dict:
    """Like `updated()`, but keeps entries for URLs outside `hashes`.

    For a caller that only sees one publication's URLs at a time: pruning there
    would delete the other publications' recorded dates and reset them to the
    build date on the next full emit.
    """
    ledger = load() if ledger is None else ledger
    today = today or build_date()
    resolved = resolve(hashes, ledger, today)
    entries = dict(ledger.get("entries", {}))
    for url, digest in hashes.items():
        entries[url] = {"hash": digest, "lastmod": resolved[url]}
    return {
        "schema": SCHEMA,
        "note": _NOTE,
        "seeded_on": ledger.get("seeded_on") or today,
        "reseeded_from_git_on": ledger.get("reseeded_from_git_on"),
        "entries": {url: entries[url] for url in sorted(entries)},
    }


def save(ledger: dict, path: Path = LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
