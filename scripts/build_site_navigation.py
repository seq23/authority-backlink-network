#!/usr/bin/env python3
"""Rebuild the derived navigation surface of the three publications.

Two defects put all three publications at zero indexed pages in Bing, and this
script is the repair for both.

1. Every URL in every sitemap named the `.html` file. Cloudflare Pages answers
   308 for that form and serves the extensionless path, so a crawler following
   the sitemap hit a redirect on the first request of all 562 of them. The
   canonical tags named the same redirecting form, and 57 pages carried no
   canonical at all.

2. 546 of 568 pages had no inbound internal link from anywhere on their own
   site. A page nothing links to is a page a crawler has no reason to fetch and
   no signal to rank, whatever the sitemap says.

What it writes
--------------
* `<link rel="canonical">` on every publishable page, from
  `lib.site_urls.page_url()` - the same helper the sitemap emitters use.
* One hub page per topic in `data/topic-taxonomy.json`, under `topics/`, listing
  its members by absolute URL grouped under the recorded cluster they belong to.
* A breadcrumb `<nav>` and a BreadcrumbList node on every daily page, and a
  related-pages `<nav>` linking its siblings inside the same hub.
* A "Browse by topic" section on each publication index linking every hub.

All of it is idempotent: the injected blocks are delimited by `data-nav`
attributes and replaced wholesale on each run, so a second run writes the same
bytes.

Why the injected navigation sits inside <nav>
---------------------------------------------
`lib.lastmod_ledger.content_hash()` hashes visible text with `<nav>`, `<footer>`,
`<head>`, `<script>` and `<style>` stripped. Adding a breadcrumb to 565 pages
would otherwise register as 565 content changes and collapse every lastmod onto
one build day, which is what erased the dates reconstructed from git history the
last time this was attempted. Hub member lists are *not* inside `<nav>`: on a hub
page the list of members is the content, and its lastmod should move when
membership does.

Diagnostics go to stderr. stdout is a single JSON receipt, because
`scripts/validate.py::parse_child_receipt()` runs `json.loads()` over a child's
entire stdout.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import page_composer, site_urls  # noqa: E402

PUBLICATIONS = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
TAXONOMY = json.loads((ROOT / "data/topic-taxonomy.json").read_text(encoding="utf-8"))
CLUSTER_ARTICLES = ROOT / "content-bank/cluster-articles"

CANONICAL_RE = re.compile(r'<link[^>]+rel=["\']canonical["\'][^>]*>', re.I)
HEAD_CLOSE_RE = re.compile(r"</head>", re.I)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
DESCRIPTION_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content="([^"]*)"', re.I)

# --- how a page declares which topic it belongs to --------------------------
# Three generators produce daily pages and each records the topic differently.
# None of these is a guess: every one is a value the generator wrote.
TOPIC_ROW_RE = re.compile(r"<tr><td>Topic</td><td>([^<]*)</td></tr>")
TOPIC_CONTEXT_RE = re.compile(r"Topic context:</strong>\s*([^<.]*)")
DATE_PREFIX_RE = re.compile(r"^\d{4}-\d\d-\d\d-")


def stderr(message: str) -> None:
    print(message, file=sys.stderr)


def cluster_article_map() -> dict[str, str]:
    """{slug: cluster} for the hand-authored cluster articles."""
    out: dict[str, str] = {}
    for path in sorted(CLUSTER_ARTICLES.glob("*.json")):
        for article in json.loads(path.read_text(encoding="utf-8")).get("articles", []):
            if article.get("slug") and article.get("cluster"):
                out[article["slug"]] = article["cluster"]
    return out


SLUG_CLUSTERS = cluster_article_map()


def cluster_of(rel: str, text: str) -> str | None:
    """The cluster this page records for itself, or None if it records none."""
    row = TOPIC_ROW_RE.search(text)
    if row:
        return row.group(1).strip()
    slug = DATE_PREFIX_RE.sub("", Path(rel).stem)
    if slug in SLUG_CLUSTERS:
        return SLUG_CLUSTERS[slug]
    context = TOPIC_CONTEXT_RE.search(text)
    return context.group(1).strip() if context else None


def page_title(text: str) -> str:
    """The page's own h1, falling back to the part of <title> before the site name."""
    match = H1_RE.search(text)
    if match:
        return html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()
    match = TITLE_RE.search(text)
    if not match:
        return ""
    return html.unescape(re.split(r"\s+\|\s+", match.group(1))[0]).strip()


# --- pass 1: canonical ------------------------------------------------------
def set_canonical(text: str, url: str) -> str:
    """Replace, or insert, the canonical link so it names `url`."""
    tag = f'<link rel="canonical" href="{html.escape(url, quote=True)}">'
    # Replace the tag in place, leaving whatever whitespace already surrounds it.
    # Normalising that whitespace here made the pass non-idempotent: a freshly
    # composed hub page and the same page read back differed by one newline, so
    # every run reported the same 56 files as changed.
    if CANONICAL_RE.search(text):
        return CANONICAL_RE.sub(lambda _m: tag, text, count=1)
    return HEAD_CLOSE_RE.sub(tag + "</head>", text, count=1)


ANCHOR_HREF_RE = re.compile(r'(<a\b[^>]*?\bhref=")([^"]+)(")', re.I)


def normalize_internal_links(text: str, rel: str, domain: str, known: set[str]) -> str:
    """Point every internal anchor at the URL the origin serves 200 for.

    Only anchors, and only ones that resolve to a page of this same publication:
    a stylesheet href, an off-site destination, and a link to another property in
    the registry are all left exactly as they are. A root-relative link stays
    root-relative and an absolute one stays absolute - both address the same URL,
    and rewriting the form of a link that already works buys nothing.
    """
    def replace(match: re.Match) -> str:
        href = match.group(2)
        target = resolve_href(href, rel, known, domain)
        if not target:
            return match.group(0)
        # A fragment or query on an internal link is the reader's destination
        # within the page and has to survive the rewrite.
        suffix = re.search(r"[?#].*$", href)
        path = site_urls.url_path(target) + (suffix.group(0) if suffix else "")
        new = (f"https://{domain}/{path}" if href.startswith(("http://", "https://"))
               else "/" + path)
        return match.group(1) + new + match.group(3)

    return ANCHOR_HREF_RE.sub(replace, text)


# --- pass 2 and 3: the hubs and the per-page navigation ----------------------
def load_hubs(pub_id: str) -> list[dict]:
    hubs = TAXONOMY["publications"][pub_id]["hubs"]
    slugs = [h["slug"] for h in hubs]
    duplicates = [s for s, n in Counter(slugs).items() if n > 1]
    if duplicates:
        raise SystemExit(f"{pub_id}: duplicate hub slugs in the taxonomy: {duplicates}")
    return hubs


def assign_members(source: Path, domain: str, hubs: list[dict]) -> tuple[dict[str, list[dict]], list[str]]:
    """Map every daily page onto exactly one hub, by its recorded cluster."""
    hub_of_cluster: dict[str, str] = {}
    for hub in hubs:
        for cluster in hub["clusters"]:
            key = cluster.strip().lower()
            if key in hub_of_cluster:
                raise SystemExit(
                    f"cluster {cluster!r} is claimed by two hubs: "
                    f"{hub_of_cluster[key]} and {hub['slug']}")
            hub_of_cluster[key] = hub["slug"]

    members: dict[str, list[dict]] = defaultdict(list)
    unmapped: list[str] = []
    for rel, url, text in site_urls.published_pages(source, domain):
        if not rel.startswith("daily/"):
            continue
        cluster = cluster_of(rel, text)
        slug = hub_of_cluster.get((cluster or "").strip().lower())
        if not slug:
            unmapped.append(f"{rel} :: {cluster!r}")
            continue
        members[slug].append({"rel": rel, "url": url, "cluster": cluster,
                              "title": page_title(text)})
    for rows in members.values():
        rows.sort(key=lambda r: (r["cluster"].lower(), r["title"].lower()))
    return members, unmapped


def rebuild(write: bool) -> dict:
    receipt_pubs = []
    unmapped_all: list[str] = []
    empty_hubs: list[str] = []
    thin_hubs: list[str] = []
    written = 0

    for pub in sorted(PUBLICATIONS, key=lambda p: p["id"]):
        source = ROOT / pub["folder"]
        domain = site_urls.domain_of(pub)
        hubs = load_hubs(pub["id"])
        members, unmapped = assign_members(source, domain, hubs)
        unmapped_all += unmapped

        # An empty hub carries no outbound editorial link, which is a blocking
        # conversion_path failure in validate_content_pattern_contract.js, and it
        # is not navigation either. A one-member hub is a redirect wearing a
        # costume. Neither is ever generated: the taxonomy is corrected instead.
        for hub in hubs:
            count = len(members.get(hub["slug"], []))
            if count == 0:
                empty_hubs.append(f'{pub["id"]}/{hub["slug"]}')
            elif count < TAXONOMY["minimum_hub_members"]:
                thin_hubs.append(f'{pub["id"]}/{hub["slug"]} ({count})')
        if empty_hubs or thin_hubs:
            continue

        hub_urls = {h["slug"]: site_urls.page_url(domain, f'topics/{h["slug"]}.html')
                    for h in hubs}
        home = f"https://{domain}/"
        # The set of paths that exist, for rewriting internal .html anchors onto
        # the extensionless form. Hub pages are included whether or not they have
        # been written yet, so a first run and a second run agree.
        known = {rel for rel, _u, _t in site_urls.published_pages(source, domain)}
        known |= {f'topics/{h["slug"]}.html' for h in hubs}
        known.add("index.html")

        # -- hub pages
        hub_overviews = [(t, u) for t, u, _r in
                         overview_pages(source, domain,
                                        {row["rel"] for rs in members.values()
                                         for row in rs}, hubs)]
        for hub in hubs:
            page = page_composer.compose_hub_page(
                hub=hub,
                pub=pub,
                domain=domain,
                url=hub_urls[hub["slug"]],
                home=home,
                members=members[hub["slug"]],
                siblings=[(h["title"], hub_urls[h["slug"]]) for h in hubs
                          if h["slug"] != hub["slug"]],
                overviews=hub_overviews,
            )
            written += write_if_changed(source / "topics" / f'{hub["slug"]}.html', page, write)

        # -- the publication-level furniture every page can carry
        hub_rows = [(h["title"], hub_urls[h["slug"]], len(members[h["slug"]]))
                    for h in hubs]
        member_rels = {row["rel"] for rows in members.values() for row in rows}
        overviews = overview_pages(source, domain, member_rels, hubs)
        about = [(t, u) for t, u, r in overviews if r == "about.html"]
        # On a daily page the library nav names the hubs and the about page: the
        # publication's structure, not a copy of its whole page list. The standing
        # overview pages are named on the publication-level pages, which is where
        # a reader browsing the publication rather than a topic actually is.
        # No home link in the block: every page that carries it already links
        # home from its breadcrumb or its header nav. And one nav per hub, each
        # omitting that hub: the page's breadcrumb already links its own hub with
        # the same anchor text, and validation/repair.py answers an exact
        # (href, anchor) repeat by deleting the second anchor outright - which
        # silently un-linked 543 pages and put the rebuild and the repair pass
        # into a loop, each undoing the other.
        daily_library = {
            hub["slug"]: page_composer.library_nav_html(
                pub["title"], home, hub_rows, about, home_link=False,
                self_url=hub_urls[hub["slug"]])
            for hub in hubs}
        latest_rows = recent_pages(members)

        # The publication's whole running order, for topping up a hub too small
        # to offer a full set of siblings.
        library_order = [(h["slug"], h["title"], row)
                         for h in hubs for row in members[h["slug"]]]
        position = {(slug, r["rel"]): i
                    for i, (slug, _t, r) in enumerate(library_order)}

        # -- breadcrumbs and sibling links on every member page
        for hub in hubs:
            rows = members[hub["slug"]]
            for index, row in enumerate(rows):
                path = source / row["rel"]
                text = path.read_text(encoding="utf-8", errors="ignore")
                before = link_targets(text)
                trail = [(pub["title"], home), (hub["title"], hub_urls[hub["slug"]]),
                         (row["title"] or hub["title"], row["url"])]
                siblings = neighbours(rows, index)
                related = [(other["title"], other["url"]) for other in siblings]
                topup = cross_hub_topup(
                    library_order, position[(hub["slug"], row["rel"])],
                    hub["slug"], SIBLING_SPAN - len(siblings))
                text = page_composer.apply_page_navigation(
                    text,
                    breadcrumb=page_composer.breadcrumb_html(trail),
                    breadcrumb_schema=page_composer.breadcrumb_schema(trail),
                    related=page_composer.related_html(
                        f'More on {hub["title"].lower()}', related,
                        hub["title"], hub_urls[hub["slug"]]),
                    more=page_composer.more_nav_html(pub["title"], topup),
                    library=daily_library[hub["slug"]],
                )
                text = set_canonical(text, row["url"])
                text = normalize_internal_links(text, row["rel"], domain, known)
                assert_no_links_lost(row["rel"], before, text)
                written += write_if_changed(path, text, write)

        # -- canonical on every other publishable page, and the index's hub list
        overview_rels = {r for _t, _u, r in overviews}
        for rel, url, text in site_urls.published_pages(source, domain):
            if rel in member_rels:
                continue
            before = link_targets(text)
            updated = normalize_internal_links(set_canonical(text, url), rel, domain, known)
            if rel == "index.html":
                updated = page_composer.apply_topic_index(
                    updated,
                    page_composer.topic_index_html(
                        pub["title"],
                        [(h["title"], hub_urls[h["slug"]], h["summary"],
                          len(members[h["slug"]])) for h in hubs]))
                updated = page_composer.apply_page_navigation(
                    updated, breadcrumb="", breadcrumb_schema={}, related="",
                    library="",
                    latest=page_composer.latest_nav_html(pub["title"], latest_rows))
            elif rel in overview_rels:
                # about.html and the standing overview pages carried a breadcrumb
                # on none of them and six internal links each. They are two clicks
                # from every hub now, and they say so in schema.
                title = page_title(text) or pub["title"]
                trail = [(pub["title"], home), (title, url)]
                updated = page_composer.apply_page_navigation(
                    updated,
                    breadcrumb=page_composer.breadcrumb_html(trail),
                    breadcrumb_schema=page_composer.breadcrumb_schema(trail),
                    related="",
                    library=page_composer.library_nav_html(
                        pub["title"], home, hub_rows,
                        [(t, u) for t, u, _r in overviews], self_url=url,
                        home_link=False),
                    latest=page_composer.latest_nav_html(pub["title"], latest_rows,
                                                         self_url=url))
            assert_no_links_lost(rel, before, updated)
            written += write_if_changed(source / rel, updated, write)

        receipt_pubs.append({
            "publication": pub["id"],
            "domain": domain,
            "hubs": len(hubs),
            "hub_members": {h["slug"]: len(members[h["slug"]]) for h in hubs},
            "smallest_hub": min(len(members[h["slug"]]) for h in hubs),
            "largest_hub": max(len(members[h["slug"]]) for h in hubs),
            "pages_in_a_hub": sum(len(v) for v in members.values()),
        })

    duplicate_anchor_pages = duplicate_anchor_audit()

    problems = {}
    if duplicate_anchor_pages:
        problems["pages_with_a_repeated_absolute_anchor"] = duplicate_anchor_pages[:20]
    if empty_hubs:
        problems["empty_hubs"] = empty_hubs
    if thin_hubs:
        problems["hubs_below_minimum_members"] = thin_hubs
    if unmapped_all:
        problems["pages_with_no_hub"] = unmapped_all[:50]
    return {
        "status": "FAIL" if problems else "PASS",
        "written": write,
        "files_changed": written,
        "minimum_hub_members": TAXONOMY["minimum_hub_members"],
        "publications": receipt_pubs,
        **problems,
    }


def overview_pages(source: Path, domain: str, member_rels: set[str],
                   hubs: list[dict]) -> list[tuple[str, str, str]]:
    """The publication-level pages: about, plus the standing overview pages.

    Everything publishable that is not a daily page, not a topic hub, and not the
    index. These are the pages whose subject is the publication rather than one
    topic, so they are the ones that carry the full library nav and the recently
    published list.
    """
    hub_rels = {f'topics/{h["slug"]}.html' for h in hubs}
    out = []
    for rel, url, text in site_urls.published_pages(source, domain):
        if rel in member_rels or rel in hub_rels or rel == "index.html":
            continue
        if rel.startswith(("daily/", "topics/")):
            continue
        out.append((page_title(text) or rel, url, rel))
    out.sort(key=lambda row: row[0].lower())
    return out


def recent_pages(members: dict[str, list[dict]], limit: int = 12
                 ) -> list[tuple[str, str, str]]:
    """The `limit` most recently published daily pages, newest first.

    The date is read from the page's own filename, which every daily generator
    writes as a `YYYY-MM-DD-` prefix. Pages without that prefix are skipped
    rather than given a guessed date.
    """
    rows = []
    for pages in members.values():
        for row in pages:
            stem = Path(row["rel"]).stem
            match = DATE_PREFIX_RE.match(stem)
            if match:
                rows.append((match.group(0).rstrip("-"), row["title"], row["url"]))
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    return [(title, url, date) for date, title, url in rows[:limit]]


ANY_ANCHOR_RE = re.compile(r'<a\b[^>]*?\bhref="([^"]+)"', re.I)


def link_targets(text: str) -> set[str]:
    """Every distinct href on the page.

    Destinations, not anchor tags. The publications write internal links as
    absolute `https://<domain>/...` URLs, so a scheme test cannot separate
    internal from external and there is no reason to try: the invariant this
    supports is that a navigation rebuild never costs the page a destination,
    and that holds for every href on it.

    Counting tags instead of destinations was wrong in one direction that
    matters. Dropping a second, identical link to the same URL - the home link
    the library nav repeated after the breadcrumb already carried it - lowers the
    tag count while removing nothing a reader or a crawler can reach, and
    page_validation.py reports that repeat as DUPLICATE_EXTERNAL_LINK.
    """
    return set(ANY_ANCHOR_RE.findall(text))


def assert_no_links_lost(rel: str, before: set[str], after_text: str) -> None:
    """A navigation pass may only add destinations. Abort rather than write a loss."""
    lost = before - link_targets(after_text)
    if lost:
        raise SystemExit(
            f"refusing to write {rel}: {len(lost)} link target(s) would be lost, "
            f"first {sorted(lost)[:3]}. A navigation rebuild adds links; it never "
            "removes one.")


ABSOLUTE_ANCHOR_RE = re.compile(
    r'<a\s+[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', re.I | re.S)


def repeated_absolute_anchors(text: str) -> list[tuple[str, str]]:
    """(href, anchor) pairs this page carries more than once.

    `validation/page_audit.py` calls an exact repeat DUPLICATE_EXTERNAL_LINK and
    `validation/repair.py` fixes it by deleting the second anchor tag and leaving
    its text as bare words. That is a page silently losing a link, and because
    this script would put the link straight back on the next run, the two passes
    undo each other forever. So the rebuild does not emit one: every block that
    can name a URL another block already names with the same words leaves it out.

    Matches the audit's own key: href with any trailing slash dropped, anchor
    text stripped of tags, whitespace-trimmed and lowercased.
    """
    seen: set[tuple[str, str]] = set()
    repeats = []
    for href, inner in ABSOLUTE_ANCHOR_RE.findall(text):
        key = (href.rstrip("/"), re.sub(r"<[^>]+>", "", inner).strip().lower())
        if key in seen:
            repeats.append(key)
        seen.add(key)
    return repeats


SIBLING_SPAN = 12


def cross_hub_topup(library_order: list[tuple[str, str, dict]], position: int,
                    own_slug: str, wanted: int) -> list[tuple[str, str, str]]:
    """`wanted` pages from hubs other than `own_slug`, from `position` onward.

    Returns (title, url, hub title). Empty when the page's own hub already
    supplied a full set of siblings, which is the common case: this only fires
    for hubs holding fewer than SIBLING_SPAN + 1 pages.
    """
    if wanted <= 0:
        return []
    out = []
    total = len(library_order)
    for offset in range(1, total):
        slug, hub_title, row = library_order[(position + offset) % total]
        if slug == own_slug:
            continue
        out.append((row["title"], row["url"], hub_title))
        if len(out) == wanted:
            break
    return out


def duplicate_anchor_audit() -> list[str]:
    """Every publishable page that carries the same (href, anchor) twice.

    Reported as a blocking problem in the receipt rather than left to be found
    when the repair pass quietly deletes the second copy.
    """
    out = []
    for pub in sorted(PUBLICATIONS, key=lambda p: p["id"]):
        source = ROOT / pub["folder"]
        domain = site_urls.domain_of(pub)
        for rel, _url, text in site_urls.published_pages(source, domain):
            repeats = repeated_absolute_anchors(text)
            if repeats:
                out.append(f'{pub["id"]}/{rel} :: {repeats[0][1]!r}')
    return sorted(out)


def neighbours(rows: list[dict], index: int, span: int = SIBLING_SPAN) -> list[dict]:
    """Up to `span` siblings around `index`, wrapping, never the page itself.

    Sequential neighbours rather than a random sample: adjacent rows share a
    cluster, so the links a reader is offered are the closest pages to the one
    they are on, and every page in the hub is linked from some other page in it.

    `span` was 4, which held the daily pages at six internal links out - two
    crumbs and four siblings. The one property in this estate that measurably
    earns AI-assistant citations sustains a median of 17 and is almost entirely
    free of orphans; 12 siblings plus the hub, the crumbs and the library nav is
    what clears that bar without the block ceasing to be topical. Rows are sorted
    by cluster, so the first neighbours are still same-cluster pages.
    """
    if len(rows) <= 1:
        return []
    out = []
    for offset in range(1, min(span, len(rows) - 1) + 1):
        out.append(rows[(index + offset) % len(rows)])
    return out


def write_if_changed(path: Path, text: str, write: bool) -> int:
    if path.exists() and path.read_text(encoding="utf-8", errors="ignore") == text:
        return 0
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        tmp.replace(path)
    return 1


# --- reachability, reported rather than assumed -----------------------------
def link_graph(source: Path, domain: str) -> tuple[dict[str, set[str]], set[str]]:
    rels = {rel for rel, _u, _t in site_urls.published_pages(source, domain)}
    rels.add("index.html")
    edges: dict[str, set[str]] = {}
    for path in sorted(source.rglob("*.html")):
        rel = path.relative_to(source).as_posix()
        if rel not in rels:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        out = set()
        for href in re.findall(r'<a[^>]+href="([^"]+)"', text, re.I):
            target = resolve_href(href, rel, rels, domain)
            if target and target != rel:
                out.add(target)
        edges[rel] = out
    return edges, rels


def resolve_href(href: str, current: str, rels: set[str], domain: str) -> str | None:
    import posixpath
    href = href.split("#")[0].split("?")[0]
    if not href:
        return None
    if href.startswith(("http://", "https://")):
        match = re.match(r"https?://(?:www\.)?([^/]+)(/.*)?$", href)
        if not match or match.group(1).lower() != domain:
            return None
        path = match.group(2) or "/"
    elif href.startswith("/"):
        path = href
    else:
        base = "/" + posixpath.dirname(current)
        path = posixpath.normpath(posixpath.join(base + "/", href))
    path = path.lstrip("/") or "index.html"
    if path.endswith("/"):
        path += "index.html"
    for candidate in (path, path + ".html", path + "/index.html"):
        if candidate in rels:
            return candidate
    return None


def reachability() -> dict:
    out = {}
    for pub in sorted(PUBLICATIONS, key=lambda p: p["id"]):
        source = ROOT / pub["folder"]
        domain = site_urls.domain_of(pub)
        edges, rels = link_graph(source, domain)
        inbound = Counter()
        for outs in edges.values():
            for target in outs:
                inbound[target] += 1
        orphans = sorted(r for r in rels if r != "index.html" and not inbound[r])
        depth = {"index.html": 0}
        queue = deque(["index.html"])
        while queue:
            current = queue.popleft()
            for target in edges.get(current, ()):
                if target not in depth:
                    depth[target] = depth[current] + 1
                    queue.append(target)
        out[pub["id"]] = {
            "published_pages": len(rels),
            "orphans": len(orphans),
            "orphan_paths": orphans[:20],
            "unreachable_from_root": sorted(r for r in rels if r not in depth)[:20],
            "click_depth": dict(sorted(Counter(depth.values()).items())),
            "max_click_depth": max(depth.values()) if depth else 0,
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="Write the rebuilt navigation into the repository.")
    args = ap.parse_args()
    receipt = rebuild(args.write)
    receipt["reachability"] = reachability()
    print(json.dumps(receipt, indent=2))
    raise SystemExit(1 if receipt["status"] != "PASS" else 0)


if __name__ == "__main__":
    main()
