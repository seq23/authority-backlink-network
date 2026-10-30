#!/usr/bin/env python3
"""An owner exception to the publishing freeze admits exactly what she approved.

30 Oct 2026, owner: "Yes, publish 3 now" -- three Glory By Us starter articles
on Professional Resource Library, published although Search Console shows no
measured query for them yet. The freeze (11 Oct 2026) stays exactly as strict for
every other brand and article. The exception is data, not a looser check: a
named, dated entry in data/search_intelligence/publishing_freeze.json
`owner_exceptions` that measured.freeze_violations reads.

This pins, against the real tree:
  1. The Glory By Us entry exists with its brand, host, date, the owner's words
     and max_articles == 3, and exactly three published pages claim it; each
     links glorybyus.com, carries an outside Sources block, and matches none
     of the brand's prohibited_claim_patterns.
  2. The real tree has no freeze violation.
And proves negatively, with the real pages in memory:
  3. A fourth article claiming the exception fails.
  4. Another brand's page claiming it fails; a page not linking glorybyus.com
     fails; a page on another host fails; a page dated before the decision fails.
  5. The same pages with the entry removed, or naming an unknown id, fail.
  6. An entry missing the owner's words or with a non-integer cap fails.
  7. An unmeasured page with no exception still fails (the freeze is intact).
  8. The validator calls freeze_violations, and the autopilot never reads
     owner_exceptions (an exception never lets the generator publish).
Fails on zero exception pages examined.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "search_intelligence"))
import measured as m  # noqa: E402

EXC_ID = "glory-by-us-starters-2026-10-30"
fails: list[str] = []

fz = m.freeze()
released = (m.read_json(m.HELD_PATH, {}) or {}).get("released", [])
exc = next((e for e in fz.get("owner_exceptions", []) if e.get("id") == EXC_ID), None)

# 1. The entry and its pages.
if exc is None:
    fails.append(f"publishing_freeze.json has no owner exception {EXC_ID}")
    exc = {}
expect = {"brand_id": "glory-by-us", "target_domain": "glorybyus.com", "host": "professionalresourcelibrary.com",
          "max_articles": 3, "decided": "2026-10-30", "owner_words": "Yes, publish 3 now"}
for k, v in expect.items():
    if exc.get(k) != v:
        fails.append(f"owner exception {EXC_ID}: {k} is {exc.get(k)!r}, expected {v!r}")
if len(fz.get("owner_exceptions", [])) != 1:
    fails.append(f"exactly one owner exception is approved; found {len(fz.get('owner_exceptions', []))}")

claimed = [r for r in released if r.get("owner_exception") == EXC_ID]
if len(claimed) != 3:
    fails.append(f"{len(claimed)} released page(s) claim {EXC_ID}; the owner approved 3")
brand = next(b for b in json.loads((ROOT / "data/brands.json").read_text(encoding="utf-8")) if b["id"] == "glory-by-us")
claims = [re.compile(p) for p in brand["prohibited_claim_patterns"]]
pages = []
for r in claimed:
    path = ROOT / r["path"]
    if not path.is_file():
        fails.append(f"{r['path']}: claimed by the exception but not on disk")
        continue
    html = path.read_text(encoding="utf-8")
    pages.append((r["path"], r["host"], html))
    if not re.search(r'href="https://glorybyus\.com[/"]', html):
        fails.append(f"{r['path']}: does not link glorybyus.com")
    if 'data-block="external-citations"' not in html or 'data-source="external-authority"' not in html:
        fails.append(f"{r['path']}: no outside Sources block")
    for p in claims:
        if p.search(html.lower()):
            fails.append(f"{r['path']}: prohibited claim {p.pattern}")
if not pages:
    fails.append("rule0: no owner-exception page examined")

# 2. The real tree.
real_daily = [(p.relative_to(ROOT).as_posix(), s["host"], p.read_text(encoding="utf-8", errors="ignore"))
              for s in m.sites() for p in sorted((ROOT / s["folder"] / "daily").glob("*.html"))]
real = m.freeze_violations(fz, released, real_daily)
if real:
    fails.append(f"real tree breaks the freeze: {real[:3]}")


def must_fail(label: str, fz_: dict, released_: list[dict], pages_: list[tuple[str, str, str]], needle: str) -> None:
    got = m.freeze_violations(fz_, released_, pages_)
    if not any(needle in g for g in got):
        fails.append(f"negative proof '{label}' did not fail as expected ({needle!r}); got {got[:2]}")


if pages:
    path0, host0, html0 = pages[0]
    rec0 = next(r for r in claimed if r["path"] == path0)

    # 3. A fourth article.
    fourth = path0.replace("2026-10-30-", "2026-10-30-fourth-")
    must_fail("fourth article", fz, released + [{**rec0, "path": fourth}], pages + [(fourth, host0, html0)], "allows 3 article")

    # 4. Another brand / no link / another host / before the decision.
    other = path0.replace("2026-10-30-", "2026-10-30-other-brand-")
    other_html = re.sub(r"glorybyus\.com", "horselegalguide.com", html0)
    must_fail("another brand", fz, released + [{**rec0, "path": other, "target_brand_id": "horse-legal-guide"}],
              pages + [(other, host0, other_html)], "brand 'horse-legal-guide'")
    must_fail("no glorybyus link", fz, released + [{**rec0, "path": other}], [(other, host0, other_html)], "does not link glorybyus.com")
    must_fail("another host", fz, released, [(path0, "founderoperatorlibrary.com", html0)], "host 'founderoperatorlibrary.com'")
    early = path0.replace("2026-10-30-", "2026-10-29-")
    must_fail("before the decision", fz, released + [{**rec0, "path": early}], [(early, host0, html0)], "before the owner decided")

    # 5. Entry removed / unknown id.
    must_fail("entry removed", {**fz, "owner_exceptions": []}, released, pages, "does not hold")
    must_fail("unknown id", fz, [{**r, "owner_exception": "someone-else"} for r in claimed], pages, "does not hold")

    # 6. Malformed entries are not records.
    for field, value, needle in (("owner_words", "", "missing owner_words"), ("max_articles", "3", "positive integer"),
                                 ("decided", "", "missing decided")):
        bad = copy.deepcopy(fz)
        bad["owner_exceptions"][0][field] = value
        must_fail(f"entry without {field}", bad, released, pages, needle)

    # 7. The freeze itself is intact: an unmeasured page with no exception fails.
    must_fail("unmeasured page", fz, [{**rec0, "owner_exception": None}], [(path0, host0, html0)], "without a measured query")

# 8. Wiring.
validator = (ROOT / "scripts/validators/validate_search_intelligence.py").read_text(encoding="utf-8")
if "m.freeze_violations(" not in validator:
    fails.append("validate_search_intelligence.py no longer calls measured.freeze_violations")
if "owner_exceptions" in (ROOT / "scripts/authority_v4_autopilot.py").read_text(encoding="utf-8"):
    fails.append("authority_v4_autopilot.py reads owner_exceptions; an exception must never let the generator publish")

print(json.dumps({"validator": "freeze_owner_exception", "status": "FAIL" if fails else "PASS",
                  "hard_failures": len(fails), "exception_pages": len(pages), "daily_pages": len(real_daily),
                  "failures": fails[:40]}, indent=2))
raise SystemExit(1 if fails else 0)
