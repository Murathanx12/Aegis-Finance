"""CH-13: the daily discovery-failure autopsy.

For one session D: which names moved most AGAINST THE MARKET (up and down), and
for each of them -- did Aegis look at the name before D's open, and did a dated
headline or filing naming it exist before D's open?

WHY (docs/AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md §4.3; CLAUDE.md rules 2 and 4)
==========================================================================================
"What were today's biggest idiosyncratic winners and losers across the whole
market, what evidence existed BEFORE their move, and did AEGIS generate the
name at all? A miss here is an opportunity-discovery failure, and it becomes a
research task for the overnight queue." Explaining a winner afterwards is
trivial; the autopsy only counts what was dated before the open. Losers are
studied as hard as winners: the screen keeps the same number on each side.

WHAT ALREADY EXISTED, AND WHY THIS IS NOT A REWRITE OF IT
=========================================================
`scripts/night_missed_opportunity.py` (J2) screens a trailing 21-session window
for the best 5-session excess run and checks seven precursor classes. It ran
once (2026-09-22). It answers a different question -- a month's biggest runs,
not one session's biggest events -- and it has no candidate/forecast ladder,
no dated headline, no weekly count and no queue output. This module reads the
decision path the way J2 does (day contracts; AGENCY_BOOK:* rows are not names)
and keeps its NOT_HELD discipline, and adds the per-session view.

THE LADDER (highest rung reached, everything dated strictly before D's open)
===========================================================================
* NOT_IN_UNIVERSE -- the ranker's own floors (xs_ranker MIN_PRICE / MAX_PRICE /
  MIN_MEDIAN_DOLLAR_VOL over 63 sessions / MIN_HISTORY_SESSIONS) on bars before D
  would not admit it. This is an APPROXIMATION of `xs_ranker.mark_eligible`
  (same constants; the vol/momentum notna conditions are implied by the history
  floor) and the receipt says so.
* IN_UNIVERSE_NOT_CANDIDATE -- admissible, but neither the funnel snapshot in
  force at the open nor any day contract written before the open named it.
* CANDIDATE_NOT_FORECAST -- named by the funnel or a contract, no live forecast.
* FORECAST -- a `predictions.jsonl` row made before the open, inside the
  lookback, not resolved before D. Its direction is compared with D's move as a
  DESCRIPTION; the forecast resolves on its own horizon, not on D.

KNOWABLE, independently of the ladder
=====================================
* KNOWABLE_OVERNIGHT -- a corpus row whose `tickers` names the company and that
  Aegis FIRST SAW in [previous close, D open). `first_seen_utc` is the clock:
  a story published at 08:00 that we fetched at 10:00 was public, not ours.
* KNOWABLE_EARLIER -- the same in the `AUTOPSY_KNOWABLE_LOOKBACK_DAYS` before.
* NO_HEADLINE_IN_CORPUS -- the overnight window held enough corpus rows to be
  read, and none named the company. This is "our corpus held nothing", never
  "nothing was knowable".
* UNKNOWN -- the overnight window's corpus is empty or thin. An empty corpus day
  says nothing about the world.
Quote/estimates pages the reader visited are attention, not precursors, and
never make a name KNOWABLE (`config.AUTOPSY_NOT_NEWS_TAGS`).

"MISSED BUT KNOWABLE" = not FORECAST, and KNOWABLE (either tier).

DESCRIPTIVE ONLY. Nothing here says a move was predictable: a headline that
preceded a move is the seed of a hypothesis (written to the research queue in
hyp_lab's field shape), and the matched non-mover is owed before it is one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import warnings
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from backend import config as C

NY = ZoneInfo("America/New_York")
SCHEMA = "discovery-autopsy/1"
BENCH = "SPY"

NOT_IN_UNIVERSE = "NOT_IN_UNIVERSE"
IN_UNIVERSE_NOT_CANDIDATE = "IN_UNIVERSE_NOT_CANDIDATE"
CANDIDATE_NOT_FORECAST = "CANDIDATE_NOT_FORECAST"
FORECAST = "FORECAST"
LADDER = (NOT_IN_UNIVERSE, IN_UNIVERSE_NOT_CANDIDATE, CANDIDATE_NOT_FORECAST, FORECAST)

KNOWABLE_OVERNIGHT = "KNOWABLE_OVERNIGHT"
KNOWABLE_EARLIER = "KNOWABLE_EARLIER"
NO_HEADLINE_IN_CORPUS = "NO_HEADLINE_IN_CORPUS"
UNKNOWN = "UNKNOWN"
KNOWABLE_STATES = (KNOWABLE_OVERNIGHT, KNOWABLE_EARLIER)

DIRECTIONAL_OBSERVABLES = ("return_sign", "beats_benchmark", "direction")

# refusal codes -- each is a red, non-zero exit in the CLI
PANEL_MISSING = "PANEL_MISSING"
PANEL_STALE = "PANEL_STALE"
NOT_A_SESSION = "NOT_A_SESSION"
THIN_PANEL = "THIN_PANEL"
NO_BENCHMARK = "NO_BENCHMARK"
LEDGER_MISSING = "LEDGER_MISSING"
FUNNEL_MISSING = "FUNNEL_MISSING"
DECISIONS_MISSING = "DECISIONS_MISSING"
DIGEST_MISSING = "DIGEST_MISSING"
CORPUS_MISSING = "CORPUS_MISSING"
CIK_MAP_MISSING = "CIK_MAP_MISSING"
NO_MOVERS = "NO_MOVERS"
LOOKAHEAD = "LOOKAHEAD"
OUT_INSIDE_DATA_ROOT = "OUT_INSIDE_DATA_ROOT"


class AutopsyRefused(RuntimeError):
    """The autopsy will not print a mover list it cannot support.

    A stale or thin panel would otherwise print "no movers" -- the quiet zero
    this repository keeps paying for.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# ───────────────────────────────────────────────────────── small helpers

def _utc(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        return None
    return d.astimezone(timezone.utc)


def _iso(d: Optional[datetime]) -> Optional[str]:
    return None if d is None else d.astimezone(timezone.utc).isoformat(timespec="seconds")


def _r(x: Any, n: int = 6) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, n) if np.isfinite(v) else None


def _sha(*parts: Any, n: int = 16) -> str:
    h = hashlib.sha256("\x1f".join(json.dumps(p, sort_keys=True, default=str)
                                   for p in parts).encode("utf-8"))
    return h.hexdigest()[:n]


def _as_list(v: Any) -> list:
    """Corpus `tickers`/`entity_tags` are lists; some older rows stored the
    list's repr ("['VRT', 'ETN']"), parsed here without evaluating anything."""
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [p.strip().strip("'\"") for p in inner.split(",") if p.strip().strip("'\"")]
    return []


def norm_ticker(t: Any) -> str:
    """One spelling for share classes: SEC writes BRK-B, the bars panel BRK.B."""
    return str(t or "").strip().upper().replace("-", ".")


def load_cik_map(path: Path) -> dict[int, str]:
    """`official/company_tickers.json` ({"t": stamp, "map": {cik: ticker}}) -> {int cik: ticker}."""
    p = Path(path)
    if not p.is_file():
        raise AutopsyRefused(CIK_MAP_MISSING, f"no CIK map at {p}: SEC filings carry a CIK, "
                                              f"not a ticker, so none could name a mover")
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise AutopsyRefused(CIK_MAP_MISSING, f"unreadable CIK map {p}: {e}") from e
    raw = obj.get("map") if isinstance(obj, dict) else None
    if not isinstance(raw, dict) or not raw:
        raise AutopsyRefused(CIK_MAP_MISSING, f"CIK map {p} holds no `map` rows")
    out: dict[int, str] = {}
    for k, v in raw.items():
        try:
            out[int(k)] = norm_ticker(v)
        except (TypeError, ValueError):
            continue
    return out


def session_open_utc(d: date) -> datetime:
    """09:30 America/New_York on `d`, as UTC (the open is 09:30 on half days too)."""
    return datetime.combine(d, time(9, 30), tzinfo=NY).astimezone(timezone.utc)


def session_close_utc(d: date) -> datetime:
    """The exchange calendar's real close (early closes included). Raises when
    the calendar cannot say -- a 16:00 guess is the bug `market_sessions` replaced."""
    from backend.services import market_sessions as MS
    c = MS.session_close_utc(d)
    if c is None:
        raise AutopsyRefused(NOT_A_SESSION, f"{d} is not an XNYS session")
    return c


def latest_closed_session(now: datetime) -> date:
    """The most recent XNYS session whose close is at or before `now`."""
    from backend.services import market_sessions as MS
    d = now.astimezone(NY).date()
    for _ in range(15):
        c = MS.session_close_utc(d) if MS.is_session(d) else None
        if c is not None and c <= now:
            return d
        d -= timedelta(days=1)
    raise AutopsyRefused(NOT_A_SESSION, f"no closed session in the 15 days before {now}")


def input_stat(path: Path) -> dict:
    """Size of an input (age is printed against the open where a stamp exists)."""
    p = Path(path)
    out: dict = {"path": str(p), "exists": p.exists()}
    if not p.exists():
        return out
    if p.is_dir():
        files = [f for f in p.iterdir() if f.is_file()]
        out["n_files"] = len(files)
        out["newest_file"] = max((f.name for f in files), default=None)
    else:
        out["bytes"] = p.stat().st_size
    return out


# ───────────────────────────────────────────────────────── 1. the movers

def load_bars(path: Path, start: date, end: Optional[date] = None) -> pd.DataFrame:
    """symbol, date, close, volume for [start, end]: columns and filters, never the wide panel."""
    p = Path(path)
    if not p.is_file():
        raise AutopsyRefused(PANEL_MISSING, f"no bars panel at {p}")
    flt = [("date", ">=", pd.Timestamp(start))]
    if end is not None:
        flt.append(("date", "<=", pd.Timestamp(end)))
    b = pd.read_parquet(p, columns=["symbol", "date", "close", "volume"], filters=flt)
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    return b


def history_counts(path: Path) -> pd.DataFrame:
    """symbol, date only -- for `sessions_seen` (the ranker's history floor) at any D."""
    p = Path(path)
    if not p.is_file():
        raise AutopsyRefused(PANEL_MISSING, f"no bars panel at {p}")
    d = pd.read_parquet(p, columns=["symbol", "date"])
    d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    return d


def panel_facts(history: pd.DataFrame) -> dict:
    """Last date, symbol count and names per day of the WHOLE panel."""
    last = history["date"].max()
    per_day = history.groupby("date")["symbol"].nunique()
    return {"last_date": None if pd.isna(last) else last.date().isoformat(),
            "first_date": None if history.empty else history["date"].min().date().isoformat(),
            "n_symbols": int(history["symbol"].nunique()), "n_rows": int(len(history)),
            "names_per_day_tail": {k.date().isoformat(): int(v)
                                   for k, v in per_day.tail(12).items()}}


def _ranker_floors() -> dict:
    from backend.services import xs_ranker as XR
    return {"min_price": float(XR.MIN_PRICE), "max_price": float(XR.MAX_PRICE),
            "min_median_dollar_vol_63": float(XR.MIN_MEDIAN_DOLLAR_VOL),
            "min_history_sessions": int(XR.MIN_HISTORY_SESSIONS),
            "index_proxies": sorted(XR.INDEX_PROXIES)}


def screen_movers(bars: pd.DataFrame, day: date, *, history: Optional[pd.DataFrame] = None,
                  top_k: Optional[int] = None) -> dict:
    """The day's largest residual moves vs SPY, both sides, with every count printed.

    residual_D = r_D - beta * r_SPY,D, beta and the residual sigma estimated
    over the trailing `AUTOPSY_BETA_WINDOW_SESSIONS` ending D-1; z = residual / sigma.
    """
    k = int(C.AUTOPSY_TOP_K_PER_SIDE if top_k is None else top_k)
    D = pd.Timestamp(day).normalize()
    if bars.empty:
        raise AutopsyRefused(PANEL_STALE, f"the bars panel holds no rows; D={day}")
    last = bars["date"].max()
    if last < D:
        raise AutopsyRefused(PANEL_STALE, f"the bars panel ends {last.date()}, before D={day}; "
                                          f"a stale panel must not print 'no movers'")
    spy = bars[bars["symbol"] == BENCH]
    if spy.empty:
        raise AutopsyRefused(NO_BENCHMARK, f"no {BENCH} rows: an excess return with no "
                                           f"benchmark is a raw return wearing its label")
    cal = sorted(pd.Timestamp(x) for x in spy["date"].unique())
    if D not in set(cal):
        raise AutopsyRefused(NOT_A_SESSION, f"{BENCH} has no bar on {day}: not a session, "
                                            f"or the benchmark is missing that day")
    on_day = int(bars.loc[bars["date"] == D, "symbol"].nunique())
    floor = int(C.AUTOPSY_MIN_NAMES_ON_DAY)
    if on_day < floor:
        raise AutopsyRefused(THIN_PANEL, f"{on_day} names have a bar on {day}; the floor is "
                                         f"{floor} (a partial refresh is not a quiet day)")
    i = cal.index(D)
    if i < 1:
        raise AutopsyRefused(THIN_PANEL, f"no session before {day} in the loaded bars")
    W = int(C.AUTOPSY_BETA_WINDOW_SESSIONS)
    need = max(W, 63, int(C.AUTOPSY_DOLLAR_VOL_SESSIONS)) + 1
    lo = max(0, i - need)
    cal_w = cal[lo:i + 1]
    b = bars[bars["date"].isin(cal_w)]
    px = b.pivot_table(index="date", columns="symbol", values="close", aggfunc="last"
                       ).reindex(cal_w)
    dv = (b.assign(dv=b["close"] * b["volume"])
          .pivot_table(index="date", columns="symbol", values="dv", aggfunc="last")
          .reindex(cal_w))
    ret = px.pct_change(fill_method=None)
    prev = cal[i - 1]
    r_d = ret.loc[D]
    m_d = float(r_d[BENCH])
    if not np.isfinite(m_d):
        raise AutopsyRefused(NO_BENCHMARK, f"{BENCH} has no return on {day} (no bar on "
                                           f"{prev.date()}): no market to net the move against")
    trail = ret.loc[cal[max(lo + 1, i - W):i]]            # returns ending D-1
    M = trail[BENCH].to_numpy(dtype=float)
    syms = [s for s in ret.columns if s != BENCH]
    X = trail[syms].to_numpy(dtype=float)
    valid = np.isfinite(X) & np.isfinite(M)[:, None]
    n_obs = valid.sum(axis=0)
    Xv = np.where(valid, X, np.nan)
    Mv = np.where(valid, M[:, None], np.nan)
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)       # all-NaN columns
        mx, mm = np.nanmean(Xv, axis=0), np.nanmean(Mv, axis=0)
        cov = np.nanmean((Xv - mx) * (Mv - mm), axis=0)
        var = np.nanmean((Mv - mm) ** 2, axis=0)
        beta_est = cov / var
        full = n_obs >= int(C.AUTOPSY_BETA_MIN_OBS)
        beta = np.where(full & np.isfinite(beta_est), beta_est, 1.0)
        sigma = np.nanstd(Xv - beta * Mv, axis=0, ddof=1)
        sigma = np.where(n_obs >= int(C.AUTOPSY_SIGMA_MIN_OBS), sigma, np.nan)
        rd = r_d[syms].to_numpy(dtype=float)
        resid = rd - beta * m_d
        z = resid / sigma
        close_prev = px.loc[prev, syms].to_numpy(dtype=float)
        close_d = px.loc[D, syms].to_numpy(dtype=float)
        dv_win = dv.loc[cal[max(lo, i - int(C.AUTOPSY_DOLLAR_VOL_SESSIONS)):i], syms]
        med_dv = dv_win.median(axis=0, skipna=True).to_numpy(dtype=float)
        dv63 = dv.loc[cal[max(lo, i - 63):i], syms]
        med_dv63 = np.where(dv63.notna().sum(axis=0).to_numpy() >= 40,
                            dv63.median(axis=0, skipna=True).to_numpy(dtype=float), np.nan)

    if history is not None:
        seen = (history[history["date"] < D].groupby("symbol").size()
                .reindex(syms).fillna(0).astype(int).to_numpy())
        seen_basis = "bars in the full panel dated before D"
    else:
        seen = px.loc[:prev, syms].notna().sum(axis=0).to_numpy()
        seen_basis = "LOWER BOUND: bars in the loaded window only"
    fl = _ranker_floors()

    priced = np.isfinite(rd) & np.isfinite(close_prev)
    has_sigma = np.isfinite(sigma) & (np.nan_to_num(sigma) > 0)
    not_proxy = np.array([s not in fl["index_proxies"] for s in syms], dtype=bool)
    with np.errstate(invalid="ignore"):
        tradable = ((np.nan_to_num(close_prev) >= float(C.AUTOPSY_MIN_PRICE))
                    & (np.nan_to_num(med_dv) >= float(C.AUTOPSY_MIN_DOLLAR_VOL)))
        base = priced & has_sigma & not_proxy & tradable
        big = ((np.abs(np.nan_to_num(z)) >= float(C.AUTOPSY_MIN_ABS_Z))
               & (np.abs(np.nan_to_num(resid)) >= float(C.AUTOPSY_MIN_ABS_RESID)))
        elig = ((np.nan_to_num(close_prev) >= fl["min_price"])
                & (np.nan_to_num(close_prev) <= fl["max_price"])
                & (np.nan_to_num(med_dv63) >= fl["min_median_dollar_vol_63"])
                & (seen >= fl["min_history_sessions"]) & not_proxy)
    key = z if str(C.AUTOPSY_RANK_BY) == "z" else resid

    def _row(j: int, side: str) -> dict:
        return {"ticker": str(syms[j]), "side": side,
                "ret_raw": _r(rd[j]), "ret_spy": _r(m_d), "beta": _r(beta[j], 4),
                "beta_basis": ("ols_trailing" if bool(full[j]) else "fallback_1.0"),
                "n_obs": int(n_obs[j]), "resid": _r(resid[j]), "sigma": _r(sigma[j]),
                "z": _r(z[j], 3), "close_prev": _r(close_prev[j], 4), "close_d": _r(close_d[j], 4),
                "median_dollar_vol": _r(med_dv[j], 0), "median_dollar_vol_63": _r(med_dv63[j], 0),
                "sessions_seen": int(seen[j]), "ranker_eligible": bool(elig[j])}

    cand = np.where(base & big)[0]
    ups = sorted([j for j in cand if resid[j] > 0], key=lambda j: -key[j])[:k]
    downs = sorted([j for j in cand if resid[j] < 0], key=lambda j: key[j])[:k]
    movers = [_row(j, "UP") for j in ups] + [_row(j, "DOWN") for j in downs]
    if not movers:
        raise AutopsyRefused(NO_MOVERS, f"no name on {day} cleared |z| >= {C.AUTOPSY_MIN_ABS_Z} "
                                        f"and |resid| >= {C.AUTOPSY_MIN_ABS_RESID} among "
                                        f"{int(base.sum())} screened: across a whole market "
                                        f"that is a broken input, not a quiet day")
    return {
        "movers": movers,
        "screen": {
            "session": D.date().isoformat(), "prev_session": prev.date().isoformat(),
            "benchmark": BENCH, "ret_spy": _r(m_d),
            "n_names_with_bar_on_d": on_day, "min_names_on_day": floor,
            "n_names_in_window": len(syms), "n_priced_d_and_prev": int(priced.sum()),
            "n_with_sigma": int((priced & has_sigma).sum()),
            "n_over_price_and_dollar_vol_floors": int(base.sum()),
            "n_clearing_z_and_resid": int((base & big).sum()),
            "n_up_kept": len(ups), "n_down_kept": len(downs), "top_k_per_side": k,
            "rank_by": str(C.AUTOPSY_RANK_BY), "min_abs_z": float(C.AUTOPSY_MIN_ABS_Z),
            "min_abs_resid": float(C.AUTOPSY_MIN_ABS_RESID),
            "min_price": float(C.AUTOPSY_MIN_PRICE), "min_dollar_vol": float(C.AUTOPSY_MIN_DOLLAR_VOL),
            "dollar_vol_sessions": int(C.AUTOPSY_DOLLAR_VOL_SESSIONS),
            "beta_window_sessions": W, "beta_min_obs": int(C.AUTOPSY_BETA_MIN_OBS),
            "n_beta_fallback": int((base & ~full).sum()),
            "resid_is": "r_D - beta * r_SPY,D; beta, sigma over trailing returns ending D-1",
            "ranker_floors": fl, "sessions_seen_basis": seen_basis,
            "ranker_eligible_is": ("APPROXIMATION of xs_ranker.mark_eligible on bars before D: "
                                   "same price / 63-session median dollar volume / history floors"),
        },
    }


# ─────────────────────────────────────────── 2. what Aegis generated before D

def funnel_in_force(funnel_path: Path, history_dir: Path, before: datetime) -> dict:
    """The newest funnel snapshot whose OWN `generated_at` precedes the open."""
    from backend.services import investment_committee as IC
    paths = [Path(funnel_path)]
    if Path(history_dir).is_dir():
        paths += sorted(Path(history_dir).glob("funnel_*.json"))
    snaps: dict[str, dict] = {}
    unreadable = []
    for p in paths:
        if not p.is_file():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unreadable.append(str(p))
            continue
        g = _utc(d.get("generated_at"))
        if g is None or g >= before:
            continue
        snaps.setdefault(_iso(g), {"path": str(p), "generated_at": _iso(g),
                                   "tickers": sorted({norm_ticker(c.get("ticker"))
                                                      for c in d.get("candidates") or []
                                                      if c.get("ticker")})})
    out = {"n_snapshot_files": len(paths), "unreadable": unreadable,
           "stale_after_days": int(IC.FUNNEL_STALE_DAYS)}
    if not snaps:
        return {**out, "state": "NOT_HELD", "tickers": [],
                "detail": "no funnel snapshot dated before the open"}
    best = snaps[max(snaps)]
    age = IC._funnel_age_days(best["generated_at"], now=before)
    return {**out, "state": "PRESENT", **best, "age_days_at_open": _r(age, 2),
            "staleness": IC.funnel_staleness(best["generated_at"], now=before)}


def contract_names(decisions_dir: Path, day: date, before: datetime,
                   lookback_days: Optional[int] = None) -> dict:
    """tickers named by day contracts WRITTEN before the open (J2 reads rows the same way)."""
    lb = int(C.AUTOPSY_CONTRACT_LOOKBACK_DAYS if lookback_days is None else lookback_days)
    root = Path(decisions_dir)
    by: dict[str, list[dict]] = {}
    used, after_open, missing = [], [], []
    for n in range(lb + 1):
        d = day - timedelta(days=n)
        p = root / f"{d.isoformat()}.json"
        if not p.is_file():
            missing.append(d.isoformat())
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            missing.append(d.isoformat())
            continue
        w = _utc(obj.get("written_utc"))
        if w is None or w >= before:
            after_open.append({"path": str(p), "written_utc": obj.get("written_utc")})
            continue
        used.append({"path": str(p), "written_utc": _iso(w), "n_rows": len(obj.get("rows") or [])})
        for row in obj.get("rows") or []:
            t = norm_ticker(row.get("ticker"))
            if not t or ":" in t:
                continue
            by.setdefault(t, []).append({"date": d.isoformat(), "written_utc": _iso(w),
                                         "direction": row.get("direction") or row.get("verdict"),
                                         "authority": row.get("authority"),
                                         "signal": row.get("signal")})
    return {"by_ticker": by, "files_used": used, "files_written_after_open": after_open,
            "days_without_contract": missing, "lookback_days": lb}


def digest_names(digest_dir: Path, before: datetime, lookback_days: Optional[int] = None) -> dict:
    """tickers in world-digest themes stamped before the open (`top_tickers`)."""
    lb = int(C.AUTOPSY_DIGEST_LOOKBACK_DAYS if lookback_days is None else lookback_days)
    lo = before - timedelta(days=lb)
    by: dict[str, list[dict]] = {}
    used = []
    root = Path(digest_dir)
    for p in (sorted(root.glob("world_digest_*.json")) if root.is_dir() else []):
        stamp = p.stem.replace("world_digest_", "")
        try:
            ts = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if not (lo <= ts < before):
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        used.append({"path": str(p), "stamp": _iso(ts), "n_themes": len(obj.get("themes") or [])})
        for th in obj.get("themes") or []:
            for t in th.get("top_tickers") or []:
                by.setdefault(norm_ticker(t), []).append({"stamp": _iso(ts),
                                                         "theme": str(th.get("title") or "")[:160]})
    return {"by_ticker": by, "digests_used": used, "lookback_days": lb}


def index_forecasts(pred_path: Path, tickers: Iterable[str],
                    windows: dict[str, tuple[datetime, date]],
                    lookback_days: Optional[int] = None) -> dict:
    """ONE read-only streaming pass over `predictions.jsonl` (rewritten in place:
    never loaded whole). `windows` maps a session id -> (open_utc, session date).
    Returns {"by_day": {day: {ticker: [rows]}}, "stats": {...}}."""
    p = Path(pred_path)
    if not p.is_file():
        raise AutopsyRefused(LEDGER_MISSING, f"no forecast ledger at {p}: the FORECAST rung "
                                             f"cannot be told from CANDIDATE_NOT_FORECAST")
    lb = timedelta(days=int(C.AUTOPSY_FORECAST_LOOKBACK_DAYS if lookback_days is None
                            else lookback_days))
    want = {norm_ticker(t) for t in tickers}
    by_day: dict[str, dict[str, list]] = {k: {} for k in windows}
    n = bad = no_stamp = 0
    newest: Optional[datetime] = None
    size = p.stat().st_size
    with p.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            n += 1
            try:
                row = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if not isinstance(row, dict):
                bad += 1
                continue
            made = _utc(row.get("made_at"))
            if made is None:
                no_stamp += 1
                continue
            if newest is None or made > newest:
                newest = made
            t = norm_ticker(row.get("ticker"))
            if t not in want:
                continue
            ra = str(row.get("resolves_after") or "")[:10] or None
            for k, (op, d) in windows.items():
                if not (op - lb <= made < op):
                    continue
                if ra is not None and ra < d.isoformat():
                    continue
                by_day[k].setdefault(t, []).append({
                    "prediction_id": row.get("prediction_id"), "made_at": _iso(made),
                    "specialist": row.get("specialist"), "observable": row.get("observable"),
                    "horizon_days": row.get("horizon_days"), "probability": row.get("probability"),
                    "benchmark": row.get("benchmark"), "resolves_after": ra})
    return {"by_day": by_day,
            "stats": {"path": str(p), "bytes": size, "lines": n, "unparseable": bad,
                      "no_made_at": no_stamp, "newest_made_at": _iso(newest),
                      "lookback_days": lb.days, "read": "streamed line by line, read-only"}}


def forecast_direction(row: dict) -> str:
    obs = str(row.get("observable") or "")
    try:
        p = float(row.get("probability"))
    except (TypeError, ValueError):
        return "UNSTATED"
    if obs not in DIRECTIONAL_OBSERVABLES:
        return "NON_DIRECTIONAL"
    return "UP" if p > 0.5 else ("DOWN" if p < 0.5 else "FLAT")


# ─────────────────────────────────────────────────── 3. the corpus (knowable)

class Corpus:
    """Dated rows of `news_corpus/<source>/<YYYY-MM-DD>.jsonl`, read lazily and cached.

    The clock is `first_seen_utc` (when Aegis held the row). A row with no
    first-seen stamp falls back to `published_utc` and is flagged.

    SEC 8-K rows carry `tickers: []` and a `cik:<10 digits>` entity tag; without
    `cik_map` (int CIK -> ticker, `official/company_tickers.json`) no filing
    could ever name a company, and every filing-led move would read as
    NO_HEADLINE_IN_CORPUS.
    """

    def __init__(self, root: Path, cik_map: Optional[dict[int, str]] = None) -> None:
        self.root = Path(root)
        self.cik_map = dict(cik_map or {})
        self.n_cik_resolved = 0
        self.sources = (sorted(p.name for p in self.root.iterdir()
                               if p.is_dir() and not p.name.startswith("_"))
                        if self.root.is_dir() else [])
        self._cache: dict[tuple[str, str], list[dict]] = {}

    def _day(self, src: str, day: str) -> list[dict]:
        key = (src, day)
        if key in self._cache:
            return self._cache[key]
        f = self.root / src / f"{day}.jsonl"
        rows: list[dict] = []
        if f.is_file():
            with f.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(o, dict):
                        continue
                    fs = _utc(o.get("first_seen_utc"))
                    pub = _utc(o.get("published_utc"))
                    known = fs or pub
                    if known is None:
                        continue
                    tags = [str(t) for t in _as_list(o.get("entity_tags"))]
                    tickers = {norm_ticker(t) for t in _as_list(o.get("tickers"))}
                    for t in tags:
                        if t.startswith("cik:"):
                            try:
                                hit = self.cik_map.get(int(t[4:]))
                            except ValueError:
                                hit = None
                            if hit and hit not in tickers:
                                tickers.add(hit)
                                tags.append(f"resolved:cik_map:{hit}")
                                self.n_cik_resolved += 1
                    rows.append({"source": src, "title": str(o.get("title") or "")[:240],
                                 "known_at": known,
                                 "clock": "first_seen_utc" if fs else "published_utc",
                                 "published_utc": _iso(pub),
                                 "tickers": sorted(t for t in tickers if t),
                                 "tags": tags,
                                 "url": str(o.get("url") or "")[:200]})
        self._cache[key] = rows
        return rows

    def window(self, lo: datetime, hi: datetime) -> dict:
        """Rows known in [lo, hi), with per-source counts. Files are named by a
        UTC day; one day either side is read and the stamp decides."""
        days, d = [], (lo - timedelta(days=1)).date()
        while d <= (hi + timedelta(days=1)).date():
            days.append(d.isoformat())
            d += timedelta(days=1)
        rows, per_src = [], {}
        files_present = 0
        for s in self.sources:
            for dd in days:
                if (self.root / s / f"{dd}.jsonl").is_file():
                    files_present += 1
                for r in self._day(s, dd):
                    if lo <= r["known_at"] < hi:
                        rows.append(r)
                        per_src[s] = per_src.get(s, 0) + 1
        by: dict[str, list[dict]] = {}
        for r in rows:
            for t in set(r["tickers"]):
                by.setdefault(t, []).append(r)
        return {"lo": _iso(lo), "hi": _iso(hi), "n_rows": len(rows),
                "n_ticker_tagged": sum(1 for r in rows if r["tickers"]),
                "per_source": dict(sorted(per_src.items())), "files_present": files_present,
                "by_ticker": by}


def _evidence(r: dict) -> dict:
    kind = "FILING" if r["source"].startswith("sec_") else "NEWS"
    items = sorted({t.split(":", 1)[1] for t in r["tags"] if t.startswith("8-K:")})
    basis = [t for t in r["tags"] if t.startswith("resolved:") or t.startswith("cik:")][:3]
    return {"source": r["source"], "kind": kind, "title": r["title"],
            "known_at": _iso(r["known_at"]), "clock": r["clock"],
            "published_utc": r["published_utc"], "items_8k": items,
            "entity_basis": basis, "url": r["url"]}


def knowable(ticker: str, overnight: dict, earlier: dict) -> dict:
    """KNOWABLE_OVERNIGHT / KNOWABLE_EARLIER / NO_HEADLINE_IN_CORPUS / UNKNOWN."""
    not_news = set(C.AUTOPSY_NOT_NEWS_TAGS)

    def split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
        news = [r for r in rows if not (set(r["tags"]) & not_news)]
        pages = [r for r in rows if set(r["tags"]) & not_news]
        return news, pages

    on, on_pages = split(overnight["by_ticker"].get(ticker, []))
    er, er_pages = split(earlier["by_ticker"].get(ticker, []))
    covered = overnight["n_rows"] >= int(C.AUTOPSY_MIN_CORPUS_ROWS)
    if on:
        state = KNOWABLE_OVERNIGHT
    elif er:
        state = KNOWABLE_EARLIER
    elif covered:
        state = NO_HEADLINE_IN_CORPUS
    else:
        state = UNKNOWN
    hits = sorted(on + er, key=lambda r: r["known_at"])
    return {"state": state, "n_overnight": len(on), "n_earlier": len(er),
            "earliest": _evidence(hits[0]) if hits else None,
            "latest_before_open": _evidence(hits[-1]) if hits else None,
            "evidence": [_evidence(r) for r in hits[-6:]],
            "reader_pages_before_open": len(on_pages) + len(er_pages),
            "overnight_corpus_rows": overnight["n_rows"], "corpus_covered": covered}


# ─────────────────────────────────────────────────────────── 4. classify

def classify(m: dict, *, funnel: dict, contracts: dict, digest: dict,
             forecasts: dict[str, list], know: dict) -> dict:
    t = norm_ticker(m["ticker"])
    in_funnel = t in set(funnel.get("tickers") or [])
    cons = contracts["by_ticker"].get(t) or []
    fc = forecasts.get(t) or []
    dig = digest["by_ticker"].get(t) or []
    if fc:
        rung = FORECAST
    elif in_funnel or cons:
        rung = CANDIDATE_NOT_FORECAST
    elif m["ranker_eligible"]:
        rung = IN_UNIVERSE_NOT_CANDIDATE
    else:
        rung = NOT_IN_UNIVERSE
    dirs = [forecast_direction(r) for r in fc]
    directional = [d for d in dirs if d in ("UP", "DOWN")]
    latest = max(fc, key=lambda r: r["made_at"]) if fc else None
    return {**m, "ladder": rung,
            "attention": {"funnel_candidate": in_funnel,
                          "contract_rows": cons[:4], "n_contract_rows": len(cons),
                          "world_digest": dig[:3], "n_world_digest": len(dig),
                          "ranker_eligible": m["ranker_eligible"]},
            "forecasts": {"n": len(fc), "n_directional": len(directional),
                          "n_direction_agrees_with_d": sum(1 for d in directional if d == m["side"]),
                          "latest": latest,
                          "note": "direction compared with D's move descriptively; each "
                                  "forecast resolves on its own horizon"},
            "knowable": know,
            "missed_but_knowable": rung != FORECAST and know["state"] in KNOWABLE_STATES}


def summarise(rows: list[dict]) -> dict:
    return {"n_movers": len(rows),
            "by_side": {s: sum(1 for r in rows if r["side"] == s) for s in ("UP", "DOWN")},
            "by_ladder": {k: sum(1 for r in rows if r["ladder"] == k) for k in LADDER},
            "by_knowable": {k: sum(1 for r in rows if r["knowable"]["state"] == k)
                            for k in (KNOWABLE_OVERNIGHT, KNOWABLE_EARLIER,
                                      NO_HEADLINE_IN_CORPUS, UNKNOWN)},
            "n_in_universe": sum(1 for r in rows if r["ladder"] != NOT_IN_UNIVERSE),
            "n_candidate_or_forecast": sum(1 for r in rows if r["ladder"] in
                                           (CANDIDATE_NOT_FORECAST, FORECAST)),
            "n_forecast": sum(1 for r in rows if r["ladder"] == FORECAST),
            "n_missed_but_knowable": sum(1 for r in rows if r["missed_but_knowable"]),
            "n_unknown": sum(1 for r in rows if r["knowable"]["state"] == UNKNOWN)}


# ──────────────────────────────────────────────────────────── 5. one day

def assert_no_lookahead(rows: list[dict], open_d: datetime) -> None:
    """Every item a mover's row cites must be dated strictly before D's open.

    The windows already cut at the open; this re-checks the OUTPUT, because an
    autopsy that cites a post-move headline as "knowable" is the hindsight
    story rule 2 forbids, and it would read exactly like a finding.
    """
    bad = []
    for r in rows:
        k = r["knowable"]
        for e in [k.get("earliest"), k.get("latest_before_open"), *(k.get("evidence") or [])]:
            ts = _utc((e or {}).get("known_at"))
            if e and (ts is None or ts >= open_d):
                bad.append((r["ticker"], "corpus", e.get("known_at")))
        latest = r["forecasts"].get("latest")
        if latest and (_utc(latest.get("made_at")) or open_d) >= open_d:
            bad.append((r["ticker"], "forecast", latest.get("made_at")))
        for c in r["attention"].get("contract_rows") or []:
            if (_utc(c.get("written_utc")) or open_d) >= open_d:
                bad.append((r["ticker"], "contract", c.get("written_utc")))
    if bad:
        raise AutopsyRefused(LOOKAHEAD, f"{len(bad)} cited item(s) dated on/after the open "
                                        f"{_iso(open_d)}: {bad[:5]}")


def run_day(day: date, *, bars: pd.DataFrame, history: Optional[pd.DataFrame],
            paths: dict, corpus: Corpus, now: datetime,
            inputs_extra: Optional[dict] = None, top_k: Optional[int] = None) -> dict:
    """The receipt for one session. Raises AutopsyRefused; never returns an empty list quietly."""
    open_d = session_open_utc(day)
    scr = screen_movers(bars, day, history=history, top_k=top_k)
    prev = date.fromisoformat(scr["screen"]["prev_session"])
    prev_close = session_close_utc(prev)
    funnel = funnel_in_force(paths["funnel"], paths["funnel_history"], open_d)
    contracts = contract_names(paths["decisions"], day, open_d)
    digest = digest_names(paths["digest"], open_d)
    fc = index_forecasts(paths["predictions"], [m["ticker"] for m in scr["movers"]],
                         {day.isoformat(): (open_d, day)})
    forecasts_by_ticker = fc["by_day"][day.isoformat()]
    overnight = corpus.window(prev_close, open_d)
    lbk = timedelta(days=int(C.AUTOPSY_KNOWABLE_LOOKBACK_DAYS))
    earlier = corpus.window(prev_close - lbk, prev_close)
    rows = [classify(m, funnel=funnel, contracts=contracts, digest=digest,
                     forecasts=forecasts_by_ticker,
                     know=knowable(norm_ticker(m["ticker"]), overnight, earlier))
            for m in scr["movers"]]
    assert_no_lookahead(rows, open_d)

    def _drop(d: dict, *keys: str) -> dict:
        return {k: v for k, v in d.items() if k not in keys}

    extra = dict(inputs_extra or {})
    stale: list[str] = list(extra.pop("stale_inputs", []))
    if funnel.get("state") != "PRESENT":
        stale.append("funnel: no snapshot dated before the open")
    elif funnel.get("staleness"):
        stale.append(f"funnel: {funnel['age_days_at_open']} days old at the open "
                     f"(limit {funnel['stale_after_days']})")
    if day.isoformat() in contracts["days_without_contract"]:
        stale.append(f"contracts: no day contract for {day} written before the open")
    if not overnight["n_rows"] >= int(C.AUTOPSY_MIN_CORPUS_ROWS):
        stale.append(f"corpus: {overnight['n_rows']} rows overnight, under the "
                     f"{C.AUTOPSY_MIN_CORPUS_ROWS} floor -- 'no headline' reads as UNKNOWN")
    if not scr["screen"]["n_up_kept"] or not scr["screen"]["n_down_kept"]:
        stale.append("screen: one tail is empty -- the winner/loser comparison is one-sided")
    candidate_set = {
        "n_funnel": len(funnel.get("tickers") or []),
        "funnel_generated_at": funnel.get("generated_at"),
        "funnel_age_days_at_open": funnel.get("age_days_at_open"),
        "funnel_age_days_now": _r(((now - _utc(funnel["generated_at"])).total_seconds() / 86400)
                                  if funnel.get("generated_at") else None, 2),
        "n_contract_tickers": len(contracts["by_ticker"]),
        "contract_files_used": [f["path"] for f in contracts["files_used"]],
        "newest_contract_written_utc": max((f["written_utc"] for f in contracts["files_used"]),
                                           default=None),
        "n_forecast_rows_for_movers": sum(len(v) for v in forecasts_by_ticker.values()),
    }
    summary = summarise(rows)
    summary["stale_inputs"] = stale
    rec = {
        "schema": SCHEMA, "chunk": "CH-13", "licence": "PRODUCT_EXPERIMENT",
        "session": day.isoformat(), "session_open_utc": _iso(open_d),
        "prev_session": prev.isoformat(), "prev_close_utc": _iso(prev_close),
        "written_utc": _iso(now),
        "descriptive_only": ("observations, not evidence of predictability: a headline that "
                             "preceded a move is a seed, and the matched non-mover is owed"),
        "candidate_set": candidate_set,
        "screen": scr["screen"],
        "inputs": {
            **extra,
            "funnel": {**_drop(funnel, "tickers"), "n_candidates": len(funnel.get("tickers") or [])},
            "contracts": {**_drop(contracts, "by_ticker"), "n_tickers": len(contracts["by_ticker"])},
            "world_digest": {**_drop(digest, "by_ticker"), "n_tickers": len(digest["by_ticker"])},
            "forecasts": fc["stats"],
            "corpus_overnight": _drop(overnight, "by_ticker"),
            "corpus_earlier": _drop(earlier, "by_ticker"),
            "corpus_root": str(corpus.root), "corpus_sources": corpus.sources,
            "corpus_cik_resolved_rows": corpus.n_cik_resolved,
        },
        "summary": summary,
        "movers": rows,
    }
    rec["receipt_sha256"] = _sha(rec, n=64)
    return rec


# ──────────────────────────────────────────────────── 6. outputs

def render_md(rec: dict) -> str:
    s, sc = rec["summary"], rec["screen"]
    fin = rec["inputs"]["funnel"]
    co = rec["inputs"]["corpus_overnight"]
    lines = [f"# Discovery-failure autopsy {rec['session']}", "",
             f"Descriptive only: {rec['descriptive_only']}.", "",
             f"- SPY {sc['ret_spy']:+.4f}; {sc['n_names_with_bar_on_d']} names with a bar on D; "
             f"{sc['n_over_price_and_dollar_vol_floors']} over the price/dollar-volume floors; "
             f"{sc['n_clearing_z_and_resid']} cleared |z| >= {sc['min_abs_z']} and |resid| >= "
             f"{sc['min_abs_resid']}; kept {sc['n_up_kept']} up / {sc['n_down_kept']} down.",
             f"- Funnel in force at the open: {fin.get('generated_at')} "
             f"(age {fin.get('age_days_at_open')} d; {fin.get('staleness') or 'within the stale limit'}).",
             f"- Corpus overnight ({rec['prev_close_utc']} to {rec['session_open_utc']}): "
             f"{co['n_rows']} rows, {co['n_ticker_tagged']} name-tagged.",
             f"- Movers {s['n_movers']}: in universe {s['n_in_universe']}, candidate-or-forecast "
             f"{s['n_candidate_or_forecast']}, forecast {s['n_forecast']}; "
             f"**missed but knowable {s['n_missed_but_knowable']}**; UNKNOWN {s['n_unknown']}.", "",
             "| side | ticker | raw | resid | z | ladder | knowable | earliest dated item before the open |",
             "|---|---|---:|---:|---:|---|---|---|"]
    for r in rec["movers"]:
        e = r["knowable"]["earliest"]
        ev = f"{e['known_at']} {e['source']}: {e['title'][:90]}" if e else ""
        lines.append(f"| {r['side']} | {r['ticker']} | {r['ret_raw']:+.3f} | {r['resid']:+.3f} | "
                     f"{r['z']:+.1f} | {r['ladder']} | {r['knowable']['state']} | "
                     f"{ev.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def research_seed(r: dict, rec: dict, receipt_path: str) -> dict:
    """A missed-but-knowable mover as a row in hyp_lab's hypothesis field shape,
    status SEED_UNADMITTED: hyp_lab does not read this file yet."""
    e = r["knowable"]["latest_before_open"] or {}
    seed = {
        "kind": "hypothesis_seed",
        "title": (f"{str(e.get('kind') or 'item').lower()} before the open -> residual move? "
                  f"({r['ticker']} {rec['session']} {r['side']})"),
        "mechanism": ("UNSTATED: the autopsy is descriptive. A seed names a precursor observed "
                      "before one large residual move; a mechanism is owed before admission."),
        "precursor": (f"{e.get('kind')} row naming {r['ticker']} first seen {e.get('known_at')} "
                      f"({e.get('source')}; 8-K items {e.get('items_8k') or []}): "
                      f"{str(e.get('title') or '')[:160]}"),
        "separation_from_beta": ("residual vs SPY beta over the trailing "
                                 f"{rec['screen']['beta_window_sessions']} sessions ending D-1, "
                                 "scaled by the name's own residual sigma"),
        "refutation": ("among names with the same precursor class before the open, the share "
                       "with |z| >= 2 on D is no higher than among matched names without it "
                       "(matched on liquidity band and sigma)"),
        "target": "return", "family": "discovery_failure_autopsy",
        "source": "discovery_autopsy", "source_ref": receipt_path,
        "status": "SEED_UNADMITTED",
        "session": rec["session"], "ticker": r["ticker"], "side": r["side"],
        "ladder": r["ladder"], "knowable": r["knowable"]["state"],
        "resid": r["resid"], "z": r["z"], "created_utc": rec["written_utc"],
    }
    seed["seed_key"] = _sha(rec["session"], r["ticker"])
    return seed


def _jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    if not Path(path).is_file():
        return out
    with Path(path).open(encoding="utf-8") as fh:
        for ln in fh:
            try:
                o = json.loads(ln)
            except ValueError:
                continue
            if isinstance(o, dict):
                out.append(o)
    return out


def _append(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True, default=str) + "\n")


def _atomic_write(path: Path, text: str) -> None:
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    if tmp.stat().st_size == 0:
        raise OSError(f"zero-byte write to {tmp}")
    tmp.replace(path)


def write_outputs(rec: dict, out_dir: Path, run_id: str) -> dict:
    """Receipt + md, index row, research-queue seeds (deduped), weekly roll-up.

    Two receipt files: `autopsy_<D>_<run>.json` is the one cited (run id in the
    name, so a second run never overwrites a receipt someone quoted) and
    `autopsy_<D>.json` is the same bytes as the day's latest run, for readers
    that want "the autopsy of D" by name.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rec = {**rec, "run_id": run_id}
    stem = f"autopsy_{rec['session']}_{run_id}"
    jp, mp = out / f"{stem}.json", out / f"{stem}.md"
    body = json.dumps(rec, indent=1, default=str)
    _atomic_write(jp, body)
    _atomic_write(out / f"autopsy_{rec['session']}.json", body)
    _atomic_write(mp, render_md(rec))
    _append(out / "index.jsonl", [{"session": rec["session"], "run_id": run_id,
                                   "receipt": str(jp), "receipt_sha256": rec["receipt_sha256"],
                                   "written_utc": rec["written_utc"], "summary": rec["summary"]}])
    qp = out / "research_queue.jsonl"
    have = {r.get("seed_key") for r in _jsonl(qp)}
    seeds = [research_seed(r, rec, str(jp)) for r in rec["movers"] if r["missed_but_knowable"]]
    new = [s for s in seeds if s["seed_key"] not in have]
    _append(qp, new)
    wk = weekly_rollup(out, date.fromisoformat(rec["session"]))
    return {"receipt": str(jp), "latest": str(out / f"autopsy_{rec['session']}.json"),
            "markdown": str(mp), "queue": str(qp),
            "queue_rows_added": len(new), "queue_rows_already_present": len(seeds) - len(new),
            "weekly": wk["path"]}


def weekly_rollup(out_dir: Path, day: date) -> dict:
    """The ISO week's 'missed but knowable' count, from the LATEST run per session."""
    iy, iw, _ = day.isocalendar()
    latest: dict[str, dict] = {}
    for row in _jsonl(Path(out_dir) / "index.jsonl"):
        s = str(row.get("session") or "")
        try:
            sd = date.fromisoformat(s)
        except ValueError:
            continue
        if tuple(sd.isocalendar())[:2] != (iy, iw):
            continue
        if s not in latest or str(row.get("written_utc")) >= str(latest[s].get("written_utc")):
            latest[s] = row
    keys = ("n_movers", "n_in_universe", "n_candidate_or_forecast", "n_forecast",
            "n_missed_but_knowable", "n_unknown")
    days = [{"session": s, "receipt": latest[s]["receipt"],
             **{k: int(latest[s]["summary"].get(k, 0)) for k in keys}} for s in sorted(latest)]
    wk = {"schema": SCHEMA + "/weekly", "iso_week": f"{iy}-W{iw:02d}", "n_sessions": len(days),
          "totals": {k: sum(d[k] for d in days) for k in keys}, "days": days}
    path = Path(out_dir) / f"weekly_{iy}-W{iw:02d}.json"
    _atomic_write(path, json.dumps(wk, indent=1))
    wk["path"] = str(path)
    return wk


def default_paths(data_root: Path, funnel_root: Optional[Path] = None) -> dict:
    dr = Path(data_root)
    fr = Path(funnel_root) if funnel_root else dr.parent
    return {"bars": dr / "prices_2025_26" / "bars.parquet",
            "predictions": dr / "predictions.jsonl",
            "decisions": dr / "decisions",
            "digest": dr / "digest",
            "corpus": dr / "news_corpus",
            "cik_map": dr / "official" / "company_tickers.json",
            "funnel": fr / "funnel_night10.json",
            "funnel_history": fr / "funnel_history"}


# ──────────────────────────────────────────────────── 7. the daily run + CLI

#: input -> refusal code. A missing input is a red exit with its name, never
#: an empty rung: a missing forecast ledger would make every mover "not forecast".
REQUIRED_INPUTS = (("bars", PANEL_MISSING, "file"), ("predictions", LEDGER_MISSING, "file"),
                   ("funnel", FUNNEL_MISSING, "file"), ("decisions", DECISIONS_MISSING, "dir"),
                   ("digest", DIGEST_MISSING, "dir"), ("corpus", CORPUS_MISSING, "dir"),
                   ("cik_map", CIK_MAP_MISSING, "file"))


def check_inputs(paths: dict) -> dict:
    """Refuse, by name, on the first missing input; else every input's size."""
    out = {}
    for key, code, kind in REQUIRED_INPUTS:
        p = Path(paths[key])
        ok = p.is_file() if kind == "file" else p.is_dir()
        if not ok:
            raise AutopsyRefused(code, f"required input `{key}` is missing: {p}")
        out[key] = input_stat(p)
    return out


def _inside(child: Path, parent: Path) -> bool:
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def sessions_between(after: date, upto: date) -> int:
    """XNYS sessions in (after, upto]."""
    from backend.services import market_sessions as MS
    n, d = 0, after + timedelta(days=1)
    while d <= upto:
        n += int(MS.is_session(d))
        d += timedelta(days=1)
    return n


def run(data_root: Path, out_dir: Path, *, funnel_root: Optional[Path] = None,
        session: Optional[date] = None, now: Optional[datetime] = None,
        top_k: Optional[int] = None, run_id: Optional[str] = None) -> dict:
    """Read-only over `data_root`; writes only under `out_dir`. Raises AutopsyRefused."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    paths = default_paths(data_root, funnel_root)
    fr = Path(funnel_root) if funnel_root else Path(data_root).parent
    for root in (Path(data_root), fr):
        if _inside(out_dir, root):
            raise AutopsyRefused(OUT_INSIDE_DATA_ROOT, f"--out {out_dir} is inside {root}: the "
                                                       f"autopsy never writes into live data")
    sizes = check_inputs(paths)
    history = history_counts(paths["bars"])
    facts = panel_facts(history)
    if facts["last_date"] is None:
        raise AutopsyRefused(PANEL_STALE, f"the bars panel {paths['bars']} holds no rows")
    last = date.fromisoformat(facts["last_date"])
    day = session or last
    latest_closed = latest_closed_session(now)
    behind = sessions_between(last, latest_closed) if latest_closed > last else 0
    panel_age = {"panel_last_date": last.isoformat(),
                 "latest_closed_session": latest_closed.isoformat(),
                 "age_days": (now.date() - last).days,
                 "sessions_behind": behind,
                 "max_sessions_behind": int(C.AUTOPSY_PANEL_MAX_SESSIONS_BEHIND),
                 "stale": behind > int(C.AUTOPSY_PANEL_MAX_SESSIONS_BEHIND)}
    stale = []
    if panel_age["stale"]:
        stale.append(f"bars panel: ends {last}, {behind} session(s) behind the latest closed "
                     f"session {latest_closed}")
    start = day - timedelta(days=int(C.AUTOPSY_LOAD_CALENDAR_DAYS))
    bars = load_bars(paths["bars"], start, day)
    cik_map = load_cik_map(paths["cik_map"])
    corpus = Corpus(paths["corpus"], cik_map=cik_map)
    extra = {"sizes": sizes, "bars_panel": {**facts, **panel_age,
                                            "survivorship": "panel built from a dated universe "
                                            "file; dead names are under-represented"},
             "cik_map_rows": len(cik_map), "stale_inputs": stale}
    rec = run_day(day, bars=bars, history=history, paths=paths, corpus=corpus, now=now,
                  inputs_extra=extra, top_k=top_k)
    rid = run_id or now.strftime("%Y%m%dT%H%M%SZ")
    written = write_outputs(rec, out_dir, rid)
    return {"receipt": rec, "written": written}


def headline(rec: dict) -> list[str]:
    s, cs, bp = rec["summary"], rec["candidate_set"], rec["inputs"]["bars_panel"]
    return [
        f"session {rec['session']} | bars panel ends {bp['panel_last_date']}, age {bp['age_days']} d, "
        f"{bp['sessions_behind']} session(s) behind {bp['latest_closed_session']}"
        f"{' [STALE]' if bp['stale'] else ''}",
        f"candidate set: funnel {cs['n_funnel']} names generated {cs['funnel_generated_at']} "
        f"(age {cs['funnel_age_days_at_open']} d at the open, {cs['funnel_age_days_now']} d now); "
        f"contracts name {cs['n_contract_tickers']} tickers (newest {cs['newest_contract_written_utc']})",
        f"movers {s['n_movers']} (UP {s['by_side']['UP']} / DOWN {s['by_side']['DOWN']}) | "
        f"ladder {s['by_ladder']} | knowable {s['by_knowable']}",
        f"MISSED BUT KNOWABLE {s['n_missed_but_knowable']} | UNKNOWN {s['n_unknown']}",
        f"stale inputs: {s['stale_inputs'] or 'none'}",
    ]


def _parse_now(s: str) -> datetime:
    d = _utc(s)
    if d is None:
        raise argparse.ArgumentTypeError(f"--now must be an ISO timestamp with a zone: {s!r}")
    return d


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="discovery_autopsy",
                                 description="CH-13 daily discovery-failure autopsy")
    ap.add_argument("--data-root", required=True, type=Path,
                    help="the optimus data folder (read only), e.g. backend/data/optimus")
    ap.add_argument("--out", required=True, type=Path, help="output folder, outside the data root")
    ap.add_argument("--funnel-root", type=Path, default=None,
                    help="folder holding funnel_night10.json (default: data-root's parent)")
    ap.add_argument("--session", type=date.fromisoformat, default=None,
                    help="session date (default: the newest session in the bars panel)")
    ap.add_argument("--now", type=_parse_now, default=None,
                    help="ISO timestamp with zone to judge ages against (default: now)")
    ap.add_argument("--top-k", type=int, default=None)
    a = ap.parse_args(argv)
    try:
        res = run(a.data_root, a.out, funnel_root=a.funnel_root, session=a.session,
                  now=a.now, top_k=a.top_k)
    except AutopsyRefused as e:
        print(f"REFUSED {e.code}: {e.detail}", file=sys.stderr)
        return 2
    for ln in headline(res["receipt"]):
        print(ln)
    print(json.dumps(res["written"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
