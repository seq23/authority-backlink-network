#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / '.github/workflows/authority-post-publish-distribution.yml').read_text(encoding='utf-8')
script = (ROOT / 'scripts/post_publish_distribution.py').read_text(encoding='utf-8')
receipt = json.loads((ROOT / 'data/distribution/provider-receipt.json').read_text(encoding='utf-8'))
feedback = json.loads((ROOT / 'data/distribution/observation-feedback.json').read_text(encoding='utf-8'))
links = json.loads((ROOT / 'data/link-registry.json').read_text(encoding='utf-8'))

required_workflow = [
    'workflow_run:', 'Authority Network V4.2 Autopilot + Social Auto-Post',
    "github.event.workflow_run.conclusion == 'success'",
    'python3 scripts/portfolio_backlink_engine.py repair',
    'python3 scripts/validate.py release',
    'python3 scripts/post_publish_distribution.py',
    'INDEXNOW_KEY', 'GSC_SERVICE_ACCOUNT_JSON', 'DEPLOYMENT_SETTLE_SECONDS', 'GSC_SITE_URLS_JSON',
    'AUTHORITY_PUBLICATION_BASE_URLS_JSON', 'LIVE_BACKLINK_VERIFY',
    'data/distribution/**', 'actions/upload-artifact@v4'
]
for token in required_workflow:
    assert token in workflow, f'missing workflow contract token: {token}'

required_script = [
    'successful_publish', 'sitemap_refresh', 'indexnow', 'gsc_sitemap_submission',
    'priority_url_inspection_where_configured', 'live_backlink_verification',
    'durable_distribution_receipt', 'observation_feedback',
    'INDEXNOW_ENDPOINT', 'GSC_INSPECTION_ENDPOINT', 'DEPLOYMENT_SETTLE_SECONDS', 'GSC_WEBMASTERS_BASE',
    'verified_external_citations_delta', 'truth_boundary'
]
for token in required_script:
    assert token in script, f'missing distribution implementation token: {token}'

assert receipt['schema'] == 'authority-network-post-publish-distribution-v1'
assert receipt['verified_external_citations_delta'] == 0
assert len(receipt['publications']) == 3
assert feedback['portfolio_totals']['verified_external_citations'] == 0
for pub in receipt['publications']:
    assert pub['sitemap_refresh']['status'] == 'SUCCESS'
    assert pub['indexnow']['status'] in {'NOT_CONFIGURED','SUCCESS','FAILED'}
    assert pub['gsc_sitemap_submission']['status'] in {'NOT_CONFIGURED','SUCCESS','FAILED'}

for row in links:
    evidence = row.get('evidence', {})
    assert not (evidence.get('indexed') and not evidence.get('live_verified'))
    assert not (evidence.get('live_verified') and not evidence.get('deployed'))

print(json.dumps({'status':'PASS','chain_steps':len(receipt['chain']),'publications':len(receipt['publications']),'verified_citations':0}))
