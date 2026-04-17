"""Tests for market_treemap — sector/ticker heatmap assembly."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from backend.services import market_treemap as tm


def _fake_history(tickers):
    idx = pd.date_range("2024-01-01", periods=260, freq="B")
    rng = np.random.default_rng(0)
    data = {}
    for i, t in enumerate(tickers):
        # Slightly different trajectories so each ticker has a unique return
        drift = 0.0003 * (i + 1)
        returns = rng.normal(drift, 0.012, size=len(idx))
        prices = 100.0 * np.exp(np.cumsum(returns))
        data[t] = prices
    return pd.DataFrame(data, index=idx)


def test_compute_return_windows():
    idx = pd.date_range("2024-01-02", periods=260, freq="B")
    series = pd.Series(np.linspace(100, 200, num=260), index=idx)
    assert tm._compute_return(series, "1d") is not None
    assert tm._compute_return(series, "1w") is not None
    assert tm._compute_return(series, "1m") is not None
    assert tm._compute_return(series, "ytd") is not None


def test_compute_return_rejects_bad_window():
    series = pd.Series([100.0, 101.0], index=pd.date_range("2024-01-01", periods=2))
    assert tm._compute_return(series, "bogus") is None


def test_compute_return_empty_series():
    assert tm._compute_return(pd.Series(dtype=float), "1d") is None


def test_build_treemap_invalid_window_raises():
    with pytest.raises(ValueError):
        tm.build_treemap(window="99y")


def test_build_treemap_end_to_end_with_mocks():
    # Limit universe so the test is fast and deterministic
    sample = {
        "Technology": ["AAPL", "MSFT"],
        "Healthcare": ["JNJ", "PFE"],
    }
    tickers = sorted({t for lst in sample.values() for t in lst})
    history = _fake_history(tickers)

    def fake_cap(t):
        return {"AAPL": 3e12, "MSFT": 2.8e12, "JNJ": 4e11, "PFE": 2e11}.get(t)

    with patch.object(tm, "SECTOR_STOCKS", sample), \
         patch.object(tm, "_download_history", return_value=history), \
         patch.object(tm, "_fetch_market_cap", side_effect=fake_cap), \
         patch.object(tm, "cache_get", return_value=None), \
         patch.object(tm, "cache_set"):
        result = tm.build_treemap(window="1m")

    assert result["window"] == "1m"
    # Both sectors should appear
    names = {c["name"] for c in result["children"]}
    assert names == {"Technology", "Healthcare"}
    assert result["ticker_count"] == 4
    assert result["total_market_cap"] > 0
    # Tickers within each sector must be sorted by market cap descending
    tech = next(c for c in result["children"] if c["name"] == "Technology")
    mcs = [child["market_cap"] for child in tech["children"]]
    assert mcs == sorted(mcs, reverse=True)


def test_build_treemap_empty_history_returns_error_shape():
    with patch.object(tm, "_download_history", return_value=None), \
         patch.object(tm, "cache_get", return_value=None), \
         patch.object(tm, "cache_set"):
        result = tm.build_treemap(window="1d")
    assert result["children"] == []
    assert "error" in result
