"""u_forecast: once per UTC day, h=1 AND h=5 rows, a cap read from the ledger
the calls are written to.

No network and no LLM: `ask_fn` is a stub that writes the same telemetry row a
real OpenClaw call writes, so the cap is exercised against the real reader.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from scripts import night_investigator_forecast as N


@pytest.fixture
def env(monkeypatch, tmp_path):
    from backend import config as C
    tele = tmp_path / "llm_calls.jsonl"
    monkeypatch.setenv(C.LLM_TELEMETRY_PATH_ENV, str(tele))
    _seed()
    return {"tele": tele, "ledger": tmp_path / "predictions.jsonl",
            "receipts": tmp_path / "forecasts"}


def _seed():
    """A telemetry ledger that exists: in production it always does, and an
    unopenable one is its own refusal (tested separately)."""
    from backend.services import llm_telemetry as LT
    LT.append([LT.build_call(provider="deepseek", model="deepseek-flash",
                             purpose="other", tokens_in=1)])


def _stub_ask(cost_tokens_in=30000, calls=None):
    from backend.services import llm_telemetry as LT
    from backend import config as C

    def ask(pk):
        rec = LT.build_call(provider="deepseek", model="deepseek-flash",
                            purpose=C.FORECAST_PURPOSE, tokens_in=cost_tokens_in,
                            tokens_out=2000, meta={"via": "openclaw", "status": "OK"})
        LT.append([rec])
        if calls is not None:
            calls.append(pk["ticker"])
        return {"ticker": pk["ticker"], "probability_1d": 0.60,
                "probability_5d": 0.40, "facts_used": ["x"], "falsifier": "y",
                "_call": {"call_id": rec.call_id, "openclaw_cost_usd": 0.01}}
    return ask


def _packet(t):
    return None if t.startswith("UNP") else {"ticker": t, "asof": "x"}


def _run(env, **kw):
    kw.setdefault("sources", {"murat_book": ["AAA", "UNP1"], "llm_books": ["BBB"],
                              "funnel": ["AAA", "CCC"], "top_revisions": []})
    kw.setdefault("packet_fn", _packet)
    return N.daily_forecast(today=datetime.now(timezone.utc).date().isoformat(),
                            ledger_path=env["ledger"],
                            telemetry_path=None, receipt_dir=env["receipts"], **kw)


def _ledger(env):
    if not env["ledger"].exists():
        return []
    return [json.loads(l) for l in env["ledger"].read_text(encoding="utf-8").splitlines()]


def test_writes_h1_and_h5_rows_for_every_priced_name(env):
    res = _run(env, ask_fn=_stub_ask(), cap_usd=5.0)
    assert res["state"] == "DONE"
    rows = _ledger(env)
    assert sorted({r["ticker"] for r in rows}) == ["AAA", "BBB", "CCC"]
    assert sorted({r["horizon_days"] for r in rows}) == [1, 5]
    assert all(r["specialist"] == N.SPECIALIST_DAILY for r in rows)
    # direction rows go RAW (adjudication 2026-09-26 row 2): no magnitude shrink
    p = {r["horizon_days"]: r["probability"] for r in rows if r["ticker"] == "AAA"}
    assert p[1] == pytest.approx(0.60) and p[5] == pytest.approx(0.40)
    assert res["n_unpriced"] == 1                 # UNP1 reported, not skipped
    rc = json.loads(next(env["receipts"].glob("day_*.json")).read_text(encoding="utf-8"))
    assert rc["unpriced"] == ["UNP1"]
    assert rc["retired_weight_zero"] and "geopolitical" in rc["retired_weight_zero"]


def test_rows_are_written_only_once_per_day(env):
    calls: list[str] = []
    _run(env, ask_fn=_stub_ask(calls=calls), cap_usd=5.0)
    n1 = len(_ledger(env))
    res2 = _run(env, ask_fn=_stub_ask(calls=calls), cap_usd=5.0)
    assert "skipped" in res2
    assert len(_ledger(env)) == n1
    assert len(calls) == 3


def test_refuses_over_the_cap_read_from_the_ledger(env):
    # one call costs ~$0.0077 at the house price; a cap of $0.01 admits two
    calls: list[str] = []
    res = _run(env, ask_fn=_stub_ask(calls=calls), cap_usd=0.01)
    assert res["state"] == "REFUSED_CAP"
    assert len(calls) == 2
    assert "cap" in res["why"]


def test_a_cap_whose_ledger_does_not_move_refuses(env):
    """The writer spent and the ledger the cap reads did not move: 09-21."""
    def ask(pk):
        return {"probability_1d": 0.5, "probability_5d": 0.5,
                "_call": {"call_id": "not-in-the-ledger", "openclaw_cost_usd": 0.01}}
    res = _run(env, ask_fn=ask, cap_usd=5.0)
    assert res["state"] == "REFUSED_CAP"
    assert "did not move" in res["why"]


def test_an_unreadable_spend_ledger_refuses(env):
    for f in env["tele"].parent.glob("llm_calls*"):
        f.unlink()
    res = _run(env, ask_fn=_stub_ask(), cap_usd=5.0,
               sources={"murat_book": ["AAA"]})
    # first call: the ledger does not exist yet -> spend UNKNOWN -> refuse
    assert res["state"] == "REFUSED_CAP"
    assert "UNKNOWN" in res["why"]
    assert _ledger(env) == []


def test_zero_rows_is_degraded(env):
    res = _run(env, ask_fn=_stub_ask(), cap_usd=5.0,
               sources={"murat_book": ["UNP1", "UNP2"]})
    assert res["state"] == "DEGRADED"
    assert "zero forecast rows" in res["why"]


def test_universe_priority_and_truncation():
    u = N.forecast_universe(sources={"murat_book": ["A", "B"], "llm_books": ["B", "C"],
                                     "funnel": ["D"], "top_revisions": ["E"]},
                            max_names=4)
    assert u["tickers"] == ["A", "B", "C", "D"]
    assert u["cut"] == ["E"]
    assert u["source_of"]["B"] == "murat_book"


def test_the_smoke_reply_shape_parses():
    txt = ('{"ticker": "CRWD", "probability_1d": 0.52, "probability_5d": 0.54, '
           '"facts_used": ["beta_63 2.14"], "falsifier": "f", '
           '"confidence_in_the_evidence": "medium", "what_is_missing": []}')
    r = N.parse_reply(txt, keys=("probability_1d", "probability_5d"))
    assert r["probability_1d"] == 0.52 and r["probability_5d"] == 0.54
    broken = '{"probability_1d": 0.52, "probability_5d": 0.47, "facts_used": ["a "b" c"]}'
    d = N.parse_reply(broken, keys=("probability_1d", "probability_5d"))
    assert d["parse"] == "degraded" and d["probability_5d"] == 0.47


# ── the sim wiring ───────────────────────────────────────────────────────────

def test_forecast_and_review_run_after_rank_and_before_plan():
    import inspect
    from scripts import sim_run as SR
    src = inspect.getsource(SR.run)
    i = {k: src.index(f'c.unit("{k}"') for k in ("rank", "forecast", "review", "plan")}
    assert i["rank"] < i["forecast"] < i["review"] < i["plan"]


def test_u_forecast_skips_on_todays_receipt_without_a_subprocess(monkeypatch, tmp_path):
    from scripts import sim_run as SR
    monkeypatch.setattr(SR._config, "OPTIMUS_LEDGER_DIR", tmp_path)
    day = datetime.now(timezone.utc).date().isoformat()
    (tmp_path / "forecasts").mkdir()
    (tmp_path / "forecasts" / f"day_{day}.json").write_text(
        json.dumps({"state": "DONE", "n_rows_written": 80}), encoding="utf-8")
    monkeypatch.setattr(SR, "_in_subprocess",
                        lambda *a, **k: pytest.fail("must not run twice a day"))
    r = SR.u_forecast(tmp_path)
    assert "skipped" in r and r["status"] == "ok"


def test_u_forecast_zero_rows_is_degraded(monkeypatch, tmp_path):
    from scripts import sim_run as SR
    monkeypatch.setattr(SR._config, "OPTIMUS_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(SR, "_in_subprocess",
                        lambda *a, **k: {"state": "DEGRADED", "n_rows_written": 0})
    assert SR.u_forecast(tmp_path)["status"] == "DEGRADED"


def test_u_review_waits_for_0800_et_and_skips_weekends(monkeypatch, tmp_path):
    from zoneinfo import ZoneInfo
    from scripts import sim_run as SR
    from backend.services import daily_review as DR
    monkeypatch.setattr(DR, "REVIEW_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(SR, "_in_subprocess",
                        lambda pick, **k: calls.append((pick, k)) or {"n_rows": 3})
    et = ZoneInfo("America/New_York")
    # derive a weekday and a Saturday from today, never a literal date
    base = datetime.now(et).replace(hour=7, minute=59, second=0, microsecond=0)
    from datetime import timedelta
    wk = base + timedelta(days=(0 - base.weekday()) % 7)          # a Monday
    assert "before" in SR.u_review(tmp_path, now_et=wk)["skipped"]
    sat = wk + timedelta(days=5)
    assert "weekend" in SR.u_review(tmp_path, now_et=sat.replace(hour=9))["skipped"]
    r = SR.u_review(tmp_path, now_et=wk.replace(hour=8, minute=5))
    assert r["morning"] is True
    assert calls and calls[0][0] == "review"
    assert json.loads(calls[0][1]["args"][0])["asof"] == wk.date().isoformat()


def test_u_forecast_timeout_counts_as_an_attempt(monkeypatch, tmp_path):
    import subprocess
    from scripts import sim_run as SR
    monkeypatch.setattr(SR._config, "OPTIMUS_LEDGER_DIR", tmp_path)

    def hang(*a, **k):
        raise subprocess.TimeoutExpired("python", 7200)
    monkeypatch.setattr(SR, "_in_subprocess", hang)
    for _ in range(SR.DAILY_UNIT_MAX_ATTEMPTS):
        assert SR.u_forecast(tmp_path)["status"] == "DEGRADED"
    monkeypatch.setattr(SR, "_in_subprocess",
                        lambda *a, **k: pytest.fail("attempts exhausted"))
    r = SR.u_forecast(tmp_path)
    assert "failed attempts" in r["skipped"] and r["status"] == "DEGRADED"


# ───── the direction shrink (adjudication 2026-09-26 row 2) ─────

def test_a_direction_row_is_written_raw_with_its_basis(env):
    _run(env, ask_fn=_stub_ask(), cap_usd=5.0)
    rows = _ledger(env)
    assert rows
    for r in rows:
        assert r["observable"] == "beats_benchmark"
        assert r["raw_probability"] == pytest.approx(r["probability"])
        assert r["shrink_basis"] == "none: direction skill unmeasured"
        assert r["shrink_basis"] == N.SHRINK_BASIS_DIRECTION


def test_magnitude_keeps_the_shrink_and_direction_does_not():
    from backend.services import belief_state as B
    p, basis = N.recalibrate(0.60, B.Observable.ABS_MOVE_EXCEEDS)
    assert p == pytest.approx(0.50 + N.SHRINK * 0.10)
    assert basis == "§64 magnitude held-out"
    for obs in (B.Observable.BEATS_BENCHMARK, B.Observable.RETURN_SIGN):
        p, basis = N.recalibrate(0.60, obs)
        assert p == pytest.approx(0.60) and basis == N.SHRINK_BASIS_DIRECTION
