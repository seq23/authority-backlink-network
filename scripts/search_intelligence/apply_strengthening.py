#!/usr/bin/env python3
"""Write data/search_intelligence/strengthened_pages.json into the published pages.

For each entry, on its page:
  * <title> and meta description = the entry's query-first title and description
    (through sync_page_meta.apply, the one function that edits those two; and
    sync_page_meta's planner reads the same entries, so a later sync agrees);
  * a definition paragraph directly under the H1
    (<p class="definition" data-strengthened="definition">);
  * a section of question H2s, each answered in the paragraph under it, and a
    short list of specific facts (<section data-block="search-strengthening">),
    placed after the page's first section so it sits near the top;
  * a FAQPage JSON-LD built ONLY from those visible questions, and only when the
    entry says faq_schema: true -- which it may only say for a page that had no
    FAQPage of its own. A page keeps exactly one FAQPage either way.
and on each host's homepage, a "Most-read guides" list linking every
strengthened page by its title (<section data-block="search-strengthened-links">).

No outbound link is added: portfolio links stay governed by
data/portfolio-link-policy.json and rebalance_portfolio_links.py.

Idempotent: every block it writes is removed and re-rendered from the entry, so
the autopilot runs it on every pass (after the generators, before the editorial
chrome) and a rerun changes nothing. `--check` exits 1 if any page differs from
what --write would produce; the validator calls that.

    python3 scripts/search_intelligence/apply_strengthening.py [--write|--check]
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import measured as m  # noqa: E402
from sync_page_meta import apply as apply_meta  # noqa: E402
from lib import site_urls  # noqa: E402

LEDGER = m.SI / "strengthened_pages.json"
DEF_RE = re.compile(r'<p class="definition" data-strengthened="definition">.*?</p>', re.S)
SEC_RE = re.compile(r'<section data-block="search-strengthening">.*?</section>', re.S)
FAQ_RE = re.compile(r'<script type="application/ld\+json" data-strengthened="faq">.*?</script>', re.S)
HOME_RE = re.compile(r'<section data-block="search-strengthened-links">.*?</section>', re.S)
FAQ_TYPE_RE = re.compile(r'"@type"\s*:\s*"FAQPage"')
e = html.escape


def entries() -> list[dict]:
    return (m.read_json(LEDGER, {}) or {}).get("pages", [])


def strip_blocks(text: str) -> str:
    for rx in (DEF_RE, SEC_RE, FAQ_RE):
        text = rx.sub("", text)
    return text


def faq_node(entry: dict) -> dict:
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q["q"], "acceptedAnswer": {"@type": "Answer", "text": q["a"]}} for q in entry["questions"]]}


def render_page(text: str, entry: dict) -> str:
    text = apply_meta(strip_blocks(text), {"title": entry["title"], "description": entry["description"]})
    h1 = text.find("</h1>")
    if h1 < 0:
        raise ValueError(f"{entry['file']}: no </h1>")
    at = h1 + len("</h1>")
    text = text[:at] + f'<p class="definition" data-strengthened="definition">{e(entry["definition"])}</p>' + text[at:]
    qa = "".join(f"<h2>{e(q['q'])}</h2><p>{e(q['a'])}</p>" for q in entry["questions"])
    facts = "".join(f"<li>{e(f)}</li>" for f in entry["facts"])
    block = f'<section data-block="search-strengthening">{qa}<h2>The facts in one place</h2><ul>{facts}</ul></section>'
    first = text.find("</section>", at)
    cut = first + len("</section>") if first >= 0 else text.find("</main>")
    text = text[:cut] + block + text[cut:]
    if entry.get("faq_schema"):
        if FAQ_TYPE_RE.search(text):
            raise ValueError(f"{entry['file']}: faq_schema is true but the page already has a FAQPage; a page keeps one")
        script = f'<script type="application/ld+json" data-strengthened="faq">{json.dumps(faq_node(entry), ensure_ascii=False)}</script>'
        # Before the head's first script (the page's own Article JSON-LD), not
        # before </head>: the editorial chrome re-renders its managed block at
        # </head> on every run, and this must not move relative to it.
        head_end = text.find("</head>")
        first = text.find("<script", 0, head_end)
        at_s = first if first >= 0 else head_end
        text = text[:at_s] + script + text[at_s:]
    return text


def render_home(text: str, site: dict, pages: list[dict]) -> str:
    text = HOME_RE.sub("", text)
    if not pages:
        return text
    items = "".join(
        f'<li><a href="{e(site_urls.page_url(site["host"], Path(p["file"]).relative_to(site["folder"]).as_posix()))}">{e(p["title"])}</a></li>'
        for p in pages)
    block = (f'<section data-block="search-strengthened-links"><h2>Most-read guides</h2>'
             f'<p>The pages readers find most often in search, kept current.</p><ul>{items}</ul></section>')
    for anchor in ('<section data-nav="topic-index"', "</main>"):
        i = text.find(anchor)
        if i >= 0:
            return text[:i] + block + text[i:]
    raise ValueError(f"{site['folder']}/index.html: no place for the most-read list")


def planned() -> dict[Path, str]:
    """{path: text as --write would leave it}."""
    out: dict[Path, str] = {}
    all_entries = entries()
    for entry in all_entries:
        p = m.ROOT / entry["file"]
        out[p] = render_page(p.read_text(encoding="utf-8"), entry)
    for site in m.sites():
        home = m.ROOT / site["folder"] / "index.html"
        mine = [x for x in all_entries if x["host"] == site["host"]]
        out[home] = render_home(home.read_text(encoding="utf-8"), site, mine)
    return out


def main() -> int:
    write = "--write" in sys.argv
    changed = []
    for path, text in planned().items():
        if path.read_text(encoding="utf-8") != text:
            changed.append(path.relative_to(m.ROOT).as_posix())
            if write:
                with path.open("w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
    n = len(entries())
    print(f"apply_strengthening: {n} strengthened page(s) + {len(m.sites())} homepages; "
          f"{len(changed)} {'written' if write else 'differ from strengthened_pages.json'}")
    if not write and changed:
        for c in changed[:20]:
            print(f"  drift: {c}")
        return 1
    if n == 0:
        print("apply_strengthening: strengthened_pages.json lists no pages", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
