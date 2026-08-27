#!/usr/bin/env python3
"""Measure internal click depth from each publication's homepage.

Orphan count correlates inversely with AI citations across the measured
portfolio: the most-cited property carries 3 orphans, and every zero-citation
property is heavily orphaned. This makes that number a first-class,
reproducible measurement instead of an assertion.

A page is reachable at depth N if the shortest chain of internal <a href>
hops from the publication homepage is N links long. A page no chain reaches
is an orphan: it can be in the sitemap and still be invisible to a crawler
that only follows links, which is what a citation-seeking retriever does.

Cloudflare Pages serves extensionless routes, so `/topics/foo` resolves to
`topics/foo.html`. Resolution mirrors that, plus `foo/index.html`.

Usage:
    python3 scripts/measure_click_depth.py
    python3 scripts/measure_click_depth.py --json reports/click-depth.json
    python3 scripts/measure_click_depth.py --max-depth 3   # non-zero exit if breached
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import deque
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parents[1]
SITES = ROOT / "sites"
PUBLICATIONS = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))

ANCHOR_HREF = re.compile(r"<a\s+[^>]*?href=\"([^\"]+)\"", re.I)


def norm_host(value: str) -> str:
    return (urlparse(value).netloc or "").lower().removeprefix("www.").strip("/")


def route_of(path: Path, pub_root: Path) -> str:
    """Canonical serving route for a source file."""
    rel = path.relative_to(pub_root).as_posix()
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("/index.html")]
    return "/" + rel[: -len(".html")]


def build_route_map(pub_root: Path) -> dict[str, Path]:
    """Every route spelling that resolves to a file, so a link is only broken
    when nothing serves it -- not when it merely omitted a trailing slash."""
    route_map: dict[str, Path] = {}
    for path in sorted(pub_root.rglob("*.html")):
        canonical = route_of(path, pub_root)
        rel = path.relative_to(pub_root).as_posix()
        for spelling in {canonical, canonical.rstrip("/") or "/", "/" + rel}:
            route_map.setdefault(spelling, path)
        if canonical != "/":
            route_map.setdefault(canonical + "/", path)
    return route_map


def outbound_routes(path: Path, working_domain: str) -> set[str]:
    """Internal routes this page links to, whether written relative or absolute.

    Pages in this repo link to themselves absolutely (https://domain/route) as
    often as relatively, and a crawler treats both as the same internal edge.
    """
    html = path.read_text(encoding="utf-8", errors="ignore")
    found: set[str] = set()
    for href in ANCHOR_HREF.findall(html):
        href = unquote(href.strip())
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
            continue
        if href.startswith(("http://", "https://")):
            if norm_host(href) != working_domain:
                continue
            target = urlparse(href).path or "/"
        elif href.startswith("//"):
            continue
        elif href.startswith("/"):
            target = href
        else:
            continue  # relative-to-file links are not used by this generator
        target = target.split("#", 1)[0].split("?", 1)[0]
        found.add(target or "/")
    return found


def measure(pub: dict) -> dict:
    pub_root = ROOT / pub["folder"]
    working_domain = norm_host("https://" + pub["working_domain"])
    route_map = build_route_map(pub_root)
    all_pages = sorted(p for p in pub_root.rglob("*.html"))

    # 404 pages are served by status code, never linked; counting them as
    # orphans would inflate the number with a page that is correct as-is.
    countable = [p for p in all_pages if p.name != "404.html"]

    home = pub_root / "index.html"
    depth: dict[Path, int] = {home: 0}
    broken: list[tuple[str, str]] = []
    queue: deque[Path] = deque([home])
    while queue:
        current = queue.popleft()
        for target in sorted(outbound_routes(current, working_domain)):
            resolved = route_map.get(target) or route_map.get(target.rstrip("/") or "/")
            if resolved is None:
                broken.append((route_of(current, pub_root), target))
                continue
            if resolved not in depth:
                depth[resolved] = depth[current] + 1
                queue.append(resolved)

    histogram: dict[str, int] = {}
    for page in countable:
        key = str(depth[page]) if page in depth else "orphan"
        histogram[key] = histogram.get(key, 0) + 1
    orphans = sorted(route_of(p, pub_root) for p in countable if p not in depth)
    deep = sorted(
        (route_of(p, pub_root), depth[p]) for p in countable if depth.get(p, 0) > 3
    )
    return {
        "publication": pub["id"],
        "working_domain": pub["working_domain"],
        "pages": len(countable),
        "reachable": len(countable) - len(orphans),
        "orphans": len(orphans),
        "orphan_pct": round(100 * len(orphans) / max(len(countable), 1), 1),
        "max_depth": max((depth[p] for p in countable if p in depth), default=0),
        "depth_histogram": {k: histogram[k] for k in sorted(histogram, key=lambda x: (x == "orphan", x))},
        "beyond_depth_3": len(deep),
        "beyond_depth_3_sample": deep[:20],
        "orphan_sample": orphans[:20],
        "broken_internal_links": sorted({f"{s} -> {t}" for s, t in broken})[:20],
        "broken_internal_link_count": len({f"{s} -> {t}" for s, t in broken}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_out", default="reports/click-depth.json")
    parser.add_argument("--max-depth", type=int, default=None,
                        help="Exit non-zero if any page sits deeper than this or is orphaned.")
    args = parser.parse_args()

    results = [measure(pub) for pub in PUBLICATIONS]
    print("CLICK DEPTH FROM HOMEPAGE (internal <a href> graph)")
    breaches = 0
    for r in results:
        hist = "  ".join(f"d{k}={v}" if k != "orphan" else f"ORPHAN={v}"
                         for k, v in r["depth_histogram"].items())
        print(f"\n  {r['publication']} ({r['working_domain']})")
        print(f"    pages {r['pages']}  reachable {r['reachable']}  "
              f"orphans {r['orphans']} ({r['orphan_pct']}%)  max depth {r['max_depth']}")
        print(f"    {hist}")
        if r["broken_internal_link_count"]:
            print(f"    broken internal links: {r['broken_internal_link_count']}")
            for line in r["broken_internal_links"][:5]:
                print(f"      {line}")
        if args.max_depth is not None:
            over = r["orphans"] + sum(v for k, v in r["depth_histogram"].items()
                                      if k != "orphan" and int(k) > args.max_depth)
            if over:
                breaches += over
                print(f"    BREACH: {over} page(s) orphaned or deeper than {args.max_depth}")

    out = ROOT / args.json_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "schema_version": "1.0",
        "measurement": "internal-click-depth-from-homepage",
        "max_depth_policy": args.max_depth,
        "publications": results,
        "totals": {
            "pages": sum(r["pages"] for r in results),
            "orphans": sum(r["orphans"] for r in results),
            "beyond_depth_3": sum(r["beyond_depth_3"] for r in results),
        },
    }, indent=2) + "\n", encoding="utf-8")
    print(f"\n  wrote {args.json_out}")

    if args.max_depth is not None and breaches:
        print(f"\nCLICK DEPTH: FAIL ({breaches} page(s) beyond policy)")
        return 1
    print("\nCLICK DEPTH: measured")
    return 0


if __name__ == "__main__":
    sys.exit(main())
