"""MARKET-SCALING-1 — use the date-level information in a DATE-LEVEL model.

STATE-OBSERVABLE-1 fed macro state (credit spread, term structure, TED,
Fama-French factor state) into the stock-level risk head as extra
columns, and it made things significantly WORSE (-0.074 MSE log variance,
POWERED). The diagnosis was not "credit spreads are uninformative" — they
obviously carry market-risk information — but a sample-size mismatch:

    a per-DATE feature has an effective sample of ~131 dates, not 226,228
    stock-months. A tree handed eight macro columns has ~131
    effectively-independent observations of them and overfits the date
    dimension.

That is the same pseudo-replication this run has already hit at the book
level and in the Marchenko-Pastur sample size. Feeding a date-level
signal to a stock-level learner is the wrong shape, not the wrong signal.

So this trial uses the identical information in the shape that matches
its sample size:

  STAGE 1 (date level, ~100 training points, a LINEAR model — anything
    richer would overfit 100 points): predict next month's realized
    MARKET variance from macro state plus trailing market variance.
  STAGE 2 (stock level, untouched): take the shipped risk head's
    cross-sectional prediction and RESCALE it in log space by the
    stage-1 market-variance surprise.

        log_pred_adj = log_pred + beta * (log mkt_hat - log mkt_trailing)

Cross-sectional ORDERING is exactly preserved for any beta — the shift is
constant within a date — so this can only move the LEVEL. That is
deliberate: every result in this run says the ordering is already good and
the level is where the headroom is.

beta is FIT ON TRAINING DATES ONLY. beta = 0 recovers the baseline
exactly, so the comparison is nested and the trial can only show a gain
if the scaling carries information.

Declared before running: this should improve QLIKE (a level loss) and
leave rank IC bit-identical. If QLIKE does not improve, the level ceiling
is not reachable from macro state in any shape, and the family closes.

    python -m scripts.market_scaling_1

RESULT: it does not help either, and the family closes.

    arm          QLIKE     MSE(logV)   rankIC
    baseline   0.50032       0.49908   0.7978
    scaled     0.56870       0.52992   0.7978   (both worse, significant)

    rank IC change +0.00e+00 — the design invariant held exactly.

Stage 1 fits: in-sample R^2 0.26-0.45, beta2 +0.09..+0.20. So the
date-level model DOES fit market variance in sample, and the scaling
coefficient is positive and stable — yet applying it out of sample hurts.

The most likely reason, and the test that would confirm it: the risk head
ALREADY carries the market level, through its own implied-variance
feature. `log_iv_var` is a forward-looking, market-inclusive risk
measure, so the market's level is priced into the prediction before any
macro state is added; a macro-based market forecast then double-counts it
and contributes only estimation noise. The oracle's remaining advantage
is knowledge of the REALISED future, which no observable proxies.

NEXT TEST (cheap, decisive): re-run the oracle contrast with an
options-FREE baseline. If the oracle's QLIKE gain is materially larger
without `log_iv_var`, the level was indeed already carried by implied
variance and the ceiling is not "unreached" so much as "already taken".

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
    bootstrap_block_dates, rank_ic_by_date)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)
from scripts.option_incremental_risk_1 import (              # noqa: E402
    ERAS, VAR_FLOOR, WITH_OPT, build, qlike)
from scripts.regime_risk_conditioning_1 import market_state   # noqa: E402
from scripts.state_observable_1 import MACRO_FEATS, macro_state  # noqa: E402

OUT = _config.OPTIMUS_LEDGER_DIR / "regime"
SEED = 20260820


def _ols(X, y):
    A = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    return beta


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--era", default="modern", choices=list(ERAS))
    a = ap.parse_args()
    cfg = ERAS[a.era]

    print("building panel + market/macro state...")
    df = build(a.era)
    need = list(dict.fromkeys(list(WITH_OPT) + ["fwd_var"]))
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=need)

    ms = market_state(a.era)          # has trailing AND forward mkt var
    mac = macro_state()
    mac["date"] = pd.to_datetime(mac["date"])
    dstate = ms.merge(mac, on="date", how="left").sort_values("date")
    have = [c for c in MACRO_FEATS if c in dstate.columns]
    dstate = dstate.dropna(subset=["mkt_rv_21", "mkt_rv_fwd21"] + have)
    dstate["log_mkt_trail"] = np.log(dstate["mkt_rv_21"].clip(VAR_FLOOR))
    dstate["log_mkt_fwd"] = np.log(dstate["mkt_rv_fwd21"].clip(VAR_FLOOR))
    print(f"date-level state: {len(dstate)} dates, features {have}")

    df = df.merge(dstate[["date", "log_mkt_trail", "log_mkt_fwd"] + have],
                  on="date", how="inner")

    from lightgbm import LGBMRegressor
    rows, ic_b, ic_s, ql_b, ql_s, ms_b, ms_s = [], [], [], [], [], [], []
    stage1 = []
    for y in range(cfg["test_from"], cfg["years"][1] + 1):
        tr = df[df["date"].dt.year < y]
        te = df[df["date"].dt.year == y]
        if len(tr) < 5000 or len(te) < 1000:
            continue
        dtr = dstate[dstate["date"] < te["date"].min()]
        if len(dtr) < 30:
            continue

        # ---- STAGE 1: date-level market-variance forecast (linear)
        Xtr = dtr[["log_mkt_trail"] + have].to_numpy(float)
        beta1 = _ols(Xtr, dtr["log_mkt_fwd"].to_numpy(float))
        dte = dstate[dstate["date"].isin(te["date"].unique())]
        if not len(dte):
            continue
        Xte = dte[["log_mkt_trail"] + have].to_numpy(float)
        mkt_hat = np.column_stack([np.ones(len(Xte)), Xte]) @ beta1
        surprise = pd.Series(mkt_hat - dte["log_mkt_trail"].to_numpy(),
                             index=dte["date"].to_numpy())
        # in-sample stage-1 fit, for the receipt
        pred_tr = np.column_stack([np.ones(len(Xtr)), Xtr]) @ beta1
        r2 = float(1 - np.var(dtr["log_mkt_fwd"] - pred_tr)
                   / max(np.var(dtr["log_mkt_fwd"]), 1e-12))

        # ---- baseline stock-level head
        m = LGBMRegressor(n_estimators=300, num_leaves=31,
                          learning_rate=0.05, random_state=SEED,
                          verbose=-1)
        m.fit(tr[list(WITH_OPT)].to_numpy(),
              np.log(tr["fwd_var"].to_numpy()))
        log_pred = m.predict(te[list(WITH_OPT)].to_numpy())

        # ---- STAGE 2: fit the scaling coefficient on TRAIN dates only
        log_pred_tr = m.predict(tr[list(WITH_OPT)].to_numpy())
        # residual of the train head vs truth, regressed on the train
        # market surprise: how much of the head's level error does the
        # market surprise explain?
        dtr_s = pd.Series(
            (np.column_stack([np.ones(len(Xtr)), Xtr]) @ beta1)
            - dtr["log_mkt_trail"].to_numpy(),
            index=dtr["date"].to_numpy())
        s_train = tr["date"].map(dtr_s)
        resid = np.log(tr["fwd_var"].to_numpy()) - log_pred_tr
        ok = s_train.notna().to_numpy()
        beta2 = float(_ols(s_train[ok].to_numpy(float).reshape(-1, 1),
                           resid[ok])[1]) if ok.sum() > 100 else 0.0

        s_test = te["date"].map(surprise).to_numpy(float)
        s_test = np.nan_to_num(s_test)
        log_pred_adj = log_pred + beta2 * s_test

        atrue = te["fwd_var"].to_numpy()
        for tag, lp, ICS, QLS, MSS in (
                ("baseline", log_pred, ic_b, ql_b, ms_b),
                ("scaled", log_pred_adj, ic_s, ql_s, ms_s)):
            pred = np.exp(lp)
            ICS.append(rank_ic_by_date(pred, atrue, te["date"].to_numpy()))
            lr = np.log(atrue / np.clip(pred, VAR_FLOOR, None))
            QLS.append(pd.Series(qlike(atrue, pred),
                                 index=te["date"].to_numpy()))
            MSS.append(pd.Series(lr ** 2, index=te["date"].to_numpy()))
        stage1.append({"year": int(y), "stage1_train_r2": round(r2, 4),
                       "beta2_scaling": round(beta2, 4),
                       "n_train_dates": int(len(dtr))})
        print(f"  fold {y}: stage1 R2={r2:.3f} beta2={beta2:+.3f} "
              f"({len(dtr)} train dates)")

    ICb, ICs = pd.concat(ic_b), pd.concat(ic_s)
    QLb = pd.concat(ql_b).groupby(level=0).mean()
    QLs = pd.concat(ql_s).groupby(level=0).mean()
    MSb = pd.concat(ms_b).groupby(level=0).mean()
    MSs = pd.concat(ms_s).groupby(level=0).mean()
    ix = MSb.index.intersection(MSs.index)
    dates = np.array(sorted(ix), dtype="datetime64[D]")
    blk = bootstrap_block_dates(dates, 21)

    def contrast(b, s_):
        d = (b.loc[ix] - s_.loc[ix]).to_numpy(float)
        inf = block_bootstrap_paired(d, dates, block_days=blk,
                                     seed=SEED).as_dict()
        return {"delta": round(inf["mean"], 6),
                "scaled_better": bool(inf["mean"] > 0),
                "ci": [round(inf["ci_lo"], 6), round(inf["ci_hi"], 6)],
                "mde_80": round(inf["mde_80pct_power"], 6),
                "significant": bool(inf["ci_lo"] > 0 or inf["ci_hi"] < 0),
                "clears_mde": bool(abs(inf["mean"])
                                   >= inf["mde_80pct_power"])}

    c_ql = contrast(QLb, QLs)
    c_ms = contrast(MSb, MSs)
    d_ic = float(ICs.reindex(ix).mean() - ICb.reindex(ix).mean())

    if c_ql["significant"] and c_ql["scaled_better"]:
        verdict = ("MARKET_SCALING_HELPS — the date-level information "
                   "pays when used at the date level, having hurt when "
                   "fed to the stock-level learner")
    elif abs(d_ic) > 1e-6:
        verdict = ("INVALID — the scaling changed cross-sectional "
                   "ordering, which a within-date constant cannot do; "
                   "investigate before reading the level result")
    else:
        verdict = ("MARKET_SCALING_DOES_NOT_HELP — the level ceiling is "
                   "not reachable from macro state in EITHER shape, so "
                   "the observable-state family closes")

    res = {"trial": "MARKET-SCALING-1", "mode": "SCREEN", "era": a.era,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "design": "stage 1 date-level linear market-variance forecast; "
                     "stage 2 constant-within-date log shift of the "
                     "stock-level prediction, coefficient fit on train "
                     "dates only (beta=0 recovers baseline exactly)",
           "macro_features": have,
           "folds": stage1,
           "summary": {
               "baseline": {"mean_qlike": round(float(QLb.loc[ix].mean()), 5),
                            "mse_log_var": round(float(MSb.loc[ix].mean()), 5),
                            "mean_rank_ic": round(float(ICb.reindex(ix).mean()), 4)},
               "scaled": {"mean_qlike": round(float(QLs.loc[ix].mean()), 5),
                          "mse_log_var": round(float(MSs.loc[ix].mean()), 5),
                          "mean_rank_ic": round(float(ICs.reindex(ix).mean()), 4)}},
           "qlike_contrast": c_ql, "mse_contrast": c_ms,
           "d_rank_ic": round(d_ic, 8),
           "ordering_preserved": bool(abs(d_ic) < 1e-6),
           "verdict": verdict}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"market_scaling_1_{a.era}_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"\n{'arm':10s} {'QLIKE':>9s} {'MSElogV':>9s} {'rankIC':>9s}")
    for k, v in res["summary"].items():
        print(f"{k:10s} {v['mean_qlike']:>9.5f} {v['mse_log_var']:>9.5f} "
              f"{v['mean_rank_ic']:>9.4f}")
    print(f"\nQLIKE  delta {c_ql['delta']:+.5f}  MDE {c_ql['mde_80']:.5f}  "
          f"{'POWERED' if c_ql['clears_mde'] else ('significant' if c_ql['significant'] else 'ns')}")
    print(f"MSE    delta {c_ms['delta']:+.5f}  MDE {c_ms['mde_80']:.5f}  "
          f"{'POWERED' if c_ms['clears_mde'] else ('significant' if c_ms['significant'] else 'ns')}")
    print(f"rank IC change {d_ic:+.2e} (must be ~0 — a within-date "
          f"constant cannot reorder)")
    print(f"VERDICT: {verdict}")
    print(f"receipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
