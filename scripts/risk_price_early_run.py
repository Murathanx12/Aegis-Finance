"""RISK-PRICE-EARLY-1 runner.

    python -m scripts.risk_price_early_run                 # deciding (early)
    python -m scripts.risk_price_early_run --modern-cell   # SCREEN cell

Protocol: docs/TRIALS/PREREG_RISK_PRICE_EARLY_1.md (frozen before any
early-era model IC on these features). §64 masked audit precedes the
verdict; the modern consistency cell is SCREEN and never pools into the
deciding statistic.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services import risk_price_features as RPF      # noqa: E402
from backend.services.aegis_panel import (_floor_frame,      # noqa: E402
                                          _spine_labels, FLOOR_FEATURES)
from backend.services.lane_factory_sim import load_panel     # noqa: E402
from backend.services.net_tournament import (assert_signed,  # noqa: E402
                                             bootstrap_block_dates,
                                             head_verdicts,
                                             rank_ic_by_date)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)

TRIAL = "RISK-PRICE-EARLY-1"
PREREG = REPO / "docs" / "TRIALS" / "PREREG_RISK_PRICE_EARLY_1.md"
OUT = _config.OPTIMUS_LEDGER_DIR / "aegis_panel"
PIT_DIR = _config.OPTIMUS_LEDGER_DIR / "crsp_pit"
ECONOMIC_BAR = 0.01
SEED = 20260819
MIN_TRAIN = 20_000
LABEL = "ret_1m_fwd"


def build_dataset(era: str) -> pd.DataFrame:
    if era == "early":
        years, univ = (1990, 2012), PIT_DIR / "crsp_pit_monthly_early.parquet"
    else:
        years, univ = (2013, 2024), PIT_DIR / "crsp_pit_monthly_v1.parquet"
    panel = load_panel(years=years, univ_path=univ)
    base = _floor_frame(panel)
    base["month"] = base["date"].dt.to_period("M")
    base = base.merge(_spine_labels(univ), on=["permno", "month"],
                      how="left")
    rp = RPF.build(years)
    rp["month"] = rp["date"].dt.to_period("M")
    df = base.merge(rp.drop(columns=["date"]), on=["permno", "month"],
                    how="left")
    cov = df[list(RPF.FEATURES)].notna().mean().mean()
    if cov < 0.80:
        raise RPF.RiskPriceRefused(
            f"risk-price join covered only {cov:.1%} of rows — a quiet "
            f"all-NaN family would run against nothing")
    return df


def walk_forward(df: pd.DataFrame, test_years) -> dict[str, pd.Series]:
    from lightgbm import LGBMRegressor
    arms = {"floor_lgbm": list(FLOOR_FEATURES),
            "riskprice_lgbm": list(FLOOR_FEATURES) + list(RPF.FEATURES)}
    ics: dict[str, list] = {a: [] for a in arms}
    for y in test_years:
        jan = pd.Period(f"{y}-01", freq="M")
        tr = df[(df["month"] + 1 < jan) & df[LABEL].notna()]
        te = df[(df["month"].dt.year == y) & df[LABEL].notna()]
        if len(tr) < MIN_TRAIN or not len(te):
            print(f"  fold {y} REFUSED (train {len(tr)}, test {len(te)})")
            continue
        for a, cols in arms.items():
            t0 = time.perf_counter()
            m = LGBMRegressor(n_estimators=300, num_leaves=31,
                              learning_rate=0.05, random_state=SEED,
                              verbose=-1)
            m.fit(tr[cols].to_numpy(), tr[LABEL].to_numpy())
            s = rank_ic_by_date(m.predict(te[cols].to_numpy()),
                                te[LABEL].to_numpy(),
                                te["date"].to_numpy())
            ics[a].append(s)
            print(f"  {y} {a:16s} ic {float(s.mean()):+.4f} "
                  f"({time.perf_counter() - t0:5.1f}s)", flush=True)
    return {a: pd.concat(v) for a, v in ics.items() if v}


def contrast(ic_a: pd.Series, ic_b: pd.Series) -> dict:
    ix = ic_a.index.intersection(ic_b.index)
    d = (ic_a.loc[ix] - ic_b.loc[ix]).to_numpy(float)
    dates = ix.to_numpy(dtype="datetime64[D]")
    block = bootstrap_block_dates(dates, 21)
    inf = block_bootstrap_paired(d, dates, block_days=block,
                                 seed=SEED).as_dict()
    inf["block_days_derived"] = block
    inf["n_dates"] = int(len(ix))
    return inf


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="risk_price_early_run")
    ap.add_argument("--modern-cell", action="store_true",
                    help="SCREEN consistency cell (2016-2024), never "
                         "pooled into the deciding statistic")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    signer = assert_signed(PREREG)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if a.modern_cell:
        print(f"{TRIAL} SCREEN modern consistency cell  signer: "
              f"{signer[:30]}")
        df = build_dataset("modern")
        print(f"rows {len(df):,}  months {df['month'].nunique()}")
        ics = walk_forward(df, range(2016, 2025))
        inf = contrast(ics["riskprice_lgbm"], ics["floor_lgbm"])
        receipt = {"trial": TRIAL, "mode": "SCREEN_MODERN_CELL",
                   "at": stamp, "signed_by": signer,
                   "contrast": inf,
                   "pooled_ic": {k: round(float(s.mean()), 5)
                                 for k, s in ics.items()},
                   "ic_by_year": {k: {int(y): round(float(g.mean()), 4)
                                      for y, g in s.groupby(s.index.year)}
                                  for k, s in ics.items()},
                   "note": "SCREEN — consistency of own-construction "
                           "features with the JKP-based parent lead; "
                           "never deciding, never pooled"}
        p = OUT / "risk_price_modern_cell.json"
        p.write_text(json.dumps(receipt, indent=2, default=str),
                     encoding="utf-8")
        print(f"MODERN CELL dIC {inf['mean']:+.4f} "
              f"(mde {inf['mde_80pct_power']:.4f})  receipt: {p.name}")
        return 0

    print(f"{TRIAL} DECIDING (early era)  signer: {signer[:30]}")
    df = build_dataset("early")
    print(f"rows {len(df):,}  months {df['month'].nunique()}  "
          f"names {df['permno'].nunique():,}")
    ics = walk_forward(df, range(1994, 2013))
    inf = contrast(ics["riskprice_lgbm"], ics["floor_lgbm"])

    masked = {k: v for k, v in inf.items() if k != "mean"}
    audit = {"audit": f"{TRIAL} §64 (mean masked here)", "at": stamp,
             **masked, "economic_bar": ECONOMIC_BAR,
             "win_limb_answerable": True,
             "noninferior_limb_answerable":
                 bool(inf["mde_80pct_power"] <= ECONOMIC_BAR)}
    (OUT / "risk_price_early_audit.json").write_text(
        json.dumps(audit, indent=2, default=str), encoding="utf-8")
    print("§64:", json.dumps({k: audit[k] for k in
                              ("n_dates", "se", "mde_80pct_power",
                               "noninferior_limb_answerable")},
                             default=str))

    v = head_verdicts({"c": inf}, economic_bar=ECONOMIC_BAR)["c"]
    relabel = {"COMPLEX_WINS": "RISKPRICE_ADDS",
               "LINEAR_NONINFERIOR": "FLOOR_NONINFERIOR",
               "NOT_ESTABLISHED": "NOT_ESTABLISHED"}
    v["verdict"] = relabel[v["verdict"]]

    receipt = {"trial": TRIAL, "mode": "REGISTERED", "at": stamp,
               "signed_by": signer,
               "era": "1994-2012 walk-forward on 1990-2012 panel",
               "primary": {"cell": "riskprice_lgbm - floor_lgbm, "
                                   "ret_1m_fwd rank IC", "contrast": inf,
                           "verdict": v},
               "pooled_ic": {k: round(float(s.mean()), 5)
                             for k, s in ics.items()},
               "ic_by_year": {k: {int(y): round(float(g.mean()), 4)
                                  for y, g in s.groupby(s.index.year)}
                              for k, s in ics.items()}}
    p = OUT / "risk_price_early_trial.json"
    p.write_text(json.dumps(receipt, indent=2, default=str),
                 encoding="utf-8")
    print(f"PRIMARY: {v['verdict']}  dIC {inf['mean']:+.4f} "
          f"(mde {inf['mde_80pct_power']:.4f})")
    print("receipt:", p.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
