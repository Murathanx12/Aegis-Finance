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
Admission: a corpus row naming the company that Aegis held (`first_seen_utc`)
before D's open, inside `AUTOPSY_KNOWABLE_LOOKBACK_DAYS`. Tier: by the item's
own `published_utc` when it carries a time, else by `first_seen_utc`:
* KNOWABLE_FRESH -- published after the previous session's close and before
  D's open: D is the first session that could price it.
* KNOWABLE_ALREADY_TRADED -- published before the previous close: at least
  one session had already priced it (an EX-99 out at 11:50Z and pulled at
  22:50Z is this, not an overnight precursor).
* NO_HEADLINE_IN_CORPUS -- the overnight window held enough corpus rows to be
  read, and none named the company. This is "our corpus held nothing", never
  "nothing was knowable".
* UNKNOWN -- the overnight window's corpus is empty or thin.
An 8-K's atom row and its EX-99 row are ONE item (same accession). Quote and
estimates pages the reader visited are attention, not precursors, and never
make a name KNOWABLE (`config.AUTOPSY_NOT_NEWS_TAGS`). A row with neither a
first-seen stamp nor a timed publication stamp is dropped and counted.

"MISSED BUT KNOWABLE" = not FORECAST, and KNOWABLE_FRESH. Not-forecast and
KNOWABLE_ALREADY_TRADED is counted beside it, never inside it, and never seeded.

SUSPECT_CORPORATE_ACTION -- a one-bar raw move beyond `AUTOPSY_SUSPECT_UP/DOWN`
on a name priced over the floor: listed and counted, never ranked, counted as
missed, or seeded (a split, spin-off or bad bar until shown otherwise).

FOLLOW-UP (2026-11-12, schema discovery-autopsy/2)
=================================================
* FORECAST movers are split by sign: every forecast made before the open is
  compared with the sign of D's residual (FORECAST_RIGHT_SIGN / _WRONG_SIGN /
  _MIXED / _NON_DIRECTIONAL in `ladder_outcome`; `ladder` keeps FORECAST), with
  each forecast's source and the AGE of its information (`inputs_used.claim_utc`,
  else the digest stamp; "not recorded" otherwise). One session, descriptive.
* Headlines are named through the issuer table (`news_entities.resolve` over
  `news_entities/issuers.csv`, the table CH-14a and the universe graph read),
  including headlines LISTED in reader page bodies (tier UNTIMED: no publication
  time) and the reader's article store `news_corpus/dowjones/<pub>/<day>/*.json`.
  Bare-word symbols (`AUTOPSY_BARE_WORD_TICKERS`) need `$TICK`, `NYSE: TICK`, a
  name, a CIK or a per-ticker feed.
* Analyst revisions (`analyst/target_revisions.parquet`) are knowable items, cut
  on the LATER of the event time and the first-seen stamp.
* `--daily` writes only `<data-root>/discovery_autopsy/`, idempotent on input hashes.

DESCRIPTIVE ONLY. Nothing here says a move was predictable: a headline that
preceded a move is the seed of a hypothesis (written to the research queue in
hyp_lab's field shape), and the matched non-mover is owed before it is one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import warnings
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from backend import config as C
from backend.services import forecast_ledger as FL

NY = ZoneInfo("America/New_York")
SCHEMA = "discovery-autopsy/2"
BENCH = "SPY"

NOT_IN_UNIVERSE = "NOT_IN_UNIVERSE"
IN_UNIVERSE_NOT_CANDIDATE = "IN_UNIVERSE_NOT_CANDIDATE"
CANDIDATE_NOT_FORECAST = "CANDIDATE_NOT_FORECAST"
FORECAST = "FORECAST"
LADDER = (NOT_IN_UNIVERSE, IN_UNIVERSE_NOT_CANDIDATE, CANDIDATE_NOT_FORECAST, FORECAST)

#: a FORECAST mover, split by the sign of every forecast made before the open
#: against the sign of D's residual move. DESCRIPTIVE, one day: each forecast
#: resolves on its own horizon, and a sign agreement on one session is no skill.
FORECAST_RIGHT_SIGN = "FORECAST_RIGHT_SIGN"
FORECAST_WRONG_SIGN = "FORECAST_WRONG_SIGN"
FORECAST_MIXED = "FORECAST_MIXED"
FORECAST_NON_DIRECTIONAL = "FORECAST_NON_DIRECTIONAL"
FORECAST_OUTCOMES = (FORECAST_RIGHT_SIGN, FORECAST_WRONG_SIGN, FORECAST_MIXED,
                     FORECAST_NON_DIRECTIONAL)
LADDER_OUTCOMES = (NOT_IN_UNIVERSE, IN_UNIVERSE_NOT_CANDIDATE, CANDIDATE_NOT_FORECAST,
                   *FORECAST_OUTCOMES)

SUSPECT_CORPORATE_ACTION = "SUSPECT_CORPORATE_ACTION"

#: knowable, tiered by when the item was PUBLISHED (when timed), else by when we first saw it:
#: FRESH = after the previous session's close and before D's open (D is its first session);
#: ALREADY_TRADED = before the previous close (at least one session already priced it);
#: UNTIMED = a headline LISTED on a reader page (a numbered list in its body): we held it
#: before the open, but the page does not say when the story ran, so it is neither.
KNOWABLE_FRESH = "KNOWABLE_FRESH"
KNOWABLE_ALREADY_TRADED = "KNOWABLE_ALREADY_TRADED"
KNOWABLE_UNTIMED = "KNOWABLE_UNTIMED"
NO_HEADLINE_IN_CORPUS = "NO_HEADLINE_IN_CORPUS"
UNKNOWN = "UNKNOWN"
KNOWABLE_STATES = (KNOWABLE_FRESH, KNOWABLE_ALREADY_TRADED, KNOWABLE_UNTIMED)
KNOWABLE_ALL = (*KNOWABLE_STATES, NO_HEADLINE_IN_CORPUS, UNKNOWN)

#: the reader's article store: news_corpus/<DJ_STORE>/<publisher>/<YYYY-MM-DD>/<sha>.json
DJ_STORE = "dowjones"
REVISIONS_SOURCE = "analyst/target_revisions"
EVIDENCE_KINDS = ("FILING", "NEWS", "LISTED_HEADLINE", "ANALYST_REVISION")

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
SESSION_NOT_CLOSED = "SESSION_NOT_CLOSED"
STALE_INPUT = "STALE_INPUT"
ISSUER_MAP_MISSING = "ISSUER_MAP_MISSING"
REVISIONS_MISSING = "REVISIONS_MISSING"
DAILY_WRITE_OUTSIDE = "DAILY_WRITE_OUTSIDE"
BAD_ARGS = "BAD_ARGS"


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


def _drop_keys(d: dict, *keys: str) -> dict:
    return {k: v for k, v in d.items() if k not in keys}


def _file_sha(p: Path) -> Optional[str]:
    if not Path(p).is_file():
        return None
    h = hashlib.sha256()
    with Path(p).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
    RDV = int(C.AUTOPSY_RANKER_DV_SESSIONS)
    need = max(W, RDV, int(C.AUTOPSY_DOLLAR_VOL_SESSIONS)) + 1
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
        dv63 = dv.loc[cal[max(lo, i - RDV):i], syms]
        med_dv63 = np.where(dv63.notna().sum(axis=0).to_numpy() >= int(C.AUTOPSY_RANKER_DV_MIN_OBS),
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
        suspect = (priced & not_proxy & (np.nan_to_num(close_prev) >= float(C.AUTOPSY_MIN_PRICE))
                   & ((rd > float(C.AUTOPSY_SUSPECT_UP)) | (rd < float(C.AUTOPSY_SUSPECT_DOWN))))
        base = priced & has_sigma & not_proxy & tradable & ~suspect
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
    suspects = [{**_row(j, "UP" if rd[j] > 0 else "DOWN"), "ladder": SUSPECT_CORPORATE_ACTION,
                 "why": (f"one-bar raw move {rd[j]:+.1%} outside [{C.AUTOPSY_SUSPECT_DOWN:+.0%}, "
                         f"{C.AUTOPSY_SUSPECT_UP:+.0%}]: split, spin-off or bad bar until shown otherwise")}
                for j in np.where(suspect)[0]]
    if not movers:
        raise AutopsyRefused(NO_MOVERS, f"no name on {day} cleared |z| >= {C.AUTOPSY_MIN_ABS_Z} "
                                        f"and |resid| >= {C.AUTOPSY_MIN_ABS_RESID} among "
                                        f"{int(base.sum())} screened: across a whole market "
                                        f"that is a broken input, not a quiet day")
    return {
        "movers": movers, "suspects": suspects,
        "screen": {
            "n_suspect_corporate_action": len(suspects),
            "suspect_bounds": [float(C.AUTOPSY_SUSPECT_DOWN), float(C.AUTOPSY_SUSPECT_UP)],
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
                                   f"same price / {RDV}-session median dollar volume / history floors"),
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
    if not FL.exists(p):
        raise AutopsyRefused(LEDGER_MISSING, f"no forecast ledger at {p}: the FORECAST rung "
                                             f"cannot be told from CANDIDATE_NOT_FORECAST")
    lb = timedelta(days=int(C.AUTOPSY_FORECAST_LOOKBACK_DAYS if lookback_days is None
                            else lookback_days))
    want = {norm_ticker(t) for t in tickers}
    by_day: dict[str, dict[str, list]] = {k: {} for k in windows}
    newest_before: dict[str, Optional[datetime]] = {k: None for k in windows}
    n = bad = no_stamp = 0
    newest: Optional[datetime] = None
    size = p.stat().st_size if p.is_file() else None
    # Through the ledger layer: after the monthly split a direct read sees a frozen file.
    for line in FL.logical_lines(p):
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
        for k, (op, _d) in windows.items():
            if made < op and (newest_before[k] is None or made > newest_before[k]):
                newest_before[k] = made
        t = norm_ticker(row.get("ticker"))
        if t not in want:
            continue
        ra = str(row.get("resolves_after") or "")[:10] or None
        for k, (op, d) in windows.items():
            if not (op - lb <= made < op):
                continue
            if ra is not None and ra < d.isoformat():
                continue
            src, info, basis = forecast_info(row)
            by_day[k].setdefault(t, []).append({
                "prediction_id": row.get("prediction_id"), "made_at": _iso(made),
                "specialist": row.get("specialist"), "source": src,
                "observable": row.get("observable"),
                "horizon_days": row.get("horizon_days"), "probability": row.get("probability"),
                "benchmark": row.get("benchmark"), "resolves_after": ra,
                "info_utc": _iso(info), "info_basis": basis,
                "info_age_days_at_made": _r((made - info).total_seconds() / 86400, 2)
                if info is not None else None})
    return {"by_day": by_day,
            "stats": {"path": str(p), "bytes": size, "lines": n, "unparseable": bad,
                      "no_made_at": no_stamp, "newest_made_at": _iso(newest),
                      "newest_made_before_open": {k: _iso(v) for k, v in newest_before.items()},
                      "lookback_days": lb.days, "read": "forecast_ledger.logical_lines, streamed, read-only"}}


def forecast_direction(row: dict) -> str:
    obs = str(row.get("observable") or "")
    try:
        p = float(row.get("probability"))
    except (TypeError, ValueError):
        return "UNSTATED"
    if obs not in DIRECTIONAL_OBSERVABLES:
        return "NON_DIRECTIONAL"
    return "UP" if p > 0.5 else ("DOWN" if p < 0.5 else "FLAT")


def forecast_info(row: dict) -> tuple[Optional[str], Optional[datetime], str]:
    """(source, when the information behind the forecast was first held, basis).

    `source:*` rows carry the claim's own first-seen stamp (`inputs_used.claim_utc`);
    `news_digest:*` rows the digest's UTC stamp (`inputs_used.digest_id`). Other
    specialists record no information time, and the receipt says so rather than
    using `made_at` (a forecast made today from a month-old article is the case).
    """
    iu = row.get("inputs_used") if isinstance(row.get("inputs_used"), dict) else {}
    src = iu.get("source_id") or iu.get("source")
    src = str(src) if src else None
    t = _utc(iu.get("claim_utc"))
    if t is not None:
        return src, t, "inputs_used.claim_utc"
    did = str(iu.get("digest_id") or "")
    try:
        return (src, datetime.strptime(did, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc),
                "inputs_used.digest_id")
    except ValueError:
        return src, None, "not recorded on the ledger row"


def forecast_quality(fc: list[dict], side: str, open_d: datetime) -> dict:
    """Every forecast made before the open, its sign against D's residual sign, the
    age of its information at the open, and the mover's FORECAST_* outcome."""
    stale_days = float(C.AUTOPSY_FORECAST_STALE_INFO_DAYS)
    rows = []
    for r in sorted(fc, key=lambda r: (r["made_at"], str(r.get("prediction_id")))):
        made = _utc(r.get("made_at"))
        if made is None or made >= open_d:          # index_forecasts cut already; re-checked
            continue
        d = forecast_direction(r)
        info = _utc(r.get("info_utc"))
        age = None if info is None else (open_d - info).total_seconds() / 86400
        rows.append({**r, "direction": d, "realised_resid_sign": side,
                     "agrees": (d == side) if d in ("UP", "DOWN") else None,
                     "info_age_days_at_open": _r(age, 2),
                     "stale_source": None if age is None else bool(age > stale_days)})
    right = sum(1 for x in rows if x["agrees"] is True)
    wrong = sum(1 for x in rows if x["agrees"] is False)
    if right and wrong:
        outcome = FORECAST_MIXED
    elif right:
        outcome = FORECAST_RIGHT_SIGN
    elif wrong:
        outcome = FORECAST_WRONG_SIGN
    else:
        outcome = FORECAST_NON_DIRECTIONAL
    known_age = [x for x in rows if x["stale_source"] is not None]
    return {"outcome": outcome if rows else None, "rows": rows, "n": len(rows),
            "n_right_sign": right, "n_wrong_sign": wrong,
            "n_non_directional": len(rows) - right - wrong,
            "n_stale_source": sum(1 for x in known_age if x["stale_source"]),
            "n_info_age_unknown": len(rows) - len(known_age),
            "n_directional_stale_source": sum(1 for x in rows if x["stale_source"]
                                              and x["agrees"] is not None),
            "n_wrong_sign_stale_source": sum(1 for x in rows if x["stale_source"]
                                             and x["agrees"] is False),
            "n_right_sign_stale_source": sum(1 for x in rows if x["stale_source"]
                                             and x["agrees"] is True),
            "stale_after_days": stale_days}


# ─────────────────────────────────────────────────── 3. the corpus (knowable)

class Corpus:
    """Dated rows of `news_corpus/<source>/<YYYY-MM-DD>.jsonl`, read lazily and cached.

    TWO clocks per row, used for different questions:
    * `known_at` = `first_seen_utc`, when Aegis held the row. This is the
      conservative "we could have known" stamp the look-ahead cut uses.
    * `published_at` = `published_utc` when it carries a real time (a date-only
      or exact-midnight stamp is not a time). This decides FRESH vs
      ALREADY_TRADED: an EX-99 published at 11:50Z and pulled at 22:50Z was
      priced by that day's session, whatever our pull time says.
    A row with no first-seen stamp keeps its timed `published_utc` as its clock;
    with neither it is DROPPED and counted -- a date-only stamp would otherwise
    read as "before the open" on the day it happened.

    Many SEC 8-K rows carry `tickers: []` and only a `cik:<10 digits>` entity
    tag (newer rows are also name-resolved by the collector); without `cik_map`
    (int CIK -> ticker, `official/company_tickers.json`) those filings name no
    company and their moves read as NO_HEADLINE_IN_CORPUS. On 2026-11-11 the
    map added a ticker to 1,097 corpus rows in the windows read.
    """

    def __init__(self, root: Path, cik_map: Optional[dict[int, str]] = None,
                 entities: Any = None) -> None:
        self.root = Path(root)
        self.cik_map = dict(cik_map or {})
        #: `news_entities._Tables` over `news_entities/issuers.csv` -- the issuer
        #: table CH-14a and the universe graph read. None = titles are not resolved.
        self.entities = entities
        self.n_cik_resolved = 0
        self.n_dropped_undated = 0
        self.n_first_seen_missing_timed_pub = 0
        self.n_title_resolved_rows = 0
        self.n_listed_headline_rows = 0
        self.n_store_rows = 0
        self.n_bare_word_refused = 0
        self.bare_word_refused: dict[str, int] = {}
        self.sources = (sorted(p.name for p in self.root.iterdir()
                               if p.is_dir() and not p.name.startswith("_"))
                        if self.root.is_dir() else [])
        self._cache: dict[tuple[str, str], list[dict]] = {}

    # -- issuer resolution (no bare words) ---------------------------------

    def _refuse_bare(self, sym: str) -> None:
        self.n_bare_word_refused += 1
        self.bare_word_refused[sym] = self.bare_word_refused.get(sym, 0) + 1

    def resolve_text(self, text: str) -> dict[str, str]:
        """symbol -> rule, through `news_entities.resolve` on the issuer table.

        A bare-word symbol (`config.AUTOPSY_BARE_WORD_TICKERS`: AI, IT, ON, ALL,
        NOW, A, GOLD, ...) is kept only from `$TICK`, `NYSE: TICK` or an issuer
        NAME (names are >= 5 characters); "artificial intelligence (AI)" is not C3.ai.
        """
        if self.entities is None or not text:
            return {}
        from backend.services import news_entities as NE
        bare = set(C.AUTOPSY_BARE_WORD_TICKERS)
        out: dict[str, str] = {}
        for s, rule in NE.resolve(text, tbl=self.entities, limit=8).how.items():
            s = norm_ticker(s)
            if s in bare and rule not in ("cashtag", "venue_ticker", "name"):
                self._refuse_bare(s)
                continue
            out[s] = rule
        return out

    def _names(self, src: str, collector: Iterable[Any], tags: list[str],
               text: str) -> set[str]:
        """Collector tags (bare words re-verified), CIK-mapped filings, issuer names."""
        bare = set(C.AUTOPSY_BARE_WORD_TICKERS)
        queried = src in set(C.AUTOPSY_TICKER_QUERIED_SOURCES)
        by_text = self.resolve_text(text)
        tickers: set[str] = set()
        for t in collector:
            t = norm_ticker(t)
            if not t:
                continue
            if t in bare and not queried and t not in by_text:
                self._refuse_bare(t)
                continue
            tickers.add(t)
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
        new = {s: r for s, r in by_text.items() if s not in tickers}
        if new:
            self.n_title_resolved_rows += 1
            for s, r in sorted(new.items()):
                tags.append(f"resolved:issuer_{r}:{s}")
            tickers |= set(new)
        return tickers

    def _listed(self, src: str, body: str, page: dict) -> list[dict]:
        """A numbered list in a page body is a list of headlines; one row per headline
        that names an issuer, timed only by the PAGE's first-seen stamp."""
        out = []
        n = 0
        found = list(_LISTED_LINE.finditer(body or ""))
        if len(found) < 3:                 # a list page, not an article with one numbered line
            return out
        for m in found:
            n += 1
            if n > int(C.AUTOPSY_LISTED_HEADLINES_MAX):
                break
            line = " ".join(m.group(1).split())[:240]
            names = self.resolve_text(line)
            if not names:
                continue
            self.n_listed_headline_rows += 1
            out.append({**page, "source": f"{src}#listed", "title": line, "published_at": None,
                        "published_utc_raw": None, "listed": True,
                        "tickers": sorted(names),
                        "tags": [*page["tags"], "listed_headline",
                                 *(f"resolved:issuer_{r}:{s}" for s, r in sorted(names.items()))],
                        "item_key": "hl:" + _sha(line.lower())})
        return out

    def _row(self, src: str, o: dict) -> Optional[dict]:
        fs_raw, pub_raw = o.get("first_seen_utc"), o.get("published_utc")
        fs = _utc(fs_raw)
        pub = timed_utc(pub_raw)
        if fs is None and pub is None:
            self.n_dropped_undated += 1
            return None
        if fs is None:
            self.n_first_seen_missing_timed_pub += 1
        tags = [str(t) for t in _as_list(o.get("entity_tags"))]
        title = str(o.get("title") or "")
        tickers = self._names(src, _as_list(o.get("tickers")), tags, title)
        url = str(o.get("url") or "")[:200]
        return {"source": src, "title": title[:240],
                "known_at": fs or pub, "published_at": pub,
                "clock": "first_seen_utc" if fs else "published_utc",
                "first_seen_utc_raw": fs_raw if isinstance(fs_raw, str) else None,
                "published_utc_raw": pub_raw if isinstance(pub_raw, str) else None,
                "tickers": sorted(t for t in tickers if t),
                "tags": tags, "url": url, "listed": False,
                "item_key": item_key(src, tags, url, o.get("raw_id"), o.get("title"))}

    def _day(self, src: str, day: str) -> list[dict]:
        key = (src, day)
        if key in self._cache:
            return self._cache[key]
        rows: list[dict] = []
        objs: list[tuple[str, dict]] = []
        f = self.root / src / f"{day}.jsonl"
        if f.is_file():
            with f.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(o, dict):
                        objs.append((src, o))
        if src == DJ_STORE:
            # the reader's article store: <publisher>/<day>/<sha>.json, one article per file
            for d in sorted(self.root.glob(f"{DJ_STORE}/*/{day}")):
                for jf in sorted(d.glob("*.json")):
                    try:
                        o = json.loads(jf.read_text(encoding="utf-8", errors="replace"))
                    except (OSError, ValueError):
                        continue
                    if not isinstance(o, dict):
                        continue
                    self.n_store_rows += 1
                    col = o.get("column")
                    o = {**o, "entity_tags": [f"column:{col}"] if col else [],
                         "raw_id": o.get("sha"), "body": o.get("text")}
                    objs.append((f"{DJ_STORE}/{d.parent.name}", o))
        for s, o in objs:
            r = self._row(s, o)
            if r is None:
                continue
            rows.append(r)
            rows.extend(self._listed(s, str(o.get("body") or ""), r))
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
                if s == DJ_STORE:
                    files_present += sum(1 for _ in self.root.glob(f"{DJ_STORE}/*/{dd}"))
                for r in self._day(s, dd):
                    if lo <= r["known_at"] < hi:
                        rows.append(r)
                        per_src[r["source"]] = per_src.get(r["source"], 0) + 1
        by: dict[str, list[dict]] = {}
        for r in rows:
            for t in set(r["tickers"]):
                by.setdefault(t, []).append(r)
        return {"lo": _iso(lo), "hi": _iso(hi), "n_rows": len(rows),
                "n_ticker_tagged": sum(1 for r in rows if r["tickers"]),
                "per_source": dict(sorted(per_src.items())), "files_present": files_present,
                "by_ticker": by}


def timed_utc(ts: Any) -> Optional[datetime]:
    """A stamp that carries a TIME: zoned ISO with a clock part that is not an
    exact midnight (a date-only stamp rendered as T00:00:00 is not a time)."""
    if not isinstance(ts, str) or len(ts) <= 10:
        return None
    d = _utc(ts)
    if d is None:
        return None
    if (d.hour, d.minute, d.second, d.microsecond) == (0, 0, 0, 0):
        return None
    return d


_ACCESSION_URL = re.compile(r"/edgar/data/\d+/(\d{18})")
_LISTED_LINE = re.compile(r"^\s*\d{1,2}\.\s+(\S.{6,238}?)\s*$", re.MULTILINE)


# ─────────────────────────────────────────── 3b. analyst revisions (knowable)

def _naive_event_utc(raw: Any) -> Optional[datetime]:
    """`event_date` is NAIVE ("2026-11-10 16:21:00"). Read conservatively, so the
    knowable cut can only come out LATER than the truth: a naive time is New York
    time (later than reading it as UTC), and an exact midnight or a date alone is
    the END of that New York day."""
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is not None:
        return d.astimezone(timezone.utc)
    if (d.hour, d.minute, d.second) == (0, 0, 0) and len(s) <= 19:
        d = d.replace(hour=23, minute=59, second=59)
    return d.replace(tzinfo=NY).astimezone(timezone.utc)


def load_revisions(path: Path, tickers: Iterable[str], lo: datetime, hi: datetime) -> dict:
    """Analyst rating/target revisions knowable in [lo, hi) for `tickers`.

    Knowable at the LATER of the event time and the time Aegis first held the row
    (`first_seen_utc`, else `pulled_at`): a revision dated the previous evening
    but first pulled after the open was not knowable before it. The event must
    itself fall inside the window (a backfill pull of a 2022 revision is not news).
    """
    p = Path(path)
    if not p.is_file():
        raise AutopsyRefused(REVISIONS_MISSING, f"no analyst revisions table at {p}")
    want = sorted({norm_ticker(t) for t in tickers})
    cols = ["ticker", "event_date", "first_seen_utc", "pulled_at", "firm", "action",
            "from_grade", "to_grade", "target_action", "prior_target", "current_target"]
    lo_s = (lo - timedelta(days=1)).astimezone(NY).date().isoformat()
    raw_want = sorted(set(want) | {t.replace(".", "-") for t in want})
    try:
        df = pd.read_parquet(p, columns=cols, filters=[("event_date", ">=", lo_s),
                                                       ("ticker", "in", raw_want)])
    except (OSError, ValueError) as e:
        raise AutopsyRefused(REVISIONS_MISSING, f"unreadable revisions table {p}: {e}") from e
    by: dict[str, list[dict]] = {}
    st = {"path": str(p), "n_rows_read": int(len(df)), "n_admitted": 0,
          "n_event_outside_window": 0, "n_seen_at_or_after_open": 0, "n_undated": 0,
          "lo": _iso(lo), "hi": _iso(hi),
          "event_date_read_as": "naive -> America/New_York; midnight/date-only -> 23:59:59 NY",
          "knowable_at": "later of event_date and first_seen_utc (else pulled_at)"}
    for rec in df.to_dict("records"):
        ev = _naive_event_utc(rec.get("event_date"))
        seen = _utc(rec.get("first_seen_utc")) or _utc(rec.get("pulled_at"))
        if ev is None or seen is None:
            st["n_undated"] += 1
            continue
        if not (lo <= ev < hi):
            st["n_event_outside_window"] += 1
            continue
        known = max(ev, seen)
        if known >= hi:
            st["n_seen_at_or_after_open"] += 1
            continue
        st["n_admitted"] += 1
        t = norm_ticker(rec.get("ticker"))
        firm = str(rec.get("firm") or "")
        title = (f"{firm}: {rec.get('action') or ''} {rec.get('from_grade') or ''}->"
                 f"{rec.get('to_grade') or ''}; target {rec.get('target_action') or ''} "
                 f"{_r(rec.get('prior_target'), 2)}->{_r(rec.get('current_target'), 2)}")
        by.setdefault(t, []).append({
            "source": REVISIONS_SOURCE, "title": " ".join(title.split())[:240],
            "known_at": known, "published_at": ev, "clock": "later of event_date and first_seen_utc",
            "first_seen_utc_raw": _iso(known), "published_utc_raw": _iso(ev),
            "event_date_raw": str(rec.get("event_date")),
            "tickers": [t], "tags": ["analyst_revision", f"firm:{firm}"], "url": "",
            "listed": False, "item_key": "rev:" + _sha(t, firm, str(rec.get("event_date")),
                                                       rec.get("to_grade"),
                                                       rec.get("current_target"))})
    return {"by_ticker": by, "stats": st}


def item_key(src: str, tags: list[str], url: str, raw_id: Any, title: Any) -> str:
    """One key per real-world item: an 8-K's atom row and its EX-99 body share
    the accession number and count once."""
    for t in tags:
        if t.startswith("accession:"):
            return "acc:" + t.split(":", 1)[1].replace("-", "")
    m = _ACCESSION_URL.search(url or "")
    if m:
        return "acc:" + m.group(1)
    rid = str(raw_id or "")
    head = rid.split(":", 1)[0].replace("-", "")
    if src.startswith("sec_") and len(head) == 18 and head.isdigit():
        return "acc:" + head
    return "url:" + url if url else f"title:{src}:{str(title or '')[:120]}"


def freshness(r: dict, prev_close: datetime, open_d: datetime) -> tuple[str, str]:
    """(tier, basis) for a row already known before the open."""
    if r["published_at"] is not None:
        t, basis = r["published_at"], ("event_date" if r["source"] == REVISIONS_SOURCE
                                       else "published_utc")
    elif r.get("listed"):
        return UNTIMED, "listed on a reader page first seen before the open; no publication time"
    else:
        t, basis = r["known_at"], "first_seen_utc (no timed published_utc)"
    if t < prev_close:
        return ALREADY_TRADED, basis
    if t < open_d:
        return FRESH, basis
    return PUBLISHED_AFTER_OPEN, basis


FRESH = "FRESH"
ALREADY_TRADED = "ALREADY_TRADED"
UNTIMED = "UNTIMED"
PUBLISHED_AFTER_OPEN = "PUBLISHED_AFTER_OPEN"
_TIER_ORDER = {ALREADY_TRADED: 0, FRESH: 1, UNTIMED: 2, PUBLISHED_AFTER_OPEN: 3}


def evidence_kind(r: dict) -> str:
    if r["source"] == REVISIONS_SOURCE:
        return "ANALYST_REVISION"
    if r.get("listed"):
        return "LISTED_HEADLINE"
    return "FILING" if r["source"].startswith("sec_") else "NEWS"


def _evidence(r: dict, tier: str, basis: str) -> dict:
    kind = evidence_kind(r)
    items = sorted({t.split(":", 1)[1] for t in r["tags"] if t.startswith("8-K:")})
    ebasis = [t for t in r["tags"] if t.startswith("resolved:") or t.startswith("cik:")][:3]
    return {"source": r["source"], "kind": kind, "title": r["title"],
            "known_at": _iso(r["known_at"]), "clock": r["clock"],
            "first_seen_utc": r["first_seen_utc_raw"], "published_utc": r["published_utc_raw"],
            "tier": tier, "tier_basis": basis, "item_key": r["item_key"],
            "items_8k": items, "entity_basis": ebasis, "url": r["url"]}


def knowable(ticker: str, overnight: dict, earlier: dict, *,
             prev_close: datetime, open_d: datetime,
             revisions: Optional[dict] = None) -> dict:
    """KNOWABLE_FRESH / KNOWABLE_ALREADY_TRADED / KNOWABLE_UNTIMED /
    NO_HEADLINE_IN_CORPUS / UNKNOWN.

    Rows are admitted by `known_at` < open (both windows end at the open) and
    tiered by publication time. Items are counted once per `item_key`. Analyst
    revisions (`load_revisions`) are items like any other, admitted on the later
    of their event and first-seen stamps.
    """
    not_news = set(C.AUTOPSY_NOT_NEWS_TAGS)
    rows = overnight["by_ticker"].get(ticker, []) + earlier["by_ticker"].get(ticker, [])
    revs = [r for r in ((revisions or {}).get("by_ticker", {}).get(ticker) or [])
            if r["known_at"] < open_d]
    news = [r for r in rows if not (set(r["tags"]) & not_news)] + revs
    pages = len(rows) + len(revs) - len(news)
    items: dict[str, dict] = {}
    for r in sorted(news, key=lambda r: r["known_at"]):
        tier, basis = freshness(r, prev_close, open_d)
        ev = _evidence(r, tier, basis)
        k = r["item_key"]
        if k not in items:
            items[k] = {**ev, "n_rows": 1, "sources": [r["source"]]}
        else:
            items[k]["n_rows"] += 1
            items[k]["sources"].append(r["source"])
            # an item is as fresh as its EARLIEST publication among its rows
            if _TIER_ORDER[tier] < _TIER_ORDER[items[k]["tier"]]:
                items[k].update(tier=tier, tier_basis=basis, published_utc=ev["published_utc"])
    ev_all = sorted(items.values(), key=lambda e: e["known_at"])
    fresh = [e for e in ev_all if e["tier"] == FRESH]
    traded = [e for e in ev_all if e["tier"] == ALREADY_TRADED]
    untimed = [e for e in ev_all if e["tier"] == UNTIMED]
    covered = overnight["n_rows"] >= int(C.AUTOPSY_MIN_CORPUS_ROWS)
    if fresh:
        state = KNOWABLE_FRESH
    elif traded:
        state = KNOWABLE_ALREADY_TRADED
    elif untimed:
        state = KNOWABLE_UNTIMED
    elif covered:
        state = NO_HEADLINE_IN_CORPUS
    else:
        state = UNKNOWN
    kinds = {k: sum(1 for e in ev_all if e["kind"] == k
                    and e["tier"] in (FRESH, ALREADY_TRADED, UNTIMED)) for k in EVIDENCE_KINDS}
    return {"state": state, "n_items": len(ev_all), "n_fresh": len(fresh),
            "n_already_traded": len(traded), "n_untimed": len(untimed),
            "n_published_after_open": sum(1 for e in ev_all if e["tier"] == PUBLISHED_AFTER_OPEN),
            "n_by_kind": kinds,
            "n_rows": len(news),
            "earliest": ev_all[0] if ev_all else None,
            "latest_before_open": ev_all[-1] if ev_all else None,
            "latest_fresh": fresh[-1] if fresh else None,
            "evidence": ev_all[-6:],
            "reader_pages_before_open": pages,
            "overnight_corpus_rows": overnight["n_rows"], "corpus_covered": covered}


# ─────────────────────────────────────────────────────────── 4. classify

def classify(m: dict, *, funnel: dict, contracts: dict, digest: dict,
             forecasts: dict[str, list], know: dict,
             open_d: Optional[datetime] = None) -> dict:
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
    q = forecast_quality(fc, m["side"], open_d) if (fc and open_d is not None) else None
    return {**m, "ladder": rung,
            "ladder_outcome": (q["outcome"] if q and q["outcome"] else rung),
            "forecast_quality": q,
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
            "missed_but_knowable": rung != FORECAST and know["state"] == KNOWABLE_FRESH,
            "missed_already_traded": rung != FORECAST and know["state"] == KNOWABLE_ALREADY_TRADED}


def summarise(rows: list[dict], suspects: Optional[list[dict]] = None) -> dict:
    sus = suspects or []
    return {"n_movers": len(rows),
            "by_side": {s: sum(1 for r in rows if r["side"] == s) for s in ("UP", "DOWN")},
            "by_ladder": {k: sum(1 for r in rows if r["ladder"] == k) for k in LADDER},
            "by_knowable": {k: sum(1 for r in rows if r["knowable"]["state"] == k)
                            for k in KNOWABLE_ALL},
            "by_ladder_outcome": {k: sum(1 for r in rows if r.get("ladder_outcome") == k)
                                  for k in LADDER_OUTCOMES},
            "forecast_wrong_sign": [r["ticker"] for r in rows
                                    if r.get("ladder_outcome") == FORECAST_WRONG_SIGN],
            "forecast_mixed": [r["ticker"] for r in rows
                               if r.get("ladder_outcome") == FORECAST_MIXED],
            "forecast_right_sign": [r["ticker"] for r in rows
                                    if r.get("ladder_outcome") == FORECAST_RIGHT_SIGN],
            #: a mover with at least one DIRECTIONAL forecast whose information was
            #: older than AUTOPSY_FORECAST_STALE_INFO_DAYS at the open
            "forecast_from_stale_source": [
                r["ticker"] for r in rows if (r.get("forecast_quality") or {}).get(
                    "n_directional_stale_source")],
            #: ... and one of those stale forecasts pointed the WRONG way (a MIXED
            #: outcome can hide it: NVDA-shaped, p=0.60 up from 27-day-old articles)
            "forecast_wrong_sign_from_stale_source": [
                r["ticker"] for r in rows if (r.get("forecast_quality") or {}).get(
                    "n_wrong_sign_stale_source")],
            "n_forecast_rows": sum((r.get("forecast_quality") or {}).get("n", 0) for r in rows),
            "n_forecast_rows_right_sign": sum((r.get("forecast_quality") or {}).get(
                "n_right_sign", 0) for r in rows),
            "n_forecast_rows_wrong_sign": sum((r.get("forecast_quality") or {}).get(
                "n_wrong_sign", 0) for r in rows),
            "n_forecast_rows_stale_source": sum((r.get("forecast_quality") or {}).get(
                "n_stale_source", 0) for r in rows),
            "n_forecast_rows_info_age_unknown": sum((r.get("forecast_quality") or {}).get(
                "n_info_age_unknown", 0) for r in rows),
            "forecast_sign_note": ("one session, descriptive: the sign of each forecast made "
                                   "before the open against D's residual sign; every forecast "
                                   "resolves on its own horizon. Not a skill claim."),
            "by_knowable_kind": {k: sum(1 for r in rows if r["knowable"].get("n_by_kind", {})
                                        .get(k)) for k in EVIDENCE_KINDS},
            "n_in_universe": sum(1 for r in rows if r["ladder"] != NOT_IN_UNIVERSE),
            "n_candidate_or_forecast": sum(1 for r in rows if r["ladder"] in
                                           (CANDIDATE_NOT_FORECAST, FORECAST)),
            "n_forecast": sum(1 for r in rows if r["ladder"] == FORECAST),
            "n_missed_but_knowable": sum(1 for r in rows if r["missed_but_knowable"]),
            "missed_but_knowable": [r["ticker"] for r in rows if r["missed_but_knowable"]],
            "n_missed_already_traded": sum(1 for r in rows if r["missed_already_traded"]),
            "missed_already_traded": [r["ticker"] for r in rows if r["missed_already_traded"]],
            "n_unknown": sum(1 for r in rows if r["knowable"]["state"] == UNKNOWN),
            "n_suspect_corporate_action": len(sus),
            "suspect_corporate_action": [f"{s['ticker']} {s['ret_raw']:+.3f}" for s in sus]}


# ──────────────────────────────────────────────────────────── 5. one day

def assert_no_lookahead(rows: list[dict], open_d: datetime) -> None:
    """Every item a mover's row cites must be dated strictly before D's open.

    The windows already cut at the open on the derived `known_at`; this check
    re-reads the RAW stamps carried on each evidence item (`first_seen_utc`,
    else a timed `published_utc`) and parses them afresh, so a bug in the
    derivation cannot certify itself. An item whose own publication time is
    after the open is a look-ahead too, whatever our pull time says.
    """
    bad = []
    for r in rows:
        k = r["knowable"]
        for e in [k.get("earliest"), k.get("latest_before_open"), k.get("latest_fresh"),
                  *(k.get("evidence") or [])]:
            if not e:
                continue
            fs = _utc(e.get("first_seen_utc"))
            pub = timed_utc(e.get("published_utc"))
            clock = fs if fs is not None else pub
            if clock is None or clock >= open_d or (pub is not None and pub >= open_d):
                bad.append((r["ticker"], "corpus", e.get("first_seen_utc"), e.get("published_utc")))
        latest = r["forecasts"].get("latest")
        if latest and (_utc(latest.get("made_at")) or open_d) >= open_d:
            bad.append((r["ticker"], "forecast", latest.get("made_at")))
        for f in (r.get("forecast_quality") or {}).get("rows") or []:
            if (_utc(f.get("made_at")) or open_d) >= open_d:
                bad.append((r["ticker"], "forecast", f.get("made_at")))
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
    revs = (load_revisions(paths["revisions"], [m["ticker"] for m in scr["movers"]],
                           prev_close - lbk, open_d)
            if paths.get("revisions") is not None else {"by_ticker": {}, "stats": {"read": False}})
    rows = [classify(m, funnel=funnel, contracts=contracts, digest=digest,
                     forecasts=forecasts_by_ticker, open_d=open_d,
                     know=knowable(norm_ticker(m["ticker"]), overnight, earlier,
                                   prev_close=prev_close, open_d=open_d, revisions=revs))
            for m in scr["movers"]]
    assert_no_lookahead(rows, open_d)
    #: what this session's receipt was computed FROM, per component: a re-run
    #: with every hash equal is the same autopsy (daily mode writes nothing).
    #: Ages against `now` and the sizes of growing files are left out on purpose.
    input_hashes = {
        "schema": _sha(SCHEMA),
        "params": _sha({k: getattr(C, k) for k in sorted(dir(C)) if k.startswith("AUTOPSY_")}),
        "screen": _sha(scr),
        "funnel": _sha(_drop_keys(funnel, "staleness")),
        "contracts": _sha(contracts),
        "digest": _sha(digest),
        "forecasts": _sha(forecasts_by_ticker,
                          fc["stats"]["newest_made_before_open"].get(day.isoformat())),
        "corpus": _sha([(w["n_rows"], w["per_source"]) for w in (overnight, earlier)],
                       {norm_ticker(m["ticker"]): r["knowable"] for m, r in zip(scr["movers"], rows)}),
        "revisions": _sha(revs["stats"], revs["by_ticker"]),
        "issuers": _sha(getattr(corpus, "entities_fingerprint", None)),
    }

    def _drop(d: dict, *keys: str) -> dict:
        return {k: v for k, v in d.items() if k not in keys}

    extra = dict(inputs_extra or {})
    stale: list[str] = list(extra.pop("stale_inputs", []))
    warn: list[str] = []
    if funnel.get("state") != "PRESENT":
        stale.append("funnel: no snapshot dated before the open")
    elif funnel.get("staleness"):
        stale.append(f"funnel: {funnel['age_days_at_open']} days old at the open "
                     f"(limit {funnel['stale_after_days']})")
    nb = _utc(fc["stats"]["newest_made_before_open"].get(day.isoformat()))
    led_age = None if nb is None else (open_d - nb).total_seconds() / 86400
    fc["stats"]["newest_made_before_open_age_days"] = _r(led_age, 2)
    fc["stats"]["max_age_days"] = int(C.AUTOPSY_LEDGER_MAX_AGE_DAYS)
    if led_age is None or led_age > int(C.AUTOPSY_LEDGER_MAX_AGE_DAYS):
        stale.append(f"forecast ledger: newest row made before the open is "
                     f"{fc['stats']['newest_made_before_open'].get(day.isoformat())} "
                     f"(age {_r(led_age, 2)} d, limit {C.AUTOPSY_LEDGER_MAX_AGE_DAYS}) -- a "
                     f"frozen ledger turns every mover into 'missed'")
    if day.isoformat() in contracts["days_without_contract"]:
        warn.append(f"contracts: no day contract for {day} written before the open")
    for f in contracts["files_written_after_open"]:
        warn.append(f"contracts: {Path(f['path']).name} written {f['written_utc']}, after the "
                    f"open -- its names are not counted as generated before D")
    if not overnight["n_rows"] >= int(C.AUTOPSY_MIN_CORPUS_ROWS):
        warn.append(f"corpus: {overnight['n_rows']} rows overnight, under the "
                    f"{C.AUTOPSY_MIN_CORPUS_ROWS} floor -- 'no headline' reads as UNKNOWN")
    if not scr["screen"]["n_up_kept"] or not scr["screen"]["n_down_kept"]:
        warn.append("screen: one tail is empty -- the winner/loser comparison is one-sided")
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
    summary = summarise(rows, scr["suspects"])
    summary["stale_inputs"] = stale
    summary["warnings"] = warn
    rec = {
        "schema": SCHEMA, "chunk": "CH-13", "licence": "PRODUCT_EXPERIMENT",
        "session": day.isoformat(), "session_open_utc": _iso(open_d),
        "prev_session": prev.isoformat(), "prev_close_utc": _iso(prev_close),
        "written_utc": _iso(now),
        "descriptive_only": ("observations, not evidence of predictability: a headline that "
                             "preceded a move is a seed, and the matched non-mover is owed"),
        "forecast_sign_is": ("DESCRIPTIVE, one session: each forecast's sign against the sign "
                             "of D's residual move; never a skill claim"),
        "input_hashes": input_hashes, "input_hash": _sha(input_hashes),
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
            "corpus_rows_dropped_undated": corpus.n_dropped_undated,
            "corpus_rows_without_first_seen_kept_on_timed_published":
                corpus.n_first_seen_missing_timed_pub,
            "corpus_rows_named_by_issuer_table": corpus.n_title_resolved_rows,
            "corpus_listed_headline_rows": corpus.n_listed_headline_rows,
            "corpus_reader_store_rows": corpus.n_store_rows,
            "corpus_bare_word_matches_refused": corpus.n_bare_word_refused,
            "corpus_bare_word_refused_by_symbol": dict(sorted(corpus.bare_word_refused.items())),
            "issuer_table": getattr(corpus, "entities_fingerprint", None),
            "revisions": revs["stats"],
        },
        "summary": summary,
        "movers": rows,
        "suspects": scr["suspects"],
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
             f"**missed but knowable (fresh) {s['n_missed_but_knowable']}**; missed, already "
             f"traded {s['n_missed_already_traded']}; UNKNOWN {s['n_unknown']}.",
             f"- Suspect corporate action / bad bar (excluded): {s['n_suspect_corporate_action']} "
             f"{s['suspect_corporate_action'][:10]}.",
             f"- Forecast sign ({s.get('forecast_sign_note', '')}): "
             f"{ {k: v for k, v in s.get('by_ladder_outcome', {}).items() if k.startswith('FORECAST_')} }; "
             f"wrong sign {s.get('forecast_wrong_sign')}; mixed {s.get('forecast_mixed')}; "
             f"a directional forecast from a source older than "
             f"{C.AUTOPSY_FORECAST_STALE_INFO_DAYS:g} d at the open: {s.get('forecast_from_stale_source')}.",
             f"- Knowable by kind (movers with at least one item): {s.get('by_knowable_kind')}.",
             f"- Stale inputs: {s['stale_inputs'] or 'none'}"
             f"{' (ALLOWED by --allow-stale)' if rec.get('allow_stale') else ''}; "
             f"warnings: {s['warnings'] or 'none'}.", "",
             "| side | ticker | raw | resid | z | ladder | forecasts R/W/ND, stale src | knowable "
             "| earliest dated item before the open |",
             "|---|---|---:|---:|---:|---|---|---|---|"]
    for r in rec["movers"]:
        e = r["knowable"]["latest_fresh"] or r["knowable"]["earliest"]
        ev = (f"pub {e['published_utc']} seen {e['known_at']} [{e['tier']}] {e['source']}: "
              f"{e['title'][:80]}") if e else ""
        q = r.get("forecast_quality") or {}
        fq = (f"{q.get('n_right_sign', 0)}/{q.get('n_wrong_sign', 0)}/"
              f"{q.get('n_non_directional', 0)}, {q.get('n_stale_source', 0)}") if q else ""
        lines.append(f"| {r['side']} | {r['ticker']} | {r['ret_raw']:+.3f} | {r['resid']:+.3f} | "
                     f"{r['z']:+.1f} | {r.get('ladder_outcome', r['ladder'])} | {fq} | "
                     f"{r['knowable']['state']} | {ev.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def research_seed(r: dict, rec: dict, receipt_path: str) -> dict:
    """A missed-but-knowable mover as a row in hyp_lab's hypothesis field shape,
    status SEED_UNADMITTED: hyp_lab does not read this file yet."""
    e = r["knowable"]["latest_fresh"] or r["knowable"]["latest_before_open"] or {}
    seed = {
        "kind": "hypothesis_seed",
        "title": (f"{str(e.get('kind') or 'item').lower()} before the open -> residual move? "
                  f"({r['ticker']} {rec['session']} {r['side']})"),
        "mechanism": ("UNSTATED: the autopsy is descriptive. A seed names a precursor observed "
                      "before one large residual move; a mechanism is owed before admission."),
        "precursor": (f"{e.get('kind')} item naming {r['ticker']} published "
                      f"{e.get('published_utc')}, first seen {e.get('known_at')} "
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


class DailyFolder:
    """The ONLY place `--daily` writes: `<data-root>/<AUTOPSY_DAILY_DIRNAME>/`.

    Every write is checked to land directly in that folder (no subfolders, no
    `..`, no link pointing elsewhere), and is temp -> verify -> replace: the temp
    file is read back and compared byte for byte before it replaces the target.
    The append-only files are rewritten whole the same way (old bytes + new lines),
    so a reader never sees half a line.
    """

    def __init__(self, data_root: Path) -> None:
        self.data_root = Path(data_root).resolve()
        self.root = self.data_root / str(C.AUTOPSY_DAILY_DIRNAME)
        if self.root.exists() and (self.root.is_symlink() or not self.root.is_dir()):
            raise AutopsyRefused(DAILY_WRITE_OUTSIDE, f"{self.root} is not a plain folder")
        self.written: list[str] = []

    def _check(self, path: Path) -> Path:
        p = Path(path)
        if p.parent.resolve() != self.root.resolve() or p.name in ("", ".", ".."):
            raise AutopsyRefused(DAILY_WRITE_OUTSIDE, f"refusing to write {p}: daily mode writes "
                                                      f"only directly inside {self.root}")
        if p.exists() and p.is_symlink():
            raise AutopsyRefused(DAILY_WRITE_OUTSIDE, f"refusing to write through a link: {p}")
        return p

    def path(self, name: str) -> Path:
        return self._check(self.root / name)

    def write(self, path: Path, data: bytes) -> None:
        import os
        import time as _time
        p = self._check(path)
        self.root.mkdir(parents=False, exist_ok=True)
        tmp = self._check(p.with_name(f".{p.name}.tmp{os.getpid()}"))
        tmp.write_bytes(data)
        if tmp.read_bytes() != data:
            tmp.unlink()
            raise OSError(f"verify failed for {tmp}")
        for i in range(6):
            try:
                os.replace(tmp, p)
                break
            except PermissionError:           # a reader holding the file open on Windows
                if i == 5:
                    tmp.unlink()
                    raise
                _time.sleep(0.25 * (i + 1))
        self.written.append(p.name)

    def write_text(self, path: Path, text: str) -> None:
        self.write(path, text.encode("utf-8"))

    def append(self, path: Path, rows: list[dict]) -> None:
        if not rows:
            return
        p = self._check(path)
        old = p.read_bytes() if p.is_file() else b""
        if old and not old.endswith(b"\n"):
            old += b"\n"
        new = "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in rows)
        self.write(p, old + new.encode("utf-8"))


def write_daily(rec: dict, folder: DailyFolder, run_id: str) -> dict:
    """Daily-mode outputs, idempotent on the receipt's `input_hash`.

    * the newest index row for the session has the same `input_hash` -> nothing
      is written at all (not even the weekly file);
    * otherwise a new version: v1 is `autopsy_<D>.json`, later ones
      `autopsy_<D>_v<k>.json` (a quoted receipt is never overwritten), and the
      index row names the version it supersedes and which input components changed.
    """
    session = rec["session"]
    ip = folder.path("index.jsonl")
    prior = [r for r in _jsonl(ip) if r.get("session") == session]
    last = max(prior, key=lambda r: int(r.get("version") or 1)) if prior else None
    if last is not None and last.get("input_hash") == rec["input_hash"]:
        return {"unchanged": True, "session": session, "version": int(last.get("version") or 1),
                "receipt": last.get("receipt"), "folder": str(folder.root), "files_written": []}
    version = 1 if last is None else int(last.get("version") or 1) + 1
    if last is None:
        why = ["first autopsy of this session"]
    else:
        old = last.get("input_hashes") or {}
        why = [f"input changed: {k}" for k in sorted(rec["input_hashes"])
               if old.get(k) != rec["input_hashes"][k]] or ["input_hash changed"]
    stem = f"autopsy_{session}" + ("" if version == 1 else f"_v{version}")
    jp, mp = folder.path(f"{stem}.json"), folder.path(f"{stem}.md")
    if jp.exists():
        raise AutopsyRefused(DAILY_WRITE_OUTSIDE, f"{jp} exists but the index has no row for it: "
                                                  f"refusing to overwrite a receipt")
    rec = {**rec, "run_id": run_id, "version": version, "why": why}
    body = json.dumps(rec, indent=1, default=str)
    folder.write_text(jp, body)
    folder.write_text(mp, render_md(rec))
    folder.append(ip, [{"session": session, "version": version, "run_id": run_id,
                        "supersedes": None if last is None else last.get("receipt"),
                        "why": why, "receipt": jp.name, "receipt_sha256": rec["receipt_sha256"],
                        "input_hash": rec["input_hash"], "input_hashes": rec["input_hashes"],
                        "written_utc": rec["written_utc"], "summary": rec["summary"]}])
    qp = folder.path("research_queue.jsonl")
    have = {r.get("seed_key") for r in _jsonl(qp)}
    seeds = [research_seed(r, rec, jp.name) for r in rec["movers"] if r["missed_but_knowable"]]
    new = [s for s in seeds if s["seed_key"] not in have]
    folder.append(qp, new)
    wk = weekly_rollup(folder.root, date.fromisoformat(session), writer=folder.write_text)
    return {"unchanged": False, "session": session, "version": version, "why": why,
            "receipt": str(jp), "markdown": str(mp), "index": str(ip), "queue": str(qp),
            "queue_rows_added": len(new), "queue_rows_already_present": len(seeds) - len(new),
            "weekly": wk["path"], "folder": str(folder.root), "files_written": folder.written}


def weekly_rollup(out_dir: Path, day: date, writer: Any = None) -> dict:
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
            "n_missed_but_knowable", "n_missed_already_traded", "n_unknown",
            "n_suspect_corporate_action")
    days = [{"session": s, "receipt": latest[s]["receipt"],
             **{k: int(latest[s]["summary"].get(k, 0)) for k in keys}} for s in sorted(latest)]
    wk = {"schema": SCHEMA + "/weekly", "iso_week": f"{iy}-W{iw:02d}", "n_sessions": len(days),
          "totals": {k: sum(d[k] for d in days) for k in keys}, "days": days}
    path = Path(out_dir) / f"weekly_{iy}-W{iw:02d}.json"
    (writer or _atomic_write)(path, json.dumps(wk, indent=1))
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
            "revisions": dr / "analyst" / "target_revisions.parquet",
            "funnel": fr / "funnel_night10.json",
            "funnel_history": fr / "funnel_history",
            # the issuer table CH-14a (`funnel_news_source.load_issuers`) and the
            # universe graph read; the live one sits beside the funnel.
            "issuers": fr / "news_entities" / "issuers.csv",
            "adrs": fr / "news_entities" / "asia_adrs.csv"}


# ──────────────────────────────────────────────────── 7. the daily run + CLI

#: input -> refusal code. A missing input is a red exit with its name, never
#: an empty rung: a missing forecast ledger would make every mover "not forecast".
REQUIRED_INPUTS = (("bars", PANEL_MISSING, "file"), ("predictions", LEDGER_MISSING, "file"),
                   ("funnel", FUNNEL_MISSING, "file"), ("decisions", DECISIONS_MISSING, "dir"),
                   ("digest", DIGEST_MISSING, "dir"), ("corpus", CORPUS_MISSING, "dir"),
                   ("cik_map", CIK_MAP_MISSING, "file"),
                   ("issuers", ISSUER_MAP_MISSING, "file"),
                   ("revisions", REVISIONS_MISSING, "file"))


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


def _repo_data_dirs(*roots: Path) -> list[Path]:
    """Every `backend/data` folder at or above the given roots: the live data
    is the whole of the runtime's backend/data, not only `optimus/`."""
    out = []
    for r in roots:
        rr = Path(r).resolve()
        for p in (rr, *rr.parents):
            if p.name == "data" and p.parent.name == "backend":
                out.append(p)
        out.append(rr)
    return out


def run(data_root: Path, out_dir: Optional[Path], *, funnel_root: Optional[Path] = None,
        session: Optional[date] = None, now: Optional[datetime] = None,
        top_k: Optional[int] = None, run_id: Optional[str] = None,
        allow_stale: bool = False, daily: bool = False) -> dict:
    """Read-only over `data_root`; writes only under `out_dir`. Raises AutopsyRefused.

    `daily=True`: `out_dir` must be None, and the ONLY folder written is
    `<data_root>/<AUTOPSY_DAILY_DIRNAME>/` (`DailyFolder`), idempotent on the
    receipt's input hashes (`write_daily`). Without it, `out_dir` keeps the rule
    that it lies outside every `backend/data`.

    A stale input (bars panel, funnel, forecast ledger beyond its config limit)
    is a refusal unless `allow_stale`, and the permission travels onto the
    receipt. Nothing is written -- no receipt, no index row -- on a refusal.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    paths = default_paths(data_root, funnel_root)
    fr = Path(funnel_root) if funnel_root else Path(data_root).parent
    folder: Optional[DailyFolder] = None
    if daily:
        if out_dir is not None:
            raise AutopsyRefused(BAD_ARGS, "--daily writes only to <data-root>/"
                                           f"{C.AUTOPSY_DAILY_DIRNAME}/; --out is not taken with it")
        folder = DailyFolder(Path(data_root))
    else:
        if out_dir is None:
            raise AutopsyRefused(BAD_ARGS, "give --out <folder outside backend/data>, or --daily")
        for root in _repo_data_dirs(Path(data_root), fr):
            if _inside(out_dir, root):
                raise AutopsyRefused(OUT_INSIDE_DATA_ROOT, f"--out {out_dir} is inside {root}: the "
                                                           f"autopsy never writes into live data "
                                                           f"(use --daily for its own folder there)")
    sizes = check_inputs(paths)
    history = history_counts(paths["bars"])
    facts = panel_facts(history)
    if facts["last_date"] is None:
        raise AutopsyRefused(PANEL_STALE, f"the bars panel {paths['bars']} holds no rows")
    last = date.fromisoformat(facts["last_date"])
    day = session or last
    from backend.services import market_sessions as MS
    if not MS.is_session(day):
        raise AutopsyRefused(NOT_A_SESSION, f"{day} is not an XNYS session")
    if day > last:
        raise AutopsyRefused(PANEL_STALE, f"the bars panel ends {last}, before D={day}")
    latest_closed = latest_closed_session(now)
    if day > latest_closed:
        raise AutopsyRefused(SESSION_NOT_CLOSED, f"session {day} is later than the latest closed "
                                                 f"XNYS session at {_iso(now)} ({latest_closed}): "
                                                 f"a session still trading has no close to grade")
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
    from backend.services import news_entities as NE
    ents = NE.tables(issuers=paths["issuers"], adrs=paths["adrs"])
    if ents.n_issuer_rows == 0:
        raise AutopsyRefused(ISSUER_MAP_MISSING, f"issuer table {paths['issuers']} holds no rows")
    corpus = Corpus(paths["corpus"], cik_map=cik_map, entities=ents)
    corpus.entities_fingerprint = {"issuers": str(paths["issuers"]),
                                   "issuers_sha256": _file_sha(paths["issuers"]),
                                   "adrs_sha256": _file_sha(paths["adrs"]),
                                   "issuer_rows": ents.n_issuer_rows,
                                   "name_keys": len(ents.name_to_symbol),
                                   "bare_word_tickers": list(C.AUTOPSY_BARE_WORD_TICKERS)}
    extra = {"sizes": sizes, "bars_panel": {**facts, **panel_age,
                                            "survivorship": "panel built from a dated universe "
                                            "file; dead names are under-represented"},
             "cik_map_rows": len(cik_map), "stale_inputs": stale}
    rec = run_day(day, bars=bars, history=history, paths=paths, corpus=corpus, now=now,
                  inputs_extra=extra, top_k=top_k)
    rec["allow_stale"] = bool(allow_stale)
    if rec["summary"]["stale_inputs"] and not allow_stale:
        raise AutopsyRefused(STALE_INPUT, "; ".join(rec["summary"]["stale_inputs"])
                             + " (pass --allow-stale to write a receipt that says so)")
    # the input hash also covers the stale permission: a receipt written WITH
    # --allow-stale is not the same autopsy as one without a stale input.
    rec["input_hashes"]["stale"] = _sha(rec["summary"]["stale_inputs"], bool(allow_stale))
    rec["input_hash"] = _sha(rec["input_hashes"])
    rec["daily"] = bool(daily)
    rec["receipt_sha256"] = _sha({k: v for k, v in rec.items() if k != "receipt_sha256"}, n=64)
    rid = run_id or now.strftime("%Y%m%dT%H%M%SZ")
    if folder is not None:
        written = write_daily(rec, folder, rid)
    else:
        written = write_outputs(rec, out_dir, rid)
    return {"receipt": rec, "written": written}


def headline(rec: dict) -> list[str]:
    s, cs, bp = rec["summary"], rec["candidate_set"], rec["inputs"]["bars_panel"]
    fs = rec["inputs"]["forecasts"]
    return [
        f"session {rec['session']} | bars panel ends {bp['panel_last_date']}, age {bp['age_days']} d, "
        f"{bp['sessions_behind']} session(s) behind {bp['latest_closed_session']}"
        f"{' [STALE]' if bp['stale'] else ''}",
        f"candidate set: funnel {cs['n_funnel']} names generated {cs['funnel_generated_at']} "
        f"(age {cs['funnel_age_days_at_open']} d at the open, {cs['funnel_age_days_now']} d now); "
        f"contracts name {cs['n_contract_tickers']} tickers (newest {cs['newest_contract_written_utc']})",
        f"forecast ledger: newest row before the open {fs['newest_made_before_open'].get(rec['session'])} "
        f"(age {fs.get('newest_made_before_open_age_days')} d, limit {fs.get('max_age_days')})",
        f"movers {s['n_movers']} (UP {s['by_side']['UP']} / DOWN {s['by_side']['DOWN']}) | "
        f"ladder {s['by_ladder']} | knowable {s['by_knowable']}",
        f"MISSED BUT KNOWABLE (fresh) {s['n_missed_but_knowable']} {s['missed_but_knowable']} | "
        f"missed, already traded {s['n_missed_already_traded']} {s['missed_already_traded']} | "
        f"UNKNOWN {s['n_unknown']}",
        f"suspect corporate action / bad bar (excluded): {s['n_suspect_corporate_action']} "
        f"{s['suspect_corporate_action'][:10]}",
        f"ladder outcome {s.get('by_ladder_outcome')} | wrong sign {s.get('forecast_wrong_sign')} "
        f"| mixed {s.get('forecast_mixed')} | directional forecast from a stale source "
        f"{s.get('forecast_from_stale_source')} (wrong sign among them "
        f"{s.get('forecast_wrong_sign_from_stale_source')}; descriptive, one session; "
        f"not a skill claim)",
        f"knowable by kind {s.get('by_knowable_kind')} | bare-word matches refused "
        f"{rec['inputs'].get('corpus_bare_word_matches_refused')}",
        f"stale inputs: {s['stale_inputs'] or 'none'}"
        f"{' [ALLOWED by --allow-stale]' if rec.get('allow_stale') and s['stale_inputs'] else ''}",
        f"warnings: {s['warnings'] or 'none'}",
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
    ap.add_argument("--out", type=Path, default=None,
                    help="output folder, outside backend/data (not with --daily)")
    ap.add_argument("--daily", action="store_true",
                    help=f"write into <data-root>/{C.AUTOPSY_DAILY_DIRNAME}/ (only there), "
                         f"idempotent on the input hashes")
    ap.add_argument("--funnel-root", type=Path, default=None,
                    help="folder holding funnel_night10.json (default: data-root's parent)")
    ap.add_argument("--session", type=date.fromisoformat, default=None,
                    help="session date (default: the newest session in the bars panel)")
    ap.add_argument("--now", type=_parse_now, default=None,
                    help="ISO timestamp with zone to judge ages against (default: now)")
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--allow-stale", action="store_true",
                    help="write a receipt despite a stale input; the flag is recorded on it")
    a = ap.parse_args(argv)
    try:
        res = run(a.data_root, a.out, funnel_root=a.funnel_root, session=a.session,
                  now=a.now, top_k=a.top_k, allow_stale=a.allow_stale, daily=a.daily)
    except AutopsyRefused as e:
        print(f"REFUSED {e.code}: {e.detail}", file=sys.stderr)
        return 2
    for ln in headline(res["receipt"]):
        print(ln)
    w = res["written"]
    if a.daily:
        print(f"daily: {'UNCHANGED (identical input hashes; nothing written)' if w['unchanged'] else 'version ' + str(w['version']) + ' ' + str(w.get('why'))}"
              f" -> {w['folder']}")
    print(json.dumps(res["written"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
