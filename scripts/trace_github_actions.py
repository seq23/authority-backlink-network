#!/usr/bin/env python3
"""Static GitHub Actions data-trace validator for Authority Network.
This does not call GitHub. It verifies workflow wiring, required commands,
required secrets/vars references, concurrency, and no direct Cloudflare deploy.
"""
import json, re, subprocess
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
    },
    'journalist-query-scan.yml': {
        'commands': ['python3 scripts/journalist_query_scan.py','python3 scripts/validators/validate_journalist_query_lane.py'],
        'secrets': ['SOS_IMAP_HOST','SOS_IMAP_USER','SOS_IMAP_PASSWORD','OPENROUTER_API_KEY'],
        'vars': ['SOS_IMAP_PORT','SOS_IMAP_FOLDER','JOURNALIST_QUERY_MODEL'],
        'must_have': ['contents: write','issues: write','stefanzweifel/git-auto-commit-action@v5','dacbd/create-issue-action@v2','named_outcome']
    },
    'uscis-changelog.yml': {
        'commands': ['python3 scripts/uscis_changelog.py','python3 scripts/validators/validate_uscis_changelog.py','python3 scripts/validate.py release'],
        'secrets': ['OPENROUTER_API_KEY'],
        'vars': ['USCIS_CHANGELOG_MODEL'],
        'must_have': ['contents: write','issues: write','stefanzweifel/git-auto-commit-action@v5','dacbd/create-issue-action@v2','named_outcome']
    }
}

# The two lanes that both auto-commit to main. Their plumbing, not their logic,
# is what turned them red on 2026-09-02, twice and in two different ways -- so
# the plumbing is what is guarded here.
CITATION_LANES = ['journalist-query-scan.yml','uscis-changelog.yml']
CITATION_CONCURRENCY = 'authority-network-citation-lanes-${{ github.ref }}'
FILE_PATTERN_RE = re.compile(r'file_pattern:\s*"([^"]*)"')


def tracked(pathspec: str) -> bool:
    """Does git already track at least one file under this pathspec?

    git-auto-commit-action runs `git add <file_pattern>` and git exits 128 on a
    pathspec that matches NOTHING. The journalist lane's pattern named
    `data/journalist-queries/digests/**`, a directory that is empty on a quiet
    day because git does not track empty directories -- so the designed, correct,
    most common outcome of that lane turned the workflow red. A pattern must
    therefore name paths that ALWAYS exist, not the files a productive day
    happens to produce.
    """
    base = pathspec.split('*')[0].rstrip('/')
    if not base:
        return False
    proc = subprocess.run(['git','ls-files','--',base],
                          cwd=ROOT, text=True, capture_output=True)
    return proc.returncode == 0 and bool(proc.stdout.strip())
errors=[]; warnings=[]; traces=[]; checked_patterns=[]
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
    if name in CITATION_LANES:
        # Root cause of the USCIS red run on 2026-09-02: both lanes commit to
        # main, git-auto-commit-action does not rebase, and dispatching them
        # together produced a non-fast-forward push on a lane whose own work had
        # succeeded. One shared group makes them queue instead of colliding.
        ok = ('concurrency:' in text and CITATION_CONCURRENCY in text
              and 'cancel-in-progress: false' in text)
        trace['guards']['shared_citation_concurrency'] = ok
        if not ok:
            errors.append(f'{name}:missing_shared_citation_concurrency')

        # Root cause of the journalist-query red run on the same day: a commit
        # pathspec that matches nothing makes git exit 128, and it matched
        # nothing precisely because the lane had correctly found nothing.
        patterns = FILE_PATTERN_RE.findall(text)
        if not patterns:
            errors.append(f'{name}:no_file_pattern_to_check')
        for pattern in patterns:
            for spec in pattern.split():
                checked_patterns.append(f'{name}:{spec}')
                ok = tracked(spec)
                trace['guards'][f'commit_pathspec_always_exists:{spec}'] = ok
                if not ok:
                    errors.append(
                        f'{name}:commit_pathspec_can_match_nothing:{spec} -- '
                        f'git-auto-commit-action exits 128 on a pathspec that matches '
                        f'no tracked file, so a run that correctly produced nothing '
                        f'would go red')

        # A legitimate stop must be green because the lane reached one and said
        # so, never because a failure was swallowed on the way out.
        for cheat in ['continue-on-error', '|| true', 'exit 0 #']:
            if cheat in text:
                trace['guards'][f'no_green_by_suppression:{cheat}'] = False
                errors.append(
                    f'{name}:green_by_suppression:{cheat} -- a named stop must exit 0 '
                    f'on purpose; a suppressed failure is indistinguishable from a '
                    f'lane that has quietly died')

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
# Rule 0: this validator may not exit 0 having examined nothing. If the citation
# lanes stop being found, or their commit patterns stop being read, the guard has
# gone blind and must say so rather than pass on an empty loop.
if not checked_patterns:
    errors.append('citation_lane_commit_patterns:examined_zero -- the guard on the '
                  'pathspec that turned this lane red found nothing to examine, which '
                  'is a blind guard, not a passing one')

report={
    'status':'PASS' if not errors else 'FAIL',
    'scope':'static workflow data trace plus local command-equivalent validation wiring',
    'live_github_actions_execution':'NOT_EXECUTED_IN_ARTIFACT_CONTAINER',
    'errors':errors,
    'warnings':warnings,
    'workflows':traces,
    'citation_lane_commit_patterns_checked':checked_patterns,
    'notes':[
        'Cloudflare deployment is intentionally not run by GitHub Actions; Cloudflare Git integration handles deploys.',
        'Autopilot and social-only workflows share one concurrency group to prevent simultaneous social posting races.',
        'Secrets are referenced but not validated live until GitHub repository secrets are added.',
        'The two citation lanes (journalist query scan, USCIS changelog) share one concurrency group because both auto-commit to main and git-auto-commit-action does not rebase.',
        'Every commit pathspec on those lanes is checked against git ls-files: a pattern that can match nothing makes git exit 128, which is how a correct no-op run went red.'
    ]
}
(REPORT_DIR/'github-actions-data-trace.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
if errors:
    raise SystemExit(1)
