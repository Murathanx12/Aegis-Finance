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
from statistics import NormalDist

from backend.services.arena import reliability

logger = logging.getLogger(__name__)

ROUTER_VERSION = "RELIABILITY_ROUTER_v1"

_NORM = NormalDist()

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

#: The per-WORLD false-trust rate the corrected bar is built to hold: the
#: probability that ANY actor earns weight when no actor has edge. ORDER 27
#: P2 declared 5% and the G1 correlated battery measures whether it is
#: delivered — a nominal rate is a claim, not a property.
EDGE_ALPHA = 0.05


def edge_z(n_actors: int, *, cluster_adjust: bool,
           alpha: float = EDGE_ALPHA) -> float:
    """Standard errors an actor must clear the prior by to earn weight.

    v1 (cluster_adjust off) keeps its declared EDGE_Z untouched: ORDER 27 says
    the v1 bars stand for v1, and this function must not quietly restate them.

    With the correction on, the bar is Bonferroni over the actors being ranked.
    The router's whole job is to pick the best of m, and a per-comparison bar
    applied to a best-of-m choice is the multiplicity error the canon (§63)
    refuses everywhere else in this codebase; m is the number of actors in the
    run, exactly as `m = run` reads for a screen. It scales itself: the day the
    arena carries eight model_ids the bar rises without anyone remembering to
    raise it.
    """
    if not cluster_adjust:
        return EDGE_Z
    m = max(1, int(n_actors))
    return _NORM.inv_cdf(1.0 - alpha / m)

#: Divide each cell's row count by the design effect its own decision-date
#: clustering measures (`reliability.design_effect`), instead of counting ten
#: names entered on one morning as ten independent observations.
#:
#: DEFAULT OFF, and that default is an ATTENDED decision rather than a
#: judgement that OFF is right. The G1 correlated-worlds battery
#: (`scripts/g1_correlated_battery.py`, 2026-08-23) measures the two settings:
#:
#:     OFF  null-world recommendation rate 38.7% [33.3, 44.3]
#:     ON   see the committed receipt
#:
#: against ORDER 27's <=5% bar — so OFF is measurably broken and ON is the
#: fix. It ships off because this router's verdict is already in a live causal
#: path (`engine.py` sizes `ce_kelly` books at `abstain_kelly_factor` unless
#: the verdict is RECOMMENDED), and flipping it silently would leave one live
#: NAV series describing two policies mid-segment. That flip is Murat's, and
#: `router_capital_gate` refuses to license the OFF setting in the meantime.
#: FLIPPED TO TRUE 2026-08-23 on Murat's confirmation. The G1 correlated-worlds
#: battery measures OFF at a 38.7% null-world recommendation rate against ORDER
#: 27's <=5% bar, so OFF was measurably broken and this is the correction.
#:
#: It was safe to flip only because the setting is now part of the POLICY
#: IDENTITY of the books that consume it (`spec.book_fingerprint`), so the flip
#: is self-refusing rather than silent: PROFIT_ALLOCATOR_v1, the only ce_kelly
#: book, cannot run under its old seed. It is RETIRED from AUTHORISED_ACTIVE
#: rather than left to fail nightly; its NAV history is preserved untouched and
#: a v2 succeeds it, seeded under cluster adjustment from birth.
CLUSTER_ADJUST_DEFAULT = True

_BANNER = {
    "router_version": ROUTER_VERSION,
    "validation_status": "PRODUCT_EXPERIMENT",
    "simulation": True,
    "consumed_by": ("arena engine ce_kelly sizing — verdict != RECOMMENDED "
                    "halves declared aggression (v1 knob only)"),
    "may_mutate_books": False,
    "trains_on": "matured resolved outcomes only (reliability cells)",
}


def _banner(cluster_adjust: bool) -> dict:
    return {
        **_BANNER,
        # Cross-horizon correlation IS adjusted (effective n = per-state max
        # across horizons — the G1 battery fix, 2026-08-21). Cross-NAME
        # correlation within a day is adjusted only when cluster_adjust is on.
        "correlation_adjusted": ("horizon-dedup + decision-date design effect"
                                 if cluster_adjust else "horizon-dedup only"),
        "cluster_adjust": cluster_adjust,
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
def _hierarchy(cells: list[dict], actor: str, context: dict, *,
               cluster_adjust: bool,
               actor_clustering: dict | None = None,
               ) -> list[tuple[float, float, float]]:
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
        n_eff = _effective_n(matching, cluster_adjust=cluster_adjust)
        if cluster_adjust and not keys:
            # The unconditional level pools every cell, so its cells are
            # different views of the same mornings and cannot have their
            # effective counts added. The counting brain measured this actor's
            # clustering once, over its deduplicated decisions; that number is
            # the only one entitled to speak for the pooled level.
            pooled = (actor_clustering or {}).get(actor) or {}
            pooled_n = pooled.get("n_effective")
            if isinstance(pooled_n, (int, float)) and pooled_n > 0:
                n_eff = min(n_eff, float(pooled_n))
        if cluster_adjust and n > 0:
            # ONE sample size, used everywhere. Shrinking a rate with `n` while
            # pricing its standard error off `n_eff` is not conservative — it
            # is incoherent, and it is why the first cluster-corrected run
            # still recommended coin flips in 30% of null worlds: 12 pseudo-
            # observations shrink nothing against 675 rows, while the SE beside
            # them was already claiming only 15 independent decisions existed.
            # The ratio estimate is unbiased at either weight; carrying it at
            # n_eff makes the prior bite exactly as hard as the evidence is
            # thin.
            s, n = (s / n) * n_eff, n_eff
        out.append((s, n, n_eff))
    return out


def _cell_n_eff(cell: dict, *, cluster_adjust: bool) -> float:
    """One cell's independent-decision count.

    Without the adjustment this is the row count, which assumes every row was
    a separate draw. With it, the count is the one the counting brain measured
    from the cell's own decision-date clustering — a cell whose rows came from
    four mornings carries four mornings of information however many names each
    morning held. A cell that never reported its clustering (an older row, a
    reader that predates the field) falls back to its row count, and that
    fallback is the permissive direction, so `recommend` records whether the
    adjustment was actually available rather than merely requested.
    """
    n = float(cell["n"])
    if not cluster_adjust:
        return n
    clustering = cell.get("clustering") or {}
    n_eff = clustering.get("n_effective")
    return float(n_eff) if isinstance(n_eff, (int, float)) and n_eff > 0 else n


def _effective_n(matching: list[dict], *, cluster_adjust: bool = False) -> float:
    """DECISIONS, not rows: per vol_state, the max n across horizon cells.

    The same decision produces one row per horizon (experience.HORIZONS is
    five deep), and by construction those rows share the decision's fate far
    more often than not. Cells in different vol_states come from different
    decision days and are counted in full; cells that differ only by horizon
    are near-copies, so the largest of them bounds the independent sample.
    This is the conservative end of n_eff ∈ [max_h, sum_h] — chosen after
    the G1 battery measured a 27.5% null-world false-positive rate under
    the sum (rows-as-independent) assumption.

    That fix deduplicated the five horizon rows of one decision and nothing
    else. `cluster_adjust` deduplicates the OTHER axis — the names that shared
    a morning — by taking each cell's measured independent-decision count
    before the same per-state max. The G1 correlated-worlds battery measures
    what each setting is worth; see CLUSTER_ADJUST_DEFAULT.
    """
    by_state: dict[str, float] = {}
    for c in matching:
        key = str(c.get("vol_state"))
        by_state[key] = max(by_state.get(key, 0.0),
                            _cell_n_eff(c, cluster_adjust=cluster_adjust))
    return sum(by_state.values())


def trust_weights(cells: list[dict], *, context: dict | None = None,
                  prior: float = POPULATION_PRIOR, k: float = SHRINK_K,
                  evidence_floor_n: int = EVIDENCE_FLOOR_N,
                  cluster_adjust: bool | None = None,
                  actor_clustering: dict | None = None) -> dict:
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
    if cluster_adjust is None:
        cluster_adjust = CLUSTER_ADJUST_DEFAULT
    actors = sorted({c["actor"] for c in cells})
    # The floor is priced in DECISIONS, not rows — five horizon rows of one
    # decision are not five observations (see _effective_n).
    total_n = sum(_hierarchy(cells, a, {}, cluster_adjust=cluster_adjust,
                             actor_clustering=actor_clustering)[0][2]
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
            "cluster_adjusted": cluster_adjust,
        }

    est = {}
    for a in actors:
        levels = _hierarchy(cells, a, context, cluster_adjust=cluster_adjust,
                            actor_clustering=actor_clustering)
        e = backoff_estimate(levels, prior=prior, k=k)
        e["se"] = _standard_error(e["evidence_n"], prior=prior, k=k)
        est[a] = e

    # lower-confidence-bound excess: what the evidence supports, not what the
    # point estimate flatters
    z_trust = edge_z(len(actors), cluster_adjust=cluster_adjust)
    lcb = {a: max(0.0, e["estimate"] - prior - z_trust * e["se"])
           for a, e in est.items()}

    def _row(a: str, weight: float) -> dict:
        return {"weight": round(weight, 4),
                "estimate": round(est[a]["estimate"], 4),
                "se": round(est[a]["se"], 4),
                "leaf_n": int(est[a]["leaf_n"]),
                "evidence_n": int(est[a]["evidence_n"])}

    if all(x == 0.0 for x in lcb.values()):
        # DELIBERATELY uncorrected, and asymmetric with the trust bar above.
        # Multiplicity control exists to stop us funding noise; applying it
        # here would make a harmful actor HARDER to exclude, which is the
        # opposite of what the correction is for. Wrongly excluding an actor
        # costs an equal share of a fallback; wrongly funding a measurably
        # harmful one costs capital.
        harmful = {a for a, e in est.items()
                   if e["estimate"] < prior - EDGE_Z * e["se"]}
        # The fallback funds an actor only if its own shrunk estimate is at
        # least the no-skill prior — NOT merely "not proven harmful". Failing
        # to reject harm is not evidence of safety, and the G1 correlated
        # battery priced that confusion: under a significance-tested exclusion
        # a truly harmful actor (0.35 against a 0.50 prior) still collected a
        # third of the fallback in HALF of all harmful worlds, because its
        # shrunk estimate sat just inside the threshold. Among actors we
        # cannot rank, the one that looks worst has no claim on capital.
        #
        # Rides on `cluster_adjust` with every other v1.1 change, so that ONE
        # attended flip moves the router from its declared v1 semantics to the
        # measured ones. A fix that arrived on its own schedule would leave the
        # OFF receipt describing a router that is neither v1 nor v1.1.
        below = ({a for a, e in est.items() if e["estimate"] < prior}
                 if cluster_adjust else harmful)
        kept = [a for a in actors if a not in below]
        share = (1.0 / len(kept)) if kept else 0.0
        return {
            "verdict": "NO_EDGE",
            "reason": ("no actor clears the trust bar at these sample sizes — "
                       "the honest null; uniform by fallback over actors whose "
                       "own estimate is at or above the prior, and no capital "
                       "at all if none is"),
            "context": context,
            "actors": {a: _row(a, 0.0 if a in below else share)
                       for a in actors},
            "excluded_as_harmful": sorted(harmful),
            "excluded_below_prior": sorted(below),
            "total_matured_n": int(total_n),
            "cluster_adjusted": cluster_adjust,
        }

    z = sum(lcb.values())
    return {
        "verdict": "RECOMMENDED",
        "context": context,
        "actors": {a: _row(a, lcb[a] / z) for a in actors},
        "total_matured_n": int(total_n),
        "cluster_adjusted": cluster_adjust,
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
            # measured by the counting brain; absent on pre-2026-08-23 rows
            "clustering": c.get("clustering"),
        })
    return out


def recommend(*, root=None, leg: str = "forecast",
              context: dict | None = None,
              cluster_adjust: bool | None = None) -> dict:
    """The live receipt: trust over model_ids from the arena's matured cells.

    On the unseeded/young arena this returns ABSTAIN with zero cells — which
    is the correct answer, printed rather than implied.
    """
    if cluster_adjust is None:
        cluster_adjust = CLUSTER_ADJUST_DEFAULT
    report = reliability.decision_cells(
        root=root, leg=leg,
        by=("model_id", "horizon_days", "vol_state"))
    cells = _decision_cells_as_router_input(report)
    actor_clustering = report.get("actor_clustering") or {}
    per_state = {}
    for vol_state in reliability.VOL_STATES:
        per_state[vol_state] = trust_weights(
            cells, context={**(context or {}), "vol_state": vol_state},
            cluster_adjust=cluster_adjust, actor_clustering=actor_clustering)
    # Requested is not the same as applied: a ledger of cells that carry no
    # clustering block silently falls back to row counts, and a receipt that
    # said "adjusted" over that would be the permissive lie this whole battery
    # exists to catch.
    n_with_clustering = sum(1 for c in cells
                            if (c.get("clustering") or {}).get("n_effective"))
    return {
        **_banner(cluster_adjust),
        "computed_at": _now(),
        "leg": leg,
        "n_reported_cells": len(cells),
        "n_cells_seen": report.get("n_cells", 0),
        "n_cells_with_clustering": n_with_clustering,
        "cluster_adjust_effective": bool(cluster_adjust and n_with_clustering),
        "global": trust_weights(cells, context=context,
                                cluster_adjust=cluster_adjust,
                                actor_clustering=actor_clustering),
        "by_vol_state": per_state,
        "params": {"shrink_k": SHRINK_K, "prior": POPULATION_PRIOR,
                   "edge_z": EDGE_Z, "evidence_floor_n": EVIDENCE_FLOOR_N,
                   "cluster_adjust": cluster_adjust},
    }


def _cli() -> None:  # pragma: no cover - manual driver
    print(json.dumps(recommend(), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    _cli()
