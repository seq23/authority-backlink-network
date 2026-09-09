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

Distributing platforms, not merely enabled ones
-----------------------------------------------
The contract is "every published page, for every platform that a published page
still has to REACH", and it is evaluated per platform rather than as a union. A
union check would also have been satisfied if X had silently dropped out while
LinkedIn kept enqueueing, which is the failure mode this exists to catch.

"Has to reach" is not the same question as "is switched on", and this validator
used to ask the wrong one. It asked `declared_enabled()`. Both platforms are
declared `enabled: false`, so it computed an empty set and failed the 2026-09-09
release with "no platform switched on ... if that is intended it must be a
recorded decision in data/social-brand-policy.json". The decision was recorded
there, in full, and had been since 2026-08-29: X is paused for its own paid API
ONLY, `pause_mode: "delivery_route"`, with a switched-on Buffer route that has
accepted 49 posts. The validator could not see the `delivery_route` half of the
declaration, so it named a real distribution drop after a policy gap that did
not exist -- and scripts/authority_v4_autopilot.py had the identical blind spot,
gating its X enqueue loop on `enabled_platforms()`, which is what caused the
drop it was reporting.

Both now ask social_platforms.distributing_platforms(): enabled platforms plus
route-only platforms whose route is switched on. A DORMANT platform is still
excluded -- LinkedIn must not keep enqueueing, because an entry created for a
platform with no way out is a parked row that reads as imminent work and 581 of
them accumulated exactly that way. So the static contract below still requires
the enqueue site to gate every platform, only now on the shared question rather
than on a locally re-derived list.
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
    # The set the contract is evaluated against. Not `declared_enabled`: a
    # platform paused route-only still distributes, through its route, and its
    # published pages must still be enqueued or the route has nothing to carry.
    # Asking the wrong question here is what made this validator report a real
    # distribution drop under a false name -- "no platform switched on ... it
    # must be a recorded decision in data/social-brand-policy.json" -- when the
    # decision was recorded there in full and it was the reader that could not
    # see the `delivery_route` half of it.
    distributing = social_platforms.distributing_platforms(policy)
    routed = social_platforms.routed_platforms(policy)
    dormant = [p for p in social_platforms.PLATFORMS if p not in distributing]

    # The enqueue site must consult the switch, or a dormant platform silently
    # rebuilds its parked backlog one run at a time.
    checks_performed += 1
    if "distributing_social_platforms" not in src:
        hard_failures.append(
            "scripts/authority_v4_autopilot.py no longer gates enqueue on "
            "social_platforms.distributing_platforms(). Gating on enabled_platforms() "
            "alone drops every route-only platform: X's posts leave through Buffer, "
            "and a row that is never created is a post the route can never carry. "
            "Gating on nothing at all rebuilds the 581 parked LinkedIn rows instead."
        )
    for plat in social_platforms.PLATFORMS:
        checks_performed += 1
        if f"'{plat}' in distributing_social_platforms" not in src:
            hard_failures.append(
                f"scripts/authority_v4_autopilot.py does not guard the {plat} enqueue "
                f"loop with \"'{plat}' in distributing_social_platforms\". Every "
                f"platform's enqueue loop must ask the one shared question, so that "
                f"flipping a switch or a delivery route in "
                f"data/social-brand-policy.json is the whole change."
            )
    for plat in distributing:
        checks_performed += 1
        if f"'platform': '{plat}'" not in src:
            hard_failures.append(
                f"{plat} distributes (enabled, or paused route-only with its route "
                f"switched on) per data/social-brand-policy.json, but "
                f"scripts/authority_v4_autopilot.py has no enqueue site that emits "
                f"platform '{plat}'. A distributing platform with no enqueue site "
                f"publishes pages that reach nobody."
            )
    # Rule 0 for the static half: a policy in which nothing distributes at all
    # would make every loop above vacuous, and this validator would pass by
    # checking that no page needs to go anywhere. That is a real silent stop and
    # it fails here, whatever the per-run receipts say.
    checks_performed += 1
    if not distributing:
        hard_failures.append(
            "no platform in data/social-brand-policy.json distributes: every platform is "
            "either switched off dormant or has no switched-on delivery route. Publishing "
            "into a network where nothing distributes is a silent stop. To intend it, "
            "declare it -- a platform paused dormant is a decision; all of them at once, "
            "while pages keep publishing, is an outage."
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
    # Clamped at zero. The backfill enqueued pages beyond those the run receipts
    # counted, so this subtraction went negative and the receipt reported
    # "legacy_pages_never_queued: -74" - a count of a thing that cannot be
    # negative, published as evidence. A surplus means the backlog is covered,
    # not that minus-74 pages are missing.
    legacy_deficit = max(0, legacy_published - legacy_queued)

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
            # `platforms_distributing` is the field written since the route-only
            # gate landed. Receipts from before it carry only `platforms_enabled`,
            # which on those runs meant the same thing, so it is the fallback --
            # not a synonym, a predecessor.
            platforms_in_play = (receipt.get("platforms_distributing")
                                 or receipt.get("platforms_enabled") or [])
            if not platforms_in_play:
                hard_failures.append(
                    f"run {run.get('date')} published {receipt.get('published_pages')} pages "
                    f"and enqueued them for nothing: no platform was switched on and no "
                    f"delivery route was carrying one either. Publishing into a network "
                    f"where nothing distributes is a silent stop, and it is the state this "
                    f"repository was in from the day X was paused route-only while the "
                    f"enqueue gate still asked only which platforms were ENABLED."
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
        "platforms_distributing": distributing,
        "platforms_routed": routed,
        "platforms_dormant": dormant,
        "platforms_paused": social_platforms.paused_platforms(policy),
        "runs_examined": len(governed),
        # The per-run half of this validator iterates `governed`. The existing
        # Rule 0 guard above checks `history`, which is 61 legacy runs and
        # therefore never empty - so it cannot see that the loop below ran zero
        # times. Today it does: the cadence cap holds the autopilot at 0 pages a
        # day, so no run since the contract has published anything. That is a
        # legitimate state, not a failure, but a green receipt must say which
        # half of the check actually ran rather than leaving it to be inferred
        # from a count nobody reads.
        "dynamic_coverage": (
            "per_run_receipts_verified" if governed else
            "VACUOUS: no run since %s has published a page, so the per-run enqueue "
            "check examined nothing. Only the %d static contract checks against "
            "scripts/authority_v4_autopilot.py carry this PASS." % (CONTRACT_SINCE, checks_performed)
        ),
        "legacy_runs_reported_only": len(legacy),
        "legacy_pages_published": legacy_published,
        "legacy_pages_queued": legacy_queued,
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
