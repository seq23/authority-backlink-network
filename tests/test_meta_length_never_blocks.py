#!/usr/bin/env python3
"""A title or meta description never blocks a build for its length alone.

Owner ruling, 2 Nov 2026 (personal brain, Settled decisions): over a length
limit never fails -- the generator trims to fit; under a floor fails only below
75% of it. scripts/lib/meta_description.py is where every page writer gets its
<title> and meta description, so the rule is pinned there:

  * over-long titles, descriptions, daily titles and homepage titles come back
    trimmed to the bound, never raised;
  * text between 75% and 100% of the floor is accepted as is;
  * text under 75% of the floor still raises (the floor is not removed);
  * the autopilot's quality gate does not hard-fail an over-long head.

Fails on zero cases checked.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lib import meta_description as md  # noqa: E402

checked = 0
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global checked
    checked += 1
    if not ok:
        failures.append(f"{name}: {detail}")


def raises(fn, *args) -> bool:
    try:
        fn(*args)
    except ValueError:
        return True
    return False


SITE = "Professional Resource Library"
LONG_DESC = ("A long description written by a generator that ran well past the limit, "
             "naming every input the page was built from and then going on to explain "
             "what to compare, what to ask and which mistakes to avoid on the day.")

# Over the maximum: trimmed, never refused.
desc = md.require(LONG_DESC, "over-long description")
check("description over max is trimmed", len(desc) <= md.DESC_MAX and desc != LONG_DESC,
      f"{len(desc)} {desc!r}")
check("trimmed description is publishable", md.description_ok(desc), repr(desc))

long_name = "An Extremely Long Editorial Page Title About Credit Report Dispute Letters And Their Timelines"
title = md.require_title(f"{long_name} | {SITE}", "over-long title")
check("title over max is trimmed", len(title) <= md.TITLE_MAX, f"{len(title)} {title!r}")
check("trimmed title keeps the site suffix", title.endswith(f" | {SITE}"), repr(title))
check("site_title never raises on length",
      len(md.site_title(long_name, SITE, "site title")) <= md.TITLE_MAX)

daily = md.daily_site_title("a cluster nobody has written a short editorial alias for yet",
                            "Founder Operator Library",
                            "founder/daily/2026-11-02-some-page.html")
check("daily title over max is trimmed, keeps date and brand",
      len(daily) <= md.TITLE_MAX and "2026-11-02 | Founder Operator Library" in daily, repr(daily))

home = md.home_title({"id": "x", "title": "Professional Resource Library",
                      "home_descriptor": "plain guides for practitioners who run small professional offices"})
check("home title over max is trimmed", len(home) <= md.HOME_TITLE_MAX, f"{len(home)} {home!r}")

picked = md.pick_title([long_name + " Edition One"], set())
check("pick_title trims rather than returning nothing", bool(picked) and len(picked) <= md.TITLE_MAX,
      repr(picked))
check("first_fitting trims rather than raising",
      len(md.first_fitting([LONG_DESC], "first_fitting")) <= md.DESC_MAX)

# Between 75% and 100% of the floor: accepted unchanged.
near_desc = "x" * int(md.DESC_MIN * 0.8)
check("description at 80% of floor passes", md.require(near_desc, "near") == near_desc)
near_title = "y" * int(md.TITLE_MIN * 0.8)
check("title at 80% of floor passes", md.require_title(near_title, "near") == near_title)

# Under 75% of the floor: still refused.
check("description under 75% of floor raises", raises(md.require, "z" * int(md.DESC_MIN * 0.7), "short"))
check("title under 75% of floor raises", raises(md.require_title, "z" * int(md.TITLE_MIN * 0.7), "short"))
check("every candidate under 75% raises", raises(md.first_fitting, ["too short"], "short"))

# The autopilot's quality gate reads the same helpers.
check("quality gate accepts an over-long head",
      md.title_ok("t" * (md.TITLE_MAX + 40)) and md.description_ok("d" * (md.DESC_MAX + 80)))
autopilot = (ROOT / "scripts/authority_v4_autopilot.py").read_text(encoding="utf-8")
check("autopilot gate uses the floor helpers, not the band",
      "meta_description.description_ok(" in autopilot and "meta_description.title_ok(" in autopilot
      and "meta_description.fits(html" not in autopilot)

if checked == 0:
    print("test_meta_length_never_blocks: FAIL - zero cases checked")
    sys.exit(1)
if failures:
    print(f"test_meta_length_never_blocks: FAIL ({len(failures)}/{checked})")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"test_meta_length_never_blocks: PASS ({checked} cases)")
