#!/usr/bin/env python3
"""Render hand-authored editorial cluster articles into the three publications.

Why this exists separately from authority_v4_autopilot.py
---------------------------------------------------------
The autopilot composes pages from a pantry of reusable phrasing. That is the
right engine for daily cadence, but docs/strategy/publishing-cadence.md now says
the budget should buy depth rather than breadth: named sources, concrete
figures, comparison tables, FAQ blocks, and a self-contained answer inside the
first third of the page.

Two of those - a genuinely useful table and an FAQ block with FAQPage schema -
cannot be generated from a pantry, because the content of a table is the whole
value of a table. So the editorial substance for these pages is authored by hand
in content-bank/cluster-articles/*.json and this script only assembles it.

What this script guarantees by construction
-------------------------------------------
* Every outbound link is an affiliated destination that already exists in
  data/brands.json, and carries rel="sponsored nofollow" via affiliation.rel_attr.
* No page links to any domain outside the registry. These articles cite named
  bodies (a state licensing board, a civil surgeon, NARR) in prose without an
  outbound URL, because scripts/hostile_review.py locks the outbound domain set
  and an unregistered link would be a release failure, not a citation.
* Every page carries the publication disclosure, the "Affiliation disclosed:"
  marker, and the full professional-advice boundary sentence, so the sensitive
  topic rule in hostile_review.py is satisfied whether or not the topic trips it.
* Every page ships one Article node and one FAQPage node in a single JSON-LD
  @graph.

Idempotent: rerunning rewrites the same bytes and adds no duplicate ledger rows.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from affiliation import rel_attr  # noqa: E402
from byline import entity_for  # noqa: E402
from lib import meta_description, site_urls  # noqa: E402

CONTENT_DIR = ROOT / "content-bank/cluster-articles"
LEDGER = ROOT / "data/link-registry.json"
CLARITY = json.loads((ROOT / "data/clarity_projects.json").read_text(encoding="utf-8"))
PUBLICATIONS = {p["id"]: p for p in json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))}
BRANDS = {b["id"]: b for b in json.loads((ROOT / "data/brands.json").read_text(encoding="utf-8"))}

# Table styling used to live on the page, in an inline <style> block with the
# warm palette (#e5dac8, #f2ece1) hardcoded into it. That was correct when all
# three publications shared one byte-identical stylesheet; it is wrong now that
# they do not, because an inline block outranks the linked sheet and would drag
# the founder publication's old colours onto the Memphis and Professional sites.
#
# .ct-wrap, .ct and .ct caption are now defined in each site's own styles.css in
# terms of that site's design tokens, and .ct th/.ct td inherit the generic
# th/td rules there. scripts/install_editorial_chrome.py strips any surviving
# copy of the old inline block, so this staying empty is load-bearing.
TABLE_CSS = ""


def esc(value: str) -> str:
    return html.escape(str(value), quote=True)


def approved_link(brand_id: str, url: str) -> dict:
    """Fail loudly if a destination is not already registered.

    scripts/link_audit.py rejects an unregistered destination as
    destination_not_in_approved_set. Catching it here names the article instead
    of leaving a URL string in an audit report.
    """
    for item in BRANDS[brand_id].get("approved_links", []):
        if item.get("url", "").rstrip("/") == url.rstrip("/"):
            return item
    raise SystemExit(f"{brand_id}: destination is not in approved_links: {url}")


def render_table(table: dict) -> str:
    headers = "".join(f"<th>{esc(h)}</th>" for h in table["headers"])
    rows = []
    for row in table["rows"]:
        if len(row) != len(table["headers"]):
            raise SystemExit(f"table row width mismatch: {row}")
        if any(not str(cell).strip() for cell in row):
            # An empty cell is a blocking failure in the content pattern
            # contract: the review agent calls a half-filled table impossible
            # to cite. Better to refuse to render it.
            raise SystemExit(f"table row has an empty cell: {row}")
        rows.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>")
    return (
        f'<div class="ct-wrap"><table class="ct"><caption>{esc(table["caption"])}</caption>'
        f"<thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_sections(sections: list[dict]) -> str:
    out = []
    for section in sections:
        body = "".join(f"<p>{esc(p)}</p>" for p in section["paras"])
        out.append(f"<h2>{esc(section['h2'])}</h2>{body}")
    return "".join(out)


def render_list(block: dict) -> str:
    tag = "ol" if block.get("ordered") else "ul"
    items = "".join(f"<li>{esc(x)}</li>" for x in block["items"])
    intro = f"<p>{esc(block['intro'])}</p>" if block.get("intro") else ""
    return f"<h2>{esc(block['h2'])}</h2>{intro}<{tag}>{items}</{tag}>"


# Search Readiness checklist item d2: "Numbered steps for processes, tables for
# comparisons, bullet lists for options." A list snippet is extracted from a
# literal <ol>, never from prose, and on 25 Oct 2026 every how-to page in all
# three publications carried its procedure in paragraphs only: six pages on
# founderoperatorlibrary.com and memphisvendorlibrary.com failed the item live.
#
# The fix is NOT to renumber `checklist`. Those blocks are genuinely unordered
# -- "Send these details when you request a quote", "What to confirm in an
# individual tech check" -- and the same checklist item says a set of options or
# conditions belongs in a bullet list. Numbering them would have satisfied the
# check and mislabelled the content, which is the shape of defect this network's
# validators exist to refuse.
#
# So a how-to article carries its procedure as its own authored, ordered block,
# and `guard()` below refuses to render one without it.
def render_steps(block: dict) -> str:
    items = "".join(f"<li>{esc(x)}</li>" for x in block["items"])
    intro = f"<p>{esc(block['intro'])}</p>" if block.get("intro") else ""
    return f"<h2>{esc(block['h2'])}</h2>{intro}<ol>{items}</ol>"


# A page is a process page when its own visible heading or its <title> says so.
# Both are checked because the two can differ: item b1 capped <title> at 65
# characters on 25 Oct 2026, and two articles' seo_title lost the words "how to"
# while their h1 kept them. The page is still a how-to; the audit samples titles,
# the reader reads the h1, and both should find the steps.
PROCESS_RE = re.compile(r"\bhow to\b", re.I)
COMPARISON_RE = re.compile(r"\bvs\.?\b|\bversus\b", re.I)


def is_process(article: dict) -> bool:
    return bool(PROCESS_RE.search(article["title"])
                or PROCESS_RE.search(article.get("seo_title") or ""))


def is_comparison(article: dict) -> bool:
    return bool(COMPARISON_RE.search(article["title"])
                or COMPARISON_RE.search(article.get("seo_title") or ""))


# The recommendation_summary block: a one-sentence statement of what the page
# recommends, in the page's own words, placed above the first section where an
# answer engine reaches it.
#
# It used to be installed only by scripts/retrofit_recommendation_summary.js,
# after this generator had written the page. That made it fragile in one
# direction and harmful in the other. Fragile, because re-rendering an article
# silently dropped the block from all 46 cluster pages -- this generator writes
# the page whole. Harmful, because that script is not idempotent on a page which
# already has one: re-run on the published tree it relocated 63 blocks out of
# the opening and down into a later section, behind a table, and replaced their
# sentence with a weaker one lifted from further down the page.
#
# So the block is built here, from `answer`, which is the article's own recorded
# recommendation. `first_sentence` reproduces that script's rule exactly -- the
# first sentence boundary at or after 40 characters, with a leading label
# dropped -- so the bytes it emits for the 46 existing pages are the bytes
# already published, and the retrofit script has nothing left to do on them.
LABEL_PREFIX = re.compile(
    r"^(short answer|quick answer|direct answer|answer|bottom line|summary|tl;?dr)\s*[:\u2014-]\s*",
    re.I,
)
SENTENCE_RE = re.compile(r"^(.{40,}?[.!?])(\s|$)", re.S)


def first_sentence(text: str, max_len: int = 320) -> str:
    t = LABEL_PREFIX.sub("", str(text or "").strip())
    if not t:
        return ""
    m = SENTENCE_RE.match(t)
    s = m.group(1) if m else t
    return s if len(s) <= max_len else ""


def render_recommendation_summary(article: dict) -> str:
    rec = first_sentence(article["answer"])
    if not rec:
        # The retrofit script's rule: a block that announces a gap is worse than
        # no block. A sentence too long to carry is left out rather than cut.
        return ""
    return (
        '<div class="info-panel recommendation-summary" '
        'data-content-block="recommendation_summary" id="recommendation-summary">'
        "<h2>What this page recommends</h2>"
        f'<p class="recommendation-summary__answer">{esc(rec)}</p></div>'
    )


def render_faq(faq: list[dict]) -> str:
    blocks = "".join(f"<h3>{esc(x['q'])}</h3><p>{esc(x['a'])}</p>" for x in faq)
    return f'<section class="faq"><h2>Frequently asked questions</h2>{blocks}</section>'


def schema_graph(article: dict, pub: dict, url: str) -> str:
    graph = [
        {
            "@type": "Article",
            "headline": article["title"],
            "description": article["meta_description"],
            "datePublished": article["date"],
            "dateModified": article["date"],
            # author is the editorial company that writes the publication;
            # publisher is the publication itself. Both organisations, and the
            # author string is the same expression the visible footer byline
            # uses -- see scripts/byline.py.
            "author": {"@type": "Organization", "name": entity_for(pub["title"])},
            "publisher": {"@type": "Organization", "name": pub["title"]},
            "about": article["cluster"],
            "isAccessibleForFree": True,
            "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        },
        {
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": x["q"],
                    "acceptedAnswer": {"@type": "Answer", "text": x["a"]},
                }
                for x in article["faq"]
            ],
        },
    ]
    payload = {"@context": "https://schema.org", "@graph": graph}
    return (
        '<script type="application/ld+json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script>"
    )


def clarity_tag(domain: str) -> str:
    projects = {domain: CLARITY["projects"][domain]}
    return (
        '<script data-clarity-loader>(function(w,d,m){var h=(w.location.hostname||"")'
        '.toLowerCase().replace(/^www\\./,"");var id=m[h];if(!id)return;w.clarity=w.clarity||'
        'function(){(w.clarity.q=w.clarity.q||[]).push(arguments)};var s=d.createElement("script");'
        's.async=1;s.src="https://www.clarity.ms/tag/"+id;var f=d.getElementsByTagName("script")[0];'
        "f.parentNode.insertBefore(s,f)})(window,document,"
        + json.dumps(projects)
        + ")</script>"
    )


BOUNDARY = (
    "This page is not legal, medical, mental-health, immigration, financial, or "
    "professional advice."
)
AFFILIATION = (
    "<strong>Affiliation disclosed:</strong> this page is published by an affiliated "
    "authority network and includes one affiliated resource only where it directly "
    "supports the topic. It is not an independent award, ranking, review, or "
    "earned-media claim."
)


def render(article: dict) -> str:
    pub = PUBLICATIONS[article["publication"]]
    domain = pub["working_domain"]
    filename = f"{article['date']}-{article['slug']}.html"
    # Extensionless, from the shared helper: the .html form 308s to this one.
    url = site_urls.page_url(domain, f"daily/{filename}")
    approved_link(article["target_brand_id"], article["target_url"])
    meta_description.require(article["meta_description"], f"cluster article {article['id']}")

    sections = article["sections"]
    lead_sections = render_sections(sections[:1])
    rest_sections = render_sections(sections[1:])
    # The procedure sits directly under the opening section, above the table:
    # a reader looking for the steps should not have to scroll past a table and
    # a checklist, and a list snippet is extracted from the first <ol> found.
    steps_html = render_steps(article["steps"]) if article.get("steps") else ""
    summary_html = render_recommendation_summary(article)

    disclosure = " ".join(
        [pub["disclosure"], article["disclaimer"], BOUNDARY, AFFILIATION]
    )
    campaign_note = (
        f". Campaign: {esc(article['campaign_id'])}" if article.get("campaign_id") else ""
    )
    link_html = (
        f'<a href="{esc(article["target_url"])}"'
        f'{rel_attr(article["target_url"])}>{esc(article["anchor"])}</a>'
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(meta_description.require_title(article.get('seo_title') or article['title'], article['id']))}</title><meta name="description" content="{esc(article['meta_description'])}"><link rel="canonical" href="{esc(url)}"><link rel="stylesheet" href="../styles.css">{TABLE_CSS}{schema_graph(article, pub, url)}{clarity_tag(domain)}</head>
<body data-cluster-id="{esc(article['id'])}"><main class="page"><p><a href="../index.html">&larr; Home</a></p><article><h1>{esc(article['title'])}</h1><p class="dek"><strong>Short answer:</strong> {esc(article['answer'])}</p><p><em>Updated {article['date']}. Topic cluster: {esc(article['cluster'])}. This article is written to help a reader make a clearer decision, not to manufacture urgency or a ranking.</em></p>
{summary_html}{lead_sections}
{steps_html}
{render_table(article['table'])}
{render_list(article['checklist'])}
{rest_sections}
<h2>A related resource, and what it is not</h2><p>{esc(article['link_context'])} {link_html}. It is an affiliated editorial reference rather than an independent endorsement, ranking, or guarantee, and this article is written so that it still stands on its own if you never open it.</p>
{render_faq(article['faq'])}
<h2>Editorial and affiliation note</h2><p>{disclosure}</p><p class="meta">Authority Network cluster: {esc(article['cluster'])}{campaign_note}. Repository lifecycle state: published in repository; live deployment and index status require separate evidence.</p></article></main></body></html>
"""


# Mirrors scripts/hostile_review.py BANNED_PHRASES. Checked here so a bad phrase
# is named against the article that contains it rather than surfacing as a
# release failure over a rendered file. Note "cure " matches inside "secure ",
# which is exactly the kind of thing that is easier to catch at authoring time.
BANNED = [
    "guaranteed settlement", "guaranteed results", "guaranteed approval",
    "guaranteed success", "guaranteed healing", "best lawyer", "best dentist",
    "best civil surgeon", "best equine lawyer", "best in memphis without proof",
    "diagnose you", "cure ", "cures ", "fake review", "fake reviews",
    "official provider endorsement", "safe for everyone",
]
URL_RE = re.compile(r'https?://[^\s"\'<>]+')


def guard(article: dict, page: str) -> None:
    lower = page.lower()
    for phrase in BANNED:
        if phrase in lower:
            raise SystemExit(f"{article['slug']}: banned phrase {phrase!r}")
    allowed = {"schema.org", "clarity.ms", "www.clarity.ms"}
    allowed |= {p["working_domain"].lower() for p in PUBLICATIONS.values()}
    for brand in BRANDS.values():
        for d in (brand.get("domains") or [brand.get("domain", "")]):
            if d:
                allowed.add(str(d).strip().lower().lstrip(".").removeprefix("www."))
    for url in URL_RE.findall(page):
        host = url.split("/")[2].lower().removeprefix("www.")
        if host not in allowed:
            raise SystemExit(f"{article['slug']}: outbound domain not in registry: {host}")
    if "Affiliation disclosed:" not in page:
        raise SystemExit(f"{article['slug']}: affiliation disclosure missing")
    words = len(re.findall(r"\b[\w'-]+\b", re.sub(r"<[^>]+>", " ", page)))
    if words < 470:
        raise SystemExit(f"{article['slug']}: only {words} words; editorial target is 450+")
    # Search Readiness item d2, enforced where the page is built rather than
    # checked after the fact. A how-to article without an authored `steps` block
    # cannot be rendered, and the assertion is made against the rendered page so
    # that a steps block which somehow produced no <ol> also fails.
    if is_process(article) and "<ol>" not in page:
        # Two ways to satisfy this, and both are already in use: an authored
        # `steps` block, or a `checklist` marked "ordered": true where the
        # checklist genuinely IS the procedure. Nine of the nineteen how-to
        # articles took the second route before this guard existed; the ten that
        # failed the item on 25 Oct 2026 took neither.
        raise SystemExit(
            f"{article['slug']}: the title says 'how to' but the page renders no "
            f"ordered list (Search Readiness d2). Give the article a `steps` block, "
            f'or set "ordered": true on its checklist if that list is the procedure.'
        )
    if is_comparison(article) and "<table" not in page:
        raise SystemExit(
            f"{article['slug']}: the title is a comparison, so the page needs a table "
            f"(Search Readiness d2)"
        )


def ledger_row(article: dict, rel_path: str) -> dict:
    meta = approved_link(article["target_brand_id"], article["target_url"])
    brand = BRANDS[article["target_brand_id"]]
    return {
        "date": article["date"],
        "scheduled_content_date": article["date"],
        "release_date": article["date"],
        "source_path": rel_path,
        "source_publication": article["publication"],
        "target_brand_id": article["target_brand_id"],
        "target_domain": re.sub(r"^www\.", "", article["target_url"].split("/")[2]),
        "target_url": article["target_url"],
        "anchor": article["anchor"],
        "brand": brand.get("name", article["target_brand_id"]),
        "destination_type": meta.get("destination_type", ""),
        "product_id": meta.get("product_id", ""),
        "product_name": meta.get("product_name", ""),
        "target_route": meta.get("route", ""),
        "campaign_id": article.get("campaign_id", ""),
        "authority_page_contract_version": "v5",
        "link_type": "affiliated-editorial-backlink",
        "status": "published",
        "lifecycle_stage": "published_in_repository",
        "evidence": {
            "repository_rendered": True,
            "deployed": False,
            "live_verified": False,
            "discoverable": False,
            "indexed": False,
            "search_visibility_observed": False,
            "ai_cited": False,
        },
        "score": 88,
    }


def main() -> None:
    articles = []
    for source in sorted(CONTENT_DIR.glob("*.json")):
        articles.extend(json.loads(source.read_text(encoding="utf-8"))["articles"])
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    # Keyed on the page, not on (page, target_url). A cluster article renders
    # exactly one affiliated editorial link, so one page is one ledger row --
    # and the row's target_url is not this generator's to match on, because
    # scripts/rebalance_portfolio_links.py owns it after the fact and retargets
    # it to honour the portfolio quotas. With target_url in the key, every
    # re-render of an already-rebalanced page missed its own row and appended a
    # second one: regenerating all 46 articles on 25 Oct 2026 added 24 duplicate
    # rows, and would have added 24 more on the next run. The docstring above
    # has always claimed this script adds no duplicate ledger rows; now it does
    # not.
    existing = {r.get("source_path") for r in ledger}

    seen_slugs: set[str] = set()
    written, added = [], 0
    for article in articles:
        pub = PUBLICATIONS[article["publication"]]
        filename = f"{article['date']}-{article['slug']}.html"
        rel_path = f"{pub['folder']}/daily/{filename}"
        if rel_path in seen_slugs:
            raise SystemExit(f"duplicate output path: {rel_path}")
        seen_slugs.add(rel_path)
        page = render(article)
        guard(article, page)
        path = ROOT / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text(encoding="utf-8") != page:
            path.write_text(page, encoding="utf-8")
        written.append(rel_path)
        if rel_path not in existing:
            ledger.append(ledger_row(article, rel_path))
            existing.add(rel_path)
            added += 1

    LEDGER.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    by_pub: dict[str, int] = {}
    for article in articles:
        by_pub[article["publication"]] = by_pub.get(article["publication"], 0) + 1
    print(json.dumps({
        "status": "PASS",
        "articles": len(written),
        "by_publication": by_pub,
        "new_ledger_rows": added,
    }, indent=2))


if __name__ == "__main__":
    main()
