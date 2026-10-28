#!/usr/bin/env python3
"""Every <title> names its publication once; homepages say what the site is.

Why: on 11 Oct 2026 all three homepages published "<Publication> | <Publication>"
("Memphis Vendor Library | Memphis Vendor Library"), a title that tells a
searcher nothing. lib/head_seo.py now renders the homepage <title> from
data/publications.json as "<Publication>: <home_descriptor>" and
lib/meta_description.site_title() drops a suffix that would repeat the name.
This checks the published tree:

  * no page's <title> is "X | X" (suffix equal to prefix, case/space-insensitive);
  * each homepage <title> equals lib/meta_description.home_title(pub), is
    30-65 characters and does not contain the publication name twice;
  * each homepage's og:title, twitter:title and WebPage `name` equal its <title>.

HARD_FAIL on zero pages or fewer homepages than publications.

    python3 scripts/validators/validate_title_suffix.py
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
from lib import head_seo as hs  # noqa: E402
from lib import meta_description as md  # noqa: E402


def main() -> int:
    failures, pages, homes, pubs = [], 0, 0, set()
    for pub, folder, path, rel, text in hs.published_pages(ROOT):
        pages += 1
        pubs.add(pub["id"])
        m = hs.TITLE_RE.search(text)
        if not m:
            continue
        title = html.unescape(hs.plain(m.group(1)))
        if title.casefold().count(pub["title"].casefold()) != 1:
            failures.append(f"{rel}: <title> must name {pub['title']!r} exactly once")
        if md.doubled_suffix(title):
            failures.append(f"{rel}: <title> repeats its suffix: {title!r}")
        if path != folder / "index.html":
            continue
        homes += 1
        want = md.home_title(pub)
        if title != want:
            failures.append(f"{rel}: homepage <title> {title!r} != {want!r} (rerun npm run editorial:chrome)")
        if not md.HOME_TITLE_MIN <= len(title) <= md.HOME_TITLE_MAX:
            failures.append(f"{rel}: homepage <title> is {len(title)} chars, must be "
                            f"{md.HOME_TITLE_MIN}-{md.HOME_TITLE_MAX}")
        if title.casefold().count(pub["title"].casefold()) != 1:
            failures.append(f"{rel}: homepage <title> must name {pub['title']!r} exactly once")
        og = hs.meta_values(text, "property", "og:title")
        tw = hs.meta_values(text, "name", "twitter:title")
        names = [n.get("name") for n in hs.jsonld_nodes(text) if "WebPage" in hs.node_types(n)]
        for label, got in (("og:title", og), ("twitter:title", tw), ("WebPage name", names)):
            if [html.unescape(v) for v in got] != [title]:
                failures.append(f"{rel}: {label} {got!r} does not follow <title> {title!r}")
    if pages == 0 or homes == 0 or homes < len(pubs):
        print(f"HARD_FAIL title_suffix: inert ({pages} pages, {homes} homepages, {len(pubs)} publications)")
        return 1
    if failures:
        print(f"HARD_FAIL title_suffix: {len(failures)} finding(s)")
        for f in failures[:40]:
            print("  " + f)
        return 1
    print(f"PASS title_suffix: {pages} pages name their own site once; {homes} homepage titles in "
          f"{md.HOME_TITLE_MIN}-{md.HOME_TITLE_MAX} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
