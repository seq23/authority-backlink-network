#!/usr/bin/env python3
"""The search loop strengthens what it qualifies, in the same run, before it validates.

12 Oct 2026: fresh Search Console truth qualified a new demand family (the
memphisvendorlibrary.com surprise-room-setup article). Strengthening existed only
as hand-authored entries in data/search_intelligence/strengthened_pages.json, so
the validator failed it as not_strengthened on main, and the truth was committed
alone, leaving every later `validate.py release` on main with a stale plan.

This pins:
  1. derive_strengthening.missing() turns a qualifying page with no entry into
     an entry built from the page's own dek and questions (real tree: drop one
     qualifying entry in memory, the loop must re-derive it).
  2. apply_strengthening renders a derived entry idempotently: the dek MOVES
     into the definition slot (its text appears once), the questions are listed
     once near the top, their answers are not repeated, and the <title> is not
     rewritten.
  3. A page too thin to derive is recorded `underivable` (non-blocking) and
     never `not_strengthened`; a derivable page is never `underivable`.
  4. The workflow derives and applies BEFORE building the plan and validating,
     and commits truth, plan and pages in one step before validation.
Fails on zero qualifying families examined.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "search_intelligence"))
sys.path.insert(0, str(ROOT / "scripts"))
import measured as m  # noqa: E402
import derive_strengthening as derive  # noqa: E402
import apply_strengthening as apply  # noqa: E402
import build_search_plan as plan_mod  # noqa: E402

fails: list[str] = []

# 1. A qualifying page with no entry is derived by the loop itself.
pages = (m.read_json(m.SI / "strengthened_pages.json", {}) or {}).get("pages", [])
qualifying = []
for path, doc in plan_mod.plan().items():
    if path.endswith("demand_families.json"):
        qualifying += [(doc["host"], f) for f in doc["families"] if f["qualifies"]]
if not qualifying:
    fails.append("rule0: no qualifying family examined")
victim = next((p for p in pages if any(h == p["host"] and f["page"] == p["route"] and f["status"] == "strengthened"
                                       for h, f in qualifying)
               and derive.derivable(ROOT / p["file"])), None)
if victim is None:
    fails.append("rule0: no strengthened qualifying page to drop")
else:
    real_read = m.read_json

    def without_victim(path, default=None):
        doc = real_read(path, default)
        if Path(path) == m.SI / "strengthened_pages.json":
            doc = dict(doc, pages=[p for p in doc["pages"] if p is not victim and p["route"] != victim["route"]])
        return doc

    m.read_json = without_victim
    plan_mod._TEXT_CACHE.clear()
    try:
        derived = derive.missing()
    finally:
        m.read_json = real_read
    if not any(e["host"] == victim["host"] and e["route"] == victim["route"] and e.get("derived_from_page")
               and len(e["questions"]) >= derive.MIN_QUESTIONS for e in derived):
        fails.append(f"derive: dropping the entry for {victim['host']}{victim['route']} did not make the loop derive one "
                     f"(got {[e['route'] for e in derived]})")

# 2. Rendering a derived entry: moved, listed once, idempotent, title untouched.
PAGE = ("<html><head><title>Original Title</title><meta name=\"description\" content=\"Meta words.\"></head><body><main>"
        "<h1>Original Title</h1><p class=\"dek\"><strong>Short answer:</strong> Dek words here.</p>"
        "<section><h2>Intro</h2><p>Body.</p></section>"
        "<section class=\"faq\"><h2>Frequently asked questions</h2>"
        "<h3>First question here?</h3><p>Answer one text.</p><h3>Second question here?</h3><p>Answer two text.</p>"
        "<h3>Third question here?</h3><p>Answer three text.</p></section></main></body></html>")
with tempfile.TemporaryDirectory() as tmp:
    real_root = m.ROOT
    m.ROOT = Path(tmp)
    try:
        (Path(tmp) / "p.html").write_text(PAGE, encoding="utf-8")
        entry = derive.derive_entry("h", "/p", "p.html", "fam")
        thin = PAGE.replace("<h3>Third question here?</h3><p>Answer three text.</p>", "")
        (Path(tmp) / "thin.html").write_text(thin, encoding="utf-8")
        if derive.derivable(Path(tmp) / "thin.html") or derive.derive_entry("h", "/t", "thin.html", "fam") is not None:
            fails.append("derive: a page with 2 question headings must be underivable")
    finally:
        m.ROOT = real_root
if not entry:
    fails.append("derive: the fixture page (dek + 3 FAQ questions) was not derivable")
else:
    once = apply.render_page(PAGE, entry)
    twice = apply.render_page(once, entry)
    if once != twice:
        fails.append("apply: rendering a derived entry is not idempotent")
    checks = {
        "dek moved, not copied": once.count("Dek words here.") == 1 and 'class="dek"' not in once,
        "definition slot under the H1": re.search(r'</h1><p class="definition" data-strengthened="definition"[^>]*>', once),
        "one strengthening block": once.count('data-block="search-strengthening"') == 1,
        "answers not repeated": all(once.count(a) == 1 for a in ("Answer one text.", "Answer two text.", "Answer three text.")),
        "questions listed": all(f"<li>{q}</li>" in once for q in ("First question here?", "Second question here?")),
        "title untouched": "<title>Original Title</title>" in once and 'content="Meta words."' in once,
        "no FAQPage added": "FAQPage" not in once,
        # build_search_plan strips hand-authored definitions from a page's own
        # words; a moved dek was the page's own words and must stay counted.
        "dek still counts as the page's own words": "Dek words here." in re.sub(
            r'<p class="definition" data-strengthened="definition">.*?</p>', " ", once, flags=re.S),
    }
    fails += [f"apply: derived render fails '{k}'" for k, ok in checks.items() if not ok]

# 3. The status the plan records for qualifying article families on the real tree.
for host, f in qualifying:
    if f["status"] == "not_strengthened":
        fails.append(f"plan {host}: {f['family']!r} left not_strengthened; derive_strengthening.py must have run")
    if f["status"] == "underivable" and derive.derivable(ROOT / f["file"]):
        fails.append(f"plan {host}: {f['family']!r} recorded underivable but its page is derivable")

# 4. Workflow order: derive -> apply -> plan -> one commit -> validate.
wf = (ROOT / ".github/workflows/authority-v4-autopilot.yml").read_text(encoding="utf-8")
search = wf.split("\n  search:", 1)[1].split("\n  autopilot:", 1)[0]
order = ["collect_gsc.py", "derive_strengthening.py --write", "apply_strengthening.py --write",
         "build_search_plan.py --write", "git-auto-commit-action", "validate_search_intelligence.py"]
at = [search.find(s) for s in order]
if -1 in at or at != sorted(at):
    fails.append(f"workflow: the search job must run {order} in that order (positions {at})")
if search.count("git-auto-commit-action") != 1 or 'file_pattern: "data/search_intelligence/** sites/**"' not in search:
    fails.append("workflow: the search job must commit truth, plan and strengthened pages in ONE step")
autopilot = wf.split("\n  autopilot:", 1)[1]
if not 0 <= autopilot.find("derive_strengthening.py --write") < autopilot.find("apply_strengthening.py --write"):
    fails.append("workflow: the autopilot job must derive before it applies strengthening")

print(json.dumps({"validator": "search_strengthening_loop", "status": "FAIL" if fails else "PASS",
                  "hard_failures": len(fails), "qualifying_examined": len(qualifying), "failures": fails}, indent=2))
sys.exit(1 if fails else 0)
