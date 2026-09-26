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
