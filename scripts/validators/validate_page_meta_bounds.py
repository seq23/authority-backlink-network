#!/usr/bin/env python3
"""Titles (30-70) and meta descriptions (110-160): in bounds and unique per site.

What this stops happening again
-------------------------------
Bing Webmaster, 25 Sep 2026, on the three publications this repo serves:

  rule 118  meta description too short: founderoperatorlibrary.com/ (82),
            founderoperatorlibrary.com/about (56), memphisvendorlibrary.com/ (68)
  audit     short descriptions on 25 more pages, over-long (161-238) on 60,
            62 duplicate-description groups from the daily generator's one
            sentence mould, and one duplicate <title> on memphisvendorlibrary.com
            (daily 2026-07-19 and 2026-08-22), because the generator's title
            left out the audience that distinguished the two briefs.
  site scan title too long (over 70) on 398 pages: the composed daily title
            runs to 114 characters, and a "| Site" suffix pushed others over.

The fix is at source: lib/meta_description.py holds the bounds, every generator
builds or checks its description against it and raises rather than write a bad
one, authority_v4_autopilot.py gives each page the first <title> form that fits
and is unused (or refuses the brief), and sync_page_meta.py carries a source
change onto pages that already exist.
This validator checks the published tree against the same constants.

Severity
--------
A description of the wrong length or a repeated title is a page-quality defect,
not corruption, so the page findings are STRONG_WARNING: reported on every run,
never blocking a release. The generators are the hard guard. What does fail
hard is this check going inert or its generator contract breaking:

  zero       no pages, titles or descriptions examined
  contract   daily_description() cannot describe some pantry combination, or
             the autopilot no longer refuses a duplicate heading or a brief
             with no unused in-bounds <title>

    python3 scripts/validators/validate_page_meta_bounds.py
"""
from __future__ import annotations

import html
import itertools
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import meta_description as md  # noqa: E402
from lib import site_urls  # noqa: E402

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
DESC_RE = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)
CANON_RE = re.compile(r'<link\s+rel="canonical"\s+href="([^"]*)"', re.I)
NOINDEX_RE = re.compile(r'<meta\s+name="robots"\s+content="[^"]*noindex', re.I)


def scan_pages() -> tuple[dict, list[dict]]:
    counts = {"pages": 0, "titles": 0, "descriptions": 0, "publications": 0}
    findings: list[dict] = []
    for pub in json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8")):
        folder = ROOT / pub["folder"]
        domain = site_urls.domain_of(pub)
        counts["publications"] += 1
        titles: dict[str, list[str]] = defaultdict(list)
        descs: dict[str, list[str]] = defaultdict(list)
        for path in sorted(folder.rglob("*.html")):
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            head = text.split("</head>", 1)[0]
            if NOINDEX_RE.search(head):
                continue
            counts["pages"] += 1
            t = TITLE_RE.search(head)
            d = DESC_RE.search(head)
            title = html.unescape(t.group(1).strip()) if t else ""
            desc = html.unescape(d.group(1)) if d else ""
            if title:
                counts["titles"] += 1
            if desc:
                counts["descriptions"] += 1
            if not md.title_fits(title):
                findings.append({"page": rel, "defect": "title_out_of_bounds", "length": len(title),
                                 "bounds": [md.TITLE_MIN, md.TITLE_MAX]})
            if not md.fits(desc):
                findings.append({"page": rel, "defect": "description_out_of_bounds",
                                 "length": len(desc), "bounds": [md.DESC_MIN, md.DESC_MAX]})
            # A page that canonicalises to another URL is not competing for its
            # own snippet, so it is left out of the uniqueness check.
            canon = CANON_RE.search(head)
            own = site_urls.page_url(domain, path.relative_to(folder).as_posix())
            if canon and canon.group(1).rstrip("/") != own.rstrip("/"):
                continue
            titles[title.casefold()].append(rel)
            descs[desc].append(rel)
        for kind, groups in (("duplicate_title", titles), ("duplicate_description", descs)):
            for value, pages in groups.items():
                if value and len(pages) > 1:
                    findings.append({"defect": kind, "value": value, "pages": pages})
    return counts, findings


def contract_failures() -> tuple[list[str], int]:
    """The generator side: every pantry extreme describes inside the bounds,
    and the autopilot still refuses a repeated title."""
    failures: list[str] = []
    exercised = 0
    pantry = json.loads((ROOT / "content-bank/yearly-pantry.json").read_text(encoding="utf-8"))
    for key, pub in pantry["publications"].items():
        # The shortest and longest value of each input: the combinations that
        # sit at the edges of the bounds.
        edges = [sorted({min(pub[f], key=len), max(pub[f], key=len)})
                 for f in ("clusters", "audiences", "formats", "intents", "modifiers")]
        for c, a, f, i, m in itertools.product(*edges):
            exercised += 1
            try:
                md.daily_description(cluster=c, audience=a, fmt=f, intent=i, modifier=m)
            except ValueError as exc:
                failures.append(f"{key}: {exc}")
    src = (ROOT / "scripts/authority_v4_autopilot.py").read_text(encoding="utf-8")
    if "meta_description.daily_description(" not in src:
        failures.append("authority_v4_autopilot.py no longer builds its description with "
                        "lib.meta_description.daily_description()")
    if "brief['seo_title'] = seo_title_for(brief, pub_key)" not in src \
            or not re.search(r"brief\['title'\]\.casefold\(\) in taken\(pub_key\)\['headings'\] "
                             r"or not brief\['seo_title'\]", src) \
            or "'duplicate_title'" not in src:
        failures.append("authority_v4_autopilot.py no longer refuses a heading the "
                        "publication already has, or a brief with no unused 30-70 character <title>")
    return failures, exercised


def main() -> int:
    counts, findings = scan_pages()
    contract, exercised = contract_failures()
    import sync_page_meta
    drift, missing, _ = sync_page_meta.plan()
    for rel, field, current, want in drift:
        findings.append({"page": rel, "defect": f"{field}_not_synced_from_source",
                         "current": current, "source": want})
    for rel in missing:
        findings.append({"page": rel, "defect": "source_names_missing_page"})

    hard: list[str] = list(contract)
    for key in ("publications", "pages", "titles", "descriptions"):
        if counts[key] == 0:
            hard.append(f"zero {key} examined: a guard over an empty list reports PASS forever")
    if exercised == 0:
        hard.append("zero pantry combinations exercised")

    status = "FAIL" if hard else ("PASS_WITH_STRONG_WARNING" if findings else "PASS")
    print(json.dumps({
        "validator": "page_meta_bounds",
        "status": status,
        "hard_failures": len(hard),
        "strong_warnings": len(findings),
        "soft_warnings": 0,
        "bounds": {"description": [md.DESC_MIN, md.DESC_MAX], "title": [md.TITLE_MIN, md.TITLE_MAX]},
        "examined": counts,
        "pantry_edge_combinations_exercised": exercised,
        "hard": hard,
        "findings": findings[:200],
    }, indent=2, ensure_ascii=False))
    return 1 if (hard or findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
