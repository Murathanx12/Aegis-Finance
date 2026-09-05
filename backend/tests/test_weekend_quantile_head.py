"""The quantile head is a DIFFERENT MODEL, not a relabelled mean head.

WHY THIS FILE EXISTS
====================
`models.fit_predict(..., quantile=q)` was added on 2026-09-06 so a weekend-lab
variant could ask "is the right tail more predictable than the mean?". The
failure that variant was one line away from is specific and quiet: if the
installed lightgbm ignored the quantile objective, all three of q0.1 / q0.5 /
q0.9 would return the SAME numbers, the job would report three identical cells,
and the receipt would call it a tail finding.

So these tests do not check that the code runs. They check the three things that
distinguish a real pinball head from a relabelled mean head:

1. the fitted BOOSTER's objective says quantile -- not the constructor's kwarg,
   which only proves the argument was stored;
2. the predictions have the COVERAGE a quantile is defined by -- about q of the
   realised values fall below the q-th quantile prediction; and
3. q0.9 and q0.1 are ordered and far apart, and q0.9 is not the mean head.

A test that only asserted "it returned an array" would pass against precisely
the bug this file exists to catch.
"""
from __future__ import annotations

import numpy as np
import pytest

from learner import models


pytestmark = pytest.mark.skipif(not models._LGBM, reason="lightgbm is not installed")


def _heteroskedastic(n=4000, seed=11):
    """A world where the tail is predictable and the MEAN is not.

    `y`'s conditional mean does not depend on x2 at all; its conditional SPREAD
    does. A mean head can learn nothing from x2; a quantile head must.
    """
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.uniform(0.2, 3.0, size=n)
    y = 0.5 * x1 + rng.normal(scale=x2)
    X = np.column_stack([x1, x2])
    return X, y


def _fit(q, seed=11):
    X, y = _heteroskedastic(seed=seed)
    cut = int(0.7 * len(y))
    m, meta = models._fit_lgbm(X[:cut], y[:cut], X[cut:], y[cut:], quantile=q)
    return m, meta, X[cut:], y[cut:]


def test_the_fitted_booster_objective_is_quantile_not_just_the_kwarg():
    """The constructor storing the kwarg is not evidence the booster used it."""
    m, meta, _X, _y = _fit(0.9)
    assert meta["objective"] == "quantile"
    assert meta["quantile_alpha"] == 0.9
    dumped = str(m.booster_.dump_model().get("objective", ""))
    assert "quantile" in dumped, f"fitted booster objective is {dumped!r}"


@pytest.mark.parametrize("q", [0.1, 0.5, 0.9])
def test_empirical_coverage_is_near_the_requested_quantile(q):
    """THE DEFINING PROPERTY. About q of realised values sit below the q-th
    quantile prediction. A mean head returns ~0.5 for every q and fails two of
    these three outright."""
    _m, _meta, Xte, yte = _fit(q)
    m2, _, _, _ = _fit(q)
    pred = m2.predict(Xte)
    covered = float((yte <= pred).mean())
    assert abs(covered - q) < 0.08, f"q={q} covered {covered:.3f}"


def test_q90_is_above_q10_on_every_row_and_far_apart():
    m_lo, _, Xte, _ = _fit(0.1)
    m_hi, _, _, _ = _fit(0.9)
    lo, hi = m_lo.predict(Xte), m_hi.predict(Xte)
    assert (hi > lo).mean() > 0.99
    # Not merely ordered -- SEPARATED. Two mean heads with different seeds would
    # be ordered on ~half the rows and separated on none.
    assert float(np.mean(hi - lo)) > 1.0


def test_the_tail_head_is_not_the_mean_head():
    """q0.9 must carry information the mean head does not. If the two rank the
    same names in the same order, the variant is asking one question twice."""
    X, y = _heteroskedastic()
    cut = int(0.7 * len(y))
    mean_m, _ = models._fit_lgbm(X[:cut], y[:cut], X[cut:], y[cut:])
    q90_m, _ = models._fit_lgbm(X[:cut], y[:cut], X[cut:], y[cut:], quantile=0.9)
    mp, qp = mean_m.predict(X[cut:]), q90_m.predict(X[cut:])
    r = float(np.corrcoef(mp, qp)[0, 1])
    assert r < 0.9, f"q0.9 and the mean head correlate {r:.3f} -- same question twice"
    assert float((qp > mp).mean()) > 0.9


def test_it_refuses_a_quantile_outside_the_open_unit_interval():
    X, y = _heteroskedastic(n=400)
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            models._fit_lgbm(X, y, X[:0], y[:0], quantile=bad)


def test_it_refuses_a_quantile_on_a_classifier():
    """A probability's quantile is not a quantity."""
    X, y = _heteroskedastic(n=400)
    with pytest.raises(ValueError):
        models._fit_lgbm(X, (y > 0).astype(float), X[:0], y[:0],
                         classifier=True, quantile=0.9)


def test_fit_predict_refuses_a_quantile_on_a_non_lgbm_arm():
    import pandas as pd
    df = pd.DataFrame({"month": ["2020-01"] * 10})
    with pytest.raises(ValueError):
        models.fit_predict("ridge", "raw", df, df, [], 1, quantile=0.9)


def test_the_default_path_is_untouched_by_the_new_argument():
    """`quantile=None` must be byte-identical to the pre-change behaviour: the
    objective stays l2 and no alpha is recorded."""
    X, y = _heteroskedastic(n=1000)
    _m, meta = models._fit_lgbm(X, y, X[:0], y[:0])
    assert meta["objective"] == "l2"
    assert meta["quantile_alpha"] is None
