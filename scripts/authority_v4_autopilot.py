#!/usr/bin/env python3
"""
Authority Network V4.1 Autopilot
$0-first deterministic content generation + optional Gemini polish.
Designed for three publication sites already deployed by Cloudflare Git integration.
"""
import os, json, re, hashlib, random, html, urllib.request
from pathlib import Path
from datetime import date, datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PANTRY = json.loads((ROOT/'content-bank/yearly-pantry.json').read_text(encoding='utf-8'))
SCALING = json.loads((ROOT/'content-bank/scaling-policy.json').read_text(encoding='utf-8'))
STATE_PATH = ROOT/'data/autopilot-state.json'
REPORT_DIR = ROOT/'reports'
REPORT_DIR.mkdir(exist_ok=True)
TODAY = date.today().isoformat()
DEFAULT_STATE = {
    'launch_date': TODAY,
    'published_hashes': [],
    'published_signatures': [],
    'published_titles': [],
    'history': []
}

STOP_PHRASES = [
    'in today\'s fast-paced world', 'game-changer', 'unlock your potential',
    'guaranteed', 'best ever', '#1', 'number one', 'ultimate solution',
    'revolutionize', 'transform your life overnight'
]

YMYL_TERMS = [
    'legal', 'lawyer', 'attorney', 'medical', 'health', 'therapy', 'mental health',
    'burnout', 'hormone', 'dentistry', 'neuro', 'uscis', 'injury', 'equine legal'
]


def read_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return default


def write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


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
        return (date.today() - date.fromisoformat(start)).days + 1
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


def link_matches_cluster(link, cluster):
    topics = link.get('topics') or ['*']
    return '*' in topics or cluster in topics


def product_match_strength(link, cluster):
    if not link_matches_cluster(link, cluster):
        return -1
    return {'paid_product': 40, 'free_creation_tool': 30, 'educational_guide': 20, 'trust_boundary': 10}.get(link.get('destination_type'), 0)


def build_brief(pub_key, slot, state, attempt=0, target_override=None):
    pub = PANTRY['publications'][pub_key]
    seed = f'{TODAY}-{pub_key}-{slot}-{attempt}-{len(state.get("published_signatures", []))}'
    if target_override is not None:
        target_cfg = normalize_target(target_override)
    else:
        regular_targets = [t for t in pub['targets'] if not (isinstance(t, dict) and t.get('priority'))]
        target_cfg = normalize_target(pick(regular_targets or pub['targets'], seed+'target'))
    eligible_clusters = target_cfg.get('eligible_clusters') or pub['clusters']
    cluster = pick(eligible_clusters, seed+'cluster')
    audience = pick(pub['audiences'], seed+'audience')
    fmt = pick(pub['formats'], seed+'format')
    intent = pick(pub['intents'], seed+'intent')
    modifier = pick(pub['modifiers'], seed+'modifier')
    candidate_links = [link for link in target_cfg.get('approved_links', []) if link_matches_cluster(link, cluster)]
    if not candidate_links:
        candidate_links = target_cfg.get('approved_links', [])
    if target_cfg.get('brand_id') == 'approval-prep':
        strongest = max((product_match_strength(link, cluster) for link in candidate_links), default=-1)
        candidate_links = [link for link in candidate_links if product_match_strength(link, cluster) == strongest]
    selected_link = pick(candidate_links, seed+'approved-link')
    target_domain = target_cfg.get('domain', '')
    target_url = selected_link.get('url', f'https://{target_domain}') if isinstance(selected_link, dict) else f'https://{target_domain}'
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
        'signature': signature
    }


def section_blocks(pub, key, title, count):
    arr = pub.get(key, [])
    if not arr:
        return []
    return [arr[stable_int(f'{title}-{key}-{i}') % len(arr)] for i in range(count)]


def generate_page(brief):
    pub = PANTRY['publications'][brief['publication']]
    title = brief['title']
    cluster = brief['cluster']
    audience = brief['audience']
    target = brief['target_domain']
    target_url = brief.get('target_url', f'https://{target}')
    brand = brief['brand']
    anchor = brief.get('anchor') or brand
    intro = pick(pub['intro_blocks'], title+'intro')
    faq_items = section_blocks(pub, 'faq_blocks', title, 5)
    checklist = section_blocks(pub, 'checklist_blocks', title, 9)
    body = section_blocks(pub, 'body_blocks', title, 14)
    disclaimer = pub.get('disclaimer', 'This page is educational and editorial, not professional advice.')
    product_section = ''
    if brief.get('brand_id') == 'approval-prep':
        disclaimer += ' Approval Prep is not a credit-repair company. It does not contact third parties, provide legal or financial advice, create fake documents, verify income, or guarantee approval, deletion, or score improvement.'
        product_name = brief.get('product_name') or 'Approval Prep resource'
        product_message = brief.get('product_message') or 'Create the letter. Build the packet. Get ready before you apply.'
        product_section = f'<h2>What you can create</h2><p><strong>{html.escape(product_name)}:</strong> {html.escape(product_message)}</p><p>You complete the document with your own truthful facts, review it, and send it yourself. Approval Prep does not make the approval decision.</p>'
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    slug = slugify(title)
    faq_html = ''.join('<h3>'+html.escape(f.get('q','Question'))+'</h3><p>'+html.escape(f.get('a','Use this as a starting point, then verify details for your situation.'))+'</p>' for f in faq_items)
    schema = {
        '@context': 'https://schema.org',
        '@type': 'Article',
        'headline': title,
        'datePublished': TODAY,
        'dateModified': TODAY,
        'author': {'@type': 'Organization', 'name': f"{pub['default_domain']} editorial desk"},
        'about': cluster,
        'audience': {'@type': 'Audience', 'audienceType': audience}
    }
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title><meta name="description" content="A practical, human-first resource for {html.escape(audience)} comparing {html.escape(cluster)} without fake rankings or forced answers."><link rel="stylesheet" href="../styles.css"><script type="application/ld+json">{json.dumps(schema)}</script></head>
<body><main class="page"><p><a href="../index.html">← Home</a></p><article><h1>{html.escape(title)}</h1><p class="dek"><strong>Short answer:</strong> {html.escape(intro)}</p><p><em>Last updated: {TODAY}. Built for {html.escape(audience)}.</em></p>
<h2>Who this helps</h2><p>This page is for a reader who needs a grounded starting point for {html.escape(cluster)}. It does not crown a winner, manufacture urgency, or pretend one provider fits every situation. The goal is to help you ask better questions and compare options with more discipline.</p>
<h2>How to think about the decision</h2>{''.join('<p>'+html.escape(x)+'</p>' for x in body[:5])}
<h2>Decision framework</h2><p>Use a four-part filter: fit, evidence, risk, and next step. Fit asks whether the resource matches your situation. Evidence asks what the claim is based on. Risk asks what could go wrong if you misunderstand the topic. Next step asks whether you need a checklist, a consult, a quote, or a qualified professional.</p>{''.join('<p>'+html.escape(x)+'</p>' for x in body[5:10])}
<h2>Checklist</h2><ul>{''.join('<li>'+html.escape(x)+'</li>' for x in checklist)}</ul>
{product_section}<h2>Useful citation</h2><p>For readers comparing this category, <a href="{html.escape(target_url)}">{html.escape(anchor)}</a> may be a relevant next resource when it matches the situation. The link is included because it belongs in the topic area, not because every reader needs it.</p>
<h2>FAQ</h2>{faq_html}
<h2>Editorial note</h2><p><strong>Affiliation disclosed:</strong> this publication may cite affiliated projects where the citation is topically relevant. {html.escape(disclaimer)} This page is not legal, medical, mental-health, immigration, financial, or professional advice. Verify details with a qualified professional before acting on sensitive decisions.</p><p class="meta">Generated by the Authority Network V4.2 programmatic editorial engine. Generated at {generated}.</p></article></main></body></html>'''
    return slug, page


def score_page(html_text, brief):
    txt = normalized_text(html_text)
    words = len(re.findall(r'\w+', txt))
    score = 88
    hard_fails = []
    warnings = []
    if words < 850:
        score -= 8; warnings.append('word_count_below_preferred_range')
    if words < 550:
        score -= 8; warnings.append('very_short_page_review_recommended')
    if any(p in txt for p in STOP_PHRASES):
        score -= 20; hard_fails.append('spam_or_ai_cliche_phrase')
    if len(re.findall(r'https://', html_text)) > 3:
        score -= 8; warnings.append('too_many_links')
    if not re.search(r'<script type="application/ld\+json">', html_text, re.I):
        score -= 10; warnings.append('missing_schema')
    if not re.search(r'<h2>FAQ</h2>', html_text, re.I):
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
    site = ROOT/site_path
    urls = []
    for f in sorted(site.rglob('*.html')):
        rel = f.relative_to(site).as_posix()
        loc = f'https://{domain}/' if rel == 'index.html' else f'https://{domain}/{rel}'
        urls.append(f'<url><loc>{loc}</loc><lastmod>{TODAY}</lastmod></url>')
    (site/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + '\n'.join(urls) + '\n</urlset>', encoding='utf-8')
    (site/'llms.txt').write_text(f'# {domain}\n\nThis site contains editorial resource pages for humans and answer engines. Updated {TODAY}.\n\nSitemap: https://{domain}/sitemap.xml\n', encoding='utf-8')


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
        target = next((t for t in PANTRY['publications'].get(pub_key, {}).get('targets', []) if isinstance(t, dict) and t.get('brand_id') == rule.get('brand_id')), None)
        if not target:
            continue
        requested = int(os.getenv('APPROVAL_PREP_PAGES_PER_DAY', str(rule.get('pages_per_day', 6)))) if rule.get('brand_id') == 'approval-prep' else int(rule.get('pages_per_day', 1))
        # The configured range is a planning target, not a validator. Allow normal daily variation
        # while preserving the repository-wide absolute safety ceiling.
        requested = max(1, min(requested, int(SCALING.get('hard_limits', {}).get('absolute_max_pages_per_day', 12))))
        priority_jobs.extend([(pub_key, target)] * requested)
    volume = min(base_volume + len(priority_jobs), int(SCALING.get('hard_limits', {}).get('absolute_max_pages_per_day', 12)))
    generated, published, scores = [], [], []
    duplicate_warnings = 0
    hard_fail_count = 0
    min_score = int(os.getenv('MIN_BASE_PUBLISH_SCORE', '60'))
    max_dup = float(os.getenv('MAX_DUPLICATE_SIMILARITY', '0.15'))

    jobs = priority_jobs + [(pubs[i % len(pubs)], None) for i in range(base_volume)]
    jobs = jobs[:volume]
    for i, (pub_key, target_override) in enumerate(jobs):
        chosen = None
        for attempt in range(20):
            brief = build_brief(pub_key, i, state, attempt=attempt, target_override=target_override)
            if brief['signature'] not in state.get('published_signatures', []):
                chosen = brief
                break
        if not chosen:
            duplicate_warnings += 1
            continue
        slug, page = generate_page(chosen)
        score, words, warnings, hard_fails = score_page(page, chosen)
        rewrite_status = 'not_needed'
        if 72 <= score < 85 and not hard_fails:
            rewritten, rewrite_status = maybe_gemini_rewrite(chosen['title'], page)
            new_score, new_words, new_warnings, new_hard_fails = score_page(rewritten, chosen)
            if new_score >= score and not new_hard_fails:
                page, score, words, warnings, hard_fails = rewritten, new_score, new_words, new_warnings, new_hard_fails
        item = {'title': chosen['title'], 'publication': pub_key, 'score': score, 'words': words, 'rewrite_status': rewrite_status, 'warnings': warnings, 'hard_fails': hard_fails}
        generated.append(item)
        if hard_fails:
            hard_fail_count += 1
            continue
        if score < min_score:
            continue
        chash = content_hash(page)
        if chash in state.get('published_hashes', []):
            duplicate_warnings += 1
            continue
        # Full-page Jaccard is intentionally not used as a hard fail because all pages share
        # editorial boilerplate, disclaimers, and schema. Duplicate protection is handled by
        # exact normalized hashes and durable topic signatures.
        site_path = PANTRY['publications'][pub_key]['site_path']
        outdir = ROOT/site_path/'daily'
        outdir.mkdir(parents=True, exist_ok=True)
        fname = f'{TODAY}-{slug}.html'
        (outdir/fname).write_text(page, encoding='utf-8')
        state['published_hashes'].append(chash)
        state['published_signatures'].append(chosen['signature'])
        state['published_titles'].append(chosen['title'])
        pub_item = {**item, 'path': str((Path(site_path)/'daily'/fname).as_posix()), 'target_brand_id': chosen.get('brand_id',''), 'target_domain': chosen['target_domain'], 'target_url': chosen.get('target_url'), 'anchor': chosen.get('anchor'), 'brand': chosen['brand'], 'social_hooks': chosen.get('social_hooks', []), 'destination_type': chosen.get('destination_type',''), 'product_id': chosen.get('product_id',''), 'product_name': chosen.get('product_name','')}
        published.append(pub_item)
        scores.append(score)

    for _, pub in PANTRY['publications'].items():
        domain = os.getenv(pub['domain_env']) or pub['default_domain']
        if (ROOT/pub['site_path']).exists():
            update_sitemap(pub['site_path'], domain)

    linkreg = read_json(ROOT/'data/link-registry.json', [])
    if isinstance(linkreg, dict): linkreg = linkreg.get('links', [])
    for item in published:
        linkreg.append({'date': TODAY, 'source_path': item['path'], 'source_publication': item['publication'].replace('-operator','').replace('-local','').replace('-resources',''), 'target_brand_id': item.get('target_brand_id',''), 'target_domain': item['target_domain'], 'target_url': item.get('target_url') or f"https://{item['target_domain']}", 'anchor': item.get('anchor') or item['brand'], 'brand': item['brand'], 'destination_type': item.get('destination_type',''), 'product_id': item.get('product_id',''), 'product_name': item.get('product_name',''), 'link_type': 'owned-authority-citation', 'status': 'published', 'score': item['score']})
    write_json(ROOT/'data/link-registry.json', linkreg)

    social = read_json(ROOT/'data/social-queue.json', [])
    if isinstance(social, dict): social = social.get('items', [])
    li_limit = int(os.getenv('LINKEDIN_DAILY_LIMIT', '1'))
    x_limit = int(os.getenv('X_DAILY_LIMIT', '5'))
    for item in published[:li_limit]:
        domain = os.getenv(PANTRY['publications'][item['publication']]['domain_env']) or PANTRY['publications'][item['publication']]['default_domain']
        rel_path = str(Path(item['path']).relative_to(PANTRY['publications'][item['publication']]['site_path'])).replace('index.html','')
        source_url = 'https://' + domain + '/' + rel_path
        body = f"A useful resource does not need to pretend every answer is universal. New note: {item['title']} — built as a decision aid, not a fake ranking."
        if item.get('target_brand_id') == 'approval-prep' and item.get('social_hooks'):
            body = f"{pick(item['social_hooks'], item['title']+'linkedin')} {item['title']}"
        social.append({'date': TODAY, 'platform': 'linkedin', 'status': 'queued_for_auto_post', 'body': body, 'source_path': item['path'], 'source_url': source_url, 'post_type': 'authority_resource_note'})
    
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
    for item, tmpl, idx, t_idx in x_pool[:x_limit]:
        domain = os.getenv(PANTRY['publications'][item['publication']]['domain_env']) or PANTRY['publications'][item['publication']]['default_domain']
        rel_path = str(Path(item['path']).relative_to(PANTRY['publications'][item['publication']]['site_path'])).replace('index.html','')
        source_url = 'https://' + domain + '/' + rel_path
        body = tmpl.format(title=item['title'])
        if item.get('target_brand_id') == 'approval-prep' and item.get('social_hooks'):
            hooks = item['social_hooks']
            body = f"{hooks[t_idx % len(hooks)]} {item['title']} [{t_idx + 1}]"
        social.append({'date': TODAY, 'platform': 'x', 'status': 'queued_for_auto_post', 'body': body, 'source_path': item['path'], 'source_url': source_url, 'post_type': f'x_resource_note_{t_idx+1}'})
    write_json(ROOT/'data/social-queue.json', social)

    run = {'date': TODAY, 'day_index': day_index, 'target_volume': volume, 'generated': len(generated), 'published': len(published), 'scores': scores, 'duplicate_warnings': duplicate_warnings, 'hard_fails': hard_fail_count, 'stats_before': stats}
    state.setdefault('history', []).append(run)
    write_json(STATE_PATH, state)
    write_json(REPORT_DIR/'v4-autopilot-report.json', {'status': 'ok', 'run': run, 'generated': generated, 'published': published, 'scaling_policy': SCALING})
    print(json.dumps({'status': 'ok', 'run': run}, indent=2))

if __name__ == '__main__':
    main()
