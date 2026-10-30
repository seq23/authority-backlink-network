#!/usr/bin/env python3
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
brands = json.loads((ROOT / 'data/brands.json').read_text(encoding='utf-8'))
manifests = json.loads((ROOT / 'data/product-repo-manifests.json').read_text(encoding='utf-8'))
campaigns = json.loads((ROOT / 'data/portfolio-backlink-campaigns.json').read_text(encoding='utf-8'))['campaigns']
links = json.loads((ROOT / 'data/link-registry.json').read_text(encoding='utf-8'))
health = json.loads((ROOT / 'data/portfolio-campaign-health.json').read_text(encoding='utf-8'))['campaigns']
seed = json.loads((ROOT / 'data/backlink-seed-articles.json').read_text(encoding='utf-8'))['articles']

brand_ids = {b['id'] for b in brands}
required = {
    'the-industry-guides','accident-guides','dentistry-guides','hormones-iv-hair','neuro-eval-guides','uscis-exam-guides',
    'virtual-agency-os','west-peek-productions','bhpc','approval-prep','dream-wedding-builder','porch-party',
    'hicks-consulting','horse-legal-guide','diannes-place','glory-by-us'
}
assert required <= brand_ids, f'missing governed brands: {sorted(required-brand_ids)}'

manifest_rows = manifests.get('repos', manifests.get('manifests', manifests if isinstance(manifests, list) else []))
manifest_ids = {m.get('brand_id') for m in manifest_rows}
assert required <= manifest_ids, f'missing product manifest snapshots: {sorted(required-manifest_ids)}'
for m in manifest_rows:
    if m.get('brand_id') in required:
        assert m.get('source_sha256'), f"{m.get('brand_id')}: source SHA required"
        assert m.get('status') not in {'awaiting_configuration','unknown'}, f"{m.get('brand_id')}: manifest not imported"
        assert m.get('surfaces'), f"{m.get('brand_id')}: no imported surfaces"

campaign_by_id = {c['id']: c for c in campaigns}
assert len(campaign_by_id) == 16
health_by_id = {h['campaign_id']: h for h in health}
assert set(campaign_by_id) == set(health_by_id)
assert all(h['coverage_status'] == 'HEALTHY_RENDERED' for h in health), 'all campaigns must meet rendered gap-closure floors'

published = [r for r in links if r.get('status') == 'published']
for r in published:
    ev = r.get('evidence', {})
    assert not (ev.get('indexed') and not ev.get('live_verified')), 'indexed evidence requires live verification'
    assert r.get('link_type') != 'independent_earned_backlink', 'owned-network link may not be labeled independent'

coverage = defaultdict(list)
for r in published:
    coverage[r.get('campaign_id')].append(r)
for cid, campaign in campaign_by_id.items():
    rows = coverage[cid]
    assert len(rows) >= campaign['minimum_rendered_coverage'], f'{cid}: rendered floor not met'
    assert len({r.get('target_url') for r in rows}) >= campaign['minimum_distinct_destinations'], f'{cid}: destination floor not met'

community = coverage['wpp-community-authority']
assert len(community) >= 5
assert len({r['target_url'] for r in community}) == 1
assert all('westpeekproductions.com' in r['target_url'] for r in community)
assert len(coverage['wpp-commercial']) >= 2
assert all('westpeekproductions.com' in r['target_url'] for r in coverage['wpp-commercial'])

floors = {'dream-planning-tools':6,'dianne-recovery-resources':4,'hicks-workplace-wellbeing':4,'horse-equine-legal':4}
for cid, floor in floors.items():
    assert len(coverage[cid]) >= floor, f'{cid}: immediate gap-closure floor not met'

# glorybyus.com is served like a portfolio site (owner decision, 30 Oct 2026):
# followed links, every destination catalogued, and a cosmetic claim boundary
# that hostile_review.py enforces on every page citing it.
import sys as _sys
_sys.path.insert(0, str(ROOT / 'scripts'))
from affiliation import is_portfolio as _is_portfolio  # noqa: E402
glory = next(b for b in brands if b['id'] == 'glory-by-us')
assert glory['approved_publications'] == ['professional']
assert len(glory.get('prohibited_claim_patterns', [])) >= 5, 'glory-by-us: cosmetic claim boundary missing'
_deep = {t['url'].rstrip('/') for t in json.loads((ROOT / 'data/portfolio-deep-targets.json').read_text(encoding='utf-8'))['targets'].get('glorybyus.com', [])}
for l in glory['approved_links']:
    assert _is_portfolio(l['url']), f"glory-by-us link not followed: {l['url']}"
    assert l['url'].rstrip('/') in _deep, f"glory-by-us link not in deep-target catalogue: {l['url']}"
    assert l.get('topics') and '*' not in l['topics'], f"glory-by-us link without topic scope: {l['url']}"
_pantry = json.loads((ROOT / 'content-bank/yearly-pantry.json').read_text(encoding='utf-8'))['publications']['professional-resources']
_target = next(t for t in _pantry['targets'] if isinstance(t, dict) and t.get('brand_id') == 'glory-by-us')
_hubs = json.loads((ROOT / 'data/topic-taxonomy.json').read_text(encoding='utf-8'))['publications']['professional']['hubs']
_mapped = {c for h in _hubs for c in h['clusters']}
assert len(_target['eligible_clusters']) >= 4
assert set(_target['eligible_clusters']) <= set(_pantry['clusters']) & _mapped, 'glory-by-us cluster not in pantry/taxonomy'
for l in _target['approved_links']:
    assert set(l['topics']) <= set(_target['eligible_clusters']), f"glory-by-us link topic outside its scope: {l['url']}"
_lanes = json.loads((ROOT / 'content-bank/scaling-policy.json').read_text(encoding='utf-8'))['priority_targets']
assert any(r['brand_id'] == 'glory-by-us' and r.get('until_rendered_coverage') for r in _lanes), 'glory-by-us priority lane missing'
# Pages for it publish through the 11 Oct 2026 publishing freeze like every
# other target. Any page that does link it must stay inside the claim boundary.
_claims = [re.compile(p) for p in glory['prohibited_claim_patterns']]
for r in links:
    if r.get('target_domain') == 'glorybyus.com' and r.get('status') == 'published':
        _text = (ROOT / r['source_path']).read_text(encoding='utf-8').lower()
        for _p in _claims:
            assert not _p.search(_text), f"{r['source_path']}: prohibited glory-by-us claim {_p.pattern}"

# The registry stores the anchor as plain text; the page renders it as HTML,
# so "&" is "&amp;" on the page (rebalance_portfolio_links.py and the backlink
# engine both html.escape it). A raw substring test against the HTML fails on
# any anchor with an "&", which is what kept the autopilot red from 28 Oct 2026
# ("Virtual Therapy Serving Memphis & Tennessee"). The check below is stricter
# than the old substring test: one <a> element must carry exactly this href AND
# exactly this anchor text.
ANCHOR_RE = re.compile(r'<a\b([^>]*)>(.*?)</a>', re.I | re.S)
HREF_RE = re.compile(r'\bhref\s*=\s*(["\'])(.*?)\1', re.I | re.S)
TAG_RE = re.compile(r'<[^>]+>')


def rendered_links(text):
    for attrs, inner in ANCHOR_RE.findall(text):
        href = HREF_RE.search(attrs)
        if href:
            yield (html.unescape(href.group(2)),
                   ' '.join(html.unescape(TAG_RE.sub('', inner)).split()))


seed_ids = {x['id'] for x in seed}
seed_rows_checked = 0
for row in published:
    if row.get('seed_article_id'):
        seed_rows_checked += 1
        assert row['seed_article_id'] in seed_ids
        path = ROOT / row['source_path']
        text = path.read_text(encoding='utf-8')
        assert '<link rel="canonical"' in text
        assert '<meta name="description"' in text
        assert 'Affiliation disclosed:' in text
        anchor = ' '.join(row['anchor'].split())
        assert (row['target_url'], anchor) in set(rendered_links(text)), (
            f"{row.get('id')}: {row['source_path']} has no <a href={row['target_url']!r}> "
            f"with anchor text {row['anchor']!r}")
assert seed_rows_checked > 0, 'no seed-article backlinks examined: registry or filter is broken'

print(json.dumps({
    'status':'PASS',
    'brands':len(brands),
    'campaigns':len(campaigns),
    'published_backlinks':len(published),
    'seed_articles':len(seed),
    'seed_rows_checked':seed_rows_checked,
    'community_rendered':len(community),
    'community_destinations':len({r['target_url'] for r in community}),
}))
