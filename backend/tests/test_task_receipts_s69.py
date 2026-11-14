"""S69 (2026-11-14, CH-22a §5.8): the eleven tasks added 11-11 .. 11-14 are judged by
the receipt each job writes. Every reader gets fresh-OK, stale, refused and unreadable
cases on synthetic fixtures under tmp_path; every date is derived from a passed-in
`now` (protocol item 5). The live data folder is never read.
"""

from __future__ import annotations

import json
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import system_health as SH
from backend.services import task_receipts as TR

NEW_TASKS = ("AegisEventNodes", "AegisForwardCalendar", "AegisOwnerCallsRecord", "AegisDiscoveryAutopsy",
             "AegisRawSecCollection", "AegisLabNight", "AegisNewsOverlayBook", "AegisLLMSelectorBook",
             "AegisSystemStatus", "AegisOwnerEventWarning", "AegisCodexDaemonAtLogon")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _w(p: Path, obj) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    return p


def _jl(p: Path, rows: list) -> Path:
    return _w(p, "\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n")


def _ctx(tmp_path: Path, now: datetime, **paths) -> SH.ProbeCtx:
    od = tmp_path / "optimus"
    od.mkdir(parents=True, exist_ok=True)
    return SH.ProbeCtx(optimus_dir=od, now=now, repo=tmp_path / "repo", prev_state={},
                       paths={"terminal_repo": tmp_path / "no_terminal", **paths},
                       run=lambda argv, t: (None, "not installed"), pid_cmdline=lambda pid: None)


def _task(name: str, **kw) -> dict:
    return {"TaskName": "\\" + name, "Scheduled Task State": "Enabled",
            "Last Run Time": "-", "Last Result": "0", "Next Run Time": "-", **kw}


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _wrapper(ctx, module: str, argv: list, rc: int, at: datetime, pid: int = 4242) -> None:
    p = ctx.optimus_dir / "runtime_switch" / "runtime_task_runs.jsonl"
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []
    rows += [{"wrapper_pid": pid, "utc": _iso(at - timedelta(seconds=5)), "event": "start", "segment": 0,
              "argv": ["-m", module, *argv]},
             {"wrapper_pid": pid, "utc": _iso(at), "event": "end", "segment": 0, "module": module, "rc": rc}]
    _jl(p, rows)
    ctx.cache.pop("runtime_task_runs_tail", None)


def _j(ctx, name, task=None):
    return TR.judge(ctx, name, task or _task(name))


# ─────────────────────────────────────────── registry


def test_every_new_task_is_declared_with_a_cadence():
    from backend import config as C
    for n in NEW_TASKS:
        assert n in TR.TASK_RECEIPT, n
        spec = TR.TASK_RECEIPT[n]
        assert spec.retired or n in C.HEALTH_TASK_CADENCE_H, n
    assert TR.TASK_RECEIPT["AegisCodexDaemonAtLogon"].retired


@pytest.mark.parametrize("name", NEW_TASKS)
def test_no_new_task_prints_no_receipt_is_declared(tmp_path, name):
    j = _j(_ctx(tmp_path, _now()), name)
    assert "no receipt is declared" not in j.detail and j.state != "ALIVE_PROGRESSING", (name, j.detail)


def test_codex_daemon_is_retired_and_named_for_deletion(tmp_path):
    j = _j(_ctx(tmp_path, _now()), "AegisCodexDaemonAtLogon",
           _task("AegisCodexDaemonAtLogon", **{"Scheduled Task State": "Disabled"}))
    assert j.state == "DEGRADED" and "schtasks /Delete /TN AegisCodexDaemonAtLogon" in j.detail


# ─────────────────────────────────────────── wrapper outcome matching


def test_wrapper_ignores_manual_runs_and_pairs_by_pid(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _wrapper(ctx, "scripts.event_nodes", ["daily", "--data-root", "x"], 0, now - timedelta(minutes=30), pid=1)
    _wrapper(ctx, "scripts.event_nodes", ["daily", "--help"], 2, now - timedelta(minutes=5), pid=2)
    _wrapper(ctx, "scripts.event_nodes", ["verify", "--out", "x"], 2, now - timedelta(minutes=4), pid=3)
    o = TR.wrapper_outcome(ctx, "scripts.event_nodes", ("daily",))
    assert o["rc"] == 0 and o["utc"] == now - timedelta(minutes=30)


def test_wrapper_reads_a_wrapper_refusal_row(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _jl(ctx.optimus_dir / "runtime_switch" / "runtime_task_runs.jsonl",
        [{"utc": _iso(now - timedelta(minutes=1)), "event": "refused", "wrapper_pid": 9, "rc": 90,
          "why": "split brain", "argv": ["--pythonw", "-m", "scripts.owner_calls", "record"]}])
    o = TR.wrapper_outcome(ctx, "scripts.owner_calls", ("record",))
    assert o["rc"] == 90 and o["event"] == "refused"


# ─────────────────────────────────────────── AegisEventNodes


def _event_latest(ctx, now, **kw):
    d = {"schema": "event-nodes-daily/1", "build_id": "en_x", "now": _iso(now), "n_events": 10,
         "appended_versions": 1, "chain": {"ok": True, "n": 5}, "read": {"rows_read": 100},
         "graph": {"status": "OK"}, "calendar": {"status": "OK"}, "catalyst_calendar": {"status": "OK"}}
    d.update(kw)
    _w(ctx.optimus_dir / "event_nodes" / "daily_latest.json", d)


def test_event_nodes_fresh_ok(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _event_latest(ctx, now - timedelta(minutes=10))
    _wrapper(ctx, "scripts.event_nodes", ["daily"], 0, now - timedelta(minutes=9))
    assert _j(ctx, "AegisEventNodes").state == "ALIVE_PROGRESSING"


def test_event_nodes_stale(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _event_latest(ctx, now - timedelta(hours=3))
    assert _j(ctx, "AegisEventNodes").state == "STALE"


def test_event_nodes_refusal_after_the_receipt_is_refused(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _event_latest(ctx, now - timedelta(minutes=20))
    _wrapper(ctx, "scripts.event_nodes", ["daily"], 2, now - timedelta(minutes=2))
    j = _j(ctx, "AegisEventNodes")
    assert j.state == "REFUSED" and "rc 2" in j.detail


def test_event_nodes_broken_chain_or_missing_input_is_degraded(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _event_latest(ctx, now - timedelta(minutes=5), chain={"ok": False, "n": 5}, calendar={"status": "MISSING"})
    j = _j(ctx, "AegisEventNodes")
    assert j.state == "DEGRADED" and "chain.ok=False" in j.detail and "calendar=MISSING" in j.detail


def test_event_nodes_unreadable_is_unknown(tmp_path):
    ctx = _ctx(tmp_path, _now())
    _w(ctx.optimus_dir / "event_nodes" / "daily_latest.json", "{not json")
    j = _j(ctx, "AegisEventNodes")
    assert j.state == "UNKNOWN" and "cannot be read" in j.detail


# ─────────────────────────────────────────── AegisForwardCalendar


def _fc(ctx, t: datetime, status="OK", scope="FULL_UNIVERSE", name=None):
    stamp = t.strftime("%Y%m%dT%H%M%SZ")
    _w(ctx.optimus_dir / "forward_calendar" / "snapshots" / (name or f"fc_{stamp}_abcdef_receipt.json"),
       {"receipt": "forward_calendar_pull", "pull_id": f"fc_{stamp}_abcdef", "scope": scope, "status": status,
        "finished_utc": _iso(t), "requested": 100, "answered": 99, "with_date": 30, "answered_share": 0.99,
        "min_answered_share": 0.9, "date_share": 0.3 if status == "OK" else 0.1, "min_date_share": 0.2,
        "earnings_fields_share": 0.9, "min_earnings_fields_share": 0.8})


def test_forward_calendar_fresh_ok_and_partial_ignored(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _fc(ctx, now - timedelta(hours=2))
    _fc(ctx, now - timedelta(minutes=5), status="LOW_DATE_SHARE", scope="PARTIAL")
    assert _j(ctx, "AegisForwardCalendar").state == "ALIVE_PROGRESSING"


def test_forward_calendar_stale(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _fc(ctx, now - timedelta(hours=50))
    assert _j(ctx, "AegisForwardCalendar").state == "STALE"


def test_forward_calendar_low_date_share_is_refused(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _fc(ctx, now - timedelta(hours=1), status="LOW_DATE_SHARE")
    _wrapper(ctx, "scripts.forward_calendar", ["pull", "--data-root", "x"], 2, now - timedelta(minutes=59))
    j = _j(ctx, "AegisForwardCalendar")
    assert j.state == "REFUSED" and "LOW_DATE_SHARE" in j.detail and "date share 0.1" in j.detail


def test_forward_calendar_lock_skip_is_not_a_refusal(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _fc(ctx, now - timedelta(hours=1))
    _wrapper(ctx, "scripts.forward_calendar", ["pull", "--data-root", "x"], 3, now - timedelta(minutes=1))
    j = _j(ctx, "AegisForwardCalendar")
    assert j.state == "ALIVE_PROGRESSING" and "SKIP_PULL_LOCKED" in j.detail


def test_forward_calendar_refusal_without_receipt_is_refused(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _fc(ctx, now - timedelta(hours=20))
    _wrapper(ctx, "scripts.forward_calendar", ["pull", "--data-root", "x"], 2, now - timedelta(minutes=1))
    assert _j(ctx, "AegisForwardCalendar").state == "REFUSED"


def test_forward_calendar_unreadable_newest_is_unknown(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _fc(ctx, now - timedelta(hours=20))
    _w(ctx.optimus_dir / "forward_calendar" / "snapshots" /
       f"fc_{(now - timedelta(hours=1)).strftime('%Y%m%dT%H%M%SZ')}_ffffff_receipt.json", "garbage")
    assert _j(ctx, "AegisForwardCalendar").state == "UNKNOWN"


# ─────────────────────────────────────────── AegisOwnerCallsRecord


def _states(ctx, t: datetime, extra: str = ""):
    row = {"schema": "owner-call-state/1", "day": (t - timedelta(days=1)).date().isoformat(),
           "recorded_utc": _iso(t), "prev": "GENESIS", "seal": "abc"}
    _w(ctx.optimus_dir / "owner_calls" / "states.jsonl", json.dumps(row) + "\n" + extra)


def test_owner_calls_fresh_ok(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _states(ctx, now - timedelta(hours=3))
    assert _j(ctx, "AegisOwnerCallsRecord").state == "ALIVE_PROGRESSING"


def test_owner_calls_stale(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _states(ctx, now - timedelta(hours=40))
    assert _j(ctx, "AegisOwnerCallsRecord").state == "STALE"


def test_owner_calls_broken_chain_rc2_is_refused(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _states(ctx, now - timedelta(hours=3))
    _wrapper(ctx, "scripts.owner_calls", ["record"], 2, now - timedelta(minutes=10))
    assert _j(ctx, "AegisOwnerCallsRecord").state == "REFUSED"


def test_owner_calls_unreadable_is_unknown(tmp_path):
    ctx = _ctx(tmp_path, _now())
    _w(ctx.optimus_dir / "owner_calls" / "states.jsonl", "garbage\nmore garbage\n")
    assert _j(ctx, "AegisOwnerCallsRecord").state == "UNKNOWN"


# ─────────────────────────────────────────── AegisDiscoveryAutopsy


def _autopsy(ctx, t: datetime, degradations=()):
    _jl(ctx.optimus_dir / "discovery_autopsy" / "index.jsonl",
        [{"session": (t - timedelta(days=1)).date().isoformat(), "run_id": t.strftime("%Y%m%dT%H%M%SZ"),
          "receipt": "autopsy_x.json", "summary": {"degradations": list(degradations)}}])


def test_autopsy_fresh_ok(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _autopsy(ctx, now - timedelta(hours=2))
    assert _j(ctx, "AegisDiscoveryAutopsy").state in TR.ALIVE_STATES


def test_autopsy_stale(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _autopsy(ctx, now - timedelta(days=9))
    assert _j(ctx, "AegisDiscoveryAutopsy").state == "STALE"


def test_autopsy_refusal_and_degradation(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _autopsy(ctx, now - timedelta(hours=2), degradations=["digest missing"])
    assert _j(ctx, "AegisDiscoveryAutopsy").state == "DEGRADED"
    _autopsy(ctx, now - timedelta(hours=2))
    _wrapper(ctx, "scripts.discovery_autopsy", ["--data-root", "x", "--daily"], 2, now - timedelta(minutes=3))
    assert _j(ctx, "AegisDiscoveryAutopsy").state == "REFUSED"


def test_autopsy_unreadable_is_unknown(tmp_path):
    ctx = _ctx(tmp_path, _now())
    _w(ctx.optimus_dir / "discovery_autopsy" / "index.jsonl", "nope\n")
    assert _j(ctx, "AegisDiscoveryAutopsy").state == "UNKNOWN"


# ─────────────────────────────────────────── AegisRawSecCollection


def _raw(folder: Path, t: datetime, status: str, reason: str, pid: int = 1, fails: int = 0):
    _w(folder / f"{t.strftime('%Y%m%dT%H%M%SZ')}_{pid}.json",
       {"job": "keyless_sec_raw_collection", "status": status, "reason": reason, "started_utc": _iso(t),
        "written_utc": _iso(t + timedelta(seconds=5)), "rows_new": 0, "consecutive_failures": fails})


def _raw_ctx(tmp_path, now):
    folder = tmp_path / "raw_receipts"
    return _ctx(tmp_path, now, raw_sec_receipts=folder), folder


def test_raw_sec_fresh_ok_through_a_newer_yield(tmp_path):
    now = _now()
    ctx, f = _raw_ctx(tmp_path, now)
    _raw(f, now - timedelta(minutes=50), "OK", "CAUGHT_UP_INDEX_VERIFIED_NO_EX99")
    _raw(f, now - timedelta(minutes=5), "REFUSED", "CORPUS_WRITER_ACTIVE", pid=2)
    j = _j(ctx, "AegisRawSecCollection")
    assert j.state == "ALIVE_PROGRESSING" and "1 newer yield" in j.detail


def test_raw_sec_yield_does_not_hide_an_older_refusal(tmp_path):
    now = _now()
    ctx, f = _raw_ctx(tmp_path, now)
    _raw(f, now - timedelta(minutes=50), "REFUSED", "SOURCE_FAILURE", fails=1)
    _raw(f, now - timedelta(minutes=5), "REFUSED", "CORPUS_WRITER_ACTIVE", pid=2)
    j = _j(ctx, "AegisRawSecCollection")
    assert j.state == "REFUSED" and "SOURCE_FAILURE" in j.detail


def test_raw_sec_backoff_is_degraded_and_old_is_stale(tmp_path):
    now = _now()
    ctx, f = _raw_ctx(tmp_path, now)
    _raw(f, now - timedelta(minutes=10), "SKIPPED", "BACKOFF", fails=3)
    assert _j(ctx, "AegisRawSecCollection").state == "DEGRADED"
    ctx2, f2 = _raw_ctx(tmp_path / "b", now)
    _raw(f2, now - timedelta(hours=3), "OK", "ROWS_WRITTEN")
    assert _j(ctx2, "AegisRawSecCollection").state == "STALE"


def test_raw_sec_unreadable_is_unknown(tmp_path):
    now = _now()
    ctx, f = _raw_ctx(tmp_path, now)
    _w(f / f"{now.strftime('%Y%m%dT%H%M%SZ')}_7.json", "")
    assert _j(ctx, "AegisRawSecCollection").state == "UNKNOWN"


# ─────────────────────────────────────────── AegisLabNight


def _lab(ctx, tick: datetime, started: datetime, ticks: int = 60):
    _w(ctx.optimus_dir / "lab_status.json", {"receipt": "always_on_lab", "utc": _iso(tick),
                                              "started_utc": _iso(started), "ticks": ticks, "pid": 11,
                                              "heartbeat_minutes": 5})


def _lock(ctx, started: datetime):
    _w(ctx.optimus_dir / "always_on_lab_lock.json", {"pid": 12, "started_utc": _iso(started),
                                                      "previous_exit_reason": "not_recorded (killed or crashed)"})


def _day_at(d, hh, mm=0) -> datetime:
    return datetime.combine(d, dtime(hh, mm), timezone.utc)


def test_lab_night_outside_window_after_a_good_night_is_idle(tmp_path):
    today = _now().date()
    now = _day_at(today, 8)
    ctx = _ctx(tmp_path, now)
    y = today - timedelta(days=1)
    _lab(ctx, _day_at(y, 22, 10), _day_at(y, 15))
    _lock(ctx, _day_at(y, 15))
    j = _j(ctx, "AegisLabNight")
    assert j.state == "ALIVE_IDLE_EXPECTED", j.detail


def test_lab_night_with_a_start_and_no_tick_is_degraded(tmp_path):
    today = _now().date()
    now = _day_at(today, 8)
    ctx = _ctx(tmp_path, now)
    y, yy = today - timedelta(days=1), today - timedelta(days=2)
    _lab(ctx, _day_at(yy, 22, 10), _day_at(yy, 15))
    _lock(ctx, _day_at(y, 15))
    j = _j(ctx, "AegisLabNight")
    assert j.state == "DEGRADED" and "wrote no lab tick" in j.detail


def test_lab_night_stale_when_nothing_for_days(tmp_path):
    today = _now().date()
    now = _day_at(today, 8)
    ctx = _ctx(tmp_path, now)
    old = today - timedelta(days=5)
    _lab(ctx, _day_at(old, 22, 10), _day_at(old, 15))
    _lock(ctx, _day_at(old, 15))
    assert _j(ctx, "AegisLabNight").state == "STALE"


def test_lab_night_inside_window(tmp_path, monkeypatch):
    today = _now().date()
    ctx = _ctx(tmp_path, _day_at(today, 15, 10))
    _lock(ctx, _day_at(today, 15))
    _lab(ctx, _day_at(today - timedelta(days=1), 22, 10), _day_at(today - timedelta(days=1), 15))
    assert _j(ctx, "AegisLabNight").state == "ALIVE_IDLE_EXPECTED"        # first tick not due yet
    ctx = _ctx(tmp_path, _day_at(today, 18))
    assert _j(ctx, "AegisLabNight").state == "DEGRADED"                   # 3 h in, no tick
    _lab(ctx, _day_at(today, 17, 58), _day_at(today, 15))
    monkeypatch.setattr(SH, "p_always_on_lab", lambda c: SH.ProbeResult("ALIVE", None, None, "pid alive"))
    assert _j(ctx, "AegisLabNight").state == "ALIVE_PROGRESSING"
    monkeypatch.setattr(SH, "p_always_on_lab", lambda c: SH.ProbeResult("DEAD", None, None, "pid gone"))
    assert _j(ctx, "AegisLabNight").state == "DEGRADED"


def test_lab_night_off_marker_and_unreadable(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _w(ctx.optimus_dir / "lab_status.json", "{broken")
    assert _j(ctx, "AegisLabNight").state == "UNKNOWN"
    _w(ctx.optimus_dir / "always_on_lab_OFF", f"off since {_iso(now)}")
    assert _j(ctx, "AegisLabNight").state == "STOPPED_BY_OPERATOR"


# ─────────────────────────────────────────── AegisNewsOverlayBook


def _session_at(now: datetime, et_hhmm: tuple, back: int = 0) -> datetime:
    from zoneinfo import ZoneInfo
    et = SH._et(now)
    days, _ = SH._sessions(et.date() - timedelta(days=20), et.date())
    return datetime.combine(days[-1 - back], dtime(*et_hhmm), ZoneInfo("America/New_York")).astimezone(timezone.utc)


def _overlay(ctx, t: datetime, **kw):
    row = {"label": "FORWARD", "session": SH._et(t).date().isoformat(), "scalar": 1.0, "degradation": None,
           "written": True, "written_utc": _iso(t)}
    row.update(kw)
    _jl(ctx.optimus_dir / "news_overlay_book" / "decisions.jsonl",
        [{"label": "BACKDATED", "written_utc": _iso(t + timedelta(seconds=1))}, row])


def test_overlay_fresh_ok_inside_its_window(tmp_path):
    t = _session_at(_now(), (15, 45), back=1)
    ctx = _ctx(tmp_path, t + timedelta(minutes=5))
    _overlay(ctx, t)
    # a 24 h cadence inside a 30-minute window: window_status reads the fresh row as the
    # window's product (the same rule as AegisStraddleForward)
    assert _j(ctx, "AegisNewsOverlayBook").state in TR.ALIVE_STATES


def test_overlay_stale(tmp_path):
    t = _session_at(_now(), (15, 45), back=8)
    ctx = _ctx(tmp_path, _session_at(_now(), (15, 50), back=1))
    _overlay(ctx, t)
    assert _j(ctx, "AegisNewsOverlayBook").state == "STALE"


def test_overlay_refused_row_and_raised_refusal(tmp_path):
    t = _session_at(_now(), (15, 45), back=1)
    ctx = _ctx(tmp_path, t + timedelta(minutes=5))
    _overlay(ctx, t, refused=True, degradation="STALE_BASE")
    assert _j(ctx, "AegisNewsOverlayBook").state == "REFUSED"
    _overlay(ctx, t - timedelta(days=1))
    _wrapper(ctx, "scripts.news_overlay_book", ["step"], 2, t + timedelta(minutes=1))
    j = _j(ctx, "AegisNewsOverlayBook")
    assert j.state == "REFUSED" and "rc 2" in j.detail


def test_overlay_unreadable_and_never_run(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _w(ctx.optimus_dir / "news_overlay_book" / "decisions.jsonl", "junk\n")
    assert _j(ctx, "AegisNewsOverlayBook").state == "UNKNOWN"
    ctx2 = _ctx(tmp_path / "b", now)
    first = (now + timedelta(days=1)).astimezone()
    task = _task("AegisNewsOverlayBook", **{"Last Result": TR.NEVER_RAN_RC, "Start Date": first.strftime("%m/%d/%Y"),
                                            "Start Time": first.strftime("%I:%M:%S %p")})
    j = TR.judge(ctx2, "AegisNewsOverlayBook", task)
    assert j.state == "ALIVE_IDLE_EXPECTED" and "not due yet" in j.detail


# ─────────────────────────────────────────── AegisLLMSelectorBook


def _sel(ctx, dec: datetime | None = None, ref: datetime | None = None, code="CANDIDATES_STALE",
         ref_date=None):
    f = ctx.optimus_dir / "llm_selector"
    if dec:
        _jl(f / "decisions.jsonl", [{"decision_date": dec.date().isoformat(), "entry_session": "x",
                                     "written_utc": _iso(dec)}])
    if ref:
        _jl(f / "refusals.jsonl", [{"row_type": "refusal", "code": code, "detail": "why",
                                    "decision_date": ref_date or ref.date().isoformat(), "written_utc": _iso(ref)}])


def _never(now: datetime, first_offset: timedelta) -> dict:
    first = (now + first_offset).astimezone()
    return _task("AegisLLMSelectorBook", **{"Last Result": TR.NEVER_RAN_RC, "Next Run Time": "next week",
                                            "Start Date": first.strftime("%m/%d/%Y"),
                                            "Start Time": first.strftime("%I:%M:%S %p")})


def test_selector_fresh_ok_and_stale(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _sel(ctx, dec=now - timedelta(days=2))
    assert _j(ctx, "AegisLLMSelectorBook").state == "ALIVE_PROGRESSING"
    ctx2 = _ctx(tmp_path / "b", now)
    _sel(ctx2, dec=now - timedelta(days=10))
    assert _j(ctx2, "AegisLLMSelectorBook").state == "STALE"


def test_selector_never_run_is_not_due_yet_then_a_fault(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _sel(ctx, dec=now - timedelta(days=1))
    j = TR.judge(ctx, "AegisLLMSelectorBook", _never(now, -timedelta(days=1)))
    assert j.state == "ALIVE_IDLE_EXPECTED" and "not due yet" in j.detail and "MANUAL" in j.detail
    j = TR.judge(ctx, "AegisLLMSelectorBook", _never(now, -timedelta(days=10)))
    assert j.state == "DEGRADED" and "NEVER run" in j.detail
    empty = _ctx(tmp_path / "e", now)
    assert TR.judge(empty, "AegisLLMSelectorBook", _never(now, -timedelta(days=1))).state == "ALIVE_IDLE_EXPECTED"
    bad = _task("AegisLLMSelectorBook", **{"Last Result": TR.NEVER_RAN_RC, "Start Date": "?", "Start Time": "?"})
    assert TR.judge(empty, "AegisLLMSelectorBook", bad).state == "STALE"


def test_selector_refusals(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _sel(ctx, dec=now - timedelta(days=2), ref=now - timedelta(hours=1))
    j = _j(ctx, "AegisLLMSelectorBook")
    assert j.state == "REFUSED" and "CANDIDATES_STALE" in j.detail
    d = now - timedelta(hours=2)
    _sel(ctx, dec=d, ref=now - timedelta(hours=1), code="ALREADY_DECIDED", ref_date=d.date().isoformat())
    assert _j(ctx, "AegisLLMSelectorBook").state == "ALIVE_IDLE_EXPECTED"
    _wrapper(ctx, "scripts.llm_selector_book", ["--decide", "--data-root", "x"], 4, now - timedelta(minutes=5))
    assert _j(ctx, "AegisLLMSelectorBook").state == "REFUSED"


def test_selector_unreadable_is_unknown(tmp_path):
    ctx = _ctx(tmp_path, _now())
    _w(ctx.optimus_dir / "llm_selector" / "decisions.jsonl", "junk\n")
    assert _j(ctx, "AegisLLMSelectorBook").state == "UNKNOWN"


# ─────────────────────────────────────────── AegisSystemStatus


def _status(ctx, t: datetime, rc: int, und=()):
    _w(ctx.optimus_dir / "system_status" / "status.json",
       {"receipt": "system_status/1", "generated_utc": _iso(t), "exit_code": rc, "counts": {"OK": 1},
        "undetermined": list(und)})


@pytest.mark.parametrize("rc,state", [(0, "ALIVE_PROGRESSING"), (3, "ALIVE_PROGRESSING"), (1, "DEGRADED")])
def test_system_status_exit_codes(tmp_path, rc, state):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _status(ctx, now - timedelta(minutes=5), rc, und=["tasks/X: UNKNOWN"] if rc == 3 else ())
    j = _j(ctx, "AegisSystemStatus")
    assert j.state == state, j.detail
    if rc == 3:
        assert "1 row(s) undetermined" in j.detail


def test_system_status_stale_and_unreadable(tmp_path):
    now = _now()
    ctx = _ctx(tmp_path, now)
    _status(ctx, now - timedelta(hours=2), 0)
    assert _j(ctx, "AegisSystemStatus").state == "STALE"
    _w(ctx.optimus_dir / "system_status" / "status.json", "{")
    assert _j(ctx, "AegisSystemStatus").state == "UNKNOWN"


# ─────────────────────────────────────────── AegisOwnerEventWarning


def _ow(tmp_path, now, rows):
    p = tmp_path / "journal" / "owner_warning_runs.jsonl"
    _w(p, "﻿" + "\n".join(json.dumps(r) for r in rows) + "\n")
    return _ctx(tmp_path, now, owner_warning_runs=p)


def test_owner_warning_states(tmp_path):
    now = _now()
    at = (now - timedelta(minutes=3)).isoformat()
    assert _j(_ow(tmp_path / "a", now, [{"status": "NO_HELD_EVENT", "at_utc": at}]),
              "AegisOwnerEventWarning").state == "ALIVE_PROGRESSING"
    j = _j(_ow(tmp_path / "b", now, [{"status": "NO_RUNNER_RECEIPT", "at_utc": at}]), "AegisOwnerEventWarning")
    assert j.state == "DEGRADED" and "ExitCode null" in j.detail
    j = _j(_ow(tmp_path / "c", now, [{"status": "PROVISIONAL", "at_utc": at},
                                     {"status": "REFUSED", "reason": "SOURCE_AMBIGUOUS", "at_utc": at}]),
           "AegisOwnerEventWarning")
    assert j.state == "REFUSED" and "SOURCE_AMBIGUOUS" in j.detail
    assert _j(_ow(tmp_path / "d", now, [{"status": "DEFERRED_IIF_WINDOW", "at_utc": at}]),
              "AegisOwnerEventWarning").state == "ALIVE_IDLE_EXPECTED"


def test_owner_warning_stale_and_unreadable(tmp_path):
    now = _now()
    old = (now - timedelta(hours=2)).isoformat()
    assert _j(_ow(tmp_path / "a", now, [{"status": "NO_HELD_EVENT", "at_utc": old}]),
              "AegisOwnerEventWarning").state == "STALE"
    p = tmp_path / "x" / "owner_warning_runs.jsonl"
    _w(p, "junk\n")
    assert _j(_ctx(tmp_path / "x", now, owner_warning_runs=p), "AegisOwnerEventWarning").state == "UNKNOWN"


# ─────────────────────────────────────────── the systems page row


def test_status_page_does_not_degrade_a_never_run_task_its_reader_calls_not_due(monkeypatch):
    from scripts import system_status as S
    now = _now()
    monkeypatch.setattr(SH, "_schtasks", lambda ctx: {"AegisLLMSelectorBook": {
        "Last Run Time": "11/30/1999 12:00:00 AM", "Last Result": TR.NEVER_RAN_RC,
        "Next Run Time": "later", "Scheduled Task State": "Ready"}})
    pr = {"probe": "task", "name": "task:AegisLLMSelectorBook", "verdict": "ALIVE", "state": "ALIVE_IDLE_EXPECTED",
          "detail": "not due yet", "evidence_utc": None, "cadence_s": 86400}
    r = S.tasks_section(object(), now, [pr])[0]
    assert r["status"] == "OK" and "has never run (not due yet)" in r["detail"]
    pr2 = {**pr, "state": "ALIVE_PROGRESSING"}
    assert S.tasks_section(object(), now, [pr2])[0]["status"] == "DEGRADED"
