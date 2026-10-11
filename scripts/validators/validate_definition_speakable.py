#!/usr/bin/env python3
"""Each homepage answers "what is this publication?" right under its H1.

Why: an answer engine quoting a publication needs one self-contained paragraph
that says what it is. On 10 Oct 2026 none of the three homepages had one; the
H1 was followed by a one-line dek. lib/head_seo.py now installs
<p id="publication-definition"> directly after the H1, built from
data/publications.json `definition` plus a closing sentence naming the
publication's own editorial company, and a WebPage SpeakableSpecification
points at it. This checks, per homepage:

  * the paragraph is the first element after </h1>, exactly once;
  * it begins "<Publication title> is " and runs 40-60 words;
  * it equals what the source data renders (no hand edit survives);
  * it names this publication's own editorial company;
  * the WebPage speakable cssSelector resolves to it -- every selector is an
    #id present exactly once on the page.

HARD_FAIL on zero homepages examined.

    python3 scripts/validators/validate_definition_speakable.py
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lib import head_seo as hs  # noqa: E402
from byline import entity_for, subsidiary_clause  # noqa: E402

AFTER_H1_RE = re.compile(r"</h1>\s*<p id=\"" + hs.DEFINITION_ID + r"\" class=\"definition\">(.*?)</p>", re.S | re.I)


def main() -> int:
    failures, homes = [], 0
    for pub, folder, path, rel, text in hs.published_pages(ROOT):
        if path != folder / "index.html":
            continue
        homes += 1
        entity = entity_for(pub["title"])
        m = AFTER_H1_RE.search(text)
        if not m:
            failures.append(f"{rel}: no #{hs.DEFINITION_ID} paragraph directly under the H1")
            continue
        para = html.unescape(m.group(1))
        n = hs.word_count(para)
        if text.count(f'id="{hs.DEFINITION_ID}"') != 1:
            failures.append(f"{rel}: #{hs.DEFINITION_ID} appears {text.count(f'id=\"{hs.DEFINITION_ID}\"')} times")
        if not para.startswith(pub["title"] + " is "):
            failures.append(f"{rel}: definition does not begin {pub['title']!r} is ...")
        if not hs.DEFINITION_MIN_WORDS <= n <= hs.DEFINITION_MAX_WORDS:
            failures.append(f"{rel}: definition is {n} words, want {hs.DEFINITION_MIN_WORDS}-{hs.DEFINITION_MAX_WORDS}")
        if entity not in para:
            failures.append(f"{rel}: definition does not name {entity!r}")
        if para != hs.definition_text(pub, entity, subsidiary_clause()):
            failures.append(f"{rel}: definition differs from data/publications.json -- re-run install_editorial_chrome.py")
        selectors = []
        for node in hs.jsonld_nodes(text):
            if "WebPage" in hs.node_types(node) and isinstance(node.get("speakable"), dict):
                selectors += node["speakable"].get("cssSelector") or []
        if hs.SPEAKABLE_SELECTOR not in selectors:
            failures.append(f"{rel}: no WebPage speakable cssSelector {hs.SPEAKABLE_SELECTOR!r}")
        for sel in selectors:
            if not sel.startswith("#") or text.count(f'id="{sel[1:]}"') != 1:
                failures.append(f"{rel}: speakable selector {sel!r} does not resolve to exactly one element")
    if homes == 0:
        failures.append("zero homepages examined -- this check went inert")
    if failures:
        print("DEFINITION + SPEAKABLE: FAIL")
        for line in failures:
            print(f"  HARD_FAIL {line}")
        return 1
    print(f"  {homes} homepages carry a {hs.DEFINITION_MIN_WORDS}-{hs.DEFINITION_MAX_WORDS} word "
          f"definition under the H1, covered by a resolving speakable selector")
    print("DEFINITION + SPEAKABLE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
