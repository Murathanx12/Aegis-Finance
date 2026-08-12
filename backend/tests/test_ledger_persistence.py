"""The prediction ledger has to survive a deploy (NIGHT-14, defect F7).

Until tonight the ledger resolved to a path INSIDE the container image, so on
Railway every PredictionRecord the nightly specialists wrote was destroyed by
the next push. That failure is invisible from the inside: a ledger that lost
its history is indistinguishable from a ledger that is simply young, and the
forward calibration clock — which starts at the first written record and can
never be backfilled — would have restarted at zero on every deploy right up to
the first resolution (2026-09-12).

The migration that moves ~87 real DeepSeek forecasts onto the volume is the
dangerous part, so the first test here is the one that says it must never
overwrite a destination that already holds records. The volume is authoritative
the moment it is non-empty; the in-image copy is a git snapshot that ages.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from backend.services.belief_state import (Observable, append,
                                           ensure_ledger_migrated,
                                           ledger_health, ledger_persistence,
                                           make_prediction, read_predictions)


def _pred(**kw):
    base = dict(ticker="AAA", specialist="biotech",
                observable=Observable.RETURN_SIGN, horizon_days=20,
                probability=0.6, thesis="t", counter_thesis="c",
                next_observable="n", model="m", model_version="v",
                prompt="p", input_snapshot={"ticker": "AAA"})
    base.update(kw)
    return make_prediction(**base)


def _seed(directory: Path, n: int, *, tag: str) -> list[str]:
    """Write n distinct predictions into directory/predictions.jsonl."""
    directory.mkdir(parents=True, exist_ok=True)
    # `prompt` is part of the prediction_id hash, `thesis` is not — distinct
    # prompts are what make the image-side and volume-side records different
    # records rather than the same forecast written twice.
    recs = [_pred(made_at=f"2026-0{i + 1}-0{i + 1}T00:00:00",
                  prompt=f"{tag}{i}", thesis=f"{tag}{i}")
            for i in range(n)]
    append(recs, directory / "predictions.jsonl")
    return [r.prediction_id for r in recs]


# ── the dangerous case, written first ───────────────────────────────────────
def test_a_destination_that_already_has_records_is_never_overwritten(tmp_path):
    """The one rule that makes the migration safe.

    After the first migrated boot the volume holds everything the specialists
    have written since; the image copy is a frozen git snapshot. Copying the
    snapshot over the volume would delete exactly the forward calibration this
    subsystem exists to accumulate — so a non-empty destination is untouchable,
    even when the source has MORE records than it does.
    """
    legacy, dest = tmp_path / "image", tmp_path / "volume"
    _seed(legacy, 3, tag="image")
    live_ids = _seed(dest, 1, tag="live")

    report = ensure_ledger_migrated(dest_dir=dest, legacy_dir=legacy)

    assert report["status"] == "not_needed"
    entry = report["files"]["predictions.jsonl"]
    assert entry["status"] == "destination_not_empty"
    assert entry["legacy_records"] == 3 and entry["dest_records"] == 1
    # The live record is still the only thing there, byte-identical.
    after = read_predictions(dest / "predictions.jsonl")
    assert [r["prediction_id"] for r in after] == live_ids


def test_records_only_in_the_image_copy_are_reported_not_silently_dropped(tmp_path):
    """Refusing to copy is right; refusing quietly is not.

    If the shipped ledger carries ids the volume has never seen, that divergence
    is a fact about the history and it gets counted, so a human can decide.
    """
    legacy, dest = tmp_path / "image", tmp_path / "volume"
    _seed(legacy, 3, tag="image")
    _seed(dest, 1, tag="live")
    report = ensure_ledger_migrated(dest_dir=dest, legacy_dir=legacy)
    assert report["files"]["predictions.jsonl"]["legacy_only_records"] == 3


# ── the migration itself ────────────────────────────────────────────────────
def test_an_empty_volume_receives_the_whole_history_and_the_count_round_trips(tmp_path):
    legacy, dest = tmp_path / "image", tmp_path / "volume"
    ids = _seed(legacy, 4, tag="image")
    append([_pred(made_at="2026-05-05T00:00:00")], legacy / "beliefs.jsonl")

    report = ensure_ledger_migrated(dest_dir=dest, legacy_dir=legacy)

    assert report["status"] == "migrated"
    assert report["files"]["predictions.jsonl"]["migrated_records"] == 4
    moved = read_predictions(dest / "predictions.jsonl")
    assert [r["prediction_id"] for r in moved] == ids
    # It is a COPY: the image-side file is left intact, so a failed boot after a
    # successful copy cannot land between two empty ledgers.
    assert len(read_predictions(legacy / "predictions.jsonl")) == 4
    assert (dest / "beliefs.jsonl").exists()


def test_migrating_twice_changes_nothing_the_second_time(tmp_path):
    legacy, dest = tmp_path / "image", tmp_path / "volume"
    _seed(legacy, 2, tag="image")
    first = ensure_ledger_migrated(dest_dir=dest, legacy_dir=legacy)
    second = ensure_ledger_migrated(dest_dir=dest, legacy_dir=legacy)
    assert first["status"] == "migrated"
    assert second["status"] == "not_needed"
    assert second["files"]["predictions.jsonl"]["status"] == "destination_not_empty"
    assert len(read_predictions(dest / "predictions.jsonl")) == 2


def test_a_corrupt_source_aborts_before_it_writes_a_partial_history(tmp_path):
    """Half a history is worse than a history in one place.

    A malformed line stops the copy with an error rather than producing a
    truncated destination that would then be authoritative forever.
    """
    legacy, dest = tmp_path / "image", tmp_path / "volume"
    _seed(legacy, 2, tag="image")
    with (legacy / "predictions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("{not json at all\n")

    report = ensure_ledger_migrated(dest_dir=dest, legacy_dir=legacy)

    assert report["status"] == "failed"
    assert report["files"]["predictions.jsonl"]["status"] == "failed"
    assert not (dest / "predictions.jsonl").exists()
    assert not list(dest.glob("predictions.jsonl.migrating*"))


def test_a_stale_staging_file_from_a_crashed_replica_is_inert(tmp_path):
    """Railway runs two replicas through a rolling deploy, so a killed process
    can leave a staging file behind. It carries a private per-pid name, is never
    read as ledger content, and does not block or corrupt the next migration."""
    legacy, dest = tmp_path / "image", tmp_path / "volume"
    ids = _seed(legacy, 3, tag="image")
    dest.mkdir(parents=True)
    (dest / "predictions.jsonl.migrating.99999").write_text(
        "half a record, no newline", encoding="utf-8")

    report = ensure_ledger_migrated(dest_dir=dest, legacy_dir=legacy)

    assert report["status"] == "migrated"
    assert [r["prediction_id"] for r in read_predictions(dest / "predictions.jsonl")] == ids


def test_an_empty_image_copy_is_not_an_error(tmp_path):
    legacy, dest = tmp_path / "image", tmp_path / "volume"
    legacy.mkdir()
    report = ensure_ledger_migrated(dest_dir=dest, legacy_dir=legacy)
    assert report["status"] == "not_needed"
    assert report["files"]["predictions.jsonl"]["status"] == "nothing_to_migrate"


def test_the_same_directory_is_a_declared_no_op_not_a_copy_onto_itself(tmp_path):
    """Local dev: DATA_DIR is backend/data, so source and destination ARE the
    same file. Copying it onto itself would truncate the live ledger."""
    both = tmp_path / "optimus"
    ids = _seed(both, 2, tag="local")
    report = ensure_ledger_migrated(dest_dir=both, legacy_dir=both)
    assert report["status"] == "same_path"
    assert [r["prediction_id"] for r in read_predictions(both / "predictions.jsonl")] == ids


# ── the paths themselves ────────────────────────────────────────────────────
def test_locally_the_ledger_path_is_exactly_what_it_always_was():
    """Requirement 3: with no AEGIS_DATA_DIR, nothing about dev changes.

    Resolved in a fresh interpreter because DATA_DIR is read from the
    environment at import time (same technique as test_deploy_gate.py).
    """
    probe = (
        "from backend.config import BACKEND_DIR;"
        "from backend.services.belief_state import PREDICTIONS, BELIEFS;"
        "assert PREDICTIONS == BACKEND_DIR / 'data' / 'optimus' / 'predictions.jsonl', PREDICTIONS;"
        "assert BELIEFS == BACKEND_DIR / 'data' / 'optimus' / 'beliefs.jsonl', BELIEFS;"
        "print('OK')"
    )
    env = {k: v for k, v in os.environ.items() if k != "AEGIS_DATA_DIR"}
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, f"local ledger path changed:\n{r.stdout}\n{r.stderr}"


def test_with_a_volume_configured_the_ledger_follows_it(tmp_path):
    """The F7 fix itself: AEGIS_DATA_DIR=/vol ⇒ the ledger lives on /vol."""
    vol = tmp_path / "volume"
    probe = (
        "from backend.config import DATA_DIR;"
        "from backend.services.belief_state import PREDICTIONS;"
        "assert str(PREDICTIONS).startswith(str(DATA_DIR)), (PREDICTIONS, DATA_DIR);"
        "print('OK')"
    )
    env = {**os.environ, "AEGIS_DATA_DIR": str(vol)}
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, f"ledger does not follow the volume:\n{r.stdout}\n{r.stderr}"


# ── the health surface ──────────────────────────────────────────────────────
def test_a_ledger_outside_a_configured_volume_is_degraded_with_the_reason(
        tmp_path, monkeypatch):
    """Precisely the invisible failure: a mounted volume, and a ledger not on it."""
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path / "volume"))
    row = ledger_persistence(Path("/app/backend/data/optimus/predictions.jsonl"),
                             data_dir=tmp_path / "volume")
    assert row["status"] == "DEGRADED"
    assert row["under_data_dir"] is False and row["volume_configured"] is True
    assert "destroyed by the next deploy" in row["reason"]


def test_a_ledger_on_the_configured_volume_is_ok(tmp_path, monkeypatch):
    vol = tmp_path / "volume"
    monkeypatch.setenv("AEGIS_DATA_DIR", str(vol))
    row = ledger_persistence(vol / "optimus" / "predictions.jsonl", data_dir=vol)
    assert row["status"] == "ok" and row["under_data_dir"] is True


def test_without_a_volume_the_check_says_so_instead_of_guessing(monkeypatch):
    """No AEGIS_DATA_DIR is the normal LOCAL state. Calling it DEGRADED would
    cry wolf on every dev box; calling it verified would be a fabrication — so
    it reports ok and states what it cannot distinguish."""
    monkeypatch.delenv("AEGIS_DATA_DIR", raising=False)
    row = ledger_persistence()
    assert row["status"] == "ok" and row["volume_configured"] is False
    assert "cannot distinguish" in row["note"]


def test_ledger_health_carries_the_persistence_row_and_degrades_on_it(
        tmp_path, monkeypatch):
    legacy = tmp_path / "image"
    _seed(legacy, 2, tag="image")
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path / "volume"))
    monkeypatch.setattr("backend.services.belief_state._config.DATA_DIR",
                        tmp_path / "volume")
    out = ledger_health(legacy / "predictions.jsonl", today=None)
    assert out["persistence"]["status"] == "DEGRADED"
    assert out["status"] == "DEGRADED"
    assert any("ledger persistence" in p for p in out["problems"])


def test_the_live_ledger_reports_its_persistence_row():
    """The real ledger, as this box sees it — the row must exist and be honest."""
    out = ledger_health()
    assert "persistence" in out
    assert out["persistence"]["ledger_path"].endswith("predictions.jsonl")
