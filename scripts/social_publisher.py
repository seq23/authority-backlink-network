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
import base64, copy, hashlib, hmac, json, os, re, time, urllib.parse, urllib.request, urllib.error
from collections import defaultdict
from pathlib import Path
from datetime import date, datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = Path(os.getenv('SOCIAL_QUEUE_PATH', str(ROOT / 'data/social-queue.json')))
REPORT_PATH = Path(os.getenv('SOCIAL_REPORT_PATH', str(ROOT / 'reports/social-publisher-report.json')))
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
TODAY = date.today().isoformat()
TODAY_ORDINAL = date.today().toordinal()

POSTED_STATUSES = {'posted', 'skipped_duplicate', 'failed_permanent'}
POSTABLE_STATUSES = {'queued_for_auto_post', 'approved_for_auto_post'}


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


def x_post(text):
    url = 'https://api.x.com/2/tweets'
    payload = {'text': text}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        method='POST',
        headers={
            'Authorization': x_oauth_header('POST', url),
            'Content-Type': 'application/json'
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode('utf-8', errors='replace')
        out = json.loads(body) if body.strip().startswith('{') else {'raw': body}
        return {'ok': True, 'status': resp.status, 'id': out.get('data', {}).get('id', ''), 'body': out}


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


def main():
    original_queue = read_json(QUEUE_PATH, [])
    queue = original_queue
    if isinstance(queue, dict):
        queue = queue.get('items', [])
    # Dry-run validation must never mutate the publish queue. Live mode mutates statuses after real API attempts.
    if truthy('SOCIAL_DRY_RUN', 'false') or truthy('MOCK_SOCIAL_POSTING', 'false'):
        queue = copy.deepcopy(queue)
    enable_li = truthy('ENABLE_LINKEDIN_POSTING', 'true')
    enable_x = truthy('ENABLE_X_POSTING', 'true')
    dry_run = truthy('SOCIAL_DRY_RUN', 'false') or truthy('MOCK_SOCIAL_POSTING', 'false')
    require_secrets = truthy('REQUIRE_SOCIAL_SECRETS', 'true')
    li_limit = int(os.getenv('LINKEDIN_DAILY_LIMIT', '1'))
    x_limit = int(os.getenv('X_DAILY_LIMIT', '5'))
    max_sim = float(os.getenv('MAX_SOCIAL_SIMILARITY', '0.86'))
    # Count already-posted items for TODAY so multiple workflows cannot exceed
    # the daily cap when both autopilot and social-only schedules run.
    posted_today = {'linkedin': 0, 'x': 0}
    attempts, successes, failures, skipped = [], [], [], []

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

    if platform_secret_skips and require_secrets and not dry_run:
        strict_failure = truthy('FAIL_ON_SOCIAL_POST_FAILURE', 'false')
        report = {
            'date': TODAY, 'dry_run': False,
            'enabled': {'linkedin': enable_li, 'x': enable_x},
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
        if platform == 'linkedin' and (not enable_li or posted_today['linkedin'] >= li_limit):
            continue
        if platform == 'x' and (not enable_x or posted_today['x'] >= x_limit):
            continue
        body = append_url(item.get('body',''), item)
        if any(jaccard_text(body, old) > max_sim for old in bodies_today_by_platform[platform]):
            item['status'] = 'skipped_duplicate'
            item['skipped_at'] = datetime.now(timezone.utc).isoformat()
            skipped.append({'index': idx, 'platform': platform, 'reason': 'same_day_similarity'})
            continue
        item['last_attempt_at'] = datetime.now(timezone.utc).isoformat()
        attempts.append({'index': idx, 'platform': platform, 'brand': item.get('brand'), 'preview': body[:120]})
        try:
            result = post_item(item, dry_run=dry_run)
            if result.get('ok'):
                item['status'] = 'posted'
                item['posted_at'] = datetime.now(timezone.utc).isoformat()
                item['post_id'] = result.get('id', '')
                item['post_result'] = {'dry_run': result.get('dry_run', False), 'status': result.get('status')}
                posted_today[platform] += 1
                bodies_today_by_platform[platform].append(body)
                successes.append({'index': idx, 'platform': platform, 'brand': item.get('brand'), 'id': item['post_id'], 'dry_run': result.get('dry_run', False)})
            else:
                item['status'] = 'post_failed'
                item['last_error'] = result.get('error', 'unknown_error')
                failures.append({'index': idx, 'platform': platform, 'error': item['last_error']})
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', errors='replace')[:500]
            item['status'] = 'post_failed'
            item['last_error'] = f'HTTP {e.code}: {detail}'
            failures.append({'index': idx, 'platform': platform, 'error': item['last_error']})
        except Exception as e:
            item['status'] = 'post_failed'
            item['last_error'] = str(e)[:500]
            failures.append({'index': idx, 'platform': platform, 'error': item['last_error']})

    if not dry_run:
        write_json(QUEUE_PATH, queue)
    report = {
        'date': TODAY,
        'dry_run': dry_run,
        'enabled': {'linkedin': enable_li, 'x': enable_x},
        'secret_skips': platform_secret_skips,
        'limits': {'linkedin': li_limit, 'x': x_limit},
        'attempts': attempts,
        'successes': successes,
        'failures': failures,
        'skipped': skipped,
        'posted_today': posted_today,
        'brand_rotation_policy': {'quota_count': len(brand_quotas), 'daily_rotation_offset': TODAY_ORDINAL},
        'status': ('blocked_missing_secrets' if platform_secret_skips and require_secrets and not dry_run else ('ok_with_secret_warning' if platform_secret_skips else ('ok' if not failures else 'partial_failure')))
    }
    write_json(REPORT_PATH, report)
    print(json.dumps(report, indent=2))
    if failures and truthy('FAIL_ON_SOCIAL_POST_FAILURE', 'false'):
        raise SystemExit('One or more social posts failed')

if __name__ == '__main__':
    main()
