#!/usr/bin/env python3
"""JSON-LD types per page kind, and each publication's identity in every node.

Why: on 10 Oct 2026 the homepages carried Article + Organization only -- no
WebSite node naming the publication, and the editorial pages (masthead,
standards, corrections, contributors) had no BreadcrumbList.
lib/head_seo.py adds them; this checks the published tree:

  every page      all JSON-LD parses; one WebSite node named for THIS
                  publication at https://<its domain>/, published by its own
                  editorial company (byline.entity_for) with no
                  parentOrganization
  homepage        a WebPage with a SpeakableSpecification
  inner pages     a BreadcrumbList (404.html, noindex, exempt)
  og:type article an Article-family node (the Article nodes are kept as-is)
  FAQPage         only where the page already has the Q&A: every Question name
                  must appear in the page's visible text, so a FAQPage can
                  never be invented
  identity        no JSON-LD on a page names another publication's editorial
                  company; every author node names this publication's own

Three more, added 25 Oct 2026 from the Search Readiness Checklist, which reads
the published pages the same way an answer engine does -- first matching node
wins -- and found all three failing on every page of all three publications:

  c1  EVERY Organization node naming this publication or its editorial company
      carries name, url, logo and sameAs. The checklist reads the FIRST
      Organization on the page, which on an article page is the publisher node
      inside the article's own JSON-LD, not the one in the managed head block,
      so checking only the head block would have passed a failing page.
  c2  a WebPage node on every page, not only the homepage
  d4  a page whose JSON-LD states a date shows that date to a reader

HARD_FAIL on zero pages examined.

    python3 scripts/validators/validate_jsonld_types.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lib import head_seo as hs  # noqa: E402
from byline import entity_for  # noqa: E402

BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.S | re.I)
SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.S | re.I)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def main() -> int:
    pubs = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
    entities = {p["id"]: entity_for(p["title"]) for p in pubs}
    failures, pages, faq_pages, crumbs = [], 0, 0, 0
    for pub, folder, path, rel, text in hs.published_pages(ROOT):
        pages += 1
        domain, mine = pub["working_domain"], entities[pub["id"]]
        is_home, is_404 = path == folder / "index.html", path == folder / "404.html"
        for raw in hs.LDJSON_ANY_RE.findall(text):
            try:
                json.loads(raw)
            except json.JSONDecodeError as exc:
                failures.append(f"{rel}: JSON-LD does not parse: {exc}")
        nodes = hs.jsonld_nodes(text)
        types = hs.types_on(text)
        sites = [n for n in nodes if "WebSite" in hs.node_types(n) and n.get("@id") == f"https://{domain}/#website"]
        if len(sites) != 1 or sites[0].get("name") != pub["title"] or sites[0].get("url") != hs.site_url(domain):
            failures.append(f"{rel}: want one WebSite node named {pub['title']!r} at {hs.site_url(domain)}")
        publishers = [n for n in nodes if n.get("@id") == hs.publisher_id(domain) and n.get("name")]
        if not publishers or any(n.get("name") != mine or "parentOrganization" in n for n in publishers):
            failures.append(f"{rel}: site-graph publisher is not {mine!r} standing alone (no parentOrganization)")
        # c1: every Organization node that claims to BE this publication or its
        # editorial company must be identifiable. A third party's Organization
        # node is left out: this repository does not assert facts about other
        # companies' identity.
        ours = {mine.casefold(), pub["title"].casefold()}
        for n in nodes:
            if "Organization" not in hs.node_types(n):
                continue
            if str(n.get("name", "")).casefold() not in ours:
                continue
            thin = [k for k in ("name", *hs.organization_identity(domain)) if not n.get(k)]
            if thin:
                failures.append(f"{rel}: Organization {n.get('name')!r} lacks {', '.join(thin)}")
        # c2: a WebPage node on every page.
        if "WebPage" not in types:
            failures.append(f"{rel}: no WebPage node")
        # d4: a stated date is a visible date.
        dates = hs.schema_dates(text)
        if dates and not (any(d in hs.visible_text(text) for d in dates)
                          or any(f'datetime="{d}' in text for d in dates)):
            failures.append(f"{rel}: JSON-LD states {dates[0]} and the page shows no date")
        if is_home:
            speak = [n for n in nodes if "WebPage" in hs.node_types(n) and n.get("speakable")]
            if not speak:
                failures.append(f"{rel}: homepage has no WebPage with a SpeakableSpecification")
        elif not is_404:
            if "BreadcrumbList" not in types:
                failures.append(f"{rel}: inner page has no BreadcrumbList")
            else:
                crumbs += 1
        og_type = hs.meta_values(text, "property", "og:type")
        if og_type == ["article"] and not (types & hs.BYLINED_TYPES):
            failures.append(f"{rel}: og:type article but no Article-family JSON-LD node")
        if "FAQPage" in types:
            faq_pages += 1
            body = BODY_RE.search(text)
            visible = norm(hs.plain(SCRIPT_RE.sub(" ", body.group(1) if body else "")))
            questions = [n for n in nodes if "Question" in hs.node_types(n)]
            if not questions:
                failures.append(f"{rel}: FAQPage with no Question nodes")
            for q in questions:
                if norm(str(q.get("name", ""))) not in visible or not q.get("acceptedAnswer"):
                    failures.append(f"{rel}: FAQPage question not on the page (invented?) or unanswered: {str(q.get('name'))[:80]!r}")
        for n in nodes:
            if hs.node_types(n) & hs.BYLINED_TYPES:
                author = n.get("author")
                for a in (author if isinstance(author, list) else [author]):
                    if isinstance(a, dict) and a.get("name") != mine:
                        failures.append(f"{rel}: author {a.get('name')!r}, want {mine!r}")
        ld_text = " ".join(hs.LDJSON_ANY_RE.findall(text))
        for pid, other in entities.items():
            if pid != pub["id"] and other in ld_text:
                failures.append(f"{rel}: JSON-LD names another publication's editorial company {other!r}")
    if pages == 0 or crumbs == 0 or faq_pages == 0:
        failures.append(f"inert: {pages} pages, {crumbs} breadcrumb pages, {faq_pages} FAQ pages examined")
    if failures:
        print("JSON-LD TYPES: FAIL")
        for line in failures[:40]:
            print(f"  HARD_FAIL {line}")
        if len(failures) > 40:
            print(f"  ... and {len(failures) - 40} more")
        return 1
    print(f"  {pages} pages: WebSite + own publisher (name, url, logo, sameAs) + WebPage "
          f"everywhere, every stated date shown, {crumbs} inner pages with BreadcrumbList, "
          f"{faq_pages} FAQPage nodes all backed by on-page Q&A")
    print("JSON-LD TYPES: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
