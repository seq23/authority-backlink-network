#!/usr/bin/env python3
"""Guard the self-healing machinery against the four ways it was theatre.

Every assertion here corresponds to a defect reproduced on origin/main on
2026-08-29. This validator exists so none of them can come back silently.

1. `portfolio_backlink_engine.repair()` gated on lifecycle stages
   {published_in_repository, rendered_in_repository}. The registry has never
   held either: all 613 rows are live_verified or approved_destination, so the
   repair matched 0 rows on every run and printed status PASS. Asserted here as
   "the gate must match rows that actually exist".

2. The same function appended rows to `repaired` for findings it has no handler
   for, so a defect it cannot fix was recorded as fixed. Asserted here as
   "every handled finding must have a handler in the source".

3. `cache.fingerprint()` omitted `allow_repair`, so `page_validation.py release
   --no-repair` cached an un-repaired page and the next repairing run got a HIT
   and repaired nothing. Asserted here by calling fingerprint directly.

4. `heal_until_clean.REPAIRS["pages_changed"]` ran `page_validation.py changed`,
   which cannot repair in any circumstance, while claiming to be "the repairing
   form of the identical contract". Asserted here as "every declared repair must
   be able to mutate".

Plus the wiring itself: the loop must be reachable from a workflow.

Zero-item hard fail: if the registry is empty, the workflow directory is empty,
or no repairs are declared, this exits non-zero rather than passing vacuously.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

errors: list[str] = []
checked = 0


def check(condition: bool, message: str) -> None:
    global checked
    checked += 1
    if not condition:
        errors.append(message)


# --- 1. the repair gate must match rows the registry actually contains --------
registry = json.loads((ROOT / "data/link-registry.json").read_text(encoding="utf-8"))
if not registry:
    print("selfheal wiring: link registry is empty - refusing to pass vacuously", file=sys.stderr)
    raise SystemExit(1)

engine_src = (ROOT / "scripts/portfolio_backlink_engine.py").read_text(encoding="utf-8")


def literal_set(name: str) -> set[str]:
    m = re.search(rf"^{name}\s*=\s*\{{(.*?)\}}", engine_src, re.M | re.S)
    return set(re.findall(r"'([^']+)'", m.group(1))) if m else set()


stages = literal_set("REPAIRABLE_STAGES")
statuses = literal_set("REPAIRABLE_STATUSES")
check(bool(stages), "portfolio_backlink_engine.py declares no REPAIRABLE_STAGES")
check(bool(statuses), "portfolio_backlink_engine.py declares no REPAIRABLE_STATUSES")

matched = [r for r in registry
           if r.get("lifecycle_stage") in stages and r.get("status") in statuses]
check(
    len(matched) > 0,
    f"the backlink repair gate matches 0 of {len(registry)} registry rows "
    f"(stages={sorted(stages)}, statuses={sorted(statuses)}) - it is a no-op that reports PASS",
)

# The stages the repair must NOT touch: these rows were deliberately withdrawn or
# had off-topic links deleted by repair_offtopic_affiliate_links.py. Repairing
# them would re-insert exactly what that remediation removed.
forbidden = {"approved_destination"}
check(
    not (stages & forbidden),
    f"the backlink repair gate includes {sorted(stages & forbidden)} - those rows are withdrawn, "
    "removed_off_topic or never published, and repairing them re-inserts links a prior remediation deleted",
)

# --- 2. every finding claimed as handled must have a handler ------------------
handled = literal_set("HANDLED_FINDINGS")
check(bool(handled), "portfolio_backlink_engine.py declares no HANDLED_FINDINGS")
repair_body = engine_src.split("def repair()", 1)[-1].split("\ndef ", 1)[0]
for finding in sorted(handled):
    check(
        f"'{finding}'" in repair_body,
        f"HANDLED_FINDINGS claims {finding} but repair() has no branch for it - "
        "it would be recorded as repaired without being repaired",
    )

# --- 3. allow_repair must be part of the cache key ----------------------------
from validation import cache  # noqa: E402

with_repair = cache.fingerprint("page", {"dep": "1"}, "release", True)
without_repair = cache.fingerprint("page", {"dep": "1"}, "release", False)
check(
    with_repair != without_repair,
    "cache.fingerprint() ignores allow_repair - a --no-repair result can satisfy a repairing run "
    "and suppress the repair entirely",
)

# --- 4. every declared repair must be able to mutate --------------------------
heal_src = (ROOT / "scripts/heal_until_clean.py").read_text(encoding="utf-8")
declared = re.findall(r'"scripts/page_validation\.py",\s*"(\w+)"([^\]]*)\]', heal_src)
check(bool(declared), "heal_until_clean.py declares no page_validation repairs")
for mode, rest in declared:
    can_repair = mode in {"release", "full"} or "--repair" in rest
    check(
        can_repair and "--no-repair" not in rest,
        f'heal_until_clean.py declares `page_validation.py {mode}{rest}` as a REPAIR, but that '
        f"invocation cannot mutate the tree - it is inert by construction",
    )

# --- 5. the loop must be reachable from a workflow ----------------------------
wf_dir = ROOT / ".github/workflows"
workflows = sorted(p for p in wf_dir.glob("*.yml")) if wf_dir.exists() else []
if not workflows:
    print("selfheal wiring: examined zero workflow files - refusing to pass vacuously", file=sys.stderr)
    raise SystemExit(1)

pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
lanes = {name: body for name, body in (pkg.get("scripts") or {}).items()
         if "heal_until_clean.py" in body and "--dry-run" not in body}
if not lanes:
    print("selfheal wiring: examined zero self-heal npm scripts - refusing to pass vacuously", file=sys.stderr)
    raise SystemExit(1)

# Comment lines are stripped: a script named only in a comment is documentation,
# not an invocation.
live = "\n".join(
    "\n".join(l for l in p.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#"))
    for p in workflows
)
check(
    "heal_until_clean.py" in live,
    "no workflow runs scripts/heal_until_clean.py - the repair loop exists but CI can never start it",
)

if errors:
    print("Self-heal wiring validation failed:\n- " + "\n- ".join(errors))
    raise SystemExit(1)

print(json.dumps({
    "status": "PASS",
    "assertions": checked,
    "registry_rows": len(registry),
    "rows_matched_by_repair_gate": len(matched),
    "handled_findings": sorted(handled),
    "declared_page_repairs": [f"{m}{r}".strip() for m, r in declared],
    "workflows_scanned": [p.name for p in workflows],
}, indent=2))
