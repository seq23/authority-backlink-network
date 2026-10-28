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
scripts/validators/validate_page_meta_bounds.py checks the published tree
against the same constants, so the rule cannot exist twice and drift.
"""
from __future__ import annotations

# Tightened 25 Oct 2026 to the owner's Search Readiness Checklist, which is
# stricter than the Bing site scan these bounds were first written from and is
# what now audits these publications every Monday:
#
#   item b1  "Title 30-65 characters, unique, the query first, the site name
#            once" -- 214 pages were 66-70 characters, inside the old bound and
#            outside this one.
#   item b2  "Meta description 120-160 characters" -- four pages were 113-119.
#
# 65 rather than 70 because a title is only worth the part that survives
# Google's ~600px cut, and 120 rather than 110 because a snippet shorter than
# that leaves the engine to write its own from the page.
DESC_MIN = 120
DESC_MAX = 160
TITLE_MIN = 30
TITLE_MAX = 65


def title_fits(title: str) -> bool:
    return TITLE_MIN <= len(title) <= TITLE_MAX


def require_title(title: str, where: str) -> str:
    if not title_fits(title):
        raise ValueError(
            f"{where}: <title> is {len(title)} characters; it must be "
            f"{TITLE_MIN}-{TITLE_MAX}: {title!r}")
    return title


# A homepage title is "<Publication>: <what it is>". 65, not 70, so the
# descriptor survives Google's ~600px cut on every publication name we carry.
HOME_TITLE_MIN = 30
HOME_TITLE_MAX = 65


def same_name(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def doubled_suffix(title: str) -> bool:
    """True for "X | X": the site-name suffix repeats the page title.

    11 Oct 2026: all three homepages published "<Publication> | <Publication>".
    """
    head, sep, tail = title.rpartition(" | ")
    return bool(sep) and same_name(head, tail)


def home_title(pub: dict) -> str:
    """The homepage <title>: "<Publication>: <descriptor>", 30-65 characters.

    The descriptor is data (data/publications.json `home_descriptor`), a 4-7
    word restatement of the publication's `definition`.
    """
    name = pub["title"]
    desc = " ".join((pub.get("home_descriptor") or "").split())
    if not desc:
        raise ValueError(f"data/publications.json: '{pub.get('id')}' has no `home_descriptor`")
    if not 4 <= len(desc.split()) <= 7:
        raise ValueError(f"'{pub.get('id')}' home_descriptor must be 4-7 words: {desc!r}")
    if name.casefold() in desc.casefold():
        raise ValueError(f"'{pub.get('id')}' home_descriptor repeats the publication name")
    title = f"{name}: {desc}"
    if not HOME_TITLE_MIN <= len(title) <= HOME_TITLE_MAX:
        raise ValueError(
            f"'{pub.get('id')}' homepage <title> is {len(title)} characters; it must be "
            f"{HOME_TITLE_MIN}-{HOME_TITLE_MAX}: {title!r}")
    return title


def site_title(name: str, site: str, where: str) -> str:
    """Keep the publication name once, inside the same 65-character budget.

    Dated topic pages use daily_site_title() instead, so shortening cannot
    drop the subject of the article.
    """
    name = " ".join(name.split())
    if name.casefold().endswith((" | " + site).casefold()):
        name = name[:-(len(site) + 3)].strip()
    if site.casefold() in name.casefold():
        if len(name) < TITLE_MIN and same_name(name, "About " + site):
            name = "About the " + site
        return require_title(name, where)
    suffix = f" | {site}"
    if len(name + suffix) > TITLE_MAX:
        budget = TITLE_MAX - len(suffix)
        # An ellipsis makes the shortening explicit; never cut through a word.
        if len(name) > budget:
            words = name.split()
            while words and len(" ".join(words)) > budget - 1:
                words.pop()
            while words and words[-1].casefold() in {"a", "an", "the", "and", "or", "for", "to", "of", "with", "before", "after"}:
                words.pop()
            if not words:
                raise ValueError(f"{where}: supply a concise editorial title for {name!r}")
            name = " ".join(words).rstrip(" :;,.-") + "…"
    return require_title(name + suffix, where)


def daily_site_title(cluster: str, site: str, where: str) -> str:
    """The complete topic and source archive date, followed by the brand.

    Topic aliases are editorial data, never a word-cut of the search query.
    A new topic that cannot fit fails loudly until it has an editorial alias.
    """
    import json
    import re
    from pathlib import Path
    subjects = json.loads((Path(__file__).resolve().parents[2] / "data/title-subjects.json").read_text())
    subject = subjects.get(cluster, _tc(cluster))
    date = re.search(r"(?:^|/)daily/(\d{4}-\d{2}-\d{2})-", where)
    if not date:
        raise ValueError(f"{where}: daily title needs its archive date")
    return require_title(f"{subject} {date.group(1)} | {site}", where)


def _tc(phrase: str) -> str:
    """Capitalise each word without lowering the rest ("HR leader" -> "HR Leader")."""
    return " ".join(w[:1].upper() + w[1:] for w in phrase.split(" "))


def daily_title_candidates(*, cluster: str, audience: str, fmt: str, intent: str,
                           modifier: str) -> list[str]:
    """<title> forms for a pantry-composed daily page, most specific first.

    The first is the page's heading ("Cluster: Modifier Format Intent"), which
    runs to 114 characters. The rest drop the modifier or swap the intent for
    the audience, so a caller can take the first one that fits TITLE_MIN-
    TITLE_MAX and that the publication has not already used.

    The last three drop the format rather than the intent. They exist because
    tightening TITLE_MAX to 65 (25 Oct 2026) left clusters whose every
    format-bearing form was over the bound and whose one short form
    ("Cluster: Format") a sibling page had already taken -- a long cluster name
    with a long format, such as "Apartment Application Paperwork" and "Budget
    Planning Note Before You Book" at 69 characters. Dropping the format keeps
    the cluster and the reader's intent, which is the part a searcher typed.
    """
    c, m, f, i = cluster.title(), modifier.title(), fmt.title(), intent.title()
    who = f"For {_article(audience).capitalize()} {_tc(audience)}"
    forms = [
        f"{c}: {m} {f} {i}",
        f"{c}: {f} {i}",
        f"{c}: {m} {f} {who}",
        f"{c}: {f} {who}",
        f"{c}: {m} {f}",
        f"{c}: {f}",
        f"{c}: {m} {i}",
        f"{c}: {i}",
        f"{c}: {who}",
    ]
    return list(dict.fromkeys(forms))


def pick_title(candidates: list[str], taken: set[str]) -> str | None:
    """The first candidate inside the bounds whose casefold is not in `taken`."""
    for candidate in candidates:
        if title_fits(candidate) and candidate.casefold() not in taken:
            return candidate
    return None


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
