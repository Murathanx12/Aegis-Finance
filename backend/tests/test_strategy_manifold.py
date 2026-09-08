"""S4 -- `do_predict`, against a PLANTED out-of-manifold regime.

The known answer: train on a tight blob, then ask about a point 50 standard
deviations away. Every detector must object; the flag must fall to -2; the
score must come back NULL rather than extrapolated.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.strategy.manifold import (DETECTORS, DO_PREDICT_EXPIRED,
                                       DO_PREDICT_TRUSTWORTHY, ManifoldRefusal,
                                       expired_flags, fit_manifold)


def _blob(n: int = 300, centre: float = 0.0, sd: float = 1.0,
          seed: int = 20260908) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"f1": rng.normal(centre, sd, n),
                         "f2": rng.normal(centre, sd, n),
                         "f3": rng.normal(centre, sd, n)})


def test_a_row_INSIDE_the_training_blob_is_trustworthy():
    train = _blob()
    gate = fit_manifold(train)
    inside = pd.DataFrame({"f1": [0.0], "f2": [0.0], "f3": [0.0]})
    assert int(gate.do_predict(inside).iloc[0]) == DO_PREDICT_TRUSTWORTHY


def test_a_regime_NEVER_SEEN_is_rejected_by_every_enabled_detector():
    """THE PLANTED FAULT. 50 sd from the centre is a regime the model has
    never seen; the answer is known by construction."""
    train = _blob()
    gate = fit_manifold(train)
    far = pd.DataFrame({"f1": [50.0], "f2": [50.0], "f3": [50.0]})
    rej = gate.rejections(far)
    assert set(rej) == set(gate.enabled)
    assert all(bool(m[0]) for m in rej.values()), rej
    flag = int(gate.do_predict(far).iloc[0])
    assert flag == DO_PREDICT_TRUSTWORTHY - len(gate.enabled)
    assert flag <= 0


def test_all_three_detectors_fit_on_an_ordinary_blob():
    gate = fit_manifold(_blob())
    assert set(gate.enabled) == set(DETECTORS), gate.disabled


def test_the_gated_score_is_NULL_not_zero_and_not_shrunk():
    """A zero would rank an unknown name above every genuine negative."""
    train = _blob()
    gate = fit_manifold(train)
    rows = pd.DataFrame({"f1": [0.0, 50.0], "f2": [0.0, 50.0],
                         "f3": [0.0, 50.0], "score": [0.7, 0.9]},
                        index=["INSIDE", "OUTSIDE"])
    out = gate.attach(rows)
    assert out.loc["INSIDE", "score_gated"] == 0.7
    assert pd.isna(out.loc["OUTSIDE", "score_gated"])
    assert out.loc["OUTSIDE", "score"] == 0.9        # the raw score is untouched


def test_the_per_detector_cause_travels_beside_the_flag():
    gate = fit_manifold(_blob())
    rows = pd.DataFrame({"f1": [50.0], "f2": [50.0], "f3": [50.0],
                         "score": [1.0]})
    out = gate.attach(rows)
    for name in DETECTORS:
        assert f"rejected_by_{name}" in out.columns
    assert bool(out["rejected_by_dissimilarity_index"].iloc[0])


def test_a_detector_that_would_reject_a_THIRD_of_its_own_training_set_is_DISABLED():
    """`outlier_protection_percentage`: a refusal, not a decimated fit. With a
    di_threshold below 1 the leave-one-out self-rejection rate explodes."""
    gate = fit_manifold(_blob(), di_threshold=0.05,
                        outlier_protection_percentage=30.0)
    assert "dissimilarity_index" in gate.disabled
    assert "dissimilarity_index" not in gate.enabled
    assert "OWN training set" in gate.disabled["dissimilarity_index"]


def test_when_every_detector_is_disabled_the_fit_REFUSES_instead_of_returning_1():
    with pytest.raises(ManifoldRefusal, match="all three"):
        fit_manifold(_blob(), di_threshold=0.05, svm_nu=0.9,
                     dbscan_eps=1e-9, outlier_protection_percentage=1.0)


def test_a_gate_with_no_enabled_detector_REFUSES_to_score():
    gate = fit_manifold(_blob())
    gate.enabled = ()
    with pytest.raises(ManifoldRefusal, match="no in-manifold detector"):
        gate.do_predict(pd.DataFrame({"f1": [0.0], "f2": [0.0], "f3": [0.0]}))


def test_too_few_training_rows_REFUSE():
    with pytest.raises(ManifoldRefusal, match="training rows"):
        fit_manifold(_blob(5))


def test_zero_variance_features_REFUSE():
    df = pd.DataFrame({"a": [1.0] * 100, "b": [2.0] * 100})
    with pytest.raises(ManifoldRefusal, match="zero variance"):
        fit_manifold(df)


def test_a_missing_training_feature_at_inference_REFUSES():
    gate = fit_manifold(_blob())
    with pytest.raises(ManifoldRefusal, match="missing training features"):
        gate.do_predict(pd.DataFrame({"f1": [0.0], "f2": [0.0]}))


def test_an_expired_model_emits_NULL_predictions_with_flag_2():
    out = expired_flags(["AAPL", "MSFT"], reason="last fit 2026-01-01, 250d stale")
    assert list(out["do_predict"]) == [DO_PREDICT_EXPIRED] * 2
    assert out["score"].isna().all()
    assert "stale" in out["expiry_reason"].iloc[0]
    # 2 is NOT the trustworthy value; a book gating on == 1 excludes it.
    assert DO_PREDICT_EXPIRED != DO_PREDICT_TRUSTWORTHY


def test_the_flag_is_monotone_in_distance_from_the_manifold():
    """Known-answer, weak form: further out is never MORE trusted."""
    gate = fit_manifold(_blob())
    rows = pd.DataFrame({"f1": [0.0, 3.0, 12.0, 60.0],
                         "f2": [0.0, 3.0, 12.0, 60.0],
                         "f3": [0.0, 3.0, 12.0, 60.0]})
    flags = list(gate.do_predict(rows))
    assert flags == sorted(flags, reverse=True), flags
    assert flags[0] == DO_PREDICT_TRUSTWORTHY
    assert flags[-1] <= 0


def test_the_report_names_the_gate_and_every_disabled_reason():
    gate = fit_manifold(_blob(), di_threshold=0.05)
    rep = gate.report()
    assert rep["gate"] == "books admit a name only when do_predict == 1"
    assert "dissimilarity_index" in rep["detectors_disabled"]
    assert rep["n_train"] == 300
