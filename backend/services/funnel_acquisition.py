"""Owned, private nonfinancial acquisition; no default production integration.

Only the gated worker imports provider libraries. Limits count actual synchronous
Curl.perform entries, including yfinance auth/retry calls, not logical batches.
Redirects, proxy/auth negotiation, async/streaming and unsupported hosts refuse.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import sysconfig
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

FROZEN_FIVE = frozenset({"EVO.ST", "HAG.DE", "KOG.OL", "RHM.DE", "SAAB-B.ST"})
_ROOT = Path(__file__).resolve().parents[2]
_LIMITS = {
    "max_transport_attempts",
    "request_seconds",
    "wall_seconds",
    "cleanup_seconds",
    "job_commit_bytes",
    "max_response_bytes",
    "max_artifact_bytes",
    "max_raw_rows",
    "max_symbols",
    "batch_size",
}


class AcquisitionRefused(ValueError):
    """Sanitized refusal; never includes provider text, credentials or query URLs."""


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _date(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise AcquisitionRefused("noncanonical_date")
    return parsed


def validate_request(request: dict, *, finnhub_key: str | None) -> None:
    """All policy inputs explicit; no filesystem, provider or owner access."""
    try:
        if not isinstance(request, dict):
            raise ValueError
        mode = request["mode"]
        lim = request["limits"]
        if set(lim) != _LIMITS:
            raise ValueError
        for k, v in lim.items():
            if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
                raise ValueError
            if (
                k not in {"request_seconds", "wall_seconds", "cleanup_seconds"}
                and type(v) is not int
            ):
                raise ValueError
        if lim["request_seconds"] > lim["wall_seconds"]:
            raise ValueError
        hs, he = _date(request["history_start"]), _date(request["history_end"])
        cs, ce = _date(request["coverage_start"]), _date(request["coverage_end"])
        minimum = request["coverage_min_rows"]
        if (
            not hs <= cs <= ce <= he
            or type(minimum) is not int
            or not 0 < minimum <= (ce - cs).days + 1
        ):
            raise ValueError
        if not isinstance(request["run_dir"], str) or not request["run_dir"]:
            raise ValueError
        pins = request["source_pins"]
        if (
            not isinstance(pins, dict)
            or not pins
            or any(
                not isinstance(v, str) or not re.fullmatch("[0-9a-f]{64}", v) for v in pins.values()
            )
        ):
            raise ValueError
        for provider, scope in [("yahoo", "private_personal_research_history")] + (
            [("finnhub", "stock_symbol_US")] if mode == "full_us" else []
        ):
            authority = request["entitlements"][provider]
            if (
                authority["qualified"] is not True
                or authority["scope"] != scope
                or not isinstance(authority["evidence_ref"], str)
                or not authority["evidence_ref"].strip()
            ):
                raise ValueError
        extras = request["extras"]
        if (
            not isinstance(extras, list)
            or len(set(extras)) != len(extras)
            or any(
                not isinstance(t, str)
                or not re.fullmatch(r"[A-Z0-9-]{1,5}", t)
                or not t.replace("-", "")
                for t in extras
            )
        ):
            raise ValueError
        if mode == "frozen_five":
            if (
                request["symbols"] != sorted(FROZEN_FIVE)
                or extras
                or finnhub_key is not None
                or lim["max_symbols"] < 5
                or lim["max_transport_attempts"] < 5
            ):
                raise ValueError
        elif mode == "full_us":
            if (
                request["symbols"] != []
                or not isinstance(finnhub_key, str)
                or not finnhub_key.strip()
            ):
                raise ValueError
            if lim["max_transport_attempts"] < 2:
                raise ValueError
        else:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise AcquisitionRefused("missing_or_invalid_acquisition_contract") from None


def _runtime_contract() -> dict:
    """Only the reviewed direct CPython runtime; no venv launcher fallback."""
    if (
        sys.platform != "win32"
        or sys.implementation.name != "cpython"
        or tuple(sys.version_info[:2]) != (3, 12)
    ):
        raise AcquisitionRefused("unsupported_direct_worker_runtime")
    executable = Path(sys._base_executable)
    base = Path(sys.base_prefix)
    if (
        not executable.is_absolute()
        or executable.name.lower() != "python.exe"
        or executable.is_symlink()
        or executable.parent.resolve() != base.resolve()
        or (base / "pyvenv.cfg").exists()
        or (base.parent / "pyvenv.cfg").exists()
    ):
        raise AcquisitionRefused("direct_base_interpreter_required")
    return {
        "classification": "cpython_3_12_windows_direct_base",
        "executable": str(executable.resolve()),
        "base_prefix": str(base.resolve()),
        "version": list(sys.version_info[:3]),
        "pointer_bits": ctypes.sizeof(ctypes.c_void_p) * 8,
    }


def _source_paths(site_dir: str | None = None) -> dict[str, Path]:
    site = Path(site_dir or sysconfig.get_path("purelib"))
    paths = {
        name: site / name
        for name in (
            "yfinance/data.py",
            "yfinance/base.py",
            "yfinance/version.py",
            "yfinance/multi.py",
            "yfinance/cache.py",
            "yfinance/scrapers/history.py",
            "curl_cffi/requests/session.py",
            "curl_cffi/requests/utils.py",
            "curl_cffi/curl.py",
            "curl_cffi/const.py",
            "curl_cffi/__version__.py",
            "curl_cffi/_wrapper.pyd",
        )
    }
    paths.update(
        adapter=Path(__file__),
        worker=_ROOT / "scripts/funnel_acquisition_worker.py",
        funnel=_ROOT / "backend/services/opportunity_funnel.py",
        staging=_ROOT / "backend/services/funnel_staging.py",
        quiet_subprocess=_ROOT / "backend/services/quiet_subprocess.py",
    )
    runtime = _runtime_contract()
    paths.update(
        {
            "runtime/base_interpreter": Path(runtime["executable"]),
            "runtime/python312.dll": Path(runtime["base_prefix"]) / "python312.dll",
            "runtime/python3.dll": Path(runtime["base_prefix"]) / "python3.dll",
        }
    )
    return paths


def source_pins(site_dir: str | None = None) -> dict[str, str]:
    """Read exact installed/source files without importing SDKs or touching caches."""
    try:
        pins = {k: _sha(p.read_bytes()) for k, p in _source_paths(site_dir).items()}
        pins["runtime/identity"] = _sha(_encode(_runtime_contract()))
        return pins
    except OSError:
        raise AcquisitionRefused("source_qualification_files_unavailable") from None


def _check_window(now: datetime, *, wall_seconds: float, cleanup_seconds: float) -> None:
    if now.tzinfo is None:
        raise AcquisitionRefused("aware_clock_required")
    local = now.astimezone(timezone(timedelta(hours=8)))
    quiet = local.replace(hour=16, minute=35, second=0, microsecond=0)
    end = quiet.replace(hour=17, minute=10)
    # The next start bounds every budget, including those spanning several days.
    until_quiet = (quiet - local).total_seconds()
    if local >= end:
        until_quiet += 24 * 60 * 60
    if quiet <= local < end or wall_seconds + cleanup_seconds >= until_quiet:
        raise AcquisitionRefused("operation_and_cleanup_overlap_quiet_window")


def _private_path(path: Path) -> Path:
    raw = path.absolute()
    for part in (raw, *raw.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise AcquisitionRefused("private_path_alias")
    resolved = raw.resolve()
    blocked = {"backend", "data", ".cache", "funnel_cache", "funnel_history", ".git"}
    if (
        raw.parent.name != "funnel-acquisition-staging"
        or not raw.parent.is_dir()
        or raw.exists()
        or blocked.intersection(p.lower() for p in resolved.parts)
    ):
        raise AcquisitionRefused("new_private_run_directory_required")
    for key in ("AEGIS_DATA_DIR",):
        if os.getenv(key):
            protected = Path(os.environ[key]).resolve()
            if resolved == protected or protected in resolved.parents:
                raise AcquisitionRefused("protected_data_root")
    return resolved


def _child_environment(root: Path) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH"}
    }
    for k, directory in {
        "HOME": "home",
        "USERPROFILE": "home",
        "APPDATA": "appdata",
        "LOCALAPPDATA": "local",
        "TEMP": "tmp",
        "TMP": "tmp",
        "XDG_CACHE_HOME": "cache",
    }.items():
        env[k] = str(root / directory)
    env.update(
        AEGIS_IGNORE_DOTENV="1",
        PYTHONDONTWRITEBYTECODE="1",
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    return env


class _OwnedJob:
    """Private per-operation Windows Job: aggregate worker-tree committed memory.

    Mirrors the existing owned-Job pattern WITHOUT importing a scheduled owner
    or borrowing llama_server's global handle. This is not an RSS/parent cap.
    """

    def __init__(self, memory_limit: int, *, expected_image=None):
        if sys.platform != "win32":
            raise AcquisitionRefused("windows_job_required_unsupported_platform")
        from ctypes import wintypes as W

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, result, args in (
            ("CreateJobObjectW", W.HANDLE, [W.LPVOID, W.LPCWSTR]),
            ("SetInformationJobObject", W.BOOL, [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD]),
            ("OpenProcess", W.HANDLE, [W.DWORD, W.BOOL, W.DWORD]),
            ("AssignProcessToJobObject", W.BOOL, [W.HANDLE, W.HANDLE]),
            (
                "QueryInformationJobObject",
                W.BOOL,
                [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD, ctypes.POINTER(W.DWORD)],
            ),
            ("CloseHandle", W.BOOL, [W.HANDLE]),
        ):
            fn = getattr(k, name)
            fn.restype = result
            fn.argtypes = args

        class Basic(ctypes.Structure):
            _fields_ = [
                ("user_process", ctypes.c_int64),
                ("user_job", ctypes.c_int64),
                ("flags", W.DWORD),
                ("min_ws", ctypes.c_size_t),
                ("max_ws", ctypes.c_size_t),
                ("active", W.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", W.DWORD),
                ("scheduling", W.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", IO),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        self.k = k
        self.expected_image = expected_image
        self.handle = k.CreateJobObjectW(None, None)
        if not self.handle:
            raise AcquisitionRefused("job_creation_failed")
        info = Extended()
        info.basic.flags = 0x2000 | 0x200
        info.job_memory = memory_limit
        if not k.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise AcquisitionRefused("job_memory_limit_failed")
        actual = Extended()
        if (
            not k.QueryInformationJobObject(
                self.handle, 9, ctypes.byref(actual), ctypes.sizeof(actual), None
            )
            or actual.basic.flags & 0x2200 != 0x2200
            or actual.job_memory != memory_limit
        ):
            self.close()
            raise AcquisitionRefused("job_limit_readback_failed")
        self.attestation = {
            "flags": int(actual.basic.flags),
            "aggregate_worker_commit_bytes": int(actual.job_memory),
        }

    def bind(self, pid: int) -> None:
        from ctypes import wintypes as W

        if self.expected_image is None:
            raise AcquisitionRefused("pinned_direct_worker_image_required")
        for name, args in (
            ("IsProcessInJob", [W.HANDLE, W.HANDLE, ctypes.POINTER(W.BOOL)]),
            ("QueryFullProcessImageNameW", [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]),
        ):
            fn = getattr(self.k, name)
            fn.restype, fn.argtypes = W.BOOL, args
        process = self.k.OpenProcess(0x0100 | 0x0001 | 0x1000, False, pid)
        if not process:
            raise AcquisitionRefused("owned_process_open_failed")
        try:
            if not self.k.AssignProcessToJobObject(self.handle, process):
                raise AcquisitionRefused("job_binding_failed")
            member = W.BOOL()
            if (
                not self.k.IsProcessInJob(process, self.handle, ctypes.byref(member))
                or not member.value
            ):
                raise AcquisitionRefused("owned_worker_membership_unverified")
            image, size = ctypes.create_unicode_buffer(32768), W.DWORD(32768)
            if not self.k.QueryFullProcessImageNameW(process, 0, image, ctypes.byref(size)):
                raise AcquisitionRefused("owned_worker_image_unverified")
            actual = Path(image.value).resolve()
            expected, digest = self.expected_image
            if actual != Path(expected).resolve() or _sha(actual.read_bytes()) != digest:
                raise AcquisitionRefused("owned_worker_image_mismatch")
            self.attestation.update(
                worker_pid=pid,
                worker_in_private_job=True,
                worker_image=str(actual),
                worker_image_sha256=digest,
            )
        finally:
            self.k.CloseHandle(process)

    def close(self) -> None:
        if self.handle:
            if not self.k.CloseHandle(self.handle):
                raise AcquisitionRefused("job_close_failed")
            self.handle = None


def _supervise(
    process,
    job,
    wire: bytes,
    deadline: float,
    cleanup: float,
    *,
    clock=time.monotonic,
    now=lambda: datetime.now(timezone.utc),
    cancel=lambda: False,
    on_bound=lambda: None,
):
    """No authorization byte until binding succeeds; kill only this owned tree."""
    try:
        job.bind(process.pid)
        on_bound()
        pending = wire
        while True:
            remaining = deadline - clock()
            if remaining <= 0 or cancel():
                raise AcquisitionRefused("owned_worker_timeout_or_cancel")
            _check_window(now(), wall_seconds=remaining, cleanup_seconds=cleanup)
            try:
                process.communicate(input=pending, timeout=min(0.1, remaining))
                break
            except subprocess.TimeoutExpired:
                pending = None
        if clock() > deadline or process.returncode != 0:
            raise AcquisitionRefused("owned_worker_failed_or_late")
    finally:
        # Closing our private handle kills the whole Job, including descendants.
        try:
            job.close()
        finally:
            if process.poll() is None:
                process.kill()
            try:
                process.communicate(timeout=cleanup)
            except subprocess.TimeoutExpired:
                raise AcquisitionRefused("owned_worker_cleanup_timeout") from None


def acquire(
    request: dict,
    *,
    finnhub_key: str | None,
    _job_factory=None,
    _popen=None,
    _clock=time.monotonic,
    _now=lambda: datetime.now(timezone.utc),
    _cancel=lambda: False,
) -> dict:
    """Explicit operating API. Build/tests never invoke its real provider path."""
    validate_request(request, finnhub_key=finnhub_key)
    lim = request["limits"]
    started = _clock()
    deadline = started + lim["wall_seconds"]
    _check_window(_now(), wall_seconds=lim["wall_seconds"], cleanup_seconds=lim["cleanup_seconds"])
    if sys.platform != "win32" and _job_factory is None:
        raise AcquisitionRefused("windows_job_required_unsupported_platform")
    if source_pins() != request["source_pins"]:
        raise AcquisitionRefused("source_qualification_pin_mismatch")
    runtime = _runtime_contract()
    if _clock() >= deadline or _cancel():
        raise AcquisitionRefused("preflight_deadline_or_cancel")
    root = _private_path(Path(request["run_dir"]))
    payload = {
        "request": request,
        "finnhub_key": finnhub_key,
        "deadline": deadline,
        "site_dir": sysconfig.get_path("purelib"),
        "runtime": runtime,
    }
    wire = b"A" + _encode(payload)
    if len(wire) > 32768:
        raise AcquisitionRefused("worker_input_too_large")
    job = (
        _job_factory(lim["job_commit_bytes"])
        if _job_factory
        else _OwnedJob(
            lim["job_commit_bytes"],
            expected_image=(
                runtime["executable"],
                request["source_pins"]["runtime/base_interpreter"],
            ),
        )
    )
    try:
        _check_window(
            _now(), wall_seconds=max(0, deadline - _clock()), cleanup_seconds=lim["cleanup_seconds"]
        )
        root.mkdir()
        for name in ("home", "appdata", "local", "tmp", "cache", "funnel-price-staging"):
            (root / name).mkdir()
        from backend.services import quiet_subprocess as qsp

        p = (_popen or qsp.popen)(
            [
                runtime["executable"],
                "-I",
                "-S",
                "-B",
                str(_ROOT / "scripts/funnel_acquisition_worker.py"),
            ],
            cwd=root,
            env=_child_environment(root),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )

        def bound_receipt():
            _write(
                root,
                "owner_control.json",
                {
                    "owner_pid": os.getpid(),
                    "child_pid": p.pid,
                    "native_private_job": _job_factory is None,
                    "kernel_limit_readback": getattr(job, "attestation", None),
                    "runtime": runtime,
                    "deadline_monotonic": deadline,
                    "cleanup_seconds": lim["cleanup_seconds"],
                    "memory_scope": "aggregate worker-tree committed memory, not parent/RSS",
                    "authorization_gate": "bound_before_A_byte",
                },
                lim["max_artifact_bytes"],
            )

        _supervise(
            p,
            job,
            wire,
            deadline,
            lim["cleanup_seconds"],
            clock=_clock,
            now=_now,
            cancel=_cancel,
            on_bound=bound_receipt,
        )
    finally:
        job.close()
    output = root / "acquisition.json"
    if output.stat().st_size > lim["max_artifact_bytes"]:
        raise AcquisitionRefused("worker_output_too_large")
    result = json.loads(output.read_bytes())
    if _clock() > deadline + lim["cleanup_seconds"]:
        raise AcquisitionRefused("aggregate_operation_deadline")
    _check_window(_now(), wall_seconds=0, cleanup_seconds=0)
    if result.get("mode") != request["mode"] or result.get("status") != "COMPLETE":
        raise AcquisitionRefused("acquisition_refused_see_private_accounting")
    return result


class AttemptMeter:
    """Sticky actual synchronous transfer budget, journaled before each perform."""

    def __init__(self, limits: dict, deadline: float, root: Path, *, clock=time.monotonic):
        self.limits, self.deadline, self.clock = limits, deadline, clock
        self.attempts: list[dict] = []
        self.failure: str | None = None
        self.path = root / "attempts.jsonl"
        self.path.touch(exist_ok=False)

    def refuse(self, reason: str):
        self.failure = self.failure or reason
        raise AcquisitionRefused(self.failure)

    def healthy(self):
        if self.failure:
            raise AcquisitionRefused(self.failure)
        if self.clock() >= self.deadline:
            self.refuse("transport_deadline")

    def _journal(self, row: dict):
        data = _encode(row) + b"\n"
        if self.path.stat().st_size + len(data) > self.limits["max_artifact_bytes"]:
            self.refuse("attempt_journal_size_cap")
        with self.path.open("ab") as stream:
            stream.write(data)
            stream.flush()

    def perform(self, perform, label: str):
        self.healthy()
        if len(self.attempts) >= self.limits["max_transport_attempts"]:
            self.refuse("transport_attempt_cap")
        row = {
            "attempt": len(self.attempts) + 1,
            "endpoint": label,
            "state": "STARTED",
            "started_utc": datetime.now(timezone.utc).isoformat(),
        }
        self._journal(row)
        self.attempts.append(row)
        try:
            result = perform()
        except Exception as exc:
            row.update(state="ERROR", error_type=type(exc).__name__)
            self._journal(row)
            raise
        row["state"] = "RETURNED"
        self._journal(row)
        self.healthy()
        return result


def bound_session_class(session_class, curl_class, opts, meter: AttemptMeter):
    """Factory permits tiny fake native boundaries in tests; only worker installs it."""
    import threading

    creator = threading.get_ident()

    class MeteredCurl(curl_class):
        label = "unlabelled"

        def perform(self, *args, **kwargs):
            # Reapply at the last Python/native boundary, after SDK option setup.
            for name, value in (
                ("FOLLOWLOCATION", 0),
                ("MAXREDIRS", 0),
                ("HTTPAUTH", 0),
                ("PROXYAUTH", 0),
                ("PROXY", b""),
                ("NOPROXY", b"*"),
                ("FRESH_CONNECT", 1),
                ("FORBID_REUSE", 1),
                ("HTTP_VERSION", 2),
            ):
                self.setopt(getattr(opts, name), value)
            return meter.perform(
                lambda: super(MeteredCurl, self).perform(*args, **kwargs), self.label
            )

    class BoundSession(session_class):
        def __init__(self, **kwargs):
            if any(
                kwargs.get(k)
                for k in (
                    "curl",
                    "thread",
                    "auth",
                    "proxy",
                    "proxies",
                    "proxy_auth",
                    "curl_options",
                )
            ):
                meter.refuse("unsupported_session_configuration")
            kwargs.update(
                curl=MeteredCurl(),
                use_thread_local_curl=False,
                trust_env=False,
                allow_redirects=False,
                max_redirects=0,
            )
            super().__init__(**kwargs)

        def request(self, method, url, **kwargs):
            meter.healthy()
            parsed = urlsplit(url)
            hosts = {
                "query1.finance.yahoo.com",
                "query2.finance.yahoo.com",
                "fc.yahoo.com",
                "guce.yahoo.com",
                "consent.yahoo.com",
                "finance.yahoo.com",
            }
            finnhub = parsed.netloc == "finnhub.io" and parsed.path == "/api/v1/stock/symbol"
            if (
                threading.get_ident() != creator
                or method.upper() != "GET"
                or parsed.scheme != "https"
                or parsed.username
                or parsed.password
                or not (finnhub or parsed.netloc in hosts)
                or any(
                    kwargs.get(k)
                    for k in ("stream", "auth", "proxy", "proxies", "proxy_auth", "files")
                )
            ):
                meter.refuse("unsupported_request_boundary")
            kwargs.update(
                allow_redirects=False,
                max_redirects=0,
                verify=True,
                timeout=min(meter.limits["request_seconds"], meter.deadline - meter.clock()),
            )
            self.curl.label = (
                "finnhub_universe"
                if finnhub
                else ("yahoo_chart" if "/chart/" in parsed.path else "yahoo_auth_or_metadata")
            )
            response = super().request(method, url, **kwargs)
            if meter.attempts:
                meter.attempts[-1].update(
                    response_status=response.status_code, response_bytes=len(response.content)
                )
                meter._journal(meter.attempts[-1])
            if 300 <= response.status_code < 400 or getattr(response, "redirect_count", 0):
                meter.refuse("redirect_refused_no_hop_followed")
            if response.status_code == 429:
                meter.refuse("provider_429_no_fallback")
            if len(response.content) > meter.limits["max_response_bytes"]:
                meter.refuse("response_size_cap")
            return response

        def ws_connect(self, *args, **kwargs):
            meter.refuse("websocket_unsupported")

        def stream(self, *args, **kwargs):
            meter.refuse("streaming_unsupported")

    return BoundSession


def _write(root: Path, name: str, value: object, cap: int) -> dict:
    data = _encode(value)
    if len(data) > cap:
        raise AcquisitionRefused("artifact_size_cap")
    with (root / name).open("xb") as stream:
        stream.write(data)
    return {"file": name, "sha256": _sha(data), "bytes": len(data)}


def _universe(rows: list[dict], extras: list[str], raw_sha: str, stamp: str, limits: dict) -> dict:
    from backend.services import opportunity_funnel as F
    from backend.services.funnel_staging import membership_sha256

    if not isinstance(rows, list) or not rows or len(rows) > limits["max_raw_rows"]:
        raise AcquisitionRefused("complete_raw_universe_required")
    admitted = []
    admitted_hashes = {}
    dropped = {"venue": 0, "type": 0, "symbol": 0}
    for row in rows:
        if not isinstance(row, dict) or any(
            not isinstance(row.get(k), str) for k in ("symbol", "mic", "type")
        ):
            raise AcquisitionRefused("raw_universe_schema")
        symbol = row["symbol"].strip().upper()
        if row["mic"] not in F.LISTED_VENUES:
            dropped["venue"] += 1
        elif row["type"].strip() not in ("Common Stock", "ADR"):
            dropped["type"] += 1
        elif (
            not symbol or not symbol.replace("-", "").isalnum() or "." in symbol or len(symbol) > 5
        ):
            dropped["symbol"] += 1
        else:
            admitted.append(symbol)
            admitted_hashes.setdefault(symbol, []).append(_sha(_encode(row)))
    provider_set = set(admitted)
    if not provider_set:
        raise AcquisitionRefused("provider_admitted_universe_empty_no_extras_fallback")
    names = sorted(provider_set | set(extras))
    if not names or len(names) > limits["max_symbols"]:
        raise AcquisitionRefused("complete_universe_exceeds_symbol_cap")
    if 1 + len(names) > limits["max_transport_attempts"]:
        raise AcquisitionRefused("complete_universe_exceeds_minimum_transport_plan")
    return {
        "tickers": names,
        "n": len(names),
        "membership_sha256": membership_sha256(names),
        "truncated": False,
        "source": "finnhub /stock/symbol?exchange=US + declared extras",
        "fetched_at": stamp,
        "exclusions": dropped,
        "venues": sorted(F.LISTED_VENUES),
        "raw_rows_sha256": raw_sha,
        "raw_rows_count": len(rows),
        "admitted_provider_rows": len(admitted),
        "duplicate_admitted_rows": len(admitted) - len(provider_set),
        "provider_admitted_tickers": sorted(provider_set),
        "admitted_provider_row_sha256s": admitted_hashes,
        "extras_lineage": {
            "requested": extras,
            "added": sorted(set(extras) - provider_set),
            "already_provider_admitted": sorted(set(extras) & provider_set),
        },
        "cache_provenance": {
            "mode": "uncached",
            "identity": "private_raw_universe_response",
            "sha256": raw_sha,
        },
    }


def _raw_history_payload(frame):
    """Capture returned fields/local dates before any CV projection or UTC conversion."""
    import numbers
    import pandas as pd
    from pandas.api.types import is_numeric_dtype, is_bool_dtype, is_complex_dtype

    columns = list(frame.columns)
    if any(not isinstance(c, str) for c in columns):
        raise AcquisitionRefused("unsupported_raw_history_columns")
    missing = sorted({"Open", "High", "Low", "Close", "Volume"} - set(columns))
    dated = isinstance(frame.index, pd.DatetimeIndex)
    original_index = [
        None if pd.isna(t) else t.isoformat() if dated else str(t) for t in frame.index
    ]
    dates = [None if pd.isna(t) or not dated else t.date().isoformat() for t in frame.index]
    nonfinite = []
    data = []
    for i, row in enumerate(frame.itertuples(index=False, name=None)):
        values = []
        for column, value in zip(columns, row):
            if hasattr(value, "item"):
                value = value.item()
            if isinstance(value, numbers.Real) and not isinstance(value, bool):
                if not math.isfinite(value):
                    nonfinite.append({"row": i, "column": column, "value": str(value)})
                    value = None
            elif value is pd.NA or value is pd.NaT:
                value = None
            elif value is not None and not isinstance(value, (str, bool)):
                raise AcquisitionRefused("unsupported_raw_history_value")
            values.append(value)
        data.append(values)
    ready = (
        not frame.empty
        and not missing
        and not frame.columns.has_duplicates
        and dated
        and not frame.index.hasnans
        and frame.index.is_unique
        and frame.index.is_monotonic_increasing
        and frame.index.equals(frame.index.normalize())
        and len(set(dates)) == len(dates)
    )
    if ready:
        fields = ["Open", "High", "Low", "Close", "Volume"]
        ready = all(
            is_numeric_dtype(frame[c].dtype)
            and not is_bool_dtype(frame[c].dtype)
            and not is_complex_dtype(frame[c].dtype)
            for c in fields
        )
        if ready:
            values = frame[fields].to_numpy(dtype=float, na_value=float("nan"))
            ready = all(
                all(math.isfinite(v) for v in row)
                and all(v > 0 for v in row[:4])
                and row[4] >= 0
                and row[4] % 1 == 0
                and row[2] <= min(row[0], row[3]) <= max(row[0], row[3]) <= row[1]
                for row in values
            )
    payload = {
        "columns": columns,
        "data": data,
        "index": original_index,
        "index_timezone": str(frame.index.tz) if dated and frame.index.tz is not None else None,
        "original_session_dates": dates,
        "nonfinite_values": nonfinite,
        "adjustment": "unadjusted; auto_adjust=False, back_adjust=False, repair=False",
    }
    readiness = {
        "missing_raw_ohlcv_fields": missing,
        "raw_ohlcv_structurally_ready": bool(ready),
        "grade_admission_ready": False,
    }
    return payload, readiness


def _collect(
    request: dict, root: Path, meter: AttemptMeter, session, history, *, finnhub_key=None
) -> dict:
    """Worker-only vertical slice; fake HTTP/history functions exercise it offline."""
    import pandas as pd
    from backend.services import opportunity_funnel as F
    from backend.services import funnel_staging as S

    validate_request(request, finnhub_key=finnhub_key)
    lim = request["limits"]

    def stamp():
        return datetime.now(timezone.utc).isoformat()

    result = {
        "mode": request["mode"],
        "status": "REFUSED",
        "promotion_eligible": False,
        "eligibility_enrichment_ranking": "not_evaluated",
        "source_pins": request["source_pins"],
        "transport_unit": "actual_synchronous_curl_perform",
        "raw_history": {},
        "artifacts": [],
        "started_at": stamp(),
    }
    try:
        if request["mode"] == "full_us":
            response = session.get(
                "https://finnhub.io/api/v1/stock/symbol",
                params={"exchange": "US", "token": finnhub_key},
            )
            if response.status_code != 200:
                raise AcquisitionRefused("finnhub_universe_http_failure")
            raw = response.content
            if finnhub_key.encode() in raw:
                raise AcquisitionRefused("secret_in_provider_body_refused")
            rows = json.loads(raw)
            if not isinstance(rows, list):
                raise AcquisitionRefused("raw_universe_not_a_complete_list")
            # Retain original successful response bytes, without credentials/request URL.
            if len(raw) > lim["max_artifact_bytes"]:
                raise AcquisitionRefused("raw_universe_size_cap")
            with (root / "universe_response.json").open("xb") as stream:
                stream.write(raw)
            result["raw_universe"] = {"file": "universe_response.json", "sha256": _sha(raw)}
            universe = _universe(rows, request["extras"], _sha(raw), stamp(), lim)
            result["universe"] = universe
            names = universe["tickers"]
        else:
            names = request["symbols"]
            result["artifact_kind"] = "frozen_five_constituent_qualification_not_full_funnel"
            result["symbols"] = names

        result["symbol_outcomes"] = {symbol: {"status": "not_attempted"} for symbol in names}
        result["artifacts"].append(
            _write(
                root,
                "plan.json",
                {
                    "mode": request["mode"],
                    "symbols": names,
                    "history_window": [request["history_start"], request["history_end"]],
                    "coverage_window": [request["coverage_start"], request["coverage_end"]],
                    "promotion_eligible": False,
                },
                lim["max_artifact_bytes"],
            )
        )

        def provider(batch_id, symbols):
            meter.healthy()
            pairs = []
            saved = {}
            for symbol in symbols:
                meter.healthy()
                outcome = result["symbol_outcomes"][symbol]
                first_attempt = len(meter.attempts)
                outcome.update(status="history_started", batch_id=batch_id)
                journal = root / "symbol_attempts.jsonl"
                with journal.open("ab") as stream:
                    stream.write(_encode({"symbol": symbol, **outcome}) + b"\n")
                try:
                    frame = history(
                        symbol,
                        session=session,
                        start=request["history_start"],
                        end=(_date(request["history_end"]) + timedelta(days=1)).isoformat(),
                        interval="1d",
                        auto_adjust=False,
                        back_adjust=False,
                        repair=False,
                        actions=False,
                        keepna=True,
                        raise_errors=True,
                        timeout=lim["request_seconds"],
                    )
                    if not isinstance(frame, pd.DataFrame):
                        raise AcquisitionRefused("history_schema")
                    # Full returned OHLCV/other fields and original local labels first.
                    # Never make Open/High/Low from Close or serialize midnight via UTC.
                    saved[symbol], readiness = _raw_history_payload(frame)
                    extent = {
                        "rows": len(frame),
                        "first_date": str(frame.index.min()),
                        "last_date": str(frame.index.max()),
                        "eligibility_certified": False,
                        **readiness,
                    }
                    extent["availability"] = (
                        "empty_history"
                        if frame.empty
                        else "observed_short_history"
                        if str(frame.index.min())[:10] > request["history_start"]
                        else "history_returned"
                    )
                    result["raw_history"][symbol] = extent
                    outcome["status"] = "history_returned"
                    if not isinstance(frame.index, pd.DatetimeIndex):
                        raise AcquisitionRefused("history_date_schema")
                    if not {"Close", "Volume"}.issubset(frame.columns):
                        raise AcquisitionRefused("coverage_close_volume_missing")
                    # Retain raw history above; normalize daily index only for explicit coverage.
                    frame = frame[["Close", "Volume"]].copy()
                    frame.index = frame.index.tz_localize(None)
                    selected = frame.loc[
                        (frame.index.date >= _date(request["coverage_start"]))
                        & (frame.index.date <= _date(request["coverage_end"]))
                    ]
                    pairs.append((symbol, selected))
                except Exception as exc:
                    result["raw_history"].setdefault(symbol, {"rows": None})["error_type"] = type(
                        exc
                    ).__name__
                    outcome.update(status="history_error", error_type=type(exc).__name__)
                    # Missing stays missing; the accepted coverage API accounts for it.
                outcome["transport_attempts"] = list(
                    range(first_attempt + 1, len(meter.attempts) + 1)
                )
                with journal.open("ab") as stream:
                    stream.write(_encode({"symbol": symbol, **outcome}) + b"\n")
            artifact = _write(root, f"history-{batch_id}.json", saved, lim["max_artifact_bytes"])
            result["artifacts"].append(artifact)
            return {
                "source": "yfinance unadjusted daily Close/Volume",
                "fetched_at": stamp(),
                "cache_provenance": {
                    "mode": "uncached",
                    "identity": artifact["file"],
                    "sha256": artifact["sha256"],
                },
                "prices": pairs,
            }

        if request["mode"] == "full_us":
            n_batches = (len(names) + lim["batch_size"] - 1) // lim["batch_size"]
            receipt = F.stage_price_coverage(
                universe=universe,
                provider=provider,
                limits=S.Limits(lim["batch_size"], n_batches, n_batches, lim["max_symbols"]),
                start_date=request["coverage_start"],
                end_date=request["coverage_end"],
                min_rows=request["coverage_min_rows"],
            )
            meter.healthy()
            if len(receipt.payload) > lim["max_artifact_bytes"]:
                raise AcquisitionRefused("price_receipt_size_cap")
            path = S.write_price_coverage(receipt, staging_dir=root / "funnel-price-staging")
            result["price_coverage"] = {
                "file": str(path.relative_to(root)),
                "sha256": _sha(receipt.payload),
            }
        else:
            outcomes = []
            for i in range(0, len(names), lim["batch_size"]):
                chunk = names[i : i + lim["batch_size"]]
                response = provider(f"B{i // lim['batch_size'] + 1:06d}", chunk)
                frames = dict(response["prices"])
                for symbol in chunk:
                    validation = (
                        S._frame(
                            frames[symbol],
                            _date(request["coverage_start"]),
                            _date(request["coverage_end"]),
                            request["coverage_min_rows"],
                        )
                        if symbol in frames
                        else {"status": "missing"}
                    )
                    outcomes.append({"symbol": symbol, **validation})
            result["outcomes"] = outcomes
            meter.healthy()
            if any(row["status"] != "valid" for row in outcomes):
                raise AcquisitionRefused("five_constituent_coverage_incomplete")
        result["status"] = "COMPLETE"
    except S.CoverageRefused as exc:
        result["coverage_refusal"] = exc.report
        result["reason"] = "complete_us_price_coverage_refused"
    except Exception as exc:
        result["reason"] = str(exc) if isinstance(exc, AcquisitionRefused) else type(exc).__name__
    result["attempts"] = meter.attempts
    result["transport_failure"] = meter.failure
    result["coverage_window"] = {
        k: request[k] for k in ("coverage_start", "coverage_end", "coverage_min_rows")
    }
    result["history_window"] = {k: request[k] for k in ("history_start", "history_end")}
    result["completed_at"] = stamp()
    result["raw_ohlcv_all_structurally_ready"] = bool(result.get("symbol_outcomes")) and (
        len(result["raw_history"]) == len(result["symbol_outcomes"])
        and all(
            x.get("raw_ohlcv_structurally_ready", False) for x in result["raw_history"].values()
        )
    )
    result["grade_admission_ready"] = False
    result["status_scope"] = "declared Close/Volume coverage, not OHLCV/native grade admission"
    _write(root, "acquisition.json", result, lim["max_artifact_bytes"])
    return result


def worker_main(stream) -> int:
    """Called only by the stdlib gated helper, after parent-owned Job binding."""
    payload = json.loads(stream.read(32769))
    request, key = payload["request"], payload["finnhub_key"]
    validate_request(request, finnhub_key=key)
    if source_pins(payload["site_dir"]) != request["source_pins"]:
        raise AcquisitionRefused("worker_source_pin_mismatch")
    runtime = _runtime_contract()
    if (
        payload["runtime"] != runtime
        or Path(sys.executable).resolve() != Path(runtime["executable"])
        or Path(sys.prefix).resolve() != Path(runtime["base_prefix"])
    ):
        raise AcquisitionRefused("worker_runtime_identity_mismatch")
    # -S suppresses site/.pth startup before Job binding. Add the pinned site
    # directory only now; never execute sitecustomize or arbitrary .pth code.
    sys.path.insert(0, payload["site_dir"])
    root = Path(request["run_dir"])
    if any((root / "cache").iterdir()):
        raise AcquisitionRefused("worker_cache_must_start_empty")
    import logging

    logging.disable(logging.CRITICAL)
    from curl_cffi import Curl, CurlOpt, requests as curl_requests

    meter = AttemptMeter(request["limits"], payload["deadline"], root)
    Bound = bound_session_class(curl_requests.Session, Curl, CurlOpt, meter)
    # Child-only namespace: cover even SDK-created auth/metadata sessions.
    curl_requests.Session = Bound
    curl_requests.session.Session = Bound
    import yfinance as yf

    yf.set_tz_cache_location(str(root / "cache"))
    with Bound(impersonate="chrome") as session:

        def history(symbol, **kwargs):
            bound = kwargs.pop("session")
            return yf.Ticker(symbol, session=bound).history(**kwargs)

        result = _collect(request, root, meter, session, history, finnhub_key=key)
    return 0 if result["status"] == "COMPLETE" else 2
