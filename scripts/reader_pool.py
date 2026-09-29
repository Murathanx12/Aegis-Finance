"""The reader POOL: several tabs of the dedicated MuratClaw Chrome at once,
paced per host, reading the sites' own navigation, the per-stock pages, the
news they show, the media they carry, and the social hosts.

Murat, 2026-09-28 21:45 HKT: "can openclaw read more, can it launch another
chrome tabs to read too, this one by one is very slow, it needs to read wsj,
barron, marketwatch per stock and the news from that too, it should navigate
them, not just the stocks, and also the media too." Earlier the same day:
"dont read it too slow, while its waiting make it read other pages then, reddit
x and other socials are logged in too" and "it should always work and shouldnt
be standing idle." 22:00 HKT: "use the transcript of the videos, its much better."

WHY ONE PROCESS WITH THREADS (measured, 2026-09-28 evening)
===========================================================
On the live three-worker run, per page: open ~2-7 s, settle + scroll + read
~10 s, and 46-73 s IDLE waiting for the one shared throttle (a global drawn gap
of 6-20 s serialised across the three processes with the lock held through the
sleep, plus a same-host floor of 3x the draw, ~60 s). The page load was not the
bottleneck; the pacing was. So:
* pacing is PER HOST (`Throttle(per_host_mode=True)`: a drawn, jittered gap per
  host, RESERVED under the file lock and slept outside it) plus a short drawn
  gap between any two opens;
* one process holds up to `READER_MAX_TABS` tabs, `READER_TABS_PER_HOST` per
  host, each tab served by a thread. Every browser call is the SAME guarded,
  synchronous `openclaw_client` call the reader always made (HTTP transport, one
  keep-alive session per thread), so no guard is rewritten for concurrency; an
  asyncio loop would have meant a second client. One process also lets ONE
  memory governor decide the tab count, which N worker processes could only do
  through a shared file.

WHAT EACH TAB DOES, ONE PAGE AT A TIME
======================================
reserve a slot on the page's host -> sleep outside the lock -> open a FRESH tab
at the URL (`web_reader.open_lane_tab`: URL rules, instance proof, landed-host
check inside the client) -> read -> classify -> store -> close the tab. Kinds:
* `front`       a section front: snapshot, article + media links chosen FROM it
                (newest / most prominent first, sponsored units skipped);
* `front_text`  a data page (calendars, upgrades/downgrades): text + table rows;
* `stock_links` a stock page (MarketWatch, WSJ, Barron's): its news links;
* `stock_text`  the MarketWatch analyst page: stored as text;
* `article` / `media`: the fixed text read, then the fixed media read (media
                items, captions / transcript text the site exposes, tables,
                related links followed to depth 1 when a universe ticker is named);
* `social`      x / reddit / stocktwits search pages: `source_kind = "social"`.
* `robots`      a general-news host's robots.txt, read once a day through the
                same browser; a disallowed path is never opened.
Every stored article carries `reached_by` (lane, section, parent url, position,
depth). The order is `reader_scheduler.priority_key`.

THE BROWSE LANE (2026-09-29)
============================
Murat: "digest the news see what they are implying is there an another path
they are leading, not only the forecast from the websites but the stocks news
and the general news brose the news like a human to get the context". MEASURED
the same morning: 0 pages for 100+ minutes with every Dow Jones cap free and
`pending: 0` -- the list was EXHAUSTED and nothing refilled it. Now:
* the fronts are the Dow Jones sections (incl. politics, opinion, commodities,
  video, podcasts) plus general news on free public sites
  (`reader_scheduler.NEWS_FRONTS`, hosts `config.OPENCLAW_NEWS_HOSTS`);
* every front read is STORED as a page record (its headlines in page order and
  its outbound links), so a digest sees what each front put first;
* from an article reached from a front, up to `READER_BROWSE_FOLLOW_MAX`
  outbound links (its related block on the same host, and in-article links on
  any allowed news host that have that host's article shape) are followed one
  hop; the stock-page news keeps the ticker rule;
* THE REFILL RULE (`reader_scheduler.front_due_now`): a host whose pending list
  is at the low-water mark goes back to its fronts once they are
  `READER_FRONT_MIN_REVISIT_S` old; a page is read once (canonical URL against
  every stored record);
* the status names the queue's state per host and for the pool: READING,
  REFILLING, QUEUE_EMPTY, WAITING_FOR_CAP, COOLING (`queue_state`). An empty
  list with caps free is QUEUE_EMPTY, never a stall.

REFUSALS (unchanged, and in the client, not here): only the dedicated Chrome,
proven before every action; read-only; no payment / message / social write; no
typing; brokerage, bank, payment and mail hosts refused. A challenge, block,
login wall or rate-limit page STOPS that host for `READER_HOST_COOL_S`; nothing
is done to get around it. X, Reddit and Dow Jones terms restrict automated
access; the owner was told the account risk twice and decided.

    python -m scripts.reader_pool --handoff --until 08:00
    python -m scripts.reader_pool --handoff --trial --fronts wsj:home,barrons:home,marketwatch:home \
        --tickers NVDA,MU --max-pages 24 --worker-id pool-trial
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402
from backend.services import disk_guard as DG  # noqa: E402
from backend.services import media_transcripts as MT  # noqa: E402
from backend.services import reader_scheduler as RS  # noqa: E402
from backend.services import web_reader as WR  # noqa: E402

DJ = Path(_config.OPTIMUS_LEDGER_DIR) / "dowjones"
STATUS = DJ / "reader_pool_status.json"
STOP_FILES = (DJ / "SUPERVISOR_STOP", DJ / "READER_POOL_STOP")
FRONT_SCHEDULE = DJ / "front_schedule.json"
#: 2026-09-29: the found links still pending when a pool stops (a memory
#: recycle, a stall restart) are carried to the next pool, so a restart never
#: throws away what the fronts showed
PENDING_CARRY: Path | None = None       # None -> DJ / "pool_pending_carry.json" at call time
CARRY_KINDS = ("article", "media", "search")
SOCIAL_SEEN = WR.corpus_root() / "_social_seen.jsonl"
#: the codes that end the whole pool (the supervisor classifies the log tail)
FATAL = re.compile(r"REFUSED_NOT_MURATCLAW_INSTANCE|REFUSED_INSTANCE_|REFUSED_TAB_NOT_IN_INSTANCE|"
                   r"REFUSED_MAIN_CHROME_PROFILE|REFUSED_THROTTLE_DAY\b")
CHALLENGE_CLASSES = ("CHALLENGE", "LOGIN_WALL", "INTERSTITIAL", "RATE_LIMITED")
#: kinds that come round again (a front on its schedule, a stock or social page
#: after its freshness window); an article url is read once
RECURRING = ("front", "front_text", "stock_links", "stock_text", "social", "robots")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ───────────────────────────── the candidate names ───────────────────────────

def book_names() -> set[str]:
    """Frozen books (personal, competition, probe) + contest candidates."""
    out: set[str] = set()
    try:
        from backend.services import digest_inbox as DI
        for v in DI.book_names().values():
            out |= {str(t).upper() for t in v if t}
    except Exception:  # noqa: BLE001 -- a missing book is an empty book
        pass
    try:
        cands = sorted((Path(_config.OPTIMUS_LEDGER_DIR) / "contest").glob("candidates_*.json"))
        if cands:
            d = json.loads(cands[-1].read_text(encoding="utf-8"))
            out |= {str(r.get("symbol")).upper() for r in (d.get("proposal_names") or [])
                    if isinstance(r, dict) and r.get("symbol")}
    except (OSError, ValueError):
        pass
    return out


def fresh_names(now: datetime, hours: float = 36.0) -> set[str]:
    """Tickers with an alert (built from SEC filings) in the last `hours`."""
    out: set[str] = set()
    p = Path(_config.OPTIMUS_LEDGER_DIR) / "alerts" / "alerts.jsonl"
    try:
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(ln)
                t = datetime.fromisoformat(str(r.get("created_utc")))
            except (ValueError, TypeError):
                continue
            if r.get("ticker") and now - t <= timedelta(hours=hours):
                out.add(str(r["ticker"]).upper())
    except OSError:
        pass
    return out


def _load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def stock_last_reads(*, stored: dict[str, set[str]]) -> dict[tuple[str, str], datetime]:
    """(lane, TICKER) -> the last time that stock page was read."""
    out: dict[tuple[str, str], datetime] = {}
    legacy = {"wsj": "wsj:stock", "barrons": "barrons:stock"}
    p = WR.corpus_root() / "_search_seen.jsonl"
    try:
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(ln)
                t = datetime.fromisoformat(str(r.get("at")))
            except (ValueError, TypeError):
                continue
            lane = legacy.get(str(r.get("source")), str(r.get("source")))
            k = (lane, str(r.get("ticker") or "").upper())
            if k not in out or t > out[k]:
                out[k] = t
    except OSError:
        pass
    mw = RS.STOCK_PAGES[0]
    for key, days in stored.items():
        m = re.match(r"marketwatch\.com/investing/stock/([a-z0-9.]+)/analystestimates$", key)
        if m and days:
            d = max(x for x in days if x) if any(days) else ""
            if d:
                t = datetime.fromisoformat(d + "T00:00:00+00:00")
                k = (mw["lane"], m.group(1).upper())
                if k not in out or t > out[k]:
                    out[k] = t
    return out


def social_last_reads() -> dict[tuple[str, str], datetime]:
    out: dict[tuple[str, str], datetime] = {}
    try:
        for ln in SOCIAL_SEEN.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(ln)
                out[(r["host"], r["ticker"])] = datetime.fromisoformat(r["at"])
            except (ValueError, KeyError, TypeError):
                continue
    except OSError:
        pass
    return out


# ───────────────────────────────── the pool ──────────────────────────────────

class Pool:
    """Several tabs, one scheduler, one governor. Every side effect is
    injectable (driver, throttle, clock, sleep, memory) for the tests."""

    def __init__(self, *, driver: Any, throttle: WR.Throttle, profile: str = "muratclaw",
                 names: list[str], books: set[str], fresh: set[str],
                 fronts: list[dict] | None = None, social: bool = True,
                 stock_pages: tuple[dict, ...] = RS.STOCK_PAGES,
                 governor: RS.TabGovernor | None = None, cooling: RS.HostCooling | None = None,
                 until: datetime | None = None, max_pages: int | None = None,
                 tabs_per_host: dict | None = None, printer: Any = print,
                 stored: dict[str, set[str]] | None = None, now_fn: Any = _now,
                 wait_fn: Any = None, caption_fetch: Any = None,
                 dropped: set[str] | None = None, front_last: dict | None = None,
                 stock_last: dict | None = None, social_last: dict | None = None,
                 persist: bool = True, alert_fn: Any = None,
                 reader_sleep: Any = None, front_links_max: int | None = None,
                 read_next_path: Path | None = None) -> None:
        self.driver, self.thr, self.profile = driver, throttle, profile
        self.names = [n.upper() for n in dict.fromkeys(names)]
        self.universe = set(self.names)
        self.books, self.fresh = set(books), set(fresh)
        self.fronts = list(RS.all_fronts() if fronts is None else fronts)
        self.social, self.stock_pages = social, stock_pages
        self.gov = governor or RS.TabGovernor()
        self.cooling = cooling or RS.HostCooling()
        self.until, self.max_pages = until, max_pages
        self.per_host = dict(tabs_per_host or getattr(_config, "READER_TABS_PER_HOST", {}))
        self.printer = printer
        self.now_fn = now_fn
        self.stop_event = threading.Event()
        self.wait_fn = wait_fn or (lambda s: self.stop_event.wait(s))
        self.caption_fetch = caption_fetch
        self.persist = persist
        self.alert_fn = alert_fn
        #: the settle and scroll pauses inside a page (None -> interruptible waits)
        self.reader_sleep = reader_sleep
        self.front_links_max = int(front_links_max if front_links_max is not None else
                                   getattr(_config, "READER_FRONT_LINKS_MAX", 12))
        self.lock = threading.RLock()
        self.stored = WR.stored_urls() if stored is None else stored
        self.dropped = RS.dropped_section_urls() if dropped is None else set(dropped)
        self.front_last: dict[str, datetime] = dict(front_last if front_last is not None else {
            k: datetime.fromisoformat(v) for k, v in _load_json(FRONT_SCHEDULE).items()})
        self.stock_last = dict(stock_last if stock_last is not None
                               else stock_last_reads(stored=self.stored))
        self.social_last = dict(social_last if social_last is not None else social_last_reads())
        try:
            from scripts import dowjones_pull as DP
            self.last_read = DP.last_read_days(self.names, stored=self.stored)
            self._nf = {src: DP.not_found_tickers(src) for src in
                        ("marketwatch", "wsj", "barrons")}
        except Exception:  # noqa: BLE001 -- ordering falls back to the given order
            self.last_read, self._nf = {}, {}
        self.pending: list[dict] = []
        self.queued: set[str] = set()
        self.inflight: Counter = Counter()
        self.open_tabs: dict[str, str] = {}
        #: every tab id this process opened (newest last, capped): a tab left
        #: open by a stop or a failed close is still the READER's, so the
        #: supervisor's Chrome recycle must not read it as the owner's
        #: (2026-09-29: two such tabs refused a recycle as OWNER_MAY_BE_USING)
        self.reader_tab_ids: list[str] = []
        self.seq = 0
        self.pages = 0
        self.stop_reason: str | None = None
        self.stats: dict[str, Counter] = defaultdict(Counter)
        self.classes: dict[str, Counter] = defaultdict(Counter)
        self.timings: list[dict] = []
        self.errors: list[str] = []
        self.cool_events: list[dict] = []
        self.media_counts: dict[str, Counter] = defaultdict(Counter)
        self.orphans: list[str] = []
        self.host_blocked_until: dict[str, datetime] = {}
        #: front key -> {url, landed, title, class, links, new, at}: the live
        #: verification of every section URL (a redirect to another path is
        #: recorded as REDIRECTED, not as the section)
        self.front_results: dict[str, dict] = {}
        # the browse lane (2026-09-29)
        self.robots: dict[str, dict] = {}
        self.robots_tried: dict[str, datetime] = {}
        self.robots_refused: Counter = Counter()
        self.paywall_streak: Counter = Counter()
        self.fronts_only_until: dict[str, datetime] = {}
        self.early_fronts: Counter = Counter()
        self.last_refill: dict = {}
        self.follow_max = int(getattr(_config, "READER_BROWSE_FOLLOW_MAX", 3))
        #: a recurring item whose OPEN failed may come back after this time
        #: (review 2026-09-29 F6: it used to stay in `queued` for good)
        self.retry_after: dict[str, datetime] = {}
        #: consecutive BLANK pages per host (review F3: a soft block renders
        #: blank; READER_BLANK_STREAK_COOL in a row cools the host)
        self.blank_streak: Counter = Counter()
        #: the digest's asks (news_digest/read_next.jsonl): adopted once each
        self.read_next_path = read_next_path if read_next_path is not None else (
            RS.read_next_path() if persist else None)
        self.read_next_done: set[str] = read_next_adopted() if persist else set()
        self.read_next_n = len(self.read_next_done)
        self.carried_in = self._load_carry() if persist else 0
        self.started = self.now_fn()

    # ── the queue ───────────────────────────────────────────────────────────

    def _key(self, it: dict) -> tuple:
        return RS.priority_key(it, books=self.books, fresh=self.fresh, last_read=self.last_read)

    def _add(self, it: dict) -> bool:
        k = it.get("key") or WR.norm_url(it["url"])
        if k in self.queued:
            return False
        ra = self.retry_after.get(k)
        if ra is not None and ra > self.now_fn():
            return False
        self.seq += 1
        it = dict(it, seq=self.seq, key=k)
        self.queued.add(k)
        self.pending.append(it)
        return True

    def ordered_names(self) -> list[str]:
        def k(n: str) -> tuple:
            return (RS.ticker_tier(n, books=self.books, fresh=self.fresh),
                    self.last_read.get(n, ""), self.names.index(n) if n in self.names else 0)
        return sorted(self.names, key=k)

    # ── robots.txt (general-news hosts only) ────────────────────────────────

    def _robots_rec(self, host: str) -> dict | None:
        host = RS.robots_host(host)
        rec = self.robots.get(host)
        if rec is None and self.persist:
            rec = RS.robots_record(host)
            if rec is not None:
                self.robots[host] = rec
        return rec

    def robots_state(self, url: str) -> bool | None:
        """True / False: what the general-news host's robots.txt says about
        `url`; None: not read yet. A Dow Jones or social URL is not judged here
        (True)."""
        h = WR.host_of(url)
        if not RS.is_news_host(h):
            return True
        rec = self._robots_rec(h)
        if rec is None:
            return None
        return RS.robots_allows(rec.get("text"), url)

    def robots_ok(self, url: str) -> bool:
        return self.robots_state(url) is True

    def _need_robots(self, host: str, site: str | None = None) -> bool:
        """Queue the host's robots.txt read (first in its host's line), at most
        once per 30 minutes per host. True when queued now."""
        now = self.now_fn()
        with self.lock:
            tried = self.robots_tried.get(host)
            if tried is not None and (now - tried).total_seconds() < 1800:
                return False
            if self._add({"kind": "robots", "site": site or RS.site_key_of_host(host) or host,
                          "host": host, "lane": f"robots:{host}", "url": RS.robots_url(host),
                          "key": f"robots:{host}", "tier": RS.TIER_FRONT}):
                self.robots_tried[host] = now
                return True
        return False

    def _refused_by_robots(self, url: str, lane: str | None) -> None:
        h = WR.host_of(url)
        with self.lock:
            self.robots_refused[h] += 1
            self.classes[h]["ROBOTS_DISALLOWED"] += 1
        if self.persist:
            WR.log_page(h, "ROBOTS_DISALLOWED", url, lane=lane, worker="pool")

    def refill(self) -> int:
        """Due fronts, stale stock pages, stale social pages -> pending.

        THE REFILL RULE (2026-09-29): a front is due on its schedule OR early,
        when its host's list is at the low-water mark and the front was read
        `READER_FRONT_MIN_REVISIT_S` ago (`RS.front_due_now`). A general-news
        host's robots.txt is read first; a front its robots.txt disallows is
        never queued."""
        now = self.now_fn()
        added = 0
        stock_h = float(getattr(_config, "READER_STOCK_FRESH_H", 20.0))
        social_h = float(getattr(_config, "READER_SOCIAL_FRESH_H", 12.0))
        with self.lock:
            blocked = self._blocked(now)
            load = Counter(it["host"] for it in self.pending)
            for h, n in self.inflight.items():
                load[h] += max(0, n)
            for f in self.fronts:
                url = RS.front_url(f, self.dropped)
                fk = RS.front_key(f)
                host = RS.front_host(f)
                if url is None or host in blocked:
                    continue
                if RS.is_news_host(host):
                    rec = self._robots_rec(host)
                    if rec is None or not RS.robots_fresh(rec, now):
                        if self._need_robots(host, f["site"]):
                            added += 1
                            load[host] += 1
                        if rec is None:
                            continue
                    if not RS.robots_allows(rec.get("text"), url):
                        if f"robots_front:{fk}" not in self.queued:
                            self.queued.add(f"robots_front:{fk}")
                            self._refused_by_robots(url, f"front:{fk}")
                        continue
                last = self.front_last.get(fk)
                if not RS.front_due_now(f, last, now, host_pending=load[host]):
                    continue
                if self._add({"kind": f.get("kind", "front"), "site": f["site"],
                              "host": host, "section": f["section"],
                              "lane": f"front:{fk}", "url": url, "front_key": fk,
                              "key": f"front:{fk}"}):
                    added += 1
                    load[host] += 1
                    if last is not None and not RS.front_due(f, last, now):
                        self.early_fronts[host] += 1
            added += self._adopt_read_next(now)
            self.last_refill = {"t": now.isoformat(timespec="seconds"), "added": added}
            for t in self.ordered_names():
                for pg in self.stock_pages:
                    last = self.stock_last.get((pg["lane"], t))
                    if last is not None and (now - last).total_seconds() < stock_h * 3600:
                        continue
                    if t in self._nf.get("marketwatch" if pg["site"] == "marketwatch"
                                         else pg["site"], set()) and pg["lane"] in (
                            "marketwatch:analyst", "wsj:stock", "barrons:stock"):
                        continue
                    added += self._add({"kind": pg["kind"], "site": pg["site"],
                                        "host": RS.site_host(pg["site"]), "lane": pg["lane"],
                                        "ticker": t, "url": RS.stock_url(pg, t),
                                        "column": pg.get("column"),
                                        "key": f"{pg['lane']}:{t}"})
                if self.social:
                    from scripts import social_browser_pull as SB
                    for it in SB.social_items([t]):
                        last = self.social_last.get((it["host"], t))
                        if last is not None and (now - last).total_seconds() < social_h * 3600:
                            continue
                        added += self._add(dict(it, key=f"{it['lane']}:{t}"))
        return added

    def _blocked(self, now: datetime) -> set[str]:
        out = set(self.cooling.active(now))
        out |= {h for h, t in self.host_blocked_until.items() if t > now}
        return out

    def take(self, slot: int) -> dict | None:
        """The next item for tab slot `slot`, or None (the governor says no,
        or nothing can be served now)."""
        now = self.now_fn()
        with self.lock:
            if slot >= self.gov.target or not self.gov.may_open(sum(self.inflight.values())):
                return None
            by_host: dict[str, list[dict]] = defaultdict(list)
            for it in self.pending:
                by_host[it["host"]].append(it)
            free = {h: int(self.per_host.get(h, 1)) - self.inflight[h] for h in by_host}
            rows = self.thr._rows()
            free_at = {}
            glo = float(self.thr.global_gap_s[0])
            stamps = [r[0] for r in rows]
            for h in by_host:
                at = now
                same = [r[0] for r in rows if r[1] == h]
                if same:
                    at = max(at, max(same) + timedelta(seconds=self.thr.host_range(h)[0]))
                # not behind another host's FUTURE reservation (2026-09-29)
                free_at[h] = WR.fit_global_gap(at, stamps, glo)
            it = RS.choose(by_host, free_slots=free, blocked=self._blocked(now),
                           free_at=free_at, now=now, key=self._key,
                           in_flight=dict(self.inflight))
            if it is None:
                return None
            self.pending.remove(it)
            self.inflight[it["host"]] += 1
            return it

    def release(self, it: dict) -> None:
        with self.lock:
            self.inflight[it["host"]] -= 1

    def requeue(self, it: dict) -> None:
        with self.lock:
            self.pending.append(it)

    # ── one page ────────────────────────────────────────────────────────────

    def stop(self, why: str) -> None:
        with self.lock:
            if self.stop_reason is None:
                self.stop_reason = why[:400]
                self.printer(f"POOL_STOP: {self.stop_reason}")
        self.stop_event.set()

    def _cool(self, host: str, cls: str, url: str) -> None:
        row = self.cooling.cool(host, f"{cls}: the host showed a {cls.lower()} page; its lanes "
                                      f"stop for the cooling period, nothing is done to pass it",
                                url, self.now_fn())
        ev = {"host": host, "class": cls, "url": url, **row}
        with self.lock:
            self.cool_events.append(ev)
        self.printer(f"HOST_COOLING {host}: {cls} at {url} until {row['until']}")
        if self.alert_fn:
            try:
                self.alert_fn(ev)
            except Exception:  # noqa: BLE001 -- the stop stands either way
                pass

    def process(self, it: dict, slot: int) -> None:
        host, url = it["host"], it["url"]
        t0 = time.time()
        if it["kind"] != "robots" and RS.is_news_host(host):
            rs = self.robots_state(url)
            if rs is not True:               # disallowed, or robots.txt not read yet
                if rs is False:
                    self._refused_by_robots(url, it.get("lane"))
                with self.lock:
                    self.queued.discard(it.get("key"))
                    self.retry_after[it.get("key")] = self.now_fn() + timedelta(
                        seconds=120 if rs is None else 86400)
                if rs is None:
                    self._need_robots(host)
                return
        try:
            res = self.thr.reserve("open", host)
        except WR.ReaderRefused as exc:
            msg = str(exc)
            if "REFUSED_THROTTLE_DAY" in msg:
                self.requeue(it)
                self.stop(msg)
            else:                         # a host cap: that host rests, the item waits
                rest = timedelta(hours=1) if "HOST_DAY" in msg else timedelta(minutes=10)
                with self.lock:
                    self.host_blocked_until[host] = self.now_fn() + rest
                self.requeue(it)
                self.errors.append(msg[:200])
            return
        if res["wait_s"] > 0 and self.wait_fn(res["wait_s"]):
            self.thr.refund("pool stopping before the open", line=res["line"])
            self.requeue(it)
            return
        t_open = time.time()
        try:
            op = WR.open_lane_tab(self.driver, self.profile, url, throttle=None, host=host)
        except Exception as exc:  # noqa: BLE001 -- classified below
            if not getattr(exc, "tab_made", False):
                self.thr.refund(f"open failed: {type(exc).__name__}", line=res["line"])
            self._fail(it, exc)
            with self.lock:                  # not lost for the life of the process
                if it["kind"] in RECURRING:
                    self.queued.discard(it.get("key"))
                    self.retry_after[it.get("key")] = self.now_fn() + timedelta(
                        seconds=float(getattr(_config, "READER_OPEN_RETRY_S", 600.0)))
            return
        open_s = time.time() - t_open
        with self.lock:
            self.pages += 1
            self.open_tabs[op["new_tab"]] = url
            self._remember_tab(op["new_tab"])
        rd = WR.Reader(profile=self.profile, tab=op["new_tab"], throttle=self.thr,
                       driver=self.driver, lock=False, direct_open=True, lane=it.get("lane"),
                       worker=f"pool{slot}", page_log=True, max_pages=10 ** 6,
                       sleep_fn=self.reader_sleep or (lambda s: self.stop_event.wait(s) and None))
        rd.pages = rd.tab_pages = 1
        rd._mark_loaded()
        # review 2026-09-29 F3: the page load REACHED the site, so its slot
        # counts against the caps whatever the page turns out to be (a soft
        # block renders blank); only an open that produced no tab is given back
        rd._slot_line = None
        it = dict(it, landed_url=op.get("url") or url)
        outcome = "OK"
        try:
            outcome = self._read(it, rd) or "OK"
        except Exception as exc:  # noqa: BLE001 -- classified below
            outcome = self._fail(it, exc, rd)
        finally:
            if not rd.retired:
                rd.retire()
            for tab, ok in rd.closed.items():
                if not ok:
                    self.orphans.append(tab)
            with self.lock:
                self.open_tabs.pop(op["new_tab"], None)
                if it["kind"] in RECURRING:          # due again after its window
                    self.queued.discard(it.get("key"))
            with self.lock:
                self.timings.append({"host": host, "kind": it["kind"],
                                     "wait_s": round(res["wait_s"], 2),
                                     "open_s": round(open_s, 2),
                                     "work_s": round(time.time() - t_open - open_s, 2),
                                     "total_s": round(time.time() - t0, 2),
                                     "outcome": outcome,
                                     "at": self.now_fn().isoformat(timespec="seconds")})
                self.timings = self.timings[-2000:]
                self.stats[host][it["kind"]] += 1
            self._blank_outcome(host, outcome, url)
            if self.max_pages is not None and self.pages >= self.max_pages:
                self.stop(f"BUDGET_SPENT: {self.pages} pages >= --max-pages {self.max_pages}")

    def _blank_outcome(self, host: str, outcome: str, url: str) -> None:
        """READER_BLANK_STREAK_COOL blank pages in a row on one host cool it like
        a challenge (review F3); any OK page resets the count."""
        o = str(outcome or "")
        if o in ("BLANK", "PAGE_BLANK", "REFUSED_EMPTY_READ"):
            with self.lock:
                self.blank_streak[host] += 1
                n = self.blank_streak[host]
            if n >= int(getattr(_config, "READER_BLANK_STREAK_COOL", 4)):
                with self.lock:
                    self.blank_streak[host] = 0
                self._cool(host, "BLANK_STREAK", url)
        elif o == "OK":
            with self.lock:
                self.blank_streak[host] = 0

    def _fail(self, it: dict, exc: BaseException, rd: WR.Reader | None = None) -> str:
        msg = f"{type(exc).__name__}: {exc}"[:400]
        host = it["host"]
        m = re.search(r"PAGE_([A-Z_]+)|REFUSED_(CHALLENGE|EMPTY_READ)", msg)
        if m:
            cls = m.group(1) or ("BLANK" if m.group(2) == "EMPTY_READ" else m.group(2))
            with self.lock:
                self.classes[host][cls] += 1
        if WR.is_gateway_down(msg) or FATAL.search(msg):
            self.stop(msg)
            return "FATAL"
        if "REFUSED_CHALLENGE" in msg:
            self._cool(host, "CHALLENGE", it["url"])
            return "CHALLENGE"
        if "PAGE_NOT_FOUND" in msg:
            if it["kind"] in ("front", "front_text"):
                if RS.record_section_not_found(it["url"], msg, self.now_fn()):
                    self.printer(f"SECTION_NOT_FOUND {it['url']} (recorded once, dropped)")
                self.dropped.add(it["url"])
            elif it.get("ticker") and it["kind"] in ("stock_links", "stock_text"):
                try:
                    from scripts import dowjones_pull as DP
                    DP.record_not_found(it["site"], it["ticker"], it["url"])
                except Exception:  # noqa: BLE001
                    pass
            return "NOT_FOUND"
        if WR.is_detached(msg):
            try:
                WR.ensure_attached(self.profile, oc=self.driver, log=[])
            except Exception as exc2:  # noqa: BLE001
                self.stop(f"{msg} / re-attach failed: {exc2}"[:400])
                return "FATAL"
        with self.lock:
            self.errors.append(f"{it.get('lane')}: {msg}"[:300])
            self.errors = self.errors[-200:]
        cls = msg.split(":", 1)[1].strip().split(":", 1)[0] if ":" in msg else "ERROR"
        return cls[:40]

    def _mark_read(self, it: dict) -> None:
        now = self.now_fn()
        with self.lock:
            if it["kind"] in ("front", "front_text"):
                self.front_last[it["front_key"]] = now
                if self.persist:
                    DG.atomic_write_json(FRONT_SCHEDULE, {k: v.isoformat(timespec="seconds")
                                                          for k, v in self.front_last.items()})
            elif it["kind"] in ("stock_links", "stock_text"):
                self.stock_last[(it["lane"], it["ticker"])] = now
                if self.persist:
                    DG.locked_append_line(WR.corpus_root() / "_search_seen.jsonl", json.dumps(
                        {"source": it["lane"], "ticker": it["ticker"], "day": now.date().isoformat(),
                         "at": now.isoformat(timespec="seconds"), "by": "reader_pool"}))
            elif it["kind"] == "social":
                self.social_last[(it["host"], it["ticker"])] = now
                if self.persist:
                    DG.locked_append_line(SOCIAL_SEEN, json.dumps(
                        {"host": it["host"], "ticker": it["ticker"],
                         "at": now.isoformat(timespec="seconds")}))

    def _reached_by(self, it: dict) -> dict:
        return {k: it.get(k) for k in ("lane", "section", "parent_url", "position", "depth",
                                       "ticker", "link_text", "via", "question", "digest_id",
                                       "theme", "published_visible")
                if it.get(k) is not None} \
            | {"kind": it["kind"], "via": it.get("via") or "direct"}

    def _read(self, it: dict, rd: WR.Reader) -> str:
        kind = it["kind"]
        if kind == "robots":
            return self._read_robots(it, rd)
        if kind in ("front", "stock_links", "search"):
            return self._read_links(it, rd)
        if kind == "social":
            from scripts import social_browser_pull as SB
            cls, row = SB.read_opened(rd, url=it["url"], ticker=it.get("ticker"),
                                      reached_by=self._reached_by(it))
            with self.lock:
                self.classes[it["host"]][cls] += 1
            if cls == "BLANK":
                rd.refund_slot(f"BLANK social page: {it['url']}")
            elif cls != "OK":
                self._cool(it["host"], cls, row.get("url") or it["url"])
            self._mark_read(it)
            return cls
        return self._read_article(it, rd)

    def _read_robots(self, it: dict, rd: WR.Reader) -> str:
        """One robots.txt page through the same browser: the text is kept
        (`dowjones/robots/<host>.json`) and judges every later URL on the host.
        A bot check or block page cools the host; no file = everything allowed."""
        host, now = it["host"], self.now_fn()
        got = self.driver.read_text(rd.tab, profile_name=self.profile)
        text = str(got.get("text") or "")
        if RS_CHALLENGE(text, got.get("title")):
            cls = "CHALLENGE"
        elif "user-agent" in text.lower():
            cls = "OK"
        else:
            cls = "NO_ROBOTS"              # a 404 page / html: nothing is disallowed
        rd.count_page(it["url"], "OK" if cls != "CHALLENGE" else cls)
        with self.lock:
            self.classes[host][f"ROBOTS_{cls}"] += 1
        if cls == "CHALLENGE":
            self._cool(host, "CHALLENGE", it["url"])
            return cls
        rec = {"host": host, "fetched_utc": now.isoformat(timespec="seconds"), "class": cls,
               "text": text if cls == "OK" else ""}
        if self.persist:
            rec = RS.save_robots(RS.robots_host(host), text=rec["text"], cls=cls, now=now)
        with self.lock:
            self.robots[RS.robots_host(host)] = rec
        return "OK"

    def _paywall(self, host: str, cls: str) -> None:
        """A run of paywall stubs / signed-out pages on one host: that host
        reads only its fronts (the headlines) for `READER_FRONTS_ONLY_S`."""
        with self.lock:
            if cls in ("PAYWALL_STUB", "SIGNED_OUT"):
                self.paywall_streak[host] += 1
                if self.paywall_streak[host] >= int(getattr(_config, "READER_PAYWALL_STREAK", 3)):
                    until = self.now_fn() + timedelta(
                        seconds=float(getattr(_config, "READER_FRONTS_ONLY_S", 21600.0)))
                    if self.fronts_only_until.get(host) is None or \
                            self.fronts_only_until[host] < until:
                        self.fronts_only_until[host] = until
                        self.printer(f"FRONTS_ONLY {host}: {self.paywall_streak[host]} paywalled "
                                     f"pages in a row; headlines only until {until:%H:%M}Z")
                    self.pending = [x for x in self.pending
                                    if not (x["host"] == host and x["kind"] in ("article",))]
            elif cls == "OK":
                self.paywall_streak[host] = 0

    def _fronts_only(self, host: str) -> bool:
        t = self.fronts_only_until.get(host)
        return t is not None and t > self.now_fn()

    def _store_front(self, it: dict, snap: str, landed: str) -> None:
        """A front page is a page read: its headlines in page order and its
        outbound links are stored as a record (`page_kind = "front"`), so the
        digest sees what each front put first. The same headlines twice store
        once (the text hash)."""
        if not self.persist:
            return
        host, site = it["host"], it["site"]
        pat = RS.ARTICLE_PATTERN.get(site)
        rows = []
        if pat:
            sel = WR.select_front_links(snap, pat, now=self.now_fn(), max_age_days=30, limit=80)
            rows = sel["links"]
        out = outbound_links(snap)
        lines = [f"{lk.get('position') or i + 1}. {lk.get('text')}" for i, lk in enumerate(rows)]
        title = WR.snapshot_title(snap)[:200] or it.get("section") or ""
        text = f"{title}\n" + "\n".join(lines)
        news = RS.is_news_host(host)
        from backend.services import dowjones_claims as DC
        kind = it["kind"] if it["kind"] in ("front", "search") else "front"
        if kind == "search" and it.get("question"):
            text = f"{text}\n\nsearched for: {it.get('query')}\nquestion: {it.get('question')}"
        art = {"url": landed or it["url"], "title": title, "text": text,
               "publisher": site, "origin": "reader_pool",
               "column": f"{kind}_{site}_{it.get('section')}",
               "first_seen_utc": DC.now_iso(), "sha": DC.text_sha(f"{it['url']}\n{text}"),
               "page_kind": kind, "page_class": "OK", "host": host,
               "section": it.get("section"),
               "source_kind": "general_news" if news else "dowjones",
               "outbound_links": out, "reached_by": self._reached_by(it)}
        if news:
            art["licence"] = getattr(_config, "READER_NEWS_LICENCE", None)
        try:
            WR.store_article(art)
        except Exception as exc:  # noqa: BLE001 -- the links were queued already
            with self.lock:
                self.errors.append(f"front store: {exc}"[:200])

    def _read_links(self, it: dict, rd: WR.Reader) -> str:
        url, site = it["url"], it["site"]
        snap = rd.snapshot_after_scroll(pages=3, pause_s=1.0)
        landed = it.get("landed_url") or url
        pcls = WR.classify_page(url=url, final_url=landed, title=WR.snapshot_title(snap),
                                raw=snap[:1500], text=snap)
        if it["kind"] == "front" and pcls == "OK" and                 WR.norm_url(landed) != WR.norm_url(url):
            pcls = "REDIRECTED"                  # a section that became another page
        if it["kind"] in ("front", "front_text"):
            with self.lock:
                self.front_results[it["front_key"]] = {
                    "url": url, "landed": landed, "title": WR.snapshot_title(snap)[:120],
                    "class": pcls, "at": self.now_fn().isoformat(timespec="seconds")}
        if pcls == "REDIRECTED":
            rd.count_page(url, pcls)
            return self._fail(it, WR.ReaderRefused(f"PAGE_NOT_FOUND: {url!r} redirected to "
                                                   f"{landed!r}"))
        rd.count_page(url, pcls)
        with self.lock:
            self.classes[it["host"]][pcls] += 1
        if pcls == "CHALLENGE":
            self._cool(it["host"], "CHALLENGE", url)
            return pcls
        if pcls == "BLANK":
            rd.refund_slot(f"BLANK list page: {url}")
            return pcls
        if pcls == "NOT_FOUND":
            return self._fail(it, WR.ReaderRefused(f"PAGE_NOT_FOUND: {url!r}"))
        self._mark_read(it)
        if pcls != "OK":
            return pcls
        front = kind_front = it["kind"] == "front"
        search = it["kind"] == "search"
        now = self.now_fn()
        if front or search:
            self._store_front(it, snap, landed)
        pattern = RS.ARTICLE_PATTERN.get(site) if (front or search) else RS.ANY_DJ_ARTICLE
        limit = (self.front_links_max if front else
                 int(getattr(_config, "READER_SEARCH_LINKS_MAX", 3)) if search else 4)
        # 2026-09-29: links whose visible date is older than
        # READER_MAX_ARTICLE_AGE_DAYS are not queued (was 30 days on a stock page:
        # 455 of 995 Dow Jones pages in 36 h were archive, median 65 days)
        age_days = min(3.0, RS.max_article_age_days()) if front else RS.max_article_age_days()
        found = []
        if pattern and not self._fronts_only(it["host"]):
            sel = WR.select_front_links(snap, pattern, now=now, max_age_days=age_days,
                                        limit=limit)
            found = [("article", lk) for lk in sel["links"]]
        if kind_front and RS.MEDIA_PATTERN.get(site):
            msel = WR.select_front_links(snap, RS.MEDIA_PATTERN[site], now=now, max_age_days=7,
                                         limit=int(getattr(_config,
                                                           "READER_FRONT_MEDIA_LINKS_MAX", 3)))
            found += [("media", lk) for lk in msel["links"]]
        tier = RS.TIER_FRONT_NEWS if (front or search) else RS.ticker_tier(
            it.get("ticker"), books=self.books, fresh=self.fresh)
        n_new = 0
        with self.lock:
            for kind, lk in found:
                u = lk["url"]
                if self.stored.get(WR.norm_url(u)) or not WR.host_ok(u):
                    continue
                rs = self.robots_state(u)
                if rs is False:
                    self._refused_by_robots(u, it["lane"])
                    continue
                if rs is None:
                    self._need_robots(WR.host_of(u))
                n_new += self._add({"kind": kind, "site": site_of(u),
                                    "host": WR.host_of(u), "lane": it["lane"],
                                    "section": it.get("section"), "ticker": it.get("ticker"),
                                    "url": u, "parent_url": url, "position": lk.get("position"),
                                    "depth": 0, "tier": tier, "link_text": lk.get("text"),
                                    "via": it["kind"],
                                    "published_visible": lk.get("published_visible"),
                                    "question": it.get("question"),
                                    "digest_id": it.get("digest_id"),
                                    "theme": it.get("theme")})
            self.stats[it["host"]]["links_found"] += len(found)
            self.stats[it["host"]]["links_new"] += n_new
            if it["kind"] == "front":
                self.front_results[it["front_key"]].update(links=len(found), new=n_new)
        return "OK"

    def _read_article(self, it: dict, rd: WR.Reader) -> str:
        kind = it["kind"]
        host = it["host"]
        news = RS.is_news_host(host)
        column = it.get("column") or (f"{it['site']}_{it['section']}" if kind == "front_text"
                                      else None)
        if news and column is None:
            column = f"news_{it['site']}_{it.get('section') or 'other'}"
        link = {"url": it["url"], "text": it.get("link_text")} if it.get("link_text") \
            else it["url"]
        extra = {"reached_by": self._reached_by(it), "page_kind": kind, "host": host,
                 "section": it.get("section")}
        if news:
            extra.update(publisher=it["site"], source_kind="general_news",
                         licence=getattr(_config, "READER_NEWS_LICENCE", None))
        # the page's outbound links (related blocks and in-article links), read
        # from the same tab before the text read; no page load
        snap_links: list[dict] = []
        if int(it.get("depth") or 0) == 0 and kind in ("article", "media"):
            try:
                snap_links = outbound_links(rd.snapshot())
            except Exception as exc:  # noqa: BLE001 -- the article stands without them
                with self.lock:
                    self.errors.append(f"outbound snapshot: {exc}"[:200])
        extra["outbound_links"] = snap_links
        try:
            art = rd.finish_article(link, column=column,
                                    tickers=[it["ticker"]] if it.get("ticker") else None,
                                    t0=time.time(), extra=extra,
                                    with_media=True, universe=self.universe)
        except WR.ReaderRefused as exc:
            m = re.search(r"PAGE_(PAYWALL_STUB|SIGNED_OUT)", str(exc))
            if m:
                self._paywall(host, m.group(1))
            raise
        self._paywall(host, "OK")
        with self.lock:
            self.classes[it["host"]]["OK"] += 1
            self.stored.setdefault(WR.norm_url(art.get("url") or it["url"]), set()).add(
                self.now_fn().date().isoformat())
            self.stored.setdefault(WR.norm_url(it["url"]), set()).add(
                self.now_fn().date().isoformat())
        if kind in ("stock_text", "front_text"):
            self._mark_read(it)
        raw = art.get("_media_raw") or {}
        items = MT.items_from_media(art.get("url") or it["url"], raw.get("media"),
                                    published_utc=art.get("published_utc"))
        if items:
            fetch = self.caption_fetch or MT.fetch_captions
            resolved = MT.resolve_transcripts(items, fetch=fetch)
            if self.persist:
                MT.store_items(resolved, reached_by=self._reached_by(it))
            with self.lock:
                mc = self.media_counts[it["host"]]
                mc["items"] += len(resolved)
                mc["with_transcript"] += sum(1 for x in resolved
                                             if x.get("transcript") != MT.NONE_PUBLISHED)
        if RS.is_archive(art.get("published_utc"), self.now_fn()):
            with self.lock:
                self.stats[host]["archive_read"] += 1
            return "OK"                      # an archive page: read, not followed
        if int(it.get("depth") or 0) == 0 and self._browsing(it):
            self._follow_browse(it, art, snap_links)
        elif int(it.get("depth") or 0) == 0 and art.get("_related"):
            self._follow_related(it, art)
        return "OK"

    def _adopt_read_next(self, now: datetime) -> int:
        """The digest's asks -> pending (called under the lock by `refill`),
        ranked with the section fronts (tier 0): they are targeted asks.

        A row with a `url` on an allowed, non-social host is read as an
        article; a row with a `search_query` becomes a NAVIGATION to the own
        search URL of `RS.SEARCH_SITES_PER_QUESTION` sites (never typing). At
        most READER_READ_NEXT_PER_REFILL rows per refill, rows older than
        READER_READ_NEXT_MAX_AGE_H ignored, each row adopted once (recorded in
        `dowjones/read_next_adopted.jsonl`, so a restart does not repeat it)."""
        path = self.read_next_path
        if path is None or not Path(path).exists():
            return 0
        per = int(getattr(_config, "READER_READ_NEXT_PER_REFILL", 6))
        max_age_h = float(getattr(_config, "READER_READ_NEXT_MAX_AGE_H", 36.0))
        added = taken = 0
        try:
            lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return 0
        for ln in lines:
            if taken >= per:
                break
            try:
                row = json.loads(ln)
            except ValueError:
                continue
            key = RS.read_next_key(row)
            if key in ("url:", "q:") or key in self.read_next_done:
                continue
            try:
                t = datetime.fromisoformat(str(row.get("t")))
                if (now - t).total_seconds() > max_age_h * 3600:
                    continue
            except (TypeError, ValueError):
                pass
            taken += 1
            self.read_next_done.add(key)
            ctx = {k: row.get(k) for k in ("question", "digest_id", "theme")}
            items: list[str] = []
            u = str(row.get("url") or "").strip()
            if u:
                if WR.host_ok(u) and not WR.is_social(u) and not self.stored.get(WR.norm_url(u)):
                    if self._add({"kind": "article", "site": site_of(u), "host": WR.host_of(u),
                                  "lane": "read_next", "section": "read_next", "url": u,
                                  "tier": RS.TIER_FRONT, "via": "read_next",
                                  "parent_url": "read_next", "position": 1, "depth": 0,
                                  **ctx}):
                        items.append(u)
            else:
                q = str(row.get("search_query") or row.get("question") or "")
                for site in RS.search_sites_for(self.read_next_n):
                    su = RS.search_url(site, q)
                    host = WR.host_of(su or "")
                    if not su or not WR.host_ok(su):
                        continue
                    if RS.is_news_host(host) and self._robots_rec(host) is None:
                        self._need_robots(host, site)      # queued ahead of the search
                    if self._add({"kind": "search", "site": site, "host": host,
                                  "lane": f"search:{site}", "section": "read_next",
                                  "url": su, "query": q, "tier": RS.TIER_FRONT,
                                  "key": f"search:{site}:{key}", **ctx}):
                        items.append(su)
                self.read_next_n += 1
            added += len(items)
            if self.persist:
                try:
                    DG.locked_append_line(DJ / "read_next_adopted.jsonl", json.dumps(
                        {"t": now.isoformat(timespec="seconds"), "key": key,
                         "digest_id": row.get("digest_id"), "queued": items}))
                except Exception:  # noqa: BLE001 -- the items are queued either way
                    pass
        return added

    def _load_carry(self, path: Path | None = None, max_age_h: float = 6.0) -> int:
        """Pending found links a previous pool left (read once, then removed)."""
        pth = path or PENDING_CARRY or DJ / "pool_pending_carry.json"
        d = _load_json(pth)
        n = 0
        try:
            t = datetime.fromisoformat(str(d.get("t")))
            fresh = (self.now_fn() - t).total_seconds() <= max_age_h * 3600
        except (TypeError, ValueError):
            fresh = False
        if fresh:
            for it in d.get("items") or []:
                if not isinstance(it, dict) or it.get("kind") not in CARRY_KINDS:
                    continue
                if self.stored.get(WR.norm_url(it.get("url") or "")):
                    continue
                it = {k: v for k, v in it.items() if k != "seq"}
                if it.get("kind") == "search" or it.get("via") == "read_next":
                    it["tier"] = RS.TIER_FRONT        # the digest's asks rank with the fronts
                n += self._add(it)
        try:
            pth.unlink()
        except OSError:
            pass
        return n

    def save_carry(self, path: Path | None = None) -> int:
        with self.lock:
            items = [it for it in self.pending if it.get("kind") in CARRY_KINDS]
        try:
            DG.atomic_write_json(path or PENDING_CARRY or DJ / "pool_pending_carry.json", {
                "t": self.now_fn().isoformat(timespec="seconds"), "items": items})
        except Exception:  # noqa: BLE001 -- a carry file never blocks a stop
            return 0
        return len(items)

    @staticmethod
    def _browsing(it: dict) -> bool:
        """An article reached from a section front (the browse lane): its
        outbound links are followed without the ticker rule."""
        return it.get("via") == "front" or str(it.get("lane") or "").startswith("front:")

    def _follow_browse(self, it: dict, art: dict, snap_links: list[dict]) -> int:
        """PURE-ish (queue only). Up to `READER_BROWSE_FOLLOW_MAX` links, one hop:
        the related block on the SAME host first, then in-article links on any
        allowed, non-social host that have that host's article shape. Stored,
        queued, robots-disallowed and account / ad links are skipped."""
        parent_url = art.get("url") or it["url"]
        ph = WR.host_of(parent_url)
        cands: list[tuple[str, str]] = []
        for lk in art.get("_related") or []:
            u = str(lk.get("url") or "")
            if WR.host_of(u) == ph:
                cands.append((u, str(lk.get("text") or "")))
        cands += [(str(lk.get("url") or ""), str(lk.get("text") or "")) for lk in snap_links]
        n = 0
        seen: set[str] = set()
        with self.lock:
            for pos, (u, t) in enumerate(cands, 1):
                if n >= self.follow_max:
                    break
                k = WR.norm_url(u)
                if not u or k in seen or k == WR.norm_url(parent_url):
                    continue
                seen.add(k)
                if len(t) < 12 or WR.ARTICLE_DENY_LINK_TEXT.search(t) or WR.AD_TEXT.search(t):
                    continue
                if not WR.host_ok(u) or WR.is_social(u) or not RS.any_article_pattern(u):
                    continue
                if self.stored.get(k) or k in self.queued or self._fronts_only(WR.host_of(u)):
                    continue
                rs = self.robots_state(u)
                if rs is False:
                    self._refused_by_robots(u, "browse")
                    continue
                if rs is None:
                    self._need_robots(WR.host_of(u))
                if self._add({"kind": "article", "site": site_of(u), "host": WR.host_of(u),
                              "lane": "related" if WR.host_of(u) == ph else "browse",
                              "section": it.get("section"), "ticker": it.get("ticker"),
                              "url": u, "parent_url": parent_url, "position": pos,
                              "depth": 1, "tier": it.get("tier"), "link_text": t,
                              "via": "related" if WR.host_of(u) == ph else "browse",
                              "key": k}):
                    n += 1
            self.stats[ph]["browse_followed"] += n
        return n

    def _follow_related(self, it: dict, art: dict) -> None:
        site = WR.host_of(art.get("url") or it["url"]).split(".")[0]
        pattern = RS.ARTICLE_PATTERN.get(site)
        if not pattern:
            return
        named = art.get("tickers_named") or []
        parent = {"depth": 0, "url": art.get("url") or it["url"]}
        n = 0
        cap = int(getattr(_config, "READER_RELATED_LINKS_MAX", 3))
        with self.lock:
            for pos, lk in enumerate(art["_related"], 1):
                u, t = str(lk.get("url") or ""), str(lk.get("text") or "")
                if n >= cap:
                    break
                if len(t) < 12 or WR.ARTICLE_DENY_LINK_TEXT.search(t) or WR.AD_TEXT.search(t):
                    continue
                if not RS.may_follow_related(parent, u, universe=self.universe, named=named,
                                             pattern=pattern):
                    continue
                if self.stored.get(WR.norm_url(u)) or not WR.host_ok(u):
                    continue
                if self._add({"kind": "article", "site": site, "host": WR.host_of(u),
                              "lane": "related", "section": it.get("section"),
                              "ticker": it.get("ticker") or (named[0] if named else None),
                              "url": u, "parent_url": parent["url"], "position": pos,
                              "depth": 1, "tier": it.get("tier"), "link_text": t,
                              "via": "related"}):
                    n += 1

    # ── the loop ────────────────────────────────────────────────────────────

    READER_TAB_IDS_KEEP = 500

    def _remember_tab(self, tab: str) -> None:
        if tab and tab not in self.reader_tab_ids[-50:]:
            self.reader_tab_ids.append(str(tab))
            del self.reader_tab_ids[:-self.READER_TAB_IDS_KEEP]

    def all_reader_tab_ids(self) -> list[str]:
        """Every tab id this process opened: the ones it registered, the ones
        the client still holds as opened-and-not-closed (`_OPENED_TABS`, which
        includes a tab made by an open that then failed), and the orphans."""
        held = getattr(self.driver, "_OPENED_TABS", None)
        extra = sorted(str(t) for t in held) if isinstance(held, (set, frozenset)) else []
        out = list(dict.fromkeys([*self.reader_tab_ids, *extra, *self.orphans,
                                  *sorted(self.open_tabs)]))
        return out[-self.READER_TAB_IDS_KEEP:]

    def slot_loop(self, slot: int) -> None:
        idle = 0
        while not self.stop_event.is_set():
            it = self.take(slot)
            if it is None:
                idle += 1
                if idle % 30 == 0:
                    self.refill()
                self.stop_event.wait(2.0)
                continue
            idle = 0
            try:
                self.process(it, slot)
            except Exception as exc:  # noqa: BLE001 -- a thread never dies silently
                self._fail(it, exc)
            finally:
                self.release(it)

    def should_stop(self) -> str | None:
        if self.until is not None and self.now_fn() >= self.until:
            return "END_TIME"
        for f in STOP_FILES:
            if f.exists():
                return f"STOP file {f.name}"
        hand = Path(getattr(_config, "DOWJONES_HANDOFF_FILE", REPO / "HANDOFF_PC"))
        if not hand.exists():
            return "REFUSED_NO_HANDOFF: the HANDOFF_PC file is gone"
        return None

    # ── status, receipt ─────────────────────────────────────────────────────

    def status(self) -> dict:
        with self.lock:
            return self._status()

    def _status(self) -> dict:
        now = self.now_fn()
        rows = self.thr._rows()
        hosts = sorted(set(self.per_host) | {it["host"] for it in self.pending}
                       | {RS.front_host(f) for f in self.fronts})
        cool = self.cooling.active(now)
        by_host = {}
        for h in hosts:
            hr = [r for r in rows if r[1] == h]
            by_host[h] = {
                "open_tabs": self.inflight[h], "tab_limit": int(self.per_host.get(h, 1)),
                # reserved slots (future-dated) count: they are opens already granted
                "loads_60m": sum(1 for r in hr if now - r[0] < timedelta(hours=1)),
                "cap_hour": self.thr.host_hour_cap(h),
                "loads_24h": sum(1 for r in hr if now - r[0] < timedelta(days=1)),
                "cap_day": self.thr.host_day_cap(h),
                "pending": sum(1 for it in self.pending if it["host"] == h),
                "classes": dict(self.classes[h]),
                "cooling": cool.get(h), "blocked_until": (self.host_blocked_until.get(h).isoformat(
                    timespec="seconds") if self.host_blocked_until.get(h) and
                    self.host_blocked_until[h] > now else None)}
            for k in ("loads_60m", "loads_24h"):
                cap = by_host[h]["cap_hour" if k == "loads_60m" else "cap_day"]
                if cap:
                    by_host[h][k.replace("loads", "use")] = f"{by_host[h][k]}/{cap}"
        # 2026-09-29: what each host is DOING, in the words the supervisor reads
        pend = {h: v["pending"] for h, v in by_host.items()}
        host_states = {}
        for h, v in by_host.items():
            capped = bool(v["blocked_until"]) or (
                bool(v["cap_day"]) and v["loads_24h"] >= v["cap_day"]) or (
                bool(v["cap_hour"]) and v["loads_60m"] >= v["cap_hour"])
            due = RS.next_front_due_s(self.fronts, self.front_last, now, pending_by_host=pend,
                                      dropped=self.dropped, host=h)
            v["next_front_due_s"] = None if due is None else round(due, 1)
            v["fronts_only_until"] = (self.fronts_only_until[h].isoformat(timespec="seconds")
                                      if self._fronts_only(h) else None)
            host_states[h] = v["queue_state"] = RS.host_queue_state(
                pending=v["pending"], in_flight=v["open_tabs"], capped=capped,
                cooling=bool(v["cooling"]), front_due_in_s=due)
        qstate = RS.pool_queue_state(host_states)
        blocked = {h for h, s in host_states.items() if s in (RS.Q_COOLING, RS.Q_WAITING_FOR_CAP)}
        nxt = RS.next_front_due_s(self.fronts, self.front_last, now, pending_by_host=pend,
                                  dropped=self.dropped, blocked=blocked)
        tiers = Counter(RS.TIER_NAMES[self._key(it)[0]] for it in self.pending)
        ok_60 = sum(1 for t in self.timings if t.get("outcome") == "OK" and
                    now - datetime.fromisoformat(t["at"]) <= timedelta(hours=1))
        run_h = max(1e-9, (now - self.started).total_seconds() / 3600.0)
        ok_run = sum(self.classes[h]["OK"] for h in self.classes)
        return {"t": now.isoformat(timespec="seconds"), "pid": os.getpid(),
                # review 2026-09-29 F2: the state is what the pool is DOING,
                # never "reading" merely because the process is alive
                "state": "stopping" if self.stop_event.is_set() else qstate.lower(),
                "queue_state": qstate,
                "throughput": {"ok_last_60m": ok_60, "run_hours": round(run_h, 2),
                               # measured over the whole run, not a burst
                               "sustained_ok_per_hour": round(ok_run / run_h, 1)
                               if run_h >= 0.5 else None}, "next_front_due_s": None if nxt is None else round(nxt, 1),
                "last_refill": self.last_refill,
                "carried_in": getattr(self, "carried_in", 0),
                "early_front_revisits": dict(self.early_fronts),
                "robots_disallowed": dict(self.robots_refused),
                "stop_reason": self.stop_reason,
                "tabs": {"target": self.gov.target, "max": self.gov.max_tabs,
                         "open_now": len(self.open_tabs), "in_flight": sum(self.inflight.values()),
                         "why": self.gov.reason, "free_gb": self.gov.free_gb,
                         "floor_gb": self.gov.floor_gb},
                "caps": {"hour_all": self.thr.max_per_hour, "day_all": self.thr.max_per_day,
                         "loads_60m_all": sum(1 for r in rows
                                              if now - r[0] < timedelta(hours=1)),
                         "loads_24h_all": sum(1 for r in rows if now - r[0] < timedelta(days=1))},
                "hosts": by_host, "pending_by_tier": dict(tiers),
                "pages_this_run": self.pages, "media": {h: dict(c) for h, c in
                                                        self.media_counts.items()},
                "cooling_events": self.cool_events[-10:], "last_errors": self.errors[-5:],
                "fronts": self.front_results,
                "orphaned_tabs": self.orphans,
                # 2026-09-29: the tab ids, so a supervisor that stops this
                # process by PID can close exactly the tabs it left behind
                "open_tab_ids": sorted(self.open_tabs),
                "reader_tab_ids": self.all_reader_tab_ids(),
                # the earliest reserved open still ahead (a far-future value with
                # no page reads = waiting for a cap, not stalled)
                "next_slot_in_s": next_slot_in_s(rows, now)}

    def receipt(self) -> dict:
        with self.lock:
            return self._receipt()

    def _receipt(self) -> dict:
        import statistics as S
        agg: dict[str, dict] = {}
        for t in self.timings:
            k = f"{t['host']}|{t['kind']}"
            agg.setdefault(k, {"n": 0, "wait_s": [], "open_s": [], "work_s": []})
            agg[k]["n"] += 1
            for f in ("wait_s", "open_s", "work_s"):
                agg[k][f].append(t[f])
        timing = {k: {"n": v["n"], **{f"median_{f}": round(S.median(v[f]), 2)
                                      for f in ("wait_s", "open_s", "work_s")}}
                  for k, v in agg.items()}
        return {"receipt": "reader_pool", "started_utc": self.started.isoformat(timespec="seconds"),
                "pid": os.getpid(), "profile": self.profile, "names": len(self.names),
                "books": sorted(self.books), "fresh": sorted(self.fresh),
                "stop_reason": self.stop_reason, "pages": self.pages,
                "stats": {h: dict(c) for h, c in self.stats.items()},
                "classes": {h: dict(c) for h, c in self.classes.items()},
                "timing_medians": timing, "timings_tail": self.timings[-50:],
                "governor_history": self.gov.history, "cooling_events": self.cool_events,
                "media": {h: dict(c) for h, c in self.media_counts.items()},
                "sections_dropped": sorted(self.dropped), "errors": self.errors[-50:],
                "fronts": self.front_results,
                "open_tabs_now": sorted(self.open_tabs), "orphaned_tabs": self.orphans,
                "reader_tab_ids": self.all_reader_tab_ids(),
                "throttle_targets_s": self.thr.targets[-200:]}

    def run(self, *, status_path: Path | None = STATUS, receipt_path: Path | None = None,
            status_every_s: float = 15.0, report_every_s: float = 3600.0) -> dict:
        self.refill()
        n_slots = max(1, int(self.gov.max_tabs))
        threads = [threading.Thread(target=self.slot_loop, args=(i,), daemon=True,
                                    name=f"pool{i}") for i in range(n_slots)]
        for th in threads:
            th.start()
        last_report = 0.0
        last_refill = time.time()
        try:
            while not self.stop_event.is_set():
                why = self.should_stop()
                if why:
                    self.stop(why)
                    break
                self.gov.update(len(self.open_tabs))
                if time.time() - last_refill > 60:
                    self.refill()
                    last_refill = time.time()
                if status_path is not None:
                    try:
                        DG.atomic_write_json(status_path, self.status())
                    except Exception:  # noqa: BLE001 -- a status line never stops reading
                        pass
                if receipt_path is not None:
                    try:
                        DG.atomic_write_json(receipt_path, self.receipt())
                    except Exception:  # noqa: BLE001
                        pass
                if self.persist and time.time() - last_report >= report_every_s:
                    last_report = time.time()
                    try:
                        from backend.services import reader_report as RR
                        RR.write_report(universe=self.names)
                    except Exception as exc:  # noqa: BLE001
                        self.errors.append(f"report: {exc}"[:200])
                self.stop_event.wait(status_every_s)
        finally:
            self.stop_event.set()
            for th in threads:
                th.join(timeout=150)
            if self.persist:
                self.save_carry()
            for tab in list(self.open_tabs):      # a thread that did not finish: close its tab
                try:
                    self.driver.browser("close", profile_name=self.profile, target_id=tab)
                except Exception:  # noqa: BLE001
                    self.orphans.append(tab)
            if status_path is not None:
                try:
                    DG.atomic_write_json(status_path, self.status())
                except Exception:  # noqa: BLE001
                    pass
            if receipt_path is not None:
                DG.atomic_write_json(receipt_path, self.receipt())
            if self.persist:
                try:
                    from backend.services import reader_report as RR
                    RR.write_report(universe=self.names)
                except Exception:  # noqa: BLE001
                    pass
        return self.receipt()


def read_next_adopted(path: Path | None = None) -> set[str]:
    """Keys of digest asks already adopted (any earlier run)."""
    out: set[str] = set()
    try:
        for ln in (path or DJ / "read_next_adopted.jsonl").read_text(
                encoding="utf-8", errors="replace").splitlines():
            try:
                out.add(str(json.loads(ln)["key"]))
            except (ValueError, KeyError, TypeError):
                continue
    except OSError:
        pass
    return out


def site_of(url: str) -> str:
    """PURE. The site key of a URL's host (`reuters`, `wsj`, ...); an unknown
    host falls back to its first label (the old rule)."""
    h = WR.host_of(url)
    return RS.site_key_of_host(h) or h.split(".")[0]


def outbound_links(snapshot_text: str, *, limit: int | None = None) -> list[dict]:
    """PURE. The links a page SHOWS, for the page record: `[{url, text}]`,
    deduplicated by canonical URL, http(s) only, article-shaped links (on any
    known host) first and then the rest with headline-length text, at most
    `READER_OUTBOUND_LINKS_STORED`. Nothing here is opened."""
    cap = int(limit if limit is not None else
              getattr(_config, "READER_OUTBOUND_LINKS_STORED", 60))
    first, rest, seen = [], [], set()
    for lk in WR.parse_snapshot(snapshot_text or "")["links"]:
        u, t = str(lk.get("url") or ""), str(lk.get("text") or "").strip()
        if not u.lower().startswith(("http://", "https://")):
            continue
        k = WR.norm_url(u)
        if k in seen:
            continue
        seen.add(k)
        row = {"url": u[:500], "text": t[:200]}
        if RS.any_article_pattern(u):
            first.append(row)
        elif len(t) >= 12:
            rest.append(row)
    return (first + rest)[:cap]


def RS_CHALLENGE(text: str, title: str | None) -> bool:
    """PURE. A robots.txt read that came back as a bot check / block page."""
    return bool(WR._CHALLENGE.search(f"{title or ''}\n{(text or '')[:1500]}"))


# ───────────────────────────────── the CLI ───────────────────────────────────

def next_slot_in_s(rows: list, now: datetime) -> float | None:
    """PURE. Seconds until the EARLIEST future-dated reservation, or None when
    no reservation lies ahead."""
    ahead = [r[0] for r in rows if r[0] > now]
    return round((min(ahead) - now).total_seconds(), 1) if ahead else None


def previous_open_tabs(rdir: Path = DJ, keep: int = 3) -> list[str]:
    """Tabs earlier pool runs recorded as open and never closed (by receipt)."""
    out: list[str] = []
    for p in sorted(rdir.glob("pool_*.json"))[-keep:]:
        d = _load_json(p)
        out += list(d.get("open_tabs_now") or []) + list(d.get("orphaned_tabs") or [])
    return out


def parse_fronts(spec: str) -> list[dict]:
    """`wsj:home,barrons:markets` -> those SECTION_FRONTS entries (refuses unknown)."""
    want = [p.strip().lower() for p in (spec or "").split(",") if p.strip()]
    by = {RS.front_key(f): f for f in RS.SECTION_FRONTS + RS.NEWS_FRONTS}
    bad = [w for w in want if w not in by]
    if bad:
        raise WR.ReaderRefused(f"REFUSED_FRONTS: unknown {bad}; known {sorted(by)}")
    return [by[w] for w in want]


def end_time(hhmm: str | None) -> datetime | None:
    if not hhmm:
        return None
    h, m = (int(x) for x in hhmm.split(":"))
    now = datetime.now()
    end = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if end <= now:
        end += timedelta(days=1)
    return end.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--handoff", action="store_true")
    ap.add_argument("--profile", default="muratclaw")
    ap.add_argument("--until", default=None, help="local HH:MM")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--max-tabs", type=int, default=None)
    ap.add_argument("--worker-id", default="pool")
    ap.add_argument("--trial", action="store_true",
                    help="a short trial: only --fronts and --tickers, fronts due at once")
    ap.add_argument("--fronts", default=None, help="site:section,... (default: all)")
    ap.add_argument("--tickers", default=None, help="T1,T2 (default: the rolling universe)")
    ap.add_argument("--no-social", action="store_true")
    ap.add_argument("--front-links", type=int, default=None,
                    help="article links taken per front (default config READER_FRONT_LINKS_MAX)")
    a = ap.parse_args(argv)
    hand = Path(getattr(_config, "DOWJONES_HANDOFF_FILE", REPO / "HANDOFF_PC"))
    if not a.handoff or not hand.exists():
        print(f"REFUSED_NO_HANDOFF: the pool needs --handoff AND {hand} (Murat's act).")
        return 2
    from backend.services import openclaw_client as OC
    from scripts import dowjones_pull as DP
    print(DP.TOU_SENTENCE, flush=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    rpath = DJ / f"pool_{stamp}{'_trial' if a.trial else ''}.json"
    lock = None
    try:
        WR.ensure_attached(a.profile, oc=OC, log=[])
        proof = DP.instance_gate(a.profile, OC)
        if proof is None or not WR.direct_open_ok(OC, a.profile):
            print(f"REFUSED_NOT_DEDICATED: the pool runs only on a dedicated, proven profile; "
                  f"{a.profile!r} is not one")
            return 2
        lock = WR.acquire_reader_lock(worker=a.worker_id)
        cleanup = WR.close_leftover_tabs(OC, a.profile, previous_open_tabs())
        print(f"startup cleanup: closed {len(cleanup.get('closed') or [])} leftover tab(s)",
              flush=True)
        names = ([t.strip().upper() for t in a.tickers.split(",") if t.strip()] if a.tickers
                 else DP.rolling_names())
        books = book_names()
        if not a.tickers:
            names = list(dict.fromkeys(names + sorted(books)))
        fronts = parse_fronts(a.fronts) if a.fronts else (None if not a.trial else [])
        gov = RS.TabGovernor(max_tabs=a.max_tabs or int(getattr(_config, "READER_MAX_TABS", 6)))
        thr = WR.Throttle(WR.throttle_path(), wait_on_hour_cap=True, per_host_mode=True)
        pool = Pool(driver=OC, throttle=thr, profile=a.profile, names=names, books=books,
                    fresh=fresh_names(_now()), fronts=fronts, social=not a.no_social,
                    governor=gov, until=end_time(a.until), max_pages=a.max_pages,
                    front_last={} if a.trial else None, persist=True,
                    front_links_max=a.front_links)
        print(f"pool: {len(names)} names, {len(pool.fronts)} fronts, social "
              f"{'on' if pool.social else 'off'}, up to {gov.max_tabs} tabs "
              f"({pool.per_host}), receipt {rpath}", flush=True)
        rc = pool.run(receipt_path=rpath)
    except Exception as exc:  # noqa: BLE001 -- the refusal is printed for the supervisor
        print(f"REFUSED: {type(exc).__name__}: {exc}", flush=True)
        return 2
    finally:
        if lock is not None:
            WR.release_reader_lock(lock)
    print(json.dumps({"receipt": str(rpath), "pages": rc["pages"], "stop": rc["stop_reason"],
                      "classes": rc["classes"], "media": rc["media"]}, indent=1, default=str),
          flush=True)
    why = str(rc.get("stop_reason") or "")
    return 0 if (why.startswith(("END_TIME", "STOP file", "BUDGET_SPENT")) or not why) else 2


if __name__ == "__main__":
    sys.exit(main())
