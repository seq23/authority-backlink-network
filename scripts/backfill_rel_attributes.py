#!/usr/bin/env python3
"""Backfill rel="sponsored nofollow" on already-published affiliated links.

Idempotent: an anchor that already carries both tokens is left byte-identical, so
this can run repeatedly and inside the build without churn.

Three modes:
  (no flag)    rewrite in place
  --dry-run    report what would change, write nothing
  --check      the same scan as a release validator; exits non-zero if any
               affiliated link is missing its disclosure

Existing rel tokens are preserved and merged, never overwritten - dropping an
existing noopener would be a real regression.

Scope matches scripts/affiliation.py: absolute http(s) links to a domain listed in
data/brands.json. Relative links, canonicals, stylesheets and schema.org URLs are
untouched because none resolve to an affiliated host. The /agency/ dashboard is
skipped: it is a noindex operator view, not published content.
"""
from __future__ import annotations
import os, re, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from affiliation import is_affiliated, REL_VALUE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRY = "--dry-run" in sys.argv or "--check" in sys.argv
# --check is the same scan, wired as a release validator. Nothing else in this
# repository fails when an affiliated link is missing rel="sponsored nofollow":
# validate_brand_link_concentration.py uses the sponsored token to *select*
# commercial links, so a link that lost its rel drops out of the count instead
# of being reported. An undisclosed affiliate link on a publication whose only
# asset is credibility is the failure this catches.
CHECK = "--check" in sys.argv
SKIP_PARTS = ("/agency/",)

OPEN_TAG = re.compile(r'<a\s+([^>]*?)>', re.I | re.S)
HREF = re.compile(r'href="([^"]*)"', re.I)
REL = re.compile(r'\srel="([^"]*)"', re.I)


def fix_attrs(attrs: str) -> tuple[str, bool]:
    m = HREF.search(attrs)
    if not m or not is_affiliated(m.group(1)):
        return attrs, False
    rm = REL.search(attrs)
    existing = rm.group(1).split() if rm else []
    merged = list(existing)
    for t in REL_VALUE.split():
        if t not in merged:
            merged.append(t)
    if merged == existing:
        return attrs, False
    rel = ' rel="' + " ".join(merged) + '"'
    return (REL.sub(rel, attrs, count=1) if rm else attrs.rstrip() + rel), True


def main() -> int:
    changed_files = changed_links = scanned = 0
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "dist", "reports", "artifacts"}]
        for fn in files:
            if not fn.endswith(".html"):
                continue
            path = os.path.join(base, fn)
            rel_path = os.path.relpath(path, ROOT)
            if any(p in "/" + rel_path.replace(os.sep, "/") for p in SKIP_PARTS):
                continue
            scanned += 1
            src = open(path, encoding="utf-8", errors="ignore").read()
            hits = [0]

            def repl(m):
                new, did = fix_attrs(m.group(1))
                if did:
                    hits[0] += 1
                    return "<a " + new + ">"
                return m.group(0)

            out = OPEN_TAG.sub(repl, src)
            if hits[0]:
                changed_files += 1
                changed_links += hits[0]
                if not DRY:
                    open(path, "w", encoding="utf-8").write(out)
    if CHECK:
        print(json.dumps({
            "validator": "affiliate_rel_disclosure",
            "status": "FAIL" if changed_links else "PASS",
            "hard_failures": changed_files,
            "strong_warnings": 0,
            "soft_warnings": 0,
            "pages_scanned": scanned,
            "links_missing_rel": changed_links,
            "pages_affected": changed_files,
            "remedy": "npm run links:backfill-rel",
        }, indent=2))
        return 1 if changed_links else 0
    print(f"[backfill:rel-attributes]{' DRY-RUN' if DRY else ''} scanned={scanned} files_changed={changed_files} links_changed={changed_links}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
