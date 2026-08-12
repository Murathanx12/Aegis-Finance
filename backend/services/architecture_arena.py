"""LLM-ARCHITECTURE-ARENA-1 — does the PIPELINE buy what the PERSONA did not?

WHAT THIS IS
============
LLM-SWARM-1 spent 8,014 calls on fourteen specialist personas and measured its
own ceiling: `effective_distinct_ideas` ratio **0.2996**, mean pairwise
probability spread **0.059**, and **27 honest abstentions in 8,014 calls**.
Fourteen roles behaved as one forecaster.

The registered hypothesis (`Aegis module/TRIALS/PREREG_LLM_ARCHITECTURE_ARENA_1.md`,
frozen at 57cf834) is that this is a property of the PROMPT ARCHITECTURE — the
same point-in-time snapshot, the same "you have no live feed", and the same
large output contract for every role — and not of the model. This module is the
instrument that falsifies or supports it.

Six arms, identical items, identical targets, PAIRED:

    A0  SNAPSHOT-PERSONA   the SWARM-1 prompt, byte-for-byte. Control AND corpse.
    A1  FINE-GRAINED       extract -> novelty -> expectedness -> propagate ->
                           market-expectation -> discrepancy -> forecast, seven
                           separate calls with the SMALLEST schema each.
    A2  BELIEF-UPDATE      prior frozen BEFORE evidence, then evidence, then
                           posterior. `posterior == prior` is a FIRST-CLASS
                           answer meaning "this changed nothing".
    A3  ADVERSARIAL        proposer -> refuter -> merge. The merger records what
                           SURVIVED; it does not decide truth.
    A4  TOOL-CALL          the model REQUESTS what it wants from a PIT tool
                           layer instead of being handed a fixed snapshot.
    A5  MODEL TIER         the best arm re-run paired on flash vs pro.

THE FIVE CONSTRAINTS, EACH ONE PAID FOR
---------------------------------------
1. **`served_model` is read off the response body and stored on every row.**
   The requested name is not evidence. On 2026-08-12 `deepseek-chat` and
   `deepseek-reasoner` were both found to resolve server-side to
   `deepseek-v4-flash`, which voided one arm of a running trial that believed it
   was comparing two models. `completion_tokens_details.reasoning_tokens` is
   stored beside it for the same reason: it is a fact the vendor reports and we
   have no other way to reconstruct it.
2. **Historical records go to a SEPARATE ledger.** `predictions.jsonl` stays
   forward-only. Its entire value is that it has never been backfilled, and a
   trial that backfills it to answer a provisional question destroys a property
   that cannot be rebuilt.
3. **A4 never runs a live web search against a historical date.** A search
   executed today against a 2024 date returns the 2026 index; that is leakage by
   construction, not retrieval. Every tool in `TOOL_SPECS` is served from the
   frozen PIT panel or from a static local file, and A4 is FORWARD-ONLY.
4. **The `p = 0.50` refusal is REPLACED in A2, not inherited.** Banning the coin
   flip without offering an alternative is what taught the model to say 0.51 —
   27 abstentions in 8,014 calls is the measurement of that. A2's abstain
   channel is `posterior == prior`, so `allow_coin_flip=True` there and only
   there.
5. **Cost discipline is a design constraint, not an afterthought.** v4-flash
   cached input is 50x cheaper than a miss ($0.0028 vs $0.14/Mtok), so every arm
   except A0 begins from the same `ARENA_PREFIX`. That is simultaneously the
   cheapest design and the correctly paired one. A0 is excluded because A0 must
   be byte-for-byte the SWARM-1 prompt and prepending anything to it would make
   the control a different thing.

WHAT THE NUMBERS MAY AND MAY NOT DO
-----------------------------------
P1 (`effective_distinct_ideas` per dollar) does not depend on outcomes, so it is
immune to the leakage question. It decides WHICH ARM GETS SCALED and nothing
else. No arm receives production weight, specialist authority or a portfolio
role from this trial; that needs resolved forward records and Amendment A5
binds unchanged.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from backend.config import (SWARM_BACKOFF_BASE_S, SWARM_BENCHMARK,
                            SWARM_MAX_FORECASTS_PER_CALL, SWARM_MAX_RETRIES,
                            SWARM_MIN_FORECASTS_PER_CALL, SWARM_TEMPERATURE,
                            SWARM_TIMEOUT_S, WHY_MOVED_FORBIDDEN_PATTERN)
from backend.services import llm_swarm as sw
from backend.services.belief_state import (HORIZONS, Observable,
                                           PredictionRecord, make_prediction)
from backend.services.research_budget import ResearchBudgetExhausted

logger = logging.getLogger(__name__)

MODULE_VERSION = "architecture_arena/1.0.0"
CAMPAIGN = "grand_arena_1"          # the governor's campaign, unchanged
PURPOSE = "architecture_arena_1"
TRIAL = "LLM-ARCHITECTURE-ARENA-1"

FLASH = "deepseek-v4-flash"
PRO = "deepseek-v4-pro"

ARMS = ("A0", "A1", "A2", "A3", "A4")

_FORBIDDEN = re.compile(WHY_MOVED_FORBIDDEN_PATTERN, re.I)


# ── the wire ────────────────────────────────────────────────────────────────

@dataclass
class ArmReply:
    """One wire attempt, carrying the two facts the requested name cannot give.

    `served_model` is read off the response body. `reasoning_tokens` comes from
    `completion_tokens_details`; it is the vendor's own count and there is no
    way to reconstruct it later, so it is stored at call time or not at all.
    """
    text: str
    served_model: str
    requested_model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    latency_ms: float = 0.0
    retries: int = 0
    cost_usd: float | None = None

    @property
    def alias_mismatch(self) -> bool:
        """Did the vendor serve something other than what was asked for?"""
        return self.served_model.strip() != self.requested_model.strip()


def _client(timeout: float = SWARM_TIMEOUT_S):
    import os

    from openai import OpenAI
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is empty. Keys are env-only by house rule; an "
            "arena run with no key must fail loudly rather than quietly produce "
            "nothing and be recorded as a night with no spend.")
    return OpenAI(api_key=key,
                  base_url=os.getenv("DEEPSEEK_BASE_URL",
                                     "https://api.deepseek.com"),
                  timeout=timeout, max_retries=0)


_RETRYABLE = ("429", "500", "502", "503", "504", "timeout", "timed out",
              "connection", "overloaded", "rate limit", "temporarily")


def _is_retryable(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    if getattr(exc, "status_code", None) in (408, 409, 429, 500, 502, 503, 504):
        return True
    return any(t in s for t in _RETRYABLE)


def call_model(messages: list[dict], *, model: str = FLASH, arm: str,
               item: str, step: str, client=None,
               temperature: float = SWARM_TEMPERATURE, max_tokens: int = 900,
               max_retries: int = SWARM_MAX_RETRIES, since: str | None = None,
               telemetry_path: Any = None,
               rng: random.Random | None = None) -> ArmReply:
    """One budget-gated call, priced at the SERVED model.

    `research_budget.require()` runs before EVERY request including every retry,
    because a retry is a request and spends like one. When it raises it
    propagates: an exhausted budget is a campaign-level stop, and absorbed into
    a per-cell failure count it would look like vendor flakiness while the pool
    kept submitting work that can only be refused.

    Priced at `served_model`, never at the requested name. Pricing a v4-pro
    response at the flash rate is exactly the 2.8x error that put ten thousand
    rows in the ledger at the wrong number on 2026-08-12.
    """
    from backend.services import llm_telemetry as tel
    from backend.services import research_budget

    cli = client or _client()
    rnd = rng or random
    retries = 0
    last: Exception | None = None
    t0 = time.perf_counter()
    for attempt in range(max_retries + 1):
        research_budget.require(CAMPAIGN, since=since)
        try:
            resp = cli.chat.completions.create(
                model=model, temperature=temperature, max_tokens=max_tokens,
                response_format={"type": "json_object"}, messages=messages)
        except Exception as exc:                               # noqa: BLE001
            last = exc
            if attempt >= max_retries or not _is_retryable(exc):
                break
            retries += 1
            time.sleep(SWARM_BACKOFF_BASE_S * (2 ** attempt)
                       * (0.5 + rnd.random()))
            continue

        u = tel.extract_usage(resp, "deepseek")
        served = str(getattr(resp, "model", "") or "")
        ctd = getattr(getattr(resp, "usage", None),
                      "completion_tokens_details", None)
        reasoning = int(getattr(ctd, "reasoning_tokens", 0) or 0)
        if not served:
            # An empty `model` on the body means we cannot say what answered.
            # Recorded as such rather than silently backfilled with the request,
            # which is the precise substitution that voided an arm.
            logger.warning("arena: response body carried no model id for "
                           "%s/%s/%s — served_model is UNKNOWN, not %s",
                           arm, item, step, model)
            served = "UNKNOWN"
        reply = ArmReply(text=(resp.choices[0].message.content or ""),
                         served_model=served, requested_model=model,
                         reasoning_tokens=reasoning,
                         latency_ms=(time.perf_counter() - t0) * 1000.0,
                         retries=retries, **u)
        reply.cost_usd = tel.price_call(served, reply.tokens_in,
                                        reply.tokens_out, reply.cached_tokens)
        if reply.alias_mismatch:
            logger.warning("arena: asked %r, served %r — the requested name is "
                           "not evidence (%s/%s/%s)", model, served, arm, item,
                           step)
        try:
            tel.record_call(
                provider="deepseek", model=served, model_version=served,
                purpose=PURPOSE, agent=f"{arm}:{step}",
                prompt=messages, context={"item": item, "arm": arm},
                tokens_in=reply.tokens_in, tokens_out=reply.tokens_out,
                cached_tokens=reply.cached_tokens,
                latency_ms=reply.latency_ms, retries=retries,
                schema_valid=True,
                meta={"trial": TRIAL, "arm": arm, "item": item, "step": step,
                      "requested_model": model, "served_model": served,
                      "alias_mismatch": reply.alias_mismatch,
                      "reasoning_tokens": reasoning,
                      "module": MODULE_VERSION},
                path=telemetry_path)
        except Exception as exc:                               # noqa: BLE001
            logger.warning("arena: telemetry not recorded for %s/%s/%s (%s) — "
                           "the SPEND is missing from the ledger, the reply is "
                           "not", arm, item, step, exc)
        return reply
    assert last is not None
    raise last


#: (messages, model, arm, item, step, max_tokens) -> ArmReply. Injectable so the
#: offline suite never reaches the network.
Caller = Callable[..., ArmReply]


# ── the shared prefix (constraint 5) ────────────────────────────────────────

#: EVERY arm except A0 begins here. A0 is excluded because A0 must be the
#: SWARM-1 prompt byte-for-byte; prepending to the control would make it a
#: different control. Cached input is 50x cheaper than a miss, so this block
#: being long is a feature: it is paid for once per prefix, not once per item.
ARENA_PREFIX = """\
You are one stage of an automated market-research instrument. Everything you
emit is parsed by a machine, written to a ledger, and graded on a fixed date
against actual closes. Nothing you write is a recommendation and nothing you
write reaches a buy or sell surface.

Hard rules that apply at every stage:
- You never state a position size, weight, allocation or action, and you never
  use the words buy, sell, hold, trim, overweight, underweight, take profit or
  stop loss. The engine allocates; you reason.
- Return ONLY valid JSON matching the schema you are given. No prose outside it.
- Do not invent a number you were not shown and cannot derive. "unknown" is an
  available and respected answer everywhere in this instrument.
"""

FORECAST_SCHEMA = f"""\
A FORECAST is exactly this object:
{{"observable": "return_sign"|"beats_benchmark"|"abs_move_exceeds"|"drawdown_exceeds",
 "horizon_days": one of {list(HORIZONS)} (trading days),
 "probability": float in [0,1],
 "threshold": for abs_move_exceeds and drawdown_exceeds a DECIMAL FRACTION
   strictly between 0 and 1 (a 25% move is 0.25, never 25); null for
   return_sign and beats_benchmark,
 "thesis": str, "counter_thesis": str, "next_observable": str}}

`beats_benchmark` is graded against {SWARM_BENCHMARK}. Give
{SWARM_MIN_FORECASTS_PER_CALL} to {SWARM_MAX_FORECASTS_PER_CALL} forecasts
spanning AT LEAST TWO DISTINCT OBSERVABLES and AT LEAST TWO DISTINCT HORIZONS:
a batch that is one observable at one horizon is one forecast wearing several
rows. Choose the horizon your mechanism actually implies — the short ones exist
so a claim about a reaction resolves in days, the long ones so a claim about a
business resolves on the timescale the business works on.
counter_thesis states what would make you wrong; next_observable is one
concrete checkable thing that resolves BEFORE the horizon.
"""


# ── the parse surface ───────────────────────────────────────────────────────

@dataclass
class ArmResult:
    """What one arm produced for one item, including nothing.

    `rejections` is not an error log; it is the measurement of how much of the
    spend bought ungradeable output, and it is what makes cost-per-gradeable
    comparable across arms with different call counts.
    """
    arm: str
    item: str
    status: str = "ok"                      # ok | abstained | zero_yield | failed
    forecasts: list[dict] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)
    replies: list[ArmReply] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    persona: str = ""
    error: str | None = None
    extra: dict = field(default_factory=dict)

    def reject(self, reason: str, detail: str = "") -> None:
        self.rejections.append({"reason": reason, "detail": str(detail)[:300]})

    @property
    def cost_usd(self) -> float:
        """Spend on this (arm, item). Unpriced replies contribute 0 and are
        counted separately, so the total is a LOWER BOUND that says so."""
        return round(sum(float(r.cost_usd) for r in self.replies
                         if r.cost_usd is not None), 8)

    @property
    def n_unpriced(self) -> int:
        return sum(1 for r in self.replies if r.cost_usd is None)

    def as_row(self) -> dict:
        return {
            "arm": self.arm, "item": self.item, "status": self.status,
            "persona": self.persona, "error": self.error,
            "n_calls": len(self.replies),
            "n_forecasts": len(self.forecasts),
            "cost_usd": self.cost_usd, "n_unpriced": self.n_unpriced,
            "tokens_in": sum(r.tokens_in for r in self.replies),
            "tokens_out": sum(r.tokens_out for r in self.replies),
            "cached_tokens": sum(r.cached_tokens for r in self.replies),
            "reasoning_tokens": sum(r.reasoning_tokens for r in self.replies),
            "served_models": sorted({r.served_model for r in self.replies}),
            "requested_models": sorted({r.requested_model for r in self.replies}),
            "alias_mismatch": any(r.alias_mismatch for r in self.replies),
            "latency_ms": round(sum(r.latency_ms for r in self.replies), 1),
            "retries": sum(r.retries for r in self.replies),
            "forecasts": self.forecasts,
            "rejections": self.rejections,
            "trace": self.trace,
            "extra": self.extra,
        }


def extract_json(text: str) -> dict:
    """Parse the model's JSON, including when it fences it."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def validate_forecast(f: Any, out: ArmResult, *,
                      allow_coin_flip: bool = False) -> dict | None:
    """One forecast, or None with the reason it is not one.

    Deliberately the SAME refusals `llm_swarm._validate_forecast` applies, with
    ONE parameter: `allow_coin_flip`. That parameter is the trial's fourth hard
    constraint made executable. A2 freezes a prior before it sees evidence and
    then emits a posterior; `posterior == prior` there is the honest statement
    "this changed nothing", and a prior of 0.50 that stays 0.50 is the most
    informative thing that arm can say. Inheriting the ban would teach the same
    0.51 the ban already taught once, which is the failure this trial exists to
    replace.
    """
    if not isinstance(f, dict):
        out.reject("forecast_not_object", repr(f)[:200])
        return None
    try:
        obs = Observable(str(f.get("observable", "")).strip().lower())
    except ValueError:
        out.reject("unknown_observable", repr(f.get("observable")))
        return None
    try:
        h = int(f.get("horizon_days"))
    except (TypeError, ValueError):
        out.reject("horizon_not_numeric", repr(f.get("horizon_days")))
        return None
    if h not in HORIZONS:
        out.reject("horizon_not_frozen", f"{h} is not one of {list(HORIZONS)}")
        return None
    try:
        p = float(f.get("probability"))
    except (TypeError, ValueError):
        out.reject("probability_not_numeric", repr(f.get("probability")))
        return None
    if not 0.0 <= p <= 1.0:
        out.reject("probability_not_a_credence", repr(p))
        return None
    if not allow_coin_flip and abs(p - 0.5) < 0.005:
        out.reject("coin_flip_filler", f"p={p}")
        return None
    thr = f.get("threshold")
    if thr is not None:
        try:
            thr = float(thr)
        except (TypeError, ValueError):
            out.reject("threshold_not_numeric", repr(f.get("threshold")))
            return None
    if obs in (Observable.ABS_MOVE_EXCEEDS, Observable.DRAWDOWN_EXCEEDS):
        if thr is None:
            out.reject("threshold_missing", f"{obs.value} cannot resolve")
            return None
        if not 0.0 < thr < 1.0:
            # The percent/fraction mixup. A threshold of 20.0 is a 2000% move;
            # at p=0.75 that is a guaranteed-wrong record scored against an arm
            # whose reasoning had nothing to do with it. Six of these reached a
            # live ledger the one time the refusal was swallowed.
            out.reject("threshold_not_a_fraction",
                       f"{thr} is almost certainly percent, not a fraction")
            return None
    elif thr is not None:
        thr = None
    ct = str(f.get("counter_thesis", "")).strip()
    if not ct:
        out.reject("no_counter_thesis", "a forecast with no stated way of being "
                                        "wrong is not falsifiable")
        return None
    blob = f"{f.get('thesis', '')} {ct} {f.get('next_observable', '')}"
    hits = _FORBIDDEN.findall(blob)
    if hits:
        out.reject("recommendation_language",
                   f"matched {sorted({str(x).lower() for x in hits})}")
        return None
    return {"observable": obs.value, "horizon_days": h, "probability": p,
            "threshold": thr, "thesis": str(f.get("thesis", "")).strip()[:600],
            "counter_thesis": ct[:600],
            "next_observable": str(f.get("next_observable", "")).strip()[:600]}


def _monoculture(forecasts: Sequence[dict]) -> bool:
    """Is this batch one forecast wearing several rows?"""
    if len(forecasts) < 2:
        return False
    return len({(f["observable"], f["horizon_days"]) for f in forecasts}) == 1


def finish(out: ArmResult, raw_forecasts: Any, *,
           allow_coin_flip: bool = False) -> ArmResult:
    """Validate an arm's final forecast list and set the status. Shared by all
    arms so the yield definition cannot drift between them — a comparison of
    ideas per dollar across arms that scored their output by different rules
    would be measuring the rules."""
    if not isinstance(raw_forecasts, list) or not raw_forecasts:
        out.reject("no_forecasts", "the final stage emitted nothing gradeable")
        out.status = "zero_yield"
        return out
    kept: list[dict] = []
    for f in raw_forecasts[:SWARM_MAX_FORECASTS_PER_CALL]:
        v = validate_forecast(f, out, allow_coin_flip=allow_coin_flip)
        if v is not None:
            kept.append(v)
    if len(raw_forecasts) > SWARM_MAX_FORECASTS_PER_CALL:
        out.reject("forecasts_past_cap",
                   f"{len(raw_forecasts) - SWARM_MAX_FORECASTS_PER_CALL} past "
                   f"the cap of {SWARM_MAX_FORECASTS_PER_CALL}")
    if not kept:
        out.status = "zero_yield"
        return out
    if _monoculture(kept):
        out.reject("monoculture_batch",
                   f"all {len(kept)} are {kept[0]['observable']}@"
                   f"{kept[0]['horizon_days']}d — refused whole")
        out.status = "zero_yield"
        return out
    out.forecasts = kept
    out.status = "ok"
    return out


def _compact(snapshot: dict) -> str:
    return json.dumps(snapshot, indent=1, sort_keys=True, default=str)


def _identity(snapshot: dict) -> dict:
    """The non-price facts about a name: who it is, not how it has traded.

    A2's prior call sees ONLY this. That is what makes it a prior — a credence
    formed before the evidence, which is the object the posterior is compared
    against.
    """
    return {k: snapshot.get(k) for k in
            ("ticker", "company_name", "sector", "industry", "as_of")
            if snapshot.get(k) is not None}


# ── A0 · SNAPSHOT-PERSONA (control and corpse) ──────────────────────────────

def run_a0(snapshot: dict, *, persona: str, caller: Caller,
           model: str = FLASH, **kw: Any) -> ArmResult:
    """The SWARM-1 prompt, byte-for-byte, parsed by the SWARM-1 parser.

    `llm_swarm.build_prompt` and `llm_swarm.parse_reply` are CALLED, never
    reimplemented. A control that had been retyped would be a fifth arm wearing
    the control's name, and the whole trial is an attempt to beat a thing we
    already built and already measured.
    """
    item = str(snapshot.get("ticker", "")).upper()
    out = ArmResult(arm="A0", item=item, persona=persona)
    system, user = sw.build_prompt(persona, snapshot, benchmark=SWARM_BENCHMARK)
    reply = caller([{"role": "system", "content": system},
                    {"role": "user", "content": user}],
                   model=model, arm="A0", item=item, step=f"snapshot:{persona}",
                   max_tokens=1800)
    out.replies.append(reply)
    parsed = sw.parse_reply(persona, snapshot, reply.text)
    out.rejections.extend({"reason": r["reason"], "detail": r["detail"]}
                          for r in parsed.rejections)
    if parsed.abstained:
        out.status = "abstained"
        out.extra["abstain_reason"] = parsed.abstain_reason
        return out
    if not parsed.forecasts:
        out.status = "zero_yield"
        return out
    out.forecasts = parsed.forecasts
    out.extra["confidence"] = parsed.confidence
    out.status = "ok"
    return out


# ── A1 · FINE-GRAINED ───────────────────────────────────────────────────────

_A1_STEPS = ("extract", "novelty", "expectedness", "propagate",
             "market_expectation", "discrepancy", "forecast")

_A1_SYS = {
    "extract": ARENA_PREFIX + """
STAGE: EXTRACT. You are given a point-in-time snapshot of one security. Name
the two or three facts in it that most distinguish this security from a random
member of its sector. Nothing else. No interpretation, no forecast.
Schema: {"facts": [{"fact": str, "field": str, "value": str}]}""",

    "novelty": ARENA_PREFIX + """
STAGE: NOVELTY. For each fact you are given, say whether it is NEW information
or a stale restatement of something the market has had for months. Nothing
else. A fact can be large and not novel.
Schema: {"novelty": [{"fact": str, "novel": true|false, "why": str}]}""",

    "expectedness": ARENA_PREFIX + """
STAGE: EXPECTEDNESS. For each fact, say whether it is what you would ALREADY
EXPECT given the sector and the general regime, or a surprise relative to that
baseline. Nothing else.
Schema: {"expectedness": [{"fact": str, "expected": true|false, "why": str}]}""",

    "propagate": ARENA_PREFIX + """
STAGE: CAUSAL PROPAGATION. Given the facts and their novelty and expectedness,
state the mechanical chain by which each one transmits into this security's
price or volatility. One link per row, each link a thing that could be checked.
Nothing else.
Schema: {"propagation": [{"from": str, "to": str, "mechanism": str,
 "sign": "+"|"-"|"ambiguous", "lag": "days"|"weeks"|"quarters"}]}""",

    "market_expectation": ARENA_PREFIX + """
STAGE: MARKET EXPECTATION. State in one sentence what the CURRENT PRICE already
embeds about this security, and name the observable number in which that
expectation is visible. You are not stating your own view here. Nothing else.
Schema: {"market_expects": str, "visible_in": str, "confidence_in_reading":
 "high"|"medium"|"low"}""",

    "discrepancy": ARENA_PREFIX + """
STAGE: DISCREPANCY. You are given the causal chain and the market's embedded
expectation. State ONLY where the two differ, and how large the difference is.
"none" is a complete and respected answer: most securities on most days carry
no discrepancy, and saying so is worth more than manufacturing one.
Schema: {"discrepancy": str, "magnitude": "none"|"small"|"large",
 "direction": "up"|"down"|"volatility"|"none"}""",

    "forecast": ARENA_PREFIX + FORECAST_SCHEMA + """
STAGE: FORECAST. You are given the whole chain that preceded you: facts,
novelty, expectedness, propagation, the market's embedded expectation and the
discrepancy. Emit forecasts that follow from THAT CHAIN and from nothing else.
If the discrepancy was "none", your probabilities should look like base rates,
and that is the correct output rather than a failure.
Schema: {"forecasts": [FORECAST, ...]}""",
}


def run_a1(snapshot: dict, *, caller: Caller, model: str = FLASH,
           **kw: Any) -> ArmResult:
    """Seven separate calls, the smallest schema each, chained.

    The chain carries FORWARD only the compact JSON each stage emitted, never
    the prose of the stage before it. That is the decomposition being tested: if
    one big output contract is what collapsed fourteen personas into one
    forecaster, then seven small contracts that each answer one question should
    leave more of the model's disagreement with itself intact.
    """
    item = str(snapshot.get("ticker", "")).upper()
    out = ArmResult(arm="A1", item=item)
    ctx: dict[str, Any] = {}
    snap_txt = _compact(snapshot)

    for step in _A1_STEPS:
        if step == "extract":
            user = f"Point-in-time snapshot:\n{snap_txt}"
        elif step in ("novelty", "expectedness"):
            user = (f"Security {item}, sector "
                    f"{snapshot.get('sector', 'Unknown')}.\n"
                    f"Facts:\n{json.dumps(ctx.get('extract', {}), indent=1)}")
        elif step == "propagate":
            user = ("Facts, novelty and expectedness:\n"
                    + json.dumps({k: ctx.get(k) for k in
                                  ("extract", "novelty", "expectedness")},
                                 indent=1, default=str))
        elif step == "market_expectation":
            user = f"Point-in-time snapshot:\n{snap_txt}"
        elif step == "discrepancy":
            user = ("Causal chain:\n"
                    + json.dumps(ctx.get("propagate"), indent=1, default=str)
                    + "\n\nMarket's embedded expectation:\n"
                    + json.dumps(ctx.get("market_expectation"), indent=1,
                                 default=str))
        else:
            user = ("The whole chain:\n"
                    + json.dumps(ctx, indent=1, default=str)
                    + f"\n\nSecurity {item}. Last close "
                    + f"{snapshot.get('last_close')} as of "
                    + f"{snapshot.get('as_of')}.")

        max_tok = 1000 if step == "forecast" else 500
        reply = caller([{"role": "system", "content": _A1_SYS[step]},
                        {"role": "user", "content": user}],
                       model=model, arm="A1", item=item, step=step,
                       max_tokens=max_tok)
        out.replies.append(reply)
        try:
            ctx[step] = extract_json(reply.text)
        except Exception as exc:                               # noqa: BLE001
            # A broken link breaks the chain. Recorded with the stage name so
            # the failure is attributable to a stage rather than to the arm — a
            # decomposition whose third stage never parses is a different
            # finding from a decomposition that does not help.
            out.reject(f"unparseable_json:{step}",
                       f"{type(exc).__name__}: {exc}")
            out.status = "zero_yield"
            return out
        out.trace.append({"step": step, "chars": len(reply.text)})

    out.extra["discrepancy_magnitude"] = str(
        (ctx.get("discrepancy") or {}).get("magnitude", ""))
    out.extra["chain"] = {k: ctx.get(k) for k in
                          ("market_expectation", "discrepancy")}
    return finish(out, (ctx.get("forecast") or {}).get("forecasts"))


# ── A2 · BELIEF-UPDATE ──────────────────────────────────────────────────────

_A2_PRIOR_SYS = ARENA_PREFIX + FORECAST_SCHEMA + """
STAGE: PRIOR. You are told WHO this security is and nothing about how it has
traded. Freeze a prior: for two or three (observable, horizon, threshold) slots
of your choosing, state the credence you hold BEFORE seeing any evidence, from
base rates and general knowledge alone.

PROBABILITY 0.50 IS PERMITTED AND OFTEN CORRECT HERE. A prior of one half on
the sign of a one-day return is not laziness, it is the base rate. Do not
manufacture precision you do not have; you will be shown evidence next, and the
thing that gets graded is how far it moves you.

Schema: {"prior": [{"observable": ..., "horizon_days": ..., "threshold": ...,
 "probability": float, "basis": str}]}
Omit thesis/counter_thesis/next_observable at this stage.
"""

_A2_POST_SYS = ARENA_PREFIX + FORECAST_SCHEMA + """
STAGE: POSTERIOR. You are given the prior YOU froze before seeing anything, and
now the evidence. For EACH slot in the prior — the same observable, the same
horizon, the same threshold, in the same order — emit a posterior.

`posterior == prior` IS A FIRST-CLASS ANSWER. It means "this evidence changed
nothing", which is true of most evidence about most securities on most days,
and it is the honest alternative to nudging a number to look like work. Set
"unchanged": true and repeat the probability. That is a complete answer and it
is recorded as one.

For every slot state which SPECIFIC piece of evidence moved you (or that none
did) and how good that evidence is.

Schema: {"posterior": [{"observable": ..., "horizon_days": ..., "threshold": ...,
 "probability": float, "unchanged": true|false, "moved_by": str,
 "evidence_quality": "strong"|"weak"|"none",
 "thesis": str, "counter_thesis": str, "next_observable": str}]}
"""


def run_a2(snapshot: dict, *, caller: Caller, model: str = FLASH,
           **kw: Any) -> ArmResult:
    """Prior frozen before the evidence, then posterior. Two calls.

    The `p = 0.50` refusal is REPLACED here, not inherited (constraint 4). The
    ban is what taught the model to say 0.51: 27 honest abstentions in 8,014
    calls is the measurement of a forecaster that had been given no way to say
    "I don't know" that it would not be punished for. Structure replaces
    prohibition — the abstain channel is `posterior == prior`.
    """
    item = str(snapshot.get("ticker", "")).upper()
    out = ArmResult(arm="A2", item=item)

    prior_reply = caller(
        [{"role": "system", "content": _A2_PRIOR_SYS},
         {"role": "user", "content":
          "Security identity only — you are shown no prices, no returns and no "
          "volatility:\n" + json.dumps(_identity(snapshot), indent=1)}],
        model=model, arm="A2", item=item, step="prior", max_tokens=700)
    out.replies.append(prior_reply)
    try:
        prior = (extract_json(prior_reply.text) or {}).get("prior")
    except Exception as exc:                                   # noqa: BLE001
        out.reject("unparseable_json:prior", f"{type(exc).__name__}: {exc}")
        out.status = "zero_yield"
        return out
    if not isinstance(prior, list) or not prior:
        out.reject("no_prior", "a posterior with no prior is just a forecast")
        out.status = "zero_yield"
        return out

    post_reply = caller(
        [{"role": "system", "content": _A2_POST_SYS},
         {"role": "user", "content":
          "The prior you froze:\n" + json.dumps(prior, indent=1, default=str)
          + "\n\nThe evidence (point-in-time; every number computed from closes "
            f"at or before {snapshot.get('as_of')}):\n" + _compact(snapshot)}],
        model=model, arm="A2", item=item, step="posterior", max_tokens=1200)
    out.replies.append(post_reply)
    try:
        post = (extract_json(post_reply.text) or {}).get("posterior")
    except Exception as exc:                                   # noqa: BLE001
        out.reject("unparseable_json:posterior", f"{type(exc).__name__}: {exc}")
        out.status = "zero_yield"
        return out

    # The belief UPDATE is the arm's own object, so it is measured here rather
    # than left to be reconstructed. Slots are matched on (observable, horizon,
    # threshold); a posterior that answered a different question than the prior
    # asked is counted, not silently paired.
    def key(r: Any) -> tuple:
        if not isinstance(r, dict):
            return ()
        return (str(r.get("observable", "")).lower(),
                r.get("horizon_days"),
                None if r.get("threshold") is None else round(
                    float(r["threshold"]), 4)
                if _num(r.get("threshold")) else None)

    pri = {key(r): _num(r.get("probability")) for r in prior
           if isinstance(r, dict)}
    deltas, unchanged, unmatched = [], 0, 0
    for r in (post if isinstance(post, list) else []):
        if not isinstance(r, dict):
            continue
        p0 = pri.get(key(r))
        p1 = _num(r.get("probability"))
        if p0 is None or p1 is None:
            unmatched += 1
            continue
        deltas.append(abs(p1 - p0))
        if bool(r.get("unchanged")) or abs(p1 - p0) < 1e-9:
            unchanged += 1
    out.extra.update({
        "n_prior_slots": len(prior),
        "n_matched_slots": len(deltas),
        "n_unmatched_posterior_slots": unmatched,
        "mean_abs_belief_update": (round(sum(deltas) / len(deltas), 4)
                                   if deltas else None),
        "max_abs_belief_update": (round(max(deltas), 4) if deltas else None),
        "n_posterior_equals_prior": unchanged,
        "prior_probabilities": [v for v in pri.values() if v is not None],
        "evidence_quality": [str(r.get("evidence_quality", ""))
                             for r in (post or []) if isinstance(r, dict)],
    })
    if unmatched:
        out.reject("posterior_slot_not_in_prior",
                   f"{unmatched} posterior row(s) answer a question the prior "
                   f"did not ask — the update for those is not measurable")
    return finish(out, post, allow_coin_flip=True)


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── A3 · ADVERSARIAL ────────────────────────────────────────────────────────

_A3_PROPOSE_SYS = ARENA_PREFIX + FORECAST_SCHEMA + """
STAGE: PROPOSER. State the strongest security-specific claim the snapshot
supports, and the forecasts that follow from it. You will be attacked by a
refuter who sees exactly what you wrote, so do not overreach: a claim that dies
under the first attack costs this instrument a whole item.
Schema: {"claim": str, "forecasts": [FORECAST, ...]}"""

_A3_REFUTE_SYS = ARENA_PREFIX + """
STAGE: REFUTER. You are shown a proposal. Your job is to ATTACK it, one attack
per forecast, and you are not permitted to agree in general terms. For each
forecast name the specific way it fails: the base rate it ignores, the factor
that already explains the move, the confound, or the mechanism that does not
transmit at that horizon. State the probability YOU would put on the same
observable.
An attack of severity "fatal" means the forecast should not be recorded at all.
Schema: {"attacks": [{"target_index": int, "attack": str,
 "severity": "fatal"|"serious"|"minor", "your_probability": float}]}"""

_A3_MERGE_SYS = ARENA_PREFIX + FORECAST_SCHEMA + """
STAGE: MERGE. You are shown a proposal and the attacks on it. YOU DO NOT DECIDE
WHO IS RIGHT. You record what SURVIVED: a forecast survives if its attack was
not fatal, and it survives with a probability that reflects the attack rather
than ignoring it. A forecast whose attack was fatal is dropped and named in
"killed" — dropping it is the arm working, not the arm failing.
Schema: {"surviving": [FORECAST + {"survived_because": str}],
 "killed": [{"observable": str, "horizon_days": int, "killed_by": str}]}"""


def run_a3(snapshot: dict, *, caller: Caller, model: str = FLASH,
           **kw: Any) -> ArmResult:
    """Proposer, then a refuter that sees the proposal, then a merge.

    The merger is explicitly forbidden from deciding truth. An arbiter that
    picks a winner is a third opinion from the same model wearing a judge's
    hat; what this arm can honestly produce is the record of which claims
    survived contact with an attack, and that is what it is asked for.
    """
    item = str(snapshot.get("ticker", "")).upper()
    out = ArmResult(arm="A3", item=item)
    snap_txt = _compact(snapshot)

    prop_reply = caller([{"role": "system", "content": _A3_PROPOSE_SYS},
                         {"role": "user", "content":
                          f"Point-in-time snapshot:\n{snap_txt}"}],
                        model=model, arm="A3", item=item, step="propose",
                        max_tokens=1100)
    out.replies.append(prop_reply)
    try:
        prop = extract_json(prop_reply.text)
    except Exception as exc:                                   # noqa: BLE001
        out.reject("unparseable_json:propose", f"{type(exc).__name__}: {exc}")
        out.status = "zero_yield"
        return out
    proposed = prop.get("forecasts")
    if not isinstance(proposed, list) or not proposed:
        out.reject("no_proposal", "the proposer produced nothing to attack")
        out.status = "zero_yield"
        return out

    ref_reply = caller([{"role": "system", "content": _A3_REFUTE_SYS},
                        {"role": "user", "content":
                         f"Point-in-time snapshot:\n{snap_txt}\n\nThe proposal "
                         f"(forecasts are indexed from 0):\n"
                         + json.dumps(prop, indent=1, default=str)}],
                       model=model, arm="A3", item=item, step="refute",
                       max_tokens=900)
    out.replies.append(ref_reply)
    try:
        attacks = (extract_json(ref_reply.text) or {}).get("attacks")
    except Exception as exc:                                   # noqa: BLE001
        out.reject("unparseable_json:refute", f"{type(exc).__name__}: {exc}")
        out.status = "zero_yield"
        return out

    merge_reply = caller([{"role": "system", "content": _A3_MERGE_SYS},
                          {"role": "user", "content":
                           "The proposal:\n"
                           + json.dumps(prop, indent=1, default=str)
                           + "\n\nThe attacks:\n"
                           + json.dumps(attacks, indent=1, default=str)}],
                         model=model, arm="A3", item=item, step="merge",
                         max_tokens=1100)
    out.replies.append(merge_reply)
    try:
        merged = extract_json(merge_reply.text)
    except Exception as exc:                                   # noqa: BLE001
        out.reject("unparseable_json:merge", f"{type(exc).__name__}: {exc}")
        out.status = "zero_yield"
        return out

    sev = [str(a.get("severity", "")).lower()
           for a in (attacks or []) if isinstance(a, dict)]
    killed = merged.get("killed") or []
    out.extra.update({
        "n_proposed": len(proposed),
        "n_attacks": len(sev),
        "n_fatal_attacks": sum(1 for s in sev if s == "fatal"),
        "n_killed_by_merge": len(killed) if isinstance(killed, list) else 0,
        "proposer_probabilities": [_num(f.get("probability"))
                                   for f in proposed if isinstance(f, dict)],
        "refuter_probabilities": [_num(a.get("your_probability"))
                                  for a in (attacks or [])
                                  if isinstance(a, dict)],
    })
    surviving = merged.get("surviving")
    if isinstance(surviving, list) and not surviving:
        # Every claim died. That is a REAL output of this architecture and it is
        # a form of yield the other arms cannot produce — but it mints no
        # gradeable record, so it is counted as zero_yield with its own reason
        # rather than dressed up as information.
        out.reject("all_claims_killed",
                   "every proposed forecast was fatally attacked and the merge "
                   "recorded no survivor — an honest empty, not a parse failure")
        out.status = "zero_yield"
        return out
    return finish(out, surviving)


# ── A4 · TOOL-CALL (forward-only, no live web search) ───────────────────────

#: The tool layer. EVERY tool is served from the frozen PIT panel or from a
#: static local file, and there is NO web search of any kind. Constraint 3: a
#: search executed today against a historical date returns today's index, which
#: is leakage by construction rather than retrieval. This arm is FORWARD-ONLY —
#: its observation timestamp is the most recent close available, so "PIT" here
#: costs nothing and is checkable.
TOOL_SPECS: dict[str, str] = {
    "prices": "Trailing returns and last close for the security. args: {}",
    "factors": "Beta vs the benchmark, realised volatility, drawdown state and "
               "excess return vs the benchmark. args: {}",
    "identity": "Company name, sector, industry, market cap, short interest. "
                "args: {}",
    "peers": "Up to 5 same-sector names with their trailing returns and vol, so "
             "you can tell a security-specific move from a sector one. args: "
             "{\"n\": int}",
    "macro": "Benchmark trailing returns and the market backdrop available at "
             "the observation timestamp. args: {}",
    "prior_experiments": "Search Aegis's own registry of already-run "
                         "experiments and their kill conditions. args: "
                         "{\"query\": str}",
}


@dataclass
class ToolContext:
    """Everything the tool layer is allowed to serve. Frozen at construction.

    Passing the whole world in and letting each tool slice it is what keeps the
    PIT guarantee checkable in one place: no tool holds a network handle, so no
    tool CAN answer with information from after the observation timestamp.
    """
    snapshot: dict
    peers: list[dict] = field(default_factory=list)
    registry: list[dict] = field(default_factory=list)


def serve_tool(name: str, args: dict, ctx: ToolContext) -> dict:
    """Answer one tool request, or say plainly that it cannot be answered.

    An unavailable tool returns `{"available": false, "reason": ...}` and is
    COUNTED. That is a measurement in its own right — what the model asks for
    against what this programme can actually serve — and it is the honest
    alternative to a stub that returns an empty dict and reads as "nothing
    there".
    """
    s = ctx.snapshot
    if name == "prices":
        return {"available": True,
                "last_close": s.get("last_close"),
                "as_of": s.get("as_of"),
                "trailing_return_pct": s.get("trailing_return_pct"),
                "n_bars_available": s.get("n_bars_available")}
    if name == "factors":
        return {"available": True,
                "beta_vs_benchmark": s.get("beta_vs_benchmark"),
                "realised_vol_annualised_pct":
                    s.get("realised_vol_annualised_pct"),
                "max_drawdown_1y_pct": s.get("max_drawdown_1y_pct"),
                "pct_below_1y_high": s.get("pct_below_1y_high"),
                "pct_above_1y_low": s.get("pct_above_1y_low"),
                "excess_return_63d_pct_vs_benchmark":
                    s.get("excess_return_63d_pct_vs_benchmark")}
    if name == "identity":
        return {"available": True, **_identity(s),
                "market_cap_usd": s.get("market_cap_usd"),
                "shares_short_pct_float": s.get("shares_short_pct_float")}
    if name == "peers":
        n = int(args.get("n") or 5)
        if not ctx.peers:
            return {"available": False,
                    "reason": "no same-sector peer with enough history at the "
                              "observation timestamp is in the frozen universe"}
        return {"available": True, "peers": ctx.peers[:max(1, min(n, 8))]}
    if name == "macro":
        return {"available": True,
                "benchmark": s.get("benchmark"),
                "benchmark_trailing_return_pct":
                    s.get("benchmark_trailing_return_pct"),
                "note": "no live feed exists behind this tool; these are closes "
                        "at or before the observation timestamp"}
    if name == "prior_experiments":
        q = str(args.get("query") or "").lower().strip()
        if not ctx.registry:
            return {"available": False,
                    "reason": "the experiment registry was not loadable"}
        if not q:
            return {"available": True,
                    "n_experiments": len(ctx.registry),
                    "note": "pass a query to search"}
        terms = [t for t in re.split(r"\W+", q) if len(t) > 3]
        hits = []
        for r in ctx.registry:
            blob = " ".join(str(r.get(k, "")) for k in
                            ("name", "hypothesis", "kill_condition")).lower()
            if any(t in blob for t in terms):
                hits.append({"name": r.get("name"),
                             "hypothesis": str(r.get("hypothesis", ""))[:400],
                             "kill_condition": str(
                                 r.get("kill_condition", ""))[:250]})
        return {"available": True, "n_matches": len(hits), "matches": hits[:4]}
    return {"available": False,
            "reason": f"no tool named {name!r}; available tools are "
                      f"{sorted(TOOL_SPECS)}"}


_A4_SYS = ARENA_PREFIX + FORECAST_SCHEMA + f"""
STAGE: RETRIEVAL AND FORECAST. You are NOT handed a snapshot. You are told which
security to forecast and given a tool layer; ask it for exactly what you want
and nothing you do not.

There is NO web search and NO news feed behind these tools, and there will not
be one. Every tool answers from closes at or before the observation timestamp
or from a static local file. A tool that cannot answer says so; an unavailable
tool is information about this programme and you should reason with the absence
rather than around it.

Tools:
{json.dumps(TOOL_SPECS, indent=1)}

Each turn, reply with EXACTLY ONE of:
  {{"tool_calls": [{{"tool": str, "args": object}}, ...]}}   to request data
  {{"forecasts": [FORECAST, ...], "used": [str, ...]}}        when you are ready

You have at most {{max_rounds}} rounds of tool calls. Requesting nothing and
forecasting immediately is permitted and is itself a statement about how much
these tools are worth.
"""


def run_a4(snapshot: dict, *, caller: Caller, model: str = FLASH,
           ctx: ToolContext | None = None, max_rounds: int = 3,
           **kw: Any) -> ArmResult:
    """The model requests what it wants instead of being handed a snapshot.

    The protocol is a hand-rolled JSON request loop rather than the vendor's
    function-calling API, and the report says so. The reason is that every other
    arm runs under `response_format=json_object`; switching transports for one
    arm would put a second uncontrolled difference into a paired comparison, and
    what is being tested is whether CHOOSING the inputs helps, not whether one
    wire format parses better than another.

    The full tool trace is recorded — which tools were asked for, in what order,
    with what arguments, and which came back unavailable.
    """
    item = str(snapshot.get("ticker", "")).upper()
    out = ArmResult(arm="A4", item=item)
    ctx = ctx or ToolContext(snapshot=snapshot)
    system = _A4_SYS.replace("{max_rounds}", str(max_rounds))
    msgs: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content":
         f"Forecast the security {item}. The observation timestamp is "
         f"{snapshot.get('as_of')}. You know nothing else about it yet."}]

    n_unavailable = 0
    for rnd_i in range(max_rounds + 1):
        reply = caller(msgs, model=model, arm="A4", item=item,
                       step=f"round{rnd_i}", max_tokens=1100)
        out.replies.append(reply)
        try:
            body = extract_json(reply.text)
        except Exception as exc:                               # noqa: BLE001
            out.reject(f"unparseable_json:round{rnd_i}",
                       f"{type(exc).__name__}: {exc}")
            out.status = "zero_yield"
            return out

        if isinstance(body.get("forecasts"), list):
            out.extra.update({"n_tool_rounds": rnd_i,
                              "n_tool_calls": len(out.trace),
                              "n_tools_unavailable": n_unavailable,
                              "tools_used": [t["tool"] for t in out.trace],
                              "claimed_used": body.get("used")})
            return finish(out, body["forecasts"])

        reqs = body.get("tool_calls")
        if not isinstance(reqs, list) or not reqs:
            out.reject(f"neither_tool_call_nor_forecast:round{rnd_i}",
                       json.dumps(body)[:200])
            out.status = "zero_yield"
            return out
        if rnd_i >= max_rounds:
            # Out of rounds and still asking. Counted with its own reason: an
            # arm that never stops retrieving is a different failure from one
            # whose forecast did not parse, and folding them together would hide
            # the more interesting of the two.
            out.reject("tool_budget_exhausted",
                       f"still requesting tools after {max_rounds} rounds")
            out.status = "zero_yield"
            out.extra.update({"n_tool_rounds": rnd_i,
                              "n_tool_calls": len(out.trace),
                              "n_tools_unavailable": n_unavailable})
            return out

        results = []
        for r in reqs[:6]:
            if not isinstance(r, dict):
                continue
            tname = str(r.get("tool", ""))
            targs = r.get("args") if isinstance(r.get("args"), dict) else {}
            res = serve_tool(tname, targs, ctx)
            if not res.get("available"):
                n_unavailable += 1
            out.trace.append({"round": rnd_i, "tool": tname, "args": targs,
                              "available": bool(res.get("available"))})
            results.append({"tool": tname, "result": res})
        msgs.append({"role": "assistant", "content": reply.text})
        msgs.append({"role": "user",
                     "content": "Tool results:\n"
                                + json.dumps(results, indent=1, default=str)})

    out.status = "zero_yield"                                  # unreachable
    return out


RUNNERS: dict[str, Callable[..., ArmResult]] = {
    "A0": run_a0, "A1": run_a1, "A2": run_a2, "A3": run_a3, "A4": run_a4,
}


# ── P1: effective distinct ideas per dollar ─────────────────────────────────

def effective_distinct_ideas(preds: Sequence[dict]) -> dict:
    """CANON §20, the SAME implementation the 0.2996 measurement used.

    Called, not reimplemented. This number's only value is that it is comparable
    to the one that motivated the trial, and a retyped version of it would be a
    different number wearing the same name.
    """
    return sw.effective_distinct_ideas(list(preds))


def _idea_keys(forecasts: Sequence[dict], item: str) -> set[tuple]:
    """The §20 buckets one item contributes.

    Buckets are keyed on (ticker, observable, probability/0.05), so two
    DIFFERENT tickers can never share one. That is what makes the effective-idea
    count ADDITIVE across items — and additivity is the only reason a per-item
    bootstrap and a paired per-item difference are legitimate here rather than
    an approximation.
    """
    return {(item, f["observable"], round(float(f["probability"]) / 0.05))
            for f in forecasts}


def arm_metrics(rows: Sequence[dict]) -> dict:
    """P1 and everything reported beside it, for one arm.

    `ideas_per_usd` is a ratio of SUMS, not a mean of ratios: an item that cost
    a tenth of a cent and produced one idea must not carry the same weight as
    one that cost ten times more. The per-item ratios are computed too, but only
    for the paired difference that the MDE is built on.
    """
    items = sorted({r["item"] for r in rows})
    per_item_ideas: dict[str, int] = {}
    per_item_cost: dict[str, float] = {}
    per_item_calls: dict[str, int] = {}
    n_forecasts = 0
    for it in items:
        rs = [r for r in rows if r["item"] == it]
        keys: set[tuple] = set()
        for r in rs:
            keys |= _idea_keys(r.get("forecasts") or [], it)
            n_forecasts += len(r.get("forecasts") or [])
        per_item_ideas[it] = len(keys)
        per_item_cost[it] = round(sum(float(r.get("cost_usd") or 0.0)
                                      for r in rs), 10)
        per_item_calls[it] = sum(int(r.get("n_calls") or 0) for r in rs)

    total_ideas = sum(per_item_ideas.values())
    total_cost = round(sum(per_item_cost.values()), 8)
    n_calls = sum(per_item_calls.values())
    status = {}
    for r in rows:
        status[r["status"]] = status.get(r["status"], 0) + 1
    gradeable = status.get("ok", 0)
    return {
        "n_items": len(items),
        "n_cells": len(rows),
        "n_calls": n_calls,
        "n_forecasts": n_forecasts,
        "effective_distinct_ideas": total_ideas,
        "ratio_ideas_per_forecast": (round(total_ideas / n_forecasts, 4)
                                     if n_forecasts else None),
        "cost_usd": total_cost,
        "ideas_per_usd": (round(total_ideas / total_cost, 2)
                          if total_cost > 0 else None),
        "cost_per_idea_usd": (round(total_cost / total_ideas, 6)
                              if total_ideas else None),
        "cost_per_call_usd": (round(total_cost / n_calls, 6)
                              if n_calls else None),
        "cost_per_gradeable_cell_usd": (round(total_cost / gradeable, 6)
                                        if gradeable else None),
        "status_counts": status,
        "gradeable_rate": (round(gradeable / len(rows), 4) if rows else None),
        "abstention_rate": (round(status.get("abstained", 0) / len(rows), 4)
                            if rows else None),
        "zero_yield_rate": (round(1 - gradeable / len(rows), 4)
                            if rows else None),
        "n_unpriced_replies": sum(int(r.get("n_unpriced") or 0) for r in rows),
        "tokens_in": sum(int(r.get("tokens_in") or 0) for r in rows),
        "tokens_out": sum(int(r.get("tokens_out") or 0) for r in rows),
        "cached_tokens": sum(int(r.get("cached_tokens") or 0) for r in rows),
        "reasoning_tokens": sum(int(r.get("reasoning_tokens") or 0)
                                for r in rows),
        "served_models": sorted({m for r in rows
                                 for m in (r.get("served_models") or [])}),
        "n_alias_mismatch": sum(1 for r in rows if r.get("alias_mismatch")),
        "_per_item_ideas": per_item_ideas,
        "_per_item_cost": per_item_cost,
    }


def bootstrap_a0_dispersion(a0_rows: Sequence[dict], *, n_boot: int = 4000,
                            seed: int = 20260812) -> dict:
    """A0's own dispersion, resampling ITEMS with replacement.

    The prereg's decision rule needs a threshold rather than a vibe: an arm
    whose P1 does not exceed A0's by more than A0's own measured dispersion is
    NOT DETECTABLY BETTER (§19) and is recorded as such, never as a kill. This
    supplies that dispersion.

    Items are the resampling unit, not forecasts. Two forecasts about the same
    security are not two independent draws — §20 exists because of exactly that
    — and bootstrapping forecasts would manufacture precision the design does
    not have.
    """
    m = arm_metrics(a0_rows)
    items = sorted(m["_per_item_ideas"])
    if not items:
        return {"n_boot": 0, "reason": "A0 produced no item"}
    ideas = [m["_per_item_ideas"][i] for i in items]
    cost = [m["_per_item_cost"][i] for i in items]
    rng = random.Random(seed)
    n = len(items)
    draws: list[float] = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        ti = sum(ideas[j] for j in idx)
        tc = sum(cost[j] for j in idx)
        if tc > 0:
            draws.append(ti / tc)
    if not draws:
        return {"n_boot": 0, "reason": "every resample cost zero"}
    draws.sort()

    def pct(q: float) -> float:
        return draws[min(len(draws) - 1, max(0, int(q * len(draws))))]

    mean = sum(draws) / len(draws)
    sd = (sum((d - mean) ** 2 for d in draws) / max(len(draws) - 1, 1)) ** 0.5
    point = m["ideas_per_usd"] or 0.0
    return {
        "n_boot": len(draws), "n_items": n,
        "a0_ideas_per_usd": point,
        "boot_mean": round(mean, 2), "boot_sd": round(sd, 2),
        "boot_p05": round(pct(0.05), 2), "boot_p50": round(pct(0.50), 2),
        "boot_p95": round(pct(0.95), 2),
        # The prereg's own words: "does not exceed A0's by more than A0's own
        # measured dispersion across bootstrap resamples".
        "threshold_point_plus_1sd": round(point + sd, 2),
        "threshold_boot_p95": round(pct(0.95), 2),
        "reading": ("an arm must exceed threshold_point_plus_1sd to be "
                    "DETECTABLY better than A0 on P1; below it the correct "
                    "record is 'not detectably better', never a kill"),
    }


def paired_difference(arm_rows: Sequence[dict], a0_rows: Sequence[dict]) -> dict:
    """The paired per-item difference in ideas per dollar, with its 80%-power MDE.

    CANON §19: every arm prints its own MDE, and a result below it is NOT
    DETECTABLE rather than absent. The pairing is on the item — both arms saw
    the identical security with the identical observation timestamp — which is
    the whole reason the design was built paired.

    MDE at 80% power and a two-sided 5% test is 2.802 x SE. Reported in the same
    units as the difference, so "the effect we could have seen" and "the effect
    we saw" are directly comparable.
    """
    ma, m0 = arm_metrics(arm_rows), arm_metrics(a0_rows)
    common = sorted(set(ma["_per_item_ideas"]) & set(m0["_per_item_ideas"]))
    d = []
    for it in common:
        ca, c0 = ma["_per_item_cost"][it], m0["_per_item_cost"][it]
        if ca <= 0 or c0 <= 0:
            continue
        d.append(ma["_per_item_ideas"][it] / ca - m0["_per_item_ideas"][it] / c0)
    n = len(d)
    if n < 2:
        return {"n_paired_items": n,
                "reading": "fewer than two paired items with non-zero cost in "
                           "both arms — no difference is estimable"}
    mean = sum(d) / n
    sd = (sum((x - mean) ** 2 for x in d) / (n - 1)) ** 0.5
    se = sd / (n ** 0.5)
    mde = 2.802 * se
    return {
        "n_paired_items": n,
        "mean_per_item_difference": round(mean, 2),
        "sd": round(sd, 2), "se": round(se, 2),
        "mde_80pct_power": round(mde, 2),
        "t": (round(mean / se, 3) if se > 0 else None),
        "detectable": bool(abs(mean) > mde),
        "reading": ("mean per-item (arm - A0) ideas per dollar beside the "
                    "smallest effect this n could have detected at 80% power; "
                    "|mean| below the MDE is NOT DETECTABLE, never a kill "
                    "(CANON §19)"),
    }


# ── minting ─────────────────────────────────────────────────────────────────

def mint(result: ArmResult, *, snapshot: dict, made_at: str | None = None,
         benchmark: str = SWARM_BENCHMARK) -> list[PredictionRecord]:
    """Turn an arm's forecasts into ledger records, arm-attributed.

    `make_prediction` is CALLED, never reimplemented, so its refusals apply
    here unchanged — including the percent/fraction one. Each refusal becomes a
    counted rejection carrying the ledger's own message.

    The specialist key is `arena_<ARM>` (with the persona appended for A0, which
    is the only arm that has one). That prefix is what makes arm-level forward
    Brier and rank-IC resolvable from the ledger without a side table.
    """
    spec = (f"arena_{result.arm}:{result.persona}" if result.persona
            else f"arena_{result.arm}")
    served = sorted({r.served_model for r in result.replies}) or ["UNKNOWN"]
    records: list[PredictionRecord] = []
    for f in result.forecasts:
        try:
            records.append(make_prediction(
                ticker=result.item, specialist=spec,
                observable=Observable(f["observable"]),
                horizon_days=f["horizon_days"], probability=f["probability"],
                threshold=f["threshold"],
                benchmark=(benchmark
                           if f["observable"] == Observable.BEATS_BENCHMARK.value
                           else None),
                thesis=f["thesis"], counter_thesis=f["counter_thesis"],
                next_observable=f["next_observable"],
                model=(result.replies[0].requested_model
                       if result.replies else "unknown"),
                model_version="+".join(served),
                prompt=f"{TRIAL}:{result.arm}:{result.persona}",
                input_snapshot=snapshot, made_at=made_at))
        except Exception as exc:                               # noqa: BLE001
            result.reject("ledger_refused",
                          f"{f['observable']}@{f['horizon_days']}d: "
                          f"{type(exc).__name__}: {exc}")
    return records


def load_registry(path: Path) -> list[dict]:
    """The experiment registry the `prior_experiments` tool serves.

    Returns [] with a WARNING when it cannot be read. A4 then reports the tool
    as unavailable to the model, which is the truth, rather than serving an
    empty result that reads as "no prior experiment matches".
    """
    try:
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception as exc:                                   # noqa: BLE001
        logger.warning("arena: experiment registry unreadable at %s (%s) — the "
                       "prior_experiments tool will report itself UNAVAILABLE, "
                       "not empty", path, exc)
        return []


__all__ = [
    "ARMS", "FLASH", "PRO", "TRIAL", "PURPOSE", "MODULE_VERSION",
    "ArmReply", "ArmResult", "ToolContext", "TOOL_SPECS",
    "call_model", "serve_tool", "validate_forecast", "finish",
    "run_a0", "run_a1", "run_a2", "run_a3", "run_a4", "RUNNERS",
    "effective_distinct_ideas", "arm_metrics", "bootstrap_a0_dispersion",
    "paired_difference", "mint", "load_registry", "ResearchBudgetExhausted",
]
