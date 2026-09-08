"""X8 — the potential-universe header may not quote null 1 as validation.

WHAT HAPPENED. `learner/potential_universe.STATE_SEMANTICS` is copied verbatim
into the header of every potential-universe vintage, under
`whole_universe_refusals.state.semantics`. Its note read:

    "4 OOS states, k=4, p=0.000 vs 200 random partitions"

That p is **null 1** — the LEGACY within-month shuffle that `learner/nullbar.py`
records as MIS-SPECIFIED and that null 2 supersedes — quoted on its own. The
three-null adjudication (`N5_states_third_null.json`) is:

  * null 1 (legacy within-month shuffle) ....... p 0.000  clears
  * null 2 (persistence-preserving circular) ... p 1.000  **FAILS**
  * null 3 (name-path permutation) ............. p 0.005  clears
  * `final_verdict` ....... **CANNOT_DETERMINE / NULL_2_ALONE_DISAGREES**

and that receipt's own `demotion` block names this file and asks for this
correction in as many words: the text "quotes null 1 alone and reads as a
validated finding".

Standing canon is that **a null owes two tests**. A header that reports the one
null that clears, and not the one that supersedes it and fails, is a receipt
arguing a case. So the block now leads with `status: CANNOT_DETERMINE` and
`admissibility: INFORMATIONAL-ONLY`, carries all three nulls together, and this
file fails if either statement is removed or if a lone null-1 p reappears.

The assignment itself is separately inert on this surface — a tracker day file
cannot supply `STATE_FEATURES`, so `state.status` is CANNOT_DETERMINE on every
row anyway. That is exactly why the TEXT mattered: it was the only part of the
block a reader could mistake for evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from learner import potential_universe as PU

REPO = Path(__file__).resolve().parents[2]


# --------------------------------------------------------- the constant itself

def test_state_semantics_leads_with_cannot_determine_and_informational_only():
    s = PU.STATE_SEMANTICS
    assert s["status"] == "CANNOT_DETERMINE"
    assert "INFORMATIONAL-ONLY" in s["admissibility"]
    for forbidden in ("sizing", "admission", "routing"):
        assert forbidden in s["admissibility"], forbidden


def test_all_three_nulls_travel_together_and_the_failing_one_is_named():
    nulls = PU.STATE_SEMANTICS["nulls"]
    keys = list(nulls)
    assert sum(1 for k in keys if k.startswith("null_")) == 3, keys
    failing = [k for k, v in nulls.items() if "FAILS" in str(v)]
    assert len(failing) == 1 and "circular_shift" in failing[0], failing
    assert nulls["verdict"].startswith("CANNOT_DETERMINE")


def test_null_one_is_never_quoted_alone_as_validation():
    """The exact defect: a lone `p=0.000 vs 200 random partitions`."""
    note = PU.STATE_SEMANTICS["note"]
    assert "p=0.000 vs 200 random partitions" not in note
    assert "CANNOT_DETERMINE" in note
    # if a null-1 p is mentioned anywhere in the block it must be labelled
    # mis-specified/superseded, never as the finding.
    blob = json.dumps(PU.STATE_SEMANTICS)
    if "0.000" in blob:
        assert "MIS_SPECIFIED" in blob or "mis-specified" in blob


def test_the_descriptive_tag_is_labelled_as_one():
    assert "DESCRIPTIVE TAG" in PU.STATE_SEMANTICS["0"]


# ------------------------------------------- it agrees with its own receipt

def test_the_block_matches_the_third_null_receipt():
    p = REPO / PU.STATES_THIRD_NULL_RECEIPT
    if not p.is_file():
        pytest.skip(f"third-null receipt absent on this machine: {p}")
    fv = json.loads(p.read_text(encoding="utf-8"))["final_verdict"]
    assert fv["verdict"] == "CANNOT_DETERMINE"
    assert fv["family_case"] == "NULL_2_ALONE_DISAGREES"
    assert float(fv["p_null_1"]) == 0.0 and fv["clears_null_1"] is True
    assert float(fv["p_null_2"]) == 1.0 and fv["clears_null_2"] is False
    assert float(fv["p_null_3"]) == 0.005 and fv["clears_null_3"] is True

    nulls = PU.STATE_SEMANTICS["nulls"]
    assert "1.000" in nulls["null_2_persistence_preserving_circular_shift"]
    assert "0.005" in nulls["null_3_name_path_permutation"]


# ------------------------------------------------------- the VINTAGE header

def _vintage(monkeypatch, tmp_path):
    """One real vintage, built through `build_potential_universe`.

    Reuses the shapes `test_potential_universe.py` already exercises rather than
    a hand-built dict, because the point of the test is that the constant
    reaches the FILE a reader opens, not that a dict has keys.
    """
    from backend.tests import test_potential_universe as T  # noqa: PLC0415
    rows = [T._row("AAA"), T._row("BBB")]
    return T._build(rows)


def test_the_vintage_header_carries_the_verdict_beside_the_semantics(
        monkeypatch, tmp_path):
    pu = _vintage(monkeypatch, tmp_path)
    sem = pu["header"]["whole_universe_refusals"]["state"]["semantics"]
    assert sem["status"] == "CANNOT_DETERMINE"
    assert "INFORMATIONAL-ONLY" in sem["admissibility"]
    assert "p=0.000 vs 200 random partitions" not in json.dumps(sem)


def test_the_written_vintage_round_trips_the_verdict(tmp_path, monkeypatch):
    pu = _vintage(monkeypatch, tmp_path)
    path = PU.write_potential_universe(pu, out_dir=tmp_path)
    back = PU.read_potential_universe(path)
    sem = back["header"]["whole_universe_refusals"]["state"]["semantics"]
    assert sem["status"] == "CANNOT_DETERMINE"
    assert sem["nulls"]["verdict"].startswith("CANNOT_DETERMINE")
