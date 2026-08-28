#!/usr/bin/env python3
"""Render the compiled consumer reporting company directory.

This is the first original compiled asset on this network. Everything else here
is an article; this is a reference table, and the difference matters. An article
is a thing that cites sources. A reference table is a thing that can itself be
cited, which is the move the one property in this portfolio that earns citations
actually made: it took a published, enumerable list from a primary source and
made it addressable.

The source is the CFPB's 2025 List of Consumer Reporting Companies, compiled by
scripts/compile_consumer_reporting_companies.py into
data/compiled/cfpb-consumer-reporting-companies-2025.json. Every value on the
rendered page comes from that file, and every value in that file came from the
CFPB's own CSV export or, for the nationwide section the export omits, from the
CFPB's PDF. This script computes nothing except counts, and the counts are
counts of rows it did not write.

Two constraints shape the rendering, and both are deliberate:

  * Company websites are printed without the https:// scheme and are NOT
    anchors. These are 61 data brokers with no editorial relationship to this
    publication; linking them would pass ranking signal the publication has no
    basis to pass, and scripts/hostile_review.py rejects any URL outside
    data/external-sources.json anywhere in the page text, anchor or not.
  * No dollar figure appears anywhere. The CFPB's PDF contains a few; this page
    carries none, because a compiled table that invents or half-quotes a number
    is worth less than no table.

    python3 scripts/build_consumer_reporting_directory.py --write
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/compiled/cfpb-consumer-reporting-companies-2025.json"
PUBLICATIONS = {p["id"]: p for p in json.loads(
    (ROOT / "data/publications.json").read_text(encoding="utf-8"))}
SOURCES = {s["id"]: s for s in json.loads(
    (ROOT / "data/external-sources.json").read_text(encoding="utf-8"))["sources"]}

LANE = "professional"
SLUG = "consumer-reporting-companies-directory.html"
PUBLISHED = "2026-08-28"

TITLE = "Consumer Reporting Companies: the CFPB's 2025 List, Compiled"
H1 = "Every Consumer Reporting Company on the CFPB's 2025 List"
DESCRIPTION = ("The Consumer Financial Protection Bureau's 2025 list of consumer "
               "reporting companies, transcribed into one page: every company, its "
               "category, whether it provides a free report, whether it offers a "
               "security freeze, and where to write.")

DISCLAIMER = ("This page is informational. It is not legal, medical, mental-health, "
              "immigration, financial, or professional advice.")

HEADER_RE = re.compile(r"<header>.*?</header>", re.S | re.I)
FOOTER_RE = re.compile(r"<footer>.*?</footer>", re.S | re.I)
CLARITY_RE = re.compile(r"<script data-clarity-loader>.*?</script>", re.S | re.I)


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def slugify(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return out or "entry"


def chrome() -> tuple[str, str, str]:
    """Header, footer and analytics loader, lifted from the publication's own
    index.html so this page cannot drift away from the rest of the site."""
    index = (ROOT / PUBLICATIONS[LANE]["folder"] / "index.html").read_text(encoding="utf-8")
    header = HEADER_RE.search(index)
    footer = FOOTER_RE.search(index)
    clarity = CLARITY_RE.search(index)
    if not header or not footer:
        raise SystemExit("cannot read chrome from the professional index.html")
    return header.group(0), footer.group(0), (clarity.group(0) if clarity else "")


def cite(source_id: str, anchor: str | None = None) -> str:
    """One anchor to one registered, network-verified source.

    Every id must exist in data/external-sources.json and be registered for this
    lane, which is the same rule scripts/link_audit.py enforces at HARD_FAIL.
    Failing here rather than at validation makes the cause obvious.
    """
    source = SOURCES.get(source_id)
    if source is None:
        raise SystemExit(f"source {source_id!r} is not in data/external-sources.json")
    if LANE not in source["lanes"]:
        raise SystemExit(f"source {source_id!r} is not registered for the {LANE} lane")
    return (f'<a href="{esc(source["url"])}" data-source="external-authority" '
            f'rel="noopener">{esc(anchor or source["title"])}</a>')


def table(headers: list[str], rows: list[list[str]], row_ids: list[str] | None = None) -> str:
    """Render a table, refusing to emit an empty cell.

    An empty cell is a blocking failure in
    scripts/validators/validate_content_pattern_contract.js, and the reason it is
    blocking is that a half-filled row is not citable. The compiler already
    substitutes a spelled-out "not listed" for every blank source value, so
    reaching this raise means something upstream changed.
    """
    head = "".join(f"<th scope=\"col\">{esc(h)}</th>" for h in headers)
    body = ""
    for index, row in enumerate(rows):
        if len(row) != len(headers):
            raise SystemExit(f"row width {len(row)} != {len(headers)}: {row}")
        for cell in row:
            if not str(cell).strip():
                raise SystemExit(f"empty table cell in row: {row}")
        attr = f' id="{esc(row_ids[index])}"' if row_ids else ""
        body += f"<tr{attr}>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
    return ('<div class="table-scroll"><table><thead><tr>'
            f'{head}</tr></thead><tbody>{body}</tbody></table></div>')


def build(data: dict) -> str:
    pub = PUBLICATIONS[LANE]
    domain = pub["working_domain"]
    url = f"https://{domain}/{SLUG[:-5]}"
    header, footer, clarity = chrome()
    entries = data["entries"]
    counts = data["counts"]

    by_category: dict[str, list[dict]] = {}
    for entry in entries:
        by_category.setdefault(entry["category"], []).append(entry)

    direct_answer = (
        f'The Consumer Financial Protection Bureau publishes a list of consumer '
        f'reporting companies. Its {data["edition"]} edition names '
        f'{counts["companies"]} companies across {counts["categories"]} categories: '
        f'the three nationwide credit bureaus plus {counts["from_csv"]} companies that '
        f'report on employment, tenancy, bank accounts, insurance, medical history, '
        f'subprime lending, telecoms, retail returns and gambling. This page is that '
        f'list, in full, on one page. The CFPB records that all {counts["companies"]} '
        f'provide a free report on request and that {counts["security_freeze_yes"]} of '
        f'them will place a security freeze.')

    recommends = (
        f'Start from the category that matches the decision that went against you. '
        f'A denied apartment is a tenant screening file, not a credit file, and the '
        f'{len(by_category.get("Tenant Screening", []))} companies listed under Tenant '
        f'Screening are the ones to request it from.')

    # ------------------------------------------------------------------ blocks
    blocks: list[str] = []

    blocks.append(
        '<section><h2>What this page is, and what it is not</h2>'
        f'<p>This is a transcription. The Consumer Financial Protection Bureau '
        f'compiled and published this list; this publication typed it into one '
        f'document and did nothing else to it. Every company name, category, '
        f'self-description, phone number, mailing address, free-report flag and '
        f'freeze flag below is carried through from the CFPB\'s own files without '
        f'edit. Nothing was researched, estimated, ranked or added here.</p>'
        f'<p>{esc(data["what_this_is_not"])}</p>'
        f'<p>The reason to reproduce a list the CFPB already publishes is that the '
        f'CFPB does not publish it as a page. It publishes a 44-page PDF, a '
        f'JavaScript-paginated widget spread over three screens, and a CSV download. '
        f'None of the three can be linked to at the level of one company, quoted '
        f'without a reader downloading something, or read at all with scripting off. '
        f'This page can. Each row below carries its own anchor.</p></section>')

    blocks.append(
        '<section><h2>Where every value on this page came from</h2>'
        f'<p>The CFPB\'s own currency statement, verbatim: '
        f'&ldquo;{esc(data["currency_statement_verbatim"])}&rdquo; '
        f'That sentence is the CFPB\'s, not this publication\'s, and it is the single '
        f'most important thing on this page: a directory is only as current as the day '
        f'the agency last revised it.</p>' +
        table(["What", "Value"], [
            ["Publisher", esc(data["publisher"])],
            ["Edition", esc(data["edition"])],
            ["The Bureau's own page", cite("cfpb-consumer-reporting-companies-list",
                                           "Companies List")],
            ["Full PDF, 44 pages", cite("cfpb-consumer-reporting-companies-list-pdf-2025",
                                        "List of Consumer Reporting Companies (2025 PDF)")],
            ["Machine-readable export", cite("cfpb-consumer-reporting-companies-list-csv-2025",
                                             "2025 CSV export")],
            ["CSV SHA-256", f'<code>{esc(data["sources"]["csv"]["sha256"])}</code>'],
            ["PDF SHA-256", f'<code>{esc(data["sources"]["pdf"]["sha256"])}</code>'],
            ["Retrieved", esc(data["retrieved"])],
            ["Companies transcribed", f'{counts["companies"]} '
             f'({counts["from_csv"]} from the CSV, {counts["from_pdf"]} from the PDF)'],
        ]) +
        '<p class="note">The checksums are published so that anyone can confirm this '
        'page was built from the bytes the CFPB actually served, rather than from a '
        'remembered or paraphrased version of them. If the CFPB republishes the list, '
        'those hashes stop matching and the builder in this repository refuses to '
        'run.</p></section>')

    blocks.append(
        '<section><h2>How many companies are in each category</h2>' +
        table(["Category", "Companies", "Free report on request", "Will place a security freeze"],
              [[esc(category),
                str(len(rows)),
                str(sum(1 for r in rows if r["free_report"] == "Yes")),
                str(sum(1 for r in rows if r["security_freeze"] == "Yes"))]
               for category, rows in
               ((c, by_category[c]) for c in data["category_order"])]) +
        '<p>The two right-hand columns are the CFPB\'s own <em>Free Report</em> and '
        '<em>Freeze Report</em> fields, counted. They are flags, not promises: the PDF '
        'prints a sentence or two of qualifying text under each company\'s '
        '&ldquo;Free report&rdquo; and &ldquo;Freeze your report&rdquo; headings that '
        'the export reduces to Yes or No, so the PDF remains the place to read what a '
        'Yes is conditioned on. On a security freeze generally, the FTC explains what '
        'one does and does not stop: ' + cite("ftc-credit-freezes-and-fraud-alerts") +
        '.</p></section>')

    # One section per category, in the PDF's own order.
    for category in data["category_order"]:
        rows = by_category[category]
        blocks.append(
            f'<section id="cat-{esc(slugify(category))}">'
            f'<h2>{esc(category)}</h2>'
            f'<p>{len(rows)} '
            f'{"company" if len(rows) == 1 else "companies"} the CFPB lists under '
            f'{esc(category)}. The description column is each company\'s own words as '
            f'the CFPB recorded them.</p>' +
            table(["Company", "What the CFPB records it does", "Free report",
                   "Security freeze", "Website", "Phone"],
                  [[esc(e["company"]), esc(e["description"]), esc(e["free_report"]),
                    esc(e["security_freeze"]),
                    f'<code>{esc(e["website_display"])}</code>', esc(e["phone"])]
                   for e in rows],
                  row_ids=[f'co-{slugify(e["company"])}' for e in rows]) +
            '</section>')

    blocks.append(
        '<section id="mailing-addresses"><h2>Where to write, by company</h2>'
        '<p>The Fair Credit Reporting Act dispute route runs on writing, and a written '
        'dispute needs an address. The CFPB lists one for every company on the list; '
        'they are gathered here so a reader does not have to page through a PDF to '
        'find one. On what a dispute letter has to contain and what the company owes '
        'in return, see ' + cite("ftc-disputing-credit-report-errors") + ' and '
        + cite("cfpb-dispute-credit-report-error") + '.</p>' +
        table(["Company", "Category", "Mailing address"],
              [[esc(e["company"]), esc(e["category"]), esc(e["address"])]
               for e in entries]) +
        '</section>')

    blocks.append(
        '<section><h2>What this compilation leaves out, and why</h2><ul>' +
        "".join(f"<li>{esc(item)}</li>" for item in data["excluded"]) +
        '<li>Live links to the 61 companies. Their web addresses are printed in full '
        'so they can be copied, but they are not anchors. This publication has no '
        'relationship with any company on this list, has not assessed any of them, '
        'and will not pass a ranking signal to a data broker on the strength of a '
        'government list that explicitly says it has not verified them either.</li>'
        '<li>Any figure in dollars. The CFPB\'s PDF contains a few; none is reproduced '
        'here, because a compiled table that half-quotes a number is worse than one '
        'that omits it.</li>'
        '<li>Any company not on the CFPB\'s list. The Bureau states the list &ldquo;is '
        'not intended to be all-inclusive and does not cover every company in the '
        'industry.&rdquo; Nothing was added to fill that gap.</li>'
        '</ul>' +
        '<p>Two mechanical changes were made to the source values and are recorded '
        'rather than hidden:</p><ul>' +
        "".join(f"<li>{esc(item)}</li>" for item in data["transformations"]) +
        '</ul></section>')

    blocks.append(
        '<section><h2>What this page does not prove</h2>'
        '<p>Being a compiled reference is not the same as being a cited one. This page '
        'existing is evidence that the list was transcribed accurately and published; '
        'it is not evidence that anyone has linked to it, quoted it, or found it. '
        'Those are separate observations that have to be measured separately, and this '
        'publication does not treat a page it rendered as a citation it earned.</p>'
        '<p>Nor does inclusion on the CFPB\'s list mean a company holds a file on any '
        'particular person. Most of these companies will have nothing on most readers. '
        'The list is a map of who might, not a statement that anyone does.</p></section>')

    blocks.append(
        '<section data-block="external-sources"><h2>Sources</h2>'
        '<p>Everything above rests on these. All are federal government publications, '
        'none is affiliated with this publication, and nothing was paid for their '
        'inclusion.</p><ul>'
        f'<li>{cite("cfpb-credit-reports-and-scores")} &mdash; Consumer Financial '
        f'Protection Bureau. <span class="note">What a consumer report contains and '
        f'who may see it.</span></li>'
        f'<li>{cite("cfpb-tenant-screening-report")} &mdash; Consumer Financial '
        f'Protection Bureau. <span class="note">What a landlord receives, and the '
        f'applicant\'s right to the report behind a denial.</span></li>'
        f'<li>{cite("ftc-free-credit-reports")} &mdash; Federal Trade Commission. '
        f'<span class="note">Which reports are free and which sites charge.</span></li>'
        f'<li>{cite("identitytheft-gov")} &mdash; Federal Trade Commission. '
        f'<span class="note">Where to start when an entry on one of these files is '
        f'there because of identity theft.</span></li>'
        '</ul>'
        '<p class="note">Requirements and company details change. Confirm the current '
        'text at the source before relying on it.</p></section>')

    faq = [
        ("Is this the official CFPB list?",
         "No. The CFPB publishes the list; this page is a transcription of it. The "
         "Bureau's own page, PDF and CSV export are linked above, and they are what "
         "governs if this page and the source ever disagree."),
        ("How current is it?",
         f'The CFPB states: "{data["currency_statement_verbatim"]}" That is the '
         f'edition transcribed here, retrieved on {data["retrieved"]}. No later '
         f'edition was published at that date.'),
        ("Does the CFPB vouch for what these companies say they do?",
         "No, and it says so. The Bureau states the list incorporates information "
         "from the companies' own self-descriptions that it has not independently "
         "verified. This publication has not verified them either."),
        ("Which of these companies will give me a report for free?",
         f'The CFPB marks all {counts["companies"]} as providing a free report on '
         f'request. The PDF qualifies several of them company by company, most often '
         f'with a condition such as the company holding a file on you at all, so read '
         f'the PDF entry before assuming a report is available.'),
        ("Which of them will freeze my file?",
         f'{counts["security_freeze_yes"]} of {counts["companies"]}, by the CFPB\'s '
         f'Freeze Report field, including the three nationwide bureaus. The remaining '
         f'{counts["companies"] - counts["security_freeze_yes"]} are marked No.'),
        ("Why are the company websites not clickable?",
         "Because this publication has no relationship with any of them and has not "
         "assessed any of them. The addresses are printed in full so they can be "
         "copied; they are not endorsed by being linked."),
    ]

    # ------------------------------------------------------------- structured
    citations = [
        {"@type": "CreativeWork", "name": SOURCES[i]["title"], "url": SOURCES[i]["url"],
         "publisher": {"@type": "Organization", "name": SOURCES[i]["publisher"]}}
        for i in ("cfpb-consumer-reporting-companies-list",
                  "cfpb-consumer-reporting-companies-list-pdf-2025",
                  "cfpb-consumer-reporting-companies-list-csv-2025",
                  "cfpb-credit-reports-and-scores",
                  "cfpb-tenant-screening-report",
                  "cfpb-dispute-credit-report-error",
                  "ftc-disputing-credit-report-errors",
                  "ftc-credit-freezes-and-fraud-alerts",
                  "ftc-free-credit-reports",
                  "identitytheft-gov")
    ]
    article_ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": H1,
        "description": DESCRIPTION,
        "datePublished": PUBLISHED,
        "dateModified": PUBLISHED,
        "inLanguage": "en",
        "isAccessibleForFree": True,
        "publisher": {"@type": "Organization", "name": pub["title"],
                      "url": f"https://{domain}"},
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "citation": citations,
    }
    dataset_ld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": data["title"],
        "description": data["what_this_is"],
        "url": url,
        "inLanguage": "en",
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization",
                    "name": "Consumer Financial Protection Bureau"},
        "sourceOrganization": {"@type": "Organization",
                               "name": "Consumer Financial Protection Bureau"},
        "publisher": {"@type": "Organization", "name": pub["title"],
                      "url": f"https://{domain}"},
        "isBasedOn": [SOURCES[i]["url"] for i in (
            "cfpb-consumer-reporting-companies-list",
            "cfpb-consumer-reporting-companies-list-pdf-2025",
            "cfpb-consumer-reporting-companies-list-csv-2025")],
        "dateModified": PUBLISHED,
        "variableMeasured": ["Company", "Category", "Self-description recorded by the CFPB",
                             "Website", "Phone", "Mailing address",
                             "Free report on request", "Security freeze offered"],
    }
    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a}}
                       for q, a in faq],
    }

    ld = "\n".join(
        f'<script type="application/ld+json">{json.dumps(block, ensure_ascii=False)}</script>'
        for block in (article_ld, dataset_ld, faq_ld))

    faq_html = "".join(
        f'<div class="faq-item"><h3>{esc(q)}</h3><p>{esc(a)}</p></div>' for q, a in faq)

    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{esc(TITLE)} | {esc(pub["title"])}</title>\n'
        f'<meta name="description" content="{esc(DESCRIPTION)}">\n'
        f'<link rel="canonical" href="{esc(url)}">\n'
        '<link rel="stylesheet" href="/styles.css">\n'
        + ld + "\n" + clarity + "</head>\n<body>\n"
        + header + "\n<main>\n"
        '<p class="eyebrow">Compiled reference</p>\n'
        f'<h1>{esc(H1)}</h1>\n'
        f'<p class="dek">{direct_answer}</p>\n'
        '<section class="card"><div class="info-panel recommendation-summary" '
        'data-content-block="recommendation_summary" id="recommendation-summary">'
        '<h2>What this page recommends</h2>'
        f'<p class="recommendation-summary__answer">{recommends}</p></div>'
        f'<h2>Short answer</h2><p>{direct_answer}</p></section>\n'
        + "\n".join(blocks) + "\n"
        + f'<section class="faq" data-faq="true"><h2>Questions people ask</h2>{faq_html}</section>\n'
        + '<section><h2>Editorial boundary</h2>'
        '<p>This page reproduces a federal agency\'s list. It does not advise anyone '
        'on whether to request a report, dispute an entry, or place a freeze, and it '
        'cannot say what any company holds about any individual.</p>'
        f'<p>{esc(DISCLAIMER)}</p></section>\n'
        '</main>\n' + footer + '\n</body></html>\n'
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if not DATA.exists():
        print(f"FAIL: {DATA} is missing; run "
              f"scripts/compile_consumer_reporting_companies.py --fetch", file=sys.stderr)
        return 1
    data = json.loads(DATA.read_text(encoding="utf-8"))
    rendered = build(data)
    target = ROOT / PUBLICATIONS[LANE]["folder"] / SLUG
    current = target.read_text(encoding="utf-8") if target.exists() else None

    words = len(re.findall(r"\b[\w'-]+\b", re.sub(r"<[^>]+>", " ", rendered)))
    changed = current != rendered
    if changed and args.write:
        target.write_text(rendered, encoding="utf-8", newline="\n")

    print(json.dumps({
        "status": "PASS",
        "page": str(target.relative_to(ROOT)),
        "written": bool(changed and args.write),
        "changed": changed,
        "companies": data["counts"]["companies"],
        "categories": data["counts"]["categories"],
        "words": words,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
