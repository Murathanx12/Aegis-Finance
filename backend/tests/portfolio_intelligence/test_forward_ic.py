"""Tests for the forward-IC scorecard (reads PIT signals back, grades them).

Offline: the price-history fetcher is injected, so no network."""

import numpy as np
import pandas as pd
import pytest

from backend.db import get_connection, init_db, snapshot
from backend.services.portfolio_intelligence.forward_ic import (
    build_signal_panel,
    forward_ic_scorecard,
    score_forward_ic,
)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test_fic.db"
    init_db(path)
    return path


@pytest.fixture
def conn(db_path):
    c = get_connection(db_path)
    yield c
    c.close()


def _rising_prices(start="2026-01-01", n=400, slope=0.001):
    idx = pd.bdate_range(start=start, periods=n)
    return pd.Series(100.0 * np.exp(slope * np.arange(n)), index=idx)


class TestScoreForwardIC:
    def test_insufficient_history_reported(self):
        out = score_forward_ic(pd.DataFrame(columns=["date", "asset", "factor", "fwd_return"]))
        assert out["status"] == "insufficient_history"
        assert out["data_grade"] == "directional"  # yfinance default

    def test_all_nan_forward_returns_insufficient(self):
        # A panel that looks big but whose factor/fwd are all NaN must report
        # insufficient_history, NOT status="scored" with an empty IC.
        rows = [{"date": d, "asset": f"A{a}", "factor": float(a),
                 "fwd_return": float("nan")}
                for d in ["2026-01-05", "2026-01-12", "2026-01-20", "2026-01-27"]
                for a in range(6)]
        out = score_forward_ic(pd.DataFrame(rows))
        assert out["status"] == "insufficient_history"

    def test_predictive_factor_scores_usable(self):
        # Noisy-but-predictive factor across 12 dates x 10 assets: IC varies
        # date-to-date (non-zero std -> real t-stat), mean IC strongly positive.
        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2026-01-01", periods=12)
        rows = []
        for d in dates:
            factors = rng.normal(size=10)
            fwd = factors * 0.02 + rng.normal(scale=0.01, size=10)
            for a in range(10):
                rows.append({"date": str(d.date()), "asset": f"A{a}",
                             "factor": float(factors[a]), "fwd_return": float(fwd[a])})
        out = score_forward_ic(pd.DataFrame(rows))
        assert out["status"] == "scored"
        assert out["ic"]["mean_ic"] > 0.3
        assert out["ic"]["t_stat"] > 2.0
        assert out["ic"]["verdict"] in ("weak but significant", "usable signal")
        assert out["data_grade"] == "directional"

    def test_grade_follows_source(self):
        dates = pd.bdate_range("2026-01-01", periods=5)
        rows = [{"date": str(d.date()), "asset": f"A{a}", "factor": float(a),
                 "fwd_return": 0.01 * a} for d in dates for a in range(8)]
        out = score_forward_ic(pd.DataFrame(rows), source="sharadar")
        assert out["data_grade"] == "sizing"


class TestBuildSignalPanel:
    def test_panel_joins_pit_scores_with_forward_returns(self, conn):
        tickers = [f"T{i}" for i in range(6)]
        as_ofs = ["2026-01-05", "2026-01-12", "2026-01-20"]
        # Seed PIT: score == ticker index (a clean cross-sectional factor).
        for i, t in enumerate(tickers):
            for d in as_ofs:
                snapshot(conn, f"mf:{t}", d, float(i), source="test",
                         observed_at=f"{d}T00:00:00+00:00")

        prices = {t: _rising_prices() for t in tickers}
        panel = build_signal_panel(
            conn, "mf:", tickers,
            price_history=lambda t: prices[t], horizon_days=21,
        )
        assert not panel.empty
        assert set(panel.columns) == {"date", "asset", "factor", "fwd_return"}
        # 6 tickers x 3 dates = 18 rows (all have forward room in a 400-day series)
        assert len(panel) == 18
        assert panel["fwd_return"].notna().all()

    def test_leak_free_uses_observed_value(self, conn):
        # A later revision observed AFTER the cutoff must not leak in.
        snapshot(conn, "mf:X", "2026-01-05", 1.0, source="test",
                 observed_at="2026-01-05T00:00:00+00:00")
        snapshot(conn, "mf:X", "2026-01-05", 999.0, source="test",
                 observed_at="2026-02-01T00:00:00+00:00")  # revised later
        prices = {"X": _rising_prices()}
        panel = build_signal_panel(
            conn, "mf:", ["X"], price_history=lambda t: prices[t],
            as_of_ts="2026-01-10T00:00:00+00:00",  # before the revision
        )
        assert (panel["factor"] == 1.0).all()  # not 999.0

    def test_missing_prices_skipped(self, conn):
        snapshot(conn, "mf:Y", "2026-01-05", 1.0, source="test",
                 observed_at="2026-01-05T00:00:00+00:00")
        panel = build_signal_panel(conn, "mf:", ["Y"], price_history=lambda t: None)
        assert panel.empty


class TestScorecardEndToEnd:
    def test_scorecard_runs_and_stamps_grade(self, conn):
        tickers = [f"S{i}" for i in range(8)]
        as_ofs = ["2026-01-05", "2026-01-12", "2026-01-20", "2026-01-27"]
        for i, t in enumerate(tickers):
            for d in as_ofs:
                snapshot(conn, f"mf:{t}", d, float(i), source="test",
                         observed_at=f"{d}T00:00:00+00:00")
        prices = {t: _rising_prices() for t in tickers}
        out = forward_ic_scorecard(
            conn, "mf:", tickers, price_history=lambda t: prices[t], horizon_days=21,
        )
        assert out["status"] == "scored"
        assert out["key_prefix"] == "mf:"
        assert out["horizon_days"] == 21
        assert out["data_grade"] == "directional"
        assert out["n_tickers"] == 8
