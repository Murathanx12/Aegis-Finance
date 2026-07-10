"""
Per-position portfolio guidance — offline tests.

Invariants: the trailing stop is the frozen exit_engine config (no per-user
tuning); nudges name behavioral patterns without order language; per-holding
failures degrade only that holding; PIT signal reads are optional context;
numpy-laden inputs serialize (the explain-move lesson).
"""

import json

import numpy as np
import pandas as pd
import pytest

from backend.services import portfolio_guidance as pg


def _trending_up(periods=250, daily=0.003, start_px=10.0):
    idx = pd.bdate_range("2025-07-01", periods=periods)
    return pd.Series(start_px * np.cumprod([1 + daily] * periods), index=idx)


def _peaked_and_rolled(periods=250, start_px=10.0):
    """Rises strongly then falls hard for 15 days — below any 3x-ATR stop."""
    rng = np.random.default_rng(3)
    up = list(rng.normal(0.004, 0.004, periods - 15))
    down = [-0.05] * 15
    idx = pd.bdate_range("2025-07-01", periods=periods)
    return pd.Series(start_px * np.cumprod([1 + r for r in up + down]), index=idx)


class TestStopLevel:
    def test_uptrend_not_breached(self):
        out = pg.chandelier_stop_level(_trending_up())
        assert out is not None
        assert out["breached"] is False
        assert out["distance_pct"] > 0

    def test_rollover_breaches(self):
        out = pg.chandelier_stop_level(_peaked_and_rolled())
        assert out["breached"] is True

    def test_short_history_returns_none(self):
        assert pg.chandelier_stop_level(_trending_up(periods=10)) is None


class TestNudges:
    def test_winner_rolling_over_nudge(self):
        close = _peaked_and_rolled()
        out = pg.position_guidance("SOC", 100, cost_basis=5.0, close=close)
        types = [n["type"] for n in out["nudges"]]
        assert "winner_rolling_over" in types
        assert out["unrealized_pnl_pct"] > 0

    def test_loser_past_stop_is_disposition_nudge(self):
        close = _peaked_and_rolled()
        high_basis = float(close.iloc[-1]) * 2  # bought near the top
        out = pg.position_guidance("SOC", 100, cost_basis=high_basis, close=close)
        types = [n["type"] for n in out["nudges"]]
        assert "loser_past_stop" in types
        assert any("disposition" in n["message"].lower() for n in out["nudges"])

    def test_quiet_winner_has_no_stop_nudge(self):
        out = pg.position_guidance("AAPL", 10, cost_basis=5.0,
                                   close=_trending_up())
        assert all(n["type"] != "winner_rolling_over" for n in out["nudges"])

    def test_no_order_language(self):
        out = pg.position_guidance("SOC", 100, cost_basis=5.0,
                                   close=_peaked_and_rolled())
        for n in out["nudges"]:
            low = n["message"].lower()
            for phrase in ("should sell", "sell now", "should buy", "buy now",
                           "recommend selling", "recommend buying"):
                assert phrase not in low


class TestPortfolioAssembly:
    def test_per_holding_failure_degrades_only_itself(self, tmp_path):
        def fetch(t):
            if t == "GONE":
                raise RuntimeError("delisted")
            return _trending_up()
        from backend.db import init_db
        db = tmp_path / "g.db"
        init_db(db)
        out = pg.portfolio_guidance(
            [{"ticker": "AAPL", "shares": 10, "cost_basis": 100},
             {"ticker": "GONE", "shares": 5}],
            db_path=db, price_fetch=fetch)
        assert out["n_positions"] == 2
        by = {p["ticker"]: p for p in out["positions"]}
        assert by["GONE"]["status"] == "unavailable"
        assert by["AAPL"].get("status") != "unavailable"
        assert "not financial advice" in out["disclaimer"]

    def test_pit_signals_attached_when_present(self, tmp_path):
        from backend.db import get_connection, init_db, snapshot
        db = tmp_path / "g.db"
        init_db(db)
        conn = get_connection(db)
        try:
            snapshot(conn, "pead_score:AAPL", "2026-07-08", 0.7,
                     source="yfinance", payload={"status": "ok"})
        finally:
            conn.close()
        out = pg.portfolio_guidance([{"ticker": "AAPL", "shares": 1}],
                                    db_path=db,
                                    price_fetch=lambda t: _trending_up())
        sig = out["positions"][0]["signals"]
        assert sig["pead_score"]["value"] == 0.7

    def test_result_is_json_serializable(self, tmp_path):
        from backend.db import init_db
        db = tmp_path / "g.db"
        init_db(db)
        out = pg.portfolio_guidance([{"ticker": "AAPL", "shares": 1}],
                                    db_path=db,
                                    price_fetch=lambda t: _trending_up())
        json.dumps(out)  # numpy leakage would raise (the explain-move lesson)
