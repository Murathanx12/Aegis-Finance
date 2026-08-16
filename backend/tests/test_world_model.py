"""World Model v0 primitives: the scoring rule, the embargo, the baselines.

The walk-forward embargo gets a test that would FAIL without it — a purge
nobody has watched skip a row is a purge that will be quietly removed.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services import world_model as WM


# ── scoring ────────────────────────────────────────────────────────────────

def test_pinball_loss_is_minimised_at_the_true_quantile():
    """The property that makes it a proper scoring rule."""
    rng = np.random.default_rng(0)
    y = rng.normal(0.0, 1.0, 20000)
    tau = (0.25,)
    truth = np.quantile(y, 0.25)
    at_truth = WM.pinball_loss(y, np.full((len(y), 1), truth), tau).mean()
    for wrong in (truth - 0.3, truth + 0.3, 0.0, 1.0):
        assert WM.pinball_loss(
            y, np.full((len(y), 1), wrong), tau).mean() > at_truth


def test_pinball_loss_is_asymmetric_in_the_declared_direction():
    """tau=0.05 must punish over-prediction far harder than under-prediction."""
    y = np.array([0.0])
    over = WM.pinball_loss(y, np.array([[1.0]]), (0.05,))[0, 0]
    under = WM.pinball_loss(y, np.array([[-1.0]]), (0.05,))[0, 0]
    assert over == pytest.approx(0.95)
    assert under == pytest.approx(0.05)
    assert over > under


def test_pinball_loss_is_not_pre_averaged_over_quantiles():
    """The hypothesis lives in specific quantiles; averaging would hide it."""
    y = np.zeros(7)
    q = np.tile(np.linspace(-2, 2, len(WM.QUANTILES)), (7, 1))
    assert WM.pinball_loss(y, q).shape == (7, len(WM.QUANTILES))


def test_pit_coverage_recovers_tau_on_a_correctly_specified_model():
    rng = np.random.default_rng(1)
    y = rng.normal(0.0, 1.0, 50000)
    from scipy.stats import norm
    q = np.tile(norm.ppf(WM.QUANTILES), (len(y), 1))
    cov = WM.pit_coverage(y, q)
    assert np.allclose(cov, WM.QUANTILES, atol=0.01)


def test_enforce_monotone_repairs_crossing_and_cannot_worsen_loss():
    y = np.array([0.5, -1.2, 0.0])
    crossed = np.array([[1.0, -1.0, 0.5, 0.2, 2.0, 0.1, 1.5]] * 3)
    fixed = WM.enforce_monotone(crossed)
    assert (np.diff(fixed, axis=1) >= 0).all()
    assert (WM.pinball_loss(y, fixed).mean()
            <= WM.pinball_loss(y, crossed).mean() + 1e-12)


# ── baselines ──────────────────────────────────────────────────────────────

def test_climatology_ignores_today_entirely():
    y_tr = np.array([-5.0, -1.0, 0.0, 1.0, 6.0] * 40)
    q = WM.climatology_quantiles(y_tr, 3)
    assert q.shape == (3, len(WM.QUANTILES))
    assert (q[0] == q[1]).all() and (q[1] == q[2]).all()


def test_gaussian_vol_widens_with_todays_volatility():
    y_tr = np.zeros(500)
    q = WM.gaussian_vol_quantiles(y_tr, np.array([10.0, 40.0]), 20)
    width_calm = q[0, -1] - q[0, 0]
    width_stressed = q[1, -1] - q[1, 0]
    assert width_stressed > width_calm * 3.5


def test_scaled_empirical_is_fat_tailed_relative_to_gaussian():
    """The comparator's whole advantage: empirical tails, not normal ones."""
    rng = np.random.default_rng(2)
    # Student-t outcomes at constant vol => fatter than normal
    rv = np.full(20000, 20.0)
    scale = 20.0 * np.sqrt(20 / WM.TRADING_DAYS)
    y = rng.standard_t(3, 20000) * scale
    g = WM.gaussian_vol_quantiles(y, np.array([20.0]), 20)
    s = WM.scaled_empirical_quantiles(y, rv, np.array([20.0]), 20)
    assert s[0, 0] < g[0, 0]          # 5th percentile further out
    assert s[0, -1] > g[0, -1]        # 95th percentile further out


def test_scaled_empirical_survives_zero_volatility_rows():
    y = np.array([1.0, -1.0, 0.5] * 100)
    rv_tr = np.array([0.0, 20.0, 20.0] * 100)
    out = WM.scaled_empirical_quantiles(y, rv_tr, np.array([20.0]), 20)
    assert np.isfinite(out).all()


# ── the embargo ────────────────────────────────────────────────────────────

def _dates(n: int) -> np.ndarray:
    return (np.datetime64("2000-01-01")
            + np.arange(n) * np.timedelta64(1, "D"))


def test_folds_are_temporal_and_never_train_on_the_future():
    dates = _dates(4000)
    folds = WM.walk_forward_folds(dates, 2005, 20, min_train=100)
    assert folds
    for tr, te, _f in folds:
        assert dates[tr].max() < dates[te].min()


def test_the_embargo_actually_drops_rows_at_the_boundary():
    """Would pass trivially if the purge were removed — so it is measured.

    The gap between the last training date and the first test date must exceed
    the horizon, not merely be positive.
    """
    dates = _dates(4000)
    horizon = 20
    folds = WM.walk_forward_folds(dates, 2005, horizon, min_train=100)
    for tr, te, _f in folds:
        gap_days = (dates[te].min() - dates[tr].max()).astype(int)
        assert gap_days > horizon, (
            f"only {gap_days}d between train end and test start; a {horizon}d "
            f"forward return overlaps the test window")


def test_a_larger_horizon_purges_more():
    dates = _dates(4000)
    small = WM.walk_forward_folds(dates, 2005, 5, min_train=100)
    large = WM.walk_forward_folds(dates, 2005, 60, min_train=100)
    assert small[0][0].size > large[0][0].size


def test_folds_are_skipped_rather_than_shrunk_below_min_train():
    dates = _dates(4000)
    folds = WM.walk_forward_folds(dates, 2000, 20, min_train=2000)
    assert all(f[2].n_train >= 2000 for f in folds)


# ── the model ──────────────────────────────────────────────────────────────

def test_the_model_produces_monotone_quantiles_on_real_noise():
    rng = np.random.default_rng(3)
    n = 3000
    X = rng.normal(size=(n, 3))
    y = X[:, 0] * 2.0 + rng.normal(0.0, 1.0 + np.abs(X[:, 1]), n)
    m = WM.WorldModelV0(n_estimators=40).fit(X, y, ("a", "b", "c"))
    p = m.predict(X[:200])
    assert p.shape == (200, len(WM.QUANTILES))
    assert (np.diff(p, axis=1) >= 0).all()


def test_the_model_widens_where_the_noise_is_wider():
    """Sanity: it must at least learn heteroskedasticity it was shown."""
    rng = np.random.default_rng(4)
    n = 6000
    X = rng.uniform(0.0, 1.0, size=(n, 1))
    y = rng.normal(0.0, 0.2 + 3.0 * X[:, 0], n)
    m = WM.WorldModelV0(n_estimators=120, min_child_samples=50).fit(
        X, y, ("x",))
    p = m.predict(np.array([[0.05], [0.95]]))
    assert (p[1, -1] - p[1, 0]) > (p[0, -1] - p[0, 0]) * 2.0
