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


__all__ = ["AgencyError", "BANDS", "CONSTRAINT_RE", "ESG_CATEGORIES",
           "HOLD_FAMILY", "IPS", "IPS_SCHEMA", "LIMITS_SENTENCE",
           "MAX_CASH_FOR", "N_QUESTIONS", "PERSONALITIES", "QUESTIONS",
           "QUESTIONNAIRE_VERSION", "PersonalityRow", "TABLE",
           "amendment_kind", "cash_floor_for", "draft_prose", "intake",
           "ips_hash", "numeric_fields", "parse_constraints",
           "personality_for", "score_questionnaire", "template_prose",
           "unexplained_numbers", "validate_document"]
