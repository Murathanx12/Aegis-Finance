"""Terminal wealth under a DECLARED utility — not raw return, not accuracy.

WHY THIS MODULE EXISTS (P0.5, ordered 2026-08-15)
==================================================
The mission says the objective is *"terminal wealth under a declared utility,
risk-adjusted or deliberately risk-seeking by declared choice"*. The Gym was
measuring something else and saying so nowhere:

    def ranked(self):
        return sorted(self.results.values(), key=lambda r: -r.net_return_pct)

`PolicyResult` carried return, cost and turnover. No drawdown, no minimum
wealth, no time under water, no utility. So "the best counterfactual" meant
"the highest raw terminal return" — out of a menu that includes `buy_25` and
`buy_50`, i.e. 1.25x and 1.5x leverage. In a rising window the levered arm wins
by construction, every attribution label computed against it inherits that, and
nothing in the record said which objective had been used.

**We were measuring System A while aiming at System B.**

WHAT IS *NOT* CLAIMED — the correction that matters
====================================================
It would be wrong to declare the existing tensor invalid. `REGRET_TENSOR`
already reports `mean_edge_vs_default` — the action minus a pre-declared HOLD —
and says in its own header that this is the quantity answering its question.
That number never went through `best()`. The `sell_100` result vs HOLD is a
**raw-return result against a declared default**, not an artefact of a
best-of-17 ranking.

The honest statement is narrower and more useful:

    The raw-return tensor is not invalid. It is INCOMPLETE relative to the
    objective we actually hold.

So nothing here overwrites anything. A dimension is added.

THE TRAP, MADE UNREPRESENTABLE RATHER THAN DOCUMENTED
======================================================
The obvious implementation is a `utility_score` property returning
`log(final_wealth)`. It would change **no ranking whatsoever**, because log is
monotonic in terminal wealth: whenever W_a > W_b, log W_a > log W_b. A per-path
log utility is raw return wearing a different hat, and the resulting "utility
tensor" would agree with the return tensor everywhere and be reported as
confirmation.

Expected-log / Kelly behaviour only produces different rankings when it is
evaluated **across a distribution of episodes** or along a sequential wealth
process — because there the concavity bites on the SPREAD, which is exactly
what it is for.

Objectives therefore declare their `kind`:

  * ``path``          scores one episode's trajectory. May reorder within a
                      single episode: drawdown, time under water, downside
                      deviation and ruin breaches are properties of the route,
                      not the endpoint.
  * ``distribution``  scores a SET of episodes. `score_one` **raises** for
                      these. That is the trap turned into an exception.

BREAK-EVEN RISK AVERSION INSTEAD OF A VERDICT
==============================================
`break_even_gamma` answers "*at what risk aversion does this choice flip?*"
rather than "*was selling wrong?*". The second is a claim that depends on an
undeclared utility; the first is a number that tells four personalities apart
in one measurement, and it can be reported even where neither policy's edge
clears its own MDE — because it is a statement about preferences, not about
significance. It is still governed by §19 when it is used to make a claim: a
gamma* estimated on three effective episodes is a gamma* with an interval wider
than the range of plausible gammas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

from backend.services.research_gym.policies import PolicyResult

#: Trading days per year, for annualising path statistics. Matches the rest of
#: the repo (`tearsheet.TRADING_DAYS`, `factorial_pm.M2_TRADING_DAYS`).
TRADING_DAYS = 252

#: Wealth below which an episode is a RUIN BREACH rather than a bad outcome.
#: 0.40 = a 60% drawdown from the decision point. Declared, not tuned: the
#: point of a ruin constraint is that it is a constraint, so it must not be
#: fitted to make a favoured policy pass.
RUIN_FLOOR = 0.40


class ObjectiveMisuse(RuntimeError):
    """A distribution objective was asked to score a single episode."""


# ── path statistics ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PathStats:
    """What the route did, as opposed to where it ended.

    Every field is `None` rather than `0.0` when it could not be measured. A
    downside deviation of 0.0 means "no down days"; `None` means "not enough
    path to say", and the two must never print the same.
    """
    n_days: int
    terminal_wealth: float
    min_wealth: float
    net_return_pct: float
    realised_vol_pct: float | None
    downside_deviation_pct: float | None
    max_drawdown_pct: float
    max_drawdown_days: int
    time_under_water_frac: float
    worst_day_pct: float | None
    worst_week_pct: float | None
    expected_shortfall_5_pct: float | None
    recovery_days: int | None
    ruin: bool

    def as_dict(self) -> dict:
        def _r(x, n=4):
            return None if x is None else round(float(x), n)
        return {
            "n_days": self.n_days,
            "terminal_wealth": _r(self.terminal_wealth, 6),
            "min_wealth": _r(self.min_wealth, 6),
            "net_return_pct": _r(self.net_return_pct),
            "realised_vol_pct": _r(self.realised_vol_pct),
            "downside_deviation_pct": _r(self.downside_deviation_pct),
            "max_drawdown_pct": _r(self.max_drawdown_pct),
            "max_drawdown_days": self.max_drawdown_days,
            "time_under_water_frac": _r(self.time_under_water_frac),
            "worst_day_pct": _r(self.worst_day_pct),
            "worst_week_pct": _r(self.worst_week_pct),
            "expected_shortfall_5_pct": _r(self.expected_shortfall_5_pct),
            "recovery_days": self.recovery_days,
            "ruin": self.ruin,
        }


def path_stats(wealth_path: Sequence[float], *,
               ruin_floor: float = RUIN_FLOOR) -> PathStats | None:
    """Path risk from a net wealth path that starts at 1.0 on day 0.

    Returns None for an empty path rather than a zero-filled record: an
    unmeasured path and a flat one are different facts, and the whole reason
    this module exists is that a summary statistic hid which one it was.
    """
    w = [float(x) for x in wealth_path]
    if not w:
        return None
    n = len(w)
    prev = [1.0] + w[:-1]
    daily = [(a / b - 1.0) if b > 0 else 0.0 for a, b in zip(w, prev)]

    peak, max_dd, cur_uw, max_uw, uw_days = 1.0, 0.0, 0, 0, 0
    dd_end_idx = None
    for i, x in enumerate(w):
        if x >= peak:
            peak, cur_uw = x, 0
        else:
            cur_uw += 1
            uw_days += 1
            max_uw = max(max_uw, cur_uw)
        dd = (peak - x) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd, dd_end_idx = dd, i

    # Recovery: days from the trough back to the prior peak, or None if the
    # path ends still under water. None is the informative answer — "it had not
    # recovered by the end of the window" is not a large number, it is an
    # unknown one.
    recovery = None
    if dd_end_idx is not None:
        peak_before = max(w[:dd_end_idx + 1])
        for j in range(dd_end_idx + 1, n):
            if w[j] >= peak_before:
                recovery = j - dd_end_idx
                break

    vol = None
    dd_dev = None
    if n > 1:
        m = sum(daily) / n
        var = sum((r - m) ** 2 for r in daily) / (n - 1)
        vol = math.sqrt(var * TRADING_DAYS) * 100.0
        down = [r for r in daily if r < 0.0]
        # Downside deviation is taken about ZERO, not about the mean: the
        # quantity a loss-averse investor cares about is deviation below a
        # target, and using the sample mean as the target makes a policy look
        # safer precisely because it lost money on average.
        dsq = sum(r * r for r in down) / (n - 1)
        dd_dev = math.sqrt(dsq * TRADING_DAYS) * 100.0

    weekly = None
    if n >= 5:
        weekly = min((w[i + 4] / w[i - 1] - 1.0) if i > 0 else (w[i + 4] - 1.0)
                     for i in range(0, n - 4))

    es = None
    if n >= 20:
        tail = sorted(daily)[:max(1, int(round(0.05 * n)))]
        es = 100.0 * sum(tail) / len(tail)

    return PathStats(
        n_days=n,
        terminal_wealth=w[-1],
        min_wealth=min(w),
        net_return_pct=(w[-1] - 1.0) * 100.0,
        realised_vol_pct=vol,
        downside_deviation_pct=dd_dev,
        max_drawdown_pct=max_dd * 100.0,
        max_drawdown_days=max_uw,
        time_under_water_frac=uw_days / n,
        worst_day_pct=(min(daily) * 100.0) if daily else None,
        worst_week_pct=(weekly * 100.0) if weekly is not None else None,
        expected_shortfall_5_pct=es,
        recovery_days=recovery,
        ruin=min(w) <= float(ruin_floor),
    )


def stats_of(res: PolicyResult, *, ruin_floor: float = RUIN_FLOOR
             ) -> PathStats | None:
    return path_stats(res.wealth_path, ruin_floor=ruin_floor)


# ── the objective interface ─────────────────────────────────────────────────

@dataclass(frozen=True)
class Objective:
    """A declared utility. Every ranked comparison must name one."""
    name: str
    #: "path" scores one episode; "distribution" scores a set of them.
    kind: str
    description: str
    #: path objectives: PathStats -> float
    path_fn: Callable[[PathStats], float] | None = None
    #: distribution objectives: Sequence[PathStats] -> float
    dist_fn: Callable[[Sequence[PathStats]], float] | None = None
    #: per-episode contribution for a distribution objective, so an edge vs a
    #: default still has a per-episode difference and therefore an SE and an
    #: MDE. Its EXISTENCE is not permission to rank on it — see `score_one`.
    contribution_fn: Callable[[PathStats], float] | None = None
    higher_is_better: bool = True
    units: str = "pct"

    def __post_init__(self):
        if self.kind not in ("path", "distribution"):
            raise ValueError(f"unknown objective kind {self.kind!r}")
        if self.kind == "path" and self.path_fn is None:
            raise ValueError(f"{self.name}: a path objective needs path_fn")
        if self.kind == "distribution" and self.dist_fn is None:
            raise ValueError(f"{self.name}: needs dist_fn")


def score_one(obj: Objective, stats: PathStats | None) -> float | None:
    """Score a SINGLE episode. Refuses for distribution objectives.

    This refusal is the point of the module. `log(final_wealth)` on one path
    ranks identically to `final_wealth`, so a per-episode expected-log
    "utility" would reproduce the return ranking exactly and be read as
    confirmation that the objective does not matter.
    """
    if obj.kind == "distribution":
        raise ObjectiveMisuse(
            f"{obj.name} is a DISTRIBUTION objective and cannot score one "
            f"episode. Log utility is monotonic in terminal wealth, so a "
            f"per-path expected-log score reproduces the raw-return ranking "
            f"exactly — it would agree with total_return everywhere and be "
            f"reported as agreement rather than as the tautology it is. "
            f"Expected-log growth is a property of the episode DISTRIBUTION; "
            f"use score_many(). Path risk (drawdown, ruin, time under water) "
            f"is what reorders a single trajectory.")
    if stats is None:
        return None
    return float(obj.path_fn(stats))


def score_many(obj: Objective, stats: Sequence[PathStats | None]
               ) -> float | None:
    """Score a set of episodes under either kind of objective."""
    xs = [s for s in stats if s is not None]
    if not xs:
        return None
    if obj.kind == "distribution":
        return float(obj.dist_fn(xs))
    vals = [float(obj.path_fn(s)) for s in xs]
    return sum(vals) / len(vals)


def contribution(obj: Objective, stats: PathStats | None) -> float | None:
    """The per-episode quantity whose MEAN is (or drives) the objective.

    For path objectives that is the score itself. For distribution objectives
    it is `contribution_fn` — log wealth for expected-log growth — which exists
    so a cell can carry an SE and an MDE. It is deliberately NOT reachable
    through `score_one`.
    """
    if stats is None:
        return None
    if obj.kind == "path":
        return float(obj.path_fn(stats))
    if obj.contribution_fn is None:
        return None
    return float(obj.contribution_fn(stats))


# ── the declared objectives ─────────────────────────────────────────────────

def _total_return(s: PathStats) -> float:
    return s.net_return_pct


def _sortino(s: PathStats) -> float:
    """Annualised return over downside deviation. A PATH objective.

    Reorders a single trajectory, which log utility cannot: two paths ending at
    the same wealth score differently if one got there through a 30% drawdown.
    """
    if s.downside_deviation_pct is None or s.downside_deviation_pct <= 1e-9:
        # No down days at all. Not infinity — an unbounded score would make one
        # lucky episode dominate any average it enters.
        return s.net_return_pct
    ann = ((s.terminal_wealth ** (TRADING_DAYS / max(s.n_days, 1))) - 1.0) * 100.0
    return ann / s.downside_deviation_pct


def _log_wealth(s: PathStats) -> float:
    # Wealth is floored before the log so a wiped-out path is a very negative
    # number rather than a crash. A path AT zero is ruin, and ruin's utility is
    # the floor's, not negative infinity — infinities propagate through means
    # and turn one episode into the whole answer.
    return math.log(max(s.terminal_wealth, 1e-6))


def _expected_log_growth(xs: Sequence[PathStats]) -> float:
    return sum(_log_wealth(s) for s in xs) / len(xs)


def _log_growth_with_ruin(xs: Sequence[PathStats]) -> float:
    """Expected log growth, with any ruin breach scored AT the floor.

    A constraint, not a penalty term: an episode that breached is not allowed
    to be compensated by how well it finished afterwards. That is the whole
    difference between a drawdown you sat through and a drawdown you could not
    have sat through.
    """
    vals = [math.log(RUIN_FLOOR) if s.ruin else _log_wealth(s) for s in xs]
    return sum(vals) / len(vals)


def _log_growth_ruin_contribution(s: PathStats) -> float:
    return math.log(RUIN_FLOOR) if s.ruin else _log_wealth(s)


def aggressive_growth(dd_lambda: float = 0.15,
                      ruin_floor: float = RUIN_FLOOR) -> Objective:
    """Deliberately risk-SEEKING, with ruin still terminal. NOT the default.

    The mission allows a declared risk-seeking utility, and Murat's own
    declared preference is growth-first. Risk-seeking is not the same as
    indifferent to ruin: a path that goes through the floor cannot compound out
    of it, so the constraint stays while the volatility penalty is set low
    enough to prefer a bumpy winner over a smooth also-ran.

    Parameterised rather than pinned so the four personalities are four
    configurations of one function, and so this one is never mistaken for the
    public default.
    """
    def fn(s: PathStats) -> float:
        if s.min_wealth <= ruin_floor:
            return -100.0
        return s.net_return_pct - dd_lambda * s.max_drawdown_pct
    return Objective(
        name=f"aggressive_growth_lambda{dd_lambda:g}", kind="path",
        description=("net return with a small drawdown penalty and a hard ruin "
                     "constraint; declared risk-seeking, not the public "
                     "default"),
        path_fn=fn, units="pct")


TOTAL_RETURN = Objective(
    name="total_return", kind="path",
    description=("net terminal return. The objective every ranked comparison "
                 "in the Gym was silently computed under before 2026-08-15."),
    path_fn=_total_return, units="pct")

SORTINO = Objective(
    name="sortino", kind="path",
    description=("annualised return over downside deviation about zero; a "
                 "PATH objective, so it can reorder a single episode"),
    path_fn=_sortino, units="ratio")

def drawdown_penalised(dd_lambda: float) -> Objective:
    """Net return minus `dd_lambda` x maximum drawdown.

    A WARNING ATTACHED TO THE FUNCTION THAT PRODUCES THE PROBLEM. At
    `dd_lambda = 1.0` this objective's optimum is **cash**, in almost every
    state, for a reason that has nothing to do with markets: a zero-exposure
    policy has zero return AND zero drawdown, so it scores ~0, while any long
    policy whose drawdown exceeds its return scores below zero. Measured on the
    real corpus, that produced thirteen "material" utility flips, every one of
    them `buy_50 -> sell_100`, and every one of them an artefact of the penalty
    weight rather than a preference being revealed.

    It is kept, declared, and flagged (`UtilityTensor.degenerate_objectives`)
    rather than deleted or quietly retuned: an objective whose argmax is cash
    everywhere is a specification error, and the way to prevent the next one is
    to be able to detect it, not to remove this example of it.
    """
    return Objective(
        name=f"drawdown_penalised_lambda{dd_lambda:g}", kind="path",
        description=f"net return minus {dd_lambda:g} x maximum drawdown",
        path_fn=lambda s: s.net_return_pct - dd_lambda * s.max_drawdown_pct,
        units="pct")


DRAWDOWN_PENALISED = drawdown_penalised(1.0)
DRAWDOWN_PENALISED_LIGHT = drawdown_penalised(0.25)

EXPECTED_LOG_GROWTH = Objective(
    name="expected_log_growth", kind="distribution",
    description=("mean log terminal wealth ACROSS episodes — Kelly. Refuses "
                 "to score one episode, because log is monotonic in terminal "
                 "wealth and a per-path version is raw return renamed."),
    dist_fn=_expected_log_growth, contribution_fn=_log_wealth, units="log")

LOG_GROWTH_WITH_RUIN = Objective(
    name="log_growth_with_ruin_constraint", kind="distribution",
    description=("expected log growth with any ruin breach scored at the "
                 f"floor ({RUIN_FLOOR:g}); breaching is not compensable"),
    dist_fn=_log_growth_with_ruin,
    contribution_fn=_log_growth_ruin_contribution, units="log")

# ── the four personalities ──────────────────────────────────────────────────
# "One brain, several personalities" (mission §0, rule 3). `aggressive_growth`
# already said the four should be four configurations of one function; until
# 2026-08-16 only one of them existed, so three quarters of the declared
# objective surface was unreachable by name and G3 could not be end-to-end
# authoritative.
#
# WHAT THESE NUMBERS ARE, HONESTLY: a declared preference LADDER, not an
# elicited or fitted one. The ordering (preservation penalises drawdown most,
# extreme growth least) is the content; the specific lambdas are conventions
# standing in until Murat's own risk preference is elicited properly. They are
# named and frozen so that a ranked comparison can cite one, which is the thing
# that was missing — not because 0.60 is known to be right.
#
# All four keep ruin terminal. Risk-seeking is a statement about volatility,
# never about survival: a path through the floor cannot compound out of it.
#
# None exceeds dd_lambda = 1.0, where the optimum is cash everywhere — see
# `drawdown_penalised`. Preservation sits deliberately below that cliff, since
# a "preservation" objective whose argmax is cash in every state would be a
# specification error wearing the right name.

def personality(name: str, dd_lambda: float,
                ruin_floor: float = RUIN_FLOOR) -> Objective:
    """One of the declared personalities. Four configurations, one function."""
    def fn(s: PathStats) -> float:
        if s.min_wealth <= ruin_floor:
            return -100.0
        return s.net_return_pct - dd_lambda * s.max_drawdown_pct
    return Objective(
        name=name, kind="path",
        description=(f"declared personality {name!r}: net return minus "
                     f"{dd_lambda:g} x maximum drawdown, ruin terminal at "
                     f"{ruin_floor:g}"),
        path_fn=fn, units="pct")


PRESERVATION = personality("preservation", 0.60)
BALANCED = personality("balanced", 0.30)
AGGRESSIVE = personality("aggressive", 0.15)
EXTREME_GROWTH = personality("extreme_growth", 0.05)

#: Ordered least to most risk-tolerant. Anything iterating the personalities
#: should use this rather than re-listing them, so adding a fifth cannot leave
#: a caller silently covering four.
PERSONALITIES: tuple[Objective, ...] = (PRESERVATION, BALANCED, AGGRESSIVE,
                                        EXTREME_GROWTH)

#: The declared set. Named and stable, because objective names end up in
#: lineage rows exactly as policy names do.
OBJECTIVES: dict[str, Objective] = {
    o.name: o for o in (*PERSONALITIES,
                        TOTAL_RETURN, SORTINO, DRAWDOWN_PENALISED,
                        DRAWDOWN_PENALISED_LIGHT,
                        EXPECTED_LOG_GROWTH, LOG_GROWTH_WITH_RUIN,
                        aggressive_growth())
}


def get_objective(name: str) -> Objective:
    if name not in OBJECTIVES:
        raise KeyError(
            f"unknown objective {name!r}; declared: {sorted(OBJECTIVES)}")
    return OBJECTIVES[name]


# ── break-even risk aversion ────────────────────────────────────────────────

def crra_utility(wealth: float, gamma: float) -> float:
    """CRRA utility of terminal wealth. gamma=0 is risk-neutral, 1 is log."""
    w = max(float(wealth), 1e-6)
    if abs(gamma - 1.0) < 1e-9:
        return math.log(w)
    return (w ** (1.0 - gamma) - 1.0) / (1.0 - gamma)


def expected_crra(wealths: Sequence[float], gamma: float) -> float:
    xs = [float(w) for w in wealths]
    return sum(crra_utility(w, gamma) for w in xs) / len(xs)


def break_even_gamma(a_wealths: Sequence[float], b_wealths: Sequence[float],
                     *, lo: float = 0.0, hi: float = 30.0,
                     tol: float = 1e-4) -> float | None:
    """The risk aversion at which two policies are exactly indifferent.

    Reported INSTEAD of "selling was wrong". "Selling was wrong" is a claim
    about an undeclared utility; "de-risking is worse below gamma* = 3.1 and
    better above it" is the same evidence stated so that four personalities can
    read their own answer off it.

    Returns None when one policy is preferred at every gamma in the searched
    range — which is itself the finding, and a stronger one than a crossing.
    """
    a = [float(w) for w in a_wealths]
    b = [float(w) for w in b_wealths]
    if not a or not b or len(a) != len(b):
        return None

    def diff(g: float) -> float:
        return expected_crra(a, g) - expected_crra(b, g)

    d_lo, d_hi = diff(lo), diff(hi)
    # INDIFFERENT AT BOTH ENDS IS NOT A CROSSING (found 2026-08-15 by the
    # paired-resampling test, which fed two IDENTICAL policies and got
    # gamma* = 0.0 back). The first version returned `lo` whenever the
    # difference at `lo` was exactly zero, so two policies that are equally
    # good everywhere reported a break-even risk aversion of zero — a
    # preference reversal manufactured out of a tie. In a bootstrap that turns
    # into "a crossing exists in 100% of resamples", which is precisely the
    # confidence the interval was added to withhold.
    if abs(d_lo) < tol and abs(d_hi) < tol:
        return None
    if abs(d_lo) < tol:
        return lo                        # genuine boundary crossing at gamma=lo
    if (d_lo > 0) == (d_hi > 0):
        return None                      # no crossing in range: dominance
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        d_mid = diff(mid)
        if abs(d_mid) < tol or (hi - lo) < tol:
            return mid
        if (d_mid > 0) == (d_lo > 0):
            lo, d_lo = mid, d_mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ── bootstrap intervals, because gamma* without one is a number ─────────────

def bootstrap_gamma_star(a_wealths: Sequence[float], b_wealths: Sequence[float],
                         *, n_boot: int = 400, seed: int = 20260815,
                         lo_q: float = 5.0, hi_q: float = 95.0,
                         block: int = 1) -> dict:
    """Resampled interval for `break_even_gamma`, plus how often it exists.

    A point estimate of gamma* invites exactly the reading SS19 exists to
    prevent: 0.35 and 2.86 look like a large difference between two states
    until you learn that both intervals span [0, 30]. Episodes are resampled in
    PAIRS so the two policies are always compared on the same drawn windows —
    resampling them independently would add a difference that is not in the
    data.

    `block` IS NOT OPTIONAL IN PRACTICE. The episodes are overlapping forward
    windows: with a 252-day horizon sampled every 5 days, consecutive entries
    share 247 of their 252 days. An i.i.d. resample of those treats each as a
    fresh draw and returns an interval far too tight — the same inflated-n
    error as §41, arriving through the resampler instead of through the
    denominator. A MOVING-BLOCK bootstrap with `block = horizon / stride`
    keeps the overlap intact.
    """
    import numpy as np

    a = [float(w) for w in a_wealths]
    b = [float(w) for w in b_wealths]
    if not a or len(a) != len(b) or len(a) < 3:
        return {"point": None, "lo": None, "hi": None, "n_boot": 0,
                "frac_crossing": None, "block": int(block)}
    rng = np.random.default_rng(seed)
    n = len(a)
    L = max(1, min(int(block), n))
    n_blocks = max(1, -(-n // L))            # ceil
    gs: list[float] = []
    n_none = 0
    for _ in range(int(n_boot)):
        if L == 1:
            idx = rng.integers(0, n, size=n)
        else:
            starts = rng.integers(0, max(1, n - L + 1), size=n_blocks)
            idx = np.concatenate([np.arange(s, s + L) for s in starts])[:n]
        g = break_even_gamma([a[i] for i in idx], [b[i] for i in idx])
        if g is None:
            n_none += 1
        else:
            gs.append(g)
    point = break_even_gamma(a, b)
    if not gs:
        return {"point": point, "lo": None, "hi": None, "n_boot": int(n_boot),
                "frac_crossing": 0.0, "block": L}
    return {
        "point": point,
        "lo": float(np.percentile(gs, lo_q)),
        "hi": float(np.percentile(gs, hi_q)),
        "n_boot": int(n_boot),
        # How often a crossing existed at all. A low number means "one policy
        # usually dominates outright", which is a different statement from a
        # wide interval and must not be averaged into one.
        "frac_crossing": 1.0 - n_none / float(n_boot),
        "block": L,
    }
