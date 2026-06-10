"""
Grind A1: silent degradation must be loud (and isolated per ticker).

Two confirmed bug classes:
  - real_analyzer beta loop: one ticker's decomposition failure used to abort
    every remaining ticker silently → concentration flags computed on a
    partial beta_map presented as complete.
  - replay universe fetch: a ticker dropped by a fetch failure shrank the
    replay universe with no log line.
"""

import logging
from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.services.portfolio_intelligence.real_analyzer import _compute_beta_map


def _price_frame(tickers):
    idx = pd.date_range("2025-01-01", periods=300, freq="B")
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {t: 100 + np.cumsum(rng.normal(0, 1, len(idx))) for t in tickers},
        index=idx,
    )


class TestBetaMapIsolation:
    def test_one_failure_does_not_abort_remaining_tickers(self, caplog):
        prices = _price_frame(["GOOD", "BAD", "ALSO_GOOD"])

        def fake_decompose(ticker, price_series=None):
            if ticker == "BAD":
                raise RuntimeError("boom")
            return {"factors": {"Mkt-RF": {"loading": 1.23}}}

        with patch(
            "backend.services.factor_model.decompose_stock",
            side_effect=fake_decompose,
        ):
            with caplog.at_level(logging.WARNING):
                beta_map = _compute_beta_map(
                    ["GOOD", "BAD", "ALSO_GOOD"], prices, {"Mkt-RF": 1.0},
                )

        assert beta_map == {"GOOD": 1.23, "ALSO_GOOD": 1.23}, (
            "tickers after the failing one must still be decomposed"
        )
        assert any("BAD" in r.message for r in caplog.records), (
            "the dropped ticker must be logged, not swallowed"
        )

    def test_no_market_factor_returns_empty(self):
        prices = _price_frame(["A"])
        assert _compute_beta_map(["A"], prices, {"Mkt-RF": None}) == {}


class TestReplayUniverseDropsAreLogged:
    def test_failed_ticker_logged_and_others_kept(self, caplog):
        from backend.services.portfolio_intelligence.replay import ReplayEngine

        idx = pd.date_range("2025-01-01", periods=50, freq="B")
        good_series = pd.Series(np.linspace(100, 110, len(idx)), index=idx)

        calls = {"n": 0}

        def fake_fetch(ticker, start, end, name=None):
            calls["n"] += 1
            if calls["n"] == 1:  # first ticker in the universe fails
                raise RuntimeError("network down")
            return good_series

        engine = ReplayEngine.__new__(ReplayEngine)  # skip __init__ deps
        with patch("backend.services.data_fetcher.fetch_safe",
                   side_effect=fake_fetch):
            with caplog.at_level(logging.WARNING):
                df = engine._get_ticker_universe_prices(
                    None, {}, date(2025, 1, 1), date(2025, 3, 1),
                )

        assert not df.empty, "remaining tickers must survive one failure"
        assert any("dropping" in r.message.lower() for r in caplog.records), (
            "the dropped ticker must be logged"
        )
