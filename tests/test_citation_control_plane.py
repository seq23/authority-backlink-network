#!/usr/bin/env python3
import importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
brands=json.loads((ROOT/'data/brands.json').read_text())
profiles=json.loads((ROOT/'data/brand-growth-profiles.json').read_text())['profiles']
assert {b['id'] for b in brands} == {p['brand_id'] for p in profiles}, 'every brand requires exactly one growth profile'
assert all(p.get('targets_are_nonblocking') is True for p in profiles)
links=json.loads((ROOT/'data/link-registry.json').read_text())
for row in links:
    ev=row.get('evidence',{})
    assert not (ev.get('indexed') and not ev.get('live_verified')), 'indexed evidence requires live verification'
policy=json.loads((ROOT/'content-bank/scaling-policy.json').read_text())
assert policy['portfolio_citation_objective']['target']==100000
assert policy['portfolio_citation_objective']['never_equate_generated_with_indexed_or_cited'] is True
spec=importlib.util.spec_from_file_location('autopilot',ROOT/'scripts/authority_v4_autopilot.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
counts={p['brand_id']:p.get('current_published_backlinks_at_v46_baseline',0) for p in profiles}
for pub in mod.PANTRY['publications']:
    target=mod.choose_fair_target(pub,0,counts)
    if target is not None:
        assert target['brand_id'] in {t['brand_id'] for t in mod.PANTRY['publications'][pub]['targets'] if isinstance(t,dict)}
print(json.dumps({'status':'PASS','brands':len(brands),'objective':100000,'scheduler_publications':len(mod.PANTRY['publications'])}))
