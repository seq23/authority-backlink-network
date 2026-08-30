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

def _early_norm_domain(url_or_domain: str) -> str:
    if str(url_or_domain).startswith('http'):
        host = urlparse(str(url_or_domain)).netloc
    else:
        host = str(url_or_domain)
    return host.lower().replace('www.', '').strip('/')


PUB_FOLDERS = {p['id']: p['folder'] for p in publications}
PUBLICATION_DOMAINS = {p['id']: p['working_domain'] for p in publications}
BRAND_BY_ID = {b['id']: b for b in brands}

def brand_domains(brand):
    return {_early_norm_domain(x) for x in (brand.get('domains') or [brand.get('domain','')]) if x}

TARGET_DOMAIN_TO_BRAND = {}
for brand in brands:
    for domain in brand_domains(brand):
        if domain in TARGET_DOMAIN_TO_BRAND and TARGET_DOMAIN_TO_BRAND[domain]['id'] != brand['id']:
            errors.append(f'duplicate domain ownership: {domain}')
        TARGET_DOMAIN_TO_BRAND[domain] = brand
APPROVED_URLS_BY_DOMAIN = {domain: {link.get('url','').rstrip('/') for link in brand.get('approved_links', []) if _early_norm_domain(link.get('url','')) == domain} for domain, brand in TARGET_DOMAIN_TO_BRAND.items()}
ALL_TARGET_DOMAINS = set(TARGET_DOMAIN_TO_BRAND)
ALL_PUBLICATION_DOMAINS = {d.replace('www.', '') for d in PUBLICATION_DOMAINS.values()}
# Analytics and schema hosts are infrastructure, not editorial destinations. They
# are referenced from <script>/<link> rather than linked to, so the outbound-link
# rules below do not apply, but the domain lock still sees them in the raw text.
# Listed explicitly so the lock stays a real allowlist rather than being widened.
INFRASTRUCTURE_DOMAINS = {'clarity.ms', 'www.clarity.ms'}

# Verified non-affiliated authoritative sources, from data/external-sources.json.
# Until these existed every outbound link on all three publications pointed at a
# domain inside this network, which is what a link farm looks like from outside.
# The lock is not widened to "any .gov": only registered URLs whose existence was
# confirmed over the network by scripts/verify_external_sources.py may be cited,
# and only from the publication lanes the registry names.
external_sources = json.loads((ROOT / 'data/external-sources.json').read_text())
EXTERNAL_SOURCE_BY_URL = {s['url'].rstrip('/'): s for s in external_sources['sources']}
EXTERNAL_SOURCE_DOMAINS = {_early_norm_domain(s['url']) for s in external_sources['sources']}
EXTERNAL_SOURCE_LANES = {}
for _s in external_sources['sources']:
    EXTERNAL_SOURCE_LANES.setdefault(_early_norm_domain(_s['url']), set()).update(_s['lanes'])

ALLOWED_EXTERNAL_DOMAINS = (ALL_TARGET_DOMAINS | ALL_PUBLICATION_DOMAINS
                            | INFRASTRUCTURE_DOMAINS | EXTERNAL_SOURCE_DOMAINS)

ALLOWED_PUB_TARGETS = {}
for b in brands:
    for pub in b['approved_publications']:
        ALLOWED_PUB_TARGETS.setdefault(pub, set()).update(brand_domains(b))

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
# Same anchors, but keeping the whole opening tag so `rel` is inspectable.
ANCHOR_TAG_RE = re.compile(r'<a\s+([^>]*?href="([^"]+)"[^>]*?)>(.*?)</a>', re.I | re.S)


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
    domains = brand_domains(b)
    if not domains:
        errors.append(f"{b['id']}: no registered domain")
    if b.get('url') and norm_domain(b['url']) not in domains:
        warnings.append(f"{b['id']}: url is not one of the registered domains: {b['url']}")
    for pub in b['approved_publications']:
        if pub not in PUB_FOLDERS:
            errors.append(f"{b['id']}: unknown approved publication {pub}")
    for link in b.get('approved_links', []):
        if norm_domain(link.get('url','')) not in domains:
            errors.append(f"{b['id']}: approved link uses unowned domain: {link.get('url')}")
    if b.get('id') == 'dream-wedding-builder':
        expected_domains = {'weddingchecklistpdf.com','weddingbudgetspreadsheet.com','weddingtimelinetemplate.com','weddingseatingchartmaker.com'}
        expected_routes = {'/build','/products/checklist-pdf','/products/budget-spreadsheet','/products/timeline-template','/products/seating-chart-maker'}
        if domains != expected_domains:
            errors.append(f'dream-wedding-builder: domain set mismatch: {sorted(domains)}')
        products = b.get('products', [])
        routes = {x.get('route') for x in products}
        if routes != expected_routes:
            errors.append(f'dream-wedding-builder: route set mismatch: {sorted(routes)}')
        if sum(1 for x in products if x.get('destination_type') == 'free_tool') != 1:
            errors.append('dream-wedding-builder: exactly one free_tool product is required')
        if sum(1 for x in products if x.get('destination_type') == 'paid_product') != 4:
            errors.append('dream-wedding-builder: exactly four paid_product records are required')

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
        if domain not in brand_domains(brand):
            errors.append(f'{pantry_pub}: brand/domain mismatch for {brand_id}: {domain} not owned by brand')
        if expected_pub not in brand.get('approved_publications', []):
            errors.append(f'{pantry_pub}: {brand_id} is not approved for {expected_pub}')
        links = target.get('approved_links') or []
        if not links:
            errors.append(f'{pantry_pub}: {brand_id} has no approved links')
        for link in links:
            if norm_domain(link.get('url', '')) not in brand_domains(brand):
                errors.append(f'{pantry_pub}: {brand_id} approved link uses wrong domain: {link.get("url")}')

# Validate HTML pages.
pages_examined = 0
for pub, folder in PUB_FOLDERS.items():
    base = ROOT / folder
    if not base.exists():
        errors.append(f'Missing publication folder: {folder}')
        continue
    for path in sorted(base.rglob('*.html')):
        pages_examined += 1
        rel = str(path.relative_to(ROOT))
        txt = path.read_text(errors='ignore')
        lower = txt.lower()
        if '/agency/' in '/' + rel or re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', txt, re.I):
            continue

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
            if domain in EXTERNAL_SOURCE_DOMAINS and pub not in EXTERNAL_SOURCE_LANES[domain]:
                errors.append(f'{rel}: external source domain {domain} is not registered for the {pub} lane')

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

        # Citations of outside authorities. Two things have to hold or the
        # citation is worse than none: the exact URL must be one that was
        # actually fetched and verified, and it must not be declared sponsored.
        # rel="sponsored" on a CFPB or USCIS page would tell a crawler this
        # publication was paid to link to a federal agency, which is a false
        # disclosure and undoes the reason for citing it.
        for open_tag, href, anchor_html in ANCHOR_TAG_RE.findall(txt):
            if not href.startswith('http'):
                continue
            if norm_domain(href) not in EXTERNAL_SOURCE_DOMAINS:
                continue
            if href.rstrip('/') not in EXTERNAL_SOURCE_BY_URL:
                errors.append(f'{rel}: unverified external-source URL (not in data/external-sources.json): {href}')
                continue
            rel_match = re.search(r'rel="([^"]*)"', open_tag, re.I)
            rel_tokens = {t.lower() for t in rel_match.group(1).split()} if rel_match else set()
            if 'sponsored' in rel_tokens:
                errors.append(f'{rel}: editorial citation must not be marked sponsored: {href}')
            if not clean_anchor(anchor_html):
                errors.append(f'{rel}: external-source citation has empty anchor text: {href}')

        # Generic product-aware routing. Metadata is structural; topic fit is warning-only.
        for domain, anchor, href in outbound_targets:
            brand = TARGET_DOMAIN_TO_BRAND.get(domain, {})
            product_by_url = {x.get('url','').rstrip('/'): x for x in brand.get('approved_links', [])}
            meta = product_by_url.get(href.rstrip('/'))
            if not meta:
                errors.append(f'{rel}: destination has no registered metadata: {href}')
                continue
            if meta.get('product_id') and not meta.get('destination_type'):
                errors.append(f'{rel}: product destination missing destination_type: {href}')
            if brand.get('id') == 'dream-wedding-builder' and not meta.get('route'):
                errors.append(f'{rel}: Dream Wedding Builder destination missing route: {href}')
            topics = meta.get('topics') or []
            if topics and '*' not in topics and not any(topic.lower() in lower for topic in topics):
                warnings.append(f'{rel}: product/topic fit should be reviewed: {href}')

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
        # Matched on word boundaries rather than as bare substrings: 'cure ' as a
        # substring also fires on "obscure concern", "secure the venue" and
        # "procure a permit", none of which is a health claim. The claim this
        # rule exists to catch - "cure", "cures" - is still caught.
        for phrase in BANNED_PHRASES:
            if re.search(r'\b' + re.escape(phrase.strip()) + r'\b', lower):
                # Footer says no fake rankings/reviews; that is allowed as a disclosure.
                if phrase.startswith('fake') and 'no fake' in lower:
                    continue
                errors.append(f'{rel}: banned phrase: {phrase}')

        # Sensitive pages need disclaimer language.
        if any(term in lower for term in SENSITIVE_TERMS):
            if REQUIRED_DISCLOSURE_SNIPPETS[1] not in lower:
                errors.append(f'{rel}: sensitive topic page missing full professional-advice disclaimer')

# Validate City Vendor lifecycle and preservation.
city_path = ROOT / 'data/city-publications.json'
if not city_path.exists():
    errors.append('data/city-publications.json is missing')
else:
    city_data = json.loads(city_path.read_text())
    cities = city_data.get('cities', [])
    memphis = next((c for c in cities if c.get('id') == 'memphis'), None)
    if not memphis or memphis.get('status') != 'active':
        errors.append('Memphis must remain an active City Vendor publication')
    for c in cities:
        if c.get('status') not in {'candidate','approved','building','active','paused','retired'}:
            errors.append(f"city {c.get('id')}: invalid status {c.get('status')}")
    memphis_pub = next((p for p in publications if p.get('id') == 'memphis'), {})
    if 'porch-party' not in memphis_pub.get('supports', []):
        errors.append('Memphis publication must continue to support Porch & Party')
    if 'dream-wedding-builder' not in memphis_pub.get('supports', []):
        errors.append('Memphis publication must support Dream Wedding Builder')

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
        # The duplicate check exists to stop duplicate POSTING, so it only
        # applies to entries that can still be posted. An entry retired as
        # not_for_posting is kept in the file on purpose -- with its reason --
        # as an audit trail of a decision, and counting it here would make that
        # record itself the failure.
        retired = item.get('status') == 'not_for_posting'
        if not retired:
            if key in seen:
                errors.append(f'data/social-queue.json item {i}: duplicate {platform} body')
            seen.add(key)
        # 'buffer_queued' is a real terminal status, not a typo: Buffer has
        # accepted the post and holds it in the X channel's queue until the
        # channel's next posting slot. It is deliberately NOT 'posted' -- queued
        # in Buffer is not published on X -- and it is in no postable set, so the
        # entry is never sent again. Missing from this list, it turned the first
        # run that actually delivered anything through the route into a hard
        # failure, on the day the route started working.
        if item.get('status') not in {'draft_requires_human_approval','queued_for_auto_post','approved_for_auto_post','posted','buffer_queued','post_failed','skipped_duplicate','failed_permanent','not_for_posting'}:
            errors.append(f'data/social-queue.json item {i}: unsupported social status: {item.get("status")}')
        target_url = item.get('target_url') or item.get('source_url') or ''
        if target_url.startswith('http') and norm_domain(target_url) not in (ALL_TARGET_DOMAINS | ALL_PUBLICATION_DOMAINS):
            errors.append(f'data/social-queue.json item {i}: social target/source domain not in registry: {target_url}')
        for phrase in BANNED_PHRASES:
            if phrase in body_key:
                errors.append(f'data/social-queue.json item {i}: banned phrase in social body: {phrase}')

# Rule 0: a hostile review that read no pages found no problems for the same
# reason a closed book contains no typos. Proved by deleting every file under
# sites/: this reported PASS. The publication folders are committed, so an empty
# sweep is a moved tree or a broken PUB_FOLDERS mapping, not a clean library.
if not pages_examined:
    errors.append(
        'hostile review examined 0 published pages. The publication folders named in '
        'PUB_FOLDERS are tracked in git and always contain pages, so finding none means '
        'the tree moved or the mapping broke. Reporting PASS here would vouch for nothing.'
    )

report = {
    'status': 'PASS' if not errors else 'FAIL',
    'pages_examined': pages_examined,
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
