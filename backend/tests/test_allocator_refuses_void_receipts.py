"""A consumer that reads a superseded receipt is worse than one that refuses.

WHY THIS FILE EXISTS
====================
On 2026-09-05, B1 re-issued four tape receipts on a rebuilt panel and wrote a
`<name>.SUPERSEDED_BY.json` sidecar beside each sealed original (sealed receipts
are immutable — editing one is the tampering the chain exists to detect).

`learner/allocator.py` cites two of those four. Its `REV_ARM` sleeve had been
chosen at an excess of **+1.745pp/yr, t +0.73**; on the clean panel that same arm
measures **−7.71pp/yr, t −1.19**. The allocator is SHADOW_ONLY so nothing traded
on it, but it would have gone on reporting a positive sleeve from a void file,
and a stale number that still parses looks fresher than an error.

Two design choices are pinned here, and the second is the load-bearing one:

1. Supersession is **derived from the filesystem**, not from a hand-kept list in
   the consumer. A list would have to be updated by whoever re-issues a receipt,
   in a file they have no reason to open.
2. The allocator **refuses rather than following the sidecar** to the
   replacement. Repointing looks helpful and is not: which arm to cite from a
   re-issued receipt is a research decision, and here the answer changed sign.
   Auto-following would have re-derived a sleeve weight from evidence that
   refutes the sleeve.
"""

from __future__ import annotations

import json

import pytest

from learner import allocator as A


@pytest.fixture()
def repo(tmp_path):
    """A miniature repo holding one receipt, so the test never depends on the
    real tree's supersession state (which is exactly what will change next)."""
    for rel in A.RECEIPT_PATHS.values():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"arms": {"some_arm": {"excess_cagr": 0.0174}}}),
                     encoding="utf-8")
    return tmp_path


def _sidecar_for(repo, key, superseded_by="new_receipt_20260905.json"):
    p = repo / A.RECEIPT_PATHS[key]
    side = p.with_name(p.name + ".SUPERSEDED_BY.json")
    side.write_text(json.dumps({
        "artefact": "SUPERSEDED_BY_SIDECAR",
        "sealed_receipt": p.name,
        "superseded_by": superseded_by,
        "status": "VOID -- DO NOT QUOTE ANY NUMBER FROM THE SEALED RECEIPT",
        "reason": "re-issued on the rebuilt panel; the arm changed sign",
    }), encoding="utf-8")
    return side


def test_a_receipt_without_a_sidecar_is_read_normally(repo):
    receipts = A.load_receipts(repo=repo)
    got = A._extract(receipts, "revision_6m", "arms.some_arm.excess_cagr")
    assert got["basis"] != "REFUSED", got
    assert got["value"] == pytest.approx(0.0174)


def test_a_sidecar_makes_the_receipt_void_and_the_component_refuse(repo):
    _sidecar_for(repo, "revision_6m")
    receipts = A.load_receipts(repo=repo)

    void = receipts["revision_6m"][A.VOID_SENTINEL]
    assert void["superseded_by"] == "new_receipt_20260905.json"
    assert "changed sign" in void["reason"]

    got = A._extract(receipts, "revision_6m", "arms.some_arm.excess_cagr")
    assert got["basis"] == "REFUSED"
    assert got["value"] is None, "a void receipt must not yield a number"
    # The refusal has to be actionable: it names the void file, the replacement,
    # and the reason. "REFUSED" alone teaches the reader to skim refusals.
    assert "VOID" in got["reason"]
    assert "revision_6m_cohorts_20260904.json" in got["reason"]
    assert "new_receipt_20260905.json" in got["reason"]
    assert "re-choose the arm" in got["reason"]


def test_the_refusal_does_not_silently_follow_the_sidecar(repo):
    """The replacement's number must NOT appear in place of the void one."""
    _sidecar_for(repo, "revision_6m")
    (repo / "backend/data/optimus/tracker_backtest/new_receipt_20260905.json").write_text(
        json.dumps({"arms": {"some_arm": {"excess_cagr": -0.0771}}}), encoding="utf-8")
    receipts = A.load_receipts(repo=repo)
    got = A._extract(receipts, "revision_6m", "arms.some_arm.excess_cagr")
    assert got["value"] is None
    assert got["basis"] == "REFUSED"


def test_an_unreadable_sidecar_still_voids_the_receipt(repo):
    """Fail loud, not open: a corrupt sidecar means we cannot trust the receipt."""
    p = repo / A.RECEIPT_PATHS["toxic_short"]
    p.with_name(p.name + ".SUPERSEDED_BY.json").write_text("{ not json",
                                                           encoding="utf-8")
    receipts = A.load_receipts(repo=repo)
    assert receipts["toxic_short"][A.VOID_SENTINEL]["reason"] == \
        "sidecar present but unreadable"
    got = A._extract(receipts, "toxic_short", "arms.some_arm.excess_cagr")
    assert got["basis"] == "REFUSED"


def test_the_gate_label_says_void_not_unreadable():
    """A refusal that names the wrong cause sends the reader to the wrong place.

    The first version of this change printed `NOT_DEPLOYABLE_RECEIPT_UNREADABLE`
    for a superseded receipt. The file is perfectly readable — its NUMBER is
    wrong. Someone reading that gate would go hunting for a missing file sitting
    right there, and would not learn that the sleeve's evidence had been
    refuted. Three distinct causes, three labels.
    """
    unreadable = A.refused("receipt unreadable: some/path.json")
    void = A.refused("receipt VOID -- superseded: a.json -> b.json (reason)")
    absent = A.refused("key absent from receipt: some/path.json#arms.x")
    fine = A.cited(0.01, "revision_6m", "arms.x.excess_cagr")

    assert A._refusal_gate(void, fine) == "NOT_DEPLOYABLE_RECEIPT_VOID_SUPERSEDED"
    assert A._refusal_gate(absent, fine) == "NOT_DEPLOYABLE_RECEIPT_KEY_ABSENT"
    assert A._refusal_gate(unreadable, fine) == "NOT_DEPLOYABLE_RECEIPT_UNREADABLE"
    # VOID wins when several causes coincide: it is the one that means the
    # evidence changed, which is the finding a reader must not miss.
    assert A._refusal_gate(unreadable, void) == "NOT_DEPLOYABLE_RECEIPT_VOID_SUPERSEDED"


def test_supersession_is_derived_not_declared():
    """No hand-kept void list may exist in the module.

    If one is ever added, whoever re-issues a receipt has to remember to edit a
    consumer they have no reason to open -- and that is how the sidecars would
    stop being honoured.
    """
    src = (A.__file__ and open(A.__file__, encoding="utf-8").read()) or ""
    assert "SUPERSEDED_BY.json" in src, "the sidecar convention must be derived"
    for banned in ("VOID_RECEIPTS = ", "VOID_LIST", "KNOWN_VOID"):
        assert banned not in src, f"{banned} is a hand-kept list; derive instead"


@pytest.mark.parametrize("key", ["revision_6m", "toxic_short"])
def test_the_real_tree_has_these_two_void_right_now(key):
    """Documents today's actual state -- and is allowed to change.

    When B1's replacements are adopted and `RECEIPT_PATHS` is repointed, this
    assertion flips to 'not void', which is the signal to update it. It exists so
    the flip is deliberate rather than unnoticed.
    """
    receipts = A.load_receipts()
    payload = receipts.get(key)
    if payload is None:
        pytest.skip(f"{key} receipt absent on this machine")
    void = payload.get(A.VOID_SENTINEL)
    assert void is not None, (
        f"{A.RECEIPT_PATHS[key]} is no longer superseded -- if RECEIPT_PATHS was "
        "repointed at the re-issued receipt, update this test and confirm the "
        "sleeve's arm was re-chosen on the new evidence rather than assumed")
    assert void["superseded_by"].endswith("_20260905.json")
