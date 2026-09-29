"""The reader "always works" (2026-09-29 afternoon): a dedicated Chrome that
went away, a machine that slept, a PID query that failed, and the X handles.

MEASURED that day (receipts under `dowjones/` and `local_pc/`):

* The dedicated Chrome ended CLEANLY three times that day: its own session
  log recorded an EXIT event with `tab_count 0` each time, no crash dump, no
  WER entry. Chrome on Windows ends when its last tab closes, and the reader
  CLOSES each tab after its read; with no other page left the browser went
  with it. So the supervisor keeps one about:blank ANCHOR page.
* The machine slept for two hours (lid closed on battery). On resume the PID
  query returned nothing while the pool was alive, the supervisor read the
  pool as down, and the hourly digest ran before the reader was checked.

Test doubles only: no browser, network, gateway or process is touched. No
literal calendar dates.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import gateway_repair as GR
from backend.services import muratclaw_instance as MI
from backend.services import reader_scheduler as RS
from backend.services import web_reader as WR
from scripts import night_reader_supervisor as S
from scripts import reader_pool as RP
from scripts import social_browser_pull as SB

NOW = datetime.now(timezone.utc).replace(microsecond=0)


# ───────────────────── 1. the anchor page keeps Chrome alive ─────────────────

def _pages(*urls):
    return [{"id": f"T{i}", "type": "page", "url": u} for i, u in enumerate(urls)]


def test_anchor_is_opened_only_when_no_blank_page_is_left():
    opened = []
    out = GR.ensure_anchor_tab(prove=lambda: {"pid": 1},
                               page_targets=lambda: _pages("https://www.wsj.com/a"),
                               open_blank=lambda: opened.append(1) or "NEW")
    assert out["ok"] and out["opened"] == "NEW" and opened == [1]
    out2 = GR.ensure_anchor_tab(
        prove=lambda: {"pid": 1},
        page_targets=lambda: _pages("https://www.wsj.com/a", "about:blank"),
        open_blank=lambda: pytest.fail("an anchor is already there"))
    assert out2["ok"] and out2["opened"] is None and out2["anchor"] == "T1"


def test_anchor_refuses_on_an_unproven_browser_and_opens_nothing():
    def prove():
        raise MI.InstanceNotProven("REFUSED_INSTANCE_DOWN: not answering")
    out = GR.ensure_anchor_tab(prove=prove, page_targets=lambda: pytest.fail("no listing"),
                               open_blank=lambda: pytest.fail("no open"))
    assert out["ok"] is False and "REFUSED_INSTANCE_DOWN" in out["refused"]


def test_anchor_counts_an_empty_browser_too():
    out = GR.ensure_anchor_tab(prove=lambda: {}, page_targets=lambda: [],
                               open_blank=lambda: "A")
    assert out["opened"] == "A" and out["n_pages"] == 0


# ───────────────── 2. relaunch the dedicated Chrome, and prove it ────────────

DED = MI.user_data_dir()


def _ded(pid):
    return {"pid": pid, "created": "c", "cmdline": (
        f'"chrome.exe" --user-data-dir={DED} --remote-debugging-port={MI.port()} '
        f'--remote-debugging-address=127.0.0.1 --no-first-run about:blank')}


def _launcher(state):
    def popen(argv, **kw):
        state["up"] = True
        state["argv"] = argv
        return type("P", (), {"pid": 77})()

    def http(u):
        if not state["up"]:
            raise ConnectionRefusedError()
        return {"Browser": "Chrome"}
    return popen, http


def test_launch_verifies_the_new_pid_by_command_line_and_leaves_the_main_chrome():
    state = {"up": False}
    main = {"pid": 5, "created": "m", "cmdline": '"chrome.exe" --profile-directory=Default'}
    popen, http = _launcher(state)
    pr = MI.Probes(http_json=http,
                   chrome_processes=lambda: [main] + ([_ded(77)] if state["up"] else []))
    out = MI.launch_attach(probes=pr, popen=popen, sleep_fn=lambda s: None)
    assert out["launched"] and out["verified"] is True, out
    assert out["main_chrome_before"] == out["main_chrome_after"] == [5]
    assert state["argv"] == MI.attach_argv()           # exactly the documented line


def test_launch_says_unverified_when_the_new_pid_is_not_the_dedicated_one():
    state = {"up": False}
    popen, http = _launcher(state)
    pr = MI.Probes(http_json=http, chrome_processes=lambda: [_ded(88)] if state["up"] else [])
    out = MI.launch_attach(probes=pr, popen=popen, sleep_fn=lambda s: None)
    assert out["launched"] and out["verified"] is False
    assert "77" in out["verify_problem"]


def test_launch_never_starts_a_second_one_when_it_is_running():
    pr = MI.Probes(http_json=lambda u: {"Browser": "Chrome"}, chrome_processes=lambda: [_ded(9)])
    out = MI.launch_attach(probes=pr, popen=lambda *a, **k: pytest.fail("must not launch"))
    assert out["launched"] is False and out["why"] == "running"


# ───────────────────────── 3. sleep / resume ─────────────────────────────────

def test_a_sixty_second_sleep_that_took_two_hours_is_a_suspend():
    t0 = 1_000_000.0
    assert S.slept_through(t0, t0 + 61.0) is None
    assert S.slept_through(t0, t0 + S.TICK_S + S.RESUME_GAP_S - 1) is None
    assert S.slept_through(t0, t0 + 7200.0) == pytest.approx(7200.0 - S.TICK_S)


def test_a_stall_inside_the_resume_grace_reads_as_starting():
    now = 5000.0
    assert S.resume_state(S.STALLED, now=now, grace_until=now + 60) == S.STARTING
    assert S.resume_state(S.STALLED, now=now, grace_until=now - 1) == S.STALLED
    assert S.resume_state(S.READING, now=now, grace_until=now + 60) == S.READING


def test_resume_defers_the_hourly_digest():
    now = 10_000.0
    new = S.defer_digest_after_resume(now - 2 * S.HOURLY_S, now=now)
    assert new + S.HOURLY_S - now == pytest.approx(S.RESUME_DIGEST_DEFER_S)
    assert S.defer_digest_after_resume(now - 10, now=now) == now - 10   # never earlier


# ─────────────── 4. a failed PID query is not "the reader is down" ───────────

def test_pids_from_the_query_when_it_answers():
    assert S.live_reader_pids(query=lambda: [11, 12], pool_pid=lambda: (99, NOW),
                              alive=lambda pid, t: True) == ([11, 12], "query")


def test_a_failed_or_empty_query_falls_back_to_the_pools_own_live_pid():
    for q in (lambda: None, lambda: []):
        pids, how = S.live_reader_pids(query=q, pool_pid=lambda: (99, NOW),
                                       alive=lambda pid, t: pid == 99)
        assert pids == [99] and how.startswith("pool_status")


def test_a_dead_or_reused_pool_pid_means_down():
    pids, how = S.live_reader_pids(query=lambda: [], pool_pid=lambda: (99, NOW),
                                   alive=lambda pid, t: False)
    assert pids == [] and how == "none"
    pids, how = S.live_reader_pids(query=lambda: None, pool_pid=lambda: (None, None),
                                   alive=lambda pid, t: True)
    assert pids == [] and how == "query_failed"


def test_reader_pids_checked_is_none_on_a_failed_query(monkeypatch):
    class R:
        returncode, stdout, stderr = 1, "", "WMI not ready"
    monkeypatch.setattr(S.subprocess, "run", lambda *a, **k: R())
    assert S.reader_pids_checked() is None
    assert S.reader_pids() == []


def test_pid_created_after_the_status_was_written_is_a_reused_pid():
    t = NOW
    assert S.pid_started_before(t - timedelta(minutes=5), t) is True
    assert S.pid_started_before(t + timedelta(minutes=5), t) is False
    assert S.pid_started_before(None, t) is False


# ─────────────────────── 5. X handle timelines ───────────────────────────────

def test_handle_items_are_profile_pages_only():
    items = SB.x_handle_items(["@SemiAnalysis_", "dylan522p", "@semianalysis_", "@home",
                               "@bad handle", "@compose", "@x/../settings", ""])
    assert [i["url"] for i in items] == ["https://x.com/SemiAnalysis_",
                                         "https://x.com/dylan522p"]
    for it in items:
        assert it["host"] == "x.com" and it["kind"] == "social" and it["ticker"] is None
        assert it["handle"].startswith("@") and it["tier"] == 2
        assert not any(w in it["url"] for w in ("search", "compose", "intent", "follow"))
        assert WR.host_ok(it["url"]) and WR.is_social(it["url"])


def test_handle_url_refuses_reserved_and_malformed_names():
    for bad in ("@home", "@i", "@messages", "@settings", "@explore", "@notifications",
                "@a-b", "@" + "x" * 16, "", None):
        with pytest.raises(WR.ReaderRefused):
            SB.x_handle_url(bad)


class _Thr:
    def _rows(self):
        return []


def _pool(tmp_path, monkeypatch, **kw):
    monkeypatch.setattr(RP, "SOCIAL_SEEN", tmp_path / "social_seen.jsonl")
    return RP.Pool(driver=object(), throttle=_Thr(), names=[], books=set(), fresh=set(),
                   fronts=[], social=True, stock_pages=(), stored={},
                   now_fn=lambda: NOW, wait_fn=lambda s: False, dropped=set(),
                   front_last={}, stock_last={}, persist=False,
                   cooling=RS.HostCooling(path=tmp_path / "cool.json"),
                   printer=lambda *a: None, **kw)


def test_the_pool_queues_each_handle_once_and_not_again_while_fresh(tmp_path, monkeypatch):
    p = _pool(tmp_path, monkeypatch, social_last={}, x_handles=["@TrendForce", "@MicronTech"])
    p.refill()
    p.refill()
    got = [it for it in p.pending if it.get("handle")]
    assert [it["url"] for it in got] == ["https://x.com/TrendForce", "https://x.com/MicronTech"]
    p2 = _pool(tmp_path, monkeypatch, x_handles=["@TrendForce"],
               social_last={("x.com", "@TrendForce"): NOW - timedelta(hours=2)})
    p2.refill()
    assert not [it for it in p2.pending if it.get("handle")]
    p3 = _pool(tmp_path, monkeypatch, x_handles=["@TrendForce"],
               social_last={("x.com", "@TrendForce"): NOW - timedelta(hours=30)})
    p3.refill()
    assert [it["handle"] for it in p3.pending if it.get("handle")] == ["@TrendForce"]


def test_no_handles_without_the_social_lane_or_by_default(tmp_path, monkeypatch):
    p = _pool(tmp_path, monkeypatch, social_last={})
    p.refill()
    assert not [it for it in p.pending if it.get("handle")]
    p.social = False
    p.x_handles = ["@TrendForce"]
    p.refill()
    assert not [it for it in p.pending if it.get("handle")]


def test_a_handle_read_is_remembered_by_handle(tmp_path, monkeypatch):
    p = _pool(tmp_path, monkeypatch, social_last={}, x_handles=["@TrendForce"])
    p.persist = True
    it = SB.x_handle_items(["@TrendForce"])[0]
    p._mark_read(it)
    assert ("x.com", "@TrendForce") in p.social_last
    rows = [json.loads(x) for x in (tmp_path / "social_seen.jsonl").read_text().splitlines()]
    assert rows[-1]["handle"] == "@TrendForce" and rows[-1]["ticker"] is None
    assert ("x.com", "@TrendForce") in RP.social_last_reads()


def test_the_pool_checks_the_anchor_only_before_closing_its_last_tab(tmp_path, monkeypatch):
    calls = []
    p = _pool(tmp_path, monkeypatch, social_last={},
              keep_window=lambda: calls.append(1) or {"opened": "A", "n_pages": 1})
    p.open_tabs = {"T1": "u1", "T2": "u2"}
    p._keep_window()
    assert calls == []                       # another tab of ours keeps the window
    p.open_tabs = {"T1": "u1"}
    p._keep_window()
    assert calls == [1]
    p.keep_window = lambda: (_ for _ in ()).throw(RuntimeError("cdp down"))
    p._keep_window()                         # never raises
    assert any("keep_window" in e for e in p.errors)
