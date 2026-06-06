"""
Tests for engine/validation/factor_ic.py
==========================================

Verifies the IC primitives on cases with a known answer:
  - factor == forward return            → IC = +1 every date
  - factor == -forward return           → IC = -1
  - factor independent of returns       → IC ≈ 0, t-stat small, "no skill"
  - monotone construction               → positive, monotonic quantile spread
  - t-stat identity                     → t = IR · √n
"""

import numpy as np
import pandas as pd
import pytest

from engine.validation.factor_ic import (
    analyze_factor,
    cross_sectional_ic,
    ic_by_date,
    ic_summary,
    quantile_return_spread,
)


def _panel(rng, n_dates=40, n_assets=30, rel=None):
    """Build a tidy long panel; `rel(factor)->fwd_return` sets the relationship."""
    rows = []
    for d in range(n_dates):
        f = rng.normal(0, 1, n_assets)
        if rel is None:
            r = rng.normal(0, 1, n_assets)  # independent
        else:
            r = rel(f, rng)
        for a in range(n_assets):
            rows.append({"date": d, "asset": a, "factor": f[a], "fwd": r[a]})
    return pd.DataFrame(rows)


def test_perfect_alignment_ic_is_one():
    rng = np.random.default_rng(1)
    panel = _panel(rng, rel=lambda f, rng: f.copy())  # fwd == factor
    ic = ic_by_date(panel, "factor", "fwd")
    assert ic.mean() == pytest.approx(1.0, abs=1e-9)


def test_perfect_inverse_ic_is_minus_one():
    rng = np.random.default_rng(2)
    panel = _panel(rng, rel=lambda f, rng: -f)
    ic = ic_by_date(panel, "factor", "fwd")
    assert ic.mean() == pytest.approx(-1.0, abs=1e-9)


def test_independent_factor_has_no_skill():
    rng = np.random.default_rng(3)
    panel = _panel(rng, n_dates=60, n_assets=40, rel=None)
    summary = ic_summary(ic_by_date(panel, "factor", "fwd"))
    assert abs(summary["mean_ic"]) < 0.05
    assert summary["verdict"] == "no measurable skill"


def test_noisy_real_signal_detected():
    """A factor with a modest true relationship should register usable skill."""
    rng = np.random.default_rng(4)
    panel = _panel(rng, n_dates=80, n_assets=50,
                   rel=lambda f, rng: 0.5 * f + rng.normal(0, 1, len(f)))
    summary = ic_summary(ic_by_date(panel, "factor", "fwd"))
    assert summary["mean_ic"] > 0.05
    assert summary["t_stat"] > 2.0
    assert summary["verdict"] == "usable signal"


def test_cross_sectional_ic_guards():
    # Too few assets → NaN
    assert np.isnan(cross_sectional_ic(pd.Series([1, 2]), pd.Series([1, 2])))
    # No variance → NaN
    f = pd.Series([1, 1, 1, 1, 1, 1])
    r = pd.Series([1, 2, 3, 4, 5, 6])
    assert np.isnan(cross_sectional_ic(f, r))


def test_quantile_spread_monotonic_for_real_factor():
    rng = np.random.default_rng(5)
    panel = _panel(rng, n_dates=60, n_assets=50,
                   rel=lambda f, rng: 0.8 * f + rng.normal(0, 0.5, len(f)))
    spread = quantile_return_spread(panel, "factor", "fwd", n_quantiles=5)
    assert spread["available"]
    assert spread["top_minus_bottom"] > 0
    assert spread["monotonic_increasing"]


def test_tstat_equals_ir_times_sqrt_n():
    ic = pd.Series([0.05, 0.03, 0.07, 0.02, 0.06, 0.04, 0.05, 0.03, 0.06, 0.04])
    s = ic_summary(ic)
    expected_t = s["ic_ir"] * np.sqrt(s["n_periods"])
    assert s["t_stat"] == pytest.approx(expected_t, abs=1e-2)


def test_ic_summary_empty():
    assert ic_summary(pd.Series([], dtype=float))["n_periods"] == 0


def test_analyze_factor_shape():
    rng = np.random.default_rng(6)
    panel = _panel(rng, rel=lambda f, rng: 0.4 * f + rng.normal(0, 1, len(f)))
    out = analyze_factor(panel, "factor", "fwd")
    assert set(out) == {"factor", "ic", "quantiles"}
    assert out["ic"]["n_periods"] > 0
