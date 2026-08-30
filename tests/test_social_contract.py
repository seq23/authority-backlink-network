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

    # The platform switch is a round trip, not a one-way retirement. Flipping
    # platforms.linkedin.enabled off must park every LinkedIn entry WITHOUT
    # touching the queue file, and flipping it back on must restore all of them
    # with no un-marking pass and no re-backfill. A row-level pause stamp would
    # pass a naive "are they postable again" check while quietly making the
    # reversal a per-row job, so the queue bytes are compared too.
    import shutil
    policy_src = ROOT/'data/social-brand-policy.json'
    for switch, expect_li in ((False, 0), (True, 1)):
        policy = td/f'policy-{switch}.json'
        doc = json.loads(policy_src.read_text())
        doc['platforms']['linkedin']['enabled'] = switch
        # X is paused for posting in the committed declaration. This fixture is
        # about the LinkedIn switch in isolation, so X is switched ON here on
        # purpose -- otherwise "X was unaffected" would be vacuously true.
        doc['platforms']['x']['enabled'] = True
        doc['platforms']['linkedin'].setdefault('paused_on', '2026-08-29')
        doc['platforms']['linkedin'].setdefault('paused_by', 'owner')
        doc['platforms']['linkedin'].setdefault('paused_reason', 'fixture')
        policy.write_text(json.dumps(doc, indent=2), encoding='utf-8')
        q3=td/f'queue3-{switch}.json'; r3=td/f'report3-{switch}.json'
        rows=[{'platform':'linkedin','brand':'Fixture','post_type':'resource','body':'LI fixture','source_url':'https://example.com/a','status':'queued_for_auto_post'},
              {'platform':'x','brand':'Fixture','post_type':'resource','body':'X fixture','source_url':'https://example.com/b','status':'queued_for_auto_post'}]
        q3.write_text(json.dumps(rows,indent=2),encoding='utf-8')
        before=q3.read_bytes()
        env3={**os.environ,'SOCIAL_QUEUE_PATH':str(q3),'SOCIAL_REPORT_PATH':str(r3),
              'SOCIAL_PLATFORM_POLICY_PATH':str(policy),'SOCIAL_DRY_RUN':'true'}
        for key in ['ENABLE_LINKEDIN_POSTING','ENABLE_X_POSTING']: env3.pop(key,None)
        p3=subprocess.run([sys.executable,'scripts/social_publisher.py'],cwd=ROOT,env=env3,text=True,capture_output=True)
        assert p3.returncode==0,(p3.stdout,p3.stderr)
        r=json.loads(r3.read_text())
        li=[a for a in r['attempts'] if a['platform']=='linkedin']
        x=[a for a in r['attempts'] if a['platform']=='x']
        assert len(li)==expect_li, f'linkedin switch={switch} attempted {len(li)}, expected {expect_li}'
        assert len(x)==1, f'X must be unaffected by the LinkedIn switch (switch={switch})'
        assert q3.read_bytes()==before, 'the switch rewrote the queue; parking must be derived, not stamped'
        if not switch:
            assert r['platform_states']['linkedin']=='paused_by_switch'
            assert r['parked_by_platform_switch'].get('linkedin')==1
            assert 'linkedin' in r['named_stops'], 'a paused platform must name its stop'
        else:
            assert not r.get('parked_by_platform_switch'), 'switch on must park nothing'

    # A run with every switch off DORMANT must stop by NAME, not exit 0 having
    # done nothing. Dormant is the case that produces nothing at all; the
    # paused-for-posting case below must NOT report itself as a stop.
    policy_off = td/'policy-all-off.json'
    doc = json.loads(policy_src.read_text())
    for plat in ('linkedin','x'):
        doc['platforms'][plat].update({'enabled': False, 'pause_mode':'dormant',
                                       'paused_on':'2026-08-29',
                                       'paused_by':'owner','paused_reason':'fixture'})
    policy_off.write_text(json.dumps(doc, indent=2), encoding='utf-8')
    q4=td/'queue4.json'; r4=td/'report4.json'
    q4.write_text(json.dumps([{'platform':'x','brand':'Fixture','post_type':'resource','body':'X fixture','source_url':'https://example.com/b','status':'queued_for_auto_post'}],indent=2),encoding='utf-8')
    env4={**os.environ,'SOCIAL_QUEUE_PATH':str(q4),'SOCIAL_REPORT_PATH':str(r4),
          'SOCIAL_PLATFORM_POLICY_PATH':str(policy_off),'SOCIAL_DRY_RUN':'true'}
    for key in ['ENABLE_LINKEDIN_POSTING','ENABLE_X_POSTING']: env4.pop(key,None)
    p4=subprocess.run([sys.executable,'scripts/social_publisher.py'],cwd=ROOT,env=env4,text=True,capture_output=True)
    assert p4.returncode==0,(p4.stdout,p4.stderr)
    r=json.loads(r4.read_text())
    assert r['status']=='stopped_no_enabled_platform','a run with nowhere to post must stop by name'
    assert r['stop_reason'],'the stop must carry a reason'

    assert r['platform_states']['x']=='paused_by_switch','a dormant pause must read as one'
    assert 'manual_drafts' not in r,'the hand-post lane is retired; nothing may report it'

    # Pacing knobs must be reported, so a run that silently lost its spacing is visible.
    assert r['pacing']['run_limit']>=1 and 'min_interval_seconds' in r['pacing'],'pacing not reported'

    # The other pause: X's own API switched off with a DELIVERY ROUTE declared.
    # Nothing may be sent to the API, nothing may be asked of a human, and the
    # entries the route could not carry must simply stay queued and be counted.
    # "Deferred, 10 waiting" is a named state; only "nothing produced and
    # nothing waiting" is a stop.
    policy_route = td/'policy-delivery-route.json'
    doc = json.loads(policy_src.read_text())
    doc['platforms']['linkedin'].update({'enabled': False, 'pause_mode':'dormant',
                                         'paused_on':'2026-08-29','paused_by':'owner',
                                         'paused_reason':'fixture'})
    doc['platforms']['x'].update({'enabled': False, 'pause_mode':'delivery_route',
                                  'paused_on':'2026-08-29','paused_by':'owner',
                                  'paused_reason':'fixture'})
    policy_route.write_text(json.dumps(doc, indent=2), encoding='utf-8')
    q5=td/'queue5.json'; r5=td/'report5.json'
    rows5=[{'platform':'x','brand':'Fixture','post_type':'resource',
            'body':f'X fixture {i}','source_url':f'https://example.com/{i}',
            'status':'queued_for_auto_post'} for i in range(10)]
    q5.write_text(json.dumps(rows5,indent=2),encoding='utf-8')
    before5=q5.read_bytes()
    env5={**os.environ,'SOCIAL_QUEUE_PATH':str(q5),'SOCIAL_REPORT_PATH':str(r5),
          'SOCIAL_PLATFORM_POLICY_PATH':str(policy_route),'SOCIAL_DRY_RUN':'true',
          'SOCIAL_DRAFT_LEDGER_PATH':str(td/'ledger5.json')}
    for key in ['ENABLE_LINKEDIN_POSTING','ENABLE_X_POSTING','BUFFER_ACCESS_TOKEN']:
        env5.pop(key,None)
    p5=subprocess.run([sys.executable,'scripts/social_publisher.py'],cwd=ROOT,env=env5,text=True,capture_output=True)
    assert p5.returncode==0,(p5.stdout,p5.stderr)
    r=json.loads(r5.read_text())
    assert r['platform_states']['x']=='paused_api_awaiting_delivery_route',\
        'a pause_mode of delivery_route must resolve to its own state'
    assert r['attempts']==[] and r['api_requests_made']==0,\
        'a platform paused for its own API must be contacted zero times'
    assert r['deferred_waiting_for_delivery_route']==len(rows5),\
        'every entry the route could not carry must stay queued and be counted'
    assert r['route_only_platforms']==['x'],\
        'the platform whose distribution runs through a route must be named'
    assert 'manual_drafts' not in json.dumps(r),\
        'no run may report a hand-post lane: it is deleted, not switched off'
    assert not (ROOT/'reports'/'social-drafts.md').exists(),\
        'the copy-paste sheet is retired and must never be written again'
    assert r['status']!='stopped_no_enabled_platform',\
        'a run whose entries are waiting on a route is not a stop with nothing waiting'
    assert 'x' in r['named_stops'] and 'route' in r['named_stops']['x'].lower(),\
        'the stop must say the posts are waiting for the route, and that nothing is asked'
    assert 'by hand' not in r['named_stops']['x'].lower(),\
        'nothing may tell the owner to post by hand; she has said she never will'
    assert q5.read_bytes()==before5,'pausing rewrote the queue'
    assert r['hand_post_history']['marked_posted_through'] is None or \
        isinstance(r['hand_post_history']['marked_posted_through'],str),\
        'the historical hand-post record must be reported, read-only'
    assert not (td/'ledger5.json').exists(),\
        'nothing may write the hand-post ledger; it is a historical record'
print(json.dumps({'status':'PASS','fixtures':['platform_switch_round_trip','all_switches_off_named_stop','route_only_pause_defers_by_name_and_makes_no_requests','dry_run_nonmutation','both_platforms_exercised','missing_secrets_nonblocking_by_default','strict_social_failure_opt_in','one_platform_missing_does_not_abort_the_other','pacing_reported']}))
