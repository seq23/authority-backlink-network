#!/usr/bin/env python3
"""No URL Search Console measures for these publications may 404.

A page Google shows in results, or reports on through URL Inspection, is the
page with the most to lose from disappearing. The publications have renamed and
retired pages before (see sites/founder-operator/_redirects), and a measured URL
that no longer resolves throws away exactly the impressions this loop exists to
grow. This checks, per host in data/search_intelligence/sites.json, every URL in

  gsc_truth.json        rows[].page and by_page[].page
  index_coverage.json   urls[].url
  target_query_set.json targets[].landing_route

resolves in the published tree the way Cloudflare Pages serves it (route.html,
route/index.html, or the .html form) or through a rule in the site's _redirects.

HARD_FAIL on any miss, and on zero URLs examined (Rule 0).

    python3 scripts/validators/validate_measured_urls_resolve.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "search_intelligence"))
import measured as m  # noqa: E402


def main() -> int:
    fail, checked = [], 0
    for site in m.sites():
        d = m.SI / site["host"]
        truth = m.read_json(d / "gsc_truth.json", {}) or {}
        cov = m.read_json(d / "index_coverage.json", {}) or {}
        tq = m.read_json(d / "target_query_set.json", {}) or {}
        urls = {r["page"] for r in truth.get("rows", [])} | {p["page"] for p in truth.get("by_page", [])} | \
            {u["url"] for u in cov.get("urls", [])}
        routes = {m.route_of(u) for u in urls} | {t["landing_route"] for t in tq.get("targets", []) if t.get("landing_route")}
        redirects = m.redirect_rules(site)
        for route in sorted(routes):
            checked += 1
            if m.file_for_route(site, route) is None and (route.rstrip("/") or "/") not in redirects:
                fail.append(f"{site['host']}{route}: measured by Search Console, no published file and no _redirects rule")
    if checked == 0:
        fail.append("rule0: no measured URL examined (data/search_intelligence/<host>/ is empty)")
    print(json.dumps({"validator": "measured_urls_resolve", "status": "FAIL" if fail else "PASS",
                      "hard_failures": len(fail), "routes_checked": checked, "failures": fail[:40]}, indent=2))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
