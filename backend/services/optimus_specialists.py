"""DeepSeek category specialists that produce scored forecasts, not prose.

WHAT THIS IS FOR
================

Murat's ask, in his words: the engine should run many instances and learn from
their mistakes the way he does. Running many instances does not by itself
produce learning. Learning needs a frozen input, a stated probability, a
resolution date and a score — which is what `belief_state.PredictionRecord`
provides and what this module fills in.

The specialists are split by category because his own process was: he reasoned
about clinical trials one way and about semiconductor cycles another, and a
single prompt asked to do both does neither. Splitting them also makes the
reliability tensor possible — "this specialist is good at 6-month semis and
overconfident on binary biotech readouts" is only sayable if the specialists
were separate when they spoke.

THE FIREWALL, RESTATED
----------------------
The specialists PROPOSE and FORECAST. They never size, never allocate and never
see a price target they are asked to justify. NIGHT-3 measured that LLM output
earns no role in stock ORDERING (t 0.04 and 0.93 across 16,320 decisions). This
module does not contest that. It asks the different question that has never had
an instrument: are the stated probabilities calibrated? A forecaster can be
useless at ranking and still be well calibrated, and only one of those two has
ever been measured here.

THE BATCH IS CHECKED AGAINST ITSELF
-----------------------------------
CANON §20: NIGHT-10 found ten "independent" LLM hypotheses that were one
connected component. A batch of forecasts that are all the same forecast wearing
different tickers has an effective sample size of one, and averaging them
produces false confidence. `effective_distinct_ideas` is computed here and
recorded on the batch.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.services.belief_state import (HORIZONS, BeliefState, Observable,
                                           PredictionRecord, ScenarioLeg,
                                           make_prediction)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"

#: One specialist per way of being wrong. The skeptic exists because a panel of
#: agreeing forecasters is one forecaster, and NIGHT-10 measured that failure.
SPECIALISTS: dict[str, str] = {
    "biotech": (
        "You are a clinical-stage biotech analyst. You reason in probability "
        "trees: trial phase, endpoint, historical success rates for the "
        "indication and modality, cash runway versus next readout, financing "
        "risk and dilution. You are aware that most clinical assets fail and "
        "that base rates beat narratives."),
    "semis_compute": (
        "You are a semiconductor and compute-infrastructure analyst. You reason "
        "about capacity, node transitions, inventory cycles, memory pricing, "
        "hyperscaler capex and the difference between a secular trend and its "
        "already-priced expectation."),
    "energy_materials": (
        "You are an energy, battery and critical-materials analyst. You reason "
        "about reserves, production cost curves, policy and subsidy regimes, "
        "commodity price sensitivity and operating leverage."),
    "software_consumer": (
        "You are a software, internet and consumer analyst. You reason about "
        "unit economics, retention, competitive moats, pricing power and the "
        "gap between revenue growth and durable margin."),
    "skeptic": (
        "You are a professional skeptic whose job is to find the reason a "
        "position loses money. You default to the base rate, you distrust "
        "narratives that require several things to go right in sequence, and "
        "you treat a large analyst price target as evidence of consensus "
        "enthusiasm rather than evidence of value."),
}

#: The rule every specialist is bound by, appended to each system prompt. It is
#: separated so its hash changes when the CONTRACT changes, not when a category
#: description is reworded.
CONTRACT = """
You produce FORECASTS ABOUT OBSERVABLES, not recommendations.

Hard rules:
- You never state a position size, a weight, an allocation or an action.
- You never use the words buy, sell, hold, overweight or underweight.
- Every probability is your genuine credence. A probability of 0.5 is a valid
  and useful answer and is strongly preferred to a confident guess.
- Every forecast carries a counter_thesis that would make you wrong, and a
  next_observable: one concrete, checkable thing that resolves before the
  horizon does and would move your credence.
- Base rates first. If you do not have specific information that distinguishes
  this security, say so and give a probability near the base rate.
- THRESHOLDS ARE DECIMAL FRACTIONS, NEVER PERCENTAGES. A 25% move is 0.25, not
  25. "abs_move_exceeds" and "drawdown_exceeds" REQUIRE a threshold strictly
  between 0 and 1; the other two observables require threshold: null.

Return ONLY valid JSON, no prose outside it, matching exactly:
{"forecasts": [{"ticker": str, "observable": one of
 ["return_sign","beats_benchmark","abs_move_exceeds","drawdown_exceeds"],
 "horizon_days": one of [5,20,60,120,252], "probability": float 0..1,
 "threshold": float or null, "thesis": str, "counter_thesis": str,
 "next_observable": str}],
 "belief": {"theme": str, "causal_chain": [str], "adoption_stage": str,
 "payoff_skew": str, "thesis_breakers": [str], "next_observable": str,
 "market_implied_expectation": str, "optimus_expectation": str,
 "dislocation": str, "regime_sensitivity": str,
 "scenarios": [{"label": str, "probability": float, "price_target": float or null,
 "rationale": str}]}}
"""

_FORBIDDEN = re.compile(
    r"\b(buy|sell|hold|overweight|underweight|allocate|position size|"
    r"we recommend|you should)\b", re.I)


@dataclass
class SpecialistBatch:
    """One specialist's output for one candidate set."""
    specialist: str
    model: str
    model_version: str
    prompt_hash: str
    predictions: list[PredictionRecord]
    beliefs: list[BeliefState]
    raw: dict
    refusals: list[str]


def _client(api_key: str | None = None):
    from openai import OpenAI
    key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is empty. Keys are env-only by house rule; a "
            "specialist run with no key must fail loudly rather than quietly "
            "produce nothing and be recorded as a night with no spend.")
    return OpenAI(api_key=key, base_url=os.getenv("DEEPSEEK_BASE_URL",
                                                  DEFAULT_BASE_URL))


def _extract_json(text: str) -> dict:
    """Parse the model's JSON, including when it wraps it in a code fence."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def build_prompt(specialist: str, candidates: list[dict]) -> tuple[str, str]:
    """System and user prompt. The snapshot is what the model is allowed to see."""
    system = SPECIALISTS[specialist] + "\n" + CONTRACT
    user = (
        "Forecast observables for the securities below. Use only the "
        "information given plus your general knowledge of the industry; you "
        "have no live data feed.\n\n"
        f"{json.dumps(candidates, indent=1, sort_keys=True)}\n\n"
        "Produce two to four forecasts per security, across different horizons "
        "and observables. Prefer abs_move_exceeds where the payoff is genuinely "
        "binary — that is how a probability tree gets stated in a form that can "
        "be scored.")
    return system, user


def run_specialist(specialist: str, candidates: list[dict], *,
                   model: str = DEFAULT_MODEL, benchmark: str = "SPY",
                   client=None, temperature: float = 0.3) -> SpecialistBatch:
    """Ask one specialist, and refuse whatever it returns that cannot be graded."""
    if specialist not in SPECIALISTS:
        raise KeyError(f"unknown specialist {specialist}")
    system, user = build_prompt(specialist, candidates)
    cli = client or _client()
    resp = cli.chat.completions.create(
        model=model, temperature=temperature,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}])
    text = resp.choices[0].message.content or ""
    version = getattr(resp, "model", model)
    raw = _extract_json(text)

    known = {c["ticker"] for c in candidates}
    preds: list[PredictionRecord] = []
    refusals: list[str] = []
    for f in raw.get("forecasts", []):
        try:
            tkr = str(f["ticker"]).upper()
            if tkr not in known:
                refusals.append(f"{tkr}: not in the candidate set — a forecast "
                                f"about a security nobody asked about cannot be "
                                f"resolved against the snapshot it never saw")
                continue
            obs = Observable(str(f["observable"]))
            h = int(f["horizon_days"])
            if h not in HORIZONS:
                refusals.append(f"{tkr}/{obs.value}: horizon {h} is not frozen")
                continue
            blob = f"{f.get('thesis','')} {f.get('counter_thesis','')}"
            if _FORBIDDEN.search(blob):
                refusals.append(f"{tkr}/{obs.value}: contains recommendation "
                                f"language — the LLM narrates, the engine "
                                f"computes")
                continue
            if not str(f.get("counter_thesis", "")).strip():
                refusals.append(f"{tkr}/{obs.value}: no counter_thesis — a "
                                f"forecast with no stated way of being wrong is "
                                f"not falsifiable")
                continue
            snapshot = next(c for c in candidates if c["ticker"] == tkr)
            preds.append(make_prediction(
                ticker=tkr, specialist=specialist, observable=obs,
                horizon_days=h, probability=float(f["probability"]),
                threshold=(float(f["threshold"])
                           if f.get("threshold") is not None else None),
                benchmark=(benchmark if obs is Observable.BEATS_BENCHMARK
                           else None),
                thesis=str(f.get("thesis", "")),
                counter_thesis=str(f.get("counter_thesis", "")),
                next_observable=str(f.get("next_observable", "")),
                model=model, model_version=str(version),
                prompt=system + user, input_snapshot=snapshot))
        except Exception as exc:                       # noqa: BLE001
            refusals.append(f"{f.get('ticker','?')}: {type(exc).__name__} {exc}")

    beliefs = []
    b = raw.get("belief")
    if isinstance(b, dict) and candidates:
        for c in candidates:
            beliefs.append(BeliefState(
                ticker=c["ticker"], as_of=str(c.get("as_of", "")),
                theme=str(b.get("theme", "")),
                causal_chain=list(b.get("causal_chain", []) or []),
                adoption_stage=str(b.get("adoption_stage", "")),
                payoff_skew=str(b.get("payoff_skew", "")),
                thesis_breakers=list(b.get("thesis_breakers", []) or []),
                next_observable=str(b.get("next_observable", "")),
                market_implied_expectation=str(b.get("market_implied_expectation", "")),
                optimus_expectation=str(b.get("optimus_expectation", "")),
                dislocation=str(b.get("dislocation", "")),
                regime_sensitivity=str(b.get("regime_sensitivity", "")),
                scenarios=[ScenarioLeg(
                    label=str(s.get("label", "")),
                    probability=float(s.get("probability", 0.0)),
                    price_target=(float(s["price_target"])
                                  if s.get("price_target") is not None else None),
                    rationale=str(s.get("rationale", "")))
                    for s in (b.get("scenarios") or [])],
                source=f"deepseek:{specialist}"))

    if refusals:
        logger.warning("%s: refused %d forecast(s): %s", specialist,
                       len(refusals), refusals[:4])
    logger.info("%s: %d prediction(s), %d refusal(s), model %s",
                specialist, len(preds), len(refusals), version)
    return SpecialistBatch(
        specialist=specialist, model=model, model_version=str(version),
        prompt_hash=preds[0].prompt_hash if preds else "",
        predictions=preds, beliefs=beliefs, raw=raw, refusals=refusals)


def effective_distinct_ideas(preds: list[PredictionRecord]) -> dict:
    """CANON §20 — how many DIFFERENT forecasts a batch actually contains.

    NIGHT-10 found ten "independent" LLM hypotheses that were one connected
    component. A batch whose forecasts all say the same thing has an effective
    sample size of one, and averaging it manufactures confidence that no
    independent evidence supports.

    Two forecasts are treated as the same idea when they concern the same
    security and observable and their probabilities agree within 0.05 — the
    cheapest measure that catches the failure mode without pretending to read
    the theses.
    """
    if not preds:
        return {"n_forecasts": 0, "effective_distinct_ideas": 0, "ratio": None}
    buckets: set[tuple] = set()
    for p in preds:
        buckets.add((p.ticker, p.observable, round(p.probability / 0.05)))
    n = len(preds)
    eff = len(buckets)
    return {
        "n_forecasts": n, "effective_distinct_ideas": eff,
        "ratio": round(eff / n, 3),
        "distinct_tickers": len({p.ticker for p in preds}),
        "distinct_observables": len({p.observable for p in preds}),
        "reading": ("the denominator for any claim about this batch is the "
                    "effective count, not the raw count (CANON §20)"),
    }
