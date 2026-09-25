#!/usr/bin/env python3
"""Bring every published page's <title> and meta description into line with its source.

Why this exists
---------------
Most generators here are scaffolds: once a page exists they leave it alone,
because build_site_navigation.py, add_external_citations.py and
install_editorial_chrome.py have since written into it and a rewrite from the
template would delete their work (see the comments in build_demand_shape_pages.py,
build_wedding_cost_dataset_page.py and portfolio_backlink_engine.plan_seed_writes).
So fixing a title or description in a generator changed nothing that was
already live, and Bing kept reporting the old one (25 Sep 2026: rule 118 on both
homepages and founderoperatorlibrary.com/about; 62 duplicate-description groups
from the daily mould; descriptions of 161-238 characters on 60 more pages;
titles over 70 characters on 398 pages).

This script owns exactly two things on an existing page: the <title>, and the
description in the <meta name="description"> tag and in any JSON-LD
"description" that carried the same text. Headings, JSON-LD headlines, slugs
and links are left alone. It asks each page's generator what they should be:

  autopilot daily pages     lib.meta_description.daily_description() and
                            daily_title_candidates(), from the cluster and
                            audience in the page's JSON-LD and the modifier,
                            format and intent its <h1> was composed from
  backlink seed pages       portfolio_backlink_engine.seed_description(), and
                            the article's seo_title or title
  cluster articles          content-bank/cluster-articles/*.json
  demand-shape pages        demand_shape_content.PAGES
  data pages                the TITLE / DESCRIPTION / describe() of their builders
  hand-authored pages       HAND_AUTHORED and HAND_TITLES below -- these pages
                            have no generator, so those tables are their source

Editorial pages and topic hubs are not listed: build_editorial_pages.py and
build_site_navigation.py rewrite those pages on every autopilot run.

Idempotent. `--check` (the default) lists drift and exits 1 if there is any;
`--write` applies it. scripts/validators/validate_page_meta_bounds.py
runs the same planner, so a source edit that was never synced fails CI.

    python3 scripts/sync_page_meta.py [--write]
"""
from __future__ import annotations

import html
import itertools
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import meta_description  # noqa: E402
from lib.text_io import write_lf  # noqa: E402

META_RE = re.compile(r'(<meta name="description" content=")([^"]*)(")')
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
SEED_RE = re.compile(r'data-backlink-seed-id="([^"]+)"')

# Pages with no generator: the HTML was uploaded by hand, so the description
# lives here. Each is written from the page's own content (its dek and short
# answer), inside 110-160 characters, and unique.
HAND_AUTHORED = {
    "sites/founder-operator/index.html":
        "Founder Operator Library: practical guides for founders and operators on AI "
        "execution, delegation, lean-team hiring, operating rhythms and virtual events.",
    "sites/founder-operator/about.html":
        "About Founder Operator Library: who owns and edits it, the editorial policy its "
        "guides follow, and how affiliated citations are chosen and disclosed.",
    "sites/founder-operator/ai-executive-coaching-resources.html":
        "Comparing AI coaching, accountability systems and human coaching: when a "
        "structured AI operating system helps with planning, sequencing and review.",
    "sites/founder-operator/ai-marketing-operations-resources.html":
        "Where AI speeds up marketing research, drafts, repurposing and reporting, and "
        "where strategy, positioning and judgment still need a person to own them.",
    "sites/founder-operator/founder-execution-systems.html":
        "Founder execution systems: operating rhythms, daily agendas, review loops and "
        "minimum viable execution days that recover fast after an imperfect day.",
    "sites/memphis-local/index.html":
        "Memphis Vendor Library: questions, cost drivers and checklists for Memphis "
        "weddings, parties, porch styling and grazing tables, before you book a vendor.",
    "sites/memphis-local/about.html":
        "About Memphis Vendor Library: who owns and edits it, the editorial policy behind "
        "its guides, and the standards a local vendor listing has to meet here.",
    "sites/memphis-local/memphis-grazing-table-resources.html":
        "What to clarify before booking a Memphis grazing table: styling only or food "
        "sourcing too, what the quote includes, and who is responsible for food safety.",
    "sites/memphis-local/memphis-party-decor-vendors.html":
        "Questions to ask before booking party decor, hotel room setups or celebration "
        "styling in Memphis: venue rules, materials, setup time and tear-down.",
    "sites/memphis-local/memphis-porch-decorating-resources.html":
        "What to settle before booking seasonal porch decorating in Memphis: season, "
        "entry size, budget, installation complexity and whether take-down is included.",
    "sites/memphis-local/seasonal-home-styling-memphis.html":
        "Seasonal front-door and porch refreshes in Memphis for fall, Halloween, Christmas "
        "and events, and how weather, materials and storage shape the quote.",
    "sites/professional-resources/about.html":
        "About Professional Resource Library: who owns and edits it, its editorial policy, "
        "and the limits that keep its legal, medical and financial pages educational.",
    "sites/professional-resources/dental-decision-resources.html":
        "Questions and comparison points before major dental work: diagnosis clarity, "
        "written treatment plans, cost breakdowns, second opinions and follow-up care.",
    "sites/professional-resources/equine-legal-resource-library.html":
        "Educational resources on horse ownership, sales, boarding, leases and liability, "
        "to list the paperwork questions worth taking to qualified counsel.",
    "sites/professional-resources/hormone-wellness-clinic-research.html":
        "Questions to ask before comparing TRT, IV hydration, hair-loss, peptide or "
        "weight-loss clinics, focused on supervision, monitoring, scope and red flags.",
    "sites/professional-resources/neuro-evaluation-research.html":
        "How to approach ADHD, autism and neuropsychological evaluations: testing purpose, "
        "scope, report usefulness, timeline, cost and what happens after results.",
    "sites/professional-resources/personal-injury-research-resources.html":
        "Educational resources for post-accident decisions: how the personal injury process "
        "runs and which questions to prepare before a consult. Not legal advice.",
    "sites/professional-resources/regulated-service-provider-research.html":
        "How to compare regulated local service providers without relying on slogans: "
        "verify identity, licensing, scope, pricing, red flags and written next steps.",
    "sites/professional-resources/uscis-medical-exam-resources.html":
        "What to ask before booking a USCIS medical exam with a civil surgeon: cost, "
        "documents, vaccination records and timing. Educational, not legal or medical advice.",
}


# Pantry pages whose <title> no longer carries the modifier/format/intent it was
# composed from, so the parts are recorded here instead.
#
# memphis-local 2026-08-22 published the same <title> as 2026-07-19 because the
# generator's title left out the audience (Bing duplicate-title report, 25 Sep
# 2026). It was retitled with its audience rather than canonicalised to the
# earlier page: it is a different page -- a maid or matron of honor rather than
# a caterer, 41 sentences against 28 with 14 shared, and it carries an
# affiliated citation the earlier page does not -- so it is not a copy of it.
# authority_v4_autopilot.py now refuses a title the publication already has.
DAILY_PARTS_OVERRIDE = {
    "sites/memphis-local/daily/2026-08-22-wedding-day-timeline-plain-english-mistakes-to-avoid-for-careful-decision-makers.html":
        ("plain-English", "mistakes to avoid", "for careful decision-makers"),
}


# <title> for hand-uploaded pages whose own title is outside 30-70 characters.
HAND_TITLES = {
    "sites/professional-resources/workplace-burnout-and-boundaries.html":
        "Workplace Burnout and Boundaries Resources",
}


def _publications() -> dict[str, dict]:
    return {p["id"]: p for p in json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))}


def _daily_parts() -> tuple[list[str], list[str], list[str]]:
    pantry = json.loads((ROOT / "content-bank/yearly-pantry.json").read_text(encoding="utf-8"))
    mods, fmts, intents = set(), set(), set()
    for pub in pantry["publications"].values():
        mods.update(pub["modifiers"]); fmts.update(pub["formats"]); intents.update(pub["intents"])
    return sorted(mods), sorted(fmts), sorted(intents)


def _article_node(text: str) -> dict | None:
    for block in LD_RE.findall(text):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for node in data.get("@graph", [data]):
            if isinstance(node, dict) and node.get("@type") == "Article":
                return node
    return None


def _pantry_parts(text: str, rel: str, suffixes: dict) -> tuple | None:
    """(cluster, audience, modifier, format, intent) of a pantry-composed page,
    read from its own JSON-LD and from its <h1>, which keeps the composed title
    even where the <title> has been shortened. None if it is not one."""
    node = _article_node(text) or {}
    cluster = node.get("about") if isinstance(node.get("about"), str) else None
    audience = (node.get("audience") or {}).get("audienceType")
    h1 = H1_RE.search(text)
    heading = html.unescape(re.sub(r"<[^>]+>", "", h1.group(1)).strip()) if h1 else ""
    prefix = f"{cluster.title()}: " if cluster else None
    parts = DAILY_PARTS_OVERRIDE.get(rel) or (
        suffixes.get(heading[len(prefix):]) if prefix and heading.startswith(prefix) else None)
    if not (cluster and audience and parts):
        return None
    return (cluster, audience, *parts)


def _current(text: str) -> tuple[str, str]:
    t = TITLE_RE.search(text)
    d = META_RE.search(text)
    return (html.unescape(t.group(1).strip()) if t else "",
            html.unescape(d.group(2)) if d else "")


def expected_meta() -> tuple[dict[str, dict], list[str]]:
    """{repo-relative path: {"description": ..., "title": ...}} as each page's
    source says it should read, and the daily pages no source was found for.

    "title" is only present for pages whose <title> this script owns.
    """
    pubs = _publications()
    expected: dict[str, dict] = {rel: {"description": d} for rel, d in HAND_AUTHORED.items()}
    for rel, t in HAND_TITLES.items():
        expected.setdefault(rel, {})["title"] = t

    def put(rel: str, description: str, title: str) -> None:
        expected[rel] = {"description": description, "title": title}

    # Data and demand-shape pages.
    import build_consumer_reporting_directory as crd
    import build_uscis_changelog_page as uscis
    import build_wedding_cost_dataset_page as wedding
    from demand_shape_content import PAGES
    prof, memphis = pubs["professional"], pubs["memphis"]
    put(f"{prof['folder']}/{crd.SLUG}", crd.DESCRIPTION,
        meta_description.site_title(crd.TITLE, prof["title"], crd.SLUG))
    put(f"{prof['folder']}{uscis.CANONICAL_PATH}.html", uscis.DESCRIPTION,
        meta_description.site_title(uscis.TITLE, prof["title"], "USCIS changelog"))
    dataset = json.loads(wedding.DATASET_PATH.read_text(encoding="utf-8"))
    put(f"{memphis['folder']}/{dataset['slug']}", wedding.describe(dataset),
        meta_description.site_title(dataset["title"], memphis["title"], dataset["slug"]))
    for page in PAGES:
        pub = pubs[page["lane"]]
        put(f"{pub['folder']}/{page['slug']}", page["description"],
            meta_description.site_title(page.get("seo_title") or page["title"], pub["title"], page["slug"]))

    # Cluster articles.
    for path in sorted((ROOT / "content-bank/cluster-articles").glob("*.json")):
        for a in json.loads(path.read_text(encoding="utf-8"))["articles"]:
            put(f"{pubs[a['publication']]['folder']}/daily/{a['date']}-{a['slug']}.html",
                a["meta_description"], a.get("seo_title") or a["title"])

    # Seed pages and pantry-composed daily pages, identified from the page itself.
    import portfolio_backlink_engine as seed_engine
    seeds = {a["id"]: a for a in json.loads(
        (ROOT / "data/backlink-seed-articles.json").read_text(encoding="utf-8"))["articles"]}
    mods, fmts, intents = _daily_parts()
    suffixes = {f"{m.title()} {f.title()} {i.title()}": (m, f, i)
                for m, f, i in itertools.product(mods, fmts, intents)}
    unidentified: list[str] = []
    for pub in pubs.values():
        folder = ROOT / pub["folder"]
        pantry_pages: list[tuple[str, tuple, str]] = []
        for path in sorted((folder / "daily").glob("*.html")):
            rel = path.relative_to(ROOT).as_posix()
            if rel in expected:
                continue
            text = path.read_text(encoding="utf-8")
            seed_id = SEED_RE.search(text)
            if seed_id and seed_id.group(1) in seeds:
                a = seeds[seed_id.group(1)]
                put(rel, seed_engine.seed_description(a), a.get("seo_title") or a["title"])
                continue
            parts = _pantry_parts(text, rel, suffixes)
            if not parts:
                unidentified.append(rel)
                continue
            cluster, audience, m, f, i = parts
            expected[rel] = {"description": meta_description.daily_description(
                cluster=cluster, audience=audience, fmt=f, intent=i, modifier=m)}
            pantry_pages.append((rel, parts, _current(text)[0]))

        # <title> for pantry pages. Every other page's title is fixed by its own
        # source (above) or by a generator that rewrites it (editorial pages,
        # topic hubs), so those are taken first. A pantry page keeps a title
        # that is already inside the bounds and unique; the rest get the first
        # daily_title_candidates() form that is -- the same rule the autopilot
        # applies to a new page, so a rerun changes nothing.
        pantry_rels = {rel for rel, _, _ in pantry_pages}
        titles: dict[str, str] = {}
        for path in folder.rglob("*.html"):
            rel = path.relative_to(ROOT).as_posix()
            if rel in pantry_rels:
                continue
            titles[rel] = expected.get(rel, {}).get("title") or _current(path.read_text(encoding="utf-8"))[0]
        taken = {t.casefold() for t in titles.values()}
        counts = Counter([t.casefold() for t in titles.values()] + [cur.casefold() for _, _, cur in pantry_pages])
        pending = []
        for rel, parts, cur in pantry_pages:
            if meta_description.title_fits(cur) and counts[cur.casefold()] == 1:
                expected[rel]["title"] = cur
                taken.add(cur.casefold())
            else:
                pending.append((rel, parts, cur))
        for rel, parts, cur in pending:
            cluster, audience, m, f, i = parts
            pick = meta_description.pick_title(meta_description.daily_title_candidates(
                cluster=cluster, audience=audience, fmt=f, intent=i, modifier=m), taken)
            if pick is None:
                raise ValueError(f"{rel}: no <title> form is {meta_description.TITLE_MIN}-"
                                 f"{meta_description.TITLE_MAX} characters and unused on this site")
            expected[rel]["title"] = pick
            taken.add(pick.casefold())
    return expected, unidentified


def apply(text: str, want: dict) -> str:
    """The page with its description replaced in the meta tag and in any JSON-LD
    field that held the same text, and its <title> replaced if one is given.
    Headings, JSON-LD headlines and links are left alone."""
    if want.get("description"):
        m = META_RE.search(text)
        if not m:
            raise ValueError("no <meta name=\"description\">")
        new = want["description"]
        old = html.unescape(m.group(2))
        text = text[:m.start(2)] + html.escape(new) + text[m.end(2):]
        if old != new:
            for enc in {json.dumps(old), json.dumps(old, ensure_ascii=False)}:
                text = text.replace(f'"description": {enc}',
                                    f'"description": {json.dumps(new, ensure_ascii=False)}')
    if want.get("title"):
        t = TITLE_RE.search(text)
        text = text[:t.start(1)] + html.escape(want["title"], quote=False) + text[t.end(1):]
    return text


def plan() -> tuple[list[tuple[str, str, str, str]], list[str], list[str]]:
    """(drift rows [(rel, field, current, expected)], missing files, unidentified dailies)."""
    expected, unidentified = expected_meta()
    drift, missing = [], []
    for rel, want in sorted(expected.items()):
        if want.get("description"):
            meta_description.require(want["description"], rel)
        if want.get("title"):
            meta_description.require_title(want["title"], rel)
        path = ROOT / rel
        if not path.exists():
            missing.append(rel)
            continue
        cur_title, cur_desc = _current(path.read_text(encoding="utf-8"))
        if want.get("description") and cur_desc != want["description"]:
            drift.append((rel, "description", cur_desc, want["description"]))
        if want.get("title") and cur_title != want["title"]:
            drift.append((rel, "title", cur_title, want["title"]))
    return drift, missing, unidentified


def main() -> int:
    write = "--write" in sys.argv
    expected, _ = expected_meta()
    drift, missing, unidentified = plan()
    print(f"PAGE META SYNC: {len(expected)} page(s) with a known source")
    for rel in missing:
        print(f"  MISSING {rel} (a source names a page that does not exist)")
    for rel in unidentified:
        print(f"  UNIDENTIFIED {rel} (no generator recognised; checked for bounds only)")
    for rel, field, current, want in drift:
        print(f"  {'WROTE' if write else 'DRIFT'} {rel} {field}: {len(current)} -> {len(want)} characters")
    if write:
        for rel in sorted({row[0] for row in drift}):
            path = ROOT / rel
            write_lf(path, apply(path.read_text(encoding="utf-8"), expected[rel]))
    if not expected:
        print("PAGE META SYNC: FAIL - zero pages have a known source")
        return 1
    if missing:
        return 1
    if drift and not write:
        print(f"PAGE META SYNC: {len(drift)} field(s) out of step; run with --write")
        return 1
    print(f"PAGE META SYNC: {'wrote ' + str(len(drift)) + ' field(s)' if write else 'in step'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
