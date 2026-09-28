"""What an alert may be made OF: the ticker set, the truth-lane events, the price.

The readers behind `backend/services/alerts.py` (LANE A, 2026-09-28). Nothing
here touches the network, calls an LLM, or places anything anywhere: every
input is a file some other collector already wrote.

WHICH EVENTS MAY ORIGINATE AN ALERT (this version)
==================================================
Only TRUTH-lane events with a primary-source link, from a free permitted source:

* ``sec_8k``     -- the SEC current-filings Atom rows `scripts/news_pull.py`
  writes to `news_corpus/sec_edgar_8k_current_atom/<day>.jsonl`, typed by their
  8-K ITEM CODE through `event_vocabulary.items_index()`. When the same filing
  has an EX-99 exhibit in `news_corpus/sec_edgar_8k_ex99_body/` (the company's
  own press release attached to the 8-K), that exhibit's URL is the primary
  source link; otherwise the filing index.
* ``sec_form4``  -- open-market purchase clusters (transaction code P, >= N
  distinct insiders) from `sec_insider/insider_events_v1.parquet`. Availability
  is that tape's `observed_at_utc` (FILING DATE end-of-day ET, the conservative
  bound -- the bulk tape carries no acceptance time), NEVER the transaction date.
  The tape is quarterly; when it ends months ago this reader returns nothing
  fresh and says so in its stats.

Discovery-lane headlines (Google News, GDELT, yfinance, the Dow Jones RSS) are
read only by `discovery_confirmations`: they may CONFIRM an alert, never
originate one. X, Reddit and StockTwits are not read at all.

The event type of an 8-K is inferred from its item code ALONE -- no typed
extraction (that needs an LLM, which this version does not call). An item that
maps to several vocabulary ids (5.02 is a departure OR an appointment) keeps an
`sec_8k_item_<code>` id and names the candidates; the alert says which one
applies is NOT KNOWN rather than guessing.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from backend import config as _cfg

NY_TZ = "America/New_York"

#: News-corpus directories that are the DISCOVERY lane (confirm only).
DISCOVERY_DIR_PREFIXES: tuple[str, ...] = (
    "google_news_rss_", "gdelt_doc_v2", "yfinance_ticker_news", "wsj_", "barrons",
    "mw_", "dowjones", "dj_reader_", "nikkei_asia_rss", "alpaca_benzinga_news")
#: Never read, never originate, never confirm.
SOCIAL_MARKERS: tuple[str, ...] = ("reddit", "stocktwits", "twitter", "x_timeline")

ATOM_DIR = "sec_edgar_8k_current_atom"
#: 8-K items that usually FURNISH a document about another item (see `_vocab_pick`).
CATCH_ALL_ITEMS: tuple[str, ...] = ("7.01", "8.01")
EX99_DIR = "sec_edgar_8k_ex99_body"

#: The typing rule that turns an event into (event type id, fact key). Frozen on
#: every alert row and every send-result row (review 2026-09-28 F2): a later
#: rule change must be visible as a different version, never as a silently
#: different message rendered from the same row.
#:   8k_item_priority/1  the FIRST qualifying item in filing order (06:04Z dry run)
#:   8k_item_priority/2  a specific item before the catch-alls 7.01/8.01, then the
#:                       largest magnitude bucket, then filing order; plain-words
#:                       fact line from `ITEM_PLAIN`
#:   form4_cluster/1     >= N distinct open-market buyers inside the lookback
TYPING_RULE_VERSION = "8k_item_priority/2;form4_cluster/1"

#: 8-K item -> (what the company did, in plain words; the KEY NOUN the phone line
#: must carry). The first line of an alert leads with this, so the event is
#: readable in a lock-screen preview (review 2026-09-28 F1: the old line cut the
#: boilerplate at 90 characters, before the item). Every item the vocabulary
#: maps is listed; `test_every_vocabulary_item_has_plain_words` pins it.
ITEM_PLAIN: dict[str, tuple[str, str]] = {
    "1.01": ("entered into a material agreement", "agreement"),
    "1.02": ("ended a material agreement", "agreement"),
    "1.03": ("reported bankruptcy or receivership", "bankruptcy"),
    "1.05": ("reported a material cybersecurity incident", "cybersecurity"),
    "2.01": ("completed an acquisition or disposal of assets", "acquisition"),
    "2.02": ("reported earnings (results of operations)", "earnings"),
    "2.03": ("took on a material debt or other financial obligation", "debt"),
    "2.04": ("reported an event that accelerates a debt or obligation", "debt"),
    "3.01": ("received a delisting notice or moved its listing", "delisting"),
    "3.02": ("sold shares in an unregistered offering", "shares"),
    "4.01": ("changed its auditor", "auditor"),
    "4.02": ("said past financial statements can no longer be relied on",
             "financial statements"),
    "5.02": ("reported a director or officer leaving or joining", "officer"),
    "7.01": ("published a Regulation FD disclosure", "Regulation FD"),
    "8.01": ("reported an 'other event', the catch-all item", "other event"),
}
FORM4_KEY_NOUN = "insiders"


def plain_item(code: str, text: str = "") -> str:
    """What the item says the company did; the item's own title when unmapped."""
    got = ITEM_PLAIN.get(str(code))
    return got[0] if got else f"filed Item {code}" + (f" ({text})" if text else "")


_ITEM_RE = re.compile(r"Item\s+(\d+\.\d+):\s*(.*?)(?=\s*Item\s+\d+\.\d+:|$)", re.S)
_ACC_IN_URL = re.compile(r"/Archives/edgar/data/\d+/(\d{18})/")


def _refused(msg: str) -> Exception:
    from backend.services.alerts import AlertRefused
    return AlertRefused(msg)


def _utc(x: Any) -> Optional[datetime]:
    if x is None or x == "":
        return None
    try:
        t = pd.Timestamp(x)
    except (TypeError, ValueError):
        return None
    if pd.isna(t):
        return None
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert("UTC").to_pydatetime()


def corpus_root() -> Path:
    return Path(_cfg.OPTIMUS_LEDGER_DIR) / "news_corpus"


# ───────────────────────────── the ticker set ──────────────────────────────

def alert_universe(*, now: datetime, funnel_path: Optional[Path] = None,
                   books_path: Optional[Path] = None) -> dict:
    """Union of the CURRENT candidate set (the funnel) and the frozen books.

    Refuses when the funnel is missing, undateable or older than
    `investment_committee.FUNNEL_STALE_DAYS` -- the same staleness rule the
    committee applies, not a second one. Twins and controls are left out: they
    are random draws standing in for a comparison, not names anyone chose.
    """
    from backend.services import investment_committee as IC
    from backend.services import llm_portfolio as LP

    fp = Path(funnel_path or _cfg.IC_FUNNEL_PATH)
    try:
        funnel = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _refused(f"REFUSED: candidate set unreadable at {fp}: {type(exc).__name__}")
    gen = funnel.get("generated_at")
    stale = IC.funnel_staleness(gen, now=now)
    if stale:
        raise _refused(f"REFUSED: the candidate set is not current -- {stale}")
    funnel_t = {str(c.get("ticker") or "").upper() for c in funnel.get("candidates") or []}
    funnel_t.discard("")
    try:
        books = [b for b in LP.read_books(books_path)
                 if b.get("kind") in ("personal", "competition")]
    except OSError:
        books = []
    book_t = {str(p.get("ticker") or "").upper() for b in books for p in b.get("positions") or []}
    book_t -= {"", "CASH"}
    tickers = sorted(funnel_t | book_t)
    if not tickers:
        raise _refused("REFUSED: the alert universe is EMPTY (no funnel candidate, no book name)")
    newest = max((str(b.get("frozen_utc") or "") for b in books), default=None) or None
    age = IC._funnel_age_days(gen, now=now)
    return {"tickers": tickers, "n": len(tickers), "n_funnel": len(funnel_t),
            "n_books": len(books), "n_book_tickers": len(book_t),
            "funnel_path": str(fp), "funnel_generated_at": gen,
            "funnel_age_days": round(age, 2) if age is not None else None,
            "funnel_stale_limit_days": IC.FUNNEL_STALE_DAYS,
            "books_newest_frozen_utc": newest}


# ──────────────────────────────── SEC 8-K ───────────────────────────────────

def parse_8k_items(body: str) -> list[tuple[str, str]]:
    """[(item code, item text)] in filing order, from an Atom row's body."""
    return [(m.group(1), " ".join(m.group(2).split())[:160])
            for m in _ITEM_RE.finditer(str(body or ""))]


def load_cik_map(path: Optional[Path] = None) -> dict[int, list[tuple[str, str]]]:
    """CIK -> [(ticker, company)] in the SEC file's order (share classes share a CIK)."""
    p = Path(path or Path(_cfg.OPTIMUS_LEDGER_DIR) / "edgar_8k" / "company_tickers.json")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _refused(f"REFUSED: CIK->ticker map unreadable at {p}: {type(exc).__name__}")
    out: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for r in (raw.values() if isinstance(raw, dict) else raw):
        try:
            out[int(r["cik_str"])].append((str(r["ticker"]).upper(), str(r.get("title") or "")))
        except (KeyError, TypeError, ValueError):
            continue
    return dict(out)


def _cik_of(row: dict) -> Optional[int]:
    for tag in row.get("entity_tags") or []:
        if str(tag).startswith("cik:"):
            try:
                return int(str(tag)[4:])
            except ValueError:
                return None
    m = re.search(r"\((\d{10})\)", str(row.get("title") or ""))
    return int(m.group(1)) if m else None


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _days_back(now: datetime, hours: float) -> list[str]:
    d0 = (now - timedelta(hours=hours + 24)).date()
    return [str(d0 + timedelta(days=i)) for i in range((now.date() - d0).days + 1)]


def _vocab_pick(codes: list[str]) -> tuple[str, str, list[str], Optional[int]]:
    """(primary item, event type id, candidate ids, direction prior).

    Primary = a SPECIFIC item before a catch-all one (7.01 Reg FD and 8.01
    Other Events mostly carry the press release that announces a specific item
    -- measured on the first live run: AB's leadership-change 8-K typed as 7.01
    while its 5.02 was the fact), then the largest magnitude bucket among the
    item's candidate ids, then filing order. One candidate id -> that id; several
    -> `sec_8k_item_<code>` with the candidates named. The prior is kept only
    when every candidate agrees on it.
    """
    from backend.services import event_vocabulary as V
    idx = V.items_index()
    rank = {b: i for i, b in enumerate(V.MAGNITUDE_BUCKETS)}
    best, best_r = None, (-1, -1)
    for c in codes:
        r = (0 if c in CATCH_ALL_ITEMS else 1,
             max(rank.get(V.by_id(i).magnitude_bucket, 0) for i in idx[c]))
        if r > best_r:
            best, best_r = c, r
    ids = list(idx[best])
    priors = {V.by_id(i).direction_prior for i in ids}
    prior = next(iter(priors)) if len(priors) == 1 else None
    etype = ids[0] if len(ids) == 1 else f"sec_8k_item_{best}"
    return best, etype, ids, prior


def read_8k_events(*, now: datetime, universe: Iterable[str], root: Optional[Path] = None,
                   cik_map: Optional[dict] = None,
                   max_age_h: Optional[float] = None) -> tuple[list[dict], dict]:
    """Typed truth-lane events from the 8-K Atom corpus, first seen within `max_age_h`."""
    from backend.services import event_vocabulary as V
    root = Path(root or corpus_root())
    max_age_h = float(max_age_h if max_age_h is not None else _cfg.ALERT_EVENT_MAX_AGE_H)
    uni = {str(t).upper() for t in universe}
    cmap = cik_map if cik_map is not None else load_cik_map()
    qualifying = set(V.items_index())
    stats: dict[str, Any] = defaultdict(int)
    days = _days_back(now, max_age_h)
    ex99: dict[str, str] = {}
    for d in days:
        for r in _read_jsonl(root / EX99_DIR / f"{d}.jsonl"):
            m = _ACC_IN_URL.search(str(r.get("url") or ""))
            if m and "EX-99.1" in str(r.get("title") or "") and m.group(1) not in ex99:
                ex99[m.group(1)] = str(r["url"])
            elif m and m.group(1) not in ex99:
                ex99[m.group(1)] = str(r["url"])
    files = [root / ATOM_DIR / f"{d}.jsonl" for d in days]
    stats["atom_files_present"] = sum(p.exists() for p in files)
    newest_seen = None
    events = []
    for p in files:
        for r in _read_jsonl(p):
            stats["rows_read"] += 1
            seen = _utc(r.get("first_seen_utc"))
            if seen is not None and (newest_seen is None or seen > newest_seen):
                newest_seen = seen
            if seen is None or seen > now or (now - seen).total_seconds() > max_age_h * 3600:
                stats["outside_age_window"] += 1
                continue
            cik = _cik_of(r)
            names = [(t, c) for t, c in cmap.get(cik, []) if t in uni] if cik else []
            if not names:
                stats["ticker_not_in_universe"] += 1
                continue
            items = parse_8k_items(r.get("body") or "")
            codes = [c for c, _ in items if c in qualifying]
            if not codes:
                stats["no_qualifying_item"] += 1
                continue
            ticker, company = names[0]
            primary, etype, cands, prior = _vocab_pick(codes)
            text = dict(items)[primary]
            form = str(r.get("title") or "8-K").split(" - ")[0].strip() or "8-K"
            acc = str(r.get("raw_id") or "").replace("-", "")
            pr_url = ex99.get(acc)
            others = [c for c in codes if c != primary]
            published = _utc(r.get("published_utc"))
            also = f"; also Item(s) {', '.join(others)}" if others else ""
            # the important words FIRST (ticker, what happened, the item), the
            # company's long legal name last, so a cut loses only the name
            fact_line = (f"{ticker} {plain_item(primary, text)} "
                         f"({form} Item {primary}{also}). {company.rstrip('.')}.")
            fact = (f"{company} ({ticker}) filed a Form {form} with the SEC"
                    + (f", accepted {published:%Y-%m-%d %H:%M} UTC" if published else "")
                    + f", reporting Item {primary} ({text})"
                    + (f"; also Item(s) {', '.join(others)}" if others else "") + ".")
            events.append({
                "ticker": ticker, "company": company, "source_kind": "sec_8k",
                "lane": "truth", "event_type_id": etype, "event_type_candidates": cands,
                "direction_prior": prior, "fact": fact, "fact_line": fact_line,
                "fact_key": f"8k_item:{primary}", "primary_item": primary,
                "typing_rule_version": TYPING_RULE_VERSION,
                "headline": f"{form} Item {primary}: {text[:70]}",
                "items": codes, "form": form, "amendment": form.upper().endswith("/A"),
                "accession": r.get("raw_id"),
                "source_url": pr_url or str(r.get("url") or ""),
                "source_url_kind": ("company press release (EX-99 on the 8-K)" if pr_url
                                    else "SEC filing index"),
                "observed_utc": seen.isoformat(timespec="seconds"),
                "published_utc": published.isoformat(timespec="seconds") if published else None,
                "sibling_tickers": [t for t, _ in names[1:]]})
            stats["events"] += 1
    stats["newest_first_seen_utc"] = newest_seen.isoformat(timespec="seconds") if newest_seen else None
    return events, dict(stats)


# ──────────────────────────────── SEC Form 4 ────────────────────────────────

def read_form4_clusters(*, now: datetime, universe: Iterable[str],
                        path: Optional[Path] = None, max_age_h: Optional[float] = None,
                        min_buyers: Optional[int] = None,
                        lookback_days: Optional[int] = None,
                        frame: Optional[pd.DataFrame] = None) -> tuple[list[dict], dict]:
    """Open-market purchase clusters whose COMPLETING filing became public
    within `max_age_h`. The clock is the tape's availability bound, never the
    transaction date (a Form 4 is due two business days after the trade)."""
    max_age_h = float(max_age_h if max_age_h is not None else _cfg.ALERT_EVENT_MAX_AGE_H)
    min_buyers = int(min_buyers or _cfg.ALERT_INSIDER_CLUSTER_MIN_BUYERS)
    lookback_days = int(lookback_days or _cfg.ALERT_INSIDER_CLUSTER_LOOKBACK_DAYS)
    uni = {str(t).upper() for t in universe}
    stats: dict[str, Any] = {}
    if frame is None:
        p = Path(path or Path(_cfg.OPTIMUS_LEDGER_DIR) / "sec_insider" / "insider_events_v1.parquet")
        if not p.exists():
            return [], {"state": f"ABSENT: {p.name} not on disk"}
        cols = ["symbol", "event_time_utc", "observed_at_utc", "observed_at_basis",
                "insider_cik", "insider_trans_code", "insider_dollar_value"]
        frame = pd.read_parquet(p, columns=cols,
                                filters=[("insider_trans_code", "==", "P")])
    df = frame
    if not len(df):
        return [], {"state": "EMPTY tape"}
    obs = pd.to_datetime(df["observed_at_utc"], utc=True)
    tape_end = obs.max()
    stats["tape_ends_utc"] = tape_end.isoformat() if pd.notna(tape_end) else None
    now_ts = pd.Timestamp(now)
    keep = ((df["insider_trans_code"] == "P") & df["symbol"].astype(str).str.upper().isin(uni)
            & (obs <= now_ts) & (obs >= now_ts - pd.Timedelta(days=lookback_days)))
    d = df.loc[keep].assign(_obs=obs[keep])
    stats["purchase_rows_in_lookback"] = int(len(d))
    events = []
    for sym, g in d.groupby(d["symbol"].astype(str).str.upper()):
        n = g["insider_cik"].nunique()
        last = g["_obs"].max()
        if n < min_buyers or (now_ts - last).total_seconds() > max_age_h * 3600:
            continue
        t0 = pd.to_datetime(g["event_time_utc"], utc=True).min()
        t1 = pd.to_datetime(g["event_time_utc"], utc=True).max()
        total = float(np.nansum(g["insider_dollar_value"].to_numpy(float)))
        fact_line = (f"{n} insiders of {sym} bought shares on the open market "
                     f"(${total:,.0f}, Form 4 code P), the last filing public "
                     f"{last:%Y-%m-%d}.")
        fact = (f"{n} distinct insiders of {sym} reported open-market purchases "
                f"(Form 4, code P) totalling ${total:,.0f}, transactions dated "
                f"{t0:%Y-%m-%d} to {t1:%Y-%m-%d}, the last filing public by "
                f"{last:%Y-%m-%d %H:%M} UTC (filing date, end of day ET).")
        events.append({
            "ticker": sym, "company": sym, "source_kind": "sec_form4", "lane": "truth",
            "event_type_id": "insider_or_institutional_ownership_change",
            "event_type_candidates": ["insider_or_institutional_ownership_change"],
            "direction_prior": 1,
            "direction_prior_basis": ("open-market purchase cluster: a literature prior "
                                      "(Cohen-Malloy-Pomorski 2012), not measured here"),
            "fact": fact, "fact_line": fact_line, "fact_key": "form4_purchase_cluster",
            "n_buyers": int(n), "typing_rule_version": TYPING_RULE_VERSION,
            "headline": f"{n} insiders reported open-market purchases (${total:,.0f})",
            "source_url": (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                           f"&CIK={sym}&type=4&dateb=&owner=include&count=40"),
            "source_url_kind": "SEC EDGAR Form 4 listing",
            "observed_utc": last.to_pydatetime().isoformat(timespec="seconds"),
            "published_utc": None, "amendment": False})
    stats["events"] = len(events)
    if pd.notna(tape_end) and (now_ts - tape_end).total_seconds() > max_age_h * 3600:
        stats["state"] = (f"STALE_TAPE: the Form 4 bulk tape ends {tape_end:%Y-%m-%d}; "
                          f"no cluster can be fresh")
    else:
        stats["state"] = "OK"
    return events, stats


# ─────────────────────────── discovery confirmation ────────────────────────

def discovery_confirmations(events: list[dict], *, now: datetime,
                            root: Optional[Path] = None) -> dict:
    """Attach `confirmations` (count + first URL) from discovery-lane headlines
    whose `tickers` name the event's ticker inside the confirm window. Reads
    only; a headline never becomes an event here."""
    root = Path(root or corpus_root())
    if not events or not root.exists():
        return {"dirs_read": 0}
    before = timedelta(hours=_cfg.ALERT_CONFIRM_WINDOW_BEFORE_H)
    after = timedelta(hours=_cfg.ALERT_CONFIRM_WINDOW_AFTER_H)
    want = {e["ticker"] for e in events}
    oldest = min(_utc(e["observed_utc"]) for e in events) - before
    days = [str(oldest.date() + timedelta(days=i))
            for i in range((now.date() - oldest.date()).days + 1)]
    hits: dict[str, list[tuple[datetime, str, str]]] = defaultdict(list)
    n_dirs = 0
    for d in sorted(root.iterdir()):
        name = d.name.lower()
        if not d.is_dir() or any(s in name for s in SOCIAL_MARKERS) \
                or not name.startswith(DISCOVERY_DIR_PREFIXES):
            continue
        n_dirs += 1
        for day in days:
            for r in _read_jsonl(d / f"{day}.jsonl"):
                tks = {str(t).upper() for t in r.get("tickers") or []} & want
                if not tks:
                    continue
                t = _utc(r.get("published_utc")) or _utc(r.get("first_seen_utc"))
                if t is None:
                    continue
                for tk in tks:
                    hits[tk].append((t, d.name, str(r.get("url") or "")))
    for e in events:
        o = _utc(e["observed_utc"])
        rows = sorted(x for x in hits.get(e["ticker"], []) if o - before <= x[0] <= o + after)
        e["confirmations"] = {"n": len(rows), "sources": sorted({x[1] for x in rows}),
                              "first_url": rows[0][2] if rows else None}
    return {"dirs_read": n_dirs}


# ───────────────────────────────── the price ────────────────────────────────

def _close_instant(day: Any) -> datetime:
    t = pd.Timestamp(day).normalize() + pd.Timedelta(hours=16)
    return t.tz_localize(NY_TZ).tz_convert("UTC").to_pydatetime()


def _sessions_between(last: date, created: datetime) -> int:
    """XNYS sessions strictly after `last` whose close is at or before `created`."""
    from backend.services import market_sessions as MS
    n, day = 0, pd.Timestamp(last) + pd.Timedelta(days=1)
    while _close_instant(day) <= created and n < 60:
        if MS.is_session(day):
            n += 1
        day += pd.Timedelta(days=1)
    return n


def reaction_state(event_utc: datetime, created: datetime) -> dict:
    """Has the market traded since the event became public, as of `created`?

    MARKET_NOT_TRADED_SINCE: the event is outside a session and the next XNYS
    open after it is later than `created`; `next_open_utc` names that open.
    TRADED_NO_CLOSE_ON_DISK: a session has run since (or the event fell inside
    one), but no close after the event is on disk -- the move is still UNKNOWN.
    CANNOT_DETERMINE when the exchange calendar cannot be read."""
    from backend.services import market_sessions as MS
    try:
        nxt = MS.next_session_open(event_utc)
        in_session = bool(MS._xnys().is_open_on_minute(
            pd.Timestamp(event_utc).tz_convert("UTC").floor("min")))
    except Exception as exc:                                       # noqa: BLE001
        return {"reaction_state": f"CANNOT_DETERMINE ({type(exc).__name__})",
                "next_open_utc": None}
    nxt_iso = nxt.astimezone(timezone.utc).isoformat(timespec="seconds")
    if not in_session and nxt > created:
        return {"reaction_state": "MARKET_NOT_TRADED_SINCE", "next_open_utc": nxt_iso}
    return {"reaction_state": "TRADED_NO_CLOSE_ON_DISK", "next_open_utc": nxt_iso}


def price_context(ticker: str, created: datetime, closes: Optional[pd.Series],
                  event_utc: Optional[datetime] = None) -> dict:
    """Last close before the alert and the move over the previous 1 and 5
    sessions, in sigma of the stock's OWN daily log returns. A missing, stale or
    too-short series returns `price_state = "UNPRICED: <why>"` -- never a blank.

    `event_utc` (review 2026-09-28 F3): when the last close on disk is BEFORE
    the event became public, those moves describe the pre-event tape, so
    `move_basis = "BEFORE_EVENT"`, `already_moved = None` (UNKNOWN) and
    `reaction_state` says whether the market has traded since at all."""
    if closes is None or not len(closes):
        return {"price_state": f"UNPRICED: no bars for {ticker}"}
    s = closes.dropna().sort_index()
    s = s[[_close_instant(d) <= created for d in s.index]]
    if not len(s):
        return {"price_state": f"UNPRICED: no {ticker} bar closed before the alert"}
    last = pd.Timestamp(s.index[-1]).date()
    try:
        gap = _sessions_between(last, created)
    except Exception as exc:                                       # noqa: BLE001
        return {"price_state": f"UNPRICED: price age CANNOT BE DETERMINED ({type(exc).__name__})"}
    if gap > _cfg.ALERT_PRICE_MAX_STALE_SESSIONS:
        return {"price_state": f"UNPRICED: last {ticker} bar is {last} ({gap} sessions old)"}
    L = int(_cfg.ALERT_SIGMA_LOOKBACK_SESSIONS)
    lr = np.log(s.to_numpy(float))
    r = np.diff(lr)[-L:]
    r = r[np.isfinite(r)]
    if len(r) < 21 or len(s) < 6:
        return {"price_state": f"UNPRICED: only {len(r)} daily returns for {ticker}'s sigma"}
    sd = float(np.std(r, ddof=1))
    if not (math.isfinite(sd) and sd > 0):
        return {"price_state": f"UNPRICED: {ticker}'s daily sigma is zero or undefined"}
    z1 = float((lr[-1] - lr[-2]) / sd)
    z5 = float((lr[-1] - lr[-6]) / (sd * math.sqrt(5)))
    k = float(_cfg.ALERT_ALREADY_MOVED_SIGMA)
    out = {"price_state": "PRICED", "last_price": round(float(s.iloc[-1]), 4),
           "last_price_ts": _close_instant(last).isoformat(timespec="seconds"),
           "last_price_basis": "daily close, prices_2025_26/bars.parquet",
           "sigma_daily": round(sd, 6), "move_1s_sigma": round(z1, 2),
           "move_5s_sigma": round(z5, 2), "already_moved_threshold_sigma": k,
           "already_moved": bool(abs(z1) >= k or abs(z5) >= k),
           "move_basis": "EVENT_TIME_UNKNOWN", "reaction_state": None, "next_open_utc": None}
    if event_utc is not None:
        if _close_instant(last) < event_utc:
            out.update(move_basis="BEFORE_EVENT", already_moved=None,
                       **reaction_state(event_utc, created))
        else:
            out.update(move_basis="INCLUDES_EVENT", reaction_state="PRICED_AFTER_EVENT")
    return out


def event_time(event: dict) -> Optional[datetime]:
    """When the event became PUBLIC: the SEC acceptance time when known, else
    when a collector first saw it (never the transaction date)."""
    return _utc(event.get("published_utc")) or _utc(event.get("observed_utc"))


def source_staleness_8k(newest_first_seen_utc: Any, now: datetime, *,
                        max_filing_hours: Optional[float] = None) -> dict:
    """Is the 8-K Atom collector alive? (review 2026-09-28 F4/F9.)

    Counts EDGAR FILING HOURS (06:00-22:00 US/Eastern on XNYS session days, a
    proxy for EDGAR business days) between the newest `first_seen_utc` on disk
    and `now`. More than `ALERT_8K_SOURCE_STALE_FILING_HOURS` of them with no new
    row is STALE: a dead collector otherwise yields "0 events, OK" for ever. A
    weekend is not staleness. No row at all is STALE; an unreadable calendar is
    UNKNOWN, never OK."""
    limit = float(max_filing_hours if max_filing_hours is not None
                  else _cfg.ALERT_8K_SOURCE_STALE_FILING_HOURS)
    newest = _utc(newest_first_seen_utc)
    if newest is None:
        return {"state": "STALE", "why": "no 8-K Atom row with a first_seen_utc in the window",
                "newest_first_seen_utc": None, "filing_hours_since": None, "limit": limit}
    from zoneinfo import ZoneInfo
    from backend.services import market_sessions as MS
    et = ZoneInfo(NY_TZ)
    n = 0
    t = newest.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    try:
        while t <= now and n <= limit:
            lt = t.astimezone(et)
            if 6 <= lt.hour < 22 and lt.weekday() < 5 and MS.is_session(lt.date()):
                n += 1
            t += timedelta(hours=1)
    except Exception as exc:                                       # noqa: BLE001
        return {"state": f"UNKNOWN ({type(exc).__name__})", "why": "calendar unreadable",
                "newest_first_seen_utc": newest.isoformat(timespec="seconds"),
                "filing_hours_since": None, "limit": limit}
    stale = n > limit
    return {"state": "STALE" if stale else "OK",
            "newest_first_seen_utc": newest.isoformat(timespec="seconds"),
            "filing_hours_since": f">{limit:g}" if stale else n, "limit": limit,
            "why": (f"no new 8-K row for more than {limit:g} EDGAR filing hours" if stale
                    else "within the filing-hours limit")}


def closes_by_symbol(bars: Optional[pd.DataFrame]) -> dict[str, pd.Series]:
    if bars is None or not len(bars):
        return {}
    b = bars[["symbol", "date", "close"]].copy()
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    return {s: g.set_index("date")["close"] for s, g in b.groupby("symbol")}


def load_price_bars(*, since_days: int = 500, now: Optional[datetime] = None) -> pd.DataFrame:
    from backend.services import source_scorecard as SS
    now = now or datetime.now(timezone.utc)
    p = Path(_cfg.OPTIMUS_LEDGER_DIR) / "prices_2025_26" / "bars.parquet"
    since = str((now - timedelta(days=since_days)).date())
    return SS.load_bars([p], since=since)
