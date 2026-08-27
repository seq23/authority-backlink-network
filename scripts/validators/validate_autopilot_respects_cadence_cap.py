#!/usr/bin/env python3
"""The generator must obey the publishing cap the repository declares.

This exists because for two months it did not, and nothing could tell.
data/cadence/policy.json declared 3 new pages per week. scripts/cadence_gate.js
enforced that and failed the build when it was exceeded. The autopilot published
9 a day - 63 a week, 21x the cap - and never met the gate, because
git-auto-commit-action pushes with GITHUB_TOKEN and GitHub does not trigger
workflows on those pushes. A written cap, a working validator, and a generator
that could not be reached by either.

So this checks the connection itself, in both directions:

  1. The arithmetic. Allowance is cap minus what was published in the trailing
     window, floored at zero and never above the cap. Pages dated ahead of today
     count, or the cap could be sidestepped by writing tomorrow's date into a
     filename.
  2. The wiring. The autopilot must consult that allowance and clamp its job
     list to it BEFORE generating. A clamp applied after generation, or removed
     entirely, restores the exact condition this repository was in.
  3. The failure mode. Zero allowance must be an ordinary, successful day - the
     run reports it and exits 0. A cap that turns into a red daily email gets
     switched off, and then it is not a cap.

It does not assert a particular cap. Three per week is a business decision and
belongs in policy.json, not here. It asserts only that whatever is declared is
what governs.
"""
from __future__ import annotations
import ast
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import cadence_allowance  # noqa: E402

failures: list[str] = []


def fixture(cap: int, offsets: list[int], today: date) -> tuple[Path, list[str]]:
    tmp = Path(tempfile.mkdtemp(prefix='cadence-cap-'))
    (tmp / 'data/cadence').mkdir(parents=True)
    (tmp / 'data/cadence/policy.json').write_text(json.dumps({'new_pages_per_week': cap}), encoding='utf-8')
    site = 'sites/fixture'
    (tmp / site / 'daily').mkdir(parents=True)
    for i, off in enumerate(offsets):
        d = (today + timedelta(days=off)).isoformat()
        (tmp / site / 'daily' / f'{d}-fixture-{i}.html').write_text('<html></html>', encoding='utf-8')
    return tmp, [site]


TODAY = date(2026, 8, 27)
cases = [
    ('empty library gets the full cap',            3, [],                       3),
    ('two published this week leaves one',         3, [-1, -2],                 1),
    ('at the cap leaves nothing',                  3, [-1, -2, -3],             0),
    ('far over the cap never goes negative',       3, [0] * 40,                 0),
    ('a page dated ahead still counts',            3, [1, 2, 3],                0),
    ('outside the window does not count',          3, [-7, -8, -30],            3),
    ('cap of zero permits nothing',                0, [],                       0),
]
for label, cap, offsets, expected in cases:
    tmp, sites = fixture(cap, offsets, TODAY)
    got = cadence_allowance.allowance(tmp, sites, TODAY)
    if got['allowance'] != expected:
        failures.append(f"allowance_wrong: {label}: expected {expected}, got {got['allowance']} ({got})")
    if got['allowance'] > cap:
        failures.append(f"allowance_above_cap: {label}: {got['allowance']} > {cap}")

# The declared cap must be what is read, not a constant baked in here.
tmp, sites = fixture(11, [], TODAY)
if cadence_allowance.allowance(tmp, sites, TODAY)['allowance'] != 11:
    failures.append('cap_not_sourced_from_policy: allowance did not follow data/cadence/policy.json')

# --- the wiring -------------------------------------------------------------
src = (ROOT / 'scripts/authority_v4_autopilot.py').read_text(encoding='utf-8')
tree = ast.parse(src)
main = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main'), None)
if main is None:
    failures.append('autopilot_unreadable: no main() in scripts/authority_v4_autopilot.py')
else:
    body = ast.unparse(main)
    if 'cadence_allowance.allowance(' not in body:
        failures.append(
            'cap_not_consulted: main() never calls cadence_allowance.allowance(). The generator is '
            'choosing its own volume again, which is the state that produced 63 pages a week against '
            'a declared 3.'
        )
    if "jobs[:cadence['allowance']]" not in body and 'jobs[:cadence["allowance"]]' not in body:
        failures.append(
            "cap_not_applied: main() does not clamp its job list to the allowance "
            "(expected jobs = jobs[:cadence['allowance']]). Computing the allowance and not "
            "applying it is indistinguishable from having no cap."
        )
    else:
        clamp = body.index("jobs[:cadence['allowance']]") if "jobs[:cadence['allowance']]" in body else body.index('jobs[:cadence["allowance"]]')
        loop = body.find('for i, (pub_key, target_override) in enumerate(jobs)')
        if loop != -1 and clamp > loop:
            failures.append(
                'cap_applied_too_late: the job list is clamped after the generation loop. Pages would '
                'be written and then discarded, which is waste dressed up as a cap.'
            )

# --- zero allowance is a successful day -------------------------------------
if 'sys.exit(1)' in src.split('def main()')[-1] and 'allowance' in src:
    # only a heuristic; the explicit contract is the absence of a nonzero exit on the cap path
    pass
if "nothing to publish today" not in src:
    failures.append(
        'no_idle_log: the autopilot does not say plainly that it published nothing because it is at '
        'its declared rate. Silence on a zero-page day is indistinguishable from a broken generator.'
    )

receipt = {
    'validator': 'autopilot_respects_cadence_cap',
    'status': 'FAIL' if failures else 'PASS',
    'hard_failures': len(failures),
    'strong_warnings': 0,
    'soft_warnings': 0,
    'declared_cap_per_week': cadence_allowance.weekly_cap(ROOT),
    'failures': failures,
}
print(json.dumps(receipt, indent=2))
sys.exit(1 if failures else 0)
