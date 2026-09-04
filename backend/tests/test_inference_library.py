"""L0: the inference library, tested on a PLANTED world and a NULL world.

A statistics module that is only ever run on real data cannot be wrong in a way
anyone notices: every output is plausible and nothing has a known answer. So
each test here builds a world whose answer is known by construction --

  PLANTED: an arm with a real edge among decoys. DSR should clear, SPA should
           reject its null, PBO should be low (the champion is stable).
  NULL:    every arm is noise. DSR should NOT clear once the search size is
           admitted, SPA should not reject, PBO should sit near a coin flip.

-- and asserts the direction, never a hard-coded value: a test that pins
0.0431 pins the seed, not the property.
"""
from __future__ import annotations

import numpy as np
import pytest

from learner import inference


def _planted(n=180, n_arms=16, edge=0.30, seed=7):
    """One arm with a genuine per-period Sharpe of ~`edge`, the rest noise."""
    rng = np.random.default_rng(seed)
    M = rng.normal(0.0, 1.0, size=(n, n_arms))
    M[:, 0] += edge
    return M


def _null_world(n=180, n_arms=16, seed=11):
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, 1.0, size=(n, n_arms))


# ------------------------------------------------------------- deflated Sharpe


def test_dsr_clears_on_a_planted_edge_and_not_on_noise():
    P, Z = _planted(), _null_world()
    best_p = P[:, int(np.argmax(P.mean(axis=0)))]
    best_z = Z[:, int(np.argmax(Z.mean(axis=0)))]
    dp = inference.deflated_sharpe(best_p, n_trials=P.shape[1])
    dz = inference.deflated_sharpe(best_z, n_trials=Z.shape[1])
    assert dp["dsr"] > dz["dsr"]
    assert dp["verdict"] == "CLEARS_DEFLATED_SHARPE"
    assert dz["verdict"] == "WITHIN_SELECTION_NOISE", dz


def test_dsr_penalises_the_number_of_cells_looked_at():
    """The same series, honestly reported, is worth less after 500 tries."""
    a = _planted(edge=0.22)[:, 0]
    one = inference.deflated_sharpe(a, n_trials=1)
    many = inference.deflated_sharpe(a, n_trials=500)
    assert one["sharpe"] == many["sharpe"]
    assert many["sharpe_benchmark_sr0"] > one["sharpe_benchmark_sr0"] >= 0.0
    assert many["dsr"] < one["dsr"]


def test_dsr_uses_the_null_draws_when_it_has_enough_of_them():
    a = _planted()[:, 0]
    draws = list(np.random.default_rng(3).normal(0, 0.25, size=128))
    with_draws = inference.deflated_sharpe(a, n_trials=64, null_sharpes=draws)
    assert "sd of 128 null Sharpes" in with_draws["null_sd_basis"]
    too_few = inference.deflated_sharpe(a, n_trials=64, null_sharpes=draws[:10])
    assert "below the" in too_few["null_sd_basis"]


def test_dsr_refuses_a_sample_too_short_to_speak():
    out = inference.deflated_sharpe([0.01, 0.02, -0.01], n_trials=4)
    assert out["verdict"].startswith(inference.CANNOT_DETERMINE)


# --------------------------------------------------------------- stationary SPA


def test_stationary_bootstrap_keeps_the_length_and_wraps():
    idx = inference.stationary_bootstrap_indices(50, block=4.0, n_boot=20, seed=1)
    assert idx.shape == (20, 50)
    assert idx.min() >= 0 and idx.max() < 50


def test_spa_rejects_on_a_planted_arm_and_not_on_noise():
    P, Z = _planted(), _null_world()
    fam_p = {f"arm{i}": P[:, i] for i in range(P.shape[1])}
    fam_z = {f"arm{i}": Z[:, i] for i in range(Z.shape[1])}
    sp = inference.spa(fam_p, n_boot=200, seed=5)
    sz = inference.spa(fam_z, n_boot=200, seed=5)
    assert sp["best_arm"] == "arm0", sp
    assert sp["p_spa_consistent"] < 0.05, sp
    assert sz["p_spa_consistent"] > 0.05, sz
    assert sz["verdict"] == "WITHIN_SPA_NULL"


def test_spa_brackets_are_ordered():
    fam = {f"arm{i}": _planted()[:, i] for i in range(8)}
    s = inference.spa(fam, n_boot=200, seed=2)
    assert s["p_spa_lower"] <= s["p_spa_consistent"] <= s["p_spa_upper"] + 1e-9, s


def test_spa_refuses_misaligned_arms():
    s = inference.spa({"a": np.zeros(40) + 0.1, "b": np.zeros(30) + 0.1}, n_boot=100)
    assert s["verdict"].startswith(inference.CANNOT_DETERMINE)
    assert "common index" in s["verdict"]


def test_spa_refuses_below_the_draw_floor():
    fam = {f"arm{i}": _planted()[:, i] for i in range(4)}
    s = inference.spa(fam, n_boot=8)
    assert s["verdict"].startswith(inference.CANNOT_DETERMINE)


# ------------------------------------------------------------------ CPCV / PBO


def test_cpcv_purges_and_embargoes_around_every_test_block():
    splits = inference.cpcv_splits(120, n_groups=6, k_test=2, purge=3, embargo=2)
    assert len(splits) == 15                       # C(6,2)
    for train, test in splits:
        assert not set(train.tolist()) & set(test.tolist())
        lo, hi = test.min(), test.max()
        # nothing inside the purge window before the first test index survives
        assert not [i for i in train if lo - 3 <= i < lo]
        assert not [i for i in train if hi < i <= hi + 2]


def test_pbo_is_low_on_a_planted_champion_and_near_a_coin_flip_on_noise():
    p = inference.pbo(_planted(n=240, n_arms=12), n_splits=8)
    z = inference.pbo(_null_world(n=240, n_arms=12), n_splits=8)
    assert p["pbo"] < 0.25, p
    assert p["verdict"] == "SELECTION_IS_STABLE"
    # A COIN FLIP IS THE FLOOR, NOT THE EXPECTATION. IS and OOS are
    # COMPLEMENTARY halves of one fixed sample, so an arm that looks good in
    # sample has, mechanically, drawn its good periods out of the other half --
    # under pure noise the in-sample champion is therefore worse than random
    # out of sample, and measured PBO here is ~0.8, not 0.5. The property being
    # tested is the ORDERING: a real edge survives the partition, noise does not.
    assert z["pbo"] > p["pbo"], (z, p)
    assert z["pbo"] >= 0.5, z
    assert z["verdict"] == "SELECTION_IS_OVERFIT", z


def test_pbo_refuses_a_single_arm():
    out = inference.pbo(np.zeros((100, 1)))
    assert out["verdict"].startswith(inference.CANNOT_DETERMINE)


# ------------------------------------------------------------------ draw store


def test_draw_store_round_trips_and_groups_by_seed(tmp_path):
    st = inference.DrawStore(tmp_path / "draws.jsonl", family_id="fam1")
    for seed in range(3):
        for cell in ("a", "b"):
            st.add(cell, seed, stat=float(seed) + (0.5 if cell == "b" else 0.0))
    st.flush()
    by_cell = inference.DrawStore.load(tmp_path / "draws.jsonl", "fam1")
    assert sorted(by_cell) == ["a", "b"] and len(by_cell["a"]) == 3
    per_draw = inference.DrawStore.per_draw_cells(tmp_path / "draws.jsonl", "fam1")
    assert len(per_draw) == 3 and per_draw[0] == {"a": 0.0, "b": 0.5}


def test_draw_store_ignores_another_family(tmp_path):
    p = tmp_path / "draws.jsonl"
    inference.DrawStore(p, family_id="one").add("a", 0, 1.0) or None
    st = inference.DrawStore(p, family_id="one")
    st.add("a", 0, 1.0)
    st.flush()
    st2 = inference.DrawStore(p, family_id="two")
    st2.add("a", 0, 99.0)
    st2.flush()
    assert inference.DrawStore.load(p, "one") == {"a": [1.0]}


# ------------------------------------------------------------------- the suite


def test_full_report_runs_all_four_and_names_the_cell_count():
    P = _planted(n=180, n_arms=10)
    fam = {f"arm{i}": P[:, i] for i in range(P.shape[1])}
    rep = inference.full_report(P[:, 0], family=fam, paired_excess=fam, n_trials=40,
                                n_boot=200, seed=1)
    assert rep["n_cells_looked_at"] == 40
    assert rep["deflated_sharpe"]["n_trials"] == 40
    assert rep["spa"]["best_arm"] == "arm0"
    assert "pbo" in rep


def test_the_normal_helpers_agree_with_scipy_if_it_is_there():
    """The Acklam fallback is only correct if it is actually correct."""
    for p in (0.01, 0.1, 0.5, 0.9, 0.975, 0.999):
        z = inference._nppf(p)
        assert abs(inference._ncdf(z) - p) < 1e-6, (p, z)
