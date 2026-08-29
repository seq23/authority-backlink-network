#!/usr/bin/env python3
"""Daily social limits must stay inside a band that is both useful and survivable.

Why this blocks
---------------
These limits govern posting to one real X account and one real LinkedIn
account. The failure modes sit on both sides of the number, and both are
expensive:

  Too low   The shipped default was LINKEDIN_DAILY_LIMIT=1 / X_DAILY_LIMIT=5
            against a queue of well over a thousand entries. At 1/day the
            LinkedIn backlog alone runs for years, which is indistinguishable
            from not distributing at all. A cap that never drains is a silent
            decision not to publish.

  Too high  Account suspension, which is effectively irreversible and would
            destroy the authority network this repository exists to build.
            Two separate ceilings apply and the lower one governs:
              - API-legal. On X's free access tier the write allowance is
                500 posts per month for the authenticated user, about 16/day
                averaged, shared across every workflow that posts. Nothing in
                this repository evidences a paid tier, so the free tier is what
                is assumed until a credential or an invoice says otherwise.
              - Platform-safe. A solo practitioner account posting dozens of
                link-bearing notes a day reads as automation to spam scoring
                regardless of what the API accepts. The gap between "the API
                took it" and "the account survived it" is large, and only the
                second one matters here.

So the band below is deliberately narrower than the API allows. The upper bound
leaves real headroom under the free-tier monthly allowance; the lower bound
stops a future edit from quietly restoring a cap that cannot drain.

Pacing is part of the same safety property and is checked here too. Eight posts
emitted inside one loop arrive on effectively one timestamp, which is a more
obvious automation signal than the count itself. The publisher must therefore
keep a per-run slice and a non-trivial inter-post interval.

Fails hard if it examines zero configuration values. A guard that finds nothing
to check and reports PASS anyway is worse than no guard, because the green
receipt is taken as proof that the numbers were reviewed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (minimum, maximum) inclusive. See the docstring for how these were chosen.
BANDS = {
    "X_DAILY_LIMIT": (5, 12),
    "LINKEDIN_DAILY_LIMIT": (2, 5),
    "SOCIAL_RUN_LIMIT": (1, 5),
    "SOCIAL_POST_MIN_INTERVAL_SECONDS": (45, 3600),
}

PUBLISHER = "scripts/social_publisher.py"
WORKFLOWS = [
    ".github/workflows/social-autopost.yml",
    ".github/workflows/authority-v4-autopilot.yml",
]


def publisher_defaults(text):
    """os.getenv('NAME', '7')  ->  {'NAME': 7}"""
    out = {}
    for name in BANDS:
        m = re.search(
            r"os\.getenv\(\s*['\"]" + re.escape(name) + r"['\"]\s*,\s*['\"](-?\d+)['\"]\s*\)",
            text,
        )
        if m:
            out[name] = int(m.group(1))
    return out


def workflow_defaults(text):
    """NAME: ${{ vars.NAME || '7' }}  ->  {'NAME': 7}"""
    out = {}
    for name in BANDS:
        for m in re.finditer(
            re.escape(name) + r":\s*\$\{\{\s*vars\.\w+\s*\|\|\s*'(-?\d+)'\s*\}\}",
            text,
        ):
            out.setdefault(name, []).append(int(m.group(1)))
    return out


def main() -> int:
    failures = []
    examined = []

    pub_path = ROOT / PUBLISHER
    if not pub_path.exists():
        print(json.dumps({
            "validator": "social_rate_limits", "status": "FAIL", "hard_failures": 1,
            "detail": f"{PUBLISHER} is missing; the rate-limit contract cannot be checked.",
        }, indent=2))
        return 1

    text = pub_path.read_text(encoding="utf-8")
    found = publisher_defaults(text)
    for name, (lo, hi) in BANDS.items():
        if name not in found:
            failures.append(
                f"{PUBLISHER} no longer reads {name} with a literal default via "
                f"os.getenv('{name}', '<int>'). The band for this value cannot be "
                f"enforced on a default this validator cannot see."
            )
            continue
        value = found[name]
        examined.append({"source": PUBLISHER, "name": name, "value": value, "band": [lo, hi]})
        if not (lo <= value <= hi):
            failures.append(
                f"{PUBLISHER} default {name}={value} is outside the safe band {lo}..{hi}. "
                + (("Below the band posts are no longer spaced apart, so a run emits a "
                    "clump on one timestamp."
                    if name == "SOCIAL_POST_MIN_INTERVAL_SECONDS" else
                    "Below the band the queue cannot drain in any useful time.")
                   if value < lo else
                   "Above the band risks the live account: suspension is irreversible "
                   "and X free-tier write allowance is about 500 posts a month.")
            )

    for wf in WORKFLOWS:
        wf_path = ROOT / wf
        if not wf_path.exists():
            continue
        for name, values in workflow_defaults(wf_path.read_text(encoding="utf-8")).items():
            lo, hi = BANDS[name]
            for value in values:
                examined.append({"source": wf, "name": name, "value": value, "band": [lo, hi]})
                if not (lo <= value <= hi):
                    failures.append(
                        f"{wf} sets fallback {name}={value}, outside the safe band {lo}..{hi}. "
                        f"A workflow fallback overrides the publisher default whenever the "
                        f"repository variable is unset, which is the case today."
                    )

    # Rule 0: a guard that examined nothing must not report PASS.
    if not examined:
        print(json.dumps({
            "validator": "social_rate_limits",
            "status": "FAIL",
            "hard_failures": 1,
            "config_values_examined": 0,
            "detail": "Found zero social rate-limit configuration values to check. "
                      "The knobs were renamed, removed, or moved out of reach of this "
                      "validator; passing here would vouch for nothing.",
        }, indent=2))
        return 1

    result = {
        "validator": "social_rate_limits",
        "status": "FAIL" if failures else "PASS",
        "hard_failures": len(failures),
        "strong_warnings": 0,
        "soft_warnings": 0,
        "config_values_examined": len(examined),
        "bands": {k: list(v) for k, v in BANDS.items()},
        "examined": examined,
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    if failures:
        print(
            "Social daily limits govern posting to live accounts. Raising them above "
            "the band needs a verified paid X tier and a clean posting history, and the "
            "band in this file must be raised deliberately, in the same commit, with "
            "the evidence written down.",
            file=sys.stderr,
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
