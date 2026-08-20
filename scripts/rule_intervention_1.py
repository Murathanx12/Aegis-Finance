"""RULE-INTERVENTION-1 — what does each GRAMMAR DECISION do?

Order 24 Phase 4. A sweep that only ranks whole books answers "which
combination won", which is the question most contaminated by selection
and least useful for building a portfolio policy. The grammar is
factorial (signal x weighting x winner_handling x top_n), so the far
more informative question is available for free:

    holding everything else fixed, what does switching ONE decision do?

That is a matched paired contrast, not a ranking. Every pair differs in
exactly one coordinate, so the signal family, the universe, the dates
and the cost basis all cancel. The unit of evidence is the DATE BLOCK
(monthly returns overlap and the whole cross-section co-moves), so
inference is a block bootstrap over dates, never over books.

Reported per contrast:
  - paired difference in annualised return, volatility, max drawdown
  - the MDE at the panel's own effective n, so a null is readable
  - heterogeneity: the same contrast computed within each signal family,
    because "inverse-vol helps" can be an average over one family it
    helps a lot and several it hurts

    python -m scripts.rule_intervention_1

SCREEN. Descriptive structure of a simulated corpus; the corpus's
families are already spent, so nothing here is a confirmation.
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
    bootstrap_block_dates)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)
from scripts.strategy_structure_1 import load_corpus         # noqa: E402

LF = _config.OPTIMUS_LEDGER_DIR / "lane_factory"
OUT = _config.OPTIMUS_LEDGER_DIR / "structure"

#: (dimension, level_a, level_b) — the contrast is a MINUS b
CONTRASTS = [
    ("weighting", "inverse_vol", "equal"),
    ("weighting", "rank", "equal"),
    ("weighting", "rank", "inverse_vol"),
    ("winner_handling", "exempt", "trim"),
    ("top_n", "50", "100"),
]
FIELDS = ("signal", "weighting", "winner_handling", "top_n")


def parse_key(k: str) -> dict:
    parts = k.split("|")
    return dict(zip(FIELDS, parts))


def matched_pairs(keys, dim: str, a: str, b: str):
    """Keys identical on every coordinate except `dim`."""
    idx = {}
    for k in keys:
        d = parse_key(k)
        if d.get(dim) not in (a, b):
            continue
        rest = tuple(d[f] for f in FIELDS if f != dim)
        idx.setdefault(rest, {})[d[dim]] = k
    return [(v[a], v[b], rest) for rest, v in idx.items()
            if a in v and b in v]


def ann_ret(s: pd.Series) -> float:
    return float(s.mean() * 12)


def ann_vol(s: pd.Series) -> float:
    return float(s.std(ddof=1) * np.sqrt(12))


def max_dd(s: pd.Series) -> float:
    c = (1 + s).cumprod()
    return float((c / c.cummax() - 1).min())


def block_boot_stat(A: pd.DataFrame, B: pd.DataFrame, stat, blk: int,
                    n_boot: int = 2000, seed: int = 20260820) -> dict:
    """Interval on `stat(A) - stat(B)` by resampling DATE BLOCKS.

    Volatility is not a per-date mean, so contrasting mean(r^2) to test
    it is both indirect and badly powered — squared returns are heavy
    tailed and the interval is dominated by a handful of months. Here the
    STATISTIC itself is recomputed on each resampled path, which is the
    right bootstrap for a path functional and is far better powered.
    A and B are aligned per-pair frames; the statistic is applied to the
    pair-averaged series so each date still contributes once.
    """
    a = A.to_numpy(float)
    b = B.to_numpy(float)
    T = a.shape[0]
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(T / max(blk, 1)))
    obs = stat(a) - stat(b)
    draws = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, max(T - blk, 1), size=n_blocks)
        idx = np.concatenate([np.arange(s, s + blk) for s in starts])[:T]
        idx = np.clip(idx, 0, T - 1)
        draws[i] = stat(a[idx]) - stat(b[idx])
    se = float(draws.std(ddof=1))
    lo, hi = (float(np.percentile(draws, 2.5)),
              float(np.percentile(draws, 97.5)))
    # Two different questions, routinely conflated:
    #  - SIGNIFICANT: the interval excludes zero (|effect| ~ 1.96 SE)
    #  - POWERED:     the effect is at least the size this design has 80%
    #                 power to detect (|effect| >= 2.802 SE)
    # An effect can be significant and still sit below the MDE, which
    # means a replication would find it only about half the time. Both
    # get reported; collapsing them into one "ns" is the error.
    return {"observed": float(obs), "se": se, "ci": [lo, hi],
            "mde_80": float(2.802 * se),
            "significant_ci_excludes_zero": bool(lo > 0 or hi < 0),
            "clears_mde": bool(abs(obs) >= 2.802 * se)}


def _vol_of(x: np.ndarray) -> float:
    return float(np.nanmean(x, axis=1).std(ddof=1) * np.sqrt(12))


def _maxdd_of(x: np.ndarray) -> float:
    c = np.cumprod(1 + np.nanmean(x, axis=1))
    return float((c / np.maximum.accumulate(c) - 1).min())


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="mega_sweep_1")
    a = ap.parse_args()

    R, meta = load_corpus(LF / f"{a.corpus}_monthly",
                          LF / f"{a.corpus}_books.jsonl")
    keys = list(R.columns)
    dates = np.array(R.index.values, dtype="datetime64[D]")
    blk = bootstrap_block_dates(dates, 21)
    print(f"corpus {a.corpus}: {len(keys)} books x {len(R)} months, "
          f"bootstrap block = {blk} dates")

    results = {}
    for dim, la, lb in CONTRASTS:
        pairs = matched_pairs(keys, dim, la, lb)
        if not pairs:
            continue
        # pooled paired difference series: average across matched pairs
        # at each date, so each DATE contributes once
        D = pd.DataFrame({f"{x}__{y}": R[x] - R[y] for x, y, _ in pairs})
        pooled = D.mean(axis=1)
        inf = block_bootstrap_paired(pooled.to_numpy(float), dates,
                                     block_days=blk,
                                     seed=20260820).as_dict()
        # RISK inference. The return contrast above is a per-date mean and
        # bootstraps directly; volatility is not a mean, so contrast the
        # squared returns instead — mean(r_x^2 - r_y^2) IS a per-date mean
        # and gives a proper interval on the VARIANCE difference. Without
        # this the risk claim would be eyeballed off level differences,
        # and an unreachable verdict is not a verdict.
        A = R[[x for x, _, _ in pairs]]
        B = R[[y for _, y, _ in pairs]]
        vol_inf = block_boot_stat(A, B, _vol_of, blk)
        dd_inf = block_boot_stat(A, B, _maxdd_of, blk)

        # level metrics
        ra = np.mean([ann_ret(R[x]) for x, _, _ in pairs])
        rb = np.mean([ann_ret(R[y]) for _, y, _ in pairs])
        va = np.mean([ann_vol(R[x]) for x, _, _ in pairs])
        vb = np.mean([ann_vol(R[y]) for _, y, _ in pairs])
        da = np.mean([max_dd(R[x]) for x, _, _ in pairs])
        db = np.mean([max_dd(R[y]) for _, y, _ in pairs])

        # heterogeneity by signal family
        het = {}
        for x, y, rest in pairs:
            sig = parse_key(x)["signal"]
            het.setdefault(sig, []).append(ann_ret(R[x]) - ann_ret(R[y]))
        het = {k: round(float(np.mean(v)), 4) for k, v in het.items()}

        name = f"{dim}: {la} - {lb}"
        d_ann = float(inf["mean"] * 12)
        mde_ann = float(inf["mde_80pct_power"] * 12)
        results[name] = {
            "n_matched_pairs": len(pairs),
            "d_ann_return": round(d_ann, 4),
            "mde_80_ann": round(mde_ann, 4),
            "clears_mde": bool(abs(d_ann) >= mde_ann),
            "ci_ann": [round(inf["ci_lo"] * 12, 4),
                       round(inf["ci_hi"] * 12, 4)],
            "return_significant": bool(inf["ci_lo"] > 0
                                       or inf["ci_hi"] < 0),
            "n_effective_date_blocks": inf["n_effective"],
            "d_ann_vol": round(vol_inf["observed"], 4),
            "mde_80_ann_vol": round(vol_inf["mde_80"], 4),
            "vol_significant": vol_inf["significant_ci_excludes_zero"],
            "vol_clears_mde": vol_inf["clears_mde"],
            "ci_ann_vol": [round(c, 4) for c in vol_inf["ci"]],
            "d_max_drawdown": round(dd_inf["observed"], 4),
            "mde_80_max_drawdown": round(dd_inf["mde_80"], 4),
            "maxdd_significant": dd_inf["significant_ci_excludes_zero"],
            "maxdd_clears_mde": dd_inf["clears_mde"],
            "ci_max_drawdown": [round(c, 4) for c in dd_inf["ci"]],
            "_risk_inference_note": "vol and maxDD are PATH statistics; "
                                    "the statistic itself is recomputed on "
                                    "each date-block resample rather than "
                                    "testing mean(r^2), which is heavy-"
                                    "tailed and badly powered",
            "level_ann_return": {la: round(float(ra), 4),
                                 lb: round(float(rb), 4)},
            "level_ann_vol": {la: round(float(va), 4),
                              lb: round(float(vb), 4)},
            "level_max_dd": {la: round(float(da), 4),
                             lb: round(float(db), 4)},
            "heterogeneity_by_signal_d_ann_return": dict(
                sorted(het.items(), key=lambda kv: kv[1])),
            "n_signals_positive": int(sum(1 for v in het.values() if v > 0)),
            "n_signals": len(het)}

    res = {"trial": "RULE-INTERVENTION-1", "mode": "SCREEN",
           "corpus": a.corpus,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "unit_of_evidence": "date block (monthly outcomes overlap and "
                               "the cross-section co-moves); never the "
                               "book, never the book-month row",
           "n_books": len(keys), "n_months": int(len(R)),
           "contrasts": results,
           "label": "SIMULATION — LANE-FACTORY-SIM-1, never a track record"}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"rule_intervention_1_{a.corpus}_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"\n{'contrast':34s} {'dRet/yr':>9s} {'retMDE':>8s} {'ret?':>7s} "
          f"{'dVol':>8s} {'var?':>7s} {"dMaxDD":>8s} {"dd?":>7s}")
    for k, v in results.items():
        def tag(sig, pw):
            return "POWERED" if pw else ("sig" if sig else "ns")
        print(f"{k:34s} {v['d_ann_return']:>+9.2%} {v['mde_80_ann']:>8.2%} "
              f"{tag(v['return_significant'], v['clears_mde']):>8s} "
              f"{v['d_ann_vol']:>+8.2%} "
              f"{tag(v['vol_significant'], v['vol_clears_mde']):>8s} "
              f"{v['d_max_drawdown']:>+8.2%} "
              f"{tag(v['maxdd_significant'], v['maxdd_clears_mde']):>8s}")
    print(f"\nreceipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
