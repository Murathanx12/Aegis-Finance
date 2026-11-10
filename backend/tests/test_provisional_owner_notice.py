"""E6 pure fixed-META manifest, rights, clocks and unchanged upstream controls."""
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
import hashlib,json,socket
from pathlib import Path
import pytest
from backend.services import provisional_owner_notice as N
from scripts import current_exposure_link as L
from backend.tests.test_current_exposure_link import chain, pin
from backend.tests.test_owner_decision_bridge import item,receipt


def entry(p):return dict(path=str(p.path),sha256=p.sha256)

@pytest.fixture
def e6(chain,tmp_path,monkeypatch):
    kw,subject,mapping,broker=chain
    def denied(*a,**k):pytest.fail('NETWORK_PROVIDER_BROKER_OR_OWNER_REACHED')
    monkeypatch.setattr(socket.socket,'connect',denied)
    monkeypatch.setattr(socket.socket,'connect_ex',denied)
    monkeypatch.setattr(socket,'create_connection',denied)
    current=datetime.now(timezone.utc)
    broker['observed_from_utc']=(current-timedelta(minutes=20)).isoformat()
    broker['observed_until_utc']=(current-timedelta(minutes=20)+timedelta(seconds=3)).isoformat()
    kw['broker']=pin(kw['broker'].path,broker)
    policy=dict(schema='e6-reviewed-message-policy/1',description_code=N.DESCRIPTION_CODE,
                source_sha256=kw['locator'].source_sha256,raw_line_sha256=subject['raw_line_sha256'],
                rights='METADATA_ONLY_CALLER_REVIEWED',max_source_age_seconds=7*86400,
                max_holding_age_seconds=86400,valid_from_utc=(current-timedelta(minutes=10)).isoformat(),
                valid_until_utc=(current+timedelta(minutes=30)).isoformat())
    policy_pin=pin(tmp_path/'policy.json',policy)
    m=dict(schema='e6-saved-input-manifest/1',evidence_mode='SAVED_REPLAY',event_id=kw['selected_event_id'],
           corpus_root=str(kw['corpus_root']),locator=asdict(kw['locator']),
           **{k:entry(kw[k]) for k in ('receipt','page','subject','mapping','broker')},
           mapping_inputs={k:entry(v) for k,v in kw['mapping_inputs'].items()},
           policy=entry(policy_pin),code_pins=N.code_pins())
    mp=pin(tmp_path/'manifest.json',m)
    return dict(manifest=mp,m=m,policy=policy,kw=kw,tmp=tmp_path)


def save_manifest(f):
    f['manifest']=pin(f['manifest'].path,f['m'])
    return f['manifest']


def test_pure_assessment_retains_negative_e2_and_distinct_clocks_without_writes(e6,monkeypatch):
    before={p:p.read_bytes() for p in e6['tmp'].rglob('*') if p.is_file()}
    monkeypatch.setattr(N,'_exclusive',lambda *a:pytest.fail('write in preview'))
    a=N.build_assessment(e6['manifest'])
    assert a['E2_decision']=='NO_CHANGE_WITH_REASON'
    assert a['E2_reason_codes']==json.loads(e6['kw']['receipt'].path.read_bytes())['groups'][0]['reason_codes']
    assert a['E5_status']==L.CANDIDATE and a['authority']==N.AUTHORITY
    assert a['clocks']['first_seen_utc']!=a['clocks']['holding_from_utc']!=a['clocks']['review_at_utc']
    assert a['eligible_for_offline_injected_test'] and a['delivery']=='NOT_ATTEMPTED'
    N._assessment(a)
    data=N.canonical(a)
    for secret in (b'PRIVATE_TEXT',b'PRIVATE-ASSET-123',b'BODY_SENTINEL',b'https:',str(e6['tmp']).encode()):
        assert secret not in data
    assert before=={p:p.read_bytes() for p in e6['tmp'].rglob('*') if p.is_file()}


def test_semantic_key_does_not_depend_on_review_container_or_snapshot(e6):
    first=N.build_assessment(e6['manifest'])
    broker=json.loads(e6['kw']['broker'].path.read_bytes())
    broker['positions_response_sha256']='c'*64
    e6['m']['broker']=entry(pin(e6['kw']['broker'].path,broker))
    second=N.build_assessment(save_manifest(e6))
    assert first['input_digest']!=second['input_digest']
    assert first['semantic_key']==second['semantic_key']


@pytest.mark.parametrize('field,value',[
    ('issuer_cik','1'),('qualification','DIRECT_ISSUER'),('rights','LICENSED_BODY_ALLOWED'),
    ('observed_at_utc','2099-01-01T00:00:00Z')])
def test_rehashed_bad_subject_refuses(e6,field,value):
    p=e6['kw']['subject'].path;s=json.loads(p.read_bytes());s[field]=value
    e6['m']['subject']=entry(pin(p,s))
    with pytest.raises(N.NoticeRefused,match='UPSTREAM_EVIDENCE_REFUSED'):
        N.build_assessment(save_manifest(e6))


@pytest.mark.parametrize('which,field,value',[
    ('broker','account_number','PRIVATE_ACCOUNT'),('broker','observed_until_utc','2099-01-01T00:00:00Z'),
    ('mapping','rights','PRIVATE_BODY'),('mapping','candidates',[])])
def test_rehashed_mapping_or_holding_cannot_promote_authority(e6,which,field,value):
    p=e6['kw'][which].path;obj=json.loads(p.read_bytes());obj[field]=value
    e6['m'][which]=entry(pin(p,obj))
    with pytest.raises(N.NoticeRefused):N.build_assessment(save_manifest(e6))


@pytest.mark.parametrize('field,value',[
    ('description_code','URGENT_PRICE_DROP'),('rights','LICENSED_FULL_TEXT'),
    ('max_holding_age_seconds',True),('max_source_age_seconds',0),('body','LICENSED_SECRET')])
def test_policy_has_closed_schema_and_explicit_age_bounds(e6,field,value):
    p=Path(e6['m']['policy']['path']);value_policy=dict(e6['policy']);value_policy[field]=value
    e6['m']['policy']=entry(pin(p,value_policy))
    with pytest.raises(N.NoticeRefused):N.build_assessment(save_manifest(e6))


def test_staleness_not_repaired_by_new_review_time(e6):
    p=Path(e6['m']['policy']['path']);policy=dict(e6['policy'],max_holding_age_seconds=1)
    e6['m']['policy']=entry(pin(p,policy))
    a=N.build_assessment(save_manifest(e6))
    assert not a['eligible_for_offline_injected_test'] and 'HOLDING_TOO_OLD' in a['blocked_reasons']


@pytest.mark.parametrize('field',['schema',r'\u0073chema'])
def test_duplicate_or_escaped_duplicate_manifest_fields_refuse(e6,field):
    data=e6['manifest'].path.read_bytes()
    data=b'{"'+field.encode()+b'":"fake",'+data[1:]
    e6['manifest'].path.write_bytes(data)
    p=L.Pin(e6['manifest'].path,N.digest(data))
    with pytest.raises(N.NoticeRefused,match='INVALID_OR_DUPLICATE_JSON'):N.build_assessment(p)


def test_rehashed_e2_unsupported_authority_is_not_forwarded(e6):
    p=e6['kw']['receipt'].path;obj=json.loads(p.read_bytes())
    obj['authority']['delivery']='DELIVERED'
    obj['receipt_id']=N.digest({k:v for k,v in obj.items() if k!='receipt_id'})
    e6['m']['receipt']=entry(pin(p,obj))
    with pytest.raises(N.NoticeRefused):N.build_assessment(save_manifest(e6))


def test_changed_source_and_foreign_locator_refuse(e6):
    root=e6['kw']['corpus_root'];p=root/e6['kw']['locator'].relative_corpus_path
    p.write_bytes(p.read_bytes()+b'{}\n')
    with pytest.raises(N.NoticeRefused):N.build_assessment(e6['manifest'])
    e6['m']['locator']['relative_corpus_path']='../foreign.jsonl'
    with pytest.raises(N.NoticeRefused):N.build_assessment(save_manifest(e6))


def test_code_pin_and_manifest_cap_refuse(e6):
    e6['m']['code_pins']['E5']='0'*64
    with pytest.raises(N.NoticeRefused,match='CODE_PIN_MISMATCH'):N.build_assessment(save_manifest(e6))
    e6['manifest'].path.write_bytes(b' '*65537)
    with pytest.raises(N.NoticeRefused):N.build_assessment(L.Pin(e6['manifest'].path,N.digest(e6['manifest'].path.read_bytes())))


def test_stable_document_identity_distinguishes_sec_sibling_exhibits():
    group=dict(event_key='filing:1326801:000119312526000001')
    one=N._semantic_key(group,dict(source_id='source-document-one'))
    two=N._semantic_key(group,dict(source_id='source-document-two'))
    assert one!=two
    assert one==N._semantic_key(group,dict(source_id='source-document-one'))
