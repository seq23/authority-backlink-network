#!/usr/bin/env python3
"""No single affiliated brand may be cited from more than a third of a publication.

What this protects
------------------
Every affiliated citation in this repository carries `rel="sponsored nofollow"`.
None of them passes a ranking signal, so none of them is worth anything to
search, and removing one costs nothing that a search engine measures. What they
cost is the sentence every page here prints about itself - that this is a
resource library which cites affiliated projects where relevant. A publication
called Professional Resource Library with an Approval Prep citation on 290 of
its 420 pages is not that, whatever the disclosure says, and the disclosure
being present and honest makes it worse rather than better: it is the receipt.

Why one third, and not a rounder or a smaller number: measured 2026-08-28, the
leading brand in the two publications nobody had a complaint about sat at 31.4%
(virtual-agency-os, 33 of founder-operator's 105 pages) and 32.7% (porch-party,
34 of memphis-local's 104). Two campaigns, two scheduling weights, two page
counts, and they bracket a third. The cap is the network's own observed
behaviour when the scheduler is working, which is why it is written in
`content-bank/scaling-policy.json` as policy and read from there rather than
being defaulted here.

This blocks on three things, in the order they would go wrong:

  1. a brand over the cap in the published output;
  2. the cap missing from the policy file, or raised without the pages moving;
  3. the generator no longer consulting it - which is the failure that actually
     matters, because output can be clean the day after the guard is removed and
     back over the cap a fortnight later. `scripts/authority_v4_autopilot.py`
     reached 69% precisely because the scheduler could see a per-campaign deficit
     and never a share, and because one brand had both a priority lane with no
     `until_rendered_coverage` and a private environment variable
     (`APPROVAL_PREP_PAGES_PER_DAY`) that outranked the shared schedule.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

A_RE = re.compile(r"<a\s+([^>]*)>", re.I)
HREF_RE = re.compile(r'href="([^"]+)"')
REL_RE = re.compile(r'rel="([^"]*)"')

failures: list[str] = []

policy = json.loads((ROOT / "content-bank/scaling-policy.json").read_text(encoding="utf-8"))
pantry = json.loads((ROOT / "content-bank/yearly-pantry.json").read_text(encoding="utf-8"))

share = policy.get("hard_limits", {}).get("max_brand_page_share_per_publication")
if share is None:
    failures.append(
        "cap_removed: content-bank/scaling-policy.json no longer declares "
        "hard_limits.max_brand_page_share_per_publication. Nothing else in the repository "
        "bounds how much of a publication one brand may occupy."
    )
    share = 1.0
share = float(share)
if share > 0.3334:
    failures.append(
        f"cap_raised: max_brand_page_share_per_publication is {share:.4f}. The third comes from "
        f"the measured 31.4% and 32.7% of the two healthy publications; raising it is a decision "
        f"about the network's posture, not a validator setting."
    )


def norm(host: str) -> str:
    return host.lower().removeprefix("www.")


def host_to_brand() -> dict[str, str]:
    out: dict[str, str] = {}
    for pub in pantry["publications"].values():
        for target in pub.get("targets", []):
            if not isinstance(target, dict) or not target.get("brand_id"):
                continue
            values = [str(target.get("domain", ""))]
            values += [str(link.get("url", "")) for link in target.get("approved_links", [])
                       if isinstance(link, dict)]
            for value in values:
                host = norm(urlparse(value if "//" in value else "//" + value).netloc)
                if host:
                    out[host] = target["brand_id"]
    return out


brands = host_to_brand()
measured: list[dict] = []
for site in sorted((ROOT / "sites").iterdir()):
    if not site.is_dir():
        continue
    total, carrying = 0, {}
    for path in sorted(site.rglob("*.html")):
        if path.name == "404.html":
            continue
        total += 1
        seen: set[str] = set()
        for attrs in A_RE.findall(path.read_text(encoding="utf-8", errors="ignore")):
            href = HREF_RE.search(attrs)
            rel = REL_RE.search(attrs)
            if not href or not rel or "sponsored" not in rel.group(1):
                continue
            brand = brands.get(norm(urlparse(href.group(1)).netloc))
            if brand:
                seen.add(brand)
        for brand in seen:
            carrying[brand] = carrying.get(brand, 0) + 1
    if not total:
        continue
    allowed = int(total * share)
    for brand, pages in sorted(carrying.items()):
        measured.append({"publication": site.name, "brand": brand, "pages": pages,
                         "of": total, "share": round(pages / total, 4)})
        if pages > allowed:
            failures.append(
                f"over_share_cap: {brand} is cited from {pages} of {site.name}'s {total} pages "
                f"({pages / total:.1%}), above the declared {share:.1%} ({allowed} pages). "
                f"scripts/reduce_commercial_link_concentration.py --write brings it back."
            )

# --- the generator still consults the cap ------------------------------------
# Clean output the day a guard is deleted proves nothing about the fortnight
# after, so the refusal itself is exercised rather than inferred.
try:
    import authority_v4_autopilot as autopilot  # noqa: E402

    if not hasattr(autopilot, "brands_at_share_cap"):
        failures.append(
            "guard_removed: authority_v4_autopilot.brands_at_share_cap() is gone. The scheduler "
            "is back to weighting by per-campaign deficit alone, which cannot see a share."
        )
    else:
        pub_key = "professional-resources"
        capped = autopilot.brands_at_share_cap(pub_key)
        fixture = [{"brand_id": next(iter(capped)) if capped else "guard-fixture-brand"},
                   {"brand_id": "guard-fixture-unknown-brand"}]
        kept = autopilot.schedulable_targets(pub_key, fixture)
        if len(kept) != 1 or kept[0]["brand_id"] != "guard-fixture-unknown-brand":
            failures.append(
                "guard_inert: schedulable_targets() did not withhold a slot from a brand already "
                "at its share of the publication. A cap the scheduler does not act on is a comment."
            )

    if "APPROVAL_PREP_PAGES_PER_DAY" in (ROOT / "scripts/authority_v4_autopilot.py").read_text(
            encoding="utf-8").split("# APPROVAL_PREP_PAGES_PER_DAY used to override", 1)[0]:
        failures.append(
            "per_brand_bypass_restored: authority_v4_autopilot.py reads "
            "APPROVAL_PREP_PAGES_PER_DAY again. A per-brand environment variable that outranks "
            "the shared schedule is how 69% happened the first time."
        )

    lanes = [t.get("brand_id") for t in policy.get("priority_targets", [])
             if t.get("until_rendered_coverage") is None]
    if lanes:
        failures.append(
            "unbounded_priority_lane: " + ", ".join(sorted(map(str, lanes))) + " hold a priority "
            "lane in content-bank/scaling-policy.json with no until_rendered_coverage. A lane with "
            "no stop condition takes the front of the job list every day, forever."
        )
except Exception as exc:  # noqa: BLE001
    failures.append(f"mechanism_unverifiable: could not exercise the share cap ({exc}). A guard "
                    f"that cannot run its own negative case is not a guard.")

receipt = {
    "validator": "brand_link_concentration",
    "status": "FAIL" if failures else "PASS",
    "hard_failures": len(failures),
    "strong_warnings": 0,
    "soft_warnings": 0,
    "declared_max_brand_page_share": share,
    "measured": measured,
    "failures": failures,
}
print(json.dumps(receipt, indent=2))
sys.exit(1 if failures else 0)
