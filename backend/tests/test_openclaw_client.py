"""openclaw_client: the profile assertion is cached, and the cache yields.

No browser, no gateway, no network: every CLI round trip is a fake `_run` that
COUNTS what it was asked. The measured claim (2026-09-27): ten verbs in a row
cost ONE `browser profiles` call, not ten, and after a refusal the next verb
re-checks.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter

import pytest

from backend.services import openclaw_client as OC

PROFILES_OUT = ("muratclaw: running [default]\n  port: 18801\n"
                "user: running (3 tabs) [existing-session]\n  transport: chrome-mcp\n"
                "chrome: stopped [extension]\n")

TABS_JSON = json.dumps({"tabs": [
    {"tabId": "t20", "targetId": "chrome-mcp:aaa:1",
     "url": "https://www.wsj.com/news/heard-on-the-street"}]})


class FakeCLI:
    """A stand-in for `_run` that records every invocation by sub-command."""

    def __init__(self, profiles_out: str = PROFILES_OUT, tabs_out: str = TABS_JSON,
                 verb_rc: int = 0):
        self.calls: list[list[str]] = []
        self.profiles_out = profiles_out
        self.tabs_out = tabs_out
        self.verb_rc = verb_rc

    def __call__(self, args, **kw):
        self.calls.append(list(args))
        if args[:2] == ["browser", "profiles"]:
            return subprocess.CompletedProcess(args, 0, self.profiles_out, "")
        if "tabs" in args:
            return subprocess.CompletedProcess(args, 0, self.tabs_out, "")
        if "status" in args:
            return subprocess.CompletedProcess(args, 0, '{"running": true}', "")
        return subprocess.CompletedProcess(args, self.verb_rc, "ok", "")

    def count(self) -> Counter:
        return Counter(OC._cmd_key(a) for a in self.calls)


@pytest.fixture(autouse=True)
def _clean_cache():
    OC.invalidate_profile_cache()
    yield
    OC.invalidate_profile_cache()


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(OC, "_clock", lambda: now["t"])
    return now


def test_ten_verbs_cost_one_profiles_call_not_ten(monkeypatch, clock):
    fake = FakeCLI()
    monkeypatch.setattr(OC, "_run", fake)
    results = []
    for verb in ("navigate", "wait", "snapshot", "scrollintoview", "scrollintoview",
                 "wait", "press", "snapshot", "wait", "screenshot"):
        args = ("https://example.com/a",) if verb == "navigate" else ()
        results.append(OC.browser(verb, *args, profile_name="muratclaw"))
        clock["t"] += 5.0                      # 45 s across the run: inside the TTL
    c = fake.count()
    print(f"\nprofiles calls for 10 verbs: {c['browser profiles']} (was 10 before the cache)")
    assert c["browser profiles"] == 1
    assert [r["profile_check"] for r in results] == ["checked"] + ["cached"] * 9
    # The receipt carries the verb's own CLI time and the pre-check time.
    assert all(isinstance(r["seconds"], float) and isinstance(r["check_seconds"], float)
               and r["rc"] == 0 for r in results)


def test_without_the_cache_it_would_have_been_ten(monkeypatch, clock):
    """The 'before' number, measured the same way: a TTL of 0 is the old code."""
    fake = FakeCLI()
    monkeypatch.setattr(OC, "_run", fake)
    monkeypatch.setattr(OC, "OPENCLAW_PROFILE_ASSERT_TTL_S", 0.0)
    for _ in range(10):
        OC.browser("wait", "--time", "1000", profile_name="muratclaw")
    assert fake.count()["browser profiles"] == 10


def test_the_ttl_expires(monkeypatch, clock):
    fake = FakeCLI()
    monkeypatch.setattr(OC, "_run", fake)
    OC.browser("snapshot", profile_name="muratclaw")
    clock["t"] += OC.OPENCLAW_PROFILE_ASSERT_TTL_S - 1
    OC.browser("snapshot", profile_name="muratclaw")
    assert fake.count()["browser profiles"] == 1
    clock["t"] += 2
    OC.browser("snapshot", profile_name="muratclaw")
    assert fake.count()["browser profiles"] == 2


def test_the_cache_is_per_profile_name(monkeypatch, clock):
    fake = FakeCLI()
    monkeypatch.setattr(OC, "_run", fake)
    OC.assert_profile(name="muratclaw")
    OC.assert_profile(name="user")
    OC.assert_profile(name="muratclaw")
    OC.assert_profile(name="user")
    assert fake.count()["browser profiles"] == 2


def test_a_failed_assertion_is_never_cached(monkeypatch, clock):
    fake = FakeCLI(profiles_out="chrome: stopped [extension]\n")
    monkeypatch.setattr(OC, "_run", fake)
    for _ in range(3):
        with pytest.raises(OC.OpenClawRefused, match="REFUSED_BROWSER_PROFILE_UNAVAILABLE"):
            OC.browser("snapshot", profile_name="muratclaw")
    assert fake.count()["browser profiles"] == 3
    # ... and once the profile exists again the next verb sees it at once.
    fake.profiles_out = PROFILES_OUT
    assert OC.browser("snapshot", profile_name="muratclaw")["rc"] == 0


def test_a_stopped_operator_profile_refuses_and_is_rechecked(monkeypatch, clock):
    fake = FakeCLI()
    monkeypatch.setattr(OC, "_run", fake)
    OC.browser("snapshot", profile_name="user", target_id="t20")
    fake.profiles_out = PROFILES_OUT.replace("user: running", "user: stopped")
    # Cached: the stop is not seen until something invalidates or the TTL runs.
    OC.browser("snapshot", profile_name="user", target_id="t20")
    assert fake.count()["browser profiles"] == 1
    OC.invalidate_profile_cache("user")
    with pytest.raises(OC.OpenClawRefused, match="REFUSED_BROWSER_PROFILE_UNAVAILABLE"):
        OC.browser("snapshot", profile_name="user", target_id="t20")
    assert "user" not in OC._PROFILE_CACHE


def test_a_missing_operator_tab_invalidates_and_the_next_verb_rechecks(monkeypatch, clock):
    fake = FakeCLI()
    monkeypatch.setattr(OC, "_run", fake)
    OC.browser("snapshot", profile_name="user", target_id="t20")
    OC.browser("snapshot", profile_name="user", target_id="t20")
    assert fake.count()["browser profiles"] == 1
    with pytest.raises(OC.OpenClawRefused, match="REFUSED_OPERATOR_TAB_MISSING"):
        OC.browser("snapshot", profile_name="user", target_id="t99")
    assert "user" not in OC._PROFILE_CACHE
    r = OC.browser("snapshot", profile_name="user", target_id="t20")
    assert r["profile_check"] == "checked"
    assert fake.count()["browser profiles"] == 2


def test_a_failed_verb_invalidates(monkeypatch, clock):
    fake = FakeCLI(verb_rc=1)
    monkeypatch.setattr(OC, "_run", fake)
    OC.browser("snapshot", profile_name="muratclaw")
    OC.browser("snapshot", profile_name="muratclaw")
    assert fake.count()["browser profiles"] == 2


def test_a_gateway_timeout_invalidates_every_profile(monkeypatch, clock):
    OC._PROFILE_CACHE["muratclaw"] = (clock["t"], (0, 0), {"ok": True})
    OC._PROFILE_CACHE["user"] = (clock["t"], (0, 0), {"ok": True})

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="openclaw", timeout=60)
    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(subprocess.TimeoutExpired):
        OC._run(["browser", "--browser-profile", "user", "--json", "tabs"])
    assert OC._PROFILE_CACHE == {}


def test_a_reattach_start_invalidates_that_profile(monkeypatch, clock):
    OC._PROFILE_CACHE["user"] = (clock["t"], (0, 0), {"ok": True})
    OC._PROFILE_CACHE["muratclaw"] = (clock["t"], (0, 0), {"ok": True})
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", ""))
    OC._run(["browser", "--browser-profile", "user", "start"], timeout=60)
    assert "user" not in OC._PROFILE_CACHE and "muratclaw" in OC._PROFILE_CACHE


def test_health_always_checks_fresh(monkeypatch, clock):
    fake = FakeCLI()
    monkeypatch.setattr(OC, "_run", fake)
    OC.assert_profile()
    OC.health()
    OC.health()
    # health(): one fresh assert_profile + one informative profiles() each.
    assert fake.count()["browser profiles"] == 1 + 2 * 2
    # The messaging-channel check runs once per health(), never per verb.
    OC.browser("snapshot", profile_name="muratclaw")
    assert fake.count()["channels list"] == 2


def test_read_text_carries_seconds_and_uses_the_cache(monkeypatch, clock):
    fake = FakeCLI()
    monkeypatch.setattr(OC, "_run", fake)
    a = OC.read_text("t1", profile_name="muratclaw")
    b = OC.read_text("t1", profile_name="muratclaw")
    assert (a["profile_check"], b["profile_check"]) == ("checked", "cached")
    assert isinstance(a["seconds"], float)
    assert fake.count()["browser profiles"] == 1


def test_the_cli_ledger_counts_seconds_per_subcommand(monkeypatch):
    OC.reset_cli_ledger()
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", ""))
    OC._run(["browser", "profiles"])
    OC._run(["browser", "--browser-profile", "user", "--json", "evaluate",
             "--target-id", "t1", "--fn", "() => 1"])
    OC._run(["browser", "--browser-profile", "user", "wait", "--time", "1000",
             "--target-id", "t1"])
    led = OC.cli_ledger()
    assert led["calls"] == 3
    assert set(led["by_cmd"]) == {"browser profiles", "browser evaluate", "browser wait"}
    assert all(v["calls"] == 1 and v["seconds"] >= 0 for v in led["by_cmd"].values())
    OC.reset_cli_ledger()
    assert OC.cli_ledger()["calls"] == 0


# -- the tab listing cache (2026-09-27) ---------------------------------------
# On the operator profile each tab verb listed `tabs` first (the host check)
# and navigate/click/press listed it again afterwards (the landed-URL check):
# 2-3 CLI round trips per action at ~15 s each that night.

WSJ_A = "https://www.wsj.com/finance/stocks/a-story-1a2b3c4d"


class OperatorCLI(FakeCLI):
    """`user` profile with live tab URLs: navigate moves the tab, evaluate reads
    it, and `nonce` is the Chrome MCP session every targetId carries."""

    def __init__(self, nonce: str = "aaa"):
        super().__init__()
        self.nonce = nonce
        self.urls = {"1": "https://www.wsj.com/news/heard-on-the-street",
                     "2": "https://www.barrons.com/market-data"}

    def handle(self, n: str) -> str:
        return f"chrome-mcp:{self.nonce}:{n}"

    def __call__(self, args, **kw):
        self.calls.append(list(args))
        verb = OC._cmd_key(args)
        if verb == "browser profiles":
            return subprocess.CompletedProcess(args, 0, self.profiles_out, "")
        if verb == "browser tabs":
            return subprocess.CompletedProcess(args, 0, json.dumps({"tabs": [
                {"tabId": f"t{20 + int(n)}", "targetId": self.handle(n), "url": u}
                for n, u in self.urls.items()]}), "")
        if verb == "browser status":
            return subprocess.CompletedProcess(args, 0, '{"running": true}', "")
        tid = args[args.index("--target-id") + 1] if "--target-id" in args else None
        n = str(tid).rsplit(":", 1)[-1] if tid else None
        if verb == "browser navigate":            # ... navigate <url> --target-id <tid>
            self.urls[n] = args[args.index("navigate") + 1]
        if verb == "browser evaluate":
            if "window.open" in args[-1]:
                self.urls[str(max(int(k) for k in self.urls) + 1)] = WSJ_A
                return subprocess.CompletedProcess(args, 0, "{}", "")
            return subprocess.CompletedProcess(args, 0, json.dumps(
                {"ok": True, "result": {"url": self.urls.get(n), "title": "T",
                                        "text": "body"}}), "")
        return subprocess.CompletedProcess(args, 0, "ok", "")


def _install(monkeypatch, fake) -> None:
    """Fake the PROCESS, not `_run`: the real `_run` then keeps the ledger."""
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: fake(list(cmd[1:]), **kw))


@pytest.fixture(autouse=True)
def _clean_tab_cache():
    def clear():
        OC.invalidate_tabs_cache()
        OC._TABS_NONCES.clear()
        OC._ATTACHED_CACHE.clear()
    clear()
    yield
    clear()


def _read_article_sequence(fake: OperatorCLI) -> None:
    """navigate, wait, snapshot, scrollintoview x2, evaluate (read_text)."""
    tab = fake.handle("1")
    OC.browser("navigate", WSJ_A, profile_name="user", target_id=tab)
    OC.browser("wait", "--time", "3500", profile_name="user", target_id=tab)
    OC.browser("snapshot", "--format", "ai", profile_name="user", target_id=tab)
    OC.browser("scrollintoview", "e12", profile_name="user", target_id=tab)
    OC.browser("scrollintoview", "e40", profile_name="user", target_id=tab)
    got = OC.read_text(tab, profile_name="user")
    assert got["url"] == WSJ_A and got["text"] == "body"


def test_a_read_article_sequence_costs_two_listings(monkeypatch, clock):
    fake = OperatorCLI()
    _install(monkeypatch, fake)
    OC.reset_cli_ledger()
    _read_article_sequence(fake)
    c = fake.count()
    led = OC.cli_ledger()
    print(f"\ntabs listings for one article: {c['browser tabs']}, URL re-reads "
          f"{led['cache']['url_rereads']}, CLI calls {led['calls']}")
    # 1 host check before navigate + 1 landed-URL re-read after it; the rest hit.
    assert c["browser tabs"] <= 2
    assert led["cache"]["url_rereads"] <= 2
    assert c["browser profiles"] == 1
    assert led["by_cmd"]["browser tabs"]["calls"] == c["browser tabs"]
    assert led["cache"]["tabs_hits"] >= 5


def test_without_the_tab_cache_the_same_sequence_lists_seven_times(monkeypatch, clock):
    """The 'before' number, measured the same way: a TTL of 0 is the old
    behaviour (HEAD 3d721f05 also listed a second time inside read_text: 8)."""
    fake = OperatorCLI()
    _install(monkeypatch, fake)
    monkeypatch.setattr(OC, "OPENCLAW_TABS_TTL_S", 0.0)
    _read_article_sequence(fake)
    print(f"\ntabs listings with no cache: {fake.count()['browser tabs']}")
    assert fake.count()["browser tabs"] >= 6


def test_scroll_press_does_not_reread_but_navigate_click_and_enter_do(monkeypatch, clock):
    fake = OperatorCLI()
    _install(monkeypatch, fake)
    tab = fake.handle("1")
    r = OC.browser("press", "PageDown", profile_name="user", target_id=tab)
    assert "tab_url_after" not in r
    OC.reset_cli_ledger()
    for verb, arg in (("click", "e7"), ("press", "Enter"), ("navigate", WSJ_A)):
        r = OC.browser(verb, arg, profile_name="user", target_id=tab)
        assert r["tab_url_after"] and r["left_allowed_hosts"] is False
    assert OC.cli_ledger()["cache"]["url_rereads"] == 3


def test_the_tab_cache_expires_after_its_ttl(monkeypatch, clock):
    fake = OperatorCLI()
    _install(monkeypatch, fake)
    tab = fake.handle("1")
    OC.browser("wait", "--time", "1", profile_name="user", target_id=tab)
    clock["t"] += OC.OPENCLAW_TABS_TTL_S - 1
    OC.browser("wait", "--time", "1", profile_name="user", target_id=tab)
    assert fake.count()["browser tabs"] == 1
    clock["t"] += 2
    OC.browser("wait", "--time", "1", profile_name="user", target_id=tab)
    assert fake.count()["browser tabs"] == 2


def test_a_session_nonce_change_relists_and_is_counted(monkeypatch, clock):
    fake = OperatorCLI(nonce="aaa")
    _install(monkeypatch, fake)
    OC.reset_cli_ledger()
    OC.browser("wait", "--time", "1", profile_name="user", target_id=fake.handle("1"))
    assert fake.count()["browser tabs"] == 1
    # The Chrome MCP session resets: every id is reissued under a new nonce.
    fake.nonce = "bbb"
    # A handle from the NEW session is not in the cached (aaa) listing: re-list.
    OC.browser("wait", "--time", "1", profile_name="user", target_id=fake.handle("1"))
    assert fake.count()["browser tabs"] == 2
    assert OC.cli_ledger()["cache"]["tabs_nonce_changes"] >= 1
    # An OLD handle refuses by name from a fresh listing, never from the cache.
    with pytest.raises(OC.OpenClawRefused, match=r"session 'aaa' is gone"):
        OC.browser("wait", "--time", "1", profile_name="user", target_id="chrome-mcp:aaa:1")
    assert "user" not in OC._TABS_CACHE


def test_a_refusal_naming_a_tab_invalidates_the_listing(monkeypatch, clock):
    fake = OperatorCLI()
    _install(monkeypatch, fake)
    OC.browser("wait", "--time", "1", profile_name="user", target_id=fake.handle("1"))
    assert "user" in OC._TABS_CACHE
    with pytest.raises(OC.OpenClawRefused, match="REFUSED_OPERATOR_TAB_MISSING"):
        OC.browser("wait", "--time", "1", profile_name="user", target_id=fake.handle("9"))
    assert "user" not in OC._TABS_CACHE
    n = fake.count()["browser tabs"]
    OC.browser("wait", "--time", "1", profile_name="user", target_id=fake.handle("1"))
    assert fake.count()["browser tabs"] == n + 1


def test_a_cached_off_host_url_is_rechecked_fresh_before_refusing(monkeypatch, clock):
    fake = OperatorCLI()
    _install(monkeypatch, fake)
    tab = fake.handle("1")
    fake.urls["1"] = "https://mail.google.com/mail/u/0"
    OC.tabs(profile_name="user")                       # cache: tab 1 off the hosts
    fake.urls["1"] = "https://www.wsj.com/news/markets"  # ... it came back
    OC.browser("wait", "--time", "1", profile_name="user", target_id=tab)   # no refusal
    fake.urls["1"] = "https://mail.google.com/mail/u/0"
    OC.invalidate_tabs_cache("user")
    with pytest.raises(OC.OpenClawRefused, match="REFUSED_OPERATOR_TAB_HOST"):
        OC.browser("wait", "--time", "1", profile_name="user", target_id=tab)
    assert "user" not in OC._TABS_CACHE


def test_close_and_start_invalidate_the_listing(monkeypatch, clock):
    fake = OperatorCLI()
    _install(monkeypatch, fake)
    OC.tabs(profile_name="user")
    assert "user" in OC._TABS_CACHE
    OC._OPENED_TABS.add(fake.handle("2"))
    try:
        OC.browser("close", profile_name="user", target_id=fake.handle("2"))
    finally:
        OC._OPENED_TABS.discard(fake.handle("2"))
    assert "user" not in OC._TABS_CACHE


def test_a_reattach_start_drops_the_listing(monkeypatch, clock):
    OC._TABS_CACHE["user"] = (clock["t"], OC._run, [{"tabId": "t1"}])
    OC._TABS_CACHE["muratclaw"] = (clock["t"], OC._run, [{"tabId": "t2"}])
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", ""))
    OC._run(["browser", "--browser-profile", "user", "start"], timeout=60)
    assert "user" not in OC._TABS_CACHE and "muratclaw" in OC._TABS_CACHE


def test_open_from_tab_lists_fresh_and_polls_fresh(monkeypatch, clock):
    fake = OperatorCLI()
    _install(monkeypatch, fake)
    OC.tabs(profile_name="user")          # a warm cache that cannot hold the new tab
    before = fake.count()["browser tabs"]
    out = OC.open_from_tab(fake.handle("1"), WSJ_A, sleep_fn=lambda s: None)
    try:
        assert out["new_tab"] == fake.handle("3")
        # the warm cache was NOT used for `before`, and the poll listed again
        assert fake.count()["browser tabs"] - before == 2
        # the post-open listing is what stays cached: a verb on the new tab hits it
        n = fake.count()["browser tabs"]
        OC.browser("wait", "--time", "1", profile_name="user", target_id=out["new_tab"])
        assert fake.count()["browser tabs"] == n
    finally:
        OC._OPENED_TABS.discard(fake.handle("3"))


def test_the_reader_footprint_carries_the_cli_ledger(monkeypatch, clock, tmp_path):
    """End to end through web_reader.Reader with the real client and a fake CLI:
    one article, and the footprint says what it cost."""
    from backend.services import web_reader as WR
    from datetime import datetime, timedelta, timezone
    fake = OperatorCLI()
    _install(monkeypatch, fake)
    now = {"t": datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc)}

    def sleep(s):
        now["t"] += timedelta(seconds=s)
    thr = WR.Throttle(tmp_path / "thr.log", now_fn=lambda: now["t"], sleep_fn=sleep, seed=3)
    rd = WR.Reader(profile="user", tab=fake.handle("1"), throttle=thr, lock=False)
    OC.reset_cli_ledger()
    rd._cli0 = rd.cli_ledger()
    art = rd.read_article(WSJ_A, store=False)
    assert art["url"] == WSJ_A
    c = fake.count()
    print(f"\nReader.read_article: {c['browser tabs']} tabs listings, "
          f"{c['browser profiles']} profiles, {sum(c.values())} CLI calls")
    assert c["browser tabs"] <= 2
    fp = WR.footprint_receipt(rd.log, reads=rd.reads, scrolled=rd.scrolled_reads,
                              write=False, cli_now=rd.cli_ledger(), cli_since=rd._cli0)
    assert fp["cli_calls"] == sum(c.values()) and fp["cli_scope"] == "since_reader_start"
    assert fp["cli_breakdown"]["tabs_listing"]["calls"] == c["browser tabs"]
    assert fp["cli_breakdown"]["profile_check"]["calls"] == c["browser profiles"]
    assert fp["cli_seconds_per_page"] is not None and fp["cli_cache"]["tabs_hits"] >= 3
    # Reader.close() writes the same fields
    out = rd.close(write_footprint=True)
    assert out["cli_calls"] == sum(c.values()) and "tabs_listing" in out["cli_breakdown"]


def test_a_stub_driver_without_a_ledger_says_so():
    from backend.services import web_reader as WR
    fp = WR.footprint_receipt([], write=False, cli_now={})
    assert fp["cli_calls"] is None and fp["cli_ledger"].startswith("UNAVAILABLE")
