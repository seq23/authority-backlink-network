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

CONTENT_DIR = ROOT / "content-bank/cluster-articles"
LEDGER = ROOT / "data/link-registry.json"
CLARITY = json.loads((ROOT / "data/clarity_projects.json").read_text(encoding="utf-8"))
PUBLICATIONS = {p["id"]: p for p in json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))}
BRANDS = {b["id"]: b for b in json.loads((ROOT / "data/brands.json").read_text(encoding="utf-8"))}

# Table styling lives on the page rather than in the shared stylesheet: styles.css
# is a published asset for 514 existing pages and this batch should not change how
# any of them render.
TABLE_CSS = (
    "<style>"
    ".ct-wrap{overflow-x:auto;margin:22px 0}"
    ".ct{border-collapse:collapse;width:100%;font-size:15px;background:#fff}"
    ".ct caption{caption-side:top;text-align:left;font-weight:700;padding:0 0 8px;color:#445}"
    ".ct th,.ct td{border:1px solid #e5dac8;padding:9px 11px;text-align:left;vertical-align:top}"
    ".ct thead th{background:#f2ece1}"
    "</style>"
)


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
            "author": {"@type": "Organization", "name": pub["title"]},
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
    url = f"https://{domain}/daily/{filename}"
    approved_link(article["target_brand_id"], article["target_url"])

    sections = article["sections"]
    lead_sections = render_sections(sections[:1])
    rest_sections = render_sections(sections[1:])
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
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(article['title'])}</title><meta name="description" content="{esc(article['meta_description'])}"><link rel="canonical" href="{esc(url)}"><link rel="stylesheet" href="../styles.css">{TABLE_CSS}{schema_graph(article, pub, url)}{clarity_tag(domain)}</head>
<body data-cluster-id="{esc(article['id'])}"><main class="page"><p><a href="../index.html">&larr; Home</a></p><article><h1>{esc(article['title'])}</h1><p class="dek"><strong>Short answer:</strong> {esc(article['answer'])}</p><p><em>Updated {article['date']}. Topic cluster: {esc(article['cluster'])}. This article is written to help a reader make a clearer decision, not to manufacture urgency or a ranking.</em></p>
{lead_sections}
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
    existing = {(r.get("source_path"), r.get("target_url")) for r in ledger}

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
        key = (rel_path, article["target_url"])
        if key not in existing:
            ledger.append(ledger_row(article, rel_path))
            existing.add(key)
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
