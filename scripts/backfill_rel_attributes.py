#!/usr/bin/env python3
"""Backfill rel="sponsored nofollow" on already-published affiliated links.

Idempotent: an anchor that already carries both tokens is left byte-identical, so
this can run repeatedly and inside the build without churn.

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

ROOT = os.getcwd()
DRY = "--dry-run" in sys.argv
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
    print(f"[backfill:rel-attributes]{' DRY-RUN' if DRY else ''} scanned={scanned} files_changed={changed_files} links_changed={changed_links}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
