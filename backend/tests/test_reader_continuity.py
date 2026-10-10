"""Keeper deadline regression: fake clock/processes, no runtime or browser calls."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from scripts import night_reader_supervisor as S
from scripts import task_keeper as K


def test_continuous_pool_has_no_deadline_but_manual_pool_does():
    from scripts import reader_pool as RP

    assert S.end_time("continuous") is None
    assert "--until" not in S.pool_cmd_text(until="continuous")
    assert RP.end_time(None) is None  # the existing pool CLI default
    assert "--until 08:00" in S.pool_cmd_text(until="08:00")
    before = datetime.now()
    end = S.end_time("08:00")
    assert end.hour == 8 and end.minute == 0
    assert before < end <= datetime.now() + timedelta(days=1)


@pytest.mark.parametrize("scan_result,paused,action", [
    (None, False, "cannot_determine"),
    ([], True, "paused"),
    ([{"pid": 77, "cmdline": "-m scripts.night_reader_supervisor --until continuous"}],
     False, "alive"),
])
def test_keeper_never_launches_when_paused_unknown_or_owned(tmp_path, scan_result, paused, action):
    stop = tmp_path / "STOP"
    if paused:
        stop.touch()
    out = K.ensure_reader(scan=lambda: scan_result,
                          launch=lambda *a: pytest.fail("duplicate or unsafe launch"),
                          stop_path=stop, log_path=tmp_path / "keeper.jsonl")
    assert out["action"] == action


@pytest.mark.parametrize("args,expected_sleeps,why", [
    (["--until", "continuous"], 3, "STOP file"),
    (["--until", "08:00"], 1, "end time"),
    ([], 1, "end time"),
])
def test_supervision_survives_days_and_caps_until_stop_but_manual_expires(
        tmp_path, monkeypatch, args, expected_sleeps, why):
    clock = {"now": datetime.now().replace(hour=12, minute=0, second=0, microsecond=0),
             "slept": 0, "seconds": 100000.0}
    started_at = clock["now"]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = clock["now"]
            return value.replace(tzinfo=timezone.utc) if tz else value

    stop = tmp_path / "STOP"
    handoff = tmp_path / "HANDOFF_PC"
    handoff.touch()
    events, launched, stopped = [], [], []

    def sleep(seconds):
        clock["seconds"] += seconds
        clock["now"] += timedelta(days=1)
        clock["slept"] += 1
        if clock["slept"] == 3:
            stop.touch()

    monkeypatch.setattr(S, "datetime", Clock)
    monkeypatch.setattr(S.time, "time", lambda: clock["seconds"])
    monkeypatch.setattr(S.time, "sleep", sleep)
    monkeypatch.setattr(S, "STOP", stop)
    monkeypatch.setattr(S, "HANDOFF", handoff)
    monkeypatch.setattr(S, "POOL_CMD", tmp_path / "pool.cmd")
    monkeypatch.setattr(S, "log", lambda **r: events.append(r))
    monkeypatch.setattr(S, "loads", lambda: 10)
    monkeypatch.setattr(S, "load_ladder", lambda: {"level": 0, "last_act": 0})
    monkeypatch.setattr(S, "queue_logs", lambda *a: [])
    monkeypatch.setattr(S, "queue_of", lambda *a: None)
    monkeypatch.setattr(S, "live_reader_pids", lambda: ([], "none"))
    monkeypatch.setattr(S.shutil, "disk_usage", lambda *a: SimpleNamespace(free=100e9))
    monkeypatch.setattr(S, "launch", lambda cmd: launched.append(cmd) or 123)
    monkeypatch.setattr(S.GR, "probe", lambda: {"healthy": True, "fault": None})
    monkeypatch.setattr(S, "log_tail", lambda *a: "REFUSED_THROTTLE_DAY")
    monkeypatch.setattr(S.GR, "classify_exit", lambda *a: {
        "kind": "POLICY_STOP", "evidence": "REFUSED_THROTTLE_DAY"})
    monkeypatch.setattr(S, "throttle_stamps", lambda: [])
    monkeypatch.setattr(S, "caps_wait_s", lambda *a: 3600.0)
    monkeypatch.setattr(S, "official_due", lambda *a, **k: False)
    monkeypatch.setattr(S, "planner_due", lambda *a, **k: False)
    monkeypatch.setattr(S, "pid_alive", lambda *a: False)
    monkeypatch.setattr(S, "free_ram_gb", lambda: 8.0)
    monkeypatch.setattr(S, "write_status", lambda *a, **k: None)
    monkeypatch.setattr(S, "digest", lambda *a: None)
    monkeypatch.setattr(S, "reader_pids", lambda: [123])
    monkeypatch.setattr(S, "stop_pool_gracefully", lambda **k: stopped.append(k) or {"killed": []})

    assert S.main([*args, "--pool"]) == 0
    assert clock["slept"] == expected_sleeps
    assert len(launched) == 1  # cap waiting never bypasses the budget
    assert len(stopped) == 1
    assert next(e for e in events if e["event"] == "end")["why"] == why
    if expected_sleeps == 3:
        assert clock["now"] - started_at >= timedelta(days=3)
        assert any(e.get("action") == "wait_caps" for e in events)
        assert next(e for e in events if e["event"] == "start")["until"] == "continuous"
