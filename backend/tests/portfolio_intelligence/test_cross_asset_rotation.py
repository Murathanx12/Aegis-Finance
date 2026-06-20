"""Tests for the cross-asset rotation decision core (Chunk 6).

Pure functions, offline. The core must be anti-hindsight (inverse-vol base) and
tilt only via the descriptive fragility multiplier."""

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio_intelligence.cross_asset_rotation import (
    EQUITY_ASSETS,
    crossasset_target_weights,
    inverse_vol_weights,
)


def _returns(vols: dict, n=250, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({a: rng.normal(0, v, n) for a, v in vols.items()})


class TestInverseVol:
    def test_lower_vol_gets_more_weight(self):
        w = inverse_vol_weights(_returns({"SPY": 0.02, "SHY": 0.002}))
        assert w["SHY"] > w["SPY"]
        assert pytest.approx(sum(w.values()), abs=1e-9) == 1.0

    def test_empty_returns_empty(self):
        assert inverse_vol_weights(pd.DataFrame()) == {}

    def test_zero_vol_asset_dropped(self):
        df = _returns({"SPY": 0.02})
        df["DEAD"] = 0.0
        w = inverse_vol_weights(df)
        assert "DEAD" not in w


class TestCrossAssetWeights:
    def _df(self):
        return _returns({"SPY": 0.02, "TLT": 0.012, "IEF": 0.006,
                         "LQD": 0.007, "GLD": 0.01, "SHY": 0.002})

    def test_no_fragility_equals_base(self):
        df = self._df()
        base = inverse_vol_weights(df)
        out = crossasset_target_weights(df, fragility_composite=None)
        for k in base:
            assert out[k] == pytest.approx(base[k], abs=1e-6)

    def test_low_fragility_full_equity(self):
        df = self._df()
        base = inverse_vol_weights(df)
        out = crossasset_target_weights(df, fragility_composite=0.10)  # below neutral
        assert out["SPY"] == pytest.approx(base["SPY"], abs=1e-6)

    def test_high_fragility_cuts_equity_lifts_defensives(self):
        df = self._df()
        base = inverse_vol_weights(df)
        out = crossasset_target_weights(df, fragility_composite=0.95)  # >= high -> floor
        assert out["SPY"] < base["SPY"]
        # at least one defensive sleeve gains
        assert any(out[a] > base[a] for a in ["TLT", "IEF", "LQD", "GLD", "SHY"])
        assert pytest.approx(sum(out.values()), abs=1e-5) == 1.0

    def test_weights_sum_to_one(self):
        for frag in [None, 0.0, 0.3, 0.6, 0.95]:
            out = crossasset_target_weights(self._df(), fragility_composite=frag)
            assert pytest.approx(sum(out.values()), abs=1e-5) == 1.0

    def test_equity_monotonic_down_in_fragility(self):
        df = self._df()
        eq = [crossasset_target_weights(df, fragility_composite=f)["SPY"]
              for f in [0.1, 0.4, 0.6, 0.8, 0.95]]
        for a, b in zip(eq, eq[1:]):
            assert b <= a + 1e-9

    def test_empty_returns_empty(self):
        assert crossasset_target_weights(pd.DataFrame(), 0.5) == {}

    def test_equity_assets_constant(self):
        assert EQUITY_ASSETS == ["SPY"]
