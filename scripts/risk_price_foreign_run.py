"""RISK-PRICE-FOREIGN-1 runner.

    python -m scripts.risk_price_foreign_run

Protocol: docs/TRIALS/PREREG_RISK_PRICE_FOREIGN_1.md (frozen before any
model IC on any foreign row). FOREIGN grade — no confirm authority; the
§64 masked audit (including the measured cross-country dependence the
power arithmetic assumed) is written before any verdict.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services.net_tournament import (assert_signed,  # noqa: E402
                                             bootstrap_block_dates,
                                             head_verdicts)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)
from scripts.wrds_pull_jkp_full import FOREIGN               # noqa: E402

TRIAL = "RISK-PRICE-FOREIGN-1"
PREREG = REPO / "docs" / "TRIALS" / "PREREG_RISK_PRICE_FOREIGN_1.md"
SRC = _config.OPTIMUS_LEDGER_DIR / "wrds" / "jkp_full"
OUT = _config.OPTIMUS_LEDGER_DIR / "aegis_panel"
ECONOMIC_BAR = 0.01
SEED = 20260819
MIN_TRAIN = 100_000
MIN_NAMES = 50
LABEL = "ret_exc_lead1m"

FLOOR = ["ret_1_0", "ret_12_1", "ret_12_7", "rvol_21d", "rvol_252d"]
RISK = ["beta_21d", "beta_252d", "beta_60m", "beta_dimson_21d",
        "betabab_1260d", "betadown_252d", "corr_1260d", "ivol_capm_21d",
        "ivol_capm_60m", "ivol_capm_252d", "ivol_ff3_21d",
        "ivol_hxz4_21d", "iskew_capm_21d", "iskew_ff3_21d",
        "iskew_hxz4_21d", "coskew_21d", "rskew_21d", "rmax1_21d",
        "rmax5_21d", "rmax5_rvol_21d", "mispricing_perf",
        "mispricing_mgmt"]


def load() -> pd.DataFrame:
    parts = []
    for c in FOREIGN:
        p = SRC / f"jkp_risk_{c.lower()}_2013_2024.parquet"
        df = pd.read_parquet(p)
        df["country"] = c
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    df = df[(df["common"] == 1) & (df["obs_main"] == 1)
            & (df["primary_sec"] == 1)]
    df["month"] = pd.to_datetime(df["eom"]).dt.to_period("M")
    med = df.groupby(["country", "month"])["me"].transform("median")
    df = df[df["me"] >= med]
    df = df[df[LABEL].notna()].dropna(subset=FLOOR)
    return df.reset_index(drop=True)


def country_month_ics(pred: np.ndarray, te: pd.DataFrame
                      ) -> pd.DataFrame:
    from scipy.stats import spearmanr
    te = te.assign(_pred=pred)
    rows, refused = [], 0
    for (ctry, m), g in te.groupby(["country", "month"]):
        if len(g) < MIN_NAMES:
            refused += 1
            continue
        ic = spearmanr(g["_pred"], g[LABEL]).statistic
        rows.append({"country": ctry, "month": m, "ic": float(ic)})
    out = pd.DataFrame(rows)
    out.attrs["refused"] = refused
    return out


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    from lightgbm import LGBMRegressor

    signer = assert_signed(PREREG)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    df = load()
    print(f"{TRIAL}  signer: {signer[:30]}")
    print(f"rows {len(df):,}  months {df['month'].nunique()}  "
          f"countries {df['country'].nunique()}")

    arms = {"floor_jkp": FLOOR, "riskprice_jkp": FLOOR + RISK}
    cm: dict[str, list] = {a: [] for a in arms}
    n_refused = 0
    for y in range(2016, 2025):
        jan = pd.Period(f"{y}-01", freq="M")
        tr = df[df["month"] + 1 < jan]
        te = df[df["month"].dt.year == y]
        if len(tr) < MIN_TRAIN or not len(te):
            print(f"  fold {y} REFUSED (train {len(tr)})")
            continue
        for a, cols in arms.items():
            t0 = time.perf_counter()
            m = LGBMRegressor(n_estimators=300, num_leaves=31,
                              learning_rate=0.05, random_state=SEED,
                              verbose=-1)
            m.fit(tr[cols].to_numpy(), tr[LABEL].to_numpy())
            ics = country_month_ics(m.predict(te[cols].to_numpy()), te)
            n_refused += ics.attrs["refused"]
            cm[a].append(ics)
            print(f"  {y} {a:15s} mean country-month ic "
                  f"{ics['ic'].mean():+.4f} "
                  f"({time.perf_counter() - t0:5.1f}s)", flush=True)

    per = {a: pd.concat(v) for a, v in cm.items()}
    # paired per-country-month dIC, then the cross-country mean per month
    j = per["riskprice_jkp"].merge(per["floor_jkp"],
                                   on=["country", "month"],
                                   suffixes=("_r", "_f"))
    j["d"] = j["ic_r"] - j["ic_f"]
    monthly = j.groupby("month").agg(d=("d", "mean"),
                                     n_countries=("d", "size"))
    d = monthly["d"].to_numpy(float)
    dates = np.array([m.to_timestamp(how="end").date()
                      for m in monthly.index], dtype="datetime64[D]")
    block = bootstrap_block_dates(dates, 21)
    inf = block_bootstrap_paired(d, dates, block_days=block,
                                 seed=SEED).as_dict()
    inf["block_days_derived"] = block
    inf["n_months"] = int(len(monthly))

    # measured cross-country dependence — the assumption the prereg's
    # power arithmetic declared, now measured before any verdict
    wide = j.pivot_table(index="month", columns="country", values="d")
    cmat = wide.corr()
    n_c = cmat.shape[0]
    rho_bar = float((cmat.values[np.triu_indices(n_c, 1)]).mean())
    k_eff = n_c / (1.0 + (n_c - 1) * max(rho_bar, 0.0))

    masked = {k: v for k, v in inf.items() if k != "mean"}
    audit = {"audit": f"{TRIAL} §64 (mean masked here)", "at": stamp,
             **masked, "economic_bar": ECONOMIC_BAR,
             "country_months_refused_thin": n_refused,
             "cross_country_mean_rho": round(rho_bar, 3),
             "effective_independent_markets": round(k_eff, 2),
             "declared_assumption_was": "k_eff ~ 4",
             "win_limb_answerable": True,
             "noninferior_limb_answerable":
                 bool(inf["mde_80pct_power"] <= ECONOMIC_BAR)}
    (OUT / "risk_price_foreign_audit.json").write_text(
        json.dumps(audit, indent=2, default=str), encoding="utf-8")
    print("§64:", json.dumps({k: audit[k] for k in
                              ("n_months", "se", "mde_80pct_power",
                               "cross_country_mean_rho",
                               "effective_independent_markets",
                               "noninferior_limb_answerable")},
                             default=str))

    v = head_verdicts({"c": inf}, economic_bar=ECONOMIC_BAR)["c"]
    relabel = {"COMPLEX_WINS": "NOT_US_ONLY",
               "LINEAR_NONINFERIOR": "US_LOCAL",
               "NOT_ESTABLISHED": "NOT_ESTABLISHED"}
    v["verdict"] = relabel[v["verdict"]]

    screen = {"per_country": {}}
    for ctry, g in j.groupby("country"):
        dd = g.sort_values("month")
        dts = np.array([m.to_timestamp(how="end").date()
                        for m in dd["month"]], dtype="datetime64[D]")
        ci = block_bootstrap_paired(dd["d"].to_numpy(float), dts,
                                    block_days=block, seed=SEED).as_dict()
        screen["per_country"][ctry] = {
            "mean_dIC": round(ci["mean"], 4),
            "se": round(ci["se"], 4), "n_months": int(len(dd))}
    screen["pooled_ic"] = {a: round(float(per[a]["ic"].mean()), 5)
                           for a in per}
    screen["d_by_year"] = {int(y): round(float(g["d"].mean()), 4)
                           for y, g in j.groupby(
                               j["month"].dt.year)}

    receipt = {"trial": TRIAL, "mode": "REGISTERED", "grade": "FOREIGN",
               "at": stamp, "signed_by": signer,
               "primary": {"cell": "cross-country mean paired dIC "
                                   "(riskprice_jkp - floor_jkp)",
                           "contrast": inf, "verdict": v},
               "screen": screen,
               "no_confirm_note": "R13e: same-era foreign slice — a "
                                  "NOT_US_ONLY verdict licenses one "
                                  "FORWARD registration and nothing "
                                  "else"}
    p = OUT / "risk_price_foreign_trial.json"
    p.write_text(json.dumps(receipt, indent=2, default=str),
                 encoding="utf-8")
    print(f"PRIMARY: {v['verdict']}  dIC {inf['mean']:+.4f} "
          f"(mde {inf['mde_80pct_power']:.4f})")
    print("per-country:", json.dumps({k: s["mean_dIC"] for k, s in
                                      screen["per_country"].items()}))
    print("receipt:", p.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
