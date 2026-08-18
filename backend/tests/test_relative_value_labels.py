"""NEURAL-RELATIVE-VALUE-1 labels — the cost gate is the contract.

What must never happen silently: a band resolved by picking an end, a
sensitive pair trained on, a free switch into an unpriced name, a pair
count quoted without its date count.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import cost_model as CM
from backend.services import relative_value_labels as RV


def _bps(v):
    return CM.OneWayBps(v, CM.MEASURED_TAQ_QUOTED, basis="test")


# ── combining the two legs ─────────────────────────────────────────────────
def test_two_measured_legs_sum_to_a_measured_cost():
    j = RV.combine_switch_cost(_bps(2.0), _bps(3.0))
    assert isinstance(j, CM.OneWayBps)
    assert j.value == pytest.approx(5.0)
    assert j.measured


def test_one_band_leg_makes_the_joint_a_band_with_the_weaker_provenance():
    j = RV.combine_switch_cost(_bps(2.0), CM.declared_liquid_band("x"))
    assert isinstance(j, CM.CostBand)
    assert j.low.value == pytest.approx(3.0)     # 2 + 1
    assert j.high.value == pytest.approx(7.0)    # 2 + 5
    assert j.provenance == CM.DECLARED_CONSERVATIVE


def test_a_bare_float_leg_refuses():
    with pytest.raises(RV.PairRefused, match="bare float"):
        RV.combine_switch_cost(2.0, _bps(3.0))


# ── the label ──────────────────────────────────────────────────────────────
def test_net_verdict_at_a_measured_cost_is_exact():
    lab = RV.pair_label(fwd_a=0.010, fwd_b=0.020, dd_a=-0.05, dd_b=-0.03,
                        cost_a=_bps(2.0), cost_b=_bps(3.0))
    assert lab["improvement_gross"] == pytest.approx(0.010)
    assert lab["improvement_net"] == pytest.approx(0.010 - 5.0 / 1e4)
    assert lab["beats_net"] is True
    assert lab["drawdown_delta"] == pytest.approx(0.02)


def test_a_verdict_that_flips_inside_the_band_is_sensitive_and_unnumbered():
    """Gross improvement 8bp against a joint band [3+1, 3+5] = [4, 8]bp of
    switch cost: positive at the low end, zero/negative at the high end.
    The pair is COST_MODEL_SENSITIVE and carries NO net number — a net at
    'some' cost is what resolve_band_by_picking exists to refuse."""
    lab = RV.pair_label(fwd_a=0.0, fwd_b=0.0008, dd_a=None, dd_b=None,
                        cost_a=_bps(3.0), cost_b=CM.declared_liquid_band("x"))
    assert lab["beats_net"] == CM.COST_MODEL_SENSITIVE
    assert lab["cost_model_sensitive"] is True
    assert lab["improvement_net"] is None


def test_an_invented_return_refuses():
    with pytest.raises(RV.PairRefused, match="invented"):
        RV.pair_label(fwd_a=float("nan"), fwd_b=0.01, dd_a=None, dd_b=None,
                      cost_a=_bps(1.0), cost_b=_bps(1.0))


# ── sampling ───────────────────────────────────────────────────────────────
def test_pair_sampling_is_deterministic_and_self_free():
    names = [f"T{i}" for i in range(20)]
    a = RV.sample_pairs(names, 50, seed=1)
    b = RV.sample_pairs(names, 50, seed=1)
    assert a == b
    assert all(x != y for x, y in a)
    assert len(a) == 50


def test_sampling_caps_at_the_full_cross():
    assert len(RV.sample_pairs(["A", "B"], 99, seed=1)) == 2


# ── one date's build ───────────────────────────────────────────────────────
def _rows():
    return pd.DataFrame({
        "date": ["2026-01-30"] * 4,
        "ticker": ["A", "B", "C", "D"],
        # D→A gross = +4bp sits INSIDE the joint band [2bp, 6bp] when D is
        # on the declared band — the pair the sensitivity gate must catch.
        "forward_return": [0.0012, 0.05, -0.02, 0.0008],
        "forward_max_drawdown": [-0.05, -0.02, -0.10, -0.04],
    })


def test_sensitive_pairs_are_counted_and_excluded_from_training():
    costs = {"A": _bps(1.0), "B": _bps(1.0), "C": _bps(1.0),
             "D": CM.declared_liquid_band("x")}
    res = RV.build_date_pairs(_rows(), costs, pairs_per_date=12, seed=0)
    assert res["n_date_blocks"] == 1
    trained = pd.DataFrame(res["rows"])
    if len(trained):
        assert not trained["cost_model_sensitive"].any()
    # with D on a band, at least one D-pair near zero gross must be sensitive
    assert res["n_cost_model_sensitive"] >= 1


def test_an_unpriced_name_refuses_its_pairs_rather_than_switching_free():
    costs = {"A": _bps(1.0), "B": _bps(1.0), "C": _bps(1.0)}   # D missing
    res = RV.build_date_pairs(_rows(), costs, pairs_per_date=12, seed=0)
    assert res["n_refused_no_cost"] >= 1
    assert all(r["incumbent"] != "D" and r["candidate"] != "D"
               for r in res["rows"])
