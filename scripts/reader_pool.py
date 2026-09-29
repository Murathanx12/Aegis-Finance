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
Every stored article carries `reached_by` (lane, section, parent url, position,
depth). The order is `reader_scheduler.priority_key`.

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
SOCIAL_SEEN = WR.corpus_root() / "_social_seen.jsonl"
#: the codes that end the whole pool (the supervisor classifies the log tail)
FATAL = re.compile(r"REFUSED_NOT_MURATCLAW_INSTANCE|REFUSED_INSTANCE_|REFUSED_TAB_NOT_IN_INSTANCE|"
                   r"REFUSED_MAIN_CHROME_PROFILE|REFUSED_THROTTLE_DAY\b")
CHALLENGE_CLASSES = ("CHALLENGE", "LOGIN_WALL", "INTERSTITIAL", "RATE_LIMITED")
#: kinds that come round again (a front on its schedule, a stock or social page
#: after its freshness window); an article url is read once
RECURRING = ("front", "front_text", "stock_links", "stock_text", "social")


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
                 reader_sleep: Any = None, front_links_max: int | None = None) -> None:
        self.driver, self.thr, self.profile = driver, throttle, profile
        self.names = [n.upper() for n in dict.fromkeys(names)]
        self.universe = set(self.names)
        self.books, self.fresh = set(books), set(fresh)
        self.fronts = list(RS.SECTION_FRONTS if fronts is None else fronts)
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
        self.started = self.now_fn()

    # ── the queue ───────────────────────────────────────────────────────────

    def _key(self, it: dict) -> tuple:
        return RS.priority_key(it, books=self.books, fresh=self.fresh, last_read=self.last_read)

    def _add(self, it: dict) -> bool:
        k = it.get("key") or WR.norm_url(it["url"])
        if k in self.queued:
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

    def refill(self) -> int:
        """Due fronts, stale stock pages, stale social pages -> pending."""
        now = self.now_fn()
        added = 0
        stock_h = float(getattr(_config, "READER_STOCK_FRESH_H", 20.0))
        social_h = float(getattr(_config, "READER_SOCIAL_FRESH_H", 12.0))
        with self.lock:
            for f in self.fronts:
                url = RS.front_url(f, self.dropped)
                fk = RS.front_key(f)
                if url is None or not RS.front_due(f, self.front_last.get(fk), now):
                    continue
                added += self._add({"kind": f.get("kind", "front"), "site": f["site"],
                                    "host": RS.site_host(f["site"]), "section": f["section"],
                                    "lane": f"front:{fk}", "url": url, "front_key": fk,
                                    "key": f"front:{fk}"})
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
            return
        open_s = time.time() - t_open
        with self.lock:
            self.pages += 1
            self.open_tabs[op["new_tab"]] = url
        rd = WR.Reader(profile=self.profile, tab=op["new_tab"], throttle=self.thr,
                       driver=self.driver, lock=False, direct_open=True, lane=it.get("lane"),
                       worker=f"pool{slot}", page_log=True, max_pages=10 ** 6,
                       sleep_fn=self.reader_sleep or (lambda s: self.stop_event.wait(s) and None))
        rd.pages = rd.tab_pages = 1
        rd._mark_loaded()
        rd._slot_line = res["line"]
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
            if self.max_pages is not None and self.pages >= self.max_pages:
                self.stop(f"BUDGET_SPENT: {self.pages} pages >= --max-pages {self.max_pages}")

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
                                       "ticker", "link_text", "via") if it.get(k) is not None} \
            | {"kind": it["kind"], "via": it.get("via") or "direct"}

    def _read(self, it: dict, rd: WR.Reader) -> str:
        kind = it["kind"]
        if kind in ("front", "stock_links"):
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
        now = self.now_fn()
        pattern = RS.ARTICLE_PATTERN[site] if front else RS.ANY_DJ_ARTICLE
        limit = self.front_links_max if front else 4
        sel = WR.select_front_links(snap, pattern, now=now, max_age_days=3 if front else 30,
                                    limit=limit)
        found = [("article", lk) for lk in sel["links"]]
        if kind_front:
            msel = WR.select_front_links(snap, RS.MEDIA_PATTERN[site], now=now, max_age_days=7,
                                         limit=int(getattr(_config,
                                                           "READER_FRONT_MEDIA_LINKS_MAX", 3)))
            found += [("media", lk) for lk in msel["links"]]
        tier = RS.TIER_FRONT_NEWS if front else RS.ticker_tier(
            it.get("ticker"), books=self.books, fresh=self.fresh)
        n_new = 0
        with self.lock:
            for kind, lk in found:
                u = lk["url"]
                if self.stored.get(WR.norm_url(u)) or not WR.host_ok(u):
                    continue
                n_new += self._add({"kind": kind, "site": WR.host_of(u).split(".")[0],
                                    "host": WR.host_of(u), "lane": it["lane"],
                                    "section": it.get("section"), "ticker": it.get("ticker"),
                                    "url": u, "parent_url": url, "position": lk.get("position"),
                                    "depth": 0, "tier": tier, "link_text": lk.get("text"),
                                    "via": it["kind"]})
            self.stats[it["host"]]["links_found"] += len(found)
            self.stats[it["host"]]["links_new"] += n_new
            if it["kind"] == "front":
                self.front_results[it["front_key"]].update(links=len(found), new=n_new)
        return "OK"

    def _read_article(self, it: dict, rd: WR.Reader) -> str:
        kind = it["kind"]
        column = it.get("column") or (f"{it['site']}_{it['section']}" if kind == "front_text"
                                      else None)
        link = {"url": it["url"], "text": it.get("link_text")} if it.get("link_text") \
            else it["url"]
        art = rd.finish_article(link, column=column,
                                tickers=[it["ticker"]] if it.get("ticker") else None,
                                t0=time.time(), extra={"reached_by": self._reached_by(it),
                                                       "page_kind": kind},
                                with_media=True, universe=self.universe)
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
        if int(it.get("depth") or 0) == 0 and art.get("_related"):
            self._follow_related(it, art)
        return "OK"

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
        hosts = sorted(set(self.per_host) | {it["host"] for it in self.pending})
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
        tiers = Counter(RS.TIER_NAMES[self._key(it)[0]] for it in self.pending)
        return {"t": now.isoformat(timespec="seconds"), "pid": os.getpid(),
                "state": "stopping" if self.stop_event.is_set() else "reading",
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
    by = {RS.front_key(f): f for f in RS.SECTION_FRONTS}
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
