"""The fast suite must not write into `evidence_memory*.jsonl`.

The gate itself lives in `backend/tests/ledger_guard.py` and is wired into
`conftest.pytest_sessionstart` / `pytest_sessionfinish`; this file tests the
gate (a guard nobody tested is a guard nobody knows the state of) and pins the
wiring, because the gate is invisible when it passes and deleting the two hooks
would not fail anything else.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from backend.tests import ledger_guard

REPO = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------- the gate works

def test_a_clean_run_reports_no_difference(tmp_path):
    (tmp_path / "evidence_memory_2026-09.jsonl").write_text("{}\n", encoding="utf-8")
    before = ledger_guard.fingerprint(tmp_path)
    assert ledger_guard.differences(before, ledger_guard.fingerprint(tmp_path)) == []


def test_an_appended_row_is_named_with_its_file(tmp_path):
    f = tmp_path / "evidence_memory_2026-09.jsonl"
    f.write_text("{}\n", encoding="utf-8")
    before = ledger_guard.fingerprint(tmp_path)
    with f.open("a", encoding="utf-8") as fh:
        fh.write('{"family_id": "x"}\n')
    diffs = ledger_guard.differences(before, ledger_guard.fingerprint(tmp_path))
    assert len(diffs) == 1
    assert "evidence_memory_2026-09.jsonl" in diffs[0] and "CHANGED" in diffs[0]


def test_a_row_rewritten_in_place_is_caught_even_at_the_same_size(tmp_path):
    """Bytes, not sizes. A compaction that swaps a row for another of the same
    length is exactly the edit the ledger's append-only promise forbids."""
    f = tmp_path / "evidence_memory_2026-09.jsonl"
    f.write_text('{"a": 1}\n', encoding="utf-8")
    before = ledger_guard.fingerprint(tmp_path)
    f.write_text('{"a": 2}\n', encoding="utf-8")
    diffs = ledger_guard.differences(before, ledger_guard.fingerprint(tmp_path))
    assert diffs and "CHANGED" in diffs[0]


def test_a_created_or_deleted_ledger_file_is_reported(tmp_path):
    before = ledger_guard.fingerprint(tmp_path)
    (tmp_path / "evidence_memory_2026-10.jsonl").write_text("{}\n", encoding="utf-8")
    after = ledger_guard.fingerprint(tmp_path)
    assert "CREATED" in ledger_guard.differences(before, after)[0]
    assert "DELETED" in ledger_guard.differences(after, before)[0]


def test_the_supersessions_log_is_covered_too(tmp_path):
    (tmp_path / "evidence_memory_supersessions.jsonl").write_text("{}\n",
                                                                  encoding="utf-8")
    assert "evidence_memory_supersessions.jsonl" in ledger_guard.fingerprint(tmp_path)


# ----------------------------------------------------------- the gate is wired

def test_conftest_brackets_the_whole_run_with_the_fingerprint():
    src = (REPO / "backend" / "tests" / "conftest.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    hooks = {n.name for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef)
             and n.name in ("pytest_sessionstart", "pytest_sessionfinish")}
    assert hooks == {"pytest_sessionstart", "pytest_sessionfinish"}, (
        "the ledger gate is only a gate if both hooks exist; without "
        "sessionfinish the fingerprint is taken and never compared")
    # The body must actually compare, not merely import. Read the AST rather
    # than grep so a docstring mentioning `differences` cannot satisfy it
    # (protocol §10).
    finish = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and n.name == "pytest_sessionfinish")
    called = {a.attr for a in ast.walk(finish)
              if isinstance(a, ast.Attribute)}
    assert "differences" in called and "fingerprint" in called


# --------------------------------------------------- the defect that caused it

def test_the_n7_scratch_receipt_test_no_longer_touches_the_live_ledger(tmp_path,
                                                                       monkeypatch):
    """The 2026-09-11 defect, re-run against the real ledger directory.

    `N7.run` folds receipts into the memory; the original test redirected the
    receipt directory and not the memory, so every suite run appended a row.
    """
    from learner import evidence_memory as EM
    from scripts import n7_memory_and_leaderboard as N7

    before = ledger_guard.fingerprint()
    out = tmp_path / "night"
    out.mkdir()
    (out / "N9_real.json").write_text(
        json.dumps({"job": "N9", "status": "SKIPPED", "headline": "nothing here"}),
        encoding="utf-8")
    monkeypatch.setattr(N7, "OUT_DIR", out)
    monkeypatch.setattr(N7, "LEADERBOARD", out / "LEADERBOARD.md")
    monkeypatch.setattr(N7, "BEST", out / "best_so_far.json")
    monkeypatch.setattr(EM, "STORE_DIR", tmp_path)
    monkeypatch.setattr(EM, "STORE", tmp_path / "evidence_memory.jsonl")

    N7.run(to_registry=False, verbose=False)

    assert ledger_guard.differences(before, ledger_guard.fingerprint()) == []
    # ...and the row it wrote went somewhere: a test that proves only absence
    # would also pass if `record_receipt` had quietly stopped writing.
    assert EM.read_all(), "the observation went nowhere at all"


@pytest.mark.parametrize("name", ["evidence_memory.jsonl",
                                  "evidence_memory_2026-09.jsonl",
                                  "evidence_memory_supersessions.jsonl"])
def test_the_pattern_matches_every_shape_of_ledger_file(name, tmp_path):
    (tmp_path / name).write_text("{}\n", encoding="utf-8")
    assert name in ledger_guard.fingerprint(tmp_path)
