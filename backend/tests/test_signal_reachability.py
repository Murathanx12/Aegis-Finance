"""Nothing computes for nobody without saying so.

The audit's own first run found `detectability_gate` — TOURNAMENT-2's declared
precondition — imported by no script and no runtime path, named only in three
comments. "The T2 runner MUST call assert_detectable" had been true as a
sentence and false as a fact for two days. These tests keep that finding from
being a one-off.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.services import signal_reachability as SR


# ── the contract ───────────────────────────────────────────────────────────


def test_every_orphan_is_classified():
    """A module neither the running system nor scripts/ can reach must carry a
    reason. 'Nobody noticed' is the failure this whole module exists to end."""
    SR.assert_no_unclassified_orphans()


def test_the_audit_can_actually_fail(tmp_path):
    """The guard on the guard (S47's lesson). If the scan found nothing, the
    contract above would pass forever while checking an empty set."""
    with pytest.raises(SR.ReachabilityUnknowable):
        SR.assert_no_unclassified_orphans(tmp_path)


def test_an_unclassified_orphan_is_refused(tmp_path):
    pkg = tmp_path / "backend"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "main.py").write_text("from backend import wired\n", encoding="utf-8")
    (pkg / "wired.py").write_text("X = 1\n", encoding="utf-8")
    (pkg / "lonely.py").write_text("Y = 2\n", encoding="utf-8")
    # Enough files to clear the "did we scan anything" floor.
    for i in range(SR._MIN_MODULES):
        (pkg / f"filler_{i}.py").write_text(
            "from backend import wired\n", encoding="utf-8")
        # ...and each filler is imported by main so it is reachable.
    (pkg / "main.py").write_text(
        "from backend import wired\n"
        + "".join(f"from backend import filler_{i}\n"
                  for i in range(SR._MIN_MODULES)),
        encoding="utf-8")

    with pytest.raises(SR.UnclassifiedOrphan, match="lonely"):
        SR.assert_no_unclassified_orphans(pkg)


# ── the discovery rule itself ──────────────────────────────────────────────


def test_the_closure_is_not_trivially_empty():
    """A discovery rule that under-detects makes the contract pass while
    missing things — `guard_contract`'s own stated failure mode, one level up.
    A BOM on one router did exactly this: read as plain utf-8 it was
    unparseable, so its whole dependency tree read as orphaned."""
    res = SR.audit()
    assert res["n_reachable"] > 100, (
        f"only {res['n_reachable']} modules reachable from "
        f"{len(res['entry_points_resolved'])} entry points — the closure is "
        f"collapsing and healthy code will report as dead")
    assert len(res["entry_points_resolved"]) > 5, "routers stopped resolving"


def test_function_level_imports_count():
    """The scheduler imports its jobs INSIDE the coroutines that run them. A
    module-level-only scan would report almost the whole system as orphaned."""
    src = SR.BACKEND / "services" / "portfolio_intelligence" / "scheduler.py"
    deps = SR._imports_of(src, "backend.services.portfolio_intelligence.scheduler")
    assert "backend.services.arena.engine" in deps or any(
        d.endswith("arena.engine") for d in deps), (
        "the arena engine is imported inside `_arena_daily`; if that is "
        "invisible here, every job's dependency tree is invisible too")


def test_ancestor_packages_are_reachable(tmp_path):
    """Importing `a.b.c` imports `a.b` and `a`. Without that every package
    __init__ reads as an orphan, and an audit that cries wolf gets ignored."""
    reached = SR.reachable_set()
    assert "backend.services" in reached
    assert "backend.services.arena" in reached


def test_a_module_only_scripts_reach_is_tooling_not_an_orphan():
    """Offline research is not a defect, and lumping it with real orphans is
    how a 79-row list becomes unreadable and then unread."""
    res = SR.audit()
    assert res["n_tooling_only"] > 20, (
        "the scripts/ closure collapsed; offline research will now report as "
        "orphaned and drown the rows that matter")
    assert "backend.services.research_gym.power" in res["tooling_only"]


# ── the findings, pinned ───────────────────────────────────────────────────


def test_known_gaps_stay_named_until_they_are_wired():
    """These are not 'fine'. Each is something that SHOULD have a caller.

    When one gets wired in, this test fails and the classification comes out —
    which is the correct way for a gap to close: visibly."""
    res = SR.audit()
    gaps = {o["module"] for o in res["orphans"]
            if (o["reason"] or "").startswith("GAP")}
    assert gaps >= {"backend.services.execution_boundary",
                    "backend.services.verdict_battery",
                    "backend.services.winner_loser_factory"}, (
        f"a gap closed or the audit stopped detecting: {sorted(gaps)}. If it "
        f"closed, delete its classification and this line — visibly.")


def test_the_first_gap_this_audit_found_is_closed():
    """`detectability_gate` was TOURNAMENT-2's declared precondition and was
    imported by nothing — named only in three comments. The planted-worlds
    script calls it now, so it must read as tooling rather than an orphan."""
    res = SR.audit()
    assert "backend.services.detectability_gate" in res["tooling_only"], (
        "the T2 detectability gate is unreachable again — 'the runner MUST "
        "call assert_detectable' is back to being a sentence")
