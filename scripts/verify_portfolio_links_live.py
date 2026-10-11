#!/usr/bin/env python3
"""Post-deploy check: every portfolio anchor/target pair resolves live.

For each distinct (target URL, anchor) pair the three publications link
(read from the committed pages, or from the deployed pages with --from-live),
fetch the target and require:

  * HTTP 200, on the target's own host (a cross-host redirect is a failure);
  * a <title> whose text, with the site-name suffix removed, equals the anchor.

With --from-live it also fetches every published page that carries a portfolio
link from its live publication URL and requires the same followed link (no
nofollow/sponsored/ugc) to be present there -- proof the deploy shipped what
the repository says.

Network-bound, so it is not in the release profile; run it after the Pages
deploys finish:

    python3 scripts/verify_portfolio_links_live.py              # targets only
    python3 scripts/verify_portfolio_links_live.py --from-live  # + live pages
Exit 1 on any failure, and on zero pairs checked.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from affiliation import host_of, is_portfolio  # noqa: E402
from build_portfolio_deep_targets import clean_title  # noqa: E402
from lib import site_urls  # noqa: E402

A_RE = re.compile(r"<a\s+([^>]*?)>(.*?)</a>", re.I | re.S)
HREF_RE = re.compile(r'href="([^"]+)"', re.I)
REL_RE = re.compile(r'rel="([^"]*)"', re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
UA = "Mozilla/5.0 (compatible; AuthorityNetworkLinkCheck/1.0)"


def fetch(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, resp.geturl(), resp.read(600_000).decode("utf-8", "ignore")
    except Exception as exc:  # noqa: BLE001
        return getattr(exc, "code", 0), url, ""


def portfolio_links(text: str):
    for m in A_RE.finditer(text):
        href = HREF_RE.search(m.group(1))
        if href and is_portfolio(href.group(1)):
            rel = REL_RE.search(m.group(1))
            yield (href.group(1), html.unescape(TAG_RE.sub("", m.group(2))).strip(),
                   set((rel.group(1) if rel else "").lower().split()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-live", action="store_true")
    args = ap.parse_args()
    pubs = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
    pairs: set[tuple[str, str]] = set()
    pages: list[tuple[str, set]] = []
    for pub in pubs:
        folder = ROOT / pub["folder"]
        for path in sorted(folder.rglob("*.html")):
            found = list(portfolio_links(path.read_text(encoding="utf-8", errors="ignore")))
            if found:
                pairs.update((u, a) for u, a, _ in found)
                pages.append((site_urls.page_url(site_urls.domain_of(pub),
                                                 path.relative_to(folder).as_posix()),
                              {u for u, _, _ in found}))
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda p: fetch(p[0]), sorted(pairs)))
    for (url, anchor), (status, final, body) in zip(sorted(pairs), results):
        m = TITLE_RE.search(body)
        if status != 200 or host_of(final) != host_of(url):
            failures.append(f"{url}: HTTP {status} (final {final})")
        elif not m or clean_title(m.group(1)) != anchor:
            failures.append(f"{url}: title {clean_title(m.group(1)) if m else None!r} != anchor {anchor!r}")
    live_checked = 0
    if args.from_live:
        with ThreadPoolExecutor(max_workers=12) as pool:
            live = list(pool.map(lambda p: fetch(p[0]), pages))
        for (page_url, urls), (status, _final, body) in zip(pages, live):
            live_checked += 1
            if status != 200:
                failures.append(f"live page {page_url}: HTTP {status}")
                continue
            got = {u: t for u, _a, t in portfolio_links(body)}
            for u in urls:
                if u not in got:
                    failures.append(f"live page {page_url}: missing {u}")
                elif got[u] & {"nofollow", "sponsored", "ugc"}:
                    failures.append(f"live page {page_url}: {u} is not followed ({sorted(got[u])})")
    if not pairs:
        failures.append("rule0: zero portfolio anchor/target pairs found")
    print(json.dumps({"check": "portfolio_links_live", "status": "FAIL" if failures else "PASS",
                      "pairs_checked": len(pairs), "live_pages_checked": live_checked,
                      "failures": failures[:40]}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
