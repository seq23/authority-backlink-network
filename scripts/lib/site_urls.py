"""The one place that decides which URL a published file is addressed by.

Why this module exists
----------------------
Three separate emitters wrote sitemaps - `scripts/deterministic_build.py`,
`authority_v4_autopilot.update_sitemap()` and
`portfolio_backlink_engine.refresh_assets()` - and each one built its `<loc>`
with its own copy of the same f-string:

    loc = f'https://{domain}/' if rel == 'index.html' else f'https://{domain}/{rel}'

That named the `.html` file, and Cloudflare Pages does not serve the `.html`
form. It answers 308 and redirects to the extensionless path:

    GET /about       -> 200
    GET /about.html  -> 308  ->  /about

So 562 of the 565 URLs in the three sitemaps sent a crawler to a redirect on the
first request of every page, and the canonical tags pointed at the same
redirecting form. All three publications sat at zero indexed pages in Bing.

Fixing that in three copies of one f-string is how it drifts back. Every URL a
publication publishes - sitemap `<loc>`, `<link rel="canonical">`, internal
navigation, llms.txt, IndexNow submissions - now comes from `page_url()` here.

What the URL form is
--------------------
`index.html` is the site root, `foo/index.html` is the directory `foo/`, and any
other `foo/bar.html` drops the extension: `/foo/bar`. That is what the origin
serves 200 for. The 308s stay in place, because links to the `.html` form exist
off-site and outside this repository, and removing a working redirect to tidy up
the shape of a URL loses whatever equity those links carry.
"""
from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

# The agency dashboard is an internal surface, and a page that has opted out of
# indexing must not be advertised in a sitemap. Both rules were duplicated in
# all three emitters; they live here now for the same reason page_url() does.
_NOINDEX = re.compile(
    r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', re.I)


def relative_path(path: Path, source: Path) -> str:
    return path.relative_to(source).as_posix()


def is_publishable(rel: str, text: str) -> bool:
    """True when this file belongs in a sitemap for its publication."""
    return not rel.startswith("agency/") and not _NOINDEX.search(text)


def url_path(rel: str) -> str:
    """The path a publication serves this file at, without the leading slash.

    'index.html'      -> ''            (the site root)
    'topics/index.html' -> 'topics/'   (a directory index)
    'daily/x.html'    -> 'daily/x'     (extensionless; the .html form 308s here)
    """
    if rel == "index.html":
        return ""
    if rel.endswith("/index.html"):
        return rel[: -len("index.html")]
    if rel.endswith(".html"):
        return rel[: -len(".html")]
    return rel


def page_url(domain: str, rel: str) -> str:
    """The single absolute URL this file is published at."""
    if not domain:
        raise ValueError("page_url requires a domain")
    return f"https://{domain}/{url_path(rel)}"


def domain_of(publication: dict) -> str:
    """The host a publication is served from, or a loud failure.

    data/publications.json stores it under "working_domain". Reading only
    "domain"/"default_domain" once yielded None for every publication and
    shipped three sitemaps full of "https://None/...".
    """
    domain = (publication.get("working_domain") or publication.get("domain")
              or publication.get("default_domain"))
    if not domain:
        raise SystemExit(
            f'publication {publication.get("id")!r} has no domain '
            '(expected "working_domain" in data/publications.json)')
    return domain


def published_pages(source: Path, domain: str) -> list[tuple[str, str, str]]:
    """[(relative path, absolute URL, file text)] for every publishable page."""
    out: list[tuple[str, str, str]] = []
    for path in sorted(source.rglob("*.html"),
                       key=lambda p: p.relative_to(source).as_posix()):
        rel = relative_path(path, source)
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not is_publishable(rel, text):
            continue
        out.append((rel, page_url(domain, rel), text))
    return out


def render_sitemap(lastmods: dict[str, str]) -> str:
    """A urlset over {url: lastmod}, in the order given."""
    urls = "\n".join(
        f"<url><loc>{escape(loc)}</loc><lastmod>{lastmod}</lastmod></url>"
        for loc, lastmod in lastmods.items())
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls}\n</urlset>\n")
