"""Chunk J -- the Dow Jones bundle: free feeds, bounded reads, claims.

    python -m scripts.dowjones_pull --feeds                    # 10 RSS feeds, every item
    python -m scripts.dowjones_pull --probe-free               # which DJ pages answer unauthenticated
    python -m scripts.dowjones_pull --handoff --parent-tab t20 --source wsj \\
        --section heard_on_the_street --max 5
    python -m scripts.dowjones_pull --handoff --parent-tab t33 --source barrons \\
        --section stock_picks --max 5
    python -m scripts.dowjones_pull --handoff --parent-tab t32 --source marketwatch \\
        --section analyst_estimates --tickers MU,DKNG,QUBT
    python -m scripts.dowjones_pull --claims                   # today's stored articles -> forecasts

ROTATION, THE ARCHIVE AND THE QUEUE (Chunk J2, 2026-09-26):
    python -m scripts.dowjones_pull --handoff --plan \
        "barrons:stock_picks:5,wsj:heard_on_the_street:5,marketwatch:analyst_estimates:MU|DKNG|QUBT"
        # one tab per source, opened from the OLDEST tab on that source's host
        # (resolved from `tabs` every run; --parent-tabs "barrons=t13,wsj=t20"
        # overrides), each listing loaded once, then ONE article per source per
        # turn under the one shared throttle. Parallel loads are the bot
        # signature; rotation is not.
    python -m scripts.dowjones_pull --handoff --archive 2026-09-22..2026-09-25
        # WSJ /news/archive/YYYY/MM/DD per trading day, newest first, <=
        # DOWJONES_ARCHIVE_MAX_PER_DAY each, resumable (a stored URL is skipped)
    python -m scripts.dowjones_pull --queue backend/data/optimus/dowjones/QUEUE_<date>.txt \
        --handoff --profile user
        # one command per line, sequential; a line that returns 0 is marked done

TERMS OF USE -- printed on every browser run:
    Dow Jones ToU 9.4.1: "You shall not access, view, retrieve ... scrape ...
    store, harvest, or otherwise ingest the Services or any Content ... using
    any automated means, ... browser automation tool, ... AI agent or assistant
    ... without our prior written consent."  9.3: stored articles may not be
    used "to develop or operate an automated trading system, or for text or
    data mining".
The browser reads run ONLY with `--handoff` AND the file Murat creates when he
hands the PC over (`config.DOWJONES_HANDOFF_FILE`). That file is his decision
to accept the risk the clause describes on his own subscription; nothing in
this repository creates it. Without it the command refuses (rc 2). The
primary path is the paste inbox (`scripts/digest_ingest.py`), where Murat
reads and this code only files what he pasted.

HOW THE BROWSER IS DRIVEN (see `backend/services/openclaw_client.py`)
* profile `user` = Murat's own Chrome. A new tab is opened only FROM an
  existing MuratClaw (Work) tab (`--parent-tab`, which must be on
  wsj/barrons/marketwatch) with a fixed `window.open(<url>)`, so it inherits
  that profile. The CDP `open` verb is refused (it lands in his MAIN profile).
* Listing -> snapshot -> links chosen FROM the snapshot (never a guessed
  article URL) -> click/navigate -> fixed innerText read -> stored locally.
* >= 20 s between page loads, <= 30/h, <= 120/day, <= `--max-pages` (20) per
  session; the tab this run opened is closed at the end.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402
from backend.services import dowjones_claims as DC  # noqa: E402
from backend.services import dowjones_feeds as DF  # noqa: E402
from backend.services import web_reader as WR  # noqa: E402

TOU_SENTENCE = (
    "Dow Jones ToU 9.4.1: no access/scrape/store of the Services 'using any automated "
    "means, ... browser automation tool, ... AI agent or assistant ... without our prior "
    "written consent'; 9.3: stored articles may not be used 'to develop or operate an "
    "automated trading system, or for text or data mining'. Run only because Murat's "
    "HANDOFF_PC file exists; personal research, nothing republished.")

#: source -> section -> (listing URL, article URL regex, column source_id)
SECTIONS: dict[str, dict[str, tuple[str, str, str]]] = {
    "wsj": {
        "heard_on_the_street": (
            "https://www.wsj.com/news/heard-on-the-street",
            r"^https://www\.wsj\.com/(?!news/|market-data|video|podcasts|livecoverage|buyside)"
            r"[a-z-]+/[a-z0-9/-]*-[0-9a-f]{8}(\?|$)",
            "wsj_heard_on_the_street"),
    },
    "barrons": {
        "stock_picks": (
            "https://www.barrons.com/market-data/stocks/stock-picks",
            r"^https://www\.barrons\.com/articles/[a-z0-9-]+-[0-9a-f]{8}(\?|$)",
            "barrons_stock_picks"),
        "big_money_poll": (
            "https://www.barrons.com/topics/big-money-poll",
            r"^https://www\.barrons\.com/articles/[a-z0-9-]+-[0-9a-f]{8}(\?|$)",
            "barrons_big_money_poll"),
    },
    "marketwatch": {
        "analyst_estimates": (
            "https://www.marketwatch.com/investing/stock/{ticker}/analystestimates",
            "", "mw_analyst_estimates"),
    },
}
DEFAULT_MW_TICKERS = ("MU", "DKNG", "QUBT")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _write(rc: dict, name: str) -> Path:
    p = DF.receipts_dir() / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return p


def handoff_ok(path: Path | None = None) -> bool:
    return Path(path or _config.DOWJONES_HANDOFF_FILE).exists()


def default_mw_tickers(cap: int = 10) -> list[str]:
    out = list(DEFAULT_MW_TICKERS)
    try:
        from scripts.source_reads import thematic_tickers
        for t in thematic_tickers():
            if t not in out:
                out.append(t)
    except Exception:  # noqa: BLE001 -- the three named tickers still run
        pass
    return out[:cap]


# ─────────────────────────────── the browser run ────────────────────────────

def run_reads(source: str, section: str, *, parent_tab: str, max_articles: int = 5,
              tickers: list[str] | None = None, max_pages: int = 20,
              profile: str = "user", driver: Any = None, throttle: Any = None,
              progress_path: Path | None = None) -> dict:
    """One bounded reading session in ONE new tab opened from `parent_tab`."""
    if source not in SECTIONS or section not in SECTIONS[source]:
        raise WR.ReaderRefused(f"REFUSED_SECTION: {source}/{section} not in {SECTIONS}")
    listing, pattern, column = SECTIONS[source][section]
    if driver is None:
        from backend.services import openclaw_client as driver  # type: ignore[no-redef]
    thr = throttle or WR.Throttle(WR.throttle_path())
    started = datetime.now(timezone.utc)
    rc: dict[str, Any] = {"receipt": "dowjones_pull.reads", "source": source,
                          "section": section, "column": column, "profile": profile,
                          "parent_tab": parent_tab, "started_utc": started.isoformat(
                              timespec="seconds"), "tou": TOU_SENTENCE, "cost_usd": 0.0,
                          "articles": [], "refusals": []}
    first_url = listing.format(ticker=(tickers or ["MU"])[0].lower())
    reader_lock = WR.acquire_reader_lock()
    try:
        thr.acquire("open_from_tab", host=source + ".com")
        opened = driver.open_from_tab(parent_tab, first_url, profile_name=profile)
    except Exception:
        WR.release_reader_lock(reader_lock)
        raise
    tab = opened["new_tab"]
    rc["tab_opened"] = tab
    rc["attached_to"] = opened.get("attached_to")
    reader = WR.Reader(profile=profile, tab=tab, throttle=thr, driver=driver,
                       max_pages=max_pages, lock=False)
    reader._lock_path = reader_lock
    reader.pages = 1
    reader.log.append({"page": 1, "what": "open_from_tab", "url": first_url,
                       "waited_s": thr.waits[-1] if thr.waits else 0.0,
                       "at": thr.now_fn().isoformat(timespec="seconds")})
    try:
        driver.browser("wait", "--time", "4000", profile_name=profile, target_id=tab)
        if section == "analyst_estimates":
            for i, t in enumerate(tickers or list(DEFAULT_MW_TICKERS)):
                url = listing.format(ticker=t.lower())
                try:
                    art = (_read_current(reader, url, column, t) if i == 0 else
                           reader.read_article(url, column=column))
                    art["ticker"] = t
                    rc["articles"].append(_summary(art))
                except WR.ReaderRefused as exc:
                    rc["refusals"].append({"ticker": t, "why": str(exc)[:200]})
                    if "SESSION_CAP" in str(exc) or "THROTTLE" in str(exc):
                        _progress(rc, reader, progress_path)
                        break
                _progress(rc, reader, progress_path)
        else:
            links = WR.select_links(reader.snapshot(), pattern, limit=max_articles)
            rc["links_found"] = [{"text": lk["text"][:140], "url": lk["url"],
                                  "has_ref": bool(lk["ref"])} for lk in links]
            if not links:
                rc["refusals"].append({"why": "NO_LINKS_ON_LISTING: the snapshot showed no "
                                              "link matching the article pattern"})
            for lk in links[:max_articles]:
                try:
                    rc["articles"].append(_summary(reader.read_article(lk, column=column)))
                except WR.ReaderRefused as exc:
                    rc["refusals"].append({"url": lk["url"], "why": str(exc)[:200]})
                    if "SESSION_CAP" in str(exc) or "THROTTLE" in str(exc) or "LEFT_HOSTS" in str(exc):
                        _progress(rc, reader, progress_path)
                        break
                _progress(rc, reader, progress_path)
    finally:
        try:
            cl = driver.browser("close", profile_name=profile, target_id=tab)
            rc["tab_closed"] = cl.get("rc") == 0
        except Exception as exc:  # noqa: BLE001 -- say it, never hide it
            rc["tab_closed"] = False
            rc["close_error"] = str(exc)[:200]
        fp = reader.close()
        rc["footprint"] = {k: fp.get(k) for k in ("verdict", "cv_of_gaps", "gaps_s",
                                                  "pages_per_hour", "scroll_share", "path")}
    rc["pages"] = reader.log
    gaps = [p["waited_s"] for p in reader.log]
    stamps = [datetime.fromisoformat(p["at"]) for p in reader.log]
    rc["seconds_between_page_loads"] = [round((b - a).total_seconds(), 1)
                                        for a, b in zip(stamps, stamps[1:])]
    rc["throttle_waits_s"] = gaps
    rc["throttle_targets_s"] = list(thr.targets)
    rc["n_articles"] = len(rc["articles"])
    rc["chars_total"] = sum(a["chars"] for a in rc["articles"])
    rc["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return rc


def _progress(rc: dict, reader: WR.Reader, path: Path | None) -> None:
    """The receipt after EVERY page, so a run that is stopped leaves evidence
    (the first live run was stopped and left none)."""
    if path is None:
        return
    rc["pages"] = reader.log
    rc["in_progress"] = True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def _read_current(reader: WR.Reader, url: str, column: str, ticker: str) -> dict:
    """The first MarketWatch page is already loaded by `open_from_tab`; read it
    in place rather than loading it twice. It is scrolled through first, like
    every other read (a read with no scroll telemetry is the tell)."""
    steps = reader.scroll_through()
    reader.reads += 1
    reader.scrolled_reads += bool(steps)
    got = reader.driver.read_text(reader.tab, profile_name=reader.profile)
    if got.get("error") or not (got.get("text") or "").strip():
        raise WR.ReaderRefused(f"REFUSED_EMPTY_READ: {url!r}: "
                               f"{(got.get('error') or 'no text returned')[:200]}")
    final = got.get("url") or url
    if not WR.host_ok(final):
        raise WR.ReaderRefused(f"REFUSED_LEFT_HOSTS: {final!r}")
    text = WR.clean_text(got.get("text") or "", got.get("title"))
    art = {"url": final, "title": got.get("title"), "byline": None,
           "published_utc": None, "text": text, "first_seen_utc": DC.now_iso(),
           "chars": len(text), "raw_chars": len(got.get("text") or ""),
           "publisher": "marketwatch", "origin": "web_reader", "tab": reader.tab,
           "profile": reader.profile, "column": column, "tickers": [ticker],
           "paywall_suspected": False, "read_s": 0.0}
    art["sha"] = DC.text_sha(text)
    if text:
        art["stored"] = WR.store_article(art)
    return art


def _summary(art: dict) -> dict:
    return {k: art.get(k) for k in ("url", "title", "byline", "published_utc",
                                    "first_seen_utc", "chars", "raw_chars", "column",
                                    "sha", "paywall_suspected", "read_s", "ticker")} | {
        "stored": (art.get("stored") or {}).get("path"),
        "duplicate": (art.get("stored") or {}).get("duplicate")}


# ─────────────────────── rotation: --plan (Chunk J2) ────────────────────────
#
# Murat, 2026-09-26: "it can also read WSJ and MarketWatch while it's waiting
# on delays". Parallel tabs loading at once are the bot signature, so the
# answer is ROTATION: one tab per source, each listing loaded once, then ONE
# article per source per turn under ONE shared throttle. Every source
# progresses, no host sees a burst, and the gap between any two page loads is
# still the jittered 20-90 s.

#: Fatal for the WHOLE run (every lane stops): the budget is gone.
_RUN_FATAL = ("REFUSED_THROTTLE_DAY", "REFUSED_THROTTLE_HOUR", "REFUSED_SESSION_CAP",
              "REFUSED_READER_BUSY")
#: Fatal for ONE lane: its tab is gone or wandered off the allowed hosts.
_LANE_FATAL = ("REFUSED_LEFT_HOSTS", "REFUSED_VERB_FAILED", "REFUSED_OPERATOR_TAB",
               "REFUSED_TABS_UNREADABLE", "REFUSED_PROFILE")

#: WSJ's dated archive. Barron's and MarketWatch: no dated archive page has
#: been SEEN on a live page by this code, so none is guessed (the rule is
#: "no URL the page did not show", except a listing the caller names).
ARCHIVE_URL = {"wsj": "https://www.wsj.com/news/archive/{y:04d}/{m:02d}/{d:02d}"}
ARCHIVE_PATTERN = SECTIONS["wsj"]["heard_on_the_street"][1]
ARCHIVE_NOT_BUILT_FOR = {
    "barrons": "no dated archive URL was seen on a live Barron's page; not guessed",
    "marketwatch": "no dated archive URL was seen on a live MarketWatch page; not guessed"}


def parse_plan(spec: str) -> list[dict]:
    """`"barrons:stock_picks:5,wsj:heard_on_the_street:5,marketwatch:analyst_estimates:MU|DKNG"`
    -> `[{lane, source, section, max, tickers}]` in the order given (the
    rotation order). A MarketWatch count instead of tickers takes the first N
    book names."""
    lanes, seen = [], set()
    for part in [p.strip() for p in (spec or "").split(",") if p.strip()]:
        bits = part.split(":")
        if len(bits) not in (2, 3):
            raise WR.ReaderRefused(f"REFUSED_PLAN: {part!r} is not source:section[:N|T1|T2]")
        src, sec = bits[0].strip().lower(), bits[1].strip().lower()
        arg = bits[2].strip() if len(bits) == 3 else ""
        if src not in SECTIONS or sec not in SECTIONS[src]:
            raise WR.ReaderRefused(f"REFUSED_PLAN_SECTION: {src}/{sec} is not a known section")
        lane = f"{src}:{sec}"
        if lane in seen:
            raise WR.ReaderRefused(f"REFUSED_PLAN_DUPLICATE: {lane} twice")
        seen.add(lane)
        tickers: list[str] = []
        n = 5
        if sec == "analyst_estimates":
            if arg and not arg.isdigit():
                tickers = [t.strip().upper() for t in arg.split("|") if t.strip()]
            else:
                tickers = default_mw_tickers(cap=int(arg) if arg else 10)
            n = len(tickers)
        elif arg:
            if not arg.isdigit():
                raise WR.ReaderRefused(f"REFUSED_PLAN_COUNT: {part!r}")
            n = int(arg)
        lanes.append({"lane": lane, "source": src, "section": sec, "max": n,
                      "tickers": tickers})
    if not lanes:
        raise WR.ReaderRefused("REFUSED_PLAN_EMPTY")
    return lanes


def parse_parent_tabs(spec: str) -> dict[str, str]:
    out = {}
    for part in [p.strip() for p in (spec or "").split(",") if p.strip()]:
        if "=" not in part:
            raise WR.ReaderRefused(f"REFUSED_PARENT_TABS: {part!r} is not source=tab")
        k, v = part.split("=", 1)
        out[k.strip().lower()] = v.strip()
    return out


def _tab_num(tid: str) -> int:
    digits = "".join(ch for ch in str(tid) if ch.isdigit())
    return int(digits) if digits else 10 ** 9


def resolve_parent_tabs(sources: list[str], tab_list: list[dict], *,
                        explicit: dict[str, str] | None = None,
                        exclude: set[str] | frozenset[str] = frozenset()) -> dict[str, dict]:
    """source -> `{tab, url, how}`. Tab ids change on every gateway restart,
    so they are RESOLVED from `tabs` each run, never hardcoded. An explicit
    `source=tab` must exist and sit on an allowed host. Otherwise: the
    OLDEST tab (lowest id -- Murat's own, not one a run opened) whose host is
    that source's site. A source with no tab on its host borrows the oldest
    tab on any allowed host (a `window.open` from a wsj.com tab inherits the
    same Chrome profile) and says so in `how`. No allowed tab at all refuses."""
    by_id = {str(t.get("tabId")): str(t.get("url") or "") for t in tab_list if t.get("tabId")}
    cands = sorted(((tid, u) for tid, u in by_id.items() if tid not in exclude
                    and WR.host_ok(u)), key=lambda x: _tab_num(x[0]))
    out: dict[str, dict] = {}
    for src in sources:
        want = (explicit or {}).get(src)
        if want:
            u = by_id.get(want)
            if u is None or not WR.host_ok(u):
                raise WR.ReaderRefused(f"REFUSED_PARENT_TAB: {src}={want} is "
                                       f"{'missing' if u is None else 'on ' + repr(u)}")
            out[src] = {"tab": want, "url": u, "how": "explicit"}
            continue
        host = f"{src}.com"
        own = [(tid, u) for tid, u in cands if WR.norm_url(u).split("/")[0].endswith(host)]
        if own:
            out[src] = {"tab": own[0][0], "url": own[0][1], "how": f"by_host:{host}"}
        elif cands:
            out[src] = {"tab": cands[0][0], "url": cands[0][1],
                        "how": f"borrowed:no {host} tab open"}
        else:
            raise WR.ReaderRefused(
                f"REFUSED_NO_PARENT_TAB: no tab on {WR.hosts()} is open in the "
                f"'user' profile to open {src} from (MuratClaw (Work) window)")
    return out


def round_robin(queues: dict[str, list]) -> list[tuple[str, Any]]:
    """The rotation order, as a pure function: one item per lane per turn in
    lane order; an exhausted lane drops out. `run_plan` walks the same order
    and can also drop a lane early (its tab failed)."""
    qs = {k: list(v) for k, v in queues.items()}
    out: list[tuple[str, Any]] = []
    while any(qs.values()):
        for k in list(qs):
            if qs[k]:
                out.append((k, qs[k].pop(0)))
    return out


def _stored_today(stored: dict[str, set[str]], url: str, day: str) -> bool:
    return day in stored.get(WR.norm_url(url), set())


def _merged_footprint(readers: list[WR.Reader], write: bool = True) -> dict:
    log = sorted((p for r in readers for p in r.log if p.get("at")), key=lambda p: p["at"])
    fp = WR.footprint_receipt(log, scrolled=sum(r.scrolled_reads for r in readers),
                              reads=sum(r.reads for r in readers), write=write)
    return {k: fp.get(k) for k in ("verdict", "cv_of_gaps", "gaps_s", "gap_min_s",
                                   "pages_per_hour", "scroll_share", "pages", "path")}


def _classify(msg: str) -> str:
    if any(m in msg for m in _RUN_FATAL):
        return "run"
    if "REFUSED_THROTTLE_HOST_DAY" in msg:
        return "host"
    if any(m in msg for m in _LANE_FATAL):
        return "lane"
    return "item"


def run_plan(lanes: list[dict], *, parents: dict[str, dict], profile: str = "user",
             driver: Any = None, throttle: Any = None, max_pages: int | None = None,
             progress_path: Path | None = None, stored: dict[str, set[str]] | None = None
             ) -> dict:
    """One rotating session: a tab per lane (opened from its source's parent),
    each listing loaded once, then one article per lane per turn."""
    if driver is None:
        from backend.services import openclaw_client as driver  # type: ignore[no-redef]
    thr = throttle or WR.Throttle(WR.throttle_path(), wait_on_hour_cap=True)
    day = _today()
    stored = WR.stored_urls() if stored is None else stored
    budget = max_pages if max_pages is not None else (
        sum(ln["max"] for ln in lanes) + len(lanes) + 2)
    rc: dict[str, Any] = {
        "receipt": "dowjones_pull.plan", "profile": profile, "tou": TOU_SENTENCE,
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan": [{k: ln[k] for k in ("lane", "max", "tickers")} for ln in lanes],
        "parent_tabs": parents, "max_pages": budget, "cost_usd": 0.0,
        "lanes": {}, "order": [], "stopped": None}
    lock = WR.acquire_reader_lock()
    readers: dict[str, WR.Reader] = {}
    queues: dict[str, list] = {}

    def total_pages() -> int:
        return sum(r.pages for r in readers.values())

    def save() -> None:
        if progress_path is not None:
            rc["in_progress"] = True
            _write(rc, progress_path.name)

    try:
        # 1. open ONE tab per lane from its source's parent; load its listing once
        for ln in lanes:
            lid, src, sec = ln["lane"], ln["source"], ln["section"]
            listing, pattern, column = SECTIONS[src][sec]
            st: dict[str, Any] = {"source": src, "section": sec, "column": column,
                                  "parent_tab": parents[src]["tab"], "tab": None,
                                  "links_found": 0, "skipped_already_stored": 0,
                                  "articles": [], "refusals": [], "dropped": None}
            rc["lanes"][lid] = st
            if total_pages() >= budget:
                st["dropped"] = "REFUSED_SESSION_CAP before the tab opened"
                continue
            if sec == "analyst_estimates":
                todo = [t for t in ln["tickers"]
                        if not _stored_today(stored, listing.format(ticker=t.lower()), day)]
                st["skipped_already_stored"] = len(ln["tickers"]) - len(todo)
                if not todo:
                    st["dropped"] = "EXHAUSTED: every ticker already stored today"
                    continue
                first_url = listing.format(ticker=todo[0].lower())
            else:
                first_url = listing
            try:
                thr.acquire("open_from_tab", host=f"{src}.com")
                opened = driver.open_from_tab(parents[src]["tab"], first_url,
                                              profile_name=profile)
            except Exception as exc:  # noqa: BLE001 -- the lane stops, said by name
                st["dropped"] = f"OPEN_FAILED: {type(exc).__name__}: {str(exc)[:200]}"
                if _classify(str(exc)) == "run":
                    rc["stopped"] = str(exc)[:200]
                    break
                continue
            tab = opened["new_tab"]
            st["tab"] = tab
            rd = WR.Reader(profile=profile, tab=tab, throttle=thr, driver=driver,
                           max_pages=10 ** 6, lock=False)
            rd.pages = 1
            rd.log.append({"page": 1, "what": "open_from_tab", "url": first_url,
                           "waited_s": thr.waits[-1] if thr.waits else 0.0,
                           "at": thr.now_fn().isoformat(timespec="seconds"), "lane": lid})
            readers[lid] = rd
            rc["order"].append({"turn": 0, "lane": lid, "what": "listing", "url": first_url,
                                "at": rd.log[-1]["at"], "ok": True})
            driver.browser("wait", "--time", "4000", profile_name=profile, target_id=tab)
            if sec == "analyst_estimates":
                queues[lid] = [("ticker", t) for t in todo]
            else:
                links = WR.select_links(rd.snapshot(), pattern)
                st["links_found"] = len(links)
                fresh = [lk for lk in links if not stored.get(WR.norm_url(lk["url"]))]
                st["skipped_already_stored"] = len(links) - len(fresh)
                queues[lid] = [("link", lk) for lk in fresh[:ln["max"]]]
                if not links:
                    st["refusals"].append({"why": "NO_LINKS_ON_LISTING: the snapshot showed "
                                                  "no link matching the article pattern"})
            save()

        # 2. the rotation: one item per lane per turn, lane order, one shared throttle
        active = [ln["lane"] for ln in lanes if ln["lane"] in readers and not rc["stopped"]]
        turn = 0
        first_mw_read = {lid: True for lid in active}
        while active and not rc["stopped"]:
            turn += 1
            for lid in list(active):
                st, rd, q = rc["lanes"][lid], readers[lid], queues.get(lid) or []
                if not q:
                    active.remove(lid)
                    st["dropped"] = st["dropped"] or "EXHAUSTED"
                    continue
                if total_pages() >= budget:
                    rc["stopped"] = f"REFUSED_SESSION_CAP: {total_pages()} pages >= {budget}"
                    break
                kind, item = q.pop(0)
                column = st["column"]
                n_before = rd.pages
                try:
                    if kind == "ticker":
                        url = SECTIONS["marketwatch"]["analyst_estimates"][0].format(
                            ticker=item.lower())
                        art = (_read_current(rd, url, column, item) if first_mw_read.get(lid)
                               else rd.read_article(url, column=column))
                        first_mw_read[lid] = False
                        art["ticker"] = item
                    else:
                        art = rd.read_article(item, column=column)
                    st["articles"].append(_summary(art))
                    loaded = rd.pages > n_before      # False: read in place (already loaded)
                    rc["order"].append({"turn": turn, "lane": lid,
                                        "url": art.get("url"), "ticker": art.get("ticker"),
                                        "at": (rd.log[-1]["at"] if loaded else
                                               thr.now_fn().isoformat(timespec="seconds")),
                                        "page_load": loaded,
                                        "waited_s": rd.log[-1]["waited_s"] if loaded else 0.0,
                                        "chars": art.get("chars"), "ok": True})
                except Exception as exc:  # noqa: BLE001 -- classified, never swallowed
                    first_mw_read[lid] = False
                    msg = f"{type(exc).__name__}: {exc}"[:300]
                    what = item if kind == "ticker" else item.get("url")
                    st["refusals"].append({"item": what, "why": msg})
                    rc["order"].append({"turn": turn, "lane": lid, "item": what,
                                        "at": thr.now_fn().isoformat(timespec="seconds"),
                                        "ok": False, "why": msg[:120]})
                    cls = _classify(msg)
                    if cls == "run":
                        rc["stopped"] = msg
                        break
                    if cls == "host":
                        host = st["source"]
                        for other in list(active):
                            if rc["lanes"][other]["source"] == host:
                                active.remove(other)
                                rc["lanes"][other]["dropped"] = msg
                    elif cls == "lane":
                        active.remove(lid)
                        st["dropped"] = msg
                save()
    finally:
        # 3. every tab this run opened is closed, whatever happened
        rc["tabs_closed"] = {}
        for lid, rd in readers.items():
            try:
                cl = driver.browser("close", profile_name=profile, target_id=rd.tab)
                rc["tabs_closed"][rd.tab] = cl.get("rc") == 0
            except Exception as exc:  # noqa: BLE001 -- say it, never hide it
                rc["tabs_closed"][rd.tab] = False
                rc["lanes"][lid]["close_error"] = str(exc)[:200]
        rc["footprint"] = _merged_footprint(list(readers.values()))
        WR.release_reader_lock(lock)
    rc["hour_cap_waits_s"] = list(getattr(thr, "hour_cap_waits", []))
    rc["throttle_targets_s"] = list(thr.targets)
    rc["per_source"] = {}
    for lid, st in rc["lanes"].items():
        ps = rc["per_source"].setdefault(st["source"], {"articles": 0, "refusals": 0,
                                                        "chars": 0})
        ps["articles"] += len(st["articles"])
        ps["refusals"] += len(st["refusals"])
        ps["chars"] += sum(a.get("chars") or 0 for a in st["articles"])
    rc["n_articles"] = sum(v["articles"] for v in rc["per_source"].values())
    rc["pages_loaded"] = total_pages()
    stamps = sorted(datetime.fromisoformat(pg["at"]) for r_ in readers.values()
                    for pg in r_.log if pg.get("at"))
    rc["seconds_between_page_loads"] = [round((b - a).total_seconds(), 1)
                                        for a, b in zip(stamps, stamps[1:])]
    rc["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rc["in_progress"] = False
    return rc


# ──────────────────────────── the archive (J2) ──────────────────────────────

def archive_days(spec: str, today: date | None = None) -> list[date]:
    """`YYYY-MM-DD` or `YYYY-MM-DD..YYYY-MM-DD` -> the NYSE trading days in
    the range, NEWEST first. Weekends and NYSE holidays are skipped; today and
    later refuse (a day that has not finished has no archive)."""
    from backend.services import digest_inbox as DI
    today = today or datetime.now(timezone.utc).date()
    a, _, b = (spec or "").partition("..")
    try:
        d0 = date.fromisoformat(a.strip())
        d1 = date.fromisoformat(b.strip()) if b else d0
    except ValueError as exc:
        raise WR.ReaderRefused(f"REFUSED_ARCHIVE_DATE: {spec!r} is not YYYY-MM-DD[..YYYY-MM-DD]"
                               ) from exc
    if d1 < d0:
        raise WR.ReaderRefused(f"REFUSED_ARCHIVE_RANGE: {d0} > {d1}")
    if d1 >= today:
        raise WR.ReaderRefused(f"REFUSED_ARCHIVE_FUTURE: {d1} has not finished yet")
    hol: set[date] = set()
    for y in range(d0.year, d1.year + 1):
        hol |= DI.nyse_holidays(y)
    out, d = [], d1
    while d >= d0:
        if d.weekday() < 5 and d not in hol:
            out.append(d)
        d -= timedelta(days=1)
    return out


def archive_url(source: str, d: date) -> str:
    return ARCHIVE_URL[source].format(y=d.year, m=d.month, d=d.day)


def run_archive(days: list[date], *, parent_tab: str, max_per_day: int | None = None,
                profile: str = "user", driver: Any = None, throttle: Any = None,
                max_pages: int | None = None, progress_path: Path | None = None,
                stored: dict[str, set[str]] | None = None) -> dict:
    """WSJ's dated archive, newest day first, in ONE tab opened from a WSJ
    parent: load the day page, choose article links FROM its snapshot, read up
    to `max_per_day` not already stored (resumable: a stored URL is never
    loaded again, and it counts toward that day's cap), then the next day."""
    if driver is None:
        from backend.services import openclaw_client as driver  # type: ignore[no-redef]
    thr = throttle or WR.Throttle(WR.throttle_path(), wait_on_hour_cap=True)
    cap = int(max_per_day if max_per_day is not None else _config.DOWJONES_ARCHIVE_MAX_PER_DAY)
    stored = WR.stored_urls() if stored is None else stored
    budget = max_pages if max_pages is not None else len(days) * (cap + 1) + 2
    rc: dict[str, Any] = {
        "receipt": "dowjones_pull.archive", "profile": profile, "tou": TOU_SENTENCE,
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": ["wsj"], "not_built": ARCHIVE_NOT_BUILT_FOR, "parent_tab": parent_tab,
        "days": [d.isoformat() for d in days], "max_per_day": cap, "max_pages": budget,
        "per_day": {}, "order": [], "stopped": None, "cost_usd": 0.0}
    if not days:
        rc["stopped"] = "NO_TRADING_DAYS_IN_RANGE"
        return rc
    lock = WR.acquire_reader_lock()
    rd: WR.Reader | None = None
    try:
        first = archive_url("wsj", days[0])
        thr.acquire("open_from_tab", host="wsj.com")
        opened = driver.open_from_tab(parent_tab, first, profile_name=profile)
        rd = WR.Reader(profile=profile, tab=opened["new_tab"], throttle=thr, driver=driver,
                       max_pages=budget, lock=False)
        rc["tab_opened"] = rd.tab
        rd.pages = 1
        rd.log.append({"page": 1, "what": "open_from_tab", "url": first,
                       "waited_s": thr.waits[-1] if thr.waits else 0.0,
                       "at": thr.now_fn().isoformat(timespec="seconds")})
        driver.browser("wait", "--time", "4000", profile_name=profile, target_id=rd.tab)
        for i, d in enumerate(days):
            url = archive_url("wsj", d)
            st: dict[str, Any] = {"url": url, "links_found": 0, "already_stored": 0,
                                  "read": 0, "refusals": []}
            rc["per_day"][d.isoformat()] = st
            try:
                if i > 0:
                    rd.navigate(url)
                rc["order"].append({"day": d.isoformat(), "what": "day_page", "url": url,
                                    "at": rd.log[-1]["at"], "ok": True})
                links = WR.select_links(rd.snapshot(), ARCHIVE_PATTERN)
            except WR.ReaderRefused as exc:
                st["refusals"].append({"why": str(exc)[:200]})
                if _classify(str(exc)) in ("run", "host", "lane"):
                    rc["stopped"] = str(exc)[:200]
                    break
                continue
            st["links_found"] = len(links)
            fresh = [lk for lk in links if not stored.get(WR.norm_url(lk["url"]))]
            st["already_stored"] = len(links) - len(fresh)
            room = max(0, cap - st["already_stored"])
            if not links:
                st["refusals"].append({"why": "NO_LINKS_ON_LISTING"})
            for lk in fresh[:room]:
                try:
                    art = rd.read_article(lk, column=None)
                    stored.setdefault(WR.norm_url(lk["url"]), set()).add(_today())
                    st["read"] += 1
                    rc["order"].append({"day": d.isoformat(), "url": art.get("url"),
                                        "at": rd.log[-1]["at"], "chars": art.get("chars"),
                                        "column": art.get("column"), "ok": True})
                except WR.ReaderRefused as exc:
                    msg = str(exc)[:200]
                    st["refusals"].append({"url": lk["url"], "why": msg})
                    if _classify(msg) in ("run", "host", "lane"):
                        rc["stopped"] = msg
                        break
            _write(rc | {"in_progress": True}, progress_path.name) if progress_path else None
            if rc["stopped"]:
                break
    except Exception as exc:  # noqa: BLE001 -- the receipt says why, the tab still closes
        rc["stopped"] = rc["stopped"] or f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        if rd is not None:
            try:
                cl = driver.browser("close", profile_name=profile, target_id=rd.tab)
                rc["tab_closed"] = cl.get("rc") == 0
            except Exception as exc:  # noqa: BLE001
                rc["tab_closed"] = False
                rc["close_error"] = str(exc)[:200]
            rc["footprint"] = _merged_footprint([rd])
        WR.release_reader_lock(lock)
    rc["n_articles"] = sum(v["read"] for v in rc["per_day"].values())
    rc["complete"] = (not rc["stopped"] and len(rc["per_day"]) == len(days))
    rc["hour_cap_waits_s"] = list(getattr(thr, "hour_cap_waits", []))
    rc["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rc["in_progress"] = False
    return rc


# ───────────────────────────── the queue (J2) ───────────────────────────────

def queue_lines(path: Path) -> list[tuple[int, str]]:
    out = []
    for i, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append((i, line))
    return out


def queue_done_dir(path: Path) -> Path:
    return Path(path).with_name(Path(path).stem + ".done")


def _line_key(lineno: int, line: str) -> str:
    import hashlib
    return f"line{lineno:03d}_{hashlib.sha256(line.encode('utf-8')).hexdigest()[:10]}"


def run_queue(path: Path, *, inherit: list[str] | None = None,
              main_fn: Any = None, only_first: bool = False) -> dict:
    """Each line is one `dowjones_pull` command (its arguments), run in order.
    A line that returns 0 gets a `.done` marker (keyed by line number AND a
    hash of its text, so an EDITED line runs again); a re-run skips done
    lines. A failed line is recorded and the queue continues, so one refused
    source does not cost the night. `inherit` (`--handoff`, `--profile X`) is
    appended to a line that does not set it."""
    main_fn = main_fn or main
    dd = queue_done_dir(path)
    rc: dict[str, Any] = {"receipt": "dowjones_pull.queue", "queue": str(path),
                          "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "lines": []}
    import shlex
    for lineno, line in queue_lines(path):
        key = _line_key(lineno, line)
        marker = dd / f"{key}.done"
        if marker.exists():
            rc["lines"].append({"line": lineno, "args": line, "status": "SKIPPED_DONE"})
            continue
        argv = shlex.split(line)
        for flag in (inherit or []):
            if flag.startswith("--") and flag not in argv:
                argv.append(flag)
        t0 = datetime.now(timezone.utc)
        try:
            code = int(main_fn(argv))
        except SystemExit as exc:
            code = int(exc.code or 0)
        except Exception as exc:  # noqa: BLE001 -- one line fails, the night goes on
            code = 2
            rc["lines"].append({"line": lineno, "args": line, "status": "ERROR",
                                "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            continue
        row = {"line": lineno, "args": line, "rc": code,
               "seconds": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
               "status": "DONE" if code == 0 else "FAILED_WILL_RETRY"}
        if code == 0:
            dd.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({"line": lineno, "args": line,
                                          "done_utc": datetime.now(timezone.utc).isoformat(
                                              timespec="seconds")}), encoding="utf-8")
        rc["lines"].append(row)
        if only_first:
            break
    rc["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return rc


def build_queue_text(today: date | None = None, *, names: dict[str, list[str]] | None = None,
                     cap: int = 40) -> str:
    """The night's queue: the rotating plan (Barron's picks 10, Big Money 3,
    HOTS 10, MarketWatch estimates for every book name, capped), the WSJ
    archive for the last four trading days, then the claims pass."""
    from backend.services import digest_inbox as DI
    today = today or datetime.now(timezone.utc).date()
    names = names if names is not None else DI.book_names()
    tick: list[str] = []
    for k in ("personal", "competition", "probe"):
        for t in names.get(k, []):
            if t and t not in tick:
                tick.append(t)
    n_all = len(tick)
    tick = tick[:cap]
    days = DI.trading_days_back(today, 2)[:4]
    rng = f"{min(days).isoformat()}..{max(days).isoformat()}" if days else ""
    lines = [
        f"# dowjones_pull queue -- generated {today.isoformat()} from the books "
        f"(personal, competition, PROBE; {n_all} distinct, first {len(tick)} kept)",
        "# run: python -m scripts.dowjones_pull --queue <this file> --handoff --profile user",
        "# one line = one command; a line that returns 0 gets a marker in "
        "<stem>.done/ and is skipped on re-run",
        f'--plan "barrons:stock_picks:10,wsj:heard_on_the_street:10,barrons:big_money_poll:3,'
        f'marketwatch:analyst_estimates:{"|".join(tick)}"',
    ]
    if rng:
        lines.append(f"--archive {rng}")
    lines.append(f"--claims --claims-since {today.isoformat()}")
    return "\n".join(lines) + "\n"


# ────────────────────────────────── claims ──────────────────────────────────

def _done_path() -> Path:
    return WR.corpus_root() / "_claims" / "_extracted.txt"


def stored_articles(day: str, root: Path | None = None) -> list[dict]:
    root = Path(root) if root else WR.corpus_root()
    out = []
    for p in sorted(root.glob(f"*/{day}/*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return out


def run_claims(day: str | None = None, *, cap_usd: float | None = None, llm_fn: Any = None,
               spend_fn: Any = None, ledger_path: Path | None = None,
               claims_path: Path | None = None, root: Path | None = None,
               done_path: Path | None = None, since: str | None = None,
               structured_dir: Path | None = None) -> dict:
    """Each stored article not yet extracted -> one DeepSeek call -> forecasts.

    Two columns are STRUCTURED, not claims (Chunk J2): a MarketWatch analyst
    estimates page becomes one `mw_analyst_snapshot` row (rating, mean/high/
    low target, n analysts, next earnings date) with NO LLM call; a Big Money
    poll also writes index-level SPX rows (`barrons_big_money_poll`) before its
    LLM pass for named stocks. `since` walks every day from `since` to today.

    The cap is read from the WRITER's ledger (`llm_telemetry.spend` with this
    purpose, since this run started) plus a per-call estimate for the call
    about to be made; an unreadable ledger REFUSES (spend unknown is not zero).
    """
    day = day or _today()
    cap = float(cap_usd if cap_usd is not None else _config.DOWJONES_CLAIMS_CAP_USD)
    est = float(_config.DOWJONES_CLAIMS_EST_USD_PER_ARTICLE)
    purpose = _config.DOWJONES_CLAIMS_PURPOSE
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    dp = Path(done_path) if done_path else _done_path()
    done = set(dp.read_text(encoding="utf-8").split()) if dp.exists() else set()

    def spent() -> float | None:
        if spend_fn is not None:
            return spend_fn()
        from backend.services import llm_telemetry as LT
        s = LT.spend(since=started, purpose=purpose)
        return None if not s else float(s.get("total_cost_usd") or 0.0)

    days = [day]
    if since:
        d0, d1 = date.fromisoformat(since), date.fromisoformat(_today())
        days = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    sd = Path(structured_dir) if structured_dir else None
    arts = [a for d in days for a in stored_articles(d, root)]
    per, n_calls, stop = [], 0, None
    structured: dict[str, Any] = {"mw_analyst_snapshot": [], "barrons_big_money_poll": []}
    for art in arts:
        if art.get("sha") in done:
            continue
        if art.get("column") == "mw_analyst_estimates" or DC.mw_ticker_of(
                str(art.get("url") or "")):
            snap = DC.write_mw_snapshot(art, path=(sd / "mw_analyst_snapshot.jsonl")
                                        if sd else None)
            structured["mw_analyst_snapshot"].append(snap)
            dp.parent.mkdir(parents=True, exist_ok=True)
            with dp.open("a", encoding="utf-8") as fh:
                fh.write(str(art.get("sha")) + "\n")
            continue
        if art.get("column") == "barrons_big_money_poll":
            structured["barrons_big_money_poll"].append(DC.write_big_money_rows(
                art, path=(sd / "barrons_big_money_poll.jsonl") if sd else None))
        sp = spent()
        if sp is None:
            stop = "REFUSED_SPEND_UNKNOWN: the telemetry ledger could not be read"
            break
        if sp + est > cap:
            stop = f"CAP: spent ${sp:.4f} + est ${est:.4f} > cap ${cap:.2f}"
            break
        ex = DC.extract_claims(art, llm_fn=llm_fn)
        n_calls += ex["status"] not in ("SKIPPED_TOO_SHORT",)
        w = (DC.write_forecasts(art, ex["claims"], ledger_path=ledger_path,
                                claims_path=claims_path)
             if ex["claims"] else {"n_rows_written": 0, "source_id": art.get("column")})
        per.append({"sha": art.get("sha"), "url": art.get("url"), "column": art.get("column"),
                    "status": ex["status"], "n_claims": len(ex["claims"]),
                    "refused": ex["refused"], "tickers": [c["ticker"] for c in ex["claims"]],
                    "directions": [c["direction"] for c in ex["claims"]],
                    "source_id": w.get("source_id"), "forecast_rows": w.get("n_rows_written", 0),
                    "write_status": w.get("status")})
        if ex["status"] != "LLM_NO_REPLY":
            dp.parent.mkdir(parents=True, exist_ok=True)
            with dp.open("a", encoding="utf-8") as fh:
                fh.write(str(art.get("sha")) + "\n")
    final = spent()
    by_src: dict[str, int] = {}
    for r in per:
        by_src[r["source_id"] or "?"] = by_src.get(r["source_id"] or "?", 0) + r["forecast_rows"]
    snaps = structured["mw_analyst_snapshot"]
    polls = structured["barrons_big_money_poll"]
    return {"receipt": "dowjones_pull.claims", "day": day, "days": days, "started_utc": started,
            "mw_analyst_snapshot": {
                "n_pages": len(snaps), "n_rows_written": sum(x["n_rows_written"] for x in snaps),
                "thin": [x["ticker"] for x in snaps if x["status"] != "OK"],
                "tickers": [x["ticker"] for x in snaps if x["status"] == "OK"]},
            "barrons_big_money_poll_index_rows": {
                "n_articles": len(polls), "n_rows_written": sum(x["n_rows_written"] for x in polls),
                "per_article": polls},
            "structured_rows_where": "gitignored news_corpus/dowjones/_structured/ (counts only here)",
            "purpose": purpose, "cap_usd": cap, "spent_usd": final, "n_llm_calls": n_calls,
            "stopped": stop, "n_articles": len(per),
            "n_claims": sum(r["n_claims"] for r in per),
            "forecast_rows_by_source_id": by_src,
            "public_safety": "claim_text in git is the model's paraphrase; verbatim quotes stay "
                             "in the gitignored news_corpus/dowjones/_claims/",
            "per_article": per}


# ─────────────────────────────────── main ───────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--feeds", action="store_true")
    ap.add_argument("--probe-free", action="store_true")
    ap.add_argument("--source", choices=sorted(SECTIONS))
    ap.add_argument("--section")
    ap.add_argument("--max", type=int, default=5)
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--tickers", default="")
    ap.add_argument("--parent-tab", default="")
    ap.add_argument("--profile", default="user")
    ap.add_argument("--handoff", action="store_true",
                    help="required for any browser read; refuses unless HANDOFF_PC exists")
    ap.add_argument("--archive", default="")
    ap.add_argument("--claims", action="store_true")
    ap.add_argument("--claims-day", default="")
    ap.add_argument("--claims-since", default="",
                    help="claims over every day from this date to today")
    ap.add_argument("--plan", default="",
                    help='rotating read: "src:section:N,...,marketwatch:analyst_estimates:T1|T2"')
    ap.add_argument("--parent-tabs", default="",
                    help='"barrons=t13,wsj=t20" (default: resolved from tabs by host)')
    ap.add_argument("--max-per-day", type=int, default=None)
    ap.add_argument("--queue", default="", help="a file of dowjones_pull lines, run in order")
    ap.add_argument("--queue-first-only", action="store_true")
    ap.add_argument("--write-queue", default="",
                    help="write the night's queue file (from the books) to this path")
    a = ap.parse_args(argv)
    out: dict[str, Any] = {}
    rc = 0
    day = _today()

    if a.feeds:
        r = DF.pull_feeds()
        p = _write(r, f"feeds_{day}.json")
        out["feeds"] = {"receipt": str(p), "items_received": r["items_received"],
                        "items_new": r["items_new"], "refused_or_red": r["refused_or_red"],
                        "per_feed": {f["source"]: f["received"] for f in r["per_feed"]}}
    if a.probe_free:
        r = DF.probe_free_surfaces()
        p = _write(r, f"free_surfaces_{day}.json")
        out["probe_free"] = {"receipt": str(p), "answer_200": r["answer_200"],
                             "walled_401_403": r["walled_401_403"], "other": r["other"]}
    if a.write_queue:
        qp = Path(a.write_queue)
        qp.parent.mkdir(parents=True, exist_ok=True)
        qp.write_text(build_queue_text(), encoding="utf-8")
        out["write_queue"] = str(qp)
    if a.queue:
        print(TOU_SENTENCE, flush=True)
        r = run_queue(Path(a.queue), inherit=["--handoff"] if a.handoff else [],
                      main_fn=lambda av: main(av + (["--profile", a.profile]
                                                    if "--profile" not in av else [])),
                      only_first=a.queue_first_only)
        p = _write(r, f"queue_{day}_{datetime.now(timezone.utc):%H%M%S}.json")
        out["queue"] = {"receipt": str(p), "lines": [
            {k: ln.get(k) for k in ("line", "status", "rc", "seconds")} for ln in r["lines"]]}
        rc = 0 if all(ln["status"] in ("DONE", "SKIPPED_DONE") for ln in r["lines"]) else 2
    if a.archive:
        print(TOU_SENTENCE, flush=True)
        try:
            days = archive_days(a.archive)
        except WR.ReaderRefused as exc:
            print(str(exc))
            return 2
        if not getattr(_config, "DOWJONES_ARCHIVE_ENABLED", False):
            print("REFUSED_ARCHIVE_OFF: config.DOWJONES_ARCHIVE_ENABLED is False (Murat, "
                  "2026-09-26). The archive days are links in digest_inbox/"
                  "WEEKEND_READING_LIST.md for a human to read instead.")
            return 2
        if not a.handoff or not handoff_ok():
            print(f"REFUSED_NO_HANDOFF: the archive reads need --handoff AND "
                  f"{_config.DOWJONES_HANDOFF_FILE}.")
            return 2
        print("ARCHIVE: WSJ only -- " + "; ".join(f"{k}: {v}" for k, v in
                                                  ARCHIVE_NOT_BUILT_FOR.items()), flush=True)
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        rpath = DF.receipts_dir() / f"archive_{day}_{stamp}.json"
        try:
            from backend.services import openclaw_client as OCm
            parents = resolve_parent_tabs(
                ["wsj"], OCm.tabs(profile_name=a.profile),
                explicit=({"wsj": a.parent_tab} if a.parent_tab else
                          parse_parent_tabs(a.parent_tabs)),
                exclude=set(getattr(OCm, "_OPENED_TABS", set())))
            print(f"parent tab: wsj -> {parents['wsj']['tab']} ({parents['wsj']['how']}, "
                  f"{parents['wsj']['url'][:80]})", flush=True)
            r = run_archive(days, parent_tab=parents["wsj"]["tab"], max_per_day=a.max_per_day,
                            profile=a.profile, progress_path=rpath)
            r["parent_tabs"] = parents
        except Exception as exc:  # noqa: BLE001 -- a refusal is a finding, rc 2
            print(f"REFUSED: {type(exc).__name__}: {exc}")
            _write({"receipt": "dowjones_pull.archive", "n_articles": 0, "days": a.archive,
                    "refused": f"{type(exc).__name__}: {exc}"[:400]}, rpath.name)
            return 2
        p = _write(r, rpath.name)
        out["archive"] = {"receipt": str(p), "n_articles": r["n_articles"],
                          "per_day": {k: {x: v[x] for x in ("links_found", "already_stored",
                                                            "read")}
                                      for k, v in r["per_day"].items()},
                          "stopped": r["stopped"], "tab_closed": r.get("tab_closed"),
                          "footprint": (r.get("footprint") or {}).get("verdict")}
        rc = 0 if r["complete"] else 2
    if a.plan:
        print(TOU_SENTENCE, flush=True)
        if not a.handoff or not handoff_ok():
            print(f"REFUSED_NO_HANDOFF: browser reads need --handoff AND "
                  f"{_config.DOWJONES_HANDOFF_FILE}.")
            return 2
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        rpath = DF.receipts_dir() / f"plan_{day}_{stamp}.json"
        try:
            lanes = parse_plan(a.plan)
            from backend.services import openclaw_client as OCm
            srcs = list(dict.fromkeys(ln["source"] for ln in lanes))
            explicit = parse_parent_tabs(a.parent_tabs)
            if a.parent_tab and len(srcs) == 1:
                explicit.setdefault(srcs[0], a.parent_tab)
            parents = resolve_parent_tabs(srcs, OCm.tabs(profile_name=a.profile),
                                          explicit=explicit,
                                          exclude=set(getattr(OCm, "_OPENED_TABS", set())))
            for s_, v in parents.items():
                print(f"parent tab: {s_} -> {v['tab']} ({v['how']}, {v['url'][:80]})",
                      flush=True)
            r = run_plan(lanes, parents=parents, profile=a.profile,
                         max_pages=a.max_pages if a.max_pages != 20 else None,
                         progress_path=rpath)
        except Exception as exc:  # noqa: BLE001 -- a refusal is a finding, rc 2
            print(f"REFUSED: {type(exc).__name__}: {exc}")
            _write({"receipt": "dowjones_pull.plan", "plan": a.plan, "n_articles": 0,
                    "refused": f"{type(exc).__name__}: {exc}"[:400],
                    "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                   rpath.name)
            return 2
        p = _write(r, rpath.name)
        out["plan"] = {"receipt": str(p), "per_source": r["per_source"],
                       "lanes": {k: {"tab": v["tab"], "articles": len(v["articles"]),
                                     "refusals": len(v["refusals"]),
                                     "skipped_already_stored": v["skipped_already_stored"],
                                     "dropped": v["dropped"]} for k, v in r["lanes"].items()},
                       "tabs_closed": r["tabs_closed"], "stopped": r["stopped"],
                       "footprint": r["footprint"].get("verdict"),
                       "hour_cap_waits_s": r["hour_cap_waits_s"]}
        rc = 0 if not r["stopped"] and all(
            v["dropped"] in (None, "EXHAUSTED") or str(v["dropped"]).startswith("EXHAUSTED")
            for v in r["lanes"].values()) else 2
    if a.source:
        print(TOU_SENTENCE, flush=True)
        if not a.handoff or not handoff_ok():
            print(f"REFUSED_NO_HANDOFF: browser reads need --handoff AND "
                  f"{_config.DOWJONES_HANDOFF_FILE} (created by Murat when he hands the "
                  f"PC over). Use scripts/digest_ingest.py for pasted articles.")
            return 2
        if not a.parent_tab or not a.section:
            print("REFUSED: --parent-tab (a MuratClaw wsj/barrons/marketwatch tab) and "
                  "--section are required")
            return 2
        tickers = [t.strip().upper() for t in a.tickers.split(",") if t.strip()] or None
        if a.section == "analyst_estimates" and not tickers:
            tickers = default_mw_tickers()
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        rpath = DF.receipts_dir() / f"reads_{day}_{a.source}_{a.section}_{stamp}.json"
        try:
            r = run_reads(a.source, a.section, parent_tab=a.parent_tab,
                          max_articles=a.max, tickers=tickers, max_pages=a.max_pages,
                          profile=a.profile, progress_path=rpath)
        except Exception as exc:  # noqa: BLE001 -- a refusal is a finding, with rc 2
            print(f"REFUSED: {type(exc).__name__}: {exc}")
            _write({"receipt": "dowjones_pull.reads", "source": a.source, "section": a.section,
                    "parent_tab": a.parent_tab, "n_articles": 0,
                    "refused": f"{type(exc).__name__}: {exc}"[:400],
                    "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                   rpath.name)
            return 2
        r["in_progress"] = False
        p = _write(r, rpath.name)
        out["reads"] = {"receipt": str(p), "n_articles": r["n_articles"],
                        "chars_total": r["chars_total"], "tab": r.get("tab_opened"),
                        "tab_closed": r.get("tab_closed"),
                        "seconds_between_page_loads": r["seconds_between_page_loads"],
                        "refusals": r["refusals"]}
        rc = 0 if r["n_articles"] else 2
    if a.claims:
        r = run_claims(a.claims_day or None, since=a.claims_since or None)
        p = _write(r, f"claims_{a.claims_day or day}_{datetime.now(timezone.utc):%H%M%S}.json")
        out["claims"] = {"receipt": str(p), "n_articles": r["n_articles"],
                         "n_claims": r["n_claims"], "spent_usd": r["spent_usd"],
                         "rows": r["forecast_rows_by_source_id"], "stopped": r["stopped"]}
    if not out and rc == 0:
        ap.print_help()
        return 2
    print(json.dumps(out, indent=1, default=str))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
