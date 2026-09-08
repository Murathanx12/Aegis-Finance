"""S1 -- the `Strategy` contract: what it refuses, and what it hashes.

The contract is only worth having if it REFUSES the things the prose rules
refuse. Each test below names the rule it is enforcing, because a contract
whose validation is untested is a docstring with a dataclass around it.
"""

from __future__ import annotations

import pytest

from backend.services.portfolio_farm.policy import PolicyError
from backend.strategy.contract import (DEFAULT_EXIT_PRIORITY, Benchmark,
                                       Construction, CostModel, HoldRule,
                                       Licence, LossBudget, Objective, Signal,
                                       Sizing, Strategy, StrategyError,
                                       Universe, Window, loss_budget_worst_case)


def _strategy(**kw) -> Strategy:
    base = dict(
        strategy_id="test:book",
        title="a book",
        universe=Universe(name="u"),
        signal=Signal(name="mom_12_1"),
        construction=Construction(),
        hold=HoldRule(),
        sizing=Sizing(),
        costs=CostModel(),
        benchmark=Benchmark(),
        objective=Objective(),
        loss_budget=LossBudget(positions_judged=20, expected_losers=8),
    )
    base.update(kw)
    return Strategy(**base)


# ------------------------------------------------------------------ costs


def test_zero_costs_are_REFUSED_by_the_farm_policy_and_not_by_a_second_copy():
    """CLAUDE.md 'EXPLORE DIRTY, PROMOTE CLEAN' item 3.

    The refusal must come OUT OF `portfolio_farm.Policy`, so that there is
    exactly one place in the repository that decides whether a frictionless run
    is admissible. `PolicyError` in the traceback is the proof.
    """
    with pytest.raises(PolicyError, match="zero transaction cost is not a default"):
        CostModel(transaction_cost_bps=0.0, slippage_bps=0.0)


def test_the_frictionless_diagnostic_is_declarable_and_the_flag_TRAVELS():
    c = CostModel(transaction_cost_bps=0.0, slippage_bps=0.0,
                  zero_cost_diagnostic=True)
    assert c.as_row()["zero_cost_diagnostic"] is True
    s = _strategy(costs=c)
    assert s.as_row()["zero_cost_diagnostic"] is True
    assert "FREE" in s.label


def test_declaring_the_diagnostic_flag_with_real_costs_is_ALSO_refused():
    """Otherwise a real run could be labelled frictionless, which is the same
    lie pointing the other way."""
    with pytest.raises(PolicyError, match="labels a real run as frictionless"):
        CostModel(transaction_cost_bps=5.0, slippage_bps=1.0,
                  zero_cost_diagnostic=True)


# ------------------------------------------------------------- exit ladder


def test_an_untyped_exit_reason_is_refused():
    """Invariant 17 requires exit attribution BY TYPED REASON; an untyped exit
    is precisely the one that cannot be attributed."""
    with pytest.raises(StrategyError, match="are not typed"):
        HoldRule(exit_priority=("VIBES",))


def test_the_roi_ladder_resolves_by_the_largest_matured_rung():
    """freqtrade `minimal_roi`: {0: 0.10, 5: 0.04, 21: 0.0}."""
    h = HoldRule(roi_ladder={0: 0.10, 5: 0.04, 21: 0.0})
    assert h.roi_floor_at(0) == pytest.approx(0.10)
    assert h.roi_floor_at(4) == pytest.approx(0.10)
    assert h.roi_floor_at(5) == pytest.approx(0.04)
    assert h.roi_floor_at(100) == pytest.approx(0.0)


def test_an_unstarted_ladder_returns_None_and_NOT_zero():
    """0.0 would read as 'take any profit'; None reads as 'no rung has
    matured'. The difference is a position closed on its first green tick."""
    h = HoldRule(roi_ladder={5: 0.04})
    assert h.roi_floor_at(0) is None
    assert h.roi_floor_at(5) == pytest.approx(0.04)


def test_a_positive_stop_loss_is_refused():
    with pytest.raises(StrategyError, match="NEGATIVE ratio"):
        HoldRule(stop_loss=0.08)


def test_the_default_exit_priority_ranks_signal_above_stop_above_roi():
    p = list(DEFAULT_EXIT_PRIORITY)
    assert p.index("THESIS_INVALIDATED") < p.index("STOP") < p.index("ROI_LADDER")
    assert p.index("ROI_LADDER") < p.index("TRAILING_STOP") < p.index("DEADLINE")


# --------------------------------------------------------------- objective


def test_the_product_ruler_without_a_drawdown_budget_is_refused():
    """'terminal wealth AT A DRAWDOWN BUDGET' without the budget ranks the most
    levered book first every time."""
    with pytest.raises(StrategyError, match="drawdown_budget"):
        Objective(name="terminal_wealth_at_drawdown_budget")
    Objective(name="terminal_wealth_at_drawdown_budget", drawdown_budget=-0.35)


def test_an_unknown_objective_is_refused_and_the_message_lists_the_declared_ones():
    with pytest.raises(StrategyError, match="unknown objective"):
        Objective(name="make_money")


# -------------------------------------------------------------- loss budget


def test_a_loss_budget_that_cannot_be_spent_is_refused():
    with pytest.raises(StrategyError, match="not a budget"):
        LossBudget(positions_judged=10, expected_losers=11)


def test_the_scoreboard_retires_an_idea_by_its_BOOK_not_by_its_first_loss():
    """Invariant 19."""
    lb = LossBudget(positions_judged=20, expected_losers=8)
    assert lb.scoreboard(losers_so_far=1, positions_so_far=1)["retired_by_scoreboard"] is False
    assert lb.scoreboard(losers_so_far=8, positions_so_far=12)["retired_by_scoreboard"] is False
    assert lb.scoreboard(losers_so_far=9, positions_so_far=14)["retired_by_scoreboard"] is True


# ---------------------------------------------------------------- identity


def test_a_drifted_parameter_is_a_DIFFERENT_strategy():
    a = _strategy()
    b = a.with_(construction=Construction(k=13))
    assert a.fingerprint != b.fingerprint
    assert a.fingerprint == _strategy().fingerprint      # and it is stable


def test_the_fingerprint_moves_with_the_cost_rate_and_with_the_licence():
    a = _strategy()
    assert a.fingerprint != a.with_(costs=CostModel(transaction_cost_bps=25.0)).fingerprint
    assert a.fingerprint != a.with_(licence=Licence.CAPITAL_CANDIDATE,
                                    note="claimed under the capital gate").fingerprint


def test_a_stricter_licence_must_say_which_standard_it_claims_under():
    with pytest.raises(StrategyError, match="which evidence standard"):
        _strategy(licence=Licence.RESEARCH_CLAIM)


# ------------------------------------------------- session protocol rule 4


def test_the_worst_case_is_printed_in_dollars_with_the_gross_line_beside_it():
    """The 28 Aug arithmetic: twelve names x 25% = 300% gross, 3% stop = -9%."""
    s = _strategy(hold=HoldRule(stop_loss=-0.03), sizing=Sizing(gross_cap=1.0))
    w = loss_budget_worst_case(s, n_names=12, notional_pct=0.25, equity_usd=100_000)
    assert w["gross_over_equity"] == pytest.approx(3.0)
    assert w["gross_within_cap"] is False
    assert w["worst_case_pct_of_equity"] == pytest.approx(0.09)
    assert w["worst_case_usd"] == pytest.approx(-9000.0)


def test_widening_the_stop_on_uncapped_gross_makes_the_worst_case_WORSE():
    """The 'fix' that raised -9% to -24%. Pinned so it cannot be proposed again
    without the number appearing beside it."""
    narrow = loss_budget_worst_case(_strategy(hold=HoldRule(stop_loss=-0.03)),
                                    n_names=12, notional_pct=0.25, equity_usd=100_000)
    wide = loss_budget_worst_case(_strategy(hold=HoldRule(stop_loss=-0.08)),
                                  n_names=12, notional_pct=0.25, equity_usd=100_000)
    assert abs(wide["worst_case_usd"]) > abs(narrow["worst_case_usd"])


def test_no_stop_is_CANNOT_DETERMINE_and_not_a_zero_loss():
    w = loss_budget_worst_case(_strategy(), n_names=12, notional_pct=0.25,
                               equity_usd=100_000)
    assert w["worst_case_usd"] is None
    assert w["verdict"].startswith("CANNOT DETERMINE")


# -------------------------------------------------------------- other rules


def test_an_unknown_construction_or_weighting_is_refused():
    with pytest.raises(StrategyError, match="unknown construction rule"):
        Construction(rule="vibes")
    with pytest.raises(StrategyError, match="unknown weighting"):
        Construction(weighting="magic")


def test_a_signal_direction_must_be_plus_or_minus_one():
    with pytest.raises(StrategyError, match="direction must be"):
        Signal(name="x", direction=0)


def test_a_window_carries_whether_it_is_sealed():
    w = Window("2016-01", "2024-12", label="growth sealed era", sealed=True)
    assert w.sealed is True
    assert Window("2004-01", "2015-12").sealed is False
