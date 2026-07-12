#!/usr/bin/env python3
"""Authority Network v4.6 portfolio citation control plane.

Read-only verification and reporting by default. It never upgrades a link to live/indexed/cited
without explicit evidence supplied by a deployment or observation process.
"""
from __future__ import annotations
import argparse, json, re, urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]

def read(path, default):
    p=ROOT/path
    return json.loads(p.read_text()) if p.exists() else default

def write(path,data):
    p=ROOT/path; p.parent.mkdir(parents=True,exist_ok=True); tmp=p.with_suffix(p.suffix+'.tmp'); tmp.write_text(json.dumps(data,indent=2)+'\n'); tmp.replace(p)

def norm_domain(v):
    host=urlparse(v).netloc if str(v).startswith('http') else str(v)
    return host.lower().replace('www.','').strip('/')

def verify_repo():
    links=read('data/link-registry.json',[]); brands=read('data/brands.json',[]); pubs=read('data/publications.json',[])
    brand_ids={b['id'] for b in brands}; pub_ids={p['id'] for p in pubs}; failures=[]; warnings=[]; rendered=0
    for i,x in enumerate(links):
        bid=x.get('target_brand_id')
        if bid and bid not in brand_ids: failures.append(f'link[{i}] unknown brand {bid}')
        srcpub=x.get('source_publication') or x.get('publication')
        if srcpub and srcpub not in pub_ids and srcpub not in {'founder-operator','memphis-local','professional-resources'}: warnings.append(f'link[{i}] legacy publication id {srcpub}')
        if x.get('status')=='published':
            src=x.get('source_path')
            if not src or not (ROOT/src).exists(): failures.append(f'link[{i}] published source missing: {src}') ; continue
            text=(ROOT/src).read_text(errors='ignore')
            url=x.get('target_url') or ''
            if url and url not in text: failures.append(f'link[{i}] target URL not rendered in source: {url}')
            else: rendered+=1
        ev=x.get('evidence',{})
        if ev.get('indexed') and not ev.get('live_verified'): failures.append(f'link[{i}] indexed without live verification')
        if ev.get('ai_cited') and not ev.get('discoverable'): warnings.append(f'link[{i}] AI citation evidence should include discoverability context')
    receipt={'schema':'authority-citation-control-v1','status':'FAIL' if failures else ('PASS_WITH_SOFT_WARNING' if warnings else 'PASS'),'hard_failures':len(failures),'strong_warnings':0,'soft_warnings':len(warnings),'rendered_links_verified':rendered,'failures':failures,'warnings':warnings}
    write('reports/citation-control-verification.json',receipt); print(json.dumps(receipt,indent=2)); raise SystemExit(1 if failures else 0)

def dashboard():
    links=read('data/link-registry.json',[]); brands=read('data/brands.json',[]); pubs=read('data/publications.json',[]); profiles=read('data/brand-growth-profiles.json',{}).get('profiles',[]); manifests=read('data/product-repo-manifests.json',{}).get('repos',[])
    by_brand=Counter(); by_domain=Counter(); by_pub=Counter(); lifecycle=Counter(); evidence=Counter(); approved=0
    for x in links:
        if x.get('status')=='approved_target_not_auto_published': approved+=1; continue
        if x.get('status') in {'published','rendered','live_verified','discoverable','indexed'}:
            by_brand[x.get('target_brand_id') or x.get('brand','unknown')]+=1; by_domain[norm_domain(x.get('target_url') or x.get('target_domain',''))]+=1; by_pub[x.get('source_publication') or x.get('publication') or 'unknown']+=1
        lifecycle[x.get('lifecycle_stage') or x.get('status','unknown')]+=1
        for k,v in (x.get('evidence') or {}).items():
            if v: evidence[k]+=1
    surface_by_brand={m['brand_id']:len(m.get('surfaces',[])) for m in manifests}
    profile_map={p['brand_id']:p for p in profiles}
    rows=[]
    for b in brands:
        bid=b['id']; p=profile_map.get(bid,{})
        rows.append({'brand_id':bid,'brand_name':b['name'],'growth_status':p.get('growth_status','unconfigured'),'authority_backlinks':by_brand.get(bid,0),'owned_manifest_surfaces':surface_by_brand.get(bid,0),'monthly_authority_target':p.get('target_authority_pages_per_month'),'monthly_verified_backlink_target':p.get('target_verified_backlinks_per_month'),'target_variance_blocks_release':False})
    objective=read('content-bank/scaling-policy.json',{}).get('portfolio_citation_objective',{})
    dash={'schema':'authority-portfolio-dashboard-v1','as_of':date.today().isoformat(),'objective':objective,'definitions':{'authority_backlinks':'Repository-rendered outbound links recorded in the Authority Network ledger.','owned_manifest_surfaces':'Canonical surfaces reported by product repositories.','live_verified':'Observed at the deployed publication URL.','indexed':'Evidence-backed index observation only.','citation_impression_objective':'Combined opportunity metric; not a claim of 100,000 independent backlinks.'},'totals':{'registered_brands':len(brands),'authority_publications':len(pubs),'authority_backlinks':sum(by_brand.values()),'approved_destinations_waiting_for_context':approved,'owned_manifest_surfaces':sum(surface_by_brand.values()),'live_verified':evidence.get('live_verified',0),'discoverable':evidence.get('discoverable',0),'indexed':evidence.get('indexed',0),'ai_cited':evidence.get('ai_cited',0)},'by_brand':rows,'by_domain':dict(by_domain),'by_publication':dict(by_pub),'lifecycle':dict(lifecycle)}
    write('reports/citation-portfolio-dashboard.json',dash)
    lines=['# Authority Network Citation Portfolio Dashboard','',f"As of: {dash['as_of']}",'',f"- Registered brands: {len(brands)}",f"- Authority publications: {len(pubs)}",f"- Repository-rendered authority backlinks: {sum(by_brand.values())}",f"- Owned product-repo surfaces imported: {sum(surface_by_brand.values())}",f"- Live verified backlinks: {evidence.get('live_verified',0)}",f"- Indexed referring pages with evidence: {evidence.get('indexed',0)}",'', '## By brand','', '| Brand | Status | Authority backlinks | Owned surfaces | Monthly authority target |','|---|---:|---:|---:|---:|']
    for r in rows: lines.append(f"| {r['brand_name']} | {r['growth_status']} | {r['authority_backlinks']} | {r['owned_manifest_surfaces']} | {r['monthly_authority_target']} |")
    (ROOT/'reports/citation-portfolio-dashboard.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'status':'PASS','report':'reports/citation-portfolio-dashboard.json','authority_backlinks':sum(by_brand.values()),'brands':len(brands)},indent=2))

def import_manifests():
    reg=read('data/product-repo-manifests.json',{}); imported=0; warnings=[]
    for repo in reg.get('repos',[]):
        url=repo.get('manifest_url','').strip()
        if not url: continue
        try:
            with urllib.request.urlopen(url,timeout=20) as r: data=json.loads(r.read().decode())
            surfaces=data.get('surfaces',data if isinstance(data,list) else [])
            valid=[]
            for s in surfaces:
                if isinstance(s,dict) and s.get('canonical_url') and s.get('topic'): valid.append(s)
            repo['surfaces']=valid; repo['status']='imported'; repo['last_imported_at']=date.today().isoformat(); imported+=len(valid)
        except Exception as e:
            warnings.append(f"{repo.get('brand_id')}: {str(e)[:120]}")
    write('data/product-repo-manifests.json',reg)
    print(json.dumps({'status':'PASS_WITH_SOFT_WARNING' if warnings else 'PASS','imported_surfaces':imported,'warnings':warnings},indent=2))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('command',choices=['verify-repo','dashboard','import-manifests']); a=ap.parse_args(); {'verify-repo':verify_repo,'dashboard':dashboard,'import-manifests':import_manifests}[a.command]()
if __name__=='__main__': main()
