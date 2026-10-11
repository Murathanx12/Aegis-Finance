"""Opt-in private Beta news IO boundary; providers remain off by default.

No scheduler, native ledger, provider fallback, local server start or stock
selector. Capture transport must run inside the separately admitted CLI owner.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from types import FunctionType

VERSION = "beta_news_runtime/1"
MAX_INPUT = 2*1024**2
MAX_OUTPUT = 1024**2
PROOF_RESERVE = 128*1024
WALL_SECONDS = 30
RSS_LIMIT = 512*1024**2
RESPONSE_BYTES = 256*1024
SDK_FILES = {'SDK:httpx/_client.py':('httpx','_client.py'),
             'SDK:httpx/_models.py':('httpx','_models.py'),
             'SDK:httpx/_transports/base.py':('httpx','_transports/base.py'),
             'SDK:openai/_client.py':('openai','_client.py')}


def sdk_source_pins(*, check=lambda:None, expected_site=None):
    """Portable installed source resolution; no package import/provider call.

    Logical keys are stable across platforms. Each value hashes actual file bytes.
    The actual owner/worker additionally constrain origins to original venv site.
    """
    import importlib.util
    origins={};pins={}
    for key,(package,relative) in SDK_FILES.items():
        check()
        if package not in origins:
            spec=importlib.util.find_spec(package)
            origin=Path(spec.origin) if spec and isinstance(spec.origin,str) else None
            if origin is None or origin.name!='__init__.py' or origin.is_symlink() or not origin.is_file():
                raise RuntimeRefused('SDK_SOURCE_ORIGIN_UNAVAILABLE')
            base=origin.parent.resolve()
            if expected_site is not None and base.parent!=Path(expected_site).resolve():
                raise RuntimeRefused('SDK_ORIGIN_OUTSIDE_ORIGINAL_SITE')
            locations=getattr(spec,'submodule_search_locations',None)
            if not locations or {Path(v).resolve() for v in locations}!={base}:
                raise RuntimeRefused('SDK_PACKAGE_ORIGIN_AMBIGUOUS')
            origins[package]=base
        base=origins[package];path=base/relative
        if path.is_symlink() or not path.resolve().is_relative_to(base):
            raise RuntimeRefused('SDK_SOURCE_ORIGIN_UNAVAILABLE')
        pins[key]=hashlib.sha256(read_bound(path,check=check)).hexdigest()
    check();return pins



class RuntimeRefused(ValueError):
    pass


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2,
                       allow_nan=False)+"\n").encode("utf-8")


def strict_json(raw, *, maximum=MAX_INPUT):
    if not isinstance(raw, bytes) or len(raw) > maximum:
        raise RuntimeRefused("INPUT_SIZE_UNAVAILABLE")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeRefused("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(RuntimeRefused("NONFINITE_JSON")))
        pending=[(result,0)];nodes=0
        while pending:
            value,depth=pending.pop();nodes+=1
            if depth>100 or nodes>100000:raise RuntimeRefused("JSON_STRUCTURE_LIMIT")
            if isinstance(value,float) and not math.isfinite(value):raise RuntimeRefused("NONFINITE_JSON")
            if isinstance(value,dict):pending.extend((v,depth+1) for v in value.values())
            elif isinstance(value,list):pending.extend((v,depth+1) for v in value)
        return result
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise RuntimeRefused("INVALID_COMPLETE_JSON") from None


def utc(value):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError()
        return stamp.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise RuntimeRefused("AWARE_CLOCK_UNAVAILABLE") from None


def quiet_admission(now, *, envelope=45):
    now = utc(now) if isinstance(now, str) else now
    if now.tzinfo is None:
        raise RuntimeRefused("AWARE_CLOCK_UNAVAILABLE")
    now = now.astimezone(timezone.utc)
    end = now+timedelta(seconds=envelope)
    for offset in (0, 1):
        day = (now+timedelta(days=offset)).date()
        start = datetime(day.year, day.month, day.day, 8, 45, tzinfo=timezone.utc)
        stop = start+timedelta(minutes=20)
        if now < stop and end >= start:
            raise RuntimeRefused("PROTECTED_WINDOW_ENVELOPE")


def authorize(grant, *, now, bundle_sha256, review, actual_sources):
    """External reviewed ROOT grant, not a self-issued launch receipt."""
    if any(k.startswith('SDK:') for k in actual_sources):
        if grant.get('source_pin_hash_domain')!='FILE_BYTES_SHA256' or review.get('source_pin_hash_domain')!='FILE_BYTES_SHA256':
            raise RuntimeRefused('SDK_SOURCE_HASH_DOMAIN_UNAVAILABLE')
    nonce=grant.get('nonce')
    if not isinstance(nonce,str) or len(nonce)!=32 or any(c not in '0123456789abcdef' for c in nonce) or not isinstance(grant.get('output_directory'),str):
        raise RuntimeRefused('EXACT_ONE_JOB_GRANT_UNAVAILABLE')
    clock = utc(now)
    quiet_admission(clock)
    issued = utc(grant.get("issued_at"))
    if not issued <= clock <= issued+timedelta(seconds=600):
        raise RuntimeRefused("FRESH_ROOT_GRANT_UNAVAILABLE")
    if (grant.get("schema") != "beta_news_actual_root_grant/1"
            or grant.get("owner") != "ROOT" or grant.get("allow_actual_capture") is not True
            or grant.get("after_restoration_reviewed") is not True
            or grant.get("development_capture_only") is not True
            or grant.get("prospective_accrual") is not False
            or grant.get("bundle_sha256") != bundle_sha256
            or grant.get("source_review_sha256") != digest(review)
            or review.get("independent") is not True
            or review.get("verdict") != "PASS_BOUNDED_BETA_NEWS_CAPTURE_SOURCE"
            or review.get("source_pins") != actual_sources
            or grant.get("source_pins") != actual_sources
            or utc(review.get("available_at")) > clock
            or grant.get("limits") != {"wall_seconds":30,"rss_bytes":RSS_LIMIT,"output_bytes":MAX_OUTPUT}):
        raise RuntimeRefused("EXACT_CAPTURE_AUTHORITY_UNAVAILABLE")


def read_bound(path, *, expected_sha256=None, check=lambda: None, maximum=MAX_INPUT):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise RuntimeRefused("INPUT_PATH_SIZE_UNAVAILABLE")
    parts, size = [], 0
    with path.open("rb") as stream:
        while True:
            check()
            part = stream.read(65536)
            if not part:
                break
            size += len(part)
            if size > maximum:
                raise RuntimeRefused("INPUT_SIZE_UNAVAILABLE")
            parts.append(part)
    raw = b"".join(parts)
    if expected_sha256 and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise RuntimeRefused("INPUT_HASH_DRIFT")
    check()
    return raw


def publish(directory, name, value, *, check=lambda: None, proof=False):
    """One writer owns a newly exclusive run directory. Never overwrite a file."""
    from backend.services import disk_guard as DG
    directory = Path(directory)
    if directory.is_symlink():raise RuntimeRefused("OUTPUT_DIRECTORY_AMBIGUOUS")
    directory = directory.resolve()
    if name not in {"capture.json", "candidate.json", "returns.json", "route.json",
                    "identity.json", "ack.json", "outer_completion.json", "refusal.json"}:
        raise RuntimeRefused("OUTPUT_NAME_UNAVAILABLE")
    target = directory/name
    if target.exists() or target.is_symlink():
        raise RuntimeRefused("IMMUTABLE_OUTPUT_EXISTS")
    raw = encode(value)
    existing = 0
    for item in directory.iterdir():
        if item.is_symlink() or not item.is_file():
            raise RuntimeRefused("OUTPUT_DIRECTORY_AMBIGUOUS")
        existing += item.stat().st_size
    cap = MAX_OUTPUT if proof else MAX_OUTPUT-PROOF_RESERVE
    # Account for the atomic temporary file as well as its committed target.
    if existing+2*len(raw) > cap:
        raise RuntimeRefused("OUTPUT_TOTAL_LIMIT")
    check()
    DG.atomic_write_text(target, raw.decode("utf-8"), check_json=True)
    check()
    return target


def validate_engine_bundle(bundle):
    from backend.services import beta_v1_policy as P
    manifest = bundle.get("engine_review", {})
    if (manifest.get("independent") is not True
            or manifest.get("selection_method") != "ENGINE_IDENTITY_INTERSECTION"
            or manifest.get("candidate_hash") != P.digest(bundle["candidates"])
            or manifest.get("identity_hash") != P.digest(bundle["identity"])
            or utc(manifest.get("available_at")) > utc(bundle["decision_at"])
            or not bundle["target"].get("benchmark_security_id")
            or not bundle["target"].get("price_basis_id")):
        raise RuntimeRefused("ENGINE_IDENTITY_OR_BENCHMARK_REVIEW_UNAVAILABLE")


def validate_route(bundle, *, at, source_pins, transport_review):
    """Hash domains are explicit: code FILE_BYTES, receipts CANONICAL_JSON_V1."""
    route=bundle['route'];review=transport_review
    required=({'backend/services/beta_v1_news_runtime.py','backend/services/llm_analyzer.py'}|set(SDK_FILES)) if route['name']=='deepseek' else {'backend/services/beta_v1_news_runtime.py','scripts/night_l4_qwen3_measure.py'}
    pins=review.get('code_pins',{})
    if (review.get('independent') is not True or review.get('verdict')!='PASS_BOUNDED_BETA_NEWS_TRANSPORT'
            or review.get('route_name')!=route['name'] or review.get('model_version')!=route['model_version']
            or set(pins)!=required or any(source_pins.get(k)!=v for k,v in pins.items())
            or review.get('code_hash_domain')!='FILE_BYTES_SHA256'
            or route.get('source_hash_domain')!='CANONICAL_JSON_V1'
            or route.get('review_hash_domain')!='CANONICAL_JSON_V1'
            or route.get('source_hash')!=digest(pins)
            or route.get('independent_review_hash')!=digest(review)
            or review.get('allowance_usd')!=route.get('allowance_usd')
            or utc(review.get('available_at'))>utc(at)
            or utc(route.get('available_at'))>utc(at)):
        raise RuntimeRefused('EXACT_TRANSPORT_ROUTE_REVIEW_UNAVAILABLE')


def saved_capture(bundle, *, transport=None, cache=None, check=lambda: None,
                  clock=None, remaining_seconds=WALL_SECONDS, source_pins=None, transport_review=None, cache_observation_at=None):
    from backend.services import beta_v1_news as N, world_digest as WD, news_source_validation as NV
    from copy import deepcopy
    item=WD.Item(**bundle['item'])
    if cache is not None:
        if cache_observation_at is not None:bundle={**bundle,'decision_at':cache_observation_at}
        # Historical/cache admission uses the supplied original formation cutoff,
        # not a fresh request and never spends a second call.
        validate_engine_bundle(bundle);check()
        result=N.capture_question(item,bundle['source_capture'],bundle['semantic_review'],
            identity=bundle['identity'],candidates=bundle['candidates'],target=bundle['target'],
            decision_at=bundle['decision_at'],route=bundle['route'],cache=cache)
        result['capture_origin']='REUSED_CACHE'
        result['cache_admission_revalidated']=result.get('cache_hit') is True
        return result
    bundle=deepcopy(bundle)
    actual_clock=clock or (lambda:datetime.now(timezone.utc).isoformat())
    start=actual_clock();started=utc(start);check()
    if type(remaining_seconds) not in (int,float) or not math.isfinite(remaining_seconds) or not 0<remaining_seconds<=WALL_SECONDS:
        raise RuntimeRefused('ACTUAL_REMAINING_DEADLINE_UNAVAILABLE')
    if transport is None:raise RuntimeRefused('PROVIDERS_OFF')
    start_bundle=deepcopy(bundle);start_bundle['decision_at']=start
    validate_engine_bundle(start_bundle)
    NV.admit_current(item,bundle['source_capture'],semantic_review=bundle['semantic_review'],cutoff_utc=start)
    N._identity(item,bundle['identity'],bundle['candidates'],start);N._target(bundle['target'],start)
    validate_route(bundle,at=start,source_pins=source_pins or {},transport_review=transport_review or {})
    deadline=(started+timedelta(seconds=remaining_seconds)).isoformat()
    # Deadline is only an upper bound. Refuse potential target rollover before spending.
    N._target(bundle['target'],deadline)
    clocks=[start]
    def actual_capture_clock():
        if clocks:return clocks.pop()
        value=actual_clock();check();return value
    result=N.capture_question(item,bundle['source_capture'],bundle['semantic_review'],
        identity=bundle['identity'],candidates=bundle['candidates'],target=bundle['target'],
        decision_at=deadline,route=bundle['route'],transport=transport,clock=actual_capture_clock)
    capture=result.get('capture')
    if capture is None:return result  # preserve failed spend/capture diagnostics from frozen boundary
    completion=capture['completed_at'];check()
    try:
        if capture['started_at']!=start or not started<=utc(completion)<=utc(deadline):
            raise RuntimeRefused('ACTUAL_CAPTURE_CLOCK_UNAVAILABLE')
        N._target(bundle['target'],completion)
        completed_bundle=deepcopy(bundle);completed_bundle['decision_at']=completion
        validate_engine_bundle(completed_bundle)
        admitted=N.capture_question(item,bundle['source_capture'],bundle['semantic_review'],
            identity=bundle['identity'],candidates=bundle['candidates'],target=bundle['target'],
            decision_at=completion,route=bundle['route'],cache={capture['cache_key']:capture})
        admitted['cache_hit']=False
        admitted['cache_admission_revalidated']=True
        admitted['capture_origin']='FRESH_REQUEST'
        admitted['runtime_timing']={'actual_start_at':start,'actual_completed_at':completion,
            'request_deadline_at':deadline,'deadline_is_not_forecast_or_source_time':True}
        return admitted
    except (ValueError,TypeError):
        return {'status':'UNAVAILABLE','reason':'ACTUAL_COMPLETION_OR_TARGET_ROLLOVER_UNAVAILABLE',
            'failed_capture':capture,'records':[],'return_authority':False}


def normalize_reviewed(bundle, capture, numeric_review, qualifications, definitions, *, made_at):
    from backend.services import beta_v1_news as N, news_source_validation as NV
    recheck = saved_capture({**bundle,"decision_at":made_at}, cache={capture["cache_key"]:capture})
    if recheck.get("capture_hash") != NV.content_sha256(capture):
        raise RuntimeRefused("SAVED_CAPTURE_REVALIDATION_UNAVAILABLE")
    row = N.candidate_record(capture, numeric_review, made_at=made_at)
    admission = N.admit_record(row, qualifications, definitions=definitions, cutoff=made_at)
    return {"status": admission["status"], "candidate": row, "admission": admission,
            "capture_sha256": NV.content_sha256(capture), "return_authority":False}


def load_capture_run(directory, *, expected_outer_sha256, expected_sources, check=lambda:None):
    """Explicit new-Beta cache only; no failed/incomplete/legacy run reuse."""
    directory=Path(directory)
    if (not isinstance(expected_outer_sha256,str) or len(expected_outer_sha256)!=64
            or any(c not in "0123456789abcdef" for c in expected_outer_sha256)):
        raise RuntimeRefused("CACHE_OWNER_PIN_UNAVAILABLE")
    if directory.is_symlink():raise RuntimeRefused("CACHE_RUN_REFUSED")
    directory=directory.resolve()
    if directory.is_symlink() or (directory/"refusal.json").exists():
        raise RuntimeRefused("CACHE_RUN_REFUSED")
    proof=strict_json(read_bound(directory/"outer_completion.json",expected_sha256=expected_outer_sha256,check=check))
    if (proof.get("schema")!="beta_news_outer_completion/1" or proof.get("status")!="BOUNDED_PRIVATE_COMPLETION"
            or proof.get("stage")!="capture" or proof.get("worker_reaped") is not True
            or proof.get("source_pins")!=expected_sources or proof.get("result_file")!="capture.json"
            or type(proof.get("elapsed_seconds_before_proof")) not in (int,float)
            or not 0<=proof["elapsed_seconds_before_proof"]<WALL_SECONDS
            or type(proof.get("aggregate_peak_upper_bound")) is not int
            or not 0<proof["aggregate_peak_upper_bound"]<RSS_LIMIT):
        raise RuntimeRefused("CACHE_OWNER_PROOF_UNAVAILABLE")
    expected_sdk={k:v for k,v in expected_sources.items() if k.startswith('SDK:')}
    if expected_sdk and (proof.get('sdk_code_pins')!=expected_sdk or proof.get('source_pin_hash_domain')!='FILE_BYTES_SHA256'):
        raise RuntimeRefused('CACHE_SDK_CODE_PROOF_UNAVAILABLE')
    guard=proof.get('guard',{});identity=proof.get('verified_identity',{})
    peaks=[proof.get(k) for k in ('owner_peak_bytes','worker_peak_bytes')]
    if (any(type(v) is not int or v<=0 for v in peaks)
            or sum(peaks)!=proof['aggregate_peak_upper_bound']
            or guard.get('status')!='BOUNDED_COMPLETION' or guard.get('worker_exit_code')!=0
            or guard.get('final_owned_handle_peak_proved') is not True
            or type(guard.get('rss_samples')) is not int or guard['rss_samples']<=0
            or type(guard.get('final_aggregate_high_water_rss_bytes')) is not int
            or not 0<guard['final_aggregate_high_water_rss_bytes']<=proof['aggregate_peak_upper_bound']
            or identity.get('nonce')!=proof.get('nonce') or type(identity.get('pid')) is not int or identity['pid']<=0
            or guard.get('owned_pids')!=[identity['pid']] or not identity.get('package_origins')
            or identity.get('sys_executable')!=proof.get('direct_base_executable')
            or identity.get('package_origins')!=proof.get('verified_package_origins')
            or identity.get('user_site_disabled') is not True
            or proof.get('limits')!={'wall_seconds':WALL_SECONDS,'rss_bytes':RSS_LIMIT,'output_bytes':MAX_OUTPUT}):
        raise RuntimeRefused('CACHE_EXACT_OWNED_PROOF_UNAVAILABLE')
    index=strict_json(read_bound(directory/"beta_news_cache_index.jsonl",check=check,maximum=65536))
    if index.get("namespace")!="BETA_NEWS_CAPTURE_V1" or index.get("capture_path")!="capture.json":
        raise RuntimeRefused("CACHE_INDEX_UNAVAILABLE")
    raw=read_bound(directory/"capture.json",expected_sha256=index.get("capture_file_sha256"),check=check)
    payload=strict_json(raw)
    if proof.get("result_sha256")!=digest(payload) or payload.get("source_pins")!=expected_sources:
        raise RuntimeRefused("CACHE_CAPTURE_DRIFT")
    result=payload.get("result",{})
    if result.get("status") not in {"CAPTURE_PENDING_NUMERIC_REVIEW","ABSTAIN"} or result["capture"]["cache_key"]!=index.get("cache_key"):
        raise RuntimeRefused("CACHE_CAPTURE_UNAVAILABLE")
    return {index["cache_key"]:result["capture"]}


def calibrate_reviewed(history, current, *, qualifications, definitions, target, cutoff,
                       return_review=None, return_qualifications=None,
                       frozen_derivation=None, decision_at=None):
    from backend.services import beta_v1_news as N, beta_v1_policy as P
    observed=decision_at or cutoff
    for row in history:
        q = qualifications.get(P.digest(row), {})
        review=q.get("outcome_review",{})
        if (not q.get("outcome_review_sha256") or q["outcome_review_sha256"]!=P.digest(review)
                or review.get("independent") is not True or not review.get("reviewer")
                or review.get("decision")!="FULL_OUTCOME_ACCEPTED"
                or review.get("graded_record_sha256")!=P.digest(row)
                or not review.get("full_outcome_receipt_sha256")
                or utc(q.get("outcome_review_available_at"))!=utc(review.get('available_at'))
                or not utc(row['label_end_at'])<=utc(row['outcome_at'])<=utc(review.get('reviewed_at'))<=utc(review.get('available_at'))<=utc(cutoff)):
            raise RuntimeRefused("EXTERNAL_OUTCOME_REVIEW_UNAVAILABLE")
    result = N.calibrated_returns(history, current, qualifications=qualifications,
        definitions=definitions, target=target, cutoff=cutoff)
    if not result["records"]:
        return result
    if (not return_review or return_review.get("independent") is not True
            or return_review.get("decision") != "FULL_DERIVED_RETURN_ACCEPTED"
            or return_review.get("derivation_sha256") != P.digest(result)
            or frozen_derivation is None or P.digest(frozen_derivation)!=P.digest(result)
            or not utc(cutoff)<=utc(return_review.get("available_at"))<=utc(observed)):
        return {"status":"DERIVED_RETURNS_EXTERNAL_REVIEW_UNAVAILABLE", "derivation":result,"records":[]}
    rows, rejected, counts = P._admit(result["records"], return_qualifications or {},
        definitions=definitions, task="expected_excess_return", horizon=target["horizon"],
        objective_version=result["records"][0]["objective_version"], cutoff=P._clock(observed), grade=False)
    return {"status":"QUALIFIED_GROSS_RETURN_INPUTS" if rows else "UNAVAILABLE",
            "records":[r for r in result["records"] if P.digest(r) in {v["record_hash"] for v in rows}],
            "derivation":result,"return_review_sha256":P.digest(return_review),"rejected":rejected,"counts":counts}


def bounded_chunks(chunks, *, check=lambda:None, maximum=RESPONSE_BYTES):
    total=0
    for chunk in chunks:
        check()
        if not isinstance(chunk,bytes):raise RuntimeRefused('TRANSPORT_BODY_TYPE_UNAVAILABLE')
        if total+len(chunk)>maximum:raise RuntimeRefused('TRANSPORT_BODY_BYTE_LIMIT')
        total+=len(chunk);yield chunk
    check()


def deepseek_transport(*, authorized=False, sdk_pins=None, expected_site=None, owner_check=lambda:None):
    """Bound raw SDK body before SDK buffering/parsing; preserve native call code."""
    if not authorized:raise RuntimeRefused('PROVIDERS_OFF')
    if not isinstance(sdk_pins,dict) or set(sdk_pins)!=set(SDK_FILES):raise RuntimeRefused('SDK_CODE_PINS_UNAVAILABLE')
    if sdk_source_pins(check=owner_check,expected_site=expected_site)!=sdk_pins:raise RuntimeRefused('SDK_SOURCE_DRIFT')
    from backend.services import llm_analyzer as LA
    import httpx
    def invoke(system,user,*,timeout_s,purpose,max_tokens):
        if timeout_s!=30:raise RuntimeRefused('TRANSPORT_TIMEOUT_UNAVAILABLE')
        started=time.monotonic()
        def check():
            owner_check()
            if time.monotonic()-started>=30:raise RuntimeRefused('TRANSPORT_BODY_DEADLINE')
        if sdk_source_pins(check=check,expected_site=expected_site)!=sdk_pins:raise RuntimeRefused('SDK_SOURCE_DRIFT')
        client=LA._get_openai_client()
        if client is None:raise RuntimeRefused('NAMED_PROVIDER_UNAVAILABLE')
        native_http=getattr(client,'_client',None)
        select_transport=getattr(native_http,'_transport_for_url',None)
        if select_transport is None:raise RuntimeRefused('BOUNDED_SDK_TRANSPORT_UNAVAILABLE')
        class Stream(httpx.SyncByteStream):
            def __init__(self,stream):self.stream=stream
            def __iter__(self):yield from bounded_chunks(iter(self.stream),check=check)
            def close(self):self.stream.close()
        class Transport(httpx.BaseTransport):
            def handle_request(self,request):
                check();request.headers['accept-encoding']='identity'
                response=select_transport(request.url).handle_request(request)
                try:
                    if response.headers.get('content-encoding','identity').lower() not in ('','identity'):
                        raise RuntimeRefused('TRANSPORT_DECOMPRESSION_UNAVAILABLE')
                    length=response.headers.get('content-length')
                    if length is not None and (int(length)<0 or int(length)>RESPONSE_BYTES):raise RuntimeRefused('TRANSPORT_BODY_BYTE_LIMIT')
                    check()
                    return httpx.Response(response.status_code,headers=response.headers,stream=Stream(response.stream),extensions=response.extensions)
                except Exception:response.close();raise
            def close(self):pass  # borrowed native pool must not be closed or mutated
        with httpx.Client(transport=Transport(),timeout=30,trust_env=False) as bounded_client:
            scoped_client=client.with_options(timeout=30,max_retries=0,http_client=bounded_client)
            namespace={**LA.call_named.__globals__,'_get_openai_client':lambda:scoped_client}
            call=FunctionType(LA.call_named.__code__,namespace,LA.call_named.__name__,LA.call_named.__defaults__)
            call.__kwdefaults__=dict(LA.call_named.__kwdefaults__ or {})
            result=call('deepseek',system,user,purpose=purpose,max_tokens=max_tokens,
                production_budget=True,model_override='deepseek-flash',no_retry=True,non_thinking=True)
            check()
            if result.get('status') in {'ERROR','RATE_LIMITED','BREAKING_BUDGET','BREAKER_OPEN'}:
                result={**result,'cost_usd':None,'spend_status':'UNAVAILABLE_NO_RETURNED_USAGE'}
                result.pop('error',None)
            if sdk_source_pins(check=check,expected_site=expected_site)!=sdk_pins:
                # Preserve actual returned usage/cost while refusing prediction authority.
                return {**result,'ok':False,'text':None,'status':'ERROR',
                    'error':'SDK_SOURCE_DRIFT','source_revalidation':'FAILED'}
            return result
    return invoke


def passive_local_transport(ownership,*,authorized=False,ownership_check=None):
    """Private clone of existing raw chat with bounded loopback body reader.

    Owned client deadline/RSS does not cancel or qualify the preexisting server.
    """
    if not authorized or ownership_check is None:raise RuntimeRefused('PASSIVE_LOCAL_OWNERSHIP_UNAVAILABLE')
    from scripts import night_l4_qwen3_measure as L4
    from backend.services import llm_language as _lang
    import urllib.request,urllib.error
    def invoke(system,user,*,timeout_s,purpose,max_tokens):
        start=time.monotonic()
        def check():
            if time.monotonic()-start>=30:raise RuntimeRefused('TRANSPORT_BODY_DEADLINE')
        ownership_check(ownership);check()
        if timeout_s!=30 or L4.listener_pid(ownership['port'])!=ownership['pid']:raise RuntimeRefused('PASSIVE_LOCAL_OWNERSHIP_UNAVAILABLE')
        def http_json(port,path,payload=None,*,timeout=30,host='127.0.0.1'):
            if host!='127.0.0.1' or port!=ownership['port'] or path!='/v1/chat/completions':raise RuntimeRefused('PASSIVE_LOCAL_ROUTE_UNAVAILABLE')
            request=urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=json.dumps(payload).encode(),method='POST',
                headers={'Content-Type':'application/json','Accept-Encoding':'identity'})
            check()
            try:
                with urllib.request.urlopen(request,timeout=min(timeout,30)) as response:
                    if response.headers.get('Content-Encoding','identity').lower() not in ('','identity'):raise RuntimeRefused('TRANSPORT_DECOMPRESSION_UNAVAILABLE')
                    length=response.headers.get('Content-Length')
                    if length is not None and (int(length)<0 or int(length)>RESPONSE_BYTES):raise RuntimeRefused('TRANSPORT_BODY_BYTE_LIMIT')
                    def pieces():
                        while True:
                            check();part=response.read(16384)
                            if not part:break
                            yield part
                    raw=b''.join(bounded_chunks(pieces(),check=check));check()
                    return response.status,strict_json(raw,maximum=RESPONSE_BYTES)
            except urllib.error.HTTPError as exc:return int(exc.code),None
        namespace={**L4.chat.__globals__,'http_json':http_json}
        chat=FunctionType(L4.chat.__code__,namespace,L4.chat.__name__,L4.chat.__defaults__)
        chat.__kwdefaults__=dict(L4.chat.__kwdefaults__ or {})
        response=chat(ownership['port'],{'system':_lang.pin(system),'user':user,'max_tokens':max_tokens},cache_prompt=False,timeout=30);check()
        text=response.get('text')
        if isinstance(text,str) and _lang.refuse('local_qwen',purpose,text):
            return {'ok':False,'text':None,'served_model':response.get('served_model'),
                'cost_usd':0.0,'tokens_in':response.get('tokens_in'),'tokens_out':response.get('tokens_out'),
                'status':'LANGUAGE_REFUSED','raw_reply_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest()}
        return {'ok':response.get('http')==200 and bool(response.get('text')),'text':response.get('text'),
            'served_model':response.get('served_model'),'cost_usd':0.0,'tokens_in':response.get('tokens_in'),
            'tokens_out':response.get('tokens_out'),'status':'OK' if response.get('http')==200 and response.get('text') else 'ERROR'}
    return invoke
