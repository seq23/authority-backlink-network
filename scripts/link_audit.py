#!/usr/bin/env python3
"""Write a full link audit and fail if outbound links violate the registry."""
import json
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
allowed_external_domains = publication_domains | target_domains | {'schema.org'}

links = []
errors = []
anchor_re = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
for path in sorted((ROOT / 'sites').glob('*/*.html')):
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
            else:
                record['violation'] = ''
        else:
            record['external'] = False
            record['violation'] = ''
        links.append(record)

report = {'status': 'PASS' if not errors else 'FAIL', 'total_links': len(links), 'violations': errors, 'links': links}
(ROOT / 'reports').mkdir(exist_ok=True)
(ROOT / 'reports/link-audit.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'status': report['status'], 'total_links': len(links), 'violations': len(errors)}, indent=2))
if errors:
    sys.exit(1)
