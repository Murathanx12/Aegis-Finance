"""S7 -- protections as data, against the live bounds and PLANTED breaches.

The known answers here are the fleet's own live numbers: five profiles whose
worst case is gross x stop, and the 2026-08-28 incident (12 names x 25% = 300%
gross, 3% stop = -9%; the "fix" that widened the stop to 8% = -24%).
"""

from __future__ import annotations

import pytest

from backend.strategy.protections import (CANNOT_DETERMINE, BookState,
                                          CooldownPeriod, DailyLossLimit,
                                          GrossExposureCap, MaxDrawdownGuard,
                                          PROFILES, ProtectionError,
                                          ProtectionStack, StoplossGuard,
                                          WorstCaseStopBudget,
                                          default_protections, profile_bounds)


# --------------------------------------------------------------------------
# the live profile table -- five KNOWN ANSWERS


@pytest.mark.parametrize("name,expected", [
    ("conservative", 0.0180),
    ("aggressive", 0.1000),
    ("maximum", 0.0900),
    ("basket", 0.1200),
    ("convex", 0.0800),
])
def test_each_profile_worst_case_is_gross_times_stop(name: str, expected: float):
    """Today's live bounds, DERIVED from gross x stop rather than typed in."""
    p = PROFILES[name]
    assert p.worst_case_pct == pytest.approx(expected, abs=1e-9)


def test_NO_PROFILE_IS_LEVERED():
    for name, p in PROFILES.items():
        assert p.gross_cap <= 1.0, f"{name} is levered at {p.gross_cap}"
        assert p.as_dict()["levered"] is False


def test_the_profile_table_names_its_source_repository():
    for row in profile_bounds().values():
        assert "aegis-alpha-terminal" in row["source"]


def test_a_levered_gross_cap_is_REFUSED_at_construction():
    with pytest.raises(ProtectionError, match="LEVERED"):
        GrossExposureCap(gross_cap=1.5)


# --------------------------------------------------------------------------
# the 2026-08-28 incident, reproduced as a known answer


def _state(n: int, notional_pct: float, stop: float, equity: float = 100_000.0,
           **kw) -> BookState:
    book = {f"N{i}": notional_pct * equity for i in range(n)}
    return BookState(equity_usd=equity, notional_by_name=book, stop_pct=stop, **kw)


def test_twelve_names_at_25pct_is_300pct_gross_and_a_3pct_stop_costs_9pct():
    """THE INCIDENT. 12 x 25% = 3.00x gross; 3.00 x 3% = 9.00% of equity."""
    g = WorstCaseStopBudget(budget_pct_of_equity=0.10).evaluate(
        _state(12, 0.25, 0.03))
    assert g.measured["gross_over_equity"] == pytest.approx(3.0)
    assert g.measured["worst_case_pct_of_equity"] == pytest.approx(0.09)
    assert g.measured["worst_case_usd"] == pytest.approx(-9_000.0)


def test_the_FIX_that_widened_the_stop_made_the_worst_case_WORSE():
    """8% on the same uncapped gross is -24%, not a risk reduction."""
    g = WorstCaseStopBudget(budget_pct_of_equity=0.10).evaluate(
        _state(12, 0.25, 0.08))
    assert g.measured["worst_case_pct_of_equity"] == pytest.approx(0.24)
    assert g.locked is True
    assert "24.00% of equity" in g.reason


def test_the_gross_cap_would_have_caught_it_first():
    r = GrossExposureCap(gross_cap=1.0).evaluate(_state(12, 0.25, 0.03))
    assert r.locked is True
    assert "ENTRIES LOCKED" in r.reason
    assert r.measured["gross_over_equity"] == pytest.approx(3.0)


def test_a_book_inside_both_bounds_is_admitted():
    r = GrossExposureCap(gross_cap=1.0).evaluate(_state(8, 0.10, 0.03))
    assert r.locked is False
    b = WorstCaseStopBudget(budget_pct_of_equity=0.10).evaluate(
        _state(8, 0.10, 0.03))
    assert b.locked is False
    assert b.measured["worst_case_pct_of_equity"] == pytest.approx(0.024)


# --------------------------------------------------------------------------
# AN UNMEASURABLE INPUT REFUSES -- it never assumes flat


@pytest.mark.parametrize("guard,state", [
    (GrossExposureCap(), BookState()),
    (GrossExposureCap(), BookState(equity_usd=1e5)),
    (WorstCaseStopBudget(), BookState(equity_usd=1e5, notional_by_name={})),
    (DailyLossLimit(), BookState(equity_usd=1e5)),
    (CooldownPeriod(), BookState()),
    (MaxDrawdownGuard(), BookState(equity_usd=1e5)),
])
def test_an_unmeasurable_input_LOCKS_with_CANNOT_DETERMINE(guard, state):
    r = guard.evaluate(state)
    assert r.locked is True
    assert r.determinable is False
    assert CANNOT_DETERMINE in r.reason
    assert "turns the guard off" in r.reason


def test_zero_equity_refuses_rather_than_dividing():
    r = GrossExposureCap().evaluate(
        BookState(equity_usd=0.0, notional_by_name={"A": 1.0}))
    assert r.determinable is False


# --------------------------------------------------------------------------
# the other guards


def test_the_daily_loss_limit_locks_after_the_day_has_cost_its_budget():
    s = BookState(equity_usd=100_000.0, realised_pnl_today_usd=-4_000.0)
    assert DailyLossLimit(limit_pct=0.03).evaluate(s).locked is True
    assert DailyLossLimit(limit_pct=0.05).evaluate(s).locked is False


def test_a_profitable_day_never_locks():
    s = BookState(equity_usd=100_000.0, realised_pnl_today_usd=+4_000.0)
    assert DailyLossLimit(limit_pct=0.03).evaluate(s).locked is False


def test_the_cooldown_blocks_only_the_names_inside_it():
    s = BookState(periods_since_last_exit_by_name={"A": 0, "B": 3, "C": 1})
    r = CooldownPeriod(periods=2).evaluate(s)
    assert r.scope == "name"
    assert r.names == ("A", "C")
    assert r.locked is True


def test_the_stoploss_guard_counts_only_TYPED_stops_and_reports_untyped():
    exits = ([{"exit_reason": "STOP", "periods_ago": 1}] * 3
             + [{"exit_reason": "DEADLINE", "periods_ago": 1}] * 5
             + [{"periods_ago": 1}] * 2)
    r = StoplossGuard(trade_limit=4, lookback_periods=5).evaluate(
        BookState(recent_exits=exits))
    assert r.measured["n_stops"] == 3
    assert r.measured["n_untyped"] == 2
    assert r.locked is False                       # 3 < 4, untyped not counted
    assert "never as stops" in r.reason


def test_the_stoploss_guard_locks_at_the_limit():
    exits = [{"exit_reason": "STOP", "periods_ago": 1}] * 4
    r = StoplossGuard(trade_limit=4).evaluate(BookState(recent_exits=exits))
    assert r.locked is True


def test_exits_outside_the_lookback_window_do_not_count():
    exits = [{"exit_reason": "STOP", "periods_ago": 99}] * 9
    assert StoplossGuard(trade_limit=4, lookback_periods=5).evaluate(
        BookState(recent_exits=exits)).locked is False


def test_the_drawdown_guard_locks_below_the_peak():
    s = BookState(equity_usd=80_000.0, peak_equity_usd=100_000.0)
    assert MaxDrawdownGuard(limit_pct=0.15).evaluate(s).locked is True
    assert MaxDrawdownGuard(limit_pct=0.25).evaluate(s).locked is False


# --------------------------------------------------------------------------
# the stack: never empty by default, entries only


def test_an_empty_protection_list_is_REFUSED():
    with pytest.raises(ProtectionError, match="never"):
        ProtectionStack()


def test_an_unprotected_book_must_state_a_REASON_in_words():
    with pytest.raises(ProtectionError, match="must carry a REASON"):
        ProtectionStack(deliberately_unprotected="  ")
    stack = ProtectionStack(deliberately_unprotected="zero-cost diagnostic only")
    out = stack.evaluate(BookState())
    assert out["deliberately_unprotected"] == "zero-cost diagnostic only"
    assert out["n_protections"] == 0


def test_the_default_stack_is_never_empty_for_any_declared_profile():
    for name in PROFILES:
        guards = default_protections(name)
        assert len(guards) >= 5
        assert ProtectionStack(guards, profile=name).evaluate(
            BookState())["n_protections"] == len(guards)


def test_an_undeclared_profile_REFUSES_rather_than_defaulting():
    with pytest.raises(ProtectionError, match="unknown profile"):
        default_protections("yolo")


def test_the_default_stack_derives_its_bounds_from_the_profile():
    guards = {g.name: g for g in default_protections("conservative")}
    assert guards["gross_exposure_cap"].gross_cap == 0.60
    assert guards["worst_case_stop_budget"].budget_pct_of_equity == pytest.approx(0.018)


def test_the_stack_locks_entries_and_says_which_guard_did_it():
    stack = ProtectionStack(default_protections("aggressive"), profile="aggressive")
    out = stack.evaluate(_state(12, 0.25, 0.08, peak_equity_usd=100_000.0,
                                realised_pnl_today_usd=0.0,
                                periods_since_last_exit_by_name={}))
    assert out["entries_allowed"] is False
    assert "gross_exposure_cap" in out["headline"]
    assert "worst_case_stop_budget" in out["headline"]


def test_a_clean_book_is_admitted_by_the_whole_default_stack():
    stack = ProtectionStack(default_protections("aggressive"), profile="aggressive")
    out = stack.evaluate(_state(8, 0.10, 0.03, peak_equity_usd=100_000.0,
                                realised_pnl_today_usd=0.0,
                                periods_since_last_exit_by_name={}))
    assert out["entries_allowed"] is True
    assert out["n_locked"] == 0
    assert out["n_cannot_determine"] == 0


def test_NO_PROTECTION_CAN_EVER_BLOCK_AN_EXIT():
    stack = ProtectionStack(default_protections("aggressive"))
    out = stack.evaluate(BookState())
    assert out["blocks"] == "entries only -- no protection can ever block an exit"
    for g in default_protections("aggressive"):
        assert g.blocks == "entries"


def test_a_name_scoped_lock_does_not_lock_the_whole_book():
    stack = ProtectionStack([CooldownPeriod(periods=2)])
    out = stack.evaluate(BookState(periods_since_last_exit_by_name={"A": 0, "B": 9}))
    assert out["entries_allowed"] is True
    assert out["blocked_names"] == ["A"]
    assert "1 name(s) on cooldown" in out["headline"]
