"""Is Book G Amendment 1 (|stdev / price|) the same split-rounding leak? (S65 night)

IBES summary `stdev` is split-adjusted to TODAY's share basis and rounded to cents.
Three versions of "low price-scaled dispersion", same cells as the family board
(top-k, monthly, 10 bps, turnover-matched twins):
  G_raw       stdev_adj / |prc|               (adjusted numerator over the RAW CRSP close:
                                               shrinks by the future split factor)
  G_basis     stdev_adj / (|prc| / cfacpr)    (both on today's basis; rounding still in)
  G_clean     G_basis where |meanest| >= 0.25 and stdev > 0
`prc` and `cfacpr` are CRSP monthly (crsp.msf) for the decision month.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backend.services.portfolio_farm import revisions as RV
from scripts.night import family_board as FB

LO = 0.25   # the PR #94 guard this check compared against (removed from config 2026-11-11)


def main() -> int:
    run_id = f"book_g_check_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    print("RUN", run_id, "pid", os.getpid(), flush=True)
    t0 = time.time()
    os.environ["NIGHT_IBES"] = "0"
    df = FB.load("1993-01-01")
    raw = RV._load_adjusted_diagnostic(FB.RUNTIME / "optimus" / "wrds")  # the LEAKY file, on purpose[["permno", "statpers", "meanest", "stdev"]].copy()
    raw["usable"] = pd.to_datetime(raw["statpers"]) + pd.offsets.BDay(5)
    raw["symbol"] = raw["permno"].astype(int).map(lambda x: f"{x:06d}")
    keys = df[["date", "symbol"]].sort_values("date")
    ib = pd.merge_asof(keys, raw.sort_values("usable")[["usable", "symbol", "meanest", "stdev"]], left_on="date",
                       right_on="usable", by="symbol", allow_exact_matches=False, direction="backward")
    ib.loc[~((ib["date"] - ib["usable"]).dt.days <= 45), ["meanest", "stdev"]] = np.nan
    msf = pd.read_parquet(FB.RUNTIME / "optimus" / "wrds" / "bulk" / "crsp__msf.parquet",
                          columns=["permno", "date", "prc", "cfacpr"])
    msf["date"] = pd.to_datetime(msf["date"])
    msf = msf[msf["date"] >= "1992-12-01"]
    msf["symbol"] = msf["permno"].astype(int).map(lambda x: f"{x:06d}")
    msf["ym"] = msf["date"].dt.to_period("M")
    msf = msf.drop_duplicates(["symbol", "ym"], keep="last")[["symbol", "ym", "prc", "cfacpr"]]
    ib["ym"] = ib["date"].dt.to_period("M")
    ib = ib.merge(msf, on=["symbol", "ym"], how="left")
    px = ib["prc"].abs()
    ok = (px > 0) & (ib["cfacpr"] > 0) & ib["stdev"].notna()
    ib["G_raw"] = np.where(ok, -(ib["stdev"] / px), np.nan)
    ib["G_basis"] = np.where(ok, -(ib["stdev"] / (px / ib["cfacpr"])), np.nan)
    clean = ok & (ib["meanest"].abs() >= LO) & (ib["stdev"] > 0)
    ib["G_clean"] = np.where(clean, ib["G_basis"], np.nan)
    df = df.merge(ib[["date", "symbol", "G_raw", "G_basis", "G_clean"]], on=["date", "symbol"], how="left")
    el = df[df["eligible"].astype(bool) & (df["symbol"] != "SPY")].copy()
    el["ret"] = el["fwd_ret"].where(el["fwd_ret"].notna(), np.where(el["delisted_in_period"].astype(bool), -0.30, 0.0))
    el["sid"] = pd.factorize(el["symbol"])[0]
    el["liq_rank"] = el.groupby("date")["median_dollar_vol"].rank(ascending=False, method="first") - 1
    months = [m for m in sorted(el["date"].unique()) if m < pd.Timestamp("2024-12-31")]
    mkt = df[df["symbol"] == "SPY"].set_index("date")["fwd_ret"].reindex(months).to_numpy(float)
    cols = ["G_raw", "G_basis", "G_clean"]
    g = {m: {"sym": x["symbol"].to_numpy(), "sid": x["sid"].to_numpy(np.int64), "ret": x["ret"].to_numpy(float),
             "liq_rank": x["liq_rank"].to_numpy(float), **{c: x[c].to_numpy(float) for c in cols}}
         for m, x in el.groupby("date")}
    ew = np.array([float(np.mean(g[m]["ret"])) for m in months])
    rng = np.random.default_rng(20261111)
    cells = []
    for uni in ("eligible", "liquid500"):
        for col in cols:
            for k in (20, 30, 50):
                res = FB.run_cell(g, months, col, 1, k, 0.001, 30, rng, uni)
                s = FB.summarise(months, res["fam"], res["twin"], mkt, ew)
                s.update(column=col, k=k, universe=uni)
                cells.append(s)
                v = s["vs_twin"]
                print(f"{uni:<9} {col:<8} k={k:<3} net {100*s['net_cagr']:6.2f}%/y | vs twin {100*v['mean_monthly']:+.2f}%/mo "
                      f"t {v['t_blocks']:+.2f} MDE {100*v['mde_monthly']:.2f} | yrs+ {s['years_positive']}/{s['n_years']} "
                      f"LOO {100*s['loo_worst_mean_monthly']:+.2f} | 17-24 {100*s['vs_twin_2017_2024']['mean_monthly']:+.2f}",
                      flush=True)
    out = FB.OUT / f"{run_id}.json"
    out.write_text(json.dumps({"run_id": run_id, "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
                               "cells": cells, "elapsed_s": round(time.time() - t0, 1)}, indent=1, default=str),
                   encoding="utf-8")
    print("DONE", out, f"{time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
