"""Opt-in private Beta capture owner. No provider/read occurs without ROOT grant.

Defaults are OFF. No legacy digest/forecast ledger, model lifecycle or scheduler
entry point is called. Arguments contain file paths/nonces, never prompts/keys.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path("C:/Users/mrthn/aegis-recovery-evidence/beta-build-sprint-20261011/beta-news-capture-runs")
SOURCES = ("scripts/beta_v1_news_capture.py", "backend/services/beta_v1_news_runtime.py",
    "backend/services/beta_v1_news_outcomes.py", "backend/services/beta_v1_news.py",
    "backend/tests/test_beta_v1_news_runtime.py", "backend/tests/test_beta_v1_news_outcomes.py",
    "docs/TRIALS/TRIAL-BETA-V1-SHADOW-20261011.md", "docs/TRIALS/TRIAL-BETA-V1-NEWS-CAPTURE-20261012.md",
    "backend/services/world_digest.py", "backend/services/news_source_validation.py", "backend/services/disk_guard.py",
    "backend/services/beta_v1_policy.py", "backend/services/beta_v1_replay.py",
    "backend/services/beta_v1_legacy_kernels.py", "backend/services/expected_return.py",
    "backend/services/forecast_reputation.py", "backend/services/llm_analyzer.py",
    "backend/services/llm_telemetry.py", "backend/services/llama_server.py", "backend/services/llm_language.py",
    "backend/config.py", "scripts/night_l4_qwen3_measure.py", "scripts/beta_v1_numerical_receipt.py")
ASML_SOURCES = ("backend/services/asml_current_adapter.py", "backend/services/issuer_ir_current_case.py",
    "backend/services/issuer_ir_html.py", "backend/services/news_registry.py",
    "backend/data/news_sources.yaml", "backend/data/news_entities/issuers.csv",
    "docs/TRIALS/MEASUREMENT_ASML_IR_CURRENT_1.md")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def memory(handle):
    """Exact Windows HANDLE counters; private prototypes, no ctypes globals."""
    if os.name != "nt":
        raise RuntimeError("OWNED_WINDOWS_RESOURCE_PROOF_UNAVAILABLE")
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[("cb",wintypes.DWORD),("faults",wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
            ("peak","rss","quota_peak_paged","quota_paged","quota_peak_nonpaged","quota_nonpaged","pagefile","peak_pagefile")]
    api=ctypes.WinDLL("psapi",use_last_error=True).GetProcessMemoryInfo
    api.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD];api.restype=wintypes.BOOL
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    if not api(handle,ctypes.byref(counters),counters.cb):
        raise RuntimeError("OWNED_RESOURCE_QUERY_UNAVAILABLE")
    if type(counters.peak) is not int or counters.peak<=0 or counters.rss<0 or counters.rss>counters.peak:
        raise RuntimeError('POSITIVE_OWNED_PEAK_PROOF_UNAVAILABLE')
    return int(counters.rss),int(counters.peak)


def owner_handle():
    from ctypes import wintypes
    api=ctypes.WinDLL("kernel32",use_last_error=True).GetCurrentProcess
    api.argtypes=[];api.restype=wintypes.HANDLE
    return api()


def server_identity(pid):
    """Read-only exact process identity; never stop/ensure/start the server."""
    from ctypes import wintypes
    api=ctypes.WinDLL("kernel32",use_last_error=True)
    api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
    api.CloseHandle.argtypes=[wintypes.HANDLE];api.CloseHandle.restype=wintypes.BOOL
    api.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4;api.GetProcessTimes.restype=wintypes.BOOL
    api.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)];api.QueryFullProcessImageNameW.restype=wintypes.BOOL
    handle=api.OpenProcess(0x1000,False,pid)
    if not handle:raise RuntimeError("PASSIVE_LOCAL_PROCESS_UNAVAILABLE")
    try:
        times=[wintypes.FILETIME() for _ in range(4)];image=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(image))
        if not api.GetProcessTimes(handle,*[ctypes.byref(v) for v in times]) or not api.QueryFullProcessImageNameW(handle,0,image,ctypes.byref(size)):
            raise RuntimeError("PASSIVE_LOCAL_IDENTITY_UNAVAILABLE")
        return {"pid":pid,"creation_filetime":(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime,
                "image_path":str(Path(image.value).resolve())}
    finally:
        api.CloseHandle(handle)


def source_pins(check, *, provider=None, expected_site=None, stage=None):
    from backend.services import beta_v1_news_runtime as R
    pins={name:hashlib.sha256(R.read_bound(ROOT/name,check=check)).hexdigest() for name in SOURCES}
    if stage=="asml-current":
        pins.update({name:hashlib.sha256(R.read_bound(ROOT/name,check=check)).hexdigest()
                     for name in ASML_SOURCES})
    if provider=='deepseek':pins.update(R.sdk_source_pins(check=check,expected_site=expected_site))
    return pins


def returned_refusal_evidence(directory):
    """Read only the immutable post-return file, even after STOP/deadline."""
    from backend.services import beta_v1_news_runtime as R
    native_file=Path(directory)/"native_return.json"
    if not native_file.is_file() or native_file.is_symlink():return {}
    native_raw=R.read_bound(native_file,maximum=R.MAX_OUTPUT)
    native=R.strict_json(native_raw,maximum=R.MAX_OUTPUT).get("result",{})
    return {"native_return_file_sha256":hashlib.sha256(native_raw).hexdigest(),
        "served_model":native.get("served_model"),
        "tokens_in":native.get("tokens_in"),"tokens_out":native.get("tokens_out"),
        "cost_usd":native.get("cost_usd"),"cost_status":native.get("cost_status"),
        "usage_status":(native.get("evidence") or {}).get("usage_status"),
        "provider_spend_status":"RETURNED_NATIVE_EVIDENCE_RETAINED"}


def worker(args):
    # Stdlib-only identity before analytical imports. Owner acknowledges actual
    # PID/base/package origin/nonce; child has no analytical file access before it.
    from scripts import beta_v1_numerical_receipt as G
    directory=Path(args.directory)
    if directory.is_symlink():raise RuntimeError("OWNED_PRIVATE_DIRECTORY_UNAVAILABLE")
    directory=directory.resolve()
    if directory.parent!=PRIVATE.resolve() or directory.name!="capture_"+args.nonce:
        raise RuntimeError("OWNED_PRIVATE_DIRECTORY_UNAVAILABLE")
    identity=G.worker_identity(args.nonce)
    raw=(json.dumps(identity,sort_keys=True)+"\n").encode()
    with (directory/"identity.json").open("xb") as stream:stream.write(raw)
    waited=time.monotonic()
    while not (directory/"ack.json").exists():
        if time.monotonic()-waited>5:raise RuntimeError("IDENTITY_ACK_UNAVAILABLE")
        time.sleep(.02)
    from backend.services import beta_v1_news_runtime as R
    ack=R.strict_json(R.read_bound(directory/"ack.json",maximum=65536))
    def check():
        if ack.get("nonce")!=args.nonce or time.monotonic()-ack["started_monotonic"]>=30:
            raise R.RuntimeRefused("OWNER_DEADLINE_OR_ACK_UNAVAILABLE")
        R.quiet_admission(stamp())
        if (ROOT/"backend/data/optimus/news_digest/STOP").exists():
            raise R.RuntimeRefused("STOP_PRESENT")
    check()
    grant=R.strict_json(R.read_bound(args.grant,check=check,maximum=65536))
    review=R.strict_json(R.read_bound(args.review,check=check,maximum=65536))
    pins=source_pins(check,provider=grant.get('provider'),expected_site=ack['verified_site'],stage=args.stage)
    if args.stage=="asml-current":
        from backend.services import asml_current_adapter as A
        A.authorize(grant,now=stamp(),review=review,actual_sources=pins)
    else:
        R.authorize(grant,now=stamp(),bundle_sha256=grant["bundle_sha256"],review=review,actual_sources=pins)
    if grant["nonce"]!=args.nonce or Path(grant["output_directory"]).resolve()!=directory:raise R.RuntimeRefused("EXACT_ONE_JOB_DIRECTORY_UNAVAILABLE")
    if grant.get("stage")!=args.stage or Path(grant["bundle_path"]).resolve()!=Path(args.bundle).resolve():
        raise R.RuntimeRefused("EXACT_INPUT_STAGE_UNAVAILABLE")
    raw=R.read_bound(args.bundle,expected_sha256=grant["bundle_sha256"],check=check)
    bundle=R.strict_json(raw)
    if args.stage=="asml-current":
        if grant.get("provider")!="deepseek":raise R.RuntimeRefused("PROVIDERS_OFF")
        from backend.services import asml_current_adapter as A
        acquisition=A.validate_bundle(bundle,grant)
        returned=[]
        def preserve(value):
            if not returned:
                # This path intentionally omits the STOP/deadline check: an
                # already-returned billed response must survive that refusal.
                native=R.publish(directory,"native_return.json",value)
                returned.append(hashlib.sha256(native.read_bytes()).hexdigest())
            return returned[0]
        transport=R.deepseek_transport(authorized=True,sdk_pins={k:pins[k] for k in R.SDK_FILES},
            expected_site=ack['verified_site'],owner_check=check,
            on_native_return=lambda result:preserve(A.private_native_return(result)))
        result=A.capture(acquisition,transport=transport,persist_native=preserve,check=check)
        name="capture.json"
    elif args.stage=="capture":
        if "numeric_cache" in bundle:raise R.RuntimeRefused("UNQUALIFIED_RAW_CACHE_UNAVAILABLE")
        if grant.get("provider")!=bundle["route"]["name"] or grant.get("allow_native_meter_telemetry") is not True:
            raise R.RuntimeRefused("PROVIDERS_OFF")
        if grant["provider"]=="deepseek":
            transport=R.deepseek_transport(authorized=True,sdk_pins={k:pins[k] for k in R.SDK_FILES},expected_site=ack['verified_site'],owner_check=check)
        elif grant["provider"]=="local_qwen":
            proof=grant.get("passive_local_ownership",{})
            def owned(expected):
                check()
                now=R.utc(stamp())
                if (type(expected.get("pid")) is not int or expected["pid"]<=0
                        or type(expected.get("creation_filetime")) is not int
                        or expected["creation_filetime"]<=0 or expected.get("owner")!="ROOT"
                        or expected.get("model_version")!=bundle["route"]["model_version"]):
                    raise R.RuntimeRefused("PASSIVE_LOCAL_PROOF_UNAVAILABLE")
                if not R.utc(expected["available_at"])<=now<=R.utc(expected["valid_until_at"]):
                    raise R.RuntimeRefused("PASSIVE_LOCAL_PROOF_EXPIRED")
                actual=server_identity(expected["pid"])
                if any(actual[k]!=expected[k] for k in ("pid","creation_filetime","image_path")):
                    raise R.RuntimeRefused("PASSIVE_LOCAL_OWNER_DRIFT")
            transport=R.passive_local_transport(proof,authorized=True,ownership_check=owned)
        else:
            raise R.RuntimeRefused("PROVIDERS_OFF")
        check()
        cache=None
        if bundle.get("cache_run"):
            reference=bundle["cache_run"]
            if Path(reference["directory"]).resolve().parent!=PRIVATE.resolve():
                raise R.RuntimeRefused("PRIVATE_CACHE_SCOPE_UNAVAILABLE")
            cache=R.load_capture_run(reference["directory"],expected_outer_sha256=reference["outer_sha256"],
                                     expected_sources=pins,check=check)
        result=R.saved_capture(bundle,transport=transport,cache=cache,check=check,
            remaining_seconds=30-(time.monotonic()-ack['started_monotonic']),source_pins=pins,transport_review=bundle.get('transport_review'),
            cache_observation_at=stamp() if cache is not None else None)
        name="capture.json"
    elif args.stage=="normalize-reviewed":
        result=R.normalize_reviewed(bundle["original_bundle"],bundle["capture"],bundle["numeric_review"],
            bundle["qualifications"],bundle["definitions"],made_at=bundle["made_at"])
        name="candidate.json"
    else:
        result=R.calibrate_reviewed(bundle["history"],bundle["current"],qualifications=bundle["qualifications"],
            definitions=bundle["definitions"],target=bundle["target"],cutoff=bundle["cutoff"],
            return_review=bundle.get("return_review"),return_qualifications=bundle.get("return_qualifications"),
            frozen_derivation=bundle.get("frozen_derivation"),decision_at=stamp())
        name="returns.json"
    check()
    payload={"schema":R.VERSION,"result":result,"bundle_sha256":grant["bundle_sha256"],
        "source_pins":pins,"actual_completed_at":stamp(),"development_only":True}
    R.publish(directory,name,payload,check=check)
    route=({"family":"asml_issuer_current_measurement","state":"PRIVATE_INTERPRETATION_ONLY",
        "legacy_catalog_registered":False,"prospective_accrual":False,"trade_authority":False,
        "forecast_authority":False,"required_reviews":["native_capture","full_row_semantics","price_panel","diagnostic_writer"]}
        if args.stage=="asml-current" else
        {"family":"beta_v1_news_probability_v1","state":"DEVELOPMENT_INACTIVE",
         "consumer":"beta_v1_consumers.current_draft qualified_return_records + reviewed vintage",
         "grader":"beta_v1_news_outcomes.score/catchup exact endpoint sidecars",
         "legacy_catalog_registered":False,"prospective_accrual":False,"trade_authority":False,
         "required_reviews":["source","numeric_capture","exact_probability_row","derived_return","outcome"]})
    R.publish(directory,"route.json",route,check=check)
    if args.stage=="capture" and result.get("capture"):
        from backend.services import world_digest as WD
        index={"namespace":"BETA_NEWS_CAPTURE_V1","capture_path":name,
            "capture_file_sha256":hashlib.sha256(R.read_bound(directory/name,check=check)).hexdigest(),
            "cache_key":result["capture"]["cache_key"]}
        raw=R.encode(index)
        # locked_append_line also creates its one-byte ownership lock sidecar.
        if sum(p.stat().st_size for p in directory.iterdir())+len(raw)+1>R.MAX_OUTPUT-R.PROOF_RESERVE:
            raise R.RuntimeRefused("OUTPUT_TOTAL_LIMIT")
        check();WD.append_cache([index],directory/"beta_news_cache_index.jsonl");check()


def own(args):
    started=time.monotonic()  # BEFORE metadata, hashes, setup and analytical IO
    from backend.services import beta_v1_news_runtime as R
    from scripts import beta_v1_numerical_receipt as G
    worker_process=None
    directory=None
    nonce=None
    def check():
        if time.monotonic()-started>=30:raise R.RuntimeRefused("OWNER_DEADLINE")
        R.quiet_admission(stamp())
        if (ROOT/"backend/data/optimus/news_digest/STOP").exists():raise R.RuntimeRefused("STOP_PRESENT")
        current,peak=memory(owner_handle())
        if max(current,peak)>=R.RSS_LIMIT:raise R.RuntimeRefused("OWNER_RSS_LIMIT")
        if worker_process is not None:
            _,child_peak=memory(worker_process._handle)
            if peak+child_peak>=R.RSS_LIMIT:raise R.RuntimeRefused("OWNED_AGGREGATE_RSS_LIMIT")
    try:
        check()
        grant_raw=R.read_bound(args.grant,check=check,maximum=65536)
        review_raw=R.read_bound(args.review,check=check,maximum=65536)
        grant,review=R.strict_json(grant_raw),R.strict_json(review_raw)
        pins=source_pins(check,provider=grant.get('provider'),stage=args.stage)
        if args.stage=="asml-current":
            from backend.services import asml_current_adapter as A
            A.authorize(grant,now=stamp(),review=review,actual_sources=pins)
        else:
            R.authorize(grant,now=stamp(),bundle_sha256=grant["bundle_sha256"],review=review,actual_sources=pins)
        if grant.get("stage")!=args.stage or Path(grant["bundle_path"]).resolve()!=Path(args.bundle).resolve():
            raise R.RuntimeRefused("EXACT_INPUT_STAGE_UNAVAILABLE")
        if Path(grant.get("private_output_root","")).resolve()!=PRIVATE.resolve():
            raise R.RuntimeRefused("PRIVATE_OUTPUT_SCOPE_UNAVAILABLE")
        if PRIVATE.is_symlink():raise R.RuntimeRefused("PRIVATE_OUTPUT_SCOPE_UNAVAILABLE")
        PRIVATE.mkdir(parents=True,exist_ok=True)
        nonce=grant["nonce"]
        candidate=Path(grant["output_directory"])
        if candidate.is_symlink() or candidate.resolve()!=PRIVATE.resolve()/("capture_"+nonce):raise R.RuntimeRefused("EXACT_ONE_JOB_DIRECTORY_UNAVAILABLE")
        candidate.mkdir(exist_ok=False)
        directory=candidate.resolve()
        base,site,env=G.direct_environment()
        if source_pins(check,provider=grant.get("provider"),expected_site=site,stage=args.stage)!=pins:raise R.RuntimeRefused("SDK_SOURCE_ORIGIN_DRIFT")
        env["AEGIS_IGNORE_DOTENV"]="1";env.pop("AEGIS_PERSONAL_MODE",None)
        check()
        worker_process=subprocess.Popen([str(base),"-B","-S","-m","scripts.beta_v1_news_capture",
            "--worker","--stage",args.stage,"--bundle",args.bundle,"--grant",args.grant,"--review",args.review,
            "--directory",str(directory),"--nonce",nonce],cwd=ROOT,env=env,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        # Every post-Popen operation is already within this try/finally.
        while not (directory/"identity.json").exists():
            check()
            if worker_process.poll() is not None:raise R.RuntimeRefused("WORKER_IDENTITY_UNAVAILABLE")
            time.sleep(.02)
        identity=R.strict_json(R.read_bound(directory/"identity.json",check=check,maximum=65536))
        G.validate_identity(identity,pid=worker_process.pid,base=base,site=site,nonce=nonce)
        R.publish(directory,"ack.json",{"nonce":nonce,"started_monotonic":started,"verified_site":str(site.resolve())},check=check,proof=True)
        guard=G.guard_worker(worker_process,rss_query=lambda pid:memory(worker_process._handle if pid else owner_handle())[0],
            max_seconds=30,max_rss=R.RSS_LIMIT,started=started,extra_check=check,
            final_peak_query=lambda process:memory(process._handle)[1]+memory(owner_handle())[1])
        if (worker_process.returncode!=0 or guard.get("status")!="BOUNDED_COMPLETION"
                or guard.get("worker_exit_code")!=0 or guard.get("final_owned_handle_peak_proved") is not True
                or type(guard.get("rss_samples")) is not int or guard["rss_samples"]<=0
                or guard.get("owned_pids")!=[worker_process.pid]):
            raise R.RuntimeRefused("OWNED_WORKER_REFUSED")
        check()
        filename={"capture":"capture.json","asml-current":"capture.json","normalize-reviewed":"candidate.json","calibrate-reviewed":"returns.json"}[args.stage]
        payload=R.strict_json(R.read_bound(directory/filename,check=check,maximum=R.MAX_OUTPUT))
        if args.stage=="asml-current":
            native_raw=R.read_bound(directory/"native_return.json",check=check,maximum=R.MAX_OUTPUT)
            if payload["result"].get("native_return_sha256")!=hashlib.sha256(native_raw).hexdigest():
                raise R.RuntimeRefused("ASML_NATIVE_RETURN_BINDING_DRIFT")
        if source_pins(check,provider=grant.get("provider"),expected_site=site,stage=args.stage)!=pins:raise R.RuntimeRefused("POST_SOURCE_DRIFT")
        if R.read_bound(args.grant,check=check,maximum=65536)!=grant_raw or R.read_bound(args.review,check=check,maximum=65536)!=review_raw:
            raise R.RuntimeRefused("POST_AUTHORITY_DRIFT")
        R.read_bound(args.bundle,expected_sha256=grant["bundle_sha256"],check=check)
        # Child freezes capture before its private Beta index; owner verifies
        # both and refuses reuse unless a completion proof exists with no refusal.
        if args.stage=="capture" and payload["result"].get("capture"):
            index_raw=R.read_bound(directory/"beta_news_cache_index.jsonl",check=check,maximum=65536)
            index=R.strict_json(index_raw)
            if (index.get("namespace")!="BETA_NEWS_CAPTURE_V1" or index.get("capture_path")!=filename
                    or index.get("cache_key")!=payload["result"]["capture"]["cache_key"]
                    or index.get("capture_file_sha256")!=hashlib.sha256(R.read_bound(directory/filename,check=check)).hexdigest()):
                raise R.RuntimeRefused("CACHE_INDEX_DRIFT")
        _,owner_peak=memory(owner_handle());_,child_peak=memory(worker_process._handle)
        proof={"schema":"beta_news_outer_completion/1","status":"BOUNDED_PRIVATE_COMPLETION",
            "elapsed_seconds_before_proof":time.monotonic()-started,"owner_peak_bytes":owner_peak,
            "worker_peak_bytes":child_peak,"aggregate_peak_upper_bound":owner_peak+child_peak,
            "measurement_scope":"includes post-worker verification and index, before final proof IO",
            "worker_reaped":worker_process.poll() is not None,"nonce":nonce,"source_pins":pins,
            "grant_nonce":grant["nonce"],"output_directory":str(directory),
            "grant_file_sha256":hashlib.sha256(grant_raw).hexdigest(),"grant_hash_domain":"FILE_BYTES_SHA256",
            "guard":guard,"verified_identity":identity,"source_pin_hash_domain":"FILE_BYTES_SHA256",
            "sdk_code_pins":{k:v for k,v in pins.items() if k.startswith("SDK:")},"direct_base_executable":str(base.resolve()),
            "verified_package_origins":identity["package_origins"],
            "limits":{"wall_seconds":30,"rss_bytes":R.RSS_LIMIT,"output_bytes":R.MAX_OUTPUT},
            "bundle_sha256":grant["bundle_sha256"],"bundle_hash_domain":"FILE_BYTES_SHA256",
            "source_review_sha256":R.digest(review),"source_review_hash_domain":"CANONICAL_JSON_V1",
            "result_file":filename,"result_sha256":R.digest(payload),"result_hash_domain":"CANONICAL_JSON_V1",
            "native_return_file_sha256":(hashlib.sha256(native_raw).hexdigest()
                if args.stage=="asml-current" else None),
            "stage":args.stage,"provider_calls_authority":"EXPLICIT_ROOT_GRANT_ONLY","activation":"DEVELOPMENT_INACTIVE",
            "native_budget_scope":"PROCESS_LOCAL_CALL_METER_AND_BREAKER_NOT_SHARED_CUMULATIVE_BUDGET"}
        check();R.publish(directory,"outer_completion.json",proof,check=check,proof=True);check()
        print(json.dumps({"status":payload["result"]["status"],"outer_status":proof["status"],"directory":directory.name}))
        return 0
    except Exception:
        if directory is not None:
            try:
                returned=returned_refusal_evidence(directory)
                R.publish(directory,"refusal.json",{"status":"UNAVAILABLE","reason":"BOUNDED_CAPTURE_REFUSED",
                    "provider_spend_status":"NO_RETURNED_NATIVE_EVIDENCE" if not returned else returned["provider_spend_status"],
                    **returned},proof=True)
            except Exception:pass
        print('{"status":"UNAVAILABLE","reason":"BOUNDED_CAPTURE_REFUSED"}')
        return 2
    finally:
        if worker_process is not None:
            if worker_process.poll() is None:worker_process.kill()
            worker_process.wait(timeout=10)
            if hasattr(worker_process,"_handle"):worker_process._handle.Close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--stage",choices=("capture","asml-current","normalize-reviewed","calibrate-reviewed"),default="capture")
    for name in ("bundle","grant","review","directory","nonce"):parser.add_argument("--"+name)
    parser.add_argument("--worker",action="store_true")
    args=parser.parse_args(argv)
    if not args.grant or not args.review or not args.bundle:
        print('{"status":"UNAVAILABLE","reason":"PROVIDERS_AND_INPUT_READS_OFF"}');return 2
    if args.worker:
        try:worker(args);return 0
        except Exception:return 2  # never print provider/raw exception payload
    return own(args)


if __name__=="__main__":
    raise SystemExit(main())
