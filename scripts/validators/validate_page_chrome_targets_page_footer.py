#!/usr/bin/env python3
"""The governance footer must land in the PAGE footer, never inside <main>.

What this stops happening again
-------------------------------
Run 34231670721 (2026-09-08, "USCIS Form and Fee Changelog") went red on

    "pages_with_a_repeated_absolute_anchor": [
      "professional/uscis-form-and-fee-changelog.html :: 'masthead'"
    ]

That week the changelog published its FIRST entry. Every entry renders its
verbatim quote as

    <blockquote class="note"><p>...</p><footer>Added to ..., observed ...</footer></blockquote>

which is the correct HTML element for a citation attribution. But five scripts
each carried their own `re.compile(r"<footer>.*?</footer>")` and treated the
FIRST match as "the page footer". With an entry present, the first match is the
blockquote's attribution -- so install_editorial_chrome.py replaced THAT with
the governance footer and left the real page footer at the bottom of <body>
untouched. The page shipped two governance footers, hence two
`<a href="https://.../masthead">Masthead</a>` anchors, and
build_site_navigation.py's duplicate-anchor audit correctly refused it.

Why it was invisible until then
-------------------------------
With zero entries the changelog page emits no nested <footer> at all, so the
shape had never been built. Nothing in the tree was wrong, and a scan of `sites/`
on any day before 2026-09-08 would have reported PASS. That is why the first
half of this guard is a BEHAVIOURAL fixture: it feeds the chrome installer the
shapes that trigger the defect and reads what comes out, rather than waiting for
a scheduled run to produce one.

Two independent things fail hard
--------------------------------
  fixtures  install_editorial_chrome.install() applied to a page carrying a
            content <footer> inside <main> must yield exactly ONE governance
            footer, outside <main>, with no repeated absolute anchor, and must
            be idempotent under a second application.
  tree      every published page must carry exactly one governance footer and it
            must be outside <main>.
  zero      a run that examined no fixtures or no pages FAILS. A guard that
            iterates an empty list reports PASS forever.

The fixtures call the real install() and the real duplicate-anchor rule
(build_site_navigation.repeated_absolute_anchors) rather than restating either,
so the guard cannot drift away from the code it governs.

    python3 scripts/validators/validate_page_chrome_targets_page_footer.py
    python3 scripts/validators/validate_page_chrome_targets_page_footer.py --sites-root DIR
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_site_navigation as nav  # noqa: E402
import install_editorial_chrome as chrome  # noqa: E402
from lib.page_chrome import MAIN_RE, page_footer_match  # noqa: E402

# The governance footer's own marker. install_editorial_chrome.render_footer()
# is the only thing in this repo that emits it, so counting it counts governance
# footers rather than <footer> elements in general.
GOVERNANCE_MARK = 'class="editorial-nav"'

PUB_TITLE = "Professional Resource Library"
DOMAIN = "professionalresourcelibrary.com"
EDITOR = "corrections@professionalresourcelibrary.com"

# Each fixture is a <body> shape that has, at some point, been produced by a
# generator in this repo. `entry_attribution` is the exact shape that broke the
# 2026-09-08 run.
FIXTURES = {
    "entry_attribution": (
        "<!doctype html><html lang=\"en\"><head><title>t</title></head><body>\n"
        "<header><nav><a href=\"https://%(d)s\">Home</a></nav></header>\n"
        "<main>\n"
        "<blockquote class=\"note\"><p>Filing fee changed.</p>"
        "<footer>Added to Federal Register, observed 2026-09-08</footer></blockquote>\n"
        "</main>\n"
        "<footer><ul><li><a href=\"https://%(d)s/masthead\">Masthead</a></li></ul></footer>\n"
        "</body></html>\n"),
    "two_entry_attributions": (
        "<!doctype html><html lang=\"en\"><head><title>t</title></head><body>\n"
        "<main>\n"
        "<blockquote><p>a</p><footer>attribution one</footer></blockquote>\n"
        "<article><p>b</p><footer>attribution two</footer></article>\n"
        "</main>\n"
        "<footer><ul><li><a href=\"https://%(d)s/masthead\">Masthead</a></li></ul></footer>\n"
        "</body></html>\n"),
    "content_footer_but_no_page_footer": (
        "<!doctype html><html lang=\"en\"><head><title>t</title></head><body>\n"
        "<main><blockquote><p>a</p><footer>attribution only</footer></blockquote></main>\n"
        "</body></html>\n"),
    "plain_page_no_content_footer": (
        "<!doctype html><html lang=\"en\"><head><title>t</title></head><body>\n"
        "<main><p>ordinary page</p></main>\n"
        "<footer><ul><li><a href=\"https://%(d)s/masthead\">Masthead</a></li></ul></footer>\n"
        "</body></html>\n"),
}


def governance_footers_outside_main(text: str) -> tuple[int, int]:
    """(total governance footers, how many of them sit inside <main>)."""
    main = MAIN_RE.search(text)
    span = (main.start(), main.end()) if main else None
    total = inside = 0
    for match in re.finditer(re.escape(GOVERNANCE_MARK), text):
        total += 1
        if span and span[0] <= match.start() < span[1]:
            inside += 1
    return total, inside


def check_fixtures() -> tuple[int, list[str]]:
    failures: list[str] = []
    checked = 0
    for name, template in sorted(FIXTURES.items()):
        page = template % {"d": DOMAIN}
        out = chrome.install(page, PUB_TITLE, DOMAIN, EDITOR, {})
        checked += 1

        total, inside = governance_footers_outside_main(out)
        if total != 1:
            failures.append(
                f"HARD_FAIL fixture {name}: install() produced {total} governance "
                f"footers; exactly one is required. More than one is the "
                f"two-masthead-anchor defect of run 34231670721.")
        if inside:
            failures.append(
                f"HARD_FAIL fixture {name}: {inside} governance footer(s) were "
                f"installed INSIDE <main>. The governance footer is page chrome and "
                f"belongs outside the content region; a <footer> inside <main> is a "
                f"citation attribution and must never be replaced.")
        repeats = nav.repeated_absolute_anchors(out)
        if repeats:
            failures.append(
                f"HARD_FAIL fixture {name}: repeated absolute anchor {repeats[0][1]!r} "
                f"-> {repeats[0][0]}; build_site_navigation.py blocks the release on "
                f"exactly this.")
        if chrome.install(out, PUB_TITLE, DOMAIN, EDITOR, {}) != out:
            failures.append(
                f"HARD_FAIL fixture {name}: install() is not idempotent; a second "
                f"application changed the page, which is how a footer accumulates.")
    return checked, failures


def check_tree(sites_root: Path) -> tuple[int, list[str]]:
    failures: list[str] = []
    checked = 0
    for path in sorted(sites_root.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if GOVERNANCE_MARK not in text:
            continue
        checked += 1
        rel = path.relative_to(sites_root).as_posix()
        total, inside = governance_footers_outside_main(text)
        if total != 1:
            failures.append(f"HARD_FAIL {rel}: {total} governance footers, expected 1")
        if inside:
            failures.append(
                f"HARD_FAIL {rel}: {inside} governance footer(s) rendered inside <main>")
        if not page_footer_match(text):
            failures.append(
                f"HARD_FAIL {rel}: carries a governance footer but no page-level "
                f"<footer> outside <main>")
    return checked, failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites-root", default=str(ROOT / "sites"),
                    help="tree to scan; used by the guard's own zero-item proof")
    args = ap.parse_args()

    sites_root = Path(args.sites_root)
    fixtures_checked, fixture_failures = check_fixtures()
    pages_checked, tree_failures = (
        check_tree(sites_root) if sites_root.is_dir() else (0, []))

    print("PAGE CHROME TARGETS THE PAGE FOOTER")
    print(f"  fixtures exercised: {fixtures_checked}")
    print(f"  published pages carrying a governance footer: {pages_checked}")

    if fixtures_checked == 0 or pages_checked == 0:
        print("PAGE CHROME TARGETS THE PAGE FOOTER: FAIL")
        print(f"  HARD_FAIL examined {fixtures_checked} fixtures and {pages_checked} "
              f"pages under {sites_root}; this guard must not report PASS on an empty "
              f"walk")
        print(json.dumps({"status": "FAIL", "hard_failures": 1}))
        return 1

    failures = fixture_failures + tree_failures
    if failures:
        print("PAGE CHROME TARGETS THE PAGE FOOTER: FAIL")
        for line in failures:
            print(f"  {line}")
        print(json.dumps({"status": "FAIL", "hard_failures": len(failures)}))
        return 1

    print(f"  {fixtures_checked} installer fixtures and {pages_checked} published pages "
          f"each carry exactly one governance footer, outside <main>")
    print("PAGE CHROME TARGETS THE PAGE FOOTER: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
