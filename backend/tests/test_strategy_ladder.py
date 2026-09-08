"""S6 -- the exit ladder as its own model, on KNOWN-ANSWER price paths.

The load-bearing test is the RANKING one: a bar on which two reasons both fire
must resolve to the reason the contract ranks first, and must resolve to the
OTHER one when the contract's ranking is reversed. That is what makes the order
data rather than an accident of which `if` was written first.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.strategy.contract import DEFAULT_EXIT_PRIORITY, HoldRule
from backend.strategy.ladder import (CANNOT_DETERMINE, EMERGENCY_REASONS,
                                     ExitLadder, LadderRefused,
                                     meta_label_exits, stop_vs_volatility)


def _hold(**kw) -> HoldRule:
    base = dict(horizon_periods=20, min_hold_periods=0,
                roi_ladder={0: 0.10, 5: 0.04, 10: 0.0},
                stop_loss=-0.08, trailing_stop=0.05)
    base.update(kw)
    return HoldRule(**base)


# --------------------------------------------------------------------------
# the time-decayed ROI curve


def test_the_roi_curve_decays_with_time_held():
    """`{0: 0.10, 5: 0.04, 10: 0.0}` = take 10% now; after 5 periods accept 4%;
    after 10 accept anything positive. Resolved by the largest key <= held."""
    h = _hold()
    assert h.roi_floor_at(0) == 0.10
    assert h.roi_floor_at(4) == 0.10
    assert h.roi_floor_at(5) == 0.04
    assert h.roi_floor_at(9) == 0.04
    assert h.roi_floor_at(10) == 0.0
    assert h.roi_floor_at(999) == 0.0


def test_an_unmatured_rung_is_None_not_zero():
    """None means 'the ladder has not started'; 0.0 means 'take any profit'."""
    h = _hold(roi_ladder={3: 0.05})
    assert h.roi_floor_at(0) is None
    assert h.roi_floor_at(3) == 0.05
    d = ExitLadder(h).evaluate(periods_held=0, unrealised_return=0.50)
    roi = next(c for c in d.checks if c.reason == "ROI_LADDER")
    assert roi.fired is False
    assert CANNOT_DETERMINE in roi.detail


# --------------------------------------------------------------------------
# THE RANKING -- the load-bearing test


def test_when_a_stop_and_a_signal_fire_together_the_DECLARED_ORDER_decides():
    h = _hold()
    assert h.exit_priority == DEFAULT_EXIT_PRIORITY
    d = ExitLadder(h).evaluate(periods_held=3, unrealised_return=-0.20,
                               signal_says_exit=True)
    assert set(d.fired) >= {"THESIS_INVALIDATED", "STOP"}
    assert d.winner == "THESIS_INVALIDATED"       # ranked above STOP


def test_reversing_the_declared_order_reverses_the_winner_on_the_SAME_bar():
    """The proof that the ranking is DATA: nothing about the bar changed."""
    reversed_priority = ("STOP", "THESIS_INVALIDATED",
                         "EXPLICIT_EVENT_STRATEGY_EXIT", "ROI_LADDER",
                         "TRAILING_STOP", "DEADLINE", "REBALANCE")
    h = _hold(exit_priority=reversed_priority)
    d = ExitLadder(h).evaluate(periods_held=3, unrealised_return=-0.20,
                               signal_says_exit=True)
    assert set(d.fired) >= {"THESIS_INVALIDATED", "STOP"}
    assert d.winner == "STOP"


def test_every_reason_is_EVALUATED_even_when_it_does_not_win():
    d = ExitLadder(_hold()).evaluate(periods_held=3, unrealised_return=-0.20,
                                     signal_says_exit=True)
    assert [c.reason for c in d.checks] == list(DEFAULT_EXIT_PRIORITY)


def test_a_stop_and_an_ROI_rung_on_one_bar_resolve_to_the_stop():
    """Impossible in one direction on a real bar, but the ranking must still be
    deterministic if a caller hands both."""
    h = _hold(roi_ladder={0: -0.50})
    d = ExitLadder(h).evaluate(periods_held=1, unrealised_return=-0.20)
    assert set(d.fired) >= {"STOP", "ROI_LADDER"}
    assert d.winner == "STOP"


# --------------------------------------------------------------------------
# minimum hold: suppresses the normal exits, never the emergency ones


def test_a_minimum_hold_SUPPRESSES_the_roi_rung():
    h = _hold(min_hold_periods=5, roi_ladder={0: 0.02})
    d = ExitLadder(h).evaluate(periods_held=2, unrealised_return=0.09)
    assert "ROI_LADDER" in d.fired
    assert d.winner is None
    assert d.suppressed_by_min_hold == ("ROI_LADDER",)


def test_a_minimum_hold_NEVER_suppresses_a_stop():
    h = _hold(min_hold_periods=5)
    d = ExitLadder(h).evaluate(periods_held=2, unrealised_return=-0.20)
    assert d.winner == "STOP"
    assert "STOP" not in d.suppressed_by_min_hold
    assert "STOP" in EMERGENCY_REASONS


def test_the_deadline_fires_at_the_horizon_and_not_before():
    h = _hold(horizon_periods=20, roi_ladder={}, stop_loss=None,
              trailing_stop=None)
    lad = ExitLadder(h)
    assert lad.evaluate(periods_held=19, unrealised_return=0.01).winner is None
    assert lad.evaluate(periods_held=20, unrealised_return=0.01).winner == "DEADLINE"


def test_the_trailing_stop_fires_on_giveback_from_the_peak():
    h = _hold(stop_loss=None, roi_ladder={}, trailing_stop=0.05)
    lad = ExitLadder(h)
    assert lad.evaluate(periods_held=3, unrealised_return=0.16,
                        peak_return=0.20).winner is None      # gave back 4%
    assert lad.evaluate(periods_held=3, unrealised_return=0.14,
                        peak_return=0.20).winner == "TRAILING_STOP"


# --------------------------------------------------------------------------
# simulation over a known path


def test_the_simulated_path_exits_at_the_STOP_bar_by_construction():
    """100 -> 99 -> 98 -> 90: -10% at bar 3 breaches the -8% stop."""
    h = _hold(roi_ladder={}, trailing_stop=None)
    out = ExitLadder(h).simulate([100.0, 99.0, 98.0, 90.0, 95.0])
    assert out["exit_reason"] == "STOP"
    assert out["exit_bar"] == 3
    assert out["fill_return"] == pytest.approx(-0.08)   # fills AT the stop
    assert out["return_at_bar"] == pytest.approx(-0.10)


def test_the_simulated_path_exits_on_the_ROI_rung_when_no_stop_is_hit():
    """{0: 0.10}: +12% at bar 2 clears the rung; the fill is the bar's 12%,
    not the rung's 10% -- an ROI exit can beat its own rung."""
    h = _hold(roi_ladder={0: 0.10}, trailing_stop=None)
    out = ExitLadder(h).simulate([100.0, 105.0, 112.0, 130.0])
    assert out["exit_reason"] == "ROI_LADDER"
    assert out["exit_bar"] == 2
    assert out["fill_return"] == pytest.approx(0.12)


def test_a_path_that_never_triggers_is_reported_as_a_CENSORED_SPELL():
    h = _hold(horizon_periods=99, roi_ladder={}, stop_loss=-0.50,
              trailing_stop=None)
    out = ExitLadder(h).simulate([100.0, 100.5, 101.0])
    assert out["exit_reason"] is None
    assert "censored" in out["note"]


def test_a_one_bar_path_REFUSES():
    with pytest.raises(LadderRefused, match="at least two"):
        ExitLadder(_hold()).simulate([100.0])


# --------------------------------------------------------------------------
# STOP WIDTH vs HOLDING-PERIOD VOLATILITY -- the 2026-09-08 finding


def test_a_stop_INSIDE_the_daily_noise_means_the_minimum_hold_can_never_bind():
    """THE LIVE CASE, reproduced. A 3% stop on a name whose per-period sd is
    3.06% is 0.98 sd wide; over a 1-period minimum hold the stop is inside one
    ordinary session and the hold rule can never bind."""
    h = _hold(stop_loss=-0.03, min_hold_periods=1)
    out = stop_vs_volatility(h, per_period_sd=0.0306)
    assert out["stop_in_sd"] == pytest.approx(0.98, abs=0.005)
    assert out["min_hold_can_bind"] is False
    assert "STOP INSIDE THE NOISE" in out["verdict"]


def test_a_stop_wider_than_the_holding_period_noise_CAN_bind():
    h = _hold(stop_loss=-0.15, min_hold_periods=1)
    out = stop_vs_volatility(h, per_period_sd=0.02)
    assert out["stop_in_sd"] == pytest.approx(7.5)
    assert out["min_hold_can_bind"] is True


def test_a_longer_minimum_hold_scales_the_noise_by_sqrt_n():
    """KNOWN ANSWER: sd 2%, min hold 25 -> holding-period sd 2% * 5 = 10%, so
    a 15% stop is 1.5 holding-period sd and still binds; a 9% stop does not."""
    a = stop_vs_volatility(_hold(stop_loss=-0.15, min_hold_periods=25),
                           per_period_sd=0.02)
    assert a["holding_period_sd"] == pytest.approx(0.10)
    assert a["stop_in_holding_period_sd"] == pytest.approx(1.5)
    assert a["min_hold_can_bind"] is True
    b = stop_vs_volatility(_hold(stop_loss=-0.09, min_hold_periods=25),
                           per_period_sd=0.02)
    assert b["min_hold_can_bind"] is False


def test_an_unmeasured_volatility_is_CANNOT_DETERMINE_not_an_assumption():
    out = stop_vs_volatility(_hold(), per_period_sd=float("nan"))
    assert out["min_hold_can_bind"] is None
    assert CANNOT_DETERMINE in out["verdict"]
    assert "inventing the answer" in out["verdict"]


def test_no_stop_declared_says_the_worst_case_is_the_whole_position():
    out = stop_vs_volatility(_hold(stop_loss=None), per_period_sd=0.02)
    assert "whole position" in out["verdict"]


# --------------------------------------------------------------------------
# META-LABELLING THE SELL


def test_the_meta_label_scores_the_exit_rule_by_typed_reason():
    """KNOWN ANSWER. STOP exits saved 5pp each (realised -0.08 vs a -0.13
    hold); DEADLINE exits cost 4pp each (realised +0.02 vs a +0.06 hold)."""
    exits = ([{"exit_reason": "STOP", "realised_return": -0.08,
               "forward_return_if_held": -0.13}] * 6
             + [{"exit_reason": "DEADLINE", "realised_return": 0.02,
                 "forward_return_if_held": 0.06}] * 6)
    out = meta_label_exits(exits)
    assert out["by_reason"]["STOP"]["mean_saved"] == pytest.approx(0.05)
    assert out["by_reason"]["STOP"]["share_correct"] == 1.0
    assert "SAVED money" in out["by_reason"]["STOP"]["verdict"]
    assert out["by_reason"]["DEADLINE"]["mean_saved"] == pytest.approx(-0.04)
    assert "COST money" in out["by_reason"]["DEADLINE"]["verdict"]
    assert out["mean_saved_overall"] == pytest.approx(0.005)


def test_an_exit_with_no_typed_reason_is_UNTYPED_not_dropped():
    out = meta_label_exits([{"realised_return": 0.01,
                             "forward_return_if_held": 0.02}])
    assert out["n_untyped"] == 1
    assert "UNTYPED" in out["by_reason"]


def test_a_record_missing_a_leg_is_UNLABELLED_not_imputed_as_zero():
    out = meta_label_exits([
        {"exit_reason": "STOP", "realised_return": -0.08,
         "forward_return_if_held": -0.13},
        {"exit_reason": "STOP", "realised_return": -0.08},
    ])
    assert out["n"] == 2
    assert out["n_labelled"] == 1
    assert out["n_unlabelled"] == 1
    assert out["by_reason"]["STOP"]["mean_saved"] == pytest.approx(0.05)


def test_no_exits_at_all_is_CANNOT_DETERMINE():
    assert CANNOT_DETERMINE in meta_label_exits([])["verdict"]
