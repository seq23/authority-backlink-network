#!/usr/bin/env python3
"""No one page may link the same target URL more times than the checklist allows.

What this protects
------------------
Search Readiness item g3: *no target domain gets more than a quarter of a site's
outbound links; no URL more than ten.* The owner's reason for the second half is
the one that matters here - "141 links from one site to one target is a
footprint search engines read as a scheme" - and the footprint is the same shape
whether the links were earned or manufactured.

They were earned, which is why this took a Monday audit to find. The Memphis
wedding cost dataset publishes 70 prices read off 21 vendor pages, and every
price linked the page it was printed on. A caterer that lists thirteen prices on
one catering page therefore collected thirteen identical anchors from one page of
one publication, and a party rental company with a single price list collected
ten. Nothing was faked and nothing was paid for. It still reads as a scheme, and
a reader offered the same link a thirteenth time gains nothing from it.

So the generator now separates provenance from linking: every row still names
its exact source and still reaches it in one click, through an in-page anchor
into a sources list that carries the one outbound link. Published repeats for
that page went 13 -> 1.

What this does and does not cover
---------------------------------
This is the per-URL half of g3 only. The per-domain quarter is not checked here,
and deliberately: measured 2026-10-26, 66 of the 149 pages carrying any off-site
portfolio link are over a quarter purely because their only off-site link is a
single portfolio link, and one of one is 100%. A share cap at that denominator
measures nothing, so pinning it would need a minimum-denominator rule invented
here rather than read from the checklist. The portfolio side of concentration is
already measured per publication by validate_brand_link_concentration.py and by
the owner's Monday audit; what had no guard at all was the per-URL count.

Three things fail, in the order they would go wrong:

  1. a page in the published output over the cap;
  2. the cap missing from content-bank/scaling-policy.json, or raised above the
     ten the checklist states;
  3. the generator no longer deduping - the failure that actually matters,
     because output is clean the day a dedupe is deleted and back at thirteen
     the next time the dataset grows.

Links to the publication's own domain are not counted. A topic hub listing its
own articles with absolute URLs is internal navigation, not a target.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

# The checklist's own number. The policy file may hold a stricter cap; it may not
# hold a looser one, because the looser one would no longer be the owner's rule.
CHECKLIST_MAX_LINKS_PER_TARGET_URL = 10

A_RE = re.compile(r"<a\s+([^>]*)>", re.I)
HREF_RE = re.compile(r'href="([^"]+)"')

failures: list[str] = []

policy = json.loads(
    (ROOT / "content-bank/scaling-policy.json").read_text(encoding="utf-8"))
publications = json.loads(
    (ROOT / "data/publications.json").read_text(encoding="utf-8"))

cap = policy.get("hard_limits", {}).get("max_outbound_links_per_target_url_per_page")
if cap is None:
    failures.append(
        "cap_removed: content-bank/scaling-policy.json no longer declares "
        "hard_limits.max_outbound_links_per_target_url_per_page. Nothing else in the "
        "repository bounds how many times one page may link one target URL."
    )
    cap = CHECKLIST_MAX_LINKS_PER_TARGET_URL
cap = int(cap)
if cap > CHECKLIST_MAX_LINKS_PER_TARGET_URL:
    failures.append(
        f"cap_raised: max_outbound_links_per_target_url_per_page is {cap}. Search "
        f"Readiness item g3 states ten. Raising it past the checklist is a decision "
        f"about the network's posture, not a validator setting."
    )


def norm(host: str) -> str:
    return host.lower().removeprefix("www.")


OWN_DOMAIN = {Path(p["folder"]).name: norm(p["working_domain"]) for p in publications}

# --- the published output -----------------------------------------------------
measured: list[dict] = []
for site in sorted((ROOT / "sites").iterdir()):
    if not site.is_dir():
        continue
    own = OWN_DOMAIN.get(site.name)
    worst = 0
    for path in sorted(site.rglob("*.html")):
        if path.name == "404.html":
            continue
        counts: collections.Counter[str] = collections.Counter()
        for attrs in A_RE.findall(path.read_text(encoding="utf-8", errors="ignore")):
            href = HREF_RE.search(attrs)
            if not href:
                continue
            url = href.group(1)
            host = norm(urlparse(url).netloc)
            if not host or host == own:
                continue
            counts[url] += 1
        if not counts:
            continue
        url, repeats = counts.most_common(1)[0]
        worst = max(worst, repeats)
        if repeats > cap:
            failures.append(
                f"over_url_repeat_cap: {site.name}/{path.relative_to(site).as_posix()} "
                f"links {url} {repeats} times, above the declared cap of {cap}. Cite the "
                f"target once and point the other references at that one citation."
            )
    measured.append({"publication": site.name, "worst_repeats_on_a_page": worst})

# --- the generator still dedupes ---------------------------------------------
# The dataset page is the one generator that renders one citation per data row,
# so it is the one that can regress here. The refusal is exercised against a
# seeded fixture rather than read off today's output: output is clean the day
# after the dedupe is deleted, and wrong a fortnight later.
try:
    import build_wedding_cost_dataset_page as wedding  # noqa: E402

    if not hasattr(wedding, "render_source_cells"):
        failures.append(
            "guard_removed: build_wedding_cost_dataset_page.render_source_cells() is "
            "gone. The dataset page is back to one outbound anchor per data row, which "
            "is how one caterer collected thirteen."
        )
    else:
        shared = "https://guard-fixture-vendor.example/one-price-list"
        rows = [{"vendor": "guard-fixture-vendor", "item": f"fixture item {i}",
                 "source_url": shared} for i in range(cap + 3)]
        vendors = {"guard-fixture-vendor": {"name": "Guard Fixture Vendor"}}
        cells = wedding.render_source_cells(rows, vendors)
        outbound = [c for c in cells if 'href="http' in c]
        if len(cells) != len(rows):
            failures.append(
                f"guard_inert: render_source_cells() returned {len(cells)} cells for "
                f"{len(rows)} rows. Every row must still name its own source."
            )
        if outbound:
            failures.append(
                f"guard_inert: render_source_cells() emitted {len(outbound)} outbound "
                f"links for {len(rows)} rows that all cite one URL. A dedupe that still "
                f"links per row is a comment."
            )
        if wedding.MAX_LINKS_PER_TARGET_URL != cap:
            failures.append(
                f"cap_disagreement: the generator reads a cap of "
                f"{wedding.MAX_LINKS_PER_TARGET_URL} and this validator reads {cap}. "
                f"Both must read content-bank/scaling-policy.json."
            )
except Exception as exc:  # noqa: BLE001
    failures.append(
        f"mechanism_unverifiable: could not exercise the source dedupe ({exc}). A guard "
        f"that cannot run its own negative case is not a guard."
    )

receipt = {
    "validator": "citation_link_repeats",
    "status": "FAIL" if failures else "PASS",
    "hard_failures": len(failures),
    "strong_warnings": 0,
    "soft_warnings": 0,
    "declared_max_links_per_target_url_per_page": cap,
    "measured": measured,
    "failures": failures,
}
print(json.dumps(receipt, indent=2))
sys.exit(1 if failures else 0)
