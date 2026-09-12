"""LANE A — the agency: an IPS, three options, a daily review, protect-first.

WHY THIS FILE EXISTS
====================
Roadmap §7: every surveyed product does goal intake OR daily review, and none
does both. Robo-advisors fixed diversification and rebalancing and **do not
pick stocks, read news, or make hold/sell/buy calls**; the multi-agent repos
make calls and have no audited record. Lane A is the join, and the spec is
`docs/research_notes/2026-09-12/spec_agency_intake.md`.

THE SPLIT THAT THE WHOLE LANE TURNS ON
======================================
**The LLM drafts the prose; the engine fills every number.** Not a convention —
a check: `draft_prose` runs the drafted sentences through `unexplained_numbers`
against `numeric_fields`, and prose carrying a number the engine did not
compute is DISCARDED in favour of the template. A sentence that invents a
number reads exactly like a sentence that reports one.

WHAT IS DECLARED AND WHAT IS DERIVED
====================================
The four personalities are DECLARED PREFERENCES (`OPTIMUS_OBJECTIVE.md` §0.9),
never inferred from the data a book will be graded on. The questionnaire
measures ability and willingness and the composite is the LOWER of the two
(CFA IPS convention, spec §1.3) — a client who says "I can take a lot of risk"
with a three-month emergency fund is not high-ability, and the IPS may not let
the statement override the measurement. What the engine may NOT do is silently
down-shift a personality the human declared: §1.5's liquidity conflict is a
REFUSAL naming which of the two inputs must change.

WHAT THIS MODULE NEVER DOES
===========================
No order path, no broker, no sizing by a language model. `intake()` and
`propose()` compute; `hold` is a human action on the control plane, and it is
the only route in this repository that mints `origin="human_text"`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)


class AgencyError(ValueError):
    """The intake asks for something the IPS cannot express, or the inputs
    contradict each other and guessing which one was meant would decide the
    client's risk for them."""


SCHEMA_VERSION = "1.0.0"
QUESTIONNAIRE_VERSION = "AEGIS-RQ-1"
LICENCE = "PRODUCT_EXPERIMENT"

#: The risk ladder, in order. Index arithmetic on this tuple is what §2's
#: "the chosen personality plus its two neighbours" means.
PERSONALITIES: tuple[str, ...] = ("preservation", "balanced", "aggressive",
                                  "extreme_growth")

#: §5.2, verbatim, appended to every agency payload — not once per session.
#: `research_agency.md` §2 and roadmap §7: SEC IM Guidance 2017-02 governs a
#: tool that advises OTHERS for compensation; a personal tool one person runs
#: on their own account sits outside that definition, and the boundary is a
#: question for counsel before any multi-user distribution, not for this repo.
LIMITS_SENTENCE = (
    "This is a paper-trading tool for personal use; it is not investment "
    "advice, and nothing here should be read as an offer to manage money for "
    "anyone but the person running it. A tool that advises OTHERS for "
    "compensation is a different, regulated activity (SEC Investment Advisers "
    "Act; see `research_agency.md` section 2) — before this becomes a "
    "multi-user product, that boundary is a question for counsel, not for "
    "this repo.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha16(obj: Any) -> str:
    """The ONE canonical-JSON hash, identical to `contract.py::_sha` and
    `belief_state.py::_hash` and truncated to the 16 hex both use."""
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str,
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ===========================================================================
# 1.4 — PERSONALITY TO NUMBERS, with every number's source on the row
# ===========================================================================
#
# A number in this table without a source is a number somebody will later have
# to reverse-engineer from a diff. `sources` is carried onto the IPS itself
# (`personality_numbers.sources`) so the receipt a page shows and the table the
# engine reads cannot drift apart.


@dataclass(frozen=True)
class PersonalityRow:
    """One row of spec §1.4. The worst case is NEVER stored — it is computed
    by `contract.loss_budget_worst_case`, which is the one place in this repo
    that prints the gross line beside the stop line (session protocol rule 4)."""

    personality: str
    k: int
    max_single_name: float
    gross_cap: float
    stop_loss: float
    drawdown_budget: float
    rebalance_frequency: str
    cash_floor: float
    sources: Mapping[str, str]
    extrapolated: bool = False
    note: str = ""

    def as_row(self) -> dict:
        return {"personality": self.personality, "k": self.k,
                "max_single_name": self.max_single_name,
                "gross_cap": self.gross_cap, "stop_loss": self.stop_loss,
                "drawdown_budget": self.drawdown_budget,
                "rebalance_frequency": self.rebalance_frequency,
                "cash_floor": self.cash_floor,
                "extrapolated": self.extrapolated,
                "sources": dict(self.sources), "note": self.note}


_YAML = "backend/data/paper_portfolios.yaml (the three personality-keyed lanes)"
_CONSTRUCTION = ("backend/strategy/contract.py::Construction defaults "
                 "(k=12, max_single_name=0.20)")
_LADDER = ("stepped along the ladder paper_portfolios.yaml already shows "
           "(max_single_name 0.03/0.05/0.08, conservative to aggressive); the "
           "worst case is RECOMPUTED from k and the stop, never hand-edited")
_EXTRAP = ("EXTRAPOLATED — no repo precedent for extreme_growth. Same step "
           "size the other three rows show. Owed a receipt once the first "
           "extreme_growth book runs.")

TABLE: dict[str, PersonalityRow] = {
    "preservation": PersonalityRow(
        personality="preservation", k=20, max_single_name=0.05, gross_cap=1.00,
        stop_loss=-0.08, drawdown_budget=-0.10, rebalance_frequency="monthly",
        cash_floor=0.10,
        sources={"k": _LADDER, "max_single_name": _LADDER,
                 "gross_cap": "1.00 — no tier below extreme_growth may lever",
                 "stop_loss": _LADDER,
                 "drawdown_budget": "spec section 1.4, the most conservative rung",
                 "rebalance_frequency":
                     f"{_YAML}: conservative.rebalance_frequency = monthly",
                 "cash_floor": "spec section 1.4 cash floor minimum"}),
    "balanced": PersonalityRow(
        personality="balanced", k=15, max_single_name=0.10, gross_cap=1.00,
        stop_loss=-0.10, drawdown_budget=-0.20, rebalance_frequency="monthly",
        cash_floor=0.05,
        sources={"k": _LADDER, "max_single_name": _LADDER,
                 "gross_cap": "1.00 — no tier below extreme_growth may lever",
                 "stop_loss": _LADDER,
                 "drawdown_budget": "spec section 1.4, midpoint of the ladder",
                 "rebalance_frequency":
                     f"{_YAML}: balanced.rebalance_frequency = monthly",
                 "cash_floor": "spec section 1.4 cash floor minimum"}),
    "aggressive": PersonalityRow(
        personality="aggressive", k=12, max_single_name=0.20, gross_cap=1.00,
        stop_loss=-0.12, drawdown_budget=-0.35, rebalance_frequency="weekly",
        cash_floor=0.02,
        note=("THE SPEC'S ONE ARITHMETIC SLIP, resolved in favour of the "
              "INPUTS. §1.4 prints this row as '12 x 8.33% x 12% = 10.0%' and "
              "its test T2 asserts -$10,000 on $100,000 — but 1.00x gross at a "
              "12% stop is 12.0%, not 10.0%, and the same table's other two "
              "rows are arithmetically exact. The spec's own note says the "
              "worst case is RECOMPUTED and never hand-edited, so the declared "
              "stop ladder (-8/-10/-12/-15) stands and this row prints 12.0%. "
              "Flipping the stop to -0.10 instead would reproduce the spec's "
              "printed number and collapse the ladder's third rung onto its "
              "second; that is a one-constant change if the reviewer prefers "
              "it, and it is a choice about the ladder, not about arithmetic."),
        sources={"k": _CONSTRUCTION, "max_single_name": _CONSTRUCTION,
                 "gross_cap": "1.00 — no tier below extreme_growth may lever",
                 "stop_loss": _LADDER,
                 "drawdown_budget": ("backend/strategy/contract.py::Objective, "
                                     "QUOTED: '-0.35, aggressive personality'"),
                 "rebalance_frequency":
                     f"{_YAML}: aggressive.rebalance_frequency = weekly",
                 "cash_floor": "spec section 1.4 cash floor minimum"}),
    "extreme_growth": PersonalityRow(
        personality="extreme_growth", k=8, max_single_name=0.30, gross_cap=1.50,
        stop_loss=-0.15, drawdown_budget=-0.50, rebalance_frequency="daily",
        cash_floor=0.00, extrapolated=True,
        note=("the ONLY tier permitted gross_cap > 1.00. Session protocol rule "
              "4: the gross is printed beside the stop on every worst case for "
              "this tier, and never the stop alone — a wider stop on uncapped "
              "gross is a BIGGER loss, which is how -9% became -24% on 28 Aug."),
        sources={k: _EXTRAP for k in ("k", "max_single_name", "gross_cap",
                                      "stop_loss", "drawdown_budget",
                                      "rebalance_frequency", "cash_floor")}),
}

#: §2.2, the three hold-rule families, keyed by personality.
HOLD_FAMILY: dict[str, dict] = {
    "preservation": {"family": "protect_first_ladder", "horizon_periods": 21,
                     "roi_ladder": {0: 0.15, 10: 0.08, 20: 0.03},
                     "min_hold_periods": 5},
    "balanced": {"family": "core_ladder", "horizon_periods": 21,
                 "roi_ladder": {0: 0.20, 10: 0.10, 20: 0.04},
                 "min_hold_periods": 3},
    "aggressive": {"family": "momentum_ladder", "horizon_periods": 21,
                   "roi_ladder": {0: 0.25, 5: 0.12}, "min_hold_periods": 0},
    "extreme_growth": {"family": "momentum_ladder", "horizon_periods": 5,
                       "roi_ladder": {0: 0.15}, "min_hold_periods": 0},
}


# ===========================================================================
# 1.3 — THE RISK QUESTIONNAIRE
# ===========================================================================


@dataclass(frozen=True)
class Question:
    qid: str
    text: str
    dimension: str          # "ability" | "willingness"
    scale: str              # what 0 and 4 mean
    source: str


QUESTIONS: tuple[Question, ...] = (
    Question("Q1", "Years until you need this money.", "ability",
             "0 = under 1 year … 4 = 10 years or more", "CFA IPS time horizon"),
    Question("Q2", "What fraction might you need within 12 months?", "ability",
             "0 = over 50% … 4 = none of it", "CFA IPS liquidity constraint"),
    Question("Q3", "How stable is your income over the next 2 years?", "ability",
             "0 = very unstable … 4 = very stable",
             "SCF-style income-stability proxy"),
    Question("Q4", "What fraction of your total net worth is this capital?",
             "ability", "0 = over 75% … 4 = under 10%",
             "capacity-for-loss (CFA IPS ability)"),
    Question("Q5", "If this dropped 20% in a month, what would you do?",
             "willingness", "0 = sell everything … 4 = buy more",
             "Grable & Lytton 1999, Financial Services Review 8(3) 163-181 — "
             "hypothetical-loss item"),
    Question("Q6", "Which statement best matches the risk you are willing to "
                   "take? (not willing to take any financial risk / average "
                   "risk for average returns / above-average risk for "
                   "above-average returns / substantial risk for substantial "
                   "returns)", "willingness",
             "0 = not willing … 4 = substantial risk (the SCF's four "
             "categories on a 0-4 scale, with room for a neutral tie-break)",
             "Federal Reserve Board Survey of Consumer Finances "
             "risk-tolerance item"),
    Question("Q7", "Investment experience (years actively investing).",
             "willingness", "0 = none … 4 = 10 years or more",
             "Grable & Lytton 1999 — experience item"),
    Question("Q8", "\"I am more concerned about losing money than about "
                   "missing gains\" (reverse-scored).", "willingness",
             "0 = strongly agree … 4 = strongly disagree",
             "Grable & Lytton 1999 — loss-aversion item"),
)

N_QUESTIONS = len(QUESTIONS)

#: §1.3. Half-open on the left, closed at the top: [0,1) [1,2) [2,3) [3,4].
BANDS: tuple[tuple[float, float, str], ...] = (
    (0.0, 1.0, "preservation"),
    (1.0, 2.0, "balanced"),
    (2.0, 3.0, "aggressive"),
    (3.0, 4.0, "extreme_growth"),
)


def score_questionnaire(answers: Sequence[int] | None) -> dict:
    """ability = mean(Q1..Q4), willingness = mean(Q5..Q8), composite = min.

    The MIN is the CFA convention and it is the reason this is not one mean of
    eight items: stated willingness never raises measured ability.
    """
    if answers is None:
        raise AgencyError(
            f"the risk questionnaire ({QUESTIONNAIRE_VERSION}) has "
            f"{N_QUESTIONS} items and none were supplied. An IPS whose risk "
            f"profile was not measured is an IPS with a risk profile somebody "
            f"assumed.")
    vals = list(answers)
    if len(vals) != N_QUESTIONS:
        raise AgencyError(f"{QUESTIONNAIRE_VERSION} has exactly {N_QUESTIONS} "
                          f"items; got {len(vals)}")
    for i, v in enumerate(vals):
        if isinstance(v, bool) or not isinstance(v, int):
            raise AgencyError(f"answer {QUESTIONS[i].qid} must be an integer "
                              f"0-4, got {v!r}")
        if not 0 <= v <= 4:
            raise AgencyError(f"answer {QUESTIONS[i].qid} = {v} is outside 0-4")
    ability = sum(vals[:4]) / 4.0
    willingness = sum(vals[4:]) / 4.0
    composite = min(ability, willingness)
    return {"ability_score": round(ability, 4),
            "willingness_score": round(willingness, 4),
            "composite_score": round(composite, 4),
            "questionnaire_version": QUESTIONNAIRE_VERSION,
            "answers": vals,
            "suggested_personality": personality_for(composite),
            "bounded_by": ("ability" if ability <= willingness else "willingness"),
            "convention": ("composite = min(ability, willingness) — CFA IPS: "
                           "stated willingness never overrides measured ability")}


def personality_for(composite: float) -> str:
    for lo, hi, name in BANDS:
        if lo <= composite < hi:
            return name
    return "extreme_growth" if composite >= 4.0 else "preservation"


# ===========================================================================
# 1.6 — THE CONSTRAINT VOCABULARY
# ===========================================================================

CONSTRAINT_RE = re.compile(
    r"^(NO_SINGLE_NAME:[A-Z.]{1,10}|NO_SECTOR:[A-Z_]+|"
    r"ESG_EXCLUDE:[a-z_]+|TAX_LOT:DEFERRED)$")

#: The ESG categories that map to a reviewed exclusion list. An unknown
#: category is a REFUSAL, not a constraint that quietly excludes nothing.
#: `gambling` really does exclude DKNG, which is a live holding in
#: `book_lanes.yaml` — the mapping is a reviewed file, not a stub.
ESG_CATEGORIES: dict[str, tuple[str, ...]] = {
    "fossil_fuels": ("APA", "CVX", "COP", "DVN", "EOG", "FANG", "HAL", "HES",
                     "MPC", "MRO", "OXY", "PSX", "SLB", "VLO", "XOM"),
    "tobacco": ("BTI", "MO", "PM", "TPB"),
    "weapons": ("GD", "HII", "LHX", "LMT", "NOC", "RGR", "RTX", "SWBI", "TXT"),
    "gambling": ("BYD", "CZR", "DKNG", "FLUT", "LVS", "MGM", "PENN", "RSI",
                 "WYNN"),
    "alcohol": ("BF.B", "DEO", "SAM", "STZ", "TAP"),
}

TAX_LOT_ECHO = ("tax-loss harvesting is not implemented: TAX_LOT:DEFERRED is "
                "an acknowledgement, and every lot-level decision echoes this "
                "sentence rather than implying a check that did not run")


def parse_constraints(constraints: Sequence[str] | None) -> dict:
    """Validate against the vocabulary and resolve to exclusions.

    An unknown token is a hard refusal (422 at the route), never a silently
    dropped constraint — the same reasoning as `Strategy`'s unknown-field
    refusal: a constraint accepted and ignored is worse than one refused,
    because the client believes it is in force.
    """
    tokens = [str(c).strip() for c in (constraints or []) if str(c).strip()]
    bad = [t for t in tokens if not CONSTRAINT_RE.match(t)]
    if bad:
        raise AgencyError(
            f"constraint token(s) {bad} are not in the vocabulary. Declared: "
            f"NO_SINGLE_NAME:<TICKER>, NO_SECTOR:<SECTOR>, "
            f"ESG_EXCLUDE:<{'|'.join(sorted(ESG_CATEGORIES))}>, "
            f"TAX_LOT:DEFERRED. A constraint accepted and ignored is worse "
            f"than one refused: the client believes it is in force.")
    tickers: set[str] = set()
    sectors: set[str] = set()
    echoes: list[str] = []
    for t in tokens:
        head, _, arg = t.partition(":")
        if head == "NO_SINGLE_NAME":
            tickers.add(arg)
        elif head == "NO_SECTOR":
            sectors.add(arg)
        elif head == "ESG_EXCLUDE":
            if arg not in ESG_CATEGORIES:
                raise AgencyError(
                    f"ESG category {arg!r} has no reviewed exclusion list. "
                    f"Declared: {sorted(ESG_CATEGORIES)}. A category that maps "
                    f"to nothing excludes nothing while reading as a policy.")
            tickers.update(ESG_CATEGORIES[arg])
        else:                                   # TAX_LOT:DEFERRED
            echoes.append(TAX_LOT_ECHO)
    return {"tokens": tokens, "excluded_tickers": sorted(tickers),
            "excluded_sectors": sorted(sectors), "echoes": echoes}


# ===========================================================================
# 1.1 — THE JSON SCHEMA, and a hand validator for the venvs without jsonschema
# ===========================================================================

IPS_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://aegis.local/schemas/ips.schema.json",
    "title": "InvestmentPolicyStatement",
    "type": "object",
    "additionalProperties": False,
    "required": ["ips_id", "ips_hash", "created_utc", "schema_version",
                 "licence", "client_facts", "objectives_and_constraints",
                 "risk_profile", "eligible_universe", "review_cadence",
                 "personality", "amends_ips_hash"],
    "properties": {
        "ips_id": {"type": "string"},
        "ips_hash": {"type": "string", "pattern": "^[0-9a-f]{16}$"},
        "created_utc": {"type": "string"},
        "schema_version": {"const": SCHEMA_VERSION},
        "licence": {"const": LICENCE},
        "amends_ips_hash": {"type": ["string", "null"],
                            "pattern": "^[0-9a-f]{16}$"},
        "client_facts": {
            "type": "object", "additionalProperties": False,
            "required": ["capital_usd", "horizon_months", "intake_answers_hash"],
            "properties": {
                "capital_usd": {"type": "number", "exclusiveMinimum": 0},
                "horizon_months": {"type": "integer", "minimum": 1},
                "intake_answers_hash": {"type": "string",
                                        "pattern": "^[0-9a-f]{16}$"}}},
        "objectives_and_constraints": {
            "type": "object", "additionalProperties": False,
            "required": ["personality", "liquidity_need", "cash_floor_pct",
                         "constraints"],
            "properties": {
                "personality": {"enum": list(PERSONALITIES)},
                "liquidity_need": {"type": "number", "minimum": 0, "maximum": 1},
                "cash_floor_pct": {"type": "number", "minimum": 0, "maximum": 1},
                "constraints": {"type": "array",
                                "items": {"type": "string",
                                          "pattern": CONSTRAINT_RE.pattern}}}},
        "risk_profile": {
            "type": "object", "additionalProperties": False,
            "required": ["ability_score", "willingness_score",
                         "composite_score", "questionnaire_version", "answers"],
            "properties": {
                "ability_score": {"type": "number", "minimum": 0, "maximum": 4},
                "willingness_score": {"type": "number", "minimum": 0,
                                      "maximum": 4},
                "composite_score": {"type": "number", "minimum": 0,
                                    "maximum": 4},
                "questionnaire_version": {"const": QUESTIONNAIRE_VERSION},
                "answers": {"type": "array", "minItems": N_QUESTIONS,
                            "maxItems": N_QUESTIONS,
                            "items": {"type": "integer", "minimum": 0,
                                      "maximum": 4}}}},
        "eligible_universe": {
            "type": "object", "additionalProperties": False,
            "required": ["source", "floor_dollar_vol_usd", "excluded_tickers",
                         "excluded_sectors"],
            "properties": {
                "source": {"type": "string"},
                "floor_dollar_vol_usd": {"type": "number", "minimum": 0},
                "excluded_tickers": {"type": "array",
                                     "items": {"type": "string"}},
                "excluded_sectors": {"type": "array",
                                     "items": {"type": "string"}}}},
        "review_cadence": {
            "type": "object", "additionalProperties": False,
            "required": ["daily_review", "rebalance_frequency"],
            "properties": {
                "daily_review": {"const": True},
                "rebalance_frequency": {"enum": ["daily", "weekly", "monthly",
                                                 "quarterly"]}}},
        "personality": {"enum": list(PERSONALITIES)},
    },
}


def _hand_validate(doc: Any, schema: dict, path: str = "$") -> list[str]:
    """Enough draft-07 for THIS schema, and no more.

    Written rather than skipped because `jsonschema` is not in every venv this
    runs in, and "validated where the library happened to be installed" is a
    validation nobody can rely on. The subset is: type, const, enum, required,
    additionalProperties, properties, items, minItems/maxItems, minimum,
    maximum, exclusiveMinimum, pattern.
    """
    errs: list[str] = []
    t = schema.get("type")
    types = [t] if isinstance(t, str) else list(t or [])
    if types:
        ok = False
        for tt in types:
            if tt == "null":
                ok = ok or doc is None
            elif tt == "string":
                ok = ok or isinstance(doc, str)
            elif tt == "integer":
                ok = ok or (isinstance(doc, int) and not isinstance(doc, bool))
            elif tt == "number":
                ok = ok or (isinstance(doc, (int, float))
                            and not isinstance(doc, bool))
            elif tt == "boolean":
                ok = ok or isinstance(doc, bool)
            elif tt == "array":
                ok = ok or isinstance(doc, list)
            elif tt == "object":
                ok = ok or isinstance(doc, dict)
        if not ok:
            return [f"{path}: expected type {types}, got {type(doc).__name__}"]
    if "const" in schema and doc != schema["const"]:
        errs.append(f"{path}: must be {schema['const']!r}, got {doc!r}")
    if "enum" in schema and doc not in schema["enum"]:
        errs.append(f"{path}: {doc!r} is not one of {schema['enum']}")
    if isinstance(doc, str) and schema.get("pattern"):
        if not re.match(schema["pattern"], doc):
            errs.append(f"{path}: {doc!r} does not match {schema['pattern']}")
    if isinstance(doc, (int, float)) and not isinstance(doc, bool):
        if "minimum" in schema and doc < schema["minimum"]:
            errs.append(f"{path}: {doc} < minimum {schema['minimum']}")
        if "maximum" in schema and doc > schema["maximum"]:
            errs.append(f"{path}: {doc} > maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and doc <= schema["exclusiveMinimum"]:
            errs.append(f"{path}: {doc} <= exclusiveMinimum "
                        f"{schema['exclusiveMinimum']}")
    if isinstance(doc, list):
        if "minItems" in schema and len(doc) < schema["minItems"]:
            errs.append(f"{path}: {len(doc)} items < minItems {schema['minItems']}")
        if "maxItems" in schema and len(doc) > schema["maxItems"]:
            errs.append(f"{path}: {len(doc)} items > maxItems {schema['maxItems']}")
        if schema.get("items"):
            for i, item in enumerate(doc):
                errs += _hand_validate(item, schema["items"], f"{path}[{i}]")
    if isinstance(doc, dict):
        props = schema.get("properties") or {}
        for req in schema.get("required") or []:
            if req not in doc:
                errs.append(f"{path}: required property {req!r} is missing")
        if schema.get("additionalProperties") is False:
            extra = sorted(set(doc) - set(props))
            if extra:
                errs.append(f"{path}: additional properties {extra} are not "
                            f"allowed")
        for key, sub in props.items():
            if key in doc:
                errs += _hand_validate(doc[key], sub, f"{path}.{key}")
    return errs


def validate_document(doc: dict) -> dict:
    """Validate against `IPS_SCHEMA`. Returns the validator that ran.

    `jsonschema` when it exists, the hand validator otherwise, and the payload
    SAYS WHICH — "validated" by two different validators is two different
    claims, and a reader has to be able to tell them apart.
    """
    try:
        import jsonschema                                        # noqa: PLC0415
    except ImportError:
        errs = _hand_validate(doc, IPS_SCHEMA)
        if errs:
            raise AgencyError("the IPS does not satisfy its own schema: "
                              + "; ".join(errs[:6])) from None
        return {"validator": "hand", "schema_id": IPS_SCHEMA["$id"],
                "note": ("jsonschema is not installed in this venv; the hand "
                         "validator covers exactly the draft-07 subset this "
                         "schema uses")}
    try:
        jsonschema.validate(doc, IPS_SCHEMA)
    except jsonschema.ValidationError as exc:                    # pragma: no cover
        raise AgencyError(f"the IPS does not satisfy its own schema: "
                          f"{exc.message} at {list(exc.absolute_path)}") from exc
    return {"validator": f"jsonschema {jsonschema.__version__}",
            "schema_id": IPS_SCHEMA["$id"]}


# ===========================================================================
# 1.7 — THE HASH
# ===========================================================================

#: Excluded from the hash: the field itself (a hash cannot include itself) and
#: the timestamp (an identical IPS re-submitted a second later is the SAME
#: IPS). The prose is not in the document at all — see `IPS.prose_md`.
HASH_EXCLUDES: tuple[str, ...] = ("ips_hash", "created_utc")


def ips_hash(document: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical JSON, 16 hex. Stable across key order.

    `sort_keys=True` is the whole property, and test T1 in the spec's table
    exists to catch the refactor that swaps in a hash call without it.
    """
    payload = {k: v for k, v in document.items() if k not in HASH_EXCLUDES}
    return _sha16(payload)


# ===========================================================================
# THE OBJECT
# ===========================================================================


@dataclass(frozen=True)
class IPS:
    """A validated IPS document, its prose, and where the prose came from."""

    document: dict
    prose_md: str = ""
    prose_source: str = "template"
    validator: str = ""
    prose_rejected: str = ""
    #: The named numbers the engine computed. This IS the set the prose is
    #: checked against (`unexplained_numbers`), so the check and the display
    #: read one object.
    numbers: Mapping[str, float] = field(default_factory=dict)
    echoes: tuple[str, ...] = ()

    @property
    def ips_id(self) -> str:
        return str(self.document["ips_id"])

    @property
    def ips_hash(self) -> str:
        return str(self.document["ips_hash"])

    @property
    def personality(self) -> str:
        return str(self.document["personality"])

    @property
    def capital_usd(self) -> float:
        return float(self.document["client_facts"]["capital_usd"])

    @property
    def horizon_months(self) -> int:
        return int(self.document["client_facts"]["horizon_months"])

    @property
    def cash_floor_pct(self) -> float:
        return float(self.document["objectives_and_constraints"]["cash_floor_pct"])

    @property
    def row(self) -> PersonalityRow:
        return TABLE[self.personality]

    def as_payload(self) -> dict:
        return {"ips": self.document, "ips_hash": self.ips_hash,
                "ips_prose_md": self.prose_md,
                "prose_source": self.prose_source,
                "prose_rejected": self.prose_rejected or None,
                "validated_by": self.validator,
                "numeric_fields": dict(self.numbers),
                "personality_numbers": self.row.as_row(),
                "echoes": list(self.echoes),
                "limits": LIMITS_SENTENCE}


# ===========================================================================
# 1.5 — THE CASH FLOOR, AND THE ONE REFUSAL
# ===========================================================================

#: The most of a book that may sit in cash before the personality it declares
#: has stopped being that personality. A preservation book can hold 60% cash
#: and still be a preservation book; an aggressive one cannot.
MAX_CASH_FOR: dict[str, float] = {"preservation": 0.60, "balanced": 0.40,
                                  "aggressive": 0.25, "extreme_growth": 0.10}


def cash_floor_for(personality: str, liquidity_need: float) -> float:
    """`max(liquidity_need, PERSONALITY_CASH_FLOOR)` — §1.5, with the refusal.

    The refusal names WHICH input must change. It does not down-shift the
    personality, because that would be the engine overriding a declared
    preference (`OPTIMUS_OBJECTIVE.md` §0.9).
    """
    if personality not in TABLE:
        raise AgencyError(f"personality {personality!r} is not one of "
                          f"{list(PERSONALITIES)}")
    if not 0.0 <= float(liquidity_need) <= 1.0:
        raise AgencyError(f"liquidity_need {liquidity_need} is a fraction of "
                          f"capital and must be in [0, 1]")
    floor = max(float(liquidity_need), TABLE[personality].cash_floor)
    ceiling = MAX_CASH_FOR[personality]
    if floor > ceiling:
        raise AgencyError(
            f"a {personality} book cannot hold {floor:.0%} in cash: the "
            f"declared liquidity need ({float(liquidity_need):.0%}) leaves "
            f"less than the {1 - ceiling:.0%} invested fraction this "
            f"personality means. CHANGE ONE: either the personality (a more "
            f"conservative tier tolerates more cash) or the liquidity need. "
            f"The engine does not pick for you — a personality is a declared "
            f"preference, not an inference.")
    return round(floor, 4)


# ===========================================================================
# 1.8 — NEW IPS vs AMENDMENT
# ===========================================================================

CAPITAL_AMENDMENT_TOLERANCE = 0.20


def amendment_kind(prior: Mapping[str, Any] | None, *, capital_usd: float,
                   horizon_months: int, personality: str,
                   liquidity_need: float,
                   liquidity_conflict: bool = False) -> dict:
    """`new_ips` or `amendment`, per the table in spec §1.8.

    A NEW IPS starts a new generation of books; an amendment keeps `ips_id` and
    points `amends_ips_hash` at the prior hash. Neither retroactively changes
    the `ips_hash` a book was created under — "a mutation is a new object" is
    the same discipline as `Strategy.with_`.
    """
    if not prior:
        return {"kind": "new_ips", "reason": "no prior IPS in this lineage",
                "amends_ips_hash": None, "ips_id": None}
    facts = prior.get("client_facts") or {}
    oc = prior.get("objectives_and_constraints") or {}
    prior_capital = float(facts.get("capital_usd") or 0.0)
    reasons: list[str] = []
    if int(facts.get("horizon_months") or 0) != int(horizon_months):
        reasons.append("horizon_months changed")
    if str(prior.get("personality")) != str(personality):
        reasons.append("personality changed — a different declared preference "
                       "is not a tweak")
    if prior_capital > 0:
        move = abs(float(capital_usd) - prior_capital) / prior_capital
        if move > CAPITAL_AMENDMENT_TOLERANCE:
            reasons.append(f"capital moved {move:.0%}, more than "
                           f"{CAPITAL_AMENDMENT_TOLERANCE:.0%}")
    if liquidity_conflict:
        reasons.append("the new liquidity need conflicts with the personality band")
    if reasons:
        return {"kind": "new_ips", "reason": "; ".join(reasons),
                "amends_ips_hash": None, "ips_id": None}
    changed = []
    if abs(float(oc.get("liquidity_need") or 0.0) - float(liquidity_need)) > 1e-9:
        changed.append("liquidity_need")
    return {"kind": "amendment",
            "reason": ("; ".join(changed) or "constraints or nothing material"),
            "amends_ips_hash": str(prior.get("ips_hash")),
            "ips_id": str(prior.get("ips_id"))}


# ===========================================================================
# A1 — THE INTAKE
# ===========================================================================

DEFAULT_UNIVERSE_SOURCE = "ips_eligible_universe"
#: The execution floor every agency book inherits. Declared here rather than
#: per book: `[[apply-the-execution-floor-before-believing-the-book]]` — it
#: existed for months as `TRADABLE_DOLLAR_VOL` and books were graded without it.
DEFAULT_FLOOR_DOLLAR_VOL = 5_000_000.0


def numeric_fields(document: Mapping[str, Any], row: PersonalityRow) -> dict:
    """Every number the engine computed for this IPS, named.

    The prose check reads THIS, so a number the model writes that is not in
    here is a number the engine did not compute. Both the personality row and
    the document contribute, because the prose legitimately talks about both.
    """
    facts = document["client_facts"]
    oc = document["objectives_and_constraints"]
    rp = document["risk_profile"]
    eu = document["eligible_universe"]
    out = {
        "capital_usd": float(facts["capital_usd"]),
        "horizon_months": float(facts["horizon_months"]),
        "horizon_years": round(float(facts["horizon_months"]) / 12.0, 4),
        "liquidity_need": float(oc["liquidity_need"]),
        "cash_floor_pct": float(oc["cash_floor_pct"]),
        "invested_fraction": round(1.0 - float(oc["cash_floor_pct"]), 4),
        "ability_score": float(rp["ability_score"]),
        "willingness_score": float(rp["willingness_score"]),
        "composite_score": float(rp["composite_score"]),
        "n_questions": float(len(rp["answers"])),
        "n_excluded_tickers": float(len(eu["excluded_tickers"])),
        "n_excluded_sectors": float(len(eu["excluded_sectors"])),
        "floor_dollar_vol_usd": float(eu["floor_dollar_vol_usd"]),
        "k": float(row.k),
        "max_single_name": row.max_single_name,
        "gross_cap": row.gross_cap,
        "stop_loss": row.stop_loss,
        "drawdown_budget": row.drawdown_budget,
        "personality_cash_floor": row.cash_floor,
    }
    # The worst case IS a number the prose may quote. The arithmetic below is
    # the same identity `contract.loss_budget_worst_case` computes
    # (gross x stop x invested equity) and `propose()` calls that function
    # directly; this copy exists so the prose check has the number BEFORE a
    # `Strategy` exists, and the test pins the two against each other.
    out["worst_case_pct_of_equity"] = round(
        abs(row.gross_cap * row.stop_loss) * (1.0 - float(oc["cash_floor_pct"])), 6)
    out["worst_case_usd"] = round(
        -out["worst_case_pct_of_equity"] * float(facts["capital_usd"]), 2)
    return out


def intake(*, capital: float, horizon_months: int, personality: str | None,
           constraints: Sequence[str] | None = None,
           liquidity_need: float = 0.0,
           answers: Sequence[int] | None = None,
           prior_ips: Mapping[str, Any] | None = None,
           ips_id: str | None = None,
           floor_dollar_vol_usd: float = DEFAULT_FLOOR_DOLLAR_VOL,
           universe_source: str = DEFAULT_UNIVERSE_SOURCE,
           draft: bool = True,
           created_utc: str | None = None) -> IPS:
    """`{capital, horizon_months, personality, constraints[], liquidity_need}`
    plus the eight answers → a validated, hashed IPS (A1).

    `personality=None` takes the questionnaire's own band. A personality the
    human declares ABOVE the band is accepted and recorded as an override —
    declared preferences are the point (`OPTIMUS_OBJECTIVE.md` §0.9) — but the
    override is on the row, never silent.
    """
    if isinstance(capital, bool) or not isinstance(capital, (int, float)):
        raise AgencyError(f"capital must be a number, got {capital!r}")
    if float(capital) <= 0:
        raise AgencyError("capital must be greater than zero: an IPS over no "
                          "money has no worst case to state")
    if isinstance(horizon_months, bool) or not isinstance(horizon_months, int):
        raise AgencyError(f"horizon_months must be a whole number of months, "
                          f"got {horizon_months!r}")
    if horizon_months < 1:
        raise AgencyError("horizon_months must be at least 1")

    scored = score_questionnaire(answers)
    band = scored["suggested_personality"]
    chosen = str(personality or band)
    if chosen not in TABLE:
        raise AgencyError(f"personality {chosen!r} is not one of "
                          f"{list(PERSONALITIES)}")
    override = None
    if chosen != band:
        direction = ("above" if PERSONALITIES.index(chosen) > PERSONALITIES.index(band)
                     else "below")
        override = (f"declared {chosen}, {direction} the questionnaire's own "
                    f"band ({band}) at composite {scored['composite_score']}. "
                    f"A personality is a DECLARED PREFERENCE; the band is the "
                    f"engine's read of the answers, and the two are recorded "
                    f"separately so neither is mistaken for the other.")

    parsed = parse_constraints(constraints)
    try:
        floor_pct = cash_floor_for(chosen, float(liquidity_need))
    except AgencyError:
        # The conflict decides the amendment question too (§1.8), so it is
        # recorded on the way out rather than swallowed.
        logger.info("intake refused: %s / liquidity_need=%s cannot be met",
                    chosen, liquidity_need)
        raise
    kind = amendment_kind(prior_ips, capital_usd=float(capital),
                          horizon_months=int(horizon_months),
                          personality=chosen,
                          liquidity_need=float(liquidity_need))

    created = created_utc or _now()
    answers_hash = _sha16({"version": QUESTIONNAIRE_VERSION,
                           "answers": list(scored["answers"])})
    doc: dict = {
        "ips_id": (ips_id or kind.get("ips_id")
                   or f"ips-{_sha16([capital, horizon_months, chosen, created])}"),
        "ips_hash": "0" * 16,                       # replaced below
        "created_utc": created,
        "schema_version": SCHEMA_VERSION,
        "licence": LICENCE,
        "amends_ips_hash": kind.get("amends_ips_hash"),
        "client_facts": {
            "capital_usd": float(capital),
            "horizon_months": int(horizon_months),
            "intake_answers_hash": answers_hash},
        "objectives_and_constraints": {
            "personality": chosen,
            "liquidity_need": float(liquidity_need),
            "cash_floor_pct": floor_pct,
            "constraints": list(parsed["tokens"])},
        "risk_profile": {
            "ability_score": scored["ability_score"],
            "willingness_score": scored["willingness_score"],
            "composite_score": scored["composite_score"],
            "questionnaire_version": QUESTIONNAIRE_VERSION,
            "answers": list(scored["answers"])},
        "eligible_universe": {
            "source": str(universe_source),
            "floor_dollar_vol_usd": float(floor_dollar_vol_usd),
            "excluded_tickers": list(parsed["excluded_tickers"]),
            "excluded_sectors": list(parsed["excluded_sectors"])},
        "review_cadence": {
            "daily_review": True,
            "rebalance_frequency": TABLE[chosen].rebalance_frequency},
        "personality": chosen,
    }
    doc["ips_hash"] = ips_hash(doc)
    validated = validate_document(doc)
    row = TABLE[chosen]
    numbers = numeric_fields(doc, row)
    echoes = list(parsed["echoes"])
    if override:
        echoes.append(override)
    echoes.append(f"amendment rule: {kind['kind']} ({kind['reason']})")

    prose, source, rejected = ("", "not_drafted", "")
    if draft:
        prose, source, rejected = draft_prose(doc, row, numbers)
    return IPS(document=doc, prose_md=prose, prose_source=source,
               prose_rejected=rejected, validator=validated["validator"],
               numbers=numbers, echoes=tuple(echoes))


# ===========================================================================
# A1 — THE PROSE, AND THE CHECK THAT KEEPS IT PROSE
# ===========================================================================

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _renderings(v: float) -> set[str]:
    """Every way a sentence might legitimately print one engine number."""
    out: set[str] = set()
    for x in (float(v), abs(float(v)), float(v) * 100.0, abs(float(v)) * 100.0):
        for digits in (0, 1, 2, 3, 4):
            s = f"{x:.{digits}f}"
            out.add(s)
            if "." in s:
                out.add(s.rstrip("0").rstrip("."))
            grouped = f"{x:,.{digits}f}"
            out.add(grouped)
            out.add(grouped.replace(",", ""))
    return {s for s in out if s and s[0].isdigit()}


def unexplained_numbers(text: str, numbers: Mapping[str, float]) -> list[str]:
    """Numeric tokens in `text` that no engine number renders to.

    The spec's rule is "prose never carries a number the engine did not
    compute". Years and small ordinals are not exempted by a hard-coded
    allowlist — every number the prose may use is put INTO `numbers` by
    `numeric_fields`, so the exemption list is the engine's own output.
    """
    allowed: set[str] = set()
    for v in numbers.values():
        allowed |= _renderings(v)
    bad: list[str] = []
    for m in _NUM_RE.finditer(text or ""):
        tok = m.group(0)
        if tok in allowed or tok.replace(",", "") in allowed:
            continue
        bad.append(tok)
    return bad


def template_prose(doc: Mapping[str, Any], row: PersonalityRow,
                   numbers: Mapping[str, float]) -> str:
    """The prose when no model is up. Written from the same numbers, so the
    fallback is a worse SENTENCE and never a different FACT."""
    oc = doc["objectives_and_constraints"]
    rp = doc["risk_profile"]
    eu = doc["eligible_universe"]
    return "\n".join([
        f"## Your policy — {doc['personality']}",
        "",
        f"You are putting ${numbers['capital_usd']:,.0f} to work for "
        f"{int(numbers['horizon_months'])} months. Your answers score "
        f"{rp['ability_score']} on ability to take risk and "
        f"{rp['willingness_score']} on willingness to take it; the policy uses "
        f"the lower of the two, {rp['composite_score']}, because what you "
        f"prefer cannot raise what you can afford.",
        "",
        f"**How the money is held.** {oc['cash_floor_pct'] * 100:.0f}% stays "
        f"in cash so it is reachable, and the rest buys at most {row.k} names, "
        f"none larger than {row.max_single_name * 100:.0f}% of the book. Each "
        f"position leaves on a {abs(row.stop_loss) * 100:.0f}% stop.",
        "",
        f"**What a bad day looks like.** If every position stopped out on the "
        f"same day you would be down about "
        f"${abs(numbers['worst_case_usd']):,.0f}, which is "
        f"{numbers['worst_case_pct_of_equity'] * 100:.1f}% of this money, at "
        f"{row.gross_cap:.2f}x gross exposure. The book's drawdown budget is "
        f"{abs(row.drawdown_budget) * 100:.0f}%; past that it protects first.",
        "",
        f"**What is excluded.** {len(eu['excluded_tickers'])} name(s) and "
        f"{len(eu['excluded_sectors'])} sector(s), from the constraints you "
        f"gave.",
        "",
        f"Reviewed every trading day; rebalanced "
        f"{doc['review_cadence']['rebalance_frequency']}.",
    ])


#: The local model's instruction. It names the language (the `_LANGUAGE_PIN` is
#: appended centrally by `model_provider`, and this is the second belt) and it
#: forbids arithmetic explicitly, because a model asked to "explain the numbers"
#: will helpfully compute a new one.
PROSE_SYSTEM = (
    "You write one short plain-English explanation of an investment policy for "
    "a non-expert. Reply in English. You MUST NOT invent, compute, round or "
    "restate any number that is not given to you verbatim; copy the numbers "
    "exactly as written. No advice, no predictions, no ticker suggestions.")

PROSE_MAX_TOKENS = 420


def draft_prose(doc: Mapping[str, Any], row: PersonalityRow,
                numbers: Mapping[str, float]) -> tuple[str, str, str]:
    """(prose, source, rejection_reason).

    The local model DRAFTS; the template stands in when it is not up. Either
    way the result passes `unexplained_numbers` — a draft carrying a number the
    engine did not compute is DISCARDED, not repaired, and the reason travels
    onto the payload. The same discipline as the language refusal: a repaired
    answer hides how often the model needed repairing.
    """
    fallback = template_prose(doc, row, numbers)
    try:
        from backend.services import free_inference as fi          # noqa: PLC0415
    except Exception as exc:                                       # noqa: BLE001
        return fallback, "template", f"free_inference unavailable: {exc}"[:200]
    facts = "\n".join(f"- {k}: {v}" for k, v in sorted(numbers.items()))
    prompt = (
        f"Write four short paragraphs explaining this investment policy to its "
        f"owner. Personality: {doc['personality']}. Use ONLY these numbers, "
        f"copied exactly:\n{facts}\n"
        f"Cover: what the money is for, how it is held, what a bad day costs, "
        f"and when it is reviewed.")
    try:
        reply = fi.complete(backend="local_gguf", prompt=prompt,
                            system=PROSE_SYSTEM, purpose="agency_ips_prose",
                            max_tokens=PROSE_MAX_TOKENS, temperature=0.0)
    except Exception as exc:                                       # noqa: BLE001
        return fallback, "template", f"{type(exc).__name__}: {exc}"[:200]
    text = (reply.text or "").strip()
    if not text:
        return fallback, "template", "the model returned an empty draft"
    bad = unexplained_numbers(text, numbers)
    if bad:
        return fallback, "template", (
            f"the draft carried {len(bad)} number(s) the engine did not "
            f"compute ({bad[:5]}) — DISCARDED, not repaired: a sentence that "
            f"invents a number reads exactly like one that reports one")
    return text, f"local_gguf:{reply.model}", ""


# ===========================================================================
# A2 — THE THREE OPTIONS
# ===========================================================================
#
# "From one IPS the engine proposes three books — preservation / balanced /
# aggressive expressions of the same IPS — each with its twin, worst case in
# dollars, expected drawdown at the declared budget, and the hold rule. Murat
# picks one; the other two are held as shadow books" (A2).
#
# WHY THE SIGNAL IS NOT `agency_default_composite`
# ------------------------------------------------
# Spec §2.1 names the signal `agency_default_composite`. A book declaring it
# would be MARKED and would never DECIDE: `book_cadence._signal_frame` is
# faithful to the contract or it refuses, and neither `SUPPORTED_SIGNALS` nor
# `book_signals.REGISTRY` can compute a signal of that name. Inventing a new
# composite here to fill the gap would be a new alpha claim shipped with no
# evidence and no control, inside the chunk whose subject is risk TREATMENT.
#
# So the agency proposes over a signal the selector can already compute, named
# honestly, and the tier is what differs between the three options — which is
# what A2 actually asks for ("three expressions of the same IPS"). The signal
# is a PARAMETER (`propose(..., signal=...)`), so when lane B's library grows a
# second independent selector the agency can offer it without touching this
# module, and the book's fingerprint changes when the signal does, which is the
# property that keeps two different strategies from sharing one forward record.
#
# The spec's intent is preserved: a lane A book is its own book with its own
# twins and its own scoreboard, never a weight folded into `arena_composite`
# (CLAUDE.md THE BOTTLENECK).

AGENCY_SIGNAL_DEFAULT = "mom_12_1"

#: What `propose` will accept. Derived from the two places that can actually
#: compute a ranking, never re-typed — a gate that derives its inputs
#: (CLAUDE.md). A signal missing from both is refused at PROPOSE time rather
#: than becoming a book that marks forever and decides never.
def supported_signals() -> tuple[str, ...]:
    from backend.services import book_signals as BS               # noqa: PLC0415
    from backend.services.book_cadence import SUPPORTED_SIGNALS   # noqa: PLC0415
    twins = {"random_genome_null", "beta_matched_index_sleeve", "overnight_only"}
    return tuple(sorted((set(SUPPORTED_SIGNALS) | set(BS.REGISTRY)) - twins))


#: The cadence a book runs on, from the IPS's rebalance frequency. The daily
#: REVIEW runs regardless (A3); this is how often the book may TRADE.
CADENCE_FOR_REBALANCE = {"daily": "daily", "weekly": "weekly",
                         "monthly": "monthly", "quarterly": "quarterly"}

#: 45% of positions are expected to lose, declared BEFORE the first position
#: (invariant 19). A placeholder with a receipt owed: the farm has no
#: same-shape control for a k-name long-only book at this cadence yet, and a
#: loss budget nobody declared is a book retired by its own first loss.
EXPECTED_LOSER_FRACTION = 0.45
POSITIONS_JUDGED_PER_K = 4        # ~one year of turnover at the book's cadence


def neighbours(personality: str) -> list[str]:
    """The chosen tier plus its two neighbours on the risk ladder (§2).

    Three, never four, and the window SLIDES at the ends rather than inventing
    a fourth bucket: at `preservation` the three are preservation / balanced /
    aggressive, at `extreme_growth` they are balanced / aggressive /
    extreme_growth. The human sees one step either side of what they said.
    """
    if personality not in TABLE:
        raise AgencyError(f"personality {personality!r} is not one of "
                          f"{list(PERSONALITIES)}")
    i = PERSONALITIES.index(personality)
    lo = max(0, min(i - 1, len(PERSONALITIES) - 3))
    return list(PERSONALITIES[lo:lo + 3])


def hold_rule_words(personality: str) -> str:
    """The hold rule in the words a person reads, from the same table the
    contract is built from — so the sentence cannot drift from the rule."""
    fam = HOLD_FAMILY[personality]
    rungs = ", ".join(f"after {k} session(s) take {v:.0%}"
                      for k, v in sorted(fam["roi_ladder"].items()))
    row = TABLE[personality]
    return (f"Hold each name up to {fam['horizon_periods']} sessions "
            f"(minimum {fam['min_hold_periods']}), leave on a "
            f"{abs(row.stop_loss):.0%} stop, and take profit on the "
            f"{fam['family']} ladder: {rungs}. Reviewed every trading day; "
            f"the book may trade {row.rebalance_frequency}.")


def _cost_model(symbols: Sequence[str] | None):
    """`taq_empirical` when the universe is ticker-keyed, `flat` otherwise.

    The curve is a CLAIM about how the net was computed, so it is declared from
    what the book can actually price: with a frozen symbol list every fill can
    be quoted per name off the TAQ panel (or its regression), and without one
    there is nothing to key on and the flat rate is the honest declaration.
    Costs are never zero either way — `CostModel` delegates that refusal to
    `portfolio_farm.Policy`, which is the one place it lives.
    """
    from backend.strategy.contract import CostModel                # noqa: PLC0415
    curve = "taq_empirical" if symbols else "flat"
    return CostModel(transaction_cost_bps=5.0, slippage_bps=1.0, curve=curve,
                     note=("per-name effective spread off the TAQ panel"
                           if symbols else
                           "flat: this universe is a screen, not a ticker list, "
                           "so there is nothing to key a per-name curve on"))


def build_strategy(ips: IPS, personality: str, *,
                   symbols: Sequence[str] | None = None,
                   signal: str | None = None):
    """One `Strategy` for one tier of one IPS (§2.1)."""
    from backend.strategy.contract import (Benchmark, Construction, HoldRule,
                                           Licence, LossBudget, Objective,
                                           Signal, Sizing, Strategy, Universe)
    if personality not in TABLE:
        raise AgencyError(f"personality {personality!r} is not one of "
                          f"{list(PERSONALITIES)}")
    sig = str(signal or AGENCY_SIGNAL_DEFAULT)
    allowed = supported_signals()
    if sig not in allowed:
        raise AgencyError(
            f"signal {sig!r} cannot be computed by the cadence selector "
            f"({list(allowed)}). A book whose signal nothing can compute is "
            f"marked forever and decides never, which reads on the board as a "
            f"book that chose to hold nothing.")
    row = TABLE[personality]
    fam = HOLD_FAMILY[personality]
    eu = ips.document["eligible_universe"]
    invested = 1.0 - ips.cash_floor_pct
    judged = int(row.k * POSITIONS_JUDGED_PER_K)
    return Strategy(
        strategy_id=f"agency-{ips.ips_id}-{personality}",
        title=f"{ips.ips_id} / {personality}",
        universe=Universe(
            name=f"agency-{ips.ips_id}-universe",
            source=str(eu["source"]),
            floor_dollar_vol_usd=float(eu["floor_dollar_vol_usd"]),
            max_names=None,        # Construction.k is the binding cap
            note=("filtered by the IPS constraints at build time (§1.6): "
                  f"{len(eu['excluded_tickers'])} ticker(s), "
                  f"{len(eu['excluded_sectors'])} sector(s) excluded")),
        signal=Signal(name=sig, column=sig, direction=1, source="lane_a_v1",
                      note=("the agency proposes three RISK TREATMENTS of one "
                            "IPS over one declared signal; the tier is what "
                            "differs between the three options")),
        construction=Construction(rule="top_k", k=row.k, weighting="ew",
                                  max_single_name=row.max_single_name,
                                  gross_cap=row.gross_cap),
        hold=HoldRule(horizon_periods=int(fam["horizon_periods"]),
                      min_hold_periods=int(fam["min_hold_periods"]),
                      roi_ladder=dict(fam["roi_ladder"]),
                      stop_loss=row.stop_loss,
                      scheduled_review_periods=1),
        sizing=Sizing(rule="equal_weight", gross_cap=row.gross_cap,
                      notional_usd=round(ips.capital_usd * invested, 2)),
        costs=_cost_model(symbols),
        benchmark=Benchmark(name="SPY", series_key="spy_tr", beta_matched=True),
        objective=Objective(name="terminal_wealth_at_drawdown_budget",
                            drawdown_budget=row.drawdown_budget,
                            utility=("risk_seeking"
                                     if personality == "extreme_growth"
                                     else "risk_adjusted")),
        loss_budget=LossBudget(
            positions_judged=judged,
            expected_losers=round(judged * EXPECTED_LOSER_FRACTION),
            note=(f"{EXPECTED_LOSER_FRACTION:.0%} base-rate loser fraction — a "
                  f"RECEIPT-OWED placeholder until the farm has a same-shape "
                  f"control for a {row.k}-name long-only book at this cadence")),
        licence=Licence.PRODUCT_EXPERIMENT,
        engine="series",
        engine_params={"ips_hash": ips.ips_hash, "personality": personality,
                       "lane": "A", "cash_floor_pct": ips.cash_floor_pct,
                       **({"symbols": list(symbols)} if symbols else {})},
    )


def eligible_symbols(ips: IPS, bars, asof) -> list[str]:
    """The IPS's declared universe resolved to names on `asof`, minus the
    constraint exclusions. Empty when there are no bars to resolve from — a
    screen with nothing behind it is not a ticker list, and `_cost_model`
    reads exactly that distinction."""
    from backend.services import paper_books as PB                 # noqa: PLC0415
    if bars is None:
        return []
    eu = ips.document["eligible_universe"]
    panel = PB.liquidity_panel(bars, asof)
    if panel.empty:
        return []
    panel = panel[panel["dollar_vol"] >= float(eu["floor_dollar_vol_usd"])]
    panel = panel[panel["n_bars"] >= 5]
    banned = set(eu["excluded_tickers"])
    return sorted(s for s in panel["symbol"].astype(str) if s not in banned)


def expected_drawdown_at_budget(strategy, twins, *, conn=None,
                                db_path=None) -> dict:
    """The worst drawdown the book's own CONTROLS have actually shown.

    Not a simulation and not a parametric guess: the twins share the book's
    universe band, cadence and costs and carry no signal, so their realised
    peak-to-trough IS what construction-level volatility alone does to this
    shape. With no marked history it returns CANNOT DETERMINE and says so —
    a number here that came from nowhere would be read as a forecast.
    """
    from backend.services import paper_books as PB                 # noqa: PLC0415
    budget = strategy.objective.drawdown_budget
    ids = [t.book_id for t in twins]
    try:
        series = PB.nav_series(ids, conn=conn, db_path=db_path)
    except Exception as exc:                                       # noqa: BLE001
        return {"verdict": "CANNOT DETERMINE",
                "why": f"the book table could not be read: {exc}"[:200],
                "drawdown_budget": budget}
    worst: float | None = None
    n_marks = 0
    for tid in ids:
        path = series.get(tid) or []
        n_marks += len(path)
        peak = None
        for _d, nav in path:
            peak = nav if peak is None else max(peak, nav)
            if peak:
                dd = nav / peak - 1.0
                worst = dd if worst is None else min(worst, dd)
    if worst is None:
        return {"verdict": "CANNOT DETERMINE",
                "why": ("neither twin has been marked yet, so this shape has "
                        "no realised drawdown. An expected drawdown computed "
                        "from no history is a forecast wearing a measurement's "
                        "clothes."),
                "drawdown_budget": budget, "n_twin_marks": 0}
    return {"verdict": "measured on the twins",
            "worst_twin_drawdown": round(worst, 6),
            "drawdown_budget": budget,
            "n_twin_marks": n_marks,
            "basis": ("peak-to-trough of the control twins' own NAV paths — "
                      "same universe band, same cadence, same costs, no "
                      "signal, so this is construction-level volatility alone"),
            "within_budget": bool(budget is None or worst > budget)}


@dataclass(frozen=True)
class Option:
    """One of the three. Carries its contract, its twins and its worst case —
    never a return, because it has not run."""

    personality: str
    strategy: Any
    twins: tuple
    worst_case: Mapping[str, Any]
    expected_drawdown: Mapping[str, Any]
    hold_rule: str
    is_declared_choice: bool
    cash_floor_pct: float

    @property
    def contract_hash(self) -> str:
        return str(self.strategy.fingerprint)

    def as_row(self) -> dict:
        row = TABLE[self.personality]
        return {
            "personality": self.personality,
            "is_declared_choice": self.is_declared_choice,
            "contract_hash": self.contract_hash,
            "strategy_id": self.strategy.strategy_id,
            "title": self.strategy.title,
            "signal": self.strategy.signal.name,
            "k": self.strategy.construction.k,
            "max_single_name": self.strategy.construction.max_single_name,
            "gross_cap": self.strategy.sizing.gross_cap,
            "stop_loss": self.strategy.hold.stop_loss,
            "drawdown_budget": self.strategy.objective.drawdown_budget,
            "cash_floor_pct": self.cash_floor_pct,
            "notional_usd": self.strategy.sizing.notional_usd,
            "cadence": CADENCE_FOR_REBALANCE[row.rebalance_frequency],
            "hold_rule": self.hold_rule,
            "worst_case": dict(self.worst_case),
            "expected_drawdown": dict(self.expected_drawdown),
            "extrapolated_tier": row.extrapolated,
            "twins": [{"book_id": t.book_id,
                       "kind": (t.strategy.engine_params.get("twin") or {}).get("kind"),
                       "construction": t.control_construction}
                      for t in self.twins],
            "contract": self.strategy.as_dict(),
            **self.strategy.costs.as_row(),
        }


def propose(ips: IPS, *, bars=None, asof=None, conn=None, db_path=None,
            signal: str | None = None) -> list[Option]:
    """Three `Strategy` contracts, each with its twins and its worst case (A2).

    Nothing is written. The twins are built here rather than at hold time for
    the same reason `paper_books.create` builds them before the book has a
    number: a control constructed after a number is known is a control chosen
    to flatter it, and the human is about to compare three numbers.
    """
    from datetime import date as _date                             # noqa: PLC0415

    from backend.services import paper_books as PB                 # noqa: PLC0415
    from backend.strategy.contract import loss_budget_worst_case   # noqa: PLC0415

    asof = asof or _date.today()
    symbols = eligible_symbols(ips, bars, asof)
    out: list[Option] = []
    for personality in neighbours(ips.personality):
        strategy = build_strategy(ips, personality, symbols=symbols,
                                  signal=signal)
        cadence = CADENCE_FOR_REBALANCE[TABLE[personality].rebalance_frequency]
        twins = PB.make_twins(strategy, cadence=cadence, bars=bars, asof=asof)
        # THE ONE FUNCTION. Session protocol rule 4 exists precisely so the
        # arithmetic is never re-derived per caller: gross beside stop, both or
        # neither. The equal-weight notional is the binding constraint whenever
        # it is tighter than `max_single_name`, which is what `paper_books.
        # worst_case` learned on the first night_job book.
        k = strategy.construction.k
        per_name = min(float(strategy.construction.max_single_name),
                       float(strategy.construction.gross_cap) / k)
        worst = loss_budget_worst_case(
            strategy, n_names=k, notional_pct=per_name,
            equity_usd=ips.capital_usd * (1.0 - ips.cash_floor_pct))
        worst["equity_basis"] = ("the INVESTED fraction of the IPS capital; "
                                 "the cash sleeve cannot be stopped out and is "
                                 "excluded (§1.5)")
        worst["notional_pct_binding_constraint"] = (
            "max_single_name" if strategy.construction.max_single_name
            <= float(strategy.construction.gross_cap) / k else "gross_cap / k")
        out.append(Option(
            personality=personality, strategy=strategy, twins=tuple(twins),
            worst_case=worst,
            expected_drawdown=expected_drawdown_at_budget(
                strategy, twins, conn=conn, db_path=db_path),
            hold_rule=hold_rule_words(personality),
            is_declared_choice=(personality == ips.personality),
            cash_floor_pct=ips.cash_floor_pct))
    return out


def propose_payload(ips: IPS, options: Sequence[Option]) -> dict:
    """What a route or a page gets. Three options, never two, and the limits
    sentence on every agency payload (§5.2)."""
    return {"ips_hash": ips.ips_hash, "ips_id": ips.ips_id,
            "declared_personality": ips.personality,
            "capital_usd": ips.capital_usd,
            "cash_floor_pct": ips.cash_floor_pct,
            "n_options": len(options),
            "options": [o.as_row() for o in options],
            "how_to_hold": ("POST /api/control/agency/hold with {ips_hash, "
                            "chosen_contract_hash, sentence}. The sentence is "
                            "required: it is what makes the book yours."),
            "the_choice_is_graded": (
                "the two you do not choose are created as shadow books on the "
                "same clock, with their own twins, so the CHOICE has a "
                "counterfactual and not just an outcome"),
            "limits": LIMITS_SENTENCE}


# ===========================================================================
# A2 — THE HOLD (and it is a human who holds)
# ===========================================================================

#: The shortest sentence that can count as a reason. Not a length check for
#: its own sake: `origin="human_text"` is the only thing that distinguishes a
#: book a person chose from one a job produced, and an empty string would make
#: that distinction unauditable the first time it mattered.
MIN_SENTENCE_CHARS = 12


def hold(ips: IPS, *, chosen_contract_hash: str, sentence: str, bars,
         asof=None, conn=None, db_path=None,
         signal: str | None = None) -> dict:
    """Create the chosen book as `human_text`, the other two as shadows (A2).

    This is the only path in the repository that mints `origin="human_text"`,
    and it records the sentence that was typed. The un-chosen options are NOT
    discarded and NOT `night_job`: they are `shadow_of:<ips_hash>` books,
    marked and forecast on the same clock, so "you would have done better with
    the other one" is a measurement rather than an argument.
    """
    from datetime import date as _date                             # noqa: PLC0415

    from backend.services import paper_books as PB                 # noqa: PLC0415

    text = (sentence or "").strip()
    if len(text) < MIN_SENTENCE_CHARS:
        raise AgencyError(
            f"a hold needs a sentence of at least {MIN_SENTENCE_CHARS} "
            f"characters saying why you are holding this one. `human_text` is "
            f"the only marker that separates a book a person chose from a book "
            f"a job produced; minting one without the sentence makes that "
            f"distinction unauditable.")
    asof = asof or _date.today()
    options = propose(ips, bars=bars, asof=asof, conn=conn, db_path=db_path,
                      signal=signal)
    by_hash = {o.contract_hash: o for o in options}
    chosen = by_hash.get(str(chosen_contract_hash))
    if chosen is None:
        raise AgencyError(
            f"contract hash {chosen_contract_hash!r} is not one of the three "
            f"this IPS proposes ({sorted(by_hash)}). A hold on a contract the "
            f"engine did not propose is a hold on something nobody costed.")
    created: list[dict] = []
    chosen_book, chosen_twins = PB.create(
        chosen.strategy,
        cadence=CADENCE_FOR_REBALANCE[TABLE[chosen.personality].rebalance_frequency],
        origin="human_text", origin_text=text, ips_hash=ips.ips_hash,
        shadow=False, bars=bars, asof=asof, conn=conn, db_path=db_path)
    created.append({"role": "chosen", "book": chosen_book.as_row(),
                    "twins": [t.as_row() for t in chosen_twins]})
    for opt in options:
        if opt.contract_hash == chosen.contract_hash:
            continue
        book, twins = PB.create(
            opt.strategy,
            cadence=CADENCE_FOR_REBALANCE[TABLE[opt.personality].rebalance_frequency],
            origin=f"{PB.SHADOW_PREFIX}{ips.ips_hash}",
            origin_text=(f"the road not taken: {opt.personality} expression of "
                         f"{ips.ips_id}, graded beside the chosen book"),
            ips_hash=ips.ips_hash, shadow=True, bars=bars, asof=asof,
            conn=conn, db_path=db_path)
        created.append({"role": "shadow", "book": book.as_row(),
                        "twins": [t.as_row() for t in twins]})
    return {"held_utc": _now(), "ips_hash": ips.ips_hash,
            "chosen_book_id": chosen_book.book_id,
            "chosen_contract_hash": chosen.contract_hash,
            "sentence": text, "books": created,
            "worst_case": dict(chosen.worst_case),
            "hold_rule": chosen.hold_rule,
            "note": ("nothing here placed an order. The book and its shadows "
                     "are frozen contracts and will be marked by the next "
                     "cadence pass."),
            "limits": LIMITS_SENTENCE}


# ===========================================================================
# THE IPS STORE — a hash has to resolve to a document
# ===========================================================================
#
# `hold` takes an `ips_hash`, and every book carries one. Something has to turn
# that hash back into the policy, or the protect-first budget and the review's
# own limits would have to be re-derived from a book's contract — which is the
# shape that lets two readers disagree about what the client actually asked
# for. One JSON file per IPS, named by its hash, written once.


def ips_dir():
    """`backend/data/optimus/agency/ips`, rooted on AEGIS_REPO_ROOT.

    NOT on `__file__`: inside a PyInstaller build that resolves to `_internal`
    and the app writes policies into a directory that disappears on the next
    install (`[[a-path-that-resolves-differently-when-frozen-is-a-defect-family]]`).
    """
    import os                                                      # noqa: PLC0415
    from pathlib import Path                                       # noqa: PLC0415
    env = os.getenv("AEGIS_REPO_ROOT")
    root = (Path(env) if env and Path(env).is_dir()
            else Path(__file__).resolve().parent.parent.parent)
    return root / "backend" / "data" / "optimus" / "agency" / "ips"


def save_ips(ips: IPS, *, directory=None) -> str:
    """Write the policy under its own hash. Returns the path.

    Written once and never rewritten: an IPS is immutable by construction (an
    amendment is a new document pointing at this one), so a second write of the
    same hash is the same bytes and a different hash is a different file.
    """
    from pathlib import Path                                       # noqa: PLC0415
    d = Path(directory) if directory is not None else ips_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{ips.ips_hash}.json"
    if not path.exists():
        path.write_text(json.dumps(
            {"ips": ips.document, "ips_prose_md": ips.prose_md,
             "prose_source": ips.prose_source, "validated_by": ips.validator,
             "numeric_fields": dict(ips.numbers), "echoes": list(ips.echoes),
             "saved_utc": _now()},
            ensure_ascii=False, indent=1), encoding="utf-8")
    return str(path)


def load_ips(hash_: str, *, directory=None) -> IPS:
    """Rebuild an IPS from the store, REVALIDATING it and rechecking its hash.

    A stored document is untrusted input like any other: the file could have
    been edited by hand, and an IPS whose hash no longer matches its content is
    a policy nobody agreed to.
    """
    from pathlib import Path                                       # noqa: PLC0415
    d = Path(directory) if directory is not None else ips_dir()
    path = d / f"{str(hash_)}.json"
    if not path.is_file():
        raise AgencyError(
            f"no IPS with hash {hash_!r} in {d}. A hold names a policy by its "
            f"hash; without the document the engine cannot rebuild the three "
            f"options it is being asked to choose between.")
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AgencyError(f"the stored IPS {hash_!r} could not be read: "
                          f"{exc}") from exc
    doc = blob.get("ips") or {}
    validated = validate_document(doc)
    recomputed = ips_hash(doc)
    if recomputed != str(hash_) or recomputed != doc.get("ips_hash"):
        raise AgencyError(
            f"the stored IPS at {path.name} hashes to {recomputed}, not "
            f"{hash_}. The file has been edited since it was written; a policy "
            f"whose hash does not match its content is one nobody agreed to.")
    row = TABLE[str(doc["personality"])]
    return IPS(document=doc, prose_md=str(blob.get("ips_prose_md") or ""),
               prose_source=str(blob.get("prose_source") or "template"),
               validator=validated["validator"],
               numbers=numeric_fields(doc, row),
               echoes=tuple(blob.get("echoes") or ()))


# ===========================================================================
# A3 — THE DAILY REVIEW
# ===========================================================================
#
# "For each holding, {hold, sell, buy_more, trim} with a probability, the news
# and events that moved it, and the forecast row written BEFORE the call is
# shown" (A3).
#
# THE ORDERING IS THE POINT
# -------------------------
# The `PredictionRecord` is built, appended and re-read from disk BEFORE the
# call is returned. `append()` returns None by house rule, so nothing branches
# on the write — the render path branches on having successfully called it and
# on the row being readable back. If `make_prediction` refuses (an out-of-range
# probability, a horizon that is not a declared one), the holding gets NO row
# in the day's review: a refusal, never a silently ungraded display.
#
# WHERE THE PROBABILITY COMES FROM, AND WHY IT IS NOT AN LLM's
# ------------------------------------------------------------
# No LLM produces this number and none may (`no LLM output ever sizes, ranks
# or decides`). It is Φ of a sum of DECLARED terms, each of which is recorded
# on the row with its own basis string, so a reader can see which ones were
# live and which returned zero because the input does not exist yet:
#
#   1. the holding's trailing information ratio against the book's control
#      twin — the same Φ(IR) convention as `book_forecasts` (spec_first_books
#      §0B), computed from history that had already happened;
#   2. the calibrated target's interval, when a target exists for the name;
#   3. the BOOK's drawdown state against its own budget;
#   4. the typed-event count — zero until L2 lands, and recorded as zero
#      rather than omitted, because an absent term and a neutral term read
#      identically in a sum and mean different things;
#   5. the market sensor's regime read — a declared placeholder (invariant 4 /
#      X4), which informs and never overrides.
#
# THE LABEL IS DERIVED FROM THE PROBABILITY, NOT CHOSEN BESIDE IT
# ---------------------------------------------------------------
# `sell` attached to p=0.62 is a contract violation, and `_check_label`
# refuses to render it. Two numbers called "the call" is how a system starts
# disagreeing with itself in public.

DECISIONS: tuple[str, ...] = ("hold", "sell", "buy_more", "trim")

#: The two cut points. Declared here, hashed into nothing, and deliberately
#: symmetric: an asymmetric pair would encode a directional view in what is
#: supposed to be a translation from a probability to a verb.
SELL_BELOW = 0.40
BUY_MORE_ABOVE = 0.60

#: How far over its own cap a position must sit before the call is `trim`.
#: Not zero: a weight 0.01pp over the cap on a rounding difference is not a
#: decision, it is float arithmetic.
OVERWEIGHT_TOLERANCE = 0.005

#: The drawdown term. A book already halfway through its budget is a book
#: whose next loss is the one that flips it (§4), so the term is negative and
#: it is the only one of the five that is currently non-zero by construction.
DRAWDOWN_TILT_Z = -0.25

SPECIALIST = "agency_daily_review"
REVIEW_MECHANISM = "agency_review_v1"
REVIEW_MODEL = "engine"
REVIEW_MODEL_VERSION = "agency_review_v1"

#: Where `review` appends when no caller names a path. `None` means
#: `belief_state.PREDICTIONS`. A module constant so the suite can redirect THIS
#: writer — the one that fires from the Morning click with no caller in sight.
DEFAULT_LEDGER = None


def _phi(z: float) -> float:
    import math                                                    # noqa: PLC0415
    return 0.5 * (1.0 + math.erf(float(z) / math.sqrt(2.0)))


def decide_label(probability: float, *, weight: float,
                 max_single_name: float) -> tuple[str, str]:
    """(decision, why) — DERIVED from the probability and the position's size.

    `trim` is the overweight branch and not a third opinion: it fires when the
    position has grown past the cap the contract declares, whatever the
    probability says, because a book that is over its own concentration limit
    is out of contract before it is out of favour.
    """
    p = float(probability)
    if p < SELL_BELOW:
        return "sell", (f"p={p:.2f} is below {SELL_BELOW:.2f}: the position is "
                        f"more likely than not to lose to the control twin")
    if weight > float(max_single_name) + OVERWEIGHT_TOLERANCE:
        return "trim", (f"the position is {weight:.1%} of the book against a "
                        f"{max_single_name:.1%} cap — out of contract, so it "
                        f"is reduced TOWARD the cap and not to zero")
    if p >= BUY_MORE_ABOVE:
        return "buy_more", (f"p={p:.2f} is at or above {BUY_MORE_ABOVE:.2f} and "
                            f"the position has room under its "
                            f"{max_single_name:.1%} cap")
    return "hold", (f"p={p:.2f} sits between {SELL_BELOW:.2f} and "
                    f"{BUY_MORE_ABOVE:.2f}: no change")


def _check_label(decision: str, probability: float, *, weight: float,
                 max_single_name: float) -> None:
    """The label and the probability must be able to coexist, or the row is
    refused. §3.1: 'a sell label attached to probability=0.62 is a contract
    violation the engine refuses to render.'"""
    if decision not in DECISIONS:
        raise AgencyError(f"decision {decision!r} is not one of {list(DECISIONS)}")
    p = float(probability)
    over = weight > float(max_single_name) + OVERWEIGHT_TOLERANCE
    if decision == "sell" and p >= SELL_BELOW:
        raise AgencyError(
            f"a `sell` call carries p={p:.2f}, at or above {SELL_BELOW:.2f}. "
            f"The label is DERIVED from the probability; two numbers called "
            f"'the call' is how a system starts disagreeing with itself.")
    if decision == "buy_more" and (p < BUY_MORE_ABOVE or over):
        raise AgencyError(
            f"a `buy_more` call carries p={p:.2f} at weight {weight:.1%} "
            f"against a {max_single_name:.1%} cap; one of the two forbids it")
    if decision == "trim" and not over:
        raise AgencyError(
            f"a `trim` call on a position at {weight:.1%} against a "
            f"{max_single_name:.1%} cap: trim is the OVERWEIGHT branch, and "
            f"using it as a soft sell would hide the sell")
    if decision == "hold" and (p < SELL_BELOW or p >= BUY_MORE_ABOVE or over):
        raise AgencyError(
            f"a `hold` call at p={p:.2f}, weight {weight:.1%}: the derivation "
            f"would not have produced it")


def _twin_nav(book, conn=None, db_path=None) -> tuple[str | None, list]:
    """(twin book id, its NAV series). The FIRST twin, as `book_forecasts`
    uses, so the book's own forecast row and its holdings' rows are graded
    against the same control."""
    from backend.services import paper_books as PB                 # noqa: PLC0415
    if not book.control_twin_ids:
        return None, []
    tid = book.control_twin_ids[0]
    try:
        return tid, (PB.nav_series([tid], conn=conn, db_path=db_path).get(tid)
                     or [])
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("review: the twin's NAV could not be read (%s)", exc)
        return tid, []


def _price_series(bars, ticker: str, asof) -> list:
    """[(date, close)] for one name up to and including `asof`."""
    import pandas as pd                                            # noqa: PLC0415
    if bars is None:
        return []
    ts = pd.Timestamp(asof)
    sub = bars[(bars["date"] <= ts) & (bars["symbol"] == ticker)]
    if sub.empty:
        return []
    sub = sub.sort_values("date")
    return [(str(pd.Timestamp(d).date()), float(c))
            for d, c in zip(sub["date"], sub["close"])]


def probability_terms(*, ticker: str, price_path, twin_path,
                      drawdown_state: Mapping[str, Any],
                      target: Mapping[str, Any] | None = None,
                      n_typed_events: int = 0,
                      sensor: Mapping[str, Any] | None = None) -> dict:
    """The five declared terms and the probability they sum to.

    Every term is returned with its own basis, INCLUDING the ones that are
    zero because their input does not exist yet. A term omitted because it has
    no data and a term that legitimately came out neutral are the same number
    and different facts.
    """
    from backend.services.book_forecasts import trailing_ir       # noqa: PLC0415

    terms: list[dict] = []
    ir, n_paired = trailing_ir(price_path, twin_path)
    terms.append({
        "term": "trailing_ir_vs_twin",
        "z": float(ir) if ir is not None else 0.0,
        "basis": (f"information ratio of {ticker}'s daily return minus the "
                  f"control twin's, over {n_paired} paired session(s)"
                  if ir is not None else
                  f"CANNOT DETERMINE — {n_paired} paired session(s) with the "
                  f"twin; an IR from fewer than two observations has no "
                  f"sampling distribution behind it"),
        "n_paired": n_paired})

    # 2. the calibrated target's interval
    if target and target.get("p50") is not None and target.get("spot"):
        spot = float(target["spot"])
        p50 = float(target["p50"])
        lo, hi = target.get("p10"), target.get("p90")
        implied = (p50 / spot - 1.0) if spot else 0.0
        band = ("banded" if lo is not None and hi is not None
                else "point only (the band was withheld or never fitted)")
        terms.append({"term": "calibrated_target_interval",
                      "z": round(max(-1.0, min(1.0, implied * 2.0)), 6),
                      "basis": (f"calibrated 52-week target implies "
                                f"{implied:+.1%} against spot; {band}. Capped "
                                f"at +/-1 z so one target cannot carry the call")})
    else:
        terms.append({"term": "calibrated_target_interval", "z": 0.0,
                      "basis": ("CANNOT DETERMINE — no calibrated target with "
                                "an interval for this name on this machine")})

    # 3. the book's own drawdown state
    dd = drawdown_state.get("drawdown")
    budget = drawdown_state.get("drawdown_budget")
    if dd is not None and budget:
        halfway = float(dd) <= float(budget) / 2.0
        terms.append({"term": "book_drawdown_state",
                      "z": DRAWDOWN_TILT_Z if halfway else 0.0,
                      "basis": (f"the BOOK is {float(dd):.1%} from its peak "
                                f"against a {float(budget):.0%} budget"
                                + ("; past halfway, so the next loss is the "
                                   "one that flips it (§4)" if halfway else
                                   "; inside the first half of the budget"))})
    else:
        terms.append({"term": "book_drawdown_state", "z": 0.0,
                      "basis": ("CANNOT DETERMINE — the book has no marked NAV "
                                "history yet, so it has no peak to fall from")})

    # 4. typed events (L2)
    terms.append({"term": "typed_events", "z": 0.0,
                  "n_events": int(n_typed_events),
                  "basis": (f"{int(n_typed_events)} typed event(s) since the "
                            f"last review. The term is ZERO BY DECLARATION "
                            f"until lane L2 lands: counting events is not the "
                            f"same as knowing what they imply, and a weight "
                            f"guessed now would be an untested mechanism "
                            f"inside a probability that looks measured.")})

    # 5. the market sensor
    terms.append({"term": "market_sensor_regime", "z": 0.0,
                  "regime": (sensor or {}).get("regime"),
                  "basis": ("PLACEHOLDER (invariant 4 / X4): the NVDA-SPY "
                            "sensor tells us what world we are in and informs "
                            "the read; it does not move the probability until "
                            "its own mapping is pre-registered.")})

    z = sum(float(t["z"]) for t in terms)
    p = max(0.02, min(0.98, _phi(z)))
    return {"probability": round(p, 6), "z_total": round(z, 6),
            "terms": terms,
            "convention": ("p = Phi(sum of declared terms), clipped to "
                           "[0.02, 0.98]. No LLM produces this number.")}


def drawdown_state(book, *, conn=None, db_path=None,
                   nav_path: Sequence | None = None) -> dict:
    """Peak, current NAV, drawdown from peak, and the book's own budget (§4.1).

    Measured on the marked NAV at the close — one row per (book, date) — and
    never intraday, which is the same discipline the marks themselves keep.
    """
    from backend.services import paper_books as PB                 # noqa: PLC0415
    budget = book.strategy.objective.drawdown_budget
    if nav_path is None:
        try:
            nav_path = (PB.nav_series([book.book_id], conn=conn,
                                      db_path=db_path).get(book.book_id) or [])
        except Exception as exc:                                   # noqa: BLE001
            return {"drawdown": None, "drawdown_budget": budget,
                    "why": f"the NAV series could not be read: {exc}"[:200]}
    if not nav_path:
        return {"drawdown": None, "drawdown_budget": budget, "n_marks": 0,
                "why": ("this book has no marked NAV row yet, so it has no "
                        "peak and no drawdown. That is not a drawdown of zero.")}
    peak, peak_date = None, None
    for d, nav in nav_path:
        if peak is None or nav > peak:
            peak, peak_date = nav, d
    last_date, last_nav = nav_path[-1]
    dd = (last_nav / peak - 1.0) if peak else 0.0
    return {"drawdown": round(dd, 6), "drawdown_budget": budget,
            "peak_nav": round(float(peak), 4), "peak_date": peak_date,
            "nav": round(float(last_nav), 4), "as_of": last_date,
            "n_marks": len(nav_path),
            "breach": bool(budget is not None and dd <= float(budget))}


def _prior_for(ticker: str, arm: str, path=None) -> tuple[float | None, str]:
    """Yesterday's probability for the same (book, holding), or None.

    §3.3 asks for the belief-change contract on every review row. On the FIRST
    review of a holding there is no prior and `make_prediction` refuses a
    posterior without one — so the row is written without the pair and says
    so, rather than inventing a prior of 0.5 that would make every first
    review look like a belief that moved.
    """
    from backend.services import belief_state as BS                # noqa: PLC0415
    try:
        rows = BS.read_predictions(path)
    except Exception as exc:                                       # noqa: BLE001
        return None, f"the ledger could not be read: {exc}"[:120]
    mine = [r for r in rows
            if r.get("specialist") == SPECIALIST and r.get("ticker") == ticker
            and r.get("arm") == arm]
    if not mine:
        return None, ("first review of this holding — no prior exists, and a "
                      "prior of 0.5 invented here would make every first "
                      "review look like a belief that moved")
    latest = max(mine, key=lambda r: str(r.get("made_at") or ""))
    return float(latest["probability"]), f"the {latest['made_at']} row"


def review(book, *, bars=None, asof=None, conn=None, db_path=None,
           path=None, targets: Mapping[str, Mapping] | None = None,
           typed_events: Mapping[str, int] | None = None,
           sensor: Mapping[str, Any] | None = None) -> list[dict]:
    """One call per holding, each with its forecast row ALREADY on disk (A3).

    Returns the calls. A holding whose row could not be written does not
    appear — `review_book` collects those refusals for the receipt, because a
    call shown without a graded row is the thing this ordering exists to stop.
    """
    from datetime import date as _date                             # noqa: PLC0415

    from backend.services import belief_state as BS                # noqa: PLC0415
    from backend.services import book_cadence as BC                # noqa: PLC0415

    asof = asof or _date.today()
    ledger = path if path is not None else DEFAULT_LEDGER
    calls, _refusals = _review_inner(
        book, bars=bars, asof=asof, conn=conn, db_path=db_path, ledger=ledger,
        targets=targets, typed_events=typed_events, sensor=sensor,
        BS=BS, BC=BC)
    return calls


def _review_inner(book, *, bars, asof, conn, db_path, ledger, targets,
                  typed_events, sensor, BS, BC):
    from backend.services import paper_books as PB                 # noqa: PLC0415

    if conn is None:
        conn = PB._conn(db_path)
        own = True
    else:
        own = False
    try:
        held = {t: sh for t, sh in BC._positions(conn, book.book_id).items()
                if t != BC.CASH}
        prices, _src = ({}, {})
        if held and bars is not None:
            prices, _src = BC.latest_prices(bars, sorted(held), asof)
        nav = sum(sh * prices.get(t, 0.0) for t, sh in held.items())
        cash = BC._positions(conn, book.book_id).get(BC.CASH, 0.0)
        book_value = nav + cash
        dd = drawdown_state(book, conn=conn, db_path=db_path)
        twin_id, twin_path = _twin_nav(book, conn=conn, db_path=db_path)
    finally:
        if own:
            conn.close()

    calls: list[dict] = []
    refusals: list[dict] = []
    cap = float(book.strategy.construction.max_single_name)
    horizon = int(book.horizon_sessions)
    rate = float(book.strategy.costs.transaction_cost_bps
                 + book.strategy.costs.slippage_bps)
    for ticker in sorted(held):
        px = prices.get(ticker)
        weight = ((held[ticker] * px / book_value)
                  if px and book_value else 0.0)
        terms = probability_terms(
            ticker=ticker, price_path=_price_series(bars, ticker, asof),
            twin_path=twin_path, drawdown_state=dd,
            target=(targets or {}).get(ticker),
            n_typed_events=int((typed_events or {}).get(ticker, 0)),
            sensor=sensor)
        p = float(terms["probability"])
        decision, why = decide_label(p, weight=weight, max_single_name=cap)
        try:
            _check_label(decision, p, weight=weight, max_single_name=cap)
            if not twin_id:
                raise AgencyError(
                    f"{book.book_id} has no control twin, so there is nothing "
                    f"for this call to be a probability ABOUT. A book's number "
                    f"is never shown without its twin's (B3).")
            prior, prior_basis = _prior_for(ticker, book.strategy.strategy_id,
                                            ledger)
            made_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            record = BS.make_prediction(
                ticker=ticker, specialist=SPECIALIST,
                observable=BS.Observable.BEATS_BENCHMARK,
                horizon_days=horizon, probability=p, benchmark=twin_id,
                thesis=(f"{ticker} beats {twin_id} over {horizon} session(s): "
                        f"{why}"),
                counter_thesis=(
                    f"the call is reading the liquidity band and the "
                    f"construction, both of which {twin_id} also has, in which "
                    f"case {ticker}'s excess is noise and the trailing IR is "
                    f"measuring it"),
                next_observable=(
                    "a typed event on this name (lane L2) that moves the "
                    "trailing IR against the twin by more than its own "
                    "dispersion — the prospective form of X2's flip test"),
                model=REVIEW_MODEL, model_version=REVIEW_MODEL_VERSION,
                prompt=f"{REVIEW_MECHANISM}|{book.strategy.fingerprint}",
                input_snapshot={"asof": str(asof), "weight": round(weight, 6),
                                "z_total": terms["z_total"],
                                "fingerprint": book.strategy.fingerprint},
                made_at=made_at,
                prior=prior, posterior=(p if prior is not None else None),
                arm=book.strategy.strategy_id, session_as_of=str(asof),
                mechanism_id=REVIEW_MECHANISM, decision_date=str(asof),
                policy_hash=book.strategy.fingerprint,
                inputs_used={"source": "local daily bars + marked book NAV",
                             "as_of": str(asof),
                             "marked_from": "daily close"},
                control_twin_id=twin_id,
                control_construction=(book.control_construction
                                      or "see the twin's contract"),
                costs_charged=True, cost_rate_bps=rate,
                licence=book.strategy.licence.value,
                notes_text=f"prior basis: {prior_basis}")
            # WRITE, THEN READ BACK, THEN DISPLAY. `append` returns None by
            # house rule, so the proof that the row exists is the row.
            BS.append([record], ledger)
            persisted = _persisted_row(record.prediction_id, ledger, BS)
        except (AgencyError, ValueError) as exc:
            refusals.append({"ticker": ticker, "reason": f"{exc}"[:300],
                             "shown": False})
            continue
        calls.append({
            "ticker": ticker, "decision": decision, "why": why,
            "probability": p, "weight": round(weight, 6),
            "max_single_name": cap,
            "horizon_sessions": horizon,
            "benchmark_twin": twin_id,
            "prediction_id": record.prediction_id,
            "row_made_at": record.made_at,
            "row_hash": persisted["hash"],
            "displayed_after_utc": datetime.now(timezone.utc)
                .isoformat(timespec="seconds"),
            "terms": terms["terms"], "z_total": terms["z_total"],
            "prior": record.prior, "belief_change": record.belief_change,
            "prior_basis": record.notes_text,
            "drawdown_state": dd,
            "limits": LIMITS_SENTENCE,
        })
    return calls, refusals


def row_hash(row: Mapping[str, Any]) -> str:
    """The hash of a persisted forecast row, over the fields that identify the
    CLAIM — not over the whole record, whose resolution fields are filled in
    later by the grader and would make the hash unstable by design."""
    return _sha16({k: row.get(k) for k in (
        "prediction_id", "ticker", "specialist", "observable", "horizon_days",
        "probability", "benchmark", "made_at", "resolves_after", "policy_hash",
        "arm", "prior", "posterior")})


def _persisted_row(prediction_id: str, ledger, BS) -> dict:
    """Read the row back off disk and hash it. Raises if it is not there."""
    rows = [r for r in BS.read_predictions(ledger)
            if r.get("prediction_id") == prediction_id]
    if not rows:
        raise AgencyError(
            f"the forecast row {prediction_id} is not in the ledger after "
            f"append(). The call is NOT shown: a call whose row cannot be read "
            f"back is a call nobody can grade.")
    return {"row": rows[-1], "hash": row_hash(rows[-1])}


def review_book(book, **kw) -> dict:
    """`review` plus the refusals, for a receipt."""
    from datetime import date as _date                             # noqa: PLC0415

    from backend.services import belief_state as BS                # noqa: PLC0415
    from backend.services import book_cadence as BC                # noqa: PLC0415

    asof = kw.pop("asof", None) or _date.today()
    ledger = kw.pop("path", None)
    ledger = ledger if ledger is not None else DEFAULT_LEDGER
    calls, refusals = _review_inner(
        book, bars=kw.pop("bars", None), asof=asof, conn=kw.pop("conn", None),
        db_path=kw.pop("db_path", None), ledger=ledger,
        targets=kw.pop("targets", None), typed_events=kw.pop("typed_events", None),
        sensor=kw.pop("sensor", None), BS=BS, BC=BC)
    if kw:
        raise AgencyError(f"review_book got unexpected argument(s) {sorted(kw)}")
    return {"book_id": book.book_id, "ips_hash": book.ips_hash,
            "as_of": str(asof), "n_calls": len(calls),
            "n_refused": len(refusals),
            "calls": calls, "refused": refusals,
            "vocabulary": list(DECISIONS),
            "ordering": ("every call below was written to the forecast ledger "
                         "and read back BEFORE it was returned; a holding whose "
                         "row could not be written is in `refused` and has no "
                         "call"),
            "limits": LIMITS_SENTENCE}


def review_all(*, bars=None, asof=None, conn=None, db_path=None, path=None,
               origins: Sequence[str] = ("human_text",)) -> dict:
    """Every book a human holds, reviewed. The Morning's `agency_review` step.

    Shadows are NOT reviewed: the review is the agency's advice to a person
    about the book that person chose, and a shadow is graded (B5 writes its
    forecast row on the same clock) without being advised about.
    """
    from datetime import date as _date                             # noqa: PLC0415

    from backend.services import paper_books as PB                 # noqa: PLC0415

    asof = asof or _date.today()
    own = conn is None
    conn = conn or PB._conn(db_path)
    try:
        books = [b for b in PB.list_books(conn=conn, include_twins=False)
                 if b.origin in tuple(origins) and b.status != "retired"]
        out = [review_book(b, bars=bars, asof=asof, conn=conn, path=path)
               for b in books]
    finally:
        if own:
            conn.close()
    return {"as_of": str(asof), "n_books": len(out),
            "n_calls": sum(r["n_calls"] for r in out),
            "n_refused": sum(r["n_refused"] for r in out),
            "books": out,
            "reviewed_origins": list(origins),
            "limits": LIMITS_SENTENCE}


# ===========================================================================
# A4 — PROTECT FIRST
# ===========================================================================
#
# "Drawdown budget per book from the IPS; a breach flips the book to its
# preservation twin's construction, logged, reversible by a human" (A4).
#
# FOUR THINGS THAT ARE NOT OBVIOUS AND ARE THEREFORE ENFORCED
# -----------------------------------------------------------
# 1. **The peak never resets.** Not at an amendment, not at the flip itself,
#    and not at the reversal. A book that breaches, flips and recovers is
#    still measured against its ORIGINAL peak, so a second breach cannot be
#    avoided by the act of flipping. The carried peak lives on the flip rows,
#    so it survives the book id changing.
# 2. **"Preservation twin's construction" means the preservation PERSONALITY's
#    construction.** The control twin (B3) is a random/beta-matched draw used
#    for grading and is never a construction a book can BE. Confusing the two
#    would flip a breached book into a random portfolio.
# 3. **A mutation is a new object.** `Strategy.with_` produces a new frozen
#    contract with a new fingerprint, so the flipped book is a NEW book and
#    the original is retained unmutated at status `flipped`. Both are shown.
# 4. **The engine flips; only a human unflips.** Protect-first is
#    one-directional automatically — CLAUDE.md's "no LLM authority over real
#    capital", extended to paper capital's protective state.
#
# AND THE CONTROL: how often would this rule fire on a book that is doing
# nothing unusual? The same rule, plus random thresholds, run against the
# book's own twin — whose breach rate is what construction-level volatility
# alone does to this shape. A flip that fires no more often than the twin's is
# a protection event that was not informative, and the Regret page reports
# THAT comparison rather than the raw flip count. ("A null owes two tests.")

FLIP_EVENT = "protect_first_flip"

#: Where the flip log lives. `None` means "beside the forecast ledger", which
#: is the same volume `PredictionRecord` is written to — a flip is a receipt,
#: not a log line that can scroll away.
FLIPS_PATH = None

#: How many random thresholds the base-rate control draws, and the band it
#: draws them from as a multiple of the book's own budget. Declared, not tuned:
#: the question is "how often does a rule of roughly this severity fire on
#: noise", and a band chosen after seeing the answer would not be a control.
BASE_RATE_DRAWS = 200
BASE_RATE_BAND = (0.5, 1.5)


def flips_path():
    from backend.services import belief_state as BS                # noqa: PLC0415
    from pathlib import Path                                       # noqa: PLC0415
    if FLIPS_PATH is not None:
        return Path(FLIPS_PATH)
    return Path(BS.LEDGER_DIR) / "protect_first.jsonl"


def read_flips(path=None) -> list[dict]:
    from pathlib import Path                                       # noqa: PLC0415
    p = Path(path) if path is not None else flips_path()
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _write_flips(rows: Sequence[Mapping[str, Any]], path=None) -> None:
    """Rewrite the whole file.

    A reversal writes `reversed_utc` onto the SAME row as the flip it reverses
    (§4.4) — never a second row, which could be read independently of the flip
    and would make a reversed flip look like two events. That is a
    read-modify-write, so it rewrites rather than appends, and it is the one
    file in this programme that is deliberately not append-only.
    """
    from pathlib import Path                                       # noqa: PLC0415
    p = Path(path) if path is not None else flips_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                 encoding="utf-8")


def carried_peak(book, path=None) -> tuple[float | None, str]:
    """The peak this book inherits from its own flip lineage, if any.

    A flip changes the book id (a mutation is a new object), so without this
    the new book would start measuring from its own first mark and the budget
    would silently reset — which is exactly what §4.1 forbids.
    """
    for row in read_flips(path):
        if row.get("to_book_id") == book.book_id and row.get("peak_nav"):
            return float(row["peak_nav"]), (
                f"carried from flip {row['flip_seq']} of {row['book_id']}")
    return None, ""


def breach_check(book, *, conn=None, db_path=None, path=None) -> dict:
    """Is this book past its own drawdown budget at the close? (§4.1)

    `drawdown <= budget` — both negative ratios, so the comparison fires when
    the drawdown is AS BAD OR WORSE than the budget.
    """
    state = drawdown_state(book, conn=conn, db_path=db_path)
    inherited, why = carried_peak(book, path)
    if inherited and state.get("nav"):
        peak = max(float(inherited), float(state.get("peak_nav") or 0.0))
        if peak != state.get("peak_nav"):
            state["peak_nav"] = peak
            state["peak_carried_from"] = why
            state["drawdown"] = round(float(state["nav"]) / peak - 1.0, 6)
    budget = book.strategy.objective.drawdown_budget
    dd = state.get("drawdown")
    state["drawdown_budget"] = budget
    if dd is None or budget is None:
        state["breach"] = False
        state.setdefault("why", "")
        state["why"] = (state["why"] or "") + (
            "" if budget is not None else
            " This book declares no drawdown budget, so protect-first has "
            "nothing to measure against and never fires.")
        return state
    state["breach"] = bool(float(dd) <= float(budget))
    state["distance_to_budget"] = round(float(dd) - float(budget), 6)
    return state


def base_rate_on_twin(book, *, conn=None, db_path=None) -> dict:
    """§4.5 — how often the same rule fires on a book doing nothing unusual.

    Two numbers, printed beside every flip:
    * the SAME budget applied to the control twin's own NAV path;
    * the fraction of RANDOM thresholds in a declared band around the budget
      that would have fired on that path.

    The twin shares the universe band, cadence and costs and carries no
    signal, so its breach rate is protect-first's false-positive rate under
    "nothing is actually wrong, the signal just has this much noise".
    """
    import numpy as np                                             # noqa: PLC0415

    from backend.services import paper_books as PB                 # noqa: PLC0415

    budget = book.strategy.objective.drawdown_budget
    tid = book.control_twin_ids[0] if book.control_twin_ids else None
    if tid is None or budget is None:
        return {"verdict": "CANNOT DETERMINE",
                "why": ("a base rate needs a control twin and a declared "
                        "budget; without both there is nothing to compare the "
                        "flip against")}
    try:
        path = PB.nav_series([tid], conn=conn, db_path=db_path).get(tid) or []
    except Exception as exc:                                       # noqa: BLE001
        return {"verdict": "CANNOT DETERMINE",
                "why": f"the twin's NAV could not be read: {exc}"[:200]}
    if len(path) < 2:
        return {"verdict": "CANNOT DETERMINE", "twin_id": tid,
                "n_twin_marks": len(path),
                "why": ("the twin has fewer than two marks, so it has no "
                        "drawdown path and no base rate. A flip reported "
                        "without one is a fired rule with no false-positive "
                        "rate beside it.")}
    peak = None
    worst = 0.0
    n_breach = 0
    for _d, nav in path:
        peak = nav if peak is None else max(peak, nav)
        dd = nav / peak - 1.0 if peak else 0.0
        worst = min(worst, dd)
        if dd <= float(budget):
            n_breach += 1
    rng = np.random.default_rng(int(book.strategy.fingerprint[:8], 16))
    lo, hi = BASE_RATE_BAND
    draws = rng.uniform(float(budget) * hi, float(budget) * lo, BASE_RATE_DRAWS)
    fired = int(sum(1 for t in draws if worst <= t))
    return {"verdict": "measured on the twin",
            "twin_id": tid, "n_twin_marks": len(path),
            "twin_worst_drawdown": round(worst, 6),
            "twin_sessions_in_breach": n_breach,
            "twin_breach_rate": round(n_breach / len(path), 6),
            "random_threshold_fire_rate": round(fired / BASE_RATE_DRAWS, 6),
            "random_thresholds": {"n": BASE_RATE_DRAWS,
                                  "band_x_budget": list(BASE_RATE_BAND),
                                  "seed": "derived from the book fingerprint"},
            "reading": ("a book whose own breach is not distinguishably more "
                        "frequent than these is a book whose 'protection' "
                        "event was not informative — that comparison, not the "
                        "flip count, is what the Regret page reports")}


def protected_strategy(strategy, *, flip_seq: int):
    """The same book, rebuilt on the PRESERVATION row (§4.2).

    `Strategy.with_` — a mutation is a new strategy, never an edit — so the
    original object survives untouched in the book's history and the new one
    has its own fingerprint.
    """
    from backend.strategy.contract import (Construction, HoldRule, Objective,
                                           Sizing)                 # noqa: PLC0415
    row = TABLE["preservation"]
    fam = HOLD_FAMILY["preservation"]
    params = dict(strategy.engine_params or {})
    params.update({"protect_first": {
        "flip_seq": int(flip_seq),
        "flipped_from": strategy.fingerprint,
        "construction": "the preservation PERSONALITY's row (§1.4), not the "
                        "control twin — a twin is a grading control and never "
                        "a construction a book can be"}})
    return strategy.with_(
        strategy_id=f"{strategy.strategy_id}-PROTECTED-{int(flip_seq)}",
        title=f"{strategy.title} (protected {int(flip_seq)})",
        construction=Construction(rule=strategy.construction.rule, k=row.k,
                                  weighting=strategy.construction.weighting,
                                  max_single_name=row.max_single_name,
                                  gross_cap=row.gross_cap),
        hold=HoldRule(horizon_periods=int(fam["horizon_periods"]),
                      min_hold_periods=int(fam["min_hold_periods"]),
                      roi_ladder=dict(fam["roi_ladder"]),
                      stop_loss=row.stop_loss,
                      scheduled_review_periods=1),
        sizing=Sizing(rule=strategy.sizing.rule, gross_cap=row.gross_cap,
                      notional_usd=strategy.sizing.notional_usd),
        objective=Objective(name=strategy.objective.name,
                            periods_per_year=strategy.objective.periods_per_year,
                            drawdown_budget=row.drawdown_budget,
                            utility="risk_adjusted"),
        engine_params=params,
        parents=tuple(strategy.parents) + (strategy.strategy_id,))


def flip(book, *, state: Mapping[str, Any], bars, asof=None, conn=None,
         db_path=None, path=None) -> dict:
    """Flip a breached book to the preservation construction, and log it.

    Returns the log row. The ORIGINAL book is set to `flipped` and kept; the
    protected one is a new book with `origin="mutation"` carrying the same
    `ips_hash`, so both are shown and neither is edited.
    """
    from datetime import date as _date                             # noqa: PLC0415

    from backend.services import paper_books as PB                 # noqa: PLC0415

    asof = asof or _date.today()
    rows = read_flips(path)
    seq = 1 + sum(1 for r in rows if r.get("lineage") == (book.ips_hash
                                                          or book.book_id))
    new_strategy = protected_strategy(book.strategy, flip_seq=seq)
    new_book, twins = PB.create(
        new_strategy, cadence=book.cadence, origin="mutation",
        origin_text=(f"protect-first flip on {asof}, drawdown "
                     f"{float(state['drawdown']):.2%} vs budget "
                     f"{float(state['drawdown_budget']):.2%}"),
        ips_hash=book.ips_hash, shadow=book.shadow, bars=bars, asof=asof,
        conn=conn, db_path=db_path)
    PB.set_status(book.book_id, "flipped", conn=conn, db_path=db_path)
    row = {
        "event": FLIP_EVENT,
        "lineage": book.ips_hash or book.book_id,
        "book_id": book.book_id,
        "to_book_id": new_book.book_id,
        "ips_hash": book.ips_hash,
        "flip_seq": seq,
        "triggered_utc": _now(),
        "session_as_of": str(asof),
        "nav_at_trigger": state.get("nav"),
        "peak_nav": state.get("peak_nav"),
        "peak_date": state.get("peak_date"),
        "drawdown_at_trigger": state.get("drawdown"),
        "drawdown_budget": state.get("drawdown_budget"),
        "from_strategy_fingerprint": book.strategy.fingerprint,
        "to_strategy_fingerprint": new_strategy.fingerprint,
        "to_construction": "preservation",
        "base_rate_control": base_rate_on_twin(book, conn=conn,
                                               db_path=db_path),
        "reversible": True,
        "reversed_utc": None,
        "reversed_by": None,
        "twins_of_protected_book": [t.book_id for t in twins],
        "note": ("the peak is NOT reset by this flip: a book that breaches, "
                 "flips and recovers is still measured against its original "
                 "peak, so a second breach cannot be avoided by flipping"),
    }
    _write_flips(list(rows) + [row], path)
    logger.info("protect-first: %s flipped to %s at drawdown %s",
                book.book_id, new_book.book_id, state.get("drawdown"))
    return row


def unflip(*, book_id: str | None = None, flip_seq: int | None = None,
           by: str = "human", conn=None, db_path=None, path=None) -> dict:
    """Reverse a flip. A HUMAN action, and the engine never takes it (§4.4).

    (a) restores the pre-flip book (the retained object, not a re-derivation),
    (b) writes `reversed_utc`/`reversed_by` onto the SAME row, and
    (c) does NOT reset `peak_nav` — a reversed flip that breaches again
        immediately is a real second breach, not a bug.
    """
    from backend.services import paper_books as PB                 # noqa: PLC0415

    rows = read_flips(path)
    live = [r for r in rows
            if r.get("reversed_utc") is None
            and (book_id is None or book_id in (r.get("book_id"),
                                                r.get("to_book_id")))
            and (flip_seq is None or int(r.get("flip_seq", 0)) == int(flip_seq))]
    if not live:
        raise AgencyError(
            f"no un-reversed protect-first flip matches "
            f"book_id={book_id!r} flip_seq={flip_seq!r}. A reversal of a flip "
            f"that did not happen would restore a construction nobody left.")
    if len(live) > 1:
        raise AgencyError(
            f"{len(live)} un-reversed flips match; name the `flip_seq`. "
            f"Reversing 'the flip' when there are two is a guess about which "
            f"protective state the human meant to leave.")
    row = live[0]
    peak_before = row.get("peak_nav")
    PB.set_status(row["to_book_id"], "retired", conn=conn, db_path=db_path)
    PB.set_status(row["book_id"], "holding", conn=conn, db_path=db_path)
    row["reversed_utc"] = _now()
    row["reversed_by"] = str(by)
    row["peak_nav"] = peak_before        # explicitly unchanged, see (c)
    row["reversal_note"] = (
        "the pre-flip book is restored to `holding` and the protected book is "
        "retired. `peak_nav` is unchanged: the drawdown that fired this flip "
        "is still the drawdown, and an immediate re-breach is a real one.")
    _write_flips(rows, path)
    return row


#: Which origins protect-first watches. A shadow is protected too: it is the
#: counterfactual of a CHOICE, and a counterfactual run without the protection
#: the chosen book has is a comparison between two different policies.
PROTECTED_ORIGINS_NOTE = (
    "every book created from an IPS — the one a human held and the two "
    "shadows — is watched, because a shadow run without the protection the "
    "chosen book has is a comparison between two different policies")


def protect_first_pass(*, asof=None, bars=None, conn=None, db_path=None,
                       path=None) -> dict:
    """Check every IPS book at the close; flip the ones in breach (§4).

    One pass per session, on the marked NAV, never intraday.
    """
    from datetime import date as _date                             # noqa: PLC0415

    from backend.services import paper_books as PB                 # noqa: PLC0415

    asof = asof or _date.today()
    own = conn is None
    conn = conn or PB._conn(db_path)
    try:
        books = [b for b in PB.list_books(conn=conn, include_twins=False)
                 if b.ips_hash and b.status == "holding"]
        checked: list[dict] = []
        flipped: list[dict] = []
        for book in books:
            state = breach_check(book, conn=conn, db_path=db_path, path=path)
            already = (book.strategy.construction.k == TABLE["preservation"].k
                       and book.strategy.construction.max_single_name
                       == TABLE["preservation"].max_single_name)
            entry = {"book_id": book.book_id, "origin": book.origin,
                     "shadow": book.shadow,
                     "drawdown": state.get("drawdown"),
                     "drawdown_budget": state.get("drawdown_budget"),
                     "breach": bool(state.get("breach")),
                     "why": state.get("why"),
                     "base_rate_control": base_rate_on_twin(
                         book, conn=conn, db_path=db_path)}
            if state.get("breach") and already:
                entry["flipped"] = False
                entry["reason"] = (
                    "already at the preservation construction; there is no "
                    "more conservative row to flip to, and re-flipping would "
                    "mint a book identical to this one")
            elif state.get("breach"):
                if bars is None:
                    entry["flipped"] = False
                    entry["reason"] = (
                        "REFUSED: a flip creates a new book, which needs a "
                        "control twin, which needs bars to draw from. The "
                        "breach is recorded and the book is NOT flipped.")
                else:
                    row = flip(book, state=state, bars=bars, asof=asof,
                               conn=conn, db_path=db_path, path=path)
                    entry["flipped"] = True
                    entry["flip"] = row
                    flipped.append(row)
            else:
                entry["flipped"] = False
            checked.append(entry)
    finally:
        if own:
            conn.close()
    return {"as_of": str(asof), "n_checked": len(checked),
            "n_flipped": len(flipped), "books": checked,
            "watched": PROTECTED_ORIGINS_NOTE,
            "reversal": ("only a human reverses a flip: POST "
                         "/api/control/agency/unflip. The engine is "
                         "one-directional by design."),
            "limits": LIMITS_SENTENCE}


__all__ = ["AGENCY_SIGNAL_DEFAULT", "AgencyError", "BANDS",
           "BASE_RATE_DRAWS", "BUY_MORE_ABOVE", "CADENCE_FOR_REBALANCE",
           "CONSTRAINT_RE", "DECISIONS", "ESG_CATEGORIES", "FLIP_EVENT",
           "HOLD_FAMILY", "IPS", "IPS_SCHEMA", "LIMITS_SENTENCE",
           "MAX_CASH_FOR", "MIN_SENTENCE_CHARS", "N_QUESTIONS", "Option",
           "PERSONALITIES", "PersonalityRow", "QUESTIONNAIRE_VERSION",
           "QUESTIONS", "SELL_BELOW", "TABLE", "amendment_kind",
           "base_rate_on_twin", "breach_check", "build_strategy",
           "carried_peak", "cash_floor_for", "decide_label", "draft_prose",
           "drawdown_state", "eligible_symbols",
           "expected_drawdown_at_budget", "flip", "flips_path", "hold",
           "hold_rule_words", "intake", "ips_dir", "ips_hash", "load_ips",
           "neighbours", "numeric_fields", "parse_constraints",
           "personality_for", "probability_terms", "propose",
           "propose_payload", "protect_first_pass", "protected_strategy",
           "read_flips", "review", "review_all", "review_book", "row_hash",
           "save_ips", "score_questionnaire", "supported_signals",
           "template_prose", "unexplained_numbers", "unflip",
           "validate_document"]
