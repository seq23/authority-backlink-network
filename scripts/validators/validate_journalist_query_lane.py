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
  the real digest     the actual 2026-09-02 SOS digest parses to every query its
  parses whole        own index declares, with each summary still bound to the
                      address it arrived with and no footer inside a question.
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
from datetime import date, timedelta
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

    # --- the REAL welcome email must not read as a broken parser -----------
    # tests/fixtures/journalist-queries/sos-welcome-2026-09-02.eml is the actual
    # message the owner received, kept verbatim but for her name and the
    # unsubscribe token. Before it was recognised, the lane read it as a digest,
    # parsed it to zero queries, and raised UNPARSEABLE_DIGEST -- a false stop
    # that would have fired every run for two days and taught its reader to
    # ignore the real one.
    report.exercised()
    welcome = (ROOT / "tests/fixtures/journalist-queries/"
                      "sos-welcome-2026-09-02.eml")
    if not welcome.exists():
        report.fail(f"the real welcome-email fixture is missing ({welcome.name}); the "
                    f"non-digest path would be proved only against invented input")
    else:
        got = drive(report, tmp, "welcome", {welcome.name: welcome.read_text(encoding="utf-8")})
        if [m["signature"] for m in got["non_digest_messages"]] != ["sos-welcome"]:
            report.fail("the real SOS welcome email is not recognised as a non-digest; "
                        "it would raise a false UNPARSEABLE_DIGEST on every run")
        if got["digests_read"] != 0:
            report.fail(
                f"a run that read only the welcome email reported "
                f"{got['digests_read']} digest(s). A message positively recognised as "
                f"NOT a digest may not be counted as one: 'digests read: 2' on a "
                f"morning with one digest is the small dishonesty that makes the big "
                f"one -- 'nothing relevant today' -- believable.")
        if got["stops"]:
            report.fail(f"the real welcome email produced stop(s) "
                        f"{[x['code'] for x in got['stops']]}; a welcome email is not a "
                        f"broken parser")
        if "NO RELEVANT QUERIES" in got["named_outcome"]:
            report.fail("a run that read only a welcome email reported 'no relevant "
                        "queries'; no query was looked at")

        # And the excuse must be narrow. A REAL digest that happens to carry
        # welcome-ish wording must still be parsed, never dismissed.
        report.exercised()
        # The subject deliberately MATCHES the welcome signature. Only the body
        # markers distinguish this real digest from the real welcome email, so
        # this is what proves recognition needs both.
        disguised = ("From: Peter Shankman <peter@sourceofsources.com>\n"
                     "Subject: Welcome to SOS! Here are today's queries\n\n"
                     + FIXTURE_DIGEST)
        got2 = drive(report, tmp, "disguised", {"d.eml": disguised})
        if got2["non_digest_messages"]:
            report.fail("a digest carrying a stray welcome phrase was dismissed as a "
                        "non-digest. Recognition must require the subject AND the body "
                        "markers, or a changed format gets excused as a welcome email.")
        if got2["queries_ingested"] < 2:
            report.fail(f"the disguised digest yielded {got2['queries_ingested']} "
                        f"queries; its blocks must still be parsed")

    # --- a short read must be named, not silently accepted -----------------
    # The publisher states 10-15 queries per digest. A digest parsing to two has
    # dropped eight nobody knows were there, which is the quiet version of the
    # failure above.
    report.exercised()
    short = drive(report, tmp, "short", {"d.eml":
        "From: Peter Shankman <peter@sourceofsources.com>\n"
        "Subject: SOS Queries\n\n" + FIXTURE_DIGEST})
    codes = {x["code"] for x in short["stops"]}
    if "PARTIAL_DIGEST_PARSE" not in codes:
        report.fail("a digest parsing to fewer queries than the declared floor did not "
                    "raise PARTIAL_DIGEST_PARSE. A partial parse drops queries silently, "
                    "which is the failure mode this repository keeps finding.")
    if short["queries_ingested"] < 2:
        report.fail("a partially parsed digest must still process the queries it DID "
                    "read; naming the gap is not a reason to discard the rest")

    # --- the same query is never surfaced twice ----------------------------
    # The mailbox is read with a lookback window, so consecutive runs see the
    # same digest.
    report.exercised()
    ids = [J.query_identity(q) for q in
           J.parse_digest("sos", FIXTURE_DIGEST, J.compile_formats(J.load(J.FORMATS)))]
    if len(ids) != len(set(ids)):
        report.fail("two different queries in one digest share an identity; one would "
                    "silently suppress the other")
    if any(not i for i in ids):
        report.fail("a query produced an empty identity, so dedupe would not hold")

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


# ---------------------------------------------------------------------------
# Property -- the grammar must parse the REAL digest, whole and unmixed.
# ---------------------------------------------------------------------------

REAL_DIGEST = ROOT / "tests/fixtures/journalist-queries/sos-digest-2026-09-02.eml"

# Labels the provider uses. Any of these appearing INSIDE a parsed value means
# the block boundaries are wrong and one query's text has run into the next.
PROVIDER_LABELS = ("SUMMARY:", "CATEGORY:", "NAME:", "EMAIL:", "MUCK RACK URL:",
                   "MEDIA OUTLET:", "MEDIA WEBSITE:", "DEADLINE DATE:",
                   "DEADLINE TIME:", "TIME ZONE:", "QUERY:")


def check_real_digest(report: Report, tmp: Path) -> None:
    """Drive the REAL 2026-09-02 SOS digest through the real scanner.

    Why this exists. Every parser property above was proved against
    FIXTURE_DIGEST, which this repository wrote. The grammar had therefore never
    met its actual input, and when the first real digest arrived on 2026-09-02 it
    parsed 2 of its 10 queries -- and paired query 1's summary with query 6's
    email address, which would have handed the owner a draft answering one
    reporter, addressed to another. PARTIAL_DIGEST_PARSE caught the shortfall and
    the run stayed green; nothing was sent, because this lane has no send path.

    A synthetic fixture cannot catch that class, because whoever writes the
    fixture writes it in the layout the grammar already expects. So the real
    message is kept, and the expected result is derived from the message ITSELF
    rather than from the grammar: the index markers the newsletter prints, and
    the summary/email pairs read straight out of the raw text.
    """
    report.exercised()
    if not REAL_DIGEST.exists():
        report.fail(
            f"the real-digest fixture is missing ({REAL_DIGEST.name}). Without it "
            f"the grammar is proved only against input this repository wrote, "
            f"which is exactly the state in which it shipped unable to read 8 of "
            f"10 real queries.")
        return

    raw = REAL_DIGEST.read_text(encoding="utf-8")
    body = raw.split("\n\n", 1)[1]

    # --- the oracle, read out of the message and not out of the grammar ----
    expected_count = len(re.findall(r"\(#item\d+\)", body))
    if expected_count < 5:
        report.fail(f"the real-digest fixture declares only {expected_count} index "
                    f"entries; it is no longer a representative digest and this "
                    f"property is not proving anything")
        return
    expected_pairs = set(re.findall(
        r"^\s*\d+\)\s*SUMMARY:\s*(.+?)\s*$.*?^\s*EMAIL:\s*(\S+)",
        body, re.M | re.S))
    expected_pairs = {(s, e.split("(")[0].strip()) for s, e in expected_pairs}

    # This property is about the PARSER, so no model is called: the drafting key
    # is withheld for the duration. That keeps the check deterministic, free, and
    # runnable with no network, which is what lets it sit in the release profile.
    saved_key = J.api_key
    J.api_key = lambda: None
    try:
        got = drive(report, tmp, "realdigest", {REAL_DIGEST.name: raw})
    finally:
        J.api_key = saved_key

    codes = {s["code"] for s in got["stops"]}
    if "UNPARSEABLE_DIGEST" in codes:
        report.fail("the real SOS digest is reported as unreadable")
    if "PARTIAL_DIGEST_PARSE" in codes:
        report.fail(
            f"the real SOS digest still parses short: {[s for s in got['stops'] if s['code'] == 'PARTIAL_DIGEST_PARSE']}. "
            f"The stop is doing its job; the grammar is not.")
    if got["non_digest_messages"]:
        report.fail("the real SOS digest was dismissed as a non-digest message")

    report.exercised()
    if got["queries_ingested"] != expected_count:
        report.fail(
            f"the real digest indexes {expected_count} queries and the parser "
            f"ingested {got['queries_ingested']}. Every missing one is a query the "
            f"owner never sees and nobody knows was there.")

    # --- and the fields must belong to the query they were read from -------
    report.exercised()
    compiled = J.compile_formats(J.load(J.FORMATS))
    parsed = J.parse_digest("sos", body, compiled)
    got_pairs = {(q.get("summary", ""), q.get("email", "")) for q in parsed}
    missing = expected_pairs - got_pairs
    if missing:
        report.fail(
            f"{len(missing)} of {len(expected_pairs)} summary/address pairs did not "
            f"survive parsing intact, e.g. {sorted(missing)[:2]}. A summary bound to "
            f"the wrong address is a draft answering one reporter and addressed to "
            f"another, which is worse than dropping the query.")

    report.exercised()
    for query in parsed:
        for field, value in query.items():
            if field == "provider":
                continue
            for label in PROVIDER_LABELS:
                if label in str(value).upper():
                    report.fail(
                        f"the parsed {field!r} of {query.get('summary', '')[:40]!r} "
                        f"contains the provider label {label!r}, so a block boundary "
                        f"is wrong and one field has swallowed the next")
                    break

    report.exercised()
    for query in parsed:
        for required in ("summary", "outlet", "deadline", "email", "query"):
            if not query.get(required):
                report.fail(
                    f"the real digest yielded a query with no {required!r} "
                    f"({query.get('summary', '(no summary)')[:60]!r}). The owner acts "
                    f"on these fields: a missing deadline or address makes a draft "
                    f"unusable without her going back to the mailbox herself.")

    # --- the footer must not be inside a reporter's question ---------------
    report.exercised()
    for query in parsed:
        text = str(query.get("query", ""))
        for junk in ("This email was sent to", "unsubscribe from this list",
                     "Back to top", "Terms of Service"):
            if junk in text:
                report.fail(f"mailing-list boilerplate ({junk!r}) was parsed as part "
                            f"of a reporter's question; it would be fed to the model "
                            f"and could end up quoted back at the reporter")


# ---------------------------------------------------------------------------
# Property -- a stop the lane cannot clear itself is NAMED, CLASSIFIED, and
# carries the right colour.
# ---------------------------------------------------------------------------

STOP_CODE_RE = re.compile(r'NamedStop\(\s*\n?\s*"([A-Z_]+)"|"code":\s*"([A-Z_]+)"')


def check_stop_taxonomy(report: Report, tmp: Path) -> int:
    """Drive the credential-rejected path and assert the whole vocabulary.

    Why this exists
    ---------------
    On 2026-09-09 the mailbox credential was rejected -- the owner had changed
    the Google account password that morning, which revokes app passwords -- and
    the lane died on an unhandled `imaplib.IMAP4.error`. Three separate things
    were wrong with that, and only the first is obvious:

      1. The lane HAD a named-stop vocabulary and did not use it. "No credential
         set" was a named stop; "credential set and refused" was a traceback.
      2. The crash killed the process before the receipt was written, so the
         workflow's reporting step read the PREVIOUS run's receipt and printed
         "NO RELEVANT QUERIES: 10 queries were read from 1 digest(s)" on a
         morning the lane had read nothing. A quiet day and a broken lane looked
         identical, which is the single failure this lane exists to prevent.
      3. The lane's existing credential check asks whether the secret is SET. A
         check on configuration cannot see a credential that is set and dead, so
         the only thing that ever exercises the credential is the run itself --
         which means the run has to report the answer honestly or nothing does.

    So this drives the real scanner against a mailbox that refuses the login and
    asserts the outcome, rather than asserting prose about it.
    """
    codes = {a or b for a, b in STOP_CODE_RE.findall(SCANNER.read_text(encoding="utf-8"))}
    codes.discard("")
    policy = J.stop_policy()

    report.exercised()
    if not codes:
        report.fail("found zero named stop codes in the scanner; this check examined "
                    "nothing and cannot vouch for the taxonomy")
    if not policy:
        report.fail("data/journalist-queries/stop_policy.json declares no stops. The "
                    "taxonomy that decides which failures are green is missing.")
    for code in sorted(codes):
        report.exercised()
        if code not in policy:
            report.fail(
                f"the scanner can raise {code} and stop_policy.json does not classify "
                f"it. An unclassified stop defaults to OUTAGE, which is the safe "
                f"reading, but nobody has said whether it is a break or a quiet day.")
        elif J.stop_class(code, policy) not in (J.CLASS_LEGITIMATE, J.CLASS_OUTAGE):
            report.fail(f"{code} has no valid class in stop_policy.json")

    # --- a rejected credential is a NAMED STOP, and it is RED ---------------
    report.exercised()
    calls: list[tuple[str, str]] = []
    saved_open, saved_imap = J.open_issue, J.imaplib
    saved = (J.RECEIPT, J.STATE, J.DIGESTS)

    class _RefusingIMAP:
        """A mailbox that answers the login exactly as Gmail did on 2026-09-09."""
        error = saved_imap.IMAP4.error

        def __init__(self, host, port):
            pass

        def login(self, user, password):
            raise saved_imap.IMAP4.error(b"[AUTHENTICATIONFAILED] Invalid credentials (Failure)")

        def logout(self):
            pass

    class _FakeImaplib:
        IMAP4 = saved_imap.IMAP4
        IMAP4_SSL = _RefusingIMAP

    secret = "s3cr3t-app-password-value"
    saved_env = {k: os.environ.get(k) for k in
                 ("SOS_IMAP_HOST", "SOS_IMAP_USER", "SOS_IMAP_PASSWORD")}
    try:
        J.open_issue = lambda title, body: (calls.append((title, body)) or (True, "stubbed"))
        J.imaplib = _FakeImaplib
        os.environ["SOS_IMAP_HOST"] = "imap.example.com"
        os.environ["SOS_IMAP_USER"] = "owner@example.com"
        os.environ["SOS_IMAP_PASSWORD"] = secret
        J.RECEIPT, J.STATE, J.DIGESTS = (tmp / "rej-r.json", tmp / "rej-s.json",
                                         tmp / "rej-d")
        # A STALE receipt is planted first. If the scanner fails to rewrite it,
        # this fixture reproduces the 2026-09-09 report exactly, and the
        # assertions below catch it.
        J.write_json(J.RECEIPT, {"schema": "journalist-query-scan-v1", "stops": [],
                                 "named_outcome": "NO RELEVANT QUERIES: yesterday",
                                 "messages_read": 1, "digests_read": 1,
                                 "queries_ingested": 10, "surfaced": 0})
        args = argparse.Namespace(inbox_dir=None, no_issue=False, model=J.DEFAULT_MODEL)
        try:
            receipt = J.run(args)
        except Exception as exc:  # noqa: BLE001 - the defect under test IS a crash
            # This is the 2026-09-09 shape restored. Reported as a named failure
            # rather than allowed to abort this validator, so the receipt says
            # WHY instead of the reader having to read a traceback about a
            # traceback.
            report.fail(
                f"a mailbox that refuses the login crashed the scan with "
                f"{type(exc).__name__}: {str(exc)[:120]}. An auth failure must be a "
                f"NAMED STOP, not an unhandled traceback: the crash kills the process "
                f"before the receipt is written, and the workflow's reporting step then "
                f"reads the PREVIOUS run's receipt and calls a blind morning a quiet day.")
            return len(codes)
        codes_seen = [s["code"] for s in receipt["stops"]]

        if "MAILBOX_CREDENTIAL_REJECTED" not in codes_seen:
            report.fail(
                f"a mailbox that refuses the login produced {codes_seen or 'no stop'} "
                f"instead of MAILBOX_CREDENTIAL_REJECTED. A credential that is set and "
                f"dead must not be reported as one that was never set, and must not be "
                f"an unhandled traceback.")
        if "NO_MAILBOX_CREDENTIAL" in codes_seen:
            report.fail("a REJECTED credential was reported as a MISSING one. Those are "
                        "different states: one is a lane waiting to be set up, the "
                        "other is a lane that has stopped working.")

        report.exercised()
        if J.stop_class("MAILBOX_CREDENTIAL_REJECTED", policy) != J.CLASS_OUTAGE:
            report.fail("MAILBOX_CREDENTIAL_REJECTED is not classed as an outage. A "
                        "credential outage that reports green is a false green over a "
                        "lane that is genuinely not reading her mail.")
        if not J.outage_stops(receipt):
            report.fail("a rejected credential produced no outage stop, so the run "
                        "would exit 0. The lane read nothing; it must stay red.")

        # --- the receipt must be TODAY's, never yesterday's -----------------
        report.exercised()
        on_disk = json.loads(J.RECEIPT.read_text(encoding="utf-8"))
        if "yesterday" in on_disk.get("named_outcome", ""):
            report.fail(
                "the stale receipt survived the failure. This is the 2026-09-09 defect "
                "exactly: the workflow's reporting step reads this file and would "
                "announce a quiet day on a morning the lane read nothing.")
        if on_disk.get("queries_ingested") or on_disk.get("digests_read"):
            report.fail(f"the receipt of a run that read nothing claims "
                        f"{on_disk.get('digests_read')} digest(s) and "
                        f"{on_disk.get('queries_ingested')} quer(ies)")

        # --- the secret is never printed ------------------------------------
        report.exercised()
        blob = json.dumps(on_disk) + json.dumps(calls)
        if secret in blob:
            report.fail("the mailbox password appears in the receipt or the issue body")
        if "owner@example.com" in blob:
            report.fail("the full mailbox address appears in the receipt or the issue "
                        "body; it is masked so the owner can identify it without the "
                        "repository publishing it")

        # --- announced ONCE, then reminded, never every run -----------------
        report.exercised()
        first = len(calls)
        if first != 1:
            report.fail(f"a fresh outage opened {first} issues; it must open exactly one")
        J.run(args)
        if len(calls) != first:
            report.fail(
                f"the same unresolved outage opened another issue on the very next run "
                f"({len(calls)} total). Two scheduled runs a weekday is ten issues a "
                f"week for one dead password, and a notification at that volume is one "
                f"that gets muted.")

        report.exercised()
        every = J.reminder_days("MAILBOX_CREDENTIAL_REJECTED", policy)
        if every <= 0:
            report.fail("MAILBOX_CREDENTIAL_REJECTED has no reminder cadence. Said once "
                        "and then never again is how an outage becomes permanent.")
        else:
            state = json.loads(J.STATE.read_text(encoding="utf-8"))
            stale = (date.today() - timedelta(days=every + 1)).isoformat()
            state["stops_announced"] = {"MAILBOX_CREDENTIAL_REJECTED": stale}
            J.write_json(J.STATE, state)
            J.run(args)
            if len(calls) != first + 1:
                report.fail(f"an outage unresolved for more than {every} days did not "
                            f"produce a reminder; it went silent instead.")
    finally:
        J.open_issue, J.imaplib = saved_open, saved_imap
        J.RECEIPT, J.STATE, J.DIGESTS = saved
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # --- a LEGITIMATE stop is green ----------------------------------------
    report.exercised()
    if J.stop_class("NO_MAILBOX_CREDENTIAL", policy) != J.CLASS_LEGITIMATE:
        report.fail("NO_MAILBOX_CREDENTIAL is not a legitimate stop. A lane waiting to "
                    "be set up is a named stop and must be GREEN, or the red means "
                    "nothing when something actually breaks.")
    if J.outage_stops({"stops": [{"code": "NO_MAILBOX_CREDENTIAL"}]}):
        report.fail("a legitimate stop was classed as an outage and would fail the run")

    return len(codes)


def main() -> int:
    report = Report()
    ledger = J.load(LANE / "expertise-ledger.json")
    beats = J.load(LANE / "beats.json")

    check_no_send_path(report)
    check_guard_alive(report, ledger, beats)
    check_ledger(report, ledger)
    drafts = check_recorded_digests(report, ledger, beats)
    stop_codes = 0
    with tempfile.TemporaryDirectory() as td:
        check_outcomes(report, Path(td))
        check_real_digest(report, Path(td))
        stop_codes = check_stop_taxonomy(report, Path(td))

    if report.properties == 0:
        report.fail("exercised zero properties; a guard that iterates an empty list "
                    "reports PASS forever and its green receipt is taken as proof")

    status = "FAIL" if report.hard else "PASS"
    print(f"JOURNALIST QUERY LANE: {status}")
    print(f"  properties exercised: {report.properties} "
          f"({len(ledger['facts'])} ledger fact(s), {drafts} recorded draft(s), "
          f"7 guard proofs, 4 outcome proofs, 6 real-digest proofs, "
          f"{stop_codes} stop code(s) classified)")
    if drafts == 0:
        print("  NAMED ZERO: no digest has been recorded yet, because ingestion is "
              "waiting on a mailbox credential. The guard was still driven through "
              "its fixtures above, so this PASS is not an empty loop.")
    for problem in report.hard:
        print(f"  HARD_FAIL {problem}")
    return 1 if report.hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
