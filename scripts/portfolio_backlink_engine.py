#!/usr/bin/env python3
"""Portfolio backlink campaign engine.

Creates useful, disclosure-backed Authority Network pages and records truthful lifecycle state.
It never marks a page deployed, indexed, cited, or independently earned without observation evidence.
"""
from __future__ import annotations
import argparse, hashlib, html, json, re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape

ROOT=Path(__file__).resolve().parents[1]

def read(rel,default=None):
 p=ROOT/rel
 return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default

def write(rel,obj):
 p=ROOT/rel; p.parent.mkdir(parents=True,exist_ok=True); tmp=p.with_suffix(p.suffix+'.tmp'); tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); tmp.replace(p)

def norm_domain(v): return urlparse(v).netloc.lower().replace('www.','')
def words(s): return len(re.findall(r"[A-Za-z0-9']+",re.sub('<[^>]+>',' ',s)))
def stable_id(*parts): return hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:20]

def publication_maps():
 pubs=read('data/publications.json',[])
 return {p['id']:p for p in pubs}, {p['folder'].split('/')[-1]:p for p in pubs}

def target_topic_context(article):
 for brand in read('data/brands.json',[]):
  if brand.get('id') != article.get('target_brand_id'): continue
  for item in brand.get('approved_links',[]):
   if item.get('url','').rstrip('/') == article.get('target_url','').rstrip('/'):
    topics=[x for x in item.get('topics',[]) if x and x != '*']
    if topics: return topics[0]
 return article.get('campaign_id','').replace('-',' ')

def paragraph_for_factor(factor:str,idx:int)->str:
 openers=[
  'This factor matters because it changes the work required after the initial decision.',
  'Treat this as an operating question rather than a cosmetic preference.',
  'The practical value is that it turns a vague goal into something a team can verify.',
  'This is where many plans become fragile: the responsibility is assumed but never assigned.',
  'A useful comparison asks how this factor behaves during ordinary weeks and during pressure.',
 ]
 closers=[
  'Write the decision down, name the owner, and identify the evidence that would cause a review.',
  'If the answer is unclear, pause the commitment and gather the missing information instead of filling the gap with optimism.',
  'The goal is not maximum complexity; it is enough clarity that another person could follow the decision later.',
  'A provider or internal team should be able to explain this in plain language without hiding behind jargon.',
  'Revisit it at a defined checkpoint rather than renegotiating it every time a new preference appears.',
 ]
 return f"<p><strong>{html.escape(factor)}</strong> {openers[idx%len(openers)]} {closers[idx%len(closers)]}</p>"

def render(article,pub):
 title=article['title']; direct=article['direct_answer']; target=article['target_url']; anchor=article['anchor']; today=article['date']; topic_context=target_topic_context(article)
 factors=''.join(paragraph_for_factor(x,i) for i,x in enumerate(article['decision_factors']))
 qlist=''.join(f'<li>{html.escape(x)}</li>' for x in article['questions'])
 mistakes=''.join(f'<li><strong>Mistake {i+1}:</strong> {html.escape(x)} A better response is to slow down, verify the missing fact, and record the decision boundary.</li>' for i,x in enumerate(article['mistakes']))
 steps=''.join(f'<li><strong>Step {i+1}:</strong> {html.escape(x)}</li>' for i,x in enumerate([
  'Define the real decision and the person it affects.',
  'Collect the minimum facts needed to compare options on the same basis.',
  'Separate required protections from preferences and nice-to-have features.',
  'Choose the smallest responsible next action and a review date.',
  'Preserve the notes, documents, and assumptions used to make the decision.',
 ]))
 faqs=[]
 for i,q in enumerate(article['questions'][:4]):
  faqs.append(f'<h3>{html.escape(q)}</h3><p>Use the question to request a specific, verifiable answer. Ask who owns the responsibility, what evidence supports the answer, what is excluded, and what changes if the situation becomes more complex. For regulated or sensitive matters, confirm the answer with the appropriate qualified professional.</p>')
 disclosure=pub['disclosure']+' '+article['disclaimer']+' This page is not legal, medical, mental-health, immigration, financial, or professional advice. <strong>Affiliation disclosed:</strong> this page is published by an affiliated authority network and includes one affiliated resource only where it directly supports the topic. It is not an independent award, ranking, review, or earned-media claim.'
 schema={'@context':'https://schema.org','@type':'Article','headline':title,'datePublished':today,'dateModified':today,'author':{'@type':'Organization','name':pub['title']},'publisher':{'@type':'Organization','name':pub['title']},'about':article['campaign_id'],'mainEntityOfPage':{'@type':'WebPage','@id':f"https://{pub['working_domain']}/daily/{today}-{article['slug']}.html"}}
 return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><meta name="description" content="A practical, answer-first guide to {html.escape(title.lower())}, with decision factors, questions, mistakes, and a transparent related resource."><link rel="canonical" href="https://{pub['working_domain']}/daily/{today}-{article['slug']}.html"><link rel="stylesheet" href="../styles.css"><script type="application/ld+json">{json.dumps(schema,ensure_ascii=False)}</script></head>
<body data-backlink-seed-id="{html.escape(article['id'])}"><main class="page"><p><a href="../index.html">← Home</a></p><article><h1>{html.escape(title)}</h1><p class="dek"><strong>Short answer:</strong> {html.escape(direct)}</p><p><em>Updated {today}. This article is designed to help a reader make a clearer decision, not to manufacture urgency or a ranking.</em></p>
<p class="topic-context"><strong>Topic context:</strong> {html.escape(topic_context)}.</p>
<h2>What this decision is really about</h2><p>{html.escape(direct)} The useful test is whether the plan still makes sense after responsibilities, exclusions, evidence, timing, and failure paths are visible. A polished promise is not enough; the operating details have to survive real-world use.</p><p>Start by writing the intended outcome in one sentence. Then identify the person who owns the decision, the people affected by it, the facts that are known, the facts still missing, and the point at which a qualified professional or provider must be consulted. This prevents a simple resource page from being mistaken for individualized advice.</p>
<h2>Decision factors to evaluate</h2>{factors}
<h2>Questions worth asking</h2><p>Ask the same core questions of every option so the answers can be compared honestly. Record the response rather than relying on memory or sales language.</p><ul>{qlist}</ul>
<h2>A simple five-step decision path</h2><ol>{steps}</ol><p>Do not skip the final documentation step. A decision becomes easier to maintain when the assumptions, exclusions, owner, and review date are visible. That record also makes it easier to repair the plan if circumstances change.</p>
<h2>Common mistakes</h2><ul>{mistakes}</ul>
<h2>How to use the related resource</h2><p>The following resource is included because it directly addresses this article’s decision area. Review its scope and boundaries before using it: <a href="{html.escape(target)}">{html.escape(anchor)}</a>. The link is an affiliated editorial reference, not an independent endorsement, ranking, or guarantee.</p><p>A useful next step is to compare the resource against the questions above. Confirm that the destination is current, that its stated purpose matches your situation, and that any legal, medical, financial, contractual, or clinical question is handled by an appropriately qualified person.</p>
<h2>Frequently asked questions</h2>{''.join(faqs)}
<h2>Editorial and affiliation note</h2><p>{disclosure}</p><p class="meta">Authority Network campaign: {html.escape(article['campaign_id'])}. Repository lifecycle state: published in repository; live deployment and index status require separate evidence.</p></article></main></body></html>'''

def refresh_assets():
 pubs,_=publication_maps()
 for pub in pubs.values():
  folder=ROOT/pub['folder']; domain=pub['working_domain']; pages=sorted(folder.rglob('*.html'))
  urls=[]; llms=[f"# {pub['title']}",pub['mission'],'',f"Sitemap: https://{domain}/sitemap.xml",'','## Pages']
  for p in pages:
   rel=p.relative_to(folder).as_posix(); url=f'https://{domain}/' if rel=='index.html' else f'https://{domain}/{rel}'
   urls.append(f'<url><loc>{escape(url)}</loc><lastmod>{date.today().isoformat()}</lastmod></url>'); llms.append(f'- {url}')
  sitemap='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+'\n'.join(urls)+'\n</urlset>\n'
  (folder/'sitemap.xml').write_text(sitemap,encoding='utf-8'); (folder/'llms.txt').write_text('\n'.join(llms)+'\n',encoding='utf-8')

def seed():
 data=read('data/backlink-seed-articles.json',{'articles':[]}); links=read('data/link-registry.json',[]); pubs,_=publication_maps(); existing={x.get('seed_article_id') for x in links}; made=[]
 for a in data['articles']:
  pub=pubs[a['publication']]; rel=f"{pub['folder']}/daily/{a['date']}-{a['slug']}.html"; path=ROOT/rel; page=render(a,pub)
  path.parent.mkdir(parents=True,exist_ok=True)
  if not path.exists() or path.read_text(encoding='utf-8')!=page: path.write_text(page,encoding='utf-8')
  if a['id'] not in existing:
   links.append({'id':'bl-'+stable_id(a['id'],a['target_url']),'date':a['date'],'seed_article_id':a['id'],'source_path':rel,'source_publication':a['publication'],'target_brand_id':a['target_brand_id'],'campaign_id':a['campaign_id'],'target_domain':norm_domain(a['target_url']),'target_url':a['target_url'],'anchor':a['anchor'],'brand':next((b['name'] for b in read('data/brands.json',[]) if b['id']==a['target_brand_id']),a['target_brand_id']),'link_type':'affiliated-editorial-backlink','status':'published','lifecycle_stage':'published_in_repository','score':92,'evidence':{'repository_rendered':True,'deployed':False,'live_verified':False,'discoverable':False,'indexed':False,'search_visibility_observed':False,'ai_cited':False},'truth_boundary':'Owned-network rendered backlink; not independent, live, indexed, or cited without evidence.'}); made.append(rel)
 write('data/link-registry.json',links); refresh_assets(); health()
 print(json.dumps({'status':'PASS','created_or_refreshed':len(data['articles']),'new_ledger_records':len(made),'pages':made},indent=2))

def local_findings(row):
 p=ROOT/row.get('source_path',''); findings=[]
 if not p.exists(): return ['source_missing']
 t=p.read_text(encoding='utf-8',errors='ignore');
 if row.get('target_url') not in t: findings.append('target_link_missing')
 if row.get('anchor') and row.get('anchor') not in html.unescape(t): findings.append('anchor_missing')
 # Modernized/seeded pages must satisfy the full Authority Network page contract.
 # Legacy pages remain protected and are checked for backlink integrity without
 # retroactively hard-failing on metadata their original template never emitted.
 modern = bool(row.get('seed_article_id')) or bool(row.get('authority_page_contract_version'))
 if modern:
  if 'Affiliation disclosed:' not in t: findings.append('affiliation_disclosure_missing')
  if '<link rel="canonical"' not in t: findings.append('canonical_missing')
  if '<meta name="description"' not in t: findings.append('meta_description_missing')
 return findings

def repair():
 links=read('data/link-registry.json',[]); repaired=[]; blocked=[]
 for row in links:
  if row.get('lifecycle_stage') not in {'published_in_repository','rendered_in_repository'}: continue
  f=local_findings(row)
  if not f: continue
  p=ROOT/row.get('source_path','')
  if not p.exists(): blocked.append({'source':row.get('source_path'),'reason':'source_missing'}); continue
  t=p.read_text(encoding='utf-8')
  if 'target_link_missing' in f:
   marker='<h2>Editorial note</h2>'
   insertion=f'<h2>Related resource</h2><p><a href="{html.escape(row["target_url"])}">{html.escape(row.get("anchor") or row["target_url"])}</a> is included as an affiliated editorial reference when it directly supports the topic.</p>'
   t=t.replace(marker,insertion+marker) if marker in t else t.replace('</article>',insertion+'</article>')
  if 'affiliation_disclosure_missing' in f:
   t=t.replace('</article>','<h2>Affiliation note</h2><p><strong>Affiliation disclosed:</strong> this page may reference an affiliated project when directly relevant. The link is not an independent ranking, award, or guarantee.</p></article>')
  p.write_text(t,encoding='utf-8'); repaired.append({'source':str(p.relative_to(ROOT)),'repairs':f})
 write('data/backlink-self-heal-latest.json',{'schema':'authority-backlink-self-heal-v1','status':'PASS' if not blocked else 'PASS_WITH_SOFT_WARNING','repaired':repaired,'blocked':blocked})
 print(json.dumps({'status':'PASS' if not blocked else 'PASS_WITH_SOFT_WARNING','repaired':len(repaired),'blocked':blocked},indent=2))

def verify_local():
 links=read('data/link-registry.json',[]); failures=[]; checked=0
 for row in links:
  if row.get('status')!='published' and row.get('lifecycle_stage') not in {'published_in_repository','rendered_in_repository','deployed','live_verified','source_discovered','source_indexed'}: continue
  checked+=1
  for f in local_findings(row): failures.append({'source':row.get('source_path'),'target':row.get('target_url'),'finding':f})
  if str(row.get('campaign_id','')).startswith('wpp-') and norm_domain(row.get('target_url',''))!='westpeekproductions.com': failures.append({'source':row.get('source_path'),'target':row.get('target_url'),'finding':'wpp_target_must_be_westpeekproductions.com'})
 receipt={'schema':'authority-local-backlink-verification-v1','status':'FAIL' if failures else 'PASS','checked':checked,'hard_failures':len(failures),'failures':failures}
 write('reports/backlink-local-verification.json',receipt); print(json.dumps(receipt,indent=2)); raise SystemExit(1 if failures else 0)

def health():
 campaigns=read('data/portfolio-backlink-campaigns.json',{'campaigns':[]})['campaigns']; links=read('data/link-registry.json',[]); rows=[]
 for c in campaigns:
  rs=[r for r in links if r.get('campaign_id')==c['id'] and r.get('status')=='published']
  rendered=sum(bool((r.get('evidence') or {}).get('repository_rendered')) for r in rs); live=sum(bool((r.get('evidence') or {}).get('live_verified')) for r in rs); indexed=sum(bool((r.get('evidence') or {}).get('indexed')) for r in rs)
  dest=len({r.get('target_url') for r in rs}); anchors=Counter(r.get('anchor') for r in rs)
  rows.append({'campaign_id':c['id'],'brand_id':c['brand_id'],'rendered':rendered,'live_verified':live,'indexed':indexed,'distinct_destinations':dest,'distinct_anchors':len(anchors),'rendered_floor':c['minimum_rendered_coverage'],'destination_floor':c['minimum_distinct_destinations'],'coverage_status':'HEALTHY_RENDERED' if rendered>=c['minimum_rendered_coverage'] and dest>=c['minimum_distinct_destinations'] else 'GAP','external_outcome_proven':live>0 or indexed>0})
 out={'schema':'authority-campaign-health-v1','as_of':date.today().isoformat(),'truth_boundary':'Rendered coverage is owned-network inventory, not live or indexed proof.','campaigns':rows}
 write('data/portfolio-campaign-health.json',out); print(json.dumps({'status':'PASS','campaigns':len(rows),'gaps':sum(r['coverage_status']=='GAP' for r in rows)},indent=2))

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('command',choices=['seed','repair','verify-local','health']); a=ap.parse_args(); globals()[a.command.replace('-','_')]()
if __name__=='__main__': main()
