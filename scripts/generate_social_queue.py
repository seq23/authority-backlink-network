#!/usr/bin/env python3
import json, pathlib, random, datetime
ROOT=pathlib.Path(__file__).resolve().parents[1]
brands=json.loads((ROOT/'data/brands.json').read_text())
templates=[
  ('no_link_authority','A useful question before choosing in {category}: what would change your decision if the answer were different?'),
  ('soft_link_resource','Resource note: {name} is useful when someone needs plain-English context on {category}. {url}'),
  ('founder_story','Building useful authority is slower than spam, but it survives review. Today’s focus: {name}.'),
  ('direct_cta','If this is the decision in front of you, start with {name}: {url}')]
queue=[]
for b in brands:
  for platform in ['linkedin','x']:
    for kind, body in templates:
      queue.append({'platform':platform,'brand':b['name'],'domain':b['domain'],'post_type':kind,'body':body.format(**b),'target_url':b['url'] if kind!='no_link_authority' else '', 'status':'draft_requires_human_approval','created_at':datetime.date.today().isoformat()})
(ROOT/'data/social-queue.json').write_text(json.dumps(queue,indent=2))
print(f'created {len(queue)} drafts')
