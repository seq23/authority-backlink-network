#!/usr/bin/env python3
"""Run validation, repair what is repairable, re-validate, loop until clean.

validate.py already reports every non-blocking failure in one pass, so a single
run is enough to decide what to repair. What it does not do is act on the
result: a repairable defect still cost a human round-trip.

The pairing rule is narrow on purpose - a repair is declared only where it
writes the artifact the check reads. A repair that merely sounds related would
produce motion without fixing the defect and make the loop look like it had
tried something.

Note that page_validation.py repairs by default; the `changed` profile
deliberately passes --no-repair so ordinary development validates without
mutating the tree. The loop calls the repairing form explicitly, so repair only
ever happens because the loop decided to repair.
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "self-heal-loop.json"

# check name -> ordered list of repairs. Only where the repair writes what the
# check reads. Order matters: the cheap wholly-derived rebuild runs first.
#
# The derived rebuild is paired with the page checks because a stale or damaged
# derived artifact surfaces AS a page failure, not as a deterministic_build
# failure - deterministic_build compares fresh temp builds against each other
# and passes regardless of what is in the tree. Corrupting a generated 404.html
# reproduced exactly this: pages_release failed, page_validation could not fix
# it because it does not own that file, and the loop honestly reported
# UNRESOLVED. Rebuilding the derived artifacts first resolves it in one attempt.
BUILD_DERIVED = ([sys.executable, "scripts/deterministic_build.py", "--write"],
                 "Rewrites the wholly derived artifacts (sitemaps, llms.txt, 404s). Safe to run unconditionally: it regenerates from source and cannot destroy authored content.")
REPAIRS = {
    "pages_changed": [BUILD_DERIVED,
                      ([sys.executable, "scripts/page_validation.py", "changed"],
                       "page_validation.py repairs by default; the check runs the same code with --no-repair, so this is the repairing form of the identical contract.")],
    "pages_release": [BUILD_DERIVED,
                      ([sys.executable, "scripts/page_validation.py", "release"],
                       "Same validator, repairing form.")],
    "pages_full": [BUILD_DERIVED,
                   ([sys.executable, "scripts/page_validation.py", "full"],
                    "Same validator, repairing form.")],
    "deterministic_build": [BUILD_DERIVED],
}

# Deliberately unpaired, recorded so the omissions stay auditable:
# json/python are syntax gates - a malformed file needs an author, not a rerun.
# content_pattern, citation_contract and hostile need words written into pages.
# workflow_trace, portfolio_backlinks, backlink_local, distribution_chain,
# recovery_agency and social_contract describe externally observed state;
# generating their inputs would be fabrication rather than repair.


def run(cmd: list[str]) -> int:
    return subprocess.run(cmd, cwd=ROOT).returncode


def failures(profile: str) -> list[str]:
    receipt = ROOT / "reports" / f"validation-{profile}.json"
    if not receipt.exists():
        return []
    data = json.loads(receipt.read_text(encoding="utf-8"))
    return [r["id"] for r in data.get("results", []) if r.get("exit_code")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", nargs="?", default="release", choices=["changed", "release", "full"])
    ap.add_argument("--max", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--strict", action="store_true", help="Pass --strict through to validate.py.")
    args = ap.parse_args()

    attempts: list[dict] = []
    failed: list[str] = []

    for attempt in range(args.max + 1):
        cmd = [sys.executable, "scripts/validate.py", args.profile] + (["--strict"] if args.strict else [])
        run(cmd)
        failed = failures(args.profile)
        print(f"self-heal: attempt {attempt} - {len(failed)} failing check(s)"
              + (f": {', '.join(failed)}" if failed else ""))
        if not failed or attempt == args.max:
            break

        actions = []
        ran_any = False
        ran_commands: set[str] = set()
        for check in failed:
            pair = REPAIRS.get(check)
            if not pair:
                actions.append({"check": check, "action": "no declared repair", "ran": False})
                continue
            for command, why in pair:
                joined = " ".join(command)
                if args.dry_run:
                    actions.append({"check": check, "action": joined, "ran": False, "skipped": "dry-run"})
                    continue
                if joined in ran_commands:
                    actions.append({"check": check, "action": joined, "ran": False, "skipped": "already run this attempt"})
                    continue
                ran_commands.add(joined)
                code = run(command)
                ran_any = True
                actions.append({"check": check, "action": joined, "ran": True, "repair_exit": code, "why": why})
        attempts.append({"attempt": attempt + 1, "failed_before": failed, "actions": actions})
        if not ran_any:
            print("self-heal: nothing repairable - these need a decision, not another attempt")
            break

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "mode": "dry-run" if args.dry_run else "repair",
        "max_attempts": args.max,
        "status": "UNRESOLVED" if failed else "CLEAN",
        "unresolved": failed,
        "attempts": attempts,
    }, indent=2) + "\n", encoding="utf-8")

    print(f"self-heal: {'UNRESOLVED (' + ', '.join(failed) + ')' if failed else 'CLEAN'}"
          f" - report at {REPORT.relative_to(ROOT)}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
