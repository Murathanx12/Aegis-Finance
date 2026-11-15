"""S70 status truth: AegisTickerHub reader, old scheduler rc, retired tasks, power row, git flags.
Synthetic fixtures only (no headline text); dates derive from `now`."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import system_health as SH, task_receipts as TR
from scripts import system_status as S

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _stamp(dt: datetime) -> str:
    return dt.astimezone().strftime("%m/%d/%Y %I:%M:%S %p")


# -- part 1: AegisTickerHub ---------------------------------------------------

def _hub_ctx(tmp_path, built, **kw):
    folder = tmp_path / "ticker_hub" / "receipts"
    folder.mkdir(parents=True)
    rec = {"schema": "ticker-hub/2", "generation": "g_fixture", "built_utc": built.isoformat(),
           "rows_in_index": 100, "rows_read_new": 3, "elapsed_s": 5.0}
    rec.update(kw)
    (folder / "build_20000101T000000Z_1.json").write_text(json.dumps(rec), encoding="utf-8")
    return SH.ProbeCtx(optimus_dir=tmp_path, now=NOW, repo=tmp_path)


TASK = {"Scheduled Task State": "Enabled", "Last Result": "0"}


def test_ticker_hub_is_declared_and_dated_by_its_own_stamp(tmp_path):
    assert "AegisTickerHub" in TR.TASK_RECEIPT
    ctx = _hub_ctx(tmp_path, NOW - timedelta(minutes=10))
    j = TR.judge(ctx, "AegisTickerHub", TASK)
    assert j.state == "ALIVE_PROGRESSING" and j.stamp == NOW - timedelta(minutes=10)


def test_ticker_hub_an_old_build_is_stale_never_ok(tmp_path):
    ctx = _hub_ctx(tmp_path, NOW - timedelta(hours=5))
    assert TR.judge(ctx, "AegisTickerHub", TASK).state == "STALE"


@pytest.mark.parametrize("kw", [{"rows_in_index": 0}, {"verify": {"status": "DAMAGED", "problems": ["x"]}}])
def test_ticker_hub_bad_build_is_degraded(tmp_path, kw):
    ctx = _hub_ctx(tmp_path, NOW - timedelta(minutes=5), **kw)
    assert TR.judge(ctx, "AegisTickerHub", TASK).state == "DEGRADED"


def test_ticker_hub_no_receipt_is_not_ok(tmp_path):
    ctx = SH.ProbeCtx(optimus_dir=tmp_path, now=NOW, repo=tmp_path)
    assert TR.judge(ctx, "AegisTickerHub", TASK).state in ("STALE", "UNKNOWN", "DEAD")


# -- part 1b: rolling cohorts mapping -----------------------------------------

@pytest.mark.parametrize("action,state", [("STALE_PRICES", "DEGRADED"), ("MISSED_ENTRY_WINDOW", "DEGRADED"),
                                          ("REFUSED", "REFUSED"), ("NOTHING_DUE", "ALIVE_IDLE_EXPECTED")])
def test_rolling_cohorts_unhealthy_actions_are_not_ok_and_nothing_due_is(tmp_path, action, state):
    p = tmp_path / "runs.jsonl"
    p.write_text(json.dumps({"task": "AegisRollingCohorts", "utc": (NOW - timedelta(minutes=5)).isoformat(),
                             "action": action, "rc": 0, "forward_age_sessions": 1,
                             "newest_forward_cohort": "fixture", "cohorts_total": 5, "cohorts_live": 5}) + "\n",
                 encoding="utf-8")
    ctx = SH.ProbeCtx(optimus_dir=tmp_path / "o", now=NOW, repo=tmp_path, paths={"rolling_cohort_runs": p})
    assert TR.judge(ctx, "AegisRollingCohorts", TASK).state == state


# -- part 2: old rc, retired tasks --------------------------------------------

def _sch(name, last_run, rc, state="Enabled", nxt=None):
    return {name: {"Last Run Time": _stamp(last_run), "Last Result": str(rc),
                   "Next Run Time": _stamp(NOW + timedelta(days=1)) if nxt is None else nxt,
                   "Scheduled Task State": state}}


def _tasks(monkeypatch, sch, probe_rows):
    monkeypatch.setattr(SH, "_schtasks", lambda ctx: sch)
    return {r["name"]: r for r in S.tasks_section(object(), NOW, probe_rows)}


def _probe(name, verdict, evidence, state="ALIVE_PROGRESSING"):
    return {"probe": "task", "name": f"task:{name}", "verdict": verdict, "state": state, "detail": "d",
            "evidence_utc": evidence.isoformat(), "proof": "p"}


def test_old_nonzero_rc_with_a_newer_good_receipt_is_shown_with_its_age(monkeypatch):
    name = "AegisAnalystPull"
    rows = _tasks(monkeypatch, _sch(name, NOW - timedelta(days=4), 2),
                  [_probe(name, "ALIVE", NOW - timedelta(days=2))])
    r = rows[name]
    assert r["status"] == "OK" and "old last result 2" in r["detail"] and "not a current failure" in r["detail"]


def test_current_nonzero_rc_stays_degraded(monkeypatch):
    name = "AegisAnalystPull"
    rows = _tasks(monkeypatch, _sch(name, NOW - timedelta(minutes=30), 2),
                  [_probe(name, "ALIVE", NOW - timedelta(days=2))])        # receipt OLDER than the run
    assert rows[name]["status"] == "DEGRADED"


def test_nonzero_rc_whose_receipt_is_the_same_runs_own_stays_degraded(monkeypatch):
    name = "AegisFleetDailyCheck"
    rows = _tasks(monkeypatch, _sch(name, NOW - timedelta(hours=14), 1),
                  [_probe(name, "ALIVE", NOW - timedelta(hours=14) + timedelta(minutes=2))])
    assert rows[name]["status"] == "DEGRADED"


def test_nonzero_rc_with_no_receipt_reader_or_a_bad_receipt_stays_not_ok(monkeypatch):
    rows = _tasks(monkeypatch, {**_sch("AegisNoReader", NOW - timedelta(days=9), 2),
                                **_sch("AegisBadReceipt", NOW - timedelta(days=9), 2)},
                  [_probe("AegisBadReceipt", "STALE", NOW - timedelta(days=1), "STALE")])
    assert rows["AegisNoReader"]["status"] != "OK" and rows["AegisBadReceipt"]["status"] != "OK"


def test_disabled_declared_task_is_retired_and_counted_out(monkeypatch):
    rows = _tasks(monkeypatch, _sch("AegisContestDesk", NOW - timedelta(days=1), 0, "Disabled", "N/A"),
                  [_probe("AegisContestDesk", "STOPPED_BY_OPERATOR", NOW, "STOPPED_BY_OPERATOR")])
    r = rows["AegisContestDesk"]
    assert r["status"] == "OK" and r["extra"]["retired"] is True and "RETIRED" in r["detail"]


def test_disabled_undeclared_task_stays_degraded_and_enabled_declared_task_is_not_retired(monkeypatch):
    rows = _tasks(monkeypatch, {**_sch("AegisSomethingElse", NOW, 0, "Disabled", "N/A"),
                                **_sch("AegisContestDesk", NOW, 0, "Enabled")},
                  [_probe("AegisSomethingElse", "STALE", NOW, "STALE"),
                   _probe("AegisContestDesk", "STALE", NOW, "STALE")])
    assert rows["AegisSomethingElse"]["status"] == "DEGRADED"
    assert not rows["AegisContestDesk"].get("extra", {}).get("retired")


# -- part 3: the power row ----------------------------------------------------

def _ev(i, prov, age_h):
    return {"id": i, "provider": prov, "utc": (NOW - timedelta(hours=age_h)).isoformat()}


def test_power_row_down_degraded_ok_unknown():
    kp = "Microsoft-Windows-Kernel-Power"
    assert S.power_row(NOW, [_ev(41, kp, 3)])["status"] == "DOWN"
    r = S.power_row(NOW, [_ev(41, kp, 50), _ev(6008, "EventLog", 50),
                          _ev(1001, "Microsoft-Windows-WER-SystemErrorReporting", 100)])
    assert r["status"] == "DEGRADED" and "BugCheck 1001" in r["detail"] and len(r["extra"]["events"]) == 3
    assert S.power_row(NOW, [_ev(41, kp, 24 * 8)])["status"] == "OK"        # outside the 7 days
    assert S.power_row(NOW, [])["status"] == "OK"
    assert S.power_row(NOW, None)["status"] == "UNKNOWN"
    assert S.power_row(NOW, [_ev(7, kp, 1)])["status"] == "OK"            # other ids are not counted


def test_machine_rows_uses_the_injected_event_source_and_unreadable_log_is_unknown():
    run = lambda a, t: (127, "")  # noqa: E731
    rows = {r["name"]: r for r in S.machine_rows(NOW, run=run, ram_free=lambda: 9.0, boot=lambda n: n,
                                                 power_events=lambda d: [_ev(41, "Kernel-Power", 2)])}
    assert rows["power"]["status"] == "DOWN"
    rows = {r["name"]: r for r in S.machine_rows(NOW, run=run, ram_free=lambda: 9.0, boot=lambda n: n)}
    assert rows["power"]["status"] == "UNKNOWN"


def test_default_power_source_rejects_foreign_shapes(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert S._power_events_default(7, lambda a, t: (0, '[{"number": 1}]')) is None
    assert S._power_events_default(7, lambda a, t: (0, "")) is None
    assert S._power_events_default(7, lambda a, t: (1, "[]")) is None
    ok = '[{"id":41,"provider":"Microsoft-Windows-Kernel-Power","utc":"2026-11-14T02:42:16Z"}]'
    assert len(S._power_events_default(7, lambda a, t: (0, ok))) == 1
    assert S._power_events_default(7, lambda a, t: (0, "[]")) == []
    monkeypatch.setattr(sys, "platform", "linux")
    assert S._power_events_default(7, lambda a, t: (0, ok)) is None


def test_default_run_has_no_console_window_on_windows(monkeypatch):
    seen = {}

    def fake(argv, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(argv, 0, "x", "")
    monkeypatch.setattr(S.subprocess, "run", fake)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(S.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    S._default_run(["x"], 1)
    assert seen["creationflags"] == 0x08000000


# -- part 4: code_version -----------------------------------------------------

def test_code_version_git_call_has_no_window(monkeypatch):
    from backend.services.portfolio_intelligence import branch_population_rolling as R
    seen = {}

    def boom(*a, **kw):
        seen.update(kw)
        raise FileNotFoundError("git")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(R, "_CODE_VERSION", {})
    assert R.code_version() is None and seen["creationflags"] == 0x08000000
