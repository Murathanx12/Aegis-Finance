"""The reader POOL (2026-09-28 21:45 HKT): several tabs at once, paced per host,
the sites' own navigation, the per-stock pages and their news, the media and
its published transcripts, the social hosts in the rotation.

Murat: "can openclaw read more, can it launch another chrome tabs to read too,
this one by one is very slow, it needs to read wsj, barron, marketwatch per
stock and the news from that too, it should navigate them, not just the
stocks, and also the media too." / "use the transcript of the videos".

Test doubles only: a fake driver, a fake clock, a fake memory reader, a fake
captions getter, tmp_path. No network, browser, CLI or gateway. Dates derive
from today.
"""
from __future__ import annotations

import json
import subprocess
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as _config
from backend.services import disk_guard as DG
from backend.services import media_transcripts as MT
from backend.services import openclaw_client as OC
from backend.services import openclaw_http as OH
from backend.services import reader_report as RR
from backend.services import reader_scheduler as RS
from backend.services import web_reader as WR
from backend.tests.test_lane_o_muratclaw import FakeBrowser, FakeSession, _cli_adapter
from scripts import reader_pool as RP
from scripts import social_browser_pull as SB

NOW = datetime.now(timezone.utc).replace(microsecond=0)


class Clock:
    def __init__(self, t: datetime = NOW):
        self.t = t
        self.slept: list[float] = []

    def now(self) -> datetime:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += timedelta(seconds=max(0.0, s))


def _thr(tmp_path, clock, **kw) -> WR.Throttle:
    base = dict(path=tmp_path / "_throttle.log", now_fn=clock.now, sleep_fn=clock.sleep,
                seed=7, per_host_mode=True, max_per_hour=1000, max_per_day=10000,
                max_per_day_per_host=5000, per_host_day_caps={},
                host_gap_s={"wsj.com": (10.0, 45.0), "barrons.com": (10.0, 45.0),
                            "x.com": (25.0, 90.0)},
                global_gap_s=(1.0, 4.0), per_host_hour_caps={})
    base.update(kw)
    return WR.Throttle(**base)


# ───────────────────────── 1. per-host pacing on page OPENS ──────────────────

def test_per_host_pacing_binds_on_opens_with_several_tabs(tmp_path):
    """Two tabs on one host cannot open closer than that host's drawn gap; a
    tab bound for ANOTHER host waits only for the short global gap."""
    c = Clock()
    thr = _thr(tmp_path, c)
    a = thr.reserve("open", "wsj.com")
    b = thr.reserve("open", "wsj.com")           # a second wsj tab, same instant
    x = thr.reserve("open", "barrons.com")       # a barrons tab, same instant
    gap_same = (b["slot"] - a["slot"]).total_seconds()
    assert 10.0 <= gap_same <= 45.0 and abs(gap_same - b["target_s"]) < 0.01
    # barrons waits only for the global gap -- from the NEAREST open, not from
    # the latest reservation (2026-09-29: queueing behind another host's future
    # slot left every host idle for 10 minutes): it takes the free time before b
    near = min(abs((x["slot"] - r["slot"]).total_seconds()) for r in (a, b))
    assert near >= 1.0 and x["slot"] < b["slot"]
    assert (x["slot"] - a["slot"]).total_seconds() <= 4.0 + 1e-6
    # a third wsj open is paced from the second, not from the barrons one
    d = thr.reserve("open", "wsj.com")
    assert (d["slot"] - b["slot"]).total_seconds() >= 10.0


def test_the_gaps_are_drawn_never_constant_and_inside_the_range(tmp_path):
    c = Clock()
    thr = _thr(tmp_path, c)
    slots = [thr.reserve("open", "wsj.com")["slot"] for _ in range(60)]
    gaps = [(b - a).total_seconds() for a, b in zip(slots, slots[1:])]
    assert all(10.0 <= g <= 45.0 + 1e-6 for g in gaps)
    assert len({round(g, 2) for g in gaps}) == len(gaps)           # never the same twice
    assert all(abs(b - a) >= 1.0 for a, b in zip(gaps, gaps[1:]))  # never within 1 s
    mean = sum(gaps) / len(gaps)
    sd = (sum((g - mean) ** 2 for g in gaps) / len(gaps)) ** 0.5
    assert sd / mean > 0.15                                         # the footprint alarm's line


def test_the_lock_is_not_held_through_the_sleep(tmp_path):
    """A worker sleeping out one host's gap must not block another's reservation."""
    c = Clock()
    thr = _thr(tmp_path, c)
    thr.reserve("open", "wsj.com")
    seen: list[bool] = []

    def sleep(s: float) -> None:
        got: list[bool] = []

        def other() -> None:
            try:
                with DG.file_lock(thr.lock_path(), timeout_s=0.5):
                    got.append(True)
            except DG.FileLockTimeout:
                got.append(False)
        th = threading.Thread(target=other)
        th.start()
        th.join()
        seen.extend(got)
        c.sleep(s)
    thr.sleep_fn = sleep
    waited = thr.acquire("open", "wsj.com")
    assert waited >= 10.0 and seen == [True]


def test_a_host_hourly_cap_refuses_or_waits_and_the_other_host_is_free(tmp_path):
    c = Clock()
    thr = _thr(tmp_path, c, per_host_hour_caps={"wsj.com": 3})
    for _ in range(3):
        thr.reserve("open", "wsj.com")
    with pytest.raises(WR.ReaderRefused, match="REFUSED_THROTTLE_HOUR"):
        thr.reserve("open", "wsj.com")
    thr.reserve("open", "barrons.com")                    # another host is not capped
    thr.wait_on_hour_cap = True
    r = thr.reserve("open", "wsj.com")
    first = datetime.fromisoformat((tmp_path / "_throttle.log").read_text().split()[0])
    assert r["slot"] >= first + timedelta(hours=1)


def test_a_reserved_slot_that_opened_nothing_is_given_back(tmp_path):
    c = Clock()
    thr = _thr(tmp_path, c)
    r = thr.reserve("open", "wsj.com")
    assert thr.refund("open failed", line=r["line"])
    assert (tmp_path / "_throttle.log").read_text().strip() == ""


def test_the_old_global_mode_is_unchanged_by_default(tmp_path):
    thr = WR.Throttle(tmp_path / "t.log")
    assert thr.per_host_mode is False


# ───────────────────────────── 2. the tab governor ───────────────────────────

def test_the_governor_grows_to_the_max_with_memory_and_shrinks_below_the_floor():
    mem = {"gb": 9.0}
    g = RS.TabGovernor(max_tabs=6, floor_gb=2.0, grow_gb=2.6, mem_fn=lambda: mem["gb"])
    for _ in range(10):
        g.update()
    assert g.target == 6 and "holding at 6" in g.reason
    mem["gb"] = 1.5
    for _ in range(10):
        g.update()
    assert g.target == 1 and "floor" in g.reason          # never below one tab
    assert g.may_open(0) is True                           # the reader never stops entirely
    assert g.may_open(1) is False and "no new tab" in g.reason
    mem["gb"] = 2.3                                        # between floor and grow: hold
    g.update()
    assert g.target == 1 and "holding" in g.reason
    assert [h["to"] for h in g.history][:1] == [2]


def test_the_governor_holds_when_memory_cannot_be_read():
    g = RS.TabGovernor(max_tabs=6, mem_fn=lambda: None, target=3)
    g.update()
    assert g.target == 3 and "unreadable" in g.reason


# ─────────────────────── 3. section fronts on a schedule ─────────────────────

def _ny(hour: int, weekday: bool = True) -> datetime:
    from zoneinfo import ZoneInfo
    d = datetime.now(ZoneInfo("America/New_York")).replace(hour=hour, minute=0, second=0,
                                                            microsecond=0)
    while (d.weekday() < 5) != weekday:
        d += timedelta(days=1)
    return d.astimezone(timezone.utc)


def test_fronts_are_due_every_30_min_in_us_hours_and_every_2_h_otherwise():
    home = next(f for f in RS.SECTION_FRONTS if RS.front_key(f) == "wsj:home")
    tech = next(f for f in RS.SECTION_FRONTS if RS.front_key(f) == "wsj:tech")
    day = _ny(11)
    assert RS.front_interval_s(home, day) == 1800 and RS.front_interval_s(tech, day) == 7200
    assert RS.front_interval_s(home, _ny(22)) == 7200
    assert RS.front_interval_s(home, _ny(11, weekday=False)) == 7200
    assert RS.front_due(home, None, day)
    assert not RS.front_due(home, day - timedelta(minutes=29), day)
    assert RS.front_due(home, day - timedelta(minutes=31), day)
    assert not RS.front_due(tech, day - timedelta(minutes=90), day)


def test_a_front_url_not_found_is_dropped_and_the_next_candidate_tried(tmp_path):
    mk = next(f for f in RS.SECTION_FRONTS if RS.front_key(f) == "wsj:markets")
    assert RS.front_url(mk, set()) == mk["urls"][0]
    p = tmp_path / "nf.json"
    assert RS.record_section_not_found(mk["urls"][0], "PAGE_NOT_FOUND", NOW, path=p)
    assert not RS.record_section_not_found(mk["urls"][0], "again", NOW, path=p)   # once
    dropped = RS.dropped_section_urls(p)
    assert RS.front_url(mk, dropped) == mk["urls"][1]
    assert RS.front_url(mk, set(mk["urls"])) is None


def test_every_front_the_owner_named_is_in_the_catalogue():
    keys = {RS.front_key(f) for f in RS.SECTION_FRONTS}
    for k in ("wsj:home", "wsj:markets", "wsj:business", "wsj:tech", "wsj:economy", "wsj:world",
              "wsj:heard_on_the_street", "wsj:latest_headlines", "barrons:home",
              "barrons:markets", "barrons:stock_picks", "barrons:technology",
              "barrons:economy_and_policy", "barrons:latest_news",
              "barrons:up_and_down_wall_street", "barrons:the_trader", "barrons:streetwise",
              "marketwatch:home", "marketwatch:latest_news", "marketwatch:markets",
              "marketwatch:investing", "marketwatch:stocks", "marketwatch:economy_and_politics",
              "marketwatch:earnings", "marketwatch:upgrades_downgrades"):
        assert k in keys, k
    assert all(WR.host_ok(u) for f in RS.SECTION_FRONTS for u in f["urls"])


# ─────────────────────── 4. the depth-1 related-link rule ────────────────────

def test_related_links_are_followed_to_depth_one_only_when_a_universe_ticker_is_named():
    art = "https://www.barrons.com/articles/nvidia-chips-1a2b3c4d"
    rel = "https://www.barrons.com/articles/amd-rival-5e6f7a8b"
    kw = dict(universe={"NVDA"}, pattern=RS.BARRONS_ARTICLE)
    assert RS.may_follow_related({"depth": 0, "url": art}, rel, named=["NVDA"], **kw)
    assert not RS.may_follow_related({"depth": 1, "url": art}, rel, named=["NVDA"], **kw)
    assert not RS.may_follow_related({"depth": 0, "url": art}, rel, named=[], **kw)
    assert not RS.may_follow_related({"depth": 0, "url": art}, rel, named=["TSLA"], **kw)
    off = "https://www.wsj.com/tech/amd-rival-5e6f7a8b"
    assert not RS.may_follow_related({"depth": 0, "url": art}, off, named=["NVDA"], **kw)
    assert not RS.may_follow_related({"depth": 0, "url": art},
                                     "https://www.barrons.com/topics/markets", named=["NVDA"],
                                     **kw)


def test_names_tickers_reads_the_ways_the_sites_print_a_ticker():
    t = "Nvidia (NVDA) and AMD +1.2%; ticker: MU. IT spending. A (NASDAQ: AAPL) chip. $TSLA."
    got = WR.names_tickers(t, {"NVDA", "AMD", "MU", "IT", "AAPL", "TSLA", "A"})
    assert set(got) == {"NVDA", "AMD", "MU", "AAPL", "TSLA"}


# ───────────────────────────── 5. what to read first ─────────────────────────

def test_the_priority_order_is_fronts_then_front_news_then_books_then_fresh_then_rest():
    books, fresh = {"NVDA"}, {"MRVL"}
    last = {"NVDA": "2026-01-01", "MRVL": "", "AAA": "2026-01-01", "BBB": ""}
    items = [
        {"kind": "stock_links", "ticker": "AAA", "url": "u1", "seq": 1},
        {"kind": "stock_links", "ticker": "BBB", "url": "u2", "seq": 2},
        {"kind": "stock_links", "ticker": "MRVL", "url": "u3", "seq": 3},
        {"kind": "stock_links", "ticker": "NVDA", "url": "u4", "seq": 4},
        {"kind": "article", "tier": RS.TIER_FRONT_NEWS, "parent_url": "f", "url": "u5",
         "position": 2, "seq": 5},
        {"kind": "front", "url": "u6", "seq": 6},
        {"kind": "article", "ticker": "NVDA", "parent_url": "u4", "tier": RS.TIER_BOOK,
         "url": "u7", "seq": 7},
    ]
    key = lambda it: RS.priority_key(it, books=books, fresh=fresh, last_read=last)  # noqa: E731
    order = [it["url"] for it in sorted(items, key=key)]
    assert order == ["u6", "u5", "u7", "u4", "u3", "u2", "u1"]


def test_choose_prefers_a_host_free_now_over_one_the_tab_would_wait_for():
    key = lambda it: (it["p"],)  # noqa: E731
    pending = {"wsj.com": [{"host": "wsj.com", "p": 0}],
               "barrons.com": [{"host": "barrons.com", "p": 5}]}
    free_at = {"wsj.com": NOW + timedelta(seconds=40), "barrons.com": NOW}
    got = RS.choose(pending, free_slots={"wsj.com": 1, "barrons.com": 1}, blocked=set(),
                    free_at=free_at, now=NOW, key=key)
    assert got["host"] == "barrons.com"
    free_at["wsj.com"] = NOW + timedelta(seconds=3)                 # within the slack: best wins
    got = RS.choose(pending, free_slots={"wsj.com": 1, "barrons.com": 1}, blocked=set(),
                    free_at=free_at, now=NOW, key=key)
    assert got["host"] == "wsj.com"
    assert RS.choose(pending, free_slots={"wsj.com": 1, "barrons.com": 1},
                     blocked={"wsj.com", "barrons.com"}, free_at=free_at, now=NOW,
                     key=key) is None
    assert RS.choose(pending, free_slots={"wsj.com": 0, "barrons.com": 0}, blocked=set(),
                     free_at=free_at, now=NOW, key=key) is None


# ─────────────────────── 6. media and published transcripts ──────────────────

VTT = ("WEBVTT\n\nNOTE made by the site\n\n1\n00:00:00.000 --> 00:00:02.000\n"
       "<v Host>Nvidia beat estimates.\n\n2\n00:00:02.000 --> 00:00:04.000\n"
       "Nvidia beat estimates.\n\n3\n00:00:04.000 --> 00:00:06.000\nGuidance was raised.\n")


def test_captions_parse_to_plain_text():
    assert MT.parse_captions(VTT) == "Nvidia beat estimates.\nGuidance was raised."
    srt = "1\n00:00:01,000 --> 00:00:02,000\nHello\n\n2\n00:00:02,000 --> 00:00:03,000\nWorld\n"
    assert MT.parse_captions(srt) == "Hello\nWorld"
    assert MT.iso_duration_s("PT2M30S") == 150 and MT.iso_duration_s("95") == 95
    assert MT.iso_duration_s("soon") is None


def test_media_items_take_the_sites_own_transcript_else_captions_else_none_published():
    page = "https://www.wsj.com/video/series/markets/nvidia-earnings/ABC"
    m = {"structured": [{"type": "VideoObject", "name": "Nvidia earnings", "duration": "PT3M",
                         "published": "2026-09-28T12:00:00Z", "transcript": "Full text here."}],
         "caption_urls": ["https://cdn.example-video.net/c/abc.vtt"]}
    items = MT.items_from_media(page, m)
    assert items[0]["transcript_source"] == "structured_data" and items[0]["duration_s"] == 180
    m2 = {"elements": [{"kind": "video", "title": "Clip", "duration": 61,
                        "tracks": [{"src": "https://cdn.example-video.net/c/clip.vtt"}]}]}
    got = MT.resolve_transcripts(MT.items_from_media(page, m2),
                                 fetch=lambda u: {"ok": True, "host": "cdn.example-video.net",
                                                  "text": "Captions text."})
    assert got[0]["transcript_source"] == "captions_track"
    assert got[0]["captions_host"] == "cdn.example-video.net"
    m3 = {"audio": {"n": 1, "titles": ["The Barron's Streetwise podcast"]}}
    got = MT.resolve_transcripts(MT.items_from_media(page, m3), fetch=lambda u: {})
    assert got[0]["transcript"] == MT.NONE_PUBLISHED and got[0]["media_kind"] == "audio"
    assert MT.items_from_media(page, {"images": {"n": 4}}) == []


class _Resp:
    def __init__(self, body: bytes, ct: str = "text/vtt", code: int = 200):
        self.status_code, self.headers, self._b = code, {"Content-Type": ct}, body

    def iter_content(self, n):
        yield self._b


def test_only_a_captions_text_file_is_ever_fetched():
    calls = []

    def get(url, **kw):
        calls.append(url)
        return _Resp(VTT.encode())
    ok = MT.fetch_captions("https://cdn.example-video.net/c/a.vtt", get=get)
    assert ok["ok"] and ok["host"] == "cdn.example-video.net" and "Guidance" in ok["text"]
    for bad in ("http://cdn.example-video.net/a.vtt",          # not https
                "https://cdn.example-video.net/a.mp4",         # a video file, never
                "https://cdn.example-video.net/a.m3u8",        # a stream playlist, never
                "https://x.com/a.vtt",                          # a social host
                "https://mail.google.com/a.vtt"):              # a refused host
        assert not MT.fetch_captions(bad, get=get)["ok"]
    assert calls == ["https://cdn.example-video.net/c/a.vtt"]
    big = MT.fetch_captions("https://cdn.example-video.net/c/b.vtt",
                            get=lambda u, **k: _Resp(b"x" * 50), max_bytes=10)
    assert "TOO_BIG" in big["error"]
    html = MT.fetch_captions("https://cdn.example-video.net/c/b.vtt",
                             get=lambda u, **k: _Resp(b"<html>", ct="text/html"))
    assert "CONTENT_TYPE" in html["error"]


def test_the_media_function_is_a_constant_and_nothing_else_is_evaluated():
    with pytest.raises(OC.OpenClawRefused, match="REFUSED_EVALUATE_NOT_CONSTANT"):
        OC._evaluate_constant("() => fetch('https://evil')", "A" * 32)
    assert "fetch(" not in OC.READ_MEDIA_FN and "click" not in OC.READ_MEDIA_FN
    assert ".play(" not in OC.READ_MEDIA_FN and "XMLHttpRequest" not in OC.READ_MEDIA_FN


# ───────────────────────────── 7. social classes ─────────────────────────────

@pytest.mark.parametrize("final,text,cls", [
    ("https://x.com/search?q=%24NVDA&f=live", "NVDA post " * 60, "OK"),
    ("https://x.com/i/flow/login", "Sign in to X " * 20, "LOGIN_WALL"),
    ("https://x.com/search?q=%24NVDA", "Sign in to X. Don't miss what's happening " * 6,
     "LOGIN_WALL"),
    ("https://www.reddit.com/r/stocks/search/", "whoa there, pardner! " * 12, "RATE_LIMITED"),
    ("https://stocktwits.com/symbol/NVDA", "Just a moment... Verify you are human " * 6,
     "CHALLENGE"),
    ("https://x.com/search?q=%24NVDA", "Something went wrong. Try reloading. " * 6,
     "INTERSTITIAL"),
    ("https://x.com/search?q=%24NVDA", "", "BLANK"),
    ("https://www.google.com/", "x" * 400, "REDIRECTED_OFF_HOST"),
])
def test_social_pages_are_classified(final, text, cls):
    assert WR.classify_social(url=final, final_url=final, title="", text=text) == cls


def test_a_social_row_can_never_be_an_alert_origin(tmp_path):
    row = {"source_kind": "social", "host": "x.com", "url": "https://x.com/search?q=%24NVDA",
           "read_utc": NOW.isoformat(), "text": "posts"}
    p = WR.store_social(row, root=tmp_path)
    stored = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert set(stored["never"]) >= {"alert_origin", "order"}
    for bad in ({"alert_origin": True}, {"order_origin": True}, {"is_alert_origin": 1}):
        with pytest.raises(WR.ReaderRefused, match="REFUSED_SOCIAL_ALERT_ORIGIN"):
            WR.store_social(dict(row, **bad), root=tmp_path)


def test_social_items_navigate_to_urls_never_type_and_pass_the_write_rules():
    from backend.services import browser_policy as BP
    items = SB.social_items(["NVDA"])
    assert {i["host"] for i in items} == {"x.com", "reddit.com", "stocktwits.com"}
    for it in items:
        assert BP.social_url_refusal(it["url"], WR.social_hosts()) is None
        assert "typed" not in it["url"]
    red = next(i for i in items if i["host"] == "reddit.com")["url"]
    assert "r/stocks+investing" in red and "restrict_sr=1" in red


# ───────────────────── 8. the pool, end to end, fake driver ──────────────────

def _snap(title: str, links: list[tuple[str, str]]) -> str:
    body = [f'- RootWebArea "{title}" [ref=e1]']
    for i, (text, url) in enumerate(links, 2):
        body.append(f'- link "{text}" [ref=e{i}] [url={url}]')
    body += ['- paragraph "' + "market news and analysis " * 12 + '"']
    return "\n".join(body) + "\n"


class FakeDriver:
    """A dedicated MuratClaw Chrome: open / snapshot / press / evaluate / close."""

    def __init__(self, pages: dict[str, dict]):
        self.pages, self.tabs, self.n = pages, {}, 0
        self._OPENED_TABS: set[str] = set()
        self.actions: list[tuple[str, str]] = []
        self.proofs = 0
        self.lock = threading.Lock()
        self.fail_proof = False

    def dedicated_profiles(self):
        return ("muratclaw",)

    def _prove(self):
        self.proofs += 1
        if self.fail_proof:
            raise OC.OpenClawRefused("REFUSED_NOT_MURATCLAW_INSTANCE: not the dedicated Chrome")

    def open_tab(self, url, *, profile_name="muratclaw", timeout=90.0):
        self._prove()
        with self.lock:
            self.n += 1
            tid = f"{self.n:032X}"
            self.tabs[tid] = url
            self._OPENED_TABS.add(tid)
            self.actions.append(("open", url))
        return {"new_tab": tid, "url": url, "rc": 0}

    def browser(self, verb, *args, profile_name=None, target_id=None, url=None, timeout=0):
        self._prove()
        with self.lock:
            self.actions.append((verb, self.tabs.get(target_id, "")))
        if verb == "snapshot":
            return {"rc": 0, "stdout": self.pages.get(self.tabs.get(target_id), {}).get(
                "snapshot", "")}
        if verb == "close":
            self.tabs.pop(target_id, None)
        return {"rc": 0}

    def read_text(self, tab, *, profile_name=None):
        self._prove()
        url = self.tabs.get(tab)
        with self.lock:
            self.actions.append(("read_text", url))
        p = self.pages.get(url, {})
        return {"url": url, "title": p.get("title"), "text": p.get("text", "")}

    def read_media(self, tab, *, profile_name=None):
        self._prove()
        url = self.tabs.get(tab)
        with self.lock:
            self.actions.append(("read_media", url))
        p = self.pages.get(url, {})
        return {"url": url, "media": p.get("media"), "tables": p.get("tables", []),
                "related_links": p.get("related", [])}


FRONT = "https://www.wsj.com/"
ART1 = "https://www.wsj.com/tech/nvidia-beats-estimates-1a2b3c4d"
ART2 = "https://www.wsj.com/finance/stocks/chip-rally-broadens-5e6f7a8b"
REL = "https://www.wsj.com/tech/amd-answers-nvidia-9a8b7c6d"
REL2 = "https://www.wsj.com/tech/second-level-related-0f0e0d0c"
VIDEO = "https://www.wsj.com/video/series/markets/nvidia-earnings-explained/ABCDEF12"
STOCK = "https://www.barrons.com/market-data/stocks/nvda"
BARTICLE = "https://www.barrons.com/articles/buy-nvidia-stock-price-pick-c12a8a9a"
LONG = "Nvidia (NVDA) reported results that beat estimates. " * 30


def _pages() -> dict:
    return {
        FRONT: {"snapshot": _snap("The Wall Street Journal", [
            ("Nvidia Beats Estimates Again On Data Centers", ART1),
            ("Chip Rally Broadens Beyond the Giants", ART2),
            ("Sponsored: Partner Content Wealth Offer", "https://www.wsj.com/tech/ad-00000000"),
            ("Nvidia Earnings Explained In Three Minutes", VIDEO)])},
        ART1: {"title": "Nvidia Beats Estimates", "text": LONG,
               "media": {"video": {"n": 1, "titles": ["Nvidia call"]},
                         "structured": [{"type": "VideoObject", "name": "Nvidia call",
                                         "duration": "PT2M", "transcript": "Jensen said..."}]},
               "tables": [{"caption": "Revenue", "rows": [["Q", "Rev"], ["Q2", "46.7"]]}],
               "related": [{"url": REL, "text": "AMD Answers Nvidia With a New Chip"},
                           {"url": "https://www.barrons.com/articles/off-host-11112222",
                            "text": "An off-host related article here"}]},
        ART2: {"title": "Chip Rally", "text": "The chip rally broadened today. " * 30},
        REL: {"title": "AMD answers", "text": "AMD (AMD) answered Nvidia (NVDA). " * 30,
              "related": [{"url": REL2, "text": "A Second Level Related Article"}]},
        VIDEO: {"title": "Nvidia earnings explained", "text": "Video page. " * 40,
                "media": {"elements": [{"kind": "video", "title": "Explained", "duration": 180,
                                        "tracks": [{"src": "https://cdn.vid.example/e.vtt"}]}]}},
        STOCK: {"snapshot": _snap("NVDA Stock Price | Barron's", [
            ("Buy Nvidia Stock, This Analyst Says", BARTICLE)])},
        BARTICLE: {"title": "Buy Nvidia", "text": "Barron's says buy Nvidia (NVDA). " * 30},
    }


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(_config, "DOWJONES_HANDOFF_FILE", tmp_path / "HANDOFF_PC")
    (tmp_path / "HANDOFF_PC").write_text("x")
    monkeypatch.setattr(RP, "DJ", tmp_path / "dowjones")
    monkeypatch.setattr(RP, "FRONT_SCHEDULE", tmp_path / "dowjones" / "front_schedule.json")
    monkeypatch.setattr(RP, "SOCIAL_SEEN", tmp_path / "social_seen.jsonl")
    monkeypatch.setattr(RP, "STOP_FILES", (tmp_path / "STOP",))
    return tmp_path


def _pool(ledger, driver, *, fronts=None, stock_pages=(), names=("NVDA",), social=False,
          max_pages=None, mem=9.0, **kw):
    c = Clock()
    thr = _thr(ledger, c, host_gap_s={"wsj.com": (10.0, 45.0), "barrons.com": (10.0, 45.0)},
               wait_on_hour_cap=True)
    gov = RS.TabGovernor(max_tabs=4, mem_fn=lambda: mem, target=4)
    return RP.Pool(driver=driver, throttle=thr, names=list(names), books={"NVDA"}, fresh=set(),
                   fronts=[f for f in RS.SECTION_FRONTS if RS.front_key(f) == "wsj:home"]
                   if fronts is None else fronts, social=social, stock_pages=stock_pages,
                   governor=gov, cooling=RS.HostCooling(path=ledger / "cool.json"),
                   max_pages=max_pages, stored={}, now_fn=c.now, wait_fn=lambda s: False,
                   caption_fetch=lambda u: {"ok": True, "host": "cdn.vid.example",
                                            "text": "The video captions."},
                   dropped=set(), front_last={}, stock_last={}, social_last={},
                   printer=lambda *a: None, reader_sleep=lambda s: None, **kw), c


def _drain(pool, n=40):
    """Serve the queue on one slot until it is empty (deterministic)."""
    for _ in range(n):
        it = pool.take(0)
        if it is None:
            break
        try:
            pool.process(it, 0)
        finally:
            pool.release(it)


def _stored(ledger) -> dict[str, dict]:
    out = {}
    for p in (ledger / "news_corpus" / "dowjones").glob("*/*/*.json"):
        r = json.loads(p.read_text(encoding="utf-8"))
        out[r["url"]] = r
    return out


def test_the_pool_reads_a_front_its_news_media_and_related_to_depth_one(ledger):
    d = FakeDriver(_pages())
    pool, _ = _pool(ledger, d)
    pool.refill()
    _drain(pool)
    st = _stored(ledger)
    assert set(st) == {ART1, ART2, REL, VIDEO}               # no ad, no depth-2, no off-host
    rb = st[ART1]["reached_by"]
    assert rb["lane"] == "front:wsj:home" and rb["parent_url"] == FRONT and rb["position"] == 1
    assert rb["depth"] == 0 and rb["via"] == "front"
    assert st[REL]["reached_by"]["depth"] == 1 and st[REL]["reached_by"]["lane"] == "related"
    assert st[ART1]["media"]["video"]["n"] == 1 and st[ART1]["tables"][0]["rows"][1] == ["Q2",
                                                                                        "46.7"]
    assert "NVDA" in st[ART1]["tickers_named"]
    assert all(v == 0 for v in [len(d.tabs)])                 # every tab closed
    opens = [u for v, u in d.actions if v == "open"]
    assert opens[0] == FRONT and REL2 not in opens
    rows = [json.loads(ln) for p in (ledger / "news_corpus" / "media_transcripts").glob("*/*.jsonl")
            for ln in p.read_text(encoding="utf-8").splitlines()]
    by_src = Counter(r["transcript_source"] for r in rows)
    assert by_src == {"structured_data": 1, "captions_track": 1}
    assert pool.media_counts["wsj.com"]["with_transcript"] == 2


def test_every_open_is_proven_and_a_failed_proof_stops_the_pool(ledger):
    d = FakeDriver(_pages())
    pool, _ = _pool(ledger, d)
    pool.refill()
    _drain(pool)
    n_actions = len(d.actions)
    assert d.proofs >= n_actions                              # a proof before every action
    d2 = FakeDriver(_pages())
    d2.fail_proof = True
    pool2, _ = _pool(ledger, d2, front_last=None) if False else _pool(ledger, d2)
    pool2.front_last = {}
    pool2.refill()
    _drain(pool2)
    assert d2.actions == [] and "REFUSED_NOT_MURATCLAW_INSTANCE" in (pool2.stop_reason or "")


def test_a_challenge_page_stops_that_host_and_the_status_says_so(ledger):
    pages = _pages()
    pages[FRONT]["snapshot"] = _snap("Access Denied", [("x" * 20, ART1)]).replace(
        "market news", "Access to this page has been denied. Verify you are human")
    d = FakeDriver(pages)
    alerts = []
    pool, _ = _pool(ledger, d, alert_fn=alerts.append)
    pool.refill()
    _drain(pool)
    assert [e["host"] for e in pool.cool_events] == ["wsj.com"] and alerts
    assert "wsj.com" in pool.cooling.active(pool.now_fn())
    st = pool.status()
    assert st["hosts"]["wsj.com"]["cooling"]["why"].startswith("CHALLENGE")
    # a later wsj item is not served while the host cools
    pool._add({"kind": "article", "site": "wsj", "host": "wsj.com", "url": ART2, "lane": "x"})
    assert pool.take(0) is None


def test_a_social_login_wall_cools_that_host_only(ledger):
    x_url = WR.social_url("x.com", "NVDA")
    st_url = WR.social_url("stocktwits.com", "NVDA")
    pages = {x_url: {"title": "X", "text": "Sign in to X " * 20},
             st_url: {"title": "NVDA", "text": "NVDA bullish post " * 40}}
    d = FakeDriver(pages)
    pool, _ = _pool(ledger, d, fronts=[], social=True, names=("NVDA",))
    pool.per_host.update({"x.com": 1, "stocktwits.com": 1, "reddit.com": 1})
    pool.thr.host_gap_s.update({"x.com": (25.0, 90.0), "stocktwits.com": (25.0, 90.0),
                                "reddit.com": (25.0, 90.0)})
    pool.refill()
    _drain(pool)
    assert set(pool.cooling.active(pool.now_fn())) == {"x.com"}
    rows = [json.loads(ln) for p in (ledger / "news_corpus" / "social").glob("*/*.jsonl")
            for ln in p.read_text(encoding="utf-8").splitlines()]
    assert [r["host"] for r in rows] == ["stocktwits.com"]
    assert rows[0]["source_kind"] == "social" and "alert_origin" in rows[0]["never"]
    assert rows[0]["reached_by"]["lane"] == "social:stocktwits.com"


def test_a_stock_page_s_news_is_read_and_the_page_is_not_reread_inside_its_window(ledger):
    d = FakeDriver(_pages())
    bar = next(p for p in RS.STOCK_PAGES if p["lane"] == "barrons:stock")
    pool, clock = _pool(ledger, d, fronts=[], stock_pages=(bar,))
    pool.refill()
    _drain(pool)
    st = _stored(ledger)
    assert BARTICLE in st and st[BARTICLE]["reached_by"]["lane"] == "barrons:stock"
    assert st[BARTICLE]["reached_by"]["ticker"] == "NVDA"
    assert pool.refill() == 0                                  # fresh: nothing re-queued
    clock.t += timedelta(hours=21)
    assert pool.refill() == 1


def test_the_governor_bounds_the_tabs_the_pool_holds(ledger):
    d = FakeDriver(_pages())
    pool, _ = _pool(ledger, d, mem=1.0)                        # below the floor
    pool.gov.target = 1
    pool.refill()
    it = pool.take(0)
    assert it is not None
    assert pool.take(1) is None                                # slot 1 is above the target
    assert pool.take(0) is None                                # one in flight, below the floor
    pool.release(it)


def test_the_status_reports_tabs_caps_and_per_host_rates(ledger):
    d = FakeDriver(_pages())
    pool, _ = _pool(ledger, d)
    pool.refill()
    _drain(pool)
    st = pool.status()
    assert {"target", "open_now", "why", "free_gb"} <= set(st["tabs"])
    w = st["hosts"]["wsj.com"]
    assert w["loads_60m"] >= 4 and "cap_day" in w and w["classes"].get("OK", 0) >= 4
    assert "hour_all" in st["caps"] and "loads_60m_all" in st["caps"]


# ─────────────── 9. no guard removed: the REAL client, per action ─────────────

class _FB(FakeBrowser):
    """The lane-O fake Chrome, with a fresh id per opened tab."""

    def __init__(self):
        super().__init__()
        self.n = 0

    def do(self, verb, tid=None, arg=None):
        if verb == "open":
            self.actions.append(verb)
            self.n += 1
            nid = f"{0xB0 + self.n:032X}"
            self.tabs[nid] = arg
            return {"targetId": nid, "url": arg}
        return super().do(verb, tid, arg)


@pytest.fixture
def real(monkeypatch):
    proofs: list = []
    monkeypatch.setattr(OC, "_PROVER", lambda **k: proofs.append(k) or {"ok": True})
    monkeypatch.setattr(OC, "attached_to", lambda **k: {"pid": 1})
    monkeypatch.setattr(OC, "_topology_lock", lambda: __import__("contextlib").nullcontext())
    fb = _FB()
    OC.invalidate_profile_cache()
    OC._SNAPSHOTS.clear()
    OC.reset_cli_ledger()
    monkeypatch.setenv(OC.TRANSPORT_ENV, "http")
    monkeypatch.setattr(subprocess, "run", _cli_adapter(fb))
    fb.session = FakeSession(fb)
    monkeypatch.setattr(OC, "_HTTP", OH.HttpTransport(session=fb.session, token_fn=lambda: "tok"))
    fb.proofs = proofs
    yield fb
    for t in list(fb.tabs):
        OC._OPENED_TABS.discard(t)
    OC.invalidate_profile_cache()
    OC._SNAPSHOTS.clear()


def _guards_of(fn) -> Counter:
    OC.reset_cli_ledger()
    fn()
    return Counter(OC.cli_ledger().get("guards") or {})


def test_no_guard_was_removed_per_action_on_the_pool_path(real, ledger):
    """The pool reads one page through the REAL client; its guard counts equal
    the sum of each action's guards measured alone, and the instance is proven
    before every action."""
    pool, _ = _pool(ledger, OC, fronts=[], names=("NVDA",))
    it = {"kind": "stock_text", "site": "wsj", "host": "wsj.com", "lane": "t", "ticker": "NVDA",
          "url": "https://www.wsj.com/tech/nvidia-1a2b3c4d", "column": "c", "key": "k"}
    OC.reset_cli_ledger()
    real.actions.clear()
    pool.process(it, 0)
    got = Counter(OC.cli_ledger()["guards"])
    acts = Counter(real.actions)
    assert acts["open"] == 1 and acts["close"] == 1 and acts["evaluate"] == 2
    # each action alone, on a fresh tab of the same Chrome
    per = {}
    per["open"] = _guards_of(lambda: per.setdefault("tab", OC.open_tab(
        "https://www.wsj.com/tech/nvidia-1a2b3c4d")["new_tab"]))
    tab = per["tab"]
    per["press"] = _guards_of(lambda: OC.browser("press", "PageDown", target_id=tab))
    per["evaluate"] = _guards_of(lambda: OC.read_text(tab))
    per["media"] = _guards_of(lambda: OC.read_media(tab))
    per["close"] = _guards_of(lambda: OC.browser("close", target_id=tab))
    want = per["open"] + per["evaluate"] + per["media"] + per["close"]
    for _ in range(acts["press"]):
        want = want + per["press"]
    assert got == want, (got, want)
    n_actions = sum(acts.values())
    assert got["instance"] >= n_actions + 1                    # open is proven twice
    assert per["media"] == per["evaluate"]                    # the media read = the text read


# ─────────────────────────────── 10. the report ──────────────────────────────

def test_the_reading_report_counts_what_was_read(ledger):
    d = FakeDriver(_pages())
    pool, _ = _pool(ledger, d, names=("NVDA", "AMD"))
    pool.refill()
    _drain(pool)
    day = datetime.now(timezone.utc).date().isoformat()
    p = RR.write_report(day, universe=["NVDA", "AMD", "MU"], root=ledger)
    g = RR.gather(day, root=ledger, universe=["NVDA", "AMD", "MU"])
    assert g["n_articles"] == 4 and g["articles_by_publisher"]
    assert g["tickers_covered"] == 2                           # NVDA, AMD named; MU not
    assert g["media"]["wsj.com"]["with_transcript"] == 2
    txt = p.read_text(encoding="utf-8")
    for s in ("pages/hour", "Articles stored", "tickers covered", "most recent headlines",
              "Media items"):
        assert s.lower() in txt.lower(), s


# ─────────────────────────────── 11. the supervisor ──────────────────────────

def test_the_supervisor_launches_the_pool_and_finds_its_pid_by_command_line():
    from scripts import night_reader_supervisor as S
    txt = S.pool_cmd_text(until="08:00", py="python.exe", day=NOW.date().isoformat())
    assert "-m scripts.reader_pool --handoff --profile muratclaw --until 08:00" in txt
    assert ">> backend\\data\\optimus\\dowjones\\reader_pool_" in txt
    assert "reader_pool" in S.READER_CMDLINE and "dowjones_pull" in S.READER_CMDLINE
    assert S.decide(kind="QUEUE_DONE", probe={"healthy": True}, restarts=0, since_launch_s=None,
                    budget_ok=True) == "stop"


def test_a_section_url_that_lands_on_another_page_is_dropped_not_read(ledger, monkeypatch):
    """Live verification of a section URL: a front that redirects elsewhere is
    recorded once as not found and its next candidate is tried."""
    mk = next(f for f in RS.SECTION_FRONTS if RS.front_key(f) == "wsj:markets")
    pages = _pages()
    pages[mk["urls"][0]] = dict(pages[FRONT])
    pages[mk["urls"][1]] = dict(pages[FRONT])
    d = FakeDriver(pages)
    real_open = d.open_tab

    def open_tab(url, **kw):
        r = real_open(url, **kw)
        if url == mk["urls"][0]:
            r["url"] = "https://www.wsj.com/"            # landed on the home page
        return r
    d.open_tab = open_tab
    monkeypatch.setattr(RS, "sections_not_found_path", lambda: ledger / "nf.json")
    pool, _ = _pool(ledger, d, fronts=[mk])
    pool.refill()
    _drain(pool, n=3)
    assert pool.front_results["wsj:markets"]["class"] == "REDIRECTED"
    assert mk["urls"][0] in pool.dropped
    pool.refill()
    it = pool.take(0)
    assert it["url"] == mk["urls"][1]
    pool.release(it)


def test_a_free_tab_goes_to_the_host_with_the_fewest_tabs_in_flight():
    """Measured live 2026-09-28: the Dow Jones sites took every slot and the
    social hosts waited. Every ready host gets a tab before any gets a second."""
    key = lambda it: (it["p"],)  # noqa: E731
    pending = {"wsj.com": [{"host": "wsj.com", "p": 0}],
               "x.com": [{"host": "x.com", "p": 9}]}
    got = RS.choose(pending, free_slots={"wsj.com": 1, "x.com": 1}, blocked=set(),
                    free_at={}, now=NOW, key=key, in_flight={"wsj.com": 1, "x.com": 0})
    assert got["host"] == "x.com"
    got = RS.choose(pending, free_slots={"wsj.com": 1, "x.com": 1}, blocked=set(),
                    free_at={}, now=NOW, key=key, in_flight={"wsj.com": 1, "x.com": 1})
    assert got["host"] == "wsj.com"
