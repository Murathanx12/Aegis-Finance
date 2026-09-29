"""LANE O (2026-09-28): only MuratClaw, the owner's rules on both transports,
a supervisor that repairs its dependency, and a reader that checks its yield.

Test doubles only: no browser, no gateway, no CLI process, no network, no
PowerShell. Dates derive from today.

Murat, 2026-09-28: "configure to only murat claw like as if its controlling my
pc"; "dont use any payments, dont send any messages or emails without asking
me, use muratclaw mainly"; "reddit x and other socials are logged in too".
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import browser_policy as BP
from backend.services import gateway_repair as GR
from backend.services import muratclaw_instance as MI
from backend.services import openclaw_client as OC
from backend.services import openclaw_http as OH
from backend.services import web_reader as WR

TODAY = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
GUID = "48c6e3c7-ef15-4c1e-992e-e5f9d22b20b0"
DED = MI.user_data_dir()


# ───────────────────────── 1. the instance proof ────────────────────────────

def _cfg(**over) -> dict:
    profs = {"muratclaw": {"attachOnly": True, "cdpUrl": f"http://127.0.0.1:{MI.port()}"},
             "user": {"attachOnly": True, "cdpUrl": "http://127.0.0.1:9"},
             "chrome": {"attachOnly": True, "cdpUrl": "http://127.0.0.1:9"}}
    profs.update(over)
    return {"browser": {"defaultProfile": "muratclaw", "profiles": profs}}


def _probes(*, cfg=None, answers=True, ws_port=None, pid=4242, cmdline=None, name="chrome.exe",
            listener=None, targets=("AAAA",), counter=None) -> MI.Probes:
    c = counter if counter is not None else Counter()
    port = ws_port or MI.port()

    def http(url):
        c["http"] += 1
        if not answers:
            raise ConnectionRefusedError("down")
        if url.endswith("/json/version"):
            return {"webSocketDebuggerUrl": f"ws://127.0.0.1:{port}/devtools/browser/{GUID}"}
        return [{"id": t} for t in targets]

    def ws(url):
        c["ws"] += 1
        return pid

    def proc(p):
        c["proc"] += 1
        return {"pid": p, "name": name, "created": "today",
                "cmdline": cmdline if cmdline is not None else
                f'"chrome.exe" --user-data-dir="{DED}" --remote-debugging-port={MI.port()}'}

    return MI.Probes(http_json=http, ws_browser_pid=ws, process=proc,
                     listener=lambda p: listener if listener is not None else pid,
                     read_config=lambda: cfg if cfg is not None else _cfg(),
                     chrome_processes=lambda: [])


@pytest.fixture(autouse=True)
def _fresh_proof_cache():
    MI.reset_cache()
    yield
    MI.reset_cache()


def test_the_dedicated_chrome_is_proven_from_both_sides():
    c = Counter()
    out = MI.prove(target_id="AAAA", probes=_probes(counter=c))
    assert out["ok"] and out["pid"] == 4242 and out["guid"] == GUID
    assert out["tab_in_instance"] and out["pid_proof"] == "checked"
    assert c["ws"] == 1 and c["proc"] == 1          # Chrome's word AND the OS's word


def test_the_os_side_proof_is_cached_per_browser_guid_and_the_rest_is_not():
    c = Counter()
    pr = _probes(counter=c)
    MI.prove(probes=pr)
    out = MI.prove(target_id="AAAA", probes=pr)
    assert out["pid_proof"] == "cached" and c["ws"] == 1 and c["proc"] == 1
    assert c["http"] == 3                           # version, version, list: every call


@pytest.mark.parametrize("kw,code", [
    ({"answers": False}, "REFUSED_INSTANCE_DOWN"),
    ({"ws_port": 9222}, "REFUSED_INSTANCE_ENDPOINT"),
    ({"cmdline": '"chrome.exe"'}, "REFUSED_NOT_MURATCLAW_INSTANCE"),     # the MAIN Chrome
    ({"cmdline": '"chrome.exe" --user-data-dir="C:\\\\Other" --remote-debugging-port=18802'},
     "REFUSED_NOT_MURATCLAW_INSTANCE"),
    ({"name": "node.exe"}, "REFUSED_INSTANCE_PROCESS"),
    ({"listener": 1111}, "REFUSED_INSTANCE_LISTENER"),
    ({"targets": ("BBBB",)}, "REFUSED_TAB_NOT_IN_INSTANCE"),
])
def test_every_failed_step_refuses_by_name(kw, code):
    with pytest.raises(MI.InstanceNotProven, match=code):
        MI.prove(target_id="AAAA", probes=_probes(**kw))


@pytest.mark.parametrize("cfg,why", [
    (_cfg(user=None), "profiles.user"),
    ({"browser": {"defaultProfile": "muratclaw", "profiles": {
        "muratclaw": {"attachOnly": True, "cdpUrl": f"http://127.0.0.1:{MI.port()}"},
        "chrome": {"attachOnly": True, "cdpUrl": "http://127.0.0.1:9"}}}}, "profiles.user"),
    (_cfg(user={"driver": "existing-session", "attachOnly": True}), "existing-session"),
    (_cfg(muratclaw={"cdpPort": 18801}), "cdpUrl"),
    (_cfg(chrome={"attachOnly": True, "cdpUrl": f"http://127.0.0.1:{MI.port()}"}),
     "also points at the dedicated endpoint"),
])
def test_a_config_that_could_reach_the_main_chrome_refuses(cfg, why):
    cfg = json.loads(json.dumps(cfg))
    cfg["browser"]["profiles"] = {k: v for k, v in cfg["browser"]["profiles"].items()
                                  if v is not None}
    assert any(why in p for p in MI.config_problems(cfg))
    with pytest.raises(MI.InstanceNotProven, match="REFUSED_INSTANCE_CONFIG"):
        MI.prove(probes=_probes(cfg=cfg))


def test_the_live_config_shape_of_2026_09_28_is_confined():
    assert MI.config_problems(_cfg()) == []


def test_the_probe_talks_to_loopback_only():
    with pytest.raises(MI.InstanceNotProven, match="REFUSED_NOT_LOOPBACK"):
        MI._http_json("http://10.0.0.5:18802/json/version")


# ───────────────────────── 2. start it, check it ────────────────────────────

def _status_probes(procs, answers):
    return MI.Probes(http_json=(lambda u: {"Browser": "Chrome"}) if answers else
                     (lambda u: (_ for _ in ()).throw(ConnectionRefusedError())),
                     chrome_processes=lambda: procs)


def test_status_separates_the_dedicated_chrome_from_the_main_one():
    procs = [{"pid": 1, "cmdline": '"chrome.exe"', "created": "a"},
             {"pid": 2, "cmdline": f'"chrome.exe" --user-data-dir="{DED}" '
                                   f'--remote-debugging-port={MI.port()}', "created": "b"}]
    st = MI.status(probes=_status_probes(procs, True))
    assert st["running_with_port"] and [d["pid"] for d in st["dedicated"]] == [2]
    assert st["main_chrome"] == [{"pid": 1, "created": "a"}]


def test_launch_is_a_noop_when_running_and_refuses_when_the_folder_is_held_without_port():
    ok = [{"pid": 2, "cmdline": f'--user-data-dir="{DED}" --remote-debugging-port={MI.port()}',
           "created": "b"}]
    boom = lambda *a, **k: pytest.fail("must not launch")   # noqa: E731
    assert MI.launch_attach(probes=_status_probes(ok, True), popen=boom)["launched"] is False
    held = [{"pid": 3, "cmdline": f'--user-data-dir="{DED}" --no-first-run', "created": "c"}]
    with pytest.raises(MI.InstanceNotProven, match="REFUSED_INSTANCE_NO_PORT"):
        MI.launch_attach(probes=_status_probes(held, False), popen=boom)


def test_launch_starts_the_attach_argv_and_waits_for_the_port():
    seen = {}
    state = {"up": False}

    def popen(argv, **kw):
        seen["argv"], seen["shell"] = argv, kw.get("shell")
        state["up"] = True
        return type("P", (), {"pid": 77})()

    def http(u):
        if not state["up"]:
            raise ConnectionRefusedError()
        return {"Browser": "Chrome"}
    pr = MI.Probes(http_json=http, chrome_processes=lambda: [])
    out = MI.launch_attach(probes=pr, popen=popen, sleep_fn=lambda s: None)
    assert out["launched"] and seen["shell"] is False
    assert f"--user-data-dir={DED}" in seen["argv"]
    assert f"--remote-debugging-port={MI.port()}" in seen["argv"]
    assert "--remote-debugging-address=127.0.0.1" in seen["argv"]


# ─────────────── 3. the owner's rules (pure), both snapshot shapes ───────────

SNAP_INLINE = ('- link "Nvidia rallies as chip demand grows" [ref=e5] '
               '[url=https://www.wsj.com/tech/nvidia-1a2b3c4d]\n'
               '- button "Murathan Abdullaev" [ref=e6]\n'
               '- link "Subscribe for $1" [ref=e7] [url=https://www.wsj.com/subscribe]\n'
               '- link "Share this story on X" [ref=e8] [url=https://www.wsj.com/a-1]\n'
               '- link "Store" [ref=e9] [url=https://store.wsj.com/shop]\n')
SNAP_APPENDIX = ('- link "Nvidia rallies as chip demand grows" [ref=e5]\n'
                 'Links:\n1. Nvidia rallies as chip demand grows -> '
                 'https://www.wsj.com/tech/nvidia-1a2b3c4d\n')


def test_one_parser_reads_both_snapshot_shapes():
    for snap in (SNAP_INLINE, SNAP_APPENDIX):
        links = BP.parse_snapshot(snap)["links"]
        assert links[0]["url"] == "https://www.wsj.com/tech/nvidia-1a2b3c4d"
        assert WR.parse_snapshot(snap) == BP.parse_snapshot(snap)
    # the 2026-09-28 zero: the reader's link chooser finds the inline links
    got = WR.select_links(SNAP_INLINE, r"wsj\.com/tech/")
    assert [g["ref"] for g in got] == ["e5"]


@pytest.mark.parametrize("ref,code", [
    ("e6", "REFUSED_CLICK_ROLE"), ("e7", "REFUSED_PAYMENT_ACTION"),
    ("e8", "REFUSED_MESSAGE_ACTION"), ("e9", "REFUSED_PAYMENT_URL"),
    ("e99", "REFUSED_CLICK_UNSEEN_REF")])
def test_a_click_lands_only_on_a_seen_harmless_link(ref, code):
    kw = dict(tab_url="https://www.wsj.com/", social_hosts=("x.com",),
              allowed_hosts=("wsj.com",))
    assert BP.click_refusal(SNAP_INLINE, "e5", **kw) is None
    why = BP.click_refusal(SNAP_INLINE, ref, **kw)     # e9: "Store" -> store.wsj.com
    assert why and why.startswith(code), why


@pytest.mark.parametrize("url,code", [
    ("https://www.wsj.com/checkout/step1", "REFUSED_PAYMENT_URL"),
    ("https://store.barrons.com/shop/us", "REFUSED_PAYMENT_URL"),
    ("https://customercenter.wsj.com/billing", "REFUSED_PAYMENT_URL"),
    ("https://www.marketwatch.com/subscribe?x=1", "REFUSED_PAYMENT_URL"),
    ("https://mail.google.com/mail/u/0", "REFUSED_MESSAGE_URL"),
    ("https://www.reddit.com/message/compose", "REFUSED_MESSAGE_URL"),
    ("https://x.com/messages", "REFUSED_MESSAGE_URL"),
])
def test_payment_and_message_addresses_refuse(url, code):
    assert (BP.url_refusal(url) or "").startswith(code)


def test_an_article_slug_with_a_money_word_is_not_a_payment_address():
    assert BP.url_refusal("https://www.wsj.com/finance/stocks/stocks-to-buy-now-1a2b3c4d") is None
    assert BP.url_refusal("https://www.barrons.com/articles/share-buyback-order-flow-5e6f") is None


def test_social_write_paths_refuse_and_search_urls_do_not():
    soc = ("x.com", "reddit.com", "stocktwits.com")
    assert BP.social_url_refusal("https://x.com/intent/tweet?text=hi", soc)
    assert BP.social_url_refusal("https://www.reddit.com/r/stocks/submit", soc)
    for h in soc:
        assert BP.social_url_refusal(WR.social_url(h, "NVDA"), soc) is None


def test_press_is_scroll_keys_only():
    assert BP.press_refusal(["PageDown"]) is None
    for k in (["Enter"], ["Space"], ["a"], ["Tab"], []):
        assert (BP.press_refusal(k) or "").startswith("REFUSED_PRESS_KEY")


# ───────────── 4. a fake browser, driven over BOTH transports ────────────────

WSJ_A = "https://www.wsj.com/tech/nvidia-1a2b3c4d"


class FakeBrowser:
    """One dedicated Chrome: tabs by raw CDP id; counts ACTION calls per verb."""

    def __init__(self):
        self.tabs = {"A" * 32: "https://www.wsj.com/", "C" * 32: "https://x.com/search?q=%24NVDA"}
        self.actions: list[str] = []

    def listing(self):
        return [{"targetId": k, "tabId": f"t{i}", "url": u}
                for i, (k, u) in enumerate(self.tabs.items(), 1)]

    def do(self, verb, tid=None, arg=None):
        self.actions.append(verb)
        if verb == "open":
            nid = "B" * 32
            self.tabs[nid] = arg
            return {"targetId": nid, "url": arg}
        if verb == "navigate":
            self.tabs[tid] = arg
            return {"url": arg, "targetId": tid}
        if verb == "close":
            self.tabs.pop(tid, None)
            return {"ok": True}
        if verb == "snapshot":
            return SNAP_INLINE
        if verb == "evaluate":
            return {"targetId": tid, "result": {"url": self.tabs.get(tid), "title": "T",
                                                "text": "A story\n" + "words " * 50}}
        return {"ok": True}


def _cli_adapter(fb: FakeBrowser):
    def run(cmd, **kw):
        args = list(cmd[len(OC._resolve_cli()["prefix"]):])
        key = OC._cmd_key(args)
        ok = lambda out: subprocess.CompletedProcess(cmd, 0, out, "")   # noqa: E731
        tid = args[args.index("--target-id") + 1] if "--target-id" in args else None
        if key == "browser profiles":
            return ok("muratclaw: running [default]\n  port: 18802\nuser: stopped\n")
        if key == "browser tabs":
            return ok(json.dumps({"tabs": fb.listing()}))
        if key == "browser status":
            return ok(json.dumps({"running": True, "cdpUrl": "http://127.0.0.1:18802"}))
        verb = key.split(" ", 1)[1]
        if verb == "open":
            return ok(json.dumps(fb.do("open", arg=args[-1])))
        if verb == "navigate":
            r = fb.do("navigate", tid, args[args.index("navigate") + 1])
            return ok(f"navigated to {r['url']}")
        if verb == "close":
            return ok(json.dumps(fb.do("close", args[-1])))
        if verb == "snapshot":
            return ok(fb.do("snapshot", tid))
        if verb == "evaluate":
            return ok(json.dumps(fb.do("evaluate", tid)))
        return ok(json.dumps(fb.do(verb, tid)))
    return run


class _Resp:
    def __init__(self, body, code=200):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


class FakeSession:
    """`requests.Session` stand-in for `POST /tools/invoke`."""

    def __init__(self, fb: FakeBrowser):
        self.fb, self.posts = fb, []

    def post(self, url, json=None, headers=None, timeout=None):     # noqa: A002
        a = json["args"]
        self.posts.append(dict(a))
        act, tid = a["action"], a.get("targetId")
        det: dict
        if act == "tabs":
            det = {"tabs": self.fb.listing(), "running": True}
        elif act == "status":
            det = {"running": True, "cdpUrl": "http://127.0.0.1:18802"}
        elif act == "open":
            det = self.fb.do("open", arg=a["targetUrl"])
        elif act == "navigate":
            det = self.fb.do("navigate", tid, a["targetUrl"])
        elif act == "close":
            det = self.fb.do("close", tid)
        elif act == "snapshot":
            snap = self.fb.do("snapshot", tid)
            return _Resp({"ok": True, "result": {"content": [{"type": "text", "text": (
                "SECURITY NOTICE\n<<<EXTERNAL_UNTRUSTED_CONTENT id=\"x\">>>\nSource: Browser\n"
                f"---\n{snap}\n<<<END_EXTERNAL_UNTRUSTED_CONTENT id=\"x\">>>")}],
                "details": {"ok": True, "truncated": False}}})
        elif act == "act":
            det = self.fb.do({"evaluate": "evaluate", "press": "press", "click": "click",
                              "scrollIntoView": "scrollintoview", "wait": "wait"}[a["kind"]],
                             tid)
        else:
            det = {"ok": True}
        return _Resp({"ok": True, "result": {"content": [{"type": "text", "text": "x"}],
                                             "details": det}})


@pytest.fixture
def both(monkeypatch):
    """Yields a function `use(transport) -> FakeBrowser` wiring the REAL client
    to a fake CLI process or a fake HTTP session, with the prover faked."""
    proofs: list = []
    monkeypatch.setattr(OC, "_PROVER", lambda **k: proofs.append(k) or {"ok": True})
    monkeypatch.setattr(OC, "attached_to", lambda **k: {"pid": 1})
    monkeypatch.setattr(OC, "_topology_lock", lambda: __import__("contextlib").nullcontext())

    def use(transport: str) -> FakeBrowser:
        fb = FakeBrowser()
        OC.invalidate_profile_cache()
        OC._SNAPSHOTS.clear()
        OC.reset_cli_ledger()
        proofs.clear()
        monkeypatch.setenv(OC.TRANSPORT_ENV, transport)
        monkeypatch.setattr(subprocess, "run", _cli_adapter(fb))
        fb.session = FakeSession(fb)
        monkeypatch.setattr(OC, "_HTTP", OH.HttpTransport(session=fb.session,
                                                          token_fn=lambda: "tok"))
        return fb
    use.proofs = proofs
    yield use
    OC._OPENED_TABS.discard("B" * 32)
    OC.invalidate_profile_cache()
    OC._SNAPSHOTS.clear()


def _one_read(fb: FakeBrowser) -> None:
    """open -> snapshot -> click a seen link -> scroll -> read -> close."""
    op = OC.browser("open", url="https://www.wsj.com/")
    tid = op["new_tab"]
    OC.browser("snapshot", "--format", "ai", "--urls", target_id=tid)
    OC.browser("click", "e5", target_id=tid)
    OC.browser("press", "PageDown", target_id=tid)
    got = OC.read_text(tid)
    assert got["text"].startswith("A story")
    OC.browser("close", target_id=tid)


REQUIRED_GUARDS = {"verb_allow", "denied_domains", "policy_url", "host_allow", "instance",
                   "host_before", "host_after", "policy_press", "policy_click", "own_tab"}


def test_every_guard_binds_on_the_http_path_exactly_as_on_the_cli(both):
    counts = {}
    for tr in ("cli", "http"):
        fb = both(tr)
        _one_read(fb)
        led = OC.cli_ledger()
        counts[tr] = dict(led["guards"])
        routed = led.get("by_transport") or {}
        # the actions went where the transport says (profiles is CLI on both)
        assert set(routed) == ({"cli"} if tr == "cli" else {"cli", "http"})
        if tr == "http":
            assert set(routed["cli"]) == {"browser profiles"}
            assert fb.session.posts, "the HTTP route was not used"
        assert fb.actions == ["open", "snapshot", "click", "press", "evaluate", "close"]
    missing = REQUIRED_GUARDS - set(counts["http"])
    assert not missing, f"the HTTP path skipped {missing}"
    assert counts["cli"] == counts["http"], (counts["cli"], counts["http"])
    # the instance was proven before EVERY action (open is proven twice: before
    # the tab exists and after, with its id)
    assert counts["http"]["instance"] >= len(["open", "open2", "snapshot", "click", "press",
                                              "evaluate", "close"])


@pytest.mark.parametrize("transport", ["cli", "http"])
def test_a_failed_instance_proof_refuses_before_any_action(both, monkeypatch, transport):
    fb = both(transport)

    def not_proven(**k):
        raise MI.InstanceNotProven("REFUSED_NOT_MURATCLAW_INSTANCE: the port is someone else's")
    monkeypatch.setattr(OC, "_PROVER", not_proven)
    for call in (lambda: OC.browser("open", url="https://www.wsj.com/"),
                 lambda: OC.browser("snapshot", target_id="A" * 32),
                 lambda: OC.browser("navigate", WSJ_A, target_id="A" * 32),
                 lambda: OC.read_text("A" * 32)):
        with pytest.raises(OC.OpenClawRefused, match="REFUSED_NOT_MURATCLAW_INSTANCE"):
            call()
    assert fb.actions == []


@pytest.mark.parametrize("transport", ["cli", "http"])
def test_the_social_hosts_are_read_only_on_both_transports(both, transport):
    fb = both(transport)
    x_tab = "C" * 32
    OC.browser("snapshot", target_id=x_tab)                 # reading is allowed
    for call, code in (
            (lambda: OC.browser("click", "e5", target_id=x_tab), "REFUSED_SOCIAL_CLICK"),
            (lambda: OC.browser("press", "Enter", target_id=x_tab), "REFUSED_PRESS_KEY"),
            (lambda: OC.browser("type", "e1", "hello", target_id=x_tab), "REFUSED_OPERATOR_VERB"),
            (lambda: OC.browser("fill", "e1", target_id=x_tab), "REFUSED_OPERATOR_VERB"),
            (lambda: OC.browser("navigate", "https://x.com/intent/tweet?text=hi",
                                target_id=x_tab), "REFUSED_SOCIAL_WRITE_URL"),
            (lambda: OC.browser("navigate", "https://www.reddit.com/r/stocks/submit",
                                target_id=x_tab), "REFUSED_SOCIAL_WRITE_URL"),
            (lambda: OC.browser("open", url="https://x.com/messages"), "REFUSED_MESSAGE_URL")):
        with pytest.raises(OC.OpenClawRefused, match=code):
            call()
    # a search is a NAVIGATION to a search URL, and that passes
    OC.browser("navigate", WR.social_url("reddit.com", "NVDA"), target_id=x_tab)
    assert fb.actions == ["snapshot", "navigate"]


@pytest.mark.parametrize("transport", ["cli", "http"])
def test_payments_and_messages_refuse_on_both_transports(both, transport):
    fb = both(transport)
    tab = "A" * 32
    OC.browser("snapshot", target_id=tab)
    for call, code in (
            (lambda: OC.browser("click", "e7", target_id=tab), "REFUSED_PAYMENT_ACTION"),
            (lambda: OC.browser("click", "e8", target_id=tab), "REFUSED_MESSAGE_ACTION"),
            (lambda: OC.browser("click", "e6", target_id=tab), "REFUSED_CLICK_ROLE"),
            (lambda: OC.browser("navigate", "https://www.wsj.com/checkout/a",
                                target_id=tab), "REFUSED_PAYMENT_URL"),
            (lambda: OC.browser("open", url="https://mail.google.com/"), "REFUSED_MESSAGE_URL"),
            (lambda: OC.browser("open", url="https://app.alpaca.markets/"), "REFUSED_DOMAIN")):
        with pytest.raises(OC.OpenClawRefused, match=code):
            call()
    assert fb.actions == ["snapshot"]


def test_a_click_after_the_page_changed_needs_a_new_snapshot(both):
    both("cli")
    tab = "A" * 32
    OC.browser("snapshot", target_id=tab)
    OC.browser("navigate", WSJ_A, target_id=tab)        # the refs of the old page are gone
    with pytest.raises(OC.OpenClawRefused, match="REFUSED_CLICK_UNSEEN_REF"):
        OC.browser("click", "e5", target_id=tab)


@pytest.mark.parametrize("name", ["user", "chrome"])
def test_the_main_chrome_profiles_refuse_by_name_everywhere(monkeypatch, name):
    monkeypatch.setattr(OC, "_run", lambda *a, **k: pytest.fail("must not reach OpenClaw"))
    for call in (lambda: OC.browser("snapshot", profile_name=name, target_id="t1"),
                 lambda: OC.tabs(profile_name=name), lambda: OC.read_text("t1", profile_name=name),
                 lambda: OC.open_tab("https://www.wsj.com/", profile_name=name),
                 lambda: OC.own_blank_tab("blank", "t1", profile_name=name)):
        with pytest.raises(OC.OpenClawRefused, match="REFUSED_MAIN_CHROME_PROFILE"):
            call()
    monkeypatch.setenv(OC.PROFILE_ENV, name)
    with pytest.raises(OC.OpenClawRefused, match="REFUSED_MAIN_CHROME_PROFILE"):
        OC.browser("snapshot", target_id="t1")


def test_the_transport_defaults_to_the_cli_and_an_unknown_value_is_the_cli(monkeypatch):
    monkeypatch.delenv(OC.TRANSPORT_ENV, raising=False)
    assert OC.browser_transport() == "cli"
    monkeypatch.setenv(OC.TRANSPORT_ENV, "carrier-pigeon")
    assert OC.browser_transport() == "cli"
    monkeypatch.setenv(OC.TRANSPORT_ENV, "http")
    assert OC.browser_transport() == "http"


def test_a_truncated_http_snapshot_is_reread_on_the_cli(both, monkeypatch):
    fb = both("http")
    real_post = fb.session.post

    def post(url, json=None, **kw):                                   # noqa: A002
        if json["args"]["action"] == "snapshot":
            return _Resp({"ok": True, "result": {"content": [{"type": "text", "text": "part"}],
                                                 "details": {"truncated": True}}})
        return real_post(url, json=json, **kw)
    fb.session.post = post
    out = OC.browser("snapshot", target_id="A" * 32)
    assert out["stdout"] == SNAP_INLINE.strip() and out["cli_route"] != "http"
    assert OC.cli_ledger()["http_truncated_fallbacks"] == 1


# ───────────────────────── 5. the HTTP transport itself ──────────────────────

@pytest.mark.parametrize("argv,expect", [
    (["browser", "--browser-profile", "muratclaw", "--json", "tabs"],
     {"action": "tabs", "profile": "muratclaw"}),
    (["browser", "--browser-profile", "m", "navigate", WSJ_A, "--target-id", "T"],
     {"action": "navigate", "targetUrl": WSJ_A, "targetId": "T", "profile": "m",
      "timeoutMs": 75000}),
    (["browser", "--browser-profile", "m", "press", "PageDown", "--target-id", "T"],
     {"action": "act", "kind": "press", "key": "PageDown", "targetId": "T", "profile": "m"}),
    (["browser", "--browser-profile", "m", "--json", "evaluate", "--target-id", "T", "--fn", "F"],
     {"action": "act", "kind": "evaluate", "fn": "F", "targetId": "T", "profile": "m"}),
    (["browser", "--browser-profile", "m", "wait", "--time", "4000", "--target-id", "T"],
     {"action": "act", "kind": "wait", "timeMs": 4000, "targetId": "T", "profile": "m"}),
])
def test_argv_maps_to_tool_args(argv, expect):
    assert OH.tool_args(OH.parse_argv(argv)) == expect


def test_profiles_start_stop_and_gateway_stay_on_the_cli():
    t = OH.HttpTransport(session=object(), token_fn=lambda: "tok")
    for argv in (["browser", "profiles"], ["browser", "--browser-profile", "m", "start"],
                 ["gateway", "restart"], ["agent", "--message-file", "x"]):
        assert not t.serves(argv) and t.run(argv) is None


def test_the_token_never_reaches_an_error_message():
    class Boom:
        def post(self, *a, **k):
            raise ConnectionError("refused with Bearer sekret-token-123")
    r = OH.HttpTransport(session=Boom(), token_fn=lambda: "sekret-token-123").run(
        ["browser", "--browser-profile", "m", "--json", "tabs"])
    assert r.returncode == 1 and "sekret" not in r.stderr and "ECONNREFUSED" in r.stderr
    assert WR.is_gateway_down(r.stderr)


def test_an_http_timeout_is_a_timeout_like_the_cli():
    class Slow:
        def post(self, *a, **k):
            raise type("ReadTimeout", (Exception,), {})("slow")
    with pytest.raises(subprocess.TimeoutExpired):
        OH.HttpTransport(session=Slow(), token_fn=lambda: "t").run(
            ["browser", "--browser-profile", "m", "--json", "tabs"])


# ───────────────────────── 6. the supervisor's repair ────────────────────────

@pytest.mark.parametrize("text,kind", [
    ("REFUSED: ReaderRefused: REFUSED_GATEWAY_DOWN: GATEWAY_NEEDS_RESTART: `start` answered "
     "'Chrome MCP subprocess tree cleanup could not be verified.'", "GATEWAY_STUCK"),
    ("OpenClawRefused: gateway timeout after 45000ms", "GATEWAY_DOWN"),
    ("gateway unreachable: ECONNREFUSED", "GATEWAY_DOWN"),
    ("REFUSED_INSTANCE_DOWN: the dedicated Chrome is not running", "CHROME_DOWN"),
    ("REFUSED_NOT_MURATCLAW_INSTANCE: browser pid 1", "NOT_MURATCLAW"),
    ("REFUSED_ZERO_YIELD_LANE: ['wsj:x']", "POLICY_STOP"),
    ("REFUSED_NO_HANDOFF: the archive reads need --handoff", "POLICY_STOP"),
    ("Traceback (most recent call last):\n  KeyError: 'x'", "READER_CRASH"),
])
def test_the_exit_is_classified(text, kind):
    assert GR.classify_exit(text)["kind"] == kind


def test_the_budget_is_three_an_hour_with_doubling_backoff():
    b = GR.RepairBudget(per_hour=3, backoff_s=60.0)
    t = 1000.0
    assert b.allow(t) == (True, 0.0)
    b.spend(t)
    assert b.allow(t + 59)[0] is False and b.allow(t + 60)[0] is True
    b.spend(t + 60)
    assert b.allow(t + 60 + 119)[0] is False and b.allow(t + 60 + 120)[0] is True
    b.spend(t + 180)
    ok, wait = b.allow(t + 400)
    assert ok is False and wait == pytest.approx(3600 - 400)       # 3 in the hour
    assert b.allow(t + 3601)[0] is True          # the first repair has aged out


class World:
    """A fake machine for the repair ladder."""

    def __init__(self, *, gw=False, chrome=True, latched=False, free=8.0, procs=(),
                 start_works=True, stop_clears=False, restart_works=True):
        self.gw, self.chrome, self.latched, self.free = gw, chrome, latched, free
        self.procs, self.start_works, self.stop_clears = list(procs), start_works, stop_clears
        self.restart_works = restart_works
        self.cmds: list[list[str]] = []
        self.t = 0.0

    def deps(self) -> GR.Deps:
        return GR.Deps(
            port_open=lambda h, p: self.gw,
            openclaw=self.openclaw,
            browser_status=lambda prof: ({"ok": False, "detail": "Chrome MCP subprocess tree "
                                          "cleanup could not be verified."} if self.latched
                                         else {"ok": True, "running": self.chrome}),
            chrome_status=lambda: {"running_with_port": self.chrome},
            chrome_launch=self.launch, orphan_mcp=lambda: [], kill_pid=lambda p: True,
            gateway_procs=lambda: self.procs, free_gb=lambda: self.free,
            sleep=self.sleep, clock=lambda: self.t, reclaim=lambda need: {"ok": False})

    def sleep(self, s):
        self.t += s

    def launch(self):
        self.chrome = True
        return {"launched": True}

    def openclaw(self, args, timeout=None):
        self.cmds.append(list(args))
        if args[:2] == ["gateway", "start"] and self.start_works:
            self.gw = True
        if args[:2] == ["gateway", "restart"] and self.restart_works:
            self.gw, self.latched = True, False
        if args[-1] == "stop" and self.stop_clears:
            self.latched = False
        return {"rc": 0}


def test_a_killed_gateway_is_started_once_and_nothing_else():
    w = World(gw=False)
    r = GR.repair("GATEWAY_DOWN", deps=w.deps())
    assert r["healthy"] and r["cleared_by"] == "gateway_start"
    assert w.cmds == [["gateway", "start"]]


def test_under_the_memory_floor_the_repair_reclaims_then_proceeds():
    """2026-09-29: the floor used to END the repair -- a gate the repair could
    never clear while a browser held the memory. Now it reclaims what the reader
    owns first and then starts the gateway anyway (never waits forever)."""
    w = World(gw=False, free=0.6)
    reclaims: list[float] = []

    def reclaim(need):
        reclaims.append(need)
        w.free = 1.9                          # the recycle freed memory
        return {"ok": True}
    d = w.deps()
    d.reclaim = reclaim
    r = GR.repair("GATEWAY_DOWN", deps=d)
    names = [s["step"] for s in r["steps"]]
    assert reclaims == [GR.min_free_gb()]
    assert names[0] == "reclaim_memory" and "gateway_start" in names
    assert r["healthy"] and r["cleared_by"] == "gateway_start"


def test_a_reclaim_that_cannot_clear_the_floor_still_does_not_block_the_repair():
    w = World(gw=False, free=0.6)
    d = w.deps()
    d.reclaim = lambda need: {"ok": False}
    r = GR.repair("GATEWAY_DOWN", deps=d)
    assert ["gateway", "start"] in w.cmds and r["healthy"]
    assert r["stopped_because"] is None


def test_a_gateway_already_starting_is_waited_for_never_doubled():
    """The 2026-09-28 14:30 kill test: `restart` after a slow `start` left two
    gateway trees fighting for one port."""
    w = World(gw=False, procs=[{"pid": 1}])
    r = GR.repair("GATEWAY_DOWN", deps=w.deps())
    assert not r["healthy"] and "GATEWAY_STARTING_SLOW" in r["stopped_because"]
    assert not any(c[:2] in (["gateway", "start"], ["gateway", "restart"]) for c in w.cmds)


def test_a_start_that_does_not_bind_is_not_followed_by_a_restart():
    w = World(gw=False, start_works=False)
    r = GR.repair("GATEWAY_DOWN", deps=w.deps())
    assert not r["healthy"] and ["gateway", "restart"] not in w.cmds
    assert "did not bind its port" in r["stopped_because"]


def test_a_latched_gateway_tries_the_light_resets_before_a_restart():
    w = World(gw=True, latched=True)
    r = GR.repair("GATEWAY_STUCK", deps=w.deps())
    names = [s["step"] for s in r["steps"]]
    assert names[:3] == ["browser_stop", "kill_orphan_mcp_by_pid", "gateway_restart"]
    assert r["healthy"] and r["cleared_by"] == "gateway_restart"
    w2 = World(gw=True, latched=True, stop_clears=True)
    assert GR.repair("GATEWAY_STUCK", deps=w2.deps())["cleared_by"] == "browser_stop"


def test_a_closed_dedicated_chrome_is_launched_and_not_mistaken_for_the_gateway():
    w = World(gw=True, chrome=False)
    r = GR.repair("CHROME_DOWN", deps=w.deps())
    assert r["healthy"] and r["cleared_by"] == "launch_dedicated_chrome" and w.cmds == []


def test_not_muratclaw_is_never_auto_repaired():
    w = World(gw=True, chrome=True)
    r = GR.repair("NOT_MURATCLAW", deps=w.deps())
    assert r["steps"] == [] and not r["healthy"] and "never auto-repaired" in r["refused"]


def test_the_supervisor_never_relaunches_while_the_dependency_is_down():
    from scripts import night_reader_supervisor as S
    down, up = {"healthy": False}, {"healthy": True}
    assert S.decide(kind="GATEWAY_STUCK", probe=down, restarts=3, since_launch_s=9999,
                    budget_ok=True) == "repair"
    assert S.decide(kind="GATEWAY_STUCK", probe=down, restarts=3, since_launch_s=9999,
                    budget_ok=False) == "wait_dep"
    # even a "crash" is not relaunched into a dead gateway
    assert S.decide(kind="READER_CRASH", probe=down, restarts=0, since_launch_s=None,
                    budget_ok=False) == "wait_dep"
    assert S.decide(kind="NOT_MURATCLAW", probe=up, restarts=0, since_launch_s=None,
                    budget_ok=True) == "stop"
    assert S.decide(kind="POLICY_STOP", probe=up, restarts=0, since_launch_s=None,
                    budget_ok=True) == "stop"
    assert S.decide(kind="READER_CRASH", probe=up, restarts=2, since_launch_s=60,
                    budget_ok=True) == "wait"                     # backoff 120 s
    assert S.decide(kind="READER_CRASH", probe=up, restarts=2, since_launch_s=121,
                    budget_ok=True) == "relaunch"
    assert [S.reader_backoff_s(n) for n in (1, 2, 3, 10)] == [60, 120, 240, 1800]


def test_last_nights_retry_storm_cannot_happen_again():
    """20 relaunches in 100 minutes against a jammed gateway (2026-09-28 02:17-
    04:05): replay 100 minutes of 5-minute ticks with the gateway latched and
    count relaunches (0) and repairs (<= 3 per hour)."""
    from scripts import night_reader_supervisor as S
    b = GR.RepairBudget(per_hour=3, backoff_s=60.0)
    relaunches, repairs = 0, []
    for tick in range(20):
        now = tick * 300.0
        ok, _ = b.allow(now)
        act = S.decide(kind="GATEWAY_STUCK", probe={"healthy": False}, restarts=0,
                       since_launch_s=None, budget_ok=ok)
        if act == "repair":
            b.spend(now)
            repairs.append(now)
        relaunches += act == "relaunch"
    assert relaunches == 0 and repairs[:3] == [0.0, 300.0, 600.0]
    assert max(sum(1 for t in repairs if a <= t < a + 3600) for a in repairs) == 3


def test_the_queue_command_logs_are_found(tmp_path):
    from scripts import night_reader_supervisor as S
    cmd = tmp_path / "q.cmd"
    cmd.write_text("python -m scripts.dowjones_pull --queue q.txt >> a.log 2>> a.log.err\n")
    (tmp_path / "a.log").write_text("x" * 10 + "\nREFUSED_INSTANCE_DOWN: closed\n")
    logs = S.queue_logs(cmd)
    assert [p.name for p in logs] == ["a.log", "a.log.err"]
    logs = [tmp_path / "a.log", tmp_path / "missing.err"]
    assert GR.classify_exit(S.log_tail(logs))["kind"] == "CHROME_DOWN"


# ─────────────── 7. rotation, caps, yield, social rows (web_reader) ──────────

def test_the_next_lane_is_the_one_whose_host_is_free_soonest():
    last = {"wsj.com": TODAY - timedelta(seconds=5), "x.com": TODAY - timedelta(seconds=30)}
    lanes = [("wsj:a", "wsj.com"), ("x:nvda", "x.com"), ("reddit:nvda", "reddit.com")]
    # wsj.com is busy for 13 s more; x.com and reddit.com are free NOW: a tie keeps
    # the caller's (fair) order
    assert WR.pick_next_lane(lanes, last, TODAY, 18.0) == "x:nvda"
    assert WR.pick_next_lane([lanes[0], lanes[2], lanes[1]], last, TODAY, 18.0) == "reddit:nvda"
    assert WR.pick_next_lane(lanes[:1], last, TODAY, 18.0) == "wsj:a"     # the only one left
    # all busy: the soonest free wins, whatever the order
    last2 = {"wsj.com": TODAY - timedelta(seconds=15), "x.com": TODAY - timedelta(seconds=2)}
    assert WR.pick_next_lane(lanes[:2], last2, TODAY, 18.0) == "wsj:a"
    assert WR.pick_next_lane([], last, TODAY, 18.0) is None


def test_with_more_hosts_no_host_repeats_inside_its_floor():
    q = {"wsj": list(range(6)), "barrons": list(range(6)), "x": list(range(6)),
         "reddit": list(range(6))}
    hosts = {"wsj": "wsj.com", "barrons": "barrons.com", "x": "x.com", "reddit": "reddit.com"}
    order = WR.host_aware_order(q, hosts, same_host_gap_s=18.0, load_s=8.0, start=TODAY)
    assert len(order) == 24 and sorted(order) == sorted((k, i) for k in q for i in range(6))
    for a, b in zip(order, order[1:]):
        assert a[0] != b[0]                       # never the same host twice in a row
    assert [i for k, i in order if k == "x"] == list(range(6))   # a lane keeps its order


def test_the_social_hosts_have_their_own_daily_cap(tmp_path):
    th = WR.Throttle(tmp_path / "t.log", min_delay_s=0.0, max_delay_s=0.0,
                     min_same_host_gap_s=0.0, max_per_hour=10_000, max_per_day=10_000,
                     max_per_day_per_host=600, now_fn=lambda: TODAY, sleep_fn=lambda s: None,
                     per_host_day_caps={"x.com": 150, "reddit.com": 150, "stocktwits.com": 150})
    assert th.host_day_cap("old.reddit.com") == 150 and th.host_day_cap("wsj.com") == 600
    tl = tmp_path / "t.log"
    tl.write_text("".join(f"{(TODAY - timedelta(minutes=i)).isoformat()} x.com 10\n"
                          for i in range(150)), encoding="utf-8")
    with pytest.raises(WR.ReaderRefused, match="REFUSED_THROTTLE_HOST_DAY: >= 150"):
        th.acquire("page", host="x.com")
    th.acquire("page", host="wsj.com")


def test_the_social_caps_in_config_are_150_each():
    from backend import config as C
    assert C.WEB_READER_MAX_PER_DAY_BY_HOST == {"x.com": 150, "reddit.com": 150,
                                               "stocktwits.com": 150}
    assert set(C.OPENCLAW_SOCIAL_HOSTS) == {"x.com", "reddit.com", "stocktwits.com"}
    assert set(C.OPENCLAW_USER_TAB_HOSTS) <= set(C.OPENCLAW_BROWSER_HOSTS)
    assert C.OPENCLAW_ALLOWED_PROFILES == ("muratclaw",)
    assert set(C.OPENCLAW_MAIN_CHROME_PROFILES) == {"user", "chrome"}


def test_a_lane_at_zero_on_every_page_refuses_by_name_after_ten_pages():
    """2026-09-28: 51 of 51 stock pages returned 0 links and nothing noticed."""
    printed: list[str] = []
    y = WR.YieldCheck(after=10, printer=printed.append)
    for i in range(9):
        lane = "wsj:search" if i % 2 else "barrons:picks"
        y.record(lane, links=0 if lane == "wsj:search" else 12)
    with pytest.raises(WR.ReaderRefused, match=r"REFUSED_ZERO_YIELD_LANE: \['wsj:search'\]"):
        y.record("wsj:search", links=0)
    assert printed and printed[0].startswith("YIELD ")
    rep = y.reports[0]["lanes"]
    assert rep["barrons:picks"]["links_per_page"] == 12.0
    assert rep["wsj:search"]["zero_link_pages"] == 5


def test_a_lane_that_yields_passes_and_the_end_report_is_recorded():
    y = WR.YieldCheck(after=3, printer=None)
    for n in (5, 0, 7):
        y.record("mw:search", links=n)
    y.record("mw:article", chars=4200)
    rep = y.check("end")
    assert rep["zero_lanes"] == [] and rep["lanes"]["mw:article"]["chars_per_page"] == 4200
    assert len(y.reports) == 2


def test_a_social_row_is_tagged_and_stored_by_host_and_day(tmp_path):
    row = {"source_kind": "social", "host": "x.com", "url": "https://x.com/search?q=%24NVDA",
           "read_utc": TODAY.isoformat(), "text": "posts"}
    p = WR.store_social(row, root=tmp_path)
    assert p == tmp_path / "x.com" / f"{TODAY.date().isoformat()}.jsonl"
    assert json.loads(p.read_text(encoding="utf-8").splitlines()[0])["source_kind"] == "social"
    with pytest.raises(WR.ReaderRefused, match="REFUSED_SOCIAL_KIND"):
        WR.store_social({"host": "x.com", "text": "t"}, root=tmp_path)


def test_read_social_page_navigates_scrolls_reads_and_never_clicks(tmp_path):
    calls: list = []

    class Drv:
        def browser(self, verb, *a, profile_name=None, target_id=None, url=None):
            calls.append(verb)
            return {"rc": 0, "verb": verb}

        def read_text(self, tab, profile_name=None):
            calls.append("read_text")
            return {"url": "https://stocktwits.com/symbol/NVDA", "title": "NVDA",
                    "text": "bullish chatter " * 20}

        def own_blank_tab(self, verb, tab, url=None, profile_name=None):
            calls.append(f"own_{verb}")
            return {"rc": 0}

    th = WR.Throttle(tmp_path / "t.log", min_delay_s=0.0, max_delay_s=0.0,
                     min_same_host_gap_s=0.0, now_fn=lambda: TODAY, sleep_fn=lambda s: None)
    rd = WR.Reader(profile="muratclaw", tab="T", driver=Drv(), throttle=th, lock=False)
    row = WR.read_social_page(rd, WR.social_url("stocktwits.com", "nvda"), ticker="nvda",
                              root=tmp_path)
    assert row["source_kind"] == "social" and row["host"] == "stocktwits.com"
    assert row["ticker"] == "NVDA" and row["never"] == ["alert_origin", "order"]
    assert "click" not in calls and calls[0] == "navigate" and "read_text" in calls
    with pytest.raises(WR.ReaderRefused, match="REFUSED_SOCIAL_HOST"):
        WR.read_social_page(rd, "https://www.wsj.com/", root=tmp_path)


def test_a_raw_cdp_target_id_is_a_stable_handle_and_a_tn_alias_is_not():
    assert WR.is_stable_handle("A" * 32) and WR.is_stable_handle("chrome-mcp:abc:4")
    assert not WR.is_stable_handle("t24") and not WR.is_stable_handle("a" * 31)


# ─────────────── 8. the marker is replaced by the instance gate ──────────────

def test_the_reader_proves_the_instance_before_it_resolves_a_tab(monkeypatch):
    from scripts import dowjones_pull as DP

    class OCStub:
        def __init__(self, ok):
            self.ok = ok

        def dedicated_profiles(self):
            return ("muratclaw",)

        def _instance_check(self, profile, **k):
            if not self.ok:
                raise OC.OpenClawRefused("REFUSED_NOT_MURATCLAW_INSTANCE: not it")
            return {"ok": True, "pid": 9}

    assert DP.instance_gate("muratclaw", OCStub(True))["pid"] == 9
    with pytest.raises(WR.ReaderRefused, match="REFUSED_NOT_MURATCLAW_INSTANCE"):
        DP.instance_gate("muratclaw", OCStub(False))
    assert DP.instance_gate("some_other", OCStub(False)) is None


def test_every_browser_entry_of_the_reader_calls_the_gate_right_after_attach():
    import inspect
    from scripts import dowjones_pull as DP
    src = inspect.getsource(DP.main) + inspect.getsource(DP._launch_workers)
    assert src.count("instance_gate(") == 3
    # and the marker still binds on an operator profile that is NOT dedicated
    assert "not in dedicated_profiles()" in inspect.getsource(DP.main)


# ─────────────── 9. the social lane runner (stubbed end to end) ──────────────

def test_the_social_runner_rotates_hosts_stores_social_rows_and_closes_its_tabs(tmp_path):
    from scripts import social_browser_pull as SP
    now = {"t": TODAY}

    class Drv:
        def __init__(self):
            self.calls, self.n, self._OPENED_TABS = [], 0, set()

        def dedicated_profiles(self):
            return ("muratclaw",)

        def _instance_check(self, profile, **k):
            self.calls.append(("prove",))
            return {"ok": True, "pid": 5}

        def open_tab(self, url, profile_name=None):
            self.n += 1
            tid = f"{self.n:032X}"
            self._OPENED_TABS.add(tid)
            self.calls.append(("open_tab", url))
            return {"new_tab": tid, "url": url}

        def browser(self, verb, *a, profile_name=None, target_id=None, url=None):
            self.calls.append((verb,) + a[:1])
            return {"rc": 0, "verb": verb}

        def read_text(self, tab, profile_name=None):
            return {"url": [c for c in self.calls
                            if c[0] in ("open_tab", "navigate", "own_navigate")][-1][1],
                    "title": "t", "text": "a post about the ticker " * 10}

        def own_blank_tab(self, verb, tab, url=None, profile_name=None):
            self.calls.append((f"own_{verb}", url))
            return {"rc": 0}

    def sleep(s):
        now["t"] += timedelta(seconds=s)
    th = WR.Throttle(tmp_path / "t.log", min_delay_s=6.0, max_delay_s=20.0,
                     min_same_host_gap_s=18.0, max_per_hour=1000, max_per_day=1000,
                     now_fn=lambda: now["t"], sleep_fn=sleep, seed=1)
    drv = Drv()
    lanes = SP.plan_lanes(["nvda", "mu"], ["x.com", "reddit.com", "stocktwits.com"])
    rc = SP.run(lanes, driver=drv, throttle=th, root=tmp_path, printer=None)
    assert rc["stopped"] is None and rc["n_rows"] == 6 and rc["instance"]["pid"] == 5
    assert drv.calls[0] == ("prove",)                                # proven before any tab
    # 2026-09-28: one FRESH tab per page (closed after its read, never blanked)
    assert sum(1 for c in drv.calls if c[0] == "open_tab") == 6
    assert sum(1 for c in drv.calls if c[0] == "close") == 6
    assert not any(c[0] == "own_blank" for c in drv.calls)
    assert not any(c[0] in ("click", "type", "fill") for c in drv.calls)
    hosts = [r["host"] for r in rc["rows"]]
    assert all(a != b for a, b in zip(hosts, hosts[1:]))             # never the same host twice
    stored = sorted(p.parent.name for p in tmp_path.rglob("*.jsonl"))
    assert set(stored) == {"x.com", "reddit.com", "stocktwits.com"}
    for p in tmp_path.rglob("*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            assert json.loads(line)["source_kind"] == "social"
    assert rc["closed"] and all(rc["closed"].values())


def test_the_social_runner_refuses_without_the_handoff(monkeypatch, tmp_path, capsys):
    from scripts import social_browser_pull as SP
    monkeypatch.setattr(SP._config, "DOWJONES_HANDOFF_FILE", tmp_path / "HANDOFF_PC")
    assert SP.main(["--tickers", "NVDA", "--handoff"]) == 2
    assert "REFUSED_NO_HANDOFF" in capsys.readouterr().out
    (tmp_path / "HANDOFF_PC").write_text("x")
    assert SP.main(["--tickers", "NVDA", "--hosts", "facebook.com", "--handoff"]) == 2
