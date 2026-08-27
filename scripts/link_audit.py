#!/usr/bin/env python3
"""Audit outbound links against multi-domain brand and product-route registries."""
import json, html, pathlib, re, sys
from urllib.parse import urlparse
ROOT=pathlib.Path(__file__).resolve().parents[1]
brands=json.loads((ROOT/'data/brands.json').read_text())
publications=json.loads((ROOT/'data/publications.json').read_text())
city_data=json.loads((ROOT/'data/city-publications.json').read_text()) if (ROOT/'data/city-publications.json').exists() else {'cities':[]}

def norm_domain(value):
    host=urlparse(value).netloc if str(value).startswith('http') else str(value)
    return host.lower().replace('www.','').strip('/')
def brand_domains(b): return {norm_domain(x) for x in (b.get('domains') or [b.get('domain','')]) if x}
def approved_links(b): return {x.get('url','').rstrip('/'):x for x in b.get('approved_links',[])}

brand_by_domain={}; errors=[]
for b in brands:
    for d in brand_domains(b):
        if d in brand_by_domain and brand_by_domain[d]['id']!=b['id']:
            errors.append({'domain':d,'violation':'duplicate_domain_ownership'})
        brand_by_domain[d]=b
publication_domains={norm_domain(p['working_domain']) for p in publications}
target_domains=set(brand_by_domain)
# Verified outside authorities (data/external-sources.json). These are editorial
# citations, not affiliated placements: they are deliberately outside
# `affiliated_all`, so the sponsored+nofollow requirement below does not and must
# not apply to them. Each cited URL still has to be one the registry verified.
external_sources=json.loads((ROOT/'data/external-sources.json').read_text())
external_source_urls={s['url'].rstrip('/'):s for s in external_sources['sources']}
external_source_domains={norm_domain(s['url']) for s in external_sources['sources']}
external_source_lanes={}
for _s in external_sources['sources']:
    external_source_lanes.setdefault(norm_domain(_s['url']),set()).update(_s['lanes'])
allowed_external=publication_domains|target_domains|external_source_domains|{'schema.org'}
allowed_by_pub={}
for b in brands:
    for pub in b.get('approved_publications',[]): allowed_by_pub.setdefault(pub,set()).update(brand_domains(b))
pub_by_folder={p['folder']:p['id'] for p in publications}
active_cities={c['id'] for c in city_data.get('cities',[]) if c.get('status')=='active'}
affiliated_all={d for b in brands for d in brand_domains(b)}
links=[]
# Capture the whole opening tag, not just href and inner HTML, so rel is
# inspectable. Without the tag we cannot tell a followed affiliated link from
# a nofollowed one, which is the entire point of the sponsored-nofollow rule.
anchor_re=re.compile(r'<a\s+([^>]*?href="([^"]+)"[^>]*?)>(.*?)</a>',re.I|re.S)
for path in sorted((ROOT/'sites').rglob('*.html')):
    rel=str(path.relative_to(ROOT)); folder='/'.join(rel.split('/')[:2]); pub=pub_by_folder.get(folder); text=path.read_text(errors='ignore')
    if '/agency/' in '/' + rel or re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', text, re.I):
        continue
    for open_tag,href,anchor_html in anchor_re.findall(text):
        anchor=re.sub('<.*?>','',anchor_html).strip(); domain=norm_domain(href) if href.startswith('http') else ''
        row={'source':rel,'publication':pub,'href':href,'domain':domain,'anchor':anchor,'external':href.startswith('http'),'violation':''}
        if row['external']:
            if domain not in allowed_external: row['violation']='external_domain_not_in_registry'; errors.append(row)
            elif domain in external_source_domains:
                if href.rstrip('/') not in external_source_urls:
                    row['violation']='external_source_url_not_verified'; errors.append(row)
                elif pub not in external_source_lanes[domain]:
                    row['violation']='external_source_wrong_publication_lane'; errors.append(row)
            elif domain in target_domains and domain not in allowed_by_pub.get(pub,set()): row['violation']='target_domain_wrong_publication_lane'; errors.append(row)
            elif domain in target_domains:
                brand=brand_by_domain[domain]; meta=approved_links(brand).get(href.rstrip('/'))
                if not meta:
                    row['violation']='destination_not_in_approved_set'; errors.append(row)
                elif meta.get('product_id') and meta.get('route'):
                    expected=meta.get('route','')
                    if urlparse(href).path.rstrip('/') != expected.rstrip('/'):
                        row['violation']='product_route_mismatch'; errors.append(row)
        if row['external'] and domain in allowed_external and not row['violation']:
            rel_tokens = set()
            m_rel = re.search(r'rel="([^"]*)"', open_tag, re.I)
            if m_rel: rel_tokens = {t.lower() for t in m_rel.group(1).split()}
            if domain in affiliated_all and not {'sponsored','nofollow'} <= rel_tokens:
                row['violation']='affiliated_link_missing_sponsored_nofollow'; errors.append(row)
        links.append(row)

ledger_path=ROOT/'data/link-registry.json'; ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else []
ledger=ledger.get('links',[]) if isinstance(ledger,dict) else ledger
published=[r for r in ledger if r.get('status')=='published' and r.get('target_brand_id')]
ledger_keys={(r.get('source_path'),r.get('target_url'),r.get('anchor')) for r in published}
for r in published:
    source=ROOT/r.get('source_path','')
    if not source.exists(): errors.append({'source':r.get('source_path'),'violation':'published_ledger_source_missing'}); continue
    text=source.read_text(errors='ignore'); href=r.get('target_url',''); anchor=r.get('anchor',''); domain=norm_domain(href or r.get('target_domain',''))
    if href not in text or anchor not in html.unescape(text): errors.append({'source':r.get('source_path'),'href':href,'violation':'published_ledger_does_not_match_html'})
    brand=brand_by_domain.get(domain)
    if not brand or r.get('target_brand_id')!=brand.get('id'): errors.append({'source':r.get('source_path'),'violation':'published_ledger_brand_domain_mismatch'})
    elif href:
        meta=approved_links(brand).get(href.rstrip('/'))
        if not meta: errors.append({'source':r.get('source_path'),'href':href,'violation':'product_metadata_missing'})
        else:
            for field in ('product_id','destination_type'):
                if r.get(field) and r.get(field)!=meta.get(field): errors.append({'source':r.get('source_path'),'href':href,'violation':f'ledger_{field}_mismatch'})
            if r.get('target_route') and r.get('target_route')!=meta.get('route'): errors.append({'source':r.get('source_path'),'href':href,'violation':'ledger_route_mismatch'})
for row in links:
    if row.get('domain') in target_domains and brand_by_domain[row['domain']].get('id')=='dream-wedding-builder':
        if (row['source'],row['href'],row['anchor']) not in ledger_keys:
            # Existing hand-authored pages are allowed until first generated wedding publication.
            if '/daily/' in row['source']: errors.append({**row,'violation':'wedding_html_link_missing_ledger_record'})
report={'status':'PASS' if not errors else 'FAIL','total_links':len(links),'violations':errors,'target_domains':sorted(target_domains),'links':links}
(ROOT/'reports').mkdir(exist_ok=True); (ROOT/'reports/link-audit.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'status':report['status'],'total_links':len(links),'violations':len(errors)},indent=2))
if errors: sys.exit(1)
