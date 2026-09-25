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
4. Writes `leaderboard_<date>.json` + `LEADERBOARD.md` (idempotent per day: the
   same panel gives the same bytes; run metadata lives in `run_<date>.json`).
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
    extra = pd.DataFrame({"gross_margin": gm, "revenue": rev}).reset_index()
    extra = extra.sort_values(["ticker", "filed"])
    g = extra.groupby("ticker")
    prev_rev = g["revenue"].shift(4)
    extra["rev_gr"] = (extra["revenue"] - prev_rev) / prev_rev.where(prev_rev > 0)
    extra["gm_chg"] = extra["gross_margin"] - g["gross_margin"].shift(4)
    extra["inflection"] = extra["rev_gr"] * extra["gm_chg"]
    feats = r.merge(extra[["ticker", "filed", "gross_margin", "rev_gr", "gm_chg", "inflection"]],
                    on=["ticker", "filed"], how="left")
    feats["available"] = feats["filed"] + pd.Timedelta(days=FF.LAG_DAYS)
    feats = feats.sort_values("available")
    cols = list(FF.FUNDAMENTAL_FEATURES) + ["gross_margin", "rev_gr", "gm_chg", "inflection"]
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


def evaluate_rule(panel: pd.DataFrame, spy: pd.Series, rule, *, since: str) -> dict:
    """All breadth cells of one rule; a missing input is a named REFUSAL."""
    try:
        sc = SL.selection_scores(panel, rule)
    except SL.RuleInputMissing as e:
        return {"id": rule.id, "status": "REFUSED", "why": str(e), "meta": rule.meta()}
    cells = {}
    for k in _breadth(rule):
        m = SL.run_strategy(panel, rule, k=k, scores=sc)
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
    spy_row = None
    for r in ok:
        c = r["cells"].get(r["primary_k"]) or {}
        h = c.get("hindsight_since_2020") or {}
        if h.get("cagr_spy") is not None:
            spy_row = {"cagr_since_2020": h["cagr_spy"], "cum_since_2020": h["cum_spy"],
                       "max_dd_since_2020": h.get("max_dd_spy"), "n_months": h.get("n_months")}
            break
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
        "multiplicity": {
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


def render_md(board: dict, books: dict | None = None, forward: list | None = None) -> str:
    mp = board["multiplicity"]
    spy = board["spy"]
    L = [f"# Strategy library leaderboard — {board['date']}", "",
         f"> {board['read_me_first']}", ""]
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
          f"- controls (never ranked, never trials): {', '.join(mp['controls_excluded_from_trials'])}", "",
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


def _existing_lib_ids(books: list) -> set:
    out = set()
    for b in books:
        nm = str(b.get("name") or "")
        if nm.startswith("lib_") and b.get("kind") != "twin":
            out.add(nm[4:].rsplit("_", 1)[0])
    return out


def freeze_book(rule_id: str, description: str, picks: list, *, today: date,
                bars: pd.DataFrame, note: str, log=print) -> dict:
    from backend.services import llm_portfolio as LP
    k = len(picks)
    name = f"lib_{rule_id}_{today}"
    w = 1.0 / k
    book = {
        "name": name, "kind": "personal",
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
    rec = LP.freeze(book, today=today)
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    tw = LP.twins(rec, asof=today, seed=seed, bars=bars)
    LP.append_book(rec)
    for t in tw.values():
        LP.append_book(t)
    wc = worst_case_line(name, k, LP.START_CAPITAL)
    log(wc)
    return {"status": "FROZEN", "book_id": rec["book_id"], "name": name,
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
    existing = _existing_lib_ids(LP.read_books())
    by_id = {r.id: r for r in rules}
    out: dict = {}
    n_top = int(_cfg.STRATEGY_LIB_FREEZE_TOP)
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
            out[rid] = freeze_book(rid, by_id[rid].description, picks, today=today,
                                   bars=bars, note=note, log=log)
        except (SL.RuleInputMissing, LP.Refusal) as e:
            out[rid] = {"status": "REFUSED", "why": str(e)}
    for entry in SL.FORWARD_ONLY:
        rid = entry["id"]
        if rid in existing:
            out[rid] = {"status": "ALREADY_HAS_A_FORWARD_BOOK"}
            continue
        try:
            picks = forward_only_picks(entry, panel, today=today)
            out[rid] = freeze_book(rid, entry["description"], picks, today=today, bars=bars,
                                   note=f"FORWARD-ONLY on this panel. {entry['replay_reported']}",
                                   log=log)
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


def write_outputs(board: dict, *, out: Path, today: date, books=None, forward=None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    lb = out / f"leaderboard_{today}.json"
    atomic_write_json(lb, board, indent=1)
    md = render_md(board, books, forward)
    (out / "LEADERBOARD.md").write_text(md, encoding="utf-8")
    return {"leaderboard": str(lb), "markdown": str(out / "LEADERBOARD.md")}


def print_top(board: dict, log=print) -> None:
    mp = board["multiplicity"]
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
    out = Path(a.out) if a.out else (out_dir() / "smoke" if a.smoke else out_dir())
    paths = XR.survivorship_free_paths()
    start = "2018-01-01" if a.smoke else _cfg.STRATEGY_LIB_START
    print(f"{JOB} {today}: panels {[p.name for p in paths]}; start {start}", flush=True)
    W = load_wide(paths, start=start, max_symbols=300 if a.smoke else 0)
    print(f"  wide arrays {W['close'].shape} ({W['n_bar_rows']:,} bars) in {time.time()-t0:.0f}s", flush=True)
    panel = build_panel(W, delist_return=float(_cfg.STRATEGY_LIB_DELIST_RETURN))
    print(f"  panel {len(panel):,} rows, {panel['date'].nunique()} dates in {time.time()-t0:.0f}s", flush=True)
    panel, fmeta = attach_fundamentals(panel)
    panel, flmeta = attach_flow(panel)
    print(f"  fundamentals {fmeta.get('status')}, flow {flmeta.get('status')} ({time.time()-t0:.0f}s)", flush=True)
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
    paths_out = write_outputs(board, out=out, today=today, books=books, forward=forward)
    run = {"job": JOB, "date": str(today), "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "elapsed_s": round(time.time() - t0, 1), "partial": board.get("partial"),
           "n_rules_done": board["n_rules_done"], "n_computed_this_run": board["n_computed_this_run"],
           "panel": {"rows": int(len(panel)), "dates": int(panel["date"].nunique()),
                     "symbols": int(panel["symbol"].nunique()),
                     "first": str(panel["date"].min().date()), "last": str(panel["date"].max().date()),
                     "fingerprint": panel_fingerprint(panel)},
           "survivorship_audit": audit, "fundamentals": fmeta, "flow": flmeta,
           "spy": {k: v for k, v in spy_meta.items() if k != "market_benchmark"},
           "market_benchmark": spy_meta.get("market_benchmark"),
           "books": books, "backtest_vs_forward": forward, **paths_out}
    atomic_write_json(out / f"run_{today}.json", _round(run), indent=1)
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
