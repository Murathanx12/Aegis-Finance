"""REVISION-FORECASTER-1 — the three ways this trial could have lied to itself.

Pre-registration: `Aegis module/TRIALS/PREREG_REVISION_FORECASTER_1.md` @ d81577e.
Verdict: STOP. These tests exist because the verdict is only worth the
instrument, and this instrument was wrong once in a way that produced a t of
4.04.

  1. THE LOOK-AHEAD. `t1` — the post-event IBES cut the revision is measured at
     — sits a median of 20 CALENDAR DAYS after the event. The first version of
     the precondition scored the revision against returns measured from the
     EVENT, so `t1` fell inside both the 5- and the 21-session window: the
     revision was "predicting" a return that had already happened when it was
     observed. That version reported IC +0.0454 (t 3.56) and, for the
     surprise-orthogonal residual, +0.0504 (t 4.04). Measured from `t1`, both
     collapse to +0.0028 and +0.0108, under MDE80. A t of 4.0 is exactly the
     number nobody goes back to re-examine.

  2. THE FISCAL ROLL. IBES rolls the FY1 pointer, so `meanest_t1 - meanest_t0`
     across a roll compares an FY2013 estimate to an FY2014 one. That is not a
     revision; it is a large number correlated with the calendar, and the
     calendar is correlated with returns.

  3. THE TRANSCRIBED ARITHMETIC. The 21-session forward return is computed in
     this trial rather than by mutating `event_response_v1`'s frozen SPEC. A
     transcription that drifted would void every number, so it is asserted
     against the original rather than trusted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import revision_forecaster_v1 as rf


# ── 3. the transcription ────────────────────────────────────────────────────


def _panel(n_days=40, permnos=(1, 2, 3), seed=11):
    rng = np.random.default_rng(seed)
    rows = []
    dates = pd.bdate_range("2015-01-01", periods=n_days)
    for p in permnos:
        for d in dates:
            rows.append({"permno": p, "date": d,
                         "ret": float(rng.normal(0, 0.02)),
                         "prc": 50.0})
    return pd.DataFrame(rows)


def test_the_forward_return_math_matches_event_response_v1_exactly():
    """If this drifts, every number in the trial is void."""
    from scripts import event_response_v1 as v1

    d = _panel()
    mine = rf.excess_forward_math(d, [1, 2, 5])

    # v1's arithmetic, inlined from `forward_returns` after its file reading.
    x = d.copy()
    x["date"] = pd.to_datetime(x["date"])
    x["ret"] = pd.to_numeric(x["ret"], errors="coerce")
    x = x.dropna(subset=["ret"]).sort_values(["permno", "date"])
    mkt = x.groupby("date")["ret"].mean().rename("mkt")
    x = x.merge(mkt, left_on="date", right_index=True, how="left")
    x["ex"] = x["ret"] - x["mkt"]
    for k in v1.SPEC["horizons_sessions"]:
        inc = (x.groupby("permno")["ex"]
               .transform(lambda s, k=k: s[::-1].rolling(k, min_periods=k)
                          .sum()[::-1]))
        x[f"fwd{k}"] = inc.groupby(x["permno"]).shift(-1)

    for k in v1.SPEC["horizons_sessions"]:
        a = mine[f"fwd{k}"].to_numpy()
        b = x[f"fwd{k}"].to_numpy()
        both = np.isfinite(a) & np.isfinite(b)
        assert both.sum() > 10
        assert np.allclose(a[both], b[both], atol=1e-12), f"fwd{k} drifted"


def test_the_forward_window_starts_STRICTLY_after_the_session():
    """Including the event session would make |gap| contribute positively to a
    sign(gap)-scaled target by construction — a continuation finding that is
    pure arithmetic. v1 shipped that bug once."""
    d = _panel(n_days=10, permnos=(1, 2))
    out = rf.excess_forward_math(d, [1])
    g = out[out["permno"] == 1].sort_values("date").reset_index(drop=True)
    # fwd1 at row i must equal the excess return at row i+1, never row i.
    assert g["fwd1"].iloc[0] == pytest.approx(g["ex"].iloc[1], abs=1e-12)
    assert g["fwd1"].iloc[0] != pytest.approx(g["ex"].iloc[0], abs=1e-12)


# ── 2. the fiscal roll ──────────────────────────────────────────────────────


def _events(dates, permno=1):
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(len(dates))],
        "permno": [permno] * len(dates),
        "event_date": pd.to_datetime(dates)})


def _cons(rows, permno=1):
    return pd.DataFrame([
        {"permno": permno, "statpers": pd.Timestamp(sp), "meanest": me,
         "stdev": 0.1, "numest": 10.0, "numup": 3.0, "numdown": 1.0,
         "fpedats": pd.Timestamp(fpe)}
        for sp, me, fpe in rows])


def test_a_FISCAL_ROLL_between_the_two_cuts_is_dropped():
    """The most efficient way to manufacture a target out of nothing."""
    ev = _events(["2015-02-10"])
    cons = _cons([
        ("2015-01-15", 2.00, "2015-12-31"),   # t0, FY2015
        ("2015-02-19", 3.50, "2016-12-31"),   # t1, but FY2016 — a ROLL
    ])
    out = rf.attach_revision(ev, cons)
    assert out.empty, "a period roll must not be read as a +1.50 revision"


def test_the_same_fiscal_period_across_both_cuts_is_kept():
    ev = _events(["2015-02-10"])
    cons = _cons([
        ("2015-01-15", 2.00, "2015-12-31"),
        ("2015-02-19", 2.10, "2015-12-31"),
    ])
    out = rf.attach_revision(ev, cons)
    assert len(out) == 1
    assert out["meanest_t1"].iloc[0] - out["meanest_t0"].iloc[0] == pytest.approx(0.10)


# ── 1. the timing of t1 ─────────────────────────────────────────────────────


def test_t1_must_be_at_least_5_days_after_the_event():
    """A cut taken the day after the print has not digested it."""
    ev = _events(["2015-02-17"])
    cons = _cons([
        ("2015-01-15", 2.00, "2015-12-31"),
        ("2015-02-18", 2.30, "2015-12-31"),   # only 1 day after — too early
        ("2015-03-19", 2.40, "2015-12-31"),   # 30 days after — this one
    ])
    out = rf.attach_revision(ev, cons)
    assert len(out) == 1
    assert out["t1"].iloc[0] == pd.Timestamp("2015-03-19")
    assert out["meanest_t1"].iloc[0] == pytest.approx(2.40)


def test_a_t1_beyond_45_days_is_dropped_rather_than_reached_for():
    """A name that loses coverage must drop out, not borrow a stale cut."""
    ev = _events(["2015-02-10"])
    cons = _cons([
        ("2015-01-15", 2.00, "2015-12-31"),
        ("2015-06-18", 2.90, "2015-12-31"),   # 128 days later
    ])
    assert rf.attach_revision(ev, cons).empty


def test_t0_is_STRICTLY_before_the_event():
    """A cut published on the event date may already contain the print."""
    ev = _events(["2015-02-19"])
    cons = _cons([
        ("2015-01-15", 2.00, "2015-12-31"),
        ("2015-02-19", 2.50, "2015-12-31"),   # same day as the event
        ("2015-03-19", 2.60, "2015-12-31"),
    ])
    out = rf.attach_revision(ev, cons)
    assert len(out) == 1
    assert out["t0"].iloc[0] == pd.Timestamp("2015-01-15")


def test_the_frozen_block_matches_the_pre_registration():
    """The pre-registration is the authority; this dict is a restatement, and a
    restatement that drifts is worse than no restatement."""
    assert rf.FROZEN["fpi"] == "1"
    assert rf.FROZEN["primary_horizon_sessions"] == 21
    assert rf.FROZEN["t1_min_days_after_event"] == 5
    assert rf.FROZEN["t1_max_days_after_event"] == 45
    assert rf.FROZEN["first_test_year"] == 2012
    assert rf.FROZEN["fpedats_must_match"] is True
    assert rf.FROZEN["declared_effect_size"] == 0.025
