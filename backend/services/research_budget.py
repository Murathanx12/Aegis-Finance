"""The governor the research swarm never had.

WHY THIS EXISTS
===============
Two budgets were believed to exist and only one did.

`llm.daily_call_cap = 150` guards the PRODUCTION path (`llm_analyzer`). It was
sized for a $20 prepaid balance and it is the right shape for a user-facing
endpoint. The external review read it as the thing throttling research.

It was not. It never applied to research at all. `why_moved` and
`optimus_specialists` build their own client and call DeepSeek directly, so the
swarm paths were not throttled — they were **ungoverned**. For a campaign of
thousands of calls that is the worse of the two failures: nothing would have
stopped a runaway loop except the vendor balance emptying, and the first
symptom would have been a dead key on the production path that shares it.

So this is not a raised cap. It is a separate governor that the research paths
actually consult, leaving production's guard exactly where it is.

WHAT IT COUNTS, AND WHY IT READS THE LEDGER
-------------------------------------------
Spend is read from `llm_telemetry`, which is the only place that knows what was
really spent. A budget enforced against an in-process counter is not a budget —
it resets on restart, and a campaign that crashes and resumes would silently
spend twice. The cost is an ESTIMATE against a dated price table, so the dollar
ceiling is treated as approximate and the CALL ceiling is the hard one.

THE THIRD BRAKE
---------------
Calls and dollars are the obvious limits. The one that matters more here is
**zero yield**: the share of calls that produced no prediction and no
hypothesis. A campaign spending its budget on ungradeable output is buying
tokens rather than information, which is the exact failure the whole telemetry
effort exists to expose. Past a threshold it halts for inspection instead of
spending the remainder the same way. It is not armed below a minimum n, because
halting a campaign on three unlucky parses would be its own kind of stupidity.

REFUSALS ARE FREE
-----------------
A call refused by this module spends nothing and writes no telemetry row.
Counting refusals would dilute the zero-yield denominator with calls that never
reached the vendor — the same reasoning `llm_research` already applies to its
own budget refusals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.config import (RESEARCH_LLM_ENABLED, RESEARCH_LLM_MAX_CALLS,
                            RESEARCH_LLM_MAX_USD,
                            RESEARCH_LLM_MAX_ZERO_YIELD_RATE,
                            RESEARCH_LLM_ZERO_YIELD_MIN_N)

logger = logging.getLogger(__name__)


class ResearchBudgetExhausted(RuntimeError):
    """The campaign's budget is spent. Refusing to call.

    Raised rather than returned so a caller cannot accidentally treat an
    exhausted budget as an empty result and carry on.
    """


@dataclass(frozen=True)
class BudgetState:
    """What the campaign has spent and what remains."""
    campaign: str
    n_calls: int
    cost_usd: float | None
    cost_is_lower_bound: bool
    zero_yield_rate: float | None
    calls_remaining: int
    usd_remaining: float | None
    ok: bool
    reason: str | None
    #: Calls whose yield is accounted at the chain level and not knowable yet.
    #: Excluded from the zero-yield denominator, reported so that exclusion is
    #: never invisible — a pending count that never falls is a stuck campaign.
    n_yield_pending: int = 0
    n_yield_resolvable: int = 0

    def as_dict(self) -> dict:
        return {
            "campaign": self.campaign,
            "n_calls": self.n_calls,
            "cost_usd": self.cost_usd,
            "cost_is_estimate": True,
            "cost_is_lower_bound": self.cost_is_lower_bound,
            "zero_yield_rate": self.zero_yield_rate,
            "calls_remaining": self.calls_remaining,
            "usd_remaining": self.usd_remaining,
            "max_calls": RESEARCH_LLM_MAX_CALLS,
            "max_usd": RESEARCH_LLM_MAX_USD,
            "n_yield_pending": self.n_yield_pending,
            "n_yield_resolvable": self.n_yield_resolvable,
            "ok": self.ok,
            "reason": self.reason,
        }


def _summary(since: str | None, path: Path | None) -> dict:
    """Spend so far, from the telemetry ledger. Never raises.

    A telemetry read failure must not be allowed to look like zero spend — that
    would silently disarm every ceiling at once — so the failure is reported and
    the caller treats it as unknown rather than free.
    """
    try:
        from backend.services import llm_telemetry
        # `spend` rather than `summary`: identical inputs to the decision below,
        # without the prediction-ledger join a gate does not need. The join is
        # ~6x the cost of the counts, and this function is called before EVERY
        # vendor request — a governor that is expensive to consult is a governor
        # someone eventually consults less often.
        return llm_telemetry.spend(since=since, path=path)
    except Exception as exc:                                   # noqa: BLE001
        logger.warning("research_budget: cannot read the telemetry ledger "
                       "(%s: %s) — spend is UNKNOWN, not zero",
                       type(exc).__name__, exc)
        return {}


def check(campaign: str = "grand_arena_1", *, since: str | None = None,
          path: Path | None = None) -> BudgetState:
    """Where the campaign stands. Pure: reads, decides, writes nothing."""
    if not RESEARCH_LLM_ENABLED:
        return BudgetState(campaign, 0, 0.0, False, None, 0, 0.0, False,
                           "research LLM disabled (AEGIS_RESEARCH_LLM=0)")

    s = _summary(since, path)
    if not s:
        # Unknown spend. Allowing the campaign here would mean every ceiling is
        # off precisely when the accounting is broken.
        return BudgetState(campaign, 0, None, True, None, 0, None, False,
                           "telemetry unreadable — refusing to spend against an "
                           "unknown balance")

    n = int(s.get("n_calls", 0) or 0)
    cost = s.get("total_cost_usd")
    lower_bound = bool(s.get("total_is_lower_bound"))

    # THE DENOMINATOR IS THE RESOLVABLE CALLS, NOT ALL OF THEM.
    # `share_of_calls` counts a call whose chain has not finished as zero-yield,
    # which is true of EVERY call of a microtask-chain campaign until its last
    # arm ends. IIF-1 halted at 100% after 50 calls for that reason alone — the
    # rule was reading the minting schedule, not the information content. Rows
    # that never declare a chain are unaffected: pending is 0 and this is the
    # old number exactly.
    zbucket = s.get("zero_gradeable_output") or {}
    n_pending = int(zbucket.get("n_yield_pending", 0) or 0)
    n_resolvable = int(zbucket.get("n_resolvable", n - n_pending) or 0)
    zy = zbucket.get("share_of_resolvable")
    if zy is None and not n_pending:
        zy = zbucket.get("share_of_calls")

    calls_left = max(0, RESEARCH_LLM_MAX_CALLS - n)
    usd_left = (None if cost is None
                else round(RESEARCH_LLM_MAX_USD - float(cost), 4))

    reason = None
    if calls_left <= 0:
        reason = (f"call ceiling reached: {n} >= {RESEARCH_LLM_MAX_CALLS}")
    elif cost is not None and float(cost) >= RESEARCH_LLM_MAX_USD:
        reason = (f"estimated spend ${float(cost):.2f} >= "
                  f"${RESEARCH_LLM_MAX_USD:.2f}"
                  + (" (and the estimate is a LOWER BOUND — unpriced models "
                     "are in the ledger)" if lower_bound else ""))
    elif (zy is not None and n_resolvable >= RESEARCH_LLM_ZERO_YIELD_MIN_N
          and float(zy) > RESEARCH_LLM_MAX_ZERO_YIELD_RATE):
        # Not a spend limit — an information limit. The campaign is buying
        # tokens rather than gradeable output and should be looked at.
        reason = (f"zero-yield rate {float(zy):.1%} exceeds "
                  f"{RESEARCH_LLM_MAX_ZERO_YIELD_RATE:.0%} over {n_resolvable} "
                  f"resolvable calls (of {n} total"
                  + (f", {n_pending} pending" if n_pending else "")
                  + ") — halting for inspection: this campaign is buying "
                    "tokens, not information")

    return BudgetState(campaign, n, cost, lower_bound, zy, calls_left, usd_left,
                       reason is None, reason,
                       n_yield_pending=n_pending,
                       n_yield_resolvable=n_resolvable)


def require(campaign: str = "grand_arena_1", *, since: str | None = None,
            path: Path | None = None) -> BudgetState:
    """Gate a research call. Raises ResearchBudgetExhausted when spent.

    Call this BEFORE the vendor request. A refusal costs nothing and writes no
    telemetry row, so refusals never dilute the zero-yield denominator.
    """
    st = check(campaign, since=since, path=path)
    if not st.ok:
        logger.warning("research_budget: REFUSING a %s call — %s",
                       campaign, st.reason)
        raise ResearchBudgetExhausted(st.reason or "budget exhausted")
    return st


def health(campaign: str = "grand_arena_1") -> dict:
    """Status row. Distinguishes 'no campaign has run' from 'budget spent'."""
    st = check(campaign)
    d = st.as_dict()
    d["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if st.n_calls == 0 and st.ok:
        d["reading"] = "no research calls recorded yet in this window"
    elif st.ok:
        d["reading"] = (f"{st.n_calls} calls, "
                        f"{st.calls_remaining} remaining under the ceiling")
    else:
        d["reading"] = f"REFUSING further research calls: {st.reason}"
    return d
