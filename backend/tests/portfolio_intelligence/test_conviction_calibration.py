"""
Conviction calibration scorecard — offline tests.

Invariants: buy calls graded on forward return, sell calls on the INVERSE
(return avoided); unmatured horizons pending, never guessed; sparse buckets
reported sparse; empty log and failed price fetch are explicit statuses.
"""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from backend.db import get_connection, init_db, insert_personal_decision
from backend.services.portfolio_intelligence import conviction_calibration as cc


def _prices(start="2026-01-02", periods=300, daily=0.001, start_px=100.0):
    idx = pd.bdate_range(start, periods=periods)
    return pd.Series(start_px * np.cumprod([1 + daily] * periods), index=idx)


def _decision(id_, ticker, action, conviction, ts):
    return {"id": id_, "ticker": ticker, "action": action,
            "conviction": conviction, "timestamp": ts}


class TestGrading:
    def test_buy_call_graded_on_forward_return(self):
        px = _prices(daily=0.002)  # rising
        g = cc.grade_decisions(
            [_decision(1, "AAPL", "enter", 4, "2026-01-05T10:00:00")],
            {"AAPL": px})
        h21 = g[0].horizons[21]
        assert h21["matured"] is True
        assert h21["fwd_return"] > 0
        assert h21["call_return"] == h21["fwd_return"]  # buy: right when up

    def test_sell_call_graded_inverse(self):
        px = _prices(daily=-0.002)  # falling
        g = cc.grade_decisions(
            [_decision(1, "SOC", "exit", 5, "2026-01-05T10:00:00")],
            {"SOC": px})
        h21 = g[0].horizons[21]
        assert h21["fwd_return"] < 0
        assert h21["call_return"] > 0  # selling before a fall was RIGHT

    def test_unmatured_horizon_pending(self):
        px = _prices(periods=40)  # only ~40 trading days of data
        g = cc.grade_decisions(
            [_decision(1, "AAPL", "enter", 3, "2026-01-05T10:00:00")],
            {"AAPL": px})
        assert g[0].horizons[21]["matured"] is True
        assert g[0].horizons[126]["matured"] is False
        assert g[0].horizons[126]["call_return"] is None

    def test_missing_prices_pending_not_zero(self):
        g = cc.grade_decisions(
            [_decision(1, "GONE", "enter", 3, "2026-01-05T10:00:00")], {})
        assert all(v["call_return"] is None and not v["matured"]
                   for v in g[0].horizons.values())


class TestReliabilityCurve:
    def test_groups_by_conviction_with_honest_counts(self):
        up, down = _prices(daily=0.002), _prices(daily=-0.002)
        g = cc.grade_decisions(
            [_decision(1, "A", "enter", 5, "2026-01-05T09:00:00"),
             _decision(2, "B", "enter", 5, "2026-01-05T09:00:00"),
             _decision(3, "C", "enter", 2, "2026-01-05T09:00:00")],
            {"A": up, "B": up, "C": down})
        curve = cc.reliability_curve(g)
        assert curve["5"]["21"]["n"] == 2
        assert curve["5"]["21"]["hit_rate"] == 1.0
        assert curve["2"]["21"]["n"] == 1
        assert curve["2"]["21"]["hit_rate"] == 0.0
        assert curve["3"]["21"]["n"] == 0
        assert curve["3"]["21"]["mean_call_return"] is None  # sparse stays sparse


class TestScorecard:
    def _db_with_decision(self, tmp_path, ts):
        p = tmp_path / "cal.db"
        init_db(p)
        conn = get_connection(p)
        try:
            insert_personal_decision(
                conn, timestamp=ts, ticker="AAPL", action="enter",
                shares_delta=5.0, price=100.0,
                rationale="x" * 60, thesis_tags=[], conviction=4,
                portfolio_snapshot={},
            )
        finally:
            conn.close()
        return p

    def test_empty_log(self, tmp_path):
        p = tmp_path / "empty.db"
        init_db(p)
        out = cc.calibration_scorecard(db_path=p)
        assert out["status"] == "no_decisions"

    def test_scorecard_end_to_end_with_injected_prices(self, tmp_path):
        db = self._db_with_decision(tmp_path, "2026-01-05T10:00:00")
        out = cc.calibration_scorecard(
            db_path=db,
            price_fetch=lambda tickers, start: {"AAPL": _prices(daily=0.002)})
        assert out["status"] == "ok"
        assert out["n_decisions"] == 1
        assert out["reliability_curve"]["4"]["21"]["n"] == 1
        assert "never a training signal" in out["label"]

    def test_fresh_decision_reports_no_matured(self, tmp_path):
        today = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        db = self._db_with_decision(tmp_path, today)
        short = pd.Series([100.0], index=pd.bdate_range(today[:10], periods=1))
        out = cc.calibration_scorecard(
            db_path=db, price_fetch=lambda t, s: {"AAPL": short})
        assert out["status"] == "no_matured_horizons"

    def test_price_fetch_failure_is_explicit(self, tmp_path):
        db = self._db_with_decision(tmp_path, "2026-01-05T10:00:00")
        def _boom(t, s):
            raise RuntimeError("network down")
        out = cc.calibration_scorecard(db_path=db, price_fetch=_boom)
        assert out["status"] == "prices_unavailable"
