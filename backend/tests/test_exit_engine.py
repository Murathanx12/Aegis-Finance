"""
Tests for the exit engine & position sizing primitives.

These are the mechanical fix for the disposition effect. The behaviours we
assert are exactly the ones that distinguish "let winners run" from "sold too
early": a monotonic winner is NOT stopped out early; a winner that rolls over
IS exited near its peak (capturing most of the run); the stop never ratchets
down; and sizing shrinks as volatility rises.

All deterministic — no network, no randomness beyond a seeded rng.
"""

import numpy as np
import pandas as pd
import pytest

from backend.services.exit_engine import (
    ExitResult,
    compute_atr,
    fractional_kelly_fraction,
    realized_vol,
    simulate_trailing_exit,
    volatility_target_weight,
)


# ── ATR ───────────────────────────────────────────────────────────────────────


def test_atr_positive_and_aligned():
    close = pd.Series(np.linspace(100, 120, 60))
    atr = compute_atr(close, period=14)
    assert len(atr) == len(close)
    assert (atr >= 0).all()
    assert not atr.isna().any()


def test_atr_higher_for_more_volatile_series():
    calm = pd.Series(100 + np.cumsum(np.full(200, 0.1)))
    rng = np.random.default_rng(7)
    wild = pd.Series(100 + np.cumsum(rng.normal(0.1, 3.0, 200)))
    assert compute_atr(wild).iloc[-1] > compute_atr(calm).iloc[-1]


def test_atr_true_range_uses_high_low():
    close = pd.Series([100.0, 101.0, 102.0, 103.0])
    high = close + 2.0
    low = close - 2.0
    atr_hl = compute_atr(close, high=high, low=low, period=2)
    atr_close = compute_atr(close, period=2)
    # With a 4-point H-L band, true-range ATR must exceed the close-only proxy.
    assert atr_hl.iloc[-1] > atr_close.iloc[-1]


# ── Trailing-stop: the core behaviours ────────────────────────────────────────


def test_monotonic_winner_runs_to_the_end():
    """A relentlessly rising stock must NOT be stopped out — it runs to the end.

    This is the 'don't sell NVDA at +200%' property.
    """
    close = pd.Series(np.linspace(20, 100, 250))  # 5x, straight up
    res = simulate_trailing_exit(close, entry_index=0, atr_multiple=3.0)
    assert res.reason == "end_of_data"
    assert res.return_pct == pytest.approx(100 / 20 - 1.0, rel=1e-6)


def test_winner_that_rolls_over_exits_near_peak():
    """Rise to a peak then crash: the stop must fire and keep most of the gain."""
    up = np.linspace(20.0, 100.0, 200)
    down = np.linspace(100.0, 30.0, 50)
    close = pd.Series(np.concatenate([up, down]))
    res = simulate_trailing_exit(close, entry_index=0, atr_multiple=3.0)
    assert res.reason == "trailing_stop"
    # Exited on the way down, not at the bottom.
    assert res.exit_index > 200
    assert res.exit_price < 100.0
    # Captured a large chunk of the 5x run (far better than buy-and-hold to the
    # end, which would have given back to 30).
    assert res.return_pct > 1.0
    assert res.max_favorable_pct == pytest.approx(4.0, rel=1e-6)


def test_stop_never_ratchets_down():
    rng = np.random.default_rng(42)
    close = pd.Series(50 + np.cumsum(rng.normal(0.05, 1.0, 400)).clip(min=-40))
    res = simulate_trailing_exit(close, entry_index=0, atr_multiple=2.5)
    stops = np.array(res.stop_path)
    # Monotonically non-decreasing within floating tolerance.
    assert np.all(np.diff(stops) >= -1e-9)


def test_tighter_multiple_exits_no_later_than_looser():
    up = np.linspace(20.0, 100.0, 150)
    down = np.linspace(100.0, 60.0, 40)
    close = pd.Series(np.concatenate([up, down]))
    tight = simulate_trailing_exit(close, atr_multiple=2.0)
    loose = simulate_trailing_exit(close, atr_multiple=4.0)
    assert tight.exit_index <= loose.exit_index


def test_returns_exitresult_dataclass():
    close = pd.Series(np.linspace(10, 11, 30))
    res = simulate_trailing_exit(close)
    assert isinstance(res, ExitResult)
    assert res.bars_held == res.exit_index  # entry_index defaults to 0


def test_invalid_entry_index_raises():
    close = pd.Series(np.linspace(10, 11, 30))
    with pytest.raises(ValueError):
        simulate_trailing_exit(close, entry_index=99)


def test_empty_series_raises():
    with pytest.raises(ValueError):
        simulate_trailing_exit(pd.Series([], dtype=float))


# ── Volatility targeting ──────────────────────────────────────────────────────


def test_realized_vol_scales_with_noise():
    rng = np.random.default_rng(1)
    calm = pd.Series(rng.normal(0, 0.005, 300))
    wild = pd.Series(rng.normal(0, 0.03, 300))
    assert realized_vol(wild) > realized_vol(calm)


def test_vol_target_weight_smaller_for_more_volatile():
    rng = np.random.default_rng(2)
    calm = pd.Series(rng.normal(0, 0.02, 300))
    wild = pd.Series(rng.normal(0, 0.04, 300))
    # Large cap so neither input saturates — we are testing the scaling itself.
    w_calm = volatility_target_weight(calm, target_vol=0.20, max_weight=5.0)
    w_wild = volatility_target_weight(wild, target_vol=0.20, max_weight=5.0)
    assert w_wild < w_calm
    assert w_wild > 0.0


def test_vol_target_weight_respects_cap():
    flat = pd.Series(np.full(300, 0.0))  # zero vol → would imply infinite size
    # zero/non-finite vol → 0.0 (can't size what we can't measure)
    assert volatility_target_weight(flat) == 0.0


def test_vol_target_weight_capped_at_max():
    rng = np.random.default_rng(3)
    very_calm = pd.Series(rng.normal(0, 0.0001, 300))
    w = volatility_target_weight(very_calm, target_vol=0.20, max_weight=0.25)
    assert w == pytest.approx(0.25)


# ── Fractional Kelly ──────────────────────────────────────────────────────────


def test_kelly_known_value_quarter():
    # p=0.6, b=2 → full Kelly = 0.6 - 0.4/2 = 0.4 ; quarter = 0.10
    f = fractional_kelly_fraction(0.6, 2.0, fraction=0.25, cap=1.0)
    assert f == pytest.approx(0.10, rel=1e-9)


def test_kelly_negative_edge_is_zero():
    # p=0.4, b=1 → full Kelly = 0.4 - 0.6 = -0.2 → no bet
    assert fractional_kelly_fraction(0.4, 1.0) == 0.0


def test_kelly_respects_cap():
    f = fractional_kelly_fraction(0.95, 5.0, fraction=1.0, cap=0.25)
    assert f == pytest.approx(0.25)


def test_kelly_zero_payoff_is_zero():
    assert fractional_kelly_fraction(0.7, 0.0) == 0.0


def test_kelly_invalid_prob_raises():
    with pytest.raises(ValueError):
        fractional_kelly_fraction(1.5, 2.0)
