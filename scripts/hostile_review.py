#!/usr/bin/env python3
"""Hostile review gate for the targeted Authority Network.

Blocks:
- outbound links to domains outside the locked target/publication registry
- links from the wrong publication lane to a target domain
- canonical guide sites linking back to The Industry Guides
- banned YMYL/spam claims in publishable pages/social drafts
- missing disclosure/disclaimer language on sensitive pages
- duplicate social drafts
"""
import json
import pathlib
import re
import sys
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
brands = json.loads((ROOT / 'data/brands.json').read_text())
publications = json.loads((ROOT / 'data/publications.json').read_text())
rules = json.loads((ROOT / 'data/network-rules.json').read_text())

errors = []
warnings = []

PUB_FOLDERS = {p['id']: p['folder'] for p in publications}
PUBLICATION_DOMAINS = {p['id']: p['working_domain'] for p in publications}
TARGET_DOMAIN_TO_BRAND = {b['domain'].replace('www.', ''): b for b in brands}
BRAND_BY_ID = {b['id']: b for b in brands}
APPROVED_URLS_BY_DOMAIN = {norm: {link.get('url','').rstrip('/') for link in brand.get('approved_links', [])} for norm, brand in TARGET_DOMAIN_TO_BRAND.items()}
ALL_TARGET_DOMAINS = set(TARGET_DOMAIN_TO_BRAND)
ALL_PUBLICATION_DOMAINS = {d.replace('www.', '') for d in PUBLICATION_DOMAINS.values()}
ALLOWED_EXTERNAL_DOMAINS = ALL_TARGET_DOMAINS | ALL_PUBLICATION_DOMAINS

ALLOWED_PUB_TARGETS = {}
for b in brands:
    for pub in b['approved_publications']:
        ALLOWED_PUB_TARGETS.setdefault(pub, set()).add(b['domain'].replace('www.', ''))

BANNED_PHRASES = [
    'guaranteed settlement', 'guaranteed results', 'guaranteed approval',
    'guaranteed success', 'guaranteed healing', 'best lawyer', 'best dentist',
    'best civil surgeon', 'best equine lawyer', 'best in memphis without proof',
    'diagnose you', 'cure ', 'cures ', 'fake review', 'fake reviews',
    'official provider endorsement', 'safe for everyone'
]
SENSITIVE_TERMS = [
    'legal', 'lawyer', 'attorney', 'contract', 'medical', 'dentist', 'dental',
    'hormone', 'iv hydration', 'neuro', 'adhd', 'autism', 'uscis', 'immigration',
    'therapy', 'mental', 'burnout', 'clinical', 'diagnosis'
]
REQUIRED_DISCLOSURE_SNIPPETS = [
    'affiliation disclosed',
    'not legal, medical, mental-health, immigration, financial, or professional advice'
]

URL_RE = re.compile(r'https?://[^\s"\'<>]+')
ANCHOR_RE = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)


def norm_domain(url_or_domain: str) -> str:
    if url_or_domain.startswith('http'):
        host = urlparse(url_or_domain).netloc
    else:
        host = url_or_domain
    return host.lower().replace('www.', '').strip('/')


def clean_anchor(html: str) -> str:
    return re.sub(r'<.*?>', '', html).strip()


# Validate brand registry itself.
brand_ids = [b['id'] for b in brands]
if len(brand_ids) != len(set(brand_ids)):
    errors.append('data/brands.json contains duplicate brand ids')
for b in brands:
    if norm_domain(b['domain']) not in norm_domain(b['url']):
        warnings.append(f"{b['id']}: url/domain mismatch: {b['url']} vs {b['domain']}")
    for pub in b['approved_publications']:
        if pub not in PUB_FOLDERS:
            errors.append(f"{b['id']}: unknown approved publication {pub}")

# Validate publications only support known brand ids.
known = set(brand_ids)
for p in publications:
    for support in p['supports']:
        if support not in known:
            errors.append(f"publication {p['id']} supports unknown brand id {support}")

# Validate paired pantry targets against the brand registry.
pantry = json.loads((ROOT / 'content-bank/yearly-pantry.json').read_text())
for pantry_pub, config in pantry.get('publications', {}).items():
    expected_pub = pantry_pub.replace('-operator', '').replace('-local', '').replace('-resources', '')
    for target in config.get('targets', []):
        if not isinstance(target, dict):
            errors.append(f'{pantry_pub}: legacy unpaired target remains: {target}')
            continue
        brand_id = target.get('brand_id')
        brand = BRAND_BY_ID.get(brand_id)
        if not brand:
            errors.append(f'{pantry_pub}: target references unknown brand id {brand_id}')
            continue
        domain = norm_domain(target.get('domain', ''))
        if domain != norm_domain(brand.get('domain', '')):
            errors.append(f'{pantry_pub}: brand/domain mismatch for {brand_id}: {domain} != {brand.get("domain")}')
        if expected_pub not in brand.get('approved_publications', []):
            errors.append(f'{pantry_pub}: {brand_id} is not approved for {expected_pub}')
        links = target.get('approved_links') or []
        if not links:
            errors.append(f'{pantry_pub}: {brand_id} has no approved links')
        for link in links:
            if norm_domain(link.get('url', '')) != domain:
                errors.append(f'{pantry_pub}: {brand_id} approved link uses wrong domain: {link.get("url")}')

# Validate HTML pages.
for pub, folder in PUB_FOLDERS.items():
    base = ROOT / folder
    if not base.exists():
        errors.append(f'Missing publication folder: {folder}')
        continue
    for path in sorted(base.rglob('*.html')):
        rel = str(path.relative_to(ROOT))
        txt = path.read_text(errors='ignore')
        lower = txt.lower()

        if 'affiliation disclosed' not in lower:
            errors.append(f'{rel}: missing affiliation disclosure')

        # External URL domain lock.
        for url in URL_RE.findall(txt):
            domain = norm_domain(url)
            if domain == 'schema.org':
                continue
            if domain not in ALLOWED_EXTERNAL_DOMAINS:
                errors.append(f'{rel}: external domain not allowed by registry: {domain}')
            if domain in ALL_TARGET_DOMAINS and domain not in ALLOWED_PUB_TARGETS.get(pub, set()):
                errors.append(f'{rel}: target domain {domain} is not allowed in {pub} publication')

        # Anchor checks only for outbound target links.
        outbound_targets = []
        for href, anchor_html in ANCHOR_RE.findall(txt):
            if href.startswith('http'):
                domain = norm_domain(href)
                anchor = clean_anchor(anchor_html)
                if domain in ALL_TARGET_DOMAINS:
                    outbound_targets.append((domain, anchor, href))
                    if len(anchor.split()) > 14:
                        warnings.append(f'{rel}: unusually long outbound anchor should be reviewed for clarity: {anchor}')

        if len(outbound_targets) > 8:
            warnings.append(f'{rel}: high outbound-link count; review only if the page feels crowded')

        # Product-aware Approval Prep routing. Missing or wrong-domain metadata is structural;
        # topic fit is editorial judgment and therefore warning-only with normal margins.
        approval_brand = TARGET_DOMAIN_TO_BRAND.get('approvalprep.com', {})
        product_by_url = {x.get('url','').rstrip('/'): x for x in approval_brand.get('approved_links', [])}
        for domain, anchor, href in outbound_targets:
            if domain != 'approvalprep.com':
                continue
            meta = product_by_url.get(href.rstrip('/'))
            if not meta:
                errors.append(f'{rel}: Approval Prep destination has no registered product metadata: {href}')
                continue
            if not meta.get('destination_type') or not meta.get('product_id'):
                errors.append(f'{rel}: Approval Prep destination missing destination_type/product_id: {href}')
            topics = meta.get('topics') or []
            if '*' not in topics and not any(topic.lower() in lower for topic in topics):
                warnings.append(f'{rel}: Approval Prep product/topic fit should be reviewed: {href}')

        # Approval Prep affirmative-claim boundaries. Boundary/disclaimer language is allowed.
        if 'approvalprep.com' in lower or 'approval prep' in lower:
            prohibited_patterns = [
                r'approval prep (?:will |can )?repair(?:s)? your credit',
                r'approval prep (?:will |can )?remove(?:s)? negative',
                r'guaranteed (?:approval|deletion|score increase)',
                r'raise your (?:credit )?score fast',
                r'get approved today',
                r'we contact (?:the )?(?:bureaus|creditors|landlords|lenders)',
                r'(?:we|approval prep) (?:create|creates|provide|provides) (?:fake|fabricated|verified) (?:income )?documents'
            ]
            for pattern in prohibited_patterns:
                if re.search(pattern, lower):
                    errors.append(f'{rel}: prohibited Approval Prep claim: {pattern}')
            if 'approval prep is not a credit-repair company' not in lower and 'approval prep does not repair credit' not in lower:
                warnings.append(f'{rel}: Approval Prep page should state the no-credit-repair boundary clearly')

        # YMYL/spam phrase check.
        for phrase in BANNED_PHRASES:
            if phrase in lower:
                # Footer says no fake rankings/reviews; that is allowed as a disclosure.
                if phrase.startswith('fake') and 'no fake' in lower:
                    continue
                errors.append(f'{rel}: banned phrase: {phrase}')

        # Sensitive pages need disclaimer language.
        if any(term in lower for term in SENSITIVE_TERMS):
            if REQUIRED_DISCLOSURE_SNIPPETS[1] not in lower:
                errors.append(f'{rel}: sensitive topic page missing full professional-advice disclaimer')

# Validate no canonical target file links back to The Industry Guides in the registry.
canonical_ids = {'accident-guides','dentistry-guides','hormones-iv-hair','neuro-eval-guides','uscis-exam-guides'}
for b in brands:
    if b['id'] in canonical_ids:
        for link in b.get('approved_links', []):
            if 'theindustryguides.com' in link.get('url',''):
                errors.append(f"{b['id']}: canonical approved_links cannot point back to The Industry Guides")

# Validate social queue is safe for auto-posting and not duplicated.
social_path = ROOT / 'data/social-queue.json'
if social_path.exists():
    social = json.loads(social_path.read_text())
    seen = set()
    for i, item in enumerate(social):
        body_key = re.sub(r'\s+', ' ', item.get('body','').strip().lower())
        platform = item.get('platform')
        key = (platform, body_key)
        if key in seen:
            errors.append(f'data/social-queue.json item {i}: duplicate {platform} body')
        seen.add(key)
        if item.get('status') not in {'draft_requires_human_approval','queued_for_auto_post','approved_for_auto_post','posted','post_failed','skipped_duplicate','failed_permanent'}:
            errors.append(f'data/social-queue.json item {i}: unsupported social status: {item.get("status")}')
        target_url = item.get('target_url') or item.get('source_url') or ''
        if target_url.startswith('http') and norm_domain(target_url) not in (ALL_TARGET_DOMAINS | ALL_PUBLICATION_DOMAINS):
            errors.append(f'data/social-queue.json item {i}: social target/source domain not in registry: {target_url}')
        for phrase in BANNED_PHRASES:
            if phrase in body_key:
                errors.append(f'data/social-queue.json item {i}: banned phrase in social body: {phrase}')

report = {
    'status': 'PASS' if not errors else 'FAIL',
    'target_domains_locked': sorted(ALL_TARGET_DOMAINS),
    'publication_domains_assumed': sorted(ALL_PUBLICATION_DOMAINS),
    'errors': errors,
    'warnings': warnings,
    'hostile_questions': rules['hostile_review_questions'],
}
(ROOT / 'reports').mkdir(exist_ok=True)
(ROOT / 'reports/hostile-review-report.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
if errors:
    sys.exit(1)
