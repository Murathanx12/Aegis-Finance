"""Reproducibility of the crash-model artifact (Track 3).

The crash-training PIPELINE is deterministic given fixed input — two trainings on
identical features/targets produce byte-identical .pkl files (same sha256). That
is what makes the provenance sidecar's model_sha256 meaningful.

CAVEAT (documented, not asserted): reproducing the SHIPPED crash_model.pkl
additionally requires pinned INPUT DATA. The shipped model trains on live
yfinance + FRED (not committed, and historical values can be revised), and the
artifact is gitignored. So full bit-reproduction of the deployed model is not
possible from the repo alone; the regeneration command is
`python -m engine.training.train_crash_model`, and the sidecar records the train
date + library versions for provenance.
"""

import os
import warnings

import numpy as np
import pandas as pd

from backend.services.crash_model import _file_sha256
from backend.services.crash_model import CrashPredictor

warnings.filterwarnings("ignore")


def _fixed_input():
    """A fixed synthetic feature matrix + 3-horizon targets (no network)."""
    rng = np.random.default_rng(7)
    n = 1400
    cols = [f"f{i}" for i in range(12)]
    X = pd.DataFrame(
        rng.normal(size=(n, 12)), columns=cols,
        index=pd.bdate_range("2015-01-01", periods=n),
    )
    tgt = {
        h: pd.Series((np.random.default_rng(seed).random(n) < 0.06).astype(int),
                     index=X.index)
        for h, seed in [("3m", 1), ("6m", 2), ("12m", 3)]
    }
    return X, tgt


def _train_and_hash(X, tgt, path):
    p = CrashPredictor(n_estimators=40, random_state=42)
    p.train(X, tgt, min_train_samples=252 * 3)
    p.save_model(path)
    return _file_sha256(path)


def test_training_is_deterministic_given_fixed_input(tmp_path):
    X, tgt = _fixed_input()
    h1 = _train_and_hash(X, tgt, str(tmp_path / "m1.pkl"))
    h2 = _train_and_hash(X, tgt, str(tmp_path / "m2.pkl"))
    assert h1 == h2, "training pipeline must be byte-deterministic on fixed input"


def test_sidecar_sha_matches_its_own_pkl(tmp_path):
    """The sidecar's model_sha256 matches the .pkl it was written for."""
    import json

    from backend.services.crash_model import _meta_path

    X, tgt = _fixed_input()
    path = str(tmp_path / "m.pkl")
    p = CrashPredictor(n_estimators=40, random_state=42)
    p.train(X, tgt, min_train_samples=252 * 3)
    p.save_model(path)
    meta = json.loads(_meta_path(path).read_text())
    assert meta["model_sha256"] == _file_sha256(path)
