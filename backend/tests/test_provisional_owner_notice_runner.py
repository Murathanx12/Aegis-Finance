"""Only injected callbacks: no native owner send, broker/model or task."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import pytest
from backend.services import provisional_owner_notice as N
from scripts import provisional_owner_notice as CLI
from backend.tests.test_provisional_owner_notice import e6,entry,save_manifest,chain
from backend.tests.test_current_exposure_link import pin


def native_ack(text,*,tag,expected_owner,until):
    witness=dict(recipient=expected_owner,message_id=17,chat_type='private')
    ack=dict(state='SENT',messages=1,
             native_ack_sha256=N.digest(dict(schema='telegram-native-ack/1',owner=expected_owner,message_id=17)),
             tag_sha256=N.digest(dict(tag=tag)),text_sha256=N.digest(text.encode()))
    ack['delivery_binding_sha256']=N.digest({k:ack[k] for k in ('native_ack_sha256','tag_sha256','text_sha256')})
    return ack|dict(native_witness=witness)


def verify(review,proofs,key):
    # Deliberately SYNTHETIC proof contract in an offline injected harness.
    # Not an adapter or acceptance receipt for any actual manual/legacy delivery.
    for data in proofs.values():
        obj=N.parse(data)
        assert obj==dict(schema='synthetic-manual-proof/1',state='FIXTURE_ACK')
    return dict(schema='e6-offline-suppression-verdict/1',semantic_key=key,
                proof_set_sha256=N.digest({k:N.digest(v) for k,v in proofs.items()}),state='CLEAR')


@pytest.fixture
def delivery(e6):
    a=N.build_assessment(e6['manifest']);t=datetime.now(timezone.utc)
    proof=pin(e6['tmp']/'apple-proof.json',dict(schema='synthetic-manual-proof/1',state='FIXTURE_ACK'))
    review=pin(e6['tmp']/'suppression.json',dict(schema='e6-offline-cross-lane-review/1',
        reviewed_at_utc=t.isoformat(),coverage=['LEGACY_AUTO','ALL_KNOWN_MANUAL','E6_JOURNAL'],
        proofs=[dict(label='APPLE_MANUAL',lane='MANUAL',proof=entry(proof))]))
    grant=dict(schema='e6-offline-injection-grant/1',test_only=True,authority='DATED_CALLER_ATTESTED_CANDIDATE_ONLY',
               manifest_sha256=e6['manifest'].sha256,input_digest=a['input_digest'],semantic_key=a['semantic_key'],
               code_pins=N.code_pins(),policy_sha256=a['policy_sha256'],suppression_sha256=review.sha256,
               recipient='987654321',valid_from_utc=(t-timedelta(minutes=2)).isoformat(),
               valid_until_utc=(t+timedelta(minutes=5)).isoformat())
    gp=pin(e6['tmp']/'grant.json',grant)
    journal=e6['tmp']/'journal';journal.mkdir(mode=0o700)
    e6.update(grant=gp,grant_obj=grant,suppression=review,proof=proof,journal=journal,
              harness=N.OfflineHarness(native_ack,verify))
    return e6


def run(f,**kw):
    return N.run_notice(f['manifest'],send=True,harness=kw.pop('harness',f['harness']),
                        journal=f['journal'],grant=f['grant'],suppression=f['suppression'],**kw)


def refresh_grant(f):
    a=N.build_assessment(f['manifest'])
    f['grant_obj'].update(manifest_sha256=f['manifest'].sha256,input_digest=a['input_digest'],policy_sha256=a['policy_sha256'])
    f['grant']=pin(f['grant'].path,f['grant_obj'])


def test_preview_cannot_reach_sender_or_journal(delivery,monkeypatch):
    monkeypatch.setattr(N,'_external_dir',lambda *a:pytest.fail('preview journal access'))
    monkeypatch.setattr(N,'_exclusive',lambda *a:pytest.fail('preview write'))
    r=N.run_notice(delivery['manifest'])
    assert r['state']=='PREVIEW' and r['transport_calls']==0 and not r['production_send_authority']
    assert not list(delivery['journal'].iterdir())
    assert CLI.main(['--manifest',str(delivery['manifest'].path),'--manifest-sha256',delivery['manifest'].sha256,'--send'])==2


def test_one_injected_attempt_is_durable_and_suppresses_duplicate(delivery):
    calls=[]
    def sender(text,**kw):
        paths=list(delivery['journal'].glob('*.sending.json'))
        assert len(paths)==1 and json.loads(paths[0].read_bytes())['state']=='SENDING_INJECTED_ONLY'
        calls.append(text)
        return native_ack(text,**kw)
    harness=N.OfflineHarness(sender,verify)
    first=run(delivery,harness=harness)
    second=run(delivery,harness=harness)
    assert first['state']=='INJECTED_ACKNOWLEDGED'
    assert second['state']=='ALREADY_SENT_INJECTED_ONLY' and len(calls)==1
    for p in delivery['journal'].glob('*.json'):
        raw=p.read_bytes()
        assert all(s not in raw for s in (b'987654321',b'PRIVATE_TEXT',b'PRIVATE-ASSET-123',b'BODY_SENTINEL',b'https:'))


@pytest.mark.parametrize('attack',['recipient','message_id','text','tag','binding','extra','late'])
def test_wrong_or_late_ack_never_retries(delivery,attack,monkeypatch):
    calls=[]
    def sender(text,**kw):
        calls.append(1);ack=native_ack(text,**kw)
        if attack=='recipient':ack['native_witness']['recipient']='111'
        if attack=='message_id':ack['native_witness']['message_id']=True
        if attack=='text':ack['text_sha256']='a'*64
        if attack=='tag':ack['tag_sha256']='a'*64
        if attack=='binding':ack['delivery_binding_sha256']='a'*64
        if attack=='extra':ack['account_number']='PRIVATE'
        if attack=='late':monkeypatch.setattr(N.time,'monotonic',lambda:10**20)
        return ack
    harness=N.OfflineHarness(sender,verify)
    with pytest.raises(N.NoticeRefused,match='UNKNOWN_RECONCILE_REQUIRED'):run(delivery,harness=harness)
    monkeypatch.undo()
    with pytest.raises(N.NoticeRefused,match='UNKNOWN_RECONCILE_REQUIRED'):run(delivery,harness=harness)
    assert len(calls)==1


def test_orphan_sending_and_transport_timeout_are_nonretryable(delivery):
    calls=[]
    def timeout(*a,**kw):calls.append(1);raise TimeoutError('SECRET')
    harness=N.OfflineHarness(timeout,verify)
    for _ in range(2):
        with pytest.raises(N.NoticeRefused,match='UNKNOWN_RECONCILE_REQUIRED'):run(delivery,harness=harness)
    assert calls==[1] and not list(delivery['journal'].glob('*.result.json'))


@pytest.mark.parametrize('phase',['before_sending','after_sending','before_result','after_result'])
def test_persistence_boundaries_fail_closed(delivery,monkeypatch,phase):
    original=N._exclusive;calls=[]
    def fail(path,value):
        is_sending=path.name.endswith('.sending.json')
        hit=(is_sending and 'sending' in phase) or (not is_sending and 'result' in phase)
        if hit and phase.startswith('before'):raise OSError('private path')
        original(path,value)
        if hit and phase.startswith('after'):raise OSError('private path')
    def sender(text,**kw):calls.append(1);return native_ack(text,**kw)
    monkeypatch.setattr(N,'_exclusive',fail)
    with pytest.raises(N.NoticeRefused,match='UNKNOWN_RECONCILE_REQUIRED'):
        run(delivery,harness=N.OfflineHarness(sender,verify))
    assert len(calls)==int('result' in phase)
    monkeypatch.setattr(N,'_exclusive',original)
    if phase=='after_result':assert run(delivery)['state']=='ALREADY_SENT_INJECTED_ONLY'
    elif phase!='before_sending':
        with pytest.raises(N.NoticeRefused,match='UNKNOWN_RECONCILE_REQUIRED'):run(delivery)


def test_source_drift_after_sending_checkpoint_does_not_dispatch(delivery,monkeypatch):
    original=N._exclusive;calls=[]
    def mutate(path,value):
        original(path,value)
        source=delivery['kw']['corpus_root']/delivery['kw']['locator'].relative_corpus_path
        source.write_bytes(source.read_bytes()+b'{}\n')
    monkeypatch.setattr(N,'_exclusive',mutate)
    def sender(*a,**kw):calls.append(1);return {}
    with pytest.raises(N.NoticeRefused,match='UNKNOWN_RECONCILE_REQUIRED'):
        run(delivery,harness=N.OfflineHarness(sender,verify))
    assert not calls


@pytest.mark.parametrize('state',['PRIOR_ACK','UNKNOWN'])
def test_cross_lane_prior_or_unknown_proof_blocks_transport(delivery,state):
    calls=[]
    def check(review,proofs,key):return dict(verify(review,proofs,key),state=state)
    def sender(*a,**kw):calls.append(1);return {}
    harness=N.OfflineHarness(sender,check)
    if state=='PRIOR_ACK':assert run(delivery,harness=harness)['state']=='SUPPRESSED_BY_REVIEWED_TEST_PROOF'
    else:
        with pytest.raises(N.NoticeRefused,match='CROSS_LANE_UNKNOWN'):run(delivery,harness=harness)
    assert not calls and not list(delivery['journal'].iterdir())


def test_manual_proof_hash_mismatch_or_missing_coverage_refuses(delivery):
    delivery['proof'].path.write_bytes(b'forged')
    with pytest.raises(N.NoticeRefused):run(delivery)
    assert not list(delivery['journal'].iterdir())


def test_new_broker_snapshot_does_not_resend_same_event(delivery):
    assert run(delivery)['state']=='INJECTED_ACKNOWLEDGED'
    broker=json.loads(delivery['kw']['broker'].path.read_bytes())
    broker['positions_response_sha256']='c'*64
    delivery['m']['broker']=entry(pin(delivery['kw']['broker'].path,broker))
    save_manifest(delivery);refresh_grant(delivery)
    assert run(delivery)['state']=='ALREADY_SENT_INJECTED_ONLY'


@pytest.mark.parametrize('field,value', [('test_only',False),('authority','VERIFIED_CURRENT_HOLDING'),
                                       ('recipient','not-private'),('valid_until_utc','2000-01-01T00:00:00Z')])
def test_missing_or_unsupported_real_send_grant_never_dispatches(delivery,field,value):
    delivery['grant_obj'][field]=value
    delivery['grant']=pin(delivery['grant'].path,delivery['grant_obj'])
    with pytest.raises(N.NoticeRefused):run(delivery)
    assert not list(delivery['journal'].iterdir())


def test_repository_or_corpus_journal_is_refused(delivery):
    delivery['journal']=delivery['kw']['corpus_root']
    # Qualify journal privacy first so POSIX reaches the source-output guard.
    delivery['journal'].chmod(0o700)
    before=list(delivery['journal'].rglob('*'))
    with pytest.raises(N.NoticeRefused,match='SOURCE_OUTPUT_REFUSED'):run(delivery)
    assert before==list(delivery['journal'].rglob('*'))


def test_expired_policy_and_deadline_are_not_empty_success(delivery,monkeypatch):
    p=Path(delivery['m']['policy']['path']);policy=dict(delivery['policy'],max_holding_age_seconds=1)
    delivery['m']['policy']=entry(pin(p,policy));save_manifest(delivery)
    with pytest.raises(N.NoticeRefused,match='STALE_OR_EXPIRED'):run(delivery)
    monkeypatch.setattr(N.Bounds,'check',lambda *a:N.refuse('DEADLINE'))
    with pytest.raises(N.NoticeRefused,match='DEADLINE'):N.run_notice(delivery['manifest'])


def test_new_container_hash_and_review_time_do_not_mint_identity(delivery):
    assert run(delivery)['state']=='INJECTED_ACKNOWLEDGED'
    p=delivery['kw']['corpus_root']/delivery['kw']['locator'].relative_corpus_path
    p.write_bytes(p.read_bytes()+b'{}\n')
    delivery['m']['locator']['container_sha256']=N.digest(p.read_bytes())
    save_manifest(delivery);refresh_grant(delivery)
    assert run(delivery)['state']=='ALREADY_SENT_INJECTED_ONLY'


def test_material_source_amendment_requires_review_not_automatic_resend(delivery):
    from dataclasses import replace
    from backend.tests.test_owner_decision_bridge import item,receipt
    f=delivery
    assert run(f)['state']=='INJECTED_ACKNOWLEDGED'
    source=f['kw']['corpus_root']/f['kw']['locator'].relative_corpus_path
    row=json.loads(source.read_bytes());row['body']+=' changed source version'
    raw=json.dumps(row,separators=(',',':')).encode()+b'\n';source.write_bytes(raw)
    i=item(raw,'dj_reader_wsj');rec=receipt([i])
    rec_path=f['kw']['receipt'].path
    rec_path.write_bytes(N.canonical(rec)+b'\n')
    f['m']['receipt']=entry(N.E5.Pin(rec_path,N.digest(rec_path.read_bytes())))
    f['m']['locator'].update(source_sha256=N.digest(raw.rstrip(b'\r\n')),container_sha256=N.digest(raw))
    subject=json.loads(f['kw']['subject'].path.read_bytes())
    subject.update(source_sha256=f['m']['locator']['source_sha256'],raw_line_sha256=N.digest(raw))
    f['m']['subject']=entry(pin(f['kw']['subject'].path,subject))
    policy=dict(f['policy'],source_sha256=f['m']['locator']['source_sha256'],raw_line_sha256=N.digest(raw))
    f['m']['policy']=entry(pin(Path(f['m']['policy']['path']),policy))
    save_manifest(f);refresh_grant(f)
    with pytest.raises(N.NoticeRefused,match='MATERIAL_UPDATE_REVIEW_REQUIRED'):run(f)
    assert len(list(f['journal'].glob('*.result.json')))==1


def test_missing_apple_proof_or_stale_cross_lane_review_refuses(delivery):
    f=delivery
    review=json.loads(f['suppression'].path.read_bytes());review['proofs'][0]['label']='SOME_OTHER_MANUAL'
    f['suppression']=pin(f['suppression'].path,review)
    f['grant_obj']['suppression_sha256']=f['suppression'].sha256
    f['grant']=pin(f['grant'].path,f['grant_obj'])
    with pytest.raises(N.NoticeRefused,match='KNOWN_MANUAL_SUPPRESSION_REQUIRED'):run(f)
    assert not list(f['journal'].iterdir())
    review['reviewed_at_utc']='2000-01-01T00:00:00Z'
    f['suppression']=pin(f['suppression'].path,review)
    f['grant_obj']['suppression_sha256']=f['suppression'].sha256
    f['grant']=pin(f['grant'].path,f['grant_obj'])
    with pytest.raises(N.NoticeRefused,match='SUPPRESSION_COVERAGE_REQUIRED'):run(f)


def test_rehashed_old_attempt_authority_or_payload_injection_refuses(delivery):
    f=delivery
    assert run(f)['state']=='INJECTED_ACKNOWLEDGED'
    sp=next(f['journal'].glob('*.sending.json'));rp=next(f['journal'].glob('*.result.json'))
    s=json.loads(sp.read_bytes());r=json.loads(rp.read_bytes())
    s['artifact']['authority']['forecast']='ENABLED'
    s['artifact']['assessment_sha256']=N.digest({k:v for k,v in s['artifact'].items() if k!='assessment_sha256'})
    s['artifact_sha256']=N.digest(s['artifact']);r['sending_sha256']=N.digest(s)
    sp.write_bytes(N.canonical(s));rp.write_bytes(N.canonical(r))
    before={p:p.read_bytes() for p in f['journal'].iterdir()}
    with pytest.raises(N.NoticeRefused):run(f)
    assert before=={p:p.read_bytes() for p in f['journal'].iterdir()}
