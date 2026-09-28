"""Lane M6: TRIAL-LIB-FWD-TWIN-1's pairing, pooled z, kill rule and luck table.
Synthetic rows only; a temporary registry DB; no network."""
from __future__ import annotations

import math

import pytest

from backend.services import lib_forward_trial as LT


def _books():
    return [
        {"book_id": "a", "name": "lib_a", "kind": "personal"},
        {"book_id": "b", "name": "lib_b", "kind": "control"},
        {"book_id": "v", "name": "lib_v", "kind": "personal"},
        {"book_id": "v", "name": "lib_v", "kind": "void"},
        {"book_id": "p", "name": "pers_x", "kind": "personal"},            # not a lib_ book
        {"book_id": "ta1", "kind": "twin", "twin": "random_same_band", "parent_book_id": "a"},
        {"book_id": "ta2", "kind": "twin", "twin": "matched_random", "parent_book_id": "a"},
        {"book_id": "tb1", "kind": "twin", "twin": "random_same_band", "parent_book_id": "b"},
        {"book_id": "tv1", "kind": "twin", "twin": "matched_random", "parent_book_id": "v"},
    ]


def test_pairs_prefer_the_matched_twin_and_skip_void_and_non_library_books():
    pairs = LT.select_pairs(_books())
    assert [p["name"] for p in pairs] == ["lib_a", "lib_b"]
    a = pairs[0]
    assert a["twin_book_id"] == "ta2" and a["twin_type"] == "matched_random"
    assert pairs[1]["twin_type"] == "random_same_band"


def test_a_library_book_without_a_frozen_twin_refuses_by_name():
    rows = [{"book_id": "c", "name": "lib_c", "kind": "personal"},
            {"book_id": "tc", "kind": "twin", "twin": "ew", "parent_book_id": "c"}]
    with pytest.raises(LT.LibTrialInputMissing, match="lib_c"):
        LT.select_pairs(rows)


def test_cluster_of_uses_the_bridge_and_makes_a_forward_only_book_its_own_cluster():
    rows = [{"book": "lib_a", "cluster_full": 170}, {"book": "lib_f", "cluster_full": None}]
    assert LT.cluster_of("lib_a", rows) == "170"
    assert LT.cluster_of("lib_f", rows) == "solo:lib_f"
    assert LT.cluster_of("lib_missing", rows) == "solo:lib_missing"


def test_pooled_sd_matches_the_closed_form():
    # two clusters: {a, b} and {c}; sigma 1 each
    s = {"a": 1.0, "b": 1.0, "c": 1.0}
    cl = {"a": "1", "b": "1", "c": "2"}
    rw, rb = 0.5, 0.0
    # D = 0.5 * (a+b)/2 + 0.5 * c ; var = 0.25 * (2 + 2*0.5)/4 + 0.25 = 0.1875 + 0.25
    assert LT.pooled_sd(s, cl, rw, rb) == pytest.approx(math.sqrt(0.4375))
    # independent singletons: sd = sigma / sqrt(C)
    assert LT.pooled_sd(s, {"a": "1", "b": "2", "c": "3"}, 0.0, 0.0) == pytest.approx(1 / math.sqrt(3))


def test_pooled_z_reads_only_the_frozen_sigma_and_refuses_a_missing_one():
    frozen = {"sigma_21": {"a": 0.1, "b": 0.1, "c": 0.1}, "rho_within": 0.0, "rho_between": 0.0}
    cl = {"a": "1", "b": "1", "c": "2"}
    r = LT.pooled_z({"a": 0.02, "b": 0.04, "c": 0.06}, cl, frozen, 21)
    assert r["pooled_diff"] == pytest.approx((0.03 + 0.06) / 2)
    assert r["n_clusters"] == 2 and r["z"] > 0
    with pytest.raises(LT.LibTrialInputMissing):
        LT.pooled_z({"z": 0.01}, {"z": "9"}, frozen, 21)


def test_the_kill_rule_every_branch():
    d = LT.decide
    assert d({"z": -2.5, "pooled_diff": -0.1}, None, n_expected=30, n_dropped=0)["verdict"] == "EARLY_KILL"
    assert d({"z": -1.0, "pooled_diff": -0.01}, None, n_expected=30, n_dropped=0)["verdict"] == "INTERIM"
    assert d({"z": 1, "pooled_diff": 0.01}, {"z": 2.3}, n_expected=30, n_dropped=0)["verdict"] == "SURVIVES"
    # z_63 clears 2 but the 21-session sign was negative: not SURVIVES
    assert d({"z": -0.2, "pooled_diff": -0.01}, {"z": 2.3}, n_expected=30,
             n_dropped=0)["verdict"] == "CANNOT_DISTINGUISH"
    assert d({"z": 0.1, "pooled_diff": 0.001}, {"z": 0.4}, n_expected=30, n_dropped=0)["verdict"] == "KILL"
    assert d({"z": 0.1, "pooled_diff": 0.001}, {"z": 1.5}, n_expected=30,
             n_dropped=0)["verdict"] == "CANNOT_DISTINGUISH"
    assert d(None, {"z": 3.0}, n_expected=30, n_dropped=9)["verdict"] == "CANNOT_DETERMINE"


def test_luck_table_matches_the_closed_form_when_independent():
    rows = LT.luck_table([17, 30], [0.0], n_sim=200_000)
    for r in rows:
        assert r["p_best_ge_z"] == pytest.approx(r["p_independent_closed_form"], abs=0.01)
    corr = LT.luck_table([30], [0.5], n_sim=50_000)[0]
    assert corr["p_best_ge_z"] < rows[1]["p_best_ge_z"]           # correlation lowers the max


def test_registration_is_idempotent_and_counts_once(tmp_path):
    db = tmp_path / "pi.db"
    a = LT.ensure_lib_forward_trial(db_path=db, frozen_receipt="x.json")
    b = LT.ensure_lib_forward_trial(db_path=db)
    assert a == b
    from backend.db import get_connection
    c = get_connection(db)
    try:
        n = c.execute("SELECT COUNT(*) AS n FROM rule_experiments WHERE param = ?",
                      (LT.PARAM,)).fetchone()["n"]
    finally:
        c.close()
    assert n == 1


# ── AMENDMENT 2026-09-28 (review F2): the deciding correlations are the as-read ones ──

def test_the_grader_decides_on_the_as_read_correlation_and_prints_the_registered_beside_it():
    sig = {"a": 0.08, "b": 0.08, "c": 0.08, "d": 0.08}
    cl = {"a": "1", "b": "1", "c": "2", "d": "3"}
    frozen = {"sigma_21": sig, "rho_within": LT.RHO_WITHIN_REGISTERED,
              "rho_between": LT.RHO_BETWEEN_REGISTERED}
    r = LT.pooled_z({"a": 0.05, "b": 0.05, "c": 0.05, "d": 0.05}, cl, frozen, 21)
    sd_new = LT.pooled_sd(sig, cl, LT.RHO_WITHIN_AS_READ, LT.RHO_BETWEEN_AS_READ)
    sd_old = LT.pooled_sd(sig, cl, LT.RHO_WITHIN_REGISTERED, LT.RHO_BETWEEN_REGISTERED)
    assert r["sd"] == pytest.approx(sd_new) and r["sd_registered"] == pytest.approx(sd_old)
    assert r["z"] == pytest.approx(0.05 / sd_new)
    assert abs(r["z"]) < abs(r["z_registered"])      # the wider bar never flatters z
    # the verdict is taken on the deciding z: a pooled edge that reads z >= 2 only on
    # the registered (too narrow) bar must NOT survive
    D = 2.2 * sd_old
    z63 = {"z": D / sd_new, "z_registered": D / sd_old}
    assert z63["z_registered"] >= 2 > z63["z"]
    v = LT.decide({"z": 0.5, "pooled_diff": 0.01}, z63, n_expected=30, n_dropped=0)
    assert v["verdict"] != "SURVIVES"


def test_the_amended_correlations_are_the_wider_ones_and_the_bets_are_few():
    assert LT.RHO_BETWEEN_AS_READ > LT.RHO_BETWEEN_REGISTERED
    assert LT.RHO_WITHIN_AS_READ > LT.RHO_WITHIN_REGISTERED
    assert LT.effective_bets(17, 0.0) == pytest.approx(17.0)
    assert LT.effective_bets(17, LT.RHO_BETWEEN_AS_READ) < 3.0


def test_estimate_takes_rho_from_the_difference_type_the_trial_reads(tmp_path, monkeypatch):
    """A band-only pair's correlation must come from rule - random_1 (the style
    the band-only twin leaves in), not from rule - matched twin."""
    import numpy as np
    import pandas as pd
    from scripts import lib_forward_trial as S
    months = pd.date_range(end=pd.Timestamp.today().normalize(), periods=60, freq="ME")
    rng = np.random.default_rng(7)
    style = rng.normal(0, 0.05, 60)                           # shared momentum style
    cols = ["r1@k20", "r2@k20"]
    net = pd.DataFrame({"r1@k20": style + rng.normal(0, 0.01, 60),
                        "r2@k20": style + rng.normal(0, 0.01, 60),
                        "random_1@k50": rng.normal(0, 0.001, 60)}, index=months)
    tw = pd.DataFrame({("rule_minus_twin0", c): rng.normal(0, 0.02, 60) for c in cols}, index=months)
    tw.columns = pd.MultiIndex.from_tuples(tw.columns)
    tp, npth = tmp_path / "tw.parquet", tmp_path / "net.parquet"
    tw.to_parquet(tp)
    net.to_parquet(npth)
    monkeypatch.setattr(S, "TWIN_SERIES", tp)
    monkeypatch.setattr(S, "NET_SERIES", npth)
    pairs = [{"name": "A", "twin_type": "random_same_band"}, {"name": "B", "twin_type": "random_same_band"}]
    bridge = [{"book": "A", "rule": "r1", "cluster_full": 1}, {"book": "B", "rule": "r2", "cluster_full": 2}]
    est = S.estimate(pairs, bridge)
    assert abs(est["rho_between"]) < 0.4                     # matched differences: independent noise
    assert est["rho_between_as_read"] > 0.9                   # as read: the shared style
