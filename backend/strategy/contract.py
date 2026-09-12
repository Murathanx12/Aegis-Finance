"""THE STRATEGY CONTRACT -- one named, versioned, executable object for "what a book IS".

WHY THIS FILE EXISTS
====================
`docs/EXTERNAL_2026-09-07_FIVE_REPOS.md` section 7, read against this repo:
every one of the five external repos -- including the two with no evidence and
the one with no trading in it -- has a single executable contract for a
strategy and one command that runs it end to end in front of someone who was
not in the session. freqtrade has `IStrategy` + `freqtrade backtesting`;
Vibe-Trading has `SignalEngine.generate` + `backtest/runner.py`; TradingAgents
has `TradingAgentsGraph.propagate` returning a typed `PortfolioDecision`.

Aegis had none. A strategy was spread across an arena book YAML, a frozen
contract in the terminal repo, a farm preset, a composite weight table and a
selector function, with no interface a new mechanism had to implement. That is
why a new mechanism costs a session instead of a file, and it is the stated
reason five months of guardrails moved the demonstrated edge by zero: the
guardrails guard a PROCESS, not a TYPE.

WHAT THIS IS NOT
================
It is **not** a new engine. `run_one` WRAPS the machinery that already exists
(`learner.growth_lab`, `backend.services.portfolio_farm`,
`backend.services.arena.policies`) and does not reimplement a single return.
The acceptance test for the whole block is that the composite arena book and
the growth-book champion, expressed through this contract, reproduce the
numbers on their existing sealed receipts.

WHY COSTS ARE A CONSTRUCTOR REFUSAL AND NOT A FIELD WITH A DEFAULT
==================================================================
`CostModel` does not re-implement the zero-cost refusal -- it CONSTRUCTS a
`portfolio_farm.Policy` and lets `PolicyError` out. There is exactly one place
in this repository that decides whether a frictionless run is admissible, and a
second copy of that decision is a second place for it to drift. The
`zero_cost_diagnostic` flag travels into the strategy fingerprint and onto
every result row, exactly as it travels into `policy_id`.

WHY THE LADDER IS A CURVE AND NOT TWO SCALARS
=============================================
`HoldRule.roi_ladder` is freqtrade's `minimal_roi` shape (section 3 of the
external review): `{periods_held: min_profit}`, resolved by
`max(k for k in table if k <= held)`. "I want 8%, but after 5 sessions I will
take 2%" is more expressive AND more testable than a fixed horizon, and the
`exit_priority` tuple removes the ambiguity when a stop and a signal fire on
the same bar. Declared here as DATA so it can be hashed, diffed and searched.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Any, Mapping


class StrategyError(ValueError):
    """The strategy asks for something the contract cannot express."""


class Licence(str, Enum):
    """`CLAUDE.md` THREE LICENCES. Every artefact names one."""

    PRODUCT_EXPERIMENT = "PRODUCT_EXPERIMENT"
    CAPITAL_CANDIDATE = "CAPITAL_CANDIDATE"
    RESEARCH_CLAIM = "RESEARCH_CLAIM"


#: Typed exit reasons, in the order they are RESOLVED when several fire on the
#: same bar. freqtrade's documented ladder (`interface.py:1419-1522`), which is
#: the part Aegis lacked: it already had typed exit reasons and no ranking, so
#: a bar on which a stop and a signal both fired resolved differently in paper
#: and in replay. First match wins; the order is part of the fingerprint.
DEFAULT_EXIT_PRIORITY: tuple[str, ...] = (
    "THESIS_INVALIDATED",              # the signal said sell
    "EXPLICIT_EVENT_STRATEGY_EXIT",
    "STOP",
    "ROI_LADDER",
    "TRAILING_STOP",
    "DEADLINE",                        # horizon reached
    "REBALANCE",                       # dropped out on a scheduled pass
)

KNOWN_WEIGHTING = ("ew", "vw", "inverse_vol", "rank", "ce_kelly")
#: `threshold_coverage` was added 2026-09-12 for lane B's abstention book
#: (`docs/research_notes/2026-09-12/spec_first_books.md` §D.3): the book holds
#: its declared fallback (cash, or an index) unless a name's signal clears a
#: threshold, so COVERAGE is the decision and top-k is only what happens once
#: coverage is non-empty. It is a new ALLOWED VALUE, not a new field -- adding a
#: field to `Construction` would change the fingerprint of every book ever
#: written, and a fingerprint is what tells two sessions they are looking at the
#: same strategy. The threshold and the fallback ride in `Strategy.engine_params`
#: (`{"abstain": {"min_signal": ..., "min_names": ..., "fallback": "CASH"}}`),
#: which is already part of the hash. The spec's synthetic-`CASH_OR_SPY`
#: workaround still works and is no longer required.
KNOWN_CONSTRUCTION = ("top_k", "composite_top_k", "rank_weight", "passthrough",
                      "threshold_coverage")

#: The TWO RULERS. A ranked comparison names the objective it was computed
#: under, or it is not a ranked comparison.
KNOWN_OBJECTIVE = (
    "alpha_intercept",                       # the CLAIMS ruler
    "terminal_wealth_at_drawdown_budget",    # the PRODUCT ruler
    "sharpe",
    "rank_ic",
)


#: `CostModel` fields added AFTER the first books were fingerprinted, with the
#: value every prior book implicitly had. `Strategy.fingerprint` drops them at
#: that value; see its docstring and `Policy._HASH_NEUTRAL_DEFAULTS`, which
#: does the same job for `policy_id`. Two mechanisms because the two hashes are
#: over two different records, and one shared helper would have to know both.
_COSTS_HASH_NEUTRAL_DEFAULTS = {"curve": "flat", "flat_bps": None}


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Universe:
    """WHICH NAMES COULD HAVE BEEN BOUGHT -- the denominator of every stage.

    `floor_dollar_vol_usd` is the execution floor
    ([[apply-the-execution-floor-before-believing-the-book]]): it existed for
    months as `TRADABLE_DOLLAR_VOL` and books were graded without it.
    """

    name: str
    source: str = ""
    floor_dollar_vol_usd: float | None = None
    min_price_usd: float | None = None
    max_names: int | None = None
    fingerprint: str | None = None
    note: str = ""


@dataclass(frozen=True)
class Signal:
    """WHAT IS RANKED. One book, one alpha source.

    `CLAUDE.md` THE BOTTLENECK: a new mechanism arrives as its OWN book, never
    as a weight in `arena_composite`. `run_one` never folds two signals; a
    blend is a declared construction with both parents named in `parents`.
    """

    name: str
    column: str | None = None
    direction: int = 1                 # +1 buy the high end, -1 buy the low end
    source: str = ""
    warmup_periods: int = 0            # freqtrade `startup_candle_count`
    note: str = ""

    def __post_init__(self) -> None:
        if self.direction not in (1, -1):
            raise StrategyError(f"direction must be +1 or -1, got {self.direction!r}")


@dataclass(frozen=True)
class Construction:
    """HOW A RANK BECOMES WEIGHTS.

    Stage three, where the transfer coefficient was measured to fall to 0.13
    (roadmap amendment section 0).
    """

    rule: str = "top_k"
    k: int = 12
    weighting: str = "ew"
    max_single_name: float = 0.20
    hysteresis_rank: int | None = None       # hold until rank > this
    gross_cap: float = 1.0
    note: str = ""

    def __post_init__(self) -> None:
        if self.rule not in KNOWN_CONSTRUCTION:
            raise StrategyError(f"unknown construction rule {self.rule!r}; "
                                f"declared: {list(KNOWN_CONSTRUCTION)}")
        if self.weighting not in KNOWN_WEIGHTING:
            raise StrategyError(f"unknown weighting {self.weighting!r}; "
                                f"declared: {list(KNOWN_WEIGHTING)}")
        if self.k < 1:
            raise StrategyError("k must be >= 1")
        if not 0.0 <= self.max_single_name <= 1.0:
            raise StrategyError("max_single_name must be in [0, 1]")


@dataclass(frozen=True)
class HoldRule:
    """WHEN IT LEAVES.

    Stage four, where turnover fell 0.90 -> 0.53 by holding alone.
    `roi_ladder` is `{periods_held: min_profit_ratio}` -- freqtrade's
    `minimal_roi`, resolved by the largest key <= periods held. `{}` disables
    it. `exit_priority` is the RANKING, not a menu.
    """

    horizon_periods: int = 21
    min_hold_periods: int = 0
    roi_ladder: Mapping[int, float] = field(default_factory=dict)
    stop_loss: float | None = None            # negative ratio, e.g. -0.08
    trailing_stop: float | None = None
    exit_priority: tuple[str, ...] = DEFAULT_EXIT_PRIORITY
    scheduled_review_periods: int | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.horizon_periods < 1:
            raise StrategyError("horizon_periods must be >= 1")
        if self.min_hold_periods < 0:
            raise StrategyError("min_hold_periods must be >= 0")
        if self.stop_loss is not None and self.stop_loss >= 0:
            raise StrategyError(
                f"stop_loss is a NEGATIVE ratio (e.g. -0.08); got {self.stop_loss}. "
                "A positive value here reads as a stop already breached at entry, "
                "which would exit every position on its first bar.")
        for k in self.roi_ladder:
            if int(k) < 0:
                raise StrategyError("roi_ladder keys are periods held, >= 0")
        unknown = [r for r in self.exit_priority if r not in DEFAULT_EXIT_PRIORITY]
        if unknown:
            raise StrategyError(
                f"exit reasons {unknown} are not typed. An untyped exit cannot be "
                f"attributed, and exit attribution by typed reason is required on "
                f"every receipt (invariant 17). Declared: "
                f"{list(DEFAULT_EXIT_PRIORITY)}")

    def roi_floor_at(self, periods_held: int) -> float | None:
        """The ROI the ladder will accept after `periods_held`.

        None when no rung has matured -- NOT 0.0, which would read as "take any
        profit" and is the difference between a ladder that has not started and
        a ladder that has run out.
        """
        keys = [int(k) for k in self.roi_ladder if int(k) <= int(periods_held)]
        if not keys:
            return None
        return float(self.roi_ladder[max(keys)])


@dataclass(frozen=True)
class Sizing:
    """HOW MUCH.

    The engine bounds the sizer; the sizer does not bound itself (freqtrade
    `custom_stake_amount`, external review section 3(c)).
    """

    rule: str = "equal_weight"
    gross_cap: float = 1.0
    notional_usd: float = 10_000.0
    overlays: tuple[str, ...] = ()      # e.g. ("dd", "bsc")
    params: Mapping[str, Any] = field(default_factory=dict)
    note: str = ""

    def __post_init__(self) -> None:
        if self.gross_cap <= 0:
            raise StrategyError("gross_cap must be > 0")


@dataclass(frozen=True)
class CostModel:
    """COSTS ARE NEVER ZERO -- and the refusal is `portfolio_farm.Policy`'s.

    Constructing this object constructs a Policy purely so that the ONE
    zero-cost refusal in the repository is the one that fires. If that refusal
    ever changes, this changes with it, which is the point.
    """

    transaction_cost_bps: float = 5.0     # one way
    slippage_bps: float = 1.0
    financing_bps_over_rf: float = 0.0
    borrow_bps: float = 0.0
    zero_cost_diagnostic: bool = False
    note: str = ""
    #: WHICH COST RULER: "flat" | "taq_empirical" | "retail_paper". Appended
    #: LAST and defaulting to "flat", which `Policy._HASH_NEUTRAL_DEFAULTS`
    #: omits from the hash at that value -- so `Strategy.fingerprint`, which is
    #: a SHA-256 over the whole record, is unchanged for every strategy that
    #: does not ask for a curve. Pinned by test.
    curve: str = "flat"
    #: Only meaningful when `curve == "flat"`; kept so that a receipt written
    #: before the curve existed can still state the rate it was graded at even
    #: after a re-grade writes a second receipt beside it.
    flat_bps: float | None = None

    def __post_init__(self) -> None:
        # DELEGATED, not re-implemented. See the class docstring. The curve
        # travels into the delegation too, so the ONE zero-cost refusal fires
        # under whichever ruler is declared.
        from backend.services.portfolio_farm.policy import Policy

        Policy(transaction_cost_bps=float(self.transaction_cost_bps),
               slippage_bps=float(self.slippage_bps),
               zero_cost_diagnostic=bool(self.zero_cost_diagnostic),
               curve=str(self.curve))

    @property
    def round_trip_bps(self) -> float:
        """The DECLARED flat round trip. Under a non-flat curve the charged
        rate is per fill; the realised average lands on the result row as
        `mean_realised_cost_bps`."""
        return 2.0 * (float(self.transaction_cost_bps) + float(self.slippage_bps))

    def as_row(self) -> dict:
        """The flag TRAVELS. Every result row carries it, so a frictionless
        number can never be quoted as net -- and so does the CURVE, so a net
        computed under a per-name ruler can never be read as a flat one."""
        return {
            "transaction_cost_bps_per_side": float(self.transaction_cost_bps),
            "slippage_bps": float(self.slippage_bps),
            "round_trip_bps": self.round_trip_bps,
            "financing_bps_over_rf": float(self.financing_bps_over_rf),
            "borrow_bps": float(self.borrow_bps),
            "zero_cost_diagnostic": bool(self.zero_cost_diagnostic),
            "cost_curve": str(self.curve),
        }


@dataclass(frozen=True)
class Benchmark:
    """WHAT IT IS GRADED AGAINST.

    Beta is printed FIRST on every book, so the benchmark is part of the
    contract rather than a reporting choice.
    [[an-EW-average-against-a-VW-market-is-the-regime]]:
    `is_own_universe_average` is admissible only as a DIAGNOSTIC and says so on
    the row.
    """

    name: str = "SPY"
    series_key: str = "spy_tr"
    beta_matched: bool = True
    levered_at_budget: bool = False
    is_own_universe_average: bool = False


@dataclass(frozen=True)
class Objective:
    """THE RULER. Two of them, and the row names which."""

    name: str = "alpha_intercept"
    periods_per_year: int = 12
    drawdown_budget: float | None = None      # e.g. -0.35, aggressive personality
    utility: str = "risk_adjusted"
    note: str = ""

    def __post_init__(self) -> None:
        if self.name not in KNOWN_OBJECTIVE:
            raise StrategyError(f"unknown objective {self.name!r}; "
                                f"declared: {list(KNOWN_OBJECTIVE)}")
        if self.name == "terminal_wealth_at_drawdown_budget" and self.drawdown_budget is None:
            raise StrategyError(
                "the product ruler is 'terminal wealth AT A DRAWDOWN BUDGET'; "
                "without `drawdown_budget` it is just terminal wealth, which "
                "ranks the most levered book first every time.")
        if self.drawdown_budget is not None and self.drawdown_budget >= 0:
            raise StrategyError("drawdown_budget is a NEGATIVE ratio")


@dataclass(frozen=True)
class LossBudget:
    """INVARIANT 19: declared BEFORE the first position.

    An idea is retired by its book's scoreboard, never by its own first loss.
    """

    positions_judged: int
    expected_losers: int
    note: str = ""

    def __post_init__(self) -> None:
        if self.positions_judged < 1:
            raise StrategyError("positions_judged must be >= 1")
        if not 0 <= self.expected_losers <= self.positions_judged:
            raise StrategyError(
                f"expected_losers {self.expected_losers} must be in "
                f"[0, {self.positions_judged}]. A budget that cannot be spent "
                "is not a budget.")

    def scoreboard(self, *, losers_so_far: int, positions_so_far: int) -> dict:
        return {
            "positions_judged_at": self.positions_judged,
            "expected_losers": self.expected_losers,
            "positions_so_far": int(positions_so_far),
            "losers_so_far": int(losers_so_far),
            "budget_left": int(self.expected_losers - losers_so_far),
            "retired_by_scoreboard": bool(losers_so_far > self.expected_losers),
        }


@dataclass(frozen=True)
class Window:
    """The period the book is run over, and whether it is SEALED.

    `sealed` is not decoration. `run_one` REFUSES a sealed window unless the
    caller passes an explicit authorisation, because a sealed era is opened
    once per frozen champion against an append-only ledger and a verification
    re-run is still a look.
    """

    start: str
    end: str
    label: str = ""
    sealed: bool = False
    periods_per_year: int = 12


@dataclass(frozen=True)
class Strategy:
    """ONE BOOK, COMPLETE, HASHED.

    Every field is a DECLARED choice, as in `portfolio_farm.Policy`: no field's
    value is inferred from the data it will be graded on.
    """

    strategy_id: str
    title: str
    universe: Universe
    signal: Signal
    construction: Construction
    hold: HoldRule
    sizing: Sizing
    costs: CostModel
    benchmark: Benchmark
    objective: Objective
    loss_budget: LossBudget
    licence: Licence = Licence.PRODUCT_EXPERIMENT
    #: Which existing machine runs it. `run_one` dispatches on this; it never
    #: contains a return calculation of its own.
    engine: str = "series"
    engine_params: Mapping[str, Any] = field(default_factory=dict)
    parents: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if not self.strategy_id:
            raise StrategyError("strategy_id is the identity; it cannot be empty")
        if self.licence is not Licence.PRODUCT_EXPERIMENT and not self.note:
            raise StrategyError(
                f"a {self.licence.value} book must say in `note` which evidence "
                "standard it is claiming under. PRODUCT_EXPERIMENT is the only "
                "licence that needs no argument.")

    # ------------------------------------------------------------- identity
    def as_dict(self) -> dict:
        d = asdict(self)
        d["licence"] = self.licence.value
        d["hold"]["roi_ladder"] = {str(k): float(v)
                                   for k, v in sorted(self.hold.roi_ladder.items())}
        return d

    @property
    def fingerprint(self) -> str:
        """SHA-256 over the WHOLE record, 16 hex -- the width the arena and the
        farm both use. A drifted parameter is a different strategy.

        FIELDS ADDED AFTER THE FIRST BOOKS WERE HASHED are dropped AT THEIR
        DEFAULT, for the reason `KNOWN_CONSTRUCTION`'s comment gives: a new
        field changes the fingerprint of every book ever written, and a
        fingerprint is what tells two sessions they are looking at the same
        strategy. At any other value the field hashes normally, so a
        `curve="taq_empirical"` re-run of a promoted flat book is a NEW
        strategy and never a silent edit of the promoted one.
        """
        d = self.as_dict()
        costs = dict(d.get("costs") or {})
        for k, default in _COSTS_HASH_NEUTRAL_DEFAULTS.items():
            if k in costs and costs[k] == default:
                costs.pop(k)
        d["costs"] = costs
        return _sha(d)[:16]

    @property
    def label(self) -> str:
        cost = ("FREE" if self.costs.zero_cost_diagnostic
                else f"{self.costs.round_trip_bps:.0f}bp")
        return (f"{self.signal.name}/{self.construction.rule}k{self.construction.k}/"
                f"{self.construction.weighting}/h{self.hold.horizon_periods}/{cost}")

    def with_(self, **kw) -> "Strategy":
        """A MUTATION IS A NEW STRATEGY, never an edit.

        Same shape as `dataclasses.replace`, named so the call site reads as a
        fork rather than an assignment.
        """
        return replace(self, **kw)

    def as_row(self) -> dict:
        return {"strategy_id": self.strategy_id,
                "fingerprint": self.fingerprint,
                "label": self.label,
                "licence": self.licence.value,
                "engine": self.engine,
                **self.costs.as_row()}


def loss_budget_worst_case(strategy: Strategy, *, n_names: int,
                           notional_pct: float, equity_usd: float) -> dict:
    """SESSION PROTOCOL RULE 4, as a function instead of a habit.

    On 28 Aug twelve names x 25% = 300% gross and a 3% stop cost -9%; the "fix"
    that widened the stop raised the worst case to -24%. Wider stops on
    uncapped gross are bigger losses, so the gross line is printed beside the
    stop line and neither is quoted alone.
    """
    stop = abs(strategy.hold.stop_loss) if strategy.hold.stop_loss is not None else None
    gross = float(n_names) * float(notional_pct)
    out = {
        "n_names": int(n_names),
        "notional_pct_per_name": float(notional_pct),
        "gross_over_equity": gross,
        "gross_cap_declared": float(strategy.sizing.gross_cap),
        "gross_within_cap": bool(gross <= float(strategy.sizing.gross_cap) + 1e-12),
        "stop_pct": stop,
    }
    if stop is None:
        out["worst_case_usd"] = None
        out["worst_case_pct_of_equity"] = None
        out["verdict"] = ("CANNOT DETERMINE -- no stop declared, so the worst case "
                          "is the whole gross exposure, not a stop-bounded loss")
        return out
    loss_pct = gross * stop
    out["worst_case_pct_of_equity"] = loss_pct
    out["worst_case_usd"] = -abs(loss_pct * float(equity_usd))
    out["verdict"] = (f"{n_names} names x {notional_pct:.0%} x {stop:.0%} stop = "
                      f"{loss_pct:.2%} of equity; gross {gross:.2f}x")
    return out
