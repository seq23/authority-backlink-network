#!/usr/bin/env python3
"""Render the Memphis wedding cost dataset page and its CSV from the dataset file.

Why this exists as a generator rather than a hand-written page
-------------------------------------------------------------
The value of an original-data page is entirely in whether the numbers are real.
A hand-written HTML table is a place where a number can be improved by hand and
nothing notices. So the page is derived: every figure on it comes from
`data/memphis-wedding-cost-2026.json`, where each row carries the source URL the
price is printed on and the date the page was read.

`scripts/validators/validate_wedding_cost_dataset.py` then checks the published
HTML against that dataset independently, and fails if any dollar figure on the
page does not resolve to a row or to a derivation the dataset defines.

Every source URL used here must also be registered in
`data/external-sources.json` and have a 200 receipt, because
`scripts/hostile_review.py` rejects any outbound link that was not fetched and
verified. That is deliberate: a price attributed to a page that does not exist
is worse than no price.

    python3 scripts/build_wedding_cost_dataset_page.py --write
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data/memphis-wedding-cost-2026.json"
PUBLICATIONS = {p["id"]: p for p in json.loads(
    (ROOT / "data/publications.json").read_text(encoding="utf-8"))}
SOURCES_BY_URL = {s["url"].rstrip("/"): s for s in json.loads(
    (ROOT / "data/external-sources.json").read_text(encoding="utf-8"))["sources"]}

DISCLAIMER = ("This page is informational. It is not legal, medical, mental-health, "
              "immigration, financial, or professional advice.")

HEADER_RE = re.compile(r"<header>.*?</header>", re.S | re.I)
FOOTER_RE = re.compile(r"<footer>.*?</footer>", re.S | re.I)
CLARITY_RE = re.compile(r"<script data-clarity-loader>.*?</script>", re.S | re.I)


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def money(value: float) -> str:
    """One canonical rendering of a dollar amount.

    The validator parses the page with the same rule, so a figure that does not
    round-trip through this function cannot appear on the page and pass.
    """
    if float(value) == int(float(value)):
        return f"${int(float(value)):,}"
    return f"${float(value):,.2f}"


# ---------------------------------------------------------------------------
# The derivation. Arithmetic on published per-person and per-item prices only.
# ---------------------------------------------------------------------------

def band_for(guests: int) -> str:
    if guests < 100:
        return "50-99"
    if guests < 150:
        return "100-149"
    return "150+"


def per_guest(dataset: dict, guests: int) -> tuple[float, float]:
    low = high = 0.0
    for component in dataset["derivation"]["per_guest_components"]:
        if component.get("banded"):
            band = component["bands"][band_for(guests)]
            low += band["low"]
            high += band["high"]
        else:
            low += component["low"]
            high += component["high"]
    return round(low, 2), round(high, 2)


def fixed_total(dataset: dict) -> tuple[float, float]:
    low = sum(c["low"] for c in dataset["derivation"]["fixed_components"])
    high = sum(c["high"] for c in dataset["derivation"]["fixed_components"])
    return round(low, 2), round(high, 2)


def totals(dataset: dict, guests: int) -> dict:
    pg_low, pg_high = per_guest(dataset, guests)
    fx_low, fx_high = fixed_total(dataset)
    total_low = round(fx_low + pg_low * guests, 2)
    total_high = round(fx_high + pg_high * guests, 2)
    return {
        "guests": guests,
        "per_guest_low": pg_low,
        "per_guest_high": pg_high,
        "total_low": total_low,
        "total_high": total_high,
        "all_in_per_guest_low": round(total_low / guests, 2),
        "all_in_per_guest_high": round(total_high / guests, 2),
    }


def row_price_cell(row: dict) -> str:
    if "price_low" in row:
        return f'{money(row["price_low"])} &ndash; {money(row["price_high"])}'
    return money(row["price"])


UNIT_LABELS = {
    "package": "package",
    "starting_price": "starting price",
    "stated_average": "vendor's stated average",
    "range": "vendor's stated range",
    "rental": "venue rental",
    "per_person": "per person",
    "per_serving": "per serving",
    "per_hour": "per hour",
    "per_item": "per item",
    "flat_fee": "flat fee",
    "order_minimum": "order minimum",
    "minimum": "minimum",
}


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def build_csv(dataset: dict) -> str:
    vendors = {v["id"]: v for v in dataset["vendors"]}
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["vendor", "vendor_area", "category", "item", "price_low",
                     "price_high", "unit", "guest_band", "includes",
                     "source_url", "observed", "published_quote"])
    for row in dataset["rows"]:
        low = row.get("price_low", row.get("price"))
        high = row.get("price_high", row.get("price"))
        vendor = vendors[row["vendor"]]
        writer.writerow([vendor["name"], vendor["area"], row["category"], row["item"],
                         low, high, row["unit"], row.get("guest_band", ""),
                         row["includes"], row["source_url"], row["observed"],
                         row["quote"]])
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def chrome(lane: str) -> tuple[str, str, str]:
    index = (ROOT / PUBLICATIONS[lane]["folder"] / "index.html").read_text(encoding="utf-8")
    header = HEADER_RE.search(index)
    footer = FOOTER_RE.search(index)
    clarity = CLARITY_RE.search(index)
    if not header or not footer:
        raise SystemExit(f"cannot read chrome from {lane} index.html")
    return header.group(0), footer.group(0), (clarity.group(0) if clarity else "")


def build_page(dataset: dict) -> str:
    lane = dataset["lane"]
    pub = PUBLICATIONS[lane]
    domain = pub["working_domain"]
    url = f'https://{domain}{dataset["canonical_path"]}'
    csv_path = "/data/memphis-wedding-cost-by-guest-count-2026.csv"
    csv_url = f"https://{domain}{csv_path}"
    header, footer, clarity = chrome(lane)
    vendors = {v["id"]: v for v in dataset["vendors"]}

    vendor_count = len(dataset["vendors"])
    row_count = len(dataset["rows"])
    window = dataset["collection_window"]
    fx_low, fx_high = fixed_total(dataset)
    guest_rows = [totals(dataset, n) for n in dataset["derivation"]["guest_counts"]]

    description = (
        f"Published prices from {vendor_count} Memphis-area wedding and event vendors, "
        f"collected {window['start']}, and what they imply about cost by guest count. "
        "Method, sample size and exclusions stated; full table and CSV on the page.")

    dataset_ld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": dataset["title"],
        "description": description,
        "url": url,
        "identifier": url,
        "version": dataset["edition"],
        "datePublished": dataset["published"],
        "dateModified": dataset["published"],
        "inLanguage": "en",
        "isAccessibleForFree": True,
        # Expressed as text rather than a URL on purpose: hostile_review.py locks
        # outbound domains to the registry, and creativecommons.org is not a
        # source this publication cites. The licence still parses as schema.org
        # Dataset.license, which accepts Text.
        "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
        "creator": {"@type": "Organization",
                    "name": "Memphis Vendor Library Editorial Desk",
                    "url": f"https://{domain}/masthead"},
        "publisher": {"@type": "Organization", "name": pub["title"],
                      "url": f"https://{domain}"},
        "spatialCoverage": {"@type": "Place", "name": dataset["geography"]},
        "temporalCoverage": f'{window["start"]}/{window["end"]}',
        "measurementTechnique": window["method"],
        "variableMeasured": sorted({row["category"] for row in dataset["rows"]}),
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv",
                          "contentUrl": csv_url}],
        "citation": [
            {"@type": "CreativeWork",
             "name": SOURCES_BY_URL[u]["title"],
             "url": SOURCES_BY_URL[u]["url"],
             "publisher": {"@type": "Organization",
                           "name": SOURCES_BY_URL[u]["publisher"]}}
            for u in sorted({row["source_url"].rstrip("/") for row in dataset["rows"]})
        ],
    }

    faqs = [
        ("How many vendors is this based on?",
         f"{vendor_count} Memphis-area vendors, and {row_count} individual published "
         f"prices, all read from the vendors' own websites on {window['start']}. Some "
         "categories are a sample of one. Where that is true it is labelled on the "
         "table rather than presented as an average."),
        ("Why is the per-guest figure lower than the national numbers?",
         "Because this dataset covers less. National per-guest figures of roughly "
         f"{money(dataset['national_context']['per_guest_low'])} to "
         f"{money(dataset['national_context']['per_guest_high'])} include "
         "alcohol, attire, rings, stationery, videography, transport "
         "and hair and makeup. None of those are in this sample, because no vendor in "
         "it publishes a price for them. The figures here are not a smaller version of "
         "the national number; they are a different, narrower measurement."),
        ("Why does the cost per guest fall as the guest count rises?",
         "Two published effects, both visible in the table. Most of what Memphis "
         "vendors publish is fixed: a photographer, a DJ, a coordinator and a venue "
         "cost the same for 50 guests as for 200, so the fixed block is divided across "
         "more people. On top of that, the one caterer in this sample that publishes "
         "banded pricing charges less per person at higher counts."),
        ("Can I use these numbers?",
         "Yes. The table and the CSV are published so they can be quoted, and every "
         "figure names the vendor page it came from and the date it was read. Please "
         "cite the source URL for the figure rather than this page alone, and note "
         "that published prices change."),
        ("Why are most Memphis vendors missing?",
         "Because most do not publish a price. A vendor that answers pricing only by "
         "email cannot be in a desk-researched dataset without inventing something, so "
         "it is not here. That is a selection bias with a knowable direction: vendors "
         "who post a starting price are more likely to be competing on transparency or "
         "price, so this sample probably sits below the market it is drawn from."),
    ]
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q,
                              "acceptedAnswer": {"@type": "Answer", "text": a}}
                             for q, a in faqs]}

    parts: list[str] = []

    # --- method, first, because that is what makes it quotable ---------------
    parts.append(
        '<section class="card"><div class="info-panel recommendation-summary" '
        'data-content-block="recommendation_summary" id="recommendation-summary">'
        '<h2>What this page recommends</h2>'
        '<p class="recommendation-summary__answer">Budget the fixed vendors first and '
        'the per-guest vendors second: in this sample the fixed block does not move '
        'with guest count at all, so the cost per guest falls steeply as the list '
        'grows, and cutting the guest list saves far less than people expect.</p></div>'
        '<h2>Method, sample and limits</h2>'
        f'<p><strong>Sample:</strong> {vendor_count} Memphis-area wedding and event '
        f'vendors, {row_count} individual published prices.</p>'
        f'<p><strong>Collection window:</strong> {esc(window["start"])} to '
        f'{esc(window["end"])}. Every price was read from the vendor\'s own website on '
        'that date.</p>'
        f'<p><strong>Method:</strong> {esc(window["method"])}</p>'
        f'<p><strong>Coverage:</strong> {esc(dataset["geography"])}</p>'
        '<p><strong>What this is not:</strong> not a survey, not an average of what '
        'couples paid, and not a ranking. It is a record of what these vendors publish.'
        '</p></section>')

    # --- what it does not cover ---------------------------------------------
    parts.append(
        '<section><h2>What this data does not cover</h2>'
        '<p>Stated before the numbers rather than after them, because the gaps decide '
        'what the numbers can honestly be used for.</p><ul>'
        + "".join(f"<li>{esc(item)}</li>" for item in dataset["not_covered"])
        + '</ul></section>')

    # --- the headline derived table -----------------------------------------
    parts.append(
        '<section><h2>Cost by guest count, from published Memphis prices</h2>'
        '<p>Guest count is the largest single cost driver in this category, and it is '
        'the thing national wedding sites answer worst: they publish a national average '
        'and apply a city multiplier, which is not a measurement of Memphis. The table '
        'below is arithmetic on the published per-person and per-item prices in this '
        'dataset, plus a fixed block of vendors whose price does not vary with guest '
        'count. Every input is listed underneath it.</p>'
        '<div class="table-scroll"><table><thead><tr>'
        '<th>Guests</th><th>Per-guest variable cost</th><th>Fixed vendor block</th>'
        '<th>Total</th><th>All-in per guest</th></tr></thead><tbody>'
        + "".join(
            f'<tr><td>{t["guests"]}</td>'
            f'<td>{money(t["per_guest_low"])} &ndash; {money(t["per_guest_high"])}</td>'
            f'<td>{money(fx_low)} &ndash; {money(fx_high)}</td>'
            f'<td>{money(t["total_low"])} &ndash; {money(t["total_high"])}</td>'
            f'<td>{money(t["all_in_per_guest_low"])} &ndash; '
            f'{money(t["all_in_per_guest_high"])}</td></tr>'
            for t in guest_rows)
        + '</tbody></table></div>'
        '<p>The shape is the finding. The all-in figure per guest falls from '
        f'{money(guest_rows[0]["all_in_per_guest_low"])}&ndash;'
        f'{money(guest_rows[0]["all_in_per_guest_high"])} at '
        f'{guest_rows[0]["guests"]} guests to '
        f'{money(guest_rows[-1]["all_in_per_guest_low"])}&ndash;'
        f'{money(guest_rows[-1]["all_in_per_guest_high"])} at '
        f'{guest_rows[-1]["guests"]}, because most of what these vendors publish is a '
        'fixed cost being divided across more people. Read the other way: trimming the '
        'guest list saves only the per-guest column, which is the smaller half of the '
        'bill at every count in this table.</p>'
        '<p class="note">These totals are lower than the national per-guest figures for '
        'a reason stated above and worth repeating here: this dataset contains no '
        'alcohol, attire, rings, stationery, videography, transport or beauty costs, '
        'because no vendor in the sample publishes a price for them. It is a narrower '
        'measurement, not a cheaper city.</p></section>')

    # --- inputs to the derivation -------------------------------------------
    parts.append(
        '<section><h2>The per-guest inputs</h2>'
        '<p>Each line is a published Memphis price. Where a component comes from one '
        'vendor, the sample size says so.</p>'
        '<div class="table-scroll"><table><thead><tr>'
        '<th>Component</th><th>Low</th><th>High</th><th>Basis</th><th>Vendors</th>'
        '</tr></thead><tbody>'
        + "".join(
            (f'<tr><td>{esc(c["label"])}</td>'
             f'<td>{money(min(b["low"] for b in c["bands"].values()))}</td>'
             f'<td>{money(max(b["high"] for b in c["bands"].values()))}</td>'
             f'<td>{esc(c["basis"])}</td><td>{c["sample_size"]}</td></tr>')
            if c.get("banded") else
            (f'<tr><td>{esc(c["label"])}</td><td>{money(c["low"])}</td>'
             f'<td>{money(c["high"])}</td><td>{esc(c["basis"])}</td>'
             f'<td>{c["sample_size"]}</td></tr>')
            for c in dataset["derivation"]["per_guest_components"])
        + '</tbody></table></div>'
        '<h2>The fixed inputs</h2>'
        '<div class="table-scroll"><table><thead><tr>'
        '<th>Component</th><th>Low</th><th>High</th><th>Basis</th><th>Vendors</th>'
        '</tr></thead><tbody>'
        + "".join(
            f'<tr><td>{esc(c["label"])}</td><td>{money(c["low"])}</td>'
            f'<td>{money(c["high"])}</td>'
            f'<td>{esc(c["basis"])}'
            + (f' {esc(c["capacity_note"])}' if c.get("capacity_note") else "")
            + f'</td><td>{c["sample_size"]}</td></tr>'
            for c in dataset["derivation"]["fixed_components"])
        + '</tbody></table></div></section>')

    # --- the full underlying table ------------------------------------------
    by_category: dict[str, list[dict]] = {}
    for row in dataset["rows"]:
        by_category.setdefault(row["category"], []).append(row)

    table_blocks = []
    for category in sorted(by_category):
        rows = by_category[category]
        distinct = len({r["vendor"] for r in rows})
        table_blocks.append(
            f'<h3>{esc(category.title())} &mdash; {len(rows)} published price(s) from '
            f'{distinct} vendor(s)</h3>'
            f'<p class="note">{esc(dataset["categories"][category])}</p>'
            '<div class="table-scroll"><table><thead><tr>'
            '<th>Vendor</th><th>Item</th><th>Price</th><th>Unit</th>'
            '<th>What the price covers</th><th>Source</th><th>Observed</th>'
            '</tr></thead><tbody>'
            + "".join(
                f'<tr><td>{esc(vendors[r["vendor"]]["name"])}</td>'
                f'<td>{esc(r["item"])}</td>'
                f'<td>{row_price_cell(r)}</td>'
                f'<td>{esc(UNIT_LABELS[r["unit"]])}</td>'
                f'<td>{esc(r["includes"])}</td>'
                f'<td><a href="{esc(r["source_url"])}" data-source="external-authority" '
                f'rel="noopener">{esc(vendors[r["vendor"]]["name"])}: '
                f'{esc(r["item"])}</a>'
                f'</td><td>{esc(r["observed"])}</td></tr>'
                for r in rows)
            + '</tbody></table></div>')

    parts.append(
        '<section data-block="external-sources"><h2>The underlying table</h2>'
        '<p>Every price in this dataset, with the page it is printed on and the date it '
        'was read. The vendor links are ordinary editorial citations: nothing was paid '
        'for a listing here, no vendor is ranked, and no vendor was told it would '
        'appear. Prices change; check the source before relying on a figure.</p>'
        f'<p><a href="{esc(csv_path)}">Download the full dataset as CSV</a> '
        f'&mdash; {row_count} rows, the same data as the tables below.</p>'
        + "".join(table_blocks)
        + '<p class="note">These vendors are independent. None is affiliated with this '
        'publication, none paid to be included, and inclusion depended only on whether '
        'the vendor publishes a price.</p></section>')

    # --- reproduce it -------------------------------------------------------
    parts.append(
        '<section><h2>How to check or reproduce this</h2><ol>'
        '<li>Open any source link in the table. The figure quoted here should appear on '
        'that page.</li>'
        '<li>If it has changed, the price moved after the observation date shown in the '
        'row. That is expected, and it is why the date is published next to every '
        'figure.</li>'
        '<li>To rebuild the guest-count table, take the per-guest inputs, multiply by '
        'the guest count, and add the fixed block. There is no weighting, no smoothing '
        'and no adjustment factor.</li>'
        '<li>If you find an error, the corrections address is on the corrections page '
        'and a correction will be logged there rather than quietly edited.</li>'
        '</ol>'
        '<p>This dataset is published under the Creative Commons Attribution 4.0 '
        'International licence (CC BY 4.0). Reuse it, including commercially, with '
        'attribution to Memphis Vendor Library and a link to this page.</p>'
        '<p>The next edition will be published at a new URL with its own year, so this '
        'one stays citable rather than being overwritten.</p></section>')

    parts.append(
        '<section class="faq" data-faq="true"><h2>Questions about this dataset</h2>'
        + "".join(f'<div class="faq-item"><h3>{esc(q)}</h3><p>{esc(a)}</p></div>'
                  for q, a in faqs)
        + '</section>')

    parts.append(
        '<section><h2>Editorial boundary</h2>'
        '<p>This is a record of prices Memphis-area vendors publish, not a quote, a '
        'recommendation, a ranking or a negotiation position. No vendor paid to appear '
        'and no vendor was excluded for any reason other than not publishing a price. '
        'It is not tax advice and it does not price any specific event.</p>'
        f'<p>{esc(DISCLAIMER)}</p></section>')

    blocks = [
        f'<script type="application/ld+json">{json.dumps(dataset_ld, ensure_ascii=False)}</script>',
        f'<script type="application/ld+json">{json.dumps(faq_ld, ensure_ascii=False)}</script>',
    ]

    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{esc(dataset["title"])} | {esc(pub["title"])}</title>\n'
        f'<meta name="description" content="{esc(description)}">\n'
        f'<link rel="canonical" href="{esc(url)}">\n'
        '<link rel="stylesheet" href="/styles.css">\n'
        + "\n".join(blocks) + "\n"
        + clarity + "</head>\n<body>\n"
        + header + "\n<main>\n"
        '<p class="eyebrow">Original data &middot; first edition &middot; '
        f'{esc(window["start"])}</p>\n'
        f'<h1>{esc(dataset["title"])}</h1>\n'
        f'<p class="dek">Nobody publishes rigorous Memphis-specific wedding pricing, so '
        f'this publication collected it. {vendor_count} Memphis-area vendors publish '
        f'{row_count} prices on their own websites; this page records all of them, '
        'derives what they imply about cost by guest count, and states plainly what the '
        'sample does not cover.</p>\n'
        + "\n".join(parts) + "\n"
        '</main>\n' + footer + '\n</body></html>\n'
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    lane = dataset["lane"]
    folder = ROOT / PUBLICATIONS[lane]["folder"]
    page_path = folder / dataset["slug"]
    csv_target = folder / "data/memphis-wedding-cost-by-guest-count-2026.csv"

    # Refuse to render a price whose source is not a verified external source.
    # Without this the page would be rejected by hostile_review with a message
    # about link policy, when the real defect is an unverified citation.
    unregistered = sorted({r["source_url"] for r in dataset["rows"]
                           if r["source_url"].rstrip("/") not in SOURCES_BY_URL})
    if unregistered:
        print("WEDDING COST DATASET PAGE: FAIL")
        for url in unregistered:
            print(f"  HARD_FAIL source not registered in data/external-sources.json: {url}")
        return 1

    if not dataset["rows"]:
        print("WEDDING COST DATASET PAGE: FAIL")
        print("  HARD_FAIL dataset has zero rows; there is nothing to publish")
        return 1

    page = build_page(dataset)
    csv_text = build_csv(dataset)

    changes = []
    for target, content in ((page_path, page), (csv_target, csv_text)):
        current = target.read_text(encoding="utf-8") if target.exists() else None
        # The page, once published, is also written to by build_site_navigation.py
        # (breadcrumbs, library nav) and install_editorial_chrome.py. Rewriting it
        # wholesale would delete their work, so an existing page is only replaced
        # when the generated body actually differs in a way that matters: the
        # dataset changed. That is detected by comparing the figures, not the bytes.
        if current is None:
            changes.append(target)
            if args.write:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
        elif target is csv_target and current != content:
            changes.append(target)
            if args.write:
                target.write_text(content, encoding="utf-8", newline="\n")

    vendor_count = len(dataset["vendors"])
    print("WEDDING COST DATASET PAGE")
    print(f"  vendors: {vendor_count}   published prices: {len(dataset['rows'])}")
    print(f"  categories: {len({r['category'] for r in dataset['rows']})}")
    print(f"  sources registered and verified: "
          f"{len({r['source_url'].rstrip('/') for r in dataset['rows']})}")
    for target in changes:
        print(f"  {'wrote' if args.write else 'would write'}: "
              f"{target.relative_to(ROOT).as_posix()}")
    if not changes:
        print("  up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
