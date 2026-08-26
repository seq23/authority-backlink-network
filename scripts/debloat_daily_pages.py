#!/usr/bin/env python3
"""Rewrite generated daily pages so the page-specific part outweighs the mould.

`scripts/template_share.js` measured a 45.9% median template share against a 40%
ceiling. The 465 pages emitted by `authority_v4_autopilot.py` carried, on every
one of them, ten paragraphs cut from two sentence moulds, nine checklist items
cut from a third, five FAQ answers that were one fixed sentence repeated, and a
four-row decision table identical across the library. The topic names inside
those moulds were drawn by hash from the publication's whole cluster list, so
they did not even describe the page they were on.

This replaces that scaffolding with `scripts/lib/page_composer.py`, which builds
the body out of facts the repository already records for the page. It never
writes a claim that is not one of those recorded values, and it never invents a
number, a source, or a date.

What is preserved byte-for-byte
-------------------------------
  * the <head>, apart from the JSON-LD block, which gains a FAQPage node
  * the single outbound <a> tag, including every rel token on it
  * the Approval Prep product block, where the page has one
  * the editorial/affiliation note, which `scripts/hostile_review.py` requires
    verbatim ("affiliation disclosed", and the full professional-advice line)
  * the generated-at meta line

Usage: debloat_daily_pages.py [--write] [--limit N] [--offset N]
Prints a JSON receipt to stdout; diagnostics go to stderr.
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

from lib import page_composer as pc  # noqa: E402

MARKER = "Authority Network V4.2 programmatic editorial engine"
PANTRY = json.loads((ROOT / "content-bank/yearly-pantry.json").read_text(encoding="utf-8"))
PUB_BY_FOLDER = {p["folder"].split("/")[-1]: p for p in pc.publications()}

LINK_RE = re.compile(r'<a\s[^>]*href="https?://[^"]+"[^>]*>.*?</a>', re.I | re.S)
HREF_RE = re.compile(r'href="(https?://[^"]+)"', re.I)


def decompose_title(title: str, cluster: str, pub_key: str) -> dict | None:
    """Recover the four fields the title was built from.

    generate_page() builds `f"{cluster.title()}: {modifier.title()} {fmt.title()}
    {intent.title()}"`, so the fields are recoverable exactly rather than guessed.
    """
    pub = PANTRY["publications"][pub_key]
    prefix = cluster.title() + ": "
    if not title.startswith(prefix):
        return None
    rest = title[len(prefix):]
    mods = [x for x in pub["modifiers"] if rest.startswith(x.title() + " ")]
    if not mods:
        return None
    modifier = max(mods, key=len)
    rest = rest[len(modifier) + 1:]
    fmts = [x for x in pub["formats"] if rest.startswith(x.title() + " ")]
    if not fmts:
        return None
    fmt = max(fmts, key=len)
    rest = rest[len(fmt) + 1:]
    intents = [x for x in pub["intents"] if rest == x.title()]
    if not intents:
        return None
    return {"modifier": modifier, "format": fmt, "intent": intents[0]}


def extract(path: Path, source: str) -> dict | None:
    pub_key = path.relative_to(ROOT).parts[1]
    pub = PUB_BY_FOLDER.get(pub_key)
    if not pub:
        return None

    m_title = re.search(r"<title>(.*?)</title>", source, re.S)
    m_head = re.search(r"^(.*?)</head>", source, re.S)
    m_ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', source, re.S)
    m_h1 = re.search(r"<h1[^>]*>.*?</h1>", source, re.S)
    m_date = re.search(r"Last updated: (\d{4}-\d{2}-\d{2})", source)
    m_link = LINK_RE.search(source)
    if not all([m_title, m_head, m_ld, m_h1, m_date, m_link]):
        return None

    try:
        schema = json.loads(m_ld.group(1))
    except json.JSONDecodeError:
        return None
    article = schema.get("@graph", [schema])[0] if isinstance(schema, dict) else None
    if not isinstance(article, dict):
        return None
    cluster = article.get("about", "")
    audience = (article.get("audience") or {}).get("audienceType", "")
    if not cluster or not audience:
        return None

    title = html.unescape(m_title.group(1))
    fields = decompose_title(title, cluster, pub_key)
    if not fields:
        return None

    link_html = m_link.group(0)
    target_url = HREF_RE.search(link_html).group(1)
    anchor_text = html.unescape(re.sub(r"<[^>]+>", "", link_html)).strip()

    brand = pc.brand_for_url(target_url)
    approved = pc.approved_link_for_url(brand, target_url)
    campaign = pc.campaign_for_url(target_url)
    topics = [t for t in (approved.get("topics") or []) if t and t != "*"]

    # Blocks kept verbatim. Each is required by a validator or carries data the
    # composer cannot regenerate without asserting something new.
    product = ""
    m_prod = re.search(r"<h2>What you can create</h2>.*?(?=<h2>Useful citation</h2>)", source, re.S)
    if m_prod:
        product = m_prod.group(0).strip()
    m_note = re.search(r"<h2>Editorial note</h2>\s*<p>.*?</p>", source, re.S)
    m_meta = re.search(r'<p class="meta">.*?</p>', source, re.S)
    if not m_note or not m_meta:
        return None

    return {
        "path": path,
        "head": m_head.group(1),
        "ld_raw": m_ld.group(0),
        "article_schema": article,
        "h1": m_h1.group(0),
        "title": title,
        "cluster": cluster,
        "audience": audience,
        "date": m_date.group(1),
        "pub_title": pub["title"],
        "pub_domain": pub["working_domain"],
        "link_html": link_html,
        "anchor_text": anchor_text,
        "target_url": target_url,
        "brand_name": brand.get("name", ""),
        "brand_category": brand.get("category", ""),
        "brand_compliance": brand.get("compliance", ""),
        "link_policy": brand.get("link_policy", ""),
        "link_topics": topics,
        "destination_type": approved.get("destination_type", ""),
        "campaign_id": campaign.get("campaign_id", ""),
        "campaign_keywords": campaign.get("keywords", []) or [],
        "product_section_html": product,
        "editorial_note_html": m_note.group(0),
        "meta_line_html": m_meta.group(0),
        **fields,
    }


def rebuild(f: dict) -> str:
    body, items = pc.compose_body(f)
    graph = [f["article_schema"]]
    faq = pc.faq_schema(items)
    if faq:
        graph.append(faq)
    schema = {"@context": "https://schema.org", "@graph": graph}
    for node in graph:
        node.pop("@context", None)
    ld = ('<script type="application/ld+json">'
          + json.dumps(schema, ensure_ascii=False) + "</script>")
    head = f["head"].replace(f["ld_raw"], ld)
    return (head + "</head>\n"
            '<body><main class="page"><p><a href="../index.html">&larr; Home</a></p><article>'
            + f["h1"] + "\n" + body + "</article></main></body></html>\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    args = ap.parse_args()

    candidates = [p for p in sorted((ROOT / "sites").rglob("*.html"))
                  if MARKER in p.read_text(encoding="utf-8", errors="replace")]
    window = candidates[args.offset:]
    if args.limit:
        window = window[:args.limit]

    rewritten, skipped, unchanged = [], [], 0
    link_delta, rel_delta = [], []
    for path in window:
        source = path.read_text(encoding="utf-8")
        facts = extract(path, source)
        if not facts:
            skipped.append(path.relative_to(ROOT).as_posix())
            continue
        result = rebuild(facts)
        before_links = re.findall(r"<a\s[^>]*>", source)
        after_links = re.findall(r"<a\s[^>]*>", result)
        if sorted(before_links) != sorted(after_links):
            link_delta.append(path.relative_to(ROOT).as_posix())
            continue
        if MARKER not in result or "affiliation disclosed" not in result.lower():
            skipped.append(path.relative_to(ROOT).as_posix())
            continue
        if result == source:
            unchanged += 1
            continue
        if args.write:
            path.write_text(result, encoding="utf-8")
        rewritten.append(path.relative_to(ROOT).as_posix())

    receipt = {
        "status": "FAIL" if (skipped or link_delta or rel_delta) else "PASS",
        "candidates": len(candidates),
        "considered": len(window),
        "rewritten": len(rewritten),
        "already_current": unchanged,
        "skipped": skipped[:20],
        "skipped_count": len(skipped),
        "link_set_changed": link_delta[:20],
        "written": args.write,
    }
    print(json.dumps(receipt, indent=2))
    raise SystemExit(1 if receipt["status"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
