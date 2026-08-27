#!/usr/bin/env python3
"""Fail if an owner/operator-only surface is present in the published site tree.

sites/ is served publicly. The authority publications allow every AI crawler and
carry no robots.txt Disallow rules, so a `noindex` meta keeps a page out of a search
index but does nothing to stop an LLM crawler or a person from fetching it. Anything
that discloses network operations therefore must not live under sites/ at all.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITES = ROOT / "sites"

# Route segments that may never appear under the published tree.
FORBIDDEN_SEGMENTS = {"agency", "admin", "operator", "internal", "ops", "dashboard"}

# Page-level markers that identify an operator surface regardless of its path.
FORBIDDEN_MARKERS = (
    re.compile(r"OWNER\s*/\s*OPERATOR VIEW", re.I),
    re.compile(r"Backlink Operations", re.I),
    re.compile(r"backlink ledger rows", re.I),
)


def main() -> int:
    failures: list[str] = []

    for path in sorted(SITES.rglob("*.html")):
        rel = path.relative_to(ROOT).as_posix()
        segments = {p.lower() for p in path.relative_to(SITES).parts[:-1]}
        hit = segments & FORBIDDEN_SEGMENTS
        if hit:
            failures.append(f"HARD_FAIL {rel}: operator route segment {sorted(hit)} in published tree")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in FORBIDDEN_MARKERS:
            if marker.search(text):
                failures.append(f"HARD_FAIL {rel}: operator-surface marker /{marker.pattern}/ in published tree")
                break

    if failures:
        print("PUBLISHED TREE PURITY: FAIL")
        for line in failures:
            print(f"  {line}")
        return 1

    total = sum(1 for _ in SITES.rglob("*.html"))
    print(f"PUBLISHED TREE PURITY: PASS ({total} published page(s) checked, 0 operator surfaces)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
