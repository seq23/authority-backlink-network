#!/usr/bin/env python3
"""Every internal link the reader receives must resolve to a page the build publishes.

What this stops happening again
-------------------------------
On 2026-09-03 (crawl 01:08-01:39 UTC) Ahrefs reported "Page has links to broken
page" on 421 of 421 professional-resources URLs, 105 of 105 memphis-local URLs
and 105 of 105 founder-operator URLs -- every published page of all three
publications -- and site health fell to 4, 13 and 12.

Nothing in `sites/` was wrong. Resolved against the tree, all 21,988 internal
links were good; fetched from the live origins, all 631 published URLs returned
200. The broken link did not exist in the repository at all. Cloudflare's
**Email Address Obfuscation** rewrote the footer's `mailto:` anchor at the edge
into `<a href="/cdn-cgi/l/email-protection#hex">`, and
`https://<domain>/cdn-cgi/l/email-protection` -- no fragment, because fragments
are never sent to a server -- returns 404. One broken link, injected after the
origin, on every page of the network.

That is why this guard checks the markup the READER receives, not the markup the
build writes. A static check over `sites/` had nothing to find and would have
reported PASS through the whole outage. See scripts/lib/contact_link.py.

Two independent things fail hard
--------------------------------
  unresolved  an internal link -- in the file, or injected by the edge -- that
              points at a URL this build does not publish. Cloudflare Pages
              routing is modelled: `/x` serves `x.html`, `/x/` serves
              `x/index.html`, and `_redirects` prefixes are honoured.
  zero        the walk examined no pages, no internal links, or no email
              anchors. A guard that iterates an empty list reports PASS forever,
              so each of those three counts must be non-zero.

The edge rewrite is modelled from the same module the generators emit through
(`lib.contact_link`), not from a second copy of the rule, so the guard cannot
drift away from the markup it governs.

    python3 scripts/validators/validate_internal_links_resolve.py
"""
from __future__ import annotations

import json
import posixpath
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.contact_link import EMAIL_OFF_CLOSE, EMAIL_OFF_OPEN, is_wrapped  # noqa: E402

ANCHOR_RE = re.compile(r"<a\s[^>]*?href=[\"']([^\"']+)[\"']", re.I)
MAILTO_ANCHOR_RE = re.compile(r"<a\s[^>]*?href=[\"']mailto:[^\"']+[\"'][^>]*>.*?</a>", re.I | re.S)
NON_HTTP = ("mailto:", "tel:", "javascript:", "data:", "#")

# What Cloudflare Email Address Obfuscation puts in place of an unprotected
# mailto: anchor. The fragment carries the encoded address and is never sent to
# the origin, so the origin only ever sees this bare path -- and 404s it.
CDN_EMAIL_PROTECTION = "/cdn-cgi/l/email-protection"


def publications() -> list[dict]:
    return json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))


def redirect_prefixes(folder: Path) -> list[str]:
    """Paths `_redirects` makes serve something, so they are not broken links."""
    out: list[str] = []
    path = folder / "_redirects"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        source = line.split()[0]
        out.append(source[:-1] if source.endswith("*") else source)
    return out


def published_paths(folder: Path) -> set[str]:
    """Every site-absolute URL path this build actually serves.

    Cloudflare Pages serves `foo.html` at `/foo` and `dir/index.html` at `/dir/`
    and `/dir`, so each file contributes every path that reaches it.
    """
    served: set[str] = set()
    for file in folder.rglob("*"):
        if not file.is_file():
            continue
        rel = "/" + str(file.relative_to(folder)).replace("\\", "/")
        served.add(rel)
        if rel.endswith(".html"):
            served.add(rel[: -len(".html")])
            if rel.endswith("/index.html"):
                stem = rel[: -len("index.html")]
                served.add(stem)
                served.add(stem.rstrip("/") or "/")
    served.add("/")
    return served


def resolve(base_rel: str, href: str) -> str | None:
    """The site-absolute path `href` requests from a page published at base_rel.

    base_rel is the CLEAN url of the containing page ("/daily/x"), because that
    is what a relative href resolves against in the reader's browser -- not the
    ".html" file name.
    """
    parsed = urlparse(href)
    path = unquote(parsed.path)
    if not path:
        return None
    if path.startswith("/"):
        return posixpath.normpath(path) + ("/" if path.endswith("/") and path != "/" else "")
    parent = posixpath.dirname(base_rel) or "/"
    joined = posixpath.normpath(posixpath.join(parent, path))
    return joined + ("/" if path.endswith("/") else "")


def clean_url(rel_file: str) -> str:
    """The URL a published file is served at: sites/x/daily/y.html -> /daily/y."""
    url = "/" + rel_file
    if url.endswith("/index.html"):
        return url[: -len("index.html")]
    if url.endswith(".html"):
        return url[: -len(".html")]
    return url


def main() -> int:
    failures: list[str] = []
    pages_examined = 0
    links_examined = 0
    email_anchors_examined = 0
    unprotected_emails = 0
    per_site: dict[str, dict[str, int]] = {}
    broken: dict[tuple[str, str], set[str]] = defaultdict(set)

    for pub in publications():
        folder = ROOT / pub["folder"]
        domain = pub["working_domain"].lower().replace("www.", "")
        if not folder.is_dir():
            failures.append(f"HARD_FAIL {pub['folder']}: publication folder does not exist")
            continue
        served = published_paths(folder)
        prefixes = redirect_prefixes(folder)
        site_pages = site_links = site_email = 0

        for file in sorted(folder.rglob("*.html")):
            rel_file = str(file.relative_to(folder)).replace("\\", "/")
            base = clean_url(rel_file)
            markup = file.read_text(encoding="utf-8", errors="ignore")
            site_pages += 1

            hrefs = [h.strip() for h in ANCHOR_RE.findall(markup)]

            # The edge rewrite. Every mailto: anchor NOT inside the
            # <!--email_off--> markers is replaced by Cloudflare with a link to
            # CDN_EMAIL_PROTECTION, so the reader receives that link even though
            # this file does not contain it. Model it, then resolve it like any
            # other internal link -- that is the whole defect.
            for match in MAILTO_ANCHOR_RE.finditer(markup):
                site_email += 1
                if not is_wrapped(markup, match.start(), match.end()):
                    unprotected_emails += 1
                    hrefs.append(CDN_EMAIL_PROTECTION)

            for href in hrefs:
                if href.lower().startswith(NON_HTTP):
                    continue
                parsed = urlparse(href)
                if parsed.scheme in ("http", "https"):
                    host = parsed.netloc.lower().replace("www.", "")
                    if host != domain:
                        continue  # off-site; verify_external_sources.py owns those
                elif parsed.scheme:
                    continue
                target = resolve(base, href)
                if target is None:
                    continue
                site_links += 1
                if target in served or f"{target}/" in served:
                    continue
                if any(target.startswith(p) for p in prefixes):
                    continue
                broken[(domain, target)].add(f"{pub['folder']}/{rel_file}")

        per_site[domain] = {"pages": site_pages, "internal_links": site_links,
                            "email_anchors": site_email}
        pages_examined += site_pages
        links_examined += site_links
        email_anchors_examined += site_email

    print("INTERNAL LINKS RESOLVE")
    for domain, counts in sorted(per_site.items()):
        print(f"  {domain:<34} {counts['pages']:>4} pages  "
              f"{counts['internal_links']:>6} internal links  "
              f"{counts['email_anchors']:>4} email anchors")

    if pages_examined == 0 or links_examined == 0 or email_anchors_examined == 0:
        print("INTERNAL LINKS RESOLVE: FAIL")
        print(f"  HARD_FAIL examined {pages_examined} pages, {links_examined} internal "
              f"links and {email_anchors_examined} email anchors; this guard must not "
              f"report PASS on an empty walk")
        return 1

    if unprotected_emails:
        print(f"  edge-injected links modelled: {unprotected_emails}")

    for (domain, target), sources in sorted(broken.items(), key=lambda kv: -len(kv[1])):
        listed = ", ".join(sorted(sources)[:3])
        more = f" (+{len(sources) - 3} more)" if len(sources) > 3 else ""
        why = ""
        if target == CDN_EMAIL_PROTECTION:
            why = (" -- Cloudflare Email Address Obfuscation rewrites an unprotected "
                   f"mailto: anchor to this path, which the origin 404s. Emit it through "
                   f"lib.contact_link.mailto_link() so it is wrapped in "
                   f"{EMAIL_OFF_OPEN}...{EMAIL_OFF_CLOSE}.")
        failures.append(
            f"HARD_FAIL https://{domain}{target} is linked from {len(sources)} published "
            f"page(s) but this build publishes nothing there{why} Linked from: {listed}{more}")

    if failures:
        print("INTERNAL LINKS RESOLVE: FAIL")
        for line in failures:
            print(f"  {line}")
        return 1

    print(f"  {links_examined} internal links across {pages_examined} pages all resolve "
          f"to published URLs; {email_anchors_examined} email anchors all protected from "
          f"the edge rewrite")
    print("INTERNAL LINKS RESOLVE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
