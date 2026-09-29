"""The reader's BROWSE lane (2026-09-29): general news beyond Dow Jones, a list
that refills itself, and states that tell the truth.

Murat, 2026-09-29: "digest the news see what they are implying is there an
another path they are leading, not only the forecast from the websites but the
stocks news and the general news brose the news like a human to get the
context" / "it shuld always work and shouldnt be standing idle".

MEASURED that morning: 0 pages for 100+ minutes with every Dow Jones cap free
and `pending: 0` -- the work list was exhausted, nothing refilled it, and the
supervisor restarted a healthy idle pool every ~15 minutes as STALLED.

Test doubles only (the fake driver of test_reader_pool, a fake clock, tmp_path).
No network, browser, CLI or gateway. No literal calendar dates: every time is
derived from now.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend import config as _config
from backend.services import reader_report as RR
from backend.services import reader_scheduler as RS
from backend.services import web_reader as WR
from backend.tests.test_reader_pool import Clock, FakeDriver, _snap, _thr
from scripts import night_reader_supervisor as S
from scripts import reader_pool as RP

NOW = datetime.now(timezone.utc).replace(microsecond=0)

CNBC_FRONT = "https://www.cnbc.com/markets/"
CNBC_ROBOTS = "https://www.cnbc.com/robots.txt"
FED_ROBOTS = "https://www.federalreserve.gov/robots.txt"
_D = NOW.strftime("%Y/%m/%d")
CNBC_A1 = f"https://www.cnbc.com/{_D}/treasury-yields-jump-after-jobs-report.html"
CNBC_A2 = f"https://www.cnbc.com/{_D}/oil-prices-slide-on-supply-worries.html"
CNBC_BLOCKED = f"https://www.cnbc.com/{_D}/private-page-robots-disallow.html"
FED_PR = "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260101a.htm"
X_POST = "https://x.com/someone/status/1234567890"
LONG = "Treasury yields rose sharply after the payrolls report surprised. " * 20


def _pages() -> dict:
    return {
        CNBC_ROBOTS: {"title": "", "text": f"User-agent: *\nDisallow: /{_D}/private-\n"},
        FED_ROBOTS: {"title": "", "text": "User-agent: *\nDisallow: /cgi-bin/\n"},
        CNBC_FRONT: {"snapshot": _snap("Markets - CNBC", [
            ("Treasury Yields Jump After the Jobs Report", CNBC_A1),
            ("Oil Prices Slide On Supply Worries Today", CNBC_A2),
            ("A Search Result Page That Robots Disallow", CNBC_BLOCKED)])},
        CNBC_A1: {"title": "Treasury yields jump", "text": LONG,
                  "snapshot": _snap("Treasury yields jump", [
                      ("Federal Reserve issues FOMC statement", FED_PR),
                      ("Someone posted about yields on X today", X_POST),
                      ("Oil Prices Slide On Supply Worries Today", CNBC_A2)])},
        CNBC_A2: {"title": "Oil slides", "text": "Oil prices slid on supply worries. " * 30},
        FED_PR: {"title": "FOMC statement", "text": "The Committee decided to maintain. " * 30},
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


def _front(key: str) -> dict:
    return next(f for f in RS.all_fronts() if RS.front_key(f) == key)


def _pool(ledger, driver, *, fronts, clock=None, **kw):
    # the pool's clock starts at the TEST's own now, not at collection time: the
    # store stamps records with the real time and `pages_read_since` drops a
    # record more than 5 min after its `now`, so a clock frozen at import failed
    # these tests whenever the suite reached them > 5 min after collection
    c = clock or Clock(datetime.now(timezone.utc).replace(microsecond=0))
    thr = _thr(ledger, c, wait_on_hour_cap=True)
    gov = RS.TabGovernor(max_tabs=4, mem_fn=lambda: 9.0, target=4)
    return RP.Pool(driver=driver, throttle=thr, names=[], books=set(), fresh=set(),
                   fronts=fronts, social=False, stock_pages=(), governor=gov,
                   cooling=RS.HostCooling(path=ledger / "cool.json"), stored={},
                   now_fn=c.now, wait_fn=lambda s: False, caption_fetch=lambda u: {},
                   dropped=set(), front_last={}, stock_last={}, social_last={},
                   printer=lambda *a: None, reader_sleep=lambda s: None, **kw), c


def _drain(pool, n=60):
    for _ in range(n):
        it = pool.take(0)
        if it is None:
            break
        try:
            pool.process(it, 0)
        finally:
            pool.release(it)


# ───────────────────────────── 1. the refill rule ────────────────────────────

def test_a_starving_host_revisits_its_fronts_early_and_a_busy_one_waits():
    fed = _front("fed:press_releases")            # a slow front: every 2 h on schedule
    last = NOW - timedelta(minutes=25)
    assert not RS.front_due(fed, last, NOW)
    assert RS.front_due_now(fed, last, NOW, host_pending=0, low=3, revisit_s=1200)
    assert RS.front_due_now(fed, last, NOW, host_pending=3, low=3, revisit_s=1200)
    assert not RS.front_due_now(fed, last, NOW, host_pending=4, low=3, revisit_s=1200)
    assert not RS.front_due_now(fed, NOW - timedelta(minutes=10), NOW, host_pending=0,
                                low=3, revisit_s=1200)           # changed 10 min ago: not yet
    assert RS.front_due_now(fed, None, NOW, host_pending=99)     # never read: due


def test_next_front_due_counts_the_early_revisit_for_an_empty_host():
    fed = _front("fed:press_releases")
    last = {RS.front_key(fed): NOW - timedelta(minutes=15)}
    s_empty = RS.next_front_due_s([fed], last, NOW, pending_by_host={})
    s_busy = RS.next_front_due_s([fed], last, NOW, pending_by_host={fed["host"]: 10})
    assert s_empty == pytest.approx(RS.min_revisit_s() - 900, abs=1)
    assert s_busy > s_empty
    assert RS.next_front_due_s([fed], {}, NOW, pending_by_host={}) == 0.0


def test_the_pool_refills_an_exhausted_list_from_its_fronts(ledger):
    d = FakeDriver(_pages())
    pool, c = _pool(ledger, d, fronts=[_front("cnbc:markets")])
    pool.refill()
    assert [it["kind"] for it in pool.pending] == ["robots"]    # robots.txt before the front
    _drain(pool)
    pool.refill()
    _drain(pool)
    opens = [u for v, u in d.actions if v == "open"]
    assert opens[:2] == [CNBC_ROBOTS, CNBC_FRONT]
    assert CNBC_A1 in opens and CNBC_A2 in opens and FED_PR in opens
    assert not pool.pending
    st = pool.status()
    assert st["queue_state"] == RS.Q_EMPTY and st["state"] == "queue_empty"
    # 25 minutes later the list is still empty: the front comes round EARLY
    c.t += timedelta(minutes=25)
    assert pool.refill() >= 1
    assert [it["kind"] for it in pool.pending] == ["front"]
    assert pool.early_fronts["cnbc.com"] == 1
    assert pool.status()["queue_state"] == RS.Q_READING


def test_a_page_is_read_once_by_canonical_url(ledger):
    d = FakeDriver(_pages())
    pool, c = _pool(ledger, d, fronts=[_front("cnbc:markets")])
    for _ in range(2):
        pool.refill()
        _drain(pool)
    c.t += timedelta(minutes=25)
    pool.refill()
    _drain(pool)                                      # the front again, nothing new on it
    opens = [u for v, u in d.actions if v == "open"]
    assert opens.count(CNBC_A1) == 1 and opens.count(CNBC_A2) == 1
    assert opens.count(CNBC_FRONT) == 2
    # the same article with a tracking query and a trailing slash is the same page
    assert WR.norm_url(CNBC_A1 + "?utm_source=x") == WR.norm_url(CNBC_A1 + "/")


# ─────────────────────────── 2. links and robots ─────────────────────────────

@pytest.mark.parametrize("url,ok", [
    ("https://www.reuters.com/markets/us/stocks-rally-as-yields-ease-2026-01-02/", True),
    ("https://www.reuters.com/markets/", False),
    ("https://apnews.com/article/stocks-markets-rates-inflation-0123456789abcdef", True),
    (f"https://www.cnbc.com/{_D}/oil-prices-slide.html", True),
    ("https://www.cnbc.com/markets/", False),
    ("https://www.ft.com/content/0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b", True),
    ("https://www.federalreserve.gov/newsevents/pressreleases/monetary20260101a.htm", True),
    ("https://www.bls.gov/news.release/empsit.nr0.htm", True),
    ("https://home.treasury.gov/news/press-releases/sb0123", True),
    ("https://www.scmp.com/business/markets/article/3300000/some-headline-here", True),
    ("https://x.com/someone/status/1", False),
])
def test_article_shapes_per_host(url, ok):
    assert RS.any_article_pattern(url) is ok


def test_outbound_links_put_articles_first_and_dedupe():
    snap = _snap("A page", [("Home", "https://www.cnbc.com/"),
                            ("Federal Reserve issues FOMC statement", FED_PR),
                            ("Federal Reserve issues FOMC statement", FED_PR + "?x=1"),
                            ("A long navigation link to a section", "https://www.cnbc.com/world/"),
                            ("javascript thing that is long enough", "javascript:void(0)")])
    out = RP.outbound_links(snap)
    assert [o["url"] for o in out] == [FED_PR, "https://www.cnbc.com/world/"]
    assert RP.site_of(FED_PR) == "fed" and RP.site_of("https://finance.yahoo.com/x") == "yahoo"


def test_robots_rules_are_read_and_a_disallowed_page_is_never_opened(ledger):
    rules = f"User-agent: *\nDisallow: /{_D}/private-\n"
    assert RS.robots_allows(rules, CNBC_BLOCKED) is False
    assert RS.robots_allows(rules, CNBC_A1) is True
    assert RS.robots_allows(None, CNBC_A1) is True          # no robots.txt: nothing disallowed
    d = FakeDriver(_pages())
    pool, _ = _pool(ledger, d, fronts=[_front("cnbc:markets")])
    pool.refill()
    _drain(pool)
    pool.refill()
    _drain(pool)
    opens = [u for v, u in d.actions if v == "open"]
    assert CNBC_BLOCKED not in opens
    assert pool.robots_refused["cnbc.com"] >= 1
    assert RS.robots_record("cnbc.com")["class"] == "OK"     # kept for a day
    assert FED_ROBOTS in opens and opens.index(FED_ROBOTS) < opens.index(FED_PR)


def test_browse_follows_in_article_links_one_hop_never_social(ledger):
    d = FakeDriver(_pages())
    pool, _ = _pool(ledger, d, fronts=[_front("cnbc:markets")])
    pool.refill()
    _drain(pool)
    pool.refill()
    _drain(pool)
    opens = [u for v, u in d.actions if v == "open"]
    assert FED_PR in opens and X_POST not in opens            # no ticker needed; no social
    rec = {r["url"]: r for r in RR.pages_read_since(1, root=ledger, now=pool.now_fn())}
    assert rec[FED_PR]["reached_by"]["depth"] == 1
    assert rec[FED_PR]["reached_by"]["via"] == "browse"
    assert rec[FED_PR]["reached_by"]["parent_url"] == CNBC_A1


# ─────────────────────── 3. the store and the digest read ────────────────────

def test_every_page_read_is_stored_with_what_a_digest_needs(ledger):
    d = FakeDriver(_pages())
    pool, c = _pool(ledger, d, fronts=[_front("cnbc:markets")])
    pool.refill()
    _drain(pool)
    pool.refill()
    _drain(pool)
    rows = RR.pages_read_since(2, root=ledger, now=c.now())
    by = {r["url"]: r for r in rows}
    a = by[CNBC_A1]
    for k in ("url", "host", "section", "title", "published_utc", "fetched_utc", "text",
              "outbound_links", "page_class", "page_kind", "source_kind"):
        assert k in a
    assert a["host"] == "cnbc.com" and a["section"] == "markets" and a["page_class"] == "OK"
    assert a["source_kind"] == "general_news" and a["publisher"] == "cnbc"
    assert FED_PR in [o["url"] for o in a["outbound_links"]]
    fronts = [r for r in rows if r["page_kind"] == "front"]
    assert len(fronts) == 1 and "Treasury Yields Jump" in fronts[0]["text"]
    assert RR.pages_read_since(2, root=ledger, now=c.now(), kinds=("front",)) == fronts
    assert "text" not in RR.pages_read_since(2, root=ledger, now=c.now(),
                                             include_text=False)[0]
    # nothing read in the window that ended an hour before the reads
    assert RR.pages_read_since(1, root=ledger, now=c.now() - timedelta(hours=3)) == []
    # the stored record says it is not Dow Jones
    assert json.loads(open(a["path"], encoding="utf-8").read())["licence"].startswith("public")


def test_claims_skip_fronts_and_general_news(ledger):
    from scripts import dowjones_pull as DP
    d = FakeDriver(_pages())
    pool, _ = _pool(ledger, d, fronts=[_front("cnbc:markets")])
    pool.refill()
    _drain(pool)
    pool.refill()
    _drain(pool)

    def boom(*a, **k):
        raise AssertionError("no LLM call for a front or a general-news page")
    out = DP.run_claims(NOW.date().isoformat(), llm_fn=boom, spend_fn=lambda: 0.0,
                        root=WR.corpus_root(), done_path=ledger / "done.txt",
                        claims_path=ledger / "claims.jsonl", ledger_path=ledger / "led.jsonl",
                        structured_dir=ledger / "structured")
    assert isinstance(out, dict)


# ──────────────────────────── 4. the state labels ────────────────────────────

def test_host_and_pool_queue_states():
    q = RS.host_queue_state
    assert q(pending=0, in_flight=0, capped=False, cooling=True, front_due_in_s=0) == RS.Q_COOLING
    assert q(pending=5, in_flight=0, capped=True, cooling=False,
             front_due_in_s=0) == RS.Q_WAITING_FOR_CAP
    assert q(pending=2, in_flight=0, capped=False, cooling=False,
             front_due_in_s=900) == RS.Q_READING
    assert q(pending=0, in_flight=0, capped=False, cooling=False,
             front_due_in_s=0) == RS.Q_REFILLING
    assert q(pending=0, in_flight=0, capped=False, cooling=False,
             front_due_in_s=600) == RS.Q_EMPTY
    assert RS.pool_queue_state({"a": RS.Q_EMPTY, "b": RS.Q_WAITING_FOR_CAP}) == RS.Q_EMPTY
    assert RS.pool_queue_state({"a": RS.Q_COOLING, "b": RS.Q_WAITING_FOR_CAP}) == \
        RS.Q_WAITING_FOR_CAP
    assert RS.pool_queue_state({"a": RS.Q_EMPTY, "b": RS.Q_READING}) == RS.Q_READING


def _st(**kw):
    base = dict(alive=True, repairing=False, ok_10m=0, last_ok_age=6000.0,
                since_launch_s=5000.0, next_slot_in_s=None, attempts_10m=0,
                stall_after_s=600.0)
    base.update(kw)
    return S.derive_state(**base)


def test_an_empty_list_with_caps_free_is_queue_empty_never_stalled():
    # the 2026-09-29 morning: alive, nothing attempted, no OK page for 100 min
    assert _st() == S.STALLED                              # without the pool's word
    assert _st(pool_state=S.QUEUE_EMPTY) == S.QUEUE_EMPTY
    assert _st(pool_state=S.WAITING_FOR_CAP) == S.WAITING_FOR_CAP
    assert _st(pool_state=S.QUEUE_EMPTY, since_launch_s=30) == S.QUEUE_EMPTY
    # pages attempted and none OK is still a stall, whatever the pool says
    assert _st(pool_state=S.QUEUE_EMPTY, attempts_10m=12) == S.STALLED
    assert _st(pool_state=S.REFILLING, since_launch_s=60) == S.REFILLING
    assert _st(pool_state=S.QUEUE_EMPTY, ok_10m=2) == S.READING


def test_a_stale_pool_status_is_not_believed():
    fresh = {"t": NOW.isoformat(), "queue_state": "QUEUE_EMPTY"}
    old = {"t": (NOW - timedelta(minutes=10)).isoformat(), "queue_state": "QUEUE_EMPTY"}
    assert S.pool_state_of(fresh, NOW) == "QUEUE_EMPTY"
    assert S.pool_state_of(old, NOW) is None and S.pool_state_of(None, NOW) is None


def test_next_action_never_says_keep_reading_beside_a_stall():
    assert S.next_action_for(S.STALLED) != "keep reading"
    assert "revisit" in S.next_action_for(S.QUEUE_EMPTY, {"next_front_due_s": 300})
    assert S.next_action_for(S.READING) == "keep reading"


def test_the_stall_ladder_survives_a_restart(tmp_path):
    p = tmp_path / "ladder.json"
    S.save_ladder(2, 123.0, path=p)
    assert S.load_ladder(p) == {"level": 2, "last_act": 123.0}
    old = json.loads(p.read_text(encoding="utf-8"))
    old["saved"] -= 7200
    p.write_text(json.dumps(old), encoding="utf-8")
    assert S.load_ladder(p)["level"] == 0                  # an hour-old ladder is not resumed


# ───────────────────── 5. caps count, blank and paywall runs ─────────────────

def test_a_blank_page_keeps_its_slot_and_a_run_of_blanks_cools_the_host(ledger, monkeypatch):
    monkeypatch.setattr(_config, "READER_BLANK_STREAK_COOL", 2)
    pages = _pages()
    pages[CNBC_A1] = {"title": "", "text": ""}             # renders blank
    pages[CNBC_A2] = {"title": "", "text": ""}
    d = FakeDriver(pages)
    pool, _ = _pool(ledger, d, fronts=[_front("cnbc:markets")])
    pool.refill()
    _drain(pool)
    pool.refill()
    _drain(pool)
    lines = [ln for ln in (ledger / "_throttle.log").read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    opens = [u for v, u in d.actions if v == "open"]
    assert len(lines) == len(opens)                          # every load is on the caps
    assert "cnbc.com" in RS.HostCooling(path=ledger / "cool.json").active(pool.now_fn())


def test_a_paywall_run_leaves_a_host_on_its_headlines(ledger, monkeypatch):
    monkeypatch.setattr(_config, "READER_PAYWALL_STREAK", 2)
    pool, _ = _pool(ledger, FakeDriver({}), fronts=[])
    pool.pending = [{"kind": "article", "host": "ft.com", "url": "u", "key": "k"}]
    pool._paywall("ft.com", "PAYWALL_STUB")
    assert not pool._fronts_only("ft.com")
    pool._paywall("ft.com", "SIGNED_OUT")
    assert pool._fronts_only("ft.com") and pool.pending == []
    pool._paywall("wsj.com", "PAYWALL_STUB")
    pool._paywall("wsj.com", "OK")
    assert pool.paywall_streak["wsj.com"] == 0


# ─────────────────────────── 6. the allowlist ────────────────────────────────

def test_news_hosts_are_allowed_and_nothing_else_moved():
    for h in _config.OPENCLAW_NEWS_HOSTS:
        assert WR.host_ok(f"https://{h}/") or WR.host_ok(f"https://www.{h}/")
    assert not WR.host_ok("https://mail.google.com/")
    assert not WR.host_ok("https://app.alpaca.markets/")
    assert not WR.host_ok("https://www.example.org/")
    # the Dow Jones and social caps are unchanged
    assert _config.WEB_READER_MAX_PER_DAY_PER_HOST == 1200
    assert all(_config.WEB_READER_MAX_PER_DAY_BY_HOST[h] == 150
               for h in ("x.com", "reddit.com", "stocktwits.com"))
    assert all(_config.READER_MAX_PER_HOUR_BY_HOST[h] == 120
               for h in ("wsj.com", "barrons.com", "marketwatch.com"))
    # every news front is on an allowed host
    for f in RS.NEWS_FRONTS:
        assert WR.host_ok(f["urls"][0]), f["urls"][0]


# ─────────────── 7. the digest's asks, and current vs archive ────────────────

AP_SEARCH_HIT = "https://apnews.com/article/iran-talks-ceasefire-0123456789abcdef"
WSJ_HIT = "https://www.wsj.com/world/middle-east/iran-talks-resume-1a2b3c4d"


def test_search_urls_are_navigations_on_the_sites_own_search_page():
    u = RS.search_url("apnews", "US Iran ceasefire talks & latest")
    assert u == "https://apnews.com/search?q=US+Iran+ceasefire+talks+%26+latest"
    assert RS.search_url("nowhere", "x") is None and RS.search_url("apnews", "  ") is None
    a, b = RS.search_sites_for(0), RS.search_sites_for(1)
    assert len(a) == 2 and a != b
    assert any(k in RS.NEWS_SITES for k in a) and any(k not in RS.NEWS_SITES for k in a)
    for k in RS.SEARCH_URLS:
        assert WR.host_ok(RS.search_url(k, "oil prices")), k
    assert RS.read_next_key({"search_query": "  Oil  Prices "}) == "q:oil prices"
    assert RS.read_next_key({"url": "https://x"}) == "url:https://x"


def test_the_digest_asks_are_adopted_once_as_searches_and_urls(ledger):
    rn = ledger / "read_next.jsonl"
    rows = [{"t": NOW.isoformat(), "digest_id": "d1", "theme": "Iran",
             "question": "Will talks resume?", "search_query": "US Iran ceasefire talks"},
            {"t": NOW.isoformat(), "digest_id": "d1", "url": CNBC_A2, "question": "oil"},
            {"t": NOW.isoformat(), "digest_id": "d1", "url": X_POST},           # social: never
            {"t": (NOW - timedelta(days=3)).isoformat(), "search_query": "old ask"}]
    rn.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    ap = RS.search_url("apnews", "US Iran ceasefire talks")
    wsj = RS.search_url("wsj", "US Iran ceasefire talks")
    pages = _pages()
    pages["https://apnews.com/robots.txt"] = {"title": "", "text": "User-agent: *\nAllow: /\n"}
    pages[ap] = {"snapshot": _snap("Search - AP", [("Iran And US Resume Ceasefire Talks",
                                                    AP_SEARCH_HIT)])}
    pages[wsj] = {"snapshot": _snap("Search - WSJ", [("Iran Talks Resume in Oman, Officials Say",
                                                      WSJ_HIT)])}
    pages[AP_SEARCH_HIT] = {"title": "Talks resume", "text": "Talks resumed today in Oman. " * 30}
    pages[WSJ_HIT] = {"title": "Talks resume", "text": "Officials said talks resume. " * 30}
    d = FakeDriver(pages)
    pool, c = _pool(ledger, d, fronts=[], read_next_path=rn)
    pool.refill()
    kinds = sorted(it["kind"] for it in pool.pending)
    assert kinds == ["article", "robots", "search", "search"]
    assert not any(it["url"] == X_POST for it in pool.pending)
    for _ in range(3):
        _drain(pool)
        pool.refill()
    opens = [u for v, u in d.actions if v == "open"]
    assert ap in opens and wsj in opens and AP_SEARCH_HIT in opens and WSJ_HIT in opens
    assert opens.count(ap) == 1                               # adopted once
    rec = {r["url"]: r for r in RR.pages_read_since(1, root=ledger, now=c.now())}
    assert rec[AP_SEARCH_HIT]["reached_by"]["question"] == "Will talks resume?"
    assert rec[AP_SEARCH_HIT]["reached_by"]["via"] == "search"
    assert any(r["page_kind"] == "search" for r in rec.values())
    # a new pool (a restart) does not adopt the same asks again
    pool2, _ = _pool(ledger, FakeDriver(pages), fronts=[], read_next_path=rn)
    pool2.read_next_done = RP.read_next_adopted(ledger / "dowjones" / "read_next_adopted.jsonl")
    pool2.refill()
    assert not [it for it in pool2.pending if it["kind"] == "search"]


def test_old_links_are_not_queued_and_archive_pages_are_flagged_not_followed(ledger):
    old = (NOW - timedelta(days=40)).strftime("%b. %d, %Y").replace("May.", "May")
    assert RS.is_archive((NOW - timedelta(days=40)).isoformat(), NOW)
    assert not RS.is_archive((NOW - timedelta(days=1)).isoformat(), NOW)
    assert not RS.is_archive(None, NOW)
    assert RS.recency_rank({"published_visible": (NOW - timedelta(hours=2)).isoformat()},
                           NOW) == pytest.approx(2.0)
    assert RS.recency_rank({}, NOW) == 12.0
    # a dated link from 40 days ago on a front is not queued
    snap = (f'- RootWebArea "Markets - CNBC" [ref=e1]\n'
            f'- link "Treasury Yields Jump After the Jobs Report" [ref=e2] [url={CNBC_A1}]\n'
            f'- link "An Old Story About Oil From Last Month" [ref=e3] [url={CNBC_A2}]\n'
            f'  - text "{old}"\n'
            f'- paragraph "' + "market news and analysis " * 12 + '"\n')
    sel = WR.select_front_links(snap, RS.ARTICLE_PATTERN["cnbc"], now=NOW, max_age_days=4)
    assert [lk["url"] for lk in sel["links"]] == [CNBC_A1] and sel["skipped_old"] == [CNBC_A2]
    # a stored article dated 40 days back is flagged archive and its links not followed
    pages = _pages()
    pages[CNBC_A1] = dict(pages[CNBC_A1], text=f"{old}\n" + LONG)
    d = FakeDriver(pages)
    pool, c = _pool(ledger, d, fronts=[_front("cnbc:markets")])
    pool.refill()
    _drain(pool)
    pool.refill()
    _drain(pool)
    opens = [u for v, u in d.actions if v == "open"]
    rec = {r["url"]: r for r in RR.pages_read_since(1, root=ledger, now=c.now())}
    assert rec[CNBC_A1]["published_utc"]                      # the dateline parsed
    assert rec[CNBC_A1]["archive"] is True
    assert FED_PR not in opens
    assert pool.stats["cnbc.com"]["archive_read"] == 1
    assert CNBC_A1 not in {r["url"] for r in RR.pages_read_since(
        1, root=ledger, now=c.now(), include_archive=False)}


def test_a_restart_carries_the_pending_links_to_the_next_pool(ledger, monkeypatch):
    monkeypatch.setattr(RP, "PENDING_CARRY", ledger / "carry.json")
    d = FakeDriver(_pages())
    pool, c = _pool(ledger, d, fronts=[])
    pool.pending = []
    pool._add({"kind": "article", "site": "cnbc", "host": "cnbc.com", "url": CNBC_A2,
               "lane": "front:cnbc:markets", "tier": RS.TIER_FRONT_NEWS})
    pool._add({"kind": "front", "site": "cnbc", "host": "cnbc.com", "url": CNBC_FRONT,
               "key": "front:cnbc:markets"})
    assert pool.save_carry() == 1                             # fronts come round on their own
    pool2, _ = _pool(ledger, FakeDriver(_pages()), fronts=[], clock=c)
    assert pool2.carried_in == 1 and pool2.pending[0]["url"] == CNBC_A2
    assert not (ledger / "carry.json").exists()               # read once


def test_a_paywall_title_is_a_stub_and_an_archive_index_is_not_an_article():
    long_offer = "Subscribe to unlock this article and more. " * 100
    assert WR.classify_page(url="https://www.ft.com/content/x", final_url=None,
                            title="Subscribe to read", raw=long_offer) == "PAYWALL_STUB"
    assert WR.classify_page(url=CNBC_A1, final_url=None, title="Treasury yields jump",
                            raw=LONG) == "OK"
    assert not RS.any_article_pattern(
        "https://www.federalreserve.gov/newsevents/pressreleases/press-release-archive.htm")
    assert RS.any_article_pattern(FED_PR)
