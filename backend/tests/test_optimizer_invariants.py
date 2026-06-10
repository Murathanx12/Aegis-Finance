"""
Grind A2: invariant coverage for portfolio math + crash post-processing.

Targets the lowest-covered high-risk module (portfolio_optimizer.py, 58%
baseline) plus the crash-model monotonicity contract. All offline —
_fetch_returns and liquidity fetches are patched with synthetic data.

Invariants:
  - optimizer outputs: weights ⊆ requested tickers, long-only, sum ≈ 1
  - liquidity adjustment: never invents weight, conserves sum when any
    liquid asset survives, hard-floors sub-minimum dollar-volume names
  - predict_all_horizons: monotone 3m ≤ 6m ≤ 12m for ANY raw model output
"""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from backend.services.portfolio_optimizer import (
    _equal_weight_fallback,
    _recommend_method,
    adjust_weights_for_liquidity,
    compare_methods,
    optimize_hrp,
    optimize_max_diversification,
    optimize_mean_cvar,
    optimize_risk_parity,
)

TICKERS = ["AAA", "BBB", "CCC", "DDD", "EEE"]


def _synthetic_returns(n_days: int = 400, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n_days, freq="B")
    # Correlated returns with distinct vols so optimizers differentiate.
    base = rng.normal(0.0003, 0.01, (n_days, 1))
    noise = rng.normal(0, 1, (n_days, len(TICKERS)))
    vols = np.array([0.008, 0.012, 0.02, 0.015, 0.01])
    data = base + noise * vols
    return pd.DataFrame(data, index=idx, columns=TICKERS)


def _assert_valid_weights(result, tickers):
    assert result is not None
    weights = result["weights"]
    assert set(weights) <= set(tickers)
    assert all(w >= 0 for w in weights.values()), f"short position: {weights}"
    total = sum(weights.values())
    assert total == pytest.approx(1.0, abs=0.01), f"weights sum {total}"


class TestOptimizerInvariants:
    @pytest.mark.parametrize("fn", [
        optimize_mean_cvar,
        optimize_risk_parity,
        optimize_max_diversification,
        optimize_hrp,
    ])
    def test_long_only_fully_invested(self, fn):
        with patch(
            "backend.services.portfolio_optimizer._fetch_returns",
            return_value=_synthetic_returns(),
        ):
            result = fn(TICKERS, lookback_days=400)
        _assert_valid_weights(result, TICKERS)

    def test_no_data_returns_none(self):
        with patch(
            "backend.services.portfolio_optimizer._fetch_returns",
            return_value=None,
        ):
            assert optimize_risk_parity(TICKERS) is None

    def test_single_ticker_returns_none(self):
        returns = _synthetic_returns()[["AAA"]]
        with patch(
            "backend.services.portfolio_optimizer._fetch_returns",
            return_value=returns,
        ):
            assert optimize_hrp(["AAA"]) is None

    def test_equal_weight_fallback(self):
        result = _equal_weight_fallback(TICKERS)
        _assert_valid_weights(result, TICKERS)
        assert len(set(result["weights"].values())) == 1


class TestCompareMethods:
    def test_runs_all_methods_and_recommends(self):
        liq = {t: {"composite": 90, "tier": "high",
                   "avg_dollar_volume_mm": 500.0} for t in TICKERS}
        with patch(
            "backend.services.portfolio_optimizer._fetch_returns",
            return_value=_synthetic_returns(),
        ), patch(
            "backend.services.portfolio_optimizer._fetch_liquidity_scores",
            return_value=liq,
        ):
            result = compare_methods(TICKERS, lookback_days=400)

        assert result["n_methods"] >= 2
        assert "equal_weight" in result["methods"]
        assert "Best risk-adjusted" in result["recommendation"]
        for r in result["methods"].values():
            assert "liquidity_adjusted" in r

    def test_recommend_empty(self):
        assert _recommend_method({}) == "Insufficient data for optimization."


# ── Liquidity adjustment property tests ──────────────────────────────────────

_weight_lists = st.lists(
    st.floats(min_value=0.01, max_value=1.0, allow_nan=False),
    min_size=2, max_size=8,
)
_scores = st.lists(
    st.tuples(
        st.floats(min_value=0, max_value=100, allow_nan=False),   # composite
        st.floats(min_value=0, max_value=500, allow_nan=False),   # dollar vol $M
    ),
    min_size=2, max_size=8,
)


class TestLiquidityAdjustmentProperties:
    @settings(max_examples=200, deadline=None)
    @given(raw=_weight_lists, scores=_scores)
    def test_never_invents_weight_and_conserves_when_possible(self, raw, scores):
        n = min(len(raw), len(scores))
        tickers = [f"T{i}" for i in range(n)]
        total_in = sum(raw[:n])
        weights = {t: raw[i] / total_in for i, t in enumerate(tickers)}
        liq = {
            t: {"composite": scores[i][0], "tier": "x",
                "avg_dollar_volume_mm": scores[i][1]}
            for i, t in enumerate(tickers)
        }

        out = adjust_weights_for_liquidity(weights, liq)
        adjusted = out["weights"]

        # Never invents tickers; never goes short.
        assert set(adjusted) <= set(tickers)
        assert all(w >= 0 for w in adjusted.values())

        # If any liquid (unpenalized) asset survived, weight is conserved.
        survivors_unpenalized = [
            t for t in adjusted if t not in out["adjustments"]
        ]
        if survivors_unpenalized:
            assert sum(adjusted.values()) == pytest.approx(1.0, abs=0.02)

    def test_hard_floor_zeroes_thin_names(self):
        weights = {"LIQ": 0.5, "THIN": 0.5}
        liq = {
            "LIQ": {"composite": 90, "tier": "x", "avg_dollar_volume_mm": 100.0},
            "THIN": {"composite": 90, "tier": "x", "avg_dollar_volume_mm": 0.1},
        }
        out = adjust_weights_for_liquidity(weights, liq)
        assert "THIN" not in out["weights"]
        assert out["weights"]["LIQ"] == pytest.approx(1.0, abs=0.001)
        assert out["n_removed"] == 1


# ── Crash model post-processing contract ─────────────────────────────────────


class TestPredictAllHorizonsMonotone:
    @settings(max_examples=200, deadline=None)
    @given(
        p3=st.floats(min_value=0, max_value=1, allow_nan=False),
        p6=st.floats(min_value=0, max_value=1, allow_nan=False),
        p12=st.floats(min_value=0, max_value=1, allow_nan=False),
    )
    def test_monotone_for_any_raw_output(self, p3, p6, p12):
        """predict_all_horizons must order ANY raw per-horizon outputs."""
        from backend.services.crash_model import CrashPredictor

        predictor = CrashPredictor()
        predictor.lgb_models = {"3m": object(), "6m": object(), "12m": object()}
        raw = {"3m": p3, "6m": p6, "12m": p12}

        with patch.object(
            CrashPredictor, "predict_proba",
            side_effect=lambda self_or_f, horizon=None, **kw: np.array(
                [raw[horizon]]
            ),
        ):
            probs = predictor.predict_all_horizons(pd.DataFrame([{"f": 0.0}]))

        assert probs["3m"][0] <= probs["6m"][0] <= probs["12m"][0]
        # Post-processing may only raise probabilities, never lower them.
        for h in raw:
            assert probs[h][0] >= raw[h] - 1e-12
