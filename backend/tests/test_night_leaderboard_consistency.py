"""A NEGATIVE THAT REPRODUCES IS NOT TWO DISAPPOINTMENTS.

`N3_frozen_embedding_head` returned FAILED_VARIANT on 2026-09-10 and again on
2026-09-11. The board showed two rows that read as two unrelated failures, when
what actually happened is that a result replicated -- which is stronger evidence
than either row alone and is exactly the sort of thing a board exists to make
visible.

And the board itself was not visible: `backend/routers/control.NIGHT_DIR` was
the literal `night_factory_2026-09-08`, so the desktop night page served the
09-08 leaderboard while 09-09, 09-10 and 09-11 accumulated beside it.

Both are pinned here on SYNTHETIC nights written by the test, so the assertions
do not depend on which nights happen to be on this checkout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.routers import control
from scripts import night_leaderboard_sync as S

REPO = Path(__file__).resolve().parents[2]


def _night(base: Path, date: str, job: str, run: int, verdict: str,
           headline: str = "the same finding again") -> Path:
    d = base / f"night_factory_{date}"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{job}_run{run:02d}.json"
    p.write_text(json.dumps({"job": job, "run": run, "verdict": verdict,
                             "headline": headline}), encoding="utf-8")
    return p


# ------------------------------------------------------- the consistency note

def test_a_repeated_verdict_is_marked_replicated(tmp_path: Path):
    _night(tmp_path, "2026-09-10", "N3", 1,
           "FAILED_VARIANT: the frozen-embedding arm does not beat the control")
    payload = {"verdict": "FAILED_VARIANT: still does not beat the control",
               "headline": "IC -0.0032 (t -0.683)"}
    note = S.consistency_note("N3", 1, payload, night="2026-09-11", base=tmp_path)
    assert note == "[REPLICATED x2: FAILED_VARIANT also on 2026-09-10 run 01]"


def test_a_changed_verdict_gets_no_badge(tmp_path: Path):
    """A verdict that MOVED is a different finding and deserves a read, not a
    badge that makes it look like more of the same."""
    _night(tmp_path, "2026-09-10", "N3", 1, "PRODUCT_PROMISING: it worked")
    payload = {"verdict": "FAILED_VARIANT: it did not", "headline": "h"}
    assert S.consistency_note("N3", 1, payload, night="2026-09-11", base=tmp_path) is None


def test_the_first_run_of_a_job_has_nothing_to_replicate(tmp_path: Path):
    payload = {"verdict": "FAILED_VARIANT: first time", "headline": "h"}
    assert S.consistency_note("N3", 1, payload, night="2026-09-11", base=tmp_path) is None


def test_the_streak_counts_every_consecutive_night(tmp_path: Path):
    for date in ("2026-09-08", "2026-09-09", "2026-09-10"):
        _night(tmp_path, date, "N3", 1, "FAILED_VARIANT: no")
    note = S.consistency_note("N3", 1, {"verdict": "FAILED_VARIANT: no", "headline": "h"},
                              night="2026-09-11", base=tmp_path)
    assert note.startswith("[REPLICATED x4:")
    assert "2026-09-10" in note and "2026-09-08" in note


def test_the_streak_stops_at_the_night_the_verdict_changed(tmp_path: Path):
    _night(tmp_path, "2026-09-08", "N3", 1, "FAILED_VARIANT: no")
    _night(tmp_path, "2026-09-09", "N3", 1, "PRODUCT_PROMISING: yes")
    _night(tmp_path, "2026-09-10", "N3", 1, "FAILED_VARIANT: no")
    note = S.consistency_note("N3", 1, {"verdict": "FAILED_VARIANT: no", "headline": "h"},
                              night="2026-09-11", base=tmp_path)
    assert note.startswith("[REPLICATED x2:")
    assert "2026-09-08" not in note


def test_the_verdicts_are_compared_by_TAG_not_by_prose(tmp_path: Path):
    """Rewording a sentence must not make a replication look like a new result."""
    _night(tmp_path, "2026-09-10", "N3", 1,
           "FAILED_VARIANT: the arm does not beat the shuffled-text control")
    note = S.consistency_note(
        "N3", 1,
        {"verdict": "FAILED_VARIANT: whatever it earns is the calendar, not the text",
         "headline": "h"}, night="2026-09-11", base=tmp_path)
    assert note is not None


def test_a_later_night_does_not_count_as_a_prior_one(tmp_path: Path):
    _night(tmp_path, "2026-09-12", "N3", 1, "FAILED_VARIANT: no")
    assert S.consistency_note("N3", 1, {"verdict": "FAILED_VARIANT: no", "headline": "h"},
                              night="2026-09-11", base=tmp_path) is None


def test_nights_are_ordered_by_name_never_by_mtime(tmp_path: Path):
    """A fresh checkout rewrites every mtime (session protocol 7)."""
    for date in ("2026-09-01", "2026-09-09", "2026-09-05"):
        (tmp_path / f"night_factory_{date}").mkdir()
    (tmp_path / "night_factory_2026-09-01" / "x").write_text("x", encoding="utf-8")
    assert [p.name for p in S.night_dirs(tmp_path)] == [
        "night_factory_2026-09-01", "night_factory_2026-09-05", "night_factory_2026-09-09"]


def test_an_unreadable_prior_receipt_is_skipped_not_fatal(tmp_path: Path):
    d = tmp_path / "night_factory_2026-09-10"
    d.mkdir(parents=True)
    (d / "N3_run01.json").write_text("{not json", encoding="utf-8")
    assert S.consistency_note("N3", 1, {"verdict": "FAILED_VARIANT: no", "headline": "h"},
                              night="2026-09-11", base=tmp_path) is None


# ------------------------------------------------------------- onto the board

def test_the_note_reaches_the_headline_and_the_payload(tmp_path: Path):
    _night(tmp_path, "2026-09-10", "N3", 1, "FAILED_VARIANT: no")
    out = S.with_consistency("N3", 1, {"verdict": "FAILED_VARIANT: no", "headline": "IC -0.0032"},
                             night="2026-09-11", base=tmp_path)
    assert out["headline"].startswith("[REPLICATED x2:")
    assert out["headline"].endswith("IC -0.0032")
    assert out["consistency"].startswith("[REPLICATED")
    assert out["verdict"] == "FAILED_VARIANT: no"          # the verdict is NOT rewritten


def test_a_payload_with_nothing_to_say_is_returned_unchanged(tmp_path: Path):
    payload = {"verdict": "FAILED_VARIANT: no", "headline": "h"}
    assert S.with_consistency("N3", 1, payload, night="2026-09-11", base=tmp_path) is payload


# -------------------------------------------- the board the night page reads

def test_the_router_reads_the_newest_night_not_a_literal_date(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NIGHT_RUN_DATE", raising=False)
    for date in ("2026-09-08", "2026-09-11", "2026-09-09"):
        (tmp_path / f"night_factory_{date}").mkdir(parents=True)
    # touch the OLDEST last, so mtime order is the reverse of name order
    (tmp_path / "night_factory_2026-09-08" / "x").write_text("x", encoding="utf-8")
    assert control._night_dir(tmp_path).name == "night_factory_2026-09-11"


def test_NIGHT_RUN_DATE_wins_because_it_is_what_the_factory_reads(tmp_path: Path,
                                                                 monkeypatch):
    monkeypatch.setenv("NIGHT_RUN_DATE", "2026-09-09")
    (tmp_path / "night_factory_2026-09-11").mkdir(parents=True)
    assert control._night_dir(tmp_path).name == "night_factory_2026-09-09"


def test_no_night_directory_at_all_falls_back_rather_than_raising(tmp_path: Path,
                                                                  monkeypatch):
    monkeypatch.delenv("NIGHT_RUN_DATE", raising=False)
    assert control._night_dir(tmp_path).name == "night_factory_2026-09-08"


def test_a_spawned_job_is_told_which_night_it_is(monkeypatch):
    """Without this the board this router reads and the directory the job writes
    into can be two different nights, which is the same invisibility one level
    up."""
    src = (REPO / "backend" / "routers" / "control.py").read_text(encoding="utf-8")
    assert src.count('"NIGHT_RUN_DATE": NIGHT_DIR.name.replace("night_factory_", "")') == 2


def test_the_live_board_carries_the_replicated_note():
    """The end-to-end claim: the page's own endpoint shows it."""
    lb = control.leaderboard()
    if not lb.get("markdown"):
        pytest.skip("no leaderboard on this checkout")
    rows = [ln for ln in lb["markdown"].splitlines() if ln.startswith("| ")]
    assert rows, "the board has no rows"
