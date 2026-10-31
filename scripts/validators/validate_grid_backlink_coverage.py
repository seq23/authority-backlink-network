#!/usr/bin/env python3
"""Every grid side business gets at least one rendered network backlink, or a named stop.

Authority audit, 30 Oct 2026: memphisseniorcarehomes.com, time-2-read.com,
howweknowdeep.com and spryexecutiveos.com had ZERO published links from the
network, and nothing said so. The network exists to deliver backlinks to the
side businesses, so a side business it does not link is the network failing at
its one job, silently.

For every domain in data/grid-coverage.json:
  * at least one data/link-registry.json row with status "published" whose
    source page exists under sites/ and really carries an <a href> to that
    domain (a registry row with no link on the page is not a backlink); or
  * an entry in grid-coverage.json `named_stops` saying why not -- printed on
    every run as a NAMED STOP, never a silent pass.
A domain with neither is a HARD_FAIL. So is a named stop for a domain that is
covered (a stale stop hides nothing but still lies).

When a sibling ../boss-os checkout exists, the list is also compared with the
grid registry it was copied from, so the two cannot drift apart unnoticed. CI
has no sibling checkout; that comparison is skipped there and says so.

Rule 0: an empty domain list is a FAIL.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
COVERAGE = ROOT / "data/grid-coverage.json"
REGISTRY = ROOT / "data/link-registry.json"
GRID = ROOT.parent / "boss-os/src/shared/boss/searchReadiness/sites.json"
NETWORK = {"professionalresourcelibrary.com", "founderoperatorlibrary.com", "memphisvendorlibrary.com"}


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def main(coverage_path: Path = COVERAGE, registry_path: Path = REGISTRY) -> int:
    cov = json.loads(coverage_path.read_text(encoding="utf-8"))
    domains = cov.get("domains") or []
    stops = cov.get("named_stops") or {}
    rows = json.loads(registry_path.read_text(encoding="utf-8"))
    failures, named, covered = [], [], {}
    page_cache: dict[str, str] = {}
    for d in domains:
        n = 0
        for r in rows:
            if r.get("status") != "published" or host(r.get("target_url", "")) != d:
                continue
            src = r.get("source_path") or ""
            if src not in page_cache:
                p = ROOT / src
                page_cache[src] = p.read_text(encoding="utf-8") if src and p.is_file() else ""
            if re.search(r'<a\b[^>]*href="https?://(www\.)?' + re.escape(d) + r'[/"]', page_cache[src]):
                n += 1
        covered[d] = n
        if n and d in stops:
            failures.append(f"{d}: has {n} rendered backlink(s) but still carries a named stop; remove it")
        elif not n and d in stops:
            named.append(f"NAMED STOP {d}: {stops[d]}")
        elif not n:
            failures.append(f"{d}: 0 rendered network backlinks and no named stop. Add a campaign "
                            "(data/portfolio-backlink-campaigns.json) and a seed article, or name the stop.")
    grid_note = "skipped: no sibling boss-os checkout (CI)"
    if GRID.exists():
        grid = json.loads(GRID.read_text(encoding="utf-8"))
        want = sorted(x["domain"] for x in grid.get("grid_repos", [])
                      if x.get("category") in ("side_business", "own_business") and x["domain"] not in NETWORK)
        if want != sorted(domains):
            failures.append(f"data/grid-coverage.json drifted from boss-os: missing {sorted(set(want)-set(domains))}, "
                            f"extra {sorted(set(domains)-set(want))}")
        grid_note = "matched boss-os grid registry" if want == sorted(domains) else "DRIFT"
    if not domains:
        failures.append("Rule 0: data/grid-coverage.json lists no domains")
    for line in named:
        print(line, file=sys.stderr)
    print(json.dumps({"validator": "grid_backlink_coverage", "status": "FAIL" if failures else "PASS",
                      "domains": len(domains), "covered": covered, "named_stops": named,
                      "grid_sync": grid_note, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
