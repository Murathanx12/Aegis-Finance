"""C15 (2026-10-07): row supersession on the twin boards is OWNED BY THE WRITER.

C19's reader fix wrote `hyp_lab/board_supersessions.json` by hand (review F2). The board
writer (`scripts/hyp_twin_board.py`) now stamps `supersedes_rows: [{run_id, rule}]` into a
supplement's summary, and ONE function regenerates the file from the summaries. The two
2026-10-07 supplements (FT_2026-10-07_2, STK_2026-10-07_3) predate the stamp; they are
carried by `BACKFILL_SUPERSEDES`, never by editing a written summary. Offline.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import legibility as L
from scripts import hyp_twin_board as H

LIQW, QC = "mom_12_1_liqw", "qc623_mom63_liquidity_weighted"


def _summary(folder: Path, run: str, kind: str, rules: list[str], hours_ago: float = 0.0, **extra) -> None:
    (folder / f"twin_board_SUMMARY_{run}.json").write_text(json.dumps({
        "schema": "hyp_lab/twin_board/3", "run_id": run, "twin_kind": kind,
        "written_utc": (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds"),
        "summary": {"n_rules": len(rules)}, **extra}), encoding="utf-8")
    with open(folder / f"twin_board_{run}.jsonl", "w", encoding="utf-8") as fh:
        for i, r in enumerate(rules):
            fh.write(json.dumps({"rule": r, "family": "momentum", "twin_kind": kind,
                                 "status": "OK" if r != "refused_rule" else "REFUSED: x",
                                 "fair_twin_net": {"validate": {"t": -2.56 if run.endswith("_2") and kind == "sticky"
                                                                else -1.05 + i}}}) + "\n")


def _world(folder: Path) -> None:
    full = [LIQW, QC] + [f"rule_{i}" for i in range(5)]
    _summary(folder, "STK_2026-10-07_2", "sticky", full, hours_ago=5)
    _summary(folder, "FT_2026-10-07_1", "basket", full, hours_ago=5)
    _summary(folder, "STK_2026-10-07_3", "sticky", [LIQW, QC], hours_ago=2)   # pre-stamp supplements
    _summary(folder, "FT_2026-10-07_2", "basket", [LIQW, QC], hours_ago=2)


def test_the_two_1007_supplements_regenerate_the_hand_written_file(tmp_path):
    _world(tmp_path)
    got = H.supersessions_from_summaries(tmp_path)
    by = {s["supplement_run"]: s for s in got["supersessions"]}
    assert set(by) == {"STK_2026-10-07_3", "FT_2026-10-07_2"}
    assert by["STK_2026-10-07_3"]["supersedes_runs"] == ["STK_2026-10-07_2"]
    assert by["FT_2026-10-07_2"]["supersedes_runs"] == ["FT_2026-10-07_1"]
    for s in by.values():
        assert s["rules"] == [LIQW, QC] and "amihud" in s["why"] and "BACKFILL" in s["stamp"]
    assert got["from_summaries"] == [] and len(got["from_backfill"]) == 2 and got["refused"] == []


def test_a_stamped_supplement_is_read_from_its_own_summary_and_refused_rows_supersede_nothing(tmp_path):
    _world(tmp_path)
    _summary(tmp_path, "STK_2026-10-09_1", "sticky", [QC, "refused_rule"],
             supersedes_rows=[{"run_id": "STK_2026-10-07_2", "rule": QC}],
             supersedes_why="a corrected cost column")
    got = H.supersessions_from_summaries(tmp_path)
    new = [s for s in got["supersessions"] if s["supplement_run"] == "STK_2026-10-09_1"]
    assert new == [{"supplement_run": "STK_2026-10-09_1", "twin_kind": "sticky",
                    "supersedes_runs": ["STK_2026-10-07_2"], "rules": [QC], "why": "a corrected cost column",
                    "stamp": "summary.supersedes_rows"}]
    assert got["from_summaries"] == ["twin_board_SUMMARY_STK_2026-10-09_1.json"]


def test_the_written_file_is_what_the_theory_lab_reader_overlays(tmp_path):
    _world(tmp_path)
    body = H.write_supersessions(tmp_path)
    on_disk = json.loads((tmp_path / H.SUPERSESSIONS_FILE).read_text(encoding="utf-8"))
    assert body["status"] == "OK"
    assert on_disk["sha256"] == body["sha256"] and "WRITER" in on_disk["written_by"]
    board, refs = L._twin_board(tmp_path, "STK", datetime.now(timezone.utc), with_rows=True)
    assert board["run_id"] == "STK_2026-10-07_2"
    rows = {r["rule"]: r for r in board["rows"]}
    assert rows[LIQW]["source_run"] == "STK_2026-10-07_3" and rows[LIQW]["superseded_in"] == "STK_2026-10-07_2"
    assert rows["rule_0"].get("source_run") in (None, "")
    assert [a["supplement_run"] for a in board["supersessions_applied"]] == ["STK_2026-10-07_3"]


def test_supersedes_without_only_and_why_is_refused_before_scoring(capsys):
    assert H.main(["--run-id", "X_1", "--supersedes", "STK_2026-10-07_2"]) == 2
    assert "REFUSED" in capsys.readouterr().out
    assert H.main([]) == 2                                           # no run id, no regenerate flag


# ── review C15 M3: the writer validates the board it supersedes ──────────────

def test_the_backfill_table_is_closed():
    """No third entry without a stamp: a new supplement stamps `supersedes_rows` itself."""
    assert sorted(H.BACKFILL_SUPERSEDES) == ["FT_2026-10-07_2", "STK_2026-10-07_3"]


@pytest.mark.parametrize("target,kind,rules,why", [
    ("STK_2099-01-01_1", "sticky", [QC], "does not exist"),
    ("FT_2026-10-07_1", "sticky", [QC], "twin kind"),
    ("STK_2026-10-07_2", "sticky", ["never_scored_rule"], "never scored"),
    ("STK_2026-10-07_2", "sticky", [LIQW], "already superseded by STK_2026-10-07_3"),
])
def test_a_bad_supersedes_target_is_refused_before_scoring(tmp_path, target, kind, rules, why):
    _world(tmp_path)
    bad = H.check_supersedes_target(tmp_path, [target], kind, rules, "STK_2026-10-09_1")
    assert any(why in b for b in bad), bad


def test_a_stamp_against_a_newer_board_refuses_the_whole_file(tmp_path):
    _world(tmp_path)
    before = H.write_supersessions(tmp_path)
    assert before["status"] == "OK"
    _summary(tmp_path, "STK_2026-10-06_9", "sticky", [QC], hours_ago=9,           # OLDER than its target
             supersedes_rows=[{"run_id": "STK_2026-10-07_2", "rule": QC}], supersedes_why="x")
    out = H.write_supersessions(tmp_path)
    assert out["status"] == "REFUSED" and "not older" in " ".join(out["refused"][0]["why"])
    on_disk = json.loads((tmp_path / H.SUPERSESSIONS_FILE).read_text(encoding="utf-8"))
    assert on_disk["sha256"] == before["sha256"]                                  # previous file kept
