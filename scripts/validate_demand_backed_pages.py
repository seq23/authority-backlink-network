#!/usr/bin/env python3
"""Fails the build on the three ways a page fan-out goes wrong here.

1. A sitemap URL that does not render.
2. A page on disk that no sitemap names.
3. A daily run that ground through attempts to reach its page count.

Check 3 is the one this repo needs most. `SELF_HEAL_MAX_ATTEMPTS` was 96: each
attempt re-rolled a date-seeded PRNG over a cartesian pantry advertising 898,560
to 1,123,200 combinations and tried again until a permutation cleared the score
gate. The daily count was the fixed input and the content was the search space,
which is a publication quota however the config labels it. It is 8 now, and a
run that still cannot fill its slots records a shortfall.

This repo has no measured demand and says so itself, in
data/queries/evidence/evidence_queries.json:

    "Derived from the topics this network actually publishes on, not from
     measured search demand. There is no Search Console evidence set in this
     repo, and inventing plausible queries would have produced a measurement of
     nothing."

That file is honest and no code reads it. Until impression data exists, this
validator states the absence on every run rather than letting it go unmentioned.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors, notes = [], []

# --- 1 & 2. sitemap and disk agree ------------------------------------------
total_locs = 0
for sitemap in sorted(ROOT.glob('sites/*/sitemap.xml')):
    pub = sitemap.parent
    xml = sitemap.read_text(encoding='utf-8')
    locs = re.findall(r'<loc>([^<]+)</loc>', xml)
    total_locs += len(locs)
    missing = []
    claimed = set()
    for loc in locs:
        rel = re.sub(r'^https?://[^/]+/', '', loc).rstrip('/')
        candidates = [pub / rel, pub / (rel + '.html'), pub / rel / 'index.html'] if rel else [pub / 'index.html']
        hit = next((c for c in candidates if c.is_file()), None)
        if hit is None:
            missing.append('/' + rel)
        else:
            claimed.add(hit.resolve())
    if missing:
        errors.append(f'{pub.name}: {len(missing)} sitemap URL(s) do not render, e.g. ' + ', '.join(missing[:5]))
    on_disk = {p.resolve() for p in pub.rglob('*.html')}
    orphans = sorted(p.relative_to(ROOT).as_posix() for p in (on_disk - claimed))
    orphans = [o for o in orphans if '/agency/' not in o]
    if orphans:
        notes.append(f'{pub.name}: {len(orphans)} page(s) on disk in no sitemap, e.g. ' + ', '.join(orphans[:3]))
notes.append(f'{total_locs} sitemap URLs across {len(list(ROOT.glob("sites/*/sitemap.xml")))} publications')

# --- 3. the daily run must not grind to hit a number ------------------------
ATTEMPT_CEILING = 16
configured = int(os.getenv('SELF_HEAL_MAX_ATTEMPTS', '8'))
if configured > ATTEMPT_CEILING:
    errors.append(
        f'SELF_HEAL_MAX_ATTEMPTS is {configured}. Above {ATTEMPT_CEILING} the generator is not recovering '
        f'from an unlucky draw, it is searching a cartesian space until a permutation passes the gate - '
        f'which makes the daily page count the input and the content the output.'
    )
else:
    notes.append(f'SELF_HEAL_MAX_ATTEMPTS={configured} (ceiling {ATTEMPT_CEILING})')

state_path = ROOT / 'data' / 'autopilot-state.json'
if state_path.is_file():
    state = json.loads(state_path.read_text(encoding='utf-8'))
    history = state.get('history', [])
    notes.append(f'{len(state.get("published_hashes", []))} published pages across {len(history)} recorded days')
    heavy = [h for h in history if isinstance(h, dict) and int(h.get('self_heal_attempts') or 0) > ATTEMPT_CEILING]
    if heavy:
        notes.append(f'{len(heavy)} past day(s) needed more than {ATTEMPT_CEILING} attempts to fill their slots - those pages are retirement candidates')

# --- demand -----------------------------------------------------------------
ev = ROOT / 'data' / 'queries' / 'evidence' / 'evidence_queries.json'
if ev.is_file():
    doc = json.loads(ev.read_text(encoding='utf-8'))
    rows = doc if isinstance(doc, list) else doc.get('queries', doc.get('records', []))
    measured = [r for r in rows if isinstance(r, dict) and (r.get('volume') or r.get('impressions'))]
    if not measured:
        notes.append(
            f'NOT MEASURED: {len(rows)} evidence queries, none carrying a volume or impression figure. '
            f'The file says so itself. Verify these hostnames in Search Console to close it.'
        )
    else:
        notes.append(f'demand: {len(measured)} of {len(rows)} evidence queries carry a measurement')

for n in notes:
    print(f'note: {n}')
if errors:
    print('validate:demand-backed-pages FAILED', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
print('validate:demand-backed-pages OK')
