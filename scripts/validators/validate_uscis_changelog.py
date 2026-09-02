#!/usr/bin/env python3
"""No published changelog entry may claim anything the stored diff does not support.

The failure this exists to stop
-------------------------------
This lane publishes a dated record of what changed on USCIS pages, and a language
model writes the prose. Two different things can put an unsupported sentence on
that page, and only one of them is the model:

  the model      produces a fluent, plausible sentence about a fee or an edition
                 date that was never in the diff. `scripts/uscis_changelog.py`
                 catches that at write time.

  a person       opens data/uscis-changelog/entries.json or the HTML and improves
                 a headline, tidies a quote's punctuation, or adds an entry by
                 hand. Nothing at write time ever sees that, because no run
                 happened.

The second is the one this file exists for. It re-derives the check from scratch,
offline, against the evidence stored with each entry, so a hand edit fails
exactly the way a hallucination does. On YMYL material about filing fees, a
sentence nobody can trace to a government page is a harmful sentence regardless
of who typed it.

What it checks
--------------
  guard is alive       the real verify() from the run script is driven through a
                       clean synthetic entry and five broken ones. This runs on
                       every invocation, including weeks with no entries, so a
                       green receipt is never just an empty loop.
  entries verify       every quote in every published entry must appear verbatim
                       in that entry's own stored added/removed lines.
  entries are on-page  every entry, its quotes, its agency URL and its checked
                       date must actually appear in the published HTML. An entry
                       that exists only in the data file is not published.
  no advice            no entry may cross the publication's advice boundary.
  sources are real     every tracked source is registered and verified in
                       data/external-sources.json.
  snapshots are intact each snapshot's stored sha256 must match its stored lines.
  staleness is honest  a source with no successful check may not be presented on
                       the page as current, and the page must name every tracked
                       source.

Hard-fails if it examines zero items. A guard that iterates an empty list reports
PASS forever, and the green receipt is then taken as proof of the thing it never
looked at.

    python3 scripts/validators/validate_uscis_changelog.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import uscis_changelog as U  # noqa: E402

LANE = ROOT / "data/uscis-changelog"
TRACKED = LANE / "tracked-sources.json"
ENTRIES = LANE / "entries.json"
STATE = LANE / "state.json"
SNAPSHOTS = LANE / "snapshots"
PAGE = ROOT / "sites/professional-resources/uscis-form-and-fee-changelog.html"
EXTERNAL = ROOT / "data/external-sources.json"
VERIFICATION = ROOT / "reports/external-source-verification.json"


class Report:
    def __init__(self) -> None:
        self.hard: list[str] = []
        self.items = 0

    def fail(self, message: str) -> None:
        self.hard.append(message)

    def examined(self, n: int = 1) -> None:
        self.items += n


# ---------------------------------------------------------------------------
# Property 1 -- the guard is alive, proved negatively, every run.
# ---------------------------------------------------------------------------

FIXTURE_BEFORE = [
    "Update to Form I-864EZ, Affidavit of Support Under Section 213A of the INA. New Edition Dated 08/24/26.",
    "Forms updates are posted on this page as they take effect.",
    "USCIS will accept the prior edition of this form until further notice.",
]
FIXTURE_AFTER = [
    "Update to Form I-130, Petition for Alien Relative. New Edition Dated 11/02/26.",
    "Forms updates are posted on this page as they take effect.",
    "USCIS will accept the prior edition of this form until further notice.",
]

CLEAN_ENTRY = {
    "headline": "I-864EZ edition listing replaced by an I-130 edition listing",
    "summary": ("The page previously listed an update to Form I-864EZ with a new edition "
                "dated 08/24/26. It now lists an update to Form I-130 with a new edition "
                "dated 11/02/26."),
    "quotes": [
        {"side": "removed",
         "text": "Update to Form I-864EZ, Affidavit of Support Under Section 213A of the INA. New Edition Dated 08/24/26."},
        {"side": "added",
         "text": "Update to Form I-130, Petition for Alien Relative. New Edition Dated 11/02/26."},
    ],
}


def prove_guard(report: Report) -> None:
    d = U.diff_lines(FIXTURE_BEFORE, FIXTURE_AFTER)
    report.examined()
    if not d["added"] or not d["removed"]:
        report.fail("the fixture diff produced no added or removed lines, so the "
                    "negative proofs below would prove nothing")
        return

    problems = U.verify(CLEAN_ENTRY, d, FIXTURE_AFTER, FIXTURE_BEFORE)
    report.examined()
    if problems:
        report.fail(f"the guard rejects an entry that is fully supported by its diff, "
                    f"so it would reject real work: {problems}")

    def must_reject(name: str, mutate) -> None:
        broken = copy.deepcopy(CLEAN_ENTRY)
        mutate(broken)
        report.examined()
        if not U.verify(broken, d, FIXTURE_AFTER, FIXTURE_BEFORE):
            report.fail(f"the guard ACCEPTED a broken entry ({name}); the load-bearing "
                        f"check on this lane is not working")

    # Each of these is a real way an unsupported claim reaches the page.
    must_reject("a quote edited so a date no longer matches the source",
                lambda e: e["quotes"].__setitem__(
                    1, {"side": "added",
                        "text": "Update to Form I-130, Petition for Alien Relative. New Edition Dated 12/31/26."}))
    must_reject("a claim invented wholesale",
                lambda e: e.__setitem__("quotes", [{
                    "side": "added",
                    "text": "USCIS raised the Form I-130 filing fee to $875 effective January 2027."}]))
    must_reject("prose that tells a reader what to do",
                lambda e: e.__setitem__(
                    "summary", "You should file the 11/02/26 edition of your petition "
                               "before the prior edition stops being accepted."))
    must_reject("an entry with no quoted source text at all",
                lambda e: e.__setitem__("quotes", []))
    must_reject("a quote attributed to the wrong side of the diff",
                lambda e: e["quotes"][0].__setitem__("side", "added"))


# ---------------------------------------------------------------------------
# Property 2 -- every published entry, against its own stored evidence.
# ---------------------------------------------------------------------------

def check_entries(report: Report, entries: list[dict], page: str) -> None:
    seen_ids: set[str] = set()
    for entry in entries:
        report.examined()
        eid = entry.get("id", "<no id>")
        if eid in seen_ids:
            report.fail(f"duplicate entry id {eid!r}")
        seen_ids.add(eid)

        for field in ("date_observed", "checked_at", "source_url", "source_title",
                      "publisher", "headline", "summary", "quotes", "evidence"):
            if not entry.get(field):
                report.fail(f"entry {eid}: missing required field {field!r}")
        if "evidence" not in entry or "quotes" not in entry:
            continue

        evidence = entry["evidence"]
        stored = {"added": evidence.get("added", []),
                  "removed": evidence.get("removed", [])}
        after = list(stored["added"])
        before = list(stored["removed"])

        # The same verify() the run script uses, applied to the STORED diff with
        # no network call. A hand-edited entry fails here identically.
        problems = U.verify(entry, stored, after, before)
        if problems:
            for problem in problems:
                report.fail(f"entry {eid}: {problem}")

        # And the entry must actually be on the page, with its evidence intact.
        import html as html_mod
        if eid not in page:
            report.fail(f"entry {eid}: published in entries.json but absent from "
                        f"{PAGE.relative_to(ROOT)}")
            continue
        for quote in entry["quotes"]:
            report.examined()
            if html_mod.escape(quote["text"], quote=True) not in page:
                report.fail(f"entry {eid}: quoted line is not on the published page: "
                            f"{quote['text'][:80]!r}")
        if entry["source_url"] not in page:
            report.fail(f"entry {eid}: the agency URL it cites is not linked on the "
                        f"published page: {entry['source_url']}")
        if entry["checked_at"][:10] not in page:
            report.fail(f"entry {eid}: the date it was checked "
                        f"({entry['checked_at'][:10]}) is not on the published page")


# ---------------------------------------------------------------------------
# Property 3 -- sources, snapshots and staleness.
# ---------------------------------------------------------------------------

def check_sources(report: Report, tracked: dict, state: dict, page: str) -> None:
    registry = {s["url"].rstrip("/"): s for s in
                json.loads(EXTERNAL.read_text(encoding="utf-8"))["sources"]}
    receipts = {r["url"].rstrip("/"): r for r in
                json.loads(VERIFICATION.read_text(encoding="utf-8"))["receipts"]}

    if not tracked.get("sources"):
        report.fail("tracked-sources.json declares zero sources; the lane watches nothing")

    for source in tracked["sources"]:
        report.examined()
        url = source["url"].rstrip("/")
        if url not in registry:
            report.fail(f"tracked source {source['id']}: not registered in "
                        f"data/external-sources.json ({source['url']})")
        receipt = receipts.get(url)
        if not receipt or receipt.get("http_status") != 200:
            report.fail(f"tracked source {source['id']}: no HTTP 200 verification "
                        f"receipt in reports/external-source-verification.json")
        if source["url"] not in page:
            report.fail(f"tracked source {source['id']}: not named on the published "
                        f"page, so a reader cannot see what is being watched")

        snapshot = SNAPSHOTS / f"{source['id']}.json"
        st = state.get("sources", {}).get(source["id"], {})
        if not snapshot.exists():
            # Legitimate before the first run. It is only a failure if the state
            # file claims a successful check, because then something captured a
            # page and threw the copy away.
            if st.get("last_success"):
                report.fail(f"tracked source {source['id']}: state.json records a "
                            f"successful check but no snapshot was stored, so nothing "
                            f"can be diffed against")
            continue

        report.examined()
        snap = json.loads(snapshot.read_text(encoding="utf-8"))
        recomputed = hashlib.sha256("\n".join(snap["lines"]).encode("utf-8")).hexdigest()
        if recomputed != snap["sha256"]:
            report.fail(f"snapshot {source['id']}: stored sha256 does not match its "
                        f"stored lines; the snapshot has been altered outside a run")
        if len(snap["lines"]) < 20:
            report.fail(f"snapshot {source['id']}: only {len(snap['lines'])} lines "
                        f"stored; a page that thin is a failed fetch recorded as a "
                        f"baseline")

        # Staleness must be honest on the page, not only in a CI receipt.
        if not st.get("last_success") and "not yet checked" not in page:
            report.fail(f"tracked source {source['id']}: has never been successfully "
                        f"reached, but the published page does not say so anywhere")


def main() -> int:
    report = Report()

    tracked = json.loads(TRACKED.read_text(encoding="utf-8"))
    entries = (json.loads(ENTRIES.read_text(encoding="utf-8")).get("entries", [])
               if ENTRIES.exists() else [])
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"sources": {}}

    if not PAGE.exists():
        print("USCIS CHANGELOG: FAIL")
        print(f"  HARD_FAIL the changelog page does not exist: {PAGE.relative_to(ROOT)}")
        return 1
    page = PAGE.read_text(encoding="utf-8")

    prove_guard(report)
    check_entries(report, entries, page)
    check_sources(report, tracked, state, page)

    # Rule 0. Zero items examined is a failure, not a pass.
    if report.items == 0:
        report.fail("examined zero items; a guard that iterates an empty list reports "
                    "PASS forever and its green receipt is taken as proof")

    status = "FAIL" if report.hard else "PASS"
    print(f"USCIS CHANGELOG: {status}")
    print(f"  items examined: {report.items} "
          f"({len(entries)} published entr{'y' if len(entries) == 1 else 'ies'}, "
          f"{len(tracked['sources'])} tracked source(s), 6 guard proofs)")
    if not entries:
        print("  NAMED ZERO: no change has been recorded yet. The guard was still "
              "driven through its fixtures above, so this PASS is not an empty loop.")
    for problem in report.hard:
        print(f"  HARD_FAIL {problem}")
    return 1 if report.hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
