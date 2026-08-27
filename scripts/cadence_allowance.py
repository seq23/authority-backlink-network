#!/usr/bin/env python3
"""How many new pages the generator is allowed to publish today.

The repository already declares its publishing rate in data/cadence/policy.json,
and scripts/cadence_gate.js fails the build when that rate is exceeded. Until
now nothing connected the two: the autopilot chose a volume from its own scaling
config and published 9 pages a day against a declared cap of 3 per week - 21x -
and never saw the gate, because git-auto-commit-action pushes with GITHUB_TOKEN
and GitHub does not trigger workflows on those pushes. The cap was real, written
down, and structurally unreachable by the one process that could violate it.

This module is the connection. The generator asks how much room the policy
leaves before it decides what to write, so the cap governs publication rather
than being discovered afterwards by a validator nobody's push ran.

The window is a rolling 7 days over the daily pages themselves, not over the
cadence ledger. The ledger answers "what has been accepted into the baseline",
which resets whenever an acceptance is recorded - measure against that and the
allowance would refill on every accept, permitting the cap per day instead of
per week. The filenames answer "what was actually published recently", which is
what a weekly rate means.

Pages dated ahead of today count. A page scheduled for next Tuesday is already
in the sitemap and already presses on the library the cap exists to protect;
treating it as unpublished until its date arrives would let the whole cap be
sidestepped by writing tomorrow's date into the filename.

Nothing here retires, deletes, or hides a page. It only decides whether to add
one more.
"""
from __future__ import annotations
import json
import re
from datetime import date, timedelta
from pathlib import Path

DATE_PREFIX_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})-')
DEFAULT_WEEKLY_CAP = 3
WINDOW_DAYS = 7


def weekly_cap(root: Path) -> int:
    """The declared cap. Absent policy means the conservative default, never unlimited."""
    f = root / 'data/cadence/policy.json'
    if not f.exists():
        return DEFAULT_WEEKLY_CAP
    try:
        value = json.loads(f.read_text(encoding='utf-8')).get('new_pages_per_week')
        return int(value) if value is not None else DEFAULT_WEEKLY_CAP
    except (ValueError, OSError):
        return DEFAULT_WEEKLY_CAP


def daily_page_dates(root: Path, site_paths: list[str]) -> list[date]:
    out = []
    for site_path in site_paths:
        for page in (root / site_path / 'daily').glob('*.html'):
            match = DATE_PREFIX_RE.match(page.name)
            if not match:
                continue
            try:
                out.append(date.fromisoformat(match.group(1)))
            except ValueError:
                continue
    return out


def published_in_window(root: Path, site_paths: list[str], today: date) -> int:
    """Daily pages dated inside the trailing 7-day window, plus anything dated ahead."""
    floor = today - timedelta(days=WINDOW_DAYS - 1)
    return sum(1 for d in daily_page_dates(root, site_paths) if d >= floor)


def allowance(root: Path, site_paths: list[str], today: date) -> dict:
    cap = weekly_cap(root)
    recent = published_in_window(root, site_paths, today)
    return {
        'weekly_cap': cap,
        'window_days': WINDOW_DAYS,
        'published_in_window': recent,
        'allowance': max(0, cap - recent),
        'window_start': (today - timedelta(days=WINDOW_DAYS - 1)).isoformat(),
        'window_end': today.isoformat(),
    }
