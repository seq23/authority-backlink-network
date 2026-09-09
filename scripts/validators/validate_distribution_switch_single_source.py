#!/usr/bin/env python3
"""One question, one answer: which platforms must a published page reach?

Why this validator exists
-------------------------
On 2026-09-09 the autopilot published two pages and enqueued them for nothing.
X had been paused route-only since 2026-08-29 -- its own paid API off, its posts
leaving through a switched-on Buffer route that had already accepted 49 of them
-- and three components each answered "which platforms distribute?" from their
own local reading of data/social-brand-policy.json:

    scripts/social_publisher.py            asked partition_queue()      CORRECT
    scripts/prioritize_social_queue.py     asked partition_queue()      CORRECT
    scripts/authority_v4_autopilot.py      asked enabled_platforms()    WRONG
    scripts/validators/
        validate_social_enqueue_completeness.py
                                           asked declared_enabled()     WRONG

The two wrong readings agreed with each other, so the drop was self-consistent:
the autopilot enqueued nothing for X, and the validator confirmed that nothing
was expected. What actually broke was invisible from either end. The validator
did fail the release, but it named a policy gap -- "if that is intended it must
be a recorded decision in data/social-brand-policy.json" -- that did not exist.
The decision was recorded there in full. Neither reader could see it.

That is the "two components each keeping their own list with no link" class, and
patching the two wrong readings does not close it: a fifth component can be
written tomorrow with the same blind spot, and it will agree with itself too. So
the link is asserted, here, as a property of the repository rather than of any
one caller.

What this asserts
-----------------
1. Every declared distribution decision site consults the SHARED helper --
   social_platforms.distributing_platforms(), or partition_queue() which is
   defined in terms of it -- and no site re-derives the set from
   enabled_platforms()/declared_enabled() alone.
2. No UNDECLARED site creates social-queue rows. A new enqueue site has to be
   declared here, which is the moment its gate gets read.
3. The helper actually distinguishes the states, proven against synthetic
   policies rather than asserted in prose: dormant excluded, route-only with the
   route ON included, route-only with the route OFF excluded, enabled included.
4. The autopilot's enqueue loops are gated by a real membership test against the
   shared answer, read from the AST rather than by substring -- a comment
   mentioning the name cannot satisfy this.

Rule 0
------
Hard-fails when it examines zero sites, zero gates or zero states. A validator
that passes over an empty loop is not passing, and the sites are found on disk,
so a rename or a deletion makes this loud instead of vacuous.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lib import social_platforms  # noqa: E402

# Every module that decides whether a published page enters the social queue, or
# whether a queued row may leave. Each must consult the shared answer.
#
# `gate` is the name the module must bind the shared answer to (enqueue sites,
# which must gate per platform), or None for consumers that legitimately use
# partition_queue() instead.
DECISION_SITES = (
    {"path": "scripts/authority_v4_autopilot.py", "kind": "enqueue",
     "gate": "distributing_social_platforms"},
    {"path": "scripts/social_publisher.py", "kind": "post", "gate": None},
    {"path": "scripts/prioritize_social_queue.py", "kind": "post", "gate": None},
    {"path": "scripts/validators/validate_social_enqueue_completeness.py",
     "kind": "contract", "gate": None},
)

# Any of these means the module asked the shared question.
SHARED_CALLS = ("distributing_platforms", "partition_queue")
# Asking only these is the blind spot. They are fine ALONGSIDE a shared call --
# reporting which platforms are enabled is honest and the receipts do it -- and
# wrong as the only answer in a module that decides distribution.
NARROW_CALLS = ("enabled_platforms", "declared_enabled")

# Where social-queue rows are created. Any file that writes a row carrying a
# 'platform' key into data/social-queue.json is an enqueue site by definition.
ENQUEUE_ROW_MARKER = "'platform':"
QUEUE_WRITE_MARKER = "data/social-queue.json"
# Declared non-enqueue writers of the queue file: they rewrite existing rows,
# they never create one for a platform, so they carry no distribution decision.
KNOWN_QUEUE_WRITERS = {
    "scripts/authority_v4_autopilot.py",
    "scripts/social_publisher.py",
    "scripts/prioritize_social_queue.py",
    "scripts/backfill_social_queue.py",
    "scripts/generate_social_queue.py",
    "scripts/lib/social_platforms.py",
}


def called_names(tree: ast.AST) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                out.add(func.attr)
            elif isinstance(func, ast.Name):
                out.add(func.id)
    return out


def membership_gates(tree: ast.AST) -> set:
    """Names used as the right-hand side of an `x in NAME` test, from the AST."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.In):
            right = node.comparators[0]
            if isinstance(right, ast.Name):
                out.add(right.id)
    return out


def main() -> int:
    failures: list[str] = []
    sites_examined = 0
    gates_examined = 0
    site_report = []

    for site in DECISION_SITES:
        path = ROOT / site["path"]
        if not path.exists():
            failures.append(
                f"{site['path']} is declared here as a distribution decision site but does "
                f"not exist. It was renamed, moved or deleted without updating this guard, "
                f"so nothing is now checking whichever file took over its decision."
            )
            continue
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        calls = called_names(tree)
        sites_examined += 1
        shared = sorted(c for c in SHARED_CALLS if c in calls)
        narrow = sorted(c for c in NARROW_CALLS if c in calls)
        if not shared:
            failures.append(
                f"{site['path']} decides distribution ({site['kind']}) but never asks "
                f"social_platforms.distributing_platforms() or partition_queue(). It "
                f"reads the policy through {narrow or ['no shared helper at all']}, which "
                f"cannot see a route-only pause -- the exact reading that stopped X "
                f"distribution dead on 2026-08-29 while Buffer sat connected and idle."
            )
        gates = membership_gates(tree)
        if site["gate"]:
            gates_examined += 1
            if site["gate"] not in gates:
                failures.append(
                    f"{site['path']} has no `<platform> in {site['gate']}` membership test "
                    f"in its AST. Its enqueue loops must be gated on the shared answer "
                    f"bound to that name; a gate on any other list is a second opinion, "
                    f"and the two opinions agreeing is what made the 2026-09-09 drop "
                    f"invisible from both ends."
                )
            else:
                missing_gate = [p for p in social_platforms.PLATFORMS
                                if f"'{p}' in {site['gate']}" not in src]
                if missing_gate:
                    failures.append(
                        f"{site['path']} does not gate {', '.join(missing_gate)} on "
                        f"{site['gate']}. Every platform's enqueue loop asks the same "
                        f"question, so flipping `enabled` or `delivery_route` in "
                        f"data/social-brand-policy.json is the whole change."
                    )
        site_report.append({"path": site["path"], "kind": site["kind"],
                            "shared_calls": shared, "narrow_calls": narrow})

    # --- No undeclared enqueue site -----------------------------------------
    undeclared = []
    scanned_py = 0
    for path in sorted(ROOT.glob("scripts/**/*.py")):
        rel = path.relative_to(ROOT).as_posix()
        # Validators read the queue and quote its field names; none of them
        # writes a row. Scanning them finds only the strings this file and
        # validate_social_enqueue_completeness.py use to DESCRIBE an enqueue,
        # which is a match on the description rather than on the thing.
        if "__pycache__" in rel or rel.startswith("scripts/validators/"):
            continue
        scanned_py += 1
        if rel in KNOWN_QUEUE_WRITERS:
            continue
        src = path.read_text(encoding="utf-8")
        if QUEUE_WRITE_MARKER in src and ENQUEUE_ROW_MARKER in src:
            undeclared.append(rel)
    if undeclared:
        failures.append(
            f"these files create social-queue rows and are not declared as decision "
            f"sites: {undeclared}. A new enqueue site is a new answer to 'which platforms "
            f"must a published page reach?'; declare it in DECISION_SITES so its gate is "
            f"read, rather than letting it keep its own list."
        )

    # --- The helper actually distinguishes the states -----------------------
    def policy(x_enabled, x_mode, route_on, li_enabled=False):
        paperwork = {"paused_on": "2026-01-01", "paused_by": "test",
                     "paused_reason": "synthetic fixture for this validator"}
        x = {"enabled": x_enabled, "pause_mode": x_mode, **paperwork,
             "delivery_route": {"route": "buffer", "enabled": route_on}}
        li = {"enabled": li_enabled, "pause_mode": "dormant", **paperwork}
        return {"platforms": {"x": x, "linkedin": li}}

    states = (
        ("route_only_with_route_on_distributes",
         policy(False, "delivery_route", True), ["x"]),
        ("route_only_with_route_off_does_not_distribute",
         policy(False, "delivery_route", False), []),
        ("dormant_does_not_distribute",
         policy(False, "dormant", True), []),
        ("legacy_draft_by_hand_spelling_still_distributes",
         policy(False, "draft_by_hand", True), ["x"]),
        ("enabled_distributes_whatever_the_route_says",
         policy(True, "dormant", False), ["x"]),
        ("enabled_linkedin_distributes",
         policy(False, "dormant", False, li_enabled=True), ["linkedin"]),
    )
    states_examined = 0
    for name, pol, expected in states:
        states_examined += 1
        got = social_platforms.distributing_platforms(pol)
        if got != expected:
            failures.append(
                f"distributing_platforms() property {name!r} does not hold: expected "
                f"{expected}, got {got}."
            )

    # --- Rule 0 -------------------------------------------------------------
    if not sites_examined:
        failures.append(
            "examined zero distribution decision sites. This validator cannot vouch for "
            "anything and must not report a pass.")
    if not gates_examined:
        failures.append(
            "examined zero enqueue gates. The enqueue gate is the thing that dropped X "
            "distribution; a run that checks none of them proves nothing.")
    if not states_examined or not scanned_py:
        failures.append(
            f"examined {states_examined} helper states over {scanned_py} scripts. An "
            f"empty tree is not a clean one.")

    result = {
        "validator": "distribution_switch_single_source",
        "status": "FAIL" if failures else "PASS",
        "hard_failures": len(failures),
        "sites_examined": sites_examined,
        "gates_examined": gates_examined,
        "helper_states_examined": states_examined,
        "scripts_scanned_for_undeclared_enqueue": scanned_py,
        "sites": site_report,
        "live_answer": {
            "enabled": social_platforms.enabled_platforms(),
            "routed": social_platforms.routed_platforms(),
            "distributing": social_platforms.distributing_platforms(),
        },
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
