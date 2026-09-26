"""Chunk J -- Dow Jones through Murat's own Chrome, the paste inbox, the feeds.

No browser, no network, no LLM: every browser verb is a stub driver, every
HTTP call is a stubbed `news_pull._http_get`, every model reply is a string.
Dates are derived from `today`, never literals that expire (protocol 5).
"""

from __future__ import annotations

import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as C
from backend.services import digest_inbox as DI
from backend.services import dowjones_claims as DC
from backend.services import dowjones_feeds as DF
from backend.services import openclaw_client as OC
from backend.services import web_reader as WR

REPO = Path(__file__).resolve().parents[2]

LISTING = """- rootwebarea "Heard on the Street - WSJ"
  - link "Sign Out" [ref=r1]
  - link "Subscribe" [ref=r2]
  - button "Search" [ref=r3]
  - link "Markets" [ref=r4]
  - heading "Heard on the Street" [ref=r5]
  - link "Micron's Memory Boom Has Further to Run" [ref=r6]
  - link "Why DraftKings Investors Should Brace for a Rough Quarter" [ref=r7]
  - link "Micron's Memory Boom Has Further to Run" [ref=r8]
  - link "Our Newsletter: Heard on the Street every morning" [ref=r9]
  - link "A great deal on a subscription offer today" [ref=r10]
  - link "Latest Market Data and the whole Quote Page" [ref=r11]
  - link "Shady page that looks like an article here" [ref=r12]
Links:
1. Sign Out -> https://accounts.wsj.com/logout
2. Subscribe -> https://store.wsj.com/shop
3. Markets -> https://www.wsj.com/finance
4. Micron's Memory Boom Has Further to Run -> https://www.wsj.com/finance/stocks/micron-memory-boom-1a2b3c4d
5. Why DraftKings Investors Should Brace for a Rough Quarter -> https://www.wsj.com/finance/stocks/draftkings-rough-quarter-5e6f7a8b?mod=hots
6. Micron's Memory Boom Has Further to Run -> https://www.wsj.com/finance/stocks/micron-memory-boom-1a2b3c4d
7. Our Newsletter: Heard on the Street every morning -> https://www.wsj.com/newsletters/heard-0000aaaa
8. A great deal on a subscription offer today -> https://www.wsj.com/finance/offer-deal-12345678
9. Latest Market Data and the whole Quote Page -> https://www.wsj.com/market-data/quotes/MU-deadbeef
10. Shady page that looks like an article here -> https://www.wsj-news.evil.com/finance/stocks/fake-9abcdef0
"""
HOTS_PATTERN = r"^https://www\.wsj\.com/(?!news/|market-data|video|podcasts|livecoverage|buyside)[a-z-]+/[a-z0-9/-]*-[0-9a-f]{8}(\?|$)"

ARTICLE_TEXT = """Skip to Main Content
Sign Out
Murat Abdullaev
Markets
Heard on the Street
Micron's Memory Boom Has Further to Run
HBM pricing keeps rising and the market still underestimates it.
By Asa Fitch
Sept. 24, 2026 5:30 am ET
Micron stock has doubled, but investors who sell now are making a mistake because high-bandwidth memory prices should keep rising into 2027.
The company guided above consensus and supply remains tight across the industry, which argues for further gains over the next few months.
Rivals are adding capacity slowly. That leaves Micron with pricing power it has rarely enjoyed in previous cycles, and the shares still trade at a discount.
Copyright ©2026 Dow Jones & Company, Inc. All Rights Reserved.
What to Read Next
Some other story
"""


# ───────────────────────────── link selection ───────────────────────────────

def test_listing_links_come_from_the_page_and_decoys_are_dropped():
    links = WR.select_links(LISTING, HOTS_PATTERN)
    urls = [lk["url"] for lk in links]
    assert urls == ["https://www.wsj.com/finance/stocks/micron-memory-boom-1a2b3c4d",
                    "https://www.wsj.com/finance/stocks/draftkings-rough-quarter-5e6f7a8b?mod=hots"]
    assert links[0]["ref"] == "r6" and links[1]["ref"] == "r7"


def test_a_button_or_account_link_is_never_clickable():
    assert WR.ref_is_clickable(LISTING, "r6")
    assert not WR.ref_is_clickable(LISTING, "r3")      # button
    assert not WR.ref_is_clickable(LISTING, "r1")      # Sign Out
    assert not WR.ref_is_clickable(LISTING, "r2")      # Subscribe
    assert not WR.ref_is_clickable(LISTING, "nope")


def test_never_hosts_are_refused_even_if_allowlisted_by_mistake(monkeypatch):
    monkeypatch.setattr(C, "OPENCLAW_USER_TAB_HOSTS", ("wsj.com", "google.com", "alpaca.markets"))
    assert not WR.host_ok("https://mail.google.com/mail/u/0")
    assert not WR.host_ok("https://app.alpaca.markets/paper")
    assert WR.host_ok("https://www.wsj.com/x")


def test_clean_text_strips_nav_account_and_footer():
    t = WR.clean_text(ARTICLE_TEXT, "Micron's Memory Boom Has Further to Run - WSJ")
    assert t.startswith("Micron's Memory Boom Has Further to Run")
    assert "Abdullaev" not in t and "Sign Out" not in t
    assert "Copyright" not in t and "What to Read Next" not in t
    assert WR.parse_byline(t) == "By Asa Fitch"
    assert WR.parse_published(t) == "2026-09-24T09:30:00+00:00"


# ───────────────────────────────── throttle ─────────────────────────────────

class Clock:
    def __init__(self):
        self.t = datetime.now(timezone.utc)

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=s)


def test_throttle_gaps_are_jittered_in_range_and_never_repeat(tmp_path):
    ck = Clock()
    th = WR.Throttle(tmp_path / "t.log", min_delay_s=20, max_delay_s=90, max_per_hour=99,
                     max_per_day=99, max_per_day_per_host=99, now_fn=ck.now,
                     sleep_fn=ck.sleep, seed=7)
    for _ in range(25):
        th.acquire(host="wsj.com")
    tg = th.targets
    assert all(20 <= t <= 90 for t in tg)
    assert all(abs(a - b) >= 1.0 for a, b in zip(tg, tg[1:]))
    log = [{"at": ln.split()[0]} for ln in (tmp_path / "t.log").read_text().splitlines()]
    fp = WR.footprint_receipt(log, write=False)
    assert fp["verdict"] == "HUMAN_PACE_OK" and fp["cv_of_gaps"] >= WR.FOOTPRINT_CV_ALARM


def test_footprint_alarms_when_pacing_collapses_to_a_constant():
    t0 = datetime.now(timezone.utc)
    log = [{"at": (t0 + timedelta(seconds=30 * i)).isoformat()} for i in range(6)]
    assert WR.footprint_receipt(log, write=False)["verdict"].startswith("ALARM: CV")
    assert WR.footprint_receipt(log[:3], write=False)["verdict"].startswith("CANNOT DETERMINE")


def test_throttle_per_host_daily_cap(tmp_path):
    ck = Clock()
    th = WR.Throttle(tmp_path / "t.log", min_delay_s=20, max_delay_s=20, max_per_hour=99,
                     max_per_day=99, max_per_day_per_host=2, now_fn=ck.now, sleep_fn=ck.sleep)
    th.acquire(host="wsj.com")
    th.acquire(host="wsj.com")
    with pytest.raises(WR.ReaderRefused, match="HOST_DAY"):
        th.acquire(host="wsj.com")
    th.acquire(host="barrons.com")


def test_one_reader_at_a_time(tmp_path):
    import os
    lk = tmp_path / "r.lock"
    WR.acquire_reader_lock(lk)
    lk.write_text(json.dumps({"pid": os.getppid(), "since": "x"}))   # a live other process
    with pytest.raises(WR.ReaderRefused, match="READER_BUSY"):
        WR.acquire_reader_lock(lk)
    lk.write_text(json.dumps({"pid": 999999991, "since": "x"}))       # dead -> stale, taken over
    WR.acquire_reader_lock(lk)
    WR.release_reader_lock(lk)
    assert not lk.exists()


def test_run_decodes_utf8_not_the_console_code_page(monkeypatch):
    seen = {}

    def fake(*a, **k):
        seen.update(k)
        return subprocess.CompletedProcess(a[0], 0, "“quoted”", "")
    monkeypatch.setattr(subprocess, "run", fake)
    OC._run(["x"])
    assert seen.get("encoding") == "utf-8" and seen.get("errors") == "replace"


def test_an_empty_read_is_a_named_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", tmp_path)
    drv = StubDriver()
    drv.read_text = lambda tab, profile_name=None: {"url": "https://www.wsj.com/a", "text": ""}
    ck = Clock()
    r = WR.Reader(profile="user", tab="t99", driver=drv, lock=False,
                  throttle=WR.Throttle(tmp_path / "t.log", now_fn=ck.now, sleep_fn=ck.sleep))
    with pytest.raises(WR.ReaderRefused, match="EMPTY_READ"):
        r.read_article("https://www.wsj.com/finance/x-1a2b3c4d")


def test_throttle_spaces_page_loads_and_refuses_over_the_cap(tmp_path):
    ck = Clock()
    th = WR.Throttle(tmp_path / "t.log", min_delay_s=20, max_delay_s=20, max_per_hour=3,
                     max_per_day=10, now_fn=ck.now, sleep_fn=ck.sleep)
    assert th.acquire() == 0.0
    ck.t += timedelta(seconds=5)
    assert th.acquire() == pytest.approx(15.0)
    assert th.acquire() == pytest.approx(20.0)
    with pytest.raises(WR.ReaderRefused, match="THROTTLE_HOUR"):
        th.acquire()
    # the budget is in the FILE: a second process sees the same history
    th2 = WR.Throttle(tmp_path / "t.log", min_delay_s=20, max_delay_s=20, max_per_hour=3,
                      max_per_day=10, now_fn=ck.now, sleep_fn=ck.sleep)
    with pytest.raises(WR.ReaderRefused, match="THROTTLE_HOUR"):
        th2.acquire()


# ─────────────────────────── openclaw operator rules ────────────────────────

def _fake_profiles():
    return [{"name": "muratclaw", "state": "stopped"}, {"name": "user", "state": "running"},
            {"name": "chrome", "state": "stopped"}]


def test_profiles_parses_the_tab_count_line(monkeypatch):
    out = ("muratclaw: stopped [default]\n  port: 18801\n"
           "user: running (33 tabs) [existing-session]\n  transport: chrome-mcp\n"
           "chrome: stopped [extension]\n")
    monkeypatch.setattr(OC, "_run", lambda args, **k: subprocess.CompletedProcess(args, 0, out, ""))
    ps = {p["name"]: p for p in OC.profiles()}
    assert ps["user"]["state"] == "running" and ps["user"]["tabs"] == 33
    assert ps["user"]["tag"] == "existing-session"


def test_an_unlisted_profile_name_refuses():
    with pytest.raises(OC.OpenClawRefused, match="NOT_ALLOWED"):
        OC.profile("somebody_elses_chrome")


def test_explicit_user_is_honoured_and_never_swapped_for_muratclaw(monkeypatch):
    monkeypatch.setenv(OC.PROFILE_ENV, "muratclaw")
    assert OC.profile("user") == "user"


@pytest.mark.parametrize("verb", ["open", "type", "fill", "download", "batch"])
def test_the_operator_profile_refuses_new_tabs_and_input(monkeypatch, verb):
    monkeypatch.setattr(OC, "profiles", _fake_profiles)
    monkeypatch.setattr(OC, "_run", lambda *a, **k: pytest.fail("must not reach the CLI"))
    with pytest.raises(OC.OpenClawRefused, match="REFUSED_(OPERATOR_VERB|VERB)"):
        OC.browser(verb, url="https://www.wsj.com/", profile_name="user", target_id="t20")


def test_the_operator_profile_refuses_other_hosts(monkeypatch):
    monkeypatch.setattr(OC, "profiles", _fake_profiles)
    monkeypatch.setattr(OC, "_run", lambda *a, **k: pytest.fail("must not reach the CLI"))
    for u in ("https://www.sec.gov/", "https://x.com/", "https://mail.google.com/"):
        with pytest.raises(OC.OpenClawRefused, match="HOST"):
            OC.browser("navigate", u, profile_name="user", target_id="t20")


def test_an_action_on_a_tab_off_the_allowed_hosts_refuses(monkeypatch):
    monkeypatch.setattr(OC, "profiles", _fake_profiles)
    monkeypatch.setattr(OC, "tabs", lambda profile_name=None: [
        {"tabId": "t24", "url": "https://mail.google.com/mail/u/0"},
        {"tabId": "t20", "url": "https://www.wsj.com/news/heard-on-the-street"}])
    monkeypatch.setattr(OC, "_run", lambda *a, **k: pytest.fail("must not reach the CLI"))
    with pytest.raises(OC.OpenClawRefused, match="OPERATOR_TAB_HOST"):
        OC.browser("snapshot", profile_name="user", target_id="t24")
    with pytest.raises(OC.OpenClawRefused, match="OPERATOR_TAB_UNNAMED"):
        OC.browser("snapshot", profile_name="user")


def test_close_only_touches_a_tab_this_process_opened(monkeypatch):
    monkeypatch.setattr(OC, "profiles", _fake_profiles)
    monkeypatch.setattr(OC, "_run", lambda *a, **k: pytest.fail("must not reach the CLI"))
    with pytest.raises(OC.OpenClawRefused, match="OPERATOR_CLOSE"):
        OC.browser("close", profile_name="user", target_id="t20")


def test_evaluate_is_still_not_a_free_verb_and_read_text_sends_only_the_constant(monkeypatch):
    assert "evaluate" not in OC.ALLOWED_VERBS
    seen = {}
    monkeypatch.setattr(OC, "profiles", _fake_profiles)
    monkeypatch.setattr(OC, "tabs", lambda profile_name=None: [
        {"tabId": "t20", "url": "https://www.wsj.com/x"}])
    monkeypatch.setattr(OC, "attached_to", lambda profile_name=None: {"pid": 1})

    def run(args, **k):
        seen["argv"] = args
        return subprocess.CompletedProcess(args, 0, json.dumps(
            {"ok": True, "result": {"url": "https://www.wsj.com/x", "title": "T", "text": "body"}}), "")
    monkeypatch.setattr(OC, "_run", run)
    r = OC.read_text("t20", profile_name="user")
    assert r["text"] == "body" and seen["argv"][-1] == OC.READ_TEXT_FN


def test_open_from_tab_json_encodes_the_url_and_records_the_new_tab(monkeypatch):
    monkeypatch.setattr(OC, "profiles", _fake_profiles)
    state = {"tabs": [{"tabId": "t20", "url": "https://www.wsj.com/a"}]}
    monkeypatch.setattr(OC, "tabs", lambda profile_name=None: list(state["tabs"]))
    monkeypatch.setattr(OC, "attached_to", lambda profile_name=None: {"pid": 1})
    sent = {}

    def run(args, **k):
        sent["fn"] = args[-1]
        state["tabs"].append({"tabId": "t40", "url": "https://www.wsj.com/news/heard-on-the-street"})
        return subprocess.CompletedProcess(args, 0, "{}", "")
    monkeypatch.setattr(OC, "_run", run)
    with pytest.raises(OC.OpenClawRefused, match="OPERATOR_HOST"):
        OC.open_from_tab("t20", "https://www.sec.gov/", sleep_fn=lambda s: None)
    r = OC.open_from_tab("t20", "https://www.wsj.com/news/heard-on-the-street",
                         sleep_fn=lambda s: None)
    assert r["new_tab"] == "t40" and "t40" in OC._OPENED_TABS
    assert '"https://www.wsj.com/news/heard-on-the-street"' in sent["fn"]
    OC._OPENED_TABS.discard("t40")


# ─────────────────────────── the whole reader, stubbed ──────────────────────

class StubDriver:
    """openclaw_client's surface, recorded; pages served from dicts."""

    def __init__(self):
        self.calls = []
        self.current = None
        self.closed = []

    def open_from_tab(self, parent, url, profile_name="user"):
        self.calls.append(("open_from_tab", parent, url))
        self.current = url
        return {"new_tab": "t99", "url": url, "attached_to": {"pid": 7}}

    def browser(self, verb, *args, profile_name=None, target_id=None, url=None):
        self.calls.append((verb, target_id, args))
        if verb == "navigate":
            self.current = args[0]
        if verb == "snapshot":
            return {"rc": 0, "stdout": LISTING}
        if verb == "close":
            self.closed.append(target_id)
        return {"rc": 0, "verb": verb, "stdout": ""}

    def read_text(self, tab, profile_name=None):
        self.calls.append(("read_text", tab))
        return {"url": "https://www.wsj.com/finance/stocks/micron-memory-boom-1a2b3c4d",
                "title": "Micron's Memory Boom Has Further to Run - WSJ", "text": ARTICLE_TEXT}


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", tmp_path)
    return tmp_path


def test_run_reads_opens_one_tab_reads_closes_and_stores_locally(ledger):
    from scripts import dowjones_pull as DP
    ck = Clock()
    drv = StubDriver()
    th = WR.Throttle(ledger / "thr.log", now_fn=ck.now, sleep_fn=ck.sleep, seed=3)
    rc = DP.run_reads("wsj", "heard_on_the_street", parent_tab="t20", max_articles=2,
                      driver=drv, throttle=th)
    assert drv.calls[0][0] == "open_from_tab" and drv.closed == ["t99"]
    assert rc["n_articles"] == 2 and rc["tab_closed"] is True
    assert all(20 <= g <= 90 for g in rc["seconds_between_page_loads"])
    assert len(set(rc["throttle_targets_s"])) == len(rc["throttle_targets_s"])
    # each article scrolled 2-3 PageDowns before the read; footprint written; lock released
    assert sum(1 for c in drv.calls if c[0] == "press") >= 4
    assert rc["footprint"]["scroll_share"] == 1.0 and Path(rc["footprint"]["path"]).exists()
    assert not WR.lock_path().exists()
    # first article by CLICKING its ref from the snapshot, the second by its snapshot URL
    verbs = [c[0] for c in drv.calls]
    assert "click" in verbs and verbs.count("navigate") == 1
    stored = list((ledger / "news_corpus" / "dowjones").glob("wsj/*/*.json"))
    assert len(stored) == 1        # same text twice -> one file (idempotent by sha)
    rec = json.loads(stored[0].read_text(encoding="utf-8"))
    assert rec["licence"] == WR.LICENCE and rec["column"] == "wsj_heard_on_the_street"
    rows = (ledger / "news_corpus" / "dj_reader_wsj").glob("*.jsonl")
    assert sum(1 for f in rows for _ in f.read_text(encoding="utf-8").splitlines()) == 1


def test_browser_reads_refuse_without_the_handoff_file(ledger, monkeypatch, capsys):
    from scripts import dowjones_pull as DP
    monkeypatch.setattr(C, "DOWJONES_HANDOFF_FILE", ledger / "HANDOFF_PC")
    rc = DP.main(["--handoff", "--source", "wsj", "--section", "heard_on_the_street",
                  "--parent-tab", "t20"])
    assert rc == 2 and "REFUSED_NO_HANDOFF" in capsys.readouterr().out


def test_archive_crawl_is_off(monkeypatch, capsys):
    from scripts import dowjones_pull as DP
    monkeypatch.setattr(C, "DOWJONES_ARCHIVE_ENABLED", False)
    past = (date.today() - timedelta(days=3)).isoformat()
    assert DP.main(["--archive", past]) == 2
    assert "REFUSED_ARCHIVE_OFF" in capsys.readouterr().out
    assert DP.main(["--archive", (date.today() + timedelta(days=3)).isoformat()]) == 2


# ───────────────────────────────── claims ───────────────────────────────────

GOOD_REPLY = json.dumps({"claims": [
    {"ticker": "MU", "direction": "up", "horizon_days": 60, "magnitude_bucket": "medium",
     "quote": "high-bandwidth memory prices should keep rising into 2027",
     "paraphrase": "The column expects Micron to keep rising on HBM pricing."},
    {"ticker": "NVDA", "direction": "down", "horizon_days": 21, "magnitude_bucket": "small",
     "quote": "Nvidia will collapse next week", "paraphrase": "invented"},
    {"ticker": "not a ticker", "direction": "up", "quote": "x", "paraphrase": "y"}]})


def test_claims_refuse_an_invented_quote_and_write_a_paraphrase_not_the_text(ledger):
    from scripts import dowjones_pull as DP
    art = {"url": "https://www.wsj.com/finance/stocks/micron-memory-boom-1a2b3c4d",
           "title": "Micron's Memory Boom", "text": WR.clean_text(ARTICLE_TEXT, None),
           "first_seen_utc": DC.now_iso(), "publisher": "wsj",
           "column": "wsj_heard_on_the_street", "origin": "web_reader"}
    art["sha"] = DC.text_sha(art["text"])
    WR.store_article(art)
    lp, cp = ledger / "pred.jsonl", ledger / "claims.jsonl"
    rc = DP.run_claims(art["first_seen_utc"][:10], llm_fn=lambda s, u: GOOD_REPLY,
                       spend_fn=lambda: 0.0, ledger_path=lp, claims_path=cp)
    assert rc["n_claims"] == 1 and rc["forecast_rows_by_source_id"] == {"wsj_heard_on_the_street": 3}
    refused = rc["per_article"][0]["refused"]
    # NVDA: the article never names Nvidia (refused before its invented quote is
    # even looked at); "not a ticker": malformed.
    assert {r["why"].split(":")[0] for r in refused} == {"REFUSED_TICKER_NOT_IN_ARTICLE",
                                                         "REFUSED_TICKER"}
    rows = [json.loads(x) for x in lp.read_text(encoding="utf-8").splitlines()]
    assert {r["specialist"] for r in rows} == {"source:wsj_heard_on_the_street"}
    public = lp.read_text(encoding="utf-8") + cp.read_text(encoding="utf-8")
    assert "high-bandwidth memory prices should keep rising" not in public
    assert "keep rising on HBM pricing" in public
    # a re-run extracts nothing new
    rc2 = DP.run_claims(art["first_seen_utc"][:10], llm_fn=lambda s, u: GOOD_REPLY,
                        spend_fn=lambda: 0.0, ledger_path=lp, claims_path=cp)
    assert rc2["n_articles"] == 0


def test_claims_stop_at_the_cap_and_refuse_when_spend_is_unknown(ledger):
    from scripts import dowjones_pull as DP
    art = {"url": "https://www.wsj.com/a-1a2b3c4d", "title": "t", "text": "x " * 400,
           "first_seen_utc": DC.now_iso(), "publisher": "wsj", "origin": "web_reader"}
    WR.store_article(art)
    day = art["first_seen_utc"][:10]
    r = DP.run_claims(day, cap_usd=0.30, llm_fn=lambda s, u: pytest.fail("over cap"),
                      spend_fn=lambda: 0.299)
    assert r["stopped"].startswith("CAP") and r["n_llm_calls"] == 0
    r = DP.run_claims(day, llm_fn=lambda s, u: pytest.fail("unknown"), spend_fn=lambda: None)
    assert r["stopped"].startswith("REFUSED_SPEND_UNKNOWN")


def test_an_archive_article_records_claims_but_writes_no_forecast(ledger):
    seen = datetime.now(timezone.utc)
    art = {"url": "https://www.wsj.com/a", "text": "t", "first_seen_utc": seen.isoformat(),
           "published_utc": (seen - timedelta(days=90)).isoformat(), "column": "wsj_other"}
    claims = [{"ticker": "MU", "direction": "up", "horizon_days_stated": 63,
               "magnitude_bucket": "unstated", "quote": "q", "paraphrase": "p"}]
    r = DC.write_forecasts(art, claims, ledger_path=ledger / "p.jsonl",
                           claims_path=ledger / "c.jsonl")
    assert r["status"] == "ARCHIVE_NO_FORECAST" and not (ledger / "p.jsonl").exists()


def test_column_of_names_the_columns():
    assert DC.column_of("https://www.wsj.com/finance/x-1a2b3c4d", "", "Heard on the Street") \
        == "wsj_heard_on_the_street"
    assert DC.column_of("https://www.barrons.com/articles/buy-grainger-stock-0b591a70") \
        == "barrons_stock_picks"
    assert DC.column_of("https://www.marketwatch.com/investing/stock/mu/analystestimates") \
        == "mw_analyst_estimates"
    assert DC.column_of("https://www.wsj.com/world/x") == "wsj_other"


# ───────────────────────────────── feeds ────────────────────────────────────

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><guid isPermaLink="false">WP-1</guid><title>Micron rises</title>
<link>https://www.marketwatch.com/story/a</link><description>d</description>
<pubDate>Sat, 26 Sep 2026 13:35:00 GMT</pubDate></item>
<item><guid isPermaLink="false">WP-1</guid><title>dup</title><link>x</link>
<pubDate>Sat, 26 Sep 2026 13:35:00 GMT</pubDate></item></channel></rss>"""
HTML = b"<!DOCTYPE html><html><head><title>wsj</title></head><body>Please enable JS and disable any ad blocker</body></html>"


def test_feed_refuses_html_before_the_parser(monkeypatch, tmp_path):
    from scripts import news_pull as NP
    monkeypatch.setattr(C, "DATA_DIR", tmp_path)
    assert DF.looks_like_xml(RSS) and not DF.looks_like_xml(HTML)
    monkeypatch.setattr(NP, "_http_get", lambda url, headers=None, timeout=45.0: HTML)
    r = DF.pull_feeds(("mw_topstories",), paced=False)
    f = r["per_feed"][0]
    assert f["received"] == 0 and any("REFUSED_NON_XML" in x for x in f["failures"])


def test_feed_dedupes_by_guid_and_stamps_first_seen(monkeypatch, tmp_path):
    from scripts import news_pull as NP
    monkeypatch.setattr(C, "DATA_DIR", tmp_path)
    monkeypatch.setattr(NP, "_http_get", lambda url, headers=None, timeout=45.0: RSS)
    r = DF.pull_feeds(("mw_topstories",), paced=False)
    assert r["per_feed"][0]["new"] == 1 and r["per_feed"][0]["dupes"] == 1
    r2 = DF.pull_feeds(("mw_topstories",), paced=False)
    assert r2["per_feed"][0]["new"] == 0
    row = json.loads(next((tmp_path / "optimus" / "news_corpus" / "mw_topstories")
                          .glob("*.jsonl")).read_text(encoding="utf-8").splitlines()[0])
    assert row["raw_id"] == "WP-1" and row["published_utc"] == "2026-09-26T13:35:00+00:00"
    assert row["first_seen_utc"] >= row["published_utc"]


def test_the_ten_feeds_are_pullable_registry_rows():
    from backend.services import news_registry as NR
    pull = {s.id for s in NR.pullable()}
    assert set(DF.FEED_IDS) <= pull
    for sid in ("dj_reader_wsj", "dj_digest_inbox"):
        s = NR.get(sid)
        assert not s.implemented and s.implemented_note and sid not in pull


# ────────────────────────────── the paste inbox ─────────────────────────────

PASTE_1 = """=== https://www.barrons.com/articles/buy-grainger-stock-recovery-us-manufacturing-0b591a70 | 2026-09-24 | Barron's
Buy Grainger Stock. The Recovery in U.S. Manufacturing Is Coming.
By Al Root
Grainger shares have lagged, but a manufacturing recovery should lift the stock 20% over the next year, making it a buy for patient investors.
The distributor has pricing power and its online business keeps gaining share from smaller rivals across the country.
"""
PASTE_2 = """Heard on the Street
The Wall Street Journal
DraftKings Investors Should Brace for a Rough Quarter
Sept. 25, 2026 6:00 am ET
DraftKings faces rising state taxes and a slower sports calendar, and its shares look likely to underperform over the coming quarter as margins come under pressure.
Competition from prediction markets adds to the pressure on the company's core business in several large states.
"""


def test_two_pasted_entries_ingest_once_with_ingest_time_as_first_seen(ledger):
    inbox = ledger / "digest_inbox"
    DI.ensure_inbox(inbox)
    (inbox / "DIGEST.md").write_text(DI.DIGEST_HEADER + PASTE_1, encoding="utf-8")
    (inbox / "hots_dkng.txt").write_text(PASTE_2, encoding="utf-8")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    r = DI.ingest(inbox, now_utc=now)
    assert r["n_new"] == 2 and r["n_duplicate"] == 0
    by = {e["file"]: e for e in r["entries"]}
    assert by["DIGEST.md"]["column"] == "barrons_stock_picks"
    assert by["DIGEST.md"]["published_utc"].startswith("2026-09-24")
    assert by["hots_dkng.txt"]["column"] == "wsj_heard_on_the_street"
    assert by["hots_dkng.txt"]["published_utc"] == "2026-09-25T10:00:00+00:00"
    stored = [json.loads(p.read_text(encoding="utf-8"))
              for p in (ledger / "news_corpus" / "dowjones").glob("*/*/*.json")]
    assert {s["first_seen_utc"] for s in stored} == {now}
    assert {s["origin"] for s in stored} == {"pasted_by_operator"}
    r2 = DI.ingest(inbox)
    assert r2["n_new"] == 0 and r2["n_duplicate"] == 2


def test_reading_list_derives_its_days_and_names():
    today = date.today()
    md = DI.build_reading_list(today, {"personal": ["QUBT"], "competition": ["MU"],
                                       "probe": ["TSM"]})
    days = [d for d in DI.trading_days_back(today, 8)]
    assert 35 <= len(days) <= 40 and all(d.weekday() < 5 for d in days)
    assert f"https://www.wsj.com/news/archive/{days[0]:%Y/%m/%d}" in md
    for t in ("QUBT", "MU", "TSM"):
        assert f"/{t.lower()}/analystestimates" in md and f"quotes/{t}/research-ratings" in md
    assert md.startswith("# Weekend reading list") and "How to paste" in md


def test_labor_day_is_not_a_trading_day():
    y = date.today().year
    ld = DI._nth_weekday(y, 9, 0, 1)
    assert ld in DI.nyse_holidays(y)


# ─────────────────────────────── gitignore ──────────────────────────────────

@pytest.mark.parametrize("path,ignored", [
    ("backend/data/optimus/news_corpus/dowjones/wsj/2026-01-01/abc.json", True),
    ("backend/data/optimus/digest_inbox/DIGEST.md", True),
    ("backend/data/optimus/digest_inbox/pasted.txt", True),
    ("backend/data/optimus/HANDOFF_PC", True),
    ("backend/data/optimus/digest_inbox/README.md", False),
    ("backend/data/optimus/dowjones/feeds_2026-01-01.json", False),
])
def test_full_text_is_gitignored_and_receipts_are_not(path, ignored):
    r = subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO)
    assert (r.returncode == 0) is ignored


def test_one_article_is_one_view_per_ticker_and_the_ticker_must_be_named():
    text = ("Micron (MU) shares should keep rising as memory prices climb. "
            "We think Micron can rise further next year. HP looks cheap too.")
    raw = [{"ticker": "MU", "direction": "up", "quote": "Micron (MU) shares should keep rising",
            "paraphrase": "a"},
           {"ticker": "MU", "direction": "up", "quote": "We think Micron can rise further",
            "paraphrase": "b"},
           {"ticker": "HP", "direction": "up", "quote": "HP looks cheap too", "paraphrase": "c"},
           {"ticker": "MU", "direction": "none", "quote": "memory prices climb",
            "paraphrase": "d"}]
    kept, refused = DC.validate_claims(raw, text, allowed_tickers={"MU"})
    assert [(c["ticker"], c["direction"]) for c in kept] == [("MU", "up"), ("MU", "none")]
    whys = sorted(r["why"].split(":")[0] for r in refused)
    assert whys == ["REFUSED_DUPLICATE_VIEW", "REFUSED_TICKER_NOT_IN_ARTICLE"]
    assert "MU" in DC.article_tickers("Micron (MU) rose.")


def test_a_quote_not_in_the_article_is_refused():
    kept, refused = DC.validate_claims(
        [{"ticker": "MU", "direction": "up", "quote": "Micron will triple by Friday",
          "paraphrase": "x"}], "Micron (MU) reported results.", allowed_tickers={"MU"})
    assert not kept and refused[0]["why"] == "REFUSED_QUOTE_NOT_IN_ARTICLE"


def test_a_description_of_a_past_move_is_not_a_forecast():
    assert DC.backward_only("Dell stock has risen sharply this year",
                            "The article says PC makers' stocks, including Dell, have risen sharply.")
    assert not DC.backward_only("Micron shares have risen, and they should keep rising",
                                "Micron should keep rising")
    kept, refused = DC.validate_claims(
        [{"ticker": "DELL", "direction": "up", "quote": "Dell stock has risen sharply this year",
          "paraphrase": "Dell shares have risen sharply this year."}],
        "Dell stock has risen sharply this year.", allowed_tickers={"DELL"})
    assert not kept and refused[0]["why"].startswith("REFUSED_BACKWARD_LOOKING")


# ═══════════════ Chunk J2: rotation, the archive, the queue ═════════════════

def _listing(title: str, items: list[tuple[str, str]]) -> str:
    """A `snapshot --format ai --urls` page with a Sign Out decoy and links."""
    tree = [f'- rootwebarea "{title}"', '  - link "Sign Out" [ref=s0]']
    urls = ["1. Sign Out -> https://accounts.wsj.com/logout"]
    for i, (text, url) in enumerate(items, 1):
        tree.append(f'  - link "{text}" [ref=e{i}]')
        urls.append(f"{i + 1}. {text} -> {url}")
    return "\n".join(tree) + "\nLinks:\n" + "\n".join(urls) + "\n"


def _body(title: str) -> str:
    return (f"{title}\nBy A Writer\nSept. 24, 2026 5:30 am ET\n"
            + f"{title} -- a paragraph about the company and what may come next. " * 8)


BARRONS_ITEMS = [(f"Barron's pick number {i} looks cheap now",
                  f"https://www.barrons.com/articles/pick-number-{i}-{i}a2b3c4d") for i in (1, 2, 3)]
WSJ_ITEMS = [("Heard on the Street: memory boom has further to run",
              "https://www.wsj.com/finance/stocks/memory-boom-1a2b3c4d")]
LISTINGS = {
    "https://www.barrons.com/market-data/stocks/stock-picks": _listing("Picks", BARRONS_ITEMS),
    "https://www.wsj.com/news/heard-on-the-street": _listing("HOTS", WSJ_ITEMS),
}
MW_PAGE = """MU Analyst Estimates
Micron Technology Inc.
Stock Price Target MU
High\t$250.00
Median\t$195.00
Low\t$120.00
Average\t$198.37
Current Price\t$161.22
Average Recommendation
Overweight
Average Target Price
198.37
Number Of Ratings
38
Next Earnings Date
Dec. 17, 2026
52 Week High 205.10
"""


class MultiStub:
    """openclaw_client with several tabs: each tab has its own current URL;
    listings snapshot from LISTINGS; clicks follow the ref to its URL."""

    def __init__(self, tabs=None, listings=None, pages=None):
        self.calls, self.closed, self.cur, self.n = [], [], {}, 50
        self.listings = listings if listings is not None else LISTINGS
        self.pages = pages or {}
        self._tabs = tabs if tabs is not None else [
            {"tabId": "t13", "url": "https://www.barrons.com/market-data/bonds/x"},
            {"tabId": "t20", "url": "https://www.wsj.com/health/some-story-4aa63e38"},
            {"tabId": "t24", "url": "https://mail.google.com/mail/u/0"},
            {"tabId": "t32", "url": "https://www.marketwatch.com/investing/stock/mu/analystestimates"}]

    def tabs(self, profile_name=None):
        return self._tabs

    def open_from_tab(self, parent, url, profile_name="user"):
        self.n += 1
        tid = f"t{self.n}"
        self.cur[tid] = url
        self.calls.append(("open_from_tab", parent, url, tid))
        return {"new_tab": tid, "url": url, "attached_to": {"pid": 7}}

    def browser(self, verb, *args, profile_name=None, target_id=None, url=None):
        self.calls.append((verb, target_id, args))
        if verb == "navigate":
            self.cur[target_id] = args[0]
        if verb == "snapshot":
            return {"rc": 0, "stdout": self.listings.get(self.cur.get(target_id), "")}
        if verb == "click":
            snap = self.listings.get(self.cur.get(target_id), "")
            parsed = WR.parse_snapshot(snap)
            name = next(n["name"] for n in parsed["nodes"] if n["ref"] == args[0])
            self.cur[target_id] = next(lk["url"] for lk in parsed["links"] if lk["text"] == name)
        if verb == "close":
            self.closed.append(target_id)
        return {"rc": 0, "verb": verb, "stdout": ""}

    def read_text(self, tab, profile_name=None):
        u = self.cur.get(tab)
        self.calls.append(("read_text", tab, u))
        if u in self.pages:
            return {"url": u, "title": "page", "text": self.pages[u]}
        if "analystestimates" in (u or ""):
            t = u.split("/stock/")[1].split("/")[0].upper()
            return {"url": u, "title": f"{t} Analyst Estimates",
                    "text": MW_PAGE.replace("MU", t) + f"\nsalt {t}\n"}
        title = next((x for x, y in BARRONS_ITEMS + WSJ_ITEMS if y == u), f"Story at {u}")
        return {"url": u, "title": title, "text": _body(title)}


def _clock_throttle(path, seed=5, **kw):
    ck = Clock()
    return ck, WR.Throttle(path, now_fn=ck.now, sleep_fn=ck.sleep, seed=seed, **kw)


def test_round_robin_is_one_item_per_lane_per_turn_and_exhausted_lanes_drop():
    from scripts import dowjones_pull as DP
    order = DP.round_robin({"b": [1, 2, 3], "w": [1], "m": ["MU", "DKNG"]})
    assert order == [("b", 1), ("w", 1), ("m", "MU"), ("b", 2), ("m", "DKNG"), ("b", 3)]


def test_run_plan_rotates_sources_under_one_throttle_and_closes_every_tab(ledger):
    from scripts import dowjones_pull as DP
    drv = MultiStub()
    _, th = _clock_throttle(ledger / "thr.log")
    lanes = DP.parse_plan("barrons:stock_picks:3,wsj:heard_on_the_street:5,"
                          "marketwatch:analyst_estimates:MU|DKNG")
    parents = DP.resolve_parent_tabs(["barrons", "wsj", "marketwatch"], drv.tabs())
    rc = DP.run_plan(lanes, parents=parents, driver=drv, throttle=th, stored={})
    reads = [(o["lane"].split(":")[0], o.get("ticker") or o["url"])
             for o in rc["order"] if o["turn"] > 0 and o["ok"]]
    assert [r[0] for r in reads] == ["barrons", "wsj", "marketwatch", "barrons",
                                     "marketwatch", "barrons"]
    assert reads[2][1] == "MU" and reads[4][1] == "DKNG"
    # one tab per lane, each opened from its OWN host's parent, all closed
    opens = [c for c in drv.calls if c[0] == "open_from_tab"]
    assert [c[1] for c in opens] == ["t13", "t20", "t32"]
    assert sorted(drv.closed) == sorted(c[3] for c in opens)
    assert all(rc["tabs_closed"].values()) and len(rc["tabs_closed"]) == 3
    assert rc["per_source"] == {"barrons": {"articles": 3, "refusals": 0,
                                            "chars": rc["per_source"]["barrons"]["chars"]},
                                "wsj": {"articles": 1, "refusals": 0,
                                        "chars": rc["per_source"]["wsj"]["chars"]},
                                "marketwatch": {"articles": 2, "refusals": 0,
                                                "chars": rc["per_source"]["marketwatch"]["chars"]}}
    # every page load in the run -- listings included -- is 20-90 s from the last
    assert all(20 <= g <= 90 for g in rc["seconds_between_page_loads"])
    assert rc["footprint"]["verdict"] == "HUMAN_PACE_OK" and rc["footprint"]["scroll_share"] == 1.0
    assert rc["stopped"] is None and not WR.lock_path().exists()
    # the MU page was already loaded by open_from_tab: read in place, not loaded twice
    mw_tab = opens[2][3]
    assert sum(1 for c in drv.calls if c[0] == "navigate" and c[1] == mw_tab) == 1


def test_run_plan_skips_stored_urls_and_a_failed_tab_drops_only_its_lane(ledger):
    from scripts import dowjones_pull as DP
    drv = MultiStub()
    orig = drv.browser

    def flaky(verb, *args, profile_name=None, target_id=None, url=None):
        if verb == "press" and drv.cur.get(target_id, "").startswith("https://www.wsj.com/"):
            return {"rc": 0, "left_allowed_hosts": True, "tab_url_after": "https://evil.example"}
        return orig(verb, *args, profile_name=profile_name, target_id=target_id, url=url)
    drv.browser = flaky
    _, th = _clock_throttle(ledger / "thr.log")
    lanes = DP.parse_plan("barrons:stock_picks:3,wsj:heard_on_the_street:5")
    stored = {WR.norm_url(BARRONS_ITEMS[0][1]): {"2026-01-01"}}
    rc = DP.run_plan(lanes, parents=DP.resolve_parent_tabs(["barrons", "wsj"], drv.tabs()),
                     driver=drv, throttle=th, stored=stored)
    assert rc["lanes"]["barrons:stock_picks"]["skipped_already_stored"] == 1
    assert len(rc["lanes"]["barrons:stock_picks"]["articles"]) == 2
    assert rc["lanes"]["wsj:heard_on_the_street"]["dropped"].startswith("ReaderRefused: REFUSED_LEFT_HOSTS")
    assert len(drv.closed) == 2


def test_parent_tabs_are_resolved_by_host_never_hardcoded():
    from scripts import dowjones_pull as DP
    tabs = [{"tabId": "t38", "url": "https://www.marketwatch.com/x"},
            {"tabId": "t32", "url": "https://www.marketwatch.com/investing/stock/mu"},
            {"tabId": "t20", "url": "https://www.wsj.com/a-1a2b3c4d"},
            {"tabId": "t5", "url": "https://railway.com/dashboard"}]
    got = DP.resolve_parent_tabs(["marketwatch", "wsj", "barrons"], tabs)
    assert got["marketwatch"]["tab"] == "t32"          # the OLDEST MarketWatch tab
    assert got["wsj"]["how"] == "by_host:wsj.com"
    assert got["barrons"]["how"].startswith("borrowed") and got["barrons"]["tab"] == "t20"
    assert DP.resolve_parent_tabs(["wsj"], tabs, explicit={"wsj": "t20"})["wsj"]["how"] == "explicit"
    with pytest.raises(WR.ReaderRefused, match="PARENT_TAB"):
        DP.resolve_parent_tabs(["wsj"], tabs, explicit={"wsj": "t5"})
    with pytest.raises(WR.ReaderRefused, match="NO_PARENT_TAB"):
        DP.resolve_parent_tabs(["wsj"], [tabs[3]])
    # a tab this process opened is never a parent
    assert DP.resolve_parent_tabs(["marketwatch"], tabs,
                                  exclude={"t32"})["marketwatch"]["tab"] == "t38"


def test_plan_parsing_refuses_unknown_sections_and_duplicates():
    from scripts import dowjones_pull as DP
    lanes = DP.parse_plan("wsj:heard_on_the_street:4,marketwatch:analyst_estimates:mu|dkng")
    assert lanes[0]["max"] == 4 and lanes[1]["tickers"] == ["MU", "DKNG"]
    for bad in ("wsj:opinion:3", "wsj:heard_on_the_street:3,wsj:heard_on_the_street:2",
                "barrons:stock_picks:many", ""):
        with pytest.raises(WR.ReaderRefused):
            DP.parse_plan(bad)


def test_archive_days_skip_weekends_and_holidays_newest_first():
    from scripts import dowjones_pull as DP
    today = date.today()
    start = today - timedelta(days=30)
    days = DP.archive_days(f"{start.isoformat()}..{(today - timedelta(days=1)).isoformat()}",
                           today=today)
    assert days == sorted(days, reverse=True)
    assert all(d.weekday() < 5 for d in days) and 18 <= len(days) <= 23
    # a Saturday alone is no trading day
    sat = today - timedelta(days=(today.weekday() - 5) % 7 or 7)
    assert DP.archive_days(sat.isoformat(), today=today) == []
    # Labor Day of this year is skipped (derived, not a literal)
    from backend.services import digest_inbox as DI
    ld = DI._nth_weekday(today.year, 9, 0, 1)
    if ld < today:
        assert DP.archive_days(ld.isoformat(), today=today) == []
    assert DP.archive_url("wsj", date(2026, 9, 2)) == "https://www.wsj.com/news/archive/2026/09/02"
    with pytest.raises(WR.ReaderRefused, match="FUTURE"):
        DP.archive_days(today.isoformat(), today=today)
    with pytest.raises(WR.ReaderRefused, match="RANGE"):
        DP.archive_days(f"{today - timedelta(days=2)}..{today - timedelta(days=5)}", today=today)


def test_run_archive_reads_newest_day_first_caps_per_day_and_resumes(ledger):
    from scripts import dowjones_pull as DP
    d1, d0 = date(2026, 9, 25), date(2026, 9, 24)
    items = {d: [(f"Story {d.day} number {i} about a company",
                  f"https://www.wsj.com/business/story-{d.day}-{i}-{i}{d.day:02d}c3d4e")
                 for i in range(1, 5)] for d in (d0, d1)}
    listings = {DP.archive_url("wsj", d): _listing(f"Archive {d}", items[d]) for d in (d0, d1)}
    drv = MultiStub(listings=listings)
    _, th = _clock_throttle(ledger / "thr.log")
    stored = {WR.norm_url(items[d1][0][1]): {"2026-09-26"}}
    rc = DP.run_archive([d1, d0], parent_tab="t20", max_per_day=2, driver=drv, throttle=th,
                        stored=stored)
    assert rc["per_day"]["2026-09-25"] == {"url": DP.archive_url("wsj", d1), "links_found": 4,
                                           "already_stored": 1, "read": 1, "refusals": []}
    assert rc["per_day"]["2026-09-24"]["read"] == 2 and rc["complete"]
    days_in_order = [o["day"] for o in rc["order"]]
    assert days_in_order == sorted(days_in_order, reverse=True)
    assert rc["tab_closed"] and rc["sources"] == ["wsj"] and "barrons" in rc["not_built"]
    # resume: what was read is now on disk (plus the one pre-stored URL) -> the
    # same run loads only the day pages
    on_disk = WR.stored_urls()
    assert len(on_disk) == 3
    drv2 = MultiStub(listings=listings)
    rc2 = DP.run_archive([d1, d0], parent_tab="t20", max_per_day=2, driver=drv2, throttle=th,
                         stored={**on_disk, WR.norm_url(items[d1][0][1]): {"2026-09-26"}})
    assert rc2["n_articles"] == 0 and rc2["complete"]
    assert not [c for c in drv2.calls if c[0] == "read_text"]


def test_queue_resume_skips_done_lines_and_reruns_failed_or_edited_ones(tmp_path):
    from scripts import dowjones_pull as DP
    q = tmp_path / "QUEUE.txt"
    q.write_text("# a comment\n--plan \"wsj:heard_on_the_street:2\"\n\n--archive 2026-09-22\n"
                 "--claims\n", encoding="utf-8")
    calls, fail = [], {"--archive"}

    def fake_main(argv):
        calls.append(argv)
        return 2 if argv[0] in fail else 0
    r1 = DP.run_queue(q, inherit=["--handoff"], main_fn=fake_main)
    assert [ln["status"] for ln in r1["lines"]] == ["DONE", "FAILED_WILL_RETRY", "DONE"]
    assert calls[0] == ["--plan", "wsj:heard_on_the_street:2", "--handoff"]
    assert len(list(DP.queue_done_dir(q).glob("*.done"))) == 2
    calls.clear()
    fail.clear()
    r2 = DP.run_queue(q, inherit=["--handoff"], main_fn=fake_main)
    assert [ln["status"] for ln in r2["lines"]] == ["SKIPPED_DONE", "DONE", "SKIPPED_DONE"]
    assert calls == [["--archive", "2026-09-22", "--handoff"]]
    # an EDITED line is a new line: it runs again
    q.write_text(q.read_text(encoding="utf-8").replace("--claims", "--claims --claims-day 2026-09-25"),
                 encoding="utf-8")
    calls.clear()
    DP.run_queue(q, main_fn=fake_main)
    assert calls == [["--claims", "--claims-day", "2026-09-25"]]


def test_build_queue_text_carries_the_books_and_the_archive():
    from scripts import dowjones_pull as DP
    names = {"personal": ["QUBT", "DKNG"], "competition": ["MU", "DKNG"],
             "probe": [f"P{i:02d}" for i in range(60)]}
    txt = DP.build_queue_text(date(2026, 9, 26), names=names, cap=40)
    plan = next(ln for ln in txt.splitlines() if ln.startswith("--plan"))
    ticks = plan.split("analyst_estimates:")[1].rstrip('"').split("|")
    assert ticks[:3] == ["QUBT", "DKNG", "MU"] and len(ticks) == 40
    assert "barrons:stock_picks:10" in plan and "barrons:big_money_poll:3" in plan
    assert "wsj:heard_on_the_street:10" in plan
    assert "--archive 2026-09-22..2026-09-25" in txt
    assert txt.rstrip().splitlines()[-1] == "--claims --claims-since 2026-09-26"
    import shlex
    assert DP.parse_plan(shlex.split(plan)[1])[3]["tickers"] == ticks


def test_the_hourly_cap_is_waited_out_on_a_long_run_but_the_day_cap_refuses(tmp_path):
    ck, th = _clock_throttle(tmp_path / "t.log", min_delay_s=20, max_delay_s=20,
                             max_per_hour=3, max_per_day=5, wait_on_hour_cap=True)
    for _ in range(4):
        th.acquire(host="wsj.com")
    assert len(th.hour_cap_waits) == 1 and th.hour_cap_waits[0] > 3000
    th.acquire(host="wsj.com")
    with pytest.raises(WR.ReaderRefused, match="THROTTLE_DAY"):
        th.acquire(host="wsj.com")


# ────────────────── structured rows: MarketWatch, Big Money ─────────────────

def test_mw_analyst_snapshot_parses_the_consensus_fields():
    row = DC.parse_mw_analyst(MW_PAGE)
    assert row["consensus_rating"] == "Overweight"
    assert (row["target_mean"], row["target_high"], row["target_low"],
            row["target_median"]) == (198.37, 250.0, 120.0, 195.0)
    assert row["n_analysts"] == 38 and row["next_earnings_date"] == "Dec. 17, 2026"
    assert row["current_price"] == 161.22 and row["fields_found"] == 8
    # the LIVE layout (MarketWatch, 2026-09-26): tab-separated, "STOCK PRICE
    # TARGETS", and the earnings date as a sentence
    live = ("SNAPSHOT\nAverage Recommendation\tBuy\nAverage Target Price\t1,575.88\n"
            "Number Of Ratings\t57\nFY Report Date\t8/2026\nLast Quarter's Earnings\t25.11\n"
            "Current Quarter's Estimate\t31.52\nCurrent Year's Estimate\t73.77\n"
            "STOCK PRICE TARGETS\nHigh\t$2,200.00\nMedian\t$1,600.00\nLow\t$361.00\n"
            "Average\t$1,575.88\nCurrent Price\t$1,080.53\nYEARLY NUMBERS\n"
            "MU WILL REPORT 2026 EARNINGS ON 09/30/2026\n2025\t2026\nHigh\t8.29\t77.38\n")
    lr = DC.parse_mw_analyst(live)
    assert (lr["consensus_rating"], lr["target_mean"], lr["target_high"], lr["target_low"],
            lr["n_analysts"], lr["next_earnings_date"]) == ("Buy", 1575.88, 2200.0, 361.0, 57,
                                                            "09/30/2026")
    assert lr["eps_current_quarter_est"] == 31.52 and lr["fy_report_date"] == "8/2026"
    # the 52-week High is not a target; a page with nothing is THIN, never zeros
    assert DC.parse_mw_analyst("52 Week High 205.10\nnothing else")["target_high"] is None
    assert DC.parse_mw_analyst("")["fields_found"] == 0


def test_mw_snapshot_row_is_written_once_with_first_seen_and_no_llm(ledger):
    from scripts import dowjones_pull as DP
    day = datetime.now(timezone.utc).date().isoformat()
    art = {"url": "https://www.marketwatch.com/investing/stock/mu/analystestimates",
           "text": MW_PAGE, "first_seen_utc": f"{day}T01:02:03+00:00", "sha": "abc123",
           "column": "mw_analyst_estimates", "publisher": "marketwatch"}
    WR.store_article(dict(art), root=ledger / "news_corpus" / "dowjones")

    def no_llm(system, user):
        raise AssertionError("an analyst estimates page must not reach the LLM")
    r = DP.run_claims(day, llm_fn=no_llm, spend_fn=lambda: 0.0,
                      ledger_path=ledger / "p.jsonl", claims_path=ledger / "c.jsonl",
                      done_path=ledger / "done.txt")
    assert r["mw_analyst_snapshot"]["tickers"] == ["MU"] and r["n_llm_calls"] == 0
    rows = [json.loads(x) for x in DC.structured_path("mw_analyst_snapshot")
            .read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["kind"] == "mw_analyst_snapshot"
    assert rows[0]["first_seen_utc"] == art["first_seen_utc"] and rows[0]["target_mean"] == 198.37
    assert DC.write_mw_snapshot(art)["n_rows_written"] == 0          # idempotent
    # the structured file is under the gitignored corpus
    assert "news_corpus" in str(DC.structured_path("mw_analyst_snapshot"))


BIG_MONEY = """Barron's Big Money Poll: The Bulls Are Back
By A Writer
Oct. 24, 2026 5:00 am ET
Some 58% of the managers are bullish on the stock market, while 14% are bearish and the rest neutral.
The S&P 500 closed at 6,641 on Friday.
On average, the bulls expect the S&P 500 to finish the year at 6,900 and to reach 7,250 by the middle of 2027.
The bears see the index at 5,800 by the end of 2027.
Nvidia (ticker: NVDA) is the managers' favorite stock, and Micron (ticker: MU) is second.
"""


def test_big_money_poll_becomes_index_level_rows():
    p = DC.parse_big_money(BIG_MONEY, seen_day="2026-10-24")
    assert (p["bullish_pct"], p["bearish_pct"], p["majority_direction"]) == (58, 14, "up")
    got = {(f["level"], f["horizon_label"], f["horizon_end"]) for f in p["spx_forecasts"]}
    assert got == {(6900.0, "end-2026", "2026-12-31"), (7250.0, "mid-2027", "2027-06-30")}
    # "closed at 6,641" is a level, not a forecast; the bears' sentence names no S&P


def test_big_money_rows_are_written_locally_and_barrons_tickers_are_read(ledger):
    art = {"url": "https://www.barrons.com/articles/big-money-poll-bulls-a54d307f",
           "text": BIG_MONEY, "first_seen_utc": "2026-10-24T12:00:00+00:00", "sha": "bm1",
           "published_utc": "2026-10-24T09:00:00+00:00", "column": "barrons_big_money_poll"}
    r = DC.write_big_money_rows(art)
    assert r["status"] == "OK" and r["n_rows_written"] == 3 and r["n_spx_levels"] == 2
    rows = [json.loads(x) for x in DC.structured_path("barrons_big_money_poll")
            .read_text(encoding="utf-8").splitlines()]
    d = next(x for x in rows if x["forecast"] == "direction")
    assert d["direction"] == "up" and d["horizon_label"] == "end-2026" and d["index"] == "SPX"
    assert DC.write_big_money_rows(art)["n_rows_written"] == 0
    assert DC.barrons_named_tickers(BIG_MONEY) == ["NVDA", "MU"]
    assert DC.barrons_named_tickers("Brookfield (ticker: BN) and (tickers: GOOGL, GOOG)") == [
        "BN", "GOOGL", "GOOG"]
    assert "BN" in DC.article_tickers("Brookfield (ticker: BN) looks cheap.")


def test_a_url_with_a_shell_metacharacter_loses_only_its_tracking_query(tmp_path):
    # 2026-09-26: "&mod=" ended the openclaw .cmd command line; both Big Money reads failed
    u = ("https://www.barrons.com/articles/big-money-poll-bulls-a54d307f"
         "?refsec=big-money-poll&mod=topics_big-money-poll")
    assert WR.shell_safe_url(u) == "https://www.barrons.com/articles/big-money-poll-bulls-a54d307f"
    assert WR.shell_safe_url("https://www.wsj.com/a-1a2b3c4d?mod=hots") == \
        "https://www.wsj.com/a-1a2b3c4d?mod=hots"
    drv = MultiStub()
    ck, th = _clock_throttle(tmp_path / "t.log")
    rd = WR.Reader(profile="user", tab="t99", driver=drv, lock=False, throttle=th)
    rd.navigate(u)
    nav = [c for c in drv.calls if c[0] == "navigate"][0]
    assert "&" not in nav[2][0] and rd.log[-1]["url_shown"] == u


class FakeOC:
    """`profiles` / `_run` / `tabs` for `ensure_attached`; never the real CLI."""

    def __init__(self, start_works=True, start_out="", tabs=None):
        self.state, self.start_works, self.start_out = "stopped", start_works, start_out
        self.runs, self._tabs = [], tabs if tabs is not None else [{"tabId": "t1", "url": "u"}]

    def profiles(self):
        return [{"name": "user", "state": self.state}]

    def _run(self, args, timeout=180.0):
        self.runs.append(args)
        if args[-1] == "start" and self.start_works:
            self.state = "running"
        return subprocess.CompletedProcess(args, 0, self.start_out, "")

    def tabs(self, profile_name=None):
        return self._tabs if self.state == "running" else []


@pytest.fixture
def fast_reattach(monkeypatch):
    monkeypatch.setattr(WR, "REATTACH_WAIT_S", 4.0)
    monkeypatch.setattr(WR, "REATTACH_POLL_S", 1.0)
    t = [0.0]

    def sleep(s):
        t[0] += s
    return {"sleep_fn": sleep, "clock": lambda: t[0]}


def test_a_stopped_profile_is_reattached_with_start_and_logged(fast_reattach):
    oc, log = FakeOC(), []
    r = WR.ensure_attached("user", oc=oc, log=log, **fast_reattach)
    assert r["reattached"] and oc.runs == [["browser", "--browser-profile", "user", "start"]]
    assert len(log) == 1 and log[0]["ok"] and log[0]["from_state"] == "stopped"
    # already running -> nothing is started
    assert WR.ensure_attached("user", oc=oc, log=log, **fast_reattach) == {
        "reattached": False, "state": "running"}
    assert len(oc.runs) == 1


def test_reattach_refuses_after_two_failed_starts(fast_reattach):
    oc, log = FakeOC(start_works=False), []
    with pytest.raises(WR.ReaderRefused, match="REATTACH_FAILED"):
        WR.ensure_attached("user", oc=oc, log=log, **fast_reattach)
    assert len(oc.runs) == 2 and [x["ok"] for x in log] == [False, False]
    # running but NO tabs is not attached either
    oc2 = FakeOC(tabs=[])
    with pytest.raises(WR.ReaderRefused, match="REATTACH_FAILED"):
        WR.ensure_attached("user", oc=oc2, log=[], **fast_reattach)


def test_a_gateway_timeout_refuses_by_name_and_never_restarts_the_gateway(fast_reattach):
    oc = FakeOC(start_works=False, start_out="Error: gateway timeout after 45000ms")
    with pytest.raises(WR.ReaderRefused, match="GATEWAY_DOWN"):
        WR.ensure_attached("user", oc=oc, log=[], **fast_reattach)
    assert oc.runs == [["browser", "--browser-profile", "user", "start"]]
    assert not any("gateway" in a for r in oc.runs for a in r)
    assert not WR.is_detached("OpenClawRefused: gateway timeout after 45000ms; is 'stopped'")
    assert WR.is_detached("REFUSED_BROWSER_PROFILE_UNAVAILABLE: operator profile 'user' is 'stopped'")


def test_a_stopped_user_profile_is_reattached_before_any_tabs_call(ledger, monkeypatch, capsys):
    from scripts import dowjones_pull as DP
    monkeypatch.setattr(C, "DOWJONES_HANDOFF_FILE", ledger / "HANDOFF_PC")
    (ledger / "HANDOFF_PC").write_text("x")
    monkeypatch.setattr(WR, "REATTACH_WAIT_S", 0.0)
    fake = FakeOC(start_works=False)
    monkeypatch.setattr(OC, "profiles", fake.profiles)
    monkeypatch.setattr(OC, "_run", fake._run)       # NEVER the live CLI in a test

    def no_tabs(**k):
        raise AssertionError("tabs must not be called on a stopped operator profile")
    monkeypatch.setattr(OC, "tabs", no_tabs)
    assert DP.main(["--handoff", "--plan", "wsj:heard_on_the_street:2"]) == 2
    out = capsys.readouterr().out
    assert "REFUSED_REATTACH_FAILED" in out and "ToU 9.4.1" in out
    assert [r[-1] for r in fake.runs] == ["start", "start"]
    rc = json.loads(sorted((ledger / "dowjones").glob("plan_*.json"))[-1].read_text(encoding="utf-8"))
    assert rc["n_articles"] == 0 and "REATTACH_FAILED" in rc["refused"]


class DetachingStub(MultiStub):
    """Drops to `stopped` on the Nth read; `start` re-attaches and RENUMBERS
    every tab id, as a real re-attach does."""

    def __init__(self, drop_at=3, **kw):
        super().__init__(**kw)
        self.state, self.reads, self.drop_at, self.runs = "running", 0, drop_at, []
        self._OPENED_TABS = set()

    def profiles(self):
        return [{"name": "user", "state": self.state}]

    def _run(self, args, timeout=180.0):
        self.runs.append(args)
        if args[-1] == "start":
            self.state = "running"
            shift = lambda t: f"t{int(t[1:]) + 100}"   # noqa: E731
            self._tabs = [dict(t, tabId=shift(t["tabId"])) for t in self._tabs]
            self.cur = {shift(k): v for k, v in self.cur.items()}
        return subprocess.CompletedProcess(args, 0, "", "")

    def tabs(self, profile_name=None):
        return self._tabs + [{"tabId": k, "url": v} for k, v in self.cur.items()]

    def open_from_tab(self, parent, url, profile_name="user"):
        r = super().open_from_tab(parent, url, profile_name)
        self._OPENED_TABS.add(r["new_tab"])
        return r

    def _check(self, target_id):
        if self.state != "running":
            raise OC.OpenClawRefused("REFUSED_BROWSER_PROFILE_UNAVAILABLE: operator profile "
                                     "'user' is 'stopped', not running.")
        if target_id and target_id not in self.cur:
            raise OC.OpenClawRefused(f"REFUSED_OPERATOR_TAB_MISSING: no tab {target_id!r}")

    def browser(self, verb, *args, profile_name=None, target_id=None, url=None):
        self._check(target_id)
        return super().browser(verb, *args, profile_name=profile_name, target_id=target_id,
                               url=url)

    def read_text(self, tab, profile_name=None):
        self.reads += 1
        if self.reads == self.drop_at:
            self.state = "stopped"
        self._check(tab)
        return super().read_text(tab, profile_name)


def test_run_plan_reattaches_mid_run_remaps_tabs_and_finishes(ledger, fast_reattach, monkeypatch):
    from scripts import dowjones_pull as DP
    monkeypatch.setattr(WR, "REATTACH_WAIT_S", 0.0)
    drv = DetachingStub(drop_at=3)
    _, th = _clock_throttle(ledger / "thr.log")
    lanes = DP.parse_plan("barrons:stock_picks:3,wsj:heard_on_the_street:5,"
                          "marketwatch:analyst_estimates:MU|DKNG")
    parents = DP.resolve_parent_tabs(["barrons", "wsj", "marketwatch"], drv.tabs())
    rc = DP.run_plan(lanes, parents=parents, driver=drv, throttle=th, stored={})
    assert rc["reattaches"] == 1 and rc["stopped"] is None
    assert rc["reattach_log"][0]["ok"] and [r[-1] for r in drv.runs] == ["start"]
    assert rc["per_source"]["barrons"]["articles"] == 3
    assert rc["per_source"]["wsj"]["articles"] == 1
    assert rc["per_source"]["marketwatch"]["articles"] == 2
    # every tab id moved by +100; the run closed the NEW ids and re-resolved parents
    remap = rc["tab_remaps"][0]["remap"]
    assert all(v == f"t{int(k[1:]) + 100}" for k, v in remap.items())
    assert sorted(drv.closed) == sorted(remap.values()) and all(rc["tabs_closed"].values())
    assert rc["parent_tabs_final"] == {"barrons": "t113", "wsj": "t120", "marketwatch": "t132"}
    assert any(o.get("why", "").startswith("DETACHED") for o in rc["order"])


def test_a_gateway_that_cannot_clean_up_its_mcp_subprocess_refuses_at_once(fast_reattach):
    # the live answer on 2026-09-26 after the MCP subprocess died: retrying `start` is futile
    oc = FakeOC(start_works=False, start_out="GatewayClientRequestError: Error: Chrome MCP "
                                             "subprocess tree cleanup could not be verified.")
    log: list = []
    with pytest.raises(WR.ReaderRefused, match="GATEWAY_NEEDS_RESTART"):
        WR.ensure_attached("user", oc=oc, log=log, **fast_reattach)
    assert len(oc.runs) == 1 and log[0]["ok"] is False and "cleanup" in log[0]["start_out"]
