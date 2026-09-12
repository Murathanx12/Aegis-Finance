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

#: The declared cost regimes. `flat` is the historical behaviour: one scalar
#: rate for every name. `taq_empirical` prices each fill from the TAQ
#: effective-spread panel plus a square-root impact term. `retail_paper` is a
#: DIFFERENT market (Alpaca/IEX fills) and is refused by the CRSP replay.
KNOWN_CURVES = ("flat", "taq_empirical", "retail_paper")

#: FIELDS ADDED AFTER THE FIRST POLICIES WERE HASHED, with the value every
#: prior policy implicitly had. At that value the field is OMITTED from
#: `policy_id`, so a receipt written in August still reproduces its own
#: identity today; at any other value it is included, so two curves are two
#: policies.
#:
#: This is not a convenience. `policy_id` is a SHA-256 over `asdict`, so
#: appending a field to the dataclass changes the hash of EVERY policy ever
#: written, and every archived receipt's identity silently stops matching the
#: code that produced it -- the exact "drifted parameter, same identity"
#: failure this class exists to prevent, arriving from the other direction.
#: Pinned by `test_portfolio_farm_policy.py` against a real archived row.
_HASH_NEUTRAL_DEFAULTS = {"curve": "flat", "decay": 0.0}


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
    #: WHICH COST RULER. `flat` charges `transaction_cost_bps + slippage_bps`
    #: on every name alike; `taq_empirical` charges each fill its own
    #: half-effective-spread plus square-root impact at its own participation
    #: rate (`backend/services/cost_curve.py`). Under a non-flat curve the two
    #: flat fields are IGNORED FOR PRICING and kept only so a receipt written
    #: under `flat` still reproduces.
    #:
    #: Appended LAST on purpose: a field inserted mid-record would shift every
    #: positional construction, and this one has to be invisible to everything
    #: that does not ask for it. Default `flat` is hash-neutral
    #: (`_HASH_NEUTRAL_DEFAULTS`).
    curve: str = "flat"
    #: DECAY-BLENDED TARGET WEIGHTS. `w_t = decay * w_{t-1} + (1 - decay) *
    #: target_t`, renormalised to the book's gross exposure after blending.
    #: Lambda in [0, 1); 0.0 is no blending, which is every policy ever written
    #: before this field existed, so it is hash-neutral at its default and the
    #: blending branch does not execute at all.
    #:
    #: It is a COST-CONTROL parameter and belongs on the same axis as
    #: `fee_bps`: a book that half-remembers last rebalance trades less, and
    #: whether that is worth the tracking error is an empirical question the
    #: farm can answer only if the two are swept together. Reported against its
    #: own `decay=0` twin at the same cost, never alone.
    decay: float = 0.0

    def __post_init__(self):
        if self.signal not in SIGNALS:
            from .signals import DEPRECATED_ALIASES
            renamed = DEPRECATED_ALIASES.get(self.signal)
            if renamed:
                # REFUSED, not silently resolved. A Policy is a frozen hashed
                # strategy record, so rewriting its signal field here would
                # produce a policy whose hash does not match the receipt it
                # came from — a reproducibility problem wearing a convenience.
                # Naming the replacement makes the fix one edit long.
                raise PolicyError(
                    f"signal {self.signal!r} was RENAMED to {renamed!r} on "
                    f"2026-08-25 and is no longer a policy-declarable name. "
                    f"Scoring every name equally does not produce an "
                    f"equal-weight book — it produces the sort's tie-break, "
                    f"and that tie-break is permno order, i.e. LISTING AGE. "
                    f"The holdings are unchanged; the name now says what they "
                    f"are. Use {renamed!r}, and see `newest_listing` for the "
                    f"opposite-tail control.")
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
        if self.curve not in KNOWN_CURVES:
            raise PolicyError(
                f"unknown cost curve {self.curve!r}; declared: "
                f"{list(KNOWN_CURVES)}. A curve name the engine does not know "
                f"would price every fill at the flat rate while the receipt "
                f"said otherwise.")
        if float(self.transaction_cost_bps) < 0 or float(self.slippage_bps) < 0:
            raise PolicyError("a negative cost pays the book to trade")
        # THE ZERO-COST REFUSAL, UNDER WHICHEVER RULER IS DECLARED. Under a
        # curve the two flat fields are unused, so asking them whether this
        # book pays anything answers a different question -- and a curve whose
        # every rate happened to floor at exactly 0 (a regression gone wrong, a
        # panel of zeros) is precisely the bug this refusal exists to catch.
        if self.curve == "flat":
            cost = float(self.transaction_cost_bps) + float(self.slippage_bps)
        else:
            from backend.services import cost_curve as CC
            cost = float(CC.curve_floor_one_way_bps(self.curve))
            if self.zero_cost_diagnostic:
                raise PolicyError(
                    f"zero_cost_diagnostic=True with curve={self.curve!r} is "
                    f"two contradictory declarations: a frictionless "
                    f"diagnostic is curve='flat' with the flag, and a measured "
                    f"curve is never frictionless. Pick one.")
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
        if not 0.0 <= float(self.decay) < 1.0:
            # 1.0 is excluded deliberately: at lambda = 1 the blend never lets
            # a new target in, so the book freezes at its first formation and
            # the signal stops mattering -- a strategy with no signal, wearing
            # the signal's policy_id.
            raise PolicyError(
                f"decay must be in [0, 1), got {self.decay}. At 1.0 the blend "
                f"never admits a new target and the book freezes at its first "
                f"formation, which is a different strategy wearing this one's "
                f"identity.")

    @property
    def round_trip_bps(self) -> float:
        """The DECLARED flat round trip. Under a non-flat curve this is not
        what the book pays -- the realised rate is per fill and lands on the
        receipt as `mean_realised_cost_bps`. Kept unchanged because every
        archived row keys on it."""
        return 2.0 * (float(self.transaction_cost_bps) + float(self.slippage_bps))

    @property
    def policy_id(self) -> str:
        """SHA-256 over the WHOLE record. Not a name, not a counter: a name can
        be reused for a changed rule and a counter says nothing about what
        changed. Sixteen hex characters is the same width the arena uses.

        Fields in `_HASH_NEUTRAL_DEFAULTS` are omitted AT THEIR DEFAULT so that
        a policy written before the field existed still hashes to the identity
        its receipt records. Any other value is hashed normally, so two curves
        are two policies.
        """
        rec = {k: v for k, v in asdict(self).items()
               if k not in _HASH_NEUTRAL_DEFAULTS
               or v != _HASH_NEUTRAL_DEFAULTS[k]}
        blob = json.dumps(rec, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    @property
    def label(self) -> str:
        """Human-readable, and deliberately NOT the identity."""
        if self.curve != "flat":
            cost = self.curve
        else:
            cost = ("FREE" if self.zero_cost_diagnostic
                    else f"{self.round_trip_bps:.0f}bp")
        seed = f"#{self.signal_seed}" if self.signal_seed else ""
        ph = f"p{self.phase_offset}" if self.phase_offset else ""
        if self.decay:
            cost = f"{cost}/d{self.decay:g}"
        return (f"{self.signal}{seed}/h{self.holding_days}{ph}/k{self.top_k}/"
                f"{self.sizing[:3]}/u{self.universe_n}/{cost}")

    def as_row(self) -> dict:
        """`cost_curve` rides on every row. A gross/net pair with no rate
        between them is the C2 shape: a level with no way to check what
        produced it."""
        return {"policy_id": self.policy_id, "label": self.label,
                "cost_curve": self.curve, **asdict(self)}


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
        """THE REALISED RATE SITS BETWEEN GROSS AND NET.

        `total_cost_usd / traded_notional_usd` was derivable before; the
        NOTIONAL-WEIGHTED MEAN of the per-fill rate is a different number
        whenever the curve is non-flat, and reporting only one invites exactly
        the averaging-methodology confusion `taq_calibration.py` needed two
        sections for. Both are here, and so is the provenance mix, because a
        book that is 80% measured and 20% extrapolated must print both counts.
        """
        d = self.diagnostics or {}
        return {**self.policy.as_row(), **self.metrics,
                "mean_realised_cost_bps": d.get("mean_realised_cost_bps"),
                "cost_curve_provenance": d.get("cost_curve_provenance"),
                "cost_bps_by_liquidity_tercile": d.get(
                    "cost_bps_by_liquidity_tercile"),
                "diagnostics": self.diagnostics}
