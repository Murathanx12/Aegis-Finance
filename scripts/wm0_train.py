"""WM0 — train and score World Model v0. The first G5 artefact.

    python -m scripts.wm0_train --power-only     # design stage
    python -m scripts.wm0_train                  # training run

Registered at `docs/TRIALS/PREREG_WM0_WORLD_MODEL_V0.md`.

THE QUESTION
============
Does a conditional model of the forward-return DISTRIBUTION beat cheap
volatility scaling — and if so, in which quantiles?

The roadmap's standing ruling is that realised vol is commoditised for RANKING,
so the learned model must earn its keep on tail and shape. `scaled_empirical`
is therefore the comparator of record: fat-tailed, conditionally scaled, and
free. Beating `climatology` instead would be the flattering comparison and is
reported only as context.

WHAT A NULL MEANS HERE
======================
That the state vector carries no distributional information beyond today's
realised volatility. That is a publishable v0 result and it tells the next
session to spend on state (options, cross-sectional, macro) rather than on
architecture.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from backend import config as _config
from backend.services import world_model as WM
from backend.services.research_gym.slice_register import (SliceIdentity,
                                                          SliceRefusal,
                                                          SliceRegister)

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "wm0_world_model_v0.json"

# ── frozen in the prereg ───────────────────────────────────────────────────
UNIVERSE = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK", "XLV", "XLI", "XLP",
            "XLU", "XLB", "XLY", "DIA", "TLT", "GLD", "EFA", "EEM", "IYR"]
HORIZON = 20
FIRST_TEST_YEAR = 2006
SEED = 20260816
START = "1999-01-01"
END = "2026-08-15"

FEATURES = ("vix", "vix_chg_5d", "drawdown_pct", "ret_1m_pct", "ret_3m_pct",
            "ret_6m_pct", "realised_vol_20d", "realised_vol_60d",
            "vol_ratio_20_60", "dist_from_200d_pct", "downside_vol_20d",
            "abs_ret_5d_mean")

BASELINES = ("climatology", "gaussian_vol", "scaled_empirical")


def _build(a) -> tuple:
    """State vectors and H-day forward returns, pooled across the universe."""
    import pandas as pd
    import yfinance as yf

    frames = []
    for tkr in UNIVERSE:
        px = yf.download(tkr, start=a.start, end=a.end, progress=False)["Close"]
        if isinstance(px, pd.DataFrame):
            px = px.squeeze()
        px = px.dropna()
        if len(px) < 1500:
            print(f"  {tkr}: too little history — skipped")
            continue
        r = px.pct_change().dropna()
        rv20 = r.rolling(20).std() * np.sqrt(252) * 100.0
        rv60 = r.rolling(60).std() * np.sqrt(252) * 100.0
        dn = r.clip(upper=0.0).rolling(20).std() * np.sqrt(252) * 100.0
        roll_max = px.rolling(252, min_periods=20).max()
        ma200 = px.rolling(200, min_periods=50).mean()

        df = pd.DataFrame(index=r.index)
        # Every feature shifted: no row may see the day it is predicting.
        df["drawdown_pct"] = ((px / roll_max - 1.0) * 100.0).shift(1)
        df["ret_1m_pct"] = (px.pct_change(21) * 100.0).shift(1)
        df["ret_3m_pct"] = (px.pct_change(63) * 100.0).shift(1)
        df["ret_6m_pct"] = (px.pct_change(126) * 100.0).shift(1)
        df["realised_vol_20d"] = rv20.shift(1)
        df["realised_vol_60d"] = rv60.shift(1)
        df["vol_ratio_20_60"] = (rv20 / rv60).shift(1)
        df["dist_from_200d_pct"] = ((px / ma200 - 1.0) * 100.0).shift(1)
        df["downside_vol_20d"] = dn.shift(1)
        df["abs_ret_5d_mean"] = (r.abs().rolling(5).mean() * 100.0).shift(1)
        df["fwd"] = ((px.shift(-HORIZON) / px - 1.0) * 100.0)
        df["security"] = tkr
        frames.append(df)
        print(f"  {tkr}: {len(df)} rows")

    vix = yf.download("^VIX", start=a.start, end=a.end, progress=False)["Close"]
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()
    vix = vix.dropna()

    all_df = pd.concat(frames).sort_index()
    all_df["vix"] = vix.reindex(all_df.index).ffill().shift(1)
    all_df["vix_chg_5d"] = (vix.pct_change(5) * 100.0
                            ).reindex(all_df.index).ffill().shift(1)

    all_df = all_df.dropna(subset=["fwd", "realised_vol_20d"])
    all_df = all_df.sort_index(kind="stable")

    X = all_df[list(FEATURES)].to_numpy(dtype=float)
    y = all_df["fwd"].to_numpy(dtype=float)
    rv = all_df["realised_vol_20d"].to_numpy(dtype=float)
    dates = all_df.index.to_numpy()
    secs = all_df["security"].to_numpy()
    return X, y, rv, dates, secs, all_df


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--power-only", action="store_true")
    ap.add_argument("--skip-slice-claim", action="store_true",
                    help="for reruns; the claim is idempotent-by-refusal")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    # ── the slice claim, BEFORE any data is read ───────────────────────────
    ident = SliceIdentity(
        securities=tuple(UNIVERSE), start=a.start, end=a.end,
        outcome_horizon_days=HORIZON,
        outcome_definition="H-day forward return distribution",
        information_cutoff=a.end)
    reg = SliceRegister()
    verdict = reg.check(ident, "EXPLORE", trial="WM0")
    print(f"slice {ident.slice_id}: EXPLORE allowed={verdict['allowed']}")
    if verdict["prior_readers"]:
        print(f"  prior readers of overlapping data: {verdict['prior_readers']}")
        print("  (EXPLORE may revisit; this trial may NEVER be reported as "
              "confirmation)")

    print(f"\nbuilding state for {len(UNIVERSE)} securities ...")
    X, y, rv, dates, secs, df = _build(a)
    print(f"\npooled: {len(y)} rows, {X.shape[1]} features, "
          f"{str(dates.min())[:10]} -> {str(dates.max())[:10]}")

    folds = WM.walk_forward_folds(dates, FIRST_TEST_YEAR, HORIZON)
    print(f"walk-forward: {len(folds)} annual folds, "
          f"{HORIZON * 2}d embargo at each boundary")

    if a.power_only:
        # The primary metric is a paired pinball-loss DIFFERENCE, so the
        # dispersion R13 needs is the sd of that difference, not the sd of the
        # return. Estimated from BASELINE vs BASELINE — gaussian_vol against
        # scaled_empirical — which requires fitting nothing, so the model under
        # test cannot inform its own power declaration.
        diffs = []
        for tr, te, _f in folds:
            g = WM.gaussian_vol_quantiles(y[tr], rv[te], HORIZON)
            s = WM.scaled_empirical_quantiles(y[tr], rv[tr], rv[te], HORIZON)
            diffs.append(WM.pinball_loss(y[te], g).mean(axis=1)
                         - WM.pinball_loss(y[te], s).mean(axis=1))
        d = np.concatenate(diffs)
        ref = np.concatenate([
            WM.pinball_loss(y[te], WM.scaled_empirical_quantiles(
                y[tr], rv[tr], rv[te], HORIZON)).mean(axis=1)
            for tr, te, _f in folds])
        n_test = sum(f[1].size for f in folds)
        block = HORIZON * 2
        n_eff = n_test / block          # honest, per R13b

        print("\n=== POWER INPUTS (design stage) ===")
        print(f"  baseline mean pinball loss  = {ref.mean():.5f} pp")
        print(f"  sd of paired loss difference= {np.std(d, ddof=1):.5f} pp "
              f"(gaussian_vol vs scaled_empirical — no model fitted)")
        print(f"  outcome_horizon_days        = {HORIZON}")
        print(f"  test observations           = {n_test}")
        print(f"  effective n (R13b, {block}d blocks) = {n_eff:.0f}")
        floor = (1.959963985 + 0.8416212336) * np.std(d, ddof=1) / np.sqrt(n_eff)
        print(f"  smallest resolvable loss difference = {floor:.5f} pp "
              f"({100.0 * floor / ref.mean():.2f}% of baseline loss)")
        print(f"  securities                  = {len(set(secs))}")
        print("\n--power-only: no model was fitted.")
        return 0

    if not a.skip_slice_claim:
        try:
            reg.claim(ident, "EXPLORE", trial="WM0",
                      consumed_at="2026-08-16T18:00:00Z",
                      prereg="docs/TRIALS/PREREG_WM0_WORLD_MODEL_V0.md",
                      note="World Model v0 conditional distribution training")
        except SliceRefusal as exc:
            print(f"REFUSED: {exc}")
            return 1

    # ── train ──────────────────────────────────────────────────────────────
    nq = len(WM.QUANTILES)
    losses: dict[str, list] = {k: [] for k in ("world_model", *BASELINES)}
    preds_all: dict[str, list] = {k: [] for k in ("world_model", *BASELINES)}
    y_all, fold_rows = [], []

    for tr, te, fold in folds:
        model = WM.WorldModelV0(seed=SEED).fit(X[tr], y[tr], FEATURES)
        p = {
            "world_model": model.predict(X[te]),
            "climatology": WM.climatology_quantiles(y[tr], te.size),
            "gaussian_vol": WM.gaussian_vol_quantiles(y[tr], rv[te], HORIZON),
            "scaled_empirical": WM.scaled_empirical_quantiles(
                y[tr], rv[tr], rv[te], HORIZON),
        }
        row = {"train_end": fold.train_end, "test_start": fold.test_start,
               "test_end": fold.test_end, "n_train": fold.n_train,
               "n_test": fold.n_test}
        for k, v in p.items():
            L = WM.pinball_loss(y[te], v)
            losses[k].append(L)
            preds_all[k].append(v)
            row[f"{k}_pinball"] = float(L.mean())
        y_all.append(y[te])
        fold_rows.append(row)
        print(f"  {fold.test_start[:4]}  n_tr {fold.n_train:>6d} "
              f"n_te {fold.n_test:>5d}   "
              + "  ".join(f"{k[:9]} {row[f'{k}_pinball']:.4f}"
                          for k in ("world_model", "scaled_empirical")))

    y_cat = np.concatenate(y_all)
    L = {k: np.concatenate(v, axis=0) for k, v in losses.items()}
    P = {k: np.concatenate(v, axis=0) for k, v in preds_all.items()}

    # ── the comparison of record ───────────────────────────────────────────
    print(f"\n{'=' * 78}\nPOOLED, {len(y_cat)} out-of-sample observations\n")
    print(f"{'model':<18s} {'mean pinball':>13s} {'vs sc_emp %':>12s} "
          f"{'tail pinball':>13s} {'vs sc_emp %':>12s}")
    tail_idx = [i for i, q in enumerate(WM.QUANTILES) if q <= 0.10]
    ref = L["scaled_empirical"]
    summary = {}
    for k in ("world_model", *BASELINES):
        m = float(L[k].mean())
        t = float(L[k][:, tail_idx].mean())
        rel = 100.0 * (1.0 - m / float(ref.mean()))
        relt = 100.0 * (1.0 - t / float(ref[:, tail_idx].mean()))
        summary[k] = {"mean_pinball": m, "tail_pinball": t,
                      "rel_vs_scaled_empirical_pct": rel,
                      "tail_rel_vs_scaled_empirical_pct": relt}
        print(f"{k:<18s} {m:>13.5f} {rel:>+12.2f} {t:>13.5f} {relt:>+12.2f}")

    # ── paired difference with its own SE (SS18) ───────────────────────────
    # The difference is the estimand, not the two levels. Block bootstrap over
    # calendar blocks, because overlapping H-day outcomes on co-moving
    # securities are nowhere near independent (R13b, the same error N20 hit).
    rng = np.random.default_rng(SEED)
    d = L["world_model"].mean(axis=1) - ref.mean(axis=1)
    n = d.size
    block = HORIZON * 2
    nb = int(np.ceil(n / block))
    boots = []
    for _ in range(2000):
        starts = rng.integers(0, max(1, n - block), size=nb)
        pos = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        boots.append(float(d[pos].mean()))
    lo, hi = float(np.quantile(boots, 0.05)), float(np.quantile(boots, 0.95))
    se = float(np.std(boots, ddof=1))
    mde = (1.959963985 + 0.8416212336) * se

    print(f"\npaired difference (world_model - scaled_empirical), "
          f"block bootstrap {block}d:")
    print(f"  mean {d.mean():+.6f}   90% CI [{lo:+.6f}, {hi:+.6f}]   "
          f"SE {se:.6f}")
    print(f"  80%-power MDE {mde:.6f}  "
          f"({100.0 * mde / float(ref.mean()):.2f}% of baseline loss)")
    beats = hi < 0.0
    worse = lo > 0.0
    verdict_txt = ("BEATS_SCALED_EMPIRICAL" if beats else
                   "WORSE_THAN_SCALED_EMPIRICAL" if worse else
                   "NOT_DETECTABLE_IN_SCOPE")
    print(f"  VERDICT: {verdict_txt}")

    # ── calibration, reported whatever the verdict ─────────────────────────
    print(f"\ncalibration — empirical P(y <= q_tau), target = tau:")
    print(f"{'model':<18s} " + "".join(f"{q:>8.2f}" for q in WM.QUANTILES))
    cov = {}
    for k in ("world_model", *BASELINES):
        c = WM.pit_coverage(y_cat, P[k])
        cov[k] = [float(x) for x in c]
        print(f"{k:<18s} " + "".join(f"{x:>8.3f}" for x in c))

    print(f"\nper-quantile pinball, world_model vs scaled_empirical (% better):")
    per_q = 100.0 * (1.0 - L["world_model"].mean(axis=0) / ref.mean(axis=0))
    print(f"{'tau':<18s} " + "".join(f"{q:>8.2f}" for q in WM.QUANTILES))
    print(f"{'% better':<18s} " + "".join(f"{x:>+8.2f}" for x in per_q))

    payload = {
        "trial": "WM0",
        "prereg": "docs/TRIALS/PREREG_WM0_WORLD_MODEL_V0.md",
        "slice_id": ident.slice_id,
        "universe": UNIVERSE, "horizon_days": HORIZON,
        "features": list(FEATURES), "quantiles": list(WM.QUANTILES),
        "seed": SEED, "n_folds": len(folds),
        "n_test_obs": int(len(y_cat)),
        "embargo_days": HORIZON * 2,
        "comparator_of_record": "scaled_empirical",
        "summary": summary,
        "paired_difference": {
            "mean": float(d.mean()), "ci_lo": lo, "ci_hi": hi, "se": se,
            "mde_80pct_power": float(mde),
            "mde_as_pct_of_baseline": float(100.0 * mde / float(ref.mean())),
            "verdict": verdict_txt,
        },
        "per_quantile_pct_better_vs_scaled_empirical": [float(x) for x in per_q],
        "calibration": cov,
        "folds": fold_rows,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
