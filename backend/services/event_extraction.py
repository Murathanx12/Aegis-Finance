"""L2 -- the extraction contract: one document in, one typed row or a refusal out.

    from backend.services import event_extraction as ex

    ex.user_prompt(scope="NVDA", scope_kind="ticker", document_date="2026-09-12",
                   source_feed="alpaca_benzinga_news", title=..., body=...)
    ex.parse_reply(raw_text, document=body)      # -> TypedEventRow | Refusal
    ex.extract(doc)                              # the whole call, through local_gguf

WHAT IS FROZEN HERE
===================
`docs/research_notes/2026-09-11/spec_events_and_calibration.md` sections 2.1-2.5:
the JSON Schema (draft-07), the system prompt verbatim, the user template, the
one-document-one-row rule and the refusal shape. `PROMPT_HASH` covers the wire
system prompt, the user template and the canonical schema together; every typed
row carries it beside `vocabulary_hash`, so a row can always answer "which prompt
and which vocabulary produced you" without a lookup table.

THE LANGUAGE PIN IS NOT APPLIED HERE, AND THAT IS DELIBERATE
============================================================
The spec's rule 9 ends "Respond in English only." -- which is
`llm_language.LANGUAGE_PIN`, and the spec says so: the string is shown there to
display the wire prompt, not to be typed twice. The pin AND the >10% non-Latin
refusal are applied centrally in `model_provider.complete` (it calls
`_lang.pin(system)` on the way out and `_lang.refuse` on the way back), which is
the path `free_inference.complete` uses. So `SYSTEM_PROMPT` below stops at "no
additional keys." and `wire_system()` reconstructs what the model actually sees.
Pinning here as well would send the sentence twice and change the hash of a
prompt nobody edited.

THE VALIDATOR THAT ACTUALLY RUNS IS THE HAND VALIDATOR
======================================================
The spec asks for `jsonschema.validate` "a real validator, not ad-hoc key
checks". `jsonschema` is NOT installed in this environment and is not in
`requirements.txt` (checked 2026-09-13), so a module that only called it would
either crash or -- worse -- skip validation and pass novel strings through. Both
paths exist here: `jsonschema` is used when importable, and `_hand_errors` is the
live path otherwise. It is `_hand_errors` that the tests exercise, because a
guard on a dormant branch protects nothing (the `ANTHROPIC_API_KEY` lesson, with
the sign flipped). `validator_in_use()` says which one ran, and every receipt
prints it.

WHAT A TYPED ROW IS NOT
=======================
It is a FEATURE. Nothing here sizes, ranks or orders; `direction` is the
document's sign relative to the named scope entity, not a position. Invariant 5:
the LLM classifies into enums, the engine allocates.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.services import event_vocabulary as vocab
from backend.services import llm_language as _lang

#: The document body is truncated before it reaches the prompt. Spec section 2.3.
BODY_CHARS = 2000

#: `evidence_span`'s ceiling, from the schema. A longer span is a schema refusal.
EVIDENCE_CHARS = 400

#: The backend this contract is written for. Local, free, and NOT
#: `llm_analyzer._call_llm`, which is DeepSeek-specific (spec section 2).
BACKEND = "local_gguf"

PURPOSE = "l2_event_extraction"

#: The refusal classes, spec section 2.5. `no_event` is NOT among them: a
#: `no_event` row is a successful classification and is written like any other,
#: because it is how L2 measures the corpus's genuine event rate. Dropping it
#: would make the denominator silently wrong.
REFUSAL_CLASSES = ("REFUSED_LANGUAGE", "REFUSED_UNPARSEABLE", "REFUSED_SCHEMA")

#: How much of an unparseable reply is kept for the regression corpus.
RAW_KEEP = 1000


# --------------------------------------------------------------------- schema

def schema() -> dict:
    """The draft-07 schema, with the enum GENERATED from the frozen vocabulary.

    Typing the 40 ids a second time is how the schema and the vocabulary drift.
    """
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "aegis://schemas/typed_event_row.json",
        "title": "AegisTypedEventRow",
        "type": "object",
        "additionalProperties": False,
        "required": ["event_type", "direction", "magnitude_bucket", "confidence",
                     "evidence_span"],
        "properties": {
            "event_type": {"type": "string", "enum": list(vocab.EVENT_TYPES)},
            "direction": {"type": "integer", "enum": list(vocab.DIRECTIONS)},
            "magnitude_bucket": {"type": "string",
                                 "enum": list(vocab.MAGNITUDE_BUCKETS)},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "evidence_span": {
                "type": "string", "minLength": 0, "maxLength": EVIDENCE_CHARS,
                "description": (
                    "A verbatim substring of the input document (<=400 chars) that "
                    "justifies event_type and direction. Empty string only when "
                    "event_type is no_event."),
            },
        },
    }


SCHEMA: dict = schema()


# --------------------------------------------------------------------- prompts

#: Spec section 2.2, verbatim, MINUS rule 9's closing "Respond in English only."
#: -- that sentence is `llm_language.LANGUAGE_PIN` and is appended centrally on
#: the wire. `wire_system()` puts it back.
SYSTEM_PROMPT = """You are a financial-news event classifier. You read one news document about
one named entity (a company ticker, or a macro topic) and output exactly ONE
JSON object matching the schema you have been given. You classify into fixed
categories only — you never write free-form analysis, never predict future
prices, never give investment advice, and never add fields not in the schema.

Rules:
1. event_type must be exactly one value from the enum. If nothing in the
   document is a dated, decision-relevant event about the named entity, use
   "no_event".
2. direction is -1, 0, or +1, relative to the NAMED ENTITY ONLY, never the
   broad market. Use 0 when the event is real but has no directional
   implication by itself (e.g. a routine, unchanged dividend declaration).
   Never invent a fourth value. If you are unsure, still choose the single
   most likely direction and reflect your uncertainty in confidence instead.
3. magnitude_bucket is your prior expectation of how big a same-scope price
   reaction an event of THIS TYPE typically produces over the next 1-2
   trading sessions, not a forecast about today's specific facts:
   NEGLIGIBLE < 0.5%, SMALL 0.5-2%, MODERATE 2-5%, LARGE 5-10%, EXTREME >=10%
   (expected absolute return).
4. confidence is a number from 0 to 1: your probability that the event_type
   AND direction you chose together are the correct reading of the document.
5. evidence_span is a verbatim substring of the document (at most 400
   characters) that most directly supports your event_type and direction
   choice. Use an empty string only when event_type is "no_event".
6. A sarcastic, speculative, or hedged headline is read for its LITERAL
   claim, not its tone — quote the hedge language (e.g. "considering",
   "reportedly", "sources say") in evidence_span and lower confidence
   accordingly; do not change event_type just because a claim is uncertain.
7. A denial ("X is NOT acquiring Y") is NOT the event it denies. Classify the
   denial itself: if a denial is newsworthy corrective information, still
   pick the nearest matching event_type but set direction to the OPPOSITE of
   what the rumor implied (a denied acquisition rumor is a mild NEGATIVE for
   the would-be target, since an expected catalyst was removed), and quote
   the negation explicitly in evidence_span.
8. An article that only RECAPS an event that was already reported on an
   earlier date (no new fact, just a summary or "as previously announced")
   is "no_event" — the event was already extracted from the original article
   on its original date; extracting it again from a recap double-counts it.
9. Output EXACTLY the JSON object. No markdown fences, no explanation before
   or after, no additional keys."""

#: The INTER-RATER control's second prompt (roadmap L2: "a second prompt hash on
#: a 500-row sample, kappa printed"). Same contract, same enums, different
#: wording and a different rule order -- which is the point: a kappa between two
#: paraphrases of one contract measures how much of the reading is the CONTRACT
#: and how much is the phrasing. It must never introduce a rule the other lacks;
#: `test_event_extraction.py` pins that both carry all nine.
SYSTEM_PROMPT_B = """You classify financial news. Input: one document about one named entity (a
company ticker or a macro topic). Output: exactly one JSON object matching the
given schema - no prose, no price predictions, no advice, no extra fields.

How to fill each field:
- event_type: exactly one enum value. Nothing dated and decision-relevant about
  the named entity in this document means "no_event".
- direction: -1, 0 or +1, and always about the NAMED ENTITY, never the broad
  market. 0 means the event is real but carries no directional implication on
  its own (an unchanged routine dividend, say). There is no fourth value: when
  unsure, pick the single most likely sign and put the uncertainty in
  confidence.
- magnitude_bucket: what an event of THIS TYPE typically does to the same-scope
  price over the next one or two sessions - a prior about the type, not a
  forecast about today. NEGLIGIBLE < 0.5%, SMALL 0.5-2%, MODERATE 2-5%,
  LARGE 5-10%, EXTREME >= 10% expected absolute return.
- confidence: 0 to 1, your probability that the event_type AND direction you
  chose are together the right reading.
- evidence_span: up to 400 characters copied verbatim from the document,
  whichever passage most directly supports your choice. Empty only for
  "no_event".

Three readings that are easy to get wrong:
- Tone is not content. Sarcasm, speculation and hedging do not change
  event_type; quote the hedging words in evidence_span and lower confidence.
- A denial is not the event denied. Classify the denial: keep the nearest
  event_type, set direction to the opposite of what the rumor implied (a denied
  takeover rumor removes an expected catalyst), and quote the negation.
- A recap is not news. An article that only restates something already reported
  on an earlier date ("as previously announced") is "no_event"; the original
  article's own date already carried it.

Emit the JSON object alone: no markdown fences, nothing before or after it, no
keys outside the schema."""

PROMPTS: dict[str, str] = {"A": SYSTEM_PROMPT, "B": SYSTEM_PROMPT_B}

#: Spec section 2.3.
USER_TEMPLATE = """Entity: {scope}  (type: {scope_kind})
Document date: {document_date}
Document source: {source_feed}
Document title: {title}
Document body (may be truncated):
{body}

Classify this document about {scope} per your instructions. Output the JSON
object only."""


def wire_system(variant: str = "A") -> str:
    """Exactly what the model sees, pin included.

    Used for the hash and for a receipt. The call path does NOT use it: it passes
    the unpinned prompt to `free_inference.complete`, which pins centrally.
    """
    return _lang.pin(PROMPTS[variant])


def prompt_hash(variant: str = "A") -> str:
    """sha256 over (wire system prompt, user template, canonical schema).

    All three, because a schema edit changes what the model was asked as surely
    as a prompt edit does, and a row that carries only a prompt hash could not
    tell the two apart.
    """
    payload = json.dumps(
        {"system": wire_system(variant), "user_template": USER_TEMPLATE,
         "schema": SCHEMA},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


PROMPT_HASH: str = prompt_hash("A")
PROMPT_HASH_B: str = prompt_hash("B")


def user_prompt(*, scope: str, scope_kind: str, document_date: str,
                source_feed: str, title: str, body: str = "") -> str:
    """One document rendered into the frozen template.

    `document_date` is the PIT anchor and is never omitted -- an empty one is a
    refusal here rather than a blank line the model fills in from its own idea of
    "now".
    """
    if not str(document_date or "").strip():
        raise ValueError(
            "REFUSED: document_date is the PIT anchor of the extraction prompt and "
            "cannot be empty. A model asked to classify an undated document dates "
            "it from its own training, which is exactly the lookahead L3 measures.")
    if scope_kind not in ("ticker", "macro_topic"):
        raise ValueError(f"scope_kind must be 'ticker' or 'macro_topic', not {scope_kind!r}")
    return USER_TEMPLATE.format(
        scope=scope, scope_kind=scope_kind, document_date=document_date,
        source_feed=source_feed, title=(title or "").strip(),
        body=(body or "").strip()[:BODY_CHARS])


# ------------------------------------------------------------------ the rows

@dataclass(frozen=True)
class TypedEventRow:
    """One graded row. Numeric by construction: every field is an enum, a sign,
    an ordinal bucket, a probability, or a quoted substring."""

    event_type: str
    direction: int
    magnitude_bucket: str
    confidence: float
    evidence_span: str
    prompt_hash: str
    vocabulary_hash: str
    #: WHICH vocabulary the hash belongs to. A hash says which TABLE; a version
    #: says which table a reader should go looking for, and the two together are
    #: what makes a corpus typed across a vocabulary change still readable.
    vocabulary_version: int = vocab.VOCABULARY_VERSION
    #: True when `evidence_span` really is a substring of the document shown.
    #: MEASURED, not enforced: the spec asks for a verbatim span but does not
    #: make a paraphrase a refusal, and refusing one would throw away an
    #: otherwise-correct classification. A rate that climbs is visible instead.
    evidence_span_verbatim: bool | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Refusal:
    """A refusal is a FINDING. It carries the reason, and enough of the reply to
    put in the regression corpus."""

    reason: str
    detail: str
    raw: str = ""
    errors: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ validation

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def strip_fences(text: str) -> str:
    """Spec section 2.5 step 1. Fences only -- no other repair, ever."""
    out = (text or "").strip()
    out = _FENCE.sub("", out)
    return out.strip()


def _hand_errors(obj: Any) -> list[str]:
    """The schema, checked by hand. THE LIVE PATH (see the module docstring).

    Mirrors `SCHEMA` field by field rather than paraphrasing it: required keys,
    no additional keys, enum membership, integer-not-bool for `direction`,
    numeric range for `confidence`, and the length ceiling on `evidence_span`.
    """
    if not isinstance(obj, dict):
        return [f"root: expected an object, got {type(obj).__name__}"]
    errs: list[str] = []
    props = SCHEMA["properties"]
    for key in SCHEMA["required"]:
        if key not in obj:
            errs.append(f"{key}: required and missing")
    for key in obj:
        if key not in props:
            errs.append(f"{key}: additionalProperties is false and this key is not in the schema")
    et = obj.get("event_type")
    if "event_type" in obj:
        if not isinstance(et, str):
            errs.append("event_type: expected a string")
        elif et not in props["event_type"]["enum"]:
            errs.append(f"event_type: {et!r} is not one of the {vocab.N_TYPES} frozen ids")
    if "direction" in obj:
        d = obj["direction"]
        if isinstance(d, bool) or not isinstance(d, int):
            errs.append("direction: expected an integer -1, 0 or +1")
        elif d not in props["direction"]["enum"]:
            errs.append(f"direction: {d!r} is not -1, 0 or +1 -- there is no fourth value")
    if "magnitude_bucket" in obj:
        m = obj["magnitude_bucket"]
        if m not in props["magnitude_bucket"]["enum"]:
            errs.append(f"magnitude_bucket: {m!r} is not one of {vocab.MAGNITUDE_BUCKETS}")
    if "confidence" in obj:
        c = obj["confidence"]
        if isinstance(c, bool) or not isinstance(c, (int, float)):
            errs.append("confidence: expected a number in [0, 1]")
        elif not (0.0 <= float(c) <= 1.0):
            errs.append(f"confidence: {c!r} is outside [0, 1]")
    if "evidence_span" in obj:
        s = obj["evidence_span"]
        if not isinstance(s, str):
            errs.append("evidence_span: expected a string")
        elif len(s) > EVIDENCE_CHARS:
            errs.append(f"evidence_span: {len(s)} characters, ceiling is {EVIDENCE_CHARS}")
    return errs


def _jsonschema_errors(obj: Any) -> list[str] | None:
    """The library's verdict, or `None` when the library is absent."""
    try:
        import jsonschema
    except ImportError:
        return None
    validator = jsonschema.Draft7Validator(SCHEMA)
    return [f"{'.'.join(str(p) for p in e.path) or 'root'}: {e.message}"
            for e in sorted(validator.iter_errors(obj), key=lambda e: list(e.path))]


def validator_in_use() -> str:
    """"jsonschema" or "hand". A receipt prints it: which validator ran is the
    difference between a checked enum and a hoped-for one."""
    return "hand" if _jsonschema_errors({}) is None else "jsonschema"


def schema_errors(obj: Any) -> list[str]:
    """Every reason `obj` is not a typed row, or `[]`.

    Both validators run when both are available, and their union is returned: two
    validators that disagree is a fact worth surfacing, and a union can only be
    stricter.
    """
    hand = _hand_errors(obj)
    lib = _jsonschema_errors(obj)
    if lib is None:
        return hand
    return hand + [e for e in lib if e not in hand]


# ------------------------------------------------------------------ the parser

def parse_reply(raw: str, *, document: str | None = None, variant: str = "A",
                provider: str = BACKEND) -> TypedEventRow | Refusal:
    """The reply as a typed row, or a refusal naming its class.

    Spec section 2.5, in its order and for its reasons:

    1. strip fences and whitespace;
    2. the LANGUAGE check FIRST, before any parsing -- a Chinese reply that
       happens to be valid JSON is still not the answer that was asked for, and
       parsing it first would record it as a success;
    3. `json.loads`;
    4. schema validation;

    and no repair and no retry at any step. The caller falls back to the
    deterministic path that already exists.
    """
    text = strip_fences(raw)
    if _lang.refuse(provider, PURPOSE, text):
        return Refusal(
            reason="REFUSED_LANGUAGE",
            detail=(f"{_lang.non_latin_share(text):.0%} of the letters are non-Latin "
                    f"(bar is {_lang.NON_LATIN_BAR:.0%}). Discarded, not repaired and "
                    "not retried."),
            raw=text[:RAW_KEEP])
    if not text:
        return Refusal(reason="REFUSED_UNPARSEABLE",
                       detail="the reply was empty after fences and whitespace were stripped",
                       raw="")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return Refusal(reason="REFUSED_UNPARSEABLE", detail=f"json.loads: {exc}",
                       raw=text[:RAW_KEEP])
    errs = schema_errors(obj)
    if errs:
        return Refusal(reason="REFUSED_SCHEMA",
                       detail="; ".join(errs), raw=text[:RAW_KEEP],
                       errors=tuple(errs))
    span = str(obj["evidence_span"])
    verbatim = None if document is None else (span in document if span else True)
    return TypedEventRow(
        event_type=str(obj["event_type"]), direction=int(obj["direction"]),
        magnitude_bucket=str(obj["magnitude_bucket"]),
        confidence=float(obj["confidence"]), evidence_span=span,
        prompt_hash=prompt_hash(variant), vocabulary_hash=vocab.VOCABULARY_HASH,
        vocabulary_version=vocab.VOCABULARY_VERSION,
        evidence_span_verbatim=verbatim)


# ------------------------------------------------------------------ the call

def extract(*, scope: str, scope_kind: str, document_date: str, source_feed: str,
            title: str, body: str = "", backend: str = BACKEND, variant: str = "A",
            max_tokens: int = 320, temperature: float = 0.0,
            complete=None) -> tuple[TypedEventRow | Refusal, dict]:
    """One document through the local reader. Returns `(row_or_refusal, usage)`.

    `complete` is injectable so the tests can pin the contract without a model;
    the default is `free_inference.complete`, which owns the price table, the
    telemetry row, the language pin and the non-Latin refusal.

    A `ProviderRefusal` (the server is down, the model is undeclared) is NOT
    caught: it is not a property of the document, it is the run being impossible,
    and the job that calls this probes first and refuses by name.
    """
    from backend.services.model_provider import LanguageRefused

    if complete is None:
        from backend.services.free_inference import complete as complete_
        complete = complete_
    prompt = user_prompt(scope=scope, scope_kind=scope_kind,
                         document_date=document_date, source_feed=source_feed,
                         title=title, body=body)
    document = f"{title}\n{body}"
    try:
        reply = complete(backend, prompt, system=PROMPTS[variant], max_tokens=max_tokens,
                         temperature=temperature, purpose=PURPOSE)
    except LanguageRefused as exc:
        # The wire already counted the refusal and the tokens it burned; this
        # turns it into the row-level class the receipt counts by.
        return (Refusal(reason="REFUSED_LANGUAGE", detail=str(exc),
                        raw=str(getattr(getattr(exc, "reply", None), "text", ""))[:RAW_KEEP]),
                {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
    usage = {"tokens_in": int(getattr(reply, "tokens_in", 0) or 0),
             "tokens_out": int(getattr(reply, "tokens_out", 0) or 0),
             "cost_usd": float(getattr(reply, "cost_usd", 0.0) or 0.0),
             "latency_s": float(getattr(reply, "latency_s", 0.0) or 0.0)}
    return parse_reply(getattr(reply, "text", ""), document=document,
                       variant=variant, provider=backend), usage


def declaration() -> dict:
    """What every L2 receipt prints about the contract it ran under."""
    return {
        "backend": BACKEND,
        "purpose_tag": PURPOSE,
        "prompt_hash_A": PROMPT_HASH,
        "prompt_hash_B": PROMPT_HASH_B,
        "prompt_hash_covers": "wire system prompt + user template + canonical schema",
        "language_pin": ("applied CENTRALLY in model_provider.complete, never at this "
                         "call site; wire_system() shows the pinned text"),
        "validator": validator_in_use(),
        "body_chars": BODY_CHARS,
        "evidence_chars": EVIDENCE_CHARS,
        "refusal_classes": list(REFUSAL_CLASSES),
        "no_event_is_not_a_refusal": (
            "a no_event row is a SUCCESSFUL classification and is written like any "
            "other row -- it is how L2 measures the corpus's genuine event rate, and "
            "dropping it would make the denominator silently wrong"),
        "one_row_per_document": (
            "spec section 2.4: the DOMINANT event only. v1's schema has no "
            "multi-event shape, and additionalProperties:false forbids smuggling one in"),
        "vocabulary": vocab.declaration(),
    }
