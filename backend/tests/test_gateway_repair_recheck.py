"""Gateway repair re-check (2026-11-14 wake): a gateway process that was alive
when the repair began died DURING the wait; the repair ended unhealthy and
started nothing. Test doubles only: no gateway, process or network is touched.
"""
from __future__ import annotations

import json

from backend.services import gateway_repair as GR
from scripts import night_reader_supervisor as S

SF = {"file": "x-gateway.startup_failed.json", "pid": 41800,
      "reason": "another OpenClaw process owns state-lifecycle"}


class Machine:
    def __init__(self, *, alive_at_entry=True, dies_during_wait=True, start_binds=True):
        self.alive = alive_at_entry
        self.dies = dies_during_wait
        self.start_binds = start_binds
        self.gw = False
        self.starts = 0
        self.t = 0.0

    def sleep(self, s):
        self.t += s
        if self.alive and self.dies and self.t > 30:
            self.alive = False

    def openclaw(self, args, timeout=None):
        if args[:2] == ["gateway", "start"]:
            self.starts += 1
            if self.start_binds:
                self.gw, self.alive = True, True
        return {"rc": 0}

    def deps(self) -> GR.Deps:
        return GR.Deps(
            port_open=lambda h, p: self.gw, openclaw=self.openclaw,
            browser_status=lambda prof: {"ok": True, "running": True},
            chrome_status=lambda: {"running_with_port": True}, chrome_launch=lambda: {},
            orphan_mcp=lambda: [], kill_pid=lambda p: True,
            gateway_procs=lambda: [{"pid": 1}] if self.alive else [],
            startup_failed=lambda: SF, free_gb=lambda: 8.0, sleep=self.sleep,
            clock=lambda: self.t, reclaim=lambda need: {"ok": False})


def test_a_process_that_dies_during_the_wait_gets_exactly_one_start():
    m = Machine()
    r = GR.repair("GATEWAY_DOWN", deps=m.deps())
    assert m.starts == 1 and r["gateway_starts"] == 1
    assert r["healthy"] and r["cleared_by"] == "gateway_start"
    names = [s["step"] for s in r["steps"]]
    assert names == ["wait_for_port_existing", "gateway_start"]


def test_a_process_still_alive_and_unhealthy_is_never_doubled_and_says_why():
    m = Machine(dies_during_wait=False)
    r = GR.repair("GATEWAY_DOWN", deps=m.deps())
    assert m.starts == 0 and not r["healthy"]
    assert "GATEWAY_STARTING_SLOW" in r["stopped_because"]
    assert r["startup_failed"] == SF            # the newest reason rides the row


def test_nothing_alive_at_entry_is_the_old_single_start():
    m = Machine(alive_at_entry=False)
    r = GR.repair("GATEWAY_DOWN", deps=m.deps())
    assert m.starts == 1 and r["healthy"] and r["cleared_by"] == "gateway_start"
    assert [s["step"] for s in r["steps"]] == ["gateway_start"]


def test_the_starter_runs_at_most_once_even_when_it_does_not_bind():
    for kw in ({}, {"start_binds": False}, {"alive_at_entry": False, "start_binds": False},
               {"dies_during_wait": False}):
        m = Machine(**kw)
        r = GR.repair("GATEWAY_DOWN", deps=m.deps())
        assert m.starts <= 1 and r["gateway_starts"] <= 1, kw
        if not r["healthy"]:
            assert r["startup_failed"] == SF


def test_a_failed_start_after_the_wait_is_red_with_the_reason():
    m = Machine(start_binds=False)
    r = GR.repair("GATEWAY_DOWN", deps=m.deps())
    assert m.starts == 1 and not r["healthy"] and r["startup_failed"] == SF
    assert "did not bind" in r["stopped_because"]


def test_two_failed_passes_in_a_row_write_a_down_row_and_one_pass_does_not(
        tmp_path, monkeypatch):
    rows = []
    monkeypatch.setattr(S, "log", lambda **r: rows.append(r))
    status = []
    monkeypatch.setattr(S, "write_status", lambda state, **k: status.append((state, k)))
    streak = tmp_path / "streak.json"
    bad = {"fault": "GATEWAY_DOWN", "healthy": False, "cleared_by": None, "steps": [],
           "stopped_because": "GATEWAY_STARTING_SLOW: 1 gateway process(es) alive",
           "startup_failed": SF}
    assert S.log_repair(bad, streak_path=streak)["down"] is False
    assert not [r for r in rows if r["event"] == "gateway_down"]
    out = S.log_repair(bad, streak_path=streak)
    assert out == {"fails_in_a_row": 2, "down": True}
    down = [r for r in rows if r["event"] == "gateway_down"]
    assert len(down) == 1 and down[0]["level"] == "DOWN"
    assert down[0]["startup_failed"] == SF
    assert status and status[-1][0] == S.DOWN
    good = {"fault": "GATEWAY_DOWN", "healthy": True, "cleared_by": "gateway_start",
            "steps": []}
    assert S.log_repair(good, streak_path=streak)["fails_in_a_row"] == 0
    assert json.loads(streak.read_text())["fails"] == 0
    assert S.log_repair(bad, streak_path=streak)["down"] is False      # starts over


def test_the_repair_row_carries_the_reason_and_cleared_by(tmp_path, monkeypatch):
    rows = []
    monkeypatch.setattr(S, "log", lambda **r: rows.append(r))
    S.log_repair({"fault": "GATEWAY_DOWN", "healthy": True, "cleared_by": "gateway_start",
                  "steps": [{"step": "gateway_start"}], "gateway_starts": 1,
                  "startup_failed": SF}, streak_path=tmp_path / "s.json")
    assert rows[0]["cleared_by"] == "gateway_start" and rows[0]["startup_failed"] == SF


def test_newest_startup_failed_reads_the_newest_record(tmp_path):
    assert GR.newest_startup_failed(tmp_path) is None
    for stamp, msg in (("2026-01-01T00-00-00-000Z-1", "old"), ("2026-02-01T00-00-00-000Z-2", "new")):
        (tmp_path / f"openclaw-stability-{stamp}-gateway.startup_failed.json").write_text(
            json.dumps({"generatedAt": "g", "process": {"pid": 2},
                        "error": {"name": "E", "message": msg}}), encoding="utf-8")
    assert GR.newest_startup_failed(tmp_path)["reason"] == "new"
