#!/usr/bin/env python3
"""Build data/portfolio-deep-targets.json: the pages each portfolio site is strengthening.

Owner decision, 11 Oct 2026: links from these publications to the owner's
portfolio are ordinary followed editorial links, and they should point at the
pages the target sites are measurably working on -- not at homepages.

Where the target pages come from
--------------------------------
Each target repository publishes its own measured target set. This script reads
them from sibling checkouts (``../<repo>``, at ``origin/main`` when the checkout
has one, so a dirty working tree is never the source):

    p-n-p                   data/search_intelligence/target_query_set.json
    approvalprep            data/search_intelligence/target_query_set.json
    dream-wedding-builder   data/search_intelligence/target_query_set.json
    local-guides-generator  data/search_intelligence/<host>/target_query_set.json
                            data/search_intelligence/strengthened_pages.json
    WPP-llm                 data/seo/measured_targets.json
    sprylabs-hpc-site       data/search_intelligence/target_query_set.json
    hicks-consulting-canonical
                            data/search_intelligence/target_query_set.json

plus every deep URL this repository's own pantry already approves (the targets
with no measured set: A Player Mode, Virtual Agency OS, Horse Legal Guide, The
Industry Guides).

Every candidate is fetched live. Only a page that answers 200 on its own host
is kept, and its anchor is the page's own <title> with the site-name suffix
removed -- so anchor text and destination cannot disagree. The keywords are the
measured queries that admitted the page plus the words of that title; the link
rebalancer and the autopilot match them against a page's subject.

The output is committed. CI has no sibling checkouts and no network, so the
validators read the committed file; this script is the operator refresh:

    python3 scripts/build_portfolio_deep_targets.py --write
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
GITHUB = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts"))
from affiliation import portfolio_domains, host_of  # noqa: E402

OUT = ROOT / "data/portfolio-deep-targets.json"
SOURCES = [
    ("p-n-p", "data/search_intelligence/target_query_set.json", "porchandparty901.com"),
    ("approvalprep", "data/search_intelligence/target_query_set.json", "approvalprep.com"),
    ("dream-wedding-builder", "data/search_intelligence/target_query_set.json", None),
    ("local-guides-generator", "data/search_intelligence/dentistryguides.com/target_query_set.json", "dentistryguides.com"),
    ("local-guides-generator", "data/search_intelligence/hormonesivhair.com/target_query_set.json", "hormonesivhair.com"),
    ("local-guides-generator", "data/search_intelligence/neuroevalguides.com/target_query_set.json", "neuroevalguides.com"),
    ("local-guides-generator", "data/search_intelligence/theaccidentguides.com/target_query_set.json", "theaccidentguides.com"),
    ("local-guides-generator", "data/search_intelligence/uscisexam.com/target_query_set.json", "uscisexam.com"),
    ("local-guides-generator", "data/search_intelligence/strengthened_pages.json", None),
    ("WPP-llm", "data/seo/measured_targets.json", "westpeekproductions.com"),
    ("sprylabs-hpc-site", "data/search_intelligence/target_query_set.json", None),
    # 25 Oct 2026: the owner reclassified hicksconsulting.org from a client
    # property to a grid repo, so its links are followed editorial links and it
    # needs a catalogue like every other portfolio domain -- without one the
    # rebalancer's capacity for it is zero and it unlinks every citation.
    ("hicks-consulting-canonical", "data/search_intelligence/target_query_set.json", "hicksconsulting.org"),
]
ROUTE_KEYS = ("expected_owned_route", "owner_route", "owned_route", "route", "expected_owned_url",
              "url", "page", "pages")
# Pages that are never an editorial destination.
EXCLUDE_PATH = re.compile(r"^/(privacy|terms|cookie|legal|contact|login|account|cart|checkout|states/)", re.I)
# A candidate whose URL or title names the parent company is never a
# destination. These publications name no parent (see
# scripts/validators/validate_no_parent_company.py, which hard-fails on the
# string anywhere in a generator or a data file): on 25 Oct 2026 a refresh
# admitted billionairehighperformancecoach.com/spry-labs, whose <title> carries
# it, and the validator caught the catalogue rather than a page -- which is the
# guard working, and also a candidate this builder should never have offered.
EXCLUDE_PARENT = re.compile(r"spry[\s-]*labs", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
MAX_PER_DOMAIN = 25
UA = "Mozilla/5.0 (compatible; AuthorityNetworkLinkCheck/1.0)"


def read_source(repo: str, rel: str):
    path = GITHUB / repo
    if not path.exists():
        return None
    try:
        blob = subprocess.run(["git", "-C", str(path), "show", f"origin/main:{rel}"],
                              capture_output=True, text=True, check=True).stdout
        return json.loads(blob)
    except (subprocess.CalledProcessError, ValueError):
        f = path / rel
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def walk(node, default_host, out, query=""):
    if isinstance(node, list):
        for item in node:
            walk(item, default_host, out, query)
        return
    if not isinstance(node, dict):
        return
    q = str(node.get("query") or query or "")
    host = node.get("host") or default_host
    weight = 0
    for key in ("impressions", "volume", "number", "value"):
        if isinstance(node.get(key), (int, float)):
            weight = max(weight, node[key])
    for key in ROUTE_KEYS:
        value = node.get(key)
        for v in (value if isinstance(value, list) else [value]):
            if not isinstance(v, str) or not v:
                continue
            if v.startswith("http"):
                h, path = host_of(v), urlparse(v).path or "/"
            elif v.startswith("/") and host:
                h, path = host_of(host), v
            else:
                continue
            out.append((h, path, q, weight))
    for key, value in node.items():
        if isinstance(value, dict) and key.endswith((".com", ".org")):
            walk(value, key, out, q)
        elif isinstance(value, (dict, list)) and key not in ROUTE_KEYS:
            walk(value, host, out, q)


def pantry_links():
    pantry = json.loads((ROOT / "content-bank/yearly-pantry.json").read_text(encoding="utf-8"))
    for pub in pantry["publications"].values():
        for target in pub.get("targets", []):
            if not isinstance(target, dict):
                continue
            for link in target.get("approved_links", []):
                url = str((link or {}).get("url", ""))
                if url.startswith("http"):
                    yield host_of(url), urlparse(url).path or "/", str(link.get("anchor", "")), 0


def fetch(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            final = resp.geturl()
            body = resp.read(400_000).decode("utf-8", "ignore")
            return resp.status, final, body
    except Exception as exc:  # noqa: BLE001 - any failure means "not a destination"
        return getattr(exc, "code", 0), url, ""


def clean_title(raw: str) -> str:
    title = html.unescape(re.sub(r"\s+", " ", raw)).strip()
    # Drop a trailing " | Site" / " - Site" / " — Site" brand suffix.
    parts = re.split(r"\s+[|—–-]\s+", title)
    if len(parts) > 1 and len(parts[0]) >= 12:
        title = parts[0]
    return title.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    portfolio = portfolio_domains()
    raw: list[tuple] = []
    for repo, rel, host in SOURCES:
        data = read_source(repo, rel)
        if data is None:
            print(f"  skip {repo}:{rel} (no checkout)")
            continue
        walk(data, host, raw)
    raw.extend(pantry_links())

    by_url: dict[str, dict] = {}
    for h, path, q, weight in raw:
        if h not in portfolio or EXCLUDE_PATH.match(path) or EXCLUDE_PARENT.search(path):
            continue
        canonical_host = h
        url = f"https://{canonical_host}{path}"
        row = by_url.setdefault(url, {"url": url, "domain": h, "queries": set(), "weight": 0})
        if q:
            row["queries"].add(q.lower().strip())
        row["weight"] = max(row["weight"], weight)

    candidates = sorted(by_url.values(), key=lambda r: (r["domain"], -r["weight"], r["url"]))
    print(f"  candidates: {len(candidates)} across {len({r['domain'] for r in candidates})} domains")
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda r: fetch(r["url"]), candidates))

    targets: dict[str, list] = {}
    dropped = []
    for row, (status, final, body) in zip(candidates, results):
        m = TITLE_RE.search(body or "")
        same_host = host_of(final) == row["domain"]
        if status != 200 or not m or not same_host:
            dropped.append({"url": row["url"], "status": status, "final": final,
                            "reason": "not 200 on its own host" if status != 200 or not same_host
                            else "no <title>"})
            continue
        final_url = final if final.startswith("https://") else row["url"]
        title = clean_title(m.group(1))
        if not title:
            continue
        # The anchor IS the page's <title>, so a page titled for the parent
        # company would put that name on these publications. Checked here as
        # well as on the URL: the title is only known after the fetch.
        if EXCLUDE_PARENT.search(title):
            dropped.append({"url": row["url"], "status": status, "final": final,
                            "reason": "title names the parent company"})
            continue
        bucket = targets.setdefault(row["domain"], [])
        if any(t["url"] == final_url for t in bucket) or len(bucket) >= MAX_PER_DOMAIN:
            continue
        is_home = urlparse(final_url).path in ("", "/")
        bucket.append({"url": final_url, "title": title, "home": is_home,
                       "queries": sorted(row["queries"])[:12], "measured_weight": row["weight"]})
    for bucket in targets.values():
        # Deep pages first, strongest measurement first.
        bucket.sort(key=lambda t: (t["home"], -t["measured_weight"], t["url"]))

    doc = {
        "schema_version": "1.0",
        "built_by": "scripts/build_portfolio_deep_targets.py",
        "rule": ("Each entry answered HTTP 200 on its own host when built; its anchor is the page's "
                 "own <title>. Deep pages come from each target repo's measured target set; "
                 "homepages are kept only as a last resort for topic matching."),
        "targets": dict(sorted(targets.items())),
        "dropped": dropped,
    }
    summary = {d: len(v) for d, v in sorted(targets.items())}
    print("  kept per domain:", json.dumps(summary))
    print(f"  dropped: {len(dropped)}")
    if args.write:
        OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  wrote {OUT.relative_to(ROOT)}")
    return 0 if targets else 1


if __name__ == "__main__":
    raise SystemExit(main())
