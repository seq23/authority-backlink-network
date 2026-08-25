#!/usr/bin/env python3
"""Emit _repo_validation_matrix.json from validation/plan.json.

The plan is authority; this file is the flat, reviewable projection of it, in
the same shape the sibling repos publish so the portfolio can be read at a
glance. Regenerate with `npm run validation:matrix` after changing the plan.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "validation/plan.json"
OUT = ROOT / "_repo_validation_matrix.json"

plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
matrix = plan.get("severity_matrix", {})
policy = plan.get("severity_matrix_policy", {})
default = policy.get("default", "HARD_FAIL")

profiles = plan.get("profiles", {})
rows = []
for check in sorted({c for checks in profiles.values() for c in checks}):
    entry = matrix.get(check, {})
    rows.append({
        "id": check,
        "severity": entry.get("severity", default),
        "classified": check in matrix,
        "rationale": entry.get("rationale", "Unclassified; treated as the fail-safe default."),
        "profiles": sorted(p for p, checks in profiles.items() if check in checks),
    })

payload = {
    "schema_version": "1.0",
    "generated_from": "validation/plan.json",
    "plan_sha256": hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest(),
    "severity_definitions": plan.get("severity_policy", {}),
    "severity_matrix_policy": policy,
    "count": len(rows),
    "counts_by_severity": {
        s: sum(1 for r in rows if r["severity"] == s)
        for s in sorted({r["severity"] for r in rows})
    },
    "unclassified": [r["id"] for r in rows if not r["classified"]],
    "validators": rows,
}
OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"VALIDATION MATRIX GENERATED ({len(rows)} validators; "
      f"{payload['counts_by_severity']}; unclassified={len(payload['unclassified'])})")
