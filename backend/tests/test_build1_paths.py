"""A `git mv` of documentation must not silently disarm a budget gate.

WHAT HAPPENED (2026-08-29 → 2026-08-30)
=======================================
A documentation clean-up moved 92 dated docs into `docs/archive/`, and took the
whole of `docs/BUILD1/` with them. That directory is not prose: it holds
fourteen artefacts that code reads and writes, including `llm_ledger.jsonl`,
the append-only spend ledger that `llm_research.spent_usd()` sums to enforce
`CAMPAIGN_BUDGET_USD`.

`spent_usd()` returns **0.0 when the file is absent**. So the move did not raise
— it reset the recorded spend from 71 calls to nothing, and would have
re-authorised the full $30 budget. The only visible symptom was ONE red test out
of 6,018, and it was about a different file in the same directory.

The class is the one already in canon twice over: *a store whose count never
grows is RESET, not quiet*, and *a check that did not run is not a check that
passed*. `llm_research._mirror`'s docstring even names this exact failure —
"re-pointing a budget gate during an instrumentation change is how budgets stop
being enforced" — which is the lesson: **a warning in a comment cannot enforce
itself.**

WHAT THIS FILE PINS
===================
1. the resolver finds an artefact wherever it currently lives;
2. an EXISTING file wins, so an append-only ledger never forks into an empty
   twin beside its own history;
3. no module under `backend/`, `scripts/` or `engine/` reads a filesystem path
   built from a docs directory that has since moved.

(3) is the general guard. (1) and (2) only fix the instance.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from backend import config

ROOT = Path(__file__).resolve().parents[2]

#: Artefacts under BUILD1 that CODE touches, as opposed to documents a human
#: reads. Each must be locatable, or the consumer named beside it is broken.
CODE_ARTEFACTS = {
    "llm_ledger.jsonl": "llm_research.spent_usd -> CAMPAIGN_BUDGET_USD",
    "funnel_night10.json": "investment_committee, mirror_challenge",
    "ANALYST_SOURCE_COVERAGE.md": "pm_catalysts source-claim provenance",
    "analyst_source_probe_DKNG.json": "the receipts behind that matrix",
}


@pytest.mark.parametrize("name,consumer", sorted(CODE_ARTEFACTS.items()))
def test_every_build1_code_artefact_is_locatable(name, consumer):
    p = config.build1_path(name)
    assert p.exists(), f"{name} not found in {config.BUILD1_DIRS} — breaks {consumer}"


def test_an_existing_file_wins_over_the_live_directory(tmp_path, monkeypatch):
    """History must not fork. The archived ledger keeps being the ledger."""
    live, arch = tmp_path / "docs" / "BUILD1", tmp_path / "docs" / "archive" / "BUILD1"
    live.mkdir(parents=True)
    arch.mkdir(parents=True)
    (arch / "llm_ledger.jsonl").write_text('{"cost_usd": 1.0}\n', encoding="utf-8")
    monkeypatch.setattr(config, "BUILD1_DIRS", (live, arch))
    assert config.build1_path("llm_ledger.jsonl") == arch / "llm_ledger.jsonl"
    # ...and a file that exists NOWHERE resolves to a live directory that does,
    # so a first write lands somewhere a human recognises.
    assert config.build1_path("brand_new.json") == live / "brand_new.json"


def test_the_spend_ledger_is_not_empty_where_the_gate_reads_it():
    """The specific regression: the budget gate must see the recorded calls."""
    from backend.services import llm_research

    assert llm_research.LEDGER_PATH.exists(), (
        "the campaign spend ledger is missing, so spent_usd() reads $0.00 and the "
        f"${llm_research.CAMPAIGN_BUDGET_USD:.2f} budget is unenforced")
    rows = [line for line in llm_research.LEDGER_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert rows, "an empty ledger and a moved ledger are indistinguishable to the gate"
    total = sum(float(json.loads(r).get("cost_usd") or 0.0) for r in rows)
    assert llm_research.spent_usd() == pytest.approx(total), \
        "spent_usd() disagrees with the file it claims to read"


def _string_constants(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return set()
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def test_no_module_builds_a_path_from_a_docs_directory_that_moved():
    """The general guard: code may not hardcode a docs dir that only exists in archive.

    Prose in a docstring is fine — this looks at STRING CONSTANTS used to build
    paths, which is what actually breaks. `docs/BUILD1` is the known case; the
    check is written over every directory so the next reorganisation is caught
    by CI rather than by a budget quietly resetting.
    """
    live_dirs = {p.name for p in (ROOT / "docs").iterdir() if p.is_dir() and p.name != "archive"}
    archive_dirs = {p.name for p in (ROOT / "docs" / "archive").iterdir() if p.is_dir()}
    moved = archive_dirs - live_dirs
    if not moved:
        pytest.skip("no docs directory exists only in archive")

    # The resolver itself must name both locations -- that is its whole job --
    # and this file must quote the directory it is testing for.
    exempt = {ROOT / "backend" / "config.py", Path(__file__).resolve()}
    offenders = []
    for sub in ("backend", "scripts", "engine"):
        for py in (ROOT / sub).rglob("*.py"):
            if py.resolve() in exempt:
                continue
            consts = _string_constants(py)
            for d in moved & consts:
                # `"docs" / "<dir>"` as adjacent constants is the path-building
                # shape. A bare mention inside one long prose string is not.
                if "docs" in consts:
                    offenders.append(f"{py.relative_to(ROOT)} builds a path with 'docs'/'{d}'")
    assert not offenders, (
        "these modules build filesystem paths from a docs directory that now lives only "
        "in docs/archive/; use config.build1_path() or an equivalent resolver:\n  "
        + "\n  ".join(sorted(offenders)))
