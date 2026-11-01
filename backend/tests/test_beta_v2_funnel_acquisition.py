"""Tiny offline transports/processes only; no provider or native Job execution."""

from datetime import datetime, timezone
from types import SimpleNamespace
import json
import subprocess

import pandas as pd
import pytest

from backend.services import funnel_acquisition as A


def limits(**changes):
    return {
        "max_transport_attempts": 20,
        "request_seconds": 2,
        "wall_seconds": 30,
        "cleanup_seconds": 2,
        "job_commit_bytes": 512 * 1024**2,
        "max_response_bytes": 100000,
        "max_artifact_bytes": 1000000,
        "max_raw_rows": 20,
        "max_symbols": 10,
        "batch_size": 2,
        **changes,
    }


def request(root, **changes):
    return {
        "mode": "frozen_five",
        "symbols": sorted(A.FROZEN_FIVE),
        "extras": [],
        "run_dir": str(root / "run-1"),
        "history_start": "2026-10-22",
        "history_end": "2026-10-23",
        "coverage_start": "2026-10-23",
        "coverage_end": "2026-10-23",
        "coverage_min_rows": 1,
        "limits": limits(),
        "source_pins": {"fake": "a" * 64},
        "entitlements": {
            "yahoo": {
                "qualified": True,
                "scope": "private_personal_research_history",
                "evidence_ref": "fixture",
            }
        },
        **changes,
    }


def bars(start="2026-10-22"):
    return pd.DataFrame(
        {"Close": [10.0, 11.0], "Volume": [100.0, 200.0]}, index=pd.date_range(start, periods=2)
    )


def fixture_runtime(tmp_path, monkeypatch):
    base = tmp_path / "fixture-runtime"
    base.mkdir()
    for name in ("python.exe", "python312.dll", "python3.dll"):
        (base / name).write_bytes(("inert fixture " + name).encode())
    runtime = {
        "classification": "cpython_3_12_windows_direct_base",
        "executable": str(base / "python.exe"),
        "base_prefix": str(base),
        "version": [3, 12, 10],
        "pointer_bits": 64,
    }
    monkeypatch.setattr(A, "_runtime_contract", lambda: runtime)
    return runtime


def test_missing_contract_refuses_before_owner_or_io(monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail("missing contract reached operation")

    monkeypatch.setattr(A, "_source_paths", forbidden)
    monkeypatch.setattr(A, "_OwnedJob", forbidden)
    with pytest.raises(A.AcquisitionRefused):
        A.acquire({}, finnhub_key=None)


def test_meter_counts_actual_attempts_not_logical_callbacks(tmp_path):
    ticks = [0.0]
    m = A.AttemptMeter(limits(max_transport_attempts=2), 10.0, tmp_path, clock=lambda: ticks[0])
    m.perform(lambda: None, "yahoo_auth")
    m.perform(lambda: None, "yahoo_chart")
    called = []
    with pytest.raises(A.AcquisitionRefused):
        m.perform(lambda: called.append(True), "yahoo_retry")
    assert not called
    assert len(m.attempts) == 2
    assert m.failure == "transport_attempt_cap"


def test_meter_deadline_refuses_before_transport(tmp_path):
    m = A.AttemptMeter(limits(), 1.0, tmp_path, clock=lambda: 2.0)
    called = []
    with pytest.raises(A.AcquisitionRefused):
        m.perform(lambda: called.append(True), "yahoo_chart")
    assert not called and not m.attempts


def test_meter_error_is_counted_and_secret_text_not_saved(tmp_path):
    m = A.AttemptMeter(limits(), 20.0, tmp_path, clock=lambda: 0.0)

    def bad():
        raise RuntimeError("fixture-secret must never be retained")

    with pytest.raises(RuntimeError):
        m.perform(bad, "yahoo_auth")
    assert len(m.attempts) == 1
    assert "fixture-secret" not in (tmp_path / "attempts.jsonl").read_text()


@pytest.mark.parametrize(
    "changes",
    [
        {"symbols": ["EVO.ST"]},
        {"extras": ["AAA"]},
        {"coverage_end": "2026-10-24"},
        {"coverage_min_rows": 0},
        {"entitlements": {}},
        {"source_pins": {}},
        {"limits": limits(max_transport_attempts=True)},
    ],
)
def test_invalid_requests_refuse_before_io(tmp_path, changes):
    with pytest.raises(A.AcquisitionRefused):
        A.validate_request(request(tmp_path, **changes), finnhub_key=None)


def test_full_us_requires_finnhub_entitlement_before_io(tmp_path):
    r = request(tmp_path, mode="full_us", symbols=[])
    with pytest.raises(A.AcquisitionRefused):
        A.validate_request(r, finnhub_key="fixture-secret")


def test_quiet_window_includes_operation_and_cleanup():
    now = datetime(2026, 10, 25, 8, 34, 40, tzinfo=timezone.utc)
    with pytest.raises(A.AcquisitionRefused):
        A._check_window(now, wall_seconds=19, cleanup_seconds=2)
    A._check_window(now, wall_seconds=15, cleanup_seconds=2)


@pytest.mark.parametrize(
    "observed,wall,cleanup,refused",
    [
        ("2026-10-25T09:11:00+00:00", 84600, 2, True),
        ("2026-10-25T09:11:00+00:00", 84237, 2, False),
        ("2026-10-25T09:11:00+00:00", 84238, 2, True),
        ("2026-10-25T09:11:00+00:00", 84239, 2, True),
        ("2026-10-25T09:11:00+00:00", 7 * 3600, 2, False),
        ("2026-10-25T09:10:00+00:00", 84297, 2, False),
        ("2026-10-25T09:10:00+00:00", 84298, 2, True),
        ("2026-10-25T08:35:00+00:00", 0, 0, True),
        ("2026-10-25T09:09:59+00:00", 0, 0, True),
        ("2026-10-25T08:34:40+00:00", 18, 2, True),
        ("2026-12-31T09:11:00+00:00", 84600, 2, True),
        ("2026-10-25T09:11:00+00:00", 2 * 86400, 2, True),
        ("2026-10-25T09:11:00+00:00", 1e308, 1e308, True),
    ],
    ids=[
        "reviewer-next-day-repro",
        "next-day-before-boundary",
        "next-day-exact-boundary",
        "cleanup-crosses-next-day",
        "midnight-without-quiet-overlap",
        "quiet-end-allowed",
        "quiet-end-next-boundary",
        "quiet-start-refused",
        "inside-quiet-refused",
        "same-day-exact-boundary",
        "year-rollover",
        "multiple-days",
        "huge-finite-budgets",
    ],
)
def test_quiet_window_full_budget(observed, wall, cleanup, refused):
    now = datetime.fromisoformat(observed)
    if refused:
        with pytest.raises(A.AcquisitionRefused, match="quiet_window"):
            A._check_window(now, wall_seconds=wall, cleanup_seconds=cleanup)
    else:
        A._check_window(now, wall_seconds=wall, cleanup_seconds=cleanup)


def test_next_day_overlap_refuses_before_source_owner_or_activation(tmp_path, monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("overlapping budget reached source, path, owner or process")

    monkeypatch.setattr(A, "source_pins", forbidden)
    monkeypatch.setattr(A, "_private_path", forbidden)
    req = request(tmp_path, limits=limits(wall_seconds=84600))
    try:
        with pytest.raises(A.AcquisitionRefused, match="quiet_window"):
            A.acquire(
                req,
                finnhub_key=None,
                _job_factory=forbidden,
                _popen=forbidden,
                _clock=lambda: 0.0,
                _now=lambda: datetime(2026, 10, 25, 9, 11, tzinfo=timezone.utc),
            )
    finally:
        assert calls == []


def test_unsupported_job_refuses_without_starting_process(monkeypatch):
    monkeypatch.setattr(A.sys, "platform", "unsupported")
    with pytest.raises(A.AcquisitionRefused):
        A._OwnedJob(100000)


def fake_session(meter, *, inner_attempts=1, status=200, content=b"{}"):
    calls = []

    class Curl:
        def __init__(self):
            self.options = {}

        def setopt(self, key, value):
            self.options[key] = value

        def perform(self):
            calls.append(dict(self.options))

    class Session:
        def __init__(self, **kwargs):
            self.curl = kwargs["curl"]
            self.init = kwargs
            self.sent = []

        def request(self, method, url, **kwargs):
            self.sent.append(kwargs)
            # Simulate SDK retry/auth traffic inside one logical request.
            for _ in range(inner_attempts):
                self.curl.setopt("FOLLOWLOCATION", 1)
                self.curl.perform()
            return SimpleNamespace(status_code=status, content=content, redirect_count=0)

        def get(self, url, **kwargs):
            return self.request("GET", url, **kwargs)

    names = (
        "FOLLOWLOCATION",
        "MAXREDIRS",
        "HTTPAUTH",
        "PROXYAUTH",
        "PROXY",
        "NOPROXY",
        "FRESH_CONNECT",
        "FORBID_REUSE",
        "HTTP_VERSION",
    )
    options = SimpleNamespace(**{name: name for name in names})
    return A.bound_session_class(Session, Curl, options, meter), calls


def test_actual_boundary_caps_inner_retries_and_reapplies_redirect_policy(tmp_path):
    m = A.AttemptMeter(limits(max_transport_attempts=2), 10.0, tmp_path, clock=lambda: 0.0)
    Bound, calls = fake_session(m, inner_attempts=3)
    session = Bound()
    with pytest.raises(A.AcquisitionRefused, match="transport_attempt_cap"):
        session.get("https://query1.finance.yahoo.com/v8/finance/chart/AAA", allow_redirects=True)
    assert len(calls) == len(m.attempts) == 2
    assert all(
        row["FOLLOWLOCATION"] == 0
        and row["HTTPAUTH"] == 0
        and row["FRESH_CONNECT"] == 1
        and row["HTTP_VERSION"] == 2
        for row in calls
    )
    assert session.sent[0]["timeout"] == 2
    assert session.init["trust_env"] is False


@pytest.mark.parametrize("status,reason", [(302, "redirect_refused"), (429, "provider_429")])
def test_redirect_and_429_latch_without_follow_or_fallback(tmp_path, status, reason):
    m = A.AttemptMeter(limits(), 10.0, tmp_path, clock=lambda: 0.0)
    Bound, calls = fake_session(m, status=status)
    s = Bound()
    with pytest.raises(A.AcquisitionRefused, match=reason):
        s.get("https://fc.yahoo.com", allow_redirects=True)
    with pytest.raises(A.AcquisitionRefused):
        s.get("https://query2.finance.yahoo.com/v1/test/getcrumb")
    assert len(calls) == 1
    assert s.sent[0]["allow_redirects"] is False
    assert s.sent[0]["max_redirects"] == 0


@pytest.mark.parametrize(
    "method,url,kwargs",
    [
        ("POST", "https://consent.yahoo.com", {}),
        ("GET", "http://query1.finance.yahoo.com", {}),
        ("GET", "https://not-authorized.test", {}),
        ("GET", "https://query1.finance.yahoo.com", {"stream": True}),
        ("GET", "https://finnhub.io/api/v1/stock/metric", {}),
        ("GET", "https://query1.finance.yahoo.com", {"auth": ("a", "b")}),
    ],
)
def test_unsupported_boundary_refuses_before_perform(tmp_path, method, url, kwargs):
    m = A.AttemptMeter(limits(), 10.0, tmp_path, clock=lambda: 0.0)
    Bound, calls = fake_session(m)
    with pytest.raises(A.AcquisitionRefused):
        Bound().request(method, url, **kwargs)
    assert not calls and not m.attempts


def test_response_cap_is_not_claimed_as_wire_byte_cap(tmp_path):
    m = A.AttemptMeter(limits(max_response_bytes=1), 10.0, tmp_path, clock=lambda: 0.0)
    Bound, calls = fake_session(m, content=b"{}")
    with pytest.raises(A.AcquisitionRefused, match="response_size_cap"):
        Bound().get("https://fc.yahoo.com")
    assert len(calls) == 1  # post-transfer size check, not a pre-transfer byte limit


class FakeJob:
    def __init__(self, memory=1):
        self.bound = False
        self.closed = False

    def bind(self, pid):
        self.bound = True

    def close(self):
        self.closed = True


class FakeProcess:
    pid = 123

    def __init__(self, job, *, stall=False, bad_exit=False):
        self.job = job
        self.stall = stall
        self.bad_exit = bad_exit
        self.returncode = None
        self.wires = []
        self.killed = False

    def communicate(self, input=None, timeout=None):
        if input is not None:
            assert self.job.bound
            self.wires.append(input)
        if self.stall and not self.killed:
            raise subprocess.TimeoutExpired("owned fixture", timeout)
        self.returncode = 2 if self.bad_exit else 0

    def poll(self):
        return self.returncode

    def kill(self):
        assert self.job.closed
        self.killed = True


def test_job_bound_before_gate_and_closed_after_success():
    job = FakeJob()
    process = FakeProcess(job)
    A._supervise(
        process,
        job,
        b"A{}",
        10.0,
        1.0,
        clock=lambda: 0.0,
        now=lambda: datetime(2026, 10, 25, 6, tzinfo=timezone.utc),
    )
    assert process.wires == [b"A{}"] and job.closed


@pytest.mark.parametrize("mode", ["timeout", "cancel", "exit", "bind"])
def test_owned_failures_kill_only_owned_process_and_never_release_early(mode):
    job = FakeJob()
    process = FakeProcess(job, stall=mode in {"timeout", "cancel"}, bad_exit=mode == "exit")
    ticks = iter([0.0, 20.0])
    if mode == "bind":

        def bad_bind(pid):
            raise A.AcquisitionRefused("bind failed")

        job.bind = bad_bind
    with pytest.raises(A.AcquisitionRefused):
        A._supervise(
            process,
            job,
            b"A{}",
            10.0,
            1.0,
            clock=lambda: next(ticks, 20.0) if mode == "timeout" else 0.0,
            now=lambda: datetime(2026, 10, 25, 6, tzinfo=timezone.utc),
            cancel=lambda: mode == "cancel",
        )
    assert job.closed
    if mode in {"cancel", "bind"}:
        assert not process.wires
    if mode != "exit":
        assert process.killed


def test_acquire_isolates_child_environment_and_never_imports_sdk_in_parent(tmp_path, monkeypatch):
    runtime = fixture_runtime(tmp_path, monkeypatch)
    root = tmp_path / "funnel-acquisition-staging"
    root.mkdir()
    req = request(root)
    monkeypatch.setenv("FINNHUB_API_KEY", "fixture-parent-secret")
    monkeypatch.setenv("HTTPS_PROXY", "fixture-parent-proxy")
    monkeypatch.setattr(A, "source_pins", lambda: req["source_pins"])
    job = FakeJob()
    before = dict(A.os.environ)
    loaded = A.sys.modules.get("yfinance.data")

    def popen(argv, **kw):
        assert argv[0] == runtime["executable"]
        assert "-S" in argv and "-I" in argv
        assert "FINNHUB_API_KEY" not in kw["env"] and "HTTPS_PROXY" not in kw["env"]
        assert kw["env"]["HOME"] == str(kw["cwd"] / "home")
        (kw["cwd"] / "acquisition.json").write_text(
            json.dumps({"mode": "frozen_five", "status": "COMPLETE"})
        )
        return FakeProcess(job)

    A.acquire(
        req,
        finnhub_key=None,
        _job_factory=lambda _: job,
        _popen=popen,
        _clock=lambda: 0.0,
        _now=lambda: datetime(2026, 10, 25, 6, tzinfo=timezone.utc),
    )
    assert A.os.environ == before
    assert A.sys.modules.get("yfinance.data") is loaded


def full_request(root, **changes):
    req = request(root, mode="full_us", symbols=[], **changes)
    req["entitlements"]["finnhub"] = {
        "qualified": True,
        "scope": "stock_symbol_US",
        "evidence_ref": "fixture-account-scope",
    }
    return req


def rows():
    return [
        {"symbol": "AAA", "mic": "XNAS", "type": "Common Stock"},
        {"symbol": "BBB", "mic": "XNYS", "type": "ADR"},
        {"symbol": "AAA", "mic": "XNAS", "type": "Common Stock"},
        {"symbol": "OTC", "mic": "OOTC", "type": "Common Stock"},
    ]


def run_collection(tmp_path, *, mode="frozen_five", bad_symbol=None, **changes):
    (tmp_path / "funnel-price-staging").mkdir()
    req = (
        request(tmp_path, **changes) if mode == "frozen_five" else full_request(tmp_path, **changes)
    )
    meter = A.AttemptMeter(req["limits"], 100.0, tmp_path, clock=lambda: 0.0)
    key = None if mode == "frozen_five" else "fixture-secret"
    called = []

    class Session:
        def get(self, url, **kwargs):
            assert mode == "full_us"
            meter.perform(lambda: None, "finnhub_universe")
            return SimpleNamespace(status_code=200, content=json.dumps(rows()).encode())

    def history(symbol, **kwargs):
        called.append(symbol)
        assert kwargs["auto_adjust"] is False and kwargs["repair"] is False
        meter.perform(lambda: None, "yahoo_chart")
        if symbol == bad_symbol:
            raise RuntimeError("fixture-secret in provider error must not escape")
        return bars()

    return A._collect(req, tmp_path, meter, Session(), history, finnhub_key=key), called


def test_frozen_five_never_calls_finnhub_and_is_not_full_funnel(tmp_path):
    result, called = run_collection(tmp_path)
    assert set(called) == A.FROZEN_FIVE
    assert result["status"] == "COMPLETE"
    assert result["artifact_kind"] == "frozen_five_constituent_qualification_not_full_funnel"
    assert result["promotion_eligible"] is False
    assert not list((tmp_path / "funnel-price-staging").iterdir())
    assert all(r["first_date"].startswith("2026-10-22") for r in result["raw_history"].values())
    assert result["coverage_window"]["coverage_start"] == "2026-10-23"


def test_full_universe_raw_rows_extras_and_reviewed_coverage_handoff(tmp_path):
    result, called = run_collection(tmp_path, mode="full_us", extras=["BBB", "CCC"])
    assert result["status"] == "COMPLETE"
    assert set(called) == {"AAA", "BBB", "CCC"}
    u = result["universe"]
    assert u["n"] == 3 and u["truncated"] is False
    assert u["raw_rows_count"] == 4 and u["duplicate_admitted_rows"] == 1
    assert u["exclusions"] == {"venue": 1, "type": 0, "symbol": 0}
    assert u["extras_lineage"] == {
        "requested": ["BBB", "CCC"],
        "added": ["CCC"],
        "already_provider_admitted": ["BBB"],
    }
    assert json.loads((tmp_path / "universe_response.json").read_bytes()) == rows()
    receipt = json.loads((tmp_path / result["price_coverage"]["file"]).read_bytes())
    assert receipt["usable_price_coverage_complete"] is True
    assert receipt["window"]["start_date"] == receipt["window"]["end_date"] == "2026-10-23"
    assert receipt["claims"]["eligibility"] is False


@pytest.mark.parametrize("mode,symbol", [("frozen_five", "HAG.DE"), ("full_us", "AAA")])
def test_partial_history_never_produces_full_artifact_or_secret_logs(tmp_path, mode, symbol):
    result, _ = run_collection(tmp_path, mode=mode, bad_symbol=symbol)
    assert result["status"] == "REFUSED"
    assert not list((tmp_path / "funnel-price-staging").iterdir())
    assert "fixture-secret" not in (tmp_path / "acquisition.json").read_text()
    assert result["symbol_outcomes"][symbol]["status"] == "history_error"
    if mode == "full_us":
        assert len(result["coverage_refusal"]["outcomes"]) == 2


def test_full_domain_cap_retains_raw_response_and_does_not_shrink(tmp_path):
    result, called = run_collection(tmp_path, mode="full_us", limits=limits(max_symbols=1))
    assert result["status"] == "REFUSED" and not called
    assert result["reason"] == "complete_universe_exceeds_symbol_cap"
    assert (tmp_path / "universe_response.json").exists()
    assert not list((tmp_path / "funnel-price-staging").iterdir())


def test_source_qualification_hashes_files_without_sdk_import(tmp_path, monkeypatch):
    runtime = fixture_runtime(tmp_path, monkeypatch)
    one = tmp_path / "one.py"
    two = tmp_path / "native.pyd"
    one.write_bytes(b"source")
    two.write_bytes(b"inert native fixture")
    monkeypatch.setattr(A, "_source_paths", lambda site=None: {"one": one, "native": two})
    before = A.sys.modules.get("yfinance.data")
    first = A.source_pins()
    assert first["runtime/identity"] == A._sha(A._encode(runtime))
    one.write_bytes(b"changed source")
    assert A.source_pins()["one"] != first["one"]
    assert A.source_pins()["native"] == first["native"]
    assert A.sys.modules.get("yfinance.data") is before
    one.unlink()
    with pytest.raises(A.AcquisitionRefused, match="source_qualification_files_unavailable"):
        A.source_pins()


@pytest.mark.parametrize("reason", ["pins", "deadline", "cancel"])
def test_source_or_deadline_failure_precedes_job_and_run_directory(tmp_path, monkeypatch, reason):
    root = tmp_path / "funnel-acquisition-staging"
    root.mkdir()
    req = request(root)
    ticks = [0.0]
    owners = []

    def observed_pins():
        if reason == "deadline":
            ticks[0] = 40.0
        return {} if reason == "pins" else req["source_pins"]

    monkeypatch.setattr(A, "source_pins", observed_pins)
    with pytest.raises(A.AcquisitionRefused):
        A.acquire(
            req,
            finnhub_key=None,
            _job_factory=lambda m: owners.append(m),
            _clock=lambda: ticks[0],
            _cancel=lambda: reason == "cancel",
            _now=lambda: datetime(2026, 10, 25, 6, tzinfo=timezone.utc),
        )
    assert not owners and not list(root.iterdir())


@pytest.mark.parametrize("parent", ["backend", "data", ".cache", "funnel_history"])
def test_protected_paths_refuse_without_creation(tmp_path, parent):
    root = tmp_path / parent / "funnel-acquisition-staging"
    root.mkdir(parents=True)
    with pytest.raises(A.AcquisitionRefused):
        A._private_path(root / "new")
    assert not list(root.iterdir())


def test_prior_run_and_artifacts_are_immutable(tmp_path):
    root = tmp_path / "funnel-acquisition-staging"
    root.mkdir()
    run = root / "prior"
    run.mkdir()
    original = A._write(run, "receipt.json", {"original": True}, 1000)
    with pytest.raises(A.AcquisitionRefused):
        A._private_path(run)
    with pytest.raises(FileExistsError):
        A._write(run, "receipt.json", {"replacement": True}, 1000)
    assert A._sha((run / "receipt.json").read_bytes()) == original["sha256"]


def test_actual_request_timeout_is_clamped_to_remaining_aggregate_time(tmp_path):
    m = A.AttemptMeter(limits(), 0.25, tmp_path, clock=lambda: 0.0)
    Bound, calls = fake_session(m)
    s = Bound()
    s.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=100)
    assert s.sent[0]["timeout"] == 0.25 and len(calls) == 1


@pytest.mark.parametrize(
    "fault", [None, "membership_error", "not_member", "image_error", "wrong_image", "wrong_hash"]
)
def test_subprocess_owner_cap_is_native_job_commit_readback(tmp_path, monkeypatch, fault):
    runtime = fixture_runtime(tmp_path, monkeypatch)

    class Function:
        def __init__(self, fn):
            self.fn = fn

        def __call__(self, *args):
            return self.fn(*args)

    saved = {}

    def set_limit(handle, kind, pointer, size):
        saved["flags"] = pointer._obj.basic.flags
        saved["memory"] = pointer._obj.job_memory
        return True

    def query(handle, kind, pointer, size, length):
        pointer._obj.basic.flags = saved["flags"]
        pointer._obj.job_memory = saved["memory"]
        return True

    def member(process, handle, pointer):
        pointer._obj.value = fault != "not_member"
        return fault != "membership_error"

    def image(process, flags, buffer, size):
        buffer.value = (
            str(tmp_path / "wrong.exe") if fault == "wrong_image" else runtime["executable"]
        )
        size._obj.value = len(buffer.value)
        return fault != "image_error"

    kernel = SimpleNamespace(
        **{
            name: Function(fn)
            for name, fn in {
                "CreateJobObjectW": lambda *a: 101,
                "SetInformationJobObject": set_limit,
                "QueryInformationJobObject": query,
                "OpenProcess": lambda *a: 202,
                "AssignProcessToJobObject": lambda *a: True,
                "IsProcessInJob": member,
                "QueryFullProcessImageNameW": image,
                "CloseHandle": lambda *a: True,
            }.items()
        }
    )
    monkeypatch.setattr(A.sys, "platform", "win32")
    monkeypatch.setattr(A.ctypes, "WinDLL", lambda *a, **k: kernel, raising=False)
    digest = (
        "0" * 64 if fault == "wrong_hash" else A._sha(A.Path(runtime["executable"]).read_bytes())
    )
    job = A._OwnedJob(1234567, expected_image=(runtime["executable"], digest))
    assert job.attestation == {"flags": 0x2200, "aggregate_worker_commit_bytes": 1234567}
    wires = []
    process = SimpleNamespace(
        pid=42,
        returncode=0,
        poll=lambda: 0,
        kill=lambda: None,
        communicate=lambda input=None, timeout=None: wires.append(input) if input else None,
    )
    try:
        if fault:
            with pytest.raises(A.AcquisitionRefused, match="owned_worker_"):
                A._supervise(
                    process,
                    job,
                    b"A{}",
                    10.0,
                    1.0,
                    clock=lambda: 0.0,
                    now=lambda: datetime(2026, 10, 25, 6, tzinfo=timezone.utc),
                )
        else:
            A._supervise(
                process,
                job,
                b"A{}",
                10.0,
                1.0,
                clock=lambda: 0.0,
                now=lambda: datetime(2026, 10, 25, 6, tzinfo=timezone.utc),
            )
            assert job.attestation["worker_in_private_job"] is True
            assert job.attestation["worker_image_sha256"] == digest
    finally:
        assert wires == ([] if fault else [b"A{}"])
    assert job.handle is None


def test_runtime_file_pins_bind_base_executable_and_dlls(tmp_path, monkeypatch):
    runtime = fixture_runtime(tmp_path, monkeypatch)
    # Supply explicit fixture SDK paths; no installed providers are needed.
    one = tmp_path / "sdk.py"
    one.write_bytes(b"inert sdk fixture")
    runtime_paths = {
        k: v for k, v in A._source_paths(str(tmp_path)).items() if k.startswith("runtime/")
    }
    monkeypatch.setattr(A, "_source_paths", lambda site=None: {"sdk": one, **runtime_paths})
    before = A.source_pins()
    A.Path(runtime["executable"]).write_bytes(b"changed binary")
    after = A.source_pins()
    assert before["runtime/base_interpreter"] != after["runtime/base_interpreter"]
    assert before["runtime/python312.dll"] == after["runtime/python312.dll"]
    runtime["version"] = [3, 12, 11]
    assert after["runtime/identity"] != A.source_pins()["runtime/identity"]


def test_default_runtime_refuses_unsupported_host_without_sdk_access(monkeypatch):
    monkeypatch.setattr(A.sys, "platform", "unsupported")
    with pytest.raises(A.AcquisitionRefused, match="unsupported_direct_worker_runtime"):
        A._runtime_contract()


@pytest.mark.parametrize("defect", [None, "launcher_path", "wrong_version", "venv_config"])
def test_direct_runtime_classification_uses_explicit_fixtures(tmp_path, monkeypatch, defect):
    base = tmp_path / "base"
    base.mkdir()
    executable = base / "python.exe"
    executable.write_bytes(b"inert interpreter fixture")
    monkeypatch.setattr(A.sys, "platform", "win32")
    monkeypatch.setattr(
        A.sys, "version_info", (3, 13, 0) if defect == "wrong_version" else (3, 12, 10)
    )
    monkeypatch.setattr(A.sys, "base_prefix", str(base))
    monkeypatch.setattr(
        A.sys,
        "_base_executable",
        str(base / "Scripts" / "python.exe") if defect == "launcher_path" else str(executable),
    )
    if defect == "venv_config":
        (base / "pyvenv.cfg").write_bytes(b"inert venv fixture")
    if defect:
        with pytest.raises(A.AcquisitionRefused):
            A._runtime_contract()
    else:
        assert A._runtime_contract()["executable"] == str(executable.resolve())


@pytest.mark.parametrize("defect", ["image", "prefix", "contract"])
def test_worker_runtime_mismatch_refuses_before_any_sdk_import(tmp_path, monkeypatch, defect):
    import builtins
    import io

    runtime = fixture_runtime(tmp_path, monkeypatch)
    req = request(tmp_path)
    monkeypatch.setattr(A, "source_pins", lambda site=None: req["source_pins"])
    monkeypatch.setattr(
        A.sys,
        "executable",
        str(tmp_path / "launcher.exe") if defect == "image" else runtime["executable"],
    )
    monkeypatch.setattr(
        A.sys, "prefix", str(tmp_path) if defect == "prefix" else runtime["base_prefix"]
    )
    payload = {
        "request": req,
        "finnhub_key": None,
        "site_dir": str(tmp_path),
        "runtime": {} if defect == "contract" else runtime,
    }
    imports = []
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in {"yfinance", "curl_cffi"}:
            imports.append(name)
            raise AssertionError("mismatched runtime imported SDK")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    try:
        with pytest.raises(A.AcquisitionRefused, match="worker_runtime_identity_mismatch"):
            A.worker_main(io.BytesIO(A._encode(payload)))
    finally:
        assert imports == []


def test_source_has_no_owner_import_or_parent_sdk_import():
    import ast

    tree = ast.parse(A.Path(A.__file__).read_text())
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert all("yfinance" not in ast.unparse(n) and "curl_cffi" not in ast.unparse(n) for n in top)
    assert "local_branching_task" not in ast.unparse(tree)
    assert "llama_server" not in "\n".join(
        ast.unparse(n) for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
    )


def test_cap_latched_inside_history_cannot_be_hidden_by_valid_frames(tmp_path):
    req = request(tmp_path, limits=limits(max_transport_attempts=5))
    (tmp_path / "funnel-price-staging").mkdir()
    meter = A.AttemptMeter(req["limits"], 100.0, tmp_path, clock=lambda: 0.0)

    def history(symbol, **kwargs):
        for _ in range(2):
            try:
                meter.perform(lambda: None, "yahoo_auth_or_chart")
            except A.AcquisitionRefused:
                pass  # emulate a provider SDK swallowing its own errors
        return bars()

    result = A._collect(req, tmp_path, meter, None, history)
    assert result["status"] == "REFUSED"
    assert result["transport_failure"] == "transport_attempt_cap"
    assert len(result["attempts"]) == 5
    assert set(result["symbol_outcomes"]) == A.FROZEN_FIVE
    assert not list((tmp_path / "funnel-price-staging").iterdir())


def test_short_raw_history_is_separate_from_exact_session_coverage(tmp_path):
    req = request(tmp_path)
    (tmp_path / "funnel-price-staging").mkdir()
    meter = A.AttemptMeter(req["limits"], 100.0, tmp_path, clock=lambda: 0.0)
    result = A._collect(req, tmp_path, meter, None, lambda *a, **k: bars().iloc[-1:])
    assert result["status"] == "COMPLETE"
    assert all(
        x["availability"] == "observed_short_history"
        and x["rows"] == 1
        and not x["eligibility_certified"]
        for x in result["raw_history"].values()
    )
    assert all(x["rows"] == 1 and x["status"] == "valid" for x in result["outcomes"])


def test_european_midnight_full_ohlcv_survives_raw_roundtrip_and_cv_projection(tmp_path):
    req = request(tmp_path)
    (tmp_path / "funnel-price-staging").mkdir()
    meter = A.AttemptMeter(req["limits"], 100.0, tmp_path, clock=lambda: 0.0)
    original = pd.DataFrame(
        {
            "Open": [9.5, 10.5],
            "High": [11.0, 12.0],
            "Low": [9.0, 10.0],
            "Close": [10.0, 11.0],
            "Volume": [100.0, 200.0],
        },
        index=pd.date_range("2026-10-22", periods=2, tz="Europe/Stockholm"),
    )
    result = A._collect(req, tmp_path, meter, None, lambda *a, **k: original.copy())
    assert result["status"] == "COMPLETE"
    saved = json.loads((tmp_path / "history-B000001.json").read_bytes())["EVO.ST"]
    assert saved["columns"] == list(original.columns)
    assert saved["data"] == original.to_numpy().tolist()
    assert saved["index_timezone"] == "Europe/Stockholm"
    assert saved["original_session_dates"] == ["2026-10-22", "2026-10-23"]
    assert saved["index"][1] == "2026-10-23T00:00:00+02:00"
    restored = pd.DatetimeIndex([pd.Timestamp(x) for x in saved["index"]]).tz_convert(
        saved["index_timezone"]
    )
    assert restored.equals(original.index)
    # A UTC date would be the previous day; the explicit original session labels win.
    assert pd.Timestamp(saved["index"][1]).tz_convert("UTC").date().isoformat() == "2026-10-22"
    assert result["raw_history"]["EVO.ST"]["raw_ohlcv_structurally_ready"] is True
    assert result["raw_history"]["EVO.ST"]["grade_admission_ready"] is False
    assert all(
        r["status"] == "valid"
        and r["first_date"] == "2026-10-23"
        and r["schema"] == ["date", "Close", "Volume"]
        for r in result["outcomes"]
    )


def test_close_volume_only_is_retained_but_not_ohlcv_admission_ready(tmp_path):
    result, _ = run_collection(tmp_path)
    assert result["status"] == "COMPLETE"  # CV coverage remains independently useful.
    raw = json.loads((tmp_path / "history-B000001.json").read_bytes())["EVO.ST"]
    assert raw["columns"] == ["Close", "Volume"]
    assert "Open" not in raw["columns"]
    assert not result["raw_ohlcv_all_structurally_ready"]
    assert not result["grade_admission_ready"]
    for extent in result["raw_history"].values():
        assert extent["missing_raw_ohlcv_fields"] == ["High", "Low", "Open"]
        assert not extent["raw_ohlcv_structurally_ready"]
        assert not extent["grade_admission_ready"]


def test_nonfinite_ohlc_remains_explicit_and_does_not_poison_cv_coverage(tmp_path):
    req = request(tmp_path)
    (tmp_path / "funnel-price-staging").mkdir()
    meter = A.AttemptMeter(req["limits"], 100.0, tmp_path, clock=lambda: 0.0)
    frame = bars()
    frame["Open"] = [9.0, float("inf")]
    frame["High"] = [11.0, 12.0]
    frame["Low"] = [8.0, 10.0]
    result = A._collect(req, tmp_path, meter, None, lambda *a, **k: frame.copy())
    assert result["status"] == "COMPLETE"
    raw = json.loads((tmp_path / "history-B000001.json").read_bytes())["EVO.ST"]
    assert raw["nonfinite_values"] == [{"row": 1, "column": "Open", "value": "inf"}]
    assert raw["data"][1][raw["columns"].index("Open")] is None
    assert not result["raw_history"]["EVO.ST"]["raw_ohlcv_structurally_ready"]


def test_empty_admitted_provider_domain_cannot_fall_back_to_extras():
    with pytest.raises(A.AcquisitionRefused, match="no_extras_fallback"):
        A._universe(
            [{"symbol": "OTC", "mic": "OOTC", "type": "Common Stock"}],
            ["AAA"],
            "a" * 64,
            "2026-10-23T00:00:00+00:00",
            limits(),
        )
