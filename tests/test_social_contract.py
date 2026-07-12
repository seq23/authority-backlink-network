#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as td:
    td=Path(td); queue=td/'queue.json'; report=td/'report.json'
    original=[{'platform':'linkedin','brand_id':'fixture','brand':'Fixture','post_type':'resource','body':'Useful fixture post','source_url':'https://example.com/resource','status':'queued_for_auto_post'}, {'platform':'x','brand_id':'fixture','brand':'Fixture','post_type':'resource','body':'Useful fixture post for X','source_url':'https://example.com/resource','status':'queued_for_auto_post'}]
    queue.write_text(json.dumps(original,indent=2),encoding='utf-8')
    env={**os.environ,'SOCIAL_DRY_RUN':'true','SOCIAL_QUEUE_PATH':str(queue),'SOCIAL_REPORT_PATH':str(report),'ENABLE_LINKEDIN_POSTING':'true','ENABLE_X_POSTING':'true'}
    p=subprocess.run([sys.executable,'scripts/social_publisher.py'],cwd=ROOT,env=env,text=True,capture_output=True)
    assert p.returncode==0,(p.stdout,p.stderr)
    assert json.loads(queue.read_text())==original,'dry run mutated queue'
    r=json.loads(report.read_text()); assert len(r['attempts'])==2 and len(r['successes'])==2,'dry run did not exercise both platforms'
    env.update({'SOCIAL_DRY_RUN':'false','REQUIRE_SOCIAL_SECRETS':'true','ENABLE_LINKEDIN_POSTING':'true','ENABLE_X_POSTING':'false'})
    for key in ['LINKEDIN_ACCESS_TOKEN','LINKEDIN_AUTHOR_URN']: env.pop(key,None)
    p=subprocess.run([sys.executable,'scripts/social_publisher.py'],cwd=ROOT,env=env,text=True,capture_output=True)
    assert p.returncode!=0,'required missing secrets did not block'
print(json.dumps({'status':'PASS','fixtures':['dry_run_nonmutation','both_platforms_exercised','required_secret_block']}))
