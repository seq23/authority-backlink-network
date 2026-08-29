#!/usr/bin/env python3
"""Every tracked script under scripts/ must have a caller.

Why this blocks
---------------
Seven scripts in this repository had no caller at all: three citation
measurement tools and four one-shot backfills. Nothing about the repository
said so. `git grep` on the filename found the docstring that mentions it and
the README paragraph that describes it, so each one read as wired, and the
question "is this still reachable" had to be re-answered by hand every time
anyone looked. Two of them had rotted while unreachable --
measure_internal_reachability.py wrote its result into a temporary directory
belonging to a session that no longer exists, and read its input from an
absolute path outside this checkout, so running it from this repository
measured a different tree and then crashed.

That is the failure this validator exists to stop: not "unused code" as an
aesthetic, but a script that has quietly stopped being run and is therefore no
longer being tested by anything, while still looking live.

What counts as a caller
-----------------------
An invocation or a real import. Specifically:

  invocation   the script's repo-relative path appears in a *runner* -- a
               package.json "scripts" value, a workflow `run:` block, a shell
               script, or a Makefile recipe -- on the same line as an
               interpreter (python/python3/node/npx/bash/sh).

  spawn        the path appears in Python or JS source within two lines of a
               process-spawning token (sys.executable, python, node,
               subprocess, execFileSync, spawn). This is how
               scripts/validate.py registers a validator:
                   "links": [sys.executable, "scripts/link_audit.py"],
               and how scripts/cadence/publish_headroom.mjs reaches
               scripts/cadence/gsc_surfacing.py, where the interpreter and the
               path sit on consecutive lines inside one execFileSync call.

  import       a Python `import`/`from ... import` of the module, or a JS
               `require()`/`import ... from` of the relative path. This is how
               scripts/lib/* and scripts/affiliation.py are reached.

A prose mention is NOT a caller. Markdown, docs/, reports/ and data/ are not in
the reference corpus at all, and inside source files the interpreter token has
to be on the same line, so a docstring sentence like "`scripts/template_share.js`
measured a 45.9% median template share" does not satisfy anything.

This file excludes ITSELF from the reference corpus. Without that, the
paragraph above -- which names scripts by path in order to explain the rule --
would satisfy the rule for every script it mentions, and the validator would
pass by describing itself.

Fails hard if it examines zero scripts. A guard that quietly iterates over an
empty list reports PASS forever and is worse than no guard, because the green
receipt is taken as proof.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SELF = "scripts/validators/validate_script_callers.py"

SCRIPT_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".sh"}

# Reference corpus: things that can actually run or import a script. Markdown
# and generated trees are deliberately absent -- prose is not a caller.
REFERENCE_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".sh", ".yml", ".yaml", ".json"}
REFERENCE_EXCLUDED_DIRS = ("reports/", "data/", "docs/", "sites/", "content-bank/",
                           "content-recipes/", "prompts/")
# Only these JSON files are runners. Every other tracked .json is data.
RUNNER_JSON = {"package.json"}

# Word-bounded on purpose. An unbounded "sh" matches "share" and "shape", which
# would turn half the prose in this repository into evidence of a caller.
INTERPRETER = re.compile(
    r"\b(?:python3?|node|npx|bash|sh|subprocess|execFileSync|execFile|execSync|"
    r"spawnSync|spawn|run)\b|sys\.executable")

# How far from the path an interpreter may sit and still count. execFileSync in
# publish_headroom.mjs puts them on consecutive lines; nothing legitimate in
# this repository needs more room than that.
SPAWN_WINDOW = 2


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True,
                         capture_output=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def reference_corpus(files: list[str]) -> list[tuple[str, str]]:
    docs: list[tuple[str, str]] = []
    for rel in files:
        if rel == SELF:
            continue
        path = Path(rel)
        if path.suffix not in REFERENCE_SUFFIXES and path.name != "Makefile":
            continue
        if path.suffix == ".json" and path.name not in RUNNER_JSON:
            continue
        if rel.startswith(REFERENCE_EXCLUDED_DIRS):
            continue
        try:
            docs.append((rel, (ROOT / rel).read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return docs


def python_module_names(rel: str) -> list[str]:
    """Import spellings that reach this file, given how the repo sets sys.path.

    scripts/ and scripts/lib/ are both pushed onto sys.path by the callers, so
    scripts/lib/page_composer.py is reachable as `lib.page_composer`,
    `page_composer`, or `from lib import page_composer`.
    """
    parts = Path(rel).with_suffix("").parts
    names = [parts[-1]]
    if len(parts) >= 2 and parts[0] == "scripts":
        names.append(".".join(parts[1:]))
    return sorted(set(names))


def has_import(rel: str, docs: list[tuple[str, str]]) -> str | None:
    stem = Path(rel).stem
    if Path(rel).suffix == ".py":
        pats = []
        for name in python_module_names(rel):
            esc = re.escape(name)
            pats.append(rf"^\s*import\s+{esc}\b")
            pats.append(rf"^\s*from\s+{esc}\s+import\b")
            if "." in name:
                pkg, leaf = name.rsplit(".", 1)
                pats.append(rf"^\s*from\s+{re.escape(pkg)}\s+import\s+[^\n]*\b{re.escape(leaf)}\b")
        rx = re.compile("|".join(pats), re.M)
        for src_rel, text in docs:
            if src_rel == rel or Path(src_rel).suffix != ".py":
                continue
            if rx.search(text):
                return f"{src_rel} imports it"
        return None

    if Path(rel).suffix in {".js", ".mjs", ".cjs"}:
        esc = re.escape(stem)
        rx = re.compile(
            rf"(?:require\(|from\s+)['\"][^'\"]*[./]{esc}(?:\.(?:js|mjs|cjs))?['\"]", re.M)
        for src_rel, text in docs:
            if src_rel == rel or Path(src_rel).suffix not in {".js", ".mjs", ".cjs"}:
                continue
            if rx.search(text):
                return f"{src_rel} imports it"
    return None


def has_invocation(rel: str, docs: list[tuple[str, str]]) -> str | None:
    """The path appears near an interpreter or a spawn call.

    A bare mention is not enough. `python3 scripts/x.py` counts; the sentence
    "scripts/x.py measured a 45.9% median template share" does not, because no
    interpreter token sits within the window.
    """
    for src_rel, text in docs:
        if src_rel == rel:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if rel not in line:
                continue
            lo = max(0, i - SPAWN_WINDOW)
            window = "\n".join(lines[lo:i + SPAWN_WINDOW + 1])
            if INTERPRETER.search(window):
                return f"{src_rel}:{i + 1}: {line.strip()[:160]}"
    return None


def main() -> int:
    files = tracked_files()
    scripts = sorted(
        rel for rel in files
        if rel.startswith("scripts/")
        and Path(rel).suffix in SCRIPT_SUFFIXES
        and Path(rel).name != "__init__.py"
    )
    docs = reference_corpus(files)

    failures: list[str] = []

    # A guard that examined nothing must never report PASS.
    if not scripts:
        failures.append(
            "examined 0 tracked scripts under scripts/ -- the corpus query is broken, "
            "not the repository")
    if not docs:
        failures.append("reference corpus is empty -- every script would look orphaned")

    called: dict[str, str] = {}
    for rel in scripts:
        why = has_invocation(rel, docs) or has_import(rel, docs)
        if why:
            called[rel] = why
        else:
            failures.append(
                f"{rel}: no caller. Nothing invokes it from package.json, a workflow, a "
                f"shell script or a Makefile, and no tracked source imports it. Give it a "
                f"named entry point in package.json or delete it.")

    receipt = {
        "validator": "script_callers",
        "status": "FAIL" if failures else "PASS",
        "hard_failures": len(failures),
        "strong_warnings": 0,
        "soft_warnings": 0,
        "scripts_examined": len(scripts),
        "reference_files": len(docs),
        "uncalled": len(scripts) - len(called),
        "failures": failures,
    }
    print(json.dumps(receipt, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
