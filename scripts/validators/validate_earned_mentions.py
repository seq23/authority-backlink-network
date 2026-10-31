#!/usr/bin/env python3
"""The earned-mention ledger is well formed, and the Wikidata gate refuses what it must.

Blocks (HARD_FAIL):
  * a ledger row missing url / outlet / brand_domain, a non-https URL, a duplicate URL,
    or a brand_domain that is not a brand in data/brands.json;
  * a row whose URL is on a portfolio or network domain -- that is not earned;
  * the gate itself, exercised on fixed cases (so this never checks zero items):
      - two URLs on the SAME outlet host     -> not eligible
      - a URL on the brand's own / network host counts for nothing
      - a row that last failed its weekly check counts for nothing
      - two distinct independent outlets     -> eligible
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import earned_mentions as em  # noqa: E402


def main() -> int:
    failures: list[str] = []
    data = em.load()
    owned = em.owned_hosts()
    brands = set(em.brand_names())
    seen: set[str] = set()
    for i, r in enumerate(data.get("mentions", [])):
        for k in ("url", "outlet", "brand_domain"):
            if not r.get(k):
                failures.append(f"row {i}: missing {k}")
        url = r.get("url", "")
        if not url.startswith("https://"):
            failures.append(f"row {i}: {url!r} is not https")
        if url in seen:
            failures.append(f"row {i}: duplicate {url}")
        seen.add(url)
        if em.host(url) in owned:
            failures.append(f"row {i}: {url} is on an owned or network domain; not earned")
        if r.get("brand_domain") not in brands:
            failures.append(f"row {i}: brand_domain {r.get('brand_domain')!r} is not in data/brands.json")

    d = "example-brand.test"
    cases = [
        ("same outlet twice", [{"url": "https://news.one/a", "brand_domain": d}, {"url": "https://news.one/b", "brand_domain": d}], False),
        ("own and network hosts", [{"url": f"https://{d}/press", "brand_domain": d},
                                   {"url": "https://memphisvendorlibrary.com/x", "brand_domain": d},
                                   {"url": "https://news.one/a", "brand_domain": d}], False),
        ("failed check", [{"url": "https://news.one/a", "brand_domain": d},
                          {"url": "https://news.two/b", "brand_domain": d, "last_check": {"ok": False}}], False),
        ("two independent outlets", [{"url": "https://news.one/a", "brand_domain": d},
                                     {"url": "https://news.two/b", "brand_domain": d}], True),
    ]
    for name, rows, want in cases:
        got = em.eligibility(rows, owned).get(d, {}).get("eligible", False)
        if got != want:
            failures.append(f"gate case {name!r}: eligible={got}, expected {want}")
    print(json.dumps({"validator": "earned_mentions", "status": "FAIL" if failures else "PASS",
                      "ledger_rows": len(data.get("mentions", [])), "gate_cases": len(cases),
                      "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
