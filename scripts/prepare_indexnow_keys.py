#!/usr/bin/env python3
"""Materialize the public IndexNow key file in each publication root.

IndexNow keys are public verification tokens, not private credentials. Configure the
same value as a GitHub Actions repository variable named INDEXNOW_KEY.
"""
import json, os, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
key=os.getenv('INDEXNOW_KEY','').strip()
key_source='env'
# The docstring above already says these keys are public verification tokens and
# not credentials, but the script still gated entirely on an env var. That var
# was never set, so this printed NOT_CONFIGURED and wrote zero files, and all
# three domains served 404 for their key file. IndexNow refuses any submission
# whose key it cannot read at the publication root, so the lane was dead.
# Fall back to the committed key so the default path works with no secret
# plumbing; INDEXNOW_KEY still wins when set, for rotation.
if not key:
    fallback=ROOT/'data/indexnow_key.txt'
    if fallback.is_file():
        key=fallback.read_text(encoding='utf-8').strip()
        key_source='data/indexnow_key.txt'
pubs=json.loads((ROOT/'data/publications.json').read_text(encoding='utf-8'))
if not key:
    print(json.dumps({'status':'NOT_CONFIGURED','files_written':0,'instruction':'Set repository variable INDEXNOW_KEY or commit data/indexnow_key.txt to enable IndexNow.'}))
    raise SystemExit(0)
if not re.fullmatch(r'[A-Za-z0-9-]{8,128}',key):
    raise SystemExit('INDEXNOW_KEY must be 8-128 letters, digits, or hyphens')
written=[]
for pub in pubs:
    path=ROOT/pub['folder']/f'{key}.txt'
    path.write_text(key+'\n',encoding='utf-8')
    written.append(str(path.relative_to(ROOT)))
print(json.dumps({'status':'PASS','key_source':key_source,'files_written':len(written),'files':written}))
