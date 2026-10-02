"""Offline tests for the round-2 library run and the conditional-cell engine (2026-09-30)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import bridges_on_crsp_run as BR
from scripts import conditionals_on_crsp as C

T = pd.Timestamp


def test_missing_inputs_are_parsed_without_evaluating_code():
    why = "inputs absent in the CRSP era: ['dtc', 'net_raises']"
    assert BR._missing_from_why(why) == ["dtc", "net_raises"]
    assert BR._missing_from_why("") == ["?"]


def _stats(tw_d, tw_v, mk_d, mk_v, t, dsr):
    w = lambda m, tt=None: {"mean_monthly": m, "t_blocks": tt}          # noqa: E731
    return {"vs_twin": {"design": w(tw_d), "validate": w(tw_v), "design_validate": w(0.3, t)},
            "vs_market": {"design": w(mk_d), "validate": w(mk_v)}, "dsr": dsr}


def test_library_verdict_needs_every_leg():
    assert BR.verdict(_stats(0.1, 0.1, 0.1, 0.1, 2.5, 0.97), True)[0] == "SURVIVES"
    v, fails = BR.verdict(_stats(0.1, 0.1, 0.1, -0.1, 2.5, 0.97), True)
    assert v == "CANNOT_DISTINGUISH" and fails == ["rule-market <= 0 in validate"]
    assert BR.verdict(_stats(0.1, 0.1, 0.1, 0.1, 2.5, 0.5), True)[0] == "CANNOT_DISTINGUISH"
    assert BR.verdict(_stats(0.1, 0.1, 0.1, 0.1, 2.5, 0.97), False)[0] == "NOT_DECIDABLE"


def test_every_new_source_has_a_declared_start():
    assert set(BR.SOURCE_COLS) <= set(BR.NEW_SOURCE_START)
    assert "eightk" in BR.DESCRIPTION_ONLY


def test_trade_cost_charges_half_spread_on_traded_weight():
    c, to = C.trade_cost({"A": 0.5, "B": 0.5}, {"A": 0.5, "C": 0.5}, {"A": 0.01, "B": 0.02, "C": 0.04}, 0.0035)
    assert c == pytest.approx(0.5 * 0.02 / 2 + 0.5 * 0.04 / 2)
    assert to == pytest.approx(0.5)


def _panel(n_dates=3, n=12, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2010-01-31", periods=n_dates, freq="ME")
    rows = []
    for d in dates:
        for i in range(n):
            rows.append({"date": d, "symbol": f"{i:06d}", "eligible": True, "fwd_ret": 0.01 * (i % 3),
                         "median_dollar_vol": 5e7, "vol_63": 0.02 + 0.001 * (i % 4),
                         "mom_252_21": 0.1 * (i % 5)})
    P = pd.DataFrame(rows)
    P["_cell"] = C.add_cells(P)
    return P, dates


def test_twin_uses_only_non_selected_names_of_the_same_cells():
    P, dates = _panel()
    g = P[P["date"] == dates[0]].copy()
    g["_cell"] = "x"                                  # one cell: twin = mean of the non-selected
    sel = pd.Index(["000000", "000003"])              # fwd 0.00 and 0.00
    rest = g[~g["symbol"].isin(sel)]["fwd_ret"].mean()
    assert C.twin_gross(sel, g) == pytest.approx(rest)


def test_small_selection_holds_the_market_and_gate_off_holds_the_market():
    P, dates = _panel()
    mkt = pd.Series(0.005, index=dates)
    spreads = pd.Series(0.001, index=P.index)
    few = P["symbol"].isin(["000001", "000002"])      # 2 names < MIN_NAMES
    s = C.run_cell(P, few, mkt, spreads)
    assert (~s["invested"]).all() and (s["net"] == 0.005).all()
    many = P["symbol"].astype(int) < 8
    gate = pd.Series([True, False, True], index=dates)
    s2 = C.run_cell(P, many, mkt, spreads, active=gate)
    assert list(s2["invested"]) == [True, False, True]
    assert s2["cost"].iloc[1] > 0                     # leaving the book to the market is a trade
    assert s2["net"].iloc[0] == pytest.approx(s2["gross"].iloc[0] - s2["cost"].iloc[0])


def test_cell_verdict_rule():
    idx = pd.date_range("1999-01-29", "2016-12-30", freq="BME")
    rng = np.random.default_rng(3)
    s = pd.DataFrame({"gross": 0.012 + rng.normal(0, 0.002, len(idx)), "cost": 0.001,
                      "twin_gross": 0.008, "market": 0.005, "n": 20, "turnover": 0.3, "invested": True}, index=idx)
    s["net"] = s["gross"] - s["cost"]
    r = C.cell_verdict(s, "1999-01-29")
    assert r["verdict"] == "CANDIDATE" and r["validate_years_positive"] == 8
    s2 = s.assign(net=s["market"] - 0.001)
    assert C.cell_verdict(s2, "1999-01-29")["verdict"] == "FAILED_VARIANT"


def test_declared_cells_are_at_most_twelve_and_each_has_a_start():
    assert 1 <= len(C.CELLS) <= 12
    for c in C.CELLS.values():
        assert pd.Timestamp(c["when"]) >= T("1991-01-01") and c["condition"] and c["question"]
