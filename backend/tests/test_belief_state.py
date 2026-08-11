"""The prediction ledger — the guards that keep a score honest.

A calibration record is only worth what its refusals are worth. Every test here
blocks a way of writing something into the ledger that would later be scored as
if it meant what it says.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from backend.services.belief_state import (HORIZONS, BeliefState, Observable,
                                           PredictionRecord, ScenarioLeg,
                                           append, calibration,
                                           make_prediction, read_predictions,
                                           resolve_all, resolve_one)
from backend.services.optimus_specialists import (CONTRACT, SPECIALISTS,
                                                  effective_distinct_ideas)


def _pred(**kw):
    base = dict(ticker="AAA", specialist="biotech",
                observable=Observable.RETURN_SIGN, horizon_days=20,
                probability=0.6, thesis="t", counter_thesis="c",
                next_observable="n", model="m", model_version="v",
                prompt="p", input_snapshot={"ticker": "AAA"})
    base.update(kw)
    return make_prediction(**base)


# ── what may not be written ─────────────────────────────────────────────────
def test_a_percent_threshold_is_refused_rather_than_coerced():
    """THE defect of the first live run. '|move| > 20.0' is a 2000% move, so at
    p=0.75 it is a guaranteed-wrong record — and it would have been charged to a
    specialist whose judgment had nothing to do with the unit error. All six
    occurrences came from ONE specialist, so the damage was systematic."""
    with pytest.raises(ValueError, match="decimal fraction"):
        _pred(observable=Observable.ABS_MOVE_EXCEEDS, threshold=20.0)
    ok = _pred(observable=Observable.ABS_MOVE_EXCEEDS, threshold=0.20)
    assert ok.threshold == 0.20


def test_a_threshold_observable_without_a_threshold_is_refused():
    with pytest.raises(ValueError, match="positive threshold"):
        _pred(observable=Observable.DRAWDOWN_EXCEEDS, threshold=None)


def test_an_unfrozen_horizon_is_refused():
    """A horizon chosen per-prediction is a free parameter, and free parameters
    are how a forecaster becomes right in retrospect."""
    with pytest.raises(ValueError, match="not one of"):
        _pred(horizon_days=47)
    for h in HORIZONS:
        assert _pred(horizon_days=h).horizon_days == h


def test_a_probability_outside_zero_to_one_is_refused():
    with pytest.raises(ValueError, match="not a probability"):
        _pred(probability=1.4)


def test_beats_benchmark_without_a_benchmark_is_refused():
    with pytest.raises(ValueError, match="needs a benchmark"):
        _pred(observable=Observable.BEATS_BENCHMARK, benchmark=None)


# ── the record identifies the world it saw ──────────────────────────────────
def test_the_same_inputs_hash_the_same_and_different_ones_do_not():
    a = _pred(made_at="2026-01-01T00:00:00", input_snapshot={"px": 1})
    b = _pred(made_at="2026-01-01T00:00:00", input_snapshot={"px": 1})
    c = _pred(made_at="2026-01-01T00:00:00", input_snapshot={"px": 2})
    assert a.prediction_id == b.prediction_id
    assert a.input_snapshot_hash != c.input_snapshot_hash


def test_the_resolution_date_is_never_before_the_window_closes():
    """Grading early is indistinguishable from being right early."""
    for h in HORIZONS:
        p = _pred(horizon_days=h, made_at="2026-01-01T00:00:00")
        gap = (date.fromisoformat(p.resolves_after)
               - date.fromisoformat("2026-01-01")).days
        assert gap >= h, f"h={h} would be graded on a partial window"


# ── resolution ──────────────────────────────────────────────────────────────
def _prices(n=400, drift=0.002):
    idx = pd.bdate_range("2025-01-01", periods=n)
    rng = np.random.default_rng(0)
    up = 100 * np.cumprod(1 + drift + rng.normal(0, 0.005, n))
    return pd.DataFrame({"AAA": up, "SPY": np.linspace(100, 110, n)}, index=idx)


def test_a_record_whose_window_has_not_closed_is_not_graded():
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(timespec="seconds")
    rec = json.loads(json.dumps(_pred(made_at=future).__dict__, default=str))
    assert resolve_one(rec, _prices()) is None


def test_a_resolved_record_carries_its_brier_and_its_evidence():
    rec = json.loads(json.dumps(
        _pred(made_at="2025-02-03T00:00:00", probability=0.9).__dict__, default=str))
    out = resolve_one(rec, _prices())
    assert out is not None and out["outcome"] == 1
    assert out["brier"] == pytest.approx(0.01)
    assert "realised_return" in out["resolution_detail"]


def test_a_voided_record_is_never_scored():
    """It stays in the ledger as evidence the forecast was made, and out of
    every score. Deleting it hides a defect; grading it charges a forecaster for
    one."""
    rec = json.loads(json.dumps(_pred(made_at="2025-02-03T00:00:00").__dict__,
                                default=str))
    rec["void_reason"] = "threshold in percent"
    assert resolve_one(rec, _prices()) is None


def test_calibration_reports_nothing_before_anything_resolves(tmp_path):
    p = tmp_path / "empty.jsonl"
    out = calibration(p)
    assert out["n_resolved"] == 0
    assert "clock started" in out["reading"]


def test_calibration_compares_against_climatology(tmp_path):
    """'The forecast was informative' has exactly one meaning here: it beat the
    base rate. A Brier score with no climatology beside it says nothing."""
    p = tmp_path / "led.jsonl"
    recs = [_pred(ticker="AAA", made_at=f"2025-02-0{i+1}T00:00:00",
                  probability=0.9) for i in range(6)]
    append(recs, p)
    resolve_all(_prices(), p)
    out = calibration(p)
    assert out["n_resolved"] == 6
    g = out["groups"]["biotech"]
    assert "climatology_brier" in g and "overconfidence" in g


def test_the_ledger_refuses_to_write_the_same_record_twice(tmp_path):
    p = tmp_path / "led.jsonl"
    r = _pred(made_at="2026-01-01T00:00:00")
    append([r], p)
    append([r], p)
    assert len(read_predictions(p)) == 1


# ── the firewall and the batch check ────────────────────────────────────────
def test_every_specialist_is_bound_by_the_no_sizing_contract():
    for name, sys_prompt in SPECIALISTS.items():
        assert sys_prompt.strip()
    assert "never state a position size" in CONTRACT
    assert "DECIMAL FRACTIONS" in CONTRACT


def test_a_batch_of_identical_forecasts_has_an_effective_size_of_one():
    """CANON §20. NIGHT-10 found ten 'independent' LLM hypotheses that were one
    connected component; averaging them manufactures confidence."""
    same = [_pred(ticker="AAA", probability=0.6) for _ in range(8)]
    eff = effective_distinct_ideas(same)
    assert eff["effective_distinct_ideas"] == 1
    assert eff["n_forecasts"] == 8


def test_genuinely_different_forecasts_are_counted_separately():
    varied = [_pred(ticker=f"T{i}", probability=0.3 + 0.05 * i) for i in range(8)]
    eff = effective_distinct_ideas(varied)
    assert eff["effective_distinct_ideas"] == 8


# ── the belief state ────────────────────────────────────────────────────────
def test_an_incoherent_probability_tree_yields_no_expected_value():
    """An EV computed from branches that do not sum to one is worse than no EV:
    it looks like a valuation and is arithmetic on an error."""
    b = BeliefState(ticker="AAA", as_of="2026-08-11", scenarios=[
        ScenarioLeg("win", 0.5, 100.0), ScenarioLeg("lose", 0.2, 10.0)])
    assert b.expected_value() is None


def test_a_coherent_probability_tree_prices_the_branches():
    b = BeliefState(ticker="AAA", as_of="2026-08-11", scenarios=[
        ScenarioLeg("win", 0.3, 100.0), ScenarioLeg("lose", 0.7, 10.0)])
    assert b.expected_value() == pytest.approx(37.0)


def test_the_live_ledger_has_records_and_none_of_them_are_scoreable_yet():
    """The clock started tonight. Nothing has resolved, and that is the point."""
    rows = read_predictions()
    assert len(rows) >= 60, "the first live run should be on disk"
    assert all(r.get("outcome") is None for r in rows)
    voided = [r for r in rows if r.get("void_reason")]
    assert all(not (0 < (r["threshold"] or 0.5) < 1) for r in voided)


# ── the canary: would anything say so if this went dark? ────────────────────
def test_an_empty_ledger_reads_as_degraded_not_as_healthy(tmp_path):
    """A prediction ledger fails by NOT growing, and an empty append looks
    identical to a night with nothing to say. Silence must not read as ok."""
    from backend.services.belief_state import ledger_health
    out = ledger_health(tmp_path / "nothing.jsonl")
    assert out["status"] == "DEGRADED"
    assert out["n"] == 0


def test_a_forecast_past_its_resolution_date_degrades_the_canary(tmp_path):
    """An overdue record means the resolver cannot see its security. Counting it
    as 'pending' hides a permanently dark forecast behind a growing backlog."""
    from backend.services.belief_state import ledger_health
    p = tmp_path / "led.jsonl"
    append([_pred(made_at="2025-02-03T00:00:00")], p)
    out = ledger_health(p)
    assert out["status"] == "DEGRADED"
    assert out["n_overdue"] == 1


def test_the_live_ledger_canary_is_healthy():
    from backend.services.belief_state import ledger_health
    out = ledger_health()
    assert out["status"] == "ok", out
    assert out["distinct_specialists"] >= 5
