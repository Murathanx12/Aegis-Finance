"""
TRIAL-PEAD-IC — offline tests for the PEAD score + collector.

Invariants: signal exists only within the post-announcement window (stale →
honest 0); two-way alignment detected; missing components degrade to explicit
statuses; the collector snapshots into the PIT store under pead_score:*.
"""

import numpy as np
import pandas as pd
import pytest

from backend.services import pead_signal as ps


def _earnings_df(ann="2026-06-25", surprise=8.0, reported=1.25):
    idx = pd.to_datetime([ann, "2026-09-25"])  # one reported, one scheduled
    return pd.DataFrame(
        {"EPS Estimate": [1.10, 1.30], "Reported EPS": [reported, np.nan],
         "Surprise(%)": [surprise, np.nan]}, index=idx)


def _prices(jump_on="2026-06-25", jump=0.12, start="2026-04-01", periods=90):
    idx = pd.bdate_range(start, periods=periods)
    px = pd.Series(100.0, index=idx).cumsum() * 0 + 100.0
    px = pd.Series(100.0 * np.ones(periods), index=idx)
    j = idx.searchsorted(pd.Timestamp(jump_on))
    px.iloc[j:] = 100.0 * (1 + jump)
    return px


def _flat_spy(start="2026-04-01", periods=90):
    return pd.Series(100.0, index=pd.bdate_range(start, periods=periods))


class TestScore:
    def test_aligned_positive_surprise_and_pop(self):
        inputs = {"earnings_dates": _earnings_df(surprise=8.0),
                  "prices": _prices(jump=0.12), "spy": _flat_spy()}
        out = ps.compute_pead_score(inputs, as_of="2026-07-09")
        assert out["status"] == "ok"
        assert out["pead_score"] > 0.5
        assert out["two_way_aligned"] is True
        assert out["n_components"] == 2

    def test_misaligned_components_dampen(self):
        # positive surprise but the stock DROPPED vs SPY on the announcement
        inputs = {"earnings_dates": _earnings_df(surprise=8.0),
                  "prices": _prices(jump=-0.12), "spy": _flat_spy()}
        out = ps.compute_pead_score(inputs, as_of="2026-07-09")
        assert out["status"] == "ok"
        assert out["two_way_aligned"] is False
        assert abs(out["pead_score"]) < 0.5

    def test_stale_earnings_is_honest_zero(self):
        inputs = {"earnings_dates": _earnings_df(ann="2026-01-15"),
                  "prices": _prices(), "spy": _flat_spy()}
        out = ps.compute_pead_score(inputs, as_of="2026-07-09")
        assert out["status"] == "stale_earnings"
        assert out["pead_score"] == 0.0

    def test_no_reported_earnings(self):
        out = ps.compute_pead_score({"earnings_dates": None,
                                     "prices": _prices(), "spy": _flat_spy()},
                                    as_of="2026-07-09")
        assert out["status"] == "no_reported_earnings"
        assert out["pead_score"] == 0.0

    def test_surprise_only_when_prices_missing(self):
        inputs = {"earnings_dates": _earnings_df(surprise=-6.0),
                  "prices": pd.Series(dtype=float), "spy": pd.Series(dtype=float)}
        out = ps.compute_pead_score(inputs, as_of="2026-07-09")
        assert out["status"] == "ok"
        assert out["n_components"] == 1
        assert out["pead_score"] < 0

    def test_components_clip_to_unit(self):
        inputs = {"earnings_dates": _earnings_df(surprise=250.0),
                  "prices": _prices(jump=0.9), "spy": _flat_spy()}
        out = ps.compute_pead_score(inputs, as_of="2026-07-09")
        assert out["pead_score"] == pytest.approx(1.0)

    def test_scheduled_future_row_ignored(self):
        # only the scheduled (NaN-reported) row exists before as_of → no signal
        df = _earnings_df()
        df = df.iloc[[1]]  # future row only
        out = ps.compute_pead_score({"earnings_dates": df, "prices": _prices(),
                                     "spy": _flat_spy()}, as_of="2026-07-09")
        assert out["status"] == "no_reported_earnings"


class TestCollector:
    def test_snapshots_into_pit(self, tmp_path):
        from backend.db import get_connection, init_db
        from backend.services.portfolio_intelligence.pead_collector import (
            collect_pead_scores,
        )
        db = tmp_path / "pead.db"
        init_db(db)
        stub = {"earnings_dates": _earnings_df(surprise=8.0),
                "prices": _prices(jump=0.12), "spy": _flat_spy()}
        out = collect_pead_scores(db_path=db, tickers=["AAPL", "NVDA"],
                                  fetch=lambda t: stub, as_of="2026-07-09")
        assert out["status"] == "collected"
        assert out["n"] == 2 and out["nonzero"] == 2
        conn = get_connection(db)
        try:
            rows = conn.execute(
                "SELECT key, value FROM pit_observations WHERE key LIKE 'pead_score:%'"
            ).fetchall()
        finally:
            conn.close()
        assert {r["key"] for r in rows} == {"pead_score:AAPL", "pead_score:NVDA"}
        assert all(r["value"] > 0.5 for r in rows)

    def test_throttled_second_run(self, tmp_path):
        from backend.db import init_db
        from backend.services.portfolio_intelligence.pead_collector import (
            collect_pead_scores,
        )
        db = tmp_path / "pead.db"
        init_db(db)
        stub = {"earnings_dates": _earnings_df(), "prices": _prices(),
                "spy": _flat_spy()}
        collect_pead_scores(db_path=db, tickers=["AAPL"], fetch=lambda t: stub,
                            as_of="2026-07-09")
        out = collect_pead_scores(db_path=db, tickers=["AAPL"],
                                  fetch=lambda t: stub, as_of="2026-07-11")
        assert out["status"] == "throttled"
