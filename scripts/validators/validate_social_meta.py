#!/usr/bin/env python3
"""Every page carries a complete Open Graph + Twitter card, from its own data.

Why: on 10 Oct 2026 no page on the three publications had og:description,
og:image or twitter:card, so every shared link rendered as a bare URL.
lib/head_seo.py renders the set; this checks the published tree against the
same list:

  * each of REQUIRED_OG and REQUIRED_TWITTER exactly once and non-empty;
  * og:description == twitter:description == the page's meta description;
  * og:url == the canonical link (404.html, which has none, uses its own URL);
  * og:image == twitter:image == https://<this publication>/og.png, the file
    exists and is exactly og:image:width x og:image:height (1200x630);
  * og:site_name is this publication's title;
  * og:type is "website" on the homepage and 404, "article" exactly where the
    page's JSON-LD declares an Article-family node.

HARD_FAIL on zero pages examined.

    python3 scripts/validators/validate_social_meta.py
"""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lib import head_seo as hs  # noqa: E402


def main() -> int:
    failures, pages, articles = [], 0, 0
    image_ok: dict = {}
    for pub, folder, path, rel, text in hs.published_pages(ROOT):
        pages += 1
        domain = pub["working_domain"]
        is_home, is_404 = path == folder / "index.html", path == folder / "404.html"
        got = {}
        for key in hs.REQUIRED_OG:
            vals = hs.meta_values(text, "property", key)
            if len(vals) != 1 or not vals[0].strip():
                failures.append(f"{rel}: {key} appears {len(vals)} times (or empty), want 1")
            got[key] = vals[0] if vals else ""
        for key in hs.REQUIRED_TWITTER:
            vals = hs.meta_values(text, "name", key)
            if len(vals) != 1 or not vals[0].strip():
                failures.append(f"{rel}: {key} appears {len(vals)} times (or empty), want 1")
            got[key] = vals[0] if vals else ""
        desc = hs.meta_values(text, "name", "description")
        canon = hs.CANON_RE.search(text)
        want_url = canon.group(1) if canon else (f"https://{domain}/404.html" if is_404 else None)
        want_img = hs.og_image_url(domain)
        checks = [
            ("og:description", desc[0] if desc else None),
            ("twitter:description", desc[0] if desc else None),
            ("og:url", want_url),
            ("og:image", want_img), ("twitter:image", want_img),
            ("og:image:width", str(hs.OG_WIDTH)), ("og:image:height", str(hs.OG_HEIGHT)),
            ("og:site_name", pub["title"]), ("twitter:card", "summary_large_image"),
        ]
        for key, want in checks:
            if got.get(key) != want:
                failures.append(f"{rel}: {key} is {got.get(key)!r}, want {want!r}")
        want_type = "article" if (not is_home and not is_404 and hs.is_article(text)) else "website"
        articles += want_type == "article"
        if got.get("og:type") != want_type:
            failures.append(f"{rel}: og:type is {got.get('og:type')!r}, want {want_type!r}")
        if domain not in image_ok:
            img = folder / hs.OG_IMAGE
            try:
                image_ok[domain] = img.is_file() and hs.png_size(img) == (hs.OG_WIDTH, hs.OG_HEIGHT)
            except OSError:
                image_ok[domain] = False
            if not image_ok[domain]:
                failures.append(f"{pub['folder']}/{hs.OG_IMAGE} missing or not {hs.OG_WIDTH}x{hs.OG_HEIGHT}")
    if pages == 0 or articles == 0:
        failures.append(f"inert: {pages} pages, {articles} article pages examined")
    if failures:
        print("SOCIAL META: FAIL")
        for line in failures[:40]:
            print(f"  HARD_FAIL {line}")
        if len(failures) > 40:
            print(f"  ... and {len(failures) - 40} more")
        return 1
    print(f"  {pages} pages ({articles} articles) carry complete og:/twitter: tags pointing at "
          f"{len(image_ok)} per-publication 1200x630 cards")
    print("SOCIAL META: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
