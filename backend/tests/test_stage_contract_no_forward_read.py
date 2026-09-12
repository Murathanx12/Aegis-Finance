"""The stage contract, first step: no receipt may read an artefact from a LATER stage.

This is deliberately narrow. It is not a DAG verifier and does not try to be.
It catches one class of bug -- "E2 accidentally reads a paper book's realised
fill price as a feature" -- which a PIT assertion on a single table cannot see,
because every row in that table is individually point-in-time and the leak is in
where the table came from.

`raw < normalized < features < signal < weights < pnl`

REFUSAL-SHAPED, on the `monday_gate_check` lesson. If no receipt in the corpus
carries a `stage`, this reports CANNOT DETERMINE rather than a false green -- a
check that can only ever pass is not a check. And a receipt with a stage but no
declared inputs is not silently counted as clean: it is NAMED, so the list of
receipts that cannot be checked is visible instead of comfortable.

What it does NOT do, on purpose: add `stage` to `Strategy` or `PaperBook`. That
is the farm-and-book unification the roadmap scopes as "big" and gates on lane
B, and forcing it here would be roadmap-scale work under a test's name. The
receipt-level field is the cheap, tamper-evident down payment.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.night_factory_jobs import JOB_STAGES, STAGE_ORDER      # noqa: E402

OPTIMUS = REPO / "backend" / "data" / "optimus"
#: the keys a receipt may use to say what it read
INPUT_KEYS = ("inputs", "reads_from", "read_from", "sources")
RANK = {s: i for i, s in enumerate(STAGE_ORDER)}


def _receipts() -> list[tuple[Path, dict]]:
    out = []
    for d in sorted(OPTIMUS.glob("night_factory_*")):
        for p in sorted(d.glob("*.json")):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(r, dict):
                out.append((p, r))
    return out


def _declared_paths(r: dict) -> list[str]:
    paths = []
    for k in INPUT_KEYS:
        v = r.get(k)
        if isinstance(v, str):
            paths.append(v)
        elif isinstance(v, list):
            paths.extend(str(x) for x in v if isinstance(x, str))
        elif isinstance(v, dict):
            paths.extend(str(x) for x in v.values() if isinstance(x, str))
    panel = r.get("panel")
    if isinstance(panel, dict) and isinstance(panel.get("path"), str):
        paths.append(panel["path"])
    return paths


def _stage_by_path(receipts) -> dict[str, str]:
    """Which stage produced the artefact at each path a receipt claims to write."""
    out = {}
    for p, r in receipts:
        stage = r.get("stage")
        if not stage:
            continue
        out[p.name.lower()] = stage
        for key in ("daily_csv", "output", "wrote"):
            v = r.get(key)
            if isinstance(v, str):
                out[Path(v).name.lower()] = stage
    return out


# ---------------------------------------------------------------------------
def test_the_stage_vocabulary_is_ordered_and_closed():
    assert STAGE_ORDER == ("raw", "normalized", "features", "signal", "weights", "pnl")
    assert set(JOB_STAGES.values()) <= set(STAGE_ORDER), (
        "a job declares a stage that is not in the vocabulary, so the order is undefined "
        "for it and the contract cannot rank it")


def test_no_receipt_reads_an_artefact_from_a_later_stage():
    receipts = _receipts()
    if not receipts:
        pytest.skip(f"no night-factory receipts on this checkout ({OPTIMUS})")
    stamped = [(p, r) for p, r in receipts if r.get("stage")]
    if not stamped:
        pytest.skip("CANNOT DETERMINE: no receipt in the corpus carries a `stage` yet. "
                    "This is not a pass -- it is the absence of anything to check.")

    producer = _stage_by_path(receipts)
    violations, unchecked = [], []
    for p, r in stamped:
        mine = r["stage"]
        paths = _declared_paths(r)
        if not paths:
            unchecked.append(p.name)
            continue
        for ref in paths:
            name = Path(ref).name.lower()
            theirs = producer.get(name)
            if theirs is None:
                continue
            if RANK.get(theirs, -1) > RANK.get(mine, 99):
                violations.append(f"{p.name} (stage {mine}) reads {name} (stage {theirs})")
    assert not violations, (
        "a receipt reads an artefact produced by a LATER stage, which is the structural "
        "leak the contract exists to stop:\n  " + "\n  ".join(sorted(violations)))
    # not an assertion -- a visible statement of what could not be checked
    print(f"[stage contract] {len(stamped)} stamped receipts, "
          f"{len(unchecked)} of them declare no inputs and were not checked: "
          f"{sorted(unchecked)[:10]}")


def test_chunk_nines_own_receipts_carry_a_stage():
    """The jobs this contract's first step was added for must actually stamp one."""
    night = OPTIMUS / "night_factory_2026-09-13"
    if not night.is_dir():
        pytest.skip("chunk 9's night directory is not on this checkout")
    seen = {}
    for p in sorted(night.glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        seen[p.name] = r.get("stage")
    if not seen:
        pytest.skip("no receipts in chunk 9's night directory yet")
    missing = sorted(k for k, v in seen.items() if not v)
    assert not missing, f"these chunk-9 receipts carry no stage: {missing}"
    assert set(seen.values()) <= set(STAGE_ORDER)


def test_a_job_without_a_declared_stage_is_named_not_defaulted():
    """A guessed stage is worse than an absent one, and the map must not guess."""
    from scripts import night_factory_jobs as nfj

    unstamped = sorted(set(nfj.JOBS) - set(JOB_STAGES))
    # This is a REPORT, not a failure: most of those jobs predate the contract
    # and giving them a default would fill the table with guesses. What must
    # hold is that the factory writes None for them rather than inventing one.
    assert JOB_STAGES.get("a_job_that_does_not_exist") is None
    print(f"[stage contract] {len(unstamped)} registered jobs declare no stage yet: {unstamped}")
    assert "E1_event_head" in JOB_STAGES and "L4_qwen3_measure" in JOB_STAGES


def test_the_cadence_pass_declares_the_last_stage():
    """The pass that turns marks into positions and NAV is `pnl`, and nothing reads it."""
    src = (REPO / "backend" / "services" / "book_cadence.py").read_text(encoding="utf-8")
    assert '"stage": "pnl"' in src, (
        "the cadence pass no longer stamps a stage, so the one artefact family that must "
        "never be read as an input is unlabelled")


def test_a_forward_read_would_actually_be_caught(tmp_path, monkeypatch):
    """The guard has to fail on a planted violation, or it proves nothing."""
    night = tmp_path / "night_factory_2026-09-13"
    night.mkdir(parents=True)
    (night / "A_pnl_run01.json").write_text(json.dumps(
        {"job": "A", "stage": "pnl", "daily_csv": str(night / "A_pnl_run01_daily.csv")}),
        encoding="utf-8")
    (night / "B_signal_run01.json").write_text(json.dumps(
        {"job": "B", "stage": "signal", "inputs": ["A_pnl_run01_daily.csv"]}), encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "OPTIMUS", tmp_path)
    with pytest.raises(AssertionError) as e:
        test_no_receipt_reads_an_artefact_from_a_later_stage()
    assert "LATER stage" in str(e.value)
    # the guard compares on lower-cased basenames, so the message carries that form
    assert "a_pnl_run01_daily.csv" in str(e.value)
