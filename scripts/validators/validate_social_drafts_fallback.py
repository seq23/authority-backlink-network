#!/usr/bin/env python3
"""A platform that cannot post must still get the content out, by hand.

What this guards
----------------
X answers every write on this account with HTTP 402 credits-depleted, which is
X's pay-per-use billing saying the enrolled developer account has no credits -
not a period cap that resets, and not something a lower posting rate gets under.
The first request of the first run in this repository's history got it, and no
post has ever succeeded. So "defer and retry tomorrow" is, on its own, a lane
that exits 0 having done nothing, every run, forever, while 581 published pages
go undistributed.

scripts/social_drafts.py is the answer: when a platform is switched ON and still
cannot get a post out, the day's highest-value posts are written to
reports/social-drafts.md as copy-paste text, and the owner posts them by hand.
Four properties have to hold for that to be worth anything, and none of them can
be seen by reading configuration - so this drives the REAL publisher against
synthetic queues with the platform API stubbed and asserts them:

  drafts actually appear   platform refuses -> a sheet exists, with posts on it,
                           carrying the exact characters the API would have sent
  done means done          a batch marked posted in the ledger is never offered
                           again, and no second batch piles on top of an open one
  the queue is untouched   drafting reads data/social-queue.json and writes
                           nothing to it - byte for byte - so restoring API
                           access restores automatic posting with no undo pass
  the caps still bind      the drafting path must not become a second way to
                           walk the whole queue: a 402 still costs exactly ONE
                           request, and a batch never exceeds the daily limit

And one thing that must NOT happen: a platform paused by decision - LinkedIn is,
as of 2026-08-29 - produces no drafts. A pause is a choice, not an outage, and
drafting it would quietly reverse the switch.

Fails hard if it exercises zero scenarios.
"""
from __future__ import annotations

import contextlib
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
DRAFTER = ROOT / "scripts" / "social_drafts.py"
LIVE_QUEUE = ROOT / "data" / "social-queue.json"
LIVE_LEDGER = ROOT / "data" / "social-draft-ledger.json"

X_DAILY_LIMIT = 8
RUN_LIMIT = 3
QUEUE_SIZE = 40

REFUSAL_402 = {"ok": False, "error": 'HTTP 402: {"detail":"credits depleted"}'}

VOCAB = [
    w + s
    for s in ("alpha", "bravo", "delta", "gamma", "omega", "sigma", "theta", "kappa")
    for w in (
        "quiet", "river", "stone", "amber", "cedar", "falcon", "harbor", "ivory",
        "juniper", "lantern", "meadow", "nimbus", "orchid", "pewter", "quartz",
        "saffron", "tundra", "velvet", "willow", "zephyr",
    )
]


def synthetic_queue(n=QUEUE_SIZE):
    return [
        {
            "platform": "x",
            "brand": f"Brand {i % 7}",
            "domain": f"example{i % 7}.com",
            "post_type": "link_share",
            # Long enough that the X length trim genuinely fires on every entry,
            # so "the trim never eats the URL" is actually exercised rather than
            # asserted about strings that were never trimmed.
            "body": " ".join(VOCAB[(i * 17 + j) % len(VOCAB)] for j in range(40)),
            "source_url": (f"https://example{i % 7}.com/daily/"
                           f"2026-08-29-a-deliberately-long-slug-for-entry-{i}.html"),
            "status": "queued_for_auto_post",
            "created_at": "2026-08-01",
        }
        for i in range(n)
    ]


def load_publisher():
    spec = importlib.util.spec_from_file_location("social_publisher_drafts_probe", PUBLISHER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["social_publisher_drafts_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


def drive(tmp, name, response, runs=1, env_extra=None, queue=None):
    """Run the real publisher against an isolated queue/ledger/sheet."""
    qp, rp = tmp / f"{name}-queue.json", tmp / f"{name}-report.json"
    lp, dp = tmp / f"{name}-ledger.json", tmp / f"{name}-drafts.md"
    qp.write_text(json.dumps(queue if queue is not None else synthetic_queue()))
    os.environ.update({
        "SOCIAL_QUEUE_PATH": str(qp), "SOCIAL_REPORT_PATH": str(rp),
        "SOCIAL_DRAFT_LEDGER_PATH": str(lp), "SOCIAL_DRAFTS_PATH": str(dp),
        "SOCIAL_DRY_RUN": "false", "REQUIRE_SOCIAL_SECRETS": "false",
        "X_DAILY_LIMIT": str(X_DAILY_LIMIT), "SOCIAL_RUN_LIMIT": str(RUN_LIMIT),
        "SOCIAL_POST_MIN_INTERVAL_SECONDS": "90",
        "ENABLE_X_POSTING": "true", "ENABLE_LINKEDIN_POSTING": "false",
        "X_API_KEY": "stub", "X_API_SECRET": "stub",
        "X_ACCESS_TOKEN": "stub", "X_ACCESS_TOKEN_SECRET": "stub",
    })
    os.environ.update(env_extra or {})
    calls_total = 0
    for _ in range(runs):
        mod = load_publisher()
        calls = [0]

        def stub_post(item, dry_run=False, _c=calls):
            _c[0] += 1
            if response.get("ok"):
                return {"ok": True, "id": f"stub-{_c[0]}", "status": 201}
            return dict(response)

        mod.post_item = stub_post
        mod.time.sleep = lambda *_a, **_k: None
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                mod.main()
            except SystemExit:
                pass
        calls_total += calls[0]
    return {
        "queue_path": qp, "ledger_path": lp, "drafts_path": dp,
        "report": json.loads(rp.read_text()),
        "queue": json.loads(qp.read_text()),
        "ledger": json.loads(lp.read_text()) if lp.exists() else None,
        "sheet": dp.read_text() if dp.exists() else "",
        "calls": calls_total,
    }


def fingerprints(ledger, batch_index=None):
    batches = ledger.get("batches", [])
    if batch_index is not None:
        batches = [batches[batch_index]]
    return {e["fingerprint"] for b in batches for e in b.get("items", [])}


def main() -> int:  # noqa: C901 - one assertion per property, kept flat on purpose
    failures, checks = [], []
    for path in (PUBLISHER, DRAFTER):
        if not path.exists():
            print(json.dumps({
                "validator": "social_drafts_fallback", "status": "FAIL",
                "hard_failures": 1,
                "detail": f"{path} is missing; the drafting fallback cannot be exercised.",
            }, indent=2))
            return 1

    import social_drafts  # noqa: E402 - needs scripts/ on the path, set above
    from lib import social_selection  # noqa: E402

    tmp = Path(tempfile.mkdtemp())

    # ---------------------------------------------------------------- property 1
    # The platform refuses; drafts must appear, and say exactly what the API
    # would have sent.
    refused = drive(tmp, "refused", REFUSAL_402)
    ledger = refused["ledger"] or {}
    batches = ledger.get("batches", [])
    drafted = sum(len(b.get("items", [])) for b in batches)
    checks.append({"property": "drafts_produced_when_platform_refuses",
                   "requests_made": refused["calls"], "batches": len(batches),
                   "drafts": drafted, "sheet_bytes": len(refused["sheet"])})
    if drafted == 0:
        failures.append(
            "The platform answered 402 with 40 postable entries queued and NO drafts "
            "were produced. That is the silent-defer shape: the run exits 0, nothing "
            "was posted, nothing was handed to a human, and 581 published pages stay "
            "undistributed for as long as the API stays dead."
        )
    if not refused["sheet"].strip():
        failures.append("No drafts sheet was written; there is nowhere for the owner to "
                        "read the posts she is meant to send by hand.")
    # The sheet must carry the post VERBATIM, not the raw body.
    queue_by_fp = {social_drafts.fingerprint(i): i for i in refused["queue"]}
    for batch in batches:
        for entry in batch.get("items", []):
            source = queue_by_fp.get(entry["fingerprint"])
            if source is None:
                failures.append(f"Draft {entry['fingerprint']} matches no queue entry.")
                continue
            expected = social_selection.post_text(source)
            if entry["text"] != expected:
                failures.append(
                    f"Draft {entry['fingerprint']} does not carry the text the API would "
                    f"have sent. A sheet she has to edit before posting is a sheet she "
                    f"will not use."
                )
            if entry.get("url") and entry["url"] not in entry["text"]:
                failures.append(
                    f"Draft {entry['fingerprint']} carries a truncated or missing URL. The "
                    f"length trim must come out of the body, never out of the link: a post "
                    f"whose URL is cut is a dead link, which is no click, no citation and "
                    f"no backlink for the slot it spent."
                )
            if entry["text"] not in refused["sheet"]:
                failures.append(
                    f"Draft {entry['fingerprint']} is in the ledger but its text is not "
                    f"on the sheet, so it cannot actually be copied and posted."
                )

    # ---------------------------------------------------------------- property 4a
    # A batch must never exceed a day's worth. A wall of 581 drafts is as
    # useless as an empty queue, and it is also how a fallback turns into a
    # second way to walk the whole queue.
    for batch in batches:
        if len(batch.get("items", [])) > X_DAILY_LIMIT:
            failures.append(
                f"Batch {batch['batch_id']} holds {len(batch['items'])} drafts against a "
                f"daily limit of {X_DAILY_LIMIT}."
            )

    # ---------------------------------------------------------------- property 4b
    # The caps still bind on the path that now also drafts. One refusal, one
    # request - drafting must not have reopened the loop.
    checks.append({"property": "refusal_still_costs_exactly_one_request",
                   "requests_made": refused["calls"], "requests_expected": 1})
    if refused["calls"] > 1:
        failures.append(
            f"The publisher made {refused['calls']} requests after a 402 refusal. Adding "
            f"a drafting fallback must not reopen the loop the attempt-counting caps "
            f"closed; a refusal costs exactly one request."
        )

    # ---------------------------------------------------------------- property 3
    # An open batch is reissued, never piled on top of.
    reissued = drive(tmp, "reissue", REFUSAL_402, runs=3)
    r_ledger = reissued["ledger"] or {}
    open_ids = [b["batch_id"] for b in social_drafts.open_batches(r_ledger)]
    checks.append({"property": "open_batch_is_reissued_not_multiplied",
                   "runs": 3, "batches_total": len(r_ledger.get("batches", [])),
                   "open_batches": open_ids})
    if len(r_ledger.get("batches", [])) != 1:
        failures.append(
            f"Three runs against a dead platform produced "
            f"{len(r_ledger.get('batches', []))} draft batches. An unposted batch must be "
            f"re-rendered, not added to: a backlog of drafts is exactly the wall of work "
            f"the batch size exists to prevent."
        )

    # ---------------------------------------------------------------- property 2
    # Marked done stays done. One edit to marked_posted_through retires the
    # whole batch, and nothing in it is ever offered again.
    done_id = r_ledger["batches"][0]["batch_id"] if r_ledger.get("batches") else None
    first_fps = fingerprints(r_ledger, 0) if done_id else set()
    if done_id:
        r_ledger["marked_posted_through"] = done_id
        reissued["ledger_path"].write_text(json.dumps(r_ledger, indent=2))
        after = drive(tmp, "reissue", REFUSAL_402, queue=reissued["queue"])
        a_ledger = after["ledger"] or {}
        # The temp ledger persists across drive() calls with the same name, so the
        # marked batch is still there and a NEW one must have been cut beside it.
        new_fps = fingerprints(a_ledger) - first_fps
        repeated = first_fps & fingerprints(a_ledger, len(a_ledger["batches"]) - 1)
        sheet_repeats = [
            e["text"] for b in r_ledger["batches"][:1] for e in b["items"]
            if e["text"] in after["sheet"]
        ]
        checks.append({"property": "a_draft_marked_done_is_never_reoffered",
                       "marked_posted_through": done_id,
                       "batches_after": len(a_ledger.get("batches", [])),
                       "new_drafts": len(new_fps),
                       "reoffered": len(repeated),
                       "reappeared_on_sheet": len(sheet_repeats)})
        if repeated:
            failures.append(
                f"{len(repeated)} drafts from the batch marked posted were offered again "
                f"in the next batch. A draft she has already posted must never come back, "
                f"or the sheet becomes untrustworthy and she stops using it."
            )
        if sheet_repeats:
            failures.append(
                f"{len(sheet_repeats)} posts from the batch marked posted are still "
                f"printed on the sheet. Marking a batch done must remove it from view."
            )
        if len(a_ledger.get("batches", [])) < 2 or not new_fps:
            failures.append(
                "Marking the open batch posted did not release a new one. The single "
                "declaration is the whole mark-done mechanism; if it does not advance, "
                "distribution stops at the first batch."
            )
        # Done-ness must be DERIVED from that one field, never stamped per row.
        stamped = [e for b in a_ledger.get("batches", []) for e in b.get("items", [])
                   if any(k in e for k in ("posted", "posted_at", "done", "status"))]
        if stamped:
            failures.append(
                f"{len(stamped)} draft rows carry a per-row done marker. Done-ness is "
                f"derived from marked_posted_through so that changing her mind is one "
                f"edit; a per-row stamp is a row-by-row job to reverse."
            )

    # ---------------------------------------------------------------- property 5
    # Drafting must never consume the queue. Byte-for-byte, called directly.
    q_path = tmp / "untouched-queue.json"
    original = synthetic_queue()
    q_path.write_text(json.dumps(original, indent=2))
    before_bytes = q_path.read_bytes()
    live_queue = json.loads(q_path.read_text())
    receipt = social_drafts.run(
        live_queue,
        social_selection.eligible_in_priority_order(live_queue, {}, "2026-08-29", 739857),
        {"x": "synthetic outage"},
        policy={}, ledger_path=tmp / "untouched-ledger.json",
        drafts_path=tmp / "untouched-drafts.md", today="2026-08-29",
        batch_sizes={"x": X_DAILY_LIMIT})
    postable_after = sum(1 for i in live_queue
                         if i.get("status") in social_selection.POSTABLE_STATUSES)
    checks.append({"property": "drafting_never_consumes_the_queue",
                   "queue_entries": len(original), "postable_after": postable_after,
                   "drafts_written": receipt["drafts_written"],
                   "queue_file_unchanged": q_path.read_bytes() == before_bytes,
                   "queue_object_unchanged": live_queue == original})
    if q_path.read_bytes() != before_bytes or live_queue != original:
        failures.append(
            "Drafting mutated the queue. The 581 entries must survive drafting untouched, "
            "or restoring API access needs an un-drafting pass and the automatic lane "
            "cannot simply resume."
        )
    if postable_after != len(original):
        failures.append(
            f"{postable_after} of {len(original)} entries are still postable after "
            f"drafting. Drafting must not retire, consume or reserve a queue entry."
        )
    if receipt["drafts_written"] == 0:
        failures.append("Drafting produced nothing from a queue of postable entries.")

    # ---------------------------------------------------------------- property 6
    # A platform paused by decision produces no drafts. LinkedIn is paused; a
    # fallback that drafted it would quietly reverse the owner's switch.
    from lib import social_platforms  # noqa: E402
    paused_states = {"linkedin": social_platforms.STATE_PAUSED,
                     "x": social_platforms.STATE_ON}
    paused_unavailable = social_drafts.unavailable_platforms(
        paused_states, {}, {"x": 0}, {"x": 0}, {"x": 0}, {"x": 0})
    checks.append({"property": "a_paused_platform_is_never_drafted",
                   "states": paused_states, "unavailable": paused_unavailable})
    if "linkedin" in paused_unavailable:
        failures.append(
            "LinkedIn is paused by a recorded decision and was still treated as an "
            "outage to draft around. A pause is a choice; drafting it reverses the "
            "switch without anyone deciding to."
        )
    # A healthy platform that has merely finished its day is not an outage either.
    healthy = social_drafts.unavailable_platforms(
        {"x": social_platforms.STATE_ON}, {}, {"x": 0}, {"x": 0},
        {"x": X_DAILY_LIMIT}, {"x": X_DAILY_LIMIT})
    checks.append({"property": "a_finished_healthy_day_is_not_an_outage",
                   "unavailable": healthy})
    if healthy:
        failures.append(
            "A day that posted its full allowance successfully was reported as an "
            "outage. Drafting on top of a healthy day double-posts the same content."
        )
    # ...but a day whose whole budget went on refusals IS one.
    burned = social_drafts.unavailable_platforms(
        {"x": social_platforms.STATE_ON}, {}, {"x": 0}, {"x": 0},
        {"x": X_DAILY_LIMIT}, {"x": 0})
    checks.append({"property": "a_budget_burned_on_refusals_is_an_outage",
                   "unavailable": burned})
    if "x" not in burned:
        failures.append(
            "A day whose entire posting budget was spent on failed attempts was not "
            "treated as an outage, so the next run would draft nothing and the day "
            "would pass with no distribution at all."
        )

    # ---------------------------------------------------------------- property 7
    # The committed ledger, if present, must be readable and self-consistent -
    # a marker naming a batch that does not exist silently retires nothing.
    if LIVE_LEDGER.exists():
        live = json.loads(LIVE_LEDGER.read_text(encoding="utf-8"))
        checks.append({"property": "committed_ledger_is_consistent",
                       "batches": len(live.get("batches", [])),
                       "marked_posted_through": live.get("marked_posted_through"),
                       "open_drafts": sum(len(b["items"])
                                          for b in social_drafts.open_batches(live))})
        if social_drafts.marker_is_stale(live):
            failures.append(
                f"data/social-draft-ledger.json sets marked_posted_through to "
                f"{live.get('marked_posted_through')!r}, which matches no batch id. "
                f"Nothing has been marked done and the sheet will keep showing posts "
                f"that may already have gone out."
            )

    # Rule 0: a guard that exercised nothing must not report PASS.
    if not checks:
        print(json.dumps({
            "validator": "social_drafts_fallback", "status": "FAIL", "hard_failures": 1,
            "properties_exercised": 0,
            "detail": "Exercised zero properties; passing here would vouch for nothing.",
        }, indent=2))
        return 1

    result = {
        "validator": "social_drafts_fallback",
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
