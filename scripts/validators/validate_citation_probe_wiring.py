#!/usr/bin/env python3
"""The citation probe must actually have something to ask.

What went wrong
---------------
scripts/llm_citation_probe.mjs is the only thing in this repository that
measures whether answer engines cite these publications. It was wired into the
autopilot on the stated grounds that "the probe shipped in seven repos and was
invoked by none, so no citation observation was ever taken".

It was then invoked, and still took no observation. loadQueries() falls back to
`data/seo/priority_queries.json` when the config does not name a file, and that
path has never existed here. A missing file yields an empty list, an empty list
exits 1 with "citation probe: no queries found", and the workflow step is
continue-on-error - so every scheduled run since has ended with the probe dead
and the run green. The queries existed the whole time, in
data/queries/evidence/evidence_queries.json, generated from the topic map for
exactly this purpose. Two components each keeping their own list, with nothing
joining them.

Being invoked is not the same as doing work. This checks the second thing.

What it proves
--------------
It runs the real probe in dry-run mode - no API key, no network, no spend - and
requires it to exit 0 and report a non-zero count of queries ready. That is the
narrowest possible statement of "this stage would do work if it ran", and it is
the statement that was false.

It fails if the configured queries file is missing or empty, if the probe exits
non-zero, or if it reports zero queries ready.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts" / "llm_citation_probe.mjs"
CONFIG = ROOT / "data" / "signals" / "citation_probe_config.json"
# Mirrors the fallback inside loadQueries(). Named here so that relying on it is
# visible rather than implicit.
PROBE_DEFAULT_QUERIES = "data/seo/priority_queries.json"


def main() -> int:
    failures = []
    checks = []

    if not PROBE.exists():
        print(json.dumps({
            "validator": "citation_probe_wiring", "status": "FAIL", "hard_failures": 1,
            "detail": f"{PROBE} is missing; the citation observation cannot be checked.",
        }, indent=2))
        return 1

    config = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    queries_file = config.get("queries_file") or PROBE_DEFAULT_QUERIES
    qpath = ROOT / queries_file
    checks.append({"check": "queries_file_declared", "value": queries_file,
                   "from_config": bool(config.get("queries_file"))})

    query_count = 0
    if not qpath.exists():
        failures.append(
            f"The citation probe reads its queries from {queries_file}, which does not "
            f"exist. loadQueries() returns an empty list for a missing file and the probe "
            f"then exits 1 without taking any observation"
            + (
                f". No queries_file is declared in {CONFIG.relative_to(ROOT)}, so it fell "
                f"back to the built-in default {PROBE_DEFAULT_QUERIES} - the exact path "
                f"that was never present in this repository."
                if not config.get("queries_file") else "."
            )
        )
    else:
        raw = json.loads(qpath.read_text(encoding="utf-8"))
        rows = raw if isinstance(raw, list) else (
            raw.get("queries") or raw.get("priority_queries") or raw.get("entries") or [])
        query_count = len([r for r in rows if r])
        checks.append({"check": "queries_available", "value": query_count})
        if not query_count:
            failures.append(
                f"{queries_file} exists but declares no queries. The probe would exit 1 "
                f"with 'no queries found' and no citation observation would be taken."
            )

    # Drive the real probe. --dry-run makes no network call and needs no key.
    proc = subprocess.run(
        ["node", str(PROBE), "--dry-run", "--limit", "25"],
        cwd=ROOT, text=True, capture_output=True,
    )
    output = (proc.stdout + proc.stderr).strip()
    m = re.search(r"(\d+)\s+queries ready", output)
    ready = int(m.group(1)) if m else 0
    checks.append({"check": "probe_dry_run_exit_code", "value": proc.returncode})
    checks.append({"check": "probe_reports_queries_ready", "value": ready})
    if proc.returncode != 0:
        failures.append(
            f"The citation probe exited {proc.returncode} on a dry run: {output[:300]}. "
            f"In the autopilot this step is continue-on-error, so a non-zero exit here is "
            f"invisible at run time - the workflow stays green while the only measurement "
            f"of answer-engine citation in this repository does nothing."
        )
    if ready <= 0:
        failures.append(
            f"The citation probe reported {ready} queries ready. A probe with nothing to "
            f"ask produces the same output on every run regardless of the library it is "
            f"measuring, which is an inert stage wearing a green tick."
        )

    # Rule 0: never pass having examined nothing.
    if not checks:
        print(json.dumps({
            "validator": "citation_probe_wiring", "status": "FAIL", "hard_failures": 1,
            "checks_made": 0,
            "detail": "Examined nothing; passing here would vouch for nothing.",
        }, indent=2))
        return 1

    result = {
        "validator": "citation_probe_wiring",
        "status": "FAIL" if failures else "PASS",
        "hard_failures": len(failures),
        "strong_warnings": 0,
        "soft_warnings": 0,
        "checks_made": len(checks),
        "queries_file": queries_file,
        "queries_available": query_count,
        "queries_ready_on_dry_run": ready,
        "checks": checks,
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
