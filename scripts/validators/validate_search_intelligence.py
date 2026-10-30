#!/usr/bin/env python3
"""The measured search loop is measured, sourced, acted on and frozen where it says.

Owner-approved 11 Oct 2026: the three publications earn their own rankings from
Search Console numbers, not from a pantry draw. scripts/search_intelligence/
collects the truth daily, builds the plan and strengthens the pages; this checks
that each part is real, per host in data/search_intelligence/sites.json:

  truth       gsc_truth.json is state OK and collected within MAX_AGE_DAYS, or
              collection_status.json records a NAMED STOP for the host with its
              reason (a credential only the owner holds never reds main). The
              collector itself must have run within MAX_AGE_DAYS. Totals are
              coherent: 28-day window, row/query/page counts equal their lists,
              query-row impressions <= site total impressions.
  coverage    index_coverage.json: state OK, buckets sum to the URLs inspected,
              inspected + never-inspected = the sitemap universe, > 0 inspected.
  targets     every target has source gsc_export and a positive number equal to
              its measurement; every query with impressions is a target or
              dropped with a reason; every dropped row has a reason. Zero targets
              only when every impression on the host is anonymised, and the file
              says so.
  plan        target_query_set / demand_families / consolidation_candidates /
              strengthening_ledger equal what build_search_plan.py computes now.
  families    every qualifying family is strengthened or carries a reason
              (no_page / intent_mismatch / underivable); none is left
              not_strengthened. underivable is measured and non-blocking, and
              is re-checked: a page derive_strengthening.py could strengthen
              from its own questions may not carry it. A derived entry's listed
              questions must still be visible headings on its page.
              Every strengthened page renders exactly as apply_strengthening.py
              would write it, carries the definition and >= 3 question H2s, and
              is linked from its homepage.
  faqpage     no published page has more than one FAQPage; a strengthening
              FAQPage exists only where the page had none and only from the
              visible questions.
  freeze      publishing_freeze.json `enabled` is a boolean, the autopilot reads
              it, and while enabled every daily page dated on/after `since` was
              released with a measured query (held_pages.json `released`), or
              claims a valid owner exception (publishing_freeze.json
              `owner_exceptions`: one brand, one host, a date, the owner's
              words, at most `max_articles` pages; see
              measured.freeze_violations, pinned by
              tests/test_freeze_owner_exception.py).

Rule 0: zero hosts, zero pages scanned, or zero families examined is a FAIL.

    python3 scripts/validators/validate_search_intelligence.py
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "search_intelligence"))
sys.path.insert(0, str(ROOT / "scripts"))
import measured as m  # noqa: E402
import build_search_plan as plan_mod  # noqa: E402
import apply_strengthening as strengthen  # noqa: E402
import derive_strengthening as derive  # noqa: E402

MAX_AGE_DAYS = 4
LD_RE = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


def age_days(stamp: str) -> float:
    t = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 86400


def faq_nodes(text: str) -> list[dict]:
    out = []
    for block in LD_RE.findall(text):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for node in (data.get("@graph", [data]) if isinstance(data, dict) else data):
            if isinstance(node, dict) and node.get("@type") == "FAQPage":
                out.append(node)
    return out


def main() -> int:
    fail: list[str] = []
    stats = {"hosts": 0, "targets": 0, "families": 0, "qualifying": 0, "strengthened_pages": 0, "derived_pages": 0, "underivable": 0, "pages_scanned": 0}
    sites = m.sites()
    status = m.read_json(m.SI / "collection_status.json", {}) or {}
    if not status.get("ran_at") or age_days(status["ran_at"]) > MAX_AGE_DAYS:
        fail.append(f"truth: collect_gsc.py has not run in {MAX_AGE_DAYS} days (collection_status.json ran_at={status.get('ran_at')})")

    for site in sites:
        h = site["host"]
        d = m.SI / h
        stats["hosts"] += 1
        truth = m.read_json(d / "gsc_truth.json")
        host_status = (status.get("hosts") or {}).get(h, {})
        if not truth or truth.get("state") != "OK":
            fail.append(f"truth {h}: gsc_truth.json missing or not OK")
            continue
        if age_days(truth["collected_at"]) > MAX_AGE_DAYS and host_status.get("state") != "NAMED_STOP":
            fail.append(f"truth {h}: collected {truth['collected_at']}, older than {MAX_AGE_DAYS} days, and no NAMED STOP recorded")
        s, e = dt.date.fromisoformat(truth["start_date"]), dt.date.fromisoformat(truth["end_date"])
        if (e - s).days != 27 or truth.get("window_days") != 28:
            fail.append(f"truth {h}: window {s}..{e} is not 28 days")
        for key, lst in (("row_count", "rows"), ("query_count", "by_query"), ("page_count", "by_page")):
            if truth.get(key) != len(truth.get(lst, [])):
                fail.append(f"truth {h}: {key}={truth.get(key)} but {lst} has {len(truth.get(lst, []))}")
        qimp = sum(q["impressions"] for q in truth["by_query"])
        if qimp != truth.get("query_row_impressions") or qimp > truth["totals"]["impressions"]:
            fail.append(f"truth {h}: query-row impressions {qimp} vs recorded {truth.get('query_row_impressions')} vs site total {truth['totals']['impressions']}")
        if truth["totals"]["impressions"] > 0 and not truth["by_page"]:
            fail.append(f"truth {h}: {truth['totals']['impressions']} impressions but no page rows")

        cov = m.read_json(d / "index_coverage.json")
        if not cov or cov.get("state") != "OK":
            fail.append(f"coverage {h}: index_coverage.json missing or not OK")
        else:
            if sum(cov["summary"]["buckets"].values()) != cov["inspected_total"] or cov["inspected_total"] != len(cov["urls"]):
                fail.append(f"coverage {h}: buckets {cov['summary']['buckets']} do not sum to inspected_total {cov['inspected_total']} / {len(cov['urls'])} rows")
            if cov["inspected_total"] + cov["never_inspected"] != cov["sitemap_url_count"]:
                fail.append(f"coverage {h}: inspected + never_inspected != sitemap_url_count")
            if cov["inspected_total"] == 0:
                fail.append(f"coverage {h}: zero URLs inspected")
            if age_days(cov["collected_at"]) > MAX_AGE_DAYS and host_status.get("state") != "NAMED_STOP":
                fail.append(f"coverage {h}: collected {cov['collected_at']}, older than {MAX_AGE_DAYS} days, and no NAMED STOP recorded")

        tq = m.read_json(d / "target_query_set.json")
        if not tq:
            fail.append(f"targets {h}: target_query_set.json missing")
        else:
            stats["targets"] += len(tq["targets"])
            ids = {t["query"] for t in tq["targets"]}
            dropped = {x["query"] for x in tq["dropped"]}
            for t in tq["targets"]:
                if t.get("source") != "gsc_export" or not (isinstance(t.get("impressions"), (int, float)) and t["impressions"] > 0) \
                        or (t.get("measurement") or {}).get("value") != t["impressions"]:
                    fail.append(f"targets {h}: unsourced or unmeasured target {t.get('query')!r}")
            for q in truth["by_query"]:
                if q["impressions"] > 0 and q["query"] not in ids and q["query"] not in dropped:
                    fail.append(f"targets {h}: measured query {q['query']!r} is neither a target nor dropped with a reason")
            for x in tq["dropped"]:
                if not x.get("reason"):
                    fail.append(f"targets {h}: dropped {x.get('query')!r} has no reason")
            if tq["target_count"] != len(tq["targets"]):
                fail.append(f"targets {h}: target_count != len(targets)")
            if not tq["targets"] and not (truth.get("query_row_impressions") == 0 and tq.get("anonymised_impressions") == truth["totals"]["impressions"]):
                fail.append(f"targets {h}: zero targets although Search Console reports visible queries")

        fams = m.read_json(d / "demand_families.json")
        if not fams:
            fail.append(f"families {h}: demand_families.json missing")
            continue
        stats["families"] += len(fams["families"])
        for f in fams["families"]:
            if not f.get("status") or not f.get("reason"):
                fail.append(f"families {h}: {f['family']!r} has no status/reason")
            if f["qualifies"]:
                stats["qualifying"] += 1
                if f["status"] == "underivable":
                    # Measured, non-blocking -- but only when it is true: a page
                    # that can supply its own questions must have been derived.
                    stats["underivable"] += 1
                    if derive.derivable(ROOT / f["file"]) if f.get("file") else False:
                        fail.append(f"families {h}: {f['family']!r} is recorded underivable but {f['file']} carries "
                                    f"{derive.MIN_QUESTIONS}+ question headings; derive_strengthening.py must strengthen it")
                elif f["status"] not in ("strengthened", "no_page", "intent_mismatch"):
                    fail.append(f"families {h}: qualifying family {f['family']!r} is {f['status']}: {f['reason']}")

    # The plan is rebuilt by the workflow after every change to the tree, so it
    # is checked for what must hold whatever the tree looks like: built from
    # today's truth, and every family's qualification consistent with its own
    # numbers under the rule (a byte comparison would red any lane that edits a
    # page, which is not a defect in the plan).
    R = plan_mod.RULE
    for site in sites:
        d = m.SI / site["host"]
        truth = m.read_json(d / "gsc_truth.json") or {}
        fams = m.read_json(d / "demand_families.json") or {"families": []}
        for name in ("target_query_set.json", "demand_families.json", "consolidation_candidates.json"):
            doc = m.read_json(d / name) or {}
            if doc.get("gsc_window") != f"{truth.get('start_date')}..{truth.get('end_date')}":
                fail.append(f"plan {site['host']}: {name} was not built from the current gsc_truth.json window")
        page_total = sum(p["impressions"] for p in truth.get("by_page", []))
        # Each page contributes max(page impressions, its visible-query rows), so
        # families can only hold at least what the pages report -- never less.
        if fams["families"] and sum(f["impressions"] for f in fams["families"]) < page_total:
            fail.append(f"plan {site['host']}: families hold {sum(f['impressions'] for f in fams['families'])} impressions, pages report {page_total}: demand was dropped")
        for f in fams["families"]:
            ranking = f["query_count"] > 0 and f["page_impressions"] >= R["ranking_min_impressions"] and \
                f["page_position"] is not None and f["page_position"] <= R["ranking_position"]
            demand = f["rank"] <= R["top_n"] and f["impressions"] >= R["min_family_impressions"] and f["weighted_position"] <= R["max_position"]
            if f["qualifies"] != (ranking or demand):
                fail.append(f"plan {site['host']}: {f['family']!r} qualifies={f['qualifies']} contradicts its own numbers under the rule")
    ledger = m.read_json(m.SI / "strengthening_ledger.json") or {}
    if not ledger.get("entries"):
        fail.append("plan: strengthening_ledger.json is missing or empty")

    entries = strengthen.entries()
    stats["strengthened_pages"] = len(entries)
    if not entries:
        fail.append("families: strengthened_pages.json lists no pages")
    try:
        planned = strengthen.planned()
    except ValueError as exc:
        fail.append(f"strengthening: {exc}")
        planned = {}
    for path, text in planned.items():
        if path.read_text(encoding="utf-8") != text:
            fail.append(f"strengthening: {path.relative_to(ROOT)} differs from apply_strengthening.py (run it with --write)")
    for entry in entries:
        site = next((s for s in sites if s["host"] == entry["host"]), None)
        page = ROOT / entry["file"]
        if site is None or not page.is_file():
            fail.append(f"strengthening: {entry['host']}{entry['route']} has no site or file")
            continue
        text = page.read_text(encoding="utf-8")
        if 'data-strengthened="definition"' not in text or len(entry["questions"]) < 3 or \
                text.count('data-block="search-strengthening"') != 1:
            fail.append(f"strengthening: {entry['file']} lacks the definition, the question H2s, or has the block twice")
        if entry.get("derived_from_page"):
            stats["derived_pages"] += 1
            # The list near the top points at answers the page must still give.
            visible = {q["q"].casefold() for q in derive.page_questions(text)}
            gone = [q["q"] for q in entry["questions"] if q["q"].casefold() not in visible]
            if gone:
                fail.append(f"strengthening: {entry['file']} lists questions it no longer answers as headings: {gone[:3]}")
            if entry.get("faq_schema"):
                fail.append(f"faqpage: {entry['file']} is derived and may not add a FAQPage")
        url = m.ROOT / site["folder"] / "index.html"
        rel_page = Path(entry["file"]).relative_to(site["folder"]).as_posix()
        from lib import site_urls  # noqa: PLC0415
        if f'href="{site_urls.page_url(site["host"], rel_page)}"' not in url.read_text(encoding="utf-8"):
            fail.append(f"strengthening: {entry['file']} is not linked from {site['folder']}/index.html")
        faqs = faq_nodes(text)
        if entry.get("faq_schema"):
            names = [q.get("name") for f in faqs for q in f.get("mainEntity", [])]
            if len(faqs) != 1 or names != [q["q"] for q in entry["questions"]]:
                fail.append(f"faqpage: {entry['file']} must carry exactly the strengthening FAQPage built from its visible questions")

    for site in sites:
        for p in (ROOT / site["folder"]).rglob("*.html"):
            stats["pages_scanned"] += 1
            n = len(faq_nodes(p.read_text(encoding="utf-8", errors="ignore")))
            if n > 1:
                fail.append(f"faqpage: {p.relative_to(ROOT)} has {n} FAQPage nodes; a page keeps one")

    fz = m.freeze()
    if not isinstance(fz.get("enabled"), bool):
        fail.append("freeze: publishing_freeze.json `enabled` must be a boolean")
    auto = (ROOT / "scripts/authority_v4_autopilot.py").read_text(encoding="utf-8")
    if "search_measured.freeze()" not in auto or "FREEZE.get('enabled') is True" not in auto or "measured_target(" not in auto:
        fail.append("freeze: scripts/authority_v4_autopilot.py no longer reads the publishing freeze")
    released = (m.read_json(m.HELD_PATH, {}) or {}).get("released", [])
    daily = [(p.relative_to(ROOT).as_posix(), site["host"], p.read_text(encoding="utf-8", errors="ignore"))
             for site in sites for p in sorted((ROOT / site["folder"] / "daily").glob("*.html"))]
    fail += m.freeze_violations(fz, released, daily)

    if stats["hosts"] == 0 or stats["pages_scanned"] == 0 or stats["families"] == 0:
        fail.append(f"rule0: examined nothing ({stats})")
    print(json.dumps({"validator": "search_intelligence", "status": "FAIL" if fail else "PASS",
                      "hard_failures": len(fail), **stats, "failures": fail[:40]}, indent=2))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
