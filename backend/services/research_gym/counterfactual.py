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

#: How much better an alternative must be, in percentage points of net return,
#: before the taken action is called a mistake rather than a tie.
#:
#: Not a p-value and not pretending to be one. A single episode cannot support
#: an inference; this threshold exists to stop the classifier labelling a 4bp
#: difference as an "action-mapping failure", which would fill the taxonomy with
#: noise and make the counts meaningless. The real test is whether a mode
#: RECURS across episodes, and that test lives one layer up.
MATERIAL_EDGE_PCT = 1.0


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

    def ranked(self) -> list[PolicyResult]:
        return sorted(self.results.values(),
                      key=lambda r: -r.net_return_pct)

    def best(self) -> PolicyResult | None:
        r = self.ranked()
        return r[0] if r else None

    def regret_pct(self) -> float | None:
        """Best available minus what was done. Never negative by construction."""
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
            "regret_pct": self.regret_pct(),
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


def attribute(ep: EP.DecisionEpisode, surface: ResponseSurface,
              realised_return_pct: float,
              base_rate=None) -> tuple[str, str]:
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
    taken, best = surface.taken, surface.best()
    if taken is None or best is None:
        return EP.UNCLASSIFIED, "no counterfactual surface"

    regret = best.net_return_pct - taken.net_return_pct
    if regret < MATERIAL_EDGE_PCT:
        return (EP.NO_FAILURE,
                f"the action taken was within {MATERIAL_EDGE_PCT:.1f}pp of the "
                f"best available alternative (regret {regret:.2f}pp)")

    # Cost first: it is the only mode where the gross decision was RIGHT and the
    # implementation ate it, and testing it later would let a turnover problem
    # be misfiled as a timing one.
    if (taken.gross_return_pct >= best.gross_return_pct - MATERIAL_EDGE_PCT
            and taken.cost_pct > best.cost_pct + MATERIAL_EDGE_PCT):
        return (EP.COST_FAILURE,
                f"gross was competitive ({taken.gross_return_pct:.2f}pp vs "
                f"{best.gross_return_pct:.2f}pp) and turnover cost "
                f"{taken.cost_pct:.2f}pp against {best.cost_pct:.2f}pp")

    p_up = _direction_belief(ep)
    if p_up is None:
        return (EP.UNCLASSIFIED,
                f"regret {regret:.2f}pp, but the episode carries no directional "
                f"belief, so a wrong VIEW and a wrong ACTION cannot be "
                f"separated — and assuming either would invent the finding")

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
            from backend.services.research_gym.base_rate import \
                disagrees_with_base_rate
            contradicted = disagrees_with_base_rate(p_up, base_rate)
            if contradicted is True:
                return (EP.STATE_TO_FORECAST_FAILURE,
                        f"the state was read correctly ({base_rate.state_key}) "
                        f"and the expectation drawn from it contradicted that "
                        f"state's own history: P(up) believed {p_up:.2f}, "
                        f"historical P(up | {base_rate.state_key}) = "
                        f"{base_rate.p_up:.2f} over n={base_rate.n} "
                        f"({base_rate.horizon_days}d), realised "
                        f"{realised_return_pct:+.2f}%. Perception was fine; the "
                        f"inference from state to expected return was wrong, "
                        f"and it was wrong before the outcome was known")
            if contradicted is None:
                return (EP.FORECAST_FAILURE,
                        f"believed P(up)={p_up:.2f}, realised "
                        f"{realised_return_pct:+.2f}% — and the base rate for "
                        f"{base_rate.state_key} is too thin (n={base_rate.n}) "
                        f"to say whether the view was unreasonable at the time")
            return (EP.FORECAST_FAILURE,
                    f"believed P(up)={p_up:.2f}, consistent with the state's "
                    f"own history (P(up | {base_rate.state_key}) = "
                    f"{base_rate.p_up:.2f}, n={base_rate.n}), and the realised "
                    f"return was {realised_return_pct:+.2f}% — an unlucky draw "
                    f"rather than a fixable inference")
        return (EP.FORECAST_FAILURE,
                f"believed P(up)={p_up:.2f} and the {surface.horizon_days}-day "
                f"return was {realised_return_pct:+.2f}% — the world went the "
                f"other way. NO BASE RATE was supplied, so whether this was "
                f"unlucky or systematically miscalibrated is UNKNOWN")

    # Beliefs were directionally right, and the action still cost materially.
    # That is the policy layer, and the sub-mode says which knob.
    same_family = best.name.startswith(taken.name.split("_reenter")[0])
    reentry = "reenter" in best.name or "scale_in" in best.name
    if reentry and same_family:
        return (EP.TIMING_FAILURE,
                f"direction was right (P(up)={p_up:.2f}, realised "
                f"{realised_return_pct:+.2f}%) and {best.name} beat "
                f"{taken.name} by {regret:.2f}pp using the same direction with "
                f"a different re-entry moment")
    if reentry:
        return (EP.TIMING_FAILURE,
                f"direction was right and the best alternative ({best.name}) "
                f"differs by when it returns to the market: +{regret:.2f}pp")
    if best.name in ("sell_25", "sell_50", "buy_25", "buy_50", "hold") and \
            taken.name in ("sell_25", "sell_50", "sell_100", "buy_25",
                           "buy_50", "hold"):
        return (EP.SIZING_FAILURE,
                f"direction was right (P(up)={p_up:.2f}, realised "
                f"{realised_return_pct:+.2f}%) and the best alternative "
                f"{best.name} differs from {taken.name} only in HOW MUCH: "
                f"+{regret:.2f}pp")
    return (EP.ACTION_MAPPING_FAILURE,
            f"beliefs were directionally correct (P(up)={p_up:.2f}, realised "
            f"{realised_return_pct:+.2f}%) and {best.name} beat the action "
            f"taken ({taken.name}) by {regret:.2f}pp — perception was right and "
            f"the policy layer converted it into the wrong action")


def attribute_in_place(ep: EP.DecisionEpisode, surface: ResponseSurface,
                       base_rate=None) -> EP.DecisionEpisode:
    """Classify and write the mode onto the episode. Requires an outcome."""
    if not ep.is_resolved:
        ep.failure_mode = EP.UNCLASSIFIED
        ep.failure_detail = "unresolved — no outcome attached yet"
        return ep
    assert ep.outcome is not None
    mode, detail = attribute(ep, surface,
                             float(ep.outcome.realised_return_pct or 0.0),
                             base_rate=base_rate)
    ep.failure_mode, ep.failure_detail = mode, detail
    return ep
