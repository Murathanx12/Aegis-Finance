"""RELIABILITY_ROUTER_v1: the first layer that LEARNS from the graded ledger.

The reliability reader counts. This module turns those counts into TRUST — a
recommended weight per actor (model_id on the decision side, specialist on the
forecast side), conditioned on state, with hierarchical shrinkage so a thin
cell can never speak louder than its n.

What it is NOT, stated before what it is:

  * It does not mutate any book. CURRENT_BEST_v1 and every other seeded book
    run their declared policy untouched. The output here is a RECOMMENDATION
    RECEIPT that a future, separately-declared challenger book may cite.
  * It is not a neural router. It is the low-capacity counting baseline that
    any learned router must beat — deliberately, because a baseline you have
    not built is a baseline you cannot lose to (reliability.py, same sentence).
  * It never trains on same-day P&L or NAV. Its only input is matured,
    resolved outcomes as the reliability reader reports them.

The estimator is empirical-Bayes backoff. A cell's rate is shrunk toward its
parent with SHRINK_K pseudo-observations, recursively up the hierarchy:

    cell (actor, horizon, vol_state)
        -> (actor, horizon)
        -> (actor,)
        -> population prior (0.5: no skill)

so `shrunk = (successes + K * parent) / (n + K)` at every level. n=0 returns
the parent exactly; n >> K returns the data. An 8-for-8 lucky streak lands at
(8 + 12*parent)/20 — impressed, not convinced — while 200 observations at 55%
keep almost all of their evidence. That asymmetry IS the design.

Verdicts, so the caller can never mistake silence for signal:
  RECOMMENDED     enough matured evidence to rank actors
  ABSTAIN         evidence below EVIDENCE_FLOOR_N — weights are uniform and
                  the receipt says so; uniform-by-ignorance and
                  uniform-by-measurement are different facts
  NO_EDGE         evidence sufficient and no actor's shrunk rate clears the
                  prior — the honest null, reported as such

Known limitation, declared not hidden: actors are treated as independent.
Two clones of one signal will each collect trust; correlation-aware routing
is a later version's problem and this receipt says `correlation_adjusted:
false` so nobody reads it as already solved.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from backend.services.arena import reliability

logger = logging.getLogger(__name__)

ROUTER_VERSION = "RELIABILITY_ROUTER_v1"

#: Pseudo-observations pulling every estimate toward its parent. At n == K
#: the data and the parent split the estimate evenly.
SHRINK_K = 12.0

#: No-skill prior for a hit rate. The decision-cell hit definition
#: (GOOD_CALL/GOOD_PASS) is symmetric, so 0.5 is the honest zero.
POPULATION_PRIOR = 0.5

#: Below this many matured observations across an actor's cells, the router
#: abstains rather than rank. Ranking three actors on nine outcomes is a
#: horoscope with a schema.
EVIDENCE_FLOOR_N = 30

#: An actor earns weight only for shrunk rate beyond prior + EDGE_Z standard
#: errors of its own evidence. A fixed epsilon failed the null-world battery:
#: 101/200 vs 99/200 is sampling noise, and any constant small enough to pass
#: real edges lets noise through at some n. Scaling the bar by SE means the
#: same code says NO_EDGE to coin flips at n=200 and RECOMMENDED to 65% at
#: n=200 — and it is also why a lucky 8-for-8 keeps only a sliver of weight
#: against 400 sustained observations: its SE is 5x larger.
EDGE_Z = 1.5

_BANNER = {
    "router_version": ROUTER_VERSION,
    "validation_status": "PRODUCT_EXPERIMENT",
    "simulation": True,
    "consumed_by": "nothing — recommendation surface only; no book reads this",
    "may_mutate_books": False,
    # Cross-horizon correlation IS adjusted (effective n = per-state max
    # across horizons — the G1 battery fix, 2026-08-21). Cross-NAME
    # correlation within a day is still not.
    "correlation_adjusted": "horizon-dedup only",
    "trains_on": "matured resolved outcomes only (reliability cells)",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── the estimator ───────────────────────────────────────────────────────────
def shrunk_rate(successes: float, n: float, parent: float,
                k: float = SHRINK_K) -> float:
    """Posterior mean of a rate under k pseudo-observations at the parent."""
    if n < 0 or successes < 0 or successes > n:
        raise ValueError(f"impossible cell: successes={successes}, n={n}")
    return (successes + k * parent) / (n + k)


def backoff_estimate(levels: list[tuple], *,
                     prior: float = POPULATION_PRIOR,
                     k: float = SHRINK_K) -> dict:
    """Shrink through a hierarchy, least-specific first.

    `levels` is [(successes, n[, n_effective]), ...] ordered ROOT -> LEAF
    (global first, the exact cell last). Each level's estimate becomes the
    next level's parent, so a thin leaf inherits its lineage instead of
    shouting alone.

    `evidence_n` is the EFFECTIVE n at the DEEPEST level that had any
    observations — the sample the uncertainty of this estimate should be
    priced off. Effective, because the same decision matures at every
    horizon: pooling horizon cells multiplies ROWS ~5x without adding a
    single independent decision, and pricing SE off rows is how the G1
    known-answer battery caught this router recommending coin flips in
    27.5% of null worlds (2026-08-21). A two-tuple level prices its own n.
    """
    est = prior
    leaf_n = 0.0
    evidence_n = 0.0
    for lvl in levels:
        successes, n = float(lvl[0]), float(lvl[1])
        n_eff = float(lvl[2]) if len(lvl) > 2 else n
        est = shrunk_rate(successes, n, est, k)
        leaf_n = n
        if n > 0:
            evidence_n = n_eff
    return {"estimate": est, "leaf_n": leaf_n, "evidence_n": evidence_n,
            "prior": prior, "k": k}


def _standard_error(evidence_n: float, *, prior: float = POPULATION_PRIOR,
                    k: float = SHRINK_K) -> float:
    """SE of a rate at this much evidence, under the prior's variance. The
    +k keeps a zero-evidence actor's SE finite (and large)."""
    return (prior * (1.0 - prior) / (evidence_n + k)) ** 0.5


# ── cells -> trust ──────────────────────────────────────────────────────────
def _hierarchy(cells: list[dict], actor: str,
               context: dict) -> list[tuple[float, float]]:
    """Aggregate an actor's cells at each backoff level, root -> leaf.

    A cell matches a level if it agrees with `context` on every key the level
    conditions on. Missing context keys condition on nothing (global level).
    """
    keys_by_level = [(), ("horizon_days",), ("horizon_days", "vol_state")]
    out = []
    for keys in keys_by_level:
        s = n = 0.0
        matching: list[dict] = []
        for c in cells:
            if c.get("actor") != actor:
                continue
            if any(str(c.get(k)) != str(context.get(k)) for k in keys):
                continue
            s += c["successes"]
            n += c["n"]
            matching.append(c)
        out.append((s, n, _effective_n(matching)))
    return out


def _effective_n(matching: list[dict]) -> float:
    """DECISIONS, not rows: per vol_state, the max n across horizon cells.

    The same decision produces one row per horizon (experience.HORIZONS is
    five deep), and by construction those rows share the decision's fate far
    more often than not. Cells in different vol_states come from different
    decision days and are counted in full; cells that differ only by horizon
    are near-copies, so the largest of them bounds the independent sample.
    This is the conservative end of n_eff ∈ [max_h, sum_h] — chosen after
    the G1 battery measured a 27.5% null-world false-positive rate under
    the sum (rows-as-independent) assumption.
    """
    by_state: dict[str, float] = {}
    for c in matching:
        key = str(c.get("vol_state"))
        by_state[key] = max(by_state.get(key, 0.0), float(c["n"]))
    return sum(by_state.values())


def trust_weights(cells: list[dict], *, context: dict | None = None,
                  prior: float = POPULATION_PRIOR, k: float = SHRINK_K,
                  evidence_floor_n: int = EVIDENCE_FLOOR_N) -> dict:
    """Recommended relative trust per actor from matured cells.

    `cells`: [{actor, successes, n, horizon_days?, vol_state?}, ...] — matured
    outcomes only; the caller (or `recommend`) guarantees that.

    Weight construction: shrunk excess BEYOND `prior + EDGE_Z * SE(actor's
    own evidence)`, floored at zero, normalised. Below that bound an actor
    gets weight 0 (downweighted to silence), never a negative weight — this
    router recommends trust, not short positions in its own models. If nobody
    clears the bound the verdict is NO_EDGE and the fallback is uniform BY
    DECLARED FALLBACK over the actors NOT significantly below prior — an
    actor measurably harmful in this context is excluded even from the
    fallback, because "we cannot rank the rest" is not a reason to fund it.
    """
    context = context or {}
    actors = sorted({c["actor"] for c in cells})
    # The floor is priced in DECISIONS, not rows — five horizon rows of one
    # decision are not five observations (see _effective_n).
    total_n = sum(_effective_n([c for c in cells if c["actor"] == a])
                  for a in actors)
    if not actors or total_n < evidence_floor_n:
        return {
            "verdict": "ABSTAIN",
            "reason": (f"matured effective n={int(total_n)} < "
                       f"floor={evidence_floor_n}; "
                       f"uniform weights are ignorance, not measurement"),
            "context": context,
            "actors": {a: {"weight": (1.0 / len(actors)) if actors else None,
                           "estimate": None, "leaf_n": 0}
                       for a in actors},
            "total_matured_n": int(total_n),
        }

    est = {}
    for a in actors:
        levels = _hierarchy(cells, a, context)
        e = backoff_estimate(levels, prior=prior, k=k)
        e["se"] = _standard_error(e["evidence_n"], prior=prior, k=k)
        est[a] = e

    # lower-confidence-bound excess: what the evidence supports, not what the
    # point estimate flatters
    lcb = {a: max(0.0, e["estimate"] - prior - EDGE_Z * e["se"])
           for a, e in est.items()}

    def _row(a: str, weight: float) -> dict:
        return {"weight": round(weight, 4),
                "estimate": round(est[a]["estimate"], 4),
                "se": round(est[a]["se"], 4),
                "leaf_n": int(est[a]["leaf_n"]),
                "evidence_n": int(est[a]["evidence_n"])}

    if all(x == 0.0 for x in lcb.values()):
        harmful = {a for a, e in est.items()
                   if e["estimate"] < prior - EDGE_Z * e["se"]}
        kept = [a for a in actors if a not in harmful]
        share = (1.0 / len(kept)) if kept else 0.0
        return {
            "verdict": "NO_EDGE",
            "reason": ("no actor clears prior + EDGE_Z*SE at these sample "
                       "sizes — the honest null; uniform by fallback over "
                       "non-harmful actors"),
            "context": context,
            "actors": {a: _row(a, 0.0 if a in harmful else share)
                       for a in actors},
            "excluded_as_harmful": sorted(harmful),
            "total_matured_n": int(total_n),
        }

    z = sum(lcb.values())
    return {
        "verdict": "RECOMMENDED",
        "context": context,
        "actors": {a: _row(a, lcb[a] / z) for a in actors},
        "total_matured_n": int(total_n),
    }


# ── live entry point over the arena ledgers ─────────────────────────────────
def _decision_cells_as_router_input(report: dict) -> list[dict]:
    """Reliability decision cells -> router cells, REPORTED ones only.

    REFUSED_THIN cells carry no rate by contract, so their observations
    cannot be pooled into the parent levels here — the router sees only what
    the counting brain was willing to stand behind. That loses some evidence
    at the margins and is the conservative direction to lose it in.
    """
    out = []
    for c in (report.get("cells") or {}).values():
        if c.get("verdict") != "REPORTED":
            continue
        n = int(c["n"])
        out.append({
            "actor": str(c.get("model_id")),
            "successes": float(c["hit_rate"]) * n,
            "n": n,
            "horizon_days": c.get("horizon_days"),
            "vol_state": c.get("vol_state"),
        })
    return out


def recommend(*, root=None, leg: str = "forecast",
              context: dict | None = None) -> dict:
    """The live receipt: trust over model_ids from the arena's matured cells.

    On the unseeded/young arena this returns ABSTAIN with zero cells — which
    is the correct answer, printed rather than implied.
    """
    report = reliability.decision_cells(
        root=root, leg=leg,
        by=("model_id", "horizon_days", "vol_state"))
    cells = _decision_cells_as_router_input(report)
    per_state = {}
    for vol_state in reliability.VOL_STATES:
        per_state[vol_state] = trust_weights(
            cells, context={**(context or {}), "vol_state": vol_state})
    return {
        **_BANNER,
        "computed_at": _now(),
        "leg": leg,
        "n_reported_cells": len(cells),
        "n_cells_seen": report.get("n_cells", 0),
        "global": trust_weights(cells, context=context),
        "by_vol_state": per_state,
        "params": {"shrink_k": SHRINK_K, "prior": POPULATION_PRIOR,
                   "edge_z": EDGE_Z, "evidence_floor_n": EVIDENCE_FLOOR_N},
    }


def _cli() -> None:  # pragma: no cover - manual driver
    print(json.dumps(recommend(), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    _cli()
