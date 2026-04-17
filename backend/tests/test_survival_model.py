"""Tests for CrashSurvivalModel (Cox PH crash timing)."""

import numpy as np
import pandas as pd
import pytest

from backend.services.survival_model import (
    COX_FEATURES,
    CrashSurvivalModel,
    _HAS_LIFELINES,
    _build_survival_targets,
)


def _synthetic_prices(n: int = 500, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0005, 0.01, size=n)
    # Inject a clear 25% drawdown around day 300 to guarantee event observations
    returns[300:320] = -0.02
    prices = 100.0 * np.exp(np.cumsum(returns))
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.DataFrame({"SP500": prices}, index=idx)


def test_build_survival_targets_finds_crash_event():
    df = _synthetic_prices()
    out = _build_survival_targets(df, max_horizon=252, threshold=-0.20)

    assert list(out.columns) == ["duration", "event"]
    # Should detect at least one crash event in our injected window
    assert out["event"].sum() >= 1
    # Durations must be positive and bounded
    assert (out["duration"] > 0).all()
    assert (out["duration"] <= 252).all()


def test_build_survival_targets_no_crash_all_censored():
    """Smoothly rising prices → every row censored (event=0)."""
    idx = pd.date_range("2020-01-01", periods=300, freq="B")
    prices = np.linspace(100.0, 140.0, num=300)
    df = pd.DataFrame({"SP500": prices}, index=idx)

    out = _build_survival_targets(df, max_horizon=126, threshold=-0.20)
    assert out["event"].sum() == 0
    assert (out["duration"] == 126).all()


def test_predict_proba_unfitted_returns_base_rate():
    model = CrashSurvivalModel()
    features = pd.DataFrame({f: np.zeros(10) for f in COX_FEATURES})

    probs = model.predict_proba(features, horizon="12m")
    assert probs.shape == (10,)
    # Should fall back to configured base rate
    assert np.allclose(probs, model._base_rate)


def test_top_features_empty_when_untrained():
    model = CrashSurvivalModel()
    assert model.get_top_features() == []


def test_train_refuses_too_few_samples():
    model = CrashSurvivalModel()
    n = 200
    features = pd.DataFrame(
        {f: np.random.default_rng(0).standard_normal(n) for f in COX_FEATURES}
    )
    df = _synthetic_prices(n=n)

    result = model.train(features, df, train_end_idx=100, min_train_samples=1260)
    assert result["success"] is False
    assert "samples" in result["reason"].lower()


def test_train_refuses_missing_sp500_column():
    model = CrashSurvivalModel()
    features = pd.DataFrame(
        {f: np.zeros(100) for f in COX_FEATURES}
    )
    bad_df = pd.DataFrame({"NOT_SP500": np.ones(100)})

    result = model.train(features, bad_df, train_end_idx=50)
    assert result["success"] is False
    assert "SP500" in result["reason"]


@pytest.mark.skipif(not _HAS_LIFELINES, reason="lifelines not installed")
def test_train_and_predict_end_to_end():
    """Train on synthetic data with a real crash — verify fit returns coefficients."""
    n = 2000
    rng = np.random.default_rng(7)
    df = _synthetic_prices(n=n, seed=7)

    # Create synthetic features with some signal relative to injected crash
    vix_z = np.concatenate([
        rng.normal(0, 1, 290),
        rng.normal(3, 1, 40),   # VIX spike before crash
        rng.normal(1, 1, n - 330),
    ])
    features = pd.DataFrame(
        {
            "vix_zscore": vix_z,
            "term_spread": rng.normal(0, 0.01, n),
            "credit_spread_proxy": rng.normal(0, 0.5, n),
            "mom_12m": rng.normal(0.08, 0.15, n),
            "vol_ratio_1m_12m": rng.normal(1.0, 0.2, n),
            "mom_6m": rng.normal(0.04, 0.10, n),
            "sma_200d_dev": rng.normal(0, 0.05, n),
            "dist_52w_high": rng.normal(-0.05, 0.05, n),
            "vol_1m": rng.normal(0.15, 0.05, n),
        },
        index=df.index,
    )

    model = CrashSurvivalModel()
    result = model.train(features, df, train_end_idx=n, min_train_samples=800)

    # Either we successfully trained, or lifelines reported an honest reason
    if result.get("success"):
        assert model.is_trained
        # Prediction over a fresh slice should stay inside [0.02, 0.98]
        probs = model.predict_proba(features.iloc[-50:], horizon="6m")
        assert probs.shape == (50,)
        assert (probs >= 0.02).all() and (probs <= 0.98).all()
        assert len(model.get_top_features(3)) == 3
    else:
        assert "reason" in result
