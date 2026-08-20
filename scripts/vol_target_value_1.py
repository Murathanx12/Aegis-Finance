"""VOL-TARGET-VALUE-1 — the one use of the risk head this run has not tested.

Order 24's chain keeps converging on one distinction:

    the risk head's ORDERING is excellent and era-invariant (rank IC
    ~0.80, transfer ratio 1.001) — and ordering is not what portfolio
    weights consume.

RISK-SIZING-VALUE-1 tried the ordering inside the book, sizing names
against each other, and it was NOT_ESTABLISHED. RISK-SIZING-DISPERSION-1
found why (the model is shrunk) and fixed the shrinkage, and it was still
NOT_ESTABLISHED. CONSTRUCTION-SIZING-1 added covariance awareness and it
was worse pooled. REGIME-RISK-CONDITIONING-1 then found that the one
place a perfectly-known state still helps is the **LEVEL**: QLIKE falls
0.500 -> 0.434 while rank IC does not move at all.

So there is exactly one use left that this run has not tried, and it is
the one that consumes a level rather than an ordering:

    scale the book's TOTAL EXPOSURE so its predicted volatility hits a
    constant target.

Cross-sectional ordering is irrelevant to that. What matters is whether
the predicted portfolio volatility is right in LEVEL, month by month —
which is precisely where §1's calibrated arm and §10's oracle ceiling say
the remaining information is.

ARMS (overlay on the same underlying book, so selection is held fixed):

    none      the raw book
    trailing  leverage = target / trailing realized vol of the book
    model     leverage = target / sqrt(w' S w), where S combines the
              MODEL's predicted variances with trailing correlations

The model is used where it is strong (per-name variance level) and
trailing where it has no choice (the correlation matrix). Leverage is
known at the START of each month and capped, so no month is levered on
its own outcome.

PRIMARY: tracking of the volatility target — mean |realized ann vol −
target| over rolling windows, and the dispersion of realized vol. A
better-calibrated LEVEL should hold the target more tightly. Drawdown and
return are reported but are not the primary; a vol target is a promise
about volatility.

Declared before running: the model arm should track the target more
tightly than the trailing arm. If it does not, then every route from this
risk head to a portfolio decision that Order 24 could test has been
tested, and none of them pays.

    python -m scripts.vol_target_value_1

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
from backend.services import lane_factory_sim as LFS         # noqa: E402
from backend.services.information_classes import (           # noqa: E402
    build_extras, register)
from backend.services.net_tournament import (                # noqa: E402
    bootstrap_block_dates)
from scripts.risk_sizing_value_1 import (HANDLINGS, SIGNALS,  # noqa: E402
                                         START, END, TOP_N,
                                         walk_forward_predictions)
from scripts.rule_intervention_1 import block_boot_stat      # noqa: E402

OUT = _config.OPTIMUS_LEDGER_DIR / "structure"
TARGET_VOL = 0.15
LEV_CAP = (0.25, 2.0)
CORR_LOOKBACK = 252
SEED = 20260820


def predicted_portfolio_vol(panel, extras, piv, sig, weighting="equal"):
    """Model-predicted annualised portfolio vol at each month-end.

    S = D^(1/2) R D^(1/2): the MODEL supplies the diagonal (per-name
    predicted variance, its measured strength) and the trailing window
    supplies the correlations (which the model has no view on at all).
    Ignoring correlations entirely would repeat CONSTRUCTION-SIZING-1's
    lesson in a new place.
    """
    out = {}
    month_ends = panel.px.groupby(panel.px.index.to_period("M")).tail(1)
    for d in month_ends.index:
        if d < pd.Timestamp(START) or d > pd.Timestamp(END):
            continue
        elig = panel.elig_by_month.get(d.to_period("M"), set())
        s = LFS.SIGNALS[sig](panel, d, extras)
        s = s[np.isfinite(s)]
        s = s[s.index.isin(elig)].sort_values(ascending=False)
        picks = list(s.index[:TOP_N])
        if len(picks) < 10:
            continue
        h = piv.loc[:d]
        if not len(h):
            continue
        pv = h.iloc[-1]
        pv = pv[pv.index.isin(picks)].dropna()
        pv = pv[pv > 0]
        if len(pv) < 10:
            continue
        hist = panel.ret.loc[:d].iloc[-CORR_LOOKBACK:][list(pv.index)]
        hist = hist.dropna(axis=1, thresh=int(0.8 * len(hist)))
        cols = [c for c in pv.index if c in hist.columns]
        if len(cols) < 10:
            continue
        R = hist[cols].corr().to_numpy(float)
        R = np.nan_to_num(R, nan=0.0)
        np.fill_diagonal(R, 1.0)
        sd = np.sqrt(pv[cols].to_numpy(float))
        w = np.full(len(cols), 1.0 / len(cols))
        var = float(w @ (np.outer(sd, sd) * R) @ w)
        out[d] = float(np.sqrt(max(var, 1e-12)))
    return pd.Series(out).sort_index()


def overlay(monthly: pd.Series, lev: pd.Series) -> pd.Series:
    """Apply leverage known at the START of each month."""
    l = lev.reindex(monthly.index).shift(1).ffill()
    l = l.clip(*LEV_CAP).fillna(1.0)
    return monthly * l


def realized_vol_series(r: pd.Series, win: int = 12) -> pd.Series:
    return r.rolling(win).std(ddof=1) * np.sqrt(12)


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=2000)
    a = ap.parse_args()

    pred = walk_forward_predictions()
    piv = pred.pivot_table(index="date", columns="permno",
                           values="pred_var", aggfunc="last").sort_index()
    piv.index = pd.to_datetime(piv.index)

    register(LFS.SIGNALS)
    panel = LFS.load_panel()
    extras = build_extras(panel)

    series, rows = {}, []
    for sig in SIGNALS:
        pvol = predicted_portfolio_vol(panel, extras, piv, sig)
        for h in HANDLINGS:
            b = LFS.run_book(panel, weighting="equal", winner_handling=h,
                             top_n=TOP_N, signal=sig, extras=extras,
                             start=START, end=END)
            m = b["monthly_returns"]
            arms = {
                "none": m,
                "trailing": overlay(
                    m, TARGET_VOL / realized_vol_series(m).replace(
                        0, np.nan)),
                "model": overlay(m, TARGET_VOL / pvol.reindex(
                    m.index).ffill().replace(0, np.nan)),
            }
            for name, r in arms.items():
                k = f"{sig}|{name}|{h}"
                series[k] = r
                rv = realized_vol_series(r).dropna()
                rows.append({
                    "key": k, "signal": sig, "arm": name, "handling": h,
                    "ann_vol": round(float(r.std(ddof=1) * np.sqrt(12)), 4),
                    "mean_abs_dev_from_target": round(
                        float((rv - TARGET_VOL).abs().mean()), 4),
                    "sd_of_realized_vol": round(float(rv.std(ddof=1)), 4),
                    "ann_return": round(float(r.mean() * 12), 4),
                    "max_drawdown": round(float(
                        ((1 + r).cumprod()
                         / (1 + r).cumprod().cummax() - 1).min()), 4)})

    R = pd.DataFrame(series).dropna()
    dates = np.array(R.index.values, dtype="datetime64[D]")
    blk = bootstrap_block_dates(dates, 21)

    def track_err(x: np.ndarray) -> float:
        s = pd.Series(np.nanmean(x, axis=1))
        rv = s.rolling(12).std(ddof=1) * np.sqrt(12)
        return float((rv - TARGET_VOL).abs().mean())

    def contrast(an, bn):
        prs = [(f"{s}|{an}|{h}", f"{s}|{bn}|{h}")
               for s in SIGNALS for h in HANDLINGS
               if f"{s}|{an}|{h}" in R.columns
               and f"{s}|{bn}|{h}" in R.columns]
        if not prs:
            return None
        A, B = R[[x for x, _ in prs]], R[[y for _, y in prs]]
        return {"n_pairs": len(prs),
                "d_tracking_error": block_boot_stat(A, B, track_err, blk,
                                                    n_boot=a.n_boot),
                "per_pair_d_tracking": {
                    x.split("|")[0] + "|" + x.split("|")[-1]: round(
                        float(
                            (realized_vol_series(R[x]).dropna()
                             - TARGET_VOL).abs().mean()
                            - (realized_vol_series(R[y]).dropna()
                               - TARGET_VOL).abs().mean()), 4)
                    for x, y in prs}}

    contrasts = {"model_vs_trailing": contrast("model", "trailing"),
                 "model_vs_none": contrast("model", "none"),
                 "trailing_vs_none": contrast("trailing", "none")}

    res = {"trial": "VOL-TARGET-VALUE-1", "mode": "SCREEN",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "target_vol": TARGET_VOL, "leverage_cap": list(LEV_CAP),
           "primary": "mean |rolling-12m realized ann vol - target|; a "
                      "vol target is a promise about VOLATILITY, so "
                      "return and drawdown are reported but secondary",
           "declared_direction": "the model arm should track the target "
                                 "more tightly than the trailing arm",
           "n_months": int(len(R)),
           "predicted_portfolio_vol": "S = D^(1/2) R D^(1/2); model "
                                      "supplies the diagonal, trailing "
                                      "window supplies correlations",
           "contrasts": contrasts, "books": rows,
           "label": "SIMULATION — LANE-FACTORY-SIM-1, never a track record"}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "vol_target_value_1_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"\n{'arm':10s} {'mean|vol-target|':>17s} {'sd(realvol)':>12s} "
          f"{'ann vol':>9s} {'ann ret':>9s} {'maxDD':>8s}")
    for arm in ("none", "trailing", "model"):
        sel = [r for r in rows if r["arm"] == arm]
        print(f"{arm:10s} "
              f"{np.mean([r['mean_abs_dev_from_target'] for r in sel]):>17.4f} "
              f"{np.mean([r['sd_of_realized_vol'] for r in sel]):>12.4f} "
              f"{np.mean([r['ann_vol'] for r in sel]):>9.4f} "
              f"{np.mean([r['ann_return'] for r in sel]):>9.4f} "
              f"{np.mean([r['max_drawdown'] for r in sel]):>8.4f}")

    def tag(d):
        return ("POWERED" if d["clears_mde"] else
                ("significant" if d["significant_ci_excludes_zero"]
                 else "ns"))
    print("\ntracking error contrasts (NEGATIVE == first arm tracks "
          "the target better):")
    for k, c in contrasts.items():
        if not c:
            continue
        d = c["d_tracking_error"]
        print(f"  {k:22s} {d['observed']:+.5f}  MDE {d['mde_80']:.5f}  "
              f"CI [{d['ci'][0]:+.5f}, {d['ci'][1]:+.5f}]  {tag(d)}")
    print(f"\nreceipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
