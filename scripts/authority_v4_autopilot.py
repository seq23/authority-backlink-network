#!/usr/bin/env python3
"""
Authority Network V4.1 Autopilot
$0-first deterministic content generation + optional Gemini polish.
Designed for three publication sites already deployed by Cloudflare Git integration.
"""
import os, json, re, hashlib, random, html, urllib.request
from pathlib import Path
import cadence_allowance
from datetime import date, datetime, timezone
from urllib.parse import urlparse
from lib.authority_core import atomic_write_json, read_json
from lib import lastmod_ledger, site_urls
# rel_attr marks affiliated outbound links rel="sponsored nofollow". Both call
# sites below used it without importing it, so every run of this script died
# with NameError: name 'rel_attr' is not defined.
from affiliation import rel_attr
from byline import entity_for
from lib import page_composer

ROOT = Path(__file__).resolve().parents[1]
PANTRY = json.loads((ROOT/'content-bank/yearly-pantry.json').read_text(encoding='utf-8'))
SCALING = json.loads((ROOT/'content-bank/scaling-policy.json').read_text(encoding='utf-8'))
GROWTH = json.loads((ROOT/'data/brand-growth-profiles.json').read_text(encoding='utf-8'))
GROWTH_BY_BRAND = {x['brand_id']: x for x in GROWTH.get('profiles', [])}
CAMPAIGNS = json.loads((ROOT/'data/portfolio-backlink-campaigns.json').read_text(encoding='utf-8')) if (ROOT/'data/portfolio-backlink-campaigns.json').exists() else {'campaigns': []}
CAMPAIGN_BY_ID = {x['id']: x for x in CAMPAIGNS.get('campaigns', [])}
STATE_PATH = ROOT/'data/autopilot-state.json'
REPORT_DIR = ROOT/'reports'
REPORT_DIR.mkdir(exist_ok=True)
TODAY = os.getenv('BUILD_DATE') or date.today().isoformat()
RELEASE_DATE = os.getenv('PUBLIC_RELEASE_DATE') or TODAY
DEFAULT_STATE = {
    'launch_date': TODAY,
    'published_hashes': [],
    'published_signatures': [],
    'published_titles': [],
    'history': []
}

PUBLICATIONS = json.loads((ROOT/'data/publications.json').read_text(encoding='utf-8'))
PUBLICATION_BY_FOLDER = {p['folder'].split('/')[-1]: p for p in PUBLICATIONS}
PUBLICATION_BY_ID = {p['id']: p for p in PUBLICATIONS}

STOP_PHRASES = [
    'in today\'s fast-paced world', 'game-changer', 'unlock your potential',
    'guaranteed', 'best ever', '#1', 'number one', 'ultimate solution',
    'revolutionize', 'transform your life overnight'
]

YMYL_TERMS = [
    'legal', 'lawyer', 'attorney', 'medical', 'health', 'therapy', 'mental health',
    'burnout', 'hormone', 'dentistry', 'neuro', 'uscis', 'injury', 'equine legal'
]


def write_json(path, data):
    atomic_write_json(Path(path), data)


def stable_int(value):
    return int(hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:12], 16)


def slugify(s):
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:90].strip('-') or 'resource'


def normalized_text(text):
    text = re.sub(r'<script.*?</script>', ' ', text, flags=re.I|re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\b20\d\d-\d\d-\d\d\b', ' ', text)
    text = re.sub(r'Generated at [^\.]+\.', ' ', text)
    text = re.sub(r'[^a-z0-9 ]+', ' ', text.lower())
    return re.sub(r'\s+', ' ', text).strip()


def content_hash(html_text):
    return hashlib.sha256(normalized_text(html_text).encode('utf-8')).hexdigest()


def word_set(text):
    return set(re.findall(r'[a-z]{5,}', normalized_text(text)))


def jaccard(a, b):
    wa, wb = word_set(a), word_set(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def days_since(start):
    try:
        return (date.fromisoformat(TODAY) - date.fromisoformat(start)).days + 1
    except Exception:
        return 1


def recent_stats(state, days=14):
    hist = state.get('history', [])[-days:]
    if not hist:
        return {'pass_rate': 1.0, 'avg_quality': 85, 'duplicate_warnings': 0, 'hard_fails': 0}
    total = sum(x.get('generated', 0) for x in hist) or 1
    passed = sum(x.get('published', 0) for x in hist)
    scores = [s for x in hist for s in x.get('scores', [])]
    return {
        'pass_rate': passed / total,
        'avg_quality': sum(scores) / len(scores) if scores else 85,
        'duplicate_warnings': sum(x.get('duplicate_warnings', 0) for x in hist),
        'hard_fails': sum(x.get('hard_fails', 0) for x in hist)
    }


def choose_volume(day, stats):
    env = os.getenv('DAILY_PAGE_LIMIT')
    if env:
        try:
            return max(1, min(int(env), int(os.getenv('ABSOLUTE_MAX_PAGES_PER_DAY', '9'))))
        except Exception:
            pass
    # Only verified structural/compliance failures may reduce global volume.
    # Duplicate notices, quality scores, word counts, and cadence variance are diagnostics.
    if stats.get('hard_fails', 0) > 0:
        return 3
    if day <= 14:
        return 3
    if day <= 45:
        return 6 if stats['pass_rate'] >= .85 else 3
    if day <= 90:
        return 6 if stats['pass_rate'] >= .75 else 3
    if day <= 365:
        if stats['pass_rate'] >= .85 and stats['avg_quality'] >= 85:
            return 9
        if stats['pass_rate'] >= .75:
            return 6
        return 3
    return 6


def pick(arr, seed):
    if not arr:
        return ''
    rng = random.Random(stable_int(seed))
    return arr[rng.randrange(len(arr))]


def normalize_target(target):
    if isinstance(target, dict):
        return target
    return {'brand_id': '', 'brand': str(target), 'domain': str(target), 'approved_links': [{'url': f'https://{target}', 'anchor': str(target), 'topics': ['*']}]}


def target_scope(target_cfg):
    """The clusters this target may be cited on, and nothing wider.

    A target that declares no `eligible_clusters` gets an EMPTY scope here, not
    the publication's whole cluster list. That inversion is the fix: the old
    line read

        eligible_clusters = target_cfg.get('eligible_clusters') or pub['clusters']

    so a target with no declared scope inherited all 58 professional clusters,
    the page's subject and its paid destination were then drawn independently,
    and they landed together only by chance. That is how uscisexam.com - the
    one property in the portfolio earning AI citations - was cited from a page
    about trauma-informed leadership, dentistryguides.com from a page about
    credit-report errors, and hormonesivhair.com from a page about equine
    liability.

    An empty scope makes a target unschedulable rather than universally
    schedulable. Not placing a link is free; placing it on the wrong subject
    damages the property it points at and makes the page's own disclosure
    sentence - "may cite affiliated projects where the citation is topically
    relevant" - false.
    """
    if not isinstance(target_cfg, dict):
        # A bare-string target declares nothing, so it scopes to nothing.
        return []
    return [c for c in (target_cfg.get('eligible_clusters') or []) if str(c).strip()]


def link_matches_cluster(link, cluster):
    """Does this approved link belong on a page about `cluster`?

    `'*'` means "valid anywhere in this target's declared scope" - not "valid
    on any subject in the publication". The distinction only became safe once
    target_scope() stopped handing an undeclared target every cluster: all
    eight undeclared targets carried `topics: ['*']` on every approved link, so
    the topical filter below matched unconditionally and never constrained
    anything. Bounded by a real scope, the wildcard is now a statement about
    links within a subject rather than a hole in the routing.
    """
    topics = link.get('topics') or ['*']
    return '*' in topics or cluster in topics


def product_match_strength(link, cluster):
    if not link_matches_cluster(link, cluster):
        return -1
    base = {'paid_product': 40, 'free_tool': 35, 'free_creation_tool': 35, 'educational_guide': 20, 'trust_boundary': 10}.get(link.get('destination_type'), 0)
    return base + (5 if link.get('preferred') else 0)



def published_counts_by_brand():
    records = read_json(ROOT/'data/link-registry.json', [])
    if isinstance(records, dict):
        records = records.get('links', [])
    counts = {}
    for row in records:
        if row.get('status') in {'published','rendered','live_verified','discoverable','indexed'} or row.get('lifecycle_stage') in {'published_in_repository','rendered_in_repository','deployed','live_verified','source_discovered','source_indexed'}:
            bid = row.get('target_brand_id')
            if bid:
                counts[bid] = counts.get(bid, 0) + 1
            cid = row.get('campaign_id')
            if cid:
                counts['campaign:'+cid] = counts.get('campaign:'+cid, 0) + 1
    return counts


# The share of a publication's pages one brand may be cited from. Read from the
# policy file, never defaulted: a missing cap is a policy question, not a value
# for this module to invent.
MAX_BRAND_PAGE_SHARE = float(SCALING.get('hard_limits', {})['max_brand_page_share_per_publication'])
_SPONSORED_A = re.compile(r'<a\s+([^>]*)>', re.I)
_HREF = re.compile(r'href="([^"]+)"')
_REL = re.compile(r'rel="([^"]*)"')
_SHARE_CACHE = {}


def _host_to_brand():
    """Every host an owned target is reachable at, mapped to its brand id.

    Keyed off approved_links as well as `domain` because dream-wedding-builder
    is one brand behind four sibling domains; counting them separately would
    read a 51% share as four unremarkable ones.
    """
    out = {}
    for pub in PANTRY['publications'].values():
        for target in pub.get('targets', []):
            if not isinstance(target, dict) or not target.get('brand_id'):
                continue
            hosts = [str(target.get('domain', ''))]
            hosts += [str(l.get('url', '')) for l in target.get('approved_links', [])
                      if isinstance(l, dict)]
            for value in hosts:
                host = urlparse(value if '//' in value else '//' + value).netloc.lower()
                host = host.removeprefix('www.')
                if host:
                    out[host] = target['brand_id']
    return out


def brands_at_share_cap(pub_key):
    """Brand ids already cited from at least their share of this publication's pages.

    Counted from the rendered pages rather than from data/link-registry.json,
    because the ledger is a record of intent and the pages are the footprint.

    This is the guard that was missing. approval-prep reached 290 of
    professional-resources' 420 pages - 69%, against 31.4% and 32.7% for the
    leading brand in the other two publications - because nothing in the
    scheduler could see a share, only a per-campaign deficit that a priority
    target with no `until_rendered_coverage` never stopped filling.
    """
    if pub_key in _SHARE_CACHE:
        return _SHARE_CACHE[pub_key]
    site_path = ROOT / PANTRY['publications'][pub_key]['site_path']
    brands = _host_to_brand()
    total, carrying = 0, {}
    for path in sorted(site_path.rglob('*.html')):
        if path.name == '404.html':
            continue
        total += 1
        seen = set()
        for attrs in _SPONSORED_A.findall(path.read_text(encoding='utf-8', errors='ignore')):
            href = _HREF.search(attrs)
            rel = _REL.search(attrs)
            if not href or not rel or 'sponsored' not in rel.group(1):
                continue
            host = urlparse(href.group(1)).netloc.lower().removeprefix('www.')
            if host in brands:
                seen.add(brands[host])
        for bid in seen:
            carrying[bid] = carrying.get(bid, 0) + 1
    allowed = int(total * MAX_BRAND_PAGE_SHARE)
    result = {bid for bid, n in carrying.items() if n >= allowed}
    _SHARE_CACHE[pub_key] = result
    return result


def schedulable_targets(pub_key, targets):
    """`targets` minus the ones already at their share of this publication.

    A brand at the cap is not offered another slot. It is not an error and does
    not degrade to "place it anyway": if every target in a publication is at its
    cap the day produces nothing there, which the run already reports honestly.
    """
    capped = brands_at_share_cap(pub_key)
    return [t for t in targets if t.get('brand_id') not in capped]


def choose_fair_target(pub_key, slot, counts):
    """Choose the largest weighted portfolio deficit without forcing a link outside topic fit.

    Targets guide scheduling only. The page generator still selects a contextually eligible
    cluster and the validators may reject unsafe or contradictory output.
    """
    # A target with no declared cluster scope is not schedulable. Offering it a
    # slot could only ever produce a page whose subject was drawn at random, so
    # it is filtered here rather than left for build_brief to refuse downstream.
    targets = [t for t in PANTRY['publications'][pub_key].get('targets', [])
               if isinstance(t, dict) and not t.get('priority') and target_scope(t)]
    targets = schedulable_targets(pub_key, targets)
    if not targets:
        return None
    scored = []
    for target in targets:
        bid = target.get('brand_id','')
        profile = GROWTH_BY_BRAND.get(bid, {})
        monthly = max(1, int(profile.get('target_authority_pages_per_month', 1)))
        weight = float(profile.get('scheduler_weight', 1))
        campaign_id = target.get('campaign_id','')
        current = counts.get('campaign:'+campaign_id, 0) if campaign_id else counts.get(bid, 0)
        # Lower coverage relative to the configured target receives more scheduling weight.
        deficit = weight * monthly / (current + 1)
        tie = stable_int(f'{TODAY}|{pub_key}|{slot}|{bid}') / 10**15
        scored.append((deficit + tie, target))
    return max(scored, key=lambda x: x[0])[1]

def build_brief(pub_key, slot, state, attempt=0, target_override=None):
    pub = PANTRY['publications'][pub_key]
    seed = f'{TODAY}-{pub_key}-{slot}-{attempt}-{len(state.get("published_signatures", []))}'
    if target_override is not None:
        target_cfg = normalize_target(target_override)
    else:
        regular_targets = [t for t in pub['targets']
                           if not (isinstance(t, dict) and t.get('priority')) and target_scope(t)]
        regular_targets = schedulable_targets(pub_key, regular_targets)
        if not regular_targets:
            return None
        target_cfg = normalize_target(pick(regular_targets, seed+'target'))
    eligible_clusters = target_scope(target_cfg)
    if not eligible_clusters:
        # No declared scope, so there is no subject on which this citation is
        # known to be relevant. Decline the slot instead of drawing a subject at
        # random out of the publication's whole cluster list.
        return None
    cluster = pick(eligible_clusters, seed+'cluster')
    audience = pick(pub['audiences'], seed+'audience')
    fmt = pick(pub['formats'], seed+'format')
    intent = pick(pub['intents'], seed+'intent')
    modifier = pick(pub['modifiers'], seed+'modifier')
    candidate_links = [link for link in target_cfg.get('approved_links', []) if link_matches_cluster(link, cluster)]
    if not candidate_links:
        # Decline, do not degrade. This used to read
        #
        #     if not candidate_links:
        #         candidate_links = target_cfg.get('approved_links', [])
        #
        # which turned the topical filter off at exactly the moment it had
        # something to say, and shipped a link anyway. It is the line that
        # actually put an off-topic citation on a published page. Returning None
        # leaves the slot unwritten; the caller retries with a fresh seed and
        # records the refusal, so nothing is silently dropped.
        return None
    if any(isinstance(link, dict) and link.get('product_id') for link in candidate_links):
        strongest = max((product_match_strength(link, cluster) for link in candidate_links), default=-1)
        candidate_links = [link for link in candidate_links if product_match_strength(link, cluster) == strongest]
        preferred = [link for link in candidate_links if link.get('preferred')]
        if preferred:
            candidate_links = preferred
    selected_link = pick(candidate_links, seed+'approved-link')
    fallback_domain = target_cfg.get('domain', '')
    target_url = selected_link.get('url', f'https://{fallback_domain}') if isinstance(selected_link, dict) else f'https://{fallback_domain}'
    target_domain = urlparse(target_url).netloc.replace('www.','') if target_url.startswith('http') else fallback_domain
    anchor = selected_link.get('anchor', target_cfg.get('brand', target_domain)) if isinstance(selected_link, dict) else target_cfg.get('brand', target_domain)
    brand = target_cfg.get('brand', target_domain)
    brand_id = target_cfg.get('brand_id', '')
    title = f"{cluster.title()}: {modifier.title()} {fmt.title()} {intent.title()}"
    signature = hashlib.sha256(f'{pub_key}|{cluster}|{audience}|{fmt}|{intent}|{modifier}|{target_url}|{anchor}|{brand_id}'.encode()).hexdigest()
    return {
        'publication': pub_key, 'cluster': cluster, 'audience': audience, 'format': fmt,
        'intent': intent, 'modifier': modifier, 'title': title, 'target_domain': target_domain,
        'target_url': target_url, 'anchor': anchor, 'brand_id': brand_id, 'brand': brand,
        'social_hooks': target_cfg.get('social_hooks', []), 'ctas': target_cfg.get('ctas', []),
        'destination_type': selected_link.get('destination_type','') if isinstance(selected_link, dict) else '',
        'product_id': selected_link.get('product_id','') if isinstance(selected_link, dict) else '',
        'product_name': selected_link.get('product_name','') if isinstance(selected_link, dict) else '',
        'product_message': selected_link.get('product_message','') if isinstance(selected_link, dict) else '',
        'target_route': selected_link.get('route','') if isinstance(selected_link, dict) else '',
        'preferred_domain': selected_link.get('preferred_domain','') if isinstance(selected_link, dict) else '',
        'campaign_id': target_cfg.get('campaign_id') or (selected_link.get('campaign_id','') if isinstance(selected_link, dict) else ''),
        'used_preferred_domain': bool(selected_link.get('preferred')) if isinstance(selected_link, dict) else False,
        'signature': signature
    }


# section_blocks() drew N entries from a pantry list by hashing the page title.
# It is gone with the moulds it fed: content-bank/yearly-pantry.json still holds
# intro_blocks, body_blocks, checklist_blocks and faq_blocks, but nothing reads
# them, because every entry in those lists was one of three sentence templates
# with a cluster name substituted in.


def generate_page(brief):
    pub = PANTRY['publications'][brief['publication']]
    title = brief['title']
    cluster = brief['cluster']
    audience = brief['audience']
    target = brief['target_domain']
    target_url = brief.get('target_url', f'https://{target}')
    brand = brief['brand']
    anchor = brief.get('anchor') or brand
    disclaimer = pub.get('disclaimer', 'This page is educational and editorial, not professional advice.')
    product_section = ''
    if brief.get('brand_id') == 'approval-prep':
        disclaimer += ' Approval Prep is not a credit-repair company. It does not contact third parties, provide legal or financial advice, create fake documents, verify income, or guarantee approval, deletion, or score improvement.'
        product_name = brief.get('product_name') or 'Approval Prep resource'
        product_message = brief.get('product_message') or 'Create the letter. Build the packet. Get ready before you apply.'
        product_section = f'<h2>What you can create</h2><p><strong>{html.escape(product_name)}:</strong> {html.escape(product_message)}</p><p>You complete the document with your own truthful facts, review it, and send it yourself. Approval Prep does not make the approval decision.</p>'
    generated = (f'{RELEASE_DATE}T00:00:00Z' if os.getenv('PUBLIC_RELEASE_DATE') else datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'))
    slug = slugify(title)
    # The extensionless form, from the same helper the sitemap uses. A canonical
    # that names the .html file points at a URL the origin answers 308 for.
    canonical_url = site_urls.page_url(pub['default_domain'], f'daily/{TODAY}-{slug}.html')

    # The body used to be drawn from the pantry: ten paragraphs cut from two
    # sentence moulds, nine checklist items from a third, five FAQ entries whose
    # answers were one sentence repeated, and a decision table that was the same
    # four rows on every page. The topic names inside the moulds came from a hash
    # over the publication's whole cluster list rather than from this page's
    # cluster, so a page about compassion fatigue argued about dental decisions.
    # scripts/template_share.js put the result at 45.9% median template share
    # against a 40% ceiling. page_composer builds the body from what the brief
    # and the registries already know about this specific page instead.
    publication = PUBLICATION_BY_FOLDER.get(brief['publication'], {})
    brand_record = page_composer.brand_for_url(target_url)
    approved = page_composer.approved_link_for_url(brand_record, target_url)
    campaign = page_composer.campaign_for_url(target_url)
    facts = {
        'title': title,
        'cluster': cluster,
        'audience': audience,
        'format': brief['format'],
        'intent': brief['intent'],
        'modifier': brief['modifier'],
        'date': RELEASE_DATE,
        'pub_title': publication.get('title') or pub['default_domain'],
        'pub_domain': publication.get('working_domain') or pub['default_domain'],
        'anchor_text': anchor,
        'link_html': f'<a href="{html.escape(target_url)}"{rel_attr(target_url)}>{html.escape(anchor)}</a>',
        'brand_name': brand_record.get('name', ''),
        'brand_category': brand_record.get('category', ''),
        'brand_compliance': brand_record.get('compliance', ''),
        'link_policy': brand_record.get('link_policy', ''),
        'link_topics': [t for t in (approved.get('topics') or []) if t and t != '*'],
        'campaign_id': campaign.get('campaign_id', '') or brief.get('campaign_id', ''),
        'campaign_keywords': campaign.get('keywords', []) or [],
        'destination_type': brief.get('destination_type') or approved.get('destination_type', ''),
        'product_section_html': product_section,
        'editorial_note_html': (
            '<h2>Editorial note</h2><p><strong>Affiliation disclosed:</strong> this publication may '
            'cite affiliated projects where the citation is topically relevant. '
            + html.escape(disclaimer)
            + ' This page is not legal, medical, mental-health, immigration, financial, or '
              'professional advice. Verify details with a qualified professional before acting on '
              'sensitive decisions.</p>'),
        'meta_line_html': (
            '<p class="meta">Generated by the Authority Network V4.2 programmatic editorial engine. '
            f'Generated at {generated}.</p>'),
    }
    body_html, faq_entries = page_composer.compose_body(facts)

    article = {
        '@type': 'Article',
        'headline': title,
        'datePublished': RELEASE_DATE,
        'dateModified': RELEASE_DATE,
        # The byline. Derived from scripts/byline.py, which is the same
        # expression install_editorial_chrome.py renders into the VISIBLE
        # footer byline -- so the machine-readable author and the one a
        # reader sees cannot disagree. It used to be a domain string here
        # while the footer named a person, which is exactly the drift this
        # closes.
        'author': {'@type': 'Organization', 'name': entity_for(facts['pub_title'])},
        'about': cluster,
        'audience': {'@type': 'Audience', 'audienceType': audience},
        'mainEntityOfPage': {'@type': 'WebPage', '@id': canonical_url}
    }
    graph = [article]
    faq_node = page_composer.faq_schema(faq_entries)
    if faq_node:
        graph.append(faq_node)
    schema = {'@context': 'https://schema.org', '@graph': graph}
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title><meta name="description" content="A practical, human-first resource for {html.escape(audience)} comparing {html.escape(cluster)} without fake rankings or forced answers."><link rel="canonical" href="{html.escape(canonical_url)}"><link rel="stylesheet" href="../styles.css"><script type="application/ld+json">{json.dumps(schema)}</script></head>
<body><main class="page"><p><a href="../index.html">&larr; Home</a></p><article><h1>{html.escape(title)}</h1>
{body_html}</article></main></body></html>'''
    return slug, page


def score_page(html_text, brief):
    txt = normalized_text(html_text)
    words = len(re.findall(r'\w+', txt))
    score = 88
    hard_fails = []
    warnings = []
    # 850 was calibrated when roughly half of a page was pantry scaffolding, so it
    # rewarded length that carried no information. The repo's stated editorial
    # floor is validation/page_audit.py's WORD_TARGET_MIN of 450; below 300 a page
    # is genuinely too thin to answer anything.
    if words < 450:
        score -= 8; warnings.append('word_count_below_preferred_range')
    if words < 300:
        score -= 8; warnings.append('very_short_page_review_recommended')
    if any(p in txt for p in STOP_PHRASES):
        score -= 20; hard_fails.append('spam_or_ai_cliche_phrase')
    # This counted every 'https://' in the source, which includes the canonical
    # link, the schema.org context, and the mainEntityOfPage @id - so it fired on
    # every page ever generated, for a page carrying exactly one outbound link.
    # Count anchors, which is what the check is about.
    if len(re.findall(r'<a\s[^>]*href="https?://', html_text, re.I)) > 3:
        score -= 8; warnings.append('too_many_links')
    if not re.search(r'<script type="application/ld\+json">', html_text, re.I):
        score -= 10; warnings.append('missing_schema')
    # The FAQ used to be an <h2>FAQ</h2> heading over five pantry entries. It is
    # now a marked-up section with a FAQPage node in the JSON-LD graph, so the
    # check looks for the schema rather than for the old heading text.
    if not re.search(r'"@type":\s*"FAQPage"', html_text, re.I):
        score -= 8; warnings.append('missing_faq')
    is_ymyl = any(term in txt for term in YMYL_TERMS) or brief['publication'] == 'professional-resources'
    if is_ymyl and not re.search(r'educational|not .*advice|qualified professional|professional advice', txt, re.I):
        score -= 25; hard_fails.append('ymyl_without_disclaimer')
    if re.search(r'fake review|fake ranking|guaranteed|#1|number one', txt, re.I):
        score -= 30; hard_fails.append('unsafe_claim_or_fake_review_language')
    if brief.get('target_url', brief['target_domain']) not in html_text:
        score -= 20; hard_fails.append('missing_target_citation')
    return max(0, min(100, score)), words, warnings, hard_fails


def maybe_gemini_rewrite(title, html_text):
    if os.getenv('ENABLE_GEMINI_REWRITE', 'false').lower() != 'true':
        return html_text, 'disabled'
    key = os.getenv('GEMINI_API_KEY')
    if not key:
        return html_text, 'missing_key'
    model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-lite')
    prompt_file = ROOT/'prompts/human_pov_editorial.md'
    base_prompt = prompt_file.read_text(encoding='utf-8') if prompt_file.exists() else 'Rewrite with practical editorial clarity. Do not fabricate.'
    prompt = base_prompt + "\nRewrite this HTML article in a clearer editorial voice while preserving links, disclaimers, schema, and factual caution. Return full HTML only.\nTITLE:" + title + "\nHTML:\n" + html_text[:18000]
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}'
    payload = json.dumps({'contents': [{'parts': [{'text': prompt}]}]}).encode()
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read().decode())
        text = data['candidates'][0]['content']['parts'][0]['text'].strip()
        text = re.sub(r'^```(?:html)?\s*', '', text, flags=re.I).strip()
        text = re.sub(r'\s*```$', '', text).strip()
        if '<html' in text.lower() and '</html>' in text.lower():
            return text, 'rewritten'
        return html_text, 'bad_response'
    except Exception as e:
        return html_text, 'failed:' + str(e)[:120]


def update_sitemap(site_path, domain):
    # Guard the same failure deterministic_build.py hit: a missing domain
    # formats into the URLs below as a literal "https://None/...", producing a
    # syntactically valid sitemap that points every page at an unresolvable
    # host. Fail the build instead - that is recoverable; a silently broken
    # sitemap is not noticed until Search Console reports it months later.
    if not domain:
        raise SystemExit(f'update_sitemap: no domain resolved for {site_path}')
    site = ROOT/site_path
    # RELEASE_DATE on every URL made the whole publication claim to have been
    # refreshed on whatever day the autopilot last ran. Only the handful of pages
    # the run actually wrote had changed; the rest were a date bump, which is
    # both untrue and self-defeating - a freshness signal that fires for
    # everything distinguishes nothing. The date now follows the content hash.
    ledger = lastmod_ledger.load()
    # <loc> comes from lib/site_urls.page_url(), shared with the other two
    # sitemap emitters. This function used to build it from its own copy of the
    # same f-string, which named the .html file the origin answers 308 for.
    hashes = {loc: lastmod_ledger.content_hash(text)
              for _, loc, text in site_urls.published_pages(site, domain)}
    lastmods = lastmod_ledger.resolve(hashes, ledger, RELEASE_DATE)
    lastmod_ledger.save(lastmod_ledger.merge(hashes, ledger, RELEASE_DATE))
    newest = max(lastmods.values()) if lastmods else RELEASE_DATE
    sitemap = site_urls.render_sitemap({loc: lastmods[loc] for loc in hashes})
    llms = f'# {domain}\n\nThis site contains editorial resource pages for humans and answer engines. Updated {newest}.\n\nSitemap: https://{domain}/sitemap.xml\n'
    tmp = site/'sitemap.xml.tmp'
    with tmp.open('w', encoding='utf-8', newline='\n') as handle:
        handle.write(sitemap)
    tmp.replace(site/'sitemap.xml')
    tmp = site/'llms.txt.tmp'
    with tmp.open('w', encoding='utf-8', newline='\n') as handle:
        handle.write(llms)
    tmp.replace(site/'llms.txt')



def write_authoring_queue(deferred_jobs, state, cadence):
    """Record the slots the cap deferred, with the angle each was going to take.

    A deferred slot is not a discarded one. Without this the cap would silently
    shrink the day's output and the intent behind each unwritten page would be
    gone, which is how a rate limit turns into quiet attrition. Each entry
    carries enough to write the page later, or to decide it was not worth
    writing - which is also a legitimate outcome, and one the queue makes
    reviewable instead of invisible.
    """
    queue = []
    for i, (pub_key, target_override) in enumerate(deferred_jobs):
        try:
            brief = build_brief(pub_key, i, state, attempt=0, target_override=target_override)
        except Exception as exc:  # a brief that cannot be built is still worth recording
            queue.append({'publication': pub_key, 'error': f'brief_unavailable: {exc}'})
            continue
        if brief is None:
            # Declined on topical grounds, not lost. Recording the refusal keeps
            # it reviewable instead of invisible, which is the whole point of
            # this queue.
            queue.append({'publication': pub_key, 'deferred_on': TODAY,
                          'reason': 'no_topically_eligible_affiliated_link'})
            continue
        queue.append({
            'publication': pub_key,
            'cluster': brief.get('cluster', ''),
            'audience': brief.get('audience', ''),
            'format': brief.get('format', ''),
            'intent': brief.get('intent', ''),
            'modifier': brief.get('modifier', ''),
            'intended_title': brief.get('title', ''),
            'target_brand': brief.get('brand', ''),
            'target_url': brief.get('target_url', ''),
            'signature': brief.get('signature', ''),
            'deferred_on': TODAY,
            'reason': 'weekly_publication_cap',
        })
    write_json(REPORT_DIR/'authoring-queue.json', {
        'schema_version': '1.0',
        'run_at': TODAY,
        'note': (
            'Slots the weekly publication cap deferred. Not discarded: each carries the angle it '
            'was going to take, so it can be written when there is room, or retired on purpose. '
            'The cap is data/cadence/policy.json:new_pages_per_week and is enforced in '
            'scripts/cadence_allowance.py before generation, not after.'
        ),
        'cadence': cadence,
        'deferred': len(queue),
        'queue': queue,
    })


def main():
    state = read_json(STATE_PATH, DEFAULT_STATE)
    for k, v in DEFAULT_STATE.items():
        state.setdefault(k, v if not isinstance(v, list) else [])
    day_index = days_since(state.get('launch_date', TODAY))
    stats = recent_stats(state)
    base_volume = choose_volume(day_index, stats)
    pubs = list(PANTRY['publications'].keys())
    priority_jobs = []
    for rule in SCALING.get('priority_targets', []):
        pub_key = rule.get('publication')
        target = next((t for t in PANTRY['publications'].get(pub_key, {}).get('targets', []) if isinstance(t, dict) and t.get('brand_id') == rule.get('brand_id') and (not rule.get('campaign_id') or t.get('campaign_id') == rule.get('campaign_id'))), None)
        if not target:
            continue
        campaign_id = rule.get('campaign_id') or target.get('campaign_id','')
        current_campaign = published_counts_by_brand().get('campaign:'+campaign_id, 0) if campaign_id else published_counts_by_brand().get(rule.get('brand_id',''), 0)
        if rule.get('until_rendered_coverage') is not None and current_campaign >= int(rule.get('until_rendered_coverage')):
            continue
        # A priority lane is for a campaign in deficit, not a standing exemption
        # from the share cap. This check is why one brand can no longer take the
        # front of the job list every day until it holds two thirds of a
        # publication: the cap is checked before the slot is created, not after.
        if not schedulable_targets(pub_key, [target]):
            print(f"SHARE CAP: {rule.get('brand_id')} is at "
                  f"{MAX_BRAND_PAGE_SHARE:.1%} of {pub_key}; no priority slots today.")
            continue
        # APPROVAL_PREP_PAGES_PER_DAY used to override this line for one brand
        # only. A per-brand environment variable that outranks the shared
        # schedule is how the concentration was produced; the rule file is the
        # only input now.
        requested = int(rule.get('pages_per_day', 1))
        # The configured range is a planning target, not a validator. Allow normal daily variation
        # while preserving the repository-wide absolute safety ceiling.
        requested = max(1, min(requested, int(SCALING.get('hard_limits', {}).get('absolute_max_pages_per_day', 12))))
        priority_jobs.extend([(pub_key, target)] * requested)
    volume = min(base_volume + len(priority_jobs), int(SCALING.get('hard_limits', {}).get('absolute_max_pages_per_day', 12)))
    generated, published, scores = [], [], []
    duplicate_warnings = 0
    hard_fail_count = 0
    min_score = int(os.getenv('MIN_BASE_PUBLISH_SCORE', '60'))
    # This was 96. Each attempt re-rolls the date-seeded PRNG over the yearly
    # pantry - a cartesian product of clusters x formats x intents x modifiers
    # advertising 898,560 to 1,123,200 combinations - and tries again until a
    # permutation clears the score gate. With the daily count fixed as the input
    # and the content as the search space, that is a publication quota in the
    # strict sense, whatever `targets_are_quotas: false` says elsewhere in the
    # config. A slot that needs 96 tries did not have a page worth writing in it.
    #
    # Eight attempts is enough to ride out an unlucky draw or a duplicate hash.
    # Past that the honest output is a shortfall, which is now recorded rather
    # than ground away, because a cadence that cannot be met from real material
    # is information and hiding it is how 743 filler pages got published in a
    # sibling repo to keep a 75-page daily number intact.
    max_self_heal_attempts = max(1, int(os.getenv('SELF_HEAL_MAX_ATTEMPTS', '8')))
    self_heal_recoveries = 0
    self_heal_attempts = 0
    blocked_slots = []

    portfolio_counts = published_counts_by_brand()
    base_jobs = []
    for i in range(base_volume):
        pub_key = pubs[i % len(pubs)]
        base_jobs.append((pub_key, choose_fair_target(pub_key, i, portfolio_counts)))
    jobs = priority_jobs + base_jobs
    jobs = jobs[:volume]

    # The publishing cap the repository already declares finally governs the
    # generator that can violate it. Before this, volume came only from the
    # scaling config and the gate in .github/workflows/hostile-review.yml never
    # saw the result, because git-auto-commit-action pushes with GITHUB_TOKEN and
    # GitHub does not trigger workflows on those pushes. So a declared 3 per week
    # sat next to a measured 63 per week and nothing could reconcile them.
    #
    # Over the cap is not an error and does not fail the run. There is nothing
    # broken about a day with no room left; the honest response is to publish
    # nothing and say so. What would be dishonest is publishing anyway, or
    # quietly discarding the material - so the slots that do not fit are written
    # to the authoring queue with the angle each one was going to take, and the
    # run exits 0.
    site_paths = [cfg['site_path'] for cfg in PANTRY['publications'].values()]
    cadence = cadence_allowance.allowance(ROOT, site_paths, date.fromisoformat(TODAY))
    deferred_jobs = jobs[cadence['allowance']:]
    jobs = jobs[:cadence['allowance']]
    print(
        f"CADENCE: {cadence['published_in_window']} page(s) published in the {cadence['window_days']} days "
        f"to {cadence['window_end']}, cap is {cadence['weekly_cap']} per week -> room for {cadence['allowance']} today; "
        f"{len(deferred_jobs)} slot(s) queued for later."
    )
    if not jobs:
        print("CADENCE: nothing to publish today. This is success, not a failure - the library is at its declared rate.")
    write_authoring_queue(deferred_jobs, state, cadence)
    for i, (pub_key, target_override) in enumerate(jobs):
        accepted = None
        attempt_findings = []
        for attempt in range(max_self_heal_attempts):
            brief = build_brief(pub_key, i, state, attempt=attempt, target_override=target_override)
            if brief is None:
                # No approved link for this target belongs on the subject that
                # was drawn. Retry with a fresh seed; if every attempt refuses,
                # the slot goes unpublished. An unwritten page costs nothing. An
                # off-topic paid citation costs the property it points at.
                attempt_findings.append({'attempt': attempt, 'reason': 'no_topically_eligible_affiliated_link'})
                continue
            if brief['signature'] in state.get('published_signatures', []):
                attempt_findings.append({'attempt': attempt, 'reason': 'duplicate_signature'})
                continue
            slug, page = generate_page(brief)
            score, words, warnings, hard_fails = score_page(page, brief)
            rewrite_status = 'not_needed'
            if 72 <= score < 85 and not hard_fails:
                rewritten, rewrite_status = maybe_gemini_rewrite(brief['title'], page)
                new_score, new_words, new_warnings, new_hard_fails = score_page(rewritten, brief)
                if new_score >= score and not new_hard_fails:
                    page, score, words, warnings, hard_fails = rewritten, new_score, new_words, new_warnings, new_hard_fails
            chash = content_hash(page)
            site_path = PANTRY['publications'][pub_key]['site_path']
            fname = f'{TODAY}-{slug}.html'
            output_path = ROOT/site_path/'daily'/fname
            if hard_fails:
                attempt_findings.append({'attempt': attempt, 'reason': 'hard_fail', 'codes': hard_fails})
                continue
            if score < min_score:
                attempt_findings.append({'attempt': attempt, 'reason': 'score_below_floor', 'score': score})
                continue
            if chash in state.get('published_hashes', []):
                attempt_findings.append({'attempt': attempt, 'reason': 'duplicate_content_hash'})
                continue
            if output_path.exists():
                attempt_findings.append({'attempt': attempt, 'reason': 'existing_output_path'})
                continue
            accepted = (brief, slug, page, score, words, warnings, rewrite_status, chash, site_path, fname, output_path, attempt)
            break

        self_heal_attempts += len(attempt_findings)
        if not accepted:
            hard_fail_count += 1
            blocked_slots.append({'slot': i, 'publication': pub_key, 'attempts': max_self_heal_attempts, 'findings': attempt_findings[-12:]})
            generated.append({'publication': pub_key, 'slot': i, 'status': 'blocked_after_self_heal', 'repair_attempts': len(attempt_findings), 'hard_fails': [x.get('reason') for x in attempt_findings[-12:]]})
            continue

        brief, slug, page, score, words, warnings, rewrite_status, chash, site_path, fname, output_path, accepted_attempt = accepted
        if accepted_attempt > 0:
            self_heal_recoveries += 1
        item = {
            'title': brief['title'], 'publication': pub_key, 'score': score, 'words': words,
            'rewrite_status': rewrite_status, 'warnings': warnings, 'hard_fails': [],
            'self_healed': accepted_attempt > 0, 'repair_attempts': accepted_attempt,
            'repair_history': attempt_findings
        }
        generated.append(item)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_page = output_path.with_suffix(output_path.suffix + '.tmp')
        with tmp_page.open('w', encoding='utf-8', newline='\n') as handle:
            handle.write(page)
        tmp_page.replace(output_path)
        state['published_hashes'].append(chash)
        state['published_signatures'].append(brief['signature'])
        state['published_titles'].append(brief['title'])
        pub_item = {**item, 'path': str((Path(site_path)/'daily'/fname).as_posix()), 'target_brand_id': brief.get('brand_id',''), 'target_domain': brief['target_domain'], 'target_url': brief.get('target_url'), 'anchor': brief.get('anchor'), 'brand': brief['brand'], 'social_hooks': brief.get('social_hooks', []), 'destination_type': brief.get('destination_type',''), 'product_id': brief.get('product_id',''), 'product_name': brief.get('product_name',''), 'target_route': brief.get('target_route',''), 'campaign_id': brief.get('campaign_id',''), 'preferred_domain': brief.get('preferred_domain',''), 'used_preferred_domain': brief.get('used_preferred_domain',False)}
        published.append(pub_item)
        scores.append(score)

    for _, pub in PANTRY['publications'].items():
        domain = os.getenv(pub['domain_env']) or pub['default_domain']
        if (ROOT/pub['site_path']).exists():
            update_sitemap(pub['site_path'], domain)

    linkreg = read_json(ROOT/'data/link-registry.json', [])
    if isinstance(linkreg, dict): linkreg = linkreg.get('links', [])
    for item in published:
        pub_meta = PUBLICATION_BY_FOLDER.get(item['publication'], {})
        linkreg.append({'date': TODAY, 'scheduled_content_date': TODAY, 'release_date': RELEASE_DATE, 'source_path': item['path'], 'source_publication': pub_meta.get('id', item['publication']), 'target_brand_id': item.get('target_brand_id',''), 'target_domain': item['target_domain'], 'target_url': item.get('target_url') or f"https://{item['target_domain']}", 'anchor': item.get('anchor') or item['brand'], 'brand': item['brand'], 'destination_type': item.get('destination_type',''), 'product_id': item.get('product_id',''), 'product_name': item.get('product_name',''), 'target_route': item.get('target_route',''), 'preferred_domain': item.get('preferred_domain',''), 'used_preferred_domain': item.get('used_preferred_domain',False), 'publication_family_id': pub_meta.get('publication_family_id',''), 'city': pub_meta.get('city',''), 'campaign_id': item.get('campaign_id',''), 'authority_page_contract_version': 'v5', 'link_type': 'affiliated-editorial-backlink', 'status': 'published', 'lifecycle_stage': 'published_in_repository', 'evidence': {'repository_rendered': True, 'deployed': False, 'live_verified': False, 'discoverable': False, 'indexed': False, 'search_visibility_observed': False, 'ai_cited': False}, 'score': item['score']})
    write_json(ROOT/'data/link-registry.json', linkreg)

    social = read_json(ROOT/'data/social-queue.json', [])
    if isinstance(social, dict): social = social.get('items', [])
    # Enqueue every published page. Daily platform rate limits are enforced at
    # POST time by scripts/social_publisher.py, which leaves unposted items as
    # queued_for_auto_post so they roll to the next run. Slicing here instead
    # dropped the remainder permanently and silently: 427 of 474 pages (90%)
    # published before this fix never entered the queue on any platform, because
    # LINKEDIN_DAILY_LIMIT=1 and the x_pool ordering below spent all 5 X slots on
    # published[0]. A rate limit belongs where the rate is consumed, not where
    # the candidate is recorded.
    for item in published:
        domain = os.getenv(PANTRY['publications'][item['publication']]['domain_env']) or PANTRY['publications'][item['publication']]['default_domain']
        rel_path = str(Path(item['path']).relative_to(PANTRY['publications'][item['publication']]['site_path'])).replace('index.html','')
        source_url = 'https://' + domain + '/' + rel_path
        body = f"A useful resource does not need to pretend every answer is universal. New note: {item['title']} — built as a decision aid, not a fake ranking."
        if item.get('target_brand_id') == 'approval-prep' and item.get('social_hooks'):
            body = f"{pick(item['social_hooks'], item['title']+'linkedin')} {item['title']}"
        social.append({'date': RELEASE_DATE, 'scheduled_content_date': TODAY, 'platform': 'linkedin', 'status': 'queued_for_auto_post', 'body': body, 'source_path': item['path'], 'source_url': source_url, 'post_type': 'authority_resource_note'})
    
    x_templates = [
        "New resource: {title}. Better questions, fewer loud claims.",
        "Not every resource page needs a hot take. This one is built to help compare the decision: {title}.",
        "Useful citation, not fake ranking: {title}.",
        "Decision aid added: {title}. The point is clarity, not keyword confetti.",
        "Added a practical resource: {title}. Built for people first, search second."
    ]
    x_pool = []
    for idx, item in enumerate(published):
        for t_idx, tmpl in enumerate(x_templates):
            x_pool.append((item, tmpl, idx, t_idx))
    for item, tmpl, idx, t_idx in x_pool:
        domain = os.getenv(PANTRY['publications'][item['publication']]['domain_env']) or PANTRY['publications'][item['publication']]['default_domain']
        rel_path = str(Path(item['path']).relative_to(PANTRY['publications'][item['publication']]['site_path'])).replace('index.html','')
        source_url = 'https://' + domain + '/' + rel_path
        body = tmpl.format(title=item['title'])
        if item.get('target_brand_id') == 'approval-prep' and item.get('social_hooks'):
            hooks = item['social_hooks']
            body = f"{hooks[t_idx % len(hooks)]} {item['title']} [{t_idx + 1}]"
        social.append({'date': RELEASE_DATE, 'scheduled_content_date': TODAY, 'platform': 'x', 'status': 'queued_for_auto_post', 'body': body, 'source_path': item['path'], 'source_url': source_url, 'post_type': f'x_resource_note_{t_idx+1}'})
    write_json(ROOT/'data/social-queue.json', social)
    # Rule 0 visibility: a run that publishes pages but enqueues no distribution
    # for them is a silent drop, so the counts are recorded in the run receipt.
    social_enqueued_paths = {s.get('source_path') for s in social if s.get('scheduled_content_date') == TODAY}
    social_enqueued = {
        'published_pages': len(published),
        'pages_enqueued_for_social': len([p for p in {i['path'] for i in published} if p in social_enqueued_paths]),
        'pages_missing_social': sorted(p for p in {i['path'] for i in published} if p not in social_enqueued_paths),
    }

    # Refresh the portfolio dashboard after canonical state is written.
    try:
        import subprocess
        subprocess.run([os.sys.executable, 'scripts/citation_control_plane.py', 'dashboard'], cwd=ROOT, check=False, capture_output=True, text=True)
    except Exception:
        pass

    run = {'date': TODAY, 'release_date': RELEASE_DATE, 'day_index': day_index, 'target_volume': volume, 'generated': len(generated), 'published': len(published), 'scores': scores, 'duplicate_warnings': duplicate_warnings, 'hard_fails': hard_fail_count, 'self_heal_recoveries': self_heal_recoveries, 'self_heal_attempts': self_heal_attempts, 'blocked_slots': blocked_slots, 'social_enqueued': social_enqueued, 'stats_before': stats}
    state.setdefault('history', []).append(run)
    write_json(STATE_PATH, state)
    write_json(REPORT_DIR/'v4-autopilot-report.json', {'status': 'ok', 'run': run, 'generated': generated, 'published': published, 'scaling_policy': SCALING})
    print(json.dumps({'status': 'ok', 'run': run}, indent=2))

if __name__ == '__main__':
    main()
