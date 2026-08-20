"""FACTOR-STABILITY-1 — is the cross-source structure the SAME structure
over time, or does it rotate?

CROSS-SOURCE-STRUCTURE-1's headline is that 28 features from four sources
collapse to 3-7 signal factors and that **every factor is a blend of
sources**, which was offered as the explanation for why adding a source
never adds a dimension. That claim was computed on the pooled 2013-2024
panel, and a pooled spectrum can be an average of two different
structures rather than one persistent structure.

If the loadings rotate between periods, "the sources share factors" is a
statement about an average and not about the market, and it should not be
carried forward as a reason for anything.

METHOD. Split the panel into consecutive periods, compute each period's
top-k eigenvectors, and measure how aligned the SUBSPACES are — not the
individual eigenvectors, which are interchangeable under near-degenerate
eigenvalues and would show spurious instability. Principal angles between
subspaces are the right instrument:

    alignment = mean(cos^2 theta_i) over the k principal angles

    1.0  the two periods span the same k-dimensional subspace
    k'/k the subspaces share k' dimensions
    ~k/N what two RANDOM k-subspaces of R^N would score

The random baseline is the whole point: with k=7 and N=28, two arbitrary
subspaces already overlap by ~0.25 on this measure, so an alignment of
0.5 is much closer to noise than the number suggests.

Also reported: whether the SOURCE COMPOSITION of the leading factor is
stable, since that composition is what §13's claim actually rests on.

    python -m scripts.factor_stability_1

SCREEN — a robustness check on a claim this run already made.
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
from scripts.cross_source_structure_1 import build_panel     # noqa: E402

OUT = _config.OPTIMUS_LEDGER_DIR / "structure"
SEED = 20260820


def top_k(Z: pd.DataFrame, k: int) -> np.ndarray:
    C = np.corrcoef(Z.to_numpy(float), rowvar=False)
    C = np.nan_to_num(C, nan=0.0)
    np.fill_diagonal(C, 1.0)
    w, v = np.linalg.eigh(C)
    return v[:, ::-1][:, :k]


def subspace_alignment(A: np.ndarray, B: np.ndarray) -> float:
    """Mean cos^2 of the principal angles between span(A) and span(B).

    Uses singular values of A^T B, which is the standard and
    rotation-invariant way to compare subspaces — comparing eigenvectors
    one by one would report spurious instability whenever two eigenvalues
    are close, because the pair is then only defined up to a rotation.
    """
    s = np.linalg.svd(A.T @ B, compute_uv=False)
    s = np.clip(s, 0.0, 1.0)
    return float(np.mean(s ** 2))


def random_baseline(N: int, k: int, n: int = 400, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        A, _ = np.linalg.qr(rng.normal(size=(N, k)))
        B, _ = np.linalg.qr(rng.normal(size=(N, k)))
        vals.append(subspace_alignment(A, B))
    v = np.array(vals)
    return {"mean": round(float(v.mean()), 4),
            "p95": round(float(np.percentile(v, 95)), 4)}


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--era", default="modern")
    ap.add_argument("--k", type=int, default=7)
    ap.add_argument("--n-periods", type=int, default=4)
    a = ap.parse_args()

    df, src = build_panel(a.era)
    for key in list(src):
        cs = [c for c in src[key] if c in df.columns]
        if not cs or float(df[cs].notna().all(axis=1).mean()) < 0.60:
            src.pop(key, None)
    feats = [c for v in src.values() for c in v if c in df.columns]
    sub = df[["date"] + feats].replace([np.inf, -np.inf],
                                       np.nan).dropna()
    Z = sub.groupby("date")[feats].rank(pct=True) - 0.5
    Z["date"] = sub["date"].to_numpy()
    dates = np.sort(sub["date"].unique())
    edges = np.array_split(dates, a.n_periods)
    print(f"{len(feats)} features, {len(dates)} dates, "
          f"{a.n_periods} periods, k={a.k}")

    src_of = {c: kk for kk, vs in src.items() for c in vs}
    Vs, labels, comps = [], [], []
    for i, ed in enumerate(edges):
        part = Z[Z["date"].isin(ed)][feats]
        if len(part) < 500:
            continue
        V = top_k(part, a.k)
        Vs.append(V)
        labels.append(f"{pd.Timestamp(ed[0]):%Y-%m}..{pd.Timestamp(ed[-1]):%Y-%m}")
        load = pd.Series(np.abs(V[:, 0]), index=feats)
        by = load.groupby([src_of.get(c, "?") for c in feats]).sum()
        by = (by / by.sum()).sort_values(ascending=False)
        comps.append({k2: round(float(x), 3) for k2, x in by.items()})
        print(f"  {labels[-1]}: {len(part):,} rows  "
              f"factor-1 composition {comps[-1]}")

    base = random_baseline(len(feats), a.k)
    pairs = []
    for i in range(len(Vs)):
        for j in range(i + 1, len(Vs)):
            al = subspace_alignment(Vs[i], Vs[j])
            pairs.append({"a": labels[i], "b": labels[j],
                          "alignment": round(al, 4),
                          "adjacent": bool(j == i + 1)})
    al_all = np.array([p["alignment"] for p in pairs])
    adj = np.array([p["alignment"] for p in pairs if p["adjacent"]])
    far = np.array([p["alignment"] for p in pairs if not p["adjacent"]])

    excess = float(al_all.mean() - base["mean"])
    if al_all.mean() > 0.85:
        verdict = ("STABLE — the same subspace persists across periods; "
                   "the pooled spectrum describes one structure")
    elif al_all.mean() > base["p95"]:
        verdict = (f"PARTIALLY STABLE — alignment {al_all.mean():.2f} is "
                   f"above what random {a.k}-subspaces score "
                   f"({base['mean']:.2f}) but well short of 1.0: the "
                   f"pooled spectrum is a blend of related but drifting "
                   f"structures, and per-period claims are safer than "
                   f"pooled ones")
    else:
        verdict = ("UNSTABLE — alignment is not distinguishable from "
                   "random subspaces; the pooled factor structure is an "
                   "average of different structures and CROSS-SOURCE-"
                   "STRUCTURE-1's composition claim must be restated "
                   "per period")

    res = {"trial": "FACTOR-STABILITY-1", "mode": "SCREEN", "era": a.era,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "checks": "a robustness check on CROSS-SOURCE-STRUCTURE-1's "
                     "own headline, not a new claim",
           "k": a.k, "n_features": len(feats), "n_dates": int(len(dates)),
           "periods": labels,
           "factor1_source_composition_by_period": comps,
           "pairwise_alignment": pairs,
           "mean_alignment": round(float(al_all.mean()), 4),
           "adjacent_mean": round(float(adj.mean()), 4) if len(adj) else None,
           "distant_mean": round(float(far.mean()), 4) if len(far) else None,
           "random_subspace_baseline": base,
           "excess_over_random": round(excess, 4),
           "method": "mean cos^2 of principal angles (SVD of A^T B) — "
                     "subspace comparison, not eigenvector-by-"
                     "eigenvector, which would report spurious "
                     "instability under near-degenerate eigenvalues",
           "verdict": verdict}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"factor_stability_1_{a.era}_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"\npairwise subspace alignment (k={a.k}):")
    for q in pairs:
        print(f"  {q['a']} vs {q['b']}  {q['alignment']:.3f}"
              f"{'  (adjacent)' if q['adjacent'] else ''}")
    print(f"\nmean {al_all.mean():.3f}   adjacent "
          f"{adj.mean() if len(adj) else float('nan'):.3f}   distant "
          f"{far.mean() if len(far) else float('nan'):.3f}")
    print(f"random {a.k}-subspace baseline: mean {base['mean']:.3f} "
          f"p95 {base['p95']:.3f}   -> excess {excess:+.3f}")
    print(f"\nVERDICT: {verdict}")
    print(f"receipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
