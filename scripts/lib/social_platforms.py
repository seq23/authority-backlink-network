#!/usr/bin/env python3
"""One switch per social platform, and the three states a platform can be in.

Why this module exists
----------------------
"Is LinkedIn on?" used to have three different answers depending on where you
looked: ENABLE_LINKEDIN_POSTING defaulted to 'true' in scripts/social_publisher.py,
both workflows hard-coded their own `|| 'true'` fallback, and the operative
answer was actually "no" -- LINKEDIN_ACCESS_TOKEN and LINKEDIN_AUTHOR_URN are
absent from repository secrets. So the platform was off, every run reported it
as on-but-skipped, and 581 LinkedIn entries piled up in data/social-queue.json
at `queued_for_auto_post`, looking like work that was about to happen.

A platform that is off because someone decided to switch it off, and a platform
that is off because a credential went missing, must not look the same. The first
is a decision; the second is an outage. A blank secret cannot tell you which.

So enablement is DECLARED, in data/social-brand-policy.json, and that
declaration is the only switch:

    "platforms": {
      "x":        {"enabled": true,  "daily_limit": 8},
      "linkedin": {"enabled": false, "daily_limit": 3,
                   "paused_on": ..., "paused_by": ..., "paused_reason": ...}
    }

Three states, deliberately distinguishable (see `platform_state`):

    paused_by_switch          enabled:false, with the paused_* record saying who
                              decided and why. Nothing is attempted; the run
                              says so by name.
    on_but_uncredentialled    enabled:true, credentials absent. A named stop,
                              not a failure and not a silent success.
    on_and_posting            enabled:true, credentials present.

And a fourth that is always a build failure: enabled:false with no paused_*
record. That is an undocumented switch-off -- indistinguishable, from the
outside, from something quietly breaking. scripts/validators/validate_social_rate_limits.py
fails on exactly that shape.

Parked queue entries are DERIVED, never stamped
-----------------------------------------------
A LinkedIn entry that cannot post while the switch is off keeps its own status
of `queued_for_auto_post`. It is not rewritten to `not_for_posting`, and it
carries no per-row pause marker, because a row-level mark has to be hunted down
and reversed row by row when the switch flips back. `partition_queue` computes
"parked because its platform is paused" on the fly from the switch, so flipping
`enabled` back to true restores all 581 entries at once with no queue edit, no
un-marking pass and no re-backfill.

That is different from `not_for_posting`, which scripts/prioritize_social_queue.py
writes onto entries retired as DUPLICATES. Those are retired on their own merits
and stay retired whatever the switch says.

ENABLE_<PLATFORM>_POSTING still exists as the per-run override and still wins
when set to a real value; the test fixtures use it. Unset or blank falls through
to the declaration, so there is exactly one durable answer and one temporary
override, with no hard-coded third opinion.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Overridable for tests only, exactly like SOCIAL_QUEUE_PATH in the publisher.
# Nothing in CI or the workflows sets it, so the committed declaration governs.
POLICY_PATH = Path(os.getenv("SOCIAL_PLATFORM_POLICY_PATH",
                             str(ROOT / "data/social-brand-policy.json")))

# Every platform this repository can post to, and the env override for each. A
# platform absent from the declaration defaults to ON, so adding a platform
# never requires editing the declaration first -- only turning one OFF requires
# a written decision.
PLATFORMS = ("linkedin", "x")
ENV_OVERRIDE = {"linkedin": "ENABLE_LINKEDIN_POSTING", "x": "ENABLE_X_POSTING"}
PAUSE_FIELDS = ("paused_on", "paused_by", "paused_reason")

# Statuses an entry must hold to be a candidate for posting at all. Kept in step
# with POSTABLE_STATUSES in scripts/social_publisher.py.
POSTABLE_STATUSES = {"queued_for_auto_post", "approved_for_auto_post"}

TRUTHY = {"1", "true", "yes", "y", "on"}
FALSEY = {"0", "false", "no", "n", "off"}

STATE_PAUSED = "paused_by_switch"
STATE_UNDOCUMENTED_OFF = "off_without_a_recorded_decision"
STATE_UNCREDENTIALLED = "on_but_uncredentialled"
STATE_ON = "on_and_posting"


def load_policy(path=None) -> dict:
    p = Path(path) if path else POLICY_PATH
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def declaration(platform: str, policy=None) -> dict:
    """The declared record for one platform. Missing == on, no paperwork needed."""
    policy = load_policy() if policy is None else policy
    platforms = policy.get("platforms") or {}
    entry = platforms.get(platform)
    return entry if isinstance(entry, dict) else {}


def declared_enabled(platform: str, policy=None) -> bool:
    return bool(declaration(platform, policy).get("enabled", True))


def declared_daily_limit(platform: str, policy=None):
    value = declaration(platform, policy).get("daily_limit")
    return value if isinstance(value, int) else None


def pause_record(platform: str, policy=None):
    """The pause record, or None if the platform is not properly declared paused.

    Paused means: switched off WITH the paperwork. Switched off without it
    returns None on purpose, so the validator can fail on exactly that case
    instead of accepting a bare `enabled: false`.
    """
    entry = declaration(platform, policy)
    if entry.get("enabled", True):
        return None
    if not all(entry.get(f) for f in PAUSE_FIELDS):
        return None
    return {f: entry.get(f) for f in PAUSE_FIELDS}


def missing_pause_fields(platform: str, policy=None) -> list:
    entry = declaration(platform, policy)
    if entry.get("enabled", True):
        return []
    return [f for f in PAUSE_FIELDS if not entry.get(f)]


def is_enabled(platform: str, policy=None) -> bool:
    """Declared state, overridable by ENABLE_<PLATFORM>_POSTING when it is set.

    Unset OR blank falls through to the declaration. Blank matters: the
    workflows pass `${{ vars.ENABLE_LINKEDIN_POSTING }}`, which expands to an
    empty string when the repository variable does not exist, and empty must
    mean "no opinion", not "false".
    """
    raw = (os.getenv(ENV_OVERRIDE.get(platform, "")) or "").strip().lower()
    if raw in TRUTHY:
        return True
    if raw in FALSEY:
        return False
    return declared_enabled(platform, policy)


def enabled_platforms(policy=None) -> list:
    return [p for p in PLATFORMS if is_enabled(p, policy)]


def paused_platforms(policy=None) -> dict:
    """Platforms switched off with a recorded decision, keyed by platform."""
    out = {}
    for p in PLATFORMS:
        rec = pause_record(p, policy)
        if rec is not None and not is_enabled(p, policy):
            out[p] = rec
    return out


def platform_state(platform: str, missing_secrets=None, policy=None) -> str:
    """Which of the distinguishable states this platform is in right now.

    `missing_secrets` is the caller's credential check (the publisher owns that,
    since only it knows which env vars each API needs). Pass None when the
    caller has not checked -- the credential states are then not reported.
    """
    if not is_enabled(platform, policy):
        return STATE_PAUSED if pause_record(platform, policy) else STATE_UNDOCUMENTED_OFF
    if missing_secrets:
        return STATE_UNCREDENTIALLED
    return STATE_ON


def partition_queue(queue, policy=None):
    """Split queue entries into what can post now and what is parked by a switch.

    Derived, not stamped. `parked` entries still carry their own
    `queued_for_auto_post` status and are restored in full the instant the
    platform's `enabled` flips back to true -- no queue rewrite, no per-row
    un-marking, no re-backfill.
    """
    enabled = set(enabled_platforms(policy))
    postable, parked = [], {}
    for i, item in enumerate(queue):
        if item.get("status") not in POSTABLE_STATUSES:
            continue
        platform = item.get("platform")
        if platform in PLATFORMS and platform not in enabled:
            parked.setdefault(platform, []).append(i)
        else:
            postable.append(i)
    return postable, parked
