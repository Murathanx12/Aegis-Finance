"""Every paper account, one table: ROI since its own inception vs SPY over the same window.

    python -m scripts.paper_accounts_roi            # live: prod API + Alpaca GETs
    python -m scripts.paper_accounts_roi --no-chart

Writes
    backend/data/optimus/paper_accounts/roi_<date>.json   (the receipt)
    docs/PAPER_ACCOUNTS.md                               (the table, regenerated)
    docs/assets/paper_accounts_roi_<date>.png            (+ _latest.png copy)

Murat, 2026-09-26: "tell me all the paper accounts' ROI ... we have many paper
accounts so I want to see all." Before this there were six places to look and
no single number. This script READS each of them and invents nothing:

  website_lane      the ten $100k lanes, from the LIVE deploy's /api/pi/track-record
                    (fallback: the local NAV store, marked `fresh: false`)
  alpaca_fleet      hack1-hack6, GET /v2/account + /v2/positions per role; a 401 is
                    CREDENTIAL_INVALID, never $0
  pc_paper          PC-PAPER via backend.services.pc_broker.snapshot()
  night_books       backend.services.paper_books (store + marked NAV), with twins
  llm_portfolio     the frozen books.jsonl + newest leaderboard; PENDING until entry
  agency            AGENCY_BOOK:* proposals in decisions/*.json -> UNGRADED (no NAV path)
  murat_book        backend/data/murat_book.yaml, marked on the bars panel vs its
                    2026-08-11 as_of closes (a WINDOW return, not a P&L since purchase)

SPY over each row's own window comes from `learner.benchmark.spy_total_return`
(the one ruler) and the receipt carries its stamp. Broker access is GET only;
no orders, no LLM calls.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "backend" / "data" / "optimus" / "paper_accounts"
DOC_PATH = REPO / "docs" / "PAPER_ACCOUNTS.md"
ASSETS = REPO / "docs" / "assets"
PROD = "https://aegis-finance-production.up.railway.app"
TRACK_RECORD_URL = f"{PROD}/api/pi/track-record"
ALPACA_PAPER = "https://paper-api.alpaca.markets"
TERMINAL_ENV = REPO.parent / "aegis-alpha-terminal" / ".env"
LLM_DIR = REPO / "backend" / "data" / "optimus" / "llm_portfolio"
DECISIONS_DIR = REPO / "backend" / "data" / "optimus" / "decisions"
MURAT_BOOK = REPO / "backend" / "data" / "murat_book.yaml"

SCHEMA = "paper_accounts_roi/1"
STATUSES = ("LIVE", "PENDING", "RETIRED", "UNPRICED", "CREDENTIAL_INVALID", "UNGRADED",
            "VOIDED")
#: `llm_portfolio.VOID_SCHEMA`, repeated so this reader never imports the service.
VOID_SCHEMA = "llm_portfolio/void"

#: account-number -> role, from docs/ACCOUNTS_2026-09-22_THE_PAPER_FLEET.md
FLEET = ("hack1", "hack2", "hack3", "hack4", "hack5", "hack6")
RETIRED_ROLES = {"hack3": "retired 2026-09-22 (Railway loop removed); the Alpaca "
                           "account was still open with 9 positions on 09-22"}
FLEET_START_USD = 100_000.0
PC_START_USD = 1_000_000.0
PC_INCEPTION = "2026-09-22"
LANE_START_USD = 100_000.0

#: `spy_base`: whose close is the window's starting point.
#:   "inception_close"  -- the account's first mark IS a close (lanes, books,
#:                         murat's as_of): SPY sessions strictly after it.
#:   "prior_close"      -- a brokerage account funded before the open of its
#:                         inception day: SPY sessions from that day on.
BASE_AFTER = "inception_close"
BASE_BEFORE = "prior_close"

FAMILY_ORDER = ("website_lane", "alpaca_fleet", "pc_paper", "night_books",
                "night_books_twin", "murat_book", "agency",
                "llm_portfolio:personal", "llm_portfolio:competition",
                "llm_portfolio:lib", "llm_portfolio:twin")


# ───────────────────────────────── helpers ──────────────────────────────────

def _row(account: str, family: str, *, source: str, inception: Optional[str] = None,
         start_capital: Optional[float] = None, equity: Optional[float] = None,
         n_positions: Optional[int] = None, last_mark: Optional[str] = None,
         status: str = "LIVE", note: str = "", spy_base: str = BASE_AFTER,
         **extra: Any) -> dict:
    if status not in STATUSES:
        raise ValueError(f"status {status!r} not in {STATUSES}")
    roi = None
    if status == "LIVE" and equity is not None and start_capital:
        roi = (float(equity) / float(start_capital) - 1.0) * 100.0
    r = {"account": account, "family": family, "inception": inception,
         "start_capital": start_capital,
         "equity": None if equity is None else round(float(equity), 2),
         "roi_pct": None if roi is None else round(roi, 3),
         "spy_same_window_pct": None, "vs_spy_pp": None,
         "n_positions": n_positions, "last_mark": last_mark, "status": status,
         "source": source, "note": note, "spy_base": spy_base}
    r.update(extra)
    return r


def _d(x: Any) -> Optional[str]:
    if x is None:
        return None
    return pd.Timestamp(x).date().isoformat()


def next_session_after(asof: str) -> str:
    """First weekday strictly after `asof` (the llm_portfolio entry rule)."""
    return str(np.busday_offset(np.datetime64(asof, "D"), 1, roll="forward"))


# ───────────────────────────── the SPY leg ──────────────────────────────────

def load_spy(start: str):
    """The ONE ruler (learner.benchmark). Returns (Benchmark|None, error|None)."""
    from learner import benchmark as B
    try:
        return B.spy_total_return(start=start), None
    except B.BenchmarkUnavailable as e:
        return None, str(e)


def spy_window_pct(bm, inception: Optional[str], last_mark: Optional[str],
                   spy_base: str = BASE_AFTER) -> Optional[float]:
    """SPY total return (%) over the row's own window, from the benchmark series."""
    if bm is None or not inception or not last_mark:
        return None
    from learner import benchmark as B
    r = bm.returns.dropna()
    lo = pd.Timestamp(inception)
    hi = pd.Timestamp(last_mark)
    if hi < lo:
        return None
    mask = (r.index >= lo) if spy_base == BASE_BEFORE else (r.index > lo)
    sel = r[mask & (r.index <= hi)]
    if sel.empty:
        return 0.0 if hi == lo else None
    if pd.Timestamp(r.index.min()) > lo:          # series does not reach back far enough
        return None
    return (B.compound(sel, overlapping=bm.overlapping) - 1.0) * 100.0


# ───────────────────────────── 1. website lanes ─────────────────────────────

def fetch_track_record(http_get: Optional[Callable] = None) -> tuple[Optional[dict], str]:
    import requests
    get = http_get or requests.get
    try:
        resp = get(TRACK_RECORD_URL, timeout=40)
        if getattr(resp, "status_code", 200) != 200:
            return None, f"HTTP {resp.status_code}"
        return resp.json(), "ok"
    except Exception as e:  # network down, DNS, timeout: fall back, say so
        return None, f"{type(e).__name__}: {e}"[:200]


def local_track_record() -> Optional[dict]:
    """The local NAV store, for when prod is unreachable. Often empty on this PC."""
    try:
        from backend.db import get_connection, get_nav_series
        from backend.services.portfolio_intelligence.rules import (
            BOOK_LANES, CONSERVATIVE_ATR_LANES, REFERENCE_LANES, SMQ_LANES, TSMOM_LANES)
    except Exception:
        return None
    conn = get_connection()
    try:
        lanes = {}
        for lid in (*REFERENCE_LANES, *BOOK_LANES, *CONSERVATIVE_ATR_LANES,
                    *SMQ_LANES, *TSMOM_LANES):
            rows = get_nav_series(conn, lid)
            if rows:
                lanes[lid] = [{"date": r["date"], "value": r["nav"]} for r in rows]
    finally:
        conn.close()
    return {"lanes": lanes, "benchmarks": {}, "all_fresh": False} if lanes else None


def collect_lanes(tr: Optional[dict], *, fresh: bool, source: str) -> list[dict]:
    rows = []
    if not tr or not tr.get("lanes"):
        return [_row("website lanes (all ten)", "website_lane", source=source,
                     status="UNPRICED", start_capital=None,
                     note="prod track-record unreachable and the local NAV store is empty",
                     fresh=False)]
    expected = tr.get("expected_nav_date")
    for lane, pts in tr["lanes"].items():
        if not pts:
            continue
        last = pts[-1]
        note = ""
        lane_fresh = bool(fresh and tr.get("all_fresh"))
        if expected and last["date"] < expected:
            note = (f"NAV last marked {last['date']}; the deploy expected {expected} "
                    f"(all_fresh={tr.get('all_fresh')})")
            lane_fresh = False
        rows.append(_row(lane, "website_lane", source=source,
                         inception=pts[0]["date"], start_capital=LANE_START_USD,
                         equity=last["value"], n_positions=None,
                         last_mark=last["date"], note=note, fresh=lane_fresh,
                         config_version=last.get("config_version")))
    return rows


# ───────────────────────────── 2. Alpaca fleet ──────────────────────────────

def read_env_file(path: Path) -> dict:
    """Parse a .env into a dict WITHOUT exporting it and without printing values."""
    try:
        from dotenv import dotenv_values
        return {k: v for k, v in dotenv_values(path).items() if v}
    except Exception:
        return {}


def collect_fleet(env: dict, http_get: Optional[Callable] = None,
                  roles: Iterable[str] = FLEET) -> list[dict]:
    import requests
    get = http_get or requests.get
    rows = []
    for role in roles:
        n = role.replace("hack", "")
        kid, sec = env.get(f"AAT_HACK{n}_KEY_ID"), env.get(f"AAT_HACK{n}_SECRET_KEY")
        src = f"GET {ALPACA_PAPER}/v2/account + /v2/positions (AAT_HACK{n}_* in aegis-alpha-terminal/.env)"
        retired = RETIRED_ROLES.get(role, "")
        if not kid or not sec:
            rows.append(_row(role, "alpaca_fleet", source=src, start_capital=FLEET_START_USD,
                             status="CREDENTIAL_INVALID", note=("no key pair in the env file. " + retired).strip()))
            continue
        h = {"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec}
        try:
            a = get(f"{ALPACA_PAPER}/v2/account", headers=h, timeout=20)
        except Exception as e:
            rows.append(_row(role, "alpaca_fleet", source=src, start_capital=FLEET_START_USD,
                             status="UNPRICED", note=f"network: {type(e).__name__}"))
            continue
        if a.status_code in (401, 403):
            rows.append(_row(role, "alpaca_fleet", source=src, start_capital=FLEET_START_USD,
                             status="CREDENTIAL_INVALID",
                             note=(f"HTTP {a.status_code} on /v2/account -- the key is "
                                   f"revoked or wrong, NOT a $0 account. " + retired).strip()))
            continue
        if a.status_code != 200:
            rows.append(_row(role, "alpaca_fleet", source=src, start_capital=FLEET_START_USD,
                             status="UNPRICED", note=f"HTTP {a.status_code} on /v2/account"))
            continue
        acct = a.json()
        n_pos = None
        try:
            p = get(f"{ALPACA_PAPER}/v2/positions", headers=h, timeout=20)
            if p.status_code == 200:
                n_pos = len(p.json())
        except Exception:
            pass
        rows.append(_row(role, "alpaca_fleet", source=src,
                         inception=_d(acct.get("created_at")),
                         start_capital=FLEET_START_USD,
                         equity=float(acct.get("equity") or 0.0),
                         n_positions=n_pos, last_mark=None,
                         status="RETIRED" if retired else "LIVE",
                         note=retired, spy_base=BASE_BEFORE,
                         account_number=acct.get("account_number"),
                         cash=float(acct.get("cash") or 0.0),
                         last_equity=float(acct.get("last_equity") or 0.0),
                         broker_now=True))
    # A RETIRED row that still answers is priced like any other account.
    for r in rows:
        if r["status"] == "RETIRED" and r["equity"] is not None:
            r["roi_pct"] = round((r["equity"] / r["start_capital"] - 1) * 100, 3)
    return rows


# ───────────────────────────── 3. PC-PAPER ──────────────────────────────────

def collect_pc(snapshot_fn: Optional[Callable] = None) -> list[dict]:
    src = "backend.services.pc_broker.snapshot() (GET /v2/account + /v2/positions)"
    try:
        if snapshot_fn is None:
            import backend.config  # noqa: F401  (loads .env for the PC-PAPER pair)
            from backend.services import pc_broker
            # Written beside this receipt, not into pc_book/nav.jsonl: a report
            # must not add rows to the live loop's own equity curve.
            snap = pc_broker.snapshot(tag="paper_accounts_roi", out_dir=OUT_DIR / "pc_snapshot")
        else:
            snap = snapshot_fn()
    except Exception as e:
        msg = str(e)
        status = "CREDENTIAL_INVALID" if ("401" in msg or "not configured" in msg) else "UNPRICED"
        return [_row("PC-PAPER", "pc_paper", source=src, inception=PC_INCEPTION,
                     start_capital=PC_START_USD, status=status, note=msg[:200])]
    return [_row("PC-PAPER", "pc_paper", source=src, inception=PC_INCEPTION,
                 start_capital=PC_START_USD, equity=snap.get("equity"),
                 n_positions=snap.get("n_positions"), last_mark=None,
                 spy_base=BASE_BEFORE, account_number=snap.get("account_number"),
                 cash=snap.get("cash"), broker_now=True,
                 note="first trades 2026-09-25")]


# ───────────────────────────── 4. night-job paper books ─────────────────────

def collect_paper_books(books: Optional[list] = None,
                        nav: Optional[dict] = None) -> list[dict]:
    src = "backend.services.paper_books (paper_books store + paper_nav book: rows)"
    try:
        if books is None or nav is None:
            from backend.services import paper_books as PB
            books = PB.list_books() if books is None else books
            nav = PB.nav_series() if nav is None else nav
            start = PB.INCEPTION_VALUE
        else:
            start = 100_000.0
    except Exception as e:
        return [_row("paper_books store", "night_books", source=src,
                     status="UNPRICED", note=f"store unreadable: {e}"[:200])]
    titles = {b.book_id: b.strategy.title for b in books}
    rows = []
    for b in books:
        s = nav.get(b.book_id) or []
        title = (titles[b.book_id].replace("—", "-").replace("–", "-")
                 .encode("ascii", "replace").decode())
        name = f"{title[:44]} [{b.book_id[5:13]}]"
        fam = "night_books_twin" if b.is_twin else "night_books"
        kw = dict(source=src, start_capital=start,
                  graded_against=(titles.get(b.parent_id, b.parent_id)[:44] if b.is_twin
                                  else f"{len(b.control_twin_ids) or 'its'} twins"),
                  book_id=b.book_id)
        if not s:
            rows.append(_row(name, fam, inception=b.created_utc[:10], status="UNGRADED",
                             note="no paper_nav rows: the book has never been marked", **kw))
            continue
        status = "RETIRED" if b.status == "retired" else "LIVE"
        r = _row(name, fam, inception=s[0][0], equity=s[-1][1], last_mark=s[-1][0],
                 status="LIVE", note=f"{len(s)} marks", **kw)
        r["status"] = status
        rows.append(r)
    return rows


# ───────────────────────────── 5. llm_portfolio books ───────────────────────

def _newest_leaderboard(d: Path) -> tuple[Optional[dict], Optional[str]]:
    files = sorted(d.glob("leaderboard_*.json"))
    if not files:
        return None, None
    return json.loads(files[-1].read_text(encoding="utf-8")), files[-1].name


def collect_llm_books(books_path: Path = LLM_DIR / "books.jsonl",
                      leaderboard: Optional[dict] = None,
                      leaderboard_name: Optional[str] = None) -> list[dict]:
    if not books_path.exists():
        return []
    lines = [json.loads(l) for l in books_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    # A void row is not a book (llm_portfolio.void appends one; nothing is edited).
    voids: dict = {}
    for x in lines:
        if x.get("schema") == VOID_SCHEMA and x.get("book_id") not in voids:
            voids[x.get("book_id")] = x
    recs = [x for x in lines if x.get("schema") != VOID_SCHEMA]
    if leaderboard is None:
        leaderboard, leaderboard_name = _newest_leaderboard(books_path.parent)
    graded = {b["book_id"]: b for b in (leaderboard or {}).get("books", [])}
    names = {r["book_id"]: r["name"] for r in recs}
    twins_of: dict[str, list[str]] = {}
    for r in recs:
        if r.get("kind") == "twin":
            twins_of.setdefault(r.get("parent_book_id"), []).append(r.get("twin") or r["name"])
    src = (f"backend/data/optimus/llm_portfolio/books.jsonl + {leaderboard_name or 'no leaderboard'} "
           f"(python -m scripts.llm_portfolio grade --no-pull)")
    rows = []
    for r in recs:
        kind = r.get("kind")
        if kind == "twin":
            group, against = "twin", f"twin ({r.get('twin')}) of {names.get(r.get('parent_book_id'), r.get('parent_book_id'))}"
        else:
            group = "lib" if r["name"].startswith("lib_") else kind
            tw = twins_of.get(r["book_id"], [])
            against = f"{r.get('benchmark', 'SPY')}; twins: {', '.join(tw) if tw else 'none'}"
        entry = next_session_after(r["asof"])
        g = graded.get(r["book_id"], {})
        kw = dict(source=src, inception=entry, start_capital=r.get("start_capital_usd"),
                  n_positions=r.get("n_positions"), graded_against=against,
                  book_id=r["book_id"], frozen_utc=r.get("frozen_utc"), entry=entry)
        v = voids.get(r["book_id"])
        if v is not None:
            rows.append(_row(r["name"], f"llm_portfolio:{group}", status="VOIDED",
                             note=f"voided before entry ({str(v.get('voided_utc'))[:10]}, "
                                  f"{v.get('who')}): {v.get('reason')}", **kw))
            continue
        if g.get("status") not in (None, "PENDING") and g.get("nav_usd") is not None:
            rows.append(_row(r["name"], f"llm_portfolio:{group}", equity=g["nav_usd"],
                             last_mark=leaderboard.get("bars_through"), **kw))
        else:
            rows.append(_row(r["name"], f"llm_portfolio:{group}", status="PENDING",
                             note=f"PENDING (entry {entry})", **kw))
    return rows


# ───────────────────────────── 6. agency books ──────────────────────────────

def collect_agency(decisions_dir: Path = DECISIONS_DIR,
                   paper_book_ids: Iterable[str] = ()) -> list[dict]:
    files = sorted(decisions_dir.glob("20*.json"))
    if not files:
        return []
    f = files[-1]
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []
    found: dict[str, dict] = {}

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            t = o.get("ticker")
            if isinstance(t, str) and t.startswith("AGENCY_BOOK:"):
                found[t] = o
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(d)
    held = set(paper_book_ids)
    rows = []
    for t, o in sorted(found.items()):
        rows.append(_row(t, "agency",
                         source=f"backend/data/optimus/decisions/{f.name} ({t})",
                         inception=None, status="UNGRADED",
                         note=("a PROPOSAL (authority " + str(o.get("authority")) +
                               ", expected_payoff NOT CALIBRATED); no paper_books entry "
                               "holds it, so there is no NAV path to grade"
                               if t not in held else "held"),
                         policy_id=o.get("policy_id")))
    return rows


# ───────────────────────────── 7. Murat's own book ──────────────────────────

def collect_murat(book_path: Path = MURAT_BOOK, bars: Optional[pd.DataFrame] = None) -> list[dict]:
    import yaml
    src = "backend/data/murat_book.yaml x bars panel (prices_2025_26/bars.parquet) closes"
    try:
        y = yaml.safe_load(book_path.read_text(encoding="utf-8"))
    except Exception as e:
        return [_row("murat_live", "murat_book", source=src, status="UNPRICED",
                     note=f"book unreadable: {e}"[:200])]
    asof = str(y.get("as_of"))
    pos = [(p["ticker"], float(p["shares"])) for p in y.get("positions", [])]
    if bars is None:
        try:
            from backend.services import paper_books as PB
            bars = pd.read_parquet(PB._bars_path(), columns=["symbol", "date", "close"])
        except Exception as e:
            return [_row("murat_live", "murat_book", source=src, inception=asof,
                         status="UNPRICED", note=f"UNPRICED (no bars panel: {e})"[:200])]
    bars = bars[bars["symbol"].isin([t for t, _ in pos])]
    bars = bars.assign(date=pd.to_datetime(bars["date"]))
    a = pd.Timestamp(asof)
    start_v = end_v = 0.0
    priced, missing, last = [], [], None
    for t, sh in pos:
        g = bars[bars["symbol"] == t].sort_values("date")
        b0 = g[g["date"] == a]
        if b0.empty or g.empty:
            missing.append(t)
            continue
        start_v += sh * float(b0["close"].iloc[0])
        end_v += sh * float(g["close"].iloc[-1])
        last = g["date"].iloc[-1] if last is None else min(last, g["date"].iloc[-1])
        priced.append(t)
    if not priced:
        return [_row("murat_live", "murat_book", source=src, inception=asof,
                     status="UNPRICED", note="UNPRICED (no cost basis and no as_of close)")]
    note = (f"window return of the recorded share counts since as_of {asof} "
            f"(confirmed: {y.get('confirmed')}; cash unknown); NOT a P&L since purchase. "
            f"Priced {len(priced)}/{len(pos)}" + (f"; absent from the panel: {', '.join(missing)}" if missing else ""))
    return [_row("murat_live", "murat_book", source=src, inception=asof,
                 start_capital=round(start_v, 2), equity=end_v, n_positions=len(pos),
                 last_mark=_d(last), note=note, priced=priced, unpriced=missing)]


# ───────────────────────────── assembly ─────────────────────────────────────

def attach_spy(rows: list[dict], bm) -> None:
    last_session = _d(bm.returns.index.max()) if bm is not None and len(bm.returns) else None
    for r in rows:
        if r.get("broker_now") and r["last_mark"] is None:
            r["last_mark"] = last_session or date.today().isoformat()
        if r["roi_pct"] is None:
            continue
        s = spy_window_pct(bm, r["inception"], r["last_mark"], r.get("spy_base", BASE_AFTER))
        if s is not None:
            r["spy_same_window_pct"] = round(s, 3)
            r["vs_spy_pp"] = round(r["roi_pct"] - s, 3)


def aggregate(rows: list[dict]) -> dict:
    priced = [r for r in rows if r["roi_pct"] is not None and r["equity"] is not None
              and r["start_capital"]]
    non_ctrl = [r for r in priced if not r["family"].endswith("twin")]

    def agg(rs):
        eq = sum(r["equity"] for r in rs)
        st = sum(r["start_capital"] for r in rs)
        return {"n": len(rs), "sum_equity": round(eq, 2), "sum_start_capital": round(st, 2),
                "pnl": round(eq - st, 2), "roi_pct": round((eq / st - 1) * 100, 3) if st else None}

    compared = [r for r in priced if r["vs_spy_pp"] is not None]
    ahead = [r["account"] for r in compared if r["vs_spy_pp"] > 0]
    behind = [r["account"] for r in compared if r["vs_spy_pp"] <= 0]
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    by_family = {}
    for fam in FAMILY_ORDER:
        rs = [r for r in rows if r["family"] == fam]
        if rs:
            p = [r for r in rs if r in priced]
            by_family[fam] = {"n": len(rs), "n_priced": len(p),
                              **({k: v for k, v in agg(p).items() if k != "n"} if p else {})}
    ne = [r for r in compared if not r["family"].endswith("twin")]
    sentence = (f"Of {len(compared)} priced accounts with an own-window SPY leg, "
                f"{len(ahead)} are ahead of SPY and {len(behind)} behind "
                f"(excluding control twins: {sum(1 for r in ne if r['vs_spy_pp'] > 0)} ahead, "
                f"{sum(1 for r in ne if r['vs_spy_pp'] <= 0)} behind); "
                f"{counts['PENDING']} are PENDING (not yet entered), "
                f"{counts['UNGRADED']} UNGRADED, {counts['CREDENTIAL_INVALID']} CREDENTIAL_INVALID, "
                f"{counts['UNPRICED']} UNPRICED, {counts['VOIDED']} VOIDED before entry (never graded).")
    return {"all_priced": agg(priced) if priced else None,
            "priced_excluding_control_twins": agg(non_ctrl) if non_ctrl else None,
            "n_ahead_of_spy": len(ahead), "n_behind_spy": len(behind),
            "n_pending": counts["PENDING"], "status_counts": counts,
            "by_family": by_family, "honest_sentence": sentence}


def lane_series(tr: Optional[dict]) -> dict:
    if not tr:
        return {}
    out = {"lanes": {k: [[p["date"], p["value"]] for p in v] for k, v in tr.get("lanes", {}).items()}}
    spy = (tr.get("benchmarks") or {}).get("SPY") or []
    out["spy_rebased_100k_at_2026_06_08"] = [[p["date"], p["value"]] for p in spy]
    return out


def build(*, tr: Optional[dict], tr_source: str, tr_fresh: bool, fleet_env: dict,
          http_get: Optional[Callable] = None, pc_snapshot: Optional[Callable] = None,
          paper_books_args: Optional[tuple] = None, llm_books_path: Path = LLM_DIR / "books.jsonl",
          llm_leaderboard: Optional[dict] = None, decisions_dir: Path = DECISIONS_DIR,
          murat_bars: Optional[pd.DataFrame] = None, bm=None, bm_error: Optional[str] = None,
          include_fleet: bool = True, include_pc: bool = True) -> dict:
    rows: list[dict] = []
    rows += collect_lanes(tr, fresh=tr_fresh, source=tr_source)
    if include_fleet:
        rows += collect_fleet(fleet_env, http_get=http_get)
    if include_pc:
        rows += collect_pc(pc_snapshot)
    pb = collect_paper_books(*(paper_books_args or (None, None)))
    rows += pb
    rows += collect_murat(bars=murat_bars)
    rows += collect_agency(decisions_dir, [r.get("book_id") for r in pb])
    rows += collect_llm_books(llm_books_path, leaderboard=llm_leaderboard,
                              leaderboard_name="injected" if llm_leaderboard else None)
    order = {f: i for i, f in enumerate(FAMILY_ORDER)}
    rows.sort(key=lambda r: (order.get(r["family"], 99),
                             -(r["roi_pct"] if r["roi_pct"] is not None else -1e9)))
    attach_spy(rows, bm)
    receipt = {
        "schema": SCHEMA,
        "receipt": "paper_accounts_roi",
        "licence": "PRODUCT_EXPERIMENT",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {
            "website_lanes": {"source": tr_source,
                              "fresh": bool(tr_fresh and (tr or {}).get("all_fresh")),
                              "reachable": tr_fresh,
                              "expected_nav_date": (tr or {}).get("expected_nav_date"),
                              "all_fresh": (tr or {}).get("all_fresh")},
            "spy_leg": ("learner.benchmark.spy_total_return (yfinance adj close, total return)"
                        if bm is not None else f"UNAVAILABLE: {bm_error}"),
        },
        "rows": rows,
        "aggregate": aggregate(rows),
        "lane_nav_series": lane_series(tr),
        "read_me_first": ("ROI is equity / start capital - 1 over each account's OWN window; "
                          "SPY is compounded over that same window. Nothing here is a claim: "
                          "every book runs under PRODUCT_EXPERIMENT. A window of weeks cannot "
                          "separate skill from noise. PENDING books have not entered yet."),
    }
    if bm is not None:
        from learner import benchmark as B
        receipt[B.STAMP_KEY] = bm.stamp()
    return receipt


# ───────────────────────────── outputs ──────────────────────────────────────

def _f(x: Any, pct: bool = False, money: bool = False) -> str:
    if x is None:
        return "—"
    if money:
        return f"${x:,.0f}"
    if pct:
        return f"{x:+.2f}%"
    return str(x)


def render_markdown(rc: dict, png_name: Optional[str]) -> str:
    rows = rc["rows"]
    ag = rc["aggregate"]
    day = rc["generated_utc"][:10]
    L = [f"# Paper accounts — every one, ROI vs SPY over its own window ({day})", "",
         "Regenerated by `python -m scripts.paper_accounts_roi`. Receipt: "
         f"[`backend/data/optimus/paper_accounts/roi_{day}.json`](../backend/data/optimus/paper_accounts/roi_{day}.json). "
         "Served at `GET /api/pi/paper-accounts`.", "",
         "> **Nothing here is a claim.** Every account runs under `PRODUCT_EXPERIMENT`; "
         "windows of weeks cannot separate skill from noise. `mirror`'s loss is its book's "
         "real performance, left on the record on purpose.", ""]
    if png_name:
        L += [f"![ROI per paper account vs SPY over the same window](assets/{png_name})", ""]
    a = ag.get("all_priced")
    x = ag.get("priced_excluding_control_twins")
    L += ["## Aggregate", ""]
    if a:
        L.append(f"- **All priced accounts ({a['n']}):** equity **${a['sum_equity']:,.0f}** vs "
                 f"start **${a['sum_start_capital']:,.0f}** → **{a['roi_pct']:+.2f}%** "
                 f"(${a['pnl']:+,.0f}).")
    if x:
        L.append(f"- **Excluding control twins ({x['n']}):** ${x['sum_equity']:,.0f} vs "
                 f"${x['sum_start_capital']:,.0f} → **{x['roi_pct']:+.2f}%**.")
    L += [f"- {ag['honest_sentence']}", "",
          f"SPY leg: {rc['sources']['spy_leg']}. Website lanes: {rc['sources']['website_lanes']['source']} "
          f"(fresh: {rc['sources']['website_lanes']['fresh']}; deploy expected NAV date "
          f"{rc['sources']['website_lanes']['expected_nav_date']}).", ""]
    head = ("| account | family | inception | start capital | equity | ROI | SPY same window | vs SPY | positions | last mark | status | source / note |\n"
            "|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|")
    priced_fams = [f for f in FAMILY_ORDER if not f.startswith("llm_portfolio")]
    L += ["## Priced and broker accounts", "", head]
    for r in rows:
        if r["family"] not in priced_fams:
            continue
        note = r["note"] or ""
        src = r["source"].split(" (")[0]
        vs = "—" if r["vs_spy_pp"] is None else f"{r['vs_spy_pp']:+.2f} pp"
        L.append(f"| {r['account']} | {r['family']} | {_f(r['inception'])} | {_f(r['start_capital'], money=True)} | "
                 f"{_f(r['equity'], money=True)} | {_f(r['roi_pct'], pct=True)} | {_f(r['spy_same_window_pct'], pct=True)} | "
                 f"{vs} | "
                 f"{_f(r['n_positions'])} | {_f(r['last_mark'])} | **{r['status']}** | {src}{'; ' + note if note else ''} |")
    L += ["", "## `llm_portfolio` books and their twins", "",
          "Frozen 2026-09-25; entry is the OPEN of the first session after `asof`, so every one is "
          "PENDING until that session prints. Twins are the controls each parent is graded against "
          "(`ew`, `sector_etf`, `random_same_band`, `spy`).", ""]
    for fam in ("llm_portfolio:personal", "llm_portfolio:competition", "llm_portfolio:lib", "llm_portfolio:twin"):
        rs = [r for r in rows if r["family"] == fam]
        if not rs:
            continue
        L += [f"### {fam.split(':')[1]} ({len(rs)})", "",
              "| book | start capital | positions | status | graded against |", "|---|---:|---:|---|---|"]
        for r in rs:
            st = (r["note"] if r["status"] in ("PENDING", "VOIDED")
                  else f"{r['status']} {_f(r['roi_pct'], pct=True)}")
            L.append(f"| {r['account']} | {_f(r['start_capital'], money=True)} | {_f(r['n_positions'])} | {st} | {r.get('graded_against', '')} |")
        L.append("")
    vd = [r for r in rows if r["status"] == "VOIDED"]
    if vd:
        L += [f"### Voided before entry ({len(vd)}) — never graded, never counted", ""]
        L += [f"- `{r['account']}`: {r['note']}" for r in vd]
        L.append("")
    return "\n".join(L) + "\n"


def render_chart(rc: dict, path: Path) -> Optional[Path]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
    ACC, SPY_C, NEG = "#2a78d6", "#8a8984", "#eb6834"
    rows = [r for r in rc["rows"] if r["roi_pct"] is not None
            and not r["family"].startswith("llm_portfolio")]
    lanes = (rc.get("lane_nav_series") or {}).get("lanes") or {}
    n = len(rows)
    top_h = 0.28 * n + 1.6
    fig = plt.figure(figsize=(13, top_h + (5.6 if lanes else 0)), facecolor=SURF)
    if lanes:
        sf_top, sf_bot = fig.subfigures(2, 1, height_ratios=[top_h, 5.6])
        sf_top.set_facecolor(SURF)
        sf_bot.set_facecolor(SURF)
    else:
        sf_top, sf_bot = fig, None
    ax = sf_top.add_subplot(1, 1, 1)
    ax.set_facecolor(SURF)
    y = np.arange(n)[::-1]
    roi = np.array([r["roi_pct"] for r in rows])
    spy = np.array([np.nan if r["spy_same_window_pct"] is None else r["spy_same_window_pct"] for r in rows])
    ax.barh(y, roi, height=0.62, color=[ACC if v >= 0 else NEG for v in roi], zorder=3)
    ax.scatter(spy, y, marker="|", s=260, linewidths=2.2, color=INK, zorder=4, label="SPY, same window")
    labels = []
    for r in rows:
        tag = " (retired)" if r["status"] == "RETIRED" else ""
        labels.append(f"{r['account'][:40]}{tag}  ·  {r['family']}")
    ax.set_yticks(y, labels, fontsize=8, color=INK2)
    for yi, v, sv in zip(y, roi, spy):
        xe = max(v, sv) if (v >= 0 and not np.isnan(sv)) else v
        ax.text(xe + (0.3 if v >= 0 else -0.3), yi, f"{v:+.1f}%", va="center",
                ha="left" if v >= 0 else "right", fontsize=7.5, color=INK)
    ax.axvline(0, color=INK2, lw=0.8, zorder=2)
    ax.grid(axis="x", color=GRID, lw=0.6, zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_xlabel("return since the account's own inception, %", color=INK2, fontsize=9)
    fams = [r["family"] for r in rows]
    for i in range(1, n):
        if fams[i] != fams[i - 1]:
            ax.axhline(y[i] + 0.5, color=GRID, lw=1.0)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=ACC, label="account ROI (gain)"), Patch(color=NEG, label="account ROI (loss)"),
                       ax.collections[0]], loc="lower right", fontsize=8, frameon=False)
    ag = rc["aggregate"]
    a = ag.get("all_priced") or {}
    ax.set_title(f"Every priced paper account vs SPY over its own window — {rc['generated_utc'][:10]}\n"
                 f"{ag['n_ahead_of_spy']} ahead of SPY, {ag['n_behind_spy']} behind, {ag['n_pending']} pending "
                 f"(llm_portfolio books enter 2026-09-28, not shown).  Aggregate "
                 f"{a.get('roi_pct', 0):+.2f}% on ${a.get('sum_start_capital', 0):,.0f}.  No result here is a claim.",
                 loc="left", fontsize=10.5, color=INK)
    if lanes:
        spy = dict((d, v) for d, v in (rc["lane_nav_series"].get("spy_rebased_100k_at_2026_06_08") or []))
        axs = sf_bot.subplots(2, 5)
        sf_bot.subplots_adjust(hspace=0.45, wspace=0.3, top=0.9, bottom=0.1)
        for i, (lane, pts) in enumerate(lanes.items()):
            a2 = axs[i // 5, i % 5]
            a2.set_facecolor(SURF)
            d = pd.to_datetime([p[0] for p in pts])
            v = np.array([p[1] for p in pts]) / 1000.0
            sd = [p[0] for p in pts if p[0] in spy]
            if sd:
                base = spy[sd[0]]
                sp = pd.Series({pd.Timestamp(k): val / base * pts[0][1] / 1000.0
                                for k, val in spy.items() if k >= sd[0]})
                a2.plot(sp.index, sp.values, color=SPY_C, lw=1.4, label="SPY")
            a2.plot(d, v, color=ACC, lw=2, label=lane)
            a2.set_title(f"{lane}  {v[-1] / 100 - 1:+.1%}", fontsize=8.5, color=INK, loc="left")
            a2.tick_params(labelsize=7, colors=INK2)
            a2.xaxis.set_major_locator(matplotlib.dates.MonthLocator())
            a2.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b"))
            a2.grid(color=GRID, lw=0.5)
            for s in ("top", "right"):
                a2.spines[s].set_visible(False)
            if i == 0:
                a2.set_ylabel("NAV, $k", fontsize=8, color=INK2)
                a2.legend(fontsize=7, frameon=False, loc="lower left")
        sf_bot.text(0.01, 0.0, "Lower panels: the ten website lanes' NAV since inception (blue) vs SPY rebased "
                 "to each lane's first mark (gray). Source: the live /api/pi/track-record.",
                 fontsize=8, color=INK2)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, bbox_inches="tight", facecolor=SURF)
    plt.close(fig)
    return path


def write_outputs(rc: dict, *, chart: bool = True) -> dict:
    day = rc["generated_utc"][:10]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rj = OUT_DIR / f"roi_{day}.json"
    png = latest = None
    if chart:
        png = render_chart(rc, ASSETS / f"paper_accounts_roi_{day}.png")
        if png:
            latest = ASSETS / "paper_accounts_roi_latest.png"
            shutil.copyfile(png, latest)
            rc["chart"] = {"png": f"docs/assets/{png.name}", "latest": "docs/assets/paper_accounts_roi_latest.png"}
    tmp = rj.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rc, indent=1, default=str), encoding="utf-8")
    tmp.replace(rj)
    DOC_PATH.write_text(render_markdown(rc, "paper_accounts_roi_latest.png" if png else None), encoding="utf-8")
    return {"receipt": rj, "png": png, "latest": latest, "doc": DOC_PATH}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-chart", action="store_true")
    ap.add_argument("--no-broker", action="store_true", help="skip the Alpaca fleet and PC-PAPER GETs")
    a = ap.parse_args(argv)
    tr, why = fetch_track_record()
    tr_source, fresh = TRACK_RECORD_URL, True
    if tr is None:
        tr, tr_source, fresh = local_track_record(), f"local NAV store (prod unreachable: {why})", False
    bm, bm_err = load_spy("2026-05-15")
    rc = build(tr=tr, tr_source=tr_source, tr_fresh=fresh,
               fleet_env={} if a.no_broker else read_env_file(TERMINAL_ENV),
               bm=bm, bm_error=bm_err, include_fleet=not a.no_broker, include_pc=not a.no_broker)
    out = write_outputs(rc, chart=not a.no_chart)
    for r in rc["rows"]:
        if r["family"].startswith("llm_portfolio"):
            continue
        print(f"{r['account'][:46]:46s} {r['family']:17s} {r['status']:18s} "
              f"roi {_f(r['roi_pct'], pct=True):>9s}  spy {_f(r['spy_same_window_pct'], pct=True):>8s}  "
              f"eq {_f(r['equity'], money=True):>12s}")
    n_llm = sum(1 for r in rc["rows"] if r["family"].startswith("llm_portfolio"))
    print(f"+ {n_llm} llm_portfolio rows (PENDING until entry)")
    print(rc["aggregate"]["honest_sentence"])
    for k, v in out.items():
        print(f"-> {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
