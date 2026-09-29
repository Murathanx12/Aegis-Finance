"""Sizing on the size of the move (2026-09-29): can a direction-free size forecast raise
terminal wealth or log utility?

    python -m scripts.sizing_lab --part library      # experiments 1 + 3 on the library panel (2017-2026)
    python -m scripts.sizing_lab --part crsp         # experiments 2 + 4 (+ 1/3 foreign slice), CRSP 2013-2024
    python -m scripts.sizing_lab --part all

Licence PRODUCT_EXPERIMENT. $0: no LLM, no broker, no network (SPY is built from the bars,
`spy_leg(network=False)`). Costs are ALWAYS on (the library's band toll; `run_book` refuses
zero costs). Pure pieces and the declared verdict rule live in
`backend/services/move_size_sizing.py`.

Writes, under `backend/data/optimus/sizing_lab/`, one receipt per part with the run id in
the file name (`sizing_<part>_<run_id>.json`) and the monthly series beside it
(`sizing_<part>_monthly_<run_id>.parquet`, gitignored). Never overwrites: an existing
receipt path refuses. Local caches (gitignored) go to `local_pc/sizing_lab/`.

PANELS
* library: `night_backtest_factory.load_wide` + `build_panel` over
  `xs_ranker.survivorship_free_paths()` (living + delisted bars, reused tickers cut by
  `stitched_tickers.cut_reader_bars`), month-end decisions, entry at the next session's
  open, delisting fill -30%. Still partially survivor-selected (living names chosen alive
  2026-09-01; dead names from the inactive listed list only) -- printed on the receipt.
* crsp: CRSP daily 2012-2024 for every permno ever eligible in `crsp_pit_monthly_v1`
  (price >= $5, >= $100M/month dollar volume), delisting returns from `dsedelist`,
  Compustat `rdq` for earnings dates (via CCM), OptionMetrics 30-day ATM implied vol
  (via the OptionMetrics-CRSP link). Survivorship-free by construction.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                              # noqa: E402
from backend.services import move_size_sizing as MS             # noqa: E402

OPT = REPO / "backend" / "data" / "optimus"
OUT = OPT / "sizing_lab"
CACHE = OPT / "local_pc" / "sizing_lab"
K = 20
N_RANDOM_SEEDS = 20
QUARTER_OFFSETS = {"jajo": (1, 4, 7, 10), "fman": (2, 5, 8, 11), "mjsd": (3, 6, 9, 12)}

#: the size model's inputs on the library panel (all known at the decision close)
LIB_SPEC = {"vol_21": "log", "vol_63": "log", "vol_252": "log", "idio_vol_63": "log",
            "max_ret_21": "abslog", "amihud": "raw", "dollar_vol_log": "raw", "beta_252": "raw",
            "skew_63": "raw", "turnover_surge": "raw", "mom_21": "abs", "mom_252": "abslog",
            "close": "log"}


def peak_rss_mb():
    try:
        class PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("a", ctypes.c_size_t), ("b", ctypes.c_size_t), ("c", ctypes.c_size_t),
                        ("d", ctypes.c_size_t), ("e", ctypes.c_size_t), ("f", ctypes.c_size_t)]
        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        fn = k32.K32GetProcessMemoryInfo
        fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
        if fn(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return round(c.PeakWorkingSetSize / 1e6, 1)
    except Exception:                                   # noqa: BLE001 -- not Windows
        return None
    return None


def rnd(o, nd: int = 6):
    if isinstance(o, (float, np.floating)):
        o = float(o)
        return round(o, nd) if math.isfinite(o) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, dict):
        return {str(k): rnd(v, nd) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [rnd(v, nd) for v in o]
    return o


def band_costs() -> dict:
    from backend.services import xs_ranker as XR
    c = dict(XR.COST_BPS_BY_BAND)
    # the farm's zero-cost refusal, inherited (strategy_library.check_costs builds a Policy)
    from backend.services import strategy_library as SL
    SL.check_costs(1.0, False)
    return c


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def say(*a):
    print(*a, flush=True)


# ═════════════════════════ shared: the size-input book family ════════════════

def per_date_kappa(panel: pd.DataFrame, col: str, realised: str, mask: np.ndarray, gap: int = 2) -> pd.Series:
    """Walk-forward kappa_t = MS.calibrate_scale over dates <= t - gap (mean absolute,
    expanding window): sigma_t = kappa_t * size, in monthly return units."""
    dates = np.sort(panel["date"].unique())
    di = np.searchsorted(dates, panel["date"].to_numpy())
    x = panel[col].to_numpy(dtype=float)
    r = panel[realised].to_numpy(dtype=float)
    ok = mask & np.isfinite(x) & np.isfinite(r) & (x > 0)
    s_r = np.bincount(di[ok], weights=np.abs(r[ok]), minlength=len(dates))
    s_x = np.bincount(di[ok], weights=x[ok], minlength=len(dates))
    cr, cx = np.cumsum(s_r), np.cumsum(s_x)
    kap = np.full(len(dates), np.nan)
    for j in range(len(dates)):
        lt = j - gap
        if lt >= 5 and cx[lt] > 0:
            kap[j] = math.sqrt(math.pi / 2.0) * cr[lt] / cx[lt]
    return pd.Series(kap[di], index=panel.index)


def book_family(panel: pd.DataFrame, scores: np.ndarray, *, costs: dict, size_cols: dict,
                sigma_cols: dict, start_date, months=None, hold_months: int = 3) -> dict:
    """For one selection rule: {variant: {offset: monthly net Series}}.

    Variants: equal; inv_<x> (w ~ 1/x, cap 10%); kelly_<x> (w ~ 1/sigma^2, g = half-Kelly on
    a FIXED assumed edge); vt_<x> (w ~ 1/sigma, g = 15%/yr vol target). Every variant sees
    the SAME names on the SAME calendar -- only the size input differs."""
    arrays = {k: panel[c].to_numpy(dtype=float) for k, c in size_cols.items()}
    sig = {k: panel[c].to_numpy(dtype=float) for k, c in sigma_cols.items()}
    variants = {"equal": (None, None)}
    for k, a in arrays.items():
        variants[f"inv_{k}"] = ((lambda idx, a=a: MS.inverse_size_weights(a[idx])), None)
    for k, s in sig.items():
        variants[f"kelly_{k}"] = ((lambda idx, s=s: MS.inverse_size_weights(s[idx], power=2.0)),
                                  (lambda idx, w, s=s: MS.kelly_gross(w, _fill(s[idx]))))
        variants[f"vt_{k}"] = ((lambda idx, s=s: MS.inverse_size_weights(s[idx])),
                               (lambda idx, w, s=s: MS.vol_target_gross(w, _fill(s[idx]))))
    offs = QUARTER_OFFSETS if months is None else months
    out = {}
    for v, (wf, gf) in variants.items():
        out[v] = {}
        for tag, rm in offs.items():
            m = MS.run_book(panel, scores, k=K, costs=costs, rebalance_months=rm, hold_months=hold_months,
                            weight_fn=wf, gross_fn=gf, start_date=start_date)
            out[v][tag] = m.set_index("date")
    return out


def _fill(s: np.ndarray) -> np.ndarray:
    ok = np.isfinite(s) & (s > 0)
    return np.where(ok, s, np.median(s[ok]) if ok.any() else np.nan)


def family_tranche(fam: dict, field: str = "net") -> dict:
    return {v: MS.tranche({t: df[field] for t, df in offs.items()}) for v, offs in fam.items()}


COMPARISONS = (
    # (variant, twin, question)
    ("inv_ridgeqm", "inv_vol", "Q1 PRIMARY (b) vs (a), dispersion held equal: ridge ranks on trailing vol's "
                               "per-date distribution vs trailing vol (added after the first read showed the "
                               "raw ridge compresses weight dispersion)"),
    ("inv_ridge", "inv_vol", "Q1 (b) vs (a): inverse size, raw ridge forecast vs trailing vol"),
    ("inv_vol", "equal", "Q1 (a) vs equal weight"),
    ("inv_ridge", "equal", "Q1 (b) vs equal weight"),
    ("kelly_ridgeqm", "kelly_vol", "Q3 PRIMARY half-Kelly on a fixed edge, dispersion held equal"),
    ("kelly_ridge", "kelly_vol", "Q3 half-Kelly on a fixed edge: better variance forecast vs trailing vol"),
    ("vt_ridgeqm", "vt_vol", "Q3 15% vol target, dispersion held equal"),
    ("vt_ridge", "vt_vol", "Q3 15% vol target: better forecast vs trailing vol"),
    ("kelly_vol", "equal", "Q3 half-Kelly (trailing vol) vs fully invested equal weight"),
)


WINSOR_CMP = (
    ("inv_ridgeqmw", "inv_volw", "Q1 winsorised inputs (1%/99% per date), dispersion held equal"),
    ("kelly_ridgeqmw", "kelly_volw", "Q3 half-Kelly, winsorised inputs, dispersion held equal"),
    ("vt_ridgeqmw", "vt_volw", "Q3 vol target, winsorised inputs, dispersion held equal"),
)
DEFECT_VOL = 3.0
DEFECT_MOM = 20.0


def top20_defect_slots(panel, mom, scr) -> dict:
    d = panel.assign(_m=mom, _ok=scr)
    d = d[np.isfinite(d["_m"])].sort_values(["date", "_m"], ascending=[True, False]).groupby("date").head(K)
    return {"slots": int(len(d)), "defective": int((~d["_ok"]).sum())}


def read_family(tr_rule: dict, tr_rand: dict, market: pd.Series, extra_cmp=()) -> dict:
    res = {}
    for v, t, q in tuple(COMPARISONS) + tuple(extra_cmp):
        if v not in tr_rule or t not in tr_rule:
            continue
        r = {"question": q, "mom_12_1_q_tranche": MS.diff_report(tr_rule[v], tr_rule[t], market)}
        if tr_rand:
            r["random_control"] = MS.seed_diff_report({s: d[v] for s, d in tr_rand.items()},
                                                      {s: d[t] for s, d in tr_rand.items()}, market)
        res[f"{v}_minus_{t}"] = r
    return res


def book_table(tr_rule: dict, tr_rand: dict) -> dict:
    out = {}
    for v, s in tr_rule.items():
        m = MS.book_metrics(s)
        row = {"mom_12_1_q": m}
        if tr_rand:
            per = [MS.book_metrics(d[v]) for d in tr_rand.values()]
            row["random_median"] = {k: float(np.median([p[k] for p in per if p.get(k) is not None]))
                                    for k in ("cagr", "vol_annual", "sharpe", "max_dd", "terminal_wealth",
                                              "log_utility_monthly")}
        out[v] = row
    return out


# ═════════════════════════ part: library (experiments 1 + 3) ═════════════════

def load_library_panel() -> tuple[pd.DataFrame, pd.Series, dict]:
    from scripts import night_backtest_factory as F
    from backend.services import xs_ranker as XR
    import pyarrow.parquet as pq
    CACHE.mkdir(parents=True, exist_ok=True)
    paths = XR.survivorship_free_paths()
    sizes = {p.name: int(pq.ParquetFile(p).metadata.num_rows) for p in paths}
    stamp = "_".join(f"{v}" for v in sizes.values())
    cp = CACHE / f"library_panel_{stamp}.parquet"
    sp = CACHE / f"library_spy_{stamp}.parquet"
    meta = {"bars": sizes, "paths": [str(p.relative_to(REPO)).replace("\\", "/") for p in paths],
            "delist_return": float(_cfg.STRATEGY_LIB_DELIST_RETURN), "start": _cfg.STRATEGY_LIB_START,
            "stitched": "reused tickers cut by stitched_tickers.cut_reader_bars inside load_wide"}
    if cp.exists() and sp.exists():
        say(f"  library panel from cache {cp.name}")
        return pd.read_parquet(cp), pd.read_parquet(sp)["spy"], meta | {"cache": cp.name}
    W = F.load_wide(paths, start=_cfg.STRATEGY_LIB_START)
    panel = F.build_panel(W, delist_return=float(_cfg.STRATEGY_LIB_DELIST_RETURN))
    spy, spy_meta = F.spy_leg(panel, W, network=False)
    del W
    keep = ["date", "symbol", "eligible", "median_dollar_vol", "fwd_ret", "delisted_in_period",
            "is_month_end", "mom_252_21"] + [c for c in LIB_SPEC if c not in ("mom_252_21",)]
    keep = list(dict.fromkeys(c for c in keep if c in panel.columns))
    panel = panel.loc[panel["is_month_end"], keep].reset_index(drop=True)
    from backend.services import strategy_library as SL
    panel["tiebreak"] = SL._tiebreak(panel)
    panel.to_parquet(cp, index=False)
    pd.DataFrame({"spy": spy}).to_parquet(sp)
    return panel, spy, meta | {"spy": spy_meta.get("source"), "cache_written": cp.name}


def part_library(run_id: str) -> dict:
    t0 = time.time()
    costs = band_costs()
    panel, spy, meta = load_library_panel()
    say(f"  panel {len(panel):,} rows, {panel['date'].nunique()} dates, {panel['symbol'].nunique()} symbols; "
        f"dead-in-period rows {int(panel['delisted_in_period'].sum())}; {time.time()-t0:.0f}s peak {peak_rss_mb()} MB")
    elig = panel["eligible"].to_numpy(dtype=bool)
    panel["abs_x"] = MS.abs_excess(panel)
    panel["abs_r"] = panel["fwd_ret"].abs()
    # (b) the better size forecast: walk-forward ridge on |excess|, gap 2 decision dates
    panel["size_ridge"], fitlog = MS.walk_forward_size(panel, LIB_SPEC, target="abs_x", train_mask=elig,
                                                       gap=2, min_train_dates=12)
    panel["size_vol"] = panel["vol_63"]
    first = panel.loc[panel["size_ridge"].notna(), "date"].min()
    say(f"  ridge size forecast from {pd.Timestamp(first).date()} ({len(fitlog)} fits); {time.time()-t0:.0f}s")
    # forecast quality on eligible names, per date
    m_ok = elig & panel["size_ridge"].notna().to_numpy() & panel["abs_x"].notna().to_numpy()
    ic_r = MS.per_date_ic(panel, "size_ridge", "abs_x", mask=m_ok)
    ic_v = MS.per_date_ic(panel, "size_vol", "abs_x", mask=m_ok)
    qual = {"ic_ridge_mean": float(ic_r.mean()), "ic_vol_mean": float(ic_v.mean()),
            "ridge_minus_vol": MS.block_stats(ic_r - ic_v, 1),
            "ridge_minus_vol_by_hold_year": MS.by_hold_year(ic_r - ic_v),
            "n_dates": int(len(ic_r)),
            "note": "Spearman of the forecast with next month's |excess over the median|, eligible names; "
                    "SE on single-month blocks (the target windows do not overlap)"}
    say(f"  size IC: ridge {qual['ic_ridge_mean']:.4f} vs vol_63 {qual['ic_vol_mean']:.4f}; "
        f"diff t {qual['ridge_minus_vol']['t_blocks']}")
    # sigma in monthly return units, calibrated walk-forward the SAME way for both inputs
    qm_mask = elig & panel["size_ridge"].notna().to_numpy()
    panel["size_ridgeqm"] = MS.quantile_map(panel, "size_ridge", "size_vol", qm_mask)
    # winsorised inputs (per date, eligible names, 1% / 99%): the SAME clip for both, so a
    # few defective bars cannot set the book's sigma (added after the second read)
    q = panel.loc[elig].groupby("date")["size_vol"].quantile([0.01, 0.99]).unstack()
    lo = panel["date"].map(q[0.01]).to_numpy(dtype=float)
    hi = panel["date"].map(q[0.99]).to_numpy(dtype=float)
    panel["size_volw"] = np.clip(panel["size_vol"].to_numpy(dtype=float), lo, hi)
    panel["size_ridgeqmw"] = MS.quantile_map(panel, "size_ridge", "size_volw", qm_mask)
    for c in ("volw", "ridgeqmw"):
        panel[f"kap_{c}"] = per_date_kappa(panel, f"size_{c}", "fwd_ret", elig)
        panel[f"sig_{c}"] = panel[f"kap_{c}"] * panel[f"size_{c}"]
    panel["kap_vol"] = per_date_kappa(panel, "size_vol", "fwd_ret", elig)
    panel["kap_ridgeqm"] = per_date_kappa(panel, "size_ridgeqm", "fwd_ret", elig)
    panel["sig_ridgeqm"] = panel["kap_ridgeqm"] * panel["size_ridgeqm"]
    panel["kap_ridge"] = per_date_kappa(panel, "size_ridge", "fwd_ret", elig)
    panel["sig_vol"] = panel["kap_vol"] * panel["size_vol"]
    panel["sig_ridge"] = panel["kap_ridge"] * panel["size_ridge"]
    start = pd.Timestamp(first)
    sel_mask = elig & panel["size_ridge"].notna().to_numpy()
    mom = np.where(sel_mask, panel["mom_252_21"].to_numpy(dtype=float), np.nan)
    size_cols = {"vol": "size_vol", "ridge": "size_ridge", "ridgeqm": "size_ridgeqm",
                 "volw": "size_volw", "ridgeqmw": "size_ridgeqmw"}
    sigma_cols = {"vol": "sig_vol", "ridge": "sig_ridge", "ridgeqm": "sig_ridgeqm",
                  "volw": "sig_volw", "ridgeqmw": "sig_ridgeqmw"}
    fam_rule = book_family(panel, mom, costs=costs, size_cols=size_cols, sigma_cols=sigma_cols, start_date=start)
    say(f"  mom_12_1_q family done {time.time()-t0:.0f}s")
    # engine check: equal weight through run_book == strategy_library.run_strategy (same panel, same k)
    check = engine_check(panel, fam_rule, costs, start)
    say(f"  ENGINE CHECK vs run_strategy: {check}")
    from backend.services import strategy_library as SL
    rand = {}
    for sd in range(N_RANDOM_SEEDS):
        sc = SL.seeded_noise(1000 + sd)(panel).to_numpy(dtype=float)
        sc = np.where(sel_mask, sc, np.nan)
        rand[sd] = family_tranche(book_family(panel, sc, costs=costs, size_cols=size_cols,
                                              sigma_cols=sigma_cols, start_date=start))
    say(f"  random family ({N_RANDOM_SEEDS} seeds) done {time.time()-t0:.0f}s peak {peak_rss_mb()} MB")
    tr_rule = family_tranche(fam_rule)
    inv_rule = family_tranche(fam_rule, "invested")
    market = spy.reindex(tr_rule["equal"].index)
    results = read_family(tr_rule, rand, market, extra_cmp=WINSOR_CMP)
    # DEFECT SCREEN (declared after the second read): momentum's top 20 buys bar defects
    # (vol_63 up to 895 = 89,500%/yr, 12-1 momentum up to +46,000%); inverse vol zero-weights
    # them mechanically. The screened rule drops rows with vol_63 > 3 or |mom_252_21| > 20.
    scr = (panel["vol_63"].to_numpy(dtype=float) <= DEFECT_VOL) &           (np.abs(panel["mom_252_21"].to_numpy(dtype=float)) <= DEFECT_MOM)
    mom_s = np.where(scr, mom, np.nan)
    tr_s = family_tranche(book_family(panel, mom_s, costs=costs, size_cols=size_cols, sigma_cols=sigma_cols,
                                      start_date=start))
    results_screened = read_family(tr_s, {}, market, extra_cmp=WINSOR_CMP)
    screen_counts = {"eligible_rows_screened_out": int((elig & ~scr).sum()),
                     "mom_top20_slots_hit_by_defects": top20_defect_slots(panel, mom, scr)}
    say(f"  screened family done; {screen_counts}")
    # how different are the books? (a mechanical bound on any effect)
    diffw = weight_distance(panel, mom, costs, start)
    # exp 3 extras: does the forecast predict the BOOK's realised risk?
    risk_fit = book_risk_fit(panel, mom, costs, start)
    worst = latest_worst_case(panel, mom)
    series = pd.DataFrame({f"rule_{k}": v for k, v in tr_rule.items()} |
                          {f"rule_invested_{k}": v for k, v in inv_rule.items()} |
                          {f"rand_mean_{v}": pd.concat([d[v] for d in rand.values()], axis=1).mean(axis=1)
                           for v in tr_rule} | {"spy": market})
    return {"meta": meta, "panel": {"rows": int(len(panel)), "dates": int(panel["date"].nunique()),
                                    "symbols": int(panel["symbol"].nunique()),
                                    "first": str(panel["date"].min().date()), "last": str(panel["date"].max().date()),
                                    "dead_in_period_rows": int(panel["delisted_in_period"].sum())},
            "size_model": {"spec": LIB_SPEC, "target": "|fwd_ret - date median| (eligible)", "gap_dates": 2,
                           "min_train_dates": 12, "refit": "every decision date", "alpha": 10.0,
                           "n_fits": len(fitlog), "first_forecast": str(start.date()),
                           "last_fit": fitlog[-1] if fitlog else None},
            "forecast_quality": qual, "engine_check": check,
            "books": book_table(tr_rule, rand), "comparisons": results,
            "defect_screen": {"rule": f"drop vol_63 > {DEFECT_VOL} or |mom_252_21| > {DEFECT_MOM}",
                              "counts": screen_counts, "books": book_table(tr_s, {}),
                              "comparisons": results_screened},
            "weight_distance": diffw, "added_after_first_read": {
                "run": "2026-09-29T025839Z (receipt kept unchanged)",
                "what": "the quantile-mapped ridge (ridgeqm) variants and the mean-ABSOLUTE sigma calibration",
                "why": "the first read showed the raw ridge's per-date dispersion (cv 0.35) is a quarter of "
                       "trailing vol's (cv 1.36), so inverse-ridge weights sat near equal weight (L1 vs equal "
                       "0.14 vs 0.29) and the comparison measured dispersion, not forecast skill; and the "
                       "mean-square calibration gave trailing vol kappa 0.069 vs a naive 0.289 (vol_63 "
                       "outliers dominate squares), inflating every sigma and shrinking every Kelly gross"}, "book_risk_fit": risk_fit, "worst_case": worst,
            "_series": series, "elapsed_s": round(time.time() - t0, 1)}


def engine_check(panel, fam_rule, costs, start) -> dict:
    """run_book (equal weight) must reproduce strategy_library.run_strategy on the same
    panel rows; a mismatch is a finding about one of the two engines."""
    from backend.services import strategy_library as SL
    import dataclasses
    base = SL.rule_by_id("mom_12_1_q")
    sub = panel[(panel["date"] >= start) & panel["size_ridge"].notna()].copy()
    sub_full = panel[panel["date"] >= start].copy()
    sub_full["eligible"] = sub_full["eligible"] & sub_full["size_ridge"].notna()
    out = {}
    for tag, rm in QUARTER_OFFSETS.items():
        rule = dataclasses.replace(base, id=f"chk_{tag}", rebalance_months=rm)
        m = SL.run_strategy(sub_full, rule, k=K).set_index("date")["net"]
        mine = fam_rule["equal"][tag]["net"]
        c = m.index.intersection(mine.index)
        out[tag] = {"n": int(len(c)), "max_abs_diff": float((m.reindex(c) - mine.reindex(c)).abs().max())
                    if len(c) else None}
    del sub
    return out


def weight_distance(panel, mom, costs, start) -> dict:
    """Mean L1 distance between the (a) and (b) inverse-size weights of the SAME names,
    and each one's distance from equal weight: if (a) and (b) barely differ, no portfolio
    effect can be large."""
    a = panel["size_vol"].to_numpy(dtype=float)
    b = panel["size_ridge"].to_numpy(dtype=float)
    res = {}
    for tag, rm in QUARTER_OFFSETS.items():
        m = MS.run_book(panel, mom, k=K, costs=costs, rebalance_months=rm, hold_months=3,
                        start_date=start, keep_holdings=True)
        l_ab, l_ae, l_be, mx_a, mx_b = [], [], [], [], []
        for h in m.attrs["holdings"]:
            idx = np.asarray(h["idx"])
            wa, wb = MS.inverse_size_weights(a[idx]), MS.inverse_size_weights(b[idx])
            eq = np.full(len(idx), 1.0 / len(idx))
            l_ab.append(np.abs(wa - wb).sum())
            l_ae.append(np.abs(wa - eq).sum())
            l_be.append(np.abs(wb - eq).sum())
            mx_a.append(wa.max())
            mx_b.append(wb.max())
        res[tag] = {"n_rebalances": len(l_ab), "l1_a_vs_b": float(np.mean(l_ab)), "l1_a_vs_equal": float(np.mean(l_ae)),
                    "l1_b_vs_equal": float(np.mean(l_be)), "max_w_a": float(np.max(mx_a)),
                    "max_w_b": float(np.max(mx_b))}
    return res


def book_risk_fit(panel, mom, costs, start) -> dict:
    """At each rebalance of the equal-weight mom_12_1_q offsets: the book's predicted
    sigma_p (constant-correlation model on each sigma input) vs the realised |book return|
    over the first held month. Spearman across rebalances, and the QLIKE-style loss."""
    rows = []
    sv, sr = panel["sig_vol"].to_numpy(dtype=float), panel["sig_ridge"].to_numpy(dtype=float)
    sq = panel["sig_ridgeqm"].to_numpy(dtype=float)
    fwd = panel["fwd_ret"].to_numpy(dtype=float)
    for tag, rm in QUARTER_OFFSETS.items():
        m = MS.run_book(panel, mom, k=K, costs=costs, rebalance_months=rm, hold_months=3,
                        start_date=start, keep_holdings=True)
        for h in m.attrs["holdings"]:
            idx = np.asarray(h["idx"])
            w = np.full(len(idx), 1.0 / len(idx))
            r = np.nansum(w * np.nan_to_num(fwd[idx]))
            rows.append({"date": h["date"], "offset": tag, "sp_vol": MS.portfolio_sigma(w, _fill(sv[idx])),
                         "sp_ridge": MS.portfolio_sigma(w, _fill(sr[idx])),
                         "sp_ridgeqm": MS.portfolio_sigma(w, _fill(sq[idx])), "abs_r": abs(r)})
    df = pd.DataFrame(rows).dropna()
    def qlike(s):
        v = s ** 2
        return float(np.mean(df["abs_r"] ** 2 / v + np.log(v)))
    return {"n_rebalances": int(len(df)), "spearman_vol": MS.spearman(df["sp_vol"], df["abs_r"]),
            "spearman_ridge": MS.spearman(df["sp_ridge"], df["abs_r"]),
            "spearman_ridgeqm": MS.spearman(df["sp_ridgeqm"], df["abs_r"]),
            "qlike_vol": qlike(df["sp_vol"]), "qlike_ridge": qlike(df["sp_ridge"]),
            "qlike_ridgeqm": qlike(df["sp_ridgeqm"]),
            "mean_sp_vol": float(df["sp_vol"].mean()), "mean_sp_ridge": float(df["sp_ridge"].mean()),
            "mean_sp_ridgeqm": float(df["sp_ridgeqm"].mean()),
            "rmse_abs_r": float(np.sqrt(np.mean(df["abs_r"] ** 2))),
            "note": "one realised month per rebalance: a single month's |return| is a noisy variance proxy"}


def latest_worst_case(panel, mom) -> dict:
    """Protocol item 4 for the largest admissible book of the proposed rule."""
    last = panel.loc[panel["size_ridge"].notna(), "date"].max()
    d = panel[(panel["date"] == last)].copy()
    sc = pd.Series(mom, index=panel.index).loc[d.index]
    d = d.assign(sc=sc).dropna(subset=["sc"])
    d = d.sort_values(["sc", "tiebreak"], ascending=[False, True]).head(K)
    w = MS.inverse_size_weights(d["size_ridge"].to_numpy(dtype=float))
    s = d["sig_ridge"].to_numpy(dtype=float)
    wc = MS.worst_case_dollars(equity=1_000_000.0, n_names=K, name_cap=MS.NAME_CAP, gross=1.0,
                               sigma_monthly=s, weights=w, stop_sigma=None, k_sigma=3.0)
    wc["decision_date"] = str(pd.Timestamp(last).date())
    wc["names"] = [{"symbol": str(sy), "w": round(float(x), 4), "sigma_monthly": round(float(v), 4)}
                   for sy, x, v in zip(d["symbol"], w, s)]
    return wc


# ═════════════════════════ main ══════════════════════════════════════════════

def write_receipt(part: str, run_id: str, body: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    rp = OUT / f"sizing_{part}_{run_id}.json"
    if rp.exists():
        raise SystemExit(f"REFUSED: {rp.name} exists; a receipt is never overwritten")
    series = body.pop("_series", None)
    if series is not None:
        spath = OUT / f"sizing_{part}_monthly_{run_id}.parquet"
        series.to_parquet(spath)
        body["monthly_series"] = str(spath.relative_to(REPO)).replace("\\", "/")
    doc = {"schema": "sizing_lab/1", "part": part, "run_id": run_id, "licence": "PRODUCT_EXPERIMENT",
           "llm_spend_usd": 0.0, "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "verdict_rule": MS.VERDICT_RULE, "mde_z": MS.MDE_Z,
           "constants": {"k": K, "name_cap": MS.NAME_CAP, "kelly_mu_monthly": MS.KELLY_MU_MONTHLY,
                         "kelly_fraction": MS.KELLY_FRACTION, "kelly_rho": MS.KELLY_RHO,
                         "vol_target_annual": MS.VOL_TARGET_ANNUAL, "gross_cap": MS.GROSS_CAP,
                         "random_seeds": N_RANDOM_SEEDS, "offsets": QUARTER_OFFSETS},
           "conventions": {
               "costs": "band round trip (xs_ranker.COST_BPS_BY_BAND), half on each weight bought or sold; "
                        "zero cost refused (strategy_library.check_costs -> portfolio_farm Policy)",
               "cash": "earns 0 (T-bills NOT credited) -- conservative against every gross < 1 variant",
               "weights": "held constant between rebalances, drift not charged (strategy_library convention)",
               "matched_twin": "for a sizing question the twin is the SAME names on the SAME calendar with the "
                               "baseline size input: selection cancels exactly",
               "by_year": "keyed on the HOLD month (entry = decision + 1 business day)",
               "t": "non-overlapping 3-month date blocks (quarterly holds); MDE = 2.8 x SE",
               "survivorship": "library panel: partially survivor-selected (living names chosen alive "
                               "2026-09-01, dead names from the inactive listed list, -30% delisting fill); "
                               "crsp part: survivorship-free with CRSP delisting returns"},
           "peak_working_set_mb": peak_rss_mb()} | body
    rp.write_text(json.dumps(rnd(doc), indent=1, default=str), encoding="utf-8")
    return rp


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=("library", "crsp", "all"), default="all")
    a = ap.parse_args(argv)
    run_id = new_run_id()
    say(f"sizing_lab run {run_id} part {a.part}")
    if a.part in ("library", "all"):
        body = part_library(run_id)
        say(f"-> {write_receipt('library', run_id, body)}")
    if a.part in ("crsp", "all"):
        from scripts import sizing_lab_crsp as SC
        body = SC.part_crsp(run_id)
        say(f"-> {write_receipt('crsp', run_id, body)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
