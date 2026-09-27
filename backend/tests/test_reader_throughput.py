"""Reader throughput (2026-09-27): fewer CLI calls, interleaved lanes, workers.

No browser, no network, no OpenClaw CLI: every browser verb is a stub driver
or a fake CLI behind the REAL `openclaw_client` guard, every clock is fake
(except the lock tests, which need two real threads / a real second process
and use sub-second waits). The reference pacing (20-90 s, same host 60 s) is
pinned by the Chunk J autouse fixture, imported below and kept.

What is pinned here, and why each matters:

* the interleave ORDER (`interleave_order`, and `run_plan` follows it);
* the global drawn gap and the same-host floor still bind on PAGE LOADS;
* gaps are never constant (the footprint CV alarm passes at live pacing);
* every new tab comes from `open_from_tab` with the MARKER parent;
* no guard was removed: every action has a host check before it, a
  navigate/click has its landed-URL check after it, and an off-host landing
  in the navigate reply still refuses;
* two workers never take the same throttle slot (threads + a real process);
* start-up cleanup never closes a LIVE worker's tab.
"""

# ruff: noqa: F811  -- `ledger` is a pytest fixture imported by name, then requested
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as C
from backend.services import disk_guard as DG
from backend.services import openclaw_client as OC
from backend.services import web_reader as WR
from backend.tests.test_dowjones_chunk_j import (  # noqa: F401 -- fixtures reused on purpose
    LISTINGS, MultiStub, _clock_throttle, _no_parent_marker, ledger)

MARKER_URL = "https://www.wsj.com/?aegis=muratclaw"


# ─────────────────────────── the interleave order ───────────────────────────

def test_interleave_order_is_pinned():
    from scripts import dowjones_pull as DP
    ops = DP.interleave_order({"b": [1, 2, 3], "w": [1], "m": ["MU", "DKNG"]},
                              needs_load=lambda lane, item: not (lane == "m" and item == "MU"))
    assert ops == [("load", "b", 1), ("load", "w", 1), ("finish", "b", 1),
                   ("finish", "w", 1), ("finish", "m", "MU"),
                   ("load", "b", 2), ("load", "m", "DKNG"), ("finish", "b", 2),
                   ("load", "b", 3), ("finish", "m", "DKNG"), ("finish", "b", 3)]
    # loads happen in round-robin order (minus the in-place item), one at a time
    rr = [x for x in DP.round_robin({"b": [1, 2, 3], "w": [1], "m": ["MU", "DKNG"]})
          if x != ("m", "MU")]
    assert [(k, i) for op, k, i in ops if op == "load"] == rr
    # a lane never has two items outstanding (it has one tab)
    out: dict[str, int] = {}
    for op, k, _ in ops:
        out[k] = out.get(k, 0) + (1 if op == "load" else -1 if out.get(k) else 0)
        assert out[k] <= 1
    # every item is finished exactly once
    assert sorted((k, str(i)) for op, k, i in ops if op == "finish") == sorted(
        [("b", "1"), ("b", "2"), ("b", "3"), ("w", "1"), ("m", "MU"), ("m", "DKNG")])


def test_a_single_lane_is_serial():
    from scripts import dowjones_pull as DP
    assert DP.interleave_order({"a": [1, 2]}) == [
        ("load", "a", 1), ("finish", "a", 1), ("load", "a", 2), ("finish", "a", 2)]


def _ops_from_calls(drv: MultiStub, opens: list) -> list[tuple[str, str]]:
    lane_of = {c[3]: c[2] for c in opens}
    seq = []
    for c in drv.calls:
        if c[0] in ("navigate", "click") and c[1] in lane_of and not (
                c[0] == "navigate" and c[2][0] == WR.BLANK_URL):
            seq.append(("load", c[1]))
        elif c[0] == "read_text":
            seq.append(("finish", c[1]))
    return seq


def test_run_plan_follows_the_interleave_order(ledger):
    from scripts import dowjones_pull as DP
    drv = MultiStub()
    _, th = _clock_throttle(ledger / "thr.log")
    lanes = DP.parse_plan("barrons:stock_picks:3,wsj:heard_on_the_street:5,"
                          "marketwatch:analyst_estimates:MU|DKNG")
    rc = DP.run_plan(lanes, parents=DP.resolve_parent_tabs(["barrons", "wsj", "marketwatch"],
                                                          drv.tabs()),
                     driver=drv, throttle=th, stored={})
    assert rc["stopped"] is None and rc["n_articles"] == 6
    opens = [c for c in drv.calls if c[0] == "open_from_tab"]
    tab = {c[2].split("/")[2].split(".")[1][0]: c[3] for c in opens}   # b / w / m -> tab
    expect = DP.interleave_order({"b": [1, 2, 3], "w": [1], "m": ["MU", "DKNG"]},
                                 needs_load=lambda lane, item: not (lane == "m" and item == "MU"))
    assert _ops_from_calls(drv, opens) == [(op, tab[k]) for op, k, _ in expect]


def test_the_settle_is_served_locally_and_covered_by_other_lanes(ledger):
    """No `browser wait` CLI call on a read; the settle after a load is local
    time, and in an interleaved rotation the next lane's throttle slot covers
    it (a settle of 0 s)."""
    from scripts import dowjones_pull as DP
    drv = MultiStub()
    _, th = _clock_throttle(ledger / "thr.log")
    rd = WR.Reader(profile="user", tab="t99", driver=drv, lock=False, throttle=th)
    rd.read_article("https://www.wsj.com/finance/stocks/memory-boom-1a2b3c4d", store=False)
    assert not [c for c in drv.calls if c[0] == "wait"]
    assert rd.settles == [3.5]                    # nothing else ran: the full settle, locally
    drv2 = MultiStub()
    _, th2 = _clock_throttle(ledger / "thr2.log")
    lanes = DP.parse_plan("barrons:stock_picks:3,wsj:heard_on_the_street:5")
    DP.run_plan(lanes, parents=DP.resolve_parent_tabs(["barrons", "wsj"], drv2.tabs()),
                driver=drv2, throttle=th2, stored={})
    rotation_waits = [c for c in drv2.calls if c[0] == "wait"]
    # the only CLI waits left are the one-per-lane first look after open_from_tab
    assert len(rotation_waits) == 2 and all(c[2] == ("--time", "4000") for c in rotation_waits)


# ─────────────────────────── pacing still binds ─────────────────────────────

def _throttle_rows(path: Path) -> list[tuple[datetime, str, float]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        t, h, g = line.split()
        out.append((datetime.fromisoformat(t), h, float(g)))
    return out


def test_interleaved_loads_keep_the_global_gap_and_the_same_host_floor(ledger):
    from scripts import dowjones_pull as DP
    drv = MultiStub()
    _, th = _clock_throttle(ledger / "thr.log", seed=11)
    lanes = DP.parse_plan("barrons:stock_picks:3,wsj:heard_on_the_street:5,"
                          "marketwatch:analyst_estimates:MU|DKNG|NVDA|AMZN|TSM")
    rc = DP.run_plan(lanes, parents=DP.resolve_parent_tabs(["barrons", "wsj", "marketwatch"],
                                                          drv.tabs()),
                     driver=drv, throttle=th, stored={})
    assert rc["stopped"] is None and rc["n_articles"] == 9
    rows = _throttle_rows(ledger / "thr.log")
    assert len(rows) == rc["pages_loaded"]            # every page load took a slot
    gaps = [(b[0] - a[0]).total_seconds() for a, b in zip(rows, rows[1:])]
    assert min(gaps) >= 20 - 1e-6                     # the global drawn gap (20-90 s)
    for host in {r[1] for r in rows}:
        st = [r[0] for r in rows if r[1] == host]
        same = [(b - a).total_seconds() for a, b in zip(st, st[1:])]
        assert all(g >= 60 - 1e-6 for g in same), (host, same)   # the same-host floor
    assert rc["footprint"]["verdict"] == "HUMAN_PACE_OK"


def test_gaps_are_never_constant_even_when_the_throttle_binds_every_load(tmp_path, monkeypatch):
    """Three workers loading back to back at the LIVE pacing (6-20 s, same host
    18 s): the throttle sets every gap, and the gaps still vary -- the footprint
    CV alarm (< 0.15) does not fire and no gap repeats its predecessor."""
    for k, v in (("WEB_READER_MIN_DELAY_S", 6.0), ("WEB_READER_MAX_DELAY_S", 20.0),
                 ("WEB_READER_MIN_SAME_HOST_GAP_S", 18.0)):
        monkeypatch.setattr(C, k, v)
    t = {"t": datetime(2026, 9, 27, tzinfo=timezone.utc)}

    def sleep(s):
        t["t"] += timedelta(seconds=s)
    th = WR.Throttle(tmp_path / "t.log", max_per_hour=999, max_per_day=9999,
                     max_per_day_per_host=9999, now_fn=lambda: t["t"], sleep_fn=sleep, seed=4)
    hosts = ["wsj.com", "barrons.com", "marketwatch.com"]
    log = []
    for i in range(60):
        th.acquire("page", host=hosts[i % 3])
        log.append({"at": t["t"].isoformat()})
        t["t"] += timedelta(seconds=0.5)              # the next worker is already waiting
    fp = WR.footprint_receipt(log, write=False, cli_now={})
    assert fp["cv_of_gaps"] >= WR.FOOTPRINT_CV_ALARM
    assert fp["verdict"] == "HUMAN_PACE_OK"
    tg = th.targets
    assert all(abs(a - b) >= 1.0 for a, b in zip(tg, tg[1:]))
    assert len(set(fp["gaps_s"])) > len(fp["gaps_s"]) // 2


# ───────────────────────── the marker parent, always ─────────────────────────

def _marker_tabs():
    return [{"tabId": "t8", "url": MARKER_URL},
            {"tabId": "t13", "url": "https://www.barrons.com/market-data/bonds/x"},
            {"tabId": "t20", "url": "https://www.wsj.com/health/some-story-4aa63e38"},
            {"tabId": "t32", "url": "https://www.marketwatch.com/investing/stock/mu/analystestimates"}]


def test_every_open_goes_through_open_from_tab_with_the_marker_parent(ledger, monkeypatch):
    from scripts import dowjones_pull as DP
    monkeypatch.setattr(DP, "PARENT_MARKER", DP.MARKER_DEFAULT or "aegis=muratclaw")
    monkeypatch.setattr(C, "WEB_READER_MAX_PAGES_PER_TAB", 2, raising=False)  # rotations
    drv = MultiStub(tabs=_marker_tabs())
    _, th = _clock_throttle(ledger / "thr.log")
    lanes = DP.parse_plan("barrons:stock_picks:3,wsj:heard_on_the_street:5,"
                          "marketwatch:analyst_estimates:MU|DKNG|NVDA")
    parents = DP.resolve_parent_tabs(["barrons", "wsj", "marketwatch"], drv.tabs())
    assert {v["tab"] for v in parents.values()} == {"t8"}
    rc = DP.run_plan(lanes, parents=parents, driver=drv, throttle=th, stored={})
    opens = [c for c in drv.calls if c[0] == "open_from_tab"]
    assert rc["tab_rotations"] and len(opens) > 3            # rotations re-opened tabs
    assert {c[1] for c in opens} == {"t8"}                     # ... all from the marker tab
    assert not [c for c in drv.calls if c[0] == "open"]
    # no marker tab -> refused, before anything opens
    with pytest.raises(WR.ReaderRefused, match="REFUSED_NO_MARKER_TAB"):
        DP.resolve_parent_tabs(["wsj"], _marker_tabs()[1:])


def test_the_worker_launcher_refuses_without_a_marker_tab_and_spawns_nothing(ledger,
                                                                              monkeypatch):
    from scripts import dowjones_pull as DP
    monkeypatch.setattr(DP, "PARENT_MARKER", "aegis=muratclaw")
    monkeypatch.setattr(WR, "ensure_attached", lambda *a, **k: {"reattached": False})

    class NoMarkerOC:
        _OPENED_TABS: set = set()

        def tabs(self, profile_name=None):
            return _marker_tabs()[1:]
    spawned = []
    a = DP.argparse.Namespace(plan="wsj:heard_on_the_street:5,barrons:stock_picks:3",
                              workers=3, profile="user", parent_tabs="", max_pages=20,
                              fresh_since="")
    code = DP._launch_workers(a, "2026-09-27", "010203", oc=NoMarkerOC(),
                              spawn=lambda av: spawned.append(av))
    assert code == 2 and spawned == []


# ─────────────────── no guard removed: the real client ───────────────────────

WSJ_A = "https://www.wsj.com/finance/stocks/a-story-1a2b3c4d"


class ReplyCLI:
    """`user` profile behind the REAL guard. `navigate` replies the way
    openclaw 2026.9.5 does (`navigated to <url>`), landing on `land` when set."""

    PROFILES = "user: running (3 tabs) [existing-session]\n  transport: chrome-mcp\n"

    def __init__(self, land: str | None = None, reply: bool = True):
        self.calls: list[list[str]] = []
        self.urls = {"1": "https://www.wsj.com/news/heard-on-the-street"}
        self.land, self.reply = land, reply

    def h(self, n: str) -> str:
        return f"chrome-mcp:zzz:{n}"

    def __call__(self, args, **kw):
        self.calls.append(list(args))
        verb = OC._cmd_key(args)
        ok = lambda out: subprocess.CompletedProcess(args, 0, out, "")   # noqa: E731
        if verb == "browser profiles":
            return ok(self.PROFILES)
        if verb == "browser tabs":
            return ok(json.dumps({"tabs": [{"tabId": f"t{n}", "targetId": self.h(n), "url": u}
                                           for n, u in self.urls.items()]}))
        if verb == "browser status":
            return ok('{"running": true}')
        tid = args[args.index("--target-id") + 1] if "--target-id" in args else None
        n = str(tid).rsplit(":", 1)[-1] if tid else None
        if verb == "browser navigate":
            dest = args[args.index("navigate") + 1]
            self.urls[n] = self.land or dest if dest != WR.BLANK_URL else dest
            return ok(f"navigated to {self.urls[n]}" if self.reply else "ok")
        if verb == "browser evaluate":
            return ok(json.dumps({"ok": True, "targetId": tid, "result": {
                "url": self.urls.get(n), "title": "T", "text": "body text " * 20}}))
        return ok("ok")


@pytest.fixture
def real_client(monkeypatch):
    t = {"t": 1000.0}
    monkeypatch.setattr(OC, "_clock", lambda: t["t"])
    OC.invalidate_profile_cache()
    OC._TABS_NONCES.clear()
    yield t
    OC.invalidate_profile_cache()
    OC._OPENED_TABS.difference_update({h for h in list(OC._OPENED_TABS)
                                       if h.startswith("chrome-mcp:zzz:")})


def _install(monkeypatch, fake):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: fake(
        list(cmd[len(OC._resolve_cli()["prefix"]):]), **kw))


def _audit(monkeypatch, fake):
    """Record every host check (`_operator_tab`) and every ACTION verb, in order."""
    events: list[tuple[str, str]] = []
    orig = OC._operator_tab

    def checked(target_id, **kw):
        events.append(("check", str(target_id)))
        return orig(target_id, **kw)
    monkeypatch.setattr(OC, "_operator_tab", checked)
    orig_call = fake.__call__

    class Rec:
        def __call__(self, args, **kw):
            v = OC._cmd_key(args)
            if v in ("browser navigate", "browser press", "browser click", "browser evaluate",
                     "browser close", "browser snapshot", "browser wait"):
                tid = args[args.index("--target-id") + 1] if "--target-id" in args else "?"
                events.append(("act:" + v.split()[1], str(tid)))
            return orig_call(args, **kw)
    _install(monkeypatch, Rec())
    return events


def test_every_action_keeps_its_host_check_and_navigate_its_landed_url_check(
        monkeypatch, real_client, tmp_path):
    fake = ReplyCLI()
    events = _audit(monkeypatch, fake)
    tab = fake.h("1")
    now = {"t": datetime(2026, 9, 27, 14, tzinfo=timezone.utc)}
    thr = WR.Throttle(tmp_path / "thr.log", now_fn=lambda: now["t"],
                      sleep_fn=lambda s: now.__setitem__("t", now["t"] + timedelta(seconds=s)),
                      seed=3)
    rd = WR.Reader(profile="user", tab=tab, throttle=thr, lock=False)
    OC.reset_cli_ledger()
    art = rd.read_article(WSJ_A, store=False)
    assert art["url"] == WSJ_A
    acts = [i for i, e in enumerate(events) if e[0].startswith("act:")]
    assert [events[i][0] for i in acts][0] == "act:navigate"
    assert "act:wait" not in {e[0] for e in events}             # the timer wait is local now
    last = -1
    for i in acts:                    # a host check on THIS tab since the previous action
        assert ("check", events[i][1]) in events[last + 1:i], events[last + 1:i + 1]
        last = i
    n_press = sum(1 for e in events if e[0] == "act:press")
    assert sum(1 for e in events if e[0] == "check") == len(acts) == n_press + 2
    led = OC.cli_ledger()
    # the post-navigate URL check came from the navigate reply (no extra listing)
    assert led["cache"]["url_from_reply"] == 1 and led["cache"]["url_rereads"] == 0
    assert led["by_cmd"]["browser tabs"]["calls"] == 1          # the pre-navigate check only
    assert "browser wait" not in led["by_cmd"]
    fp = WR.footprint_receipt(rd.log, reads=rd.reads, scrolled=rd.scrolled_reads, write=False,
                              cli_now=led, cli_since=None)
    assert fp["cli_by_verb"]["browser press"]["calls"] == n_press   # seconds per verb, receipted
    print(f"\none article through the real guard: {led['calls']} CLI calls "
          f"({ {k: v['calls'] for k, v in led['by_cmd'].items()} })")


def test_an_off_host_landing_in_the_navigate_reply_still_refuses(monkeypatch, real_client,
                                                                 tmp_path):
    fake = ReplyCLI(land="https://sso.accounts.dowjones.com/login?target=x")
    _install(monkeypatch, fake)
    thr = WR.Throttle(tmp_path / "thr.log", now_fn=lambda: datetime.now(timezone.utc),
                      sleep_fn=lambda s: None, min_delay_s=0, max_delay_s=0)
    rd = WR.Reader(profile="user", tab=fake.h("1"), throttle=thr, lock=False)
    with pytest.raises(WR.ReaderRefused, match="REFUSED_LEFT_HOSTS"):
        rd.navigate(WSJ_A)


def test_a_navigate_reply_without_the_url_falls_back_to_a_fresh_listing(monkeypatch,
                                                                        real_client):
    fake = ReplyCLI(reply=False)
    _install(monkeypatch, fake)
    OC.reset_cli_ledger()
    r = OC.browser("navigate", WSJ_A, profile_name="user", target_id=fake.h("1"))
    assert r["tab_url_after_source"] == "tabs_reread" and r["tab_url_after"] == WSJ_A
    assert OC.cli_ledger()["cache"]["url_rereads"] == 1


def test_attached_status_is_not_a_per_page_call(monkeypatch, real_client):
    fake = ReplyCLI()
    _install(monkeypatch, fake)
    OC._ATTACHED_CACHE.clear()
    tab = fake.h("1")
    for i in range(4):                      # four pages, 70 s apart (> the old 60 s cache)
        OC.browser("navigate", WSJ_A, profile_name="user", target_id=tab)
        real_client["t"] += 70
        OC._ATTACHED_CACHE.update({k: (v[0] - 70, v[1]) for k, v in OC._ATTACHED_CACHE.items()})
    assert sum(1 for c in fake.calls if OC._cmd_key(c) == "browser status") == 1
    OC.invalidate_profile_cache("user")     # any failure drops it: the next call re-asks
    OC.browser("navigate", WSJ_A, profile_name="user", target_id=tab)
    assert sum(1 for c in fake.calls if OC._cmd_key(c) == "browser status") == 2


# ───────────────────── workers: slots, locks, cleanup ────────────────────────

def test_two_workers_never_take_the_same_throttle_slot(tmp_path):
    """Two 'workers' (threads, each with its OWN Throttle on the SAME file, as
    two processes would have) load back to back: every recorded slot is at
    least the minimum gap after the previous one, whoever took it."""
    path = tmp_path / "shared.log"
    errs: list[BaseException] = []

    def worker(host: str, seed: int) -> None:
        try:
            th = WR.Throttle(path, min_delay_s=0.15, max_delay_s=0.3, min_same_host_gap_s=0,
                             max_per_hour=999, max_per_day=999, max_per_day_per_host=999,
                             seed=seed)
            for _ in range(5):
                th.acquire("page", host=host)
        except BaseException as exc:  # noqa: BLE001
            errs.append(exc)
    ts = [threading.Thread(target=worker, args=(h, s)) for h, s in (("wsj.com", 1),
                                                                    ("barrons.com", 2))]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    assert not errs
    rows = _throttle_rows(path)
    assert len(rows) == 10 and {r[1] for r in rows} == {"wsj.com", "barrons.com"}
    stamps = [r[0] for r in rows]
    assert stamps == sorted(stamps) and len(set(stamps)) == 10
    gaps = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:])]
    assert min(gaps) >= 0.15 - 0.02, gaps


def test_the_throttle_lock_excludes_another_process(tmp_path):
    lock = tmp_path / "t.log.lock"
    code = ("import sys,time; sys.path.insert(0, %r); "
            "from backend.services import disk_guard as DG\n"
            "with DG.file_lock(__import__('pathlib').Path(%r)):\n"
            "    print('held', flush=True); time.sleep(20)\n") % (
        str(Path(__file__).resolve().parents[2]), str(lock))
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "held"
        t0 = time.monotonic()
        with pytest.raises(DG.FileLockTimeout):
            with DG.file_lock(lock, timeout_s=0.3):
                pass
        assert time.monotonic() - t0 >= 0.3
    finally:
        p.kill()                                     # our own child, by its handle
        p.wait(10)
    with DG.file_lock(lock, timeout_s=2):            # free again once it is gone
        pass


def test_reader_locks_one_per_worker_and_never_mixed_with_a_single_session(ledger,
                                                                           monkeypatch):
    live = {101, 102, 103}
    monkeypatch.setattr(WR, "_pid_alive", lambda pid: pid in live)
    a = WR.acquire_reader_lock(worker="wsj", pid=101)
    b = WR.acquire_reader_lock(worker="barrons", pid=102)          # a second worker id: fine
    assert a != b and a.name == "_reader_wsj.lock"
    with pytest.raises(WR.ReaderRefused, match="REFUSED_READER_BUSY"):
        WR.acquire_reader_lock(worker="wsj", pid=103)              # same id, live holder
    with pytest.raises(WR.ReaderRefused, match="REFUSED_READER_BUSY"):
        WR.acquire_reader_lock(pid=103)                            # single session vs workers
    WR.release_reader_lock(a, pid=101)
    WR.release_reader_lock(b, pid=102)
    s = WR.acquire_reader_lock(pid=103)
    with pytest.raises(WR.ReaderRefused, match="REFUSED_READER_BUSY"):
        WR.acquire_reader_lock(worker="marketwatch", pid=101)      # worker vs single session
    WR.release_reader_lock(s, pid=103)
    with pytest.raises(WR.ReaderRefused, match="REFUSED_WORKER_ID"):
        WR.acquire_reader_lock(worker="../x", pid=101)


def _receipt(d: Path, name: str, **kw) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps({"receipt": "dowjones_pull.plan", **kw}), encoding="utf-8")


class CleanupDriver:
    def __init__(self, handles):
        self._OPENED_TABS: set = set()
        self.closed: list[str] = []
        self.listing = [{"targetId": h, "url": "https://www.wsj.com/finance/x-1a2b3c4d"}
                        for h in handles]

    def tabs(self, profile_name=None):
        return self.listing

    def browser(self, verb, *a, profile_name=None, target_id=None, url=None):
        assert verb == "close" and target_id in self._OPENED_TABS
        self.closed.append(target_id)
        return {"rc": 0}


def test_startup_cleanup_never_closes_a_live_workers_tab(tmp_path, monkeypatch):
    from scripts import dowjones_pull as DP
    rdir = tmp_path / "receipts"
    day = datetime.now(timezone.utc).date().isoformat()
    LIVE, DEAD, ME = 4242, 4343, 4444
    _receipt(rdir, f"plan_{day}_010101_wsj.json", worker="wsj", pid=LIVE,
             opened=["chrome-mcp:s:5"], in_progress=True)
    _receipt(rdir, f"plan_{day}_010102_barrons.json", worker="barrons", pid=DEAD,
             opened=["chrome-mcp:s:6"], in_progress=True)
    _receipt(rdir, f"plan_{day}_010103.json", opened=["chrome-mcp:s:7"])     # single session
    alive = lambda pid: pid == LIVE                                          # noqa: E731
    # BEFORE (the hazard): the old rule read every receipt, so a second run
    # starting next to a live one would have adopted and closed ITS tabs
    drv0 = CleanupDriver(["chrome-mcp:s:5", "chrome-mcp:s:6", "chrome-mcp:s:7"])
    WR.close_leftover_tabs(drv0, "user", ["chrome-mcp:s:5", "chrome-mcp:s:6", "chrome-mcp:s:7"])
    assert "chrome-mcp:s:5" in drv0.closed
    # AFTER: ownership by worker id, and never a live pid's receipt
    kw = dict(rdir=rdir, me=ME, alive=alive)
    assert DP.previous_opened_handles(worker="wsj", **kw) == []      # its own run is ALIVE
    assert DP.previous_opened_handles(worker="barrons", **kw) == ["chrome-mcp:s:6"]
    assert DP.previous_opened_handles(worker=None, **kw) == ["chrome-mcp:s:7"]
    assert DP.previous_opened_handles(worker="marketwatch", **kw) == []
    # through startup_cleanup, as a worker start runs it
    monkeypatch.setattr(DP.DF, "receipts_dir", lambda: rdir)
    monkeypatch.setattr(WR, "_pid_alive", alive)
    drv = CleanupDriver(["chrome-mcp:s:5", "chrome-mcp:s:6", "chrome-mcp:s:7"])
    res = DP.startup_cleanup(drv, "user", worker="barrons")
    assert res["closed"] == ["chrome-mcp:s:6"] and drv.closed == ["chrome-mcp:s:6"]
    # the wsj worker restarting (its old run now dead) closes ITS leftovers only
    monkeypatch.setattr(WR, "_pid_alive", lambda pid: False)
    drv2 = CleanupDriver(["chrome-mcp:s:5", "chrome-mcp:s:7"])
    assert DP.startup_cleanup(drv2, "user", worker="wsj")["closed"] == ["chrome-mcp:s:5"]


def test_a_run_plan_receipt_names_its_worker_and_pid(ledger, monkeypatch):
    import os
    from scripts import dowjones_pull as DP
    drv = MultiStub()
    _, th = _clock_throttle(ledger / "thr.log")
    rc = DP.run_plan(DP.parse_plan("barrons:stock_picks:1"),
                     parents=DP.resolve_parent_tabs(["barrons"], drv.tabs()),
                     driver=drv, throttle=th, stored={}, worker="barrons")
    assert rc["worker"] == "barrons" and rc["pid"] == os.getpid()
    assert not (WR.corpus_root() / "_reader_barrons.lock").exists()   # released


# ──────────────────────────── splitting + spawning ───────────────────────────

WIDE = ("marketwatch:analyst_estimates:VKTX|NTLA|HWM,wsj_search:VKTX|NTLA,"
        "barrons_search:VKTX|NTLA,barrons:stock_picks:40,wsj:heard_on_the_street:40,"
        "barrons:big_money_poll:5")


def test_the_plan_splits_by_site_and_round_trips():
    from scripts import dowjones_pull as DP
    lanes = DP.parse_plan(WIDE)
    g = DP.split_lanes_by_site(lanes, 3)
    assert list(g) == ["marketwatch", "wsj", "barrons"]
    assert [ln["lane"] for ln in g["barrons"]] == ["barrons:search", "barrons:stock_picks",
                                                  "barrons:big_money_poll"]
    for lns in g.values():
        assert DP.parse_plan(DP.plan_spec(lns)) == lns
    g2 = DP.split_lanes_by_site(lanes, 2)
    assert sorted(g2) == ["g1", "g2"] and sum(len(v) for v in g2.values()) == len(lanes)
    assert all(len({ln["source"] for ln in v}) >= 1 for v in g2.values())
    b = DP.split_budget(900, g)
    assert sum(b.values()) >= 900 and b["barrons"] > b["marketwatch"]
    assert DP.split_budget(None, g) == {k: None for k in g}


def test_run_workers_starts_one_process_per_site_and_folds_their_receipts(ledger,
                                                                           monkeypatch):
    from scripts import dowjones_pull as DP
    rdir = ledger / "receipts"
    monkeypatch.setattr(DP.DF, "receipts_dir", lambda: rdir)
    groups = DP.split_lanes_by_site(DP.parse_plan(WIDE), 3)
    stamp = "2026-09-27_010203"
    started = []

    class P:
        def __init__(self, av):
            self.av, self.pid = av, 9000 + len(started)
            started.append(self)
            wid = av[av.index("--worker") + 1]
            _receipt(rdir, f"plan_{stamp}_{wid}.json", worker=wid, pid=self.pid,
                     n_articles={"marketwatch": 3, "wsj": 2, "barrons": 0}[wid],
                     stopped=None if wid != "barrons" else "REFUSED_THROTTLE_DAY: x",
                     lanes={})

        def wait(self):
            return 2 if "barrons" in self.av else 0
    out = DP.run_workers(groups, stamp=stamp, profile="user", max_pages=900,
                         fresh_since="2026-09-27", spawn=P, bind=lambda pid: {"bound": True})
    assert [p.av[p.av.index("--worker") + 1] for p in started] == ["marketwatch", "wsj",
                                                                    "barrons"]
    for p in started:
        assert "--handoff" in p.av and p.av[p.av.index("--profile") + 1] == "user"
        assert "--parent-tab" not in p.av          # each worker resolves the MARKER itself
    pidf = json.loads(DP.workers_pid_path().read_text(encoding="utf-8"))
    assert pidf["workers"] == {"marketwatch": 9000, "wsj": 9001, "barrons": 9002}
    assert out["n_articles"] == 5 and out["rc"] == 2
    assert out["refused"].startswith("barrons: rc 2: REFUSED_THROTTLE_DAY")
