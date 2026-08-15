"""Replay one decision under every alternative, and record the whole surface.

RULING R3, second half: *record the WHOLE surface, never just the best answer.*

That instruction is the difference between research and hindsight. The best
policy on one episode is a maximum over seventeen tries on a single sample; it
has a selection bias the size of the menu and no standard error at all. The
surface is the honest object: it says what every alternative did, so the
question "is `hold` reliably better than `sell_100` after extreme stress" can be
asked across many episodes, where it has a denominator.

WHAT THIS BUYS THAT A BACKTEST DOES NOT
=======================================
A backtest scores the strategy that was run. The surface scores the decision
against the alternatives available at the same moment on the same information,
which is the only comparison from which R4's attribution can be computed. You
cannot call something an action-mapping failure until you can show that a
different action on the SAME beliefs would have done better — and that requires
the counterfactual, not the P&L.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from backend.services.research_gym import episode as EP
from backend.services.research_gym.policies import (DEFAULT_COST_BPS,
                                                    POLICY_MENU, PolicyResult,
                                                    run_policy)

#: FALLBACK ONLY, and known to be wrong. Kept so the classifier still runs when
#: no matched null is available, and labelled UNCALIBRATED wherever it is used.
#:
#: WHY IT IS WRONG (G1, measured 2026-08-15). This gate was supposed to stop the
#: classifier calling a 4bp difference a failure. It was never checked against
#: what a blameless decision actually scores under this denominator. Measured:
#: **P(an always-HOLD decision showing more than 1.0pp regret) = 0.931.** So the
#: gate passed 93% of neutral holds through to a failure label, and 27 of the 28
#: HOLDs in dataset zero were classified as failures by construction rather than
#: by measurement. The real bar is a percentile of the state-and-action-matched
#: null (`regret.failure_threshold_pct`), which at VIX>=35 for a full sell is
#: **35pp, not 1pp**.
MATERIAL_EDGE_PCT = 1.0

#: A DIFFERENT question that happens to use the same number: how much of a gap
#: between two policies' costs on the SAME window counts as the cost mattering.
#: That is a direct comparison of two measured quantities, not a comparison
#: against a null, so it does not inherit G1. Separated from `MATERIAL_EDGE_PCT`
#: so that recalibrating the failure gate cannot silently move it.
MATERIAL_COST_GAP_PCT = 1.0


@dataclass
class ResponseSurface:
    """Every policy's outcome for one episode. The whole thing, always."""
    episode_id: str
    security: str
    decision_ts: str
    horizon_days: int
    taken_policy: str
    results: dict[str, PolicyResult] = field(default_factory=dict)
    cost_bps: float = DEFAULT_COST_BPS

    @property
    def taken(self) -> PolicyResult | None:
        return self.results.get(self.taken_policy)

    def ranked(self, objective=None) -> list[PolicyResult]:
        """Order the surface UNDER A NAMED OBJECTIVE.

        FOUND 2026-08-15 (P0.5). This sorted on `net_return_pct` and nothing
        else, so "the best counterfactual" silently meant "the highest raw
        terminal return" — out of a menu containing `buy_25` and `buy_50`, i.e.
        1.25x and 1.5x leverage. In an up window the levered arm wins by
        construction, and every attribution label computed against the winner
        inherited an objective nobody had declared.

        `objective` may be an `utility.Objective`, its name, or None. None
        keeps the historical behaviour — raw net return — because changing the
        default would silently restate published numbers; what changes is that
        the choice is now named on every record that uses it.

        A distribution objective (expected-log growth) is REFUSED here: ranking
        one episode by log wealth reproduces the raw-return order exactly,
        because log is monotonic. See `utility.score_one`.
        """
        from backend.services.research_gym import utility as U

        if objective is None:
            return sorted(self.results.values(), key=lambda r: -r.net_return_pct)
        obj = (U.get_objective(objective) if isinstance(objective, str)
               else objective)
        scored = []
        for r in self.results.values():
            s = U.score_one(obj, U.stats_of(r))
            if s is not None:
                scored.append((s, r))
        sign = -1.0 if obj.higher_is_better else 1.0
        return [r for _, r in sorted(scored, key=lambda t: sign * t[0])]

    def best(self, objective=None) -> PolicyResult | None:
        r = self.ranked(objective)
        return r[0] if r else None

    def objective_used(self, objective=None) -> str:
        """What `ranked`/`best` were computed under. Goes on every record."""
        if objective is None:
            return "total_return (implicit — raw net return, the historical "\
                   "default)"
        return objective if isinstance(objective, str) else objective.name

    def regret_pct(self) -> float | None:
        """Best available minus what was done. AN UPPER BOUND, NOT A MEASUREMENT.

        "Never negative by construction" — which was the original docstring —
        is the tell. This is a maximum over the whole menu minus one member of
        it, so a decision-maker with no skill scores large positive values:
        measured at roughly +5pp for always-HOLD and +17pp for a full sell
        after VIX>=35. Use `regret.regret_triple()` for a number that can
        exonerate as well as convict.
        """
        b, t = self.best(), self.taken
        if b is None or t is None:
            return None
        return b.net_return_pct - t.net_return_pct

    def as_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "security": self.security,
            "decision_ts": self.decision_ts,
            "horizon_days": self.horizon_days,
            "taken_policy": self.taken_policy,
            "cost_bps": self.cost_bps,
            # WHICH OBJECTIVE RANKED THIS. Mission rule 3: every ranked
            # comparison names the objective it was computed under. Before
            # 2026-08-15 this record contained a ranking and no such name.
            "objective_used": self.objective_used(),
            "regret_vs_ex_post_best_pct": self.regret_pct(),
            "regret_vs_ex_post_best_note":
                "UPPER BOUND — max over the menu minus the action taken. Has a "
                "large positive null (G1). Not comparable across states or "
                "actions without `regret.regret_triple`.",
            # The full surface, sorted for readability but complete. Truncating
            # to a top-N here would quietly turn the record into a leaderboard.
            "surface": [
                {"policy": r.name,
                 "net_return_pct": round(r.net_return_pct, 4),
                 "gross_return_pct": round(r.gross_return_pct, 4),
                 "cost_pct": round(r.cost_pct, 4),
                 "turnover": round(r.turnover, 4),
                 "first_divergence_day": r.first_divergence_day}
                for r in self.ranked()],
        }


def taken_policy_name(ep: EP.DecisionEpisode) -> str:
    """Map the action actually taken onto the menu, or refuse.

    Refusing matters: an episode whose action has no counterpart in the menu
    cannot be compared to the menu, and silently mapping it to the nearest
    entry would make the regret number describe a decision nobody made.
    """
    after = round(float(ep.exposure_after), 4)
    for name, level in (("hold", 1.0), ("sell_25", 0.75), ("sell_50", 0.5),
                        ("sell_100", 0.0), ("buy_25", 1.25), ("buy_50", 1.5)):
        if abs(after - level) < 1e-6:
            return name
    raise ValueError(
        f"exposure_after={after} matches no menu policy; add one rather than "
        f"rounding the decision to something that was not taken")


def replay(ep: EP.DecisionEpisode, daily_returns: Sequence[float], *,
           policies: Sequence[str] | None = None,
           cost_bps: float = DEFAULT_COST_BPS) -> ResponseSurface:
    """One episode against the whole policy menu."""
    names = list(policies or POLICY_MENU.keys())
    taken = taken_policy_name(ep)
    if taken not in names:
        names.append(taken)

    taken_path = [float(x) for x in
                  POLICY_MENU[taken](list(daily_returns), {})]
    surface = ResponseSurface(
        episode_id=ep.episode_id, security=ep.security,
        decision_ts=ep.decision_ts, horizon_days=len(daily_returns),
        taken_policy=taken, cost_bps=cost_bps)
    for name in names:
        surface.results[name] = run_policy(
            name, daily_returns, start_exposure=ep.exposure_before,
            taken_exposure_path=taken_path, cost_bps=cost_bps,
            ctx={"state": ep.state})
    return surface


# ── R4: where the decision actually went wrong ──────────────────────────────

def _direction_belief(ep: EP.DecisionEpisode) -> float | None:
    b = ep.beliefs
    if b.p_up is not None:
        return b.p_up
    if b.p_down is not None:
        return 1.0 - b.p_down
    return None


@dataclass(frozen=True)
class Attribution:
    """A classification, its regret in all three denominators, and its strength.

    Returned as an object rather than `(mode, detail)` because the tuple was
    exactly the shape that let the regret number travel without its
    denominator, which is how G1 survived a review: `+26.5pp` reads as a
    measurement of the engine right up until you ask what a blameless decision
    scores, and the tuple never had anywhere to put that answer.
    """
    mode: str
    detail: str
    regret: "object | None" = None          # regret.RegretTriple
    evidence_strength: str = ""
    #: The bar this episode was judged against, and where the bar came from.
    threshold_pct: float | None = None
    threshold_provenance: str = ""


def attribute(ep: EP.DecisionEpisode, surface: ResponseSurface,
              realised_return_pct: float,
              base_rate=None, *, matched_null=None,
              state_key: str | None = None) -> Attribution:
    """Classify one resolved episode into the R4 taxonomy.

    THE CENTRAL DISTINCTION, and the reason the surface had to exist first:

      * If the beliefs pointed the wrong way, the perception failed. No policy
        choice rescues a wrong view of the world, and calling that a policy
        problem would send the fix to the wrong layer.

      * If the beliefs pointed the RIGHT way and a different action on those
        same beliefs would have done materially better, perception was fine and
        the POLICY LAYER converted it into the wrong action. That is
        `action_mapping_failure`, and it is the finding the timing backtest has
        been sitting on: stress detection worked, and the map from "high stress"
        to "zero exposure" was wrong.

    The refinements below only apply once action-mapping is established, and
    they are ordered from most to least specific:

      * a policy that differs from the one taken ONLY in when it returns to the
        market is a `timing_failure`;
      * one that differs only in how much is a `sizing_failure`;
      * a gross edge eaten by turnover is a `cost_failure`.

    Returns `(mode, detail)`. Never guesses: an episode with no beliefs is
    `UNCLASSIFIED`, because "we do not know what it believed" is not the same
    fact as "its belief was wrong".
    """
    from backend.services.research_gym import regret as RG

    taken, best = surface.taken, surface.best()
    if taken is None or best is None:
        return Attribution(EP.UNCLASSIFIED, "no counterfactual surface")

    triple = RG.regret_triple(surface, state_key=state_key,
                              matched_null=matched_null)
    regret = triple.vs_ex_post_best

    def _out(mode: str, detail: str, strength: str = "") -> Attribution:
        return Attribution(mode=mode, detail=detail, regret=triple,
                           evidence_strength=strength,
                           threshold_pct=threshold,
                           threshold_provenance=threshold_note)

    # THE BAR IS THE NULL, NOT A ROUND NUMBER.
    #
    # "Within 1pp of the best of seventeen" sounded conservative and was the
    # opposite: a blameless hold clears 1pp 93% of the time, so the old gate
    # convicted almost everything it saw. The bar now moves with the state and
    # the action, because 3pp of regret after a VIX-50 panic and 3pp in a calm
    # market are not the same claim.
    threshold, threshold_note = RG.failure_threshold_pct(
        triple.null_cell, fallback_pct=MATERIAL_EDGE_PCT)
    if regret < threshold:
        return _out(EP.NO_FAILURE,
                    f"regret {regret:.2f}pp against the ex-post best does not "
                    f"clear {threshold:.2f}pp — {threshold_note}"
                    + ("" if triple.excess_vs_matched_null is None else
                       f". Excess over the matched null: "
                       f"{triple.excess_vs_matched_null:+.2f}pp"))

    # Cost first: it is the only mode where the gross decision was RIGHT and the
    # implementation ate it, and testing it later would let a turnover problem
    # be misfiled as a timing one.
    if (taken.gross_return_pct >= best.gross_return_pct - MATERIAL_COST_GAP_PCT
            and taken.cost_pct > best.cost_pct + MATERIAL_COST_GAP_PCT):
        return _out(EP.COST_FAILURE,
                    f"gross was competitive ({taken.gross_return_pct:.2f}pp vs "
                    f"{best.gross_return_pct:.2f}pp) and turnover cost "
                    f"{taken.cost_pct:.2f}pp against {best.cost_pct:.2f}pp")

    p_up = _direction_belief(ep)
    if p_up is None:
        return _out(EP.UNCLASSIFIED,
                    f"regret {regret:.2f}pp, but the episode carries no "
                    f"directional belief, so a wrong VIEW and a wrong ACTION "
                    f"cannot be separated — and assuming either would invent "
                    f"the finding")

    expected_up = p_up > 0.5
    actual_up = realised_return_pct > 0
    if expected_up != actual_up:
        # UNLUCKY, OR WRONG IN A WAY THE DATA ALREADY KNEW?
        #
        # Splitting these is the difference between a fixable defect and noise.
        # Without the base rate, every de-risking decision followed by a rally
        # lands in `forecast_failure` BY CONSTRUCTION — which is what the first
        # dataset-zero run did, producing a label that was true and told nobody
        # anything. The state's own history is the only pre-outcome evidence
        # available about whether the expectation was reasonable at the time.
        if base_rate is not None:
            from backend.services.research_gym import base_rate as BR
            a = BR.assess(p_up, base_rate)
            n_eff = ("unknown" if a.n_effective is None
                     else f"{a.n_effective:.1f}")
            if a.disagrees is True:
                return _out(EP.STATE_TO_FORECAST_FAILURE,
                            f"the state was read correctly "
                            f"({base_rate.state_key}) and the expectation "
                            f"drawn from it contradicted that state's own "
                            f"history: P(up) believed {p_up:.2f}, historical "
                            f"P(up | {base_rate.state_key}) = "
                            f"{base_rate.p_up:.2f} over n={base_rate.n} "
                            f"(n_effective {n_eff}, {base_rate.horizon_days}d),"
                            f" realised {realised_return_pct:+.2f}%. "
                            f"Perception was fine; the inference from state to "
                            f"expected return was wrong, and it was wrong "
                            f"before the outcome was known. EVIDENCE "
                            f"{a.strength.upper()}: {a.detail}",
                            strength=a.strength)
            if a.disagrees is None:
                return _out(EP.FORECAST_FAILURE,
                            f"believed P(up)={p_up:.2f}, realised "
                            f"{realised_return_pct:+.2f}% — and the base rate "
                            f"for {base_rate.state_key} is too thin "
                            f"(n={base_rate.n}, n_effective {n_eff}) to say "
                            f"whether the view was unreasonable at the time",
                            strength=a.strength)
            return _out(EP.FORECAST_FAILURE,
                        f"believed P(up)={p_up:.2f}, consistent with the "
                        f"state's own history (P(up | {base_rate.state_key}) = "
                        f"{base_rate.p_up:.2f}, n={base_rate.n}, n_effective "
                        f"{n_eff}), and the realised return was "
                        f"{realised_return_pct:+.2f}% — an unlucky draw rather "
                        f"than a fixable inference", strength=a.strength)
        return _out(EP.FORECAST_FAILURE,
                    f"believed P(up)={p_up:.2f} and the "
                    f"{surface.horizon_days}-day return was "
                    f"{realised_return_pct:+.2f}% — the world went the other "
                    f"way. NO BASE RATE was supplied, so whether this was "
                    f"unlucky or systematically miscalibrated is UNKNOWN")

    # Beliefs were directionally right, and the action still cost materially.
    # That is the policy layer, and the sub-mode says which knob.
    same_family = best.name.startswith(taken.name.split("_reenter")[0])
    reentry = "reenter" in best.name or "scale_in" in best.name
    if reentry and same_family:
        return _out(EP.TIMING_FAILURE,
                    f"direction was right (P(up)={p_up:.2f}, realised "
                    f"{realised_return_pct:+.2f}%) and {best.name} beat "
                    f"{taken.name} by {regret:.2f}pp using the same direction "
                    f"with a different re-entry moment")
    if reentry:
        return _out(EP.TIMING_FAILURE,
                    f"direction was right and the best alternative "
                    f"({best.name}) differs by when it returns to the market: "
                    f"+{regret:.2f}pp")
    if best.name in ("sell_25", "sell_50", "buy_25", "buy_50", "hold") and \
            taken.name in ("sell_25", "sell_50", "sell_100", "buy_25",
                           "buy_50", "hold"):
        return _out(EP.SIZING_FAILURE,
                    f"direction was right (P(up)={p_up:.2f}, realised "
                    f"{realised_return_pct:+.2f}%) and the best alternative "
                    f"{best.name} differs from {taken.name} only in HOW MUCH: "
                    f"+{regret:.2f}pp")
    return _out(EP.ACTION_MAPPING_FAILURE,
                f"beliefs were directionally correct (P(up)={p_up:.2f}, "
                f"realised {realised_return_pct:+.2f}%) and {best.name} beat "
                f"the action taken ({taken.name}) by {regret:.2f}pp — "
                f"perception was right and the policy layer converted it into "
                f"the wrong action")


def attribute_in_place(ep: EP.DecisionEpisode, surface: ResponseSurface,
                       base_rate=None, *, matched_null=None,
                       state_key: str | None = None) -> EP.DecisionEpisode:
    """Classify and write the mode onto the episode. Requires an outcome."""
    if not ep.is_resolved:
        ep.failure_mode = EP.UNCLASSIFIED
        ep.failure_detail = "unresolved — no outcome attached yet"
        return ep
    assert ep.outcome is not None
    a = attribute(ep, surface, float(ep.outcome.realised_return_pct or 0.0),
                  base_rate=base_rate, matched_null=matched_null,
                  state_key=state_key)
    ep.failure_mode, ep.failure_detail = a.mode, a.detail
    ep.evidence_strength = a.evidence_strength
    # The triple, never a scalar — see `DecisionEpisode.regret`.
    ep.regret = {} if a.regret is None else a.regret.as_dict()
    return ep
