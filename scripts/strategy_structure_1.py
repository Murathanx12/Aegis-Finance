"""STRATEGY-EFFECTIVE-DIMENSION-1 + SELECTION-OVERFIT-BATTERY-1.

Order 24 Phases 2 and 3, run against an existing book corpus so the
answers arrive before the next sweep is designed rather than after.

Two questions, neither of which "how many books did we run" answers.

**How many genuinely different strategies are in here?** Thousands of
grammar variants are not thousands of behaviours. Similarity is measured
through several independent views, because two books can correlate 0.5
on monthly returns while owning nearly the same names and breaking on
the same day:

    return       Pearson correlation of monthly net returns
    residual     correlation AFTER stripping common style factors — a
                 book that is value-in-a-costume stops looking distinct
    tail         co-crash dependence: P(both in their own worst decile)
                 normalised by the 0.10 independence baseline

Views this corpus CANNOT support are named, not silently skipped
(canon: a check that did not run is not a check that passed):
holdings overlap and per-month action/turnover correlation need
per-book holdings and turnover PATHS, and mega-sweep-1 persisted only
aggregates. That is a requirement on the next sweep, recorded here.

Reported as effective dimension, not cluster count: participation
ratio and the entropy-based effective rank (Meucci's effective number
of bets) of the correlation spectrum. If N books collapse to a handful
of behaviours, that handful is the number that matters.

**How much of the best result is selection?** BH-FDR governs a declared
hypothesis family; it says nothing about searching a zoo and admiring
the winner. Three diagnostics that do:

    matched null    demean every book (true Sharpe := 0) and block-
                    bootstrap whole ROWS, preserving cross-book
                    correlation, serial dependence and every book's own
                    volatility. The distribution of the MAX Sharpe under
                    that null is what "the prettiest noise" looks like.
    deflated Sharpe the best book's Sharpe corrected for trial count,
                    skew and kurtosis (Bailey & Lopez de Prado)
    PBO / CSCV      how often the book chosen best in-sample lands below
                    median out-of-sample, over every symmetric split

Plus a breakeven cost in bps for every book, so the corpus is
comparable in one column instead of "does it survive 10bps".

    python -m scripts.strategy_structure_1

SCREEN. Descriptive structure of a simulated corpus; no promotions.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from itertools import combinations
from math import erf, lgamma, log, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402

LF = _config.OPTIMUS_LEDGER_DIR / "lane_factory"
JKP = _config.OPTIMUS_LEDGER_DIR / "jkp"
OUT = _config.OPTIMUS_LEDGER_DIR / "structure"
SEED = 20260820

#: style factors used to residualise books. FF5+MOM analogues from the
#: JKP set; the point is not a perfect factor model but a fair chance
#: for a book to reveal itself as a known style in disguise.
STYLE = ("market_equity", "be_me", "ret_12_1", "ope_be", "at_gr1",
         "ret_1_0")
COST_BASIS_BPS = 3.0          # lane_factory_sim.COST_ONE_WAY_BPS


# ── corpus ─────────────────────────────────────────────────────────────────
def load_corpus(monthly_dir: Path, books_path: Path):
    books = [json.loads(x) for x in
             books_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    meta = {b["key"]: b for b in books}
    series = {}
    for f in sorted(monthly_dir.glob("*.json")):
        k = f.stem.replace("~", "|")
        d = json.loads(f.read_text(encoding="utf-8"))
        s = pd.Series({pd.Timestamp(int(ts), unit="ms"): v
                       for ts, v in d.items()}, dtype=float)
        series[k] = s.sort_index()
    R = pd.DataFrame(series).dropna(how="all")
    R = R.loc[:, R.notna().sum() >= 24]
    return R.dropna(), meta


def style_factors(index: pd.DatetimeIndex) -> pd.DataFrame:
    df = pd.read_csv(JKP / "usa_all_factors_monthly_vw_cap.csv")
    df["date"] = pd.to_datetime(df["date"])
    m = df[df["name"].isin(STYLE)].pivot_table(
        index="date", columns="name", values="ret")
    m = m.reindex(m.index.union(index)).sort_index()
    # align on month, not on exact day stamp
    m.index = m.index.to_period("M")
    out = m.groupby(level=0).last()
    return out.reindex(index.to_period("M")).set_index(index)


# ── similarity views ───────────────────────────────────────────────────────
def residualise(R: pd.DataFrame, F: pd.DataFrame) -> pd.DataFrame:
    F = F.dropna(axis=1, how="all")
    ok = F.notna().all(axis=1)
    X = np.column_stack([np.ones(int(ok.sum())), F[ok].to_numpy(float)])
    res = {}
    for c in R.columns:
        y = R.loc[ok, c].to_numpy(float)
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        res[c] = pd.Series(y - X @ beta, index=R.index[ok])
    return pd.DataFrame(res)


def tail_dependence(R: pd.DataFrame, q: float = 0.10) -> pd.DataFrame:
    """P(both books in their own worst decile) / q — 1.0 == independent."""
    thr = R.quantile(q)
    B = (R <= thr).to_numpy(float)
    n = len(R)
    joint = (B.T @ B) / n
    dep = joint / (q * q)          # ratio to independence
    np.fill_diagonal(dep, 1.0 / q)
    # map to a [0,1]-ish similarity: 1 == perfectly co-crashing
    sim = np.clip((dep * q - q) / (1 - q), 0, 1)
    np.fill_diagonal(sim, 1.0)
    return pd.DataFrame(sim, index=R.columns, columns=R.columns)


def eff_dimension(C: np.ndarray) -> dict:
    w = np.linalg.eigvalsh(C)
    w = np.clip(w, 0, None)
    s = w.sum()
    if s <= 0:
        return {"participation_ratio": 0.0, "effective_rank": 0.0}
    p = w / s
    pr = float((s ** 2) / float((w ** 2).sum()))
    ent = float(-(p[p > 0] * np.log(p[p > 0])).sum())
    return {"participation_ratio": round(pr, 3),
            "effective_rank": round(float(np.exp(ent)), 3),
            "top_eigval_share": round(float(p.max()), 4),
            "n_eig_for_90pct": int(np.searchsorted(
                np.cumsum(np.sort(p)[::-1]), 0.90) + 1)}


def cluster(D: np.ndarray, labels: list[str], thresholds) -> dict:
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    np.fill_diagonal(D, 0.0)
    D = (D + D.T) / 2
    Z = linkage(squareform(D, checks=False), method="average")
    out = {}
    for t in thresholds:
        lab = fcluster(Z, t=t, criterion="distance")
        out[str(t)] = {"n_clusters": int(lab.max()),
                       "sizes": sorted(np.bincount(lab)[1:].tolist(),
                                       reverse=True)[:10]}
    return out, Z


# ── selection-overfit battery ──────────────────────────────────────────────
def sharpe(x: np.ndarray) -> float:
    x = x[~np.isnan(x)]
    sd = x.std(ddof=1)
    return float(x.mean() / sd * np.sqrt(12)) if sd > 0 else 0.0


def matched_null_max_sharpe(R: pd.DataFrame, n_boot: int = 2000,
                            block: int = 6, seed: int = SEED) -> dict:
    """Best-of-N Sharpe when every book's true edge is exactly zero.

    Demeaning sets the truth; block-bootstrapping whole ROWS keeps the
    cross-book correlation on each date and the serial dependence within
    a block, so the null zoo has the same co-movement and persistence as
    the real one and differs ONLY in having no edge.
    """
    X = (R - R.mean()).to_numpy(float)
    T, N = X.shape
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(T / block))
    maxes = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, max(T - block, 1), size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:T]
        idx = np.clip(idx, 0, T - 1)
        S = X[idx]
        sd = S.std(axis=0, ddof=1)
        sd[sd == 0] = np.nan
        maxes[b] = np.nanmax(S.mean(axis=0) / sd * np.sqrt(12))
    return {"null_max_sharpe_mean": round(float(maxes.mean()), 4),
            "null_max_sharpe_p95": round(float(np.percentile(maxes, 95)), 4),
            "null_max_sharpe_p99": round(float(np.percentile(maxes, 99)), 4),
            "_dist": maxes}


def deflated_sharpe(best: np.ndarray, all_sr: np.ndarray, T: int) -> dict:
    """Bailey & Lopez de Prado (2014): the Sharpe a selection this wide
    would produce by luck, and whether the observed one beats it."""
    sr = sharpe(best)
    sr_m = sr / np.sqrt(12)                     # to per-period units
    x = best[~np.isnan(best)]
    g3 = float(pd.Series(x).skew())
    g4 = float(pd.Series(x).kurt()) + 3.0
    n = len(all_sr)
    v = float(np.var(all_sr / np.sqrt(12), ddof=1))
    gamma = 0.5772156649
    e = 1 - gamma
    # expected max of n iid normal SRs
    z1 = _ppf(1 - 1.0 / max(n, 2))
    z2 = _ppf(1 - 1.0 / (max(n, 2) * np.e))
    sr0 = np.sqrt(v) * (e * z1 + gamma * z2)
    denom = np.sqrt(max(1e-12, 1 - g3 * sr_m + (g4 - 1) / 4 * sr_m ** 2))
    stat = (sr_m - sr0) * np.sqrt(max(T - 1, 1)) / denom
    dsr = 0.5 * (1 + erf(stat / sqrt(2)))
    return {"best_sharpe_ann": round(sr, 4),
            "n_trials": int(n),
            "expected_max_sharpe_ann_under_null": round(
                float(sr0 * np.sqrt(12)), 4),
            "skew": round(g3, 3), "kurtosis": round(g4, 3),
            "deflated_sharpe_prob": round(float(dsr), 4),
            "passes_at_0.95": bool(dsr > 0.95)}


def _ppf(p: float) -> float:
    from statistics import NormalDist
    return float(NormalDist().inv_cdf(min(max(p, 1e-12), 1 - 1e-12)))


def pbo_cscv(R: pd.DataFrame, s: int = 12, max_combos: int = 4000,
             seed: int = SEED) -> dict:
    """Probability of Backtest Overfitting via combinatorially symmetric
    cross-validation. Split the timeline into S blocks; for every way of
    choosing S/2 blocks as in-sample, take the book that wins IS and
    record its OOS rank. PBO is how often that winner lands below the
    OOS median — i.e. how often selection is anti-informative."""
    X = R.to_numpy(float)
    T, N = X.shape
    s = min(s, T // 4 * 2) or 2
    if s < 4:
        return {"error": "series too short for CSCV"}
    edges = np.linspace(0, T, s + 1).astype(int)
    blocks = [np.arange(edges[i], edges[i + 1]) for i in range(s)]
    combos = list(combinations(range(s), s // 2))
    rng = np.random.default_rng(seed)
    if len(combos) > max_combos:
        pick = rng.choice(len(combos), size=max_combos, replace=False)
        combos = [combos[i] for i in pick]
    logits, below = [], 0
    for c in combos:
        is_idx = np.concatenate([blocks[i] for i in c])
        oos_idx = np.concatenate([blocks[i] for i in range(s)
                                  if i not in c])
        sr_is = _sr_cols(X[is_idx])
        sr_oos = _sr_cols(X[oos_idx])
        j = int(np.nanargmax(sr_is))
        # relative rank of the IS winner in the OOS distribution
        r = float((np.sum(sr_oos < sr_oos[j]) + 1) / (N + 1))
        if r <= 0.5:
            below += 1
        r = min(max(r, 1e-6), 1 - 1e-6)
        logits.append(log(r / (1 - r)))
    return {"n_combinations": len(combos), "n_blocks": int(s),
            "pbo": round(below / len(combos), 4),
            "median_oos_rank_of_is_winner": round(
                float(np.median([1 / (1 + np.exp(-l)) for l in logits])), 4),
            "interpretation": "PBO is the probability that the book "
                              "selected as best in-sample performs below "
                              "median out-of-sample; 0.5 == selection "
                              "carries no information"}


def _sr_cols(A: np.ndarray) -> np.ndarray:
    sd = A.std(axis=0, ddof=1)
    sd = np.where(sd == 0, np.nan, sd)
    return A.mean(axis=0) / sd


def breakeven_bps(meta: dict, R: pd.DataFrame, baseline_key: str) -> dict:
    """The cost rate at which a book's edge over the baseline vanishes.

    One comparable column beats "survives 10bps" for the whole corpus.
    """
    if baseline_key not in meta:
        return {}
    b = meta[baseline_key]
    out = {}
    for k, m in meta.items():
        if k == baseline_key or k not in R.columns:
            continue
        d_cost = float(m.get("cost_paid_frac", 0.0)
                       - b.get("cost_paid_frac", 0.0))
        net_ex = float(m.get("total_return", 0.0)
                       - b.get("total_return", 0.0))
        gross_ex = net_ex + d_cost
        if abs(d_cost) < 1e-9:
            out[k] = None                      # no cost differential
            continue
        out[k] = round(COST_BASIS_BPS * gross_ex / d_cost, 2)
    return out


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="mega_sweep_1")
    ap.add_argument("--n-boot", type=int, default=2000)
    a = ap.parse_args()

    R, meta = load_corpus(LF / f"{a.corpus}_monthly",
                          LF / f"{a.corpus}_books.jsonl")
    print(f"corpus {a.corpus}: {R.shape[1]} books x {R.shape[0]} months "
          f"({R.index.min():%Y-%m}..{R.index.max():%Y-%m})")

    # ── views ──
    C_ret = R.corr().to_numpy(float)
    F = style_factors(R.index)
    Rres = residualise(R, F)
    C_res = Rres.corr().to_numpy(float)
    S_tail = tail_dependence(R).to_numpy(float)

    views = {"return": C_ret, "residual": C_res, "tail": S_tail}
    dims = {k: eff_dimension(v) for k, v in views.items()}
    D = np.mean([1 - C_ret, 1 - C_res, 1 - S_tail], axis=0)
    clusters, _ = cluster(D.copy(), list(R.columns), (0.2, 0.3, 0.4, 0.5))

    # stability: recompute consensus clusters on time-block bootstraps
    rng = np.random.default_rng(SEED)
    T = len(R)
    agree = []
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    base = fcluster(linkage(squareform(((D + D.T) / 2), checks=False),
                            method="average"), t=0.3, criterion="distance")
    same0 = (base[:, None] == base[None, :])
    for _ in range(40):
        idx = rng.integers(0, T, size=T)
        Rb = R.iloc[idx]
        Db = np.mean([1 - Rb.corr().to_numpy(float),
                      1 - residualise(Rb, F.iloc[idx]).corr().to_numpy(float),
                      1 - tail_dependence(Rb).to_numpy(float)], axis=0)
        Db = (Db + Db.T) / 2
        np.fill_diagonal(Db, 0.0)
        lb = fcluster(linkage(squareform(Db, checks=False),
                              method="average"), t=0.3,
                      criterion="distance")
        agree.append(float((same0 == (lb[:, None] == lb[None, :])).mean()))

    # ── selection-overfit battery ──
    sr_all = np.array([sharpe(R[c].to_numpy()) for c in R.columns])
    best_col = R.columns[int(np.nanargmax(sr_all))]
    null = matched_null_max_sharpe(R, n_boot=a.n_boot)
    null_dist = null.pop("_dist")
    obs_max = float(np.nanmax(sr_all))
    p_null = float((null_dist >= obs_max).mean())
    dsr = deflated_sharpe(R[best_col].to_numpy(), sr_all, len(R))
    pbo = pbo_cscv(R)

    base_key = next((k for k in meta if k.startswith("none|")), None)
    be = breakeven_bps(meta, R, base_key) if base_key else {}

    res = {
        "trial": "STRATEGY-EFFECTIVE-DIMENSION-1 + "
                 "SELECTION-OVERFIT-BATTERY-1",
        "mode": "SCREEN", "corpus": a.corpus,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_books": int(R.shape[1]), "n_months": int(R.shape[0]),
        "views_computed": list(views),
        "views_unavailable": {
            "holdings_overlap": "mega-sweep-1 persisted aggregate "
                                "turnover only, not per-month holdings",
            "action_turnover_correlation": "same — turnover totals are "
                                           "stored, not the path"},
        "next_sweep_requirement": "MEGA-SWEEP-2 must persist per-book "
                                  "per-month holdings and turnover or "
                                  "two of the five similarity views stay "
                                  "unanswerable",
        "effective_dimension": dims,
        "consensus_clusters_by_cut": clusters,
        "cluster_stability_pairwise_agreement": {
            "mean": round(float(np.mean(agree)), 4),
            "p05": round(float(np.percentile(agree, 5)), 4),
            "n_bootstraps": len(agree)},
        "selection_overfit": {
            "best_book": best_col,
            "observed_max_sharpe": round(obs_max, 4),
            "matched_null": null,
            "p_value_vs_matched_null": round(p_null, 4),
            "deflated_sharpe": dsr,
            "pbo_cscv": pbo},
        "breakeven_cost_bps_vs_baseline": be,
        "baseline_key": base_key,
        "label": "SIMULATION — descriptive structure, no promotions"}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"strategy_structure_1_{a.corpus}_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print("\neffective dimension (of "
          f"{R.shape[1]} books):")
    for k, v in dims.items():
        print(f"  {k:9s} participation_ratio={v['participation_ratio']:6.2f} "
              f"effective_rank={v['effective_rank']:6.2f} "
              f"top_eig_share={v['top_eigval_share']:.3f} "
              f"n_for_90%={v['n_eig_for_90pct']}")
    print("\nconsensus clusters:", {k: v["n_clusters"]
                                    for k, v in clusters.items()})
    print(f"cluster stability (pairwise agreement): "
          f"{np.mean(agree):.3f}")
    print(f"\nbest book: {best_col}  Sharpe {obs_max:.3f}")
    print(f"  matched-null max Sharpe: mean "
          f"{null['null_max_sharpe_mean']:.3f} "
          f"p95 {null['null_max_sharpe_p95']:.3f}  -> p={p_null:.4f}")
    print(f"  deflated Sharpe prob: {dsr['deflated_sharpe_prob']:.4f} "
          f"(passes@0.95: {dsr['passes_at_0.95']})")
    print(f"  PBO: {pbo.get('pbo')}")
    print(f"\nreceipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
