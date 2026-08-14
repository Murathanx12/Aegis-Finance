"""INTERNET-INVESTIGATOR-FWD-1 — the microtask investigator.

Pre-registration: `Aegis module/TRIALS/PREREG_INTERNET_INVESTIGATOR_FWD_1.md`.
Frozen parameters: `Aegis module/scripts/iif1_config.py`.

WHAT REPLACES THE MEGA-SCHEMA
=============================
SWARM-1 handed every "specialist" one large common contract: scenarios, multiple
forecast types, a thesis, a counter-thesis, all in a single call. NIGHT-14
measured what that produced — fourteen personas with 0.49 effective distinct
ideas, against 0.85 for one generic agent at a fifth of the calls. The personas
were one forecaster wearing hats, and the schema was doing the wearing.

So this is division of COGNITION, not of persona. Five small contracts, each
separately gradeable, each with one job:

    gather        (tool arms only) decide what to look up, and look it up
    event         what changed, when, who is affected, novelty, expectedness
    expectations  what did the market already believe, and what moved
    forecast      prior / posterior / belief_change per (observable, horizon)
    critic        why is this chain wrong, and what would falsify it

The forecaster sees the earlier outputs and never the raw tool dump, so the
chain is a pipeline rather than one prompt with sections.

THE BELIEF-CHANGE CONTRACT
--------------------------
The forecaster returns `prior` and `posterior`. `belief_change = 0` is a valid
answer and is graded like any other. The old `p != 0.50` refusal is retired: it
kept coin flips out of the ledger at the cost of teaching forecasters to say
0.51 instead of "this changed nothing".

WHAT IS HELD IDENTICAL ACROSS ARMS
----------------------------------
Everything except the two things under test: whether the arm may call tools, and
whether it is shown the engineered snapshot. Same microtask prompts, same
schema, same temperature, same model, same cells. If an arm ever differs in
anything else, the comparison stops being about investigation.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.services import investigator_tools as IT

logger = logging.getLogger(__name__)


def _budget_errors() -> tuple[type[BaseException], ...]:
    """Exceptions that mean "stop", not "this cell failed".

    `ResearchBudgetExhausted` is imported defensively: the agent must work in a
    checkout where the research-budget module is absent, but it must never
    silently lose the ability to recognise a governor refusal.
    """
    errs: list[type[BaseException]] = [IT.BudgetExhausted]
    try:
        from backend.services.research_budget import ResearchBudgetExhausted
        errs.append(ResearchBudgetExhausted)
    except Exception:                                          # noqa: BLE001
        logger.warning("research_budget unavailable — a governor refusal will "
                       "not be distinguishable from a cell failure")
    return tuple(errs)


_BUDGET_ERRORS = _budget_errors()

#: Max rounds the model may spend calling tools before it must answer. Bounded
#: because an agent loop with no ceiling is a budget leak with a story attached.
MAX_TOOL_ROUNDS = 4

TEMPERATURE = 0.0
MAX_TOKENS = 1600

#: The observables this trial forecasts, mirroring `iif1_config.PRIMARY_
#: OBSERVABLES` and `SECONDARY_OBSERVABLES_UNDERPOWERED`. Kept here as the
#: runtime copy; the frozen source of truth is the config in `Aegis module`.
FORECAST_CELLS = (
    ("abs_move_exceeds", 5, 0.05),
    ("abs_move_exceeds", 1, 0.03),
    ("return_sign", 5, None),
)

# ── why a cell was dropped: a CLOSED, VALUE-FREE vocabulary ─────────────────
# The receipt is read every morning during a 40-night blind, so a drop reason
# may never carry a model-stated number or name a cell. These codes say what
# was wrong with the SHAPE and nothing about the content.
DROP_REPLY_NOT_A_LIST = "reply_not_a_list"
DROP_REPLY_NOT_AN_OBJECT = "reply_not_an_object"
DROP_CELL_NOT_AN_OBJECT = "cell_not_an_object"
DROP_FIELD_MISSING = "field_missing_or_unparseable"
DROP_CELL_NOT_REQUESTED = "cell_not_requested"
DROP_BELIEF_OUT_OF_RANGE = "belief_out_of_unit_range"
DROP_SIZE_BOUND_NOT_A_FRACTION = "size_bound_not_a_fraction"
DROP_CALL_FAILED = "call_failed"

DROP_REASONS = frozenset({
    DROP_REPLY_NOT_A_LIST, DROP_REPLY_NOT_AN_OBJECT, DROP_CELL_NOT_AN_OBJECT,
    DROP_FIELD_MISSING, DROP_CELL_NOT_REQUESTED, DROP_BELIEF_OUT_OF_RANGE,
    DROP_SIZE_BOUND_NOT_A_FRACTION, DROP_CALL_FAILED,
})


# ── prompts: identical across arms, by construction ─────────────────────────

SYS_GATHER = """You are an investigator. You have tools. Your job in this step \
is ONLY to find out what is true about this security right now — not to \
forecast anything.

Call the tools you actually need. Do not call all of them by reflex; each call \
costs budget and an unnecessary lookup crowds out a useful one. Stop as soon as \
you know enough to describe what is going on.

CRITICAL: if a tool reports LOOKUP FAILED, that means you DO NOT KNOW. It does \
not mean there is nothing there. Never treat a failed lookup as an absence of \
news, of filings, or of events.

When you are done gathering, reply with a short plain-text dossier of what you \
found and — explicitly — what you could not find out."""

SYS_EVENT = """Extract what changed. Reply with JSON only:
{"what_changed": str, "when": str, "who_is_affected": [str],
 "novelty": "none"|"low"|"medium"|"high",
 "expectedness": "fully_expected"|"partly_expected"|"surprise",
 "unknowns": [str]}

"novelty" is how new this information is to the world. "expectedness" is whether \
the market would already have been positioned for it. They are different things \
and a scheduled event can be high-novelty and fully expected at once.
If nothing changed, say so plainly: what_changed = "nothing identifiable"."""

SYS_EXPECT = """You are given a description of what changed. Reply with JSON only:
{"prior_market_belief": str, "what_moved_in_expectations": str,
 "already_priced": "yes"|"partly"|"no"|"unknown"}

Answer about EXPECTATIONS, not about price direction. If you cannot tell, say \
"unknown" — that is a real answer and it is graded as one."""

SYS_FORECAST = """You forecast MAGNITUDE, not direction. Reply with JSON only:
{"forecasts": [{"observable": str, "horizon_days": int, "threshold": float|null,
  "prior": float, "posterior": float, "rationale": str}]}

For each cell you are given:
  "prior"      = your probability BEFORE the evidence in this dossier, i.e. the \
base rate for a security like this one.
  "posterior"  = your probability AFTER the evidence.

If the evidence changed nothing, set posterior = prior. That is a valid and \
expected answer — "this information changed nothing" is informative and is \
graded like any other forecast. Do NOT manufacture a difference to look decisive.

Both must be in [0,1]. Give one entry per cell you were asked about, and no \
others."""

SYS_CRITIC = """You are shown a reasoning chain and its forecasts. Attack it. \
Reply with JSON only:
{"strongest_objection": str, "contradicting_evidence": str,
 "falsifying_check": str, "confidence_in_chain": "low"|"medium"|"high"}

"falsifying_check" must be something that could actually be run against data — \
name the comparison, not a sentiment."""


@dataclass
class MicrotaskCall:
    """One LLM call in the chain, with what it cost and what served it."""
    task: str
    ok: bool
    text: str = ""
    parsed: Any = None
    served_model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    error: str = ""

    def as_row(self) -> dict:
        return {"task": self.task, "ok": self.ok,
                "served_model": self.served_model,
                "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                "latency_ms": round(self.latency_ms, 1),
                "error": self.error[:200]}


@dataclass
class Investigation:
    """Everything one (arm, ticker) produced, including nothing."""
    arm: str
    ticker: str
    status: str = "ok"                     # ok | no_forecast | failed
    calls: list[MicrotaskCall] = field(default_factory=list)
    tool_log: list[dict] = field(default_factory=list)
    dossier: str = ""
    event: dict | None = None
    expectations: dict | None = None
    forecasts: list[dict] = field(default_factory=list)
    #: Why cells were dropped, counted by reason. A barren cell that says only
    #: `n_forecasts: 0` cannot be diagnosed after the night, at any price.
    forecast_drops: dict = field(default_factory=dict)
    critique: dict | None = None
    error: str = ""

    @property
    def served_models(self) -> set[str]:
        return {c.served_model for c in self.calls if c.served_model}

    @property
    def tokens(self) -> tuple[int, int]:
        return (sum(c.tokens_in for c in self.calls),
                sum(c.tokens_out for c in self.calls))

    def as_row(self) -> dict:
        return {"arm": self.arm, "ticker": self.ticker, "status": self.status,
                "n_calls": len(self.calls), "n_tool_calls": len(self.tool_log),
                "n_forecasts": len(self.forecasts),
                "forecast_drops": dict(self.forecast_drops),
                "served_models": sorted(self.served_models),
                "tokens_in": self.tokens[0], "tokens_out": self.tokens[1],
                "error": self.error[:200]}


def _extract_json(text: str) -> Any:
    """Parse a JSON object out of a reply, or raise.

    Never returns a default. A silently-empty parse would be recorded as a
    forecaster that declined to answer, which is a completely different finding
    from a forecaster whose reply we failed to read.
    """
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def mask_ticker(text: str, ticker: str, alias: str = "COMPANY_X") -> str:
    """Replace ticker mentions for the `B_anon` arm.

    Glasserman & Lin found that anonymising tickers IMPROVED returns — the
    model's company knowledge acting as a net distraction. `NEGATIVE_RESULTS`
    §19 requires that finding be rebutted rather than ignored, and this trial
    rebuts it by testing it, so the masking has to actually work.

    It is deliberately crude and word-boundary anchored: over-masking degrades
    the arm's information, which biases AGAINST H3, and a control that errs
    against its own hypothesis is the safe direction to err in.
    """
    if not ticker:
        return text
    return re.sub(rf"\b{re.escape(ticker)}\b", alias, text or "",
                  flags=re.IGNORECASE)


class Investigator:
    """Runs the microtask chain for one arm.

    `llm_call` and `tool_runner` are injected so the whole chain is testable
    offline with no vendor and no network — which is how the tests run.
    """

    def __init__(self, arm: str, *, llm_call: Callable, tool_runner=None,
                 model: str = "deepseek-v4-flash",
                 max_tool_rounds: int = MAX_TOOL_ROUNDS,
                 tool_budget: int = IT.MAX_TOOL_CALLS_PER_INVESTIGATION) -> None:
        if arm not in ("A_snapshot", "B_tools", "C_tools_only", "D_all",
                       "B_anon"):
            raise KeyError(f"unknown arm {arm!r}")
        self.arm = arm
        self.llm_call = llm_call
        self.tool_runner = tool_runner or IT.run_tool
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self.tool_budget = tool_budget

    # ── arm capabilities: the only things that differ ───────────────────────
    @property
    def may_use_tools(self) -> bool:
        return bool(IT.tools_for_arm(self.arm))

    @property
    def sees_snapshot(self) -> bool:
        """`C_tools_only` is the arm that answers whether the engine snapshot is
        carrying real weight or is ballast."""
        return self.arm != "C_tools_only"

    @property
    def anonymised(self) -> bool:
        return self.arm == "B_anon"

    # ── one microtask ───────────────────────────────────────────────────────
    def _task(self, task: str, system: str, user: str,
              parse: bool = True) -> MicrotaskCall:
        t0 = time.perf_counter()
        try:
            reply = self.llm_call(system=system, user=user, model=self.model,
                                  temperature=TEMPERATURE,
                                  max_tokens=MAX_TOKENS)
        except _BUDGET_ERRORS:
            # NEVER absorbed into a per-cell failure. A swallowed ceiling keeps
            # calling the vendor while logging warnings — the most expensive
            # possible way to fail, and the one `llm_swarm` already documented.
            raise
        except Exception as exc:                               # noqa: BLE001
            logger.warning("[%s/%s] %s failed: %s", self.arm, task,
                           type(exc).__name__, exc)
            return MicrotaskCall(task, False,
                                 error=f"{type(exc).__name__}: {exc}",
                                 latency_ms=(time.perf_counter() - t0) * 1000)
        c = MicrotaskCall(
            task, True, text=getattr(reply, "text", "") or "",
            served_model=str(getattr(reply, "model_version", "") or ""),
            tokens_in=int(getattr(reply, "tokens_in", 0) or 0),
            tokens_out=int(getattr(reply, "tokens_out", 0) or 0),
            latency_ms=(time.perf_counter() - t0) * 1000)
        if parse:
            try:
                c.parsed = _extract_json(c.text)
            except (json.JSONDecodeError, ValueError) as exc:
                c.ok = False
                c.error = f"unparseable reply: {exc}"
        return c

    # ── the gather step ─────────────────────────────────────────────────────
    def _gather(self, ticker: str, inv: Investigation) -> str:
        """Run the tools. Returns a plain-text dossier the later steps read.

        The model is asked which tools to call; the answer is parsed as a JSON
        list rather than via vendor function-calling, so the chain does not
        depend on one provider's tool protocol and can be replayed offline.
        """
        budget = IT.ToolBudget(max_calls=self.tool_budget)
        available = IT.tools_for_arm(self.arm)
        # The anonymised arm must still be able to LOOK THINGS UP about the real
        # security — otherwise it is not an anonymisation control, it is an arm
        # with no data, and H3 would be answered by starvation rather than by
        # the effect of ticker knowledge. So the prompt shows the alias while
        # the tool call uses the real symbol, and the results are masked on the
        # way back.
        shown = "COMPANY_X" if self.anonymised else ticker
        seen: list[str] = []
        for _ in range(self.max_tool_rounds):
            if budget.exhausted:
                break
            user = (f"Security: {shown}\n"
                    f"Tools available: {', '.join(available)}\n"
                    f"Already gathered:\n" + ("\n".join(seen) or "(nothing yet)")
                    + "\n\nReply with JSON only: "
                      '{"calls": [{"tool": str, "args": {...}}], "done": bool}. '
                      'Set done=true when you have enough. You do not need to '
                      'supply the security identifier; it is filled in for you.')
            c = self._task("gather_plan", SYS_GATHER, user)
            inv.calls.append(c)
            if not c.ok or not isinstance(c.parsed, dict):
                break
            for call in (c.parsed.get("calls") or [])[:6]:
                if budget.exhausted:
                    break
                name = str(call.get("tool", ""))
                args = dict(call.get("args") or {})
                # FORCE, never default. The model may not redirect a lookup to
                # a different security: that would let one cell's evidence come
                # from another company's news, which is silent cross-
                # contamination between paired cells and would be invisible in
                # the output. It also keeps the anonymised arm honest, since it
                # cannot name the symbol it is really asking about.
                args["ticker"] = ticker
                res = self.tool_runner(name, args, budget)
                txt = res.as_model_text()
                seen.append(mask_ticker(txt, ticker) if self.anonymised else txt)
            if c.parsed.get("done"):
                break
        inv.tool_log = budget.log
        return "\n".join(seen) if seen else "(no tools were run)"

    # ── the chain ───────────────────────────────────────────────────────────
    def investigate(self, ticker: str, snapshot: dict | None = None
                    ) -> Investigation:
        inv = Investigation(arm=self.arm, ticker=ticker)
        shown = "COMPANY_X" if self.anonymised else ticker

        try:
            dossier = (self._gather(ticker, inv) if self.may_use_tools
                       else "(this arm has no investigation tools)")
            snap_txt = ""
            if self.sees_snapshot and snapshot is not None:
                snap_txt = json.dumps(snapshot, default=str)[:5000]
            elif not self.sees_snapshot:
                snap_txt = "(this arm is not shown the engine snapshot)"

            if self.anonymised:
                dossier = mask_ticker(dossier, ticker)
                snap_txt = mask_ticker(snap_txt, ticker)
            inv.dossier = dossier

            base = (f"Security: {shown}\n\nENGINE SNAPSHOT:\n{snap_txt}\n\n"
                    f"INVESTIGATION DOSSIER:\n{dossier}\n")

            c_ev = self._task("event", SYS_EVENT, base)
            inv.calls.append(c_ev)
            inv.event = c_ev.parsed if c_ev.ok else None

            c_ex = self._task("expectations", SYS_EXPECT,
                              base + f"\nWHAT CHANGED:\n"
                                     f"{json.dumps(inv.event, default=str)}")
            inv.calls.append(c_ex)
            inv.expectations = c_ex.parsed if c_ex.ok else None

            cells = "\n".join(
                f'- observable={o}, horizon_days={h}, threshold={t}'
                for o, h, t in FORECAST_CELLS)
            c_fc = self._task(
                "forecast", SYS_FORECAST,
                base
                + f"\nWHAT CHANGED:\n{json.dumps(inv.event, default=str)}"
                + f"\nEXPECTATIONS:\n{json.dumps(inv.expectations, default=str)}"
                + f"\n\nForecast EXACTLY these cells:\n{cells}")
            inv.calls.append(c_fc)
            if c_fc.ok and isinstance(c_fc.parsed, dict):
                inv.forecasts, inv.forecast_drops = self._validate(
                    c_fc.parsed.get("forecasts"))
            elif c_fc.ok:
                inv.forecast_drops = {DROP_REPLY_NOT_AN_OBJECT: 1}
            else:
                inv.forecast_drops = {DROP_CALL_FAILED: 1}

            c_cr = self._task(
                "critic", SYS_CRITIC,
                base + f"\nCHAIN:\n{json.dumps(inv.event, default=str)}\n"
                       f"{json.dumps(inv.expectations, default=str)}\n"
                       f"{json.dumps(inv.forecasts, default=str)}")
            inv.calls.append(c_cr)
            inv.critique = c_cr.parsed if c_cr.ok else None

            if not inv.forecasts:
                inv.status = "no_forecast"
        except _BUDGET_ERRORS:
            raise                       # stop the night, do not mark one cell
        except Exception as exc:                               # noqa: BLE001
            logger.exception("[%s/%s] investigation failed", self.arm, ticker)
            inv.status = "failed"
            inv.error = f"{type(exc).__name__}: {exc}"
        return inv

    @staticmethod
    def _validate(raw: Any) -> "tuple[list[dict], dict]":
        """Keep only forecasts that could actually be graded.

        A malformed cell is DROPPED and not repaired. Coercing a forecaster's
        output is guessing at what it meant, and a guessed forecast is scored
        against a judgement nobody made — the `threshold >= 1.0` incident in the
        swarm produced six guaranteed-wrong records that way.
        """
        out: list[dict] = []
        drops: dict[str, int] = {}

        def _drop(code: str) -> None:
            # WHY a cell was dropped is the only thing that makes a barren arm
            # diagnosable. Night 1 lost 15 of 40 cells in one arm and 8 of 10 in
            # another, and the receipt recorded only `n_forecasts: 0` — so the
            # cause could not be established afterwards at any price.
            #
            # CODES ONLY. The receipt is read every morning during a 40-night
            # blind, so a reason may never interpolate a model-stated number or
            # name a cell — "the size bound was not a fraction" is diagnostic;
            # "0.07 was not a fraction" is a forecast leaking out through the
            # error path. The vocabulary is closed and pinned by a test.
            assert code in DROP_REASONS, code
            drops[code] = drops.get(code, 0) + 1

        if not isinstance(raw, list):
            _drop(DROP_REPLY_NOT_A_LIST)
            return out, drops
        wanted = {(o, h) for o, h, _ in FORECAST_CELLS}
        for f in raw:
            if not isinstance(f, dict):
                _drop(DROP_CELL_NOT_AN_OBJECT)
                continue
            try:
                obs = str(f["observable"])
                hz = int(f["horizon_days"])
                pri = float(f["prior"])
                pos = float(f["posterior"])
            except (KeyError, TypeError, ValueError):
                _drop(DROP_FIELD_MISSING)
                continue
            if (obs, hz) not in wanted:
                _drop(DROP_CELL_NOT_REQUESTED)
                continue
            if not (0.0 <= pri <= 1.0 and 0.0 <= pos <= 1.0):
                _drop(DROP_BELIEF_OUT_OF_RANGE)
                continue
            thr = f.get("threshold")
            thr = float(thr) if isinstance(thr, (int, float)) else None
            if obs == "abs_move_exceeds" and not (thr and 0 < thr < 1.0):
                # The leading suspect: a size bound stated in PERCENT (5) where
                # a fraction (0.05) is required is out of range, and the cell
                # dies silently.
                _drop(DROP_SIZE_BOUND_NOT_A_FRACTION)
                continue
            out.append({"observable": obs, "horizon_days": hz,
                        "threshold": thr, "prior": pri, "posterior": pos,
                        "belief_change": pos - pri,
                        "rationale": str(f.get("rationale", ""))[:600]})
        return out, drops
