"""E3: the interval has to break where it is known to break, and recover where
it is claimed to recover.

Coverage is the one statistic that cannot be checked by reading the code: a
method that returns an interval always returns an interval, and only the
realised frequency says whether it meant anything. So the known-answer here is
a planted regime shift -- the point forecast stays CORRECT and only the error
scale triples, which isolates distribution shift from a forecasting failure --
and three facts are asserted, all three from the same run:

* plain split conformal's realised coverage COLLAPSES after the shift (the
  ~90% -> ~50% failure `research_nn.md` section 4 flags for daily equity
  returns);
* ACI comes back within a tolerance, at a `k` that is swept and reported;
* the non-exchangeable weighting is at least as fast -- checked, not assumed.

The rest pins the arithmetic that a refactor could quietly change: the weighted
quantile against numpy on the uniform case, `rho = 1.0` being exactly the
unweighted path, the Gibbs-Candes update by hand, and the refusal shapes (an
ungraded step is -1 and never 0; a tercile with fewer than 10 blocks says
CANNOT DETERMINE rather than dividing by four observations).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import conformal                             # noqa: E402
from scripts import night_e3_adaptive_conformal as e3              # noqa: E402


# ---------------------------------------------------------------------------
# the arithmetic
# ---------------------------------------------------------------------------
def test_uniform_weighted_quantile_agrees_with_numpy():
    rng = np.random.default_rng(0)
    v = rng.normal(size=400)
    for level in (0.5, 0.8, 0.9, 0.95):
        mine = conformal.weighted_quantile(v, level)
        # `inverted_cdf` IS the convention here: the smallest value whose
        # cumulative share reaches `level`. `higher` interpolates the rank and
        # lands one index further at the grid points, which is a different
        # estimator, not a rounding difference.
        ref = float(np.quantile(v, level, method="inverted_cdf"))
        assert mine == pytest.approx(ref, abs=1e-9), f"level {level}"


def test_rho_one_is_exactly_the_unweighted_path():
    w = conformal.recency_weights(50, 1.0)
    assert np.all(w == 1.0)
    v = np.linspace(0, 1, 50)
    assert conformal.weighted_quantile(v, 0.9, w) == conformal.weighted_quantile(v, 0.9)


def test_recency_weights_favour_the_recent_end():
    w = conformal.recency_weights(5, 0.5)
    assert w[-1] == pytest.approx(1.0)
    assert w[0] == pytest.approx(0.5 ** 4)
    assert np.all(np.diff(w) > 0), "the pool is oldest-first, so weights must increase"


def test_weighting_moves_the_quantile_towards_recent_scores():
    old = np.zeros(200)
    recent = np.ones(20)
    pool = np.concatenate([old, recent])
    assert conformal.weighted_quantile(pool, 0.9, conformal.recency_weights(len(pool), 1.0)) == 0.0
    assert conformal.weighted_quantile(pool, 0.9, conformal.recency_weights(len(pool), 0.9)) == 1.0


def test_the_aci_update_is_the_papers_line():
    # a miss (err=1) LOWERS alpha, which WIDENS the next interval
    assert conformal.aci_step(0.10, 1, 0.10, gamma=0.02) == pytest.approx(0.10 + 0.02 * (0.10 - 1))
    # a hit (err=0) raises alpha back towards the target
    assert conformal.aci_step(0.10, 0, 0.10, gamma=0.02) == pytest.approx(0.102)
    # and the documented clip holds it inside a defined quantile lookup
    assert conformal.aci_step(0.001, 1, 0.10, gamma=0.5) == conformal.ALPHA_FLOOR
    assert conformal.aci_step(0.999, 0, 0.99, gamma=0.5) == conformal.ALPHA_CEIL


def test_an_ungraded_step_is_minus_one_not_zero():
    """A warmup step is 'not graded'. Filing it as 'not covered' would make every
    method look worse by exactly its warmup length."""
    pred = np.zeros(50)
    truth = np.zeros(50)
    run = conformal.run_stream(pred, truth, warmup=20)
    cov = np.asarray(run.covered)
    assert (cov[:20] == -1).all()
    assert (cov[20:] >= 0).all()
    table = conformal.coverage_table({"x": run}, np.zeros(50, dtype=int))
    assert table["x"]["by_vol_tercile"]["ALL"]["n_date_blocks"] == 30


def test_a_thin_tercile_says_cannot_determine():
    pred = np.zeros(60)
    truth = np.zeros(60)
    run = conformal.run_stream(pred, truth, warmup=5)
    regime = np.zeros(60, dtype=int)
    regime[:8] = 2                       # a HIGH tercile with fewer than 10 graded blocks
    t = conformal.coverage_table({"x": run}, regime)
    assert "CANNOT DETERMINE" in t["x"]["by_vol_tercile"]["HIGH"]["status"]
    assert "realised_coverage" not in t["x"]["by_vol_tercile"]["HIGH"]


def test_terciles_never_file_an_unknown_regime_under_low():
    x = np.array([1.0, 2.0, 3.0, np.nan, 5.0, 6.0])
    r = conformal.terciles(x)
    assert r[3] == -1
    assert set(np.unique(r[[0, 1, 2, 4, 5]])) <= {0, 1, 2}


def test_nothing_sizes_an_interval_with_its_own_outcome():
    """Step t's interval must come from residuals strictly before t."""
    pred = np.zeros(200)
    truth = np.zeros(200)
    truth[150] = 99.0                      # one enormous outcome
    run = conformal.run_stream(pred, truth, warmup=20)
    assert run.covered[150] == 0, (
        "the step with the huge outcome was covered, so its own residual was used to size its "
        "own interval -- the coverage number would then be meaningless")
    assert run.covered[151] == 1, "the following step should have widened"


# ---------------------------------------------------------------------------
# the known-answer: the planted regime shift
# ---------------------------------------------------------------------------
def test_naive_coverage_collapses_and_aci_recovers():
    ka = e3.known_answer()
    post = ka["post_shift_coverage_120_steps"]
    assert post["NAIVE"] < 0.75, (
        f"plain conformal held {post['NAIVE']:.3f} coverage through a 3x variance shift -- "
        "either the shift is not being planted or the method is not naive")
    assert ka["naive_coverage_collapses"] is True
    assert ka["aci_recovers"] is True
    assert post["ACI"] > post["NAIVE"] + 0.15
    k = ka["smallest_k_back_within_5_points"]["ACI"]
    assert k is not None and k <= 200, f"ACI took {k} steps to come back"


def test_the_weighted_variant_is_compared_not_assumed():
    ka = e3.known_answer()
    ks = ka["smallest_k_back_within_5_points"]
    assert "ACI_WEIGHTED" in ks
    assert isinstance(ka["weighted_recovers_at_least_as_fast"], bool)
    assert ka["weighted_recovers_at_least_as_fast"] is True, (
        "recency weights recovered SLOWER than plain ACI on a series where recent history is "
        "strictly more informative after the shift -- that wants explaining, not silence")


def test_the_synthetic_shift_moves_the_scale_and_not_the_forecast():
    pred, y, sd = e3.synthetic_shift()
    err = y - pred
    assert np.std(err[600:900]) > 2.0 * np.std(err[100:400])
    assert abs(np.mean(err[600:900])) < 0.01, "the forecast itself drifted, which is a different bug"
    assert sd[499] < sd[500]


# ---------------------------------------------------------------------------
# the declaration a receipt has to carry
# ---------------------------------------------------------------------------
def test_the_declaration_names_both_papers_and_the_deviation():
    d = conformal.declaration()
    assert "Gibbs" in d["citations"]["aci"]
    assert "Barber" in d["citations"]["non_exchangeable"]
    assert any("clip" in s for s in d["deviations"])
    assert 1.0 in d["rho_grid"], "rho = 1.0 must be in the sweep -- it IS the control point"


def test_the_arm_choice_falls_back_to_the_control_and_says_so():
    import pandas as pd
    daily = pd.DataFrame({"date": pd.bdate_range("2025-01-02", periods=5),
                          "pred_GBM_NOTEXT": 0.0, "gross_GBM_NOTEXT": 0.0})
    negative = [{"results": {"eras": {"ALL": {"vs_controls": {
        "GBM:EVENT_minus_SHUFFLE": {"ic": {"mean": -0.004}}}}}}}]
    pick = e3._pick_arm(daily, negative)
    assert pick["column"] == "GBM_NOTEXT"
    assert "control" in pick["reason"].lower()
    assert "NOT a claim" in pick["reason"]


def test_a_positive_control_adjusted_arm_is_preferred_when_one_exists():
    import pandas as pd
    daily = pd.DataFrame({"date": pd.bdate_range("2025-01-02", periods=5),
                          "pred_GBM_EVENT": 0.0, "gross_GBM_EVENT": 0.0,
                          "pred_GBM_NOTEXT": 0.0, "gross_GBM_NOTEXT": 0.0})
    positive = [{"results": {"eras": {"ALL": {"vs_controls": {
        "GBM:EVENT_minus_SHUFFLE": {"ic": {"mean": +0.006}}}}}}}]
    pick = e3._pick_arm(daily, positive)
    assert pick["column"] == "GBM_EVENT"
    assert "POSITIVE" in pick["reason"]
