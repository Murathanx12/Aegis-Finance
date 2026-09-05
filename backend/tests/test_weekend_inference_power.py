"""VALIDATION of `learner.inference.power_note` -- the tape-requirement note.

WHAT IS BEING PINNED, AND WHY IT NEEDS A PLANTED *AND* A NULL WORLD
==================================================================
`power_note` inverts one identity: a t-statistic on a mean return is
`SR * sqrt(T)`, so `T_needed = (t_target / SR)^2`. Everything the function
claims follows from that, which means a single test on a single array can pass
while the function is wrong in the two directions that matter:

* on a PLANTED world (a Sharpe put in by hand) it must RECOVER the analytic
  tape requirement -- otherwise the number under-states how much history a
  result needs and an underpowered arm gets published as a live one;
* on a NULL world it must not CLAIM power -- otherwise `powered: True` is
  printed for arms that have nothing, and the reader stops believing the flag.

A null owes two tests (project canon). This file gives it three: an exactly
constructed Sharpe, a sampled planted world, and a sampled null world.

Everything here is offline, seeded with `np.random.default_rng`, and encodes no
calendar moment.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from learner import inference as INF


PPY = 12                     # monthly periods per year, the module's default
T_TARGET = 2.0


def _series_with_exact_sample_sharpe(sharpe: float, n: int, seed: int) -> np.ndarray:
    """An array whose SAMPLE Sharpe (mean / sd, ddof=1) is EXACTLY `sharpe`.

    Standardising the draw removes the sampling noise from the planted quantity,
    so the analytic expectation below is an equality rather than a tolerance --
    which is what turns "roughly right" into "right".
    """
    z = np.random.default_rng(seed).normal(0.0, 1.0, n)
    z = (z - z.mean()) / z.std(ddof=1)
    return z * 1.0 + sharpe


# ------------------------------------------------------- the planted world


@pytest.mark.parametrize("sharpe,n", [(0.30, 240), (0.10, 120), (0.50, 60), (0.05, 300)])
def test_planted_sharpe_recovers_the_analytic_years_needed(sharpe, n):
    """`years_needed_for_t2` == the analytic `(t/SR)^2 / periods_per_year`."""
    r = _series_with_exact_sample_sharpe(sharpe, n, seed=11)
    res = INF.power_note(r, periods_per_year=PPY, t_target=T_TARGET)

    assert res["n_periods"] == n
    assert res["sharpe_per_period"] == pytest.approx(sharpe, abs=1e-4)

    analytic_periods = (T_TARGET / sharpe) ** 2
    analytic_years = analytic_periods / PPY
    # the receipt rounds periods to one decimal, so the bar is the rounding
    # granularity, not float equality.
    assert res["periods_needed_for_t_target"] == pytest.approx(analytic_periods, abs=0.06)
    assert res["years_needed_for_t2"] == pytest.approx(analytic_years, abs=0.05), (
        f"planted SR {sharpe} over {n} periods needs {analytic_years:.2f} years "
        f"analytically; power_note said {res['years_needed_for_t2']}")

    # And the observed t is the same identity read the other way.
    assert res["t_observed"] == pytest.approx(sharpe * math.sqrt(n), abs=1e-3)
    assert res["years_observed"] == pytest.approx(n / PPY, abs=1e-6)


def test_the_night_lab_number_is_reproduced_from_its_own_identity():
    """The case the function was written for: an arm whose t = 2 needs more tape
    than the panel has. 7 years of monthly tape at the Sharpe that requires 16
    is the shape of the 2026-09-05 result, and `powered` must be False for it.
    """
    years_needed = 16.1
    sharpe = T_TARGET / math.sqrt(years_needed * PPY)     # invert the identity
    r = _series_with_exact_sample_sharpe(sharpe, 7 * PPY, seed=5)
    res = INF.power_note(r, periods_per_year=PPY)

    assert res["years_observed"] == pytest.approx(7.0, abs=1e-6)
    assert res["years_needed_for_t2"] == pytest.approx(years_needed, abs=0.1)
    assert res["powered"] is False
    assert "MORE TAPE THAN EXISTS HERE" in res["reading"]


def test_sampled_planted_world_lands_on_the_analytic_requirement():
    """The same claim without the standardisation crutch: over 60 independent
    draws of N(0.3, 1) the MEDIAN tape requirement must sit on the analytic one.

    The median, not each draw: `(2/SR)^2` is convex in `1/SR`, so a single
    unlucky draw legitimately reports 19 years for a 3.7-year truth. A per-draw
    bar would be a flaky test asserting a false property.
    """
    analytic_years = (T_TARGET / 0.30) ** 2 / PPY          # 3.7037...
    got = []
    for seed in range(60):
        rng = np.random.default_rng(1000 + seed)
        res = INF.power_note(rng.normal(0.30, 1.0, 240), periods_per_year=PPY)
        got.append(res["years_needed_for_t2"])

    assert all(v is not None for v in got), "a positive-mean draw reported no requirement"
    median = float(np.median(got))
    assert median == pytest.approx(analytic_years, rel=0.25), (
        f"median tape requirement {median:.2f} years over 60 draws vs analytic "
        f"{analytic_years:.2f}")


# ---------------------------------------------------------- the null world


def test_null_world_almost_never_claims_power():
    """Zero-mean noise: `powered` must fire at about the size of the test.

    `powered` is `years_needed <= years_observed`, which reduces algebraically
    to `t_observed >= t_target`, so under a true null it must fire at the
    one-sided normal rate for t = 2 (~2.3%) and not more. The bar is 10% over
    200 draws -- roughly seven binomial sd above the truth, so it cannot flake,
    and it still refutes any implementation that claims power by default.
    """
    n_draws, fired = 200, 0
    for seed in range(n_draws):
        rng = np.random.default_rng(50_000 + seed)
        res = INF.power_note(rng.normal(0.0, 1.0, 240), periods_per_year=PPY)
        fired += bool(res["powered"])
    rate = fired / n_draws
    assert rate <= 0.10, f"{rate:.1%} of pure-noise arms were reported as powered"


def test_null_world_reports_a_requirement_far_beyond_the_tape_it_has():
    """The other half of the null: when noise does have a positive sample mean,
    the years it would need must dwarf the years it has. Otherwise the note
    would quietly bless noise as nearly-powered."""
    ratios = []
    for seed in range(60):
        rng = np.random.default_rng(90_000 + seed)
        res = INF.power_note(rng.normal(0.0, 1.0, 240), periods_per_year=PPY)
        if res["years_needed_for_t2"] is not None:
            ratios.append(res["years_needed_for_t2"] / res["years_observed"])
    assert ratios, "no null draw produced a positive Sharpe in 60 seeds -- implausible"
    assert float(np.median(ratios)) > 3.0, (
        "the median noise arm was reported as needing less than 3x the tape it had")


# ------------------------------------------------- the non-positive Sharpe


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_negative_sharpe_returns_none_not_a_number(seed):
    """A losing arm does not "need" tape. `None`, not a crash, not a number."""
    rng = np.random.default_rng(4_000 + seed)
    res = INF.power_note(rng.normal(-0.30, 1.0, 240), periods_per_year=PPY)

    assert res["sharpe_per_period"] < 0
    assert res["years_needed_for_t2"] is None
    assert res["periods_needed_for_t_target"] is None
    assert res["powered"] is False
    assert res["t_observed"] < 0
    assert "not positive" in res["reading"]


def test_exactly_zero_mean_returns_none():
    """The boundary itself: SR == 0 is non-positive, so no requirement is quoted
    (a zero mean divided into t_target is an infinity, and printing one would
    read as a promise)."""
    a = np.array([1.0, -1.0] * 60)                 # mean exactly 0, sd > 0
    res = INF.power_note(a, periods_per_year=PPY)
    assert res["sharpe_per_period"] == 0.0
    assert res["years_needed_for_t2"] is None
    assert res["powered"] is False


# ------------------------------------------------------- `powered` itself


@pytest.mark.parametrize("n", [24, 60, 144, 240])
def test_powered_is_exactly_the_t_target_crossing(n):
    """`powered` must be True exactly when `t_observed >= t_target`.

    That is the algebraic content of `years_needed <= years_observed`, and it is
    the form with no rounding in it: `powered` is computed from the UNROUNDED
    requirement while the receipt prints the requirement rounded to one decimal
    (see `test_powered_is_computed_before_the_rounding` for the gap that opens
    at the boundary). Swept across the crossing so an inverted comparison cannot
    hide on one side of it.
    """
    seen_true = seen_false = False
    for sharpe in np.linspace(0.01, 0.60, 40):
        r = _series_with_exact_sample_sharpe(float(sharpe), n, seed=17)
        res = INF.power_note(r, periods_per_year=PPY, t_target=T_TARGET)
        by_t = res["t_observed"] >= T_TARGET - 1e-6
        assert res["powered"] is by_t, (
            f"powered={res['powered']} at t={res['t_observed']} vs target {T_TARGET}")
        # away from the boundary the printed number must agree with the flag too
        if abs(res["t_observed"] - T_TARGET) > 0.05:
            by_years = (res["years_needed_for_t2"] is not None
                        and res["years_needed_for_t2"] <= res["years_observed"])
            assert res["powered"] is by_years
        seen_true |= res["powered"]
        seen_false |= not res["powered"]
    assert seen_true and seen_false, "the sweep never crossed the boundary -- vacuous"


def test_powered_is_computed_before_the_rounding():
    """FINDING, PINNED: `powered` uses the unrounded requirement, the receipt
    prints it rounded to one decimal, so at the boundary a reader can see
    `years_needed_for_t2 == years_observed` beside `powered: False`.

    Constructed exactly: a Sharpe whose requirement is a hair above the tape on
    hand rounds down onto it. This is cosmetic, not arithmetic -- the flag is
    right and the printed number is the one that lost information -- but it is
    asserted so it cannot drift into the flag itself.
    """
    n = 24
    years_obs = n / PPY                                     # 2.0
    needed = years_obs + 0.02                               # rounds to 2.0
    sharpe = T_TARGET / math.sqrt(needed * PPY)
    res = INF.power_note(_series_with_exact_sample_sharpe(sharpe, n, seed=17),
                         periods_per_year=PPY, t_target=T_TARGET)
    assert res["powered"] is False, "the flag must use the unrounded requirement"
    assert res["years_needed_for_t2"] == res["years_observed"] == pytest.approx(2.0), (
        "if this stops being equal the rounding changed, not the logic")


def test_t_target_is_honoured_and_not_hardcoded_to_two():
    """`t_target=3` must need 2.25x the tape `t_target=2` needs. If the target
    were hardcoded the two calls would agree and the parameter would be a lie."""
    r = _series_with_exact_sample_sharpe(0.20, 240, seed=3)
    at2 = INF.power_note(r, periods_per_year=PPY, t_target=2.0)
    at3 = INF.power_note(r, periods_per_year=PPY, t_target=3.0)
    assert at3["years_needed_for_t2"] / at2["years_needed_for_t2"] == pytest.approx(
        (3.0 / 2.0) ** 2, rel=0.02)
    assert at2["t_observed"] == at3["t_observed"]      # the t itself does not move


def test_periods_per_year_scales_the_years_and_never_the_t():
    """The identity is in PERIODS; `periods_per_year` only converts the answer
    into years. Reading a daily series as monthly must move `years_*` by the
    ratio of the two conventions and must leave `t_observed` untouched."""
    r = _series_with_exact_sample_sharpe(0.05, 504, seed=9)
    monthly = INF.power_note(r, periods_per_year=12)
    daily = INF.power_note(r, periods_per_year=252)

    assert monthly["t_observed"] == daily["t_observed"]
    assert monthly["sharpe_per_period"] == daily["sharpe_per_period"]
    assert monthly["years_observed"] / daily["years_observed"] == pytest.approx(252 / 12)
    assert monthly["years_needed_for_t2"] / daily["years_needed_for_t2"] == pytest.approx(
        252 / 12, rel=0.02)
    # `n_oos_months` is only meaningful on the monthly convention.
    assert monthly["n_oos_months"] == 504
    assert daily["n_oos_months"] is None


# ------------------------------------------------- degenerate input refuses


@pytest.mark.parametrize("bad", [[], [1.0], [2.0] * 50, [np.nan, np.nan, 1.0]])
def test_degenerate_input_says_cannot_determine_and_does_not_crash(bad):
    """Fewer than two usable periods, or zero variance: CANNOT DETERMINE.

    NOTE FOR THE READER OF THIS FILE: on this branch the returned dict carries
    ONLY `n_periods` and `verdict`. It does NOT carry `powered`, so a caller
    that writes `power_note(x)["powered"]` raises KeyError on a degenerate arm
    rather than reading False. That asymmetry is asserted here so it cannot
    change silently, and it is reported as an API finding rather than fixed.
    """
    res = INF.power_note(bad, periods_per_year=PPY)
    assert INF.CANNOT_DETERMINE in res["verdict"]
    assert "powered" not in res
    assert "years_needed_for_t2" not in res


def test_nan_rows_are_dropped_not_counted():
    """`n_periods` counts FINITE observations. A series padded with NaN must not
    report a longer tape than it has -- that would deflate the requirement."""
    clean = _series_with_exact_sample_sharpe(0.25, 120, seed=2)
    padded = np.concatenate([clean, np.full(60, np.nan)])
    a = INF.power_note(clean, periods_per_year=PPY)
    b = INF.power_note(padded, periods_per_year=PPY)
    assert a["n_periods"] == b["n_periods"] == 120
    assert a["years_needed_for_t2"] == b["years_needed_for_t2"]


# ---------------------------------------------------- the full_report block


def test_full_report_carries_the_power_block_beside_the_deflated_sharpe():
    """The whole point of the change: no receipt can quote a Sharpe without the
    tape requirement beside it in the same dict."""
    rng = np.random.default_rng(21)
    arm = rng.normal(0.10, 1.0, 180)
    fam = {f"cell_{i}": rng.normal(0.0, 1.0, 180) for i in range(4)}
    rep = INF.full_report(arm, family=fam, n_trials=32, n_boot=50, seed=1,
                          periods_per_year=PPY)

    assert "power" in rep and "deflated_sharpe" in rep
    assert rep["power"]["n_periods"] == 180
    assert rep["power"]["years_observed"] == pytest.approx(15.0)
    assert rep["power"] == INF.power_note(arm, periods_per_year=PPY)


def test_full_report_passes_periods_per_year_through():
    """A daily-convention report must not silently be read as monthly."""
    rng = np.random.default_rng(22)
    arm = rng.normal(0.02, 1.0, 504)
    monthly = INF.full_report(arm, n_boot=20, periods_per_year=12)
    daily = INF.full_report(arm, n_boot=20, periods_per_year=252)
    assert monthly["power"]["years_observed"] == pytest.approx(42.0)
    assert daily["power"]["years_observed"] == pytest.approx(2.0)
