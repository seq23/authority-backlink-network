#!/usr/bin/env python3
"""Every dollar figure on the wedding cost dataset page must resolve to a source.

The failure this exists to stop
-------------------------------
An original-data page is worth something only because its numbers are real. The
way that stops being true is not dramatic: someone opens the HTML, changes a
figure because it reads better, or adds a row for a vendor nobody fetched, and
the page still validates because nothing was checking the numbers against
anything. From then on the page is a fabrication that looks exactly like
research, and every other figure on it is worthless too, because a reader cannot
tell which one was edited.

So this validator treats `sites/memphis-local/memphis-wedding-cost-by-guest-count-2026.html`
as untrusted text. It extracts every dollar amount inside `<main>` and requires
each one to resolve to one of three things:

  a published row   a price in data/memphis-wedding-cost-2026.json, which carries
                    the vendor's source URL, the date it was observed, and the
                    vendor's own words
  a derivation      a value this validator recomputes from those rows, using the
                    arithmetic the dataset itself declares
  dataset prose     a figure that literally appears inside a string in the
                    dataset file, such as a vendor's quoted price sheet or a
                    stated national comparison

Anything else is a number with no provenance, and it hard-fails.

It also checks the other half of the promise: every row must carry a source URL
and an observation date, that URL must be registered and verified in
data/external-sources.json, and it must actually be linked from the page. A
citation that exists only in the data file is not a citation the reader can
follow.

Hard-fails if it examines zero figures or zero rows. A guard that iterates over
an empty list reports PASS forever, and the green receipt is then taken as proof
that the thing it never looked at is fine.

    python3 scripts/validators/validate_wedding_cost_dataset.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data/memphis-wedding-cost-2026.json"
EXTERNAL_SOURCES = ROOT / "data/external-sources.json"
VERIFICATION = ROOT / "reports/external-source-verification.json"

MAIN_RE = re.compile(r"<main[^>]*>(.*?)</main>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
MONEY_RE = re.compile(r"\$\s?([\d,]+(?:\.\d{1,2})?)")
HREF_RE = re.compile(r'href="([^"]+)"')
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The minimum defensible sample. The plan this work comes from is explicit that
# six vendors is not a dataset, and that a thin edition is worse than none. If
# the file is ever trimmed below this the page must come down, not degrade
# quietly into a blog post with numbers in it.
MIN_VENDORS = 12


def as_money(value: float) -> str:
    """Must match scripts/build_wedding_cost_dataset_page.py:money()."""
    if float(value) == int(float(value)):
        return f"{int(float(value)):,}"
    return f"{float(value):,.2f}"


def band_for(guests: int) -> str:
    if guests < 100:
        return "50-99"
    if guests < 150:
        return "100-149"
    return "150+"


def derived_values(dataset: dict) -> set[str]:
    """Recompute every figure the page is allowed to derive.

    Deliberately reimplemented here rather than imported from the builder: the
    point is to check the published HTML against the dataset, and a shared
    helper that both sides trust would only prove the builder agrees with
    itself.
    """
    out: set[str] = set()
    derivation = dataset["derivation"]

    fixed_low = fixed_high = 0.0
    for component in derivation["fixed_components"]:
        out.add(as_money(component["low"]))
        out.add(as_money(component["high"]))
        fixed_low += component["low"]
        fixed_high += component["high"]
    out.add(as_money(round(fixed_low, 2)))
    out.add(as_money(round(fixed_high, 2)))

    for component in derivation["per_guest_components"]:
        if component.get("banded"):
            for band in component["bands"].values():
                out.add(as_money(band["low"]))
                out.add(as_money(band["high"]))
            out.add(as_money(min(b["low"] for b in component["bands"].values())))
            out.add(as_money(max(b["high"] for b in component["bands"].values())))
        else:
            out.add(as_money(component["low"]))
            out.add(as_money(component["high"]))

    for guests in derivation["guest_counts"]:
        low = high = 0.0
        for component in derivation["per_guest_components"]:
            if component.get("banded"):
                band = component["bands"][band_for(guests)]
                low += band["low"]
                high += band["high"]
            else:
                low += component["low"]
                high += component["high"]
        low, high = round(low, 2), round(high, 2)
        total_low = round(fixed_low + low * guests, 2)
        total_high = round(fixed_high + high * guests, 2)
        for value in (low, high, total_low, total_high,
                      round(total_low / guests, 2), round(total_high / guests, 2)):
            out.add(as_money(value))
    return out


def row_values(dataset: dict) -> set[str]:
    out: set[str] = set()
    for row in dataset["rows"]:
        if "price_low" in row:
            out.add(as_money(row["price_low"]))
            out.add(as_money(row["price_high"]))
        else:
            out.add(as_money(row["price"]))
    return out


def prose_values(dataset: dict) -> set[str]:
    """Dollar amounts written inside the dataset's own strings.

    A vendor's quoted price sheet ("150+ $11.50 100-149 $11.95") and the stated
    national comparison live here. They are allowed on the page because they are
    in the reviewed data file; a number invented in the HTML is not.
    """
    raw = DATASET_PATH.read_text(encoding="utf-8")
    out = {match.group(1).lstrip("0") or "0" for match in MONEY_RE.finditer(raw)}
    out |= {match.group(1) for match in MONEY_RE.finditer(raw)}
    context = dataset.get("national_context", {})
    for key in ("per_guest_low", "per_guest_high"):
        if key in context:
            out.add(as_money(context[key]))
    return out


def main() -> int:
    failures: list[str] = []
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    page_path = ROOT / "sites/memphis-local" / dataset["slug"]
    csv_path = ROOT / "sites/memphis-local/data/memphis-wedding-cost-by-guest-count-2026.csv"

    rows = dataset.get("rows", [])
    vendors = dataset.get("vendors", [])
    if not rows:
        print("WEDDING COST DATASET: FAIL")
        print("  HARD_FAIL dataset contains zero rows; nothing was examined")
        return 1
    if len(vendors) < MIN_VENDORS:
        failures.append(
            f"HARD_FAIL sample is {len(vendors)} vendor(s); the stated floor for a "
            f"publishable edition is {MIN_VENDORS}. Publish more or withdraw the page.")

    if not page_path.exists():
        print("WEDDING COST DATASET: FAIL")
        print(f"  HARD_FAIL published page missing: {page_path.relative_to(ROOT)}")
        return 1
    if not csv_path.exists():
        failures.append("HARD_FAIL the page offers a CSV that does not exist: "
                        f"{csv_path.relative_to(ROOT)}")

    # -- every row must be attributable -------------------------------------
    registry = json.loads(EXTERNAL_SOURCES.read_text(encoding="utf-8"))
    registered = {s["url"].rstrip("/") for s in registry["sources"]}
    memphis_lane = {s["url"].rstrip("/") for s in registry["sources"]
                    if "memphis" in s["lanes"]}
    receipts = {}
    if VERIFICATION.exists():
        receipts = json.loads(VERIFICATION.read_text(encoding="utf-8"))

    vendor_ids = {v["id"] for v in vendors}
    rows_examined = 0
    for index, row in enumerate(rows):
        label = f"row {index} ({row.get('vendor', '?')} / {row.get('item', '?')})"
        rows_examined += 1
        if row.get("vendor") not in vendor_ids:
            failures.append(f"HARD_FAIL {label}: vendor id is not in the vendor list")
        url = row.get("source_url", "")
        if not url:
            failures.append(f"HARD_FAIL {label}: no source_url")
        elif url.rstrip("/") not in registered:
            failures.append(f"HARD_FAIL {label}: source_url is not registered in "
                            f"data/external-sources.json: {url}")
        elif url.rstrip("/") not in memphis_lane:
            failures.append(f"HARD_FAIL {label}: source is not registered for the "
                            f"memphis lane: {url}")
        if not DATE_RE.match(row.get("observed", "")):
            failures.append(f"HARD_FAIL {label}: no ISO observation date")
        if not row.get("quote", "").strip():
            failures.append(f"HARD_FAIL {label}: no verbatim published quote")
        if "price" not in row and not ("price_low" in row and "price_high" in row):
            failures.append(f"HARD_FAIL {label}: no price")

    # -- the receipts must say the sources were actually reachable ----------
    receipt_by_id = {}
    if isinstance(receipts, dict):
        for entry in receipts.get("sources", receipts.get("receipts", [])) or []:
            if isinstance(entry, dict) and entry.get("id"):
                receipt_by_id[entry["id"]] = entry
    source_ids = {s["url"].rstrip("/"): s["id"] for s in registry["sources"]}
    for url in sorted({r.get("source_url", "").rstrip("/") for r in rows if r.get("source_url")}):
        sid = source_ids.get(url)
        entry = receipt_by_id.get(sid)
        if entry is not None and entry.get("status") not in (200, "200", None):
            failures.append(f"STRONG_WARNING {sid}: last verification returned "
                            f"{entry.get('status')} for {url}")

    # -- every figure on the page must resolve ------------------------------
    page = page_path.read_text(encoding="utf-8")
    main_match = MAIN_RE.search(page)
    if not main_match:
        print("WEDDING COST DATASET: FAIL")
        print("  HARD_FAIL page has no <main>; nothing could be examined")
        return 1
    body = SCRIPT_RE.sub(" ", main_match.group(1))
    hrefs = set(HREF_RE.findall(body))
    text = TAG_RE.sub(" ", body).replace("&ndash;", " ").replace("&mdash;", " ")

    allowed = row_values(dataset) | derived_values(dataset) | prose_values(dataset)
    figures = [m.group(1) for m in MONEY_RE.finditer(text)]
    if not figures:
        print("WEDDING COST DATASET: FAIL")
        print("  HARD_FAIL no dollar figures found on the page; the guard examined "
              "nothing and must not report PASS")
        return 1

    unresolved: dict[str, int] = {}
    for figure in figures:
        normalised = figure
        if normalised not in allowed:
            # A whole-dollar figure may be written either way round.
            try:
                alt = as_money(float(figure.replace(",", "")))
            except ValueError:
                alt = figure
            if alt not in allowed:
                unresolved[figure] = unresolved.get(figure, 0) + 1
    for figure, count in sorted(unresolved.items()):
        failures.append(f"HARD_FAIL page figure ${figure} (x{count}) does not resolve "
                        "to any row, derivation or quoted string in "
                        "data/memphis-wedding-cost-2026.json")

    # -- every cited source must be reachable from the page -----------------
    linked = {h.rstrip("/") for h in hrefs if h.startswith("http")}
    for url in sorted({r.get("source_url", "").rstrip("/") for r in rows if r.get("source_url")}):
        if url not in linked:
            failures.append(f"HARD_FAIL source is used for a price but never linked "
                            f"from the page: {url}")

    # -- the method statement has to actually be there ----------------------
    for required in ("Method, sample and limits", "What this data does not cover",
                     "Collection window", "Download the full dataset as CSV"):
        if required not in body:
            failures.append(f"HARD_FAIL page is missing its {required!r} section; the "
                            "method statement is what makes the data citable")
    if '"@type": "Dataset"' not in page:
        failures.append("HARD_FAIL page emits no Dataset JSON-LD")

    print("WEDDING COST DATASET")
    print(f"  vendors: {len(vendors)}   rows examined: {rows_examined}   "
          f"page figures examined: {len(figures)}   "
          f"distinct sources linked: {len({r.get('source_url') for r in rows if r.get('source_url')})}")
    if failures:
        print("WEDDING COST DATASET: FAIL")
        for line in failures:
            print(f"  {line}")
        return 1
    print("WEDDING COST DATASET: PASS (every published figure resolves to a row with a "
          "source URL and an observation date)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
