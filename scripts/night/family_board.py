"""Strategy-family comparison on the survivorship-free CRSP monthly panel (S65 night).

Reads the runtime's crsp_rebuild panels (library_panel / library_fund / event_bridge,
1991-2024 month-ends, every permno of the PIT universe incl. dead names, delisting
returns booked; `fwd_ret` = next month, entry the session after the decision).
Writes one JSON receipt with a run id to night_2026-11-11/.

Each (family, k, universe) cell: top-k equal weight, monthly rebalance, cost
`--cost-bps` one-way on traded weight; a TURNOVER-MATCHED random twin (same k,
same eligible set, replaces exactly as many names as the family did each month,
same cost), `--twins` draws. Score = family net - mean twin net. Printed:
net CAGR, vs market (FF VW, not SPY), vs twin, by-year sign count, worst
leave-one-year-out mean, t on non-overlapping 3-month blocks with MDE = 2.8 x SE.
No look-ahead: selection uses only columns dated <= the decision date; a null
fwd_ret on a selected name is booked at -30% when it is a delisting month, else 0
(counted on the receipt).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend" / "data" / "optimus" / "night_2026-11-11"
RUNTIME = Path(os.environ.get("AEGIS_RUNTIME_DATA", r"C:\Users\mrthn\aegis-finance\backend\data"))
CR = RUNTIME / "optimus" / "crsp_rebuild"
PANEL = CR / "library_panel_2026-09-29T075640Z.parquet"
FUND = CR / "library_fund_2026-09-29T041550Z.parquet"
EB = CR / "event_bridge_EB_2026-09-29T1055Z.parquet"

#: family -> (source, column, sign, extra filter). sign +1 = high score buys.
FAMILIES = {
    "mom_12_1": ("panel", "mom_252_21", +1),
    "reversal_1m": ("panel", "mom_21", -1),
    "low_vol": ("panel", "vol_63", -1),
    "rev_flow_rule": ("eb", "flow_rule_score", +1),      # net raises x firms (the leaders' score)
    "rev_net_raises": ("eb", "net_raises", +1),
    "quality_gp_at": ("fund", "gp_at", +1),
    "value_bm": ("fund", "book_to_market", +1),
    "pead_ear": ("eb", "ear_last", +1),                   # reaction-based drift, <= 63 days old
    "ibes_low_dispersion": ("ibes", "rev_dispersion", +1),  # -stdev/|meanest| FY1: agreement buys
    "ibes_rev_breadth": ("ibes", "rev_breadth", +1),        # (numup - numdown) / numest
    # The same dispersion with the SPLIT-ROUNDING LEAK removed: IBES summary history is
    # split-adjusted to today's share basis and rounded to cents, so a firm that later
    # splits many times (a future winner) shows meanest ~0.01 and stdev 0.00 in early
    # years, which the 0.10 floor turns into "perfect agreement". Defined only where
    # |meanest| >= 0.25 and stdev > 0, ratio without the floor.
    "ibes_low_dispersion_clean": ("ibes", "rev_dispersion_clean", +1),
}


def ibes_monthly(keys: pd.DataFrame) -> pd.DataFrame:
    """FY1 EPS consensus state as of each month-end decision date, PIT.

    Reuses the farm's loader and derivation (`portfolio_farm.revisions`): a row
    stamped `statpers = s` is usable only on a date STRICTLY after s plus a
    5-business-day distribution lag, and is stale after 45 days.
    """
    from backend.services.portfolio_farm import revisions as RV
    raw = RV.derive(RV._load_raw())   # as quoted since 2026-11-11 (ibes_pit_consensus)
    me = raw["meanest"].abs()
    raw["rev_dispersion_clean"] = np.where((me >= 0.25) & (raw["stdev"] > 0), -raw["stdev"] / me, np.nan)
    raw = raw[["permno", "statpers", "rev_dispersion", "rev_breadth", "rev_dispersion_clean"]].copy()
    for c in ("rev_dispersion", "rev_breadth"):
        lo, hi = RV.PLAUSIBLE[c]
        raw.loc[(raw[c] < lo) | (raw[c] > hi), c] = np.nan
    raw["usable"] = pd.to_datetime(raw["statpers"]) + pd.offsets.BDay(5)
    raw["symbol"] = raw["permno"].astype(int).map(lambda x: f"{x:06d}")
    raw = raw.sort_values("usable")
    keys = keys[["date", "symbol"]].sort_values("date")
    m = pd.merge_asof(keys, raw[["usable", "symbol", "rev_dispersion", "rev_breadth", "rev_dispersion_clean"]], left_on="date",
                      right_on="usable", by="symbol", allow_exact_matches=False, direction="backward")
    stale = ~((m["date"] - m["usable"]).dt.days <= 45)
    m.loc[stale, ["rev_dispersion", "rev_breadth", "rev_dispersion_clean"]] = np.nan
    return m[["date", "symbol", "rev_dispersion", "rev_breadth", "rev_dispersion_clean"]]


def describe(p: Path) -> dict:
    st = p.stat()
    return {"path": str(p), "bytes": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}


def load(start: str) -> pd.DataFrame:
    cols = ["date", "symbol", "eligible", "fwd_ret", "delisted_in_period", "mom_252_21",
            "mom_21", "vol_63", "median_dollar_vol"]
    p = pd.read_parquet(PANEL, columns=cols)
    f = pd.read_parquet(FUND, columns=["date", "symbol", "gp_at", "book_to_market"])
    e = pd.read_parquet(EB, columns=["date", "symbol", "flow_rule_score", "net_raises",
                                     "ear_last", "days_since_earn"])
    df = p.merge(f, on=["date", "symbol"], how="left").merge(e, on=["date", "symbol"], how="left")
    df.loc[~(df["days_since_earn"] <= 63), "ear_last"] = np.nan
    if os.environ.get("NIGHT_IBES", "1") == "1":
        ib = ibes_monthly(df)
        df = df.merge(ib, on=["date", "symbol"], how="left")
    # flow scores are 0 for covered names with no events; a covered-zero is not a signal
    for c in ("flow_rule_score", "net_raises"):
        df.loc[df[c] == 0, c] = np.nan
    df = df[df["date"] >= pd.Timestamp(start)]
    return df


def block_stats(d: np.ndarray, block: int = 3) -> dict:
    d = d[np.isfinite(d)]
    nb = len(d) // block
    if nb < 4:
        return {"n_months": int(len(d)), "n_blocks": int(nb)}
    bm = d[: nb * block].reshape(nb, block).mean(axis=1)
    se = bm.std(ddof=1) / math.sqrt(nb)
    return {"n_months": int(len(d)), "n_blocks": int(nb), "mean_monthly": float(d.mean()),
            "se_monthly": float(se), "t_blocks": float(bm.mean() / se) if se > 0 else None,
            "mde_monthly": float(2.8 * se)}


def run_cell(g: dict, months: list, sig_col: str, sign: int, k: int, cost: float,
             twins: int, rng: np.random.Generator, universe: str) -> dict:
    fam_net, twin_net, fam_turn = [], [], []
    tw_hold = [None] * twins
    prev = None
    n_nullfill = 0
    for m in months:
        x = g[m]
        s = x[sig_col]
        ok = np.isfinite(s)
        if universe == "liquid500":
            ok &= x["liq_rank"] < 500
        idx = np.flatnonzero(ok)
        if len(idx) < max(k * 2, 20):
            fam_net.append(np.nan); twin_net.append(np.nan); fam_turn.append(np.nan)
            continue
        order = idx[np.argsort(-sign * s[idx], kind="mergesort")][:k]
        r = x["ret"]
        cur = set(x["sym"][order].tolist())
        n_new = k if prev is None else len(cur - prev)
        traded = (2.0 * n_new / k) if prev is not None else 1.0
        fam_net.append(float(np.mean(r[order])) - cost * traded)
        fam_turn.append(n_new / k)
        prev = cur
        # turnover-matched twins on the same eligible set (integer symbol ids)
        ids_ok = x["sid"][idx]
        tws = []
        for j in range(twins):
            h = tw_hold[j]
            if h is None:
                pick = rng.choice(len(idx), size=k, replace=False)
                tw_hold[j] = ids_ok[pick]
                tws.append(float(np.mean(r[idx[pick]])) - cost * 1.0)
                continue
            alive = h[np.isin(h, ids_ok)]
            forced = len(h) - len(alive)
            drop = max(0, n_new - forced)
            if drop and len(alive):
                alive = alive[rng.permutation(len(alive))[: max(0, len(alive) - drop)]]
            need = k - len(alive)
            if need:
                pool = np.flatnonzero(~np.isin(ids_ok, alive))
                add = ids_ok[rng.choice(pool, size=need, replace=False)]
                new_ids = np.concatenate([alive, add])
            else:
                new_ids = alive
            sel = idx[np.isin(ids_ok, new_ids)]
            tw_hold[j] = new_ids
            tws.append(float(np.mean(r[sel])) - cost * 2.0 * need / k)
        twin_net.append(float(np.mean(tws)))
    return {"fam": np.array(fam_net), "twin": np.array(twin_net), "turn": np.array(fam_turn)}


def summarise(months, fam, twin, mkt, ew) -> dict:
    hold_year = np.array([(pd.Timestamp(m) + pd.offsets.MonthEnd(1)).year for m in months])
    ok = np.isfinite(fam) & np.isfinite(twin)
    d = np.where(ok, fam - twin, np.nan)
    yrs = sorted(set(hold_year[ok].tolist()))
    by_year = {int(y): float(np.nansum(d[hold_year == y])) for y in yrs}
    loo = {int(y): float(np.nanmean(d[ok & (hold_year != y)])) for y in yrs}
    worst_y = min(loo, key=loo.get) if loo else None

    def cagr(x):
        x = x[np.isfinite(x)]
        return float(np.exp(np.log1p(x).sum() * 12 / len(x)) - 1) if len(x) else None
    early = ok & (hold_year <= 2016)
    late = ok & (hold_year >= 2017)
    return {
        "net_cagr": cagr(np.where(ok, fam, np.nan)), "twin_cagr": cagr(np.where(ok, twin, np.nan)),
        "market_cagr": cagr(np.where(ok, mkt, np.nan)), "ew_universe_cagr": cagr(np.where(ok, ew, np.nan)),
        "vs_twin": block_stats(d[ok]), "vs_market": block_stats((fam - mkt)[ok]),
        "vs_twin_1993_2016": block_stats(d[early]), "vs_twin_2017_2024": block_stats(d[late]),
        "by_year_vs_twin": by_year,
        "years_positive": int(sum(v > 0 for v in by_year.values())), "n_years": len(by_year),
        "loo_worst_mean_monthly": loo[worst_y] if worst_y is not None else None,
        "loo_worst_dropped_year": worst_y,
        "best_year_share_of_total": (max(by_year.values()) / sum(by_year.values())
                                     if by_year and sum(by_year.values()) > 0 else None),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="1993-01-01")
    ap.add_argument("--ks", default="10,20,50,100")
    ap.add_argument("--cost-bps", type=float, default=10.0)
    ap.add_argument("--twins", type=int, default=30)
    ap.add_argument("--universes", default="eligible,liquid500")
    ap.add_argument("--families", default=",".join(FAMILIES))
    ap.add_argument("--seed", type=int, default=20261111)
    a = ap.parse_args(argv)
    run_id = f"family_board_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    print("RUN", run_id, "pid", os.getpid(), flush=True)
    inputs = {k: describe(v) for k, v in (("panel", PANEL), ("fund", FUND), ("event_bridge", EB))}
    print(json.dumps(inputs, indent=1), flush=True)
    t0 = time.time()
    df = load(a.start)
    print(f"joined panel: {len(df):,} rows, {df['date'].nunique()} month-ends "
          f"{df['date'].min().date()}..{df['date'].max().date()}, {df['symbol'].nunique():,} symbols", flush=True)
    mkt = df[df["symbol"] == "SPY"].set_index("date")["fwd_ret"]
    el = df[df["eligible"].astype(bool) & (df["symbol"] != "SPY")].copy()
    nullf = el["fwd_ret"].isna()
    fill = np.where(el["delisted_in_period"].astype(bool), -0.30, 0.0)
    el["ret"] = el["fwd_ret"].where(~nullf, fill)
    null_by_year = el[nullf].groupby(el["date"].dt.year).size().to_dict()
    el["sid"] = pd.factorize(el["symbol"])[0]
    el["liq_rank"] = el.groupby("date")["median_dollar_vol"].rank(ascending=False, method="first") - 1
    months = sorted(el["date"].unique())
    months = [m for m in months if m < pd.Timestamp("2024-12-31")]  # last month has no forward
    g = {}
    for m, x in el.groupby("date"):
        g[m] = {"sym": x["symbol"].to_numpy(), "sid": x["sid"].to_numpy(np.int64), "ret": x["ret"].to_numpy(float),
                "liq_rank": x["liq_rank"].to_numpy(float),
                **{c: x[c].to_numpy(float) for c in {v[1] for v in FAMILIES.values()}}}
    ew = np.array([float(np.mean(g[m]["ret"])) for m in months])
    mk = mkt.reindex(months).to_numpy(float)
    cov = {f: {int(pd.Timestamp(m).year): int(np.isfinite(g[m][FAMILIES[f][1]]).sum())
               for m in months[::12]} for f in FAMILIES}
    print("coverage (names with signal, first month of each year):", json.dumps(cov), flush=True)
    rng = np.random.default_rng(a.seed)
    ks = [int(k) for k in a.ks.split(",")]
    cells = []
    for uni in a.universes.split(","):
        for fam in a.families.split(","):
            src, col, sign = FAMILIES[fam]
            for k in ks:
                t1 = time.time()
                res = run_cell(g, months, col, sign, k, a.cost_bps / 1e4, a.twins, rng, uni)
                s = summarise(months, res["fam"], res["twin"], mk, ew)
                s.update(family=fam, column=col, sign=sign, k=k, universe=uni,
                         turnover_monthly=float(np.nanmean(res["turn"])),
                         months_run=int(np.isfinite(res["fam"]).sum()))
                cells.append(s)
                vt = s["vs_twin"]
                print(f"{uni:<9} {fam:<15} k={k:<3} net {100*(s['net_cagr'] or 0):6.2f}%/y "
                      f"mkt {100*(s['market_cagr'] or 0):5.2f} twin {100*(s['twin_cagr'] or 0):5.2f} | "
                      f"vs twin {100*vt.get('mean_monthly', float('nan')):+.2f}%/mo t {vt.get('t_blocks') or float('nan'):+.2f} "
                      f"MDE {100*vt.get('mde_monthly', float('nan')):.2f} | yrs+ {s['years_positive']}/{s['n_years']} "
                      f"LOO {100*(s['loo_worst_mean_monthly'] or float('nan')):+.2f} | turn {s['turnover_monthly']:.2f} "
                      f"({time.time()-t1:.0f}s)", flush=True)
                rec = {"run_id": run_id, "pid": os.getpid(), "licence": "PRODUCT_EXPERIMENT",
                       "llm_spend_usd": 0.0, "args": vars(a), "inputs": inputs,
                       "null_fwd_ret_filled_by_year": {int(k_): int(v) for k_, v in null_by_year.items()},
                       "coverage": cov, "n_cells": len(cells), "cells": cells,
                       "elapsed_s": round(time.time() - t0, 1),
                       "notes": "market = FF VW total return (NOT SPY). by-year keyed on the HOLD month. "
                                "Twin = turnover-matched random from the same eligible set with the signal defined."}
                tmp = OUT / f"{run_id}.json.tmp"
                tmp.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
                tmp.replace(OUT / f"{run_id}.json")
    print("DONE", run_id, f"{time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
