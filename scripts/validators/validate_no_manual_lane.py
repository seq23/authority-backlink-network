#!/usr/bin/env python3
"""Nothing in this repository may ask the owner to post something by hand.

What this guards, and why it replaced its own predecessor
---------------------------------------------------------
There used to be a validator here called validate_social_drafts_fallback.py. It
guarded a copy-paste sheet, reports/social-drafts.md, that the publisher wrote
whenever X's API could not carry the day's posts: the exact text the API would
have sent, for the owner to paste into X herself, marked done by setting one
field in data/social-draft-ledger.json.

It was the right build while X's API was pay-per-use and unfunded and there was
no other way out. On 2026-08-29, shown what the sheet actually asked of her, the
owner said:

    "this means i manually have to do it? i will never do it honestly."

That sentence retires the lane. A sheet nobody will ever read is output that
nothing downstream consumes -- the same defect class as a run that exits 0
having done nothing, except louder, because it also leaves a standing
instruction that will never be followed. A standing instruction nobody follows
is worse than no instruction: every run reports N posts "waiting", the number
only grows, and the report reads like pending work when it is actually a dead
end.

So Buffer, which carries the same posts to the same X profile from a free plan
at no per-post cost, became the whole of X's distribution, and the manual lane
was deleted rather than left dormant. This validator exists to keep it deleted.

The four things that must stay true
-----------------------------------
  no sheet is written        no run, in any configuration, may write a
                             copy-paste sheet or any other file whose purpose
                             is to be read and acted on by a person.
  no surface instructs her   not the report, not the run summary, not the
                             platform declaration. "Deferred because Buffer is
                             full" is a NAMED, COUNTED state; it is not a task.
  nothing is stranded        a post the route could not take keeps
                             `queued_for_auto_post`, is not retired, is not
                             moved to a second holding place, and goes out on a
                             LATER RUN. Proved across two consecutive runs
                             against the same queue, not asserted.
  history is never re-sent   the posts she DID put on X by hand, before the
                             sheet was retired, are recorded at or before
                             `marked_posted_through` and must never be sent
                             anywhere again. That declaration is read-only now:
                             nothing updates it and nothing asks her to.

Every property is driven through the REAL publisher with Buffer's transport
stubbed and every network path counted. Each is proved negatively where a
negative proof is possible.

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
LIVE_LEDGER = ROOT / "data" / "social-draft-ledger.json"

TOKEN = "manual-lane-canary-4f1a8c-never-log-me"

# Words that only ever appear when something is asking a person to do a task.
# Matched against what a RUN produces -- the report and the stdout -- never
# against source comments, which are allowed to explain the retired lane.
INSTRUCTION_PHRASES = (
    "post these by hand",
    "posted by hand",
    "to be posted by hand",
    "copy-paste",
    "paste them",
    "mark them done",
    "marked_posted_through\" to",
    "set \"marked_posted_through\"",
)

# The lane's own artifacts. None of these may be produced by a run, and the
# first two may not exist in the tree at all.
RETIRED_FILES = ("reports/social-drafts.md", "scripts/social_drafts.py",
                 "scripts/validators/validate_social_drafts_fallback.py")

VOCAB = [w + s for s in ("alpha", "bravo", "delta", "gamma", "omega", "sierra")
         for w in ("quiet", "river", "stone", "amber", "cedar", "falcon", "harbor",
                   "ivory", "juniper", "lantern", "meadow", "nimbus")]


def synthetic_queue(n=30):
    """Deliberately dissimilar bodies: the same-day similarity guard would
    otherwise skip most of them and every count below would move for the wrong
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
    for name in ("lib", "lib.social_platforms", "lib.buffer_route",
                 "lib.hand_post_history", "lib.social_selection",
                 "social_publisher_manual_probe"):
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location("social_publisher_manual_probe",
                                                  PUBLISHER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["social_publisher_manual_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


def buffer_stub(calls, plan_depth=10, already_queued=0, daily_limit=50,
                channel_service="twitter", refuse_after=None,
                refusal="LimitReachedError"):
    """Stand in for Buffer, with a free plan whose QUEUE DEPTH is the ceiling.

    `already_queued` is how many posts Buffer says are already waiting, spread
    over the horizon the route sums. It is the knob that makes "the plan is
    full" happen without any refusal at all, which is the case that must leave
    entries queued rather than stranded.
    """
    state = {"queued": already_queued}

    def graphql(query, variables=None, timeout=30, opener=None):
        calls["all"].append(query.strip()[:60])
        if "organizations" in query:
            return {"account": {"id": "acc", "organizations": [
                {"id": "org", "name": "My Organization", "channelCount": 2,
                 "limits": {"channels": 3, "scheduledPosts": plan_depth}}]}}
        if "channels(input" in query:
            if channel_service is None:
                return {"channels": []}
            return {"channels": [{"id": "ch-x", "name": "sequoia_ta12767",
                                  "service": channel_service, "isDisconnected": False,
                                  "isLocked": False, "isQueuePaused": False}]}
        if "dailyPostingLimits" in query:
            # The depth sweep asks day by day. Everything already waiting is
            # reported on the first day asked about; the rest are empty.
            dated = bool((variables or {}).get("input", {}).get("date"))
            first = dated and not calls.get("depth_days")
            if dated:
                calls.setdefault("depth_days", []).append(
                    variables["input"].get("date"))
            return {"dailyPostingLimits": [
                {"channelId": "ch-x", "isAtLimit": False, "limit": daily_limit,
                 "scheduled": state["queued"] if first else 0, "sent": 0}]}
        if "createPost" in query:
            calls["createPost"].append(variables["input"])
            n = len(calls["createPost"])
            if refuse_after is not None and n >= refuse_after:
                return {"createPost": {"__typename": refusal,
                                       "message": "Buffer says no"}}
            state["queued"] += 1
            return {"createPost": {"__typename": "PostActionSuccess",
                                   "post": {"id": f"buf-{n}", "status": "scheduled",
                                            "dueAt": "2026-08-30T14:00:00Z",
                                            "channelId": "ch-x"}}}
        raise AssertionError(f"unexpected query: {query[:80]}")
    return graphql


def drive(tmp, name, policy, queue=None, ledger=None, token=TOKEN, run_limit=20,
          queue_path=None, **stub):
    """Run the REAL publisher with only Buffer's transport replaced.

    `queue_path` lets a second run read the queue the first run WROTE, which is
    the only way to prove that a deferred entry actually goes out later rather
    than merely being described as deferred.
    """
    qp = Path(queue_path) if queue_path else tmp / f"{name}-queue.json"
    rp, lp = tmp / f"{name}-report.json", tmp / f"{name}-ledger.json"
    pp = tmp / f"{name}-policy.json"
    pp.write_text(json.dumps(policy, indent=2))
    if queue is not None or not qp.exists():
        qp.write_text(json.dumps(
            queue if queue is not None else synthetic_queue(), indent=2))
    if ledger is not None:
        lp.write_text(json.dumps(ledger, indent=2))
    queue_before = json.loads(qp.read_text())

    for var in ("ENABLE_X_POSTING", "ENABLE_LINKEDIN_POSTING",
                "ENABLE_X_BUFFER_ROUTE", "SOCIAL_DRAFTS_PATH"):
        os.environ.pop(var, None)
    os.environ.update({
        "SOCIAL_PLATFORM_POLICY_PATH": str(pp), "SOCIAL_QUEUE_PATH": str(qp),
        "SOCIAL_REPORT_PATH": str(rp), "SOCIAL_DRAFT_LEDGER_PATH": str(lp),
        "SOCIAL_DRY_RUN": "false", "REQUIRE_SOCIAL_SECRETS": "false",
        "X_DAILY_LIMIT": "8", "LINKEDIN_DAILY_LIMIT": "3",
        "SOCIAL_RUN_LIMIT": str(run_limit),
        "SOCIAL_POST_MIN_INTERVAL_SECONDS": "0",
    })
    if token:
        os.environ["BUFFER_ACCESS_TOKEN"] = token
    else:
        os.environ.pop("BUFFER_ACCESS_TOKEN", None)

    before_files = {p for p in tmp.rglob("*") if p.is_file()}
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
    after_files = {p for p in tmp.rglob("*") if p.is_file()}
    queue_after = json.loads(qp.read_text())
    return {
        "report": json.loads(rp.read_text()),
        "queue_before": queue_before, "queue_after": queue_after,
        "queue_path": qp,
        "stdout": stdout.getvalue(),
        "files_written": sorted(str(p.name) for p in after_files - before_files),
        "create_calls": len(calls["createPost"]),
        "sent_texts": [c.get("text") for c in calls["createPost"]],
        "x_api_calls": len(calls["x_api"]), "urlopen_calls": len(calls["urlopen"]),
        "buffer_ids": [s.get("id") for s in
                       json.loads(rp.read_text()).get("successes", [])
                       if s.get("via") == "buffer"],
        "queued_entries": [i for i in queue_after
                           if i.get("status") == "buffer_queued"],
        "still_postable": [i for i in queue_after
                           if i.get("status") == "queued_for_auto_post"],
    }


def main() -> int:  # noqa: C901 - one property per block, deliberately flat
    failures, checks = [], []
    if not PUBLISHER.exists() or not POLICY.exists():
        print(json.dumps({"validator": "no_manual_lane", "status": "FAIL",
                          "hard_failures": 1, "properties_exercised": 0,
                          "detail": "publisher or platform declaration missing"},
                         indent=2))
        return 1

    from lib import hand_post_history, social_platforms  # noqa: E402
    committed = json.loads(POLICY.read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp())

    # ------------------------------------------------------------- property 1
    # The lane's own files are gone from the tree, not merely unused. A dormant
    # module is one import away from being alive again, and the whole point of
    # deleting it is that no future change can quietly re-enable a sheet the
    # owner has said she will never read.
    present = [f for f in RETIRED_FILES if (ROOT / f).exists()]
    tracked = subprocess.run(["git", "ls-files", "--", *RETIRED_FILES],
                             cwd=ROOT, text=True, capture_output=True).stdout.split()
    importers = subprocess.run(
        ["git", "grep", "-lI", "-e", "import social_drafts",
         "-e", "from social_drafts", "--", "scripts", "tests"],
        cwd=ROOT, text=True, capture_output=True).stdout.split()
    checks.append({"property": "the_retired_manual_lane_is_deleted_not_dormant",
                   "files_still_present": present,
                   "files_still_tracked": tracked,
                   "modules_still_importing_it": importers})
    if present or tracked:
        failures.append(
            f"The retired hand-post lane is still in the tree: {present or tracked}. "
            f"The owner said she would never post from it -- \"i will never do it "
            f"honestly\" -- so it produces output nothing consumes. Left in place it "
            f"is one import away from being live again.")
    if importers:
        failures.append(
            f"{importers} still import the deleted drafting module, so the publisher "
            f"cannot even start. ")

    # ------------------------------------------------------------- property 2
    # A run in the ordinary configuration writes NO file for a person to act on.
    # Measured by watching the directory rather than by trusting a path
    # constant: a sheet written somewhere unexpected is still a sheet.
    ordinary = drive(tmp, "ordinary", committed)
    sheets = [f for f in ordinary["files_written"] if "draft" in f and f.endswith(".md")]
    checks.append({"property": "a_run_writes_no_sheet_for_a_person_to_act_on",
                   "files_written": ordinary["files_written"],
                   "sheet_like_files": sheets,
                   "buffer_posts_created": ordinary["create_calls"]})
    if sheets:
        failures.append(
            f"A run wrote {sheets}, which is a copy-paste sheet by another name. "
            f"Distribution must not depend on a person, and a file that asks one to "
            f"act is a lane with no consumer.")
    if ordinary["create_calls"] == 0:
        failures.append(
            "The ordinary run handed Buffer nothing at all with 30 eligible entries "
            "and an empty Buffer queue, so every observation below is about a lane "
            "that is not running.")

    # ------------------------------------------------------------- property 3
    # The report names no task. "Deferred" is a state; "post these by hand" is
    # an instruction, and the difference is the whole point of this file.
    surfaces = json.dumps(ordinary["report"]).lower() + ordinary["stdout"].lower()
    found = sorted(p for p in INSTRUCTION_PHRASES if p in surfaces)
    has_manual_key = "manual_drafts" in ordinary["report"]
    checks.append({"property": "no_surface_instructs_the_owner_to_post_anything",
                   "instruction_phrases_found": found,
                   "report_has_manual_drafts_key": has_manual_key,
                   "deferred_is_named_and_counted": {
                       "deferred_waiting_for_delivery_route":
                           ordinary["report"].get("deferred_waiting_for_delivery_route"),
                       "route_only_platforms":
                           ordinary["report"].get("route_only_platforms")}})
    if found:
        failures.append(
            f"A run's own output still tells the owner to post something: {found}. "
            f"She has said she never will, so this is a standing instruction that will "
            f"never be followed -- worse than none, because it reads as pending work.")
    if has_manual_key:
        failures.append(
            "The run report still carries a `manual_drafts` block. Anything reading "
            "the report will keep presenting hand-posting as a live lane.")
    if ordinary["report"].get("deferred_waiting_for_delivery_route") is None:
        failures.append(
            "The report does not count what the route could not carry. Without that "
            "number, 'Buffer took two and the rest are fine' is indistinguishable "
            "from 'twenty-eight posts vanished'.")

    # ------------------------------------------------------------- property 4
    # The free plan's QUEUE DEPTH, not a refusal, is what stops the run. Buffer
    # says nine of ten slots are already taken: the route must take at most the
    # room that is left and must NOT go looking for a refusal to find the edge.
    nearly_full = drive(tmp, "nearly-full", committed, plan_depth=10,
                        already_queued=9)
    receipt = ((nearly_full["report"].get("delivery_routes") or {}).get("x")
               or {}).get("receipt") or {}
    checks.append({"property": "a_full_free_plan_stops_the_run_without_a_refusal",
                   "plan_queue_depth": 10, "already_queued_in_buffer": 9,
                   "buffer_create_calls": nearly_full["create_calls"],
                   "binding_ceiling": receipt.get("binding_ceiling"),
                   "ceilings": receipt.get("ceilings_discovered"),
                   "halted": receipt.get("halted")})
    if nearly_full["create_calls"] > 1:
        failures.append(
            f"Buffer's free plan allows 10 posts queued at once and 9 were already "
            f"waiting, and the route made {nearly_full['create_calls']} createPost "
            f"calls. The owner pays Buffer nothing; pushing past a free allowance is "
            f"how an account meets an upgrade prompt.")
    if receipt.get("halted"):
        failures.append(
            f"The route halted ({receipt['halted']}) on a plan that was merely nearly "
            f"full. Finding the ceiling by being refused at it is exactly what must "
            f"not happen: the ceiling is discovered and respected BEFORE the request.")

    # Proved negatively: empty the Buffer queue and the same fixture, the same
    # plan and the same policy send more. If the count did not move, the depth
    # cap above held for some other reason.
    checks.append({"property": "the_queue_depth_is_what_governs_not_something_else",
                   "with_9_of_10_taken": nearly_full["create_calls"],
                   "with_0_of_10_taken": ordinary["create_calls"]})
    if ordinary["create_calls"] <= nearly_full["create_calls"]:
        failures.append(
            f"An empty Buffer queue sent no more posts than a nearly full one "
            f"({ordinary['create_calls']} vs {nearly_full['create_calls']}), so the "
            f"queue-depth ceiling is not being read at all.")

    # ------------------------------------------------------------- property 5
    # What the route could not take is NOT stranded. Same queue, second run,
    # Buffer having drained: the entries left behind go out. This is the
    # property the deleted sheet used to provide, and the reason it can be
    # deleted safely.
    two_run_queue = tmp / "two-run-queue.json"
    first = drive(tmp, "tworun-1", committed, queue=synthetic_queue(),
                  queue_path=two_run_queue, plan_depth=10, already_queued=8)
    left_after_first = len(first["still_postable"])
    second = drive(tmp, "tworun-2", committed, queue_path=two_run_queue,
                   plan_depth=10, already_queued=0)
    first_ids = {i.get("buffer_post_id") for i in first["queued_entries"]}
    second_ids = {i.get("buffer_post_id") for i in second["queued_entries"]}
    newly_carried = len(second["queued_entries"]) - len(first["queued_entries"])
    lost = len(first["queue_after"]) - len(second["queue_after"])
    retired = [i.get("status") for i in second["queue_after"]
               if i.get("status") not in ("queued_for_auto_post", "buffer_queued",
                                          "skipped_duplicate")]
    checks.append({"property": "what_the_route_could_not_take_goes_out_on_a_later_run",
                   "run_1_buffer_calls": first["create_calls"],
                   "run_1_still_queued_after": left_after_first,
                   "run_2_buffer_calls": second["create_calls"],
                   "run_2_newly_carried": newly_carried,
                   "entries_lost_between_runs": lost,
                   "unexpected_statuses": sorted(set(retired))})
    if left_after_first == 0:
        failures.append(
            "The first run left nothing queued, so 'it goes out on a later run' was "
            "never actually tested.")
    if second["create_calls"] == 0 or newly_carried <= 0:
        failures.append(
            f"A second run against the same queue, with Buffer drained, carried "
            f"{newly_carried} further post(s). Entries the route could not take on the "
            f"first run are therefore stranded -- and with the hand-post sheet retired "
            f"there is nothing else to catch them.")
    if lost:
        failures.append(f"{lost} queue entries disappeared between two runs.")
    if retired:
        failures.append(
            f"A deferred entry was moved to {sorted(set(retired))}. Waiting for room in "
            f"Buffer is not a fault of the post: it must keep queued_for_auto_post and "
            f"nothing else.")

    # ------------------------------------------------------------- property 6
    # The historical marker is honoured and never rewritten. These are posts she
    # put on X with her own hands; they were never consumed from the queue, so
    # without this guard they would go out a second time on the same profile.
    # Exactly twelve entries and a ceiling of eight: with the first four
    # blocked as already hand-posted, the eight that leave are precisely the
    # four drafted-never-posted plus the four fresh ones. Nothing here depends
    # on where the priority ordering happens to put them.
    fixture = synthetic_queue(12)
    hand_posted = [{"fingerprint": hand_post_history.fingerprint(i),
                    "platform": "x", "brand": i["brand"],
                    "url": i["source_url"],
                    "text": i["body"]} for i in fixture[:4]]
    never_posted = [{"fingerprint": hand_post_history.fingerprint(i),
                     "platform": "x", "brand": i["brand"],
                     "url": i["source_url"], "text": i["body"]}
                    for i in fixture[4:8]]
    ledger = {
        "schema": "authority-social-draft-ledger-v1",
        "marked_posted_through": "x-2026-08-28-1",
        "batches": [
            {"batch_id": "x-2026-08-28-1", "platform": "x",
             "generated_at": "2026-08-28T00:00:00Z", "reason": "fixture",
             "items": hand_posted},
            {"batch_id": "x-2026-08-29-1", "platform": "x",
             "generated_at": "2026-08-29T00:00:00Z", "reason": "fixture",
             "items": never_posted},
        ],
    }
    ledger_before = json.dumps(ledger, sort_keys=True)
    history = drive(tmp, "history", committed, queue=fixture, ledger=ledger,
                    plan_depth=50, already_queued=0)
    ledger_after = (tmp / "history-ledger.json").read_text()
    # Matched on the URL, not on the body. X's 280-character trim can cut the
    # body short, so a body-substring test would report "not sent" for a post
    # that went out -- a guard that passes for the wrong reason in the one
    # direction that matters.
    hand_urls = {e["url"] for e in hand_posted}
    never_urls = {e["url"] for e in never_posted}
    sent = [t or "" for t in history["sent_texts"]]
    resent = sorted(u for u in hand_urls if any(u in t for t in sent))
    released = sorted(u for u in never_urls if any(u in t for t in sent))
    checks.append({"property": "hand_posted_history_is_never_re_sent_and_never_rewritten",
                   "posts_she_posted_by_hand": len(hand_posted),
                   "of_those_sent_to_buffer_again": len(resent),
                   "posts_drafted_but_never_posted": len(never_posted),
                   "of_those_released_to_buffer": len(released),
                   "ledger_unchanged_by_the_run":
                       json.dumps(json.loads(ledger_after), sort_keys=True) == ledger_before,
                   "reported_history": history["report"].get("hand_post_history")})
    if resent:
        failures.append(
            f"{len(resent)} post(s) at or before marked_posted_through were handed to "
            f"Buffer. She already put those on X herself; they are live on the profile, "
            f"and this is a second identical post from a system whose whole purpose is "
            f"to look like a person.")
    if not released:
        failures.append(
            "Posts drafted onto the retired sheet and NEVER posted from it were still "
            "held back from Buffer. Nothing will ever release them by hand -- that lane "
            "is gone -- so holding them freezes the day's distribution forever.")
    if json.dumps(json.loads(ledger_after), sort_keys=True) != ledger_before:
        failures.append(
            "A run modified data/social-draft-ledger.json. It is a historical record "
            "now: marked_posted_through says what the owner posted by hand, nothing "
            "updates it, and rewriting it is how a post she already made gets sent "
            "again.")

    # ------------------------------------------------------------- property 7
    # The committed record still holds a real distribution to protect, and the
    # committed queue is intact. Without this every check above could pass
    # against an empty repository.
    live = json.loads(LIVE_QUEUE.read_text(encoding="utf-8")) if LIVE_QUEUE.exists() else []
    if isinstance(live, dict):
        live = live.get("items", [])
    counts = {s: sum(1 for i in live if i.get("status") == s)
              for s in ("queued_for_auto_post", "not_for_posting",
                        "draft_requires_human_approval", "buffer_queued")}
    committed_ledger = (json.loads(LIVE_LEDGER.read_text(encoding="utf-8"))
                        if LIVE_LEDGER.exists() else {})
    checks.append({"property": "there_is_still_a_real_distribution_to_protect",
                   "committed_queue_counts": counts,
                   "committed_ledger_marker":
                       committed_ledger.get("marked_posted_through"),
                   "committed_ledger_batches":
                       len(committed_ledger.get("batches") or [])})
    if sum(counts.values()) == 0:
        failures.append(
            "The committed data/social-queue.json holds nothing in any guarded status, "
            "so there is no distribution left and every check above is moot.")

    # ------------------------------------------------------------- property 8
    # X's own API is contacted zero times through every path above. It is
    # pay-per-use and unfunded; that is why Buffer exists at all.
    runs = (("ordinary", ordinary), ("nearly-full", nearly_full),
            ("tworun-1", first), ("tworun-2", second), ("history", history))
    checks.append({"property": "x_api_is_contacted_zero_times_by_any_of_these_paths",
                   "x_api_calls": sum(r["x_api_calls"] for _, r in runs),
                   "raw_network_calls": sum(r["urlopen_calls"] for _, r in runs)})
    for label, run in runs:
        if run["x_api_calls"] or run["urlopen_calls"]:
            failures.append(
                f"The {label} run made {run['x_api_calls']} call(s) to X's own API and "
                f"{run['urlopen_calls']} raw network call(s). Every one is billable on "
                f"an account the owner has declined to fund.")

    # ------------------------------------------------------------- property 9
    # Switching the route OFF does not resurrect a manual lane. It used to: the
    # sheet came back. Now X simply stops distributing and says so, and the
    # entries wait. That is the honest outcome, and it must not be dressed up
    # as work for a person.
    off = copy.deepcopy(committed)
    off["platforms"]["x"]["delivery_route"]["enabled"] = False
    route_off = drive(tmp, "route-off", off)
    off_surfaces = json.dumps(route_off["report"]).lower() + route_off["stdout"].lower()
    off_found = sorted(p for p in INSTRUCTION_PHRASES if p in off_surfaces)
    off_sheets = [f for f in route_off["files_written"]
                  if "draft" in f and f.endswith(".md")]
    checks.append({"property": "switching_the_route_off_does_not_resurrect_a_manual_lane",
                   "buffer_calls": route_off["create_calls"],
                   "sheet_like_files": off_sheets,
                   "instruction_phrases_found": off_found,
                   "x_state": route_off["report"]["platform_states"]["x"],
                   "still_queued": len(route_off["still_postable"]),
                   "deferred_named":
                       route_off["report"].get("deferred_waiting_for_delivery_route"),
                   "stop_reason": (route_off["report"].get("stop_reason") or "")[:200]})
    if route_off["create_calls"]:
        failures.append(
            f"The route is switched off in the declaration and still made "
            f"{route_off['create_calls']} Buffer call(s).")
    if off_sheets or off_found:
        failures.append(
            f"Switching the route off brought a manual lane back: {off_sheets or off_found}. "
            f"There is nothing to fall back TO any more, and pretending otherwise puts "
            f"a task in front of the owner that she has said she will never do.")
    if not route_off["still_postable"]:
        failures.append(
            "With the route off, X's entries did not stay queued. They must simply "
            "wait: waiting costs nothing and loses nothing.")
    if not route_off["report"].get("stop_reason") and not route_off["report"].get(
            "named_stops"):
        failures.append(
            "The route is off and the run names no reason. 'X distributed nothing "
            "today' has to be readable without going to look at the code.")

    # ------------------------------------------------------------ property 10
    # The same guard holds on X's OWN API path, not only on the routed one.
    #
    # This was a real defect, found on 2026-08-29: the check lived inside the
    # `if x_via_route:` branch of the publisher, so it protected Buffer and
    # nothing else. The day the owner funds X's API and flips the one boolean,
    # every entry at or before `marked_posted_through` would have gone out a
    # second time through the API -- the exact failure the record exists to
    # prevent, on the exact path nobody would think to check.
    api_on = copy.deepcopy(committed)
    api_on["platforms"]["x"]["enabled"] = True
    api_on["platforms"]["x"]["delivery_route"]["enabled"] = False
    # A credential has to be present or the platform reports itself
    # uncredentialled and the loop is never reached -- a guard proved against a
    # run that posted nothing is a guard proved against nothing. x_post itself
    # is stubbed and counted in drive(), so no request leaves.
    os.environ["X_OAUTH2_ACCESS_TOKEN"] = "fixture-only-never-sent"
    try:
        api_run = drive(tmp, "api-on", api_on, queue=fixture, ledger=ledger,
                        token=None)
    finally:
        os.environ.pop("X_OAUTH2_ACCESS_TOKEN", None)
    api_posted_urls = {i.get("source_url") for i in api_run["queue_after"]
                       if i.get("status") == "posted"}
    api_resent = sorted(u for u in hand_urls if u in api_posted_urls)
    checks.append({"property": "hand_posted_history_is_refused_on_x_s_own_api_path_too",
                   "x_api_calls": api_run["x_api_calls"],
                   "entries_posted_via_api": len(api_posted_urls),
                   "of_those_she_had_already_posted_by_hand": len(api_resent),
                   "of_those_drafted_but_never_posted":
                       len([u for u in never_urls if u in api_posted_urls]),
                   "x_state": api_run["report"]["platform_states"]["x"]})
    if api_run["x_api_calls"] == 0:
        failures.append(
            "With X's own API switched on, the run posted nothing at all, so the guard "
            "below was never exercised on that path.")
    if api_resent:
        failures.append(
            f"{len(api_resent)} post(s) at or before marked_posted_through went out "
            f"through X's OWN API. The double-post guard has to sit above the route "
            f"branch, not inside it: the day the API is funded and the one boolean "
            f"flips, everything she posted by hand goes out again on the same profile.")

    exercised = len(checks)
    receipt_out = {
        "validator": "no_manual_lane",
        "status": "FAIL" if failures else "PASS",
        "hard_failures": len(failures),
        "strong_warnings": 0,
        "soft_warnings": 0,
        "properties_exercised": exercised,
        "failures": failures,
        "checks": checks,
    }
    if exercised == 0:
        receipt_out["status"] = "FAIL"
        receipt_out["hard_failures"] = 1
        receipt_out["failures"] = ["Zero properties were exercised, so this receipt is "
                                   "evidence of nothing."]
    print(json.dumps(receipt_out, indent=2, default=str))
    return 1 if receipt_out["hard_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
