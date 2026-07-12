#!/usr/bin/env python3
"""Generate social drafts without deleting posting history or operator decisions."""
import datetime, hashlib, json
from pathlib import Path
from lib.authority_core import atomic_write_json, read_json
ROOT=Path(__file__).resolve().parents[1]
brands=read_json(ROOT/'data/brands.json',[])
queue_path=ROOT/'data/social-queue.json'
existing=read_json(queue_path,[])
if isinstance(existing,dict): existing=existing.get('items',[])
templates=[
  ('no_link_authority','A useful question before choosing in {category}: what would change your decision if the answer were different?'),
  ('soft_link_resource','Resource note: {name} is useful when someone needs plain-English context on {category}. {url}'),
  ('founder_story','Building useful authority is slower than spam, but it survives review. Today’s focus: {name}.'),
  ('direct_cta','If this is the decision in front of you, start with {name}: {url}')]

def stable_id(platform,brand_id,kind,target_url,body):
    raw='|'.join([platform,brand_id,kind,target_url,body])
    return hashlib.sha256(raw.encode()).hexdigest()[:20]

seen={item.get('id') for item in existing if item.get('id')}
# Legacy rows without IDs are preserved and deduplicated by stable content key.
legacy_keys={(i.get('platform'),i.get('brand_id') or i.get('brand'),i.get('post_type'),i.get('target_url',''),i.get('body','')) for i in existing}
created=0
for b in brands:
  domains=b.get('domains') or [b.get('domain','')]
  primary_domain=domains[0]
  primary_url=b.get('url') or ('https://'+primary_domain)
  fmt={**b,'domain':primary_domain,'url':primary_url,'category':b.get('category','the topic')}
  for platform in ['linkedin','x']:
    for kind, template in templates:
      body=template.format(**fmt); target=primary_url if kind!='no_link_authority' else ''
      row_id=stable_id(platform,b['id'],kind,target,body)
      key=(platform,b['id'],kind,target,body)
      if row_id in seen or key in legacy_keys: continue
      existing.append({'id':row_id,'platform':platform,'brand_id':b['id'],'brand':b['name'],'domain':primary_domain,'post_type':kind,'body':body,'target_url':target,'status':'draft_requires_human_approval','created_at':datetime.date.today().isoformat()})
      seen.add(row_id); created+=1
atomic_write_json(queue_path,existing)
print(json.dumps({'status':'PASS','created':created,'preserved':len(existing)-created,'total':len(existing)}))
