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
            )
            written += write_if_changed(source / "topics" / f'{hub["slug"]}.html', page, write)

        # -- breadcrumbs and sibling links on every member page
        for hub in hubs:
            rows = members[hub["slug"]]
            for index, row in enumerate(rows):
                path = source / row["rel"]
                text = path.read_text(encoding="utf-8", errors="ignore")
                trail = [(pub["title"], home), (hub["title"], hub_urls[hub["slug"]]),
                         (row["title"] or hub["title"], row["url"])]
                related = [(other["title"], other["url"])
                           for other in neighbours(rows, index)]
                text = page_composer.apply_page_navigation(
                    text,
                    breadcrumb=page_composer.breadcrumb_html(trail),
                    breadcrumb_schema=page_composer.breadcrumb_schema(trail),
                    related=page_composer.related_html(
                        f'More on {hub["title"].lower()}', related,
                        hub["title"], hub_urls[hub["slug"]]),
                )
                text = set_canonical(text, row["url"])
                text = normalize_internal_links(text, row["rel"], domain, known)
                written += write_if_changed(path, text, write)

        # -- canonical on every other publishable page, and the index's hub list
        member_rels = {row["rel"] for rows in members.values() for row in rows}
        for rel, url, text in site_urls.published_pages(source, domain):
            if rel in member_rels:
                continue
            updated = normalize_internal_links(set_canonical(text, url), rel, domain, known)
            if rel == "index.html":
                updated = page_composer.apply_topic_index(
                    updated,
                    page_composer.topic_index_html(
                        pub["title"],
                        [(h["title"], hub_urls[h["slug"]], h["summary"],
                          len(members[h["slug"]])) for h in hubs]))
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

    problems = {}
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


def neighbours(rows: list[dict], index: int, span: int = 4) -> list[dict]:
    """Up to `span` siblings around `index`, wrapping, never the page itself.

    Sequential neighbours rather than a random sample: adjacent rows share a
    cluster, so the links a reader is offered are the closest pages to the one
    they are on, and every page in the hub is linked from some other page in it.
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
