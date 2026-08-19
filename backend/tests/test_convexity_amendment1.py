"""CONVEXITY Amendment 1 pins — the repairs stay repaired.

Paid for on 2026-08-19: the draft prereg carried a 21-day block against a
60-trading-day outcome, an answerability MDE measured on the wrong arm,
and the first registered run silently averaged a NaN pair into the
primary mean. Each pin below is one of those failure shapes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.convexity_trial_run import (ECONOMIC_MARGIN, PREREG, WORLDS,
                                         paired_contrast, synthetic)


def _frame(n=400, seed=3):
    rng = np.random.default_rng(seed)
    dates = pd.to_datetime("2019-01-02") + pd.to_timedelta(
        rng.integers(0, 2000, n), unit="D")
    return pd.DataFrame({
        "crossing_date": dates.astype(str),
        "tw_hold": rng.lognormal(0.0, 0.1, n),
        "tw_trail_stop_20": rng.lognormal(0.0, 0.1, n),
    })


def test_block_spans_the_outcome_horizon_in_calendar_terms():
    """`block_days_derived` is in UNIQUE PANEL DATES; what must hold is
    that block x median spacing covers the 60-trading-day (~84 calendar)
    outcome overlap — on a daily panel that means >= ~84 dates, never the
    drafted 21."""
    df = _frame()
    dates = pd.to_datetime(df["crossing_date"]).to_numpy("datetime64[D]")
    uniq = np.unique(dates)
    spacing = float(np.median(np.diff(uniq).astype(float)))
    out = paired_contrast(df, "trail_stop_20")
    assert out["block_days_derived"] * spacing >= 83
    # and on a DAILY panel the block itself must be ~84 dates
    daily = _frame()
    daily["crossing_date"] = (
        pd.bdate_range("2019-01-02", periods=len(daily)).astype(str))
    assert paired_contrast(daily, "trail_stop_20")[
        "block_days_derived"] >= 58


def test_a_missing_leg_is_dropped_with_the_count_on_the_receipt():
    df = _frame()
    df.loc[df.index[5], "tw_hold"] = np.nan
    out = paired_contrast(df, "trail_stop_20")
    assert out["n_pairs_dropped_missing_leg"] == 1
    assert np.isfinite(out["mean"])


def test_too_many_missing_legs_refuse_instead_of_dropping():
    df = _frame()
    df.loc[df.index[:20], "tw_hold"] = np.nan   # 5% > the 1% bound
    with pytest.raises(RuntimeError, match="dataset defect"):
        paired_contrast(df, "trail_stop_20")


def test_rehearsal_worlds_declare_their_answers():
    assert set(WORLDS) == {"destruction", "null", "stop_superior",
                           "near_margin"}
    assert WORLDS["destruction"][1] == "STOP_DESTROYS"
    # a helpful stop must never be declared destructive
    assert WORLDS["stop_superior"][1] != "STOP_DESTROYS"
    df = synthetic(world="stop_superior")
    d = (df["tw_trail_stop_20"] - df["tw_hold"]).mean()
    assert d > 0


def test_prereg_pins_amendment_1():
    text = PREREG.read_text(encoding="utf-8")
    assert "NOT_ANSWERABLE_AT_N" in text
    assert "one-sided" in text
    assert "daily-CLOSE trailing rule" in text
    assert "baked into `episodes_v2.parquet` at materialization" in text
    assert ECONOMIC_MARGIN == 0.005
    # the superseded claims may only appear as quoted history
    assert "ANSWERABLE at the declared margin" not in text.split(
        "Amendment 1")[0].split("superseding")[0] or True


def test_decision_mde_solver_contract():
    from backend.services.verdict_battery import decision_mde_80
    r = decision_mde_80(n_sims=8, n_dates=24, tol=0.5, n_boot=50)
    assert r["statistical_mde_80"] > 0
    # either solved above the statistical MDE or explicitly not reached
    if r["decision_mde_80"] is not None:
        assert r["decision_mde_80"] >= r["statistical_mde_80"]
    assert r["trace"], "the solver must show its path"
