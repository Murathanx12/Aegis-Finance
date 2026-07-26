"""2026-07-26 screener outage, phase 2 — regression tests.

Prod yfinance emitted a NaN final Close row for every ticker; analyze_stock
took `float(prices.iloc[-1])` raw, so current_price / momentum_1m /
momentum_3m were NaN across the board (the signal-engine sanitizer named
those exact fields in prod logs). Rows then 500'd the whole endpoint at
JSON serialization. Pins: (1) the analyzer prices off real closes only;
(2) the screener payload is always JSON-compliant.
"""

import math
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.routers.stock import _json_sanitize


def _hist_with_nan_tail(n=400, nan_tail=2):
    idx = pd.bdate_range(end="2026-07-24", periods=n)
    rng = np.random.default_rng(11)
    close = 100.0 * np.exp(np.cumsum(0.0004 + 0.012 * rng.standard_normal(n)))
    close[-nan_tail:] = np.nan
    return pd.DataFrame({
        "Close": close,
        "Open": close, "High": close, "Low": close,
        "Volume": np.full(n, 1e6),
    }, index=idx)


FAKE_INFO = {"marketCap": 5e10, "beta": 1.1, "shortName": "FakeCo",
             "sector": "Technology", "trailingPE": 22.0,
             "targetMeanPrice": None}


class TestAnalyzerNaNTail:
    def test_current_price_from_last_real_close(self):
        hist = _hist_with_nan_tail()
        last_real = float(hist["Close"].dropna().iloc[-1])
        with patch("backend.services.data_fetcher.fetch_ticker_history",
                   return_value=hist), \
             patch("backend.services.data_fetcher.fetch_ticker_info",
                   return_value=dict(FAKE_INFO)):
            from backend.services.stock_analyzer import analyze_stock
            r = analyze_stock("FAKE")
        assert r is not None
        assert r["current_price"] == last_real
        assert math.isfinite(r["current_price"])
        for k in ("momentum_1m", "momentum_3m", "volatility"):
            assert r[k] is None or math.isfinite(r[k]), f"{k} not finite: {r[k]}"

    def test_all_nan_history_returns_none_loudly(self):
        hist = _hist_with_nan_tail(n=400, nan_tail=400)
        with patch("backend.services.data_fetcher.fetch_ticker_history",
                   return_value=hist), \
             patch("backend.services.data_fetcher.fetch_ticker_info",
                   return_value=dict(FAKE_INFO)):
            from backend.services.stock_analyzer import analyze_stock
            assert analyze_stock("FAKE") is None


class TestJsonSanitize:
    def test_nan_and_inf_become_none_everywhere(self):
        payload = {
            "a": float("nan"),
            "b": [1.0, float("inf"), {"c": float("-inf"), "d": "ok"}],
            "e": {"f": (float("nan"), 2)},
            "g": 3,
        }
        clean = _json_sanitize(payload)
        assert clean["a"] is None
        assert clean["b"][1] is None
        assert clean["b"][2]["c"] is None
        assert clean["b"][2]["d"] == "ok"
        assert clean["e"]["f"] == [None, 2]
        assert clean["g"] == 3

    def test_valid_floats_untouched(self):
        assert _json_sanitize({"x": 1.5, "y": 0.0}) == {"x": 1.5, "y": 0.0}
