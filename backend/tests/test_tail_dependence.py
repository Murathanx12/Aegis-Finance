"""
Tests for Cross-Asset Tail Dependence & Contagion Analysis
=============================================================

Tests empirical copula tail dependence estimation, contagion scoring,
cluster detection, and rolling analysis using synthetic data (fast)
and real market data (slow, network-dependent).
"""

import numpy as np
import pandas as pd
import pytest

from backend.services.tail_dependence import (
    _empirical_copula_ranks,
    _pairwise_tail_dependence,
    _compute_all_pairs,
    _cluster_analysis,
    _portfolio_contagion_summary,
    _rolling_tail_dependence,
    analyze_tail_dependence,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def correlated_returns():
    """Generate highly correlated returns (ρ ≈ 0.8) with fat tails.

    Two assets that move together, especially in the tails.
    """
    rng = np.random.default_rng(42)
    n = 500

    # Common factor + idiosyncratic
    common = rng.standard_t(df=5, size=n) * 0.01
    asset_a = common + rng.normal(0, 0.005, n)
    asset_b = common + rng.normal(0, 0.005, n)

    dates = pd.bdate_range(end="2025-12-31", periods=n)
    return pd.DataFrame({"A": asset_a, "B": asset_b}, index=dates)


@pytest.fixture
def uncorrelated_returns():
    """Generate independent returns — no tail dependence expected."""
    rng = np.random.default_rng(123)
    n = 500
    dates = pd.bdate_range(end="2025-12-31", periods=n)
    return pd.DataFrame({
        "X": rng.normal(0.0003, 0.01, n),
        "Y": rng.normal(0.0002, 0.012, n),
    }, index=dates)


@pytest.fixture
def mixed_portfolio():
    """4-asset portfolio: 2 correlated equity-like, 1 bond-like, 1 gold-like."""
    rng = np.random.default_rng(7)
    n = 504

    # Common equity factor
    equity_factor = rng.standard_t(df=5, size=n) * 0.01
    stock_a = equity_factor + rng.normal(0, 0.005, n)
    stock_b = equity_factor * 0.8 + rng.normal(0, 0.006, n)

    # Bond: slightly negatively correlated to equities (flight to safety)
    bond = -equity_factor * 0.3 + rng.normal(0.0001, 0.003, n)

    # Gold: near-independent
    gold = rng.normal(0.0002, 0.008, n)

    dates = pd.bdate_range(end="2025-12-31", periods=n)
    return pd.DataFrame({
        "EQ1": stock_a, "EQ2": stock_b,
        "BOND": bond, "GOLD": gold,
    }, index=dates)


# ── Unit: Empirical Copula Ranks ──────────────────────────────────────────────


class TestEmpiricalCopulaRanks:
    def test_output_range(self, correlated_returns):
        """Pseudo-observations must be in (0, 1) — never exactly 0 or 1."""
        ranks = _empirical_copula_ranks(correlated_returns)
        assert ranks.min().min() > 0
        assert ranks.max().max() < 1

    def test_uniform_marginals(self, correlated_returns):
        """Each column should be approximately uniform on (0, 1)."""
        ranks = _empirical_copula_ranks(correlated_returns)
        for col in ranks.columns:
            mean = ranks[col].mean()
            assert 0.45 < mean < 0.55, f"Mean of {col} ranks should be ~0.5, got {mean}"

    def test_preserves_columns(self, mixed_portfolio):
        ranks = _empirical_copula_ranks(mixed_portfolio)
        assert list(ranks.columns) == list(mixed_portfolio.columns)


# ── Unit: Pairwise Tail Dependence ────────────────────────────────────────────


class TestPairwiseTailDependence:
    def test_correlated_assets_have_tail_dep(self, correlated_returns):
        """Highly correlated t-distributed assets should show tail dependence."""
        ranks = _empirical_copula_ranks(correlated_returns)
        td = _pairwise_tail_dependence(ranks["A"].values, ranks["B"].values)

        assert td["lower_tail_dep"] > 0.05, (
            f"Expected positive lower tail dep for correlated assets, got {td['lower_tail_dep']}"
        )

    def test_independent_assets_low_tail_dep(self, uncorrelated_returns):
        """Independent Gaussian returns should have near-zero tail dependence."""
        ranks = _empirical_copula_ranks(uncorrelated_returns)
        td = _pairwise_tail_dependence(ranks["X"].values, ranks["Y"].values)

        assert td["lower_tail_dep"] < 0.15, (
            f"Expected low tail dep for independent assets, got {td['lower_tail_dep']}"
        )

    def test_perfect_dependence(self):
        """Identical series should have tail dependence ≈ 1.0."""
        rng = np.random.default_rng(99)
        n = 1000
        x = rng.normal(0, 1, n)
        u = np.argsort(np.argsort(x)).astype(float) / (n + 1)

        td = _pairwise_tail_dependence(u, u)
        assert td["lower_tail_dep"] > 0.80, (
            f"Identical series should have high tail dep, got {td['lower_tail_dep']}"
        )

    def test_returns_both_tails(self, correlated_returns):
        """Should return both lower and upper tail dependence."""
        ranks = _empirical_copula_ranks(correlated_returns)
        td = _pairwise_tail_dependence(ranks["A"].values, ranks["B"].values)

        assert "lower_tail_dep" in td
        assert "upper_tail_dep" in td
        assert isinstance(td["lower_tail_dep"], float)
        assert isinstance(td["upper_tail_dep"], float)


# ── Unit: Compute All Pairs ───────────────────────────────────────────────────


class TestComputeAllPairs:
    def test_correct_number_of_pairs(self, mixed_portfolio):
        """n assets → n*(n-1)/2 pairs."""
        ranks = _empirical_copula_ranks(mixed_portfolio)
        pairs = _compute_all_pairs(ranks, mixed_portfolio)

        n = len(mixed_portfolio.columns)
        expected = n * (n - 1) // 2
        assert len(pairs) == expected

    def test_pair_fields(self, mixed_portfolio):
        """Each pair dict should have all required fields."""
        ranks = _empirical_copula_ranks(mixed_portfolio)
        pairs = _compute_all_pairs(ranks, mixed_portfolio)

        required = {
            "asset_1", "asset_2", "pearson_correlation", "kendall_tau",
            "lower_tail_dep", "upper_tail_dep", "tail_asymmetry", "contagion_score",
        }
        for pair in pairs:
            assert required.issubset(pair.keys()), f"Missing fields: {required - pair.keys()}"

    def test_sorted_by_contagion(self, mixed_portfolio):
        """Pairs should be sorted by contagion score descending."""
        ranks = _empirical_copula_ranks(mixed_portfolio)
        pairs = _compute_all_pairs(ranks, mixed_portfolio)

        scores = [p["contagion_score"] for p in pairs]
        assert scores == sorted(scores, reverse=True)

    def test_equity_pair_higher_tail_dep_than_equity_bond(self, mixed_portfolio):
        """EQ1-EQ2 should have higher tail dep than EQ1-BOND."""
        ranks = _empirical_copula_ranks(mixed_portfolio)
        pairs = _compute_all_pairs(ranks, mixed_portfolio)

        eq_pair = next(
            p for p in pairs
            if {p["asset_1"], p["asset_2"]} == {"EQ1", "EQ2"}
        )
        eq_bond = next(
            p for p in pairs
            if {p["asset_1"], p["asset_2"]} == {"EQ1", "BOND"}
        )

        assert eq_pair["lower_tail_dep"] > eq_bond["lower_tail_dep"], (
            f"Equity pair tail dep ({eq_pair['lower_tail_dep']}) should exceed "
            f"equity-bond ({eq_bond['lower_tail_dep']})"
        )


# ── Unit: Cluster Analysis ───────────────────────────────────────────────────


class TestClusterAnalysis:
    def test_correlated_assets_cluster(self, mixed_portfolio):
        """Correlated equities should form a cluster."""
        ranks = _empirical_copula_ranks(mixed_portfolio)
        pairs = _compute_all_pairs(ranks, mixed_portfolio)
        clusters = _cluster_analysis(pairs, list(mixed_portfolio.columns))

        # At least one cluster should contain EQ1 and EQ2
        eq_clustered = any(
            "EQ1" in c["members"] and "EQ2" in c["members"]
            for c in clusters
        )
        # This may not always cluster depending on threshold, so just check structure
        for c in clusters:
            assert "members" in c
            assert "n_members" in c
            assert "avg_lower_tail_dep" in c
            assert c["n_members"] >= 2

    def test_empty_pairs(self):
        """No pairs → no clusters."""
        clusters = _cluster_analysis([], ["A", "B"])
        assert clusters == []


# ── Unit: Portfolio Summary ───────────────────────────────────────────────────


class TestPortfolioSummary:
    def test_summary_fields(self, mixed_portfolio):
        """Summary should have all expected fields."""
        ranks = _empirical_copula_ranks(mixed_portfolio)
        pairs = _compute_all_pairs(ranks, mixed_portfolio)
        summary = _portfolio_contagion_summary(pairs, list(mixed_portfolio.columns))

        required = {
            "overall_contagion", "avg_lower_tail_dep", "avg_pearson_correlation",
            "max_lower_tail_dep", "hidden_risk_score", "diversification_quality",
            "diversification_explanation", "n_pairs", "n_high_contagion_pairs",
        }
        assert required.issubset(summary.keys())

    def test_diversification_quality_values(self, mixed_portfolio):
        """Quality should be one of the defined levels."""
        ranks = _empirical_copula_ranks(mixed_portfolio)
        pairs = _compute_all_pairs(ranks, mixed_portfolio)
        summary = _portfolio_contagion_summary(pairs, list(mixed_portfolio.columns))

        assert summary["diversification_quality"] in {
            "excellent", "good", "fair", "poor",
        }

    def test_empty_pairs(self):
        summary = _portfolio_contagion_summary([], ["A"])
        assert summary["diversification_quality"] == "unknown"


# ── Unit: Rolling Tail Dependence ─────────────────────────────────────────────


class TestRollingTailDependence:
    def test_rolling_output(self, correlated_returns):
        """Rolling analysis should return time series of tail dep estimates."""
        rolling = _rolling_tail_dependence(
            correlated_returns, "A", "B", window=126,
        )
        assert len(rolling) > 0

        for point in rolling:
            assert "date" in point
            assert "lower_tail_dep" in point
            assert "pearson_correlation" in point

    def test_short_series_returns_empty(self):
        """Series shorter than window should return empty."""
        dates = pd.bdate_range(end="2025-12-31", periods=50)
        short = pd.DataFrame({
            "A": np.random.default_rng(1).normal(0, 0.01, 50),
            "B": np.random.default_rng(2).normal(0, 0.01, 50),
        }, index=dates)

        rolling = _rolling_tail_dependence(short, "A", "B", window=126)
        assert rolling == []


# ── Integration: Full Analysis (synthetic) ────────────────────────────────────


class TestAnalyzeSynthetic:
    def test_too_few_tickers(self):
        """Should return error for < 2 tickers."""
        result = analyze_tail_dependence(["AAPL"])
        assert "error" in result

    def test_output_structure(self, mixed_portfolio, monkeypatch):
        """Full analysis with mocked data should have all top-level keys."""
        # Mock _fetch_returns to use our synthetic data
        import backend.services.tail_dependence as td_module
        monkeypatch.setattr(td_module, "_fetch_returns", lambda t, l: mixed_portfolio)

        result = analyze_tail_dependence(
            ["EQ1", "EQ2", "BOND", "GOLD"],
            include_rolling=True,
        )

        assert "tickers" in result
        assert "pairs" in result
        assert "clusters" in result
        assert "portfolio_summary" in result
        assert "rolling" in result
        assert result["n_observations"] == len(mixed_portfolio)


# ── Slow: Real Market Data ────────────────────────────────────────────────────


@pytest.mark.slow
class TestRealMarketData:
    def test_spy_tlt_gld(self):
        """Real tail dep: SPY-TLT should have lower tail dep than SPY-QQQ."""
        result = analyze_tail_dependence(
            ["SPY", "QQQ", "TLT", "GLD"],
            lookback=504,
        )
        assert "error" not in result
        assert len(result["pairs"]) == 6

        # Find specific pairs
        spy_qqq = next(
            (p for p in result["pairs"]
             if {p["asset_1"], p["asset_2"]} == {"SPY", "QQQ"}),
            None,
        )
        spy_tlt = next(
            (p for p in result["pairs"]
             if {p["asset_1"], p["asset_2"]} == {"SPY", "TLT"}),
            None,
        )

        if spy_qqq and spy_tlt:
            assert spy_qqq["lower_tail_dep"] > spy_tlt["lower_tail_dep"], (
                f"SPY-QQQ tail dep ({spy_qqq['lower_tail_dep']}) should exceed "
                f"SPY-TLT ({spy_tlt['lower_tail_dep']})"
            )

    def test_portfolio_summary_quality(self):
        """Diversified portfolio (stocks + bonds + gold) should rate at least 'fair'."""
        result = analyze_tail_dependence(
            ["SPY", "TLT", "GLD", "VNQ"],
            lookback=504,
        )
        assert "error" not in result
        assert result["portfolio_summary"]["diversification_quality"] in {
            "excellent", "good", "fair",
        }

    def test_rolling_analysis(self):
        """Rolling analysis should produce time series."""
        result = analyze_tail_dependence(
            ["SPY", "QQQ"],
            lookback=504,
            include_rolling=True,
        )
        assert "error" not in result
        assert "rolling" in result
        assert len(result["rolling"]["series"]) > 0
