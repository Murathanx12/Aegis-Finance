"""LLM-SWARM-1: thousands of independent calls, each of which must be gradeable.

WHAT THIS IS, AND WHAT IT IS NOT
================================

Murat's instruction was "make thousands of llm calls why did we stop?". The
honest reading of that is not "emit volume" — it is "stop treating inference as
scarce and start treating it as an experimental resource". A campaign of
thousands of calls is only worth running if every call produces something a
machine can later grade, which is why this module's centre of gravity is the
PARSER, not the caller. The caller is thirty lines. The refusals are three
hundred.

**Volume buys EXPLORATION DIVERSITY. It does not buy evidence.** Asking one
foundation model 8,000 times is not n=8,000; it is one correlated opinion
sampled 8,000 times, and `effective_distinct_ideas` (CANON §20) is computed and
reported precisely so nobody downstream can forget that. Only resolved market
outcomes supply evidence.

ARCHITECTURE_RESULT_ONLY
------------------------
Nothing produced here certifies alpha, and it cannot: the foundation model was
trained on history that overlaps anything we might backtest, so a good-looking
historical result is unfalsifiably contaminated. Every forecast this module
mints is about a future that has not happened yet, which is the only
configuration in which the model's training data cannot help it. Forward
resolution is the evidence. This file is the instrument.

FOURTEEN ROLES, NONE OF WHICH SEE EACH OTHER
--------------------------------------------
Each specialist is a separate call with a separate system prompt and no sight of
any other specialist's answer. This is not a stylistic choice. A panel that has
read each other is one forecaster wearing fourteen names, §20 collapses its
effective n to 1, and every aggregate computed over it is false confidence.
NIGHT-10 measured exactly that failure: ten "independent" hypotheses that were
one connected component.

THE THREE RULES THAT COST US SOMETHING TO LEARN
-----------------------------------------------
1. **ABSTAIN is available and is better than fake precision.** A specialist with
   nothing to say about a security should say so. Abstentions are COUNTED, never
   discarded, and they are honestly reported as producing no gradeable output —
   because they do not. An abstention that were quietly booked as yield would
   make the zero-yield brake unable to see the campaign it exists to watch.
2. **p = 0.50 is REFUSED.** The first WHY-MOVED batch was 23 of 25 one-day
   `return_sign` claims at exactly 0.50. That is the shape of a campaign that
   accrues records at full speed and learns nothing. The abstain channel exists
   for "I don't know"; a coin flip dressed as a forecast does not get a record.
3. **A threshold >= 1.0 is a percent/fraction mixup, and `make_prediction`
   refuses it.** That refusal is SURFACED as a counted rejection with the
   message intact, never swallowed. One live run wrote six guaranteed-wrong
   records because it was swallowed, all from a single specialist whose judgment
   had nothing to do with it.

A BATCH THAT IS ONE OBSERVABLE AT ONE HORIZON IS ONE FORECAST
-------------------------------------------------------------
Three `return_sign` claims at 5 days about the same security are not three
forecasts. `_monoculture` refuses the batch rather than minting them, because a
ledger full of them looks productive on every count that matters and is not.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from backend.config import (SWARM_BACKOFF_BASE_S, SWARM_BENCHMARK,
                            SWARM_COIN_FLIP_EPS,
                            SWARM_MAX_FORECASTS_PER_CALL, SWARM_MAX_RETRIES,
                            SWARM_MAX_TOKENS,
                            SWARM_MIN_FORECASTS_PER_CALL, SWARM_MODEL,
                            SWARM_SCENARIO_PROB_TOL, SWARM_TEMPERATURE,
                            SWARM_TIMEOUT_S, WHY_MOVED_FORBIDDEN_PATTERN)
from backend.services.belief_state import (HORIZONS, BeliefState, Observable,
                                           PredictionRecord, ScenarioLeg,
                                           make_prediction)
from backend.services.research_budget import ResearchBudgetExhausted

logger = logging.getLogger(__name__)

MODULE_VERSION = "llm_swarm/1.0.0"
CAMPAIGN = "grand_arena_1"
PURPOSE = "swarm_specialist_forecast"

_FORBIDDEN = re.compile(WHY_MOVED_FORBIDDEN_PATTERN, re.I)

#: Top-level fields a non-abstaining reply MUST carry. Absence is a counted
#: rejection of the whole item, not a field quietly defaulted to "": a reply
#: missing its market-implied expectation did not do the job that distinguishes
#: this from market commentary, which is to state a DISCREPANCY.
REQUIRED_FIELDS: tuple[str, ...] = (
    "market_implied_expectation", "optimus_expectation",
    "expectation_discrepancy", "causal_chain", "scenarios", "thesis_breakers",
    "next_observable", "confidence", "counterargument", "evidence", "forecasts",
)

#: The three branches a probability tree must name. Fixed, because a tree whose
#: branch labels are chosen per-reply cannot be compared across replies, and
#: comparing them is the entire reason for asking 8,000 times.
SCENARIO_LABELS: tuple[str, ...] = ("bull", "base", "bear")


# ── the roles ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SpecialistSpec:
    """One way of being wrong about a security.

    `sectors` is the routing gate. A biotech analyst asked about a utility has
    two honest options — abstain, or invent — and asking anyway spends money to
    find out which. So sector-bound roles are only routed to their sector, and
    the sector-free roles (which reason about things every security has) are
    routed to everything. Names whose sector we could not determine are routed
    to the bound roles too: "unknown" is not permission to skip a check, and the
    abstain channel is there for exactly that case.
    """
    name: str
    system: str
    sectors: frozenset[str] | None = None   # None = every security


def _spec(name: str, system: str, sectors: Iterable[str] | None = None) -> SpecialistSpec:
    return SpecialistSpec(name=name, system=system,
                          sectors=None if sectors is None else frozenset(sectors))


SPECIALISTS: dict[str, SpecialistSpec] = {s.name: s for s in [
    _spec("company_fundamental",
          "You are a company fundamentals analyst. You reason about revenue "
          "durability, unit economics, gross and operating margin, cash "
          "conversion, balance-sheet capacity, capital intensity and the gap "
          "between reported growth and the growth already embedded in the "
          "price. You know that a good company and a good expected return are "
          "different objects."),
    _spec("analyst_revisions",
          "You are an analyst-estimate specialist. You reason about the "
          "DIRECTION and DISPERSION of earnings and revenue revisions, "
          "price-target and rating changes, coverage initiations and drops, and "
          "the difference between a level (which is consensus) and a revision "
          "(which is news). You know a target change is a statement about a "
          "forecaster, not about a firm, and that revision information decays "
          "fast and is far weaker in large caps than in small ones."),
    _spec("semis_technology",
          "You are a semiconductor, hardware and compute-infrastructure "
          "analyst. You reason about node transitions, foundry and packaging "
          "capacity, memory and substrate pricing, inventory cycles, "
          "hyperscaler capex commitments, export controls, and the difference "
          "between a secular trend and the expectation of it already in the "
          "price.",
          ("Technology", "Semiconductors", "Communication Services",
           "Communications", "Industrials", "Unknown")),
    _spec("biotech_pharma",
          "You are a clinical-stage biotech and pharmaceutical analyst. You "
          "reason in probability trees: phase, indication, endpoint, historical "
          "success rates for that modality, competitive readouts, regulatory "
          "path, cash runway against the next catalyst, and financing and "
          "dilution risk. You know most clinical assets fail and that base "
          "rates beat narratives.",
          ("Healthcare", "Health Care", "Unknown")),
    _spec("energy_materials",
          "You are an energy, mining, battery and critical-materials analyst. "
          "You reason about reserves and depletion, production cost curves, "
          "spare capacity, refining and processing bottlenecks, policy and "
          "subsidy regimes, commodity price pass-through and operating "
          "leverage.",
          ("Energy", "Materials", "Basic Materials", "Utilities", "Unknown")),
    _spec("macro_rates",
          "You are a rates and macro strategist. You reason about the yield "
          "curve, real rates, inflation prints, central-bank reaction "
          "functions, credit spreads, liquidity and the duration sensitivity of "
          "long-dated equity cash flows. You know that an unprofitable growth "
          "company is a long-duration asset and trades like one."),
    _spec("geopolitical",
          "You are a geopolitical risk analyst. You reason about conflict "
          "escalation and de-escalation, sanctions, tariffs, export controls, "
          "shipping chokepoints, elections and policy shocks, and how each "
          "transmits into a specific security. You are acutely aware that "
          "'geopolitics' is the most over-used explanation in markets and that "
          "a real shock leaves a specific, checkable signature."),
    _spec("event_news",
          "You are an event-driven analyst. You reason about scheduled and "
          "unscheduled catalysts: earnings dates, guidance, index inclusion, "
          "lockup expiries, secondary offerings, M&A, spin-offs, litigation and "
          "regulatory decisions. You care about WHEN something became public, "
          "because a move that preceded a disclosure was not caused by it."),
    _spec("options_volatility",
          "You are a volatility and market-microstructure analyst. You reason "
          "about implied versus realised volatility, skew and term structure, "
          "dealer gamma, expiries, short interest and borrow, float and "
          "liquidity, and you distinguish a move caused by information from a "
          "move caused by positioning."),
    _spec("accounting_forensics",
          "You are a forensic accountant. You reason about revenue "
          "recognition, receivables and inventory build relative to sales, "
          "capitalised costs, non-GAAP bridges, share-count dilution, "
          "related-party transactions, auditor changes and restatements. You "
          "look for the gap between accrual earnings and cash."),
    _spec("behavioral_narrative",
          "You are a behavioural and narrative analyst. You reason about "
          "attention, retail and social flow, story-stock dynamics, anchoring "
          "on prior prices, crowding and the lifecycle of a theme from "
          "discovery to saturation. You know a narrative can be correct and "
          "still be fully priced."),
    _spec("ownership_flow",
          "You are an ownership and flow analyst. You reason about insider "
          "transactions and their cluster structure, institutional "
          "concentration, index membership and rebalance flows, buybacks, "
          "share issuance and the difference between an informed seller and a "
          "mechanical one."),
    _spec("execution_momentum",
          "You are a cross-sectional momentum and trend analyst. You reason "
          "about relative strength across horizons, trend persistence and "
          "reversal, volatility regime, drawdown state and the well-documented "
          "asymmetry between 12-1 momentum and 1-month reversal. You start "
          "from the question of whether a name is simply moving with its "
          "factor."),
    _spec("skeptic",
          "You are a professional skeptic whose job is to find the reason a "
          "position loses money. You default to the base rate. You distrust "
          "any thesis requiring several things to go right in sequence, you "
          "treat a large analyst price target as evidence of consensus "
          "enthusiasm rather than evidence of value, and you know that most of "
          "what looks like signal in a single security is idiosyncratic noise. "
          "You are the only member of this panel who can lower its confidence, "
          "and you are expected to abstain more often than the others."),
]}


# ── the contract every specialist is bound by ───────────────────────────────

CONTRACT = f"""
You produce a STRUCTURED, FALSIFIABLE VIEW of ONE security, not a
recommendation and not commentary. Everything you say will be checked: the
scenario tree is priced, and every forecast is written to a ledger that grades
it against actual closes on a fixed date.

ABSTAINING IS A FIRST-CLASS ANSWER. If you have no security-specific
information or reasoning that distinguishes this name from its sector, return
{{"abstain": true, "abstain_reason": "<one specific sentence>"}} and nothing
else. An abstention is recorded and costs you nothing. A confident-sounding
forecast built on no information costs everyone.

Hard rules:
- You never state a position size, weight, allocation or action, and you never
  use the words buy, sell, hold, trim, overweight, underweight, take profit or
  stop loss. The engine allocates; you forecast.
- PROBABILITY 0.50 IS REJECTED, NOT ACCEPTED. A coin flip you called a coin
  flip is not a forecast. If your genuine credence is one half, you have no
  view: abstain, or forecast a DIFFERENT observable where you do have one.
- Every forecast carries a counter_thesis (what would make you wrong) and a
  next_observable (one concrete checkable thing that resolves BEFORE the
  horizon and would move your credence).
- evidence[].first_public_timestamp is when the information became public. If
  you do not know, write "unknown". Never invent one.
- scenarios must be exactly three, labelled bull, base and bear, each with a
  numeric price_target and probabilities summing to 1.0.
- THRESHOLDS ARE DECIMAL FRACTIONS, NEVER PERCENTAGES. A 25% move is 0.25, not
  25. abs_move_exceeds and drawdown_exceeds REQUIRE a threshold strictly
  between 0 and 1; return_sign and beats_benchmark require threshold: null.

Your forecasts must NOT all be the same observable at the same horizon. Give
{SWARM_MIN_FORECASTS_PER_CALL} to {SWARM_MAX_FORECASTS_PER_CALL} forecasts
spanning AT LEAST TWO DISTINCT OBSERVABLES and AT LEAST TWO DISTINCT HORIZONS.
A batch that is one observable at one horizon is one forecast wearing several
rows and is rejected whole. Use abs_move_exceeds where the payoff is genuinely
binary; that is how a probability tree gets stated in a form that can be scored.

horizon_days must be one of {list(HORIZONS)} (trading days). The short horizons
exist so a claim about a reaction resolves in days rather than quarters; the
long ones exist so a claim about a business resolves on the timescale the
business works on. Choose the one your mechanism actually implies.

Return ONLY valid JSON, no prose outside it, matching exactly:
{{"security": str, "abstain": false, "abstain_reason": "",
 "evidence": [{{"what": str, "source": str, "first_public_timestamp": str}}],
 "market_implied_expectation": str,
 "optimus_expectation": str,
 "expectation_discrepancy": str,
 "causal_chain": [str, ...],
 "scenarios": [{{"label": "bull"|"base"|"bear", "probability": float,
                "price_target": float, "rationale": str}}],
 "thesis_breakers": [str, ...],
 "next_observable": str,
 "confidence": float 0..1,
 "counterargument": str,
 "forecasts": [{{"observable":
    "return_sign"|"beats_benchmark"|"abs_move_exceeds"|"drawdown_exceeds",
   "horizon_days": int, "probability": float 0..1 and NOT 0.50,
   "threshold": float or null, "thesis": str, "counter_thesis": str,
   "next_observable": str}}]}}
"""


def build_prompt(specialist: str, snapshot: dict, *,
                 benchmark: str = SWARM_BENCHMARK) -> tuple[str, str]:
    """System and user prompt for one (specialist, security) cell.

    The snapshot is the ONLY market data the model is shown, and it is computed
    from closes at or before the observation timestamp. Nothing in it is visible
    after `as_of`; that is what makes the forecast a forecast.
    """
    if specialist not in SPECIALISTS:
        raise KeyError(f"unknown specialist {specialist!r}")
    system = SPECIALISTS[specialist].system + "\n" + CONTRACT
    user = (
        f"Form your own independent view of ONE security. You have not seen and "
        f"will not see any other analyst's answer; do not write as if you had.\n\n"
        f"Point-in-time snapshot (every number is computed from closes at or "
        f"before {snapshot.get('as_of')}; nothing after that date is available "
        f"to you, and you have no live feed):\n"
        f"{json.dumps(snapshot, indent=1, sort_keys=True, default=str)}\n\n"
        f"`beats_benchmark` forecasts are graded against {benchmark}.\n"
        f"Your view is written down today and graded on schedule against actual "
        f"closes. Nothing about the future is in the snapshot.")
    return system, user


# ── what one call produced ──────────────────────────────────────────────────

@dataclass
class ParsedCall:
    """One reply, split into what can be graded and what was refused.

    `rejections` is not an error log. It is the measurement of how much of a
    specialist's output was ungradeable, and it is reported per reason.
    """
    specialist: str
    ticker: str
    abstained: bool = False
    abstain_reason: str = ""
    forecasts: list[dict] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)
    belief: BeliefState | None = None
    confidence: float | None = None
    raw: dict | None = None

    def reject(self, reason: str, detail: str = "") -> None:
        self.rejections.append({"specialist": self.specialist,
                                "ticker": self.ticker, "reason": reason,
                                "detail": str(detail)[:300]})


def _extract_json(text: str) -> dict:
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


def _monoculture(forecasts: Sequence[dict]) -> bool:
    """Is this batch one forecast wearing several rows?

    True when two or more forecasts collapse onto a single (observable,
    horizon) pair. A single forecast cannot be a monoculture — variety is a
    property of a set — so n=1 passes here and is caught instead by the
    minimum-forecast count, which is a different finding and is counted
    separately.
    """
    if len(forecasts) < 2:
        return False
    return len({(f["observable"], f["horizon_days"]) for f in forecasts}) == 1


def _scenarios(raw: Any, out: ParsedCall) -> list[ScenarioLeg] | None:
    """The probability tree, or None with the reason recorded."""
    if not isinstance(raw, list) or len(raw) != len(SCENARIO_LABELS):
        out.reject("scenarios_not_three",
                   f"expected exactly {len(SCENARIO_LABELS)} branches "
                   f"{SCENARIO_LABELS}, got {len(raw) if isinstance(raw, list) else type(raw).__name__}")
        return None
    legs: list[ScenarioLeg] = []
    for s in raw:
        if not isinstance(s, dict):
            out.reject("scenario_not_object", repr(s))
            return None
        try:
            p = float(s.get("probability"))
            pt = (float(s["price_target"])
                  if s.get("price_target") is not None else None)
        except (TypeError, ValueError):
            out.reject("scenario_not_numeric", repr(s)[:200])
            return None
        legs.append(ScenarioLeg(label=str(s.get("label", "")).strip().lower(),
                                probability=p, price_target=pt,
                                rationale=str(s.get("rationale", ""))))
    labels = {leg.label for leg in legs}
    if labels != set(SCENARIO_LABELS):
        out.reject("scenario_labels_wrong", f"got {sorted(labels)}")
        return None
    total = sum(leg.probability for leg in legs)
    if abs(total - 1.0) > SWARM_SCENARIO_PROB_TOL:
        # An expected value computed from branches that do not sum to one is
        # arithmetic on an error. belief_state refuses to price it; refusing it
        # here means the incoherent tree never reaches the ledger at all.
        out.reject("scenario_probs_dont_sum", f"sum={total:.3f}")
        return None
    if any(leg.price_target is None for leg in legs):
        out.reject("scenario_missing_price_target",
                   "a branch with no target cannot be priced")
        return None
    return legs


def _validate_forecast(f: Any, out: ParsedCall) -> dict | None:
    """One forecast, or None with the reason it is not one.

    Every refusal here removes a way this specialist could later be caught being
    wrong, so each is named rather than dropped.
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
        out.reject("horizon_not_frozen",
                   f"{h} is not one of {list(HORIZONS)}; a horizon chosen "
                   f"per-forecast is a free parameter")
        return None
    try:
        p = float(f.get("probability"))
    except (TypeError, ValueError):
        out.reject("probability_not_numeric", repr(f.get("probability")))
        return None
    if not 0.0 <= p <= 1.0:
        out.reject("probability_not_a_credence", repr(p))
        return None
    if abs(p - 0.5) < SWARM_COIN_FLIP_EPS:
        # The whole reason this rule exists. See the module docstring.
        out.reject("coin_flip_filler",
                   f"p={p} — a coin flip you called a coin flip is not a "
                   f"forecast; the abstain channel exists for having no view")
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
            out.reject("threshold_missing",
                       f"{obs.value} has nothing to resolve against")
            return None
    elif thr is not None:
        # Harmless in the ledger, but it means the reply did not follow the
        # contract, and a threshold on return_sign usually signals the model
        # confused two observables.
        thr = None
    ct = str(f.get("counter_thesis", "")).strip()
    if not ct:
        out.reject("no_counter_thesis",
                   "a forecast with no stated way of being wrong is not "
                   "falsifiable")
        return None
    blob = f"{f.get('thesis', '')} {ct} {f.get('next_observable', '')}"
    hits = _FORBIDDEN.findall(blob)
    if hits:
        out.reject("recommendation_language",
                   f"matched {sorted({str(x).lower() for x in hits})}")
        return None
    return {"observable": obs.value, "horizon_days": h, "probability": p,
            "threshold": thr, "thesis": str(f.get("thesis", "")).strip(),
            "counter_thesis": ct,
            "next_observable": str(f.get("next_observable", "")).strip()}


def parse_reply(specialist: str, snapshot: dict, text: str, *,
                max_forecasts: int = SWARM_MAX_FORECASTS_PER_CALL) -> ParsedCall:
    """Everything gradeable in one reply, and a counted pile of everything else.

    This function makes no network call and mints nothing, so the whole refusal
    surface is testable offline — which matters, because the refusals are the
    part of this campaign that decides whether the money bought information.
    """
    ticker = str(snapshot.get("ticker", "")).upper()
    out = ParsedCall(specialist=specialist, ticker=ticker)
    try:
        raw = _extract_json(text)
    except Exception as exc:                                   # noqa: BLE001
        out.reject("unparseable_json", f"{type(exc).__name__}: {exc}")
        return out
    if not isinstance(raw, dict):
        out.reject("reply_not_object", type(raw).__name__)
        return out
    out.raw = raw

    if raw.get("abstain") is True:
        reason = str(raw.get("abstain_reason", "")).strip()
        if not reason:
            # An abstention with no reason is indistinguishable from a reply
            # that fell over, and the two mean very different things about the
            # specialist. It is refused so the distinction stays real.
            out.reject("abstain_without_reason",
                       "an abstention with no stated reason cannot be told "
                       "apart from a failure")
            return out
        out.abstained = True
        out.abstain_reason = reason[:500]
        return out

    sec = str(raw.get("security", ticker)).upper()
    if sec and sec != ticker:
        out.reject("wrong_security",
                   f"reply is about {sec}, the prompt was about {ticker}; a "
                   f"forecast about a security nobody asked about cannot be "
                   f"resolved against the snapshot it never saw")
        return out

    missing = [k for k in REQUIRED_FIELDS if k not in raw]
    if missing:
        out.reject("missing_required_field", ",".join(missing))
        return out

    ev = [e for e in (raw.get("evidence") or []) if isinstance(e, dict)]
    if not ev:
        out.reject("no_evidence", "the reply cited nothing")
        return out
    if not all("first_public_timestamp" in e for e in ev):
        out.reject("evidence_without_first_public_timestamp",
                   "a move that preceded the disclosure was not caused by it, "
                   "and without the timestamp that cannot be checked")
        return out

    try:
        conf = float(raw.get("confidence"))
    except (TypeError, ValueError):
        out.reject("confidence_not_numeric", repr(raw.get("confidence")))
        return out
    if not 0.0 <= conf <= 1.0:
        out.reject("confidence_not_a_credence", repr(conf))
        return out
    out.confidence = conf

    if not str(raw.get("counterargument", "")).strip():
        out.reject("no_counterargument", "every view states the case against it")
        return out
    if not str(raw.get("expectation_discrepancy", "")).strip():
        out.reject("no_expectation_discrepancy",
                   "the discrepancy between the market's expectation and ours "
                   "IS the view; without it this is commentary")
        return out

    legs = _scenarios(raw.get("scenarios"), out)
    if legs is None:
        return out

    items = raw.get("forecasts")
    if not isinstance(items, list) or not items:
        out.reject("no_forecasts", "a non-abstaining reply with no forecast is "
                                   "a paragraph, not a view")
        return out

    kept: list[dict] = []
    for f in items[:max_forecasts]:
        v = _validate_forecast(f, out)
        if v is not None:
            kept.append(v)
    if len(items) > max_forecasts:
        out.reject("forecasts_past_cap",
                   f"{len(items) - max_forecasts} forecast(s) past the cap of "
                   f"{max_forecasts} were not read")
    if not kept:
        return out
    if _monoculture(kept):
        out.reject("monoculture_batch",
                   f"all {len(kept)} forecasts are "
                   f"{kept[0]['observable']}@{kept[0]['horizon_days']}d — one "
                   f"forecast wearing several rows, refused whole")
        return out

    out.forecasts = kept
    out.belief = BeliefState(
        ticker=ticker, as_of=str(snapshot.get("as_of", "")),
        theme=str(raw.get("optimus_expectation", ""))[:500],
        causal_chain=[str(x) for x in (raw.get("causal_chain") or [])],
        scenarios=legs,
        thesis_breakers=[str(x) for x in (raw.get("thesis_breakers") or [])],
        next_observable=str(raw.get("next_observable", "")),
        market_implied_expectation=str(raw.get("market_implied_expectation", "")),
        optimus_expectation=str(raw.get("optimus_expectation", "")),
        dislocation=str(raw.get("expectation_discrepancy", "")),
        confidence=conf, source=f"llm_swarm:{specialist}")
    return out


def mint(parsed: ParsedCall, *, snapshot: dict, prompt: str, model: str,
         model_version: str, benchmark: str = SWARM_BENCHMARK,
         made_at: str | None = None) -> list[PredictionRecord]:
    """Turn validated forecasts into ledger records. Mutates `parsed.rejections`.

    `make_prediction` is CALLED, never reimplemented, so its refusals apply here
    unchanged — including the percent/fraction one that produced six
    guaranteed-wrong records the last time it was swallowed. Each refusal
    becomes a counted rejection carrying the ledger's own message, so the
    specialist that produced it is identifiable.
    """
    records: list[PredictionRecord] = []
    for f in parsed.forecasts:
        try:
            records.append(make_prediction(
                ticker=parsed.ticker, specialist=parsed.specialist,
                observable=Observable(f["observable"]),
                horizon_days=f["horizon_days"], probability=f["probability"],
                threshold=f["threshold"],
                benchmark=(benchmark
                           if f["observable"] == Observable.BEATS_BENCHMARK.value
                           else None),
                thesis=f["thesis"], counter_thesis=f["counter_thesis"],
                next_observable=f["next_observable"], model=model,
                model_version=model_version, prompt=prompt,
                input_snapshot=snapshot, made_at=made_at))
        except Exception as exc:                               # noqa: BLE001
            parsed.reject("ledger_refused",
                          f"{f['observable']}@{f['horizon_days']}d: "
                          f"{type(exc).__name__}: {exc}")
    return records


# ── the vendor call ─────────────────────────────────────────────────────────

@dataclass
class SwarmReply:
    """One wire attempt's result, with everything the telemetry row needs."""
    text: str
    model_version: str
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0
    latency_ms: float = 0.0
    retries: int = 0


#: (system, user) -> SwarmReply. Injectable so the offline suite never reaches
#: the network; the default is DeepSeek, budget-gated.
LLMCall = Callable[[str, str], SwarmReply]

_RETRYABLE = ("429", "500", "502", "503", "504", "timeout", "timed out",
              "connection", "overloaded", "rate limit", "temporarily")


def _is_retryable(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    status = getattr(exc, "status_code", None)
    if status in (408, 409, 429, 500, 502, 503, 504):
        return True
    return any(t in s for t in _RETRYABLE)


def _client(api_key: str | None = None, *, timeout: float = SWARM_TIMEOUT_S):
    import os

    from openai import OpenAI
    key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is empty. Keys are env-only by house rule; a "
            "swarm run with no key must fail loudly rather than quietly produce "
            "nothing and be recorded as a night with no spend.")
    return OpenAI(api_key=key,
                  base_url=os.getenv("DEEPSEEK_BASE_URL",
                                     "https://api.deepseek.com"),
                  timeout=timeout, max_retries=0)


def default_llm_call(system: str, user: str, *, client=None,
                     model: str = SWARM_MODEL,
                     temperature: float = SWARM_TEMPERATURE,
                     max_tokens: int = SWARM_MAX_TOKENS,
                     max_retries: int = SWARM_MAX_RETRIES,
                     campaign: str = CAMPAIGN,
                     since: str | None = None,
                     rng: random.Random | None = None) -> SwarmReply:
    """One budget-gated DeepSeek call, with backoff. Raises on final failure.

    `research_budget.require()` is called BEFORE EVERY VENDOR REQUEST, including
    every retry — a retry is a request and spends like one. When the governor
    raises, it propagates: an exhausted budget must stop the campaign, not be
    absorbed into a per-cell failure count where it would look like flakiness.

    Usage counts are read defensively (`extract_usage`) because `usage` is the
    vendor's object, not ours, and a missing field must degrade to a zero-token
    row rather than take a forecast down.
    """
    from backend.services import research_budget
    from backend.services.llm_telemetry import extract_usage

    cli = client or _client()
    rnd = rng or random
    retries = 0
    last: Exception | None = None
    t0 = time.perf_counter()
    for attempt in range(max_retries + 1):
        research_budget.require(campaign, since=since)
        try:
            resp = cli.chat.completions.create(
                model=model, temperature=temperature, max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}])
        except Exception as exc:                               # noqa: BLE001
            last = exc
            if attempt >= max_retries or not _is_retryable(exc):
                break
            retries += 1
            time.sleep(SWARM_BACKOFF_BASE_S * (2 ** attempt)
                       * (0.5 + rnd.random()))
            continue
        u = extract_usage(resp, "deepseek")
        return SwarmReply(
            text=(resp.choices[0].message.content or ""),
            model_version=str(getattr(resp, "model", model)),
            latency_ms=(time.perf_counter() - t0) * 1000.0, retries=retries,
            **u)
    assert last is not None
    raise last


# ── one cell, end to end ────────────────────────────────────────────────────

@dataclass
class CellResult:
    """What one (specialist, security) call produced, including nothing."""
    specialist: str
    ticker: str
    status: str                       # ok | abstained | zero_yield | failed
    parsed: ParsedCall | None
    records: list[PredictionRecord] = field(default_factory=list)
    reply: SwarmReply | None = None
    error: str | None = None
    pass_id: int = 1

    def as_row(self) -> dict:
        """The checkpoint row. Small on purpose: a crash at call 6,000 must be
        resumable from a file that is still cheap to read."""
        p = self.parsed
        return {
            "specialist": self.specialist, "ticker": self.ticker,
            "pass_id": self.pass_id, "status": self.status,
            "error": self.error,
            "n_forecasts": len(p.forecasts) if p else 0,
            "n_records": len(self.records),
            "abstain_reason": (p.abstain_reason if p else ""),
            "confidence": (p.confidence if p else None),
            "rejections": [{"reason": r["reason"], "detail": r["detail"][:160]}
                           for r in (p.rejections if p else [])],
            "forecasts": [{"observable": f["observable"],
                           "horizon_days": f["horizon_days"],
                           "probability": f["probability"],
                           "threshold": f["threshold"]}
                          for f in (p.forecasts if p else [])],
            "prediction_ids": [r.prediction_id for r in self.records],
            "tokens_in": (self.reply.tokens_in if self.reply else 0),
            "tokens_out": (self.reply.tokens_out if self.reply else 0),
            "cached_tokens": (self.reply.cached_tokens if self.reply else 0),
            "latency_ms": round(self.reply.latency_ms, 1) if self.reply else None,
            "retries": (self.reply.retries if self.reply else 0),
            "model_version": (self.reply.model_version if self.reply else ""),
        }


def run_cell(specialist: str, snapshot: dict, *, llm_call: LLMCall | None = None,
             model: str = SWARM_MODEL, benchmark: str = SWARM_BENCHMARK,
             made_at: str | None = None, pass_id: int = 1,
             telemetry_path: Any = None) -> CellResult:
    """Ask one specialist about one security and keep only what can be graded.

    Telemetry is written exactly once, at the end, carrying the ids actually
    minted. A row that claimed yield it did not mint would be worse than no row,
    because the zero-yield brake reads these rows to decide whether the campaign
    is buying information.
    """
    system, user = build_prompt(specialist, snapshot, benchmark=benchmark)
    call = llm_call or default_llm_call
    try:
        reply = call(system, user)
    except ResearchBudgetExhausted:
        # NEVER absorbed into the per-cell failure count. An exhausted budget is
        # a campaign-level stop; booked as one more flaky cell it would look
        # like vendor noise and the pool would keep submitting work that can
        # only ever be refused.
        raise
    except Exception as exc:                                   # noqa: BLE001
        # No wire result means no telemetry row: nothing was spent that the
        # vendor billed us for, and a row here would dilute the very
        # denominator the zero-yield brake protects. The failure is COUNTED by
        # the caller instead.
        logger.warning("swarm: %s/%s failed: %s: %s", specialist,
                       snapshot.get("ticker"), type(exc).__name__, exc)
        return CellResult(specialist=specialist,
                          ticker=str(snapshot.get("ticker", "")).upper(),
                          status="failed", parsed=None,
                          error=f"{type(exc).__name__}: {exc}"[:300],
                          pass_id=pass_id)

    parsed = parse_reply(specialist, snapshot, reply.text)
    records = ([] if (parsed.abstained or not parsed.forecasts)
               else mint(parsed, snapshot=snapshot, prompt=system + user,
                         model=model, model_version=reply.model_version,
                         benchmark=benchmark, made_at=made_at))
    if parsed.abstained:
        status = "abstained"
    elif records:
        status = "ok"
    else:
        status = "zero_yield"

    try:
        from backend.services.llm_telemetry import record_call
        record_call(
            provider="deepseek", model=model, model_version=reply.model_version,
            purpose=PURPOSE, agent=specialist, prompt=system + user,
            context=snapshot, tokens_in=reply.tokens_in,
            tokens_out=reply.tokens_out, cached_tokens=reply.cached_tokens,
            latency_ms=reply.latency_ms, retries=reply.retries,
            # schema_valid is about the CONTRACT, not the HTTP status. An
            # abstention is schema-valid and gradeable-empty; an unparseable
            # reply is neither. Rubber-stamping a 200 here is the exact failure
            # the telemetry ledger exists to expose.
            schema_valid=bool(parsed.abstained or parsed.forecasts
                              or parsed.raw is not None),
            error=(None if status != "zero_yield"
                   else ";".join(r["reason"] for r in parsed.rejections)[:400]),
            prediction_ids=[r.prediction_id for r in records],
            meta={"pass_id": pass_id, "ticker": parsed.ticker,
                  "status": status, "n_rejections": len(parsed.rejections),
                  "module": MODULE_VERSION},
            path=telemetry_path)
    except Exception as exc:                                   # noqa: BLE001
        logger.warning("swarm: telemetry not recorded for %s/%s (%s: %s) — the "
                       "spend is MISSING from the ledger, the forecast is not",
                       specialist, parsed.ticker, type(exc).__name__, exc)

    return CellResult(specialist=specialist, ticker=parsed.ticker, status=status,
                      parsed=parsed, records=records, reply=reply,
                      pass_id=pass_id)


# ── CANON §20 ───────────────────────────────────────────────────────────────

def effective_distinct_ideas(preds: Sequence[PredictionRecord | dict]) -> dict:
    """How many DIFFERENT forecasts a swarm actually contains.

    Deliberately the SAME rule `optimus_specialists.effective_distinct_ideas`
    uses — same security, same observable, probabilities agreeing within 0.05 is
    one idea — so the number is comparable across the two surfaces. Accepts
    dicts as well as records because the checkpoint stores dicts and this must
    be computable on a resumed run without re-minting anything.

    THE READING THAT MATTERS: 8,000 calls to one foundation model is not
    n=8,000. It is one correlated opinion sampled 8,000 times. This ratio is the
    honest denominator for any claim made about the swarm, and it is never a
    reason to feel good about the raw count.
    """
    def get(p: Any, k: str) -> Any:
        return p.get(k) if isinstance(p, dict) else getattr(p, k)

    n = len(preds)
    if not n:
        return {"n_forecasts": 0, "effective_distinct_ideas": 0, "ratio": None}
    buckets = {(get(p, "ticker"), get(p, "observable"),
                round(float(get(p, "probability")) / 0.05)) for p in preds}
    return {
        "n_forecasts": n,
        "effective_distinct_ideas": len(buckets),
        "ratio": round(len(buckets) / n, 4),
        "distinct_tickers": len({get(p, "ticker") for p in preds}),
        "distinct_observables": len({get(p, "observable") for p in preds}),
        "distinct_horizons": len({get(p, "horizon_days") for p in preds}),
        "reading": ("the denominator for any claim about this swarm is the "
                    "effective count, not the raw count (CANON §20)"),
    }


# ── the point-in-time snapshot ──────────────────────────────────────────────

def _ret(s: Any, n: int) -> float | None:
    """Trailing return over n bars, or None when the history is not there.

    None rather than 0.0, always: a security with 40 bars of history did not
    return zero over a year, and a zero would be read as a fact by every
    downstream consumer including the language model.
    """
    if len(s) < n + 1:
        return None
    a, b = float(s.iloc[-(n + 1)]), float(s.iloc[-1])
    if a == 0:
        return None
    return round((b / a - 1.0) * 100.0, 2)


def snapshot_from_panel(ticker: str, panel: Any, *, as_of: str,
                        benchmark: str = SWARM_BENCHMARK,
                        meta: dict | None = None) -> dict | None:
    """Everything one specialist is shown about one security, PIT by construction.

    The panel is TRUNCATED at `as_of` before anything is computed, so no field
    can carry information from after the observation timestamp. That is the only
    property that makes the forecasts forecasts rather than a memory test of the
    foundation model — and it is enforced here, once, rather than trusted to
    every call site.

    Returns None when the security has no usable history at `as_of`. A name we
    cannot price cannot be forecast about, and its records could never resolve.
    """
    import pandas as pd

    if ticker not in panel.columns:
        return None
    s = pd.to_numeric(panel[ticker], errors="coerce").dropna()
    s = s.loc[:pd.Timestamp(as_of)]
    if len(s) < 30:
        return None
    b = pd.to_numeric(panel[benchmark], errors="coerce").dropna().loc[:pd.Timestamp(as_of)] \
        if benchmark in panel.columns else pd.Series(dtype="float64")

    r = s.pct_change().dropna()
    win = s.iloc[-252:] if len(s) >= 252 else s
    hi, lo = float(win.max()), float(win.min())
    last = float(s.iloc[-1])
    dd = float((win / win.cummax() - 1.0).min()) * 100.0

    beta = None
    rel_63 = None
    if len(b) > 60:
        j = pd.concat([r, b.pct_change()], axis=1).dropna().iloc[-252:]
        if len(j) >= 60 and float(j.iloc[:, 1].var()) > 0:
            beta = round(float(j.cov().iloc[0, 1] / j.iloc[:, 1].var()), 3)
        rb, rs = _ret(b, 63), _ret(s, 63)
        if rb is not None and rs is not None:
            rel_63 = round(rs - rb, 2)

    out: dict = {
        "ticker": ticker.upper(),
        "as_of": as_of,
        "n_bars_available": int(len(s)),
        "last_close": round(last, 4),
        "trailing_return_pct": {
            "1d": _ret(s, 1), "5d": _ret(s, 5), "21d": _ret(s, 21),
            "63d": _ret(s, 63), "126d": _ret(s, 126), "252d": _ret(s, 252)},
        "realised_vol_annualised_pct": {
            "21d": (round(float(r.iloc[-21:].std()) * (252 ** 0.5) * 100.0, 1)
                    if len(r) >= 21 else None),
            "63d": (round(float(r.iloc[-63:].std()) * (252 ** 0.5) * 100.0, 1)
                    if len(r) >= 63 else None)},
        "max_drawdown_1y_pct": round(dd, 2),
        "pct_below_1y_high": (round((last / hi - 1.0) * 100.0, 2) if hi else None),
        "pct_above_1y_low": (round((last / lo - 1.0) * 100.0, 2) if lo else None),
        "beta_vs_benchmark": beta,
        "excess_return_63d_pct_vs_benchmark": rel_63,
        "benchmark": benchmark,
        "benchmark_trailing_return_pct": {
            "21d": _ret(b, 21), "63d": _ret(b, 63), "252d": _ret(b, 252)}
        if len(b) else {},
    }
    if meta:
        out.update({k: v for k, v in meta.items() if v is not None})
    return out
