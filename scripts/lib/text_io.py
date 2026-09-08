#!/usr/bin/env python3
"""One way to write generated text with LF endings on every supported runtime.

Why this module exists
----------------------
`docs/V4-6-1-PYTHON-PORTABILITY-FIX.md` records this failure once already:

    pathlib.Path.write_text() was called with the `newline` keyword, which the
    local Python runtime does not support.

`Path.write_text(..., newline=...)` was added in Python 3.10. CI pins 3.11, so
the call works there and fails only on the runtime the updater and the local
validation profile actually run on -- which is why it comes back: nothing in the
pipeline that gates a merge can see it. v4.6.1 fixed two scripts by hand and the
keyword has since reappeared in nine call sites, including a validator, where it
raises

    TypeError: write_text() got an unexpected keyword argument 'newline'

and takes a HARD_FAIL check down with it.

Fixing the call sites again without a shared writer would just restart the same
cycle, so the rule lives here, every generated-text write calls it, and
`scripts/validators/validate_generated_text_writes_are_portable.py` fails the
release if the keyword returns anywhere in the tree.
"""
from __future__ import annotations

from pathlib import Path


def write_lf(path: Path, text: str) -> None:
    """Write `text` to `path` as UTF-8 with LF line endings, no translation.

    The deterministic builds compare bytes between two runs and between two
    machines, so a CRLF translation on a Windows checkout is a real difference,
    not a cosmetic one. `open(..., newline="\\n")` expresses that on 3.9 as well
    as on 3.11; `Path.write_text(..., newline=...)` does not exist before 3.10.
    """
    with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
