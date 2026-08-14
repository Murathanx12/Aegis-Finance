"""INTERNET-INVESTIGATOR-FWD-1 — the tools the investigating arms may call.

Pre-registration: `Aegis module/TRIALS/PREREG_INTERNET_INVESTIGATOR_FWD_1.md`.
Frozen parameters: `Aegis module/scripts/iif1_config.py`.

WHAT THIS IS
============
Six read-only tools, each a thin wrapper over a service this repo already ships.
Nothing here fetches anything the engine could not already fetch; the trial is
about whether letting a model DECIDE WHAT TO LOOK UP adds anything over handing
it a pre-computed snapshot, so the tools deliberately expose existing
capability rather than new data.

THE ONE RULE THAT MATTERS MOST HERE
-----------------------------------
**A tool that fails must say so, in words, to the model.**

This project's recurring failure mode is a fetch that dies quietly and gets read
as information. The precedent is exact and expensive: the daily brief once hit a
GDELT 429, read the zero-default dict, and reported geopolitics as "quiet" —
fabricated calm, presented as a finding. The same shape has appeared in the
insider collector, the replay universe, the sector map and the crash overlay.

So every tool returns a `ToolResult` whose `status` is one of:

    ok           the tool ran and found something
    empty        the tool ran and there is genuinely nothing (a real answer)
    unavailable  the tool could not run -- throttled, missing key, exception

and `unavailable` is rendered into the model-visible text as an explicit
statement that the lookup FAILED. A model told "no news found" when the news
feed was down will confidently forecast calm. A model told "the news feed was
unavailable" can say it does not know, which under the belief-change contract is
a valid and gradeable answer (`belief_change = 0`).

`empty` and `unavailable` are never merged. That distinction is the whole point.

BUDGET AND PIT
--------------
Every tool call is counted and capped per investigation, because an agent loop
with an unbounded tool budget is a way to spend a night's money on one ticker.
The trial is forward-only, so "now" is point-in-time by construction and no
historical retrieval is possible or permitted.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: Hard cap on tool calls within a single ticker's investigation. An agent that
#: loops is a budget leak with a plausible explanation attached.
MAX_TOOL_CALLS_PER_INVESTIGATION = 12

#: Per-call wall-clock ceiling. A hung vendor must not hold the night open.
TOOL_TIMEOUT_S = 25.0

STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_UNAVAILABLE = "unavailable"


@dataclass
class ToolResult:
    """What a tool returned, including the fact that it returned nothing.

    `status` is load-bearing and is rendered into the model-visible text. See
    the module docstring: `empty` and `unavailable` mean opposite things and
    merging them is how this project has fabricated calm before.
    """
    tool: str
    status: str
    payload: Any = None
    reason: str = ""
    latency_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    def as_model_text(self) -> str:
        """The string the model actually sees. Failure is stated, not implied."""
        if self.status == STATUS_UNAVAILABLE:
            return (f"[{self.tool}] LOOKUP FAILED — {self.reason or 'unavailable'}. "
                    f"You do not know the answer to this; do not treat it as "
                    f"'nothing found'.")
        if self.status == STATUS_EMPTY:
            return (f"[{self.tool}] ran successfully and found nothing. This is "
                    f"a real negative result, not a failure.")
        try:
            body = json.dumps(self.payload, default=str)[:6000]
        except (TypeError, ValueError):
            body = str(self.payload)[:6000]
        return f"[{self.tool}] {body}"

    def as_row(self) -> dict:
        return {"tool": self.tool, "status": self.status, "reason": self.reason,
                "latency_ms": round(self.latency_ms, 1)}


@dataclass
class ToolSpec:
    """A tool the model may call: its contract, and how to run it."""
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]
    #: True when the tool reaches an external vendor. Used to decide what a
    #: failure means and to keep the arms honest about what they consumed.
    external: bool = True


@dataclass
class ToolBudget:
    """Per-investigation call accounting. Refuses rather than overspends."""
    max_calls: int = MAX_TOOL_CALLS_PER_INVESTIGATION
    used: int = 0
    log: list[dict] = field(default_factory=list)

    def take(self) -> bool:
        if self.used >= self.max_calls:
            return False
        self.used += 1
        return True

    @property
    def exhausted(self) -> bool:
        return self.used >= self.max_calls


# ── the tool implementations ────────────────────────────────────────────────
#
# Each returns a plain object or raises. `run_tool` is the only place that turns
# an exception into `unavailable`, so no implementation can accidentally swallow
# its own failure into a zero-default.

def _search_news(ticker: str, max_items: int = 8) -> Any:
    from backend.services.news_intelligence import fetch_stock_news
    items = fetch_stock_news(ticker, max_items=max_items) or []
    return [{"title": i.get("title"), "publisher": i.get("publisher"),
             "published": i.get("published"), "link": i.get("link")}
            for i in items]


def _read_filings(ticker: str, days: int = 14) -> Any:
    from backend.services.edgar_events import fetch_events_for_ticker
    evs = fetch_events_for_ticker(ticker, days=days) or []
    out = []
    for e in evs:
        out.append({
            "form": getattr(e, "form", None),
            "filed": str(getattr(e, "filing_date", "")),
            "items": getattr(e, "item_codes", None),
            "classification": getattr(e, "classification", None),
        })
    return out


def _query_revisions(ticker: str) -> Any:
    from backend.services.estimate_revisions import get_revisions_trend
    return get_revisions_trend(ticker)


def _query_options(ticker: str) -> Any:
    from backend.services.options_intelligence import get_iv_signal
    return get_iv_signal(ticker)


def _query_earnings(ticker: str) -> Any:
    from backend.services.earnings_intelligence import get_earnings_summary
    return get_earnings_summary(ticker)


def _query_prices(ticker: str, period: str = "3mo") -> Any:
    from backend.services.data_fetcher import fetch_ticker_history
    h = fetch_ticker_history(ticker, period=period)
    if h is None or getattr(h, "empty", True):
        return None
    tail = h.tail(30)
    close = tail["Close"] if "Close" in tail else tail.iloc[:, 0]
    return {"last": float(close.iloc[-1]),
            "ret_5d_pct": float(close.pct_change(5).iloc[-1] * 100.0),
            "ret_20d_pct": float(close.pct_change(20).iloc[-1] * 100.0)
            if len(close) > 20 else None,
            "realised_vol_20d_ann_pct": float(
                close.pct_change().tail(20).std() * (252 ** 0.5) * 100.0)}


TOOLS: dict[str, ToolSpec] = {
    "search_news": ToolSpec(
        name="search_news",
        description=("Recent news headlines for a ticker. Returns titles, "
                     "publishers and timestamps — not article bodies."),
        parameters={"type": "object", "required": ["ticker"], "properties": {
            "ticker": {"type": "string"},
            "max_items": {"type": "integer", "minimum": 1, "maximum": 20}}},
        fn=_search_news),
    "read_filings": ToolSpec(
        name="read_filings",
        description=("Recent SEC filings (8-K item codes and classification) "
                     "for a ticker."),
        parameters={"type": "object", "required": ["ticker"], "properties": {
            "ticker": {"type": "string"},
            "days": {"type": "integer", "minimum": 1, "maximum": 90}}},
        fn=_read_filings),
    "query_revisions": ToolSpec(
        name="query_revisions",
        description="Analyst estimate revision trend for a ticker.",
        parameters={"type": "object", "required": ["ticker"], "properties": {
            "ticker": {"type": "string"}}},
        fn=_query_revisions),
    "query_options": ToolSpec(
        name="query_options",
        description=("Options-implied signal: IV rank, skew, put/call. The "
                     "market's own view of how much this name is about to "
                     "move."),
        parameters={"type": "object", "required": ["ticker"], "properties": {
            "ticker": {"type": "string"}}},
        fn=_query_options),
    "query_earnings": ToolSpec(
        name="query_earnings",
        description=("Earnings history, next scheduled date, surprise record. "
                     "The single most useful thing for a magnitude forecast."),
        parameters={"type": "object", "required": ["ticker"], "properties": {
            "ticker": {"type": "string"}}},
        fn=_query_earnings),
    "query_prices": ToolSpec(
        name="query_prices",
        description="Recent price action and realised volatility for a ticker.",
        parameters={"type": "object", "required": ["ticker"], "properties": {
            "ticker": {"type": "string"},
            "period": {"type": "string"}}},
        fn=_query_prices),
}

#: The market-graph tool is only offered to `D_all`. It is listed separately so
#: an arm cannot be given it by accident.
GRAPH_TOOL = "query_market_graph"


def openai_tool_schemas(names: list[str]) -> list[dict]:
    """The function-calling schema block for the named tools."""
    out = []
    for n in names:
        spec = TOOLS.get(n)
        if spec is None:
            raise KeyError(f"unknown tool {n!r}; the arm's tool list is part of "
                           f"the frozen design and a typo would silently "
                           f"change which arm this is")
        out.append({"type": "function", "function": {
            "name": spec.name, "description": spec.description,
            "parameters": spec.parameters}})
    return out


def run_tool(name: str, args: dict, budget: ToolBudget | None = None
             ) -> ToolResult:
    """Execute one tool call. The ONLY place an exception becomes `unavailable`.

    Every failure path returns a ToolResult carrying a reason, and every reason
    reaches the model. Nothing here returns a zero-default that could be read as
    an answer.
    """
    t0 = time.perf_counter()

    def _finish(res: ToolResult) -> ToolResult:
        """Single exit point. Every path — success, empty, vendor failure, bad
        arguments, unknown tool, budget refusal — is timed AND logged here.

        The budget-refusal path used to return early without logging, which made
        a night that hit the tool cap indistinguishable from a night that had
        nothing to ask. That is the same silent-fragility shape this module
        exists to prevent, one level up, and it was caught by its own test.
        """
        res.latency_ms = (time.perf_counter() - t0) * 1000.0
        if budget is not None:
            budget.log.append(res.as_row())
        return res

    spec = TOOLS.get(name)
    if spec is None:
        return _finish(ToolResult(name, STATUS_UNAVAILABLE,
                                  reason=f"no such tool {name!r}"))
    if budget is not None and not budget.take():
        return _finish(ToolResult(
            name, STATUS_UNAVAILABLE,
            reason=f"tool budget exhausted after {budget.max_calls} calls"))
    try:
        payload = spec.fn(**(args or {}))
    except TypeError as exc:
        # A bad argument set from the model is not a vendor failure, and
        # labelling it one would hide a contract bug behind a flaky-network
        # story.
        res = ToolResult(name, STATUS_UNAVAILABLE,
                         reason=f"bad arguments: {exc}")
    except Exception as exc:                                   # noqa: BLE001
        logger.warning("tool %s failed: %s", name, exc)
        res = ToolResult(name, STATUS_UNAVAILABLE,
                         reason=f"{type(exc).__name__}: {exc}")
    else:
        empty = (payload is None
                 or (isinstance(payload, (list, dict, str)) and len(payload) == 0))
        res = ToolResult(name, STATUS_EMPTY if empty else STATUS_OK,
                         payload=None if empty else payload)
    return _finish(res)


def tools_for_arm(arm: str) -> list[str]:
    """Which tools each arm may call. Part of the frozen design.

    `A_snapshot` gets none — that is what makes it the control. Handing it a
    tool by accident would not fail loudly; it would quietly turn the primary
    contrast into a comparison of two investigating arms, and the trial would
    report a null that means nothing.
    """
    base = ["search_news", "read_filings", "query_revisions", "query_options",
            "query_earnings", "query_prices"]
    if arm == "A_snapshot":
        return []
    if arm in ("B_tools", "C_tools_only", "B_anon"):
        return list(base)
    if arm == "D_all":
        return list(base)          # + GRAPH_TOOL once the graph server is wired
    raise KeyError(f"unknown arm {arm!r}")
