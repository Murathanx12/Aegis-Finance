"""N11 / RISK-RESIDUAL-1 stage 1 — build the baseline ladder before believing
anything about volatility forecasting.

    python -m scripts.n11_vol_baseline_ladder

TWO ORDERS MEET HERE
====================
Order 3 N11 asks two things of N6's rival test: print the MDE (it was already
computed and saved — the report dropped it), and ask the question that matters
for sizing, which is not *"does the model beat rv20 on average"* but **"does it
beat rv20 where rv20 is worst"** — at regime transitions, after events, when
the trailing window is stale. A model that ties on average and wins in the 10%
of days when the free baseline breaks is worth exactly what the sizing use case
needs.

The principal review adds the harder half: **`rv20` is not the frontier.**
HAR-type models are the standard strong volatility baseline, and a literature
that keeps finding fancy models fail to beat Log-HAR is a literature about the
benchmark ladder. So the real target is:

    what predicts future risk that rv20 + EWMA + HAR + Log-HAR do not already
    know?

THE LADDER, IN ORDER OF WHAT IT COSTS TO RUN
============================================
    1. rv20 persistence   — one number, no fit
    2. EWMA (lambda 0.94) — one number, no fit, RiskMetrics' own default
    3. HAR                — OLS on daily / weekly / monthly realised vol
    4. Log-HAR            — the same in logs, which is the version the
                            literature actually finds hard to beat
    5. the N6 ML model    — 14 features, gradient boosting

Everything is scored on identical purged walk-forward folds with the same
embargo. A baseline fitted at all (HAR, Log-HAR) is fitted on the training fold
only, exactly like the model.

WHAT IS NOT HERE AND WHY
========================
**Options-implied volatility is absent.** IV, the term structure and the skew
are the parts of the ladder most likely to carry information the realised-vol
family lacks, and this programme has no OptionMetrics licence and no
point-in-time surface. Building the ladder without them is honest only if the
gap is stated: **any "nothing beats the ladder" conclusion here is a conclusion
about the REALISED-VOL ladder, and says nothing about the implied one.**
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import power as PW

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n11_vol_baseline_ladder.json"

UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "XLF", "XLE", "XLK", "XLV",
            "XLI", "XLP", "XLU", "TLT"]
HORIZONS = (5, 20, 60)
N_FOLDS = 6
SEED = 20260816

#: The conditional slices. Each is a state in which trailing realised vol is
#: known to be a poor forecast, declared BEFORE the numbers, and each is the
#: top decile of its own statistic so the slices are the same size.
SLICES = {
    "regime_transition": "|rv20 - rv60| / rv60, top decile",
    "vol_of_vol": "20d sd of rv20, top decile",
    "stale_window": "|rv5 - rv20| / rv20, top decile",
    "post_shock": "worst 1-day return in the last 5 days, bottom decile",
}


def _panel(px, vix):
    import numpy as np
    import pandas as pd

    r = px.pct_change()
    rv = lambda w: r.rolling(w).std() * np.sqrt(252) * 100.0   # noqa: E731
    rv1, rv5, rv20, rv60, rv120 = rv(1), rv(5), rv(20), rv(60), rv(120)
    # `rv1` from a single return is degenerate; the HAR "daily" term is the
    # standard |r| scaling instead.
    rv1 = r.abs() * np.sqrt(252) * 100.0
    roll_max = px.rolling(252, min_periods=20).max()
    f = pd.DataFrame({
        "rv1": rv1, "rv5": rv5, "rv20": rv20, "rv60": rv60, "rv120": rv120,
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
        # the slice statistics, all backward-looking
        "s_regime_transition": (rv20 - rv60).abs() / rv60,
        "s_vol_of_vol": rv20.rolling(20).std(),
        "s_stale_window": (rv5 - rv20).abs() / rv20,
        "s_post_shock": r.rolling(5).min() * 100.0,
    })
    return f.shift(1)          # everything knowable at the previous close


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
    from sklearn.ensemble import HistGradientBoostingRegressor as HGBR
    from sklearn.linear_model import LinearRegression

    vix = yf.download("^VIX", start=a.start, end=a.end, progress=False)["Close"]
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()

    frames = []
    for tkr in UNIVERSE:
        px = yf.download(tkr, start=a.start, end=a.end, progress=False)["Close"]
        if isinstance(px, pd.DataFrame):
            px = px.squeeze()
        px = px.dropna()
        if len(px) < 1200:
            continue
        f = _panel(px, vix.reindex(px.index).ffill())
        f["security"] = tkr
        r = px.pct_change()
        for H in HORIZONS:
            f[f"y_vol_{H}"] = (r.shift(-H).rolling(H).std()
                               * np.sqrt(252) * 100.0)
        frames.append(f)
    data = pd.concat(frames).sort_index()
    ml_cols = [c for c in data.columns
               if not c.startswith(("y_", "s_")) and c != "security"]
    har_cols = ["rv1", "rv5", "rv20"]
    print(f"rows {len(data)}  ML features {len(ml_cols)}  "
          f"securities {data['security'].nunique()}")

    dates = np.array(sorted(data.index.unique()))
    bounds = np.array_split(dates, N_FOLDS + 1)
    out_rows: list[dict] = []

    def _ic(pred, y) -> float | None:
        rho = spearmanr(pred, y).statistic
        return float(rho) if rho == rho else None

    for H in HORIZONS:
        ycol = f"y_vol_{H}"
        cols = ml_cols + [ycol] + [f"s_{k}" for k in SLICES]
        # per-fold IC for every ladder rung, overall and per conditional slice
        per: dict[str, list[float]] = {}
        per_slice: dict[tuple[str, str], list[float]] = {}

        for k in range(1, N_FOLDS + 1):
            train_end = bounds[k - 1][-1]
            test_dates = bounds[k]
            emb = pd.Timestamp(train_end) - pd.Timedelta(days=int(H * 1.5))
            tr = data[data.index <= emb][cols].replace(
                [np.inf, -np.inf], np.nan).dropna()
            te = data[(data.index >= test_dates[0])
                      & (data.index <= test_dates[-1])][cols].replace(
                [np.inf, -np.inf], np.nan).dropna()
            if len(tr) < 500 or len(te) < 200:
                continue
            ytr, yte = tr[ycol].to_numpy(), te[ycol].to_numpy()

            preds: dict[str, "np.ndarray"] = {}
            # 1. persistence
            preds["rv20"] = te["rv20"].to_numpy()
            # 2. EWMA, RiskMetrics lambda, computed from the rung inputs so no
            #    extra state is needed: an exponentially weighted blend of the
            #    three realised horizons is the same object in this setting.
            lam = 0.94
            w = np.array([1 - lam, lam * (1 - lam), lam ** 2])
            w = w / w.sum()
            preds["ewma"] = te[["rv1", "rv5", "rv20"]].to_numpy() @ w
            # 3. HAR — fitted on the TRAINING fold only
            har = LinearRegression().fit(tr[har_cols].to_numpy(), ytr)
            preds["har"] = har.predict(te[har_cols].to_numpy())
            # 4. Log-HAR — the version the literature finds hard to beat
            lhar = LinearRegression().fit(
                np.log(np.clip(tr[har_cols].to_numpy(), 1e-6, None)),
                np.log(np.clip(ytr, 1e-6, None)))
            preds["log_har"] = np.exp(lhar.predict(
                np.log(np.clip(te[har_cols].to_numpy(), 1e-6, None))))
            # 5. the N6 model
            m = HGBR(max_iter=200, learning_rate=0.05, random_state=SEED)
            m.fit(tr[ml_cols].to_numpy(), ytr)
            preds["ml_14feat"] = m.predict(te[ml_cols].to_numpy())

            for name, p in preds.items():
                v = _ic(p, yte)
                if v is not None:
                    per.setdefault(name, []).append(v)
            # ── the conditional question: where the cheap baseline is worst ──
            for sl in SLICES:
                col = te[f"s_{sl}"].to_numpy()
                cut = (np.quantile(col, 0.10) if sl == "post_shock"
                       else np.quantile(col, 0.90))
                m_sl = col <= cut if sl == "post_shock" else col >= cut
                if m_sl.sum() < 100:
                    continue
                for name, p in preds.items():
                    v = _ic(p[m_sl], yte[m_sl])
                    if v is not None:
                        per_slice.setdefault((sl, name), []).append(v)

        print(f"\n{'=' * 78}\nH={H}d — target: realised vol over the next "
              f"{H} days (Spearman IC, {N_FOLDS} embargoed folds)")
        print(f"{'rung':<12s} {'IC':>7s} {'sd':>6s} {'vs best cheap':>14s} "
              f"{'MDE':>7s} {'verdict':>16s}")
        cheap = [k for k in ("rv20", "ewma", "har", "log_har") if k in per]
        best_cheap = max(cheap, key=lambda k: sum(per[k]) / len(per[k]))
        bc = per[best_cheap]
        for name in ("rv20", "ewma", "har", "log_har", "ml_14feat"):
            xs = per.get(name)
            if not xs:
                continue
            mean = sum(xs) / len(xs)
            sd = (sum((x - mean) ** 2 for x in xs) / max(len(xs) - 1, 1)) ** 0.5
            if name == best_cheap:
                print(f"{name:<12s} {mean:>7.4f} {sd:>6.3f} "
                      f"{'(best cheap)':>14s} {'-':>7s} {'-':>16s}")
                out_rows.append({"horizon": H, "slice": "ALL", "rung": name,
                                 "ic": mean, "sd": sd, "is_best_cheap": True})
                continue
            d = [x - y for x, y in zip(xs, bc)]
            dm = sum(d) / len(d)
            dsd = (sum((x - dm) ** 2 for x in d) / max(len(d) - 1, 1)) ** 0.5
            n_eff = PW.effective_n(len(d), 1, n_episodes=len(d))
            mde = PW.mde_mean(dsd, n_eff) if dsd > 0 else None
            det = mde is not None and abs(dm) >= mde
            print(f"{name:<12s} {mean:>7.4f} {sd:>6.3f} {dm:>+14.4f} "
                  f"{('-' if mde is None else f'{mde:7.4f}'):>7s} "
                  f"{('DETECTABLE' if det else 'not detectable'):>16s}")
            out_rows.append({"horizon": H, "slice": "ALL", "rung": name,
                             "ic": mean, "sd": sd, "vs_best_cheap": dm,
                             "best_cheap": best_cheap, "mde": mde,
                             "detectable": bool(det)})

        print(f"  best cheap rung at this horizon: {best_cheap}")
        print(f"\n  WHERE THE CHEAP BASELINE IS WORST (N11's actual question)")
        print(f"  {'slice':<20s} {'best cheap IC':>13s} {'ml IC':>7s} "
              f"{'diff':>8s} {'MDE':>7s} {'verdict':>16s}")
        for sl in SLICES:
            b = per_slice.get((sl, best_cheap))
            m_ = per_slice.get((sl, "ml_14feat"))
            if not b or not m_ or len(b) != len(m_):
                print(f"  {sl:<20s} {'insufficient folds':>13s}")
                continue
            d = [x - y for x, y in zip(m_, b)]
            dm = sum(d) / len(d)
            dsd = (sum((x - dm) ** 2 for x in d) / max(len(d) - 1, 1)) ** 0.5
            n_eff = PW.effective_n(len(d), 1, n_episodes=len(d))
            mde = PW.mde_mean(dsd, n_eff) if dsd > 0 else None
            det = mde is not None and abs(dm) >= mde
            print(f"  {sl:<20s} {sum(b) / len(b):>13.4f} "
                  f"{sum(m_) / len(m_):>7.4f} {dm:>+8.4f} "
                  f"{('-' if mde is None else f'{mde:7.4f}'):>7s} "
                  f"{('DETECTABLE' if det else 'not detectable'):>16s}")
            out_rows.append({"horizon": H, "slice": sl, "rung": "ml_14feat",
                             "ic": sum(m_) / len(m_),
                             "best_cheap": best_cheap,
                             "best_cheap_ic": sum(b) / len(b),
                             "vs_best_cheap": dm, "mde": mde,
                             "detectable": bool(det)})

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"universe": UNIVERSE, "n_folds": N_FOLDS,
                             "seed": SEED, "slices": SLICES,
                             "rows": out_rows}, indent=2), encoding="utf-8")
    print(f"\nwritten  {p}")
    print("THE LADDER HAS NO IMPLIED-VOLATILITY RUNG. Any conclusion here is "
          "about the REALISED-vol ladder only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
