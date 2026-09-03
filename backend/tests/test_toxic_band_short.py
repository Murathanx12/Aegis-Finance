"""The short-construction mechanics that must never quietly stop being true.

`scripts/toxic_band_short_run.py` turns the toxic_ge_5 exclusion into a SHORT
book, and every way it can be wrong still prints a smooth number: a hedge with
the wrong sign flatters the short in down markets, a borrow fee applied per
month instead of per period overstates a 12-month book's costs twelvefold, a
turnover computed against un-drifted weights hides the cover leg, and a chain
that compounds through -100% resurrects a wiped account. Each is pinned here
on synthetic frames, OFFLINE, in well under a second.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.toxic_band_short_run import (
    borrow_cost_per_period, breakeven_borrow_rate_pct, chain_wealth,
    drifted_short_weights, hedge_return, net_series, short_book,
    short_turnover,
)


def _cohort(months, names_per_month=3, fwd=-0.10, mkt=0.01, beta=1.3):
    """A minimal cohort frame: same names every month, constant returns."""
    rows = []
    for m in months:
        for i in range(names_per_month):
            rows.append({"month": m, "permno": 10000 + i, "fwd": fwd,
                         "mkt_vw": mkt, "beta_pre": beta})
    return pd.DataFrame(rows)


# ------------------------------------------------------------- borrow costs

def test_borrow_cost_scales_with_holding_period_not_per_month():
    """A 12%/yr fee over a 3-month hold is 3%, not 12% and not 36%."""
    assert borrow_cost_per_period(12.0, 3) == pytest.approx(0.03)
    assert borrow_cost_per_period(12.0, 1) == pytest.approx(0.01)
    assert borrow_cost_per_period(0.0, 12) == 0.0


def test_breakeven_borrow_rate_zeroes_the_mean():
    """At the quoted breakeven rate the mean net return is exactly zero --
    the definition, applied rather than asserted."""
    for h in (1, 3, 12):
        mean_not = 0.02  # +2% per h-month period net of trading
        be = breakeven_borrow_rate_pct(mean_not, h)
        assert mean_not - borrow_cost_per_period(be, h) == pytest.approx(0.0, abs=1e-12)


def test_net_series_subtracts_borrow_from_net_of_trading():
    bk = pd.DataFrame({"net_of_trading": [0.05, -0.01]},
                      index=["2020-01", "2020-02"])
    ns = net_series(bk, 24.0, 1)  # 24%/yr over 1 month = 2%
    assert ns.tolist() == pytest.approx([0.03, -0.03])


# ------------------------------------------------------------- short returns

def test_short_gross_is_minus_the_cohort_return_and_hedge_adds_market():
    """A cohort that fell 10% while the market rose 1%: naive short earns
    +10% gross; unit hedge earns +11%; beta hedge earns +10% + beta x 1%."""
    c = _cohort(["2020-01"], fwd=-0.10, mkt=0.01, beta=1.5)
    naive = short_book(c, 1, trade_cost_bps=0.0, hedge=None)
    unit = short_book(c, 1, trade_cost_bps=0.0, hedge="unit", hedge_cost_bps=0.0)
    beta = short_book(c, 1, trade_cost_bps=0.0, hedge="beta", hedge_cost_bps=0.0)
    assert naive["gross"].iloc[0] == pytest.approx(0.10)
    assert unit["gross"].iloc[0] == pytest.approx(0.11)
    assert beta["gross"].iloc[0] == pytest.approx(0.10 + 1.5 * 0.01)
    assert hedge_return(0.01, 0.0) == 0.0


def test_unit_hedged_short_equals_short_toxic_minus_short_market():
    """The identity the receipt states: unit-hedged = paired difference vs the
    short-the-market benchmark. -(fwd) + mkt == (-(fwd)) - (-(mkt))."""
    c = _cohort(["2020-01"], fwd=0.07, mkt=-0.03)
    unit = short_book(c, 1, trade_cost_bps=0.0, hedge="unit", hedge_cost_bps=0.0)
    short_toxic, short_mkt = -0.07, +0.03
    assert unit["gross"].iloc[0] == pytest.approx(short_toxic - short_mkt)


# ---------------------------------------------------- turnover and alignment

def test_drifted_short_weights_move_with_the_short_leg_and_floor_at_zero():
    """A name that fell keeps MORE short weight than one that rallied, and a
    name that more than doubled has consumed its short equity: weight 0."""
    w = pd.Series([0.5, 0.5], index=[1, 2])
    fwd = pd.Series([-0.50, 0.50], index=[1, 2])  # short legs: +50% / -50%
    d = drifted_short_weights(w, fwd)
    assert d[1] == pytest.approx(0.75)
    assert d[2] == pytest.approx(0.25)
    d2 = drifted_short_weights(w, pd.Series([0.0, 1.5], index=[1, 2]))
    assert d2[2] == 0.0 and d2[1] == pytest.approx(1.0)


def test_short_turnover_counts_cover_leg_and_new_short_leg():
    """Full replacement of the book is sum|dw| = 2 (cover 1, short 1)."""
    w_old = pd.Series([1.0], index=[1])
    w_new = pd.Series([1.0], index=[2])
    assert short_turnover(w_new, w_old) == pytest.approx(2.0)
    assert short_turnover(w_old, w_old) == pytest.approx(0.0)


def test_formation_exit_alignment_turnover_compares_cohort_t_minus_h():
    """At horizon h the replaced cohort is the one formed h months ago, so the
    first h formation months have no measured turnover (NaN, filled with the
    median for costing), and an unchanged book at h=1 has ~zero turnover."""
    months = [f"2020-{i:02d}" for i in range(1, 7)]
    c = _cohort(months, fwd=0.0)
    bk1 = short_book(c, 1, trade_cost_bps=10.0)
    bk3 = short_book(c, 3, trade_cost_bps=10.0)
    assert np.isnan(bk1["turnover"].iloc[0]) and bk1["turnover"].iloc[1:].abs().max() < 1e-12
    assert bk3["turnover"].iloc[:3].isna().all()
    assert bk3["turnover"].iloc[3:].abs().max() < 1e-12
    # identical cohorts + zero drift => zero trading cost after the median fill
    assert bk1["trade_cost"].iloc[1:].max() == pytest.approx(0.0)


def test_trade_cost_charged_on_measured_turnover():
    """Half the book replaced each month at 10bps/side: sum|dw| = 1.0 (cover
    0.5 + short 0.5), cost = 1.0 x 10bps = 10bps."""
    rows = []
    for i, m in enumerate(["2020-01", "2020-02"]):
        for p in ([1, 2] if i == 0 else [1, 3]):
            rows.append({"month": m, "permno": p, "fwd": 0.0,
                         "mkt_vw": 0.0, "beta_pre": 1.0})
    bk = short_book(pd.DataFrame(rows), 1, trade_cost_bps=10.0)
    assert bk["turnover"].iloc[1] == pytest.approx(1.0)
    assert bk["trade_cost"].iloc[1] == pytest.approx(10.0 / 10_000.0)


# -------------------------------------------------------------------- ruin

def test_chain_wealth_reports_ruin_and_stays_ruined():
    """A -110% period is a wiped account. It reports RUIN and does not
    compound back to life on the next +50%."""
    w, ruined = chain_wealth(np.array([0.10, -1.10, 0.50]))
    assert ruined is True
    assert w[-1] == 0.0
    w2, r2 = chain_wealth(np.array([0.10, -0.50, 0.50]))
    assert r2 is False and w2[-1] == pytest.approx(1.1 * 0.5 * 1.5)
