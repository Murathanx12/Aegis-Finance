"""FEATURE-COVERAGE-AUDIT-1 — does missing data decide the arena's ranking?

The arena composite z-scores each factor cross-sectionally and then takes the
weighted mean of *whatever factors a name happens to have*
(`multifactor.compute_multifactor_scores`, the frozen estimator). That rule is
documented. Its consequence is not:

    a name scored on ONE factor has composite variance ~1
    a name scored on SIX correlated factors has composite variance ~1/k_eff

Averaging shrinks. So the better-measured names are pushed toward the middle of
the distribution and the thinly-measured names own both tails — and a top-k
selection reads only one tail. In the live arena that asymmetry is extreme:
every one of the ~180 candidate names gets `mom_12_1`, while the five PIT
score families are collected on the ~12-name book cross-section only.

This script measures the size of the effect under a declared generative model,
and compares the current rule against a coverage-normalized one that divides
each name's weighted sum by the standard deviation implied by ITS OWN
available set. Run it, don't argue about it:

    python -m scripts.arena_coverage_audit
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from backend.services.arena.discovery import COMPOSITE_WEIGHTS

N_NAMES = 180
N_ENRICHED = 12          # names the registered collectors actually score
N_TRIALS = 4000
TOP_K = 12
SEED = 20260820

#: Correlation between any two factor views of the same latent skill. Order 24
#: measured 3–7 shared latent factors across all sources, i.e. the views are
#: strongly, not weakly, redundant.
FACTOR_RHO = 0.4


def _z(x: np.ndarray) -> np.ndarray:
    sd = x.std(ddof=1)
    return (x - x.mean()) / sd if sd > 0 else np.zeros_like(x)


def _current_rule(zs: np.ndarray, mask: np.ndarray,
                  w: np.ndarray) -> np.ndarray:
    """Weighted mean of the AVAILABLE factors — what the arena does today."""
    num = (zs * w * mask).sum(axis=1)
    den = (w * mask).sum(axis=1)
    return np.where(den > 0, num / np.where(den > 0, den, 1.0), 0.0)


def _coverage_normalized(zs: np.ndarray, mask: np.ndarray, w: np.ndarray,
                         corr: np.ndarray) -> np.ndarray:
    """Weighted SUM divided by the sd that sum has given the name's own
    available set: s = w'z / sqrt(w' C w) over the available block. Every
    name's composite then has unit variance whatever its coverage."""
    num = (zs * w * mask).sum(axis=1)
    out = np.zeros(len(zs))
    for i in range(len(zs)):
        idx = np.flatnonzero(mask[i])
        if idx.size == 0:
            continue
        wi = w[idx]
        var = float(wi @ corr[np.ix_(idx, idx)] @ wi)
        out[i] = num[i] / np.sqrt(var) if var > 0 else 0.0
    return out


def run(n_trials: int = N_TRIALS) -> dict:
    rng = np.random.default_rng(SEED)
    factors = list(COMPOSITE_WEIGHTS)
    w = np.array([COMPOSITE_WEIGHTS[f] for f in factors], dtype=float)
    k = len(factors)

    # Every name has factor 0 (price-derived momentum); only the enriched
    # subset has the PIT families.
    mask = np.zeros((N_NAMES, k), dtype=float)
    mask[:, 0] = 1.0
    mask[:N_ENRICHED, 1:] = 1.0

    corr = np.full((k, k), FACTOR_RHO)
    np.fill_diagonal(corr, 1.0)
    chol = np.linalg.cholesky(corr)

    stats = {"current": {"enriched_in_top": [], "selected_skill": []},
             "coverage_normalized": {"enriched_in_top": [], "selected_skill": []},
             "oracle": {"enriched_in_top": [], "selected_skill": []}}

    for _ in range(n_trials):
        skill = rng.standard_normal(N_NAMES)
        # each factor is a correlated noisy view of the same latent skill
        noise = rng.standard_normal((N_NAMES, k)) @ chol.T
        raw = 0.6 * skill[:, None] + 0.8 * noise
        zs = np.column_stack([_z(raw[:, j]) for j in range(k)])

        for label, score in (
                ("current", _current_rule(zs, mask, w)),
                ("coverage_normalized", _coverage_normalized(zs, mask, w, corr)),
                ("oracle", skill)):
            top = np.argsort(-score)[:TOP_K]
            stats[label]["enriched_in_top"].append(int((top < N_ENRICHED).sum()))
            stats[label]["selected_skill"].append(float(skill[top].mean()))

    expected_share = N_ENRICHED / N_NAMES * TOP_K
    out = {
        "n_trials": n_trials, "n_names": N_NAMES, "n_enriched": N_ENRICHED,
        "top_k": TOP_K, "factor_rho": FACTOR_RHO, "factors": factors,
        "weights": [float(x) for x in w],
        "enriched_share_if_coverage_were_irrelevant": round(expected_share, 3),
        "rules": {},
    }
    for label, s in stats.items():
        out["rules"][label] = {
            "mean_enriched_names_in_top_k": round(
                float(np.mean(s["enriched_in_top"])), 3),
            "mean_latent_skill_of_selection": round(
                float(np.mean(s["selected_skill"])), 4),
        }
    cur = out["rules"]["current"]["mean_latent_skill_of_selection"]
    cov = out["rules"]["coverage_normalized"]["mean_latent_skill_of_selection"]
    orc = out["rules"]["oracle"]["mean_latent_skill_of_selection"]
    out["verdict"] = {
        "selection_quality_gain_from_normalizing": round(cov - cur, 4),
        "share_of_oracle_gap_closed": (round((cov - cur) / (orc - cur), 4)
                                       if orc > cur else None),
        "reading": ("under the current rule the better-measured names are "
                    "shrunk toward the middle and are structurally scarce in "
                    "a top-k tail; the collectors feed the snapshot without "
                    "being able to reach the selection"),
    }
    return out


def coverage_value(n_trials: int = N_TRIALS) -> dict:
    """What is WIDER coverage worth, separately from how it is aggregated?

    The bias question ("are the 12 enriched names treated fairly?") and the
    coverage question ("should 168 names be ranked on momentum alone?") have
    very different answers, and conflating them is how a real defect gets
    fixed while the expensive problem stays. Three worlds, same generator:

      momentum_only   every name scored on 1 factor (what 168/180 get today)
      current_split   12 names enriched, 168 on momentum alone
      full_coverage   every name scored on all 6
    """
    rng = np.random.default_rng(SEED + 1)
    factors = list(COMPOSITE_WEIGHTS)
    w = np.array([COMPOSITE_WEIGHTS[f] for f in factors], dtype=float)
    k = len(factors)
    corr = np.full((k, k), FACTOR_RHO)
    np.fill_diagonal(corr, 1.0)
    chol = np.linalg.cholesky(corr)

    masks = {}
    m = np.zeros((N_NAMES, k)); m[:, 0] = 1.0
    masks["momentum_only"] = m
    m = np.zeros((N_NAMES, k)); m[:, 0] = 1.0; m[:N_ENRICHED, 1:] = 1.0
    masks["current_split"] = m
    masks["full_coverage"] = np.ones((N_NAMES, k))

    acc = {name: [] for name in masks}
    acc["oracle"] = []
    for _ in range(n_trials):
        skill = rng.standard_normal(N_NAMES)
        noise = rng.standard_normal((N_NAMES, k)) @ chol.T
        raw = 0.6 * skill[:, None] + 0.8 * noise
        zs = np.column_stack([_z(raw[:, j]) for j in range(k)])
        for name, mask in masks.items():
            score = _coverage_normalized(zs, mask, w, corr)
            acc[name].append(float(skill[np.argsort(-score)[:TOP_K]].mean()))
        acc["oracle"].append(float(skill[np.argsort(-skill)[:TOP_K]].mean()))

    out = {name: round(float(np.mean(v)), 4) for name, v in acc.items()}
    gap = out["oracle"] - out["momentum_only"]
    out["value_of_full_coverage"] = round(
        out["full_coverage"] - out["momentum_only"], 4)
    out["value_of_current_split"] = round(
        out["current_split"] - out["momentum_only"], 4)
    out["share_of_oracle_gap_full_coverage_closes"] = (
        round((out["full_coverage"] - out["momentum_only"]) / gap, 4)
        if gap > 0 else None)
    out["reading"] = (
        "the aggregation defect is worth a fraction of what the coverage "
        "hole is worth; enriching 12 names of 180 buys almost nothing "
        "whatever the aggregation rule, and enriching all 180 is the "
        "experiment that has a number attached")
    return out


def redundancy_sensitivity(n_trials: int = 1500) -> dict:
    """Is CHEAP coverage worth as much as DIVERSE coverage?

    The headline `value_of_full_coverage` assumes the five added factors are
    views correlated at rho=0.4. Five more PRICE-derived features (momentum
    over other windows, drawdown, 52-week state, gap, volume z) are not that:
    they are near-copies of the momentum the arena already has. Order 24
    measured 3–7 shared latent factors across ALL sources, which is exactly
    the warning that adding a feed need not add a dimension.

    So the build decision — cheap price trackers vs. buying fundamental /
    options / expectations coverage across the whole universe — turns on rho,
    and rho is the thing to put a number on before spending.
    """
    rng = np.random.default_rng(SEED + 2)
    factors = list(COMPOSITE_WEIGHTS)
    w = np.array([COMPOSITE_WEIGHTS[f] for f in factors], dtype=float)
    k = len(factors)
    thin = np.zeros((N_NAMES, k)); thin[:, 0] = 1.0
    full = np.ones((N_NAMES, k))

    out = {}
    for rho in (0.2, 0.4, 0.6, 0.75, 0.9):
        corr = np.full((k, k), rho)
        np.fill_diagonal(corr, 1.0)
        chol = np.linalg.cholesky(corr)
        a, b, orc = [], [], []
        for _ in range(n_trials):
            skill = rng.standard_normal(N_NAMES)
            noise = rng.standard_normal((N_NAMES, k)) @ chol.T
            raw = 0.6 * skill[:, None] + 0.8 * noise
            zs = np.column_stack([_z(raw[:, j]) for j in range(k)])
            a.append(float(skill[np.argsort(
                -_coverage_normalized(zs, thin, w, corr))[:TOP_K]].mean()))
            b.append(float(skill[np.argsort(
                -_coverage_normalized(zs, full, w, corr))[:TOP_K]].mean()))
            orc.append(float(skill[np.argsort(-skill)[:TOP_K]].mean()))
        gain = float(np.mean(b) - np.mean(a))
        gap = float(np.mean(orc) - np.mean(a))
        out[f"rho_{rho}"] = {
            "momentum_only": round(float(np.mean(a)), 4),
            "full_coverage": round(float(np.mean(b)), 4),
            "gain": round(gain, 4),
            "share_of_oracle_gap": round(gain / gap, 4) if gap > 0 else None,
        }
    out["reading"] = (
        "gain from widening coverage falls steeply as the added features "
        "become copies of the one already there. Price-derived trackers sit "
        "at the high-rho end; fundamentals/options/expectations sit at the "
        "low-rho end. Both widen coverage; only one buys a dimension.")
    return out


def main() -> None:
    res = run()
    res["coverage_value"] = coverage_value()
    res["redundancy_sensitivity"] = redundancy_sensitivity()
    print(json.dumps(res, indent=2))
    dest = Path("docs") / "FEATURE_COVERAGE_AUDIT_1.json"
    if dest.parent.exists():
        dest.write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
