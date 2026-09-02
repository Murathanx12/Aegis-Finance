"""H2 / H3 / ANOMALY — does WHO holds, and HOW they habitually hold, predict?

Licence: PRODUCT_EXPERIMENT (docs/IDEA_2026-08-31_HOLDER_PROVENANCE_TO_THE_ROOTS.md §6).
No significance gate is required at this tier.  The pre-registration header, PIT
discipline and honest sub-period reporting are NOT optional and are written into
the receipt BEFORE any number.

Depends on scripts/holder_fingerprint.py having been run (fingerprint panel +
transitions cache + quarter snapshots).

Run: python -m scripts.holder_h2_h3_test
"""

from __future__ import annotations

import argparse
import json
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.holder_fingerprint import (
    BULK, ROOT, TRACKER, TRANS_DIR, WRDS, FP_PATH, QSNAP_PATH,
    Q0_YEAR, build_crsp, public_date_of, qidx_of, qlabel,
)

RECEIPT = TRACKER / "holder_h2_h3.json"
EVENTS_DIR = WRDS / "holder_events"

# ---------------------------------------------------------------- pre-registration
PREREG = {
    "written_before_any_result": True,
    "date": "2026-09-02",
    "licence": "PRODUCT_EXPERIMENT — exploration; no significance gate, no MDE, no "
               "multiplicity control. A claim of alpha would require RESEARCH_CLAIM "
               "gates that this run does NOT attempt.",
    "grain": "FILER (13F mgrno). The active/passive split is NOT observable in "
             "entitled WRDS (idea doc §4a); every manager-level statement here is a "
             "blended index+active statement and carries active_passive=UNKNOWN.",
    "pit_rule": "an event at report quarter q is actionable at "
                "quarter_end(max(rdate, first Thomson vintage)) + 45 calendar days; "
                "all forward returns start at the first trading CLOSE on or after "
                "that date. Fingerprints stamped for quarter q read filings through "
                "q-1 only. Manager-history scores read only events whose own forward "
                "window had already resolved before the current event's public date.",
    "events": {
        "NEW_POSITION": "shares_adj_prev == 0 and shares_adj_now > 0",
        "LARGE_ADD": "shares_adj_now >= 1.5 * shares_adj_prev > 0 AND the position is "
                     ">= 0.5% of the filer's portfolio value",
        "LARGE_TRIM": "0 < shares_adj_now <= 0.5 * shares_adj_prev",
        "COMPLETE_EXIT": "shares_adj_prev > 0 and shares_adj_now == 0",
        "note": "share counts are split-comparable (shares x CRSP cfacshr) so a "
                "split is not a LARGE_ADD. Events are generated only for filers "
                "present in BOTH q-1 and q (a skipped filing is not an exit).",
    },
    "primary_metric": "63-session forward EXCESS return vs the equal-weighted CRSP "
                      "screened universe, from the public date. 21/126/252 sessions "
                      "and a value-weighted benchmark are reported alongside.",
    "H2": {
        "hypothesis": "Manager identity carries skill: a filer's OWN historical "
                      "post-event excess predicts the forward excess of their NEXT "
                      "event of the same type, beyond the event type's pooled base "
                      "rate.",
        "design": "By-quarter (Fama-MacBeth) cross-sectional OLS of forward excess on "
                  "the manager-history score (own expanding PIT mean post-event excess "
                  "for that event type, MINUS the PIT pooled mean for that type), with "
                  "controls log market cap (z), momentum 12-1 (z), and event-type "
                  "dummies. t computed across QUARTERS; n_effective = number of "
                  "quarters with a valid coefficient (§58 date blocks).",
        "secondary": "tercile sort on the manager-history score within quarter; "
                     "top-minus-bottom spread, t across quarters.",
        "min_history": "a manager-history score requires >= 5 resolved prior events "
                       "of that type for that manager.",
    },
    "H3": {
        "hypothesis": "A long-duration holder ENTERING is a different event from a "
                      "fast trader entering (and likewise for exits).",
        "design": "Within each quarter, split filers into terciles of the PIT "
                  "fingerprint's median completed holding duration (requires >= 10 "
                  "completed spells). For NEW_POSITION and for COMPLETE_EXIT "
                  "separately, take mean forward excess by tercile; primary statistic "
                  "is the per-quarter LONG-minus-SHORT spread and its t across "
                  "quarters.",
    },
    "ANOMALY_H6_prep": {
        "definition_fixed_before_outcomes": True,
        "score": "percentile of the event's position size (% of the COMPANY's shares "
                 "outstanding) within that manager's OWN prior history of position "
                 "sizes, read from the PIT fingerprint's quantile ladder.",
        "cut": "top decile = pct_of_company_now >= the manager's own historical p90.",
        "comparison": "matched ordinary events — same quarter, same event type, same "
                      "market-cap tercile — mean difference per cell, averaged per "
                      "quarter, t across quarters. Winners AND losers reported "
                      "(fraction positive, p10/p90, worst and best deciles).",
    },
    "honesty": {
        "sub_periods": "1996-2012 and 2013-2024 reported separately as a regime check, "
                       "plus the full sample.",
        "do_nothing_control": "all events pooled, no conditioning — reported first.",
        "costs": "IGNORED. Every number here is GROSS of commissions, spread, impact "
                 "and borrow. 13F is a <=45-day-stale ownership structure, not a live "
                 "catalyst.",
        "winsorising": "forward excess is reported raw AND winsorised at the 1st/99th "
                       "percentile within quarter; both appear in the receipt.",
        "missing_controls": "log cap and momentum are z-scored within quarter; a "
                            "missing control is imputed at the cross-sectional mean "
                            "(z=0) rather than dropping the event.",
    },
}

HORIZONS = {"h21": 21, "h63": 63, "h126": 126, "h252": 252}
PRIMARY = "h63"
# Lag before an event's realised outcome may be used as a predictor for another
# event. Outcomes for quarter q enter the accumulator only AFTER quarter q+LAG is
# scored, so the EFFECTIVE lag is LAG+1 = 2 quarters ~ 182 calendar days, against
# the ~91 calendar days a 63-session window actually needs. 2x margin.
SCORE_LAG_Q = 1
ETYPES = ["NEW_POSITION", "LARGE_ADD", "LARGE_TRIM", "COMPLETE_EXIT"]
MIN_MGR_HISTORY = 5
MIN_SPELLS_FOR_DURATION = 10
QUANT_P = np.array([0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
QUANT_COLS = ["pct_of_company_p10", "pct_of_company_p25", "pct_of_company_median",
              "pct_of_company_p75", "pct_of_company_p90", "pct_of_company_p95",
              "pct_of_company_p99"]


# ---------------------------------------------------------------- helpers
def tstat(x: np.ndarray):
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return {"mean": None, "t": None, "n_quarters": n}
    se = x.std(ddof=1) / np.sqrt(n)
    return {"mean": float(x.mean()), "t": float(x.mean() / se) if se > 0 else None,
            "se": float(se), "n_quarters": int(n),
            "t_newey_west_4": _nw_t(x, 4)}


def _nw_t(x: np.ndarray, lags: int):
    n = len(x)
    if n < lags + 3:
        return None
    e = x - x.mean()
    g0 = (e @ e) / n
    v = g0
    for L in range(1, lags + 1):
        g = (e[L:] @ e[:-L]) / n
        v += 2.0 * (1.0 - L / (lags + 1.0)) * g
    if v <= 0:
        return None
    return float(x.mean() / np.sqrt(v / n))


def winsor(x: np.ndarray, lo=0.01, hi=0.99):
    ok = np.isfinite(x)
    if ok.sum() < 20:
        return x
    a, b = np.nanquantile(x[ok], [lo, hi])
    return np.clip(x, a, b)


def zscore(x: np.ndarray):
    ok = np.isfinite(x)
    out = np.zeros_like(x, dtype="float64")
    if ok.sum() < 5:
        return out
    m, s = x[ok].mean(), x[ok].std(ddof=1)
    if not np.isfinite(s) or s == 0:
        return out
    out[ok] = (x[ok] - m) / s
    return out


def ols_coef(y, X):
    """Return coefficients and their positions; X already includes an intercept."""
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    if ok.sum() < max(30, X.shape[1] * 5):
        return None
    b, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
    return b, int(ok.sum())


def pct_rank_from_quantiles(x: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """Percentile of x within a distribution summarised by the quantile ladder Q
    (n, 7) at probabilities QUANT_P.  Log-linear interpolation; clipped to
    [0.005, 0.995] outside the ladder."""
    lx = np.log(np.maximum(x, 1e-12))
    lQ = np.log(np.maximum(Q, 1e-12))
    idx = (lx[:, None] > lQ).sum(axis=1)
    out = np.full(len(x), np.nan)
    below = idx == 0
    above = idx == Q.shape[1]
    mid = ~below & ~above
    out[below] = QUANT_P[0] * 0.5
    out[above] = 0.995
    if mid.any():
        i = idx[mid] - 1
        r = np.arange(len(x))[mid]
        x0, x1 = lQ[r, i], lQ[r, i + 1]
        p0, p1 = QUANT_P[i], QUANT_P[i + 1]
        w = np.where(x1 > x0, (lx[mid] - x0) / np.maximum(x1 - x0, 1e-9), 0.0)
        out[mid] = p0 + np.clip(w, 0, 1) * (p1 - p0)
    valid = np.isfinite(Q).all(axis=1) & np.isfinite(x)
    out[~valid] = np.nan
    return out


# ---------------------------------------------------------------- event stream
def classify(t: pd.DataFrame) -> np.ndarray:
    sp, sn = t.shares_prev.values, t.shares_now.values
    pf = np.nan_to_num(t.pct_pf_now.values, nan=0.0)
    et = np.full(len(t), -1, dtype="int8")
    et[(sp > 0) & (sn > 0) & (sn <= 0.5 * sp)] = 2                      # LARGE_TRIM
    et[(sp > 0) & (sn >= 1.5 * sp) & (pf >= 0.005)] = 1                 # LARGE_ADD
    et[(sp > 0) & (sn == 0)] = 3                                        # COMPLETE_EXIT
    et[(sp == 0) & (sn > 0)] = 0                                        # NEW_POSITION
    return et


def run(start_year=1996, end_year=2024, verbose=True) -> dict:
    t0 = time.time()
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    for f in EVENTS_DIR.glob("*.parquet"):
        f.unlink()

    crsp = build_crsp(verbose=verbose)
    qs = pd.read_parquet(QSNAP_PATH, columns=["permno", "qidx", "logcap", "mom_12_1",
                                              "cap_tercile", "mktcap"])
    qs["k"] = qs.qidx.values.astype("int64") * 1000000 + qs.permno.values.astype("int64")
    qsi = qs.set_index("k")[["logcap", "mom_12_1", "cap_tercile"]]
    del qs

    fp = pd.read_parquet(FP_PATH, columns=[
        "mgrno", "as_of_qidx", "dur_median_qtrs", "n_completed_spells",
        "n_quarters_filed", "n_positions", "exit_freq", "entry_freq",
        "turnover_mean", "cap_tercile_mean"] + QUANT_COLS)
    fp["k"] = fp.as_of_qidx.values.astype("int64") * 10000000 + fp.mgrno.values.astype("int64")
    fpi = fp.set_index("k")
    del fp

    # ---- PIT accumulators for the manager-history score
    NM = 200000
    mgr_sum = np.zeros((NM, 4)); mgr_cnt = np.zeros((NM, 4))
    pool_sum = np.zeros(4); pool_cnt = np.zeros(4)
    mgr_index: dict[int, int] = {}
    pending: deque = deque()

    per_q = []          # one dict of per-quarter statistics
    files = sorted(TRANS_DIR.glob("q*.parquet"))
    diag = {"quarters": 0, "transitions_read": 0, "events": {e: 0 for e in ETYPES},
            "events_with_primary_return": 0, "events_dropped_no_return": 0}

    for f in files:
        q = int(f.stem[1:])
        if not (qidx_of(start_year, 1) <= q <= qidx_of(end_year, 4)):
            continue
        t = pd.read_parquet(f)
        diag["transitions_read"] += len(t)
        et = classify(t)
        t = t[et >= 0].reset_index(drop=True)
        et = et[et >= 0]
        if len(t) == 0:
            continue
        for i, e in enumerate(ETYPES):
            diag["events"][e] += int((et == i).sum())

        # ---- PIT public date -> first trading close on/after
        pub = np.array([np.datetime64(public_date_of(int(x)), "D")
                        for x in t.public_qidx.values])
        di = crsp.dayidx_on_or_after(pub)
        # PIT self-check: the return clock never starts before the statutory
        # deadline of the report quarter. A regression here is a leak.
        qe = np.datetime64(public_date_of(q), "D") - np.timedelta64(45, "D")
        okdi = di < len(crsp.cal)
        if okdi.any():
            lagd = (crsp.cal[di[okdi]] - qe).astype("timedelta64[D]").astype(int)
            diag["min_days_quarter_end_to_return_start"] = min(
                diag.get("min_days_quarter_end_to_return_start", 10**9), int(lagd.min()))
            diag["max_days_quarter_end_to_return_start"] = max(
                diag.get("max_days_quarter_end_to_return_start", -1), int(lagd.max()))

        # ---- forward excess returns
        cols = {}
        for name, h in HORIZONS.items():
            ex, raw, _ = crsp.forward_excess(t.permno.values.astype("int32"), di, h, "ew")
            cols[f"exc_{name}_ew"] = ex
            cols[f"raw_{name}"] = raw
        exv, _, _ = crsp.forward_excess(t.permno.values.astype("int32"), di,
                                        HORIZONS[PRIMARY], "vw")
        cols[f"exc_{PRIMARY}_vw"] = exv

        # ---- controls at the report quarter-end
        k = np.int64(q) * 1000000 + t.permno.values.astype("int64")
        ctl = qsi.reindex(k)
        # ---- fingerprint (PIT: stamped for as_of_quarter q, built through q-1)
        fk = np.int64(q) * 10000000 + t.mgrno.values.astype("int64")
        fpr = fpi.reindex(fk)

        ev = pd.DataFrame({
            "mgrno": t.mgrno.values, "permno": t.permno.values,
            "qidx": np.int16(q), "public_qidx": t.public_qidx.values,
            "etype": et,
            "pct_co_now": t.pct_co_now.values, "pct_pf_now": t.pct_pf_now.values,
            "logcap": ctl.logcap.values, "mom_12_1": ctl.mom_12_1.values,
            "cap_tercile": ctl.cap_tercile.values,
            "dur_median_qtrs": fpr.dur_median_qtrs.values,
            "n_completed_spells": fpr.n_completed_spells.values,
            "n_quarters_filed": fpr.n_quarters_filed.values,
            **cols,
        })
        Q = fpr[QUANT_COLS].values
        ev["anomaly_pct"] = pct_rank_from_quantiles(ev.pct_co_now.values, Q)
        ev["anomaly_top_decile"] = (ev.pct_co_now.values >= Q[:, 4]) & np.isfinite(Q[:, 4])

        prim = ev[f"exc_{PRIMARY}_ew"].values
        diag["events_with_primary_return"] += int(np.isfinite(prim).sum())
        diag["events_dropped_no_return"] += int((~np.isfinite(prim)).sum())

        # ---- manager-history score (from resolved events only)
        mi = np.array([mgr_index.setdefault(int(m), len(mgr_index))
                       for m in ev.mgrno.values], dtype="int64")
        if mgr_index and max(mgr_index.values()) >= NM:
            raise RuntimeError("manager capacity exceeded")
        cnt = mgr_cnt[mi, et]
        own = np.where(cnt >= MIN_MGR_HISTORY, mgr_sum[mi, et] / np.maximum(cnt, 1), np.nan)
        base = np.where(pool_cnt[et] > 0, pool_sum[et] / np.maximum(pool_cnt[et], 1), np.nan)
        ev["mgr_score"] = own - base
        ev["mgr_score_n"] = cnt
        ev["type_base_rate"] = base

        slim = ev[["mgrno", "permno", "qidx", "etype", f"exc_{PRIMARY}_ew",
                   "exc_h252_ew", "pct_co_now", "pct_pf_now", "anomaly_pct",
                   "anomaly_top_decile", "dur_median_qtrs", "mgr_score",
                   "cap_tercile"]].copy()
        for c in slim.columns:
            if slim[c].dtype == "float64":
                slim[c] = slim[c].astype("float32")
        slim.to_parquet(EVENTS_DIR / f"q{q:03d}.parquet", index=False)
        per_q.append(_quarter_stats(ev, q))
        diag["quarters"] += 1

        # ---- push this quarter's realised outcomes into the accumulators AFTER a
        #      lag long enough that the outcome was public before the next use.
        # the accumulated score uses the WINSORISED excess, matching the regression
        # target — an un-winsorised manager mean is one 400% name away from noise.
        pending.append((q, mi, et, winsor(prim)))
        while pending and pending[0][0] <= q - SCORE_LAG_Q:
            _, pmi, pet, pex = pending.popleft()
            ok = np.isfinite(pex)
            np.add.at(mgr_sum, (pmi[ok], pet[ok]), pex[ok])
            np.add.at(mgr_cnt, (pmi[ok], pet[ok]), 1.0)
            np.add.at(pool_sum, pet[ok], pex[ok])
            np.add.at(pool_cnt, pet[ok], 1.0)
        if verbose and q % 8 == 0:
            print(f"  {qlabel(q)} events={len(ev):7,d} scored="
                  f"{int(np.isfinite(ev.mgr_score.values).sum()):6,d}  {time.time()-t0:5.0f}s")

    diag["seconds"] = round(time.time() - t0, 1)
    return {"per_q": pd.DataFrame(per_q), "diag": diag}


# ---------------------------------------------------------------- per-quarter stats
def _quarter_stats(ev: pd.DataFrame, q: int) -> dict:
    out = {"qidx": q, "quarter": qlabel(q), "n_events": len(ev)}
    y_raw = ev[f"exc_{PRIMARY}_ew"].values.astype("float64")
    y = winsor(y_raw)
    out["mean_excess_all_events_raw"] = float(np.nanmean(y_raw)) if np.isfinite(y_raw).any() else np.nan
    out["mean_excess_all_events_wins"] = float(np.nanmean(y)) if np.isfinite(y).any() else np.nan
    for name in HORIZONS:
        v = ev[f"exc_{name}_ew"].values
        out[f"mean_excess_all_{name}"] = float(np.nanmean(v)) if np.isfinite(v).any() else np.nan
    v = ev[f"exc_{PRIMARY}_vw"].values
    out["mean_excess_all_vw"] = float(np.nanmean(v)) if np.isfinite(v).any() else np.nan

    et = ev.etype.values
    for i, e in enumerate(ETYPES):
        m = et == i
        out[f"n_{e}"] = int(m.sum())
        out[f"mean_excess_{e}"] = float(np.nanmean(y[m])) if m.sum() and np.isfinite(y[m]).any() else np.nan
        out[f"mean_excess_raw_{e}"] = float(np.nanmean(y_raw[m])) if m.sum() and np.isfinite(y_raw[m]).any() else np.nan

    # ---------------- H2: Fama-MacBeth slope on the manager-history score
    sc = ev.mgr_score.values.astype("float64")
    lc = zscore(ev.logcap.values.astype("float64"))
    mo = zscore(winsor(ev.mom_12_1.values.astype("float64")))
    D = np.column_stack([et == 1, et == 2, et == 3]).astype("float64")
    use = np.isfinite(sc) & np.isfinite(y)
    out["n_h2_scored"] = int(use.sum())
    out["n_h2_managers"] = int(pd.unique(ev.mgrno.values[use]).size) if use.any() else 0
    out["h2_score_sd"] = float(np.nanstd(sc[use])) if use.sum() > 5 else np.nan
    if use.sum() >= 100:
        X = np.column_stack([np.ones(use.sum()), sc[use], lc[use], mo[use], D[use]])
        r = ols_coef(y[use], X)
        out["h2_beta"] = float(r[0][1]) if r else np.nan
        out["h2_n"] = int(r[1]) if r else 0
        # raw (unwinsorised) version
        r2 = ols_coef(y_raw[use], X)
        out["h2_beta_raw"] = float(r2[0][1]) if r2 else np.nan
        # no-control version, for the "is it just size/momentum?" question
        r3 = ols_coef(y[use], np.column_stack([np.ones(use.sum()), sc[use]]))
        out["h2_beta_nocontrol"] = float(r3[0][1]) if r3 else np.nan
        # tercile spread on the score
        s = sc[use]
        if len(s) >= 60:
            lo, hi = np.nanquantile(s, [1 / 3, 2 / 3])
            top, bot = y[use][s >= hi], y[use][s <= lo]
            if len(top) >= 10 and len(bot) >= 10:
                out["h2_tercile_spread"] = float(np.nanmean(top) - np.nanmean(bot))
    else:
        out["h2_beta"] = np.nan; out["h2_n"] = 0

    # ---------------- H3: duration tercile x event type
    dur = ev.dur_median_qtrs.values.astype("float64")
    ok_dur = np.isfinite(dur) & (ev.n_completed_spells.values >= MIN_SPELLS_FOR_DURATION)
    out["n_h3_managers_with_duration"] = int(pd.unique(ev.mgrno.values[ok_dur]).size)
    if ok_dur.sum() >= 60:
        lo, hi = np.nanquantile(dur[ok_dur], [1 / 3, 2 / 3])
        short = ok_dur & (dur <= lo)
        long_ = ok_dur & (dur >= hi)
        out["dur_tercile_cut_low"] = float(lo); out["dur_tercile_cut_high"] = float(hi)
        for i, e in [(0, "NEW_POSITION"), (3, "COMPLETE_EXIT"), (1, "LARGE_ADD"),
                     (2, "LARGE_TRIM")]:
            a = y[long_ & (et == i)]; b = y[short & (et == i)]
            na, nb = int(np.isfinite(a).sum()), int(np.isfinite(b).sum())
            out[f"h3_{e}_long_mean"] = float(np.nanmean(a)) if na >= 5 else np.nan
            out[f"h3_{e}_short_mean"] = float(np.nanmean(b)) if nb >= 5 else np.nan
            out[f"h3_{e}_spread"] = (out[f"h3_{e}_long_mean"] - out[f"h3_{e}_short_mean"]
                                     if na >= 5 and nb >= 5 else np.nan)
            out[f"h3_{e}_n_long"] = na; out[f"h3_{e}_n_short"] = nb

    # ---------------- ANOMALY: top-decile own-history position size vs matched
    has_q = ev.anomaly_pct.notna().values          # manager has a own-history ladder
    anom = ev.anomaly_top_decile.values.astype(bool) & has_q
    ordn = has_q & ~anom
    ct = ev.cap_tercile.values
    diffs, wa, wo = [], [], []
    for i in range(4):
        for c in (0.0, 1.0, 2.0):
            cell = (et == i) & (ct == c)
            a = y[cell & anom]; o = y[cell & ordn]
            if np.isfinite(a).sum() >= 5 and np.isfinite(o).sum() >= 5:
                diffs.append(np.nanmean(a) - np.nanmean(o))
                wa.append(np.nanmean(a)); wo.append(np.nanmean(o))
    out["anom_diff"] = float(np.mean(diffs)) if diffs else np.nan
    out["anom_mean"] = float(np.mean(wa)) if wa else np.nan
    out["anom_ordinary_mean"] = float(np.mean(wo)) if wo else np.nan
    out["n_anom_events"] = int(anom.sum())
    ya = y_raw[anom]
    if np.isfinite(ya).sum() >= 10:
        out["anom_frac_positive"] = float(np.nanmean(ya > 0))
        out["anom_p10"] = float(np.nanquantile(ya[np.isfinite(ya)], 0.10))
        out["anom_p90"] = float(np.nanquantile(ya[np.isfinite(ya)], 0.90))
    yo = y_raw[ordn]
    if np.isfinite(yo).sum() >= 10:
        out["ord_frac_positive"] = float(np.nanmean(yo > 0))
    return out


# ---------------------------------------------------------------- aggregation
def summarise(per_q: pd.DataFrame, diag: dict) -> dict:
    def block(df: pd.DataFrame, label: str) -> dict:
        if df.empty:
            return {"label": label, "n_quarters": 0}
        b = {"label": label, "n_quarters": int(len(df)),
             "n_events": int(df.n_events.sum()),
             "first_quarter": str(df.quarter.iloc[0]),
             "last_quarter": str(df.quarter.iloc[-1])}
        b["do_nothing_control_all_events_pooled"] = {
            "winsorised": tstat(df.mean_excess_all_events_wins.values),
            "raw": tstat(df.mean_excess_all_events_raw.values),
            "vw_benchmark": tstat(df.mean_excess_all_vw.values),
            "by_horizon": {h: tstat(df[f"mean_excess_all_{h}"].values) for h in HORIZONS},
        }
        b["by_event_type"] = {
            e: {"n_events": int(df[f"n_{e}"].sum()),
                "winsorised": tstat(df[f"mean_excess_{e}"].values),
                "raw": tstat(df[f"mean_excess_raw_{e}"].values)}
            for e in ETYPES}
        b["H2"] = {
            "fama_macbeth_beta_on_manager_history_score": tstat(df.h2_beta.values),
            "beta_raw_returns": tstat(df.h2_beta_raw.values),
            "beta_without_size_momentum_type_controls": tstat(df.h2_beta_nocontrol.values),
            "tercile_spread_top_minus_bottom": tstat(df.get(
                "h2_tercile_spread", pd.Series(dtype=float)).values),
            "mean_scored_events_per_quarter": float(np.nanmean(df.n_h2_scored.values)),
            "total_scored_events": int(np.nansum(df.n_h2_scored.values)),
            "mean_scored_managers_per_quarter": float(np.nanmean(df.n_h2_managers.values)),
            "mean_score_sd": float(np.nanmean(df.h2_score_sd.values)),
            "excess_per_1sd_of_score": (
                float(np.nanmean(df.h2_beta.values) * np.nanmean(df.h2_score_sd.values))
                if np.isfinite(df.h2_beta.values).any() else None),
        }
        h3 = {}
        for e in ETYPES:
            if f"h3_{e}_spread" in df:
                h3[e] = {
                    "long_minus_short_duration_spread": tstat(df[f"h3_{e}_spread"].values),
                    "long_duration_mean": tstat(df[f"h3_{e}_long_mean"].values),
                    "short_duration_mean": tstat(df[f"h3_{e}_short_mean"].values),
                    "mean_n_long_per_quarter": float(np.nanmean(df[f"h3_{e}_n_long"].values)),
                    "mean_n_short_per_quarter": float(np.nanmean(df[f"h3_{e}_n_short"].values)),
                }
        b["H3"] = h3
        if "dur_tercile_cut_low" in df:
            b["H3_duration_tercile_cuts_quarters"] = {
                "median_low_cut": float(np.nanmedian(df.dur_tercile_cut_low.values)),
                "median_high_cut": float(np.nanmedian(df.dur_tercile_cut_high.values)),
            }
        b["ANOMALY"] = {
            "top_decile_minus_matched_ordinary": tstat(df.anom_diff.values),
            "top_decile_mean": tstat(df.anom_mean.values),
            "matched_ordinary_mean": tstat(df.anom_ordinary_mean.values),
            "total_top_decile_events": int(np.nansum(df.n_anom_events.values)),
            "losers_and_winners": {
                "mean_fraction_positive_top_decile": float(np.nanmean(df.get(
                    "anom_frac_positive", pd.Series(dtype=float)).values)),
                "mean_fraction_positive_ordinary": float(np.nanmean(df.get(
                    "ord_frac_positive", pd.Series(dtype=float)).values)),
                "mean_p10_of_top_decile_excess": float(np.nanmean(df.get(
                    "anom_p10", pd.Series(dtype=float)).values)),
                "mean_p90_of_top_decile_excess": float(np.nanmean(df.get(
                    "anom_p90", pd.Series(dtype=float)).values)),
            },
        }
        return b

    per_q = per_q.sort_values("qidx").reset_index(drop=True)
    yr = Q0_YEAR + per_q.qidx.values // 4
    return {
        "PRE_REGISTRATION": PREREG,
        "run": {"built_at": pd.Timestamp.utcnow().isoformat(),
                "receipt": str(RECEIPT.relative_to(ROOT)).replace("\\", "/"),
                "events_cache": str(EVENTS_DIR.relative_to(ROOT)).replace("\\", "/")},
        "scale": {
            "quarters": int(len(per_q)),
            "total_events": int(per_q.n_events.sum()),
            "events_by_type": {e: int(per_q[f"n_{e}"].sum()) for e in ETYPES},
            "diagnostics": diag,
        },
        "FULL_SAMPLE": block(per_q, "1996-2024 (full)"),
        "SUBPERIOD_1996_2012": block(per_q[yr <= 2012], "1996-2012"),
        "SUBPERIOD_2013_2024": block(per_q[yr >= 2013], "2013-2024"),
        "per_quarter_primary": per_q[[c for c in [
            "quarter", "n_events", "mean_excess_all_events_wins", "h2_beta",
            "h3_NEW_POSITION_spread", "h3_COMPLETE_EXIT_spread", "anom_diff"]
            if c in per_q.columns]].round(6).to_dict(orient="records"),
    }




# ---------------------------------------------------------------- caveats
# Design-level, fixed, and true regardless of what the numbers came out as.
CAVEATS = {
    "the_benchmark_is_the_biggest_one":
        "The pooled EW-market excess is the SAME (-1.8% to -2.1% at 63 sessions) "
        "for all four event types, including two that are opposite trades, while "
        "the pooled VW excess is ~0. That is a SIZE/BENCHMARK artefact: 13F-held "
        "names are large and the equal-weighted screened universe is not. Read NO "
        "level from this run. Only matched DIFFERENCES survive it -- long-vs-short "
        "duration inside a cap tercile, anomaly-vs-matched-ordinary inside a cap "
        "tercile, and the Fama-MacBeth slope with its log-cap control.",
    "the_universe_changes_at_2013":
        "The 13F pull used two CUSIP screens: 24,114 cusips for 1996-2012 (early "
        "universe) and 11,603 for 2013-2024 (v1, ~6,894 permnos). Event COUNTS are "
        "not comparable across sub-periods and a sub-period difference could be a "
        "universe difference. The split is a regime CHECK, not a clean regime TEST.",
    "duration_is_integer_and_piles_low":
        "Median completed holding duration is integer-valued in quarters with "
        "p50 = 2, so a TERCILE split separates '<=2 quarters' from '>=3 quarters' "
        "-- a one-quarter contrast. The primary H3 null at that resolution is "
        "close to uninformative; the addendum's >=6 vs <=1 quarter split is the "
        "contrast that actually tests the hypothesis.",
    "long_duration_is_confounded_with_indexing":
        "The longest-duration filers here are Vanguard, Geode, Northern Trust and "
        "State Street -- index complexes. A NEW_POSITION by a long-duration filer "
        "is disproportionately an INDEX ADDITION, and index additions are known to "
        "underperform after the event. Any H3 entry result is consistent with that "
        "mechanism and establishes NOTHING about discretionary conviction. "
        "Separating the two needs the 13D/13G ingest that idea doc 4a places "
        "outside entitled WRDS.",
    "no_filing_timestamp_exists":
        "tr_13f.s34 carries no SEC filing date; fdate is Thomson's VINTAGE "
        "quarter. The public date is quarter_end(max(rdate, first vintage)) + 45 "
        "days -- conservative but coarse. See diagnostics "
        "min/max_days_quarter_end_to_return_start for the realised spread.",
    "delisting_and_survivorship":
        "CRSP delisting returns are compounded into each permno's final "
        "observation, so an exit ahead of a delisting is scored against the real "
        "terminal return. The CRSP files themselves cover a pre-screened universe, "
        "not the whole tape.",
    "costs":
        "GROSS. No commission, spread, impact or borrow anywhere in this receipt.",
    "clustering":
        "Within a quarter, events cluster by manager and by name and the "
        "cross-sectional standard errors are NOT adjusted for that. The reported t "
        "is computed ACROSS QUARTERS (n_effective = date blocks, canon 58), and a "
        "Newey-West(4) t is printed beside every simple t.",
    "sic_is_not_time_varying":
        "Fingerprint sector entropy uses the LAST siccd per permno from dsenames, "
        "not the SIC in force at the quarter.",
}


def _fmt(d):
    if not d or d.get("mean") is None:
        return "n/a"
    return (f"{d['mean']:+.5f} (t {d['t']:+.2f}, NW4 "
            f"{d['t_newey_west_4'] if d['t_newey_west_4'] is not None else float('nan'):+.2f}, "
            f"{d['n_quarters']} quarters)")


def verdicts(out: dict) -> dict:
    """Generated from the computed statistics, so it cannot go stale on a re-run."""
    F, A, B = out["FULL_SAMPLE"], out["SUBPERIOD_1996_2012"], out["SUBPERIOD_2013_2024"]
    ad = out.get("ADDENDUM_EXTREME_DURATION_AND_SIZE_NEUTRAL", {})
    adF = ad.get("FULL_SAMPLE", {})
    dc = F["do_nothing_control_all_events_pooled"]
    v = {
        "do_nothing_control":
            f"All {F['n_events']:,} events pooled: EW-excess {_fmt(dc['winsorised'])}, "
            f"VW-excess {_fmt(dc['vw_benchmark'])}. The control IS the finding -- 13F "
            "events as a class carry no value-weighted-relative return, and any level "
            "quoted against the equal-weighted universe is a size artefact.",
        "H2_manager_identity":
            "Fama-MacBeth slope on the filer's own PIT post-event history "
            f"{_fmt(F['H2']['fama_macbeth_beta_on_manager_history_score'])} full sample; "
            f"{_fmt(A['H2']['fama_macbeth_beta_on_manager_history_score'])} in 1996-2012 and "
            f"{_fmt(B['H2']['fama_macbeth_beta_on_manager_history_score'])} in 2013-2024. "
            f"Tercile spread {_fmt(F['H2']['tercile_spread_top_minus_bottom'])}. "
            f"Economic size {F['H2']['excess_per_1sd_of_score']:+.5f} of 63-session excess "
            "per 1sd of score.",
        "H3_holding_duration_interaction":
            "Tercile split (a one-quarter contrast): "
            + "; ".join(f"{e} {_fmt(F['H3'][e]['long_minus_short_duration_spread'])}"
                        for e in ETYPES if e in F["H3"])
            + ". Extreme split (>=6 vs <=1 quarter), size-neutral: "
            + "; ".join(f"{e} {_fmt(adF.get(e, {}).get('long_minus_short_63s_SIZE_NEUTRAL'))}"
                        for e in ETYPES if e in adF)
            + ". At 252 sessions: "
            + "; ".join(f"{e} {_fmt(adF.get(e, {}).get('long_minus_short_252s'))}"
                        for e in ETYPES if e in adF),
        "ANOMALY_H6_prep":
            f"Top decile of the manager's OWN stake-size history vs matched ordinary "
            f"(same quarter, type and cap tercile): 63 sessions "
            f"{_fmt(F['ANOMALY']['top_decile_minus_matched_ordinary'])}; 252 sessions "
            f"size-neutral {_fmt(adF.get('ANOMALY_252s_size_neutral'))}. "
            f"Losers and winners: {F['ANOMALY']['losers_and_winners']}.",
    }
    return v


# ---------------------------------------------------------------- addendum
# Two things the primary run made suspicious, so we run the controls we would
# not have chosen (feedback-run-the-control-you-would-not-have-chosen):
#
#  1. The H3 duration terciles land 2 quarters vs 3 quarters apart. Median
#     holding duration is INTEGER-valued and piles on 1-3, so a tercile split is
#     a one-quarter contrast — a null there may be resolution, not absence.
#     The extreme split is >= 6 quarters (18 months) vs <= 1 quarter.
#  2. The pooled EW-market excess is -2.0% for EVERY event type alike, while the
#     VW excess is ~0. That is the signature of a SIZE/BENCHMARK artefact: 13F
#     names are large, the EW universe is not. Group DIFFERENCES are the robust
#     statistic, and they are recomputed inside market-cap terciles.
DUR_LONG_MIN_QTRS = 6
DUR_SHORT_MAX_QTRS = 1


def addendum_from_cache(verbose=True) -> dict:
    files = sorted(EVENTS_DIR.glob("q*.parquet"))
    rows = []
    for f in files:
        e = pd.read_parquet(f, columns=["qidx", "etype", "exc_h63_ew", "exc_h252_ew",
                                        "dur_median_qtrs", "cap_tercile",
                                        "anomaly_top_decile", "anomaly_pct"])
        q = int(f.stem[1:])
        y = winsor(e.exc_h63_ew.values.astype("float64"))
        y252 = winsor(e.exc_h252_ew.values.astype("float64"))
        d = e.dur_median_qtrs.values
        ct = e.cap_tercile.values
        et = e.etype.values
        long_ = d >= DUR_LONG_MIN_QTRS
        short = d <= DUR_SHORT_MAX_QTRS
        r = {"qidx": q, "quarter": qlabel(q),
             "n_long": int(long_.sum()), "n_short": int(short.sum()),
             "mean_dur_long": float(np.nanmean(d[long_])) if long_.any() else np.nan,
             "mean_dur_short": float(np.nanmean(d[short])) if short.any() else np.nan}
        for i, name in enumerate(ETYPES):
            for tag, yy in (("", y), ("_h252", y252)):
                a, b = yy[long_ & (et == i)], yy[short & (et == i)]
                na, nb = int(np.isfinite(a).sum()), int(np.isfinite(b).sum())
                r[f"ext_{name}{tag}_spread"] = (float(np.nanmean(a) - np.nanmean(b))
                                                if na >= 20 and nb >= 20 else np.nan)
                if not tag:
                    r[f"ext_{name}_long_mean"] = float(np.nanmean(a)) if na >= 20 else np.nan
                    r[f"ext_{name}_short_mean"] = float(np.nanmean(b)) if nb >= 20 else np.nan
                    r[f"ext_{name}_n_long"] = na
                    r[f"ext_{name}_n_short"] = nb
            # size-neutral: same spread computed inside each cap tercile, averaged
            cells = []
            for c in (0.0, 1.0, 2.0):
                a = y[long_ & (et == i) & (ct == c)]
                b = y[short & (et == i) & (ct == c)]
                if np.isfinite(a).sum() >= 20 and np.isfinite(b).sum() >= 20:
                    cells.append(np.nanmean(a) - np.nanmean(b))
            r[f"ext_{name}_spread_size_neutral"] = float(np.mean(cells)) if cells else np.nan
        # anomaly, size-neutral, at 252 sessions as well
        has = np.isfinite(e.anomaly_pct.values)
        an = e.anomaly_top_decile.values.astype(bool) & has
        cells252 = []
        for i in range(4):
            for c in (0.0, 1.0, 2.0):
                cell = (et == i) & (ct == c)
                a, b = y252[cell & an], y252[cell & has & ~an]
                if np.isfinite(a).sum() >= 20 and np.isfinite(b).sum() >= 20:
                    cells252.append(np.nanmean(a) - np.nanmean(b))
        r["anom_diff_h252"] = float(np.mean(cells252)) if cells252 else np.nan
        rows.append(r)
    df = pd.DataFrame(rows).sort_values("qidx").reset_index(drop=True)
    yr = Q0_YEAR + df.qidx.values // 4

    def blk(d, label):
        if d.empty:
            return {"label": label, "n_quarters": 0}
        o = {"label": label, "n_quarters": int(len(d)),
             "mean_duration_long_group_qtrs": float(np.nanmean(d.mean_dur_long.values)),
             "mean_duration_short_group_qtrs": float(np.nanmean(d.mean_dur_short.values)),
             "mean_n_long_per_quarter": float(np.nanmean(d.n_long.values)),
             "mean_n_short_per_quarter": float(np.nanmean(d.n_short.values))}
        for name in ETYPES:
            o[name] = {
                "long_minus_short_63s": tstat(d[f"ext_{name}_spread"].values),
                "long_minus_short_63s_SIZE_NEUTRAL":
                    tstat(d[f"ext_{name}_spread_size_neutral"].values),
                "long_minus_short_252s": tstat(d[f"ext_{name}_h252_spread"].values),
                "long_group_mean_63s": tstat(d[f"ext_{name}_long_mean"].values),
                "short_group_mean_63s": tstat(d[f"ext_{name}_short_mean"].values),
            }
        o["ANOMALY_252s_size_neutral"] = tstat(d.anom_diff_h252.values)
        return o

    return {
        "why": "the primary H3 terciles were only 2 vs 3 quarters apart (median "
               "duration is integer-valued and piles on 1-3), and the pooled EW "
               "excess is -2.0% for every event type alike — a size/benchmark "
               "artefact. This addendum widens the duration contrast to "
               f">= {DUR_LONG_MIN_QTRS} quarters vs <= {DUR_SHORT_MAX_QTRS} quarter "
               "and recomputes every spread inside market-cap terciles.",
        "FULL_SAMPLE": blk(df, "1996-2024"),
        "SUBPERIOD_1996_2012": blk(df[yr <= 2012], "1996-2012"),
        "SUBPERIOD_2013_2024": blk(df[yr >= 2013], "2013-2024"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=1996)
    ap.add_argument("--end-year", type=int, default=2024)
    ap.add_argument("--addendum-only", action="store_true",
                    help="recompute only the extreme-duration / size-neutral addendum "
                         "from the cached events, and patch it into the receipt")
    a = ap.parse_args()
    if a.addendum_only:
        out = json.loads(RECEIPT.read_text(encoding="utf-8"))
        out["ADDENDUM_EXTREME_DURATION_AND_SIZE_NEUTRAL"] = addendum_from_cache()
        out["CAVEATS"] = CAVEATS
        out["VERDICTS"] = verdicts(out)
        RECEIPT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(json.dumps(out["ADDENDUM_EXTREME_DURATION_AND_SIZE_NEUTRAL"],
                         indent=2, default=str))
        print("receipt ->", RECEIPT)
        return
    res = run(a.start_year, a.end_year)
    out = summarise(res["per_q"], res["diag"])
    out["ADDENDUM_EXTREME_DURATION_AND_SIZE_NEUTRAL"] = addendum_from_cache()
    out["CAVEATS"] = CAVEATS
    out["VERDICTS"] = verdicts(out)
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ["scale"]}, indent=2, default=str))
    for k in ["FULL_SAMPLE", "SUBPERIOD_1996_2012", "SUBPERIOD_2013_2024"]:
        print(f"\n===== {k} =====")
        print(json.dumps({kk: out[k][kk] for kk in out[k]
                          if kk in ("label", "n_quarters", "n_events",
                                    "do_nothing_control_all_events_pooled",
                                    "by_event_type", "H2", "H3", "ANOMALY")},
                         indent=2, default=str))
    print("\nreceipt ->", RECEIPT)


if __name__ == "__main__":
    main()
