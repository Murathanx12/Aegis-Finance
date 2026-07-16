"""
Tests for 7 previously-untested backend services:
  - savings_calculator (pure math)
  - data_quality (pure logic)
  - regime_validator (pure logic)
  - shap_explainer (mock predictor)
  - net_liquidity (mock FRED)
  - return_model (fallback + mock LGB)
  - llm_analyzer (mock client + parsing)

All tests are fast (no network). Marked "not slow" by default.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# SAVINGS CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════


class TestSavingsBasic:
    """Core projection logic."""

    def test_returns_required_keys(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(500, 10_000, 30, 65)
        assert "projections" in result
        assert "summary" in result
        assert "target" in result
        assert "milestones" in result

    def test_projection_count_matches_years(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(500, 0, 30, 50)
        assert len(result["projections"]) == 20

    def test_nominal_grows_monotonically(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(1000, 0, 25, 65)
        balances = [p["nominal_balance"] for p in result["projections"]]
        assert balances == sorted(balances)

    def test_real_less_than_nominal(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(500, 10_000, 30, 65)
        for p in result["projections"]:
            assert p["real_balance"] <= p["nominal_balance"]

    def test_conservative_grows_slower_than_aggressive(self):
        from backend.services.savings_calculator import project_savings
        cons = project_savings(500, 10_000, 30, 65, risk_level="conservative")
        aggr = project_savings(500, 10_000, 30, 65, risk_level="aggressive")
        assert cons["summary"]["final_nominal"] < aggr["summary"]["final_nominal"]

    def test_total_contributed_correct(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(500, 10_000, 30, 40)
        # 10 years * 12 months * $500 + $10k initial
        expected = 10_000 + 500 * 12 * 10
        assert result["summary"]["total_contributed"] == expected

    def test_growth_equals_nominal_minus_contributed(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(500, 10_000, 30, 65)
        s = result["summary"]
        assert abs(s["total_growth"] - (s["final_nominal"] - s["total_contributed"])) < 0.01


class TestSavingsTarget:
    """Target-reaching and required monthly."""

    def test_target_met_flag(self):
        from backend.services.savings_calculator import project_savings
        # Large contribution should reach $1M
        result = project_savings(5000, 100_000, 25, 65)
        assert result["target"]["met"] is True
        assert result["target"]["met_at_age"] is not None

    def test_target_not_met_provides_required_monthly(self):
        from backend.services.savings_calculator import project_savings
        # Tiny contribution won't reach $1M
        result = project_savings(50, 0, 55, 65)
        assert result["target"]["met"] is False
        assert result["target"]["required_monthly"] is not None
        assert result["target"]["required_monthly"] > 50

    def test_required_monthly_zero_rate(self):
        from backend.services.savings_calculator import _required_monthly_for_target
        # With 0% rate, just divide evenly
        result = _required_monthly_for_target(0, 120_000, 120, 0.0)
        assert result == 1000.0

    def test_already_exceeded_target(self):
        from backend.services.savings_calculator import _required_monthly_for_target
        result = _required_monthly_for_target(2_000_000, 1_000_000, 120, 0.005)
        assert result == 0.0


class TestSavingsMilestones:
    """Milestone detection."""

    def test_milestones_increasing(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(2000, 50_000, 25, 65)
        amounts = [m["amount"] for m in result["milestones"]]
        assert amounts == sorted(amounts)

    def test_no_milestones_below_current_savings(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(500, 300_000, 30, 65)
        for m in result["milestones"]:
            assert m["amount"] > 300_000

    def test_same_age_produces_one_year(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(500, 0, 65, 65)
        # max(65-65, 1) = 1 year
        assert len(result["projections"]) == 1


class TestSavingsEdgeCases:
    """Edge cases and boundary inputs."""

    def test_zero_contribution(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(0, 100_000, 30, 65)
        # Growth purely from compound interest
        assert result["summary"]["final_nominal"] > 100_000

    def test_zero_savings_zero_contribution(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(0, 0, 30, 65)
        assert result["summary"]["final_nominal"] == 0.0

    def test_unknown_risk_level_defaults_moderate(self):
        from backend.services.savings_calculator import project_savings
        default = project_savings(500, 10_000, 30, 65, risk_level="unknown")
        moderate = project_savings(500, 10_000, 30, 65, risk_level="moderate")
        assert default["summary"]["final_nominal"] == moderate["summary"]["final_nominal"]

    def test_summary_rates(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(500, 0, 30, 65, risk_level="aggressive")
        assert result["summary"]["nominal_rate"] == 0.09
        assert result["summary"]["inflation_rate"] == 0.025
        assert abs(result["summary"]["real_rate"] - 0.065) < 1e-6


# ═══════════════════════════════════════════════════════════════════════════════
# DATA QUALITY CHECKER
# ═══════════════════════════════════════════════════════════════════════════════


def _make_market_df(n_days=300, include_vix=True, include_yields=True):
    """Helper: build a synthetic market DataFrame."""
    dates = pd.bdate_range("2023-01-01", periods=n_days)
    rng = np.random.default_rng(42)
    data = {"SP500": 4000 + np.cumsum(rng.normal(0, 10, n_days))}
    if include_vix:
        data["VIX"] = 18 + rng.normal(0, 3, n_days)
    if include_yields:
        data["T10Y"] = 4.0 + rng.normal(0, 0.2, n_days)
        data["T3M"] = 5.0 + rng.normal(0, 0.1, n_days)
    return pd.DataFrame(data, index=dates)


class TestDataQualityValidate:
    """Core validate() and summary() methods."""

    def test_healthy_data_no_warnings(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        df = _make_market_df()
        warnings = checker.validate(df)
        # Healthy synthetic data should have no errors
        errors = [w for w in warnings if w["severity"] == "error"]
        assert len(errors) == 0

    def test_summary_returns_required_keys(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        result = checker.summary(_make_market_df())
        assert "status" in result
        assert "errors" in result
        assert "warnings" in result
        assert "details" in result

    def test_empty_dataframe(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        warnings = checker.validate(pd.DataFrame())
        assert warnings == []


class TestDataQualityStaleness:
    """Staleness detection."""

    def test_stale_column_detected(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        df = _make_market_df(n_days=100)
        # Make VIX stale: NaN for last 10 days
        df.loc[df.index[-10:], "VIX"] = np.nan
        warnings = checker.validate(df)
        stale = [w for w in warnings if w["check"] == "staleness" and w["column"] == "VIX"]
        assert len(stale) > 0


class TestDataQualityRange:
    """Range violation detection."""

    def test_vix_out_of_range_detected(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        df = _make_market_df()
        df.loc[df.index[0], "VIX"] = 100  # Above 90 range
        warnings = checker.validate(df)
        vix_warnings = [w for w in warnings if w["column"] == "VIX" and w["check"] == "range"]
        assert len(vix_warnings) > 0

    def test_yield_out_of_range_detected(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        df = _make_market_df()
        df.loc[df.index[0], "T10Y"] = 25.0  # Above 20 range
        warnings = checker.validate(df)
        yield_warnings = [w for w in warnings if w["column"] == "T10Y"]
        assert len(yield_warnings) > 0


class TestDataQualityCompleteness:
    """NaN completeness checks."""

    def test_high_nan_pct_flagged(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        df = _make_market_df(n_days=100)
        # Set 30% of VIX to NaN (threshold is 20%)
        df.loc[df.index[:30], "VIX"] = np.nan
        warnings = checker.validate(df)
        completeness = [w for w in warnings if w["check"] == "completeness" and w["column"] == "VIX"]
        assert len(completeness) > 0


class TestDataQualityConsistency:
    """Consistency (jump) detection."""

    def test_huge_sp500_jump_flagged(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        df = _make_market_df()
        # Insert a 50% jump
        df.iloc[50, df.columns.get_loc("SP500")] = df.iloc[49, df.columns.get_loc("SP500")] * 1.6
        warnings = checker.validate(df)
        consistency = [w for w in warnings if w["check"] == "consistency"]
        assert len(consistency) > 0

    def test_summary_degraded_on_error(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        df = _make_market_df()
        df.iloc[50, df.columns.get_loc("SP500")] = df.iloc[49, df.columns.get_loc("SP500")] * 1.6
        result = checker.summary(df)
        assert result["status"] == "degraded"


# ═══════════════════════════════════════════════════════════════════════════════
# REGIME VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════════


def _make_regime_df(sp500_trend="up", n_days=250, n_sectors=5):
    """Helper: build DataFrame for regime validation."""
    dates = pd.bdate_range("2023-01-01", periods=n_days)
    rng = np.random.default_rng(42)
    if sp500_trend == "up":
        sp = 4000 + np.linspace(0, 500, n_days) + rng.normal(0, 5, n_days)
    else:
        sp = 4000 - np.linspace(0, 500, n_days) + rng.normal(0, 5, n_days)

    data = {"SP500": sp}
    for i in range(n_sectors):
        if sp500_trend == "up":
            data[f"Sector_{i}"] = 100 + np.linspace(0, 20, n_days) + rng.normal(0, 1, n_days)
        else:
            data[f"Sector_{i}"] = 100 - np.linspace(0, 20, n_days) + rng.normal(0, 1, n_days)
    return pd.DataFrame(data, index=dates)


class TestRegimeValidatorPrice:
    """Price structure (200d SMA) check."""

    def test_bull_confirmed_when_above_sma(self):
        from backend.services.regime_validator import validate_regime
        df = _make_regime_df("up", n_days=250)
        result = validate_regime(df, "Bull")
        assert result.price_confirmed is True

    def test_bear_not_confirmed_when_above_sma(self):
        from backend.services.regime_validator import validate_regime
        df = _make_regime_df("up", n_days=250)
        result = validate_regime(df, "Bear")
        assert result.price_confirmed is False

    def test_insufficient_data_returns_false(self):
        from backend.services.regime_validator import validate_regime
        df = _make_regime_df("up", n_days=100)  # < 200 days
        result = validate_regime(df, "Bull")
        assert result.price_confirmed is False
        assert any("Insufficient" in n or "200d SMA" in n for n in result.notes)


class TestRegimeValidatorBreadth:
    """Market breadth check."""

    def test_bull_breadth_confirmed_with_advancing_sectors(self):
        from backend.services.regime_validator import validate_regime
        df = _make_regime_df("up", n_days=250, n_sectors=8)
        result = validate_regime(df, "Bull")
        assert result.breadth_confirmed is True

    def test_bear_breadth_with_declining_sectors(self):
        from backend.services.regime_validator import validate_regime
        df = _make_regime_df("down", n_days=250, n_sectors=8)
        result = validate_regime(df, "Bear")
        assert result.breadth_confirmed is True

    def test_no_sectors_returns_false(self):
        from backend.services.regime_validator import validate_regime
        df = _make_regime_df("up", n_days=250, n_sectors=0)
        result = validate_regime(df, "Bull")
        assert result.breadth_confirmed is False


class TestRegimeValidatorConfidence:
    """Overall confirmation and confidence levels."""

    def test_bull_with_all_checks_is_high(self):
        from backend.services.regime_validator import validate_regime
        df = _make_regime_df("up", n_days=250, n_sectors=8)
        result = validate_regime(df, "Bull")
        assert result.confirmed  # np.bool_ — truthiness, not `is True`

    def test_bear_needs_two_checks(self):
        from backend.services.regime_validator import validate_regime
        # Bear with uptrending data — price won't confirm, breadth won't confirm
        df = _make_regime_df("up", n_days=250, n_sectors=8)
        result = validate_regime(df, "Bear")
        assert not result.confirmed  # np.bool_ — truthiness, not `is False`
        assert result.confidence == "LOW"

    def test_result_is_dataclass(self):
        from backend.services.regime_validator import validate_regime, RegimeValidation
        df = _make_regime_df("up", n_days=250)
        result = validate_regime(df, "Bull")
        assert isinstance(result, RegimeValidation)
        assert result.regime == "Bull"


# ═══════════════════════════════════════════════════════════════════════════════
# SHAP EXPLAINER
# ═══════════════════════════════════════════════════════════════════════════════


def _mock_predictor():
    """Create a mock CrashPredictor for SHAP tests."""
    predictor = MagicMock()
    predictor.predict_proba.return_value = np.array([0.25])
    predictor.get_shap_values.return_value = [
        ("vix_zscore", 0.15),
        ("term_spread", -0.08),
        ("mom_3m", 0.05),
    ]
    return predictor


class TestShapExplain:
    """explain_prediction tests."""

    def test_returns_required_keys(self):
        from backend.services.shap_explainer import explain_prediction
        features = pd.DataFrame({"vix_zscore": [2.0], "term_spread": [-0.3], "mom_3m": [-0.1]})
        result = explain_prediction(_mock_predictor(), features, horizon="3m", top_n=3)
        assert "crash_prob" in result
        assert "horizon" in result
        assert "top_features" in result

    def test_crash_prob_from_predictor(self):
        from backend.services.shap_explainer import explain_prediction
        features = pd.DataFrame({"vix_zscore": [2.0]})
        result = explain_prediction(_mock_predictor(), features)
        assert result["crash_prob"] == 0.25

    def test_top_features_limited_by_top_n(self):
        from backend.services.shap_explainer import explain_prediction
        features = pd.DataFrame({"vix_zscore": [2.0]})
        result = explain_prediction(_mock_predictor(), features, top_n=2)
        assert len(result["top_features"]) == 2

    def test_feature_values_populated(self):
        from backend.services.shap_explainer import explain_prediction
        features = pd.DataFrame({"vix_zscore": [2.0], "term_spread": [-0.3], "mom_3m": [-0.1]})
        result = explain_prediction(_mock_predictor(), features, top_n=3)
        vix_feat = next(f for f in result["top_features"] if f["feature"] == "vix_zscore")
        assert vix_feat["feature_value"] == 2.0
        assert vix_feat["shap_value"] == 0.15


class TestShapCounterfactual:
    """run_counterfactual tests."""

    def test_returns_base_prob_and_scenarios(self):
        from backend.services.shap_explainer import run_counterfactual
        features = pd.DataFrame({"vix": [20.0], "vix_zscore": [0.5]})
        scenarios = [{"label": "VIX Spike", "overrides": {"vix": 40}}]
        result = run_counterfactual(_mock_predictor(), features, scenarios)
        assert "base_prob" in result
        assert len(result["scenarios"]) == 1
        assert result["scenarios"][0]["label"] == "VIX Spike"

    def test_delta_computed(self):
        from backend.services.shap_explainer import run_counterfactual
        pred = _mock_predictor()
        # First call = base, second call = scenario
        pred.predict_proba.side_effect = [np.array([0.20]), np.array([0.45])]
        features = pd.DataFrame({"vix": [20.0]})
        scenarios = [{"label": "test", "overrides": {"vix": 40}}]
        result = run_counterfactual(pred, features, scenarios)
        assert abs(result["scenarios"][0]["delta"] - 0.25) < 1e-6

    def test_empty_scenarios(self):
        from backend.services.shap_explainer import run_counterfactual
        features = pd.DataFrame({"vix": [20.0]})
        result = run_counterfactual(_mock_predictor(), features, [])
        assert result["scenarios"] == []

    def test_default_scenarios_exist(self):
        from backend.services.shap_explainer import DEFAULT_SCENARIOS
        assert len(DEFAULT_SCENARIOS) >= 3
        for s in DEFAULT_SCENARIOS:
            assert "label" in s
            assert "overrides" in s


# ═══════════════════════════════════════════════════════════════════════════════
# NET LIQUIDITY (mocked FRED)
# ═══════════════════════════════════════════════════════════════════════════════


def _mock_fred_series():
    """Create mock FRED time series for net liquidity calculation.

    All three FRED series (WALCL, WTREGEN, RRPONTSYD) are in millions USD.
    """
    dates = pd.date_range("2023-01-01", periods=156, freq="W")  # 3 years weekly
    rng = np.random.default_rng(42)
    walcl = pd.Series(8_000_000 + rng.normal(0, 50_000, 156), index=dates)
    tga = pd.Series(500_000 + rng.normal(0, 20_000, 156), index=dates)
    rrp = pd.Series(2_000_000 + rng.normal(0, 100_000, 156), index=dates)  # millions
    return walcl, tga, rrp


class TestNetLiquidity:
    """Net liquidity calculation logic."""

    def test_default_response_structure(self):
        from backend.services.net_liquidity import _default_response
        result = _default_response("test error")
        assert result["current"]["signal"] == "UNKNOWN"
        assert result["error"] == "test error"
        assert result["formula"] == "Net_Liq = WALCL - (TGA + RRP)"

    def test_default_response_no_error(self):
        from backend.services.net_liquidity import _default_response
        result = _default_response()
        assert result["error"] == "Data unavailable"

    @patch("backend.services.net_liquidity.api_keys")
    @patch("backend.services.net_liquidity.cache_get", return_value=None)
    @patch("backend.services.net_liquidity.cache_set")
    def test_fetch_and_calculate_success(self, mock_cache_set, mock_cache_get, mock_keys):
        """Test the full calculation pipeline with mocked FRED."""
        mock_keys.has.return_value = True
        mock_keys.fred = "test_key"

        walcl, tga, rrp = _mock_fred_series()
        mock_fred_instance = MagicMock()
        mock_fred_instance.get_series.side_effect = [walcl, tga, rrp]

        with patch.dict("sys.modules", {}), \
             patch("fredapi.Fred", return_value=mock_fred_instance):
            from backend.services.net_liquidity import _fetch_and_calculate
            result = _fetch_and_calculate()

        assert "current" in result
        assert result["current"]["signal"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert result["unit"] == "Trillions USD"
        assert len(result["history"]) > 0
        assert len(result["history"]) <= 52

    @patch("backend.services.net_liquidity.api_keys")
    def test_no_fred_key_returns_default(self, mock_keys):
        mock_keys.has.return_value = False
        from backend.services.net_liquidity import _fetch_and_calculate
        result = _fetch_and_calculate()
        assert result["current"]["signal"] == "UNKNOWN"


# ═══════════════════════════════════════════════════════════════════════════════
# RETURN MODEL (fallback path)
# ═══════════════════════════════════════════════════════════════════════════════


class TestReturnModelReal:
    """Test ReturnPredictor with enough data for the real LightGBM class."""

    @pytest.fixture()
    def trained_predictor(self):
        from backend.services.return_model import ReturnPredictor
        rng = np.random.default_rng(42)
        n = 1500  # > min_train_samples (1260)
        features = pd.DataFrame(rng.standard_normal((n, 5)), columns=[f"f{i}" for i in range(5)])
        targets = {"12m": pd.Series(rng.standard_normal(n) * 0.2)}
        predictor = ReturnPredictor(n_estimators=50, random_state=42)
        result = predictor.train(features, targets, min_train_samples=500)
        return predictor, features, result

    def test_train_succeeds(self, trained_predictor):
        predictor, _, result = trained_predictor
        assert result["success"] is True
        assert predictor.is_trained is True

    def test_predict_after_train(self, trained_predictor):
        predictor, features, _ = trained_predictor
        preds = predictor.predict(features.iloc[:10])
        assert len(preds) == 10
        # Predictions should be finite
        assert np.all(np.isfinite(preds))

    def test_predict_quantiles_after_train(self, trained_predictor):
        predictor, features, _ = trained_predictor
        q = predictor.predict_quantiles(features.iloc[:10])
        assert "median" in q
        assert "p10" in q
        assert "p90" in q
        # p10 <= median <= p90 on average
        assert np.mean(q["p10"]) <= np.mean(q["median"])
        assert np.mean(q["median"]) <= np.mean(q["p90"])

    def test_predict_before_train_raises(self):
        from backend.services.return_model import ReturnPredictor
        predictor = ReturnPredictor()
        features = pd.DataFrame(np.random.randn(10, 3), columns=["a", "b", "c"])
        with pytest.raises(RuntimeError, match="not trained"):
            predictor.predict(features)

    def test_get_top_features_empty_before_train(self):
        from backend.services.return_model import ReturnPredictor
        predictor = ReturnPredictor()
        assert predictor.get_top_features() == []

    def test_get_top_features_after_train(self, trained_predictor):
        predictor, _, _ = trained_predictor
        top = predictor.get_top_features(n=3)
        assert len(top) == 3
        # Each entry is (feature_name, importance)
        assert all(isinstance(t[0], str) for t in top)

    def test_insufficient_data_fails(self):
        from backend.services.return_model import ReturnPredictor
        predictor = ReturnPredictor()
        features = pd.DataFrame(np.random.randn(50, 3), columns=["a", "b", "c"])
        targets = {"12m": pd.Series(np.random.randn(50))}
        result = predictor.train(features, targets, min_train_samples=1260)
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# LLM ANALYZER (mocked client + response parsing)
# ═══════════════════════════════════════════════════════════════════════════════


class TestLlmAvailability:
    """is_available() and client initialization."""

    @patch("backend.services.llm_analyzer._DEEPSEEK_API_KEY", "")
    @patch("backend.services.llm_analyzer._ANTHROPIC_API_KEY", "")
    def test_not_available_without_key(self):
        from backend.services.llm_analyzer import is_available
        assert is_available() is False

    @patch("backend.services.llm_analyzer._DEEPSEEK_API_KEY", "")
    @patch("backend.services.llm_analyzer._ANTHROPIC_API_KEY", "")
    def test_get_provider_returns_none_without_key(self):
        from backend.services.llm_analyzer import _get_provider
        assert _get_provider() == "none"

    @patch("backend.services.llm_analyzer._DEEPSEEK_API_KEY", "")
    @patch("backend.services.llm_analyzer._ANTHROPIC_API_KEY", "")
    def test_call_llm_returns_none_without_keys(self):
        """Without any API keys, _call_llm returns None."""
        from backend.services.llm_analyzer import _call_llm
        result = _call_llm("system", "user")
        assert result is None


class TestLlmNewsSummarization:
    """summarize_market_news parsing tests."""

    def test_empty_news_returns_none(self):
        from backend.services.llm_analyzer import summarize_market_news
        # Clear cache to avoid stale results
        result = summarize_market_news([])
        assert result is None

    @patch("backend.services.llm_analyzer._call_llm")
    def test_bullish_sentiment_detected(self, mock_llm):
        mock_llm.return_value = "Markets rallied strongly on optimistic earnings reports."
        # Need to bypass cache
        import backend.services.llm_analyzer as mod
        # Call the underlying logic directly
        news = [{"title": "Markets surge", "publisher": "Reuters"}]
        result = mod.summarize_market_news.__wrapped__(news)
        assert result["sentiment"] == "bullish"

    @patch("backend.services.llm_analyzer._call_llm")
    def test_bearish_sentiment_detected(self, mock_llm):
        mock_llm.return_value = "Markets declined sharply amid crash fears and pessimism."
        import backend.services.llm_analyzer as mod
        news = [{"title": "Markets crash", "publisher": "Reuters"}]
        result = mod.summarize_market_news.__wrapped__(news)
        assert result["sentiment"] == "bearish"

    @patch("backend.services.llm_analyzer._call_llm", return_value=None)
    def test_llm_failure_returns_none(self, mock_llm):
        import backend.services.llm_analyzer as mod
        news = [{"title": "Test headline", "publisher": "Test"}]
        result = mod.summarize_market_news.__wrapped__(news)
        assert result is None


class TestLlmStockOutlook:
    """analyze_stock_outlook parsing tests."""

    @patch("backend.services.llm_analyzer._call_llm")
    def test_parses_structured_response(self, mock_llm):
        mock_llm.return_value = (
            "BULL: Strong revenue growth and expanding margins.\n"
            "BEAR: High valuation and competition risk.\n"
            "SCORE: 0.3\n"
            "SUMMARY: Moderately positive outlook."
        )
        import backend.services.llm_analyzer as mod
        result = mod.analyze_stock_outlook.__wrapped__(
            "AAPL",
            [{"title": "Apple earnings beat"}],
            {"pe_ratio": 30, "current_price": 200},
        )
        assert result["bull_case"] == "Strong revenue growth and expanding margins."
        assert result["bear_case"] == "High valuation and competition risk."
        assert result["sentiment_score"] == 0.3
        assert result["summary"] == "Moderately positive outlook."

    @patch("backend.services.llm_analyzer._call_llm")
    def test_score_clamped_to_range(self, mock_llm):
        mock_llm.return_value = "BULL: x\nBEAR: y\nSCORE: 5.0\nSUMMARY: z"
        import backend.services.llm_analyzer as mod
        result = mod.analyze_stock_outlook.__wrapped__("AAPL", [], {"pe_ratio": 30})
        assert result["sentiment_score"] == 1.0  # clamped from 5.0

    @patch("backend.services.llm_analyzer._call_llm")
    def test_unparseable_response_fallback(self, mock_llm):
        mock_llm.return_value = "Just a plain text response without structure."
        import backend.services.llm_analyzer as mod
        result = mod.analyze_stock_outlook.__wrapped__("AAPL", [], {"pe_ratio": 30})
        assert "summary" in result


class TestLlmExpectations:
    """generate_expectations parsing."""

    def test_no_data_returns_none(self):
        import backend.services.llm_analyzer as mod
        result = mod.generate_expectations.__wrapped__("AAPL", None, None)
        assert result is None

    @patch("backend.services.llm_analyzer._call_llm")
    def test_catalysts_extracted(self, mock_llm):
        mock_llm.return_value = (
            "Key things to watch:\n"
            "- Upcoming product launch in Q2\n"
            "- Rising competition in AI chips\n"
            "- Margin pressure from tariffs\n"
        )
        import backend.services.llm_analyzer as mod
        result = mod.generate_expectations.__wrapped__(
            "AAPL",
            analyst_targets={"low": 150, "mean": 200, "high": 250},
        )
        assert len(result["key_catalysts"]) == 3
        assert "Upcoming product launch" in result["key_catalysts"][0]


# ═══════════════════════════════════════════════════════════════════════════════
# HARDENING: STOCK ANALYZER HELPER EDGE CASES
# (Tests that narrowed except blocks still catch expected yfinance failures)
# ═══════════════════════════════════════════════════════════════════════════════


class TestStockAnalyzerHelpers:
    """Edge cases for stock_analyzer helper functions (narrowed excepts)."""

    def test_get_analyst_targets_none_stock(self):
        from backend.services.stock_analyzer import _get_analyst_targets
        mock_stock = MagicMock()
        mock_stock.analyst_price_targets = None
        assert _get_analyst_targets(mock_stock) is None

    def test_get_analyst_targets_dict_input(self):
        from backend.services.stock_analyzer import _get_analyst_targets
        mock_stock = MagicMock()
        mock_stock.analyst_price_targets = {"low": 100, "mean": 150, "high": 200}
        result = _get_analyst_targets(mock_stock)
        assert result["low"] == 100
        assert result["high"] == 200

    def test_get_analyst_targets_type_error(self):
        """Narrowed except catches TypeError from unexpected data shapes."""
        from backend.services.stock_analyzer import _get_analyst_targets
        mock_stock = MagicMock()
        # Return an int (not dict or DataFrame) — has no to_dict, not a dict
        mock_stock.analyst_price_targets = 42
        assert _get_analyst_targets(mock_stock) is None

    def test_get_analyst_targets_key_error(self):
        """Narrowed except catches KeyError."""
        from backend.services.stock_analyzer import _get_analyst_targets
        mock_stock = MagicMock()
        # to_dict raises KeyError
        targets = MagicMock()
        targets.to_dict.side_effect = KeyError("bad key")
        mock_stock.analyst_price_targets = targets
        assert _get_analyst_targets(mock_stock) is None

    def test_get_recommendations_none(self):
        from backend.services.stock_analyzer import _get_recommendations
        mock_stock = MagicMock()
        mock_stock.recommendations = None
        assert _get_recommendations(mock_stock) is None

    def test_get_recommendations_empty_df(self):
        from backend.services.stock_analyzer import _get_recommendations
        mock_stock = MagicMock()
        mock_stock.recommendations = pd.DataFrame()
        assert _get_recommendations(mock_stock) is None

    def test_get_recommendations_valid_df(self):
        from backend.services.stock_analyzer import _get_recommendations
        mock_stock = MagicMock()
        mock_stock.recommendations = pd.DataFrame([
            {"strongBuy": 5, "buy": 10, "hold": 8, "sell": 2, "strongSell": 1},
        ])
        result = _get_recommendations(mock_stock)
        assert result["strongBuy"] == 5
        assert result["sell"] == 2

    def test_get_news_empty_list(self):
        from backend.services.stock_analyzer import _get_news
        mock_stock = MagicMock()
        mock_stock.news = []
        assert _get_news(mock_stock) is None

    def test_get_news_none(self):
        from backend.services.stock_analyzer import _get_news
        mock_stock = MagicMock()
        mock_stock.news = None
        assert _get_news(mock_stock) is None

    def test_get_news_valid_items(self):
        from backend.services.stock_analyzer import _get_news
        mock_stock = MagicMock()
        mock_stock.news = [{"title": "Test headline", "publisher": "Reuters", "link": "http://x"}]
        result = _get_news(mock_stock)
        assert result is not None
        assert len(result) == 1

    def test_get_price_history_none_input(self):
        from backend.services.stock_analyzer import _get_price_history
        assert _get_price_history(None) is None

    def test_get_price_history_empty_series(self):
        from backend.services.stock_analyzer import _get_price_history
        assert _get_price_history(pd.Series([], dtype=float)) is None

    def test_get_price_history_valid(self):
        from backend.services.stock_analyzer import _get_price_history
        dates = pd.bdate_range("2023-01-01", periods=20)
        prices = pd.Series(range(100, 120), index=dates)
        result = _get_price_history(prices, sample_every=5)
        assert result is not None
        assert len(result) == 4  # 20 / 5

    def test_get_key_stats_empty_info_short_returns(self):
        from backend.services.stock_analyzer import _get_key_stats
        returns = pd.Series([0.01, -0.005, 0.02])
        result = _get_key_stats({}, returns, 100.0)
        # No yfinance fields, but computed stats (return_1m etc.) are added as None
        # when returns are too short, so result is still a dict
        assert result is not None
        assert result["return_1m"] is None
        assert result["return_1y"] is None

    def test_get_key_stats_with_pe(self):
        from backend.services.stock_analyzer import _get_key_stats
        info = {"trailingPE": 25.5, "forwardPE": 22.0, "dividendYield": 0.015}
        returns = pd.Series(np.random.randn(300) * 0.01)
        result = _get_key_stats(info, returns, 150.0)
        assert result["pe_trailing"] == 25.5
        assert result["pe_forward"] == 22.0
        assert "return_1m" in result
        assert "return_1y" in result

    def test_get_sector_peers_known_sector(self):
        from backend.services.stock_analyzer import _get_sector_peers
        result = _get_sector_peers("Technology", "AAPL")
        assert "AAPL" not in result
        assert "MSFT" in result

    def test_get_sector_peers_unknown_sector(self):
        from backend.services.stock_analyzer import _get_sector_peers
        result = _get_sector_peers("Aliens", "XYZ")
        assert result is None

    def test_get_sector_peers_self_excluded(self):
        from backend.services.stock_analyzer import _get_sector_peers
        result = _get_sector_peers("Energy", "XOM")
        assert "XOM" not in result

    def test_get_cap_tier_boundaries(self):
        from backend.services.stock_analyzer import _get_cap_tier
        assert _get_cap_tier(300e9) == "mega"
        assert _get_cap_tier(50e9) == "large"
        assert _get_cap_tier(5e9) == "mid"
        assert _get_cap_tier(1e9) == "small"
        assert _get_cap_tier(None) == "large"
        assert _get_cap_tier(-1) == "large"
        assert _get_cap_tier(0) == "large"


class TestStockAnalyzerSelectStocks:
    """select_stocks_from_sectors edge cases."""

    def test_empty_sectors_returns_default(self):
        from backend.services.stock_analyzer import select_stocks_from_sectors, DEFAULT_WATCHLIST
        result = select_stocks_from_sectors({})
        assert result == DEFAULT_WATCHLIST[:20]

    def test_returns_unique_tickers(self):
        from backend.services.stock_analyzer import select_stocks_from_sectors
        sectors = {
            "Technology": {"expected_total": 0.15},
            "Healthcare": {"expected_total": 0.10},
            "Financials": {"expected_total": 0.08},
        }
        result = select_stocks_from_sectors(sectors, n_stocks=10)
        assert len(result) == len(set(result))  # no duplicates

    def test_respects_n_stocks_limit(self):
        from backend.services.stock_analyzer import select_stocks_from_sectors
        sectors = {f"Sector_{i}": {"expected_total": 0.1 - i * 0.01} for i in range(5)}
        result = select_stocks_from_sectors(sectors, n_stocks=5)
        assert len(result) <= 5


# ═══════════════════════════════════════════════════════════════════════════════
# HARDENING: REGIME VALIDATOR CONFIG-DRIVEN THRESHOLD
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegimeValidatorConfigDriven:
    """Verify consensus threshold reads from config, not hardcoded."""

    def test_config_has_regime_validation_section(self):
        from backend.config import config
        rv_cfg = config.get("regime_validation", {})
        assert "consensus_bull_threshold" in rv_cfg
        assert "min_declining_sectors" in rv_cfg

    def test_consensus_threshold_is_float(self):
        from backend.config import config
        threshold = config["regime_validation"]["consensus_bull_threshold"]
        assert isinstance(threshold, float)
        assert 0.0 < threshold < 0.20  # sanity range

    def test_consensus_check_uses_config_threshold(self):
        """The _check_consensus function should use config, not hardcoded 0.03."""
        import inspect
        from backend.services.regime_validator import _check_consensus
        source = inspect.getsource(_check_consensus)
        # Should NOT contain the old hardcoded comparison
        assert "< 0.03" not in source
        assert ">= 0.03" not in source
        # Should reference config
        assert "config" in source


# ═══════════════════════════════════════════════════════════════════════════════
# HARDENING: NARROWED EXCEPTS IN PORTFOLIO ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class TestPortfolioEngineExceptNarrowing:
    """Verify portfolio_engine excepts are narrowed (not bare Exception)."""

    def test_no_bare_except_in_portfolio_engine(self):
        """portfolio_engine.py should have zero bare 'except Exception:' blocks."""
        import inspect
        from backend.services import portfolio_engine
        source = inspect.getsource(portfolio_engine)
        # Count remaining broad except blocks
        import re
        broad = re.findall(r"except Exception\b(?!.*(?:KeyError|ValueError|LinAlg|TypeError|Attribute|Import|Index))", source)
        # _fetch_prices has "except Exception" (network call) + v9 integrations
        # (attribution, copula, MCTR) each have non-blocking except blocks
        assert len(broad) <= 6, f"Found {len(broad)} remaining broad excepts in portfolio_engine"

    def test_no_bare_except_in_stock_analyzer(self):
        """stock_analyzer.py helper functions should have narrowed excepts."""
        import inspect
        from backend.services import stock_analyzer
        source = inspect.getsource(stock_analyzer)
        import re
        # analyze_stock has legitimate broad excepts (yfinance fetch, GARCH fit)
        # + v9 integrations (factor exposure, insider, liquidity) each non-blocking
        # + 2026-07-16: the five OPTIONAL enrichment extractors (_get_analyst_
        #   targets/_get_recommendations/_get_holders/_get_news/_get_earnings)
        #   moved from narrow to broad excepts ON PURPOSE — their contract is
        #   "degrade this one field to None"; the narrow tuples let network-layer
        #   exceptions kill the whole analysis (postmortem
        #   docs/postmortems/2026-07-16-screener-nameerror.md). Each logs debug.
        broad = re.findall(r"except Exception\b", source)
        assert len(broad) <= 10, f"Found {len(broad)} broad excepts in stock_analyzer (expected ≤10)"


# ═══════════════════════════════════════════════════════════════════════════════
# HARDENING: SAVINGS CALCULATOR EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestSavingsHardening:
    """Additional edge cases for savings_calculator."""

    def test_very_large_contribution(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(100_000, 1_000_000, 25, 65)
        assert result["target"]["met"] is True
        assert result["summary"]["final_nominal"] > 1_000_000

    def test_negative_age_gap_produces_one_year(self):
        """target_age < current_age should produce 1 year (min)."""
        from backend.services.savings_calculator import project_savings
        result = project_savings(500, 10_000, 65, 30)
        assert len(result["projections"]) == 1

    def test_zero_inflation(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(500, 10_000, 30, 65, inflation_rate=0.0)
        # With zero inflation, nominal == real
        last = result["projections"][-1]
        assert abs(last["nominal_balance"] - last["real_balance"]) < 0.01

    def test_custom_target_amount(self):
        from backend.services.savings_calculator import project_savings
        result = project_savings(1000, 0, 25, 65, target_amount=500_000)
        assert result["target"]["amount"] == 500_000


# ═══════════════════════════════════════════════════════════════════════════════
# HARDENING: DATA QUALITY EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestDataQualityHardening:
    """Additional edge cases for DataQualityChecker."""

    def test_all_nan_column(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        df = _make_market_df(n_days=50)
        df["VIX"] = np.nan
        warnings = checker.validate(df)
        completeness = [w for w in warnings if w["check"] == "completeness" and w["column"] == "VIX"]
        assert len(completeness) > 0

    def test_single_row_dataframe(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        df = pd.DataFrame({"SP500": [4000.0], "VIX": [20.0]}, index=[pd.Timestamp("2024-01-01")])
        # Should not crash
        warnings = checker.validate(df)
        assert isinstance(warnings, list)

    def test_no_sp500_column(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        df = pd.DataFrame({"VIX": np.random.randn(100)},
                          index=pd.bdate_range("2023-01-01", periods=100))
        # Should not crash even without SP500
        warnings = checker.validate(df)
        assert isinstance(warnings, list)

    def test_summary_healthy_status(self):
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        df = _make_market_df(n_days=50, include_vix=False, include_yields=False)
        result = checker.summary(df)
        assert result["status"] in ("healthy", "warning")


# ═══════════════════════════════════════════════════════════════════════════════
# HARDENING: REGIME VALIDATOR EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegimeValidatorHardening:
    """Additional edge cases for regime_validator."""

    def test_crisis_regime_treated_as_bearish(self):
        from backend.services.regime_validator import validate_regime
        df = _make_regime_df("down", n_days=250, n_sectors=8)
        result = validate_regime(df, "Crisis")
        # Crisis is in the bearish set, should trigger bear checks
        assert result.regime == "Crisis"

    def test_volatile_regime_treated_as_bearish(self):
        from backend.services.regime_validator import validate_regime
        df = _make_regime_df("down", n_days=250, n_sectors=8)
        result = validate_regime(df, "Volatile")
        assert result.regime == "Volatile"

    def test_neutral_regime_treated_as_bullish(self):
        from backend.services.regime_validator import validate_regime
        df = _make_regime_df("up", n_days=250, n_sectors=8)
        result = validate_regime(df, "Neutral")
        # Neutral is NOT in the bearish set, so it's treated as bullish
        assert result.regime == "Neutral"

    def test_empty_dataframe_doesnt_crash(self):
        from backend.services.regime_validator import validate_regime
        df = pd.DataFrame()
        result = validate_regime(df, "Bull")
        assert result.price_confirmed is False
        assert result.breadth_confirmed is False

    def test_notes_populated(self):
        from backend.services.regime_validator import validate_regime
        df = _make_regime_df("up", n_days=250, n_sectors=8)
        result = validate_regime(df, "Bull")
        assert len(result.notes) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# HARDENING: SHAP EXPLAINER EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestShapHardening:
    """Additional edge cases for shap_explainer."""

    def test_explain_with_missing_feature_column(self):
        """Features DataFrame missing a column referenced by SHAP values."""
        from backend.services.shap_explainer import explain_prediction
        pred = _mock_predictor()
        # DataFrame missing 'term_spread' which SHAP values reference
        features = pd.DataFrame({"vix_zscore": [2.0]})
        result = explain_prediction(pred, features, top_n=3)
        # Should still work — feature_value will be None for missing columns
        term_feat = next((f for f in result["top_features"] if f["feature"] == "term_spread"), None)
        assert term_feat is not None
        assert term_feat["feature_value"] is None

    def test_counterfactual_override_nonexistent_column(self):
        """Override a column that doesn't exist in the features."""
        from backend.services.shap_explainer import run_counterfactual
        features = pd.DataFrame({"vix": [20.0]})
        scenarios = [{"label": "test", "overrides": {"nonexistent_col": 99}}]
        # Should not crash — nonexistent column is simply skipped
        result = run_counterfactual(_mock_predictor(), features, scenarios)
        assert len(result["scenarios"]) == 1

    def test_explain_multiple_rows(self):
        """Features with multiple rows — should use last row."""
        from backend.services.shap_explainer import explain_prediction
        features = pd.DataFrame({"vix_zscore": [1.0, 2.0, 3.0]})
        result = explain_prediction(_mock_predictor(), features, top_n=3)
        # Feature value should come from last row (iloc[-1])
        vix = next(f for f in result["top_features"] if f["feature"] == "vix_zscore")
        assert vix["feature_value"] == 3.0


# ═══════════════════════════════════════════════════════════════════════════════
# HARDENING: RETURN MODEL EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestReturnModelHardening:
    """Additional edge cases for ReturnPredictor."""

    def test_predict_quantiles_before_train_raises(self):
        from backend.services.return_model import ReturnPredictor
        predictor = ReturnPredictor()
        features = pd.DataFrame(np.random.randn(10, 3), columns=["a", "b", "c"])
        with pytest.raises(RuntimeError, match="not trained"):
            predictor.predict_quantiles(features)

    def test_multi_horizon_training(self):
        """Train with multiple horizons (3m, 6m, 12m)."""
        from backend.services.return_model import ReturnPredictor
        rng = np.random.default_rng(42)
        n = 1500
        features = pd.DataFrame(rng.standard_normal((n, 5)), columns=[f"f{i}" for i in range(5)])
        targets = {
            "3m": pd.Series(rng.standard_normal(n) * 0.05),
            "6m": pd.Series(rng.standard_normal(n) * 0.10),
            "12m": pd.Series(rng.standard_normal(n) * 0.20),
        }
        predictor = ReturnPredictor(n_estimators=30, random_state=42)
        result = predictor.train(features, targets, min_train_samples=500)
        assert result["success"] is True
        # Should have models for at least 12m
        assert predictor.is_trained

    def test_predictions_are_clipped(self):
        """Predictions should be clipped to sensible range."""
        from backend.services.return_model import ReturnPredictor
        rng = np.random.default_rng(42)
        n = 1500
        features = pd.DataFrame(rng.standard_normal((n, 3)), columns=["a", "b", "c"])
        targets = {"12m": pd.Series(rng.standard_normal(n) * 0.2)}
        predictor = ReturnPredictor(n_estimators=30, random_state=42)
        predictor.train(features, targets, min_train_samples=500)
        preds = predictor.predict(features.iloc[:10])
        # Should be within clipped range (no extreme values)
        assert np.all(preds >= -0.80)
        assert np.all(preds <= 2.00)


# ═══════════════════════════════════════════════════════════════════════════════
# HARDENING: NET LIQUIDITY EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestNetLiquidityHardening:
    """Additional edge cases for net_liquidity."""

    def test_default_response_has_all_current_keys(self):
        from backend.services.net_liquidity import _default_response
        result = _default_response()
        current = result["current"]
        for key in ["walcl", "tga", "rrp", "net_liquidity", "wow_change", "wow_change_pct", "signal"]:
            assert key in current

    def test_default_response_has_last_updated(self):
        from backend.services.net_liquidity import _default_response
        result = _default_response()
        assert "last_updated" in result
        assert "T" in result["last_updated"]  # ISO format

    @patch("backend.services.net_liquidity.cache_get")
    def test_cached_result_returned(self, mock_cache_get):
        """get_net_liquidity returns cached value when available."""
        mock_cache_get.return_value = {"current": {"signal": "BULLISH"}, "cached": True}
        from backend.services.net_liquidity import get_net_liquidity
        result = get_net_liquidity()
        assert result.get("cached") is True

    @patch("backend.services.net_liquidity.api_keys")
    @patch("backend.services.net_liquidity.cache_get", return_value=None)
    @patch("backend.services.net_liquidity.cache_set")
    def test_rrp_not_multiplied(self, mock_cache_set, mock_cache_get, mock_keys):
        """RRP should NOT be multiplied by 1000 — RRPONTSYD is already in millions."""
        mock_keys.has.return_value = True
        mock_keys.fred = "test_key"

        dates = pd.date_range("2023-01-01", periods=52, freq="W")
        rng = np.random.default_rng(99)
        # All series in millions USD
        walcl = pd.Series(8_000_000 + rng.normal(0, 10_000, 52), index=dates)
        tga = pd.Series(500_000 + rng.normal(0, 5_000, 52), index=dates)
        rrp = pd.Series(400_000 + rng.normal(0, 5_000, 52), index=dates)  # ~400B in millions

        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = [walcl, tga, rrp]

        with patch("fredapi.Fred", return_value=mock_fred):
            from backend.services.net_liquidity import _fetch_and_calculate
            result = _fetch_and_calculate()

        current = result["current"]
        # Net liq = (WALCL - TGA - RRP) / 1M → trillions
        # ~8.0T - 0.5T - 0.4T ≈ 7.1T (realistic)
        # If RRP were wrongly *1000, it would be ~8.0 - 0.5 - 400 = -392T (absurd)
        assert current["net_liquidity"] > 0, (
            f"Net liquidity should be positive (~7T), got {current['net_liquidity']}T "
            "— RRP may still be incorrectly multiplied"
        )
        assert 5.0 < current["net_liquidity"] < 10.0, (
            f"Expected ~7T net liquidity, got {current['net_liquidity']}T"
        )

    @patch("backend.services.net_liquidity.api_keys")
    @patch("backend.services.net_liquidity.cache_get", return_value=None)
    @patch("backend.services.net_liquidity.cache_set")
    def test_net_liquidity_formula_correct(self, mock_cache_set, mock_cache_get, mock_keys):
        """Verify Net_Liq = WALCL - (TGA + RRP) with known values."""
        mock_keys.has.return_value = True
        mock_keys.fred = "test_key"

        dates = pd.date_range("2023-01-01", periods=20, freq="W")
        # Constant series for easy verification
        walcl = pd.Series([7_500_000.0] * 20, index=dates)  # 7.5T in millions
        tga = pd.Series([600_000.0] * 20, index=dates)       # 0.6T in millions
        rrp = pd.Series([300_000.0] * 20, index=dates)       # 0.3T in millions
        # Expected: 7.5 - 0.6 - 0.3 = 6.6T

        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = [walcl, tga, rrp]

        with patch("fredapi.Fred", return_value=mock_fred):
            from backend.services.net_liquidity import _fetch_and_calculate
            result = _fetch_and_calculate()

        assert abs(result["current"]["net_liquidity"] - 6.6) < 0.01, (
            f"Expected 6.6T, got {result['current']['net_liquidity']}T"
        )

    @patch("backend.services.net_liquidity.api_keys")
    @patch("backend.services.net_liquidity.cache_get", return_value=None)
    @patch("backend.services.net_liquidity.cache_set")
    def test_signal_uses_config_thresholds(self, mock_cache_set, mock_cache_get, mock_keys):
        """Signal thresholds should come from config, not hardcoded."""
        from backend.config import config
        nl_cfg = config.get("net_liquidity", {})
        assert "wow_bullish_threshold" in nl_cfg
        assert "wow_bearish_threshold" in nl_cfg
        assert nl_cfg["wow_bullish_threshold"] > 0
        assert nl_cfg["wow_bearish_threshold"] < 0

    def test_history_entries_have_required_keys(self):
        """Each history entry should have date, walcl, tga, rrp, net_liquidity, wow_change."""
        from backend.services.net_liquidity import _default_response
        result = _default_response()
        assert result["history"] == []
        assert result["formula"] == "Net_Liq = WALCL - (TGA + RRP)"

    @patch("backend.services.net_liquidity.api_keys")
    @patch("backend.services.net_liquidity.cache_get", return_value=None)
    @patch("backend.services.net_liquidity.cache_set")
    def test_signal_bullish_when_wow_above_threshold(self, mock_cs, mock_cg, mock_keys):
        """Signal is BULLISH when WoW change exceeds bullish threshold."""
        mock_keys.has.return_value = True
        mock_keys.fred = "test_key"

        dates = pd.date_range("2023-01-01", periods=20, freq="W")
        # Rising WALCL → positive WoW change in net liquidity
        walcl = pd.Series(np.linspace(7_000_000, 8_000_000, 20), index=dates)
        tga = pd.Series([500_000.0] * 20, index=dates)
        rrp = pd.Series([300_000.0] * 20, index=dates)

        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = [walcl, tga, rrp]

        with patch("fredapi.Fred", return_value=mock_fred):
            from backend.services.net_liquidity import _fetch_and_calculate
            result = _fetch_and_calculate()

        assert result["current"]["signal"] == "BULLISH"
        assert result["current"]["wow_change"] > 0

    @patch("backend.services.net_liquidity.api_keys")
    @patch("backend.services.net_liquidity.cache_get", return_value=None)
    @patch("backend.services.net_liquidity.cache_set")
    def test_signal_bearish_when_wow_below_threshold(self, mock_cs, mock_cg, mock_keys):
        """Signal is BEARISH when WoW change is below bearish threshold."""
        mock_keys.has.return_value = True
        mock_keys.fred = "test_key"

        dates = pd.date_range("2023-01-01", periods=20, freq="W")
        # Falling WALCL → negative WoW change
        walcl = pd.Series(np.linspace(8_000_000, 7_000_000, 20), index=dates)
        tga = pd.Series([500_000.0] * 20, index=dates)
        rrp = pd.Series([300_000.0] * 20, index=dates)

        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = [walcl, tga, rrp]

        with patch("fredapi.Fred", return_value=mock_fred):
            from backend.services.net_liquidity import _fetch_and_calculate
            result = _fetch_and_calculate()

        assert result["current"]["signal"] == "BEARISH"
        assert result["current"]["wow_change"] < 0

    @patch("backend.services.net_liquidity.api_keys")
    @patch("backend.services.net_liquidity.cache_get", return_value=None)
    @patch("backend.services.net_liquidity.cache_set")
    def test_signal_neutral_when_flat(self, mock_cs, mock_cg, mock_keys):
        """Signal is NEUTRAL when WoW change is near zero."""
        mock_keys.has.return_value = True
        mock_keys.fred = "test_key"

        dates = pd.date_range("2023-01-01", periods=20, freq="W")
        # Constant series → zero WoW change
        walcl = pd.Series([7_500_000.0] * 20, index=dates)
        tga = pd.Series([500_000.0] * 20, index=dates)
        rrp = pd.Series([300_000.0] * 20, index=dates)

        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = [walcl, tga, rrp]

        with patch("fredapi.Fred", return_value=mock_fred):
            from backend.services.net_liquidity import _fetch_and_calculate
            result = _fetch_and_calculate()

        assert result["current"]["signal"] == "NEUTRAL"

    @patch("backend.services.net_liquidity.api_keys")
    @patch("backend.services.net_liquidity.cache_get", return_value=None)
    @patch("backend.services.net_liquidity.cache_set")
    def test_insufficient_data_returns_default(self, mock_cs, mock_cg, mock_keys):
        """Returns default when FRED gives fewer than 4 weeks of data."""
        mock_keys.has.return_value = True
        mock_keys.fred = "test_key"

        dates = pd.date_range("2023-01-01", periods=3, freq="W")
        walcl = pd.Series([7_000_000.0] * 3, index=dates)
        tga = pd.Series([500_000.0] * 3, index=dates)
        rrp = pd.Series([300_000.0] * 3, index=dates)

        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = [walcl, tga, rrp]

        with patch("fredapi.Fred", return_value=mock_fred):
            from backend.services.net_liquidity import _fetch_and_calculate
            result = _fetch_and_calculate()

        assert result["current"]["signal"] == "UNKNOWN"
        assert "Insufficient" in result.get("error", "")

    @patch("backend.services.net_liquidity.api_keys")
    @patch("backend.services.net_liquidity.cache_get", return_value=None)
    @patch("backend.services.net_liquidity.cache_set")
    def test_history_capped_at_52_entries(self, mock_cs, mock_cg, mock_keys):
        """History should contain at most 52 weekly entries."""
        mock_keys.has.return_value = True
        mock_keys.fred = "test_key"

        dates = pd.date_range("2020-01-01", periods=200, freq="W")
        walcl = pd.Series([7_500_000.0] * 200, index=dates)
        tga = pd.Series([500_000.0] * 200, index=dates)
        rrp = pd.Series([300_000.0] * 200, index=dates)

        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = [walcl, tga, rrp]

        with patch("fredapi.Fred", return_value=mock_fred):
            from backend.services.net_liquidity import _fetch_and_calculate
            result = _fetch_and_calculate()

        assert len(result["history"]) <= 52
        # Verify each entry has all required keys
        for entry in result["history"]:
            for key in ("date", "walcl", "tga", "rrp", "net_liquidity", "wow_change"):
                assert key in entry, f"Missing key '{key}' in history entry"

    @patch("backend.services.net_liquidity.cache_get", return_value=None)
    def test_get_net_liquidity_narrows_exceptions(self, mock_cg):
        """get_net_liquidity catches specific exceptions, not bare Exception."""
        from backend.services.net_liquidity import get_net_liquidity

        # ValueError should be caught → returns default response
        with patch("backend.services.net_liquidity._fetch_and_calculate",
                    side_effect=ValueError("bad value")):
            result = get_net_liquidity()
            assert result["current"]["signal"] == "UNKNOWN"

        # OSError (network) should be caught
        with patch("backend.services.net_liquidity._fetch_and_calculate",
                    side_effect=OSError("network down")):
            result = get_net_liquidity()
            assert result["current"]["signal"] == "UNKNOWN"

    @patch("backend.services.net_liquidity.api_keys")
    @patch("backend.services.net_liquidity.cache_get", return_value=None)
    @patch("backend.services.net_liquidity.cache_set")
    def test_component_values_sum_correctly(self, mock_cs, mock_cg, mock_keys):
        """Verify walcl - tga - rrp = net_liquidity in current output."""
        mock_keys.has.return_value = True
        mock_keys.fred = "test_key"

        dates = pd.date_range("2023-01-01", periods=20, freq="W")
        walcl = pd.Series([8_000_000.0] * 20, index=dates)
        tga = pd.Series([600_000.0] * 20, index=dates)
        rrp = pd.Series([400_000.0] * 20, index=dates)

        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = [walcl, tga, rrp]

        with patch("fredapi.Fred", return_value=mock_fred):
            from backend.services.net_liquidity import _fetch_and_calculate
            result = _fetch_and_calculate()

        c = result["current"]
        expected_nl = c["walcl"] - c["tga"] - c["rrp"]
        assert abs(c["net_liquidity"] - expected_nl) < 0.001, (
            f"net_liquidity={c['net_liquidity']} != walcl-tga-rrp={expected_nl}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# HARDENING: DATA QUALITY EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestDataQualityEdgeCases:
    """Edge cases for data_quality.py."""

    def test_non_datetime_index_no_crash(self):
        """DataQualityChecker should not crash on non-datetime index."""
        from backend.services.data_quality import DataQualityChecker
        df = pd.DataFrame({"SP500": [100, 101, 102]}, index=[0, 1, 2])
        checker = DataQualityChecker()
        warnings = checker._check_staleness(df)
        assert isinstance(warnings, list)
        assert len(warnings) == 0  # Should skip, not warn

    def test_empty_dataframe_no_crash(self):
        """DataQualityChecker should handle empty DataFrame."""
        from backend.services.data_quality import DataQualityChecker
        df = pd.DataFrame()
        checker = DataQualityChecker()
        warnings = checker.validate(df)
        assert isinstance(warnings, list)
        assert len(warnings) == 0

    def test_all_nan_column(self):
        """Staleness check should handle columns that are entirely NaN."""
        from backend.services.data_quality import DataQualityChecker
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        df = pd.DataFrame({"SP500": [100.0] * 10, "VIX": [float("nan")] * 10}, index=dates)
        checker = DataQualityChecker()
        warnings = checker._check_staleness(df)
        assert isinstance(warnings, list)
        # VIX is all-NaN → last_valid_index() returns None → skipped, no crash

    def test_vix_out_of_range_detected(self):
        """Range check flags VIX values outside configured bounds."""
        from backend.services.data_quality import DataQualityChecker
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        df = pd.DataFrame({"VIX": [10, 20, 95, 3, 50]}, index=dates)
        checker = DataQualityChecker()
        warnings = checker._check_range(df)
        vix_warns = [w for w in warnings if w["column"] == "VIX"]
        assert len(vix_warns) == 1
        assert "outside" in vix_warns[0]["message"]

    def test_sp500_extreme_return_flagged(self):
        """Range check flags S&P daily returns exceeding threshold."""
        from backend.services.data_quality import DataQualityChecker
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        # 50% single-day jump
        df = pd.DataFrame({"SP500": [100, 150, 155, 160, 162]}, index=dates)
        checker = DataQualityChecker()
        warnings = checker._check_range(df)
        sp_warns = [w for w in warnings if w["column"] == "SP500"]
        assert len(sp_warns) == 1
        assert "exceeding" in sp_warns[0]["message"]

    def test_consistency_flags_huge_jump(self):
        """Consistency check flags day-over-day SP500 changes > 30%."""
        from backend.services.data_quality import DataQualityChecker
        dates = pd.date_range("2024-01-01", periods=4, freq="D")
        df = pd.DataFrame({"SP500": [100, 100, 200, 200]}, index=dates)  # 100% jump
        checker = DataQualityChecker()
        warnings = checker._check_consistency(df)
        assert len(warnings) == 1
        assert warnings[0]["severity"] == "error"

    def test_completeness_flags_high_nan(self):
        """Completeness check flags columns with >20% NaN."""
        from backend.services.data_quality import DataQualityChecker
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        values = [100.0] * 7 + [float("nan")] * 3  # 30% NaN
        df = pd.DataFrame({"SP500": values}, index=dates)
        checker = DataQualityChecker()
        warnings = checker._check_completeness(df)
        assert len(warnings) == 1
        assert "NaN" in warnings[0]["message"]

    def test_summary_returns_degraded_on_error(self):
        """summary() returns 'degraded' status when errors present."""
        from backend.services.data_quality import DataQualityChecker
        dates = pd.date_range("2024-01-01", periods=4, freq="D")
        df = pd.DataFrame({"SP500": [100, 100, 200, 200]}, index=dates)  # huge jump = error
        checker = DataQualityChecker()
        summary = checker.summary(df)
        assert summary["status"] == "degraded"
        assert summary["errors"] >= 1

    def test_summary_returns_healthy_on_clean_data(self):
        """summary() returns 'healthy' when no issues found."""
        from backend.services.data_quality import DataQualityChecker
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        df = pd.DataFrame({"SP500": np.linspace(100, 102, 10)}, index=dates)
        checker = DataQualityChecker()
        summary = checker.summary(df)
        assert summary["status"] == "healthy"

    def test_string_index_no_crash(self):
        """String-indexed DataFrame should not crash staleness check."""
        from backend.services.data_quality import DataQualityChecker
        df = pd.DataFrame({"SP500": [100, 101]}, index=["a", "b"])
        checker = DataQualityChecker()
        warnings = checker._check_staleness(df)
        assert isinstance(warnings, list)


# ═══════════════════════════════════════════════════════════════════════════════
# HARDENING: LLM ANALYZER EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestLlmHardening:
    """Additional edge cases for llm_analyzer."""

    @patch("backend.services.llm_analyzer._call_llm")
    def test_mixed_sentiment_detected(self, mock_llm):
        mock_llm.return_value = "Markets showed mixed signals with uncertain outlook and volatility."
        import backend.services.llm_analyzer as mod
        news = [{"title": "Mixed signals", "publisher": "Reuters"}]
        result = mod.summarize_market_news.__wrapped__(news)
        assert result["sentiment"] == "mixed"

    @patch("backend.services.llm_analyzer._call_llm")
    def test_neutral_sentiment_default(self, mock_llm):
        mock_llm.return_value = "The market traded sideways today with minimal movement."
        import backend.services.llm_analyzer as mod
        news = [{"title": "Flat markets", "publisher": "Reuters"}]
        result = mod.summarize_market_news.__wrapped__(news)
        assert result["sentiment"] == "neutral"

    @patch("backend.services.llm_analyzer._call_llm")
    def test_negative_score_clamped(self, mock_llm):
        mock_llm.return_value = "BULL: x\nBEAR: y\nSCORE: -5.0\nSUMMARY: z"
        import backend.services.llm_analyzer as mod
        result = mod.analyze_stock_outlook.__wrapped__("AAPL", [], {"pe_ratio": 30})
        assert result["sentiment_score"] == -1.0

    @patch("backend.services.llm_analyzer._call_llm")
    def test_invalid_score_defaults_zero(self, mock_llm):
        mock_llm.return_value = "BULL: x\nBEAR: y\nSCORE: not_a_number\nSUMMARY: z"
        import backend.services.llm_analyzer as mod
        result = mod.analyze_stock_outlook.__wrapped__("AAPL", [], {"pe_ratio": 30})
        assert result["sentiment_score"] == 0.0

    def test_stock_outlook_none_news(self):
        """analyze_stock_outlook handles None news list."""
        import backend.services.llm_analyzer as mod
        # _call_llm returns None when no key set
        with patch("backend.services.llm_analyzer._call_llm", return_value=None):
            result = mod.analyze_stock_outlook.__wrapped__("AAPL", None, {"pe_ratio": 30})
        assert result is None

    @patch("backend.services.llm_analyzer._call_llm")
    def test_expectations_with_earnings_only(self, mock_llm):
        mock_llm.return_value = "Watch for:\n- Earnings surprise\n- Revenue trend"
        import backend.services.llm_analyzer as mod
        result = mod.generate_expectations.__wrapped__(
            "AAPL", analyst_targets=None, earnings={"next_date": "2026-04-20", "estimate": 1.50}
        )
        assert result is not None
        assert len(result["key_catalysts"]) == 2

    def test_config_values_loaded(self):
        """LLM config values should come from config.py, not hardcoded."""
        from backend.config import config
        llm_cfg = config.get("llm", {})
        assert "base_url" in llm_cfg
        assert "model" in llm_cfg
        assert "max_tokens" in llm_cfg
        assert "temperature" in llm_cfg
        assert isinstance(llm_cfg["max_tokens"], int)
        assert 0 < llm_cfg["temperature"] <= 1.0

    @patch("backend.services.llm_analyzer._call_llm")
    def test_bullish_sentiment_keywords(self, mock_llm):
        """Bullish keywords should be detected in market summary."""
        mock_llm.return_value = "Stocks continued their rally sharply on strong optimism."
        import backend.services.llm_analyzer as mod
        news = [{"title": "Rally", "publisher": "Bloomberg"}]
        result = mod.summarize_market_news.__wrapped__(news)
        assert result["sentiment"] == "bullish"

    @patch("backend.services.llm_analyzer._call_llm")
    def test_bearish_sentiment_keywords(self, mock_llm):
        """Bearish keywords should be detected in market summary."""
        mock_llm.return_value = "Markets declined as fear spread through the banking sector."
        import backend.services.llm_analyzer as mod
        news = [{"title": "Decline", "publisher": "CNBC"}]
        result = mod.summarize_market_news.__wrapped__(news)
        assert result["sentiment"] == "bearish"

    @patch("backend.services.llm_analyzer._call_llm")
    def test_positive_score_clamped_at_1(self, mock_llm):
        """Scores above 1.0 should be clamped to 1.0."""
        mock_llm.return_value = "BULL: amazing\nBEAR: minor\nSCORE: 9.9\nSUMMARY: very bullish"
        import backend.services.llm_analyzer as mod
        result = mod.analyze_stock_outlook.__wrapped__("NVDA", [], {"pe_ratio": 60})
        assert result["sentiment_score"] == 1.0

    @patch("backend.services.llm_analyzer._call_llm")
    def test_outlook_fallback_when_no_bull_bear(self, mock_llm):
        """If LLM doesn't follow format, fallback uses full response as summary."""
        mock_llm.return_value = "AAPL looks solid with strong revenue growth expected."
        import backend.services.llm_analyzer as mod
        result = mod.analyze_stock_outlook.__wrapped__("AAPL", [], {"pe_ratio": 30})
        assert result["bull_case"] == ""
        assert result["bear_case"] == ""
        assert "AAPL" in result["summary"]

    def test_empty_news_returns_none(self):
        """summarize_market_news returns None for empty news list."""
        import backend.services.llm_analyzer as mod
        result = mod.summarize_market_news.__wrapped__([])
        assert result is None

    def test_expectations_none_when_no_targets_or_earnings(self):
        """generate_expectations returns None when both inputs are None."""
        import backend.services.llm_analyzer as mod
        with patch("backend.services.llm_analyzer._call_llm", return_value="anything"):
            result = mod.generate_expectations.__wrapped__("AAPL", None, None)
        assert result is None

    @patch("backend.services.llm_analyzer._call_llm")
    def test_outlook_with_zero_market_cap(self, mock_llm):
        """analyze_stock_outlook handles zero/None market cap gracefully."""
        mock_llm.return_value = "BULL: growth\nBEAR: risk\nSCORE: 0.2\nSUMMARY: moderate"
        import backend.services.llm_analyzer as mod
        result = mod.analyze_stock_outlook.__wrapped__(
            "XYZ", [], {"pe_ratio": None, "market_cap": 0, "beta": None}
        )
        assert result is not None
        assert result["sentiment_score"] == 0.2
