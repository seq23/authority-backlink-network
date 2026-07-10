#!/usr/bin/env python3
"""Write a full link audit and fail if outbound links violate the registry."""
import json
import html
import pathlib
import re
import sys
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
brands = json.loads((ROOT / 'data/brands.json').read_text())
publications = json.loads((ROOT / 'data/publications.json').read_text())

def norm_domain(url_or_domain: str) -> str:
    host = urlparse(url_or_domain).netloc if url_or_domain.startswith('http') else url_or_domain
    return host.lower().replace('www.', '').strip('/')

allowed_targets_by_pub = {}
for b in brands:
    for pub in b['approved_publications']:
        allowed_targets_by_pub.setdefault(pub, set()).add(norm_domain(b['domain']))

pub_by_folder = {p['folder']: p['id'] for p in publications}
publication_domains = {norm_domain(p['working_domain']) for p in publications}
target_domains = {norm_domain(b['domain']) for b in brands}
brand_by_domain = {norm_domain(b['domain']): b for b in brands}
approved_urls_by_domain = {norm_domain(b['domain']): {link.get('url','').rstrip('/') for link in b.get('approved_links', [])} for b in brands}
approval_product_by_url = {link.get('url','').rstrip('/'): link for link in brand_by_domain.get('approvalprep.com', {}).get('approved_links', [])}
allowed_external_domains = publication_domains | target_domains | {'schema.org'}

links = []
errors = []
anchor_re = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
for path in sorted((ROOT / 'sites').rglob('*.html')):
    rel = str(path.relative_to(ROOT))
    folder = '/'.join(rel.split('/')[:2])
    pub = pub_by_folder.get(folder)
    text = path.read_text(errors='ignore')
    for m in anchor_re.finditer(text):
        href = m.group(1)
        anchor = re.sub('<.*?>', '', m.group(2)).strip()
        domain = norm_domain(href) if href.startswith('http') else ''
        record = {'source': rel, 'publication': pub, 'href': href, 'domain': domain, 'anchor': anchor}
        if href.startswith('http'):
            record['external'] = True
            if domain not in allowed_external_domains:
                record['violation'] = 'external_domain_not_in_registry'
                errors.append(record)
            elif domain in target_domains and domain not in allowed_targets_by_pub.get(pub, set()):
                record['violation'] = 'target_domain_wrong_publication_lane'
                errors.append(record)
            elif domain == 'approvalprep.com' and href.rstrip('/') not in approved_urls_by_domain.get(domain, set()):
                record['violation'] = 'approval_prep_destination_not_approved'
                errors.append(record)
            elif domain in target_domains and href.rstrip('/') not in approved_urls_by_domain.get(domain, set()):
                record['violation'] = 'legacy_destination_not_in_current_approved_set_warning'
            else:
                record['violation'] = ''
        else:
            record['external'] = False
            record['violation'] = ''
        links.append(record)

# New-schema published ledger records must match exact HTML evidence.
ledger_path = ROOT / 'data/link-registry.json'
ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
ledger = ledger.get('links', []) if isinstance(ledger, dict) else ledger
new_records = [r for r in ledger if r.get('status') == 'published' and r.get('target_brand_id')]
for row in new_records:
    source = ROOT / row.get('source_path', '')
    if not source.exists():
        errors.append({'source': row.get('source_path'), 'violation': 'published_ledger_source_missing'})
        continue
    text = source.read_text(errors='ignore')
    href = row.get('target_url', '')
    anchor = row.get('anchor', '')
    if href not in text or anchor not in html.unescape(text):
        errors.append({'source': row.get('source_path'), 'href': href, 'anchor': anchor, 'violation': 'published_ledger_does_not_match_html'})
    brand = brand_by_domain.get(norm_domain(row.get('target_domain','')))
    if not brand or row.get('target_brand_id') != brand.get('id'):
        errors.append({'source': row.get('source_path'), 'violation': 'published_ledger_brand_domain_mismatch'})
    if norm_domain(row.get('target_domain','')) == 'approvalprep.com':
        meta = approval_product_by_url.get(href.rstrip('/'))
        if not meta:
            errors.append({'source': row.get('source_path'), 'href': href, 'violation': 'approval_prep_product_metadata_missing'})
        elif row.get('product_id') and row.get('product_id') != meta.get('product_id'):
            errors.append({'source': row.get('source_path'), 'href': href, 'violation': 'approval_prep_ledger_product_id_mismatch'})
        elif row.get('destination_type') and row.get('destination_type') != meta.get('destination_type'):
            errors.append({'source': row.get('source_path'), 'href': href, 'violation': 'approval_prep_ledger_destination_type_mismatch'})

# Every generated Approval Prep link must have a new-schema ledger record.
ledger_keys = {(r.get('source_path'), r.get('target_url'), r.get('anchor')) for r in new_records}
for record in links:
    if record.get('domain') == 'approvalprep.com':
        key = (record.get('source'), record.get('href'), record.get('anchor'))
        if key not in ledger_keys:
            errors.append({**record, 'violation': 'approval_prep_html_link_missing_ledger_record'})

report = {'status': 'PASS' if not errors else 'FAIL', 'total_links': len(links), 'violations': errors, 'links': links}
(ROOT / 'reports').mkdir(exist_ok=True)
(ROOT / 'reports/link-audit.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'status': report['status'], 'total_links': len(links), 'violations': len(errors)}, indent=2))
if errors:
    sys.exit(1)
