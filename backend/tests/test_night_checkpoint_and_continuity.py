"""Crash safety and cross-night continuity for the night factory (2026-09-10).

These pin two things the 09-09 crash exposed:

1. A long job must survive a kill. `atomic_write_json` + `Checkpoint` are the
   mechanism; a resume under a changed configuration is a REFUSAL, not a silent
   continuation under the old run number.

2. The search must not replay itself. The 09-09 G3 run was a bit-identical
   repeat of the 09-08 one -- same declared seed, `bank_seed = seed + 1000*gen`,
   same banks, same tree. The overlap test below reads the real evaluations log
   and pins that number, so a future "the night factory learns overnight" claim
   has to face it.

Every number asserted here is read from a file in the repo, per CLAUDE.md's
"a headline number belongs in a receipt".
"""

from __future__ import annotations

import collections
import json
import random
from pathlib import Path

import pytest

from scripts.night_checkpoint import (
    Checkpoint,
    SearchState,
    atomic_write_json,
    rng_state_from_json,
    rng_state_to_json,
)

REPO = Path(__file__).resolve().parents[2]
G3_EVALS = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-08" / "G3_evaluations.jsonl"


# --------------------------------------------------------------- atomic write

def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "receipt.json"
    for i in range(5):
        atomic_write_json(target, {"i": i})
    assert json.loads(target.read_text(encoding="utf-8"))["i"] == 4
    # a tmp left behind would accumulate one file per generation over a 5h night
    assert [p.name for p in tmp_path.iterdir()] == ["receipt.json"]


def test_atomic_write_does_not_destroy_the_previous_version_on_failure(tmp_path: Path) -> None:
    target = tmp_path / "receipt.json"
    atomic_write_json(target, {"good": True})

    class Unserialisable:
        pass

    with pytest.raises(TypeError):
        # default=str would stringify this, so force the failure through a key
        atomic_write_json(target, {Unserialisable(): 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"good": True}


# --------------------------------------------------------------- rng round-trip

def test_rng_state_survives_json() -> None:
    """`getstate()` returns a tuple of tuples; JSON returns lists, and
    `setstate` raises `TypeError: state[1] must be a tuple`. A resume is the
    worst place to discover that."""
    a = random.Random(1234)
    [a.random() for _ in range(50)]
    blob = json.loads(json.dumps(rng_state_to_json(a.getstate())))
    b = random.Random()
    b.setstate(rng_state_from_json(blob))
    assert [a.random() for _ in range(20)] == [b.random() for _ in range(20)]


# --------------------------------------------------------------- checkpoint

def _cfg(**over):
    base = {"seed": 1, "pop": 8, "sel_windows": 6, "n_null": 3}
    base.update(over)
    return base


def test_checkpoint_round_trips(tmp_path: Path) -> None:
    c = Checkpoint(tmp_path / "ck.json", _cfg())
    assert not c.exists()
    c.save({"gen": 7, "n_eval": 42})
    assert Checkpoint(tmp_path / "ck.json", _cfg()).load()["gen"] == 7


def test_checkpoint_refuses_a_resume_under_a_different_configuration(tmp_path: Path) -> None:
    Checkpoint(tmp_path / "ck.json", _cfg()).save({"gen": 7})
    with pytest.raises(ValueError) as exc:
        Checkpoint(tmp_path / "ck.json", _cfg(pop=24)).load()
    msg = str(exc.value)
    assert "REFUSED" in msg and "pop" in msg and "8" in msg and "24" in msg


def test_checkpoint_refuses_a_truncated_file_with_a_reason(tmp_path: Path) -> None:
    p = tmp_path / "ck.json"
    p.write_text('{"kind": "night_check', encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        Checkpoint(p, _cfg()).load()
    assert "not readable JSON" in str(exc.value)


def test_checkpoint_clear_is_idempotent(tmp_path: Path) -> None:
    c = Checkpoint(tmp_path / "ck.json", _cfg())
    c.save({"gen": 1})
    c.clear()
    c.clear()                      # a second clear must not raise on a finished run
    assert not c.exists()


# --------------------------------------------------------------- search state

def test_fresh_bank_seeds_never_returns_a_seed_the_search_selected_on(tmp_path: Path) -> None:
    """The archive's whole claim is 'a bank the search never saw'. Once nights
    accumulate, a random draw WILL collide with an earlier night's selection
    bank unless something refuses it."""
    st = SearchState(tmp_path / "state.json")
    st.record_selection_banks(range(1, 96))          # 95 of the 100 available
    rng = random.Random(0)
    seeds, rejected = st.fresh_bank_seeds(rng, 5, lo=1, hi=100)
    assert sorted(seeds) == [96, 97, 98, 99, 100]
    assert rejected > 0, "the guard must report how often it fired, not fire silently"


def test_fresh_bank_seeds_refuses_rather_than_reusing_when_the_space_is_exhausted(tmp_path: Path) -> None:
    st = SearchState(tmp_path / "state.json")
    st.record_selection_banks(range(1, 11))
    with pytest.raises(RuntimeError) as exc:
        st.fresh_bank_seeds(random.Random(0), 1, lo=1, hi=10)
    assert "REFUSED" in str(exc.value)


def test_elites_prefer_the_better_measured_genome_not_the_better_scoring_one(tmp_path: Path) -> None:
    """Picking the higher fitness would be selection on the outcome -- the error
    `feedback_a_matched_control_must_not_be_picked_on_the_outcome` records."""
    st = SearchState(tmp_path / "state.json")
    st.update_elites([{"key": "a", "genome": {"w": 1}, "fitness": 1.0, "banks_met": 9}])
    st.update_elites([{"key": "a", "genome": {"w": 2}, "fitness": 99.0, "banks_met": 1}])
    kept = [e for e in st.elites if e["key"] == "a"][0]
    assert kept["banks_met"] == 9 and kept["fitness"] == 1.0


def test_search_state_persists_across_nights(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    st = SearchState(p)
    assert st.night_index == 0 and not st.loaded_from_disk
    st.record_selection_banks([11, 22])
    st.update_elites([{"key": "g1", "genome": {"w": 1}, "fitness": 3.0, "banks_met": 2}])
    st.close_night({"job": "T"})

    st2 = SearchState(p)
    assert st2.night_index == 1
    assert st2.bank_seeds_selected_on == {11, 22}
    assert st2.seed_population(4) == [{"w": 1}]


def test_seed_population_is_empty_on_the_first_night(tmp_path: Path) -> None:
    assert SearchState(tmp_path / "state.json").seed_population(8) == []


# --------------------------------------------------------------- the replay

@pytest.mark.skipif(not G3_EVALS.exists(), reason="G3 evaluations log not on this checkout")
def test_the_2026_09_09_g3_run_was_a_replay_of_the_earlier_one() -> None:
    """The receipt for the crashed run said `exited 1073807364 with no receipt`
    and the handoff called 3.1 hours of work lost. The log says otherwise: the
    run rediscovered nothing.

    Pinned so that a later change which restores a fixed `seed + 1000*gen` bank
    schedule turns this red instead of quietly reinstating the replay.
    """
    rows = [json.loads(line) for line in G3_EVALS.read_text(encoding="utf-8").splitlines() if line.strip()]
    boundary = next(i for i in range(1, len(rows)) if rows[i]["gen"] < rows[i - 1]["gen"])
    first = {r["key"] for r in rows[:boundary]}
    second = {r["key"] for r in rows[boundary:]}
    assert boundary == 2373
    assert len(first) == 595 and len(second) == 541
    # every genome the second run "discovered" was already in the first run's log
    assert second <= first
    assert len(second & first) == 541


@pytest.mark.skipif(not G3_EVALS.exists(), reason="G3 evaluations log not on this checkout")
def test_the_old_archive_rule_discarded_the_well_measured_genomes() -> None:
    """`finalist_basis` in `G3_evolve_run01.json` reads
    "ALL lineages (only 3 met two banks)". The log shows 161 genomes met two or
    more. The gap is the lineage-representative rule: it ranked by median
    fitness, and a one-bank median is a single draw sitting at the noisy top.
    """
    rows = [json.loads(line) for line in G3_EVALS.read_text(encoding="utf-8").splitlines() if line.strip()]
    boundary = next(i for i in range(1, len(rows)) if rows[i]["gen"] < rows[i - 1]["gen"])
    banks: dict[str, set] = collections.defaultdict(set)
    for r in rows[:boundary]:
        if (r.get("result") or {}).get("fitness") is not None:
            banks[r["key"]].add(r["bank_seed"])
    multi = sum(1 for v in banks.values() if len(v) >= 2)
    assert len(banks) == 595
    assert multi == 161, "the well-measured genomes existed; the representative rule threw them away"

    receipt = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-08" / "G3_evolve_run01.json"
    if receipt.exists():
        basis = json.loads(receipt.read_text(encoding="utf-8")).get("finalist_basis") or ""
        assert "only 3 met two banks" in basis, (
            "this test documents the DEFECTIVE receipt; if the receipt was regenerated, "
            "update the test to the new basis string rather than deleting the evidence"
        )


# --------------------------------------------------- the factory's resume rule

def test_resolve_run_resumes_a_crashed_stub_instead_of_bumping_the_run_number(
        tmp_path: Path, monkeypatch) -> None:
    """`while _receipt_path(job, run).exists(): run += 1` treated the crash stub
    as a completed run, so the next night would have started G3 at run 02 from
    generation 0 with the crashed run's checkpoint orphaned on disk."""
    from scripts import night_factory as nf

    monkeypatch.setattr(nf, "OUT", tmp_path)
    (tmp_path / "J_run01.log").write_text("...", encoding="utf-8")
    (tmp_path / "J_run01.json").write_text(json.dumps(
        {"verdict": "FAILED", "headline": "exited 1073807364 with no receipt"}), encoding="utf-8")
    assert nf.resolve_run("J", 1) == (1, True)


def test_resolve_run_does_not_resume_a_completed_run(tmp_path: Path, monkeypatch) -> None:
    from scripts import night_factory as nf

    monkeypatch.setattr(nf, "OUT", tmp_path)
    (tmp_path / "J_run01.log").write_text("...", encoding="utf-8")
    (tmp_path / "J_run01.json").write_text(json.dumps(
        {"verdict": "PRODUCT_PROMISING", "headline": "it worked"}), encoding="utf-8")
    assert nf.resolve_run("J", 1) == (2, False)


def test_resolve_run_resumes_a_log_with_no_receipt_at_all(tmp_path: Path, monkeypatch) -> None:
    """The PC dying takes night_factory with it, so the stub is never written."""
    from scripts import night_factory as nf

    monkeypatch.setattr(nf, "OUT", tmp_path)
    (tmp_path / "J_run01.log").write_text("...", encoding="utf-8")
    assert nf.resolve_run("J", 1) == (1, True)


def test_the_dispatcher_refuses_resume_for_a_job_with_no_checkpoint() -> None:
    """Forwarding --resume to a job whose function has no such parameter is a
    TypeError three hours into the night."""
    from scripts.night_factory_jobs import RESUMABLE, main

    assert "G3_evolve_v2" in RESUMABLE
    assert main(["D1_reaction_book", "--resume"]) == 2
