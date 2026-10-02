"""What the reader pool reads next, how many tabs it may hold, and which hosts
are cooling -- pure rules, one place, pinned by tests.

Murat, 2026-09-28 21:45 HKT: "can openclaw read more, can it launch another
chrome tabs to read too, this one by one is very slow, it needs to read wsj,
barron, marketwatch per stock and the news from that too, it should navigate
them, not just the stocks, and also the media too." Earlier: "it should always
work and shouldnt be standing idle."

* `SECTION_FRONTS` -- the sites' own navigation: each section front with the
  URL(s) to try. A URL that comes back NOT_FOUND is recorded once
  (`sections_not_found.json`) and dropped; the next candidate is tried.
* `front_interval_s` / `front_due` -- front page and markets every 30 min in US
  hours, everything else every 2 h.
* `priority_key` -- THE ordering rule (below).
* `choose` -- which host a free tab serves next (a host free now beats a
  host that would make the tab wait).
* `TabGovernor` -- the memory governor.
* `HostCooling` -- a host that showed a challenge / block / login wall / rate
  limit is not opened again until its cooling period ends.
* `may_follow_related` -- the depth-1 "related / read next" rule.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from backend import config as _config
from backend.services import disk_guard as DG


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


# ───────────────────────────── the section fronts ────────────────────────────
#
# `urls`: candidates in order; the first not recorded as NOT_FOUND is loaded.
# `fast`: refreshed every READER_FRONT_FAST_S during US hours.
# `kind`: "front" (links are followed) or "front_text" (a data page whose text
# and table rows are stored: calendars, upgrades/downgrades).

WSJ_ARTICLE = (r"^https://www\.wsj\.com/(?!news/|market-data|video|podcasts|livecoverage|buyside)"
               r"[a-z-]+/[a-z0-9/-]*-[0-9a-f]{8}(\?|$)")
BARRONS_ARTICLE = r"^https://www\.barrons\.com/articles/[a-z0-9-]+-[0-9a-f]{8}(\?|$)"
MW_ARTICLE = r"^https://www\.marketwatch\.com/(story|articles?)/[a-z0-9-]+-[0-9a-f]{8}(\?|$)"
ARTICLE_PATTERN = {"wsj": WSJ_ARTICLE, "barrons": BARRONS_ARTICLE, "marketwatch": MW_ARTICLE}
#: an EPISODE / clip page (a show or series index is two segments shorter and
#: lists items without their transcripts; measured live 2026-09-28)
MEDIA_PATTERN = {
    "wsj": r"^https://www\.wsj\.com/(video|podcasts)/[a-z0-9_.-]+/[a-z0-9_.-]+/[a-z0-9/_.-]{6,}",
    "barrons": r"^https://www\.barrons\.com/(video|podcasts?)/[a-z0-9_.-]+/[a-z0-9/_.-]{6,}",
    "marketwatch": r"^https://www\.marketwatch\.com/(video|podcasts?)/[a-z0-9_.-]+/[a-z0-9/_.-]{6,}",
}
#: sister-site article links a stock page may carry (both hosts are allowed)
ANY_DJ_ARTICLE = "|".join((WSJ_ARTICLE, BARRONS_ARTICLE, MW_ARTICLE))

SECTION_FRONTS: tuple[dict, ...] = (
    {"site": "wsj", "section": "home", "fast": True, "urls": ("https://www.wsj.com/",)},
    {"site": "wsj", "section": "markets", "fast": True,
     "urls": ("https://www.wsj.com/finance", "https://www.wsj.com/news/markets")},
    {"site": "wsj", "section": "business", "urls": ("https://www.wsj.com/business",)},
    {"site": "wsj", "section": "tech", "urls": ("https://www.wsj.com/tech",)},
    {"site": "wsj", "section": "economy", "urls": ("https://www.wsj.com/economy",)},
    {"site": "wsj", "section": "world", "urls": ("https://www.wsj.com/world",)},
    {"site": "wsj", "section": "heard_on_the_street",
     "urls": ("https://www.wsj.com/news/heard-on-the-street",)},
    {"site": "wsj", "section": "latest_headlines",
     "urls": ("https://www.wsj.com/news/latest-headlines",)},
    {"site": "barrons", "section": "home", "fast": True, "urls": ("https://www.barrons.com/",)},
    {"site": "barrons", "section": "markets", "fast": True,
     "urls": ("https://www.barrons.com/topics/markets",)},
    {"site": "barrons", "section": "stock_picks",
     "urls": ("https://www.barrons.com/topics/stock-picks",
              "https://www.barrons.com/market-data/stocks/stock-picks")},
    {"site": "barrons", "section": "technology",
     "urls": ("https://www.barrons.com/topics/technology",)},
    {"site": "barrons", "section": "economy_and_policy",
     "urls": ("https://www.barrons.com/topics/economy-and-policy",)},
    {"site": "barrons", "section": "latest_news",
     "urls": ("https://www.barrons.com/real-time", "https://www.barrons.com/news")},
    {"site": "barrons", "section": "up_and_down_wall_street",
     "urls": ("https://www.barrons.com/topics/up-and-down-wall-street",)},
    {"site": "barrons", "section": "the_trader", "urls": ("https://www.barrons.com/topics/the-trader",)},
    {"site": "barrons", "section": "streetwise", "urls": ("https://www.barrons.com/topics/streetwise",)},
    {"site": "marketwatch", "section": "home", "fast": True,
     "urls": ("https://www.marketwatch.com/",)},
    {"site": "marketwatch", "section": "latest_news",
     "urls": ("https://www.marketwatch.com/latest-news",)},
    {"site": "marketwatch", "section": "markets", "fast": True,
     "urls": ("https://www.marketwatch.com/markets",)},
    {"site": "marketwatch", "section": "investing",
     "urls": ("https://www.marketwatch.com/investing",)},
    {"site": "marketwatch", "section": "stocks",
     "urls": ("https://www.marketwatch.com/investing/stocks",
              "https://www.marketwatch.com/markets/us")},
    {"site": "marketwatch", "section": "economy_and_politics",
     "urls": ("https://www.marketwatch.com/economy-politics",)},
    {"site": "marketwatch", "section": "earnings",
     "urls": ("https://www.marketwatch.com/investing/earnings",
              "https://www.marketwatch.com/markets/earnings")},
    {"site": "marketwatch", "section": "upgrades_downgrades", "kind": "front_text",
     "urls": ("https://www.marketwatch.com/tools/upgrades-downgrades",
              "https://www.marketwatch.com/tools/upgradesdowngrades")},
    {"site": "marketwatch", "section": "economic_calendar", "kind": "front_text",
     "urls": ("https://www.marketwatch.com/economy-politics/calendar",
              "https://www.marketwatch.com/tools/calendars/economic")},
    {"site": "marketwatch", "section": "earnings_calendar", "kind": "front_text",
     "urls": ("https://www.marketwatch.com/tools/earnings-calendar",
              "https://www.marketwatch.com/tools/earningscalendar")},
    # 2026-09-29, the BROWSE lane (Murat: "browse the news like a human to get the
    # context ... not only stock forecast"): politics, opinion, commodities and the
    # video / podcast fronts. A URL that is not found is recorded once and dropped.
    {"site": "wsj", "section": "politics", "urls": ("https://www.wsj.com/politics",)},
    {"site": "wsj", "section": "opinion", "urls": ("https://www.wsj.com/opinion",)},
    {"site": "wsj", "section": "video", "urls": ("https://www.wsj.com/video",)},
    {"site": "wsj", "section": "podcasts", "urls": ("https://www.wsj.com/podcasts",)},
    {"site": "barrons", "section": "commodities",
     "urls": ("https://www.barrons.com/topics/commodities",)},
    {"site": "barrons", "section": "video", "urls": ("https://www.barrons.com/video",)},
    {"site": "barrons", "section": "podcasts", "urls": ("https://www.barrons.com/podcasts",)},
    {"site": "marketwatch", "section": "personal_finance",
     "urls": ("https://www.marketwatch.com/personal-finance",)},
)

#: The per-stock pages (the MarketWatch analyst page is TEXT that is stored; the
#: other three are link pages whose news is followed).
STOCK_PAGES: tuple[dict, ...] = (
    {"site": "marketwatch", "lane": "marketwatch:analyst", "kind": "stock_text",
     "url": "https://www.marketwatch.com/investing/stock/{ticker}/analystestimates",
     "column": "mw_analyst_estimates"},
    {"site": "marketwatch", "lane": "marketwatch:stock", "kind": "stock_links",
     "url": "https://www.marketwatch.com/investing/stock/{ticker}"},
    {"site": "wsj", "lane": "wsj:stock", "kind": "stock_links",
     "url": "https://www.wsj.com/market-data/quotes/{TICKER}"},
    {"site": "barrons", "lane": "barrons:stock", "kind": "stock_links",
     "url": "https://www.barrons.com/market-data/stocks/{ticker}"},
)


def site_ticker(ticker: str) -> str:
    return (ticker or "").strip().replace("-", ".").replace("/", ".").replace(" ", "")


def stock_url(page: dict, ticker: str) -> str:
    t = site_ticker(ticker)
    return page["url"].format(ticker=t.lower(), TICKER=t.upper())


def site_host(site: str) -> str:
    return f"{site}.com"


# ─────────────────────────── the front schedule ──────────────────────────────

def us_hours(now: datetime) -> bool:
    """PURE. Weekday 09:00-17:00 in New York."""
    try:
        from zoneinfo import ZoneInfo
        ny = now.astimezone(ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001 -- no tz database: a fixed -4 h offset
        ny = now.astimezone(timezone(timedelta(hours=-4)))
    return ny.weekday() < 5 and 9 <= ny.hour < 17


def front_interval_s(front: dict, now: datetime) -> float:
    """PURE. How often `front` is re-read at `now`."""
    fast = float(_cfg("READER_FRONT_FAST_S", 1800.0))
    slow = float(_cfg("READER_FRONT_SLOW_S", 7200.0))
    return fast if front.get("fast") and us_hours(now) else slow


def front_due(front: dict, last_read: datetime | None, now: datetime) -> bool:
    """PURE. Never read, or read at least one interval ago."""
    return last_read is None or (now - last_read).total_seconds() >= front_interval_s(front, now)


def front_url(front: dict, dropped: set[str]) -> str | None:
    """PURE. The first candidate URL not recorded as NOT_FOUND; None when every
    candidate was dropped (the section is then gone for good)."""
    return next((u for u in front["urls"] if u not in dropped), None)


def front_key(front: dict) -> str:
    return f"{front['site']}:{front['section']}"


# ───────────────────────────── THE ORDERING RULE ─────────────────────────────

TIER_FRONT, TIER_FRONT_NEWS, TIER_BOOK, TIER_FRESH, TIER_REST = 0, 1, 2, 3, 4
TIER_NAMES = {0: "section front due", 1: "news a front showed", 2: "book / contest name",
              3: "fresh SEC filing or alert", 4: "rest of the universe"}


def ticker_tier(ticker: str | None, *, books: set[str], fresh: set[str]) -> int:
    t = (ticker or "").upper()
    if t and t in books:
        return TIER_BOOK
    if t and t in fresh:
        return TIER_FRESH
    return TIER_REST


def priority_key(item: dict, *, books: set[str], fresh: set[str],
                 last_read: dict[str, str]) -> tuple:
    """PURE. THE ordering rule of the reader pool (smaller = sooner).

    1. tier: a DUE section front (0); the news a front showed (1); a name in
       the frozen books or the contest candidates (2); a name with a fresh SEC
       filing or an alert today (3); the rest of the universe (4). An item
       found on a page (an article link, a related link) inherits its
       parent's tier (`item["tier"]`), so a book name's news stays a book
       name's news.
    2. inside a tier, what a page already SHOWED (a found link, depth >= 0 with
       a parent) comes before a new list page -- found news is read before the
       next list is opened;
    3. then the name read longest ago ('' = never read comes first);
    4. then how recent the link's visible date is (2026-09-29: hours since
       `published_visible`; undated = 12 h), so today's news is read before
       last week's;
    5. then the link's position on its page (1 = most prominent);
    6. then the order it was found in (`seq`)."""
    if item.get("kind") in ("front", "front_text"):
        tier = TIER_FRONT
    elif item.get("tier") is not None:
        tier = int(item["tier"])
    else:
        tier = ticker_tier(item.get("ticker"), books=books, fresh=fresh)
    found = 0 if item.get("parent_url") else 1
    lr = last_read.get((item.get("ticker") or "").upper(), "") if item.get("ticker") else ""
    return (tier, found, lr, round(recency_rank(item), 1), int(item.get("position") or 0),
            int(item.get("seq") or 0))


def choose(pending: dict[str, list[dict]], *, free_slots: dict[str, int],
           blocked: set[str] | frozenset[str], free_at: dict[str, datetime], now: datetime,
           key: Callable[[dict], tuple], ready_slack_s: float = 5.0,
           in_flight: dict[str, int] | None = None) -> dict | None:
    """PURE. The item a free tab serves next. Candidates are hosts with a free
    tab slot, not blocked (cooling / capped) and something pending. Among them
    only hosts free within `ready_slack_s` of the soonest one are considered --
    a tab does not wait for a busy host while another host can be read now --
    and among those the host with the FEWEST tabs in flight is served first
    (every host gets a tab before any host gets a second: measured live on
    2026-09-28, with the governor below the maximum the three Dow Jones sites
    took every slot and the social hosts waited), then the best `key`."""
    cands = [h for h, items in pending.items()
             if items and free_slots.get(h, 0) > 0 and h not in blocked]
    if not cands:
        return None
    soonest = min(max(now, free_at.get(h, now)) for h in cands)
    ready = [h for h in cands
             if max(now, free_at.get(h, now)) <= soonest + timedelta(seconds=ready_slack_s)]
    best, best_k = None, None
    fl = in_flight or {}
    for h in ready:
        it = min(pending[h], key=key)
        k = (int(fl.get(h, 0)), *key(it))
        if best_k is None or k < best_k:
            best, best_k = it, k
    return best


def may_follow_related(parent: dict, link_url: str, *, universe: set[str],
                       named: list[str], pattern: str) -> bool:
    """PURE. A "related / read next" link is followed only (1) from an article
    at depth 0 (so depth never exceeds READER_RELATED_DEPTH = 1), (2) when the
    article names a ticker in the universe, (3) on the same host, (4) when it
    matches that host's article pattern."""
    import re
    from urllib.parse import urlsplit
    depth_max = int(_cfg("READER_RELATED_DEPTH", 1))
    if int(parent.get("depth") or 0) + 1 > depth_max:
        return False
    if not any(t in universe for t in (named or [])):
        return False
    ph = (urlsplit(parent.get("url") or "").hostname or "").lower().removeprefix("www.")
    lh = (urlsplit(link_url or "").hostname or "").lower().removeprefix("www.")
    if not ph or ph != lh:
        return False
    return bool(re.search(pattern, link_url or ""))


# ─────────────────────────────── the governor ────────────────────────────────

@dataclass
class TabGovernor:
    """How many tabs the pool may hold at once, from free system memory.

    * below `floor_gb` free: no new tab; the target falls by one per update,
      never below 1 (tabs are closed after each read, so an idle tab never
      exists -- the slots above the target simply stop opening);
    * at or above `grow_gb` free: the target rises by one per update, up to
      `max_tabs` (the gap between the two is hysteresis, so it does not flap);
    * memory unreadable: the target holds, and says so.
    `reason` is what the status file prints."""
    max_tabs: int = field(default_factory=lambda: int(_cfg("READER_MAX_TABS", 6)))
    floor_gb: float = field(default_factory=lambda: float(_cfg("READER_MIN_FREE_GB", 2.0)))
    grow_gb: float = field(default_factory=lambda: float(_cfg("READER_GROW_FREE_GB", 2.6)))
    #: what one more tab is assumed to cost; growth needs this much headroom
    #: ABOVE the floor (2026-09-29)
    tab_gb: float = field(default_factory=lambda: float(_cfg("READER_TAB_GB", 0.5)))
    mem_fn: Callable[[], float | None] | None = None
    target: int = 1
    reason: str = "starting at 1 tab"
    free_gb: float | None = None
    history: list[dict] = field(default_factory=list)

    def _free(self) -> float | None:
        if self.mem_fn is None:
            from backend.services import web_reader as WR
            return WR.free_memory_gb()
        try:
            return self.mem_fn()
        except Exception:  # noqa: BLE001 -- unreadable
            return None

    def update(self, open_tabs: int | None = None) -> int:
        """`open_tabs`: tabs actually open now (their memory is already in
        `free`); the adaptive maximum counts headroom above THEM."""
        free = self._free()
        self._open = self.target if open_tabs is None else int(open_tabs)
        self.free_gb = free
        old = self.target
        if free is None:
            self.reason = f"free memory unreadable: holding at {self.target}"
        elif free < self.floor_gb:
            # a deep deficit (more than a tab's worth under the floor) sheds two
            step = 2 if free < self.floor_gb - self.tab_gb else 1
            self.target = max(1, self.target - step)
            self.reason = (f"free memory {free:.1f} GB < floor {self.floor_gb:.1f} GB: "
                           f"no new tab, target {self.target}")
        elif (free >= self.grow_gb and self.target < self.effective_max(free)):
            self.target += 1
            self.reason = (f"free memory {free:.1f} GB >= {self.grow_gb:.1f} GB: "
                           f"grew to {self.target} of {self.effective_max(free)} "
                           f"(max {self.max_tabs})")
        else:
            self.reason = (f"free memory {free:.1f} GB: holding at {self.target} of "
                           f"{self.effective_max(free)} (max {self.max_tabs})")
        if self.target != old:
            self.history.append({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "from": old, "to": self.target, "free_gb": free})
        return self.target

    def effective_max(self, free: float | None) -> int:
        """The ADAPTIVE maximum: the tabs held now plus as many more as fit
        above the floor at `tab_gb` each, never above `max_tabs`, never below 1."""
        base = getattr(self, "_open", None)
        base = self.target if base is None else base
        if free is None:
            return max(1, min(self.max_tabs, self.target))
        headroom = int(max(0.0, free - self.floor_gb) // max(self.tab_gb, 0.05))
        return max(1, min(self.max_tabs, base + headroom))

    def may_open(self, open_tabs: int) -> bool:
        """Before a tab is opened: memory re-read; below the floor only the
        very first tab may open (the reader never stops entirely)."""
        free = self._free()
        self.free_gb = free
        if free is not None and free < self.floor_gb and open_tabs >= 1:
            self.reason = (f"free memory {free:.1f} GB < floor {self.floor_gb:.1f} GB: "
                           f"no new tab while {open_tabs} open")
            return False
        return open_tabs < self.target


# ────────────────────────────── host cooling ─────────────────────────────────

def cooling_path() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "dowjones" / "host_cooling.json"


@dataclass
class HostCooling:
    """`{host: {until, why, url, since}}`, persisted, file-locked. A host in it
    is not opened again until `until` (config READER_HOST_COOL_S after the page
    that caused it). Nothing is done to get around the page that caused it."""
    path: Path = field(default_factory=cooling_path)
    seconds: float = field(default_factory=lambda: float(_cfg("READER_HOST_COOL_S", 3600.0)))

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def cool(self, host: str, why: str, url: str, now: datetime) -> dict:
        with DG.file_lock(self.path.with_name(self.path.name + ".lock")):
            d = self._read()
            row = {"until": (now + timedelta(seconds=self.seconds)).isoformat(timespec="seconds"),
                   "why": str(why)[:200], "url": str(url)[:300],
                   "since": now.isoformat(timespec="seconds")}
            d[host] = row
            DG.atomic_write_json(self.path, d)
        return row

    def active(self, now: datetime) -> dict:
        out = {}
        for h, r in self._read().items():
            try:
                if datetime.fromisoformat(r["until"]) > now:
                    out[h] = r
            except (KeyError, ValueError, TypeError):
                continue
        return out


# ─────────────────────────── sections not found ──────────────────────────────

def sections_not_found_path() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "dowjones" / "sections_not_found.json"


def dropped_section_urls(path: Path | None = None) -> set[str]:
    try:
        return set(json.loads((path or sections_not_found_path()).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def record_section_not_found(url: str, why: str, now: datetime, path: Path | None = None) -> bool:
    """Record a section URL that came back NOT_FOUND, once. True when new."""
    p = path or sections_not_found_path()
    with DG.file_lock(p.with_name(p.name + ".lock")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        if url in d:
            return False
        d[url] = {"first_seen_utc": now.isoformat(timespec="seconds"), "why": str(why)[:200]}
        DG.atomic_write_json(p, d)
    return True


# ═════════════════════ THE BROWSE LANE (2026-09-29) ══════════════════════════
#
# Murat, 2026-09-29: "digest the news see what they are implying is there an
# another path they are leading, not only the forecast from the websites but the
# stocks news and the general news brose the news like a human to get the
# context, ot speisifcaly search something not only stock forecast". And: "it
# shuld always work and shouldnt be standing idle".
#
# MEASURED that morning: the pool read 0 pages for 100+ minutes with the three
# Dow Jones hosts at 437-628 of 1,200 pages for the day and `pending: 0` on each.
# Every stock page and every front link had been read, fronts were due only
# every 2 h outside US hours, and nothing refilled the list; the supervisor
# called that STALLED and restarted the pool every ~15 minutes.
#
# So: (1) general-news fronts on free public sites (`NEWS_FRONTS`, hosts in
# `config.OPENCLAW_NEWS_HOSTS`); (2) a host whose pending list falls to the
# low-water mark has its fronts revisited after `READER_FRONT_MIN_REVISIT_S`
# instead of their scheduled interval (`front_due_now`); (3) an empty list with
# caps free is its own state, QUEUE_EMPTY / REFILLING (`host_queue_state`),
# never a stall. Nothing here disguises automation: a bot check, block, paywall
# or robots refusal is recorded by class and the host is left alone.

#: site key -> the host it reads and its article / media URL shapes
NEWS_SITES: dict[str, dict] = {
    "reuters": {"host": "reuters.com",
                "article": r"^https://www\.reuters\.com/(world|business|markets|technology|legal|"
                           r"breakingviews|sustainability|science)/[a-z0-9/_-]*-\d{4}-\d{2}-\d{2}/?(\?|$)"},
    "apnews": {"host": "apnews.com", "article": r"^https://apnews\.com/article/[a-z0-9-]{8,}"},
    "cnbc": {"host": "cnbc.com",
             "article": r"^https://www\.cnbc\.com/\d{4}/\d{2}/\d{2}/[a-z0-9-]+\.html",
             "media": r"^https://www\.cnbc\.com/video/\d{4}/\d{2}/\d{2}/[a-z0-9-]+\.html"},
    "yahoo": {"host": "finance.yahoo.com",
              "article": r"^https://finance\.yahoo\.com/(news|m/[0-9a-f-]+|markets/[a-z-]+/articles)/"
                         r"[a-z0-9-]{12,}\.html",
              "media": r"^https://finance\.yahoo\.com/video/[a-z0-9-]{12,}\.html"},
    "bbc": {"host": "bbc.com",
            "article": r"^https://www\.bbc\.com/news/(articles/[a-z0-9]{8,}|[a-z-]+-\d{6,})",
            "media": r"^https://www\.bbc\.com/news/videos/[a-z0-9]{8,}"},
    "ft": {"host": "ft.com",
           "article": r"^https://www\.ft\.com/content/[0-9a-f]{8}-[0-9a-f-]{27}"},
    "nikkei": {"host": "asia.nikkei.com",
               "article": r"^https://asia\.nikkei\.com/[a-z-]+(/[a-z0-9-]+){0,4}/"
                          r"[a-z0-9]+(-[a-z0-9]+){3,}/?(\?|$)"},
    "scmp": {"host": "scmp.com",
             "article": r"^https://www\.scmp\.com/[a-z-]+(/[a-z0-9-]+)*/article/\d{6,}/"},
    "fed": {"host": "federalreserve.gov",
            "article": r"^https://www\.federalreserve\.gov/newsevents/(pressreleases|speech|"
                       r"testimony)/(?![a-z-]*archive)[a-z0-9-]+\.htm"},
    "bls": {"host": "bls.gov", "article": r"^https://www\.bls\.gov/news\.release/[a-z0-9_.]+\.htm"},
    "sec": {"host": "sec.gov",
            "article": r"^https://www\.sec\.gov/newsroom/(press-releases|speeches-statements)/"
                       r"[a-z0-9-]{4,}"},
    "treasury": {"host": "home.treasury.gov",
                 "article": r"^https://home\.treasury\.gov/news/press-releases/[a-z]{2}\d{3,}"},
}
for _k, _v in NEWS_SITES.items():
    ARTICLE_PATTERN.setdefault(_k, _v["article"])
    if _v.get("media"):
        MEDIA_PATTERN.setdefault(_k, _v["media"])

#: General-news section fronts (free public pages). `host` names the host
#: explicitly (a Dow Jones front derives it from `site`).
NEWS_FRONTS: tuple[dict, ...] = (
    {"site": "reuters", "section": "home", "urls": ("https://www.reuters.com/",)},
    {"site": "reuters", "section": "business", "urls": ("https://www.reuters.com/business/",)},
    {"site": "reuters", "section": "markets", "urls": ("https://www.reuters.com/markets/",)},
    {"site": "reuters", "section": "world", "urls": ("https://www.reuters.com/world/",)},
    {"site": "reuters", "section": "technology", "urls": ("https://www.reuters.com/technology/",)},
    {"site": "reuters", "section": "commodities",
     "urls": ("https://www.reuters.com/markets/commodities/",)},
    {"site": "apnews", "section": "home", "urls": ("https://apnews.com/",)},
    {"site": "apnews", "section": "business", "urls": ("https://apnews.com/business",)},
    {"site": "apnews", "section": "markets", "urls": ("https://apnews.com/hub/financial-markets",)},
    {"site": "apnews", "section": "politics", "urls": ("https://apnews.com/politics",)},
    {"site": "apnews", "section": "world", "urls": ("https://apnews.com/world-news",)},
    {"site": "apnews", "section": "technology", "urls": ("https://apnews.com/technology",)},
    {"site": "cnbc", "section": "home", "urls": ("https://www.cnbc.com/world/",)},
    {"site": "cnbc", "section": "markets", "urls": ("https://www.cnbc.com/markets/",)},
    {"site": "cnbc", "section": "economy", "urls": ("https://www.cnbc.com/economy/",)},
    {"site": "cnbc", "section": "technology", "urls": ("https://www.cnbc.com/technology/",)},
    {"site": "cnbc", "section": "politics", "urls": ("https://www.cnbc.com/politics/",)},
    {"site": "cnbc", "section": "asia", "urls": ("https://www.cnbc.com/asia-markets/",
                                                 "https://www.cnbc.com/world-markets/")},
    {"site": "cnbc", "section": "video", "urls": ("https://www.cnbc.com/video/",
                                                  "https://www.cnbc.com/latest-video/")},
    {"site": "yahoo", "section": "home", "urls": ("https://finance.yahoo.com/",)},
    {"site": "yahoo", "section": "latest_news",
     "urls": ("https://finance.yahoo.com/topic/latest-news/", "https://finance.yahoo.com/news/")},
    {"site": "yahoo", "section": "stock_market",
     "urls": ("https://finance.yahoo.com/topic/stock-market-news/",)},
    {"site": "yahoo", "section": "economy",
     "urls": ("https://finance.yahoo.com/topic/economic-news/",)},
    {"site": "bbc", "section": "business", "urls": ("https://www.bbc.com/business",)},
    {"site": "bbc", "section": "world", "urls": ("https://www.bbc.com/news/world",)},
    {"site": "ft", "section": "home", "urls": ("https://www.ft.com/",)},
    {"site": "ft", "section": "markets", "urls": ("https://www.ft.com/markets",)},
    {"site": "ft", "section": "world", "urls": ("https://www.ft.com/world",)},
    {"site": "ft", "section": "companies", "urls": ("https://www.ft.com/companies",)},
    {"site": "nikkei", "section": "home", "urls": ("https://asia.nikkei.com/",)},
    {"site": "nikkei", "section": "business", "urls": ("https://asia.nikkei.com/business",)},
    {"site": "nikkei", "section": "economy", "urls": ("https://asia.nikkei.com/economy",)},
    {"site": "nikkei", "section": "markets", "urls": ("https://asia.nikkei.com/business/markets",)},
    {"site": "scmp", "section": "business", "urls": ("https://www.scmp.com/business",)},
    {"site": "scmp", "section": "economy", "urls": ("https://www.scmp.com/economy",)},
    {"site": "scmp", "section": "tech", "urls": ("https://www.scmp.com/tech",)},
    {"site": "scmp", "section": "china", "urls": ("https://www.scmp.com/news/china",)},
    {"site": "fed", "section": "press_releases",
     "urls": ("https://www.federalreserve.gov/newsevents/pressreleases.htm",)},
    {"site": "fed", "section": "speeches",
     "urls": ("https://www.federalreserve.gov/newsevents/speeches.htm",
              "https://www.federalreserve.gov/newsevents/speeches-testimony.htm")},
    {"site": "bls", "section": "news_releases", "urls": ("https://www.bls.gov/bls/newsrels.htm",)},
    {"site": "sec", "section": "press_releases",
     "urls": ("https://www.sec.gov/newsroom/press-releases",)},
    {"site": "treasury", "section": "press_releases",
     "urls": ("https://home.treasury.gov/news/press-releases",)},
)
for _f in NEWS_FRONTS:
    _f.setdefault("host", NEWS_SITES[_f["site"]]["host"])
    _f.setdefault("news", True)


def news_fronts_enabled() -> bool:
    return bool(_cfg("READER_NEWS_ENABLED", True))


def _on(host: str, domains: tuple[str, ...]) -> bool:
    h = (host or "").lower().removeprefix("www.")
    return any(h == d or h.endswith("." + d) for d in domains)


def all_fronts() -> tuple[dict, ...]:
    """The Dow Jones fronts, plus the general-news fronts when enabled -- only
    those whose host is on the allowlist (`config.OPENCLAW_BROWSER_HOSTS`)."""
    if not news_fronts_enabled():
        return SECTION_FRONTS
    allowed = tuple(_cfg("OPENCLAW_BROWSER_HOSTS", ()))
    return SECTION_FRONTS + tuple(f for f in NEWS_FRONTS if _on(f["host"], allowed))


def front_host(front: dict) -> str:
    return front.get("host") or site_host(front["site"])


def site_key_of_host(host: str) -> str | None:
    """`reuters.com` -> "reuters"; `home.treasury.gov` -> "treasury"; `wsj.com`
    -> "wsj"; unknown -> None."""
    for k, v in NEWS_SITES.items():
        if _on(host, (v["host"],)):
            return k
    for k in ("wsj", "barrons", "marketwatch"):
        if _on(host, (f"{k}.com",)):
            return k
    return None


def is_news_host(host: str) -> bool:
    """A general-news host (not Dow Jones, not social)."""
    return site_key_of_host(host) in NEWS_SITES


def article_pattern_for(host: str) -> str | None:
    k = site_key_of_host(host)
    return ARTICLE_PATTERN.get(k) if k else None


def any_article_pattern(url: str) -> bool:
    """PURE. `url` matches the article pattern of the host it is on."""
    import re
    from urllib.parse import urlsplit
    try:
        h = (urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return False
    pat = article_pattern_for(h)
    return bool(pat and re.search(pat, url or ""))


# ─────────────────── the refill rule and the queue's state ───────────────────

def low_water() -> int:
    return int(_cfg("READER_QUEUE_LOW_WATER", 3))


def min_revisit_s() -> float:
    return float(_cfg("READER_FRONT_MIN_REVISIT_S", 1200.0))


def front_due_now(front: dict, last_read: datetime | None, now: datetime, *,
                  host_pending: int, low: int | None = None,
                  revisit_s: float | None = None) -> bool:
    """PURE. THE REFILL RULE. A front is due on its schedule (`front_due`), OR
    early when its host's pending list is at or below the low-water mark and it
    was read at least `READER_FRONT_MIN_REVISIT_S` ago (fronts change; an idle
    host with caps free goes back to its fronts instead of standing still)."""
    if front_due(front, last_read, now):
        return True
    lw = low_water() if low is None else int(low)
    mr = min_revisit_s() if revisit_s is None else float(revisit_s)
    return host_pending <= lw and (now - last_read).total_seconds() >= mr


def next_front_due_s(fronts: list[dict] | tuple[dict, ...], last: dict[str, datetime],
                     now: datetime, *, pending_by_host: dict[str, int],
                     dropped: set[str] | None = None, blocked: set[str] | None = None,
                     host: str | None = None) -> float | None:
    """PURE. Seconds until the soonest front (on `host`, or on any unblocked
    host) becomes due under `front_due_now` (0 = due now); None when none."""
    lw, mr = low_water(), min_revisit_s()
    best: float | None = None
    for f in fronts:
        h = front_host(f)
        if (host is not None and h != host) or (blocked and h in blocked) \
                or front_url(f, dropped or set()) is None:
            continue
        lr = last.get(front_key(f))
        if lr is None:
            return 0.0
        waits = [front_interval_s(f, now)]
        if pending_by_host.get(h, 0) <= lw:
            waits.append(mr)
        s = max(0.0, min(waits) - (now - lr).total_seconds())
        best = s if best is None else min(best, s)
    return best


#: the pool's own words for what it is doing (the supervisor reads them)
Q_READING, Q_REFILLING, Q_EMPTY, Q_WAITING_FOR_CAP, Q_COOLING = (
    "READING", "REFILLING", "QUEUE_EMPTY", "WAITING_FOR_CAP", "COOLING")


def host_queue_state(*, pending: int, in_flight: int, capped: bool, cooling: bool,
                     front_due_in_s: float | None) -> str:
    """PURE. One host's state:
    * COOLING         -- it showed a challenge / block / wall; left alone;
    * WAITING_FOR_CAP -- its hourly or daily cap is spent;
    * READING         -- something in flight or pending;
    * REFILLING       -- nothing pending and one of its fronts is due now;
    * QUEUE_EMPTY     -- nothing pending, caps free, the next front revisit is
                         ahead (`front_due_in_s`). A state of its own: never a
                         stall, never a reason to restart anything."""
    if cooling:
        return Q_COOLING
    if capped:
        return Q_WAITING_FOR_CAP
    if in_flight > 0 or pending > 0:
        return Q_READING
    if front_due_in_s is not None and front_due_in_s <= 0:
        return Q_REFILLING
    return Q_EMPTY


def pool_queue_state(host_states: dict[str, str]) -> str:
    """PURE. The whole pool: READING if any host reads; else REFILLING if any
    host refills; else QUEUE_EMPTY if any host with free caps has nothing to
    do; else WAITING_FOR_CAP (every host capped or cooling)."""
    vals = set(host_states.values())
    for s in (Q_READING, Q_REFILLING, Q_EMPTY):
        if s in vals:
            return s
    return Q_WAITING_FOR_CAP if vals else Q_EMPTY


# ─────────────────────────────── robots.txt ──────────────────────────────────

def robots_url(host: str) -> str:
    """The robots.txt a host serves (bare two-label hosts get `www.` except the
    ones that live on the bare name)."""
    h = (host or "").lower()
    if h.count(".") == 1 and h not in ("apnews.com",):
        h = "www." + h
    return f"https://{h}/robots.txt"


def robots_host(host: str) -> str:
    """The host a robots.txt record is kept under: the news site's own host."""
    k = site_key_of_host(host)
    return NEWS_SITES[k]["host"] if k in NEWS_SITES else (host or "").lower().removeprefix("www.")


def robots_allows(robots_text: str | None, url: str, agent: str = "*") -> bool:
    """PURE. What the site's robots.txt says about `url` for `agent` (the
    `*` group unless a named group matches). No file / no groups = allowed
    (the standard reading of a missing robots.txt)."""
    if not robots_text or "user-agent" not in robots_text.lower():
        return True
    from urllib.robotparser import RobotFileParser
    rp = RobotFileParser()
    try:
        rp.parse(robots_text.splitlines())
        return bool(rp.can_fetch(agent, url))
    except Exception:  # noqa: BLE001 -- an unparseable file refuses nothing
        return True


def robots_dir() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "dowjones" / "robots"


def robots_record(host: str, *, path: Path | None = None) -> dict | None:
    try:
        return json.loads(((path or robots_dir()) / f"{host}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def robots_fresh(rec: dict | None, now: datetime) -> bool:
    ttl = float(_cfg("READER_ROBOTS_TTL_S", 86400.0))
    try:
        return rec is not None and (now - datetime.fromisoformat(rec["fetched_utc"])
                                    ).total_seconds() < ttl
    except (KeyError, ValueError, TypeError):
        return False


def save_robots(host: str, *, text: str, cls: str, now: datetime,
                path: Path | None = None) -> dict:
    rec = {"host": host, "fetched_utc": now.isoformat(timespec="seconds"), "class": cls,
           "text": (text or "")[:200_000]}
    DG.atomic_write_json((path or robots_dir()) / f"{host}.json", rec)
    return rec


# ─────────── what the digest asks the reader to read next (2026-09-29) ───────
#
# The world digest writes `news_digest/read_next.jsonl`: rows with a `url`
# (read it, when its host is allowed) or a `search_query` (a question it wants
# answered). A query becomes a NAVIGATION to a site's own search URL -- never
# typing into a box -- on the sites below, each only if its host is allowed and
# (for a general-news host) its robots.txt allows the search path.

SEARCH_URLS: dict[str, str] = {
    "apnews": "https://apnews.com/search?q={q}",
    "cnbc": "https://www.cnbc.com/search/?query={q}&qsearchterm={q}",
    "ft": "https://www.ft.com/search?q={q}",
    "scmp": "https://www.scmp.com/search/{q}",
    "reuters": "https://www.reuters.com/site-search/?query={q}",
    "wsj": "https://www.wsj.com/search?query={q}",
    "marketwatch": "https://www.marketwatch.com/search?q={q}",
    "barrons": "https://www.barrons.com/search?query={q}",
}
#: each question is searched on this many sites, one general-news site and one
#: Dow Jones site in turn, so fifty questions do not become four hundred loads
SEARCH_SITES_PER_QUESTION = 2


def search_url(site: str, query: str) -> str | None:
    """PURE. The site's own search URL for `query` (None: no search page)."""
    from urllib.parse import quote_plus
    tpl = SEARCH_URLS.get(site)
    q = " ".join(str(query or "").split())[:160]
    return tpl.format(q=quote_plus(q)) if tpl and q else None


def search_sites_for(n: int, *, allowed: tuple[str, ...] | None = None,
                     per_question: int = SEARCH_SITES_PER_QUESTION) -> list[str]:
    """PURE. The sites question number `n` is searched on: alternating a
    general-news site and a Dow Jones site, rotating so the load spreads."""
    allowed = tuple(_cfg("OPENCLAW_BROWSER_HOSTS", ())) if allowed is None else allowed
    host = {k: (NEWS_SITES[k]["host"] if k in NEWS_SITES else f"{k}.com") for k in SEARCH_URLS}
    news = [k for k in SEARCH_URLS if k in NEWS_SITES and _on(host[k], allowed)]
    dj = [k for k in SEARCH_URLS if k not in NEWS_SITES and _on(host[k], allowed)]
    out: list[str] = []
    for i in range(per_question):
        grp = (news, dj)[i % 2] or news or dj
        if grp:
            k = grp[(n + i // 2) % len(grp)]
            if k not in out:
                out.append(k)
    return out


def read_next_path() -> Path:
    return Path(_cfg("READER_READ_NEXT_FILE",
                     Path(_config.OPTIMUS_LEDGER_DIR) / "news_digest" / "read_next.jsonl"))


def read_next_key(row: dict) -> str:
    """PURE. One row's identity (the digest may write the same ask again)."""
    u = str(row.get("url") or "").strip()
    if u:
        return "url:" + u
    q = " ".join(str(row.get("search_query") or row.get("question") or "").lower().split())
    return "q:" + q


# ────────────────────── publication time: current or archive ─────────────────

def max_article_age_days() -> float:
    return float(_cfg("READER_MAX_ARTICLE_AGE_DAYS", 4.0))


def is_archive(published_utc: str | None, seen: datetime) -> bool:
    """PURE. An article whose own dateline is more than READER_MAX_ARTICLE_AGE_DAYS
    before we read it (undated = not known to be archive)."""
    if not published_utc:
        return False
    try:
        t = datetime.fromisoformat(str(published_utc))
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (seen - t).total_seconds() > max_article_age_days() * 86400


def recency_rank(item: dict, now: datetime | None = None) -> float:
    """PURE. Hours since the date the link showed (smaller = sooner); an
    undated link ranks as 12 h (a front's top stories are often undated)."""
    pv = item.get("published_visible")
    if not pv:
        return 12.0
    try:
        t = datetime.fromisoformat(str(pv))
    except ValueError:
        return 12.0
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - t).total_seconds() / 3600.0)



# ═════════════════════ THE READING BUDGET (2026-09-30) ═══════════════════════
#
# Murat, 2026-09-29: "use openclaw to review stocks or the general news and the
# market positions, insider traders, politics etc anything needed", "digest
# everything".
#
# MEASURED the evening before: the pool read ~400 OK pages an hour first-come,
# spent its 4,000 page loads per rolling 24 h by 10:44 UTC, and then stood
# WAITING_FOR_CAP for hours (the throttle log: 307-385 loads an hour at
# 03:00-10:00 UTC, 11-43 an hour at 21:00-02:00 UTC). The cap did its job; the
# ORDER did not: first-come spends the day on whatever refilled fastest (the
# Dow Jones hosts took 2,345 of the 3,873 loads in the window) and leaves the
# US session with nothing.
#
# So the same 4,000 loads are now SPENT BY RULE:
# * LANES with declared shares (`budget_lane` classifies every queued item);
# * an HOURLY ALLOWANCE shaped by the sessions (`hour_allowance`: heavier in
#   the hours before and during the Asian and US sessions, never below the
#   floor, the curve sums to the daily total), enforced on a rolling hour AND
#   on a rolling 10 minutes (so an hour's allowance is not spent in a burst and
#   the reader is never silent for most of an hour);
# * a lane under its own hourly share is always served; a lane over it may
#   BORROW only when no other lane with something servable is under its share
#   (work-conserving: an idle lane's share is not wasted); a lane that has
#   spent `READER_BUDGET_LANE_DAY_MULT` x its daily share borrows nothing
#   while another lane is waiting.
# The Dow Jones and social per-host caps are NOT changed; they bind inside this.

BUDGET_LANES: tuple[str, ...] = (
    "book_names", "universe_names", "markets_news", "macro_world", "politics_policy",
    "official_releases", "social", "digest_asks", "overhead")

#: declared shares of the browser's daily page loads (sum 1.0); `config`
#: `READER_BUDGET_SHARES` overrides
DEFAULT_BUDGET_SHARES: dict[str, float] = {
    "book_names": 0.24, "universe_names": 0.12, "markets_news": 0.20, "macro_world": 0.12,
    "politics_policy": 0.08, "official_releases": 0.04, "social": 0.11,
    "digest_asks": 0.06, "overhead": 0.03}

#: relative weight of each UTC hour (index 0-23). Asia session 00-08 UTC (Tokyo,
#: Hong Kong, Shanghai), its pre-open at 23; Europe 08-11; US pre-open 11-13;
#: US session 13-20 (09:30-16:00 ET); US evening 20-23.
DEFAULT_HOUR_WEIGHTS: tuple[float, ...] = (
    1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4,      # 00-07 Asia
    0.8, 0.8, 0.8,                               # 08-10 Europe
    1.3, 1.3,                                    # 11-12 US pre-open
    1.6, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6,           # 13-19 US session
    0.7, 0.7, 0.7,                               # 20-22 US evening
    1.2)                                         # 23 Asia pre-open

OFFICIAL_BROWSER_HOSTS = ("federalreserve.gov", "bls.gov", "sec.gov", "treasury.gov")
_POLITICS = ("politic", "policy", "opinion", "government", "congress", "white-house",
             "whitehouse", "election", "tariff", "geopolit", "washington", "regulat")
_MACRO = ("economy", "economic", "world", "asia", "china", "commodit", "global",
          "currenc", "rates", "bonds")
_MACRO_HOSTS = ("asia.nikkei.com", "scmp.com")


def budget_enabled() -> bool:
    return bool(_cfg("READER_BUDGET_ENABLED", True))


def budget_shares() -> dict[str, float]:
    """The declared shares, normalised to sum 1 over `BUDGET_LANES` (a lane
    missing from the config gets 0)."""
    raw = dict(_cfg("READER_BUDGET_SHARES", DEFAULT_BUDGET_SHARES) or DEFAULT_BUDGET_SHARES)
    s = {k: max(0.0, float(raw.get(k, 0.0))) for k in BUDGET_LANES}
    tot = sum(s.values()) or 1.0
    return {k: v / tot for k, v in s.items()}


def hour_weights() -> tuple[float, ...]:
    w = tuple(float(x) for x in (_cfg("READER_BUDGET_HOUR_WEIGHTS", DEFAULT_HOUR_WEIGHTS)
                                 or DEFAULT_HOUR_WEIGHTS))
    return w if len(w) == 24 and all(x >= 0 for x in w) and sum(w) > 0 else DEFAULT_HOUR_WEIGHTS


def budget_day_total() -> int:
    return int(_cfg("READER_BUDGET_DAY_TOTAL", _cfg("WEB_READER_MAX_PER_DAY", 4000)))


def hour_allowance(now: datetime, *, day_total: int | None = None,
                   weights: tuple[float, ...] | None = None) -> int:
    """PURE. Page loads allowed in the rolling hour ending at `now`: the day's
    total spread by the UTC-hour weights (the 24 allowances sum to about the
    total), never below `READER_BUDGET_MIN_PER_HOUR`."""
    w = weights or hour_weights()
    tot = budget_day_total() if day_total is None else int(day_total)
    h = now.astimezone(timezone.utc).hour
    floor = int(_cfg("READER_BUDGET_MIN_PER_HOUR", 60))
    return max(floor, int(round(tot * w[h] / sum(w))))


def ten_min_allowance(hour_allow: int) -> int:
    """PURE. The rolling-10-minute ceiling: a sixth of the hour, with slack
    (`READER_BUDGET_BURST`, default 1.5x) so one slow page does not starve."""
    burst = float(_cfg("READER_BUDGET_BURST", 1.5))
    return max(3, int(round(hour_allow / 6.0 * burst)))


def _host_of(url: str) -> str:
    from urllib.parse import urlsplit
    try:
        return (urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return ""


def budget_lane(item: dict, *, books: set[str] | frozenset[str] = frozenset(),
                fresh: set[str] | frozenset[str] = frozenset()) -> str:
    """PURE. Which budget lane a queued item spends from.

    * robots.txt reads -> overhead; social hosts -> social;
    * a digest ask (a site search, a URL the digest asked for) -> digest_asks;
    * an official host (Fed, BLS, SEC, Treasury) -> official_releases;
    * a stock page, or the news a stock page showed (it carries the ticker and
      a ticker tier) -> book_names (book / contest / fresh-filing names) or
      universe_names (the rest);
    * a front or its news: politics / policy / opinion sections -> politics_policy;
      economy / world / Asia sections and the Asian hosts -> macro_world;
      everything else -> markets_news."""
    kind = str(item.get("kind") or "")
    host = str(item.get("host") or _host_of(str(item.get("url") or ""))).lower()
    host = host.removeprefix("www.")
    lane = str(item.get("lane") or "")
    if kind == "robots" or lane.startswith("robots:"):
        return "overhead"
    if kind == "social" or _on(host, tuple(_cfg("OPENCLAW_SOCIAL_HOSTS",
                                                 ("x.com", "reddit.com", "stocktwits.com")))):
        return "social"
    if kind == "search" or item.get("via") == "read_next" or lane.startswith(
            ("search:", "read_next")):
        return "digest_asks"
    if _on(host, OFFICIAL_BROWSER_HOSTS):
        return "official_releases"
    tk = str(item.get("ticker") or "").upper()
    tier = item.get("tier")
    if kind in ("stock_links", "stock_text") or (
            tk and (tier is None or int(tier) >= TIER_BOOK)):
        t = ticker_tier(tk, books=set(books), fresh=set(fresh))
        return "book_names" if t in (TIER_BOOK, TIER_FRESH) else "universe_names"
    text = " ".join((str(item.get("section") or ""), lane,
                     str(item.get("url") or "").split("?")[0])).lower()
    if any(w in text for w in _POLITICS):
        return "politics_policy"
    if _on(host, _MACRO_HOSTS) or any(w in text for w in _MACRO):
        return "macro_world"
    return "markets_news"


def lane_hour_quota(lane: str, hour_allow: int, shares: dict[str, float] | None = None) -> int:
    """PURE. A lane's own share of this hour's allowance (a lane with a
    non-zero share always gets at least one page)."""
    sh = (shares or budget_shares()).get(lane, 0.0)
    return 0 if sh <= 0 else max(1, int(round(sh * hour_allow)))


def budget_verdict(lane: str, *, now: datetime, loads_60m: int, loads_10m: int,
                   lane_60m: dict[str, int], lane_24h: dict[str, int],
                   servable_lanes: set[str] | frozenset[str],
                   shares: dict[str, float] | None = None,
                   day_total: int | None = None) -> tuple[bool, str]:
    """PURE. May one more page load be spent on `lane` now?

    Refusals, in order: the rolling hour's allowance is spent
    (`HOUR_BUDGET_SPENT`); the rolling 10 minutes' ceiling is spent
    (`PACE_10M`); the lane has spent `READER_BUDGET_LANE_DAY_MULT` x its daily
    share while another servable lane is under its own (`LANE_DAY_SHARE_SPENT`);
    the lane is over its hourly share and another lane with something servable
    is still under its own (`LEAVE_FOR:<lane>`). Grants: `OWN_SHARE` (under its
    hourly share) or `BORROW` (nobody servable is under theirs, so the idle
    share is not wasted)."""
    shares = shares or budget_shares()
    tot = budget_day_total() if day_total is None else int(day_total)
    allow = hour_allowance(now, day_total=tot)
    if loads_60m >= allow:
        return False, f"HOUR_BUDGET_SPENT: {loads_60m} >= {allow} this hour"
    if loads_10m >= ten_min_allowance(allow):
        return False, f"PACE_10M: {loads_10m} >= {ten_min_allowance(allow)} in 10 min"
    mult = float(_cfg("READER_BUDGET_LANE_DAY_MULT", 1.6))
    day_max = shares.get(lane, 0.0) * tot * mult
    under = [x for x in sorted(servable_lanes) if x != lane
             and lane_60m.get(x, 0) < lane_hour_quota(x, allow, shares)]
    if lane_24h.get(lane, 0) >= day_max and under:
        return False, f"LANE_DAY_SHARE_SPENT: {lane_24h.get(lane, 0)} >= {day_max:.0f}"
    if lane_60m.get(lane, 0) < lane_hour_quota(lane, allow, shares):
        return True, "OWN_SHARE"
    if under:
        return False, f"LEAVE_FOR:{under[0]}"
    return True, "BORROW"


def budget_plan(now: datetime, *, shares: dict[str, float] | None = None,
                day_total: int | None = None) -> dict:
    """PURE. The declared plan, for the status file and the receipts: shares,
    per-lane daily targets, this hour's allowance and each lane's quota, and
    the 24 hourly allowances."""
    shares = shares or budget_shares()
    tot = budget_day_total() if day_total is None else int(day_total)
    allow = hour_allowance(now, day_total=tot)
    base = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hours = {f"{h:02d}": hour_allowance(base.replace(hour=h), day_total=tot) for h in range(24)}
    return {"day_total": tot, "hour_allowance_now": allow,
            "ten_min_allowance_now": ten_min_allowance(allow),
            "shares": {k: round(v, 4) for k, v in shares.items()},
            "day_target": {k: int(round(v * tot)) for k, v in shares.items()},
            "hour_quota_now": {k: lane_hour_quota(k, allow, shares) for k in shares},
            "hourly_allowance_utc": hours}


def budget_log_path() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "dowjones" / "budget_lanes.jsonl"


def lane_counts(rows: list[dict], now: datetime) -> dict:
    """PURE. From budget-log rows `{t, lane, host, outcome}`: loads and OK pages
    per lane and per host over the last 60 min and 24 h, plus total loads in
    the last 10 / 60 min and 24 h."""
    from collections import Counter
    out: dict = {"lane_60m": Counter(), "lane_24h": Counter(), "ok_lane_60m": Counter(),
                 "ok_lane_24h": Counter(), "host_24h": Counter(), "ok_host_24h": Counter(),
                 "ok_host_60m": Counter(), "loads_10m": 0, "loads_60m": 0, "loads_24h": 0}
    for r in rows:
        try:
            t = datetime.fromisoformat(str(r["t"]))
        except (KeyError, ValueError, TypeError):
            continue
        age = max(0.0, (now - t).total_seconds())
        if age >= 86400:
            continue
        lane, host, ok = r.get("lane") or "?", r.get("host") or "?", r.get("outcome") == "OK"
        out["lane_24h"][lane] += 1
        out["host_24h"][host] += 1
        out["loads_24h"] += 1
        if ok:
            out["ok_lane_24h"][lane] += 1
            out["ok_host_24h"][host] += 1
        if age < 3600:
            out["lane_60m"][lane] += 1
            out["loads_60m"] += 1
            if ok:
                out["ok_lane_60m"][lane] += 1
                out["ok_host_60m"][host] += 1
        if age < 600:
            out["loads_10m"] += 1
    return out


def read_budget_log(path: Path | None = None, now: datetime | None = None,
                    max_lines: int = 20000) -> list[dict]:
    """The budget log's rows of the last 24 h (the tail, bounded)."""
    p = path or budget_log_path()
    now = now or datetime.now(timezone.utc)
    out = []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except OSError:
        return []
    for ln in lines:
        try:
            r = json.loads(ln)
            if (now - datetime.fromisoformat(str(r["t"]))).total_seconds() < 86400:
                out.append(r)
        except (ValueError, KeyError, TypeError):
            continue
    return out
