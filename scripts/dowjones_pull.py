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
        --handoff --profile muratclaw
        # one command per line, sequential; a line that returns 0 is marked done

TAB DISCIPLINE, COMPANY SEARCH, THE v3 SHORTLIST QUEUE (2026-09-27):
    python -m scripts.dowjones_pull --handoff --plan "wsj_search:MU|NVDA,barrons_search:MU|NVDA" \
        --max-pages 60 --fresh-since 2026-09-27
        # each name's quote page (wsj.com/market-data/quotes/<T>, barrons.com/
        # market-data/stocks/<t>), <= 3 article links chosen FROM its snapshot
        # (<= 30 days old when dated), read in rotation; --max-pages is the
        # line's budget (reaching it is DONE, not a refusal); a name searched
        # on/after --fresh-since is skipped on a rerun (_search_seen.jsonl)
    python -m scripts.dowjones_pull --write-shortlist-queue \
        backend/data/optimus/dowjones/QUEUE_2026-09-27.txt --shortlist-date 2026-09-27
    Every lane tab is blanked (about:blank) after each read, closed and
    re-opened from its parent after 10 page loads, and closed on every exit
    path; `orphaned_tabs` on the receipt lists any it could not close, and the
    next run's start-up cleanup closes the ones still on a Dow Jones host.

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
from backend.services import disk_guard as DG  # noqa: E402
from backend.services import openclaw_client as OCH  # noqa: E402  -- pure tab-id helpers only
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
        # the company's quote page (seen live: wsj.com/market-data/quotes/MU/research-ratings
        # is linked from a stored page); its news list is chosen FROM the snapshot.
        # Column "" = inferred per article (dowjones_claims.column_of).
        # 2026-09-28 live (PLTR): the WSJ stock page's news list links the Dow
        # Jones SISTER sites -- Barron's articles and MarketWatch stories -- and no
        # wsj.com article at all, so a wsj.com-only pattern read 0 links on every
        # page. Sister-site article links (both on the allowlist) are taken too.
        "search": (
            "https://www.wsj.com/market-data/quotes/{TICKER}",
            r"^https://www\.wsj\.com/(?!news/|market-data|video|podcasts|livecoverage|buyside)"
            r"[a-z-]+/[a-z0-9/-]*-[0-9a-f]{8}(\?|$)"
            r"|^https://www\.barrons\.com/articles/[a-z0-9-]+-[0-9a-f]{8}(\?|$)"
            r"|^https://www\.marketwatch\.com/story/[a-z0-9-]+-[0-9a-f]{8}(\?|$)",
            ""),
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
        "search": (
            "https://www.barrons.com/market-data/stocks/{ticker}",
            r"^https://www\.barrons\.com/articles/[a-z0-9-]+-[0-9a-f]{8}(\?|$)",
            ""),
    },
    "marketwatch": {
        "analyst_estimates": (
            "https://www.marketwatch.com/investing/stock/{ticker}/analystestimates",
            "", "mw_analyst_estimates"),
    },
}
DEFAULT_MW_TICKERS = ("MU", "DKNG", "QUBT")
#: Sections whose items are TICKERS (one page per name), not listing links.
TICKER_SECTIONS = ("analyst_estimates", "search")
#: A search lane reads up to this many article links per name, none older
#: than this many days when the page shows a date.
SEARCH_LINKS_PER_NAME = 3
SEARCH_MAX_AGE_DAYS = 30


def site_ticker(ticker: str) -> str:
    """The ticker as the Dow Jones sites spell it in a URL: a share class takes a
    DOT (`BRK-B` / `BRK/B` in the bars panel -> `BRK.B`: marketwatch.com/
    investing/stock/brk.b, wsj.com/market-data/quotes/BRK.B), and no spaces."""
    return (ticker or "").strip().replace("-", ".").replace("/", ".").replace(" ", "")


def lane_url(source: str, section: str, ticker: str = "MU") -> str:
    """The page a lane loads for one name (`{ticker}` lower, `{TICKER}` upper)."""
    t = site_ticker(ticker)
    return SECTIONS[source][section][0].format(ticker=t.lower(), TICKER=t.upper())


# ─────────────── a ticker whose page is NOT_FOUND is not retried ──────────────

def not_found_path() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "dowjones" / "not_found_tickers.json"


def not_found_tickers(source: str, path: Path | None = None) -> set[str]:
    """Tickers whose `source` page came back NOT_FOUND once (never retried)."""
    try:
        d = json.loads((path or not_found_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {t.upper() for t in (d.get(source) or {})}


def record_not_found(source: str, ticker: str, url: str, path: Path | None = None) -> None:
    p = path or not_found_path()
    with DG.file_lock(p.with_name(p.name + ".lock")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        d.setdefault(source, {}).setdefault(str(ticker).upper(), {
            "first_seen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "url": url})
        DG.atomic_write_json(p, d)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _write(rc: dict, name: str) -> Path:
    p = DF.receipts_dir() / name
    # atomic (2026-09-27): a full disk leaves the OLD receipt, never a zero-byte one
    DG.atomic_write_json(p, rc)
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
              profile: str = "muratclaw", driver: Any = None, throttle: Any = None,
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
    first_url = lane_url(source, section, (tickers or ["MU"])[0])
    reader_lock = WR.acquire_reader_lock()
    try:
        rc["startup_cleanup"] = startup_cleanup(driver, profile)
        opened = WR.open_lane_tab(driver, profile, first_url, parent=parent_tab or None,
                                  throttle=thr, host=source + ".com")
    except Exception:
        WR.release_reader_lock(reader_lock)
        raise
    tab = opened["new_tab"]
    rc["tab_opened"] = tab
    rc["attached_to"] = opened.get("attached_to")
    reader = WR.Reader(profile=profile, tab=tab, throttle=thr, driver=driver,
                       max_pages=max_pages, lock=False, direct_open=bool(opened.get("direct")))
    reader._lock_path = reader_lock
    reader.pages, reader.tab_pages, reader.parent = 1, 1, (parent_tab or None)
    reader.log.append({"page": 1, "what": _open_what(opened), "url": first_url,
                       "waited_s": thr.waits[-1] if thr.waits else 0.0,
                       "at": thr.now_fn().isoformat(timespec="seconds")})
    try:
        driver.browser("wait", "--time", "4000", profile_name=profile, target_id=tab)
        if section == "analyst_estimates":
            for i, t in enumerate(tickers or list(DEFAULT_MW_TICKERS)):
                url = lane_url(source, section, t)
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
        rc["tab_closed"] = reader.close_tab()
        if reader.close_errors:
            rc["close_error"] = "; ".join(f"{k}: {v}" for k, v in reader.close_errors.items())[:300]
        _tab_accounting(rc, [reader])
        fp = reader.close()
        rc["footprint"] = _footprint_fields(fp or {}, rc)
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
    DG.atomic_write_json(path, rc)


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
    text = WR.clean_text(got.get("text") or "", got.get("title"))
    cls = WR.classify_page(url=url, final_url=final, title=got.get("title"),
                           raw=got.get("text") or "", text=text)
    reader.count_page(final, cls)
    if cls == "REDIRECTED_OFF_HOST":
        raise WR.ReaderRefused(f"REFUSED_LEFT_HOSTS: {final!r}")
    if cls != "OK":
        reader.last_snapshot = ""
        reader.blank()
        if cls == "CHALLENGE":
            raise WR.ReaderRefused(f"REFUSED_CHALLENGE: {final!r} shows a bot check or "
                                   f"block page; this lane stops")
        raise WR.ReaderRefused(f"PAGE_{cls}: {final!r} ({len(text)} chars) not stored")
    art = {"url": final, "title": got.get("title"), "byline": None,
           "published_utc": None, "text": text, "first_seen_utc": DC.now_iso(),
           "chars": len(text), "raw_chars": len(got.get("text") or ""),
           "publisher": "marketwatch", "origin": "web_reader", "tab": reader.tab,
           "profile": reader.profile, "column": column, "tickers": [ticker],
           "paywall_suspected": False, "read_s": 0.0}
    art["sha"] = DC.text_sha(text)
    if text:
        art["stored"] = WR.store_article(art)
    reader.last_snapshot = ""
    reader.blank()
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
              "REFUSED_READER_BUSY", "REFUSED_GATEWAY_DOWN", "REFUSED_REATTACH")
#: Fatal for ONE lane: its tab is gone or wandered off the allowed hosts.
_LANE_FATAL = ("REFUSED_LEFT_HOSTS", "REFUSED_VERB_FAILED", "REFUSED_OPERATOR_TAB",
               "REFUSED_TABS_UNREADABLE", "REFUSED_PROFILE", "REFUSED_CHALLENGE")

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
        head, _, rest = part.partition(":")
        if head.lower().endswith("_search"):          # `wsj_search:MU|NVDA` sugar
            part = f"{head[:-len('_search')]}:search:{rest}"
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
        elif sec == "search":
            tickers = [t.strip().upper() for t in arg.split("|") if t.strip()]
            if not tickers or any(not t.replace(".", "").replace("-", "").isalnum()
                                  for t in tickers):
                raise WR.ReaderRefused(f"REFUSED_PLAN_TICKERS: {part!r} needs T1|T2|...")
            n = len(tickers) * (1 + SEARCH_LINKS_PER_NAME)   # a page + up to N articles
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
    return OCH.label_num(tid)


#: THE MARKER (2026-09-27). The `user` attach reaches EVERY profile of the running
#: Chrome and the tab list does not name a tab's profile; "by host" twice put
#: pages in Murat's main account. When this is set (main() sets it for operator
#: profiles), the ONLY admissible parent is a tab whose URL carries the marker --
#: a tab Murat opened by hand in the MuratClaw window. Everything the reader
#: opens comes from `window.open` inside it, so it inherits that profile.
#: No marker tab -> REFUSED_NO_MARKER_TAB; an explicit parent without it refuses too.
#:
#: SUPERSEDED FOR THE DEDICATED PROFILE (LANE O, 2026-09-28). With OpenClaw
#: attached ONLY to the dedicated Chrome (`config.OPENCLAW_DEDICATED_USER_DATA_DIR`,
#: 127.0.0.1:18802), every tab it lists IS a MuratClaw tab, so the marker is no
#: longer what identifies the profile. The guard is not deleted, it is
#: REPLACED by `instance_gate()`: before any tab is resolved, the attached
#: browser is PROVEN to be the dedicated one (`muratclaw_instance.prove`) and
#: the run refuses otherwise. The marker still binds on any operator profile
#: that is NOT dedicated (none today).
PARENT_MARKER: str | None = None
MARKER_DEFAULT = "aegis=muratclaw"


def instance_gate(profile: str, oc: Any = None) -> dict | None:
    """LANE O: prove the browser behind `profile` is the dedicated MuratClaw
    Chrome BEFORE any tab is resolved or opened. Returns the proof (None for a
    profile that is not dedicated); raises `ReaderRefused` with the prover's
    code (REFUSED_NOT_MURATCLAW_INSTANCE, REFUSED_INSTANCE_DOWN, ...)."""
    if oc is None:
        from backend.services import openclaw_client as oc  # type: ignore[no-redef]
    ded = getattr(oc, "dedicated_profiles", None)
    if not callable(ded) or profile not in ded():
        return None
    try:
        return oc._instance_check(profile)
    except Exception as exc:  # noqa: BLE001 -- the client's refusal, renamed
        if type(exc).__name__ == "OpenClawRefused":
            raise WR.ReaderRefused(str(exc)) from exc
        raise


def _has_marker(url: str) -> bool:
    return PARENT_MARKER is None or PARENT_MARKER in (url or "")


DIRECT_HOW = "direct_open: dedicated instance, no parent tab used"
#: the fault a run that could not open ANY lane's tab ends with; the night
#: supervisor (`gateway_repair.classify_exit`) backs off on it
READER_CANNOT_OPEN_TABS = "READER_CANNOT_OPEN_TABS"


def _open_what(opened: dict) -> str:
    return "open_tab" if opened.get("direct") else "open_from_tab"


def resolve_parent_tabs(sources: list[str], tab_list: list[dict], *,
                        explicit: dict[str, str] | None = None,
                        exclude: set[str] | frozenset[str] = frozenset(),
                        direct: bool = False) -> dict[str, dict]:
    """source -> `{tab, url, how}`. Tab ids change on every gateway restart,
    so they are RESOLVED from `tabs` each run, never hardcoded. An explicit
    `source=tab` must exist and sit on an allowed host. Otherwise: the
    OLDEST tab (lowest id -- Murat's own, not one a run opened) whose host is
    that source's site. A source with no tab on its host borrows the oldest
    tab on any allowed host (a `window.open` from a wsj.com tab inherits the
    same Chrome profile) and says so in `how`. No allowed tab at all refuses.

    `direct=True` (2026-09-28, the DEDICATED instance, proven by
    `instance_gate`): no parent tab is needed or used -- lanes open with
    `open_tab` -- so every source maps to `{tab: None, how: DIRECT_HOW}`,
    no tab of the owner's is chosen, and nothing refuses because no Dow Jones
    tab is open. The marker rule does not apply."""
    if direct:
        return {src: {"tab": None, "label": None, "url": "", "how": DIRECT_HOW}
                for src in sources}
    # the handle is the STABLE id (raw targetId when the listing has one); the
    # `tN` label only orders oldest-first and is printed (Chunk J3)
    rows = [(OCH.tab_handle(t), OCH.tab_label(t), str(t.get("url") or ""), t)
            for t in tab_list if OCH.tab_handle(t)]
    if PARENT_MARKER is not None:
        rows = [r for r in rows if _has_marker(r[2])]
        if not rows:
            raise WR.ReaderRefused(
                f"REFUSED_NO_MARKER_TAB: no open tab carries {PARENT_MARKER!r}. Open "
                f"https://www.wsj.com/?{PARENT_MARKER} in the MuratClaw window and leave it open.")
    cands = sorted(((h, lab, u) for h, lab, u, t in rows
                    if not any(OCH.tab_matches(t, x) for x in exclude) and WR.host_ok(u)),
                   key=lambda x: _tab_num(x[1]))
    out: dict[str, dict] = {}
    for src in sources:
        want = (explicit or {}).get(src)
        if want:
            hit = next(((h, lab, u) for h, lab, u, t in rows if OCH.tab_matches(t, want)), None)
            if hit is None or not WR.host_ok(hit[2]):
                raise WR.ReaderRefused(f"REFUSED_PARENT_TAB: {src}={want} is "
                                       f"{'missing' if hit is None else 'on ' + repr(hit[2])}")
            out[src] = {"tab": hit[0], "label": hit[1], "url": hit[2], "how": "explicit"}
            continue
        host = f"{src}.com"
        own = [c for c in cands if WR.norm_url(c[2]).split("/")[0].endswith(host)]
        if own:
            out[src] = {"tab": own[0][0], "label": own[0][1], "url": own[0][2],
                        "how": f"by_host:{host}"}
        elif cands:
            out[src] = {"tab": cands[0][0], "label": cands[0][1], "url": cands[0][2],
                        "how": f"borrowed:no {host} tab open"}
        else:
            raise WR.ReaderRefused(
                f"REFUSED_NO_PARENT_TAB: no tab on {WR.hosts()} is open in the "
                f"dedicated MuratClaw Chrome to open {src} from")
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


def interleave_order(queues: dict[str, list],
                     needs_load: Any = None) -> list[tuple[str, str, Any]]:
    """The INTERLEAVED rotation (2026-09-27), as a pure function: `run_plan`
    applies exactly these rules online. Ops are `("load", lane, item)` (a
    throttle slot + the navigate/click) and `("finish", lane, item)` (settle
    remainder, scroll, read, store, blank -- no page load).

    1. turns in lane order, one item per lane per turn (`round_robin`);
    2. a lane's item is LOADED at its turn and FINISHED right after the NEXT
       load, so its settle is spent on another lane's page load;
    3. a lane never has two items outstanding -- it has one tab -- so its own
       unread item is finished before its next load;
    4. an item that needs no load (`needs_load(lane, item)` False: the tab
       was opened AT it) finishes at its turn, after the outstanding one;
    5. whatever is outstanding at the end finishes, oldest first.
    Loads therefore happen in `round_robin` order, one at a time."""
    need = needs_load or (lambda lane, item: True)
    qs = {k: list(v) for k, v in queues.items()}
    active = list(qs)
    ops: list[tuple[str, str, Any]] = []
    pend: dict[str, Any] = {}
    prev: str | None = None
    while active:
        for k in list(active):
            if k in pend:
                ops.append(("finish", k, pend.pop(k)))
            if not qs[k]:
                active.remove(k)
                continue
            item = qs[k].pop(0)
            p = prev
            if not need(k, item):
                prev = None
                if p is not None and p in pend:
                    ops.append(("finish", p, pend.pop(p)))
                ops.append(("finish", k, item))
                continue
            ops.append(("load", k, item))
            pend[k] = item
            prev = k
            if p is not None and p != k and p in pend:
                ops.append(("finish", p, pend.pop(p)))
    for k in list(pend):
        ops.append(("finish", k, pend.pop(k)))
    return ops


def _stored_today(stored: dict[str, set[str]], url: str, day: str) -> bool:
    return day in stored.get(WR.norm_url(url), set())


def _stored_since(stored: dict[str, set[str]], url: str, since: str) -> bool:
    """Stored on or after `since` (ISO day): the resume rule for a line that
    may run across a UTC midnight (`--fresh-since`)."""
    return any(d and d >= since for d in stored.get(WR.norm_url(url), set()))


# ───────────────────── search memory + start-up cleanup ─────────────────────

def search_seen_path() -> Path:
    return WR.corpus_root() / "_search_seen.jsonl"


def searched_since(source: str, since: str, path: Path | None = None) -> set[str]:
    """Tickers whose `source` search page this reader loaded on/after `since`
    (a quote page is not an article, so `stored_urls` cannot resume it)."""
    p = Path(path) if path else search_seen_path()
    out: set[str] = set()
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("source") == source and str(r.get("day") or "") >= since:
            out.add(str(r.get("ticker") or "").upper())
    return out


def _record_search(source: str, ticker: str, row: dict, path: Path | None = None) -> None:
    p = Path(path) if path else search_seen_path()
    # locked append (2026-09-27): reader WORKER processes share this file
    DG.locked_append_line(p, json.dumps(
        {"source": source, "ticker": ticker.upper(), "day": _today(),
         "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **row}))


#: Receipts whose tabs a later run may clean up, and how far back it looks.
CLEANUP_RECEIPT_PREFIXES = ("plan_", "archive_", "reads_")
CLEANUP_LOOKBACK_DAYS = 3


def previous_opened_handles(rdir: Path | None = None, *,
                            lookback_days: int = CLEANUP_LOOKBACK_DAYS,
                            worker: str | None = None, me: int | None = None,
                            alive: Any = None) -> list[str]:
    """Every tab handle an earlier run's receipt records as OPENED and not
    closed: the `opened` list (2026-09-27 on), and for older receipts
    `tab_opened`, each lane's `tab`, `orphaned_tabs`, `tabs_lost_on_reattach`
    -- minus any the same receipt says it closed. Receipts are dated by the
    stamp in their NAME, never by mtime (protocol 7).

    OWNERSHIP (2026-09-27, reader workers). Until today the one-reader lock
    made "an earlier receipt" mean "a dead run". With worker processes a LIVE
    run's in-progress receipt lists its open lane tabs, and a second run
    starting would have adopted and closed them (`close_leftover_tabs` adopts
    any session-qualified handle on a Dow Jones host). So a receipt counts only
    when (1) its `worker` equals `worker` (a crashed worker's tabs are closed
    by the next start of THAT worker id; a receipt with no `worker` -- a
    single-session run -- only by a single-session run or the worker
    launcher), and (2) its `pid`, when it carries one, is not a live process
    other than `me`."""
    import os
    me = int(me if me is not None else os.getpid())
    alive = alive or WR._pid_alive
    d = Path(rdir) if rdir else DF.receipts_dir()
    since = (datetime.now(timezone.utc).date() - timedelta(days=lookback_days)).isoformat()
    out: set[str] = set()
    for p in sorted(d.glob("*.json")) if d.exists() else []:
        if not p.name.startswith(CLEANUP_RECEIPT_PREFIXES):
            continue
        day = p.name.split("_", 2)[1] if p.name.count("_") >= 2 else ""
        if day < since:
            continue
        try:
            rc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(rc, dict):
            continue
        if (rc.get("worker") or None) != (worker or None):
            continue
        rpid = int(rc.get("pid") or 0)
        if rpid and rpid != me and alive(rpid):
            continue                     # a LIVE run's tabs are its own
        hs: set[str] = set(str(h) for h in (rc.get("opened") or []) if h)
        if rc.get("tab_opened"):
            hs.add(str(rc["tab_opened"]))
        for st in (rc.get("lanes") or {}).values():
            if isinstance(st, dict) and st.get("tab"):
                hs.add(str(st["tab"]))
        for k in ("orphaned_tabs", "tabs_lost_on_reattach"):
            hs |= {str(h) for h in (rc.get(k) or []) if h}
        closed = rc.get("tabs_closed") or {}
        if isinstance(closed, dict):
            hs -= {h for h, ok in closed.items() if ok}
        if rc.get("tab_closed") is True and rc.get("tab_opened"):
            hs.discard(str(rc["tab_opened"]))
        out |= hs
    return sorted(out)


def startup_cleanup(driver: Any, profile: str, handles: list[str] | None = None, *,
                    worker: str | None = None) -> dict:
    """Run AFTER this run's reader lock is held: close what earlier DEAD runs
    of the same worker id left open (`previous_opened_handles` -- a live run's
    receipt is never read as leftovers; `web_reader.close_leftover_tabs` --
    session-qualified handles still on a Dow Jones host only). Never raises;
    the result goes on the receipt."""
    try:
        hs = previous_opened_handles(worker=worker) if handles is None else list(handles)
        res = WR.close_leftover_tabs(driver, profile, hs)
    except Exception as exc:  # noqa: BLE001 -- a cleanup never costs the run
        res = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    if res.get("closed"):
        print(f"start-up cleanup: closed {len(res['closed'])} tab(s) an earlier run left: "
              f"{res['closed']}", flush=True)
    return res


def _tab_accounting(rc: dict, readers: Any) -> None:
    """`opened` (every handle this run held), `tabs_closed` (handle -> closed
    ok), `orphaned_tabs` (opened and not closed), blank/rotation counts."""
    readers = list(readers)
    opened: list[str] = []
    for r in readers:
        for h in r.opened:
            if h not in opened:
                opened.append(h)
    closed: dict[str, bool] = {}
    errs: dict[str, str] = {}
    for r in readers:
        closed.update(r.closed)
        errs.update(r.close_errors)
    rc["opened"] = opened
    rc["tabs_closed"] = {h: bool(closed.get(h)) for h in opened}
    rc["orphaned_tabs"] = [h for h in opened if not closed.get(h)]
    if errs:
        rc["close_errors"] = errs
    rc["blanks"] = sum(r.blanks for r in readers)
    # 2026-09-28: on the dedicated instance a read tab is CLOSED, not blanked
    rc["closes_after_read"] = sum(getattr(r, "closes_after_read", 0) for r in readers)
    rc["blank_slot_refunds"] = [x for r in readers for x in getattr(r, "slot_refunds", [])]
    pc: dict[str, dict[str, int]] = {}
    for r in readers:
        for host, row in (getattr(r, "page_classes", None) or {}).items():
            tgt = pc.setdefault(host, {})
            for k, v in row.items():
                tgt[k] = tgt.get(k, 0) + v
    rc["page_classes"] = pc
    rc["blank_failures"] = [x for r in readers for x in r.blank_failures]
    rc["tab_rotations"] = [x for r in readers for x in r.rotations]


#: What the RUN receipt copies from a footprint. The cli_* fields (2026-09-27)
#: show what the profile-assert cache (3d721f05) and the tabs-listing cache
#: (2131b2ba) saved; before this list carried them they lived only in the
#: footprint file, so a morning read of the run receipt could not see them.
FOOTPRINT_RECEIPT_KEYS = ("verdict", "cv_of_gaps", "gaps_s", "gap_min_s", "pages_per_hour",
                          "scroll_share", "pages", "path", "cli_scope", "cli_calls",
                          "cli_seconds", "cli_seconds_per_page", "cli_calls_per_page",
                          "cli_breakdown", "cli_cache", "cli_by_verb")


def _footprint_fields(fp: dict, rc: dict | None = None) -> dict:
    """The run receipt's `footprint` block: FOOTPRINT_RECEIPT_KEYS from the
    footprint (None when absent -- missing is visible, never 0), plus the run's
    recovery counts: `reattaches` (int) and `tab_remaps` (how many remap events;
    the events themselves stay in the receipt's top-level `tab_remaps`)."""
    out = {k: fp.get(k) for k in FOOTPRINT_RECEIPT_KEYS}
    rc = rc or {}
    out["reattaches"] = int(rc.get("reattaches") or 0)
    out["tab_remaps"] = len(rc.get("tab_remaps") or [])
    return out


def _merged_footprint(readers: list[WR.Reader], write: bool = True,
                      rc: dict | None = None) -> dict:
    log = sorted((p for r in readers for p in r.log if p.get("at")), key=lambda p: p["at"])
    fp = WR.footprint_receipt(log, scrolled=sum(r.scrolled_reads for r in readers),
                              reads=sum(r.reads for r in readers), write=write)
    return _footprint_fields(fp, rc)


def _classify(msg: str) -> str:
    if any(m in msg for m in _RUN_FATAL):
        return "run"
    if "REFUSED_THROTTLE_HOST_DAY" in msg:
        return "host"
    if any(m in msg for m in _LANE_FATAL):
        return "lane"
    return "item"


class _Recovery:
    """Re-attach after `user` drops to `stopped` mid-run (2026-09-26: the
    Chrome MCP subprocess dies between sections while Chrome stays up).

    `recover()` runs `WR.ensure_attached` (start, wait <= 20 s for running +
    tabs, refuse after two failed attempts, never touch a dead gateway), then
    -- because tab ids CHANGE after a re-attach -- remaps every tab this run
    holds by the URL it last loaded (the newest matching tab), re-resolves the
    parents by host, and reopens a lane whose tab cannot be found from its
    re-resolved parent at the URL it was on. BLANKED lanes (on `about:blank`)
    are remapped only when the new listing holds EXACTLY as many blank tabs as
    this run has blanked lanes (then every blank tab is one of ours, paired in
    tab order); otherwise a blank tab cannot be told from one of Murat's, so
    the lane is marked `needs_reopen` and re-opened from its parent at its
    next page load (no page is loaded twice; the lost blank handle stays in
    `orphaned_tabs`). Everything goes in the receipt: `reattaches`,
    `reattach_log`, `tab_remaps`, `tabs_lost_on_reattach`."""

    MAX_PER_RUN = 6

    def __init__(self, driver: Any, profile: str, rc: dict, thr: Any) -> None:
        self.driver, self.profile, self.rc, self.thr, self.n = driver, profile, rc, thr, 0
        rc.setdefault("reattaches", 0)
        rc.setdefault("reattach_log", [])
        rc.setdefault("tab_remaps", [])
        rc.setdefault("tabs_lost_on_reattach", [])

    def recover(self, readers: dict[str, WR.Reader], parents: dict[str, dict],
                source_of: dict[str, str]) -> dict:
        if self.n >= self.MAX_PER_RUN:
            raise WR.ReaderRefused(f"REFUSED_REATTACH_BUDGET: {self.n} recoveries this run")
        self.n += 1
        res = WR.ensure_attached(self.profile, oc=self.driver, log=self.rc["reattach_log"])
        self.rc["reattaches"] += bool(res.get("reattached"))
        tabs = self.driver.tabs(profile_name=self.profile)
        opened = getattr(self.driver, "_OPENED_TABS", None)
        taken: set[str] = set()
        remap: dict[str, str | None] = {}
        lost: list[str] = []
        blanked = sorted(((k, r) for k, r in readers.items() if r.blanked
                          and not r.needs_reopen and not r.closed.get(r.tab)),
                         key=lambda kr: _tab_num(kr[1].tab))
        blank_tabs = sorted((t for t in tabs if str(t.get("url") or "") == WR.BLANK_URL),
                            key=lambda t: _tab_num(OCH.tab_label(t)))
        if blanked and len(blank_tabs) == len(blanked):
            for (key, rd), t in zip(blanked, blank_tabs):
                old, new = rd.tab, OCH.tab_handle(t)
                taken.add(new)
                if opened is not None:
                    opened.discard(old)
                    opened.add(new)
                rd.tab, remap[old] = new, new
                rd.opened = [new if h == old else h for h in rd.opened]
        for key, rd in readers.items():
            if rd.needs_reopen or rd.closed.get(rd.tab) or rd.tab in taken:
                continue
            old = rd.tab
            if rd.blanked:
                # an about:blank tab cannot be told from Murat's own blank tabs
                remap[old] = None
                rd.needs_reopen = True
                rd.closed.setdefault(old, False)
                rd.close_errors.setdefault(old, "LOST: blank tab, handle reissued by a re-attach")
                self.rc["tabs_lost_on_reattach"].append(old)
                continue
            last = next((pg["url"] for pg in reversed(rd.log) if pg.get("url")), "") or ""
            want = WR.norm_url(last)
            cands = sorted((t for t in tabs if OCH.tab_handle(t) not in taken
                            and WR.norm_url(str(t.get("url") or "")) == want),
                           key=lambda t: -_tab_num(OCH.tab_label(t)))
            if cands:
                new = OCH.tab_handle(cands[0])
                taken.add(new)
                if opened is not None:
                    opened.discard(old)
                    opened.add(new)
                rd.tab, remap[old] = new, new
                rd.opened = [new if h == old else h for h in rd.opened]
                if old in rd.closed:
                    rd.closed[new] = rd.closed.pop(old)
            else:
                remap[old] = None
                lost.append(key)
        fresh = resolve_parent_tabs(sorted(set(parents)), tabs, exclude=taken,
                                    direct=WR.direct_open_ok(self.driver, self.profile))
        parents.update(fresh)
        for key, rd in readers.items():
            src = source_of.get(key)
            if src in parents and rd.parent is not None:
                rd.parent = parents[src]["tab"]
        for key in lost:
            rd = readers[key]
            old = rd.tab
            self.rc["tabs_lost_on_reattach"].append(old)
            rd.closed.setdefault(old, False)
            rd.close_errors.setdefault(old, "LOST: handle reissued by a re-attach")
            last = next((pg["url"] for pg in reversed(rd.log) if pg.get("url")), "") or ""
            src = source_of[key]
            op = WR.open_lane_tab(self.driver, self.profile, last, parent=parents[src]["tab"],
                                  throttle=self.thr, host=f"{src}.com")
            rd.tab = op["new_tab"]
            rd.opened.append(rd.tab)
            rd.last_snapshot, rd.blanked, rd.tab_pages = "", False, 1
            rd.pages += 1
            rd.log.append({"page": rd.pages, "what": "reopen_after_reattach", "url": last,
                           "waited_s": self.thr.waits[-1] if self.thr.waits else 0.0,
                           "at": self.thr.now_fn().isoformat(timespec="seconds")})
            remap[f"{key}:reopened"] = rd.tab
        self.rc["tab_remaps"].append({
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reattached": bool(res.get("reattached")), "remap": remap,
            "parents": {k: v["tab"] for k, v in parents.items()}})
        return remap


def _close_all(driver: Any, profile: str, readers: dict[str, WR.Reader], rc: dict,
               recovery: _Recovery | None, parents: dict[str, dict],
               source_of: dict[str, str]) -> None:
    """Close every tab this run opened (a blanked one through
    `own_blank_tab_verb`); a close refused because the profile detached gets
    ONE recovery (re-attach + remap) and a second try. Then the accounting:
    `opened`, `tabs_closed`, `orphaned_tabs`."""
    for attempt in (1, 2):
        detached = False
        for key, rd in readers.items():
            if rd.closed.get(rd.tab):
                continue
            if not rd.close_tab() and WR.is_detached(rd.close_errors.get(rd.tab, "")):
                detached = True
                rd.closed.pop(rd.tab, None)          # retried after the re-attach
        if not detached or recovery is None or attempt == 2:
            break
        try:
            recovery.recover(readers, parents, source_of)
        except Exception as exc:  # noqa: BLE001
            rc["close_recovery_error"] = str(exc)[:200]
            break
    _tab_accounting(rc, readers.values())


def run_plan(lanes: list[dict], *, parents: dict[str, dict], profile: str = "muratclaw",
             driver: Any = None, throttle: Any = None, max_pages: int | None = None,
             progress_path: Path | None = None, stored: dict[str, set[str]] | None = None,
             fresh_since: str | None = None, cleanup_handles: list[str] | None = None,
             searched: dict[str, set[str]] | None = None,
             worker: str | None = None) -> dict:
    """One rotating session: a tab per lane (opened from its source's parent),
    each listing loaded once, then one item per lane per turn.

    Ticker lanes (`analyst_estimates`, `search`) skip a name already done on or
    after `fresh_since` (default today): a MarketWatch page stored, a search
    page recorded in `_search_seen.jsonl`. A search item loads the company's
    quote page, chooses up to SEARCH_LINKS_PER_NAME article links FROM its
    snapshot (`WR.select_search_links`: <= SEARCH_MAX_AGE_DAYS old when a date
    shows) and puts them at the head of that lane's queue. An EXPLICIT
    `max_pages` is the line's budget: reaching it ends the run as
    `budget_spent`, not as a refusal.

    `worker` (2026-09-27): this run is ONE of several reader processes (one
    per site). It holds `_reader_<worker>.lock` instead of the single-session
    lock, its receipt carries `worker` and `pid`, and its start-up cleanup
    closes only tabs a DEAD run of the same worker id left open. The throttle
    file is shared and file-locked, so every process's page loads draw from
    ONE budget of slots."""
    import os
    if driver is None:
        from backend.services import openclaw_client as driver  # type: ignore[no-redef]
    thr = throttle or WR.Throttle(WR.throttle_path(), wait_on_hour_cap=True)
    pfx = f"[{worker}] " if worker else ""
    day = _today()
    since = fresh_since or day
    stored = WR.stored_urls() if stored is None else stored
    explicit_budget = max_pages is not None
    budget = max_pages if max_pages is not None else (
        sum(ln["max"] for ln in lanes) + len(lanes) + 2)
    rc: dict[str, Any] = {
        "receipt": "dowjones_pull.plan", "profile": profile, "tou": TOU_SENTENCE,
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan": [{k: ln[k] for k in ("lane", "max", "tickers")} for ln in lanes],
        "parent_tabs": parents, "max_pages": budget, "budget_explicit": explicit_budget,
        "fresh_since": since, "cost_usd": 0.0, "lanes": {}, "order": [], "stopped": None,
        "budget_spent": None, "opened": [], "orphaned_tabs": [],
        "worker": worker, "pid": os.getpid()}
    lock = WR.acquire_reader_lock(worker=worker) if worker else WR.acquire_reader_lock()
    readers: dict[str, WR.Reader] = {}
    queues: dict[str, list] = {}
    parents = {k: dict(v) for k, v in parents.items()}
    source_of = {ln["lane"]: ln["source"] for ln in lanes}
    recovery = _Recovery(driver, profile, rc, thr)
    queued_urls: set[str] = set()
    open_failures: list[str] = []
    # LANE O5: after the first N pages and at the end, links/page and chars/page
    # per lane are printed and recorded; a lane at zero on EVERY page refuses.
    ychk = WR.YieldCheck()
    rc["yield"] = ychk.reports

    def total_pages() -> int:
        return sum(r.pages for r in readers.values())

    def save() -> None:
        if progress_path is not None:
            rc["in_progress"] = True
            _tab_accounting(rc, readers.values())
            _write(rc, progress_path.name)

    def out_of_budget() -> bool:
        if total_pages() < budget:
            return False
        if explicit_budget:
            rc["budget_spent"] = f"BUDGET_SPENT: {total_pages()} pages >= --max-pages {budget}"
        else:
            rc["stopped"] = f"REFUSED_SESSION_CAP: {total_pages()} pages >= {budget}"
        return True

    try:
        rc["startup_cleanup"] = startup_cleanup(driver, profile, cleanup_handles,
                                                worker=worker)
        gone = set(rc["startup_cleanup"].get("closed") or [])
        hit = sorted(k for k, v in parents.items() if v.get("tab") in gone)
        if hit:        # a leftover had been chosen as a parent: re-resolve without it
            parents.update(resolve_parent_tabs(hit, driver.tabs(profile_name=profile),
                                               exclude=gone,
                                               direct=WR.direct_open_ok(driver, profile)))
            rc["parents_reresolved_after_cleanup"] = {k: parents[k]["tab"] for k in hit}
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
                st["dropped"] = ("BUDGET_SPENT before the tab opened" if explicit_budget else
                                 "REFUSED_SESSION_CAP before the tab opened")
                continue
            if sec in TICKER_SECTIONS:
                nf = not_found_tickers(src)
                st["skipped_not_found"] = sorted(t for t in ln["tickers"] if t.upper() in nf)
            if sec == "analyst_estimates":
                todo = [t for t in ln["tickers"] if t.upper() not in nf
                        and not _stored_since(stored, lane_url(src, sec, t), since)]
            elif sec == "search":
                done = (searched or {}).get(src) if searched is not None else \
                    searched_since(src, since)
                todo = [t for t in ln["tickers"] if t.upper() not in (done or set())
                        and t.upper() not in nf]
                st["searches"] = {}
            if sec in TICKER_SECTIONS:
                st["skipped_already_stored"] = len(ln["tickers"]) - len(todo)
                if not todo:
                    st["dropped"] = f"EXHAUSTED: every ticker already done since {since}"
                    continue
                first_url = lane_url(src, sec, todo[0])
            else:
                first_url = listing
            opened, err = None, None
            for attempt in (1, 2):
                try:
                    opened = WR.open_lane_tab(driver, profile, first_url,
                                              parent=parents[src]["tab"], throttle=thr,
                                              host=f"{src}.com")
                    break
                except Exception as exc:  # noqa: BLE001 -- detached -> re-attach once
                    err = f"{type(exc).__name__}: {str(exc)[:200]}"
                    if attempt == 1 and WR.is_detached(str(exc)):
                        try:
                            recovery.recover(readers, parents, source_of)
                            st["parent_tab"] = parents[src]["tab"]
                            continue
                        except Exception as exc2:  # noqa: BLE001
                            err = f"{type(exc2).__name__}: {str(exc2)[:200]}"
                    break
            if opened is None:
                st["dropped"] = f"OPEN_FAILED: {err}"
                open_failures.append(f"{lid}: {err}")
                if _classify(err or "") == "run" or WR.is_gateway_down(err or ""):
                    rc["stopped"] = (err or "")[:200]
                    break
                continue
            tab = opened["new_tab"]
            st["tab"] = tab
            rd = WR.Reader(profile=profile, tab=tab, throttle=thr, driver=driver,
                           max_pages=10 ** 6, lock=False, parent=parents[src]["tab"],
                           direct_open=bool(opened.get("direct")), lane=lid, worker=worker,
                           page_log=True)
            rd.pages, rd.tab_pages = 1, 1
            rd.log.append({"page": 1, "what": _open_what(opened), "url": first_url,
                           "waited_s": thr.waits[-1] if thr.waits else 0.0,
                           "at": thr.now_fn().isoformat(timespec="seconds"), "lane": lid})
            readers[lid] = rd
            st["opened"] = {k: opened.get(k) for k in ("label", "how", "tabs_before",
                                                       "tabs_after")}
            print(f"{pfx}opened {lid}: {opened.get('label') or tab} = {tab} "
                  f"({opened.get('how') or '?'}) {first_url[:80]}", flush=True)
            rc["order"].append({"turn": 0, "lane": lid, "what": "listing", "url": first_url,
                                "at": rd.log[-1]["at"], "ok": True})

            def first_look() -> str | None:
                driver.browser("wait", "--time", "4000", profile_name=profile,
                               target_id=rd.tab)
                return None if sec in TICKER_SECTIONS else rd.snapshot()
            try:
                listing_snap = first_look()
            except Exception as exc:  # noqa: BLE001 -- detached -> ONE rebind, then retry
                if not WR.is_detached(str(exc)):
                    raise
                recovery.recover(readers, parents, source_of)
                st["tab"] = rd.tab
                listing_snap = first_look()
            if sec == "analyst_estimates":
                queues[lid] = [("ticker", t) for t in todo]
            elif sec == "search":
                queues[lid] = [("search", t) for t in todo]
            else:
                links = WR.select_links(listing_snap or "", pattern)
                st["links_found"] = len(links)
                fresh = [lk for lk in links if not stored.get(WR.norm_url(lk["url"]))]
                st["skipped_already_stored"] = len(links) - len(fresh)
                queues[lid] = [("link", lk) for lk in fresh[:ln["max"]]]
                queued_urls |= {WR.norm_url(lk["url"]) for lk in fresh[:ln["max"]]}
                if not links:
                    st["refusals"].append({"why": "NO_LINKS_ON_LISTING: the snapshot showed "
                                                  "no link matching the article pattern"})
                rd.blank()                       # read done: closed (dedicated) or blanked
            save()

        # EVERY lane that tried to open failed and none opened: a named fault, so the
        # supervisor backs off instead of relaunching a reader that cannot open a tab
        # (2026-09-28: a blocked window.open, 0 tabs on every lane, relaunched every 5 min)
        if open_failures and not readers and not rc["stopped"]:
            rc["stopped"] = (f"{READER_CANNOT_OPEN_TABS}: {len(open_failures)} of "
                             f"{len(open_failures)} lane(s) failed to open a tab; first: "
                             f"{open_failures[0]}")[:400]
        # 2. the rotation: one item per lane per turn, lane order, one shared
        #    throttle -- INTERLEAVED (2026-09-27, `interleave_order`): a lane's
        #    page is LOADED at its turn and READ right after the NEXT lane's
        #    load, so the settle of one page is spent loading another. Every
        #    load still takes a throttle slot (global gap + same-host floor);
        #    a lane never has two pages outstanding (it has one tab).
        active = [ln["lane"] for ln in lanes if ln["lane"] in readers and not rc["stopped"]]
        turn = 0
        in_place = {lid: rc["lanes"][lid]["section"] in TICKER_SECTIONS for lid in active}
        pend: dict[str, dict] = {}
        prev: list[str | None] = [None]

        def drop_pending(lid: str, why: str) -> None:
            job = pend.pop(lid, None)
            if job is not None:
                it = job["item"]
                rc["lanes"][lid]["refusals"].append(
                    {"item": it if isinstance(it, str) else it.get("url"),
                     "why": f"NOT_READ: loaded, then {why}"[:300]})

        def handle(lid: str, kind: str, item: Any, exc: BaseException) -> str | None:
            """The one exception rule for a load or a read (classified, never
            swallowed). Returns "break" when the whole run stops."""
            st, q = rc["lanes"][lid], queues.get(lid) or []
            msg = f"{type(exc).__name__}: {exc}"[:300]
            what = item if isinstance(item, str) else item.get("url")
            if WR.is_detached(msg):
                # the profile dropped: re-attach, remap, and retry this item
                rc["order"].append({"turn": turn, "lane": lid, "item": what,
                                    "at": thr.now_fn().isoformat(timespec="seconds"),
                                    "ok": False, "why": "DETACHED: " + msg[:100]})
                try:
                    recovery.recover(readers, parents, source_of)
                    q.insert(0, (kind, item))
                    queues[lid] = q
                    save()
                    return None
                except Exception as exc2:  # noqa: BLE001
                    msg = f"{type(exc2).__name__}: {exc2}"[:300]
            in_place[lid] = False
            if "PAGE_NOT_FOUND" in msg and kind in ("ticker", "search") and isinstance(item, str):
                record_not_found(st["source"], item, str(what or ""))
            st["refusals"].append({"item": what, "why": msg})
            rc["order"].append({"turn": turn, "lane": lid, "item": what,
                                "at": thr.now_fn().isoformat(timespec="seconds"),
                                "ok": False, "why": msg[:120]})
            cls = "run" if WR.is_gateway_down(msg) else _classify(msg)
            if cls == "run":
                rc["stopped"] = msg
                return "break"
            if cls == "host":
                host = st["source"]
                for other in list(active):
                    if rc["lanes"][other]["source"] == host:
                        active.remove(other)
                        rc["lanes"][other]["dropped"] = msg
                        drop_pending(other, "its host was dropped")
            elif cls == "lane":
                if lid in active:
                    active.remove(lid)
                st["dropped"] = msg
                drop_pending(lid, "its lane was dropped")
            return None

        def load(lid: str, kind: str, item: Any) -> str | None:
            """The PAGE LOAD half of an item (throttle slot + navigate/click)."""
            rd = readers[lid]
            try:
                if kind == "search":
                    url = lane_url(rc["lanes"][lid]["source"], "search", item)
                    rd.navigate(url)
                elif kind == "ticker":
                    url = lane_url("marketwatch", "analyst_estimates", item)
                    rd.load_article(url)
                else:
                    url = item["url"]
                    rd.load_article(item)
            except Exception as exc:  # noqa: BLE001 -- classified in `handle`
                code = handle(lid, kind, item, exc)
                save()
                return code
            in_place[lid] = False
            pend[lid] = {"kind": kind, "item": item, "url": url, "loaded": True,
                         "turn": turn, "at": rd.log[-1]["at"],
                         "waited_s": rd.log[-1]["waited_s"], "t0": time.time()}
            return None

        def finish(lid: str) -> str | None:
            """The READ half of the item `lid` has outstanding. No page load."""
            job = pend.pop(lid, None)
            if job is None:
                return None
            st, rd, q = rc["lanes"][lid], readers[lid], queues.get(lid) or []
            kind, item, column = job["kind"], job["item"], st["column"]
            try:
                if kind == "search":
                    src = st["source"]
                    snap = (rd.snapshot_after_scroll() if hasattr(rd, "snapshot_after_scroll")
                            else rd.snapshot())
                    pcls = WR.classify_page(url=job["url"], final_url=job["url"],
                                            title=WR.snapshot_title(snap), raw=snap[:1500],
                                            text=snap)
                    rd.count_page(job["url"], pcls)
                    if pcls == "CHALLENGE":
                        rd.blank()
                        raise WR.ReaderRefused(f"REFUSED_CHALLENGE: {job['url']!r} shows a bot "
                                               f"check or block page; this lane stops")
                    if pcls in ("NOT_FOUND", "BLANK"):
                        rd.blank()
                        raise WR.ReaderRefused(f"PAGE_{pcls}: {job['url']!r} (search page)")
                    sel = WR.select_search_links(snap, SECTIONS[src]["search"][1],
                                                 now=thr.now_fn(),
                                                 max_age_days=SEARCH_MAX_AGE_DAYS,
                                                 limit=SEARCH_LINKS_PER_NAME)
                    rd.blank()
                    take = [lk for lk in sel["links"]
                            if not stored.get(WR.norm_url(lk["url"]))
                            and WR.norm_url(lk["url"]) not in queued_urls]
                    queued_urls.update(WR.norm_url(lk["url"]) for lk in take)
                    q[0:0] = [("link", dict(lk, ticker=item)) for lk in take]
                    queues[lid] = q
                    info = {"links_on_page": sel["candidates"], "taken": len(take),
                            "skipped_old": len(sel["skipped_old"]),
                            "skipped_ad": len(sel["skipped_ad"]),
                            "already_stored": len(sel["links"]) - len(take)}
                    st["searches"][item] = info
                    st["links_found"] += len(sel["links"])
                    ychk.record(lid, links=sel["candidates"], kind="search")
                    _record_search(src, item, info)
                    if searched is not None:
                        searched.setdefault(src, set()).add(item.upper())
                    rc["order"].append({"turn": job["turn"], "lane": lid, "what": "search",
                                        "ticker": item, "url": job["url"],
                                        "at": job["at"], "ok": True, **info})
                    save()
                    return None
                if kind == "ticker":
                    art = (rd.finish_article(job["url"], column=column, t0=job["t0"])
                           if job["loaded"] else _read_current(rd, job["url"], column, item))
                    art["ticker"] = item
                else:
                    tick = [item["ticker"]] if item.get("ticker") else None
                    art = rd.finish_article(item, column=column or None, tickers=tick,
                                            t0=job["t0"])
                    if item.get("ticker"):
                        art["ticker"] = item["ticker"]
                stored.setdefault(WR.norm_url(art.get("url") or ""), set()).add(day)
                st["articles"].append(_summary(art))
                ychk.record(lid, chars=art.get("chars"), kind="article")
                loaded = job["loaded"]
                rc["order"].append({"turn": job["turn"], "lane": lid,
                                    "url": art.get("url"), "ticker": art.get("ticker"),
                                    "at": (job["at"] if loaded else
                                           thr.now_fn().isoformat(timespec="seconds")),
                                    "page_load": loaded,
                                    "waited_s": job["waited_s"] if loaded else 0.0,
                                    "chars": art.get("chars"), "ok": True})
            except Exception as exc:  # noqa: BLE001 -- classified in `handle`
                code = handle(lid, kind, item, exc)
                save()
                return code
            save()
            return None

        def in_place_job(lid: str, kind: str, item: Any) -> None:
            """An item whose page is already loaded (the tab opened AT it)."""
            rd = readers[lid]
            url = (lane_url(rc["lanes"][lid]["source"], "search", item) if kind == "search"
                   else lane_url("marketwatch", "analyst_estimates", item))
            in_place[lid] = False
            pend[lid] = {"kind": kind, "item": item, "url": url, "loaded": False,
                         "turn": turn, "at": rd.log[-1]["at"], "waited_s": 0.0,
                         "t0": time.time()}

        while active and not rc["stopped"] and not rc["budget_spent"]:
            turn += 1
            for lid in list(active):
                if rc["stopped"] or lid not in active:
                    continue
                st, q = rc["lanes"][lid], queues.get(lid) or []
                if lid in pend and finish(lid) == "break":
                    break
                if lid not in active:
                    continue
                if not q:
                    active.remove(lid)
                    st["dropped"] = st["dropped"] or "EXHAUSTED"
                    continue
                if out_of_budget():
                    break
                kind, item = q.pop(0)
                if kind == "link" and stored.get(WR.norm_url(item["url"])):
                    st["skipped_already_stored"] += 1
                    continue
                p = prev[0]
                if kind in ("search", "ticker") and in_place.get(lid):
                    prev[0] = None
                    if p and p in pend and finish(p) == "break":
                        break
                    in_place_job(lid, kind, item)
                    if finish(lid) == "break":
                        break
                    continue
                code = load(lid, kind, item)
                prev[0] = lid if lid in pend else None
                if p and p != lid and p in pend and finish(p) == "break":
                    break
                if code == "break":
                    break
        # whatever is still loaded and unread is read now (no page load);
        # not after the gateway went down -- every verb would time out
        if not (rc["stopped"] and WR.is_gateway_down(str(rc["stopped"]))):
            for lid in list(pend):
                finish(lid)
        for lid in list(pend):
            drop_pending(lid, f"the run stopped ({str(rc['stopped'])[:120]})")
        if rc["budget_spent"]:
            for lid in active:
                if queues.get(lid):
                    rc["lanes"][lid]["dropped"] = rc["lanes"][lid]["dropped"] or rc["budget_spent"]
    except BaseException as exc:
        rc["stopped"] = rc["stopped"] or f"{type(exc).__name__}: {str(exc)[:200]}"
        raise
    finally:
        # 3. every tab this run opened is closed, whatever happened
        for lid, rd in readers.items():
            rc["lanes"][lid]["tab"] = rd.tab           # the id after any re-attach / rotation
        _close_all(driver, profile, readers, rc, recovery, parents, source_of)
        rc["parent_tabs_final"] = {k: v["tab"] for k, v in parents.items()}
        rc["footprint"] = _merged_footprint(list(readers.values()), rc=rc)
        WR.release_reader_lock(lock)
        if progress_path is not None:            # a crashed run still leaves its tab accounting
            _write(rc, progress_path.name)
    rc["hour_cap_waits_s"] = list(getattr(thr, "hour_cap_waits", []))
    rc["same_host_waits"] = list(getattr(thr, "same_host_waits", []))
    rc["throttle_targets_s"] = list(thr.targets)
    if ychk.rows:
        try:
            ychk.check("end")
        except WR.ReaderRefused as exc:
            rc["yield_refused"] = str(exc)
            rc["stopped"] = rc["stopped"] or str(exc)[:200]
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
                profile: str = "muratclaw", driver: Any = None, throttle: Any = None,
                max_pages: int | None = None, progress_path: Path | None = None,
                stored: dict[str, set[str]] | None = None,
                cleanup_handles: list[str] | None = None) -> dict:
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
    readers: dict[str, WR.Reader] = {}
    parents = {"wsj": {"tab": parent_tab, "url": "", "how": "given"}}
    recovery = _Recovery(driver, profile, rc, thr)

    def guarded(fn: Any) -> Any:
        """Run one step; a DETACHED failure gets one re-attach and one retry."""
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if not WR.is_detached(str(exc)) or not readers:
                raise
            recovery.recover(readers, parents, {"wsj": "wsj"})
            return fn()

    try:
        rc["startup_cleanup"] = startup_cleanup(driver, profile, cleanup_handles)
        if parent_tab in set(rc["startup_cleanup"].get("closed") or []):
            parent_tab = resolve_parent_tabs(["wsj"], driver.tabs(profile_name=profile),
                                             exclude=set(rc["startup_cleanup"]["closed"]),
                                             direct=WR.direct_open_ok(driver, profile)
                                             )["wsj"]["tab"]
            parents["wsj"]["tab"] = rc["parent_tab"] = parent_tab
        first = archive_url("wsj", days[0])
        opened = WR.open_lane_tab(driver, profile, first, parent=parent_tab, throttle=thr,
                                  host="wsj.com")
        rd = WR.Reader(profile=profile, tab=opened["new_tab"], throttle=thr, driver=driver,
                       max_pages=budget, lock=False, parent=parent_tab,
                       direct_open=bool(opened.get("direct")))
        rd.tab_pages = 1
        readers["wsj"] = rd
        rc["tab_opened"] = rd.tab
        rc["opened_detail"] = {k: opened.get(k) for k in ("label", "how", "tabs_before",
                                                          "tabs_after")}
        print(f"opened wsj archive: {opened.get('label') or rd.tab} = {rd.tab} "
              f"({opened.get('how') or '?'})", flush=True)
        rd.pages = 1
        rd.log.append({"page": 1, "what": _open_what(opened), "url": first,
                       "waited_s": thr.waits[-1] if thr.waits else 0.0,
                       "at": thr.now_fn().isoformat(timespec="seconds")})
        guarded(lambda: driver.browser("wait", "--time", "4000", profile_name=profile,
                                       target_id=rd.tab))
        for i, d in enumerate(days):
            url = archive_url("wsj", d)
            st: dict[str, Any] = {"url": url, "links_found": 0, "already_stored": 0,
                                  "read": 0, "refusals": []}
            rc["per_day"][d.isoformat()] = st
            try:
                if i > 0:
                    guarded(lambda: rd.navigate(url))
                rc["order"].append({"day": d.isoformat(), "what": "day_page", "url": url,
                                    "at": rd.log[-1]["at"], "ok": True})
                links = WR.select_links(guarded(rd.snapshot), ARCHIVE_PATTERN)
                rd.blank()                       # the day page waits blank while articles load
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
                    art = guarded(lambda: rd.read_article(lk, column=None))
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
            if progress_path:
                _tab_accounting(rc, readers.values())
                _write(rc | {"in_progress": True}, progress_path.name)
            if rc["stopped"]:
                break
    except Exception as exc:  # noqa: BLE001 -- the receipt says why, the tab still closes
        rc["stopped"] = rc["stopped"] or f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        if rd is not None:
            _close_all(driver, profile, readers, rc, recovery, parents, {"wsj": "wsj"})
            rc["tab_closed"] = bool(rc["tabs_closed"]) and all(rc["tabs_closed"].values())
            rc["tab_opened"] = rd.tab
            rc["footprint"] = _merged_footprint([rd], rc=rc)
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


#: What the last `main()` call did, for the queue's DONE rule (J3). `main`
#: fills it; `run_queue` clears it before each line.
_LAST_OUTCOME: dict[str, Any] = {}


def line_status(code: int, outcome: dict | None) -> str:
    """One queue line's verdict (Chunk J3, 2026-09-27: lines 3-6 of the 00:33
    queue were marked DONE with `n_articles 0`, one of them a claims pass over
    nothing).

    * a refusal / stop with nothing read -> `FAILED_WILL_RETRY`, whatever rc;
    * a claims pass with zero NEW stored articles -> `SKIPPED_NOTHING_TO_DO`
      (no marker: the next run tries again once reads exist);
    * rc 0 otherwise -> `DONE`; anything else -> `FAILED_WILL_RETRY`."""
    o = outcome or {}
    n = o.get("n_articles")
    if o.get("refused") and (not n or o.get("kind") == "claims"):
        return "FAILED_WILL_RETRY"          # a claims pass cut short leaves articles unread
    if o.get("kind") == "claims" and code == 0 and not o.get("refused") and not n:
        return "SKIPPED_NOTHING_TO_DO"
    return "DONE" if code == 0 else "FAILED_WILL_RETRY"


def run_queue(path: Path, *, inherit: list[str] | None = None,
              main_fn: Any = None, only_first: bool = False) -> dict:
    """Each line is one `dowjones_pull` command (its arguments), run in order.
    A line whose `line_status` is DONE (rc 0 AND not a refusal over nothing,
    J3) gets a `.done` marker (keyed by line number AND a hash of its text,
    so an EDITED line runs again); a re-run skips done lines. A failed line is recorded and the queue continues, so one refused
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
        _LAST_OUTCOME.clear()
        try:
            code = int(main_fn(argv))
        except SystemExit as exc:
            code = int(exc.code or 0)
        except Exception as exc:  # noqa: BLE001 -- one line fails, the night goes on
            code = 2
            rc["lines"].append({"line": lineno, "args": line, "status": "ERROR",
                                "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            continue
        outcome = dict(_LAST_OUTCOME)
        status = line_status(code, outcome)
        row = {"line": lineno, "args": line, "rc": code,
               "seconds": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
               "status": status, "outcome": outcome}
        print(f"queue line {lineno}: {status} (rc {code}, "
              f"{outcome.get('n_articles')} article(s)"
              f"{', ' + str(outcome.get('refused'))[:120] if outcome.get('refused') else ''})",
              flush=True)
        if status == "DONE":
            dd.mkdir(parents=True, exist_ok=True)
            DG.atomic_write_json(marker, {"line": lineno, "args": line,
                                          "done_utc": datetime.now(timezone.utc).isoformat(
                                              timespec="seconds")}, indent=None)
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
        "# run: python -m scripts.dowjones_pull --queue <this file> --handoff --profile muratclaw",
        "# one line = one command; a line that returns 0 gets a marker in "
        "<stem>.done/ and is skipped on re-run",
        f'--plan "barrons:stock_picks:10,wsj:heard_on_the_street:10,barrons:big_money_poll:3,'
        f'marketwatch:analyst_estimates:{"|".join(tick)}"',
    ]
    if rng:
        lines.append(f"--archive {rng}")
    lines.append(f"--claims --claims-since {today.isoformat()}")
    return "\n".join(lines) + "\n"


#: The search line's whole budget (pages, quote pages and articles together).
SHORTLIST_SEARCH_MAX_PAGES = 60


def carded_names(day: str, cards_dir: Path | None = None) -> list[str]:
    """Tickers with a NON-refused thesis card on `day` -- the rule
    `scripts/stock_lists_v3_build.load_cards` uses for the v3 note's §2."""
    d = Path(cards_dir) if cards_dir else Path(_config.OPTIMUS_LEDGER_DIR) / "thesis_cards" / day
    out = []
    for p in sorted(d.glob("*.json")) if d.exists() else []:
        if p.name.startswith("_"):
            continue
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(c, dict) and c.get("ticker") and \
                not str(c.get("verdict", "")).startswith("REFUSED"):
            out.append(str(c["ticker"]).upper())
    return out


def roi_order(day: str, note: Path | None = None) -> list[str]:
    """The v3 note's §3 ROI-list order (`| 1 | VKTX (n 19) | ...`), top first."""
    import re
    p = Path(note) if note else REPO / "docs" / "research_notes" / day / f"stock_lists_{day}_v3.md"
    if not p.exists():
        return []
    txt = p.read_text(encoding="utf-8")
    start = txt.find("# 3. ROI")
    if start < 0:
        return []
    end = txt.find("\n## EXCLUDED", start)
    sect = txt[start:end if end > 0 else len(txt)]
    return [m.group(1) for m in re.finditer(r"^\|\s*\d+\s*\|\s*([A-Z][A-Z0-9.\-]*)\s*\(", sect,
                                            re.M)]


def build_shortlist_queue_text(day: str, *, names: list[str] | None = None,
                               order: list[str] | None = None,
                               mw_done: set[str] | None = None,
                               search_max_pages: int = SHORTLIST_SEARCH_MAX_PAGES,
                               archive: str = "2026-09-22..2026-09-25") -> str:
    """The v3 shortlist queue (2026-09-27): the carded names, ROI-list order
    first, then the rest alphabetically.

    (a) MarketWatch analyst estimates for every name not already snapshotted
        on `day`; (b) WSJ + Barron's company search lanes over the same names,
        up to SEARCH_LINKS_PER_NAME articles per name, `search_max_pages` for
        the whole line; (c) the archive range; (d) claims last. Every reading
        line carries `--fresh-since day`, so a rerun after a UTC midnight still
        skips what this queue already did."""
    names = names if names is not None else carded_names(day)
    order = order if order is not None else roi_order(day)
    ranked = [t for t in order if t in names]
    ranked += sorted(t for t in names if t not in ranked)
    if mw_done is None:
        stored = WR.stored_urls()
        mw_done = {t for t in ranked
                   if _stored_since(stored, lane_url("marketwatch", "analyst_estimates", t), day)}
    mw = [t for t in ranked if t not in mw_done]
    lines = [
        f"# dowjones_pull queue -- the v3 shortlist ({len(ranked)} carded names on {day}; "
        f"ROI-list order first: {', '.join(ranked[:10])})",
        f"# written by: python -m scripts.dowjones_pull --write-shortlist-queue <this file> "
        f"--shortlist-date {day}",
        "# run: python -m scripts.dowjones_pull --queue <this file> --handoff --profile muratclaw",
        f"# (a) MarketWatch analyst estimates: {len(mw)} names ({len(mw_done)} already "
        f"snapshotted on {day} left out); one page each",
        f"# (b) WSJ quote page + Barron's stock page per name, <= {SEARCH_LINKS_PER_NAME} "
        f"article links each (<= {SEARCH_MAX_AGE_DAYS} days old when dated), "
        f"{search_max_pages} pages for the whole line",
        "# (c) the WSJ archive the 09-26 queue refused on the gateway; (d) claims last",
        "# one line = one command; a DONE line gets a marker in <stem>.done/ and is skipped",
    ]
    if mw:
        lines.append(f'--plan "marketwatch:analyst_estimates:{"|".join(mw)}" '
                     f"--fresh-since {day}")
    lines.append(f'--plan "wsj_search:{"|".join(ranked)},barrons_search:{"|".join(ranked)}" '
                 f"--max-pages {search_max_pages} --fresh-since {day}")
    if archive:
        lines.append(f"--archive {archive}")
    lines.append(f"--claims --claims-since {day}")
    return "\n".join(lines) + "\n"


# ────────────────────────────────── claims ──────────────────────────────────

#: 2026-09-28 (Murat: "it should always work and shouldnt be standing idle"):
#: when every plan line of the current queue is DONE, the supervisor builds the
#: next queue itself from these sources.
ROLLING_UNIVERSE_GLOB = "UNIVERSE_*.txt"


def rolling_names(*, universe_dir: Path | None = None, books: dict | None = None,
                  extra: list[str] | None = None) -> list[str]:
    """The union of the candidate set: the newest `UNIVERSE_*.txt` (the wide
    candidate list), the frozen books and the contest names
    (`digest_inbox.book_names()`), plus `extra`. Upper-case, de-duplicated."""
    d = Path(universe_dir) if universe_dir else DF.receipts_dir()
    names: list[str] = []
    files = sorted(d.glob(ROLLING_UNIVERSE_GLOB))
    if files:
        names += [ln.strip().upper() for ln in files[-1].read_text(encoding="utf-8").splitlines()
                  if ln.strip() and not ln.startswith("#")]
    if books is None:
        try:
            from backend.services import digest_inbox as DI
            books = DI.book_names()
        except Exception:  # noqa: BLE001 -- a missing book is an empty book
            books = {}
    for k in ("personal", "competition", "probe"):
        names += [str(t).upper() for t in (books or {}).get(k, []) if t]
    names += [str(t).upper() for t in (extra or []) if t]
    return list(dict.fromkeys(n for n in names if n.replace(".", "").replace("-", "").isalnum()))


def last_read_days(names: list[str], *, stored: dict[str, set[str]] | None = None,
                   seen_path: Path | None = None) -> dict[str, str]:
    """ticker -> the newest day ANY site's page for it was read ('' = never):
    the MarketWatch estimates page stored, or a WSJ / Barron's search page seen."""
    stored = WR.stored_urls() if stored is None else stored
    out = {n: "" for n in names}
    for n in names:
        days = stored.get(WR.norm_url(lane_url("marketwatch", "analyst_estimates", n))) or set()
        if days:
            out[n] = max(days)
    p = Path(seen_path) if seen_path else search_seen_path()
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            t, d = str(r.get("ticker") or "").upper(), str(r.get("day") or "")
            if t in out and d > out[t]:
                out[t] = d
    return out


def build_rolling_queue_text(names: list[str], last: dict[str, str], *, day: str,
                             cap: int = 120) -> str:
    """PURE. One rotating plan line over the names whose NEWEST read is OLDEST
    (never-read first), MarketWatch estimates + WSJ + Barron's stock pages, at
    most `cap` names. A name read today is skipped by the plan's own freshness
    rule, so the queue is exhausted only when every name has been read today."""
    order = sorted(names, key=lambda n: (last.get(n) or "", names.index(n)))[:cap]
    if not order:
        return f"# rolling queue {day}: no names\n"
    tk = "|".join(order)
    return "\n".join([
        f"# rolling queue built {day} by the night supervisor: {len(order)} of {len(names)} "
        f"names, oldest newest-read first (never read first)",
        f'--plan "marketwatch:analyst_estimates:{tk},wsj:search:{tk},barrons:search:{tk}"',
        ""])


def queue_exhausted(path: Path) -> bool:
    """True when every `--plan` line of the queue file has its DONE marker."""
    lines = [(n, ln) for n, ln in queue_lines(path) if ln.startswith("--plan")]
    if not lines:
        return True
    dd = queue_done_dir(path)
    return all((dd / f"{_line_key(n, ln)}.done").exists() for n, ln in lines)


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
        # 2026-09-29: the browse lane stores section-front headline lists and
        # general-news pages in the same store; neither is a Dow Jones article
        # and neither is sent for (paid) claim extraction here
        if art.get("page_kind") == "front" or art.get("source_kind") == "general_news":
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

# ─────────────────── reader workers: one process per site ────────────────────
#
# 2026-09-27: one page cost ~16 OpenClaw CLI round trips at ~9 s each, all in
# series, so a night read ~40 pages/hour while the pacing allowed ~180. Each
# CLI call is a fresh node process (~4-6 s of start-up measured with
# `browser --help`); the gateway serialises the Chrome MCP operations of one
# session with an async lock and names a pageId on every call (openclaw
# 2026.9.5 `withChromeMcpOperationLock`, `callTargetTool`), so CLI calls from
# several processes queue at the gateway instead of acting on each other's
# tab. Splitting the plan by SITE into worker processes overlaps the start-up
# and the local waits; the shared, file-locked throttle keeps the pace ONE
# budget. Isolation: each worker has its own `_OPENED_TABS` (the close guard),
# its own lock, receipts stamped with `worker` + `pid`, and a start-up cleanup
# that reads only its OWN dead runs' receipts.

def split_lanes_by_site(lanes: list[dict], n: int) -> dict[str, list[dict]]:
    """worker id -> lanes. One worker per SOURCE when `n` >= the number of
    sources (the id is the source: `wsj`, `barrons`, `marketwatch`); fewer
    workers take whole sources round-robin (`g1`, `g2`, ...). A source is
    never split across workers: two processes on one site would each keep
    their own same-host history."""
    sources = list(dict.fromkeys(ln["source"] for ln in lanes))
    n = max(1, int(n))
    if n >= len(sources):
        return {s: [ln for ln in lanes if ln["source"] == s] for s in sources}
    groups: dict[str, list[dict]] = {f"g{i + 1}": [] for i in range(n)}
    for i, s in enumerate(sources):
        groups[f"g{i % n + 1}"] += [ln for ln in lanes if ln["source"] == s]
    return groups


def plan_spec(lanes: list[dict]) -> str:
    """The `--plan` text for `lanes` (inverse of `parse_plan`)."""
    out = []
    for ln in lanes:
        if ln["section"] in TICKER_SECTIONS:
            out.append(f"{ln['source']}:{ln['section']}:{'|'.join(ln['tickers'])}")
        else:
            out.append(f"{ln['source']}:{ln['section']}:{ln['max']}")
    return ",".join(out)


def split_budget(budget: int | None, groups: dict[str, list[dict]]) -> dict[str, int | None]:
    """An explicit `--max-pages` split across workers in proportion to each
    group's default budget (sum of lane maxima + lanes + 2), rounded up; None
    stays None (each worker then uses its own default)."""
    if budget is None:
        return {k: None for k in groups}
    need = {k: sum(ln["max"] for ln in v) + len(v) + 2 for k, v in groups.items()}
    tot = sum(need.values()) or 1
    return {k: max(1, -(-int(budget) * need[k] // tot)) for k in groups}


def worker_argv(spec: str, wid: str, *, stamp: str, profile: str,
                max_pages: int | None, fresh_since: str | None,
                parent_tabs: str = "") -> list[str]:
    argv = [sys.executable, "-m", "scripts.dowjones_pull", "--plan", spec, "--worker", wid,
            "--run-stamp", stamp, "--profile", profile, "--handoff"]
    if max_pages is not None:
        argv += ["--max-pages", str(max_pages)]
    if fresh_since:
        argv += ["--fresh-since", fresh_since]
    if parent_tabs:
        argv += ["--parent-tabs", parent_tabs]
    return argv


def workers_pid_path() -> Path:
    return DF.receipts_dir() / "queue_workers.pid"


def run_workers(groups: dict[str, list[dict]], *, stamp: str, profile: str,
                max_pages: int | None, fresh_since: str | None, parent_tabs: str = "",
                spawn: Any = None, bind: Any = None, rdir: Path | None = None) -> dict:
    """Start one `dowjones_pull --plan ... --worker <id>` process per group,
    wait for all, and fold their receipts into one outcome. `spawn(argv)`
    returns a Popen-like (`pid`, `wait()`); `bind(pid)` ties the child to this
    process's lifetime (a Windows job object: killing the launcher by PID
    kills its workers too -- never by image name). The PIDs are written to
    `queue_workers.pid` before the first wait."""
    import subprocess
    spawn = spawn or (lambda av: subprocess.Popen(av, cwd=str(REPO), stdin=subprocess.DEVNULL))
    if bind is None:
        def bind(pid: int) -> dict:
            try:
                from backend.services import llama_server as _LS
                return _LS.bind_lifetime(pid)
            except Exception as exc:  # noqa: BLE001 -- reported, never fatal
                return {"bound": False, "reason": f"{type(exc).__name__}: {exc}"}
    budgets = split_budget(max_pages, groups)
    procs: dict[str, Any] = {}
    out: dict[str, Any] = {"receipt": "dowjones_pull.workers", "stamp": stamp,
                           "launcher_pid": __import__("os").getpid(), "workers": {}}
    for wid, lns in groups.items():
        av = worker_argv(plan_spec(lns), wid, stamp=stamp, profile=profile,
                         max_pages=budgets[wid], fresh_since=fresh_since,
                         parent_tabs=parent_tabs)
        p = spawn(av)
        procs[wid] = p
        out["workers"][wid] = {"pid": p.pid, "lanes": [ln["lane"] for ln in lns],
                               "max_pages": budgets[wid], "bound": bind(p.pid)}
        print(f"worker {wid}: pid {p.pid} lanes {out['workers'][wid]['lanes']}", flush=True)
    DG.atomic_write_json(workers_pid_path(), {
        "launcher": out["launcher_pid"], "stamp": stamp,
        "workers": {k: v["pid"] for k, v in out["workers"].items()}}, indent=None)
    d = Path(rdir) if rdir else DF.receipts_dir()
    total, refusals, codes = 0, [], {}
    for wid, p in procs.items():
        code = int(p.wait() or 0)
        codes[wid] = code
        rp = d / f"plan_{stamp}_{wid}.json"
        try:
            r = json.loads(rp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            r = {}
        n = int(r.get("n_articles") or 0)
        total += n
        why = r.get("refused") or r.get("stopped") or "; ".join(
            f"{k}: {v.get('dropped')}" for k, v in (r.get("lanes") or {}).items()
            if v.get("dropped") and not str(v["dropped"]).startswith(("EXHAUSTED",
                                                                       "BUDGET_SPENT")))
        if code != 0 or not r:
            refusals.append(f"{wid}: rc {code}: {str(why or 'no receipt')[:160]}")
        out["workers"][wid].update(rc=code, receipt=str(rp) if r else None, n_articles=n,
                                   refused=why or None)
    out.update(n_articles=total, refused="; ".join(refusals)[:300] or None,
               rc=0 if all(c == 0 for c in codes.values()) else 2)
    return out


def _launch_workers(a: Any, day: str, stamp: str, *, oc: Any = None,
                    spawn: Any = None, bind: Any = None) -> int:
    """`--plan ... --workers N`: the pre-flight a worker cannot do alone,
    then the workers.

    1. re-attach if needed, and resolve every source's parent through the
       MARKER rule -- no marker tab refuses here, before any process starts
       (each worker resolves again itself and refuses the same way);
    2. take the SINGLE-SESSION lock (refuses while any reader, worker or not,
       is alive), close what dead single-session runs left open (receipts
       with no `worker`), release it;
    3. start the workers and wait (`run_workers`)."""
    if oc is None:
        from backend.services import openclaw_client as oc  # type: ignore[no-redef]
    stamp_full = f"{day}_{stamp}"
    pre_log: list = []
    out: dict[str, Any] = {"receipt": "dowjones_pull.workers", "plan": a.plan,
                           "stamp": stamp_full}
    try:
        lanes = parse_plan(a.plan)
        groups = split_lanes_by_site(lanes, a.workers)
        WR.ensure_attached(a.profile, oc=oc, log=pre_log)
        out["instance"] = instance_gate(a.profile, oc)
        srcs = list(dict.fromkeys(ln["source"] for ln in lanes))
        direct = WR.direct_open_ok(oc, a.profile)
        parents = resolve_parent_tabs(srcs, [] if direct else oc.tabs(profile_name=a.profile),
                                      explicit=parse_parent_tabs(a.parent_tabs),
                                      exclude=set(getattr(oc, "_OPENED_TABS", set())),
                                      direct=direct)
        out["parent_tabs"] = parents
        lock = WR.acquire_reader_lock()
        try:
            out["startup_cleanup"] = startup_cleanup(oc, a.profile, worker=None)
        finally:
            WR.release_reader_lock(lock)
    except Exception as exc:  # noqa: BLE001 -- a refusal is a finding, rc 2
        print(f"REFUSED: {type(exc).__name__}: {exc}")
        out.update(refused=f"{type(exc).__name__}: {exc}"[:400], reattach_log=pre_log)
        _write(out, f"workers_{stamp_full}.json")
        _LAST_OUTCOME.update(kind="plan", n_articles=0, refused=out["refused"][:300])
        return 2
    res = run_workers(groups, stamp=stamp_full, profile=a.profile,
                      max_pages=a.max_pages if a.max_pages != 20 else None,
                      fresh_since=a.fresh_since or None, parent_tabs=a.parent_tabs,
                      spawn=spawn, bind=bind)
    out.update(res, reattach_log=pre_log)
    p = _write(out, f"workers_{stamp_full}.json")
    print(json.dumps({"workers": {"receipt": str(p), "n_articles": res["n_articles"],
                                  "refused": res["refused"],
                                  "per_worker": {k: {x: v.get(x) for x in
                                                     ("pid", "rc", "n_articles")}
                                                 for k, v in res["workers"].items()}}},
                     indent=1, default=str))
    _LAST_OUTCOME.update(kind="plan", n_articles=res["n_articles"], refused=res["refused"])
    return int(res["rc"])


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
    ap.add_argument("--profile", default="muratclaw")
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
    ap.add_argument("--fresh-since", default="",
                    help="plan: a ticker done (MW page stored / search page loaded) on or "
                         "after this day is skipped (default: today); lets a line resume "
                         "across a UTC midnight")
    ap.add_argument("--write-shortlist-queue", default="",
                    help="write the v3 shortlist queue (carded names) to this path")
    ap.add_argument("--shortlist-date", default="",
                    help="the thesis_cards/<date> the shortlist queue is built from")
    ap.add_argument("--workers", type=int, nargs="?", default=1,
                    const=int(getattr(_config, "DOWJONES_READER_WORKERS_DEFAULT", 3)),
                    help="plan: split the lanes by site into N reader processes sharing "
                         "one throttle (bare --workers = config default, 3)")
    ap.add_argument("--worker", default="",
                    help="(set by --workers) run as this worker id with its own lock")
    ap.add_argument("--run-stamp", default="",
                    help="(set by --workers) receipt stamp YYYY-MM-DD_HHMMSS")
    ap.add_argument("--queue", default="", help="a file of dowjones_pull lines, run in order")
    ap.add_argument("--queue-first-only", action="store_true")
    ap.add_argument("--write-queue", default="",
                    help="write the night's queue file (from the books) to this path")
    a = ap.parse_args(argv)
    from backend.services.openclaw_client import dedicated_profiles, is_operator_profile
    if getattr(a, "profile", None) and is_operator_profile(a.profile) \
            and a.profile not in dedicated_profiles():
        # an operator profile that is NOT the proven dedicated Chrome keeps the
        # marker rule; the dedicated one is proven by `instance_gate` instead
        global PARENT_MARKER
        PARENT_MARKER = MARKER_DEFAULT
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
    if a.write_shortlist_queue:
        qp = Path(a.write_shortlist_queue)
        qp.parent.mkdir(parents=True, exist_ok=True)
        DG.atomic_write_text(qp, build_shortlist_queue_text(a.shortlist_date or day))
        out["write_shortlist_queue"] = str(qp)
    if a.write_queue:
        qp = Path(a.write_queue)
        qp.parent.mkdir(parents=True, exist_ok=True)
        DG.atomic_write_text(qp, build_queue_text())
        out["write_queue"] = str(qp)
    if a.queue:
        # START-UP GUARD (2026-09-27 disk-full): a queue that cannot write its
        # receipts must not start reading; refuse by name before any page load.
        try:
            DG.require_free(_config.DISK_FREE_DEAD_GB + 1, "dowjones_pull --queue",
                            path=DF.receipts_dir())
        except DG.DiskTooFull as exc:
            print(f"REFUSED: {exc}", flush=True)
            return 2
        print(TOU_SENTENCE, flush=True)
        def _line_main(av: list[str]) -> int:
            extra = ["--profile", a.profile] if "--profile" not in av else []
            if a.workers > 1 and "--plan" in av and "--workers" not in av:
                extra += ["--workers", str(a.workers)]
            return main(av + extra)
        r = run_queue(Path(a.queue), inherit=["--handoff"] if a.handoff else [],
                      main_fn=_line_main, only_first=a.queue_first_only)
        p = _write(r, f"queue_{day}_{datetime.now(timezone.utc):%H%M%S}.json")
        out["queue"] = {"receipt": str(p), "lines": [
            {k: ln.get(k) for k in ("line", "status", "rc", "seconds")} for ln in r["lines"]]}
        rc = 0 if all(ln["status"] in ("DONE", "SKIPPED_DONE", "SKIPPED_NOTHING_TO_DO")
                      for ln in r["lines"]) else 2
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
        pre_log: list = []
        try:
            from backend.services import openclaw_client as OCm
            # RUNNING before `tabs`: a stopped profile is re-attached with
            # `browser start` (<= 2 attempts, 20 s each); a dead gateway refuses
            WR.ensure_attached(a.profile, oc=OCm, log=pre_log)
            instance_gate(a.profile, OCm)
            direct = WR.direct_open_ok(OCm, a.profile)
            parents = resolve_parent_tabs(
                ["wsj"], [] if direct else OCm.tabs(profile_name=a.profile),
                explicit=({"wsj": a.parent_tab} if a.parent_tab else
                          parse_parent_tabs(a.parent_tabs)),
                exclude=set(getattr(OCm, "_OPENED_TABS", set())), direct=direct)
            print(f"parent tab: wsj -> {parents['wsj']['tab']} ({parents['wsj']['how']}, "
                  f"{parents['wsj']['url'][:80]})", flush=True)
            r = run_archive(days, parent_tab=parents["wsj"]["tab"], max_per_day=a.max_per_day,
                            profile=a.profile, progress_path=rpath)
            r["parent_tabs"] = parents
            r["reattach_log"] = pre_log + r.get("reattach_log", [])
            r["reattaches"] = r.get("reattaches", 0) + sum(1 for x in pre_log if x.get("ok"))
            if isinstance(r.get("footprint"), dict):           # the pre-run re-attach counts too
                r["footprint"]["reattaches"] = r["reattaches"]
        except Exception as exc:  # noqa: BLE001 -- a refusal is a finding, rc 2
            print(f"REFUSED: {type(exc).__name__}: {exc}")
            _LAST_OUTCOME.update(kind="archive", n_articles=0,
                                 refused=f"{type(exc).__name__}: {exc}"[:300])
            _write({"receipt": "dowjones_pull.archive", "n_articles": 0, "days": a.archive,
                    "reattach_log": pre_log,
                    "refused": f"{type(exc).__name__}: {exc}"[:400]}, rpath.name)
            return 2
        p = _write(r, rpath.name)
        out["archive"] = {"receipt": str(p), "n_articles": r["n_articles"],
                          "per_day": {k: {x: v[x] for x in ("links_found", "already_stored",
                                                            "read")}
                                      for k, v in r["per_day"].items()},
                          "stopped": r["stopped"], "tab_closed": r.get("tab_closed"),
                          "reattaches": r.get("reattaches"),
                          "footprint": (r.get("footprint") or {}).get("verdict")}
        rc = 0 if r["complete"] else 2
        _LAST_OUTCOME.update(kind="archive", n_articles=r["n_articles"], refused=r["stopped"])
    if a.plan and a.workers > 1 and not a.worker:
        print(TOU_SENTENCE, flush=True)
        if not a.handoff or not handoff_ok():
            print(f"REFUSED_NO_HANDOFF: browser reads need --handoff AND "
                  f"{_config.DOWJONES_HANDOFF_FILE}.")
            return 2
        rc = _launch_workers(a, day, datetime.now(timezone.utc).strftime("%H%M%S"))
        out["plan_workers"] = {"rc": rc, "n_articles": _LAST_OUTCOME.get("n_articles"),
                               "refused": _LAST_OUTCOME.get("refused")}
    elif a.plan:
        print(TOU_SENTENCE, flush=True)
        if not a.handoff or not handoff_ok():
            print(f"REFUSED_NO_HANDOFF: browser reads need --handoff AND "
                  f"{_config.DOWJONES_HANDOFF_FILE}.")
            return 2
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        rpath = DF.receipts_dir() / f"plan_{day}_{stamp}.json"
        if a.worker:
            rpath = DF.receipts_dir() / f"plan_{a.run_stamp or day + '_' + stamp}_{a.worker}.json"
        pre_log: list = []
        try:
            lanes = parse_plan(a.plan)
            from backend.services import openclaw_client as OCm
            WR.ensure_attached(a.profile, oc=OCm, log=pre_log)   # before `tabs` (see --archive)
            instance_gate(a.profile, OCm)
            srcs = list(dict.fromkeys(ln["source"] for ln in lanes))
            explicit = parse_parent_tabs(a.parent_tabs)
            if a.parent_tab and len(srcs) == 1:
                explicit.setdefault(srcs[0], a.parent_tab)
            direct = WR.direct_open_ok(OCm, a.profile)
            parents = resolve_parent_tabs(srcs,
                                          [] if direct else OCm.tabs(profile_name=a.profile),
                                          explicit=explicit,
                                          exclude=set(getattr(OCm, "_OPENED_TABS", set())),
                                          direct=direct)
            for s_, v in parents.items():
                print(f"parent tab: {s_} -> {v['tab']} ({v['how']}, {v['url'][:80]})",
                      flush=True)
            r = run_plan(lanes, parents=parents, profile=a.profile,
                         max_pages=a.max_pages if a.max_pages != 20 else None,
                         progress_path=rpath, fresh_since=a.fresh_since or None,
                         worker=a.worker or None)
            r["reattach_log"] = pre_log + r.get("reattach_log", [])
            r["reattaches"] = r.get("reattaches", 0) + sum(1 for x in pre_log if x.get("ok"))
            if isinstance(r.get("footprint"), dict):           # the pre-run re-attach counts too
                r["footprint"]["reattaches"] = r["reattaches"]
        except Exception as exc:  # noqa: BLE001 -- a refusal is a finding, rc 2
            print(f"REFUSED: {type(exc).__name__}: {exc}")
            _LAST_OUTCOME.update(kind="plan", n_articles=0,
                                 refused=f"{type(exc).__name__}: {exc}"[:300])
            # keep what run_plan's `finally` already wrote there (its `opened`
            # / `tabs_closed` accounting is what the next start of this worker
            # reads to close a crashed run's tabs) and add the refusal to it
            try:
                prior = json.loads(rpath.read_text(encoding="utf-8")) if rpath.exists() else {}
            except (OSError, ValueError):
                prior = {}
            _write({**(prior if isinstance(prior, dict) else {}),
                    "receipt": "dowjones_pull.plan", "plan": a.plan, "n_articles": 0,
                    "reattach_log": pre_log, "worker": a.worker or None,
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
                       "budget_spent": r.get("budget_spent"),
                       "orphaned_tabs": r.get("orphaned_tabs"), "blanks": r.get("blanks"),
                       "tab_rotations": len(r.get("tab_rotations") or []),
                       "startup_cleanup_closed": (r.get("startup_cleanup") or {}).get("closed"),
                       "reattaches": r["reattaches"],
                       "footprint": r["footprint"].get("verdict"),
                       "hour_cap_waits_s": r["hour_cap_waits_s"]}
        planned_end = ("EXHAUSTED", "BUDGET_SPENT")
        rc = 0 if not r["stopped"] and all(
            v["dropped"] is None or str(v["dropped"]).startswith(planned_end)
            for v in r["lanes"].values()) else 2
        dropped = [f"{k}: {v['dropped']}" for k, v in r["lanes"].items()
                   if v["dropped"] and not str(v["dropped"]).startswith(planned_end)]
        _LAST_OUTCOME.update(kind="plan", n_articles=r["n_articles"],
                             refused=r["stopped"] or ("; ".join(dropped)[:300] or None))
    if a.source:
        print(TOU_SENTENCE, flush=True)
        if not a.handoff or not handoff_ok():
            print(f"REFUSED_NO_HANDOFF: browser reads need --handoff AND "
                  f"{_config.DOWJONES_HANDOFF_FILE} (created by Murat when he hands the "
                  f"PC over). Use scripts/digest_ingest.py for pasted articles.")
            return 2
        if not a.section or (not a.parent_tab and a.profile not in dedicated_profiles()):
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
        n_new = r["n_articles"] + int((r.get("mw_analyst_snapshot") or {}).get("n_pages") or 0)
        _LAST_OUTCOME.update(kind="claims", n_articles=n_new, refused=r["stopped"])
        if r["stopped"] and str(r["stopped"]).startswith("REFUSED"):
            rc = 2
    if not out and rc == 0:
        ap.print_help()
        return 2
    print(json.dumps(out, indent=1, default=str))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
