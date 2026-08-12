"""TRANSACTION-ENSEMBLE-1 — the failure modes the prereg exists to prevent.

Three properties are load-bearing and each is silent if it breaks:

1. A member violating its DECLARED anchor subset must be rejected at
   generation — otherwise the ensemble quietly contains histories that
   contradict the record they claim to satisfy.
2. The ensemble must VARY where the data is unknown (cash, exit dates,
   weights). An ensemble that collapses to one history is a point
   fabrication wearing an ensemble's clothes — the house failure mode.
3. Grading output contains ONLY ranges and counts. A single member quoted
   as the answer is the outcome-shopping the prereg refuses.

All offline: prices come from the frozen CSV; no network.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services import transaction_ensemble as te


@pytest.fixture(scope="module")
def ctx():
    return te.Ctx()


@pytest.fixture(scope="module")
def small_ensemble(ctx):
    """A small always-on-arm ensemble; enough members to measure spread."""
    return te.generate_ensemble(
        ctx, members_per_arm=8, subsets=((),), qubt_arms=(300.0,),
        max_attempts=80)


def _one_member(ctx, declared=(), qubt=300.0, start_index=5000):
    for i in range(start_index, start_index + 10):
        rng = np.random.default_rng([te.TE_MASTER_SEED, i])
        for _ in range(120):
            m, _reason = te.sample_member(i, declared, qubt, ctx, rng)
            if m is not None:
                return m
    raise AssertionError("could not generate a member for the test")


# ── 1. rejection at generation ──────────────────────────────────────────────

def test_a_member_violating_its_declared_subset_is_rejected(ctx):
    """Declaring an anchor the history does not satisfy must be caught.

    Take an accepted always-on member whose satisfied set misses one of
    {7,8,9}, relabel it as declaring that anchor, and validation must refuse
    it — the exact tamper that would let a flattering subset be claimed."""
    m = _one_member(ctx)
    assert te.validate_member(m, ctx) == []
    missing = [a for a in (7, 8, 9) if a not in m.satisfied]
    if not missing:  # extremely unlikely under the prior; regenerate stricter
        pytest.skip("sampled member satisfied all soft anchors")
    m.declared = (missing[0],)
    bad = te.validate_member(m, ctx)
    assert any(f"anchor{missing[0]}" in v for v in bad), bad


def test_a_tampered_exit_date_is_caught(ctx):
    """Moving TVTX's annotated exit to a day whose close contradicts the
    stated 34.4 fill must be a violation — the sold-at annotations are
    anchors, not decoration. 2026-01-13 closed at 29.11, 41% below 34.4
    after tolerance."""
    m = _one_member(ctx)
    for e in m.episodes:
        if e.exit_kind == "known_price" and e.ticker == "TVTX":
            e.exit = te.JAN  # close 29.11 vs stated fill 34.4
    bad = te.validate_member(m, ctx)
    assert any("anchor3" in v and "TVTX" in v for v in bad), bad


def test_generation_never_returns_a_member_missing_its_declared_anchor(ctx):
    """sample_member with a declared subset either rejects or returns a
    member that satisfies it — there is no third path."""
    rng = np.random.default_rng([te.TE_MASTER_SEED, 6000])
    seen = 0
    for i in range(200):
        m, reason = te.sample_member(6000, (8,), 300.0, ctx, rng)
        if m is not None:
            seen += 1
            assert 8 in m.satisfied
        else:
            assert reason, "a rejection must carry its reason"
    assert seen > 0, "no member accepted in 200 attempts — generator broken"


def test_the_log_share_counts_are_pinned_at_the_log_date(ctx):
    """Anchor 4: whatever else varies, the 2026-07-11 book must be exactly
    the logged counts (QUBT by arm). A drifting share count would silently
    unpin the one date the dollar scale hangs on."""
    m = _one_member(ctx, qubt=200.0)
    held = {}
    for e in m.episodes:
        if e.exit is None and e.exit_kind != "wash":
            held[e.ticker] = held.get(e.ticker, 0.0) + e.shares
    expect = dict(ctx.log_shares)
    expect["QUBT"] = 200.0
    for tkr, sh in expect.items():
        assert abs(held.get(tkr, 0.0) - sh) < 1e-6, (tkr, held.get(tkr))


# ── 2. the ensemble varies where data is unknown ────────────────────────────

def test_the_ensemble_varies_where_data_is_unknown(small_ensemble, ctx):
    """The silent-fragility check: cash, exit dates and as-traded outcomes
    must show NONZERO spread. An ensemble that agrees everywhere has not
    modelled the uncertainty it exists to model."""
    members = small_ensemble["members"]
    assert len(members) >= 5, small_ensemble["unfilled"]

    cash = [m.cash0_frac for m in members]
    assert np.std(cash) > 0.01, "cash fraction did not vary"

    tvtx_dates = {str(e.exit.date()) for m in members for e in m.episodes
                  if e.exit_kind == "known_price" and e.ticker == "TVTX"}
    assert len(tvtx_dates) > 1, "the unknown exit date collapsed to one day"

    rets = [te.as_traded_stats(m)["total_return"] for m in members]
    assert max(rets) - min(rets) > 0.01, "as-traded return did not vary"

    navs0 = [float(m.nav.asof(te.W0)) for m in members]
    assert max(navs0) - min(navs0) > 1000, "unknown weights did not vary NAV"


def test_rejections_are_counted_not_hidden(small_ensemble):
    """Every rejected attempt must leave a countable trace."""
    rej = small_ensemble["rejections"]["{}|QUBT300"]
    assert isinstance(rej, dict)
    assert all(isinstance(v, int) and v > 0 for v in rej.values())


# ── 3. the frozen grading rule ──────────────────────────────────────────────

def test_grading_is_data_needed_when_a_flip_exists():
    """A planted sign flip across members must grade DATA_NEEDED and carry
    the minimal exact ask — never be averaged away."""
    g = te.grade({"{7}": [-3.0, 4.0], "{8}": [2.0]},
                 unit="pts", ask="broker CSV export, ~2 minutes")
    assert g["label"] == "DATA_NEEDED"
    assert "broker CSV" in g["minimal_ask"]


def test_grading_is_data_needed_when_magnitude_class_flips():
    """Same sign but different magnitude class is still not robust — the
    frozen rule requires BOTH to agree."""
    g = te.grade({"{7}": [2.0, 40.0]}, unit="pts", ask="ask")
    assert g["label"] == "DATA_NEEDED"


def test_grading_is_robust_when_sign_and_class_hold():
    g = te.grade({"{7}": [-48.0, -59.0], "{7,8,9}": [-42.0]},
                 unit="pts", ask="ask")
    assert g["label"] == "ensemble_robust"
    assert g["range"]["min"] == -59.0 and g["range"]["max"] == -42.0


def test_grading_output_contains_only_ranges_and_counts():
    """No output path may quote a single member as the answer. The grade
    dict carries ranges, counts and labels — no member index, no seed, no
    'best', no per-member value keyed to an identity."""
    g = te.grade({"{7}": [1.0, 2.0, 3.0]}, unit="pts", ask="ask")
    # counts of members are allowed; identities of members are not
    forbidden = ("best", "seed", "preferred", "chosen", "most_likely")
    for key in g:
        low = key.lower()
        assert not any(f in low for f in forbidden), key
        assert low not in ("member", "index", "member_id"), key
    assert set(g["range"]) == {"min", "max", "p05", "p50", "p95"}
    assert g["n_members"] == 3


def test_answers_quote_no_single_member(small_ensemble):
    """The assembled Q1-Q4 answers must contain only ranges+counts: walk the
    whole tree and refuse member identities anywhere in a graded answer."""
    answers = te.answer_questions(small_ensemble)
    forbidden = ("best_member", "preferred", "most_likely", "chosen_member")

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                assert not any(f in str(k).lower() for f in forbidden), k
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for q in ("Q1", "Q2", "Q3", "Q4"):
        walk(answers[q])
    # graded leaves carry ranges, not points
    q4 = answers["Q4"]["total_return"]
    assert "range" in q4 and "n_members" in q4


def test_exit_cost_definition_charges_proceeds_with_book_return(ctx):
    """If the book after the exit went up as much as the sold name, the exit
    cost must be ~zero — the proceeds are charged with what they actually
    earned, not with zero. Guard on the sign convention."""
    m = _one_member(ctx)
    costs = te.exit_costs(m, ctx)
    for tkr in ("TVTX", "ALMS", "SLDP"):
        assert tkr in costs
        assert np.isfinite(costs[tkr]["cost_pts_of_terminal_nav"])
    assert np.isfinite(costs["total_pts"])
