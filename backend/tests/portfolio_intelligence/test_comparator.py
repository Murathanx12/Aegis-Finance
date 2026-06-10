"""
Tests for the portfolio comparator.

Covers: period resolution, metric normalization, date alignment,
benchmark blending, and edge cases.
"""

from datetime import datetime
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.services.portfolio_intelligence.comparator import (
    _resolve_period,
    _returns_to_metric_pack,
    _build_6040_returns,
    compute_comparison,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

def _make_returns(n_days: int = 252, drift: float = 0.0003, vol: float = 0.012, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=datetime.now(), periods=n_days)
    return pd.Series(rng.normal(drift, vol, n_days), index=dates)


# ── _resolve_period ─────────────────────────────────────────────────────────


class TestResolvePeriod:
    def test_known_periods(self):
        assert _resolve_period("1M") == 21
        assert _resolve_period("3M") == 63
        assert _resolve_period("6M") == 126
        assert _resolve_period("1Y") == 252
        assert _resolve_period("3Y") == 756

    def test_ytd_positive(self):
        days = _resolve_period("YTD")
        assert days >= 5

    def test_all_period(self):
        assert _resolve_period("ALL") == 5000

    def test_unknown_defaults_to_252(self):
        assert _resolve_period("UNKNOWN") == 252


# ── _returns_to_metric_pack ─────────────────────────────────────────────────


class TestReturnsToMetricPack:
    def test_positive_returns(self):
        returns = _make_returns(252, drift=0.002, vol=0.01)
        mp = _returns_to_metric_pack(returns)
        assert mp.total_return > 0
        assert mp.annualized_return > 0
        assert mp.annualized_volatility > 0
        assert mp.sharpe_ratio is not None
        assert mp.sharpe_ratio > 0

    def test_negative_returns(self):
        returns = _make_returns(252, drift=-0.0005, vol=0.01)
        mp = _returns_to_metric_pack(returns)
        assert mp.total_return < 0
        assert mp.annualized_return < 0

    def test_max_drawdown_negative(self):
        returns = _make_returns(252, drift=0.0003, vol=0.015)
        mp = _returns_to_metric_pack(returns)
        assert mp.max_drawdown <= 0

    def test_too_few_returns(self):
        returns = pd.Series([0.01, -0.005])
        mp = _returns_to_metric_pack(returns)
        assert mp.total_return == 0.0

    def test_with_spy_computes_beta(self):
        spy = _make_returns(252, seed=1)
        port = _make_returns(252, seed=2)
        mp = _returns_to_metric_pack(port, spy_returns=spy)
        assert mp.beta_vs_spy is not None
        assert mp.tracking_error_vs_spy is not None

    def test_sortino_populated(self):
        returns = _make_returns(252, drift=0.0005, vol=0.015)
        mp = _returns_to_metric_pack(returns)
        assert mp.sortino_ratio is not None

    def test_drawdown_duration(self):
        returns = _make_returns(504, drift=0.0002, vol=0.02, seed=99)
        mp = _returns_to_metric_pack(returns)
        if mp.max_drawdown_duration_days is not None:
            assert mp.max_drawdown_duration_days >= 0


# ── _build_6040_returns ─────────────────────────────────────────────────────


class TestBuild6040:
    def test_blend_weights(self):
        spy = pd.Series([0.01, 0.02, -0.01], index=pd.bdate_range("2026-01-01", periods=3))
        agg = pd.Series([0.002, 0.001, 0.003], index=pd.bdate_range("2026-01-01", periods=3))
        blended = _build_6040_returns(spy, agg)
        expected = spy * 0.60 + agg * 0.40
        np.testing.assert_allclose(blended.values, expected.values, atol=1e-10)

    def test_misaligned_dates(self):
        spy = pd.Series([0.01, 0.02], index=pd.bdate_range("2026-01-01", periods=2))
        agg = pd.Series([0.002, 0.001, 0.003], index=pd.bdate_range("2026-01-01", periods=3))
        blended = _build_6040_returns(spy, agg)
        assert len(blended) == 2  # inner join

    def test_empty_input(self):
        spy = pd.Series(dtype=float)
        agg = pd.Series([0.01])
        blended = _build_6040_returns(spy, agg)
        assert len(blended) == 0


# ── compute_comparison ──────────────────────────────────────────────────────


class TestComputeComparison:
    @patch("backend.services.portfolio_intelligence.comparator._fetch_benchmark_returns")
    def test_basic_comparison(self, mock_fetch):
        spy_returns = _make_returns(252, seed=1)
        agg_returns = _make_returns(252, seed=2)
        mock_fetch.side_effect = lambda ticker, days: (
            spy_returns if ticker == "SPY" else agg_returns
        )

        port_returns = {
            "balanced": _make_returns(252, seed=3),
            "aggressive": _make_returns(252, seed=4),
        }
        result = compute_comparison(port_returns, ["SPY", "AGG"], period="1Y")
        assert "balanced" in result.lanes
        assert "aggressive" in result.lanes
        assert "SPY" in result.benchmarks
        assert "AGG" in result.benchmarks
        assert result.period == "1Y"

    @patch("backend.services.portfolio_intelligence.comparator._fetch_benchmark_returns")
    def test_6040_benchmark(self, mock_fetch):
        spy_returns = _make_returns(252, seed=1)
        agg_returns = _make_returns(252, seed=2)
        mock_fetch.side_effect = lambda ticker, days: (
            spy_returns if ticker == "SPY" else agg_returns
        )

        port_returns = {"conservative": _make_returns(252, seed=5)}
        result = compute_comparison(port_returns, ["SPY", "60-40"], period="1Y")
        assert "60-40" in result.benchmarks

    @patch("backend.services.portfolio_intelligence.comparator._fetch_benchmark_returns")
    def test_period_trimming(self, mock_fetch):
        spy_returns = _make_returns(504, seed=1)
        mock_fetch.return_value = spy_returns

        port_returns = {"long": _make_returns(504, seed=3)}
        result = compute_comparison(port_returns, ["SPY"], period="3M")
        assert result.period == "3M"
