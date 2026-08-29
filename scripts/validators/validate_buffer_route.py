#!/usr/bin/env python3
"""A second way out for X must not become a second way to burn the account.

What this guards
----------------
X's own API is pay-per-use and unfunded, so it is switched off and contacted
zero times. Buffer carries the same posts to the same X profile for nothing, as
a DELIVERY ROUTE declared on platforms.x.delivery_route in
data/social-brand-policy.json. Adding a second way for a post to leave adds
exactly four ways to do damage, and each one has already happened somewhere in
this repository's short history:

  post twice          the hand-post sheet offers eight posts and the route
                      takes the same eight. She posts them; Buffer posts them
                      again. Two identical posts on one profile, from a system
                      whose whole purpose is to look like a person.
  run past a refusal  on 2026-08-29 this repository made 581 requests in 76
                      seconds because its caps counted successes rather than
                      attempts, so one refusal cost one request per queue
                      entry. A route that retries is that failure again.
  exceed the ceiling  Buffer publishes the limit it will accept
                      (dailyPostingLimits). Guessing it, or counting only what
                      succeeded, is how an account gets locked.
  eat the queue       1,162 entries are waiting. A delivery lane that consumes
                      or retires them takes the network's distribution with it.

And one that would be worse than all of them: BUFFER_ACCESS_TOKEN reaching a
log, a report or a commit. The publisher prints its whole report into the
workflow log and commits it to reports/.

Each property below is driven through the REAL publisher and the REAL route
with only Buffer's transport stubbed, and each is proved NEGATIVELY -- the
opposite configuration is run too, and the behaviour has to flip. A check that
passes both ways proves nothing.

Fails hard if it exercises zero properties.
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

PUBLISHER = ROOT / "scripts" / "social_publisher.py"
POLICY = ROOT / "data" / "social-brand-policy.json"
LIVE_QUEUE = ROOT / "data" / "social-queue.json"

# A value that could not occur by accident, so finding it anywhere is proof
# rather than coincidence.
CANARY_TOKEN = "buffer-canary-2b7f1c9e-never-log-me"
GUARDED_STATUSES = ("queued_for_auto_post", "not_for_posting",
                    "draft_requires_human_approval")

VOCAB = [w + s for s in ("alpha", "bravo", "delta", "gamma", "omega", "sierra")
         for w in ("quiet", "river", "stone", "amber", "cedar", "falcon", "harbor",
                   "ivory", "juniper", "lantern", "meadow", "nimbus")]


def synthetic_queue(n=30):
    """Deliberately dissimilar bodies: the same-day similarity guard would
    otherwise skip most of them and every cap below would pass for the wrong
    reason."""
    return [
        {
            "platform": "x",
            "brand": f"Brand {i}",
            "domain": f"example{i}.com",
            "post_type": "link_share",
            "body": " ".join(VOCAB[(i * 17 + j * 7) % len(VOCAB)] for j in range(18))
                    + f" entry number {i} of the synthetic fixture",
            "source_url": f"https://example{i}.com/daily/2026-08-29-entry-{i}.html",
            "status": "queued_for_auto_post",
            "created_at": "2026-08-01",
        }
        for i in range(n)
    ]


def load_publisher():
    for name in ("social_drafts", "lib", "lib.social_platforms", "lib.buffer_route",
                 "lib.social_selection", "social_publisher_buffer_probe"):
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location("social_publisher_buffer_probe", PUBLISHER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["social_publisher_buffer_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


def buffer_stub(calls, limit=25, used=0, channel_service="twitter",
                refuse_after=None, refusal="LimitReachedError"):
    """Stand in for Buffer's GraphQL endpoint, recording every request.

    `refuse_after` makes createPost refuse from the Nth call onward, which is
    how "halts on the first refusal" is measured: the stub would happily answer
    a thousand more.
    """
    def graphql(query, variables=None, timeout=30, opener=None):
        calls["all"].append(query.strip().split("\n")[1].strip() if "\n" in query else query)
        if "organizations" in query:
            return {"account": {"id": "acc", "organizations": [
                {"id": "org", "name": "My Organization",
                 "limits": {"channels": 3, "scheduledPosts": 10}}]}}
        if "channels(input" in query:
            if channel_service is None:
                return {"channels": []}
            return {"channels": [{"id": "ch-x", "name": "westpeek",
                                  "service": channel_service, "isDisconnected": False,
                                  "isLocked": False, "isQueuePaused": False}]}
        if "dailyPostingLimits" in query:
            return {"dailyPostingLimits": [{"channelId": "ch-x", "isAtLimit": False,
                                            "limit": limit, "scheduled": used, "sent": 0}]}
        if "createPost" in query:
            calls["createPost"].append(variables["input"])
            n = len(calls["createPost"])
            if refuse_after is not None and n >= refuse_after:
                return {"createPost": {"__typename": refusal,
                                       "message": "Buffer says no"}}
            return {"createPost": {"__typename": "PostActionSuccess",
                                   "post": {"id": f"buf-{n}", "status": "scheduled",
                                            "dueAt": "2026-08-30T14:00:00Z",
                                            "channelId": "ch-x"}}}
        raise AssertionError(f"unexpected query: {query[:80]}")
    return graphql


def drive(tmp, name, policy, queue=None, token=CANARY_TOKEN, ledger=None,
          run_limit=20, **stub):
    """Run the REAL publisher with only Buffer's transport replaced.

    Every route out is counted: post_item, the two platform senders, and
    urlopen itself. A route that quietly called X's API would be caught at the
    third even if it bypassed the first two.
    """
    qp, rp = tmp / f"{name}-queue.json", tmp / f"{name}-report.json"
    lp, dp = tmp / f"{name}-ledger.json", tmp / f"{name}-drafts.md"
    pp = tmp / f"{name}-policy.json"
    pp.write_text(json.dumps(policy, indent=2))
    qp.write_text(json.dumps(queue if queue is not None else synthetic_queue(), indent=2))
    if ledger is not None:
        lp.write_text(json.dumps(ledger, indent=2))
    queue_before = json.loads(qp.read_text())

    for var in ("ENABLE_X_POSTING", "ENABLE_LINKEDIN_POSTING",
                "ENABLE_X_BUFFER_ROUTE"):
        os.environ.pop(var, None)
    os.environ.update({
        "SOCIAL_PLATFORM_POLICY_PATH": str(pp), "SOCIAL_QUEUE_PATH": str(qp),
        "SOCIAL_REPORT_PATH": str(rp), "SOCIAL_DRAFT_LEDGER_PATH": str(lp),
        "SOCIAL_DRAFTS_PATH": str(dp), "SOCIAL_DRY_RUN": "false",
        "REQUIRE_SOCIAL_SECRETS": "false", "X_DAILY_LIMIT": "8",
        "LINKEDIN_DAILY_LIMIT": "3", "SOCIAL_RUN_LIMIT": str(run_limit),
        "SOCIAL_POST_MIN_INTERVAL_SECONDS": "0",
    })
    if token:
        os.environ["BUFFER_ACCESS_TOKEN"] = token
    else:
        os.environ.pop("BUFFER_ACCESS_TOKEN", None)

    mod = load_publisher()
    calls = {"createPost": [], "all": [], "x_api": [], "urlopen": []}
    mod.buffer_route.graphql = buffer_stub(calls, **stub)
    mod.x_post = lambda text: calls["x_api"].append(text) or {"ok": True, "id": "x"}
    mod.linkedin_post = lambda text: {"ok": True, "id": "li"}
    mod.urllib.request.urlopen = lambda *a, **k: calls["urlopen"].append(1) or (
        _ for _ in ()).throw(AssertionError("a real network call was attempted"))
    mod.time.sleep = lambda *a, **k: None
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        try:
            mod.main()
        except SystemExit:
            pass
    queue_after = json.loads(qp.read_text())
    return {
        "report": json.loads(rp.read_text()),
        "queue_before": queue_before, "queue_after": queue_after,
        "ledger": json.loads(lp.read_text()) if lp.exists() else {},
        "sheet": dp.read_text() if dp.exists() else "",
        "stdout": stdout.getvalue(),
        "create_calls": len(calls["createPost"]),
        "sent_texts": [c.get("text") for c in calls["createPost"]],
        "x_api_calls": len(calls["x_api"]), "urlopen_calls": len(calls["urlopen"]),
        "queued": [i for i in queue_after if i.get("status") == "buffer_queued"],
        "paths": {"report": rp, "ledger": lp, "sheet": dp, "queue": qp},
    }


def main() -> int:  # noqa: C901 - one property per block, deliberately flat
    failures, checks = [], []
    if not PUBLISHER.exists() or not POLICY.exists():
        print(json.dumps({"validator": "buffer_route", "status": "FAIL",
                          "hard_failures": 1, "properties_exercised": 0,
                          "detail": "publisher or platform declaration missing"},
                         indent=2))
        return 1

    from lib import social_platforms  # noqa: E402
    committed = json.loads(POLICY.read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp())

    # ------------------------------------------------------------- property 1
    # The route is DECLARED, in the one file that is the switch for everything
    # else about a platform, and it is reversible by one boolean.
    route = social_platforms.delivery_route("x", committed)
    declared_on = social_platforms.route_enabled("x", social_platforms.ROUTE_BUFFER,
                                                 committed)
    off = copy.deepcopy(committed)
    off["platforms"]["x"]["delivery_route"]["enabled"] = False
    declared_off = social_platforms.route_enabled("x", social_platforms.ROUTE_BUFFER, off)
    checks.append({"property": "the_route_is_one_declared_reversible_boolean",
                   "declared": {k: v for k, v in route.items() if k == "route"},
                   "enabled_now": declared_on, "enabled_after_flip": declared_off})
    if not declared_on:
        failures.append(
            "platforms.x.delivery_route is not switched on in "
            "data/social-brand-policy.json, so nothing carries X's posts but her hands.")
    if declared_off:
        failures.append(
            "Setting platforms.x.delivery_route.enabled to false left the route enabled. "
            "A delivery lane that cannot be switched off in one edit is a lane nobody "
            "can stop when it misbehaves.")

    # ------------------------------------------------------------- property 2
    # The ceiling is Buffer's own number, discovered at runtime, and it holds.
    # Buffer allows 2 today; 30 entries are eligible; X_DAILY_LIMIT is 8.
    capped = drive(tmp, "cap-2", committed, limit=2)
    checks.append({"property": "never_exceeds_the_discovered_daily_limit",
                   "buffer_limit_reported": 2, "eligible_entries": 30,
                   "create_calls": capped["create_calls"],
                   "receipt": capped["report"]["delivery_routes"]["x"]["receipt"]})
    if capped["create_calls"] > 2:
        failures.append(
            f"Buffer reported a daily limit of 2 and the route made "
            f"{capped['create_calls']} createPost calls. The ceiling is not a ceiling.")
    if capped["create_calls"] == 0:
        failures.append(
            "The route made zero createPost calls with 30 eligible entries and headroom "
            "of 2. A cap that stops everything is not a cap, it is an outage, and it "
            "would pass every other check in this file.")

    # Proved negatively: raise ONLY Buffer's number and more posts leave. If the
    # count were the same either way, property 2 measured something else --
    # the run limit, the queue, the similarity guard.
    roomy = drive(tmp, "cap-6", committed, limit=6)
    checks.append({"property": "the_discovered_limit_is_what_governs",
                   "with_limit_2": capped["create_calls"],
                   "with_limit_6": roomy["create_calls"]})
    if roomy["create_calls"] <= capped["create_calls"]:
        failures.append(
            f"Raising Buffer's reported limit from 2 to 6 did not change how many posts "
            f"went out ({capped['create_calls']} vs {roomy['create_calls']}). The route "
            f"is not reading Buffer's limit at all, so the cap that held above held by "
            f"accident.")
    # And this repository's own declared limit still caps a generous Buffer.
    generous = drive(tmp, "cap-25", committed, limit=25)
    checks.append({"property": "the_networks_own_daily_limit_still_caps_a_generous_buffer",
                   "buffer_limit_reported": 25, "x_daily_limit": 8,
                   "create_calls": generous["create_calls"]})
    if generous["create_calls"] > 8:
        failures.append(
            f"Buffer would have allowed 25 and the route sent {generous['create_calls']}, "
            f"past this network's own X_DAILY_LIMIT of 8. The lower of the two ceilings "
            f"has to govern.")

    # ------------------------------------------------------------- property 3
    # One refusal ends the route for the run. The stub would answer forever.
    refused = drive(tmp, "refusal", committed, limit=25, refuse_after=2)
    halted = refused["report"].get("halted_platforms", {})
    dispositions = [f.get("disposition") for f in refused["report"].get("failures", [])]
    checks.append({"property": "halts_on_the_first_refusal_and_cannot_loop",
                   "createPost_calls_before_and_including_refusal": refused["create_calls"],
                   "eligible_entries": 30,
                   "halted_platforms": list(halted),
                   "failure_dispositions": dispositions})
    if refused["create_calls"] != 2:
        failures.append(
            f"Buffer refused the 2nd call and the route made {refused['create_calls']} "
            f"createPost calls against 30 eligible entries. Continuing past a refusal is "
            f"the 581-requests-in-76-seconds failure of 2026-08-29, exactly.")
    if "x" not in halted:
        failures.append(
            "Buffer refused and the run recorded no halt for x, so nothing downstream "
            "can tell that the route stopped carrying posts.")
    if any(d and d.startswith("failed_permanent") for d in dispositions):
        failures.append(
            f"A Buffer refusal retired queue entries permanently ({dispositions}). The "
            f"platform refused the account, not the post: entries must be deferred and "
            f"tried again, or 581 good pages die on one bad afternoon.")

    # Proved negatively: with no refusal the same fixture keeps going, so the
    # low call count above is the halt and not an empty queue.
    checks.append({"property": "without_a_refusal_the_same_fixture_keeps_going",
                   "calls_when_refused": refused["create_calls"],
                   "calls_when_accepted": generous["create_calls"]})
    if generous["create_calls"] <= refused["create_calls"]:
        failures.append(
            "The same fixture made no more calls when Buffer accepted than when it "
            "refused, so the halt above proves nothing.")

    # ------------------------------------------------------------- property 4
    # A post Buffer accepted is never offered on the hand-post sheet, and a
    # post already on an open sheet is never taken by the route.
    from lib import social_selection  # noqa: E402
    import social_drafts  # noqa: E402

    fixture = synthetic_queue()
    # Put the first three entries on an open, unmarked batch: she has been asked
    # to post these by hand and has not yet said she did.
    open_items = [social_drafts.draft_entry(item, i) for i, item in enumerate(fixture[:3])]
    ledger = social_drafts.empty_ledger()
    ledger["batches"].append({"batch_id": "x-2026-08-29-1", "platform": "x",
                              "generated_at": "2026-08-29T00:00:00Z",
                              "reason": "fixture", "items": open_items})
    double = drive(tmp, "double", committed, queue=fixture, ledger=ledger, limit=25)
    open_texts = {e["text"] for e in open_items}
    collisions = sorted(open_texts.intersection(double["sent_texts"]))
    drafted_after = {e["text"] for b in double["ledger"].get("batches", [])
                     for e in b.get("items", [])}
    queued_texts = {social_selection.post_text(i) for i in double["queued"]}
    both = sorted(queued_texts.intersection(drafted_after))
    checks.append({"property": "no_post_goes_out_by_both_routes",
                   "posts_open_on_the_sheet": len(open_items),
                   "of_those_taken_by_buffer": len(collisions),
                   "buffer_accepted": len(double["queued"]),
                   "of_those_also_drafted": len(both),
                   "statuses_after": sorted({i.get("status") for i in double["queue_after"]})})
    if collisions:
        failures.append(
            f"{len(collisions)} post(s) sitting unposted on reports/social-drafts.md were "
            f"ALSO handed to Buffer. She posts them by hand, Buffer posts them again: two "
            f"identical posts on one profile.")
    if both:
        failures.append(
            f"{len(both)} post(s) Buffer accepted were also written onto the hand-post "
            f"sheet. Accepted by Buffer means it is going out; offering it again is a "
            f"double post.")
    if not double["queued"]:
        failures.append(
            "Buffer accepted nothing in the double-post fixture, so nothing above was "
            "actually tested.")
    if "buffer_queued" in social_platforms.POSTABLE_STATUSES:
        failures.append(
            "'buffer_queued' is a postable status, so an entry Buffer already holds "
            "would be sent again on the next run.")

    # Proved negatively: switch the route off and the SAME entries are drafted
    # by hand again. If they were drafted either way, the route is not the
    # reason the sheet is empty.
    route_off = drive(tmp, "route-off", off, queue=fixture, limit=25)
    checks.append({"property": "with_the_route_off_the_hand_sheet_comes_back",
                   "x_state_route_on": double["report"]["platform_states"]["x"],
                   "x_state_route_off": route_off["report"]["platform_states"]["x"],
                   "drafts_route_on": double["report"]["manual_drafts"]["drafts_written"],
                   "drafts_route_off": route_off["report"]["manual_drafts"]["drafts_written"],
                   "buffer_calls_route_off": route_off["create_calls"]})
    if route_off["create_calls"]:
        failures.append(
            f"The route is switched off in the declaration and still made "
            f"{route_off['create_calls']} Buffer call(s).")
    if route_off["report"]["manual_drafts"]["drafts_written"] == 0:
        failures.append(
            "With the Buffer route off, X produced no drafts. The hand-post fallback is "
            "the thing Buffer replaces; if it does not come back when the route is off, "
            "switching the route off ends X's distribution altogether.")

    # ------------------------------------------------------------- property 5
    # X's own API is contacted ZERO times. That is the whole reason this route
    # exists: every request to X is billable and she has declined to fund it.
    checks.append({"property": "x_api_is_never_contacted_by_the_route",
                   "x_api_calls": sum(r["x_api_calls"] for r in
                                      (capped, roomy, generous, refused, double)),
                   "raw_network_calls": sum(r["urlopen_calls"] for r in
                                            (capped, roomy, generous, refused, double)),
                   "reported": double["report"]["delivery_routes"]["x"]["x_api_requests_made"]})
    for label, run in (("capped", capped), ("roomy", roomy), ("generous", generous),
                       ("refused", refused), ("double", double), ("off", route_off)):
        if run["x_api_calls"] or run["urlopen_calls"]:
            failures.append(
                f"The {label} run made {run['x_api_calls']} call(s) to X's own API and "
                f"{run['urlopen_calls']} raw network call(s). X is pay-per-use and "
                f"unfunded; the route exists precisely so that number stays zero.")

    # ------------------------------------------------------------- property 6
    # Queued in Buffer is not published on X, and the record says so.
    sample = double["queued"][0] if double["queued"] else {}
    checks.append({"property": "queued_in_buffer_is_recorded_as_not_yet_published",
                   "status": sample.get("status"),
                   "has_buffer_post_id": bool(sample.get("buffer_post_id")),
                   "has_posted_at": "posted_at" in sample,
                   "buffer_post_status": sample.get("buffer_post_status"),
                   "report_separates_them": {
                       "posted_this_run": double["report"]["posted_this_run"],
                       "buffer_queued_this_run": double["report"]["buffer_queued_this_run"]}})
    if sample.get("status") != "buffer_queued":
        failures.append(
            f"An entry Buffer accepted carries status {sample.get('status')!r}. Buffer "
            f"holding a post is not X having published it, and a ledger that says "
            f"'posted' cannot be told apart from one that means it.")
    if "posted_at" in sample:
        failures.append(
            "An entry Buffer merely accepted carries posted_at, which reads as published.")
    if not sample.get("buffer_post_id"):
        failures.append(
            "A Buffer-accepted entry carries no Buffer post id, so nothing can find the "
            "post again to check whether it went out.")
    if double["report"]["posted_this_run"].get("x"):
        failures.append(
            "posted_this_run counts Buffer-queued posts as published to X.")

    # ------------------------------------------------------------- property 7
    # The queue is not consumed. Nothing is deleted, nothing is retired, and
    # every entry the route did not take keeps its own status.
    before, after = double["queue_before"], double["queue_after"]
    lost = len(before) - len(after)
    moved = [(b.get("status"), a.get("status")) for b, a in zip(before, after)
             if b.get("status") != a.get("status")]
    unexpected = sorted({m for m in moved if m[1] not in
                         ("buffer_queued", "skipped_duplicate", "queued_for_auto_post")})
    live = json.loads(LIVE_QUEUE.read_text(encoding="utf-8")) if LIVE_QUEUE.exists() else []
    if isinstance(live, dict):
        live = live.get("items", [])
    live_counts = {s: sum(1 for i in live if i.get("status") == s) for s in GUARDED_STATUSES}
    checks.append({"property": "the_queue_is_not_consumed",
                   "entries_before": len(before), "entries_after": len(after),
                   "status_transitions": sorted(set(moved)),
                   "committed_queue_counts": live_counts})
    if lost:
        failures.append(f"{lost} queue entries disappeared during a routed run.")
    if unexpected:
        failures.append(
            f"A routed run moved entries into unexpected statuses: {unexpected}. The "
            f"route may take an entry or leave it; retiring one is not on the menu.")
    if sum(live_counts.values()) == 0:
        failures.append(
            "The committed data/social-queue.json holds no entries in any guarded status, "
            "so there is no distribution left to protect and every check above is moot.")

    # ------------------------------------------------------------- property 8
    # The token never reaches a log, a report, a sheet, a ledger or a commit.
    leaks = []
    for label, run in (("double", double), ("refused", refused)):
        for where in ("stdout", "sheet"):
            if CANARY_TOKEN in run[where]:
                leaks.append(f"{label}:{where}")
        for where in ("report", "ledger"):
            if CANARY_TOKEN in json.dumps(run[where]):
                leaks.append(f"{label}:{where}")
    tracked = subprocess.run(["git", "grep", "-lI", "-e", "BUFFER_ACCESS_TOKEN"],
                             cwd=ROOT, text=True, capture_output=True).stdout.split()
    # The NAME may appear anywhere; a value must not. A Buffer token is a long
    # opaque string, so any literal assignment of one is the shape to reject.
    assignment = subprocess.run(
        ["git", "grep", "-nIE",
         r"BUFFER_ACCESS_TOKEN[\"']?\s*[:=]\s*[\"'][A-Za-z0-9/+_.-]{20,}"],
        cwd=ROOT, text=True, capture_output=True).stdout.strip()
    checks.append({"property": "the_token_never_reaches_a_log_a_report_or_a_commit",
                   "canary_leaks": leaks,
                   "files_naming_the_secret": len(tracked),
                   "literal_assignments_found": bool(assignment)})
    if leaks:
        failures.append(
            f"BUFFER_ACCESS_TOKEN's value appeared in {leaks}. The publisher prints its "
            f"report into the workflow log and commits it to reports/, so a token that "
            f"reaches either is a published credential.")
    if assignment:
        failures.append(
            f"A literal BUFFER_ACCESS_TOKEN value looks committed:\n{assignment[:300]}")

    # ------------------------------------------------------------- property 9
    # No X channel in Buffer is a NAMED stop with the fix in it, not a silent
    # nothing -- and the hand-post sheet still carries the day.
    nochannel = drive(tmp, "no-x-channel", committed, channel_service="tiktok")
    why = (nochannel["report"].get("delivery_routes", {}).get("x", {}) or {}).get("why_not_used")
    checks.append({"property": "a_missing_channel_is_named_and_falls_back",
                   "x_state": nochannel["report"]["platform_states"]["x"],
                   "why_not_used": (why or "")[:160],
                   "drafts_written": nochannel["report"]["manual_drafts"]["drafts_written"],
                   "buffer_create_calls": nochannel["create_calls"]})
    if nochannel["create_calls"]:
        failures.append("The route posted with no X channel connected.")
    if not why:
        failures.append(
            "Buffer could not carry X and the report gives no reason, so 'it went out by "
            "hand again' has no explanation anywhere she looks.")
    if nochannel["report"]["manual_drafts"]["drafts_written"] == 0:
        failures.append(
            "With no X channel in Buffer, nothing was drafted by hand either. That is the "
            "day's distribution lost in silence -- the fallback must survive the route "
            "being unusable.")

    # ------------------------------------------------------------ property 10
    # The budget is spent BEFORE the request, not after the outcome. Measured
    # from inside the call: while Buffer is still deciding, the allowance must
    # already be one lower. This is the exact defect of 2026-08-29 -- caps that
    # charged for successes, so a run where every call failed paid nothing and
    # made one request per queue entry -- and it cannot be seen from outside,
    # because every refusal also halts the route.
    from lib import buffer_route as br  # noqa: E402

    observed = {}

    def charge_probe(fail):
        route = br.Route("x", policy_daily_limit=8)
        calls = {"createPost": [], "all": []}
        base = buffer_stub(calls, limit=25)

        def graphql(query, variables=None, timeout=30, opener=None):
            if "createPost" in query:
                # Mid-flight: the outcome is not known yet.
                observed["remaining_during_call"] = route.remaining()
                observed["attempts_during_call"] = route.attempts
                if fail:
                    raise br.BufferError("HTTP 500: buffer is down", kind="http_error")
            return base(query, variables, timeout, opener)

        real, os_token = br.graphql, os.environ.get("BUFFER_ACCESS_TOKEN")
        br.graphql = graphql
        os.environ["BUFFER_ACCESS_TOKEN"] = CANARY_TOKEN
        try:
            route.open()
            headroom = route.headroom
            try:
                route.create_post("a post that may or may not be accepted")
            except br.BufferError:
                pass
            return {"headroom": headroom, "attempts_after": route.attempts,
                    "accepted_after": route.accepted,
                    "remaining_during_call": observed.get("remaining_during_call")}
        finally:
            br.graphql = real
            if os_token is not None:
                os.environ["BUFFER_ACCESS_TOKEN"] = os_token

    failed_call = charge_probe(fail=True)
    checks.append({"property": "the_budget_is_spent_on_attempts_not_on_successes",
                   "measured_during_a_call_that_then_failed": failed_call})
    if failed_call["attempts_after"] != 1:
        failures.append(
            f"A Buffer call that failed left attempts at {failed_call['attempts_after']}. "
            f"A failed request still reached Buffer and still counts; charging only for "
            f"successes is how 581 requests left this repository in 76 seconds.")
    if failed_call["accepted_after"] != 0:
        failures.append("A failed Buffer call was counted as accepted.")
    if failed_call["remaining_during_call"] != failed_call["headroom"] - 1:
        failures.append(
            f"While the request was in flight the route still reported "
            f"{failed_call['remaining_during_call']} of {failed_call['headroom']} left, so "
            f"the budget is charged on the OUTCOME rather than on the attempt. Remove the "
            f"halt-on-refusal rule above and that alone reproduces the 2026-08-29 run.")

    exercised = len(checks)
    status = "FAIL" if failures else "PASS"
    receipt = {
        "validator": "buffer_route",
        "status": status,
        "hard_failures": len(failures),
        "strong_warnings": 0,
        "soft_warnings": 0,
        "properties_exercised": exercised,
        "failures": failures,
        "checks": checks,
    }
    if exercised == 0:
        receipt["status"] = "FAIL"
        receipt["hard_failures"] = 1
        receipt["failures"] = ["Zero properties were exercised, so this receipt is "
                               "evidence of nothing."]
    print(json.dumps(receipt, indent=2, default=str))
    return 1 if receipt["hard_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
