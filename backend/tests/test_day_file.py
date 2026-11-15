"""The day file (ROADMAP CH-44 part 1): synthetic receipts only, no network, no live data.

The failure these tests exist for is a section that silently disappears when its receipt is
missing: an absent source must print UNKNOWN (CANNOT_DETERMINE), a stale one RED, and every
line must name its receipt.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import day_file as DF

NOW = datetime.now(timezone.utc).replace(microsecond=0)
SENTINEL = "ZQXJ-PRIVATE-NOTE-TEXT-4471"
HEADLINE = "ZQXJ-LICENSED-HEADLINE-9926"


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


def _sched(d: datetime) -> str:
    return d.astimezone().strftime("%m/%d/%Y %I:%M:%S %p")


def _status(generated: datetime, rows: list | None = None) -> dict:
    rows = rows if rows is not None else []
    counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("OK", "DEGRADED", "DOWN", "UNKNOWN")}
    return {"receipt": "system_status", "generated_utc": _iso(generated), "counts": counts,
            "sections": {"tasks": {"rows": [r for r in rows if r["section"] == "tasks"]},
                         "learning": {"rows": [r for r in rows if r["section"] == "learning"]}}}


def _row(section: str, name: str, status: str, **kw) -> dict:
    return {"section": section, "name": name, "status": status, "detail": f"{name} detail",
            "evidence_path": f"x/{name}.json", "evidence_utc": _iso(NOW - timedelta(hours=1)), **kw}


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")


def _root(tmp_path: Path, **kw) -> Path:
    root = tmp_path / "optimus"
    root.mkdir()
    if "status" in kw:
        _write(root / "system_status" / "status.json", kw["status"])
    return root


def _build(root: Path, status_fn=None):
    return DF.build(root, now=NOW, wall=NOW, forecast_lines=lambda p: iter(()), status_fn=status_fn)


def _lines(rec: dict, key: str) -> list[dict]:
    return rec["sections"][key]["lines"]


def test_every_section_is_present_when_every_receipt_is_missing(tmp_path):
    rec = _build(_root(tmp_path))
    assert list(rec["sections"]) == [k for k, _ in DF.SECTIONS]
    for key, sec in rec["sections"].items():
        assert sec["lines"], f"{key} vanished"
        assert sec["status"] != DF.OK or key in ("schedule",), f"{key} claims OK with nothing to read"
    # the systems, cohorts, dynamic books and inbox are UNKNOWN, never omitted and never OK
    for key in ("red", "cohorts", "inbox"):
        assert rec["sections"][key]["status"] == DF.CD
    assert any("dynamic books" in ln["text"] and ln["status"] == DF.CD for ln in _lines(rec, "cohorts"))
    assert "red" in rec["sections_cannot_determine"]


def test_a_stale_systems_receipt_turns_red_and_names_down_rows(tmp_path):
    old = NOW - timedelta(hours=5)
    rows = [_row("tasks", "AegisBroken", "DOWN"), _row("learning", "learner", "DEGRADED"),
            _row("tasks", "AegisFine", "OK")]
    rec = _build(_root(tmp_path, status=_status(old, rows)))
    red = rec["sections"]["red"]
    assert red["status"] == DF.RED
    assert any("systems receipt is" in ln["text"] and ln["status"] == DF.RED for ln in red["lines"])
    down = [ln for ln in red["lines"] if ln["text"].startswith("DOWN rows")]
    assert down and "tasks/AegisBroken" in down[0]["text"] and down[0]["status"] == DF.RED
    assert red["data"]["down"] == ["tasks/AegisBroken"]
    assert not any("AegisFine" in ln["text"] for ln in red["lines"])


def test_a_fresh_systems_receipt_is_not_stale(tmp_path):
    rec = _build(_root(tmp_path, status=_status(NOW - timedelta(minutes=3), [_row("tasks", "A", "OK")])))
    assert not any("systems receipt is" in ln["text"] for ln in _lines(rec, "red"))
    assert any(ln["text"] == "no row is DOWN" for ln in _lines(rec, "red"))


def test_a_status_stamped_after_the_clock_is_unknown(tmp_path):
    rec = _build(_root(tmp_path, status=_status(NOW + timedelta(hours=2))))
    assert rec["sections"]["red"]["status"] == DF.CD
    assert rec["sections"]["schedule"]["status"] == DF.CD


def test_schedule_lists_tasks_due_today(tmp_path):
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(DF._cfg("DAY_FILE_TZ", "Asia/Hong_Kong"))
    noon = NOW.astimezone(tz).replace(hour=12, minute=0, second=0)
    rows = [_row("tasks", "AegisDueToday", "OK", extra={"next_run": _sched(noon), "last_run": "-", "last_result": "0"}),
            _row("tasks", "AegisNotToday", "OK",
                 extra={"next_run": _sched(noon + timedelta(days=3)), "last_run": "-", "last_result": "0"})]
    rec = _build(_root(tmp_path, status=_status(NOW - timedelta(minutes=2), rows)))
    sched = rec["sections"]["schedule"]
    assert sched["data"]["due_today"] == ["AegisDueToday"]
    assert any("AegisDueToday" in ln["text"] for ln in sched["lines"])
    assert not any("AegisNotToday" in ln["text"] for ln in sched["lines"])
    assert sched["data"]["next_sessions"] and len(sched["data"]["next_sessions"]) == 10


def _cohort_row(utc: datetime, **kw) -> dict:
    d = {"action": "NOTHING_DUE", "rc": 0, "through": "d", "newest_cohort": "c1", "newest_forward_cohort": None,
         "cohorts_forward": 0, "cohorts_total": 5, "cohorts_live": 5, "marks_total": 99, "forward_age_sessions": 0,
         "stale_limit_sessions": 10, "scoreboard": r"C:\elsewhere\rolling_cohorts\sb_1.json", "utc": _iso(utc)}
    d.update(kw)
    return d


def _scoreboard() -> dict:
    return {"run_id": "20260101T000000000000Z-ab", "through": "d",
            "boards": {"21": {"header_all": {"min_strict_blocks": 6}, "cohorts": [{}, {}],
                              "families_all": {"f1": {"n_blocks_strict": 1}, "f2": {"n_blocks_strict": 4}},
                              "summary": {"tests_all": 7, "cannot_determine_all": 7}}}}


def test_cohort_headline_and_still_needed(tmp_path):
    root = _root(tmp_path)
    _write(root / "rolling_cohorts" / "runs.jsonl", json.dumps(_cohort_row(NOW - timedelta(hours=1))) + "\n")
    _write(root / "rolling_cohorts" / "sb_1.json", _scoreboard())
    rec = _build(root)
    sec = rec["sections"]["cohorts"]
    txt = " | ".join(ln["text"] for ln in sec["lines"])
    assert "0 forward of 5 cohorts" in txt and "newest cohort c1" in txt
    assert "fewest 2, most 5" in txt
    assert sec["data"]["cohort_report"]["needs"] == {"f1": 5, "f2": 2}
    first = sec["lines"][0]
    assert first["status"] == DF.OK and first["receipt"] == "rolling_cohorts/runs.jsonl[-1]" and first["age_s"] > 0


def test_a_stale_cohort_journal_row_is_red(tmp_path):
    root = _root(tmp_path)
    _write(root / "rolling_cohorts" / "runs.jsonl", json.dumps(_cohort_row(NOW - timedelta(hours=40))) + "\n")
    rec = _build(root)
    assert _lines(rec, "cohorts")[0]["status"] == DF.RED
    # the named scoreboard is not on disk: UNKNOWN, not omitted
    assert any("cohort report" in ln["text"] and ln["status"] == DF.CD for ln in _lines(rec, "cohorts"))


def test_dynamic_books_present_and_stale(tmp_path):
    root = _root(tmp_path)
    row = {"action": "MARKED", "rc": 0, "through": "d", "cohorts_total": 3, "paths_total": 9,
           "utc": _iso(NOW - timedelta(hours=100))}
    _write(root / "dynamic_books" / "runs.jsonl", json.dumps(row) + "\n")
    rec = _build(root)
    dyn = [ln for ln in _lines(rec, "cohorts") if ln["text"].startswith("dynamic books")]
    assert dyn and dyn[0]["status"] == DF.RED
    row["utc"] = _iso(NOW - timedelta(hours=1))
    _write(root / "dynamic_books" / "runs.jsonl", json.dumps(row) + "\n")
    dyn = [ln for ln in _lines(_build(root), "cohorts") if ln["text"].startswith("dynamic books")]
    assert dyn[0]["status"] == DF.OK


def test_inbox_is_a_count_never_the_text(tmp_path):
    root = _root(tmp_path)
    rows = [{"kind": "note", "schema": "owner_inbox/1", "id": "n1", "utc": _iso(NOW - timedelta(hours=2)),
             "text": SENTINEL, "page": None, "status": "unread"},
            {"kind": "note", "schema": "owner_inbox/1", "id": "n2", "utc": _iso(NOW - timedelta(hours=1)),
             "text": SENTINEL + " two", "page": None, "status": "unread"},
            {"kind": "status", "schema": "owner_inbox/1", "id": "n2", "utc": _iso(NOW), "status": "read"}]
    _write(root / "owner_inbox" / "notes.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
    rec = _build(root)
    sec = rec["sections"]["inbox"]
    assert sec["data"] == {"n_unread": 1, "n_notes": 2, "unreadable_lines": 0}
    assert sec["lines"][0]["status"] == DF.RED
    assert SENTINEL not in json.dumps(rec) and SENTINEL not in DF.render_md(rec, "x.md")


def test_no_licensed_headline_or_note_text_reaches_the_file(tmp_path):
    root = _root(tmp_path)
    _write(root / "owner_inbox" / "notes.jsonl",
           json.dumps({"kind": "note", "id": "n", "utc": _iso(NOW), "text": SENTINEL, "status": "unread"}) + "\n")
    # an event-node-like store with a headline in it must not be echoed (ids/tickers/counts only)
    _write(root / "event_nodes" / "ignored.jsonl", json.dumps({"title": HEADLINE}) + "\n")
    out = tmp_path / "out"
    rec = _build(root)
    md, js, ptr = DF.write(rec, out)
    for p in (md, js, ptr, out / f"DAY_{rec['day']}.json"):
        body = p.read_text(encoding="utf-8")
        assert SENTINEL not in body and HEADLINE not in body


def test_every_line_names_its_receipt(tmp_path):
    root = _root(tmp_path, status=_status(NOW - timedelta(minutes=1), [_row("tasks", "A", "DOWN")]))
    rec = _build(root)
    for key, sec in rec["sections"].items():
        for ln in sec["lines"]:
            if ln["text"].startswith("section reader failed"):
                continue
            assert ln["receipt"], (key, ln["text"])
    assert "receipt:" in DF.render_md(rec, "x.md")


def test_output_is_byte_stable_for_fixed_inputs(tmp_path):
    root = _root(tmp_path, status=_status(NOW - timedelta(minutes=1), [_row("tasks", "A", "DOWN")]))
    a, b = _build(root), _build(root)
    assert DF.render_md(a, "f.md") == DF.render_md(b, "f.md")
    assert json.dumps(a, default=str, sort_keys=True) == json.dumps(b, default=str, sort_keys=True)


def test_write_never_touches_the_data_root_and_never_reuses_a_stamp(tmp_path):
    root = _root(tmp_path)
    before = sorted(str(p) for p in root.rglob("*"))
    rec = _build(root)
    out = tmp_path / "out"
    md, js, ptr = DF.write(rec, out)
    assert sorted(str(p) for p in root.rglob("*")) == before
    assert md.exists() and js.exists() and ptr.exists()
    assert json.loads((out / f"DAY_{rec['day']}.json").read_text(encoding="utf-8"))["schema"] == DF.SCHEMA
    with pytest.raises(OSError):
        DF.write(rec, out)


def test_refusals(tmp_path):
    with pytest.raises(DF.DayFileRefused) as e:
        DF.build(tmp_path / "nope", now=NOW, wall=NOW)
    assert e.value.code == "DATA_ROOT_MISSING"
    with pytest.raises(DF.DayFileRefused) as e:
        DF.build(_root(tmp_path), now=NOW + timedelta(days=2), wall=NOW)
    assert e.value.code == "NOW_IN_FUTURE"


def test_a_raising_section_reader_is_unknown_not_omitted(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("nope")
    monkeypatch.setattr(DF, "cohorts_section", boom)
    rec = _build(_root(tmp_path))
    assert rec["sections"]["cohorts"]["status"] == DF.CD
    assert "RuntimeError" in rec["sections"]["cohorts"]["lines"][-1]["text"]


def test_the_cli_exit_codes(tmp_path):
    root = _root(tmp_path)
    assert DF.main(["--data-root", str(root), "--out", str(tmp_path / "o")]) == 2    # unknown sources are not fine
    assert DF.main(["--data-root", str(tmp_path / "missing"), "--out", str(tmp_path / "o2")]) == 3
    assert DF.main(["--data-root", str(root), "--now", "garbage", "--out", str(tmp_path / "o3")]) == 3


def test_the_probe_reads_the_run_stamp_and_goes_stale(tmp_path):
    from types import SimpleNamespace
    root = _root(tmp_path)
    ctx = SimpleNamespace(optimus_dir=root, now=NOW)
    r0 = DF.p_day_file(ctx)
    assert r0.verdict == "UNKNOWN"
    old = NOW - timedelta(hours=60)
    stamp = old.strftime("%Y%m%dT%H%M%SZ")
    _write(root / "day_file" / f"DAY_2026-01-01__{stamp}.json",
           {"generated_utc": _iso(old), "sections_not_ok": ["red"], "replay": False})
    r1 = DF.p_day_file(ctx)
    assert r1.verdict == "STALE" and "1 section(s) not OK" in r1.detail


def test_a_replay_does_not_read_the_live_inbox(tmp_path):
    root = _root(tmp_path)
    _write(root / "owner_inbox" / "notes.jsonl",
           json.dumps({"kind": "note", "id": "n", "utc": _iso(NOW), "text": "x", "status": "unread"}) + "\n")
    rec = DF.build(root, now=NOW - timedelta(days=2), wall=NOW, forecast_lines=lambda p: iter(()))
    assert rec["replay"] is True
    assert rec["sections"]["inbox"]["status"] == DF.CD
