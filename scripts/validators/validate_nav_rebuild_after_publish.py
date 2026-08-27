#!/usr/bin/env python3
"""Fail if publishing a new daily page would break the navigation rebuild.

The daily workflow runs `authority_v4_autopilot.py` and then
`build_site_navigation.py --write`, in that order, and the second step is what
gives the pages the first step wrote a path in. Those two scripts spent a week
in direct contradiction and nothing in the gate could see it:
`build_site_navigation.py` renders bounded navigation blocks - twelve siblings
from `neighbours()`, twelve recent pages from `recent_pages()` - and also
refused to write any page that lost a link. A bounded window over a growing
library has to evict. So every run in which the autopilot actually published
something aborted the rebuild, the new pages stayed orphans, and the workflow
went red. Neither script is wrong on its own, and running either one on the
committed tree passes, which is why no existing check caught it.

This asserts the property that was violated, in the order the workflow does it:

  a new daily page is published, then the navigation rebuild completes, and
  every page in the publication is still reachable.

How
---
The repository's generator inputs are copied into a temporary directory and a
newly-published daily page is synthesised there, one per publication. Nothing is
written into `sites/`, `data/` or `reports/`: this check has no side effects on
the repository at all, and the fixture pages exist only inside a directory that
is deleted before it returns.

The fixture is a page shape, not content. It carries no claim, no statistic and
no citation - only a title, a Topic row naming a real cluster from
`data/topic-taxonomy.json` so the rebuild can place it in a hub, and the
`<p><a href="../index.html">&larr; Home</a></p>` paragraph that every daily
generator emits and that `page_composer.apply_page_navigation` replaces with the
breadcrumb. That paragraph is deliberate: swapping a relative home link for an
absolute one in the breadcrumb was the second way the old assertion failed a
page it should have passed, and the fixture reproduces it.

Then, inside the copy:

* `build_site_navigation.py --write` must exit 0 and report PASS.
* The run must actually have evicted something from a navigation block. A guard
  that stops exercising the case it exists for is worse than no guard, so a run
  with zero evictions fails as a stale fixture rather than passing quietly.
* No eviction may leave a page the publication no longer reaches.
* `measure_click_depth.py --max-depth 3` - the same command validation/plan.json
  registers as `click_depth` at HARD_FAIL - must exit 0 with zero orphans.
* Each fixture page must be linked from some other page of its publication.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Everything the two generators read. `reports/` is created empty in the copy
# because measure_click_depth.py writes its measurement there.
COPIED = ("scripts", "data", "content-bank", "sites")

DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d\d-\d\d)-")

FIXTURE_SLUG = "nav-rebuild-guard-fixture"
FIXTURE_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{title} | {pub}</title>
<meta name="description" content="Fixture page for the navigation rebuild guard.">
</head>
<body><main class="page"><p><a href="../index.html">&larr; Home</a></p><article>
<h1>{title}</h1>
<p>This page exists only inside a temporary copy of the repository, so that
scripts/validators/validate_nav_rebuild_after_publish.py can prove the
navigation rebuild survives a new daily page being published. It is never
written into sites/ and makes no claim about anything.</p>
<table><tbody><tr><td>Topic</td><td>{cluster}</td></tr></tbody></table>
</article></main></body></html>
"""


def stderr(message: str) -> None:
    print(message, file=sys.stderr)


def build_fixture_tree(tmp: Path) -> list[tuple[str, str, str]]:
    """Copy the generator inputs and publish one new daily page per publication.

    Returns (publication id, domain, fixture rel path).
    """
    for name in COPIED:
        shutil.copytree(ROOT / name, tmp / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (tmp / "reports").mkdir(exist_ok=True)

    publications = json.loads(
        (tmp / "data/publications.json").read_text(encoding="utf-8"))
    taxonomy = json.loads(
        (tmp / "data/topic-taxonomy.json").read_text(encoding="utf-8"))

    planted: list[tuple[str, str, str]] = []
    for pub in sorted(publications, key=lambda p: p["id"]):
        source = tmp / pub["folder"]
        daily = source / "daily"
        if not daily.is_dir():
            raise SystemExit(f'{pub["id"]}: no daily/ directory to publish into')

        # One day past the newest page the publication already carries, so the
        # fixture sorts to the top of the recency block the way a real new page
        # does. recent_pages() reads the date from the filename.
        newest = max((m.group(1) for m in
                      (DATE_PREFIX_RE.match(p.name) for p in daily.glob("*.html"))
                      if m), default=None)
        if not newest:
            raise SystemExit(f'{pub["id"]}: no dated daily pages to publish after')
        stamp = (date.fromisoformat(newest) + timedelta(days=1)).isoformat()

        hub = taxonomy["publications"][pub["id"]]["hubs"][0]
        rel = f"daily/{stamp}-{FIXTURE_SLUG}.html"
        (source / rel).write_text(
            FIXTURE_PAGE.format(
                title="Navigation Rebuild Guard Fixture",
                pub=pub["title"], cluster=hub["clusters"][0]),
            encoding="utf-8", newline="\n")
        planted.append((pub["id"], pub.get("working_domain") or pub.get("domain"), rel))
    return planted


def run(tmp: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=tmp, text=True,
                          capture_output=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def linked_from_elsewhere(tmp: Path, folder: str, rel: str) -> bool:
    """True when some other page of this publication carries a link to `rel`."""
    route = "/" + rel[: -len(".html")]
    source = tmp / folder
    for path in source.rglob("*.html"):
        if path.relative_to(source).as_posix() == rel:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for href in re.findall(r'<a\s[^>]*?href="([^"]+)"', text, re.I):
            if href.split("#")[0].split("?")[0].endswith(route):
                return True
    return False


def main() -> int:
    failures: list[str] = []
    notes: list[str] = []

    with tempfile.TemporaryDirectory(prefix="nav-rebuild-guard-") as raw:
        tmp = Path(raw)
        planted = build_fixture_tree(tmp)
        notes.append(f"published {len(planted)} new daily page(s) into a copy of the tree")

        nav = run(tmp, "scripts/build_site_navigation.py", "--write")
        if nav.returncode != 0:
            failures.append(
                "HARD_FAIL the navigation rebuild refused to run after a new daily "
                f"page was published (exit {nav.returncode}): "
                f"{(nav.stderr or nav.stdout).strip().splitlines()[-1:] or ['no output']}")
        receipt = {}
        try:
            receipt = json.loads(nav.stdout)
        except json.JSONDecodeError:
            if nav.returncode == 0:
                failures.append("HARD_FAIL the navigation rebuild produced no JSON receipt")

        if receipt:
            if receipt.get("status") != "PASS":
                failures.append(
                    f'HARD_FAIL navigation rebuild receipt status {receipt.get("status")!r}: '
                    f'{ {k: v for k, v in receipt.items() if k.startswith("pages_") or k.endswith("hubs")} }')
            pubs = receipt.get("publications", [])
            evictions = sum(p.get("nav_block_evictions", 0) for p in pubs)
            stranded = sum(p.get("nav_block_evictions_left_unreachable", 0) for p in pubs)
            if evictions == 0:
                # Not a pass. Publishing a page must push something out of a
                # bounded block; if it no longer does, this check is asserting
                # nothing and needs rewriting, not ignoring.
                failures.append(
                    "HARD_FAIL the fixture no longer evicts anything from a navigation "
                    "block, so this check is no longer exercising the case it exists for")
            if stranded:
                failures.append(
                    f"HARD_FAIL {stranded} page(s) evicted from a navigation block are "
                    "reached by nothing after the rebuild")
            notes.append(f"{evictions} navigation-block eviction(s), {stranded} left unreachable")

        depth = run(tmp, "scripts/measure_click_depth.py", "--max-depth", "3")
        if depth.returncode != 0:
            failures.append(
                f"HARD_FAIL click depth breached after the rebuild (exit {depth.returncode}): "
                f"{(depth.stdout or depth.stderr).strip().splitlines()[-3:]}")
        report = tmp / "reports/click-depth.json"
        if report.is_file():
            measured = json.loads(report.read_text(encoding="utf-8"))
            for row in measured.get("publications", []):
                if row.get("orphans"):
                    failures.append(
                        f'HARD_FAIL {row["publication"]}: {row["orphans"]} orphan(s) after '
                        f'the rebuild, e.g. {row.get("orphan_sample", [])[:3]}')
            notes.append("click depth: " + ", ".join(
                f'{r["publication"]} {r["reachable"]}/{r["pages"]} reachable, '
                f'max depth {r["max_depth"]}' for r in measured.get("publications", [])))

        folders = {p["id"]: p["folder"] for p in json.loads(
            (tmp / "data/publications.json").read_text(encoding="utf-8"))}
        for pub_id, _domain, rel in planted:
            if not linked_from_elsewhere(tmp, folders[pub_id], rel):
                failures.append(
                    f"HARD_FAIL {pub_id}: the newly published page {rel} is linked "
                    "from no other page of its publication")

    if failures:
        print("NAV REBUILD AFTER PUBLISH: FAIL")
        for line in failures:
            print(f"  {line}")
        for line in notes:
            print(f"  note: {line}")
        return 1

    print("NAV REBUILD AFTER PUBLISH: PASS")
    for line in notes:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
