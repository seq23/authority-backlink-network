#!/usr/bin/env python3
"""Portfolio links are followed, contextual, spread out and pointed at real pages.

Owner decision, 11 Oct 2026 (data/portfolio-link-policy.json). This blocks on:

  rel     a link to an owner portfolio domain carrying nofollow, sponsored or
          ugc; or a link that must not pass credit -- a client brand in
          data/brands.json that is not on the portfolio list, or a tagged
          affiliate URL -- missing rel="sponsored nofollow";
  place   a portfolio link inside <footer>, <nav>, <header> or an <aside>:
          those are sitewide chrome, and the links belong in the article body;
  caps    a target domain over `max_target_domain_share_of_site_portfolio_links`
          of one site's portfolio links, or one URL over
          `max_links_per_target_url_per_site` links on one site;
  target  a portfolio link whose URL is not in data/portfolio-deep-targets.json
          (pages that answered 200 when catalogued), or whose anchor text is not
          that page's title;
  wiring  the autopilot no longer choosing through
          rebalance_portfolio_links.choose_for_new_page, or the autopilot
          workflow no longer running the rebalancer before the chrome installer
          -- output can be clean the day the wiring goes and over the caps a
          fortnight later.

Rule 0: zero pages, or zero portfolio links, is a FAIL, not a clean pass.
"""
from __future__ import annotations

import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from affiliation import host_of, is_portfolio, link_policy, nofollow_required  # noqa: E402

A_RE = re.compile(r"<a\s+([^>]*?)>(.*?)</a>", re.I | re.S)
HREF_RE = re.compile(r'href="([^"]+)"', re.I)
REL_RE = re.compile(r'rel="([^"]*)"', re.I)
CHROME_RE = re.compile(r"<(footer|nav|header|aside)\b[^>]*>.*?</\1>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
WITHHOLD = {"nofollow", "sponsored", "ugc"}


def norm_url(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.strip()).rstrip("/").lower()


def main() -> int:
    failures: list[str] = []
    policy = link_policy()
    share = float(policy["caps"]["max_target_domain_share_of_site_portfolio_links"])
    per_url = int(policy["caps"]["max_links_per_target_url_per_site"])
    catalogue = {norm_url(t["url"]): t for rows in json.loads(
        (ROOT / "data/portfolio-deep-targets.json").read_text(encoding="utf-8"))["targets"].values()
        for t in rows}

    pages = links = 0
    report = {}
    for site in sorted(p for p in (ROOT / "sites").iterdir() if p.is_dir()):
        by_domain: Counter = Counter()
        by_url: Counter = Counter()
        for path in sorted(site.rglob("*.html")):
            rel = path.relative_to(ROOT).as_posix()
            if "/agency/" in rel:
                continue
            pages += 1
            text = path.read_text(encoding="utf-8", errors="ignore")
            for chrome in CHROME_RE.finditer(text):
                for m in A_RE.finditer(chrome.group(0)):
                    href = HREF_RE.search(m.group(1))
                    if href and is_portfolio(href.group(1)):
                        failures.append(f"place {rel}: portfolio link inside <{chrome.group(1)}>: {href.group(1)}")
            for m in A_RE.finditer(text):
                href = HREF_RE.search(m.group(1))
                if not href or not href.group(1).startswith("http"):
                    continue
                url = href.group(1)
                rel_m = REL_RE.search(m.group(1))
                tokens = {t.lower() for t in rel_m.group(1).split()} if rel_m else set()
                if nofollow_required(url):
                    if not {"sponsored", "nofollow"} <= tokens:
                        failures.append(f"rel {rel}: must carry rel=\"sponsored nofollow\": {url}")
                    continue
                if not is_portfolio(url):
                    continue
                links += 1
                if tokens & WITHHOLD:
                    failures.append(f"rel {rel}: portfolio link carries {sorted(tokens & WITHHOLD)}: {url}")
                by_domain[host_of(url)] += 1
                by_url[norm_url(url)] += 1
                target = catalogue.get(norm_url(url))
                anchor = html.unescape(TAG_RE.sub("", m.group(2))).strip()
                if target is None:
                    failures.append(f"target {rel}: not a catalogued deep target: {url}")
                elif anchor != target["title"]:
                    failures.append(f"target {rel}: anchor {anchor!r} is not the page title {target['title']!r}")
        total = sum(by_domain.values())
        for domain, n in by_domain.items():
            if n > share * total + 1e-9:
                failures.append(f"caps {site.name}: {domain} has {n} of {total} portfolio links "
                                f"({n / total:.0%} > {share:.0%})")
        for url, n in by_url.items():
            if n > per_url:
                failures.append(f"caps {site.name}: {url} linked {n} times (> {per_url})")
        report[site.name] = {"portfolio_links": total,
                             "max_domain_share": round(max(by_domain.values()) / total, 3) if total else None,
                             "by_domain": dict(by_domain.most_common())}

    autopilot = (ROOT / "scripts/authority_v4_autopilot.py").read_text(encoding="utf-8")
    if "rebalance.choose_for_new_page(" not in autopilot:
        failures.append("wiring scripts/authority_v4_autopilot.py no longer chooses portfolio links "
                        "through rebalance_portfolio_links.choose_for_new_page")
    wf = (ROOT / ".github/workflows/authority-v4-autopilot.yml").read_text(encoding="utf-8")
    i, j = wf.find("rebalance_portfolio_links.py --write"), wf.find("install_editorial_chrome.py --write")
    if i < 0 or j < 0 or i > j:
        failures.append("wiring .github/workflows/authority-v4-autopilot.yml must run "
                        "rebalance_portfolio_links.py --write before install_editorial_chrome.py")
    if not pages:
        failures.append("rule0: scanned zero pages")
    if not links:
        failures.append("rule0: found zero portfolio links; the selector is broken, not the corpus clean")

    print(json.dumps({"validator": "portfolio_link_policy", "status": "FAIL" if failures else "PASS",
                      "hard_failures": len(failures), "pages_scanned": pages, "portfolio_links": links,
                      "sites": report, "failures": failures[:40]}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
