"""Does the revision-flow result survive IBES's split-adjust-and-round? (S65 night)

The event bridge builds target signs from `ibes__ptgdet` (split-adjusted to today's
basis, rounded to cents). Rounding is the only look-ahead channel such a file has:
a common split factor never changes the sign of a broker's consecutive targets,
but cent-rounding can (ties, flips) and does so disproportionately for names that
later split many times. This rebuilds the SAME events from `ibes__ptgdetu`
(unadjusted, as announced) put on one basis with CRSP's daily `cfacpr` on the event
day (no rounding), and runs the same family-board cells on both versions.

Both versions use `crsp_event_bridge.target_signs` / `flow_panel` unchanged, targets
only (ratings omitted from n_firms in BOTH so the comparison is like for like).
"""
from __future__ import annotations

import gc
import json
import os
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backend.services import crsp_event_bridge as B
from scripts.night import family_board as FB

BULK = FB.RUNTIME / "optimus" / "wrds" / "bulk"
WRDS = FB.RUNTIME / "optimus" / "wrds"


def cfacpr_changes() -> pd.DataFrame:
    """(permno, date, cfacpr) rows only where cfacpr changes -- a small table."""
    out = []
    for y in range(1993, 2025):
        d = pd.read_parquet(WRDS / f"crsp_dsf_{y}.parquet", columns=["permno", "date", "cfacpr"])
        d = d.dropna()
        d = d[d["cfacpr"] > 0].sort_values(["permno", "date"])
        ch = d["cfacpr"].ne(d.groupby("permno")["cfacpr"].shift(1))
        out.append(d[ch])
    c = pd.concat(out).sort_values(["permno", "date"])
    c = c[c["cfacpr"].ne(c.groupby("permno")["cfacpr"].shift(1))]
    c["date"] = pd.to_datetime(c["date"])
    c["permno"] = c["permno"].astype("int64")
    return c


def events(src: str, link: pd.DataFrame, cf: pd.DataFrame | None) -> tuple[pd.DataFrame, dict]:
    ptg = pd.read_parquet(BULK / src, columns=["ticker", "estimid", "value", "anndats", "actdats", "horizon",
                                                "curr", "usfirm"], filters=[("usfirm", "=", 1)])
    ptg = ptg[(ptg["horizon"].astype(str) == "12") & (ptg["curr"].astype(str) == "USD")]
    ptg["day"] = B.event_day(ptg["anndats"], ptg["actdats"]).to_numpy()
    ptg = ptg.dropna(subset=["day", "value"])[["ticker", "estimid", "value", "day"]]
    ptg, meta = B.link_permno(ptg, link)
    ptg = ptg.rename(columns={"estimid": "broker"})
    ptg["value"] = ptg["value"].astype(float)
    if cf is not None:
        ptg["day"] = pd.to_datetime(ptg["day"])
        ptg["permno"] = ptg["permno"].astype("int64")
        ptg = ptg.sort_values("day")
        m = pd.merge_asof(ptg, cf.rename(columns={"date": "cf_date"}).sort_values("cf_date"),
                          left_on="day", right_on="cf_date", by="permno", direction="backward")
        meta["share_with_cfacpr"] = float(m["cfacpr"].notna().mean())
        m = m[m["cfacpr"].notna()]
        m["value"] = m["value"] / m["cfacpr"]
        ptg = m[["permno", "broker", "value", "day"]]
    ptg = B.target_signs(ptg)
    ptg["usable"] = B.usable_date(ptg["day"]).to_numpy()
    meta["n_events"] = int(len(ptg))
    meta["sign_shares"] = {str(k): round(float(v), 4) for k, v in ptg["sign"].value_counts(normalize=True).items()}
    return ptg[["permno", "usable", "broker", "sign", "chg"]], meta


def main() -> int:
    run_id = f"flow_unadjusted_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    print("RUN", run_id, "pid", os.getpid(), flush=True)
    t0 = time.time()
    os.environ["NIGHT_IBES"] = "0"
    df = FB.load("1999-01-01")
    dates = sorted(df["date"].unique())
    link = pd.read_parquet(BULK / "wrdsapps_link_crsp_ibes__ibcrsphist.parquet")
    link["score"] = pd.to_numeric(link["score"], errors="coerce").fillna(9)
    cf = cfacpr_changes()
    print(f"cfacpr change rows {len(cf):,} ({time.time()-t0:.0f}s)", flush=True)
    metas = {}
    for tag, src, c in (("adj", "ibes__ptgdet.parquet", None), ("unadj", "ibes__ptgdetu.parquet", cf)):
        ev, metas[tag] = events(src, link, c)
        print(tag, json.dumps(metas[tag]), f"({time.time()-t0:.0f}s)", flush=True)
        fl = B.flow_panel(ev, dates)
        fl["symbol"] = fl["permno"].astype(int).map(lambda x: f"{x:06d}")
        fl = fl[["date", "symbol", "net_raises", "n_firms"]].rename(
            columns={"net_raises": f"nr_{tag}", "n_firms": f"nf_{tag}"})
        fl[f"fr_{tag}"] = fl[f"nr_{tag}"] * fl[f"nf_{tag}"]
        for col in (f"nr_{tag}", f"fr_{tag}"):
            fl.loc[fl[col] == 0, col] = np.nan
        df = df.merge(fl, on=["date", "symbol"], how="left")
        del ev, fl
        gc.collect()
    el = df[df["eligible"].astype(bool) & (df["symbol"] != "SPY")].copy()
    el["ret"] = el["fwd_ret"].where(el["fwd_ret"].notna(), np.where(el["delisted_in_period"].astype(bool), -0.30, 0.0))
    el["sid"] = pd.factorize(el["symbol"])[0]
    el["liq_rank"] = el.groupby("date")["median_dollar_vol"].rank(ascending=False, method="first") - 1
    months = [m for m in sorted(el["date"].unique()) if m < pd.Timestamp("2024-12-31")]
    mkt = df[df["symbol"] == "SPY"].set_index("date")["fwd_ret"].reindex(months).to_numpy(float)
    cols = ["nr_adj", "fr_adj", "nr_unadj", "fr_unadj"]
    g = {m: {"sym": x["symbol"].to_numpy(), "sid": x["sid"].to_numpy(np.int64), "ret": x["ret"].to_numpy(float),
             "liq_rank": x["liq_rank"].to_numpy(float), **{c: x[c].to_numpy(float) for c in cols}}
         for m, x in el.groupby("date")}
    ew = np.array([float(np.mean(g[m]["ret"])) for m in months])
    agree = {}
    for m in months[::12]:
        x = g[m]
        a, b = x["nr_adj"], x["nr_unadj"]
        ok = np.isfinite(a) & np.isfinite(b)
        agree[str(pd.Timestamp(m).year)] = {"n_both": int(ok.sum()), "n_adj": int(np.isfinite(a).sum()),
                                           "n_unadj": int(np.isfinite(b).sum()),
                                           "corr": float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 10 else None}
    print("agreement by year:", json.dumps(agree), flush=True)
    rng = np.random.default_rng(20261111)
    cells = []
    for uni in ("eligible", "liquid500"):
        for col in cols:
            for k in (10, 20, 50, 100):
                res = FB.run_cell(g, months, col, 1, k, 0.001, 30, rng, uni)
                s = FB.summarise(months, res["fam"], res["twin"], mkt, ew)
                s.update(column=col, k=k, universe=uni)
                cells.append(s)
                v = s["vs_twin"]
                print(f"{uni:<9} {col:<9} k={k:<3} net {100*s['net_cagr']:6.2f}%/y | vs twin {100*v['mean_monthly']:+.2f}%/mo "
                      f"t {v['t_blocks']:+.2f} MDE {100*v['mde_monthly']:.2f} | yrs+ {s['years_positive']}/{s['n_years']} "
                      f"LOO {100*s['loo_worst_mean_monthly']:+.2f}", flush=True)
    out = FB.OUT / f"{run_id}.json"
    out.write_text(json.dumps({"run_id": run_id, "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
                               "event_meta": metas, "agreement": agree, "cells": cells,
                               "elapsed_s": round(time.time() - t0, 1)}, indent=1, default=str), encoding="utf-8")
    print("DONE", out, f"{time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
