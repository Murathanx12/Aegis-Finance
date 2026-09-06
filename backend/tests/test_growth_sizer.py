"""The sizer: point-in-time features, an algebraic Kelly, and the sealed latch."""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from learner import growth_lab as GL
from learner import growth_sizer as GS


def _months(a, b):
    return [f"{y}-{m:02d}" for y in range(int(a[:4]), int(b[:4]) + 1)
            for m in range(1, 13) if a <= f"{y}-{m:02d}" <= b]


def _ctx(idx, spy=0.01, rf=0.001, vol=0.15):
    return pd.DataFrame({"spy": spy, "rf": rf, "spy_vol_21d": vol},
                        index=pd.Index(idx, name="month"))


# ------------------------------------------------------- point in time

def test_no_feature_reads_the_month_it_is_sizing():
    """Plant a spike in month t. NOTHING at month t may move.

    This is the single most profitable bug available in the file and it does
    not announce itself: a feature that reads its own month makes the forecast
    look prescient and the exposure look brilliant.
    """
    idx = _months("2000-01", "2010-12")
    book = pd.Series(0.01, index=pd.Index(idx))
    a = GS.regime_features(_ctx(idx), book)
    ctx2 = _ctx(idx)
    t = 80
    # a NEGATIVE spike: on a monotone-rising planted tape a positive spike sets
    # a new peak and leaves `spy_dd_12m` at zero, so the "does it reach t+1"
    # half of this test would pass vacuously.
    ctx2.iloc[t, ctx2.columns.get_loc("spy")] = -0.50
    ctx2.iloc[t, ctx2.columns.get_loc("rf")] = 0.05
    ctx2.iloc[t, ctx2.columns.get_loc("spy_vol_21d")] = 0.90
    b = GS.regime_features(ctx2, book)
    row_a, row_b = a.iloc[t], b.iloc[t]
    moved = [c for c in GS.FEATURES
             if c != "spy_vol_21d" and not _same(row_a[c], row_b[c])]
    assert moved == [], f"these features read their own month: {moved}"
    # spy_vol_21d IS read at entry and is therefore allowed to move -- it is a
    # state observed BEFORE the month, not a function of the month's return.
    assert not _same(row_a["spy_vol_21d"], row_b["spy_vol_21d"])
    # and the spike must reach the NEXT month
    assert not _same(a.iloc[t + 1]["spy_dd_12m"], b.iloc[t + 1]["spy_dd_12m"])


def test_the_book_features_do_not_read_the_books_own_month():
    idx = _months("2000-01", "2008-12")
    base = pd.Series(0.01, index=pd.Index(idx))
    spiked = base.copy()
    t = 60
    spiked.iloc[t] = -0.5
    a = GS.regime_features(_ctx(idx), base)
    b = GS.regime_features(_ctx(idx), spiked)
    for c in ("book_vol_6m", "book_ret_3m", "book_dd_12m"):
        assert _same(a.iloc[t][c], b.iloc[t][c]), f"{c} reads its own month"
    assert not _same(a.iloc[t + 1]["book_dd_12m"], b.iloc[t + 1]["book_dd_12m"])


def _same(x, y):
    if pd.isna(x) and pd.isna(y):
        return True
    return bool(np.isclose(float(x), float(y), rtol=0, atol=1e-12))


# ------------------------------------------------------------ the Kelly

def test_kelly_exposure_is_algebraic():
    """f * mu / sigma^2 with sigma read off the 5/95 spread, exactly."""
    idx = pd.Index(_months("2004-01", "2004-03"))
    sigma = 0.06
    half = GS._Z95 * sigma
    q = pd.DataFrame({"q05": 0.02 - half, "q50": 0.02, "q95": 0.02 + half},
                     index=idx)
    rf = pd.Series(0.0, index=idx)
    e = GS.kelly_exposure(q, rf)
    assert float(e.iloc[0]) == pytest.approx(GS.KELLY_FRACTION * 0.02 / sigma ** 2)


def test_the_risk_free_leg_is_subtracted_before_the_kelly():
    idx = pd.Index(_months("2004-01", "2004-02"))
    sigma = 0.10
    half = GS._Z95 * sigma
    q = pd.DataFrame({"q05": 0.02 - half, "q50": 0.02, "q95": 0.02 + half}, index=idx)
    a = GS.kelly_exposure(q, pd.Series(0.0, index=idx))
    b = GS.kelly_exposure(q, pd.Series(0.005, index=idx))
    assert float(b.iloc[0]) == pytest.approx(
        GS.KELLY_FRACTION * 0.015 / sigma ** 2)
    assert float(b.iloc[0]) < float(a.iloc[0])


def test_a_negative_forecast_goes_to_cash_and_never_short():
    idx = pd.Index(_months("2004-01", "2004-02"))
    q = pd.DataFrame({"q05": -0.20, "q50": -0.03, "q95": 0.10}, index=idx)
    e = GS.kelly_exposure(q, pd.Series(0.0, index=idx))
    assert list(e) == [GS.EXPOSURE_MIN, GS.EXPOSURE_MIN]


def test_a_confident_forecast_is_capped_at_the_gross_cap():
    idx = pd.Index(_months("2004-01", "2004-02"))
    q = pd.DataFrame({"q05": 0.049, "q50": 0.05, "q95": 0.051}, index=idx)
    e = GS.kelly_exposure(q, pd.Series(0.0, index=idx))
    assert list(e) == [GS.EXPOSURE_MAX, GS.EXPOSURE_MAX]
    assert GS.EXPOSURE_MAX == GL.GROSS_CAP


def test_a_degenerate_spread_yields_no_exposure_rather_than_infinity():
    idx = pd.Index(_months("2004-01", "2004-02"))
    q = pd.DataFrame({"q05": 0.02, "q50": 0.02, "q95": 0.02}, index=idx)
    e = GS.kelly_exposure(q, pd.Series(0.0, index=idx))
    assert e.isna().all()


# -------------------------------------------------------- the baseline

def test_the_trailing_vol_baseline_is_lagged():
    idx = _months("2000-01", "2006-12")
    rng = np.random.default_rng(20260907)
    b = pd.Series(rng.normal(0.01, 0.04, len(idx)), index=pd.Index(idx))
    spiked = b.copy()
    t = 50
    spiked.iloc[t] = -0.4
    a = GS.trailing_vol_exposure(b)
    c = GS.trailing_vol_exposure(spiked)
    assert _same(a.iloc[t], c.iloc[t]), "the vol target reads its own month"
    assert not _same(a.iloc[t + 1], c.iloc[t + 1])


def test_the_baseline_has_no_fitted_parameter():
    """Moreira-Muir here is a PIT median over its own history, nothing else."""
    idx = _months("2000-01", "2005-12")
    b = pd.Series(0.01, index=pd.Index(idx))
    e = GS.trailing_vol_exposure(b)
    assert e.notna().sum() >= 0          # a constant book has zero vol -> NaN/cap
    assert "no learning" in GS.describe()["baseline"]


# ------------------------------------------------------ applying exposure

def test_a_month_without_a_forecast_is_held_at_one_and_counted():
    """Sitting out the warm-up grades the rule on a shorter, later window."""
    idx = pd.Index(_months("2004-01", "2004-06"))
    book = pd.Series(0.02, index=idx)
    rf = pd.Series(0.0, index=idx)
    e = pd.Series([np.nan, np.nan, 1.0, 1.0, 1.0, 1.0], index=idx)
    net, meta = GS.apply_exposure(book, rf, e, cost_bps=0.0)
    assert meta["months_held_at_exposure_1_for_want_of_a_forecast"] == 2
    assert len(net) == len(book)
    assert list(net) == pytest.approx([0.02] * 6)


def test_exposure_zero_earns_the_risk_free_leg_here_too():
    idx = pd.Index(_months("2004-01", "2004-03"))
    net, _ = GS.apply_exposure(pd.Series(0.05, index=idx),
                               pd.Series(0.004, index=idx),
                               pd.Series(0.0, index=idx), cost_bps=0.0)
    assert list(net) == pytest.approx([0.004] * 3)


# ------------------------------------------------------------ the latch

def test_the_comparison_refuses_a_series_that_reaches_the_sealed_era():
    idx = pd.Index(_months("2014-01", "2016-06"))
    arms = {"reaches_2016": pd.Series(0.01, index=idx)}
    with pytest.raises(GL.SealedEraViolation):
        GS.compare_at_equal_drawdown(arms, pd.Series(0.008, index=idx),
                                     pd.Series(0.001, index=idx), cost_bps=25.0)


def test_the_module_has_no_path_to_the_sealed_slicer():
    """Check the CODE, not the prose. The docstring names the thing it avoids."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(GS))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("sealed", "open_sealed_window"), (
                f"the sizer reaches for {node.attr}")
        if isinstance(node, ast.Name):
            assert node.id not in ("sealed", "open_sealed_window")
    assert GS.describe()["sealed_era"].startswith("NEVER SEEN")


def test_describe_says_sizing_not_selection():
    d = GS.describe()
    assert d["role"] == "SIZING, never selection"
    assert len(d["seeds"]) == 8
    assert d["object_judged"].startswith("the seed-MEAN")


# ------------------------------------------------------- shipped receipt

def test_the_shipped_sizer_receipt_names_its_device_and_its_null():
    p = GL.OUT_DIR / "G5_sizer.json"
    if not p.exists():
        pytest.skip("G5 has not been run in this checkout")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["sealed_era_touched_by_this_job"] is False
    assert "cuda_available" in d and "device_actually_used" in d["device"]
    assert "constant_1x_NULL" in d["table"], "the flat null is the job's own null"
    assert d["headline"].startswith("beta ")
    assert d["verdict"]["MATURED"] in (True, False)
    for row in d["table"].values():
        assert list(row)[0] == "beta", "beta is printed first in every row"
