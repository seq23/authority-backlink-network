#!/usr/bin/env python3
"""The backlink seeder must never rewrite a page that cites outside sources.

What this stops happening again
-------------------------------
`portfolio_backlink_engine.py seed` rewrote every seed page from `render()` on
every run: `if not path.exists() or path.read_text() != page: path.write_text(page)`.
`render()` emits the bare article. The 32 seed pages on disk are not bare -- later
lanes add breadcrumb and related navigation, the editorial footer, the affiliate
disclosure, and the `Sources outside this network` block that
add_external_citations.py writes. So every nightly distribution run deleted the
outbound citations from all 32, and nothing put them back: the autopilot lane
rebuilds navigation and chrome but never calls add_external_citations.py.

Confirmed 2026-09-02 on a clean checkout of main: `seed` rewrote 32 pages and
31 of them stopped citing outside sources, taking founder to 86 (floor 94),
memphis to 85 (floor 92) and professional to 382 (floor 398). That regression
surfaced a lane later, in validate_external_citation_coverage.py, which reports
the loss but cannot say what caused it. This validator names the cause, and it
fails at the generator rather than at the far end of the pipeline.

Two things fail hard:

  clobber   `seed` would write a page whose outbound citations the rewrite does
            not contain -- action `blocked` in plan_seed_writes(), or an
            enriched page planned for `create`/`refresh`
  zero      the planner returned no seed pages at all, or none of the pages it
            planned exists on disk. A guard that iterates an empty list reports
            PASS forever.

It reads the generator's own planner, `plan_seed_writes()`, rather than a second
copy of the same rule, so the guard cannot drift away from the decision it
governs: the same function decides what `seed` writes.

    python3 scripts/validators/validate_backlink_seed_preserves_citations.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from portfolio_backlink_engine import (  # noqa: E402
    ENRICHMENT_MARKERS,
    outside_citations,
    plan_seed_writes,
)

WRITING_ACTIONS = {"create", "refresh"}


def main() -> int:
    failures: list[str] = []
    plans = plan_seed_writes()

    if not plans:
        print("BACKLINK SEED PRESERVES CITATIONS: FAIL")
        print("  HARD_FAIL plan_seed_writes() returned zero seed pages; this guard must "
              "not report PASS on an empty loop")
        return 1

    existing = 0
    citing = 0
    for plan in plans:
        path = ROOT / plan["rel"]
        if not path.exists():
            # A page the seeder is about to create for the first time carries no
            # citations yet and cannot lose any. Counted, not failed.
            continue
        existing += 1
        current = path.read_text(encoding="utf-8", errors="ignore")
        cites = outside_citations(current)
        if cites:
            citing += 1

        if plan["action"] == "blocked":
            failures.append(
                f"HARD_FAIL {plan['rel']}: rewriting this page from the seed template "
                f"would delete {len(plan['lost_citations'])} outbound citation(s): "
                f"{', '.join(plan['lost_citations'])}")
            continue

        if plan["action"] in WRITING_ACTIONS:
            lost = sorted(cites - outside_citations(plan["page"]))
            if lost:
                failures.append(
                    f"HARD_FAIL {plan['rel']}: planned action '{plan['action']}' would "
                    f"delete outbound citation(s): {', '.join(lost)}")
            enrichment = [m for m in ENRICHMENT_MARKERS if m in current]
            if enrichment:
                failures.append(
                    f"HARD_FAIL {plan['rel']}: planned action '{plan['action']}' would "
                    f"overwrite downstream enrichment on this page ({', '.join(enrichment)}). "
                    "Seeding creates pages; the lanes that enrich them own them afterwards.")

    if existing == 0:
        print("BACKLINK SEED PRESERVES CITATIONS: FAIL")
        print("  HARD_FAIL none of the planned seed pages exists on disk; this guard "
              "examined nothing and must not report PASS")
        return 1

    print("BACKLINK SEED PRESERVES CITATIONS")
    print(f"  seed pages planned: {len(plans)}")
    print(f"  already on disk: {existing}; of those, citing outside sources: {citing}")
    actions = sorted({p["action"] for p in plans})
    for action in actions:
        print(f"  {action:<9} {sum(1 for p in plans if p['action'] == action)}")

    if failures:
        print("BACKLINK SEED PRESERVES CITATIONS: FAIL")
        for line in sorted(set(failures)):
            print(f"  {line}")
        return 1
    print("BACKLINK SEED PRESERVES CITATIONS: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
