#!/usr/bin/env python3
"""Each publication must have its own analytics project, and no placeholder may ship.

Why this exists
---------------
Separate analytics per publication is ordinary hygiene: different properties,
different readers, different data. Sharing one project across two properties
mixes their sessions and makes both numbers wrong. Elsewhere in this portfolio
that has actually happened -- one Clarity project (y7l3djg8o6) carries both
porchandparty901.com and partyandporch.com.

Current state of these three, which this check locks in rather than fixes:
data/clarity_projects.json already maps each of the three publication domains to
a DISTINCT project id. Nothing was shared here. What was missing is anything
stopping the next publication from being added with a placeholder, a blank, or a
copy of a sibling's id -- the city-vendor family in data/city-publications.json
is designed to grow, and a copied id would silently pollute a live project.

What it checks
--------------
1. Every publication in data/publications.json has a Clarity project id.
2. No two publications share an id.
3. No id looks like a placeholder (see PLACEHOLDER_PATTERNS).
4. Every published page's injected Clarity map contains ONLY its own domain, so
   one publication cannot report sessions into another's project.

Exit 1 on any failure. Wired into validation/plan.json as HARD_FAIL.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

# A Clarity project id is a short lowercase alphanumeric string. Anything that
# reads like a stand-in must not reach a release.
PLACEHOLDER_PATTERNS = [
    re.compile(r"^\s*$"),
    re.compile(r"replace|placeholder|todo|tbd|changeme|your[-_]?id|example|dummy|xxx+", re.I),
    re.compile(r"^(0+|1+|x+|n/?a)$", re.I),
]

CLARITY_MAP_RE = re.compile(r"<script data-clarity-loader>.*?\}\)\(window,document,(\{.*?\})\)</script>",
                            re.S)


def main() -> int:
    pubs = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
    cfg_path = ROOT / "data/clarity_projects.json"
    if not cfg_path.exists():
        print(f"ANALYTICS SEPARATION: FAIL -- missing {cfg_path.relative_to(ROOT)}")
        return 1
    projects = json.loads(cfg_path.read_text(encoding="utf-8")).get("projects", {})

    failures = []
    seen: dict[str, str] = {}

    for pub in pubs:
        domain = pub["working_domain"].lower().replace("www.", "")
        pid = projects.get(domain)
        if pid is None:
            failures.append(f"{pub['title']} ({domain}): no analytics project configured in "
                            f"data/clarity_projects.json")
            continue
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(str(pid)):
                failures.append(f"{pub['title']} ({domain}): analytics project id {pid!r} is a "
                                f"placeholder. Create a real project and put its id here -- see "
                                f"docs/EDITORIAL-INDEPENDENCE.md, 'Separate analytics projects'.")
                break
        else:
            if pid in seen:
                failures.append(f"{pub['title']} ({domain}) shares analytics project {pid!r} with "
                                f"{seen[pid]}. Two publications reporting into one project make "
                                f"both sets of numbers wrong.")
            seen[pid] = f"{pub['title']} ({domain})"

    # Every page must carry a map naming only its own domain.
    leaks = []
    for pub in pubs:
        domain = pub["working_domain"].lower().replace("www.", "")
        for path in sorted((ROOT / pub["folder"]).rglob("*.html")):
            found = CLARITY_MAP_RE.search(path.read_text(encoding="utf-8"))
            if not found:
                continue
            try:
                mapping = json.loads(found.group(1))
            except json.JSONDecodeError:
                leaks.append(f"{path.relative_to(ROOT)}: analytics map is not valid JSON")
                continue
            foreign = [d for d in mapping if d.lower().replace("www.", "") != domain]
            if foreign:
                leaks.append(f"{path.relative_to(ROOT)}: analytics map names another "
                             f"publication's domain(s): {', '.join(sorted(foreign))}")

    failures.extend(leaks[:10])
    if len(leaks) > 10:
        failures.append(f"...and {len(leaks) - 10} more page(s) with a cross-publication "
                        f"analytics map")

    if failures:
        print("ANALYTICS SEPARATION: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"ANALYTICS SEPARATION: PASS ({len(pubs)} publication(s), "
          f"{len(seen)} distinct analytics project(s), no placeholders, no cross-publication maps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
