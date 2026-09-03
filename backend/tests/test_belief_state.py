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


def test_a_forecast_maturing_TODAY_is_due_not_overdue(tmp_path):
    """"Due today" is the resolver's WORK, not its failure.

    `ledger_health` counted a record overdue on `today >= resolves_after`, the
    same predicate `resolve_due` uses to decide what to grade. But the resolver
    is a 16:30 ET cron and the canary is a clock: from 00:00 UTC until 20:30
    UTC, every record maturing that day read as "past due and unresolved" and
    the whole deploy read DEGRADED — about 20.5 hours out of every 24 on which
    anything matures.

    That is what happened on 2026-09-03. The 15 "past due" forecasts were the
    15 whose `resolves_after` was that very date; the resolver's own receipt
    from 2026-09-02T23:32Z reported `n_overdue_actionable: 0` over the SAME
    237-record file, and every receipt in the ledger's history reports 0. The
    resolver had never once failed to grade an actionable record — it simply
    had not had its slot yet.

    A canary that is red most of the day is alarm fatigue with extra steps;
    this file already made that argument, verbatim, for the quarantine split on
    2026-08-17. So the fault predicate is STRICT: a record is overdue once a
    whole day has passed since it matured, by which point the 16:30 slot and
    all three catch-up retries have fired. `resolve_due` keeps `>=` — the
    resolver should still grade on the maturity day.

    This cannot mask a real stall for more than one day: the 2026-08-27→09-01
    gap, where 42 forecasts genuinely went ungraded for days, still degrades.
    """
    from backend.services.belief_state import ledger_health
    p = tmp_path / "today.jsonl"
    today = date.today()
    # horizon_days=1 makes resolves_after land on/near today; pin the clock
    # rather than the calendar so this cannot rot (CLAUDE.md session rule 5).
    append([_pred(made_at=datetime.now(timezone.utc).isoformat(),
                  horizon_days=1)], p)
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l]
    matures = date.fromisoformat(rows[0]["resolves_after"][:10])

    on_maturity_day = ledger_health(p, today=matures)
    assert on_maturity_day["n_overdue"] == 0, (
        "a forecast maturing today is due, not overdue — the resolver's slot "
        "has not come yet")
    assert on_maturity_day["status"] == "ok"

    the_day_after = ledger_health(p, today=matures + timedelta(days=1))
    assert the_day_after["n_overdue"] == 1, (
        "once a full day has passed the resolver has had its slot and its "
        "retries; still-unresolved is now a genuine fault")
    assert the_day_after["status"] == "DEGRADED"


def test_actionable_overdue_records_are_NAMED_not_just_counted(tmp_path):
    """The row named the QUARANTINED ids and left the actionable ones as a bare
    count — backwards, because the actionable ones are the only ones anybody
    can act on. Diagnosing the 2026-09-03 episode meant deriving which records
    were meant by arithmetic across two receipts, because no read-only surface
    would say."""
    from backend.services.belief_state import ledger_health
    p = tmp_path / "named.jsonl"
    append([_pred(made_at="2025-02-03T00:00:00")], p)
    out = ledger_health(p)
    assert out["n_overdue_actionable"] == 1
    assert out["overdue_actionable"], "the overdue records were not named"
    first = out["overdue_actionable"][0]
    assert first["prediction_id"] and first["ticker"] == "AAA"
    assert first["resolves_after"]


def test_the_live_ledger_canary_RUNS_and_returns_a_complete_report():
    """This asserted `status == "ok"` on the LIVE ledger until 2026-08-16, and
    it was a time bomb pointed at the deploy gate.

    WHAT WOULD HAVE HAPPENED, measured before it fired
    ==================================================
    The campaign ledger's first forecasts fall due on 2026-08-16. Evaluated as
    of successive dates against the real file:

        2026-08-15   status ok        0 overdue
        2026-08-16   status DEGRADED  110 overdue
        2026-08-17   status DEGRADED  201 overdue

    CI runs in UTC and was still green at 17:14 UTC on 08-15. It would have
    turned red the moment UTC crossed midnight — on no commit, from no code
    change — and **Railway gates deploys on CI**, so production would have
    frozen. Worse than this morning's version (§44, §47): clearing it needs an
    ATTENDED, irreversible resolution run, so the pipeline would have stayed
    blocked until a human woke up, and any unrelated fix would have been stuck
    behind someone else's chores.

    The canary itself is right. DEGRADED is the correct reading of "110
    forecasts are past due", and `/api/health/full` should say so loudly. What
    was wrong is asserting it in a suite that gates shipping.

    So this test now checks what a test can check — that the canary RUNS
    against the real ledger and returns a complete, well-formed report — and
    the detection behaviour it used to imply is already covered by
    `test_a_forecast_past_its_resolution_date_degrades_the_canary` on a
    constructed fixture, where it belongs.

    Third instance this week of the same defect: **a test that asserts the
    state of the world rather than the behaviour of the code.** The CI world
    (§0), the calendar's world (§44), the clock's world (§47), and now the
    operational backlog's.
    """
    from backend.services.belief_state import ledger_health
    out = ledger_health()

    # The report must be complete, whatever it says.
    for key in ("status", "n_records", "n_overdue", "n_void", "last_written",
                "distinct_specialists", "persistence"):
        assert key in out, f"the canary's report is missing {key}: {out}"
    assert out["status"] in ("ok", "DEGRADED")
    assert out["distinct_specialists"] >= 5
    assert out["n_records"] > 0
    # A DEGRADED live ledger is operational information, not a build failure.
    # It must still NAME its problem rather than degrading silently.
    if out["status"] == "DEGRADED":
        assert out.get("problems"), (
            "the canary degraded without naming a reason, which is the one "
            "thing it must never do")
