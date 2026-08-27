#!/usr/bin/env python3
"""Measure whether an affiliated placement sits on a page about its own subject.

Every daily page carries this sentence, written by the network itself:

    "this publication may cite affiliated projects where the citation is
     topically relevant"

That is a claim the pages make about themselves, so it is checkable. This
checks it, and on the professional publication it currently fails for a
little over half of the non-flagship placements: a hormone, IV and hair-loss
guide cited from a page about equine liability; a dentistry guide cited from
a page about credit report errors; the USCIS medical-exam guide cited from a
page about trauma-informed leadership.

Why it happens, which is visible in `scripts/authority_v4_autopilot.py`:

    target_cfg = normalize_target(pick(regular_targets or pub['targets'], ...))
    eligible_clusters = target_cfg.get('eligible_clusters') or pub['clusters']
    cluster = pick(eligible_clusters, seed+'cluster')

The affiliated target is drawn first. The page's subject is drawn second, and
it is constrained by the target only when that target declares
`eligible_clusters`. Six professional targets declare none, so for them the
subject and the destination are drawn independently out of 58 clusters and
land together by chance.

There is a second, quieter fallback a few lines down:

    candidate_links = [l for l in approved_links if link_matches_cluster(l, cluster)]
    if not candidate_links:
        candidate_links = target_cfg.get('approved_links', [])

The topical filter exists, and when it matches nothing it turns itself off
rather than declining to place a link.

This script reports. It changes no routing and rewrites no page, because
which brand is allowed to appear on which subject is the owner's commercial
decision and not a thing a validator should decide. It is deliberately not
wired into the blocking profiles in `validation/plan.json` for the same
reason.

    python3 scripts/measure_affiliate_topical_fit.py
    python3 scripts/measure_affiliate_topical_fit.py --json reports/affiliate-topical-fit.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

A_RE = re.compile(r"<a\s+([^>]*)>", re.I)
HREF_RE = re.compile(r'href="([^"]+)"')
REL_RE = re.compile(r'rel="([^"]*)"')


def norm(host: str) -> str:
    return host.lower().removeprefix("www.")


def page_subjects() -> dict[str, tuple[str, str]]:
    """Hub and cluster for every page, from the repo's own navigation module."""
    import build_site_navigation as nav
    from lib import site_urls

    out: dict[str, tuple[str, str]] = {}
    for pub in nav.PUBLICATIONS:
        folder = pub["folder"].split("/", 1)[1]
        members, _ = nav.assign_members(
            ROOT / pub["folder"], site_urls.domain_of(pub), nav.load_hubs(pub["id"]))
        for slug, rows in members.items():
            for row in rows:
                out[f'{folder}/{row["rel"]}'] = (slug, (row.get("cluster") or "").strip().lower())
    return out


def declared_scope() -> dict[str, set[str]]:
    """Clusters each target is allowed on, as the pantry itself declares them.

    Keyed by every host the target can actually be reached at, not only its
    `domain` field. dream-wedding-builder is one target whose `domain` is
    weddingchecklistpdf.com but whose approved_links span four sibling domains
    for the same product family. Keying on `domain` alone reported the other
    three - 46 placements - as `target_not_in_pantry`, as though the network
    were citing strangers. They are the same target, under the same declared
    scope, reached through a mirror. This widens the key, not the scope.
    """
    pantry = json.loads((ROOT / "content-bank/yearly-pantry.json").read_text(encoding="utf-8"))
    scope: dict[str, set[str]] = {}
    for pub in pantry["publications"].values():
        for target in pub.get("targets", []):
            if not isinstance(target, dict):
                continue
            hosts = {norm(str(target.get("domain", "")))}
            for link in target.get("approved_links", []):
                if isinstance(link, dict) and str(link.get("url", "")).startswith("http"):
                    hosts.add(norm(urlparse(link["url"]).netloc))
            eligible = target.get("eligible_clusters")
            for host in hosts:
                if not host:
                    continue
                # A target with no declared scope is recorded as unbounded rather
                # than as "matches everything": that distinction is the finding.
                scope.setdefault(host, set())
                if eligible:
                    scope[host].update(c.strip().lower() for c in eligible)
    return scope


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_out", default="reports/affiliate-topical-fit.json")
    args = parser.parse_args()

    subjects = page_subjects()
    scope = declared_scope()

    placements: list[dict] = []
    for path in sorted((ROOT / "sites").rglob("*.html")):
        if path.name == "404.html":
            continue
        rel_key = path.relative_to(ROOT / "sites").as_posix()
        hub, cluster = subjects.get(rel_key, ("(standing page)", ""))
        seen: set[str] = set()
        for attrs in A_RE.findall(path.read_text(encoding="utf-8", errors="ignore")):
            href = HREF_RE.search(attrs)
            rel = REL_RE.search(attrs)
            if not href or not rel or "sponsored" not in rel.group(1):
                continue
            host = norm(urlparse(href.group(1)).netloc)
            if host in seen:
                continue
            seen.add(host)
            declared = scope.get(host)
            if declared is None:
                verdict = "target_not_in_pantry"
            elif not declared:
                verdict = "target_declares_no_scope"
            elif not cluster:
                # A page that records no cluster is a hand-authored standing
                # page - a hub, an index, or an editorial pillar - not something
                # build_brief routed. Its affiliated link was placed by a person
                # choosing it, so "outside the target's declared clusters" is not
                # a finding about it; there is no drawn cluster to be outside of.
                # Counting these as out_of_scope, as this script used to, put 30
                # correct editorial placements in with the routing defects and
                # overstated the failure. Reported as their own population.
                verdict = "standing_page_no_cluster"
            elif cluster in declared:
                verdict = "in_scope"
            else:
                verdict = "out_of_scope"
            placements.append({"page": rel_key, "hub": hub, "cluster": cluster,
                               "target": host, "verdict": verdict})

    counts: dict[str, int] = {}
    by_target: dict[str, dict[str, int]] = {}
    for row in placements:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
        by_target.setdefault(row["target"], {})
        by_target[row["target"]][row["verdict"]] = \
            by_target[row["target"]].get(row["verdict"], 0) + 1

    total = len(placements)
    unbounded = sorted(d for d, s in scope.items() if not s)
    print("AFFILIATE TOPICAL FIT (does a paid placement sit on a page about its own subject?)")
    print(f"\n  affiliated placements examined: {total}")
    for verdict in ("in_scope", "standing_page_no_cluster", "out_of_scope",
                    "target_declares_no_scope", "target_not_in_pantry"):
        n = counts.get(verdict, 0)
        if n:
            print(f"    {verdict:26s} {n:5d}  ({n / total:5.1%})")

    print(f"\n  targets declaring no cluster scope: {len(unbounded)}")
    for domain in unbounded:
        n = sum(by_target.get(domain, {}).values())
        print(f"    {domain:38s} {n:4d} placement(s), subject drawn independently")

    print("\n  per target:")
    for domain in sorted(by_target, key=lambda d: -sum(by_target[d].values())):
        row = by_target[domain]
        bits = ", ".join(f"{k}={v}" for k, v in sorted(row.items()))
        print(f"    {domain:38s} {bits}")

    out = ROOT / args.json_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "schema_version": "1.0",
        "measurement": "affiliate-topical-fit",
        "placements_examined": total,
        "counts": counts,
        "targets_without_declared_scope": unbounded,
        "by_target": by_target,
        "out_of_scope": [r for r in placements if r["verdict"] != "in_scope"],
    }, indent=2) + "\n", encoding="utf-8")
    print(f"\n  wrote {args.json_out}")
    print("\nAFFILIATE TOPICAL FIT: measured (reporting only; routing is not changed here)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
