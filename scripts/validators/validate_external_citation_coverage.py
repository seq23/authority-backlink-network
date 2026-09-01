#!/usr/bin/env python3
"""These publications must keep citing sources their owner does not own.

The state this stops the network returning to
---------------------------------------------
Measured on 2026-08-27, across 608 pages: 21,055 absolute anchors, 20,484 of
them to the publications' own domains, 571 to affiliated brands (all correctly
`sponsored nofollow`), and **zero to any domain outside the portfolio**. A
publication that cites nobody does not read as reference material to a quality
classifier or to a model deciding what to quote. It reads as a link surface.

Outbound citations were then added, and they are easy to lose again: a page
rebuild that drops the citation block, a source removed from the registry, a
generator change that stops calling `add_external_citations.py`. Each of those
is silent, and none of them fails any other check. So the coverage is ratcheted:
`data/external-citation-floor.json` records what each publication currently
achieves, and this validator fails if any publication falls below it.

Four things fail hard:

  regression     a publication citing fewer pages, or fewer distinct outside
                 domains, than the recorded floor
  zero           any publication citing nothing at all, or the whole run
                 examining zero pages -- a guard that iterates an empty list
                 reports PASS forever and its green receipt is then taken as
                 proof of the thing it never looked at
  unregistered   an outbound citation to a domain that is not a verified entry
                 in data/external-sources.json
  misdeclared    an editorial citation of an outside authority carrying
                 rel="sponsored" or rel="nofollow". Those attributes declare a
                 paid placement. Applying them to a federal agency or to a
                 vendor's own price sheet is a false disclosure, and it undoes
                 the reason for citing at all. `sponsored nofollow` stays
                 mandatory for affiliated portfolio links, which this validator
                 does not touch.

Raising the floor is a deliberate edit to the floor file, made when coverage
genuinely improves. Lowering it is the thing this exists to make visible.

    python3 scripts/validators/validate_external_citation_coverage.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
SITES = ROOT / "sites"
PUBLICATIONS = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
REGISTRY = json.loads((ROOT / "data/external-sources.json").read_text(encoding="utf-8"))
FLOOR_PATH = ROOT / "data/external-citation-floor.json"

ANCHOR_RE = re.compile(r"<a\s+([^>]*?href=\"(https?://[^\"]+)\"[^>]*?)>", re.I)
MAIN_RE = re.compile(r"<main[^>]*>(.*?)</main>", re.S | re.I)

# Pages that answer no question of their own. A masthead or a topic hub that
# cited outside authorities would be decorating navigation, which is the exact
# failure this work is supposed to avoid, so they are excluded from the
# denominator rather than being forced to carry citations.
SKIP_NAMES = {"404.html", "index.html", "about.html", "masthead.html",
              "contributors.html", "corrections.html", "editorial-standards.html"}
SKIP_DIRS = {"topics"}


def norm(host_or_url: str) -> str:
    host = urlparse(host_or_url).netloc if host_or_url.startswith("http") else host_or_url
    return host.lower().removeprefix("www.").strip("/")


def main() -> int:
    failures: list[str] = []

    source_domains = {norm(s["url"]) for s in REGISTRY["sources"]}
    source_urls = {s["url"].rstrip("/") for s in REGISTRY["sources"]}
    lanes_by_domain: dict[str, set[str]] = {}
    for source in REGISTRY["sources"]:
        lanes_by_domain.setdefault(norm(source["url"]), set()).update(source["lanes"])

    own_domains = {norm(p["working_domain"]) for p in PUBLICATIONS}
    brands = json.loads((ROOT / "data/brands.json").read_text(encoding="utf-8"))
    brand_domains = set()
    for brand in brands:
        for value in [brand.get("url", "")] + [d for d in brand.get("domains", [])] \
                + [link.get("url", "") for link in brand.get("approved_links", [])]:
            if value:
                brand_domains.add(norm(value))

    observed: dict[str, dict] = {}
    pages_examined = 0

    for pub in PUBLICATIONS:
        lane = pub["id"]
        folder = ROOT / pub["folder"]
        cited_pages = 0
        substantive = 0
        domains: set[str] = set()
        for path in sorted(folder.rglob("*.html")):
            if path.name in SKIP_NAMES:
                continue
            if SKIP_DIRS & {part.lower() for part in path.relative_to(folder).parts[:-1]}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            main_match = MAIN_RE.search(text)
            body = main_match.group(1) if main_match else text
            substantive += 1
            pages_examined += 1
            rel_path = path.relative_to(ROOT).as_posix()
            page_domains: set[str] = set()
            for open_tag, href in ANCHOR_RE.findall(body):
                domain = norm(href)
                if domain in own_domains or domain in brand_domains:
                    continue
                if domain not in source_domains:
                    failures.append(
                        f"HARD_FAIL {rel_path}: cites {domain}, which is not a "
                        "verified entry in data/external-sources.json")
                    continue
                if href.rstrip("/") not in source_urls:
                    failures.append(
                        f"HARD_FAIL {rel_path}: cites an unverified URL on a "
                        f"registered domain: {href}")
                    continue
                if lane not in lanes_by_domain[domain]:
                    failures.append(
                        f"HARD_FAIL {rel_path}: {domain} is not registered for the "
                        f"{lane} lane")
                    continue
                rel_match = re.search(r'rel="([^"]*)"', open_tag, re.I)
                tokens = {t.lower() for t in rel_match.group(1).split()} if rel_match else set()
                bad = tokens & {"sponsored", "nofollow"}
                if bad:
                    failures.append(
                        f"HARD_FAIL {rel_path}: editorial citation of {domain} carries "
                        f"rel={sorted(bad)}, which declares a paid placement: {href}")
                page_domains.add(domain)
            if page_domains:
                cited_pages += 1
                domains |= page_domains
        observed[lane] = {"substantive_pages": substantive,
                          "pages_citing_outside": cited_pages,
                          "distinct_external_domains": len(domains)}

    if pages_examined == 0:
        print("EXTERNAL CITATION COVERAGE: FAIL")
        print("  HARD_FAIL examined zero pages; this guard must not report PASS on an "
              "empty loop")
        return 1

    if not FLOOR_PATH.exists():
        print("EXTERNAL CITATION COVERAGE: FAIL")
        print(f"  HARD_FAIL missing floor file {FLOOR_PATH.relative_to(ROOT)}; without "
              "it a regression is invisible")
        return 1
    floor = json.loads(FLOOR_PATH.read_text(encoding="utf-8"))["floors"]

    for lane, actual in sorted(observed.items()):
        if actual["pages_citing_outside"] == 0:
            failures.append(
                f"HARD_FAIL {lane}: zero pages cite a domain outside the portfolio. "
                "This is the exact state the citation work exists to prevent.")
        if actual["distinct_external_domains"] == 0:
            failures.append(f"HARD_FAIL {lane}: zero distinct outside domains cited")
        expected = floor.get(lane)
        if expected is None:
            failures.append(f"HARD_FAIL {lane}: no floor recorded in "
                            f"{FLOOR_PATH.relative_to(ROOT)}")
            continue
        for key in ("pages_citing_outside", "distinct_external_domains"):
            if actual[key] < expected[key]:
                failures.append(
                    f"HARD_FAIL {lane}: {key} fell to {actual[key]} from a recorded "
                    f"floor of {expected[key]}. Restore the citations or change the "
                    "floor deliberately and say why.")

    print("EXTERNAL CITATION COVERAGE")
    print(f"  pages examined: {pages_examined}")
    for lane, actual in sorted(observed.items()):
        expected = floor.get(lane, {})
        print(f"  {lane:<13} {actual['pages_citing_outside']}/"
              f"{actual['substantive_pages']} page(s) cite outside; "
              f"{actual['distinct_external_domains']} distinct domain(s) "
              f"(floor {expected.get('pages_citing_outside', '?')}/"
              f"{expected.get('distinct_external_domains', '?')})")

    if failures:
        print("EXTERNAL CITATION COVERAGE: FAIL")
        for line in sorted(set(failures)):
            print(f"  {line}")
        return 1
    print("EXTERNAL CITATION COVERAGE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
