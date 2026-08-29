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

from lib import buffer_route, social_platforms, social_selection
import social_drafts

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = Path(os.getenv('SOCIAL_QUEUE_PATH', str(ROOT / 'data/social-queue.json')))
REPORT_PATH = Path(os.getenv('SOCIAL_REPORT_PATH', str(ROOT / 'reports/social-publisher-report.json')))
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
# Where the manual-posting fallback keeps its state and writes its sheet. Both
# default beside the queue and the report they belong to, so a fixture run
# pointed at a temporary queue cannot write over the committed ones.
DRAFT_LEDGER_PATH = Path(os.getenv('SOCIAL_DRAFT_LEDGER_PATH',
                                   str(social_drafts.ledger_path_default(QUEUE_PATH))))
DRAFTS_PATH = Path(os.getenv('SOCIAL_DRAFTS_PATH',
                             str(social_drafts.drafts_path_default(REPORT_PATH))))
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


# Text rendering and selection live in scripts/lib/social_selection.py, so the
# manual-drafts sheet in scripts/social_drafts.py offers the SAME posts, in the
# same order, with the same characters that this module would have sent.
normalize = social_selection.normalize
jaccard_text = social_selection.jaccard_text
append_url = social_selection.append_url
trim_x = social_selection.trim_x


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


def post_item(item, dry_run=False, route=None):
    """Send one item, through its platform's API or through a delivery route.

    `route` is a live scripts/lib/buffer_route.Route. When one is passed for an
    item, it is the ONLY thing contacted: X's own API is not called, not even
    to check. That is what keeps "zero requests to X" true while X posts.
    """
    platform = item.get('platform')
    # One renderer, shared with the manual-drafts sheet, so what the API is sent
    # and what she is asked to paste cannot diverge.
    text = social_selection.post_text(item)
    if not text:
        return {'ok': False, 'error': 'empty_body'}
    if dry_run:
        
        dry_key = f"{platform}|{item.get('brand','')}|{item.get('post_type','')}|{item.get('source_path','')}|{text}"
        return {'ok': True, 'dry_run': True, 'id': f"dry-{hashlib.sha1(dry_key.encode()).hexdigest()[:12]}", 'text': text}
    if route is not None:
        result = route.create_post(text)
        # Accepted by Buffer is QUEUED, not published: Buffer sends it at the
        # channel's next posting slot. The caller records the difference.
        return {'ok': True, 'via': 'buffer', 'id': result['id'],
                'buffer_status': result.get('buffer_status'),
                'due_at': result.get('due_at'),
                'channel_id': result.get('channel_id'), 'status': 200}
    if platform == 'linkedin':
        return linkedin_post(text)
    if platform == 'x':
        return x_post(text)
    return {'ok': False, 'error': f'unsupported_platform:{platform}'}


def named_stops_for(platform_states, paused, secret_skips):
    """A named reason for every platform that did nothing this run.

    "Did nothing" must never be left to be inferred. The cases read differently
    on purpose: a dormant pause is a decision to produce nothing, a pause FOR
    POSTING is a decision to stop the API while distribution continues by hand,
    an uncredentialled switch is a to-do, and an undocumented switch-off is a
    bug that scripts/validators/validate_social_rate_limits.py also fails the
    build on.
    """
    stops = {}
    for platform, state in platform_states.items():
        if state == social_platforms.STATE_ON:
            continue
        if state == social_platforms.STATE_ROUTED:
            # Not a stop at all: posts left. Named anyway, because "X posted
            # today and X's API was never called" is the one sentence a reader
            # of this report most needs and would otherwise have to infer.
            stops[platform] = (
                f"{platform}_delivered_via_buffer: {platform}'s own API stayed off and "
                f"was contacted ZERO times -- it is pay-per-use and unfunded. The day's "
                f"posts were handed to Buffer's free queue instead, and Buffer publishes "
                f"them at the channel's next posting slot. Entries carry status "
                f"'buffer_queued' with the Buffer post id, and are NOT offered on "
                f"reports/social-drafts.md, because a post Buffer accepted must not also "
                f"be posted by hand."
            )
            continue
        if state == social_platforms.STATE_PAUSED:
            stops[platform] = (
                f"{platform}_paused_by_switch: {(paused.get(platform) or {}).get('paused_reason')} "
                f"Nothing is posted and nothing is drafted -- this pause is dormant on "
                f"purpose. Turn it back on by setting platforms.{platform}.enabled to true "
                f"in data/social-brand-policy.json."
            )
        elif state == social_platforms.STATE_PAUSED_FOR_POSTING:
            # Not the same stop as a dormant pause, and it must not read like
            # one: nothing was POSTED, but the day's distribution still went
            # out. A report saying only "paused" would describe a stopped lane.
            stops[platform] = (
                f"{platform}_paused_for_posting: {(paused.get(platform) or {}).get('paused_reason')} "
                f"ZERO requests were made to the {platform} API this run. Distribution did "
                f"not stop: the day's posts are on reports/social-drafts.md to be posted by "
                f"hand, and marked done in data/social-draft-ledger.json. Turn automatic "
                f"posting back on by setting platforms.{platform}.enabled to true in "
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

    # ------------------------------------------------------------------ route
    # X's own API is pay-per-use and unfunded, so it stays off. Buffer is a
    # DELIVERY ROUTE for the same X profile at no per-post cost: declared on
    # platforms.x.delivery_route in data/social-brand-policy.json, opened here,
    # and used INSTEAD of X's API -- never alongside it. The queue, the
    # selection order and the drafting fallback are untouched.
    #
    # Everything about the ceiling is discovered from Buffer at runtime
    # (dailyPostingLimits), then capped again by this network's own
    # X_DAILY_LIMIT. A number hardcoded here would be a guess that survives
    # Buffer changing it.
    x_route = None
    x_route_declared = social_platforms.route_enabled(
        'x', social_platforms.ROUTE_BUFFER, platform_policy)
    if x_route_declared and not dry_run and not enable_x:
        x_route = buffer_route.Route('x', policy_daily_limit=x_limit).open()
    x_via_route = bool(x_route and x_route.available)
    # Drafts already offered to her by hand and not yet marked posted. The route
    # must not take one: she would post it, and Buffer would post it again.
    open_draft_fingerprints = social_drafts.open_fingerprints(
        social_drafts.read_ledger(DRAFT_LEDGER_PATH)) if x_via_route else set()
    # The manual-posting fallback. A platform that is switched ON and still
    # cannot get a post out does not get to leave the run empty-handed: the
    # day's highest-value posts are written to a copy-paste sheet instead, so
    # distribution keeps happening while the API is dead. It reads the queue and
    # writes nothing to it, so restoring the API restores automatic posting with
    # no un-drafting pass. See scripts/social_drafts.py.
    def emit_drafts(states, halted=None, attempted=None, posted_run=None,
                    spent=None, posted=None):
        unavailable = social_drafts.unavailable_platforms(
            states, halted or {}, attempted or {}, posted_run or {},
            spent or {}, posted or {})
        eligible = social_selection.eligible_in_priority_order(
            queue, platform_policy, TODAY, TODAY_ORDINAL)
        return social_drafts.run(
            queue, eligible, unavailable, policy=platform_policy,
            ledger_path=DRAFT_LEDGER_PATH, drafts_path=DRAFTS_PATH,
            today=TODAY, batch_sizes={'linkedin': li_limit, 'x': x_limit},
            # A dry run reports what it WOULD draft and persists nothing, for the
            # same reason it does not write the queue.
            write=not dry_run)

    posted_this_run = {'linkedin': 0, 'x': 0}
    # Count already-posted items for TODAY so multiple workflows cannot exceed
    # the daily cap when both autopilot and social-only schedules run.
    posted_today = {'linkedin': 0, 'x': 0}
    attempts, successes, failures, skipped = [], [], [], []

    # Rule 0: a run with nothing switched on must stop with a NAMED reason, not
    # fall through the loop and exit 0 having done nothing.
    #
    # "Nothing switched on" is no longer the same as "nothing to do". A platform
    # paused FOR POSTING is off here and still owes the day its drafts, and this
    # branch returns before a single credential is read or a single request is
    # made -- which is exactly how "zero API requests while paused" is achieved
    # rather than asserted. So the drafts are cut first and the run is named by
    # what it actually produced.
    if not enable_li and not enable_x and not x_via_route:
        off_states = {p: social_platforms.platform_state(p, None, platform_policy)
                      for p in social_platforms.PLATFORMS}
        drafts = emit_drafts(off_states)
        produced = drafts.get('drafts_written', 0) + drafts.get('drafts_reissued', 0)
        drafting = sorted(social_platforms.drafting_platforms(platform_policy))
        _, parked_off = social_platforms.partition_queue(queue, platform_policy)
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
            'parked_by_platform_switch': {k: len(v) for k, v in parked_off.items()},
            'api_requests_made': 0,
            # The route was declared and could not carry anything. Say why, in
            # the report she reads, rather than leaving "X went out by hand
            # again" to be explained by someone reading the code.
            'delivery_routes': {
                'x': {
                    'route': social_platforms.ROUTE_BUFFER,
                    'declared_enabled': x_route_declared,
                    'used_this_run': False,
                    'receipt': x_route.receipt() if x_route is not None else None,
                    'why_not_used': (
                        (x_route.reason if x_route is not None else
                         'the Buffer route is not switched on for x in '
                         'data/social-brand-policy.json')
                        if not x_via_route else None),
                    'x_api_requests_made': 0,
                }
            },
            'drafting_platforms': drafting,
            'still_postable_after_run': sum(1 for i in queue
                                            if i.get('status') in POSTABLE_STATUSES),
            'manual_drafts': drafts,
            'status': ('posted_nothing_drafted_by_hand' if produced
                       else 'stopped_no_enabled_platform'),
            'production_blocked': False,
            'stop_reason': (
                # Two genuinely different outcomes, named differently. "Posted
                # nothing, drafted 8" is a run that did its work through the
                # other route; "everything dormant, nothing produced" is a run
                # that did none, and only the second is a stop.
                (f"No platform posts through its API right now, and none was contacted: "
                 f"zero requests were made. Distribution still ran -- {produced} post(s) "
                 f"are waiting on reports/social-drafts.md for "
                 f"{', '.join(drafting) or 'the drafting platforms'}, to be posted by hand "
                 f"and then marked done in data/social-draft-ledger.json. The posting queue "
                 f"is untouched and every entry keeps its status."
                 ) if produced else
                ('Every social platform switch is off in data/social-brand-policy.json, '
                 'none is paused for posting with drafts due, and there is no queued '
                 'content left to hand over, so this run had nothing to produce by any '
                 'route. '
                 + ('Recorded decisions: '
                    + '; '.join(f"{k}: {v.get('paused_reason')}" for k, v in paused.items())
                    if paused else
                    'No platform carries a paused_on/paused_by/paused_reason record, so this '
                    'is an undocumented switch-off rather than a decision.'))
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
    if x_via_route:
        # The route is open, so X's posts leave through it and must NOT also be
        # drafted by hand. If the route were unavailable or had refused, this
        # line does not run and X reports paused_for_posting exactly as before,
        # with the sheet cut as before -- the fallback is unchanged, not removed.
        platform_states['x'] = social_platforms.STATE_ROUTED
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
            'manual_drafts': emit_drafts(platform_states),
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
    for existing in queue:
        platform = existing.get('platform')
        # A post Buffer accepted today is not published yet, but it IS out of
        # this network's hands and must count against the same-day duplicate
        # guard. Otherwise a near-identical post is queued behind it.
        if (existing.get('posted_at', '') or existing.get('buffer_queued_at', '')
                ).startswith(TODAY):
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
    # Counted apart from posted_this_run on purpose: these are in Buffer's
    # queue, not on X. Merging them would report posts as published that Buffer
    # has not sent yet.
    buffer_queued_this_run = 0
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

    brand_quotas = platform_policy.get('brand_quotas', {}) if isinstance(platform_policy, dict) else {}

    # Selection moved to scripts/lib/social_selection.py unchanged: brand
    # round-robin, quota-weighted starvation guard, date-ordinal rotation, and
    # never-attempted-first within a brand. It is shared with the manual-drafts
    # lane so a sheet written by hand cannot offer a different post, or a
    # different order, from the one the API would have received.
    eligible_indices = social_selection.eligible_in_priority_order(
        queue, platform_policy, TODAY, TODAY_ORDINAL)

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
        if platform == 'x':
            if not enable_x and not x_via_route:
                continue
            if spent_today['x'] >= x_limit:
                continue
            if x_via_route:
                # The route's own discovered ceiling, spent in ATTEMPTS, and a
                # hard stop the moment it has refused once. Both are enforced
                # inside scripts/lib/buffer_route.py as well; this is the same
                # rule read before a request is built rather than after.
                if x_route.halted or x_route.remaining() <= 0:
                    continue
                if social_drafts.fingerprint(item) in open_draft_fingerprints:
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
            item_route = x_route if (platform == 'x' and x_via_route) else None
            result = post_item(item, dry_run=dry_run, route=item_route)
            if result.get('ok') and result.get('via') == 'buffer':
                # ACCEPTED, NOT PUBLISHED. Buffer holds the post in the
                # channel's queue and sends it at the next posting slot, so
                # calling this 'posted' would claim something that has not
                # happened yet. 'buffer_queued' is in no postable set, so the
                # entry is never re-sent, and it is not in POSTABLE_STATUSES,
                # so the hand-post sheet can never offer it either.
                item['status'] = 'buffer_queued'
                item['delivered_via'] = 'buffer'
                item['buffer_queued_at'] = datetime.now(timezone.utc).isoformat()
                item['buffer_post_id'] = result.get('id', '')
                item['buffer_channel_id'] = result.get('channel_id', '')
                item['buffer_post_status'] = result.get('buffer_status')
                item['buffer_due_at'] = result.get('due_at')
                item['post_id'] = result.get('id', '')
                buffer_queued_this_run += 1
                bodies_today_by_platform[platform].append(body)
                successes.append({'index': idx, 'platform': platform,
                                  'brand': item.get('brand'), 'id': item['buffer_post_id'],
                                  'via': 'buffer', 'published': False,
                                  'buffer_status': result.get('buffer_status'),
                                  'due_at': result.get('due_at')})
            elif result.get('ok'):
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
        except buffer_route.BufferError as e:
            # Buffer said no. The route has already halted itself; mirror that
            # here so the loop cannot ask a second time, and never treat it as
            # the entry's fault -- the entry is deferred, not retired.
            record_failure(item, idx, platform, f'buffer_route: {str(e)[:400]}')
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', errors='replace')[:500]
            record_failure(item, idx, platform, f'HTTP {e.code}: {detail}')
        except Exception as e:
            record_failure(item, idx, platform, str(e)[:500])
        if x_route is not None and x_route.halted and 'x' not in halted_platforms:
            halted_platforms['x'] = f'buffer_route_halted: {x_route.halted}'

    # If the route refused part-way, the posts it did not carry still have to
    # reach X somehow. Reporting X as routed would silently drop them, so the
    # platform goes back to paused_for_posting and the sheet is cut exactly as
    # it was before Buffer existed. Entries Buffer already accepted carry
    # status 'buffer_queued' and are in no postable set, so they cannot be
    # drafted -- no post is offered twice.
    draft_states = dict(platform_states)
    if x_route is not None and x_route.halted:
        draft_states['x'] = social_platforms.platform_state('x', None, platform_policy)
    manual_drafts = emit_drafts(draft_states, halted_platforms, attempted_this_run,
                                posted_this_run, spent_today, posted_today)
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
        'buffer_queued_this_run': buffer_queued_this_run,
        # What Buffer holds is NOT what X has published. Anything reading this
        # report has to be able to tell the two apart without knowing how the
        # route works.
        'delivery_routes': {
            'x': {
                'route': social_platforms.ROUTE_BUFFER,
                'declared_enabled': x_route_declared,
                'used_this_run': bool(x_route is not None),
                'receipt': x_route.receipt() if x_route is not None else None,
                'meaning_of_buffer_queued': (
                    "Buffer accepted the post and holds it in the X channel's queue. It "
                    "is NOT published yet: Buffer sends it at the channel's next posting "
                    "slot. The entry keeps status 'buffer_queued' with the Buffer post "
                    "id, is never re-sent, and is never offered on the hand-post sheet."
                ),
                'x_api_requests_made': 0,
            }
        },
        'attempted_this_run': attempted_this_run,
        'spent_today': spent_today,
        'halted_platforms': halted_platforms,
        'manual_drafts': manual_drafts,
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
