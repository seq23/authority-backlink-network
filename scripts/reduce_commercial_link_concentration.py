#!/usr/bin/env python3
"""Bring one brand's share of a publication's pages back to the network's own norm.

The measurement
---------------
Every affiliated citation in this repository already carries
`rel="sponsored nofollow"`, so none of them passes a ranking signal and none of
them is worth anything to search. What they cost instead is the claim each page
makes about itself: that this is a resource library which happens to cite
affiliated projects, rather than a distribution channel for one of them.

Measured on 2026-08-28, the leading brand in each publication:

    founder-operator        virtual-agency-os      33 of 105 pages   31.4%
    memphis-local           dream-wedding-builder  53 of 104 pages   51.0%
    memphis-local           porch-party            34 of 104 pages   32.7%
    professional-resources  approval-prep         290 of 420 pages   69.0%

Two of those numbers are the same number. The two publications nobody had a
complaint about put their leading brand on 31.4% and 32.7% of their pages -
measured independently, from different campaigns, with different scheduling
weights - and they bracket one third. That is the cap this script enforces, and
the reason it is one third rather than a figure chosen to sound modest: it is
what this network does when the scheduler is working.

Where the 69% came from is not a mystery either. In
`content-bank/scaling-policy.json`, `approval-prep` was the only priority target
with `pages_per_day: 6` and no `until_rendered_coverage` to stop at; every other
priority target asks for 1 page a day and stops at a floor of 4 to 6. In
`content-bank/yearly-pantry.json` it declares 46 eligible clusters where the
other nine professional targets declare 2 to 11. `build_brief()` draws the
destination first and the subject from that destination's clusters, so 46
clusters times an unbounded daily quota is 290 pages. The generator side of this
is fixed in `scripts/authority_v4_autopilot.py`; this script deals with what it
already published.

What it does, and does not do
-----------------------------
It removes the affiliated citation from the surplus pages and recomposes each
page around its absence, through `repair_offtopic_affiliate_links`, which first
requires the page to be reproducible byte-for-byte from its own recorded values
before it is allowed to replace it. Nothing is retitled, retired, noindexed or
argued differently: `data/back_catalogue_decision.json` records DO_NOT_RESHAPE
for the 585 pre-2026-08-26 pages, and a citation is not an editorial argument.

It never adds a link. Spreading placements onto pages that do not want them
would be a worse footprint than the concentration, and there is nowhere to
spread them to in any case: approval-prep's 46 clusters have zero overlap with
any other professional target's declared scope, so not one of these placements
can be honestly retargeted rather than removed.

Which pages keep the link is chosen for breadth, not recency alone: a
round-robin over the subjects the brand covers, newest first inside each
subject, so the kept set still spans every cluster the brand is scoped to
instead of collapsing onto whichever weeks generated most. Pages published
2026-08-26 or later - the new-template cohort `back_catalogue_decision.json`
asks to leave accumulating for re-measurement - and hand-authored standing pages
are kept and counted against the cap rather than stripped.

    python3 scripts/reduce_commercial_link_concentration.py            # dry run
    python3 scripts/reduce_commercial_link_concentration.py --write
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import measure_affiliate_topical_fit as fit  # noqa: E402
import repair_offtopic_affiliate_links as repair  # noqa: E402

SCALING = json.loads((ROOT / "content-bank/scaling-policy.json").read_text(encoding="utf-8"))
PANTRY = json.loads((ROOT / "content-bank/yearly-pantry.json").read_text(encoding="utf-8"))

# The date the page template changed. back_catalogue_decision.json asks for the
# pages published on or after it to be left alone and re-measured in 60 days;
# stripping their citations would spend the cohort the measurement depends on.
NEW_TEMPLATE_COHORT = "2026-08-26"
DATED_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-")


def cap_share() -> float:
    limits = SCALING.get("hard_limits", {})
    share = limits.get("max_brand_page_share_per_publication")
    if share is None:
        raise SystemExit(
            "content-bank/scaling-policy.json: hard_limits.max_brand_page_share_per_publication "
            "is missing. The cap is policy and is not defaulted here."
        )
    return float(share)


def host_to_brand() -> dict[str, str]:
    """Every host an owned target can be reached at, mapped to its brand id.

    Keyed off approved_links as well as `domain` for the same reason
    measure_affiliate_topical_fit does it: dream-wedding-builder is one brand
    behind four sibling domains, and counting them separately would report a
    51% penetration as four unremarkable ones.
    """
    out: dict[str, str] = {}
    for pub in PANTRY["publications"].values():
        for target in pub.get("targets", []):
            if not isinstance(target, dict):
                continue
            brand = target.get("brand_id", "")
            if not brand:
                continue
            out[fit.norm(str(target.get("domain", "")))] = brand
            for link in target.get("approved_links", []):
                if isinstance(link, dict) and str(link.get("url", "")).startswith("http"):
                    out[fit.norm(urlparse(link["url"]).netloc)] = brand
    out.pop("", None)
    return out


def survey() -> tuple[dict, dict, dict]:
    """Pages per publication, and the brands cited on each page."""
    brands = host_to_brand()
    subjects = fit.page_subjects()
    pages_by_pub: dict[str, list[Path]] = defaultdict(list)
    cited: dict[Path, dict[str, int]] = {}
    clusters: dict[Path, str] = {}

    for path in sorted((ROOT / "sites").rglob("*.html")):
        if path.name == "404.html":
            continue
        rel_key = path.relative_to(ROOT / "sites").as_posix()
        folder = path.relative_to(ROOT / "sites").parts[0]
        pages_by_pub[folder].append(path)
        clusters[path] = subjects.get(rel_key, ("", ""))[1]
        counts: dict[str, int] = defaultdict(int)
        for attrs in fit.A_RE.findall(path.read_text(encoding="utf-8", errors="ignore")):
            href = fit.HREF_RE.search(attrs)
            rel = fit.REL_RE.search(attrs)
            if not href or not rel or "sponsored" not in rel.group(1):
                continue
            brand = brands.get(fit.norm(urlparse(href.group(1)).netloc))
            if brand:
                counts[brand] += 1
        cited[path] = dict(counts)
    return pages_by_pub, cited, clusters


def strippable(path: Path, brand: str, cited: dict, clusters: dict) -> bool:
    """A page whose citation this script is allowed to remove.

    Excluded: pages with no recorded cluster (hand-authored standing pages,
    hubs and indexes, whose citation a person chose deliberately), the
    new-template cohort, and any page citing more than one brand - the
    composer removes *the* citation, so a page carrying two would silently
    lose both.
    """
    if not clusters.get(path):
        return False
    if len(cited.get(path, {})) != 1 or brand not in cited.get(path, {}):
        return False
    match = DATED_NAME.match(path.name)
    return bool(match) and match.group(1) < NEW_TEMPLATE_COHORT


def keep_order(pages: list[Path], clusters: dict) -> list[Path]:
    """Round-robin over clusters, newest first inside each cluster.

    Keeping simply the newest N would keep whichever subjects the generator
    happened to draw most recently and drop whole clusters. Breadth is the
    point: a brand cited three times across forty subjects reads as a resource
    that keeps coming up, and forty times across three reads as a placement.
    """
    by_cluster: dict[str, list[Path]] = defaultdict(list)
    for path in pages:
        by_cluster[clusters[path]].append(path)
    for group in by_cluster.values():
        group.sort(key=lambda p: (p.name, p.as_posix()), reverse=True)
    ordered: list[Path] = []
    for depth in range(max((len(g) for g in by_cluster.values()), default=0)):
        for cluster in sorted(by_cluster):
            group = by_cluster[cluster]
            if depth < len(group):
                ordered.append(group[depth])
    return ordered


def withdraw_registry_rows(removed: dict[Path, str], today: str) -> int:
    """Retire the ledger rows for citations that no longer exist on the page.

    Deleting them would erase the fact that the placement was ever made, and
    leaving them at `published` would make `citation_control` right to fail:
    the ledger would claim a rendered link the page does not carry. They move
    back to `approved_destination`, which is what they now truthfully are - an
    approved destination with no page currently citing it - and carry the date
    and reason they were withdrawn.
    """
    path = ROOT / "data/link-registry.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    stripped = {p.relative_to(ROOT).as_posix() for p in removed}
    touched = 0
    for row in rows:
        if row.get("status") != "published":
            continue
        if row.get("source_path") not in stripped:
            continue
        row["status"] = "withdrawn"
        row["lifecycle_stage"] = "approved_destination"
        row["withdrawn_on"] = today
        row["withdrawn_reason"] = (
            "brand_page_share_cap: the citation was removed from the page to bring the brand "
            "back under hard_limits.max_brand_page_share_per_publication. The destination is "
            "still approved; no page currently cites it from here."
        )
        evidence = row.setdefault("evidence", {})
        for key in evidence:
            evidence[key] = False
        touched += 1
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return touched


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="apply the reduction")
    ap.add_argument("--json", dest="json_out",
                    default="reports/commercial-link-concentration.json")
    args = ap.parse_args()

    share = cap_share()
    pages_by_pub, cited, clusters = survey()

    plan: list[dict] = []
    before: dict[tuple[str, str], int] = {}
    for pub, pages in sorted(pages_by_pub.items()):
        total = len(pages)
        allowed = int(total * share)
        by_brand: dict[str, list[Path]] = defaultdict(list)
        for path in pages:
            for brand in cited[path]:
                by_brand[brand].append(path)
        for brand, carrying in sorted(by_brand.items()):
            before[(pub, brand)] = len(carrying)
            if len(carrying) <= allowed:
                continue
            candidates = [p for p in carrying if strippable(p, brand, cited, clusters)]
            protected = len(carrying) - len(candidates)
            # Protected pages are counted against the cap, not exempted from it.
            keep_from_candidates = max(0, allowed - protected)
            ordered = keep_order(candidates, clusters)
            plan.append({
                "publication": pub,
                "brand": brand,
                "publication_pages": total,
                "allowed": allowed,
                "carrying_before": len(carrying),
                "protected": protected,
                "to_remove": len(candidates) - keep_from_candidates,
                # Least-preferred first, so a page that cannot be recomposed is
                # replaced by the next candidate rather than leaving the brand
                # over the cap. Two memphis pages predate the current template
                # and cannot be read back; the cap is still met without them.
                "order": list(reversed(ordered)),
            })

    today = date.today().isoformat()
    stripped: dict[Path, str] = {}
    failures: list[str] = []
    for row in plan:
        done = 0
        for path in row["order"]:
            if done >= row["to_remove"]:
                break
            try:
                updated = repair.recompose_without_citation(path)
            except (ValueError, KeyError) as exc:
                failures.append(f"{path.relative_to(ROOT)}: {exc}")
                continue
            if args.write:
                path.write_text(updated, encoding="utf-8")
            stripped[path] = row["brand"]
            done += 1
        row["removed"] = done
        row["shortfall"] = row["to_remove"] - done

    registry_rows = withdraw_registry_rows(stripped, today) if args.write else 0

    report = {
        "schema_version": "1.0",
        "measurement": "commercial-link-concentration",
        "measured_on": today,
        "cap": {
            "max_brand_page_share_per_publication": share,
            "evidence": (
                "The leading brand in the two publications with no concentration complaint "
                "measures 31.4% (virtual-agency-os, founder-operator) and 32.7% "
                "(porch-party, memphis-local) of their pages. The cap is the third they bracket."
            ),
        },
        "applied": bool(args.write),
        "pages_stripped": len(stripped),
        "links_removed": sum(cited[p].get(b, 0) for p, b in stripped.items()),
        "registry_rows_withdrawn": registry_rows,
        "links_retargeted": 0,
        "retargeting_note": (
            "Zero, and not for want of trying: approval-prep's 46 declared clusters share no "
            "member with any other professional target's declared scope, so there is no page "
            "among these on which another brand is in scope. Placing one anyway would trade a "
            "concentration footprint for an off-topic one."
        ),
        "brands": [
            {
                "publication": row["publication"],
                "brand": row["brand"],
                "publication_pages": row["publication_pages"],
                "pages_before": row["carrying_before"],
                "pages_after": row["carrying_before"] - row["removed"],
                "share_before": round(row["carrying_before"] / row["publication_pages"], 4),
                "share_after": round(
                    (row["carrying_before"] - row["removed"]) / row["publication_pages"], 4),
                "cap_pages": row["allowed"],
                "protected_from_stripping": row["protected"],
                "shortfall": row["shortfall"],
            }
            for row in plan
        ],
        "failures": failures,
    }

    out = ROOT / args.json_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    verb = "removed" if args.write else "would remove"
    print("COMMERCIAL LINK CONCENTRATION")
    print(f"\n  cap: no brand on more than {share:.1%} of its publication's pages")
    if not plan:
        print("\n  no brand is over the cap.")
    for row in report["brands"]:
        print(f"\n  {row['publication']} / {row['brand']}")
        print(f"    pages carrying it: {row['pages_before']} -> {row['pages_after']}"
              f"  of {row['publication_pages']}"
              f"  ({row['share_before']:.1%} -> {row['share_after']:.1%}, cap {row['cap_pages']})")
        print(f"    kept without stripping (standing page or new-template cohort): "
              f"{row['protected_from_stripping']}")
    print(f"\n  pages {'rewritten' if args.write else 'to rewrite'}: {len(stripped)}")
    print(f"  affiliated links {verb}: {report['links_removed']}")
    print(f"  affiliated links retargeted: 0 (no in-scope alternative exists; see report)")
    if args.write:
        print(f"  ledger rows withdrawn: {registry_rows}")
    if failures:
        print(f"\n  SKIPPED, could not be read back and recomposed ({len(failures)}); "
              f"the next candidate was used instead:")
        for line in failures:
            print(f"    - {line}")
    print(f"\n  wrote {args.json_out}")
    if not args.write:
        print("\n  dry run. Re-run with --write to apply.")
    return 1 if any(r["shortfall"] for r in plan) else 0


if __name__ == "__main__":
    raise SystemExit(main())
