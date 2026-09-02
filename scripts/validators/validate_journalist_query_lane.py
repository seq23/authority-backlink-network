#!/usr/bin/env python3
"""The journalist-query lane must never send, and must never invent expertise.

The two failures this exists to stop
------------------------------------
**Sending.** docs/EXTERNAL-AUTHORITY-PLAN.md Rank 1 works only because the
pitches are genuinely from Sequoia. An auto-sent pitch carrying one wrong fact
gets printed under her name; that is a correction in a real publication and a
source relationship burned permanently and silently, and the upside of
auto-sending was about thirty seconds. So there is no send path, and this
validator fails the build the day one appears -- including the day someone adds
it for a good reason, because a good reason is exactly how it would arrive.

**Inventing.** The other way this play becomes a catastrophe is a fabricated
expert. A model handed a reporter's question and asked to write as an expert
will produce a fluent, confident answer whether or not the person has any
first-hand knowledge, and the reporter has no way to tell. So a draft may only
use facts from data/journalist-queries/expertise-ledger.json, every fact must
point at evidence a stranger can open, and every number in a draft must appear
in a fact the draft cited.

What it checks
--------------
  no send path        the scanner imports no mail transport and contains no send
                      call. Its IMAP read is read-only.
  guard is alive      the real verify_draft() is driven through a clean draft and
                      six broken ones, every run.
  ledger is real      every fact's evidence path exists in this repository.
  drafts re-verify    every draft in every recorded digest is re-checked against
                      the ledger, offline. A draft edited by hand fails here.
  nothing was sent    every recorded digest is marked sent:false.
  a quiet day is quiet an empty inbox surfaces nothing, writes no digest, and
                      still says what it did.
  a broken parser is  a digest the parser cannot read is reported as
  not a quiet day     UNPARSEABLE_DIGEST, never as "no relevant queries".
  exclusions bite     a query matching a hard exclusion never reaches a model.

Hard-fails if it exercises zero properties.

    python3 scripts/validators/validate_journalist_query_lane.py
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import journalist_query_scan as J  # noqa: E402

LANE = ROOT / "data/journalist-queries"
SCANNER = ROOT / "scripts/journalist_query_scan.py"

# Anything that could put a message in front of a journalist. Checked against the
# scanner's source, with its own docstring removed so the prose explaining why
# there is no send path does not satisfy the search for one.
SEND_TOKENS = [
    r"\bsmtplib\b", r"\bSMTP\b", r"\bsendmail\b", r"\bsend_message\s*\(",
    r"\bmailgun\b", r"\bsendgrid\b", r"\bpostmark\b", r"\bses\.send", r"\bboto3\b",
    r"\bresend\b", r"\bmailersend\b", r"\bIMAP4?_?SSL\([^)]*\)\.store",
    r'"MAIL FROM"', r"\bsmtp\.", r"\bmail\.send\b",
]


class Report:
    def __init__(self) -> None:
        self.hard: list[str] = []
        self.properties = 0

    def fail(self, message: str) -> None:
        self.hard.append(message)

    def exercised(self) -> None:
        self.properties += 1


# ---------------------------------------------------------------------------
# Property 1 -- there is no send path.
# ---------------------------------------------------------------------------

def check_no_send_path(report: Report) -> None:
    report.exercised()
    source = SCANNER.read_text(encoding="utf-8")
    # Drop the module docstring: it explains at length why there is no send path,
    # and would otherwise match on its own explanation.
    body = source.split('"""', 2)[-1] if source.count('"""') >= 2 else source
    for token in SEND_TOKENS:
        m = re.search(token, body)
        if m:
            report.fail(f"the scanner contains a mail-sending construct ({m.group(0)!r}). "
                        f"This lane drafts for the owner and never sends to a journalist; "
                        f"if a send is genuinely wanted, that is a decision for the owner "
                        f"and not a change to this file.")

    report.exercised()
    if "readonly=True" not in body:
        report.fail("the IMAP read is not opened readonly=True; a lane that reads a "
                    "mailbox must not be able to modify it")
    for mutation in ("conn.store", "conn.copy", "conn.expunge", '"\\\\Deleted"'):
        if mutation in body:
            report.fail(f"the scanner mutates the mailbox ({mutation}); ingestion is "
                        f"read-only")

    report.exercised()
    # The digest reaches the owner through GitHub, which is not a journalist-facing
    # channel. If that ever changes to a direct address, it must be a deliberate
    # decision and not a quiet edit.
    if "gh" not in body or "issue" not in body:
        report.fail("the scanner no longer surfaces the digest through a GitHub issue; "
                    "whatever replaced it must be re-reasoned about, because the "
                    "notification channel is the thing that must not reach a journalist")


# ---------------------------------------------------------------------------
# Property 2 -- the grounding guard is alive, proved negatively, every run.
# ---------------------------------------------------------------------------

def check_guard_alive(report: Report, ledger: dict, beats: dict) -> None:
    fact = ledger["facts"][0]
    clean = {
        "answerable": True,
        "facts_used": [fact["id"]],
        "draft": (f"{fact['claim']} "
                  "I own Memphis Vendor Library and publish the method, so treat me "
                  "as an interested party."),
    }
    report.exercised()
    problems = J.verify_draft(clean, ledger, beats)
    if problems:
        report.fail(f"the guard rejects a draft built entirely from one ledger fact, so "
                    f"it would reject real work: {problems}")

    def must_reject(name: str, mutate) -> None:
        report.exercised()
        broken = copy.deepcopy(clean)
        mutate(broken)
        if not J.verify_draft(broken, ledger, beats):
            report.fail(f"the guard ACCEPTED a broken draft ({name}); the load-bearing "
                        f"check on this lane is not working")

    must_reject("a number that appears in no cited fact",
                lambda d: d.__setitem__("draft", d["draft"] + " We surveyed 412 vendors."))
    must_reject("a fact id that does not exist",
                lambda d: d.__setitem__("facts_used", ["a-fact-nobody-wrote"]))
    must_reject("no cited facts at all",
                lambda d: d.__setitem__("facts_used", []))
    must_reject("an unevidenced credential claim",
                lambda d: d.__setitem__(
                    "draft", d["draft"] + " I am a leading expert in this field."))
    must_reject("no disclosure of who she is and what she owns",
                lambda d: d.__setitem__("draft", fact["claim"]))
    must_reject("a draft over the word limit",
                lambda d: d.__setitem__(
                    "draft", d["draft"] + " word" * (int(beats["max_draft_words"]) + 10)))


# ---------------------------------------------------------------------------
# Property 3 -- the ledger points at evidence that exists.
# ---------------------------------------------------------------------------

def check_ledger(report: Report, ledger: dict) -> None:
    if not ledger.get("facts"):
        report.fail("the expertise ledger is empty; every draft would be ungrounded")
    seen: set[str] = set()
    for fact in ledger["facts"]:
        report.exercised()
        for field in ("id", "claim", "evidence", "public_url", "why_it_is_answerable"):
            if not fact.get(field):
                report.fail(f"ledger fact {fact.get('id', '?')}: missing {field!r}")
        if fact["id"] in seen:
            report.fail(f"duplicate ledger fact id {fact['id']!r}")
        seen.add(fact["id"])
        evidence = ROOT / fact["evidence"]
        if not evidence.exists():
            report.fail(f"ledger fact {fact['id']}: its evidence does not exist "
                        f"({fact['evidence']}). A claim a stranger cannot check is not "
                        f"a fact this lane may pitch.")
        # Every number stated in a claim must be declared, so the draft guard has
        # something to check against rather than re-deriving it from prose.
        for number in J.NUMBER_RE.findall(fact["claim"]):
            if number not in fact.get("numbers", []) and number not in fact["public_url"]:
                report.fail(f"ledger fact {fact['id']}: states {number!r} but does not "
                            f"declare it in `numbers`, so a draft quoting it would be "
                            f"rejected as ungrounded")


# ---------------------------------------------------------------------------
# Property 4 -- every draft ever recorded still verifies, and none was sent.
# ---------------------------------------------------------------------------

def check_recorded_digests(report: Report, ledger: dict, beats: dict) -> int:
    digests = sorted((LANE / "digests").glob("*.json"))
    drafts = 0
    for path in digests:
        report.exercised()
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("sent") is not False:
            report.fail(f"{path.relative_to(ROOT)}: 'sent' is not false. This lane does "
                        f"not send, so a digest claiming otherwise is either wrong or "
                        f"records something that must not have happened.")
        for item in doc.get("items", []):
            drafts += 1
            report.exercised()
            problems = J.verify_draft(
                {"facts_used": item.get("facts_used", []), "draft": item.get("draft", "")},
                ledger, beats)
            if problems:
                report.fail(f"{path.relative_to(ROOT)}: a recorded draft no longer "
                            f"verifies against the ledger: {problems}")
    return drafts


# ---------------------------------------------------------------------------
# Property 5 -- a quiet day, and a broken parser, must not look the same.
# ---------------------------------------------------------------------------

FIXTURE_DIGEST = """\
------------------------------------------
1) Summary: What does a wedding cost in a mid-size city?
Email: query-1@sourceofsources.com
Media Outlet: A Newspaper
Deadline: 5:00 PM CST - 8 September
Query: I want someone who has collected local Memphis wedding vendor prices and can say where national averages go wrong.
------------------------------------------
2) Summary: Which immigration attorney handles a green card denial?
Email: query-2@sourceofsources.com
Media Outlet: Freelance
Query: Seeking immigration attorneys on removal proceedings.
------------------------------------------
"""

UNPARSEABLE_DIGEST = (
    "Good morning. Here are today's opportunities.\n\n"
    + ("A reporter at a large publication is looking for sources on a subject. "
       "Reply if this is you. " * 12))


def drive(report: Report, tmp: Path, name: str, files: dict[str, str]) -> dict:
    """Run the REAL scanner against a fixture inbox, with its outputs redirected."""
    inbox = tmp / name
    inbox.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (inbox / filename).write_text(content, encoding="utf-8")

    saved = (J.RECEIPT, J.STATE, J.DIGESTS)
    J.RECEIPT = tmp / f"{name}-receipt.json"
    J.STATE = tmp / f"{name}-state.json"
    J.DIGESTS = tmp / f"{name}-digests"
    try:
        return J.run(argparse.Namespace(
            inbox_dir=str(inbox), no_issue=True, model=J.DEFAULT_MODEL))
    finally:
        J.RECEIPT, J.STATE, J.DIGESTS = saved


def check_outcomes(report: Report, tmp: Path) -> None:
    # --- a quiet day -------------------------------------------------------
    report.exercised()
    quiet = drive(report, tmp, "quiet", {})
    if quiet["surfaced"] != 0:
        report.fail("an empty inbox surfaced something")
    if list((tmp / "quiet-digests").glob("*.json")) if (tmp / "quiet-digests").exists() else False:
        report.fail("an empty inbox wrote a digest file; a quiet day sends nothing")
    if not quiet["named_outcome"]:
        report.fail("a quiet day produced no named outcome. Rule 0: no run may exit 0 "
                    "having done nothing without saying so.")

    # --- the credential stop must actually reach the owner ------------------
    # This is the one that shipped broken. announce_stops() sat at the tail of
    # run(), and the NO_MAILBOX_CREDENTIAL path returns from the MIDDLE of
    # run() -- so the code that announces the credential stop was unreachable
    # from the credential stop, and two CI runs printed a perfect named stop
    # into a log nobody reads and opened nothing. Driven here rather than
    # inspected, with the issue call stubbed and counted.
    report.exercised()
    calls: list[tuple[str, str]] = []
    saved_open = J.open_issue
    J.open_issue = lambda title, body: (calls.append((title, body)) or (True, "stubbed"))
    # The REAL imap_messages is used, with its credentials removed from the
    # environment. A stub would have proved only that the harness raises what
    # the harness raises; this proves the message the owner actually receives
    # names the stop and the secrets she has to set.
    saved_env = {k: os.environ.pop(k, None) for k in
                 ("SOS_IMAP_HOST", "SOS_IMAP_USER", "SOS_IMAP_PASSWORD")}
    try:
        inbox = tmp / "cred"
        inbox.mkdir(parents=True, exist_ok=True)
        saved = (J.RECEIPT, J.STATE, J.DIGESTS)
        J.RECEIPT, J.STATE, J.DIGESTS = (tmp / "cred-r.json", tmp / "cred-s.json",
                                         tmp / "cred-d")
        try:
            first = J.run(argparse.Namespace(inbox_dir=None, no_issue=False,
                                             model=J.DEFAULT_MODEL))
            second = J.run(argparse.Namespace(inbox_dir=None, no_issue=False,
                                              model=J.DEFAULT_MODEL))
        finally:
            J.RECEIPT, J.STATE, J.DIGESTS = saved
    finally:
        J.open_issue = saved_open
        for key, value in saved_env.items():
            if value is not None:
                os.environ[key] = value

    if len(calls) != 1:
        report.fail(
            f"a run that could not read the mailbox opened {len(calls)} issue(s); it "
            f"must open exactly one across two runs. Zero means the owner is never "
            f"told what to set and the lane waits forever on a log line. More than "
            f"one means a standing daily instruction, which this repository has "
            f"already established nobody follows.")
    elif "NO_MAILBOX_CREDENTIAL" not in calls[0][1] or "SOS_IMAP" not in calls[0][1]:
        report.fail("the issue that tells the owner what to set does not name the "
                    "stop and the secrets; a notification that does not say what to "
                    "do is not a notification")
    report.exercised()
    if first.get("announced", {}).get("ok") is not True:
        report.fail("the run receipt does not record that the owner was told. A "
                    "notification lane that fails silently is indistinguishable from "
                    "one that had nothing to say.")
    if "NO RELEVANT" in second["named_outcome"]:
        report.fail("a run that could not read the mailbox reported 'no relevant "
                    "queries'; nothing was looked at")

    # --- a digest the parser cannot read -----------------------------------
    report.exercised()
    broken = drive(report, tmp, "broken", {"digest.txt": UNPARSEABLE_DIGEST})
    codes = {s["code"] for s in broken["stops"]}
    if "UNPARSEABLE_DIGEST" not in codes:
        report.fail("a digest full of text that the parser could not read did NOT "
                    "produce UNPARSEABLE_DIGEST. This is the failure that makes a "
                    "broken parser indistinguishable from a quiet day, and it is the "
                    "reason a lane like this goes silently dead.")
    if "NO RELEVANT QUERIES" in broken["named_outcome"]:
        report.fail("an unreadable digest was reported as 'no relevant queries'")

    # --- the parser and the exclusions, on a real-shaped digest ------------
    report.exercised()
    compiled = J.compile_formats(J.load(J.FORMATS))
    parsed = J.parse_digest("sos", FIXTURE_DIGEST, compiled)
    if len(parsed) < 2:
        report.fail(f"the parser found {len(parsed)} queries in a two-query digest in "
                    f"the layout data/journalist-queries/query-formats.json declares; "
                    f"the grammar and the parser disagree")
    beats = J.load(J.BEATS)
    report.exercised()
    for query in parsed:
        beat, why = J.beat_for(query, beats)
        summary = query.get("summary", "").lower()
        if "attorney" in summary and beat is not None:
            report.fail("a query asking for immigration attorneys passed the beat "
                        "filter; hard exclusions must drop a query before any model "
                        "is asked anything about it")
        if "wedding cost" in summary and beat != "memphis-events":
            report.fail(f"a Memphis wedding-cost query was filed under {beat!r} rather "
                        f"than the memphis-events beat")


def main() -> int:
    report = Report()
    ledger = J.load(LANE / "expertise-ledger.json")
    beats = J.load(LANE / "beats.json")

    check_no_send_path(report)
    check_guard_alive(report, ledger, beats)
    check_ledger(report, ledger)
    drafts = check_recorded_digests(report, ledger, beats)
    with tempfile.TemporaryDirectory() as td:
        check_outcomes(report, Path(td))

    if report.properties == 0:
        report.fail("exercised zero properties; a guard that iterates an empty list "
                    "reports PASS forever and its green receipt is taken as proof")

    status = "FAIL" if report.hard else "PASS"
    print(f"JOURNALIST QUERY LANE: {status}")
    print(f"  properties exercised: {report.properties} "
          f"({len(ledger['facts'])} ledger fact(s), {drafts} recorded draft(s), "
          f"7 guard proofs, 4 outcome proofs)")
    if drafts == 0:
        print("  NAMED ZERO: no digest has been recorded yet, because ingestion is "
              "waiting on a mailbox credential. The guard was still driven through "
              "its fixtures above, so this PASS is not an empty loop.")
    for problem in report.hard:
        print(f"  HARD_FAIL {problem}")
    return 1 if report.hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
