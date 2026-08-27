#!/usr/bin/env python3
"""Clean deterministic rebuild parity for governed derived site artifacts."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import re
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from lib import lastmod_ledger, site_urls

ROOT = Path(__file__).resolve().parents[1]
PUBLICATIONS = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
BUILD_DATE = os.getenv("BUILD_DATE", "2026-01-01")


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    tmp.replace(path)



def render_404(source: Path, domain: str) -> str:
    """Build a 404 page that inherits the site's own styles.

    Cloudflare Pages answers HTTP 200 with the site index for any unmatched
    path when the output directory has no 404.html. Every nonexistent URL on
    these domains was serving a duplicate of the homepage under a 200, which
    lets search engines index unlimited synthetic URLs. Deriving the shell from
    index.html keeps the page on-brand without restating design tokens here.
    """
    index = (source / "index.html").read_text(encoding="utf-8", errors="ignore")
    # The favicon is lifted alongside the stylesheet for the same reason: each
    # publication now ships its own /favicon.svg, and rebuilding the head
    # without it would strip the icon that install_editorial_chrome.py puts on
    # every other page -- leaving the two scripts to fight over 404.html on
    # alternate builds.
    styles = "\n".join(
        re.findall(r"<style[\s\S]*?</style>", index, re.I)
        + re.findall(r'<link[^>]+rel=["\']stylesheet["\'][^>]*>', index, re.I)
        + re.findall(r'<link[^>]+rel=["\']icon["\'][^>]*>', index, re.I)
    )
    title_match = re.search(r"<title>([^<]*)</title>", index, re.I)
    site_name = re.split(r"\s+[|\u2014-]\s+", title_match.group(1))[0].strip() if title_match else domain
    footer_match = re.search(r"<footer[\s\S]*?</footer>", index, re.I)
    footer = footer_match.group(0) if footer_match else ""
    ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"Page not found \u00b7 {site_name}",
        "@id": f"https://{domain}/404.html",
        "url": f"https://{domain}/404.html",
        "isPartOf": {"@type": "WebSite", "name": site_name, "url": f"https://{domain}/"},
    }, indent=2)
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>Page not found &middot; {escape(site_name)}</title>\n"
        '  <meta name="robots" content="noindex, follow">\n'
        f'  <meta name="description" content="That page could not be found on {escape(site_name)}. '
        'The address may be mistyped, or the page may have been moved or retired.">\n'
        f'  <link rel="canonical" href="https://{domain}/404.html">\n'
        f"{styles}\n"
        "  <style>\n"
        "    .nf-wrap { max-width: 40rem; margin: 0 auto; padding: 4rem 1.25rem; }\n"
        "    .nf-code { font-size: .75rem; letter-spacing: .12em; text-transform: uppercase; opacity: .7; margin: 0 0 .75rem; }\n"
        "    .nf-wrap h1 { margin: 0 0 .75rem; text-wrap: balance; }\n"
        "    .nf-wrap p { margin: 0 0 1.5rem; max-width: 34rem; }\n"
        "  </style>\n</head>\n<body>\n  <main class=\"nf-wrap\">\n"
        '    <p class="nf-code">Error 404</p>\n'
        "    <h1>We couldn&rsquo;t find that page</h1>\n"
        "    <p>The address may be mistyped, or the page may have been moved or retired since it was linked.</p>\n"
        f'    <p><a href="/">Return to {escape(site_name)}</a></p>\n'
        "  </main>\n"
        f"{footer}\n"
        f'  <script type="application/ld+json">{ld}</script>\n'
        "</body>\n</html>\n"
    )


def build_into(out: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Write the derived artifacts under `out`.

    Returns (artifact hashes, {url: content hash}). The second value is what the
    lastmod ledger is rebuilt from; it is returned rather than persisted here so
    that building twice and comparing - which main() does to prove determinism -
    cannot be perturbed by a write this function made on the first pass.
    """
    hashes: dict[str, str] = {}
    url_hashes: dict[str, str] = {}
    ledger = lastmod_ledger.load()
    today = lastmod_ledger.build_date()
    for pub in sorted(PUBLICATIONS, key=lambda x: x["id"]):
        source = ROOT / pub["folder"]
        target = out / pub["folder"]
        target.mkdir(parents=True, exist_ok=True)
        # Never emit a sitemap addressed to a host we could not resolve. A loud
        # build failure is recoverable; a silently broken sitemap is invisible
        # until someone reads Search Console months later.
        domain = site_urls.domain_of(pub)
        # <lastmod> is a claim about when the page changed, so it is derived from
        # the page's content hash, not from BUILD_DATE. Stamping the build date on
        # every URL moved all 565 of them on every run, which told a crawler
        # nothing about which page changed and was false for the ones that did
        # not. Only a URL whose content hash differs from the ledger advances.
        #
        # The <loc> form comes from lib/site_urls.page_url(), shared with the two
        # other sitemap emitters, so no copy of it can drift back to the .html
        # form the origin answers 308 for.
        page_hashes: dict[str, str] = {
            loc: lastmod_ledger.content_hash(text)
            for _, loc, text in site_urls.published_pages(source, domain)
        }
        lastmods = lastmod_ledger.resolve(page_hashes, ledger, today)
        url_hashes.update(page_hashes)
        newest = max(lastmods.values()) if lastmods else today
        sitemap = site_urls.render_sitemap({loc: lastmods[loc] for loc in page_hashes})
        llms = f"# {domain}\n\nThis site contains editorial resource pages for humans and answer engines. Updated {newest}.\n\nSitemap: https://{domain}/sitemap.xml\n"
        not_found = render_404(source, domain)
        for name, value in (("sitemap.xml", sitemap), ("llms.txt", llms), ("404.html", not_found)):
            path = target / name
            atomic_text(path, value)
            hashes[f'{pub["folder"]}/{name}'] = hashlib.sha256(value.encode()).hexdigest()
    return hashes, url_hashes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="Write deterministic derived artifacts into the repository.")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        first, url_hashes = build_into(Path(a))
        second, _ = build_into(Path(b))
        differences = [k for k in sorted(set(first) | set(second)) if first.get(k) != second.get(k)]
        if differences:
            print(json.dumps({"status": "FAIL", "differences": differences}, indent=2))
            raise SystemExit(1)
        prior = lastmod_ledger.load().get("entries", {})
        ledger = lastmod_ledger.updated(url_hashes)
        if args.write:
            built = Path(a)
            for rel in first:
                src = built / rel
                dst = ROOT / rel
                atomic_text(dst, src.read_text(encoding="utf-8"))
            # Persisted only on --write. A validation run must leave no trace,
            # or "build twice and compare" would be comparing against a ledger
            # the first pass had already moved.
            lastmod_ledger.save(ledger)
        # Count what actually moved, not what happens to carry today's date. On
        # the day the ledger is seeded those are the same number, and reporting
        # the second as the first would overstate how much changed on any build
        # run on a date that already appears in the ledger.
        advanced = sum(1 for u, h in url_hashes.items() if prior.get(u, {}).get("hash") != h)
        print(json.dumps({
            "status": "PASS",
            "build_date": BUILD_DATE,
            "artifacts": len(first),
            "differences": [],
            "sitemap_urls": len(url_hashes),
            "lastmod_advanced_this_build": advanced,
        }, indent=2))


if __name__ == "__main__":
    main()
