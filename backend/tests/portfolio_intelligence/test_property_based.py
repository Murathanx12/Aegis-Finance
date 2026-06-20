"""Property-based + degenerate-input tests (Track 4).

hypothesis properties for the two numeric cores:
  - exposure_multiplier: bounded in [floor, 1.0], monotonic non-increasing.
  - cross_asset_rotation: weights non-negative, finite, sum to 1 (or empty).
Plus explicit degenerate inputs (zero vol, single asset, all-NaN, mixed-NaN)
that must clamp or return empty — never a silent wrong number."""

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.services.portfolio_intelligence.cross_asset_rotation import (
    crossasset_target_weights,
    inverse_vol_weights,
)
from backend.services.portfolio_intelligence.fragility import (
    EXPOSURE_FLOOR,
    exposure_multiplier,
)

ASSETS = ["SPY", "TLT", "IEF", "LQD", "GLD", "SHY"]


# ── exposure_multiplier properties ───────────────────────────────────────────


@given(st.floats(min_value=-1.0, max_value=2.0, allow_nan=False, allow_infinity=False))
def test_multiplier_always_bounded(c):
    m = exposure_multiplier(c)["multiplier"]
    assert m is not None
    assert EXPOSURE_FLOOR <= m <= 1.0


@given(
    st.floats(0.0, 1.0, allow_nan=False),
    st.floats(0.0, 1.0, allow_nan=False),
)
def test_multiplier_monotonic_non_increasing(a, b):
    ma = exposure_multiplier(a)["multiplier"]
    mb = exposure_multiplier(b)["multiplier"]
    if a <= b:
        assert ma >= mb - 1e-9
    else:
        assert mb >= ma - 1e-9


def test_multiplier_nan_is_unavailable():
    out = exposure_multiplier(float("nan"))
    assert out["status"] == "unavailable" and out["multiplier"] is None


# ── cross_asset_rotation properties ──────────────────────────────────────────


@given(
    st.lists(st.floats(min_value=0.001, max_value=0.10, allow_nan=False),
             min_size=6, max_size=6),
    st.one_of(st.none(), st.floats(0.0, 1.0, allow_nan=False)),
)
@settings(max_examples=120, deadline=None)
def test_weights_valid_for_any_positive_vols(vols, frag):
    rng = np.random.default_rng(0)
    df = pd.DataFrame({a: rng.normal(0.0, v, 120) for a, v in zip(ASSETS, vols)})
    w = crossasset_target_weights(df, fragility_composite=frag)
    assert w, "non-empty input must yield weights"
    assert all(v >= 0.0 for v in w.values()), "no negative weights"
    assert all(math.isfinite(v) for v in w.values()), "no NaN/inf weights"
    assert abs(sum(w.values()) - 1.0) < 1e-5, "weights sum to 1"


# ── degenerate inputs: clamp or empty, never silent-wrong ────────────────────


def test_zero_vol_all_assets_returns_empty():
    df = pd.DataFrame({a: [0.0] * 60 for a in ASSETS})
    assert crossasset_target_weights(df, 0.5) == {}


def test_all_nan_window_returns_empty():
    df = pd.DataFrame({a: [np.nan] * 60 for a in ASSETS})
    assert crossasset_target_weights(df, 0.5) == {}


def test_empty_frame_returns_empty():
    assert crossasset_target_weights(pd.DataFrame(), 0.5) == {}
    assert inverse_vol_weights(pd.DataFrame()) == {}


def test_single_asset_equity_only():
    df = pd.DataFrame({"SPY": np.random.default_rng(0).normal(0, 0.02, 100)})
    w = crossasset_target_weights(df, fragility_composite=0.95)
    # only equity present -> nothing to rotate into -> stays fully invested, valid
    assert set(w) == {"SPY"}
    assert w["SPY"] == pytest.approx(1.0, abs=1e-9)


def test_mixed_nan_column_dropped_not_poisoned():
    df = pd.DataFrame({
        "SPY": np.random.default_rng(1).normal(0, 0.02, 80),
        "TLT": np.random.default_rng(2).normal(0, 0.01, 80),
        "DEAD": [np.nan] * 80,
    })
    w = crossasset_target_weights(df, fragility_composite=0.4)
    assert "DEAD" not in w
    assert all(math.isfinite(v) for v in w.values())
    assert abs(sum(w.values()) - 1.0) < 1e-5
