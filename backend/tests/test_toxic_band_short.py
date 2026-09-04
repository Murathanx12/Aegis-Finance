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
    """A minimal cohort frame: same names every month, constant returns.

    `resid` is computed the SAME way `band_horizon_run.cohort_frame` computes it
    -- `fwd - beta_pre x mkt_vw`, per name. It is not decoration: since the B1
    re-issue the short book's HEADLINE is `-resid` on Reg-T capital, so a fixture
    without it would be testing a construction the receipt no longer reports.
    """
    rows = []
    for m in months:
        for i in range(names_per_month):
            rows.append({"month": m, "permno": 10000 + i, "fwd": fwd,
                         "mkt_vw": mkt, "beta_pre": beta,
                         "resid": fwd - beta * mkt})
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
                         "mkt_vw": 0.0, "beta_pre": 1.0, "resid": 0.0})
    bk = short_book(pd.DataFrame(rows), 1, trade_cost_bps=10.0)
    assert bk["turnover"].iloc[1] == pytest.approx(1.0)
    assert bk["trade_cost"].iloc[1] == pytest.approx(10.0 / 10_000.0)


# ------------------------------------- the B1 re-issue: -resid on Reg-T capital

def test_minus_resid_is_the_per_name_beta_hedge_not_the_cohort_mean_hedge():
    """`-resid` removes each name's OWN beta leg; `hedged_beta` removes the
    cohort mean's. On a constant-beta cohort they coincide, which is what makes
    the identity checkable at all."""
    c = _cohort(["2020-01"], fwd=-0.10, mkt=0.01, beta=1.5)
    bk = short_book(c, 1, trade_cost_bps=0.0, hedge="beta")
    # resid = -0.10 - 1.5 x 0.01 = -0.115, so -resid = +0.115
    assert bk["minus_resid"].iloc[0] == pytest.approx(0.115)
    # and it equals the cohort-mean beta hedge here, by construction
    assert bk["gross"].iloc[0] == pytest.approx(0.115)
    # the leverage-only leg is quoted separately and is NOT part of -resid
    assert bk["beta_matched_leg"].iloc[0] == pytest.approx(1.5 * 0.01)


def test_the_short_is_divided_by_regt_capital_not_by_one_dollar():
    """The void receipt's denominator was $1 of short notional. Reg-T wants
    0.5 x short + 0.5 x long, so a beta-1.5 hedge needs 1.25 of equity and the
    reported return is 0.8x the per-notional one."""
    c = _cohort(["2020-01"], fwd=-0.10, mkt=0.01, beta=1.5)
    bk = short_book(c, 1, trade_cost_bps=0.0, hedge="beta")
    assert bk["regt_capital"].iloc[0] == pytest.approx(1.25)
    assert bk["maint_capital"].iloc[0] == pytest.approx(0.30 + 0.25 * 1.5)
    per_notional = bk["minus_resid_net_of_trading"].iloc[0]
    assert bk["minus_resid_net_on_regt"].iloc[0] == pytest.approx(per_notional / 1.25)
    # the capital-normalised number is SMALLER whenever the hedge is levered
    assert abs(bk["minus_resid_net_on_regt"].iloc[0]) < abs(per_notional)
    # maintenance margin is a leverage BOUND, so it flatters -- and must never be
    # the headline
    assert abs(bk["minus_resid_net_on_maint"].iloc[0]) > abs(per_notional)


# -------------------------------------------------------------------- ruin

def test_chain_wealth_reports_ruin_and_stays_ruined():
    """A -110% period is a wiped account. It reports RUIN and does not
    compound back to life on the next +50%."""
    w, ruined = chain_wealth(np.array([0.10, -1.10, 0.50]))
    assert ruined is True
    assert w[-1] == 0.0
    w2, r2 = chain_wealth(np.array([0.10, -0.50, 0.50]))
    assert r2 is False and w2[-1] == pytest.approx(1.1 * 0.5 * 1.5)
