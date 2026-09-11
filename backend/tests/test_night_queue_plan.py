"""The night planner is fed a synthetic night and must derive exactly four moves.

Same shape as `test_x9_day_run_numbers.py` -- a number (here: a decision) is
pinned to the receipt it came from -- but the receipts are written by the test
into a tmp directory, so the assertions do not depend on which night happens to
be on this checkout.

The four cases are the whole contract of `scripts/night_queue_plan.py`:

| receipt | plan |
|---|---|
| `CONDITIONAL` + a declared next test | schedules it |
| `CONDITIONAL` + no declared next test | schedules NOTHING, says `CANNOT DETERMINE` |
| `REJECTED` | schedules NOTHING |
| `FAILED`, a log on disk, no job-written receipt | schedules a RESUME |

Plus the two traps the module exists to encode: a job cited inside a
NEGATIVE_RESULTS section is not thereby closed, and an empty plan never emits a
paste-able `NIGHT_QUEUE=""` (which night_factory reads as "unset" and answers
with the full default queue).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import night_queue_plan as P  # noqa: E402

#: the job ids the synthetic night is allowed to schedule; injected so the test
#: never depends on what `night_factory_jobs` happens to register today
JOBS = {"D1_reaction_book", "N2_learner_v3", "G3_evolve_v2", "RW2_event_windows"}


def _write(d: Path, name: str, payload: dict) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return p


@pytest.fixture()
def night(tmp_path: Path) -> Path:
    """One synthetic night carrying one receipt of each of the four kinds."""
    d = tmp_path / "night_factory_2026-09-01"

    # (a) CONDITIONAL, declares its next test in a field, and the field names a
    #     runnable job -- the one row that must reach the queue
    _write(d, "D1_reaction_book_run01.json", {
        "job": "D1_reaction_book", "run": 1,
        "verdict": "CONDITIONAL: the long-short survives its control in two eras of three",
        "headline": "reaction LS +8.6%/yr vs control",
        "next_test": "run N2_learner_v3 on the same events with the dateless control beside it",
    })

    # (b) CONDITIONAL, declares NOTHING -- the refusal case
    _write(d, "RW2_event_windows_run01.json", {
        "job": "RW2_event_windows", "run": 1,
        "verdict": "CONDITIONAL -- 71% of windows over control but 24% of 2016-2024 starts",
        "headline": "reaction_LS conditional on the era",
    })

    # (c) REJECTED -- a closed lane gets nothing even though it declares a next test
    _write(d, "H9_prereg_read_run01.json", {
        "job": "H9_prereg_read", "run": 1, "trial": "TRIAL-H9-something",
        "verdict": "REJECTED: reject_t_lt_1.5. The trial closes.",
        "headline": "primary t 1.14",
        "next_test": "run D1_reaction_book again at a lower floor",
    })

    # (d) FAILED with a log and no job-written receipt -- the crash case. The
    #     payload is byte-shaped like `night_factory.run_job`'s stub on purpose.
    _write(d, "G3_evolve_v2_run01.json", {
        "verdict": "FAILED", "headline": "exited 1073807364 with no receipt",
        "elapsed_s": 11102.0, "exit_code": 1073807364, "log_tail": "...gen 340...",
        "licence": "PRODUCT_EXPERIMENT", "job": "G3_evolve_v2", "run": 1,
        "written_utc": "2026-09-09T18:29:14+00:00",
    })
    (d / "G3_evolve_v2_run01.log").write_text("gen 340 best +15.9%/yr\n", encoding="utf-8")
    return d


def _plan(night: Path, **kw) -> dict:
    kw.setdefault("closed_ids", set())
    kw.setdefault("jobs", JOBS)
    kw.setdefault("plan_date", "2026-09-02")
    return P.build_plan([night], **kw)


def _row(plan: dict, job: str) -> dict | None:
    return next((r for r in plan["queue"] if r["job"] == job), None)


def _refusal(plan: dict, job: str) -> dict | None:
    return next((r for r in plan["refused"] if r["job"] == job), None)


# ------------------------------------------------------------ (a) (b) (c) (d)

def test_a_conditional_with_a_declared_next_test_schedules_it(night: Path):
    plan = _plan(night)
    row = _row(plan, "N2_learner_v3")
    assert row is not None, "the declared next test did not reach the queue"
    assert row["kind"] == "DECLARED_NEXT_TEST"
    # the reason must QUOTE the field it came from, not paraphrase it
    assert row["quoted_field"] == "next_test"
    assert row["quoted_text"].startswith("run N2_learner_v3 on the same events")
    assert "D1_reaction_book" in row["reason"] and "CONDITIONAL" in row["reason"]
    assert row["source_receipt"].endswith("D1_reaction_book_run01.json")
    assert row["minutes"] > 0
    # and it is a test, never a promotion
    assert "attended" in row["promotion"]


def test_b_conditional_with_no_declared_next_test_schedules_nothing(night: Path):
    plan = _plan(night)
    assert _row(plan, "RW2_event_windows") is None, "a row with no declaration was scheduled"
    assert "CANNOT DETERMINE: RW2_event_windows is CONDITIONAL and declares no next test" \
        in plan["cannot_determine"]
    assert "CANNOT DETERMINE" in _refusal(plan, "RW2_event_windows")["why"]


def test_c_a_rejected_row_schedules_nothing(night: Path):
    plan = _plan(night)
    assert _refusal(plan, "H9_prereg_read")["status"] == "REJECTED"
    # it declared `next_test: run D1_reaction_book again` and must NOT be honoured
    assert _row(plan, "D1_reaction_book") is None, (
        "a REJECTED lane's declared next test was scheduled; a closed lane gets nothing")


def test_d_a_failed_run_with_a_log_and_no_receipt_schedules_a_resume(night: Path):
    plan = _plan(night)
    row = _row(plan, "G3_evolve_v2")
    assert row is not None and row["kind"] == "RESUME", (
        "the crashed run was not proposed as a resume")
    assert row["log"] == "G3_evolve_v2_run01.log"
    assert "exited 1073807364 with no receipt" in row["quoted_text"]
    assert "RESUME, not a fresh run" in row["reason"]


# ------------------------------------------------------------------ the traps

def test_a_failed_run_whose_JOB_wrote_the_receipt_is_not_a_resume(night: Path):
    """`FAILED` alone is not resumable -- only a run the job never spoke for is."""
    _write(night, "G3_evolve_v2_run02.json", {
        "job": "G3_evolve_v2", "run": 2, "verdict": "FAILED",
        "headline": "the fitness never cleared the drawdown refusal",
        "generations": 12, "genome_evaluations": 88})
    (night / "G3_evolve_v2_run02.log").write_text("done\n", encoding="utf-8")
    plan = _plan(night)
    assert _row(plan, "G3_evolve_v2") is None
    assert "the JOB wrote this receipt" in _refusal(plan, "G3_evolve_v2")["why"]


def test_an_amendment_supersedes_the_status_it_amends(night: Path):
    """A row stamped PRODUCT_PROMISING and amended to ERA_DECAYED is CLOSED."""
    _write(night, "D1_verdict_amendment.json", {
        "amends": "D1_reaction_book_run01.json",
        "corrected_verdict": "ERA_DECAYED: real in 1999-2015, absent after",
        "why": "the stamp counted era SIGNS"})
    plan = _plan(night)
    assert _row(plan, "N2_learner_v3") is None, (
        "an amended-closed lane still scheduled its next test")
    assert _refusal(plan, "D1_reaction_book")["status"] == "ERA_DECAYED"


def test_a_job_merely_CITED_in_a_negative_results_section_is_not_closed(tmp_path: Path,
                                                                       night: Path):
    """RW2 is quoted inside the TRIAL-H5 section as a source of numbers.

    A substring match over job names would bury it. The closure link is the
    receipt's own `trial` field against ids taken from section HEADINGS.
    """
    nr = tmp_path / "NEGATIVE_RESULTS.md"
    nr.write_text(
        "## The event-level learner (TRIAL-H9) - REJECTED by its own registered rule\n\n"
        "on 240 seeded windows (`RW2_event_windows_run01.json`) the learner beats its own\n"
        "control in only 44% of starts, read once by the named job `RW2_event_windows`.\n",
        encoding="utf-8")
    ids = P.closed_trial_ids(nr)
    assert "TRIAL-H9" in ids

    plan = _plan(night, closed_ids=ids)
    # the CITED job keeps its ordinary refusal (no declaration), NOT a closure
    assert "CLOSED LANE" not in _refusal(plan, "RW2_event_windows")["why"]
    # the job that DECLARED the trial is closed by it
    why = _refusal(plan, "H9_prereg_read")["why"]
    assert why.startswith("CLOSED LANE") and "TRIAL-H9" in why


def test_an_empty_plan_never_emits_a_pasteable_empty_night_queue(tmp_path: Path):
    """`NIGHT_QUEUE=""` is falsy in night_factory, so it runs the DEFAULT queue."""
    d = tmp_path / "night_factory_2026-09-01"
    _write(d, "D1_reaction_book_run01.json",
           {"job": "D1_reaction_book", "verdict": "FAILED_VARIANT: nothing here"})
    plan = P.build_plan([d], closed_ids=set(), jobs=JOBS, plan_date="2026-09-02")
    assert plan["queue"] == [] and plan["verdict"] == "PLAN EMPTY"
    assert plan["night_queue_env"] is None
    # the paste block refuses instead of offering an assignment; the string
    # `NIGHT_QUEUE=""` appears only inside the sentence explaining WHY
    paste = P.render(plan).split("PASTE THIS")[1].splitlines()[1].strip()
    assert paste.startswith("REFUSED:") and "DEFAULT queue" in paste
    assert any("DEFAULT" in n for n in plan["notes_for_the_human"])


def test_night_dirs_order_by_the_name_never_by_mtime(tmp_path: Path):
    """A fresh checkout rewrites every mtime (CLAUDE.md session protocol 7)."""
    for name in ("night_factory_2026-09-01", "night_factory_2026-09-09",
                 "night_factory_2026-09-05", "night_factory_not_a_date"):
        (tmp_path / name).mkdir()
    # touch the OLDEST last, so mtime order is the reverse of name order
    (tmp_path / "night_factory_2026-09-01" / "x").write_text("x", encoding="utf-8")
    got = [p.name for p in P.night_dirs(tmp_path, 2)]
    assert got == ["night_factory_2026-09-05", "night_factory_2026-09-09"]


# ------------------------------------------------------------------- authority

def test_the_planner_cannot_run_seal_or_arm_anything():
    """The plan proposes. Anything that executes belongs to a human."""
    src = (REPO / "scripts" / "night_queue_plan.py").read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1]           # skip the module docstring
    for forbidden in ("subprocess", "os." + "system", "os.exec", "Popen", "taskkill"):
        assert forbidden not in body, f"the planner references {forbidden!r}"
    plan = P.build_plan(P.night_dirs(REPO / "backend" / "data" / "optimus", 1)
                        or [REPO], plan_date="2026-09-02")
    assert plan["requires_human_veto"] is True
    for row in plan["queue"]:
        assert row["kind"] in ("DECLARED_NEXT_TEST", "RESUME")


def test_the_memory_append_goes_through_the_sanctioned_api(tmp_path: Path, night: Path,
                                                           monkeypatch):
    from learner import evidence_memory as EM
    monkeypatch.setattr(EM, "STORE_DIR", tmp_path)
    monkeypatch.setattr(EM, "STORE", tmp_path / "evidence_memory.jsonl")
    plan = _plan(night)
    p = P.write_plan(plan, night)
    assert p.name == "NIGHT_PLAN_2026-09-02_run01.json"
    P.append_memory(plan, p)
    # Through the reader, not a filename. The ledger rotated into monthly files
    # on 2026-09-11 (E6) and the store is now "whatever `read_all` returns".
    rows = EM.read_all()
    assert len(rows) == 1
    assert EM.active_store().name.startswith("evidence_memory_")
    assert rows[0]["job"] == "night_queue_plan"
    assert "requires_human_veto" in rows[0]["verdict"]
    # the run number is bumped, never overwritten
    assert P.write_plan(plan, night).name == "NIGHT_PLAN_2026-09-02_run02.json"
