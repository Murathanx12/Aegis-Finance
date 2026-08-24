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

ROUND 2 — GRAPH-BACKBONE-2, DECLARED 2026-08-24 AFTER ROUND 1, BEFORE ITS NUMBERS
=================================================================================
Round 1 returned DEGENERATE for all four arms under the declared rule, and the
way it failed is worth more than the verdict:

    null-model expected binary density   0.958
    observed binary density              1.000
    firm pool                            94
    median firms per name                17
    median EXPECTED overlap under null   3.43 shared brokers

So `min_shared=1` — the licensed parameter — admits pairs whose overlap is
BELOW what random coverage predicts. The 100% density that sank the mechanism
is 95.8% predicted by chance; it was a fact about the threshold, not about the
data. And the `min_shared` sweep's correlation starts moving at 3-4, which is
exactly where it crosses the null expectation.

That also says what a TRANSPORTABLE version of the mechanism looks like. "At
least one shared broker" means something different in a universe with 4
covering firms than in one with 17; "more shared brokers than the null
predicts" means the same thing in both. Expressing the edge rule against the
null is not a new parameter — it removes one.

TWO CORRECTIONS TO ROUND 1, both against ROUND 1'S INSTRUMENT, not its bars:

  (i) GATE 2 WAS MIS-SPECIFIED FOR BINARY ARMS. n_eff = (sum w)^2 / sum w^2
      equals the DEGREE when every weight is 1, so for A0 and A2 gate 2 was
      re-asking gate "density" under another name and could never test what it
      was written to test. Round 2 measures n_eff against the same construction
      applied to a degree-preserving RANDOMISED coverage — "does this
      neighbourhood discriminate MORE than chance", which is the question the
      SVN already asks about edges, asked about weights.
      Declared bar: n_eff_observed <= 0.80 * n_eff_null.
  (ii) The corr bar and the rankable bar are UNCHANGED and are not re-derived
      here. The corr bar is borrowed from `assert_graph_informative` precisely
      so it cannot be tuned by whoever wants an answer; A2 cleared it
      (-0.1976) at 100% coverage, which is the fact round 2 is following up.

TWO NEW ARMS, declared with their reasons before running:

  A4  peer_sig       edge weight = -log10(p) from the same hypergeometric test
                     the SVN thresholds. A2 threw away the magnitude of the
                     evidence and kept only whether it cleared q; if the
                     mechanism is "co-coverage carries information in
                     proportion to how unusual it is", the magnitude is the
                     mechanism and binarising it is the lossy step.
  A5  peer_jaccard   w_ij = |shared| / |union|. Scale-free by construction, so
                     a broad-coverage firm cannot dominate merely by being
                     broad. This is the normalisation the co-coverage
                     literature reaches for first and round 1 skipped it.

Round 2 is still STRUCTURE ONLY. No IC, no forward return, no claim.

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
NEFF_BAR = 0.5           # round 1: fraction of (n-1). MIS-SPECIFIED for
                         # binary arms, where n_eff IS the degree. Kept so
                         # round 1 stays reproducible.
NEFF_VS_NULL_BAR = 0.80  # round 2: n_eff must beat the null graph's by this
N_NULL_DRAWS = 10        # ensemble, so the comparison has an sd
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
                   "newest": row.newest_action, "stale_days": row.stale_days,
                   "detail": row.detail}
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


def _pair_arrays(cov, shared):
    """(pairs, k, Ka, Kb) for every unordered pair, once, for vectorised tails."""
    names = sorted(cov)
    pairs, ks, kas, kbs = [], [], [], []
    for i, a in enumerate(names):
        Ka = len(cov[a])
        for b in names[i + 1:]:
            pairs.append((a, b))
            ks.append(shared[a].get(b, 0))
            kas.append(Ka)
            kbs.append(len(cov[b]))
    return pairs, np.asarray(ks), np.asarray(kas), np.asarray(kbs)


def _upper_tail(ks, kas, kbs, N):
    """P(overlap >= k) under Hypergeometric(N, Ka, Kb), vectorised."""
    from scipy.stats import hypergeom
    p = hypergeom.sf(ks - 1, N, kas, kbs)
    return np.where(ks > 0, p, 1.0)


def svn_edges(cov, shared, q: float = FDR_Q) -> tuple[set[tuple[str, str]], dict]:
    """Hypergeometric backbone, BH-FDR corrected over all tested pairs.

    Null: firm i drew K_i of the N firms in the pool at random, likewise j.
    P(overlap >= k) is the upper tail of Hypergeometric(N, K_i, K_j). An edge
    survives when the observed overlap is larger than chance at q.
    """
    N = len(firm_degree(cov))
    pairs, ks, kas, kbs = _pair_arrays(cov, shared)
    pv = _upper_tail(ks, kas, kbs, N)
    order = np.argsort(pv)
    m = len(pv)
    thresh = q * (np.arange(1, m + 1) / m)
    passing = pv[order] <= thresh
    n_sig = int(np.max(np.nonzero(passing)[0]) + 1) if passing.any() else 0
    keep = {pairs[i] for i in order[:n_sig]}
    return keep, {"n_pairs_tested": m, "n_edges_kept": n_sig,
                  "n_firm_pool": N,
                  "expected_overlap_median": float(np.median(kas * kbs / N)),
                  "fdr_q": q}


def pair_pvalues(cov, shared) -> dict[str, dict[str, float]]:
    """Upper-tail hypergeometric p for every pair, kept as a magnitude."""
    N = len(firm_degree(cov))
    pairs, ks, kas, kbs = _pair_arrays(cov, shared)
    pv = _upper_tail(ks, kas, kbs, N)
    out: dict[str, dict[str, float]] = {t: {} for t in cov}
    for (a, b), k, p in zip(pairs, ks, pv):
        if k <= 0:
            continue
        out[a][b] = float(p)
        out[b][a] = float(p)
    return out


def sig_weights(pvals) -> dict[str, dict[str, float]]:
    """w = -log10(p), floored at 0. An edge no more likely than chance gets
    weight 0 rather than a small positive one: p=1 means "exactly what the null
    predicts", and that is an absence of evidence, not weak evidence."""
    out: dict[str, dict[str, float]] = {}
    for a, nb in pvals.items():
        out[a] = {}
        for b, p in nb.items():
            w = -math.log10(max(p, 1e-300))
            if w > 0:
                out[a][b] = w
    return out


def jaccard_weights(cov, shared) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {t: {} for t in cov}
    for a, nb in shared.items():
        for b, k in nb.items():
            union = len(cov[a] | cov[b])
            if union:
                out[a][b] = k / union
    return out


def randomised_coverage(cov, rng) -> dict[str, frozenset[str]]:
    """A degree-preserving null: every name keeps its number of covering firms,
    every firm keeps its number of names, and who covers whom is shuffled.

    Implemented as a double-edge swap on the bipartite graph, which preserves
    BOTH degree sequences — reshuffling firm labels would preserve only one and
    would make the null easier to beat than it should be.
    """
    sets = {t: set(firms) for t, firms in cov.items()}
    edges = [(t, f) for t, firms in sets.items() for f in firms]
    n = len(edges)
    for _ in range(10 * n):
        i, j = int(rng.integers(0, n)), int(rng.integers(0, n))
        if i == j:
            continue
        (t1, f1), (t2, f2) = edges[i], edges[j]
        if t1 == t2 or f1 == f2:
            continue
        if f2 in sets[t1] or f1 in sets[t2]:
            continue                      # would duplicate an existing pair
        sets[t1].discard(f1); sets[t1].add(f2)
        sets[t2].discard(f2); sets[t2].add(f1)
        edges[i], edges[j] = (t1, f2), (t2, f1)
    return {t: frozenset(v) for t, v in sets.items()}


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

    pvals = pair_pvalues(cov, shared)
    sig = sig_weights(pvals)
    jac = jaccard_weights(cov, shared)

    arms = {"A0_peer_eq": binary, "A1_peer_idf": idf,
            "A2_peer_svn": svn, "A3_peer_svn_idf": svn_idf,
            "A4_peer_sig": sig, "A5_peer_jaccard": jac}

    # ROUND 2's gate 2: the same constructions on a DEGREE-PRESERVING NULL,
    # over an ENSEMBLE. One draw would give "162.00 vs 164.00" with no way to
    # know whether two is a lot -- the failure mode this programme keeps
    # catching itself on ("quote the cost rate or don't quote the count").
    print(f"building {N_NULL_DRAWS} degree-preserving null graphs ...")
    null_samples: dict[str, list[float]] = {a: [] for a in
                                            ("A0_peer_eq", "A1_peer_idf",
                                             "A2_peer_svn", "A3_peer_svn_idf",
                                             "A4_peer_sig", "A5_peer_jaccard")}
    for d in range(N_NULL_DRAWS):
        ncov = randomised_coverage(cov, np.random.default_rng(SEED + 1 + d))
        nsh = shared_counts(ncov)
        ndeg = firm_degree(ncov)
        nkeep, _ = svn_edges(ncov, nsh)
        nidf = idf_weights(ncov, nsh, ndeg)
        nsvn: dict[str, dict[str, float]] = {t: {} for t in names}
        for a, b in nkeep:
            nsvn[a][b] = 1.0
            nsvn[b][a] = 1.0
        npv = pair_pvalues(ncov, nsh)
        draw = {
            "A0_peer_eq": {t: {p: 1.0 for p in nsh[t]} for t in names},
            "A1_peer_idf": nidf,
            "A2_peer_svn": nsvn,
            "A3_peer_svn_idf": {t: {p: nidf[t][p] for p in nsvn[t]
                                    if p in nidf[t]} for t in names},
            "A4_peer_sig": sig_weights(npv),
            "A5_peer_jaccard": jaccard_weights(ncov, nsh),
        }
        for arm, w in draw.items():
            vals = [v for v in n_eff(w).values() if v > 0]
            null_samples[arm].append(float(np.median(vals)) if vals else 0.0)
        print(f"  null draw {d + 1}/{N_NULL_DRAWS}")
    null_neff = {a: float(np.mean(v)) for a, v in null_samples.items()}
    null_neff_sd = {a: float(np.std(v, ddof=1)) if len(v) > 1 else 0.0
                    for a, v in null_samples.items()}

    results = {}
    for arm, w in arms.items():
        ne = n_eff(w)
        ranked = [t for t in names if any(v > 0 for v in w[t].values())]
        density = sum(1 for t in names for p, v in w[t].items() if v > 0) / (
            n * (n - 1)) if n > 1 else 0.0
        corr, sd = degeneracy(w, names, np.random.default_rng(SEED))
        med_neff = float(np.median([ne[t] for t in ranked])) if ranked else 0.0
        rank_frac = len(ranked) / n
        nn = null_neff.get(arm, 0.0)
        gate_neff_null = bool(nn > 0 and med_neff <= NEFF_VS_NULL_BAR * nn)
        viable = (abs(corr) <= CORR_BAR
                  and gate_neff_null
                  and rank_frac >= RANKABLE_BAR)
        results[arm] = {
            "edge_density": round(density, 4),
            "corr_with_own_return": round(corr, 4),
            "corr_sd": round(sd, 4),
            "median_n_eff": round(med_neff, 2),
            "median_n_eff_under_null_mean": round(nn, 2),
            "median_n_eff_under_null_sd": round(null_neff_sd.get(arm, 0.0), 3),
            "z_vs_null": (round((med_neff - nn) / null_neff_sd[arm], 2)
                          if null_neff_sd.get(arm) else None),
            "n_eff_bar_round1_MISSPECIFIED": round(NEFF_BAR * (n - 1), 2),
            "n_eff_bar_round2_vs_null": round(NEFF_VS_NULL_BAR * nn, 2),
            "pct_universe_rankable": round(rank_frac, 4),
            "gate_corr": bool(abs(corr) <= CORR_BAR),
            "gate_n_eff_round1": bool(med_neff <= NEFF_BAR * (n - 1)),
            "gate_n_eff_vs_null_round2": gate_neff_null,
            "gate_rankable": bool(rank_frac >= RANKABLE_BAR),
            "verdict": "STRUCTURALLY_VIABLE" if viable else "DEGENERATE",
        }
        print(f"{arm:16s} density {density:6.4f}  corr {corr:+.4f}  "
              f"n_eff {med_neff:7.2f} vs null {nn:7.2f}"
              f"+-{null_neff_sd.get(arm, 0.0):.2f}  "
              f"ranked {rank_frac:5.1%}  {results[arm]['verdict']}")

    receipt = {
        "measurement_id": "GRAPH-BACKBONE-1 + GRAPH-BACKBONE-2",
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
                 "n_eff_vs_null_round2": NEFF_VS_NULL_BAR,
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
