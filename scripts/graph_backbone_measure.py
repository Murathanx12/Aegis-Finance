"""GRAPH-BACKBONE-1 — is the co-coverage graph degenerate, or is it UNWEIGHTED?

DECLARED BEFORE THE NUMBERS EXIST. This file is the declaration; the arms, the
bar and the decision rule below were written and committed before a single
coverage row was fetched.

THE OBJECTION TO THE STANDING VERDICT
=====================================
`GRAPH-PROPAGATION-DENSITY-1` measured the live graph at 100.0% density with
corr(peer_eq, own_ret) = -1.0000 and concluded the universe cannot supply a
graph. The algebra it rests on is right:

    complete graph + UNIFORM weights  =>  peer_i = (S - r_i)/(n-1)

but read the antecedent. That identity needs BOTH conjuncts, and it holds for
any n and any density -- what forces corr to -1 is not that the graph is dense,
it is that **every name's neighbourhood is identical**, so the only thing that
distinguishes peer_i across i is the subtraction of r_i. A 100%-dense graph
whose EDGE WEIGHTS differ gives every name a different weighted neighbourhood
and is under no such constraint.

The verdict swept `min_shared` -- which changes WHICH edges exist -- and never
varied what an edge is WORTH. Those are different objects.

AND THERE IS A SHARPER VERSION OF THE OBJECTION
===============================================
With ~17 covering firms per name drawn from a pool of ~N firms, two names
sharing at least one broker is what RANDOMNESS predicts, by the birthday
argument. If the null model also produces ~100% density, then 100% density is
evidence about the null, not about the data, and "the data cannot supply a
graph" is a statement about `min_shared=1` rather than about coverage.

The instrument for that is standard and predates us: a statistically validated
network (Tumminello et al. 2011, *Statistically Validated Networks in Bipartite
Complex Systems*) keeps the pair (i,j) when its observed overlap is larger than
a degree-preserving hypergeometric null predicts, at a DECLARED significance
level. The threshold is a false-discovery rate fixed in advance, not a density
knob turned until the correlation goes away -- which is precisely the objection
the density finding raised against sparsifying, and it is a fair objection to
`min_shared` and not to this.

THE ARMS
========
  A0  peer_eq        binary edges, equal-weighted mean.  THE CONTROL.
                     The licensed version. Expected to reproduce corr ~ -1.
  A1  peer_idf       edge weight = sum over shared firms of 1/log(1+deg(f)),
                     deg(f) = how many universe names that firm covers.
                     A broker that covers everything cannot say which pairs are
                     related; a broker that covers eleven names can. Density
                     is untouched -- only what an edge is WORTH changes.
  A2  peer_svn       hypergeometric backbone at BH-FDR q<=0.01, equal-weighted
                     over surviving edges.
  A3  peer_svn_idf   A2's edge set, A1's weights. Declared now so that "which
                     of the two ingredients did the work" is answerable without
                     a second look at the data.

STAGE 1 IS STRUCTURE ONLY. Nothing here touches a forward return or computes an
IC. It asks whether the graph CAN discriminate, which is a buildability
question of the same class as the density measurement -- no pre-registration,
no claim. Returns enter only as RANDOM draws, to measure the degeneracy the way
`assert_graph_informative` already does.

THE DECISION RULE, DECLARED
===========================
An arm is STRUCTURALLY_VIABLE iff all three hold:

  1. |corr(peer_score, own return)| <= 0.25 over 200 random return draws
     -- the bar `graph_propagation.assert_graph_informative` already enforces,
     borrowed rather than invented so it cannot be tuned here;
  2. median effective peer count n_eff <= 0.5 * (n-1), where
     n_eff = (sum w)^2 / sum w^2 -- the neighbourhood must actually
     discriminate, not merely be weighted;
  3. >= 80% of the universe stays rankable -- the coverage cost that sank the
     min_shared sweep applies to this route too and is not waived for it.

If NO arm passes, the density finding's verdict stands and is now supported by
a principled instrument instead of a threshold sweep -- a stronger negative
than the one it replaces.

If an arm passes, Stage 1 licenses exactly one thing: a Stage 2 IC measurement
under its OWN declaration. Passing here is not evidence of alpha and may not be
cited as any.

USAGE
    python -m scripts.graph_backbone_measure --fetch     # cache coverage
    python -m scripts.graph_backbone_measure             # measure from cache
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "backend/data/optimus/graph_propagation"
COVERAGE_CACHE = OUT / "coverage_snapshot_2026-08-21.json"
RECEIPT = OUT / "backbone_receipt.json"

AS_OF = "2026-08-21"
N_DRAWS = 200
SEED = 20260824

CORR_BAR = 0.25          # borrowed from assert_graph_informative
NEFF_BAR = 0.5           # fraction of (n-1)
RANKABLE_BAR = 0.80
FDR_Q = 0.01


# ── data ────────────────────────────────────────────────────────────────────


def universe() -> list[str]:
    from backend.config import config
    secs = config["stock_universe"]["sector_stocks"]
    out: list[str] = []
    for v in secs.values():
        out.extend(v)
    return sorted(set(out))


def fetch_coverage() -> dict:
    """One yfinance pass, cached. The density measurement did not keep the firm
    sets, so its numbers cannot be re-derived from its own receipt -- the exact
    failure the standing rules name ('a number that decides a verdict belongs
    in a runnable committed file')."""
    from backend.services.graph_propagation import read_coverage

    rows = {}
    names = universe()
    for i, t in enumerate(names, 1):
        row = read_coverage(t, AS_OF)
        rows[t] = {"status": row.status, "firms": sorted(row.firms),
                   "newest": row.newest, "stale_days": row.stale_days,
                   "note": row.note}
        if i % 20 == 0:
            print(f"  {i}/{len(names)}")
    OUT.mkdir(parents=True, exist_ok=True)
    COVERAGE_CACHE.write_text(json.dumps(
        {"as_of": AS_OF, "n": len(rows), "rows": rows}, indent=1),
        encoding="utf-8")
    print(f"cached -> {COVERAGE_CACHE}")
    return rows


def load_coverage() -> dict[str, frozenset[str]]:
    d = json.loads(COVERAGE_CACHE.read_text(encoding="utf-8"))
    return {t: frozenset(r["firms"]) for t, r in d["rows"].items()
            if r["status"] == "OK" and r["firms"]}


# ── the graph ───────────────────────────────────────────────────────────────


def shared_counts(cov: dict[str, frozenset[str]]) -> dict[str, dict[str, int]]:
    names = sorted(cov)
    by_firm: dict[str, list[str]] = {}
    for t in names:
        for f in cov[t]:
            by_firm.setdefault(f, []).append(t)
    shared: dict[str, dict[str, int]] = {t: {} for t in names}
    for members in by_firm.values():
        if len(members) < 2:
            continue
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                shared[a][b] = shared[a].get(b, 0) + 1
                shared[b][a] = shared[b].get(a, 0) + 1
    return shared


def firm_degree(cov: dict[str, frozenset[str]]) -> dict[str, int]:
    deg: dict[str, int] = {}
    for t, firms in cov.items():
        for f in firms:
            deg[f] = deg.get(f, 0) + 1
    return deg


def idf_weights(cov, shared, deg) -> dict[str, dict[str, float]]:
    """w_ij = sum over shared firms of 1/log(1+deg(f)).

    A firm covering the whole universe contributes ~1/log(1+176) = 0.19; one
    covering eleven names contributes 1/log(12) = 0.40. The ratio is modest by
    construction -- log, not inverse -- because the claim is that broad
    coverage is LESS informative, not uninformative.
    """
    by_firm: dict[str, list[str]] = {}
    for t in cov:
        for f in cov[t]:
            by_firm.setdefault(f, []).append(t)
    w: dict[str, dict[str, float]] = {t: {} for t in cov}
    for f, members in by_firm.items():
        if len(members) < 2:
            continue
        contrib = 1.0 / math.log(1.0 + deg[f])
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                w[a][b] = w[a].get(b, 0.0) + contrib
                w[b][a] = w[b].get(a, 0.0) + contrib
    return w


def svn_edges(cov, shared, q: float = FDR_Q) -> tuple[set[tuple[str, str]], dict]:
    """Hypergeometric backbone, BH-FDR corrected over all tested pairs.

    Null: firm i drew K_i of the N firms in the pool at random, likewise j.
    P(overlap >= k) is the upper tail of Hypergeometric(N, K_i, K_j). An edge
    survives when the observed overlap is larger than chance at q.
    """
    from scipy.stats import hypergeom

    names = sorted(cov)
    N = len(firm_degree(cov))
    pairs, pvals = [], []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            k = shared[a].get(b, 0)
            Ka, Kb = len(cov[a]), len(cov[b])
            # sf(k-1) = P(X >= k)
            p = float(hypergeom.sf(k - 1, N, Ka, Kb)) if k > 0 else 1.0
            pairs.append((a, b))
            pvals.append(p)
    pv = np.asarray(pvals)
    order = np.argsort(pv)
    m = len(pv)
    thresh = q * (np.arange(1, m + 1) / m)
    passing = pv[order] <= thresh
    n_sig = int(np.max(np.nonzero(passing)[0]) + 1) if passing.any() else 0
    keep = {pairs[i] for i in order[:n_sig]}
    return keep, {"n_pairs_tested": m, "n_edges_kept": n_sig,
                  "n_firm_pool": N,
                  "expected_overlap_median": float(np.median(
                      [len(cov[a]) * len(cov[b]) / N for a, b in pairs[:5000]])),
                  "fdr_q": q}


# ── scoring ─────────────────────────────────────────────────────────────────


def score(weights: dict[str, dict[str, float]], returns: dict[str, float]
          ) -> dict[str, float]:
    out = {}
    for t, nb in weights.items():
        ws = [(p, w) for p, w in nb.items() if w > 0 and p in returns]
        if not ws:
            continue
        W = sum(w for _, w in ws)
        out[t] = sum(returns[p] * w for p, w in ws) / W
    return out


def n_eff(weights: dict[str, dict[str, float]]) -> dict[str, float]:
    out = {}
    for t, nb in weights.items():
        w = np.asarray([v for v in nb.values() if v > 0], dtype=float)
        out[t] = float(w.sum() ** 2 / (w ** 2).sum()) if w.size else 0.0
    return out


def degeneracy(weights, names, rng) -> tuple[float, float]:
    """corr(peer_score, own return) over random return draws.

    Random returns because the question is STRUCTURAL: does the map
    returns -> peer_score invert the input regardless of what the input is.
    Real returns would confound the graph's geometry with the month's factor.
    """
    cs = []
    for _ in range(N_DRAWS):
        r = {t: float(x) for t, x in zip(names, rng.normal(size=len(names)))}
        s = score(weights, r)
        common = [t for t in s if t in r]
        if len(common) < 10:
            continue
        cs.append(float(np.corrcoef([s[t] for t in common],
                                    [r[t] for t in common])[0, 1]))
    return (float(np.mean(cs)), float(np.std(cs))) if cs else (float("nan"),) * 2


# ── run ─────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    args = ap.parse_args()
    if args.fetch:
        fetch_coverage()

    cov = load_coverage()
    names = sorted(cov)
    n = len(names)
    deg = firm_degree(cov)
    shared = shared_counts(cov)
    rng = np.random.default_rng(SEED)

    binary = {t: {p: 1.0 for p in shared[t]} for t in names}
    idf = idf_weights(cov, shared, deg)
    keep, svn_meta = svn_edges(cov, shared)
    svn: dict[str, dict[str, float]] = {t: {} for t in names}
    for a, b in keep:
        svn[a][b] = 1.0
        svn[b][a] = 1.0
    svn_idf = {t: {p: idf[t][p] for p in svn[t] if p in idf[t]} for t in names}

    # what the NULL predicts for the binary graph, on the same coverage
    N = len(deg)
    from scipy.stats import hypergeom
    p_edge = [1.0 - float(hypergeom.cdf(0, N, len(cov[a]), len(cov[b])))
              for i, a in enumerate(names) for b in names[i + 1:]]
    null_density = float(np.mean(p_edge))

    arms = {"A0_peer_eq": binary, "A1_peer_idf": idf,
            "A2_peer_svn": svn, "A3_peer_svn_idf": svn_idf}

    results = {}
    for arm, w in arms.items():
        ne = n_eff(w)
        ranked = [t for t in names if any(v > 0 for v in w[t].values())]
        density = sum(1 for t in names for p, v in w[t].items() if v > 0) / (
            n * (n - 1)) if n > 1 else 0.0
        corr, sd = degeneracy(w, names, np.random.default_rng(SEED))
        med_neff = float(np.median([ne[t] for t in ranked])) if ranked else 0.0
        rank_frac = len(ranked) / n
        viable = (abs(corr) <= CORR_BAR
                  and med_neff <= NEFF_BAR * (n - 1)
                  and rank_frac >= RANKABLE_BAR)
        results[arm] = {
            "edge_density": round(density, 4),
            "corr_with_own_return": round(corr, 4),
            "corr_sd": round(sd, 4),
            "median_n_eff": round(med_neff, 2),
            "n_eff_bar": round(NEFF_BAR * (n - 1), 2),
            "pct_universe_rankable": round(rank_frac, 4),
            "gate_corr": bool(abs(corr) <= CORR_BAR),
            "gate_n_eff": bool(med_neff <= NEFF_BAR * (n - 1)),
            "gate_rankable": bool(rank_frac >= RANKABLE_BAR),
            "verdict": "STRUCTURALLY_VIABLE" if viable else "DEGENERATE",
        }
        print(f"{arm:16s} density {density:6.4f}  corr {corr:+.4f}  "
              f"n_eff {med_neff:7.2f}/{NEFF_BAR*(n-1):.0f}  "
              f"ranked {rank_frac:5.1%}  {results[arm]['verdict']}")

    receipt = {
        "measurement_id": "GRAPH-BACKBONE-1",
        "licence": "PRODUCT_EXPERIMENT (buildability, structure only — no IC, "
                   "no forward return, not evidence of alpha)",
        "as_of": AS_OF,
        "declared_in": "scripts/graph_backbone_measure.py (this file)",
        "question": ("Is the live co-coverage graph degenerate because it is "
                     "DENSE, or because it is UNWEIGHTED and thresholded at "
                     "min_shared=1?"),
        "universe": {"n_with_coverage": n, "n_firm_pool": N,
                     "median_firms_per_name": float(np.median(
                         [len(cov[t]) for t in names]))},
        "null_model": {
            "expected_binary_edge_density_under_degree_preserving_null":
                round(null_density, 4),
            "reading": ("if this is ~1.0 then 100% observed density is what "
                        "RANDOM coverage predicts, and the binary graph's "
                        "completeness is a fact about min_shared=1 rather "
                        "than about the data"),
        },
        "svn": svn_meta,
        "bars": {"corr": CORR_BAR, "n_eff_fraction_of_n_minus_1": NEFF_BAR,
                 "pct_rankable": RANKABLE_BAR, "fdr_q": FDR_Q,
                 "n_random_return_draws": N_DRAWS, "seed": SEED},
        "arms": results,
        "any_viable": any(v["verdict"] == "STRUCTURALLY_VIABLE"
                          for v in results.values()),
    }
    RECEIPT.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    print(f"\nreceipt -> {RECEIPT}")
    print(f"any arm structurally viable: {receipt['any_viable']}")


if __name__ == "__main__":
    main()
