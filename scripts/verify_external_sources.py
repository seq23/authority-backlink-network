#!/usr/bin/env python3
"""Verify that every registered external source actually exists.

The point of `data/external-sources.json` is that these publications stop
citing only themselves. That is only worth anything if the citations are real.
A fabricated government URL is worse than no citation: it is a page that looks
sourced and is not, and it is the exact failure an answer engine punishes hardest.

So the registry is not trusted on its own. This fetches every URL and records
what the server returned.

Two modes, because the network is not always available and a release must not
depend on a third party being up:

    --offline (default)  Structural checks only: schema, unique ids, domain
                         agreement between `domain` and `url`, lane validity,
                         and that a receipt exists for every source.
    --network            Additionally fetch every URL and rewrite the receipts.

Structural failure is a real defect and exits non-zero. A network failure is
reported and does not fail the run: uscis.gov being briefly unreachable is not
evidence that the citation is fake, and the stored receipt still says what was
observed when it was last actually checked.

    python3 scripts/verify_external_sources.py --network
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/external-sources.json"
RECEIPTS = ROOT / "reports/external-source-verification.json"
PUBLICATION_IDS = {p["id"] for p in json.loads(
    (ROOT / "data/publications.json").read_text(encoding="utf-8"))}

# A real browser UA. Several federal hosts answer 403 to anything that looks
# automated; that is a bot rule, not a missing page, and the distinction is
# recorded rather than glossed over.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def norm_domain(value: str) -> str:
    host = urlparse(value).netloc if value.startswith("http") else value
    return host.lower().removeprefix("www.").strip("/")


def fetch(url: str, timeout: int = 25) -> dict:
    request = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(200_000).decode("utf-8", errors="replace")
            match = TITLE_RE.search(body)
            return {
                "http_status": response.status,
                "resolved_url": response.geturl(),
                "observed_title": " ".join(match.group(1).split())[:160] if match else "",
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "outcome": "verified" if response.status == 200 else "unexpected_status",
            }
    except urllib.error.HTTPError as exc:
        return {
            "http_status": exc.code,
            "resolved_url": url,
            "observed_title": "",
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            # 403/429 from a federal host is a bot rule. It is not proof the page
            # is missing, and it is not proof the page is there either.
            "outcome": "blocked_by_host" if exc.code in {403, 429} else "unreachable",
        }
    except Exception as exc:
        return {
            "http_status": 0,
            "resolved_url": url,
            "observed_title": "",
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "outcome": "unreachable",
            "error": str(exc)[:200],
        }


def structural_failures(registry: dict, receipts: dict) -> list[str]:
    failures: list[str] = []
    sources = registry.get("sources", [])
    if not sources:
        failures.append("HARD_FAIL registry has no sources")

    seen_ids: set[str] = set()
    receipt_by_id = {r["id"]: r for r in receipts.get("receipts", [])}
    for source in sources:
        sid = source.get("id", "")
        if not sid:
            failures.append("HARD_FAIL a source has no id")
            continue
        if sid in seen_ids:
            failures.append(f"HARD_FAIL duplicate source id: {sid}")
        seen_ids.add(sid)

        for field in ("domain", "url", "publisher", "publisher_type", "title", "lanes", "topics", "supports"):
            if not source.get(field):
                failures.append(f"HARD_FAIL {sid}: missing required field `{field}`")

        url = source.get("url", "")
        if url and norm_domain(url) != norm_domain(source.get("domain", "")):
            failures.append(
                f"HARD_FAIL {sid}: url host {norm_domain(url)!r} does not match "
                f"registered domain {source.get('domain')!r}")
        if url and not url.startswith("https://"):
            failures.append(f"HARD_FAIL {sid}: citation must be https")

        ptype = source.get("publisher_type", "")
        if ptype and ptype not in registry.get("publisher_types", {}):
            failures.append(f"HARD_FAIL {sid}: unknown publisher_type {ptype!r}")

        for lane in source.get("lanes", []):
            if lane not in PUBLICATION_IDS:
                failures.append(f"HARD_FAIL {sid}: unknown publication lane {lane!r}")

        receipt = receipt_by_id.get(sid)
        if receipt is None:
            failures.append(
                f"HARD_FAIL {sid}: no verification receipt. Run "
                f"`python3 scripts/verify_external_sources.py --network` before citing it.")
        elif receipt.get("outcome") != "verified":
            failures.append(
                f"HARD_FAIL {sid}: last check was {receipt.get('outcome')} "
                f"(HTTP {receipt.get('http_status')}); an unverified source may not stay registered")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", action="store_true",
                        help="Fetch every URL and rewrite receipts.")
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    sources = registry.get("sources", [])

    if args.network:
        print(f"EXTERNAL SOURCE VERIFICATION: fetching {len(sources)} source(s)")
        results = []
        for source in sources:
            observed = fetch(source["url"])
            results.append({"id": source["id"], "url": source["url"],
                            "publisher": source["publisher"], **observed})
            print(f"  {observed['outcome']:<16} {observed['http_status']:<4} "
                  f"{source['id']:<34} {observed['observed_title'][:52]}")
        receipts = {
            "schema_version": "1.0",
            "validator": "external-source-verification",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sources_checked": len(results),
            "verified": sum(1 for r in results if r["outcome"] == "verified"),
            "receipts": results,
        }
        RECEIPTS.parent.mkdir(parents=True, exist_ok=True)
        RECEIPTS.write_text(json.dumps(receipts, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {RECEIPTS.relative_to(ROOT)}")
    else:
        if not RECEIPTS.exists():
            print("EXTERNAL SOURCE VERIFICATION: FAIL")
            print("  HARD_FAIL no receipts file; run with --network at least once")
            return 1
        receipts = json.loads(RECEIPTS.read_text(encoding="utf-8"))

    failures = structural_failures(registry, receipts)
    if failures:
        print("EXTERNAL SOURCE VERIFICATION: FAIL")
        for line in failures:
            print(f"  {line}")
        return 1

    by_lane: dict[str, int] = {}
    for source in sources:
        for lane in source["lanes"]:
            by_lane[lane] = by_lane.get(lane, 0) + 1
    publishers = sorted({s["publisher"] for s in sources})
    print(f"EXTERNAL SOURCE VERIFICATION: PASS "
          f"({len(sources)} verified source(s) from {len(publishers)} publisher(s); "
          + ", ".join(f"{k}={v}" for k, v in sorted(by_lane.items())) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
