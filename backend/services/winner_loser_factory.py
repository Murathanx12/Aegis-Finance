"""The informative unit is winner vs MATCHED loser, never a gallery of winners.

Rule 4 of the mission, and the one this programme has broken most often. A
mechanism found by reading the winners explains the winners; the question is
whether it separates them from the companies that looked the same beforehand
and did not win.

WHAT MATCHING IS FOR, AND WHAT IT CANNOT DO
===========================================
Matching removes the differences it is given. A winner and a loser matched on
size, industry, momentum, volatility and expectation state differ in the
things NOT matched — and one of those is the mechanism, if there is one. That
is the whole design: make the pair as boring as possible so that whatever is
left is interesting.

What it cannot do is make a claim causal. Unmatched confounders survive
matching, and a matched pair proves only that the named dimensions are not the
explanation. Every result carries the match list, because a reader who does not
know what was held fixed cannot evaluate what was found.

TWO REFUSALS, BOTH LEARNED HERE
===============================
**Match quality is measured, not assumed.** A nearest neighbour is always
available; a nearest neighbour that is nothing like the treated unit is a
control in name only. Standardised differences are computed after matching, and
a pair outside the caliper is dropped rather than kept with a footnote. The
canon's version: a guard must derive what it checks from data it can see.

**Matching uses ONLY pre-outcome information.** Every characteristic is stamped
with the date it was computed from, and that date must precede the episode's
`decision_ts`. This is checked rather than intended — the covariate computed
"as of the event" using a window that closes after it is the most common way a
matched study becomes a look-ahead study.

WHY THE OUTCOME IS A RANK, NOT A RETURN
=======================================
"Winner" is defined cross-sectionally within a calendar block: the market's
direction over the window is common to both members of a pair, so a raw-return
definition would make every pair in a rising month a winner-winner pair and
teach the factory about the market. The label is a within-block rank, so the
market cancels by construction rather than by adjustment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Sequence

#: The dimensions matched on. Ordered as declared in the build order, and this
#: list is REPORTED with every result — a reader who does not know what was held
#: fixed cannot evaluate what was found.
MATCH_DIMENSIONS = ("industry", "log_size", "momentum_12_1", "volatility_60d",
                    "max_drawdown_1y", "log_dollar_volume", "book_to_market",
                    "revision_state", "expectation_state", "calendar_block")

#: Dimensions that must match EXACTLY rather than approximately. A "close"
#: industry is a different industry, and a control drawn from another calendar
#: block is exposed to a different market.
EXACT_DIMENSIONS = ("industry", "calendar_block")

#: Standardised-difference caliper. 0.25 sd is the conventional threshold at
#: which a covariate is considered balanced; it is a convention rather than a
#: derivation, it is declared here, and it is NOT tuned against outcomes —
#: tuning a caliper on the result is choosing the controls that give the answer.
CALIPER_SD = 0.25


@dataclass
class Episode:
    """One security at one decision time, with what was knowable then."""
    entity_id: str
    decision_ts: str
    #: Pre-outcome characteristics. Every value is a number or None; None means
    #: unknown and a pair cannot be matched on a dimension either side lacks.
    characteristics: dict[str, float | str | None]
    #: The date each characteristic's input window CLOSED. Checked against
    #: `decision_ts`, never trusted.
    characteristics_asof: dict[str, str]
    #: Filled after matching. The factory never sees it while pairing.
    outcome: float | None = None
    outcome_horizon_days: int | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class Pair:
    winner: Episode
    loser: Episode
    standardised_differences: dict[str, float]
    calendar_block: str
    worst_dimension: str
    worst_sd: float

    def as_dict(self) -> dict:
        return {
            "winner": self.winner.entity_id, "loser": self.loser.entity_id,
            "calendar_block": self.calendar_block,
            "decision_ts": self.winner.decision_ts,
            "winner_outcome": self.winner.outcome,
            "loser_outcome": self.loser.outcome,
            "standardised_differences": self.standardised_differences,
            "worst_dimension": self.worst_dimension, "worst_sd": self.worst_sd,
            "matched_on": list(MATCH_DIMENSIONS),
        }


class LookAheadInMatching(ValueError):
    """A characteristic whose window closed after the decision it informed."""


def _ts(v) -> datetime:
    d = datetime.fromisoformat(str(v))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def assert_pit(ep: Episode) -> list[str]:
    """Every characteristic's window must close before the decision.

    Returns violations rather than raising, so a builder can count and name
    them. This is the check that separates a matched study from a look-ahead
    study, and it is the one most often assumed rather than run.
    """
    bad = []
    dts = _ts(ep.decision_ts)
    for k, v in ep.characteristics.items():
        if v is None:
            continue
        asof = ep.characteristics_asof.get(k)
        if asof is None:
            bad.append(f"{k} has a value but no `characteristics_asof` entry — "
                       f"a covariate with no date cannot be shown to precede "
                       f"the decision, and 'it obviously does' is how this goes "
                       f"wrong")
            continue
        if _ts(asof) >= dts:
            bad.append(f"{k} computed as of {asof}, which is not before the "
                       f"decision at {ep.decision_ts}")
    return bad


def assert_pit_strict(ep: Episode) -> None:
    """The same check, as a REFUSAL.

    `LookAheadInMatching` was defined here and raised nowhere — an exception
    with no firing path, which is S47's failure one step earlier: not a guard
    whose test never made it fire, but a guard that could not fire at all.
    Found by the missing-input contract on its first run.

    `assert_pit` returning a list is right for the builder, which needs to
    count and name what it drops. It is wrong for every other caller, because a
    list of violations is only a guard if somebody looks at it.
    """
    bad = assert_pit(ep)
    if bad:
        raise LookAheadInMatching(
            f"episode {ep.entity_id!r} @ {ep.decision_ts}: {len(bad)} "
            f"characteristic(s) are not "
            f"point-in-time — " + "; ".join(bad))


def _numeric(eps: Sequence[Episode], dim: str) -> list[float]:
    return [float(e.characteristics[dim]) for e in eps
            if isinstance(e.characteristics.get(dim), (int, float))]


def _pooled_sd(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def standardised_differences(a: Episode, b: Episode,
                             sds: dict[str, float]) -> dict[str, float]:
    """|a - b| in pooled standard deviations, per dimension.

    A dimension whose pooled sd is zero contributes `inf` when the two differ
    and 0.0 when they do not: with no variation, ANY difference is infinitely
    many standard deviations, and returning a small number there would silently
    admit the pair.
    """
    out: dict[str, float] = {}
    for d in MATCH_DIMENSIONS:
        va, vb = a.characteristics.get(d), b.characteristics.get(d)
        if va is None or vb is None:
            out[d] = float("inf")            # cannot match on what is missing
            continue
        if d in EXACT_DIMENSIONS or isinstance(va, str) or isinstance(vb, str):
            out[d] = 0.0 if va == vb else float("inf")
            continue
        sd = sds.get(d, 0.0)
        diff = abs(float(va) - float(vb))
        out[d] = (0.0 if diff == 0 else float("inf")) if sd <= 0 else diff / sd
    return out


def match_pairs(episodes: Sequence[Episode], *, block_of,
                winner_quantile: float = 0.2,
                caliper_sd: float = CALIPER_SD,
                covariate_sds: dict[str, float] | None = None,
                min_episodes_for_scale: int = 30) -> tuple[list[Pair], dict]:
    """Winner/matched-loser pairs, one loser per winner, greedy nearest-first.

    `block_of(episode) -> str` assigns the calendar block. Matching happens
    strictly WITHIN a block: a control from another period is exposed to a
    different market, and the whole point of the pair is that the market is not
    the difference.

    Greedy nearest-first rather than optimal assignment: the ordering is by
    match quality, so the best-matched pairs form first and the leftovers are
    dropped rather than forced. An optimal global assignment would produce MORE
    pairs, each slightly worse, which is the wrong trade when the pair is the
    unit of evidence.

    Returns `(pairs, denominators)`. The denominators are not decoration — a
    factory that reports only the pairs it formed is reporting its own filter.
    """
    counts = {"episodes": len(episodes), "pit_violations": 0,
              "no_outcome": 0, "blocks": 0, "candidate_winners": 0,
              "candidate_losers": 0, "pairs": 0,
              "unmatched_winners_outside_caliper": 0,
              "unmatched_winners_no_partner": 0}
    violations: dict[str, int] = {}

    usable: list[Episode] = []
    for e in episodes:
        v = assert_pit(e)
        if v:
            counts["pit_violations"] += 1
            for x in v:
                key = x.split(" ")[0]
                violations[key] = violations.get(key, 0) + 1
            continue
        if e.outcome is None:
            counts["no_outcome"] += 1
            continue
        usable.append(e)

    # EVERY EPISODE DROPPED FOR LOOK-AHEAD IS NOT "NO PAIRS FOUND".
    #
    # Same shape as the block-local sd bug this module already carries a
    # comment about: an empty result read as a fact about the world when it was
    # a fact about the inputs. If nothing survived the point-in-time check, the
    # honest output is a refusal naming the covariates, not a report of zero.
    if episodes and not usable and counts["pit_violations"]:
        raise LookAheadInMatching(
            f"all {counts['pit_violations']} episodes failed the "
            f"point-in-time check, so there is nothing to match. Offending "
            f"covariates: {violations}. Reporting 'no pairs' here would blame "
            f"the world for a property of the extraction.")

    by_block: dict[str, list[Episode]] = {}
    for e in usable:
        by_block.setdefault(block_of(e), []).append(e)
    counts["blocks"] = len(by_block)

    # THE COVARIATE SCALE IS A PROPERTY OF THE POPULATION, NOT OF THE BLOCK.
    #
    # The first version computed the pooled sd inside each block, which is
    # degenerate exactly where it matters: in a block of two, the sd IS the
    # difference, so every possible pair sits 1.41 sd apart and nothing ever
    # matches. It also makes the caliper mean a different thing in every block
    # — 0.25 sd against a quiet quarter's spread is a much tighter requirement
    # than against a volatile one, so the same threshold would silently admit
    # different pairs depending on when they happened.
    #
    # Scales are therefore estimated once, over every usable episode, and a
    # caller may supply them outright (a fixed scale across runs is what makes
    # two runs' calipers comparable). Below `min_episodes_for_scale` the
    # estimate is not trustworthy and this REFUSES rather than matching against
    # a scale it invented from six points.
    if covariate_sds is not None:
        sds, scale_src = dict(covariate_sds), "supplied"
    elif len(usable) >= min_episodes_for_scale:
        sds = {d: _pooled_sd(_numeric(usable, d)) for d in MATCH_DIMENSIONS}
        scale_src = f"population n={len(usable)}"
    else:
        counts.update(
            pairs=0, covariate_scale_source="REFUSED",
            refusal=(f"{len(usable)} usable episodes is below "
                     f"min_episodes_for_scale={min_episodes_for_scale}: a "
                     f"standardised difference needs a spread to standardise "
                     f"BY, and one estimated from this few points would make "
                     f"the caliper meaningless. Supply `covariate_sds` if the "
                     f"scale is known from elsewhere."),
            matched_on=list(MATCH_DIMENSIONS), caliper_sd=caliper_sd,
            pit_violation_kinds=violations,
            match_rate_of_candidate_winners=None)
        return [], counts
    counts["covariate_scale_source"] = scale_src

    pairs: list[Pair] = []
    for blk, eps in sorted(by_block.items()):
        if len(eps) < 2:
            continue
        # The label is a WITHIN-BLOCK rank, so the market cancels by
        # construction. A raw-return threshold would make every pair in a
        # rising month a winner-winner pair.
        ranked = sorted(eps, key=lambda e: e.outcome, reverse=True)
        k = max(1, int(len(ranked) * winner_quantile))
        winners, losers = ranked[:k], ranked[-k:]
        counts["candidate_winners"] += len(winners)
        counts["candidate_losers"] += len(losers)

        # Score every admissible (winner, loser) combination, then take them
        # best-first so the strongest matches are not consumed by weaker ones.
        cand = []
        for w in winners:
            for l in losers:
                if w is l:
                    continue
                sd = standardised_differences(w, l, sds)
                worst_d = max(sd, key=lambda d: sd[d])
                cand.append((sd[worst_d], worst_d, sd, w, l))
        cand.sort(key=lambda c: c[0])

        used: set[int] = set()
        matched_w: set[int] = set()
        for worst, worst_d, sd, w, l in cand:
            if id(w) in matched_w or id(l) in used:
                continue
            if worst > caliper_sd:
                continue
            used.add(id(l))
            matched_w.add(id(w))
            pairs.append(Pair(winner=w, loser=l, standardised_differences=sd,
                              calendar_block=blk, worst_dimension=worst_d,
                              worst_sd=worst))
        for w in winners:
            if id(w) not in matched_w:
                # Distinguish "no admissible partner existed" from "partners
                # existed and all were too different" — they call for opposite
                # fixes, and one number for both hides which one you have.
                had_any = any(c[3] is w for c in cand)
                key = ("unmatched_winners_outside_caliper" if had_any
                       else "unmatched_winners_no_partner")
                counts[key] += 1

    counts["pairs"] = len(pairs)
    counts["pit_violation_kinds"] = violations
    counts["caliper_sd"] = caliper_sd
    counts["matched_on"] = list(MATCH_DIMENSIONS)
    counts["match_rate_of_candidate_winners"] = (
        len(pairs) / counts["candidate_winners"]
        if counts["candidate_winners"] else None)
    return pairs, counts


def balance_report(pairs: Iterable[Pair]) -> dict:
    """Post-match balance. The number that says whether matching worked.

    Reported per dimension, because a mean standardised difference of 0.1 can
    hide one dimension at 0.24 — and that dimension is the one a reader will
    propose as the explanation.
    """
    pairs = list(pairs)
    if not pairs:
        return {"n_pairs": 0}
    out: dict[str, dict] = {}
    for d in MATCH_DIMENSIONS:
        vals = [p.standardised_differences.get(d, float("inf")) for p in pairs]
        finite = [v for v in vals if math.isfinite(v)]
        out[d] = {
            "mean_sd": (sum(finite) / len(finite)) if finite else None,
            "max_sd": max(finite) if finite else None,
            "n_infinite": len(vals) - len(finite),
        }
    return {"n_pairs": len(pairs), "per_dimension": out,
            "worst_dimension": max(
                (d for d in out if out[d]["max_sd"] is not None),
                key=lambda d: out[d]["max_sd"], default=None)}
