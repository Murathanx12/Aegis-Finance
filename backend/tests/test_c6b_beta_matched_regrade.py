"""Tests for `scripts/c6b_beta_matched_regrade.py` -- the intercept-or-loading job.

WHAT THESE PIN, AND WHY EACH ONE EXISTS
=======================================
* the regression recovers a KNOWN alpha and beta -- the whole receipt is one
  number from this function and nothing else checks it;
* a book that IS `beta x market + (1 - beta) x rf` has a beta-matched excess of
  zero. That is the null the job's headline is measured against, and if the
  plumbing leaked it would read as alpha on every row;
* the Monte-Carlo null is deterministic under a fixed seed AND ACROSS PROCESSES.
  The first version seeded from `hash(key + label)`, which Python salts per
  interpreter -- reproducible inside one run and never between two, which is the
  one thing a seed is for. `test_stable_seed_survives_a_different_pythonhashseed`
  is that bug, pinned;
* a share of a non-positive total is flagged rather than printed beside 0.8355
  as if it were the same statistic;
* the walk-forward beta never sees month t;
* the receipt on disk carries `_provenance` with a NON-EMPTY `_inputs_opened`,
  which is the schema item 6 of this session's mandate reads.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import c6b_beta_matched_regrade as C1                     # noqa: E402


# ------------------------------------------------------- A: the regression

def test_ols_recovers_a_known_alpha_and_beta():
    rng = np.random.default_rng(20260906)
    n = 400
    x = rng.normal(0.008, 0.045, n)
    e = rng.normal(0.0, 0.004, n)
    y = 0.003 + 1.25 * x + e
    r = C1.ols_market_model(y, x)
    assert r["n_months"] == n
    assert r["alpha_monthly"] == pytest.approx(0.003, abs=5e-4)
    assert r["beta"] == pytest.approx(1.25, abs=0.01)
    assert r["alpha_annualised_12x"] == pytest.approx(0.003 * 12, abs=6e-3)
    # t(beta - 1) must be large and positive here -- the loading IS 1.25.
    assert r["t_beta_minus_1_ols"] > 10
    assert r["t_beta_minus_1_hac"] > 5
    # signal sd 1.25 * 0.045 = 0.056 against noise sd 0.004, so R^2 ~ 0.994.
    assert 0.999 > r["r_squared"] > 0.99
    assert r["residual_sd_monthly"] == pytest.approx(0.004, abs=5e-4)


def test_ols_on_a_pure_market_series_finds_beta_one_and_no_alpha():
    rng = np.random.default_rng(11)
    x = rng.normal(0.007, 0.04, 300)
    r = C1.ols_market_model(x, x)
    assert r["beta"] == pytest.approx(1.0, abs=1e-9)
    assert r["alpha_monthly"] == pytest.approx(0.0, abs=1e-12)
    assert abs(r["t_beta_minus_1_ols"]) < 1e-4


def test_ols_refuses_a_series_too_short_to_regress():
    r = C1.ols_market_model([0.01, 0.02, 0.03], [0.01, 0.02, 0.03])
    assert r["verdict"].startswith("CANNOT DETERMINE")
    assert r["n_months"] == 3


# ------------------------------------------------- B: the beta-matched leg

def _bench(values, freq="M", bid="vw_crsp_common_main"):
    from learner import benchmark as BM
    idx = pd.date_range("2004-01-31", periods=len(values), freq="ME")
    return BM.Benchmark(bid, pd.Series(np.asarray(values, float), index=idx), freq,
                        {"construction": "synthetic fixture", "network": False})


def test_beta_matched_excess_of_a_pure_beta_market_series_is_zero():
    """A book that is EXACTLY the leveraged market must show no alpha."""
    from learner import benchmark as BM
    rng = np.random.default_rng(7)
    n = 251
    mkt = rng.normal(0.008, 0.045, n)
    rf = np.full(n, 0.0013)
    beta = 1.3294
    net = beta * mkt + (1.0 - beta) * rf          # the leverage and nothing else

    reg = C1.ols_market_model(net - rf, mkt - rf)
    assert reg["beta"] == pytest.approx(beta, abs=1e-9)
    assert reg["alpha_monthly"] == pytest.approx(0.0, abs=1e-12)

    leg = BM.beta_matched(_bench(mkt), reg["beta"],
                          _bench(rf, bid="cash_rf_pinned"))
    excess = net - leg.returns.to_numpy()
    assert np.max(np.abs(excess)) < 1e-9
    ok, why = BM.validate_stamp(leg.stamp())
    assert ok, why


def test_beta_matched_leg_reconstructs_beta_times_market_plus_cash():
    from learner import benchmark as BM
    mkt = np.array([0.02, -0.03, 0.011, 0.004, 0.05])
    rf = np.array([0.001, 0.001, 0.0012, 0.0011, 0.0013])
    for beta in (0.8, 1.0, 1.3294):
        leg = BM.beta_matched(_bench(mkt), beta, _bench(rf, bid="cash_rf_pinned"))
        want = beta * mkt + (1.0 - beta) * rf
        assert np.max(np.abs(leg.returns.to_numpy() - want)) < 1e-12


def test_walk_forward_beta_never_sees_the_month_it_grades():
    """beta_t uses months strictly before t -- a jump at t must not move beta_t."""
    rng = np.random.default_rng(3)
    n = 120
    x = pd.Series(rng.normal(0.0, 0.04, n))
    y = pd.Series(1.0 * x.to_numpy() + rng.normal(0.0, 0.001, n))
    base = C1.walk_forward_beta(y, x, min_months=36)
    y2 = y.copy()
    y2.iloc[60] = 5.0                       # a violent shock AT month 60
    shocked = C1.walk_forward_beta(y2, x, min_months=36)
    assert base.iloc[60] == pytest.approx(shocked.iloc[60], abs=1e-12)
    assert base.iloc[61] != pytest.approx(shocked.iloc[61], abs=1e-6)
    assert base.iloc[:36].isna().all()


# ---------------------------------------------------------- D: the tail flag

def test_top5_block_reproduces_the_house_by_net_rule():
    net = pd.Series([0.30, 0.20, 0.15, 0.10, 0.08, 0.01, -0.02, -0.05],
                    index=[f"2004-{i:02d}" for i in range(1, 9)])
    bench = pd.Series(0.0, index=net.index)
    b = C1.top5_block(net, bench, selection="net")
    assert list(b["best_5_months"]) == ["2004-01", "2004-02", "2004-03",
                                        "2004-04", "2004-05"]
    assert b["share_of_total_excess_from_those_5"] == pytest.approx(
        0.83 / 0.77, abs=1e-3)
    assert b["total_excess_is_positive"] is True
    assert b["share_is_interpretable"] is True


def test_top5_block_flags_a_share_of_a_non_positive_total():
    """0.8355 and -1.09 are not the same statistic and must not read as one."""
    net = pd.Series([0.30, 0.20, 0.15, 0.10, 0.08, -0.40, -0.30, -0.20],
                    index=[f"2004-{i:02d}" for i in range(1, 9)])
    bench = pd.Series(0.0, index=net.index)
    b = C1.top5_block(net, bench, selection="net")
    assert b["total_excess_is_positive"] is False
    assert b["share_is_interpretable"] is False


# -------------------------------------------------- E: the Monte-Carlo null

def test_mc_top5_null_is_deterministic_under_a_fixed_seed():
    a = C1.mc_top5_null(0.0028, 0.036, 251, 0.8355, draws=2000, seed=99, dist="normal")
    b = C1.mc_top5_null(0.0028, 0.036, 251, 0.8355, draws=2000, seed=99, dist="normal")
    assert a == b
    c = C1.mc_top5_null(0.0028, 0.036, 251, 0.8355, draws=2000, seed=100, dist="normal")
    assert c["p_share_ge_observed"] != a["p_share_ge_observed"]


def test_mc_top5_null_t4_is_rescaled_to_the_declared_sd():
    """t4's raw sd is sqrt(2); the null must differ in SHAPE, not dispersion."""
    rng = np.random.default_rng(5)
    raw = rng.standard_t(4, size=400_000)
    scaled = 0.0 + 0.036 * raw / math.sqrt(4 / 2.0)
    assert float(scaled.std(ddof=1)) == pytest.approx(0.036, rel=0.03)
    out = C1.mc_top5_null(0.0028, 0.036, 251, 0.8355, draws=2000, seed=1, dist="t4")
    assert out["dist"] == "t4"
    assert out["sd_used"] == pytest.approx(0.036)


def test_mc_top5_null_refuses_an_unknown_distribution():
    with pytest.raises(ValueError):
        C1.mc_top5_null(0.0, 0.03, 100, 0.5, draws=100, seed=1, dist="cauchy")


def test_mc_top5_null_reports_both_p_values_and_the_positive_share():
    out = C1.mc_top5_null(0.0028, 0.036, 251, 0.8355, draws=5000, seed=2, dist="normal")
    for k in ("p_share_ge_observed", "p_share_ge_observed_given_positive_total",
              "share_of_draws_with_positive_total", "p_turns_negative_without_top5"):
        assert out[k] is not None
    assert 0.0 <= out["p_share_ge_observed"] <= 1.0


def test_stable_seed_survives_a_different_pythonhashseed():
    """The bug this replaced: `hash(str)` is salted per interpreter."""
    code = ("import sys; sys.path.insert(0, r'%s');"
            "from scripts import c6b_beta_matched_regrade as C1;"
            "print(C1.stable_seed(20260906, 'lgbm_clf|10bps|raw_market_excess'))"
            % str(REPO))
    seen = set()
    for salt in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=salt)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, env=env, timeout=180)
        assert r.returncode == 0, r.stderr[-2000:]
        seen.add(r.stdout.strip())
    assert len(seen) == 1, f"seed changed with PYTHONHASHSEED: {seen}"
    assert seen.pop() == str(C1.stable_seed(20260906,
                                            "lgbm_clf|10bps|raw_market_excess"))


# ------------------------------------------------------------- the receipt

RECEIPT = C1.RECEIPT


def _receipt() -> dict:
    assert RECEIPT.exists(), (
        f"{RECEIPT} is missing. Run "
        "`python -m scripts.c6b_beta_matched_regrade` -- this test pins the "
        "receipt's schema and a missing receipt is a failure, not a skip.")
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_receipt_carries_provenance_with_nonempty_inputs_opened():
    rec = _receipt()
    prov = rec.get("_provenance")
    assert isinstance(prov, dict), "no _provenance block"
    assert prov.get("sys_argv"), "sys_argv is empty"
    assert isinstance(prov.get("resolved_config"), dict) and prov["resolved_config"]
    opened = prov.get("_inputs_opened")
    assert isinstance(opened, list) and opened, "_inputs_opened is empty"
    for row in opened:
        assert set(row) >= {"path", "sha256", "bytes"}
        assert len(row["sha256"]) == 64
        assert int(row["bytes"]) > 0
        assert Path(row["path"]).is_absolute()
    assert prov.get("git_commit")
    assert prov.get("generated_utc")


def test_receipt_reproduces_every_w3b_cell():
    rec = _receipt()
    assert rec.get("universe_fingerprint_matches_w3b") is True
    assert rec.get("all_cells_reproduce_w3b") is True, rec.get(
        "reproduction_of_w3b_cells")


def test_receipt_carries_a_valid_benchmark_stamp():
    from learner import benchmark as BM
    rec = _receipt()
    ok, why = BM.validate_stamp(rec.get("benchmark_stamp"))
    assert ok, why
    for cell in rec["by_cell"].values():
        ok, why = BM.validate_stamp(cell["B_beta_matched"]["benchmark_stamp"])
        assert ok, why


def test_receipt_alpha_equals_the_mean_of_the_beta_matched_excess():
    """They are the same number by construction; a gap means the legs disagree."""
    rec = _receipt()
    for key, cell in rec["by_cell"].items():
        a = cell["A_market_regression"]["alpha_annualised_12x"]
        b = cell["B_beta_matched"]["annualised_excess_12x"]
        assert a == pytest.approx(b, abs=2e-4), f"{key}: alpha {a} vs excess {b}"
        assert cell["B_beta_matched"]["leg_reconstruction_max_abs_error"] < 1e-9


def test_receipt_carries_every_mandated_edge_statistic():
    rec = _receipt()
    for key, cell in rec["by_cell"].items():
        c = cell["C_inference_on_beta_matched_excess"]
        assert c["family_size_declared_for_deflation"] == C1.FAMILY_N_TRIALS
        assert c.get("family_max_p_spa_consistent") is not None, key
        assert (c.get("deflated_sharpe") or {}).get("dsr") is not None, key
        assert c.get("mde_annual_excess_at_t_target") is not None, key
        assert cell["C_era_sign_table"].get("eras_measured") == 3, key


def test_receipt_answers_intercept_or_loading_in_one_sentence():
    rec = _receipt()
    assert rec.get("one_sentence_answer")
    assert "lgbm_clf" in rec["one_sentence_answer"]
    assert "nn_pre_causal" in rec["one_sentence_answer"]
    assert set(rec["verdict_by_cell"]) == {
        f"{b}|{int(c)}bps" for b in C1.BOOKS for c in C1.COSTS}


@pytest.mark.slow
def test_the_job_reruns_and_still_reproduces_w3b():
    """Needs the long panel AND the W3b stage parquets.

    The stage files live in TEMP on purpose (they are 30 MB of intermediate
    predictions), so they may legitimately be absent on a machine that has not
    re-staged. That is the ONE skip in this file and it is explicit: the durable
    artefact is the receipt, which the tests above check unconditionally.
    """
    if not C1.W3B._stage_path("incumbents").exists():
        pytest.skip("W3b stage parquets absent -- re-stage with "
                    "`python -m scripts.w3_neural_floored --stage incumbents` "
                    "and `--stage nn_pre_causal`")
    res = C1.run(verbose=False, mc_draws=500)
    assert res.get("all_cells_reproduce_w3b") is True
    assert res.get("n_common_months") == 251
