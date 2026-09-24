"""The cross-sectional 21-session ranker — what is the best name to own NEXT MONTH.

WHY THIS MODULE EXISTS (2026-09-22, Murat's brief + the morning report)
=======================================================================
The 2026-09-22 morning report said the thing that matters: *all 30 largest moves
of the last 21 sessions were outside our universe*. That was read as a universe
bug. It is worse than a universe bug. `investment_committee.funnel_state()`
serves `backend/data/funnel_night10.json`, whose `generated_at` is
**2026-08-11T02:33:48Z** — a static file. Every EXPLOIT / EXPLORE / PROBE /
REFUSED row this programme has produced for six weeks was computed over the
forty tickers that a single August night happened to shortlist. Today's
contract scored `n_considered: 2`.

Meanwhile `backend/data/optimus/prices_2025_26/bars.parquet` holds 1,275,452
daily bars for 3,060 symbols over 430 sessions to 2026-09-21, built by P6 and
read by no decision.

This module joins them. It answers ONE question, for every liquid US name:

    Relative to every other eligible stock, where does this one rank on
    expected total return over the next 21 sessions?

THE LICENCE (CLAUDE.md, "THREE LICENCES")
=========================================
`PRODUCT_EXPERIMENT`. Internal simulation and external PAPER brokerage. No
significance gate, no MDE, no multiplicity control, no 24-month floor — those
govern a `RESEARCH_CLAIM`, and nothing here is one. What does NOT relax, and is
enforced below rather than intended:

1. **No information acted on before it was public.** Every feature is a function
   of bars at or before `t`; the forward window starts at `t+1`.
2. **No target leakage.** The 21-session target overlaps the next 20 days of
   targets, so a plain walk-forward split trains on rows whose OUTCOMES live
   inside the test window. `PURGE_SESSIONS` cuts exactly one horizon out between
   every train end and test start. This is the single defect that makes a
   backtested ranker look brilliant and lose money.
3. **Costs are never omitted.** `expected_relative_return_21d` is reported GROSS
   and NET, and the net figure subtracts a round-trip drawn from the empirical
   cost curve, never a flat guess.
4. **A frozen version once it trades.** `model_version` is the sha of the
   feature list + hyperparameters + train window, and it is written onto every
   row the live loop acts on.

WHAT IT REFUSES TO CLAIM
========================
430 sessions is ~1.6 years. That is enough to fit and honestly validate a
ranker for paper deployment; it is NOT enough to claim alpha, and this module
must never be quoted as evidence of one. `read_me_first` on every receipt says
so. The information coefficient it reports is an OOS number over a single
regime, and one regime is one observation.

WHY THE MODEL PREDICTS A PERCENTILE
===================================
The target is the within-date percentile of the forward 21-session return, not
the return itself. Two reasons, and the second is the one that earns its keep:

* Every name on a given date shares that date's market shock, so ranking within
  the date differences the market factor out without estimating one beta. The
  long-only relative-return mandate (and the Bloomberg Challenge's
  time-weighted relative return vs the WLS index) is scored on exactly this.
* A percentile target is bounded and roughly uniform, so a single fat-tailed
  name — MRNA +176% in this very window — cannot dominate the loss the way it
  dominates a squared-error fit on raw returns.

RANK IS NOT A RETURN, AND THE DIFFERENCE IS THE WHOLE SIZING PROBLEM
====================================================================
The model emits a score whose units are "percentile-ish" and mean nothing to a
position sizer. `calibrate()` maps score deciles to their **realised OOS**
relative return, p20 downside and hit rate, and `rank_asof()` reports those.
This is chunk 22's rank -> return calibration applied to the ranker itself: the
number a Kelly fraction multiplies must be a measured return, never a model
output. When a decile has too few OOS observations its expected return is
`None` and the sizer must treat it as unmeasured, not as zero.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Paths resolve through `config.OPTIMUS_LEDGER_DIR`, which consults
# AEGIS_REPO_ROOT. A `Path(__file__)`-rooted data path reads `_internal/` inside
# the frozen desktop build -- empty, and silent about it. That is defect family
# #14 and `test_frozen_path_family` exists to stop it recurring.
from backend import config as _cfg

_OPTIMUS = _cfg.OPTIMUS_LEDGER_DIR
BARS_PATH = _OPTIMUS / "prices_2025_26" / "bars.parquet"
OUT_DIR = _OPTIMUS / "xs_ranker"

#: The forward window the ranker is scored on. 21 sessions ~ one calendar month,
#: which is the Bloomberg Challenge's natural unit and Murat's "great projection
#: in the next month".
HORIZON_SESSIONS = 21

#: Cut exactly one horizon between train end and test start. Any smaller number
#: leaks the test window's outcomes into training through overlapping labels.
PURGE_SESSIONS = HORIZON_SESSIONS

#: Minimum training rows before a fold is allowed to fit at all. A fold that
#: cannot meet this REFUSES rather than fitting on noise.
MIN_TRAIN_ROWS = 40_000

#: Distinct DECISION DATES the panel must carry before walk-forward is allowed.
#: This is NOT the same quantity as MIN_HISTORY_SESSIONS, which is a per-symbol
#: listing floor. Conflating the two is what refused the first run: a panel
#: starting 2025-01 has 430 sessions but only 156 dates on which a name can
#: carry 12-1 momentum AND a realised 21-session outcome.
MIN_DECISION_DATES = 120

#: Liquidity floors. A name a $10k ticket cannot enter without being the tape is
#: not an opportunity for this account, whatever its rank.
MIN_PRICE = 3.0
MAX_PRICE = 10_000.0
MIN_MEDIAN_DOLLAR_VOL = 3_000_000.0
#: A name must have traded this many sessions before it can be ranked. 126 (six
#: months) rather than 252: requiring a full year to compute 12-1 momentum threw
#: away 60% of the panel, and LightGBM reads a NaN 12-1 natively (CLAUDE.md: do
#: not fillna a feature matrix). A name with no 12-1 is ranked on the features
#: it does have, and `why` says which ones were absent.
MIN_HISTORY_SESSIONS = 126

#: Index proxies live in the same panel and must never be ranked as stocks.
INDEX_PROXIES = frozenset({"SPY", "QQQ", "IWM", "RSP", "DIA", "VTI", "VOO"})

#: Benchmark for the relative-return target. Equal-weight of the eligible
#: cross-section: it is the thing a long-only book of ranked names is actually
#: competing with, and unlike SPY it is not 35% seven mega-caps.
BENCHMARK = "XS_EQUAL_WEIGHT"

#: Round-trip cost in basis points, by liquidity band, from the empirical cost
#: curve work (2026-09-12). Applied to BOTH legs of a 21-session hold.
COST_BPS_BY_BAND = {"mega": 6.0, "large": 10.0, "mid": 18.0, "small": 35.0}

FEATURES: tuple[str, ...] = (
    "mom_21", "mom_63", "mom_126", "mom_252_21",
    "rev_1", "rev_5",
    "vol_21", "vol_63", "vol_ratio",
    "dollar_vol_log", "turnover_surge", "trade_surge",
    "px_vs_52w_high", "px_vs_52w_low", "px_vs_ma50", "px_vs_ma200",
    "amihud", "gap_share", "vwap_pressure",
    "resid_mom_63", "beta_63",
    "up_days_21", "max_drawdown_63", "skew_63",
)

LGB_PARAMS: dict[str, Any] = {
    "objective": "regression",
    "metric": "l2",
    "learning_rate": 0.04,
    "num_leaves": 31,
    "min_child_samples": 200,
    "feature_fraction": 0.75,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 5.0,
    "n_estimators": 350,
    "verbose": -1,
}


class RankerError(RuntimeError):
    """The ranker cannot produce a trustworthy ranking."""


# ───────────────────────────────── loading ──────────────────────────────────

#: Panels that together make a survivorship-free universe. The deep pull holds
#: names alive on 2026-09-01; `bars_delisted` holds the ones that died. Ranking
#: over the first alone is what produced the 2026-09-22 bake-off's +3.13%, and
#: that number is not believable without the second.
DEEP_BARS_PATH = _OPTIMUS / "prices_deep" / "bars.parquet"
DELISTED_BARS_PATH = _OPTIMUS / "prices_deep" / "bars_delisted.parquet"

_BAR_COLUMNS = {"symbol", "date", "open", "high", "low", "close", "volume"}


def load_bars(path: Path | Iterable[Path] | None = None) -> pd.DataFrame:
    """The daily panel, sorted and typed. Raises rather than returning empty.

    Accepts several parquets and concatenates them, which is how a
    survivorship-free panel is assembled: living names from one pull, dead names
    from another. A symbol present in both keeps its first occurrence, so a
    partial re-pull cannot silently duplicate a name's history.
    """
    paths = ([Path(path)] if isinstance(path, (str, Path))
             else [Path(p) for p in path] if path is not None
             else [BARS_PATH])
    frames = []
    for p in paths:
        if not p.exists():
            raise RankerError(
                f"no bars panel at {p}. Build it with "
                f"`python -m scripts.pull_deep_bars` / `pull_delisted_bars`.")
        df = pd.read_parquet(p)
        missing = _BAR_COLUMNS - set(df.columns)
        if missing:
            raise RankerError(f"{p.name} is missing columns {sorted(missing)}")
        frames.append(df)
    out = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    out["date"] = pd.to_datetime(out["date"])
    out = out.drop_duplicates(subset=["symbol", "date"], keep="first")
    out = out.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)
    return out


def survivorship_free_paths() -> list[Path]:
    """Every panel that exists, preferring the deep pull over the 2025-26 one."""
    base = DEEP_BARS_PATH if DEEP_BARS_PATH.exists() else BARS_PATH
    out = [base]
    if DELISTED_BARS_PATH.exists():
        out.append(DELISTED_BARS_PATH)
    return out


def survivorship_audit(bars: pd.DataFrame) -> dict:
    """How many names in this panel stopped trading? Zero means selection.

    Printed on every bake-off receipt so a reader never has to wonder which
    universe a number came from.
    """
    last = bars.groupby("symbol")["date"].max()
    end = bars["date"].max()
    died = {
        f"stopped_{d}d_before_end": int((last < end - pd.Timedelta(days=d)).sum())
        for d in (30, 90, 180)
    }
    n = len(last)
    frac = died["stopped_90d_before_end"] / n if n else 0.0
    return {
        "n_symbols": int(n),
        "panel_last_session": str(end.date()),
        **died,
        "fraction_dead_90d": round(frac, 4),
        "verdict": (
            "SURVIVOR-SELECTED: no symbol stops trading, which cannot happen in a "
            "real US cross-section. Every result over this panel is biased toward "
            "whatever the dead names were — small, illiquid and distressed."
            if died["stopped_90d_before_end"] == 0 else
            f"{died['stopped_90d_before_end']:,} of {n:,} symbols ({frac:.1%}) stop "
            f"trading well before the end, so delistings are represented."),
    }


# ──────────────────────────────── features ──────────────────────────────────

def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.replace(0.0, np.nan)


def build_features(bars: pd.DataFrame, *, market_symbol: str = "SPY") -> pd.DataFrame:
    """One row per (symbol, date) with every feature computed from t and earlier.

    Every rolling window here is trailing and closed on the right at `t`, so a
    row dated `t` is computable at `t`'s close and acted on at `t+1`'s open.
    There is no `shift(-1)` anywhere in this function; the only forward-looking
    code in the module lives in `build_target`, which is a separate call so the
    two can never be confused at a call site.
    """
    df = bars.copy()
    g = df.groupby("symbol", sort=False)

    df["ret_1"] = g["close"].pct_change(fill_method=None)
    df["dollar_vol"] = df["close"] * df["volume"]

    # momentum family. mom_252_21 is the classic 12-1: a year of drift with the
    # most recent month cut out, because that month is reversal, not momentum.
    df["mom_21"] = g["close"].pct_change(21, fill_method=None)
    df["mom_63"] = g["close"].pct_change(63, fill_method=None)
    df["mom_126"] = g["close"].pct_change(126, fill_method=None)
    c252 = g["close"].shift(252)
    c21 = g["close"].shift(21)
    df["mom_252_21"] = _safe_div(c21, c252) - 1.0

    df["rev_1"] = df["ret_1"]
    df["rev_5"] = g["close"].pct_change(5, fill_method=None)

    df["vol_21"] = g["ret_1"].transform(lambda s: s.rolling(21, min_periods=15).std()) * math.sqrt(252)
    df["vol_63"] = g["ret_1"].transform(lambda s: s.rolling(63, min_periods=40).std()) * math.sqrt(252)
    df["vol_ratio"] = _safe_div(df["vol_21"], df["vol_63"])

    dv63 = g["dollar_vol"].transform(lambda s: s.rolling(63, min_periods=40).median())
    df["median_dollar_vol"] = dv63
    df["dollar_vol_log"] = np.log1p(dv63)
    dv5 = g["dollar_vol"].transform(lambda s: s.rolling(5, min_periods=3).mean())
    df["turnover_surge"] = np.log1p(_safe_div(dv5, dv63))
    tr63 = g["trades"].transform(lambda s: s.rolling(63, min_periods=40).median()) if "trades" in df else None
    if tr63 is not None:
        tr5 = g["trades"].transform(lambda s: s.rolling(5, min_periods=3).mean())
        df["trade_surge"] = np.log1p(_safe_div(tr5, tr63))
    else:
        df["trade_surge"] = np.nan

    hi252 = g["high"].transform(lambda s: s.rolling(252, min_periods=120).max())
    lo252 = g["low"].transform(lambda s: s.rolling(252, min_periods=120).min())
    df["px_vs_52w_high"] = _safe_div(df["close"], hi252) - 1.0
    df["px_vs_52w_low"] = _safe_div(df["close"], lo252) - 1.0
    ma50 = g["close"].transform(lambda s: s.rolling(50, min_periods=30).mean())
    ma200 = g["close"].transform(lambda s: s.rolling(200, min_periods=120).mean())
    df["px_vs_ma50"] = _safe_div(df["close"], ma50) - 1.0
    df["px_vs_ma200"] = _safe_div(df["close"], ma200) - 1.0

    # Amihud illiquidity: |return| per dollar traded. High = a small ticket moves it.
    df["amihud"] = np.log1p(_safe_div(df["ret_1"].abs(), df["dollar_vol"]) * 1e9)

    # Overnight vs intraday. A name whose move is all gap is reacting to news;
    # one whose move is all session is being accumulated.
    prev_close = g["close"].shift(1)
    gap = _safe_div(df["open"], prev_close) - 1.0
    intraday = _safe_div(df["close"], df["open"]) - 1.0
    tot = gap.abs() + intraday.abs()
    df["gap_share"] = (_safe_div(gap.abs(), tot).groupby(df["symbol"])
                       .transform(lambda s: s.rolling(21, min_periods=10).mean()))

    if "vwap" in df.columns:
        df["vwap_pressure"] = ((_safe_div(df["close"], df["vwap"]) - 1.0)
                               .groupby(df["symbol"])
                               .transform(lambda s: s.rolling(10, min_periods=5).mean()))
    else:
        df["vwap_pressure"] = np.nan

    df["up_days_21"] = g["ret_1"].transform(
        lambda s: (s > 0).rolling(21, min_periods=15).mean())
    roll_max = g["close"].transform(lambda s: s.rolling(63, min_periods=40).max())
    df["max_drawdown_63"] = _safe_div(df["close"], roll_max) - 1.0
    df["skew_63"] = g["ret_1"].transform(lambda s: s.rolling(63, min_periods=40).skew())

    # Residual momentum: the part of 63-session drift the market did not give
    # you. Computed against the market proxy's own return series on the same
    # dates, with beta estimated on the same trailing window.
    mkt = (bars.loc[bars["symbol"] == market_symbol, ["date", "close"]]
           .sort_values("date").set_index("date")["close"].pct_change(fill_method=None))
    if mkt.dropna().empty:
        logger.warning("xs_ranker: market proxy %s absent; residual momentum is NaN", market_symbol)
        df["beta_63"] = np.nan
        df["resid_mom_63"] = np.nan
    else:
        df["mkt_ret"] = df["date"].map(mkt)
        cov = df.groupby("symbol", sort=False).apply(
            lambda d: d["ret_1"].rolling(63, min_periods=40).cov(d["mkt_ret"]),
            include_groups=False).reset_index(level=0, drop=True)
        var = df["mkt_ret"].rolling(63, min_periods=40).var()
        df["beta_63"] = (cov / var).replace([np.inf, -np.inf], np.nan)
        mkt_63 = df["date"].map(mkt.rolling(63, min_periods=40).sum())
        df["resid_mom_63"] = df["mom_63"] - df["beta_63"] * mkt_63

    return df


# ───────────────────────────────── target ───────────────────────────────────

def build_target(df: pd.DataFrame, *, horizon: int = HORIZON_SESSIONS) -> pd.DataFrame:
    """Forward relative return over `horizon` sessions, and its within-date rank.

    THE ONLY forward-looking code in this module. The forward window is entered
    at t+1's open and exited at t+1+horizon's close, so a row dated t is never
    credited with a move that had already happened when it was scored.
    """
    out = df.copy()
    g = out.groupby("symbol", sort=False)
    entry = g["open"].shift(-1)
    exit_ = g["close"].shift(-(horizon + 1))
    out["fwd_ret"] = (exit_ / entry) - 1.0

    # Relative to the equal-weight eligible cross-section on the same date.
    bench = out.loc[out["eligible"], ["date", "fwd_ret"]].groupby("date")["fwd_ret"].mean()
    out["bench_fwd_ret"] = out["date"].map(bench)
    out["fwd_rel"] = out["fwd_ret"] - out["bench_fwd_ret"]

    elig = out["eligible"] & out["fwd_rel"].notna()
    out["y"] = np.nan
    out.loc[elig, "y"] = (out.loc[elig].groupby("date")["fwd_rel"]
                          .rank(pct=True, method="average"))
    return out


def mark_eligible(df: pd.DataFrame) -> pd.DataFrame:
    """Liquidity / listing floors, computed from trailing data only."""
    out = df.copy()
    sessions = out.groupby("symbol", sort=False).cumcount() + 1
    out["sessions_seen"] = sessions
    out["eligible"] = (
        out["close"].between(MIN_PRICE, MAX_PRICE)
        & (out["median_dollar_vol"] >= MIN_MEDIAN_DOLLAR_VOL)
        & (out["sessions_seen"] >= MIN_HISTORY_SESSIONS)
        & (~out["symbol"].isin(INDEX_PROXIES))
        & out["vol_63"].notna()
        & out["mom_63"].notna()
    )
    return out


def liquidity_band(median_dollar_vol: float | None) -> str:
    if median_dollar_vol is None or not np.isfinite(median_dollar_vol):
        return "small"
    if median_dollar_vol >= 1e9:
        return "mega"
    if median_dollar_vol >= 1e8:
        return "large"
    if median_dollar_vol >= 2e7:
        return "mid"
    return "small"


def round_trip_bps(median_dollar_vol: float | None) -> float:
    return COST_BPS_BY_BAND[liquidity_band(median_dollar_vol)]


# ───────────────────────── walk-forward, purged ─────────────────────────────

@dataclass
class Fold:
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    n_train: int
    n_test: int
    refused: str | None = None


def make_folds(dates: np.ndarray, *, n_folds: int = 4,
               min_train_frac: float = 0.45) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Expanding-window folds with a one-horizon purge between train and test."""
    d = np.sort(np.unique(dates))
    n = len(d)
    if n < MIN_DECISION_DATES:
        raise RankerError(
            f"only {n} decision dates carry both features and a realised outcome; "
            f"need >= {MIN_DECISION_DATES}. Deepen the panel with "
            f"`python -m scripts.pull_deep_bars --start 2016-01-01`.")
    start = int(n * min_train_frac)
    span = (n - start) // n_folds
    folds = []
    for k in range(n_folds):
        te_start_i = start + k * span + PURGE_SESSIONS
        te_end_i = start + (k + 1) * span if k < n_folds - 1 else n - 1
        tr_end_i = start + k * span
        if te_start_i >= te_end_i:
            continue
        folds.append((pd.Timestamp(d[tr_end_i]), pd.Timestamp(d[te_start_i]),
                      pd.Timestamp(d[te_end_i])))
    return folds


def walk_forward(panel: pd.DataFrame, *, features: Iterable[str] = FEATURES,
                 n_folds: int = 4, params: dict | None = None) -> tuple[pd.DataFrame, list[Fold]]:
    """Fit fold by fold, predict only forward, never on a purged row.

    Returns the OOS prediction frame and the fold ledger. A fold that cannot
    meet `MIN_TRAIN_ROWS` is REFUSED and named in the ledger rather than fitted
    on too little data and silently believed.
    """
    import lightgbm as lgb

    feats = list(features)
    fit_rows = panel[panel["eligible"] & panel["y"].notna()].copy()
    folds: list[Fold] = []
    preds: list[pd.DataFrame] = []

    for tr_end, te_start, te_end in make_folds(fit_rows["date"].values, n_folds=n_folds):
        tr = fit_rows[fit_rows["date"] <= tr_end]
        te = fit_rows[(fit_rows["date"] >= te_start) & (fit_rows["date"] <= te_end)]
        if len(tr) < MIN_TRAIN_ROWS:
            folds.append(Fold(tr_end, te_start, te_end, len(tr), len(te),
                              refused=f"train rows {len(tr):,} < MIN_TRAIN_ROWS {MIN_TRAIN_ROWS:,}"))
            continue
        if te.empty:
            folds.append(Fold(tr_end, te_start, te_end, len(tr), 0, refused="empty test window"))
            continue
        model = lgb.LGBMRegressor(**(params or LGB_PARAMS))
        model.fit(tr[feats], tr["y"])
        p = te[["symbol", "date", "y", "fwd_rel", "fwd_ret", "bench_fwd_ret",
                "median_dollar_vol", "close"]].copy()
        p["score"] = model.predict(te[feats])
        p["fold_train_end"] = tr_end
        preds.append(p)
        folds.append(Fold(tr_end, te_start, te_end, len(tr), len(te)))

    if not preds:
        raise RankerError("every fold refused; nothing was fitted. See the fold ledger.")
    oos = pd.concat(preds, ignore_index=True)
    # within-date rank of the SCORE is what a book actually acts on
    oos["score_pct"] = oos.groupby("date")["score"].rank(pct=True, method="average")
    oos["decile"] = np.clip((oos["score_pct"] * 10).astype(int), 0, 9)
    return oos, folds


# ─────────────────────────── rank -> return map ─────────────────────────────

#: A decile with fewer than this many OOS observations, or fewer than this many
#: distinct DATE BLOCKS, reports `None` for its expected return. CANON §58: the
#: effective n of overlapping 21-session windows is the number of date blocks,
#: not the number of rows — 200 names on one date is one observation of that
#: date's shock, not 200.
MIN_DECILE_ROWS = 500
MIN_DECILE_BLOCKS = 6


def calibrate(oos: pd.DataFrame) -> dict:
    """Map score deciles to their REALISED out-of-sample relative return.

    The sizer multiplies this, never the model score. A decile that has not
    earned a number says so with `None` and the sizer must treat it as
    unmeasured (PROBE), not as zero (which would read as a confident flat call).
    """
    rows = []
    # a date block = one calendar month of decision dates; overlapping 21-session
    # windows inside a month are one observation of that month's regime
    oos = oos.copy()
    oos["block"] = pd.to_datetime(oos["date"]).dt.to_period("M").astype(str)
    for d, grp in oos.groupby("decile"):
        n, blocks = len(grp), grp["block"].nunique()
        enough = n >= MIN_DECILE_ROWS and blocks >= MIN_DECILE_BLOCKS
        # block-mean first, then the se across blocks: the honest standard error
        # when rows inside a block are not independent
        bm = grp.groupby("block")["fwd_rel"].mean()
        se = float(bm.std(ddof=1) / math.sqrt(len(bm))) if len(bm) > 1 else float("nan")
        rows.append({
            "decile": int(d),
            "n_rows": int(n),
            "n_blocks": int(blocks),
            "measured": bool(enough),
            "mean_rel_return": float(grp["fwd_rel"].mean()) if enough else None,
            "block_se": se if enough and np.isfinite(se) else None,
            "t": (float(bm.mean() / se) if enough and np.isfinite(se) and se > 0 else None),
            "p20_rel_return": float(grp["fwd_rel"].quantile(0.20)) if enough else None,
            "p05_rel_return": float(grp["fwd_rel"].quantile(0.05)) if enough else None,
            "hit_rate": float((grp["fwd_rel"] > 0).mean()) if enough else None,
            "median_rel_return": float(grp["fwd_rel"].median()) if enough else None,
            "why_unmeasured": None if enough else (
                f"{n} rows over {blocks} month-blocks; need >= {MIN_DECILE_ROWS} rows "
                f"and >= {MIN_DECILE_BLOCKS} blocks"),
        })
    ic = _information_coefficient(oos)
    return {"deciles": rows, **ic}


def _information_coefficient(oos: pd.DataFrame) -> dict:
    """Spearman IC per date, then a t across DATES (not across rows)."""
    per_date = (oos.groupby("date")
                .apply(lambda g: g["score"].corr(g["fwd_rel"], method="spearman"),
                       include_groups=False)
                .dropna())
    if per_date.empty:
        return {"ic_mean": None, "ic_t": None, "ic_n_dates": 0, "ic_hit": None}
    se = per_date.std(ddof=1) / math.sqrt(len(per_date))
    return {
        "ic_mean": float(per_date.mean()),
        "ic_std": float(per_date.std(ddof=1)),
        "ic_t": float(per_date.mean() / se) if se > 0 else None,
        "ic_n_dates": int(len(per_date)),
        "ic_hit": float((per_date > 0).mean()),
        "ic_note": ("t is across DATES. Overlapping 21-session windows mean "
                    "consecutive dates are not independent, so this t is "
                    "OPTIMISTIC and is reported as a diagnostic, not a claim."),
    }


def top_k_backtest(oos: pd.DataFrame, *, k: int = 20, cost: bool = True,
                   horizon: int | None = None) -> dict:
    """What an equal-weight top-k book earned OOS, per rebalance date, net.

    This is the economic objective the champion/challenger comparison uses. It
    is NOT annualised and NOT compounded: each date is one independent-ish
    21-session bet, and the mean of those is the honest headline.

    THE T-STATISTIC AND THE OVERLAP (added 2026-09-24, at my own expense)
    --------------------------------------------------------------------
    `t_across_blocks` groups dates by CALENDAR MONTH. At the default horizon
    that is roughly right: a 21-session forward return is about one month, so
    two consecutive monthly blocks barely share an outcome.

    It stops being right the moment the horizon moves. At H=126 every block's
    forward return overlaps the next FIVE blocks almost completely, so 44
    "independent" monthly blocks carry about 7 blocks' worth of information and
    the standard error is understated by ~sqrt(6). Worse, the understatement
    GROWS with the horizon -- so a horizon sweep reading this column sees a t
    that rises with H partly because the estimator flatters long holds, which
    is a confound on the very axis being swept.

    Pass `horizon` and the function also blocks on NON-OVERLAPPING windows of
    `horizon` sessions, where two blocks cannot share a return by construction,
    and reports that t as `t_nonoverlap` beside `n_blocks_nonoverlap`. Read
    that one. The monthly figure stays because every receipt on disk quotes it
    and silently redefining a published number is worse than carrying two.

    The point estimates are untouched either way: overlap inflates PRECISION,
    never the mean.

    THE CORRECTION IS PARTIAL, AND IT IS OPTIMISTIC
    -----------------------------------------------
    Binning `horizon` consecutive rebalance dates does not fully de-overlap the
    blocks. Block i averages return windows starting in [126i, 126i+126), so it
    spans outcomes out to 126i+252; block i+1 spans 126i+126 to 126i+378. They
    share half their span. Zero overlap needs a block width of 2*horizon, which
    on a panel this length leaves THREE blocks -- too few for a standard error
    at all.

    So `t_nonoverlap` remains optimistic by up to sqrt(2), and
    `n_blocks_strict` reports how many truly independent blocks exist. When
    that number is small, the honest conclusion is not "the t is low", it is
    THE PANEL IS TOO SHORT TO TEST THIS HORIZON, which is a different sentence
    and forbids a different set of claims.
    """
    rows = []
    for d, grp in oos.groupby("date"):
        top = grp.nlargest(k, "score")
        if len(top) < k:
            continue
        gross = float(top["fwd_rel"].mean())
        bps = float(np.mean([round_trip_bps(v) for v in top["median_dollar_vol"]]))
        net = gross - (bps / 10_000.0 if cost else 0.0)
        rows.append({"date": str(pd.Timestamp(d).date()), "gross": gross, "net": net,
                     "cost_bps": bps, "n": len(top)})
    if not rows:
        return {"status": "REFUSED", "why": f"no date had {k} eligible ranked names"}
    rows.sort(key=lambda r: r["date"])
    net = np.array([r["net"] for r in rows])
    blocks = pd.Series([r["date"][:7] for r in rows])
    bm = pd.Series(net).groupby(blocks).mean()
    se = float(bm.std(ddof=1) / math.sqrt(len(bm))) if len(bm) > 1 else float("nan")

    # Non-overlapping blocks: one block per `horizon` distinct rebalance dates,
    # so no two blocks can share a forward return. This is the honest error bar
    # whenever the horizon exceeds a month.
    t_no = se_no = None
    n_no = n_strict = None
    if horizon and horizon > 1:
        dates = sorted({r["date"] for r in rows})
        # Rank each date, then bin the ranks in groups of `horizon`. Bins are
        # counted in TRADING DATES because that is what the horizon is measured
        # in; a calendar-width bin would be wrong across holidays.
        rank = {d: i for i, d in enumerate(dates)}
        nb = pd.Series([rank[r["date"]] // horizon for r in rows])
        bmn = pd.Series(net).groupby(nb).mean()
        n_no = int(nb.nunique())
        # How many blocks would exist at a width that CANNOT share a return
        # window (2*horizon). Reported, never used for a t: when it is small the
        # finding is about the panel's length, not about the strategy.
        n_strict = int(pd.Series([rank[r["date"]] // (2 * horizon)
                                  for r in rows]).nunique())
        if len(bmn) > 1:
            s_no = float(bmn.std(ddof=1) / math.sqrt(len(bmn)))
            if np.isfinite(s_no) and s_no > 0:
                se_no, t_no = s_no, float(bmn.mean() / s_no)

    # LEAVE-ONE-YEAR-OUT, computed unconditionally and reported beside the mean.
    #
    # On 2026-09-24 a +2.62%/hold cell survived a purge, a survivorship-free
    # panel, a breadth sweep and a corrected error bar, and died to one
    # `groupby(year).mean()`: dropping 2025 took it to +0.12%. The correction I
    # had spent the afternoon on was real and irrelevant. When a number is
    # positive the first question is not how precise it is, it is WHICH PART OF
    # THE SAMPLE IT IS -- so that question is no longer optional here.
    years = pd.Series([r["date"][:4] for r in rows])
    by_year, loo = {}, {}
    for y in sorted(years.unique()):
        m = (years == y).values
        by_year[y] = {"mean_net": float(net[m].mean()), "n_dates": int(m.sum())}
        if (~m).sum() > 1:
            loo[y] = float(net[~m].mean())
    # The worst leave-one-out mean is the number a reader should quote: it is
    # what the strategy earns if the single best year does not repeat.
    loo_worst = min(loo.values()) if loo else None
    loo_worst_year = min(loo, key=loo.get) if loo else None

    # Concentration by date, for the same reason: 35 rows of 46,361 once carried
    # 81% of a result in this programme.
    total = float(net.sum())
    order = np.argsort(-np.abs(net))
    conc = {}
    if total != 0:
        for frac in (0.01, 0.05, 0.10):
            n_top = max(1, int(len(net) * frac))
            conc[f"top_{int(frac*100)}pct_of_dates"] = float(
                net[order[:n_top]].sum() / total)

    return {
        "k": k,
        "n_dates": len(rows),
        "by_year": by_year,
        "leave_one_year_out": loo,
        "loo_worst_mean_net": loo_worst,
        "loo_worst_dropped_year": loo_worst_year,
        "share_of_total_by_date": conc,
        "n_blocks": int(blocks.nunique()),
        "n_blocks_nonoverlap": n_no,
        # Blocks at 2*horizon width, which truly cannot share an outcome. This
        # is the real independent sample size; `n_blocks_nonoverlap` is ~2x it.
        "n_blocks_strict": n_strict,
        "block_se_nonoverlap": se_no,
        # READ THIS ONE when the horizon is longer than a month. The monthly t
        # below shares outcomes between adjacent blocks and is optimistic.
        "t_nonoverlap": t_no,
        "mean_net_rel_21d": float(net.mean()),
        "mean_gross_rel_21d": float(np.mean([r["gross"] for r in rows])),
        "mean_cost_bps": float(np.mean([r["cost_bps"] for r in rows])),
        "block_se": se if np.isfinite(se) else None,
        "t_across_blocks": float(bm.mean() / se) if np.isfinite(se) and se > 0 else None,
        "hit_rate_dates": float((net > 0).mean()),
        "worst_date": min(rows, key=lambda r: r["net"]),
        "best_date": max(rows, key=lambda r: r["net"]),
        "read_me_first": ("PRODUCT_EXPERIMENT. Net of an empirical round-trip cost "
                          "by liquidity band. One regime, ~1.6 years. NOT an alpha claim."),
    }


# ───────────────────────────── the live ranking ─────────────────────────────

def model_version(features: Iterable[str], params: dict, train_end: Any) -> str:
    payload = json.dumps({"f": sorted(features), "p": params, "train_end": str(train_end)},
                         sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def fit_production(panel: pd.DataFrame, *, features: Iterable[str] = FEATURES,
                   params: dict | None = None) -> tuple[Any, pd.Timestamp]:
    """Fit on every row whose 21-session outcome is already KNOWN.

    The last `HORIZON_SESSIONS` dates have no realised label yet, so they are
    training-ineligible by construction — there is no way to accidentally train
    on them, because `y` is NaN there.
    """
    import lightgbm as lgb
    feats = list(features)
    tr = panel[panel["eligible"] & panel["y"].notna()]
    if len(tr) < MIN_TRAIN_ROWS:
        raise RankerError(f"production fit refused: {len(tr):,} labelled rows "
                          f"< MIN_TRAIN_ROWS {MIN_TRAIN_ROWS:,}")
    model = lgb.LGBMRegressor(**(params or LGB_PARAMS))
    model.fit(tr[feats], tr["y"])
    return model, pd.Timestamp(tr["date"].max())


def rank_asof(panel: pd.DataFrame, model: Any, calib: dict, *,
              asof: Any = None, features: Iterable[str] = FEATURES,
              train_end: Any = None) -> pd.DataFrame:
    """The ranked opportunity set for one date. NEVER returns empty silently."""
    feats = list(features)
    d = pd.Timestamp(asof) if asof is not None else pd.Timestamp(panel["date"].max())
    day = panel[(panel["date"] == d) & panel["eligible"]].copy()
    if day.empty:
        raise RankerError(f"no eligible names on {d.date()} — the panel may be stale "
                          f"(latest date present: {panel['date'].max()})")
    day["score"] = model.predict(day[feats])
    day["rank_21d"] = day["score"].rank(ascending=False, method="first").astype(int)
    day["score_pct"] = day["score"].rank(pct=True, method="average")
    day["decile"] = np.clip((day["score_pct"] * 10).astype(int), 0, 9)

    by_dec = {r["decile"]: r for r in calib["deciles"]}
    day["expected_relative_return_21d"] = day["decile"].map(
        lambda x: by_dec.get(int(x), {}).get("mean_rel_return"))
    day["downside_21d"] = day["decile"].map(
        lambda x: by_dec.get(int(x), {}).get("p20_rel_return"))
    day["tail_21d"] = day["decile"].map(
        lambda x: by_dec.get(int(x), {}).get("p05_rel_return"))
    day["probability_beat_benchmark"] = day["decile"].map(
        lambda x: by_dec.get(int(x), {}).get("hit_rate"))
    day["calibration_measured"] = day["decile"].map(
        lambda x: bool(by_dec.get(int(x), {}).get("measured", False)))
    day["round_trip_bps"] = day["median_dollar_vol"].map(round_trip_bps)
    day["expected_relative_return_21d_net"] = (
        day["expected_relative_return_21d"] - day["round_trip_bps"] / 10_000.0)
    day["liquidity_band"] = day["median_dollar_vol"].map(liquidity_band)
    day["model_version"] = model_version(feats, LGB_PARAMS, train_end)
    day["asof"] = str(d.date())
    day["benchmark"] = BENCHMARK
    day["horizon_sessions"] = HORIZON_SESSIONS
    return day.sort_values("rank_21d").reset_index(drop=True)


def build_panel(bars: pd.DataFrame | None = None, *,
                horizon: int = HORIZON_SESSIONS) -> pd.DataFrame:
    """bars -> features -> eligibility -> target. The one call a caller needs."""
    b = bars if bars is not None else load_bars()
    f = build_features(b)
    f = mark_eligible(f)
    return build_target(f, horizon=horizon)


def why(row: pd.Series, panel_date_stats: dict | None = None) -> list[str]:
    """The specific facts that put this name where it is. A rank with no `why`
    is a bug, not a suggestion (the funnel's own rule, kept)."""
    out = [
        f"rank {int(row['rank_21d'])} of {int(row.get('n_ranked', 0)) or '?'} eligible names "
        f"on {row['asof']}, decile {int(row['decile'])}",
    ]
    er = row.get("expected_relative_return_21d")
    if er is None or (isinstance(er, float) and not np.isfinite(er)):
        out.append("decile NOT calibrated: expected return is unmeasured, so this name "
                   "may be ranked but must not be sized off a number that does not exist")
    else:
        out.append(f"decile {int(row['decile'])} earned {er*100:+.2f}% relative over 21 sessions "
                   f"out of sample (p20 {row['downside_21d']*100:+.2f}%, "
                   f"hit {row['probability_beat_benchmark']*100:.0f}%)")
        out.append(f"net of {row['round_trip_bps']:.0f} bps round trip "
                   f"({row['liquidity_band']} liquidity): "
                   f"{row['expected_relative_return_21d_net']*100:+.2f}%")
    for f_, label in (("mom_252_21", "12-1 momentum"), ("resid_mom_63", "residual 63d momentum"),
                      ("px_vs_52w_high", "vs 52w high"), ("vol_21", "21d vol"),
                      ("turnover_surge", "turnover surge")):
        v = row.get(f_)
        if v is not None and isinstance(v, (int, float)) and np.isfinite(v):
            out.append(f"{label} {v:+.3f}")
    return out
