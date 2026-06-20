"""Tests for the descriptive continuous exposure multiplier (Chunk 5).

The crisis bridge must be CONTINUOUS (never a binary risk-off call) and never
arm a live lane."""

import pytest

from backend.services.portfolio_intelligence.fragility import (
    EXPOSURE_FLOOR,
    FRAGILITY_HIGH,
    FRAGILITY_NEUTRAL,
    exposure_multiplier,
)


class TestExposureMultiplier:
    def test_none_composite_unavailable(self):
        out = exposure_multiplier(None)
        assert out["status"] == "unavailable"
        assert out["multiplier"] is None
        assert out["arms_lane"] is False

    def test_nan_composite_unavailable(self):
        # A NaN composite (e.g. an upstream input that normalized to NaN) must NOT
        # silently produce a NaN multiplier reported as status="ok".
        import math
        out = exposure_multiplier(float("nan"))
        assert out["status"] == "unavailable"
        assert out["multiplier"] is None

    def test_low_fragility_full_exposure(self):
        out = exposure_multiplier(FRAGILITY_NEUTRAL - 0.1)
        assert out["multiplier"] == 1.0

    def test_at_neutral_full_exposure(self):
        assert exposure_multiplier(FRAGILITY_NEUTRAL)["multiplier"] == 1.0

    def test_high_fragility_hits_floor(self):
        out = exposure_multiplier(FRAGILITY_HIGH + 0.05)
        assert out["multiplier"] == EXPOSURE_FLOOR

    def test_at_high_hits_floor(self):
        assert exposure_multiplier(FRAGILITY_HIGH)["multiplier"] == EXPOSURE_FLOOR

    def test_midpoint_between_floor_and_one(self):
        mid = (FRAGILITY_NEUTRAL + FRAGILITY_HIGH) / 2
        m = exposure_multiplier(mid)["multiplier"]
        assert EXPOSURE_FLOOR < m < 1.0
        # halfway should be ~ the average of 1.0 and the floor
        assert m == pytest.approx((1.0 + EXPOSURE_FLOOR) / 2, abs=1e-6)

    def test_monotonic_non_increasing(self):
        xs = [i / 20 for i in range(21)]  # 0.0 .. 1.0
        mults = [exposure_multiplier(x)["multiplier"] for x in xs]
        for a, b in zip(mults, mults[1:]):
            assert b <= a + 1e-9

    def test_never_below_floor_or_above_one(self):
        for x in [0.0, 0.25, 0.5, 0.75, 1.0]:
            m = exposure_multiplier(x)["multiplier"]
            assert EXPOSURE_FLOOR <= m <= 1.0

    def test_clips_out_of_range_composite(self):
        assert exposure_multiplier(-0.5)["multiplier"] == 1.0
        assert exposure_multiplier(1.5)["multiplier"] == EXPOSURE_FLOOR

    def test_descriptive_never_arms(self):
        out = exposure_multiplier(0.8)
        assert out["arms_lane"] is False
        assert "NOT armed" in out["label"]
