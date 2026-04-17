"""Tests for allocation_backtester (Portfolio Visualizer-style)."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from backend.services import allocation_backtester as ab


def _fake_closes(tickers, n=1500, seed=42):
    """Generate correlated random-walk closes for a small universe."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    data = {}
    for i, t in enumerate(tickers):
        drift = 0.0003 - 0.0001 * (i % 3)
        vol = 0.010 + 0.004 * (i % 2)
        rets = rng.normal(drift, vol, size=n)
        prices = 100.0 * np.exp(np.cumsum(rets))
        data[t] = prices
    return pd.DataFrame(data, index=idx)


def test_rebalanced_equity_curve_runs_and_grows():
    closes = _fake_closes(["SPY", "AGG"], n=500)
    curve = ab._rebalanced_equity_curve(closes, {"SPY": 0.6, "AGG": 0.4}, "quarterly", 10_000.0)
    assert curve.iloc[0] == pytest.approx(10_000.0, rel=1e-2)
    assert len(curve) == len(closes)
    assert np.isfinite(curve.iloc[-1])


def test_rebalance_freq_buy_and_hold_changes_curve():
    closes = _fake_closes(["SPY", "AGG"], n=500)
    c_q = ab._rebalanced_equity_curve(closes, {"SPY": 0.6, "AGG": 0.4}, "quarterly")
    c_bh = ab._rebalanced_equity_curve(closes, {"SPY": 0.6, "AGG": 0.4}, "buy_and_hold")
    # Both should be well-defined but curves should diverge
    assert len(c_q) == len(c_bh)
    assert abs(c_q.iloc[-1] - c_bh.iloc[-1]) > 0


def test_metrics_shape():
    idx = pd.date_range("2020-01-01", periods=1000, freq="B")
    equity = pd.Series(np.linspace(10_000, 20_000, 1000), index=idx)
    m = ab._metrics(equity)
    for k in ("cagr", "volatility_annualized", "max_drawdown", "final_value", "n_years"):
        assert k in m


def test_metrics_on_drawdown_series():
    # Synthetic series with a clear 30% drawdown
    idx = pd.date_range("2020-01-01", periods=500, freq="B")
    vals = np.concatenate([
        np.linspace(100, 200, 200),
        np.linspace(200, 140, 100),  # 30% drawdown from 200 to 140
        np.linspace(140, 250, 200),
    ])
    equity = pd.Series(vals, index=idx)
    m = ab._metrics(equity)
    assert m["max_drawdown"] <= -0.28
    assert m["final_value"] == pytest.approx(250.0, rel=1e-3)


def test_backtest_allocation_rejects_bad_weights():
    with pytest.raises(ValueError):
        ab.backtest_allocation(weights={"SPY": 0.2}, start="2010-01-01")
    with pytest.raises(ValueError):
        ab.backtest_allocation(weights={}, start="2010-01-01")


def test_backtest_allocation_full_path_with_mock():
    tickers = ["SPY", "AGG"]
    closes = _fake_closes(tickers, n=1000)
    with patch.object(ab, "_download_closes", return_value=closes), \
         patch.object(ab, "cache_get", return_value=None), \
         patch.object(ab, "cache_set"):
        result = ab.backtest_allocation(weights={"SPY": 0.6, "AGG": 0.4},
                                         start="2020-01-01", rebalance_freq="quarterly")
    assert "metrics" in result
    assert "equity_curve" in result
    assert len(result["equity_curve"]) <= 260
    assert "cagr" in result["metrics"]


def test_named_strategies_are_valid():
    for name, weights in ab.NAMED_STRATEGIES.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-6, f"{name!r} weights sum to {total}"


def test_backtest_named_unknown():
    with pytest.raises(ValueError):
        ab.backtest_named("unicorn_strategy")


def test_backtest_named_delegates_to_backtest_allocation():
    tickers = list(ab.NAMED_STRATEGIES["60_40"].keys())
    closes = _fake_closes(tickers, n=600)
    with patch.object(ab, "_download_closes", return_value=closes), \
         patch.object(ab, "cache_get", return_value=None), \
         patch.object(ab, "cache_set"):
        result = ab.backtest_named("60_40", start="2020-01-01")
    assert "metrics" in result


def test_compare_strategies_table():
    # Build a closes frame containing every ticker used by the default compare set
    tickers = set()
    for n in ("60_40", "3_fund", "permanent_portfolio", "all_weather"):
        tickers.update(ab.NAMED_STRATEGIES[n].keys())
    closes = _fake_closes(list(tickers), n=800)
    with patch.object(ab, "_download_closes", return_value=closes), \
         patch.object(ab, "cache_get", return_value=None), \
         patch.object(ab, "cache_set"):
        result = ab.compare_strategies(start="2020-01-01")
    assert len(result["strategies"]) == 4
    assert all("name" in r for r in result["strategies"])
