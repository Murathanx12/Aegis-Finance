"""REGIME-ORACLE-CEILING-1 — is a regime model worth building at all?

Order 24 Phase 5, run FIRST because it decides how the rest of the
session spends its compute. The programme's covariance work already
established the pattern worth copying: lead with an oracle. Do not
spend hours building a regime *predictor* and then discover the ceiling
was zero. Spend one run asking what PERFECT foresight of the regime
label is worth, and let the answer allocate the remaining hours.

Construction
------------
Zoo: the 153 JKP US long-short factors (1926-2025, monthly). A ready
strategy zoo with a century of history and no extra simulation cost.

Regime: quartiles of the CONTEMPORANEOUS month's realized market
volatility. Contemporaneous is the point — that is the oracle's private
knowledge, the thing no predictor can have.

Policies:
  static   hold the single factor with the best full-sample mean
  oracle   at t, know regime s_t, hold the best factor IN THAT REGIME
  oracle_loo  same, but the "best in regime" for month t is estimated
              with month t excluded

`oracle` is deliberately generous (it estimates the conditional best
in-sample). `oracle_loo` removes the trivial self-selection. If even the
generous version does not beat static by a margin the null cannot
manufacture, no predictor of the state can help, and the whole
regime-conditional family closes here for the cost of one run.

THE NULL IS THE WHOLE EXPERIMENT
--------------------------------
With 153 factors and 4 regimes, "pick the best factor in each regime"
selects the max of ~153 noisy means four times over. That manufactures a
gap out of pure noise. So the comparison is not oracle-vs-static, it is
oracle-vs-**a null regime sequence with the same transition matrix** —
same number of regimes, same persistence, same block structure, labels
carrying no information. Anything below the null's 95th percentile is
selection noise wearing a regime costume.

    python -m scripts.regime_oracle_ceiling_1

SCREEN. Resolves a BUILD/DON'T-BUILD question about model families, not
a claim about markets. No promotion, no capital.
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

JKP = _config.OPTIMUS_LEDGER_DIR / "jkp"
PIT = _config.OPTIMUS_LEDGER_DIR / "crsp_pit"
OUT = _config.OPTIMUS_LEDGER_DIR / "regime"
SEED = 20260820
N_NULL = 500
K = 4

#: A regime-conditional policy pays to switch. Each switch liquidates a
#: long-short factor portfolio and builds another: two legs out, two legs
#: in, at a declared 20bps one-way => 80bps per switch. Charged to the
#: oracle AND to every null draw, so the comparison stays fair.
SWITCH_COST = 0.008
#: The programme's standing execution bar (EXECUTION_STANDARD): net
#: excess CAGR >= +3%/yr. A ceiling below it cannot fund a predictor.
ECON_BAR = 0.03


def factor_matrix() -> pd.DataFrame:
    df = pd.read_csv(JKP / "usa_all_factors_monthly_vw_cap.csv")
    df["date"] = pd.to_datetime(df["date"])
    m = df.pivot_table(index="date", columns="name", values="ret")
    m.index = m.index.to_period("M")
    return m


def market_state(years=(1990, 2024)) -> pd.Series:
    """Monthly realized volatility of an equal-weighted market proxy.

    Built from the CRSP PIT daily panel — delisting-inclusive, the same
    substrate every other trial uses.
    """
    panel = load_panel(years=years,
                       univ_path=PIT / "crsp_pit_monthly_v1.parquet")
    mkt = panel.ret.mean(axis=1)          # EW market daily return
    g = mkt.groupby(mkt.index.to_period("M"))
    rv = g.std(ddof=1) * np.sqrt(252)
    return rv.dropna()


def regimes_from(series: pd.Series, k: int = K) -> pd.Series:
    """CONTEMPORANEOUS quantile bucket — the oracle's private knowledge."""
    return pd.Series(pd.qcut(series, k, labels=False),
                     index=series.index, dtype=float)


def transition_matrix(lab: np.ndarray, k: int) -> np.ndarray:
    t = np.zeros((k, k))
    for a, b in zip(lab[:-1], lab[1:]):
        t[int(a), int(b)] += 1
    rs = t.sum(axis=1, keepdims=True)
    rs[rs == 0] = 1.0
    return t / rs


def simulate_labels(tm: np.ndarray, n: int, rng, start: int) -> np.ndarray:
    k = tm.shape[0]
    out = np.empty(n, dtype=int)
    s = start
    for i in range(n):
        out[i] = s
        s = rng.choice(k, p=tm[s])
    return out


def policy_choices(R: np.ndarray, lab: np.ndarray,
                   loo: bool = False) -> np.ndarray:
    """Which factor index the policy holds each month (for cost accounting)."""
    T, N = R.shape
    ch = np.full(T, -1, dtype=int)
    for s in np.unique(lab):
        idx = np.where(lab == s)[0]
        if len(idx) == 0:
            continue
        sub = R[idx]
        if not loo:
            ch[idx] = int(np.nanargmax(np.nanmean(sub, axis=0)))
        else:
            tot = np.nansum(sub, axis=0)
            cnt = np.sum(~np.isnan(sub), axis=0)
            for r, t in enumerate(idx):
                row = sub[r]
                den = cnt - (~np.isnan(row)).astype(int)
                den = np.where(den <= 0, np.nan, den)
                with np.errstate(invalid="ignore"):
                    ch[t] = int(np.nanargmax((tot - np.nan_to_num(row))
                                             / den))
    return ch


def switch_drag(ch: np.ndarray) -> float:
    """Annualised cost of the switches this choice path implies."""
    n_sw = int((ch[1:] != ch[:-1]).sum())
    return n_sw * SWITCH_COST / (len(ch) / 12.0)


def policy_returns(R: np.ndarray, lab: np.ndarray,
                   loo: bool = False) -> np.ndarray:
    """Regime-conditional best-factor policy.

    R is (T x N) factor returns; lab is (T,) regime labels.
    """
    T, N = R.shape
    out = np.empty(T)
    for s in np.unique(lab):
        idx = np.where(lab == s)[0]
        if len(idx) == 0:
            continue
        sub = R[idx]
        if not loo:
            j = int(np.nanargmax(np.nanmean(sub, axis=0)))
            out[idx] = sub[:, j]
        else:
            tot = np.nansum(sub, axis=0)
            cnt = np.sum(~np.isnan(sub), axis=0)
            for r, t in enumerate(idx):
                row = sub[r]
                num = tot - np.nan_to_num(row)
                den = cnt - (~np.isnan(row)).astype(int)
                den = np.where(den <= 0, np.nan, den)
                with np.errstate(invalid="ignore"):
                    j = int(np.nanargmax(num / den))
                out[t] = row[j]
    return out


def ann(x: np.ndarray) -> float:
    x = x[~np.isnan(x)]
    return float(np.nanmean(x) * 12)


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=K)
    ap.add_argument("--n-null", type=int, default=N_NULL)
    a = ap.parse_args()

    print("loading factor zoo + market state...")
    F = factor_matrix()
    rv = market_state()
    ix = F.index.intersection(rv.index)
    F, rv = F.loc[ix], rv.loc[ix]
    # factors present for the whole window — a zoo with holes would let
    # the oracle pick a factor that simply did not exist in a regime
    F = F.loc[:, F.notna().all(axis=0)]
    R = F.to_numpy(float)
    lab = regimes_from(rv, a.k).to_numpy()
    ok = ~np.isnan(lab)
    R, lab = R[ok], lab[ok].astype(int)
    print(f"zoo {R.shape[1]} factors x {R.shape[0]} months "
          f"({ix.min()}..{ix.max()}), k={a.k}")

    static_j = int(np.nanargmax(np.nanmean(R, axis=0)))
    static = R[:, static_j]
    oracle = policy_returns(R, lab)
    oracle_loo = policy_returns(R, lab, loo=True)
    drag = switch_drag(policy_choices(R, lab))
    drag_loo = switch_drag(policy_choices(R, lab, loo=True))

    g_or = ann(oracle) - ann(static)
    g_loo = ann(oracle_loo) - ann(static)
    g_or_net = g_or - drag
    g_loo_net = g_loo - drag_loo

    tm = transition_matrix(lab, a.k)
    rng = np.random.default_rng(SEED)
    null_or, null_loo = [], []
    for i in range(a.n_null):
        nl = simulate_labels(tm, len(lab), rng, start=int(lab[0]))
        if len(np.unique(nl)) < 2:
            continue
        null_or.append(ann(policy_returns(R, nl)) - ann(static)
                       - switch_drag(policy_choices(R, nl)))
        null_loo.append(ann(policy_returns(R, nl, loo=True)) - ann(static)
                        - switch_drag(policy_choices(R, nl, loo=True)))
        if (i + 1) % 100 == 0:
            print(f"  null {i + 1}/{a.n_null}")
    null_or = np.array(null_or)
    null_loo = np.array(null_loo)

    p95_or = float(np.percentile(null_or, 95))
    p95_loo = float(np.percentile(null_loo, 95))
    p_or = float((null_or >= g_or_net).mean())
    p_loo = float((null_loo >= g_loo_net).mean())

    # The ceiling that matters is what survives BOTH the selection null
    # and the economic bar. Statistical presence with a 0.2%/yr margin
    # cannot fund a predictor that will be imperfect and pay costs.
    excess = g_loo_net - p95_loo
    if excess <= 0:
        verdict = "CEILING_INDISTINGUISHABLE_FROM_SELECTION_NOISE"
    elif excess < ECON_BAR:
        verdict = "CEILING_STATISTICALLY_PRESENT_BUT_ECONOMICALLY_NEGLIGIBLE"
    else:
        verdict = "CEILING_REAL"

    res = {
        "trial": "REGIME-ORACLE-CEILING-1", "mode": "SCREEN",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "zoo": {"n_factors": int(R.shape[1]), "n_months": int(R.shape[0]),
                "start": str(ix.min()), "end": str(ix.max()),
                "source": "JKP usa_all_factors_monthly_vw_cap"},
        "k_regimes": a.k, "n_null": int(len(null_or)),
        "regime_definition": "contemporaneous quartile of realized "
                             "EW-market volatility (CRSP PIT daily panel)",
        "static_best_factor": str(F.columns[static_j]),
        "ann_return": {"static": round(ann(static), 4),
                       "oracle": round(ann(oracle), 4),
                       "oracle_loo": round(ann(oracle_loo), 4)},
        "switch_cost_per_switch": SWITCH_COST,
        "switch_drag_annual": {"oracle": round(drag, 4),
                               "oracle_loo": round(drag_loo, 4)},
        "gap_vs_static_gross": {"oracle": round(g_or, 4),
                                "oracle_loo": round(g_loo, 4)},
        "gap_vs_static": {"oracle": round(g_or_net, 4),
                          "oracle_loo": round(g_loo_net, 4)},
        "economic_bar": ECON_BAR,
        "null_gap": {"oracle_mean": round(float(null_or.mean()), 4),
                     "oracle_p95": round(p95_or, 4),
                     "oracle_loo_mean": round(float(null_loo.mean()), 4),
                     "oracle_loo_p95": round(p95_loo, 4)},
        "p_value_vs_null": {"oracle": round(p_or, 4),
                            "oracle_loo": round(p_loo, 4)},
        "excess_over_null_p95": {
            "oracle": round(g_or_net - p95_or, 4),
            "oracle_loo": round(g_loo_net - p95_loo, 4)},
        "verdict": verdict,
        "decision_rule": "if the LOO oracle gap does not exceed the "
                         "matched-transition null's 95th percentile, "
                         "perfect state knowledge buys nothing this zoo "
                         "can use, and REGIME-CONDITIONAL-RETURN-1 does "
                         "not justify a predictor on this strategy set",
        "scope_limits": [
            "gross of the switching cost a regime-conditional policy "
            "would actually pay — a CEILING, deliberately generous",
            "regime defined on market volatility only; a different state "
            "variable is a different (unasked) question",
            "the zoo is JKP long-short factors, not the mega-sweep books",
        ]}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "regime_oracle_ceiling_1_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(f"\nstatic best factor: {res['static_best_factor']} "
          f"({ann(static):+.2%}/yr)")
    print(f"oracle      gross gap {g_or:+.2%}  switch drag {drag:.2%}  "
          f"NET gap {g_or_net:+.2%}  null p95 {p95_or:+.2%}  p={p_or:.3f}")
    print(f"oracle_loo  gross gap {g_loo:+.2%}  switch drag {drag_loo:.2%}  "
          f"NET gap {g_loo_net:+.2%}  null p95 {p95_loo:+.2%}  "
          f"p={p_loo:.3f}")
    print(f"\nEXCESS over selection null (the real ceiling): "
          f"{g_loo_net - p95_loo:+.2%}/yr   economic bar {ECON_BAR:.1%}")
    print(f"\nVERDICT: {verdict}")
    print(f"receipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
