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

Switched-off platforms
----------------------
A platform can legitimately be switched off. LinkedIn is, as of 2026-08-29, by
an explicit owner decision recorded in data/social-brand-policy.json. While a
platform's switch is off, its daily-limit band is not a live constraint: nothing
is posting, so no number in the publisher governs anything.

That is not licence to stop checking. The rules below replace the band with
something stricter for the off case, because the whole point is that "off" and
"misconfigured" must never look the same to this validator:

  * A platform declared `enabled: false` MUST carry paused_on, paused_by and
    paused_reason. Off with no recorded decision fails the build. That is the
    case this validator exists to catch -- it is exactly what a credential
    quietly going missing looks like.

  * The declared `daily_limit` stays inside the band even while paused. The
    switch is meant to be flipped back by hand at any time, and flipping it must
    not require also remembering to fix a number. A paused platform parked at
    daily_limit 0 or 40 would turn one edit into two, and the second one is the
    one that gets forgotten.

  * A platform whose switch is ON is banded exactly as before, in the publisher
    default and in every workflow fallback. Re-enabling LinkedIn inside the safe
    band therefore passes without touching this file.

  * The enablement decision must live in the declaration and nowhere else. A
    literal `|| 'true'` or `|| 'false'` fallback in a workflow, or a literal
    default in the publisher, is a second answer to the question the declaration
    answers, and is rejected on sight -- that duplication is how the repository
    ended up reporting LinkedIn as enabled for weeks while it could not post.

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
sys.path.insert(0, str(ROOT / "scripts"))
from lib import social_platforms  # noqa: E402

# (minimum, maximum) inclusive. See the docstring for how these were chosen.
BANDS = {
    "X_DAILY_LIMIT": (5, 12),
    "LINKEDIN_DAILY_LIMIT": (2, 5),
    "SOCIAL_RUN_LIMIT": (1, 5),
    "SOCIAL_POST_MIN_INTERVAL_SECONDS": (45, 3600),
}

PUBLISHER = "scripts/social_publisher.py"
POLICY = "data/social-brand-policy.json"
# The env var each platform's band is expressed through, and the switch record
# that governs whether that band is live.
PLATFORM_LIMIT_ENV = {"linkedin": "LINKEDIN_DAILY_LIMIT", "x": "X_DAILY_LIMIT"}
# A literal enablement default anywhere but the declaration is a second answer
# to a question with one answer.
ENABLEMENT_LITERAL = re.compile(
    r"ENABLE_(?:LINKEDIN|X)_POSTING\s*:\s*\$\{\{[^}]*\|\|[^}]*\}\}")
PUBLISHER_ENABLEMENT_LITERAL = re.compile(
    r"os\.getenv\(\s*['\"]ENABLE_(?:LINKEDIN|X)_POSTING['\"]|"
    r"truthy\(\s*['\"]ENABLE_(?:LINKEDIN|X)_POSTING['\"]")
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


def switch_audit(policy, failures, examined):
    """Check the declaration itself: paperwork, band, and single-source-of-truth.

    Returns the set of env var names whose band is NOT live because the platform
    behind them is switched off.
    """
    dormant_envs = set()
    declared = (policy.get("platforms") or {})
    if not isinstance(declared, dict) or not any(
        isinstance(v, dict) for v in declared.values()
    ):
        failures.append(
            f"{POLICY} has no usable 'platforms' block. That block is the only switch "
            f"for social posting; without it nothing in this repository records whether "
            f"a platform is on, and 'off' becomes indistinguishable from 'broken'."
        )
        return dormant_envs

    for platform, env_name in PLATFORM_LIMIT_ENV.items():
        entry = declared.get(platform)
        if not isinstance(entry, dict):
            failures.append(
                f"{POLICY} platforms.{platform} is missing. Every platform this "
                f"repository can post to must declare its switch, so that being off is "
                f"always a recorded decision rather than an absence."
            )
            continue
        enabled = bool(entry.get("enabled", True))
        missing = social_platforms.missing_pause_fields(platform, policy)
        examined.append({
            "source": POLICY, "name": f"platforms.{platform}.enabled",
            "value": enabled, "band": None,
        })
        if not enabled:
            dormant_envs.add(env_name)
            if missing:
                failures.append(
                    f"{POLICY} switches {platform} off (enabled: false) but records no "
                    f"{', '.join(missing)}. A platform that is off without a written "
                    f"decision is indistinguishable from one whose credentials quietly "
                    f"went missing, which is the exact confusion this guard exists to "
                    f"prevent. Add who paused it, when, and why -- or set enabled: true."
                )

        # The declared limit is banded whether the switch is on or off: the switch
        # is meant to be flipped back by hand, and flipping it must not also
        # require remembering to repair a number.
        lo, hi = BANDS[env_name]
        limit = entry.get("daily_limit")
        if not isinstance(limit, int):
            failures.append(
                f"{POLICY} platforms.{platform}.daily_limit is missing or not an "
                f"integer. It is the value the switch hands back when {platform} is "
                f"turned on, so it has to be safe before anyone flips it."
            )
        else:
            examined.append({
                "source": POLICY, "name": f"platforms.{platform}.daily_limit",
                "value": limit, "band": [lo, hi],
            })
            if not (lo <= limit <= hi):
                failures.append(
                    f"{POLICY} platforms.{platform}.daily_limit={limit} is outside the "
                    f"safe band {lo}..{hi}. Turning {platform} back on is supposed to be "
                    f"one edit; a bad limit parked here makes it two, and the second one "
                    f"is the one that gets forgotten."
                )
    return dormant_envs


def single_source_audit(pub_text, failures, examined):
    """No file may carry its own literal answer to 'is this platform on?'."""
    examined.append({"source": PUBLISHER, "name": "enablement_source", "value": "declaration", "band": None})
    if PUBLISHER_ENABLEMENT_LITERAL.search(pub_text):
        failures.append(
            f"{PUBLISHER} reads ENABLE_*_POSTING with its own literal default again. "
            f"Enablement is declared in {POLICY} and overridden by the environment; a "
            f"literal default here is a third opinion, and it is how this repository "
            f"reported LinkedIn as enabled for weeks while it could not post."
        )
    # Per platform, not once for the file: checking only that the call appears
    # somewhere passes happily while one platform has been hard-wired to True.
    for plat in PLATFORM_LIMIT_ENV:
        if f"social_platforms.is_enabled('{plat}'" not in pub_text:
            failures.append(
                f"{PUBLISHER} no longer resolves {plat} enablement through "
                f"social_platforms.is_enabled('{plat}', ...), so the switch in {POLICY} "
                f"governs nothing for {plat} and a paused platform could still post."
            )
    for wf in WORKFLOWS:
        wf_path = ROOT / wf
        if not wf_path.exists():
            continue
        text = wf_path.read_text(encoding="utf-8")
        examined.append({"source": wf, "name": "enablement_source", "value": "declaration", "band": None})
        hits = ENABLEMENT_LITERAL.findall(text)
        if hits:
            failures.append(
                f"{wf} hard-codes an enablement fallback ({hits[0].strip()}). A "
                f"workflow fallback overrides the declaration whenever the repository "
                f"variable is unset, which is the case today, so the switch in {POLICY} "
                f"would stop being the switch. Pass the variable through bare instead."
            )


def main() -> int:
    failures = []
    examined = []

    policy = social_platforms.load_policy(ROOT / POLICY)
    dormant_envs = switch_audit(policy, failures, examined)

    pub_path = ROOT / PUBLISHER
    if not pub_path.exists():
        print(json.dumps({
            "validator": "social_rate_limits", "status": "FAIL", "hard_failures": 1,
            "detail": f"{PUBLISHER} is missing; the rate-limit contract cannot be checked.",
        }, indent=2))
        return 1

    text = pub_path.read_text(encoding="utf-8")
    single_source_audit(text, failures, examined)
    found = publisher_defaults(text)
    for name, (lo, hi) in BANDS.items():
        if name in dormant_envs:
            # The platform behind this knob is switched off with a recorded
            # decision, so the number governs nothing this run. It is still
            # reported, and the DECLARED limit above is still banded, so
            # flipping the switch back on cannot land outside the band.
            examined.append({"source": PUBLISHER, "name": name,
                             "value": found.get(name), "band": [lo, hi],
                             "band_live": False,
                             "why": "platform switched off with a recorded decision"})
            continue
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
                if name in dormant_envs:
                    examined.append({"source": wf, "name": name, "value": value,
                                     "band": [lo, hi], "band_live": False,
                                     "why": "platform switched off with a recorded decision"})
                    continue
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
        "platform_switches": {
            plat: {
                "enabled": social_platforms.declared_enabled(plat, policy),
                "declared_daily_limit": social_platforms.declared_daily_limit(plat, policy),
                "band_live": PLATFORM_LIMIT_ENV[plat] not in dormant_envs,
                "pause_record": social_platforms.pause_record(plat, policy),
            }
            for plat in PLATFORM_LIMIT_ENV
        },
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
