"""ERA-TRANSFER-1 — does the risk head's learning survive the era gap?

A standing evaluation rule added by Order 24: era transfer is a
first-class metric, run in BOTH directions, with the ratio reported.

The programme already knows its RETURN signal is era-dependent — price-
only return ICs are positive in 1990-2012 and negative in 2017-2024, the
sign flip that motivated (and then closed) the regime work. The risk side
has never been asked the same question. Rank IC ~0.80 within each era is
compatible with two very different worlds:

  - one relationship between the features and forward variance, stable
    across three decades; or
  - two era-specific relationships, each learned separately, with a model
    trained on one era useless on the other.

Only a cross-era fit can tell them apart, and the answer decides how much
a model trained today should be trusted forward.

FOUR CELLS, one feature set, one target, identical preprocessing:

    early  -> early     (within, the incumbent number)
    early  -> modern    (transfer)
    modern -> modern    (within)
    modern -> early     (transfer)

Reported per cell: rank IC, MSE(log variance), QLIKE and bias. The
headline is the TRANSFER RATIO — transfer performance over within-era
performance, in each direction. A ratio near 1 says the relationship is
shared; a ratio near 0 says each era was memorised separately.

The within-era cells here are honest holdouts, not in-sample fits: each
era's model is trained on its own first 60% of dates and evaluated on the
rest, so "within" and "transfer" are both out-of-sample and the ratio
compares like with like. Fitting within-era in-sample would inflate the
denominator and make every transfer ratio look worse than it is.

    python -m scripts.era_transfer_1

SCREEN.
"""

from __future__ import annotations

import argparse
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
from backend.services.net_tournament import (                # noqa: E402
    rank_ic_by_date)
from scripts.option_incremental_risk_1 import (              # noqa: E402
    VAR_FLOOR, WITH_OPT, build, qlike)

OUT = _config.OPTIMUS_LEDGER_DIR / "risk_ladder"
SEED = 20260820


def prep(era: str) -> pd.DataFrame:
    df = build(era)
    need = list(dict.fromkeys(list(WITH_OPT) + ["fwd_var"]))
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=need)
    return df.sort_values("date").reset_index(drop=True)


def split(df: pd.DataFrame, frac: float = 0.6):
    dates = np.sort(df["date"].unique())
    cut = dates[int(len(dates) * frac)]
    return df[df["date"] < cut], df[df["date"] >= cut], cut


def fit(tr: pd.DataFrame):
    from lightgbm import LGBMRegressor
    m = LGBMRegressor(n_estimators=300, num_leaves=31, learning_rate=0.05,
                      random_state=SEED, verbose=-1)
    m.fit(tr[list(WITH_OPT)].to_numpy(),
          np.log(tr["fwd_var"].to_numpy()))
    return m


def score(m, te: pd.DataFrame) -> dict:
    pred = np.exp(m.predict(te[list(WITH_OPT)].to_numpy()))
    a = te["fwd_var"].to_numpy()
    lr = np.log(a / np.clip(pred, VAR_FLOOR, None))
    return {"n_rows": int(len(te)),
            "mean_rank_ic": round(float(rank_ic_by_date(
                pred, a, te["date"].to_numpy()).mean()), 4),
            "mse_log_var": round(float(np.mean(lr ** 2)), 5),
            "mean_qlike": round(float(np.mean(qlike(a, pred))), 5),
            "bias_mean_log_ratio": round(float(np.mean(lr)), 5)}


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    argparse.ArgumentParser().parse_args()

    print("building early panel...")
    early = prep("early")
    print(f"  {len(early):,} rows")
    print("building modern panel...")
    modern = prep("modern")
    print(f"  {len(modern):,} rows")

    e_tr, e_te, e_cut = split(early)
    m_tr, m_te, m_cut = split(modern)
    print(f"early split at {str(e_cut)[:10]}  "
          f"train {len(e_tr):,} test {len(e_te):,}")
    print(f"modern split at {str(m_cut)[:10]}  "
          f"train {len(m_tr):,} test {len(m_te):,}")

    me, mm = fit(e_tr), fit(m_tr)
    cells = {
        "early_to_early": score(me, e_te),
        "early_to_modern": score(me, m_te),
        "modern_to_modern": score(mm, m_te),
        "modern_to_early": score(mm, e_te),
    }

    def ratio(t, w, key, lower_better=False):
        a, b = cells[t][key], cells[w][key]
        if lower_better:
            return round(float(b / a), 3) if a else None
        return round(float(a / b), 3) if b else None

    ratios = {
        "early_model_transfer_ratio": {
            "rank_ic": ratio("early_to_modern", "modern_to_modern",
                             "mean_rank_ic"),
            "mse_log_var": ratio("early_to_modern", "modern_to_modern",
                                 "mse_log_var", lower_better=True)},
        "modern_model_transfer_ratio": {
            "rank_ic": ratio("modern_to_early", "early_to_early",
                             "mean_rank_ic"),
            "mse_log_var": ratio("modern_to_early", "early_to_early",
                                 "mse_log_var", lower_better=True)},
    }

    res = {"trial": "ERA-TRANSFER-1", "mode": "SCREEN",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "features": list(WITH_OPT),
           "target": "log annualized realized variance over t+1..t+21",
           "protocol": "each era's model trained on its first 60% of "
                       "dates; BOTH within and transfer cells are "
                       "out-of-sample, so the ratio compares like with "
                       "like (an in-sample denominator would inflate the "
                       "within cell and flatter no one)",
           "splits": {"early_cut": str(e_cut)[:10],
                      "modern_cut": str(m_cut)[:10]},
           "cells": cells, "transfer_ratios": ratios,
           "contrast_with_return_side": "the price-only RETURN signal "
                                        "flips sign between these eras; "
                                        "this asks whether the RISK "
                                        "relationship does the same"}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "era_transfer_1_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"\n{'cell':20s} {'rankIC':>8s} {'MSElogV':>9s} "
          f"{'QLIKE':>9s} {'bias':>8s} {'n':>10s}")
    for k, v in cells.items():
        print(f"{k:20s} {v['mean_rank_ic']:>8.4f} {v['mse_log_var']:>9.4f} "
              f"{v['mean_qlike']:>9.4f} {v['bias_mean_log_ratio']:>+8.4f} "
              f"{v['n_rows']:>10,}")
    print("\ntransfer ratios (1.0 == transfers perfectly):")
    for k, v in ratios.items():
        print(f"  {k:30s} rank_ic {v['rank_ic']}  "
              f"mse_log_var {v['mse_log_var']}")
    print(f"\nreceipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
