#!/usr/bin/env python3
"""Weekly: does every sameAs profile in data/entities/*.json still resolve and link back?

For each entity file:
  sameAs           fetched (browser UA, redirects followed).
                     2xx + page names the site host  -> ok
                     2xx on a JS-rendered platform   -> `unverifiable` (a named state, never a pass)
                     2xx, server-rendered, no host   -> NAMED STOP: missing link-back, with the field to edit
                     not 2xx                          -> dead: removed from sameAs (--write), noted in the report
  profiles_pending fetched the same way; one that resolves AND links back is promoted into sameAs (--write).

`--write` edits the entity files; the workflow then rebuilds the pages from them
(scripts/lib/head_seo.py reads the entity file) and opens a pull request, so a
dead profile leaves the JSON-LD through the same release gate as any change.

Rule 0: with no profiles anywhere the run prints a NAMED STOP saying so -- the
publications have no independent profiles yet -- rather than a silent pass.
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
ENTITIES = ROOT / "data/entities"
REPORT = ROOT / "reports/entity-backlink-watch.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
JS_RENDERED = {"instagram.com", "gumroad.com", "maps.google.com", "google.com", "threads.net", "tiktok.com", "x.com", "twitter.com"}
EDIT_FIELD = {
    "facebook.com": "Page > About > Website",
    "pinterest.com": "Profile > Edit profile > Website",
    "youtube.com": "Channel > Customise > Basic info > Links",
    "github.com": "Organisation > Settings > URL",
    "linkedin.com": "Company page > Edit page > Website URL",
    "crunchbase.com": "Organization > Edit > Website",
}


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def platform(url: str) -> str:
    h = host(url)
    return next((p for p in set(JS_RENDERED) | set(EDIT_FIELD) if h == p or h.endswith("." + p)), h)


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read(3_000_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception:  # noqa: BLE001 - unreachable is a dead result, recorded as such
        return 0, ""


def classify(url: str, site: str, fetcher=fetch) -> dict:
    status, body = fetcher(url)
    plat = platform(url)
    if not 200 <= status < 300:
        state = "dead"
    elif plat in JS_RENDERED:
        state = "unverifiable"
    elif site in body.lower():
        state = "ok"
    else:
        state = "missing_link_back"
    return {"url": url, "http": status, "state": state, "platform": plat,
            "edit_field": EDIT_FIELD.get(plat, "the profile's website field")}


def watch(write: bool, fetcher=fetch) -> dict:
    files = sorted(ENTITIES.glob("*.json"))
    if not files:
        raise SystemExit("Rule 0: no entity files under data/entities/")
    out, stops, changed = [], [], []
    for path in files:
        site = path.stem
        entity = json.loads(path.read_text(encoding="utf-8"))
        same = [classify(u, site, fetcher) for u in entity.get("sameAs", [])]
        pend = [classify(p if isinstance(p, str) else p["url"], site, fetcher) for p in entity.get("profiles_pending", [])]
        dead = [r["url"] for r in same if r["state"] == "dead"]
        promote = [r["url"] for r in pend if r["state"] == "ok"]
        for r in same:
            if r["state"] == "missing_link_back":
                stops.append(f"NAMED STOP {site}: {r['url']} does not link back to {site}. "
                             f"Owner login: set {r['edit_field']} to https://{site}/")
            elif r["state"] == "unverifiable":
                stops.append(f"UNVERIFIABLE {site}: {r['url']} is JS-rendered; link-back cannot be read server-side")
        if write and (dead or promote):
            entity["sameAs"] = [u for u in entity["sameAs"] if u not in dead] + promote
            entity["profiles_pending"] = [p for p in entity["profiles_pending"]
                                          if (p if isinstance(p, str) else p["url"]) not in promote]
            path.write_text(json.dumps(entity, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            changed.append({"entity": site, "removed_dead": dead, "promoted": promote})
        out.append({"entity": site, "sameAs": same, "profiles_pending": pend, "removed_dead": dead, "promoted": promote})
    if not any(r["sameAs"] or r["profiles_pending"] for r in out):
        stops.append("NAMED STOP entity-watch: no entity has a sameAs or pending profile yet; nothing to verify.")
    report = {"date": date.today().isoformat(), "entities": out, "changed": changed, "named_stops": stops}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="self-heal: drop dead sameAs, promote resolving pending profiles")
    report = watch(ap.parse_args().write)
    for s in report["named_stops"]:
        print(s, file=sys.stderr)
    print(json.dumps({"status": "PASS", "entities": len(report["entities"]), "changed": report["changed"],
                      "named_stops": len(report["named_stops"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
