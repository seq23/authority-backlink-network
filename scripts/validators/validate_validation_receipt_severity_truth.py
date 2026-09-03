#!/usr/bin/env python3
"""The validation receipt must say which check actually failed.

What went wrong
---------------
Every result in `reports/validation-*.json` carried one field named `severity`,
set from `validation/plan.json`'s `severity_matrix` regardless of outcome. It was
a *policy class* -- what it would cost if this check failed -- but the word reads
as an outcome. In the green release receipt measured while writing this, 37 of 41
PASSing checks were stamped `"severity": "HARD_FAIL"` alongside
`"status": "PASS", "hard_failures": 0`.

That is not a cosmetic defect. Run 33650439764 had exactly one real failure,
`external_citation_coverage`, and a reader triaging that receipt for HARD_FAIL
got the whole profile back -- `citation_probe_wiring`, `social_queue_priority`
and `affiliate_rel_disclosure` among them -- and reported three validators as
failing that had passed. A receipt whose failure marker matches every check
identifies nothing, and every future failure in this lane is misdiagnosed the
same way.

Three things fail hard
----------------------
  outcome     a passing check reporting anything other than
              observed_severity == "NONE", or a failing check whose
              observed_severity does not equal its policy class. Checked
              against `scripts/validate.py`'s own `classify()`, not a second
              copy of the rule, so the guard cannot drift from the emitter.
  regression  a per-result key named plain `severity` or plain `blocking`
              reappearing. Those are the two ambiguous names this replaced;
              reintroducing either restores the misreading.
  unclassified
              any check in any profile with no `severity_matrix` entry, or
              `_repo_validation_matrix.json` out of sync with the plan it is
              generated from. The three checks unclassified when this was
              written -- external_citation_coverage,
              backlink_seed_preserves_citations, wedding_cost_dataset -- were
              precisely the guards that caught the citation outage, riding a
              fail-safe default indistinguishable from a reasoned one. The
              published matrix has never had a caller in any profile:
              `npm run validation:matrix` is manual, so a plan edit could
              publish a stale portfolio-facing matrix with nothing objecting.

Examining zero checks is itself a hard failure: a guard that iterates an empty
list reports PASS forever and its green receipt is then read as proof.

    python3 scripts/validators/validate_validation_receipt_severity_truth.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import validate as emitter  # noqa: E402  the receipt emitter under guard

PLAN_PATH = ROOT / "validation/plan.json"
MATRIX_PATH = ROOT / "_repo_validation_matrix.json"
GENERATOR = ROOT / "scripts/generate_validation_matrix.py"

AMBIGUOUS_KEYS = ("severity", "blocking")


def main() -> int:
    failures: list[str] = []
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    profiles = plan["profiles"]
    matrix = plan.get("severity_matrix", {})

    checks = sorted({c for names in profiles.values() for c in names})
    if not checks:
        print("VALIDATION RECEIPT SEVERITY TRUTH: FAIL")
        print("  HARD_FAIL no profile names any check; this guard must not report "
              "PASS on an empty loop")
        return 1

    # 1. Outcome truthfulness, read from the emitter's own classifier.
    examined = 0
    for check in checks:
        policy = emitter.severity_for(check)
        passed = emitter.classify(check, 0, False)
        failed = emitter.classify(check, 1, False)
        examined += 1
        for key in AMBIGUOUS_KEYS:
            if key in passed:
                failures.append(
                    f"HARD_FAIL {check}: result carries the ambiguous key "
                    f"'{key}'. Use severity_class for policy and "
                    "observed_severity for outcome.")
        if passed.get("observed_severity") != emitter.PASSED:
            failures.append(
                f"HARD_FAIL {check}: a passing check reports observed_severity="
                f"{passed.get('observed_severity')!r}, not {emitter.PASSED!r}. "
                "That is the stamp that made a green check look like the failing "
                "one.")
        if passed.get("severity_class") != policy:
            failures.append(
                f"HARD_FAIL {check}: severity_class={passed.get('severity_class')!r} "
                f"does not match the plan's {policy!r}")
        if failed.get("observed_severity") != policy:
            failures.append(
                f"HARD_FAIL {check}: a failing check reports observed_severity="
                f"{failed.get('observed_severity')!r}, not its policy class "
                f"{policy!r}; a real failure must be visible at its true severity")

    # 2. Every check in every profile is classified deliberately.
    unclassified = [c for c in checks if c not in matrix]
    for check in unclassified:
        failures.append(
            f"HARD_FAIL {check}: runs in {sorted(p for p, n in profiles.items() if check in n)} "
            "with no severity_matrix entry, so it rides the fail-safe default "
            "and nobody has stated what its failure would cost")

    # 3. The published matrix is the plan, not a stale snapshot of it.
    if not MATRIX_PATH.exists():
        failures.append(f"HARD_FAIL missing {MATRIX_PATH.name}; the portfolio-facing "
                        "projection of the plan is not published")
    else:
        published = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        actual_sha = hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()
        if published.get("plan_sha256") != actual_sha:
            failures.append(
                f"HARD_FAIL {MATRIX_PATH.name} was generated from a different "
                f"validation/plan.json (recorded {published.get('plan_sha256')}, "
                f"actual {actual_sha}). Run `npm run validation:matrix`.")
        # Run the real generator against a throwaway copy of the tree. Comparing
        # its output to the committed file is the only way to catch drift the
        # sha alone misses, and a validator that regenerated in place would be
        # repairing the evidence it is supposed to be reporting on.
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            (sandbox / "scripts").mkdir()
            (sandbox / "validation").mkdir()
            shutil.copy2(GENERATOR, sandbox / "scripts" / GENERATOR.name)
            shutil.copy2(PLAN_PATH, sandbox / "validation" / PLAN_PATH.name)
            proc = subprocess.run(
                [sys.executable, str(sandbox / "scripts" / GENERATOR.name)],
                cwd=sandbox, text=True, capture_output=True)
            regenerated = sandbox / MATRIX_PATH.name
            if proc.returncode != 0:
                failures.append(f"HARD_FAIL {GENERATOR.name} exits {proc.returncode}: "
                                f"{proc.stderr.strip()[-400:]}")
            elif not regenerated.exists():
                failures.append(f"HARD_FAIL {GENERATOR.name} produced no "
                                f"{MATRIX_PATH.name}")
            elif regenerated.read_text(encoding="utf-8") != MATRIX_PATH.read_text(encoding="utf-8"):
                failures.append(
                    f"HARD_FAIL {MATRIX_PATH.name} is not what its generator produces "
                    "from the current plan; run `npm run validation:matrix` and commit it")

    print("VALIDATION RECEIPT SEVERITY TRUTH")
    print(f"  checks examined: {examined}")
    print(f"  classified in severity_matrix: {len(checks) - len(unclassified)}/{len(checks)}")
    print(f"  published matrix: {'in sync with plan' if not failures else 'see failures'}")

    if failures:
        print("VALIDATION RECEIPT SEVERITY TRUTH: FAIL")
        for line in sorted(set(failures)):
            print(f"  {line}")
        return 1
    print("VALIDATION RECEIPT SEVERITY TRUTH: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
