#!/usr/bin/env python3
"""Reseed data/cadence/lastmod_ledger.json from real git history.

The ledger was introduced with every one of its 565 entries stamped with the day
it was created, on the stated grounds that no per-page history existed. That was
wrong: this repository has 143 commits going back to 2026-06-27, and every page's
history is in it. `scripts/cadence_gate.js` kept reporting

    uniform_lastmod: 565 of 565 pages share a lastmod inside 7 days - that is a
    date bump pattern, not a refresh, and it makes the freshness signal meaningless

which was an accurate description of a seeded ledger.

What date is being claimed
--------------------------
`<lastmod>` is a claim to a crawler about when this page changed. Taking each
file's most recent commit date would have laundered the tip date straight back
in: every page in this repository was touched on 2026-08-26 by a commit that
added the same block to 557 of them at once. 566 of 569 files share that
most-recent-commit date, so it carries no information about any individual page.

So the rule is: **a page's lastmod is the date its visible text last changed in
a commit that did not change most of the library at once.** A library-wide
mechanical edit - adding an analytics tag to 513 pages, backfilling a rel
attribute onto 495, inserting a summary block into 557 - is real, and the ledger
records the new content hash for it, but it does not move any page's date,
because a date that moves for every page simultaneously distinguishes nothing.
That is the same judgement `cadence_gate.js` already encodes in its
`uniform_lastmod` warning.

"Most of the library" is measured, not assumed. Sorting this repository's
commits by how many currently published pages each one touched gives a clean
gap: 557, 513, 495, 460, 244, 100, 100, 100, 100, 65, then 47, 40, 36, 32, 22.
The cut is at 10% of published pages (57 files), which sits inside that gap. The
rule applies to the commits that produced this change exactly as it applies to
the ones before it.

Where a file's visible text has never changed outside a library-wide commit, the
date it was added to the repository is used. That is still a real observation
from real history.

Nothing here invents a date. A file with no git history keeps whatever the
ledger already holds and is reported as untouched.

Usage: reseed_lastmod_from_git.py [--write]
Prints a JSON receipt to stdout; diagnostics go to stderr.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import lastmod_ledger  # noqa: E402

PUBLICATIONS = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
BULK_SHARE = 0.10  # of currently published pages


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True,
                          check=True).stdout


def visible_text_hash(blob: bytes) -> str:
    """Hash what a reader sees, so an attribute-only edit is not a content change."""
    text = blob.decode("utf-8", errors="replace")
    text = re.sub(r"<(script|style)\b[\s\S]*?</\1>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\b20\d\d-\d\d-\d\d\b", " ", text)
    text = re.sub(r"\b20\d\d-\d\d-\d\dT[\d:]+Z\b", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return lastmod_ledger.content_hash(re.sub(r"\s+", " ", text).strip())


def published_pages() -> dict[str, Path]:
    """{url: file} for every page the sitemap emitters publish, by their own rules."""
    out: dict[str, Path] = {}
    for pub in PUBLICATIONS:
        source = ROOT / pub["folder"]
        domain = pub.get("working_domain") or pub.get("domain") or pub.get("default_domain")
        if not domain or not source.exists():
            continue
        for page in sorted(source.rglob("*.html")):
            rel = page.relative_to(source).as_posix()
            text = page.read_text(encoding="utf-8", errors="ignore")
            if rel.startswith("agency/") or re.search(
                    r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', text, re.I):
                continue
            loc = f"https://{domain}/" if rel == "index.html" else f"https://{domain}/{rel}"
            out[loc] = page
    return out


def commit_history() -> tuple[list[tuple[str, str]], dict[str, list[str]], dict[str, set[str]]]:
    """(commits oldest-first, {path: [sha, ...]}, {sha: {path, ...}})."""
    raw = git("log", "--reverse", "--format=C|%H|%ad", "--date=short", "--name-only", "--", "sites")
    commits: list[tuple[str, str]] = []
    by_path: dict[str, list[str]] = defaultdict(list)
    files_in: dict[str, set[str]] = defaultdict(set)
    sha = ""
    for line in raw.splitlines():
        if line.startswith("C|"):
            _, sha, when = line.split("|", 2)
            commits.append((sha, when))
        elif line.strip() and line.endswith(".html"):
            by_path[line.strip()].append(sha)
            files_in[sha].add(line.strip())
    return commits, by_path, files_in


def blob_hashes(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Visible-text hash of every (sha, path) pair, in one `git cat-file --batch`."""
    if not pairs:
        return {}
    proc = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    request = "".join(f"{sha}:{path}\n" for sha, path in pairs).encode()
    stdout, _ = proc.communicate(request)
    out: dict[tuple[str, str], str] = {}
    pos = 0
    for key in pairs:
        end = stdout.index(b"\n", pos)
        header = stdout[pos:end].decode()
        pos = end + 1
        parts = header.split()
        if len(parts) < 3:            # "<object> missing" - path absent in that tree
            continue
        size = int(parts[2])
        out[key] = visible_text_hash(stdout[pos:pos + size])
        pos += size + 1               # payload plus its trailing newline
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    # A shallow clone can only see the tip, so every page would resolve to the
    # tip commit's date - exactly the laundering this exists to prevent.
    if git("rev-parse", "--is-shallow-repository").strip() != "false":
        print(json.dumps({
            "status": "FAIL",
            "reason": "shallow_repository",
            "detail": "History is truncated, so a per-page date cannot be observed. "
                      "Re-run in a full clone; refusing to write the tip date to every URL.",
        }, indent=2))
        raise SystemExit(1)

    pages = published_pages()
    by_file = {p.relative_to(ROOT).as_posix(): url for url, p in pages.items()}
    commits, path_commits, files_in = commit_history()
    dates = dict(commits)

    bulk_cut = BULK_SHARE * len(pages)
    bulk = {sha for sha, files in files_in.items()
            if len({f for f in files if f in by_file}) > bulk_cut}

    wanted = [(sha, path) for path in by_file for sha in path_commits.get(path, [])]
    hashes = blob_hashes(wanted)

    resolved: dict[str, str] = {}
    no_history: list[str] = []
    from_added: list[str] = []
    for path, url in by_file.items():
        shas = path_commits.get(path, [])
        if not shas:
            no_history.append(path)
            continue
        added = dates[shas[0]]
        chosen = None
        previous = None
        for sha in shas:
            digest = hashes.get((sha, path))
            if digest is None:
                continue
            changed = digest != previous
            previous = digest
            if changed and sha not in bulk:
                chosen = dates[sha]
        if chosen is None:
            chosen = added
            from_added.append(path)
        resolved[url] = chosen

    ledger = lastmod_ledger.load()
    entries = dict(ledger.get("entries", {}))
    live = {url: lastmod_ledger.content_hash(page.read_text(encoding="utf-8", errors="ignore"))
            for url, page in pages.items()}

    changed = 0
    for url, digest in live.items():
        lastmod = resolved.get(url) or (entries.get(url) or {}).get("lastmod")
        if not lastmod:
            continue
        if (entries.get(url) or {}).get("lastmod") != lastmod:
            changed += 1
        # The hash recorded is the file as it stands now, so the next build sees
        # no change and leaves the reseeded date alone.
        entries[url] = {"hash": digest, "lastmod": lastmod}

    ledger = {
        "schema": lastmod_ledger.SCHEMA,
        "note": (
            "Per-URL content hash and the date that content last changed. A page's lastmod is "
            "the date its visible text last changed in a commit that did not change more than "
            f"{int(BULK_SHARE * 100)}% of the published library at once; where that never "
            "happened, it is the date the page was added. Reseeded from real git history by "
            "scripts/reseed_lastmod_from_git.py - no date here was reconstructed or invented. "
            "lastmod only advances for a URL whose hash changed; see scripts/lib/lastmod_ledger.py."
        ),
        "seeded_on": ledger.get("seeded_on"),
        "reseeded_from_git_on": max(dates.values()) if dates else None,
        "entries": {url: entries[url] for url in sorted(entries)},
    }
    if args.write:
        lastmod_ledger.save(ledger)

    distribution: dict[str, int] = defaultdict(int)
    for value in entries.values():
        distribution[value["lastmod"]] += 1

    print(json.dumps({
        "status": "PASS",
        "written": args.write,
        "published_urls": len(pages),
        "bulk_commit_threshold_pages": round(bulk_cut),
        "bulk_commits": sorted(bulk),
        "urls_dated_from_git": len(resolved),
        "urls_dated_from_added_date": len(from_added),
        "urls_without_git_history": no_history,
        "urls_whose_lastmod_changed": changed,
        "distinct_dates": len(distribution),
        "distribution": dict(sorted(distribution.items())),
    }, indent=2))


if __name__ == "__main__":
    main()
