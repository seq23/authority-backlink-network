#!/usr/bin/env python3
"""Put the governance footer and the affiliate disclosure on every published page.

Why an installer instead of editing the generators
--------------------------------------------------
There is no shared page shell in this repository. Five separate generators each
inline their own <!doctype html> ... </html> string:

  scripts/authority_v4_autopilot.py      (the bulk of the daily pages)
  scripts/generate_cluster_articles.py
  scripts/portfolio_backlink_engine.py
  scripts/build_demand_shape_pages.py
  scripts/lib/page_composer.py           (topic hubs)

and three more scripts mutate pages in place afterwards. Adding the footer to
each of them would be five edits that drift apart, and 543 of the existing daily
pages carry no <header>, no <footer> and no <nav> at all -- the affiliation is
disclosed only in body prose partway down the page.

So this runs last and is idempotent, the same pattern scripts/install_clarity.js
already uses. Re-running it changes nothing; running it after any generator
brings that generator's output into line. Wire it into the autopilot workflow
after build_site_navigation.py and no generator needs to know it exists.

What it installs
----------------
1. A bare <footer> carrying the editorial navigation (masthead, standards,
   corrections, contributors, editorial address), the ownership sentence, and
   the regulated-advice boundary. It REPLACES any existing <footer>.

2. On pages that actually cite an affiliated destination, a visible
   .affiliate-disclosure block placed next to the citation -- not in the small
   print. It names the affiliated projects on that specific page.

3. A repair for a WITHDRAWN ownership sentence already baked into a published
   page body. The generators inline data/publications.json's `disclosure` at
   publication time, so editing that field alone fixes new pages and leaves the
   back catalogue asserting the old claim. Any string listed in that
   publication's `retired_disclosures` is rewritten to the current one. Literal
   sentence substitution, ownership chrome only -- see
   refresh_disclosure_sentence().

4. The JSON-LD byline, forced to the same editorial company the visible footer
   byline names. Both come from one call to byline.entity_for() in this pass,
   which is the point: they used to disagree on 552 pages. See
   normalise_jsonld_author().

Two hard constraints on the markup
----------------------------------
* The <footer> and <header> tags must stay BARE, with no attributes.
  scripts/build_demand_shape_pages.py lifts both with
  re.compile(r"<footer>.*?</footer>") and exits if it cannot match. Idempotency
  is therefore detected by comparing rendered content, not by a marker attribute.

* Nothing here may emit an absolute URL outside the publication's own domain.
  scripts/hostile_review.py scans the whole raw file and HARD_FAILs on any host
  outside the brand registry, the publication domains, schema.org and clarity.ms.

Anchor text is deliberately different between the footer and the disclosure even
where both point at the same page, because validation/page_audit.py raises
DUPLICATE_EXTERNAL_LINK on a repeated (href, lowercased anchor) pair.
"""

import html
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from affiliation import affiliated_domains, host_of, is_affiliated  # noqa: E402
from byline import entity_for, subsidiary_clause  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITES = ROOT / "sites"

ADVICE_BOUNDARY = ("This page is informational. It is not legal, medical, "
                   "mental-health, immigration, financial, or professional advice.")

# No trailing \s* on either of these. Consuming the whitespace after the tag
# and re-emitting a fixed newline rewrites the surrounding indentation, which
# made this script and deterministic_build.py alternately reformat 404.html on
# every build. Replace the element, leave the layout alone.
FOOTER_RE = re.compile(r"<footer>.*?</footer>", re.S | re.I)
BODY_END_RE = re.compile(r"</body>", re.I)
MAIN_END_RE = re.compile(r"</main>", re.I)
DISCLOSURE_RE = re.compile(r'<aside class="affiliate-disclosure".*?</aside>', re.S | re.I)
ANCHOR_RE = re.compile(r'<a\s+[^>]*?href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)

# Preferred insertion point: immediately before the heading that introduces the
# affiliated citation on a daily page. Falls back to the end of <main>.
CITATION_HEADING_RE = re.compile(r"<h2[^>]*>\s*(?:Useful citation|Relevant resources)\s*</h2>", re.I)


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def brand_name_by_domain(brands: list) -> dict:
    out = {}
    for b in brands:
        for d in (b.get("domains") or [b.get("domain", "")]):
            if d:
                out[host_of(d)] = b["name"]
    return out


def render_footer(pub_title: str, domain: str, editor_addr: str) -> str:
    home = f"https://{domain}"
    links = [
        ("Masthead", f"{home}/masthead"),
        ("Editorial standards", f"{home}/editorial-standards"),
        ("Corrections", f"{home}/corrections"),
        ("Contributors", f"{home}/contributors"),
    ]
    items = "".join(f'<li><a href="{esc(u)}">{esc(t)}</a></li>' for t, u in links)
    items += f'<li><a href="mailto:{esc(editor_addr)}">{esc(editor_addr)}</a></li>'
    entity = entity_for(pub_title)
    return (
        "<footer>"
        f'<ul class="editorial-nav">{items}</ul>'
        f'<p class="byline" data-byline="publisher">{esc(pub_title)} is written and '
        f"edited by <strong>{esc(entity)}</strong>{esc(subsidiary_clause())}. Pages here "
        f"carry that byline and no other: this publication names no individual author, "
        f"and never attributes a page to someone who did not write it.</p>"
        f"<p>{esc(entity)} is under common ownership with several of the projects this "
        f"publication cites. Those citations are labelled on the page and carry "
        f'<code>rel="sponsored nofollow"</code>, so they pass no ranking signal. '
        f"<strong>Affiliation disclosed.</strong> No fake rankings, no paid placement, "
        f"and no listing that can be bought.</p>"
        f"<p>&copy; 2026 {esc(pub_title)}. {esc(ADVICE_BOUNDARY)}</p>"
        "</footer>"
    )


def render_disclosure(pub_title: str, domain: str, names: list) -> str:
    """The visible disclosure. Written as an asset, not an apology.

    Transparent affiliation is a trust signal when it is stated where the reader
    is standing. It is only a liability when it is buried.
    """
    home = f"https://{domain}"
    if len(names) == 1:
        subject = f"<strong>{esc(names[0])}</strong>, which is"
    else:
        listed = ", ".join(f"<strong>{esc(n)}</strong>" for n in names[:-1])
        subject = f"{listed} and <strong>{esc(names[-1])}</strong>, which are"
    return (
        '<aside class="affiliate-disclosure" data-disclosure="affiliate">'
        "<h2>Why this page links where it does</h2>"
        f"<p>This page cites {subject} under common ownership with "
        f"<strong>{esc(entity_for(pub_title))}</strong>, the editorial company that publishes "
        f"{esc(pub_title)}. That is a genuine conflict of interest, and it is why you are "
        f"reading it here rather than discovering it somewhere else.</p>"
        f'<p>The citation carries <code>rel="sponsored nofollow"</code>, so it sends no '
        f"ranking signal to the destination. Nothing on this page is ranked, scored, or paid "
        f"for, and no mention here can be bought. If the affiliated resource is not the right "
        f"fit for you, the rest of the page still answers the question without it &mdash; that "
        f"is the test every page here has to pass. "
        f'<a href="{esc(home)}/editorial-standards">How citations get chosen</a> &middot; '
        f'<a href="{esc(home)}/masthead">every project this publication is affiliated with</a>.'
        "</p></aside>"
    )


def affiliated_names_on(text: str, names_by_domain: dict) -> list:
    """The affiliated brands actually cited on this page, in first-seen order."""
    seen, out = set(), []
    for href, _anchor in ANCHOR_RE.findall(text):
        if not is_affiliated(href):
            continue
        name = names_by_domain.get(host_of(href))
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


FAVICON_LINK = '<link rel="icon" href="/favicon.svg" type="image/svg+xml">'
HEAD_END_RE = re.compile(r"</head>", re.I)

# The legacy inline table block from scripts/generate_cluster_articles.py. It
# hardcoded the old shared palette (#e5dac8, #f2ece1) and, being inline, beat the
# linked stylesheet -- so on the Memphis and Professional sites it would paint
# founder-publication colours onto every cluster-article table. .ct is now styled
# from each site's own tokens in styles.css. Matched narrowly on .ct-wrap so no
# other inline <style> is touched.
LEGACY_TABLE_CSS_RE = re.compile(r"<style>\s*\.ct-wrap\{[^<]*?</style>", re.I | re.S)


def refresh_disclosure_sentence(text: str, current: str, retired: list) -> str:
    """Rewrite a withdrawn ownership sentence in an already-published page.

    The footer is replaced wholesale on every run, so it can never carry a stale
    ownership claim. The disclosure sentence from data/publications.json is
    different: the generators bake it into the page body at publication time, so
    changing the data file fixes new pages and leaves the back catalogue still
    asserting the retired claim. 36 published pages named a person as the
    publisher for exactly that reason.

    This closes that hole without reshaping anything. It is a literal
    substitution of one declared sentence for another -- ownership chrome only,
    no heading, structure, argument or editorial prose is touched, which keeps it
    inside data/back_catalogue_decision.json's DO_NOT_RESHAPE standing decision.
    Both the raw and the HTML-escaped spelling are handled because the generators
    disagree about whether they escape the apostrophe.

    Idempotent: once a page carries the current sentence there is nothing left to
    match.
    """
    for old in retired:
        if not old or old == current:
            continue
        text = text.replace(old, current)
        text = text.replace(esc(old), esc(current))
    return text


LDJSON_RE = re.compile(
    r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S | re.I)

# The schema.org types that carry a byline. A WebPage, AboutPage, FAQPage,
# Organization or BreadcrumbList does not, and forcing an author onto one would
# be inventing an authorship claim rather than correcting one.
BYLINED_TYPES = frozenset({
    "Article", "BlogPosting", "NewsArticle", "TechArticle",
    "ScholarlyArticle", "Report", "AdvertiserContentArticle",
})


def _canonical_author(entity: str) -> dict:
    return {"@type": "Organization", "name": entity}


def _normalise_author_nodes(node, entity: str) -> bool:
    """Set every byline on `node` to `entity`. Returns True if anything moved.

    Two separate defects are repaired here:

      * An author node that names something other than the editorial company.
        552 pages carried `"author": {"@type": "Organization"}` whose name was a
        bare domain string or the publication's own title, while the visible
        attribution named a person. Machine-readable and human-readable
        authorship disagreed on every one of them.

      * An Article with no author node at all. 36 pages had a visible byline in
        the footer and nothing in the graph, which is the same disagreement with
        one side missing.

    A Person node is never written. The author is an organisation because the
    pages are not written by a person, and turning the byline into a name would
    be the fabrication this whole change exists to remove.
    """
    changed = False
    if isinstance(node, list):
        for item in node:
            changed |= _normalise_author_nodes(item, entity)
        return changed
    if not isinstance(node, dict):
        return False

    for value in node.values():
        if isinstance(value, (dict, list)):
            changed |= _normalise_author_nodes(value, entity)

    want = _canonical_author(entity)
    types = node.get("@type")
    types = types if isinstance(types, list) else [types]
    is_bylined = any(t in BYLINED_TYPES for t in types if isinstance(t, str))

    if "author" in node:
        if node["author"] != want:
            node["author"] = want
            changed = True
    elif is_bylined:
        # Insert next to the headline rather than appending, so the graph reads
        # the way a generator would have written it.
        rebuilt, placed = {}, False
        for key, value in node.items():
            rebuilt[key] = value
            if not placed and key in ("headline", "name"):
                rebuilt["author"] = want
                placed = True
        if not placed:
            rebuilt["author"] = want
        node.clear()
        node.update(rebuilt)
        changed = True
    return changed


def normalise_jsonld_author(text: str, pub_title: str) -> str:
    """Rewrite the JSON-LD byline to match the visible one.

    Only a block that actually needs a change is re-serialised, so a page whose
    graph is already correct keeps its exact bytes. That matters: the three
    404.html files carry pretty-printed JSON-LD written by
    scripts/deterministic_build.py, and compacting them here would leave the two
    scripts reformatting the same file on alternate builds -- the failure mode
    already documented above for the footer whitespace.
    """
    entity = entity_for(pub_title)

    def repl(match: re.Match) -> str:
        open_tag, payload, close_tag = match.groups()
        try:
            graph = json.loads(payload)
        except (ValueError, TypeError):
            return match.group(0)  # not ours to fix; page_audit reports it
        if not _normalise_author_nodes(graph, entity):
            return match.group(0)
        return open_tag + json.dumps(graph, ensure_ascii=False) + close_tag

    return LDJSON_RE.sub(repl, text)


def install(text: str, pub_title: str, domain: str, editor_addr: str,
            names_by_domain: dict, disclosure: str = "",
            retired_disclosures: tuple = ()) -> str:
    # --- legacy inline table CSS -----------------------------------------
    text = LEGACY_TABLE_CSS_RE.sub("", text)

    # --- withdrawn ownership sentence in the page body --------------------
    if disclosure:
        text = refresh_disclosure_sentence(text, disclosure, list(retired_disclosures))

    # --- JSON-LD byline ---------------------------------------------------
    # Runs here, in the same pass that writes the visible footer byline, so the
    # two are produced from one call to byline.entity_for() and cannot drift.
    text = normalise_jsonld_author(text, pub_title)

    # --- favicon ----------------------------------------------------------
    # Each publication ships its own /favicon.svg. It is the identity marker a
    # reader actually sees most often, and all three previously had none.
    if 'rel="icon"' not in text and HEAD_END_RE.search(text):
        text = HEAD_END_RE.sub(FAVICON_LINK + "</head>", text, count=1)

    # --- footer -----------------------------------------------------------
    footer = render_footer(pub_title, domain, editor_addr)
    if FOOTER_RE.search(text):
        text = FOOTER_RE.sub(lambda _m: footer, text, count=1)
    elif BODY_END_RE.search(text):
        text = BODY_END_RE.sub(footer + "\n</body>", text, count=1)
    else:
        text = text + footer

    # --- affiliate disclosure --------------------------------------------
    text = DISCLOSURE_RE.sub("", text)          # drop any previous copy first
    names = affiliated_names_on(text, names_by_domain)
    if names:
        block = render_disclosure(pub_title, domain, names)
        heading = CITATION_HEADING_RE.search(text)
        if heading:
            text = text[:heading.start()] + block + text[heading.start():]
        else:
            end = MAIN_END_RE.search(text)
            if end:
                text = text[:end.start()] + block + text[end.start():]
            else:
                text = text.replace("</body>", block + "</body>", 1)
    return text


def main() -> int:
    write = "--write" in sys.argv
    publications = load("data/publications.json")
    brands = load("data/brands.json")
    editorial = load("data/editorial.json")
    names_by_domain = brand_name_by_domain(brands)

    changed, unchanged, skipped = [], 0, []

    for pub in publications:
        folder = ROOT / pub["folder"]
        domain = pub["working_domain"]
        pid = pub["id"]
        if pid not in editorial["publications"]:
            raise SystemExit(f"data/editorial.json has no entry for publication '{pid}'")
        prefix = editorial["publications"][pid]["contact_prefixes"]["editor"]
        editor_addr = f"{prefix}@{domain}"

        for path in sorted(folder.rglob("*.html")):
            rel = str(path.relative_to(ROOT))
            if "/agency/" in "/" + rel:
                skipped.append(rel)
                continue
            original = path.read_text(encoding="utf-8")
            updated = install(
                original, pub["title"], domain, editor_addr, names_by_domain,
                disclosure=pub.get("disclosure", ""),
                retired_disclosures=tuple(pub.get("retired_disclosures") or ()),
            )

            # Nothing installed may point off-domain. Check only what we added.
            for found in re.findall(r'https?://[^\s"\'<>)]+', footer_and_disclosure(updated)):
                if host_of(found) != host_of(domain):
                    raise SystemExit(f"{rel}: installed chrome points off-domain: {found}")

            if updated == original:
                unchanged += 1
                continue
            changed.append(rel)
            if write:
                path.write_text(updated, encoding="utf-8")

    print(json.dumps({
        "mode": "write" if write else "check",
        "changed": len(changed), "unchanged": unchanged, "skipped": len(skipped),
        "sample": changed[:5],
    }, indent=2))
    if not write and changed:
        print("\n(dry run -- pass --write to apply)")
    return 0


def footer_and_disclosure(text: str) -> str:
    """Just the markup this script owns, for the off-domain check."""
    parts = FOOTER_RE.findall(text) + DISCLOSURE_RE.findall(text)
    return "".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
