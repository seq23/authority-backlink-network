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
    "cadence_gate_integrity": ["node", "scripts/validators/validate_cadence_gate_integrity.js"],
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", choices=PLAN["profiles"])
    ap.add_argument("--strict", action="store_true",
                    help="Promote STRONG_WARNING and SOFT_WARNING failures to blocking.")
    args = ap.parse_args()
    results: list[dict] = []

    for check in PLAN["profiles"][args.profile]:
        result = run_check(check)
        result["severity"] = severity_for(check)
        result["blocking"] = args.strict or result["severity"] == "HARD_FAIL"
        results.append(result)
        # Stop at the first genuinely blocking failure. A non-blocking one keeps
        # the run going: reporting only the first defect and hiding the rest is
        # how a repo gets fixed one round-trip at a time.
        if result["exit_code"] != 0 and result["blocking"]:
            break

    blocking_failures = sum(1 for r in results if r["exit_code"] != 0 and r["blocking"])
    nonblocking_failures = sum(1 for r in results if r["exit_code"] != 0 and not r["blocking"])
    hard_failures = blocking_failures + sum(r["hard_failures"] for r in results)
    # Child receipts already provide warning counts. Do not count the aggregate status a second time.
    strong_warnings = sum(r["strong_warnings"] for r in results) + sum(
        1 for r in results if r["exit_code"] != 0 and not r["blocking"])
    soft_warnings = sum(r["soft_warnings"] for r in results)
    status = "FAIL" if hard_failures else ("PASS_WITH_STRONG_WARNING" if strong_warnings else ("PASS_WITH_SOFT_WARNING" if soft_warnings else "PASS"))
    receipt = {
        "schema": "authority-validation-receipt-v2",
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
