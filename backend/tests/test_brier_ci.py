"""
Tests for brier_with_ci — block-bootstrap confidence interval + event count on
the crash Brier (Chunk 4 / BACKLOG M2). Pure/offline.
"""

import numpy as np
import pytest
from sklearn.metrics import brier_score_loss

from engine.validation.metrics import _block_indices, brier_with_ci


def _rare_event_sample(n=200, n_pos=7, seed=1):
    """Synthetic rare-event sample resembling the crash setting: few positives,
    a mildly skillful predictor."""
    rng = np.random.default_rng(seed)
    y_true = np.zeros(n)
    pos_idx = rng.choice(n, size=n_pos, replace=False)
    y_true[pos_idx] = 1.0
    # Predictor: base 0.1, lifted on true positives, plus noise; clipped to [0,1].
    y_pred = np.clip(0.1 + 0.4 * y_true + rng.normal(0, 0.05, n), 0, 1)
    return y_true, y_pred


class TestBrierWithCI:
    def test_point_matches_sklearn(self):
        y_true, y_pred = _rare_event_sample()
        out = brier_with_ci(y_true, y_pred)
        assert out["point"] == pytest.approx(float(brier_score_loss(y_true, y_pred)))
        assert out["brier"] == out["point"]

    def test_ci_brackets_point(self):
        y_true, y_pred = _rare_event_sample()
        out = brier_with_ci(y_true, y_pred)
        assert 0.0 <= out["lower"] <= out["upper"]
        assert out["lower"] <= out["point"] + 1e-9
        assert out["point"] <= out["upper"] + 1e-9
        assert out["ci"] == 0.95

    def test_reports_event_count(self):
        y_true, y_pred = _rare_event_sample(n=200, n_pos=7)
        out = brier_with_ci(y_true, y_pred)
        assert out["n_positive"] == 7
        assert out["n_samples"] == 200

    def test_low_event_warning_fires_under_10(self):
        y_true, y_pred = _rare_event_sample(n=200, n_pos=7)
        assert brier_with_ci(y_true, y_pred)["low_event_warning"] is True

    def test_no_warning_with_enough_events(self):
        y_true, y_pred = _rare_event_sample(n=200, n_pos=25)
        assert brier_with_ci(y_true, y_pred)["low_event_warning"] is False

    def test_reproducible_with_seed(self):
        y_true, y_pred = _rare_event_sample()
        a = brier_with_ci(y_true, y_pred, seed=7)
        b = brier_with_ci(y_true, y_pred, seed=7)
        assert (a["lower"], a["upper"]) == (b["lower"], b["upper"])

    def test_auto_block_size_is_cube_root(self):
        y_true, y_pred = _rare_event_sample(n=200)
        out = brier_with_ci(y_true, y_pred)
        assert out["block_size"] == max(1, round(200 ** (1 / 3)))  # = 6

    def test_block_bootstrap_not_narrower_than_iid(self):
        # On an autocorrelated series the block CI should be at least as wide as
        # the i.i.d. CI (the whole reason to use it). Construct runs of positives.
        y_true = np.zeros(240)
        y_true[20:30] = 1.0  # a contiguous run (autocorrelated cluster)
        y_true[120:128] = 1.0
        rng = np.random.default_rng(3)
        y_pred = np.clip(0.1 + 0.4 * y_true + rng.normal(0, 0.05, 240), 0, 1)
        iid = brier_with_ci(y_true, y_pred, block_size=1, seed=5)
        block = brier_with_ci(y_true, y_pred, block_size=12, seed=5)
        iid_width = iid["upper"] - iid["lower"]
        block_width = block["upper"] - block["lower"]
        assert block_width >= iid_width * 0.95  # block ≥ i.i.d. (allow tiny slack)

    def test_too_few_samples(self):
        out = brier_with_ci(np.array([0.0, 1.0]), np.array([0.2, 0.8]))
        assert "error" in out

    def test_nan_dropped(self):
        y_true = np.array([0, 1, 0, 1, 0, 1, np.nan])
        y_pred = np.array([0.1, 0.8, 0.2, np.nan, 0.3, 0.7, 0.5])
        out = brier_with_ci(y_true, y_pred, n_boot=200)
        assert out["n_samples"] == 5  # two rows with a NaN dropped


class TestBlockIndices:
    def test_length_and_range(self):
        rng = np.random.default_rng(0)
        idx = _block_indices(rng, n=50, block_size=7)
        assert len(idx) == 50
        assert idx.min() >= 0 and idx.max() < 50

    def test_blocks_are_contiguous_mod_n(self):
        rng = np.random.default_rng(0)
        idx = _block_indices(rng, n=10, block_size=5)
        # First block: consecutive (mod 10) values.
        first = idx[:5]
        diffs = (np.diff(first) % 10)
        assert np.all(diffs == 1)
