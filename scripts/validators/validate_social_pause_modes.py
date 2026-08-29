#!/usr/bin/env python3
"""Switching a platform's API off must not switch its distribution off with it.

What this guards
----------------
There are two reasons to switch a social platform off, and they want opposite
behaviour from everything downstream:

  dormant          Nothing is wanted from the platform at all. LinkedIn, since
                   2026-08-29: "drop linkedin for now its not important". No
                   posts and nothing produced for anyone -- a lane that quietly
                   started manufacturing LinkedIn work again would reverse that
                   decision without anyone deciding to.

  delivery_route   The API lane is off precisely BECAUSE it cannot carry the
                   content. X, since 2026-08-29: "im not funding X so find a $0
                   workaround or kill it". X's API is pay-per-use with no free
                   tier -- every write this repository has ever made answered
                   HTTP 402 problems/credits-depleted, starting with the very
                   first request, and about $0.20 per link post makes eight a
                   day roughly $48/month. So the API is not called at all, and
                   the day's posts leave through Buffer's free queue instead.

Collapse those into one `enabled: false` and there is no safe answer left. Treat
every paused platform as still-distributing and LinkedIn starts producing work
she said she did not want. Treat none of them that way and X -- the only
platform with any distribution left -- silently stops distributing, with the run
still exiting 0 and the report still saying "paused", which is exactly the shape
of a lane that does nothing forever while looking healthy.

What is NOT here any more, and must never come back
---------------------------------------------------
Until 2026-08-29 the delivery_route pause had a human fallback:
`scripts/social_drafts.py` wrote the day's posts to `reports/social-drafts.md`
as copy-paste text and the owner sent them herself. She read it once and said
"this means i manually have to do it? i will never do it honestly." A lane whose
only consumer will never consume it distributes nothing while reporting that it
did, which is worse than reporting a stop. The sheet, the batch cutter and the
`SOCIAL_DRAFTS_PATH` environment variable are gone; Buffer carries X now, for
nothing. All that survives is the read-only historical record in
`scripts/lib/hand_post_history.py`, whose single job is that a post she already
put on X with her own hands is never sent a second time.

So the properties below check the replacement is real rather than nominal: that
"paused for the API, still distributing" is a NAMED, COUNTED state in the report
rather than a sheet somebody is supposed to notice, and that no surface anywhere
asks a human to post anything. Each is driven through the REAL publisher with
the transport stubbed, and each is proved NEGATIVELY -- by also running the
opposite declaration and showing the behaviour flips:

  the API is never touched      a route-only platform makes ZERO requests to its
                                OWN API -- no probe, no single attempt "to see
                                if credits came back". Counted at post_item, at
                                the two platform senders, and at urlopen itself
  the backlog stays postable    X paused route-only leaves every entry
                                `queued_for_auto_post`: not rewritten, not
                                retired, not parked into a file, and the run
                                reports them as deferred_waiting_for_delivery_route
                                with a count it discovers rather than asserts
  a dormant pause is silent     LinkedIn produces no posts, no requests, and no
                                artefact of any kind
  nothing asks for hands        no `*social-drafts*` file appears anywhere the
                                publisher was pointed -- including at the retired
                                SOCIAL_DRAFTS_PATH, deliberately still set here
                                -- and no report carries a `manual_drafts` key
  the mode is not decorative    flipping ONLY pause_mode from delivery_route to
                                dormant changes the reported state AND stops the
                                platform being counted as awaiting a route
  one boolean reverses it       flipping ONLY `enabled` back to true restores
                                posting on either platform, in either pause
                                mode, proved by watching the requests appear
  the queue is never consumed   a driven run leaves its queue file byte-identical
                                and no row carries a per-row pause stamp
  the legacy name still lands   an older declaration saying "draft_by_hand"
                                resolves to the route-only mode, not to an
                                undocumented switch-off -- and still cannot
                                cause a sheet to be written, because there is no
                                writer left to revive
  the hand record is read-only  the ledger survives a run byte-identical, and
                                what she posted by hand is never sent again

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

# The retired hand-post lane, by every name it ever had. None of these may exist
# and nothing may recreate one: `reports/social-drafts.md` is the sheet she said
# she would never work from, and `scripts/social_drafts.py` is the thing that
# wrote it.
RETIRED_HAND_POST_PATHS = (
    ROOT / "scripts" / "social_drafts.py",
    ROOT / "reports" / "social-drafts.md",
)
# Any filename shaped like the retired sheet. Matched case-insensitively and on
# both separators, because "the sheet came back under a slightly different name"
# is the failure, not "a file called exactly social-drafts.md came back".
SHEET_NAME_MARKERS = ("social-drafts", "social_drafts")
# A key the report must never carry again. It named the count of posts a human
# was expected to send; a run that reports it is a run that has quietly grown a
# manual step back.
RETIRED_REPORT_KEY = "manual_drafts"

# The committed queue must survive all of this untouched. The check is that
# pausing does not consume it, so a legitimate change in queue size is reported
# rather than pinned.
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
    for name in ("lib", "lib.social_platforms", "lib.buffer_route",
                 "lib.hand_post_history", "lib.social_selection",
                 "social_publisher_pause_probe"):
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location("social_publisher_pause_probe", PUBLISHER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["social_publisher_pause_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


def files_under(directory):
    return {p for p in directory.rglob("*") if p.is_file()}


def sheet_shaped(paths):
    """Any file whose name looks like the retired copy-paste sheet."""
    return sorted(str(p) for p in paths
                  if any(m in p.name.lower() for m in SHEET_NAME_MARKERS))


def has_key_anywhere(blob, key):
    """True if `key` appears as a dict key anywhere in the report.

    Checked recursively rather than at the top level: moving the manual-drafts
    count one level down into a sub-object would still be a run telling her
    there is a pile of posts waiting for her hands.
    """
    if isinstance(blob, dict):
        if key in blob:
            return True
        return any(has_key_anywhere(v, key) for v in blob.values())
    if isinstance(blob, list):
        return any(has_key_anywhere(v, key) for v in blob)
    return False


def drive(tmp, name, policy, queue=None, ledger=None):
    """Run the REAL publisher against an isolated queue, ledger and policy.

    Every outbound path is counted, not just the one the happy path uses:
    post_item is where a post is decided, x_post/linkedin_post are where a
    request is built, and urlopen is where one actually leaves. A probe that
    skipped the first two would still be caught by the third.

    Each run gets its OWN directory and the whole directory is diffed before and
    after, so "no surface asks a human to post anything" can be proved by what
    the run WROTE rather than by reading the code that no longer writes it.
    """
    run_dir = tmp / name
    run_dir.mkdir(parents=True, exist_ok=True)
    qp, rp = run_dir / "queue.json", run_dir / "report.json"
    lp, pp = run_dir / "social-draft-ledger.json", run_dir / "policy.json"
    # The retired variable, pointed somewhere writable on purpose. If any code
    # path still honours it the file appears and the sheet check below fails,
    # which is the only way to tell a dead lane from a dormant one.
    retired_sheet = run_dir / "social-drafts.md"
    pp.write_text(json.dumps(policy, indent=2))
    qp.write_text(json.dumps(queue if queue is not None else synthetic_queue(), indent=2))
    if ledger is not None:
        lp.write_text(json.dumps(ledger, indent=2))
    queue_before = qp.read_bytes()
    ledger_before = lp.read_bytes() if lp.exists() else None
    files_before = files_under(run_dir)

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
        "SOCIAL_DRAFT_LEDGER_PATH": str(lp),
        "SOCIAL_DRAFTS_PATH": str(retired_sheet),
        "SOCIAL_DRY_RUN": "false", "REQUIRE_SOCIAL_SECRETS": "false",
        "X_DAILY_LIMIT": str(X_DAILY_LIMIT), "LINKEDIN_DAILY_LIMIT": "3",
        "SOCIAL_RUN_LIMIT": "3", "SOCIAL_POST_MIN_INTERVAL_SECONDS": "90",
        "X_API_KEY": "stub", "X_API_SECRET": "stub",
        "X_ACCESS_TOKEN": "stub", "X_ACCESS_TOKEN_SECRET": "stub",
        "LINKEDIN_ACCESS_TOKEN": "stub", "LINKEDIN_AUTHOR_URN": "urn:li:person:stub",
    })
    mod = load_publisher()
    calls = {"post_item": [], "x_post": [], "linkedin_post": [], "urlopen": []}

    def stub_post_item(item, dry_run=False, route=None):
        # `route` is the delivery-route argument the publisher now passes (see
        # scripts/lib/buffer_route.py). This harness always runs without a
        # Buffer token, so it is always None here; accepting it keeps the stub
        # honest about the real signature instead of turning every call into a
        # TypeError that reads as "the platform refused".
        calls["post_item"].append(dict(item))
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
    queue_after = json.loads(qp.read_text())
    platforms = [i.get("platform") for i in calls["post_item"]]
    return {
        "report": json.loads(rp.read_text()),
        "queue_after": queue_after,
        "still_queued": sum(1 for i in queue_after
                            if i.get("status") == "queued_for_auto_post"),
        "postable_x": sum(1 for i in queue_after if i.get("platform") == "x"
                          and i.get("status") == "queued_for_auto_post"),
        "sent_bodies": [i.get("body") for i in calls["post_item"]],
        "sent_platforms": platforms,
        "calls": {k: len(v) for k, v in calls.items()},
        "x_calls": platforms.count("x") + len(calls["x_post"]),
        "li_calls": platforms.count("linkedin") + len(calls["linkedin_post"]),
        "queue_unchanged": qp.read_bytes() == queue_before,
        "ledger_unchanged": (ledger_before is None
                             or (lp.exists() and lp.read_bytes() == ledger_before)),
        "new_files": sorted(str(p) for p in files_under(run_dir) - files_before),
        "sheets_written": sheet_shaped(files_under(run_dir)),
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

    from lib import hand_post_history, social_platforms  # noqa: E402

    committed = json.loads(POLICY.read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp())

    # ------------------------------------------------------------- property 1
    # Every paused platform declares a mode this repository recognises AND a
    # full paused_on/paused_by/paused_reason record. A typo reads as "dormant",
    # which is the safe default at runtime and a silent end to distribution if
    # it is ever the wrong one -- so it must not survive the build. A missing
    # pause record is worse: `route_only()` refuses to treat an undocumented
    # switch-off as still-distributing, so an incomplete record ends X's
    # distribution just as effectively as deleting the route would.
    declared = committed.get("platforms") or {}
    modes = {}
    for platform in social_platforms.PLATFORMS:
        entry = declared.get(platform)
        if not isinstance(entry, dict):
            failures.append(
                f"data/social-brand-policy.json declares no switch for {platform}, so "
                f"nothing records whether it posts through a route, or is off entirely."
            )
            continue
        enabled = bool(entry.get("enabled", True))
        raw = social_platforms.declared_pause_mode(platform, committed)
        resolved = social_platforms.pause_mode(platform, committed)
        missing = social_platforms.missing_pause_fields(platform, committed)
        modes[platform] = {
            "enabled": enabled, "declared_pause_mode": raw,
            "resolved_pause_mode": resolved if not enabled else None,
            "state": social_platforms.platform_state(platform, None, committed),
            "route_only": social_platforms.route_only(platform, committed),
            "missing_pause_fields": missing,
        }
        if enabled:
            continue
        if raw is None:
            failures.append(
                f"platforms.{platform} is switched off with no pause_mode. Off must say "
                f"which kind of off it is: \"dormant\" produces nothing at all, "
                f"\"delivery_route\" keeps the platform distributing through its declared "
                f"route while its own API stays dark. Defaulting silently to dormant is "
                f"how a platform stops distributing with nothing reporting the loss."
            )
        elif raw not in social_platforms.PAUSE_MODES:
            failures.append(
                f"platforms.{platform}.pause_mode is {raw!r}, which is not one of "
                f"{list(social_platforms.PAUSE_MODES)}. At runtime an unrecognised mode "
                f"reads as dormant, so a typo here silently ends this platform's "
                f"distribution while the run stays green."
            )
        if missing:
            failures.append(
                f"platforms.{platform} is switched off but its pause record is missing "
                f"{missing}. A pause without who/when/why is an undocumented switch-off: "
                f"it resolves to {social_platforms.STATE_UNDOCUMENTED_OFF!r}, route_only() "
                f"refuses it, and a platform that was supposed to keep distributing "
                f"through its route quietly stops."
            )
    # The rule above is only worth anything if it fires. Prove the detector
    # rather than trusting it: a near-miss typo of the real mode must not be
    # recognised, and must not resolve to the route-only mode by accident.
    typo_policy = copy.deepcopy(committed)
    typo_policy["platforms"]["x"]["pause_mode"] = "delivery-route"
    typo_raw = social_platforms.declared_pause_mode("x", typo_policy)
    typo_detected = typo_raw not in social_platforms.PAUSE_MODES
    checks.append({"property": "every_paused_platform_declares_a_legible_mode_and_record",
                   "platforms": modes,
                   "recognised_modes": list(social_platforms.PAUSE_MODES),
                   "typo_is_detected": typo_detected,
                   "typo_resolves_to": social_platforms.pause_mode("x", typo_policy)})
    if not typo_detected:
        failures.append(
            "A pause_mode of 'delivery-route' -- one character away from the real one -- "
            "is accepted as legible by this check, so the check would pass a declaration "
            "that silently reads as dormant at runtime and ends X's distribution."
        )
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
                f"nothing downstream can keep one distributing and let the other rest."
            )

    # ------------------------------------------------------------- property 2
    # X paused ROUTE-ONLY with the route unavailable: ZERO requests to X's own
    # API, and the backlog it could not send stays postable and is reported by
    # name. This is the state that replaced the sheet. The old file asserted "a
    # full batch of drafts was written"; the observable now is
    # deferred_waiting_for_delivery_route, which is a count in the report she
    # already reads rather than a file she said she would never open.
    paused_policy = copy.deepcopy(committed)
    fixture = synthetic_queue()
    x_postable = sum(1 for i in fixture if i.get("platform") == "x")
    run_paused = drive(tmp, "paused", paused_policy, queue=fixture)
    rep = run_paused["report"]
    deferred = rep.get("deferred_waiting_for_delivery_route")
    checks.append({
        "property": "route_only_makes_zero_api_requests_and_defers_by_name",
        "x_state": rep["platform_states"].get("x"),
        "linkedin_state": rep["platform_states"].get("linkedin"),
        "api_calls": run_paused["calls"],
        "deferred_waiting_for_delivery_route": deferred,
        "route_only_platforms": rep.get("route_only_platforms"),
        "x_entries_in_fixture": x_postable,
        "x_still_queued_for_auto_post": run_paused["postable_x"],
        "still_postable_after_run": rep.get("still_postable_after_run"),
        "status": rep.get("status"),
    })
    if rep["platform_states"].get("x") != social_platforms.STATE_PAUSED_ROUTE_ONLY:
        failures.append(
            f"X is declared paused with pause_mode \"delivery_route\" but the publisher "
            f"reports its state as {rep['platform_states'].get('x')!r}. That state is what "
            f"the whole route-only lane is keyed on; if it does not resolve, the pause "
            f"behaves like a dormant one and X's distribution ends without a word."
        )
    if run_paused["x_calls"] or run_paused["calls"]["urlopen"]:
        failures.append(
            f"The publisher made {run_paused['x_calls']} X call(s) and "
            f"{run_paused['calls']['urlopen']} network call(s) while X is paused route-only. "
            f"A route-only platform must have its OWN API contacted ZERO times -- no probe, "
            f"no single attempt to see whether credits came back. Every one of those "
            f"requests is billable on a pay-per-use API the owner has declined to fund, and "
            f"every one this repository has ever made answered 402 credits-depleted."
        )
    if "x" not in (rep.get("route_only_platforms") or []):
        failures.append(
            f"X is paused route-only and the report's route_only_platforms is "
            f"{rep.get('route_only_platforms')!r}. If the run cannot name the platforms it "
            f"is still distributing for, the deferred count below belongs to nobody and "
            f"the state is indistinguishable from a dormant pause."
        )
    if not isinstance(deferred, int):
        failures.append(
            f"The report's deferred_waiting_for_delivery_route is "
            f"{deferred!r}, not a count. It is the named, visible state that replaced "
            f"reports/social-drafts.md; a run that cannot say how many posts are waiting "
            f"on the route is back to reporting a pause and nothing else."
        )
    elif deferred <= 0:
        failures.append(
            f"X is paused route-only with {x_postable} postable X entries and the run "
            f"reported deferred_waiting_for_delivery_route: {deferred}. Zero here means the "
            f"backlog vanished from the report: the run exits 0, says 'paused', and nobody "
            f"can tell it apart from a lane that has quietly had nothing to distribute for "
            f"weeks."
        )
    elif deferred != x_postable:
        failures.append(
            f"{x_postable} X entries were postable and the run deferred {deferred}. The "
            f"count must be the whole waiting backlog, not a sampled batch -- an "
            f"undercount is exactly how a queue drifts out of distribution unnoticed."
        )
    if run_paused["postable_x"] != x_postable:
        failures.append(
            f"{x_postable} X entries went in queued_for_auto_post and "
            f"{run_paused['postable_x']} came out. A route-only pause must leave the "
            f"backlog POSTABLE: rewriting or retiring those rows means flipping the route "
            f"back on restores nothing, and each rewritten row is a row-by-row job to undo."
        )
    if rep.get("status") != "deferred_waiting_for_delivery_route":
        failures.append(
            f"The run reported status {rep.get('status')!r} while deferring {deferred} X "
            f"posts to the delivery route. \"Posted nothing, {deferred} waiting on the "
            f"route\" and \"nothing left to distribute at all\" are different outcomes and "
            f"must not share a status; naming them the same is how a stalled route looks "
            f"identical to an idle one, forever."
        )
    if not rep.get("named_stops", {}).get("x"):
        failures.append("A route-only X left no named stop in the report, so nothing says "
                        "why nothing was posted or where its posts have gone.")

    # ------------------------------------------------------------- property 3
    # LinkedIn is paused DORMANT in the same run: no posts, no requests, and
    # nothing produced for anyone.
    checks.append({"property": "a_dormant_pause_produces_nothing",
                   "linkedin_api_calls": run_paused["li_calls"],
                   "anything_sent_for_linkedin":
                       run_paused["sent_platforms"].count("linkedin"),
                   "named_stop": bool(rep.get("named_stops", {}).get("linkedin")),
                   "files_the_run_wrote": run_paused["new_files"]})
    if run_paused["li_calls"]:
        failures.append(
            f"{run_paused['li_calls']} LinkedIn call(s) were made while it is paused "
            f"dormant. \"drop linkedin for now\" means nothing is attempted at all.")
    if (rep.get("route_only_platforms") or []) and "linkedin" in rep["route_only_platforms"]:
        failures.append(
            "LinkedIn is paused DORMANT and the run counts it as a platform still awaiting "
            "a delivery route. That switch says nothing is wanted from the platform; "
            "queueing LinkedIn posts for onward delivery reverses it without anyone "
            "deciding to."
        )

    # ------------------------------------------------------------- property 4
    # No surface asks a human to post anything. Proved by what the run WROTE,
    # not by reading the code that no longer writes it: the retired
    # SOCIAL_DRAFTS_PATH is deliberately still set to a writable path in the run
    # directory, and the whole directory is diffed. She said of the sheet: "this
    # means i manually have to do it? i will never do it honestly." Anything
    # that reappears in that shape is a lane distributing nothing while
    # reporting that it did.
    surviving_lane = [str(p) for p in RETIRED_HAND_POST_PATHS if p.exists()]
    checks.append({
        "property": "no_surface_asks_a_human_to_post",
        "retired_paths_still_present": surviving_lane,
        "sheet_shaped_files_written": {
            "paused": run_paused["sheets_written"]},
        "retired_env_var_pointed_at_a_writable_path": True,
        "manual_drafts_key_in_report": has_key_anywhere(rep, RETIRED_REPORT_KEY),
        "hand_post_history_present_in_report": "hand_post_history" in rep,
    })
    if surviving_lane:
        failures.append(
            f"The retired hand-post lane is back on disk: {surviving_lane}. The sheet and "
            f"its writer were deleted on 2026-08-29 because the owner said \"this means i "
            f"manually have to do it? i will never do it honestly\" -- a lane whose only "
            f"consumer will never consume it distributes nothing while the run reports "
            f"that it did."
        )
    if run_paused["sheets_written"]:
        failures.append(
            f"A route-only run wrote {run_paused['sheets_written']}. SOCIAL_DRAFTS_PATH is "
            f"set to a writable path here on purpose: a file appearing there means some "
            f"code path still honours the retired variable and the copy-paste sheet is "
            f"alive again under whatever name it was given."
        )
    if has_key_anywhere(rep, RETIRED_REPORT_KEY):
        failures.append(
            f"The run report carries a {RETIRED_REPORT_KEY!r} key. That number counted "
            f"posts waiting on the owner's hands. Nothing in this repository asks her to "
            f"post anything any more; a report that still counts manual drafts is a report "
            f"describing a step nobody will take."
        )
    if "hand_post_history" not in rep:
        failures.append(
            "The report carries no hand_post_history block. The ledger is read on every "
            "run for one reason -- the posts she put on X with her own hands are live on "
            "the profile and were never consumed from the queue -- and the report is where "
            "that guard is visible. Without it, nothing shows the guard still ran."
        )

    # ------------------------------------------------------------- property 5
    # Prove the mode negatively: with the SAME declaration except pause_mode
    # flipped to dormant, X's reported state must change AND it must stop being
    # counted as awaiting a route. If both modes report the same thing, the mode
    # is decorative and property 2 proved nothing.
    dormant_x = copy.deepcopy(committed)
    dormant_x["platforms"]["x"]["pause_mode"] = social_platforms.PAUSE_DORMANT
    run_dormant = drive(tmp, "dormant-x", dormant_x, queue=synthetic_queue())
    dorm = run_dormant["report"]
    checks.append({"property": "flipping_the_mode_to_dormant_changes_the_observable",
                   "route_only_state": rep["platform_states"].get("x"),
                   "dormant_state": dorm["platform_states"].get("x"),
                   "dormant_route_only_platforms": dorm.get("route_only_platforms"),
                   "dormant_deferred":
                       dorm.get("deferred_waiting_for_delivery_route"),
                   "dormant_status": dorm.get("status"),
                   "api_calls": run_dormant["calls"]})
    if dorm["platform_states"].get("x") == rep["platform_states"].get("x"):
        failures.append(
            f"X reports the same state ({dorm['platform_states'].get('x')!r}) with "
            f"pause_mode \"dormant\" as with \"delivery_route\". The mode is then "
            f"decorative: the route lane is keyed on \"switched off\" rather than on the "
            f"reason, and LinkedIn would start being distributed against the owner's "
            f"decision the moment anything reads the same path."
        )
    if "x" in (dorm.get("route_only_platforms") or []):
        failures.append(
            "X is paused DORMANT and is still reported as awaiting a delivery route. A "
            "dormant pause means nothing is wanted from the platform at all; carrying its "
            "posts onward anyway reverses the decision without anyone making it."
        )
    if dorm.get("deferred_waiting_for_delivery_route"):
        failures.append(
            f"X is paused DORMANT and the run still defers "
            f"{dorm['deferred_waiting_for_delivery_route']} posts to a delivery route. "
            f"Nothing may be waiting to go out for a platform the owner switched off "
            f"entirely."
        )
    if run_dormant["sheets_written"]:
        failures.append(f"A dormant run wrote {run_dormant['sheets_written']}.")
    if run_dormant["x_calls"] or run_dormant["calls"]["urlopen"]:
        failures.append("A dormant X still made API calls.")

    # ------------------------------------------------------------- property 6
    # One boolean reverses it, in BOTH modes. Change nothing but `enabled` and
    # the platform posts again -- no pause_mode edit, no queue edit, no
    # un-marking pass. Proved by watching the requests appear.
    for platform, other in (("x", "linkedin"), ("linkedin", "x")):
        flipped = copy.deepcopy(committed)
        flipped["platforms"][platform]["enabled"] = True
        run_on = drive(tmp, f"flip-{platform}", flipped, queue=synthetic_queue())
        state = run_on["report"]["platform_states"].get(platform)
        made = run_on["x_calls"] if platform == "x" else run_on["li_calls"]
        checks.append({"property": f"one_boolean_restores_{platform}",
                       "edit": f"platforms.{platform}.enabled false -> true",
                       "state": state, "api_calls_made": made,
                       "other_platform_state": run_on["report"]["platform_states"].get(other),
                       "sheets_written": run_on["sheets_written"],
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
        if social_platforms.route_only(platform, flipped):
            failures.append(
                f"{platform} is enabled and still reports route_only. A platform posting "
                f"through its own API must not also be handed to a delivery route -- that "
                f"puts the same content on the same profile twice."
            )
        if run_on["sheets_written"]:
            failures.append(
                f"Re-enabling {platform} produced {run_on['sheets_written']}.")

    # ------------------------------------------------------------- property 7
    # The queue is not consumed. Byte-identical driven queue in every scenario,
    # and the committed queue keeps every entry in every guarded status.
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
                       "route_only": run_paused["queue_unchanged"],
                       "dormant": run_dormant["queue_unchanged"]},
                   "parked_by_platform_switch":
                       rep.get("parked_by_platform_switch")})
    for label, run in (("route-only", run_paused), ("dormant", run_dormant)):
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

    # ------------------------------------------------------------- property 8
    # The legacy spelling still lands where it always meant. Older copies of
    # data/social-brand-policy.json say pause_mode "draft_by_hand", from when
    # the fallback was the copy-paste sheet. Read as an unknown mode it would
    # default to dormant and silently end X's distribution -- the exact failure
    # this file exists to catch -- so it must resolve to the route-only mode.
    # And it must not be able to revive anything: there is no writer left.
    legacy = copy.deepcopy(committed)
    legacy["platforms"]["x"]["pause_mode"] = social_platforms.PAUSE_LEGACY_DRAFT_BY_HAND
    run_legacy = drive(tmp, "legacy-draft-by-hand", legacy, queue=synthetic_queue())
    leg = run_legacy["report"]
    checks.append({
        "property": "the_legacy_draft_by_hand_spelling_still_means_route_only",
        "declared": social_platforms.declared_pause_mode("x", legacy),
        "resolved": social_platforms.pause_mode("x", legacy),
        "state": leg["platform_states"].get("x"),
        "route_only_platforms": leg.get("route_only_platforms"),
        "deferred": leg.get("deferred_waiting_for_delivery_route"),
        "sheets_written": run_legacy["sheets_written"],
        "api_calls": run_legacy["calls"]})
    if social_platforms.pause_mode("x", legacy) != social_platforms.PAUSE_ROUTE_ONLY:
        failures.append(
            f"pause_mode \"draft_by_hand\" resolves to "
            f"{social_platforms.pause_mode('x', legacy)!r} instead of "
            f"{social_platforms.PAUSE_ROUTE_ONLY!r}. That spelling is what every "
            f"declaration written before 2026-08-29 says; reading it as anything else "
            f"turns an old but perfectly clear decision into an undocumented switch-off "
            f"and stops X distributing."
        )
    if leg["platform_states"].get("x") != social_platforms.STATE_PAUSED_ROUTE_ONLY:
        failures.append(
            f"An X declared with the legacy \"draft_by_hand\" mode reports state "
            f"{leg['platform_states'].get('x')!r}. The rename was a rename; it must not "
            f"change what an existing declaration does."
        )
    if not leg.get("deferred_waiting_for_delivery_route"):
        failures.append(
            "The legacy \"draft_by_hand\" declaration deferred nothing to the delivery "
            "route, so under the old spelling X's backlog is invisible in the report."
        )
    if run_legacy["sheets_written"]:
        failures.append(
            f"The legacy \"draft_by_hand\" declaration produced {run_legacy['sheets_written']}. "
            f"The name survives only so an old file still parses; it must never bring the "
            f"copy-paste sheet back with it, because the owner will not work from one."
        )
    if run_legacy["x_calls"] or run_legacy["calls"]["urlopen"]:
        failures.append("The legacy \"draft_by_hand\" declaration still contacted X's API.")

    # ------------------------------------------------------------- property 9
    # The two pauses must not read the same in the report either. A human
    # reading "paused" for both cannot tell which one is still distributing.
    stops = rep.get("named_stops", {})
    checks.append({"property": "the_two_pauses_read_differently",
                   "named_stops": {k: v[:120] for k, v in stops.items()}})
    if stops.get("x") and stops.get("linkedin") and stops["x"] == stops["linkedin"]:
        failures.append(
            "A dormant pause and a route-only pause produced identical named stops. One "
            "of them is still distributing today and the other is deliberately silent; a "
            "report that cannot tell them apart is a report that gets ignored."
        )
    if stops.get("x") and "route" not in stops["x"].lower():
        failures.append(
            "The named stop for a platform paused ROUTE-ONLY does not mention the "
            "delivery route. Nothing then tells the reader that its posts are still "
            "queued and going out on a later run rather than lost."
        )
    for platform, stop in stops.items():
        for marker in SHEET_NAME_MARKERS + ("by hand", "copy-paste", "copy and paste"):
            if marker in stop.lower() and "posted by hand" not in stop.lower():
                failures.append(
                    f"The named stop for {platform} points the reader at {marker!r}. "
                    f"Nothing asks her to post anything any more and the sheet does not "
                    f"exist; a report that still sends her to it describes a step that "
                    f"cannot be taken."
                )

    # ------------------------------------------------------------ property 10
    # The hand-post record is history, not a workflow. It is read on every run
    # so that a post the owner already put on X with her own hands is never sent
    # a second time -- those entries were never consumed from the queue, so
    # nothing else stands between them and a duplicate on a profile whose whole
    # purpose is to look like a person. It must survive a run byte-identical:
    # a ledger the publisher writes back to is a ledger that can lose the
    # marker, and losing the marker opens the double-post silently.
    hand_items = [i for i in synthetic_queue() if i.get("platform") == "x"][:4]
    hand_ledger = {
        "schema": hand_post_history.LEDGER_SCHEMA,
        hand_post_history.MARKER_FIELD: "batch-she-posted",
        "batches": [
            {"batch_id": "batch-she-posted", "platform": "x",
             "items": [{"fingerprint": hand_post_history.fingerprint(i),
                        "body": i["body"]} for i in hand_items]},
            {"batch_id": "batch-never-posted", "platform": "x",
             "items": [{"fingerprint": hand_post_history.fingerprint(i), "body": i["body"]}
                       for i in [j for j in synthetic_queue()
                                 if j.get("platform") == "x"][4:6]]},
        ],
    }
    run_hand = drive(tmp, "hand-record", copy.deepcopy(committed),
                     queue=synthetic_queue(), ledger=hand_ledger)
    record = run_hand["report"].get("hand_post_history") or {}
    expected_by_hand = len(hand_post_history.posted_by_hand_fingerprints(hand_ledger))
    checks.append({
        "property": "the_hand_post_record_is_read_only_history",
        "ledger_file_unchanged": run_hand["ledger_unchanged"],
        "posts_she_posted_by_hand_expected": expected_by_hand,
        "posts_she_posted_by_hand_reported": record.get("posts_she_posted_by_hand"),
        "marker": record.get(hand_post_history.MARKER_FIELD),
        "files_the_run_wrote": run_hand["new_files"],
        "sheets_written": run_hand["sheets_written"]})
    if not run_hand["ledger_unchanged"]:
        failures.append(
            "The publisher rewrote data/social-draft-ledger.json. That file is a "
            "historical record with no writer: `marked_posted_through` names the last "
            "batch the owner posted to X with her own hands, and everything at or before "
            "it is live on the profile. A run that writes it back can move or drop the "
            "marker, and the only guard against posting those entries a second time goes "
            "with it."
        )
    if record.get("posts_she_posted_by_hand") != expected_by_hand:
        failures.append(
            f"The run reported {record.get('posts_she_posted_by_hand')!r} posts as already "
            f"posted by hand, from a ledger holding {expected_by_hand}. The report is where "
            f"that guard is visible; if the count is wrong there, nothing shows whether the "
            f"guard is reading the marker at all."
        )
    if record.get(hand_post_history.MARKER_FIELD) != hand_ledger[hand_post_history.MARKER_FIELD]:
        failures.append(
            f"The run reported marked_posted_through as "
            f"{record.get(hand_post_history.MARKER_FIELD)!r} rather than "
            f"{hand_ledger[hand_post_history.MARKER_FIELD]!r}. The marker is the whole "
            f"record; misreading it either re-sends posts she has already made or holds "
            f"back drafts that were never posted and are free to go."
        )
    if run_hand["sheets_written"]:
        failures.append(
            f"Supplying a hand-post ledger produced {run_hand['sheets_written']}. The "
            f"record is history; it must never cause anything to ask her for more.")

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
