"""Owner rebound forecast grader (CH-45): never a verdict before its date. Synthetic only."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts import owner_rebound_forecast as F

REF = pd.Timestamp("2024-03-01")
DUE = pd.Timestamp("2024-04-01")
AFTER = list(pd.bdate_range(REF + pd.Timedelta(days=1), periods=21))
RATIO = {"a": 1.10, "b": 1.02}
BETA = {"a": 2.0, "b": 2.0}


def test_not_due_before_the_grade_date_even_with_enough_sessions():
    g = F.grade(sessions_after=AFTER, book_ratio=RATIO, beta=BETA, spy_ret=0.03, horizon=21,
                grade_date=DUE, asof=DUE - pd.Timedelta(days=1))
    assert g["status"] == "NOT_DUE" and "vs_spy" not in g
    assert g["ew_book_return"] == pytest.approx(0.06) and g["excess_vs_spy"] == pytest.approx(0.03)


def test_not_due_with_too_few_sessions():
    g = F.grade(sessions_after=AFTER[:5], book_ratio=RATIO, beta=BETA, spy_ret=0.03, horizon=21,
                grade_date=DUE, asof=DUE)
    assert g["status"] == "NOT_DUE"


def test_graded_two_ways_when_due_and_spy_up():
    g = F.grade(sessions_after=AFTER, book_ratio=RATIO, beta=BETA, spy_ret=0.03, horizon=21,
                grade_date=DUE, asof=DUE)
    assert g["status"] == "GRADED" and g["vs_spy"] == "BEAT"
    assert g["excess_vs_beta_spy"] == pytest.approx(0.0)          # 0.06 - 2 x 0.03, up to float noise
    hi = F.grade(sessions_after=AFTER, book_ratio=RATIO, beta={"a": 2.5, "b": 2.5}, spy_ret=0.03,
                 horizon=21, grade_date=DUE, asof=DUE)
    assert hi["vs_spy"] == "BEAT" and hi["excess_vs_beta_spy"] == pytest.approx(-0.015)
    assert hi["vs_beta_spy"] == "DID_NOT_BEAT"                   # beat SPY, not beta x SPY


def test_condition_not_met_when_spy_down():
    g = F.grade(sessions_after=AFTER, book_ratio=RATIO, beta=BETA, spy_ret=-0.01, horizon=21,
                grade_date=DUE, asof=DUE)
    assert g["status"] == "CONDITION_NOT_MET" and "vs_spy" not in g


def test_book_nav_holds_frozen_weights_and_unpriced_weight_as_cash():
    idx = pd.bdate_range("2024-01-02", periods=3)
    close = pd.DataFrame({"X": [10.0, 11.0, 12.0], "SPY": [1.0, 1.0, 1.0]}, index=idx)
    nav, cov = F.book_nav({"X": 0.5, "MISSING": 0.3}, close, idx[0])
    assert cov == pytest.approx(0.5 / 0.8)
    assert list(nav.round(6)) == [1.0, 1.05, 1.1]
