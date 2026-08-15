"""N6 — are second moments detectable where first moments are not?

    python -m scripts.n6_moments

THE CLAIM, AND WHY IT DESERVES A TEST RATHER THAN A STORY
==========================================================
Four results point the same way and none of them was designed to:

* MARKET-GRAPH-1's one clean positive was about **co-movement**;
* GRAPH-COVARIANCE-1 closed because perfect foresight of forward correlation
  was worth almost nothing **inside a mean-variance architecture**;
* IIF-1's own pre-registration chose **magnitude** over direction after the
  spread of the directional prior came out at 0.0036 against 0.1183;
* NIGHT-3 found the LLM earns no role in stock **selection** over 16,320
  decisions.

Stated as a regularity: **second moments keep being detectable and first
moments keep not being.** Four coincidences are a story. This is the test.

If it holds, the consequence is architectural and large: the world model's
volatility / co-movement / drawdown heads should be built FIRST and direction
demoted, and a risk-model product may be the defensible one.

THE DESIGN IS THE WHOLE POINT
==============================
One feature set. One model class. One set of purged, embargoed walk-forward
splits. Three targets differing ONLY in which moment they ask about:

    sign(r_H)          first moment    AUC-ROC
    |r_H|              second moment   Spearman IC
    realised_vol_H     second moment   Spearman IC

Anything else — different features per target, different splits, different
model — and a difference in skill is a difference in setup.

DECLARED VERDICT RULE (protocol, before any number)
====================================================
SUPPORTED only if the second-moment targets clear their MDEs **and** the
first-moment target does not, in the same splits on the same features. If both
clear, the claim is wrong and direction is predictable here too. If neither
clears, the test was underpowered and says nothing — which must be reported as
saying nothing rather than as agreement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import power as PW

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n6_moments.json"

UNIVERSE = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK", "XLV", "XLP", "XLU",
            "XLY", "XLI", "XLB"]
HORIZONS = (5, 20, 60)
#: Walk-forward: train on everything before the fold, test on the fold. Embargo
#: of H days between them so the last training label cannot overlap the first
#: test window.
N_FOLDS = 6
SEED = 20260816


def _fmt(x):
    return '-' if x is None else f'{x:6.4f}'


def _features(px, vix):
    import numpy as np
    import pandas as pd

    r = px.pct_change()
    rv20 = r.rolling(20).std() * np.sqrt(252) * 100.0
    rv60 = r.rolling(60).std() * np.sqrt(252) * 100.0
    rv120 = r.rolling(120).std() * np.sqrt(252) * 100.0
    roll_max = px.rolling(252, min_periods=20).max()
    f = pd.DataFrame({
        "rv20": rv20,
        "rv60": rv60,
        "vol_ratio_20_60": rv20 / rv60,
        "vol_ratio_60_120": rv60 / rv120,
        "drawdown_pct": (px / roll_max - 1.0) * 100.0,
        "ret_1m": px.pct_change(21) * 100.0,
        "ret_3m": px.pct_change(63) * 100.0,
        "ret_6m": px.pct_change(126) * 100.0,
        "ret_12m": px.pct_change(252) * 100.0,
        "vix": vix,
        "vix_ratio_20": vix / vix.rolling(20).mean(),
        "abs_ret_20d_mean": r.abs().rolling(20).mean() * 100.0,
        "skew_60d": r.rolling(60).skew(),
        "kurt_60d": r.rolling(60).kurt(),
    })
    # EVERY feature is lagged one day: the state must be knowable at the close
    # BEFORE the window it labels, or the model reads its own outcome.
    return f.shift(1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="1999-01-01")
    ap.add_argument("--end", default="2026-08-15")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    import numpy as np
    import pandas as pd
    import yfinance as yf
    from scipy.stats import spearmanr
    from sklearn.ensemble import HistGradientBoostingClassifier as HGBC
    from sklearn.ensemble import HistGradientBoostingRegressor as HGBR
    from sklearn.metrics import roc_auc_score

    vix = yf.download("^VIX", start=a.start, end=a.end, progress=False)["Close"]
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()

    frames = []
    for tkr in UNIVERSE:
        px = yf.download(tkr, start=a.start, end=a.end, progress=False)["Close"]
        if isinstance(px, pd.DataFrame):
            px = px.squeeze()
        px = px.dropna()
        if len(px) < 1000:
            print(f"  {tkr}: too short, skipped")
            continue
        v = vix.reindex(px.index).ffill()
        f = _features(px, v)
        f["security"] = tkr
        r = px.pct_change()
        for H in HORIZONS:
            fwd = px.shift(-H) / px - 1.0
            f[f"y_sign_{H}"] = (fwd > 0).astype(float)
            f[f"y_absret_{H}"] = fwd.abs() * 100.0
            f[f"y_vol_{H}"] = (r.shift(-H).rolling(H).std()
                               * np.sqrt(252) * 100.0)
        frames.append(f)
        print(f"  {tkr:<5s} {len(f)} rows "
              f"{px.index.min().date()} -> {px.index.max().date()}")

    if not frames:
        return 1
    data = pd.concat(frames).sort_index()
    feat_cols = [c for c in data.columns
                 if not c.startswith("y_") and c != "security"]
    print(f"\nrows {len(data)}   features {len(feat_cols)}   "
          f"securities {data['security'].nunique()}")

    dates = np.array(sorted(data.index.unique()))
    bounds = np.array_split(dates, N_FOLDS + 1)
    results: list[dict] = []

    for H in HORIZONS:
        targets = {
            "sign (FIRST moment)": (f"y_sign_{H}", "auc"),
            "|return| (SECOND)": (f"y_absret_{H}", "ic"),
            "realised vol (SECOND)": (f"y_vol_{H}", "ic"),
        }
        print(f"\n── horizon {H} days ──")
        for label, (ycol, kind) in targets.items():
            scores: list[float] = []
            for k in range(1, N_FOLDS + 1):
                train_end = bounds[k - 1][-1]
                test_dates = bounds[k]
                # EMBARGO: the last H days before the test fold are dropped so
                # a training label cannot overlap a test window.
                emb = pd.Timestamp(train_end) - pd.Timedelta(days=int(H * 1.5))
                tr = data[data.index <= emb]
                te = data[(data.index >= test_dates[0])
                          & (data.index <= test_dates[-1])]
                cols = feat_cols + [ycol]
                tr = tr[cols].replace([np.inf, -np.inf], np.nan).dropna()
                te = te[cols].replace([np.inf, -np.inf], np.nan).dropna()
                if len(tr) < 500 or len(te) < 100:
                    continue
                Xtr, ytr = tr[feat_cols].to_numpy(), tr[ycol].to_numpy()
                Xte, yte = te[feat_cols].to_numpy(), te[ycol].to_numpy()
                if kind == "auc":
                    if len(set(ytr.tolist())) < 2 or len(set(yte.tolist())) < 2:
                        continue
                    m = HGBC(max_iter=200, learning_rate=0.05,
                             random_state=SEED)
                    m.fit(Xtr, ytr)
                    p = m.predict_proba(Xte)[:, 1]
                    scores.append(float(roc_auc_score(yte, p)))
                else:
                    m = HGBR(max_iter=200, learning_rate=0.05,
                             random_state=SEED)
                    m.fit(Xtr, ytr)
                    p = m.predict(Xte)
                    rho = spearmanr(p, yte).statistic
                    if rho == rho:
                        scores.append(float(rho))
            if not scores:
                print(f"  {label:<24s} no usable folds")
                continue
            # ── THE RIVAL EXPLANATION, TESTED RATHER THAN NOTED ────────────
            # Volatility is persistent. A model handed `rv20` as a feature and
            # asked to predict forward volatility can score a large IC by
            # copying it, and "volatility is persistent" is not a finding — it
            # is the reason the second moment is predictable at all.
            #
            # So every second-moment score is reported beside the score of the
            # FREE predictor: trailing 20-day realised volatility, alone, with
            # no model. The interesting quantity is the DIFFERENCE, and §18
            # says a difference is tested with its own SE, never by comparing
            # two numbers to a threshold separately.
            if kind == "ic":
                base_scores = []
                for k in range(1, N_FOLDS + 1):
                    test_dates = bounds[k]
                    te = data[(data.index >= test_dates[0])
                              & (data.index <= test_dates[-1])]
                    te = te[["rv20", ycol]].replace(
                        [np.inf, -np.inf], np.nan).dropna()
                    if len(te) < 100:
                        continue
                    rho = spearmanr(te["rv20"].to_numpy(),
                                    te[ycol].to_numpy()).statistic
                    if rho == rho:
                        base_scores.append(float(rho))
            else:
                base_scores = []
            mean = sum(scores) / len(scores)
            sd = ((sum((x - mean) ** 2 for x in scores)
                   / max(len(scores) - 1, 1)) ** 0.5)
            # Folds are consecutive periods of the SAME securities, so they are
            # not independent draws. n_effective is bounded by the number of
            # folds and then again by the market regimes they span.
            n_eff = PW.effective_n(len(scores), 1, n_episodes=len(scores))
            mde = PW.mde_mean(sd, n_eff) if sd > 0 else None
            null = 0.5 if kind == "auc" else 0.0
            edge = mean - null
            det = (mde is not None and abs(edge) >= mde)
            # §18: the model-minus-baseline difference, PAIRED by fold, with
            # its own SE. Not "both are large, so the model must be adding".
            beats = None
            if base_scores and len(base_scores) == len(scores):
                diffs = [m - b for m, b in zip(scores, base_scores)]
                dm = sum(diffs) / len(diffs)
                dsd = ((sum((x - dm) ** 2 for x in diffs)
                        / max(len(diffs) - 1, 1)) ** 0.5)
                dmde = PW.mde_mean(dsd, n_eff) if dsd > 0 else None
                beats = {
                    "baseline_mean": sum(base_scores) / len(base_scores),
                    "diff": dm, "diff_sd": dsd, "diff_mde": dmde,
                    "detectable": (dmde is not None and abs(dm) >= dmde),
                }
            results.append({
                "horizon": H, "target": label, "metric": kind,
                "mean": mean, "sd": sd, "n_folds": len(scores),
                "n_effective": n_eff, "mde": mde, "null": null,
                "edge": edge, "detectable": det,
                "folds": [round(x, 4) for x in scores],
                "vs_persistence_baseline": beats,
            })
            print(f"  {label:<24s} {kind.upper():<4s} {mean:7.4f}  "
                  f"vs null {null:.2f}  edge {edge:+7.4f}  "
                  f"sd {sd:6.4f}  MDE {'-' if mde is None else f'{mde:6.4f}'}  "
                  f"{'DETECTABLE' if det else 'not detectable'}")
            if beats:
                print(f"    {'vs FREE rv20 baseline':<22s} "
                      f"base {beats['baseline_mean']:7.4f}  "
                      f"model-base {beats['diff']:+7.4f}  "
                      f"MDE {_fmt(beats['diff_mde'])}  "
                      f"{'ADDS' if beats['detectable'] else 'adds nothing detectable'}")

    # ── D4: is direction useless GLOBALLY but useful CONDITIONALLY? ────────
    # N6 says the sign is a coin. D4's hypothesis is that this is an average
    # over a mixture: a weak directional edge could be economically useful
    # deployed ONLY where the move distribution is wide enough to pay for
    # being right. That is a claim about a CONDITIONAL AUC, and it is cheap to
    # test once the two models already exist.
    #
    # §18 applies: the quantity is the DIFFERENCE between conditional and
    # unconditional AUC, tested with its own SE, not two numbers compared to
    # 0.5 separately.
    print("\n── D4: direction INSIDE the predicted-high-magnitude subset ──")
    d4: list[dict] = []
    for H in HORIZONS:
        uncond, cond, kept = [], [], []
        for k in range(1, N_FOLDS + 1):
            train_end = bounds[k - 1][-1]
            test_dates = bounds[k]
            emb = pd.Timestamp(train_end) - pd.Timedelta(days=int(H * 1.5))
            cols = feat_cols + [f"y_sign_{H}", f"y_absret_{H}"]
            tr = data[data.index <= emb][cols].replace(
                [np.inf, -np.inf], np.nan).dropna()
            te = data[(data.index >= test_dates[0])
                      & (data.index <= test_dates[-1])][cols].replace(
                [np.inf, -np.inf], np.nan).dropna()
            if len(tr) < 500 or len(te) < 200:
                continue
            Xtr, Xte = tr[feat_cols].to_numpy(), te[feat_cols].to_numpy()
            ys_tr, ys_te = tr[f"y_sign_{H}"].to_numpy(), \
                te[f"y_sign_{H}"].to_numpy()
            ya_tr = tr[f"y_absret_{H}"].to_numpy()
            if len(set(ys_tr.tolist())) < 2 or len(set(ys_te.tolist())) < 2:
                continue
            mag = HGBR(max_iter=200, learning_rate=0.05, random_state=SEED)
            mag.fit(Xtr, ya_tr)
            sgn = HGBC(max_iter=200, learning_rate=0.05, random_state=SEED)
            sgn.fit(Xtr, ys_tr)
            p_sign = sgn.predict_proba(Xte)[:, 1]
            p_mag = mag.predict(Xte)
            cut = float(np.quantile(p_mag, 0.80))
            m = p_mag >= cut
            if m.sum() < 50 or len(set(ys_te[m].tolist())) < 2:
                continue
            uncond.append(float(roc_auc_score(ys_te, p_sign)))
            cond.append(float(roc_auc_score(ys_te[m], p_sign[m])))
            kept.append(int(m.sum()))
        if not cond:
            print(f"  H={H:>3d}d  no usable folds")
            continue
        du = sum(uncond) / len(uncond)
        dc = sum(cond) / len(cond)
        diffs = [c - u for c, u in zip(cond, uncond)]
        dm = sum(diffs) / len(diffs)
        dsd = ((sum((x - dm) ** 2 for x in diffs)
                / max(len(diffs) - 1, 1)) ** 0.5)
        n_eff = PW.effective_n(len(diffs), 1, n_episodes=len(diffs))
        dmde = PW.mde_mean(dsd, n_eff) if dsd > 0 else None
        det = dmde is not None and abs(dm) >= dmde
        d4.append({"horizon": H, "auc_unconditional": du,
                   "auc_high_magnitude": dc, "diff": dm, "diff_sd": dsd,
                   "diff_mde": dmde, "detectable": det,
                   "n_folds": len(diffs), "mean_kept": sum(kept) / len(kept)})
        print(f"  H={H:>3d}d  AUC all {du:.4f}   AUC top-quintile magnitude "
              f"{dc:.4f}   diff {dm:+.4f}  MDE {_fmt(dmde)}  "
              f"{'DETECTABLE' if det else 'not detectable'}")
    if d4 and not any(x["detectable"] for x in d4):
        print("  -> D4 NOT_DETECTABLE at every horizon: conditioning on "
              "predicted magnitude\n     does not reveal a directional edge "
              "that the unconditional test missed.")

    # ── the declared verdict ───────────────────────────────────────────────
    print("\nDECLARED VERDICT RULE — second moments detectable AND first not")
    for H in HORIZONS:
        sub = [r for r in results if r["horizon"] == H]
        first = [r for r in sub if "FIRST" in r["target"]]
        second = [r for r in sub if "SECOND" in r["target"]]
        if not first or not second:
            continue
        f_det = any(r["detectable"] for r in first)
        s_det = [r["detectable"] for r in second]
        if all(s_det) and not f_det:
            v = "SUPPORTED"
        elif f_det and any(s_det):
            v = "REFUTED — direction is detectable here too"
        elif not any(s_det) and not f_det:
            v = "UNDERPOWERED — says nothing, and must be reported as nothing"
        else:
            v = "MIXED"
        print(f"  H={H:>3d}d   first detectable: {f_det}   "
              f"second detectable: {sum(s_det)}/{len(s_det)}   ->  {v}")

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"universe": UNIVERSE, "n_folds": N_FOLDS,
                             "seed": SEED, "results": results,
                             "d4_magnitude_gated_direction": d4}, indent=2),
                 encoding="utf-8")
    print(f"\nwritten  {p}")
    print("Gym output. Cells are hypotheses, never claims (R2 wall 1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
