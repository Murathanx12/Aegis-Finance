"""Offline tests for scripts/library_on_crsp.py (the library re-read on CRSP).

Synthetic series only: no CRSP file, no network, no panel parquet is read.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import library_on_crsp as L


def _monthly(values, start="1991-01-31"):
    idx = pd.date_range(start, periods=len(values), freq="BME")
    return pd.Series(values, index=idx, dtype=float)


def test_coverable_names_missing_columns():
    ok, miss = L.coverable(("mom_252_21", "gp_at"), ["mom_252_21", "vol_63"])
    assert not ok and miss == ["gp_at"]
    assert L.coverable((), ["x"]) == (True, [])


def test_headline_order():
    base = {"mean_monthly": 0.004, "t_blocks": 2.5}
    assert L.headline({"mean_monthly": -0.001, "t_blocks": 3.0}, None, {}, None) == "FAILED_VARIANT"
    assert L.headline({"mean_monthly": 0.0}, None, {}, None) == "FAILED_VARIANT"
    assert L.headline(base, "CALENDAR_ARTEFACT", {"mean_monthly": 0.01}, None) == "CALENDAR_ARTEFACT"
    assert L.headline(base, "ROBUST_TO_CALENDAR", {"mean_monthly": 0.01}, "CANNOT_DISTINGUISH") == "ALPHA_DETECTED"
    assert L.headline(base, None, {"mean_monthly": 0.01}, "BETA_EXPLAINS") == "BETA_EXPLAINS"
    # t >= 2 but the honest holdout is negative: not ALPHA_DETECTED
    assert L.headline(base, None, {"mean_monthly": -0.001}, None) == "CANNOT_DISTINGUISH"
    assert L.headline({"mean_monthly": 0.002, "t_blocks": 1.1}, None, {"mean_monthly": 0.01}, None) \
        == "CANNOT_DISTINGUISH"
    assert L.headline({"mean_monthly": None}, None, {}, None) == "NOT_COMPUTED"


def test_top_share_flags_concentration():
    s = _monthly([0.0] * 99 + [1.0])
    assert L.top_share(s) == 1.0
    even = _monthly([0.01] * 100)
    assert abs(L.top_share(even) - 0.05) < 1e-9
    assert L.top_share(_monthly([-0.01] * 10)) is None      # non-positive total


def test_year_signs_keyed_on_hold_month():
    # decision 1991-12-31 holds January 1992
    s = pd.Series([0.05, -0.01], index=pd.to_datetime(["1991-12-31", "1992-06-30"]))
    ys = L.year_signs(s)
    assert ys["n_years"] == 1 and ys["n_positive"] == 1


def test_loo_worst_mean_drops_best_year():
    s = pd.concat([_monthly([0.10] * 12, "1991-01-31"), _monthly([0.0] * 12, "1992-01-31")])
    # dropping the good hold year leaves ~0; the hold-year split moves one month across the boundary
    assert L.loo_worst_mean(s) < 0.01


def test_is_candidate_filter():
    good = {"holdout": {"mean_monthly": 0.002}, "libwin": {"mean_monthly": 0.001},
            "years": {"share_positive": 0.6}, "top5pct_share": 0.4, "loo_worst": {"worst": 0.001}}
    assert L.is_candidate(good) == (True, [])
    bad = dict(good, libwin={"mean_monthly": -0.001}, top5pct_share=0.9)
    ok, why = L.is_candidate(bad)
    assert not ok and "libwin_2017_2024<=0" in why and "carried_by_top_months" in why
    ok, why = L.is_candidate(dict(good, years={"share_positive": 0.5}))
    assert not ok and why == ["positive_years<=half"]


def test_distinct_bets_single_linkage():
    rng = np.random.default_rng(7)
    a = rng.normal(size=300)
    b = a + 0.1 * rng.normal(size=300)
    c = rng.normal(size=300)
    corr = pd.DataFrame({"a": a, "b": b, "c": c}).corr()
    assert L.n_distinct_bets(corr, 0.5) == 2
    assert L.n_distinct_bets(corr, 0.999) == 3


def test_combos_average_and_count():
    s = {n: _monthly(np.full(30, v)) for n, v in (("x", 0.01), ("y", 0.03), ("z", -0.01))}
    out = L.combos(s, ["x", "y", "z"], max_size=3)
    assert set(out) == {"x+y", "x+z", "y+z", "x+y+z"}
    assert abs(out["x+y"].mean() - 0.02) < 1e-12
    assert L.combos({"x": _monthly([0.01] * 10), "y": _monthly([0.0] * 10)}, ["x", "y"]) == {}


def test_vendor_side_reads_the_matching_cell():
    idx = pd.date_range("2017-01-31", periods=36, freq="BME")
    cols = pd.MultiIndex.from_tuples([("rule_minus_twin21", "foo@k20"), ("rule_minus_twin0", "foo@k20")])
    vm = pd.DataFrame(np.column_stack([np.full(36, 0.01), np.full(36, 9.0)]), index=idx, columns=cols)
    v = L.vendor_side(vm, "foo", 20)
    assert v["cell"] == "foo@k20"
    assert abs(v["full_2017_2026"]["mean_monthly"] - 0.01) < 1e-12
    assert "NOT_COMPUTED" in L.vendor_side(vm, "bar", 20)["status"]
    assert "NOT_COMPUTED" in L.vendor_side(None, "foo", 20)["status"]


def test_sector_pit_attach():
    P = pd.DataFrame({"date": pd.to_datetime(["2000-01-31"] * 3), "symbol": ["1", "2", "3"],
                      "eligible": [True, True, True], "gsector": ["10", "10", None],
                      "mom_252_21": [0.2, 0.4, 0.9], "mom_21": [0.01, 0.03, 0.0]})
    out = L.attach_sector_pit(P).set_index("symbol")
    assert abs(out.loc["1", "sector_mom"] - 0.3) < 1e-12
    assert abs(out.loc["2", "mom_minus_sector"] - 0.1) < 1e-12
    assert pd.isna(out.loc["3", "sector_mom"])


def test_trimmed_mean_is_symmetric_and_noise_neutral():
    s = _monthly([0.0] * 95 + [1.0] * 5)          # carried entirely by 5% of months
    assert L.trimmed_mean(s) == 0.0
    s2 = _monthly(list(np.linspace(-0.05, 0.07, 100)))   # a real shift survives trimming
    assert L.trimmed_mean(s2) > 0
    assert L.trimmed_mean(_monthly([0.01] * 10)) is None


def test_amended_candidate_rule_uses_the_trim_when_present():
    row = {"holdout": {"mean_monthly": 0.002}, "libwin": {"mean_monthly": 0.001},
           "years": {"share_positive": 0.6}, "top5pct_share": 1.2, "loo_worst": {"worst": 0.001},
           "trimmed5_mean": 0.001}
    assert L.is_candidate(row) == (True, [])       # a top-5% share > 1 alone no longer vetoes
    ok, why = L.is_candidate(dict(row, trimmed5_mean=-0.0001))
    assert not ok and why == ["carried_by_extreme_months"]
