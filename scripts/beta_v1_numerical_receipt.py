"""Explicitly launched isolated numerical worker, bounded by its owning process.

Run only after independent source review and root's actual-job grant. No API,
downloads, runtime ranking or portfolio writes. Output is private and immutable.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEPENDENCIES = ("numpy", "pandas", "pyarrow", "lightgbm", "exchange_calendars")


def file_sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            result.update(chunk)
    return result.hexdigest()


def direct_environment():
    """Bypass the Windows venv redirector, retain exact authorized packages.

    -S excludes base/global/user site packages; PYTHONPATH supplies only this
    checkout plus the invoking venv's package directory. No environment secrets
    are included in receipts. The identity handshake verifies actual PID and
    package origins before any numerical/data import starts.
    """
    base = Path(sys._base_executable).resolve()
    site = Path(sys.prefix)/"Lib"/"site-packages" if os.name == "nt" else Path(sys.prefix)/"lib"/f"python{sys.version_info.major}.{sys.version_info.minor}"/"site-packages"
    site = site.resolve()
    if not base.is_file() or not site.is_dir() or Path(sys.prefix).resolve() == Path(sys.base_prefix).resolve():
        raise ValueError("verified original venv and direct base CPython required")
    env = dict(os.environ, OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2",
        NUMEXPR_NUM_THREADS="2", VECLIB_MAXIMUM_THREADS="2", PYTHONNOUSERSITE="1",
        PYTHONPATH=os.pathsep.join((str(ROOT), str(site))))
    return base, site, env


def worker_identity(nonce):
    return {"nonce": nonce, "pid": os.getpid(), "sys_executable": str(Path(sys.executable).resolve()),
        "package_origins": {name: importlib.util.find_spec(name).origin for name in DEPENDENCIES},
        "sys_path": sys.path, "user_site_disabled": os.environ.get("PYTHONNOUSERSITE") == "1"}


def validate_identity(identity, *, pid, base, site, nonce, expected_origins=None):
    if (identity.get("pid") != pid or identity.get("nonce") != nonce or
            Path(identity.get("sys_executable", "")).resolve() != base or not identity.get("user_site_disabled")):
        raise ValueError("real interpreter ownership/nonce mismatch; redirector not admitted")
    for origin in identity.get("package_origins", {}).values():
        if not origin or site not in Path(origin).resolve().parents:
            raise ValueError("dependency import origin differs from original venv")
    if set(identity.get("package_origins", {})) != set(DEPENDENCIES):
        raise ValueError("missing original package origins")
    if expected_origins is not None and identity["package_origins"] != expected_origins:
        raise ValueError("actual child dependency paths differ from invoking venv")


def guard_worker(worker, *, rss_query, sleep=time.sleep, clock=time.monotonic,
                 max_seconds=480, max_rss=3*1024**3, extra_check=lambda: None, started=None,
                 final_peak_query=None):
    """Continuous outer monitor of a proved direct interpreter, not redirector.

    RSS uses OS high-water counters to capture native-allocation peaks between
    samples. Deadline is checked after completion too, so completion cannot
    erase an already observed limit. Only this Popen process is terminated;
    reviewed numerical code launches no child processes (native CPU threads).
    """
    started = clock() if started is None else started
    peak, reason, samples = 0, None, 0
    while True:
        elapsed = clock()-started
        if elapsed >= max_seconds:
            reason = "480s hard wall cap exceeded"
        if worker.poll() is not None:
            break
        try:
            peak = max(peak, rss_query(worker.pid)+rss_query(None))
            samples += 1
            extra_check()
        except Exception as exc:
            reason = "owned real-worker resource/identity measurement failed: "+str(exc)
        if peak >= max_rss:
            reason = "3GiB owner plus real-worker RSS cap exceeded"
        if reason:
            # Kill and reap this exact live Popen handle. With direct CPython,
            # no redirector waits outside this handle and no orphan is created.
            try:
                if worker.poll() is None:
                    worker.kill()
                worker.wait(timeout=5)
            except Exception as exc:
                reason += "; exact-owned termination/reap failed: "+str(exc)
            break
        sleep(.05)
    final_peak, final_proved = None, False
    try:
        if final_peak_query is None:
            raise ValueError("final exact-owned-handle peak query unavailable")
        final_peak = final_peak_query(worker)
        if not isinstance(final_peak, int) or isinstance(final_peak, bool) or final_peak <= 0:
            raise ValueError("invalid final exact-owned-handle aggregate high-water")
        peak = max(peak, final_peak)
        final_proved = True
    except Exception as exc:
        reason = reason or "final exact-owned-handle resource proof unavailable: "+str(exc)
    if peak >= max_rss:
        reason = "3GiB owner plus real-worker final high-water RSS cap exceeded"
    elapsed = clock()-started
    if elapsed >= max_seconds and not reason:
        reason = "480s hard wall cap exceeded at completion"
    if not samples and not reason:
        reason = "no actual owned-worker RSS sample; bounded completion not proved"
    if worker.poll() is not None:
        worker.wait(timeout=5)
    return {"status": "REFUSED_OUTER_LIMIT" if reason else "BOUNDED_COMPLETION",
        "reason": reason, "worker_exit_code": worker.returncode, "elapsed_seconds": elapsed,
        "peak_aggregate_high_water_rss_bytes": peak, "rss_samples": samples,
        "final_owned_handle_peak_proved": final_proved,
        "final_aggregate_high_water_rss_bytes": final_peak,
        "owned_pids": [worker.pid], "owner_pid": os.getpid(), "direct_interpreter": True,
        "owned_worker_reaped": worker.poll() is not None,
        "hard_wall_seconds": max_seconds, "rss_cap_bytes": max_rss, "cpu_threads": 2,
        "sample_interval_seconds": .05, "worker_receipt_resource_qualified": False}


def atomic_receipt(path, payload):
    from backend.services import beta_v1_policy as policy
    from backend.services.beta_v1_numerical import NumericalRefused
    if path.exists():
        raise NumericalRefused("immutable numerical output already exists")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    existing_size = sum(p.stat().st_size for p in path.parent.iterdir() if p.is_file())
    # Reserve space for the owner's immutable verdict even when a worker has
    # finished writing a near-cap result immediately before a bound is found.
    cap = (32 if path.name == "outer_completion.json" else 31)*1024**2
    if len(encoded)+existing_size > cap:
        raise NumericalRefused("numerical output exceeds 32MiB")
    temporary = path.with_suffix(".incomplete")
    with temporary.open("xb") as stream:
        stream.write(encoded)
    temporary.rename(path)
    return policy.digest(payload)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--facts-sha256", required=True)
    parser.add_argument("--tickers-sha256", required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--nonce", default="", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    private = Path("C:/Users/mrthn/aegis-recovery-evidence/beta-build-sprint-20261011").resolve()
    output = Path(args.output_dir).resolve()
    if output == private or private not in output.parents:
        raise ValueError("new dedicated private numerical directory required")
    output.mkdir(parents=True, exist_ok=True)
    receipt = output/"beta_v1_numerical_receipt.json"
    if receipt.exists():
        raise ValueError("immutable output exists")
    if args.worker:
        # Handshake uses stdlib find_spec only, no numerical libraries/models or
        # price/SEC inputs. The owner admits exact PID/interpreter/import origins.
        atomic_receipt(output/"worker_identity.json", worker_identity(args.nonce))
        acknowledgement = output/"owner_admitted.json"
        ready_started = time.monotonic()
        while not acknowledgement.exists():
            if time.monotonic()-ready_started > 5:
                return 1
            time.sleep(.02)
        admitted = json.loads(acknowledgement.read_text())
        if admitted != {"nonce": args.nonce, "pid": os.getpid()}:
            return 1
        from backend.services import beta_v1_numerical as numerical
        before_script = numerical.sha256(__file__)
        budget = numerical.Budget()
        def model_sink(serialized, digest):
            path = output/("model_"+digest+".txt")
            if len(serialized.encode("utf-8")) > 16*1024**2:
                raise numerical.NumericalRefused("serialized model output cap exceeded")
            with path.open("x", encoding="utf-8", newline="") as stream:
                stream.write(serialized)
            if numerical.sha256(path) != digest:
                raise numerical.NumericalRefused("serialized model bytes hash mismatch")
            return str(path)
        try:
            result = numerical.run(facts_sha256=args.facts_sha256, tickers_sha256=args.tickers_sha256,
                budget=budget, model_sink=model_sink)
            if numerical.sha256(__file__) != before_script:
                raise numerical.NumericalRefused("runner changed during execution")
            result = {"result": result, "runner_sha256": before_script,
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "resource_qualification": "REQUIRES_MATCHING_IMMUTABLE_outer_completion.json"}
            atomic_receipt(receipt, result)
            return 0
        except Exception as exc:
            atomic_receipt(receipt, {"status": "REFUSED", "reason": str(exc), "error_type": type(exc).__name__,
                "evidence": getattr(exc, "evidence", {}),
                "runner_sha256": before_script, "source_pins": numerical.code_pins(),
                "resources": budget.accounting(), "activation": "NONE"})
            return 1
    # Direct base CPython is the actual worker; exact venv dependency origins
    # are checked before numerical inputs are admitted. No venv redirector.
    from backend.services.beta_v1_numerical import rss_bytes, rss_owned_handle
    base, site, env = direct_environment()
    nonce = uuid.uuid4().hex
    admitted = {}
    launch = {"parent_executable": sys.executable, "base_executable": str(base),
        "base_executable_sha256": file_sha256(base), "venv_site_packages": str(site),
        "python_no_user_site": True, "python_no_site": True, "runner_sha256": file_sha256(__file__),
        "expected_package_origins": {name: importlib.util.find_spec(name).origin for name in DEPENDENCIES}}
    with (output/"worker.stderr.txt").open("xb") as error:
        launch_started = time.monotonic()
        worker = subprocess.Popen([str(base), "-S", str(Path(__file__).resolve()), "--worker", "--output-dir", str(output),
            "--facts-sha256", args.facts_sha256, "--tickers-sha256", args.tickers_sha256, "--nonce", nonce],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=error)
        def extra_check():
            identity_path = output/"worker_identity.json"
            if identity_path.exists() and not admitted:
                identity = json.loads(identity_path.read_text())
                validate_identity(identity, pid=worker.pid, base=base, site=site, nonce=nonce,
                    expected_origins=launch["expected_package_origins"])
                admitted.update(identity)
                atomic_receipt(output/"owner_admitted.json", {"nonce": nonce, "pid": worker.pid})
            if (output/"worker.stderr.txt").stat().st_size > 1024**2:
                raise ValueError("bounded stderr cap exceeded")
        verdict = guard_worker(worker, rss_query=lambda pid: rss_bytes(pid, peak=True),
            extra_check=extra_check, started=launch_started,
            final_peak_query=lambda owned: rss_owned_handle(owned._handle, peak=True)+rss_bytes(None, peak=True))
        # Keep the original Popen handle alive through final OS peak proof and
        # wait; releasing it only now cannot accidentally target a reused PID.
        if os.name == "nt" and worker.poll() is not None:
            worker._handle.Close()
    # Worker output and outer evidence have separate immutable names. A limit
    # always remains a refusal even if the worker won its receipt-write race.
    verdict.update({"launch": launch, "verified_identity": admitted or None,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "worker_receipt_sha256": file_sha256(receipt) if receipt.exists() else None,
        "activation": "NONE"})
    if not admitted or worker.returncode != 0 or not receipt.exists():
        if verdict["status"] == "BOUNDED_COMPLETION":
            verdict["status"] = "REFUSED_WORKER_COMPLETION"
    if file_sha256(base) != launch["base_executable_sha256"] or file_sha256(__file__) != launch["runner_sha256"]:
        verdict["status"] = "REFUSED_EXECUTABLE_DRIFT"
        verdict["reason"] = "direct interpreter or runner bytes changed during owned execution"
    verdict["worker_receipt_resource_qualified"] = verdict["status"] == "BOUNDED_COMPLETION"
    atomic_receipt(output/"outer_completion.json", verdict)
    return 0 if verdict["worker_receipt_resource_qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
