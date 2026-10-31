#!/usr/bin/env python3
"""The weekly entity backlink watch is reachable, scheduled, and lands what it heals.

The defect this blocks, reproduced on origin/main on 2026-10-31
----------------------------------------------------------------
scripts/entity_backlink_watch.py, tests/test_entity_backlink_watch.py, the
`entity:watch` npm lane and the CLAUDE.md Search Readiness row that names
`entity-backlink-watch.yml` by name all landed in #132 with no workflow at all:
the watch could not run, so no sameAs was ever checked, no dead profile was
ever dropped, and a profile in `profiles_pending` could never be promoted into
`sameAs` however long it had been live. The loop existed, the documentation
described it in the present tense, and nothing invoked it. #133 created the
workflow. Nothing yet keeps it: deleting the file, dropping its schedule or
removing the rebuild would put the repository straight back into that state
with every other part of the loop still reading as live. This is that guard.

That is the "exists but nothing invokes it" class, and the owner's Search
Readiness item k6 measures exactly it: a workflow named entity-backlink-watch
with a schedule and a workflow_dispatch whose newest run is green and under
eight days old.

What this blocks (HARD_FAIL)
----------------------------
  * no workflow whose filename is entity-backlink-watch (k6's own pattern);
  * that workflow with no `schedule:`/`cron:`, or no `workflow_dispatch`;
  * a workflow that never invokes scripts/entity_backlink_watch.py;
  * a watch that heals the entity files but does not rebuild the published tree
    from them and revalidate -- a promoted profile that never reaches a page is
    a healed file nobody can read;
  * CLAUDE.md no longer naming the workflow (the spec must read the code);
  * head_seo.py no longer reading data/entities (the published Organization
    nodes would stop coming from the entity file);
  * a publication in data/publications.json with no entity file, or an entity
    file with no `sameAs` list.

Comment lines are stripped before the invocation checks: a script named only in
a comment is documentation, not a caller.

Zero-item hard fail: zero workflow files, or zero entity files, exits non-zero
rather than passing vacuously.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WATCH_NAME = re.compile(r"^entity[-_]backlink[-_]watch\.ya?ml$")   # k6's own pattern
WATCH_SCRIPT = "scripts/entity_backlink_watch.py"

errors: list[str] = []
checked = 0


def check(condition: bool, message: str) -> None:
    global checked
    checked += 1
    if not condition:
        errors.append(message)


def uncommented(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


# --- the workflow exists, under the name k6 looks for ------------------------
wf_dir = ROOT / ".github/workflows"
workflows = sorted(p for p in wf_dir.glob("*.y*ml")) if wf_dir.exists() else []
if not workflows:
    print("entity watch wiring: examined zero workflow files - refusing to pass vacuously", file=sys.stderr)
    raise SystemExit(1)

matching = [p for p in workflows if WATCH_NAME.match(p.name)]
check(
    bool(matching),
    "no .github/workflows/entity-backlink-watch.yml: the weekly link-back watch exists in "
    f"{WATCH_SCRIPT} and in CLAUDE.md, and nothing can start it (Search Readiness k6)",
)

if matching:
    body = uncommented(matching[0].read_text(encoding="utf-8"))
    name = matching[0].name
    check("schedule:" in body and "cron:" in body, f"{name} has no schedule: the watch is weekly or it is not a watch")
    check("workflow_dispatch" in body, f"{name} cannot be dispatched by hand (k6 requires workflow_dispatch)")
    check(WATCH_SCRIPT in body, f"{name} never invokes {WATCH_SCRIPT} - the workflow would run green and check nothing")
    check("--write" in body, f"{name} runs the watch read-only: a dead profile is never dropped and a pending one never promoted")
    check(
        "editorial:build" in body or "install_editorial_chrome.py" in body,
        f"{name} heals data/entities but never rebuilds the published tree from it - "
        "a promoted profile would never reach an Organization node on any page",
    )
    check(
        "scripts/validate.py" in body or "validate_entity_graph.py" in body,
        f"{name} proposes a change without revalidating the tree it rebuilt - a bad self-heal "
        "would reach a pull request with nothing having read the entity graph",
    )

# --- the spec reads the code -------------------------------------------------
claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
check(
    "entity-backlink-watch.yml" in claude_md,
    "CLAUDE.md no longer names entity-backlink-watch.yml in its Search Readiness table - "
    "the rule would stop pointing at the code that keeps it",
)

# --- the npm lane and the chokepoint ----------------------------------------
pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
lanes = [n for n, v in (pkg.get("scripts") or {}).items() if WATCH_SCRIPT in v]
check(bool(lanes), f"no npm script runs {WATCH_SCRIPT} - the watch cannot be run by hand either")

head_seo = (ROOT / "scripts/lib/head_seo.py").read_text(encoding="utf-8")
check(
    "data/entities" in head_seo,
    "scripts/lib/head_seo.py no longer reads data/entities - the published Organization nodes would "
    "stop coming from the entity file, and healing the file would change nothing a crawler sees",
)

# --- every publication has an entity file with a sameAs list ----------------
publications = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
entity_dir = ROOT / "data/entities"
entity_files = sorted(entity_dir.glob("*.json")) if entity_dir.exists() else []
if not publications or not entity_files:
    print("entity watch wiring: zero publications or zero entity files - refusing to pass vacuously", file=sys.stderr)
    raise SystemExit(1)

for pub in publications:
    domain = pub["working_domain"]
    path = entity_dir / f"{domain}.json"
    if not path.exists():
        errors.append(f"data/entities/{domain}.json is missing: {pub['title']} has no entity for the watch to check")
        checked += 1
        continue
    entity = json.loads(path.read_text(encoding="utf-8"))
    check(isinstance(entity.get("sameAs"), list), f"data/entities/{domain}.json has no sameAs list")
    check(isinstance(entity.get("profiles_pending", []), list), f"data/entities/{domain}.json profiles_pending is not a list")

if errors:
    print("Entity watch wiring validation failed:\n- " + "\n- ".join(errors))
    raise SystemExit(1)

print(json.dumps({
    "status": "PASS",
    "assertions": checked,
    "workflow": matching[0].name if matching else None,
    "npm_lanes": lanes,
    "entities": [p.stem for p in entity_files],
    "profiles": {p.stem: len(json.loads(p.read_text(encoding="utf-8")).get("sameAs") or []) for p in entity_files},
}, indent=2))
