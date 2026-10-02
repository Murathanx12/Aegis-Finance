"""THE READING BUDGET (2026-09-30): the browser's daily page loads spent by
lane (declared shares) and by hour (heavier before and during the Asian and US
sessions), and the supervisor's cap wait that used to never end.

MEASURED the evening before: first-come spent the 4,000 loads by 10:44 UTC and
the reader stood WAITING_FOR_CAP for hours; the supervisor then printed "retry
at 19:14" at 21:25 because its wait was computed from a stale log tail.

Test doubles only (the fake driver / clock / throttle of test_reader_pool,
tmp_path). No network, browser, gateway or Chrome port. No literal calendar
dates: every time is derived from now.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend import config as _config
from backend.services import reader_scheduler as RS
from backend.tests.test_reader_pool import Clock, FakeDriver, _thr
from scripts import night_reader_supervisor as S
from scripts import reader_pool as RP

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _at_utc_hour(h: int) -> datetime:
    return NOW.replace(hour=h, minute=30, second=0)


# ───────────────────────────── the plan (pure) ───────────────────────────────

def test_the_hourly_allowances_sum_to_the_daily_total_and_follow_the_sessions():
    tot = 4000
    hours = [RS.hour_allowance(_at_utc_hour(h), day_total=tot) for h in range(24)]
    assert abs(sum(hours) - tot) <= 24              # rounding only
    us, asia, evening = hours[15], hours[3], hours[21]
    assert us > asia > evening                       # US session > Asia > US evening
    assert min(hours) >= int(getattr(_config, "READER_BUDGET_MIN_PER_HOUR", 60))
    # the quietest hour still reads: never silent for hours at the cap
    assert min(hours) >= 60


def test_the_ten_minute_ceiling_spreads_an_hour():
    a = RS.hour_allowance(_at_utc_hour(15), day_total=4000)
    ten = RS.ten_min_allowance(a)
    assert a / 6 <= ten <= a / 2                     # more than a sixth, far less than the hour


def test_shares_are_normalised_and_cover_every_lane():
    sh = RS.budget_shares()
    assert set(sh) == set(RS.BUDGET_LANES)
    assert abs(sum(sh.values()) - 1.0) < 1e-9
    assert sh["book_names"] > sh["universe_names"] > 0


@pytest.mark.parametrize("item,lane", [
    ({"kind": "robots", "host": "cnbc.com", "lane": "robots:cnbc.com"}, "overhead"),
    ({"kind": "social", "host": "x.com", "ticker": "NVDA"}, "social"),
    ({"kind": "search", "host": "wsj.com", "lane": "search:wsj"}, "digest_asks"),
    ({"kind": "article", "host": "apnews.com", "via": "read_next"}, "digest_asks"),
    ({"kind": "front", "host": "federalreserve.gov", "section": "press_releases"},
     "official_releases"),
    ({"kind": "stock_links", "host": "wsj.com", "ticker": "NVDA"}, "book_names"),
    ({"kind": "stock_text", "host": "marketwatch.com", "ticker": "ZZZZ"}, "universe_names"),
    ({"kind": "article", "host": "barrons.com", "ticker": "NVDA", "tier": 2}, "book_names"),
    ({"kind": "front", "host": "wsj.com", "section": "politics", "lane": "front:wsj:politics"},
     "politics_policy"),
    ({"kind": "article", "host": "cnbc.com", "section": "politics", "tier": 1},
     "politics_policy"),
    ({"kind": "front", "host": "asia.nikkei.com", "section": "business"}, "macro_world"),
    ({"kind": "front", "host": "wsj.com", "section": "economy"}, "macro_world"),
    ({"kind": "front", "host": "barrons.com", "section": "markets"}, "markets_news"),
    ({"kind": "article", "host": "wsj.com", "section": "heard_on_the_street", "tier": 1},
     "markets_news"),
])
def test_every_item_lands_in_a_declared_lane(item, lane):
    got = RS.budget_lane(item, books={"NVDA"}, fresh=set())
    assert got == lane and got in RS.BUDGET_LANES


def _v(lane, **kw):
    base = dict(now=_at_utc_hour(15), loads_60m=0, loads_10m=0, lane_60m={}, lane_24h={},
                servable_lanes={lane}, day_total=4000)
    base.update(kw)
    return RS.budget_verdict(lane, **base)


def test_a_lane_under_its_share_is_served():
    ok, why = _v("book_names", servable_lanes={"book_names", "markets_news"})
    assert ok and why == "OWN_SHARE"


def test_a_lane_over_its_share_leaves_the_page_to_a_starving_lane():
    allow = RS.hour_allowance(_at_utc_hour(15), day_total=4000)
    q = RS.lane_hour_quota("markets_news", allow)
    ok, why = _v("markets_news", lane_60m={"markets_news": q}, loads_60m=q, loads_10m=0,
                 servable_lanes={"markets_news", "book_names"})
    assert not ok and why == "LEAVE_FOR:book_names"


def test_an_idle_share_is_borrowed_when_nobody_else_can_use_it():
    allow = RS.hour_allowance(_at_utc_hour(15), day_total=4000)
    q = RS.lane_hour_quota("markets_news", allow)
    ok, why = _v("markets_news", lane_60m={"markets_news": q}, loads_60m=q,
                 servable_lanes={"markets_news"})
    assert ok and why == "BORROW"


def test_the_hour_and_the_ten_minutes_refuse_everyone():
    allow = RS.hour_allowance(_at_utc_hour(15), day_total=4000)
    ok, why = _v("book_names", loads_60m=allow)
    assert not ok and why.startswith("HOUR_BUDGET_SPENT")
    ok, why = _v("book_names", loads_10m=RS.ten_min_allowance(allow))
    assert not ok and why.startswith("PACE_10M")


def test_a_lane_that_spent_its_day_borrows_nothing_while_another_waits():
    mult = float(getattr(_config, "READER_BUDGET_LANE_DAY_MULT", 1.6))
    day = int(RS.budget_shares()["social"] * 4000 * mult) + 1
    ok, why = _v("social", lane_24h={"social": day}, servable_lanes={"social", "book_names"})
    assert not ok and why.startswith("LANE_DAY_SHARE_SPENT")
    ok, _ = _v("social", lane_24h={"social": day}, servable_lanes={"social"})
    assert ok                                      # alone, it may still read


def test_lane_counts_window_the_rows():
    rows = [{"t": (NOW - timedelta(minutes=5)).isoformat(), "lane": "social", "host": "x.com",
             "outcome": "OK"},
            {"t": (NOW - timedelta(minutes=50)).isoformat(), "lane": "social", "host": "x.com",
             "outcome": "BLANK"},
            {"t": (NOW - timedelta(hours=5)).isoformat(), "lane": "book_names", "host": "wsj.com",
             "outcome": "OK"},
            {"t": (NOW - timedelta(hours=30)).isoformat(), "lane": "book_names", "host": "wsj.com",
             "outcome": "OK"}]
    c = RS.lane_counts(rows, NOW)
    assert c["loads_10m"] == 1 and c["loads_60m"] == 2 and c["loads_24h"] == 3
    assert c["lane_60m"]["social"] == 2 and c["ok_lane_60m"]["social"] == 1
    assert c["lane_24h"]["book_names"] == 1 and c["ok_host_24h"]["wsj.com"] == 1


# ───────────────────────────── the pool applies it ───────────────────────────

@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(RP, "DJ", tmp_path / "dowjones")
    monkeypatch.setattr(RP, "FRONT_SCHEDULE", tmp_path / "dowjones" / "front_schedule.json")
    monkeypatch.setattr(RP, "SOCIAL_SEEN", tmp_path / "social_seen.jsonl")
    return tmp_path


def _pool(ledger, clock, **kw):
    thr = _thr(ledger, clock, wait_on_hour_cap=True)
    gov = RS.TabGovernor(max_tabs=4, mem_fn=lambda: 9.0, target=4)
    return RP.Pool(driver=FakeDriver({}), throttle=thr, names=[], books={"NVDA"}, fresh=set(),
                   fronts=[], social=False, stock_pages=(), governor=gov,
                   cooling=RS.HostCooling(path=ledger / "cool.json"), stored={},
                   now_fn=clock.now, wait_fn=lambda s: False, caption_fetch=lambda u: {},
                   dropped=set(), front_last={}, stock_last={}, social_last={},
                   printer=lambda *a: None, reader_sleep=lambda s: None, persist=False,
                   budget=True, **kw), thr


def test_the_pool_serves_the_starving_lane_first(ledger):
    c = Clock(_at_utc_hour(15))
    pool, thr = _pool(ledger, c)
    allow = RS.hour_allowance(c.now())
    q = RS.lane_hour_quota("markets_news", allow)
    pool.budget_rows = [{"t": (c.now() - timedelta(minutes=30)).isoformat(),
                         "lane": "markets_news", "host": "barrons.com", "outcome": "OK"}] * q
    pool._add({"kind": "front", "site": "barrons", "host": "barrons.com", "section": "markets",
               "lane": "front:barrons:markets", "url": "https://www.barrons.com/topics/markets",
               "key": "front:barrons:markets"})
    pool._add({"kind": "stock_links", "site": "wsj", "host": "wsj.com", "lane": "wsj:stock",
               "ticker": "NVDA", "url": "https://www.wsj.com/market-data/quotes/NVDA",
               "key": "wsj:stock:NVDA"})
    it = pool.take(0)
    assert it is not None and it["blane"] == "book_names"
    assert pool.budget_block["verdicts"]["markets_news"].startswith("LEAVE_FOR")


def test_a_spent_hour_is_a_healthy_wait_not_a_stall(ledger):
    c = Clock(_at_utc_hour(21))
    pool, thr = _pool(ledger, c)
    allow = RS.hour_allowance(c.now())
    thr.path.parent.mkdir(parents=True, exist_ok=True)
    thr.path.write_text("".join(f"{(c.now() - timedelta(minutes=40, seconds=i)).isoformat()} "
                                f"wsj.com 30.0\n" for i in range(allow)), encoding="utf-8")
    pool._add({"kind": "front", "site": "barrons", "host": "barrons.com", "section": "markets",
               "lane": "front:barrons:markets", "url": "https://www.barrons.com/topics/markets",
               "key": "front:barrons:markets"})
    assert pool.take(0) is None
    assert pool.budget_block["state"] == "WAITING_FOR_BUDGET"
    st = pool.status()
    assert st["queue_state"] == RS.Q_WAITING_FOR_CAP
    assert st["budget"]["lanes"]["markets_news"]["pending"] == 1
    # the supervisor reads WAITING_FOR_CAP as healthy
    assert S.derive_state(alive=True, repairing=False, ok_10m=0, last_ok_age=3000.0,
                          since_launch_s=3600, next_slot_in_s=None, attempts_10m=0,
                          pool_state=RS.Q_WAITING_FOR_CAP) == S.WAITING_FOR_CAP


def test_the_day_cap_makes_the_pool_wait_instead_of_exit(ledger):
    c = Clock(_at_utc_hour(15))
    pool, thr = _pool(ledger, c)
    thr.max_per_day = 5
    thr.path.parent.mkdir(parents=True, exist_ok=True)
    thr.path.write_text("".join(f"{(c.now() - timedelta(hours=3, minutes=i)).isoformat()} "
                                f"wsj.com 30.0\n" for i in range(5)), encoding="utf-8")
    pool._add({"kind": "front", "site": "barrons", "host": "barrons.com", "section": "markets",
               "lane": "front:barrons:markets", "url": "https://www.barrons.com/topics/markets",
               "key": "front:barrons:markets"})
    assert pool.take(0) is None
    assert pool.budget_block["state"] == "WAITING_FOR_CAP"
    assert pool.stop_reason is None and not pool.stop_event.is_set()


def test_every_spent_load_is_one_budget_row(ledger):
    c = Clock(_at_utc_hour(15))
    pool, _ = _pool(ledger, c)
    it = {"kind": "front", "host": "wsj.com", "section": "politics", "blane": "politics_policy"}
    pool._budget_record(it, "OK")
    assert pool.budget_rows[-1]["lane"] == "politics_policy"
    assert pool.status()["budget"]["lanes"]["politics_policy"]["ok_60m"] == 1


# ───────────────────── the supervisor's cap wait (the 19:14 bug) ─────────────

def test_the_cap_wait_is_read_from_the_window_not_from_the_last_launch():
    now = NOW
    stamps = [now - timedelta(hours=23, minutes=50)] * 30 + [now - timedelta(hours=2)] * 70
    # 100 loads, cap 100, 20 room wanted: 20 must age out; they do in 10 minutes
    w = S.caps_wait_s(stamps, now, 100, min_room=20)
    assert 9 * 60 <= w <= 11 * 60
    # the window already has room: relaunch now
    assert S.caps_wait_s(stamps[:50], now, 100, min_room=20) == 0.0
    # an old day is not in the window at all
    assert S.caps_wait_s([now - timedelta(days=2)] * 500, now, 100) == 0.0


def test_the_official_run_is_launched_on_its_interval_and_never_twice():
    assert S.official_due(0.0, 10_000.0, every_s=900, child_alive=False, enabled=True)
    assert not S.official_due(9_500.0, 10_000.0, every_s=900, child_alive=False, enabled=True)
    assert not S.official_due(0.0, 10_000.0, every_s=900, child_alive=True, enabled=True)
    assert not S.official_due(0.0, 10_000.0, every_s=900, child_alive=False, enabled=False)
