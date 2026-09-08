"""Read stored documents with a FREE model and emit typed rows -- never prose.

    from backend.services.local_review import review_batch, SCHEMA
    rows, receipt = review_batch(docs, backend="local_gguf")

WHAT COMES OUT
==============
One `ReviewRow` per document, always. Never a paragraph, never a list of bullet
points, and never nothing: a document the model cannot answer about produces a
row with `status` in `REFUSALS` and a reason, which is a DIFFERENT fact from a
document that was never reviewed. That distinction is the whole reason the row
exists -- a batch that silently drops what it could not parse reports a
precision it did not earn, on a denominator it quietly shrank.

THE HARD LIMIT
==============
**No output of this module may reach a size, a stop or an order.** It reaches a
row. That is canon (`CLAUDE.md`, `AEGIS_STRATEGIC_INVARIANTS`), it is not a
style preference, and it is why nothing here returns a weight, a quantity or a
price. NIGHT-3 settled the underlying question on 16,320 graded decisions: the
LLM does not earn a role in stock selection (M1 t 0.04, M2 t 0.93), and
temperature 0.7 flipped 21.6% of its own answers. What it may do is turn text
into a structured claim that the engine then MEASURES.

WHY A CLOSED VOCABULARY AND A REFUSAL BRANCH
============================================
An open-ended "what happened here?" produces a fluent answer for every document,
including the ones with no answer in them -- which is the failure mode that
matters, because those are exactly the documents a model will invent for. So the
prompt names a closed set of event types AND an explicit `NO_EVENT` escape, and
`test_local_review.py` plants a null document that must come back refused. A
known-answer battery with no null in it cannot tell a working extractor from a
confident one.

CONFIDENCE IS THE MODEL'S, AND IT IS NOT EVIDENCE
=================================================
`confidence` is recorded because a calibration curve needs it, and it is
explicitly NOT a probability until something has plotted it against outcomes.
Invariant 20: confidence is coverage-normalised, shrinks toward the base rate by
evidence quality, and never grows with news volume. Nothing here does that
normalisation; it records the raw number so the normalisation can be measured
later rather than assumed now.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field

from backend.services import free_inference as fi
from backend.services.model_provider import ProviderRefusal

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class EmptyBatch(ValueError):
    """A throughput receipt was asked for over ZERO documents.

    `review_one` deliberately never raises -- a failed document is a ROW, which
    is the whole design. So the one thing that must refuse sits a level up: a
    receipt computed over an empty batch would print `docs_per_hour`, a wall
    clock and a DeepSeek counterfactual for a run that reviewed nothing, and a
    reader would take the zeros for a result. A throughput number with no
    denominator is not a small number; it is not a number.
    """

#: The closed vocabulary. A model asked for a free-text label returns a new
#: label every few documents and the column stops being groupable.
EVENT_TYPES = (
    "EARNINGS", "GUIDANCE", "MERGER_ACQUISITION", "REGULATORY_LEGAL",
    "PRODUCT_LAUNCH", "MANAGEMENT_CHANGE", "CAPITAL_RAISE", "BUYBACK_DIVIDEND",
    "SUPPLY_OPERATIONS", "ANALYST_ACTION", "MACRO_ONLY", "NO_EVENT",
)

DIRECTIONS = ("POSITIVE", "NEGATIVE", "UNCLEAR")

#: Every way a row can fail to be an extraction. Each is a ROW, never a gap.
REFUSALS = (
    "REFUSED_NO_EVENT",       # the model looked and says there is nothing
    "REFUSED_UNPARSEABLE",    # no JSON object in the reply
    "REFUSED_SCHEMA",         # JSON, but not this schema
    "REFUSED_LANGUAGE",       # the >10% non-Latin bar; not repaired, not retried
    "REFUSED_PROVIDER",       # the backend never answered
    "REFUSED_EMPTY_DOC",      # nothing was sent; the model is not at fault
)

SCHEMA: dict[str, object] = {
    "schema_version": SCHEMA_VERSION,
    "fields": {
        "event_type": list(EVENT_TYPES),
        "entity": "the company or ticker the event is ABOUT, or null",
        "direction": list(DIRECTIONS),
        "horizon_days": "integer 1-250, the model's own guess at when it resolves",
        "confidence": "float 0-1, the MODEL's confidence; not a probability",
        "evidence_quote": "<=200 chars quoted VERBATIM from the document",
    },
}

_SYSTEM = (
    "You extract ONE structured record from a news document. You return JSON and "
    "nothing else: no preamble, no markdown fence, no explanation. "
    "If the document does not describe a specific, company-level financial event, "
    'you MUST return {"event_type": "NO_EVENT"} rather than guessing. '
    "Returning NO_EVENT for a document with no event in it is a CORRECT answer "
    "and is preferred to a plausible invention. "
    "`evidence_quote` must be copied verbatim from the document; if you cannot "
    "quote it, the event is not in the document."
)


def build_prompt(text: str, *, max_chars: int = 6000) -> str:
    body = (text or "")[:max_chars]
    return (
        "DOCUMENT:\n"
        "-----\n"
        f"{body}\n"
        "-----\n\n"
        "Return exactly this JSON object:\n"
        "{\n"
        f'  "event_type": one of {list(EVENT_TYPES)},\n'
        '  "entity": string or null,\n'
        f'  "direction": one of {list(DIRECTIONS)},\n'
        '  "horizon_days": integer between 1 and 250,\n'
        '  "confidence": number between 0 and 1,\n'
        '  "evidence_quote": string copied verbatim from the document, '
        "max 200 characters\n"
        "}"
    )


@dataclass
class ReviewRow:
    """One document, one row. `status == "OK"` is the only extraction."""
    doc_id: str
    status: str
    backend: str
    model: str
    schema_version: int = SCHEMA_VERSION
    event_type: str | None = None
    entity: str | None = None
    direction: str | None = None
    horizon_days: int | None = None
    confidence: float | None = None
    evidence_quote: str | None = None
    refusal_reason: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    raw_sha256: str | None = None
    meta: dict = field(default_factory=dict)

    @property
    def is_refusal(self) -> bool:
        return self.status != "OK"


_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_reply(text: str) -> tuple[dict | None, str | None]:
    """(record, refusal). Exactly one of the two is None.

    A fenced block, a preamble and a trailing apology are all normal model
    output, so the widest balanced-looking object is extracted rather than the
    reply being required to be pure JSON. What is NOT tolerated is a reply with
    no object in it at all -- that is `REFUSED_UNPARSEABLE`, a row, not a retry.
    """
    if not (text or "").strip():
        return None, "REFUSED_UNPARSEABLE"
    m = _JSON_RE.search(text)
    if not m:
        return None, "REFUSED_UNPARSEABLE"
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None, "REFUSED_UNPARSEABLE"
    if not isinstance(obj, dict):
        return None, "REFUSED_SCHEMA"
    return obj, None


def validate(obj: dict) -> tuple[dict | None, str | None]:
    """Coerce to the schema or refuse. Never partially accept.

    A half-valid row that keeps whichever fields happened to parse is how a
    column ends up holding three types and a downstream group-by silently
    reports on a subset.
    """
    et = str(obj.get("event_type") or "").strip().upper()
    if et not in EVENT_TYPES:
        return None, "REFUSED_SCHEMA"
    if et == "NO_EVENT":
        return {"event_type": "NO_EVENT"}, "REFUSED_NO_EVENT"

    direction = str(obj.get("direction") or "UNCLEAR").strip().upper()
    if direction not in DIRECTIONS:
        direction = "UNCLEAR"
    try:
        horizon = int(obj.get("horizon_days") or 0)
    except (TypeError, ValueError):
        horizon = 0
    horizon = min(250, max(1, horizon)) if horizon else None
    try:
        conf = float(obj.get("confidence"))
    except (TypeError, ValueError):
        conf = None
    if conf is not None:
        conf = min(1.0, max(0.0, conf))
    quote = obj.get("evidence_quote")
    quote = str(quote)[:200] if quote else None
    entity = obj.get("entity")
    entity = str(entity)[:80] if entity else None
    return {"event_type": et, "entity": entity, "direction": direction,
            "horizon_days": horizon, "confidence": conf,
            "evidence_quote": quote}, None


def review_one(doc_id: str, text: str, *, backend: str = "local_gguf",
               model: str | None = None, max_tokens: int = 400,
               purpose: str = "local_review") -> ReviewRow:
    """One document in, one row out. NEVER raises: a failure IS the row."""
    row = ReviewRow(doc_id=doc_id, status="OK", backend=backend,
                    model=model or "")
    if not (text or "").strip():
        row.status = "REFUSED_EMPTY_DOC"
        row.refusal_reason = ("nothing was sent to the model; this is a store "
                              "or selection failure, not a model failure")
        return row
    t0 = time.monotonic()
    try:
        rep = fi.complete(backend, build_prompt(text), system=_SYSTEM,
                          model=model, purpose=purpose, max_tokens=max_tokens)
    except fi.LanguageRefused as exc:
        row.status = "REFUSED_LANGUAGE"
        row.refusal_reason = str(exc)[:300]
        row.latency_s = round(time.monotonic() - t0, 3)
        r = getattr(exc, "reply", None)
        row.tokens_in = int(getattr(r, "prompt_tokens", 0) or 0)
        row.tokens_out = int(getattr(r, "completion_tokens", 0) or 0)
        return row
    except ProviderRefusal as exc:
        row.status = "REFUSED_PROVIDER"
        row.refusal_reason = str(exc)[:300]
        row.latency_s = round(time.monotonic() - t0, 3)
        return row

    row.model = rep.model
    row.tokens_in, row.tokens_out = rep.tokens_in, rep.tokens_out
    row.cost_usd, row.latency_s = rep.cost_usd, rep.latency_s
    obj, refusal = parse_reply(rep.text)
    if refusal:
        row.status = refusal
        row.refusal_reason = f"reply had no usable JSON: {rep.text[:160]!r}"
        return row
    fields, refusal = validate(obj)
    if refusal:
        row.status = refusal
        row.event_type = (fields or {}).get("event_type")
        row.refusal_reason = (
            "the model looked and reported no company-level event"
            if refusal == "REFUSED_NO_EVENT"
            else f"JSON did not match the schema: {str(obj)[:160]}")
        return row
    for k, v in fields.items():
        setattr(row, k, v)
    return row


def review_batch(docs, *, backend: str = "local_gguf", model: str | None = None,
                 max_tokens: int = 400, purpose: str = "local_review",
                 on_row=None) -> tuple[list[ReviewRow], dict]:
    """Review `(doc_id, text)` pairs and return (rows, receipt).

    `on_row` is called after each row so a long batch writes INCREMENTALLY --
    the same lesson as the scrape store: a receipt that only exists at the end
    does not exist for any run that fails.
    """
    rows: list[ReviewRow] = []
    t0 = time.monotonic()
    for doc_id, text in docs:
        row = review_one(doc_id, text, backend=backend, model=model,
                         max_tokens=max_tokens, purpose=purpose)
        rows.append(row)
        if on_row is not None:
            on_row(row)
    return rows, throughput_receipt(rows, wall_s=time.monotonic() - t0,
                                    backend=backend)


def throughput_receipt(rows: list[ReviewRow], *, wall_s: float,
                       backend: str) -> dict:
    """Documents per hour, tokens, dollars, and what DeepSeek would have charged.

    The counterfactual is priced from `config.LLM_PRICE_PER_MTOK` on the SAME
    token counts -- the one price table. A saving computed at a rate somebody
    remembered is a wish, and this repo has already had a table that disagreed
    with itself by 1.6x on the input leg for 24 days.
    """
    if not rows:
        raise EmptyBatch(
            "throughput_receipt() was handed zero rows. There is no "
            "documents-per-hour for a batch that reviewed no documents, and "
            "emitting zeros would read as a measured result rather than as an "
            "empty run. Check the selection that produced the batch.")
    tin = sum(r.tokens_in for r in rows)
    tout = sum(r.tokens_out for r in rows)
    n = len(rows)
    ok = sum(1 for r in rows if r.status == "OK")
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    wall_s = max(float(wall_s), 1e-9)
    ds = fi.counterfactual_deepseek(tin, tout)
    spend = round(sum(r.cost_usd for r in rows), 8)
    return {
        "backend": backend,
        "schema_version": SCHEMA_VERSION,
        "n_docs": n,
        "n_ok": ok,
        "n_refusals": n - ok,
        "by_status": dict(sorted(by_status.items())),
        "tokens_in": tin,
        "tokens_out": tout,
        "wall_clock_s": round(wall_s, 2),
        "docs_per_hour": round(n / wall_s * 3600.0, 1),
        "seconds_per_doc": round(wall_s / n, 3) if n else None,
        "output_tokens_per_s": round(tout / wall_s, 1),
        "cost_usd": spend,
        "cost_usd_str": f"${spend:.2f}",
        "deepseek_counterfactual_usd": round(ds, 6),
        "deepseek_counterfactual_str": f"${ds:.4f}",
        "saved_usd": round(ds - spend, 6),
        "price_table": "backend.config.LLM_PRICE_PER_MTOK",
        "note": ("cost_usd is 0.00 because the backend is free-tier; the REAL "
                 "cost of the local path is wall clock, which is why it is "
                 "printed beside the dollars and not instead of them"),
    }


def rows_to_jsonl(rows: list[ReviewRow]) -> str:
    return "\n".join(json.dumps(asdict(r)) for r in rows)
