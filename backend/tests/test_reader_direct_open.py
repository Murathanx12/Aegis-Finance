"""The dedicated MuratClaw Chrome opens lane tabs DIRECTLY (2026-09-28).

Observed live 16:01-16:16 HKT: `open_from_tab` (a `window.open` inside a
parent tab) produced 0 new tabs on every lane of every worker in the dedicated
Chrome -- a fresh profile's pop-up blocker refuses a `window.open` without a
user gesture -- so the queue read 0 articles, burnt 16 throttle slots on opens
that loaded nothing, and the supervisor relaunched it every 5 minutes.

Pinned here:
* the dedicated profile opens with `open_tab` (instance-gated inside the
  client); `open_from_tab` is never called for it and stays for other profiles;
* no parent tab is REQUIRED for the dedicated profile (this replaces the rule
  that a run refuses with REFUSED_NO_PARENT_TAB / REFUSED_NO_MARKER_TAB when no
  Dow Jones tab is open) and the owner's own tab is never navigated or closed;
* a failed open gives its throttle slot back (hourly/daily caps untouched);
* a run where every lane failed to open ends READER_CANNOT_OPEN_TABS, and the
  supervisor backs off on it (<= 3 relaunches per rolling hour, doubling);
* the HTTP transport carries a page-load timeout on navigate/open, and the
  dedicated profile defaults to HTTP.

Test doubles only: no network, browser or CLI.
"""
from __future__ import annotations

import pytest

from backend import config as C
from backend.services import gateway_repair as GR
from backend.services import openclaw_client as OC
from backend.services import openclaw_http as OH
from backend.services import web_reader as WR
from backend.tests.test_dowjones_chunk_j import (  # noqa: F401 -- fixtures reused on purpose
    Clock, MultiStub, _clock_throttle, _no_parent_marker, ledger)

OWNER_TAB = {"tabId": "OWNER1", "url": "https://www.wsj.com/"}


class DirectStub(MultiStub):
    """A dedicated-instance driver: `open_tab` works, `open_from_tab` would be
    the pop-up-blocked path and fails loudly if anything calls it."""

    def __init__(self, *, fail_open: bool = False, make_then_refuse: bool = False, **kw):
        super().__init__(tabs=[dict(OWNER_TAB)], **kw)
        self._OPENED_TABS: set[str] = set()
        self.fail_open, self.make_then_refuse = fail_open, make_then_refuse

    def dedicated_profiles(self):
        return ("muratclaw",)

    def open_tab(self, url, profile_name="muratclaw"):
        if self.fail_open:
            self.calls.append(("open_tab_failed", None, url))
            raise OC.OpenClawRefused("REFUSED_OPEN_TAB: rc 1: 'tool execution failed'")
        self.n += 1
        tid = f"T{self.n}"
        if self.make_then_refuse:
            self._OPENED_TABS.add(tid)
            self.calls.append(("open_tab_off_host", tid, url))
            raise OC.OpenClawRefused(f"REFUSED_OPERATOR_TAB_HOST: the new tab {tid!r} is on "
                                     f"'https://evil.example/'")
        self._OPENED_TABS.add(tid)
        self.cur[tid] = url
        self.calls.append(("open_tab", None, url, tid))
        return {"verb": "open", "new_tab": tid, "target_id": tid, "url": url}

    def open_from_tab(self, parent, url, profile_name="muratclaw"):
        raise AssertionError("open_from_tab must not be used on the dedicated instance")


def _lines(path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


# ── the open itself ──────────────────────────────────────────────────────────

def test_the_dedicated_profile_opens_directly_without_a_parent(ledger):
    drv = DirectStub()
    _, th = _clock_throttle(ledger / "thr.log")
    assert WR.direct_open_ok(drv, "muratclaw")
    op = WR.open_lane_tab(drv, "muratclaw", "https://www.wsj.com/news/markets", parent=None,
                          throttle=th, host="wsj.com")
    assert op["new_tab"] == "T51" and op["direct"] is True and op["how"] == "direct_open"
    assert [c[0] for c in drv.calls] == ["open_tab"]
    assert len(_lines(ledger / "thr.log")) == 1           # the open IS a page load


def test_a_profile_that_is_not_dedicated_still_opens_from_its_parent(ledger):
    drv = MultiStub()                                     # no dedicated_profiles, no open_tab
    _, th = _clock_throttle(ledger / "thr.log")
    assert not WR.direct_open_ok(drv, "muratclaw")
    op = WR.open_lane_tab(drv, "muratclaw", "https://www.wsj.com/news/markets", parent="t20",
                          throttle=th, host="wsj.com")
    assert drv.calls[0][:2] == ("open_from_tab", "t20") and op["direct"] is False
    with pytest.raises(WR.ReaderRefused, match="REFUSED_NO_PARENT_TAB"):
        WR.open_lane_tab(drv, "muratclaw", "https://www.wsj.com/", parent=None, throttle=th)


# ── a failed open is not a page load ─────────────────────────────────────────

def test_a_failed_open_gives_its_slot_back_and_the_hourly_cap_is_untouched(ledger):
    ck = Clock()
    th = WR.Throttle(ledger / "thr.log", now_fn=ck.now, sleep_fn=ck.sleep, seed=3,
                     max_per_hour=1, max_per_day=1, max_per_day_per_host=1)
    bad = DirectStub(fail_open=True)
    for _ in range(3):                                    # three failed opens ...
        with pytest.raises(OC.OpenClawRefused, match="REFUSED_OPEN_TAB"):
            WR.open_lane_tab(bad, "muratclaw", "https://www.wsj.com/", throttle=th,
                             host="wsj.com")
    assert _lines(ledger / "thr.log") == [] and len(th.refunds) == 3
    # ... and the ONE slot of the hour, the day and the host is still free
    op = WR.open_lane_tab(DirectStub(), "muratclaw", "https://www.wsj.com/", throttle=th,
                          host="wsj.com")
    assert op["new_tab"] and len(_lines(ledger / "thr.log")) == 1
    with pytest.raises(WR.ReaderRefused, match="REFUSED_THROTTLE"):
        th.acquire("page", host="wsj.com")


def test_refund_removes_only_its_own_line(ledger):
    ck = Clock()
    th = WR.Throttle(ledger / "thr.log", now_fn=ck.now, sleep_fn=ck.sleep, seed=3)
    th.acquire("page", host="barrons.com")
    first = _lines(ledger / "thr.log")
    ck.sleep(5)
    th.acquire("page", host="wsj.com")
    assert th.refund("test") is True and _lines(ledger / "thr.log") == first
    assert th.refund("again") is False                   # once only


def test_an_open_that_made_a_tab_before_refusing_keeps_the_slot_and_closes_our_tab(ledger):
    drv = DirectStub(make_then_refuse=True)
    _, th = _clock_throttle(ledger / "thr.log")
    with pytest.raises(OC.OpenClawRefused, match="OPERATOR_TAB_HOST"):
        WR.open_lane_tab(drv, "muratclaw", "https://www.wsj.com/", throttle=th, host="wsj.com")
    assert len(_lines(ledger / "thr.log")) == 1 and th.refunds == []   # a page did load
    assert drv.closed == ["T51"]                          # ours, closed; the owner's untouched


# ── parents are not required on the dedicated instance ───────────────────────

def test_resolve_parent_tabs_direct_needs_no_tab_and_never_picks_the_owners():
    from scripts import dowjones_pull as DP
    out = DP.resolve_parent_tabs(["wsj", "barrons"], [], direct=True)
    assert {k: v["tab"] for k, v in out.items()} == {"wsj": None, "barrons": None}
    out = DP.resolve_parent_tabs(["wsj"], [dict(OWNER_TAB)], direct=True)
    assert out["wsj"]["tab"] is None and out["wsj"]["how"] == DP.DIRECT_HOW
    # an operator profile that is NOT dedicated keeps the old rule
    with pytest.raises(WR.ReaderRefused, match="REFUSED_NO_PARENT_TAB"):
        DP.resolve_parent_tabs(["wsj"], [])


def test_run_plan_on_the_dedicated_instance_reads_and_leaves_the_owners_tab_alone(ledger):
    from scripts import dowjones_pull as DP
    drv = DirectStub()
    _, th = _clock_throttle(ledger / "thr.log")
    lanes = DP.parse_plan("barrons:stock_picks:2,wsj:heard_on_the_street:2")
    parents = DP.resolve_parent_tabs(["barrons", "wsj"], [], direct=True)
    rc = DP.run_plan(lanes, parents=parents, driver=drv, throttle=th, stored={})
    opens = [c for c in drv.calls if c[0] == "open_tab"]
    # 2026-09-28: a fresh tab per page (a read tab is closed, never blanked), so
    # more than one open per lane; every one of them is closed
    assert len(opens) >= 2 and rc["stopped"] is None and rc["n_articles"] >= 2
    touched = {c[1] for c in drv.calls if c[0] in ("navigate", "close", "press", "click",
                                                    "snapshot", "evaluate")}
    assert "OWNER1" not in touched and "OWNER1" not in drv.closed
    assert sorted(drv.closed) == sorted(c[3] for c in opens) and rc["orphaned_tabs"] == []


def test_every_lane_failing_to_open_is_a_named_fault_and_burns_no_slot(ledger):
    from scripts import dowjones_pull as DP
    drv = DirectStub(fail_open=True)
    _, th = _clock_throttle(ledger / "thr.log")
    lanes = DP.parse_plan("barrons:stock_picks:2,wsj:heard_on_the_street:2")
    rc = DP.run_plan(lanes, parents=DP.resolve_parent_tabs(["barrons", "wsj"], [], direct=True),
                     driver=drv, throttle=th, stored={})
    assert str(rc["stopped"]).startswith("READER_CANNOT_OPEN_TABS: 2 of 2 lane(s)")
    assert _lines(ledger / "thr.log") == []
    assert GR.classify_exit(f'"refused": "w1: rc 2: {rc["stopped"]}"')["kind"] == \
        "READER_CANNOT_OPEN_TABS"


def test_a_rotated_tab_on_the_dedicated_instance_reopens_directly(ledger):
    drv = DirectStub()
    _, th = _clock_throttle(ledger / "thr.log")
    op = WR.open_lane_tab(drv, "muratclaw", "https://www.wsj.com/a", throttle=th, host="wsj.com")
    rd = WR.Reader(profile="muratclaw", tab=op["new_tab"], throttle=th, driver=drv, lock=False,
                   direct_open=True, max_tab_pages=1)
    rd.pages, rd.tab_pages = 1, 1
    rd.navigate("https://www.wsj.com/b")                  # 1 page served -> rotate
    assert rd.tab == "T52" and rd.rotations and drv.closed == ["T51"]
    drv.fail_open = True
    rd.tab_pages = 1
    n_lines, n_pages = len(_lines(ledger / "thr.log")), rd.pages
    with pytest.raises(OC.OpenClawRefused):
        rd.navigate("https://www.wsj.com/c")
    assert len(_lines(ledger / "thr.log")) == n_lines and rd.pages == n_pages
    assert rd.needs_reopen


# ── the supervisor backs off ─────────────────────────────────────────────────

def test_the_supervisor_backs_off_on_an_open_fault_at_most_three_an_hour():
    from scripts import night_reader_supervisor as S
    b = S.open_fault_budget()
    healthy = {"healthy": True}
    t, relaunches = 0.0, []
    while t < 3600.0:                                     # a tick every 5 minutes for an hour
        ok, _ = b.allow(t)
        act = S.decide(kind=S.OPEN_FAULT, probe=healthy, restarts=len(relaunches),
                       since_launch_s=None, budget_ok=True, open_fault_ok=ok)
        if act == "relaunch":
            b.spend(t)
            relaunches.append(t)
        else:
            assert act == "wait_open_fault"
        t += 300.0
    assert len(relaunches) == 3
    gaps = [b_ - a_ for a_, b_ in zip(relaunches, relaunches[1:])]
    assert gaps[1] > gaps[0] >= S.OPEN_FAULT_BACKOFF_S    # doubling
    # a plain crash is not throttled by the open-fault budget
    assert S.decide(kind="READER_CRASH", probe=healthy, restarts=1, since_launch_s=10 ** 6,
                    budget_ok=True, open_fault_ok=False) == "relaunch"


def test_the_supervisor_reads_its_paths_from_the_ledger_dir():
    from scripts import night_reader_supervisor as S
    assert S.DATA == type(S.DATA)(C.OPTIMUS_LEDGER_DIR)


# ── transport ────────────────────────────────────────────────────────────────

def test_http_navigate_and_open_carry_a_page_load_timeout():
    for verb in ("navigate", "open"):
        p = OH.parse_argv(["browser", "--browser-profile", "muratclaw", verb,
                           "https://www.marketwatch.com/markets"])
        assert OH.tool_args(p)["timeoutMs"] == C.OPENCLAW_HTTP_NAVIGATE_TIMEOUT_MS > 20000

    class Sess:
        def __init__(self):
            self.timeouts = []

        def post(self, url, json=None, headers=None, timeout=None):
            self.timeouts.append(timeout)

            class R:
                status_code = 200

                @staticmethod
                def json():
                    return {"ok": True, "result": {"details": {"url": "https://x"}}}
            return R()
    s = Sess()
    tr = OH.HttpTransport(session=s, token_fn=lambda: "tok", url="http://h")
    tr.run(["browser", "--browser-profile", "muratclaw", "navigate",
            "https://www.marketwatch.com/markets"], timeout=30)
    assert s.timeouts[0] >= C.OPENCLAW_HTTP_NAVIGATE_TIMEOUT_MS / 1000.0


def test_the_dedicated_profile_defaults_to_http_and_others_to_the_cli(monkeypatch):
    monkeypatch.delenv(OC.TRANSPORT_ENV, raising=False)
    assert OC.browser_transport("muratclaw") == C.OPENCLAW_BROWSER_TRANSPORT_DEDICATED == "http"
    assert OC.browser_transport() == "cli" and OC.browser_transport("other") == "cli"
    monkeypatch.setenv(OC.TRANSPORT_ENV, "cli")           # the CLI stays selectable
    assert OC.browser_transport("muratclaw") == "cli"



def test_a_cut_snapshot_with_only_nav_links_is_reread_interactive(ledger):
    """Live 2026-09-28, Barron's PLTR: the full snapshot was cut at 39,997 chars
    with 38 nav links and 0 of the page's 37 article links; the interactive one
    had them. A cut snapshot is re-read even when it shows SOME links."""
    nav = "".join(f'- link "Section {i}" [ref=n{i}] [url=https://www.barrons.com/s{i}]' + chr(10)
                  for i in range(5))
    full = nav + "x" * C.WEB_READER_SNAPSHOT_CUT_CHARS
    arts = nav + "".join(
        f'- link "A long enough headline number {i}" [ref=a{i}] '
        f'[url=https://www.barrons.com/articles/story-{i}-{i:08x}]' + chr(10) for i in range(3))

    class Snap(DirectStub):
        def browser(self, verb, *args, profile_name=None, target_id=None, url=None):
            self.calls.append((verb, target_id, args))
            if verb == "snapshot":
                return {"rc": 0, "stdout": arts if "--interactive" in args else full}
            return {"rc": 0, "verb": verb, "stdout": ""}
    drv = Snap()
    _, th = _clock_throttle(ledger / "thr.log")
    rd = WR.Reader(profile="muratclaw", tab="T1", throttle=th, driver=drv, lock=False)
    snap = rd.snapshot()
    assert len(WR.parse_snapshot(snap)["links"]) == 8 and rd.snapshot_fallbacks == 1
    # a short snapshot with links is NOT re-read
    full = nav
    drv.calls.clear()
    rd.snapshot()
    assert sum(1 for c in drv.calls if c[0] == "snapshot") == 1
