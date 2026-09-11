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


# ===========================================================================
# THE DESKTOP SCREENER RUNS OVER THE REAL UNIVERSE (O10b / O8)
# ===========================================================================
#
# "It shows only 56 stocks -- I thought we analyzed all the stocks in the
# market" (Murat, 2026-09-11). He was right about the number: `_screener`'s
# default universe is `stock_universe.sectors` x `screener_per_sector: 5`,
# capped at 80, which dedupes to 56 curated S&P names.
#
# The deep pass is a Monte Carlo plus a yfinance history per name: measured
# 2026-09-11 on this laptop at roughly 2.5 s/name at 8 workers, so 3,056 names
# is about 2.8 hours. Hence two tiers, and hence these tests -- the risk is not
# that it is slow, it is that a name WITHOUT a Monte Carlo comes back looking
# like one WITH it.

def test_the_cheap_row_leaves_every_monte_carlo_field_none():
    """A Sharpe ratio that was never computed must not appear as a number.
    None, not 0.0 and not an estimate from the cheap fields: the page renders
    None as an em dash and a 0.0 as a measurement."""
    from backend.routers import stock as S

    sc = {"symbol": "TEST", "identity": {"sector": "Widgets"},
          "engine_prior": {"upside": 0.25, "ratio": 1.25, "verdict": "admitted_shadow"},
          "p_beat": {"debiased": 0.46}, "learner_v1": {"score": 0.48},
          "execution": {"median_dollar_volume": 1.0e7, "tier": "FULL"}}
    row = S._cheap_row(sc)
    assert row["ticker"] == "TEST" and row["analysed"] == "scorecard"
    assert row["upside"] == 0.25 and row["p_beat"] == 0.46
    for deep in ("current_price", "expected_return", "sharpe", "prob_loss",
                 "volatility", "beta", "crash_prob_3m", "signal"):
        assert row[deep] is None, f"{deep} must be None on a name with no deep pass"


def test_the_deep_rank_prefers_our_own_estimate_then_capacity():
    """Ranking on `upside` would hand the Monte Carlo budget to two-analyst
    micro caps whose target is twenty times the price. `p_beat` is our own
    number, and dollar volume breaks the tie toward names that can be traded."""
    from backend.routers import stock as S

    a = {"p_beat": 0.47, "median_dollar_volume": 1e6}
    b = {"p_beat": 0.47, "median_dollar_volume": 1e9}
    c = {"p_beat": 0.20, "median_dollar_volume": 1e12}
    missing = {"p_beat": None, "median_dollar_volume": None}
    ranked = sorted([a, c, missing, b], key=S._deep_rank, reverse=True)
    assert ranked[0] is b and ranked[1] is a and ranked[2] is c
    assert ranked[-1] is missing, "a name with no estimate never outranks one with"


def test_the_universe_reader_finds_every_scorecard_or_says_why():
    from backend.routers import stock as S

    scorecards, meta = S._universe_scorecards()
    if not scorecards:
        assert meta.get("universe_error"), "an empty universe must NAME its reason"
        pytest.skip(f"no universe file in this checkout: {meta['universe_error']}")
    assert meta["universe_rows"] == len(scorecards) > 1000
    assert meta["universe_source"].endswith(".jsonl")
    assert "potential_universe" in meta["universe_source"]


def test_the_desktop_screener_publishes_the_whole_universe_before_it_computes(monkeypatch):
    """TIER 1 is the point: the page shows every name within a second, and the
    Monte Carlo columns fill in afterwards. If tier 1 were published only at
    the end, the app would sit on a spinner for ten minutes again."""
    from backend.routers import stock as S

    published: list[dict] = []
    monkeypatch.setattr(S, "cache_set", lambda k, v: published.append((k, v)), raising=False)

    scorecards, meta = S._universe_scorecards()
    if not scorecards:
        pytest.skip("no universe file in this checkout")

    # The deep tier is replaced outright: this test is about tier 1 and must
    # not make 200 network calls to prove it.
    seen = {}

    def _fake_screener(tickers=None, *, on_batch=None, batch_size=25, extra=None):
        seen["tickers"] = tickers
        return {"stocks": [], "market_signal": {}, "count": 0}

    monkeypatch.setattr(S, "_screener", _fake_screener)
    monkeypatch.setattr(S, "cache_set", lambda k, v: published.append((k, v)), raising=False)
    import backend.cache as C
    monkeypatch.setattr(C, "cache_set", lambda k, v: published.append((k, v)))

    out = S._screener_desktop()
    assert published, "tier 1 was never published; the page would show nothing"
    first_key, first_payload = published[0]
    assert first_key == "stock_screener"
    assert first_payload["count"] == meta["universe_rows"] > 1000
    assert first_payload["deep_analysed"] == 0
    assert first_payload["deep_pending"] == first_payload["deep_target"]
    assert first_payload["universe_source"] == meta["universe_source"]
    # The deep tier was asked for a BOUNDED set, not the whole universe.
    assert len(seen["tickers"]) == S.DESKTOP_DEEP_NAMES <= meta["universe_rows"]
    assert out["count"] == meta["universe_rows"]
    assert out["universe_name"].startswith("tracker universe")
    assert "em dash" in out["horizon"]


def test_the_payload_names_the_universe_so_the_page_cannot_overclaim():
    """The subtitle used to say "Top S&P 500 stocks" over 56 curated names.
    The page now prints `universe_name` and `universe_rows`, which means the
    payload must carry them or the claim silently comes back."""
    from backend.routers import stock as S

    payload = S._public_screener_payload(
        [], {}, None,
        {"universe_name": "tracker universe", "universe_rows": 3056,
         "universe_source": "backend/data/optimus/potential_universe/x.jsonl"})
    assert payload["universe_name"] == "tracker universe"
    assert payload["universe_rows"] == 3056
    assert payload["universe_source"].endswith(".jsonl")


def test_the_deployed_screener_keeps_its_cap_and_its_shape(monkeypatch):
    """3,056 Monte Carlos on every TTL is a bill, not a feature. The deployed
    path must keep the curated list -- and must not start carrying a
    `universe_name` that would make the website claim breadth it has not got."""
    import ast as _ast
    from pathlib import Path as _P

    src = _P(__file__).resolve().parent.parent / "routers" / "stock.py"
    tree = _ast.parse(src.read_text(encoding="utf-8-sig"))
    fn = next(n for n in _ast.walk(tree)
              if isinstance(n, _ast.AsyncFunctionDef) and n.name == "get_stock_screener")
    src_text = _ast.unparse(fn)
    assert "desktop_mode()" in src_text, (
        "the screener route no longer branches on desktop mode; either the "
        "deployed API is about to run 3,056 Monte Carlos or the desktop app "
        "is back to 56 names")
    assert "_screener_desktop" in src_text and "_screener" in src_text
