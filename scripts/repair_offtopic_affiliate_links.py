#!/usr/bin/env python3
"""Remove affiliated citations that sit on a page about something else.

Why this exists
---------------
Every daily page carries this sentence, which the network wrote about itself:

    "this publication may cite affiliated projects where the citation is
     topically relevant"

For 72 published placements that was false. `build_brief()` in
`scripts/authority_v4_autopilot.py` drew the paid destination first and the
page's subject second, and constrained the second by the first only when the
target declared `eligible_clusters`. Eight targets declared none and carried
`topics: ["*"]` on every approved link, so both filters were open at once and
subject and destination landed together only by chance. That is how uscisexam.com
- the one property in this portfolio earning AI citations - ended up cited from a
page about trauma-informed leadership, dentistryguides.com from a page about
credit-report errors, and hormonesivhair.com from a page about equine liability.

The generator no longer does this: it declines rather than placing a link it
cannot justify. This script deals with what it already placed.

What it does, and does not do
-----------------------------
It removes the off-topic affiliated citation and recomposes the page around its
absence. It does not delete pages. Retiring a page over a bad link would throw
away the editorial work and the internal links pointing at it to fix a defect
that lives in one section; and a page with no affiliated citation is a complete
page - it states its scope, answers its question and stops.

Nothing about which brand may appear on which subject is decided here. That is
read from `content-bank/yearly-pantry.json`, where the owner declares it, via
`scripts/measure_affiliate_topical_fit.py` - the same verdicts that script
reports, so the two can never disagree about what is off topic.

Pages whose verdict is `in_scope` or `standing_page_no_cluster` are not touched.

Every page is rebuilt from its own recorded values - the title, the scope table,
the last-updated line - and passed back through `lib.page_composer`, the same
module that wrote it. Before writing anything, `--verify` recomposes each page
*with* its existing citation and requires the result to be byte-identical to
what is on disk: if the reconstruction cannot reproduce the page it is not
allowed to replace it.

    python3 scripts/repair_offtopic_affiliate_links.py            # dry run
    python3 scripts/repair_offtopic_affiliate_links.py --write
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import measure_affiliate_topical_fit as fit  # noqa: E402
from lib import page_composer  # noqa: E402

PANTRY = json.loads((ROOT / "content-bank/yearly-pantry.json").read_text(encoding="utf-8"))
PUBLICATIONS = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
PUB_BY_FOLDER = {p["folder"].split("/")[-1]: p for p in PUBLICATIONS}

ARTICLE_RE = re.compile(r"(<article>.*?<h1>.*?</h1>)(.*?)(</article>)", re.S)
# install_editorial_chrome.py splices the disclosure in after the four filters
# and takes the newline that separated them with it, so removing the aside has
# to put one back: compose_body() joins its blocks with exactly one "\n".
DISCLOSURE_RE = re.compile(r'\s*<aside class="affiliate-disclosure".*?</aside>\s*', re.S | re.I)
H1_RE = re.compile(r"<h1>(.*?)</h1>", re.S)
ROW_RE = re.compile(r"<tr><td>([^<]+)</td><td>(.*?)</td></tr>", re.S)
UPDATED_RE = re.compile(r"<em>Last updated: (\d{4}-\d{2}-\d{2})\.")
NOTE_RE = re.compile(r"<h2>Editorial note</h2><p>.*?</p>", re.S)
META_RE = re.compile(r'<p class="meta">.*?</p>', re.S)
LD_RE = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S)
SPONSORED_RE = re.compile(r'<a\s+href="([^"]+)"\s+rel="sponsored nofollow">(.*?)</a>', re.S | re.I)


def unesc(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def pub_key_for(folder: str) -> str:
    for key, cfg in PANTRY["publications"].items():
        if cfg["site_path"].split("/")[-1] == folder:
            return key
    raise KeyError(folder)


def split_page_type(value: str, pub_cfg: dict) -> tuple[str, str]:
    """`Page type` is f"{modifier} {format}". Split it on the recorded values."""
    for fmt in sorted(pub_cfg["formats"], key=len, reverse=True):
        if value.endswith(" " + fmt):
            return value[: -len(fmt) - 1], fmt
    raise ValueError(f"page type not recognised: {value!r}")


def strip_article(noun: str, options: list[str]) -> str:
    """`Written for` is article_for(audience); recover the recorded audience."""
    for option in options:
        if page_composer.article_for(option) == noun:
            return option
    raise ValueError(f"audience not recognised: {noun!r}")


def facts_from_page(path: Path, folder: str) -> dict:
    """Rebuild the composer's `facts` from what the page itself records."""
    text = path.read_text(encoding="utf-8")
    match = ARTICLE_RE.search(text)
    if not match:
        raise ValueError(f"{path}: no <article> with an <h1>")
    head, body, _ = match.groups()
    pub_key = pub_key_for(folder)
    pub_cfg = PANTRY["publications"][pub_key]
    publication = PUB_BY_FOLDER.get(folder, {})

    rows = {unesc(k): unesc(v) for k, v in ROW_RE.findall(body)}
    cluster = rows["Topic"]
    audience = strip_article(rows["Written for"], pub_cfg["audiences"])
    modifier, fmt = split_page_type(rows["Page type"], pub_cfg)
    published_by = rows["Published by"]
    pub_title = published_by.rsplit(" (", 1)[0]
    pub_domain = published_by.rsplit(" (", 1)[1].rstrip(")")

    updated = UPDATED_RE.search(body)
    note = NOTE_RE.search(body)
    meta = META_RE.search(body)
    if not (updated and note and meta):
        raise ValueError(f"{path}: missing last-updated, editorial note, or meta line")

    return {
        "title": unesc(H1_RE.search(head).group(1)),
        "cluster": cluster,
        "audience": audience,
        "format": fmt,
        "intent": rows["Decision stage"],
        "modifier": modifier,
        "date": updated.group(1),
        "pub_title": pub_title or (publication.get("title") or pub_cfg["default_domain"]),
        "pub_domain": pub_domain,
        "editorial_note_html": note.group(0),
        "meta_line_html": meta.group(0),
    }


def citation_facts(base: dict, body: str) -> dict:
    """`base` plus the affiliated fields, read back off the page's own link."""
    link = SPONSORED_RE.search(body)
    if not link:
        raise ValueError("no sponsored link on page")
    url, anchor_html = link.group(1), link.group(2)
    brand = page_composer.brand_for_url(url)
    approved = page_composer.approved_link_for_url(brand, url)
    campaign = page_composer.campaign_for_url(url)
    product = re.search(r"<h2>What you can create</h2><p>.*?</p><p>.*?</p>", body, re.S)
    return {
        **base,
        "anchor_text": html.unescape(anchor_html),
        "link_html": link.group(0),
        "brand_name": brand.get("name", ""),
        "brand_category": brand.get("category", ""),
        "brand_compliance": brand.get("compliance", ""),
        "link_policy": brand.get("link_policy", ""),
        "link_topics": [t for t in (approved.get("topics") or []) if t and t != "*"],
        "campaign_id": campaign.get("campaign_id", "") or _campaign_row(body),
        "campaign_keywords": campaign.get("keywords", []) or [],
        "destination_type": _destination_row(body),
        "product_section_html": product.group(0) if product else "",
    }


def _campaign_row(body: str) -> str:
    rows = {unesc(k): unesc(v) for k, v in ROW_RE.findall(body)}
    return rows.get("Citation campaign", "")


def _destination_row(body: str) -> str:
    rows = {unesc(k): unesc(v) for k, v in ROW_RE.findall(body)}
    return rows.get("Destination type", "").replace(" ", "_")


def citation_free(base: dict) -> dict:
    """The same page with every affiliated field emptied."""
    return {
        **base,
        "anchor_text": "",
        "link_html": "",
        "brand_name": "",
        "brand_category": "",
        "brand_compliance": "",
        "link_policy": "",
        "link_topics": [],
        "campaign_id": "",
        "campaign_keywords": [],
        "destination_type": "",
        "product_section_html": "",
    }


def replace_faq_node(text: str, items: list[dict]) -> str:
    """Swap the FAQPage node for one matching the recomposed FAQ.

    Only the FAQPage node moves. The Article node records the headline, dates,
    author, subject and audience, none of which change when a citation is
    removed, and the BreadcrumbList belongs to the navigation build.
    """
    new_node = page_composer.faq_schema(items)

    def sub(match: re.Match) -> str:
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError:
            return match.group(0)
        graph = data.get("@graph")
        if not isinstance(graph, list) or not any(
                isinstance(n, dict) and n.get("@type") == "FAQPage" for n in graph):
            return match.group(0)
        data["@graph"] = [
            (new_node if isinstance(n, dict) and n.get("@type") == "FAQPage" else n)
            for n in graph
        ]
        return match.group(1) + json.dumps(data) + match.group(3)

    return LD_RE.sub(sub, text, count=0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="apply the repair")
    args = ap.parse_args()

    subjects = fit.page_subjects()
    scope = fit.declared_scope()

    # The same walk and the same verdicts measure_affiliate_topical_fit.py makes.
    targeted: dict[Path, list[str]] = {}
    for path in sorted((ROOT / "sites").rglob("*.html")):
        if path.name == "404.html":
            continue
        rel_key = path.relative_to(ROOT / "sites").as_posix()
        _, cluster = subjects.get(rel_key, ("(standing page)", ""))
        if not cluster:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        seen: set[str] = set()
        for attrs in fit.A_RE.findall(text):
            href = fit.HREF_RE.search(attrs)
            rel = fit.REL_RE.search(attrs)
            if not href or not rel or "sponsored" not in rel.group(1):
                continue
            host = fit.norm(fit.urlparse(href.group(1)).netloc)
            if host in seen:
                continue
            seen.add(host)
            declared = scope.get(host)
            if declared and cluster not in declared:
                targeted.setdefault(path, []).append(host)

    changed, removed, per_target, failures = 0, 0, {}, []
    for path, hosts in sorted(targeted.items()):
        folder = path.relative_to(ROOT / "sites").parts[0]
        text = path.read_text(encoding="utf-8")
        match = ARTICLE_RE.search(text)
        head, body, tail = match.groups()
        pure = DISCLOSURE_RE.sub("\n", body)

        try:
            base = facts_from_page(path, folder)
            with_citation = citation_facts(base, pure)
            rebuilt, _ = page_composer.compose_body(with_citation)
        except (ValueError, KeyError) as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
            continue

        # Refuse to rewrite a page this script cannot first reproduce.
        if pure.strip() != rebuilt.strip():
            failures.append(f"{path.relative_to(ROOT)}: reconstruction did not reproduce the page")
            continue

        new_body, items = page_composer.compose_body(citation_free(base))
        updated = text[:match.start()] + head + "\n" + new_body + tail + text[match.end():]
        updated = replace_faq_node(updated, items)

        if args.write:
            path.write_text(updated, encoding="utf-8")
        changed += 1
        removed += len(hosts)
        for host in hosts:
            per_target[host] = per_target.get(host, 0) + 1

    verb = "removed" if args.write else "would remove"
    print("OFF-TOPIC AFFILIATE LINK REPAIR")
    print(f"\n  pages {'rewritten' if args.write else 'to rewrite'}: {changed}")
    print(f"  affiliated links {verb}: {removed}")
    if per_target:
        print("\n  per target:")
        for host in sorted(per_target, key=lambda h: -per_target[h]):
            print(f"    {host:38s} {per_target[host]:4d}")
    if failures:
        print(f"\n  NOT TOUCHED ({len(failures)}):")
        for line in failures:
            print(f"    - {line}")
    if not args.write:
        print("\n  dry run. Re-run with --write to apply.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
