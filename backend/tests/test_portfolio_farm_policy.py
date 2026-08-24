"""A policy is a DECLARATION — every refusal it makes, and the identity it has.

`PolicyError` is enrolled in `guard_contract.NOT_INPUT_GUARDS` pointing here, so
this file owes each branch a test. The interesting one is the cost refusal: a
zero-cost backtest is the single most common way a strategy looks real, and the
whole "explore dirty, promote clean" licence depends on the dirt being LABELLED.
"""

from __future__ import annotations

import pytest

from backend.services.portfolio_farm.policy import Policy, PolicyError, grid


def test_a_policy_id_is_the_whole_record():
    a = Policy()
    b = Policy(top_k=13)
    assert a.policy_id != b.policy_id
    assert Policy().policy_id == a.policy_id, "identity must be deterministic"


def test_the_NOTE_is_part_of_the_identity():
    """Two policies that differ only in intent are different policies. The
    alternative — a note outside the hash — lets a forward book's stated
    purpose be rewritten without re-identifying it."""
    assert Policy(note="a").policy_id != Policy(note="b").policy_id


def test_the_seed_is_part_of_the_identity():
    assert Policy(signal="random", signal_seed=1).policy_id != \
        Policy(signal="random", signal_seed=2).policy_id


# ── the refusals ────────────────────────────────────────────────────────────


def test_zero_cost_REFUSES_unless_declared():
    with pytest.raises(PolicyError) as exc:
        Policy(transaction_cost_bps=0.0, slippage_bps=0.0)
    assert "diagnostic" in str(exc.value).lower()
    ok = Policy(transaction_cost_bps=0.0, slippage_bps=0.0,
                zero_cost_diagnostic=True)
    assert ok.round_trip_bps == 0.0
    assert "FREE" in ok.label, "a frictionless run must be visible on its row"


def test_declaring_frictionless_while_CHARGING_costs_refuses():
    """The other direction, and the dangerous one: a row labelled FREE that
    actually paid costs would understate a real strategy, but a row labelled
    net that ran frictionless would OVERSTATE one."""
    with pytest.raises(PolicyError):
        Policy(transaction_cost_bps=5.0, zero_cost_diagnostic=True)


def test_an_unknown_signal_refuses_and_LISTS_what_exists():
    with pytest.raises(PolicyError) as exc:
        Policy(signal="mom_12_1_v2")
    assert "mom_12_1" in str(exc.value)


def test_an_unknown_sizing_refuses():
    with pytest.raises(PolicyError):
        Policy(sizing="hrp")


@pytest.mark.parametrize("kw", [
    {"holding_days": 0}, {"top_k": 0}, {"max_single_name": 1.5},
    {"delisting_return": 0.5}, {"delisting_return": -2.0},
])
def test_out_of_range_parameters_refuse(kw):
    with pytest.raises(PolicyError):
        Policy(**kw)


def test_delisting_zero_is_ALLOWED_because_it_is_a_sensitivity_arm():
    """-30% is the default assumption, not the only permitted one. Bounding a
    result at 0.0 and -1.0 is how the assumption gets audited, so the
    constructor must not forbid the endpoints."""
    assert Policy(delisting_return=0.0).delisting_return == 0.0
    assert Policy(delisting_return=-1.0).delisting_return == -1.0


# ── the grid ────────────────────────────────────────────────────────────────


def test_grid_is_the_cartesian_product():
    g = grid(signal=["mom_12_1", "low_vol"], holding_days=[1, 21])
    assert len(g) == 4
    assert {(p.signal, p.holding_days) for p in g} == {
        ("mom_12_1", 1), ("mom_12_1", 21), ("low_vol", 1), ("low_vol", 21)}


def test_grid_COLLAPSES_identical_policies():
    """Two axis combinations can describe one policy. Running it twice would
    put the same result on the leaderboard twice and make a coincidence look
    like a cluster of agreeing strategies."""
    g = grid(signal=["mom_12_1", "mom_12_1"], holding_days=[21])
    assert len(g) == 1


def test_an_empty_grid_is_one_default_policy_not_zero():
    assert len(grid()) == 1
