"""SOURCE SCORECARD: grade what WSJ, Barron's and MarketWatch SAID against what then HAPPENED.

    python -m scripts.source_scorecard            # grade whatever the corpus holds now

Licence: PRODUCT_EXPERIMENT diagnostics. $0: no LLM, no browser, no network.
Grading is arithmetic on stored claims and stored daily bars.

THE UNIT
========
One dated claim about one ticker with a direction (up / down / none) and, when
stated, a magnitude and a horizon. Units come from five places:

  a. `llm_claim`   -- the claims ledger the reader's DeepSeek extraction wrote
                      (`dowjones_claims.local_claims_path`), one row per
                      (article, ticker, direction). Column = the article's column.
  b. `pick_url`    -- a Barron's stock-pick article whose URL slug says `buy-` /
                      `sell-`: its FIRST `(ticker: XX)` name is the pick. Other
                      named tickers carry no stance and are counted, not graded.
  c. `index_direction` -- a Barron's Big Money poll: bulls vs bears, parsed by
                      `dowjones_claims.parse_big_money` (regex, no LLM), graded as
                      a call on SPY. Stock picks inside the poll arrive through (a).
  d. `consensus_target` -- a MarketWatch analyst-estimates page: consensus mean
                      target vs the page's current price. These are dated by
                      WHEN AEGIS SAW THE PAGE, so today's snapshots are OPEN at
                      every horizon. History of analyst targets is a DIFFERENT
                      source: `yf_analyst_revisions` (the 393k dated yfinance
                      revisions), graded by claim type, labelled as such.
  e. WSJ Heard on the Street stances arrive through (a). The reader labels every
     WSJ page it stores `wsj_heard_on_the_street`; a page whose title starts
     "Exclusive" or whose URL is a What's-News link is re-labelled `wsj_news`,
     and every WSJ unit carries `column_evidence` (none of the stored URLs
     carries a heard-on-the-street marker, so the label is the reader lane's).

POINT IN TIME (non-negotiable)
==============================
* A claim is known from the first session that OPENS after its publication
  timestamp. With a time: converted to New York; before 09:30 ET on a session
  day -> that session, else the next. With only a date (or a digest's
  midnight-UTC stamp, or a yfinance event whose zone is unknown): the NEXT
  session after that date.
* Entry is that session's OPEN (`ENTRY_PRICE`); exit at horizon h is the CLOSE
  of session entry+h-1. Never the publication day's close.
* A horizon whose exit session is not in the bars is OPEN: counted, never
  graded, never dropped.
* A ticker with no bars is UNGRADEABLE_NO_BARS_FOR_TICKER, by name.

THREE RETURNS PER UNIT
======================
raw; in excess of SPY over the same session window; in excess of a MATCHED
CONTROL: the equal-weight mean return, over the same window, of every other name
in the unit's (size band x 63-session vol tercile x 12-1 momentum tercile) cell
on the last session BEFORE entry -- the cell definition is
`matched_twins.cell_table` / `CellIndex` (DGTW), with its fallbacks
(band_vol -> band -> any) counted. The mean of the whole cell is used instead of
one random twin: same characteristics, no draw noise.

THE EFFECTIVE SAMPLE IS DATE BLOCKS
===================================
Every cell prints n claims, n tickers and n publication dates, and its standard
error is clustered by publication date (CR1). Ten claims on one morning are one
observation of that morning, not ten. MDE = 2.8 x clustered SE.

WHAT THIS DOES NOT RE-DERIVE (closed 2026-09-26, `docs/reviews/ADJUDICATION_2026-09-26_WAVE*.md`)
* broker identity: 320,809 directional revisions, hit 50.1% (5d) / 50.2% (21d),
  firm skill rho -0.11 half-to-half -- the yfinance leg is graded by CLAIM TYPE,
  never by firm;
* first-mover raises: -0.06% at 21d point-in-time, the +1.34% version was look-ahead;
* `skill_mom` (analyst-skill filter): the whole edge is 2025.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

LICENCE = "PRODUCT_EXPERIMENT"

# ── parameters (kept here: this module must not edit backend/config.py) ─────
HORIZONS: tuple[int, ...] = (1, 5, 21, 63)
ENTRY_PRICE = "open"               # entry = OPEN of the first session opening after publication
EXIT_PRICE = "close"               # exit  = CLOSE of session entry + h - 1
MARKET_OPEN_ET = (9, 30)
NY_TZ = "America/New_York"
BENCHMARK = "SPY"
FEATURE_LOOKBACK_SESSIONS = 63     # vol and median dollar volume window (matched_twins convention)
MOM_LONG, MOM_SKIP = 252, 21       # 12-1 momentum (mom_252_21)
PRE_MOVE_SESSIONS = 5              # "already moved" window before publication
MIN_DATE_BLOCKS = 10               # fewer publication dates -> TOO_FEW
T_CRIT = 2.0                       # detection threshold on the clustered t
MDE_MULT = 2.8                     # 80% power at 5% two-sided
MIN_CONTROL_NAMES = 3              # a control cell needs this many other names
#: The effect a column would have to deliver to be worth following, per horizon
#: (signed excess vs the matched control). Used only to say the n NEEDED.
TARGET_EFFECT: dict[int, float] = {1: 0.005, 5: 0.01, 21: 0.02, 63: 0.04}
DEFAULT_DAILY_SD = 0.025           # pooled-sd fallback when a cell has < 2 date blocks
NEUTRAL_NULL_HIT = 0.6827          # P(|z| < 1) under a random walk
CONSENSUS_LOOKBACK_DAYS = 90
YF_LEG_START = "2025-01-01"
YF_SOURCE = "yf_analyst_revisions"
TOP_N_WINNERS = 5
BARS_PATHS: tuple[str, ...] = ("prices_2025_26/bars.parquet", "prices_deep/bars.parquet")
DJ_SOURCES = ("wsj", "barrons", "marketwatch")

_BUYISH = re.compile(r"\b(buy|outperform|overweight|positive|accumulate|add|strong buy|"
                     r"market outperform|sector outperform)\b", re.I)
_SELLISH = re.compile(r"\b(sell|underperform|underweight|negative|reduce|strong sell|"
                      r"market underperform|sector underperform)\b", re.I)


class ScorecardRefused(RuntimeError):
    """An input the scorecard needs is absent: it refuses by name rather than
    printing a table computed from nothing."""


# ── paths ────────────────────────────────────────────────────────────────────

def _optimus_dir() -> Path:
    from backend import config as _config
    return Path(_config.OPTIMUS_LEDGER_DIR)


def default_corpus_root() -> Path:
    from backend.services import web_reader as WR
    return WR.corpus_root()


def default_out_dir() -> Path:
    return _optimus_dir() / "source_scorecard"


def default_revisions_path() -> Path:
    return _optimus_dir() / "analyst" / "target_revisions.parquet"


# ── corpus ───────────────────────────────────────────────────────────────────

@dataclass
class Corpus:
    root: Path
    articles: dict[str, dict] = field(default_factory=dict)   # sha -> article (text in memory only)
    claims: list[dict] = field(default_factory=list)
    extracted: set[str] = field(default_factory=set)


def load_corpus(root: Optional[Path] = None) -> Corpus:
    """Every stored article (`<publisher>/<day>/<sha>.json`) and every claims row.
    Refuses by name when there is nothing at all."""
    root = Path(root) if root else default_corpus_root()
    c = Corpus(root=root)
    if root.exists():
        for p in sorted(root.glob("*/*/*.json")):
            if p.parts[-3].startswith("_"):
                continue
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(d, dict) and d.get("sha"):
                c.articles[str(d["sha"])] = d
        cdir = root / "_claims"
        if cdir.exists():
            seen: set[tuple] = set()
            for p in sorted(cdir.glob("*.jsonl")):
                for line in p.read_text(encoding="utf-8").splitlines():
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    k = (r.get("article_sha"), r.get("ticker"), r.get("direction"))
                    if k in seen:
                        continue
                    seen.add(k)
                    c.claims.append(r)
            ex = cdir / "_extracted.txt"
            if ex.exists():
                c.extracted = {s.strip() for s in ex.read_text(encoding="utf-8").split() if s.strip()}
    if not c.articles and not c.claims:
        raise ScorecardRefused(f"EMPTY_CORPUS: no stored article and no claim under {root}")
    return c


def _wsj_column(art: dict, column: str) -> tuple[str, str]:
    """(column, evidence) for a WSJ page. The reader labels every WSJ page it
    stores as Heard on the Street; the label is kept unless the page is plainly
    news (an "Exclusive" or a What's-News link)."""
    url = str(art.get("url") or "").lower()
    title = str(art.get("title") or "")
    if "heard-on-the-street" in url or "heard on the street" in title.lower():
        return column, "url_or_title_marker"
    if title.strip().lower().startswith("exclusive") or "_whatsnews" in url:
        return "wsj_news", "relabelled_news_exclusive"
    return column, "reader_lane_label"


def _time_basis(published: Any, first_seen: Any) -> tuple[Optional[str], str]:
    if published:
        return str(published), "published_utc"
    if first_seen:
        return str(first_seen), "first_seen_utc"
    return None, "none"


def _pub_of(art: dict) -> str:
    return str(art.get("publisher") or "dowjones")


def build_dj_units(corpus: Corpus) -> tuple[list[dict], dict]:
    """Units (a)-(e) from the Dow Jones corpus, plus the count of articles that
    produced none (by reason)."""
    from backend.services import dowjones_claims as DC
    units: list[dict] = []
    no_unit: Counter = Counter()
    claimed: set[tuple[str, str]] = set()

    for r in corpus.claims:
        sha = str(r.get("article_sha") or "")
        art = corpus.articles.get(sha, {})
        col = str(r.get("source_id") or art.get("column") or "dowjones_other")
        pub = _pub_of(art) if art else col.split("_")[0]
        evidence = "claims_ledger_source_id"
        if pub == "wsj" and art:
            col, evidence = _wsj_column(art, col)
        ts, basis = _time_basis(r.get("published_utc") or art.get("published_utc"),
                                r.get("first_seen_utc") or art.get("first_seen_utc"))
        d = str(r.get("direction") or "none").lower()
        mb = str(r.get("magnitude_bucket") or "unstated")
        units.append({
            "unit_id": f"llm:{sha}:{r.get('ticker')}:{d}", "source": pub, "column": col,
            "column_evidence": evidence,
            "claim_type": ("neutral_stance" if d == "none" else
                           ("manager_pick" if col == "barrons_big_money_poll" else
                            ("pick" if col == "barrons_stock_picks" else "directional_stance"))),
            "ticker": str(r.get("ticker") or "").upper(), "direction": d,
            "number_given": mb not in ("unstated", ""), "horizon_stated": r.get("horizon_days_stated"),
            "ts": ts, "time_basis": basis, "date_only": False, "pit_grade": r.get("pit_grade"),
            "article_sha": sha, "article_title": str(art.get("title") or "")[:120]})
        claimed.add((sha, str(r.get("ticker") or "").upper()))

    for sha, art in corpus.articles.items():
        col = str(art.get("column") or "")
        pub = _pub_of(art)
        text = str(art.get("text") or "")
        ts, basis = _time_basis(art.get("published_utc"), art.get("first_seen_utc"))
        base = {"source": pub, "column": col, "column_evidence": "article_column",
                "ts": ts, "time_basis": basis, "date_only": False,
                "pit_grade": art.get("pit_grade"), "article_sha": sha,
                "article_title": str(art.get("title") or "")[:120], "horizon_stated": 252}
        if col == "barrons_stock_picks":
            named = DC.barrons_named_tickers(text)
            slug = str(art.get("url") or "").lower().split("/articles/")[-1]
            d = "up" if slug.startswith("buy-") else ("down" if slug.startswith("sell-") else None)
            for i, t in enumerate(named):
                if (sha, t) in claimed:
                    continue
                if i == 0 and d:
                    units.append({**base, "unit_id": f"pick:{sha}:{t}", "claim_type": "pick_url",
                                  "ticker": t, "direction": d, "number_given": False})
                else:
                    no_unit["barrons_named_no_stance"] += 1
        elif col == "barrons_big_money_poll":
            day = str(art.get("first_seen_utc") or ts or "")[:10] or "1970-01-01"
            p = DC.parse_big_money(text, seen_day=day)
            if p["majority_direction"]:
                units.append({**base, "unit_id": f"poll:{sha}", "claim_type": "index_direction",
                              "ticker": BENCHMARK, "direction": p["majority_direction"],
                              "number_given": bool(p["spx_forecasts"]), "is_index": True})
            else:
                no_unit["big_money_no_majority_parsed"] += 1
        elif col == "mw_analyst_estimates":
            tk = DC.mw_ticker_of(str(art.get("url") or ""))
            m = DC.parse_mw_analyst(text)
            tgt, px = m.get("target_mean") or m.get("target_median"), m.get("current_price")
            # the page's consensus is a SNAPSHOT: dated when Aegis saw it
            ts2, basis2 = _time_basis(None, art.get("first_seen_utc"))
            if tk and tgt and px:
                units.append({**base, "unit_id": f"mw:{tk}:{str(ts2)[:10]}",
                              "claim_type": "consensus_target", "ticker": tk,
                              "direction": "up" if tgt > px else "down", "number_given": True,
                              "ts": ts2, "time_basis": basis2})
            else:
                no_unit["mw_page_parse_thin"] += 1
        elif sha not in corpus.extracted:
            no_unit[f"{col or pub}:awaiting_extraction"] += 1
        elif not any(u.get("article_sha") == sha for u in units):
            no_unit[f"{col or pub}:extracted_no_claim"] += 1
    # MW snapshots of one ticker on one day are one unit
    seen: set[str] = set()
    out = []
    for u in units:
        if u["unit_id"] in seen:
            continue
        seen.add(u["unit_id"])
        out.append(u)
    return out, dict(no_unit)


def _grade_direction(g: Any) -> Optional[str]:
    s = str(g or "")
    if _SELLISH.search(s):
        return "down"
    if _BUYISH.search(s):
        return "up"
    return None


def build_yf_units(rev: pd.DataFrame, *, start: str = YF_LEG_START) -> list[dict]:
    """The yfinance revisions leg, by CLAIM TYPE (never by firm: broker identity
    is closed). Event times have no stated zone, so each is date-only."""
    r = rev[rev["event_date"].astype(str) >= start].copy()
    if "pit_safe" in r:
        r = r[r["pit_safe"].astype(bool)]
    act = r["action"].astype(str).str.lower()
    ta = r["target_action"].astype(str).str.lower()
    ctype = pd.Series(None, index=r.index, dtype=object)
    dirn = pd.Series(None, index=r.index, dtype=object)
    ctype[act == "up"], dirn[act == "up"] = "upgrade", "up"
    ctype[act == "down"], dirn[act == "down"] = "downgrade", "down"
    rest = ~act.isin(["up", "down", "init"])
    ctype[rest & (ta == "raises")], dirn[rest & (ta == "raises")] = "target_raise", "up"
    ctype[rest & (ta == "lowers")], dirn[rest & (ta == "lowers")] = "target_lower", "down"
    init = act == "init"
    idir = r.loc[init, "to_grade"].map(_grade_direction)
    ctype[init & idir.reindex(r.index).notna()] = "initiation"
    dirn[init] = idir
    r["claim_type"], r["direction"] = ctype, dirn
    r = r[r["claim_type"].notna() & r["direction"].notna()]
    units = []
    for i, row in zip(r.index, r.itertuples(index=False)):
        units.append({"unit_id": f"yf:{i}", "source": YF_SOURCE, "column": YF_SOURCE,
                      "column_evidence": "yfinance_upgrades_downgrades",
                      "claim_type": row.claim_type, "ticker": str(row.ticker).upper(),
                      "direction": row.direction,
                      "number_given": bool(pd.notna(row.current_target)),
                      "horizon_stated": 252, "ts": str(row.event_date)[:10],
                      "time_basis": "event_date", "date_only": True, "pit_grade": "pit_safe"})
    return units


# ── prices ───────────────────────────────────────────────────────────────────

def load_bars(paths: Optional[Iterable[Path]] = None, *, since: Optional[str] = None) -> pd.DataFrame:
    """Union of the local daily bar files (first listed wins on a duplicate)."""
    from backend.services import stitched_tickers as ST
    paths = [Path(p) for p in paths] if paths else [_optimus_dir() / p for p in BARS_PATHS]
    frames = []
    for p in paths:
        if not p.exists():
            continue
        flt = [("date", ">=", pd.Timestamp(since))] if since else None
        frames.append(ST.tag_source(
            pd.read_parquet(p, columns=["symbol", "date", "open", "close", "volume"],
                            filters=flt), p.stem))
    if not frames:
        raise ScorecardRefused(f"NO_BARS: none of {[str(p) for p in paths]} exists")
    b = pd.concat(frames, ignore_index=True).drop_duplicates(["symbol", "date"], keep="first")
    return ST.cut_reader_bars(b, market=BENCHMARK)   # reused tickers start at the new company


class PricePanel:
    """Wide open/close/volume on the benchmark's session calendar, plus the
    matched-control characteristics as of each session's close."""

    def __init__(self, bars: pd.DataFrame):
        if bars is None or not len(bars):
            raise ScorecardRefused("NO_BARS: empty bar frame")
        b = bars.copy()
        b["date"] = pd.to_datetime(b["date"]).dt.normalize()
        if BENCHMARK not in set(b["symbol"]):
            raise ScorecardRefused(f"NO_BENCHMARK: {BENCHMARK} has no bars")
        cal = pd.DatetimeIndex(sorted(b.loc[b["symbol"] == BENCHMARK, "date"].unique()))
        self.calendar = cal
        W = {c: b.pivot_table(index="date", columns="symbol", values=c, aggfunc="last")
             .reindex(cal) for c in ("open", "close", "volume")}
        self.symbols = list(W["close"].columns)
        self.col = {s: i for i, s in enumerate(self.symbols)}
        self.O = W["open"].to_numpy(float)
        self.C = W["close"].to_numpy(float)
        V = W["volume"].to_numpy(float)
        C = W["close"]
        lr = np.log(C / C.shift(1))
        L = FEATURE_LOOKBACK_SESSIONS
        self.vol = lr.rolling(L, min_periods=int(L * 0.66)).std().to_numpy(float)
        self.mdv = (C * pd.DataFrame(V, index=cal, columns=C.columns)).rolling(
            L, min_periods=int(L * 0.66)).median().to_numpy(float)
        self.mom = (C.shift(MOM_SKIP) / C.shift(MOM_LONG) - 1.0).to_numpy(float)
        self._cells: dict[int, Any] = {}
        self._ctrl: dict[tuple, Any] = {}

    @property
    def last_date(self) -> pd.Timestamp:
        return self.calendar[-1]

    def entry_index(self, ts: Optional[str], *, date_only: bool = False) -> Optional[int]:
        """Index of the first session that OPENS after `ts`; len(calendar) when
        that session is beyond the bars (all horizons OPEN); None if undated."""
        if not ts:
            return None
        t = pd.Timestamp(ts)
        midnight_utc = (t.tzinfo is not None and t.tz_convert("UTC").hour == 0
                        and t.tz_convert("UTC").minute == 0 and t.tz_convert("UTC").second == 0)
        if t.tzinfo is None or date_only or midnight_utc or len(str(ts)) <= 10:
            day = (t.tz_convert("UTC") if t.tzinfo is not None else t).tz_localize(None).normalize()
            return int(self.calendar.searchsorted(day, side="right"))
        et = t.tz_convert(NY_TZ)
        day = pd.Timestamp(et.date())
        i = int(self.calendar.searchsorted(day, side="left"))
        if i < len(self.calendar) and self.calendar[i] == day and \
                (et.hour, et.minute) < MARKET_OPEN_ET:
            return i
        return int(self.calendar.searchsorted(day, side="right"))

    def fwd(self, e: int, h: int) -> np.ndarray:
        """Open(e) -> close(e+h-1) for every symbol (NaN where missing)."""
        return self.C[e + h - 1] / self.O[e] - 1.0

    def cells(self, e: int):
        """(CellIndex, panel_d) as of the close of session e-1 (before entry)."""
        from backend.services import matched_twins as MT
        if e in self._cells:
            return self._cells[e]
        d = e - 1
        panel_d = pd.DataFrame({"symbol": self.symbols, "median_dollar_vol": self.mdv[d],
                                "vol_63": self.vol[d], "mom_252_21": self.mom[d]})
        panel_d["eligible"] = np.isfinite(panel_d["median_dollar_vol"]) & \
            np.isfinite(panel_d["vol_63"])
        ci = MT.CellIndex(MT.cell_table(panel_d))
        self._cells[e] = (ci, panel_d)
        return self._cells[e]


# ── grading ──────────────────────────────────────────────────────────────────

def _control(panel: PricePanel, e: int, ticker: str, fwd_by_h: dict[int, np.ndarray]
             ) -> tuple[dict[int, float], str]:
    """Equal-weight mean forward return of the OTHER names in the ticker's
    matched_twins cell (fallback band_vol -> band -> any), cached per
    (entry session, cell): the own name is subtracted from the cached sum."""
    ci, panel_d = panel.cells(e)
    b, v, m = ci.cell_of(ticker, panel_d)
    own = panel.col.get(ticker)
    hs = sorted(fwd_by_h)
    for lv in ("cell", "band_vol", "band", "any"):
        if lv != "any" and b is None:
            continue
        key = (e, lv, b, v, m, tuple(hs))
        if key not in panel._ctrl:
            idx = np.array([panel.col[s] for s in ci.candidates(lv, b, v, m) if s in panel.col],
                           dtype=int)
            M = np.vstack([fwd_by_h[h][idx] for h in hs]) if len(idx) else np.empty((len(hs), 0))
            fin = np.isfinite(M)
            panel._ctrl[key] = (set(idx.tolist()), np.where(fin, M, 0.0).sum(1), fin.sum(1))
        members, ssum, cnt = panel._ctrl[key]
        ssum, cnt = ssum.copy(), cnt.copy()
        if own is not None and own in members:
            for i, h in enumerate(hs):
                x = fwd_by_h[h][own]
                if np.isfinite(x):
                    ssum[i] -= x
                    cnt[i] -= 1
        if cnt.max(initial=0) < MIN_CONTROL_NAMES:
            continue
        return ({h: float(ssum[i] / cnt[i]) if cnt[i] >= MIN_CONTROL_NAMES else float("nan")
                 for i, h in enumerate(hs)}, lv)
    return {h: float("nan") for h in fwd_by_h}, "none"


def grade_units(units: list[dict], panel: PricePanel,
                horizons: tuple[int, ...] = HORIZONS) -> pd.DataFrame:
    """Long frame: one row per (unit, horizon) with state GRADED / OPEN /
    UNGRADEABLE_<reason>, the three returns, the signed returns and the hit."""
    rows = []
    n = len(panel.calendar)
    spy = panel.col[BENCHMARK]
    fwd_cache: dict[tuple[int, int], np.ndarray] = {}
    for u in units:
        e = panel.entry_index(u.get("ts"), date_only=bool(u.get("date_only")))
        tk = u["ticker"]
        base = {k: u.get(k) for k in ("unit_id", "source", "column", "claim_type", "ticker",
                                      "direction", "number_given", "time_basis")}
        base["entry_date"] = str(panel.calendar[e].date()) if e is not None and e < n else None
        pub_day = str(pd.Timestamp(u["ts"]).date()) if u.get("ts") else None
        base["pub_date"] = pub_day
        pre = _pre_move(panel, e, tk) if e is not None and e < n and tk in panel.col else {}
        base.update(pre)

        def emit(h: int, state: str, **kw: Any) -> None:
            rows.append({**base, "h": h, "state": state, **kw})

        if e is None:
            for h in horizons:
                emit(h, "UNGRADEABLE_NO_TIMESTAMP")
            continue
        if tk not in panel.col:
            for h in horizons:
                emit(h, "UNGRADEABLE_NO_BARS_FOR_TICKER")
            continue
        if e >= n:
            for h in horizons:
                emit(h, "OPEN")
            continue
        j = panel.col[tk]
        if not np.isfinite(panel.O[e, j]):
            for h in horizons:
                emit(h, "OPEN" if e + h - 1 >= n else "UNGRADEABLE_MISSING_BAR_AT_ENTRY")
            continue
        elapsed = {h: e + h - 1 < n for h in horizons}
        fwd = {}
        for h in horizons:
            if elapsed[h]:
                k = (e, h)
                if k not in fwd_cache:
                    fwd_cache[k] = panel.fwd(e, h)
                fwd[h] = fwd_cache[k]
        ctrl, level = _control(panel, e, tk, fwd) if fwd and not u.get("is_index") else ({}, "none")
        sgn = {"up": 1.0, "down": -1.0}.get(u["direction"])
        for h in horizons:
            if not elapsed[h]:
                emit(h, "OPEN")
                continue
            raw = float(fwd[h][j])
            if not np.isfinite(raw):
                emit(h, "UNGRADEABLE_MISSING_BAR_AT_EXIT")
                continue
            ex_spy = raw - float(fwd[h][spy])
            if u.get("is_index"):
                # an index call: excess vs SPY is zero by construction; the
                # control is SPY's own unconditional drift at h over the panel
                drift = _spy_drift(panel, h)
                ex_spy, ex_ctrl, level = raw, raw - drift, "spy_unconditional_drift"
            else:
                c = ctrl.get(h, float("nan"))
                ex_ctrl = raw - c if np.isfinite(c) else float("nan")
            sd_h = pre.get("sigma_daily")
            rec = {"raw": raw, "ex_spy": ex_spy, "ex_ctrl": ex_ctrl, "control_level": level}
            if sgn is not None:
                rec["signed_spy"] = sgn * ex_spy
                rec["signed_ctrl"] = sgn * ex_ctrl if np.isfinite(ex_ctrl) else float("nan")
                rec["hit"] = float(sgn * ex_spy > 0)
            elif sd_h and np.isfinite(sd_h):
                rec["hit"] = float(abs(ex_spy) < sd_h * math.sqrt(h))
            emit(h, "GRADED", **rec)
    return pd.DataFrame(rows)


_DRIFT: dict[tuple[int, int], float] = {}


def _spy_drift(panel: PricePanel, h: int) -> float:
    k = (id(panel), h)
    if k not in _DRIFT:
        j = panel.col[BENCHMARK]
        o, c = panel.O[:, j], panel.C[:, j]
        r = c[h - 1:] / o[:len(o) - h + 1] - 1.0
        _DRIFT[k] = float(np.nanmean(r))
    return _DRIFT[k]


def _pre_move(panel: PricePanel, e: int, tk: str) -> dict:
    """What the stock had ALREADY done in the PRE_MOVE_SESSIONS closes before
    entry, in units of its own 63-session daily sigma."""
    j = panel.col[tk]
    k = PRE_MOVE_SESSIONS
    if e - 1 - k < 0:
        return {}
    c1, c0 = panel.C[e - 1, j], panel.C[e - 1 - k, j]
    sd = panel.vol[e - 1, j]
    if not (np.isfinite(c1) and np.isfinite(c0) and np.isfinite(sd) and sd > 0):
        return {}
    r = c1 / c0 - 1.0
    return {"pre_ret_5": float(r), "sigma_daily": float(sd),
            "pre_z_5": float(math.log(c1 / c0) / (sd * math.sqrt(k)))}


# ── statistics ───────────────────────────────────────────────────────────────

def clustered_se(x: np.ndarray, groups: np.ndarray) -> Optional[float]:
    """CR1 standard error of the mean, clustered by `groups`."""
    x = np.asarray(x, float)
    g = np.asarray(groups)
    ok = np.isfinite(x)
    x, g = x[ok], g[ok]
    n = len(x)
    G = len(set(g.tolist()))
    if n < 2 or G < 2:
        return None
    e = x - x.mean()
    s = pd.Series(e).groupby(g).sum().to_numpy()
    return float(math.sqrt((s ** 2).sum() / n ** 2 * G / (G - 1)))


def naive_se(x: np.ndarray) -> Optional[float]:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(x.std(ddof=1) / math.sqrt(len(x))) if len(x) >= 2 else None


def wilson(k: float, n: int, z: float = 1.96) -> tuple[Optional[float], Optional[float]]:
    if n <= 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def _f(v: Any, nd: int = 5) -> Optional[float]:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if math.isfinite(v) else None


def cell_stats(g: pd.DataFrame, h: int, *, pooled_sd: Optional[float] = None) -> dict:
    """Every statistic the scorecard prints for one (source, column, claim type, h)."""
    graded = g[g["state"] == "GRADED"]
    states = g["state"].value_counts().to_dict()
    out: dict[str, Any] = {"n_units": int(len(g)), "states": {k: int(v) for k, v in states.items()},
                           "n_graded": int(len(graded))}
    directional = "signed_ctrl" in graded and graded["signed_ctrl"].notna().any() if len(graded) else False
    metric = "signed_ctrl" if directional else None
    out["n_tickers"] = int(graded["ticker"].nunique()) if len(graded) else 0
    out["n_pub_dates"] = int(graded["pub_date"].nunique()) if len(graded) else 0
    if not len(graded):
        out.update(verdict="TOO_FEW", n_dates_needed=MIN_DATE_BLOCKS,
                   why="no graded unit at this horizon")
        return out
    hit = graded["hit"].dropna() if "hit" in graded else pd.Series(dtype=float)
    lo, hi = wilson(float(hit.sum()), int(len(hit)))
    out.update(hit_rate=_f(hit.mean()) if len(hit) else None, hit_n=int(len(hit)),
               hit_ci95=[_f(lo, 4), _f(hi, 4)])
    for col in ("raw", "ex_spy", "ex_ctrl", "signed_spy", "signed_ctrl"):
        if col in graded and graded[col].notna().any():
            out[f"mean_{col}"] = _f(graded[col].mean())
            out[f"median_{col}"] = _f(graded[col].median())
    if metric is None:
        # neutral stances: right when the move stayed inside one sigma
        if len(hit) and out["n_pub_dates"] >= MIN_DATE_BLOCKS:
            out["verdict"] = "ALPHA_DETECTED" if (lo or 0) > NEUTRAL_NULL_HIT else "CANNOT_DISTINGUISH"
        else:
            out.update(verdict="TOO_FEW", n_dates_needed=MIN_DATE_BLOCKS)
        out["neutral_null_hit"] = NEUTRAL_NULL_HIT
        return out
    x = graded[metric].to_numpy(float)
    grp = graded["pub_date"].to_numpy()
    ok = np.isfinite(x)
    se_c, se_n = clustered_se(x, grp), naive_se(x)
    xs = graded["signed_spy"].to_numpy(float)
    se_spy = clustered_se(xs, grp)
    mean_c = float(np.nanmean(x)) if ok.any() else float("nan")
    mean_s = float(np.nanmean(xs))
    t_net = None
    if "signed_net" in graded and graded["signed_net"].notna().sum() >= 2:
        xn = graded["signed_net"].to_numpy(float)
        se_net = clustered_se(xn, grp)
        if se_net:
            mean_net = float(np.nanmean(xn))
            t_net = mean_net / se_net
            out["mean_signed_net_of_source_drift"] = _f(mean_net)
            out["source_drift"] = _f(graded["source_drift"].mean()) if "source_drift" in graded else None
    out["t_net_of_source_drift"] = _f(t_net, 3) if t_net is not None else None
    out.update(se_clustered=_f(se_c), se_naive=_f(se_n),
               mde=_f(MDE_MULT * se_c) if se_c else None,
               t_ctrl=_f(mean_c / se_c, 3) if se_c else None,
               t_spy=_f(mean_s / se_spy, 3) if se_spy else None)
    # by calendar month and year of publication; leave-one-month-out
    gm = graded.assign(month=graded["pub_date"].str[:7], year=graded["pub_date"].str[:4])
    out["by_month"] = {k: {"n": int(len(v)), "mean_signed_ctrl": _f(v[metric].mean())}
                       for k, v in gm.groupby("month")}
    out["by_year"] = {k: {"n": int(len(v)), "mean_signed_ctrl": _f(v[metric].mean())}
                      for k, v in gm.groupby("year")}
    months = sorted(out["by_month"])
    loo = [float(gm.loc[gm["month"] != m, metric].mean()) for m in months] if len(months) > 1 else []
    loo = [v for v in loo if math.isfinite(v)]
    out["loo_month_worst"] = _f(min(loo)) if loo else None
    srt = np.sort(x[ok])[::-1]
    tot = float(srt.sum()) if len(srt) else 0.0
    out["top5_share"] = _f(float(srt[:5].sum()) / tot, 3) if tot > 0 else None
    out["top5_share_note"] = None if tot > 0 else "total signed excess <= 0: share undefined"
    # verdict
    nd = out["n_pub_dates"]
    date_sd = pd.Series(x[ok]).groupby(grp[ok]).mean().std(ddof=1) if nd >= 2 else float("nan")
    sd = date_sd if math.isfinite(date_sd) and date_sd > 0 else (
        pooled_sd if pooled_sd else DEFAULT_DAILY_SD * math.sqrt(h))
    need = int(math.ceil((MDE_MULT * sd / TARGET_EFFECT.get(h, 0.02)) ** 2))
    out["n_dates_needed_for_target_mde"] = max(need, MIN_DATE_BLOCKS)
    out["target_effect"] = TARGET_EFFECT.get(h)
    t_c, t_s = out.get("t_ctrl"), out.get("t_spy")
    if nd < MIN_DATE_BLOCKS or t_c is None:
        out["verdict"] = "TOO_FEW"
    elif t_c >= T_CRIT and (out["loo_month_worst"] is None or out["loo_month_worst"] > 0) \
            and (out["top5_share"] is not None and out["top5_share"] < 1.0) \
            and (t_net is None or t_net >= T_CRIT):
        out["verdict"] = "ALPHA_DETECTED"
    elif t_c >= T_CRIT and t_net is not None and t_net < T_CRIT:
        out["verdict"] = "BETA_EXPLAINS"
        out["why"] = ("beats its matched control only because every name this source writes "
                      "about drifts the same way: net of the source's common drift, t < "
                      f"{T_CRIT}")
    elif t_s is not None and t_s >= T_CRIT and t_c < T_CRIT:
        out["verdict"] = "BETA_EXPLAINS"
        out["why"] = "beats SPY in the called direction but not its size/vol/momentum cell"
    else:
        out["verdict"] = "CANNOT_DISTINGUISH"
    out["anti_signal"] = bool(t_c is not None and t_c <= -T_CRIT and nd >= MIN_DATE_BLOCKS)
    return out


def add_source_drift(df: pd.DataFrame) -> pd.DataFrame:
    """`signed_net` = direction x (excess vs control - the SOURCE'S common drift).

    The common drift is the mean excess vs control of EVERY graded unit of the
    same (source, column, h), whatever its direction. A name a source writes
    about may drift against its cell for reasons that have nothing to do with
    the direction the source called (coverage, event timing, the panel); a
    "down" call on names that all drift down scores as skill, and so does an
    "up" call's mirror. Removing the common drift leaves what the DIRECTION adds.
    """
    if not len(df) or "ex_ctrl" not in df:
        return df
    g = df[df["state"] == "GRADED"]
    common = g.groupby(["source", "column", "h"])["ex_ctrl"].mean().rename("source_drift")
    df = df.merge(common, left_on=["source", "column", "h"], right_index=True, how="left")
    sgn = df["direction"].map({"up": 1.0, "down": -1.0})
    df["signed_net"] = sgn * (df["ex_ctrl"] - df["source_drift"])
    idx = df["control_level"] == "spy_unconditional_drift" if "control_level" in df else False
    df.loc[idx, "signed_net"] = df.loc[idx, "signed_ctrl"] if "signed_ctrl" in df else np.nan
    return df


def scorecard_cells(df: pd.DataFrame, horizons: tuple[int, ...] = HORIZONS) -> list[dict]:
    """Every (source, column, claim_type, h) cell, plus a pooled `*` claim type
    per (source, column)."""
    if not len(df):
        return []
    cells = []
    # sd of DATE-BLOCK means within the same family (Dow Jones vs yfinance), so
    # "dates needed" for a one-date cell is scaled on its own family's blocks
    pooled: dict[tuple[bool, int], Optional[float]] = {}
    for is_yf in (True, False):
        for h in horizons:
            gh = df[(df["h"] == h) & (df["state"] == "GRADED") & ((df["source"] == YF_SOURCE) == is_yf)]
            if "signed_ctrl" not in gh or not gh["signed_ctrl"].notna().any():
                pooled[(is_yf, h)] = None
                continue
            m = gh.dropna(subset=["signed_ctrl"]).groupby("pub_date")["signed_ctrl"].mean()
            pooled[(is_yf, h)] = float(m.std(ddof=1)) if len(m) > 2 else None
    frames = [df, df.assign(claim_type=np.where(df["claim_type"] == "neutral_stance",
                                                "neutral_stance", "*"))]
    seen = set()
    for f in frames:
        for (src, col, ct, h), g in f.groupby(["source", "column", "claim_type", "h"], sort=True):
            key = (src, col, ct, int(h))
            if key in seen:
                continue
            seen.add(key)
            if ct == "*" and g["claim_type"].nunique() == 1 and \
                    df[(df["source"] == src) & (df["column"] == col)]["claim_type"].nunique() <= 1:
                continue   # a pooled row identical to its only claim type
            cells.append({"source": src, "column": col, "claim_type": ct, "h": int(h),
                          **cell_stats(g, int(h), pooled_sd=pooled.get((src == YF_SOURCE, int(h))))})
    return cells


# ── winner vs matched loser ──────────────────────────────────────────────────

def consensus_index(rev: Optional[pd.DataFrame]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """ticker -> (sorted event days, +1/-1/0 per event) from the yfinance revisions."""
    if rev is None or not len(rev):
        return {}
    r = rev[["ticker", "event_date", "action", "target_action"]].copy()
    act = r["action"].astype(str).str.lower()
    ta = r["target_action"].astype(str).str.lower()
    r["s"] = np.where(act == "up", 1, np.where(act == "down", -1,
                      np.where(ta == "raises", 1, np.where(ta == "lowers", -1, 0))))
    r["d"] = pd.to_datetime(r["event_date"].astype(str).str[:10], errors="coerce")
    r = r.dropna(subset=["d"]).sort_values("d")
    return {t: (g["d"].to_numpy("datetime64[D]"), g["s"].to_numpy(int))
            for t, g in r.groupby("ticker")}


def consensus_at(idx: dict, ticker: str, pub_date: Optional[str],
                 exclude_same_day: bool = True) -> Optional[str]:
    """Net direction of the revisions in the CONSENSUS_LOOKBACK_DAYS STRICTLY
    before the publication date (a same-day revision is not known beforehand)."""
    if not pub_date or ticker not in idx:
        return None
    d, s = idx[ticker]
    end = np.datetime64(pub_date[:10], "D")
    lo = int(np.searchsorted(d, end - np.timedelta64(CONSENSUS_LOOKBACK_DAYS, "D"), "left"))
    hi = int(np.searchsorted(d, end, "left"))
    if hi <= lo:
        return "none_recent"
    net = int(s[lo:hi].sum())
    return "up" if net > 0 else ("down" if net < 0 else "flat")


def winner_loser(df: pd.DataFrame, cidx: dict, *, top_n: int = TOP_N_WINNERS) -> dict:
    """For each source family: the claims that turned out most right and most
    wrong at the longest horizon holding >= half the best-covered one, and what distinguished them
    BEFORE publication. Also the share published after a >1 / >2 sigma move."""
    out: dict[str, Any] = {}
    fam = df.assign(family=np.where(df["source"] == YF_SOURCE, YF_SOURCE, "dowjones"))
    for name, g in fam.groupby("family"):
        gr = g[(g["state"] == "GRADED") & g.get("signed_ctrl", pd.Series(dtype=float)).notna()]
        units = g.drop_duplicates("unit_id")
        z = units["pre_z_5"].dropna() if "pre_z_5" in units else pd.Series(dtype=float)
        rec: dict[str, Any] = {
            "n_units_with_pre_move": int(len(z)),
            "share_pub_after_move_gt_1sigma": _f((z.abs() > 1).mean(), 4) if len(z) else None,
            "share_pub_after_move_gt_2sigma": _f((z.abs() > 2).mean(), 4) if len(z) else None}
        if "pre_z_5" in units:
            dz = units.dropna(subset=["pre_z_5"])
            sg = dz["direction"].map({"up": 1.0, "down": -1.0})
            chase = (np.sign(dz["pre_z_5"]) == sg) & (dz["pre_z_5"].abs() > 1)
            rec["share_claims_in_direction_of_a_gt_1sigma_prior_move"] = \
                _f(chase[sg.notna()].mean(), 4) if sg.notna().any() else None
        if not len(gr):
            rec["note"] = "no graded directional unit"
            out[name] = rec
            continue
        # the longest horizon that still holds at least half the best-covered one
        cnt = gr.groupby("h")["unit_id"].nunique()
        hmax = int(max(h for h, n_ in cnt.items() if n_ >= 0.5 * cnt.max()))
        gh = gr[gr["h"] == hmax].copy()
        gh["consensus"] = [consensus_at(cidx, t, p) for t, p in zip(gh["ticker"], gh["pub_date"])]
        gh["agrees_with_consensus"] = gh["consensus"] == gh["direction"]
        gh["moved_gt_1sigma"] = gh["pre_z_5"].abs() > 1 if "pre_z_5" in gh else False
        gh = gh.sort_values("signed_ctrl", ascending=False)
        cols = ["source", "column", "claim_type", "ticker", "direction", "pub_date", "number_given",
                "pre_z_5", "moved_gt_1sigma", "consensus", "agrees_with_consensus", "signed_ctrl"]
        cols = [c for c in cols if c in gh]

        def rows(x: pd.DataFrame) -> list[dict]:
            return [{k: (_f(v, 4) if isinstance(v, (float, np.floating)) else
                         (bool(v) if isinstance(v, (bool, np.bool_)) else v))
                     for k, v in r.items()} for r in x[cols].to_dict("records")]
        k = max(1, len(gh) // 3)
        win, lose = gh.head(k), gh.tail(k)

        def profile(x: pd.DataFrame) -> dict:
            return {"n": int(len(x)),
                    "share_number_given": _f(x["number_given"].astype(float).mean(), 3),
                    "share_moved_gt_1sigma_before": _f(x["moved_gt_1sigma"].astype(float).mean(), 3),
                    "share_agrees_with_consensus": _f(x["agrees_with_consensus"].astype(float).mean(), 3),
                    "share_up": _f((x["direction"] == "up").astype(float).mean(), 3),
                    "by_claim_type": x["claim_type"].value_counts().to_dict(),
                    "mean_signed_ctrl": _f(x["signed_ctrl"].mean())}
        rec.update(horizon=hmax, n_graded=int(len(gh)),
                   most_right=rows(gh.head(top_n)), most_wrong=rows(gh.tail(top_n)[::-1]),
                   top_tercile_profile=profile(win), bottom_tercile_profile=profile(lose))
        out[name] = rec
    return out


# ── the run ──────────────────────────────────────────────────────────────────

def _previous_receipt(out_dir: Path) -> Optional[dict]:
    if not out_dir.exists():
        return None
    for p in sorted(out_dir.glob("source_scorecard_*.json"), reverse=True):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def proposed_weights(cells: list[dict]) -> dict[str, float]:
    """PROPOSAL ONLY. Weight 0 for every cell that is not ALPHA_DETECTED; an
    ALPHA_DETECTED cell gets min(1, t/5). Nothing live reads this."""
    w = {}
    for c in cells:
        k = f"{c['source']}|{c['column']}|{c['claim_type']}|h{c['h']}"
        t = c.get("t_ctrl") or 0.0
        w[k] = round(min(1.0, t / 5.0), 3) if c.get("verdict") == "ALPHA_DETECTED" else 0.0
    return w


def unit_state_counts(df: pd.DataFrame) -> dict:
    out: dict[str, Any] = {}
    if not len(df):
        return out
    for (src, col), g in df.groupby(["source", "column"]):
        u = g.drop_duplicates("unit_id")
        per_h = {}
        for h, gh in g.groupby("h"):
            per_h[f"h{int(h)}"] = gh["state"].value_counts().to_dict()
        graded_any = g[g["state"] == "GRADED"]["unit_id"].nunique()
        out[f"{src}|{col}"] = {"n_units": int(len(u)),
                               "n_gradeable_at_any_horizon": int(graded_any),
                               "by_horizon": per_h,
                               "by_claim_type": u["claim_type"].value_counts().to_dict()}
    return out


def run(*, corpus_root: Optional[Path] = None, bars: Optional[pd.DataFrame] = None,
        revisions: Optional[pd.DataFrame] = None, include_yf: bool = True,
        yf_start: str = YF_LEG_START, out_dir: Optional[Path] = None,
        write: bool = True, now: Optional[datetime] = None) -> dict:
    """Grade whatever exists now; write a receipt with a run id; return it."""
    now = now or datetime.now(timezone.utc)
    corpus = load_corpus(corpus_root)
    dj_units, no_unit = build_dj_units(corpus)
    rev = revisions
    rev_path = None
    if rev is None and include_yf:
        rev_path = default_revisions_path()
        rev = pd.read_parquet(rev_path) if rev_path.exists() else None
    yf_units = build_yf_units(rev, start=yf_start) if (include_yf and rev is not None) else []
    units = dj_units + yf_units
    if not units:
        raise ScorecardRefused("NO_UNITS: the corpus holds articles but no gradeable claim unit")
    if bars is None:
        dates = [str(u["ts"])[:10] for u in units if u.get("ts")]
        since = (pd.Timestamp(min(dates)) - pd.Timedelta(days=420)).strftime("%Y-%m-%d")
        bars = load_bars(since=since)
    panel = PricePanel(bars)
    df = add_source_drift(grade_units(units, panel))
    cells = scorecard_cells(df)
    cidx = consensus_index(rev)
    wl = winner_loser(df, cidx)
    prev = _previous_receipt(Path(out_dir) if out_dir else default_out_dir())
    prev_ids = set((prev or {}).get("dj_unit_ids") or [])
    dj_ids = sorted(u["unit_id"] for u in dj_units)
    new_dj = [i for i in dj_ids if i not in prev_ids]
    by_src_new = Counter(i.split(":")[0] for i in new_dj)
    prev_yf = (prev or {}).get("n_yf_units")
    run_id = now.strftime("%Y-%m-%d_%H%M%S")
    arts = Counter(f"{_pub_of(a)}|{a.get('column')}" for a in corpus.articles.values())
    receipt = {
        "receipt": "source_scorecard", "run_id": run_id, "licence": LICENCE,
        "generated_utc": now.isoformat(timespec="seconds"), "llm_calls": 0, "cost_usd": 0.0,
        "previous_run_id": (prev or {}).get("run_id"),
        "new_rows_since_last_run": {
            "dowjones_units": len(new_dj), "dowjones_units_by_kind": dict(by_src_new),
            "yf_units": (len(yf_units) - int(prev_yf)) if prev_yf is not None else len(yf_units),
            "note": "first run: every unit is new" if prev is None else None},
        "inputs": {
            "corpus_root": str(corpus.root), "n_articles": len(corpus.articles),
            "articles_by_publisher_column": dict(arts),
            "n_llm_claim_rows": len(corpus.claims), "n_articles_extracted": len(corpus.extracted),
            "articles_without_a_unit": no_unit,
            "bars_last_date": str(panel.last_date.date()), "bars_first_date": str(panel.calendar[0].date()),
            "bars_n_symbols": len(panel.symbols),
            "bars_age_days": int((pd.Timestamp(now.date()) - panel.last_date).days),
            "bars_caveat": "the bar panel is survivor-selected (CLAUDE.md 2026-09-22); a dead name's "
                           "claim is UNGRADEABLE, and control cells exclude names with no exit bar",
            "revisions_path": str(rev_path) if rev_path else ("injected" if revisions is not None else None),
            "yf_leg_start": yf_start if include_yf else None},
        "pit_rules": {
            "known_from": "first session that OPENS after publication (ET; before 09:30 on a session "
                          "day = that session); date-only stamps -> the NEXT session",
            "entry": f"{ENTRY_PRICE} of the entry session", "exit": f"{EXIT_PRICE} of session entry+h-1",
            "horizons_sessions": list(HORIZONS), "benchmark": BENCHMARK,
            "matched_control": "equal-weight mean of every other name in the unit's matched_twins cell "
                               "(size band x vol_63 tercile x mom_252_21 tercile) as of the close before "
                               "entry; fallback band_vol -> band -> any (control_level on each row)",
            "mw_consensus_dated_by": "first_seen_utc (when Aegis saw the page), so today's pages are OPEN",
            "archive_articles": "graded from their publication time: a historical evaluation, not a "
                                "forward forecast; the LLM that extracted the claim read it after the "
                                "fact (lookahead-propensity owed, CLAUDE.md S53)"},
        "closed_not_rederived": {
            "broker_identity": "320,809 revisions, hit 50.1% (5d) / 50.2% (21d), firm skill rho -0.11",
            "first_mover_raises": "-0.06% at 21d PIT (t -0.26); the +1.34% version was look-ahead",
            "skill_mom": "analyst-skill filter edge is 2025 only (-18.1 pp ex-2025)",
            "where": "docs/reviews/ADJUDICATION_2026-09-26_WAVE1.md, ..._WAVE2_D_E.md"},
        "verdict_rules": {
            "TOO_FEW": f"< {MIN_DATE_BLOCKS} publication dates graded",
            "ALPHA_DETECTED": f"clustered t vs matched control >= {T_CRIT} AND net of the source's "
                              f"common drift >= {T_CRIT}, leave-one-month-out worst > 0, top-5 share < 1",
            "BETA_EXPLAINS": f"t vs SPY >= {T_CRIT} but vs matched control < {T_CRIT}; OR t vs control "
                             f">= {T_CRIT} but net of the source's common drift < {T_CRIT}",
            "CANNOT_DISTINGUISH": "otherwise (anti_signal flags t <= -2)",
            "neutral_stance": f"hit = |excess vs SPY| < 1 sigma*sqrt(h); ALPHA_DETECTED only if the "
                              f"Wilson lower bound > {NEUTRAL_NULL_HIT}"},
        "units": unit_state_counts(df),
        "cells": cells,
        "winner_vs_loser": wl,
        "proposed_source_weights": proposed_weights(cells),
        "proposed_source_weights_status": "PROPOSAL ONLY -- not read by policy_state, the sim or any "
                                          "live weight; zero for every cell that is not ALPHA_DETECTED",
        "n_yf_units": len(yf_units), "n_dj_units": len(dj_units), "dj_unit_ids": dj_ids,
        "dj_unit_rows": _dj_rows(df),
    }
    if write:
        from backend.services import disk_guard as DG
        od = Path(out_dir) if out_dir else default_out_dir()
        od.mkdir(parents=True, exist_ok=True)
        path = od / f"source_scorecard_{run_id}.json"
        DG.atomic_write_json(path, receipt)
        receipt["_path"] = str(path)
    return receipt


def _dj_rows(df: pd.DataFrame) -> list[dict]:
    """Per Dow Jones unit and horizon: our returns and states only -- no article
    text, no consensus numbers (Dow Jones / FactSet content stays local)."""
    if not len(df):
        return []
    d = df[df["source"] != YF_SOURCE]
    keep = ["unit_id", "source", "column", "claim_type", "ticker", "direction", "pub_date",
            "entry_date", "time_basis", "h", "state", "raw", "ex_spy", "ex_ctrl", "signed_ctrl",
            "hit", "control_level", "pre_z_5"]
    keep = [c for c in keep if c in d]
    return [{k: (_f(v) if isinstance(v, (float, np.floating)) else v) for k, v in r.items()}
            for r in d[keep].to_dict("records")]


def format_table(receipt: dict, *, min_graded: int = 0) -> str:
    lines = [f"SOURCE SCORECARD run {receipt['run_id']}  (bars through "
             f"{receipt['inputs']['bars_last_date']})",
             f"new_rows_since_last_run: {receipt['new_rows_since_last_run']}",
             f"{'source|column|claim_type':70s} {'h':>3s} {'n':>6s} {'tick':>5s} {'dates':>5s} "
             f"{'hit':>6s} {'mean_ctrl':>9s} {'se_cl':>7s} {'mde':>7s} {'t':>6s}  verdict"]
    for c in receipt["cells"]:
        if c["n_graded"] < min_graded:
            continue
        key = f"{c['source']}|{c['column']}|{c['claim_type']}"
        def s(v: Any, fmt: str) -> str:
            return format(v, fmt) if isinstance(v, (int, float)) else "-"
        lines.append(f"{key:70s} {c['h']:>3d} {c['n_graded']:>6d} {c['n_tickers']:>5d} "
                     f"{c['n_pub_dates']:>5d} {s(c.get('hit_rate'), '6.3f'):>6s} "
                     f"{s(c.get('mean_signed_ctrl'), '9.4f'):>9s} {s(c.get('se_clustered'), '7.4f'):>7s} "
                     f"{s(c.get('mde'), '7.4f'):>7s} {s(c.get('t_ctrl'), '6.2f'):>6s}  {c['verdict']}"
                     + (f" (need {c.get('n_dates_needed_for_target_mde')} dates)"
                        if c["verdict"] == "TOO_FEW" and c.get("n_dates_needed_for_target_mde") else ""))
    return "\n".join(lines)
