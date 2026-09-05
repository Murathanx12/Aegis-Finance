"""Lane C / C3 -- the two silent-fragility defects that were SAFE to fix.

Labor Day Lab, 2026-09-07. `silent-fragility-audit` over every module touched
since 2026-09-04 in both repos produced 19 ranked findings; most are reported in
the receipt rather than patched, because a fix that changes what a live loop
refuses is attended work. Two are fixed here, and each is pinned red-first:

1. `llm_telemetry.spend()` RETURNED ZEROS FOR A LEDGER IT NEVER READ.
   Its own docstring says *"Returns {} on failure, never a zero:
   `research_budget` reads an empty dict as 'spend is UNKNOWN' and refuses"* --
   and there was no such branch. `read_calls()` returns `[]` when the path
   cannot be resolved, when the file does not exist, and when every line is
   torn; `spend()` then returned a POPULATED dict of zeros, `research_budget.
   check()` tested `if not s:` on a truthy dict, and the full ceiling was
   re-authorised. That is [[a docs move disarmed a budget gate]] rebuilt in the
   successor module, one release after the lesson.

   The distinction that had to survive: a ledger that EXISTS and legitimately
   holds no matching rows is a REAL zero and must stay one. Only "no ledger was
   opened" is unknown.

2. `receipt_provenance` COUNTED A FILE IT COULD NOT FIND AS ONE IT OPENED.
   `InputTracker.opened()` records a nonexistent path as
   `{"path": ..., "error": "MISSING"}` and appends it to the order. The checker
   built `opened` by filtering on `path` alone, so those entries satisfied both
   `EMPTY_INPUTS` and `UNOPENED_PATH_STAMPED` -- a job whose every input was
   absent produced a receipt that passed the provenance sweep clean. The
   checker for "a number produced from no file it can name" could be satisfied
   by naming files that were not there.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services import llm_telemetry, receipt_provenance, research_budget


# ---------------------------------------------------------------- 1. the budget gate

def _row(cost: float = 0.01) -> dict:
    return {"ts": "2026-09-05T10:00:00+00:00", "provider": "deepseek",
            "model": "deepseek-chat", "purpose": "labor_c3_probe",
            "cost_usd": cost, "input_tokens": 100, "output_tokens": 50}


def test_spend_refuses_when_the_ledger_file_does_not_exist(tmp_path: Path) -> None:
    """An ABSENT ledger is UNKNOWN spend, not zero spend.

    This is the whole finding. Before the fix this returned
    `{"n_calls": 0, "total_cost_usd": 0.0, ...}` -- truthy, so every downstream
    `if not s: refuse` was skipped and the ceiling was handed back in full.
    """
    missing = tmp_path / "no_such_ledger.jsonl"
    assert not missing.exists()
    assert llm_telemetry.spend(path=missing) == {}, (
        "an absent ledger must read as UNKNOWN. A populated dict of zeros is "
        "indistinguishable from 'measured, and nothing was spent'.")


def test_spend_refuses_when_the_path_cannot_be_resolved() -> None:
    """`_resolve_path` returns None under pytest with no destination. No file
    was read, so there is nothing to report -- and a zero would be a claim."""
    assert llm_telemetry._resolve_path(None) is None, (
        "this test's premise: under pytest with no explicit path and no env "
        "var, telemetry has no destination")
    assert llm_telemetry.spend() == {}


def test_spend_still_reports_a_REAL_zero_for_a_present_empty_ledger(tmp_path: Path) -> None:
    """The distinction the fix must not destroy.

    A ledger that exists and holds no rows -- a campaign that has not spent
    yet -- is a MEASURED zero and must keep reading as one, or the first call
    of every night would refuse itself.
    """
    empty = tmp_path / "llm_calls.jsonl"
    empty.write_text("", encoding="utf-8")
    got = llm_telemetry.spend(path=empty)
    assert got != {}, "an existing, empty ledger is a measured zero, not unknown"
    assert got["n_calls"] == 0 and got["total_cost_usd"] == 0.0


def test_spend_reports_a_real_zero_when_a_FILTER_matches_nothing(tmp_path: Path) -> None:
    """Same distinction, one layer in: a populated ledger whose `purpose`
    filter matches nothing has genuinely spent nothing on that purpose."""
    p = tmp_path / "llm_calls.jsonl"
    p.write_text(json.dumps(_row()) + "\n", encoding="utf-8")
    got = llm_telemetry.spend(path=p, purpose="a_purpose_nobody_used")
    assert got != {} and got["n_calls"] == 0


def test_the_budget_gate_refuses_against_an_absent_ledger(tmp_path: Path) -> None:
    """End to end: the consumer that the docstring names.

    `research_budget.check()` already had the right branch and the right
    comment ("Allowing the campaign here would mean every ceiling is off
    precisely when the accounting is broken"). It could never be reached.
    """
    if not research_budget.RESEARCH_LLM_ENABLED:
        pytest.skip("AEGIS_RESEARCH_LLM=0: the gate short-circuits before the read")
    state = research_budget.check("labor_c3_probe", path=tmp_path / "absent.jsonl")
    assert state.ok is False, (
        "an absent telemetry ledger re-authorised the whole ceiling: "
        + repr(state.as_dict()))
    assert "unreadable" in (state.reason or "").lower()
    assert state.cost_usd is None, "unknown spend must not be reported as a number"


# --------------------------------------------------- 2. the provenance checker

def test_a_MISSING_input_does_not_count_as_an_opened_one(tmp_path: Path) -> None:
    """A receipt whose every input was absent must NOT pass the sweep.

    `InputTracker.opened()` deliberately records the attempt with
    `error: "MISSING"` -- that part is right, and it is what makes the failure
    visible at all. What was wrong is that `check_receipt` then counted the
    attempt as a successful open.
    """
    t = receipt_provenance.InputTracker()
    entry = t.opened(tmp_path / "never_written.parquet")
    assert entry.get("error") == "MISSING", "premise: the tracker marks it MISSING"

    receipt = {"_provenance": {"sys_argv": ["probe"], "resolved_config": {},
                               "_inputs_opened": t.entries()}}
    findings = receipt_provenance.check_receipt(receipt, require_inputs=True)
    assert any("MISSING" in f or "EMPTY_INPUTS" in f for f in findings), (
        "a job that opened nothing that exists produced a receipt the "
        "provenance sweep called clean: " + repr(findings))


def test_a_real_input_still_passes(tmp_path: Path) -> None:
    """The complement -- the fix must not make every receipt red."""
    real = tmp_path / "panel.jsonl"
    real.write_text('{"a": 1}\n', encoding="utf-8")
    t = receipt_provenance.InputTracker()
    e = t.opened(real)
    assert "error" not in e and e.get("sha256")
    receipt = {"_provenance": {"sys_argv": ["probe"], "resolved_config": {},
                               "_inputs_opened": t.entries()}}
    assert receipt_provenance.check_receipt(receipt, require_inputs=True) == []


def test_a_mix_reports_the_missing_one_and_keeps_the_good_one(tmp_path: Path) -> None:
    real = tmp_path / "panel.jsonl"
    real.write_text('{"a": 1}\n', encoding="utf-8")
    t = receipt_provenance.InputTracker()
    t.opened(real)
    t.opened(tmp_path / "gone.parquet")
    receipt = {"_provenance": {"sys_argv": ["probe"], "resolved_config": {},
                               "_inputs_opened": t.entries()}}
    findings = receipt_provenance.check_receipt(receipt, require_inputs=True)
    assert any("MISSING" in f for f in findings)
    assert not any("EMPTY_INPUTS" in f for f in findings), (
        "one input was genuinely opened, so the receipt is not input-less")
