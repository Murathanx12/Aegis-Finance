"""
Cycle 22 hardening tests — signal differentiation, risk scorer config, features cleanup.

Covers:
  1. signal_engine.get_stock_signal: additive analyst blending, edge cases
  2. signal_engine.get_market_signal: extreme / None / NaN inputs
  3. risk_scorer.build_risk_score: config-driven momentum threshold
  4. features.build_feature_matrix: NaN preservation (no fillna(0))
"""

import numpy as np
import pandas as pd
import pytest

from backend.services.signal_engine import get_market_signal, get_stock_signal
from backend.services.risk_scorer import build_risk_score, rolling_zscore, _dual_zscore
from backend.config import config


# ═══════════════════════════════════════════════════════════════════════════
# 1. STOCK SIGNAL — additive analyst blending
# ═══════════════════════════════════════════════════════════════════════════


class TestStockSignalAdditiveBlending:
    """Verify analyst target is additive, not convex-combo dominant."""

    def _hold_market(self):
        """Produce a neutral Hold market signal."""
        sig = get_market_signal()
        assert sig["action"] == "Hold"
        return sig

    def test_analyst_contribution_bounded(self):
        """Analyst component alone cannot exceed analyst_w * 0.5 = 0.06."""
        market = self._hold_market()
        base = get_stock_signal(market, current_price=100.0)
        huge_upside = get_stock_signal(market, analyst_target=200.0, current_price=100.0)
        analyst_w = config.get("stock_signal_weights", {}).get("analyst_target", 0.12)
        delta = huge_upside["composite_score"] - base["composite_score"]
        # analyst_sig is clipped to 0.5, so max delta = analyst_w * 0.5
        assert delta <= analyst_w * 0.5 + 0.001

    def test_analyst_downside_penalizes(self):
        """Stock trading above analyst target should be penalized."""
        market = self._hold_market()
        base = get_stock_signal(market, current_price=100.0)
        below_target = get_stock_signal(market, analyst_target=70.0, current_price=100.0)
        assert below_target["composite_score"] < base["composite_score"]

    def test_zero_analyst_target_ignored(self):
        """analyst_target=0 should be treated same as None."""
        market = self._hold_market()
        no_target = get_stock_signal(market, current_price=100.0)
        zero_target = get_stock_signal(market, analyst_target=0.0, current_price=100.0)
        assert no_target["composite_score"] == zero_target["composite_score"]

    def test_zero_current_price_no_crash(self):
        """current_price=0 should not cause division error."""
        market = self._hold_market()
        result = get_stock_signal(market, analyst_target=150.0, current_price=0.0)
        assert "action" in result
        assert -1 <= result["composite_score"] <= 1

    def test_negative_analyst_target_ignored(self):
        """Negative analyst target should be skipped."""
        market = self._hold_market()
        base = get_stock_signal(market, current_price=100.0)
        neg = get_stock_signal(market, analyst_target=-50.0, current_price=100.0)
        assert neg["composite_score"] == base["composite_score"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. STOCK SIGNAL — sector momentum & PE edge cases
# ═══════════════════════════════════════════════════════════════════════════


class TestStockSignalEdgeCases:
    """Edge cases for sector momentum, PE ratio, and forward PE inputs."""

    def _hold_market(self):
        return get_market_signal()

    def test_sector_momentum_below_threshold_ignored(self):
        """Sector momentum <= 3% should not affect score."""
        market = self._hold_market()
        base = get_stock_signal(market)
        small_mom = get_stock_signal(market, sector_momentum=2.5)
        assert base["composite_score"] == small_mom["composite_score"]

    def test_sector_momentum_clipped(self):
        """Extreme sector momentum should be clipped to ±0.15."""
        market = self._hold_market()
        base = get_stock_signal(market)
        extreme = get_stock_signal(market, sector_momentum=500.0)
        delta = extreme["composite_score"] - base["composite_score"]
        assert delta <= 0.151  # clipped at 0.15

    def test_negative_sector_momentum_penalizes(self):
        market = self._hold_market()
        base = get_stock_signal(market)
        weak = get_stock_signal(market, sector_momentum=-15.0)
        assert weak["composite_score"] < base["composite_score"]

    def test_pe_ratio_zero_ignored(self):
        """P/E of 0 or negative should not affect score."""
        market = self._hold_market()
        base = get_stock_signal(market)
        zero_pe = get_stock_signal(market, pe_ratio=0.0)
        neg_pe = get_stock_signal(market, pe_ratio=-5.0)
        assert base["composite_score"] == zero_pe["composite_score"]
        assert base["composite_score"] == neg_pe["composite_score"]

    def test_forward_pe_none_no_crash(self):
        """None forward_pe with valid pe_ratio should not crash."""
        market = self._hold_market()
        result = get_stock_signal(market, pe_ratio=20.0, forward_pe=None)
        assert "action" in result

    def test_forward_pe_zero_no_crash(self):
        """Zero forward_pe should skip earnings growth calc."""
        market = self._hold_market()
        base = get_stock_signal(market, pe_ratio=20.0)
        zero_fwd = get_stock_signal(market, pe_ratio=20.0, forward_pe=0.0)
        assert base["composite_score"] == zero_fwd["composite_score"]

    def test_forward_pe_greater_than_trailing_penalizes(self):
        """Forward PE > trailing PE means declining earnings → penalty."""
        market = self._hold_market()
        growing = get_stock_signal(market, pe_ratio=40.0, forward_pe=20.0)
        declining = get_stock_signal(market, pe_ratio=20.0, forward_pe=30.0)
        assert declining["composite_score"] < growing["composite_score"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. MARKET SIGNAL — extreme and None inputs
# ═══════════════════════════════════════════════════════════════════════════


class TestMarketSignalExtremeInputs:
    """Verify market signal handles extreme, zero, and None inputs safely."""

    def test_all_none_optionals(self):
        """All optional params as None should produce a valid Hold."""
        result = get_market_signal(
            crash_prob_3m=None, crash_prob_12m=None,
            yield_curve=None, external_consensus=None,
        )
        assert result["action"] == "Hold"
        assert -1 <= result["composite_score"] <= 1

    def test_extreme_crash_100_pct(self):
        """100% crash probability should produce Strong Sell."""
        result = get_market_signal(crash_prob_3m=100.0, crash_prob_12m=100.0,
                                   regime="Bear", vix=80.0, risk_score=4.0)
        assert result["action"] in {"Sell", "Strong Sell"}
        assert result["composite_score"] < -0.3

    def test_zero_crash_prob(self):
        """0% crash probability is maximally bullish for that component."""
        result = get_market_signal(crash_prob_3m=0.0)
        assert result["components"]["crash_prob"] > 0

    def test_extreme_positive_momentum(self):
        """Huge positive momentum should produce a bullish signal."""
        result = get_market_signal(sp500_1m_return=50.0, sp500_3m_return=50.0,
                                   sp500_ytd_return=80.0)
        assert result["components"]["momentum"] > 0.5

    def test_extreme_negative_momentum(self):
        result = get_market_signal(sp500_1m_return=-50.0, sp500_3m_return=-50.0)
        assert result["components"]["momentum"] < 0

    def test_vix_zero(self):
        """VIX=0 is unrealistic but should not crash."""
        result = get_market_signal(vix=0.0)
        assert "action" in result

    def test_vix_extreme_high(self):
        """VIX=90 (2008-level) should produce negative valuation signal."""
        result = get_market_signal(vix=90.0)
        assert result["components"]["valuation"] < 0

    def test_risk_score_extreme_positive(self):
        """risk_score = +4 should produce negative macro_risk signal."""
        result = get_market_signal(risk_score=4.0)
        assert result["components"]["macro_risk"] < -0.5

    def test_risk_score_extreme_negative(self):
        """risk_score = -4 should produce positive macro_risk signal."""
        result = get_market_signal(risk_score=-4.0)
        assert result["components"]["macro_risk"] > 0

    def test_unknown_regime_treated_as_neutral(self):
        result = get_market_signal(regime="UnknownRegime")
        assert result["components"]["regime"] == 0.0

    def test_unknown_external_consensus_treated_as_mixed(self):
        result = get_market_signal(external_consensus="UNKNOWN_VALUE")
        assert result["components"]["external"] == 0.0

    def test_deeply_inverted_yield_curve(self):
        """Deeply inverted yield curve should drag valuation negative."""
        normal = get_market_signal(yield_curve=2.0)
        inverted = get_market_signal(yield_curve=-1.5)
        assert inverted["components"]["valuation"] < normal["components"]["valuation"]

    def test_mean_reversion_fires_on_oversold(self):
        """3M return < -8% with VIX < 35 should activate mean reversion."""
        result = get_market_signal(sp500_3m_return=-15.0, vix=25.0)
        assert result["components"]["mean_reversion"] > 0.3

    def test_mean_reversion_blocked_by_crisis_vix(self):
        """Mean reversion should NOT fire when VIX >= 35 (crisis)."""
        result = get_market_signal(sp500_3m_return=-15.0, vix=40.0)
        assert result["components"]["mean_reversion"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 4. RISK SCORER — config-driven momentum threshold
# ═══════════════════════════════════════════════════════════════════════════


class TestRiskScorerConfigThreshold:
    """Verify momentum exhaustion reads from config, not hardcoded."""

    def _make_sp500_data(self, n_days: int = 500) -> pd.DataFrame:
        """Generate synthetic SP500 + VIX data for risk scorer tests."""
        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2020-01-01", periods=n_days)
        prices = 3000 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n_days)))
        vix = 20 + rng.normal(0, 3, n_days).clip(-10, 30)
        return pd.DataFrame({"SP500": prices, "VIX": vix}, index=dates)

    def test_config_has_momentum_exhaustion_threshold(self):
        """Config should contain the threshold (was hardcoded at 1.5)."""
        assert "momentum_exhaustion_threshold" in config["risk"]
        assert isinstance(config["risk"]["momentum_exhaustion_threshold"], (int, float))

    def test_risk_score_runs_with_sp500_only(self):
        """Minimal data: just SP500 column should produce a valid score."""
        data = self._make_sp500_data()
        score = build_risk_score(data)
        assert len(score) == len(data)
        assert score.iloc[-1] >= -4 and score.iloc[-1] <= 4

    def test_risk_score_empty_dataframe(self):
        """Empty DataFrame should return zeros."""
        data = pd.DataFrame({"SP500": pd.Series(dtype=float)})
        score = build_risk_score(data)
        assert len(score) == 0

    def test_risk_score_with_all_columns(self):
        """Full 9-column data should use all indicators."""
        rng = np.random.default_rng(42)
        n = 500
        dates = pd.bdate_range("2020-01-01", periods=n)
        data = pd.DataFrame({
            "SP500": 3000 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n))),
            "VIX": 20 + rng.normal(0, 3, n).clip(-10, 30),
            "T10Y": 3.5 + rng.normal(0, 0.1, n),
            "T3M": 2.0 + rng.normal(0, 0.1, n),
            "T30Y": 4.0 + rng.normal(0, 0.1, n),
            "HYG": 80 + rng.normal(0, 1, n),
            "LQD": 110 + rng.normal(0, 1, n),
            "Gold": 1800 + rng.normal(0, 20, n),
            "NASDAQ": 12000 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n))),
            "Russell": 2000 * np.exp(np.cumsum(rng.normal(0.0002, 0.014, n))),
        }, index=dates)
        score = build_risk_score(data)
        assert score.iloc[-1] >= -4 and score.iloc[-1] <= 4
        assert not score.isna().all()

    def test_risk_score_constant_prices_no_crash(self):
        """Constant prices (zero vol) should not crash — std=0 produces NaN z-scores."""
        n = 300
        dates = pd.bdate_range("2020-01-01", periods=n)
        data = pd.DataFrame({
            "SP500": [3000.0] * n,
            "VIX": [15.0] * n,
        }, index=dates)
        score = build_risk_score(data)
        assert len(score) == n
        # Constant prices → std=0 → z-score is NaN → score may be NaN early
        # but should not raise


class TestRollingZscoreEdges:
    """Edge cases for the rolling z-score helper."""

    def test_short_series(self):
        """Series shorter than window should produce all NaN."""
        s = pd.Series([1, 2, 3])
        z = rolling_zscore(s, window=252)
        assert z.isna().all()

    def test_constant_series(self):
        """Constant values → std=0 → z=NaN (not inf)."""
        s = pd.Series([5.0] * 300)
        z = rolling_zscore(s, window=100)
        # Where std=0, z should be NaN (not ±inf)
        valid = z.dropna()
        assert not np.isinf(valid).any()

    def test_clip_range(self):
        """Z-scores should be clipped to [-5, +5]."""
        rng = np.random.default_rng(99)
        s = pd.Series(rng.normal(0, 1, 500))
        # Inject an extreme outlier
        s.iloc[-1] = 100.0
        z = rolling_zscore(s, window=100)
        assert z.max() <= 5.0
        assert z.min() >= -5.0

    def test_dual_zscore_takes_max(self):
        """Dual z-score should be >= long-window z-score."""
        rng = np.random.default_rng(42)
        s = pd.Series(rng.normal(0, 1, 500))
        z_long = rolling_zscore(s, 252)
        z_dual = _dual_zscore(s, long_window=252, short_window=63)
        # After both windows have warmed up, dual should be >= long
        valid_idx = z_long.dropna().index.intersection(z_dual.dropna().index)
        if len(valid_idx) > 0:
            assert (z_dual.loc[valid_idx] >= z_long.loc[valid_idx] - 0.001).all()


# ═══════════════════════════════════════════════════════════════════════════
# 5. FEATURES — NaN preservation (no more fillna(0))
# ═══════════════════════════════════════════════════════════════════════════


class TestFeaturesNanPreservation:
    """Verify features.py no longer replaces NaN with 0."""

    def test_no_fillna_zero_in_source(self):
        """The features.py cleanup line should NOT contain fillna(0)."""
        from pathlib import Path
        features_path = Path(__file__).parent.parent / "services" / ".." / ".." / "engine" / "training" / "features.py"
        features_path = features_path.resolve()
        content = features_path.read_text(encoding="utf-8")
        # The old line was: df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
        assert ".fillna(0)" not in content, "features.py still contains fillna(0) — should preserve NaN for LightGBM"

    def test_build_feature_matrix_preserves_nan(self):
        """Feature matrix should contain NaN (not 0) for early rows where
        rolling windows haven't warmed up."""
        try:
            from engine.training.features import build_feature_matrix
        except ImportError:
            pytest.skip("engine.training.features not importable")

        # Build minimal SP500 data (short enough that early rows must be NaN)
        rng = np.random.default_rng(42)
        n = 300  # less than 252-day rolling window
        dates = pd.bdate_range("2023-01-01", periods=n)
        sp500 = 4000 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
        data = pd.DataFrame({"SP500": sp500}, index=dates)

        features = build_feature_matrix(data)
        # Row 0 should have NaN for most rolling features (windows not filled)
        first_row = features.iloc[0]
        n_nan = first_row.isna().sum()
        # Most rolling features (vol, zscore, SMA etc.) need ≥20 days warmup
        assert n_nan > 0, "First row should have NaN from unfilled rolling windows, not zeros"

    def test_no_inf_in_features(self):
        """Feature matrix should never contain ±inf (replaced with NaN)."""
        try:
            from engine.training.features import build_feature_matrix
        except ImportError:
            pytest.skip("engine.training.features not importable")

        rng = np.random.default_rng(42)
        n = 400
        dates = pd.bdate_range("2022-01-01", periods=n)
        sp500 = 4000 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
        data = pd.DataFrame({"SP500": sp500}, index=dates)

        features = build_feature_matrix(data)
        assert not np.isinf(features.values).any(), "Feature matrix should not contain inf values"


# ═══════════════════════════════════════════════════════════════════════════
# 6. CONFIG — stock_signal_weights section exists and is sane
# ═══════════════════════════════════════════════════════════════════════════


class TestConfigStockSignalWeights:
    """Verify the new stock_signal_weights config section."""

    def test_stock_signal_weights_exists(self):
        assert "stock_signal_weights" in config

    def test_required_keys_present(self):
        sw = config["stock_signal_weights"]
        for key in ["analyst_target", "sector_momentum", "pe_bonus", "earnings_growth"]:
            assert key in sw, f"Missing {key} in stock_signal_weights"

    def test_analyst_weight_reasonable(self):
        """Analyst weight should be < 0.20 to prevent dominance."""
        w = config["stock_signal_weights"]["analyst_target"]
        assert 0 < w < 0.20, f"Analyst weight {w} outside safe range (0, 0.20)"

    def test_all_weights_positive(self):
        for key, val in config["stock_signal_weights"].items():
            assert val > 0, f"{key} weight should be positive, got {val}"
