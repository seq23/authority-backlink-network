#!/usr/bin/env python3
"""An affiliated citation must sit on a page about its own subject.

Every daily page in this network carries a sentence it wrote about itself:

    "this publication may cite affiliated projects where the citation is
     topically relevant"

That is a claim, so it is checkable, and across 598 affiliated placements it
used to be false for about 39% of them. uscisexam.com - the single property in
this portfolio earning AI citations - was cited from a page about
trauma-informed leadership. dentistryguides.com from a page about credit-report
errors. hormonesivhair.com from a page about equine liability. A publication
that discloses its affiliations and then places them at random has not
disclosed anything; it has printed a sentence.

Two lines in scripts/authority_v4_autopilot.py produced it:

    eligible_clusters = target_cfg.get('eligible_clusters') or pub['clusters']

A target that declared no scope inherited every cluster the publication had, so
the page's subject and its paid destination were drawn independently and landed
together only by chance. Eight of seventeen targets declared no scope, and every
one of their approved links carried `topics: ['*']`, so the topical filter below
matched unconditionally as well - unbounded on both axes.

    candidate_links = [l for l in approved_links if link_matches_cluster(l, cluster)]
    if not candidate_links:
        candidate_links = target_cfg.get('approved_links', [])

And when the filter did have something to say, it switched itself off and placed
a link anyway. That is the line that actually shipped an off-topic citation.

This validator blocks four things.

  1. Declaration completeness. Every target in the pantry declares a non-empty
     `eligible_clusters`. An undeclared target is the precondition for the whole
     defect, so it fails here rather than being discovered later in the corpus.
  2. Declaration honesty. Every declared cluster is a string this repository
     actually uses - a cluster in the publication's own vocabulary, or one a
     published page records for itself. Without this, the cheapest way to pass
     check 3 would be to declare the off-topic cluster and call it scope.
  3. Corpus conformance. No affiliated placement on a page that records a
     cluster sits outside its target's declared clusters, and no affiliated link
     points at a host the pantry does not know.
  4. The mechanism, not just today's output. build_brief() is called directly and
     must DECLINE - return None - both when a target declares no scope and when
     no approved link matches the drawn cluster. A green corpus with the old
     fallbacks restored is a corpus that is one generator run from being wrong
     again, so the refusal itself is asserted rather than inferred.

Scope note, stated rather than hidden: check 3 covers pages that record a
cluster. A hand-authored standing page - a hub, an index, an editorial pillar -
records none, and its affiliated link was placed by a person choosing it rather
than by build_brief drawing it. There is no drawn subject there to be outside
of. Those placements are counted and reported by this validator, and left to
editorial judgement, which is where they belong.

Wired into validation/plan.json as HARD_FAIL.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import measure_affiliate_topical_fit as fit  # noqa: E402

failures: list[str] = []

PANTRY = json.loads((ROOT / "content-bank/yearly-pantry.json").read_text(encoding="utf-8"))


def norm(value: str) -> str:
    return str(value).strip().lower()


# --- 1. every target declares a scope ---------------------------------------
targets = []
for pub_key, pub in PANTRY["publications"].items():
    for target in pub.get("targets", []):
        if isinstance(target, dict):
            targets.append((pub_key, target))

for pub_key, target in targets:
    label = f"{pub_key}/{target.get('brand_id') or target.get('domain')}"
    if target.get("campaign_id"):
        label += f"[{target['campaign_id']}]"
    if not [c for c in (target.get("eligible_clusters") or []) if str(c).strip()]:
        failures.append(
            f"undeclared_scope: {label} declares no eligible_clusters. A target with no declared "
            f"subject cannot be cited relevantly, only coincidentally."
        )

# --- 2. declared clusters are strings this repository actually uses ----------
subjects = fit.page_subjects()
recorded: dict[str, set[str]] = {}
for rel_key, (_hub, cluster) in subjects.items():
    if cluster:
        recorded.setdefault(rel_key.split("/", 1)[0], set()).add(norm(cluster))

for pub_key, pub in PANTRY["publications"].items():
    folder = pub["site_path"].rstrip("/").split("/")[-1]
    vocabulary = {norm(c) for c in pub.get("clusters", [])} | recorded.get(folder, set())
    for target in pub.get("targets", []):
        if not isinstance(target, dict):
            continue
        label = f"{pub_key}/{target.get('brand_id') or target.get('domain')}"
        for cluster in target.get("eligible_clusters") or []:
            if norm(cluster) not in vocabulary:
                failures.append(
                    f"invented_cluster: {label} declares {cluster!r}, which is not a cluster this "
                    f"publication uses. Scope has to be declared in the vocabulary the pages are "
                    f"actually written in, or it is not a constraint."
                )

# --- 3. the published corpus conforms ---------------------------------------
scope = fit.declared_scope()
counts = {"in_scope": 0, "out_of_scope": 0, "standing_page_no_cluster": 0,
          "target_declares_no_scope": 0, "target_not_in_pantry": 0}
offenders: list[str] = []

for path in sorted((ROOT / "sites").rglob("*.html")):
    if path.name == "404.html":
        continue
    rel_key = path.relative_to(ROOT / "sites").as_posix()
    _hub, cluster = subjects.get(rel_key, ("(standing page)", ""))
    seen: set[str] = set()
    text = path.read_text(encoding="utf-8", errors="ignore")
    for attrs in fit.A_RE.findall(text):
        href = fit.HREF_RE.search(attrs)
        rel = fit.REL_RE.search(attrs)
        if not href or not rel or "sponsored" not in rel.group(1):
            continue
        from urllib.parse import urlparse
        host = fit.norm(urlparse(href.group(1)).netloc)
        if host in seen:
            continue
        seen.add(host)
        declared = scope.get(host)
        if declared is None:
            counts["target_not_in_pantry"] += 1
            offenders.append(f"unknown_destination: {rel_key} cites {host}, which no pantry target owns.")
        elif not declared:
            counts["target_declares_no_scope"] += 1
            offenders.append(f"undeclared_destination: {rel_key} cites {host}, which declares no scope.")
        elif not cluster:
            counts["standing_page_no_cluster"] += 1
        elif cluster in declared:
            counts["in_scope"] += 1
        else:
            counts["out_of_scope"] += 1
            offenders.append(
                f"off_topic_placement: {rel_key} is about {cluster!r} and carries an affiliated "
                f"citation to {host}, which is not declared for that subject."
            )

failures.extend(offenders[:20])
if len(offenders) > 20:
    failures.append(f"...and {len(offenders) - 20} further off-topic or unowned affiliated placement(s).")

# --- 4. the generator still refuses ------------------------------------------
# Output can be clean while the mechanism that produced it has been reverted.
# These two calls assert the refusal itself.
try:
    import authority_v4_autopilot as autopilot  # noqa: E402

    pub_key = next(iter(autopilot.PANTRY["publications"]))
    state = {"published_signatures": [], "published_hashes": [], "published_titles": []}

    unscoped = {"brand_id": "guard-fixture", "brand": "Guard Fixture",
                "domain": "guard-fixture.example",
                "approved_links": [{"url": "https://guard-fixture.example/",
                                    "anchor": "Guard Fixture", "topics": ["*"]}]}
    if autopilot.build_brief(pub_key, 0, state, target_override=unscoped) is not None:
        failures.append(
            "fallback_restored_all_clusters: build_brief() accepted a target that declares no "
            "eligible_clusters. That is the `or pub['clusters']` fallback back in place, and with it "
            "the page subject and the paid destination are drawn independently again."
        )

    mismatched = {"brand_id": "guard-fixture", "brand": "Guard Fixture",
                  "domain": "guard-fixture.example",
                  "eligible_clusters": ["guard fixture cluster"],
                  "approved_links": [{"url": "https://guard-fixture.example/",
                                      "anchor": "Guard Fixture",
                                      "topics": ["a topic that is not the drawn cluster"]}]}
    if autopilot.build_brief(pub_key, 0, state, target_override=mismatched) is not None:
        failures.append(
            "fallback_restored_unfiltered_links: build_brief() placed a link when no approved link "
            "matched the drawn cluster. That is the topical filter switching itself off, which is "
            "the line that actually ships an off-topic citation."
        )
except Exception as exc:  # noqa: BLE001
    failures.append(f"mechanism_unverifiable: could not exercise build_brief() ({exc}). A guard that "
                    f"cannot run its own negative case is not a guard.")

receipt = {
    "validator": "affiliate_topical_scope",
    "status": "FAIL" if failures else "PASS",
    "hard_failures": len(failures),
    "strong_warnings": 0,
    "soft_warnings": 0,
    "targets_examined": len(targets),
    "placements": counts,
    "failures": failures,
}
print(json.dumps(receipt, indent=2))
sys.exit(1 if failures else 0)
