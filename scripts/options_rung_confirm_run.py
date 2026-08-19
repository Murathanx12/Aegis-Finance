"""OPTIONS-RUNG-CONFIRM-1 — the +options vol increment, 2001–2012.

    python -m scripts.options_rung_confirm_run

Protocol frozen pre-download (PREREG_OPTIONS_RUNG_CONFIRM_1.md).
Features byte-identical to Amendment 2; LGBM arm; §64 masked audit
written before the verdict.
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
from backend.services.net_tournament import (assert_signed,  # noqa: E402
                                             bootstrap_block_dates,
                                             rank_ic_by_date)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)
from scripts.net_ladder_rungs_run import (OPT_FEATS,         # noqa: E402
                                          options_monthly)
from scripts.universe_survival_stress_1 import (             # noqa: E402
    FEATURES, build_monthly_dataset)

PREREG = REPO / "docs" / "TRIALS" / "PREREG_OPTIONS_RUNG_CONFIRM_1.md"
OUT = _config.OPTIMUS_LEDGER_DIR / "net_tournament"
PIT = _config.OPTIMUS_LEDGER_DIR / "crsp_pit"
BAR = 0.01


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    signer = assert_signed(PREREG)
    print("signed by:", signer[:40])
    print("early panel + options features...")
    df = build_monthly_dataset(
        years=(1990, 2012),
        univ_path=PIT / "crsp_pit_monthly_early.parquet")
    df["month"] = df["date"].dt.to_period("M")
    opt = options_monthly(years=(1996, 2012))
    full = df.merge(opt, on=["permno", "month"], how="left")
    lag = (full["date"] - full["opt_date"]).dt.days
    for c in OPT_FEATS:
        full.loc[lag > 14, c] = np.nan
    cov = {c: round(float(full[c].notna().mean()), 3) for c in OPT_FEATS}
    print("coverage:", cov)

    from lightgbm import LGBMRegressor
    rungs = {"numeric": list(FEATURES),
             "plus_options": list(FEATURES) + list(OPT_FEATS)}
    series = {}
    for rung, feats in rungs.items():
        out = []
        for y in range(2001, 2013):
            tr = full[full["date"].dt.year < y]
            te = full[full["date"].dt.year == y]
            if len(tr) < 5000 or len(te) < 1000:
                continue
            m = LGBMRegressor(n_estimators=300, num_leaves=31,
                              learning_rate=0.05,
                              random_state=20260819, verbose=-1)
            m.fit(tr[feats].to_numpy(), tr["fwd_vol"].to_numpy())
            out.append(rank_ic_by_date(m.predict(te[feats].to_numpy()),
                                       te["fwd_vol"].to_numpy(),
                                       te["date"].to_numpy()))
        series[rung] = pd.concat(out)

    ix = series["plus_options"].index.intersection(
        series["numeric"].index)
    d = (series["plus_options"].loc[ix]
         - series["numeric"].loc[ix]).to_numpy(float)
    dates = ix.to_numpy(dtype="datetime64[D]")
    inf = block_bootstrap_paired(
        d, dates, block_days=bootstrap_block_dates(dates, 21),
        seed=20260819).as_dict()
    audit = {"n_dates": int(len(ix)),
             "n_effective": inf["n_effective"],
             "se": round(inf["se"], 6),
             "mde": round(inf["mde_80pct_power"], 6), "bar": BAR,
             "useless_limb_answerable":
                 bool(inf["mde_80pct_power"] <= BAR)}
    (OUT / "options_rung_audit_2026-08-20.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8")
    print("audit:", json.dumps(audit))

    mean, mde = inf["mean"], inf["mde_80pct_power"]
    z = mean / inf["se"] if inf["se"] > 0 else 0.0
    p = 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))
    if mean > 0 and mean >= mde:
        verdict = "OPTIONS_RUNG_CONFIRMED"
    elif mde <= BAR and inf["ci_hi"] < BAR:
        verdict = "RUNG_USELESS"
    else:
        verdict = "NOT_ESTABLISHED"
    receipt = {"trial": "OPTIONS-RUNG-CONFIRM-1", "mode": "REGISTERED",
               "signed_by": signer,
               "at": datetime.now(timezone.utc).isoformat(
                   timespec="seconds"),
               "coverage": cov,
               "mean_ics": {r: round(float(s.mean()), 4)
                            for r, s in series.items()},
               "primary": {"d_ic": round(mean, 5), "p": round(p, 6),
                           "contrast": inf, "verdict": verdict}}
    pth = OUT / "options_rung_trial_2026-08-20.json"
    pth.write_text(json.dumps(receipt, indent=2, default=str),
                   encoding="utf-8")
    print(f"PRIMARY: {verdict}  dIC {mean:+.4f}  mde {mde:.4f}  "
          f"p {p:.5f}  ICs {receipt['mean_ics']}")
    print("receipt:", pth.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
