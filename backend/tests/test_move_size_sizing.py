"""Offline tests for backend/services/move_size_sizing.py (the 2026-09-29 sizing lab).

Every fixture is synthetic and dated from a fixed origin that encodes no calendar moment
the suite could outlive (protocol item 5)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backend.services import move_size_sizing as MS

COSTS = {"mega": 6.0, "large": 10.0, "mid": 18.0, "small": 35.0}


def _panel(n_dates=30, n_names=60, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2001-01-31", periods=n_dates, freq="ME")
    rows = []
    for d in dates:
        vol = rng.uniform(0.1, 1.0, n_names)
        for i in range(n_names):
            rows.append({"date": d, "symbol": f"S{i}", "vol_63": vol[i],
                         "fwd_ret": rng.normal(0, vol[i] / 4), "eligible": True,
                         "median_dollar_vol": 5e7, "mom": rng.normal()})
    p = pd.DataFrame(rows)
    p["abs_x"] = MS.abs_excess(p)
    return p


def test_walk_forward_size_never_reads_a_target_inside_the_gap():
    p = _panel()
    base, log = MS.walk_forward_size(p, {"vol_63": "log"}, target="abs_x", gap=2, min_train_dates=5)
    dates = np.sort(p["date"].unique())
    j = 20
    # rewrite every target from date j-1 onward: forecasts at date j must not move
    q = p.copy()
    q.loc[q["date"] >= dates[j - 1], "abs_x"] = 9.9
    alt, _ = MS.walk_forward_size(q, {"vol_63": "log"}, target="abs_x", gap=2, min_train_dates=5)
    at_j = (p["date"] == dates[j]).to_numpy()
    assert np.allclose(base[at_j], alt[at_j])
    # ...while the date after it (which may train on j-1) is allowed to move
    at_j2 = (p["date"] == dates[j + 1]).to_numpy()
    assert not np.allclose(base[at_j2], alt[at_j2])
    assert log and all(pd.Timestamp(r["train_last"]) < pd.Timestamp(r["decision"]) for r in log)


def test_walk_forward_size_is_positive_and_ranks_the_size():
    p = _panel()
    f, _ = MS.walk_forward_size(p, {"vol_63": "log"}, target="abs_x", gap=2, min_train_dates=5)
    ok = f.notna()
    assert (f[ok] > 0).all()
    ic = MS.per_date_ic(p.assign(f=f), "f", "abs_x", mask=ok.to_numpy(), min_n=20)
    assert ic.mean() > 0.2


def test_quantile_map_keeps_the_reference_distribution_and_the_source_order():
    p = _panel(n_dates=3, n_names=40)
    p["src"] = -p["vol_63"] + np.random.default_rng(1).normal(0, 0.01, len(p))
    m = MS.quantile_map(p, "src", "vol_63", np.ones(len(p), bool))
    for _, g in p.assign(m=m).groupby("date"):
        assert np.allclose(np.sort(g["m"]), np.sort(g["vol_63"]))
        assert MS.spearman(g["m"], g["src"]) == pytest.approx(1.0)


def test_capped_normalise_caps_and_sums_to_one():
    w = MS.capped_normalise(np.array([10.0] + [1.0] * 19), cap=0.10)
    assert w.sum() == pytest.approx(1.0)
    assert w.max() <= 0.10 + 1e-12
    with pytest.raises(ValueError):
        MS.capped_normalise(np.ones(5), cap=0.1)


def test_inverse_size_weights_fill_a_missing_size_with_the_median():
    w = MS.inverse_size_weights(np.array([0.1, 0.2, np.nan, 0.4]), cap=1.0)
    assert w.sum() == pytest.approx(1.0)
    assert w[2] == pytest.approx(w[1])          # median of (0.1, 0.2, 0.4) is 0.2
    assert w[0] > w[1] > w[3]


def test_kelly_and_vol_target_gross():
    w = np.full(20, 0.05)
    s = np.full(20, 0.10)
    sp = MS.portfolio_sigma(w, s, rho=0.3)
    assert sp == pytest.approx(math.sqrt(0.7 * 20 * 0.05 ** 2 * 0.01 + 0.3 * 0.1 ** 2))
    g = MS.kelly_gross(w, s, mu=0.005, fraction=0.5, rho=0.3)
    assert g == pytest.approx(min(1.0, 0.5 * 0.005 / sp ** 2))
    assert MS.kelly_gross(w, s / 100, mu=0.005) == 1.0            # capped, never levered
    assert MS.vol_target_gross(w, s, target_monthly=0.02) == pytest.approx(0.02 / sp)


def test_calibrate_scale_is_mean_absolute():
    pred = np.array([1.0, 2.0, 3.0] * 20)
    real = np.array([0.1, -0.2, 0.3] * 20)
    k = MS.calibrate_scale(pred, real)
    assert k == pytest.approx(math.sqrt(math.pi / 2) * 0.2 / 2.0)


def test_hold_year_is_the_entry_month():
    y = MS.hold_years(pd.DatetimeIndex(["2003-12-31", "2004-01-30"]))
    assert list(y) == [2004, 2004]


def test_block_stats_uses_block_sums():
    d = pd.Series([0.01, 0.02, 0.00, 0.01, 0.03, 0.02, -0.01, 0.00, 0.01],
                  index=pd.date_range("2001-01-31", periods=9, freq="ME"))
    st = MS.block_stats(d, 3)
    sums = np.array([0.03, 0.06, 0.00])
    se_b = sums.std(ddof=1) / math.sqrt(3)
    assert st["n_blocks"] == 3
    assert st["t_blocks"] == pytest.approx(sums.mean() / se_b)
    assert st["mde_monthly"] == pytest.approx(MS.MDE_Z * se_b / 3)


def test_verdict_rule_cases():
    good = {"mean_monthly": 0.01, "t_blocks": 3.0}
    assert MS.verdict(good, {"worst": 0.005}, {"t_alpha_blocks": 2.5}) == MS.ALPHA
    assert MS.verdict(good, {"worst": 0.005}, {"t_alpha_blocks": 1.0}) == MS.BETA
    assert MS.verdict(good, {"worst": -0.001}, {"t_alpha_blocks": 2.5}) == MS.CANNOT
    assert MS.verdict({"mean_monthly": -0.01, "t_blocks": -1.5}, {}, {}) == MS.FAILED
    assert MS.verdict({"mean_monthly": -0.01, "t_blocks": -0.5}, {}, {}) == MS.CANNOT
    assert MS.verdict({"mean_monthly": None, "t_blocks": None}, {}, {}) == MS.CANNOT


def test_run_book_refuses_zero_costs():
    p = _panel(n_dates=6, n_names=30)
    with pytest.raises(ValueError):
        MS.run_book(p, p["mom"].to_numpy(), k=5, costs={"mega": 0, "large": 0, "mid": 0, "small": 0})


def test_run_book_equal_weight_matches_a_hand_computation_and_gross_scales():
    p = _panel(n_dates=4, n_names=30)
    sc = p["mom"].to_numpy()
    m = MS.run_book(p, sc, k=5, costs=COSTS, hold_months=1)
    d0 = p[p["date"] == p["date"].min()].sort_values("mom", ascending=False).head(5)
    first = m.iloc[0]
    assert first["gross"] == pytest.approx(d0["fwd_ret"].mean())
    assert first["cost"] == pytest.approx(1.0 * COSTS["mid"] / 2 / 1e4)
    half = MS.run_book(p, sc, k=5, costs=COSTS, hold_months=1, gross_fn=lambda idx, w: 0.5)
    assert half.iloc[0]["gross"] == pytest.approx(0.5 * first["gross"])
    assert half.iloc[0]["invested"] == pytest.approx(0.5)


def test_run_book_fwd_override():
    p = _panel(n_dates=3, n_names=30)
    sc = p["mom"].to_numpy()
    m = MS.run_book(p, sc, k=5, costs=COSTS, fwd=np.zeros(len(p)))
    assert (m["gross"] == 0).all()


def test_diff_report_and_seed_report_shapes():
    idx = pd.date_range("2001-01-31", periods=36, freq="ME")
    rng = np.random.default_rng(3)
    a = pd.Series(rng.normal(0.01, 0.04, 36), index=idx)
    b = a - 0.002
    mkt = pd.Series(rng.normal(0.008, 0.04, 36), index=idx)
    r = MS.diff_report(a, b, mkt)
    assert r["log_utility_diff"]["mean_monthly"] > 0
    assert set(r["by_hold_year"]) == {"2001", "2002", "2003", "2004"}
    assert r["verdict"] in MS.VERDICTS
    s = MS.seed_diff_report({0: a, 1: a}, {0: b, 1: b}, mkt)
    assert s["n_seeds"] == 2 and s["seeds_variant_beats_twin_terminal_wealth"] == 2


def test_worst_case_dollars():
    wc = MS.worst_case_dollars(equity=1e6, n_names=20, name_cap=0.1, gross=1.0,
                               sigma_monthly=[0.1] * 20, weights=[0.05] * 20, stop_sigma=2.0)
    assert wc["worst_single_name_to_zero"] == -1e5
    assert wc["worst_all_names_to_zero"] == -1e6
    assert wc["n_x_notional_x_stop"] == pytest.approx(-1e6 * 20 * 0.05 * 2.0 * 0.1)
    assert wc["3_sigma_one_month_loss_per_name_max"] == pytest.approx(-1e6 * 0.05 * 0.3)


def test_per_date_kappa_reads_only_dates_before_the_gap():
    from scripts import sizing_lab as L
    p = _panel(n_dates=12, n_names=40)
    p["x"] = p["vol_63"]
    base = L.per_date_kappa(p, "x", "fwd_ret", np.ones(len(p), bool), gap=2)
    dates = np.sort(p["date"].unique())
    q = p.copy()
    q.loc[q["date"] >= dates[9], "fwd_ret"] = 5.0       # rewrite date 9 onward
    alt = L.per_date_kappa(q, "x", "fwd_ret", np.ones(len(q), bool), gap=2)
    at = (p["date"] <= dates[10]).to_numpy()            # dates <= 10 train on <= 8
    assert np.allclose(base[at], alt[at], equal_nan=True)
    assert not np.allclose(base[(p["date"] == dates[11]).to_numpy()], alt[(p["date"] == dates[11]).to_numpy()])
