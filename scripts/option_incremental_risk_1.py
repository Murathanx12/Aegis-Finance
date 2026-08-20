"""OPTION-INCREMENTAL-RISK-1 — does Aegis beat simply reading the options
market, and does it beat HAR-RV?

The program's strongest evidence is the risk head: LGBM > ridge on
forward-volatility ranking, reproduced out of era, and +options raising
mean rank IC to ~0.79. Two objections survive that record and both are
fair:

1. **"0.79" is a cross-sectional rank IC on a volatility target, not
   accuracy.** Rank IC rewards ordering. A model can order the
   cross-section beautifully while being badly calibrated in level, and
   sizing decisions consume the level. So the primary loss here is
   QLIKE on annualized realized variance, with rank IC kept as a
   secondary (and as the bridge to the existing receipts).
2. **The baseline was never the right baseline.** `numeric LGBM <
   numeric+options LGBM` shows options add to *our* model. It does not
   show our model adds to *the options market*, nor that it beats
   HAR-RV (Corsi 2009), which is brutally strong on volatility and
   beats most ML. The ladder below makes the machine earn its
   existence against both.

Ladder, all arms on IDENTICAL rows, folds and missingness:

    rv_m          last-21d realized variance, no fit          (mechanical)
    har           OLS on log RV_d / RV_w / RV_m               (Corsi)
    iv_only       ATM implied variance, no fit                (the market)
    iv_scaled     OLS on log implied variance                 (the market, levelled)
    har_iv        OLS on HAR components + log implied var     (both, linear)
    ridge_numeric ridge on the full numeric block
    lgbm_numeric  LGBM on the full numeric block
    lgbm_options  LGBM on numeric + options
    mlp_options   small MLP on numeric + options

`iv_only` is deliberately given a fitted twin (`iv_scaled`): judging a
forward-looking market price by its raw level, when every model arm is
allowed an intercept, would be a rigged comparison.

Also runs the SHIFT-INVARIANCE probe (Order 24 B2): every feature lagged
one extra month. Slow, structural features degrade gracefully; anything
that collapses was living on same-instant information.

    python -m scripts.option_incremental_risk_1 --era modern
    python -m scripts.option_incremental_risk_1 --era early --shift 1

SCREEN, not a registered confirmation: this compares model families on
data both eras have already been read on. It resolves a MODEL-CHOICE
question (which baseline must be beaten), and any survivor earns a
registration, never a promotion.
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
from scripts.net_ladder_rungs_run import (OPT_FEATS,         # noqa: E402
                                          options_monthly)

OUT = _config.OPTIMUS_LEDGER_DIR / "risk_ladder"
PIT = _config.OPTIMUS_LEDGER_DIR / "crsp_pit"

ANN = 252.0
VAR_FLOOR = 1e-8            # annualized variance floor (vol ~0.01%)
PRICE_FEATS = ("mom_21", "mom_63", "mom_126", "mom_252_21",
               "dd_252", "log_rv_d", "log_rv_w", "log_rv_m", "log_rv_q")
NUMERIC = tuple(PRICE_FEATS)
WITH_OPT = tuple(PRICE_FEATS) + tuple(OPT_FEATS) + ("log_iv_var",)

ERAS = {"modern": {"years": (2013, 2024), "univ": "crsp_pit_monthly_v1",
                   "opt_years": (2013, 2024), "test_from": 2017},
        "early": {"years": (1990, 2012), "univ": "crsp_pit_monthly_early",
                  "opt_years": (1996, 2012), "test_from": 2001}}


# ── dataset ────────────────────────────────────────────────────────────────
def build(era: str, shift_months: int = 0) -> pd.DataFrame:
    """stock x month-end panel: HAR components, price state, options, target.

    Target is ANNUALIZED REALIZED VARIANCE over t+1..t+21 — strictly
    forward, never including the formation day (CHRONOLOGY-AUDIT-1 C2).
    """
    cfg = ERAS[era]
    panel = load_panel(years=cfg["years"],
                       univ_path=PIT / f"{cfg['univ']}.parquet")
    px, ret = panel.px, panel.ret
    r2 = ret ** 2

    feats = {}
    for w in (21, 63, 126):
        feats[f"mom_{w}"] = px / px.shift(w) - 1.0
    feats["mom_252_21"] = px.shift(21) / px.shift(252) - 1.0
    feats["dd_252"] = px / px.rolling(252).max() - 1.0
    # HAR-RV cascade: daily / weekly / monthly / quarterly realized variance
    for tag, w in (("d", 1), ("w", 5), ("m", 21), ("q", 63)):
        rv = r2.rolling(w).mean() * ANN
        feats[f"log_rv_{tag}"] = np.log(rv.clip(lower=VAR_FLOOR))
    # forward realized variance over t+1..t+21 (reversed rolling, shifted)
    fwd_var = (r2[::-1].rolling(21).mean()[::-1].shift(-1)) * ANN

    month_ends = px.groupby(px.index.to_period("M")).tail(1).index
    rows = []
    for i, d in enumerate(month_ends):
        if d not in px.index:
            continue
        # shift-invariance probe: read features from an EARLIER month-end
        src = month_ends[i - shift_months] if shift_months else d
        if src not in px.index:
            continue
        elig = panel.elig_by_month.get(d.to_period("M"), set())
        f = pd.DataFrame({k: v.loc[src] for k, v in feats.items()})
        f["fwd_var"] = fwd_var.loc[d]
        f = f.replace([np.inf, -np.inf], np.nan).dropna()
        f = f[f.index.isin(elig)]
        f["date"] = d
        f["permno"] = f.index
        rows.append(f)
    df = pd.concat(rows, ignore_index=True)
    df["fwd_var"] = df["fwd_var"].clip(lower=VAR_FLOOR)
    df["month"] = df["date"].dt.to_period("M")

    # options: last surface obs of the month, staleness-capped, sign-asserted
    opt = options_monthly(years=cfg["opt_years"])
    if shift_months:
        opt = opt.copy()
        opt["month"] = opt["month"] + shift_months
    df = df.merge(opt, on=["permno", "month"], how="left")
    lag = (df["date"] - df["opt_date"]).dt.days
    if not shift_months:
        neg = int((lag < 0).sum())
        if neg:
            raise SystemExit(f"REFUSED: {neg} options postdate formation")
    for c in OPT_FEATS:
        df.loc[lag > 14 + 31 * shift_months, c] = np.nan
    df["log_iv_var"] = np.log(
        (df["opt_iv_atm"] ** 2).clip(lower=VAR_FLOOR))
    return df


# ── arms ───────────────────────────────────────────────────────────────────
def _ols(tr_X, tr_y, te_X):
    X = np.column_stack([np.ones(len(tr_X)), tr_X])
    beta, *_ = np.linalg.lstsq(X, tr_y, rcond=None)
    return np.column_stack([np.ones(len(te_X)), te_X]) @ beta


def fit_predict(arm: str, tr: pd.DataFrame, te: pd.DataFrame) -> np.ndarray:
    """Every arm returns a predicted ANNUALIZED VARIANCE (level, not log)."""
    y = np.log(tr["fwd_var"].to_numpy())
    if arm == "rv_m":
        return np.exp(te["log_rv_m"].to_numpy())
    if arm == "iv_only":
        return np.exp(te["log_iv_var"].to_numpy())
    if arm == "har":
        c = ["log_rv_d", "log_rv_w", "log_rv_m"]
        return np.exp(_ols(tr[c].to_numpy(), y, te[c].to_numpy()))
    if arm == "iv_scaled":
        c = ["log_iv_var"]
        return np.exp(_ols(tr[c].to_numpy(), y, te[c].to_numpy()))
    if arm == "har_iv":
        c = ["log_rv_d", "log_rv_w", "log_rv_m", "log_iv_var"]
        return np.exp(_ols(tr[c].to_numpy(), y, te[c].to_numpy()))

    from sklearn.linear_model import Ridge
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from lightgbm import LGBMRegressor

    if arm == "ridge_numeric":
        f, m = NUMERIC, make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    elif arm == "lgbm_numeric":
        f, m = NUMERIC, LGBMRegressor(n_estimators=300, num_leaves=31,
                                      learning_rate=0.05, verbose=-1,
                                      random_state=20260820)
    elif arm == "lgbm_options":
        f, m = WITH_OPT, LGBMRegressor(n_estimators=300, num_leaves=31,
                                       learning_rate=0.05, verbose=-1,
                                       random_state=20260820)
    elif arm == "mlp_options":
        f, m = WITH_OPT, make_pipeline(
            StandardScaler(),
            MLPRegressor(hidden_layer_sizes=(64, 32), max_iter=200,
                         random_state=20260820))
    else:
        raise ValueError(arm)
    m.fit(tr[list(f)].to_numpy(), y)
    return np.exp(m.predict(te[list(f)].to_numpy()))


def qlike(actual: np.ndarray, pred: np.ndarray) -> np.ndarray:
    """QLIKE per row. Robust to noisy variance proxies; lower is better."""
    p = np.clip(pred, VAR_FLOOR, None)
    r = actual / p
    return r - np.log(r) - 1.0


ARMS = ("rv_m", "har", "iv_only", "iv_scaled", "har_iv",
        "ridge_numeric", "lgbm_numeric", "lgbm_options", "mlp_options")


def run(era: str, shift: int = 0) -> dict:
    cfg = ERAS[era]
    print(f"building {era} panel (shift={shift})...")
    df = build(era, shift_months=shift)
    n_all = len(df)
    # IDENTICAL rows for every arm: require the options block too, else
    # the ladder compares models on different populations
    need = list(dict.fromkeys(list(WITH_OPT) + ["fwd_var"]))
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=need)
    print(f"rows {n_all:,} -> {len(df):,} with complete options block "
          f"({100 * len(df) / max(n_all, 1):.1f}%)")

    per_date = {a: [] for a in ARMS}
    ql_rows = {a: [] for a in ARMS}
    # QLIKE is ASYMMETRIC: r - log r - 1 with r = actual/pred punishes
    # under-forecasting ~linearly and over-forecasting only ~log. Implied
    # variance embeds a variance risk premium, so it over-forecasts by
    # construction — which QLIKE rewards. Carry the bias explicitly, and a
    # symmetric loss (MSE on log variance) beside it, so "IV wins" can be
    # read as "IV wins on ordering+level" or "IV wins by being high".
    lr_rows = {a: [] for a in ARMS}
    keep_dates = []
    for y in range(cfg["test_from"], cfg["years"][1] + 1):
        tr = df[df["date"].dt.year < y]
        te = df[df["date"].dt.year == y]
        if len(tr) < 5000 or len(te) < 1000:
            continue
        print(f"  fold {y}: train {len(tr):,} test {len(te):,}")
        a_true = te["fwd_var"].to_numpy()
        for arm in ARMS:
            pred = fit_predict(arm, tr, te)
            per_date[arm].append(rank_ic_by_date(
                pred, a_true, te["date"].to_numpy()))
            ql_rows[arm].append(pd.Series(
                qlike(a_true, pred), index=te["date"].to_numpy()))
            lr_rows[arm].append(pd.Series(
                np.log(a_true / np.clip(pred, VAR_FLOOR, None)),
                index=te["date"].to_numpy()))
        keep_dates.append(te["date"].to_numpy())

    if not keep_dates:
        raise SystemExit("no usable folds")
    ic = {a: pd.concat(v) for a, v in per_date.items()}
    # QLIKE aggregated to a per-DATE mean: dates are the evidence unit,
    # rows are not (a date's cross-section is one observation, not N)
    ql = {a: pd.concat(v).groupby(level=0).mean() for a, v in ql_rows.items()}
    lr_all = {a: pd.concat(v) for a, v in lr_rows.items()}
    # MSE on log variance: symmetric, bias-sensitive but not asymmetric
    mse_log = {a: pd.concat([s ** 2 for s in v]).groupby(level=0).mean()
               for a, v in lr_rows.items()}

    ix = ql["har"].index
    for a in ARMS:
        ix = ix.intersection(ql[a].index)
    dates = np.array(sorted(ix), dtype="datetime64[D]")
    blk = bootstrap_block_dates(dates, 21)

    summary = {}
    for a in ARMS:
        lr = lr_all[a]
        summary[a] = {
            "mean_rank_ic": round(float(ic[a].reindex(ix).mean()), 4),
            "mean_qlike": round(float(ql[a].loc[ix].mean()), 5),
            "median_qlike": round(float(ql[a].loc[ix].median()), 5),
            "mse_log_var": round(float(mse_log[a].loc[ix].mean()), 5),
            # >0 means the arm UNDER-forecasts variance on average
            "bias_mean_log_ratio": round(float(lr.mean()), 5),
            "pct_under_forecast": round(float(100 * (lr > 0).mean()), 1)}

    # the question is incremental: every arm contested against the two
    # baselines that actually threaten it
    contrasts = {}
    for base in ("har", "iv_scaled", "har_iv", "lgbm_numeric"):
        for arm in ARMS:
            if arm == base:
                continue
            d = (ql[base].loc[ix] - ql[arm].loc[ix]).to_numpy(float)
            inf = block_bootstrap_paired(d, dates, block_days=blk,
                                         seed=20260820).as_dict()
            contrasts[f"{arm}_vs_{base}"] = {
                "d_qlike_base_minus_arm": round(inf["mean"], 6),
                "arm_better": bool(inf["mean"] > 0),
                "ci": [round(inf["ci_lo"], 6), round(inf["ci_hi"], 6)],
                "mde_80": round(inf["mde_80pct_power"], 6),
                "n_effective": inf["n_effective"],
                "clears_mde": bool(abs(inf["mean"])
                                   >= inf["mde_80pct_power"])}

    contrasts_mse = {}
    for base in ("har", "iv_scaled", "lgbm_numeric"):
        for arm in ARMS:
            if arm == base:
                continue
            d = (mse_log[base].loc[ix] - mse_log[arm].loc[ix]).to_numpy(float)
            inf = block_bootstrap_paired(d, dates, block_days=blk,
                                         seed=20260820).as_dict()
            contrasts_mse[f"{arm}_vs_{base}"] = {
                "d_mselog_base_minus_arm": round(inf["mean"], 6),
                "arm_better": bool(inf["mean"] > 0),
                "mde_80": round(inf["mde_80pct_power"], 6),
                "clears_mde": bool(abs(inf["mean"])
                                   >= inf["mde_80pct_power"])}

    best_q = min(ARMS, key=lambda a: summary[a]["mean_qlike"])
    best_mse = min(ARMS, key=lambda a: summary[a]["mse_log_var"])
    best_ic = max(ARMS, key=lambda a: summary[a]["mean_rank_ic"])
    return {"trial": "OPTION-INCREMENTAL-RISK-1", "mode": "SCREEN",
            "era": era, "shift_months": shift,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_rows": int(len(df)), "n_dates": int(len(ix)),
            "block_dates": int(blk),
            "test_years": [cfg["test_from"], cfg["years"][1]],
            "target": "annualized realized variance over t+1..t+21",
            "primary_loss": "QLIKE (lower better), per-date mean",
            "summary": summary,
            "best_by_qlike": best_q, "best_by_rank_ic": best_ic,
            "best_by_mse_log_var": best_mse,
            "contrasts": contrasts, "contrasts_mse_log": contrasts_mse}


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--era", default="modern", choices=list(ERAS))
    ap.add_argument("--shift", type=int, default=0,
                    help="lag every feature this many extra months "
                         "(shift-invariance probe)")
    a = ap.parse_args()
    r = run(a.era, a.shift)
    OUT.mkdir(parents=True, exist_ok=True)
    tag = f"{a.era}" + (f"_shift{a.shift}" if a.shift else "")
    p = OUT / f"option_incremental_risk_1_{tag}_2026-08-20.json"
    p.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")

    print(f"\n{'arm':16s} {'QLIKE':>9s} {'MSElogV':>9s} {'rankIC':>8s} "
          f"{'bias':>8s} {'%under':>7s}")
    for arm in sorted(ARMS, key=lambda x: r["summary"][x]["mean_qlike"]):
        s = r["summary"][arm]
        print(f"{arm:16s} {s['mean_qlike']:>9.5f} {s['mse_log_var']:>9.4f} "
              f"{s['mean_rank_ic']:>8.4f} "
              f"{s['bias_mean_log_ratio']:>+8.4f} "
              f"{s['pct_under_forecast']:>6.1f}%")
    print(f"\nbest by QLIKE: {r['best_by_qlike']}   "
          f"best by MSE(log var): {r['best_by_mse_log_var']}   "
          f"best by rank IC: {r['best_by_rank_ic']}")
    print("\nsymmetric loss (MSE on log variance) — settles whether IV "
          "wins on skill or on over-forecasting:")
    for k in ("lgbm_options_vs_iv_scaled", "lgbm_numeric_vs_iv_scaled",
              "har_vs_iv_scaled", "lgbm_options_vs_lgbm_numeric"):
        c = r["contrasts_mse_log"].get(k)
        if c:
            print(f"  {k:34s} d={c['d_mselog_base_minus_arm']:+.5f} "
                  f"mde={c['mde_80']:.5f} "
                  f"{'CLEARS' if c['clears_mde'] else 'below MDE'}")
    print("\nkey contrasts (positive d == arm beats base):")
    for k in ("lgbm_options_vs_har", "lgbm_options_vs_iv_scaled",
              "lgbm_options_vs_har_iv", "lgbm_options_vs_lgbm_numeric",
              "har_vs_iv_scaled", "lgbm_numeric_vs_har",
              "mlp_options_vs_lgbm_numeric"):
        c = r["contrasts"].get(k)
        if c:
            print(f"  {k:36s} d={c['d_qlike_base_minus_arm']:+.5f} "
                  f"mde={c['mde_80']:.5f} "
                  f"{'CLEARS' if c['clears_mde'] else 'below MDE'}")
    print(f"\nreceipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
