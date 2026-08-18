"""The replay's contract: one difference at a time, and never a silent drop.

Built on constructed price paths whose answers are arithmetic, not on the live
book — a decomposition validated against the number it produced would be
validated against itself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import lane_autopsy as LA


def _prices(paths: dict[str, list[float]], start="2026-06-08") -> pd.DataFrame:
    n = len(next(iter(paths.values())))
    idx = pd.bdate_range(start=start, periods=n)
    return pd.DataFrame(paths, index=idx)


def _flat(n=60, price=100.0):
    return [price] * n


def _ramp(n=60, price=100.0, step=0.01):
    out, p = [], price
    for _ in range(n):
        out.append(p)
        p *= (1.0 + step)
    return out


# ── the mechanism machinery ────────────────────────────────────────────────
def test_only_the_mechanisms_that_actually_differ_are_reported():
    """`costs` is identical in both lanes as seeded, so it must NOT appear.
    A mechanism listed at +0.00% because it was never different reads exactly
    like one tested and found immaterial."""
    mechs = LA.differing_mechanisms(LA.CONVICTION_RULES, LA.MIRROR_RULES)
    assert "costs" not in mechs
    assert set(mechs) == {"weights", "cadence", "drift_trigger", "caps"}


def test_flipping_one_mechanism_changes_exactly_its_own_fields():
    """The property that makes 'one difference at a time' structural rather
    than a matter of careful editing."""
    flipped = LA._flip(LA.CONVICTION_RULES, LA.MIRROR_RULES, ["cadence"])
    assert flipped.rebalance_frequency == LA.MIRROR_RULES.rebalance_frequency
    # ...and nothing else moved.
    assert flipped.optimizer == LA.CONVICTION_RULES.optimizer
    assert flipped.max_single_name == LA.CONVICTION_RULES.max_single_name
    assert flipped.rebalance_trigger_drift is None


def test_an_unknown_mechanism_is_refused():
    with pytest.raises(LA.ReplayRefused, match="unknown mechanism"):
        LA._flip(LA.CONVICTION_RULES, LA.MIRROR_RULES, ["vibes"])


def test_identical_rule_sets_are_refused_rather_than_reported_as_no_effect():
    px = _prices({"A": _ramp(), "B": _flat()})
    with pytest.raises(LA.ReplayRefused, match="identical"):
        LA.decompose(px, {"A": 1, "B": 1}, LA.CONVICTION_RULES,
                     LA.CONVICTION_RULES)


# ── the replay's arithmetic ────────────────────────────────────────────────
def test_a_flat_book_returns_zero_and_costs_nothing_without_rebalancing():
    px = _prices({"A": _flat(), "B": _flat()})
    out = LA.replay(px, {"A": 10, "B": 10}, LA.CONVICTION_RULES)
    assert out["total_return"] == pytest.approx(0.0, abs=1e-12)
    assert out["n_rebalances"] == 0 and out["turnover_total"] == 0.0


def test_buy_and_hold_compounds_the_underlying():
    """A single name held forever must return exactly what the name did."""
    px = _prices({"A": _ramp(n=30, step=0.01)})
    out = LA.replay(px, {"A": 5}, LA.CONVICTION_RULES)
    expected = px["A"].iloc[-1] / px["A"].iloc[0] - 1.0
    assert out["total_return"] == pytest.approx(expected, rel=1e-9)


def test_rebalancing_costs_are_charged_against_BOTH_legs_of_turnover():
    """`turn = sum(|dw|)` counts a sell and a buy, and the rate charged against
    it is ONE-WAY — the Order 18 §1 convention, restated here because a replay
    that gets it backwards charges twice."""
    px = _prices({"A": _ramp(n=45, step=0.02), "B": _flat(n=45)})
    free = LA.LaneRules(label="free", optimizer="equal",
                        rebalance_frequency="monthly", cost_bps_one_way=0.0)
    paid = LA.LaneRules(label="paid", optimizer="equal",
                        rebalance_frequency="monthly", cost_bps_one_way=100.0)
    a = LA.replay(px, {"A": 1, "B": 1}, free)
    b = LA.replay(px, {"A": 1, "B": 1}, paid)
    assert a["cost_drag"] == 0.0 and b["cost_drag"] > 0.0
    assert b["total_return"] < a["total_return"]
    assert b["cost_drag"] == pytest.approx(b["turnover_total"] * 0.01, abs=1e-6)


def test_the_drift_trigger_fires_without_any_calendar_cadence():
    """The two rebalance paths are independent, and the live lane runs both."""
    px = _prices({"A": _ramp(n=40, step=0.05), "B": _flat(n=40)})
    rules = LA.LaneRules(label="drift", optimizer="equal",
                         rebalance_frequency="never",
                         rebalance_trigger_drift=0.05)
    out = LA.replay(px, {"A": 1, "B": 1}, rules)
    assert out["n_rebalances"] > 0


def test_a_trigger_that_can_never_be_reached_produces_no_rebalances():
    px = _prices({"A": _ramp(n=40, step=0.05), "B": _flat(n=40)})
    rules = LA.LaneRules(label="never", optimizer="equal",
                         rebalance_frequency="never",
                         rebalance_trigger_drift=99.0)
    assert LA.replay(px, {"A": 1, "B": 1}, rules)["n_rebalances"] == 0


# ── the caps ───────────────────────────────────────────────────────────────
def test_a_binding_cap_actually_caps_and_the_weights_still_sum_to_one():
    w = pd.Series({"A": 0.7, "B": 0.1, "C": 0.1, "D": 0.05, "E": 0.05})
    capped = LA._apply_caps(w, LA.LaneRules(label="c", max_single_name=0.25))
    assert capped.max() <= 0.25 + 1e-9
    assert capped.sum() == pytest.approx(1.0)


def test_capping_iterates_because_renormalising_can_push_another_name_over():
    """The single-pass version leaves a violation behind, and the violation is
    small enough to be missed by eye in a weight table."""
    w = pd.Series({"A": 0.5, "B": 0.24, "C": 0.16, "D": 0.06, "E": 0.04})
    capped = LA._apply_caps(w, LA.LaneRules(label="c", max_single_name=0.25))
    assert capped.max() <= 0.25 + 1e-9
    assert capped.sum() == pytest.approx(1.0)


def test_an_ARITHMETICALLY_IMPOSSIBLE_cap_is_refused_not_oscillated():
    """Found by these tests, not by review: three names capped at 25% can hold
    0.75 of a book, so no feasible vector exists — and the naive iteration does
    not fail, it oscillates and returns whichever violating vector it stopped
    on. A constraint violation wearing the shape of a converged answer."""
    w = pd.Series({"A": 0.7, "B": 0.2, "C": 0.1})
    with pytest.raises(LA.ReplayRefused, match="NO feasible weight vector"):
        LA._apply_caps(w, LA.LaneRules(label="c", max_single_name=0.25))


def test_the_LIVE_lane_cap_is_feasible_so_the_refusal_never_fires_there():
    """The reason it went unnoticed: 12 names at 25% hold 3x the book."""
    w = pd.Series({f"N{i}": 1 / 12 for i in range(12)})
    out = LA._apply_caps(w, LA.MIRROR_RULES)
    assert out.sum() == pytest.approx(1.0)


def test_a_cap_above_every_weight_is_a_no_op():
    w = pd.Series({"A": 0.5, "B": 0.3, "C": 0.2})
    out = LA._apply_caps(w, LA.LaneRules(label="c", max_single_name=0.9))
    assert out.equals(w)


# ── the missing-name refusal ───────────────────────────────────────────────
def test_a_name_with_no_price_column_is_REFUSED_not_dropped():
    """The failure that reads as a return: the survivors re-normalise and the
    book looks like it went up."""
    px = _prices({"A": _ramp(), "B": _flat()})
    with pytest.raises(LA.ReplayRefused, match="survivorship"):
        LA.replay(px, {"A": 1, "B": 1, "GONE": 1}, LA.CONVICTION_RULES)


def test_a_name_with_no_price_at_inception_is_refused():
    px = _prices({"A": _ramp(), "B": _flat()})
    px.iloc[0, px.columns.get_loc("B")] = np.nan
    with pytest.raises(LA.ReplayRefused, match="inception"):
        LA.replay(px, {"A": 1, "B": 1}, LA.CONVICTION_RULES)


def test_a_one_row_window_is_refused():
    px = _prices({"A": [100.0]})
    with pytest.raises(LA.ReplayRefused, match="at least two"):
        LA.replay(px, {"A": 1}, LA.CONVICTION_RULES)


# ── the decomposition's honesty ────────────────────────────────────────────
def test_the_residual_is_reported_and_the_marginals_are_NOT_forced_to_sum():
    """The Brinson interaction error, refused. If the five numbers were made to
    add up, the forcing would be invisible and the attribution would be
    confident about something it invented."""
    px = _prices({"A": _ramp(n=60, step=0.02), "B": _ramp(n=60, step=-0.005),
                  "C": _flat(n=60), "D": _ramp(n=60, step=0.004),
                  "E": _flat(n=60)})
    out = LA.decompose(px, {"A": 3, "B": 3, "C": 3, "D": 3, "E": 3})
    assert "residual" in out and "sum_of_marginals" in out
    got = out["gap_total"] - out["sum_of_marginals"]
    assert out["residual"] == pytest.approx(got, abs=1e-6)


def test_both_directions_are_measured_for_every_mechanism():
    px = _prices({"A": _ramp(n=60, step=0.02), "B": _flat(n=60),
                  "C": _flat(n=60), "D": _flat(n=60), "E": _flat(n=60)})
    out = LA.decompose(px, {"A": 2, "B": 2, "C": 2, "D": 2, "E": 2})
    for row in out["mechanisms"]:
        assert "marginal_effect" in row and "leave_one_out_effect" in row
        assert row["interaction"] == pytest.approx(
            row["leave_one_out_effect"] - row["marginal_effect"], abs=1e-6)


def test_a_mechanism_that_never_fires_is_flagged_INERT_not_immaterial():
    """The live finding this encodes: the mirror lane's 25% cap cannot bind
    while the optimizer falls back to equal weight over 12 names. '+0.00%'
    reads as 'tested and it did not matter', which is a far stronger claim
    than 'it never ran'."""
    px = _prices({"A": _ramp(n=60, step=0.01), "B": _flat(n=60)})
    base = LA.LaneRules(label="b", optimizer="equal")
    target = LA.LaneRules(label="t", optimizer="equal", max_single_name=0.99)
    out = LA.decompose(px, {"A": 2, "B": 2}, base, target)
    caps = next(r for r in out["mechanisms"] if r["mechanism"] == "caps")
    assert caps["inert"] is True
    assert "DEAD BRANCH" in caps["inert_note"]


def test_the_hrp_fallback_is_reported_rather_than_silently_equal_weighting():
    """A replay labelled HRP that ran equal weight would be a false claim about
    what the lane does, and the lane's own gate makes the fallback the normal
    case on any window shorter than a year."""
    px = _prices({"A": _ramp(n=60, step=0.01), "B": _flat(n=60),
                  "C": _flat(n=60), "D": _flat(n=60), "E": _flat(n=60)})
    out = LA.replay(px, {"A": 2, "B": 2, "C": 2, "D": 2, "E": 2},
                    LA.MIRROR_RULES)
    assert out["hrp_fallback"] == "EQUAL_WEIGHT_HRP_HISTORY_GATE_NOT_MET"


def test_the_decomposition_refuses_to_annualise_and_says_so():
    px = _prices({"A": _ramp(n=60, step=0.01), "B": _flat(n=60),
                  "C": _flat(n=60), "D": _flat(n=60), "E": _flat(n=60)})
    out = LA.decompose(px, {"A": 2, "B": 2, "C": 2, "D": 2, "E": 2})
    assert "may_not_conclude" in out
    assert "annualis" in out["may_not_conclude"].lower()
    assert not any("annual" in k for k in out)


def test_the_replay_is_deterministic():
    px = _prices({"A": _ramp(n=60, step=0.013), "B": _ramp(n=60, step=-0.004),
                  "C": _flat(n=60), "D": _flat(n=60), "E": _flat(n=60)})
    a = LA.decompose(px, {"A": 5, "B": 7, "C": 3, "D": 3, "E": 3})
    b = LA.decompose(px, {"A": 5, "B": 7, "C": 3, "D": 3, "E": 3})
    assert a["gap_total"] == b["gap_total"]
    assert [r["marginal_effect"] for r in a["mechanisms"]] == [
        r["marginal_effect"] for r in b["mechanisms"]]
