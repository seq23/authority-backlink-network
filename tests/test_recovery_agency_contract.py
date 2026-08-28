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
# The 27-day catch-up is still 243 rows over 243 distinct pages: nothing was
# retired, and the two assertions above still say so. What changed is that 24 of
# those rows carried an affiliated citation sitting on a page about something
# else - theaccidentguides.com on documentation checklists, hormonesivhair.com on
# equine liability, dentistryguides.com on credit-report errors - and
# scripts/repair_offtopic_affiliate_links.py removed those citations. The rows
# are kept and marked `removed_off_topic` rather than deleted, because the
# backfill really did publish them and erasing that would make this accounting
# lie in the other direction.
#
# So the rendering assertion follows the registry's own status field, the way
# portfolio_backlink_engine.verify_local() already does, and a removed row is
# asserted to be genuinely gone from the page. That is a stronger claim than the
# one it replaces, not a weaker one: before, this loop could only confirm a link
# was present, and had no way to say a link that should not be there is absent.
#
# `withdrawn` joins `removed_off_topic` here for the same reason and under the
# same rule. Those rows are the citations scripts/reduce_commercial_link_-
# concentration.py removed to bring approval-prep from 69% of
# professional-resources' pages back under the declared third: the placement was
# on-topic, the page still exists and still argues what it argued, and only the
# affiliated citation is gone. Both statuses are held to the stronger assertion -
# the URL must be genuinely absent from the page - not excused from the weaker one.
WITHDRAWN = {'removed_off_topic', 'withdrawn'}
removed = [r for r in catchup if r.get('status') in WITHDRAWN]
assert all(r.get('lifecycle_stage') != 'published_in_repository' for r in removed), \
    'a removed row still claims to be rendered in the repository'
for row in catchup:
    path = ROOT / row['source_path']
    assert path.exists(), row['source_path']
    text = path.read_text(encoding='utf-8', errors='ignore')
    if row.get('status') in WITHDRAWN:
        assert row['target_url'] not in text, \
            f"{row['source_path']}: withdrawn citation is still rendered"
    else:
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
# Set equality is the real contract and subsumes the count. Asserting the two
# lengths first only produced a bare AssertionError that named neither side, so
# adding one npm script failed the suite without saying which operator was
# missing.
_runtime_ops = {x['operator'] for x in agency['runtime_operators']}
_npm_scripts = set(package.get('scripts', {}))
assert _runtime_ops == _npm_scripts, (
    f"agency runtime_operators out of sync with package.json scripts; "
    f"missing from dashboard: {sorted(_npm_scripts - _runtime_ops)}; "
    f"stale in dashboard: {sorted(_runtime_ops - _npm_scripts)}")
assert {x['operator'] for x in agency['release_operators']} == set(update_contract.get('commands', {}))

# The operator dashboard was deliberately removed from the published tree, and
# `scripts/validators/validate_published_tree_purity.py` HARD_FAILs if anything
# puts it back: sites/ is publicly fetchable and allows every AI crawler, so a
# noindex meta tag does not keep an operator surface private.
#
# This block used to require that page to exist and to read its contents, which
# made these two checks contradict each other - one demanded the file, the other
# forbade it. The purity validator is the one carrying the security decision, so
# the contract here is inverted: the dashboard must be absent from sites/, and
# the operator model is asserted against the data file instead of scraped out of
# rendered HTML.
agency_page = ROOT / 'sites/founder-operator/agency/index.html'
assert not agency_page.exists(), (
    'operator dashboard is present under sites/; it is publicly fetchable there '
    'and validate_published_tree_purity.py treats it as a HARD_FAIL')
assert not (ROOT / 'sites/founder-operator/agency').exists()

for op in package.get('scripts', {}):
    assert op in _runtime_ops, op
for url in approved_urls:
    assert url in agency_approved, url

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
