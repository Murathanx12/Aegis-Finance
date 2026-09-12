"""B's closure: the power warning protects a null, not a negative.

The trap this file exists to keep shut is a specific one. TRIAL-DRAFT-B §4
computes an MDE of 7.17% against a published effect of 5.0%, finds the design
underpowered for its own prior BEFORE the read, and says a non-significant
result is CONDITIONAL rather than FAILED_VARIANT — "unless the point estimate
is <= 0". Both arms came back negative. A reader who quotes the first half of
that sentence and stops has turned a registered rule into a way of never
closing anything.

The real run-1 receipt is used as a fixture, so the numbers these tests assert
are the numbers on disk rather than numbers a test invented.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import night_b_verdict as B

RECEIPT = Path("backend/data/optimus/night_factory_2026-09-13/"
               "B_first_books_replay_run01.json")


@pytest.fixture(scope="module")
def payload():
    assert RECEIPT.is_file(), f"run 1's receipt is missing: {RECEIPT}"
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def out():
    return B.B_verdict(path=RECEIPT)


# --------------------------------------------------------------------------
# the numbers come off the receipt, not out of this file


def test_the_numbers_are_the_receipts_own(out, payload):
    books = {b["book"]: b for b in payload["books"]}
    for arm in B.ARMS:
        n = out["per_arm"][arm]["numbers"]
        assert n["pooled_mean"] == books[arm]["result"]["mean_bhar_excess_vs_twin"]
        assert n["pooled_t"] == books[arm]["result"]["nw_lag2_t"]
        assert n["confirm_mean"] == \
            books[arm]["by_era"]["2017-2024"]["mean_excess_net_monthly"]


def test_the_mean_is_found_under_either_of_the_two_names_it_is_filed_under():
    """`run_monthly` calls it `mean_excess_net_monthly`; the BHAR arms call it
    `mean_bhar_excess_vs_twin`. Reading only one returns `None` for half the
    receipt, and a `None` is not a zero."""
    assert B._mean({"mean_bhar_excess_vs_twin": -0.001}) == -0.001
    assert B._mean({"mean_excess_net_monthly": 0.002}) == 0.002
    assert B._mean({"n_blocks": 0}) is None
    assert B._mean(None) is None


def test_this_job_runs_no_backtest(out):
    assert "re-computes nothing" in out["runs_no_backtest"]
    assert out["reads_receipt"].endswith("B_first_books_replay_run01.json")


# --------------------------------------------------------------------------
# §5 applied


def test_both_arms_close_as_failed_variant_on_this_construction(out):
    assert out["arm_verdicts"] == {
        "insider_cluster_length_v1": "FAILED_VARIANT",
        "insider_cluster_same_day_v1": "FAILED_VARIANT"}
    for arm in B.ARMS:
        fired = out["per_arm"][arm]["verdict_block"]["clauses_fired"]
        assert any("clause 1" in c for c in fired)


def test_the_deciding_number_is_the_confirm_slice_not_the_pooled_mean(out):
    v = out["per_arm"]["insider_cluster_length_v1"]["verdict_block"]
    assert v["deciding_basis"] == "the 2017-2024 confirm slice"
    assert v["deciding_number"] == pytest.approx(-0.024084)


def test_the_power_warning_is_carried_and_is_explicitly_not_a_rescue(out):
    n = out["per_arm"]["insider_cluster_length_v1"]["numbers"]
    assert "CONDITIONAL, never FAILED_VARIANT" in n["power_warning"]
    why = out["per_arm"]["insider_cluster_length_v1"]["verdict_block"]["why"]
    assert "unless the point estimate is <= 0" in why
    assert "reporting its own sample size" in why


def test_a_positive_but_underpowered_arm_is_conditional_not_a_pass():
    """§4 calls this the modal case, and §5 calls it CONDITIONAL."""
    n = {"ran": True, "confirm_mean": 0.03, "confirm_t": 1.2,
         "pooled_mean": 0.02, "pooled_t": 1.0}
    v = B.arm_verdict(n, falsifier={"beats_non_cluster": False},
                      tradability={"fires": None, "why": "no count"})
    assert v["verdict"] == "CONDITIONAL"
    assert "UNDERPOWERED" in v["why"]


def test_clearing_the_mde_with_the_falsifier_alive_and_names_enough_is_promising():
    n = {"ran": True, "confirm_mean": 0.09, "confirm_t": 2.4}
    v = B.arm_verdict(n, falsifier={"beats_non_cluster": False},
                      tradability={"fires": False, "promote_gate_met": True,
                                   "why": "ok"})
    assert v["verdict"] == "PRODUCT_PROMISING"


def test_the_promote_gate_needs_the_name_count_and_will_not_guess():
    """An unmeasured tradability clause cannot be read as met."""
    n = {"ran": True, "confirm_mean": 0.09, "confirm_t": 2.4}
    v = B.arm_verdict(n, falsifier={"beats_non_cluster": False},
                      tradability={"fires": None, "why": "no count"})
    assert v["verdict"] == "CONDITIONAL"


def test_a_same_day_arm_that_wins_closes_the_book_whatever_the_length_arm_did():
    n = {"ran": True, "confirm_mean": 0.09, "confirm_t": 2.4}
    v = B.arm_verdict(n, falsifier={"beats_non_cluster": True},
                      tradability={"fires": False, "promote_gate_met": True,
                                   "why": "ok"})
    assert v["verdict"] == "FAILED_VARIANT"
    assert any("clause 2" in c for c in v["clauses_fired"])


def test_a_thin_year_closes_the_book_on_tradability():
    n = {"ran": True, "confirm_mean": 0.09, "confirm_t": 2.4,
         "names_per_year": {2017: 41, 2018: 7}}
    trad = B.tradability_clause(n)
    assert trad["status"] == "MEASURED" and trad["fires"] is True
    v = B.arm_verdict(n, falsifier={"beats_non_cluster": False}, tradability=trad)
    assert v["verdict"] == "FAILED_VARIANT"
    assert any("clause 3" in c for c in v["clauses_fired"])


def test_an_arm_that_did_not_run_is_not_graded():
    v = B.arm_verdict({"ran": False}, falsifier={}, tradability={})
    assert v["verdict"] == "CANNOT_DETERMINE"


# --------------------------------------------------------------------------
# the clause that could not be evaluated says so BY NAME


def test_the_tradability_clause_refuses_rather_than_passing_silently(out):
    for arm in B.ARMS:
        t = out["per_arm"][arm]["tradability_clause"]
        assert t["status"] == "CANNOT_DETERMINE"
        assert t["fires"] is None
        assert "no post-floor name count per year" in t["why"]
        assert out["per_arm"][arm]["verdict_block"]["unevaluated_clauses"]


# --------------------------------------------------------------------------
# the falsifier is a separate statement from the same-day arm's own verdict


def test_the_falsifier_survived_and_that_is_not_evidence_for_the_book(out):
    f = out["falsifier_status"]
    assert f["status"] == "MEASURED"
    assert f["beats_non_cluster"] is False
    assert "not evidence for the book" in f["why"]
    # and the same-day arm still closes AS A BOOK, on its own point estimate
    assert out["arm_verdicts"]["insider_cluster_same_day_v1"] == "FAILED_VARIANT"


def test_an_unreadable_same_day_arm_is_cannot_determine_not_survived():
    f = B.falsifier_status({"pooled_mean": None, "confirm_mean": None})
    assert f["status"] == "CANNOT_DETERMINE" and f["beats_non_cluster"] is None


# --------------------------------------------------------------------------
# one era is one era


def test_the_single_positive_era_is_named_and_refused_as_a_rescue(out, payload):
    books = {b["book"]: b for b in payload["books"]}
    got = out["per_arm"]["insider_cluster_length_v1"]["single_positive_era"]
    assert set(got["eras"]) == {"2000-2009"}
    assert got["eras"]["2000-2009"]["mean_excess_net_monthly"] == pytest.approx(
        books["insider_cluster_length_v1"]["by_era"]["2000-2009"]
        ["mean_excess_net_monthly"])
    assert "decides nothing" in got["reading"]
    assert "no 'best era' clause" in got["reading"]


def test_a_book_with_no_positive_era_reports_none():
    assert B.single_positive_era({"by_era": {"2017-2024": {
        "n_blocks": 9, "mean_excess_net_monthly": -0.01}}}) is None


# --------------------------------------------------------------------------
# a missing receipt is a refusal, not a verdict


def test_a_missing_receipt_refuses_rather_than_grading_nothing(tmp_path):
    out = B.B_verdict(path=tmp_path / "nope.json")
    assert out["ran"] is False
    assert out["verdict"].startswith("REFUSED")
    assert "does not produce the numbers it grades" in out["refused"]


# --------------------------------------------------------------------------
# what a FAILED_VARIANT here does and does not close


def test_the_closure_is_scoped_to_this_implementation(out):
    nxt = out["next_test"]
    assert "NEW REGISTRATION" in nxt
    assert "not insider clustering" in nxt
    assert "MORE BLOCKS" in nxt


def test_the_family_holm_block_travels_with_the_verdict(out, payload):
    assert out["family_holm_from_the_receipt"] == payload["holm"]
    assert out["family_holm_from_the_receipt"]["declared_family_size"] == 4


# --------------------------------------------------------------------------
# registration


def test_the_job_is_registered_in_the_night_factory():
    from scripts import night_factory_jobs as NFJ
    assert "B_verdict" in NFJ.JOBS
    assert NFJ.JOB_STAGES["B_verdict"] == "pnl"
    assert "B_verdict" not in NFJ.TIMEBOXED and "B_verdict" not in NFJ.RESUMABLE


def test_the_registered_constants_are_the_drafts_own():
    text = Path("docs/TRIALS/TRIAL-DRAFT-B-insider-cluster-length-v1.md").read_text(
        encoding="utf-8")
    assert "7.17%" in text and "5.0%" in text
    assert ">= 20/year to promote, < 10/year closes the book" in text
    assert B.DECLARED_MDE_PER_BLOCK == 0.0717
    assert B.PUBLISHED_EFFECT == 0.05
    assert B.PROMOTE_NAMES_PER_YEAR == 20 and B.CLOSE_NAMES_PER_YEAR == 10
    assert B.CONFIRM_SLICE == "2017-2024"
