#!/usr/bin/env python3
"""No generated-text write may use `Path.write_text(..., newline=...)`.

What this stops happening again
-------------------------------
`docs/V4-6-1-PYTHON-PORTABILITY-FIX.md` already records this exact failure:
`pathlib.Path.write_text()` was called with the `newline` keyword, which the
local runtime does not support. That keyword arrived in Python 3.10. The
workflows pin 3.11, so the call succeeds in CI and raises

    TypeError: write_text() got an unexpected keyword argument 'newline'

only where the updater and the local validation profile run. Nothing that gates
a merge could see it, so it came back: v4.6.1 fixed two scripts by hand and the
keyword had reappeared in nine call sites by 2026-09-08, one of them inside
`scripts/validators/validate_nav_rebuild_after_publish.py`, taking a HARD_FAIL
check down with it on any pre-3.10 runtime.

Hand-fixing the call sites a second time would just restart the cycle, so
`scripts/lib/text_io.write_lf()` now owns the rule and this guard fails the
release if the keyword returns anywhere under scripts/, validation/ or tests/.

The check is a source scan rather than a runtime one on purpose: the defect is
invisible at runtime on the version CI runs, which is precisely why it survived.

  zero  a run that scanned no files FAILS. A guard that greps an empty tree
        reports PASS forever.

    python3 scripts/validators/validate_generated_text_writes_are_portable.py
    python3 scripts/validators/validate_generated_text_writes_are_portable.py --root DIR
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCANNED = ("scripts", "validation", "tests")


def offending_calls(text: str) -> list[int]:
    """1-based line numbers of write_text() calls passing `newline=`.

    Parsed rather than grepped: this file and `lib/text_io.py` both NAME the
    banned call in their docstrings, and a guard that cannot tell prose from
    code fails on its own explanation of itself.
    """
    hits = []
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "write_text":
            continue
        if any(kw.arg == "newline" for kw in node.keywords):
            hits.append(node.lineno)
    return sorted(hits)


def scan(root: Path) -> tuple[int, list[str]]:
    failures: list[str] = []
    checked = 0
    for folder in SCANNED:
        for path in sorted((root / folder).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            checked += 1
            text = path.read_text(encoding="utf-8", errors="ignore")
            for line in offending_calls(text):
                failures.append(
                    f"HARD_FAIL {path.relative_to(root).as_posix()}:{line}: "
                    f"write_text(..., newline=...) is Python 3.10+ and raises "
                    f"TypeError on the local runtime. Use "
                    f"lib.text_io.write_lf(path, text), which writes UTF-8 with "
                    f"LF endings on every supported version.")
    return checked, failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT),
                    help="tree to scan; used by the guard's own zero-item proof")
    args = ap.parse_args()
    root = Path(args.root)

    checked, failures = scan(root)

    print("GENERATED TEXT WRITES ARE PORTABLE")
    print(f"  python files scanned: {checked}")

    if checked == 0:
        print("GENERATED TEXT WRITES ARE PORTABLE: FAIL")
        print(f"  HARD_FAIL scanned 0 python files under {root}; this guard must "
              f"not report PASS on an empty walk")
        print(json.dumps({"status": "FAIL", "hard_failures": 1}))
        return 1

    if failures:
        print("GENERATED TEXT WRITES ARE PORTABLE: FAIL")
        for line in failures:
            print(f"  {line}")
        print(json.dumps({"status": "FAIL", "hard_failures": len(failures)}))
        return 1

    print(f"  {checked} files carry no write_text(..., newline=...) call")
    print("GENERATED TEXT WRITES ARE PORTABLE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
