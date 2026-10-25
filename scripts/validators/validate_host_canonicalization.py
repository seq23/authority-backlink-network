#!/usr/bin/env python3
"""Every publication redirects every non-canonical host to its one canonical host.

Checklist item a1. scripts/build_host_canonicalization.py writes the Cloudflare
Pages middleware that does it; this checks the published tree carries exactly
what that generator would write, so an edited or deleted middleware fails the
release rather than silently going back to serving www and apex as two sites.

HARD_FAIL: a missing or drifted middleware is a live search defect on a public
publication, and it is invisible from inside the repository -- both hosts answer
200 and every page still looks right.

Rule 0: zero publications examined is a failure, not a pass.

    python3 scripts/validators/validate_host_canonicalization.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_host_canonicalization import plan  # noqa: E402


def main() -> int:
    wanted = plan()
    failures = []
    for rel, body in sorted(wanted.items()):
        path = ROOT / rel
        if not path.exists():
            failures.append(f"{rel}: missing; run `npm run hosts:canonical`")
            continue
        if path.read_text(encoding="utf-8") != body:
            failures.append(f"{rel}: does not match its generator; run `npm run hosts:canonical`")
    if not wanted:
        failures.append("inert: zero publications examined, so no host rule was checked")
    if failures:
        print("HOST CANONICALIZATION: FAIL")
        for line in failures:
            print(f"  HARD_FAIL {line}")
        return 1
    print(f"HOST CANONICALIZATION: PASS ({len(wanted)} publication(s), each with one canonical host)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
