"""There is exactly one roadmap: docs/ROADMAP.md.

By 2026-11-09 docs/ held 43 roadmap/sprint/plan files and the owner's plans kept
getting lost between them. The owner's decision (2026-11-09): one modular,
living roadmap that is amended in place. This test fails when a NEW top-level
roadmap/sprint/plan file appears in docs/. The fix is to add a row to
docs/ROADMAP.md, not to add a name to HISTORICAL.

It reads file NAMES only, never mtimes (CLAUDE.md protocol item 7).
"""
from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
PLAN_NAME = re.compile(r"roadmap|sprint|_plan", re.IGNORECASE)

# Frozen 2026-11-09. History only; never add to this set.
HISTORICAL = frozenset({
    "AEGIS_BETA_V1_BUILD_SPRINT_2026-10-11.md",
    "AEGIS_EXECUTION_ROADMAP.md",
    "BETA_SPRINT_MEASURED_RESULTS_2026-10-11.md",
    "EVOLUTION_LOOP_PLAN.md",
    "GRAND_ARENA_1_PLAN.md",
    "HANDOFF_2026-09-11_FABLE_TO_OPUS_BUILD_PLAN.md",
    "HANDOFF_2026-09-25_FABLE_TO_OPUS_BUILD_PLAN.md",
    "INVESTOR_BRAIN_PLAN_2026-07-18.md",
    "ROADMAP_2026-08-23_PROFIT_FIRST.md",
    "ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md",
    "ROADMAP_2026-08-26_HUMAN_HEURISTICS_AND_FAST_RESEARCH.md",
    "ROADMAP_2026-08-29_WEEKEND_TO_MONDAY.md",
    "ROADMAP_2026-08-31_COMPETITION_WEEK_WORLD_MODEL.md",
    "ROADMAP_2026-09-04_PROFIT_ENGINE.md",
    "ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md",
    "ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md",
    "ROADMAP_2026-09-08_NIGHT_ALPHA_FACTORY.md",
    "ROADMAP_2026-09-10_MODEL_NEWS_AND_THE_EVENT_NET.md",
    "ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md",
    "ROADMAP_2026-09-25_CHUNKS_AND_THE_REVIEW_LOOP.md",
    "ROADMAP_2026-09-25_CONNECT_WHAT_EXISTS.md",
    "ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md",
    "ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md",
    "SESSION_2026-09-03_SCOREBOARD_AND_ROADMAP_ADDENDUM.md",
    "V1_STATE_AND_ROADMAP.md",
    "V2_ROADMAP.md",
    "WEEKEND_LAB_2026-09-06_ROADMAP_AND_PROMPT.md",
})
THE_ROADMAP = "ROADMAP.md"


def _plan_files() -> set[str]:
    return {p.name for p in DOCS.glob("*.md") if PLAN_NAME.search(p.name)}


def test_the_one_roadmap_exists() -> None:
    text = (DOCS / THE_ROADMAP).read_text(encoding="utf-8")
    assert "There is exactly one roadmap" in text
    assert "## 8. Changelog" in text


def test_no_new_roadmap_files() -> None:
    new = sorted(_plan_files() - HISTORICAL - {THE_ROADMAP})
    assert not new, (
        f"new roadmap/plan file(s) in docs/: {new}. There is one roadmap: "
        "amend docs/ROADMAP.md (add a module row and a changelog line) instead."
    )


def test_index_points_tier1_at_the_one_roadmap() -> None:
    index = (DOCS / "INDEX.md").read_text(encoding="utf-8")
    tier1 = index.split("## TIER 1", 1)[1].split("\n## ", 1)[0]
    assert "(ROADMAP.md)" in tier1
