"""One definition of what a publishable <title> and meta description look like.

Why this exists
---------------
Bing Webmaster (25 Sep 2026) flagged rule 118, "meta description too short", on
the homepages of founderoperatorlibrary.com (82 characters) and
memphisvendorlibrary.com (68), and on founderoperatorlibrary.com/about (56). A
crawl of all three publications found the same defect on every editorial page
and hand-written hub, descriptions of 161-238 characters that search engines
truncate, and two further defects:

* the daily generator wrote one sentence mould -- "A practical, human-first
  resource for {audience} comparing {cluster} without fake rankings or forced
  answers." -- so any two pages sharing an audience and cluster shared a
  description (62 duplicate groups across the three sites), and
* its title was built from cluster, modifier, format and intent only, so two
  pages that differed only in audience published the same <title> (memphis
  2026-07-19 and 2026-08-22, "Wedding-Day Timeline: Plain-English Mistakes To
  Avoid For Careful Decision-Makers").

Every generator in this repository takes its bounds from here, and
scripts/validators/validate_meta_description_bounds.py checks the published tree
against the same constants, so the rule cannot exist twice and drift.
"""
from __future__ import annotations

DESC_MIN = 110
DESC_MAX = 160
TITLE_MIN = 30


def fits(description: str) -> bool:
    return DESC_MIN <= len(description) <= DESC_MAX


def require(description: str, where: str) -> str:
    """Return the description, or raise so a generator cannot write a bad one."""
    if not fits(description):
        raise ValueError(
            f"{where}: meta description is {len(description)} characters; "
            f"it must be {DESC_MIN}-{DESC_MAX}: {description!r}")
    return description


def first_fitting(candidates: list[str], where: str) -> str:
    """The first candidate inside the bounds; raise if none is.

    Generators list candidates most-informative first, so a page gets the
    fullest description that still fits rather than a padded or cut one.
    """
    for candidate in candidates:
        if fits(candidate):
            return candidate
    raise ValueError(
        f"{where}: no description candidate is {DESC_MIN}-{DESC_MAX} characters: "
        + "; ".join(f"{len(c)}={c!r}" for c in candidates))


def _article(phrase: str) -> str:
    word = (phrase.split() or [""])[0].split("-")[0]
    if word[:1].lower() in "aeiou":
        return "an"
    # An acronym read letter by letter ("an FAQ", "an HR leader").
    if len(word) > 1 and word.isupper() and word[:1] in "FHLMNRSX":
        return "an"
    return "a"


# Formats that are not a noun phrase on their own.
FORMAT_NOUNS = {"mistakes to avoid": "mistakes-to-avoid guide"}


def daily_description(*, cluster: str, audience: str, fmt: str, intent: str, modifier: str) -> str:
    """The description of a pantry-composed daily page.

    It names every input the page's own title is built from (cluster, modifier,
    format, intent) plus the audience, so two pages can only share a
    description if they already share a title -- which the generator now
    refuses. Candidates only shorten the closing clause; the identifying parts
    are never dropped.
    """
    fmt_text = FORMAT_NOUNS.get(fmt, fmt).replace("/", " and ")
    lead = f"{_article(modifier).capitalize()} {modifier} {fmt_text} on {cluster}"
    who = f"for {_article(audience)} {audience}"
    tails = (
        ": what to compare, what to ask and which mistakes to avoid.",
        ": what to compare and what to ask.",
        ": the questions worth asking first.",
        ".",
    )
    candidates = [f"{lead} {who}, written {intent}{tail}" for tail in tails]
    candidates += [f"{lead}, written {intent}{tail}" for tail in tails]
    return first_fitting(candidates, f"daily page on {cluster!r}")


def sentence_fit(text: str, where: str, extras: tuple[str, ...] = ()) -> str:
    """Build a description from a page's own prose.

    Whole sentences are taken from the start of `text` while they fit; if the
    result is still short, each of `extras` (page-specific clauses) is tried in
    turn. Never cuts a sentence mid-way.
    """
    import re

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    candidates: list[str] = []
    built = ""
    for sentence in sentences:
        built = f"{built} {sentence}".strip()
        candidates.append(built)
    for base in list(candidates):
        for extra in extras:
            candidates.append(f"{base} {extra}".strip())
    in_range = [c for c in candidates if fits(c)]
    if in_range:
        # Prefer the fullest candidate that fits.
        return max(in_range, key=len)
    return first_fitting(candidates, where)
