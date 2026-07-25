#!/usr/bin/env python3
"""Materialize the public IndexNow key file in each publication root.

IndexNow keys are public verification tokens, not private credentials. Configure the
same value as a GitHub Actions repository variable named INDEXNOW_KEY.
"""
import json, os, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
key=os.getenv('INDEXNOW_KEY','').strip()
pubs=json.loads((ROOT/'data/publications.json').read_text(encoding='utf-8'))
if not key:
    print(json.dumps({'status':'NOT_CONFIGURED','files_written':0,'instruction':'Set repository variable INDEXNOW_KEY to enable IndexNow.'}))
    raise SystemExit(0)
if not re.fullmatch(r'[A-Za-z0-9-]{8,128}',key):
    raise SystemExit('INDEXNOW_KEY must be 8-128 letters, digits, or hyphens')
written=[]
for pub in pubs:
    path=ROOT/pub['folder']/f'{key}.txt'
    path.write_text(key+'\n',encoding='utf-8')
    written.append(str(path.relative_to(ROOT)))
print(json.dumps({'status':'PASS','files_written':len(written),'files':written}))
