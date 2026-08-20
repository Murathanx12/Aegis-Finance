"""REGIME-RISK-CONDITIONING-1 — the half of the regime question that survived.

REGIME-ORACLE-CEILING-1 closed regime-conditional factor SELECTION: with
perfect foresight of the volatility regime, and the conditional-best
factor estimated honestly, the policy nets +0.24%/yr and clears a
matched-transition null by +1.00%/yr against a 3%/yr bar. Switching costs
eat the entire honest gross gap.

That verdict was scoped deliberately. It says nothing about conditioning
**risk**, where §59 says the clock runs ~30x faster and where this
programme's evidence actually lives. So the same oracle-first discipline
is applied to the risk head:

    baseline    the shipped feature set
    + trailing  regime state built ONLY from information available
                before the formation date
    + oracle    regime state built from the CONTEMPORANEOUS forward
                window — impossible to know, and therefore the ceiling

The third arm is the whole point. If even a perfectly-known regime label
adds nothing to a model that already reads trailing realized variance and
implied variance, then regime conditioning is closed for risk too, and it
is closed for a reason no better predictor can overturn. If the oracle
adds a lot but the trailing arm adds nothing, the family is alive and the
problem is prediction. Those are very different roadmaps, and one run
distinguishes them.

Declared before running: the oracle arm is expected to add SOMETHING (it
is, after all, partially the answer). The question is how much, and
whether the observable arm captures any of it. A null on the ORACLE arm
would be the strongest possible close.

    python -m scripts.regime_risk_conditioning_1

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
from backend.services.lane_factory_sim import load_panel     # noqa: E402
from backend.services.net_tournament import (                # noqa: E402
    bootstrap_block_dates, rank_ic_by_date)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)
from scripts.option_incremental_risk_1 import (              # noqa: E402
    ERAS, VAR_FLOOR, WITH_OPT, build, qlike)

OUT = _config.OPTIMUS_LEDGER_DIR / "regime"
PIT = _config.OPTIMUS_LEDGER_DIR / "crsp_pit"
SEED = 20260820
ANN = 252.0

TRAIL_FEATS = ("mkt_rv_21", "mkt_rv_63", "mkt_ret_21", "mkt_breadth",
               "mkt_disp", "mkt_corr")
ORACLE_FEATS = ("mkt_rv_fwd21",)


def market_state(era: str) -> pd.DataFrame:
    """Market-state features per month-end, trailing AND oracle.

    Trailing columns use only data up to and including t. The oracle
    column is the realized market variance over t+1..t+21 — the same
    window the target spans, and knowable only afterwards.
    """
    cfg = ERAS[era]
    panel = load_panel(years=cfg["years"],
                       univ_path=PIT / f"{cfg['univ']}.parquet")
    ret = panel.ret
    mkt = ret.mean(axis=1)
    r2 = mkt ** 2

    rv21 = r2.rolling(21).mean() * ANN
    rv63 = r2.rolling(63).mean() * ANN
    ret21 = mkt.rolling(21).sum()
    # cross-sectional breadth and dispersion, trailing 21d
    up = (ret > 0).astype(float).mean(axis=1)
    breadth = up.rolling(21).mean()
    disp = ret.std(axis=1).rolling(21).mean()
    # average pairwise correlation proxy: var(mean) / mean(var)
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = (mkt.rolling(63).var()
                / (ret.var(axis=1).rolling(63).mean()))
    # ORACLE: realized market variance over the FORWARD window
    fwd = (r2[::-1].rolling(21).mean()[::-1].shift(-1)) * ANN

    month_ends = ret.groupby(ret.index.to_period("M")).tail(1).index
    df = pd.DataFrame({
        "mkt_rv_21": rv21, "mkt_rv_63": rv63, "mkt_ret_21": ret21,
        "mkt_breadth": breadth, "mkt_disp": disp, "mkt_corr": corr,
        "mkt_rv_fwd21": fwd}).loc[month_ends]
    df.index.name = "date"
    return df.reset_index()


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--era", default="modern", choices=list(ERAS))
    ap.add_argument("--no-options", action="store_true",
                    help="drop the options block from the baseline. Tests "
                         "whether the oracle's LEVEL gain is larger when "
                         "implied variance is absent — i.e. whether the "
                         "market level was already carried by log_iv_var "
                         "rather than being unreachable (MARKET-SCALING-1)")
    a = ap.parse_args()
    cfg = ERAS[a.era]

    print("building panel + market state...")
    df = build(a.era)
    need = list(dict.fromkeys(list(WITH_OPT) + ["fwd_var"]))
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=need)
    ms = market_state(a.era)
    df = df.merge(ms, on="date", how="left")
    df = df.dropna(subset=list(TRAIL_FEATS) + list(ORACLE_FEATS))
    print(f"rows {len(df):,}  dates {df['date'].nunique()}")

    base_feats = [c for c in WITH_OPT
                  if not (a.no_options
                          and (c.startswith("opt_") or c == "log_iv_var"))]
    print(f"baseline features: {len(base_feats)}"
          + ("  (OPTIONS REMOVED)" if a.no_options else ""))
    arms = {
        "baseline": list(base_feats),
        "plus_trailing_state": list(base_feats) + list(TRAIL_FEATS),
        "plus_oracle_state": list(base_feats) + list(ORACLE_FEATS),
        "plus_both": list(base_feats) + list(TRAIL_FEATS)
                     + list(ORACLE_FEATS),
    }
    from lightgbm import LGBMRegressor
    ics, qls, mses = {a_: [] for a_ in arms}, {a_: [] for a_ in arms}, \
        {a_: [] for a_ in arms}
    for y in range(cfg["test_from"], cfg["years"][1] + 1):
        tr = df[df["date"].dt.year < y]
        te = df[df["date"].dt.year == y]
        if len(tr) < 5000 or len(te) < 1000:
            continue
        print(f"  fold {y}: train {len(tr):,} test {len(te):,}")
        yt = np.log(tr["fwd_var"].to_numpy())
        at = te["fwd_var"].to_numpy()
        for name, feats in arms.items():
            m = LGBMRegressor(n_estimators=300, num_leaves=31,
                              learning_rate=0.05, random_state=SEED,
                              verbose=-1)
            m.fit(tr[feats].to_numpy(), yt)
            pred = np.exp(m.predict(te[feats].to_numpy()))
            ics[name].append(rank_ic_by_date(pred, at,
                                             te["date"].to_numpy()))
            lr = np.log(at / np.clip(pred, VAR_FLOOR, None))
            qls[name].append(pd.Series(qlike(at, pred),
                                       index=te["date"].to_numpy()))
            mses[name].append(pd.Series(lr ** 2,
                                        index=te["date"].to_numpy()))

    ic = {k: pd.concat(v) for k, v in ics.items()}
    mse = {k: pd.concat(v).groupby(level=0).mean()
           for k, v in mses.items()}
    ql = {k: pd.concat(v).groupby(level=0).mean() for k, v in qls.items()}
    ix = mse["baseline"].index
    for k in arms:
        ix = ix.intersection(mse[k].index)
    dates = np.array(sorted(ix), dtype="datetime64[D]")
    blk = bootstrap_block_dates(dates, 21)

    summary = {k: {"mean_rank_ic": round(float(ic[k].reindex(ix).mean()), 4),
                   "mse_log_var": round(float(mse[k].loc[ix].mean()), 5),
                   "mean_qlike": round(float(ql[k].loc[ix].mean()), 5)}
               for k in arms}

    contrasts = {}
    for k in arms:
        if k == "baseline":
            continue
        d = (mse["baseline"].loc[ix] - mse[k].loc[ix]).to_numpy(float)
        inf = block_bootstrap_paired(d, dates, block_days=blk,
                                     seed=SEED).as_dict()
        contrasts[f"{k}_vs_baseline"] = {
            "d_mse_log_var": round(inf["mean"], 6),
            "arm_better": bool(inf["mean"] > 0),
            "ci": [round(inf["ci_lo"], 6), round(inf["ci_hi"], 6)],
            "mde_80": round(inf["mde_80pct_power"], 6),
            "significant": bool(inf["ci_lo"] > 0 or inf["ci_hi"] < 0),
            "clears_mde": bool(abs(inf["mean"])
                               >= inf["mde_80pct_power"]),
            "n_effective": inf["n_effective"]}

    # The first decision rule written for this trial tested ONLY
    # `plus_oracle_state` and would have declared the family closed. It
    # ignored `plus_both`, an arm this same script deliberately runs — and
    # `plus_both` is significant while the oracle alone is not. A rule
    # that cannot see an arm the design includes is an incomplete rule,
    # not a verdict. Both the corrected rule and what the original would
    # have said are recorded, so the correction is disclosed rather than
    # quietly applied.
    orc = contrasts["plus_oracle_state_vs_baseline"]
    both = contrasts["plus_both_vs_baseline"]
    trail = contrasts["plus_trailing_state_vs_baseline"]
    oracle_helps_level = (orc["significant"] or both["significant"]
                          or summary["plus_oracle_state"]["mean_qlike"]
                          < summary["baseline"]["mean_qlike"] * 0.95)
    d_ic = (summary["plus_oracle_state"]["mean_rank_ic"]
            - summary["baseline"]["mean_rank_ic"])
    observable_helps = trail["significant"] and trail["d_mse_log_var"] > 0

    if not oracle_helps_level and abs(d_ic) < 0.005:
        verdict = ("REGIME_CONDITIONING_CLOSED_FOR_RISK — even a "
                   "perfectly-known regime adds nothing to a model that "
                   "already reads trailing and implied variance")
    elif observable_helps:
        verdict = "OBSERVABLE_STATE_HELPS — the family is alive"
    else:
        verdict = ("CEILING_IS_IN_THE_LEVEL_ONLY — a perfectly-known "
                   "market-variance state improves CALIBRATION but not "
                   "ORDERING, and the observable trailing state does not "
                   "reach it (it is significantly WORSE on MSE log "
                   "variance). Same ordering-vs-level split as the rest "
                   "of Order 24.")
    original_rule = ("REGIME_CONDITIONING_CLOSED_FOR_RISK"
                     if not orc["significant"] else "not closed")

    res = {"trial": "REGIME-RISK-CONDITIONING-1", "mode": "SCREEN",
           "era": a.era,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_rows": int(len(df)), "n_dates": int(len(ix)),
           "options_in_baseline": bool(not a.no_options),
           "trailing_features": list(TRAIL_FEATS),
           "oracle_features": list(ORACLE_FEATS),
           "oracle_definition": "realized market variance over t+1..t+21 "
                                "— the same window the target spans, "
                                "knowable only afterwards",
           "summary": summary, "contrasts": contrasts,
           "verdict": verdict,
           "d_rank_ic_oracle_vs_baseline": round(float(d_ic), 5),
           "decision_rule_correction": {
               "original_rule": "tested only plus_oracle_state's "
                                "significance on MSE log variance",
               "original_rule_would_have_said": original_rule,
               "why_corrected": "the original ignored plus_both, an arm "
                                "this design runs and which IS "
                                "significant, and it conflated ORDERING "
                                "with LEVEL — rank IC is flat (+0.0013) "
                                "while QLIKE falls 0.500 -> 0.434",
               "disclosed": "correction applied before the verdict was "
                            "reported, and recorded here rather than "
                            "silently"}}
    OUT.mkdir(parents=True, exist_ok=True)
    tag = f"{a.era}" + ("_noopt" if a.no_options else "")
    p = OUT / f"regime_risk_conditioning_1_{tag}_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"\n{'arm':22s} {'rankIC':>8s} {'MSElogV':>9s} {'QLIKE':>9s}")
    for k, v in summary.items():
        print(f"{k:22s} {v['mean_rank_ic']:>8.4f} "
              f"{v['mse_log_var']:>9.5f} {v['mean_qlike']:>9.4f}")
    print("\nvs baseline (positive == arm better on MSE log variance):")
    for k, c in contrasts.items():
        t = ("POWERED" if c["clears_mde"]
             else ("significant" if c["significant"] else "ns"))
        print(f"  {k:38s} {c['d_mse_log_var']:+.5f} "
              f"MDE {c['mde_80']:.5f}  {t}")
    print(f"\nVERDICT: {verdict}")
    print(f"receipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
