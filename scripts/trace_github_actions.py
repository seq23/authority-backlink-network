#!/usr/bin/env python3
"""Static GitHub Actions data-trace validator for Authority Network.
This does not call GitHub. It verifies workflow wiring, required commands,
required secrets/vars references, concurrency, and no direct Cloudflare deploy.
"""
import json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
WF = ROOT/'.github'/'workflows'
REPORT_DIR = ROOT/'reports'
REPORT_DIR.mkdir(exist_ok=True)
required = {
    'authority-v4-autopilot.yml': {
        'commands': ['python3 scripts/authority_v4_autopilot.py','python3 scripts/validate.py release','python3 scripts/social_publisher.py'],
        'secrets': ['GEMINI_API_KEY','LINKEDIN_ACCESS_TOKEN','LINKEDIN_AUTHOR_URN','X_API_KEY','X_API_SECRET','X_ACCESS_TOKEN','X_ACCESS_TOKEN_SECRET'],
        'vars': ['DAILY_PAGE_LIMIT','ENABLE_LINKEDIN_POSTING','ENABLE_X_POSTING','LINKEDIN_DAILY_LIMIT','X_DAILY_LIMIT'],
        'must_have': ['contents: write','issues: write','actions/cache@v4','stefanzweifel/git-auto-commit-action@v5','dacbd/create-issue-action@v2']
    },
    'social-autopost.yml': {
        'commands': ['python3 scripts/social_publisher.py'],
        'secrets': ['LINKEDIN_ACCESS_TOKEN','LINKEDIN_AUTHOR_URN','X_API_KEY','X_API_SECRET','X_ACCESS_TOKEN','X_ACCESS_TOKEN_SECRET'],
        'vars': ['ENABLE_LINKEDIN_POSTING','ENABLE_X_POSTING','LINKEDIN_DAILY_LIMIT','X_DAILY_LIMIT','SOCIAL_DRY_RUN'],
        'must_have': ['contents: write','issues: write','stefanzweifel/git-auto-commit-action@v5','dacbd/create-issue-action@v2']
    },
    'hostile-review.yml': {
        'commands': ['python3 scripts/validate.py release'],
        'secrets': [],
        'vars': [],
        'must_have': ['actions/cache@v4','actions/upload-artifact@']
    },
    'authority-post-publish-distribution.yml': {
        'commands': ['python3 scripts/portfolio_backlink_engine.py repair','python3 scripts/validate.py release','python3 scripts/post_publish_distribution.py'],
        'secrets': ['GSC_SERVICE_ACCOUNT_JSON'],
        'vars': ['INDEXNOW_KEY','GSC_SITE_URLS_JSON','GSC_INSPECTION_LIMIT','AUTHORITY_PUBLICATION_BASE_URLS_JSON','LIVE_BACKLINK_VERIFY','FAIL_ON_PROVIDER_ERROR','DEPLOYMENT_SETTLE_SECONDS'],
        'must_have': ['contents: write','issues: write','workflow_run:',"github.event.workflow_run.conclusion == 'success'",'actions/cache@v4','actions/upload-artifact@','stefanzweifel/git-auto-commit-action@v5','dacbd/create-issue-action@v2']
    }
}
errors=[]; warnings=[]; traces=[]
for name, contract in required.items():
    path = WF/name
    if not path.exists():
        errors.append(f'missing_workflow:{name}')
        continue
    text = path.read_text(encoding='utf-8')
    trace = {'workflow': name, 'status': 'PASS', 'commands': {}, 'secrets': {}, 'vars': {}, 'guards': {}}
    for cmd in contract['commands']:
        ok = cmd in text
        trace['commands'][cmd] = ok
        if not ok: errors.append(f'{name}:missing_command:{cmd}')
    for sec in contract['secrets']:
        ok = f'secrets.{sec}' in text
        trace['secrets'][sec] = ok
        if not ok: errors.append(f'{name}:missing_secret_reference:{sec}')
    for var in contract['vars']:
        ok = f'vars.{var}' in text
        trace['vars'][var] = ok
        if not ok: warnings.append(f'{name}:missing_var_reference:{var}')
    for token in contract['must_have']:
        ok = token in text
        trace['guards'][token] = ok
        if not ok: errors.append(f'{name}:missing_guard:{token}')
    if name in {'authority-v4-autopilot.yml','social-autopost.yml'}:
        ok = 'concurrency:' in text and 'authority-network-social-${{ github.ref }}' in text and 'cancel-in-progress: false' in text
        trace['guards']['shared_social_concurrency'] = ok
        if not ok: errors.append(f'{name}:missing_shared_social_concurrency')
    forbidden = ['wrangler pages deploy','cloudflare/wrangler-action','CLOUDFLARE_API_TOKEN']
    found_forbidden = [x for x in forbidden if x in text]
    trace['guards']['no_direct_cloudflare_deploy'] = not found_forbidden
    if found_forbidden: errors.append(f'{name}:forbidden_cloudflare_deploy:{found_forbidden}')
    if any(not v for group in ['commands','secrets','guards'] for v in trace[group].values()):
        trace['status']='FAIL'
    traces.append(trace)
report={
    'status':'PASS' if not errors else 'FAIL',
    'scope':'static workflow data trace plus local command-equivalent validation wiring',
    'live_github_actions_execution':'NOT_EXECUTED_IN_ARTIFACT_CONTAINER',
    'errors':errors,
    'warnings':warnings,
    'workflows':traces,
    'notes':[
        'Cloudflare deployment is intentionally not run by GitHub Actions; Cloudflare Git integration handles deploys.',
        'Autopilot and social-only workflows share one concurrency group to prevent simultaneous social posting races.',
        'Secrets are referenced but not validated live until GitHub repository secrets are added.'
    ]
}
(REPORT_DIR/'github-actions-data-trace.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
if errors:
    raise SystemExit(1)
