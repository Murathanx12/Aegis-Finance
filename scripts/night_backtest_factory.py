"""THE NIGHTLY BACKTEST FACTORY -- every library rule, the same way, ranked honestly.

    python -m scripts.night_backtest_factory                 # the full library, tonight
    python -m scripts.night_backtest_factory --resume        # continue a killed run
    python -m scripts.night_backtest_factory --smoke         # 300 symbols, no freezing
    python -m scripts.night_backtest_factory --no-freeze     # backtest only

Spec: `docs/research_notes/2026-09-26/spec_chunk3b_strategy_library_and_backtest_factory.md`.
PRODUCT_EXPERIMENT. CPU only: no LLM, no broker, no network except the one
canonical SPY fetch in `learner.benchmark` (which REFUSES offline, and the
refusal is printed and replaced by a stamped, labelled bars leg -- never
silently).

WHAT ONE NIGHT DOES
===================
1. Builds ONE monthly panel from the survivorship-free bars (living names from
   the deep pull + the delisted pull): month-end decision dates, every feature
   computed from bars at or before the date, SEC fundamentals joined on
   `filed + 2d`, analyst revision flow strictly before the date. The forward
   return of each (date, name) runs from the OPEN of the next session to the
   OPEN of the session after the next month-end; a name whose bars stop inside
   that window is credited its last close x (1 + STRATEGY_LIB_DELIST_RETURN).
2. Runs every rule in `strategy_library.RULES` at k = 10/20/50, net of the band
   round trip on the weight actually traded. A checkpoint every 10 rules; a
   STOP file and a time box end the night between rules with a PARTIAL board.
3. BEFORE ANY RANKING, every row carries: by-year (vs SPY), leave-one-year-out
   worst, the worst breadth cell, the t on horizon-wide blocks, Sharpe with its
   block count, and the deflated Sharpe at the number of cells LOOKED AT (and
   at the number of families, beside it).
4. Writes `leaderboard_<date>T<HHMMSS>Z.json` (the RUN's receipt, never
   overwritten: a second run the same day gets its own run id) and refreshes
   `leaderboard_<date>.json` + `LEADERBOARD.md` as the "latest" copies; the same
   suffix goes on `top10_for_replication_*` and `run_*`. A date-named receipt a
   second run could overwrite is the mtime family of protocol item 7 (review
   2026-09-26 finding 0). `checkpoint_<date>.json` stays date-named: it is crash
   state that `--resume` must find, not a receipt.
5. Freezes a forward twin book (`lib_<id>_<date>`, kind personal, twins ew /
   sector_etf / spy / random_same_band) for every DSR top-10 rule that has no
   forward book yet, plus the forward-only rules the 2026-09-26 audit named,
   and prints the WORST CASE IN DOLLARS for each.
6. Grades every existing `lib_` book and prints the backtest beside the
   forward: "the backtest says +X/month, the forward book says +Y at 21d".

EVERY NUMBER BEFORE 2026-09-26 IS HINDSIGHT. The rules were written down on
that date by people who had seen 2020-2026; "since 2020" is what the rule
WOULD have done, not what Aegis did. The quotable record starts at
registration, and the forward books are where it accrues.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                        # noqa: E402
from backend.services import strategy_library as SL       # noqa: E402
from scripts.night_checkpoint import Checkpoint, atomic_write_json  # noqa: E402

JOB = "B_backtest_factory"


def out_dir() -> Path:
    return Path(_cfg.OPTIMUS_LEDGER_DIR) / _cfg.STRATEGY_LIB_SUBDIR


# ═════════════════════════════════ the panel ════════════════════════════════

_BAR_COLS = ["symbol", "date", "open", "high", "low", "close", "volume"]


def load_wide(paths, *, start: str, max_symbols: int = 0,
              market: str = "SPY") -> dict:
    """Bars -> (dates x symbols) arrays on the MARKET's calendar."""
    frames = [pd.read_parquet(p, columns=_BAR_COLS) for p in paths]
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["symbol", "date"], keep="first")
    df = df[df["date"] >= pd.Timestamp(start)]
    if max_symbols:
        syms = sorted(set(df["symbol"].unique()) - {market})[:max_symbols] + [market]
        df = df[df["symbol"].isin(syms)]
    cal = np.sort(df.loc[df["symbol"] == market, "date"].unique())
    if len(cal) < 300:
        raise SL.RuleInputMissing(
            f"the market proxy {market} has {len(cal)} sessions since {start}; "
            f"the calendar and every beta need it")
    df = df[df["date"].isin(cal)]
    symbols = np.array(sorted(df["symbol"].unique()))
    si = np.searchsorted(symbols, df["symbol"].to_numpy())
    di = np.searchsorted(cal, df["date"].to_numpy())
    T, N = len(cal), len(symbols)
    out = {"dates": pd.DatetimeIndex(cal), "symbols": symbols}
    for c in ("open", "high", "low", "close", "volume"):
        a = np.full((T, N), np.nan, dtype=np.float64)
        a[di, si] = df[c].to_numpy(dtype=np.float64)
        a[~np.isfinite(a) | (a <= 0)] = np.nan if c != "volume" else 0.0
        out[c] = a
    out["n_bar_rows"] = int(len(df))
    return out


def _win(a: np.ndarray, i: int, n: int) -> np.ndarray:
    return a[max(0, i - n + 1): i + 1]


def _count_ok(x: np.ndarray, need: int) -> np.ndarray:
    return np.isfinite(x).sum(axis=0) >= need


def decision_indices(dates: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """Month-end session indices, plus the last session if it is not one."""
    s = pd.Series(np.arange(len(dates)), index=dates)
    me = s.groupby(dates.to_period("M")).max().to_numpy()
    last = len(dates) - 1
    extra = np.array([last]) if me[-1] != last else np.array([], dtype=int)
    return me, extra


def build_panel(W: dict, *, delist_return: float, market: str = "SPY",
                min_index: int = 252) -> pd.DataFrame:
    """The long monthly panel: one row per (decision date, trading symbol)."""
    from backend.services import xs_ranker as XR
    from backend.services import llm_portfolio as LP

    dates, symbols = W["dates"], W["symbols"]
    O, H, L, C, V = W["open"], W["high"], W["low"], W["close"], W["volume"]
    T, N = C.shape
    m_i = int(np.searchsorted(symbols, market))
    Cff = pd.DataFrame(C).ffill().to_numpy()
    R = np.full_like(C, np.nan)
    R[1:] = C[1:] / Cff[:-1] - 1.0
    R[~np.isfinite(C)] = np.nan
    DV = C * V
    seen = np.cumsum(np.isfinite(C), axis=0)
    fin = np.isfinite(C)
    last_valid = np.where(fin.any(axis=0), T - 1 - np.argmax(fin[::-1], axis=0), -1)
    rm_all = R[:, m_i]

    # overnight (prev close -> open) and intraday (open -> close) log returns
    with np.errstate(invalid="ignore", divide="ignore"):
        LO = np.full_like(C, np.nan)
        LO[1:] = np.log(O[1:] / Cff[:-1])
        LI = np.log(C / O)
    LO[~np.isfinite(LO)] = np.nan
    LI[~np.isfinite(LI)] = np.nan
    # market regime, one value per session, trailing data only
    mc = Cff[:, m_i]
    ma200_m = pd.Series(mc).rolling(200, min_periods=150).mean().to_numpy()
    mvol = pd.Series(rm_all).rolling(21, min_periods=15).std().to_numpy()

    me, extra = decision_indices(dates)
    # month-end closes for the seasonality columns (every month, from the start)
    Cme = Cff[me]
    alive_me = np.array([last_valid >= i for i in me])
    Rm = np.full_like(Cme, np.nan)
    Rm[1:] = Cme[1:] / Cme[:-1] - 1.0
    Rm[~alive_me] = np.nan
    Rm[1:][~alive_me[:-1]] = np.nan

    excluded = np.array([(s in XR.INDEX_PROXIES) or LP.is_etf(s) for s in symbols])
    all_dec = list(me) + list(extra)
    frames = []
    for pos, i in enumerate(all_dec):
        if i < min_index:
            continue
        is_me = pos < len(me)
        c = C[i]
        trade = np.isfinite(c)
        if not trade.any():
            continue
        f = {}
        lag = lambda n: Cff[i - n] if i - n >= 0 else np.full(N, np.nan)  # noqa: E731
        f["mom_21"] = Cff[i] / lag(21) - 1.0
        f["mom_63"] = Cff[i] / lag(63) - 1.0
        f["mom_126"] = Cff[i] / lag(126) - 1.0
        f["mom_252"] = Cff[i] / lag(252) - 1.0
        f["mom_252_21"] = lag(21) / lag(252) - 1.0
        f["mom_126_21"] = lag(21) / lag(126) - 1.0
        f["mom_63_21"] = lag(21) / lag(63) - 1.0
        f["mom_252_126"] = lag(126) / lag(252) - 1.0
        f["rev_5"] = Cff[i] / lag(5) - 1.0
        for n, need in ((21, 15), (63, 40), (252, 120)):
            x = _win(R, i, n)
            v = np.nanstd(x, axis=0, ddof=1) * math.sqrt(252)
            f[f"vol_{n}"] = np.where(_count_ok(x, need), v, np.nan)
        f["vol_ratio"] = f["vol_21"] / f["vol_63"]
        dv = _win(DV, i, 63)
        dv = np.where(np.isfinite(_win(C, i, 63)), dv, np.nan)
        mdv = np.where(_count_ok(dv, 40), np.nanmedian(dv, axis=0), np.nan)
        f["median_dollar_vol"] = mdv
        f["dollar_vol_log"] = np.log1p(mdv)
        dv5 = _win(DV, i, 5)
        dv5 = np.where(np.isfinite(_win(C, i, 5)), dv5, np.nan)
        f["turnover_surge"] = np.log1p(np.nanmean(dv5, axis=0) / mdv)
        hwin, lwin = _win(H, i, 252), _win(L, i, 252)
        hi = np.where(_count_ok(hwin, 120), np.nanmax(hwin, axis=0), np.nan)
        lo = np.where(_count_ok(lwin, 120), np.nanmin(lwin, axis=0), np.nan)
        f["px_vs_52w_high"] = c / hi - 1.0
        f["px_vs_52w_low"] = c / lo - 1.0
        c50, c200 = _win(C, i, 50), _win(C, i, 200)
        ma50 = np.where(_count_ok(c50, 30), np.nanmean(c50, axis=0), np.nan)
        ma200 = np.where(_count_ok(c200, 120), np.nanmean(c200, axis=0), np.nan)
        f["px_vs_ma200"] = c / ma200 - 1.0
        f["ma50_vs_ma200"] = ma50 / ma200 - 1.0
        r21 = _win(R, i, 21)
        am = np.abs(r21) / np.where(_win(DV, i, 21) > 0, _win(DV, i, 21), np.nan)
        f["amihud"] = np.where(_count_ok(r21, 15), np.log1p(np.nanmean(am, axis=0) * 1e9), np.nan)
        f["max_ret_21"] = np.where(_count_ok(r21, 15), np.nanmax(r21, axis=0), np.nan)
        c63 = _win(C, i, 63)
        f["max_drawdown_63"] = np.where(_count_ok(c63, 40), c / np.nanmax(c63, axis=0) - 1.0, np.nan)
        r63 = _win(R, i, 63)
        mu, sd = np.nanmean(r63, axis=0), np.nanstd(r63, axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            sk = np.nanmean(((r63 - mu) / sd) ** 3, axis=0)
        f["skew_63"] = np.where(_count_ok(r63, 40) & (sd > 0), sk, np.nan)
        # the 12-1 window of daily returns
        w12 = R[max(0, i - 251): max(0, i - 20)]
        okw = _count_ok(w12, 120)
        pos_ = np.nanmean(np.where(np.isfinite(w12), w12 > 0, np.nan), axis=0)
        neg_ = np.nanmean(np.where(np.isfinite(w12), w12 < 0, np.nan), axis=0)
        f["up_days_12_1"] = np.where(okw, pos_, np.nan)
        f["info_discreteness"] = np.where(okw, np.sign(f["mom_252_21"]) * (neg_ - pos_), np.nan)
        # betas and residuals against the market proxy
        for n, need in ((63, 40), (252, 120)):
            x = _win(R, i, n)
            rm = _win(rm_all, i, n)[:, None]
            ok = np.isfinite(x) & np.isfinite(rm)
            X = np.where(ok, x, np.nan)
            RM = np.where(ok, rm, np.nan)
            xm, rmm = np.nanmean(X, axis=0), np.nanmean(RM, axis=0)
            cov = np.nanmean((X - xm) * (RM - rmm), axis=0)
            var = np.nanmean((RM - rmm) ** 2, axis=0)
            with np.errstate(invalid="ignore", divide="ignore"):
                b = np.where((ok.sum(axis=0) >= need) & (var > 0), cov / var, np.nan)
            f[f"beta_{n}"] = b
            if n == 63:
                f["idio_vol_63"] = np.where(ok.sum(axis=0) >= need,
                                            np.nanstd(X - b * RM, axis=0, ddof=1) * math.sqrt(252),
                                            np.nan)
                mkt63 = Cff[i, m_i] / Cff[i - 63, m_i] - 1.0 if i >= 63 else np.nan
                f["resid_mom_63"] = f["mom_63"] - b * mkt63
        x = R[max(0, i - 251): max(0, i - 20)]
        rm = rm_all[max(0, i - 251): max(0, i - 20)][:, None]
        res = x - f["beta_252"] * rm
        f["resid_mom_12_1"] = np.where(_count_ok(res, 120), np.nansum(res, axis=0), np.nan)
        # seasonality: the month this row EARNS is the next calendar month
        mpos = int(np.searchsorted(me, i, side="right"))   # index of next month in `me`
        lags = [mpos - 12 * L for L in range(1, 6)]
        vals = np.vstack([Rm[m] if 0 <= m < len(me) else np.full(N, np.nan) for m in lags])
        f["seas_same_month"] = np.where(np.isfinite(vals).sum(axis=0) >= 2, np.nanmean(vals, axis=0), np.nan)
        f["seas_lag12"] = vals[0]
        # overnight momentum (Lou-Polk-Skouras) and the gap share of the last month
        lo_w = _win(LO, i, 252)
        f["ovn_252"] = np.where(_count_ok(lo_w, 120), np.nansum(lo_w, axis=0), np.nan)
        lo21, li21 = np.abs(_win(LO, i, 21)), np.abs(_win(LI, i, 21))
        with np.errstate(invalid="ignore", divide="ignore"):
            gs = np.nansum(lo21, axis=0) / (np.nansum(lo21, axis=0) + np.nansum(li21, axis=0))
        f["gap_share_21"] = np.where(_count_ok(lo21, 15), gs, np.nan)
        # market regime (identical on every row of the date)
        up = float(mc[i] > ma200_m[i]) if np.isfinite(ma200_m[i]) else np.nan
        hist = mvol[252:i + 1] if i >= 252 else mvol[:0]
        hist = hist[np.isfinite(hist)]
        if len(hist) >= 60 and np.isfinite(mvol[i]):
            q1, q2 = np.quantile(hist, [1 / 3, 2 / 3])
            stress, calm = float(mvol[i] >= q2), float(mvol[i] <= q1)
        else:
            stress = calm = np.nan
        f["mkt_trend_up"] = np.full(N, up)
        f["mkt_trend_down"] = np.full(N, 1.0 - up if np.isfinite(up) else np.nan)
        f["mkt_stress"] = np.full(N, stress)
        f["mkt_calm"] = np.full(N, calm)
        # eligibility (xs_ranker's floors, trailing data only; ETFs out)
        elig = (trade & (c >= XR.MIN_PRICE) & (c <= XR.MAX_PRICE)
                & (np.nan_to_num(mdv) >= XR.MIN_MEDIAN_DOLLAR_VOL)
                & (seen[i] >= XR.MIN_HISTORY_SESSIONS) & ~excluded
                & np.isfinite(f["vol_63"]) & np.isfinite(f["mom_63"]))
        # forward return to the next month-end's entry
        fwd = np.full(N, np.nan)
        dead = np.zeros(N, dtype=bool)
        if is_me and pos + 1 < len(me):
            e0, e1 = i + 1, me[pos + 1] + 1
            if e1 <= T - 1:
                entry = np.where(np.isfinite(O[e0]), O[e0], c)
                died = last_valid < e1
                ex = np.where(np.isfinite(O[e1]), O[e1], Cff[e1])
                ex = np.where(died, Cff[e1] * (1.0 + delist_return), ex)
                fwd = ex / entry - 1.0
                dead = died & trade
        keep = np.where(trade)[0]
        fr = pd.DataFrame({k: v[keep] for k, v in f.items()})
        fr.insert(0, "symbol", symbols[keep])
        fr.insert(0, "date", dates[i])
        fr["close"] = c[keep]
        fr["eligible"] = elig[keep]
        fr["fwd_ret"] = fwd[keep]
        fr["delisted_in_period"] = dead[keep]
        fr["is_month_end"] = is_me
        frames.append(fr)
    panel = pd.concat(frames, ignore_index=True)
    return panel


def attach_fundamentals(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """SEC facts on `filed + LAG_DAYS`, never on `end`. Refusal is recorded."""
    from backend.services import fundamental_features as FF
    try:
        hist = FF.load_history()
    except FF.FundamentalsMissing as e:
        return panel, {"status": "REFUSED", "why": str(e)}
    wide = FF.wide_by_filing(hist)
    r = FF.ratios(wide)
    w = wide.set_index(["ticker", "filed"])
    rev = w["revenue"] if "revenue" in w else pd.Series(np.nan, index=w.index)
    cogs = w["cogs"] if "cogs" in w else pd.Series(np.nan, index=w.index)
    gm = ((rev - cogs) / rev.where(rev > 0)).rename("gross_margin")
    def _w(c):
        return w[c] if c in w else pd.Series(np.nan, index=w.index)
    extra = pd.DataFrame({"gross_margin": gm, "revenue": rev,
                          "om": _w("operating_income") / rev.where(rev > 0),
                          "roa": _w("net_income") / _w("assets").where(_w("assets") > 0),
                          "ni": _w("net_income"),
                          "dat": _w("debt") / _w("assets").where(_w("assets") > 0)}).reset_index()
    extra = extra.sort_values(["ticker", "filed"])
    g = extra.groupby("ticker")
    prev_rev = g["revenue"].shift(4)
    extra["rev_gr"] = (extra["revenue"] - prev_rev) / prev_rev.where(prev_rev > 0)
    extra["gm_chg"] = extra["gross_margin"] - g["gross_margin"].shift(4)
    extra["inflection"] = extra["rev_gr"] * extra["gm_chg"]
    # chunk D: acceleration, operating margin, ROA, turns, deleveraging (same
    # filing-sequence convention as rev_gr: four filings back ~ one year)
    g = extra.groupby("ticker")
    extra["rev_accel"] = extra["rev_gr"] - g["rev_gr"].shift(4)
    extra["om_chg"] = extra["om"] - g["om"].shift(4)
    extra["roa_chg"] = extra["roa"] - g["roa"].shift(4)
    extra["debt_at_chg"] = extra["dat"] - g["dat"].shift(4)
    pni = g["ni"].shift(4)
    extra["ni_turn"] = ((extra["ni"] > 0) & (pni <= 0)).astype(float).where(pni.notna() & extra["ni"].notna())
    pgm = g["gm_chg"].shift(4)
    extra["gm_turn"] = ((extra["gm_chg"] > 0) & (pgm <= 0)).astype(float).where(pgm.notna() & extra["gm_chg"].notna())
    prg = g["rev_gr"].shift(4)
    extra["rev_turn"] = ((extra["rev_gr"] > 0) & (prg <= 0)).astype(float).where(prg.notna() & extra["rev_gr"].notna())
    new_cols = ["gross_margin", "rev_gr", "gm_chg", "inflection", "rev_accel", "om_chg", "roa_chg",
                "debt_at_chg", "ni_turn", "gm_turn", "rev_turn"]
    feats = r.merge(extra[["ticker", "filed"] + new_cols], on=["ticker", "filed"], how="left")
    feats["available"] = feats["filed"] + pd.Timedelta(days=FF.LAG_DAYS)
    feats = feats.sort_values("available")
    cols = list(FF.FUNDAMENTAL_FEATURES) + new_cols
    left = panel.sort_values("date").reset_index()
    feats["symbol"] = feats["ticker"].astype(str)
    m = pd.merge_asof(left, feats[["symbol", "available", "filed"] + cols],
                      left_on="date", right_on="available", by="symbol",
                      direction="backward", allow_exact_matches=True)
    age = (m["date"] - m["filed"]).dt.days
    m.loc[age > 460, cols] = np.nan
    m = m.set_index("index").sort_index()
    out = panel.copy()
    for c_ in cols:
        out[c_] = m[c_].to_numpy()
    cov = out.loc[out["eligible"] & (out["date"] == out["date"].max()), "gp_at"].notna().mean()
    return out, {"status": "OK", "lag_days": FF.LAG_DAYS, "n_filings": int(len(feats)),
                 "gp_at_coverage_last_date": round(float(cov), 4) if np.isfinite(cov) else None}


def attach_flow(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Analyst revision flow strictly before each date; covered names only."""
    from backend.services import revision_flow as RF
    path = Path(_cfg.OPTIMUS_LEDGER_DIR) / "analyst" / "target_revisions.parquet"
    if not path.exists():
        return panel, {"status": "REFUSED", "why": f"no revision parquet at {path}"}
    rev = pd.read_parquet(path)
    covered = set(rev["ticker"].astype(str).str.upper())
    dates = sorted(panel["date"].unique())
    out = panel.copy()
    key = ["symbol", "date"]
    for win, suffix in ((90, ""), (30, "_30"), (180, "_180")):
        fp = RF.compute_panel(rev, dates, window_days=win).rename(columns={"ticker": "symbol"})
        keep = ["net_raises", "n_firms", "median_target_change", "n_events"] if not suffix \
            else ["net_raises"]
        fp = fp[key + keep].rename(columns={c: c + suffix for c in keep})
        out = out.merge(fp, on=key, how="left")
    cov = out["symbol"].isin(covered)
    for c_ in ("net_raises", "n_firms", "n_events", "net_raises_30", "net_raises_180"):
        out.loc[cov & out[c_].isna(), c_] = 0.0
        out.loc[~cov, c_] = np.nan
    out["flow_rule_score"] = out["net_raises"] * out["n_firms"]
    out["flow_accel"] = out["net_raises_30"] - out["net_raises"] / 3.0
    return out, {"status": "OK", "n_revision_rows": int(len(rev)), "n_covered": len(covered),
                 "windows_days": [90, 30, 180], "strictly_before_decision_date": True}


# ═════════════════════ chunk D: more PIT inputs, each a named refusal ═══════
#
# Every attacher below returns (panel, meta) and NEVER raises for missing or
# malformed data: it returns the panel unchanged with meta status REFUSED, and
# the rules that read its columns are then refused BY NAME in the leaderboard.
# Every event is counted strictly before the decision date (date-level: an
# event stamped on the decision day itself is not used).

def _decision_frame(panel: pd.DataFrame) -> tuple[pd.DatetimeIndex, dict]:
    """The decision dates and, for each, the NEXT decision date (holding-period end)."""
    ds = pd.DatetimeIndex(sorted(panel["date"].unique()))
    me = pd.DatetimeIndex(sorted(panel.loc[panel["is_month_end"], "date"].unique()))
    nxt = {}
    for d in ds:
        later = me[me > d]
        nxt[d] = later[0] if len(later) else d + pd.Timedelta(days=31)
    return ds, nxt


def _merge_feats(panel: pd.DataFrame, rows: list, cols: list, covered: set,
                 zero_fill: list) -> pd.DataFrame:
    """Left-join per-(date, symbol) features; covered names get 0 for counts."""
    feats = (pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date", "symbol"] + cols))
    out = panel.drop(columns=[c for c in cols if c in panel.columns])
    out = out.merge(feats, on=["date", "symbol"], how="left")
    cov = out["symbol"].isin(covered)
    for c in cols:
        if c not in out.columns:
            out[c] = np.nan
        if c in zero_fill:
            out.loc[cov & out[c].isna(), c] = 0.0
            out.loc[~cov, c] = np.nan
    return out


def _cum(a: np.ndarray) -> np.ndarray:
    z = np.zeros((1,) + a.shape[1:])
    return np.concatenate([z, np.cumsum(np.nan_to_num(a), axis=0)], axis=0)


def attach_ratings(panel: pd.DataFrame, W: dict, *, market: str = "SPY") -> tuple[pd.DataFrame, dict]:
    """Rating changes, LEAD vs CHASE raises, analyst skill, first movers, target dispersion.

    From the SAME revision parquet as `attach_flow`, using the columns it does
    not: `action` (up/down/init), `firm`, `current_target`.
    * LEAD raise: the stock's return over the 10 sessions before the event day
      was <= 0. CHASE raise: it was > +1 sigma (63-session daily sd x sqrt 10).
    * Skill: a firm's mean 63-session return vs SPY after its raises, using ONLY
      raises whose 63 sessions had elapsed by the decision date; >= 20 resolved
      raises and a positive mean = skilled.
    * First mover: a raise with no other raise on the name in the prior 30 days.
    * Target CV: std/mean of each firm's latest target in 180 days, >= 3 firms.
    """
    path = Path(_cfg.OPTIMUS_LEDGER_DIR) / "analyst" / "target_revisions.parquet"
    if not path.exists():
        return panel, {"status": "REFUSED", "why": f"no revision parquet at {path}"}
    rev = pd.read_parquet(path, columns=["ticker", "event_date", "firm", "action",
                                         "target_action", "current_target"])
    rev["ticker"] = rev["ticker"].astype(str).str.upper()
    rev["t"] = pd.to_datetime(rev["event_date"], errors="coerce")
    rev = rev[rev["t"].notna()]
    if getattr(rev["t"].dt, "tz", None) is not None:
        rev["t"] = rev["t"].dt.tz_convert(None)
    rev["day"] = rev["t"].dt.normalize()
    covered = set(rev["ticker"])
    dates, symbols = W["dates"], W["symbols"]
    C = W["close"]
    Cff = pd.DataFrame(C).ffill().to_numpy()
    R = np.full_like(C, np.nan)
    R[1:] = C[1:] / Cff[:-1] - 1.0
    S1, S2, SN = _cum(R), _cum(R ** 2), _cum(np.isfinite(R).astype(float))
    m_i = int(np.searchsorted(symbols, market))
    si = np.searchsorted(symbols, rev["ticker"].to_numpy())
    si = np.clip(si, 0, len(symbols) - 1)
    ok_sym = symbols[si] == rev["ticker"].to_numpy()
    i0 = np.searchsorted(dates.values, rev["day"].to_numpy(), side="left") - 1
    T = len(dates)
    ok = ok_sym & (i0 >= 63)
    ta = rev["target_action"].fillna("").str.lower().to_numpy()
    is_raise = ta == "raises"
    is_lower = ta == "lowers"
    ret10 = np.full(len(rev), np.nan)
    sig10 = np.full(len(rev), np.nan)
    exc63 = np.full(len(rev), np.nan)
    res_idx = np.full(len(rev), 10 ** 9)
    ii, ss = i0[ok], si[ok]
    ret10[ok] = Cff[ii, ss] / Cff[ii - 10, ss] - 1.0
    n_ = SN[ii + 1, ss] - SN[ii - 62, ss]
    s1 = S1[ii + 1, ss] - S1[ii - 62, ss]
    s2 = S2[ii + 1, ss] - S2[ii - 62, ss]
    with np.errstate(invalid="ignore", divide="ignore"):
        var = (s2 - s1 ** 2 / n_) / (n_ - 1)
    sig10[ok] = np.where(n_ >= 40, np.sqrt(np.maximum(var, 0)) * math.sqrt(10), np.nan)
    e0, e1 = ii + 1, ii + 64
    fut = e1 < T
    ex = np.full(len(ii), np.nan)
    ex[fut] = ((Cff[e1[fut], ss[fut]] / Cff[e0[fut], ss[fut]])
               - (Cff[e1[fut], m_i] / Cff[e0[fut], m_i]))
    exc63[ok] = ex
    ri = np.full(len(ii), 10 ** 9)
    ri[fut] = e1[fut]
    res_idx[ok] = ri
    rev["lead"] = is_raise & (ret10 <= 0)
    rev["chase"] = is_raise & (ret10 > sig10)
    rev["raise"] = is_raise
    rev["lower"] = is_lower
    rev["exc63"] = exc63
    rev["res_idx"] = res_idx
    rev = rev.sort_values(["ticker", "t"]).reset_index(drop=True)
    rr = rev[rev["raise"]]
    gap = rr.groupby("ticker")["t"].diff()
    rev["first_mover"] = False
    rev.loc[rr.index, "first_mover"] = (gap.isna() | (gap > pd.Timedelta(days=30))).to_numpy()
    rev = rev.sort_values("t").reset_index(drop=True)
    tt = rev["day"].to_numpy()
    didx = {d: i for i, d in enumerate(dates)}
    ds, _nxt = _decision_frame(panel)
    rows = []
    skilled_share: list = []
    for d in ds:
        dv = np.datetime64(d)
        lo90 = np.searchsorted(tt, np.datetime64(d - pd.Timedelta(days=90)), "left")
        lo180 = np.searchsorted(tt, np.datetime64(d - pd.Timedelta(days=180)), "left")
        hi = np.searchsorted(tt, dv, "left")                  # strictly before the day
        w = rev.iloc[lo90:hi]
        if not len(w):
            continue
        di = didx.get(d, 10 ** 9)
        resolved = rev.iloc[:hi]
        resolved = resolved[resolved["raise"] & (resolved["res_idx"] <= di)
                            & resolved["exc63"].notna()]
        sk = resolved.groupby("firm")["exc63"].agg(["mean", "count"])
        skilled = set(sk.index[(sk["count"] >= 20) & (sk["mean"] > 0)])
        wf = w["firm"].isin(skilled)
        g = pd.DataFrame({
            "ticker": w["ticker"],
            "up": (w["action"] == "up").astype(float),
            "down": (w["action"] == "down").astype(float),
            "init": (w["action"] == "init").astype(float),
            "lead": w["lead"].astype(float), "chase": w["chase"].astype(float),
            "fm": (w["first_mover"] & w["raise"]).astype(float),
            "sfm": (w["first_mover"] & w["raise"] & wf).astype(float),
            "skill": ((w["raise"] & wf).astype(float) - (w["lower"] & wf).astype(float)),
            "unskill": ((w["raise"] & ~wf).astype(float) - (w["lower"] & ~wf).astype(float)),
        }).groupby("ticker").sum()
        active = set(w["firm"].dropna())
        skilled_share.append(len(active & skilled) / len(active) if active else np.nan)
        w180 = rev.iloc[lo180:hi]
        w180 = w180[w180["current_target"] > 0]
        last = w180.drop_duplicates(["ticker", "firm"], keep="last")
        cvg = last.groupby("ticker")["current_target"].agg(["std", "mean", "count"])
        cv = (cvg["std"] / cvg["mean"]).where(cvg["count"] >= 3)
        g = g.join(cv.rename("cv"), how="outer")
        for tk, r_ in g.iterrows():
            rows.append({"date": d, "symbol": tk,
                         "rating_net_90": r_["up"] - r_["down"] if np.isfinite(r_["up"]) else np.nan,
                         "rating_downgrades_90": r_["down"], "initiations_90": r_["init"],
                         "lead_raises_90": r_["lead"], "chase_raises_90": r_["chase"],
                         "lead_minus_chase_90": r_["lead"] - r_["chase"],
                         "first_mover_raises_90": r_["fm"], "skill_net_raises_90": r_["skill"],
                         "unskilled_net_raises_90": r_["unskill"],
                         "skill_first_mover_90": r_["sfm"],
                         "target_cv_180": r_["cv"]})
    cols = ["rating_net_90", "rating_downgrades_90", "initiations_90", "lead_raises_90",
            "chase_raises_90", "lead_minus_chase_90", "first_mover_raises_90",
            "skill_net_raises_90", "unskilled_net_raises_90", "skill_first_mover_90",
            "target_cv_180"]
    out = _merge_feats(panel, rows, cols, covered, zero_fill=cols[:-1])
    n_r = int(is_raise.sum())
    ss = np.array([x for x in skilled_share if np.isfinite(x)])
    return out, {"status": "OK", "n_events": int(len(rev)), "n_raises": n_r,
                 "lead_share_of_raises": round(float(rev["lead"].sum()) / max(n_r, 1), 4),
                 "chase_share_of_raises": round(float(rev["chase"].sum()) / max(n_r, 1), 4),
                 "strictly_before_decision_date": True,
                 "skill_rule": ">= 20 resolved raises, mean 63-session excess vs SPY > 0, "
                               "resolved before the decision date",
                 # review 2026-09-26 Q5: if most active firms are 'skilled', skill ~ all raises
                 "skilled_share_of_active_firms": (
                     {"median": float(np.median(ss)), "min": float(ss.min()), "max": float(ss.max()),
                      "share_of_dates_above_0_70": float((ss > 0.7).mean()), "n_dates": int(len(ss))}
                     if len(ss) else None)}


def attach_insider(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Form 4 open-market buys/sells by distinct insider, observed before the date."""
    path = Path(_cfg.OPTIMUS_LEDGER_DIR) / "sec_insider" / "insider_events_v1.parquet"
    if not path.exists():
        return panel, {"status": "REFUSED", "why": f"no insider events at {path}"}
    start = pd.Timestamp(panel["date"].min()) - pd.Timedelta(days=200)
    ev = pd.read_parquet(path, columns=["symbol", "event_type", "observed_at_utc", "insider_cik",
                                        "insider_is_officer", "insider_dollar_value"],
                         filters=[("observed_at_utc", ">=", start.tz_localize("UTC"))])
    ev = ev[ev["symbol"].notna()]
    ev["symbol"] = ev["symbol"].astype(str).str.upper()
    ev["t"] = ev["observed_at_utc"].dt.tz_convert(None)
    ev = ev.sort_values("t").reset_index(drop=True)
    covered = set(ev["symbol"])
    tt = ev["t"].to_numpy()
    ds, _ = _decision_frame(panel)
    rows = []
    BUY, SELL, OPP = "insider_open_market_buy", "insider_open_market_sell", "insider_opportunistic_buy"
    for d in ds:
        hi = np.searchsorted(tt, np.datetime64(d), "left")     # observed before the day starts
        lo90 = np.searchsorted(tt, np.datetime64(d - pd.Timedelta(days=90)), "left")
        lo180 = np.searchsorted(tt, np.datetime64(d - pd.Timedelta(days=180)), "left")
        w9, w18 = ev.iloc[lo90:hi], ev.iloc[lo180:hi]
        if not len(w18):
            continue

        def nun(w, mask):
            x = w[mask][["symbol", "insider_cik"]].drop_duplicates()
            return x.groupby("symbol").size()
        b9 = w9["event_type"] == BUY
        f = pd.DataFrame({
            "b90": nun(w9, b9), "s90": nun(w9, w9["event_type"] == SELL),
            "o90": nun(w9, b9 & w9["insider_is_officer"].astype(bool)),
            "v90": w9[b9].groupby("symbol")["insider_dollar_value"].sum(),
            "b180": nun(w18, w18["event_type"] == BUY), "s180": nun(w18, w18["event_type"] == SELL),
            "p180": nun(w18, w18["event_type"] == OPP)}).fillna(0.0)
        for s_, r_ in f.iterrows():
            tot = r_["b180"] + r_["s180"]
            rows.append({"date": d, "symbol": s_, "ins_buyers_90": r_["b90"],
                         "ins_sellers_90": r_["s90"], "ins_officer_buyers_90": r_["o90"],
                         "ins_buy_value_90": r_["v90"], "ins_opp_buyers_180": r_["p180"],
                         "ins_net_ratio_180": (r_["b180"] - r_["s180"]) / tot if tot > 0 else np.nan})
    cols = ["ins_buyers_90", "ins_sellers_90", "ins_officer_buyers_90", "ins_buy_value_90",
            "ins_opp_buyers_180", "ins_net_ratio_180"]
    out = _merge_feats(panel, rows, cols, covered, zero_fill=cols[:-1])
    out["ins_buy_value_dv_90"] = out["ins_buy_value_90"] / out["median_dollar_vol"]
    return out, {"status": "OK", "n_events": int(len(ev)), "n_symbols": len(covered),
                 "last_observed": str(ev["t"].max()) if len(ev) else None,
                 "pit": "observed_at_utc (filing date EOD, conservative) strictly before the decision day",
                 "caveat": "the file ends at its last observed date; windows after it undercount"}


_DISTRESS_ITEMS = ("1.03", "2.04", "3.01", "4.02")


def attach_8k(panel: pd.DataFrame, W: dict, *, market: str = "SPY") -> tuple[pd.DataFrame, dict]:
    """8-K item counts, the 2.02 earnings calendar, and the announcement return."""
    path = Path(_cfg.OPTIMUS_LEDGER_DIR) / "edgar_8k" / "eightk_items.parquet"
    if not path.exists():
        return panel, {"status": "REFUSED", "why": f"no 8-K items at {path}"}
    ek = pd.read_parquet(path, columns=["ticker", "acceptance_datetime", "filing_date", "items_joined"])
    ek = ek[ek["ticker"].notna()]
    ek["ticker"] = ek["ticker"].astype(str).str.upper()
    acc = pd.to_datetime(ek["acceptance_datetime"], errors="coerce", utc=True)
    fd = pd.to_datetime(ek["filing_date"], errors="coerce")
    et = acc.dt.tz_convert("America/New_York")
    ek["day"] = et.dt.tz_localize(None).dt.normalize().fillna(fd)
    ek["after_close"] = (et.dt.hour >= 16).fillna(True).to_numpy()
    ek = ek[ek["day"].notna()]
    it = ek["items_joined"].fillna("").astype(str)
    ek["i202"] = it.str.contains("2.02", regex=False)
    ek["i101"] = it.str.contains("1.01", regex=False)
    ek["i502"] = it.str.contains("5.02", regex=False)
    ek["i701"] = it.str.contains("7.01", regex=False)
    ek["dist"] = np.logical_or.reduce([it.str.contains(x, regex=False) for x in _DISTRESS_ITEMS])
    ek = ek.sort_values("day").reset_index(drop=True)
    covered = set(ek["ticker"])
    dates, symbols = W["dates"], W["symbols"]
    Cff = pd.DataFrame(W["close"]).ffill().to_numpy()
    m_i = int(np.searchsorted(symbols, market))
    # earnings: the reaction session e (the day itself, or the next if filed after the close)
    er = ek[ek["i202"]].copy()
    si = np.clip(np.searchsorted(symbols, er["ticker"].to_numpy()), 0, len(symbols) - 1)
    oks = symbols[si] == er["ticker"].to_numpy()
    e = np.searchsorted(dates.values, er["day"].to_numpy(), "left")
    e = e + (er["after_close"].to_numpy() & (e < len(dates))
             & (dates.values[np.clip(e, 0, len(dates) - 1)] == er["day"].to_numpy())).astype(int)
    T = len(dates)
    good = oks & (e >= 1) & (e + 1 < T)
    ear = np.full(len(er), np.nan)
    a, b, s_ = e[good] - 1, e[good] + 1, si[good]
    ear[good] = (Cff[b, s_] / Cff[a, s_] - 1.0) - (Cff[b, m_i] / Cff[a, m_i] - 1.0)
    er["ear"] = ear
    er["known_idx"] = np.where(good, e + 1, 10 ** 9)
    er = er.sort_values("day").reset_index(drop=True)
    tt = ek["day"].to_numpy()
    et_ = er["day"].to_numpy()
    didx = {d: i for i, d in enumerate(dates)}
    ds, nxt = _decision_frame(panel)
    rows = []
    for d in ds:
        hi = np.searchsorted(tt, np.datetime64(d), "left")
        w90 = ek.iloc[np.searchsorted(tt, np.datetime64(d - pd.Timedelta(days=90)), "left"):hi]
        w180 = ek.iloc[np.searchsorted(tt, np.datetime64(d - pd.Timedelta(days=180)), "left"):hi]
        w365 = ek.iloc[np.searchsorted(tt, np.datetime64(d - pd.Timedelta(days=365)), "left"):hi]
        f = pd.DataFrame({"n8k": w90.groupby("ticker").size(),
                          "n101": w90[w90["i101"]].groupby("ticker").size(),
                          "n701": w90[w90["i701"]].groupby("ticker").size(),
                          "n502": w180[w180["i502"]].groupby("ticker").size(),
                          "dist": w365[w365["dist"]].groupby("ticker").size()})
        di = didx.get(d, -1)
        ehi = np.searchsorted(et_, np.datetime64(d), "left")
        past = er.iloc[:ehi]
        lastp = past.drop_duplicates("ticker", keep="last").set_index("ticker")
        known = past[past["known_idx"] <= di]
        lastk = known.drop_duplicates("ticker", keep="last").set_index("ticker")
        age = (d - lastk["day"]).dt.days
        f = f.join(pd.DataFrame({"ear": lastk["ear"].where(age <= 100),
                                 "age": age.where(age <= 100)}), how="outer")
        dn = nxt[d]
        # expected next print: a year-ago 2.02 shifted 364d, or the last 2.02 + 91d
        y0 = np.searchsorted(et_, np.datetime64(d - pd.Timedelta(days=364)), "right")
        y1 = np.searchsorted(et_, np.datetime64(dn - pd.Timedelta(days=364)), "right")
        y2 = np.searchsorted(et_, np.datetime64(dn + pd.Timedelta(days=21) - pd.Timedelta(days=364)), "right")
        nxt_set = set(er["ticker"].iloc[y0:y1])
        fol_set = set(er["ticker"].iloc[y1:y2])
        q = lastp["day"] + pd.Timedelta(days=91)
        nxt_set |= set(q.index[(q > d) & (q <= dn)])
        fol_set |= set(q.index[(q > dn) & (q <= dn + pd.Timedelta(days=21))])
        fol_set -= nxt_set
        idx = set(f.index) | nxt_set | fol_set
        f = f.reindex(sorted(idx))
        f["earn_next"] = [1.0 if t_ in nxt_set else 0.0 for t_ in f.index]
        f["earn_following"] = [1.0 if t_ in fol_set else 0.0 for t_ in f.index]
        for tk, r_ in f.iterrows():
            rows.append({"date": d, "symbol": tk, "n8k_90": r_["n8k"], "n101_90": r_["n101"],
                         "n701_90": r_["n701"], "n502_180": r_["n502"], "distress_365": r_["dist"],
                         "ear_last": r_["ear"], "days_since_earn": r_["age"],
                         "earn_next": r_["earn_next"], "earn_following": r_["earn_following"]})
    cols = ["n8k_90", "n101_90", "n701_90", "n502_180", "distress_365", "ear_last",
            "days_since_earn", "earn_next", "earn_following"]
    zero = ["n8k_90", "n101_90", "n701_90", "n502_180", "distress_365", "earn_next", "earn_following"]
    out = _merge_feats(panel, rows, cols, covered, zero_fill=zero)
    return out, {"status": "OK", "n_filings": int(len(ek)), "n_202": int(len(er)),
                 "n_202_priced": int(np.isfinite(ear).sum()), "n_tickers": len(covered),
                 "pit": ("counts: acceptance day strictly before the decision day; the 3-day "
                         "announcement return is used only once its last session has closed"),
                 "expected_print_rule": "2.02 filed 364d earlier, or the last 2.02 + 91d"}


def attach_short_interest(panel: pd.DataFrame, *, lag_days: int = 26) -> tuple[pd.DataFrame, dict]:
    """Days-to-cover and the 3-month change in short interest, published-date PIT."""
    base = Path(_cfg.OPTIMUS_LEDGER_DIR) / "wrds" / "bulk"
    p_si, p_sec = base / "comp__sec_shortint.parquet", base / "comp__security.parquet"
    if not (p_si.exists() and p_sec.exists()):
        return panel, {"status": "REFUSED", "why": f"no Compustat short interest at {base}"}
    start = pd.Timestamp(panel["date"].min()) - pd.Timedelta(days=200)
    si = pd.read_parquet(p_si, columns=["gvkey", "iid", "shortintadj", "datadate"])
    si = si[(si["iid"] == "01") & si["shortintadj"].notna()]
    si["datadate"] = pd.to_datetime(si["datadate"])
    si = si[si["datadate"] >= start]
    sec = pd.read_parquet(p_sec, columns=["gvkey", "iid", "tic", "excntry"])
    sec = sec[(sec["iid"] == "01") & (sec["excntry"] == "USA") & sec["tic"].notna()]
    sec = sec[~sec["tic"].astype(str).str.contains(r"[.\s]", regex=True)]
    lastd = si.groupby("gvkey")["datadate"].max().rename("lastd")
    sec = sec.merge(lastd, left_on="gvkey", right_index=True, how="inner")
    sec = sec.sort_values("lastd").drop_duplicates("tic", keep="last")
    si = si.merge(sec[["gvkey", "tic"]], on="gvkey", how="inner")
    si["available"] = si["datadate"] + pd.Timedelta(days=lag_days)
    si = si.rename(columns={"tic": "symbol"})[["symbol", "available", "shortintadj"]]
    si = si.sort_values("available")
    covered = set(si["symbol"])
    left = panel[["date", "symbol"]].reset_index()
    now = pd.merge_asof(left.sort_values("date"), si, left_on="date", right_on="available",
                        by="symbol", direction="backward")
    left2 = left.copy()
    left2["d3"] = left2["date"] - pd.Timedelta(days=91)
    prev = pd.merge_asof(left2.sort_values("d3"), si, left_on="d3", right_on="available",
                         by="symbol", direction="backward")
    now = now.set_index("index").sort_index()
    prev = prev.set_index("index").sort_index()
    out = panel.copy()
    stale = (out["date"] - now["available"]).dt.days > 60
    s_now = now["shortintadj"].where(~stale)
    shares_day = out["median_dollar_vol"] / out["close"]
    out["dtc"] = (s_now / shares_day.where(shares_day > 0)).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out["si_chg_3m"] = np.log((s_now + 1.0) / (prev["shortintadj"] + 1.0)).to_numpy()
    return out, {"status": "OK", "n_prints": int(len(si)), "n_symbols": len(covered),
                 "publication_lag_days": lag_days, "last_available": str(si["available"].max()),
                 "basis": ("shortintadj (split-adjusted) over split-adjusted bar volume: both on "
                           "the current share basis, so the ratio carries no split look-ahead"),
                 "caveat": "gvkey->symbol by CURRENT Compustat ticker; dead issuers mostly absent"}


def attach_sector(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Static GICS sector per symbol (Compustat), and the sector's mean 12-1 momentum."""
    base = Path(_cfg.OPTIMUS_LEDGER_DIR) / "wrds" / "bulk"
    p_co, p_sec = base / "comp__company.parquet", base / "comp__security.parquet"
    if not (p_co.exists() and p_sec.exists()):
        return panel, {"status": "REFUSED", "why": f"no Compustat company/security at {base}"}
    co = pd.read_parquet(p_co, columns=["gvkey", "gsector"])
    sec = pd.read_parquet(p_sec, columns=["gvkey", "iid", "tic", "excntry", "secstat"])
    sec = sec[(sec["iid"] == "01") & (sec["excntry"] == "USA") & sec["tic"].notna()]
    sec = sec[~sec["tic"].astype(str).str.contains(r"[.\s]", regex=True)]
    m = sec.merge(co, on="gvkey").dropna(subset=["gsector"])
    m = m.sort_values("secstat").drop_duplicates("tic", keep="first")     # 'A'ctive before 'I'
    mp = dict(zip(m["tic"].astype(str), m["gsector"].astype(str)))
    out = panel.copy()
    out["gsector"] = out["symbol"].map(mp)
    el = out["eligible"] & out["gsector"].notna()
    sm = out[el].groupby(["date", "gsector"]).agg(sector_mom=("mom_252_21", "mean"),
                                                  sector_ret_21=("mom_21", "mean"))
    out = out.drop(columns=[c for c in ("sector_mom", "sector_ret_21") if c in out.columns])
    out = out.merge(sm.reset_index(), on=["date", "gsector"], how="left")
    out["mom_minus_sector"] = out["mom_252_21"] - out["sector_mom"]
    cov = out.loc[out["eligible"] & (out["date"] == out["date"].max()), "gsector"].notna().mean()
    return out, {"status": "OK", "n_mapped_tickers": len(mp),
                 "eligible_coverage_last_date": round(float(cov), 4),
                 "caveat": "CURRENT classification applied to every past month (static map)"}


def attach_extension(panel: pd.DataFrame, W: dict) -> tuple[pd.DataFrame, dict]:
    """The sibling module's columns (`strategy_library_ext.attach`), if it has any."""
    if not SL.EXTRA_SOURCE.startswith("backend.services.strategy_library_ext"):
        return panel, {"status": "ABSENT", "why": SL.EXTRA_SOURCE}
    import importlib
    ext = importlib.import_module("backend.services.strategy_library_ext")
    fn = getattr(ext, "attach", None) or getattr(ext, "attach_panel", None)
    if fn is None:
        return panel, {"status": "NO_ATTACH", "why": ("strategy_library_ext has no attach(panel, W); "
                                                      "its rules are refused for missing columns")}
    try:
        res = fn(panel, W)
    except Exception as e:                            # noqa: BLE001 -- named in the receipt
        return panel, {"status": "REFUSED", "why": f"{type(e).__name__}: {e}"}
    if isinstance(res, tuple):
        return res[0], {"status": "OK", **(res[1] if len(res) > 1 and isinstance(res[1], dict) else {})}
    return res, {"status": "OK"}


# ═════════════════════════════════ the market leg ═══════════════════════════

def spy_leg(panel: pd.DataFrame, W: dict | None = None, *, market: str = "SPY",
            network: bool = True) -> tuple[pd.Series, dict]:
    """SPY over each decision period, via `learner.benchmark` (the one ruler).

    Canonical `spy_tr_yf_adjclose` when the network answers; otherwise the
    refusal is RECORDED and the leg is built from the same bars (vendor
    adjustment = split + dividend, so a total return) through
    `benchmark.matched`, open-to-open on the strategy's own entry sessions.
    Either way the stamp says which.
    """
    from learner import benchmark as bm
    dates = pd.DatetimeIndex(sorted(panel.loc[panel["is_month_end"], "date"].unique()))
    refusal = None
    if network:
        try:
            b = bm.spy_total_return(str((dates.min() - pd.Timedelta(days=10)).date()), None)
            r = b.returns.copy()
            r.index = pd.DatetimeIndex(r.index).tz_localize(None) if getattr(
                r.index, "tz", None) else pd.DatetimeIndex(r.index)
            vals = {}
            for a, z in zip(dates[:-1], dates[1:]):
                seg = r[(r.index > a) & (r.index <= z)]
                vals[a] = float(np.prod(1.0 + seg.to_numpy()) - 1.0) if len(seg) else np.nan
            s = pd.Series(vals, dtype=float)
            return s, {"source": "spy_tr_yf_adjclose", "market_benchmark": b.stamp(),
                       "alignment": "daily total return compounded over (month-end, next month-end]"}
        except bm.BenchmarkUnavailable as e:
            refusal = str(e)
    if W is None:
        raise bm.BenchmarkUnavailable("spy_tr_yf_adjclose", "network AND the bars fallback",
                                      refusal or "network disabled and no bars given")
    cal, O, C = W["dates"], W["open"], W["close"]
    m_i = int(np.searchsorted(W["symbols"], market))
    idx = {d: i for i, d in enumerate(cal)}
    vals = {}
    for a, z in zip(dates[:-1], dates[1:]):
        e0, e1 = idx[a] + 1, idx[z] + 1
        if e1 < len(cal):
            p0 = O[e0, m_i] if np.isfinite(O[e0, m_i]) else C[e0 - 1, m_i]
            p1 = O[e1, m_i] if np.isfinite(O[e1, m_i]) else C[e1 - 1, m_i]
            vals[a] = float(p1 / p0 - 1.0)
    s = pd.Series(vals, dtype=float)
    b = bm.matched(s, "spy_bars_entry_aligned", construction=(
        "SPY from the survivorship-free bars (vendor adjustment = split + dividend, "
        "so a total return), open of the session after each month-end to the open "
        "of the session after the next -- the strategy's own entry sessions"), freq="M",
        canonical_refused=refusal)
    return s, {"source": "matched:spy_bars_entry_aligned", "canonical_refusal": refusal,
               "market_benchmark": b.stamp()}


# ═════════════════════════════════ the factory ══════════════════════════════

def panel_fingerprint(panel: pd.DataFrame) -> str:
    body = [len(panel), str(panel["date"].min()), str(panel["date"].max()),
            int(panel["symbol"].nunique()), round(float(np.nansum(panel["fwd_ret"].to_numpy())), 6),
            sorted(panel.columns.tolist())]
    return hashlib.sha256(json.dumps(body, default=str).encode()).hexdigest()[:16]


def _breadth(rule) -> list[int]:
    return sorted(set(SL.BREADTH_K) | {int(rule.k)})



def _value_aware_run(panel, rule, *, k, scores):
    """`strategy_library_ext.run_value_rule` for the VAL-01 value rules, else
    `strategy_library.run_strategy`. The receipt of a refused period lives in
    `m.attrs["eligibility"]`; a missing ext module falls back to the base runner
    and says nothing -- the base runner's own receipt still prints."""
    try:
        from backend.services import strategy_library_ext as EXT
        value_ids = {r.id for r in getattr(EXT, "VALUE_UNLOCK_STRATEGIES", [])}
    except Exception:                                            # noqa: BLE001
        value_ids = set()
    if rule.id in value_ids:
        from backend.services import strategy_library_ext as EXT
        return EXT.run_value_rule(panel, rule, k=k, scores=scores)
    return SL.run_strategy(panel, rule, k=k, scores=scores)

def evaluate_rule(panel: pd.DataFrame, spy: pd.Series, rule, *, since: str) -> dict:
    """All breadth cells of one rule; a missing input is a named REFUSAL."""
    if getattr(rule, "forward_only", False):
        return {"id": rule.id, "status": "REFUSED", "meta": rule.meta(),
                "why": "FORWARD_ONLY: its input has no history on this panel; it accrues forward"}
    try:
        sc = SL.selection_scores(panel, rule)
    except SL.RuleInputMissing as e:
        return {"id": rule.id, "status": "REFUSED", "why": str(e), "meta": rule.meta()}
    cells = {}
    for k in _breadth(rule):
        # VAL-01 review (2026-09-27): a value rule whose decision date cannot
        # fill k names must REFUSE that period, not carry a stale book at the
        # last computable weights (the value rows kept returning non-cash
        # months after 2026-04-06, where market value is NaN).
        m = _value_aware_run(panel, rule, k=k, scores=sc)
        ev = SL.evaluate(m, spy, hold_months=rule.hold_months,
                         registered_utc=rule.first_registered_utc, since=since)
        cells[str(k)] = ev
    ok = {k: c for k, c in cells.items() if c.get("status") == "OK"}
    if not ok:
        return {"id": rule.id, "status": "REFUSED",
                "why": "no breadth cell had k selectable names on any date",
                "meta": rule.meta(), "cells": cells}

    def _c20(c):
        return (c.get("hindsight_since_2020") or {}).get("cagr_net")
    worst_k = min(ok, key=lambda k: (_c20(ok[k]) if _c20(ok[k]) is not None else 9e9))
    return {"id": rule.id, "status": "OK", "meta": rule.meta(), "cells": cells,
            "primary_k": str(rule.k),
            "worst_cell": {"k": int(worst_k), "cagr_since_2020": _c20(ok[worst_k]),
                           "mean_active_monthly": ok[worst_k].get("mean_active_monthly")}}


def _row(res: dict) -> dict:
    """The leaderboard row: the primary cell, honest columns first."""
    c = res["cells"].get(res["primary_k"]) or {}
    h = c.get("hindsight_since_2020") or {}
    meta = res["meta"]
    return {
        "id": res["id"], "family": meta["family"], "k": int(res["primary_k"]),
        "hold_months": meta["hold_months"], "universe": meta["universe_rule"],
        "source": meta["source"], "control": meta["control"],
        "first_registered_utc": meta["first_registered_utc"],
        "economic_reason": meta.get("economic_reason"),
        # THE OBJECTIVE: sealed net return vs SPY (split declared in code)
        "sealed_vs_spy": c.get("sealed_vs_spy"),
        "sealed_cagr": c.get("sealed_cagr"),
        "sealed_spy_cagr": c.get("sealed_spy_cagr"),
        "n_sealed_months": c.get("n_sealed_months"),
        "sealed_dsr": c.get("sealed_dsr"), "sealed_dsr_z": c.get("sealed_dsr_z"),
        "sealed_max_dd": (c.get("sealed_window") or {}).get("max_dd"),
        "dev_cagr": c.get("dev_cagr"), "dev_spy_cagr": c.get("dev_spy_cagr"),
        "dev_vs_spy": c.get("dev_vs_spy"),
        "n_dev_months": (c.get("dev_window") or {}).get("n_months"),
        "recent_126_return": c.get("recent_126_return"),
        "recent_126_spy": c.get("recent_126_spy"),
        "recent_126_vs_spy": c.get("recent_126_vs_spy"),
        "turnover_annual": c.get("turnover_annual"),
        "cost_bps_paid": c.get("cost_bps_paid"),
        "max_dd": c.get("max_dd"),
        # honest columns, BEFORE any headline
        "by_year_signs": c.get("by_year_signs"),
        "positive_excess_years_2020_2025": c.get("positive_excess_years_2020_2025"),
        "loo_worst_mean_active": c.get("loo_worst_mean_active"),
        "loo_worst_dropped_year": c.get("loo_worst_dropped_year"),
        "worst_cell": res.get("worst_cell"),
        "top5_months_share_of_log_return": c.get("top5_months_share_of_log_return"),
        "cagr_without_best_5_months": c.get("cagr_without_best_5_months"),
        "spy_cagr_same_window": c.get("spy_cagr_same_window"),
        "t_active_horizon_blocks": c.get("t_active_horizon_blocks"),
        "n_blocks_horizon": c.get("n_blocks_horizon"),
        "clears_hlz_t3": c.get("clears_hlz_t3"),
        "sharpe_annual": c.get("sharpe_annual"),
        "n_date_blocks": c.get("n_date_blocks"),
        "information_ratio_annual": c.get("information_ratio_annual"),
        "mean_active_monthly": c.get("mean_active_monthly"),
        "dsr": c.get("dsr"), "dsr_n_trials": c.get("dsr_n_trials"),
        "dsr_z": c.get("dsr_z"),
        "dsr_null_from_library": c.get("dsr_null_from_library"),
        "dsr_effective": c.get("dsr_effective"),
        "dsr_effective_n_trials": c.get("dsr_effective_n_trials"),
        # the headline, labelled
        "hindsight_cagr_since_2020": h.get("cagr_net"),
        "hindsight_spy_cagr_since_2020": h.get("cagr_spy"),
        "hindsight_cum_since_2020": h.get("cum_net"),
        "hindsight_spy_cum_since_2020": h.get("cum_spy"),
        "max_dd_since_2020": h.get("max_dd_net"),
        "mean_turnover_per_rebalance": c.get("mean_turnover_per_rebalance"),
        "mean_cost_bps_per_month": c.get("mean_cost_bps_per_month"),
        "n_delisting_fills": c.get("n_delisting_fills"),
        "quotable_since_registration": c.get("quotable_since_registration"),
        "by_year": c.get("by_year"),
        "literature_reported": meta.get("literature_reported"),
        "caveat": meta.get("caveat"),
    }


def _round(o, nd: int = 6):
    if isinstance(o, float):
        return round(o, nd) if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _round(v, nd) for k, v in o.items()}
    if isinstance(o, list):
        return [_round(v, nd) for v in o]
    return o


def run_factory(panel: pd.DataFrame, spy: pd.Series, spy_meta: dict, *,
                today: date, rules: list | None = None, out: Path | None = None,
                resume: bool = False, time_box_s: float | None = None,
                stop_after: int | None = None, since: str | None = None,
                checkpoint_every: int | None = None, log=print) -> dict:
    """Evaluate every rule, checkpointing; return the leaderboard dict.

    `stop_after` ends the loop after that many NEW rules as a clean stop (the
    checkpoint is flushed first) -- the STOP file and the time box take the
    same path. A crash between checkpoints loses at most `checkpoint_every`.
    """
    rules = list(rules if rules is not None else SL.rules())
    out = Path(out or out_dir())
    out.mkdir(parents=True, exist_ok=True)
    since = since or _cfg.STRATEGY_LIB_SINCE
    every = int(checkpoint_every or _cfg.STRATEGY_LIB_CHECKPOINT_EVERY)
    config = {"job": JOB, "date": str(today), "library": SL.library_fingerprint(rules),
              "panel": panel_fingerprint(panel), "breadth": list(SL.BREADTH_K),
              "since": since, "spy_source": spy_meta.get("source")}
    ck = Checkpoint(out / f"checkpoint_{today}.json", config)
    done: dict = {}
    if resume and ck.exists():
        done = dict(ck.load().get("done") or {})
        log(f"RESUME: {len(done)} rule(s) already on the checkpoint; not recomputing them")
    t0 = time.time()
    n_new = 0
    stopped_why = None
    stop_file = out / "STOP"
    for rule in rules:
        if rule.id in done:
            continue
        if stop_file.exists():
            stopped_why = f"STOP file present ({stop_file})"
            break
        if time_box_s is not None and time.time() - t0 > time_box_s:
            stopped_why = f"time box {time_box_s/60:.0f} min reached"
            break
        if stop_after is not None and n_new >= stop_after:
            stopped_why = f"stop_after={stop_after}"
            break
        done[rule.id] = _round(evaluate_rule(panel, spy, rule, since=since))
        n_new += 1
        if n_new % every == 0:
            ck.save({"done": done})
            log(f"  checkpoint: {len(done)}/{len(rules)} rules ({time.time()-t0:.0f}s)")
    ck.save({"done": done})
    board = leaderboard(done, rules, spy_meta=spy_meta, today=today,
                        partial=stopped_why, since=since)
    board["n_computed_this_run"] = n_new
    return board


def sealed_sort_key(x: dict) -> tuple:
    """THE primary sort: sealed net return vs SPY; sealed DSR z breaks ties."""
    v = x.get("sealed_vs_spy")
    z = x.get("sealed_dsr_z")
    return (v if v is not None else -9.0, z if z is not None else -99.0)


def _sr0(n: int, T: int) -> float | None:
    """Expected max monthly Sharpe of n pure-noise cells over T months (analytic null)."""
    if n < 2 or T < 3:
        return None
    from scipy.stats import norm
    g = 0.5772156649
    z = (1 - g) * norm.ppf(1 - 1.0 / n) + g * norm.ppf(1 - 1.0 / (n * math.e))
    return float(z / math.sqrt(T - 1))


def _n_noise_above(n: int, T: int, ir_annual: float) -> float | None:
    """How many of n noise cells would print an annual IR above `ir_annual` over T months."""
    if T < 3:
        return None
    from scipy.stats import norm
    return float(n * (1.0 - norm.cdf(ir_annual / math.sqrt(12) * math.sqrt(T - 1))))


def leaderboard(done: dict, rules: list, *, spy_meta: dict, today: date,
                partial: str | None, since: str) -> dict:
    """Deflate across every cell looked at, then rank. Deterministic per input."""
    order = [r.id for r in rules if r.id in done]
    res = [done[i] for i in order]
    ok = [r for r in res if r.get("status") == "OK"]
    cand = [r for r in ok if not r["meta"]["control"]]
    cells = []
    for r in cand:
        for k, c in r["cells"].items():
            if c.get("status") == "OK":
                cells.append(c)
    families = sorted({r["meta"]["family"] for r in cand})
    SL.deflate(cells, n_trials=len(cells), effective_trials=max(2, len(families)))
    controls = [r for r in ok if r["meta"]["control"]]
    ctl_cells = [c for r in controls for c in r["cells"].values() if c.get("status") == "OK"]
    if ctl_cells:
        SL.deflate(ctl_cells, n_trials=max(2, len(cells)), effective_trials=max(2, len(families)))
    rows = [_row(r) for r in cand]
    # DSR first, its z second (ties below display precision order by evidence,
    # never by name -- the 2026-09-26 first run sorted 336 zeros by id).
    key_dsr = lambda x: (x["dsr"] if x["dsr"] is not None else -1.0,               # noqa: E731
                         x["dsr_z"] if x.get("dsr_z") is not None else -99.0)
    key_cagr = lambda x: (x["hindsight_cagr_since_2020"]                           # noqa: E731
                          if x["hindsight_cagr_since_2020"] is not None else -9.0)
    top_n = int(_cfg.STRATEGY_LIB_TOP_N)
    by_id = sorted(rows, key=lambda x: x["id"])          # stable sorts keep id order on ties
    by_dsr = sorted(by_id, key=key_dsr, reverse=True)
    by_cagr = sorted(by_id, key=key_cagr, reverse=True)
    by_sealed = sorted(by_id, key=sealed_sort_key, reverse=True)
    T_full = max((len(c.get("active_returns") or []) for c in cells), default=0)
    T_sealed = max((len(c.get("sealed_active_returns") or []) for c in cells), default=0)
    spy_row = None
    for r in ok:
        c = r["cells"].get(r["primary_k"]) or {}
        h = c.get("hindsight_since_2020") or {}
        if h.get("cagr_spy") is not None:
            spy_row = {"cagr_since_2020": h["cagr_spy"], "cum_since_2020": h["cum_spy"],
                       "max_dd_since_2020": h.get("max_dd_spy"), "n_months": h.get("n_months")}
            break
    ctl_rows = {x["id"]: x for x in (_row(r) for r in controls)}
    row_by_id = {x["id"]: x for x in rows}
    gaps = {}
    if "skill_mom" in row_by_id and "unskilled_mom" in ctl_rows:
        gaps["skill_mom_minus_unskilled_mom"] = SL.by_year_gap(
            row_by_id["skill_mom"], ctl_rows["unskilled_mom"], exclude=("2025",))
    if "skill_mom" in row_by_id and "skill_mom_ranks_21_40" in ctl_rows:
        gaps["skill_mom_minus_ranks_21_40"] = SL.by_year_gap(
            row_by_id["skill_mom"], ctl_rows["skill_mom_ranks_21_40"], exclude=("2025",))
    if "mom_12_1" in row_by_id:
        for tag in SL.QUARTER_OFFSETS:
            cid = f"mom_12_1_q_{tag}"
            if cid in ctl_rows:
                gaps[f"{cid}_minus_mom_12_1"] = SL.by_year_gap(
                    ctl_rows[cid], row_by_id["mom_12_1"], exclude=())
    sr0 = cells[0].get("dsr_sr0_monthly") if cells else None
    sr0_lib = cells[0].get("dsr_sr0_monthly_library") if cells else None
    board = {
        "schema": "strategy_library.leaderboard/1", "job": JOB, "date": str(today),
        "licence": "PRODUCT_EXPERIMENT",
        "read_me_first": (
            "HINDSIGHT BACKTEST. Every rule was registered 2026-09-26, after every "
            "month in these tables; 'since 2020' is what the rule WOULD have done, "
            "not what Aegis did. The quotable record starts at registration and "
            "accrues in the lib_ forward books. Read by_year_signs, LOO-worst and "
            "the worst breadth cell BEFORE the CAGR column; read DSR before Sharpe."),
        "partial": partial, "n_rules_in_library": len(rules), "n_rules_done": len(res),
        "n_refused": sum(1 for r in res if r.get("status") != "OK"),
        "refused": {r["id"]: r.get("why") for r in res if r.get("status") != "OK"},
        "objective": {
            "primary_sort": (f"sealed_vs_spy = the {SL.SELECTION_WINDOW_LABEL}: net CAGR minus "
                             "SPY CAGR, same months. A SORT, not a holdout -- the out-of-sample "
                             "read is `dev_selected_sealed_evaluated`"),
            "window_label": SL.SELECTION_WINDOW_LABEL,
            "dev_end": SL.DEV_END, "sealed_start": SL.SEALED_START,
            "recent": f"last {SL.RECENT_PERIODS} completed monthly periods (~{SL.RECENT_SESSIONS} sessions)",
            "split_rule": "a period belongs to the window its ENTRY session (decision + 1 business day) is in",
            "n_sealed_months": T_sealed, "n_dev_months_max": T_full - T_sealed if T_full else None,
            "honest_note": (
                f"The {SL.SELECTION_WINDOW_LABEL} is {T_sealed} monthly blocks. The split was "
                f"declared in code before this run; nobody's eyes were closed to 2024-2026: every "
                f"rule was written in 2026, and the 02:00 board printed full-sample numbers "
                f"including it. Ranking {len(cells)} cells on {T_sealed} months selects luck as "
                f"readily as skill -- read sealed_dsr (at n={len(cells)}), the dev column, and "
                f"`dev_selected_sealed_evaluated` (rules picked on dev only, read on 2024-26)."),
            "noise_sharpe_ceiling_monthly_full": _sr0(len(cells), T_full),
            "noise_sharpe_ceiling_monthly_sealed": _sr0(len(cells), T_sealed),
            "noise_sharpe_ceiling_annual_sealed": (_sr0(len(cells), T_sealed) or 0) * math.sqrt(12),
            "expected_noise_cells_ir_above_0_5_annual_full": _n_noise_above(len(cells), T_full, 0.5),
            "expected_noise_cells_ir_above_0_5_annual_sealed": _n_noise_above(len(cells), T_sealed, 0.5),
        },
        "multiplicity": {
            "cells_looked_at": len(cells),
            "n_cells_looked_at": len(cells), "n_candidate_rules": len(cand),
            "n_families": len(families), "families": families,
            "dsr_n_trials_nominal": len(cells), "dsr_n_trials_effective": max(2, len(families)),
            "dsr_sr0_monthly_nominal": sr0,
            "dsr_null_basis": "analytic 1/sqrt(T-1) (primary); cross-cell dispersion beside it",
            "dsr_sr0_monthly_library_dispersion": sr0_lib,
            "hlz_t_bar": SL.HLZ_T_BAR,
            "controls_excluded_from_trials": [r["id"] for r in controls],
            "not_reachable_catalogue_rows": len(SL.NOT_REACHABLE),
        },
        "spy": {**(spy_row or {}), "source": spy_meta.get("source"),
                "canonical_refusal": spy_meta.get("canonical_refusal")},
        "market_benchmark": spy_meta.get("market_benchmark"),
        "since": since,
        "extra_rules_source": SL.EXTRA_SOURCE, "extra_rules_refused": SL.EXTRA_REFUSED,
        "dev_selected_sealed_evaluated": SL.dev_selected_sealed_evaluated(rows, n_blocks=T_sealed),
        "control_gaps": gaps,
        "top_by_sealed_vs_spy": by_sealed[:top_n],
        "bottom_by_sealed_vs_spy": by_sealed[-top_n:][::-1],
        "top_by_dsr": by_dsr[:top_n],
        "top_by_hindsight_cagr_since_2020": by_cagr[:top_n],
        "bottom_by_hindsight_cagr_since_2020": by_cagr[-top_n:][::-1],
        "controls": [_row(r) for r in controls],
        "all_rows": sorted(rows, key=lambda x: x["id"]),
    }
    return _round(board)


# ═════════════════════════════════ writing ══════════════════════════════════

def _pct(v, nd: int = 1) -> str:
    return "n/a" if v is None else f"{v*100:+.{nd}f}%"


def _num(v, nd: int = 2) -> str:
    return "n/a" if v is None else f"{v:.{nd}f}"


def _table(rows: list) -> list[str]:
    head = ("| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | "
            "best-5-mo share / CAGR without them (SPY full) | "
            "t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |")
    lines = [head, "|" + "---|" * 13]
    for r in rows:
        wc = r.get("worst_cell") or {}
        lines.append(
            f"| {r['id']} | {r['family']} | {r['k']} | `{r.get('by_year_signs')}` | "
            f"{_pct(r.get('loo_worst_mean_active'), 2)} (drop {r.get('loo_worst_dropped_year')}) | "
            f"{wc.get('k')}: {_pct(wc.get('cagr_since_2020'))} | "
            f"{_num(r.get('top5_months_share_of_log_return'))} / {_pct(r.get('cagr_without_best_5_months'))} "
            f"({_pct(r.get('spy_cagr_same_window'))}) | {_num(r.get('t_active_horizon_blocks'))} "
            f"({r.get('n_blocks_horizon')}) | {_num(r.get('sharpe_annual'))} ({r.get('n_date_blocks')}) | "
            f"{_num(r.get('dsr'), 3)} ({r.get('dsr_n_trials')}) | "
            f"{_pct(r.get('hindsight_cagr_since_2020'))} | {_pct(r.get('hindsight_spy_cagr_since_2020'))} | "
            f"{_pct(r.get('hindsight_cum_since_2020'), 0)} |")
    return lines


def _sealed_table(rows: list) -> list[str]:
    head = ("| id | family | k | 2024-26 vs SPY | 2024-26 CAGR (months) | SPY 2024-26 | 2024-26 DSR | "
            "dev CAGR | dev vs SPY | DSR full (n) | LOO-worst (mo) | top-5-mo share | "
            "turnover/yr | cost bps/yr | max DD | recent-126 (SPY) | by-year |")
    lines = [head, "|" + "---|" * 17]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['family']} | {r['k']} | **{_pct(r.get('sealed_vs_spy'))}** | "
            f"{_pct(r.get('sealed_cagr'))} ({r.get('n_sealed_months')}) | {_pct(r.get('sealed_spy_cagr'))} | "
            f"{_num(r.get('sealed_dsr'), 3)} | {_pct(r.get('dev_cagr'))} | {_pct(r.get('dev_vs_spy'))} | "
            f"{_num(r.get('dsr'), 3)} ({r.get('dsr_n_trials')}) | {_pct(r.get('loo_worst_mean_active'), 2)} | "
            f"{_num(r.get('top5_months_share_of_log_return'))} | {_num(r.get('turnover_annual'), 1)}x | "
            f"{_num(r.get('cost_bps_paid'), 0)} | {_pct(r.get('max_dd'))} | "
            f"{_pct(r.get('recent_126_return'))} ({_pct(r.get('recent_126_spy'))}) | "
            f"`{r.get('by_year_signs')}` |")
    return lines


def _dev_selected_md(b: dict) -> list[str]:
    if not b or b.get("status") == "REFUSED":
        return ["## Dev-selected, 2024-26-evaluated", "", f"REFUSED: {b.get('why')}", ""]
    sp = b.get("spearman_dev_vs_selection_window") or {}
    md = b.get("mde") or {}
    L = ["## Dev-selected, 2024-26-evaluated (the one out-of-sample read on this board)", "",
         f"Rules picked on DEV only (dev net CAGR - SPY), read on the {b['label']}:", "",
         "| top-n by dev | mean 2024-26 vs SPY | median | beat SPY | mean dev vs SPY |",
         "|---|---:|---:|---:|---:|"]
    for k in ("top_10", "top_20", "top_50"):
        t = b.get(k)
        if t:
            L.append(f"| {t['n']} | {_pct(t['mean_selection_window_vs_spy'])} | "
                     f"{_pct(t['median_selection_window_vs_spy'])} | {t['n_beat_spy']}/{t['n']} | "
                     f"{_pct(t['mean_dev_vs_spy'])} |")
    L += ["", f"- Spearman(dev rank, 2024-26 rank) over {sp.get('n')} rules: "
              f"**{_num(sp.get('rho'), 2)}** (p {_num(sp.get('p_value'), 3)}).",
          f"- rules beating SPY in BOTH windows: {b.get('n_beat_spy_in_both_windows')} of "
          f"{b.get('n_rules')} ({b.get('n_beat_spy_in_both_windows_top5_lt_0_6_dd_gt_m40')} also "
          f"with top-5-month share < 0.6 and max DD > -40%)."]
    if "mde_monthly_80pct_power" in md:
        L.append(f"- MDE: median active sigma {_pct(md['active_sigma_monthly_median'], 2)}/month -> "
                 f"SE {_pct(md['se_monthly'], 2)} over {md['n_blocks']} blocks -> MDE "
                 f"**{_pct(md['mde_monthly_80pct_power'], 2)}/month** at 80% power. A window this "
                 "long can kill a rule; it cannot certify a realistic 0.5%/month edge.")
    return L + [""]


def _gaps_md(gaps: dict) -> list[str]:
    if not gaps:
        return []
    L = ["## Control gaps by year (excess of A minus excess of B)", ""]
    for k, g in gaps.items():
        yrs = ", ".join(f"{y} {v*100:+.1f}" for y, v in sorted(g["gap_by_year"].items()))
        L.append(f"- `{k}`: {yrs} pp; excluding {g['excluded'] or 'nothing'}: sum "
                 f"{_pct(g['sum_excluding'])}, {g['n_years_positive_excluding']} of "
                 f"{g['n_years_excluding']} years positive.")
    return L + [""]


def render_md(board: dict, books: dict | None = None, forward: list | None = None) -> str:
    mp = board["multiplicity"]
    spy = board["spy"]
    L = [f"# Strategy library leaderboard — {board['date']}", "",
         f"> {board['read_me_first']}", ""]
    if board.get("run_id"):
        L += [f"Run `{board['run_id']}`; receipt `{board.get('receipt')}` (this file is the "
              f"'latest' copy and is refreshed by every run; the receipt is not).", ""]
    if board.get("partial"):
        L += [f"**PARTIAL:** {board['partial']} — {board['n_rules_done']} of "
              f"{board['n_rules_in_library']} rules evaluated.", ""]
    L += ["## Multiplicity (read before any row)", "",
          f"- cells looked at: **{mp['n_cells_looked_at']}** ({mp['n_candidate_rules']} rules x breadth "
          f"k=10/20/50 + own k); DSR computed at n={mp['dsr_n_trials_nominal']} and, beside it, at the "
          f"{mp['n_families']} families (n={mp['dsr_n_trials_effective']}).",
          f"- expected best monthly active Sharpe of pure noise at n={mp['dsr_n_trials_nominal']}: "
          f"{_num(mp.get('dsr_sr0_monthly_nominal'), 3)} monthly (x3.46 annualised) on the analytic "
          f"null; {_num(mp.get('dsr_sr0_monthly_library_dispersion'), 3)} if the null sd is the "
          f"dispersion across these cells (printed as `dsr_null_from_library`, never ranked on: "
          f"structurally negative rules inflate it).",
          f"- Harvey-Liu-Zhu bar: t >= {mp['hlz_t_bar']} on horizon-wide blocks before a row is "
          f"anything but a PRODUCT_EXPERIMENT observation.",
          f"- refused rules: {board['n_refused']}; catalogue rows not reachable on this panel: "
          f"{mp['not_reachable_catalogue_rows']} (named in `strategy_library.NOT_REACHABLE`).",
          f"- controls (never ranked, never trials): {', '.join(mp['controls_excluded_from_trials'])}", ""]
    ob = board.get("objective") or {}
    if ob:
        L += [f"## The sort: net return vs SPY in the {SL.SELECTION_WINDOW_LABEL}", "",
              f"- dev: entry <= {ob['dev_end']}; 2024-26 selection window: entry >= {ob['sealed_start']} "
              f"({ob['n_sealed_months']} monthly blocks); recent: {ob['recent']}. {ob['split_rule']}.",
              f"- {ob['honest_note']}",
              f"- noise ceiling at n={mp['n_cells_looked_at']}: best monthly active Sharpe of pure noise "
              f"{_num(ob.get('noise_sharpe_ceiling_monthly_full'), 3)} over the full window, "
              f"{_num(ob.get('noise_sharpe_ceiling_monthly_sealed'), 3)} over the 2024-26 window "
              f"(= {_num(ob.get('noise_sharpe_ceiling_annual_sealed'), 2)} annual IR).",
              f"- expected pure-noise cells with an annual IR > 0.5: "
              f"{_num(ob.get('expected_noise_cells_ir_above_0_5_annual_full'), 1)} on the full window, "
              f"{_num(ob.get('expected_noise_cells_ir_above_0_5_annual_sealed'), 1)} on the 2024-26 window.",
              f"- rules from strategy_library_ext: {board.get('extra_rules_source')}"
              + (f"; refused: {board.get('extra_rules_refused')}" if board.get("extra_rules_refused") else ""),
              ""]
        L += _dev_selected_md(board.get("dev_selected_sealed_evaluated") or {})
        L += ["", f"## Top 10 by net return vs SPY in the {SL.SELECTION_WINDOW_LABEL} "
                  "(a sort on data seen, not a holdout)", ""]
        L += _sealed_table(board.get("top_by_sealed_vs_spy") or [])
        L += ["", "## Bottom 10 by net return vs SPY in the 2024-26 selection window", ""]
        L += _sealed_table(board.get("bottom_by_sealed_vs_spy") or [])
        L += ["", "## Controls on the 2024-26 selection window (random_*: the luck bar; "
                  "diagnostic_control: one question each, never ranked)", ""]
        L += _sealed_table(board.get("controls") or [])
        L += [""] + _gaps_md(board.get("control_gaps") or {})
    L += [
          "## SPY", "",
          f"SPY since {board['since']}: CAGR {_pct(spy.get('cagr_since_2020'))}, cumulative "
          f"{_pct(spy.get('cum_since_2020'), 0)}, max DD {_pct(spy.get('max_dd_since_2020'))} "
          f"({spy.get('n_months')} months). Source `{spy.get('source')}` via learner.benchmark"
          + (f"; canonical leg refused: {spy.get('canonical_refusal')}" if spy.get("canonical_refusal") else "")
          + ".", "",
          "## Top 10 by deflated Sharpe", ""] + _table(board["top_by_dsr"]) + [
          "", "## Top 10 by hindsight CAGR since 2020", ""] + _table(board["top_by_hindsight_cagr_since_2020"]) + [
          "", "## Bottom 10", ""] + _table(board["bottom_by_hindsight_cagr_since_2020"]) + [
          "", "## Controls (random k — the bar a rule must clear by more than luck)", ""] + _table(board["controls"])
    if board.get("refused"):
        L += ["", "## Refused", ""] + [f"- `{k}`: {v}" for k, v in sorted(board["refused"].items())]
    if books:
        L += ["", "## Forward books frozen tonight", ""]
        for k, v in books.items():
            L.append(f"- `{k}`: {v.get('status')} {v.get('worst_case', '')}")
    if forward:
        L += ["", "## Backtest vs forward", ""] + [f"- {x}" for x in forward]
    return "\n".join(L) + "\n"


# ═════════════════════════════════ forward books ════════════════════════════

def recent_bars(W: dict, n: int = 90) -> pd.DataFrame:
    """The last `n` sessions as a long frame -- what twins and grades read."""
    dates, syms = W["dates"][-n:], W["symbols"]
    frames = []
    for j, d in enumerate(dates):
        i = len(W["dates"]) - n + j
        ok = np.isfinite(W["close"][i])
        frames.append(pd.DataFrame({"symbol": syms[ok], "date": d,
                                    "open": W["open"][i][ok], "high": W["high"][i][ok],
                                    "low": W["low"][i][ok], "close": W["close"][i][ok],
                                    "volume": W["volume"][i][ok]}))
    return pd.concat(frames, ignore_index=True)


def worst_case_line(name: str, n: int, capital: float) -> str:
    """CLAUDE.md protocol 4: the worst case in dollars for the book as frozen."""
    w = 1.0 / n
    fill = abs(_cfg.STRATEGY_LIB_DELIST_RETURN)
    return (f"WORST CASE {name}: {n} names x {w:.2%} = 100% gross of ${capital:,.0f}, "
            f"gross/equity 1.00, no stop (monthly rebalance): every name at the "
            f"{fill:.0%} delisting fill = -${capital*fill:,.0f}; one name to zero = "
            f"-${capital*w:,.0f}; the whole book to zero = -${capital:,.0f}")


# ═════════════════════════════════ the freeze gate ══════════════════════════
#
# Review 2026-09-26 (chunks D+E), adjudicated: a leaderboard row gets a $1M
# HEADLINE forward book only if every boolean below is True. A row that fails
# is still frozen -- as a CONTROL (`__control`, `kind: control`) -- because a
# forward record of what the gate refused is how the gate itself gets graded.
# Every boolean is printed on the freeze log and in docs/BRIDGE.md.

GATE_MAX_WEIGHT = 0.10          # per name; GATE_MAX_WEIGHT_SMALL_K when k <= 10
GATE_MAX_WEIGHT_SMALL_K = 0.15
GATE_MIN_EFFECTIVE_N = 8.0      # 1 / sum(w^2)
GATE_CLUSTER_RHO = 0.80         # pairwise 63-session daily-return correlation
GATE_CLUSTER_MAX_SHARE = 0.40
GATE_CLUSTER_WINDOW = 63
GATE_EARNINGS_WEIGHT = 0.10     # a name above this may not print in the first sessions
GATE_EARNINGS_SESSIONS = 5
GATE_EARNINGS_DUE_DAYS = 75     # last 8-K 2.02 + this <= the 5th session => a print is due
GATE_EARNINGS_FILE_MAX_AGE_DAYS = 30
GATE_WORST_NAME_USD = 150_000.0
GATE_MAX_STALE_SESSIONS = 1
GATE_FAMILY_MAX = 2
GATE_TOP5_SHARE_MAX = 0.6
GATE_MAX_DD_MIN = -0.40
GATE_TODO = ("TODO (review item 14, not tonight): re-freeze each library book as a chained "
             "immutable version at every one of its rule's own rebalance dates (month-end "
             "decision, next-open entry) under one rule fingerprint, so a monthly rule is "
             "graded as the rule and not as a stale September basket.")


def _sessions_between(a: pd.Timestamp, b: pd.Timestamp) -> int:
    """Business days in (a, b]: how many sessions a bar dated `a` is behind `b`
    (US holidays are counted as sessions -- conservative)."""
    a, b = pd.Timestamp(a).normalize(), pd.Timestamp(b).normalize()
    if b <= a:
        return 0
    return int(len(pd.bdate_range(a + pd.Timedelta(days=1), b)))


def first_sessions(decision: pd.Timestamp, calendar, n: int) -> list:
    """The first `n` sessions after the decision date: the calendar where it
    reaches, business days beyond it."""
    decision = pd.Timestamp(decision).normalize()
    cal = pd.DatetimeIndex(calendar) if calendar is not None else pd.DatetimeIndex([])
    out = [d for d in cal if d > decision][:n]
    d = out[-1] if out else decision
    while len(out) < n:
        d = d + pd.offsets.BDay(1)
        out.append(pd.Timestamp(d))
    return out


def earnings_due(tickers, decision_date, calendar=None, *, path: Path | None = None,
                 n_sessions: int = GATE_EARNINGS_SESSIONS) -> dict:
    """ticker -> {"status": DUE / NOT_DUE / UNKNOWN, ...} for a print inside the
    first `n_sessions` sessions after `decision_date`.

    Point-in-time from EDGAR 8-K item 2.02 (the factory's own earnings source):
    a print is DUE when the name's last 2.02 filed on or before the decision
    date + GATE_EARNINGS_DUE_DAYS lands on or before the n-th session. No 2.02
    history, or an 8-K file more than GATE_EARNINGS_FILE_MAX_AGE_DAYS older than
    the decision, is UNKNOWN -- never a pass.
    """
    decision = pd.Timestamp(decision_date).normalize()
    path = Path(path or Path(_cfg.OPTIMUS_LEDGER_DIR) / "edgar_8k" / "eightk_items.parquet")
    tickers = [str(t).upper() for t in tickers]
    if not path.exists():
        return {t: {"status": "UNKNOWN", "why": f"no 8-K items at {path}"} for t in tickers}
    ek = pd.read_parquet(path, columns=["ticker", "filing_date", "items_joined"])
    ek["filing_date"] = pd.to_datetime(ek["filing_date"], errors="coerce")
    ek = ek[ek["filing_date"].notna() & (ek["filing_date"] <= decision)]
    file_end = ek["filing_date"].max() if len(ek) else None
    if file_end is None or (decision - file_end).days > GATE_EARNINGS_FILE_MAX_AGE_DAYS:
        return {t: {"status": "UNKNOWN", "why": f"8-K file ends {file_end}"} for t in tickers}
    ek = ek[ek["ticker"].astype(str).str.upper().isin(tickers)
            & ek["items_joined"].fillna("").astype(str).str.contains("2.02", regex=False)]
    last = ek.assign(t=ek["ticker"].astype(str).str.upper()).groupby("t")["filing_date"].max()
    window_end = first_sessions(decision, calendar, n_sessions)[-1]
    out = {}
    for t in tickers:
        if t not in last.index:
            out[t] = {"status": "UNKNOWN", "why": "no 8-K 2.02 history"}
            continue
        due = last[t] + pd.Timedelta(days=GATE_EARNINGS_DUE_DAYS)
        out[t] = {"status": "DUE" if due <= window_end else "NOT_DUE",
                  "last_202": str(last[t].date()), "due_from": str(due.date()),
                  "window_end": str(pd.Timestamp(window_end).date()),
                  "file_ends": str(file_end.date())}
    return out


def correlated_clusters(weights: dict, bars: pd.DataFrame, asof, *,
                        window: int = GATE_CLUSTER_WINDOW, rho: float = GATE_CLUSTER_RHO) -> dict:
    """Connected components of names whose `window`-session daily returns
    (bars at or before `asof`) correlate above `rho`; the heaviest one's share."""
    names = [t for t in weights if weights[t] > 0]
    b = bars[(bars["symbol"].isin(names)) & (bars["date"] <= pd.Timestamp(asof))]
    wide = b.pivot_table(index="date", columns="symbol", values="close").sort_index()
    ret = wide.pct_change(fill_method=None).iloc[-window:]
    ret = ret.loc[:, ret.notna().sum() >= 40]
    C = ret.corr(min_periods=40) if ret.shape[1] >= 2 else pd.DataFrame()
    parent = {t: t for t in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    pairs = []
    cols = list(C.columns)
    for i, a in enumerate(cols):
        for bb in cols[i + 1:]:
            v = C.loc[a, bb]
            if np.isfinite(v) and v > rho:
                pairs.append((a, bb, round(float(v), 3)))
                parent[find(a)] = find(bb)
    comp: dict = {}
    for t in names:
        comp.setdefault(find(t), []).append(t)
    clusters = [sorted(v) for v in comp.values() if len(v) >= 2]
    shares = [sum(weights[t] for t in c) for c in clusters]
    j = int(np.argmax(shares)) if shares else None
    return {"pairs_above_rho": pairs, "clusters": clusters,
            "max_cluster": clusters[j] if j is not None else [],
            "max_cluster_share": float(shares[j]) if j is not None else 0.0,
            "n_names_with_returns": int(ret.shape[1]), "window": window, "rho": rho}


def freeze_gate(row: dict | None, weights: dict, bars: pd.DataFrame, calendar, *,
                decision_date=None, family_books_before: int = 0,
                earnings: dict | None = None, capital: float | None = None) -> dict:
    """Every boolean of the freeze rule and the verdict: PASS or CONTROL(reasons).

    `row`: the rule's leaderboard row (None for a forward-only rule: SELECTION
    cannot pass). `weights`: ticker -> weight as the book would be frozen.
    `bars`: daily bars (symbol, date, close) through at least the decision date.
    `calendar`: the session dates. `family_books_before`: headline books this
    rule's family already has. `earnings`: `earnings_due()`'s output (computed
    when None). A boolean that cannot be computed is None, and None never
    passes: the reason is printed as UNKNOWN.
    """
    from backend.services import llm_portfolio as LP
    capital = float(capital or LP.START_CAPITAL)
    decision = pd.Timestamp(decision_date or date.today()).normalize()
    w = {str(t).upper(): float(v) for t, v in weights.items() if str(t).upper() != "CASH" and v > 0}
    k = len(w)
    r = row or {}

    def gt(v, x):
        return None if v is None else bool(v > x)
    sel = {
        "dev_vs_spy_gt_0": gt(r.get("dev_vs_spy"), 0.0),
        "selection_window_vs_spy_gt_0": gt(r.get("sealed_vs_spy"), 0.0),
        "top5_month_share_lt_0_6": (None if r.get("top5_months_share_of_log_return") is None
                                    else bool(r["top5_months_share_of_log_return"] < GATE_TOP5_SHARE_MAX)),
        "max_dd_gt_m40": gt(r.get("max_dd"), GATE_MAX_DD_MIN),
        "loo_worst_mean_active_gt_0": gt(r.get("loo_worst_mean_active"), 0.0),
        "family_books_le_2": bool(family_books_before + 1 <= GATE_FAMILY_MAX),
    }
    cap = GATE_MAX_WEIGHT_SMALL_K if k <= 10 else GATE_MAX_WEIGHT
    wmax_t = max(w, key=w.get) if w else None
    wmax = w[wmax_t] if w else None
    eff_n = (1.0 / sum(v * v for v in w.values())) if w else 0.0
    cl = correlated_clusters(w, bars, decision) if w else {"max_cluster_share": 0.0, "max_cluster": []}
    big = [t for t, v in w.items() if v > GATE_EARNINGS_WEIGHT]
    if big and earnings is None:
        earnings = earnings_due(big, decision, calendar)
    earn = {t: (earnings or {}).get(t, {"status": "UNKNOWN", "why": "not looked up"}) for t in big}
    due = [t for t in big if earn[t].get("status") == "DUE"]
    unknown = [t for t in big if earn[t].get("status") not in ("DUE", "NOT_DUE")]
    earn_ok = False if due else (None if unknown else True)
    worst_name_usd = capital * (wmax or 0.0)
    con = {
        f"max_name_weight_le_{cap:.2f}": (None if wmax is None else bool(wmax <= cap + 1e-9)),
        "effective_n_ge_8": bool(eff_n >= GATE_MIN_EFFECTIVE_N),
        "no_rho_0_8_cluster_above_40pct": bool(cl["max_cluster_share"] <= GATE_CLUSTER_MAX_SHARE),
        "no_name_gt_10pct_printing_in_first_5_sessions": earn_ok,
        "largest_name_to_zero_le_150k": bool(worst_name_usd <= GATE_WORST_NAME_USD),
    }
    b = bars[bars["date"] <= decision]
    held = b[b["symbol"].isin(list(w))]
    bar_date = pd.Timestamp(held["date"].max()) if len(held) else None
    stale = _sessions_between(bar_date, decision) if bar_date is not None else None
    tim = {"bars_le_1_session_old": (None if stale is None
                                     else bool(stale <= GATE_MAX_STALE_SESSIONS))}
    reasons = []
    names = {"dev_vs_spy_gt_0": "DEV_NOT_ABOVE_SPY",
             "selection_window_vs_spy_gt_0": "2024_26_NOT_ABOVE_SPY",
             "top5_month_share_lt_0_6": "TOP5_MONTH_SHARE",
             "max_dd_gt_m40": "MAX_DD", "loo_worst_mean_active_gt_0": "LOO_WORST",
             "family_books_le_2": "FAMILY_CAP",
             f"max_name_weight_le_{cap:.2f}": "NAME_WEIGHT", "effective_n_ge_8": "EFFECTIVE_N",
             "no_rho_0_8_cluster_above_40pct": "CORRELATED_CLUSTER",
             "no_name_gt_10pct_printing_in_first_5_sessions": "EARNINGS",
             "largest_name_to_zero_le_150k": "WORST_CASE_NAME",
             "bars_le_1_session_old": "STALE_BARS"}
    for grp in (sel, con, tim):
        for key, v in grp.items():
            if v is None:
                reasons.append(("NO_BACKTEST_ROW" if grp is sel and not row
                                else "EARNINGS_UNKNOWN" if key.startswith("no_name_gt")
                                else names[key] + "_UNKNOWN"))
            elif v is False:
                reasons.append(names[key])
    reasons = list(dict.fromkeys(reasons))
    verdict = "PASS" if not reasons else "CONTROL"
    return {
        "verdict": verdict, "reasons": reasons,
        "label": "PASS" if not reasons else f"CONTROL({', '.join(reasons)})",
        "selection": sel, "construction": con, "timing": tim,
        "detail": {"k": k, "max_name": wmax_t, "max_weight": wmax, "weight_cap": cap,
                   "effective_n": round(eff_n, 3),
                   "max_cluster": cl.get("max_cluster"),
                   "max_cluster_share": round(float(cl["max_cluster_share"]), 4),
                   "pairs_above_rho": cl.get("pairs_above_rho", []),
                   "earnings_names_over_10pct": earn,
                   "largest_name_to_zero_usd": round(worst_name_usd, 0),
                   "decision_date": str(decision.date()),
                   "bar_date": str(bar_date.date()) if bar_date is not None else None,
                   "staleness_sessions": stale,
                   "family": r.get("family"), "family_books_before": family_books_before},
        "rule": ("SELECTION dev>SPY, 2024-26>SPY, top-5-month share<0.6, max DD>-40%, LOO-worst>0, "
                 "<=2 books/family; CONSTRUCTION max name <=10% (15% if k<=10), effN>=8, no "
                 "rho>0.8 cluster >40%, no name >10% printing in the first 5 sessions, largest "
                 "name to zero <=$150k at $1M; TIMING bars <=1 session old at the decision date"),
        "todo": GATE_TODO,
    }


def _existing_lib_ids(books: list) -> set:
    out = set()
    for b in books:
        nm = str(b.get("name") or "")
        if nm.startswith("lib_") and b.get("kind") != "twin":
            nm = nm[: -len("__control")] if nm.endswith("__control") else nm
            out.add(nm[4:].rsplit("_", 1)[0])
    return out


def freeze_book(rule_id: str, description: str, picks: list, *, today: date,
                bars: pd.DataFrame, note: str, log=print, gate: dict | None = None) -> dict:
    from backend.services import llm_portfolio as LP
    k = len(picks)
    control = bool(gate) and gate.get("verdict") != "PASS"
    name = f"lib_{rule_id}_{today}" + ("__control" if control else "")
    w = 1.0 / k
    if gate:
        note = f"{note} Freeze gate: {gate['label']}."
    book = {
        "name": name, "kind": "control" if control else "personal",
        "objective": ("Relative P&L vs SPY over 21 sessions, long-only equal weight, net of "
                      "band round-trip cost (strategy-library forward twin)"),
        "model": f"rule:strategy_library:{rule_id}",
        "strategy": (f"PRODUCT_EXPERIMENT; kind personal. Strategy-library rule `{rule_id}`: "
                     f"{description}. Top-{k}, equal weight, monthly rebalance. {note}")[:2000],
        "horizon_days": [1, 5, 21, 63, 126],
        "positions": [{"ticker": p["symbol"], "weight": w,
                       "thesis": f"{description}; score {p['score']:.4g}, rank {i+1} of {k}",
                       "falsifier": (f"drops out of the rule's top-{2*k} at the next month-end, "
                                     f"or the book trails its random_same_band twin after 63 "
                                     f"sessions")}
                      for i, p in enumerate(picks)] + [
            {"ticker": "CASH", "weight": 0.0, "thesis": "declared: fully invested",
             "falsifier": "n/a"}],
    }
    if gate:
        book["freeze_gate"] = gate
    rec = LP.freeze(book, today=today)
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    tw = LP.twins(rec, asof=today, seed=seed, bars=bars)
    LP.append_book(rec)
    for t in tw.values():
        LP.append_book(t)
    wc = worst_case_line(name, k, LP.START_CAPITAL)
    log(wc)
    if gate:
        log(f"FREEZE GATE {name}: {gate['label']}")
    return {"status": "FROZEN", "book_id": rec["book_id"], "name": name,
            "kind": rec.get("kind"), "gate": gate,
            "tickers": [p["ticker"] for p in rec["positions"] if p["ticker"] != "CASH"],
            "twins": sorted(tw), "twin_seed": seed, "worst_case": wc}


def forward_only_picks(entry: dict, panel: pd.DataFrame, *, today: date) -> list:
    """Positions for a rule that exists only forward on this panel."""
    last = panel["date"].max()
    elig = panel[(panel["date"] == last) & panel["eligible"]].set_index("symbol")
    if entry["id"] == "forecast_dispersion_v1":
        p = Path(_cfg.OPTIMUS_LEDGER_DIR) / "analyst" / "target_snapshots.parquet"
        if not p.exists():
            raise SL.RuleInputMissing(f"no target snapshots at {p}")
        t = pd.read_parquet(p)
        t["observed_at"] = pd.to_datetime(t["observed_at"], utc=True)
        t = t[t["observed_at"] <= pd.Timestamp(datetime.now(timezone.utc))]
        t = t.sort_values("observed_at").groupby("ticker").tail(1)
        t["dispersion"] = (t["target_high"] - t["target_low"]) / t["price"]
        t = t[(t["price"] > 0) & t["dispersion"].notna() & (t["dispersion"] >= 0)]
        t = t[t["ticker"].isin(elig.index)]
        t = t.sort_values(["dispersion", "ticker"]).head(entry["k"])
        if len(t) < entry["k"]:
            raise SL.RuleInputMissing(f"only {len(t)} eligible names carry a target snapshot")
        return [{"symbol": r.ticker, "score": -float(r.dispersion)} for r in t.itertuples()]
    if entry["id"] == "book_f_seasonality_11_20_v0":
        month = (pd.Timestamp(today) + pd.offsets.MonthBegin(1)).strftime("%Y-%m")
        p = Path(_cfg.OPTIMUS_LEDGER_DIR) / "engines" / f"F_seasonality_{month}.json"
        if not p.exists():
            raise SL.RuleInputMissing(f"no Book F export for {month} at {p}")
        d = json.loads(p.read_text(encoding="utf-8"))
        rows = [r for r in d["rows"] if r.get("tercile") == "top"]
        rows = sorted(rows, key=lambda r: r["rank"])[: entry["k"]]
        return [{"symbol": r["symbol"], "score": float(r["score"])} for r in rows]
    raise SL.RuleInputMissing(f"no forward-only resolver for {entry['id']}")


def freeze_forward(board: dict, panel: pd.DataFrame, bars: pd.DataFrame, *,
                   today: date, rules: list, log=print) -> dict:
    from backend.services import llm_portfolio as LP
    existing = _existing_lib_ids(LP.read_books(include_voided=True))
    by_id = {r.id: r for r in rules}
    out: dict = {}
    n_top = int(_cfg.STRATEGY_LIB_FREEZE_TOP)
    cal = pd.DatetimeIndex(sorted(bars.loc[bars["symbol"] == "SPY", "date"].unique())
                           if (bars["symbol"] == "SPY").any() else sorted(bars["date"].unique()))
    fam_n: dict = {}
    for row in board["top_by_dsr"][:n_top]:
        rid = row["id"]
        if rid in existing:
            out[rid] = {"status": "ALREADY_HAS_A_FORWARD_BOOK"}
            continue
        try:
            picks = SL.latest_selection(panel, by_id[rid])
            note = (f"Backtest (HINDSIGHT, registered {row['first_registered_utc'][:10]}): "
                    f"CAGR since 2020 {_pct(row['hindsight_cagr_since_2020'])} vs SPY "
                    f"{_pct(row['hindsight_spy_cagr_since_2020'])}, DSR {row['dsr']} at "
                    f"n={row['dsr_n_trials']}, LOO-worst {_pct(row['loo_worst_mean_active'], 2)}/mo, "
                    f"by-year {row['by_year_signs']}; bars asof {panel['date'].max().date()}.")
            gate = freeze_gate(row, {p_["symbol"]: 1.0 / len(picks) for p_ in picks}, bars, cal,
                               decision_date=today,
                               family_books_before=fam_n.get(row.get("family"), 0))
            out[rid] = freeze_book(rid, by_id[rid].description, picks, today=today,
                                   bars=bars, note=note, log=log, gate=gate)
            if gate["verdict"] == "PASS":
                fam_n[row.get("family")] = fam_n.get(row.get("family"), 0) + 1
        except (SL.RuleInputMissing, LP.Refusal) as e:
            out[rid] = {"status": "REFUSED", "why": str(e)}
    for entry in SL.FORWARD_ONLY:
        rid = entry["id"]
        if rid in existing:
            out[rid] = {"status": "ALREADY_HAS_A_FORWARD_BOOK"}
            continue
        try:
            picks = forward_only_picks(entry, panel, today=today)
            gate = freeze_gate(None, {p_["symbol"]: 1.0 / len(picks) for p_ in picks}, bars, cal,
                               decision_date=today)
            out[rid] = freeze_book(rid, entry["description"], picks, today=today, bars=bars,
                                   note=f"FORWARD-ONLY on this panel. {entry['replay_reported']}",
                                   log=log, gate=gate)
            out[rid]["green_replay_never_forward"] = entry["green_replay_never_forward"]
        except (SL.RuleInputMissing, LP.Refusal) as e:
            out[rid] = {"status": "REFUSED", "why": str(e)}
    return out


def backtest_vs_forward(board: dict, bars: pd.DataFrame, *, today: date) -> list[str]:
    """For every lib_ book: the backtest's mean month beside the forward 21d.

    `forward_21d_vs_backtest_mean_21d` -- "the backtest says +X, the forward
    book says +Y". A forward book with fewer than 21 sessions says PENDING.
    """
    from backend.services import llm_portfolio as LP
    rows = {r["id"]: r for r in board.get("all_rows", [])}
    lines = []
    for b in LP.read_books():
        nm = str(b.get("name") or "")
        if not nm.startswith("lib_") or b.get("kind") == "twin":
            continue
        rid = nm[4:].rsplit("_", 1)[0]
        g = LP.grade(b, bars, today=today)
        hz = g.get("horizons") or {}
        h21 = hz.get(21) or hz.get("21") or {}
        fwd = h21.get("vs_spy") if h21.get("status") == "OK" else None
        bt = (rows.get(rid) or {}).get("mean_active_monthly")
        sessions = (g.get("to_date") or {}).get("sessions")
        fwd_s = (_pct(fwd, 2) if fwd is not None
                 else f"PENDING ({h21.get('why') or g.get('why') or g.get('status')})")
        lines.append(f"{nm}: forward_21d_vs_spy={fwd_s}; backtest_mean_21d_vs_spy="
                     f"{_pct(bt, 2)} (hindsight); forward sessions={sessions}")
    return lines


def new_run_id(now: datetime | None = None) -> str:
    """`<date>T<HHMMSS>Z` in UTC: the suffix every receipt of one run carries."""
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def receipt_paths(out: Path, stem: str, today: date, run_id: str) -> tuple[Path, Path]:
    """(the run's own receipt, the date-named 'latest' copy)."""
    return out / f"{stem}_{run_id}.json", out / f"{stem}_{today}.json"


def write_outputs(board: dict, *, out: Path, today: date, books=None, forward=None,
                  run_id: str | None = None) -> dict:
    """The run's receipt `leaderboard_<run_id>.json` (never overwritten), then
    the date-named latest copy and `LEADERBOARD.md`, both naming the receipt."""
    out.mkdir(parents=True, exist_ok=True)
    run_id = run_id or new_run_id()
    lb, latest = receipt_paths(out, "leaderboard", today, run_id)
    if lb.exists():
        raise FileExistsError(f"REFUSED: {lb} exists; a receipt is never overwritten")
    board = {**board, "run_id": run_id, "receipt": _rel(lb)}
    atomic_write_json(lb, board, indent=1)
    atomic_write_json(latest, board, indent=1)
    md = render_md(board, books, forward)
    (out / "LEADERBOARD.md").write_text(md, encoding="utf-8")
    return {"leaderboard": str(lb), "leaderboard_latest": str(latest),
            "markdown": str(out / "LEADERBOARD.md"), "run_id": run_id}


def _rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(REPO)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def write_replication(board: dict, panel: pd.DataFrame, spy: pd.Series, rules: list, *,
                      out: Path, today: date, n: int = 10, run_id: str | None = None) -> Path:
    """`top10_for_replication_<date>.json`: what a second engine needs, nothing it must infer.

    Schema per `research_library_expansion_and_lean.md` 2.5: each top-n rule by
    the PRIMARY sort (sealed vs SPY) with its exact rule, universe filter,
    rebalance dates, held symbols and weights by date, the cost model, and the
    monthly series (gross, cost, net, SPY) this engine produced. A second
    engine recomputes the monthly series from the SAME holdings and costs and
    compares; it never re-derives the selection.
    """
    from backend.services import xs_ranker as XR
    by_id = {r.id: r for r in rules}
    rows = []
    for r in (board.get("top_by_sealed_vs_spy") or [])[:n]:
        rule = by_id[r["id"]]
        hold: list = []
        m = SL.run_strategy(panel, rule, k=int(r["k"]), holdings=hold)
        wins = SL.split_windows(pd.DatetimeIndex(m["date"]))
        ent = SL.entry_dates(pd.DatetimeIndex(m["date"]))
        series = []
        for j, x in enumerate(m.itertuples(index=False)):
            s_ = spy.get(x.date)
            series.append({"date": str(x.date.date()), "entry": str(ent[j].date()),
                           "gross": float(x.gross), "cost": float(x.cost), "net": float(x.net),
                           "spy": float(s_) if s_ is not None and np.isfinite(s_) else None,
                           "turnover": float(x.turnover), "n_held": int(x.n_held),
                           "n_delisted": int(x.n_delisted), "rebalanced": bool(x.rebalanced),
                           "window": ("sealed" if wins["sealed"][j] else "dev")
                           + ("+recent" if wins["recent"][j] else "")})
        meta = rule.meta()
        rows.append({
            "id": rule.id, "family": rule.family, "rule_one_line": rule.description,
            "economic_reason": rule.economic_reason, "signal_shape": meta["shape"],
            "signature": meta["signature"], "requires": meta["requires"],
            "universe_rule": rule.universe_rule,
            "universe_filter": SL.UNIVERSE_TEXT[rule.universe_rule],
            "eligible": SL.ELIGIBLE_TEXT, "k": int(r["k"]), "hold_months": rule.hold_months,
            "weight_rule": rule.weight_rule, "regime_gate": rule.regime_gate,
            "rebalance_rule": rule.rebalance, "source": rule.source,
            "first_registered_utc": rule.first_registered_utc, "fingerprint": rule.fingerprint(),
            "rebalance_dates": [h["date"] for h in hold],
            "held_symbols_by_date": {h["date"]: h["symbols"] for h in hold},
            "weights_by_date": {h["date"]: h["weights"] for h in hold},
            "risk_off_dates": [h["date"] for h in hold if h.get("risk_off")],
            "monthly_return_series": series,
            "board": {k_: r.get(k_) for k_ in ("sealed_vs_spy", "sealed_cagr", "sealed_spy_cagr",
                                               "n_sealed_months", "sealed_dsr", "dev_cagr", "dsr",
                                               "turnover_annual", "cost_bps_paid", "max_dd",
                                               "recent_126_return")},
        })
    run_id = run_id or board.get("run_id") or new_run_id()
    # the library's own 12-1 momentum (k=20, equal weight) on the same months: the
    # UMD leg of the semis/momentum regression in bridge_report (review idea 1)
    reference = {}
    if "mom_12_1" in by_id:
        mm = SL.run_strategy(panel, by_id["mom_12_1"], k=20)
        reference["mom_12_1"] = [{"date": str(x.date.date()), "net": float(x.net)}
                                 for x in mm.itertuples(index=False)]
    doc = {"schema": "strategy_library.replication/1", "date": str(today), "run_id": run_id,
           "reference_series": reference,
           "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "source": f"backend/services/strategy_library.py + leaderboard_{run_id}.json",
           "selection": "top by sealed_vs_spy (the board's primary sort)",
           "split": {"dev_end": SL.DEV_END, "sealed_start": SL.SEALED_START,
                     "recent_periods": SL.RECENT_PERIODS,
                     "rule": "a period's window is that of its ENTRY session (decision + 1 business day)"},
           "cost_model": {
               "bands_bps_round_trip": dict(XR.COST_BPS_BY_BAND),
               "band_boundaries_median_dollar_vol": {"mega": ">= 1e9", "large": ">= 1e8",
                                                     "mid": ">= 2e7", "small": "< 2e7"},
               "convention": ("half the band round trip per side on the weight traded at each "
                              "rebalance; drift between rebalances untraded and uncharged; the "
                              "band is the name's at the date it was bought"),
               "band_boundary_var": "median_dollar_vol (63 sessions, trailing)"},
           "fill_convention": ("decide at the month-end close; enter at the NEXT session's open; "
                               "exit at the open of the session after the next decision date; a "
                               "name whose bars stop inside the period is filled at its last close "
                               f"x (1 + {_cfg.STRATEGY_LIB_DELIST_RETURN}); cash (regime gate off) earns 0"),
           "rows": rows}
    path, latest = receipt_paths(out, "top10_for_replication", today, run_id)
    atomic_write_json(path, _round(doc, 10), indent=1)
    atomic_write_json(latest, _round(doc, 10), indent=1)
    return path


def check_replication(doc: dict) -> list[dict]:
    """Recompute each row's sealed CAGR and total net from its own monthly series."""
    res = []
    for r in doc["rows"]:
        s = r["monthly_return_series"]
        sealed = [x["net"] for x in s if x["window"].startswith("sealed")]
        res.append({"id": r["id"], "n": len(s), "sealed_cagr": SL._cagr(sealed),
                    "cum_net": float(np.prod([1 + x["net"] for x in s]) - 1.0),
                    "gross_minus_cost_equals_net": all(abs(x["gross"] - x["cost"] - x["net"]) < 1e-9
                                                       for x in s)})
    return res


def print_top(board: dict, log=print) -> None:
    mp = board["multiplicity"]
    ob = board.get("objective") or {}
    if ob:
        log(f"\nSORT: net vs SPY in the {SL.SELECTION_WINDOW_LABEL}; entry >= {ob['sealed_start']} "
            f"({ob['n_sealed_months']} months); cells looked at {mp['n_cells_looked_at']}; noise "
            f"ceiling sealed {_num(ob.get('noise_sharpe_ceiling_monthly_sealed'), 3)}/mo "
            f"({_num(ob.get('noise_sharpe_ceiling_annual_sealed'), 2)} annual IR)")
        log(f"{'id':28s} {'family':18s} {'sealVsSPY':>9s} {'sealCAGR':>8s} {'sDSR':>5s} {'devCAGR':>8s} "
            f"{'DSR':>5s} {'LOOw':>7s} {'top5':>5s} {'turn':>5s} {'bps':>5s} {'maxDD':>7s} {'rec126':>7s}")
        for r in board.get("top_by_sealed_vs_spy") or []:
            log(f"{r['id']:28s} {r['family']:18s} {_pct(r.get('sealed_vs_spy')):>9s} "
                f"{_pct(r.get('sealed_cagr')):>8s} {_num(r.get('sealed_dsr'), 2):>5s} "
                f"{_pct(r.get('dev_cagr')):>8s} {_num(r.get('dsr'), 2):>5s} "
                f"{_pct(r.get('loo_worst_mean_active'), 2):>7s} "
                f"{_num(r.get('top5_months_share_of_log_return')):>5s} "
                f"{_num(r.get('turnover_annual'), 1):>5s} {_num(r.get('cost_bps_paid'), 0):>5s} "
                f"{_pct(r.get('max_dd')):>7s} {_pct(r.get('recent_126_return')):>7s}")
    log(f"\nMULTIPLICITY: {mp['n_cells_looked_at']} cells looked at, {mp['n_families']} families; "
        f"DSR at n={mp['dsr_n_trials_nominal']} (effective n={mp['dsr_n_trials_effective']}); "
        f"HLZ t bar {mp['hlz_t_bar']}")
    s = board["spy"]
    log(f"SPY since {board['since']}: CAGR {_pct(s.get('cagr_since_2020'))}, cum "
        f"{_pct(s.get('cum_since_2020'), 0)} [{s.get('source')}]")
    log("TOP 10 BY DSR (HINDSIGHT -- registered 2026-09-26):")
    log(f"{'id':26s} {'family':14s} {'years':12s} {'LOOw/mo':>8s} {'worst':>12s} {'top5sh':>6s} "
        f"{'ex5':>7s} {'t':>6s} {'Sharpe':>6s} {'DSR':>6s} {'CAGR20':>8s} {'SPY':>7s}")
    for r in board["top_by_dsr"]:
        wc = r.get("worst_cell") or {}
        log(f"{r['id']:26s} {r['family']:14s} {str(r.get('by_year_signs')):12s} "
            f"{_pct(r.get('loo_worst_mean_active'), 2):>8s} "
            f"{str(wc.get('k'))+':'+_pct(wc.get('cagr_since_2020')):>12s} "
            f"{_num(r.get('top5_months_share_of_log_return')):>6s} "
            f"{_pct(r.get('cagr_without_best_5_months')):>7s} "
            f"{_num(r.get('t_active_horizon_blocks')):>6s} {_num(r.get('sharpe_annual')):>6s} "
            f"{_num(r.get('dsr'), 3):>6s} {_pct(r.get('hindsight_cagr_since_2020')):>8s} "
            f"{_pct(r.get('hindsight_spy_cagr_since_2020')):>7s}")


# ═════════════════════════════════ main ═════════════════════════════════════

def main(argv=None) -> int:
    from backend.services import xs_ranker as XR
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="300 symbols from 2018, no freezing")
    ap.add_argument("--no-freeze", action="store_true")
    ap.add_argument("--offline", action="store_true", help="skip the canonical SPY network fetch")
    ap.add_argument("--minutes", type=float, default=float(_cfg.STRATEGY_LIB_TIME_BOX_MIN))
    ap.add_argument("--max-rules", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    t0 = time.time()
    today = date.today()
    run_id = new_run_id()
    out = Path(a.out) if a.out else (out_dir() / "smoke" if a.smoke else out_dir())
    paths = XR.survivorship_free_paths()
    start = "2018-01-01" if a.smoke else _cfg.STRATEGY_LIB_START
    print(f"{JOB} {today}: panels {[p.name for p in paths]}; start {start}", flush=True)
    W = load_wide(paths, start=start, max_symbols=300 if a.smoke else 0)
    print(f"  wide arrays {W['close'].shape} ({W['n_bar_rows']:,} bars) in {time.time()-t0:.0f}s", flush=True)
    panel = build_panel(W, delist_return=float(_cfg.STRATEGY_LIB_DELIST_RETURN))
    if a.smoke or a.no_freeze:
        # only the forward freeze reads high/low/volume again; free ~0.3 GB for the attachers
        for c_ in ("high", "low", "volume"):
            W.pop(c_, None)
    print(f"  panel {len(panel):,} rows, {panel['date'].nunique()} dates in {time.time()-t0:.0f}s", flush=True)
    panel, fmeta = attach_fundamentals(panel)
    panel, flmeta = attach_flow(panel)
    print(f"  fundamentals {fmeta.get('status')}, flow {flmeta.get('status')} ({time.time()-t0:.0f}s)", flush=True)
    extra_meta = {}
    for name, fn in (("ratings", lambda p: attach_ratings(p, W)), ("insider", attach_insider),
                     ("eightk", lambda p: attach_8k(p, W)), ("short_interest", attach_short_interest),
                     ("sector", attach_sector), ("extension", lambda p: attach_extension(p, W))):
        try:
            panel, extra_meta[name] = fn(panel)
        except Exception as e:                            # noqa: BLE001 -- a refusal, named
            extra_meta[name] = {"status": "REFUSED", "why": f"{type(e).__name__}: {e}"}
        print(f"  {name}: {extra_meta[name].get('status')} "
              f"{extra_meta[name].get('why', '')} ({time.time()-t0:.0f}s)", flush=True)
    panel["tiebreak"] = SL._tiebreak(panel)
    last = pd.DataFrame({"symbol": W["symbols"],
                         "date": [W["dates"][i] if i >= 0 else pd.NaT for i in
                                  np.where(np.isfinite(W["close"]).any(axis=0),
                                           len(W["dates"]) - 1 - np.argmax(np.isfinite(W["close"])[::-1], axis=0), -1)]})
    audit = XR.survivorship_audit(last.dropna())
    print(f"  survivorship: {audit['verdict'][:120]}", flush=True)
    spy, spy_meta = spy_leg(panel, W, network=not a.offline)
    print(f"  SPY leg: {spy_meta['source']} ({len(spy)} periods)"
          + (f"; canonical refused: {spy_meta.get('canonical_refusal')}" if spy_meta.get("canonical_refusal") else ""),
          flush=True)
    rules = SL.rules()
    if a.max_rules:
        rules = rules[: a.max_rules]
    board = run_factory(panel, spy, spy_meta, today=today, rules=rules, out=out,
                        resume=a.resume, time_box_s=a.minutes * 60 - (time.time() - t0))
    print_top(board)
    books = forward = None
    if not (a.smoke or a.no_freeze):
        bars = recent_bars(W)
        books = freeze_forward(board, panel, bars, today=today, rules=rules)
        forward = backtest_vs_forward(board, bars, today=today)
        for x in forward:
            print("  " + x)
    dse = board.get("dev_selected_sealed_evaluated") or {}
    if dse.get("sentence"):
        print("DEV-SELECTED, 2024-26-EVALUATED: " + dse["sentence"], flush=True)
    for k_, g_ in (board.get("control_gaps") or {}).items():
        print(f"CONTROL GAP {k_}: by year {g_['gap_by_year']}; excluding {g_['excluded']}: "
              f"sum {g_['sum_excluding']}", flush=True)
    paths_out = write_outputs(board, out=out, today=today, books=books, forward=forward,
                              run_id=run_id)
    board = {**board, "run_id": run_id}
    try:
        paths_out["replication"] = str(write_replication(board, panel, spy, rules, out=out,
                                                         today=today, run_id=run_id))
    except Exception as e:                                # noqa: BLE001 -- printed, never silent
        paths_out["replication"] = f"REFUSED: {type(e).__name__}: {e}"
    print(f"  replication file: {paths_out['replication']}", flush=True)
    run = {"job": JOB, "date": str(today), "run_id": run_id, "licence": "PRODUCT_EXPERIMENT",
           "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "elapsed_s": round(time.time() - t0, 1), "partial": board.get("partial"),
           "n_rules_done": board["n_rules_done"], "n_computed_this_run": board["n_computed_this_run"],
           "panel": {"rows": int(len(panel)), "dates": int(panel["date"].nunique()),
                     "symbols": int(panel["symbol"].nunique()),
                     "first": str(panel["date"].min().date()), "last": str(panel["date"].max().date()),
                     "fingerprint": panel_fingerprint(panel)},
           "survivorship_audit": audit, "fundamentals": fmeta, "flow": flmeta,
           "chunk_d_inputs": extra_meta, "objective": board.get("objective"),
           "spy": {k: v for k, v in spy_meta.items() if k != "market_benchmark"},
           "market_benchmark": spy_meta.get("market_benchmark"),
           "books": books, "backtest_vs_forward": forward, **paths_out}
    rp, rl = receipt_paths(out, "run", today, run_id)
    atomic_write_json(rp, _round(run), indent=1)
    atomic_write_json(rl, _round(run), indent=1)
    print(f"-> {paths_out['leaderboard']}  ({time.time()-t0:.0f}s)")
    return 0


def B_backtest_factory(smoke: bool = False, **_ignored) -> dict:  # noqa: N802
    """The night-queue entry point (`scripts.night_factory_jobs` dispatch shape).

    Registering it is one JOBS line plus this id in the `fn(smoke=a.smoke)`
    tuple of `night_factory_jobs.main`; the payload's `verdict` leads with a
    tag `night_factory._status` reads.
    """
    argv = ["--smoke"] if smoke else []
    rc = main(argv)
    out = out_dir() / "smoke" if smoke else out_dir()
    today = date.today()
    try:
        board = json.loads((out / f"leaderboard_{today}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"verdict": "FAILED", "headline": f"exited {rc} with no leaderboard"}
    top = (board.get("top_by_dsr") or [{}])[0]
    return {"verdict": ("DESCRIPTIVE: " + ("PARTIAL " if board.get("partial") else "")
                        + f"{board['n_rules_done']} rules, {board['multiplicity']['n_cells_looked_at']} "
                        f"cells; DSR leader {top.get('id')} dsr {top.get('dsr')} (HINDSIGHT)"),
            "leaderboard": str(out / f"leaderboard_{today}.json"), "exit_code": rc}


if __name__ == "__main__":
    raise SystemExit(main())
