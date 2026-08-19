"""Known-answer worlds for the LANE-FACTORY-SIM-1 book engine.

A simulator that has not recovered planted truth is a random-number
generator with a progress bar. Each test plants a world whose right
answer is computable by hand.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services.lane_factory_sim import (Panel, SimRefused, run_book)


def _panel(px: pd.DataFrame, *, dlret: dict | None = None) -> Panel:
    ret = px.pct_change()
    elig = {per: set(px.columns) for per in
            px.index.to_period("M").unique()}
    last = pd.Series({p: px[p].dropna().index.max() for p in px.columns})
    return Panel(px=px, ret=ret, elig_by_month=elig,
                 dlret=pd.Series(dlret or {}, dtype=float), last_day=last)


def _dates(n=800):
    return pd.bdate_range("2013-01-02", periods=n)


def test_flat_world_loses_only_costs():
    d = _dates()
    px = pd.DataFrame({p: 100.0 for p in range(10)}, index=d)
    out = run_book(_panel(px), weighting="equal", winner_handling="trim",
                   start=str(d[300].date()), end=str(d[-1].date()),
                   top_n=5)
    # flat prices: no signal spread, but the book still buys once; NAV can
    # only fall by costs, never rise
    assert out["total_return"] <= 0
    assert out["total_return"] > -0.01
    assert out["max_drawdown"] > -0.01


def test_single_riser_is_captured():
    d = _dates()
    base = {p: 100.0 * np.ones(len(d)) for p in range(9)}
    base[9] = 100.0 * (1.003 ** np.arange(len(d)))      # steady riser
    px = pd.DataFrame(base, index=d)
    out = run_book(_panel(px), weighting="equal", winner_handling="trim",
                   start=str(d[300].date()), end=str(d[-1].date()),
                   top_n=3)
    assert out["total_return"] > 0.2      # the riser dominates a top-3 book


def test_delisting_to_near_zero_is_charged_not_ignored():
    d = _dates()
    base = {p: 100.0 * np.ones(len(d)) for p in range(9)}
    rise = 100.0 * (1.004 ** np.arange(len(d)))
    rise[500:] = np.nan                                 # dies mid-book
    base[9] = rise
    px = pd.DataFrame(base, index=d)
    out = run_book(_panel(px, dlret={9: -0.95}), weighting="equal",
                   winner_handling="trim",
                   start=str(d[300].date()), end=str(d[-1].date()),
                   top_n=3)
    assert out["n_delist_exits"] == 1
    # the -95% delisting return must hit the book: it held the riser
    assert out["max_drawdown"] < -0.10


def test_exempt_holds_the_winner_through_rebalance():
    d = _dates()
    base = {p: 100.0 * np.ones(len(d)) for p in range(9)}
    base[9] = 100.0 * (1.006 ** np.arange(len(d)))      # fast winner
    px = pd.DataFrame(base, index=d)
    pn = _panel(px)
    trim = run_book(pn, weighting="equal", winner_handling="trim",
                    start=str(d[300].date()), end=str(d[-1].date()),
                    top_n=3)
    exempt = run_book(pn, weighting="equal", winner_handling="exempt",
                      start=str(d[300].date()), end=str(d[-1].date()),
                      top_n=3)
    assert exempt["n_winner_exemptions"] >= 1
    # in a world where the winner only rises, refusing to trim it must win
    assert exempt["total_return"] > trim["total_return"]
    # NOTE deliberately NOT asserted: exempt turnover < trim turnover.
    # First write of this test assumed it; the engine showed the opposite
    # and the engine is right — deferred trims are bigger when they land
    # (the winner has grown for 60 more days), so total traded value can
    # EXCEED frequent small trims in a monotonic-riser world. v1
    # semantics: the +40% reference is the ORIGINAL entry, so a
    # persistent winner re-exempts after each catch-up trim — renewable
    # exemption, documented for the G2 prereg to accept or amend.


def test_unknown_rule_refuses():
    d = _dates(300)
    px = pd.DataFrame({0: 100.0}, index=d)
    with pytest.raises(SimRefused):
        run_book(_panel(px), weighting="market_cap",
                 winner_handling="trim")
    with pytest.raises(SimRefused):
        run_book(_panel(px), weighting="equal", winner_handling="yolo")


def test_output_is_labeled_simulation():
    d = _dates(400)
    px = pd.DataFrame({p: 100.0 for p in range(6)}, index=d)
    out = run_book(_panel(px), weighting="equal", winner_handling="trim",
                   start=str(d[300].date()), end=str(d[-1].date()),
                   top_n=3)
    assert "SIMULATION" in out["label"]
