"""S7 -- PROTECTIONS AS DATA, evaluated BEFORE entries.

A protection is a portfolio-level circuit breaker declared as data on the
strategy, evaluated before any entry, and it locks ENTRIES ONLY -- never exits.
A guard that could block an exit would be a risk limit that increases risk.

FOUR RULES THIS MODULE ENFORCES IN CODE RATHER THAN IN PROSE
============================================================
1.  **The guard list is never empty by default.** `ProtectionStack()` with no
    protections RAISES. A book that declares no circuit breaker must say so in
    words (`deliberately_unprotected="<why>"`), which puts the sentence on the
    receipt where a reviewer will meet it.
2.  **An unmeasurable input REFUSES; it never assumes flat.** Equity unknown,
    notional unknown, stop unknown -> the guard LOCKS with a
    `CANNOT DETERMINE` reason. A guard derives its inputs or refuses; a guard
    that treats "unknown" as "fine" is a guard that is off exactly when the
    data pipeline is broken.
3.  **The gross line and the stop line are printed together.** SESSION PROTOCOL
    rule 4, at whose cost it was learned: on 2026-08-28 twelve names x 25% =
    300% gross and a 3% stop cost -9%, and the "fix" that widened the stop
    raised the worst case to -24%. A wider stop on uncapped gross is a bigger
    loss, so neither number is ever quoted alone.
4.  **No profile is levered.** Every declared profile's gross cap is <= 1.0,
    asserted by test, because a levered cap turns every other bound into a
    multiple of itself.

THE LIVE PROFILE TABLE
======================
Mirrored from the EXECUTION repo (`aegis-alpha-terminal`), which is a separate
repository and cannot be imported from here; the values are quoted with their
source path so a reader can check them, and `worst_case_pct` is DERIVED from
gross x stop rather than typed in, so the two halves can never disagree.

    profile        gross cap   stop     worst case
    conservative       0.60    3%        1.80%
    aggressive         1.00   10%       10.00%
    maximum            0.60   15%        9.00%
    basket             1.00   12%       12.00%
    convex             1.00    8%        8.00%

PROVENANCE AND LICENCE
======================
The `IProtection` CONTRACT SHAPE -- two methods returning a lock with a
human-readable reason, plus `has_global_stop` / `has_local_stop` flags -- is
freqtrade's design (`freqtrade/plugins/protections/`, **GPL-3.0**) and
OpenAlice's (AGPL-3.0). No code from either is copied, imported or adapted;
the spec was written in English first and is reproduced in
`docs/BUILD_2026-09-08_R5_STRATEGY_PORTS.md` section S7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

CANNOT_DETERMINE = "CANNOT DETERMINE"


class ProtectionError(ValueError):
    """A protection stack that could not be constructed as declared."""


# --------------------------------------------------------------------------
# the live profile table, DERIVED not typed


@dataclass(frozen=True)
class Profile:
    name: str
    gross_cap: float
    stop_fraction: float
    max_notional_per_name: float
    source: str

    @property
    def worst_case_pct(self) -> float:
        """Gross x stop. Both numbers, one line, always."""
        return float(self.gross_cap) * float(self.stop_fraction)

    def as_dict(self) -> dict:
        return {"profile": self.name, "gross_cap": self.gross_cap,
                "stop_fraction": self.stop_fraction,
                "max_notional_per_name": self.max_notional_per_name,
                "worst_case_pct_of_equity": self.worst_case_pct,
                "levered": self.gross_cap > 1.0, "source": self.source}


_SRC = ("aegis-alpha-terminal alpha/engine/sizing.py::GROSS_NOTIONAL_CAP + "
        "alpha/engine/equity.py::{STOP_FRACTION_BY_PROFILE,MAX_NOTIONAL_BY_PROFILE}, "
        "read 2026-09-08")

PROFILES: Mapping[str, Profile] = {
    p.name: p for p in (
        Profile("conservative", 0.60, 0.03, 0.25, _SRC),
        Profile("aggressive", 1.00, 0.10, 0.25, _SRC),
        Profile("maximum", 0.60, 0.15, 0.25, _SRC),
        Profile("basket", 1.00, 0.12, 0.10, _SRC),
        Profile("convex", 1.00, 0.08, 0.10, _SRC),
    )
}


def profile_bounds() -> dict:
    """The five worst cases, derived, for a receipt."""
    return {name: p.as_dict() for name, p in PROFILES.items()}


# --------------------------------------------------------------------------
# the contract


@dataclass(frozen=True)
class BookState:
    """Everything a protection is allowed to see. `None` means UNMEASURED.

    There is no default for equity, notional or stop, deliberately: a default
    would let a broken data pipeline present itself as a flat, safe book.
    """

    equity_usd: float | None = None
    notional_by_name: Mapping[str, float] | None = None
    stop_pct: float | None = None
    realised_pnl_today_usd: float | None = None
    peak_equity_usd: float | None = None
    recent_exits: Sequence[Mapping[str, Any]] = ()
    periods_since_last_exit_by_name: Mapping[str, int] | None = None
    now: Any = None

    @property
    def gross_over_equity(self) -> float | None:
        if not self.equity_usd or self.notional_by_name is None:
            return None
        if self.equity_usd <= 0:
            return None
        return float(sum(abs(float(v)) for v in self.notional_by_name.values())
                     ) / float(self.equity_usd)

    @property
    def n_names(self) -> int | None:
        return None if self.notional_by_name is None else len(self.notional_by_name)


@dataclass(frozen=True)
class ProtectionReturn:
    """A lock decision. `locked=True` blocks ENTRIES ONLY."""

    protection: str
    locked: bool
    reason: str
    scope: str = "global"                 # global | name
    names: tuple[str, ...] = ()
    measured: Mapping[str, Any] = field(default_factory=dict)
    determinable: bool = True

    def as_dict(self) -> dict:
        return {"protection": self.protection, "locked": self.locked,
                "reason": self.reason, "scope": self.scope,
                "names": list(self.names), "measured": dict(self.measured),
                "determinable": self.determinable}


class Protection:
    """Base. `evaluate` returns a `ProtectionReturn`; it never raises on data."""

    name = "protection"
    blocks = "entries"                    # never anything else

    def evaluate(self, state: BookState) -> ProtectionReturn:  # pragma: no cover
        raise NotImplementedError

    def _refuse(self, what: str) -> ProtectionReturn:
        return ProtectionReturn(
            protection=self.name, locked=True, determinable=False,
            reason=(f"{CANNOT_DETERMINE}: {what} is unmeasured, so this guard "
                    f"LOCKS. A guard derives its inputs or refuses -- treating "
                    f"an unknown as flat turns the guard off at precisely the "
                    f"moment the data pipeline is broken."))


# --------------------------------------------------------------------------
# the concrete guards


@dataclass
class GrossExposureCap(Protection):
    """Sum |notional| / equity, evaluated BEFORE the entry that would breach it."""

    gross_cap: float = 1.0
    name: str = "gross_exposure_cap"
    #: A cap above 1.0 is LEVERAGE and needs a sentence, not a number. No
    #: declared fleet PROFILE exceeds 1.0 (asserted by test); a research book
    #: graded against levered SPY at a drawdown budget legitimately does, and
    #: the reason then travels onto the receipt where a human meets it.
    leverage_reason: str | None = None

    def __post_init__(self) -> None:
        if self.gross_cap <= 0:
            raise ProtectionError("gross_cap must be > 0")
        if self.gross_cap > 1.0 and not str(self.leverage_reason or "").strip():
            raise ProtectionError(
                f"gross_cap {self.gross_cap} is LEVERED and carries no reason. "
                f"No declared Aegis fleet profile exceeds 1.0, and a levered "
                f"cap makes every other bound a multiple of itself. Pass "
                f"`leverage_reason='<why>'` so the sentence lands on the "
                f"receipt; leverage is never a silent guard parameter.")

    def evaluate(self, state: BookState) -> ProtectionReturn:
        g = state.gross_over_equity
        if g is None:
            return self._refuse("gross exposure (equity or notional)")
        over = g > float(self.gross_cap) + 1e-12
        return ProtectionReturn(
            protection=self.name, locked=over,
            measured={"gross_over_equity": g, "gross_cap": float(self.gross_cap),
                      "levered": float(self.gross_cap) > 1.0,
                      "leverage_reason": self.leverage_reason,
                      "n_names": state.n_names},
            reason=(f"gross {g:.2f}x vs cap {self.gross_cap:.2f}x"
                    + (f" (LEVERED: {self.leverage_reason})"
                       if self.gross_cap > 1.0 else "")
                    + (" -> ENTRIES LOCKED" if over else " -> within cap")))


@dataclass
class WorstCaseStopBudget(Protection):
    """n x notional% x stop% -- the number SESSION PROTOCOL rule 4 demands."""

    budget_pct_of_equity: float = 0.10
    name: str = "worst_case_stop_budget"

    def evaluate(self, state: BookState) -> ProtectionReturn:
        g = state.gross_over_equity
        if g is None:
            return self._refuse("gross exposure (equity or notional)")
        if state.stop_pct is None or not np.isfinite(float(state.stop_pct)):
            return self._refuse("the stop width")
        stop = abs(float(state.stop_pct))
        worst = g * stop
        over = worst > float(self.budget_pct_of_equity) + 1e-12
        n = state.n_names or 0
        per_name = (g / n) if n else float("nan")
        return ProtectionReturn(
            protection=self.name, locked=over,
            measured={"gross_over_equity": g, "stop_pct": stop,
                      "n_names": n, "notional_pct_per_name": per_name,
                      "worst_case_pct_of_equity": worst,
                      "budget_pct_of_equity": float(self.budget_pct_of_equity),
                      "worst_case_usd": (None if not state.equity_usd
                                         else -abs(worst * float(state.equity_usd)))},
            reason=(f"{n} names x {per_name:.1%} x {stop:.1%} stop = "
                    f"{worst:.2%} of equity (gross {g:.2f}x) vs budget "
                    f"{float(self.budget_pct_of_equity):.2%}"
                    + (" -> ENTRIES LOCKED" if over else "")))


@dataclass
class DailyLossLimit(Protection):
    """Stop opening new risk after the day has already cost `limit_pct`."""

    limit_pct: float = 0.03
    name: str = "daily_loss_limit"

    def evaluate(self, state: BookState) -> ProtectionReturn:
        if state.equity_usd is None or state.realised_pnl_today_usd is None:
            return self._refuse("today's realised P&L or equity")
        if state.equity_usd <= 0:
            return self._refuse("equity (non-positive)")
        loss = -float(state.realised_pnl_today_usd) / float(state.equity_usd)
        over = loss > float(self.limit_pct) + 1e-12
        return ProtectionReturn(
            protection=self.name, locked=over,
            measured={"loss_today_pct": loss, "limit_pct": float(self.limit_pct)},
            reason=(f"today {-loss:+.2%} vs limit {float(self.limit_pct):.2%}"
                    + (" -> ENTRIES LOCKED" if over else "")))


@dataclass
class CooldownPeriod(Protection):
    """After a name closes, no re-entry into THAT name for N periods."""

    periods: int = 1
    name: str = "cooldown_period"

    def evaluate(self, state: BookState) -> ProtectionReturn:
        m = state.periods_since_last_exit_by_name
        if m is None:
            return self._refuse("periods since the last exit, by name")
        cooling = tuple(sorted(k for k, v in m.items()
                               if v is not None and int(v) < int(self.periods)))
        return ProtectionReturn(
            protection=self.name, locked=bool(cooling), scope="name",
            names=cooling,
            measured={"periods": int(self.periods), "n_cooling": len(cooling)},
            reason=(f"{len(cooling)} name(s) inside the {self.periods}-period "
                    f"cooldown: {list(cooling)[:5]}" if cooling
                    else f"no name is inside the {self.periods}-period cooldown"))


@dataclass
class StoplossGuard(Protection):
    """N stop-outs inside a lookback window locks entries book-wide.

    Counts ONLY typed stop exits. An untyped exit is counted as untyped and
    reported, never quietly folded into the stop count -- a guard whose trigger
    can be inflated by a missing label is a guard nobody can audit.
    """

    trade_limit: int = 4
    lookback_periods: int = 5
    name: str = "stoploss_guard"
    stop_reasons: tuple[str, ...] = ("STOP", "TRAILING_STOP", "STOPLOSS_ON_EXCHANGE",
                                     "LIQUIDATION")

    def evaluate(self, state: BookState) -> ProtectionReturn:
        rows = list(state.recent_exits or ())
        if not rows:
            return ProtectionReturn(
                protection=self.name, locked=False,
                measured={"n_stops": 0, "trade_limit": int(self.trade_limit)},
                reason="no exits in the window")
        window = [r for r in rows
                  if r.get("periods_ago") is None
                  or int(r["periods_ago"]) < int(self.lookback_periods)]
        stops = [r for r in window if r.get("exit_reason") in self.stop_reasons]
        untyped = [r for r in window if not r.get("exit_reason")]
        over = len(stops) >= int(self.trade_limit)
        return ProtectionReturn(
            protection=self.name, locked=over,
            measured={"n_stops": len(stops), "n_untyped": len(untyped),
                      "n_in_window": len(window),
                      "trade_limit": int(self.trade_limit),
                      "lookback_periods": int(self.lookback_periods)},
            reason=(f"{len(stops)} stop-out(s) in the last "
                    f"{self.lookback_periods} periods vs limit "
                    f"{self.trade_limit}"
                    + (f"; {len(untyped)} UNTYPED exit(s) in the window are "
                       f"counted separately and never as stops" if untyped else "")
                    + (" -> ENTRIES LOCKED" if over else "")))


@dataclass
class MaxDrawdownGuard(Protection):
    """Lock entries while the book is more than `limit_pct` below its peak."""

    limit_pct: float = 0.15
    name: str = "max_drawdown_guard"

    def evaluate(self, state: BookState) -> ProtectionReturn:
        if state.equity_usd is None or state.peak_equity_usd is None:
            return self._refuse("equity or its running peak")
        if state.peak_equity_usd <= 0:
            return self._refuse("the running peak (non-positive)")
        dd = 1.0 - float(state.equity_usd) / float(state.peak_equity_usd)
        over = dd > float(self.limit_pct) + 1e-12
        return ProtectionReturn(
            protection=self.name, locked=over,
            measured={"drawdown": dd, "limit_pct": float(self.limit_pct)},
            reason=(f"drawdown {dd:.2%} vs limit {float(self.limit_pct):.2%}"
                    + (" -> ENTRIES LOCKED" if over else "")))


# --------------------------------------------------------------------------
# the stack


def default_protections(profile: str = "aggressive") -> list[Protection]:
    """The list that is NEVER empty. Bounds derived from the live profile."""
    p = PROFILES.get(str(profile).strip().lower())
    if p is None:
        raise ProtectionError(
            f"unknown profile {profile!r}; declared: {sorted(PROFILES)}. A "
            f"default guard list cannot be built from bounds nobody declared.")
    return [
        GrossExposureCap(gross_cap=p.gross_cap),
        WorstCaseStopBudget(budget_pct_of_equity=p.worst_case_pct),
        DailyLossLimit(limit_pct=min(0.03, p.worst_case_pct)),
        StoplossGuard(),
        CooldownPeriod(periods=1),
        MaxDrawdownGuard(),
    ]


@dataclass
class ProtectionStack:
    """The guards, as data. Evaluated before entries; locks entries only."""

    protections: Sequence[Protection] = ()
    deliberately_unprotected: str | None = None
    profile: str | None = None

    def __post_init__(self) -> None:
        if not self.protections and not self.deliberately_unprotected:
            raise ProtectionError(
                "REFUSED: an empty protection list. The guard list is never "
                "empty by default. Either pass `default_protections(profile)`, "
                "or state `deliberately_unprotected='<why>'` so the sentence "
                "lands on the receipt where a reviewer meets it.")
        if self.deliberately_unprotected and not str(
                self.deliberately_unprotected).strip():
            raise ProtectionError(
                "`deliberately_unprotected` must carry a REASON, not a flag.")

    def evaluate(self, state: BookState) -> dict:
        """Run every guard. Entries are admitted only if nothing locked."""
        results = [p.evaluate(state) for p in self.protections]
        locked = [r for r in results if r.locked]
        undeterminable = [r for r in results if not r.determinable]
        blocked_names = tuple(sorted({n for r in locked for n in r.names}))
        entries_allowed = not any(r.locked and r.scope == "global" for r in locked)
        return {
            "entries_allowed": bool(entries_allowed),
            "blocked_names": list(blocked_names),
            "n_protections": len(results),
            "n_locked": len(locked),
            "n_cannot_determine": len(undeterminable),
            "profile": self.profile,
            "deliberately_unprotected": self.deliberately_unprotected,
            "blocks": "entries only -- no protection can ever block an exit",
            "results": [r.as_dict() for r in results],
            "headline": (
                "ENTRIES LOCKED by " + ", ".join(r.protection for r in locked)
                if not entries_allowed else
                ("entries allowed"
                 + (f"; {len(blocked_names)} name(s) on cooldown"
                    if blocked_names else ""))),
        }


__all__ = ["BookState", "CANNOT_DETERMINE", "CooldownPeriod", "DailyLossLimit",
           "GrossExposureCap", "MaxDrawdownGuard", "PROFILES", "Profile",
           "Protection", "ProtectionError", "ProtectionReturn",
           "ProtectionStack", "StoplossGuard", "WorstCaseStopBudget",
           "default_protections", "profile_bounds"]
