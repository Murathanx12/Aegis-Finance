"""The persistence-preserving states null, tested against the defect it replaces.

The load-bearing pair is the red-green pin: a CONSTANT-per-name random
partition over a target with persistent name effects is CLEARED by the old
within-month shuffle (the S36 false positive wearing state labels) and
correctly refused by `persistent_shuffled_null` -- while a partition whose
states genuinely time returns clears the new null too. A null owes two tests.

Everything here is OFFLINE and synthetic, uses `np.random.default_rng(seed)`
-- never `np.random.seed` -- and derives no dates from the wall clock.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from learner import nullbar as NB
from learner import states as S

N_NAMES = 40
N_MONTHS = 36
MONTHS = [str(p) for p in pd.period_range("2019-01", periods=N_MONTHS, freq="M")]


def _frame(states: np.ndarray, y: np.ndarray) -> pd.DataFrame:
    """(N_MONTHS x N_NAMES) arrays -> the long frame the null functions read."""
    rows = []
    for mi, m in enumerate(MONTHS):
        for i in range(N_NAMES):
            rows.append({"permno": 10_000 + i, "month": m,
                         "st": int(states[mi, i]), "excess_vw_1m": float(y[mi, i])})
    return pd.DataFrame(rows)


def _persistent_effects_constant_partition(seed: int = 4):
    """The S36 shape: y carries persistent NAME effects; the partition is a
    fixed random grouping that never changes. Zero state-return timing."""
    rng = np.random.default_rng(seed)
    a = rng.normal(size=N_NAMES)
    y = a[None, :] + 0.2 * rng.normal(size=(N_MONTHS, N_NAMES))
    states = np.tile(np.arange(N_NAMES) % 2, (N_MONTHS, 1))
    return _frame(states, y)


def _real_timing_partition(seed: int = 7):
    """States that genuinely time each name's return: six-month runs, phase
    varying by name, and y follows the name's OWN current state."""
    rng = np.random.default_rng(seed)
    mi = np.arange(N_MONTHS)[:, None]
    ni = np.arange(N_NAMES)[None, :]
    states = ((mi // 6) + ni) % 2
    y = np.where(states == 1, 0.3, -0.3) + 0.05 * rng.normal(size=(N_MONTHS, N_NAMES))
    return _frame(states, y)


# ------------------------------------------------------- draw invariants

def test_a_draw_preserves_each_names_state_composition():
    rng = np.random.default_rng(0)
    df = _real_timing_partition()
    shifted = S.circular_shift_labels(df, "st", rng)
    out = df.assign(_sh=shifted)
    for _, g in out.groupby("permno"):
        assert sorted(g["st"]) == sorted(g["_sh"])       # composition, per name
    # and the draw is not the identity: at least one name actually moved
    assert (out["st"] != out["_sh"]).any()


def test_a_draw_preserves_persistence_not_just_counts():
    """The whole point: a shifted sequence is exactly as persistent as the
    real one. The within-month shuffle fails this by construction."""
    rng = np.random.default_rng(1)
    df = _real_timing_partition()
    shifted = df.assign(st_shift=S.circular_shift_labels(df, "st", rng))
    d_real = S.transition_matrix(df.rename(columns={"st": "state"}), "state")
    d_shift = S.transition_matrix(shifted.rename(columns={"st_shift": "state"}),
                                  "state")
    # six-month runs: diagonal ~5/6; a circular shift can only move it by the
    # single wrap-cut per name, so the two must sit within a couple of percent
    assert abs(d_real["mean_persistence_diagonal"]
               - d_shift["mean_persistence_diagonal"]) < 0.05


def test_the_shifter_refuses_without_the_name_and_the_clock():
    df = _real_timing_partition().drop(columns=["permno"])
    with pytest.raises(ValueError, match="REFUSED"):
        S.circular_shift_labels(df, "st", np.random.default_rng(0))


# --------------------------------------- the red-green pin, both directions

def test_a_constant_random_partition_fools_the_old_null_and_not_the_new_one():
    """Red then green. The old within-month shuffle re-randomises every draw,
    so a fixed grouping of persistent name effects looks like a discovery to
    it. The persistent null shifts a constant sequence onto itself, every
    draw equals the observed, and the p-value says 'nothing here' at ~1."""
    df = _persistent_effects_constant_partition()

    old = S.shuffled_null(df, "st", "excess_vw_1m", n_shuffles=64, seed=2)
    assert old["beats_random_partition"] is True        # the false positive
    assert old["null_bar"] == NB.LEGACY_SHUFFLED_RANKING

    new = S.persistent_shuffled_null(df, "st", "excess_vw_1m",
                                     n_shuffles=64, seed=2)
    assert new["p_value_one_sided"] == pytest.approx(1.0)
    assert new["beats_persistent_relabelling"] is False
    assert "PERSISTENCE_PRESERVING" in new["null_bar"]


def test_a_partition_that_times_returns_clears_the_persistent_null():
    """The other direction -- a null that never fires is a rubber stamp."""
    df = _real_timing_partition()
    new = S.persistent_shuffled_null(df, "st", "excess_vw_1m",
                                     n_shuffles=64, seed=3)
    assert new["observed"] > new["null_p95"], new
    assert new["p_value_one_sided"] <= 0.05
    assert new["beats_persistent_relabelling"] is True


# ------------------------------------------------------ discipline checks

def test_the_verdict_refuses_below_the_draw_floor():
    df = _real_timing_partition()
    out = S.persistent_shuffled_null(df, "st", "excess_vw_1m",
                                     n_shuffles=20, seed=0)
    assert isinstance(out["beats_persistent_relabelling"], str)
    assert out["beats_persistent_relabelling"].startswith(NB.CANNOT_DETERMINE)
    assert "20 < 64" in out["beats_persistent_relabelling"]
    # the distribution numbers are still reported -- refused, not hidden
    assert out["null_shuffles"] == 20 and out["observed"] is not None


def test_same_seed_same_answer():
    df = _real_timing_partition()
    a = S.persistent_shuffled_null(df, "st", "excess_vw_1m", n_shuffles=64, seed=5)
    b = S.persistent_shuffled_null(df, "st", "excess_vw_1m", n_shuffles=64, seed=5)
    assert a == b
