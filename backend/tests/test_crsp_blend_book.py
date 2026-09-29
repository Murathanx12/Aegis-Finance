"""Offline tests for scripts/crsp_blend_book.py (synthetic day, no bars, no freeze)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import crsp_blend_book as B


def test_band_of_thresholds():
    assert B.band_of(2e9) == "mega" and B.band_of(1e8) == "large"
    assert B.band_of(3e7) == "mid" and B.band_of(1e6) == "small" and B.band_of(float("nan")) == "small"


def test_combine_sleeves_quarters_and_cash_for_a_closed_gate():
    book = B.combine_sleeves({"a": {"X": 1.0, "Y": 1.0}, "b": {"X": 2.0}, "c": {}, "d": {"Z": 5.0}})
    assert abs(book["X"] - (0.125 + 0.25)) < 1e-12
    assert abs(book["CASH"] - 0.25) < 1e-12
    assert abs(sum(book.values()) - 1.0) < 1e-12


def _day(n=90, seed=3):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"eligible": True,
                         "median_dollar_vol": np.repeat([2e9, 2e8, 5e7], n // 3),
                         "vol_63": rng.uniform(0.1, 0.8, n), "mom_252_21": rng.normal(0, 0.3, n)},
                        index=[f"S{i}" for i in range(n)])


def test_matched_twin_same_band_excludes_held_and_conserves_weight():
    day = _day()
    held = {"S0": 0.5, "S40": 0.25, "CASH": 0.25}
    tw, meta = B.matched_twin(held, day, seed=11, draws=21)
    assert not ({"S0", "S40"} & set(tw))
    assert abs(sum(tw.values()) - 1.0) < 1e-9 and tw["CASH"] == 0.25
    bands = day["median_dollar_vol"].map(B.band_of)
    s0_band = [t for t in tw if t != "CASH" and bands[t] == "mega"]
    assert abs(sum(tw[t] for t in s0_band) - 0.5) < 1e-9       # S0's weight stays in its band
    assert meta["draws"] == 21 and sum(meta["fallbacks"].values()) == 42
    tw2, _ = B.matched_twin(held, day, seed=11, draws=21)
    assert tw2 == tw                                              # seeded: reproducible
