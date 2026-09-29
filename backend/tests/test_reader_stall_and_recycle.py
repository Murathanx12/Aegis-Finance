"""The reader's stall of 2026-09-29 00:59-02:15 HKT, and what now prevents it.

For 77 minutes the supervisor's status said "reading" while every page came
back BLANK: one hung tab in the dedicated Chrome made every Playwright attach
of the gateway time out, the gateway probe stayed green, and nothing compared
the status with pages OK. The same night a capped social host's future-dated
throttle slot queued every other host behind it (10 idle minutes), a stale
keep-alive socket's reset was read as "gateway down" and stopped the pool, and
the repair's memory floor could block a gateway restart forever.

Everything here runs on fakes: a fake clock, a fake memory reader, a fake
transport, fake CDP targets, tmp_path. Nothing touches a browser.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import gateway_repair as GR
from backend.services import openclaw_http as OH
from backend.services import reader_scheduler as RS
from backend.services import web_reader as WR
from scripts import night_reader_supervisor as S


# ───────────────────────── 1. the status state machine ───────────────────────

def _st(**kw):
    base = dict(alive=True, repairing=False, ok_10m=0, last_ok_age=None, since_launch_s=5000.0,
                next_slot_in_s=None, attempts_10m=0, stall_after_s=600.0)
    base.update(kw)
    return S.derive_state(**base)


def test_reading_needs_pages_ok_not_a_live_process():
    assert _st(ok_10m=3) == S.READING
    # alive, pages attempted, none OK for 77 minutes: the 2026-09-29 night
    assert _st(ok_10m=0, attempts_10m=40, last_ok_age=77 * 60) == S.STALLED


def test_no_reader_process_is_down_and_a_repair_is_repairing():
    assert _st(alive=False) == S.DOWN
    assert _st(alive=False, repairing=True) == S.REPAIRING
    assert _st(alive=True, repairing=True, ok_10m=5) == S.REPAIRING


def test_a_reserved_slot_far_ahead_with_nothing_attempted_is_waiting_for_a_cap():
    assert _st(next_slot_in_s=900.0, attempts_10m=0, last_ok_age=1200) == S.WAITING_FOR_CAP
    # attempts that all failed are NOT a cap wait
    assert _st(next_slot_in_s=900.0, attempts_10m=6, last_ok_age=1200) == S.STALLED


def test_a_fresh_launch_is_starting_not_stalled():
    assert _st(since_launch_s=120.0, last_ok_age=5000) == S.STARTING
    assert _st(since_launch_s=5000.0, last_ok_age=300.0) == S.READING
    assert _st(since_launch_s=5000.0, last_ok_age=601.0) == S.STALLED


def test_page_counts_count_attempts_of_any_class(tmp_path):
    now = datetime(2026, 9, 29, 2, 0, tzinfo=timezone.utc)
    p = tmp_path / "page_log.jsonl"
    rows = [{"t": (now - timedelta(minutes=m)).isoformat(), "host": "wsj.com", "class": c,
             "url": "u", "worker": "pool0"}
            for m, c in ((2, "BLANK"), (4, "BLANK"), (8, "BLANK"), (30, "OK"))]
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    pc = S.page_counts(now, path=p)
    assert pc["attempts_10m"] == 3 and pc["ok_10m"] == 0 and pc["ok_60m"] == 1
    assert S.last_ok_age_s(now, path=p) == pytest.approx(1800.0)


# ───────────────────────── 2. a stall is detected and acted on ───────────────

def test_the_stall_ladder_escalates_and_cycles():
    got = [S.stall_action(i) for i in range(7)]
    assert got[:3] == ["close_hung_tabs", "restart_pool", "recycle_chrome"]
    assert got[3:] == ["restart_pool", "recycle_chrome", "restart_pool", "recycle_chrome"]


class FakeCDP:
    """Page targets of a fake dedicated Chrome."""

    def __init__(self, pages, hung=()):
        self.pages = [{"id": i, "url": f"https://x/{i}", "type": "page"} for i in pages]
        self.hung = set(hung)
        self.closed: list[str] = []
        self.proofs = 0

    def prove(self):
        self.proofs += 1
        return {"ok": True, "pid": 4242, "created": "2026-09-28T20:28:05+08:00"}

    def targets(self):
        return list(self.pages)

    def responsive(self, t, timeout):
        return t["id"] not in self.hung

    def close(self, tid):
        self.closed.append(tid)
        self.pages = [p for p in self.pages if p["id"] != tid]
        return True


def test_hung_tabs_are_found_and_closed_on_the_proven_instance():
    c = FakeCDP(["a", "b", "c"], hung=["b"])
    d = GR.TabDeps(prove=c.prove, page_targets=c.targets, responsive=c.responsive,
                   close_target=c.close, clock=lambda: 0.0)
    out = GR.close_hung_tabs(d)
    assert [h["id"] for h in out["hung"]] == ["b"] and c.closed == ["b"] and c.proofs == 1


def test_no_proof_no_close():
    c = FakeCDP(["a"], hung=["a"])

    def refuse():
        raise RuntimeError("REFUSED_NOT_MURATCLAW_INSTANCE")
    d = GR.TabDeps(prove=refuse, page_targets=c.targets, responsive=c.responsive,
                   close_target=c.close)
    out = GR.close_hung_tabs(d)
    assert not out["ok"] and c.closed == []


def test_the_pool_is_stopped_by_its_stop_file_then_by_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "POOL_STOP", tmp_path / "READER_POOL_STOP")
    t = {"now": 0.0}
    seen_stop = []

    def pids():
        seen_stop.append((tmp_path / "READER_POOL_STOP").exists())
        return [77]                                # never exits by itself

    killed, closed = [], []
    out = S.stop_pool_gracefully(
        wait_s=30.0, pids_fn=pids, kill_fn=lambda p: killed.append(p) or True,
        sleep_fn=lambda s: t.__setitem__("now", t["now"] + s), clock=lambda: t["now"],
        status_fn=lambda: {"open_tab_ids": ["T1", "T2"]},
        close_fn=lambda ids: closed.extend(ids) or list(ids))
    assert seen_stop[0] is True                       # asked first
    assert killed == [77] and not out["stopped_gracefully"]
    assert closed == ["T1", "T2"]                     # its tabs closed on this exit path too
    assert not (tmp_path / "READER_POOL_STOP").exists()


def test_a_pool_that_stops_itself_is_not_killed(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "POOL_STOP", tmp_path / "READER_POOL_STOP")
    calls = {"n": 0}

    def pids():
        calls["n"] += 1
        return [77] if calls["n"] < 3 else []
    killed = []
    out = S.stop_pool_gracefully(wait_s=60.0, pids_fn=pids, kill_fn=killed.append,
                                 sleep_fn=lambda s: None, clock=lambda: 0.0,
                                 status_fn=lambda: {}, close_fn=lambda ids: [])
    assert out["stopped_gracefully"] and killed == []


# ───────────────────────── 3. the repair reclaims memory ─────────────────────

class FakeMachine:
    def __init__(self, free, cdp):
        self.free, self.cdp = free, cdp
        self.events: list[str] = []
        self.alive = True
        self.t = 0.0

    def deps(self, *, frees_on_close=0.0, frees_on_recycle=0.0, exits=True):
        def close(tid):
            self.events.append(f"close:{tid}")
            self.free += frees_on_close
            return self.cdp.close(tid)

        def browser_close():
            self.events.append("browser_close")
            if exits:
                self.alive = False
            return True

        def launch():
            self.events.append("launch")
            self.free += frees_on_recycle
            self.alive = True
            return {"launched": True}

        def kill(pid):
            self.events.append(f"kill:{pid}")
            self.alive = False
            return True
        return GR.ChromeDeps(prove=self.cdp.prove, page_targets=self.cdp.targets,
                             close_target=close, open_blank=lambda: "BLANK",
                             browser_close=browser_close, pid_alive=lambda p: self.alive,
                             kill_pid=kill, launch=launch,
                             chrome_memory=lambda: {"total_gb": 8.0},
                             free_gb=lambda: self.free, responsive=self.cdp.responsive,
                             sleep=self.sleep, clock=lambda: self.t)

    def sleep(self, s):
        self.t += s


def test_reclaim_stops_at_the_first_step_that_clears_the_floor():
    m = FakeMachine(1.0, FakeCDP(["h", "x"], hung=["h"]))
    out = GR.reclaim_memory(need_gb=1.5, deps=m.deps(frees_on_close=0.6))
    assert out["ok"] and [s["step"] for s in out["steps"]] == ["close_hung_tabs"]
    assert "launch" not in m.events


def test_reclaim_recycles_the_dedicated_chrome_when_tabs_are_not_enough():
    m = FakeMachine(0.6, FakeCDP(["a", "b"]))
    out = GR.reclaim_memory(need_gb=1.5, own_tab_ids=["b"], deps=m.deps(frees_on_recycle=3.0))
    assert [s["step"] for s in out["steps"]] == ["close_hung_tabs", "close_idle_tabs",
                                                 "recycle_dedicated_chrome"]
    assert out["ok"] and out["free_after"] >= 1.5


def test_reclaim_never_waits_when_nothing_frees():
    m = FakeMachine(0.6, FakeCDP(["a"]))
    out = GR.reclaim_memory(need_gb=1.5, deps=m.deps())
    assert out["ok"] is False and len(out["steps"]) == 3        # returned, did not loop


def test_idle_tabs_keep_one_window_and_close_ours_first():
    c = FakeCDP(["x", "ours", "y"])
    m = FakeMachine(3.0, c)
    out = GR.close_idle_tabs(["ours"], deps=m.deps())
    assert out["order"][0] == "ours" and out["blank"] == "BLANK"
    assert set(out["closed"]) == {"x", "ours", "y"}


# ───────────────────────── 4. the Chrome recycle ─────────────────────────────

def test_the_recycle_closes_our_tabs_first_then_closes_and_relaunches():
    m = FakeMachine(3.0, FakeCDP(["other1", "ours1", "other2", "ours2"]))
    out = GR.recycle_dedicated_chrome(["ours2", "ours1"], deps=m.deps(), why="AGE")
    closes = [e for e in m.events if e.startswith("close:")]
    assert closes[:2] == ["close:ours2", "close:ours1"]
    assert m.events.index("browser_close") > max(m.events.index(c) for c in closes)
    assert m.events[-1] == "launch" and out["ok"]
    assert not any(e.startswith("kill:") for e in m.events)       # exited gracefully


def test_a_browser_that_does_not_exit_is_ended_by_its_proven_pid_only():
    m = FakeMachine(3.0, FakeCDP(["a"]))
    out = GR.recycle_dedicated_chrome([], deps=m.deps(exits=False), exit_wait_s=10.0)
    assert "kill:4242" in m.events and out["ok"]
    assert m.events.index("kill:4242") < m.events.index("launch")


def test_an_unproven_browser_is_never_recycled():
    c = FakeCDP(["a"])
    m = FakeMachine(3.0, c)
    d = m.deps()

    def refuse():
        raise RuntimeError("REFUSED_NOT_MURATCLAW_INSTANCE")
    d.prove = refuse
    out = GR.recycle_dedicated_chrome(["a"], deps=d)
    assert out["ok"] is False and m.events == []


def test_recycle_is_due_on_age_on_size_or_on_size_under_pressure():
    assert GR.chrome_recycle_due(age_s=3600, mem_gb=2.0, free_gb=1.0) is None
    assert GR.chrome_recycle_due(age_s=3 * 3600, mem_gb=2.0).startswith("AGE")
    assert GR.chrome_recycle_due(age_s=60, mem_gb=9.0).startswith("MEMORY")
    # a big browser on a roomy machine is left alone (no quarter-hourly churn)
    assert GR.chrome_recycle_due(age_s=900, mem_gb=5.5, free_gb=6.5) is None
    assert GR.chrome_recycle_due(age_s=900, mem_gb=5.5, free_gb=2.2).startswith(
        "MEMORY_PRESSURE")


# ───────────────────────── 5. the governor adapts ────────────────────────────

def test_the_tab_maximum_adapts_to_the_headroom():
    free = {"gb": 2.9}
    g = RS.TabGovernor(max_tabs=6, floor_gb=2.0, grow_gb=2.6, tab_gb=0.5,
                       mem_fn=lambda: free["gb"], target=3)
    assert g.effective_max(2.9) == 4               # 3 held + one 0.5 GB tab above the floor
    g.update(open_tabs=3)
    assert g.target == 4
    g.update(open_tabs=3)
    assert g.target == 4                           # no headroom for a fifth
    free["gb"] = 1.2                               # deep deficit: sheds two
    g.update(open_tabs=4)
    assert g.target == 2
    free["gb"] = 9.0
    for _ in range(10):
        g.update(open_tabs=2)
    assert g.target == 6                           # never above the configured max


# ───────────────── 6. no host waits behind another host's cap ───────────────

class Clock:
    def __init__(self):
        self.t = datetime(2026, 9, 29, 2, 0, tzinfo=timezone.utc)

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=s)


def test_fit_global_gap_uses_the_gap_before_a_future_reservation():
    t0 = datetime(2026, 9, 29, tzinfo=timezone.utc)
    future = t0 + timedelta(minutes=10)
    assert WR.fit_global_gap(t0, [future], 2.0) == t0
    assert WR.fit_global_gap(future, [future], 2.0) == future + timedelta(seconds=2)
    assert WR.fit_global_gap(t0, [t0 - timedelta(seconds=1)], 2.0) == t0 + timedelta(seconds=1)


def test_a_capped_social_host_does_not_queue_the_news_sites(tmp_path):
    clock = Clock()
    thr = WR.Throttle(path=tmp_path / "_throttle.log", now_fn=clock.now, sleep_fn=clock.sleep,
                      seed=7, per_host_mode=True, max_per_hour=1000, max_per_day=10000,
                      max_per_day_per_host=5000, per_host_day_caps={},
                      host_gap_s={"wsj.com": (10.0, 45.0), "x.com": (25.0, 90.0)},
                      global_gap_s=(1.0, 4.0), per_host_hour_caps={})
    # x.com holds a reservation ten minutes ahead (its hourly cap), as at 02:05
    ahead = clock.now() + timedelta(minutes=10)
    thr.path.write_text(f"{ahead.isoformat()} x.com 50.0\n", encoding="utf-8")
    res = thr.reserve("open", "wsj.com")
    assert res["wait_s"] < 5.0                     # was ~600 s before the fix
    assert thr.next_free_at("wsj.com") < ahead


# ───────────────── 7. a reset socket is not a gateway that is down ───────────

class ResetOnce:
    def __init__(self, n_resets=1):
        self.n, self.calls, self.headers = n_resets, 0, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls += 1
        self.headers.append(dict(headers or {}))
        if self.calls <= self.n:
            raise ConnectionError("('Connection aborted.', ConnectionResetError(10054, "
                                  "'An existing connection was forcibly closed'))")

        class R:
            status_code = 200

            def json(self):
                return {"ok": True, "result": {"details": {"tabs": []}}}
        return R()


def _t(sess, port_open=True):
    t = OH.HttpTransport(session=sess, token_fn=lambda: "tok")
    t._port_open = lambda: port_open
    return t


def test_every_request_closes_its_socket():
    s = ResetOnce(0)
    _t(s).run(["browser", "--browser-profile", "m", "--json", "tabs"])
    assert s.headers[0].get("Connection") == "close"


def test_a_read_verb_is_retried_once_after_a_reset():
    s = ResetOnce(1)
    t = _t(s)
    r = t.run(["browser", "--browser-profile", "m", "--json", "tabs"])
    assert r.returncode == 0 and s.calls == 2 and t.resets_retried == 1


def test_an_open_is_never_sent_twice_and_a_reset_under_a_live_port_is_not_gateway_down():
    s = ResetOnce(1)
    r = _t(s, port_open=True).run(["browser", "--browser-profile", "m", "open",
                                   "https://www.wsj.com/"])
    assert s.calls == 1 and r.returncode == 1
    assert "connection reset" in r.stderr and not WR.is_gateway_down(r.stderr)


def test_a_reset_with_the_port_closed_is_still_gateway_down():
    s = ResetOnce(5)
    r = _t(s, port_open=False).run(["browser", "--browser-profile", "m", "open",
                                    "https://www.wsj.com/"])
    assert WR.is_gateway_down(r.stderr)


def test_the_pool_status_names_the_next_reserved_slot():
    from scripts import reader_pool as RP
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    rows = [(now - timedelta(seconds=30), "wsj.com", 20.0),
            (now + timedelta(seconds=90), "x.com", 50.0),
            (now + timedelta(seconds=400), "reddit.com", 50.0)]
    assert RP.next_slot_in_s(rows, now) == 90.0
    assert RP.next_slot_in_s(rows[:1], now) is None


def test_machine_numbers_go_to_the_gitignored_local_pc_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "DATA", tmp_path)
    S.write_machine_record({"free_ram_gb": 2.2})
    p = tmp_path / "local_pc" / "reader_machine.jsonl"
    assert p.exists() and json.loads(p.read_text(encoding="utf-8"))["free_ram_gb"] == 2.2
    assert Path(S.__file__).resolve().parent.parent.joinpath(".gitignore").read_text(
        encoding="utf-8").find("backend/data/optimus/local_pc/") >= 0


# ───────────────── 8. idle pages do not live for the browser's life ─────────

def test_stale_and_hung_pages_are_closed_but_ours_and_blank_are_kept():
    now = 10_000.0
    pages = [{"id": "launcher", "url": "https://www.wsj.com/"},       # idle 20 min+
             {"id": "ours", "url": "https://www.barrons.com/a"},        # the pool's
             {"id": "fresh", "url": "https://www.marketwatch.com/s"},   # just navigated
             {"id": "hung", "url": "https://x.com/Microsoft"},          # does not answer
             {"id": "blank", "url": "about:blank"}]
    loaded = {"launcher": now - 1900, "ours": now - 5000, "fresh": now - 30}
    closed = []
    out = GR.close_stale_tabs(keep_ids=["ours"], max_idle_s=1800, prove=lambda: {"ok": True},
                              page_targets=lambda: pages,
                              loaded_at=lambda p, t: loaded.get(p["id"]),
                              close_target=lambda i: closed.append(i) or True,
                              open_blank=lambda: pytest.fail("a page is left: no blank"),
                              now=lambda: now, timeout_s=1.0)
    assert sorted(closed) == ["hung", "launcher"] and out["ok"]


def test_closing_every_page_opens_a_blank_first():
    order = []
    GR.close_stale_tabs(max_idle_s=10, prove=lambda: {"ok": True},
                        page_targets=lambda: [{"id": "a", "url": "https://www.wsj.com/"}],
                        loaded_at=lambda p, t: 0.0,
                        close_target=lambda i: order.append(f"close:{i}") or True,
                        open_blank=lambda: order.append("blank") or "B", now=lambda: 100.0)
    assert order == ["blank", "close:a"]


def test_the_relaunched_chrome_starts_blank_not_on_a_live_home_page():
    from backend.services import muratclaw_instance as MI
    assert MI.attach_argv()[-1] == "about:blank"
