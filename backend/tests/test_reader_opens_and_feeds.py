"""2026-09-30 night: what the reader opens, the Fed by feed only, and one
report per checkout frame.

* `dowjones/WHAT_THE_READER_OPENS.md` is GENERATED from the config the reader
  runs with (never by hand): every allowlisted host sits in a kind, the money /
  checkout / mail classes are listed, and a central bank is never in the browser;
* federalreserve.gov left the visible browser; its feed items' full text is read
  by plain HTTP into `policy_texts`;
* a checkout frame held by another worker's tab is reported ONCE, and blamed on
  the page that carries it.

Offline: fakes only. No literal calendar dates.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend import config as _config
from backend.services import official_sources as OS
from backend.services import reader_report as RR
from backend.services import web_reader as WR
from backend.tests.test_reader_money_hosts import _pool, ledger  # noqa: F401 -- fixture
from scripts import reader_pool as RP

NOW = datetime.now(timezone.utc).replace(microsecond=0)


# ─────────────────────────── the owner's check list ──────────────────────────

def test_every_allowlisted_host_is_in_a_kind_and_none_is_unclassified():
    w = RR.what_the_reader_opens(NOW)
    assert w["browser"]["unclassified"] == []
    listed = [h["host"] for k in w["browser"]["kinds"] for h in k["browser_hosts"]]
    assert sorted(listed) == sorted(set(WR.hosts()))


def test_no_central_bank_and_no_money_host_is_in_the_browser():
    w = RR.what_the_reader_opens(NOW)
    cb = next(k for k in w["browser"]["kinds"] if k["kind"].startswith("Central banks"))
    assert cb["browser_hosts"] == []
    money = w["refused"]["money_hosts (banks, brokers, payment, crypto)"]
    listed = [h["host"] for k in w["browser"]["kinds"] for h in k["browser_hosts"]]
    assert not [h for h in listed for m in money if h == m or h.endswith("." + m)]
    assert "tinypass.com" in w["refused"]["checkout_hosts (subscription checkout providers)"]
    assert "mail.google.com" in w["refused"]["mail_and_message_hosts"]
    # the Fed is still READ: by feed
    assert any(f["host"] == "www.federalreserve.gov" and f["kind"].startswith("Central banks")
               for f in w["feeds"])


def test_the_page_is_regenerated_from_config_and_rewritten_only_on_change(tmp_path, monkeypatch):
    p = RR.write_what_the_reader_opens(root=tmp_path, now=NOW)
    text = p.read_text(encoding="utf-8")
    assert text.startswith("# What the reader opens")
    assert "Never edited by hand" in text and "## 3. Refused on every path" in text
    assert "federalreserve.gov" not in text.split("## 2.")[0]      # not a browser host
    m0 = p.stat().st_mtime_ns
    RR.write_what_the_reader_opens(root=tmp_path, now=NOW + timedelta(hours=1))
    assert p.stat().st_mtime_ns == m0                               # same content: untouched
    monkeypatch.setattr(_config, "OPENCLAW_BROWSER_HOSTS",
                        tuple(_config.OPENCLAW_BROWSER_HOSTS) + ("example.org",))
    RR.write_what_the_reader_opens(root=tmp_path, now=NOW + timedelta(hours=2))
    t2 = p.read_text(encoding="utf-8")
    assert "UNCLASSIFIED" in t2 and "- example.org" in t2


def test_the_page_reads_checkout_frames_under_its_own_root_not_the_live_ledger(tmp_path, monkeypatch):
    """2026-10-02: the no-op-rewrite test above failed in the full-file run because
    `checkout_frames_seen` read the LIVE page_log while the reader was logging frames."""
    import json
    live, mine = tmp_path / "live", tmp_path / "mine"
    for base, host in ((live, "live.example"), (mine, "mine.example")):
        (base / "dowjones").mkdir(parents=True)
        (base / "dowjones" / "page_log.jsonl").write_text(json.dumps(
            {"t": OS.iso(NOW - timedelta(hours=1)), "host": host, "class": "PAYWALL_CHECKOUT_FRAME",
             "url": "https://buy.tinypass.com/checkout"}) + chr(10), encoding="utf-8")
    monkeypatch.setattr(RR, "ledger", lambda: live)
    text = RR.write_what_the_reader_opens(root=mine, now=NOW).read_text(encoding="utf-8")
    assert "mine.example (1: buy.tinypass.com)" in text
    assert "live.example" not in text


# ─────────────────────────── the Fed, by feed only ───────────────────────────

def test_the_fed_is_not_a_browser_host_and_its_fronts_left_the_rotation():
    from backend.services import reader_scheduler as RS
    assert not WR.host_ok("https://www.federalreserve.gov/newsevents/speeches.htm")
    assert not any(RS.front_host(f) == "federalreserve.gov" for f in RS.all_fronts())
    feeds = dict(OS.RSS_FEEDS["fed_rss"])
    assert set(feeds) == {"fed_press", "fed_speech", "fed_testimony"}
    assert "fed_rss" in OS.TEXT_SOURCES


def test_html_to_text_keeps_the_article_and_drops_scripts_comments_and_footer():
    html = ('<html><head><style>x{}</style></head><body><nav>menu</nav>'
            '<div id="article"><!-- player --><h3>Speech</h3><p>Rates &amp; the economy.</p>'
            '<script>var a=1;</script><p>Second paragraph.</p></div>'
            '<div id="footer">Last update</div></body></html>')
    assert OS.html_to_text(html) == "Speech\nRates & the economy.\nSecond paragraph."


def _ev(rid, url, age_h, feed="fed_speech"):
    return {"row_id": rid, "source": feed, "url": url,
            "public_utc": OS.iso(NOW - timedelta(hours=age_h)), "title": rid}


def test_texts_due_takes_new_recent_fed_items_newest_first_and_caps_the_run():
    events = [_ev("a", "https://www.federalreserve.gov/newsevents/speech/a.htm", 5),
              _ev("b", "https://www.federalreserve.gov/newsevents/speech/b.htm", 1),
              _ev("c", "https://www.federalreserve.gov/newsevents/speech/c.htm", 24 * 30),
              _ev("d", "https://www.ecb.europa.eu/press/d.html", 1, feed="ecb_press"),
              _ev("e", "https://www.federalreserve.gov/newsevents/speech/e.htm", 2)]
    due = OS.texts_due("fed_rss", events, have={"e"}, now=NOW)
    assert [r["row_id"] for r in due] == ["b", "a"]            # c too old, d not Fed, e done
    assert OS.texts_due("ecb_rss", events, have=set(), now=NOW) == []


class _FakeFx:
    def __init__(self, base, pages):
        self.base, self.pages, self.asked = base, pages, []
        self.now_fn = lambda: NOW

    def get(self, source, url, **kw):
        self.asked.append(url)
        if url not in self.pages:
            raise OS.SourceRefused("NETWORK: down")
        return 200, self.pages[url].encode(), "text/html"


def test_collect_texts_writes_one_policy_texts_row_per_item_once(tmp_path):
    u = "https://www.federalreserve.gov/newsevents/speech/x.htm"
    OS.append_rows("policy_events", [_ev("fed_speech:x", u, 1)], tmp_path, NOW)
    fx = _FakeFx(tmp_path, {u: '<div id="article"><p>Full speech text.</p></div>'})
    r1 = OS.collect_texts(fx, "fed_rss")
    assert (r1["due"], r1["fetched"], r1["rows"]) == (1, 1, 1)
    row = OS.read_table("policy_texts", tmp_path)[0]
    assert row["row_id"] == "fed_speech:x" and row["text"] == "Full speech text."
    assert row["status"] == "TEXT" and row["public_utc"] == OS.iso(NOW - timedelta(hours=1))
    assert set(OS.SCHEMAS["policy_texts"]) <= set(row) | {"first_seen_utc"}
    r2 = OS.collect_texts(fx, "fed_rss")
    assert r2["due"] == 0 and fx.asked == [u]                  # never fetched twice


# ─────────────── one report per frame, blamed on its carrier ────────────────

def test_frame_carrier_walks_the_parent_chain_to_the_page():
    ts = [{"id": "p1", "type": "page", "url": "https://www.cnbc.com/markets/"},
          {"id": "f1", "type": "iframe", "parentId": "p1", "url": "https://x.example/ad"},
          {"id": "f2", "type": "iframe", "parentId": "f1",
           "url": "https://buy.tinypass.com/checkout/offer/show"}]
    by = {t["id"]: t for t in ts}
    assert RP.frame_carrier_url(ts[2], by) == "https://www.cnbc.com/markets/"
    assert RP.frame_carrier_url(ts[0], by) is None
    assert RP.frame_carrier_url({"id": "z", "parentId": "gone"}, by) is None


def test_a_frame_in_another_workers_tab_is_reported_once_and_blamed_on_its_page(ledger):  # noqa: F811
    targets = [{"id": "p1", "type": "page", "url": "https://www.cnbc.com/markets/"},
               {"id": "f9", "type": "iframe", "parentId": "p1",
                "url": "https://buy.tinypass.com/checkout/offer/show?displayMode=inline"}]
    pool = _pool(ledger, target_scan=lambda: targets, close_target=lambda i: True)
    # a MarketWatch read finishes while the CNBC tab (another worker) holds the frame
    assert pool._sweep_money_frames("marketwatch.com",
                                    "https://www.marketwatch.com/latest-news") is False
    assert pool.classes["cnbc.com"]["PAYWALL_CHECKOUT_FRAME"] == 1
    assert pool.classes["marketwatch.com"]["PAYWALL_CHECKOUT_FRAME"] == 0
    assert pool.money_events[-1]["carrier_page"] == "https://www.cnbc.com/markets/"
    # the next two reads see the same frame: no new report
    pool._sweep_money_frames("apnews.com", "https://apnews.com/business")
    pool._sweep_money_frames("scmp.com", "https://www.scmp.com/business")
    assert pool.classes["cnbc.com"]["PAYWALL_CHECKOUT_FRAME"] == 1
    assert len(pool.money_events) == 1


# ───────────────────── HKMA: retry, then the main-site RSS ─────────────────────

_HKMA_RSS = ("<?xml version='1.0'?><rss><channel><item><title>Exchange Fund Bills Tender"
             "</title><link>https://www.hkma.gov.hk/eng/news-and-media/press-releases/x.shtml"
             "</link><pubDate>{d}</pubDate><description>Tender results</description></item>"
             "</channel></rss>")


class _HkmaFx(_FakeFx):
    def __init__(self, base, api):
        super().__init__(base, {})
        self.api = api

    def get(self, source, url, **kw):
        self.asked.append(url)
        if "api.hkma" in url:
            return self.api(url)
        from email.utils import format_datetime
        return 200, _HKMA_RSS.format(d=format_datetime(NOW - timedelta(hours=3))).encode(), "xml"


def test_hkma_api_down_is_retried_with_backoff_then_read_from_rss(tmp_path):
    def down(url):
        raise OS.SourceRefused("NETWORK: ReadTimeout")
    slept = []
    fx = _HkmaFx(tmp_path, down)
    r = OS.collect_hkma(fx, sleep_fn=slept.append, backoff_s=(1.0, 2.0))
    assert r["attempts"] == 3 and slept == [1.0, 2.0]
    assert r["via"] == "rss_fallback" and r["rows"] == 2          # press + speech feeds
    assert r["api_down_since"] is not None
    rows = OS.read_table("policy_events", tmp_path)
    assert {x["agency"] for x in rows} == {"hkma"}


def test_hkma_api_back_up_clears_the_outage(tmp_path):
    import json as _j
    ok = lambda url: (200, _j.dumps({"result": {"records": [
        {"title": "Press", "link": "https://www.hkma.gov.hk/p.shtml",
         "date": (NOW - timedelta(days=1)).date().isoformat()}]}}).encode(), "json")
    fx = _HkmaFx(tmp_path, ok)
    r = OS.collect_hkma(fx, sleep_fn=lambda s: None)
    assert r["via"] == "api" and r["attempts"] == 1 and r["api_down_since"] is None
    assert not [u for u in fx.asked if "rss" in u]


# ─────────── the Form 4 backfill leaves the live feed its requests ───────────

def test_the_backfill_stops_at_the_reserve_and_keeps_its_progress(tmp_path, monkeypatch):
    from backend.services import sec_daily_index as SDI
    fil = [{"form_type": "4", "accession": f"0000000000-26-{i:06d}", "cik": "1"}
           for i in range(10)]
    monkeypatch.setattr(SDI, "fetch_index", lambda d: {"status": "OK", "filings": fil})
    counts = {"n": 0}

    class Fx(_FakeFx):
        def day_count(self, source):
            return counts["n"]

        def _log(self, row):
            pass

        def get(self, source, url, **kw):
            counts["n"] += 1
            return 404, b"", ""                              # nothing to parse; counts only

    cap = OS.SOURCES["sec_form4"]["day_cap"]
    counts["n"] = cap - 3002                                 # two requests above the reserve
    fx = Fx(tmp_path, {})
    rec = OS.collect_sec_form4_backfill(fx, days=1, reserve=3000)
    assert rec["refused"].startswith("RESERVE")
    assert counts["n"] == cap - 3000                         # two index pages, then stop
    assert rec["errors"] == {"index_404": 2}


# ─────────── a BLANK X handle page is diagnosed and retried, not shelved ───────────

def test_a_blank_handle_page_is_not_marked_read_and_says_what_came_back(ledger, monkeypatch):  # noqa: F811
    from scripts import social_browser_pull as SB

    class Rd:
        def refund_slot(self, why):
            return True

    monkeypatch.setattr(SB, "read_opened", lambda rd, **kw: (
        "BLANK", {"title": "X", "chars": 12, "url": kw["url"]}))
    pool = _pool(ledger)
    it = {"kind": "social", "host": "x.com", "lane": "social:x.com:handle",
          "handle": "Broadcom", "url": "https://x.com/Broadcom"}
    assert pool._read(it, Rd()) == "BLANK"
    assert ("x.com", "Broadcom") not in pool.social_last
    assert "chars=12" in pool.errors[-1] and "title='X'" in pool.errors[-1]
    # a BLANK cashtag search is still marked read as before
    it2 = {"kind": "social", "host": "x.com", "lane": "social:x.com", "ticker": "AVGO",
           "url": "https://x.com/search?q=%24AVGO&f=live"}
    pool._read(it2, Rd())
    assert ("x.com", "AVGO") in pool.social_last


def test_the_supervisor_logs_a_lingering_frame_once_but_always_closes_a_page():
    from scripts import night_reader_supervisor as S
    ts = [{"id": "f1", "type": "iframe", "url": "https://buy-ap.piano.io/checkout/offer/show"},
          {"id": "p1", "type": "page", "url": "https://www.hsbc.com.hk/"}]
    seen: set[str] = set()
    closed = []
    a = S.sweep_money_pages(targets=lambda: ts, close=lambda i: closed.append(i) or True, seen=seen)
    b = S.sweep_money_pages(targets=lambda: ts, close=lambda i: closed.append(i) or True, seen=seen)
    assert [x["type"] for x in a] == ["iframe", "page"]
    assert [x["type"] for x in b] == ["page"] and closed == ["p1", "p1"]
