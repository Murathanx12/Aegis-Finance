"""Fast-mover forensics (chunk A, 2026-09-26).

Every FORWARD position that moved >= 5% absolute, or >= 2 sigma_63, within 1 or
5 sessions of entry is a CASE. For each case this module rebuilds:

* ``state_at_entry``  -- ONLY rows stamped at or before the entry
  (``first_seen_utc`` / ``made_at`` / ``event_date`` / ``observed_at`` / a
  card's date / the catalyst file's ``built`` date). Nothing later may explain
  an earlier decision (SESSION_ORDER rule 2).
* ``ex_post_catalyst`` -- a SEPARATE column: what actually happened in
  (entry, entry + h]. It is never read by ``state_at_entry``.
* ``classify``        -- one label from ``CLASSES`` with the rule that fired
  written beside it. Deterministic rules first; a DeepSeek adjudication only
  where the rules TIE, frozen into the receipt with ``adjudicated_by``.
* matched controls    -- 3 names from the same liquidity band and sector (else
  the eligible universe), not held by the book, over the same window. A
  favourable move is credited only when it beats the control median by >= 1
  sigma_h AND the mechanism was visible at entry AND the book selected it for
  that mechanism. Everything else is ``credit: none``.

Nothing here places an order, and nothing here writes under ``sim/``.

Move conventions (printed on the receipt):
  S = the first session whose CLOSE the position was held through; R = the
  last session whose close was knowable at entry (R == S for an after-close or
  weekend decision priced at the close; R == S-1 for an intraday fill).
  ``move_h``    = close[S+h] / entry_px - 1   (what the position earned)
  ``move_cc_h`` = close[S+h] / close[R] - 1   (the window controls, the sector
                  and SPY are measured over -- apples to apples)
  sigma_1 = std of the 63 daily returns ending at R; sigma_h = sigma_1*sqrt(h).
"""
from __future__ import annotations

import glob
import hashlib
import json
import logging
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from backend import config as _cfg

logger = logging.getLogger(__name__)

LEDGER = _cfg.OPTIMUS_LEDGER_DIR
OUT_DIR = LEDGER / "forensics"
NEWS_DIR = LEDGER / "news_corpus"
PREDICTIONS = LEDGER / "predictions.jsonl"
CARDS_DIR = LEDGER / "thesis_cards"
CATALYST_GLOB = str(LEDGER / "pm_catalysts" / "catalysts_*.yaml")
REVISIONS = LEDGER / "analyst" / "target_revisions.parquet"
PI_DB = _cfg.DATA_DIR / "aegis_pi.db"
COMPANY_TICKERS = LEDGER / "edgar_8k" / "company_tickers.json"
JKP = LEDGER / "wrds" / "jkp_global_factor_usa.parquet"
CRSP_PIT = LEDGER / "crsp_pit" / "crsp_pit_monthly_v1.parquet"

CLASSES = ("PREDICTED_MECHANISM", "RIGHT_STOCK_WRONG_REASON", "SECTOR_BETA",
           "UNFORESEEABLE_NEWS", "ATTENTION_REFLEXIVITY", "ANALYST_CASCADE",
           "PRODUCT_DEMAND", "SUPPLY_CONSTRAINT", "POLICY", "OTHER")
#: Ex-post mechanisms specific enough to be their own label.
SPECIFIC = ("POLICY", "SUPPLY_CONSTRAINT", "PRODUCT_DEMAND", "ANALYST_CASCADE",
            "ATTENTION_REFLEXIVITY")
#: Classes that owe a candidate_feature line when they are a hit.
FEATURE_CLASSES = ("PREDICTED_MECHANISM", "PRODUCT_DEMAND", "SUPPLY_CONSTRAINT",
                   "POLICY")

MIN_ABS = 0.05
MIN_SIGMA = 2.0
HORIZONS = (1, 5)
SIGMA_WINDOW = 63
N_CONTROLS = 3
PRIORITY_BOOKS = ("book:b109c8861c43e3c6", "book:3b3e7049e693c3e4",
                  "book:8dbbb73b6159d61d")
ADJUDICATION_CAP_USD = 0.50
ADJUDICATION_MAX_CALLS = 25
X_QUEST_CAP = 10
X_QUEST_BUDGET_USD = 1.0
X_MODEL = "deepseek/deepseek-flash"

#: Headline lexicons, ordered by label priority (a tie is broken in this order
#: only when no adjudicator is allowed, and the receipt says so).
LEXICON: dict[str, tuple[str, ...]] = {
    "POLICY": ("tariff", "sanction", "export control", "executive order",
               "white house", "trump", "commerce department", "government",
               "pentagon", "department of defense", "department of energy",
               "subsidy", "chips act", "regulator", "antitrust", "ftc ", "doj",
               "legislation", "congress", "senate", "fda",
               "approves", "ban ", "policy", "federal"),
    "SUPPLY_CONSTRAINT": ("shortage", "supply", "capacity", "constrain",
                          "sold out", "allocation", "lead time", "price hike",
                          "raises prices", "price increase", "pricing",
                          "bottleneck", "nand", "dram", "memory price", "tight"),
    "PRODUCT_DEMAND": ("demand", "orders", "order ", "backlog", "contract",
                       "partnership", "customer",
                       "record revenue", "guidance", "raises outlook",
                       "raises forecast", "launch", "wins ", "award",
                       "bookings", "sales surge", "adoption"),
    "ANALYST_CASCADE": ("upgrade", "downgrade", "price target", "raises target",
                        "initiates", "initiated", "overweight", "outperform",
                        "buy rating", "analyst"),
    "ATTENTION_REFLEXIVITY": ("reddit", "meme", "short squeeze", "squeeze",
                              "retail trader", "wallstreetbets", "viral",
                              "trending", "social media", "retail investors"),
}

#: What a book's declared signal says it selected FOR, in mechanism terms.
SIGNAL_MECHANISM = (
    (re.compile(r"revision|analyst|target", re.I), "ANALYST_CASCADE"),
    (re.compile(r"reaction|headline|news|event", re.I), "NEWS_GENERIC"),
    (re.compile(r"attention|turnover|short_interest", re.I),
     "ATTENTION_REFLEXIVITY"),
)


# ────────────────────────────── data classes ────────────────────────────────

@dataclass
class Position:
    book: str
    family: str
    ticker: str
    direction: int                 # +1 long, -1 short
    entry_ts: str                  # ISO UTC -- the information cutoff
    entry_px: float | None
    why_selected: dict = field(default_factory=dict)
    held_by_book: tuple = ()       # every name the book held at entry
    priority: bool = False
    source: str = ""
    entry_session: str | None = None   # override S (book decisions priced at a close)

    @property
    def pid(self) -> str:
        raw = f"{self.book}|{self.ticker}|{self.entry_ts}|{self.direction}"
        return hashlib.sha1(raw.encode()).hexdigest()[:12]


@dataclass
class Case:
    case_id: str
    position: Position
    S: str
    R: str
    horizon: int                   # the triggering horizon (max |z|)
    move: float                    # close[S+h]/entry_px - 1
    move_cc: float                 # close[S+h]/close[R] - 1
    sigma_1: float | None
    sigma_h: float | None
    z: float | None
    trigger: str
    path: dict = field(default_factory=dict)   # {h: {move, move_cc, z}}
    entry_basis: str = "entry_px"
    entry_px_gap: float | None = None

    def window_end(self, sessions: Sequence[pd.Timestamp]) -> str:
        i = _idx(sessions, self.S)
        return str(pd.Timestamp(sessions[i + self.horizon]).date())


# ────────────────────────────── context ─────────────────────────────────────

@dataclass
class Context:
    """Every input, so tests can build a synthetic one and the real run can
    build it from disk. ``closes``/``volumes`` are date x symbol pivots."""
    closes: pd.DataFrame
    volumes: pd.DataFrame | None = None
    sector: dict = field(default_factory=dict)          # symbol -> sector
    features: pd.DataFrame | None = None                # (symbol,date) rows
    news: list = field(default_factory=list)            # corpus rows w/ _tickers
    revisions: pd.DataFrame | None = None
    predictions: list = field(default_factory=list)
    cards: dict = field(default_factory=dict)           # ticker -> [(date, path)]
    catalysts: list = field(default_factory=list)       # {built, date, ticker, ...}
    pit_rows: list = field(default_factory=list)        # {key, observed_at, ...}
    x_posts: dict = field(default_factory=dict)         # case_id -> quest result
    spy: str = "SPY"

    @property
    def sessions(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.closes.index)


def _idx(sessions: Sequence[pd.Timestamp], d: Any) -> int:
    idx = sessions if isinstance(sessions, pd.DatetimeIndex) else pd.DatetimeIndex(sessions)
    loc = idx.get_loc(pd.Timestamp(d))
    if not isinstance(loc, (int, np.integer)):
        raise KeyError(d)
    return int(loc)


def _utc(ts: Any) -> datetime:
    if ts is None or (isinstance(ts, float) and math.isnan(ts)):
        raise ValueError("no timestamp")
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert("UTC").to_pydatetime()


def _close_utc(d: pd.Timestamp) -> datetime:
    """16:00 America/New_York on session `d`, in UTC (DST-aware)."""
    try:
        from zoneinfo import ZoneInfo
        et = datetime.combine(pd.Timestamp(d).date(), dtime(16, 0),
                              tzinfo=ZoneInfo("America/New_York"))
        return et.astimezone(timezone.utc)
    except Exception:                                        # noqa: BLE001
        return datetime.combine(pd.Timestamp(d).date(), dtime(20, 0),
                                tzinfo=timezone.utc)


def sessions_for(pos: Position, sessions: Sequence[pd.Timestamp]
                 ) -> tuple[int, int] | None:
    """(S, R) indices. See the module docstring."""
    if pos.entry_session:
        try:
            i = _idx(sessions, pos.entry_session)
            return i, i
        except KeyError:
            return None
    t = _utc(pos.entry_ts)
    idx = sessions if isinstance(sessions, pd.DatetimeIndex) else pd.DatetimeIndex(sessions)
    i = int(idx.searchsorted(pd.Timestamp(t.date()), side="right")) - 1
    while i >= 0 and _close_utc(idx[i]) > t:
        i -= 1
    if i < 0 or (t.date() - idx[i].date()).days > 4:
        return None            # before the panel, or past its last session
    last_closed = i
    nxt = last_closed + 1
    if nxt < len(sessions) and pd.Timestamp(sessions[nxt]).date() == t.date():
        return nxt, last_closed            # intraday fill on session `nxt`
    return last_closed, last_closed        # after close / weekend


# ───────────────────────────── 1. find ──────────────────────────────────────

def _sigma(closes: pd.Series, r_idx: int) -> float | None:
    s = closes.iloc[max(0, r_idx - SIGMA_WINDOW): r_idx + 1].astype(float)
    ret = s.pct_change().dropna()
    if len(ret) < 20:
        return None
    v = float(ret.std(ddof=1))
    return v if np.isfinite(v) and v > 0 else None


def measure(pos: Position, ctx: Context, horizons: Sequence[int] = HORIZONS
            ) -> dict:
    """The priced path of one position, or the reason there is none."""
    sess = ctx.sessions
    if pos.ticker not in ctx.closes.columns:
        return {"status": "UNPRICED", "why": "symbol absent from the bars panel"}
    sr = sessions_for(pos, sess)
    if sr is None:
        return {"status": "UNPRICED", "why": "entry outside the panel's sessions"}
    S, R = sr
    col = ctx.closes[pos.ticker]
    if pd.isna(col.iloc[R]) or pd.isna(col.iloc[S]):
        return {"status": "UNPRICED", "why": "no close at the entry session"}
    sig = _sigma(col, R)
    # The position's own price is used only when the panel agrees with it: a
    # placeholder cost basis (100.0), a months-old "late entry" price or a
    # different bar vendor would otherwise manufacture a fast mover.
    ref = float(col.iloc[S] if S == R else col.iloc[R])
    tol = 0.02 if S == R else 0.15
    gap = (pos.entry_px / ref - 1.0) if pos.entry_px and pos.entry_px > 0 else None
    if gap is not None and abs(gap) <= tol:
        entry_px, basis = float(pos.entry_px), "entry_px"
    else:
        entry_px = float(col.iloc[R])
        basis = ("close_R (no entry_px)" if gap is None else
                 f"close_R (entry_px {pos.entry_px:.4g} disagrees with the panel by {gap:+.1%})")
    path = {}
    for h in horizons:
        j = S + h
        if j >= len(sess) or pd.isna(col.iloc[j]):
            continue
        mv = float(col.iloc[j]) / entry_px - 1.0
        mcc = float(col.iloc[j]) / float(col.iloc[R]) - 1.0
        sh = sig * math.sqrt(h) if sig else None
        path[h] = {"move": mv, "move_cc": mcc,
                   "z": (mcc / sh) if sh else None, "end": str(sess[j].date())}
    if not path:
        return {"status": "UNPRICED", "why": "no session after entry in the panel",
                "S": str(sess[S].date())}
    return {"status": "PRICED", "S": str(sess[S].date()), "R": str(sess[R].date()),
            "sigma_1": sig, "path": path, "entry_basis": basis,
            "entry_px_gap": None if gap is None else round(gap, 5)}


def find_fast_movers(*, min_abs: float = MIN_ABS, min_sigma: float = MIN_SIGMA,
                     horizons: Sequence[int] = HORIZONS,
                     positions: Iterable[Position] | None = None,
                     ctx: Context | None = None,
                     coverage: dict | None = None) -> list[Case]:
    """Every position whose |move| >= min_abs or >= min_sigma * sigma_h within
    one of `horizons` sessions of entry. `coverage` (if given) collects the
    priced/unpriced counts so the receipt can print the denominator."""
    if ctx is None or positions is None:
        positions, ctx = build_real_inputs()
    cases: list[Case] = []
    cov = coverage if coverage is not None else {}
    for pos in positions:
        m = measure(pos, ctx, horizons)
        fam = cov.setdefault(pos.family, {"positions": 0, "priced": 0,
                                          "unpriced": {}, "cases": 0})
        fam["positions"] += 1
        if m["status"] != "PRICED":
            fam["unpriced"][m["why"]] = fam["unpriced"].get(m["why"], 0) + 1
            continue
        fam["priced"] += 1
        best, trig = None, ""
        for h, p in m["path"].items():
            sh = m["sigma_1"] * math.sqrt(h) if m["sigma_1"] else None
            hit_abs = abs(p["move"]) >= min_abs
            hit_sig = sh is not None and abs(p["move_cc"]) >= min_sigma * sh
            if hit_abs or hit_sig:
                score = abs(p["z"]) if p["z"] is not None else abs(p["move"]) / 0.02
                if best is None or score > best[0]:
                    best = (score, h)
                    trig = "+".join(t for t, ok in (("abs", hit_abs),
                                                    ("sigma", hit_sig)) if ok)
        if best is None:
            continue
        h = best[1]
        p = m["path"][h]
        sh = m["sigma_1"] * math.sqrt(h) if m["sigma_1"] else None
        fam["cases"] += 1
        cases.append(Case(
            case_id=f"{pos.pid}-h{h}", position=pos, S=m["S"], R=m["R"],
            horizon=h, move=p["move"], move_cc=p["move_cc"],
            sigma_1=m["sigma_1"], sigma_h=sh, z=p["z"], trigger=trig,
            path={str(k): v for k, v in m["path"].items()},
            entry_basis=m["entry_basis"], entry_px_gap=m["entry_px_gap"]))
    return cases


# ─────────────────────────── helpers over text ──────────────────────────────

def lexicon_hits(texts: Iterable[str]) -> dict[str, int]:
    out = {k: 0 for k in LEXICON}
    for t in texts:
        low = f" {str(t).lower()} "
        for cls, words in LEXICON.items():
            if any(w in low for w in words):
                out[cls] += 1
    return out


def _news_for(ctx: Context, ticker: str) -> list[dict]:
    return [r for r in ctx.news if ticker in (r.get("_tickers") or ())]


def _dt_or_none(v: Any) -> datetime | None:
    try:
        return _utc(v)
    except Exception:                                        # noqa: BLE001
        return None


# ─────────────────────────── 2. state at entry ──────────────────────────────

def state_at_entry(case: Case, ctx: Context) -> dict:
    """Rebuilt ONLY from rows stamped <= the entry. Every block names its PIT
    column so a reader can audit the cut."""
    pos = case.position
    t = _utc(pos.entry_ts)
    tk = pos.ticker
    sess = ctx.sessions
    out: dict[str, Any] = {"cutoff_utc": t.isoformat(), "ticker": tk}

    # ranker features at R (the last close knowable at entry)
    if ctx.features is not None and not ctx.features.empty:
        f = ctx.features
        rows = f[(f["symbol"] == tk) & (f["date"] <= pd.Timestamp(case.R))]
        if len(rows):
            r = rows.sort_values("date").iloc[-1]
            keep = [c for c in ("mom_21", "mom_63", "mom_252_21", "rev_5",
                                "vol_21", "vol_63", "median_dollar_vol",
                                "turnover_surge", "px_vs_52w_high", "amihud",
                                "beta_63") if c in r.index]
            out["ranker_features"] = {"date": str(pd.Timestamp(r["date"]).date()),
                                      **{c: _num(r[c]) for c in keep}}
        else:
            out["ranker_features"] = "none_at_entry"
    else:
        out["ranker_features"] = "unavailable"

    # revision flow, 90d, event_date <= t
    rev = ctx.revisions
    if rev is not None and not rev.empty:
        rr = rev[(rev["ticker"] == tk)]
        ev = pd.to_datetime(rr["event_date"], utc=True, errors="coerce")
        rr = rr[(ev <= pd.Timestamp(t)) & (ev > pd.Timestamp(t) - pd.Timedelta(days=90))]
        raises = int((rr["target_action"].astype(str).str.lower() == "raises").sum())
        lowers = int((rr["target_action"].astype(str).str.lower() == "lowers").sum())
        ups = int((rr["action"].astype(str).str.lower() == "up").sum())
        downs = int((rr["action"].astype(str).str.lower() == "down").sum())
        firms = sorted(set(rr["firm"].dropna().astype(str)))
        out["revision_flow_90d"] = {
            "pit_column": "event_date", "n_rows": int(len(rr)),
            "raises": raises, "lowers": lowers, "net_raises": raises - lowers,
            "upgrades": ups, "downgrades": downs, "n_firms": len(firms),
            "firms": firms[:15],
            "median_target_change": _num(rr["target_change"].median())
            if len(rr) else None}
    else:
        out["revision_flow_90d"] = "unavailable"

    # forecasts made <= t
    fc = [p for p in ctx.predictions if p.get("ticker") == tk
          and (_dt_or_none(p.get("made_at")) or t + timedelta(1)) <= t]
    out["forecasts"] = {
        "pit_column": "made_at", "n": len(fc),
        "latest": [{k: p.get(k) for k in ("made_at", "observable", "probability",
                                          "threshold", "horizon_days",
                                          "specialist", "thesis")}
                   for p in sorted(fc, key=lambda p: p.get("made_at") or "")[-5:]]}

    # thesis card dated <= entry date
    cards = [(d, p) for d, p in ctx.cards.get(tk, []) if d <= t.date().isoformat()]
    out["thesis_card"] = ({"date": cards[-1][0], "path": cards[-1][1]}
                          if cards else "none_at_entry")

    # news first_seen <= t
    pre = [r for r in _news_for(ctx, tk)
           if (_dt_or_none(r.get("first_seen_utc")) or t + timedelta(1)) <= t]
    pre.sort(key=lambda r: r.get("first_seen_utc") or "", reverse=True)
    out["news_pre_entry"] = {
        "pit_column": "first_seen_utc", "count": len(pre),
        "lexicon": lexicon_hits(r.get("title", "") for r in pre),
        "top5": [{"first_seen_utc": r.get("first_seen_utc"),
                  "source": r.get("source"), "title": (r.get("title") or "")[:160]}
                 for r in pre[:5]]}

    # X posts (dated <= entry) from an OpenClaw quest, if one ran
    q = ctx.x_posts.get(case.case_id) or ctx.x_posts.get(tk)
    if q is None:
        out["x_posts"] = "not_queried"
    else:
        posts = [p for p in q.get("posts", []) if p.get("date") and
                 str(p["date"])[:10] <= t.date().isoformat()]
        out["x_posts"] = {"pit_column": "post date (as returned by OpenClaw)",
                          "count": len(posts), "top3": posts[:3],
                          "dropped_post_entry": q.get("dropped_post_entry", 0),
                          "quest_status": q.get("status")}

    out["search_attention"] = "unavailable (no search-attention column exists in the repo's data)"

    # insider / holder rows observed <= t
    ins = [r for r in ctx.pit_rows
           if str(r.get("key", "")).endswith(f":{tk}")
           and (_dt_or_none(r.get("observed_at")) or t + timedelta(1)) <= t]
    latest: dict[str, dict] = {}
    for r in sorted(ins, key=lambda r: r.get("observed_at") or ""):
        latest[str(r["key"]).split(":")[0]] = r
    out["insider_holder"] = {"pit_column": "observed_at",
                             "latest_by_kind": {k: {"observed_at": v.get("observed_at"),
                                                    "value": v.get("value"),
                                                    "payload": v.get("payload")}
                                                for k, v in latest.items()}}

    # catalyst calendar entries known <= t (the file's `built` date)
    cat = [c for c in ctx.catalysts
           if str(c.get("ticker")) == tk and str(c.get("built", "9999")) <= t.date().isoformat()]
    out["catalysts_known"] = cat or "none_known_at_entry"

    # sector / SPY over the same window (the window is the case's, but the
    # value is a MARKET fact of the window; it is here so a reader sees the
    # position's move beside the tide -- it is NOT evidence at entry, and
    # classify() reads it from ex_post_catalyst, never from here)
    out["why_selected"] = pos.why_selected
    out["regime_at_entry"] = _spy_trend(ctx, case.R)
    return out


def _spy_trend(ctx: Context, R: str) -> dict:
    if ctx.spy not in ctx.closes.columns:
        return {"spy_mom_21": None}
    s = ctx.closes[ctx.spy]
    i = _idx(ctx.sessions, R)
    if i < 21 or pd.isna(s.iloc[i]) or pd.isna(s.iloc[i - 21]):
        return {"spy_mom_21": None}
    return {"spy_mom_21": round(float(s.iloc[i] / s.iloc[i - 21] - 1), 5)}


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 6) if np.isfinite(f) else None


# ─────────────────────────── 3. ex-post catalyst ────────────────────────────

def _window_move(ctx: Context, sym: str, R: str, S: str, h: int) -> float | None:
    if sym not in ctx.closes.columns:
        return None
    sess = ctx.sessions
    i_r, i_s = _idx(sess, R), _idx(sess, S)
    j = i_s + h
    if j >= len(sess):
        return None
    a, b = ctx.closes[sym].iloc[i_r], ctx.closes[sym].iloc[j]
    if pd.isna(a) or pd.isna(b) or a <= 0:
        return None
    return float(b / a - 1.0)


def sector_move(case: Case, ctx: Context) -> dict:
    sec = ctx.sector.get(case.position.ticker)
    if not sec:
        return {"sector": None, "sector_ew_move": None, "n": 0}
    peers = [s for s, v in ctx.sector.items()
             if v == sec and s != case.position.ticker and s in ctx.closes.columns]
    if ctx.features is not None and not ctx.features.empty and "eligible" in ctx.features:
        f = ctx.features
        ok = set(f[(f["date"] == pd.Timestamp(case.R)) & f["eligible"]]["symbol"])
        if ok:
            peers = [p for p in peers if p in ok]
    mv = [m for m in (_window_move(ctx, p, case.R, case.S, case.horizon)
                      for p in peers) if m is not None]
    return {"sector": sec, "sector_ew_move": float(np.mean(mv)) if mv else None,
            "n": len(mv)}


def ex_post_catalyst(case: Case, ctx: Context) -> dict:
    """What actually happened in (entry, S+h]. Never read by state_at_entry."""
    pos = case.position
    t = _utc(pos.entry_ts)
    sess = ctx.sessions
    end_day = pd.Timestamp(sess[_idx(sess, case.S) + case.horizon])
    t_end = _close_utc(end_day)
    rows: list[dict] = []
    public_unseen: list[dict] = []
    known_not_to_us = 0
    for r in _news_for(ctx, pos.ticker):
        fs = _dt_or_none(r.get("first_seen_utc"))
        pub = _dt_or_none(r.get("published_utc"))
        if fs is None or not (t < fs <= t_end):
            continue
        if pub is not None and pub <= t:
            known_not_to_us += 1          # public before entry, seen by us later
            public_unseen.append(r)
            continue
        rows.append(r)
    rows.sort(key=lambda r: r.get("first_seen_utc") or "")
    titles = [r.get("title", "") for r in rows]
    filings = [r for r in rows if "8-K" in str(r.get("title", ""))
               or "sec_edgar" in str(r.get("source", ""))]
    earnings = [r for r in rows if re.search(r"earning|results|quarter|q[1-4] ",
                                             str(r.get("title", "")).lower())]
    # revisions in the window
    rev_block: dict[str, Any] = {"n_firms_up": 0, "n_firms_down": 0, "firms": []}
    if ctx.revisions is not None and not ctx.revisions.empty:
        rr = ctx.revisions[ctx.revisions["ticker"] == pos.ticker]
        ev = pd.to_datetime(rr["event_date"], utc=True, errors="coerce")
        rr = rr[(ev > pd.Timestamp(t)) & (ev <= pd.Timestamp(t_end))]
        up = rr[(rr["target_action"].astype(str).str.lower() == "raises")
                | (rr["action"].astype(str).str.lower() == "up")]
        dn = rr[(rr["target_action"].astype(str).str.lower() == "lowers")
                | (rr["action"].astype(str).str.lower() == "down")]
        rev_block = {"n_firms_up": int(up["firm"].nunique()),
                     "n_firms_down": int(dn["firm"].nunique()),
                     "firms": sorted(set(rr["firm"].dropna().astype(str)))[:10]}
    # volume surge in the window vs the 63 sessions before R
    vol_ratio = None
    if ctx.volumes is not None and pos.ticker in ctx.volumes.columns:
        v = ctx.volumes[pos.ticker]
        i_r, i_s = _idx(sess, case.R), _idx(sess, case.S)
        base = v.iloc[max(0, i_r - SIGMA_WINDOW): i_r + 1].median()
        win = v.iloc[i_s: i_s + case.horizon + 1].max()
        if base and np.isfinite(base) and base > 0 and np.isfinite(win):
            vol_ratio = float(win / base)
    sm = sector_move(case, ctx)
    return {
        "window": {"from_utc": t.isoformat(), "to_utc": t_end.isoformat()},
        "news_count": len(rows),
        "news_top5": [{"first_seen_utc": r.get("first_seen_utc"),
                       "published_utc": r.get("published_utc"),
                       "source": r.get("source"),
                       "title": (r.get("title") or "")[:160]} for r in rows[:5]],
        "published_before_entry_seen_after": known_not_to_us,
        # PUBLIC before entry but first seen by the corpus after it: neither
        # state (we did not have it) nor catalyst (it was not news in the
        # window). Printed so a reader can ask "was it knowable to the world?"
        "public_before_entry_unseen_top3": [
            {"published_utc": r.get("published_utc"), "first_seen_utc": r.get("first_seen_utc"),
             "title": (r.get("title") or "")[:160]}
            for r in sorted(public_unseen, key=lambda r: r.get("published_utc") or "",
                            reverse=True)[:3]],
        "lexicon": lexicon_hits(titles),
        "filings_8k": len(filings), "earnings_rows": len(earnings),
        "revisions_in_window": rev_block,
        "volume_ratio_vs_63d_median": _num(vol_ratio),
        **sm,
        "spy_move": _window_move(ctx, ctx.spy, case.R, case.S, case.horizon),
    }


# ─────────────────────────── 5. matched controls ────────────────────────────

def matched_controls(case: Case, ctx: Context, n: int = N_CONTROLS) -> dict:
    """n names, same liquidity band and sector at R, not held by the book."""
    from backend.services.xs_ranker import liquidity_band
    pos = case.position
    held = set(pos.held_by_book) | {pos.ticker, ctx.spy}
    f = ctx.features
    band = None
    pool: list[str] = []
    basis = "eligible_universe"
    if f is not None and not f.empty:
        day = f[f["date"] == pd.Timestamp(case.R)]
        if "eligible" in day:
            day = day[day["eligible"].astype(bool)]
        me = f[(f["symbol"] == pos.ticker) & (f["date"] <= pd.Timestamp(case.R))]
        if len(me) and "median_dollar_vol" in me:
            band = liquidity_band(_num(me.sort_values("date").iloc[-1]["median_dollar_vol"]))
        if band and "median_dollar_vol" in day:
            day = day.assign(_band=day["median_dollar_vol"].map(
                lambda v: liquidity_band(_num(v))))
            same_band = day[day["_band"] == band]
        else:
            same_band = day
        sec = ctx.sector.get(pos.ticker)
        cand = [s for s in same_band["symbol"] if s not in held]
        if sec:
            cs = [s for s in cand if ctx.sector.get(s) == sec]
            if len(cs) >= n:
                pool, basis = cs, f"band={band} & sector={sec}"
        if not pool:
            pool, basis = cand, f"band={band} (sector unmapped or too thin)"
    if not pool:
        pool = [s for s in ctx.closes.columns if s not in held]
        basis = "any priced name (no feature rows)"
    seed = int(hashlib.sha1(case.case_id.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    order = list(sorted(pool))
    rng.shuffle(order)
    moves: dict[str, float] = {}
    for s in order:                      # first n with a priced window
        m = _window_move(ctx, s, case.R, case.S, case.horizon)
        if m is not None:
            moves[s] = m
        if len(moves) >= n:
            break
    med = float(np.median(list(moves.values()))) if moves else None
    return {"basis": basis, "band": band, "names": moves, "median": med,
            "seed": seed}


def credit(case: Case, cls: str, predicted: bool, selected_for: bool,
           controls: dict) -> dict:
    d = case.position.direction
    fav = d * case.move > 0
    if not fav:
        return {"credit": "n/a", "why": "adverse move -- a loss, studied not credited"}
    med = controls.get("median")
    if med is None or not case.sigma_h:
        return {"credit": "none", "why": "no control median or no sigma: cannot beat what was not measured"}
    edge = d * (case.move_cc - med)
    beats = edge >= case.sigma_h
    if not beats:
        return {"credit": "none",
                "why": f"did not beat the control median by 1 sigma_h "
                       f"(edge {edge:+.2%} < {case.sigma_h:.2%})"}
    if predicted and selected_for and cls in FEATURE_CLASSES + ("ANALYST_CASCADE",
                                                                 "ATTENTION_REFLEXIVITY"):
        return {"credit": "credited",
                "why": f"beat controls by {edge:+.2%} >= {case.sigma_h:.2%}, and "
                       f"the mechanism was visible at entry AND was why it was held"}
    return {"credit": "none",
            "why": f"accidental: beat controls by {edge:+.2%} but the mechanism "
                   f"was {'visible' if predicted else 'not visible'} at entry and "
                   f"{'was' if selected_for else 'was not'} the reason it was held"}


# ─────────────────────────── 4. classify ────────────────────────────────────

def _selected_mechanisms(pos: Position) -> set[str]:
    ws = pos.why_selected or {}
    if ws.get("is_twin"):
        return set()                     # a control twin selected nothing FOR anything
    text = " ".join(str(ws.get(k, "")) for k in ("signal", "thesis", "reason",
                                                 "rationale"))
    out = {m for rx, m in SIGNAL_MECHANISM if rx.search(text)}
    thesis = " ".join(str(ws.get(k, "")) for k in ("thesis", "reason", "rationale"))
    if thesis.strip():
        out |= {k for k, v in lexicon_hits([thesis]).items() if v}
    return out


def _pre_seen(M: str, state: dict, case: Case) -> tuple[bool, str]:
    d = 1 if case.move_cc > 0 else -1
    news = state.get("news_pre_entry") or {}
    lex = news.get("lexicon") or {}
    fc = (state.get("forecasts") or {}).get("latest") or []
    fc_text = lexicon_hits(str(p.get("thesis") or "") for p in fc)
    if M in LEXICON and (lex.get(M, 0) or fc_text.get(M, 0)):
        return True, f"pre-entry headline/forecast text matched the {M} lexicon"
    if M == "ANALYST_CASCADE":
        rf = state.get("revision_flow_90d")
        if isinstance(rf, dict) and d * rf.get("net_raises", 0) >= 2:
            return True, f"net_raises_90d={rf['net_raises']} in the move's direction at entry"
    if M == "ATTENTION_REFLEXIVITY":
        rk = state.get("ranker_features")
        if isinstance(rk, dict) and (rk.get("turnover_surge") or 0) >= 2:
            return True, f"turnover_surge={rk['turnover_surge']} at entry"
    for p in fc:
        obs, pr = p.get("observable"), p.get("probability")
        if pr is None:
            continue
        if obs in ("return_sign", "beats_benchmark") and (pr - 0.5) * d > 0.05:
            return True, f"forecast made {p.get('made_at')} ({obs} p={pr}) pointed the move's way"
        if obs == "abs_move_exceeds" and pr >= 0.5 and abs(case.move) >= (p.get("threshold") or 1):
            return True, f"forecast made {p.get('made_at')} expected |move| > {p.get('threshold')}"
    if isinstance(state.get("catalysts_known"), list) and state["catalysts_known"]:
        return True, "a catalyst was on the calendar at entry"
    return False, "no pre-entry row names this mechanism"


def classify(case: Case, state: dict | None = None, ex_post: dict | None = None,
             controls: dict | None = None, ctx: Context | None = None, *,
             adjudicate: Any = None) -> dict:
    """One label from CLASSES and the rule that produced it.

    Order: SECTOR_BETA -> the ex-post mechanism M (headline lexicon, window
    revisions, volume) -> was M visible at entry (state_at_entry only) -> was
    M why the book held it. `adjudicate` is a callable(case, tied, ex_post) ->
    label used ONLY when the lexicon ties; None breaks the tie by LEXICON order
    and says so.
    """
    if ctx is not None:
        state = state if state is not None else state_at_entry(case, ctx)
        ex_post = ex_post if ex_post is not None else ex_post_catalyst(case, ctx)
        controls = controls if controls is not None else matched_controls(case, ctx)
    state, ex_post, controls = state or {}, ex_post or {}, controls or {}
    sh = case.sigma_h or abs(case.move_cc) / 2 or 0.01
    mv = case.move_cc
    out: dict[str, Any] = {"adjudicated_by": "rules"}

    # R1 sector / tide
    bench, bench_name = ex_post.get("sector_ew_move"), "sector_ew"
    if bench is None or (ex_post.get("n") or 0) < 5:
        bench, bench_name = controls.get("median"), "control_median"
    if (bench is not None and np.sign(bench) == np.sign(mv)
            and abs(bench) >= 0.5 * abs(mv) and abs(mv - bench) < sh):
        out.update(label="SECTOR_BETA", predicted=False, selected_for=False,
                   mechanism="SECTOR_BETA",
                   rule=f"R1: {bench_name} moved {bench:+.2%} vs position "
                        f"{mv:+.2%}; residual {mv - bench:+.2%} < 1 sigma_h ({sh:.2%})")
        return out

    # R2 the ex-post mechanism M
    lex = dict(ex_post.get("lexicon") or {})
    rv = ex_post.get("revisions_in_window") or {}
    n_same = rv.get("n_firms_up", 0) if mv > 0 else rv.get("n_firms_down", 0)
    if n_same >= 2:
        lex["ANALYST_CASCADE"] = lex.get("ANALYST_CASCADE", 0) + n_same
    n_news = ex_post.get("news_count", 0) or 0
    top = max(lex.values()) if lex else 0
    tied = [k for k in LEXICON if lex.get(k, 0) == top and top > 0]
    if top > 0:
        if len(tied) > 1 and adjudicate is not None:
            M = adjudicate(case, tied, ex_post)
            if M not in tied:
                M = tied[0]
                out["adjudicated_by"] = "rules (adjudicator returned an off-list label)"
            else:
                out["adjudicated_by"] = "deepseek via llm_analyzer (frozen in receipt)"
        else:
            M = tied[0]
        m_rule = (f"R2: ex-post lexicon {({k: v for k, v in lex.items() if v})}"
                  + (f"; tie {tied} broken by "
                     f"{'adjudicator' if adjudicate else 'LEXICON order'}"
                     if len(tied) > 1 else ""))
    elif n_news > 0:
        M, m_rule = "NEWS_GENERIC", f"R2: {n_news} ticker headline(s) in window, no lexicon class"
    elif (ex_post.get("volume_ratio_vs_63d_median") or 0) >= 3:
        M, m_rule = ("ATTENTION_REFLEXIVITY",
                     f"R2: no headline; volume {ex_post['volume_ratio_vs_63d_median']:.1f}x "
                     f"the 63d median")
    else:
        M, m_rule = "NONE", "R2: no ticker headline, no revision cluster, no volume surge in window"

    # R3 visible at entry?  R4 why it was held?
    predicted, p_rule = _pre_seen(M, state, case) if M != "NONE" else (False, "")
    sel = _selected_mechanisms(case.position)
    selected_for = M in sel
    fav = case.position.direction * case.move > 0
    if M == "NONE":
        label, rule = "OTHER", m_rule + " -> OTHER (drift with no catalyst the corpus saw)"
    elif predicted and selected_for:
        label = M if M in SPECIFIC else "PREDICTED_MECHANISM"
        rule = f"{m_rule}; R3 {p_rule}; R4 book selected for {M}"
    elif predicted and fav:
        label = "RIGHT_STOCK_WRONG_REASON"
        rule = (f"{m_rule}; R3 {p_rule}; R4 book selected for "
                f"{sorted(sel) or 'a price/score signal'}, not {M}")
    elif M == "NEWS_GENERIC":
        label = "UNFORESEEABLE_NEWS"
        rule = f"{m_rule}; R3 {p_rule or 'nothing at entry named it'}"
    else:
        label = M
        rule = f"{m_rule}; R3 {p_rule or 'not visible at entry'}"
    out.update(label=label, mechanism=M, predicted=bool(predicted),
               selected_for=bool(selected_for), rule=rule)
    return out


def candidate_feature(case: Case, cls: dict, state: dict) -> dict | None:
    """A PIT feature line for chunk C/D, for hits in FEATURE_CLASSES."""
    if cls["label"] not in FEATURE_CLASSES:
        return None
    M = cls.get("mechanism") or cls["label"]
    if M in LEXICON:
        return {"name": f"news_{M.lower()}_count_7d",
                "pit_rule": f"count of corpus rows tagged to the ticker with "
                            f"first_seen_utc in (t-7d, t] whose title matches the "
                            f"{M} lexicon (fast_mover_forensics.LEXICON)",
                "source_column": "news_corpus/<source>/<date>.jsonl: tickers, title, first_seen_utc",
                "observable_pre_entry": bool(cls.get("predicted"))}
    if M == "NEWS_GENERIC":
        return {"name": "forecast_p_direction_at_entry",
                "pit_rule": "latest predictions.jsonl row for the ticker with made_at <= t; "
                            "return_sign/beats_benchmark probability - 0.5",
                "source_column": "predictions.jsonl: ticker, made_at, observable, probability",
                "observable_pre_entry": bool(cls.get("predicted"))}
    return {"name": "catalyst_in_window_known",
            "pit_rule": "1 if a pm_catalysts row with built <= t has date in (t, t+h]",
            "source_column": "pm_catalysts/catalysts_*.yaml: built, date, ticker",
            "observable_pre_entry": bool(cls.get("predicted"))}


# ─────────────────────────── adjudication ───────────────────────────────────

class Adjudicator:
    """DeepSeek via llm_analyzer, only on lexicon ties, capped and frozen."""

    def __init__(self, cap_usd: float = ADJUDICATION_CAP_USD,
                 max_calls: int = ADJUDICATION_MAX_CALLS) -> None:
        self.cap_usd, self.max_calls = cap_usd, max_calls
        self.calls: list[dict] = []

    def __call__(self, case: Case, tied: list[str], ex_post: dict) -> str:
        if len(self.calls) >= self.max_calls:
            return tied[0]
        from backend.services import llm_analyzer as LA
        system = ("You label why a stock moved. Answer with EXACTLY one label from "
                  "the list given, nothing else. Output language: English.")
        heads = "\n".join(f"- {h['title']}" for h in ex_post.get("news_top5", []))
        user = (f"Ticker {case.position.ticker} moved {case.move_cc:+.1%} over "
                f"{case.horizon} session(s). Headlines in the window:\n{heads}\n\n"
                f"Labels: {', '.join(tied)}\nWhich label best explains the move?")
        reply = LA._call_llm(system, user, purpose="fast_mover_forensics:adjudicate") or ""
        lab = next((t for t in tied if t in reply.upper()), tied[0])
        self.calls.append({"case_id": case.case_id, "tied": tied,
                           "prompt_sha": hashlib.sha1((system + user).encode()).hexdigest()[:16],
                           "reply": reply[:200], "label": lab})
        return lab


# ─────────────────────────── X quests (OpenClaw) ────────────────────────────

def x_quest(ticker: str, entry_ts: str, *, workdir: Path) -> dict:
    """Ask OpenClaw for X posts about `ticker` DATED BEFORE entry. Posts dated
    after the entry are dropped here, not trusted to the prompt."""
    from backend.services import openclaw_client as OC
    t = _utc(entry_ts)
    lo = (t - timedelta(days=7)).date().isoformat()
    hi = t.date().isoformat()
    until = (t + timedelta(days=1)).date().isoformat()
    msg = (
        f"Use the browser tool with the logged-in X/Twitter account. Open "
        f"https://x.com/search?q=%24{ticker}%20since%3A{lo}%20until%3A{until}&f=live "
        f"and read the results (scroll once or twice). Reply with ONLY one JSON "
        f"object, no prose: "
        f'{{"searched": true|false, "blocker": "<why not, or empty>", '
        f'"posts": [{{"date": "YYYY-MM-DD", "author": "@handle", '
        f'"text": "first 200 chars", "url": "..."}}]}}. '
        f"Up to 10 posts, ONLY posts dated on or before {hi}. If the page needs "
        f"a login, is rate-limited or empty, set searched accordingly and say so "
        f"in blocker.")
    workdir.mkdir(parents=True, exist_ok=True)
    mf = workdir / f"x_{ticker}_{hi}.txt"
    mf.write_text(msg, encoding="utf-8")
    r = OC.agent(str(mf), model=X_MODEL, timeout=420.0,
                 purpose=f"fast_mover_forensics:x:{ticker}")
    posts, raw, searched, blocker = [], r.get("reply") or "", None, None
    try:
        obj = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        searched, blocker = obj.get("searched"), obj.get("blocker")
        posts = [p for p in obj.get("posts") or [] if isinstance(p, dict)]
    except ValueError:
        try:
            posts = [p for p in json.loads(raw[raw.index("["): raw.rindex("]") + 1])
                     if isinstance(p, dict)]
        except ValueError:
            posts = []
    keep = [p for p in posts if str(p.get("date", ""))[:10] and str(p["date"])[:10] <= hi]
    return {"status": r.get("status"), "posts": keep, "searched": searched,
            "blocker": blocker,
            "dropped_post_entry": len(posts) - len(keep),
            "n_returned": len(posts), "call_id": r.get("call_id"),
            "usage": r.get("usage"), "openclaw_cost_usd": r.get("openclaw_cost_usd"),
            "window": [lo, hi], "reply_head": raw[:300]}


# ─────────────────────────── real inputs ────────────────────────────────────

def _book_positions() -> list[Position]:
    from backend.db import get_connection
    from backend.services import paper_books as PB
    books = {b.book_id: b for b in PB.list_books()}
    c = get_connection()
    try:
        dec = {}
        for r in c.execute("SELECT book_id, decided_utc, asof_date, weights_json, note "
                           "FROM paper_book_decisions ORDER BY id"):
            dec.setdefault(r["book_id"], dict(r))
        rows = c.execute("SELECT portfolio_id, ticker, shares, cost_basis, opened_at "
                         "FROM paper_positions WHERE portfolio_id LIKE 'book:%'").fetchall()
    finally:
        c.close()
    held: dict[str, list[str]] = {}
    for r in rows:
        if r["ticker"] != "$CASH":
            held.setdefault(r["portfolio_id"], []).append(r["ticker"])
    out = []
    for r in rows:
        if r["ticker"] == "$CASH":
            continue
        bid = r["portfolio_id"]
        b = books.get(bid)
        d = dec.get(bid) or {}
        note = json.loads(d.get("note") or "{}") if d else {}
        w = json.loads(d.get("weights_json") or "{}") if d else {}
        rank = (sorted(w, key=lambda k: -w[k]).index(r["ticker"]) + 1
                if r["ticker"] in w else None)
        why = {"book_title": b.strategy.title if b else None,
               "strategy_id": b.strategy.strategy_id if b else None,
               "signal": note.get("signal"), "rule": note.get("rule"),
               "n_universe": note.get("n_universe"), "weight": w.get(r["ticker"]),
               "rank_in_weights": rank, "is_twin": bool(b and b.is_twin),
               "decided_utc": d.get("decided_utc"), "asof_date": d.get("asof_date")}
        out.append(Position(
            book=bid, family="night_books_twin" if b and b.is_twin else "night_books",
            ticker=r["ticker"], direction=1 if (r["shares"] or 0) >= 0 else -1,
            entry_ts=d.get("decided_utc") or r["opened_at"],
            entry_px=float(r["cost_basis"]) if r["cost_basis"] else None,
            why_selected=why, held_by_book=tuple(held.get(bid, ())),
            priority=bid in PRIORITY_BOOKS, source="aegis db paper_positions + paper_book_decisions",
            entry_session=d.get("asof_date")))
    return out


def _lane_positions() -> list[Position]:
    from backend.db import get_connection
    c = get_connection()
    try:
        rows = c.execute("SELECT portfolio_id, ticker, shares, cost_basis, opened_at "
                         "FROM paper_positions WHERE portfolio_id NOT LIKE 'book:%'").fetchall()
    finally:
        c.close()
    seen, out = set(), []
    for r in rows:
        key = (r["portfolio_id"], r["ticker"], str(r["opened_at"])[:10])
        if key in seen or r["ticker"] == "$CASH":
            continue
        seen.add(key)
        out.append(Position(
            book=r["portfolio_id"], family="website_lane_localdb", ticker=r["ticker"],
            direction=1, entry_ts=str(r["opened_at"]),
            entry_px=float(r["cost_basis"]) if r["cost_basis"] else None,
            why_selected={"lane": r["portfolio_id"],
                          "note": "local DB mirror of a website lane; prod is authoritative; "
                                  "opened_at is naive and read as UTC"},
            source="local aegis db paper_positions"))
    return out


def _fleet_positions(cache: Path) -> list[Position]:
    if not cache.exists():
        return []
    d = json.loads(cache.read_text(encoding="utf-8"))
    fills = sorted(d.get("fills", []), key=lambda f: f["ts"])
    pos_qty: dict[tuple, float] = {}
    entries: dict[tuple, dict] = {}
    for f in fills:
        sym = f["symbol"]
        if len(sym) > 10 and any(ch.isdigit() for ch in sym[-8:]):
            continue                       # option
        key = (f["book"], sym)
        q = pos_qty.get(key, 0.0)
        sgn = 1 if f["side"].startswith("buy") else -1
        if q == 0 or np.sign(q) == sgn:    # opening / adding
            ek = (f["book"], sym, f["t"], sgn)
            e = entries.setdefault(ek, {"ts": f["ts"], "qty": 0.0, "notional": 0.0})
            e["qty"] += f["qty"]
            e["notional"] += f["qty"] * f["price"]
        pos_qty[key] = q + sgn * f["qty"]
    out = []
    for (book, sym, day, sgn), e in entries.items():
        out.append(Position(
            book=book, family="alpaca_fleet", ticker=sym, direction=sgn,
            entry_ts=e["ts"], entry_px=e["notional"] / e["qty"] if e["qty"] else None,
            why_selected={"book": book, "side": "long" if sgn > 0 else "short",
                          "note": "Alpaca fill; the terminal's decision thesis is not joined"},
            source=d.get("source", "alpaca fills")))
    return out


def _pc_positions() -> list[Position]:
    out, seen = [], set()
    for f in sorted(glob.glob(str(LEDGER / "pc_book" / "2026-*" / "state_latest.json"))):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for p in d.get("positions", []):
            if p["symbol"] in seen:
                continue
            seen.add(p["symbol"])
            out.append(Position(
                book="PC-PAPER", family="pc_paper", ticker=p["symbol"],
                direction=1 if float(p.get("qty", 0)) >= 0 else -1,
                entry_ts=d.get("t"), entry_px=float(p.get("avg_entry_price") or 0) or None,
                why_selected={"book": "PC-PAPER", "note": "first state_latest that shows it"},
                source=f))
    return out


def _conviction_positions() -> list[Position]:
    p = _cfg.DATA_DIR / "conviction_decisions_snapshot.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for r in d.get("decisions", []):
        if r.get("action") != "enter":
            continue
        out.append(Position(
            book="conviction", family="conviction_log", ticker=r["ticker"],
            direction=1 if (r.get("shares_delta") or 0) >= 0 else -1,
            entry_ts=r["timestamp"], entry_px=r.get("price"),
            why_selected={"rationale": r.get("rationale"), "conviction": r.get("conviction"),
                          "late_entry": r.get("late_entry")},
            source="conviction_decisions_snapshot.json"))
    return out


def collect_positions(fleet_cache: Path | None = None) -> list[Position]:
    fleet_cache = fleet_cache or OUT_DIR / f"fleet_fills_{date.today().isoformat()}.json"
    out = []
    for fn in (_book_positions, _lane_positions, _pc_positions, _conviction_positions):
        try:
            out += fn()
        except Exception as exc:                            # noqa: BLE001
            logger.warning("positions source %s failed: %s", fn.__name__, exc)
    out += _fleet_positions(fleet_cache)
    return out


def _load_bars_since(start: pd.Timestamp) -> pd.DataFrame:
    from backend.services import xs_ranker as XR
    frames = []
    for p in XR.survivorship_free_paths():
        frames.append(pd.read_parquet(p, filters=[("date", ">=", start.to_pydatetime())]))
    b = pd.concat(frames, ignore_index=True)
    b["date"] = pd.to_datetime(b["date"])
    return b.drop_duplicates(["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)


def load_sector_map() -> dict[str, str]:
    try:
        tick = pd.read_parquet(CRSP_PIT, columns=["permno", "date", "ticker"])
        tick = tick.sort_values("date").groupby("permno").tail(1)
        g = pd.read_parquet(JKP, columns=["permno", "eom", "gics"])
        g = g.dropna(subset=["gics"]).sort_values("eom").groupby("permno").tail(1)
        m = tick.merge(g, on="permno")
        return {str(t): f"gics{str(int(x))[:2]}" for t, x in zip(m["ticker"], m["gics"])}
    except Exception as exc:                                # noqa: BLE001
        logger.warning("sector map unavailable: %s", exc)
        return {}


_SUFFIX = re.compile(r"\b(inc|corp|corporation|co|ltd|plc|holdings?|group|company|"
                     r"n\.?v|s\.?a|ag|lp|llc|/[a-z]+/?)\b\.?", re.I)
_COMMON = {"american", "first", "global", "united", "general", "national", "applied",
           "advanced", "international", "digital", "energy", "capital", "health",
           "therapeutics", "technologies", "technology", "systems", "financial",
           "pharmaceuticals", "bancorp", "resources", "industries", "solutions",
           "communications", "semiconductor", "biosciences", "entertainment",
           "medical", "power", "enterprise", "enterprises", "partners", "trust"}


def load_news(tickers: set[str]) -> list[dict]:
    names: dict[str, list[re.Pattern]] = {}
    cik2t: dict[str, str] = {}
    try:
        ct = json.loads(COMPANY_TICKERS.read_text(encoding="utf-8"))
        for v in ct.values():
            t = str(v["ticker"]).upper()
            cik2t[str(v["cik_str"]).zfill(10)] = t
            if t in tickers and t not in names:
                clean = _SUFFIX.sub("", str(v["title"])).strip(" ,.").lower()
                pats = [re.compile(r"\$" + re.escape(t) + r"\b")]
                # the full cleaned company name only: first-token matching made
                # "Revolution Medicines" match every headline with "revolution"
                if len(clean) >= 5 and clean.split()[0] not in _COMMON:
                    pats.append(re.compile(r"\b" + re.escape(clean) + r"\b", re.I))
                names[t] = pats
    except (OSError, ValueError):
        pass
    out = []
    for f in sorted(glob.glob(str(NEWS_DIR / "*" / "*.jsonl"))):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                tags = {str(x).upper() for x in (r.get("tickers") or [])}
                for e in r.get("entity_tags") or []:
                    if str(e).startswith("cik:"):
                        t = cik2t.get(str(e)[4:].zfill(10))
                        if t:
                            tags.add(t)
                title = r.get("title") or ""
                hit = tags & tickers
                if hit and r.get("source") == "yfinance_ticker_news":
                    # yfinance tags a row with the QUERIED ticker and serves
                    # off-topic items ("Apple Duo Foldable..." tagged A and AA):
                    # the tag counts only when title or body names the company.
                    text = f"{title} {r.get('body') or ''}"
                    hit = {t for t in hit
                           if f"({t})" in text or f":{t})" in text or f": {t})" in text
                           or any(p.search(text) for p in names.get(t, ()))}
                for t in tickers - hit:
                    if (f"({t})" in title or f": {t})" in title or f":{t})" in title
                            or any(p.search(title) for p in names.get(t, ()))):
                        hit.add(t)
                if hit:
                    out.append({k: r.get(k) for k in ("source", "first_seen_utc",
                                                      "published_utc", "title", "url")}
                               | {"_tickers": sorted(hit)})
    return out


def _load_catalysts() -> list[dict]:
    import yaml
    out = []
    for f in glob.glob(CATALYST_GLOB):
        try:
            d = yaml.safe_load(Path(f).read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        for c in d.get("catalysts", []) or []:
            out.append({**{k: str(v) for k, v in c.items()}, "built": str(d.get("built")),
                        "file": Path(f).name})
    return out


def _load_cards() -> dict:
    out: dict[str, list] = {}
    for f in glob.glob(str(CARDS_DIR / "*" / "*.json")):
        p = Path(f)
        if p.name.startswith("_"):
            continue
        out.setdefault(p.stem, []).append((p.parent.name, str(p)))
    for v in out.values():
        v.sort()
    return out


def _load_pit_rows(tickers: set[str]) -> list[dict]:
    import sqlite3
    if not PI_DB.exists():
        return []
    c = sqlite3.connect(str(PI_DB))
    try:
        rows = c.execute("SELECT key, as_of, observed_at, value, payload, source "
                         "FROM pit_observations").fetchall()
    finally:
        c.close()
    return [{"key": k, "as_of": a, "observed_at": o, "value": v, "payload": p, "source": s}
            for k, a, o, v, p, s in rows if str(k).split(":")[-1] in tickers]


def build_real_inputs(fleet_cache: Path | None = None
                      ) -> tuple[list[Position], Context]:
    positions = collect_positions(fleet_cache)
    starts = []
    for p in positions:
        try:
            starts.append(pd.Timestamp(p.entry_session) if p.entry_session
                          else pd.Timestamp(_utc(p.entry_ts).date()))
        except ValueError:
            pass
    start = min(starts) - pd.Timedelta(days=420)
    bars = _load_bars_since(start)
    from backend.services import xs_ranker as XR
    closes = bars.pivot(index="date", columns="symbol", values="close").sort_index()
    volumes = bars.pivot(index="date", columns="symbol", values="volume").sort_index()
    feats = XR.mark_eligible(XR.build_features(bars))
    keep = [c for c in ("symbol", "date", "close", "mom_21", "mom_63", "mom_252_21",
                        "rev_5", "vol_21", "vol_63", "median_dollar_vol",
                        "turnover_surge", "px_vs_52w_high", "amihud", "beta_63",
                        "eligible") if c in feats.columns]
    feats = feats[keep]
    del bars
    ctx = Context(closes=closes, volumes=volumes, sector=load_sector_map(),
                  features=feats)
    return positions, ctx


def enrich_context(ctx: Context, tickers: set[str]) -> Context:
    """The text/row sources, loaded only for the case tickers."""
    ctx.news = load_news(tickers)
    try:
        rv = pd.read_parquet(REVISIONS)
        ctx.revisions = rv[rv["ticker"].isin(tickers)].copy()
    except Exception as exc:                                # noqa: BLE001
        logger.warning("revisions unavailable: %s", exc)
    preds = []
    if PREDICTIONS.exists():
        with open(PREDICTIONS, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("ticker") in tickers:
                    preds.append(r)
    ctx.predictions = preds
    ctx.cards = _load_cards()
    ctx.catalysts = _load_catalysts()
    ctx.pit_rows = _load_pit_rows(tickers)
    # features only for dates we need keep memory small
    return ctx


# ─────────────────────────── the run ────────────────────────────────────────

def analyse(cases: list[Case], ctx: Context, *, adjudicate: Any = None) -> list[dict]:
    rows = []
    for c in cases:
        st = state_at_entry(c, ctx)
        ex = ex_post_catalyst(c, ctx)
        ctl = matched_controls(c, ctx)
        cl = classify(c, st, ex, ctl, adjudicate=adjudicate)
        cr = credit(c, cl["label"], cl["predicted"], cl["selected_for"], ctl)
        hit = cr["credit"] in ("credited",) or (
            c.position.direction * c.move > 0 and "accidental" in cr["why"])
        feat = candidate_feature(c, cl, st) if hit else None
        p = c.position
        rows.append({
            "case_id": c.case_id, "book": p.book, "family": p.family,
            "ticker": p.ticker, "direction": p.direction, "priority": p.priority,
            "entry_ts": p.entry_ts, "entry_px": p.entry_px, "S": c.S, "R": c.R,
            "horizon": c.horizon, "move": round(c.move, 5), "move_cc": round(c.move_cc, 5),
            "sigma_1": _num(c.sigma_1), "sigma_h": _num(c.sigma_h), "z": _num(c.z),
            "trigger": c.trigger, "path": c.path, "entry_basis": c.entry_basis,
            "entry_px_gap": c.entry_px_gap,
            "state_at_entry": st, "ex_post_catalyst": ex, "controls": ctl,
            "class": cl["label"], "class_rule": cl["rule"], "mechanism": cl.get("mechanism"),
            "predicted": cl["predicted"], "selected_for": cl["selected_for"],
            "adjudicated_by": cl["adjudicated_by"],
            "credit": cr["credit"], "credit_why": cr["why"],
            "candidate_feature": feat})
    return rows


def _table(rows: list[dict]) -> list[str]:
    lines = ["| ticker | book | entry | h | move | move h1 / h5 | sigma_h | class | credited | control median | candidate feature |",
             "|---|---|---|---:|---:|---|---:|---|---|---:|---|"]
    for r in sorted(rows, key=lambda r: (not r["priority"], -abs(r["move"]))):
        cm = r["controls"].get("median")
        lines.append(
            f"| {r['ticker']} | {r['book']}{' *' if r['priority'] else ''} | {r['S']} | "
            f"{r['horizon']} | {r['move']:+.1%} | "
            f"{_hp(r, '1')} / {_hp(r, '5')} | "
            f"{(r['sigma_h'] or 0):.1%} | {r['class']} | {r['credit']} | "
            f"{'' if cm is None else f'{cm:+.1%}'} | "
            f"{(r['candidate_feature'] or {}).get('name', '')} |")
    return lines


def write_receipts(rows: list[dict], meta: dict, *, out_dir: Path = OUT_DIR,
                   day: str | None = None) -> tuple[Path, Path]:
    day = day or date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / f"fast_movers_{day}.json"
    jp.write_text(json.dumps({**meta, "cases": rows}, indent=1, default=str),
                  encoding="utf-8")
    md = out_dir / "FAST_MOVERS.md"
    lines = [f"# Fast movers -- {day}", "",
             f"Receipt: `{jp.name}`. Rules: `backend/services/fast_mover_forensics.py`. "
             "State at entry uses only rows stamped <= entry; the ex-post catalyst is a "
             "separate column. Credit requires beating the median of 3 matched controls "
             "by >= 1 sigma_h AND the mechanism visible at entry AND the reason it was held.",
             "", "## Counts", "",
             "```", json.dumps(meta.get("summary", {}), indent=1), "```", "",
             "## Cases", ""]
    lines += _table(rows)
    sup = (meta.get("priority_books_h6_supplement") or {}).get("cases")
    if sup:
        lines += ["", "## Supplement: the ~10% books at h = 6 (2026-09-21)", "",
                  "Outside the declared window (h in 1, 5); printed because that "
                  "session is where their gain came from.", ""]
        lines += _table(sup)
    lines += ["", "`*` = one of the ~10% books Murat named (abstention, always-invested, "
              "12-1 momentum).", ""]
    md.write_text("\n".join(lines), encoding="utf-8")
    return jp, md


def _hp(r: dict, h: str) -> str:
    p = (r.get("path") or {}).get(h)
    return "--" if not p else f"{p['move']:+.1%}"


def summarise(rows: list[dict], coverage: dict) -> dict:
    from collections import Counter
    fav = [r for r in rows if r["direction"] * r["move"] > 0]
    return {
        "n_cases": len(rows),
        "n_unique_ticker_entries": len({(r["ticker"], r["S"]) for r in rows}),
        "class_counts": dict(Counter(r["class"] for r in rows)),
        "credit_counts": dict(Counter(r["credit"] for r in rows)),
        "favourable": len(fav), "adverse": len(rows) - len(fav),
        "favourable_beating_controls": sum(1 for r in fav if "accidental" in r["credit_why"]
                                           or r["credit"] == "credited"),
        "credited": sum(r["credit"] == "credited" for r in rows),
        "coverage_by_family": coverage,
        "candidate_features": sorted({r["candidate_feature"]["name"] for r in rows
                                      if r["candidate_feature"]}),
    }


__all__ = ["CLASSES", "Position", "Case", "Context", "find_fast_movers",
           "state_at_entry", "ex_post_catalyst", "classify", "matched_controls",
           "credit", "candidate_feature", "analyse", "write_receipts", "summarise",
           "x_quest", "Adjudicator", "build_real_inputs", "enrich_context"]
