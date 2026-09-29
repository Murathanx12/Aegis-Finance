"""Offline tests for scripts.crsp_blend_followups (2026-09-29 review follow-ups)."""
import math

import numpy as np
import pandas as pd

from scripts.crsp_blend_followups import corwin_schultz_pairs, rank_band_mask, skip_fwd, verdict_a


def test_cs_zero_range_is_zero_and_first_is_nan():
    s = corwin_schultz_pairs([10, 10, 10], [10, 10, 10], [10, 10, 10])
    assert math.isnan(s[0])
    assert s[1] == 0.0 and s[2] == 0.0


def test_cs_positive_for_bid_ask_bounce_ranges():
    # a constant 2% range with no drift: range is all spread, estimate is positive
    s = corwin_schultz_pairs([10.1] * 5, [9.9] * 5, [10.0] * 5)
    assert np.all(s[1:] > 0.005) and np.all(s[1:] < 0.05)


def test_cs_overnight_gap_does_not_inflate():
    # day 2 gaps up 10% with the same 2% range: without the adjustment gamma would explode
    s = corwin_schultz_pairs([10.1, 11.11], [9.9, 10.89], [10.0, 11.0])
    s0 = corwin_schultz_pairs([10.1, 10.1], [9.9, 9.9], [10.0, 10.0])
    assert s[1] <= s0[1] + 0.02


def test_cs_bad_range_is_nan():
    s = corwin_schultz_pairs([10, 9], [11, 8], [10, 8.5])
    assert math.isnan(s[1])


def test_skip_fwd_identity_and_missing():
    f = np.array([0.10, 0.10, 0.10])
    out = skip_fwd(f, [1.0, np.nan, 1.02], [1.0, 1.0, np.nan])
    assert np.allclose(out, [0.10, 0.10, 1.10 / 1.02 - 1])


def test_rank_band_mask_top_n_among_eligible():
    df = pd.DataFrame({"date": ["d"] * 4, "eligible": [True, True, False, True],
                       "median_dollar_vol": [5.0, 3.0, 99.0, 4.0]})
    assert rank_band_mask(df, 2).tolist() == [True, False, False, True]


def test_verdict_a_lines():
    assert verdict_a({"mean_monthly": 0.005, "t_blocks": 2.1}) == "REMAINS_CANDIDATE"
    assert verdict_a({"mean_monthly": 0.005, "t_blocks": 1.9}) == "CANNOT_DISTINGUISH"
    assert verdict_a({"mean_monthly": 0.0005, "t_blocks": 0.2}) == "FAILED_VARIANT"
    assert verdict_a({"mean_monthly": None}) == "NOT_COMPUTED"
