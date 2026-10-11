"""Synthetic private IO/transport mechanics; no native files, provider or model."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from backend.services import beta_v1_news_runtime as R
from backend.services import beta_v1_news as N, beta_v1_policy as P
from backend.tests.test_beta_v1_news import produce, numerical_review, qualify


@pytest.fixture(autouse=True)
def runtime_input_guard(tmp_path,monkeypatch):
    original=R.read_bound
    def guarded(path,**kwargs):
        assert Path(path).resolve().is_relative_to(tmp_path.resolve()), 'outside synthetic runtime input scope'
        return original(path,**kwargs)
    monkeypatch.setattr(R,'read_bound',guarded)


def original_fixture(horizon=21):
    def extras(item,source,review,kwargs):
        kwargs['target'].update(benchmark_security_id='fixture-SPY',price_basis_id='fixture-native-source',horizon=horizon)
        cal=P._calendar();start=cal.date_to_session(kwargs['target']['label_start_at'][:10])
        kwargs['target']['label_end_at']=cal.session_close(cal.session_offset(start,horizon)).isoformat()
    captured,_,parts=produce(modify=extras)
    item,source,source_review,kwargs=parts
    bundle={**kwargs,'item':vars(item),'source_capture':source,'semantic_review':source_review}
    bundle['engine_review']={'independent':True,'selection_method':'ENGINE_IDENTITY_INTERSECTION',
        'candidate_hash':P.digest(bundle['candidates']),'identity_hash':P.digest(bundle['identity']),
        'available_at':'2026-10-12T10:00:00+00:00'}
    capture=captured['capture'];review=numerical_review(capture)
    row=N.candidate_record(capture,review,made_at=bundle['decision_at'])
    definitions={'news':{'source_family':'news','model_version':row['model_version'],
        'prompt_version':row['prompt_version'],'correlation_group':'fixture-news'}}
    return {'bundle':bundle,'capture':capture,'numeric_review':review,'record':row,
            'definitions':definitions,'qualifications':qualify([row])}


@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e309}',b'{"x":1} trailing',b'\xff'])
def test_strict_complete_json_never_repairs_or_zeros(raw):
    with pytest.raises(ValueError):R.strict_json(raw)


def test_private_capture_immutable_publish_and_hash_guard(tmp_path):
    original=original_fixture();snapshot=deepcopy(original)
    path=R.publish(tmp_path,'capture.json',{'capture':original['capture']})
    raw=R.read_bound(path,expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert R.strict_json(raw)['capture']==original['capture'] and original==snapshot
    with pytest.raises(ValueError,match='IMMUTABLE'):R.publish(tmp_path,'capture.json',{})
    with pytest.raises(ValueError,match='HASH_DRIFT'):R.read_bound(path,expected_sha256='0'*64)


def test_output_cap_is_checked_before_atomic_writer(tmp_path,monkeypatch):
    from backend.services import disk_guard as DG
    calls=[];monkeypatch.setattr(DG,'atomic_write_text',lambda *a,**k:calls.append(1))
    with pytest.raises(ValueError,match='OUTPUT_TOTAL'):R.publish(tmp_path,'capture.json',{'large':'x'*R.MAX_OUTPUT})
    assert calls==[] and list(tmp_path.iterdir())==[]


def test_external_numeric_review_and_exact_row_qualification_are_both_required():
    original=original_fixture();b=original['bundle'];c=original['capture'];q=original['qualifications'];defs=original['definitions']
    accepted=R.normalize_reviewed(b,c,original['numeric_review'],q,defs,made_at=original['record']['forecast_at'])
    assert accepted['candidate']==original['record'] and accepted['admission']['records']
    rejected=R.normalize_reviewed(b,c,original['numeric_review'],{},defs,made_at=original['record']['forecast_at'])
    assert not rejected['admission']['records'] and not rejected['return_authority']
    review={**original['numeric_review'],'independent':False}
    with pytest.raises(ValueError):R.normalize_reviewed(b,c,review,q,defs,made_at=original['record']['forecast_at'])


def test_no_mature_history_never_fabricates_returns_or_external_review():
    original=original_fixture()
    result=R.calibrate_reviewed([], [original['record']], qualifications=original['qualifications'],
        definitions=original['definitions'],target=original['bundle']['target'],cutoff=original['record']['forecast_at'])
    assert result['status']=='RETURN_CALIBRATION_UNAVAILABLE' and not result['records']


@pytest.mark.parametrize('clock,refused',[
    ('2026-10-12T08:44:14+00:00',False),('2026-10-12T08:44:15+00:00',True),
    ('2026-10-12T09:04:59+00:00',True),('2026-10-12T09:05:00+00:00',False)])
def test_whole_45s_quiet_envelope(clock,refused):
    if refused:
        with pytest.raises(ValueError,match='PROTECTED'):R.quiet_admission(clock)
    else:R.quiet_admission(clock)


def test_exact_fresh_external_launch_authority_not_boolean_self_review():
    now='2026-10-12T12:00:00+00:00';sources={'synthetic-source':'a'*64}
    review={'independent':True,'verdict':'PASS_BOUNDED_BETA_NEWS_CAPTURE_SOURCE',
            'source_pins':sources,'available_at':'2026-10-12T11:59:00+00:00'}
    grant={'schema':'beta_news_actual_root_grant/1','owner':'ROOT','allow_actual_capture':True,
        'after_restoration_reviewed':True,'development_capture_only':True,'prospective_accrual':False,
        'nonce':'1'*32,'output_directory':'/private/capture_'+('1'*32),
        'issued_at':'2026-10-12T11:59:00+00:00','bundle_sha256':'b'*64,
        'source_review_sha256':R.digest(review),'source_pins':sources,
        'limits':{'wall_seconds':30,'rss_bytes':R.RSS_LIMIT,'output_bytes':R.MAX_OUTPUT}}
    R.authorize(grant,now=now,bundle_sha256='b'*64,review=review,actual_sources=sources)
    for changed in ({'issued_at':'2000-01-01T00:00:00+00:00'},{'issued_at':'2027-01-01T00:00:00+00:00'},
                    {'source_review_sha256':'wrong'},{'prospective_accrual':True},{'allow_actual_capture':False}):
        with pytest.raises(ValueError):R.authorize({**grant,**changed},now=now,bundle_sha256='b'*64,review=review,actual_sources=sources)


def test_deepseek_clone_preserves_native_function_and_only_changes_client_options(monkeypatch):
    calls=[]
    class Client:
        _client=SimpleNamespace(_transport_for_url=lambda url:None)
        def with_options(self,**kwargs):calls.append(kwargs);return self
    client=Client()
    namespace={'_get_openai_client':lambda:client}
    exec('def call_named(provider, system, user, *, purpose, max_tokens=None, production_budget=True, model_override=None, no_retry=False, non_thinking=False):\n return {"client":_get_openai_client(),"provider":provider,"scope":(production_budget,model_override,no_retry,non_thinking)}',namespace)
    fake=SimpleNamespace(call_named=namespace['call_named'],_get_openai_client=lambda:client)
    from backend import services
    monkeypatch.setitem(sys.modules,'backend.services.llm_analyzer',fake)
    monkeypatch.setattr(services,'llm_analyzer',fake,raising=False)
    baseline=fake.call_named
    sdk={k:'a'*64 for k in R.SDK_FILES}
    monkeypatch.setattr(R,'sdk_source_pins',lambda **kw:sdk)
    result=R.deepseek_transport(authorized=True,sdk_pins=sdk)('system','user',timeout_s=30,purpose='fixture',max_tokens=256)
    assert len(calls)==1 and calls[0]['timeout']==30 and calls[0]['max_retries']==0 and 'http_client' in calls[0] and fake.call_named is baseline
    assert baseline.__globals__['_get_openai_client'] is namespace['_get_openai_client']
    assert result['scope']==(True,'deepseek-flash',True,True)
    with pytest.raises(ValueError,match='OFF'):R.deepseek_transport()


def test_passive_local_has_no_ensure_or_fallback(monkeypatch):
    import io,urllib.request
    calls=[]
    namespace={}
    exec('def chat(port,prompt,*,cache_prompt=False,timeout=600):\n status,body=http_json(port,"/v1/chat/completions",prompt,timeout=timeout)\n return {"http":status,"text":body["text"],"served_model":"fixture","tokens_in":2,"tokens_out":2}',namespace)
    fake=SimpleNamespace(listener_pid=lambda port:123,chat=namespace['chat'])
    import scripts
    monkeypatch.setitem(sys.modules,'scripts.night_l4_qwen3_measure',fake)
    monkeypatch.setattr(scripts,'night_l4_qwen3_measure',fake,raising=False)
    class Response(io.BytesIO):
        status=200;headers={}
    def open_fake(request,**kw):calls.append((request,kw));return Response(b'{"text":"synthetic"}')
    monkeypatch.setattr(urllib.request,'urlopen',open_fake)
    with pytest.raises(ValueError,match='OWNERSHIP'):R.passive_local_transport({},authorized=True)
    checked=[];transport=R.passive_local_transport({'pid':123,'port':8181},authorized=True,ownership_check=lambda value:checked.append(value))
    result=transport('system','user',timeout_s=30,purpose='fixture',max_tokens=256)
    assert checked and len(calls)==1 and calls[0][1]['timeout']==30 and result['ok']
    assert 'http_json' not in namespace


def test_cli_default_does_not_read_inputs_or_start_any_process(monkeypatch,capsys):
    from scripts import beta_v1_news_capture as CLI
    monkeypatch.setattr(CLI.subprocess,'Popen',lambda *a,**k:pytest.fail('provider/process off'))
    monkeypatch.setattr(R,'read_bound',lambda *a,**k:pytest.fail('no default data read'))
    assert CLI.main([])==2
    assert json.loads(capsys.readouterr().out)['reason']=='PROVIDERS_AND_INPUT_READS_OFF'


def test_new_beta_cache_requires_complete_pinned_owner_and_no_refusal(tmp_path):
    original=original_fixture();sources={'fixture-source':'a'*64}
    payload={'result':{'status':'CAPTURE_PENDING_NUMERIC_REVIEW','capture':original['capture']},'source_pins':sources}
    capture=R.publish(tmp_path,'capture.json',payload)
    index={'namespace':'BETA_NEWS_CAPTURE_V1','capture_path':'capture.json',
        'capture_file_sha256':hashlib.sha256(capture.read_bytes()).hexdigest(),'cache_key':original['capture']['cache_key']}
    (tmp_path/'beta_news_cache_index.jsonl').write_bytes(R.encode(index))
    proof={'schema':'beta_news_outer_completion/1','status':'BOUNDED_PRIVATE_COMPLETION','stage':'capture',
        'worker_reaped':True,'source_pins':sources,'result_file':'capture.json','result_sha256':R.digest(payload),
        'elapsed_seconds_before_proof':5.,'aggregate_peak_upper_bound':64*1024**2,
        'owner_peak_bytes':32*1024**2,'worker_peak_bytes':32*1024**2,'nonce':'fixture-nonce',
        'direct_base_executable':'fixture-base','verified_package_origins':{'numpy':'fixture-site'},
        'verified_identity':{'nonce':'fixture-nonce','pid':123,'sys_executable':'fixture-base','package_origins':{'numpy':'fixture-site'},'user_site_disabled':True},
        'guard':{'status':'BOUNDED_COMPLETION','worker_exit_code':0,'final_owned_handle_peak_proved':True,
            'rss_samples':2,'final_aggregate_high_water_rss_bytes':64*1024**2,'owned_pids':[123]},
        'limits':{'wall_seconds':30,'rss_bytes':R.RSS_LIMIT,'output_bytes':R.MAX_OUTPUT}}
    outer=R.publish(tmp_path,'outer_completion.json',proof,proof=True)
    outer_hash=hashlib.sha256(outer.read_bytes()).hexdigest()
    assert R.load_capture_run(tmp_path,expected_outer_sha256=outer_hash,expected_sources=sources)=={
        original['capture']['cache_key']:original['capture']}
    (tmp_path/'refusal.json').write_bytes(R.encode({'status':'UNAVAILABLE'}))
    with pytest.raises(ValueError,match='REFUSED'):
        R.load_capture_run(tmp_path,expected_outer_sha256=outer_hash,expected_sources=sources)


def test_owned_cli_failure_after_popen_reaps_exact_child_source_contract():
    import ast,inspect
    from scripts import beta_v1_news_capture as CLI
    tree=ast.parse(inspect.getsource(CLI.own)).body[0]
    guarded=next(node for node in tree.body if isinstance(node,ast.Try))
    popens=[node for node in ast.walk(guarded) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='Popen']
    assert len(popens)==1 and guarded.finalbody
    final=ast.dump(ast.Module(body=guarded.finalbody,type_ignores=[]),include_attributes=False)
    assert 'kill' in final and 'wait' in final and 'Close' in final
    assert 'DEVNULL' in ast.dump(popens[0],include_attributes=False)


@pytest.mark.parametrize('phase',['identity','guard','result'])
def test_mocked_owned_launch_failure_always_kills_reaps_and_closes_exact_child(tmp_path,monkeypatch,phase,capsys):
    from scripts import beta_v1_news_capture as CLI, beta_v1_numerical_receipt as G
    sources={'fixture-code':'a'*64};now='2026-10-12T12:00:00+00:00'
    bundle=tmp_path/'bundle.json';bundle.write_bytes(b'{}')
    base=tmp_path/'symbolic-base.exe';base.write_bytes(b'fixture not executable')
    site=tmp_path/'symbolic-site';site.mkdir()
    output=tmp_path/'private-output'
    review={'independent':True,'verdict':'PASS_BOUNDED_BETA_NEWS_CAPTURE_SOURCE','source_pins':sources,
            'available_at':'2026-10-12T11:58:00+00:00'}
    grant={'schema':'beta_news_actual_root_grant/1','owner':'ROOT','allow_actual_capture':True,
        'after_restoration_reviewed':True,'development_capture_only':True,'prospective_accrual':False,
        'nonce':'1'*32,'output_directory':'/private/capture_'+('1'*32),
        'issued_at':'2026-10-12T11:59:00+00:00','bundle_sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),
        'bundle_path':str(bundle),'stage':'capture','private_output_root':str(output),
        'output_directory':str(output/('capture_'+('1'*32))),
        'source_review_sha256':R.digest(review),'source_pins':sources,
        'limits':{'wall_seconds':30,'rss_bytes':R.RSS_LIMIT,'output_bytes':R.MAX_OUTPUT}}
    gp=tmp_path/'grant.json';gp.write_bytes(R.encode(grant));rp=tmp_path/'review.json';rp.write_bytes(R.encode(review))
    monkeypatch.setattr(CLI,'PRIVATE',output);monkeypatch.setattr(CLI,'stamp',lambda:now)
    monkeypatch.setattr(CLI,'memory',lambda handle:(1024**2,2*1024**2))
    monkeypatch.setattr(CLI,'owner_handle',lambda:1);monkeypatch.setattr(CLI,'source_pins',lambda check,**kwargs:sources)
    monkeypatch.setattr(G,'direct_environment',lambda:(base,site,{}))
    children=[]
    class Handle:
        closed=False
        def Close(self):self.closed=True
    class Child:
        def __init__(self,argv,**kwargs):
            self.pid=123;self._handle=Handle();self.returncode=None;self.killed=False;self.waited=False
            directory=Path(argv[argv.index('--directory')+1]);nonce=argv[argv.index('--nonce')+1]
            identity={'pid':123,'nonce':nonce,'sys_executable':str(base.resolve()),'user_site_disabled':True,
                'package_origins':{name:str(site/(name+'.py')) for name in G.DEPENDENCIES}}
            (directory/'identity.json').write_bytes(b'not JSON' if phase=='identity' else R.encode(identity))
            children.append(self)
        def poll(self):return self.returncode
        def kill(self):self.killed=True;self.returncode=9
        def wait(self,timeout):self.waited=True;return self.returncode
    monkeypatch.setattr(CLI.subprocess,'Popen',Child)
    def guard(child,**kwargs):
        assert kwargs['max_seconds']==30 and kwargs['max_rss']==R.RSS_LIMIT
        assert kwargs['final_peak_query'](child)==4*1024**2
        if phase=='guard':raise RuntimeError('PRIVATE_TRANSPORT_EXCEPTION_MUST_NOT_LEAK')
        return {'status':'BOUNDED_COMPLETION'} # fixture only; absent result must still refuse
    monkeypatch.setattr(G,'guard_worker',guard)
    assert CLI.own(SimpleNamespace(grant=str(gp),review=str(rp),bundle=str(bundle),stage='capture'))==2
    assert len(children)==1 and children[0].killed and children[0].waited and children[0]._handle.closed
    assert 'PRIVATE_TRANSPORT_EXCEPTION' not in capsys.readouterr().out



def fresh_bundle():
    original=original_fixture();bundle=deepcopy(original['bundle'])
    pins={'backend/services/beta_v1_news_runtime.py':'d'*64,'scripts/night_l4_qwen3_measure.py':'e'*64}
    review={'independent':True,'verdict':'PASS_BOUNDED_BETA_NEWS_TRANSPORT','route_name':'local_qwen',
        'model_version':bundle['route']['model_version'],'code_pins':pins,'code_hash_domain':'FILE_BYTES_SHA256',
        'allowance_usd':0,'available_at':'2026-10-12T10:00:00+00:00'}
    bundle['route'].update(source_hash=R.digest(pins),source_hash_domain='CANONICAL_JSON_V1',
        independent_review_hash=R.digest(review),review_hash_domain='CANONICAL_JSON_V1')
    return bundle,pins,review


def test_actual_advancing_capture_start_and_completion_not_old_bundle_cutoff():
    bundle,pins,review=fresh_bundle();bundle['decision_at']='2026-10-12T10:30:00+00:00'
    clocks=iter(['2026-10-12T12:00:00+00:00','2026-10-12T12:00:01+00:00']);calls=[]
    def transport(*a,**kw):
        calls.append(1);return {'ok':True,'text':'{"p":0.2,"abstain":false}',
            'served_model':'synthetic','cost_usd':0,'tokens_in':1,'tokens_out':1,'status':'OK'}
    result=R.saved_capture(bundle,transport=transport,clock=lambda:next(clocks),source_pins=pins,transport_review=review)
    assert result['status']=='CAPTURE_PENDING_NUMERIC_REVIEW' and len(calls)==1 and result['cache_hit'] is False and result['capture_origin']=='FRESH_REQUEST' and result['cache_admission_revalidated']
    assert result['capture']['started_at']=='2026-10-12T12:00:00+00:00'
    assert result['capture']['completed_at']=='2026-10-12T12:00:01+00:00'
    assert result['runtime_timing']['deadline_is_not_forecast_or_source_time']
    assert bundle['decision_at']=='2026-10-12T10:30:00+00:00'


@pytest.mark.parametrize('problem',['source_future','identity_future','engine_future','route_future','wrong_code','wrong_review','wrong_allowance','wrong_domain','rollover'])
def test_fresh_admission_refuses_before_spending(problem):
    bundle,pins,review=fresh_bundle();calls=[];start='2026-10-12T12:00:00+00:00'
    if problem=='source_future':bundle['semantic_review']['reviewed_utc']='2026-10-12T12:01:00+00:00'
    elif problem=='identity_future':bundle['identity']['available_at']='2026-10-12T12:01:00+00:00'
    elif problem=='engine_future':bundle['engine_review']['available_at']='2026-10-12T12:01:00+00:00'
    elif problem=='route_future':bundle['route']['available_at']='2026-10-12T12:01:00+00:00'
    elif problem=='wrong_code':pins['backend/services/beta_v1_news_runtime.py']='0'*64
    elif problem=='wrong_review':bundle['route']['independent_review_hash']='0'*64
    elif problem=='wrong_allowance':review['allowance_usd']=1
    elif problem=='wrong_domain':bundle['route']['source_hash_domain']='FILE_BYTES_SHA256'
    else:start='2026-10-12T19:59:50+00:00'
    with pytest.raises(ValueError):R.saved_capture(bundle,transport=lambda *a,**kw:calls.append(1),clock=lambda:start,source_pins=pins,transport_review=review)
    assert calls==[]


def test_transport_chunks_overflow_and_stall_refuse_before_full_parse():
    assert b''.join(R.bounded_chunks([b'a',b'b'],maximum=2))==b'ab'
    with pytest.raises(ValueError,match='BYTE_LIMIT'):list(R.bounded_chunks([b'a',b'bc'],maximum=2))
    calls=[]
    def stall():calls.append(1);raise ValueError('deadline')
    with pytest.raises(ValueError):list(R.bounded_chunks([b'x'],check=stall))
    assert len(calls)==1


@pytest.mark.parametrize('problem',['zero_child','missing_peak','fast_exit','missing_identity','wrong_pid','missing_limit'])
def test_cache_exact_owned_proof_missing_or_zero_refuses(tmp_path,problem):
    original=original_fixture();sources={'fixture':'a'*64};payload={'result':{'status':'CAPTURE_PENDING_NUMERIC_REVIEW','capture':original['capture']},'source_pins':sources}
    capture=R.publish(tmp_path,'capture.json',payload)
    (tmp_path/'beta_news_cache_index.jsonl').write_bytes(R.encode({'namespace':'BETA_NEWS_CAPTURE_V1','capture_path':'capture.json',
        'capture_file_sha256':hashlib.sha256(capture.read_bytes()).hexdigest(),'cache_key':original['capture']['cache_key']}))
    identity={'nonce':'n','pid':123,'sys_executable':'base','package_origins':{'numpy':'site'},'user_site_disabled':True}
    proof={'schema':'beta_news_outer_completion/1','status':'BOUNDED_PRIVATE_COMPLETION','stage':'capture','worker_reaped':True,
        'source_pins':sources,'result_file':'capture.json','result_sha256':R.digest(payload),'elapsed_seconds_before_proof':1,
        'owner_peak_bytes':10,'worker_peak_bytes':10,'aggregate_peak_upper_bound':20,'nonce':'n',
        'verified_identity':identity,'direct_base_executable':'base','verified_package_origins':{'numpy':'site'},
        'guard':{'status':'BOUNDED_COMPLETION','worker_exit_code':0,'final_owned_handle_peak_proved':True,'rss_samples':1,
            'final_aggregate_high_water_rss_bytes':20,'owned_pids':[123]},
        'limits':{'wall_seconds':30,'rss_bytes':R.RSS_LIMIT,'output_bytes':R.MAX_OUTPUT}}
    if problem=='zero_child':proof['worker_peak_bytes']=0
    elif problem=='missing_peak':proof['guard'].pop('final_owned_handle_peak_proved')
    elif problem=='fast_exit':proof['guard']['rss_samples']=0
    elif problem=='missing_identity':proof.pop('verified_identity')
    elif problem=='wrong_pid':proof['guard']['owned_pids']=[999]
    else:proof.pop('limits')
    outer=R.publish(tmp_path,'outer_completion.json',proof,proof=True)
    with pytest.raises(ValueError):R.load_capture_run(tmp_path,expected_outer_sha256=hashlib.sha256(outer.read_bytes()).hexdigest(),expected_sources=sources)


def test_past_only_calibration_nested_review_and_separate_derived_return_review():
    from backend.tests.test_beta_v1_news import normalized,history_rows
    record,defs,target=normalized();history=history_rows(record);q=qualify(history+[record]);cutoff=record['forecast_at']
    for row in history:
        review_at=(R.utc(row['outcome_at'])+timedelta(hours=1)).isoformat()
        receipt={'independent':True,'reviewer':'synthetic-external','decision':'FULL_OUTCOME_ACCEPTED',
            'graded_record_sha256':P.digest(row),'full_outcome_receipt_sha256':'f'*64,'reviewed_at':review_at,'available_at':review_at}
        q[P.digest(row)].update(outcome_review=receipt,outcome_review_sha256=P.digest(receipt),outcome_review_available_at=review_at)
    pending=R.calibrate_reviewed(history,[record],qualifications=q,definitions=defs,target=target,cutoff=cutoff)
    assert pending['status']=='DERIVED_RETURNS_EXTERNAL_REVIEW_UNAVAILABLE' and pending['derivation']['records']
    frozen=pending['derivation'];available=(R.utc(cutoff)+timedelta(seconds=5)).isoformat()
    review={'independent':True,'decision':'FULL_DERIVED_RETURN_ACCEPTED','derivation_sha256':P.digest(frozen),'available_at':available}
    admitted=R.calibrate_reviewed(history,[record],qualifications=q,definitions=defs,target=target,cutoff=cutoff,
        return_review=review,return_qualifications=qualify(frozen['records']),frozen_derivation=frozen,decision_at=available)
    assert admitted['status']=='QUALIFIED_GROSS_RETURN_INPUTS' and admitted['records']
    bad=deepcopy(q);row=history[0];nested=bad[P.digest(row)]['outcome_review'];nested['reviewed_at']='2027-01-01T00:00:00+00:00'
    bad[P.digest(row)]['outcome_review_sha256']=P.digest(nested)
    with pytest.raises(ValueError):R.calibrate_reviewed(history,[record],qualifications=bad,definitions=defs,target=target,cutoff=cutoff)


@pytest.mark.parametrize('problem',['oversize','compressed','stall'])
def test_sdk_response_bound_precedes_full_parse_without_shared_transport_change(monkeypatch,problem):
    import httpx
    parsed=[]
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            if problem=='stall':raise R.RuntimeRefused('TRANSPORT_BODY_DEADLINE')
            yield b'x'*(R.RESPONSE_BYTES+1)
    class Native(httpx.BaseTransport):
        def handle_request(self,request):
            assert request.headers['accept-encoding']=='identity'
            return httpx.Response(200,headers={'content-encoding':'gzip'} if problem=='compressed' else {},stream=Stream())
    native=Native()
    class Client:
        _client=SimpleNamespace(_transport_for_url=lambda url:native)
        def with_options(self,**kw):return SimpleNamespace(http_client=kw['http_client'])
    client=Client();namespace={'_get_openai_client':lambda:client,'parsed':parsed}
    exec('def call_named(provider,system,user,**kw):\n response=_get_openai_client().http_client.get("http://example.test/mocked")\n parsed.append(1)\n return {"status":"OK","text":response.text}',namespace)
    fake=SimpleNamespace(call_named=namespace['call_named'],_get_openai_client=lambda:client)
    from backend import services
    monkeypatch.setitem(sys.modules,'backend.services.llm_analyzer',fake)
    monkeypatch.setattr(services,'llm_analyzer',fake,raising=False)
    sdk={k:'a'*64 for k in R.SDK_FILES}
    monkeypatch.setattr(R,'sdk_source_pins',lambda **kw:sdk)
    with pytest.raises(ValueError):R.deepseek_transport(authorized=True,sdk_pins=sdk)('s','u',timeout_s=30,purpose='fixture',max_tokens=256)
    assert parsed==[] and client._client._transport_for_url(None) is native


@pytest.mark.parametrize('problem',['oversize','compressed','stall'])
def test_passive_local_body_bound_before_json_and_no_server_cancellation_claim(monkeypatch,problem):
    import io,urllib.request
    namespace={}
    exec('def chat(port,prompt,*,cache_prompt=False,timeout=600):\n status,body=http_json(port,"/v1/chat/completions",prompt,timeout=timeout)\n return {"http":status,"text":"parsed"}',namespace)
    fake=SimpleNamespace(chat=namespace['chat'],listener_pid=lambda port:123)
    import scripts
    monkeypatch.setitem(sys.modules,'scripts.night_l4_qwen3_measure',fake)
    monkeypatch.setattr(scripts,'night_l4_qwen3_measure',fake,raising=False)
    class Response(io.BytesIO):
        status=200;headers={'Content-Encoding':'gzip'} if problem=='compressed' else {}
        def read(self,size=-1):
            assert 0<size<=16384
            if problem=='stall':raise R.RuntimeRefused('TRANSPORT_BODY_DEADLINE')
            return super().read(size)
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**kw:Response(b'x'*(R.RESPONSE_BYTES+1)))
    with pytest.raises(ValueError):R.passive_local_transport({'pid':123,'port':8181},authorized=True,
        ownership_check=lambda x:None)('s','u',timeout_s=30,purpose='fixture',max_tokens=256)
    assert 'http_json' not in namespace



def test_sdk_portable_origin_files_hash_and_scope_before_provider(tmp_path,monkeypatch):
    import importlib.util
    site=tmp_path/'site';site.mkdir()
    for key,(package,relative) in R.SDK_FILES.items():
        root=site/package;root.mkdir(exist_ok=True);(root/'__init__.py').write_bytes(b'# synthetic package')
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(key.encode())
    def spec(package):
        return SimpleNamespace(origin=str(site/package/'__init__.py'),submodule_search_locations=[str(site/package)])
    monkeypatch.setattr(importlib.util,'find_spec',spec)
    pins=R.sdk_source_pins(expected_site=site)
    assert set(pins)==set(R.SDK_FILES)
    assert pins['SDK:httpx/_client.py']==hashlib.sha256(b'SDK:httpx/_client.py').hexdigest()
    with pytest.raises(ValueError,match='OUTSIDE'):R.sdk_source_pins(expected_site=tmp_path/'other')
    monkeypatch.setattr(importlib.util,'find_spec',lambda n:SimpleNamespace(origin='built-in',submodule_search_locations=[]))
    with pytest.raises(ValueError,match='ORIGIN'):R.sdk_source_pins(expected_site=site)


def test_sdk_drift_sentinels_before_and_after_call_no_file_mutation(monkeypatch):
    expected={k:'a'*64 for k in R.SDK_FILES};drift={**expected,'SDK:openai/_client.py':'b'*64}
    monkeypatch.setattr(R,'sdk_source_pins',lambda **kw:drift)
    with pytest.raises(ValueError,match='DRIFT'):R.deepseek_transport(authorized=True,sdk_pins=expected)
    calls=[];namespace={}
    class Client:
        _client=SimpleNamespace(_transport_for_url=lambda url:None)
        def with_options(self,**kw):return self
    client=Client();namespace.update(_get_openai_client=lambda:client,calls=calls)
    exec('def call_named(*a,**kw):\n calls.append(1)\n return {"status":"OK","ok":True,"cost_usd":0.001,"tokens_in":3,"tokens_out":2,"text":"original","served_model":"deepseek-flash"}',namespace)
    fake=SimpleNamespace(call_named=namespace['call_named'],_get_openai_client=lambda:client)
    from backend import services
    monkeypatch.setitem(sys.modules,'backend.services.llm_analyzer',fake)
    monkeypatch.setattr(services,'llm_analyzer',fake,raising=False)
    values=iter([expected,expected,drift]);monkeypatch.setattr(R,'sdk_source_pins',lambda **kw:next(values))
    result=R.deepseek_transport(authorized=True,sdk_pins=expected)('s','u',timeout_s=30,purpose='fixture',max_tokens=256)
    assert calls==[1] and result['status']=='ERROR' and result['text'] is None and result['cost_usd']==.001


def test_route_sdk_scope_deepseek_requires_exact_four_local_does_not():
    bundle,pins,review=fresh_bundle()
    R.validate_route(bundle,at='2026-10-12T12:00:00+00:00',source_pins=pins,transport_review=review)
    assert not any(k.startswith('SDK:') for k in pins)
    bundle['route'].update(name='deepseek',model_version='deepseek:deepseek-flash',allowance_usd=.003)
    pins={'backend/services/beta_v1_news_runtime.py':'a'*64,'backend/services/llm_analyzer.py':'b'*64,
        **{k:'c'*64 for k in R.SDK_FILES}}
    review.update(route_name='deepseek',model_version='deepseek:deepseek-flash',allowance_usd=.003,code_pins=pins)
    bundle['route'].update(source_hash=R.digest(pins),independent_review_hash=R.digest(review))
    R.validate_route(bundle,at='2026-10-12T12:00:00+00:00',source_pins=pins,transport_review=review)
    bad={k:v for k,v in pins.items() if k!='SDK:openai/_client.py'}
    with pytest.raises(ValueError):R.validate_route(bundle,at='2026-10-12T12:00:00+00:00',source_pins=bad,transport_review=review)


def test_exact_one_job_directory_replay_refuses_without_overwrite(tmp_path,monkeypatch,capsys):
    from scripts import beta_v1_news_capture as CLI, beta_v1_numerical_receipt as G
    sources={'fixture-code':'a'*64};n='1'*32;root=tmp_path/'private';root.mkdir();directory=root/('capture_'+n);directory.mkdir()
    original=(directory/'outer_completion.json');original.write_bytes(b'original immutable receipt')
    bundle=tmp_path/'bundle.json';bundle.write_bytes(b'{}')
    review={'independent':True,'verdict':'PASS_BOUNDED_BETA_NEWS_CAPTURE_SOURCE','source_pins':sources,'available_at':'2026-10-12T11:58:00+00:00'}
    grant={'schema':'beta_news_actual_root_grant/1','owner':'ROOT','allow_actual_capture':True,'after_restoration_reviewed':True,
        'development_capture_only':True,'prospective_accrual':False,'nonce':n,'output_directory':str(directory),
        'issued_at':'2026-10-12T11:59:00+00:00','bundle_sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),
        'bundle_path':str(bundle),'stage':'capture','private_output_root':str(root),'source_review_sha256':R.digest(review),
        'source_pins':sources,'limits':{'wall_seconds':30,'rss_bytes':R.RSS_LIMIT,'output_bytes':R.MAX_OUTPUT}}
    gp=tmp_path/'grant.json';gp.write_bytes(R.encode(grant));rp=tmp_path/'review.json';rp.write_bytes(R.encode(review))
    monkeypatch.setattr(CLI,'PRIVATE',root);monkeypatch.setattr(CLI,'stamp',lambda:'2026-10-12T12:00:00+00:00')
    monkeypatch.setattr(CLI,'memory',lambda h:(1,2));monkeypatch.setattr(CLI,'owner_handle',lambda:1)
    monkeypatch.setattr(CLI,'source_pins',lambda check,**kw:sources)
    monkeypatch.setattr(CLI.subprocess,'Popen',lambda *a,**kw:pytest.fail('replay must refuse before worker/provider'))
    assert CLI.own(SimpleNamespace(grant=str(gp),review=str(rp),bundle=str(bundle),stage='capture'))==2
    assert original.read_bytes()==b'original immutable receipt' and sorted(p.name for p in directory.iterdir())==['outer_completion.json']



@pytest.mark.parametrize('text,refused',[("A stock split is a corporate action.",False),("\u4e2d"*20,True)])
def test_local_raw_http_central_language_pin_reply_guard_preserves_accounting(monkeypatch,text,refused):
    import io,urllib.request
    from backend.services import llm_language as lang
    monkeypatch.setattr(lang,'REFUSALS',{})
    namespace={}
    exec('def chat(port,prompt,*,cache_prompt=False,timeout=600):\n status,body=http_json(port,"/v1/chat/completions",prompt,timeout=timeout)\n return {"http":status,"text":body["text"],"served_model":"synthetic","tokens_in":11,"tokens_out":7}',namespace)
    fake=SimpleNamespace(chat=namespace['chat'],listener_pid=lambda port:123)
    import scripts
    monkeypatch.setitem(sys.modules,'scripts.night_l4_qwen3_measure',fake)
    monkeypatch.setattr(scripts,'night_l4_qwen3_measure',fake,raising=False)
    requests=[]
    class Response(io.BytesIO):
        status=200;headers={}
    def wire(request,**kw):
        requests.append(json.loads(request.data));return Response(json.dumps({'text':text}).encode())
    monkeypatch.setattr(urllib.request,'urlopen',wire)
    invoke=R.passive_local_transport({'pid':123,'port':8181},authorized=True,ownership_check=lambda v:None)
    result=invoke('synthetic system','synthetic question',timeout_s=30,purpose='integration-fixture',max_tokens=256)
    assert len(requests)==1 and requests[0]['system']==lang.pin('synthetic system')
    assert result['cost_usd']==0.0 and result['tokens_in']==11 and result['tokens_out']==7
    assert result['ok'] is (not refused)
    if refused:
        assert result['text'] is None and result['status']=='LANGUAGE_REFUSED'
        assert result['raw_reply_sha256']==hashlib.sha256(text.encode('utf-8')).hexdigest()
        assert lang.refusals()=={'local_qwen':1}
    else:
        assert result['text']==text and result['status']=='OK' and lang.refusals()=={}
