"""G3: regret must be measured in the units it was selected under.

`regret_pct` took no objective and called `best()` with none either, so a caller
ranking under a drawdown- or ruin-penalised objective got a winner chosen by one
criterion and a regret differenced in raw net return.

These tests build an episode where the two criteria genuinely disagree — if they
agreed, the tests would pass on the broken code and prove nothing.
"""

from __future__ import annotations

import pytest

from backend.services.research_gym import utility as U
from backend.services.research_gym.counterfactual import (PolicyResult,
                                                          ResponseSurface)


def _res(name: str, path: list[float], turnover: float = 0.0) -> PolicyResult:
    net = (path[-1] - 1.0) * 100.0
    return PolicyResult(
        name=name, exposure_path=tuple([1.0] * (len(path) - 1)),
        gross_return_pct=net, cost_pct=0.0, net_return_pct=net,
        turnover=turnover, first_divergence_day=0,
        wealth_path=tuple(path))


def _surface() -> ResponseSurface:
    """Two policies that rank DIFFERENTLY under return and under drawdown.

    `bumpy` ends higher but drops 40% on the way; `smooth` ends lower with a
    trivial drawdown. Raw return prefers bumpy; a preservation objective
    prefers smooth. That disagreement is the whole point.
    """
    bumpy = _res("bumpy", [1.0, 1.10, 0.60, 0.90, 1.30])
    smooth = _res("smooth", [1.0, 1.03, 1.02, 1.06, 1.12])
    return ResponseSurface(
        episode_id="g3-units", security="TEST",
        decision_ts="2020-03-01", horizon_days=20,
        taken_policy="smooth", cost_bps=0.0,
        results={"bumpy": bumpy, "smooth": smooth},
    )


def test_the_two_objectives_really_do_disagree():
    """Guards the guard: if this fails the other tests prove nothing."""
    s = _surface()
    assert s.best().name == "bumpy"                       # raw return
    assert s.best("preservation").name == "smooth"        # drawdown-aware


def test_regret_under_an_objective_is_measured_in_that_objective():
    s = _surface()
    # taken IS the best under preservation, so regret must be zero there.
    assert s.regret_pct("preservation") == pytest.approx(0.0, abs=1e-9)
    # ...while raw return still shows the bumpy path as forgone upside.
    assert s.regret_pct() > 0.0


def test_regret_is_never_negative_under_its_own_objective():
    """Best-minus-taken cannot be negative when both use one criterion.

    Under the old signature this was violated for any objective where the
    argmax differed from the raw-return argmax.
    """
    for name in ("preservation", "balanced", "aggressive", "extreme_growth",
                 "total_return", "sortino"):
        r = _surface().regret_pct(name)
        if r is not None:
            assert r >= -1e-9, f"negative regret under {name}: {r}"


def test_the_old_mismatch_is_what_this_closes():
    """Reconstructs the defect explicitly, so it cannot quietly return.

    Selecting under preservation and differencing net_return_pct — the old
    behaviour — reports the taken policy as WORSE than the winner it actually
    was, which is a units mismatch and not a measurement.
    """
    s = _surface()
    b = s.best("preservation")
    mismatched = b.net_return_pct - s.taken.net_return_pct
    assert mismatched == pytest.approx(0.0, abs=1e-9)
    # and the genuinely broken pairing — old best(), preservation intent:
    old_style = s.best().net_return_pct - s.taken.net_return_pct
    assert old_style > 0.0
    assert s.regret_pct("preservation") != pytest.approx(old_style)


def test_units_are_reported_beside_the_number():
    s = _surface()
    assert "net return" in s.regret_units()
    assert "preservation" in s.regret_units("preservation")
    assert s.as_dict()["regret_units"] == s.regret_units()


def test_all_four_personalities_are_declared_and_ordered():
    """G3 needed four; three of them did not exist before 2026-08-16."""
    for name in ("preservation", "balanced", "aggressive", "extreme_growth"):
        assert name in U.OBJECTIVES, f"{name} missing from OBJECTIVES"
    assert [o.name for o in U.PERSONALITIES] == [
        "preservation", "balanced", "aggressive", "extreme_growth"]


def test_no_personality_sits_at_the_cash_optimum_cliff():
    """dd_lambda >= 1.0 makes cash the argmax everywhere — a spec error.

    Checked behaviourally rather than by reading the constant: a flat
    zero-return, zero-drawdown path must not beat a real winner.
    """
    cash = _res("cash", [1.0, 1.0, 1.0, 1.0, 1.0])
    winner = _res("winner", [1.0, 1.05, 1.03, 1.10, 1.20])
    for obj in U.PERSONALITIES:
        sc = U.score_one(obj, U.stats_of(cash))
        sw = U.score_one(obj, U.stats_of(winner))
        assert sw > sc, (
            f"{obj.name} prefers cash to a +20% path with a 2% drawdown — "
            f"the drawdown penalty is past the degenerate cliff")
