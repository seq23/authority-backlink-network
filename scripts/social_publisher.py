#!/usr/bin/env python3
"""
Authority Network social publisher.
Posts approved/auto-queued social items to one LinkedIn account and one X account.

Safety model:
- Only posts items with status queued_for_auto_post or approved_for_auto_post.
- Enforces daily platform limits.
- Enforces duplicate/similar same-day body suppression.
- Uses official APIs only.
- Supports SOCIAL_DRY_RUN=true for validation without network calls.
"""
import base64, copy, hashlib, hmac, json, os, random, re, sys, time, urllib.parse, urllib.request, urllib.error
from collections import defaultdict
from pathlib import Path
from datetime import date, datetime, timezone

from lib import social_platforms

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = Path(os.getenv('SOCIAL_QUEUE_PATH', str(ROOT / 'data/social-queue.json')))
REPORT_PATH = Path(os.getenv('SOCIAL_REPORT_PATH', str(ROOT / 'reports/social-publisher-report.json')))
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
TODAY = date.today().isoformat()
TODAY_ORDINAL = date.today().toordinal()

POSTED_STATUSES = {'posted', 'skipped_duplicate', 'failed_permanent'}
# Anything outside POSTABLE_STATUSES is never posted. That deliberately includes
# 'not_for_posting', which scripts/prioritize_social_queue.py writes onto entries
# retired as duplicates, together with the reason it retired them.
POSTABLE_STATUSES = {'queued_for_auto_post', 'approved_for_auto_post'}

# How many times one entry may be attempted before it is retired for good. Stops
# a genuinely unpostable item cycling forever, while letting an outage pass.
MAX_POST_ATTEMPTS = int(os.getenv('MAX_POST_ATTEMPTS', '5'))

# Errors a retry cannot change, because the item itself is the problem. Anything
# not on this list is treated as transient and the entry is deferred, because
# the expensive mistake here is dropping a page from distribution for good on
# the strength of one bad afternoon at the API.
PERMANENT_ERROR_MARKERS = ('empty_body', 'unsupported_platform')

# Responses that mean "stop talking to this platform", not "try the next item".
# 429 is the platform saying it has had enough; 402 is the account having no
# write credits left; 401/403 mean the credentials will not work for any item.
# In every case the next request cannot succeed and can only make things worse.
HALT_STATUS_REASONS = {
    '429': 'rate_limited_by_platform',
    '402': 'payment_required_credits_depleted',
    '401': 'credentials_rejected',
    '403': 'credentials_forbidden',
}


def recoverable_legacy_failure(item):
    """True for an entry retired by the attempt-budget defect of 2026-08-29.

    `post_failed` is a status this module no longer writes: an attempt that
    fails now either defers the entry or, if the entry itself is unpostable,
    retires it as `failed_permanent`. So a row still carrying `post_failed`
    came from the run that stamped 581 of them in one pass, after X answered
    402 then 429 to a loop that made one request per queue entry because its
    caps counted successes instead of attempts.

    Those entries were never faulty - the platform refused the account, not the
    post - and `post_failed` is in no postable set, so leaving them stamped
    means 581 published pages are silently never distributed. They are restored
    on sight. Only infrastructure refusals qualify; a content-level failure is
    left alone, because a retry cannot change it.
    """
    if item.get('status') != 'post_failed':
        return False
    return halt_reason(item.get('last_error')) is not None


def normalize_legacy_failures(queue):
    """Return entries stamped by that defect to the postable pool."""
    restored = 0
    for item in queue:
        if not recoverable_legacy_failure(item):
            continue
        item['status'] = 'queued_for_auto_post'
        item['attempt_count'] = int(item.get('attempt_count') or 0) or 1
        item['requeued_reason'] = (
            'restored_after_attempt_budget_defect: retired by a run whose per-run and '
            'daily caps counted successes rather than attempts, so a platform-level '
            'refusal was recorded against every entry instead of stopping the run. '
            'The entry itself was never at fault.'
        )
        restored += 1
    return restored


def is_permanent_error(error):
    text = str(error or '')
    return any(marker in text for marker in PERMANENT_ERROR_MARKERS)


def halt_reason(error):
    """Return a halt reason if this error means the whole platform should stop."""
    m = re.match(r'\s*HTTP (\d{3})', str(error or ''))
    if not m:
        return None
    code = m.group(1)
    if code in HALT_STATUS_REASONS:
        return f'{HALT_STATUS_REASONS[code]} (HTTP {code})'
    if code.startswith('5'):
        return f'platform_server_error (HTTP {code})'
    return None


def read_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding='utf-8'))


def write_json(path, data):
    from lib.authority_core import atomic_write_json
    atomic_write_json(Path(path), data)


def truthy(name, default='false'):
    return str(os.getenv(name, default)).strip().lower() in {'1','true','yes','y','on'}


def normalize(text):
    text = re.sub(r'https?://\S+', '', text or '')
    text = re.sub(r'[^a-z0-9 ]+', ' ', text.lower())
    return re.sub(r'\s+', ' ', text).strip()


def jaccard_text(a, b):
    wa = set(re.findall(r'[a-z]{4,}', normalize(a)))
    wb = set(re.findall(r'[a-z]{4,}', normalize(b)))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def append_url(body, item):
    url = item.get('source_url') or item.get('target_url') or ''
    if url and url not in body:
        return (body.rstrip() + '\n\n' + url).strip()
    return body.strip()


def trim_x(text):
    # conservative trim for plain text posts. URL length is platform-normalized, but keep simple.
    if len(text) <= 275:
        return text
    return text[:272].rstrip() + '…'


def validate_required_secrets(platform):
    if platform == 'linkedin':
        missing = [k for k in ['LINKEDIN_ACCESS_TOKEN', 'LINKEDIN_AUTHOR_URN'] if not os.getenv(k)]
    elif platform == 'x':
        # Two auth paths. OAuth 2.0 user-context is preferred when a bearer token is
        # present: it is what the X developer console now hands out, and it is a
        # single token rather than a signed pair. OAuth 1.0a stays supported so an
        # existing 1.0a setup keeps working unchanged.
        if x_oauth1a_complete() or os.getenv('X_OAUTH2_ACCESS_TOKEN'):
            missing = []
        else:
            missing = [k for k in ['X_API_KEY', 'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_TOKEN_SECRET'] if not os.getenv(k)]
    else:
        missing = []
    return missing


def linkedin_post(text):
    token = os.getenv('LINKEDIN_ACCESS_TOKEN')
    author = os.getenv('LINKEDIN_AUTHOR_URN')
    version = os.getenv('LINKEDIN_VERSION', '202606')
    payload = {
        'author': author,
        'commentary': text,
        'visibility': 'PUBLIC',
        'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [], 'thirdPartyDistributionChannels': []},
        'lifecycleState': 'PUBLISHED',
        'isReshareDisabledByAuthor': False
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        'https://api.linkedin.com/rest/posts',
        data=data,
        method='POST',
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Linkedin-Version': version,
            'X-Restli-Protocol-Version': '2.0.0'
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode('utf-8', errors='replace')
        post_id = resp.headers.get('x-restli-id') or ''
        return {'ok': True, 'status': resp.status, 'id': post_id, 'body': body}


def oauth_percent(value):
    return urllib.parse.quote(str(value), safe='')


def x_oauth_header(method, url, body_params=None):
    api_key = os.getenv('X_API_KEY')
    api_secret = os.getenv('X_API_SECRET')
    access_token = os.getenv('X_ACCESS_TOKEN')
    access_secret = os.getenv('X_ACCESS_TOKEN_SECRET')
    oauth = {
        'oauth_consumer_key': api_key,
        'oauth_nonce': hashlib.sha256(f'{time.time()}-{os.getpid()}'.encode()).hexdigest()[:32],
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_timestamp': str(int(time.time())),
        'oauth_token': access_token,
        'oauth_version': '1.0'
    }
    parsed = urllib.parse.urlparse(url)
    query_params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    sig_params = {**query_params, **oauth}
    # JSON body params are not included in OAuth 1.0a signature base string for application/json requests.
    param_str = '&'.join(f'{oauth_percent(k)}={oauth_percent(v)}' for k, v in sorted(sig_params.items()))
    base_url = f'{parsed.scheme}://{parsed.netloc}{parsed.path}'
    base = '&'.join([method.upper(), oauth_percent(base_url), oauth_percent(param_str)])
    signing_key = f'{oauth_percent(api_secret)}&{oauth_percent(access_secret)}'
    signature = base64.b64encode(hmac.new(signing_key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    oauth['oauth_signature'] = signature
    return 'OAuth ' + ', '.join(f'{oauth_percent(k)}="{oauth_percent(v)}"' for k, v in oauth.items())


def x_refresh_access_token():
    """Exchange the refresh token for a new access token.

    X's OAuth 2.0 access tokens are short-lived (about two hours), so a scheduled
    lane that only ever reads the stored token works once and then 401s forever.
    Refresh needs the OAuth 2.0 CLIENT ID - a different value from the OAuth 1.0a
    consumer key - so when it is absent this returns None and the caller falls
    back to the stored token rather than pretending to have refreshed.
    """
    refresh = os.getenv('X_OAUTH2_REFRESH_TOKEN')
    client_id = os.getenv('X_OAUTH2_CLIENT_ID')
    if not refresh or not client_id:
        return None
    body = urllib.parse.urlencode({
        'grant_type': 'refresh_token',
        'refresh_token': refresh,
        'client_id': client_id,
    }).encode('utf-8')
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    secret = os.getenv('X_OAUTH2_CLIENT_SECRET')
    if secret:
        basic = base64.b64encode(f'{client_id}:{secret}'.encode()).decode()
        headers['Authorization'] = f'Basic {basic}'
    req = urllib.request.Request('https://api.x.com/2/oauth2/token', data=body, method='POST', headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read().decode('utf-8', errors='replace'))
        return out.get('access_token') or None
    except Exception:
        # A failed refresh is not fatal here: the stored token may still be valid.
        return None


def x_send(text, bearer=None):
    url = 'https://api.x.com/2/tweets'
    data = json.dumps({'text': text}).encode('utf-8')
    auth = f'Bearer {bearer}' if bearer else x_oauth_header('POST', url)
    req = urllib.request.Request(
        url,
        data=data,
        method='POST',
        headers={'Authorization': auth, 'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode('utf-8', errors='replace')
        out = json.loads(body) if body.strip().startswith('{') else {'raw': body}
        return {'ok': True, 'status': resp.status, 'id': out.get('data', {}).get('id', ''), 'body': out}


def x_oauth1a_complete():
    return all(os.getenv(k) for k in ('X_API_KEY', 'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_TOKEN_SECRET'))


def x_post(text):
    # OAuth 1.0a wins when a complete set is present, even though OAuth 2.0 is the
    # newer path. Measured on this account: refreshing an OAuth 2.0 token returns a
    # NEW refresh token and invalidates the one that was sent. A scheduled lane
    # cannot write that rotated value back - GITHUB_TOKEN cannot update repository
    # secrets - so the OAuth 2.0 path survives exactly one refresh and then 401s
    # forever, with no signal until it does.
    #
    # OAuth 1.0a access tokens do not expire and need no refresh, which is what a
    # cron-driven publisher actually wants. OAuth 2.0 stays supported for a setup
    # that only has bearer credentials.
    if x_oauth1a_complete():
        return x_send(text)
    bearer = os.getenv('X_OAUTH2_ACCESS_TOKEN')
    if not bearer:
        return x_send(text)
    try:
        return x_send(text, bearer)
    except urllib.error.HTTPError as err:
        # 401 is the expected shape of an expired bearer. Refresh once, then retry;
        # anything else, or a refresh that cannot run, propagates unchanged.
        if err.code != 401:
            raise
        refreshed = x_refresh_access_token()
        if not refreshed:
            raise
        return x_send(text, refreshed)


def post_item(item, dry_run=False):
    platform = item.get('platform')
    text = append_url(item.get('body', ''), item)
    if platform == 'x':
        text = trim_x(text)
    if not text:
        return {'ok': False, 'error': 'empty_body'}
    if dry_run:
        
        dry_key = f"{platform}|{item.get('brand','')}|{item.get('post_type','')}|{item.get('source_path','')}|{text}"
        return {'ok': True, 'dry_run': True, 'id': f"dry-{hashlib.sha1(dry_key.encode()).hexdigest()[:12]}", 'text': text}
    if platform == 'linkedin':
        return linkedin_post(text)
    if platform == 'x':
        return x_post(text)
    return {'ok': False, 'error': f'unsupported_platform:{platform}'}


def named_stops_for(platform_states, paused, secret_skips):
    """A named reason for every platform that did nothing this run.

    "Did nothing" must never be left to be inferred. The three cases read
    differently on purpose: a paused switch is a decision, an uncredentialled
    switch is a to-do, and an undocumented switch-off is a bug that
    scripts/validators/validate_social_rate_limits.py also fails the build on.
    """
    stops = {}
    for platform, state in platform_states.items():
        if state == social_platforms.STATE_ON:
            continue
        if state == social_platforms.STATE_PAUSED:
            stops[platform] = (
                f"{platform}_paused_by_switch: {(paused.get(platform) or {}).get('paused_reason')} "
                f"Turn it back on by setting platforms.{platform}.enabled to true in "
                f"data/social-brand-policy.json."
            )
        elif state == social_platforms.STATE_UNCREDENTIALLED:
            missing = secret_skips.get(platform) or []
            stops[platform] = (
                f"{platform}_on_but_uncredentialled: the switch for {platform} is ON in "
                f"data/social-brand-policy.json, but {', '.join(missing) or 'its credentials'} "
                f"{'is' if len(missing) == 1 else 'are'} absent from repository secrets, so "
                f"nothing was posted to {platform}. This is a to-do, not a failure; any other "
                f"enabled platform posted normally."
            )
        else:
            stops[platform] = (
                f"{platform}_off_without_a_recorded_decision: the switch for {platform} is off "
                f"but carries no paused_on/paused_by/paused_reason record, so nothing here can "
                f"tell a decision from a breakage."
            )
    return stops


def restore_deferred_mode():
    """Apply the legacy-failure normalization to the queue and exit. Posts nothing.

    The publisher does this at the start of any ordinary run too, so this mode
    exists only to bring the committed queue back in one step rather than
    waiting for the next scheduled lane. It opens no network connection.
    """
    queue = read_json(QUEUE_PATH, [])
    if isinstance(queue, dict):
        queue = queue.get('items', [])
    restored = normalize_legacy_failures(queue)
    if restored:
        write_json(QUEUE_PATH, queue)
    postable = sum(1 for i in queue if i.get('status') in POSTABLE_STATUSES)
    print(json.dumps({
        'mode': 'restore-deferred',
        'posted': 0,
        'entries': len(queue),
        'restored': restored,
        'postable_after': postable,
    }, indent=2))


def main():
    if '--restore-deferred' in sys.argv:
        restore_deferred_mode()
        return
    original_queue = read_json(QUEUE_PATH, [])
    queue = original_queue
    if isinstance(queue, dict):
        queue = queue.get('items', [])
    # Dry-run validation must never mutate the publish queue. Live mode mutates statuses after real API attempts.
    if truthy('SOCIAL_DRY_RUN', 'false') or truthy('MOCK_SOCIAL_POSTING', 'false'):
        queue = copy.deepcopy(queue)
    # Enablement is declared in data/social-brand-policy.json and overridden per
    # run by ENABLE_<PLATFORM>_POSTING. The literal 'true' defaults that used to
    # live here (and in both workflows) were a third opinion about a question the
    # declaration now answers once. See scripts/lib/social_platforms.py.
    platform_policy = social_platforms.load_policy()
    enable_li = social_platforms.is_enabled('linkedin', platform_policy)
    enable_x = social_platforms.is_enabled('x', platform_policy)
    paused = social_platforms.paused_platforms(platform_policy)
    dry_run = truthy('SOCIAL_DRY_RUN', 'false') or truthy('MOCK_SOCIAL_POSTING', 'false')
    require_secrets = truthy('REQUIRE_SOCIAL_SECRETS', 'true')
    li_limit = int(os.getenv('LINKEDIN_DAILY_LIMIT', '3'))
    x_limit = int(os.getenv('X_DAILY_LIMIT', '8'))
    max_sim = float(os.getenv('MAX_SOCIAL_SIMILARITY', '0.86'))
    # Per-run cap and in-run spacing exist for one reason: a daily cap alone is
    # not account-safe. Eight posts emitted inside one loop land within seconds
    # of each other on the same timestamp, which reads as a bot to X's spam
    # heuristics no matter how modest the daily total is. The workflow runs on
    # several irregular crons; each run takes a small slice and paces the posts
    # inside it, so the same daily volume arrives as scattered activity.
    run_limit = int(os.getenv('SOCIAL_RUN_LIMIT', '3'))
    min_interval = int(os.getenv('SOCIAL_POST_MIN_INTERVAL_SECONDS', '90'))
    posted_this_run = {'linkedin': 0, 'x': 0}
    # Count already-posted items for TODAY so multiple workflows cannot exceed
    # the daily cap when both autopilot and social-only schedules run.
    posted_today = {'linkedin': 0, 'x': 0}
    attempts, successes, failures, skipped = [], [], [], []

    # Rule 0: a run with nothing switched on must stop with a NAMED reason, not
    # fall through the loop and exit 0 having done nothing.
    if not enable_li and not enable_x:
        off_states = {p: social_platforms.platform_state(p, None, platform_policy)
                      for p in social_platforms.PLATFORMS}
        report = {
            'date': TODAY, 'dry_run': dry_run,
            'enabled': {'linkedin': enable_li, 'x': enable_x},
            'platform_states': off_states,
            'named_stops': named_stops_for(off_states, paused, {}),
            'paused_platforms': paused,
            'secret_skips': {},
            'limits': {'linkedin': li_limit, 'x': x_limit},
            'attempts': [], 'successes': [], 'failures': [], 'skipped': [],
            'posted_today': {'linkedin': 0, 'x': 0},
            'pacing': {'run_limit': run_limit, 'min_interval_seconds': min_interval},
            'status': 'stopped_no_enabled_platform',
            'production_blocked': False,
            'stop_reason': (
                'Every social platform switch is off in data/social-brand-policy.json, '
                'so there is nowhere to post. '
                + ('Recorded decisions: '
                   + '; '.join(f"{k}: {v.get('paused_reason')}" for k, v in paused.items())
                   if paused else
                   'No platform carries a paused_on/paused_by/paused_reason record, so this '
                   'is an undocumented switch-off rather than a decision.')
            ),
        }
        write_json(REPORT_PATH, report)
        print(json.dumps(report, indent=2))
        return

    platform_secret_skips = {}
    if enable_li and not dry_run:
        missing = validate_required_secrets('linkedin')
        if missing:
            platform_secret_skips['linkedin'] = missing
            enable_li = False
    if enable_x and not dry_run:
        missing = validate_required_secrets('x')
        if missing:
            platform_secret_skips['x'] = missing
            enable_x = False

    # The three distinguishable states, computed from the switch and the
    # credential check together. "Paused by choice", "switched on but with no
    # credentials", and "switched on and posting" are different situations with
    # different remedies, and a reader of the ledger must be able to tell which
    # one they are looking at without going to look at the secrets.
    platform_states = {
        p: social_platforms.platform_state(p, platform_secret_skips.get(p), platform_policy)
        for p in social_platforms.PLATFORMS
    }
    # Entries that cannot post right now ONLY because their platform's switch is
    # off. Derived, never stamped onto the rows: flipping the switch back on
    # restores every one of them with no queue edit. See scripts/lib/social_platforms.py.
    _, parked_by_switch = social_platforms.partition_queue(queue, platform_policy)
    parked_by_platform_switch = {k: len(v) for k, v in parked_by_switch.items()}

    # A missing credential set retires ONE platform, not the run. This used to
    # read `if platform_secret_skips and ...`, so the absent LinkedIn token
    # returned before a single X post was attempted: the queue's real drain rate
    # was 0/day on both platforms, not 5/day on X, and every scheduled run
    # exited green with `status: ok_with_secret_warning` saying so in a field
    # nobody reads. Raising X_DAILY_LIMIT would have changed nothing. Bail only
    # when no platform is left to post to -- that is the genuinely empty run.
    no_platform_left = not enable_li and not enable_x
    if platform_secret_skips and no_platform_left and require_secrets and not dry_run:
        strict_failure = truthy('FAIL_ON_SOCIAL_POST_FAILURE', 'false')
        report = {
            'date': TODAY, 'dry_run': False,
            'enabled': {'linkedin': enable_li, 'x': enable_x},
            'platform_states': platform_states,
            'named_stops': named_stops_for(platform_states, paused, platform_secret_skips),
            'paused_platforms': paused,
            'parked_by_platform_switch': parked_by_platform_switch,
            'secret_skips': platform_secret_skips,
            'limits': {'linkedin': li_limit, 'x': x_limit},
            'attempts': [], 'successes': [], 'failures': [], 'skipped': [],
            'posted_today': {'linkedin': 0, 'x': 0},
            'status': 'blocked_missing_secrets' if strict_failure else 'ok_with_secret_warning',
            'production_blocked': bool(strict_failure),
            'message': 'Social credentials are unavailable. Social posting was skipped; content publication remains allowed.'
        }
        write_json(REPORT_PATH, report)
        print(json.dumps(report, indent=2))
        if strict_failure:
            raise SystemExit('Required social secrets are missing and strict social failure is enabled')
        return

    bodies_today_by_platform = defaultdict(list)
    posted_by_brand_platform = defaultdict(int)
    seen_order = {}
    for i, existing in enumerate(queue):
        brand = existing.get('brand') or existing.get('domain') or 'unknown'
        seen_order.setdefault(brand, len(seen_order))
        platform = existing.get('platform')
        if existing.get('status') == 'posted':
            posted_by_brand_platform[(platform, brand)] += 1
        if existing.get('posted_at','').startswith(TODAY):
            if platform in posted_today:
                posted_today[platform] += 1
            bodies_today_by_platform[platform].append(existing.get('body',''))

    restored_legacy_failures = normalize_legacy_failures(queue)

    # Budget spent TODAY is measured in attempts, not posts. posted_today above
    # counts what landed; this counts what was sent. They differ exactly when
    # things are going wrong, which is when the cap has to hold.
    spent_today = {'linkedin': 0, 'x': 0}
    for existing in queue:
        plat = existing.get('platform')
        if plat in spent_today and str(existing.get('last_attempt_at', '')).startswith(TODAY):
            spent_today[plat] += 1
    for plat in spent_today:
        # A row posted today always carries last_attempt_at too, but a queue
        # written by an older revision may not. Never let the budget read lower
        # than the number of posts already known to have gone out.
        spent_today[plat] = max(spent_today[plat], posted_today[plat])
    attempted_this_run = {'linkedin': 0, 'x': 0}
    halted_platforms = {}

    def record_failure(item, idx, platform, error):
        """A failed attempt defers the item; it does not retire it.

        Marking a transient failure terminal is how 581 queued X entries became
        581 dead ones in a single run on 2026-08-29: X answered 402 then 429,
        every entry was stamped post_failed, and post_failed is in no postable
        set, so the queue went to zero eligible items with nothing reporting a
        loss. A cap that defers is fine; a failure that drops is not.
        """
        item['last_error'] = error
        attempts_used = int(item.get('attempt_count') or 0)
        if is_permanent_error(error):
            item['status'] = 'failed_permanent'
            disposition = 'failed_permanent'
        elif attempts_used >= MAX_POST_ATTEMPTS:
            item['status'] = 'failed_permanent'
            disposition = 'failed_permanent_attempts_exhausted'
        else:
            # Back to the postable pool for a later run.
            item['status'] = 'queued_for_auto_post'
            disposition = 'deferred_for_retry'
        failures.append({'index': idx, 'platform': platform, 'error': error,
                         'attempt_count': attempts_used, 'disposition': disposition})
        halt = halt_reason(error)
        if halt and platform not in halted_platforms:
            halted_platforms[platform] = halt

    raw_eligible = [i for i, item in enumerate(queue) if item.get('status') in POSTABLE_STATUSES]

    def load_brand_policy():
        policy_path = ROOT / 'data/social-brand-policy.json'
        policy = read_json(policy_path, {})
        quotas = policy.get('brand_quotas', {}) if isinstance(policy, dict) else {}
        rotation = policy.get('rotation', {}) if isinstance(policy, dict) else {}
        return quotas, rotation

    brand_quotas, rotation_policy = load_brand_policy()

    def brand_weight(brand):
        try:
            return float(brand_quotas.get(brand, 1.0))
        except Exception:
            return 1.0

    def weighted_posted_score(platform, brand):
        # Lower score gets priority. This makes brands with fewer prior posts relative
        # to their configured quota surface earlier, preventing portfolio starvation.
        return posted_by_brand_platform[(platform, brand)] / max(brand_weight(brand), 0.01)

    def item_priority(i):
        item = queue[i]
        return (
            item.get('last_attempt_at', ''),
            0 if item.get('date') == TODAY else 1,
            0 if item.get('source_url') else 1,
            i
        )

    # Round-robin by platform and brand. This prevents X from burning several daily
    # slots on the same brand just because that brand appears first in social-queue.json.
    platform_brand_groups = defaultdict(list)
    for i in raw_eligible:
        item = queue[i]
        platform = item.get('platform')
        brand = item.get('brand') or item.get('domain') or 'unknown'
        platform_brand_groups[(platform, brand)].append(i)
    for key in platform_brand_groups:
        platform_brand_groups[key].sort(key=item_priority)

    eligible_indices = []
    for platform in ('linkedin', 'x'):
        brand_keys = [key for key in platform_brand_groups if key[0] == platform]
        
        rotation_offset = TODAY_ORDINAL % max(len(brand_keys), 1)
        brand_keys.sort(key=lambda key: (
            weighted_posted_score(key[0], key[1]),
            (seen_order.get(key[1], 9999) - rotation_offset) % max(len(brand_keys), 1),
            key[1]
        ))
        more = True
        while more:
            more = False
            for key in brand_keys:
                group = platform_brand_groups[key]
                if group:
                    eligible_indices.append(group.pop(0))
                    more = True

    for idx in eligible_indices:
        item = queue[idx]
        platform = item.get('platform')
        # A platform that has refused the account stops for the rest of the run.
        # Continuing past a 429 is the single most account-damaging thing this
        # script can do: it converts one rate-limit response into hundreds of
        # further requests against an endpoint that has just said stop.
        if platform in halted_platforms:
            continue
        if platform == 'linkedin' and (not enable_li or spent_today['linkedin'] >= li_limit):
            continue
        if platform == 'x' and (not enable_x or spent_today['x'] >= x_limit):
            continue
        if attempted_this_run.get(platform, 0) >= run_limit:
            continue
        body = append_url(item.get('body',''), item)
        if any(jaccard_text(body, old) > max_sim for old in bodies_today_by_platform[platform]):
            item['status'] = 'skipped_duplicate'
            item['skipped_at'] = datetime.now(timezone.utc).isoformat()
            skipped.append({'index': idx, 'platform': platform, 'reason': 'same_day_similarity'})
            continue
        # Space live posts apart, with jitter, so a run does not emit a clump on
        # one timestamp. Placed after the similarity guard so a skipped item does
        # not burn a delay, and skipped for dry runs and the run's first attempt.
        # Keyed on ATTEMPTS, not successes: a run whose posts are all failing is
        # exactly when spacing matters most, and keying it on successes meant a
        # fully-failing run paced nothing at all.
        if not dry_run and sum(attempted_this_run.values()) > 0 and min_interval > 0:
            time.sleep(min_interval * random.uniform(0.7, 1.6))
        # Budget is consumed HERE, before the call, because what the platform
        # rate-limits and what the free-tier allowance counts is the request,
        # not the outcome. Charging only for successes is what let a run whose
        # every call failed make one request per queue entry.
        item['last_attempt_at'] = datetime.now(timezone.utc).isoformat()
        item['attempt_count'] = int(item.get('attempt_count') or 0) + 1
        attempted_this_run[platform] = attempted_this_run.get(platform, 0) + 1
        spent_today[platform] = spent_today.get(platform, 0) + 1
        attempts.append({'index': idx, 'platform': platform, 'brand': item.get('brand'),
                         'attempt_count': item['attempt_count'], 'preview': body[:120]})
        try:
            result = post_item(item, dry_run=dry_run)
            if result.get('ok'):
                item['status'] = 'posted'
                item['posted_at'] = datetime.now(timezone.utc).isoformat()
                item['post_id'] = result.get('id', '')
                item['post_result'] = {'dry_run': result.get('dry_run', False), 'status': result.get('status')}
                posted_today[platform] += 1
                posted_this_run[platform] = posted_this_run.get(platform, 0) + 1
                bodies_today_by_platform[platform].append(body)
                successes.append({'index': idx, 'platform': platform, 'brand': item.get('brand'), 'id': item['post_id'], 'dry_run': result.get('dry_run', False)})
            else:
                record_failure(item, idx, platform, result.get('error', 'unknown_error'))
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', errors='replace')[:500]
            record_failure(item, idx, platform, f'HTTP {e.code}: {detail}')
        except Exception as e:
            record_failure(item, idx, platform, str(e)[:500])

    if not dry_run:
        write_json(QUEUE_PATH, queue)
    report = {
        'date': TODAY,
        'dry_run': dry_run,
        'enabled': {'linkedin': enable_li, 'x': enable_x},
        'platform_states': platform_states,
        'paused_platforms': paused,
        'parked_by_platform_switch': parked_by_platform_switch,
        'secret_skips': platform_secret_skips,
        'limits': {'linkedin': li_limit, 'x': x_limit},
        'pacing': {'run_limit': run_limit, 'min_interval_seconds': min_interval},
        'posted_this_run': posted_this_run,
        'attempted_this_run': attempted_this_run,
        'spent_today': spent_today,
        'halted_platforms': halted_platforms,
        'deferred_for_retry': sum(1 for f in failures if f.get('disposition') == 'deferred_for_retry'),
        'restored_legacy_failures': restored_legacy_failures,
        'still_postable_after_run': sum(1 for i in queue if i.get('status') in POSTABLE_STATUSES),
        'attempts': attempts,
        'successes': successes,
        'failures': failures,
        'skipped': skipped,
        'posted_today': posted_today,
        'brand_rotation_policy': {'quota_count': len(brand_quotas), 'daily_rotation_offset': TODAY_ORDINAL},
        # A partial credential set is a warning, not a block: X posted, LinkedIn
        # did not. Only a run with no usable platform at all is blocked.
        # "partial_failure" for a run where every single attempt failed is a
        # false description, and it is the one the 2026-08-29 run reported while
        # 581 of 581 posts failed. A run that got nothing out is named as such.
        'status': ('blocked_missing_secrets' if platform_secret_skips and no_platform_left and require_secrets and not dry_run
                   else ('ok_with_secret_warning' if platform_secret_skips
                         else ('ok' if not failures
                               else ('all_attempts_failed' if not successes else 'partial_failure')))),
        'named_stops': named_stops_for(platform_states, paused, platform_secret_skips),
    }
    write_json(REPORT_PATH, report)
    print(json.dumps(report, indent=2))
    if failures and truthy('FAIL_ON_SOCIAL_POST_FAILURE', 'false'):
        raise SystemExit('One or more social posts failed')

if __name__ == '__main__':
    main()
