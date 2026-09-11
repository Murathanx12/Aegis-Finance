"""The desktop app's "computing", not "the screener doesn't work".

On Railway a warm loop keeps every heavy cache hot, so `cache_swr` almost never
reaches its synchronous branch. In the packaged app that loop is OFF by design
-- a laptop should not run a Monte Carlo every ten minutes -- so the first
request for the 80-ticker screener IS the cold compute (~2 min) against a 45 s
fetch timeout. It failed with a red error while the work was, in fact, running
in a thread nobody could see; the retry then threw that thread's progress away.

What is pinned here:
  * desktop + cold cache        -> 202 `{state, job, progress}`, ONE compute
  * desktop + warm cache        -> the value, no 202
  * the result lands in the SAME cache the endpoint reads
  * a failed background compute -> 503 with the reason, not an endless poll
  * NOT desktop                 -> unchanged (blocks, returns the value)
"""

import asyncio
import threading
import time

import pytest

from backend import cache as C


@pytest.fixture(autouse=True)
def _clean_cache_state():
    """Leave no in-flight key or progress row behind for the next test."""
    yield
    with C._swr_lock:
        C._swr_inflight.clear()
        C._progress.clear()
        C._failures.clear()


def _key(name: str) -> str:
    """Unique per run: `cache_set` also writes the DISK cache this repo shares."""
    return f"test_computing:{name}:{time.time_ns()}"


def _slow(release: threading.Event, value, calls: list):
    def compute():
        calls.append(1)
        C.report_progress(3, 80)
        release.wait(timeout=10)
        return value
    return compute


def _wait_until(predicate, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


# --------------------------------------------------------------- desktop mode

def test_a_cold_heavy_endpoint_answers_computing_instead_of_blocking(monkeypatch):
    monkeypatch.setenv("AEGIS_DESKTOP", "1")
    key, release, calls = _key("cold"), threading.Event(), []
    try:
        out = asyncio.run(C.cache_swr_202(key, 600, _slow(release, {"ok": 1}, calls)))
        assert isinstance(out, C._Computing)
        assert out.status == 202
        assert out.body["state"] == "computing"
        assert out.body["job"] == key
        assert _wait_until(lambda: C.computing_state(key) is not None)
        # The number is REAL -- it came from the compute, not from a guess.
        assert _wait_until(
            lambda: (C.computing_state(key) or {}).get("progress") == {"done": 3, "total": 80}
        ), C.computing_state(key)
    finally:
        release.set()


def test_a_second_request_does_not_start_a_second_two_minute_job(monkeypatch):
    monkeypatch.setenv("AEGIS_DESKTOP", "1")
    key, release, calls = _key("dedupe"), threading.Event(), []
    compute = _slow(release, {"ok": 1}, calls)
    try:
        for _ in range(4):
            out = asyncio.run(C.cache_swr_202(key, 600, compute))
            assert isinstance(out, C._Computing) and out.status == 202
        assert sum(calls) == 1, "one cold compute per key, not one per poll"
    finally:
        release.set()


def test_the_result_lands_in_the_cache_the_endpoint_reads(monkeypatch):
    monkeypatch.setenv("AEGIS_DESKTOP", "1")
    key, release, calls = _key("lands"), threading.Event(), []
    out = asyncio.run(C.cache_swr_202(key, 600, _slow(release, {"ok": 42}, calls)))
    assert isinstance(out, C._Computing)
    release.set()
    assert _wait_until(lambda: C.cache_peek(key, 10 ** 9)[0] is not None)
    # The NEXT request is an ordinary value through the ordinary path.
    again = asyncio.run(C.cache_swr_202(key, 600, _slow(release, {"ok": 0}, calls)))
    assert again == {"ok": 42}
    assert sum(calls) == 1


def test_a_warm_cache_never_sees_a_202(monkeypatch):
    monkeypatch.setenv("AEGIS_DESKTOP", "1")
    key = _key("warm")
    C.cache_set(key, {"ok": "cached"})
    assert asyncio.run(C.cache_swr_202(key, 600, lambda: {"ok": "recomputed"})) == {"ok": "cached"}


def test_a_stale_value_is_served_rather_than_a_202(monkeypatch):
    """A stale answer beats "come back later" -- that was already true of
    `cache_swr`, and desktop mode must not quietly take it away."""
    monkeypatch.setenv("AEGIS_DESKTOP", "1")
    key, release, calls = _key("stale"), threading.Event(), []
    C.cache_set(key, {"ok": "old"})
    try:
        # ttl=0 => the entry is stale; max_stale is large => still usable.
        got = asyncio.run(C.cache_swr_202(key, 0, _slow(release, {"ok": "new"}, calls)))
        assert got == {"ok": "old"}
    finally:
        release.set()


def test_a_failed_background_compute_is_a_503_not_an_endless_poll(monkeypatch):
    monkeypatch.setenv("AEGIS_DESKTOP", "1")
    key = _key("boom")

    def boom():
        raise RuntimeError("no data for you")

    out = asyncio.run(C.cache_swr_202(key, 600, boom))
    # It may still be starting; poll the way a client would, briefly.
    for _ in range(200):
        out = asyncio.run(C.cache_swr_202(key, 600, boom))
        if isinstance(out, C._Computing) and out.status == 503:
            break
        time.sleep(0.02)
    assert isinstance(out, C._Computing) and out.status == 503, out
    assert out.body["state"] == "failed"
    assert "no data for you" in out.body["detail"]


# ------------------------------------------------------------ the deployed API

def test_outside_desktop_mode_the_behaviour_is_unchanged(monkeypatch):
    """The deployed API must never hand a browser a 202. `cache_swr_202` is
    `cache_swr` there -- it blocks on the first-ever request and returns the
    value, exactly as it did before this existed."""
    monkeypatch.delenv("AEGIS_DESKTOP", raising=False)
    key, calls = _key("deployed"), []

    def compute():
        calls.append(1)
        return {"ok": "computed in request"}

    assert asyncio.run(C.cache_swr_202(key, 600, compute)) == {"ok": "computed in request"}
    assert sum(calls) == 1


def test_report_progress_outside_a_background_compute_is_a_noop():
    """Call sites carry no guard, so this must be safe from the warm loop, a
    direct call and a test. A raise here would take the screener down on
    Railway, where nothing is ever "computing"."""
    C.report_progress(5, 80)
    with C._swr_lock:
        assert C._progress == {}


# ------------------------------------------------------------------- the route

def test_computing_or_turns_the_marker_into_a_real_status_code():
    """The client tells "not yet" from "broken" by STATUS, not by sniffing the
    body -- so the marker has to become a response, not a 200 with a state
    field inside it."""
    from fastapi.responses import JSONResponse

    passthrough = {"stocks": []}
    assert C.computing_or(passthrough) is passthrough

    r = C.computing_or(C._Computing({"state": "computing", "job": "k",
                                     "progress": {"done": 1, "total": 80}}))
    assert isinstance(r, JSONResponse) and r.status_code == 202

    r = C.computing_or(C._Computing({"state": "failed", "job": "k", "detail": "x"}, status=503))
    assert isinstance(r, JSONResponse) and r.status_code == 503


def test_every_endpoint_the_warm_loop_prewarms_is_on_the_computing_path():
    """The warm loop's list IS the list of endpoints that are slow when cold.
    A target whose route still calls plain `cache_swr` hangs the desktop app
    for minutes -- the bug this file exists for. Read the ROUTE sources with
    the AST, so adding a warm target without wiring its route fails HERE."""
    import ast
    from pathlib import Path

    from backend.main import _endpoint_warm_targets

    keys = {k.split(":")[0] for k, _, _ in _endpoint_warm_targets()}
    assert keys, "the warm loop resolved no targets -- the gate cannot run"

    wired: set[str] = set()
    for src in (Path(__file__).resolve().parent.parent / "routers").glob("*.py"):
        # `utf-8-sig`: `routers/portfolio.py` carries a BOM, and `ast.parse`
        # rejects U+FEFF outright rather than skipping it.
        tree = ast.parse(src.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if name != "cache_swr_202" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                wired.add(first.value.split(":")[0])
            elif isinstance(first, ast.Name):
                # `cache_key = f"sp500_projection:{n}:{y}"` -- resolve the local.
                for assign in ast.walk(tree):
                    if (isinstance(assign, ast.Assign)
                            and any(isinstance(t, ast.Name) and t.id == first.id
                                    for t in assign.targets)
                            and isinstance(assign.value, ast.JoinedStr)
                            and assign.value.values
                            and isinstance(assign.value.values[0], ast.Constant)):
                        wired.add(str(assign.value.values[0].value).split(":")[0])

    missing = sorted(keys - wired)
    assert not missing, (
        f"warm-loop targets whose route still blocks when cold: {missing}. "
        "Wire each one as: computing_or(await cache_swr_202(...))"
    )
