"""No bank, broker, payment, checkout or mail address on ANY reader path
(2026-09-30, the owner: "openclaw opens banks").

MEASURED: the dedicated Chrome's history showed no bank / broker / payment
visit, but three loads of `buy.tinypass.com/checkout/offer/show?...` -- the
Piano subscription checkout SCMP embeds in a metered article. Pinned here:
* the money / checkout hosts and paths refuse on every path: a navigation /
  open / click (`browser_policy.url_refusal`), the reader's host check
  (`web_reader.host_ok` / NEVER_HOSTS), the official-sources fetcher, the
  digest's read_next asks, the site-search URLs;
* central banks (Fed, ECB, BoJ, BoE, HKMA, PBoC) are NOT refused by it;
* a checkout FRAME seen after a read makes that page PAYWALL_STUB and its host
  fronts-only; a checkout / bank POP-UP page is closed.

Offline: fakes only, no browser, no network. No literal calendar dates.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend import config as _config
from backend.services import browser_policy as BP
from backend.services import official_sources as OS
from backend.services import reader_scheduler as RS
from backend.services import web_reader as WR
from backend.tests.test_reader_pool import Clock, FakeDriver, _thr
from scripts import night_reader_supervisor as S
from scripts import reader_pool as RP

MONEY_URLS = [
    "https://www.hsbc.com.hk/", "https://www.hsbc.com/login", "https://www.hangseng.com/en-hk/",
    "https://www.bochk.com/en/home.html", "https://www.sc.com/hk/", "https://www.za.group/hk",
    "https://mox.com/", "https://www.futuhk.com/", "https://www.moomoo.com/",
    "https://www.interactivebrokers.com.hk/", "https://www.ibkr.com/", "https://app.alpaca.markets/",
    "https://www.paypal.com/signin", "https://wise.com/", "https://www.revolut.com/",
    "https://dashboard.stripe.com/", "https://www.chase.com/", "https://www.coinbase.com/",
    "https://mail.google.com/mail/u/0/", "https://outlook.live.com/mail/",
]
CHECKOUT_URLS = [
    "https://buy.tinypass.com/checkout/offer/show?aid=x&url=https%3A%2F%2Fwww.scmp.com%2Fnews",
    "https://experience.piano.io/xbuilder/experience/load?aid=x",
    "https://www.scmp.com/checkout?plan=1", "https://www.ft.com/subscribe",
    "https://www.wsj.com/payment/update", "https://www.barrons.com/billing/",
    "https://www.cnbc.com/cart/", "https://www.nikkei.com/offer/show",
]
CENTRAL_BANKS = ["https://www.federalreserve.gov/newsevents/pressreleases.htm",
                 "https://www.ecb.europa.eu/rss/press.html", "https://www.boj.or.jp/en/rss/whatsnew.xml",
                 "https://www.bankofengland.co.uk/rss/news", "https://api.hkma.gov.hk/public/press-releases",
                 "http://www.pbc.gov.cn/en/3688110/index.html"]


@pytest.mark.parametrize("url", MONEY_URLS + CHECKOUT_URLS)
def test_every_money_or_checkout_address_refuses_on_the_navigation_path(url):
    why = BP.url_refusal(url)
    assert why and why.startswith(("REFUSED_MONEY_HOST", "REFUSED_PAYMENT_URL",
                                   "REFUSED_MESSAGE_URL"))


@pytest.mark.parametrize("url", MONEY_URLS + CHECKOUT_URLS)
def test_every_money_or_checkout_address_fails_the_reader_host_check(url):
    assert WR.host_ok(url) is False


@pytest.mark.parametrize("url", MONEY_URLS + CHECKOUT_URLS)
def test_the_official_sources_fetcher_refuses_them_before_any_request(url, tmp_path, monkeypatch):
    monkeypatch.setitem(OS.SOURCES, "probe_src", {"lane": "overhead", "host": "x", "day_cap": 9,
                                                  "every_s": 1, "min_gap_s": 0})
    fx = OS.Fetcher(base=tmp_path, http=lambda *a, **k: pytest.fail("a request left"),
                    log_requests=False)
    with pytest.raises(OS.SourceRefused, match="REFUSED_(MONEY_HOST|PAYMENT_URL|MESSAGE_URL)"):
        fx.get("probe_src", url)


@pytest.mark.parametrize("url", CENTRAL_BANKS)
def test_central_banks_are_public_sites_not_money_hosts(url):
    assert BP.money_url_refusal(url) is None
    assert S.central_bank_label(url) == "central bank (public releases)"


def test_no_official_source_and_no_search_site_is_a_money_host():
    urls = [u for feeds in OS.RSS_FEEDS.values() for _, u in feeds]
    urls += [f"https://{s['host']}/" for s in OS.SOURCES.values()]
    urls += [RS.search_url(site, "test query") for site in RS.SEARCH_URLS]
    assert [u for u in urls if u and BP.money_url_refusal(u)] == []


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(RP, "DJ", tmp_path / "dowjones")
    monkeypatch.setattr(RP, "FRONT_SCHEDULE", tmp_path / "dowjones" / "front_schedule.json")
    monkeypatch.setattr(RP, "SOCIAL_SEEN", tmp_path / "social_seen.jsonl")
    return tmp_path


def _pool(ledger, **kw):
    c = Clock(datetime.now(timezone.utc).replace(microsecond=0))
    thr = _thr(ledger, c, wait_on_hour_cap=True)
    gov = RS.TabGovernor(max_tabs=2, mem_fn=lambda: 9.0, target=2)
    return RP.Pool(driver=FakeDriver({}), throttle=thr, names=[], books=set(), fresh=set(),
                   fronts=[], social=False, stock_pages=(), governor=gov,
                   cooling=RS.HostCooling(path=ledger / "cool.json"), stored={}, now_fn=c.now,
                   wait_fn=lambda s: False, caption_fetch=lambda u: {}, dropped=set(),
                   front_last={}, stock_last={}, social_last={}, printer=lambda *a: None,
                   reader_sleep=lambda s: None, persist=False, **kw)


def test_a_digest_ask_for_a_bank_url_is_never_queued(ledger, tmp_path):
    import json
    rn = tmp_path / "read_next.jsonl"
    now = datetime.now(timezone.utc)
    rn.write_text("\n".join(json.dumps({"t": now.isoformat(), "url": u}) for u in MONEY_URLS[:6]
                            + CHECKOUT_URLS[:3]), encoding="utf-8")
    pool = _pool(ledger, read_next_path=rn)
    pool.read_next_done = set()
    pool.refill()
    assert [it["url"] for it in pool.pending if it.get("via") == "read_next"] == []


def test_a_checkout_frame_makes_the_page_a_paywall_stub_and_the_host_fronts_only(ledger):
    frames = [{"id": "f1", "type": "iframe",
               "url": "https://buy.tinypass.com/checkout/offer/show?aid=a&url="
                      "https%3A%2F%2Fwww.scmp.com%2Fnews%2Farticle%2F1%2Fx"}]
    closed = []
    pool = _pool(ledger, target_scan=lambda: frames, close_target=lambda i: closed.append(i) or True)
    pool._add({"kind": "article", "site": "scmp", "host": "scmp.com", "lane": "front:scmp:business",
               "url": "https://www.scmp.com/business/article/3000001/other", "key": "a2"})
    assert pool._sweep_money_frames("scmp.com", "https://www.scmp.com/news/article/1/x") is True
    assert pool._fronts_only("scmp.com")
    assert not [x for x in pool.pending if x["host"] == "scmp.com" and x["kind"] == "article"]
    assert pool.classes["scmp.com"]["PAYWALL_CHECKOUT_FRAME"] == 1
    assert closed == []                          # a frame is not a page: its tab closes as always
    assert pool.status()["money_frames"][0]["target_type"] == "iframe"


def test_a_money_popup_page_is_closed(ledger):
    pages = [{"id": "p9", "type": "page", "url": "https://www.hsbc.com.hk/"},
             {"id": "p1", "type": "page", "url": "https://www.cnbc.com/markets/"}]
    closed = []
    pool = _pool(ledger, target_scan=lambda: pages, close_target=lambda i: closed.append(i) or True)
    pool._sweep_money_frames("cnbc.com", "https://www.cnbc.com/markets/")
    assert closed == ["p9"]
    got = S.sweep_money_pages(targets=lambda: pages, close=lambda i: i == "p9")
    assert [g["url"] for g in got] == ["https://www.hsbc.com.hk/"] and got[0]["closed"] is True


def test_a_scan_failure_never_stops_the_read(ledger):
    def boom():
        raise RuntimeError("devtools down")
    pool = _pool(ledger, target_scan=boom)
    assert pool._sweep_money_frames("cnbc.com", "https://www.cnbc.com/") is False
