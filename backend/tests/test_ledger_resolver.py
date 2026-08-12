"""The resolver entry point — the caller resolve_all never had.

belief_state.py shipped a complete resolution machine and NOTHING called it:
no scheduler job, no route, no script. These tests pin the three properties
that make that impossible to repeat silently: the job is REGISTERED, a due
record actually RESOLVES through the entry point, and a record that cannot be
priced is COUNTED AND NAMED rather than skipped.

All offline: the price fetch is injected, `today` is injected (no freezegun),
and the only file I/O is tmp_path ledgers plus the read-only frozen CSV.
"""

from __future__ import annotations

import asyncio
from datetime import date

import numpy as np
import pandas as pd

from backend.services.belief_state import (Observable, append, ledger_health,
                                           make_prediction, read_predictions)
from backend.services.ledger_calibration import calibration_report
from backend.services.ledger_resolver import resolve_due


# ── helpers (same shapes as test_belief_state.py) ───────────────────────────
def _pred(**kw):
    base = dict(ticker="AAA", specialist="biotech",
                observable=Observable.RETURN_SIGN, horizon_days=20,
                probability=0.6, thesis="t", counter_thesis="c",
                next_observable="n", model="m", model_version="v",
                prompt="p", input_snapshot={"ticker": "AAA"})
    base.update(kw)
    return make_prediction(**base)


def _prices(n=400, drift=0.002):
    idx = pd.bdate_range("2025-01-01", periods=n)
    rng = np.random.default_rng(0)
    up = 100 * np.cumprod(1 + drift + rng.normal(0, 0.005, n))
    return pd.DataFrame({"AAA": up, "SPY": np.linspace(100, 110, n)}, index=idx)


# ── (a) the test that would have caught the current state ───────────────────
def test_the_resolver_job_is_registered_when_the_scheduler_builds():
    """resolve_one/resolve_all existed for a month with no caller. The only
    durable guard is that building the job set without pi_ledger_resolve is a
    test failure, not a code review observation."""
    from backend.services.portfolio_intelligence.scheduler import (
        setup_scheduler, shutdown_scheduler,
    )

    async def _run():
        scheduler = setup_scheduler()
        assert scheduler is not None
        job_ids = {j.id for j in scheduler.get_jobs()}
        assert "pi_ledger_resolve" in job_ids, (
            "the prediction-ledger resolver is not scheduled — records will "
            "sail past resolves_after forever and no calibration will accrue")
        shutdown_scheduler()

    asyncio.run(_run())


# ── (b) a due record resolves through the entry point ───────────────────────
def test_a_backdated_due_record_is_newly_resolved(tmp_path):
    p = tmp_path / "led.jsonl"
    append([_pred(made_at="2025-02-03T00:00:00")], p)

    fetched = []

    def fetch(tickers, start, end):
        fetched.append(list(tickers))
        return _prices()

    rep = resolve_due(p, price_fetch=fetch, today=date(2025, 6, 2))
    assert rep["newly_resolved"] == 1
    assert rep["due"] == 1
    assert rep["overdue"] == 0
    assert rep["unpriceable"] == []
    assert fetched == [["AAA"]]
    # and the resolution was written back into the ledger, not just reported
    rows = read_predictions(p)
    assert rows[0]["outcome"] is not None and rows[0]["brier"] is not None


# ── (c) unpriceable is a named finding, never a silent skip ─────────────────
def test_an_unpriceable_due_record_is_counted_and_stays_degraded(tmp_path):
    p = tmp_path / "led.jsonl"
    append([_pred(ticker="ZZZDARK", made_at="2025-02-03T00:00:00",
                  input_snapshot={"ticker": "ZZZDARK"})], p)

    rep = resolve_due(p, price_fetch=lambda t, s, e: _prices(),
                      today=date(2025, 6, 2))
    assert rep["newly_resolved"] == 0
    assert rep["overdue"] == 1, "an unpriceable due record must stay overdue"
    assert [u["ticker"] for u in rep["unpriceable"]] == ["ZZZDARK"]
    u = rep["unpriceable"][0]
    assert u["n_due_records_stranded"] == 1 and u["prediction_ids"]
    assert rep["health"]["status"] == "DEGRADED"
    assert rep["health"]["n_overdue"] == 1
    # the record itself is untouched — not resolved, not voided, not dropped
    rows = read_predictions(p)
    assert len(rows) == 1 and rows[0]["outcome"] is None
    assert rows[0].get("void_reason") is None


def test_a_missing_benchmark_column_strands_the_record_loudly(tmp_path):
    p = tmp_path / "led.jsonl"
    append([_pred(observable=Observable.BEATS_BENCHMARK, benchmark="QQQ",
                  made_at="2025-02-03T00:00:00")], p)
    rep = resolve_due(p, price_fetch=lambda t, s, e: _prices(),  # no QQQ
                      today=date(2025, 6, 2))
    assert rep["newly_resolved"] == 0 and rep["overdue"] == 1
    assert "QQQ" in [u["ticker"] for u in rep["unpriceable"]]


# ── (d) the calibration cross-tab is honest about sparse and pending ────────
def test_calibration_report_prints_n_everywhere_and_never_scores_pending(tmp_path):
    p = tmp_path / "led.jsonl"
    resolved_rec = _pred(made_at="2025-02-03T00:00:00", probability=0.9)
    pending_rec = _pred(ticker="BBB", specialist="skeptic", horizon_days=120,
                        made_at="2025-02-03T00:00:00",
                        input_snapshot={"ticker": "BBB"})
    append([resolved_rec, pending_rec], p)
    rep = resolve_due(p, price_fetch=lambda t, s, e: _prices(),
                      today=date(2025, 6, 2))
    assert rep["newly_resolved"] == 1 and rep["pending"] == 1

    out = calibration_report(p, today=date(2025, 6, 2))
    assert out["n_resolved"] == 1 and out["n_pending"] == 1
    for cell in list(out["cells"].values()) + list(out["by_specialist"].values()):
        assert "n" in cell and "n_resolved" in cell, "every cell prints its n"

    scored = out["cells"]["biotech|return_sign|20"]
    assert scored["n_resolved"] == 1
    assert scored["brier"] is not None
    assert scored["climatology_brier"] is not None

    sparse = out["cells"]["skeptic|return_sign|120"]
    assert sparse["n"] == 1 and sparse["n_pending"] == 1
    assert sparse["n_resolved"] == 0
    # pending is counted, never scored — and never smoothed into a number
    for k in ("brier", "climatology_brier", "beats_climatology",
              "base_rate", "mean_probability", "overconfidence"):
        assert sparse[k] is None, f"{k} must be None on an all-pending cell"


def test_calibration_report_keeps_void_records_out_of_every_cell(tmp_path):
    import json
    p = tmp_path / "led.jsonl"
    append([_pred(made_at="2025-02-03T00:00:00")], p)
    rows = read_predictions(p)
    rows[0]["void_reason"] = "unit test: pre-existing void"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = calibration_report(p, today=date(2025, 6, 2))
    assert out["n_void"] == 1
    assert out["cells"] == {}, "a void record belongs in no cell"


# ── (e) injectable today, no freezegun ──────────────────────────────────────
def test_injectable_today_flips_due_and_skips_the_fetch_until_needed(tmp_path):
    p = tmp_path / "led.jsonl"
    append([_pred(made_at="2026-08-11T00:00:00")], p)  # resolves after 2026-09-12

    fetched = []

    def fetch(tickers, start, end):
        fetched.append(1)
        return _prices(600)  # bdays 2025-01-01 → well past the window

    early = resolve_due(p, price_fetch=fetch, today=date(2026, 9, 1))
    assert early["due"] == 0 and early["newly_resolved"] == 0
    assert early["pending"] == 1 and early["overdue"] == 0
    assert not fetched, "nothing due — no price fetch should be burned"

    late = resolve_due(p, price_fetch=fetch, today=date(2026, 10, 1))
    assert late["due"] == 1 and late["newly_resolved"] == 1
    assert fetched, "a due record must trigger the price panel"


def test_ledger_health_accepts_an_injected_today(tmp_path):
    p = tmp_path / "led.jsonl"
    append([_pred(made_at="2026-08-11T00:00:00")], p)
    ok = ledger_health(p, today=date(2026, 8, 12))
    assert ok["status"] == "ok"
    bad = ledger_health(p, today=date(2026, 12, 1))
    assert bad["status"] == "DEGRADED" and bad["n_overdue"] == 1


# ── the fetch is chunked, because LLM-SWARM-1 changed the scale ─────────────

def test_the_price_fetch_is_chunked_so_one_bad_symbol_cannot_strand_the_ledger(
        monkeypatch):
    """One 460-symbol request fails as a unit; chunks fail proportionally.

    Before LLM-SWARM-1 the ledger held ~100 records over a dozen names and a
    single request was right. The swarm put hundreds of securities in it in one
    night, at which point a single timeout would mark EVERY due record
    unpriceable and page on a problem that is not in the ledger.
    """
    import pandas as pd

    from backend.services import ledger_resolver as lr

    seen: list[list[str]] = []
    idx = pd.bdate_range("2026-08-01", periods=5)

    class _FakeYF:
        @staticmethod
        def download(tickers, start, end, auto_adjust, progress, timeout):
            chunk = list(tickers)
            seen.append(chunk)
            if "BAD" in chunk:
                raise RuntimeError("read timed out")
            return {"Close": pd.DataFrame(
                {t: [1.0] * len(idx) for t in chunk}, index=idx)}

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYF)
    names = [f"T{i}" for i in range(7)] + ["BAD"] + [f"U{i}" for i in range(4)]
    panel = lr._default_price_fetch(names, "2026-08-01", "2026-08-08", batch=4)

    assert [len(c) for c in seen] == [4, 4, 4]
    # The bad chunk's names are simply absent — the contract this callable
    # already declares — and every other chunk survived it.
    assert "BAD" not in panel.columns
    assert "T0" in panel.columns and "U3" in panel.columns
    assert len(panel.columns) == 8


def test_a_fetch_where_every_chunk_fails_returns_empty_not_a_crash(monkeypatch):
    from backend.services import ledger_resolver as lr

    class _DeadYF:
        @staticmethod
        def download(*a, **k):
            raise RuntimeError("network down")

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _DeadYF)
    out = lr._default_price_fetch(["A", "B"], "2026-08-01", "2026-08-08")
    assert out.empty
