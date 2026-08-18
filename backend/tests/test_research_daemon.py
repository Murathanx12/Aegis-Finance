"""The daemon's contract: refuse at submission, freeze the priority, count your own m.

Three properties carry the whole design, and each is tested against the way it
would actually fail rather than the way it is described:

  * a reserved window is refused BEFORE the data is read, because a refusal at
    analysis time is a post-mortem;
  * priority is fixed at submission and there is no path to change it, because
    a ranking that can move after the outcome is a story about why the winners
    were always the priority;
  * `m` is counted by the machine that runs the tests, because "m = tests RUN"
    is only true if something is counting.
"""

from __future__ import annotations

import json

import pytest

from backend.services import research_daemon as RD


def _job(hid="H1", **kw) -> RD.HypothesisJob:
    base = dict(
        hypothesis_id=hid, question="does X predict Y?",
        universe="us_equity_top1500", outcome="max_drawdown",
        start="2010-01-01", end="2015-12-31",
        n_date_blocks=72, se_per_block=0.010, expected_effect=0.030,
        effect_units="annualised", cost_usd=2.0, p_resolves=0.8,
        decision_value=0.6)
    base.update(kw)
    return RD.HypothesisJob(**base)


# ── 1. reserved windows are unreachable AT SUBMISSION ──────────────────────
def _reserved():
    return [RD.ReservedWindow(name="M6-CONFIRM", universe="us_equity_top1500",
                              outcome="max_drawdown", start="2020-06-01",
                              end="2026-07-31")]


def test_a_job_touching_a_reserved_window_is_refused_at_submission():
    """The most important line in the module. At analysis time the window has
    already been read and is gone whatever anyone then decides."""
    d = RD.ResearchDaemon(reserved=_reserved())
    with pytest.raises(RD.JobRefused, match="RESERVED"):
        d.submit(_job(start="2019-01-01", end="2021-01-01"))
    assert d.submissions() == [], "a refused job must not enter the queue"


@pytest.mark.parametrize("start,end", [
    ("2020-05-01", "2020-06-02"),   # overlaps the front edge
    ("2026-07-01", "2027-01-01"),   # overlaps the back edge
    ("2021-01-01", "2022-01-01"),   # entirely inside
    ("2019-01-01", "2027-01-01"),   # entirely spanning
])
def test_every_kind_of_overlap_is_caught(start, end):
    d = RD.ResearchDaemon(reserved=_reserved())
    with pytest.raises(RD.JobRefused):
        d.submit(_job(start=start, end=end))


def test_a_job_beside_the_window_is_allowed():
    d = RD.ResearchDaemon(reserved=_reserved())
    assert d.submit(_job(start="2010-01-01", end="2020-05-31"))


def test_a_different_outcome_on_the_same_dates_is_a_different_window():
    """§59: drawdown and terminal return on identical dates are different
    questions with different power, and spending one does not spend the other."""
    d = RD.ResearchDaemon(reserved=_reserved())
    assert d.submit(_job(outcome="terminal_return", start="2021-01-01",
                         end="2022-01-01"))


def test_unreadable_reserved_windows_refuse_rather_than_reading_as_none(tmp_path):
    """An empty list means 'nothing is reserved', which is the most permissive
    answer available and the one a missing input must never produce."""
    p = tmp_path / "reserved_windows.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(RD.JobRefused, match="most permissive"):
        RD.load_reserved_windows(p)


def test_an_absent_reserved_file_is_an_empty_list_not_a_refusal(tmp_path):
    """Absent is a legitimate starting state; unreadable is not."""
    assert RD.load_reserved_windows(tmp_path / "nope.json") == []


# ── 2. priority is frozen at submission ────────────────────────────────────
def test_priority_is_fixed_before_any_result_exists():
    d = RD.ResearchDaemon()
    sub = d.submit(_job())
    before = sub.priority
    d.record_result("H1", p_value=0.001, observed_effect=0.05)
    assert d.get("H1").priority == before
    assert d.get("H1").priority_terms["fixed_at"].startswith("SUBMISSION")


def test_there_is_no_path_to_reprioritise():
    """Kept as a NAMED refusal rather than simply omitted, so the absence is
    deliberate and discoverable instead of looking like an oversight."""
    d = RD.ResearchDaemon()
    d.submit(_job())
    with pytest.raises(RD.JobRefused, match="fixed at submission"):
        d.reprioritise("H1")


def test_a_second_result_for_one_submission_is_refused():
    """Either a re-run reported as new evidence, or an m that stopped counting."""
    d = RD.ResearchDaemon()
    d.submit(_job())
    d.record_result("H1", p_value=0.01)
    with pytest.raises(RD.JobRefused, match="already has a result"):
        d.record_result("H1", p_value=0.001)


def test_resubmitting_one_hypothesis_is_refused():
    d = RD.ResearchDaemon()
    d.submit(_job())
    with pytest.raises(RD.JobRefused, match="already submitted"):
        d.submit(_job())


def test_priority_is_reproducible_from_the_submission_alone():
    """What makes 'the priority was fixed beforehand' checkable rather than an
    assurance: every term is on the job."""
    job = _job()
    screen = RD.power_screen(job)
    assert RD.bandit_priority(job, screen)["priority"] == pytest.approx(
        RD.bandit_priority(job, screen)["priority"])
    d = RD.ResearchDaemon()
    assert d.submit(job).priority == pytest.approx(
        RD.bandit_priority(job, screen)["priority"])


def test_a_cheaper_job_with_equal_everything_else_ranks_higher():
    d = RD.ResearchDaemon()
    d.submit(_job("CHEAP", cost_usd=1.0))
    d.submit(_job("DEAR", cost_usd=40.0))
    assert [s.job.hypothesis_id for s in d.queue()] == ["CHEAP", "DEAR"]


def test_a_free_job_does_not_rank_infinitely():
    """'It costs nothing' is a reason to run something, not a reason to run it
    before everything else forever."""
    d = RD.ResearchDaemon()
    sub = d.submit(_job("FREE", cost_usd=0.0, cost_minutes=0.0))
    assert sub.priority < float("inf")
    assert sub.priority_terms["terms"]["cost_units"] >= 0.25


# ── 3. underpowered is SHELVED, never rejected ─────────────────────────────
def test_an_underpowered_job_is_shelved_not_rejected():
    """§19's asymmetry trap: an underpowered null feels like a kill. A
    graveyard that absorbs everything the calendar could not resolve is how a
    programme talks itself out of its own good ideas."""
    d = RD.ResearchDaemon()
    sub = d.submit(_job("WEAK", expected_effect=0.001, n_date_blocks=24))
    assert sub.state == RD.SHELF
    assert sub.state != RD.REJECTED
    assert "Underpowered is NOT false" in " ".join(sub.notes)


def test_a_shelved_job_still_ranks_below_a_powered_one_but_still_ranks():
    """Damped, not zeroed — which is what keeps SHELF from behaving like a
    graveyard with extra steps."""
    d = RD.ResearchDaemon()
    d.submit(_job("STRONG"))
    d.submit(_job("WEAK", expected_effect=0.001, n_date_blocks=24))
    ids = [s.job.hypothesis_id for s in d.queue()]
    assert ids == ["STRONG", "WEAK"]
    assert d.get("WEAK").priority > 0.0


def test_more_date_blocks_can_bring_a_shelved_hypothesis_back():
    """The point of keeping it: the same question resolves once the calendar
    has supplied enough blocks."""
    weak = RD.power_screen(_job(expected_effect=0.004, n_date_blocks=36))
    strong = RD.power_screen(_job(expected_effect=0.004, n_date_blocks=400))
    assert weak["powered"] is False and strong["powered"] is True
    assert strong["mde"] < weak["mde"]


# ── 4. the power screen refuses missing inputs ─────────────────────────────
def test_a_row_count_where_date_blocks_belong_cannot_be_silently_accepted():
    """Pairs and panels explode rows without adding information (§58). The
    field is named so supplying a row count requires lying about what it is —
    and one block is refused outright."""
    with pytest.raises(RD.JobRefused, match="DATE BLOCKS"):
        RD.power_screen(_job(n_date_blocks=1))


def test_no_standard_error_means_no_mde_and_therefore_no_job():
    with pytest.raises(RD.JobRefused, match="no MDE"):
        RD.power_screen(_job(se_per_block=0.0))


def test_the_mde_shrinks_with_the_square_root_of_the_blocks():
    a = RD.power_screen(_job(n_date_blocks=100))["mde"]
    b = RD.power_screen(_job(n_date_blocks=400))["mde"]
    assert a / b == pytest.approx(2.0, rel=1e-6)


def test_the_daemon_and_the_grader_share_one_quantile_table():
    """Two power gates disagreeing about z_{0.975} is a difference that never
    shows up as an error — only as two modules quietly disagreeing about what
    is detectable."""
    from backend.services import iif1_grader as G
    assert RD.Z_STD_NORMAL is G.Z_STD_NORMAL


# ── 5. a corpse is confronted by name, in a sentence ───────────────────────
def test_naming_a_corpse_without_a_sentence_is_refused():
    d = RD.ResearchDaemon()
    with pytest.raises(RD.JobRefused, match="a sentence, not a feeling"):
        d.submit(_job(parent_corpse_ids=("G5",), distinct_claim="different"))


def test_a_real_distinct_claim_is_accepted():
    d = RD.ResearchDaemon()
    sub = d.submit(_job(
        parent_corpse_ids=("G5-a", "G5-b", "G5-c"),
        distinct_claim=("the unit is relative capital allocation between two "
                        "securities net of costs, which G5's conditional-shape "
                        "tests never scored")))
    assert sub.job.parent_corpse_ids


def test_a_job_naming_no_corpse_needs_no_sentence():
    assert RD.ResearchDaemon().submit(_job())


# ── 6. m is counted by the machine that ran the tests ──────────────────────
def test_m_is_the_daemons_own_running_test_count():
    d = RD.ResearchDaemon()
    for i in range(4):
        d.submit(_job(f"H{i}"))
    assert d.tests_run() == 0
    d.record_result("H0", p_value=0.2)
    d.record_result("H1", p_value=0.01)
    assert d.tests_run() == 2
    assert d.nightly_receipt()["multiplicity_m"] == 2
    assert d.nightly_receipt()["m_basis"] == "COUNTED_BY_THE_DAEMON_THAT_RAN_THEM"


def test_m_counts_the_boring_results_too():
    """The failure this prevents: counting only the interesting results, which
    is exactly the m that makes a screen look better than it is."""
    d = RD.ResearchDaemon()
    for i in range(3):
        d.submit(_job(f"H{i}"))
    for i in range(3):
        d.record_result(f"H{i}", p_value=0.9)     # all null, all counted
    assert d.tests_run() == 3


# ── 7. one decide() entry point ────────────────────────────────────────────
def test_deciding_without_a_declared_window_is_refused():
    """A daemon that decided without a window would be spending an error rate
    nobody reserved."""
    d = RD.ResearchDaemon()
    with pytest.raises(RD.JobRefused, match="nothing to control"):
        d.decide()


def test_decide_delegates_and_never_picks_a_criterion_itself():
    """§63: choosing between BH and Holm at the call site is choosing the error
    criterion after seeing the p-values. Asserted structurally — the daemon's
    own source must not name either procedure."""
    import inspect
    src = inspect.getsource(RD.ResearchDaemon.decide)
    body = src.split('"""')[2]
    for forbidden in ("benjamini", "holm", "bonferroni"):
        assert forbidden not in body.lower(), (
            f"decide() names {forbidden!r} in its body; the criterion belongs "
            f"to the window's declared purpose, not to this call site")

    class _Budget:
        def __init__(self):
            self.seen = []

        def decide(self, wid):
            self.seen.append(wid)
            return {"criterion": "BH_FDR", "window_id": wid}

    b = _Budget()
    d = RD.ResearchDaemon(window_id="u|p|o", budget=b)
    assert d.decide()["window_id"] == "u|p|o"
    assert b.seen == ["u|p|o"]


# ── 8. the nightly receipt ─────────────────────────────────────────────────
def test_the_receipt_reports_the_states_and_the_queue(tmp_path):
    d = RD.ResearchDaemon(reserved=_reserved())
    d.submit(_job("A"))
    d.submit(_job("B", expected_effect=0.0005, n_date_blocks=24))
    d.record_result("A", p_value=0.03)
    rec = d.nightly_receipt()
    assert rec["submitted"] == 2 and rec["tests_run"] == 1
    assert rec["shelved_underpowered"] == 1
    assert rec["queue_depth"] == 1
    assert rec["reserved_windows"] == ["M6-CONFIRM"]
    p = d.write_receipt(out_dir=tmp_path)
    assert json.loads(p.read_text(encoding="utf-8"))["daemon"] == RD.DAEMON


def test_a_second_receipt_on_one_date_does_not_overwrite_the_first(tmp_path):
    d = RD.ResearchDaemon()
    d.submit(_job())
    a = d.write_receipt(out_dir=tmp_path)
    b = d.write_receipt(out_dir=tmp_path)
    assert a != b and a.exists() and b.exists()
