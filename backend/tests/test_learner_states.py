"""The five things about the UNSUPERVISED STATE LEARNER that must stay true.

`learner/states.py` discovers latent market states without the target and then
grades what the states condition. Almost every way that experiment can be wrong
is a way it still comes out GREEN and interesting:

1. the representation is handed a future column and "states predict returns"
   becomes a tautology;
2. a block trains on the months it later labels, so the OOS protocol is a
   sentence in a docstring rather than a property of the code;
3. KMeans relabels between refits and the transition matrix reads
   relabelling noise as regime change;
4. the shuffled null is computed in a way that cannot fail;
5. the incumbent's IC comes back as `months: 0` because a distinctness filter
   deleted a five-valued predictor -- a gate that cannot go green.

Each of the five has a test below. They run OFFLINE on synthetic frames in
about a second, load no parquet, touch no network, and use
`np.random.default_rng` only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from learner import states as S


# ------------------------------------------------------------------ fixtures

def _panel(n_names: int = 60, n_months: int = 40, seed: int = 11,
           planted: bool = True) -> pd.DataFrame:
    """A synthetic panel with a PLANTED two-group structure.

    Half the names are drawn around one centre and half around another, and
    (when `planted`) the second group's forward excess return is shifted. A
    state learner that cannot recover a structure this obvious is broken; the
    null test below then checks the same machinery does NOT find structure when
    the shift is removed.

    Every date is DERIVED from `today`, never written down: a fixture with a
    literal calendar moment in it fails the day after that moment passes.
    """
    rng = np.random.default_rng(seed)
    end = pd.Timestamp.today().normalize().to_period("M") - 1
    months = pd.period_range(end - (n_months - 1), end, freq="M")
    rows = []
    for i in range(n_names):
        grp = i % 2
        for mp in months:
            entry = mp.to_timestamp(how="start").normalize() + pd.Timedelta(days=14)
            row = {"permno": 10000 + i, "month": str(mp), "entry_date": entry,
                   "band": "b_1_5_3" if grp else "lt_1_5"}
            for f in S.STATE_FEATURES:
                row[f] = float(rng.normal(loc=2.0 * grp, scale=1.0))
            row["excess_vw_1m"] = float(rng.normal(loc=0.02 * grp if planted else 0.0,
                                                   scale=0.08))
            row["excess_vw_3m"] = row["excess_vw_1m"] * 3
            row["fwd_3m"] = row["excess_vw_3m"] + 0.02
            row["prior_1m"] = 0.005 if grp else 0.002
            row["mat_date_1m"] = entry + pd.DateOffset(months=1)
            rows.append(row)
    return pd.DataFrame(rows).sort_values(["month", "permno"]).reset_index(drop=True)


def _blocks(df: pd.DataFrame, ks=(2,), min_train_months: int = 12,
            refit_every: int = 6):
    """The runner's loop, reduced to what a test needs: fit on the past,
    assign the block, keep the block bookkeeping the guard reads."""
    months = sorted(df["month"].unique())
    out, blocks = [], []
    prev_ref, ref_embedder = {k: None for k in ks}, None
    for bi, bm in enumerate(S.month_blocks(months, refit_every, min_train_months)):
        te = df[df["month"].isin(bm)]
        first_entry = te["entry_date"].min()
        tr = df[df["entry_date"] < first_entry]
        if tr["month"].nunique() < min_train_months or te.empty:
            continue
        fitted = S.fit_block(tr, ks, nn_reference_cutoff=first_entry)
        if ref_embedder is None:
            ref_embedder = fitted["embedder"]
        res = S.assign_block(fitted, te, ks)
        S.stabilise_block_labels(fitted, res, ks, prev_ref, ref_embedder)
        res["block_id"] = bi
        out.append(res)
        blocks.append(S.Block(block_id=bi, train_last_date=tr["entry_date"].max(),
                              assign_first_date=first_entry, assign_months=list(bm),
                              n_train_rows=len(tr),
                              n_train_months=tr["month"].nunique(),
                              n_assign_rows=len(te)))
    return pd.concat(out, ignore_index=True), blocks


# ---------------------------------------------------------------- the guards

def test_the_representation_refuses_future_columns():
    """1. A target column reaching the fitting side is a REFUSAL, not a warning."""
    for bad in ("excess_vw_1m", "fwd_3m", "resid_vw_1m", "prior_1m", "mat_date_1m",
                "mkt_vw_1m", "pos_vw_1m"):
        with pytest.raises(ValueError, match="REFUSED"):
            S.assert_no_target_columns(list(S.STATE_FEATURES) + [bad])
    # and the declared feature set itself must always pass
    S.assert_no_target_columns(S.STATE_FEATURES)


def test_no_state_feature_is_a_target():
    """The list itself, not just the checker. A feature added to STATE_FEATURES
    that happens to be a forward return would slip past a test of the checker."""
    for f in S.STATE_FEATURES:
        assert not any(f.startswith(p) for p in S.TARGET_PREFIXES), f
    for f in S.MARKET_FEATURES:
        assert not any(f.startswith(p) for p in S.TARGET_PREFIXES), f


def test_every_block_trains_strictly_before_the_months_it_labels():
    """2. The OOS protocol, as a property of the data rather than a paragraph."""
    df = _panel()
    A, blocks = _blocks(df)
    assert len(blocks) >= 2, "the fixture must produce at least two refit blocks"
    receipt = S.assert_block_ordering(blocks)          # raises if it ever crosses
    assert receipt["blocks"]
    for b in blocks:
        assert b.train_last_date < b.assign_first_date
    # and no assigned month is ever in a later block's training window by month
    assert A["month"].nunique() == sum(len(b.assign_months) for b in blocks)


def test_the_ordering_guard_can_actually_fail():
    """A guard that cannot go red is decoration. This one goes red."""
    bad = S.Block(block_id=0, train_last_date=pd.Timestamp("2020-06-30"),
                  assign_first_date=pd.Timestamp("2020-01-15"))
    with pytest.raises(ValueError, match="REFUSED"):
        S.assert_block_ordering([bad])


def test_state_ids_are_matched_across_refits_not_left_arbitrary():
    """3. Hungarian matching returns a permutation that restores identity."""
    prev = np.array([[0.0, 0.0], [5.0, 5.0], [-5.0, 5.0]])
    cur = prev[[2, 0, 1]] + 0.01                       # same states, relabelled
    perm, drift, sep = S.match_states(prev, cur)
    assert sorted(perm.tolist()) == [0, 1, 2]
    assert perm.tolist() == [2, 0, 1]
    assert drift < 0.1 and sep > 1.0                   # same state, far apart states
    assert drift / sep < S.MAX_DRIFT_RATIO


def test_the_planted_structure_is_recovered_and_beats_its_own_shuffle():
    """4a. On a panel with a real planted difference, the null is CLEARED."""
    df = _panel(planted=True)
    A, _ = _blocks(df)
    g = A.merge(df[["permno", "month", "excess_vw_1m"]], on=["permno", "month"])
    null = S.shuffled_null(g, "state_k2", "excess_vw_1m", n_shuffles=60)
    assert null["observed"] > null["null_p95"], null
    assert null["beats_random_partition"] is True


def test_without_cross_block_matching_the_planted_effect_cancels():
    """The reason `stabilise_block_labels` exists, pinned as a test.

    KMeans hands out arbitrary integers. Two consecutive blocks can name the
    same group 0 and then 1; pooling them averages a real difference toward
    zero. This test runs the loop WITHOUT the matching step and asserts the
    spread collapses -- so if someone deletes the matching as an optimisation,
    the suite says which number it broke rather than going quietly green.
    """
    df = _panel(planted=True)
    matched, _ = _blocks(df)
    months = sorted(df["month"].unique())
    raw = []
    for bm in S.month_blocks(months, 6, 12):
        te = df[df["month"].isin(bm)]
        first_entry = te["entry_date"].min()
        tr = df[df["entry_date"] < first_entry]
        if tr["month"].nunique() < 12 or te.empty:
            continue
        fitted = S.fit_block(tr, (2,), nn_reference_cutoff=first_entry)
        raw.append(S.assign_block(fitted, te, (2,)))           # no matching
    raw = pd.concat(raw, ignore_index=True)

    tgt = df[["permno", "month", "excess_vw_1m"]]
    s_matched = S.spread_statistic(matched.merge(tgt, on=["permno", "month"]),
                                   "state_k2", "excess_vw_1m")
    s_raw = S.spread_statistic(raw.merge(tgt, on=["permno", "month"]),
                               "state_k2", "excess_vw_1m")
    assert s_matched > 2 * s_raw, (s_matched, s_raw)


def test_the_null_can_refuse_a_partition_with_nothing_in_it():
    """4b. And on a panel with NO planted difference it is NOT cleared.

    Both directions are needed. A null that always fires is a decoration; a
    null that never fires is a rubber stamp. (Canon: a null owes two tests.)
    """
    df = _panel(planted=False, seed=23)
    A, _ = _blocks(df)
    g = A.merge(df[["permno", "month", "excess_vw_1m"]], on=["permno", "month"])
    null = S.shuffled_null(g, "state_k2", "excess_vw_1m", n_shuffles=120)
    assert null["p_value_one_sided"] > 0.05, null


def test_a_five_valued_predictor_is_still_measurable():
    """5. BAND_PRIOR emits at most five distinct numbers. `monthly_ic` must
    MEASURE it, not report `months: 0` and read as 'no signal'."""
    df = _panel()
    ic = S.monthly_ic(df, "prior_1m", "excess_vw_1m")
    assert ic["months"] >= 6, ic
    assert "mean_ic" in ic
    assert ic["mean_distinct_predictions"] <= 5


def test_grading_helpers_are_shaped_and_deterministic():
    df = _panel()
    A, _ = _blocks(df)
    g = A.merge(df[["permno", "month", "excess_vw_1m", "excess_vw_3m", "fwd_3m",
                    "prior_1m", "band"]], on=["permno", "month"])
    tbl = S.conditional_table(g, "state_k2")
    assert len(tbl) == 2
    assert abs(sum(r["share"] for r in tbl) - 1.0) < 1e-6
    for r in tbl:
        assert r["excess_vw_1m"]["p05"] <= r["excess_vw_1m"]["median"] <= r["excess_vw_1m"]["p95"]

    tr = S.transition_matrix(A, "state_k2")
    assert tr["pairs"] > 0
    assert 0.0 <= tr["mean_persistence_diagonal"] <= 1.0

    ic = S.state_ic_table(g, "state_k2", ["prior_1m"], "excess_vw_1m")
    moe = S.mixture_of_experts_summary(ic)
    assert "prior_1m" in moe

    # same seed, same answer
    a = S.shuffled_null(g, "state_k2", "excess_vw_1m", n_shuffles=20, seed=5)
    b = S.shuffled_null(g, "state_k2", "excess_vw_1m", n_shuffles=20, seed=5)
    assert a == b


def test_market_features_are_trailing_and_states_are_expanding_window():
    df = _panel(n_months=40)
    df["ret_1m"] = df["ret_1m"] if "ret_1m" in df else 0.0
    df["ratio"] = 1.5
    mf = S.market_month_features(df)
    assert list(mf.columns) == list(S.MARKET_FEATURES)
    assert len(mf) == df["month"].nunique()
    ms, meta = S.run_market_states(mf, k=2, min_train_months=12)
    assert meta["assigned_months"] == len(mf) - 12
    assert set(ms["market_state"].unique()) <= {0, 1}
    # the first assigned month is the 13th, never the 1st: no month labels itself
    assert ms["month"].iloc[0] == list(mf.index)[12]


def test_nearest_neighbours_come_only_from_matured_history():
    """The retrieval pool may only contain rows whose own target had matured
    before the assigned month began -- otherwise `nn_excess_1m_mean` is a
    lookup of the answer wearing a neighbour's name."""
    df = _panel()
    months = sorted(df["month"].unique())
    bm = S.month_blocks(months, 6, 12)[0]
    te = df[df["month"].isin(bm)]
    first_entry = te["entry_date"].min()
    tr = df[df["entry_date"] < first_entry]
    fitted = S.fit_block(tr, (2,), nn_reference_cutoff=first_entry)
    ids = fitted["nn_ids"]
    pool = tr.merge(ids, on=["permno", "month"])
    assert len(pool) > 0
    assert (pool["mat_date_1m"] < first_entry).all()

    res = S.assign_block(fitted, te, (2,))
    assert {"nn1_permno", "nn1_month", "nn1_dist", "nn_excess_1m_mean"} <= set(res.columns)
    assert (res["nn1_dist"] >= 0).all()
    assert res["nn1_month"].isin(set(tr["month"])).all()


def test_schema_hash_is_stable_and_names_the_contract():
    h1, h2 = S.schema_hash(), S.schema_hash()
    assert h1 == h2 and len(h1) == 16
    sc = S.schema()
    assert sc["schema_version"] == S.SCHEMA_VERSION
    assert set(sc["target_prefixes_refused_on_the_fitting_side"]) == set(S.TARGET_PREFIXES)
