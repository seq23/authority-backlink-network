#!/usr/bin/env python3
"""The earned-mention ledger (data/earned-mentions.json) and the Wikidata gate.

    add            record a landed journalist-query response (URL + outlet + brand)
    check          weekly: every row still resolves (2xx) and still names the brand
    wikidata-gate  a brand is Wikidata-eligible only with >= 2 independent earned URLs

Independent means: the article's host is not a portfolio domain
(data/portfolio-link-policy.json owner_portfolio_domains), not a network
publication (data/publications.json), and each counted URL is on a distinct
outlet host. A row that last failed `check` does not count. A brand's own sites
and the network never count, so a Wikidata item created from an eligible brand
always cites outside references. Wikipedia is never written for a brand.

Rule 0: an empty ledger is not a pass that hides anything -- `check` and
`wikidata-gate` print a NAMED STOP saying no earned mention has landed yet.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data/earned-mentions.json"
REPORT = ROOT / "reports/earned-mentions.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def owned_hosts(root: Path = ROOT) -> set[str]:
    policy = json.loads((root / "data/portfolio-link-policy.json").read_text(encoding="utf-8"))
    pubs = json.loads((root / "data/publications.json").read_text(encoding="utf-8"))
    return set(policy["owner_portfolio_domains"]) | {p["working_domain"] for p in pubs}


def brand_names(root: Path = ROOT) -> dict[str, str]:
    brands = json.loads((root / "data/brands.json").read_text(encoding="utf-8"))
    return {b["domain"]: b["name"] for b in brands}


def load(path: Path = LEDGER) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(data: dict, path: Path = LEDGER) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def eligibility(rows: list[dict], owned: set[str]) -> dict[str, dict]:
    """{brand_domain: {independent_urls, eligible}} -- the gate, as a pure function."""
    out: dict[str, dict] = {}
    for r in rows:
        d = r["brand_domain"]
        slot = out.setdefault(d, {"independent_urls": [], "outlet_hosts": set(), "eligible": False})
        h = host(r["url"])
        if h in owned or h == d or r.get("last_check", {}).get("ok") is False:
            continue
        if h in slot["outlet_hosts"]:
            continue
        slot["outlet_hosts"].add(h)
        slot["independent_urls"].append(r["url"])
    for d, slot in out.items():
        slot["eligible"] = len(slot["independent_urls"]) >= 2
        slot["outlet_hosts"] = sorted(slot["outlet_hosts"])
    return out


def cmd_add(a) -> int:
    data = load()
    if host(a.url) in owned_hosts():
        raise SystemExit(f"{a.url}: an owned or network site is not an earned mention")
    if any(r["url"] == a.url for r in data["mentions"]):
        raise SystemExit(f"{a.url}: already in the ledger")
    data["mentions"].append({"url": a.url, "outlet": a.outlet, "brand_domain": a.brand_domain,
                             "query_id": a.query_id or "", "landed": a.landed or date.today().isoformat()})
    save(data)
    print(json.dumps({"status": "PASS", "added": a.url}))
    return 0


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read(2_000_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception:  # noqa: BLE001 - a network error is a failed check, recorded as such
        return 0, ""


def cmd_check(_a) -> int:
    data = load()
    names = brand_names()
    if not data["mentions"]:
        print("NAMED STOP earned-mentions: no journalist-query response has landed yet; the ledger is empty.", file=sys.stderr)
    for r in data["mentions"]:
        status, body = fetch(r["url"])
        low = body.lower()
        names_brand = r["brand_domain"] in low or names.get(r["brand_domain"], "\0").lower() in low
        r["last_check"] = {"date": date.today().isoformat(), "http": status,
                           "names_brand": names_brand, "ok": 200 <= status < 300 and names_brand}
    save(data)
    bad = [r["url"] for r in data["mentions"] if not r["last_check"]["ok"]]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"checked": len(data["mentions"]), "failing": bad,
                                  "wikidata": eligibility(data["mentions"], owned_hosts())}, indent=2) + "\n")
    for url in bad:
        print(f"NAMED STOP earned-mention {url}: no longer resolves or no longer names the brand", file=sys.stderr)
    print(json.dumps({"status": "PASS", "checked": len(data["mentions"]), "failing": len(bad)}))
    return 0


def cmd_gate(_a) -> int:
    data = load()
    result = eligibility(data["mentions"], owned_hosts())
    if not result:
        print("NAMED STOP wikidata-gate: no brand has an earned mention yet; nothing is Wikidata-eligible.", file=sys.stderr)
    for d, slot in result.items():
        state = "ELIGIBLE" if slot["eligible"] else f"NOT YET ({len(slot['independent_urls'])}/2 independent earned URLs)"
        print(f"wikidata-gate {d}: {state}", file=sys.stderr)
    print(json.dumps({"status": "PASS", "brands": result}, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("--url", required=True)
    add.add_argument("--outlet", required=True)
    add.add_argument("--brand-domain", required=True)
    add.add_argument("--query-id")
    add.add_argument("--landed")
    sub.add_parser("check")
    sub.add_parser("wikidata-gate")
    a = ap.parse_args()
    return {"add": cmd_add, "check": cmd_check, "wikidata-gate": cmd_gate}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
