#!/usr/bin/env python3
"""No order of the page-writing steps can publish a page without its icon/manifest head.

13 Oct 2026: the weekly "USCIS Form and Fee Changelog" run went red at
validate_release. Only favicon_manifest failed: 28 pages (masthead, corrections,
contributors, topic hubs, some daily pages, the changelog page itself) carried
none of the four icon / manifest links. The block was installed by exactly one
script, install_editorial_chrome.py, and that workflow ran
build_site_navigation.py AFTER it, which rewrote those pages with a bare head.
The autopilot was green only because it happened to run navigation first.

Every page writer now installs the block itself (head_seo.install_head_for_path).
This pins it by running, in a scratch copy of the repository:
  1. each workflow's page-writing steps in their REAL order, read from the
     workflow file, then the favicon validator;
  2. every page writer LAST, straight after the chrome pass, then the validator,
     so a writer that stops installing the head fails here even if no workflow
     orders it last today.
Fails on zero workflows or zero writer steps found, and the validator itself
fails on zero pages examined.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lib import analytics_scope, meta_description  # noqa: E402

# Scripts that write whole published pages. A workflow line that runs one of
# these with --write is a page-writing step.
WRITERS = (
    "build_uscis_changelog_page.py",
    "build_editorial_pages.py",
    "build_robots.py",
    "install_editorial_chrome.py",
    "build_site_navigation.py",
)
# Workflows that must be exercised; each must contain at least one writer step.
WORKFLOWS = ("uscis-changelog.yml", "authority-v4-autopilot.yml")
STEP_RE = re.compile(r"python3?\s+scripts/(" + "|".join(map(re.escape, WRITERS)) + r")\s+--write")
COPY_IGNORE = shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".validation-cache")

fails: list[str] = []
scenarios: list[dict] = []


def steps_of(workflow: str) -> list[str]:
    text = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
    return [m.group(1) for m in STEP_RE.finditer(text)]


def run_scenario(name: str, steps: list[str], work: Path) -> None:
    # Fresh published tree for every scenario, so one cannot repair another.
    shutil.rmtree(work / "sites")
    shutil.copytree(ROOT / "sites", work / "sites", ignore=COPY_IGNORE)
    for script in steps:
        r = subprocess.run([sys.executable, f"scripts/{script}", "--write"], cwd=work,
                           capture_output=True, text=True)
        if r.returncode != 0:
            fails.append(f"{name}: {script} --write exited {r.returncode}: "
                         f"{(r.stdout + r.stderr).strip().splitlines()[-1:]}")
            return
    v = subprocess.run([sys.executable, "scripts/validators/validate_favicon_manifest.py"],
                       cwd=work, capture_output=True, text=True)
    bad = [line.strip() for line in v.stdout.splitlines() if "HARD_FAIL" in line]
    scenarios.append({"scenario": name, "steps": steps, "favicon_failures": len(bad)})
    if v.returncode != 0:
        fails.append(f"{name}: after {' -> '.join(steps)} the favicon validator failed "
                     f"({len(bad)} lines; first: {bad[:2]})")
    for validator in ("validate_title_suffix.py", "validate_analytics_separation.py"):
        result = subprocess.run([sys.executable, "scripts/validators/" + validator],
                                cwd=work, capture_output=True, text=True)
        if result.returncode:
            fails.append(f"{name}: {validator}: {result.stdout[-1000:]} {result.stderr[-500:]}")


# Render both sides of the conversion boundary. A footer contact link and
# commented/script examples must not opt an editorial page into recording.
base = '<html><head></head><body>{}</body></html>'
for domain, project in json.loads((ROOT / "data/clarity_projects.json").read_text())["projects"].items():
    for content in ('<form action="/submit"><input name="message"></form>',
                    '<a href="https://shop.gumroad.com/l/guide">Buy</a>',
                    '<a href="/checkout">Checkout</a>'):
        rendered = analytics_scope.install(base.format(content), domain)
        assert f'"{domain}":"{project}"' in rendered
        assert rendered.count('data-clarity-loader') == 1
        assert rendered.count('data-ai-referrer-tag') == 1
        assert analytics_scope.install(rendered, domain) == rendered
        editorial = rendered.replace(content, '<a href="/contact">Contact</a>')
        assert 'clarity.ms' not in analytics_scope.install(editorial, domain)
    for content in ('<!-- <form></form> -->', '<script>const x="<form>";</script>',
                    '<a href="https://gumroad.com.example.invalid/product">Read</a>'):
        assert 'clarity.ms' not in analytics_scope.install(base.format(content), domain)

pubs = json.loads((ROOT / "data/publications.json").read_text())
for pub in pubs:
    title = meta_description.daily_site_title('credit report errors', pub['title'],
                                              pub['folder'] + '/daily/2026-07-17-example.html')
    assert title == f"Credit Report Errors 2026-07-17 | {pub['title']}"
    assert 30 <= len(title) <= 65
    assert meta_description.site_title(title, pub['title'], 'example') == title


with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp) / "repo"
    shutil.copytree(ROOT, work, ignore=COPY_IGNORE)

    for wf in WORKFLOWS:
        steps = steps_of(wf)
        if not steps:
            fails.append(f"{wf}: no page-writing step found -- this check went inert")
            continue
        run_scenario(f"workflow {wf}", steps, work)

    for writer in WRITERS:
        if writer == "install_editorial_chrome.py":
            continue
        run_scenario(f"{writer} last", ["install_editorial_chrome.py", writer], work)

if not scenarios:
    fails.append("zero scenarios ran -- this check went inert")

print(json.dumps({"validator": "page_writers_keep_head", "status": "FAIL" if fails else "PASS",
                  "hard_failures": len(fails), "scenarios": scenarios, "failures": fails}, indent=2))
sys.exit(1 if fails else 0)
