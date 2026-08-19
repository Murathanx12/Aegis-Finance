"""AMENDMENT 2 — the +options / +expectations ladder rungs, at scale.

    python -m scripts.net_ladder_rungs_run

Feature definitions frozen in AMENDMENT2_NET_LADDER_RUNGS.md before any
computation. SCREEN only: paired per-date IC increments per rung.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from math import erf, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services.net_tournament import (                # noqa: E402
    bootstrap_block_dates, rank_ic_by_date)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)
from scripts.universe_survival_stress_1 import (             # noqa: E402
    FEATURES, build_monthly_dataset)

WRDS = _config.OPTIMUS_LEDGER_DIR / "wrds"
OUT = _config.OPTIMUS_LEDGER_DIR / "net_tournament"

OPT_FEATS = ("opt_iv_atm", "opt_skew", "opt_pc50")
EXP_FEATS = ("exp_breadth", "exp_disp", "exp_chg")
RUNGS = {"numeric": list(FEATURES),
         "plus_options": list(FEATURES) + list(OPT_FEATS),
         "plus_expectations": (list(FEATURES) + list(OPT_FEATS)
                               + list(EXP_FEATS))}


def options_monthly() -> pd.DataFrame:
    """permno-month options features per the frozen definitions."""
    link = pd.read_parquet(WRDS / "link_optionm_crsp.parquet")
    link["sdate"] = pd.to_datetime(link["sdate"])
    link["edate"] = pd.to_datetime(link["edate"])
    parts = []
    for yr in range(2013, 2025):
        s = pd.read_parquet(WRDS / f"optionm_surface30d_{yr}.parquet")
        s["date"] = pd.to_datetime(s["date"])
        s["adelta"] = s["delta"].abs()
        piv = s.pivot_table(index=["secid", "date"],
                            columns=["cp_flag", "adelta"],
                            values="impl_volatility", aggfunc="last")
        piv.columns = [f"{cp}{int(d)}" for cp, d in piv.columns]
        f = pd.DataFrame(index=piv.index)
        f["opt_iv_atm"] = piv[["C50", "P50"]].mean(axis=1)
        f["opt_skew"] = piv.get("P25") - piv.get("C25")
        f["opt_pc50"] = piv.get("P50") - piv.get("C50")
        f = f.reset_index()
        # month-end sample: last obs per secid-month
        f["month"] = f["date"].dt.to_period("M")
        f = f.sort_values("date").groupby(["secid", "month"]).tail(1)
        parts.append(f)
    allf = pd.concat(parts, ignore_index=True)
    # secid -> permno via dated link
    m = allf.merge(link[["secid", "permno", "sdate", "edate"]],
                   on="secid", how="inner")
    m = m[(m["date"] >= m["sdate"])
          & (m["date"] <= m["edate"].fillna(pd.Timestamp("2100-01-01")))]
    return m[["permno", "month", "date",
              *OPT_FEATS]].rename(columns={"date": "opt_date"})


def expectations_monthly() -> pd.DataFrame:
    e = pd.read_parquet(WRDS / "ibes_consensus_monthly.parquet")
    e = e[e["fpi"] == "1"].copy()
    e["statpers"] = pd.to_datetime(e["statpers"])
    e = e.sort_values("statpers")
    e["exp_breadth"] = (e["numup"] - e["numdown"]) / e["numest"]
    e["exp_disp"] = np.where(e["meanest"].abs() >= 0.01,
                             e["stdev"] / e["meanest"].abs(), np.nan)
    prev = e.groupby("permno")["meanest"].shift(1)
    e["exp_chg"] = np.where(prev.abs() >= 0.01,
                            (e["meanest"] - prev) / prev.abs(), np.nan)
    e["month"] = e["statpers"].dt.to_period("M")
    e = e.groupby(["permno", "month"]).tail(1)
    return e[["permno", "month", *EXP_FEATS]]


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    print("base panel...")
    df = build_monthly_dataset()
    df["month"] = df["date"].dt.to_period("M")
    print("options features...")
    opt = options_monthly()
    stale = (df.merge(opt, on=["permno", "month"], how="left"))
    # staleness cap: options obs within 10 trading days (~14 calendar)
    lag = (stale["date"] - stale["opt_date"]).dt.days
    for c in OPT_FEATS:
        stale.loc[lag > 14, c] = np.nan
    print("expectations features...")
    exp = expectations_monthly()
    full = stale.merge(exp, on=["permno", "month"], how="left")
    cov = {c: round(float(full[c].notna().mean()), 3)
           for c in (*OPT_FEATS, *EXP_FEATS)}
    print("coverage:", cov)

    from lightgbm import LGBMRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    arms = {"ridge": lambda: make_pipeline(
                SimpleImputer(strategy="median"), StandardScaler(),
                Ridge(alpha=1.0)),
            "lgbm": lambda: LGBMRegressor(
                n_estimators=300, num_leaves=31, learning_rate=0.05,
                random_state=20260819, verbose=-1)}

    def ic_series(feats, target, arm):
        out = []
        for y in range(2017, 2025):
            tr = full[full["date"].dt.year < y]
            te = full[full["date"].dt.year == y]
            if len(tr) < 5000 or len(te) < 1000:
                continue
            m = arms[arm]()
            m.fit(tr[feats].to_numpy(), tr[target].to_numpy())
            out.append(rank_ic_by_date(m.predict(te[feats].to_numpy()),
                                       te[target].to_numpy(),
                                       te["date"].to_numpy()))
        return pd.concat(out)

    results, cells = {}, []
    for target in ("fwd_ret", "fwd_vol"):
        for arm in arms:
            series = {}
            for rung, feats in RUNGS.items():
                series[rung] = ic_series(feats, target, arm)
            results[f"{arm}|{target}"] = {
                r: round(float(s.mean()), 4) for r, s in series.items()}
            prev = None
            for rung in RUNGS:
                if prev is not None:
                    ix = series[rung].index.intersection(
                        series[prev].index)
                    d = (series[rung].loc[ix]
                         - series[prev].loc[ix]).to_numpy(float)
                    dates = ix.to_numpy(dtype="datetime64[D]")
                    inf = block_bootstrap_paired(
                        d, dates,
                        block_days=bootstrap_block_dates(dates, 21),
                        seed=20260819).as_dict()
                    z = inf["mean"] / inf["se"] if inf["se"] > 0 else 0.0
                    p = 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))
                    cells.append({
                        "cell": f"{arm}|{target}|{prev}->{rung}",
                        "d_ic": round(inf["mean"], 5),
                        "p": round(p, 5),
                        "mde": round(inf["mde_80pct_power"], 5)})
                    print(json.dumps(cells[-1]))
                prev = rung

    ranked = sorted(cells, key=lambda c: c["p"])
    m = len(cells)
    survivors = []
    for i, c in enumerate(ranked, start=1):
        if c["p"] <= 0.10 * i / m:
            survivors = [x["cell"] for x in ranked[:i]]
    receipt = {"amendment": "NET AMENDMENT 2 ladder rungs (SCREEN)",
               "at": datetime.now(timezone.utc).isoformat(
                   timespec="seconds"),
               "basis": "PIT monthly panel (declared basis change, "
                        "disclosed)",
               "coverage": cov, "mean_ics": results,
               "rung_increments": cells,
               "bh_fdr_survivors": survivors, "m": m}
    p = OUT / "ladder_rungs_2026-08-20.json"
    p.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("mean ICs:", json.dumps(results, indent=2))
    print("survivors:", survivors)
    print("receipt:", p.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
