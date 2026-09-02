#!/usr/bin/env python3
"""Render the USCIS form and fee changelog from its entries and its run state.

The page is derived, never hand-written, for the same reason the Memphis pricing
page is: the only thing that makes a changelog worth citing is that every entry
is a real observation, and a hand-editable page is one where an entry can be
improved into a fabrication and nothing notices.

Everything on the page comes from three files that a run writes:

    data/uscis-changelog/tracked-sources.json   what is watched, and why this lane
    data/uscis-changelog/entries.json           the entries, each with its quotes
                                                and the stored diff they came from
    data/uscis-changelog/state.json             when each source was last actually
                                                reached

That third file is the one people forget, and it is the difference between a
changelog and a liability. A reader has to be able to see that a source has not
been reachable for three weeks; otherwise an empty log reads as "nothing has
changed" when it actually means "we stopped looking". So the per-source
last-verified table is published on the page, above the entries, with a stale
source marked stale in the reader's face rather than in a CI receipt.

`scripts/validators/validate_uscis_changelog.py` then re-derives the entry
evidence independently and fails if any published quote is absent from the
stored diff.

    python3 scripts/build_uscis_changelog_page.py --write
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT / "data/uscis-changelog"
TRACKED = LANE / "tracked-sources.json"
ENTRIES = LANE / "entries.json"
STATE = LANE / "state.json"

PUBLICATIONS = {p["id"]: p for p in json.loads(
    (ROOT / "data/publications.json").read_text(encoding="utf-8"))}
SOURCES_BY_URL = {s["url"].rstrip("/"): s for s in json.loads(
    (ROOT / "data/external-sources.json").read_text(encoding="utf-8"))["sources"]}

SLUG = "uscis-form-and-fee-changelog.html"
CANONICAL_PATH = "/uscis-form-and-fee-changelog"

DISCLAIMER = ("This page is informational. It is not legal, medical, mental-health, "
              "immigration, financial, or professional advice.")

# A source not reached in this many days is shown to the reader as stale.
STALE_AFTER_DAYS = 14

HEADER_RE = re.compile(r"<header>.*?</header>", re.S | re.I)
FOOTER_RE = re.compile(r"<footer>.*?</footer>", re.S | re.I)
CLARITY_RE = re.compile(r"<script data-clarity-loader>.*?</script>", re.S | re.I)


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def chrome(lane: str) -> tuple[str, str, str]:
    index = (ROOT / PUBLICATIONS[lane]["folder"] / "index.html").read_text(encoding="utf-8")
    header, footer = HEADER_RE.search(index), FOOTER_RE.search(index)
    clarity = CLARITY_RE.search(index)
    if not header or not footer:
        raise SystemExit(f"cannot read chrome from {lane} index.html")
    return header.group(0), footer.group(0), (clarity.group(0) if clarity else "")


def days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        when = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).days


def build_page(tracked: dict, entries: list[dict], state: dict) -> str:
    lane = tracked["lane"]
    pub = PUBLICATIONS[lane]
    domain = pub["working_domain"]
    url = f"https://{domain}{CANONICAL_PATH}"
    header, footer, clarity = chrome(lane)

    title = "USCIS Form and Fee Changelog"
    description = (
        "A dated record of what changed on the USCIS filing-fee and form-edition "
        "pages, and when. Every entry quotes the agency's own text, links the page "
        "it was read from, and carries the date it was checked.")

    # ---------------------------------------------------------------- sources
    source_rows = []
    stale_ids = []
    for source in tracked["sources"]:
        st = state.get("sources", {}).get(source["id"], {})
        age = days_since(st.get("last_success"))
        if age is None:
            status, note = "not yet checked", "This source has no successful check on record."
        elif age > STALE_AFTER_DAYS:
            status, note = "STALE", (f"Last reached {age} days ago. Nothing below should be "
                                     f"read as evidence that this page has not changed since.")
            stale_ids.append(source["id"])
        else:
            status, note = "current", ""
        source_rows.append(
            f'<tr><td><a href="{esc(source["url"])}" data-source="external-authority" '
            f'rel="noopener">{esc(source["title"])}</a></td>'
            f'<td>{esc(source["watching"])}</td>'
            f'<td>{esc(st.get("last_success", "") or "never")[:10]}</td>'
            f'<td>{esc(status)}{(" &mdash; " + esc(note)) if note else ""}</td></tr>')

    # ---------------------------------------------------------------- entries
    if entries:
        entry_blocks = []
        for e in entries:
            quotes = "".join(
                f'<blockquote class="note"><p>{esc(q["text"])}</p>'
                f'<footer>{"Added to" if q["side"] == "added" else "Removed from"} '
                f'{esc(e["source_title"])}, observed {esc(e["date_observed"])}</footer>'
                '</blockquote>' for q in e["quotes"])
            entry_blocks.append(
                f'<article class="card" id="{esc(e["id"])}">'
                f'<h3>{esc(e["date_observed"])} &mdash; {esc(e["headline"])}</h3>'
                f'<p>{esc(e["summary"])}</p>'
                f'<p><strong>What the agency page says, verbatim:</strong></p>{quotes}'
                f'<p class="note"><strong>Primary source:</strong> '
                f'<a href="{esc(e["source_url"])}" data-source="external-authority" '
                f'rel="noopener">{esc(e["publisher"])}: {esc(e["source_title"])}</a><br>'
                f'<strong>Date checked:</strong> {esc(e["checked_at"][:10])}<br>'
                f'<strong>Compared against the copy captured:</strong> '
                f'{esc(e["evidence"]["previous_captured"][:10])}</p>'
                '</article>')
        entries_html = ("<section><h2>Changes, newest first</h2>"
                        + "".join(entry_blocks) + "</section>")
    else:
        entries_html = (
            '<section><h2>Changes, newest first</h2>'
            '<div class="info-panel"><p><strong>No change has been recorded yet.</strong> '
            'The pages above are being watched from the baseline copies captured on the '
            'dates in the table, and an entry appears here the first week one of them '
            'moves. An empty log here means "watched, nothing moved" only for the '
            'sources the table above marks current &mdash; which is why that table is '
            'published above this one rather than in a footnote.</p></div></section>')

    # ------------------------------------------------------------------- FAQ
    faqs = [
        ("What is on this page?",
         "A dated record of differences between successive copies of the USCIS pages "
         "listed above. Each entry names what moved, quotes the agency's own words "
         "verbatim, links the page the words are printed on, and gives the date the "
         "page was read."),
        ("Why does this exist when USCIS publishes the forms itself?",
         "Because an agency publishes what is true now. USCIS does not publish a "
         "readable record of what its fee schedule and form editions said last month, "
         "so there is no citable answer to \"when did this change\". This page is that "
         "record, built only from the agency's own pages."),
        ("How is an entry checked?",
         "Every quoted line must appear, character for character, in the copy of the "
         "page that was fetched, and in the difference between that copy and the "
         "previous one. An entry whose quote does not verify is discarded rather than "
         "published, and a validator re-checks every published entry against the stored "
         "difference without refetching, so an entry edited by hand fails the same way."),
        ("Does this tell me what to do about a change?",
         "No, and deliberately. This publication reports what a government page says "
         "and when it changed. It does not interpret a rule, does not say which edition "
         "to file, and is not a substitute for the agency or for a licensed "
         "practitioner."),
        ("How would I know if this page had gone stale?",
         "The table above gives the date each source was last successfully reached. A "
         "source that has not been reached in "
         f"{STALE_AFTER_DAYS} days is marked STALE there. A source that cannot be "
         "fetched is never recorded as unchanged."),
        ("Can I cite this?",
         "Yes. Cite the entry's date and the agency URL it names. The entry is a "
         "record of an observation on a date, not an interpretation, and it is "
         "published so it can be checked."),
    ]

    dataset_ld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": title,
        "description": description,
        "url": url,
        "identifier": url,
        "inLanguage": "en",
        "isAccessibleForFree": True,
        "datePublished": entries[-1]["date_observed"] if entries else date.today().isoformat(),
        "dateModified": entries[0]["date_observed"] if entries else date.today().isoformat(),
        "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
        "creator": {"@type": "Organization",
                    "name": "Professional Resource Library Editorial Desk",
                    "url": f"https://{domain}/masthead"},
        "publisher": {"@type": "Organization", "name": pub["title"],
                      "url": f"https://{domain}"},
        "measurementTechnique": (
            "Each tracked page is fetched on a weekly schedule, reduced to its visible "
            "text, and compared line by line against the previously stored copy. A "
            "difference produces an entry whose every quoted line is verified to be "
            "present verbatim in the fetched page. A page that cannot be fetched is "
            "recorded as unreachable and never as unchanged."),
        "variableMeasured": ["form edition date", "filing fee", "form availability"],
        "temporalCoverage": (f'{entries[-1]["date_observed"]}/..' if entries
                             else f"{date.today().isoformat()}/.."),
        "citation": [
            {"@type": "CreativeWork",
             "name": SOURCES_BY_URL[s["url"].rstrip("/")]["title"],
             "url": s["url"],
             "publisher": {"@type": "Organization", "name": s["publisher"]}}
            for s in tracked["sources"] if s["url"].rstrip("/") in SOURCES_BY_URL],
    }
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q,
                              "acceptedAnswer": {"@type": "Answer", "text": a}}
                             for q, a in faqs]}

    parts: list[str] = []

    parts.append(
        '<section class="card"><div class="info-panel recommendation-summary" '
        'data-content-block="recommendation_summary" id="recommendation-summary">'
        '<h2>What this page recommends</h2>'
        '<p class="recommendation-summary__answer">Check the date next to a change '
        'before relying on it, and open the agency link in the entry rather than this '
        'page: this is a record of what USCIS published and when, and USCIS is the only '
        'authority on what is required today.</p></div>'
        '<h2>Method</h2>'
        f'<p><strong>What is watched:</strong> {esc(tracked["subject"])}, on the '
        f'{len(tracked["sources"])} USCIS pages listed below and nothing else.</p>'
        '<p><strong>How:</strong> each page is fetched on a weekly schedule and reduced '
        'to its visible text. That text is compared line by line against the copy '
        'stored from the previous check. A material difference becomes an entry.</p>'
        '<p><strong>The verification rule:</strong> every line quoted in an entry must '
        'appear character for character in the copy of the page that was fetched, and '
        'in the difference between that copy and the previous one. An entry that fails '
        'either check is discarded, not corrected.</p>'
        '<p><strong>What an empty week means:</strong> that every source in the table '
        'below was reached and none of them moved. It never means a source could not '
        'be checked &mdash; an unreachable page is recorded as unreachable and shown as '
        'stale in the table.</p>'
        '<p><strong>What this is not:</strong> not a complete record of United States '
        'immigration policy, not a filing guide, and not advice. It is a record of '
        'differences on three government pages.</p></section>')

    parts.append(
        '<section data-block="external-sources"><h2>Sources watched, and when each was '
        'last reached</h2>'
        '<p>Published above the entries on purpose. The value of a changelog is entirely '
        'in whether it was actually looking, so the dates it was looking on are part of '
        'the record rather than a footnote.</p>'
        '<div class="table-scroll"><table><thead><tr>'
        '<th>USCIS page</th><th>Watched for</th><th>Last reached</th><th>Status</th>'
        '</tr></thead><tbody>' + "".join(source_rows) + '</tbody></table></div>'
        + ('<p class="note"><strong>One or more sources are stale.</strong> Entries '
           'below remain accurate as records of what was observed on their stated '
           'dates, but the absence of a recent entry for a stale source is not '
           'evidence that it has not changed.</p>' if stale_ids else '')
        + '<p class="note">These are United States government pages. Nothing here is '
          'affiliated with this publication, and no page was included for any reason '
          'other than being the primary source for the subject.</p></section>')

    parts.append(entries_html)

    parts.append(
        '<section><h2>How to check or reproduce this</h2><ol>'
        '<li>Open the agency link in any entry. The quoted line should appear on that '
        'page, unless it has changed again since the date the entry names.</li>'
        '<li>If it has changed again, that is a later change and it will appear as its '
        'own dated entry rather than as an edit to this one. Entries are not rewritten '
        'once published.</li>'
        '<li>If a quoted line was never on that page, that is an error worth reporting: '
        'the corrections address is on the corrections page, and a correction is logged '
        'there rather than quietly edited away.</li></ol>'
        '<p>This record is published under the Creative Commons Attribution 4.0 '
        'International licence (CC BY 4.0). Quote it, including commercially, with '
        'attribution to Professional Resource Library and a link to this page. Please '
        'also cite the USCIS URL in the entry, because USCIS is the authority and this '
        'page is only the record of when it moved.</p></section>')

    parts.append(
        '<section class="faq" data-faq="true"><h2>Questions about this record</h2>'
        + "".join(f'<div class="faq-item"><h3>{esc(q)}</h3><p>{esc(a)}</p></div>'
                  for q, a in faqs) + '</section>')

    parts.append(
        '<section><h2>Editorial boundary</h2>'
        '<p>This page reports what a United States government page said and when it '
        'changed. It does not interpret immigration law, does not say what any change '
        'means for any person or filing, and does not recommend a course of action. '
        'Nobody paid for anything on this page, and it carries the editorial desk '
        f'byline because no individual wrote it.</p><p>{esc(DISCLAIMER)}</p></section>')

    blocks = [
        f'<script type="application/ld+json">{json.dumps(dataset_ld, ensure_ascii=False)}</script>',
        f'<script type="application/ld+json">{json.dumps(faq_ld, ensure_ascii=False)}</script>',
    ]

    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{esc(title)} | {esc(pub["title"])}</title>\n'
        f'<meta name="description" content="{esc(description)}">\n'
        f'<link rel="canonical" href="{esc(url)}">\n'
        '<link rel="stylesheet" href="/styles.css">\n'
        + "\n".join(blocks) + "\n" + clarity + "</head>\n<body>\n"
        + header + "\n<main>\n"
        '<p class="eyebrow">Primary-source record &middot; checked weekly &middot; '
        f'{len(entries)} change(s) recorded</p>\n'
        f'<h1>{esc(title)}</h1>\n'
        '<p class="dek">USCIS publishes what is required today. It does not publish a '
        'record of what it required last month, so there is no citable answer to the '
        'question a reporter and a half-finished applicant both ask: when did this '
        'change? This page is that record. Each entry quotes the agency\'s own words, '
        'links the page they are printed on, and carries the date the page was read.</p>\n'
        + "\n".join(parts) + "\n</main>\n" + footer + "\n</body></html>\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    tracked = json.loads(TRACKED.read_text(encoding="utf-8"))
    entries_doc = (json.loads(ENTRIES.read_text(encoding="utf-8"))
                   if ENTRIES.exists() else {"entries": []})
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"sources": {}}
    entries = sorted(entries_doc.get("entries", []),
                     key=lambda e: (e["date_observed"], e["id"]), reverse=True)

    unregistered = [s["url"] for s in tracked["sources"]
                    if s["url"].rstrip("/") not in SOURCES_BY_URL]
    if unregistered:
        print("USCIS CHANGELOG PAGE: FAIL")
        for u in unregistered:
            print(f"  HARD_FAIL tracked source is not registered and verified in "
                  f"data/external-sources.json: {u}")
        return 1
    if not tracked["sources"]:
        print("USCIS CHANGELOG PAGE: FAIL")
        print("  HARD_FAIL zero tracked sources; there is nothing to watch")
        return 1

    page = build_page(tracked, entries, state)
    target = ROOT / PUBLICATIONS[tracked["lane"]]["folder"] / SLUG
    changed = (not target.exists()) or target.read_text(encoding="utf-8") != page
    if args.write and changed:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8", newline="\n")

    print("USCIS CHANGELOG PAGE")
    print(f"  sources watched: {len(tracked['sources'])}")
    print(f"  entries published: {len(entries)}")
    print(f"  {'wrote' if (args.write and changed) else 'unchanged' if not changed else 'would write'}"
          f" {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
