"""ONE point-in-time, survivorship-aware training table.

Row = (date t, symbol). Features are known at the CLOSE of t. Labels are the
forward return from the OPEN of session t+1 to the OPEN of session t+1+h, for
h in (5, 21, 63), minus the cross-sectional MEDIAN of the same quantity over
the names eligible on t.

Every feature group carries its own availability stamp so it can be switched
off and so a PIT audit can prove nothing was used before it existed:

    group     availability rule                               stamp column
    -------   ---------------------------------------------   ------------------
    price     bars dated <= t                                 date itself
    fund      SEC filing FILED strictly before t (never the   fund_filed_max
              period end)
    analyst   revision event_date on a day strictly before t  analyst_last_day
    news      article published on a day strictly before t    news_last_day
    ledger    forecast made_at on a day strictly before t     ledger_last_day

`assert_pit` checks every stamp is < t (price: == t) and RAISES otherwise.

Survivorship: living names come from prices_deep (a universe selected ALIVE on
2026-09-01 with a $3M dollar-volume floor -- SELECTED), and dead names from
bars_delisted (1,784 inactive listed symbols; delistings before 2016 and OTC
names are absent). Eligibility is recomputed point-in-time on every date
(trailing 63-session median dollar volume >= $3M, >= 126 sessions of history; the
$3 price floor only where an UNADJUSTED close exists -- none does on disk, review F1). A delisted name's forward return exits at its LAST CLOSE; the
true delisting return (cash-out premium or wipe-out) is unknown and flagged.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from nn_lab import config as C

PRICE_FEATURES: tuple[str, ...] = (
    "ret_1", "mom_5", "mom_21", "mom_63", "mom_126", "mom_12_1",
    "vol_21", "vol_63", "vol_ratio", "idio_vol_63", "beta_63", "resid_mom_63",
    "dv_log", "dv_trend_5_63", "dv_trend_21_126", "trade_surge",
    "px_52w_high", "px_52w_low", "px_ma50", "px_ma200", "max_dd_63",
    "amihud_21", "up_days_21", "skew_63", "max_ret_21", "gap_share_21", "vwap_press_10",
)
FUND_FEATURES: tuple[str, ...] = (
    "f_log_mcap", "f_ey", "f_sy", "f_bm", "f_gross_margin", "f_op_margin",
    "f_rev_yoy", "f_ni_yoy", "f_debt_assets", "f_cash_assets", "f_rd_rev", "f_days_since_filing",
)
ANALYST_FEATURES: tuple[str, ...] = (
    "an_n_63", "an_up_63", "an_down_63", "an_net_63", "an_init_63", "an_net_21", "an_tgt_chg_63",
)
NEWS_FEATURES: tuple[str, ...] = ("news_n_5", "news_n_21")
LEDGER_FEATURES: tuple[str, ...] = ("ledger_prob_10", "ledger_n_10")

GROUPS: dict[str, tuple[str, ...]] = {
    "price": PRICE_FEATURES,
    "fund": FUND_FEATURES,
    "analyst": ANALYST_FEATURES,
    "news": NEWS_FEATURES,
    "ledger": LEDGER_FEATURES,
}
STAMPS = {"fund": "fund_filed_max", "analyst": "analyst_last_day",
          "news": "news_last_day", "ledger": "ledger_last_day"}
LABELS = tuple(f"y_{h}" for h in C.HORIZONS)
RAW_FWD = tuple(f"fwd_{h}" for h in C.HORIZONS)


class PITViolation(RuntimeError):
    """A feature was dated on or after the decision date it was attached to."""


# ─────────────────────────────── bars ────────────────────────────────────────

REUSED_TICKERS: list[str] = []   # filled by load_bars; printed on the table receipt
RENAMED_DEAD: list[str] = []     # dead companies kept as `SYM#d` (RENAME_REUSED_DEAD)


def load_bars(paths: Iterable[Path], start: str | None = None,
              symbols: Iterable[str] | None = None,
              extend_only: Iterable[Path] = ()) -> pd.DataFrame:
    """Concatenate bar files, typed small, WITHOUT splicing two companies.

    A symbol that an earlier file already carries is DROPPED from a later file
    (a delisted company whose ticker was reused by a later IPO is a different
    company: splicing them gave FLY/NIQ/VIA 1,500+ sessions of someone else's
    history on 2026-09-28). A file listed in `extend_only` is the same company's
    newer bars (the nightly refresh), and may only ADD dates after the earlier
    files' last date for that symbol."""
    cols = ["symbol", "date", "open", "high", "low", "close", "volume", "vwap", "trades"]
    frames = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            raise FileNotFoundError(f"bars file missing: {p}")
        filters = []
        if start is not None:
            filters.append(("date", ">=", pd.Timestamp(start)))
        if symbols is not None:
            filters.append(("symbol", "in", list(symbols)))
        df = pd.read_parquet(p, columns=cols, filters=filters or None)
        df["src"] = p.stem
        if frames:
            prev = pd.concat([f[["symbol", "date"]] for f in frames])
            last = prev.groupby("symbol")["date"].max()
            if p in {Path(x) for x in extend_only}:
                lim = df["symbol"].map(last)
                df = df[lim.isna() | (df["date"] > lim)]
            else:
                clash = df["symbol"].isin(last.index)
                if C.RENAME_REUSED_DEAD and clash.any():
                    # F3 (2026-09-30): a dead company whose ticker a later company reuses is its
                    # own dead name `SYM#d` when its bars END before the earlier file's FIRST bar
                    # for that ticker (no overlap = two companies); an overlap is still dropped.
                    first = prev.groupby("symbol")["date"].min()
                    dl = df.loc[clash].groupby("symbol")["date"].max()
                    ok = dl[dl < first.reindex(dl.index)].index
                    ren = clash & df["symbol"].isin(ok)
                    RENAMED_DEAD.extend(sorted(df.loc[ren, "symbol"].unique().tolist()))
                    df.loc[ren, "symbol"] = df.loc[ren, "symbol"] + "#d"
                    clash = clash & ~ren
                REUSED_TICKERS.extend(sorted(df.loc[clash, "symbol"].unique().tolist()))
                df = df[~clash]
        frames.append(df)
    b = pd.concat(frames, ignore_index=True)
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    b = b.drop_duplicates(["symbol", "date"], keep="first")
    for c in ("high", "low", "vwap", "volume", "trades"):
        b[c] = b[c].astype("float32")
    b = b.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)
    return split_reused_symbols(b)


#: A symbol whose bars stop for more than this many sessions and then resume is
#: treated as TWO companies (the bars vendor serves a reused ticker's histories
#: under one symbol: FLY = Fly Leasing to 2021 + Firefly from 2025).
MAX_GAP_SESSIONS = 20
SPLIT_SYMBOLS: dict[str, int] = {}   # symbol -> number of earlier segments renamed


def split_reused_symbols(b: pd.DataFrame) -> pd.DataFrame:
    """Rename every segment before the last one to `SYM#k` so it becomes its own
    (dead) name. The market proxy defines the session calendar."""
    m = b.loc[b["symbol"] == C.MARKET, "date"]
    cal = pd.DatetimeIndex(np.sort((m if len(m) else b["date"]).unique()))
    pos = np.searchsorted(cal.values, b["date"].values)
    same = b["symbol"].values[1:] == b["symbol"].values[:-1]
    jump = np.r_[False, same & (np.diff(pos) > MAX_GAP_SESSIONS)]
    if not jump.any():
        return b
    seg = pd.Series(jump.astype(int)).groupby(b["symbol"].values).cumsum().values
    nseg = pd.Series(seg).groupby(b["symbol"].values).transform("max").values
    early = seg < nseg
    sym = b["symbol"].astype(str).values.copy()
    sym[early] = [f"{s}#{k + 1}" for s, k in zip(sym[early], seg[early])]
    for s, n in pd.Series(nseg[jump], index=b["symbol"].values[jump]).groupby(level=0).max().items():
        SPLIT_SYMBOLS[str(s)] = int(n)
    b = b.copy()
    b["symbol"] = sym
    return b.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)


def session_calendar(bars: pd.DataFrame) -> pd.DatetimeIndex:
    """Trading sessions = the market proxy's dates (union of all dates if absent)."""
    m = bars.loc[bars["symbol"] == C.MARKET, "date"]
    d = m if len(m) else bars["date"]
    return pd.DatetimeIndex(np.sort(d.unique()))


GRID_ANCHOR = pd.Timestamp("2016-01-04")


def grid_mask(cal: pd.DatetimeIndex) -> np.ndarray:
    """Decision dates of the training table: every GRID_STEP-th session from a fixed anchor.

    The anchor is fixed so a nightly rebuild and the original build agree on
    which dates are on the grid."""
    pos = np.arange(len(cal)) - int(np.searchsorted(cal, GRID_ANCHOR))
    return (pos % C.GRID_STEP) == 0


# ─────────────────────────── price features ──────────────────────────────────

def _price_block(s: pd.DataFrame, mret: pd.Series, m63: pd.Series) -> pd.DataFrame:
    """All price/volume features for ONE symbol's bars (sorted by date). Trailing only."""
    c = s["close"].astype("float64")
    o = s["open"].astype("float64")
    v = s["volume"].astype("float64")
    r1 = c / c.shift(1) - 1.0
    dv = c * v
    out = {}
    out["ret_1"] = r1
    for k in (5, 21, 63, 126):
        out[f"mom_{k}"] = c / c.shift(k) - 1.0
    out["mom_12_1"] = c.shift(21) / c.shift(252) - 1.0
    vol21 = r1.rolling(21, min_periods=15).std() * math.sqrt(252)
    vol63 = r1.rolling(63, min_periods=40).std() * math.sqrt(252)
    out["vol_21"], out["vol_63"] = vol21, vol63
    out["vol_ratio"] = vol21 / vol63.replace(0, np.nan)
    mr = pd.Series(s["date"].map(mret).values, index=s.index, dtype="float64")
    cov = r1.rolling(63, min_periods=40).cov(mr)
    var = mr.rolling(63, min_periods=40).var()
    beta = cov / var.replace(0, np.nan)
    out["beta_63"] = beta
    ivar = (r1.rolling(63, min_periods=40).var() - beta ** 2 * var).clip(lower=0)
    out["idio_vol_63"] = np.sqrt(ivar) * math.sqrt(252)
    mk63 = pd.Series(s["date"].map(m63).values, index=s.index, dtype="float64")
    out["resid_mom_63"] = out["mom_63"] - beta * mk63
    med63 = dv.rolling(63, min_periods=40).median()
    out["med_dv"] = med63
    out["dv_log"] = np.log1p(med63)
    out["dv_trend_5_63"] = np.log((dv.rolling(5, min_periods=3).mean() + 1) / (med63 + 1))
    out["dv_trend_21_126"] = np.log((dv.rolling(21, min_periods=15).mean() + 1)
                                    / (dv.rolling(126, min_periods=80).mean() + 1))
    tr = s["trades"].astype("float64")
    out["trade_surge"] = np.log((tr.rolling(5, min_periods=3).mean() + 1)
                                / (tr.rolling(63, min_periods=40).median() + 1))
    hi = s["high"].astype("float64").rolling(252, min_periods=120).max()
    lo = s["low"].astype("float64").rolling(252, min_periods=120).min()
    out["px_52w_high"] = c / hi - 1.0
    out["px_52w_low"] = c / lo - 1.0
    out["px_ma50"] = c / c.rolling(50, min_periods=30).mean() - 1.0
    out["px_ma200"] = c / c.rolling(200, min_periods=120).mean() - 1.0
    out["max_dd_63"] = c / c.rolling(63, min_periods=40).max() - 1.0
    out["amihud_21"] = np.log1p((r1.abs() / dv.replace(0, np.nan)).rolling(21, min_periods=15).mean() * 1e9)
    out["up_days_21"] = (r1 > 0).astype("float64").where(r1.notna()).rolling(21, min_periods=15).mean()
    out["skew_63"] = r1.rolling(63, min_periods=40).skew()
    out["max_ret_21"] = r1.rolling(21, min_periods=15).max()
    gap = (o / c.shift(1) - 1.0).abs()
    intr = (c / o - 1.0).abs()
    out["gap_share_21"] = (gap / (gap + intr).replace(0, np.nan)).rolling(21, min_periods=10).mean()
    vw = s["vwap"].astype("float64").replace(0, np.nan)
    out["vwap_press_10"] = (c / vw - 1.0).rolling(10, min_periods=5).mean()
    f = pd.DataFrame(out, index=s.index)
    f = f.replace([np.inf, -np.inf], np.nan)
    return f


def _labels_block(s: pd.DataFrame, cal: pd.DatetimeIndex, dead: bool) -> pd.DataFrame:
    """Forward open(t+1) -> open(t+1+h) returns on the SESSION CALENDAR (not the bar list).

    A gap in a symbol's bars is not read as consecutive sessions: the exit is the
    first bar on/after calendar session t+1+h. A DEAD symbol whose series ends
    before the exit exits at its last close (flagged `delist_exit_h`)."""
    pos = np.searchsorted(cal, s["date"].values)
    n_cal = len(cal)
    first, last = pos[0], pos[-1]
    # open on each calendar session in [first, last], back-filled from the next bar
    op = pd.Series(np.nan, index=np.arange(first, last + 1))
    op.loc[pos] = s["open"].values.astype("float64")
    op_bf = op.bfill()
    last_close = float(s["close"].values[-1])
    out = {}
    entry_pos = pos + 1
    entry = op_bf.reindex(entry_pos).values
    for h in C.HORIZONS:
        exit_pos = pos + 1 + h
        ex = op_bf.reindex(exit_pos).values        # NaN beyond this symbol's last bar
        r = ex / entry - 1.0
        flag = np.zeros(len(pos), dtype=bool)
        if dead:
            beyond = (exit_pos > last) & (entry_pos <= last)
            r = np.where(beyond, last_close / entry - 1.0, r)
            flag = beyond
        # never label a window that runs past the calendar we know
        r = np.where(exit_pos >= n_cal, np.nan, r) if not dead else r
        out[f"fwd_{h}"] = r
        out[f"delist_exit_{h}"] = flag
    return pd.DataFrame(out, index=s.index)


def price_rows(bars: pd.DataFrame, cal: pd.DatetimeIndex, *, keep_dates: pd.DatetimeIndex | None,
               keep_last: bool = False, panel_end: pd.Timestamp | None = None,
               force_keys: pd.DataFrame | None = None) -> pd.DataFrame:
    """Price features + raw forward returns for eligible (symbol, date) rows.

    keep_dates: keep only these decision dates (the grid); keep_last also keeps
    every eligible row on the final calendar session (the 'live' rows).
    force_keys: (date, symbol) rows produced WHATEVER today's eligibility says -- the
    frozen membership of stored grid dates (nn_lab/membership.py, owner decision
    2026-10-06). When given, every row carries `_rebuild_eligible` so a stored member the
    re-adjusted bars would now refuse is a REVISION, not a lost row."""
    panel_end = panel_end or cal[-1]
    mkt = bars.loc[bars["symbol"] == C.MARKET].set_index("date")["close"].astype("float64")
    mret = mkt / mkt.shift(1) - 1.0
    m63 = mkt / mkt.shift(63) - 1.0
    keep = set(pd.DatetimeIndex(keep_dates)) if keep_dates is not None else None
    from nn_lab.universe_filter import excluded as _etf_excluded
    excluded = _etf_excluded()          # ETFs / ETNs / funds (EXCLUDE_ETFS); exact symbol only
    last_session = cal[-1]
    cal_pos_end = len(cal) - 1
    forced: dict = {}
    if force_keys is not None and len(force_keys):
        fk = force_keys[["date", "symbol"]].copy()
        fk["date"] = pd.to_datetime(fk["date"])
        forced = {s: set(g.values) for s, g in fk.groupby("symbol")["date"]}
    out = []
    for sym, s in bars.groupby("symbol", sort=False, observed=True):
        if sym in C.INDEX_PROXIES or sym in excluded or len(s) < C.MIN_HISTORY_SESSIONS:
            continue
        s = s.reset_index(drop=True)
        f = _price_block(s, mret, m63)
        f["sessions_seen"] = np.arange(1, len(s) + 1)
        f["close"] = s["close"].values
        f["date"] = s["date"].values
        # F1 (review 2026-09-29): the $3 floor needs an UNADJUSTED close. `close` is
        # adjusted for every later split, so a floor on it drops future splitters and
        # admits future reverse-splitters. Only the dollar-volume floor applies here
        # (adjusted close x adjusted volume = unadjusted dollar volume).
        elig = ((f["med_dv"] >= C.MIN_MEDIAN_DOLLAR_VOL)
                & (f["sessions_seen"] >= C.MIN_HISTORY_SESSIONS))
        if "close_raw" in s.columns:
            f["close_raw"] = s["close_raw"].values
            elig &= ~(f["close_raw"] < C.MIN_PRICE)
        sel = elig.values.copy()
        if keep is not None:
            on = f["date"].isin(keep).values
            if keep_last:
                on |= (f["date"] == last_session).values
            sel &= on
        if force_keys is not None:
            f["_rebuild_eligible"] = elig.values
            fd = forced.get(sym)
            if fd:
                sel |= f["date"].isin(fd).values
        if not sel.any():
            continue
        last_pos = int(np.searchsorted(cal, s["date"].values[-1]))
        dead = (cal_pos_end - last_pos) >= C.DEAD_GAP_SESSIONS
        lab = _labels_block(s, cal, dead)
        f = pd.concat([f, lab], axis=1).loc[sel]
        f["symbol"] = sym
        f["dead"] = dead
        out.append(f)
    if not out:
        return pd.DataFrame()
    df = pd.concat(out, ignore_index=True)
    for c in PRICE_FEATURES + ("med_dv",):
        df[c] = df[c].astype("float32")
    df["date"] = pd.to_datetime(df["date"])
    return df


def add_excess_labels(df: pd.DataFrame) -> pd.DataFrame:
    """y_h = fwd_h minus the cross-sectional median of fwd_h over the rows of that date."""
    for h in C.HORIZONS:
        med = df.groupby("date")[f"fwd_{h}"].transform("median")
        df[f"y_{h}"] = (df[f"fwd_{h}"] - med).astype("float32")
    return df


# ─────────────────────────── side groups ─────────────────────────────────────

def _asof(rows: pd.DataFrame, right: pd.DataFrame, *, left_key: str, right_key: str,
          by_left: str = "symbol", by_right: str = "ticker", strict: bool = True,
          cols: list[str], tiebreak: tuple[str, ...] = ()) -> pd.DataFrame:
    """merge_asof that never takes a right row dated at/after the left key when strict."""
    L = rows[[by_left, left_key]].copy()
    L["_i"] = np.arange(len(L))
    L = L.sort_values(left_key, kind="mergesort")
    extra = [c for c in tiebreak if c in right.columns and c not in cols and c != right_key]
    R = right[[by_right, right_key] + cols + extra].rename(columns={by_right: by_left})
    # F9: several rows share a filing date (a 10-Q files the prior-year comparative the
    # same day). Sorted by (filed, *tiebreak), the backward join takes the LAST: the latest
    # period end, i.e. the current quarter, never the comparative.
    R = R.dropna(subset=[right_key]).sort_values([right_key] + extra, kind="mergesort")
    L[left_key] = L[left_key].astype("datetime64[ns]")
    R[right_key] = R[right_key].astype("datetime64[ns]")
    m = pd.merge_asof(L, R, left_on=left_key, right_on=right_key, by=by_left,
                      allow_exact_matches=not strict, direction="backward")
    m = m.sort_values("_i")
    return m[cols + ([right_key] if right_key != left_key else [])].reset_index(drop=True)


FLOW_FACTS = ("revenue", "net_income", "operating_income", "cogs", "rd")
STOCK_FACTS = ("assets", "equity", "cash", "debt", "shares")
STALE_FILING_DAYS = 400


def fundamentals(rows: pd.DataFrame, facts: pd.DataFrame | None = None) -> pd.DataFrame:
    """SEC fundamentals as of FILING date strictly before t. Period end is never a key."""
    if facts is None:
        facts = pd.read_parquet(C.SEC_FACTS, columns=["ticker", "fact", "filed", "end", "period_days", "val"])
    facts = facts.copy()
    facts["filed"] = pd.to_datetime(facts["filed"]).dt.normalize()
    facts["end"] = pd.to_datetime(facts["end"])
    base = rows[["symbol", "date"]].copy()
    vals: dict[str, np.ndarray] = {}
    filed_cols = []
    for f in FLOW_FACTS:
        q = facts[(facts["fact"] == f) & facts["period_days"].between(80, 100)].copy()
        # prior-year same quarter: the ORIGINAL (first-filed) record with end ~ 1y earlier
        orig = q.sort_values("filed").drop_duplicates(["ticker", "end"], keep="first")
        key = q[["ticker", "end"]].copy()
        key["end_ly"] = key["end"] - pd.Timedelta(days=365)
        key["_i"] = np.arange(len(key))
        ly = pd.merge_asof(key.sort_values("end_ly"),
                           orig[["ticker", "end", "val", "filed"]].rename(
                               columns={"end": "end_ly", "val": "ly_val", "filed": "ly_filed"}).sort_values("end_ly"),
                           on="end_ly", by="ticker", direction="nearest",
                           tolerance=pd.Timedelta(days=25)).sort_values("_i")
        q["ly_val"] = ly["ly_val"].values
        # a prior-year value must itself have been filed before the current record
        q.loc[ly["ly_filed"].values >= q["filed"].values, "ly_val"] = np.nan
        m = _asof(base, q, left_key="date", right_key="filed", strict=True, cols=["val", "ly_val"],
                  tiebreak=("end",))
        vals[f] = m["val"].values
        vals[f + "_ly"] = m["ly_val"].values
        vals[f + "_filed"] = m["filed"].values
        filed_cols.append(f + "_filed")
    for f in STOCK_FACTS:
        q = facts[facts["fact"] == f]
        m = _asof(base, q, left_key="date", right_key="filed", strict=True, cols=["val"],
                  tiebreak=("end",))
        vals[f] = m["val"].values
        vals[f + "_filed"] = m["filed"].values
        filed_cols.append(f + "_filed")
    V = pd.DataFrame(vals)
    filed = V[filed_cols].max(axis=1)
    age = (rows["date"].values - filed.values).astype("timedelta64[D]").astype("float64")
    stale = ~(age <= STALE_FILING_DAYS)
    # F1 (review 2026-09-29, the repo's VAL-01): `close` is split-adjusted for splits
    # AFTER t while `shares` is as filed at t, so close x shares shrank every future
    # splitter (NVDA 2019 read as a $1.9B company with a 255% earnings yield). Market cap
    # and the yields come ONLY from an unadjusted close; without one they are NaN.
    raw = rows["close_raw"].values.astype("float64") if "close_raw" in rows.columns         else np.full(len(rows), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        mcap = raw * V["shares"].values
        mcap = np.where(mcap > 1e6, mcap, np.nan)
        rev = V["revenue"].values
        out = pd.DataFrame({
            "f_log_mcap": np.log(mcap),
            "f_ey": 4 * V["net_income"].values / mcap,
            "f_sy": 4 * rev / mcap,
            "f_bm": V["equity"].values / mcap,
            "f_gross_margin": np.where(rev > 0, (rev - V["cogs"].values) / rev, np.nan),
            "f_op_margin": np.where(rev > 0, V["operating_income"].values / rev, np.nan),
            "f_rev_yoy": np.where(V["revenue_ly"].values > 0, rev / V["revenue_ly"].values - 1, np.nan),
            "f_ni_yoy": (V["net_income"].values - V["net_income_ly"].values) / np.abs(V["net_income_ly"].values),
            "f_debt_assets": V["debt"].values / np.where(V["assets"].values > 0, V["assets"].values, np.nan),
            "f_cash_assets": V["cash"].values / np.where(V["assets"].values > 0, V["assets"].values, np.nan),
            "f_rd_rev": np.where(rev > 0, V["rd"].values / rev, np.nan),
            "f_days_since_filing": age,
        })
    out = out.replace([np.inf, -np.inf], np.nan)
    out.loc[stale] = np.nan
    # no full-sample clipping: that would leak the future's distribution into t.
    # Models consume per-date ranks (NN, ridge) or split points (LightGBM).
    out = out.astype("float32")
    out["fund_filed_max"] = filed.where(~stale).values
    return out


def _window_counts(rows: pd.DataFrame, daily: pd.DataFrame, cols: list[str], windows: dict[str, int],
                   by_right: str) -> pd.DataFrame:
    """Sum of `cols` over (t - w days, t - 1 day] from per-day records, via cumulative sums.

    Strictly before the decision DAY: an event stamped on day t is not used at t."""
    d = daily.sort_values([by_right, "day"]).copy()
    for c in cols:
        d["cum_" + c] = d.groupby(by_right)[c].cumsum()
    d["last_day"] = d["day"]
    cum_cols = ["cum_" + c for c in cols]
    base = rows[["symbol", "date"]].copy()
    base["k0"] = base["date"] - pd.Timedelta(days=1)
    now = _asof(base, d, left_key="k0", right_key="day", strict=False, cols=cum_cols + ["last_day"],
                by_right=by_right)
    res = {"last_day": now["last_day"].values}
    for name, w in windows.items():
        base[f"k{w}"] = base["date"] - pd.Timedelta(days=w + 1)
        then = _asof(base, d, left_key=f"k{w}", right_key="day", strict=False, cols=cum_cols,
                     by_right=by_right)
        for c in cols:
            a = now["cum_" + c].values
            b = np.nan_to_num(then["cum_" + c].values, nan=0.0)
            res[f"{c}__{name}"] = a - b     # NaN when the name has no record before t (unknown, not zero)
    return pd.DataFrame(res)


def analyst_pit_from(analyst_dir: Path | None = None) -> pd.Timestamp | None:
    """The first day the analyst snapshot is point-in-time: the date of the FIRST pull
    receipt on disk (`analyst_pull_YYYY-MM-DD.json`). None when there is none (then the
    group is unavailable everywhere)."""
    d = Path(analyst_dir or C.ANALYST_REVISIONS.parent)
    days = sorted(p.stem.rsplit("_", 1)[-1] for p in d.glob(C.ANALYST_PULL_GLOB))
    return pd.Timestamp(days[0]) if days else None


_UNSET = object()


def analyst(rows: pd.DataFrame, rev: pd.DataFrame | None = None, pit_from=_UNSET) -> pd.DataFrame:
    """Analyst revisions strictly before t.

    F2 (review 2026-09-29): the revisions file is a 2026 snapshot that can only list names
    alive in 2026 (coverage 0% for names that later died, 87-97% for survivors), so its
    COVERAGE before the first snapshot was decided by the future. Rows dated before
    `pit_from` get NaN for EVERY name, whatever the file holds."""
    if pit_from is _UNSET:
        pit_from = analyst_pit_from()
    if rev is None:
        rev = pd.read_parquet(C.ANALYST_REVISIONS, columns=["ticker", "event_date", "action", "target_change"])
    r = rev.copy()
    r["day"] = pd.to_datetime(r["event_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    r = r.dropna(subset=["day"])
    r["n"] = 1.0
    r["up"] = (r["action"] == "up").astype(float)
    r["down"] = (r["action"] == "down").astype(float)
    r["init"] = (r["action"] == "init").astype(float)
    tc = pd.to_numeric(r["target_change"], errors="coerce").clip(-0.9, 2.0)
    r["tc_sum"] = tc.fillna(0.0)
    r["tc_n"] = tc.notna().astype(float)
    daily = r.groupby(["ticker", "day"], as_index=False)[["n", "up", "down", "init", "tc_sum", "tc_n"]].sum()
    w = _window_counts(rows, daily, ["n", "up", "down", "init", "tc_sum", "tc_n"],
                       {"63": 63, "21": 21}, by_right="ticker")
    with np.errstate(divide="ignore", invalid="ignore"):
        out = pd.DataFrame({
            "an_n_63": np.log1p(w["n__63"]),
            "an_up_63": w["up__63"],
            "an_down_63": w["down__63"],
            "an_net_63": w["up__63"] - w["down__63"],
            "an_init_63": w["init__63"],
            "an_net_21": w["up__21"] - w["down__21"],
            "an_tgt_chg_63": np.where(w["tc_n__63"] > 0, w["tc_sum__63"] / w["tc_n__63"], np.nan),
        }).astype("float32")
    out["analyst_last_day"] = w["last_day"]
    before = (np.ones(len(rows), dtype=bool) if pit_from is None
              else (rows["date"].values < np.datetime64(pd.Timestamp(pit_from))))
    if before.any():
        out.loc[before, list(ANALYST_FEATURES)] = np.nan
        out.loc[before, "analyst_last_day"] = pd.NaT
    return out


def news(rows: pd.DataFrame, panel: pd.DataFrame | None = None) -> pd.DataFrame:
    if panel is None:
        panel = pd.read_parquet(C.NEWS_PANEL, columns=["symbol", "published_utc"])
    p = panel.copy()
    p["day"] = pd.to_datetime(p["published_utc"], errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    p = p.dropna(subset=["day"])
    p["n"] = 1.0
    daily = p.groupby(["symbol", "day"], as_index=False)["n"].sum().rename(columns={"symbol": "ticker"})
    w = _window_counts(rows, daily, ["n"], {"5": 5, "21": 21}, by_right="ticker")
    start = daily["day"].min() if len(daily) else pd.Timestamp.max
    before = rows["date"].values <= np.datetime64(start + pd.Timedelta(days=21))
    out = pd.DataFrame({"news_n_5": np.log1p(w["n__5"]), "news_n_21": np.log1p(w["n__21"])})
    # inside the panel's coverage a name with no article is a true zero; before it, unknown
    out = out.where(~np.isnan(out.values), 0.0)
    out.loc[before] = np.nan
    out = out.astype("float32")
    out["news_last_day"] = w["last_day"]
    return out


def ledger(rows: pd.DataFrame, path: Path | None = None) -> pd.DataFrame:
    """The forecast ledger's probabilities, only for forecasts MADE before t."""
    path = path or C.FORECAST_LEDGER
    recs = []
    if Path(path).exists():
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("ticker") and r.get("made_at") and r.get("probability") is not None:
                    recs.append((r["ticker"], r["made_at"], float(r["probability"])))
    if not recs:
        return pd.DataFrame({"ledger_prob_10": np.full(len(rows), np.nan, "float32"),
                             "ledger_n_10": np.full(len(rows), np.nan, "float32"),
                             "ledger_last_day": pd.NaT})
    L = pd.DataFrame(recs, columns=["ticker", "made_at", "p"])
    L["day"] = pd.to_datetime(L["made_at"], errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    L = L.dropna(subset=["day"])
    L["n"] = 1.0
    daily = L.groupby(["ticker", "day"], as_index=False).agg(n=("n", "sum"), p=("p", "sum"))
    w = _window_counts(rows, daily, ["n", "p"], {"10": 10}, by_right="ticker")
    with np.errstate(divide="ignore", invalid="ignore"):
        n10 = w["n__10"]
        out = pd.DataFrame({"ledger_prob_10": np.where(n10 > 0, w["p__10"] / n10, np.nan),
                            "ledger_n_10": np.where(n10 > 0, np.log1p(n10), np.nan)}).astype("float32")
    out["ledger_last_day"] = w["last_day"]
    return out


def attach_side_groups(rows: pd.DataFrame, *, facts=None, rev=None, news_panel=None,
                       ledger_path=None) -> pd.DataFrame:
    rows = rows.reset_index(drop=True)
    parts = [rows, fundamentals(rows, facts), analyst(rows, rev), news(rows, news_panel),
             ledger(rows, ledger_path)]
    return pd.concat(parts, axis=1)


# ─────────────────────────────── PIT audit ───────────────────────────────────

def assert_pit(df: pd.DataFrame) -> dict:
    """RAISE if any group's availability stamp is on/after its row's decision date."""
    report = {}
    for g, col in STAMPS.items():
        if col not in df.columns:
            continue
        st = pd.to_datetime(df[col])
        bad = st.notna() & (st >= df["date"])
        report[g] = int(bad.sum())
        if bad.any():
            ex = df.loc[bad, ["symbol", "date", col]].head(3).to_dict("records")
            raise PITViolation(f"group {g!r}: {int(bad.sum())} rows use data stamped on/after t, e.g. {ex}")
    return report


# ─────────────────────────────── builder ─────────────────────────────────────

def coverage(df: pd.DataFrame) -> dict:
    return {c: round(float(df[c].notna().mean()), 4)
            for g in GROUPS.values() for c in g if c in df.columns}


def survivorship(df: pd.DataFrame) -> dict:
    last = df.groupby("symbol")["date"].max()
    end = df["date"].max()
    dead = int(df.groupby("symbol")["dead"].first().sum())
    return {"n_symbols": int(last.size), "n_dead_symbols": dead,
            "rows_from_dead_symbols": int(df["dead"].sum()),
            "rows_with_delisting_exit_21": int(df.get("delist_exit_21", pd.Series(False)).sum()),
            "dead_by_last_year": (df[df["dead"]].groupby("symbol")["date"].max().dt.year
                                  .value_counts().sort_index().to_dict()),
            "verdict": ("PARTIALLY SURVIVOR-SELECTED: living names were chosen alive on 2026-09-01; "
                        "dead names come from the inactive listed list (mostly 2018-22 deaths) plus, "
                        "when USE_CRSP_DEATHS, CRSP-verified 2016-2024 deaths (nn_lab/deaths_crsp.py); "
                        "no OTC, no 2025-26 deaths beyond the inactive list; a dead name exits at its "
                        "last close, true delisting return unknown. Every result carries this caveat.")}


def build(start: str = "2016-01-01", symbols_limit: int | None = None, out: Path | None = None,
          bars_paths: Iterable[Path] | None = None, extend_only: Iterable[Path] = ()) -> dict:
    """Build the full table from the deep + delisted bars. Returns the receipt."""
    t0 = datetime.now(timezone.utc)
    out = Path(out or C.TABLE_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    paths = list(bars_paths or [C.BARS_DEEP, C.BARS_DELISTED])
    if bars_paths is None and C.USE_CRSP_DEATHS and C.BARS_DELISTED_CRSP.exists():
        paths.append(C.BARS_DELISTED_CRSP)      # F3: 2016-2024 deaths from CRSP (nn_lab/deaths_crsp.py)
    syms = None
    if symbols_limit:
        allsyms = pd.read_parquet(paths[0], columns=["symbol"])["symbol"].unique()
        rng = np.random.default_rng(20260928)
        syms = list(rng.choice(allsyms, size=min(symbols_limit, len(allsyms)), replace=False)) + [C.MARKET]
    bars = load_bars(paths, start=start, symbols=syms, extend_only=extend_only)
    raw_note = "OFF (config.USE_CLOSE_RAW)"
    if C.USE_CLOSE_RAW:
        from nn_lab import raw_prices as RP
        if RP.RAW_MONTHLY.exists():
            ratios = RP.month_end_ratios(bars, pd.read_parquet(RP.RAW_MONTHLY))
            bars = RP.attach_close_raw(bars, ratios)
            raw_note = f"ON: close_raw on {float(bars['close_raw'].notna().mean()):.1%} of bars"
        else:
            raw_note = f"ON but {RP.RAW_MONTHLY.name} absent: close_raw NaN"
    cal = session_calendar(bars)
    grid = cal[grid_mask(cal)]
    rows = price_rows(bars, cal, keep_dates=grid, keep_last=True)
    del bars
    rows = add_excess_labels(rows)
    rows["on_grid"] = rows["date"].isin(set(grid))
    rows = attach_side_groups(rows)
    pit = assert_pit(rows)
    rows.to_parquet(out, index=False)
    pd.DataFrame({"date": cal}).to_parquet(out.parent / "calendar.parquet", index=False)
    rec = describe(rows)
    rec.update({"artefact": "NN_LAB_TABLE", "path": str(out), "pit_violations": pit,
                "delisted_symbols_dropped_as_reused_tickers": sorted(set(REUSED_TICKERS)),
                "close_raw": raw_note,
                "dead_symbols_renamed_as_reused_tickers": {"n": len(set(RENAMED_DEAD)),
                                                           "examples": sorted(set(RENAMED_DEAD))[:25]},
                "etf_exclusions": {"flag": C.EXCLUDE_ETFS, "file": str(C.ETF_EXCLUSIONS),
                                   "n_in_file": len(__import__("nn_lab.universe_filter",
                                                               fromlist=["excluded"]).excluded())},
                "dead_names_by_last_year": (rows[rows["dead"]].groupby("symbol")["date"].max().dt.year
                                            .value_counts().sort_index().to_dict()),
                "symbols_split_at_gaps_over_20_sessions": {"n": len(SPLIT_SYMBOLS),
                                                           "examples": sorted(SPLIT_SYMBOLS)[:25]},
                "bars_sources": [str(p) for p in paths], "symbols_limit": symbols_limit,
                "calendar_sessions": len(cal), "grid_dates": int(len(grid)),
                "built_utc": t0.isoformat(timespec="seconds"),
                "elapsed_s": round((datetime.now(timezone.utc) - t0).total_seconds(), 1)})
    return rec


def describe(rows: pd.DataFrame) -> dict:
    g = rows[rows["on_grid"]] if "on_grid" in rows else rows
    per = g.groupby("date").size()
    return {
        "rows": int(len(rows)), "grid_rows": int(len(g)),
        "first_date": str(rows["date"].min().date()), "last_date": str(rows["date"].max().date()),
        "decision_dates": int(per.size),
        "names_per_date": {"min": int(per.min()), "median": int(per.median()), "max": int(per.max())},
        "labelled_rows": {f"y_{h}": int(g[f"y_{h}"].notna().sum()) for h in C.HORIZONS},
        "missing_fraction": {k: round(1 - v, 4) for k, v in coverage(g).items()},
        "group_coverage": {gname: round(float(g[list(cols)].notna().any(axis=1).mean()), 4)
                           for gname, cols in GROUPS.items()},
        "survivorship": survivorship(rows),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--symbols-limit", type=int, default=None)
    a = ap.parse_args()
    rec = build(start=a.start, symbols_limit=a.symbols_limit)
    C.RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    p = C.RECEIPT_DIR / f"table_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    p.write_text(json.dumps(rec, indent=1, default=str))
    print(json.dumps(rec, indent=1, default=str))
