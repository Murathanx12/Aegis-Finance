"""The simulator's accounting — costs, dividends, delisting, fills, refusals.

Every test here is about a way a backtest can be quietly generous. The
arithmetic that produces a NAV is easy; the arithmetic that produces an
HONEST NAV is a list of small refusals to help yourself, and each of them is
below with the free lunch it declines.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.portfolio_farm import replay
from backend.services.portfolio_farm.panel import Panel, PanelUnavailable, load_panel
from backend.services.portfolio_farm.policy import Policy
from backend.tests.test_portfolio_farm_pit import synthetic

T = 420


def _pol(**kw) -> Policy:
    return Policy(**{"top_k": 5, "universe_n": 20, "holding_days": 21, **kw})


def _flat_panel(n_names: int = 8, ret: float = 0.0) -> Panel:
    """Every name returns exactly `ret` every session. Any NAV movement is
    therefore accounting, not markets — which is what makes cost and dividend
    arithmetic legible."""
    r = np.full((T, n_names), ret)
    tri = np.cumprod(1.0 + r, axis=0)
    close = 100.0 * tri
    return Panel(
        dates=np.array([f"d{i:04d}" for i in range(T)], dtype=object),
        permnos=np.arange(1, n_names + 1, dtype=np.int64),
        close=close.astype(np.float32), open_=close.astype(np.float32),
        ret=r.astype(np.float32), retx=r.astype(np.float32),
        traded=np.ones((T, n_names), dtype=bool),
        dolvol=np.full((T, n_names), 1e8, dtype=np.float32),
        mktcap=np.full((T, n_names), 1e10, dtype=np.float32),
        tri=tri.astype(np.float32), source="flat")


# ── costs are charged, and the amount is checkable by hand ──────────────────


def test_a_flat_market_LOSES_exactly_the_costs():
    """Nothing moves, so the only thing that can change NAV is friction. The
    first rebalance buys 100% of the book at 6 bps one way."""
    p = _flat_panel()
    res = replay.run(p, _pol(signal="equal", holding_days=1000), warmup=260)
    start = 10_000.0
    assert res.diagnostics["n_fills"] == 1
    expected_cost = start * 6 / 10_000.0
    assert res.diagnostics["total_cost_usd"] == pytest.approx(expected_cost,
                                                             rel=1e-6)
    assert res.metrics["terminal_usd"] == pytest.approx(start - expected_cost,
                                                        rel=1e-6)


def test_the_frictionless_twin_loses_NOTHING():
    p = _flat_panel()
    res = replay.run(p, _pol(signal="equal", holding_days=1000,
                             transaction_cost_bps=0.0, slippage_bps=0.0,
                             zero_cost_diagnostic=True), warmup=260)
    assert res.diagnostics["total_cost_usd"] == 0.0
    assert res.metrics["terminal_usd"] == pytest.approx(10_000.0, rel=1e-9)


def test_trading_FASTER_costs_strictly_more():
    """The Micron question's mechanical half. Same signal, same names, same
    market: the only difference is how often the book pays the spread."""
    p = synthetic()
    slow = replay.run(p, _pol(signal="mom_12_1", holding_days=63), warmup=260)
    fast = replay.run(p, _pol(signal="mom_12_1", holding_days=1), warmup=260)
    assert fast.diagnostics["total_cost_usd"] > slow.diagnostics["total_cost_usd"]
    assert fast.diagnostics["n_decisions"] > slow.diagnostics["n_decisions"]


# ── dividends are cash, not free reinvestment ───────────────────────────────


def test_dividends_arrive_as_CASH_and_are_counted_once():
    """`ret` includes the dividend and `retx` does not; the difference is cash
    the holder received. Marking positions on `ret` AND crediting the cash
    would count it twice — the classic double-count that adds a silent few
    percent a year."""
    p = _flat_panel(ret=0.0)
    # 1% dividend every session: total return 1%, price return 0%.
    ret = np.full(p.ret.shape, 0.01, dtype=np.float32)
    p = Panel(**{**p.__dict__, "ret": ret})
    res = replay.run(p, _pol(signal="equal", holding_days=1000), warmup=260)
    n_days = T - 260
    # Price never moves, so the whole gain is dividend cash on a ~$10k book.
    gain = res.metrics["terminal_usd"] - 10_000.0
    assert 0 < gain < 10_000.0 * 0.01 * n_days * 1.05, (
        "dividend cash is either missing or being counted more than once")


# ── delisting is an explicit assumption ─────────────────────────────────────


def test_a_vanished_holding_is_resolved_at_the_DECLARED_delisting_return():
    p = _flat_panel(n_names=4)
    close = p.close.copy()
    close[300:, :] = np.nan                     # the whole universe disappears
    p = Panel(**{**p.__dict__, "close": close,
                 "traded": np.isfinite(close)})
    harsh = replay.run(p, _pol(signal="equal", holding_days=1000,
                               delisting_return=-1.0), warmup=260)
    mild = replay.run(p, _pol(signal="equal", holding_days=1000,
                              delisting_return=0.0), warmup=260)
    assert harsh.diagnostics["n_delistings"] > 0
    assert harsh.metrics["terminal_usd"] < mild.metrics["terminal_usd"], (
        "the delisting assumption changes nothing — it is not being applied, "
        "and the run is silently the optimistic one")


def test_a_SHORT_gap_is_not_treated_as_a_delisting():
    """A name missing for two sessions is a data gap. Liquidating it would
    churn the book on holidays and half-days and charge costs for nothing."""
    p = _flat_panel(n_names=4)
    close = p.close.copy()
    close[300:302, :] = np.nan
    p = Panel(**{**p.__dict__, "close": close, "traded": np.isfinite(close)})
    res = replay.run(p, _pol(signal="equal", holding_days=1000), warmup=260)
    assert res.diagnostics["n_delistings"] == 0


# ── the panel's own refusal ─────────────────────────────────────────────────


def test_load_panel_REFUSES_a_missing_year_rather_than_shortening(tmp_path):
    """A window that silently shrinks reports a CAGR over a period nobody
    declared, under the heading of the period that was asked for."""
    with pytest.raises(PanelUnavailable) as exc:
        load_panel(1800, 1802, dir_=tmp_path)
    assert "1800" in str(exc.value)


def test_replay_refuses_a_panel_shorter_than_its_warmup():
    p = _flat_panel()
    with pytest.raises(ValueError):
        replay.run(p, _pol(signal="equal"), warmup=T + 10)


# ── weights ─────────────────────────────────────────────────────────────────


def test_the_single_name_cap_is_respected_when_it_CAN_be():
    """8 names under a 20% cap is feasible: water-filling holds the cap and
    stays fully invested."""
    w = replay._cap_weights(np.array([0.9, 0.05, 0.05, 0.05, 0.05,
                                      0.05, 0.05, 0.05]), 0.2)
    assert w.max() <= 0.2 + 1e-9
    assert w.sum() == pytest.approx(1.0)


def test_an_INFEASIBLE_cap_leaves_cash_instead_of_quietly_exceeding_itself():
    """THE REGRESSION. 3 names cannot fit under a 20% cap. The old
    cap-then-renormalise loop returned 33% each — every weight over the cap the
    receipt claimed to enforce, with nothing raised. The book must instead be
    60% invested and 40% cash."""
    w = replay._cap_weights(np.ones(3) / 3.0, 0.2)
    assert w.max() <= 0.2 + 1e-9
    assert w.sum() == pytest.approx(0.6)


def test_water_filling_does_not_push_a_SECOND_name_over_the_cap():
    """Redistributing one name's excess can lift another past the cap, which is
    why capping is iterative and not a single `minimum`."""
    w = replay._cap_weights(np.array([0.60, 0.28, 0.06, 0.03, 0.02, 0.01]), 0.25)
    assert w.max() <= 0.25 + 1e-9
    assert w.sum() == pytest.approx(1.0)


def test_an_infeasible_cap_actually_reduces_the_books_exposure_end_to_end():
    """Not just the helper: a 3-name book under a 20% cap must end holding
    cash, so a flat market leaves it with more than a fully invested twin
    after costs."""
    p = _flat_panel(n_names=8)
    tight = replay.run(p, _pol(signal="equal", top_k=3, max_single_name=0.2,
                               holding_days=1000), warmup=260)
    full = replay.run(p, _pol(signal="equal", top_k=3, max_single_name=1.0,
                              holding_days=1000), warmup=260)
    assert tight.diagnostics["traded_notional_usd"] == pytest.approx(
        0.6 * full.diagnostics["traded_notional_usd"], rel=1e-6)
