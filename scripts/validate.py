#!/usr/bin/env python3
"""Authority Network v4.5 single-level validation orchestrator.

There is one orchestration layer. Validators return evidence; only real release risk blocks.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / "validation/plan.json").read_text(encoding="utf-8"))

COMMANDS = {
    "json": [sys.executable, "tests/validate_json_contracts.py"],
    "python": [sys.executable, "-m", "py_compile"],
    "workflow_trace": [sys.executable, "scripts/trace_github_actions.py"],
    "pages_changed": [sys.executable, "scripts/page_validation.py", "changed", "--no-repair"],
    "pages_release": [sys.executable, "scripts/page_validation.py", "release"],
    "pages_full": [sys.executable, "scripts/page_validation.py", "full"],
    "deterministic_build": [sys.executable, "scripts/deterministic_build.py"],
    "content_pattern": ["node", "scripts/validators/validate_content_pattern_contract.js"],
    "hostile": [sys.executable, "scripts/hostile_review.py"],
    "links": [sys.executable, "scripts/link_audit.py"],
    "social_contract": [sys.executable, "tests/test_social_contract.py"],
    "cache_self_test": [sys.executable, "scripts/cache_self_test.py"],
    "citation_control": [sys.executable, "scripts/citation_control_plane.py", "verify-repo"],
    "citation_contract": [sys.executable, "tests/test_citation_control_plane.py"],
    "portfolio_backlinks": [sys.executable, "tests/test_portfolio_backlink_system.py"],
    "backlink_local": [sys.executable, "scripts/portfolio_backlink_engine.py", "verify-local"],
    "distribution_chain": [sys.executable, "tests/test_distribution_chain.py"],
    "recovery_agency": [sys.executable, "tests/test_recovery_agency_contract.py"],
    "published_tree_purity": [sys.executable, "scripts/validators/validate_published_tree_purity.py"],
    "external_sources": [sys.executable, "scripts/verify_external_sources.py"],
    "click_depth": [sys.executable, "scripts/measure_click_depth.py", "--max-depth", "3"],
    "nav_rebuild_after_publish": [sys.executable, "scripts/validators/validate_nav_rebuild_after_publish.py"],
    "autopilot_cadence_cap": [sys.executable, "scripts/validators/validate_autopilot_respects_cadence_cap.py"],
    "analytics_separation": [sys.executable, "scripts/validators/validate_analytics_separation.py"],
    "affiliate_topical_scope": [sys.executable, "scripts/validators/validate_affiliate_topical_scope.py"],
    "brand_link_concentration": [sys.executable, "scripts/validators/validate_brand_link_concentration.py"],
    "cadence_gate_integrity": ["node", "scripts/validators/validate_cadence_gate_integrity.js"],
    "selfheal_wiring": [sys.executable, "scripts/validators/validate_selfheal_wiring.py"],
    "social_enqueue_completeness": [sys.executable, "scripts/validators/validate_social_enqueue_completeness.py"],
    "script_callers": [sys.executable, "scripts/validators/validate_script_callers.py"],
    "social_rate_limits": [sys.executable, "scripts/validators/validate_social_rate_limits.py"],
    "social_attempt_budget": [sys.executable, "scripts/validators/validate_social_attempt_budget.py"],
    "no_manual_lane": [sys.executable, "scripts/validators/validate_no_manual_lane.py"],
    "social_pause_modes": [sys.executable, "scripts/validators/validate_social_pause_modes.py"],
    "buffer_route": [sys.executable, "scripts/validators/validate_buffer_route.py"],
    "citation_probe_wiring": [sys.executable, "scripts/validators/validate_citation_probe_wiring.py"],
    "social_queue_priority": [sys.executable, "scripts/prioritize_social_queue.py", "--check"],
    "affiliate_rel_disclosure": [sys.executable, "scripts/backfill_rel_attributes.py", "--check"],
    "wedding_cost_dataset": [sys.executable, "scripts/validators/validate_wedding_cost_dataset.py"],
    "external_citation_coverage": [sys.executable, "scripts/validators/validate_external_citation_coverage.py"],
    "backlink_seed_preserves_citations": [sys.executable, "scripts/validators/validate_backlink_seed_preserves_citations.py"],
    "internal_links_resolve": [sys.executable, "scripts/validators/validate_internal_links_resolve.py"],
    "uscis_changelog": [sys.executable, "scripts/validators/validate_uscis_changelog.py"],
    "journalist_query_lane": [sys.executable, "scripts/validators/validate_journalist_query_lane.py"],
    "validation_receipt_severity_truth": [sys.executable, "scripts/validators/validate_validation_receipt_severity_truth.py"],
}


def python_compile_command() -> list[str]:
    files = sorted(
        [*ROOT.glob("scripts/**/*.py"), *ROOT.glob("tests/**/*.py"), *ROOT.glob("validation/**/*.py")],
        key=lambda p: p.as_posix(),
    )
    return [sys.executable, "-m", "py_compile", *[str(p.relative_to(ROOT)) for p in files]]


def parse_child_receipt(stdout: str) -> dict:
    try:
        value = json.loads(stdout)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def run_check(check: str) -> dict:
    cmd = python_compile_command() if check == "python" else COMMANDS[check]
    started = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    child = parse_child_receipt(proc.stdout)
    child_status = child.get("status", "")
    status = "FAIL" if proc.returncode else (child_status if child_status.startswith("PASS_WITH_") else "PASS")
    return {
        "id": check,
        "status": status,
        "exit_code": proc.returncode,
        "duration_ms": round((time.time() - started) * 1000),
        "hard_failures": int(child.get("hard_failures", 0)),
        "strong_warnings": int(child.get("strong_warnings", 0)),
        "soft_warnings": int(child.get("soft_warnings", 0)),
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


SEVERITY_MATRIX = PLAN.get("severity_matrix", {})
SEVERITY_DEFAULT = PLAN.get("severity_matrix_policy", {}).get("default", "HARD_FAIL")


def severity_for(check: str) -> str:
    # Unclassified checks fail safe. An absent entry means nobody has reasoned
    # about the check, which is not a reason to let it through quietly.
    return SEVERITY_MATRIX.get(check, {}).get("severity", SEVERITY_DEFAULT)


# The receipt used to carry one field named `severity` on every result, set from
# the matrix regardless of whether the check passed. It was a policy class -- how
# bad this check would be IF it failed -- but the word reads as an outcome, so 37
# of 41 PASSing checks in a green release receipt were stamped
# `"severity": "HARD_FAIL"`. A reader grepping a failed receipt for HARD_FAIL got
# every check in the profile and no way to tell which one actually broke. That
# already cost one misdiagnosis of run 33650439764, where the single real failure
# was external_citation_coverage.
#
# So the two facts are now named separately and neither is inferable from the
# other's name:
#   severity_class     static policy from validation/plan.json; what it would
#                      cost if this check failed. Present on passes and fails.
#   observed_severity  what this run actually observed. "NONE" on a pass. Only a
#                      check that genuinely failed can read HARD_FAIL here.
# `blocking_if_failed` replaces `blocking` for the same reason.
PASSED = "NONE"


def classify(check: str, exit_code: int, strict: bool) -> dict:
    """The single place outcome and policy are turned into receipt fields.

    Kept pure and separate from run_check() so the guard that protects this
    property can read the emitter's own logic instead of a second copy of it.
    """
    severity_class = severity_for(check)
    blocking_if_failed = strict or severity_class == "HARD_FAIL"
    return {
        "severity_class": severity_class,
        "observed_severity": PASSED if exit_code == 0 else severity_class,
        "blocking_if_failed": blocking_if_failed,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", choices=PLAN["profiles"])
    ap.add_argument("--strict", action="store_true",
                    help="Promote STRONG_WARNING and SOFT_WARNING failures to blocking.")
    args = ap.parse_args()
    results: list[dict] = []

    for check in PLAN["profiles"][args.profile]:
        result = run_check(check)
        result.update(classify(check, result["exit_code"], args.strict))
        results.append(result)
        # Stop at the first genuinely blocking failure. A non-blocking one keeps
        # the run going: reporting only the first defect and hiding the rest is
        # how a repo gets fixed one round-trip at a time.
        if result["exit_code"] != 0 and result["blocking_if_failed"]:
            break

    blocking_failures = sum(1 for r in results if r["exit_code"] != 0 and r["blocking_if_failed"])
    nonblocking_failures = sum(1 for r in results if r["exit_code"] != 0 and not r["blocking_if_failed"])
    hard_failures = blocking_failures + sum(r["hard_failures"] for r in results)
    # Child receipts already provide warning counts. Do not count the aggregate status a second time.
    strong_warnings = sum(r["strong_warnings"] for r in results) + sum(
        1 for r in results if r["exit_code"] != 0 and not r["blocking_if_failed"])
    soft_warnings = sum(r["soft_warnings"] for r in results)
    status = "FAIL" if hard_failures else ("PASS_WITH_STRONG_WARNING" if strong_warnings else ("PASS_WITH_SOFT_WARNING" if soft_warnings else "PASS"))
    receipt = {
        "schema": "authority-validation-receipt-v3",
        "profile": args.profile,
        "status": status,
        "release_blocked": hard_failures > 0,
        "hard_failures": hard_failures,
        "blocking_failures": blocking_failures,
        "nonblocking_failures": nonblocking_failures,
        "strict": args.strict,
        "strong_warnings": strong_warnings,
        "soft_warnings": soft_warnings,
        "results": results,
    }
    # Sweep unreachable cache receipts now that every check has finished. The
    # index keeps one object per page, so each revalidation of a changed page
    # strands the receipt it replaced; without this the store reached 3,129
    # objects behind 569 live entries. Never allowed to affect the verdict - a
    # failed sweep is a disk-space problem, not a validation failure.
    try:
        # validate.py runs from scripts/, so the repo root is not on sys.path and
        # a bare `from validation import cache` resolves to nothing.
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from validation import cache as _cache
        receipt_prune = _cache.prune()
        # stderr, never stdout: parse_child_receipt() does json.loads() on a
        # child's entire stdout, so a single stray line here would make every
        # receipt parse fail and silently zero the child's failure and warning
        # counts.
        print(f"[cache:prune] PASS: scanned={receipt_prune['objects_scanned']}; "
              f"kept={receipt_prune['objects_kept']}; removed={receipt_prune['objects_removed']}; "
              f"reclaimed={receipt_prune['bytes_reclaimed'] / 1048576:.1f}MB", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - reclaiming disk must never block release
        print(f"[cache:prune] SKIPPED: {exc}", file=sys.stderr)

    out = ROOT / "reports" / f"validation-{args.profile}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    raise SystemExit(1 if hard_failures else 0)


if __name__ == "__main__":
    main()
