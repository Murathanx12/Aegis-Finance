"""S8 -- per-era scoring, neutralisation, era boosting and MMC.

MMC's two known answers are the load-bearing ones, because they are what make
the number readable beside `corr`:
  * a book scored against ITSELF has MMC exactly 0 -- it adds nothing;
  * a book scored against an UNCORRELATED meta-model has MMC == corr -- the
    ensemble had none of it.
Both hold by construction of the definition, so a regression breaks them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.strategy.numerai import (CANNOT_DETERMINE, EraScoringRefused,
                                      era_boost_weights, gaussianize, mmc,
                                      neutralize, per_era_scores)


def _panel(n_eras: int = 24, n_names: int = 200, rho: float = 0.05,
           seed: int = 20260908) -> pd.DataFrame:
    """A panel where `signal` predicts `target` with a known cross-sectional
    correlation, `clone` is a monotone re-expression of `signal`, and
    `unrelated` is independent of both."""
    rng = np.random.default_rng(seed)
    frames = []
    for e in range(n_eras):
        s = rng.normal(size=n_names)
        u = rng.normal(size=n_names)
        target = rho * s + np.sqrt(1 - rho ** 2) * u
        frames.append(pd.DataFrame({
            "era": f"E{e:03d}",
            "signal": s,
            "clone": 3.0 * s + 7.0,             # same ORDER, different scale
            "unrelated": rng.normal(size=n_names),
            "target": target,
        }))
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------------------
# primitives


def test_gaussianize_is_shape_free_and_order_preserving():
    a = gaussianize([1.0, 2.0, 3.0, 4.0])
    b = gaussianize([10.0, 200.0, 3000.0, 40000.0])
    assert np.allclose(a, b)
    assert list(np.argsort(a)) == [0, 1, 2, 3]
    assert abs(float(np.mean(a))) < 1e-12


def test_gaussianize_gives_ties_the_same_value():
    g = gaussianize([1.0, 1.0, 5.0])
    assert g[0] == pytest.approx(g[1])


def test_neutralize_removes_the_exposure_entirely_at_proportion_one():
    rng = np.random.default_rng(7)
    f = rng.normal(size=500)
    p = 2.0 * f + 0.5 * rng.normal(size=500)
    r = neutralize(p, pd.DataFrame({"f": f}))
    assert abs(float(np.corrcoef(r, f)[0, 1])) < 1e-10


def test_neutralize_at_half_leaves_half_the_loading():
    rng = np.random.default_rng(7)
    f = rng.normal(size=2000)
    p = 2.0 * f
    r = neutralize(p, pd.DataFrame({"f": f}), proportion=0.5)
    beta = float(np.polyfit(f, r, 1)[0])
    assert beta == pytest.approx(1.0, rel=1e-6)


def test_neutralize_REFUSES_a_length_mismatch():
    with pytest.raises(EraScoringRefused, match="exposure rows"):
        neutralize([1.0, 2.0, 3.0], pd.DataFrame({"f": [1.0, 2.0]}))


# --------------------------------------------------------------------------
# per-era scoring


def test_per_era_scoring_recovers_the_planted_correlation():
    df = _panel(rho=0.05)
    out = per_era_scores(df, pred_col="signal", target_col="target",
                         era_col="era")
    assert out["n_eras"] == 24
    assert out["mean_corr"] == pytest.approx(0.05, abs=0.02)
    assert out["n_effective"] == 24          # eras, not name-days


def test_the_sample_size_is_the_ERA_count_not_the_name_day_count():
    df = _panel(n_eras=12, n_names=500)
    out = per_era_scores(df, pred_col="signal", target_col="target",
                         era_col="era")
    assert out["n_effective"] == 12
    assert len(df) == 6000
    assert "CANON section 58" in out["n_effective_note"]


def test_a_thin_era_is_DROPPED_AND_COUNTED_not_scored_on_three_rows():
    df = _panel(n_eras=3, n_names=200)
    thin = df[df["era"] == "E000"].head(5)
    df = pd.concat([df[df["era"] != "E000"], thin], ignore_index=True)
    out = per_era_scores(df, pred_col="signal", target_col="target",
                         era_col="era")
    assert out["n_eras"] == 2
    assert out["n_eras_dropped"] == 1
    assert "E000" in out["eras_dropped"]


def test_no_surviving_era_is_CANNOT_DETERMINE():
    df = _panel(n_eras=2, n_names=5)
    out = per_era_scores(df, pred_col="signal", target_col="target",
                         era_col="era")
    assert CANNOT_DETERMINE in out["verdict"]


def test_a_missing_column_REFUSES():
    with pytest.raises(EraScoringRefused, match="no column"):
        per_era_scores(_panel(), pred_col="nope", target_col="target",
                       era_col="era")


# --------------------------------------------------------------------------
# era boosting


def test_era_boosting_upweights_the_WORST_half_and_keeps_the_sample_size():
    scores = {f"E{i}": float(i) for i in range(10)}      # E0 worst, E9 best
    out = era_boost_weights(scores, keep_fraction=0.5, boost=2.0)
    assert set(out["boosted_eras"]) == {f"E{i}" for i in range(5)}
    w = out["weights"]
    assert sum(w.values()) == pytest.approx(10.0)
    assert w["E0"] > w["E9"]
    assert w["E0"] / w["E9"] == pytest.approx(2.0)


def test_era_boosting_with_no_scores_is_CANNOT_DETERMINE():
    assert CANNOT_DETERMINE in era_boost_weights({})["verdict"]


def test_an_impossible_keep_fraction_REFUSES():
    with pytest.raises(EraScoringRefused, match="keep_fraction"):
        era_boost_weights({"a": 1.0}, keep_fraction=0.0)


# --------------------------------------------------------------------------
# MMC -- the two known answers


def test_a_book_against_ITSELF_has_MMC_EXACTLY_ZERO():
    """It adds nothing to an ensemble that already is it."""
    df = _panel()
    out = mmc(df, pred_col="signal", meta_col="signal", target_col="target",
              era_col="era")
    assert out["mean_mmc"] == pytest.approx(0.0, abs=1e-12)
    assert out["mean_corr"] != pytest.approx(0.0, abs=1e-6)
    assert "RE-EXPRESSION" in out["verdict"]
    assert out["share_of_signal_the_ensemble_already_had"] == pytest.approx(1.0)


def test_a_MONOTONE_RE_EXPRESSION_also_has_MMC_ZERO():
    """`clone = 3 * signal + 7`. A different scale is not a different book,
    and gaussianising the ranks is what makes that true rather than hoped."""
    df = _panel()
    out = mmc(df, pred_col="clone", meta_col="signal", target_col="target",
              era_col="era")
    assert out["mean_mmc"] == pytest.approx(0.0, abs=1e-12)
    assert out["mean_corr_with_meta"] == pytest.approx(1.0, abs=1e-12)
    assert "RE-EXPRESSION" in out["verdict"]


def test_a_book_against_an_UNCORRELATED_meta_model_has_MMC_EQUAL_TO_CORR():
    """The ensemble had none of it, so all of it is marginal."""
    df = _panel()
    out = mmc(df, pred_col="signal", meta_col="unrelated",
              target_col="target", era_col="era")
    assert out["mean_mmc"] == pytest.approx(out["mean_corr"], abs=0.004)
    assert abs(out["mean_corr_with_meta"]) < 0.05


def test_MMC_is_between_zero_and_corr_for_a_PARTIALLY_overlapping_book():
    """A book that is half the ensemble and half something new keeps about
    half its correlation after neutralisation."""
    rng = np.random.default_rng(11)
    frames = []
    for e in range(24):
        m = rng.normal(size=300)
        new = rng.normal(size=300)
        cand = (m + new) / np.sqrt(2.0)
        target = 0.06 * cand + rng.normal(size=300)
        frames.append(pd.DataFrame({"era": f"E{e:03d}", "cand": cand,
                                    "meta": m, "target": target}))
    df = pd.concat(frames, ignore_index=True)
    out = mmc(df, pred_col="cand", meta_col="meta", target_col="target",
              era_col="era")
    assert 0.2 * out["mean_corr"] < out["mean_mmc"] < 0.9 * out["mean_corr"]
    assert out["explained_by_the_ensemble"] > 0


def test_a_book_that_points_the_WRONG_way_beyond_the_ensemble_is_named():
    rng = np.random.default_rng(13)
    frames = []
    for e in range(24):
        m = rng.normal(size=300)
        bad = rng.normal(size=300)
        cand = m + bad
        target = 0.10 * m - 0.10 * bad + 0.5 * rng.normal(size=300)
        frames.append(pd.DataFrame({"era": f"E{e:03d}", "cand": cand,
                                    "meta": m, "target": target}))
    df = pd.concat(frames, ignore_index=True)
    out = mmc(df, pred_col="cand", meta_col="meta", target_col="target",
              era_col="era")
    assert out["mean_mmc"] < 0
    assert "WORSE THAN THE ENSEMBLE" in out["verdict"]


def test_corr_minus_mmc_is_exactly_what_the_ensemble_already_had():
    df = _panel()
    out = mmc(df, pred_col="signal", meta_col="signal", target_col="target",
              era_col="era")
    assert out["explained_by_the_ensemble"] == pytest.approx(out["mean_corr"])


def test_the_mmc_block_says_what_it_does_NOT_claim():
    out = mmc(_panel(), pred_col="signal", meta_col="unrelated",
              target_col="target", era_col="era")
    assert "not a portfolio result" in out["not_claimed"]
    assert "not net of costs" in out["not_claimed"]


def test_mmc_REFUSES_a_missing_column():
    with pytest.raises(EraScoringRefused, match="no column"):
        mmc(_panel(), pred_col="signal", meta_col="nope",
            target_col="target", era_col="era")


def test_mmc_with_no_surviving_era_is_CANNOT_DETERMINE():
    out = mmc(_panel(n_eras=2, n_names=5), pred_col="signal",
              meta_col="unrelated", target_col="target", era_col="era")
    assert CANNOT_DETERMINE in out["verdict"]
