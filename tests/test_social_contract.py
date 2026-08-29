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
    env.update({'SOCIAL_DRY_RUN':'false','REQUIRE_SOCIAL_SECRETS':'true','FAIL_ON_SOCIAL_POST_FAILURE':'false','ENABLE_LINKEDIN_POSTING':'true','ENABLE_X_POSTING':'false'})
    for key in ['LINKEDIN_ACCESS_TOKEN','LINKEDIN_AUTHOR_URN']: env.pop(key,None)
    p=subprocess.run([sys.executable,'scripts/social_publisher.py'],cwd=ROOT,env=env,text=True,capture_output=True)
    assert p.returncode==0,(p.stdout,p.stderr)
    r=json.loads(report.read_text()); assert r['status']=='ok_with_secret_warning' and r['production_blocked'] is False,'missing secrets should degrade safely'
    env['FAIL_ON_SOCIAL_POST_FAILURE']='true'
    p=subprocess.run([sys.executable,'scripts/social_publisher.py'],cwd=ROOT,env=env,text=True,capture_output=True)
    assert p.returncode!=0,'strict social failure did not block'

    # One platform missing its credentials must retire THAT platform, not the run.
    # This is the regression that made the real drain rate 0/day on every platform:
    # the absent LinkedIn token returned before a single X post was attempted, and
    # the run still exited green saying 'ok_with_secret_warning', so the queue never
    # moved and nothing anywhere said why. The assertion that matters is that
    # `attempts` is non-empty -- the early-return report always has attempts == [],
    # so an empty list here means X was never even tried.
    # The X credentials below are deliberately bogus, so the attempt cannot post:
    # it fails at auth (or at the socket, offline), and either way it was ATTEMPTED.
    queue2=td/'queue2.json'; report2=td/'report2.json'
    queue2.write_text(json.dumps([{'platform':'x','brand':'Fixture','post_type':'resource','body':'Useful fixture post for X','source_url':'https://example.com/resource','status':'queued_for_auto_post'}],indent=2),encoding='utf-8')
    env2={**env,'SOCIAL_QUEUE_PATH':str(queue2),'SOCIAL_REPORT_PATH':str(report2),
          'SOCIAL_DRY_RUN':'false','FAIL_ON_SOCIAL_POST_FAILURE':'false',
          'ENABLE_LINKEDIN_POSTING':'true','ENABLE_X_POSTING':'true',
          'SOCIAL_POST_MIN_INTERVAL_SECONDS':'0',
          'X_API_KEY':'fixture-not-a-real-key','X_API_SECRET':'fixture-not-a-real-secret',
          'X_ACCESS_TOKEN':'fixture-not-a-real-token','X_ACCESS_TOKEN_SECRET':'fixture-not-a-real-token-secret'}
    for key in ['LINKEDIN_ACCESS_TOKEN','LINKEDIN_AUTHOR_URN']: env2.pop(key,None)
    p=subprocess.run([sys.executable,'scripts/social_publisher.py'],cwd=ROOT,env=env2,text=True,capture_output=True)
    assert p.returncode==0,(p.stdout,p.stderr)
    r=json.loads(report2.read_text())
    assert 'linkedin' in r['secret_skips'],'LinkedIn should be recorded as skipped for missing secrets'
    assert r['enabled']['x'] is True,'X had complete credentials and must stay enabled'
    assert len(r['attempts'])==1,'X was not attempted; a missing LinkedIn token still aborts the whole run'
    assert r['status']=='ok_with_secret_warning','a partly-credentialled run is a warning, not a block'

    # Pacing knobs must be reported, so a run that silently lost its spacing is visible.
    assert r['pacing']['run_limit']>=1 and 'min_interval_seconds' in r['pacing'],'pacing not reported'
print(json.dumps({'status':'PASS','fixtures':['dry_run_nonmutation','both_platforms_exercised','missing_secrets_nonblocking_by_default','strict_social_failure_opt_in','one_platform_missing_does_not_abort_the_other','pacing_reported']}))
