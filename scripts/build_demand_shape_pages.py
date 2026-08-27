#!/usr/bin/env python3
"""Build the pages whose SHAPE the citation measurements say can actually win.

Why these shapes
----------------
Across 65 grounded AI-answer observations in
local-guides-citation-velocity/data/signals/llm_citation_observations.json, the
shape of the query predicts whether an unbranded site gets a citation slot at all:

    cost / price        100% of slots went to unbranded sites   OPEN
    checklist / guide    76%                                    OPEN
    geo-modified         68%                                    OPEN
    comparison           64%                                    OPEN
    bare head term       44%                                    CLOSED

The daily generator aims at the head term, which is the one shape that is closed.
These pages aim at the four that are open.

What is different about them
----------------------------
1. Every factual claim carries a citation to a source outside this network,
   drawn from `data/external-sources.json`, where every URL was fetched and
   returned 200 before it was allowed in.
2. No invented figures. A cost page here explains what moves a price and where
   the authoritative number comes from. It does not print a dollar range this
   publication has no basis for, and it says so on the page.
3. Body content is authored per page rather than templated, because the
   measured defect on the existing daily pages is a 0.686 median Sorensen-Dice
   between page bodies. Only the chrome is shared, and the chrome is lifted
   from each publication's own index.html so it cannot drift.

    python3 scripts/build_demand_shape_pages.py --write
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLICATIONS = {p["id"]: p for p in json.loads(
    (ROOT / "data/publications.json").read_text(encoding="utf-8"))}
SOURCES = {s["id"]: s for s in json.loads(
    (ROOT / "data/external-sources.json").read_text(encoding="utf-8"))["sources"]}

DISCLAIMER = ("This page is informational. It is not legal, medical, mental-health, "
              "immigration, financial, or professional advice.")

HEADER_RE = re.compile(r"<header>.*?</header>", re.S | re.I)
FOOTER_RE = re.compile(r"<footer>.*?</footer>", re.S | re.I)
CLARITY_RE = re.compile(r"<script data-clarity-loader>.*?</script>", re.S | re.I)


def esc(text: str) -> str:
    return html.escape(text, quote=True)


# --------------------------------------------------------------------------
# Section renderers. Every one of them is responsible for never emitting an
# empty table cell or an empty anchor, both of which are blocking failures in
# validate_content_pattern_contract.js.
# --------------------------------------------------------------------------

def render_prose(section: dict) -> str:
    body = "".join(f"<p>{esc(p)}</p>" for p in section["paras"])
    return f'<section><h2>{esc(section["h2"])}</h2>{body}</section>'


def render_list(section: dict) -> str:
    tag = "ol" if section.get("ordered") else "ul"
    intro = f'<p>{esc(section["intro"])}</p>' if section.get("intro") else ""
    items = "".join(f"<li>{esc(i)}</li>" for i in section["items"])
    return (f'<section><h2>{esc(section["h2"])}</h2>{intro}'
            f'<{tag}>{items}</{tag}></section>')


def render_table(section: dict) -> str:
    intro = f'<p>{esc(section["intro"])}</p>' if section.get("intro") else ""
    head = "".join(f"<th>{esc(h)}</th>" for h in section["headers"])
    rows = ""
    for row in section["rows"]:
        if len(row) != len(section["headers"]):
            raise SystemExit(f"table row width mismatch in {section['h2']!r}: {row}")
        for cell in row:
            if not str(cell).strip():
                raise SystemExit(f"empty table cell in {section['h2']!r}: {row}")
        rows += "<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in row) + "</tr>"
    return (f'<section><h2>{esc(section["h2"])}</h2>{intro}'
            f'<div class="table-scroll"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{rows}</tbody></table></div></section>')


def render_sources(section: dict, lane: str) -> str:
    """The citations. This is the block that did not exist anywhere on these
    three publications before: an outbound link to something nobody in this
    network owns."""
    items = ""
    for entry in section["cites"]:
        source = SOURCES[entry["id"]]
        if lane not in source["lanes"]:
            raise SystemExit(
                f"source {entry['id']} is not registered for the {lane} lane")
        items += (
            f'<li><a href="{esc(source["url"])}" data-source="external-authority" '
            f'rel="noopener">{esc(source["title"])}</a> '
            f'&mdash; {esc(source["publisher"])}. '
            f'<span class="note">{esc(entry["used_for"])}</span></li>')
    return (f'<section data-block="external-sources"><h2>{esc(section["h2"])}</h2>'
            f'<p>{esc(section["intro"])}</p><ul>{items}</ul>'
            f'<p class="note">These are independent sources. They are not affiliated '
            f'with this publication and nothing was paid for their inclusion. '
            f'Requirements change; confirm the current text at the source before '
            f'relying on it.</p></section>')


def render_affiliated(section: dict) -> str:
    items = ""
    for url, anchor, note in section["links"]:
        items += (f'<li><a href="{esc(url)}" rel="nofollow sponsored">{esc(anchor)}</a>'
                  f' &mdash; {esc(note)} <span class="note">Affiliated / approved '
                  f'target.</span></li>')
    return (f'<section><h2>{esc(section["h2"])}</h2>'
            f'<p>{esc(section["intro"])}</p><ul>{items}</ul></section>')


def render_faq(section: dict) -> str:
    body = "".join(
        f'<div class="faq-item"><h3>{esc(q)}</h3><p>{esc(a)}</p></div>'
        for q, a in section["qas"])
    return (f'<section class="faq" data-faq="true"><h2>{esc(section.get("h2", "Questions people ask"))}</h2>'
            f'{body}</section>')


RENDERERS = {
    "prose": lambda s, lane: render_prose(s),
    "list": lambda s, lane: render_list(s),
    "table": lambda s, lane: render_table(s),
    "sources": render_sources,
    "affiliated": lambda s, lane: render_affiliated(s),
    "faq": lambda s, lane: render_faq(s),
}


def chrome(lane: str) -> tuple[str, str, str]:
    """Header, footer and analytics loader, taken from the publication's own
    index.html so these pages cannot drift away from the rest of the site."""
    index = (ROOT / PUBLICATIONS[lane]["folder"] / "index.html").read_text(encoding="utf-8")
    header = HEADER_RE.search(index)
    footer = FOOTER_RE.search(index)
    clarity = CLARITY_RE.search(index)
    if not header or not footer:
        raise SystemExit(f"cannot read chrome from {lane} index.html")
    return header.group(0), footer.group(0), (clarity.group(0) if clarity else "")


def build_page(page: dict) -> str:
    lane = page["lane"]
    pub = PUBLICATIONS[lane]
    domain = pub["working_domain"]
    url = f'https://{domain}/{page["slug"]}'
    header, footer, clarity = chrome(lane)

    faq_sections = [s for s in page["sections"] if s["type"] == "faq"]
    article_ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": page["h1"],
        "description": page["description"],
        "datePublished": page["published"],
        "dateModified": page["published"],
        "inLanguage": "en",
        "isAccessibleForFree": True,
        "publisher": {"@type": "Organization", "name": pub["title"],
                      "url": f"https://{domain}"},
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        # The citations are declared in the structured data too, not only in the
        # body, so a parser reading only the JSON-LD still sees what this page
        # stands on.
        "citation": [
            {"@type": "CreativeWork", "name": SOURCES[c["id"]]["title"],
             "url": SOURCES[c["id"]]["url"],
             "publisher": {"@type": "Organization",
                           "name": SOURCES[c["id"]]["publisher"]}}
            for s in page["sections"] if s["type"] == "sources" for c in s["cites"]
        ],
    }
    blocks = [f'<script type="application/ld+json">{json.dumps(article_ld, ensure_ascii=False)}</script>']
    if faq_sections:
        faq_ld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                for s in faq_sections for q, a in s["qas"]
            ],
        }
        blocks.append(f'<script type="application/ld+json">{json.dumps(faq_ld, ensure_ascii=False)}</script>')

    body = "".join(RENDERERS[s["type"]](s, lane) for s in page["sections"])

    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{esc(page["title"])} | {esc(pub["title"])}</title>\n'
        f'<meta name="description" content="{esc(page["description"])}">\n'
        f'<link rel="canonical" href="{esc(url)}">\n'
        '<link rel="stylesheet" href="/styles.css">\n'
        + "\n".join(blocks) + "\n"
        + clarity + "</head>\n<body>\n"
        + header + "\n<main>\n"
        f'<p class="eyebrow">{esc(page["eyebrow"])}</p>\n'
        f'<h1>{esc(page["h1"])}</h1>\n'
        f'<p class="dek">{esc(page["direct_answer"])}</p>\n'
        '<section class="card"><div class="info-panel recommendation-summary" '
        'data-content-block="recommendation_summary" id="recommendation-summary">'
        '<h2>What this page recommends</h2>'
        f'<p class="recommendation-summary__answer">{esc(page["recommends"])}</p></div>'
        f'<h2>Short answer</h2><p>{esc(page["direct_answer"])}</p></section>\n'
        + body
        + '<section><h2>Editorial boundary</h2>'
        f'<p>{esc(page["boundary"])}</p>'
        f'<p>{esc(DISCLAIMER)}</p></section>\n'
        '</main>\n' + footer + '\n</body></html>\n'
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="Rewrite pages that already exist, discarding any "
                             "canonical, breadcrumb or citation blocks that "
                             "build_site_navigation.py and "
                             "add_external_citations.py have since injected.")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "scripts"))
    from demand_shape_content import PAGES  # noqa: E402

    written, unchanged = [], []
    for page in PAGES:
        target = ROOT / PUBLICATIONS[page["lane"]]["folder"] / page["slug"]
        rendered = build_page(page)
        current = target.read_text(encoding="utf-8") if target.exists() else None
        # This is a scaffold generator, not the owner of these files. Once a page
        # exists, build_site_navigation.py has injected its canonical tag and
        # breadcrumbs into it, and rewriting from the template would silently
        # delete them. Existing pages are left alone unless --force says otherwise.
        if current is not None and not args.force:
            unchanged.append(page["slug"])
            continue
        if current == rendered:
            unchanged.append(page["slug"])
            continue
        if args.write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8", newline="\n")
        written.append(f'{page["lane"]}/{page["slug"]}')

    words = {}
    for page in PAGES:
        text = re.sub(r"<[^>]+>", " ", build_page(page))
        words[page["slug"]] = len(re.findall(r"\b[\w'-]+\b", text))

    print(f"DEMAND SHAPE PAGES: {len(PAGES)} page(s) defined")
    by_shape: dict[str, int] = {}
    for page in PAGES:
        by_shape[page["shape"]] = by_shape.get(page["shape"], 0) + 1
    for shape, count in sorted(by_shape.items()):
        print(f"  shape {shape:<12} {count}")
    print(f"  {'written' if args.write else 'would write'}: {len(written)}   "
          f"unchanged: {len(unchanged)}")
    for slug in written:
        print(f"    {slug}")
    thin = {k: v for k, v in words.items() if v < 450}
    if thin:
        print("  BELOW 450-WORD EDITORIAL TARGET:")
        for k, v in thin.items():
            print(f"    {k}: {v}")
    else:
        print(f"  all pages at or above the 450-word target "
              f"(min {min(words.values())}, max {max(words.values())})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
