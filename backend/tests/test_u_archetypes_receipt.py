"""X9 for lane U: the numbers in `BUILD_2026-09-08_R3_ARCHETYPES.md` are pinned
to `U_archetypes_nim.json`.

THE RECEIPT WINS. Every assertion reads the number out of the receipt first and
then requires the prose to carry it, so the doc cannot drift and a re-run with
different numbers fails here rather than quietly disagreeing with the paragraph
beside it. This is the rule `test_x9_doc_numbers.py` was written for after eight
of our own documents were found disagreeing with the receipts they cited.

The receipt is a committed JSON artefact, but the run needs a network endpoint,
so an environment without it SKIPS rather than fails -- and the skip names the
missing file, because a silent pass and a real pass read identically.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RECEIPT = REPO / "backend/data/optimus/archetypes/U_archetypes_nim.json"
DOC = REPO / "docs/BUILD_2026-09-08_R3_ARCHETYPES.md"


def _receipt() -> dict:
    if not RECEIPT.is_file():
        pytest.skip(f"receipt absent on this machine: {RECEIPT}")
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def _doc() -> str:
    if not DOC.is_file():
        pytest.skip(f"doc absent: {DOC}")
    return DOC.read_text(encoding="utf-8")


def _has_number(text: str, value: int) -> bool:
    """Match the integer with or without thousands separators."""
    plain = str(value)
    grouped = f"{value:,}"
    return bool(re.search(rf"(?<![\d.]){re.escape(plain)}(?![\d])", text)
                or re.search(rf"(?<![\d.]){re.escape(grouped)}(?![\d])", text))


def test_the_corpus_count_in_the_doc_is_the_receipts():
    r = _receipt()
    n = int(r["corpus"]["rows_with_title_and_permno_2015_2024"])
    assert _has_number(_doc(), n), (
        f"the doc must quote the receipt's testable-corpus count {n:,}")


def test_the_event_table_row_count_in_the_doc_is_the_receipts():
    r = _receipt()
    assert _has_number(_doc(), int(r["corpus"]["event_table_rows"]))


def test_the_chosen_k_in_the_doc_is_the_receipts():
    r = _receipt()
    assert _has_number(_doc(), int(r["U1_chosen_k"]))


def test_the_holm_survivor_count_in_the_doc_is_the_receipts():
    r = _receipt()
    n = int(r["family_correction"]["export_holm"]["n_survivors"])
    doc = _doc()
    if n == 0:
        assert re.search(r"not one of the ten|zero of the ten|0 of the ten|"
                         r"none of the ten", doc, re.I), (
            "Holm kept nothing; the doc must say so in words")
    else:
        assert _has_number(doc, n)


def test_the_declared_family_size_is_ten_and_the_correction_was_over_ten():
    r = _receipt()
    assert r["declared_before_any_result"]["family_size"] == 10
    fc = r["family_correction"]
    assert fc["declared_family_size"] == 10
    assert fc["family_size_matches_declaration"], fc.get("warning")


def test_u3_passed_in_the_committed_run():
    r = _receipt()
    u3 = r["U3_known_answer"]
    assert u3["passed"], u3["checks"]
    # All four, named, so a future weakening of the gate shows up here.
    assert set(u3["checks"]) == {
        "planted_family_clustered", "null_family_clustered",
        "planted_separated_after_holm", "null_reads_noise"}


def test_the_run_spent_nothing_on_the_paid_provider():
    r = _receipt()
    assert r["llm_spend_usd"] == 0.0
    assert "nemotron-3-embed-1b" in r["embedder"]


def test_the_receipt_carries_provenance_that_passes_the_house_check():
    from backend.services.receipt_provenance import check_receipt, hard_failures
    r = _receipt()
    assert hard_failures(check_receipt(r)) == []


def test_every_dropped_event_is_accounted_for_by_reason():
    r = _receipt()
    f = r["frame"]
    kept = int(f["n_events_with_forward_return"])
    dropped = sum(int(v) for v in f["events_dropped_by_reason"].values())
    assert kept + dropped == int(f["n_events_offered"]), (
        "an event that is neither kept nor counted as dropped is a silent drop")
