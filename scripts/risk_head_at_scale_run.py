"""RISK-HEAD-AT-SCALE-1 runner — LGBM vs ridge vol ordering, 1994–2012.

    python -m scripts.risk_head_at_scale_run

Protocol: docs/TRIALS/PREREG_RISK_HEAD_AT_SCALE_1.md (frozen before any
early-era model IC existed). §64 masked audit is written BEFORE the
verdict inside this runner; hyperparameters are the tournament's,
verbatim, imported from the modern-era stress script.
"""

from __future__ import annotations

import json
import sys
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
                                             head_verdicts,
                                             rank_ic_by_date)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)
from scripts.universe_survival_stress_1 import (             # noqa: E402
    FEATURES, build_monthly_dataset)

PREREG = REPO / "docs" / "TRIALS" / "PREREG_RISK_HEAD_AT_SCALE_1.md"
OUT = _config.OPTIMUS_LEDGER_DIR / "net_tournament"
PIT_DIR = _config.OPTIMUS_LEDGER_DIR / "crsp_pit"


def _arms():
    from lightgbm import LGBMRegressor
    from sklearn.linear_model import Ridge
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return {
        "ridge": lambda: make_pipeline(StandardScaler(),
                                       Ridge(alpha=1.0)),
        "lgbm": lambda: LGBMRegressor(n_estimators=300, num_leaves=31,
                                      learning_rate=0.05,
                                      random_state=20260819, verbose=-1),
        "mlp_2x64": lambda: make_pipeline(
            StandardScaler(),
            MLPRegressor(hidden_layer_sizes=(64, 64), max_iter=200,
                         random_state=20260819)),
    }


def ic_series(df: pd.DataFrame, target: str) -> dict[str, pd.Series]:
    arms = _arms()
    out = {a: [] for a in arms}
    for y in range(1994, 2013):
        tr = df[df["date"].dt.year < y]
        te = df[df["date"].dt.year == y]
        if len(tr) < 5000 or len(te) < 1000:
            continue
        Xtr = tr[list(FEATURES)].to_numpy()
        ytr = tr[target].to_numpy()
        Xte = te[list(FEATURES)].to_numpy()
        for a, mk in arms.items():
            m = mk()
            m.fit(Xtr, ytr)
            s = rank_ic_by_date(m.predict(Xte), te[target].to_numpy(),
                                te["date"].to_numpy())
            out[a].append(s)
    return {a: pd.concat(v) for a, v in out.items()}


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    signer = assert_signed(PREREG)
    print("signed by:", signer[:40])
    print("building early-era monthly dataset...")
    df = build_monthly_dataset(
        years=(1990, 2012),
        univ_path=PIT_DIR / "crsp_pit_monthly_early.parquet")
    print(f"rows {len(df):,}  months {df['date'].nunique()}  "
          f"names {df['permno'].nunique():,}")

    print("walk-forward vol ICs (primary)...")
    vol = ic_series(df, "fwd_vol")
    ix = vol["lgbm"].index.intersection(vol["ridge"].index)
    d = (vol["lgbm"].loc[ix] - vol["ridge"].loc[ix]).to_numpy(float)
    dates = ix.to_numpy(dtype="datetime64[D]")
    block = bootstrap_block_dates(dates, 21)
    inf = block_bootstrap_paired(d, dates, block_days=block,
                                 seed=20260819).as_dict()
    inf["block_days_derived"] = block

    audit = {"audit": "RISK-HEAD-AT-SCALE §64 (mean masked here)",
             "n_dates": int(len(ix)),
             "block_days": block,
             "n_effective": inf["n_effective"],
             "se": round(inf["se"], 6),
             "mde_80pct_power": round(inf["mde_80pct_power"], 6),
             "economic_bar": 0.01,
             "win_limb_answerable": True,
             "noninferior_limb_answerable":
                 bool(inf["mde_80pct_power"] <= 0.01)}
    (OUT / "risk_head_audit_2026-08-19.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))

    v = head_verdicts({"lgbm_minus_ridge": inf}, economic_bar=0.01)[
        "lgbm_minus_ridge"]
    relabel = {"COMPLEX_WINS": "LGBM_WINS",
               "LINEAR_NONINFERIOR": "RIDGE_NONINFERIOR",
               "NOT_ESTABLISHED": "NOT_ESTABLISHED"}
    v["verdict"] = relabel[v["verdict"]]

    print("screen: return-target ICs + MLP ...")
    ret = ic_series(df, "fwd_ret")
    screen = {
        "vol_mean_ic": {a: round(float(s.mean()), 4)
                        for a, s in vol.items()},
        "ret_mean_ic": {a: round(float(s.mean()), 4)
                        for a, s in ret.items()},
    }
    receipt = {"trial": "RISK-HEAD-AT-SCALE-1", "mode": "REGISTERED",
               "signed_by": signer,
               "at": datetime.now(timezone.utc).isoformat(
                   timespec="seconds"),
               "era": "1994-2012 walk-forward on 1990-2012 panel",
               "primary": {"cell": "LGBM - ridge, 21d fwd vol IC",
                           "contrast": inf, "verdict": v},
               "screen": screen}
    p = OUT / "risk_head_trial_2026-08-19.json"
    p.write_text(json.dumps(receipt, indent=2, default=str),
                 encoding="utf-8")
    print(f"PRIMARY: {v['verdict']}  mean dIC {inf['mean']:+.4f}  "
          f"mde {inf['mde_80pct_power']:.4f}")
    print("screen:", json.dumps(screen))
    print("receipt:", p.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
