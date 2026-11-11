"""Two follow-ups on the family board (S65 night), same panel and conventions.

1. SIGNAL DECAY. A top-20 list formed at month-end t and NOT rebalanced: its return
   in month t+1+L minus the equal-weight return of every name that had the signal
   at t (the expected random twin), for L = 0..5. Answers "how long does a frozen
   member list keep its edge?" -- the live revision_flow_v0 list has been frozen
   since 2026-09-28.
2. FACTOR CHECK. The monthly-rebalanced top-20 net series (10 bps) regressed on
   FF5 + UMD; alpha t with Newey-West(3) errors, and MDE = 2.8 x SE beside it.
Gross of costs in (1) (no trades happen after formation); net in (2).
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.night.family_board import FAMILIES, OUT, RUNTIME, load

LAGS = range(0, 6)
FAMS = ["rev_net_raises", "rev_flow_rule", "mom_12_1", "pead_ear", "quality_gp_at", "ibes_low_dispersion", "ibes_rev_breadth"]


def nw_ols(y: np.ndarray, X: np.ndarray, lags: int = 3) -> tuple[np.ndarray, np.ndarray]:
    X = np.column_stack([np.ones(len(y)), X])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ b
    xtx_inv = np.linalg.inv(X.T @ X)
    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        G = (X[L:] * e[L:, None]).T @ (X[:-L] * e[:-L, None])
        S += w * (G + G.T)
    V = xtx_inv @ S @ xtx_inv
    return b, np.sqrt(np.diag(V))


def main() -> int:
    run_id = f"decay_factors_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    print("RUN", run_id, "pid", os.getpid(), flush=True)
    df = load("1993-01-01")
    el = df[df["eligible"].astype(bool) & (df["symbol"] != "SPY")].copy()
    el["ret"] = el["fwd_ret"].where(el["fwd_ret"].notna(),
                                    np.where(el["delisted_in_period"].astype(bool), -0.30, np.nan))
    el["liq_rank"] = el.groupby("date")["median_dollar_vol"].rank(ascending=False, method="first") - 1
    months = sorted(el["date"].unique())
    mi = {m: i for i, m in enumerate(months)}
    R = el.pivot_table(index="symbol", columns="date", values="ret")      # ret during month after column date
    R = R.reindex(index=pd.Index(el["symbol"].unique()), columns=months)
    Rv = R.to_numpy(float)
    sym_ix = {s: i for i, s in enumerate(R.index)}
    ff = pd.read_parquet(RUNTIME / "optimus" / "wrds" / "ff_fivefactors_monthly.parquet")
    ff["ym"] = pd.to_datetime(ff["dateff"]).dt.to_period("M")
    ff = ff.set_index("ym")
    out = {"run_id": run_id, "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0, "decay": {}, "factors": {}}
    for uni in ("eligible", "liquid500"):
        for fam in FAMS:
            _, col, sign = FAMILIES[fam]
            ex = {L: [] for L in LAGS}
            net, prev = [], None
            dates = []
            for m, x in el.groupby("date"):
                i = mi[m]
                s = x[col].to_numpy(float)
                ok = np.isfinite(s)
                if uni == "liquid500":
                    ok &= x["liq_rank"].to_numpy() < 500
                if ok.sum() < 40:
                    continue
                syms = x["symbol"].to_numpy()[ok]
                sc = s[ok] * sign
                top = syms[np.argsort(-sc, kind="mergesort")[:20]]
                ti = np.array([sym_ix[t] for t in top])
                ai = np.array([sym_ix[t] for t in syms])
                for L in LAGS:
                    if i + L >= len(months) - 1:
                        continue
                    a = np.nanmean(Rv[ti, i + L])
                    b = np.nanmean(Rv[ai, i + L])
                    if np.isfinite(a) and np.isfinite(b):
                        ex[L].append(a - b)
                if i < len(months) - 1:
                    cur = set(top.tolist())
                    n_new = 20 if prev is None else len(cur - prev)
                    r0 = np.nanmean(Rv[ti, i])
                    if np.isfinite(r0):
                        net.append(r0 - 0.001 * (2.0 * n_new / 20 if prev is not None else 1.0))
                        dates.append(m)
                    prev = cur
            dec = {}
            for L in LAGS:
                d = np.array(ex[L])
                nb = len(d) // 3
                bm = d[: nb * 3].reshape(nb, 3).mean(1)
                se = bm.std(ddof=1) / math.sqrt(nb)
                dec[L] = {"mean_monthly": float(d.mean()), "t_blocks": float(bm.mean() / se),
                          "mde_monthly": float(2.8 * se), "n": int(len(d))}
            out["decay"][f"{uni}/{fam}"] = dec
            print(f"DECAY {uni:<9} {fam:<15} " + " ".join(
                f"L{L}:{100*dec[L]['mean_monthly']:+.2f}(t{dec[L]['t_blocks']:+.1f})" for L in LAGS), flush=True)
            hold = pd.PeriodIndex([(pd.Timestamp(m) + pd.offsets.MonthEnd(1)).to_period("M") for m in dates])
            f = ff.reindex(hold)
            y = np.array(net) - f["rf"].to_numpy(float)
            X = f[["mktrf", "smb", "hml", "rmw", "cma", "umd"]].to_numpy(float)
            okr = np.isfinite(y) & np.isfinite(X).all(1)
            b, se = nw_ols(y[okr], X[okr])
            names = ["alpha", "mktrf", "smb", "hml", "rmw", "cma", "umd"]
            fr = {n: {"coef": float(b[j]), "t": float(b[j] / se[j])} for j, n in enumerate(names)}
            fr["alpha_mde_monthly"] = float(2.8 * se[0])
            fr["n_months"] = int(okr.sum())
            out["factors"][f"{uni}/{fam}"] = fr
            print(f"FF5+UMD {uni:<9} {fam:<15} alpha {100*b[0]:+.2f}%/mo t {b[0]/se[0]:+.2f} MDE {280*se[0]:.2f} | "
                  + " ".join(f"{n} {b[j]:+.2f}({b[j]/se[j]:+.1f})" for j, n in enumerate(names) if j), flush=True)
    p = OUT / f"{run_id}.json"
    p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print("DONE", p, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
