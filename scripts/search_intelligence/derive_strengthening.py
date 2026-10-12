#!/usr/bin/env python3
"""Derive a strengthening entry for every qualifying family that has none.

Why this exists (12 Oct 2026): the loop measured a newly qualifying family
(memphisvendorlibrary.com, the surprise-room-setup article, top_demand rank 4)
and the validator failed it as `not_strengthened`, because the only source of
strengthening was data/search_intelligence/strengthened_pages.json, written by
hand. A validator cannot demand an outcome no stage of the loop produces, so the
loop now produces it: this runs before apply_strengthening.py and appends one
entry per qualifying, unstrengthened page, built ONLY from what the page already
says -- nothing is authored.

A derived entry (`"derived_from_page": true`):
  * definition  the page's own short answer (its <p class="dek">), moved into
                the definition slot under the H1 (not copied: the dek paragraph
                becomes the definition, so the text appears once). With no dek,
                the page's meta description is used and nothing is moved.
  * questions   the page's own visible question headings (<h2>/<h3> ending in
                "?" with an answer paragraph), at least MIN_QUESTIONS. They are
                listed near the top as "Questions this page answers"; the
                answers stay where they are and are not repeated.
  * title/description  the page's current ones, recorded only: a derived entry
                never rewrites the <title> or meta description (sync_page_meta
                keeps owning them).
  * faq_schema  false: the page keeps the FAQPage it already has, or none.

A page that cannot supply MIN_QUESTIONS question headings is `underivable`:
build_search_plan.py records it with that reason in demand_families.json and the
strengthening ledger (a measured, non-blocking row), and the validator checks the
claim by recomputing derivable() so the status is never an escape hatch.

    python3 scripts/search_intelligence/derive_strengthening.py [--write|--check]
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measured as m  # noqa: E402

LEDGER = m.SI / "strengthened_pages.json"
MIN_QUESTIONS = 3
MAX_QUESTIONS = 5
DEK_RE = re.compile(r'</h1>\s*(<p class="dek">(.*?)</p>)', re.S)
QUESTION_RE = re.compile(r"<h([23])[^>]*>([^<]{5,200}\?)</h\1>\s*<p[^>]*>(.*?)</p>", re.S)
OWN_BLOCKS_RE = re.compile(r'<section data-block="(search-strengthening|search-strengthened-links)">.*?</section>', re.S)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
META_RE = re.compile(r'<meta name="description" content="([^"]*)"')


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def page_questions(text: str) -> list[dict]:
    """The page's own visible questions with their answers, in page order."""
    text = OWN_BLOCKS_RE.sub(" ", text)
    out, seen = [], set()
    for _, q, a in QUESTION_RE.findall(text):
        q, a = _text(q), _text(a)
        if a and q.casefold() not in seen:
            seen.add(q.casefold())
            out.append({"q": q, "a": a})
    return out


def derivable(path: Path | None) -> bool:
    if path is None or not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return len(page_questions(text)) >= MIN_QUESTIONS and bool(DEK_RE.search(text) or META_RE.search(text))


def derive_entry(host: str, route: str, file: str, family: str) -> dict | None:
    path = m.ROOT / file
    if not derivable(path):
        return None
    text = path.read_text(encoding="utf-8")
    dek = DEK_RE.search(text)
    title = TITLE_RE.search(text)
    meta = META_RE.search(text)
    entry = {"host": host, "route": route, "file": file, "derived_from_page": True, "derived_for_family": family,
             "title": _text(title.group(1)) if title else "", "description": html.unescape(meta.group(1)) if meta else "",
             "definition": _text(dek.group(2)) if dek else html.unescape(meta.group(1)),
             "questions": page_questions(text)[:MAX_QUESTIONS], "facts": [], "faq_schema": False}
    if dek:
        # The exact paragraph the definition replaces, so apply_strengthening.py
        # can move it (remove it, render it in the definition slot) idempotently.
        entry["definition_source"] = dek.group(1)
        entry["definition_html"] = dek.group(2)
    return entry


def missing() -> list[dict]:
    """Derived entries for every qualifying family whose page has no entry."""
    import build_search_plan as plan_mod  # noqa: PLC0415  (it imports this module)
    out = []
    for path, doc in plan_mod.plan().items():
        if not path.endswith("demand_families.json"):
            continue
        for fam in doc["families"]:
            if fam["qualifies"] and fam["status"] == "not_strengthened":
                entry = derive_entry(doc["host"], fam["page"], fam["file"], fam["family"])
                if entry:
                    out.append(entry)
    return out


def main() -> int:
    new = missing()
    for e in new:
        print(f"derive_strengthening: {e['host']}{e['route']} <- {len(e['questions'])} of its own questions"
              f"{' + its dek as the definition' if 'definition_source' in e else ' + its meta description as the definition'}")
    if "--write" in sys.argv and new:
        doc = m.read_json(LEDGER, {}) or {}
        doc.setdefault("pages", []).extend(new)
        with LEDGER.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"derive_strengthening: {len(new)} qualifying page(s) without an entry; "
          f"{'appended to' if '--write' in sys.argv else 'missing from'} strengthened_pages.json")
    return 1 if ("--check" in sys.argv and new) else 0


if __name__ == "__main__":
    sys.exit(main())
