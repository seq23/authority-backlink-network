#!/usr/bin/env python3
"""Every publication serves its icon set and manifest, and every page links them.

Why: on 10 Oct 2026 https://<each publication>/favicon.ico answered 404 -- only
favicon.svg existed -- and there was no apple-touch-icon and no web manifest.
scripts/build_brand_assets.py now writes the files and
scripts/install_editorial_chrome.py (via lib/head_seo.py) links them on every
page. This fails if a file goes missing, is the wrong size, or any page loses a
link. HARD_FAIL on zero pages examined.

    python3 scripts/validators/validate_favicon_manifest.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lib import head_seo as hs  # noqa: E402


def main() -> int:
    failures, pages, seen_pubs = [], 0, {}
    for pub, folder, path, rel, text in hs.published_pages(ROOT):
        pages += 1
        seen_pubs[pub["id"]] = (pub, folder)
        for rel_attr, href in hs.REQUIRED_ICON_LINKS:
            n = len(re.findall(r'<link\s+rel="' + re.escape(rel_attr) + r'"\s+href="' + re.escape(href) + r'"', text))
            if n != 1:
                failures.append(f"{rel}: <link rel=\"{rel_attr}\" href=\"{href}\"> appears {n} times, want 1")
    for pid, (pub, folder) in seen_pubs.items():
        for name in hs.REQUIRED_ASSETS:
            if not (folder / name).is_file():
                failures.append(f"{pub['folder']}/{name} missing")
        try:
            sizes = hs.ico_sizes(folder / hs.FAVICON_ICO)
            want = {(n, n) for n in hs.ICO_SIZES}
            if not want <= sizes:
                failures.append(f"{pub['folder']}/favicon.ico: sizes {sorted(sizes)}; want an ICO with {sorted(want)}")
            touch = hs.png_size(folder / hs.APPLE_TOUCH_ICON)
            if touch != (hs.APPLE_TOUCH_SIZE,) * 2:
                failures.append(f"{pub['folder']}/apple-touch-icon.png is {touch}")
            manifest = json.loads((folder / hs.MANIFEST).read_text(encoding="utf-8"))
            if manifest.get("name") != pub["title"]:
                failures.append(f"{pub['folder']}/site.webmanifest names {manifest.get('name')!r}, not {pub['title']!r}")
            for icon in manifest.get("icons", []):
                f = folder / icon["src"].lstrip("/")
                w = int(icon["sizes"].split("x")[0])
                if not f.is_file() or hs.png_size(f) != (w, w):
                    failures.append(f"{pub['folder']}/site.webmanifest icon {icon['src']} missing or not {icon['sizes']}")
            if not manifest.get("icons"):
                failures.append(f"{pub['folder']}/site.webmanifest lists no icons")
        except (OSError, ValueError, KeyError) as exc:
            failures.append(f"{pub['folder']}: icon set unreadable: {exc}")
    if pages == 0 or not seen_pubs:
        failures.append("zero pages examined -- this check went inert")
    if failures:
        print("FAVICON + MANIFEST: FAIL")
        for line in failures[:40]:
            print(f"  HARD_FAIL {line}")
        if len(failures) > 40:
            print(f"  ... and {len(failures) - 40} more")
        return 1
    print(f"  {pages} pages link favicon.ico, favicon.svg, apple-touch-icon and the manifest; "
          f"{len(seen_pubs)} publications serve all {len(hs.REQUIRED_ASSETS)} files at the right sizes")
    print("FAVICON + MANIFEST: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
