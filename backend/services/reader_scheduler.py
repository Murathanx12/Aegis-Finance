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
    4. then the link's position on its page (1 = most prominent);
    5. then the order it was found in (`seq`)."""
    if item.get("kind") in ("front", "front_text"):
        tier = TIER_FRONT
    elif item.get("tier") is not None:
        tier = int(item["tier"])
    else:
        tier = ticker_tier(item.get("ticker"), books=books, fresh=fresh)
    found = 0 if item.get("parent_url") else 1
    lr = last_read.get((item.get("ticker") or "").upper(), "") if item.get("ticker") else ""
    return (tier, found, lr, int(item.get("position") or 0), int(item.get("seq") or 0))


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
