#!/usr/bin/env python3
"""Every publication serves the IndexNow key, and the post-publish ping uses it.

IndexNow verifies ownership by fetching https://<host>/<key>.txt and comparing
its body to the submitted key. One key serves the whole repository
(data/indexnow_key.txt); scripts/post_publish_distribution.py submits each
publication's sitemap URLs after a successful publish and on a daily schedule.
That chain worked on 10 Oct 2026 (HTTP 200 on every batch). This keeps it
working:

  * data/indexnow_key.txt is a valid key (8-128 of [A-Za-z0-9-]);
  * every publication root has <key>.txt whose body is exactly the key;
  * every publication has a sitemap.xml with at least one URL to submit;
  * post_publish_distribution.py still reads that file, builds keyLocation as
    https://{domain}/{key}.txt and posts to api.indexnow.org;
  * the post-publish workflow still runs it.

HARD_FAIL on zero publications examined.

    python3 scripts/validators/validate_indexnow_key.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEY_RE = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def main() -> int:
    failures = []
    key_file = ROOT / "data/indexnow_key.txt"
    key = key_file.read_text(encoding="utf-8").strip() if key_file.is_file() else ""
    if not KEY_RE.match(key):
        failures.append("data/indexnow_key.txt missing or not a valid IndexNow key")
    pubs = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
    for pub in pubs:
        folder = ROOT / pub["folder"]
        served = folder / f"{key}.txt"
        if not served.is_file() or served.read_text(encoding="utf-8").strip() != key:
            failures.append(f"{pub['folder']}/{key}.txt missing or does not contain the key")
        sitemap = folder / "sitemap.xml"
        if not sitemap.is_file() or "<loc>" not in sitemap.read_text(encoding="utf-8"):
            failures.append(f"{pub['folder']}/sitemap.xml missing or empty -- nothing to submit")
    src = (ROOT / "scripts/post_publish_distribution.py").read_text(encoding="utf-8")
    for needle in ('"data/indexnow_key.txt"', "https://{domain}/{key}.txt",
                   "https://api.indexnow.org/indexnow", '"keyLocation"', '"urlList"'):
        if needle not in src:
            failures.append(f"scripts/post_publish_distribution.py no longer contains {needle}")
    wf = (ROOT / ".github/workflows/authority-post-publish-distribution.yml").read_text(encoding="utf-8")
    if "python3 scripts/post_publish_distribution.py" not in wf:
        failures.append("authority-post-publish-distribution.yml no longer runs post_publish_distribution.py")
    if not pubs:
        failures.append("zero publications examined -- this check went inert")
    if failures:
        print("INDEXNOW KEY: FAIL")
        for line in failures:
            print(f"  HARD_FAIL {line}")
        return 1
    print(f"  {len(pubs)} publications serve /{key[:8]}....txt and submit their sitemaps after publish")
    print("INDEXNOW KEY: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
