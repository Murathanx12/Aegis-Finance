"""An interval that is too narrow is worse than no interval at all.

Every farm number so far is a point on one price path. These two tools give it
width — and the ways they can silently give the WRONG width are what this file
pins:

  * an i.i.d. bootstrap on serially-dependent returns returns an interval far
    too narrow, so `test_block_bootstrap_is_WIDER_than_iid...` plants
    dependence and asserts the block version notices;
  * a bootstrap on too few observations produces resamples that are near-copies
    of each other, so the module REFUSES rather than reporting a confident tiny
    interval;
  * White's Reality Check must actually price the search — a leaderboard of pure
    noise must not hand its top row a small p.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.portfolio_farm import bootstrap as B


def _ar1(n, rho=0.4, scale=0.01, seed=1):
    """Serially dependent returns — the thing an i.i.d. bootstrap destroys."""
    rng = np.random.default_rng(seed)
    e = rng.normal(0, scale, n)
    x = np.empty(n)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = rho * x[i - 1] + e[i]
    return x


# ── the interval ────────────────────────────────────────────────────────────


def test_a_flat_difference_gives_an_interval_that_CONTAINS_zero():
    rng = np.random.default_rng(7)
    s = rng.normal(0.0004, 0.01, 3000)
    out = B.excess_interval(s, s.copy(), n_boot=300)
    assert out["status"] == "ok"
    assert out["excess_annual_pct"] == pytest.approx(0.0, abs=1e-6)
    assert not out["excludes_zero"]


def test_a_REAL_edge_is_detected_and_the_interval_excludes_zero():
    rng = np.random.default_rng(11)
    b = rng.normal(0.0004, 0.01, 3000)
    s = b + 0.0006                      # ~15%/yr of pure, noiseless excess
    out = B.excess_interval(s, b, n_boot=300)
    assert out["excess_annual_pct"] > 10
    assert out["excludes_zero"] and out["ci_lo_pct"] > 0


def test_block_bootstrap_is_WIDER_than_a_one_day_block_on_dependent_data():
    """The reason blocks exist. With rho=0.4 in the difference series, a
    block length of 1 (i.i.d.) understates the width; the declared 21-day
    block must produce a visibly wider interval on the same data."""
    d = _ar1(4000, rho=0.4)
    b = np.zeros_like(d)
    wide = B.excess_interval(d, b, n_boot=400, mean_block=21)
    narrow = B.excess_interval(d, b, n_boot=400, mean_block=1)
    w = wide["ci_hi_pct"] - wide["ci_lo_pct"]
    n = narrow["ci_hi_pct"] - narrow["ci_lo_pct"]
    assert w > n * 1.2, (
        f"block interval {w:.2f} is not meaningfully wider than the i.i.d. "
        f"one {n:.2f} — the block structure is not being used, and every "
        f"interval this module reports on real returns is too narrow")


def test_TOO_SHORT_refuses_rather_than_returning_a_confident_tiny_interval():
    out = B.excess_interval(np.zeros(50), np.zeros(50), mean_block=21)
    assert out["status"] == "too_short"
    assert out["needed"] > out["n_obs"]
    assert "understate" in out["why"]


def test_the_result_is_reproducible_from_its_seed():
    d = _ar1(2000)
    a = B.excess_interval(d, np.zeros_like(d), n_boot=200, seed=5)
    b = B.excess_interval(d, np.zeros_like(d), n_boot=200, seed=5)
    assert a == b


# ── the reality check ───────────────────────────────────────────────────────


def test_a_leaderboard_of_PURE_NOISE_does_not_get_a_small_p():
    """The whole point. 40 policies of zero-mean noise: the best of them looks
    good, and the Reality Check must say so is expected."""
    rng = np.random.default_rng(3)
    cols = {f"p{i}": rng.normal(0.0, 0.01, 2000) for i in range(40)}
    out = B.reality_check(cols, n_boot=300)
    assert out["status"] == "ok" and out["n_policies"] == 40
    assert out["reality_check_p"] > 0.10, (
        f"p={out['reality_check_p']} on pure noise — the check is not pricing "
        f"the search, and every leaderboard it blesses is a maximum")


def test_a_GENUINE_standout_among_noise_gets_a_small_p():
    rng = np.random.default_rng(4)
    cols = {f"p{i}": rng.normal(0.0, 0.01, 2000) for i in range(40)}
    cols["real"] = rng.normal(0.0015, 0.01, 2000)     # ~38%/yr
    out = B.reality_check(cols, n_boot=300)
    assert out["best_policy"] == "real"
    assert out["reality_check_p"] < 0.05


def test_no_policies_is_a_status_not_a_crash():
    assert B.reality_check({})["status"] == "no_policies"


def test_daily_returns_handles_the_first_row_and_zero_navs():
    r = B.daily_returns([100.0, 110.0, 0.0, 50.0])
    assert np.isnan(r[0])
    assert r[1] == pytest.approx(0.10)
    assert np.isnan(r[3]), "a zero NAV must not produce an infinite return"


# ── the power check ─────────────────────────────────────────────────────────


def test_a_high_vol_strategy_CANNOT_resolve_a_modest_edge_in_a_short_sample():
    """The candidate's own situation: a real-looking excess inside a tracking
    error so large that twelve years cannot separate it from zero. The check
    must say so rather than reporting the excess and stopping."""
    rng = np.random.default_rng(21)
    n = 252 * 12
    b = rng.normal(0.0005, 0.011, n)
    # The noise is DE-MEANED so the realised excess is exactly the drift. The
    # first version drew the drift and the noise together and the noise won —
    # realised excess came back NEGATIVE, which is itself the point this test
    # is about, but it made the fixture test nothing.
    e = rng.normal(0.0, 0.022, n)
    s = b + 0.0006 + (e - e.mean())            # 15.1%/yr excess at ~35% TE
    out = B.power_check(s, b)
    assert out["status"] == "ok"
    assert out["observed_excess_annual_pct"] > 5
    assert out["mde_at_80pct_power_annual_pct"] > out["observed_excess_annual_pct"]
    assert out["sample_can_resolve_observed_effect"] is False
    assert out["years_needed_for_observed_effect"] > 12


def test_a_low_vol_edge_IS_resolvable_in_the_same_sample_length():
    """Calibration: the check must not simply always say 'underpowered'."""
    rng = np.random.default_rng(22)
    n = 252 * 12
    b = rng.normal(0.0005, 0.011, n)
    e = rng.normal(0.0, 0.002, n)
    s = b + 0.0006 + (e - e.mean())            # same edge, tiny tracking error
    out = B.power_check(s, b)
    assert out["sample_can_resolve_observed_effect"] is True
    assert out["years_needed_for_observed_effect"] < 12


def test_power_check_refuses_a_sample_under_a_year():
    assert B.power_check(np.zeros(100), np.zeros(100))["status"] == "too_short"
