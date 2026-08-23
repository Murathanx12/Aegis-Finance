"""The guard that would have stopped an IC of 0.99 from becoming a finding.

RELATIVE-VALUE-NN-1 returned rank IC 0.97-0.99 with t-statistics over 1,000 and
declared its signal licensed. `cs_rank` — in the feature list — is the
cross-sectional rank OF THE FORWARD RETURN. It was caught because the number was
absurd, which is not a method: the same leak yielding 0.15 would have shipped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import feature_leakage_guard as FLG


def _frame(n_blocks=20, n=60, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for b in range(n_blocks):
        y = rng.normal(size=n)
        rows.append(pd.DataFrame({
            "block": b,
            "y": y,
            "honest": rng.normal(size=n),                 # unrelated
            "weak": 0.03 * y + rng.normal(size=n),        # a real, small edge
            "leaked_rank": pd.Series(y).rank().to_numpy(),   # THE ANSWER
            "leaked_copy": y,                                 # the answer itself
        }))
    return pd.concat(rows, ignore_index=True)


def test_a_rank_of_the_target_is_refused():
    with pytest.raises(FLG.FeatureLeaksTarget, match="leaked_rank"):
        FLG.assert_no_target_leakage(
            _frame(), features=["honest", "leaked_rank"], target="y",
            block="block")


def test_the_target_itself_is_refused():
    with pytest.raises(FLG.FeatureLeaksTarget, match="leaked_copy"):
        FLG.assert_no_target_leakage(
            _frame(), features=["leaked_copy"], target="y", block="block")


def test_honest_features_pass():
    got = FLG.assert_no_target_leakage(
        _frame(), features=["honest", "weak"], target="y", block="block")
    assert got["status"] == "ok" and got["n_blocks"] == 20


def test_a_genuinely_small_edge_is_not_mistaken_for_a_leak():
    """The bar exists to separate a feature from the answer, not to refuse
    predictive features. Nothing honest in this repository exceeds 0.03."""
    got = FLG.assert_no_target_leakage(
        _frame(), features=["weak"], target="y", block="block")
    ic = got["features"]["weak"]["mean_rank_ic"]
    assert 0.0 < abs(ic) < 0.2, ic
    assert got["warned"] == []


def test_the_refusal_names_the_feature_and_its_number():
    with pytest.raises(FLG.FeatureLeaksTarget) as e:
        FLG.assert_no_target_leakage(
            _frame(), features=["honest", "leaked_rank"], target="y",
            block="block")
    msg = str(e.value)
    assert "leaked_rank" in msg and "+1.0" in msg, (
        "a refusal that does not say WHICH feature and BY HOW MUCH sends the "
        "reader back to re-derive it")


# ── the guard on the guard ─────────────────────────────────────────────────


def test_an_unscoreable_frame_is_refused_not_certified():
    empty = pd.DataFrame({"block": [], "y": [], "f": []})
    with pytest.raises(FLG.LeakageUnknowable):
        FLG.assert_no_target_leakage(empty, features=["f"], target="y",
                                     block="block")


def test_too_few_blocks_is_refused():
    with pytest.raises(FLG.LeakageUnknowable, match="block"):
        FLG.assert_no_target_leakage(
            _frame(n_blocks=2), features=["honest"], target="y", block="block")


def test_a_block_too_small_to_score_is_skipped_not_counted():
    """A block of 5 rows says nothing; counting it would let a starved probe
    reach the block floor and certify."""
    small = _frame(n_blocks=3, n=5)
    with pytest.raises(FLG.LeakageUnknowable):
        FLG.assert_no_target_leakage(small, features=["honest"], target="y",
                                     block="block")


def test_an_absent_feature_is_reported_not_silently_skipped():
    got = FLG.assert_no_target_leakage(
        _frame(), features=["honest", "nope"], target="y", block="block")
    assert got["features"]["nope"]["status"] == "ABSENT"


# ── the real case ──────────────────────────────────────────────────────────


def test_it_catches_the_actual_cs_rank_leak():
    """Not a synthetic analogue — the shape that actually happened: a column
    whose NAME reads like state and whose content is the outcome's rank."""
    rng = np.random.default_rng(7)
    rows = []
    for b in range(30):
        fwd = rng.normal(size=80)
        rows.append(pd.DataFrame({
            "date": b, "forward_return": fwd,
            "mom_252": rng.normal(size=80),
            "cs_rank": pd.Series(fwd).rank(pct=True).to_numpy(),
        }))
    d = pd.concat(rows, ignore_index=True)
    with pytest.raises(FLG.FeatureLeaksTarget, match="cs_rank"):
        FLG.assert_no_target_leakage(
            d, features=["mom_252", "cs_rank"], target="forward_return",
            block="date")
