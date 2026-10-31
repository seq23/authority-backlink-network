#!/usr/bin/env python3
"""The 31 Oct 2026 owner exception admits exactly the five grid backlink pages.

31 Oct 2026, owner: "Yes, publish all 5" -- the five seed pages staged in PR
#132 (first network links to memphisseniorcarehomes.com, time-2-read.com,
howweknowdeep.com and spryexecutiveos.com) publish although Search Console
shows no measured query for them. One-time: the 11 Oct freeze stays exactly as
strict for everything else. Recorded as four entries in
data/search_intelligence/publishing_freeze.json `owner_exceptions` (the
validator admits one brand and one host per entry), sharing one `decision` id,
each naming its pages by slug.

Pins, against the real tree:
  1. Exactly four entries carry decision grid-backlinks-2026-10-31, each with the
     expected brand, domain, host, date, owner's words, cap and slugs; the
     caps sum to 5 and the slugs are the five approved pages.
  2. Exactly five released records claim those entries, each page is on disk,
     links its target domain and carries its own publication's editorial byline,
     and none names Spry Labs, West Peek or Sequoia.
  3. The real tree has no freeze violation.
Proves negatively, with the real pages in memory:
  4. A sixth page (another slug) claiming an entry fails, even under the cap.
  5. Widening the slugs list beyond max_articles, an empty slugs list, or a
     page dated before 31 Oct fails.
  6. An unmeasured page with no exception still fails.
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

DECISION = "grid-backlinks-2026-10-31"
WORDS = "Yes, publish all 5"
EXPECT = {
    "grid-backlinks-memphis-senior-care-2026-10-31": (
        "memphis-senior-care", "memphisseniorcarehomes.com", "memphisvendorlibrary.com",
        ["assisted-living-or-memory-care-in-memphis-how-families-decide",
         "paying-for-assisted-living-in-memphis-when-savings-run-low"]),
    "grid-backlinks-time-2-read-2026-10-31": (
        "time-2-read", "time-2-read.com", "memphisvendorlibrary.com",
        ["how-to-build-a-20-minute-reading-habit-at-home"]),
    "grid-backlinks-how-we-know-2026-10-31": (
        "how-we-know", "howweknowdeep.com", "professionalresourcelibrary.com",
        ["measured-inferred-or-reconstructed-how-to-read-a-scientific-claim"]),
    "grid-backlinks-spry-executive-os-2026-10-31": (
        "spry-executive-os", "spryexecutiveos.com", "founderoperatorlibrary.com",
        ["a-daily-check-in-system-that-keeps-a-lean-team-accountable"]),
}
BYLINE = {"memphisvendorlibrary.com": "Memphis Vendor Library Editorial Desk",
          "professionalresourcelibrary.com": "Professional Resource Library Editorial Desk",
          "founderoperatorlibrary.com": "Founder Operator Library Editorial Desk"}
fails: list[str] = []

fz = m.freeze()
released = (m.read_json(m.HELD_PATH, {}) or {}).get("released", [])
entries = {e["id"]: e for e in fz.get("owner_exceptions", []) if e.get("decision") == DECISION}

# 1. The entries.
if set(entries) != set(EXPECT):
    fails.append(f"decision {DECISION} must have exactly {sorted(EXPECT)}; found {sorted(entries)}")
for eid, (brand, domain, host, slugs) in EXPECT.items():
    e = entries.get(eid, {})
    want = {"brand_id": brand, "target_domain": domain, "host": host, "max_articles": len(slugs),
            "decided": "2026-10-31", "owner_words": WORDS, "slugs": slugs}
    for k, v in want.items():
        if e.get(k) != v:
            fails.append(f"{eid}: {k} is {e.get(k)!r}, expected {v!r}")
if sum(e.get("max_articles", 0) for e in entries.values()) != 5:
    fails.append("the grid-backlinks decision must admit exactly 5 pages in total")

# 2. The pages.
claimed = [r for r in released if r.get("owner_exception") in EXPECT]
if len(claimed) != 5:
    fails.append(f"{len(claimed)} released page(s) claim the grid-backlinks exceptions; the owner approved 5")
pages = []
for r in claimed:
    path = ROOT / r["path"]
    if not path.is_file():
        fails.append(f"{r['path']}: claimed but not on disk")
        continue
    html = path.read_text(encoding="utf-8")
    pages.append((r["path"], r["host"], html))
    _, domain, host, slugs = EXPECT[r["owner_exception"]]
    if Path(r["path"]).stem[11:] not in slugs:
        fails.append(f"{r['path']}: not one of the slugs named by {r['owner_exception']}")
    if not re.search(rf'href="https://(?:www\.)?{re.escape(domain)}[/"]', html):
        fails.append(f"{r['path']}: does not link {domain}")
    if BYLINE[host] not in html:
        fails.append(f"{r['path']}: missing its publication byline {BYLINE[host]!r}")
    hit = re.search(r"spry ?labs|west ?peek|sequoia", html, re.I)
    if hit:
        fails.append(f"{r['path']}: names {hit.group(0)!r}")
if not pages:
    fails.append("rule0: no grid-backlinks exception page examined")

# 3. The real tree.
real_daily = [(p.relative_to(ROOT).as_posix(), s["host"], p.read_text(encoding="utf-8", errors="ignore"))
              for s in m.sites() for p in sorted((ROOT / s["folder"] / "daily").glob("*.html"))]
real = m.freeze_violations(fz, released, real_daily)
if real:
    fails.append(f"real tree breaks the freeze: {real[:3]}")


def must_fail(label, fz_, released_, pages_, needle):
    got = m.freeze_violations(fz_, released_, pages_)
    if not any(needle in g for g in got):
        fails.append(f"negative proof '{label}' did not fail as expected ({needle!r}); got {got[:2]}")


if pages:
    one = next(p for p in pages if "time-2-read" not in p[0] and "assisted-living-or" not in p[0]
               and "paying-for" not in p[0])  # a single-page entry
    rel0, host0, html0 = one
    rec0 = next(r for r in claimed if r["path"] == rel0)
    eid0 = rec0["owner_exception"]

    # 4. Another slug under a raised cap still fails: the slugs list governs.
    raised = copy.deepcopy(fz)
    for e in raised["owner_exceptions"]:
        if e["id"] == eid0:
            e["max_articles"] = 2
            e["slugs"] = e["slugs"] + ["a-second-page-nobody-approved"]
    other = rel0.replace("2026-10-31-", "2026-10-31-x-")
    must_fail("unnamed slug", raised, released + [{**rec0, "path": other}], [(other, host0, html0)], "is not one of the")

    # 5. Malformed slug lists and an early date.
    wide = copy.deepcopy(fz)
    for e in wide["owner_exceptions"]:
        if e["id"] == eid0:
            e["slugs"] = e["slugs"] + ["extra"]
    must_fail("slugs wider than cap", wide, released, pages, "but max_articles is")
    empty = copy.deepcopy(fz)
    for e in empty["owner_exceptions"]:
        if e["id"] == eid0:
            e["slugs"] = []
    must_fail("empty slugs", empty, released, pages, "slugs must be a non-empty list")
    early = rel0.replace("2026-10-31-", "2026-10-30-")
    must_fail("before the decision", fz, released + [{**rec0, "path": early}], [(early, host0, html0)], "before the owner decided")

    # 6. The freeze itself is intact.
    must_fail("unmeasured page", fz, [{**rec0, "owner_exception": None}], [(rel0, host0, html0)], "without a measured query")

print(json.dumps({"validator": "freeze_grid_backlinks_exception", "status": "FAIL" if fails else "PASS",
                  "hard_failures": len(fails), "exception_pages": len(pages), "daily_pages": len(real_daily),
                  "failures": fails[:40]}, indent=2))
raise SystemExit(1 if fails else 0)
