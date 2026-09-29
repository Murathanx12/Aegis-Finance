"""u_forecast: a dependency failure is named as one, retried, and seen (2026-09-28).

On 2026-09-27 the OpenClaw gateway dropped the day's first call (code 1006,
`RC_NONZERO`, 0 tokens, $0). `daily_forecast` filed it REFUSED_CAP -- the cap was
at $0.00 of $2.00 -- and REFUSED_CAP ended the UTC day: 0 rows on 09-27, 0 on
09-28. The health probe read max(made_at) over EVERY specialist, so 134
thesis-card and 33 source rows kept `u_forecast` ALIVE.

Pinned here, offline: a fake transport that drops the connection, a fake clock,
a fake sleep, a fake LLM reply, synthetic ledgers in tmp_path, dates from today.
No network, no LLM, no browser, no gateway.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as C
from scripts import night_investigator_forecast as N

GATEWAY_DROPPED = ("Gateway agent call connection closed; gateway closed "
                   "(1006 abnormal closure)")


@pytest.fixture
def env(monkeypatch, tmp_path):
    from backend.services import llm_telemetry as LT
    tele = tmp_path / "llm_calls.jsonl"
    monkeypatch.setenv(C.LLM_TELEMETRY_PATH_ENV, str(tele))
    LT.append([LT.build_call(provider="deepseek", model="deepseek-flash",
                             purpose="other", tokens_in=1)])
    return {"tele": tele, "ledger": tmp_path / "predictions.jsonl",
            "receipts": tmp_path / "forecasts"}


#: The fake clock starts at a FIXED hour of TODAY's UTC date (2026-09-29).
#: It used to start at `datetime.now()`, so the bounded-retries scenario (8 runs
#: x ~4,050 s of backoff + gap = ~9 h) crossed UTC midnight whenever the suite
#: ran after ~15:00Z; the next run then derived a NEW day, found no receipt and
#: got a fresh budget, and the test failed by the time of day. The date stays
#: current (never a literal calendar moment, protocol item 5); the hour is
#: controlled.
FAKE_CLOCK_START_HOUR_UTC = 1


def fixed_start(hour: int = FAKE_CLOCK_START_HOUR_UTC, *, day=None) -> datetime:
    """Today's UTC date (or `day`) at `hour`:00:00Z."""
    d = day or datetime.now(timezone.utc).date()
    return datetime(d.year, d.month, d.day, hour, tzinfo=timezone.utc)


def bounded_retries_span_s() -> float:
    """Fake seconds the bounded-retries scenario advances the clock by: every
    allowed run fails one name through all its attempts, then waits the gap."""
    per_run = (sum(float(x) for x in C.FORECAST_DEP_RETRY_BACKOFF_S[
                   :max(0, int(C.FORECAST_DEP_RETRY_MAX_ATTEMPTS) - 1)])
               + float(C.FORECAST_DEP_RETRY_MIN_GAP_S) + 1.0)
    return per_run * int(C.FORECAST_DEP_MAX_RUNS_PER_DAY)


class FakeClock:
    def __init__(self, start: datetime | None = None):
        self.t = start or fixed_start()
        self.slept: list[float] = []

    def now(self) -> datetime:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(float(s))
        self.t = self.t + timedelta(seconds=float(s))


class FakeTransport:
    """An `ask_fn` whose first `n_drops` calls fail the way the gateway did on
    09-27: an RC_NONZERO telemetry row with 0 tokens (costs $0), no reply.
    Later calls succeed with a priced row and a reply (the fake LLM)."""

    def __init__(self, n_drops: int):
        self.n_drops = n_drops
        self.calls: list[str] = []

    def __call__(self, pk: dict) -> dict:
        from backend.services import llm_telemetry as LT
        self.calls.append(pk["ticker"])
        if len(self.calls) <= self.n_drops:
            rec = LT.build_call(provider="deepseek", model="deepseek-flash",
                                purpose=C.FORECAST_PURPOSE, tokens_in=0, tokens_out=0,
                                meta={"via": "openclaw", "status": "RC_NONZERO"})
            LT.append([rec])
            return {"refused": "openclaw RC_NONZERO (rc 1)", "stderr": GATEWAY_DROPPED,
                    "transport_failed": True,
                    "_call": {"status": "RC_NONZERO", "call_id": rec.call_id,
                              "openclaw_cost_usd": None}}
        rec = LT.build_call(provider="deepseek", model="deepseek-flash",
                            purpose=C.FORECAST_PURPOSE, tokens_in=30000,
                            tokens_out=2000, meta={"via": "openclaw", "status": "OK"})
        LT.append([rec])
        return {"probability_1d": 0.55, "probability_5d": 0.45, "facts_used": ["x"],
                "falsifier": "y",
                "_call": {"status": "OK", "call_id": rec.call_id,
                          "openclaw_cost_usd": 0.01}}


def _run(env, clock: FakeClock, ask_fn, **kw):
    kw.setdefault("sources", {"murat_book": ["AAA", "BBB"]})
    kw.setdefault("cap_usd", 5.0)
    return N.daily_forecast(today=clock.now().date().isoformat(), ask_fn=ask_fn,
                            packet_fn=lambda t: {"ticker": t, "asof": "x"},
                            ledger_path=env["ledger"], telemetry_path=None,
                            receipt_dir=env["receipts"], sleep_fn=clock.sleep,
                            now_fn=clock.now, **kw)


def _receipt(env, clock) -> dict:
    p = env["receipts"] / f"day_{clock.now().date().isoformat()}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _rows(env) -> list[dict]:
    if not env["ledger"].exists():
        return []
    return [json.loads(l) for l in env["ledger"].read_text(encoding="utf-8").splitlines()]


# ───────────────────────────── the label and the retry ───────────────────────

def test_a_dropped_connection_is_retried_and_the_day_completes(env):
    clock = FakeClock()
    tr = FakeTransport(n_drops=2)
    res = _run(env, clock, tr)
    assert res["state"] == "DONE"
    assert res["dependency_failed_calls"] == 2 and res["dependency_retries"] == 2
    # the same name was asked again; the backoff came from config, in order
    assert tr.calls[:3] == ["AAA", "AAA", "AAA"]
    assert clock.slept == list(C.FORECAST_DEP_RETRY_BACKOFF_S[:2])
    assert sorted({r["ticker"] for r in _rows(env)}) == ["AAA", "BBB"]
    rc = _receipt(env, clock)
    assert rc["dependency"]["n_calls"] == 4 and rc["dependency"]["n_failed_calls"] == 2
    assert rc["dependency"]["failures"][0]["status"] == "RC_NONZERO"
    assert "1006" in rc["dependency"]["failures"][0]["stderr"]
    # the first-flush check ran on the first SUCCESSFUL call, not the dropped one
    assert rc["first_flush_check"]["call_status"] == "OK"
    assert rc["first_flush_check"]["ledger_delta_usd"] > 0


def test_a_gateway_that_stays_down_is_dependency_down_never_cap(env):
    clock = FakeClock()
    tr = FakeTransport(n_drops=10_000)
    res = _run(env, clock, tr)
    assert res["state"] == N.REFUSED_DEPENDENCY_DOWN
    assert res["state"] != N.REFUSED_CAP
    assert res["n_rows_written"] == 0 and _rows(env) == []
    n = int(C.FORECAST_DEP_RETRY_MAX_ATTEMPTS)
    assert len(tr.calls) == n and res["dependency_failed_calls"] == n
    assert len(clock.slept) == n - 1                    # sleeps BETWEEN calls only
    assert "was NOT the cause" in res["why"] and "$0.0000" in res["why"]
    rc = _receipt(env, clock)
    assert rc["dependency"]["runs_ended_down"] == 1
    assert "never restarted" in rc["dependency"]["degrade_path"]
    # the run fits the unit's time box: calls x agent timeout + total backoff
    worst = n * 420.0 + sum(C.FORECAST_DEP_RETRY_BACKOFF_S)
    assert worst < C.FORECAST_UNIT_TIMEOUT_S


def test_dependency_down_does_not_end_the_day(env):
    clock = FakeClock()
    _run(env, clock, FakeTransport(n_drops=10_000))
    # too soon: the gate waits FORECAST_DEP_RETRY_MIN_GAP_S
    clock.t += timedelta(seconds=C.FORECAST_DEP_RETRY_MIN_GAP_S / 2)
    early = _run(env, clock, FakeTransport(n_drops=0))
    assert "skipped" in early and "waits" in early["skipped"]
    assert _rows(env) == []
    # after the gap the day RESUMES and completes once the gateway is back
    clock.t += timedelta(seconds=C.FORECAST_DEP_RETRY_MIN_GAP_S)
    later = _run(env, clock, FakeTransport(n_drops=0))
    assert later["state"] == "DONE" and later["n_rows_written"] == 4
    rc = _receipt(env, clock)
    assert rc["resumed_from_state"] == N.REFUSED_DEPENDENCY_DOWN
    assert rc["dependency"]["runs"] == 2


def test_the_retries_per_day_are_bounded(env):
    clock = FakeClock()
    for _ in range(int(C.FORECAST_DEP_MAX_RUNS_PER_DAY)):
        r = _run(env, clock, FakeTransport(n_drops=10_000))
        assert r["state"] == N.REFUSED_DEPENDENCY_DOWN
        clock.t += timedelta(seconds=C.FORECAST_DEP_RETRY_MIN_GAP_S + 1)
    last = _run(env, clock, FakeTransport(n_drops=0))
    assert "skipped" in last and "no further retry today" in last["skipped"]


def test_the_fake_clock_keeps_the_bounded_scenario_inside_one_utc_date():
    """The clock fix, proven at a simulated late hour without touching the
    machine clock: from the fixed start the whole scenario stays on one date;
    from 20:00Z (what `datetime.now()` gave an evening run) it crosses."""
    span = timedelta(seconds=bounded_retries_span_s())
    start = FakeClock().t
    assert start.hour == FAKE_CLOCK_START_HOUR_UTC
    assert start.date() == datetime.now(timezone.utc).date()
    assert (start + span).date() == start.date()
    late = fixed_start(20)
    assert (late + span).date() != late.date()      # the old failure mode is real


def test_the_retry_budget_belongs_to_the_forecast_day_not_the_wall_date(env):
    """PRODUCTION side of item 1. A day whose runs straddle UTC midnight keeps
    ONE budget: the receipt is keyed on the forecast day passed in, and the gate
    reads that receipt, never the wall clock's date."""
    clock = FakeClock(fixed_start(20))
    day = clock.now().date().isoformat()
    for _ in range(int(C.FORECAST_DEP_MAX_RUNS_PER_DAY)):
        r = N.daily_forecast(today=day, ask_fn=FakeTransport(n_drops=10_000),
                             sources={"murat_book": ["AAA", "BBB"]}, cap_usd=5.0,
                             packet_fn=lambda t: {"ticker": t, "asof": "x"},
                             ledger_path=env["ledger"], telemetry_path=None,
                             receipt_dir=env["receipts"], sleep_fn=clock.sleep,
                             now_fn=clock.now)
        assert r["state"] == N.REFUSED_DEPENDENCY_DOWN
        clock.t += timedelta(seconds=C.FORECAST_DEP_RETRY_MIN_GAP_S + 1)
    assert clock.now().date().isoformat() != day     # the wall date moved on
    last = N.daily_forecast(today=day, ask_fn=FakeTransport(n_drops=0),
                            sources={"murat_book": ["AAA", "BBB"]}, cap_usd=5.0,
                            packet_fn=lambda t: {"ticker": t, "asof": "x"},
                            ledger_path=env["ledger"], telemetry_path=None,
                            receipt_dir=env["receipts"], sleep_fn=clock.sleep,
                            now_fn=clock.now)
    assert "skipped" in last and "no further retry today" in last["skipped"]


def test_a_true_cap_refusal_is_still_a_cap_refusal(env):
    from backend.services import llm_telemetry as LT
    one = LT.price_call("deepseek-flash", 30000, 2000)
    clock = FakeClock()
    tr = FakeTransport(n_drops=0)
    res = _run(env, clock, tr, cap_usd=1.5 * one,
               sources={"murat_book": ["AAA", "BBB", "CCC", "DDD"]})
    assert res["state"] == N.REFUSED_CAP
    assert len(tr.calls) == 2 and "cap" in res["why"]
    assert N.REFUSED_CAP in N.TERMINAL_STATES
    assert N.REFUSED_DEPENDENCY_DOWN not in N.TERMINAL_STATES


def test_ask_labels_a_transport_failure_and_a_cli_that_cannot_start(monkeypatch):
    from backend.services import openclaw_client as OC
    pk = {"ticker": "AAA"}
    monkeypatch.setattr(OC, "agent", lambda *a, **k: {
        "status": "RC_NONZERO", "rc": 1, "stderr": GATEWAY_DROPPED, "call_id": "c1"})
    a = N.ask(pk, keys=("probability_1d", "probability_5d"))
    assert a["transport_failed"] is True and a["_call"]["status"] == "RC_NONZERO"

    def boom(*a, **k):
        raise OSError("openclaw: not found")
    monkeypatch.setattr(OC, "agent", boom)
    assert N.ask(pk)["transport_failed"] is True
    # a model that answered with nothing is the NAME's refusal, not the gateway's
    monkeypatch.setattr(OC, "agent", lambda *a, **k: {"status": "EMPTY_LOG", "rc": 0})
    assert N.ask(pk)["transport_failed"] is False


# ───────────────────────────── the sim unit ──────────────────────────────────

def test_u_forecast_resumes_a_dependency_refusal_after_the_gap(monkeypatch, tmp_path):
    from scripts import sim_run as SR
    monkeypatch.setattr(SR._config, "OPTIMUS_LEDGER_DIR", tmp_path)
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    (tmp_path / "forecasts").mkdir()
    rp = tmp_path / "forecasts" / f"day_{day}.json"

    def write(last_failed: datetime):
        rp.write_text(json.dumps({
            "day": day, "state": N.REFUSED_DEPENDENCY_DOWN, "n_rows_written": 0,
            "dependency": {"runs_ended_down": 1,
                           "last_failed_utc": last_failed.isoformat(timespec="seconds")}}),
            encoding="utf-8")

    write(now - timedelta(seconds=60))
    monkeypatch.setattr(SR, "_in_subprocess",
                        lambda *a, **k: pytest.fail("must wait for the gap"))
    r = SR.u_forecast(tmp_path)
    assert "skipped" in r and r["status"] == "DEGRADED"

    write(now - timedelta(seconds=C.FORECAST_DEP_RETRY_MIN_GAP_S + 60))
    called = []
    monkeypatch.setattr(SR, "_in_subprocess", lambda *a, **k: called.append(1) or {
        "state": "DONE", "n_rows_written": 8})
    r = SR.u_forecast(tmp_path)
    assert called and r["status"] == "ok"


def test_u_forecast_a_terminal_cap_refusal_still_ends_the_day(monkeypatch, tmp_path):
    from scripts import sim_run as SR
    monkeypatch.setattr(SR._config, "OPTIMUS_LEDGER_DIR", tmp_path)
    day = datetime.now(timezone.utc).date().isoformat()
    (tmp_path / "forecasts").mkdir()
    (tmp_path / "forecasts" / f"day_{day}.json").write_text(json.dumps({
        "day": day, "state": N.REFUSED_CAP, "n_rows_written": 40}), encoding="utf-8")
    monkeypatch.setattr(SR, "_in_subprocess",
                        lambda *a, **k: pytest.fail("a cap refusal ends the day"))
    r = SR.u_forecast(tmp_path)
    assert "skipped" in r and r["status"] == "DEGRADED"


# ───────────────────────────── the per-writer health probe ───────────────────

def _ledger(tmp: Path, rows: list[dict]) -> Path:
    d = tmp / "optimus"
    d.mkdir(parents=True, exist_ok=True)
    (d / "predictions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return d


def _probe(optimus: Path, now: datetime):
    from backend.services import system_health as SH
    return SH.p_u_forecast(SH.ProbeCtx(optimus_dir=optimus, now=now, allow_proc=False))


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def test_the_probe_goes_red_when_the_scheduled_writer_is_silent_and_others_write(tmp_path):
    now = datetime.now(timezone.utc)
    rows = ([{"made_at": _iso(now - timedelta(hours=h)), "specialist": "thesis_card:thesis_card/v2"}
             for h in range(1, 20)]
            + [{"made_at": _iso(now - timedelta(days=3)), "specialist": "investigator:evidence_v3"}])
    r = _probe(_ledger(tmp_path, rows), now)
    assert r.verdict == "STALE"
    assert r.detail.startswith("DEGRADED: u_forecast")
    assert "thesis_card 19 (unscheduled, reported only)" in r.detail
    assert r.delta == 0


def test_the_probe_is_green_when_the_scheduled_writer_wrote(tmp_path):
    now = datetime.now(timezone.utc)
    rows = [{"made_at": _iso(now - timedelta(hours=1)), "specialist": "investigator:evidence_v3"}] * 6
    r = _probe(_ledger(tmp_path, rows), now)
    assert r.verdict == "ALIVE" and r.delta == 6


def test_the_probe_is_red_on_a_refused_day_receipt_even_with_yesterdays_rows(tmp_path):
    now = datetime.now(timezone.utc)
    yday = datetime.combine(now.date() - timedelta(days=1),
                            datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=1)
    opt = _ledger(tmp_path, [{"made_at": _iso(yday), "specialist": "investigator:evidence_v3"}])
    (opt / "forecasts").mkdir()
    (opt / "forecasts" / f"day_{now.date().isoformat()}.json").write_text(json.dumps({
        "state": N.REFUSED_DEPENDENCY_DOWN, "why": "the OpenClaw call failed 4 times"}),
        encoding="utf-8")
    r = _probe(opt, now)
    assert r.verdict == "STALE" and N.REFUSED_DEPENDENCY_DOWN in r.detail
