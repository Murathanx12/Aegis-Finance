"""RISK-SIZING-DISPERSION-1 — ordering is not enough for sizing.

The tail of RISK-SIZING-VALUE-1, which returned NOT_ESTABLISHED and then
explained itself.

The risk head ranks next-month variance better than trailing variance,
better than HAR-RV and better than implied variance (rank IC ~0.80 vs
~0.75, replicated out of era). Yet sizing books by 1/sqrt(predicted var)
did NOT beat sizing them by 1/sqrt(trailing var): pooled d_ann_vol
+0.0103, ns, with the pooled average driven by one signal (value_bm,
+0.26) while ten of twelve matched pairs improved or tied.

Three explanations were tested and killed:
  - weight concentration      a 5x cap moved the contrast +0.0103 -> +0.0109
  - prediction coverage       value_bm picks are 93.3% covered, HIGHER
                              than mom_12_1 (90.8%) or low_vol (89.9%)
  - model accuracy on picks   the model is MOST accurate on value picks
                              (rank IC 0.764, QLIKE 0.381) and LEAST on
                              opt_iv_low (0.499) — the opposite ordering
                              to where sizing helped

The fourth explanation survives, and it is measurable. Cross-sectional
dispersion of log predicted variance, against trailing and realized:

    signal        sd log pred   sd log trail   ratio   sd log realized
    value_bm            0.847          1.056    0.80             1.093
    opt_iv_low          0.922          1.131    0.82             1.300
    mom_12_1            0.717          1.062    0.67             1.112
    low_vol             1.029          1.007    1.02             1.441

**The model is SHRUNK.** A regularised learner minimising squared error
on log variance is rewarded for pulling toward the mean, so it orders
the cross-section well while understating its spread. Inverse-volatility
weights are driven by the SPREAD of the estimator, not its ordering: a
shrunk estimator produces near-equal weights and therefore fails to
reduce book volatility however well it ranks. On the value book,
model-sized realised vol was 0.596 against 0.608 for plain equal weight
— it was barely sizing at all — while trailing vol reached 0.331.

THE FIX, AND THE TEST
---------------------
Rank-preserving dispersion correction: on each formation date, map the
model's predicted variances onto the empirical cross-sectional
distribution of TRAILING variance by quantile. This changes only the
spread — the model's ranking, which is its proven strength, is preserved
exactly (Spearman is invariant under a monotone map).

Declared before running: `model_vol_ds` should reduce realised book
volatility relative to BOTH `inverse_vol` and the uncorrected
`model_vol`. If it does not, the head's ranking advantage does not
convert into sizing value by this route either, and the honest
conclusion is that a better-ranked variance forecast is simply not what
inverse-vol sizing needs.

    python -m scripts.risk_sizing_dispersion_1

SCREEN. No promotion, no capital.
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
from scripts.rule_intervention_1 import (block_boot_stat,    # noqa: E402
                                         _maxdd_of, _vol_of)

OUT = _config.OPTIMUS_LEDGER_DIR / "structure"
SEED = 20260820


def trailing_var_panel(panel, dates) -> pd.DataFrame:
    """permno x date trailing 63-day realized variance, annualized."""
    rows = {}
    for d in dates:
        if d not in panel.ret.index:
            continue
        h = panel.ret.loc[:d].iloc[-63:]
        sd = h.std(ddof=1)
        n = h.notna().sum()
        sd = sd[(n >= 40) & (sd > 0)]
        rows[d] = (sd ** 2) * 252
    return pd.DataFrame(rows).T.sort_index()


def dispersion_correct(pred: pd.DataFrame,
                       trail: pd.DataFrame) -> pd.DataFrame:
    """Map predictions onto the trailing distribution, BY RANK.

    Monotone in the prediction, so Spearman rank IC is preserved exactly
    — the model keeps the ordering it earned and borrows only the spread
    it was shrinking away.
    """
    out = {}
    for d in pred.index:
        p = pred.loc[d].dropna()
        if d not in trail.index or len(p) < 20:
            continue
        t = trail.loc[d].dropna()
        t = t[t > 0]
        if len(t) < 20:
            continue
        # rank of each prediction -> same quantile of trailing variance
        q = p.rank(pct=True, method="average")
        out[d] = pd.Series(np.quantile(t.to_numpy(), q.clip(0, 1)),
                           index=p.index)
    return pd.DataFrame(out).T.sort_index()


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

    print("building trailing-variance panel...")
    trail = trailing_var_panel(panel, list(piv.index))
    ds = dispersion_correct(piv, trail)
    print(f"dispersion-corrected: {ds.shape[0]} dates x {ds.shape[1]} names")

    # sanity: the correction must preserve ORDER and change SPREAD
    checks = []
    for d in list(ds.index)[:40]:
        p = piv.loc[d].dropna()
        q = ds.loc[d].dropna()
        common = p.index.intersection(q.index)
        if len(common) < 20:
            continue
        checks.append({
            "spearman": float(p[common].rank().corr(q[common].rank())),
            "sd_log_before": float(np.log(p[common][p[common] > 0]).std()),
            "sd_log_after": float(np.log(q[common][q[common] > 0]).std())})
    sp = float(np.mean([c["spearman"] for c in checks]))
    sb = float(np.mean([c["sd_log_before"] for c in checks]))
    sa = float(np.mean([c["sd_log_after"] for c in checks]))
    print(f"rank preserved: mean Spearman {sp:.6f} (must be ~1.0)")
    print(f"dispersion:     sd log {sb:.3f} -> {sa:.3f}")
    if sp < 0.999:
        raise SystemExit(
            f"REFUSED: the correction changed the ORDERING (Spearman "
            f"{sp:.4f}); it is only allowed to change the spread.")

    series, rows = {}, []
    arms = {"inverse_vol": ("inverse_vol", None),
            "model_vol": ("model_vol", piv),
            "model_vol_ds": ("model_vol", ds)}
    for sig in SIGNALS:
        for h in HANDLINGS:
            for name, (w, table) in arms.items():
                if table is not None:
                    LFS.MODEL_PRED_VAR = table
                k = f"{sig}|{name}|{h}"
                try:
                    b = LFS.run_book(panel, weighting=w, winner_handling=h,
                                     top_n=TOP_N, signal=sig,
                                     extras=extras, start=START, end=END)
                except Exception as e:                         # noqa: BLE001
                    print(f"  {k}: {type(e).__name__}: {e}")
                    continue
                series[k] = b["monthly_returns"]
                rows.append({"key": k, "signal": sig, "arm": name,
                             "handling": h,
                             **{kk: vv for kk, vv in b.items()
                                if isinstance(vv, (int, float))}})
                print(f"  {k:36s} vol {b['ann_vol']:.3f} "
                      f"dd {b['max_drawdown']:+.3f} "
                      f"ret {b['total_return']:+.3f}")

    R = pd.DataFrame(series).dropna()
    dates = np.array(R.index.values, dtype="datetime64[D]")
    blk = bootstrap_block_dates(dates, 21)

    def contrast(an, bn, label):
        prs = [(f"{s}|{an}|{h}", f"{s}|{bn}|{h}")
               for s in SIGNALS for h in HANDLINGS
               if f"{s}|{an}|{h}" in R.columns
               and f"{s}|{bn}|{h}" in R.columns]
        if not prs:
            return None
        A, B = R[[x for x, _ in prs]], R[[y for _, y in prs]]
        return {"label": label, "n_pairs": len(prs),
                "d_ann_vol": block_boot_stat(A, B, _vol_of, blk,
                                             n_boot=a.n_boot),
                "d_max_drawdown": block_boot_stat(A, B, _maxdd_of, blk,
                                                  n_boot=a.n_boot),
                "d_ann_return": block_boot_stat(
                    A, B, lambda x: float(np.nanmean(x) * 12), blk,
                    n_boot=a.n_boot),
                "per_pair_d_ann_vol": {
                    x.split("|")[0] + "|" + x.split("|")[-1]: round(
                        float(R[x].std(ddof=1) * np.sqrt(12)
                              - R[y].std(ddof=1) * np.sqrt(12)), 4)
                    for x, y in prs}}

    contrasts = {
        "ds_vs_trailing": contrast(
            "model_vol_ds", "inverse_vol",
            "dispersion-corrected model - trailing (the primary)"),
        "ds_vs_model": contrast(
            "model_vol_ds", "model_vol",
            "dispersion-corrected model - uncorrected model"),
        "model_vs_trailing": contrast(
            "model_vol", "inverse_vol",
            "uncorrected model - trailing (the prior null, for reference)"),
    }

    res = {"trial": "RISK-SIZING-DISPERSION-1", "mode": "SCREEN",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "declared_direction": "model_vol_ds should reduce realised book "
                                 "volatility vs BOTH inverse_vol and the "
                                 "uncorrected model_vol",
           "correction": "per-date rank-preserving quantile map of "
                         "predicted variance onto the trailing-variance "
                         "distribution; monotone, so rank IC is unchanged",
           "rank_preservation_spearman": round(sp, 6),
           "dispersion_sd_log_before": round(sb, 4),
           "dispersion_sd_log_after": round(sa, 4),
           "n_months": int(len(R)),
           "window": [str(R.index.min())[:10], str(R.index.max())[:10]],
           "contrasts": contrasts, "books": rows,
           "label": "SIMULATION — LANE-FACTORY-SIM-1, never a track record"}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "risk_sizing_dispersion_1_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    def tag(d):
        return ("POWERED" if d["clears_mde"] else
                ("significant" if d["significant_ci_excludes_zero"]
                 else "ns"))
    for c in contrasts.values():
        if not c:
            continue
        print(f"\n{c['label']}  ({c['n_pairs']} pairs, {len(R)} months)")
        for m in ("d_ann_vol", "d_max_drawdown", "d_ann_return"):
            d = c[m]
            print(f"  {m:16s} {d['observed']:+.4f}  MDE {d['mde_80']:.4f}"
                  f"  CI [{d['ci'][0]:+.4f}, {d['ci'][1]:+.4f}]  {tag(d)}")
    print(f"\nreceipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
