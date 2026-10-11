#!/usr/bin/env python3
"""Daily Search Console truth for the three publications in data/search_intelligence/sites.json.

Per host, into data/search_intelligence/<host>/:
  gsc_truth.json       query x page rows for the rolling 28 complete days
                       (ending 3 days ago, Search Console's data lag), the
                       property totals (no dimensions: complete, unlike the
                       query rows, which omit anonymised queries), and
                       per-query / per-page rollups.
  query_history.json   one snapshot per window end: every query's
                       impressions, clicks and position, newest last, 90 kept.
  gsc_sitemaps.json    sitemaps.list; the publication's sitemap is submitted
                       ONLY when the property does not list it, then listed again.
  index_coverage.json  urlInspection.index.inspect, 8 requests in parallel, at
                       most 150 URLs per host per day (450 of the 2,000/day
                       quota per property is far inside it). Rotation:
                       homepage, then never-inspected sitemap URLs in sitemap
                       order, then the oldest inspection, so every sitemap URL is
                       covered over time. Rows merge with the previous file.

The sitemap URL list is the committed sites/<folder>/sitemap.xml, which is what
main deployed: the step runs before the day's generator touches it.

Credentials: the stdlib JWT exchange in post_publish_distribution.google_access_token
(openssl signs; no Google client library to install). A missing credential, or a
property the service account cannot read, is a NAMED STOP line with exit 0 and
that host's files left as they were -- a secretless run never blanks evidence.
Exit 1 only when a credential exists and no host could be read at all.

Usage: collect_gsc.py [--only <host>]
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from post_publish_distribution import google_access_token, request_json  # noqa: E402

SI = ROOT / "data" / "search_intelligence"
API = "https://searchconsole.googleapis.com"
CAP_PER_HOST = 150
PARALLEL = 8
HISTORY_KEEP = 90


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def sites() -> list[dict]:
    return read_json(SI / "sites.json")["sites"]


def sitemap_urls(site: dict) -> list[str]:
    text = (ROOT / site["folder"] / "sitemap.xml").read_text(encoding="utf-8")
    return [u.strip() for u in re.findall(r"<loc>([^<]+)</loc>", text)]


class Client:
    def __init__(self, token: str):
        self.h = {"Authorization": f"Bearer {token}"}

    def call(self, method: str, path: str, payload=None) -> dict:
        r = request_json(API + path, method=method, headers=self.h, payload=payload, timeout=60)
        if not r["ok"]:
            raise RuntimeError(f"HTTP {r.get('http_status')} {json.dumps(r.get('body'))[:300]} {r.get('error', '')[:200]}")
        return r["body"] or {}

    def sa(self, site: str, start: str, end: str, dims: list[str] | None, limit: int = 25000) -> list[dict]:
        body = {"startDate": start, "endDate": end, "rowLimit": limit}
        if dims:
            body["dimensions"] = dims
        return self.call("POST", f"/webmasters/v3/sites/{urllib.parse.quote(site, safe='')}/searchAnalytics/query", body).get("rows", [])


def metrics(r: dict) -> dict:
    return {"clicks": r.get("clicks", 0), "impressions": r.get("impressions", 0),
            "ctr": round(r.get("ctr", 0), 4), "position": round(r.get("position", 0), 1)}


def analytics(c: Client, site: dict, now: str) -> dict:
    end = dt.date.today() - dt.timedelta(days=3)
    start = end - dt.timedelta(days=27)
    s, e, g = start.isoformat(), end.isoformat(), site["gsc_site"]
    tot = c.sa(g, s, e, None, 1)
    rows = sorted(({"query": r["keys"][0], "page": r["keys"][1], **metrics(r)} for r in c.sa(g, s, e, ["query", "page"])),
                  key=lambda x: (-x["impressions"], x["query"], x["page"]))
    by_query = sorted(({"query": r["keys"][0], **metrics(r)} for r in c.sa(g, s, e, ["query"])), key=lambda x: (-x["impressions"], x["query"]))
    by_page = sorted(({"page": r["keys"][0], **metrics(r)} for r in c.sa(g, s, e, ["page"])), key=lambda x: (-x["impressions"], x["page"]))
    totals = metrics(tot[0]) if tot else {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0}
    return {"schema_version": "1.0", "truth_source": "google_search_console_search_analytics", "state": "OK",
            "host": site["host"], "site_url": g, "start_date": s, "end_date": e, "window_days": 28, "collected_at": now,
            "totals": totals, "query_count": len(by_query), "page_count": len(by_page), "row_count": len(rows),
            "query_row_impressions": sum(r["impressions"] for r in by_query),
            "truth_boundary": "Search Console is the only authority for this host's Google impressions, clicks and position. totals has no dimensions and is complete; query rows omit anonymised queries, so they sum to less.",
            "rows": rows, "by_query": by_query, "by_page": by_page}


def history(prev: dict | None, truth: dict) -> dict:
    snaps = [s for s in (prev or {}).get("snapshots", []) if s.get("end_date") != truth["end_date"]]
    snaps.append({"collected_at": truth["collected_at"], "start_date": truth["start_date"], "end_date": truth["end_date"],
                  "totals": truth["totals"],
                  "queries": {q["query"]: [q["impressions"], q["clicks"], q["position"]] for q in truth["by_query"]}})
    snaps = sorted(snaps, key=lambda s: s["end_date"])[-HISTORY_KEEP:]
    return {"schema_version": "1.0", "host": truth["host"], "row_format": "query: [impressions_28d, clicks_28d, position]",
            "snapshot_count": len(snaps), "snapshots": snaps}


def sitemaps(c: Client, site: dict, now: str) -> dict:
    g = urllib.parse.quote(site["gsc_site"], safe="")
    want = f"https://{site['host']}/sitemap.xml"
    state = lambda body: {e["path"]: {"lastSubmitted": e.get("lastSubmitted"), "lastDownloaded": e.get("lastDownloaded"),  # noqa: E731
                                      "isPending": e.get("isPending"), "errors": int(e.get("errors", 0) or 0),
                                      "warnings": int(e.get("warnings", 0) or 0)} for e in body.get("sitemap", [])}
    before = state(c.call("GET", f"/webmasters/v3/sites/{g}/sitemaps"))
    submitted = []
    if want not in before:
        c.call("PUT", f"/webmasters/v3/sites/{g}/sitemaps/{urllib.parse.quote(want, safe='')}")
        submitted.append(want)
    after = state(c.call("GET", f"/webmasters/v3/sites/{g}/sitemaps")) if submitted else before
    return {"schema_version": "1.0", "site_url": site["gsc_site"], "collected_at": now, "sitemap_url": want,
            "state": "REGISTERED" if want in after else "NOT_LISTED", "listed_before": before,
            "submitted_this_run": submitted, "listed_after": after}


def bucket(idx: dict) -> str:
    state = (idx.get("coverageState") or "").lower()
    if "unknown to google" in state:
        return "unknown"
    if "crawled" in state and "not indexed" in state:
        return "crawled_not_indexed"
    if "discovered" in state and "not indexed" in state:
        return "discovered_not_indexed"
    if idx.get("verdict") == "PASS" or ("indexed" in state and "not indexed" not in state):
        return "indexed"
    return "other"


def coverage(c: Client, site: dict, prev: dict | None, now: str) -> dict:
    home = f"https://{site['host']}/"
    pages = sitemap_urls(site)
    universe = [home] + [u for u in pages if u.rstrip("/") != home.rstrip("/")]
    keep = set(universe)
    prev_rows = {r["url"]: r for r in (prev or {}).get("urls", []) if r.get("url") in keep}
    order = {u: i for i, u in enumerate(universe)}
    rest = sorted(universe[1:], key=lambda u: (u in prev_rows, (prev_rows.get(u) or {}).get("inspected_at") or "", order[u]))
    batch = ([home] + rest)[:CAP_PER_HOST]

    def inspect(url: str) -> dict:
        try:
            idx = c.call("POST", "/v1/urlInspection/index:inspect",
                         {"inspectionUrl": url, "siteUrl": site["gsc_site"], "languageCode": "en-US"}) \
                .get("inspectionResult", {}).get("indexStatusResult", {})
            return {"url": url, "bucket": bucket(idx), "coverageState": idx.get("coverageState"), "verdict": idx.get("verdict"),
                    "lastCrawlTime": idx.get("lastCrawlTime"), "pageFetchState": idx.get("pageFetchState"),
                    "googleCanonical": idx.get("googleCanonical"), "userCanonical": idx.get("userCanonical"), "inspected_at": now}
        except Exception as exc:  # noqa: BLE001 - every failure is counted, none swallowed
            return {"url": url, "bucket": "error", "error": str(exc)[:300]}

    with cf.ThreadPoolExecutor(PARALLEL) as pool:
        fresh = list(pool.map(inspect, batch))
    ok = [r for r in fresh if r["bucket"] != "error"]
    for r in ok:
        prev_rows[r["url"]] = r
    rows = [prev_rows[u] for u in universe if u in prev_rows]
    by_state: dict[str, int] = {}
    buckets: dict[str, int] = {}
    for r in rows:
        k = r.get("coverageState") or r["bucket"]
        by_state[k] = by_state.get(k, 0) + 1
        buckets[r["bucket"]] = buckets.get(r["bucket"], 0) + 1
    return {"schema_version": "1.0", "truth_source": "google_search_console_url_inspection", "host": site["host"],
            "site_url": site["gsc_site"], "collected_at": now, "state": "OK" if ok else "NAMED_STOP",
            "named_stop": None if ok else f"URL Inspection failed for all {len(batch)} URLs: {fresh[0].get('error') if fresh else 'no URLs'}",
            "sitemap_url_count": len(universe), "inspected_this_run": len(ok), "errors_this_run": len(fresh) - len(ok),
            "inspected_total": len(rows), "never_inspected": len(universe) - len(rows),
            "quota": {"daily_limit_per_property": 2000, "cap_per_host_per_day": CAP_PER_HOST, "parallel": PARALLEL},
            "rotation": "homepage, then never-inspected sitemap URLs in sitemap order, then oldest inspection first",
            "summary": {"by_coverage_state": dict(sorted(by_state.items())), "buckets": dict(sorted(buckets.items()))},
            "truth_boundary": "URL Inspection reports Google's index state per URL at inspected_at; impressions come from gsc_truth.json.",
            "urls": rows}


def collect(c: Client, site: dict, now: str) -> tuple[bool, str]:
    out = SI / site["host"]
    try:
        truth = analytics(c, site, now)
    except Exception as exc:  # noqa: BLE001
        return False, f"NAMED STOP: {site['gsc_site']} search analytics unreadable: {str(exc)[:300]}"
    write_json(out / "gsc_truth.json", truth)
    write_json(out / "query_history.json", history(read_json(out / "query_history.json"), truth))
    notes = []
    try:
        sm = sitemaps(c, site, now)
        write_json(out / "gsc_sitemaps.json", sm)
        notes.append(f"sitemap {sm['state']}{' (submitted)' if sm['submitted_this_run'] else ''}")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"NAMED STOP sitemaps: {str(exc)[:200]}")
    cov = coverage(c, site, read_json(out / "index_coverage.json"), now)
    if cov["state"] == "OK":
        write_json(out / "index_coverage.json", cov)
    else:
        notes.append(f"NAMED STOP coverage: {cov['named_stop']}")
    b = cov["summary"]["buckets"]
    return True, (f"{site['host']}: rows={truth['row_count']} impressions={truth['totals']['impressions']} "
                  f"clicks={truth['totals']['clicks']} | coverage +{cov['inspected_this_run']} -> "
                  f"{cov['inspected_total']}/{cov['sitemap_url_count']} indexed={b.get('indexed', 0)} {b} | {'; '.join(notes)}")


def status(now: str, hosts: dict) -> None:
    """data/search_intelligence/collection_status.json: when the collector last ran and
    what each host's outcome was. The validator reads it so a NAMED STOP (stale
    truth with a stated reason) is distinguishable from a collector that stopped
    running at all."""
    prev = (read_json(SI / "collection_status.json") or {}).get("hosts", {})
    write_json(SI / "collection_status.json", {"schema_version": "1.0", "ran_at": now, "hosts": {**prev, **hosts}})


def main() -> int:
    args = sys.argv[1:]
    only = args[1] if args[:1] == ["--only"] else None
    chosen = [s for s in sites() if not only or s["host"] == only]
    if not chosen:
        print(f"no site selected from data/search_intelligence/sites.json (--only {only})", file=sys.stderr)
        return 1
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    token, how = google_access_token()
    if not token:
        stop = (f"NAMED STOP: Search Console credential unavailable ({how}); set GSC_SERVICE_ACCOUNT_JSON. "
                "data/search_intelligence/<host>/ files left as they were.")
        print(stop)
        status(now, {s["host"]: {"state": "NAMED_STOP", "line": stop} for s in chosen})
        return 0
    c = Client(token)
    with cf.ThreadPoolExecutor(len(chosen)) as pool:
        results = list(pool.map(lambda s: collect(c, s, now), chosen))
    for _, line in results:
        print(line)
    status(now, {s["host"]: {"state": "OK" if ok else "NAMED_STOP", "line": line} for s, (ok, line) in zip(chosen, results)})
    if not any(ok for ok, _ in results):
        print("collect_gsc: a credential exists and no property was readable; nothing written", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
