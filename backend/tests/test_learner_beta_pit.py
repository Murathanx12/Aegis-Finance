"""The two things about the PRE-PERIOD BETA that must never quietly stop being true.

`learner/beta.py` exists to answer one question -- is the band overlay's excess
selection or a leverage tilt -- and it can be wrong in exactly one way that
still looks green: a beta fitted on the return it is later used to explain.
That failure produces a *better* looking decomposition, not a crash, and no
receipt would flag it. So:

1. `attach` never reads a beta dated on or after the row's `entry_date`;
2. the cumulative-sum rolling OLS equals a brute-force per-window OLS.

(2) matters because the fast path is the only path -- 5,700 names x 3,270
sessions is not going to be recomputed by a groupby-rolling-cov, so the
optimisation IS the estimator and it needs a slow twin to check it against.

Runs OFFLINE on synthetic frames in well under a second. Dates are DERIVED from
`today`, never literal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from learner import beta as B


def test_attach_never_reads_a_beta_on_or_after_entry_date():
    """The lookahead guard. A beta stamped ON the entry date must not be used;
    the last strictly-earlier one must be."""
    today = pd.Timestamp.today().normalize()
    entry = today - pd.Timedelta(days=30)
    panel = pd.DataFrame({
        "permno": [10001, 10001, 10001],
        "date": [entry - pd.Timedelta(days=3), entry - pd.Timedelta(days=1), entry],
        # the value ON entry day is poisoned: if it is ever read, the assert fires
        "beta_pre": [0.5, 1.5, 999.0],
    })
    df = pd.DataFrame({"permno": [10001], "entry_date": [entry]})
    got = B.attach(df, panel)
    assert float(got.iloc[0]) == 1.5, (
        "attach read a beta dated on or after entry_date -- the estimation window "
        "would then contain the return it is used to explain")


def test_attach_preserves_row_alignment_under_an_unsorted_frame():
    """merge_asof re-sorts. If the result is not put back on the caller's index,
    every beta lands on the wrong row and nothing fails loudly."""
    today = pd.Timestamp.today().normalize()
    entries = [today - pd.Timedelta(days=d) for d in (10, 90, 50)]
    panel = pd.DataFrame({
        "permno": [10001, 10002, 10003],
        "date": [e - pd.Timedelta(days=1) for e in entries],
        "beta_pre": [1.1, 2.2, 3.3],
    })
    df = pd.DataFrame({"permno": [10001, 10002, 10003], "entry_date": entries},
                      index=[7, 3, 11])
    got = B.attach(df, panel)
    assert list(got.index) == [7, 3, 11]
    assert [round(float(v), 3) for v in got] == [1.1, 2.2, 3.3]


def test_rolling_ols_matches_a_brute_force_window_regression():
    """The fast estimator IS the estimator. Check it against the slow one."""
    rng = np.random.default_rng(11)
    T, N, W, MIN = 400, 6, 120, 60
    x = rng.normal(0.0, 0.01, T)
    true_beta = np.array([0.4, 0.8, 1.0, 1.3, 1.9, 2.5])
    Y = x[:, None] * true_beta[None, :] + rng.normal(0.0, 0.01, (T, N))
    # scatter some NaNs -- a real panel has them, and they must be excluded
    # pairwise rather than zero-filled
    Y[rng.random((T, N)) < 0.05] = np.nan

    fast = B._rolling_ols_beta(Y, x, W, MIN)

    for t in (150, 275, T - 1):
        for j in range(N):
            lo = max(0, t + 1 - W)
            yy = Y[lo:t + 1, j]
            xx = x[lo:t + 1]
            m = np.isfinite(yy)
            if m.sum() < MIN:
                assert not np.isfinite(fast[t, j])
                continue
            slow = np.polyfit(xx[m], yy[m], 1)[0]
            assert abs(fast[t, j] - slow) < 1e-8, (
                f"cumsum rolling beta disagrees with a per-window OLS at t={t}, col={j}")


def test_rolling_ols_refuses_below_the_minimum_observation_floor():
    """Fewer than 60 usable sessions is NaN, never a beta fitted on 3 points."""
    x = np.linspace(-0.02, 0.02, 100)
    Y = np.full((100, 1), np.nan)
    Y[:40, 0] = x[:40] * 1.5          # only 40 usable observations, ever
    out = B._rolling_ols_beta(Y, x, 120, 60)
    assert not np.isfinite(out).any(), (
        "a beta was produced from fewer than the declared 60-session floor")
