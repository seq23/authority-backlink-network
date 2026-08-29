#!/usr/bin/env python3
"""Switching a platform's API off must not switch its distribution off with it.

What this guards
----------------
There are two reasons to switch a social platform off, and they want opposite
behaviour from everything downstream:

  dormant         Nothing is wanted from the platform at all. LinkedIn, since
                  2026-08-29: "drop linkedin for now its not important". No
                  posts, and no drafts either -- producing a sheet of LinkedIn
                  posts to send by hand would quietly reverse that decision.

  draft_by_hand   The API lane is off precisely BECAUSE it cannot carry the
                  content. X, since 2026-08-29: "im not funding X so find a $0
                  workaround or kill it". X's API is pay-per-use with no free
                  tier -- every write this repository has ever made answered
                  HTTP 402 problems/credits-depleted, starting with the very
                  first request, and about $0.20 per link post makes eight a day
                  roughly $48/month. So the API is not called at all, and the
                  day's posts go out by hand from reports/social-drafts.md.

Collapse those into one `enabled: false` and there is no safe answer left. Draft
every paused platform and LinkedIn starts producing work she said she did not
want. Draft none of them and X -- the only platform with any distribution left
-- silently stops distributing, with the run still exiting 0 and the report
still saying "paused", which is exactly the shape of a lane that does nothing
forever while looking healthy.

So the pause carries its mode, and the properties below are the ones no
configuration check can see. Each is driven through the REAL publisher with the
transport stubbed, and each is proved NEGATIVELY -- by also running the
opposite declaration and showing the behaviour flips:

  drafts survive the pause     X paused for posting still writes a full batch to
                               the sheet, and the run is NAMED for having done
                               so rather than reported as a stop (Rule 0)
  the API is never touched     a paused-for-posting platform makes ZERO requests
                               -- no probe, no single attempt "to see if credits
                               came back". Counted at post_item, at the two
                               platform senders, and at urlopen itself
  a dormant pause is silent    LinkedIn produces no batch, no sheet entry, and
                               no request
  the queue is never consumed  the committed queue keeps all 1,162
                               queued_for_auto_post, 186 not_for_posting and 120
                               draft_requires_human_approval, and a driven run
                               leaves its queue file byte-identical
  one boolean reverses it      flipping ONLY `enabled` back to true restores
                               posting on either platform, in either pause mode,
                               with no other edit -- proved by making that one
                               edit in memory and watching requests appear
  the mode is legible          every paused platform declares a recognised
                               pause_mode, the two modes resolve to different
                               states, and each carries a distinct named stop

Fails hard if it exercises zero properties.
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

PUBLISHER = ROOT / "scripts" / "social_publisher.py"
POLICY = ROOT / "data" / "social-brand-policy.json"
LIVE_QUEUE = ROOT / "data" / "social-queue.json"

# The committed queue must survive all of this untouched. These are the counts
# as of 2026-08-29; the check is that pausing does not consume them, so a
# legitimate change in queue size is reported rather than pinned.
GUARDED_STATUSES = ("queued_for_auto_post", "not_for_posting",
                    "draft_requires_human_approval")
X_DAILY_LIMIT = 8

VOCAB = [
    w + s
    for s in ("alpha", "bravo", "delta", "gamma", "omega")
    for w in ("quiet", "river", "stone", "amber", "cedar", "falcon", "harbor",
              "ivory", "juniper", "lantern", "meadow", "nimbus")
]


def synthetic_queue(n=40):
    return [
        {
            "platform": "x" if i % 4 else "linkedin",
            "brand": f"Brand {i % 7}",
            "domain": f"example{i % 7}.com",
            "post_type": "link_share",
            "body": " ".join(VOCAB[(i * 13 + j) % len(VOCAB)] for j in range(30)),
            "source_url": (f"https://example{i % 7}.com/daily/"
                           f"2026-08-29-entry-{i}.html"),
            "status": "queued_for_auto_post",
            "created_at": "2026-08-01",
        }
        for i in range(n)
    ]


def load_publisher():
    """Re-exec the publisher with a clean view of the declaration modules.

    The policy path is resolved at import time in scripts/lib/social_platforms.py,
    so a cached module would keep pointing at the committed declaration and every
    scenario below would silently test the same one.
    """
    # `lib` itself has to go too: `from lib import social_platforms` reads the
    # attribute off the cached package when one is present, so dropping only
    # the submodule leaves the stale, already-resolved policy path in place.
    for name in ("social_drafts", "lib", "lib.social_platforms",
                 "lib.social_selection", "social_publisher_pause_probe"):
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location("social_publisher_pause_probe", PUBLISHER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["social_publisher_pause_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


def drive(tmp, name, policy, queue=None):
    """Run the REAL publisher against an isolated queue, ledger, sheet and policy.

    Every outbound path is counted, not just the one the happy path uses:
    post_item is where a post is decided, x_post/linkedin_post are where a
    request is built, and urlopen is where one actually leaves. A probe that
    skipped the first two would still be caught by the third.
    """
    qp, rp = tmp / f"{name}-queue.json", tmp / f"{name}-report.json"
    lp, dp = tmp / f"{name}-ledger.json", tmp / f"{name}-drafts.md"
    pp = tmp / f"{name}-policy.json"
    pp.write_text(json.dumps(policy, indent=2))
    qp.write_text(json.dumps(queue if queue is not None else synthetic_queue(), indent=2))
    queue_before = qp.read_bytes()

    for var in ("ENABLE_X_POSTING", "ENABLE_LINKEDIN_POSTING"):
        os.environ.pop(var, None)  # The declaration must govern, not an override.
    # The pause contract is about the platform's OWN API. A Buffer token left in
    # the environment would open the delivery route mid-scenario and change what
    # every property below is measuring, so this file always runs without one.
    # The route has its own guard: scripts/validators/validate_buffer_route.py.
    os.environ.pop("BUFFER_ACCESS_TOKEN", None)
    os.environ.update({
        "SOCIAL_PLATFORM_POLICY_PATH": str(pp),
        "SOCIAL_QUEUE_PATH": str(qp), "SOCIAL_REPORT_PATH": str(rp),
        "SOCIAL_DRAFT_LEDGER_PATH": str(lp), "SOCIAL_DRAFTS_PATH": str(dp),
        "SOCIAL_DRY_RUN": "false", "REQUIRE_SOCIAL_SECRETS": "false",
        "X_DAILY_LIMIT": str(X_DAILY_LIMIT), "LINKEDIN_DAILY_LIMIT": "3",
        "SOCIAL_RUN_LIMIT": "3", "SOCIAL_POST_MIN_INTERVAL_SECONDS": "90",
        "X_API_KEY": "stub", "X_API_SECRET": "stub",
        "X_ACCESS_TOKEN": "stub", "X_ACCESS_TOKEN_SECRET": "stub",
        "LINKEDIN_ACCESS_TOKEN": "stub", "LINKEDIN_AUTHOR_URN": "urn:li:person:stub",
    })
    mod = load_publisher()
    calls = {"post_item": [], "x_post": [], "linkedin_post": [], "urlopen": []}

    def stub_post_item(item, dry_run=False):
        calls["post_item"].append(item.get("platform"))
        return {"ok": True, "id": f"stub-{len(calls['post_item'])}", "status": 201}

    def stub_x_post(text):
        calls["x_post"].append(text)
        return {"ok": True, "id": "stub-x"}

    def stub_li_post(text):
        calls["linkedin_post"].append(text)
        return {"ok": True, "id": "stub-li"}

    def stub_urlopen(*a, **k):
        calls["urlopen"].append(str(a[:1]))
        raise AssertionError("a real network call was attempted")

    mod.post_item = stub_post_item
    mod.x_post = stub_x_post
    mod.linkedin_post = stub_li_post
    mod.urllib.request.urlopen = stub_urlopen
    mod.time.sleep = lambda *_a, **_k: None
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            mod.main()
        except SystemExit:
            pass
    ledger = json.loads(lp.read_text()) if lp.exists() else {}
    return {
        "report": json.loads(rp.read_text()),
        "ledger": ledger,
        "sheet": dp.read_text() if dp.exists() else "",
        "calls": {k: len(v) for k, v in calls.items()},
        "x_calls": calls["post_item"].count("x") + len(calls["x_post"]),
        "li_calls": calls["post_item"].count("linkedin") + len(calls["linkedin_post"]),
        "queue_unchanged": qp.read_bytes() == queue_before,
        "drafted": {
            p: sum(len(b.get("items", [])) for b in ledger.get("batches", [])
                   if b.get("platform") == p)
            for p in ("x", "linkedin")
        },
    }


def main() -> int:  # noqa: C901 - one property per block, deliberately flat
    failures, checks = [], []
    if not PUBLISHER.exists() or not POLICY.exists():
        print(json.dumps({
            "validator": "social_pause_modes", "status": "FAIL", "hard_failures": 1,
            "properties_exercised": 0,
            "detail": "The publisher or the platform declaration is missing; the pause "
                      "contract cannot be exercised.",
        }, indent=2))
        return 1

    from lib import social_platforms  # noqa: E402

    committed = json.loads(POLICY.read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp())

    # ------------------------------------------------------------- property 1
    # Every paused platform declares a mode this repository recognises, and the
    # two modes are genuinely different states. A typo reads as "dormant", which
    # is the safe default at runtime and a silent end to distribution if it is
    # ever the wrong one -- so it must not survive the build.
    declared = committed.get("platforms") or {}
    modes = {}
    for platform in social_platforms.PLATFORMS:
        entry = declared.get(platform)
        if not isinstance(entry, dict):
            failures.append(
                f"data/social-brand-policy.json declares no switch for {platform}, so "
                f"nothing records whether it posts, drafts, or is off."
            )
            continue
        enabled = bool(entry.get("enabled", True))
        raw = social_platforms.declared_pause_mode(platform, committed)
        resolved = social_platforms.pause_mode(platform, committed)
        modes[platform] = {
            "enabled": enabled, "declared_pause_mode": raw,
            "resolved_pause_mode": resolved if not enabled else None,
            "state": social_platforms.platform_state(platform, None, committed),
            "drafts_by_hand": social_platforms.drafts_by_hand(platform, committed),
        }
        if enabled:
            continue
        if raw is None:
            failures.append(
                f"platforms.{platform} is switched off with no pause_mode. Off must say "
                f"which kind of off it is: \"dormant\" produces nothing at all, "
                f"\"draft_by_hand\" keeps distribution running by hand. Defaulting "
                f"silently to dormant is how a platform stops distributing with nothing "
                f"reporting the loss."
            )
        elif raw not in social_platforms.PAUSE_MODES:
            failures.append(
                f"platforms.{platform}.pause_mode is {raw!r}, which is not one of "
                f"{list(social_platforms.PAUSE_MODES)}. At runtime an unrecognised mode "
                f"reads as dormant, so a typo here silently ends this platform's "
                f"distribution while the run stays green."
            )
    checks.append({"property": "every_paused_platform_declares_a_legible_mode",
                   "platforms": modes})
    states = {p: m["state"] for p, m in modes.items()}
    if len(set(states.values())) < len(states) and len(states) > 1:
        # Only a problem when the two modes have actually collapsed together.
        paused_states = {p: m["state"] for p, m in modes.items() if not m["enabled"]}
        declared_modes = {p: m["resolved_pause_mode"] for p, m in modes.items()
                          if not m["enabled"]}
        if len(set(declared_modes.values())) > 1 and len(set(paused_states.values())) == 1:
            failures.append(
                f"Platforms paused in different modes ({declared_modes}) resolve to the "
                f"same state ({paused_states}). If the states are indistinguishable, "
                f"nothing downstream can draft one and not the other."
            )

    # ------------------------------------------------------------- property 2
    # X paused FOR POSTING: drafts appear, ZERO requests are made, and the run
    # is named for what it produced rather than reported as a stop.
    paused_policy = copy.deepcopy(committed)
    run_paused = drive(tmp, "paused", paused_policy)
    rep = run_paused["report"]
    checks.append({
        "property": "paused_for_posting_drafts_and_makes_zero_api_requests",
        "x_state": rep["platform_states"].get("x"),
        "linkedin_state": rep["platform_states"].get("linkedin"),
        "api_calls": run_paused["calls"],
        "drafts_by_platform": run_paused["drafted"],
        "status": rep.get("status"),
        "sheet_bytes": len(run_paused["sheet"]),
    })
    if rep["platform_states"].get("x") != social_platforms.STATE_PAUSED_FOR_POSTING:
        failures.append(
            f"X is declared paused with pause_mode \"draft_by_hand\" but the publisher "
            f"reports its state as {rep['platform_states'].get('x')!r}. The state is what "
            f"the drafting fallback is keyed on; if it does not resolve, the pause "
            f"behaves like a dormant one and distribution stops."
        )
    if run_paused["drafted"]["x"] == 0:
        failures.append(
            "X is paused for posting with a full queue and produced ZERO drafts. That is "
            "the whole failure this pause mode exists to prevent: the API is off because "
            "it is not funded, so the sheet is the only distribution route left, and "
            "without it the run exits 0 having done nothing, every day, forever."
        )
    if not run_paused["sheet"].strip():
        failures.append("No drafts sheet was written while X is paused for posting, so "
                        "there is nowhere to read the posts meant to go out by hand.")
    if run_paused["x_calls"] or run_paused["calls"]["urlopen"]:
        failures.append(
            f"The publisher made {run_paused['x_calls']} X call(s) and "
            f"{run_paused['calls']['urlopen']} network call(s) while X is paused for "
            f"posting. A paused platform must be contacted ZERO times -- no probe, no "
            f"single attempt to see whether credits came back. Every one of those "
            f"requests is billable on a pay-per-use API the owner has declined to fund."
        )
    if rep.get("status") == "stopped_no_enabled_platform" and run_paused["drafted"]["x"]:
        failures.append(
            "The run drafted posts and still reported itself as "
            "'stopped_no_enabled_platform'. \"Posted nothing, drafted 8\" is real work "
            "and must be named as such; reporting it as a stop hides the only "
            "distribution that happened."
        )
    if not rep.get("named_stops", {}).get("x"):
        failures.append("A paused-for-posting X left no named stop in the report, so "
                        "nothing says why nothing was posted.")

    # ------------------------------------------------------------- property 3
    # LinkedIn is paused DORMANT in the same run: no drafts, no requests.
    checks.append({"property": "a_dormant_pause_produces_nothing",
                   "linkedin_drafts": run_paused["drafted"]["linkedin"],
                   "linkedin_api_calls": run_paused["li_calls"],
                   "named_stop": bool(rep.get("named_stops", {}).get("linkedin"))})
    if run_paused["drafted"]["linkedin"]:
        failures.append(
            f"LinkedIn is paused DORMANT and produced {run_paused['drafted']['linkedin']} "
            f"drafts. That switch says nothing is wanted from the platform; handing over "
            f"a sheet of LinkedIn posts to send by hand reverses it without anyone "
            f"deciding to."
        )
    if run_paused["li_calls"]:
        failures.append(
            f"{run_paused['li_calls']} LinkedIn call(s) were made while it is paused.")

    # ------------------------------------------------------------- property 4
    # Prove it negatively: with the SAME declaration except pause_mode flipped
    # to dormant, X must stop drafting. If it drafts either way, the mode is
    # decorative and property 2 proved nothing.
    dormant_x = copy.deepcopy(committed)
    dormant_x["platforms"]["x"]["pause_mode"] = social_platforms.PAUSE_DORMANT
    run_dormant = drive(tmp, "dormant-x", dormant_x)
    checks.append({"property": "flipping_the_mode_to_dormant_stops_the_drafts",
                   "x_state": run_dormant["report"]["platform_states"].get("x"),
                   "drafts_by_platform": run_dormant["drafted"],
                   "api_calls": run_dormant["calls"]})
    if run_dormant["drafted"]["x"]:
        failures.append(
            f"X drafted {run_dormant['drafted']['x']} posts with pause_mode set to "
            f"\"dormant\". The mode is then decorative: the drafting fallback is keyed on "
            f"\"switched off\" rather than on the reason, and LinkedIn would be drafted "
            f"against the owner's decision the moment anything reads the same path."
        )
    if run_dormant["x_calls"] or run_dormant["calls"]["urlopen"]:
        failures.append("A dormant X still made API calls.")

    # ------------------------------------------------------------- property 5
    # One boolean reverses it, in BOTH modes. Change nothing but `enabled` and
    # the platform posts again -- no pause_mode edit, no queue edit, no
    # un-marking pass. Proved by watching the requests appear.
    for platform, other in (("x", "linkedin"), ("linkedin", "x")):
        flipped = copy.deepcopy(committed)
        flipped["platforms"][platform]["enabled"] = True
        run_on = drive(tmp, f"flip-{platform}", flipped)
        state = run_on["report"]["platform_states"].get(platform)
        made = run_on["x_calls"] if platform == "x" else run_on["li_calls"]
        checks.append({"property": f"one_boolean_restores_{platform}",
                       "edit": f"platforms.{platform}.enabled false -> true",
                       "state": state, "api_calls_made": made,
                       "other_platform_state": run_on["report"]["platform_states"].get(other),
                       "pause_mode_left_as_declared":
                           flipped["platforms"][platform].get("pause_mode")})
        if state != social_platforms.STATE_ON:
            failures.append(
                f"Setting platforms.{platform}.enabled to true left it in state {state!r} "
                f"instead of {social_platforms.STATE_ON!r}. Reversing a pause has to stay "
                f"ONE edit; if the stale pause_mode or pause record still governs, "
                f"turning the platform back on quietly takes two."
            )
        if made == 0:
            failures.append(
                f"{platform} was switched back on by the single `enabled` boolean and "
                f"still made zero posting attempts. The switch is then not the switch, "
                f"and funding the API later would not restore posting."
            )
        if social_platforms.drafts_by_hand(platform, flipped):
            failures.append(
                f"{platform} is enabled and still reports drafts_by_hand. A live platform "
                f"must not also be drafted by hand -- that double-posts the same content."
            )

    # ------------------------------------------------------------- property 6
    # The queue is not consumed. Byte-identical driven queue, and the committed
    # queue keeps every entry in every guarded status.
    counts = {}
    if LIVE_QUEUE.exists():
        live = json.loads(LIVE_QUEUE.read_text(encoding="utf-8"))
        if isinstance(live, dict):
            live = live.get("items", [])
        for status in GUARDED_STATUSES:
            counts[status] = sum(1 for i in live if i.get("status") == status)
    checks.append({"property": "pausing_never_consumes_the_queue",
                   "committed_queue_counts": counts,
                   "driven_queue_files_unchanged": {
                       "paused": run_paused["queue_unchanged"],
                       "dormant": run_dormant["queue_unchanged"]},
                   "parked_by_platform_switch":
                       rep.get("parked_by_platform_switch")})
    for label, run in (("paused", run_paused), ("dormant", run_dormant)):
        if not run["queue_unchanged"]:
            failures.append(
                f"The {label} run rewrote its queue file. Pausing must be derived from "
                f"the switch, never stamped onto rows: a queue edited by a pause needs a "
                f"row-by-row reversal before posting can resume."
            )
    if counts and counts.get("queued_for_auto_post", 0) == 0:
        failures.append(
            "data/social-queue.json holds zero queued_for_auto_post entries. Pausing X "
            "must park the backlog, not drain it; an empty postable pool means flipping "
            "the switch back on restores nothing."
        )
    stamped = [i for i in (json.loads(LIVE_QUEUE.read_text(encoding="utf-8"))
                           if LIVE_QUEUE.exists() else [])
               if isinstance(i, dict) and any(
                   k in i for k in ("paused", "paused_at", "platform_paused"))]
    if stamped:
        failures.append(
            f"{len(stamped)} queue rows carry a per-row pause marker. Parking is derived "
            f"from the switch so that one boolean reverses it; a stamped row is a "
            f"row-by-row job to undo."
        )

    # ------------------------------------------------------------- property 7
    # The two pauses must not read the same in the report either. A human
    # reading "paused" for both cannot tell which one still needs her hands.
    stops = rep.get("named_stops", {})
    checks.append({"property": "the_two_pauses_read_differently",
                   "named_stops": {k: v[:120] for k, v in stops.items()}})
    if stops.get("x") and stops.get("linkedin") and stops["x"] == stops["linkedin"]:
        failures.append(
            "A dormant pause and a pause for posting produced identical named stops. "
            "One of them still needs her to post by hand today and the other does not; "
            "a report that cannot tell them apart is a report that gets ignored."
        )
    if stops.get("x") and "draft" not in stops["x"].lower():
        failures.append(
            "The named stop for a platform paused FOR POSTING does not mention the "
            "drafts. Nothing then tells the reader that distribution still happened, or "
            "where to find the posts she is meant to send."
        )

    # Rule 0: a guard that exercised nothing must not report PASS.
    if not checks:
        print(json.dumps({
            "validator": "social_pause_modes", "status": "FAIL", "hard_failures": 1,
            "properties_exercised": 0,
            "detail": "Exercised zero properties; passing here would vouch for nothing.",
        }, indent=2))
        return 1

    result = {
        "validator": "social_pause_modes",
        "status": "FAIL" if failures else "PASS",
        "hard_failures": len(failures),
        "strong_warnings": 0,
        "soft_warnings": 0,
        "properties_exercised": len(checks),
        "checks": checks,
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
