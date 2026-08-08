#!/usr/bin/env python3
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = '2026-07-12'
END = '2026-08-07'
EXPECTED_DAYS = 27
EXPECTED_PER_DAY = 9
EXPECTED_TOTAL = EXPECTED_DAYS * EXPECTED_PER_DAY


def read(rel):
    return json.loads((ROOT / rel).read_text(encoding='utf-8'))


# Backfill receipt and canonical state prove the complete 27-day recovery.
receipt = read(f'reports/backfill-authority-v4-{START}_{END}.json')
assert receipt['status'] == 'PASS', receipt
assert receipt['scheduled_days'] == EXPECTED_DAYS, receipt
assert receipt['expected_per_day'] == EXPECTED_PER_DAY, receipt
assert receipt['expected_total'] == EXPECTED_TOTAL, receipt
assert receipt['published_total'] == EXPECTED_TOTAL, receipt
assert receipt['unresolved_days'] == [], receipt

state = read('data/autopilot-state.json')
history = [r for r in state.get('history', []) if START <= r.get('date', '') <= END]
assert len({r['date'] for r in history}) == EXPECTED_DAYS, len(history)
assert sum(int(r.get('published', 0)) for r in history) == EXPECTED_TOTAL
assert all(int(r.get('published', 0)) == EXPECTED_PER_DAY for r in history)
assert all(int(r.get('hard_fails', 0)) == 0 for r in history)
assert sum(int(r.get('self_heal_recoveries', 0)) for r in history) > 0, 'self-heal path was never exercised'

links = read('data/link-registry.json')
if isinstance(links, dict):
    links = links.get('links', [])
catchup = [r for r in links if START <= r.get('scheduled_content_date', '') <= END]
assert len(catchup) == EXPECTED_TOTAL, len(catchup)
assert len({r.get('source_path') for r in catchup}) == EXPECTED_TOTAL
for row in catchup:
    path = ROOT / row['source_path']
    assert path.exists(), row['source_path']
    text = path.read_text(encoding='utf-8', errors='ignore')
    assert row.get('target_url') in text, row['source_path']
    assert '"datePublished": "2026-08-08"' in text, row['source_path']
    assert 'Last updated: 2026-08-08' in text, row['source_path']

# /agency is a read-only owner view generated from canonical repo state.
agency = read('data/agency-dashboard.json')
brands = read('data/brands.json')
publications = read('data/publications.json')
package = read('package.json')
update_contract = read('_repo_update_contract.json')
approved_urls = {link['url'].rstrip('/') for brand in brands for link in brand.get('approved_links', []) if link.get('url')}
agency_approved = {t['target_url'].rstrip('/') for t in agency.get('targets', []) if t.get('registry_status') != 'HISTORICAL_NOT_CURRENTLY_APPROVED'}
assert agency['summary']['approved_target_urls'] == len(approved_urls)
assert agency_approved == approved_urls
assert agency['summary']['backlink_rows'] == len([r for r in links if r.get('target_url')])
assert len(agency.get('publication_operators', [])) == len(publications)
assert {x['id'] for x in agency['publication_operators']} == {x['id'] for x in publications}
assert len(agency.get('runtime_operators', [])) == len(package.get('scripts', {}))
assert {x['operator'] for x in agency['runtime_operators']} == set(package.get('scripts', {}))
assert {x['operator'] for x in agency['release_operators']} == set(update_contract.get('commands', {}))

page = (ROOT / 'sites/founder-operator/agency/index.html').read_text(encoding='utf-8')
assert re.search(r'<meta[^>]+name="robots"[^>]+noindex', page, re.I)
assert 'Canonical publication operators' in page
assert 'Canonical runtime operators' in page
assert 'Canonical release operators' in page
assert 'Canonical workflow operators' in page
for op in package.get('scripts', {}):
    assert f'npm run {op}' in page, op
for url in approved_urls:
    assert url in page, url

# Operator page must not leak into public discovery surfaces.
founder_sitemap = (ROOT / 'sites/founder-operator/sitemap.xml').read_text(encoding='utf-8')
founder_llms = (ROOT / 'sites/founder-operator/llms.txt').read_text(encoding='utf-8')
assert '/agency/' not in founder_sitemap
assert '/agency/' not in founder_llms

print(json.dumps({
    'status': 'PASS',
    'backfill_days': EXPECTED_DAYS,
    'backfill_pages': EXPECTED_TOTAL,
    'self_healed_slots': sum(int(r.get('self_heal_recoveries', 0)) for r in history),
    'approved_target_urls': len(approved_urls),
    'backlink_rows': agency['summary']['backlink_rows'],
    'runtime_operators': agency['summary']['runtime_operators'],
    'release_operators': agency['summary']['release_operators'],
    'publication_operators': agency['summary']['publication_operators'],
}))
