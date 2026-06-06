"""
Tests for engine/validation/validate_momentum.py (panel reconstruction)
========================================================================

The network download is not exercised here; we test `build_panel` on a
synthetic price frame to lock in the no-look-ahead reconstruction:
  - the factor at date t uses only prices up to t,
  - the forward return uses only t → t+fwd_days,
  - a steadily-rising series scores positive momentum, a falling one negative.
"""

import numpy as np
import pandas as pd

from engine.validation.validate_momentum import build_panel


def _prices(n=320):
    idx = pd.bdate_range("2020-01-01", periods=n)
    up = 100.0 * (1.001 ** np.arange(n))     # steadily rising
    down = 100.0 * (0.999 ** np.arange(n))   # steadily falling
    return pd.DataFrame({"UP": up, "DOWN": down}, index=idx)


def test_build_panel_signs_and_forward_return():
    prices = _prices()
    panel = build_panel(prices, fwd_days=21, step_days=21)
    assert not panel.empty
    # Rising series → positive momentum + positive forward; falling → negative.
    up = panel[panel.asset == "UP"]
    down = panel[panel.asset == "DOWN"]
    assert (up["composite"] > 0).all()
    assert (up["fwd"] > 0).all()
    assert (down["composite"] < 0).all()
    assert (down["mom_12_1"] < 0).all()


def test_build_panel_forward_return_is_exact():
    """The forward return must equal p[i+fwd]/p[i]-1 exactly (no leakage)."""
    prices = _prices()
    panel = build_panel(prices, fwd_days=21, step_days=21)
    col = prices["UP"].values
    # First rebalance row sits at position 252 (need 12M history).
    first = panel[(panel.asset == "UP")].iloc[0]
    i = prices.index.get_loc(first["date"])
    assert i == 252
    expected_fwd = col[i + 21] / col[i] - 1.0
    assert np.isclose(first["fwd"], expected_fwd)


def test_build_panel_non_overlapping_dates():
    prices = _prices()
    panel = build_panel(prices, fwd_days=21, step_days=21)
    dates = sorted(panel["date"].unique())
    # Each rebalance is 21 business days apart (non-overlapping forward windows).
    gaps = {(prices.index.get_loc(b) - prices.index.get_loc(a))
            for a, b in zip(dates, dates[1:])}
    assert gaps == {21}
