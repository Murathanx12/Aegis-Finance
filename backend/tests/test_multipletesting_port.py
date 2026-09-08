"""S2 -- the vendored multiple-testing library, and the gotchas it documents.

`backend/strategy/multipletesting.py` is a verbatim MIT copy of Vibe-Trading's
`agent/src/quantlib/multipletesting.py` (HEAD a4f06a29). This file does three
jobs:

1. **pins the two documented gotchas as tests**, because a library whose header
   warns about a convention and whose tests do not check it is a library that
   will be misused exactly once per session;
2. **proves the vendored implementation agrees with `learner.inference`**, the
   implementation every existing Aegis receipt was written with. If they ever
   diverge the suite says so, and the divergence is a finding rather than a
   silent adoption of whichever ran last;
3. **checks the vendored PBO against the sealed growth-book receipt** when the
   series cache is on disk. That cache is gitignored, so on CI the check
   SKIPS WITH A REASON THAT NAMES THE FILE -- a check that did not run must
   never read as a check that passed.

WHY THE AGREEMENT TEST USES A SEEDED SYNTHETIC PANEL
====================================================
So that it runs everywhere, including CI, including a fresh clone with no
`backend/data`. The property being tested -- two implementations of the same
published formula produce the same number -- does not need real returns, and a
test that can only run on the dev machine is a test that runs once.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from backend.strategy import multipletesting as MT
from backend.strategy import verdict as V
from learner import inference as INF

REPO = Path(__file__).resolve().parents[2]
GROWTH_DIR = REPO / "backend" / "data" / "optimus" / "growth_book"
SERIES_CACHE = GROWTH_DIR / "G2_genome_series.parquet"
G2_RECEIPT = GROWTH_DIR / "G2_generation0.json"

TOL = 1e-9


# --------------------------------------------------------------- the licence


def test_the_MIT_licence_header_travels_with_the_copy():
    """MIT's one condition. A vendored file with no licence is a licence breach
    wearing a convenience."""
    src = (REPO / "backend" / "strategy" / "multipletesting.py").read_text(encoding="utf-8")
    head = src[:4000]
    assert "MIT License" in head
    assert "Permission is hereby granted, free of charge" in head
    assert "Vibe-Trading" in head
    assert "VENDORED VERBATIM" in head


def test_the_vendored_body_is_not_edited():
    """The whole reason to vendor rather than reimplement is diffability.

    Everything after the prepended header must be byte-identical to upstream
    when the clone is present; when it is not, the test says which file it
    could not compare against instead of passing quietly.
    """
    upstream = Path("C:/Users/mrthn/reference/Vibe-Trading/agent/src/quantlib/"
                    "multipletesting.py")
    if not upstream.exists():
        pytest.skip(f"upstream clone absent: {upstream} -- comparison NOT RUN")
    ours = (REPO / "backend" / "strategy" / "multipletesting.py").read_text(encoding="utf-8")
    body = ours[ours.index('"""Multiple-testing control'):]
    assert body == upstream.read_text(encoding="utf-8")


# ------------------------------------------------------- the two gotchas


def test_gotcha_one_an_annualised_sharpe_is_refused_by_the_docstring_not_the_code():
    """The header states this cannot be detected. Pin the STATEMENT, so that a
    future edit which quietly starts guessing units is visible.

    Feeding an annualised Sharpe with a per-period T inflates the statistic by
    ~sqrt(periods); the test shows the size of the error rather than asserting
    a guard that does not exist.
    """
    assert "per-observation, not annualised" in MT.__doc__
    per_obs = 0.15
    annualised = per_obs * math.sqrt(12)
    honest = MT.probabilistic_sharpe_ratio(per_obs, 144)
    inflated = MT.probabilistic_sharpe_ratio(annualised, 144)
    assert inflated > honest
    assert inflated > 0.99 > honest      # a coin flip turned into a certainty


def test_gotcha_two_excess_kurtosis_is_REFUSED_not_silently_accepted():
    """`scipy.stats.kurtosis` and `pandas.Series.kurt` return the EXCESS form.

    Passing 0.0 (a Gaussian's excess kurtosis) must raise, because the correct
    value for a Gaussian is 3.0 and the wrong one makes the variance term too
    small and the confidence too high.
    """
    assert MT.GAUSSIAN_KURTOSIS == 3.0
    with pytest.raises(ValueError, match="Excess kurtosis was probably passed"):
        MT.probabilistic_sharpe_ratio(0.2, 144, kurtosis=0.0)
    # and the right one does not raise
    MT.probabilistic_sharpe_ratio(0.2, 144, kurtosis=MT.GAUSSIAN_KURTOSIS)


def test_a_short_sample_is_a_refusal_not_a_number():
    with pytest.raises(ValueError, match="at least 30 observations"):
        MT.probabilistic_sharpe_ratio(0.2, MT.MIN_OBSERVATIONS - 1)


def test_cscv_reports_the_rows_it_dropped_rather_than_dropping_them_quietly():
    """145 rows into 8 subsets leaves one row over. The count is on the result."""
    rng = np.random.default_rng(7)
    M = rng.normal(0.0, 0.02, size=(145, 6))
    res = MT.probability_of_backtest_overfitting(M, n_splits=8)
    assert res.dropped_observations == 145 - (145 // 8) * 8 == 1
    assert res.n_observations == 144


def test_pbo_of_a_pure_noise_family_is_near_a_coin_flip():
    """The published reading of PBO ~ 0.5: selection carries no information."""
    rng = np.random.default_rng(20260907)
    M = rng.normal(0.0, 0.02, size=(240, 12))
    res = MT.probability_of_backtest_overfitting(M, n_splits=8)
    assert 0.3 <= res.pbo <= 0.7


# ------------------------------- agreement with the implementation on record


def _family(seed: int = 20260907, T: int = 144, N: int = 24) -> np.ndarray:
    rng = np.random.default_rng(seed)
    common = rng.normal(0.006, 0.04, size=T)          # a shared market factor
    idio = rng.normal(0.0, 0.03, size=(T, N))
    tilt = np.linspace(-0.002, 0.004, N)
    return common[:, None] + idio + tilt[None, :]


def test_vendored_PBO_equals_learner_inference_PBO():
    """Same formula, two implementations, one number -- or a finding."""
    M = _family()
    ours = INF.pbo(M, n_splits=8)
    theirs = V.pbo(M, n_splits=8)
    assert ours["n_partitions"] == theirs["n_partitions"] == 70
    assert ours["n_arms"] == theirs["n_arms"]
    assert ours["verdict"] == theirs["verdict"]
    # `learner.inference` rounds to 4 dp on the way into a receipt; compare at
    # that precision and pin the raw delta beneath it.
    assert abs(theirs["pbo"] - ours["pbo"]) <= 0.5e-4
    assert round(theirs["pbo"], 4) == ours["pbo"]


def test_vendored_DSR_equals_learner_inference_DSR():
    """Bailey-Lopez de Prado, both ways, to 1e-9 before rounding."""
    rng = np.random.default_rng(11)
    r = rng.normal(0.004, 0.03, size=200)
    ours = INF.deflated_sharpe(r, n_trials=88)
    theirs = V.deflated_sharpe_from_returns(r, n_trials=88)
    assert abs(theirs["sharpe_benchmark_sr0"] - ours["sharpe_benchmark_sr0"]) <= 0.5e-4
    assert round(theirs["dsr"], 4) == ours["dsr"]
    assert theirs["verdict"] == ours["verdict"]
    # the raw agreement, beneath `learner.inference`'s 4 dp rounding
    m = V.moments(r)
    exact = MT.deflated_sharpe_ratio(
        observed_sharpe=m["sharpe_per_observation"], n_trials=88,
        n_observations=m["n"], trial_sharpe_std=V.analytic_trial_sharpe_std(m["n"]),
        skew=m["skew"], kurtosis=m["kurtosis_non_excess"])
    assert abs(exact.deflated_sharpe_ratio - theirs["dsr"]) <= TOL


def test_expected_maximum_sharpe_matches_the_closed_form_in_learner_inference():
    for n in (2, 8, 88, 462):
        sd = 1.0 / math.sqrt(143)
        theirs = MT.expected_maximum_sharpe(n, sd)
        ours = sd * ((1 - INF._EULER) * INF._nppf(1 - 1.0 / n)
                     + INF._EULER * INF._nppf(1 - 1.0 / (n * math.e)))
        assert abs(theirs - ours) <= TOL, n


# --------------------------------------------- against the SEALED receipts


@pytest.mark.skipif(not (SERIES_CACHE.exists() and G2_RECEIPT.exists()),
                    reason=(f"the growth-book series cache is gitignored and is "
                            f"absent here: {SERIES_CACHE}. THE CHECK DID NOT RUN. "
                            f"Its result on the dev machine is recorded in "
                            f"docs/BUILD_2026-09-07b_S1_STRATEGY_INTERFACE.md "
                            f"section 3."))
def test_vendored_PBO_reproduces_the_sealed_growth_family_PBO():
    """The S2 gate: 0.6429 on the sealed receipt, from the vendored library."""
    import pandas as pd

    from learner import growth_lab as GL

    d = json.loads(G2_RECEIPT.read_text(encoding="utf-8"))
    want = d["pbo_over_the_whole_family"]
    df = pd.read_parquet(SERIES_CACHE)
    graded = sorted(k for k, v in d["cells"].items() if v.get("beta") is not None)
    dev = {k: GL.dev(df[k].dropna()) for k in graded}
    common = None
    for k in graded:
        i = pd.Index(dev[k].index)
        common = i if common is None else common.intersection(i)
    M = np.column_stack([dev[k].reindex(common).to_numpy() for k in graded])

    got = V.pbo(M, n_splits=8)
    assert got["n_arms"] == want["n_arms"]
    assert got["n_periods"] == want["n_periods"]
    assert got["n_partitions"] == want["n_partitions"]
    assert got["verdict"] == want["verdict"]
    assert abs(got["pbo"] - want["pbo"]) <= 0.5e-4


# ------------------------------------------- the three Aegis house rules


def test_SCREEN_is_BH_and_EXPORT_is_Holm_and_both_are_reported():
    """CANON section 63. Quoting only the one that suits the paragraph is how a
    screen becomes a claim without anyone deciding that it should."""
    p = {f"cell{i}": v for i, v in enumerate(
        [0.001, 0.004, 0.01, 0.02, 0.03, 0.2, 0.4, 0.6, 0.8, 0.95])}
    both = V.screen_then_export(p)
    bh = both["screen_bh_fdr"]["survivors"]
    holm = both["export_holm"]["survivors"]
    assert set(holm) <= set(bh), "Holm can never admit what BH rejected"
    assert both["screened_not_exported"] == sorted(set(bh) - set(holm))
    assert len(bh) >= len(holm)


def test_holm_adjusted_p_is_monotone_and_matches_the_hand_computation():
    p = {"a": 0.01, "b": 0.02, "c": 0.03}
    h = V.holm(p)
    # step-down: 3*0.01, max(., 2*0.02), max(., 1*0.03)
    assert h["adjusted"]["a"] == pytest.approx(0.03)
    assert h["adjusted"]["b"] == pytest.approx(0.04)
    assert h["adjusted"]["c"] == pytest.approx(0.04)
    vals = [h["adjusted"][k] for k in ("a", "b", "c")]
    assert vals == sorted(vals)


def test_a_non_finite_p_is_DROPPED_AND_COUNTED_never_treated_as_one():
    h = V.holm({"a": 0.01, "b": None, "c": float("nan")})
    assert h["family_size"] == 1
    assert h["n_dropped_non_finite"] == 2
    assert h["dropped_non_finite"] == ["b", "c"]


def test_n_effective_counts_DATE_BLOCKS_not_rows():
    """[[name-days-are-not-periods]]: 259,234 name-days printed t -65."""
    dates = ["2020-01"] * 500 + ["2020-02"] * 500 + ["2020-03"] * 500
    n = V.n_effective_date_blocks(dates)
    assert n["n_rows"] == 1500
    assert n["n_effective"] == 3
    assert n["basis"] == "distinct DATE BLOCKS"


def test_a_sample_too_short_for_its_own_moments_is_CANNOT_DETERMINE():
    r = np.linspace(-0.01, 0.01, MT.MIN_OBSERVATIONS - 1)
    out = V.deflated_sharpe_from_returns(r, n_trials=10)
    assert out["verdict"].startswith(V.CANNOT_DETERMINE)
    assert "dsr" not in out


def test_the_null_sd_basis_is_STATED_never_assumed_silently():
    rng = np.random.default_rng(3)
    r = rng.normal(0.003, 0.02, size=120)
    without = V.deflated_sharpe_from_returns(r, n_trials=50)
    with_draws = V.deflated_sharpe_from_returns(
        r, n_trials=50, trial_sharpes=rng.normal(0.0, 0.09, size=50))
    assert "analytic" in without["null_sd_basis"]
    assert "observed trial Sharpes" in with_draws["null_sd_basis"]
    assert without["dsr"] != with_draws["dsr"]


def test_pbo_default_splits_is_8_not_the_upstream_16():
    """Adopting upstream's default would make new receipts incomparable with
    every existing one -- the exact problem the shared library was adopted to
    fix."""
    assert MT.DEFAULT_CSCV_SPLITS == 16
    M = _family(T=160, N=8)
    assert V.pbo(M)["n_partitions"] == 70          # C(8,4), i.e. n_splits=8


def test_agreement_report_names_a_disagreement_instead_of_adopting_one():
    r = V.agreement_report(vendored={"pbo": 0.7000}, receipt={"pbo": 0.6429})
    assert r["verdict"] == "DISAGREES"
    assert r["disagreements"][0]["delta"] == pytest.approx(0.0571)
    ok = V.agreement_report(vendored={"pbo": 0.6428571428571429},
                            receipt={"pbo": 0.6429})
    assert ok["verdict"] == "AGREES", "a 4-dp receipt is compared at 4 dp"


def test_the_two_DSR_implementations_agree_to_1e_9_BEFORE_any_rounding():
    """The S2 gate as stated: 1e-9.

    `learner.inference.deflated_sharpe` rounds to 4 dp on the way into a
    receipt, so the receipt itself can only be compared at 4 dp. The
    UNROUNDED comparison is done here by rebuilding `inference`'s own
    expression from its own helpers -- no rounding on either side.
    """
    rng = np.random.default_rng(20260907)
    for trials in (2, 8, 88, 462):
        r = rng.normal(0.004, 0.03, size=180)
        a = np.asarray(r, dtype="float64")
        T = a.size
        mu, sd = a.mean(), a.std(ddof=1)
        sr = mu / sd
        g3 = float(((a - mu) ** 3).mean() / sd ** 3)
        g4 = float(((a - mu) ** 4).mean() / sd ** 4)
        sr_sd = 1.0 / math.sqrt(T - 1)
        sr0 = (0.0 if trials == 1 else
               sr_sd * ((1 - INF._EULER) * INF._nppf(1 - 1.0 / trials)
                        + INF._EULER * INF._nppf(1 - 1.0 / (trials * math.e))))
        denom = 1.0 - g3 * sr + ((g4 - 1.0) / 4.0) * sr ** 2
        z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(denom)
        theirs_unrounded = INF._ncdf(z)

        vend = MT.deflated_sharpe_ratio(
            observed_sharpe=sr, n_trials=trials, n_observations=T,
            trial_sharpe_std=sr_sd, skew=g3, kurtosis=g4)
        assert abs(vend.expected_maximum_sharpe - sr0) <= TOL, trials
        assert abs(vend.deflated_sharpe_ratio - theirs_unrounded) <= TOL, trials
