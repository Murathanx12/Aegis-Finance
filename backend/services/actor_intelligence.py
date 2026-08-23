"""What is any given actor's word worth, conditional on what they are saying?

THE IDEA, AND WHY THE JOKE VERSION IS WRONG
===========================================
"Inverse Cramer" is a good instinct wrapped around a bad method. The instinct:
a public actor's track record is measurable, and an actor who is reliably wrong
carries information exactly as an actor who is reliably right does. The bad
method: deciding in advance who that actor is, because the internet finds them
funny.

The actual Inverse Cramer ETF (SJIM) returned negative over its reported life
and was liquidated. Reputation is not evidence, and a joke is not a prior.

So nothing here hard-codes any actor as contrarian. This module estimates

    P(claim resolves in the actor's stated direction | actor, domain,
      claim_type, horizon, regime)

and lets an INVERSE mapping be EARNED, under conditions strict enough that
earning it is genuinely hard.

WHY INVERTING IS STATISTICALLY DANGEROUS
========================================
An actor at a 0.42 hit rate against a 0.50 null looks like a 0.58 edge the
moment you flip them. That flip is free, which is exactly the problem:

1. **Selection.** Scan 200 actors against a 0.50 null and the worst few will
   sit well below it from noise alone. Inverting the worst is a multiplicity
   machine, not a discovery. So the deficit must survive correction across
   EVERY actor examined (CANON section 63: BH-FDR, m = the run), not just its
   own t-test.
2. **Symmetry.** Inverting does not add evidence. The inverse of a
   badly-measured actor is a badly-measured signal, with the same standard
   error and the same effective n.
3. **Correlation.** An actor commenting on forty names in one week has not
   made forty independent claims. Effective n comes from DECISION DAYS, the
   same fix the G1 battery forced on the trust router.

So `inverse_license` demands all four of: a significant deficit, survival of
multiplicity across the actors considered, a minimum of independent decision
days, AND confirmation on a HOLDOUT slice that played no part in selecting the
actor. Any one missing is a refusal with a reason.

WHAT THIS MODULE DOES NOT DO
============================
It does not size anything, trade anything, or route capital. It reuses
`trust_router.backoff_estimate` rather than reimplementing shrinkage, because a
second trust system is the thing this programme least needs. A neural or
learned router remains a CHALLENGER that must beat this baseline prospectively.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "actor-intelligence-1.0.0"

#: The null a directional claim is measured against. A claim that the market
#: goes up is right ~53% of the time over most horizons, so 0.50 is NOT the
#: honest null for a bullish call -- the base rate of the direction is. Callers
#: pass the measured base rate; this is only the fallback when none is known.
DEFAULT_NULL = 0.5

#: Below this many INDEPENDENT decision days an actor gets an estimate but no
#: verdict. Chosen to match the trust router's own thin-cell discipline.
MIN_DECISION_DAYS = 20

#: An inverse needs a bigger deficit than a direct edge needs a surplus,
#: because the inverse is selected on the same data that measured it.
INVERSE_MIN_DEFICIT = 0.05


class ActorEvidenceRefused(RuntimeError):
    """The evidence needed to judge this actor does not exist."""


class InverseRefused(RuntimeError):
    """An inverse mapping was requested that has not been earned."""


#: The dimensions an actor cell may be conditioned on. Declared, not
#: discovered: an unknown slice must be refused as loudly on an empty corpus as
#: on a full one, or "no data yet" and "never recorded" read identically.
ACTOR_KEYS = frozenset({"actor", "domain", "claim_type", "horizon_days",
                        "regime"})


@dataclass(frozen=True)
class ActorClaim:
    """One timestamped, public, falsifiable claim by a named actor.

    `public_at` is when the claim became PUBLIC, not when Aegis noticed it.
    `observed_at` is when Aegis noticed. The gap between them is
    `disclosure_lag_days`, and it is the difference between a signal and a
    fact about the past: a 13F position is public 45 days after it was taken,
    so grading it from the position date would credit the actor with foresight
    that no follower could have acted on.
    """

    claim_id: str
    actor: str
    #: analyst | executive | insider | politician | commentator | newsletter |
    #: journalist | prediction_market | institution | aegis_model
    actor_type: str
    entity: str
    #: The direction the actor asserted: +1 bullish, -1 bearish. 0 is not a
    #: claim and is refused -- an actor who says nothing cannot be graded.
    direction: int
    claim_type: str
    domain: str
    horizon_days: int
    public_at: str
    observed_at: str
    regime: str = "unknown"
    disclosure_lag_days: float | None = None
    price_when_knowable: float | None = None
    #: Filled at resolution.
    outcome: int | None = None
    realized_return: float | None = None
    benchmark_return: float | None = None
    resolved_at: str | None = None
    schema_version: str = SCHEMA_VERSION
    notes: dict = field(default_factory=dict)


def make_claim(*, actor: str, actor_type: str, entity: str, direction: int,
               claim_type: str, domain: str, horizon_days: int,
               public_at: str, observed_at: str | None = None,
               regime: str = "unknown",
               price_when_knowable: float | None = None) -> ActorClaim:
    """Build a gradeable claim, refusing the ones that cannot be graded."""
    if direction not in (-1, 1):
        raise ActorEvidenceRefused(
            f"direction={direction!r}: a claim must assert +1 or -1. An actor "
            f"who said nothing directional cannot be right or wrong, and "
            f"scoring 0 as a miss would penalise silence.")
    if horizon_days <= 0:
        raise ActorEvidenceRefused(
            "a claim with no horizon has no resolution date and is not "
            "falsifiable")
    obs = observed_at or datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    pub_d = date.fromisoformat(public_at[:10])
    obs_d = date.fromisoformat(obs[:10])
    if obs_d < pub_d:
        raise ActorEvidenceRefused(
            f"observed_at {obs[:10]} precedes public_at {public_at[:10]}: "
            f"Aegis cannot have seen a claim before it was public. This is "
            f"the shape lookahead takes in an actor corpus.")
    import hashlib
    cid = hashlib.sha256(
        f"{actor}|{entity}|{claim_type}|{public_at}|{direction}".encode()
    ).hexdigest()[:16]
    return ActorClaim(
        claim_id=cid, actor=actor, actor_type=actor_type, entity=entity,
        direction=direction, claim_type=claim_type, domain=domain,
        horizon_days=horizon_days, public_at=public_at, observed_at=obs,
        regime=regime,
        disclosure_lag_days=(obs_d - pub_d).days,
        price_when_knowable=price_when_knowable,
    )


def _decision_days(claims: list[dict]) -> int:
    """Independent decision DAYS, not claims.

    An actor who named forty stocks on one broadcast made one decision, not
    forty. Counting claims here is the same error the G1 battery caught in the
    trust router, one layer up.
    """
    return len({str(c.get("public_at", ""))[:10] for c in claims
                if c.get("public_at")})


def _hits(claims: list[dict]) -> tuple[float, float]:
    graded = [c for c in claims if c.get("outcome") in (0, 1)]
    return float(sum(c["outcome"] for c in graded)), float(len(graded))


def actor_skill(claims: list[dict], *, actor: str,
                context: dict | None = None,
                null_rate: float = DEFAULT_NULL) -> dict:
    """Shrunken hit rate for one actor, backing off through the hierarchy.

    Levels, least specific first: population -> actor_type -> actor ->
    actor x context. A thin leaf inherits its lineage instead of shouting
    alone -- `trust_router.backoff_estimate` does the arithmetic, unchanged.
    """
    from backend.services.arena.trust_router import (backoff_estimate,
                                                     _standard_error)

    context = context or {}
    unknown = set(context) - ACTOR_KEYS
    if unknown:
        raise ActorEvidenceRefused(
            f"unknown conditioning key(s) {sorted(unknown)}; known: "
            f"{sorted(ACTOR_KEYS)}. A slice discovered from whatever the data "
            f"happened to carry is not a declared slice.")

    mine = [c for c in claims if c.get("actor") == actor]
    if not mine:
        raise ActorEvidenceRefused(
            f"no claims recorded for actor {actor!r} -- an actor with no "
            f"corpus has no reliability, which is different from having a "
            f"neutral one")

    kin = [c for c in claims
           if c.get("actor_type") == (mine[0].get("actor_type"))]
    leaf = [c for c in mine
            if all(str(c.get(k)) == str(v) for k, v in context.items())]

    # A level is only a PARENT if it carries observations the child does not.
    # When an actor is the whole corpus -- or the context slice is the actor's
    # entire history -- population/kin/actor/leaf are the SAME rows, and
    # shrinking through four identical levels applies one body of evidence four
    # times, driving a 0-for-5 actor to 0.12 instead of back toward the null.
    # Collapse duplicates so each distinct body of evidence is used once.
    levels: list[tuple] = []
    for group in (claims, kin, mine, leaf):
        hits_n = _hits(group)
        if levels and (levels[-1][0], levels[-1][1]) == hits_n:
            continue
        levels.append((hits_n[0], hits_n[1], float(_decision_days(group))))

    est = backoff_estimate(levels, prior=null_rate)
    se = _standard_error(est["evidence_n"], prior=null_rate)
    days = _decision_days(leaf) or _decision_days(mine)
    edge = est["estimate"] - null_rate

    return {
        "actor": actor,
        "actor_type": mine[0].get("actor_type"),
        "context": dict(context),
        "n_claims": len(leaf) or len(mine),
        "n_decision_days": days,
        "raw_hit_rate": (_hits(leaf)[0] / _hits(leaf)[1]
                         if _hits(leaf)[1] else None),
        "shrunk_hit_rate": round(est["estimate"], 4),
        "null_rate": null_rate,
        "edge": round(edge, 4),
        "standard_error": round(se, 4),
        "z": round(edge / se, 3) if se > 0 else None,
        "evidence_n": est["evidence_n"],
        "verdict": ("THIN" if days < MIN_DECISION_DAYS else "MEASURED"),
        "thin_reason": (
            f"{days} independent decision day(s) < {MIN_DECISION_DAYS}; an "
            f"estimate is reported but no verdict is licensed"
            if days < MIN_DECISION_DAYS else None),
        "note": ("hit rate is DIRECTIONAL accuracy only. It says nothing "
                 "about timing, sizing or magnitude, which are separate "
                 "skills and are not measured here."),
    }


def inverse_license(skills: list[dict], *, holdout: list[dict] | None = None,
                    min_deficit: float = INVERSE_MIN_DEFICIT,
                    fdr_q: float = 0.10) -> dict:
    """Which actors, if any, have EARNED an inverse mapping.

    `skills` is every actor examined in this run -- not a shortlist. Passing
    only the losers would defeat the multiplicity control, so the count of
    actors considered IS the multiplicity m.

    All four conditions must hold:
      1. deficit at least `min_deficit` below the null;
      2. survives BH-FDR at `fdr_q` across every actor considered;
      3. at least MIN_DECISION_DAYS independent decision days;
      4. the deficit repeats on a HOLDOUT slice that took no part in
         selecting the actor.
    """
    considered = [s for s in skills if s.get("z") is not None]
    m = len(considered)
    if m == 0:
        return {"licensed": [], "m_considered": 0,
                "refused": [], "reason": "no actor carried a usable estimate"}

    # One-sided: we are asking specifically who is reliably WRONG.
    from math import erfc, sqrt
    scored = []
    for s in considered:
        z = float(s["z"])
        p = 0.5 * erfc((-z) / sqrt(2.0))       # P(Z <= z), left tail
        scored.append((p, s))
    scored.sort(key=lambda t: t[0])

    # Benjamini-Hochberg.
    survivors = set()
    for i, (p, s) in enumerate(scored, start=1):
        if p <= fdr_q * i / m:
            survivors = {id(x[1]) for x in scored[:i]}
    holdout_by_actor = {}
    for h in (holdout or []):
        holdout_by_actor[h.get("actor")] = h

    licensed, refused = [], []
    for p, s in scored:
        reasons = []
        if s["edge"] > -min_deficit:
            reasons.append(
                f"deficit {abs(s['edge']):.4f} < required {min_deficit}")
        if id(s) not in survivors:
            reasons.append(
                f"does not survive BH-FDR q={fdr_q} across m={m} actors "
                f"considered (p={p:.4f})")
        if s["n_decision_days"] < MIN_DECISION_DAYS:
            reasons.append(
                f"{s['n_decision_days']} decision days < {MIN_DECISION_DAYS}")
        h = holdout_by_actor.get(s["actor"])
        if h is None:
            reasons.append("no holdout slice supplied — an inverse selected "
                           "and confirmed on the same data is not confirmed")
        elif h.get("edge", 0.0) > -min_deficit:
            reasons.append(
                f"holdout edge {h.get('edge')} did not repeat the deficit")

        row = {"actor": s["actor"], "edge": s["edge"], "z": s["z"],
               "p_one_sided": round(p, 5),
               "n_decision_days": s["n_decision_days"]}
        if reasons:
            refused.append({**row, "refused_because": reasons})
        else:
            licensed.append({**row,
                             "holdout_edge": holdout_by_actor[s["actor"]]["edge"],
                             "mapping": "INVERSE",
                             "note": ("licensed on measured, multiplicity-"
                                      "corrected, holdout-confirmed evidence "
                                      "— never on reputation")})
    return {
        "licensed": licensed,
        "refused": refused,
        "m_considered": m,
        "fdr_q": fdr_q,
        "min_deficit": min_deficit,
        "standard": ("an INVERSE is earned by four independent conditions; "
                     "reputation and popular opinion are not among them"),
    }


def to_dict(claim: ActorClaim) -> dict:
    return asdict(claim)
