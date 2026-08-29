#!/usr/bin/env python3
"""Cache-aware, self-healing final-state page validation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation import cache  # noqa: E402
from validation.page_audit import audit_page, iter_pages  # noqa: E402
from validation.repair import repair_once  # noqa: E402

DEPENDENCY_PATHS = [
    "data/brands.json", "data/publications.json", "data/network-rules.json",
    "data/city-publications.json", "content-bank/scaling-policy.json",
    "content-bank/yearly-pantry.json", "validation/page_audit.py",
    "validation/repair.py", "validation/cache.py",
]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"


def dependency_state() -> dict:
    return {p: file_hash(ROOT / p) for p in DEPENDENCY_PATHS}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["changed", "release", "full"])
    parser.add_argument("--no-repair", action="store_true")
    # `changed` stays non-mutating by default so ordinary development validates
    # without rewriting the tree. --repair is the explicit opt-in, and exists so
    # heal_until_clean.py can declare a repair for pages_changed that is actually
    # the repairing form of the identical contract. Before it existed the loop
    # ran `page_validation.py changed`, which cannot repair in any circumstance
    # (allow_repair excluded the mode), reported ran/exit 0, and left the defect
    # in place - proved 2026-08-29: repairs_applied 0 under `changed` vs 1 under
    # `release` for the same stripped meta description.
    parser.add_argument("--repair", action="store_true",
                        help="Permit repair in a mode that does not repair by default.")
    args = parser.parse_args()

    if args.repair and args.no_repair:
        parser.error("--repair and --no-repair are contradictory")

    use_cache = args.mode != "full"
    allow_repair = (args.mode in {"release", "full"} or args.repair) and not args.no_repair
    deps = dependency_state()
    results: list[dict] = []
    hits = misses = repairs = 0

    for page in iter_pages():
        initial = audit_page(page)
        fp = cache.fingerprint(initial.source_hash, deps, args.mode, allow_repair)
        cached = cache.get(initial.path, fp) if use_cache else None
        if cached:
            result = cached["result"]
            result["cache_status"] = "HIT"
            hits += 1
            results.append(result)
            continue

        misses += 1
        repair_codes = {f.code for f in initial.findings if f.repairable}
        repaired = repair_once(page, repair_codes) if allow_repair and repair_codes else []
        if repaired:
            repairs += len(repaired)
        final = audit_page(page)
        final.repair_count = len(repaired)
        result = final.to_dict()
        result["repairs"] = repaired
        result["cache_status"] = "MISS"
        final_fp = cache.fingerprint(final.source_hash, deps, args.mode, allow_repair)
        if result["status"] != "FAIL":
            cache.put(final.path, final_fp, result)
        results.append(result)

    duplicate_groups: dict[str, list[str]] = {}
    for result in results:
        duplicate_groups.setdefault(result["duplicate_fingerprint"], []).append(result["path"])
    duplicate_warnings = [paths for paths in duplicate_groups.values() if len(paths) > 1]

    hard_failures = sum(r["status"] == "FAIL" for r in results)
    strong_warnings = sum(r["status"] == "PASS_WITH_STRONG_WARNING" for r in results)
    soft_warnings = sum(r["status"] == "PASS_WITH_SOFT_WARNING" for r in results)
    # Rule 0: an audit that examined no pages has not audited anything, and its
    # PASS is indistinguishable from a clean library. Proved by deleting every
    # file under sites/: this reported PASS, 0 hard failures, in the `full`
    # profile that exists to audit the whole library. sites/ is committed, so a
    # fresh checkout always has pages - which is exactly why an empty result
    # means a broken glob, a moved tree, or a generator that wrote nothing,
    # never a legitimately empty corpus.
    # `changed` is exempt: a branch that touched no page legitimately has an
    # empty set, and that is the ordinary case rather than a broken one. The
    # whole-library modes have no such excuse.
    if not results and args.mode in {"release", "full"}:
        print(json.dumps({
            "schema": "authority-page-validation-v1",
            "mode": args.mode,
            "status": "FAIL",
            "hard_failures": 1,
            "pages_examined": 0,
            "detail": "Audited zero pages in a whole-library mode. sites/ is tracked in git "
                      "and always contains published pages, so an empty audit set is a "
                      "broken selector or a missing tree, not a clean library. Passing here "
                      "would vouch for nothing while reporting full coverage.",
        }, indent=2))
        raise SystemExit(1)

    receipt = {
        "schema": "authority-page-validation-v1",
        "mode": args.mode,
        "status": "FAIL" if hard_failures else ("PASS_WITH_STRONG_WARNING" if strong_warnings else ("PASS_WITH_SOFT_WARNING" if soft_warnings else "PASS")),
        "pages_examined": len(results),
        "hard_failures": hard_failures,
        "strong_warnings": strong_warnings,
        "soft_warnings": soft_warnings,
        "cache": {"hits": hits, "misses": misses, "enabled": use_cache},
        "repairs_applied": repairs,
        "duplicate_content_groups": duplicate_warnings,
        "pages": results,
    }
    report = ROOT / "reports" / f"page-validation-{args.mode}.json"
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k != "pages"}, indent=2))
    raise SystemExit(1 if hard_failures else 0)


if __name__ == "__main__":
    main()
