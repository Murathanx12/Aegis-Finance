"""STATE-OBSERVABLE-1 — can anything OBSERVABLE reach the level ceiling?

REGIME-RISK-CONDITIONING-1 left a precise open question. A perfectly-known
market-variance state cut the risk head's QLIKE 13% (0.500 -> 0.434) while
leaving rank IC flat — so the remaining headroom is in the LEVEL, not the
ordering. But the six trailing market-state features built from the price
panel did not reach any of it; they made MSE(log variance) significantly
WORSE, adding variance without signal.

That left two possibilities, and they have opposite consequences:
the ceiling is unreachable in principle, or the right observable simply
had not been tried. The price panel can only produce price-derived state.
Macro state is a different thing entirely, and it was not available then.

It is now. This run's WRDS pass landed:
  frb.rates_daily   83 rate series back to 1954 — Aaa and Baa corporate
                    yields, fed funds, prime, long Treasury
  ff.fivefactors    the real Fama-French factors + momentum

Which gives the classic market-wide LEVEL observables the price panel
cannot express — above all the CREDIT SPREAD (Baa - Aaa), which is the
canonical market-priced measure of how risky the world currently is, and
the term structure.

ARMS, identical rows and folds, predicting log forward variance:

    baseline        the shipped risk-head features
    + macro         credit spread, its change, level, term spread,
                    fed funds, and FF factor state
    + oracle        realized market variance over t+1..t+21 — the ceiling,
                    carried forward from REGIME-RISK-CONDITIONING-1 so the
                    two runs are directly comparable
    + macro+oracle  does macro capture anything the oracle does not?

PIT DISCIPLINE, and one hazard worth naming. Fed rate series are
published same-day, so reading them at t is legitimate. Kenneth French's
factors are NOT: they are posted with a lag of days. They are therefore
lagged FF_PUBLICATION_LAG business days before use, which is the
conservative direction. Getting this wrong would manufacture exactly the
kind of level-information the trial is testing for.

    python -m scripts.state_observable_1

RESULT: the observable does NOT reach it, and adding it costs.

    arm                 rankIC   MSE(logV)   QLIKE
    baseline            0.7978     0.49918   0.5009
    plus_macro          0.7909     0.57311   0.5622   -0.074 POWERED (worse)
    plus_oracle         0.7991     0.48468   0.4337
    plus_macro_oracle   0.7976     0.49219   0.4541

The likely reason is not that credit spreads are uninformative about
market risk — they plainly are — but that a per-DATE feature has an
effective sample of ~131 dates, not 226,228 stock-months. A tree handed
eight macro columns has ~131 effectively-independent observations of them
and overfits the date dimension, which is the same pseudo-replication
that has bitten this run twice already at other levels.

So the honest next step is NOT another feature. It is a STRUCTURAL use of
the same information: forecast market variance in its own (date-level)
model and SCALE the cross-sectional prediction by it, which respects the
effective sample size instead of asking a stock-level learner to
rediscover a date-level relationship from 131 points.

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
from scripts.regime_risk_conditioning_1 import (             # noqa: E402
    ORACLE_FEATS, market_state)

WRDS = _config.OPTIMUS_LEDGER_DIR / "wrds"
OUT = _config.OPTIMUS_LEDGER_DIR / "regime"
SEED = 20260820
#: Kenneth French posts factors days after the fact; rates are same-day.
FF_PUBLICATION_LAG = 5

MACRO_FEATS = ("credit_spread", "credit_spread_chg21", "yield_level",
               "term_spread", "ted_spread", "ff_mkt_21", "ff_mktvol_21",
               "ff_umd_21")


def macro_state() -> pd.DataFrame:
    """Market-wide LEVEL observables, each stamped when it was knowable."""
    r = pd.read_parquet(WRDS / "frb_rates_daily.parquet")
    r["date"] = pd.to_datetime(r["date"])
    r = r.sort_values("date")
    out = pd.DataFrame({"date": r["date"]})
    # Baa - Aaa: the market's own price of corporate risk
    out["credit_spread"] = r["dbaa"] - r["daaa"]
    out["yield_level"] = r["daaa"]
    # `d_tcmnom_y20` is entirely EMPTY over 2013-2024 — using it made
    # term_spread 0% covered and the complete-case join returned zero
    # rows. Constant-maturity Treasuries carry the modern window.
    short = (r["dgs3mo"] if "dgs3mo" in r.columns
             else r.get("effr", r.get("dff")))
    long_ = r["dgs10"] if "dgs10" in r.columns else r["daaa"]
    out["term_spread"] = long_ - short
    if "tedrate" in r.columns:
        out["ted_spread"] = r["tedrate"]
    out = out.set_index("date").ffill()
    out["credit_spread_chg21"] = out["credit_spread"].diff(21)

    p = WRDS / "ff_fivefactors_daily.parquet"
    if p.exists():
        f = pd.read_parquet(p)
        f["date"] = pd.to_datetime(f["date"])
        f = f.sort_values("date").set_index("date")
        ff = pd.DataFrame(index=f.index)
        ff["ff_mkt_21"] = f["mktrf"].rolling(21).sum()
        ff["ff_mktvol_21"] = (f["mktrf"].rolling(21).std(ddof=1)
                              * np.sqrt(252))
        if "umd" in f.columns:
            ff["ff_umd_21"] = f["umd"].rolling(21).sum()
        # PUBLICATION LAG: French posts these days late
        ff = ff.shift(FF_PUBLICATION_LAG)
        out = out.join(ff, how="outer").sort_index().ffill()
    return out.reset_index().rename(columns={"index": "date"})


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

    print("building panel + macro/oracle state...")
    df = build(a.era)
    need = list(dict.fromkeys(list(WITH_OPT) + ["fwd_var"]))
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=need)
    ms = market_state(a.era)[["date"] + list(ORACLE_FEATS)]
    mac = macro_state()
    df = df.merge(ms, on="date", how="left")
    df = pd.merge_asof(df.sort_values("date"), mac.sort_values("date"),
                       on="date", direction="backward")
    have = [c for c in MACRO_FEATS if c in df.columns]
    df = df.dropna(subset=list(ORACLE_FEATS) + have)
    print(f"rows {len(df):,}  dates {df['date'].nunique()}  "
          f"macro features {have}")

    arms = {"baseline": list(WITH_OPT),
            "plus_macro": list(WITH_OPT) + have,
            "plus_oracle": list(WITH_OPT) + list(ORACLE_FEATS),
            "plus_macro_oracle": list(WITH_OPT) + have
            + list(ORACLE_FEATS)}
    from lightgbm import LGBMRegressor
    ic = {k: [] for k in arms}
    mse = {k: [] for k in arms}
    ql = {k: [] for k in arms}
    for y in range(cfg["test_from"], cfg["years"][1] + 1):
        tr = df[df["date"].dt.year < y]
        te = df[df["date"].dt.year == y]
        if len(tr) < 5000 or len(te) < 1000:
            continue
        yt = np.log(tr["fwd_var"].to_numpy())
        at = te["fwd_var"].to_numpy()
        for name, feats in arms.items():
            m = LGBMRegressor(n_estimators=300, num_leaves=31,
                              learning_rate=0.05, random_state=SEED,
                              verbose=-1)
            m.fit(tr[feats].to_numpy(), yt)
            pred = np.exp(m.predict(te[feats].to_numpy()))
            ic[name].append(rank_ic_by_date(pred, at,
                                            te["date"].to_numpy()))
            lr = np.log(at / np.clip(pred, VAR_FLOOR, None))
            mse[name].append(pd.Series(lr ** 2,
                                       index=te["date"].to_numpy()))
            ql[name].append(pd.Series(qlike(at, pred),
                                      index=te["date"].to_numpy()))
        print(f"  fold {y}: train {len(tr):,} test {len(te):,}")

    ICs = {k: pd.concat(v) for k, v in ic.items()}
    MSE = {k: pd.concat(v).groupby(level=0).mean() for k, v in mse.items()}
    QL = {k: pd.concat(v).groupby(level=0).mean() for k, v in ql.items()}
    ix = MSE["baseline"].index
    for k in arms:
        ix = ix.intersection(MSE[k].index)
    dates = np.array(sorted(ix), dtype="datetime64[D]")
    blk = bootstrap_block_dates(dates, 21)

    summary = {k: {"mean_rank_ic": round(float(ICs[k].reindex(ix).mean()), 4),
                   "mse_log_var": round(float(MSE[k].loc[ix].mean()), 5),
                   "mean_qlike": round(float(QL[k].loc[ix].mean()), 5)}
               for k in arms}
    contrasts = {}
    for k in arms:
        if k == "baseline":
            continue
        d = (MSE["baseline"].loc[ix] - MSE[k].loc[ix]).to_numpy(float)
        inf = block_bootstrap_paired(d, dates, block_days=blk,
                                     seed=SEED).as_dict()
        contrasts[f"{k}_vs_baseline"] = {
            "d_mse_log_var": round(inf["mean"], 6),
            "arm_better": bool(inf["mean"] > 0),
            "ci": [round(inf["ci_lo"], 6), round(inf["ci_hi"], 6)],
            "mde_80": round(inf["mde_80pct_power"], 6),
            "significant": bool(inf["ci_lo"] > 0 or inf["ci_hi"] < 0),
            "clears_mde": bool(abs(inf["mean"])
                               >= inf["mde_80pct_power"])}

    mac_c = contrasts["plus_macro_vs_baseline"]
    orc_c = contrasts["plus_oracle_vs_baseline"]
    d_ql_macro = (summary["baseline"]["mean_qlike"]
                  - summary["plus_macro"]["mean_qlike"])
    d_ql_oracle = (summary["baseline"]["mean_qlike"]
                   - summary["plus_oracle"]["mean_qlike"])
    frac = (d_ql_macro / d_ql_oracle) if d_ql_oracle > 0 else 0.0
    if mac_c["significant"] and mac_c["arm_better"]:
        verdict = (f"OBSERVABLE_REACHES_PART_OF_THE_CEILING — macro state "
                   f"improves the level, capturing ~{frac:.0%} of the "
                   f"oracle's QLIKE gain")
    elif d_ql_macro > 0 and frac > 0.2:
        verdict = (f"PARTIAL, NOT POWERED — macro captures ~{frac:.0%} of "
                   f"the oracle's QLIKE gain but the MSE contrast does "
                   f"not clear its interval")
    else:
        verdict = ("OBSERVABLE_DOES_NOT_REACH_IT — the credit spread and "
                   "term structure do not recover the level headroom a "
                   "perfectly-known market variance provides")

    res = {"trial": "STATE-OBSERVABLE-1", "mode": "SCREEN", "era": a.era,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "question": "can an OBSERVABLE macro state reach the LEVEL "
                       "ceiling REGIME-RISK-CONDITIONING-1 measured?",
           "macro_features": have,
           "pit": {"rates": "published same day; read at t",
                   "ff_factors": f"lagged {FF_PUBLICATION_LAG} business "
                                 f"days — French posts them late, and "
                                 f"not lagging them would manufacture "
                                 f"the level information under test"},
           "n_rows": int(len(df)), "n_dates": int(len(ix)),
           "summary": summary, "contrasts": contrasts,
           "qlike_gain_vs_oracle_gain": round(float(frac), 4),
           "verdict": verdict}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"state_observable_1_{a.era}_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"\n{'arm':20s} {'rankIC':>8s} {'MSElogV':>9s} {'QLIKE':>9s}")
    for k, v in summary.items():
        print(f"{k:20s} {v['mean_rank_ic']:>8.4f} "
              f"{v['mse_log_var']:>9.5f} {v['mean_qlike']:>9.4f}")
    print("\nvs baseline (positive == better on MSE log variance):")
    for k, c in contrasts.items():
        t = ("POWERED" if c["clears_mde"]
             else ("significant" if c["significant"] else "ns"))
        print(f"  {k:34s} {c['d_mse_log_var']:+.5f} "
              f"MDE {c['mde_80']:.5f}  {t}")
    print(f"\nQLIKE gain: macro {d_ql_macro:+.4f}  oracle {d_ql_oracle:+.4f}"
          f"  -> macro captures {frac:.0%} of the ceiling")
    print(f"VERDICT: {verdict}")
    print(f"receipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
