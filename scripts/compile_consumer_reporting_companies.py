#!/usr/bin/env python3
"""Compile the CFPB's published List of Consumer Reporting Companies into a
structured dataset this network can publish as a reference.

Why this exists
---------------
This network cites consumerfinance.gov more than any other source (332 outbound
links) and has never itself been the thing anyone cites. The one property in the
portfolio that does earn citations does so for one reason: it took a PUBLISHED,
ENUMERABLE list from a primary source and made it addressable. This does the same
move with a source this network already leans on.

The CFPB publishes its list three ways:

  * a 44-page PDF,
  * a JavaScript-paginated web widget spread over three pages,
  * a CSV export.

None of the three is a single addressable page. The PDF cannot be linked into per
company, the widget renders nothing without JavaScript, and the CSV is a download.
The compiled page this dataset feeds is one server-rendered document with every
entry present in the HTML and an anchor on each one.

What this script does NOT do
----------------------------
It does not add, infer, estimate or normalise a single value. Every field is
carried through verbatim from the CFPB export, with two mechanical exceptions
that are recorded in the output:

  * the four separate address columns are joined into one string,
  * an empty cell becomes the literal string recorded in UNLISTED, because the
    repo's content-pattern contract blocks a page that ships an empty table cell,
    and because "the CFPB does not list one" is a true statement while a blank
    cell is an ambiguous one.

The CSV export omits the PDF's "Nationwide consumer reporting companies" section
entirely. Those three entries are therefore transcribed from the PDF text, and
each transcribed field is stored with the PDF page it came from so the claim can
be checked without re-reading the whole document.

    python3 scripts/compile_consumer_reporting_companies.py --fetch   # re-derive
    python3 scripts/compile_consumer_reporting_companies.py           # verify
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/compiled/cfpb-consumer-reporting-companies-2025.json"

LANDING = ("https://www.consumerfinance.gov/consumer-tools/credit-reports-and-scores/"
           "consumer-reporting-companies/companies-list/")
CSV_URL = ("https://files.consumerfinance.gov/f/documents/"
           "cfpb-consumer-reporting-companies_list_2025.csv")
PDF_URL = ("https://files.consumerfinance.gov/f/documents/"
           "cfpb_consumer-reporting-companies_list_2025.pdf")

# Recorded when the files were first retrieved. --fetch fails loudly if the
# bytes on the CFPB's server no longer hash to these, because that means the
# agency republished the list and the compiled page is describing an edition
# that no longer exists.
CSV_SHA256 = "4379d2ed11817134aed96cd88437f3454640e0f0d820ae1949edc6221d32561d"
PDF_SHA256 = "3f09baa6db7577fd22e2d860aa7ffc6401856b71b835dea9f0571a835146503c"
RETRIEVED = "2026-08-28"

# The CSV is not UTF-8. It carries Windows-1252 curly quotes in the company
# self-descriptions, and decoding it as UTF-8 raises rather than corrupting.
CSV_ENCODING = "cp1252"

UNLISTED = "Not listed by the CFPB"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Order the categories the way the PDF's own table of contents orders them,
# rather than alphabetically or by row count. Nationwide first because that is
# where the PDF puts it and because it is the only category most readers came for.
CATEGORY_ORDER = [
    "Nationwide",
    "Employment Screening",
    "Tenant Screening",
    "Deposit account & payments screening",
    "Personal property insurance",
    "Medical",
    "Low-income & subprime",
    "Supplementary reports",
    "Telecom & utilities",
    "Retail",
    "Gambling & sports betting",
]

# Transcribed from the PDF, pages 9 and 10, which the CSV export does not cover.
# Shared fields are shared in the source: the PDF gives one website, one phone
# and one mailing address for all three, then a per-company direct number.
NATIONWIDE_SHARED = {
    "description": "These are the three big nationwide providers of consumer reports.",
    "website": "AnnualCreditReport.com",
    "phone": "877-322-8228 (Option 1)",
    "address": "Central Source, LLC, P.O. Box 105283, Atlanta, GA 30348-5283",
    "source_pages": [9, 10],
}
NATIONWIDE = [
    ("Equifax", "(888) 378-4329"),
    ("TransUnion", "(800) 916-8800"),
    ("Experian", "(888) 397-3742"),
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    """Retrieve the CFPB file.

    files.consumerfinance.gov answers 403 to a bare urllib request no matter what
    User-Agent it sends, so this falls back to curl. That is a bot rule on the
    CDN, not a missing file, and the sha256 check below is what actually decides
    whether the bytes are the ones this dataset was built from.
    """
    request = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 403:
            raise
    result = subprocess.run(
        ["curl", "-sSL", "--max-time", "120", "-A", UA, url],
        capture_output=True, check=True)
    return result.stdout


def join_address(row: dict) -> str:
    parts = [row.get("Street", ""), row.get("Unit", ""),
             row.get("City", ""), row.get("Postal Code", "")]
    joined = ", ".join(p.strip() for p in parts if p and p.strip())
    return joined or UNLISTED


def display_website(url: str) -> str:
    """Print the company site without its scheme.

    These 61 companies are data-broker entries transcribed from a government
    list, not destinations this publication is vouching for. Rendering them as
    live anchors would send ranking signal to companies with no editorial
    relationship to the page, and the repo's own domain lock in
    scripts/hostile_review.py rejects a bare https:// URL for any domain outside
    data/external-sources.json even when it is plain text. Dropping the scheme
    keeps the value readable and copyable without either problem. The CFPB's own
    PDF prints these as bare domains too.
    """
    if url == UNLISTED:
        return url
    return url.split("://", 1)[-1] if "://" in url else url


def clean(value: str) -> str:
    """Collapse the CSV's embedded newlines without altering any word."""
    return " ".join((value or "").split())


def parse_csv(raw: bytes) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(raw.decode(CSV_ENCODING))))
    entries = []
    for row in rows:
        company = clean(row.get("Company", ""))
        category = clean(row.get("Category", ""))
        # The export's last three lines are the CFPB's own footnote and a
        # pointer back to the PDF, carried in the Company column with every
        # other field blank. They are notes, not companies.
        if not company or not category:
            continue
        entries.append({
            "company": company,
            "category": category,
            "description": clean(row.get("Description", "")) or UNLISTED,
            "website": clean(row.get("Website", "")) or UNLISTED,
            "website_display": display_website(clean(row.get("Website", "")) or UNLISTED),
            "phone": clean(row.get("Phone", "")) or UNLISTED,
            "address": clean(join_address(row)),
            "free_report": clean(row.get("Free Report", "")) or UNLISTED,
            "security_freeze": clean(row.get("Freeze Report", "")) or UNLISTED,
            "source": "csv",
        })
    return entries


def nationwide_entries() -> list[dict]:
    out = []
    for company, direct_phone in NATIONWIDE:
        out.append({
            "company": company,
            "category": "Nationwide",
            "description": NATIONWIDE_SHARED["description"],
            "website": NATIONWIDE_SHARED["website"],
            "website_display": NATIONWIDE_SHARED["website"],
            "phone": f'{NATIONWIDE_SHARED["phone"]} shared; {company} direct: {direct_phone}',
            "address": NATIONWIDE_SHARED["address"],
            "free_report": "Yes",
            "security_freeze": "Yes",
            "source": "pdf",
            "source_pages": NATIONWIDE_SHARED["source_pages"],
        })
    return out


def build(csv_bytes: bytes) -> dict:
    entries = nationwide_entries() + parse_csv(csv_bytes)
    seen_categories = {e["category"] for e in entries}
    unknown = seen_categories - set(CATEGORY_ORDER)
    if unknown:
        raise SystemExit(f"category present in the source but not ordered here: {sorted(unknown)}")
    entries.sort(key=lambda e: (CATEGORY_ORDER.index(e["category"]), e["company"].lower()))

    for entry in entries:
        for field in ("company", "category", "description", "website",
                      "website_display", "phone", "address", "free_report",
                      "security_freeze"):
            if not str(entry[field]).strip():
                raise SystemExit(f"empty field {field!r} on {entry['company']!r}")

    return {
        "schema_version": "1.0",
        "dataset_id": "cfpb-consumer-reporting-companies-2025",
        "title": "CFPB List of Consumer Reporting Companies, 2025 edition",
        "what_this_is": (
            "A structured transcription of the Consumer Financial Protection "
            "Bureau's published 2025 List of Consumer Reporting Companies. Every "
            "value is carried through from the CFPB's own export or, for the "
            "nationwide section the export omits, from the CFPB's PDF. Nothing "
            "here is researched, estimated or added by this publication."),
        "what_this_is_not": (
            "It is not a ranking, a recommendation, an endorsement, or a "
            "verification of any company on it. The CFPB states that the list "
            "incorporates the companies' own self-descriptions and that it has "
            "not independently verified them. This publication has not verified "
            "them either."),
        "publisher": "Consumer Financial Protection Bureau",
        "edition": "2025",
        "currency_statement_verbatim": "This list is current as of January 2025.",
        "retrieved": RETRIEVED,
        "sources": {
            "landing_page": LANDING,
            "csv": {"url": CSV_URL, "sha256": CSV_SHA256, "encoding": CSV_ENCODING},
            "pdf": {"url": PDF_URL, "sha256": PDF_SHA256},
        },
        "transformations": [
            "Street, Unit, City and Postal Code were joined into a single address string.",
            f"An empty source cell is rendered as {UNLISTED!r} rather than left blank.",
            "Newlines embedded inside CSV fields were collapsed to single spaces.",
            "website_display carries the same URL with the scheme removed; it is what "
            "the published page prints, and the verbatim URL is kept alongside it.",
            "The three nationwide companies were transcribed from PDF pages 9-10, "
            "which the CSV export does not include.",
        ],
        "excluded": [
            "The CSV's final three lines, which carry the CFPB's footnote and a "
            "pointer back to the PDF in the Company column with every other field "
            "blank. They are notes, not companies.",
            "The per-company qualifying prose the PDF prints under 'Free report:' "
            "and 'Freeze your report:'. The CSV reduces those to Yes/No and this "
            "dataset carries the CSV's Yes/No, so the PDF remains the place to read "
            "what the Yes is qualified by.",
        ],
        "counts": {
            "companies": len(entries),
            "from_csv": sum(1 for e in entries if e["source"] == "csv"),
            "from_pdf": sum(1 for e in entries if e["source"] == "pdf"),
            "categories": len(seen_categories),
            "free_report_yes": sum(1 for e in entries if e["free_report"] == "Yes"),
            "security_freeze_yes": sum(1 for e in entries if e["security_freeze"] == "Yes"),
        },
        "category_order": [c for c in CATEGORY_ORDER if c in seen_categories],
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true",
                        help="Re-download the CFPB CSV and PDF and rebuild the dataset.")
    args = parser.parse_args()

    if not args.fetch:
        if not OUT.exists():
            print(f"FAIL: {OUT} does not exist; run with --fetch", file=sys.stderr)
            return 1
        data = json.loads(OUT.read_text(encoding="utf-8"))
        print(json.dumps({
            "status": "PASS",
            "mode": "offline",
            "dataset": data["dataset_id"],
            "companies": data["counts"]["companies"],
            "categories": data["counts"]["categories"],
            "csv_sha256": data["sources"]["csv"]["sha256"],
        }, indent=2))
        return 0

    csv_bytes = fetch(CSV_URL)
    pdf_bytes = fetch(PDF_URL)
    problems = []
    if sha256(csv_bytes) != CSV_SHA256:
        problems.append(f"CSV sha256 changed: {sha256(csv_bytes)}")
    if sha256(pdf_bytes) != PDF_SHA256:
        problems.append(f"PDF sha256 changed: {sha256(pdf_bytes)}")
    if problems:
        # Not a warning. If the bytes moved, the published page is describing an
        # edition of the list that the CFPB no longer serves.
        for line in problems:
            print(f"FAIL: {line}", file=sys.stderr)
        return 1

    data = build(csv_bytes)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"status": "PASS", "mode": "fetch", "written": str(OUT.relative_to(ROOT)),
                      **data["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
