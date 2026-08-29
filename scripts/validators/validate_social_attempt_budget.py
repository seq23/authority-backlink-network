#!/usr/bin/env python3
"""The posting caps must hold when posting is FAILING, not only when it works.

What went wrong
---------------
On 2026-08-29 the social publisher made 581 requests to X in 76 seconds against
`X_DAILY_LIMIT=8`, `SOCIAL_RUN_LIMIT=3` and a jittered 90-second interval. Every
one of those numbers was correct, declared, in band, and validated. None of them
governed anything, because all three were counted against SUCCESSES:

    if platform == 'x' and posted_today['x'] >= x_limit:  continue
    if posted_this_run.get(platform, 0) >= run_limit:     continue
    if ... (posted_this_run['linkedin'] + posted_this_run['x']) > 0: sleep(...)

`posted_*` only ever incremented on a successful post. X answered HTTP 402
(credits depleted) and then HTTP 429 (too many requests), so nothing succeeded,
so no counter moved, so the loop walked the entire queue at full speed - and
kept issuing requests for 481 consecutive attempts after the platform had
explicitly said stop. Then, because a failed attempt was stamped `post_failed`
and no postable set contains that status, all 581 entries left the queue for
good: the X backlog went from 581 to zero eligible items in one run, with the
workflow green and the report calling it `partial_failure`.

Both halves of that are invisible to a validator that reads configuration.
scripts/validators/validate_social_rate_limits.py checks that the numbers are
declared and inside a safe band, and it passed throughout - it is a guard that
cannot reach what it governs. The only way to know a cap holds is to run the
thing and count the calls, so this validator does that.

What it proves
--------------
It drives the REAL scripts/social_publisher.py against a synthetic queue with
the platform API stubbed, and asserts, per scenario:

  every post succeeds     -> exactly SOCIAL_RUN_LIMIT requests, spaced
  every post fails softly -> exactly SOCIAL_RUN_LIMIT requests, spaced,
                             and every entry is still postable afterwards
  platform refuses (429)  -> the run stops after ONE request
  platform refuses (402)  -> the run stops after ONE request

The failing scenarios are the point. A publisher that passes the success case
and fails the others is precisely the state this repository shipped.

It also checks the arithmetic across a whole day. SOCIAL_RUN_LIMIT is a slice
per run, so the day's exposure is that slice times the number of scheduled
runs - four crons in social-autopost.yml plus the autopilot lane, which is 15
against a daily cap of 8. The run limit alone therefore does NOT bound the day;
only a daily budget that counts attempts does. The runs-per-day figure is
derived by counting the crons in the workflow files rather than restated here,
so adding a fifth cron cannot silently widen the day's exposure.

Finally it fails if any entry in the committed queue still carries
`post_failed`, the status the defect stamped. Current code never writes it, so
its presence means either the old build is back or the 581 were never restored.

Fails hard if it exercises zero scenarios.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLISHER = ROOT / "scripts" / "social_publisher.py"
QUEUE = ROOT / "data" / "social-queue.json"
AUTOPOST_WF = ROOT / ".github" / "workflows" / "social-autopost.yml"
AUTOPILOT_WF = ROOT / ".github" / "workflows" / "authority-v4-autopilot.yml"

X_DAILY_LIMIT = 8
RUN_LIMIT = 3
QUEUE_SIZE = 40

# Distinct 4+-letter vocabulary per entry. The publisher's similarity guard
# reduces a body to its 4+-letter words, so a fixture whose bodies collapse to a
# shared token would be suppressed as duplicates and the rate question would
# never be reached - the fixture would pass by not testing anything.
VOCAB = [
    w + s
    for s in ("alpha", "bravo", "delta", "gamma", "omega", "sigma", "theta", "kappa")
    for w in (
        "quiet", "river", "stone", "amber", "cedar", "falcon", "harbor", "ivory",
        "juniper", "lantern", "meadow", "nimbus", "orchid", "pewter", "quartz",
        "saffron", "tundra", "velvet", "willow", "zephyr",
    )
]

SCENARIOS = {
    "every_post_succeeds": {"ok": True},
    "soft_failure": {"ok": False, "error": "transient_network_wobble"},
    "rate_limited_429": {"ok": False, "error": 'HTTP 429: {"detail":"Too Many Requests"}'},
    "credits_depleted_402": {"ok": False, "error": 'HTTP 402: {"detail":"credits depleted"}'},
}
# Responses that mean the platform has refused the account outright. The run
# must stop, not walk the queue.
HALTING = {"rate_limited_429", "credits_depleted_402"}


def synthetic_queue(n=QUEUE_SIZE):
    return [
        {
            "platform": "x",
            "brand": f"Brand {i % 7}",
            "domain": f"example{i % 7}.com",
            "post_type": "link_share",
            "body": " ".join(VOCAB[(i * 17 + j) % len(VOCAB)] for j in range(12)),
            "target_url": f"https://example{i % 7}.com/page-{i}",
            "status": "queued_for_auto_post",
            "created_at": "2026-08-01",
        }
        for i in range(n)
    ]


def load_publisher():
    """Fresh module instance, so per-run module state cannot leak between runs."""
    # social_publisher.py does `from lib import social_platforms`, which resolves
    # only with scripts/ on the path.
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("social_publisher_probe", PUBLISHER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["social_publisher_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


def drive(queue_path, report_path, response, runs=1):
    """Run the publisher `runs` times against one queue file. Returns call counts."""
    # No Buffer token, ever: this file is about the platform's own API, and an
    # ambient token would open the delivery route mid-scenario and change what
    # every property here measures. The route has its own guard,
    # scripts/validators/validate_buffer_route.py.
    os.environ.pop("BUFFER_ACCESS_TOKEN", None)
    os.environ.update({
        "SOCIAL_QUEUE_PATH": str(queue_path),
        "SOCIAL_REPORT_PATH": str(report_path),
        "SOCIAL_DRY_RUN": "false",
        "REQUIRE_SOCIAL_SECRETS": "false",
        "X_DAILY_LIMIT": str(X_DAILY_LIMIT),
        "SOCIAL_RUN_LIMIT": str(RUN_LIMIT),
        "SOCIAL_POST_MIN_INTERVAL_SECONDS": "90",
        "ENABLE_X_POSTING": "true",
        "ENABLE_LINKEDIN_POSTING": "false",
        # The stub replaces post_item outright; these only get the run past the
        # credential gate so the posting loop is reached. Nothing authenticates.
        "X_API_KEY": "stub", "X_API_SECRET": "stub",
        "X_ACCESS_TOKEN": "stub", "X_ACCESS_TOKEN_SECRET": "stub",
    })
    per_run = []
    sleeps_total = 0
    for _ in range(runs):
        mod = load_publisher()
        calls = [0]
        sleeps = [0]

        def stub_post(item, dry_run=False, route=None, _c=calls):
        # `route` is the delivery-route argument the publisher now passes
        # (scripts/lib/buffer_route.py). None here: these harnesses run without
        # a Buffer token. Accepting it keeps the stub matching the real
        # signature, instead of every call raising TypeError and being recorded
        # as a platform refusal.
            _c[0] += 1
            if response.get("ok"):
                return {"ok": True, "id": f"stub-{_c[0]}", "status": 201}
            return dict(response)

        def stub_sleep(seconds, _s=sleeps):
            _s[0] += 1

        mod.post_item = stub_post
        mod.time.sleep = stub_sleep
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                mod.main()
            except SystemExit:
                pass
        per_run.append(calls[0])
        sleeps_total += sleeps[0]
    report = json.loads(Path(report_path).read_text())
    final_queue = json.loads(Path(queue_path).read_text())
    postable = sum(1 for i in final_queue if i.get("status") in mod.POSTABLE_STATUSES)
    return {
        "calls_per_run": per_run,
        "calls_total": sum(per_run),
        "sleeps": sleeps_total,
        "postable_after": postable,
        "report_status": report.get("status"),
    }


def runs_per_day():
    """Count scheduled invocations of the publisher, rather than restating one.

    Adding a cron must change this number, otherwise the day's exposure could be
    widened without anything noticing.
    """
    crons = 0
    if AUTOPOST_WF.exists():
        crons += len(re.findall(r"^\s*-\s*cron:", AUTOPOST_WF.read_text(encoding="utf-8"), re.M))
    autopilot_posts = (
        AUTOPILOT_WF.exists()
        and "social_publisher.py" in AUTOPILOT_WF.read_text(encoding="utf-8")
    )
    return crons + (1 if autopilot_posts else 0)


def main() -> int:
    failures = []
    checks = []

    if not PUBLISHER.exists():
        print(json.dumps({
            "validator": "social_attempt_budget", "status": "FAIL", "hard_failures": 1,
            "detail": f"{PUBLISHER} is missing; the attempt budget cannot be exercised.",
        }, indent=2))
        return 1

    tmp = Path(tempfile.mkdtemp())
    for name, response in SCENARIOS.items():
        qp = tmp / f"{name}-queue.json"
        rp = tmp / f"{name}-report.json"
        qp.write_text(json.dumps(synthetic_queue()))
        out = drive(qp, rp, response)
        calls = out["calls_total"]
        expected = 1 if name in HALTING else RUN_LIMIT
        checks.append({
            "scenario": name, "queue_size": QUEUE_SIZE, "run_limit": RUN_LIMIT,
            "requests_made": calls, "requests_expected": expected,
            "sleeps": out["sleeps"], "postable_after": out["postable_after"],
            "report_status": out["report_status"],
        })
        if calls > expected:
            failures.append(
                f"scenario {name}: the publisher made {calls} platform requests against a "
                f"per-run limit of {RUN_LIMIT} and a queue of {QUEUE_SIZE}"
                + (
                    f". A platform that answered a refusal must stop the run after the "
                    f"first request, not keep calling an endpoint that has just said stop."
                    if name in HALTING else
                    ". The per-run slice must bound REQUESTS, not successes: counting "
                    "successes means a run where everything fails is not bounded at all."
                )
            )
        if name != "every_post_succeeds" and out["postable_after"] < QUEUE_SIZE:
            failures.append(
                f"scenario {name}: only {out['postable_after']} of {QUEUE_SIZE} entries are "
                f"still postable after a run in which nothing was posted. A failed attempt "
                f"must defer its entry, never retire it - stamping a terminal status on a "
                f"platform-side failure is what silently emptied the X queue of all 581 "
                f"entries on 2026-08-29."
            )
        if name == "soft_failure" and out["sleeps"] < RUN_LIMIT - 1:
            failures.append(
                f"scenario {name}: {out['sleeps']} inter-post delays were taken across "
                f"{calls} requests. Spacing must be keyed on attempts; a run whose posts are "
                f"all failing is exactly when unspaced requests look worst to the platform."
            )
        if name != "every_post_succeeds" and out["report_status"] == "partial_failure":
            failures.append(
                f"scenario {name}: the run reported 'partial_failure' with zero successes. "
                f"A run that got nothing out must say so; 'partial' is how 581 of 581 "
                f"failures were reported as a qualified success."
            )

    # A whole day, across every scheduled lane.
    per_day = runs_per_day()
    qp = tmp / "day-queue.json"
    rp = tmp / "day-report.json"
    qp.write_text(json.dumps(synthetic_queue()))
    day = drive(qp, rp, SCENARIOS["soft_failure"], runs=per_day)
    checks.append({
        "scenario": "full_day_all_failing", "runs_per_day": per_day,
        "run_limit": RUN_LIMIT, "unbounded_exposure": RUN_LIMIT * per_day,
        "daily_limit": X_DAILY_LIMIT, "requests_made": day["calls_total"],
        "calls_per_run": day["calls_per_run"], "postable_after": day["postable_after"],
    })
    if per_day < 2:
        failures.append(
            f"Found {per_day} scheduled publisher invocations by reading the workflow files. "
            f"That is too few to be real and means this check is no longer measuring the "
            f"day's exposure at all."
        )
    if day["calls_total"] > X_DAILY_LIMIT:
        failures.append(
            f"Across {per_day} scheduled runs with every post failing, the publisher made "
            f"{day['calls_total']} requests against a daily cap of {X_DAILY_LIMIT}. The "
            f"per-run slice of {RUN_LIMIT} allows {RUN_LIMIT * per_day} a day on its own, so "
            f"the daily budget is the only thing bounding this, and it has to count attempts "
            f"to do so - a budget spent only on successes does not exist on a bad day."
        )
    if day["postable_after"] < QUEUE_SIZE:
        failures.append(
            f"After a full day in which every post failed, {day['postable_after']} of "
            f"{QUEUE_SIZE} entries remain postable. A bad day must cost the queue nothing."
        )

    # The committed queue must not carry the status the defect stamped.
    if QUEUE.exists():
        live = json.loads(QUEUE.read_text(encoding="utf-8"))
        live = live.get("items", []) if isinstance(live, dict) else live
        stamped = [i for i, item in enumerate(live) if item.get("status") == "post_failed"]
        checks.append({
            "scenario": "committed_queue_free_of_legacy_post_failed",
            "entries": len(live), "post_failed_rows": len(stamped),
        })
        if stamped:
            failures.append(
                f"{len(stamped)} entries in data/social-queue.json still carry status "
                f"'post_failed' (indices {stamped[:5]}). Current code never writes that "
                f"status - an attempt that fails is deferred, or retired as "
                f"'failed_permanent' if the entry itself is unpostable. Its presence means "
                f"those entries are in no postable set and their pages are silently never "
                f"distributed. scripts/social_publisher.py restores them on its next run."
            )

    # Rule 0: a guard that exercised nothing must not report PASS.
    if not checks:
        print(json.dumps({
            "validator": "social_attempt_budget", "status": "FAIL", "hard_failures": 1,
            "scenarios_exercised": 0,
            "detail": "Exercised zero scenarios; passing here would vouch for nothing.",
        }, indent=2))
        return 1

    result = {
        "validator": "social_attempt_budget",
        "status": "FAIL" if failures else "PASS",
        "hard_failures": len(failures),
        "strong_warnings": 0,
        "soft_warnings": 0,
        "scenarios_exercised": len(checks),
        "runs_per_day_derived": per_day,
        "checks": checks,
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
