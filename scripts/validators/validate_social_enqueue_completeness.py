#!/usr/bin/env python3
"""Every published page must enter the social distribution queue.

Why this validator exists
-------------------------
scripts/authority_v4_autopilot.py published up to 12 pages a day and then
enqueued social distribution with `published[:li_limit]` (LINKEDIN_DAILY_LIMIT=1)
and `x_pool[:x_limit]`. Because x_pool was built item-outer/template-inner, the
first 5 X slots all belonged to published[0]. The net effect: exactly one page
per day reached the queue on either platform, and 427 of 474 pages (90.1%) that
this repository actually published were never queued for distribution at all --
not deferred, not logged, not visible in any report.

The daily platform rate limits are legitimate and still enforced, but they are
enforced where the rate is actually consumed: scripts/social_publisher.py caps
posts per day and leaves the remainder as `queued_for_auto_post` so it rolls to
the next run. A cap that defers is fine. A cap that drops is not.

This validator fails if a run publishes pages that never reach the queue, so the
enqueue step can never silently regress to slicing again.

Enabled platforms, not all platforms
------------------------------------
The contract is "every published page, for every platform that was switched ON",
and it is evaluated per platform rather than as a union. LinkedIn was paused on
2026-08-29 by an owner decision recorded in data/social-brand-policy.json, so the
contract now expects X only -- honestly, by naming the platforms in the run
receipt, not by weakening the assertion. A union check would also have been
satisfied if X had silently dropped out while LinkedIn kept enqueueing, which is
the failure mode this exists to catch.

A paused platform must ALSO not keep enqueueing. An entry created for a platform
that cannot post is a parked row that reads as imminent work; 581 of them
accumulated that way. So the static contract below additionally requires the
enqueue site to gate on the switch.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lib import social_platforms  # noqa: E402

STATE = ROOT / "data/autopilot-state.json"
QUEUE = ROOT / "data/social-queue.json"
# Runs before this date predate the enqueue fix and carry the historical
# backlog. They are reported as a known deficit, not used to fail the build.
CONTRACT_SINCE = "2026-08-29"


def load(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def main() -> int:
    state = load(STATE, {})
    queue = load(QUEUE, [])
    if isinstance(queue, dict):
        queue = queue.get("items", [])
    history = state.get("history", []) if isinstance(state, dict) else []

    hard_failures = []
    checks_performed = 0

    # --- Static contract on the enqueue site itself -------------------------
    # This is what makes the validator meaningful before the first post-fix run
    # exists, and it is the check that actually prevents the regression: the bug
    # was a slice at enqueue time, so assert no slice is reintroduced there.
    autopilot = ROOT / "scripts/authority_v4_autopilot.py"
    if not autopilot.exists():
        print(json.dumps({
            "status": "FAIL", "hard_failures": 1,
            "detail": "scripts/authority_v4_autopilot.py is missing; the enqueue contract cannot be checked.",
        }, indent=2))
        return 1
    src = autopilot.read_text(encoding="utf-8")
    checks_performed += 1
    policy = social_platforms.load_policy()
    declared_enabled = [p for p in social_platforms.PLATFORMS
                        if social_platforms.declared_enabled(p, policy)]
    declared_paused = [p for p in social_platforms.PLATFORMS if p not in declared_enabled]

    # The enqueue site must consult the switch, or a paused platform silently
    # rebuilds its parked backlog one run at a time.
    checks_performed += 1
    if "enabled_social_platforms" not in src:
        hard_failures.append(
            "scripts/authority_v4_autopilot.py no longer gates enqueue on the platform "
            "switch in data/social-brand-policy.json. Without that gate a paused "
            "platform keeps accumulating queue entries that can never post, which is "
            "how 581 parked LinkedIn rows appeared."
        )
    for plat in declared_paused:
        checks_performed += 1
        if f"'{plat}' in enabled_social_platforms" not in src:
            hard_failures.append(
                f"{plat} is switched off in data/social-brand-policy.json, but "
                f"scripts/authority_v4_autopilot.py does not guard its enqueue loop with "
                f"\"'{plat}' in enabled_social_platforms\". A paused platform must stop "
                f"creating rows, not keep creating rows nothing can post."
            )
    for plat in declared_enabled:
        checks_performed += 1
        if f"'platform': '{plat}'" not in src:
            hard_failures.append(
                f"{plat} is switched ON in data/social-brand-policy.json, but "
                f"scripts/authority_v4_autopilot.py has no enqueue site that emits "
                f"platform '{plat}'. An enabled platform with no enqueue site publishes "
                f"pages that reach nobody."
            )
    for banned, why in (
        ("for item in published[:", "LinkedIn enqueue slices the published list"),
        ("in x_pool[:", "X enqueue slices the candidate pool"),
    ):
        if banned in src:
            hard_failures.append(
                f"scripts/authority_v4_autopilot.py reintroduced an enqueue-time cap ({why}: "
                f"'{banned}...'). Daily platform limits belong in scripts/social_publisher.py, "
                f"where unposted items roll over; slicing here drops them permanently."
            )

    # Rule 0: this validator must never pass by examining nothing.
    if not history:
        print(json.dumps({
            "status": "FAIL",
            "hard_failures": 1,
            "detail": "data/autopilot-state.json has no run history; "
                      "this validator examined zero runs and cannot vouch for anything.",
        }, indent=2))
        return 1

    queued_by_date: dict[str, set] = {}
    for item in queue:
        date = item.get("scheduled_content_date") or item.get("date")
        queued_by_date.setdefault(date, set()).add(item.get("source_path"))

    governed = [r for r in history if r.get("date", "") >= CONTRACT_SINCE and r.get("published", 0) > 0]
    legacy = [r for r in history if r.get("date", "") < CONTRACT_SINCE and r.get("published", 0) > 0]

    legacy_published = sum(r.get("published", 0) for r in legacy)
    legacy_queued = len({p for r in legacy for p in queued_by_date.get(r.get("date"), set())})
    legacy_deficit = legacy_published - legacy_queued

    for run in governed:
        receipt = run.get("social_enqueued")
        if not isinstance(receipt, dict):
            hard_failures.append(
                f"run {run.get('date')} published {run.get('published')} pages but wrote no "
                f"'social_enqueued' receipt; distribution coverage is unverifiable."
            )
            continue
        # Per enabled platform where the receipt records it, union otherwise
        # (receipts written before this contract carry only the union field).
        by_platform = receipt.get("pages_missing_by_platform")
        if isinstance(by_platform, dict):
            platforms_in_play = receipt.get("platforms_enabled") or []
            if not platforms_in_play:
                hard_failures.append(
                    f"run {run.get('date')} published {receipt.get('published_pages')} pages "
                    f"with no platform switched on. Publishing into a network where nothing "
                    f"distributes is a silent stop; if that is intended it must be a recorded "
                    f"decision in data/social-brand-policy.json, not an empty list here."
                )
            for plat in platforms_in_play:
                missing = by_platform.get(plat) or []
                if missing:
                    hard_failures.append(
                        f"run {run.get('date')} published {receipt.get('published_pages')} pages "
                        f"but {len(missing)} never entered the {plat} queue: {missing[:5]}"
                    )
        else:
            missing = receipt.get("pages_missing_social") or []
            if missing:
                hard_failures.append(
                    f"run {run.get('date')} published {receipt.get('published_pages')} pages but "
                    f"{len(missing)} never entered the social queue: {missing[:5]}"
                )

    result = {
        "status": "FAIL" if hard_failures else "PASS",
        "hard_failures": len(hard_failures),
        "checks_performed": checks_performed + len(governed),
        "static_enqueue_contract": "enforced",
        "platforms_enabled": declared_enabled,
        "platforms_paused": social_platforms.paused_platforms(policy),
        "runs_examined": len(governed),
        "legacy_runs_reported_only": len(legacy),
        "legacy_pages_published": legacy_published,
        "legacy_pages_never_queued": legacy_deficit,
        "failures": hard_failures,
    }
    print(json.dumps(result, indent=2))
    if legacy_deficit > 0:
        print(
            f"NOTE: {legacy_deficit} pages published before {CONTRACT_SINCE} were never queued "
            f"for social distribution. They are a real backlog awaiting an explicit backfill "
            f"decision, not an automatic one -- backfilling posts to live accounts.",
            file=sys.stderr,
        )
    return 1 if hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
