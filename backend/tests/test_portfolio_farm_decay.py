"""The decay-blended target weights (roadmap section 11c), and the one claim
that makes the parameter safe: AT ITS DEFAULT NOTHING CHANGED.

`w_t = decay * w_{t-1} + (1 - decay) * target_t` is a cost-control knob, not a
new engine. Three things have to hold or it is a behaviour change wearing an
additive parameter's clothes:

1. `decay=0` reproduces today's NAV BIT-FOR-BIT, not "to a few decimals".
2. `decay=0` reproduces today's `policy_id`, so every archived receipt still
   identifies itself (`_HASH_NEUTRAL_DEFAULTS`).
3. `decay>0` is a DIFFERENT policy with a different hash, because a blended
   book is a different strategy and must never inherit the unblended one's
   history.

And the thing the parameter is FOR: a blended book trades less. That is
asserted on turnover rather than assumed from the formula.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.portfolio_farm import replay
from backend.services.portfolio_farm.policy import Policy, PolicyError
from backend.tests.test_portfolio_farm_pit import synthetic


def _pol(**kw) -> Policy:
    return Policy(**{"top_k": 5, "universe_n": 20, "holding_days": 21, **kw})


# ----------------------------------------------------- 1. the default is inert

def test_decay_zero_reproduces_the_undecayed_NAV_bit_for_bit():
    """The known-answer test the spec asks for. `decay=0` must not merely be
    close: the blend is skipped entirely, so every float is the same float."""
    panel = synthetic(seed=11)
    base = replay.run(panel, _pol(), warmup=260)
    same = replay.run(panel, _pol(decay=0.0), warmup=260)
    assert base.nav == same.nav
    assert base.metrics == same.metrics
    # `seconds` is wall-clock time, not a property of the replay: it differed by
    # a millisecond between two identical runs under a full-suite load on
    # 2026-09-13 and turned a determinism test into a timing test.
    strip = lambda d: {k: v for k, v in d.items() if k != "seconds"}  # noqa: E731
    assert strip(base.diagnostics) == strip(same.diagnostics)


def test_the_blend_branch_does_not_even_execute_at_the_default():
    """A diagnostics key that appeared on every row would change the shape of
    every archived receipt. Absent at the default, present when it is on."""
    panel = synthetic(seed=11)
    assert "n_blended_decisions" not in replay.run(panel, _pol(), warmup=260).diagnostics
    on = replay.run(panel, _pol(decay=0.5), warmup=260).diagnostics
    assert on["n_blended_decisions"] == on["n_decisions"] > 0
    assert on["decay"] == 0.5


def test_decay_zero_is_hash_neutral_and_any_other_value_is_not():
    """A field appended to a frozen hashed record re-identifies every policy
    ever written unless it is dropped at its default."""
    assert Policy().policy_id == "6479736fde09f076"
    assert Policy(decay=0.0).policy_id == Policy().policy_id
    assert Policy(decay=0.25).policy_id != Policy().policy_id
    assert Policy(decay=0.25).policy_id != Policy(decay=0.5).policy_id
    assert "d0.25" in Policy(decay=0.25).label
    assert "/d" not in Policy().label


# --------------------------------------------------- 2. the blend does its job

def test_a_blended_book_trades_less_than_its_own_decay_zero_twin():
    """THE REASON THE PARAMETER EXISTS. Reported against its `decay=0` twin at
    the SAME cost, which is the control the roadmap names."""
    panel = synthetic(seed=3)
    pol0 = _pol(holding_days=5, signal="mom_12_1")
    traded = {}
    for lam in (0.0, 0.5, 0.9):
        res = replay.run(panel, _pol(holding_days=5, signal="mom_12_1",
                                     decay=lam), warmup=260)
        traded[lam] = res.diagnostics["traded_notional_usd"]
    assert traded[0.0] == pytest.approx(
        replay.run(panel, pol0, warmup=260).diagnostics["traded_notional_usd"])
    assert traded[0.5] < traded[0.0], traded
    assert traded[0.9] < traded[0.5], traded


def test_the_blended_weights_stay_a_full_book_when_a_name_drops_out():
    """The renormalisation is the safety net. Without it the blend of two unit
    vectors over a CHANGED universe sums to less than one and the book quietly
    runs under-invested -- lower risk for a reason that has nothing to do with
    the strategy."""
    prev = np.zeros(6)
    prev[[0, 1, 2]] = 1.0 / 3.0
    chosen = np.array([3, 4, 5])
    weights = np.full(3, 1.0 / 3.0)
    idx, w, full = replay.blend_targets(prev, chosen, weights, _pol(decay=0.5))
    assert w.sum() == pytest.approx(1.0)
    assert full.sum() == pytest.approx(1.0)
    assert set(idx.tolist()) == {0, 1, 2, 3, 4, 5}
    # half the book is still yesterday's names, which is what a lambda of 0.5
    # means and is the whole reason turnover falls
    assert full[[0, 1, 2]].sum() == pytest.approx(0.5)


def test_the_cap_still_binds_after_blending():
    """A blend can concentrate: yesterday's name is also today's pick. The cap
    is re-applied, or `max_single_name` on the receipt would be a claim the
    engine stopped honouring exactly where it matters."""
    prev = np.zeros(8)
    prev[0] = 1.0
    idx, w, full = replay.blend_targets(prev, np.array([0]), np.array([1.0]),
                                        _pol(decay=0.5, max_single_name=0.2))
    assert w.max() <= 0.2 + 1e-12


def test_the_carried_state_is_the_TARGET_and_never_the_realised_book():
    """A drifted holding is a price move. If the decay rule blended against
    realised weights it would depend on returns, which makes it a momentum
    overlay rather than a turnover control."""
    prev = np.zeros(4)
    prev[0] = 1.0
    # `max_single_name=0` disables the cap so the blend arithmetic is the only
    # thing under test -- at the default 0.20 cap a one-name book is capped
    # before the blend can be read.
    _, _, full = replay.blend_targets(prev, np.array([1]), np.array([1.0]),
                                      _pol(decay=0.25, max_single_name=0.0))
    assert full[0] == pytest.approx(0.25)
    assert full[1] == pytest.approx(0.75)


# ------------------------------------------------------------ 3. the refusals

@pytest.mark.parametrize("bad", [1.0, 1.5, -0.1])
def test_a_decay_outside_zero_to_one_is_refused(bad):
    """At lambda = 1 the blend never admits a new target: the book freezes at
    its first formation and the signal stops mattering, which is a different
    strategy wearing this one's identity."""
    with pytest.raises(PolicyError, match="decay"):
        Policy(decay=bad)


def test_decay_is_orthogonal_to_the_zero_cost_refusal():
    """The two are independent axes and the cost refusal fires regardless."""
    with pytest.raises(PolicyError, match="zero transaction cost"):
        Policy(decay=0.5, transaction_cost_bps=0.0, slippage_bps=0.0)
    ok = Policy(decay=0.5, transaction_cost_bps=0.0, slippage_bps=0.0,
                zero_cost_diagnostic=True)
    assert ok.decay == 0.5


# ----------------------------------------- 4. the sweep pairs on FIELDS

def test_the_sweep_grid_always_contains_its_own_control():
    """A sweep whose control was optional would eventually be run without
    it."""
    from scripts.night_decay_sweep import COST_CELLS, DECAYS, build_grid
    grid = build_grid(signals=("mom_12_1",))
    assert len(grid) == len(COST_CELLS) * len(DECAYS)
    assert 0.0 in DECAYS
    for cell in COST_CELLS:
        twins = [p for p in grid if p.curve == cell.get("curve", "flat")
                 and p.decay == 0.0
                 and (cell.get("curve", "flat") != "flat"
                      or p.transaction_cost_bps == cell["transaction_cost_bps"])]
        assert len(twins) == 1, cell
    # and every cell is its own policy
    assert len({p.policy_id for p in grid}) == len(grid)


def test_the_sweep_pairs_each_cell_with_its_OWN_cost_cells_control():
    """Paired by policy FIELDS, not by position: a reordered result list must
    not pair a 50 bps cell with the 5 bps control, which is the whole content
    of the table."""
    from scripts.night_decay_sweep import table_rows

    class _R:
        def __init__(self, policy, cagr, turn):
            self.policy = policy
            self.metrics = {"status": "ok", "cagr_pct": cagr,
                            "turnover_annual": turn, "terminal_usd": 1.0}
            self.diagnostics = {}

    cheap0 = _R(Policy(decay=0.0, transaction_cost_bps=5.0, slippage_bps=1.0), 4.0, 10.0)
    cheap5 = _R(Policy(decay=0.5, transaction_cost_bps=5.0, slippage_bps=1.0), 5.0, 6.0)
    dear0 = _R(Policy(decay=0.0, transaction_cost_bps=50.0, slippage_bps=10.0), 1.0, 10.0)
    dear5 = _R(Policy(decay=0.5, transaction_cost_bps=50.0, slippage_bps=10.0), 3.0, 6.0)
    rows = {(r["cost_cell"], r["decay"]): r
            for r in table_rows([dear5, cheap0, dear0, cheap5])}   # shuffled
    assert rows[("flat_5+1bps", 0.5)]["vs_control_cagr_pp"] == 1.0
    assert rows[("flat_50+10bps", 0.5)]["vs_control_cagr_pp"] == 2.0
    assert rows[("flat_50+10bps", 0.5)]["control_decay0_cagr_pct"] == 1.0
    assert rows[("flat_5+1bps", 0.5)]["vs_control_turnover_ratio"] == 0.6
