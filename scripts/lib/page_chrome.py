#!/usr/bin/env python3
"""Locate the PAGE-LEVEL <footer>, as distinct from a content <footer>.

Why this module exists
----------------------
Five scripts each carried their own copy of

    FOOTER_RE = re.compile(r"<footer>.*?</footer>", re.S | re.I)

and used it to find "the page footer". That selector does not say page footer.
It says "the first <footer> element in the document", and `<footer>` is also the
standard HTML element for a citation attribution inside `<blockquote>` or
`<article>` -- which is exactly what `scripts/build_uscis_changelog_page.py`
emits for every published changelog entry:

    <blockquote class="note"><p>...quote...</p>
      <footer>Added to Federal Register, observed 2026-09-08</footer>
    </blockquote>

On 2026-09-08 the USCIS changelog published its first entry. That entry's
attribution footer became the first `<footer>` in the document, so
`install_editorial_chrome.py` replaced IT with the governance footer and left
the real page footer at the bottom of <body> untouched. The page shipped two
governance footers, therefore two `<a href=".../masthead">Masthead</a>` anchors,
and `build_site_navigation.py`'s duplicate-anchor audit correctly rejected it.

The bug was invisible for as long as the changelog had zero entries, because
with no entries the page emits no nested <footer> at all. That is why it landed
as a scheduled-run failure rather than as a build failure: nothing had ever
exercised the shape.

The rule
--------
A page-level footer is a `<footer>` that is NOT inside `<main>`. Content
footers belong to the article they annotate and live in the main content
region; the governance footer is chrome and lives outside it. Where a page has
more than one candidate outside <main>, the LAST is the page footer, since
chrome sits at the end of <body>.

Pages that carry no <main> at all fall back to the last <footer> in the
document, which preserves the previous behaviour for them.

`<footer>` is not self-nesting in any markup this repo emits, so a non-greedy
element match is sufficient; the fix is the scope, not the parser.
"""
from __future__ import annotations

import re

# Kept for callers that legitimately want "any footer element" (there are none
# today) and so the narrowing is visible as a deliberate difference.
ANY_FOOTER_RE = re.compile(r"<footer\b[^>]*>.*?</footer>", re.S | re.I)

MAIN_RE = re.compile(r"<main\b[^>]*>.*?</main>", re.S | re.I)


def _main_span(text: str) -> tuple[int, int] | None:
    match = MAIN_RE.search(text)
    return (match.start(), match.end()) if match else None


def page_footer_match(text: str) -> re.Match | None:
    """The match object for the page-level footer, or None if there is not one.

    None means "this page has no chrome footer yet" -- the caller inserts one --
    and is deliberately distinct from "this page has a footer inside <main>",
    which is a content footer that no caller here may touch.
    """
    span = _main_span(text)
    candidates = [m for m in ANY_FOOTER_RE.finditer(text)
                  if span is None or not (span[0] <= m.start() < span[1])]
    return candidates[-1] if candidates else None


def replace_page_footer(text: str, footer: str) -> tuple[str, bool]:
    """Swap the page-level footer for `footer`. Returns (text, replaced?).

    `replaced` is False when the page had no page-level footer, which is the
    signal for the caller to insert one rather than assume it succeeded.
    """
    match = page_footer_match(text)
    if not match:
        return text, False
    return text[:match.start()] + footer + text[match.end():], True


def page_footer_html(text: str) -> str:
    """The page-level footer's markup, or "" when the page has none."""
    match = page_footer_match(text)
    return match.group(0) if match else ""
