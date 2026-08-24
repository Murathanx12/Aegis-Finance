"""A POLICY is the whole strategy, frozen, hashed, and cheap to enumerate.

This is the object the farm searches over and the object that graduates. The
same record that ran as one of six hundred candidates in a replay is the record
that seeds a forward paper book — byte-identical, by `policy_id`. That identity
is what makes "explore dirty, promote clean" safe: exploration may produce a
thousand of these, and the one that promotes cannot have drifted on the way,
because a drifted parameter is a different hash and therefore a different
policy with no history.

WHY COSTS ARE A CONSTRUCTOR REFUSAL AND NOT A DEFAULT
=====================================================
`transaction_cost_bps=0` is the single most common way a backtest lies, and it
lies hardest exactly where the farm is most likely to find something: high
turnover. A 1-day holding period at 12 names is ~500 round trips a year; at 6
bps round trip that is ~3%/yr of drag, which is the difference between most
"discoveries" and nothing. So zero costs is not a default and not a flag you
pass quietly — it requires `zero_cost_diagnostic=True`, which travels into
`policy_id`, onto the leaderboard row, and into the receipt.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from itertools import product

from backend.services.portfolio_farm.signals import SIGNALS

KNOWN_SIZING = ("equal_weight", "inverse_vol", "cap_weight")


class PolicyError(ValueError):
    """The policy asks for something the engine does not implement."""


@dataclass(frozen=True)
class Policy:
    """One virtual portfolio's complete rules.

    Every field is a DECLARED choice. There is no field whose value is inferred
    from the data, because a parameter fitted on the replay and then reported
    from the same replay is the in-sample number this whole package exists to
    avoid producing by accident.
    """
    signal: str = "mom_12_1"
    #: Only consumed by the `random` signal. A null needs a DISTRIBUTION, not a
    #: draw: twelve names picked from five hundred have a terminal-wealth
    #: spread wide enough that beating one random policy means nothing. The
    #: seed is part of `policy_id`, so each draw is its own frozen policy.
    signal_seed: int = 0
    #: Trading days between rebalances. THE MICRON QUESTION: buying and selling
    #: a name every day looked enormously profitable in conversation, and the
    #: only way to find out is to make the holding period a searched axis and
    #: charge for it. 1, 5, 21, 63, 126, 252 span daily to annual.
    holding_days: int = 21
    #: Which session inside the rebalance cycle the book trades on.
    #:
    #: THE MEASUREMENT THAT FORCED THIS FIELD. On 2013-2024 at k=12, 12-1
    #: momentum returned $12,968 at `holding_days=21` and $38,817 at
    #: `holding_days=63` — same signal, same universe, same costs, differing
    #: only in WHICH sessions happened to be formation dates. A 3x swing from
    #: an arbitrary alignment is not a property of the strategy, and a
    #: leaderboard that reports one phase reports one draw from it.
    #:
    #: With the phase declared, a policy can be run at every offset in its
    #: cycle and summarised by the MEDIAN — which is a property of the rule
    #: rather than of the calendar. Part of `policy_id`, so a promoted book
    #: carries the exact phase it was measured at.
    phase_offset: int = 0
    top_k: int = 12
    sizing: str = "equal_weight"
    #: Formation-time liquidity screen: keep the N most liquid eligible names
    #: by trailing dollar volume. Applied with TRAILING data at each formation
    #: date, never once over the whole sample (which would be lookahead).
    universe_n: int = 500
    min_price: float = 5.0
    #: One-way, in basis points. Round trip is twice this plus twice slippage.
    transaction_cost_bps: float = 5.0
    slippage_bps: float = 1.0
    #: What a holding is assumed to fetch when its permno leaves the file. See
    #: panel.py: crsp.dsf carries no delisting return, so this is an explicit
    #: assumption and a sensitivity axis, not a silent -0%.
    delisting_return: float = -0.30
    #: Cap on any single name's weight. 0 disables.
    max_single_name: float = 0.20
    #: Starting capital. $10,000 — Murat's own unit, so a leaderboard row reads
    #: as "this is what the account would say".
    notional_usd: float = 10_000.0
    zero_cost_diagnostic: bool = False
    #: Free-text, carried into the hash so two policies that differ only in
    #: intent are still different policies.
    note: str = ""

    def __post_init__(self):
        if self.signal not in SIGNALS:
            raise PolicyError(
                f"unknown signal {self.signal!r}; declared: {sorted(SIGNALS)}. "
                f"A signal the library cannot compute would rank every name "
                f"NaN and hold nothing, which reads as a flat strategy rather "
                f"than a broken one.")
        if self.sizing not in KNOWN_SIZING:
            raise PolicyError(f"unknown sizing {self.sizing!r}; "
                              f"declared: {list(KNOWN_SIZING)}")
        if self.holding_days < 1:
            raise PolicyError("holding_days must be >= 1")
        if not 0 <= self.phase_offset < max(1, self.holding_days):
            raise PolicyError(
                f"phase_offset {self.phase_offset} is outside the rebalance "
                f"cycle [0, {self.holding_days}). Phases wrap, so an offset "
                f"of {self.holding_days} IS phase 0 wearing a different "
                f"policy_id — two identities for one policy is worse than a "
                f"refusal.")
        if self.top_k < 1:
            raise PolicyError("top_k must be >= 1")
        cost = float(self.transaction_cost_bps) + float(self.slippage_bps)
        if cost <= 0 and not self.zero_cost_diagnostic:
            raise PolicyError(
                "zero transaction cost is not a default. A frictionless run is "
                "a DIAGNOSTIC — it measures how much of a result the costs eat, "
                "which is worth knowing — so it must be declared: pass "
                "zero_cost_diagnostic=True. The flag travels into policy_id and "
                "onto every leaderboard row, so the number can never be quoted "
                "as net.")
        if cost > 0 and self.zero_cost_diagnostic:
            raise PolicyError("zero_cost_diagnostic=True with non-zero costs "
                              "labels a real run as frictionless")
        if not 0.0 <= self.max_single_name <= 1.0:
            raise PolicyError("max_single_name must be in [0, 1]")
        if not -1.0 <= self.delisting_return <= 0.0:
            raise PolicyError("delisting_return must be in [-1, 0]")

    @property
    def round_trip_bps(self) -> float:
        return 2.0 * (float(self.transaction_cost_bps) + float(self.slippage_bps))

    @property
    def policy_id(self) -> str:
        """SHA-256 over the WHOLE record. Not a name, not a counter: a name can
        be reused for a changed rule and a counter says nothing about what
        changed. Sixteen hex characters is the same width the arena uses."""
        blob = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    @property
    def label(self) -> str:
        """Human-readable, and deliberately NOT the identity."""
        cost = "FREE" if self.zero_cost_diagnostic else f"{self.round_trip_bps:.0f}bp"
        seed = f"#{self.signal_seed}" if self.signal_seed else ""
        ph = f"p{self.phase_offset}" if self.phase_offset else ""
        return (f"{self.signal}{seed}/h{self.holding_days}{ph}/k{self.top_k}/"
                f"{self.sizing[:3]}/u{self.universe_n}/{cost}")

    def as_row(self) -> dict:
        return {"policy_id": self.policy_id, "label": self.label, **asdict(self)}


def grid(**axes) -> list[Policy]:
    """Cartesian product of the axes given, defaults elsewhere.

        grid(signal=["mom_12_1", "random"], holding_days=[1, 21])   # 4 policies

    Duplicates by `policy_id` are collapsed, because two axis combinations can
    describe the same policy (top_k=1 with any max_single_name, say) and running
    an identical policy twice would put it on the leaderboard twice and make a
    coincidence look like a cluster.
    """
    if not axes:
        return [Policy()]
    keys = sorted(axes)
    out: dict[str, Policy] = {}
    for combo in product(*(axes[k] for k in keys)):
        p = Policy(**dict(zip(keys, combo)))
        out.setdefault(p.policy_id, p)
    return list(out.values())


@dataclass
class FarmResult:
    """One policy's replay outcome. `nav` is the whole daily series, because a
    terminal number without its path cannot be asked about drawdown, and a
    leaderboard that only kept terminals would have to re-run to answer that."""
    policy: Policy
    dates: list = field(default_factory=list)
    nav: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        return {**self.policy.as_row(), **self.metrics,
                "diagnostics": self.diagnostics}
