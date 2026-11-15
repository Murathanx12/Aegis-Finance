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
    # no report on disk: the derived strict-block figure is printed, labelled with its unit and as NOT the report
    assert "fewest 2, most 5" in txt and "NOT the report" in txt and "a block is not a cohort" in txt
    assert sec["data"]["derived_blocks"] == {"f1": 5, "f2": 2}
    first = sec["lines"][0]
    assert first["status"] == DF.OK and first["receipt"] == "rolling_cohorts/runs.jsonl[-1]" and first["age_s"] > 0


def test_a_stale_cohort_journal_row_is_red(tmp_path):
    root = _root(tmp_path)
    _write(root / "rolling_cohorts" / "runs.jsonl", json.dumps(_cohort_row(NOW - timedelta(hours=40))) + "\n")
    rec = _build(root)
    assert _lines(rec, "cohorts")[0]["status"] == DF.RED
    # the named scoreboard is not on disk: UNKNOWN, not omitted
    assert any("no cohort_report_" in ln["text"] and ln["status"] == DF.CD for ln in _lines(rec, "cohorts"))


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
    assert "`[" in DF.render_md(rec, "x.md")


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


# ───────────────────────── fix round: schedule, inbox, TODAY, books, worst, cohorts, exit codes ─────────────────────────

def _task_row(name: str, nxt: str, last: str = "-", **kw) -> dict:
    return _row("tasks", name, "OK", extra={"next_run": nxt, "last_run": last, "last_result": "0", **kw})


def test_schedule_is_never_ok_when_half_the_task_times_are_unreadable(tmp_path):
    rows = [_task_row(f"T{i}", "N/A") for i in range(3)] + [_task_row("Tok", _sched(NOW + timedelta(hours=1)))]
    rec = _build(_root(tmp_path, status=_status(NOW - timedelta(minutes=1), rows)))
    sched = rec["sections"]["schedule"]
    assert sched["status"] == DF.CD
    assert any("system_status should emit" in ln["text"] and "next_run_utc" in ln["text"] for ln in sched["lines"])


def test_schedule_is_unknown_when_the_status_receipt_is_stale(tmp_path):
    rows = [_task_row("A", _sched(NOW + timedelta(hours=1)))]
    rec = _build(_root(tmp_path, status=_status(NOW - timedelta(hours=6), rows)))
    assert rec["sections"]["schedule"]["status"] == DF.CD
    assert rec["sections"]["red"]["status"] == DF.RED
    assert any(d.startswith("red") for d in rec["defects"])


def test_date_order_is_proven_from_the_table_never_guessed():
    # every date has both numbers <= 12: nothing proves the order, so nothing is read
    assert DF.infer_date_order(["03/04/2026 1:00:00 PM", "05/06/2026 2:00:00 PM"]) is None
    assert DF._sched_dt("03/04/2026 1:00:00 PM", None) is None
    # a first number above 12 proves day-first; dotted dates work the same way
    assert DF.infer_date_order(["15.03.2026 13:00:00", "03.04.2026 09:00:00"]) == "dmy"
    got = DF._sched_dt("03.04.2026 09:00:00", "dmy")
    assert got is not None and got.astimezone().month == 4
    # a second number above 12 proves month-first; a conflicting table proves nothing
    assert DF.infer_date_order(["03/15/2026 1:00:00 PM"]) == "mdy"
    assert DF.infer_date_order(["15/03/2026 1:00 PM", "03/15/2026 1:00 PM"]) is None
    # an unambiguous string needs no table, and an ISO field wins over the local string
    assert DF._sched_dt("11/15/2026 1:00:00 PM", None) is not None
    assert DF._sched_dt("2026-11-15 13:00:00", None) is not None
    assert DF._sched_dt("garbage", "mdy") is None
    row = {"extra": {"next_run": "03/04/2026 1:00:00 PM", "next_run_utc": _iso(NOW)}}
    assert DF._row_time(row, "next_run", None) == NOW
    # 1 PM is 13:00, not 01:00
    assert DF._sched_dt("11/15/2026 1:00:00 PM", None).astimezone().hour == 13


def test_a_garbage_inbox_is_unknown_not_zero_unread(tmp_path):
    root = _root(tmp_path)
    _write(root / "owner_inbox" / "notes.jsonl", "not json\n{broken\n")
    rec = _build(root)
    sec = rec["sections"]["inbox"]
    assert sec["status"] == DF.CD
    assert not any("0 unread" in ln["text"] for ln in sec["lines"])
    assert any(d.startswith("inbox") for d in rec["defects"])


def test_the_today_block_is_short_and_names_the_down_rows(tmp_path):
    rows = [_row("tasks", f"AegisDown{i}", "DOWN") for i in range(12)]
    rec = _build(_root(tmp_path, status=_status(NOW - timedelta(minutes=1), rows)))
    today = rec["today"]
    assert 5 <= len(today) <= 15
    down = next(x for x in today if x.startswith("DOWN rows"))
    assert "tasks/AegisDown0" in down and "(+2)" in down
    md = DF.render_md(rec, "x.md")
    assert md.splitlines()[0].startswith("# Day file") and "RED:" in md.splitlines()[0]
    assert "## TODAY" in md
    assert rec["red_sections"] and "defects" in rec


def test_red_rows_are_capped_and_counted(tmp_path):
    rows = [_row("learning", f"r{i:02d}", "DEGRADED") for i in range(25)]
    rec = _build(_root(tmp_path, status=_status(NOW - timedelta(minutes=1), rows)))
    red = rec["sections"]["red"]
    printed = [ln for ln in red["lines"] if (ln.get("extra") or {}).get("sev")]
    assert len(printed) == 10
    assert any("15 more non-OK rows" in ln["text"] for ln in red["lines"])
    assert len(red["data"]["non_ok_rows"]) == 25


def _pair(root: Path, generated: datetime, books: list, rows: list) -> str:
    rid = generated.strftime("%Y-%m-%dT%H%M%SZ")
    _write(root / "paper_accounts" / f"roi_{rid}.json", {"generated_utc": _iso(generated), "rows": rows})
    _write(root / "paper_accounts" / f"book_dna_{rid}.json", {"generated_utc": _iso(generated), "books": books})
    return rid


def _roi(account: str, family: str, roi_pct: float, vs: float, equity: float = 1000.0) -> dict:
    return {"account": account, "family": family, "status": "LIVE", "roi_pct": roi_pct, "spy_same_window_pct": 0.0,
            "vs_spy_pp": vs, "equity": equity, "last_mark": "d", "inception": "d"}


def test_books_main_accounts_top_and_bottom_and_counts(tmp_path):
    root = _root(tmp_path)
    rows = [_roi("hack1", "alpaca_fleet", 1.0, 1.0), _roi("balanced", "website_lane", 2.0, 2.0)]
    rows += [_roi(f"x{i:02d}", "llm_portfolio:lib", float(i), float(i)) for i in range(20)]
    rows += [_roi("y__random_same_band", "llm_portfolio:twin", 99.0, 99.0), _roi("z_rehearsal", "x", 98.0, 98.0)]
    books = [{"account": r["account"], "family": r["family"], "status": "LIVE", "evidence": {"label": "OBSERVED(1)"},
              "sessions_graded": 1, "weights": {"AAA": 0.5}} for r in rows]
    _pair(root, NOW - timedelta(hours=1), books, rows)
    rec = _build(root)
    d = rec["sections"]["books"]["data"]
    assert sorted(r["account"] for r in d["main"]) == ["balanced", "hack1"]
    assert len(d["top"]) == 5 and len(d["bottom"]) == 5 and d["top"][0]["account"] == "x19"
    assert all("__" not in r["account"] and "rehearsal" not in r["account"] for r in d["top"] + d["bottom"])
    assert len(d["other"]) == 22                     # the full table is in the JSON
    assert any("counted only" in ln["text"] for ln in _lines(rec, "books"))


def test_a_stale_book_pair_is_red_and_a_defect(tmp_path):
    root = _root(tmp_path)
    rows = [_roi("hack1", "alpaca_fleet", 1.0, 1.0)]
    _pair(root, NOW - timedelta(hours=80), [{"account": "hack1", "family": "alpaca_fleet", "status": "LIVE"}], rows)
    rec = _build(root)
    assert any(ln["status"] == DF.RED and "pair run" in ln["text"] for ln in _lines(rec, "books"))
    assert any(d.startswith("books") for d in rec["defects"])


def test_worst_case_headline_states_the_gap_and_counts_exclusions(tmp_path):
    root = _root(tmp_path)
    rows = [_roi("real_book", "llm_portfolio:lib", 1.0, 1.0, equity=1000.0),
            _roi("old_rehearsal", "x", 1.0, 1.0, equity=9e6),
            _roi("a__random_same_band", "llm_portfolio:twin", 1.0, 1.0, 9e6)]
    books = [{"account": r["account"], "family": r["family"], "status": "LIVE", "weights": {"AAA": 1.0}} for r in rows]
    _pair(root, NOW - timedelta(hours=1), books, rows)
    w = _build(root)["sections"]["worst"]
    assert w["data"]["n_excluded"] == 2
    texts = " | ".join(ln["text"] for ln in w["lines"])
    assert "real_book" in texts and "old_rehearsal" not in texts.split("left out")[0]
    assert "30%" in texts
    # no broker receipt in this root: the broker-held headline is UNKNOWN, never filled from a paper book
    assert w["data"]["broker_largest"] is None
    assert any(ln["status"] == DF.CD and "broker" in ln["text"].lower() for ln in w["lines"])


def _report(**kw) -> dict:
    fam = {"f1": {"21": {"vs_spy": {"planning": {"status": "OK", "cohorts_still_needed": 7, "weeks_at_cadence": 7}}}},
           "f2": {"21": {"vs_spy": {"planning": {"status": "CANNOT", "cohorts_still_needed": None}}}}}
    return {"report_id": "cohort_report_x", "n_forward": 0, "n_cohorts": 5,
            "generated_utc": _iso(NOW - timedelta(hours=2)), "section_3_horizons": {"families": fam}, **kw}


def test_cohorts_still_needed_comes_from_the_newest_report_with_its_id_and_age(tmp_path):
    root = _root(tmp_path)
    _write(root / "rolling_cohorts" / "reports" / "cohort_report_x.json", _report())
    ln = next(x for x in _lines(_build(root), "cohorts") if x["text"].startswith("cohort report"))
    assert "cohort_report_x" in ln["text"] and "fewest 7" in ln["text"] and "forward cohorts" in ln["text"]
    assert "1 families CANNOT DETERMINE" in ln["text"] and ln["status"] == DF.INFO and ln["age_s"] > 0


def test_a_stale_cohort_report_is_red_and_a_missing_one_is_unknown(tmp_path):
    root = _root(tmp_path)
    _write(root / "rolling_cohorts" / "reports" / "cohort_report_x.json",
           _report(generated_utc=_iso(NOW - timedelta(days=30))))
    ln = next(x for x in _lines(_build(root), "cohorts") if x["text"].startswith("cohort report"))
    assert ln["status"] == DF.RED
    (tmp_path / "b").mkdir()
    ln2 = next(x for x in _lines(_build(_root(tmp_path / "b")), "cohorts") if "no cohort_report_" in x["text"])
    assert ln2["status"] == DF.CD


def test_every_section_goes_red_or_unknown_on_its_own_stale_source(tmp_path, monkeypatch):
    root = _root(tmp_path, status=_status(NOW - timedelta(minutes=1), []))
    # forecasts: the newest forecast is old and one row is overdue
    old = _iso(NOW - timedelta(days=10))
    row = json.dumps({"made_at": old, "resolves_after": _iso(NOW - timedelta(days=9)), "resolved_at": None})
    rec = DF.build(root, now=NOW, wall=NOW, forecast_lines=lambda p: iter([row]))
    f = rec["sections"]["forecasts"]
    assert f["status"] == DF.RED and f["data"]["overdue"] == 1
    assert any("OVERDUE (definition" in ln["text"] for ln in f["lines"])
    # events: a store that last built three days ago on a session day
    from backend.services import event_nodes as EN
    _write(root / "event_nodes" / EN.STORE_NAME, "")
    monkeypatch.setattr(EN, "nodes_known_at", lambda st, t: {
        "nodes": {}, "newest_build_utc": _iso(NOW - timedelta(days=3)), "age_hours": 72.0,
        "n_retired": 0, "n_versions_after_t_skipped": 0})
    monkeypatch.setattr(DF, "is_session", lambda d: True)
    assert _build(root)["sections"]["events"]["status"] == DF.RED
    # dates: the forward calendar is stale
    from backend.services import forward_calendar as FC
    monkeypatch.setattr(FC, "freshness", lambda r, n: {"verdict": "STALE", "detail": "old", "evidence_utc": None})
    assert any(ln["status"] == DF.RED and "forward calendar STALE" in ln["text"]
               for ln in _build(root)["sections"]["dates"]["lines"])
    # owner calls: nothing pinned for yesterday
    assert _build(root)["sections"]["owner_calls"]["status"] == DF.RED
    # books and worst with no pair or fleet receipt: unknown, never omitted
    rec = _build(root)
    assert rec["sections"]["books"]["status"] == DF.CD
    assert rec["sections"]["worst"]["status"] in (DF.CD, DF.RED)


def test_exit_zero_when_faithful_even_with_red_content_and_two_when_defective(tmp_path):
    root = _root(tmp_path, status=_status(NOW - timedelta(minutes=2), [_row("tasks", "AegisBroken", "DOWN")]))
    _pair(root, NOW - timedelta(hours=1), [{"account": "hack1", "family": "alpaca_fleet", "status": "LIVE"}],
          [_roi("hack1", "alpaca_fleet", 1.0, 1.0)])
    _write(root / "predictions.jsonl", json.dumps({"made_at": _iso(NOW), "resolves_after": _iso(NOW + timedelta(days=1)),
                                                   "resolved_at": None}) + "\n")
    out = tmp_path / "o"
    rc = DF.main(["--data-root", str(root), "--out", str(out)])
    rec = json.loads(next(out.glob("DAY_*__*.json")).read_text(encoding="utf-8"))
    assert rec["defects"] == [] and "red" in rec["red_sections"]
    assert rc == 0
    (root / "system_status" / "status.json").write_text(json.dumps(_status(NOW - timedelta(days=2))), encoding="utf-8")
    assert DF.main(["--data-root", str(root), "--out", str(tmp_path / "o2")]) == 2


def test_a_future_now_is_refused_with_exit_three(tmp_path):
    root = _root(tmp_path)
    future = _iso(datetime.now(timezone.utc) + timedelta(days=3))
    assert DF.main(["--data-root", str(root), "--now", future, "--out", str(tmp_path / "o")]) == 3
    assert not (tmp_path / "o").exists()


def test_no_absolute_path_of_another_checkout_reaches_the_page(tmp_path):
    assert DF.clean_path(r"C:\Users\x\aegis-runtime-1\backend\data\optimus\rolling_cohorts\runs.jsonl[-1]") == \
        "rolling_cohorts/runs.jsonl[-1]"
    assert DF.clean_path(r"C:\Users\x\wt\backend\data\fomc_schedule.json") == "repo:backend/data/fomc_schedule.json"
    assert DF.clean_path(r"C:\elsewhere\notes\f.txt") == "<abs>/f.txt"
    assert DF.clean_path("GET http://127.0.0.1:8080/health failed") == "GET http://127.0.0.1:8080/health failed"
    rec = _build(_root(tmp_path))
    assert str(tmp_path) not in json.dumps(rec) + DF.render_md(rec, "x.md")
