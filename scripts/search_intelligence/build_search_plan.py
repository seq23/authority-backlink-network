#!/usr/bin/env python3
"""Measured targets, demand families and consolidation candidates, per host.

Reads data/search_intelligence/<host>/gsc_truth.json and index_coverage.json
(written by collect_gsc.py), data/search_intelligence/strengthened_pages.json
(the hand-authored strengthening content, applied by apply_strengthening.py),
held_pages.json (the publishing freeze) and the published tree. Writes, per host:

  target_query_set.json        every query with Search Console impressions in
                               the 28-day window: source + number on every row.
                               Subjects with no number (held autopilot briefs)
                               are listed in `dropped` with the reason.
  demand_families.json         the impressions-weighted strengthening rule below.
  consolidation_candidates.json  pages Google crawled or discovered and did not
                               index, with no impressions, and the topic hub each
                               would fold into. A LIST ONLY: nothing redirects.

and data/search_intelligence/strengthening_ledger.json across the three hosts.

Demand families (the rule local-guides-generator uses, per host)
-----------------------------------------------------------------
A family is a landing page plus the queries that land on it whose intent the
page answers (at least half of the query's content tokens appear in the page's
visible text). Impressions Search Console reports for the page but attributes
to no visible query (anonymised) join that family: the page's own subject is
the only intent on record for them. Queries the page does not answer form a
separate "off-page" family on the same page.

A family qualifies for strengthening when
  (a) ranking_page: it has visible queries and its page has >= 2 impressions at
      average position <= 15, OR
  (b) top_demand: it is one of the host's top 5 families by 28-day impressions,
      has >= 2 impressions, and its impression-weighted position is <= 95.
A qualifying family is strengthened on its page when the page is an article or
a topic hub and the intent matches; the homepage, editorial pages and off-page
families record the reason instead.

Deterministic: no wall clock. Same inputs, same files, so
scripts/validators/validate_search_intelligence.py recomputes and compares.

    python3 scripts/search_intelligence/build_search_plan.py [--write]
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measured as m  # noqa: E402

RULE = {"top_n": 5, "max_position": 95, "min_family_impressions": 2,
        "ranking_position": 15, "ranking_min_impressions": 2, "intent_token_share": 0.5}
EDITORIAL = {"/about", "/masthead", "/contributors", "/corrections", "/editorial-standards"}
MAX_TARGETS = 500
_TEXT_CACHE: dict[str, set] = {}


def visible_tokens(path: Path) -> set:
    key = str(path)
    if key not in _TEXT_CACHE:
        # The article's own words only: navigation, footer, disclosure asides,
        # source lists and this loop's own strengthening blocks are excluded, so
        # neither a nav rebuild nor strengthening a page changes which queries
        # the page is judged to answer.
        t = path.read_text(encoding="utf-8", errors="ignore")
        t = re.sub(r"<(script|style|nav|aside|footer|header)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
        t = re.sub(r'<p class="definition" data-strengthened="definition">.*?</p>', " ", t, flags=re.S)
        t = re.sub(r'<section data-block="(search-strengthening|search-strengthened-links|external-sources)">.*?</section>', " ", t, flags=re.S)
        _TEXT_CACHE[key] = set(m.tokens(html.unescape(re.sub(r"<[^>]+>", " ", t))))
    return _TEXT_CACHE[key]


def page_title(path: Path) -> str:
    t = path.read_text(encoding="utf-8", errors="ignore")
    h = re.search(r"<h1[^>]*>(.*?)</h1>", t, re.S) or re.search(r"<title>(.*?)</title>", t, re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", h.group(1)).strip()) if h else ""


def page_kind(route: str) -> str:
    r = route.rstrip("/") or "/"
    if r == "/":
        return "home"
    if r.removesuffix(".html") in EDITORIAL:
        return "editorial"
    if r.startswith("/topics/"):
        return "hub"
    return "article"


def answers(query: str, toks: set) -> bool:
    q = m.tokens(query)
    return bool(q) and sum(1 for t in q if t in toks) / len(q) >= RULE["intent_token_share"]


def rel(path: Path | None) -> str | None:
    return path.relative_to(m.ROOT).as_posix() if path else None


def window(truth: dict) -> str:
    return f"{truth['start_date']}..{truth['end_date']}"


def build_targets(site: dict, truth: dict, held: list[dict]) -> dict:
    landing: dict[str, dict] = {}
    for r in truth["rows"]:
        cur = landing.get(r["query"])
        if cur is None or r["impressions"] > cur["impressions"]:
            landing[r["query"]] = r
    targets, dropped = [], []
    for q in truth["by_query"]:
        if not q["impressions"] > 0:
            dropped.append({"query": q["query"], "source": "gsc_export", "reason": "zero impressions in the window"})
            continue
        land = landing.get(q["query"])
        route = m.route_of(land["page"]) if land else None
        f = m.file_for_route(site, route) if route else None
        row = {"target_id": "abn_sq_" + hashlib.sha1(f"{site['host']}|{q['query']}".encode()).hexdigest()[:12],
               "query": q["query"], "source": "gsc_export", "impressions": q["impressions"], "clicks": q["clicks"],
               "average_position": q["position"],
               "measurement": {"metric": "impressions_28d", "value": q["impressions"], "window": window(truth),
                               "collected_at": truth["collected_at"]},
               "landing_route": route, "landing_file": rel(f),
               "page_answers_query": bool(f and answers(q["query"], visible_tokens(f)))}
        targets.append(row)
    targets.sort(key=lambda t: (-t["impressions"], t["query"]))
    for t in targets[MAX_TARGETS:]:
        dropped.append({"query": t["query"], "source": "gsc_export", "reason": f"beyond the {MAX_TARGETS}-target cap"})
    targets = targets[:MAX_TARGETS]
    for h in held:
        if h.get("host") == site["host"]:
            dropped.append({"query": h["title"], "source": "autopilot_brief_held_by_freeze",
                            "reason": "no Search Console impressions for this subject: no measured number, so not a target"})
    anonymised = max(0, truth["totals"]["impressions"] - truth.get("query_row_impressions", 0))
    return {"schema_version": "1.0", "host": site["host"], "gsc_window": window(truth), "gsc_collected_at": truth["collected_at"],
            "measurement_rule": "Every target carries its source (gsc_export) and a positive measured number (28-day impressions). Anything without a number is dropped with its reason, never kept with a null.",
            "max_targets": MAX_TARGETS, "target_count": len(targets),
            "site_impressions": truth["totals"]["impressions"], "query_row_impressions": truth.get("query_row_impressions", 0),
            "anonymised_impressions": anonymised,
            "anonymised_note": "Search Console withholds rare queries. Their impressions are counted in site totals and by page, and carried into demand families by page; there is no query string to target.",
            "truth_boundary": "A target is a query this loop observes. Its number is the measurement that admitted it, not evidence of ranking or citation.",
            "dropped_count": len(dropped), "dropped": dropped, "targets": targets}


def build_families(site: dict, truth: dict, strengthened: dict) -> list[dict]:
    by_page = {m.route_of(p["page"]): p for p in truth["by_page"]}
    rows_by_page: dict[str, list] = {}
    for r in truth["rows"]:
        if r["impressions"] > 0:
            rows_by_page.setdefault(m.route_of(r["page"]), []).append(r)
    fams = []
    for route in sorted(set(by_page) | set(rows_by_page)):
        f = m.file_for_route(site, route)
        toks = visible_tokens(f) if f else set()
        rows = rows_by_page.get(route, [])
        on = [r for r in rows if answers(r["query"], toks)]
        off = [r for r in rows if r not in on]
        page = by_page.get(route, {})
        anon = max(0, page.get("impressions", 0) - sum(r["impressions"] for r in rows))
        for kind, qs, extra in (("page", on, anon), ("off_page", off, 0)):
            imp = sum(r["impressions"] for r in qs) + extra
            if imp <= 0:
                continue
            wp = round((sum(r["impressions"] * r["position"] for r in qs) + extra * page.get("position", 100)) / imp, 1)
            queries = sorted(({"query": r["query"], "impressions": r["impressions"], "position": r["position"]} for r in qs),
                             key=lambda x: (-x["impressions"], x["query"]))
            head = queries[0]["query"] if queries else (page_title(f) if f else route)
            fams.append({"family": f"{'off-page: ' if kind == 'off_page' else ''}{head} @ {route}", "intent": kind,
                         "page": route, "page_kind": page_kind(route), "file": rel(f), "page_title": page_title(f) if f else None,
                         "impressions": imp, "visible_query_impressions": imp - extra, "anonymised_impressions": extra,
                         "weighted_position": wp, "page_impressions": page.get("impressions", 0),
                         "page_position": page.get("position"), "query_count": len(queries), "queries": queries})
    fams.sort(key=lambda x: (-x["impressions"], x["weighted_position"], x["family"]))
    for i, fam in enumerate(fams):
        fam["rank"] = i + 1
        ranking = fam["query_count"] > 0 and fam["page_impressions"] >= RULE["ranking_min_impressions"] and \
            fam["page_position"] is not None and fam["page_position"] <= RULE["ranking_position"]
        demand = fam["rank"] <= RULE["top_n"] and fam["impressions"] >= RULE["min_family_impressions"] and \
            fam["weighted_position"] <= RULE["max_position"]
        fam["basis"] = [b for b, ok in (("ranking_page", ranking), ("top_demand", demand)) if ok]
        fam["qualifies"] = bool(fam["basis"])
        fam["strengthened_pages"] = []
        if not fam["qualifies"]:
            if fam["rank"] > RULE["top_n"]:
                fam["status"], fam["reason"] = "not_top_family", f"rank {fam['rank']} of {len(fams)} by impressions; no visible query on a page at position <= {RULE['ranking_position']} with >= {RULE['ranking_min_impressions']} impressions"
            elif fam["impressions"] < RULE["min_family_impressions"]:
                fam["status"], fam["reason"] = "below_impression_floor", f"{fam['impressions']} impression(s) < {RULE['min_family_impressions']}"
            else:
                fam["status"], fam["reason"] = "position_beyond_max", f"weighted position {fam['weighted_position']} > {RULE['max_position']}"
            continue
        if fam["file"] is None:
            fam["status"], fam["reason"] = "no_page", f"{fam['page']} has no published file (see validate_measured_urls_resolve)"
        elif fam["page_kind"] == "home":
            fam["status"], fam["reason"] = "no_page", "lands on the homepage: the front door is strengthened by linking the strengthened pages from it, not by rewriting it around one query"
        elif fam["page_kind"] == "editorial":
            fam["status"], fam["reason"] = "no_page", f"lands on {fam['page']}, an editorial-governance page (masthead/about/standards); its content is the publisher's disclosure, not a search answer"
        elif fam["intent"] == "off_page":
            fam["status"], fam["reason"] = "intent_mismatch", "fewer than half of each query's content words appear on the page: the page does not answer these queries, so rewriting it for them would change what it is"
        else:
            fam["strengthened_pages"] = [fam["page"]]
            entry = strengthened.get((site["host"], fam["page"]))
            if entry:
                fam["status"], fam["reason"] = "strengthened", f"data/search_intelligence/strengthened_pages.json -> {fam['file']}"
            else:
                fam["status"], fam["reason"] = "not_strengthened", f"{fam['file']} qualifies and has no entry in data/search_intelligence/strengthened_pages.json"
    return fams


def build_consolidation(site: dict, truth: dict, cov: dict | None) -> dict:
    imp = {m.route_of(p["page"]): p for p in truth["by_page"]}
    hubs = sorted((m.ROOT / site["folder"] / "topics").glob("*.html"))
    hub_links = {h: h.read_text(encoding="utf-8", errors="ignore") for h in hubs}
    rows = []
    for u in (cov or {}).get("urls", []):
        if u.get("bucket") not in ("crawled_not_indexed", "discovered_not_indexed", "unknown"):
            continue
        route = m.route_of(u["url"])
        if route in imp:
            continue
        hub = next((h for h, text in hub_links.items() if f'"{u["url"]}"' in text or f'"{route}"' in text), None)
        f = m.file_for_route(site, route)
        rows.append({"url": u["url"], "file": rel(f), "coverage_state": u.get("coverageState"), "bucket": u["bucket"],
                     "inspected_at": u.get("inspected_at"), "impressions_28d": 0,
                     "fold_into_hub": f"/topics/{hub.stem}" if hub else None,
                     "fold_rule": "the topic hub that already lists the page" if hub else "no topic hub lists this page"})
    rows.sort(key=lambda r: (r["bucket"], r["url"]))
    by_hub: dict[str, int] = {}
    for r in rows:
        by_hub[r["fold_into_hub"] or "none"] = by_hub.get(r["fold_into_hub"] or "none", 0) + 1
    return {"schema_version": "1.0", "host": site["host"], "status": "LIST_ONLY_NO_REDIRECTS",
            "decision_input_for": "Fold a page into its topic hub when URL Inspection keeps it out of the index and Search Console shows it no impressions for the whole 28-day window. Nothing here redirects or deletes; the list is evidence for that decision.",
            "gsc_window": window(truth), "coverage_collected_at": (cov or {}).get("collected_at"),
            "inspected_url_count": len((cov or {}).get("urls", [])), "candidate_count": len(rows),
            "candidates_by_hub": dict(sorted(by_hub.items())), "rows": rows}


def plan() -> dict[str, dict]:
    """{repo-relative path: document} for every file this script owns."""
    strengthened = {(p["host"], p["route"]): p for p in (m.read_json(m.SI / "strengthened_pages.json", {}) or {}).get("pages", [])}
    held = (m.read_json(m.HELD_PATH, {}) or {}).get("held", [])
    out: dict[str, dict] = {}
    ledger = []
    for site in m.sites():
        d = m.SI / site["host"]
        truth = m.read_json(d / "gsc_truth.json")
        if not truth or truth.get("state") != "OK":
            continue
        out[f"data/search_intelligence/{site['host']}/target_query_set.json"] = build_targets(site, truth, held)
        fams = build_families(site, truth, strengthened)
        out[f"data/search_intelligence/{site['host']}/demand_families.json"] = {
            "schema_version": "1.0", "host": site["host"], "gsc_window": window(truth), "gsc_collected_at": truth["collected_at"],
            "rule": __doc__.split("Demand families (the rule local-guides-generator uses, per host)")[1].split("Deterministic:")[0].strip("-\n "),
            "thresholds": RULE, "family_count": len(fams), "qualifying_count": sum(f["qualifies"] for f in fams),
            "status_counts": {s: sum(1 for f in fams if f["status"] == s) for s in sorted({f["status"] for f in fams})},
            "families": fams}
        out[f"data/search_intelligence/{site['host']}/consolidation_candidates.json"] = build_consolidation(site, truth, m.read_json(d / "index_coverage.json"))
        for f in fams:
            if f["qualifies"]:
                e = strengthened.get((site["host"], f["page"]))
                ledger.append({"host": site["host"], "family": f["family"], "basis": f["basis"], "impressions": f["impressions"],
                               "weighted_position": f["weighted_position"], "status": f["status"], "reason": f["reason"],
                               "page": f["page"], "file": f["file"],
                               "changes": None if f["status"] != "strengthened" else {
                                   "title": e["title"], "definition": bool(e.get("definition")),
                                   "question_h2s": len(e.get("questions", [])), "faqpage": e.get("faq_schema", False),
                                   "facts": len(e.get("facts", [])), "linked_from_homepage": True}})
    for (host, route), e in sorted(strengthened.items()):
        if not any(x["host"] == host and x["page"] == route and x["status"] == "strengthened" for x in ledger):
            ledger.append({"host": host, "family": None, "basis": [], "status": "strengthened_without_qualifying_family",
                           "reason": "listed in strengthened_pages.json but no family qualifies it in this window; kept, never reverted", "page": route,
                           "file": e.get("file")})
    out["data/search_intelligence/strengthening_ledger.json"] = {
        "schema_version": "1.0", "source": "data/search_intelligence/<host>/demand_families.json + strengthened_pages.json",
        "counts": {s: sum(1 for x in ledger if x["status"] == s) for s in sorted({x["status"] for x in ledger})},
        "entries": ledger}
    return out


def main() -> int:
    docs = plan()
    if not docs:
        print("build_search_plan: no host has an OK gsc_truth.json; nothing built (collect_gsc.py writes it)", file=sys.stderr)
        return 1
    drift = []
    for path, doc in docs.items():
        text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        p = m.ROOT / path
        if not p.exists() or p.read_text(encoding="utf-8") != text:
            drift.append(path)
            if "--write" in sys.argv:
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
    for path, doc in docs.items():
        if path.endswith("demand_families.json"):
            print(f"{doc['host']}: {doc['family_count']} families, {doc['qualifying_count']} qualify {doc['status_counts']}")
    print(f"build_search_plan: {len(docs)} files, {len(drift)} {'written' if '--write' in sys.argv else 'out of date'}")
    return 0 if ("--write" in sys.argv or not drift) else 1


if __name__ == "__main__":
    sys.exit(main())
