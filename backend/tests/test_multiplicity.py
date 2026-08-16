"""A holdout window has a finite number of chances, and nothing was counting them.

`slice_register` refuses a confirmation whose LINEAGE read the calendar. Correct
for leakage, silent on family-wise error: fifty unrelated mechanisms confirming
on 2020-2026 share no lineage, so every one of those windows reads clean, and
~2.5 of them are "confirmed" under the null.
"""

from __future__ import annotations

import pytest

from backend.services.research_gym.multiplicity import (ConfirmationBudget,
                                                        MultiplicityRefusal,
                                                        window_id)

W = window_id(universe="us_equity", period="2020-06-01..2026-07-17",
              outcome="excess_return_20d")


@pytest.fixture()
def cb(tmp_path):
    return ConfirmationBudget(tmp_path / "budget.jsonl")


# ── the thing that was missing ─────────────────────────────────────────────
def test_the_window_runs_out_of_chances(cb):
    cb.declare_budget(W, budget=5, declared_by="test")
    for i in range(5):
        cb.reserve(W, trial=f"M{i}", hypothesis=f"mechanism {i}")
    assert cb.remaining(W) == 0
    with pytest.raises(MultiplicityRefusal, match="SPENT"):
        cb.reserve(W, trial="M5", hypothesis="mechanism 5")


def test_the_refusal_names_what_is_left_rather_than_only_saying_no(cb):
    cb.declare_budget(W, budget=1, declared_by="test")
    cb.reserve(W, trial="M0", hypothesis="h")
    with pytest.raises(MultiplicityRefusal) as e:
        cb.reserve(W, trial="M1", hypothesis="h")
    msg = str(e.value)
    assert "forward time" in msg and "foreign market" in msg


def test_fifty_unrelated_mechanisms_is_exactly_the_case_this_exists_for(cb):
    """None of these shares a lineage, so slice_register would pass all fifty."""
    cb.declare_budget(W, budget=5, declared_by="test")
    taken = 0
    for i in range(50):
        try:
            cb.reserve(W, trial=f"M{i}", hypothesis=f"unrelated {i}")
            taken += 1
        except MultiplicityRefusal:
            break
    assert taken == 5


# ── the family cannot be defined after the fact ────────────────────────────
def test_a_result_with_no_reservation_is_refused(cb):
    cb.declare_budget(W, budget=5, declared_by="test")
    with pytest.raises(MultiplicityRefusal, match="no reservation"):
        cb.record_result(W, trial="M0", hypothesis="h", p_value=0.01)


def test_reserving_requires_a_budget_declared_first(cb):
    with pytest.raises(MultiplicityRefusal, match="no confirmation budget"):
        cb.reserve(W, trial="M0", hypothesis="h")


def test_the_budget_cannot_be_raised_once_a_result_exists(cb):
    """A budget raised to accommodate a sixth test is the multiple-testing
    problem with a ledger entry."""
    cb.declare_budget(W, budget=2, declared_by="test")
    cb.reserve(W, trial="M0", hypothesis="h")
    cb.record_result(W, trial="M0", hypothesis="h", p_value=0.20)
    with pytest.raises(MultiplicityRefusal, match="after seeing the outcomes"):
        cb.declare_budget(W, budget=20, declared_by="test")


def test_the_budget_may_still_be_corrected_before_any_result(cb):
    """Before anything is scored there is nothing to fit the budget to, so a
    correction is a correction rather than a choice."""
    cb.declare_budget(W, budget=2, declared_by="test")
    cb.reserve(W, trial="M0", hypothesis="h")
    cb.declare_budget(W, budget=5, declared_by="test", note="rescoped")
    assert cb.budget_of(W).budget == 5


def test_the_same_hypothesis_cannot_take_two_slots(cb):
    cb.declare_budget(W, budget=5, declared_by="test")
    cb.reserve(W, trial="M0", hypothesis="h")
    with pytest.raises(MultiplicityRefusal, match="not a second chance"):
        cb.reserve(W, trial="M0", hypothesis="h")


def test_one_reservation_cannot_carry_two_p_values(cb):
    cb.declare_budget(W, budget=5, declared_by="test")
    cb.reserve(W, trial="M0", hypothesis="h")
    cb.record_result(W, trial="M0", hypothesis="h", p_value=0.04)
    with pytest.raises(MultiplicityRefusal, match="second test"):
        cb.record_result(W, trial="M0", hypothesis="h", p_value=0.01)


# ── Holm ───────────────────────────────────────────────────────────────────
def test_holm_kills_the_marginal_winners_that_naive_testing_would_keep(cb):
    """Five mechanisms, three under 0.05 the naive way. This is the number the
    ledger exists to change."""
    cb.declare_budget(W, budget=5, declared_by="test")
    for i, p in enumerate([0.004, 0.02, 0.04, 0.30, 0.60]):
        cb.reserve(W, trial=f"M{i}", hypothesis=f"h{i}")
        cb.record_result(W, trial=f"M{i}", hypothesis=f"h{i}", p_value=p)
    res = cb.holm(W)
    assert res["naive_n_below_alpha"] == 3
    assert res["n_rejected"] == 1, "only p=0.004 clears 0.05/5"
    assert res["decisions"][0]["rejected"] is True


def test_holm_steps_down_so_a_failure_carries_forward(cb):
    """Once one fails, everything after it fails regardless of its own p.
    Reporting the raw per-rank comparison without the carry-forward is the most
    common way Holm is mis-applied, and it is anti-conservative."""
    cb.declare_budget(W, budget=3, declared_by="test")
    for i, p in enumerate([0.30, 0.0001, 0.0001]):
        cb.reserve(W, trial=f"M{i}", hypothesis=f"h{i}")
        cb.record_result(W, trial=f"M{i}", hypothesis=f"h{i}", p_value=p)
    res = cb.holm(W)
    ranked = res["decisions"]
    assert ranked[0]["p_value"] == 0.0001 and ranked[0]["rejected"] is True
    assert ranked[1]["p_value"] == 0.0001 and ranked[1]["rejected"] is True
    assert ranked[2]["p_value"] == 0.30 and ranked[2]["rejected"] is False


def test_m_is_the_declared_budget_not_the_number_run(cb):
    """Reserve five, run one. Using m=1 would make a p=0.04 a discovery; the
    budget was declared at five and that is what the window was charged."""
    cb.declare_budget(W, budget=5, declared_by="test")
    for i in range(5):
        cb.reserve(W, trial=f"M{i}", hypothesis=f"h{i}")
    cb.record_result(W, trial="M0", hypothesis="h0", p_value=0.04)
    res = cb.holm(W)
    assert res["m_used"] == 5
    assert res["n_rejected"] == 0
    assert res["naive_n_below_alpha"] == 1


def test_holm_beats_bonferroni_where_it_can(cb):
    """Two strong results: Bonferroni would test both at 0.05/2 = 0.025; Holm
    tests the second at 0.05/1. Same guarantee, strictly more power, so there
    is no reason to ship the weaker procedure."""
    cb.declare_budget(W, budget=2, declared_by="test")
    for i, p in enumerate([0.02, 0.04]):
        cb.reserve(W, trial=f"M{i}", hypothesis=f"h{i}")
        cb.record_result(W, trial=f"M{i}", hypothesis=f"h{i}", p_value=p)
    res = cb.holm(W)
    assert res["n_rejected"] == 2
    assert res["decisions"][1]["holm_threshold"] == pytest.approx(0.05)


def test_holm_needs_a_budget(cb):
    with pytest.raises(MultiplicityRefusal, match="nothing to control"):
        cb.holm(W)


# ── the inputs a later deflated-Sharpe calculation needs ──────────────────
def test_variants_tried_is_carried_because_it_cannot_be_reconstructed(cb):
    cb.declare_budget(W, budget=5, declared_by="test")
    cb.reserve(W, trial="M0", hypothesis="h", variants_tried=412)
    cb.record_result(W, trial="M0", hypothesis="h", p_value=0.001)
    assert cb.holm(W)["decisions"][0]["variants_tried"] == 412


def test_the_outcome_is_part_of_the_window_identity(cb):
    """Max drawdown and terminal return on the same dates are different
    questions with different power; spending one does not spend the other."""
    a = window_id(universe="us", period="2020..2026", outcome="max_drawdown")
    b = window_id(universe="us", period="2020..2026", outcome="terminal_return")
    assert a != b
    cb.declare_budget(a, budget=1, declared_by="t")
    cb.reserve(a, trial="M", hypothesis="h")
    with pytest.raises(MultiplicityRefusal, match="SPENT"):
        cb.reserve(a, trial="M2", hypothesis="h2")
    cb.declare_budget(b, budget=1, declared_by="t")
    cb.reserve(b, trial="M2", hypothesis="h2")      # a different question


def test_the_report_shows_what_the_ledger_bought(cb):
    cb.declare_budget(W, budget=5, declared_by="test")
    for i, p in enumerate([0.01, 0.03, 0.045]):
        cb.reserve(W, trial=f"M{i}", hypothesis=f"h{i}")
        cb.record_result(W, trial=f"M{i}", hypothesis=f"h{i}", p_value=p)
    res = cb.holm(W)
    # p=0.01 meets 0.05/5 exactly and survives; the other two do not. Three
    # "significant" results become one, which is the number this ledger exists
    # to produce.
    assert res["naive_n_below_alpha"] == 3 and res["n_rejected"] == 1
    assert "without family-wise control" in res["note"]


def test_the_ledger_survives_a_reload(cb, tmp_path):
    cb.declare_budget(W, budget=3, declared_by="test")
    cb.reserve(W, trial="M0", hypothesis="h")
    cb.record_result(W, trial="M0", hypothesis="h", p_value=0.02)
    again = ConfirmationBudget(tmp_path / "budget.jsonl")
    assert again.remaining(W) == 2
    assert again.holm(W)["results_recorded"] == 1


# ── SCREEN vs EXPORT: two purposes, two criteria ──────────────────────────
def test_holm_at_five_would_have_made_the_gym_impossible(cb):
    """The defect the split fixes. A screen of 200 candidates with 60 genuine
    effects passes ONE under Holm-at-the-budget and sixty-odd under FDR. A
    machine that cannot pass its own screen produces no candidates, and then
    the kill machinery IS the programme."""
    W2 = window_id(universe="gym", period="2006..2019", outcome="ic")
    cb.declare_budget(W2, budget=200, declared_by="t", purpose="SCREEN")
    # 60 real effects at p=0.001, 140 nulls spread over (0,1]
    ps = [0.001] * 60 + [0.05 + 0.0068 * i for i in range(140)]
    for i, p in enumerate(ps):
        cb.reserve(W2, trial=f"C{i}", hypothesis=f"h{i}")
        cb.record_result(W2, trial=f"C{i}", hypothesis=f"h{i}", p_value=min(p, 1.0))
    bh = cb.decide(W2)
    assert bh["criterion"] == "BH_FDR"
    assert bh["n_rejected"] >= 60

    holm = cb.holm(W2)
    assert holm["n_rejected"] < bh["n_rejected"], (
        "the whole reason for the split")


def test_a_screen_says_out_loud_how_many_of_its_finds_are_expected_false(cb):
    W2 = window_id(universe="gym", period="2006..2019", outcome="ic")
    cb.declare_budget(W2, budget=50, declared_by="t", purpose="SCREEN", rate=0.10)
    for i, p in enumerate([0.0001] * 20):
        cb.reserve(W2, trial=f"C{i}", hypothesis=f"h{i}")
        cb.record_result(W2, trial=f"C{i}", hypothesis=f"h{i}", p_value=p)
    r = cb.decide(W2)
    assert r["expected_false_among_rejected"] == pytest.approx(2.0)
    assert "may NOT be reported as a confirmation" in r["note"]


def test_bh_steps_UP_where_holm_steps_down(cb):
    """Opposite directions, and it is the whole difference: Holm stops at the
    first failure so one weak result blocks everything behind it; BH finds the
    LAST passing rank and rejects everything at or below it."""
    W2 = window_id(universe="gym", period="2006..2019", outcome="ic")
    cb.declare_budget(W2, budget=10, declared_by="t", purpose="SCREEN", rate=0.10)
    for i, p in enumerate([0.001, 0.02, 0.03, 0.04]):
        cb.reserve(W2, trial=f"C{i}", hypothesis=f"h{i}")
        cb.record_result(W2, trial=f"C{i}", hypothesis=f"h{i}", p_value=p)
    assert cb.decide(W2)["n_rejected"] == 4
    assert cb.holm(W2)["n_rejected"] == 1


def test_the_default_purpose_is_the_strict_one(cb):
    """A budget declared without thinking gets FWER. The safe direction for a
    default is the one that refuses more."""
    cb.declare_budget(W, budget=5, declared_by="t")
    assert cb.budget_of(W).purpose == "EXPORT"
    assert cb.decide(W)["criterion"] == "HOLM_FWER"


def test_an_undeclared_purpose_is_refused_rather_than_guessed(cb):
    with pytest.raises(MultiplicityRefusal, match="not one of"):
        cb.declare_budget(W, budget=5, declared_by="t", purpose="MAYBE")


def test_the_criterion_travels_with_every_decision(cb):
    """So a screen result cannot be quoted as a confirmation three sessions
    later, when both are just a dict with `n_rejected` in it."""
    cb.declare_budget(W, budget=3, declared_by="t")
    cb.reserve(W, trial="M", hypothesis="h")
    cb.record_result(W, trial="M", hypothesis="h", p_value=0.001)
    d = cb.decide(W)
    assert d["criterion"] == "HOLM_FWER" and d["purpose"] == "EXPORT"


def test_fdr_uses_tests_RUN_and_fwer_uses_the_DECLARED_budget(cb):
    """Different m on purpose. FDR is a property of the discovery set actually
    produced; a screen's budget is a capacity limit, not a family definition.
    FWER's family was fixed in advance and that is what it must be charged."""
    Ws = window_id(universe="gym", period="p", outcome="o")
    cb.declare_budget(Ws, budget=100, declared_by="t", purpose="SCREEN")
    cb.declare_budget(W, budget=100, declared_by="t", purpose="EXPORT")
    for wid in (Ws, W):
        for i in range(3):
            cb.reserve(wid, trial=f"C{i}", hypothesis=f"h{i}")
            cb.record_result(wid, trial=f"C{i}", hypothesis=f"h{i}",
                             p_value=0.001)
    assert cb.decide(Ws)["m_used"] == 3
    assert cb.decide(W)["m_used"] == 100
