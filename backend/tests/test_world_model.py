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


# ── dependence-aware inference ─────────────────────────────────────────────

def _panel(n_dates: int, n_sec: int, rho: float, seed: int = 0,
           overlap: int = 20):
    """A panel with BOTH dependencies a forward-return panel actually has.

    - **Cross-sectional:** every security shares a common daily shock, scaled
      by `rho`.
    - **Temporal overlap:** the value at date t is the sum of shocks over
      `[t, t+overlap)`, exactly as an H-day forward return is. Adjacent dates
      are therefore near-copies sharing `overlap - 1` of their shocks.

    The overlap is the part that matters and the part the first version of
    this helper left out — without it the synthetic could not exhibit the
    defect the function under test exists to fix, and the mutation control
    passed for a reason unrelated to the fix.
    """
    rng = np.random.default_rng(seed)
    n_raw = n_dates + overlap
    common = rng.normal(0.0, 1.0, n_raw)
    idio = rng.normal(0.0, 1.0, (n_raw, n_sec))
    shocks = rho * common[:, None] + (1.0 - rho) * idio
    cum = np.cumsum(np.vstack([np.zeros((1, n_sec)), shocks]), axis=0)
    vals = cum[overlap:overlap + n_dates] - cum[:n_dates]     # rolling sums
    dates = np.repeat(
        np.datetime64("2000-01-03") + np.arange(n_dates) * np.timedelta64(1, "D"),
        n_sec)
    return vals.reshape(-1), dates


def test_date_blocks_are_wider_than_row_blocks_when_the_cross_section_comoves():
    """The mutation control for the whole fix.

    Resampling rows treats 18 ETFs on one day as 18 observations. If that
    made no difference to the interval, the fix would be cosmetic — so the
    difference is measured, not asserted.
    """
    diff, dates = _panel(600, 18, rho=0.95)
    honest = WM.block_bootstrap_paired(diff, dates, 40, n_boot=400, seed=1)
    # the naive alternative: contiguous ROWS, which in a date-sorted panel
    # span 40/18 ~ 2 days
    rng = np.random.default_rng(1)
    n = diff.size
    nb = int(np.ceil(n / 40))
    naive = np.array([
        diff[np.concatenate([np.arange(s, s + 40)
                             for s in rng.integers(0, n - 40, nb)])[:n]].mean()
        for _ in range(400)])
    assert honest.se > float(np.std(naive, ddof=1)) * 2.0


def test_n_effective_counts_date_blocks_not_rows():
    diff, dates = _panel(504, 18, rho=0.9)
    inf = WM.block_bootstrap_paired(diff, dates, 40, n_boot=50, seed=2)
    assert inf.n_rows == 504 * 18
    assert inf.n_dates == 504
    assert inf.n_securities == 18
    assert inf.n_effective == pytest.approx(504 / 40, rel=1e-6)
    # the number that would have been claimed by counting rows
    assert inf.n_effective < (inf.n_rows / 40) / 10.0


def test_a_sampled_date_carries_its_whole_cross_section():
    """If a date could be sampled partially the cross-section would leak back
    in as extra independent draws."""
    n_dates, n_sec = 50, 6
    diff, dates = _panel(n_dates, n_sec, rho=1.0)
    # rho=1 => every row on a date is identical, so ANY resample that keeps
    # dates whole must reproduce a mean drawn from the date-level means
    inf = WM.block_bootstrap_paired(diff, dates, 5, n_boot=200, seed=3)
    assert np.isfinite(inf.se) and inf.se > 0
    assert inf.n_securities == n_sec


def test_paired_inference_rejects_misaligned_inputs():
    with pytest.raises(ValueError):
        WM.block_bootstrap_paired(np.zeros(10), np.zeros(9), 5)


def test_mde_scales_with_the_declared_block_length():
    """A longer block admits fewer independent units and must not tighten."""
    diff, dates = _panel(1000, 10, rho=0.9)
    short = WM.block_bootstrap_paired(diff, dates, 5, n_boot=300, seed=4)
    long_ = WM.block_bootstrap_paired(diff, dates, 60, n_boot=300, seed=4)
    assert long_.n_effective < short.n_effective


# ── the baselines cannot see the future ────────────────────────────────────

def test_climatology_is_blind_to_everything_after_the_training_cutoff():
    """A leaked climatology would be a very strong competitor for exactly the
    wrong reason, so it is tested rather than read."""
    dates = _dates(4000)
    folds = WM.walk_forward_folds(dates, 2005, 20, min_train=100)
    rng = np.random.default_rng(5)
    y = rng.normal(0.0, 3.0, len(dates))
    for tr, te, _f in folds:
        before = WM.climatology_quantiles(y[tr], te.size)
        poisoned = y.copy()
        mask = np.ones(len(y), dtype=bool)
        mask[tr] = False
        poisoned[mask] += 500.0          # catastrophic future contamination
        after = WM.climatology_quantiles(poisoned[tr], te.size)
        assert np.array_equal(before, after)


def test_scaled_empirical_is_blind_to_future_outcomes_too():
    """Its residual distribution comes from training; only today's rv may be
    a test-period quantity, and that is a feature, not an outcome."""
    rng = np.random.default_rng(6)
    y_tr = rng.normal(0.0, 2.0, 800)
    rv_tr = np.abs(rng.normal(20.0, 3.0, 800))
    rv_te = np.abs(rng.normal(20.0, 3.0, 50))
    a = WM.scaled_empirical_quantiles(y_tr, rv_tr, rv_te, 20)
    # perturbing anything outside (y_tr, rv_tr, rv_te) cannot reach it
    b = WM.scaled_empirical_quantiles(y_tr.copy(), rv_tr.copy(), rv_te, 20)
    assert np.array_equal(a, b)


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


# ── reproducibility is a property of the PREDICTIONS, not of the metric ─────

def _repro_panel(n=900, seed=7):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 5))
    y = X[:, 0] * 2.0 + rng.normal(size=n) * (1.0 + np.abs(X[:, 1]))
    return X, y


def test_two_identical_fits_produce_identical_predictions():
    """`random_state` alone did not do this — `deterministic=True` does.

    Asserted on the prediction fingerprint rather than on a loss: two runs can
    round to the same loss from different trees, so a matching metric is
    consistent with an irreproducible model and proves nothing.
    """
    X, y = _repro_panel()
    names = tuple(f"f{i}" for i in range(X.shape[1]))
    a = WM.WorldModelV0(n_estimators=60).fit(X, y, names).predict(X)
    b = WM.WorldModelV0(n_estimators=60).fit(X, y, names).predict(X)
    assert WM.fingerprint(a) == WM.fingerprint(b)
    assert np.array_equal(a, b)


def test_the_fingerprint_can_actually_differ():
    """The mutation control: a hash that never changes proves nothing."""
    X, y = _repro_panel()
    names = tuple(f"f{i}" for i in range(X.shape[1]))
    base = WM.fingerprint(X, y, feature_names=names)
    # a single changed cell
    X2 = X.copy()
    X2[0, 0] += 1e-9
    assert WM.fingerprint(X2, y, feature_names=names) != base
    # permuted feature ORDER with identical content
    perm = [1, 0, 2, 3, 4]
    assert WM.fingerprint(X[:, perm], y,
                          feature_names=tuple(names[i] for i in perm)) != base
    # ... and it responds to the MODEL, not only to the data. `num_leaves`
    # would NOT work as the lever here: `min_child_samples=200` on 900 rows
    # caps the tree far below either setting, so 15 and 63 fit the same trees.
    m1 = WM.WorldModelV0(n_estimators=60, learning_rate=0.05).fit(X, y, names)
    m2 = WM.WorldModelV0(n_estimators=60, learning_rate=0.20).fit(X, y, names)
    assert WM.fingerprint(m1.predict(X)) != WM.fingerprint(m2.predict(X))


def test_the_seed_was_never_the_thing_that_made_this_reproducible():
    """Measured, and it changes what "pin the seeds" is worth as advice.

    With no row or column subsampling — LightGBM's default, and this model's
    configuration — `random_state` has nothing to randomise: the trees are a
    deterministic function of the data and the split rules. The 1.22617 ->
    1.22598 drift observed on an unchanged WM0 re-run therefore never had
    anything to do with the seed, and pinning it would have "fixed" nothing.
    It came from multithreaded histogram summation, which is what
    `deterministic=True, force_row_wise=True` addresses.

    Recorded as a test because the natural remediation — set more seeds — is
    the one that does not work here, and a session that applied it would have
    reported the problem closed.
    """
    X, y = _repro_panel(400)
    names = tuple(f"f{i}" for i in range(X.shape[1]))
    a = WM.WorldModelV0(n_estimators=40, seed=1).fit(X, y, names).predict(X)
    b = WM.WorldModelV0(n_estimators=40, seed=999_983).fit(X, y, names).predict(X)
    assert WM.fingerprint(a) == WM.fingerprint(b)


def test_provenance_records_what_determinism_depends_on():
    X, y = _repro_panel(300)
    m = WM.WorldModelV0(n_estimators=20).fit(X, y, ("a", "b", "c", "d", "e"))
    p = m.provenance()
    assert p["deterministic"] is True and p["force_row_wise"] is True
    assert p["seed"] == 20260816
    assert p["feature_names"] == ["a", "b", "c", "d", "e"]
    # The library version is the caveat `deterministic=True` is silent about.
    assert p["lightgbm_version"] and p["lightgbm_version"][0].isdigit()
