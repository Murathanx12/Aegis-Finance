"""Offline tests for the hypothesis-lab night of investable comparisons, vol management,
insider events and restatement vintages. Synthetic data only; no calendar literal: every
date is derived from today."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import hyp_investable as HI
from backend.services import hyp_volmanaged as V

BASE = pd.Timestamp.today().normalize() - pd.DateOffset(years=6)


# ── hyp_investable ───────────────────────────────────────────────────────────

def test_twin_basket_excludes_selection_and_follows_cell_mix():
    cells = pd.Series({"a": "c1", "b": "c1", "c": "c1", "d": "c2", "e": "c2", "f": "c3"})
    ok = pd.Series(True, index=cells.index)
    w = HI.twin_basket(["a", "d"], cells, ok)
    assert "a" not in w and "d" not in w
    assert w["b"] == pytest.approx(0.25) and w["c"] == pytest.approx(0.25)
    assert w["e"] == pytest.approx(0.5)
    assert "f" not in w                                  # c3 is not in the selection's mix
    assert sum(w.values()) == pytest.approx(1.0)


def test_twin_basket_renormalises_when_a_cell_has_no_other_name():
    cells = pd.Series({"a": "c1", "b": "c1", "d": "c2"})
    w = HI.twin_basket(["a", "d"], cells, pd.Series(True, index=cells.index))
    assert w == {"b": pytest.approx(1.0)}


def test_band_index_is_cap_weighted_within_the_selection_band_mix():
    band = pd.Series({"a": "small", "b": "small", "c": "large", "d": "large"})
    mcap = pd.Series({"a": 1.0, "b": 3.0, "c": 10.0, "d": 30.0})
    w = HI.band_index(pd.Series(["small", "large"], index=["a", "c"]), band, mcap, pd.Series(True, index=band.index))
    assert w["b"] == pytest.approx(0.5 * 0.75) and w["d"] == pytest.approx(0.5 * 0.75)


def test_trade_cost_charges_half_spread_on_traded_weight():
    c, to = HI.trade_cost({"a": 0.5, "b": 0.5}, {"a": 0.5, "c": 0.5}, {"b": 0.02, "c": 0.04}, 0.01)
    assert c == pytest.approx(0.5 * 0.02 / 2 + 0.5 * 0.04 / 2)
    assert to == pytest.approx(0.5)


def test_pit_beta_never_reads_the_row_it_is_used_on():
    idx = pd.date_range(BASE, periods=60, freq="ME")
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(0, 0.04, 60), index=idx)
    y = 2.0 * x
    y.iloc[40:] = -5.0 * x.iloc[40:]                     # the regime flips at row 40
    b = HI.pit_beta(y, x, window=36, min_n=24)
    assert np.isnan(b.iloc[23]) and b.iloc[24] == pytest.approx(2.0)
    assert b.iloc[40] == pytest.approx(2.0)              # row 40 itself is not in its own window


def test_spread_stats_keys_on_the_hold_month_and_counts_years():
    idx = pd.date_range(BASE, periods=48, freq="ME")
    s = pd.Series(0.01, index=idx)
    y0 = (idx[0] + pd.offsets.BDay(1)).year
    st = HI.spread_stats(s, f"{y0 + 1}-01-01", f"{y0 + 2}-12-31")
    assert st["n_months"] == 24 and st["years_positive"] == "2 of 2"
    assert st["mean_monthly"] == pytest.approx(0.01)


def test_survives_needs_design_validate_t_and_a_majority_of_years():
    good = {"mean_monthly": 0.01, "t_blocks": 2.5, "years_positive": "5 of 8"}
    assert HI.survives({"mean_monthly": 0.001}, good)[0]
    assert not HI.survives({"mean_monthly": -0.001}, good)[0]
    assert not HI.survives({"mean_monthly": 0.001}, {**good, "years_positive": "4 of 8"})[0]
    assert not HI.survives({"mean_monthly": 0.001}, {**good, "t_blocks": 1.9})[0]


# ── hyp_volmanaged ───────────────────────────────────────────────────────────

def _daily(n=900, seed=1):
    idx = pd.bdate_range(BASE, periods=n)
    rng = np.random.default_rng(seed)
    vol = np.where(np.arange(n) % 200 < 100, 0.005, 0.02)
    return pd.Series(rng.normal(0.0003, vol), index=idx), pd.Series(0.0001, index=idx)


def test_features_are_past_only_and_the_target_is_future_only():
    r, _ = _daily()
    X = V.realised_features(r)
    r2 = r.copy()
    r2.iloc[500:] *= 10                                   # change the future
    assert V.realised_features(r2)["rv22"].iloc[499] == pytest.approx(X["rv22"].iloc[499])
    fv = V.future_var(r, 5)
    assert fv.iloc[10] == pytest.approx(float((r.iloc[11:16] ** 2).mean()))


def test_scale_hits_the_mean_exposure_and_exposures_are_capped():
    sig = pd.Series(np.linspace(0.004, 0.03, 300))
    c = V.scale_for_mean_exposure(sig, 1.0)
    w = V.exposures(sig, c)
    assert w.mean() == pytest.approx(1.0, abs=1e-6) and w.max() <= V.MAX_EXPOSURE


def test_policy_applies_the_decision_from_the_next_session():
    r, rf = _daily(60)
    w_dec = pd.Series(0.0, index=r.index[:1])
    w_dec.loc[r.index[30]] = 1.5
    pol = V.policy_returns(r, rf, w_dec)
    assert pol.loc[r.index[30], "w"] == 0.0 and pol.loc[r.index[31], "w"] == 1.5


def test_constant_exposure_equals_its_benchmark_net_of_costs():
    r, rf = _daily(900)
    w_dec = pd.Series(1.0, index=V.decision_days(r.index, "M"))
    pol = V.policy_returns(r, rf, w_dec)
    cmp_ = V.compare(pol, None, None)
    assert abs(cmp_["diff_log_per_month"]) < 1e-4


# ── insider clusters ─────────────────────────────────────────────────────────

def test_cluster_fires_on_the_third_distinct_insider_and_then_rests():
    from scripts.hyp_insider_events import clusters
    d = [BASE + pd.Timedelta(days=k) for k in (0, 2, 2, 5, 9, 40, 200, 201, 202)]
    B = pd.DataFrame({"permno": 1, "pub": d, "insider_cik": ["x", "x", "y", "y", "z", "w", "p", "q", "r"]})
    E = clusters(B)
    assert list(E["pub"]) == [BASE + pd.Timedelta(days=9), BASE + pd.Timedelta(days=202)]
    assert list(E["n_buyers"]) == [3, 3]


def test_cluster_window_drops_old_buyers():
    from scripts.hyp_insider_events import clusters
    d = [BASE, BASE + pd.Timedelta(days=20), BASE + pd.Timedelta(days=45)]
    E = clusters(pd.DataFrame({"permno": 1, "pub": d, "insider_cik": ["a", "b", "c"]}))
    assert E.empty


# ── restatement vintages ─────────────────────────────────────────────────────

def test_vintages_separate_first_and_latest_and_time_both_at_the_first_filing():
    from scripts.hyp_restatement import asof_join, ratios, vintages
    end = BASE
    f1, f2 = BASE + pd.Timedelta(days=60), BASE + pd.Timedelta(days=420)
    rows = []
    for fact, v1, v2 in (("revenue", 100.0, 90.0), ("cogs", 40.0, 40.0), ("operating_income", 20.0, 10.0)):
        rows += [(7, fact, f1, end, 365.0, v1), (7, fact, f2, end, 365.0, v2)]
    for fact, v in (("assets", 200.0), ("equity", 100.0), ("debt", 50.0), ("cash", 20.0)):
        rows += [(7, fact, f1, end, np.nan, v)]
    F = pd.DataFrame(rows, columns=["cik", "fact", "filed", "end", "period_days", "val"])
    F["end"] = F["end"].dt.strftime("%Y-%m-%d")
    Vv = vintages(F)
    assert len(Vv) == 1 and Vv["first_filed"].iloc[0] == f1
    a, b = ratios(Vv, "first"), ratios(Vv, "latest")
    assert a["ope_be"].iloc[0] == pytest.approx(0.2) and b["ope_be"].iloc[0] == pytest.approx(0.1)
    R = pd.concat([pd.DataFrame({"permno": [7], "usable": [f1 + pd.Timedelta(days=2)]}), a], axis=1)
    keys = pd.DataFrame({"date": [f1, f1 + pd.Timedelta(days=5), f1 + pd.Timedelta(days=600)], "permno": 7})
    j = asof_join(keys, R, ["ope_be"])
    assert np.isnan(j["ope_be"].iloc[0])                  # before usable
    assert j["ope_be"].iloc[1] == pytest.approx(0.2)
    assert np.isnan(j["ope_be"].iloc[2])                  # stale after 460 days
