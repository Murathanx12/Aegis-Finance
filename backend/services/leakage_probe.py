"""LLM-LEAKAGE-PROBE-1 — does the model KNOW, or does it REMEMBER?

WHY THIS EXISTS, AND WHY IT IS NOT THE SWARM AGAIN
==================================================
LLM-SWARM-1 measured its own ceiling. 22,607 forecasts collapsed to 6,772
effective distinct ideas (ratio 0.2996), and fourteen roles forecasting the same
cell differed by a mean probability spread of 0.059. More of the same buys more
correlated exploration and no more evidence. Worse, every one of its 20,073
records is unresolved until 2026-08-16, so nothing it produced can yet be
graded at all.

This module buys the two things that campaign could not:

1. **Records that resolve the moment they are made** — the observation
   timestamps are HISTORICAL, so the outcome is already in the price series.
2. **A measurement of whether the model knows or merely remembers** — the same
   situation asked twice, once IDENTIFIED and once MASKED.

THE PRIOR ART, AND WHY THIS IS NOT A DUPLICATE
----------------------------------------------
`TRIAL-LLM-AMNESIA-1` (2026-08-08, sister repo) already ran a four-arm
named/instructed/masked/synthetic design over 120 events and found:

* an INSTRUCTION to forget changes nothing (recall 15.8% vs 15.8%);
* masking works where instruction fails (0 of 240 identifications);
* removing identity cost only **0.007 Brier** overall;
* **but the task itself was unlearnable** — every arm sat at the climatology
  Brier of 0.25 with AUC 0.51-0.55, and the cheap logistic baseline was at
  chance too. Its own retirement note says so: *"this task is retired for LLM
  evaluation ... AMNESIA-2 moves to short-horizon event reactions where the
  baseline bank has measurable signal, with famous-case stratification and the
  positive control built in from the start."*

This module IS that successor. The four changes its predecessor demanded are
built in from the start: short horizons (5/20/60 trading days rather than 12
months), an outcome-salience stratum, an identification canary on every masked
item and a recall canary on every identified one, and a PIT baseline bank so
"no skill" can be told apart from "no signal".

It adds one thing AMNESIA-1 did not have, and it is the thing that makes the
result interpretable: **an ERA stratum**. A masked prompt could score worse
simply because it is stranger to read, not because the identified prompt is
being remembered. So the estimator of leakage is not the identified-minus-masked
gap. It is the DIFFERENCE of that gap between an era the model plausibly
memorised and an era after its training data ends (CANON §18 — a difference is
tested as a difference, with its own SE).

THE FIXED SLATE, AND WHY THE SWARM'S FREE CHOICE WOULD RUIN THIS
----------------------------------------------------------------
`llm_swarm` lets each reply choose its own observables and horizons. That is
right for exploration and fatal for a paired test: if arm A answers
`return_sign@20` and arm B answers `abs_move_exceeds@60`, there is no pair to
difference. Here the five questions are FIXED, identical in both arms, with
thresholds computed from point-in-time volatility so they are the same number in
both prompts. Every accepted forecast therefore has a partner, or is counted as
a lost slot.

ARCHITECTURE_RESULT_ONLY (Amendment A, A5 and A6)
-------------------------------------------------
These are HISTORICAL resolutions. They may NOT set production specialist
weights, may NOT arm a lane, and may NOT be quoted as forward calibration.
They characterise the INSTRUMENT. Forward records from 2026-08-16 remain the
only certification path. That sentence is repeated on every artifact this
module writes, by construction rather than by discipline.

THE LEDGER RULE THAT MATTERS MOST
---------------------------------
Historical records are written to a SEPARATE ledger file. `predictions.jsonl`
is valuable precisely because it is forward-only; backfilling it with records
whose outcomes were already in the price series would destroy the one clean
instrument the programme has. Every write path here takes an explicit `path`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from backend import config as cfg
from backend.services.belief_state import (HORIZONS, Observable,
                                           PredictionRecord, make_prediction)
from backend.services.research_budget import ResearchBudgetExhausted

logger = logging.getLogger(__name__)

MODULE_VERSION = "leakage_probe/1.0.0"
CAMPAIGN = "grand_arena_1"
PURPOSE = "leakage_probe_forecast"

#: The historical ledger. NEVER `belief_state.PREDICTIONS`. See the module
#: docstring: the forward ledger's whole value is that it is forward-only.
LEAK_PREDICTIONS = cfg.OPTIMUS_LEDGER_DIR / "leakage_probe_predictions.jsonl"

_FORBIDDEN = re.compile(cfg.WHY_MOVED_FORBIDDEN_PATTERN, re.I)


# ── the fixed slate ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Slot:
    """One question every arm must answer, so every answer has a partner."""
    key: str
    observable: str
    horizon_days: int
    threshold_rule: str | None      # None | "sigma20" | "sigma60"


SLATE: tuple[Slot, ...] = (
    Slot("q1", "return_sign", 5, None),
    Slot("q2", "return_sign", 20, None),
    Slot("q3", "beats_benchmark", 20, None),
    Slot("q4", "abs_move_exceeds", 20, "sigma20"),
    Slot("q5", "drawdown_exceeds", 60, "sigma60"),
)

#: Threshold floors and caps. A threshold of 0.004 resolves TRUE almost always
#: and a threshold of 0.9 almost never; either way the slot carries no
#: information and the Brier on it is a description of the threshold rather
#: than of the forecaster.
THRESHOLD_BOUNDS = {"sigma20": (0.03, 0.45), "sigma60": (0.04, 0.55)}


def slot_thresholds(snapshot: dict) -> dict[str, float | None]:
    """PIT thresholds for the slate, from the snapshot's own realised vol.

    Scaled per security so the base rate of `abs_move_exceeds` is roughly the
    same everywhere. A single fixed 10% threshold would make the question
    trivial for a biotech and impossible for a utility, and the resulting Brier
    would rank sectors rather than forecasters.
    """
    vol = ((snapshot.get("realised_vol_annualised_pct") or {}).get("63d")
           or (snapshot.get("realised_vol_annualised_pct") or {}).get("21d"))
    out: dict[str, float | None] = {}
    for rule, days, mult in (("sigma20", 20, 1.0), ("sigma60", 60, 0.8)):
        if vol is None:
            out[rule] = None
            continue
        lo, hi = THRESHOLD_BOUNDS[rule]
        v = float(vol) / 100.0 * math.sqrt(days / 252.0) * mult
        out[rule] = round(min(max(v, lo), hi), 3)
    return out


def slate_for(snapshot: dict) -> list[dict] | None:
    """The five questions for one item, or None when they cannot be priced."""
    thr = slot_thresholds(snapshot)
    rows = []
    for s in SLATE:
        t = None if s.threshold_rule is None else thr.get(s.threshold_rule)
        if s.threshold_rule is not None and t is None:
            return None
        rows.append({"key": s.key, "observable": s.observable,
                     "horizon_days": s.horizon_days, "threshold": t})
    return rows


# ── masking ─────────────────────────────────────────────────────────────────

#: Fields that carry IDENTITY or ERA rather than situation. Removed in every
#: masked arm. `benchmark` is here because "SPY" names the market and the
#: country; `company_name` because it names the firm; `as_of` because a date is
#: the single most efficient way to look an outcome up in memory.
IDENTITY_FIELDS = ("ticker", "as_of", "company_name", "shortName", "benchmark",
                   "market_cap_usd", "shares_short_pct_float")

#: Additionally removed by the DEEP mask. These do not identify the SECURITY —
#: they identify the ERA, and an era is enough to remember a market by. A model
#: shown "the benchmark returned -38% over the last year" has been told it is
#: standing in early 2009 whether or not it has been told the date.
ERA_FIELDS = ("benchmark_trailing_return_pct", "industry")

COARSE_SECTOR = {
    "Technology": "cyclical-growth", "Information Technology": "cyclical-growth",
    "Communication Services": "cyclical-growth", "Communications": "cyclical-growth",
    "Consumer Discretionary": "cyclical-growth", "Consumer Cyclical": "cyclical-growth",
    "Healthcare": "healthcare", "Health Care": "healthcare",
    "Financials": "financial", "Financial Services": "financial",
    "Real Estate": "financial",
    "Energy": "resource", "Materials": "resource", "Basic Materials": "resource",
    "Utilities": "defensive", "Consumer Staples": "defensive",
    "Consumer Defensive": "defensive", "Industrials": "industrial",
}


def pseudonym(ticker: str, as_of: str, salt: str = "LEAK1") -> str:
    """A stable, non-ticker-shaped alias for one (security, date).

    Deliberately shaped so it cannot collide with a real symbol: a hyphen and
    four hex digits. A pseudonym that happened to spell a real ticker would put
    the identity back in the prompt by accident, which is the one failure this
    whole arm cannot survive.
    """
    h = hashlib.sha256(f"{salt}|{ticker.upper()}|{as_of}".encode()).hexdigest()
    return f"UNIT-{h[:4].upper()}"


def mask_snapshot(snapshot: dict, *, deep: bool = False,
                  salt: str = "LEAK1") -> dict:
    """The same situation with its identity — and optionally its era — removed.

    Every NUMERIC feature survives untouched. That is the design: if the masked
    arm were also a smaller feature set, a gap between the arms would measure
    "arm A had more inputs" rather than "arm A had the answer". The only things
    that change are the name, the date, the absolute price level and the name of
    the benchmark, none of which is a predictive feature.
    """
    tkr = str(snapshot.get("ticker", "")).upper()
    as_of = str(snapshot.get("as_of", ""))
    out = {k: v for k, v in snapshot.items() if k not in IDENTITY_FIELDS}
    if deep:
        for k in ERA_FIELDS:
            out.pop(k, None)
        sec = str(snapshot.get("sector") or snapshot.get("vendor_sector") or "")
        out["sector"] = COARSE_SECTOR.get(sec, "unclassified")
        out.pop("vendor_sector", None)
    out["security_id"] = pseudonym(tkr, as_of, salt)
    out["observation_point"] = (
        "T0. Every number below is computed from closes at or before T0. You "
        "are not told when T0 is and you must not assume; horizons are counted "
        "in trading days forward from T0.")
    # Rebased, not removed: a level of 412.83 is a lookup key, a level of 100 is
    # a unit. Every downstream field (returns, drawdowns, betas) is already
    # scale-free, so nothing predictive is lost.
    out["last_close_rebased"] = 100.0
    out.pop("last_close", None)
    out["benchmark_id"] = "BENCHMARK (a broad market index of the same market)"
    return out


#: Tokens too generic to treat as a company name. "Corp" appearing in a masked
#: prompt is not a leak; "Nvidia" is.
_GENERIC_NAME_TOKENS = {
    "inc", "corp", "corporation", "company", "co", "ltd", "limited", "plc",
    "holdings", "holding", "group", "the", "and", "international", "class",
    "common", "stock", "shares", "trust", "fund", "etf", "technologies",
    "technology", "systems", "industries", "solutions", "partners", "capital",
    "energy", "financial", "pharmaceuticals", "pharmaceutical", "therapeutics",
    "sciences", "resources", "services", "products", "brands", "labs",
    "laboratories", "communications", "enterprises", "motors", "n.v.", "s.a.",
}

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def masking_violations(text: str, *, ticker: str, company_name: str = "",
                       as_of: str = "", last_close: float | None = None,
                       other_tickers: Iterable[str] = (),
                       benchmark: str = cfg.SWARM_BENCHMARK) -> list[dict]:
    """Everything identifying that survived the mask. Empty list = clean.

    A leak in the masker silently destroys the experiment — the masked arm
    quietly becomes a second identified arm, the gap collapses to zero, and the
    conclusion "no leakage detectable" is then a statement about a bug. So this
    runs on the RENDERED prompt of every masked item, before the call, and an
    item with any violation is REFUSED rather than repaired: a prompt patched
    after the fact is a prompt nobody can reconstruct.
    """
    v: list[dict] = []
    t = str(text)

    def hit(kind: str, what: str) -> None:
        v.append({"kind": kind, "match": str(what)[:60]})

    for sym in {str(ticker).upper(), *[str(x).upper() for x in other_tickers]}:
        if len(sym) < 3:
            # Two-letter symbols collide with ordinary uppercase words (IT, ON,
            # SO, ALL). Scanning for them would report a leak on every prompt
            # and train the reader to ignore this check, which is worse than
            # not running it. The item's OWN ticker is always scanned below.
            continue
        if re.search(rf"\b{re.escape(sym)}\b", t):
            hit("ticker", sym)
    own = str(ticker).upper()
    if own and re.search(rf"\b{re.escape(own)}\b", t):
        hit("own_ticker", own)
    if benchmark and re.search(rf"\b{re.escape(benchmark.upper())}\b", t):
        hit("benchmark_name", benchmark)
    for tok in re.split(r"[^A-Za-z0-9.]+", str(company_name or "")):
        if len(tok) >= 4 and tok.lower() not in _GENERIC_NAME_TOKENS:
            if re.search(rf"\b{re.escape(tok)}\b", t, re.I):
                hit("company_name_token", tok)
    for m in _ISO_DATE.findall(t):
        hit("iso_date", m)
    for m in _YEAR.findall(t):
        hit("bare_year", m)
    if as_of and as_of in t:
        hit("as_of_literal", as_of)
    if last_close is not None:
        for s in {f"{last_close:.2f}", f"{last_close:.4f}",
                  str(round(float(last_close), 2))}:
            if len(s) >= 5 and s in t:
                hit("absolute_price_level", s)
    return v


# ── the roles and the framings ──────────────────────────────────────────────

#: Sector-free roles only. A sector-bound role routed at every security would
#: abstain on most of them, and an abstention is a lost pair rather than a
#: finding here. Six roles, so the role-spread measurement has something to
#: measure.
ROLES: dict[str, str] = {
    "company_fundamental":
        "You are a company fundamentals analyst. You reason about revenue "
        "durability, unit economics, margin structure, cash conversion, "
        "balance-sheet capacity and the gap between reported growth and the "
        "growth already embedded in the price.",
    "execution_momentum":
        "You are a cross-sectional momentum and trend analyst. You reason about "
        "relative strength across horizons, trend persistence and reversal, "
        "volatility regime and drawdown state, and the documented asymmetry "
        "between 12-1 momentum and 1-month reversal.",
    "options_volatility":
        "You are a volatility and market-microstructure analyst. You reason "
        "about realised volatility and its term structure, the clustering of "
        "variance, liquidity, and the difference between a move caused by "
        "information and a move caused by positioning.",
    "macro_rates":
        "You are a rates and macro strategist. You reason about the duration "
        "sensitivity of long-dated equity cash flows, credit and liquidity "
        "conditions, and how a security's beta and drawdown state express its "
        "exposure to them.",
    "behavioral_narrative":
        "You are a behavioural and narrative analyst. You reason about "
        "attention, crowding, anchoring on prior prices, and the lifecycle of a "
        "theme from discovery to saturation. You know a narrative can be "
        "correct and still be fully priced.",
    "skeptic":
        "You are a professional skeptic whose job is to find the reason a "
        "position loses money. You default to the base rate, you distrust any "
        "thesis needing several things to go right in sequence, and you know "
        "most of what looks like signal in a single security is idiosyncratic "
        "noise.",
}

#: Deliberately opposed framings, for the diversity experiment ONLY. They are
#: NOT part of the leakage arms: a bull-only framing is a biased forecaster by
#: construction and its Brier is a statement about the instruction.
FRAMINGS: dict[str, str] = {
    "framing_bull":
        "Argue the constructive case FIRST and let it lead your probabilities. "
        "You are being asked for the strongest defensible upside reading of "
        "this evidence.",
    "framing_bear":
        "Argue the destructive case FIRST and let it lead your probabilities. "
        "You are being asked for the strongest defensible downside reading of "
        "this evidence.",
    "framing_baserate":
        "Ignore narrative entirely. Reason ONLY from unconditional base rates "
        "for a security with this volatility, beta and drawdown state, and "
        "state probabilities a statistician would defend without a story.",
}


def _slate_block(slate: list[dict]) -> str:
    lines = []
    for s in slate:
        thr = ("null" if s["threshold"] is None else f"{s['threshold']}")
        lines.append(f'  {{"key": "{s["key"]}", "observable": "{s["observable"]}", '
                     f'"horizon_days": {s["horizon_days"]}, "threshold": {thr}}}')
    return "[\n" + ",\n".join(lines) + "\n]"


CONTRACT_HEAD = """
You produce a STRUCTURED, FALSIFIABLE VIEW of ONE security. Not a
recommendation, not commentary. Everything you say is written to a ledger and
graded against actual closes on a fixed schedule.

ABSTAINING IS A FIRST-CLASS ANSWER. With no reasoning that distinguishes this
security from a random one, return {"abstain": true, "abstain_reason": "<one
specific sentence>"} and nothing else. It is recorded and costs you nothing.

Hard rules:
- Never state a position size, weight, allocation or action, and never use the
  words buy, sell, hold, trim, overweight, underweight, take profit, stop loss.
- PROBABILITY 0.50 IS REJECTED. A coin flip you called a coin flip is not a
  forecast. If your genuine credence is one half you have no view: abstain.
- Every forecast carries a counter_thesis: the concrete thing that would make
  you wrong.
"""

CONTRACT_TAIL = """
YOU DO NOT CHOOSE THE QUESTIONS. Answer EXACTLY the questions below, all of
them, in this order, using the given key. The observable, the horizon and the
threshold are fixed; only the probability, the thesis and the counter_thesis
are yours. A question you cannot answer is answered by abstaining from the
whole item, not by dropping a row.

  return_sign        P(total return over the horizon > 0)
  beats_benchmark    P(the security's return over the horizon > the benchmark's)
  abs_move_exceeds   P(|total return| over the horizon > threshold)
  drawdown_exceeds   P(the deepest peak-to-trough fall inside the horizon
                      exceeds threshold in magnitude)

Thresholds are DECIMAL FRACTIONS already: 0.09 means 9%.

Return ONLY valid JSON, no prose outside it, matching exactly:
{"abstain": false, "abstain_reason": "",
 "market_implied_expectation": str,
 "optimus_expectation": str,
 "expectation_discrepancy": str,
 "causal_chain": [str, ...],
 "confidence": float 0..1,
 "counterargument": str,
 "forecasts": [{"key": str, "probability": float 0..1 and NOT 0.50,
                "thesis": str, "counter_thesis": str}, ...]}
"""


def build_prompt(role: str, snapshot: dict, slate: list[dict], *,
                 arm: str, framing: str | None = None,
                 opponent: dict | None = None,
                 benchmark: str = cfg.SWARM_BENCHMARK) -> tuple[str, str]:
    """System and user prompt for one cell.

    `arm` decides whether the snapshot is the identified one or a masked one;
    the snapshot handed in is already whichever it is, so this function never
    re-derives the mask. That matters: a mask applied in two places is a mask
    that can be applied in one of them.
    """
    system = ROLES.get(role, ROLES["company_fundamental"])
    if framing:
        system = system + "\n\n" + FRAMINGS[framing]
    system = system + "\n" + CONTRACT_HEAD + CONTRACT_TAIL

    if arm == "identified":
        head = (f"Form your own independent view of ONE security, standing at "
                f"{snapshot.get('as_of')}. You have not seen and will not see "
                f"any other analyst's answer.\n\n"
                f"Point-in-time snapshot (every number is computed from closes "
                f"at or before {snapshot.get('as_of')}; nothing after that date "
                f"is available to you):\n")
        tail = (f"\n`beats_benchmark` is graded against {benchmark}.\n")
    else:
        head = ("Form your own independent view of ONE security. Its identity, "
                "its market and the calendar date have been removed; what "
                "remains is the complete set of point-in-time facts. Reason "
                "from the evidence in front of you. Do not speculate about "
                "which security or which period this is — you will not be told, "
                "and a guess is not a forecast.\n\n"
                "Point-in-time snapshot, as of T0:\n")
        tail = ("\n`beats_benchmark` is graded against the broad market index "
                "of the same market.\n")

    user = (head
            + json.dumps(snapshot, indent=1, sort_keys=True, default=str)
            + "\n\nAnswer EXACTLY these questions:\n" + _slate_block(slate)
            + tail)

    if opponent is not None:
        # The adversarial arm. It is NOT independent by construction, it is
        # labelled that way everywhere it appears, and it is never pooled with
        # the independent arms.
        user += (
            "\nAnother analyst, working from the same snapshot, has already "
            "answered. Their answer is below. Your job is to REFUTE it: find "
            "what they got wrong, and state YOUR probabilities. Agreeing where "
            "they are right is allowed and is not a failure, but a reply that "
            "merely restates theirs has not done the job.\n"
            + json.dumps(opponent, indent=1, default=str)[:2500] + "\n")
    return system, user


# ── canaries ────────────────────────────────────────────────────────────────

CANARY_SYSTEM = ("You answer only with strict JSON matching the requested "
                 "schema. Honesty about uncertainty is worth more than a guess.")


def identification_canary(masked: dict) -> tuple[str, str]:
    """Ask the model to break the mask. The direct measurement of porosity.

    Asked BEFORE the forecast for the same item so it cannot be primed by it,
    and asked of the MASKED snapshot exactly as the forecaster will see it —
    a canary on a different rendering measures a different prompt.
    """
    user = ("The following describes a real listed security at some point in "
            "history, with its identity, its market and its date removed.\n\n"
            + json.dumps(masked, indent=1, sort_keys=True, default=str)
            + "\n\nCan you identify it, and can you date it?\n"
              'Return JSON exactly: {"ticker": "<ticker or UNKNOWN>", '
              '"company": "<name or UNKNOWN>", "year": <4-digit year or 0>, '
              '"confidence": "<HIGH|MEDIUM|LOW>"}')
    return CANARY_SYSTEM, user


def recall_canary(ticker: str, as_of: str, company: str = "") -> tuple[str, str]:
    """Ask the model outright what it remembers. AMNESIA-1B's positive control.

    Without this, "the masked arm did not score worse" has two readings that
    look identical in aggregate: the mask worked, or there was nothing to mask.
    AMNESIA-1B measured the second regime directly (95.8% declined; 5 of 5
    correct when it did answer) and this is the same instrument at the horizons
    this campaign actually uses.
    """
    who = f"{company} (ticker {ticker})" if company else f"ticker {ticker}"
    user = (f"Security: {who}. Date: {as_of}.\n\n"
            f"From your training data, do you recall what this security's price "
            f"actually did over the 20 trading days AFTER that date, and over "
            f"the 60 trading days after it?\n"
            f'Return JSON exactly: {{"recall": "<YES|NO>", '
            f'"direction_20d": "<UP|DOWN|UNSURE>", '
            f'"direction_60d": "<UP|DOWN|UNSURE>", '
            f'"what": "<=25 words"}}')
    return CANARY_SYSTEM, user


# ── parsing ─────────────────────────────────────────────────────────────────

@dataclass
class ParsedCall:
    """One reply, split into what can be graded and what was refused."""
    role: str
    ticker: str
    abstained: bool = False
    abstain_reason: str = ""
    forecasts: list[dict] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)
    confidence: float | None = None
    raw: dict | None = None

    def reject(self, reason: str, detail: str = "") -> None:
        self.rejections.append({"reason": reason, "detail": str(detail)[:240]})


def extract_json(text: str) -> dict:
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


REQUIRED_FIELDS = ("market_implied_expectation", "optimus_expectation",
                   "expectation_discrepancy", "confidence", "counterargument",
                   "forecasts")


def parse_reply(role: str, ticker: str, slate: list[dict], text: str) -> ParsedCall:
    """Everything gradeable in one reply, against the FIXED slate.

    Slots are matched by key. A reply that answers four of five questions loses
    the fifth as a counted `slot_missing`, and its partner in the other arm is
    dropped from the paired test rather than compared against nothing.
    """
    out = ParsedCall(role=role, ticker=str(ticker).upper())
    try:
        raw = extract_json(text)
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
            out.reject("abstain_without_reason", "cannot be told from a failure")
            return out
        out.abstained = True
        out.abstain_reason = reason[:400]
        return out

    missing = [k for k in REQUIRED_FIELDS if k not in raw]
    if missing:
        out.reject("missing_required_field", ",".join(missing))
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

    by_key = {s["key"]: s for s in slate}
    items = raw.get("forecasts")
    if not isinstance(items, list) or not items:
        out.reject("no_forecasts", "a non-abstaining reply with no forecast is "
                                   "a paragraph, not a view")
        return out
    seen: set[str] = set()
    kept: list[dict] = []
    for f in items:
        if not isinstance(f, dict):
            out.reject("forecast_not_object", repr(f)[:120])
            continue
        key = str(f.get("key", "")).strip().lower()
        spec = by_key.get(key)
        if spec is None:
            out.reject("unknown_slot", repr(f.get("key")))
            continue
        if key in seen:
            out.reject("duplicate_slot", key)
            continue
        try:
            p = float(f.get("probability"))
        except (TypeError, ValueError):
            out.reject("probability_not_numeric", repr(f.get("probability")))
            continue
        if not 0.0 <= p <= 1.0:
            out.reject("probability_not_a_credence", repr(p))
            continue
        if abs(p - 0.5) < cfg.SWARM_COIN_FLIP_EPS:
            out.reject("coin_flip_filler",
                       f"{key} p={p} — the abstain channel exists for no view")
            continue
        ct = str(f.get("counter_thesis", "")).strip()
        if not ct:
            out.reject("no_counter_thesis", key)
            continue
        blob = f"{f.get('thesis', '')} {ct}"
        hits = _FORBIDDEN.findall(blob)
        if hits:
            out.reject("recommendation_language",
                       f"{key}: {sorted({str(x).lower() for x in hits})}")
            continue
        seen.add(key)
        kept.append({"key": key, "observable": spec["observable"],
                     "horizon_days": spec["horizon_days"],
                     "threshold": spec["threshold"], "probability": p,
                     "thesis": str(f.get("thesis", ""))[:400],
                     "counter_thesis": ct[:400]})
    for k in by_key:
        if k not in seen:
            out.reject("slot_missing", k)
    out.forecasts = kept
    return out


def mint(parsed: ParsedCall, *, snapshot: dict, prompt: str, model: str,
         model_version: str, made_at: str,
         benchmark: str = cfg.SWARM_BENCHMARK) -> list[PredictionRecord]:
    """Validated forecasts into ledger records, with `made_at` in the PAST.

    `make_prediction` is CALLED, never reimplemented, so its refusals — the
    percent/fraction one above all — apply here unchanged and become counted
    rejections carrying the ledger's own message.
    """
    records: list[PredictionRecord] = []
    for f in parsed.forecasts:
        try:
            records.append(make_prediction(
                ticker=parsed.ticker, specialist=parsed.role,
                observable=Observable(f["observable"]),
                horizon_days=f["horizon_days"], probability=f["probability"],
                threshold=f["threshold"],
                benchmark=(benchmark
                           if f["observable"] == Observable.BEATS_BENCHMARK.value
                           else None),
                thesis=f["thesis"], counter_thesis=f["counter_thesis"],
                next_observable="", model=model, model_version=model_version,
                prompt=prompt, input_snapshot=snapshot, made_at=made_at))
        except Exception as exc:                               # noqa: BLE001
            parsed.reject("ledger_refused",
                          f"{f['key']}: {type(exc).__name__}: {exc}")
    return records


# ── the vendor call ─────────────────────────────────────────────────────────

@dataclass
class Reply:
    text: str
    model_version: str
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0
    latency_ms: float = 0.0
    retries: int = 0


_RETRYABLE = ("429", "500", "502", "503", "504", "timeout", "timed out",
              "connection", "overloaded", "rate limit", "temporarily")


def _is_retryable(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    if getattr(exc, "status_code", None) in (408, 409, 429, 500, 502, 503, 504):
        return True
    return any(t in s for t in _RETRYABLE)


def _client(timeout: float = cfg.SWARM_TIMEOUT_S):
    import os

    from openai import OpenAI
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is empty. Keys are env-only by house rule; a run "
            "with no key must fail loudly rather than quietly produce nothing "
            "and be recorded as a night with no spend.")
    return OpenAI(api_key=key,
                  base_url=os.getenv("DEEPSEEK_BASE_URL",
                                     "https://api.deepseek.com"),
                  timeout=timeout, max_retries=0)


def call_llm(system: str, user: str, *, client=None,
             model: str = cfg.SWARM_MODEL,
             temperature: float = cfg.SWARM_TEMPERATURE,
             max_tokens: int = 1400,
             max_retries: int = cfg.SWARM_MAX_RETRIES,
             since: str | None = None,
             rng: random.Random | None = None) -> Reply:
    """One budget-gated DeepSeek call. `require()` before EVERY wire request.

    A retry is a request and spends like one, so the governor is consulted
    before each attempt. When it raises, it propagates: an exhausted budget is a
    campaign-level stop, and absorbing it into a per-cell failure count would
    make it look like vendor flakiness while the pool kept submitting work.
    """
    from backend.services import research_budget
    from backend.services.llm_telemetry import extract_usage

    cli = client or _client()
    rnd = rng or random
    retries = 0
    last: Exception | None = None
    t0 = time.perf_counter()
    for attempt in range(max_retries + 1):
        research_budget.require(CAMPAIGN, since=since)
        try:
            kw: dict[str, Any] = {"model": model, "max_tokens": max_tokens,
                                  "response_format": {"type": "json_object"},
                                  "messages": [
                                      {"role": "system", "content": system},
                                      {"role": "user", "content": user}]}
            # deepseek-reasoner rejects `temperature`; passing it to chat and
            # omitting it for the reasoner is the difference between the two
            # models being comparable and one of them 400-ing every call.
            if not str(model).endswith("reasoner"):
                kw["temperature"] = temperature
            resp = cli.chat.completions.create(**kw)
        except ResearchBudgetExhausted:
            raise
        except Exception as exc:                               # noqa: BLE001
            last = exc
            if attempt >= max_retries or not _is_retryable(exc):
                break
            retries += 1
            time.sleep(cfg.SWARM_BACKOFF_BASE_S * (2 ** attempt)
                       * (0.5 + rnd.random()))
            continue
        u = extract_usage(resp, "deepseek")
        return Reply(text=(resp.choices[0].message.content or ""),
                     model_version=str(getattr(resp, "model", model)),
                     latency_ms=(time.perf_counter() - t0) * 1000.0,
                     retries=retries, **u)
    assert last is not None
    raise last


# ── one cell ────────────────────────────────────────────────────────────────

@dataclass
class CellResult:
    cell_id: str
    condition: str
    arm: str
    role: str
    ticker: str
    as_of: str
    era: str
    status: str                       # ok | abstained | zero_yield | failed | refused_mask
    parsed: ParsedCall | None = None
    records: list[PredictionRecord] = field(default_factory=list)
    reply: Reply | None = None
    error: str | None = None
    extra: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        p = self.parsed
        return {
            "cell_id": self.cell_id, "condition": self.condition,
            "arm": self.arm, "role": self.role, "ticker": self.ticker,
            "as_of": self.as_of, "era": self.era, "status": self.status,
            "error": self.error,
            "confidence": (p.confidence if p else None),
            "abstain_reason": (p.abstain_reason if p else ""),
            "rejections": [{"reason": r["reason"], "detail": r["detail"][:120]}
                           for r in (p.rejections if p else [])],
            "forecasts": [{"key": f["key"], "observable": f["observable"],
                           "horizon_days": f["horizon_days"],
                           "threshold": f["threshold"],
                           "probability": f["probability"]}
                          for f in (p.forecasts if p else [])],
            "prediction_ids": [r.prediction_id for r in self.records],
            "tokens_in": (self.reply.tokens_in if self.reply else 0),
            "tokens_out": (self.reply.tokens_out if self.reply else 0),
            "cached_tokens": (self.reply.cached_tokens if self.reply else 0),
            "latency_ms": round(self.reply.latency_ms, 1) if self.reply else None,
            "retries": (self.reply.retries if self.reply else 0),
            "model": self.extra.get("model", cfg.SWARM_MODEL),
            "model_version": (self.reply.model_version if self.reply else ""),
            "extra": self.extra,
        }


def run_cell(*, cell_id: str, condition: str, arm: str, role: str,
             item: dict, snapshot: dict, slate: list[dict],
             model: str = cfg.SWARM_MODEL,
             temperature: float = cfg.SWARM_TEMPERATURE,
             framing: str | None = None, opponent: dict | None = None,
             since: str | None = None,
             llm: Callable[..., Reply] | None = None,
             telemetry_path: Any = None,
             mask_check: bool = True) -> CellResult:
    """One forecast cell, end to end, refusing anything ungradeable.

    A MASKED cell whose rendered prompt still contains an identifier is refused
    BEFORE the wire call. That refusal costs nothing and is counted; making the
    call anyway would put a silently-identified record into the masked arm and
    bias the whole experiment toward "no leakage".
    """
    system, user = build_prompt(role, snapshot, slate, arm=arm,
                                framing=framing, opponent=opponent)
    base = dict(cell_id=cell_id, condition=condition, arm=arm, role=role,
                ticker=item["ticker"], as_of=item["as_of"], era=item["era"])

    if mask_check and arm != "identified":
        viol = masking_violations(
            user, ticker=item["ticker"], company_name=item.get("company_name", ""),
            as_of=item["as_of"], last_close=item.get("last_close"),
            other_tickers=item.get("universe", ()))
        if viol:
            logger.warning("mask leak in %s: %s", cell_id, viol[:3])
            return CellResult(status="refused_mask", parsed=None,
                              extra={"violations": viol[:6], "model": model},
                              **base)

    call = llm or call_llm
    try:
        reply = call(system, user, model=model, temperature=temperature,
                     since=since)
    except ResearchBudgetExhausted:
        raise
    except Exception as exc:                                   # noqa: BLE001
        logger.warning("cell %s failed: %s: %s", cell_id, type(exc).__name__, exc)
        return CellResult(status="failed", parsed=None,
                          error=f"{type(exc).__name__}: {exc}"[:280],
                          extra={"model": model}, **base)

    parsed = parse_reply(role, item["ticker"], slate, reply.text)
    records = ([] if (parsed.abstained or not parsed.forecasts)
               else mint(parsed, snapshot=snapshot, prompt=system + user,
                         model=model, model_version=reply.model_version,
                         made_at=item["made_at"]))
    status = ("abstained" if parsed.abstained
              else "ok" if records else "zero_yield")

    try:
        from backend.services.llm_telemetry import record_call
        record_call(provider="deepseek", model=model,
                    model_version=reply.model_version, purpose=PURPOSE,
                    agent=f"{role}|{condition}|{arm}", prompt=system + user,
                    context=snapshot, tokens_in=reply.tokens_in,
                    tokens_out=reply.tokens_out,
                    cached_tokens=reply.cached_tokens,
                    latency_ms=reply.latency_ms, retries=reply.retries,
                    schema_valid=bool(parsed.abstained or parsed.forecasts
                                      or parsed.raw is not None),
                    error=(None if status != "zero_yield"
                           else ";".join(r["reason"]
                                         for r in parsed.rejections)[:300]),
                    prediction_ids=[r.prediction_id for r in records],
                    meta={"cell_id": cell_id, "condition": condition,
                          "arm": arm, "ticker": parsed.ticker,
                          "as_of": item["as_of"], "era": item["era"],
                          "status": status, "module": MODULE_VERSION},
                    path=telemetry_path)
    except Exception as exc:                                   # noqa: BLE001
        logger.warning("telemetry not recorded for %s (%s) — the spend is "
                       "MISSING from the ledger, the forecast is not",
                       cell_id, exc)

    r = CellResult(status=status, parsed=parsed, records=records, reply=reply,
                   extra={"model": model, "temperature": temperature,
                          "framing": framing}, **base)
    r.extra["raw"] = parsed.raw if (opponent is None and condition == "debate") else None
    return r


# ── statistics: a difference tested as a difference (§18/§19) ───────────────

def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def _nw_se(x: Sequence[float], lag: int) -> float:
    """Newey-West SE of the mean of a time-ordered series.

    Lag is passed in rather than derived, because the right lag here is a
    property of the DESIGN — 20- and 60-day horizons started at nearby dates
    overlap, and the SE has to carry that. A lag chosen by the usual n^(2/9)
    rule would be blind to it.
    """
    n = len(x)
    if n < 3:
        return float("nan")
    m = _mean(x)
    e = [v - m for v in x]
    g0 = sum(v * v for v in e) / n
    s = g0
    for L in range(1, min(lag, n - 1) + 1):
        gl = sum(e[t] * e[t - L] for t in range(L, n)) / n
        s += 2.0 * (1.0 - L / (lag + 1.0)) * gl
    s = max(s, g0 * 1e-6)
    return math.sqrt(s / n)


def paired_difference(pairs: Sequence[dict], *, lag: int = 4,
                      key: str = "d") -> dict:
    """The paired difference, with its OWN standard errors (CANON §18).

    Three SEs, because they answer three different questions and the honest
    ruler is the widest of them:

    * `se_iid_pairs` treats every matched slot as independent. It is the most
      generous and is reported so the reader can see how much of any apparent
      significance is that assumption.
    * `se_cluster_date` clusters by observation date: five slots and six roles
      at one date are one draw of the world, not thirty.
    * `se_hac_date` adds Newey-West on the date series, because horizons
      started at nearby dates overlap in calendar time.
    """
    d = [float(p[key]) for p in pairs]
    n = len(d)
    if n == 0:
        return {"n_pairs": 0, "reading": "no matched pairs — nothing to test"}
    by_date: dict[str, list[float]] = {}
    for p in pairs:
        by_date.setdefault(str(p["as_of"]), []).append(float(p[key]))
    dates = sorted(by_date)
    dm = [_mean(by_date[t]) for t in dates]
    T = len(dates)

    mean = _mean(d)
    se_iid = (math.sqrt(sum((v - mean) ** 2 for v in d) / (n - 1) / n)
              if n > 1 else float("nan"))
    mdm = _mean(dm)
    se_cl = (math.sqrt(sum((v - mdm) ** 2 for v in dm) / (T - 1) / T)
             if T > 1 else float("nan"))
    se_hac = _nw_se(dm, lag) if T > 2 else float("nan")
    ses = {"se_iid_pairs": se_iid, "se_cluster_date": se_cl,
           "se_hac_date": se_hac}
    worst = max((v for v in ses.values() if v == v), default=float("nan"))
    return {
        "n_pairs": n, "n_dates": T,
        "mean_difference": round(mean, 6),
        "mean_difference_date_weighted": round(mdm, 6),
        **{k: (round(v, 6) if v == v else None) for k, v in ses.items()},
        "se_used": (round(worst, 6) if worst == worst else None),
        "t_stat": (round(mdm / worst, 3) if worst == worst and worst > 0
                   else None),
        "nw_lag": lag,
    }


def measure_mde(pairs: Sequence[dict], *, lag: int = 4, key: str = "d",
                grid: Sequence[float] = (0.002, 0.005, 0.01, 0.015, 0.02, 0.03,
                                         0.04, 0.05, 0.075, 0.10, 0.15),
                n_sim: int = 400, target_power: float = 0.80,
                seed: int = 20260812) -> dict:
    """The MEASURED 80%-power MDE for this paired difference (CANON §19).

    Never a formula. The observed differences are NULL-CENTRED, worlds are
    rebuilt by resampling whole OBSERVATION DATES with replacement (the cluster
    that actually repeats), an effect of known size is planted, and the same
    test that will be run for real is run on each world. The reported MDE is the
    smallest planted effect the design fires on 80% of the time.

    A null below this number is a statement about the design, not about the
    world, and may never be quoted as a kill.
    """
    import numpy as np

    if not pairs:
        return {"mde_at_80pct_power": None,
                "reading": "no pairs, so the design's resolution is undefined"}
    by_date: dict[str, list[float]] = {}
    for p in pairs:
        by_date.setdefault(str(p["as_of"]), []).append(float(p[key]))
    dates = sorted(by_date)
    T = len(dates)
    if T < 4:
        return {"mde_at_80pct_power": None, "n_dates": T,
                "reading": f"only {T} observation date(s) — no clustered "
                           f"resampling is meaningful and no MDE is claimed"}
    obs_mean = _mean([v for t in dates for v in by_date[t]])
    centred = {t: [v - obs_mean for v in by_date[t]] for t in dates}
    rng = np.random.default_rng(seed)

    rows = []
    for delta in grid:
        fires = 0
        for _ in range(n_sim):
            pick = rng.integers(0, T, size=T)
            dm = [_mean(centred[dates[i]]) + delta for i in pick]
            m = _mean(dm)
            se = _nw_se(dm, lag)
            fires += bool(se == se and se > 0 and abs(m / se) >= 1.96)
        rows.append({"planted": delta, "power": round(fires / n_sim, 3)})
        if rows[-1]["power"] >= target_power:
            break
    hit = [r for r in rows if r["power"] >= target_power]
    return {
        "mde_at_80pct_power": hit[0]["planted"] if hit else None,
        "grid": rows, "target_power": target_power, "n_dates": T,
        "n_pairs": len(pairs),
        "note": ("measured by planting Brier differences of known size into "
                 "date-clustered resampled worlds and running the real test — "
                 "not derived from a formula"),
        "if_none": ("no effect on the grid reached 80% power: this design "
                    "cannot reliably detect ANY leakage of plausible size, and "
                    "its null is a statement about the design (CANON §19)"),
    }


def difference_in_differences(pairs_a: Sequence[dict], pairs_b: Sequence[dict],
                              *, lag: int = 4, key: str = "d",
                              n_boot: int = 4000, seed: int = 20260812) -> dict:
    """(gap in stratum A) minus (gap in stratum B), with its own SE.

    THE HEADLINE ESTIMATOR. The identified-minus-masked gap alone confounds two
    things: what the model remembers, and how much harder a stripped prompt is
    to read. The second is present in BOTH eras; the first can only be present
    in the era the model was trained on. Differencing removes it.

    Tested as a difference with its own SE (§18), never by comparing two
    separate significance claims.
    """
    import numpy as np

    def dates_map(ps: Sequence[dict]) -> dict[str, list[float]]:
        m: dict[str, list[float]] = {}
        for p in ps:
            m.setdefault(str(p["as_of"]), []).append(float(p[key]))
        return m

    ma, mb = dates_map(pairs_a), dates_map(pairs_b)
    if not ma or not mb:
        return {"n_a": len(pairs_a), "n_b": len(pairs_b),
                "reading": "one stratum is empty — no difference-in-differences"}
    da, db = sorted(ma), sorted(mb)
    obs = _mean([_mean(ma[t]) for t in da]) - _mean([_mean(mb[t]) for t in db])
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n_boot):
        ia = rng.integers(0, len(da), size=len(da))
        ib = rng.integers(0, len(db), size=len(db))
        draws.append(_mean([_mean(ma[da[i]]) for i in ia])
                     - _mean([_mean(mb[db[i]]) for i in ib]))
    se = float(np.std(draws, ddof=1))
    return {
        "n_a_pairs": len(pairs_a), "n_b_pairs": len(pairs_b),
        "n_a_dates": len(da), "n_b_dates": len(db),
        "gap_a": round(_mean([_mean(ma[t]) for t in da]), 6),
        "gap_b": round(_mean([_mean(mb[t]) for t in db]), 6),
        "difference_in_differences": round(obs, 6),
        "se_cluster_bootstrap": round(se, 6),
        "t_stat": (round(obs / se, 3) if se > 0 else None),
        "n_boot": n_boot,
        "reading": ("positive = the identified arm's advantage is LARGER in "
                    "stratum A than in stratum B; if A is the pre-cutoff era "
                    "and B the post-cutoff era, that is the leakage estimate"),
    }


def measure_did_mde(pairs_a: Sequence[dict], pairs_b: Sequence[dict], *,
                    key: str = "d",
                    grid: Sequence[float] = (0.002, 0.005, 0.01, 0.015, 0.02,
                                             0.03, 0.04, 0.05, 0.075, 0.10,
                                             0.15, 0.20),
                    n_sim: int = 300, n_boot: int = 400,
                    target_power: float = 0.80, seed: int = 20260812) -> dict:
    """Measured 80%-power MDE for the difference-in-differences (§19)."""
    import numpy as np

    def dates_map(ps: Sequence[dict]) -> dict[str, list[float]]:
        m: dict[str, list[float]] = {}
        for p in ps:
            m.setdefault(str(p["as_of"]), []).append(float(p[key]))
        return m

    ma, mb = dates_map(pairs_a), dates_map(pairs_b)
    da, db = sorted(ma), sorted(mb)
    if len(da) < 4 or len(db) < 4:
        return {"mde_at_80pct_power": None,
                "n_a_dates": len(da), "n_b_dates": len(db),
                "reading": "too few observation dates in one stratum for a "
                           "clustered MDE to mean anything"}
    # Null-centre BOTH strata so the planted delta is the world's true effect.
    ga = _mean([_mean(ma[t]) for t in da])
    gb = _mean([_mean(mb[t]) for t in db])
    ca = {t: [v - ga for v in ma[t]] for t in da}
    cb = {t: [v - gb for v in mb[t]] for t in db}
    rng = np.random.default_rng(seed + 11)

    rows = []
    for delta in grid:
        fires = 0
        for _ in range(n_sim):
            ia = rng.integers(0, len(da), size=len(da))
            ib = rng.integers(0, len(db), size=len(db))
            wa = [_mean(ca[da[i]]) + delta for i in ia]
            wb = [_mean(cb[db[i]]) for i in ib]
            obs = _mean(wa) - _mean(wb)
            inner = np.random.default_rng(int(rng.integers(1 << 31)))
            bs = []
            for _ in range(n_boot):
                ja = inner.integers(0, len(wa), size=len(wa))
                jb = inner.integers(0, len(wb), size=len(wb))
                bs.append(_mean([wa[j] for j in ja]) - _mean([wb[j] for j in jb]))
            se = float(np.std(bs, ddof=1))
            fires += bool(se > 0 and abs(obs / se) >= 1.96)
        rows.append({"planted": delta, "power": round(fires / n_sim, 3)})
        if rows[-1]["power"] >= target_power:
            break
    hit = [r for r in rows if r["power"] >= target_power]
    return {"mde_at_80pct_power": hit[0]["planted"] if hit else None,
            "grid": rows, "target_power": target_power,
            "n_a_dates": len(da), "n_b_dates": len(db),
            "note": "measured by planting a DiD of known size into date-"
                    "clustered resampled worlds and running the real test"}


# ── calibration ─────────────────────────────────────────────────────────────

def calibration_slice(rows: Sequence[dict]) -> dict:
    """Brier against this slice's OWN climatology, with n beside it.

    A Brier below climatology is the only version of "informative" this
    programme recognises, and a Brier on eleven records describes eleven
    records. Both facts are enforced by returning them together.
    """
    rs = [r for r in rows if r.get("outcome") is not None]
    if not rs:
        return {"n": 0, "reading": "nothing resolved in this slice"}
    n = len(rs)
    briers = [float(r["brier"]) for r in rs]
    base = sum(int(r["outcome"]) for r in rs) / n
    mean_p = sum(float(r["probability"]) for r in rs) / n
    clim = base * (1 - base)
    b = sum(briers) / n
    return {"n": n, "brier": round(b, 5), "climatology_brier": round(clim, 5),
            "brier_minus_climatology": round(b - clim, 5),
            "base_rate": round(base, 4), "mean_probability": round(mean_p, 4),
            "overconfidence": round(mean_p - base, 4),
            "beats_climatology": bool(b < clim)}


def reliability_curve(rows: Sequence[dict], *, bins: int = 5) -> list[dict]:
    """Stated probability against realised frequency, with n per bin."""
    rs = [r for r in rows if r.get("outcome") is not None]
    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        g = [r for r in rs
             if lo <= float(r["probability"]) < hi
             or (i == bins - 1 and float(r["probability"]) == 1.0)]
        if not g:
            out.append({"bin": f"[{lo:.1f},{hi:.1f})", "n": 0})
            continue
        out.append({"bin": f"[{lo:.1f},{hi:.1f})", "n": len(g),
                    "mean_probability": round(
                        sum(float(r["probability"]) for r in g) / len(g), 4),
                    "realised_frequency": round(
                        sum(int(r["outcome"]) for r in g) / len(g), 4)})
    return out


# ── CANON §20 ───────────────────────────────────────────────────────────────

def effective_distinct_ideas(preds: Sequence[dict]) -> dict:
    """Same rule as `llm_swarm.effective_distinct_ideas`, so the two compare.

    One idea is one (security, observable, probability-to-0.05) bucket. Asking
    one model N times is not n=N.
    """
    n = len(preds)
    if not n:
        return {"n_forecasts": 0, "effective_distinct_ideas": 0, "ratio": None}
    buckets = {(p["ticker"], p["observable"],
                round(float(p["probability"]) / 0.05)) for p in preds}
    return {"n_forecasts": n, "effective_distinct_ideas": len(buckets),
            "ratio": round(len(buckets) / n, 4),
            "distinct_tickers": len({p["ticker"] for p in preds}),
            "distinct_observables": len({p["observable"] for p in preds})}


def within_item_dispersion(rows: Sequence[dict]) -> dict:
    """How much two answers to the IDENTICAL question actually differ.

    The swarm could only measure this loosely, because its roles chose their own
    questions and a "disagreement" could be two people answering two questions.
    With a fixed slate the comparison is exact: same security, same date, same
    observable, same horizon, same threshold.
    """
    import statistics
    cells: dict[tuple, list[float]] = {}
    for r in rows:
        if r["status"] != "ok":
            continue
        for f in r["forecasts"]:
            cells.setdefault((r["ticker"], r["as_of"], f["key"]), []).append(
                float(f["probability"]))
    multi = [v for v in cells.values() if len(v) >= 2]
    if not multi:
        return {"n_cells_with_2plus": 0,
                "reading": "no question was answered twice in this condition"}
    sd = [statistics.pstdev(v) for v in multi]
    rng_ = [max(v) - min(v) for v in multi]
    one_bucket = sum(1 for v in multi if len({round(x / 0.05) for x in v}) == 1)
    return {"n_cells_with_2plus": len(multi),
            "mean_answers_per_cell": round(
                sum(len(v) for v in multi) / len(multi), 2),
            "mean_probability_stdev": round(sum(sd) / len(sd), 4),
            "mean_probability_range": round(sum(rng_) / len(rng_), 4),
            "share_of_cells_in_one_0_05_bucket": round(
                one_bucket / len(multi), 4)}
