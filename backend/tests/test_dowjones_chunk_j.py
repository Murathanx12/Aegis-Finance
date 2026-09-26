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
