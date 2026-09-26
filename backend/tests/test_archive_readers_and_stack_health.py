"""The four corpus readers exclude `pit_grade: archive` rows and COUNT them
(wave-2 handoff §3 owed), and `stack_health` is a thin wrapper over
`system_health` with `health_probe`'s exit codes.

Every fixture corpus carries one ARCHIVE row (published 2015, first seen 2026)
beside one fresh row, so each reader must keep exactly one and print 1 excluded.
Offline: tmp_path only; nothing reads `backend/data`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.services import news_registry as NR

ARCHIVE = {"published_utc": "2015-02-23T18:26:42Z", "first_seen_utc": "2026-09-10T12:00:00Z"}
FRESH = {"published_utc": "2026-09-10T11:00:00Z", "first_seen_utc": "2026-09-10T11:05:00Z"}


def _write(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_the_shared_helper_drops_and_counts_the_archive_row():
    kept, rec = NR.exclude_archive([{**ARCHIVE, "source": "s", "pit_grade": "native_stamp"},
                                    {**FRESH, "source": "s", "pit_grade": "native_stamp"},
                                    {"source": "s", "title": "no stamps at all"}])
    assert len(kept) == 2 and rec["archive_rows_excluded"] == 1
    assert rec["archive_rows_excluded_by_source"] == {"s": 1}
    assert rec["rows_without_stamp_pair"] == 1 and rec["rows_read"] == 3
    assert all("declared_pit_grade" in r for r in kept)      # graded, not raw


# ── reader 1: night_e1_news_return_panel ────────────────────────────────────

def test_e1_corpus_rows_exclude_the_archive_row(tmp_path, monkeypatch):
    from scripts import news_pull
    from scripts import night_e1_news_return_panel as e1
    root = tmp_path / "news_corpus"
    _write(root / "src_a" / "2026-09-10.jsonl", [
        {**ARCHIVE, "source": "src_a", "pit_grade": "native_stamp", "raw_id": "old",
         "tickers": ["AAA"], "title": "Facebook acquiring QuickFire Networks"},
        {**FRESH, "source": "src_a", "pit_grade": "native_stamp", "raw_id": "new",
         "tickers": ["AAA"], "title": "fresh"}])
    monkeypatch.setattr(news_pull, "corpus_dir", lambda: root)
    census: dict = {}
    rows = e1._corpus_rows(["src_a"], "", census=census)
    assert [r["raw_id"] for r in rows] == ["new"]
    assert census["archive_rows_excluded"] == 1 and census["rows_read"] == 2

    # and the receipt prints it, even on the refusal path (no bars here)
    monkeypatch.setattr(e1, "_label_sources", lambda: ["src_a"])
    monkeypatch.setattr(e1, "_data_root", lambda: tmp_path / "optimus")
    rec = e1.E1_append()
    assert rec["verdict"] == "REFUSED"
    assert rec["archive"]["archive_rows_excluded"] == 1


# ── reader 2: night_l2_typed_events ─────────────────────────────────────────

def test_l2_corpus_plan_excludes_the_archive_row(tmp_path, monkeypatch):
    from scripts import night_l2_typed_events as l2
    f = _write(tmp_path / "src_a" / "2026-09-10.jsonl", [
        {**ARCHIVE, "source": "src_a", "pit_grade": "native_stamp", "raw_id": "old",
         "title": "old", "body": "x"},
        {**FRESH, "source": "src_a", "pit_grade": "native_stamp", "raw_id": "new",
         "title": "new", "body": "y"}])
    monkeypatch.setattr(l2, "label_sources", lambda: ["src_a"])
    monkeypatch.setattr(l2, "corpus_files", lambda sources=None: [f])
    monkeypatch.setattr(l2, "load_cursor", lambda: {})
    plan = l2._corpus_plan(smoke=False, max_rows=0)
    blk = plan["block"]
    assert blk["archive"]["archive_rows_excluded"] == 1
    assert blk["rows_on_disk"] == 2 and blk["rows_after_archive_exclusion"] == 1
    assert len(plan["units"]) == 1


def test_l2_panel_exclusion_uses_the_same_rule():
    from scripts import night_l2_typed_events as l2
    df = pd.DataFrame([{**ARCHIVE, "source": "alpaca:benzinga", "uid": "a"},
                       {**FRESH, "source": "alpaca:benzinga", "uid": "b"},
                       {"published_utc": "2025-01-02T10:00:00Z", "first_seen_utc": None,
                        "source": "alpaca:benzinga", "uid": "c"}])
    kept, rec = l2.exclude_archive_panel(df)
    assert list(kept["uid"]) == ["b", "c"]
    assert rec["archive_rows_excluded"] == 1 and rec["rows_without_stamp_pair"] == 1


# ── reader 3: n5_event_compression ──────────────────────────────────────────

def test_n5_load_news_rows_excludes_the_archive_row(tmp_path):
    from scripts import n5_event_compression as n5
    _write(tmp_path / "2026-09.jsonl", [
        {**ARCHIVE, "kind": "news", "symbols": ["AAA"], "title": "old", "body": "x",
         "observed_at": "2026-09-10T12:00:00Z", "source": "src_a", "uid": "old"},
        {**FRESH, "kind": "news", "symbols": ["AAA"], "title": "new", "body": "y",
         "observed_at": "2026-09-10T11:05:00Z", "source": "src_a", "uid": "new"}])
    census: dict = {}
    df = n5.load_news_rows(tmp_path, census=census)
    assert list(df["uid"]) == ["new"]
    assert census["archive_rows_excluded"] == 1


# ── reader 4: backend/services/morning.py (the digest) ──────────────────────

def test_morning_digest_excludes_the_archive_row(tmp_path, monkeypatch):
    from backend.services import morning as M
    corpus = tmp_path / "corpus"
    _write(corpus / "2026-09.jsonl", [
        {**ARCHIVE, "observed_at": "2026-09-10T12:00:00+00:00", "symbols": ["NVDA"],
         "title": "Archive headline about chips", "body": "old", "source": "src_a"},
        {**FRESH, "observed_at": "2026-09-10T11:05:00+00:00", "symbols": ["NVDA"],
         "title": "Fresh headline about datacentre", "body": "new", "source": "src_a"}])
    monkeypatch.setattr(M, "corpus_dir", lambda: corpus)
    monkeypatch.setattr(M, "company_name_map", lambda: {"NVDA": {"nvidia"}})
    row = M.step_digest({"yesterday": "2026-09-10", "today": "2026-09-11", "run": 1,
                         "out_dir": tmp_path / "out"})
    assert row["status"] == "ok", row
    assert row["archive"]["archive_rows_excluded"] == 1
    text = json.loads(Path(row["digests_written_to"]).read_text(encoding="utf-8"))["NVDA"]
    assert "datacentre" in text and "chips" not in text


# ── stack_health: a thin wrapper over system_health ─────────────────────────

@pytest.mark.parametrize("verdicts,rc", [(["ALIVE", "UNKNOWN"], 0), (["ALIVE", "STALE"], 2),
                                         (["STALE", "DEAD"], 1), (["UNKNOWN", "UNKNOWN"], 3)])
def test_stack_health_carries_health_probe_exit_codes(monkeypatch, tmp_path, verdicts, rc):
    from backend.services import system_health as SH
    from scripts import stack_health as STH
    rows = [{"name": f"p{i}", "verdict": v, "detail": "d"} for i, v in enumerate(verdicts)]
    monkeypatch.setattr(SH, "run", lambda **kw: {"rows": rows, "path": None})
    monkeypatch.setattr(SH, "make_ctx", lambda **kw: None)
    res = STH.run()
    assert res["exit_code"] == rc and res["green"] == (rc == 0)
    assert set(res["rows"]) == {"p0", "p1"}                  # the preflight shape
    assert res["red"] == [r["name"] for r in rows if r["verdict"] in ("DEAD", "STALE")]
    assert STH.main(["--no-write"]) == rc
