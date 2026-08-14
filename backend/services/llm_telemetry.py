"""The inference ledger: what every LLM call cost, and what it bought.

WHY THIS EXISTS
===============

Murat's standing question is not "how many calls did we make" — it is "is the
money buying anything". The external review put the failure mode precisely: the
worry is not many calls, it is **calls that produce no learning sample**.
DeepSeek billed ~$5.26 for 40M tokens across 8,936 requests, which is cheap
enough to treat inference as an experimental resource rather than a cost centre
— but only if each call is accounted for. Before this module there was no single
place that knew what was spent or what it produced: `llm_research.py` ledgered
its own three roles, `llm_analyzer.py` counted calls-per-day and nothing else,
and `optimus_specialists.py` and `copilot.py` recorded nothing at all.

The objective in `docs/OPTIMUS_OBJECTIVE.md` becomes measurable only with this
row: every dollar of inference should produce a decision, a hypothesis, or a
labelled experience.

THE INTERESTING CASE IS THE EMPTY ONE
-------------------------------------
A call whose output did not parse, or which minted no gradeable record, is not
an error to be swallowed — it is the finding. `schema_valid=False` and an empty
`prediction_ids`/`hypothesis_ids` pair are the "spent money, learned nothing"
bucket, and `summary()` prints it as a first-class number rather than something
a reader has to derive. NIGHT-13 found a resolver with no caller, green for a
month; the same shape here would be a ledger whose zero-yield share nobody ever
computed.

COST IS AN ESTIMATE, AND SAYS SO
--------------------------------
Prices come from `config.LLM_PRICE_PER_MTOK` — point-in-time list prices that
drift. An unknown model yields `cost_usd=None` and a WARNING, never a zero. A
fabricated zero would read as "free" on every dashboard that sums the column,
which is exactly the house failure mode: a number that is wrong in the direction
of looking fine.

TELEMETRY MAY NEVER TAKE DOWN A FORECAST
----------------------------------------
`record_call()` swallows its own failures to a WARNING and returns None. A
crash in accounting must not cost a specialist its batch. Callers are given
nothing to branch on, by the same house rule that makes
`belief_state.append()` return None.

CACHE HITS ARE INVISIBLE ON PURPOSE
-----------------------------------
`llm_analyzer` wraps its helpers in `@cached`; a cache hit makes no wire call,
spends nothing, and writes no row. The ledger counts wire attempts. A call
refused by the daily-cap or billing breaker likewise writes no row — it spent
nothing and produced nothing, and counting it would dilute the very denominator
this file exists to compute.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import logging
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from backend.config import (LLM_PRICE_AS_OF, LLM_PRICE_PER_MTOK,
                            LLM_TELEMETRY_PATH_ENV)

logger = logging.getLogger(__name__)

#: Sits beside predictions.jsonl deliberately: the join in `summary()` is
#: between these two files, and a ledger that can drift to another directory is
#: a join that can silently match nothing.
LEDGER_DIR = Path(__file__).resolve().parents[1] / "data" / "optimus"
LLM_CALLS = LEDGER_DIR / "llm_calls.jsonl"

#: Where torn lines go. A corrupt line is DELETED FROM NOTHING: it is copied
#: here with its line number and the parser's complaint, so the missing spend
#: has an address rather than only a count. See `quarantine_unreadable`.
QUARANTINE_SUFFIX = ".quarantine.jsonl"

SCHEMA_VERSION = "1.0.0"

#: Dated model ids (`claude-haiku-4-5-20251001`) name the same model as the
#: undated alias and are priced identically, so stripping an 8-digit date suffix
#: is a rename, not a guess. Anything else unknown stays unknown.
_DATE_SUFFIX = re.compile(r"-\d{8}$")

#: In-process sequence, part of every call_id — see the comment in `build_call`.
_SEQ = itertools.count()


def _hash(payload: Any) -> str:
    """Stable content hash. Two calls with the same hash saw the same world."""
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _now() -> str:
    """Microsecond resolution, deliberately.

    belief_state stamps records to the second because a resolution date is
    daily. A call ledger is not: a specialist panel fires several calls inside
    one second, and at second resolution two of them with the same prompt and
    token counts hash to the SAME `call_id` — whereupon `read_calls` dedupes
    one away and the night's spend is quietly understated. Caught by
    `test_the_zero_gradeable_bucket_is_a_first_class_number`, which counted two
    rows where three were written.
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


# ── pricing ─────────────────────────────────────────────────────────────────
def price_call(model: str, tokens_in: int, tokens_out: int,
               cached_tokens: int = 0) -> float | None:
    """USD estimate for one call, or None when the model is not in the table.

    `tokens_in` is the count billed at the FULL input rate and `cached_tokens`
    the count billed at the discounted cache-read rate. The two providers report
    this differently — DeepSeek's `prompt_tokens` INCLUDES its cache hits, while
    Anthropic reports `cache_read_input_tokens` beside `input_tokens` — so the
    normalisation happens at the call site (see `extract_usage`) and this
    function is handed two disjoint counts. Defining the field this way is the
    only reason the same arithmetic can price both providers.

    Returns None rather than 0.0 for an unknown model. A zero would be summed
    into a spend total and read as "this was free"; None forces every consumer
    to decide what to do about a call it cannot price.
    """
    key = model.strip()
    price = LLM_PRICE_PER_MTOK.get(key)
    if price is None:
        alias = _DATE_SUFFIX.sub("", key)
        price = LLM_PRICE_PER_MTOK.get(alias)
    if price is None:
        logger.warning(
            "llm_telemetry: no price for model %r — this call is recorded with "
            "cost_usd=None and every total that includes it is a LOWER BOUND. "
            "Add it to config.LLM_PRICE_PER_MTOK.", model)
        return None
    cached_rate = price.get("cached_in", price["in"])
    return round((int(tokens_in) * price["in"]
                  + int(cached_tokens) * cached_rate
                  + int(tokens_out) * price["out"]) / 1_000_000.0, 8)


def extract_usage(resp: Any, provider: str) -> dict:
    """Normalise a provider's usage object into (tokens_in, cached, tokens_out).

    The two wire formats disagree about whether cached input is inside or beside
    the input count, and getting that wrong silently double-counts or drops a
    whole token class. Doing the reconciliation here — once, with the reason
    written down — keeps every call site from re-deriving it:

    * OpenAI/DeepSeek: `prompt_tokens` is the TOTAL prompt, with
      `prompt_cache_hit_tokens` a subset of it, so the full-rate count is the
      difference.
    * Anthropic: `input_tokens` already EXCLUDES `cache_read_input_tokens`, so
      the two add up rather than nest.

    A provider that reports nothing yields zeros — priced at $0, which is
    honest (we know the rate, we don't know the tokens) and distinguishable
    from an unknown model, which yields None.
    """
    u = getattr(resp, "usage", None)
    if u is None:
        return {"tokens_in": 0, "tokens_out": 0, "cached_tokens": 0}

    def _get(name: str) -> int:
        v = getattr(u, name, None)
        if v is None and isinstance(u, dict):
            v = u.get(name)
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0

    if provider == "anthropic":
        return {"tokens_in": _get("input_tokens"),
                "tokens_out": _get("output_tokens"),
                "cached_tokens": _get("cache_read_input_tokens")}
    total_in = _get("prompt_tokens")
    cached = _get("prompt_cache_hit_tokens")
    return {"tokens_in": max(total_in - cached, 0),
            "tokens_out": _get("completion_tokens"),
            "cached_tokens": cached}


# ── the record ──────────────────────────────────────────────────────────────
@dataclass
class LLMCall:
    """One wire attempt against a language model, and what it produced."""
    call_id: str
    ts: str
    provider: str
    model: str
    purpose: str
    model_version: str = ""
    agent: str | None = None
    prompt_hash: str = ""
    context_hash: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0
    latency_ms: float | None = None
    cost_usd: float | None = None
    #: Always True. Kept as a field rather than a docstring so it travels with
    #: every exported row — a consumer reading the JSONL has no other way to
    #: know the number is a list-price reconstruction, not a billed amount.
    cost_is_estimate: bool = True
    pricing_as_of: str = LLM_PRICE_AS_OF
    schema_valid: bool = True
    retries: int = 0
    error: str | None = None
    prediction_ids: list[str] = field(default_factory=list)
    hypothesis_ids: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    #: "call" for a wire attempt, "amendment" for a later link (see
    #: `attach_outputs`). Folded by `read_calls`, never summed twice.
    row_type: str = "call"
    schema_version: str = SCHEMA_VERSION

    def gradeable(self) -> bool:
        """Did this call produce anything that can later be scored?

        The definition is deliberately strict: parsed output that minted no
        record is still zero learning. A call that merely 'worked' is not a
        call that taught us anything.
        """
        return bool(self.schema_valid
                    and (self.prediction_ids or self.hypothesis_ids))


def build_call(*, provider: str, model: str, purpose: str,
               agent: str | None = None,
               prompt: Any = None, prompt_hash: str | None = None,
               context: Any = None, context_hash: str | None = None,
               model_version: str | None = None,
               tokens_in: int = 0, tokens_out: int = 0,
               cached_tokens: int = 0,
               latency_ms: float | None = None,
               schema_valid: bool = True, retries: int = 0,
               error: str | None = None,
               prediction_ids: Iterable[str] | None = None,
               hypothesis_ids: Iterable[str] | None = None,
               meta: dict | None = None,
               ts: str | None = None) -> LLMCall:
    """Assemble a record. Pure: builds nothing on disk, raises on nothing."""
    ts = ts or _now()
    ph = prompt_hash if prompt_hash is not None else (
        _hash(prompt) if prompt is not None else "")
    ch = context_hash if context_hash is not None else (
        _hash(context) if context is not None else "")
    preds = [str(p) for p in (prediction_ids or [])]
    hyps = [str(h) for h in (hypothesis_ids or [])]
    return LLMCall(
        # The id salt is (pid, in-process sequence), NOT the timestamp. Windows'
        # clock granularity is ~15ms — coarser than the rate a specialist panel
        # issues calls at — so five rows written in a loop share one timestamp
        # to the microsecond and hash identically. `read_calls` would then dedupe
        # four of them away and the night's spend would read 1/5 of the truth.
        # pid separates concurrent writers; the counter separates calls within
        # one of them.
        call_id=_hash([provider, model, purpose, agent, ts, ph, ch,
                       tokens_in, tokens_out, os.getpid(), next(_SEQ)]),
        ts=ts, provider=provider, model=str(model), purpose=purpose,
        model_version=str(model_version or model), agent=agent,
        prompt_hash=ph, context_hash=ch,
        tokens_in=int(tokens_in), tokens_out=int(tokens_out),
        cached_tokens=int(cached_tokens),
        latency_ms=(round(float(latency_ms), 2)
                    if latency_ms is not None else None),
        cost_usd=price_call(model, tokens_in, tokens_out, cached_tokens),
        schema_valid=bool(schema_valid), retries=int(retries),
        error=(str(error)[:400] if error else None),
        prediction_ids=preds, hypothesis_ids=hyps, meta=dict(meta or {}))


# ── the ledger ──────────────────────────────────────────────────────────────
def _resolve_path(path: Path | None) -> Path | None:
    """Where to write. None means "do not write", and is not an error.

    Under pytest with no explicit destination the answer is None. Test doubles
    make no wire call and spend no money; a row for one would put fabricated
    spend into the ledger this module exists to keep honest — which is worse
    than the row being missing. Telemetry's own tests pass `path=` (or set the
    env var), so the write path is still exercised.
    """
    if path is not None:
        return path
    env = os.getenv(LLM_TELEMETRY_PATH_ENV)
    if env:
        return Path(env)
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None
    return LLM_CALLS


#: Serialises appends WITHIN this process. See `append` for why it exists and
#: for the case it deliberately does not cover.
_APPEND_LOCK = threading.Lock()


def append(records: list[LLMCall], path: Path | None = None) -> None:
    """Append rows. Returns None: nothing may branch on a write.

    LOCKED, and the reason is a measurement rather than a precaution. LLM-SWARM-1
    ran 24 worker threads through this function 8,014 times and **two rows came
    back torn** — one line holding only `"1.0.0"}`, another only `"}`. A
    single `write()` of a short line is atomic on POSIX by convention and is NOT
    guaranteed on Windows, so interleaved appends can and did split a row in the
    middle. The cost is two calls' spend silently missing from a ledger whose
    entire purpose is to know what was spent; `read_calls` counts the
    unreadable lines and downgrades every total to a LOWER BOUND, which is how
    this was caught at all.

    WHAT THE LOCK DOES NOT COVER: two PROCESSES (or two Railway replicas)
    writing the same file. That needs an OS-level file lock, and it is a
    different problem from the one measured here — stating the boundary rather
    than implying the file is now safe against everything.
    """
    p = _resolve_path(path)
    if p is None:
        logger.debug("llm_telemetry: write suppressed under pytest (%d row(s))",
                     len(records))
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    blob = "".join(json.dumps(asdict(r), ensure_ascii=False) + "\n"
                   for r in records)
    with _APPEND_LOCK:
        with p.open("a", encoding="utf-8") as fh:
            fh.write(blob)


def record_call(**kwargs: Any) -> None:
    """Build and append one row. NEVER raises, NEVER returns anything usable.

    This is the whole contract with the call sites: instrumentation may degrade
    to a log line, but a forecast, a summary or a chat turn must return exactly
    what it would have returned without it.
    """
    path = kwargs.pop("path", None)
    try:
        append([build_call(**kwargs)], path=path)
    except Exception as exc:                              # noqa: BLE001
        logger.warning("llm_telemetry: failed to record a %s call (%s: %s) — "
                       "the call itself is unaffected, but this spend is now "
                       "MISSING from the ledger",
                       kwargs.get("purpose", "?"), type(exc).__name__, exc)


def attach_outputs(call_id: str, *, prediction_ids: Iterable[str] = (),
                   hypothesis_ids: Iterable[str] = (),
                   schema_valid: bool | None = None,
                   yield_resolved: bool = False,
                   path: Path | None = None) -> None:
    """Link outputs discovered AFTER the row was written, append-only.

    Some roles only know what a call produced once the reply has been parsed
    (`llm_research.generate_hypotheses` is the case that forced this). Rewriting
    the original row would destroy the evidence of what was known at write time,
    so the link arrives as a second row carrying the same `call_id`, folded by
    `read_calls`. Never raises, for the same reason `record_call` does not.
    """
    try:
        row = LLMCall(call_id=call_id, ts=_now(), provider="", model="",
                      purpose="", prediction_ids=[str(p) for p in prediction_ids],
                      hypothesis_ids=[str(h) for h in hypothesis_ids],
                      schema_valid=(True if schema_valid is None
                                    else bool(schema_valid)),
                      row_type="amendment",
                      meta={"schema_valid_set": schema_valid is not None,
                            # An empty resolution is a REAL answer — "this chain
                            # finished and minted nothing" — and it must land in
                            # the dead bucket rather than stay pending forever.
                            "yield_resolved": bool(yield_resolved)})
        append([row], path=path)
    except Exception as exc:                              # noqa: BLE001
        logger.warning("llm_telemetry: failed to attach outputs to %s (%s: %s)",
                       call_id, type(exc).__name__, exc)


#: Incremental parse state, keyed by resolved path. The ledger is append-only,
#: so re-parsing 21MB to answer "how much have we spent" is pure waste — and it
#: was not free waste: MARKET-GRAPH-1 measured `research_budget.require()`
#: consuming 95% of its throughput while the vendor itself answered in 2.9s.
#: A governor that is expensive to consult creates pressure to consult it less
#: often, which is how a spend ceiling quietly becomes advisory.
#:
#: Cache validity is (size, mtime_ns) plus the requirement that the file only
#: GREW. Anything else — truncation, rewrite, a different path — forces a full
#: re-parse, because a stale spend total is the one error this module exists to
#: prevent.
_PARSE_CACHE: dict[str, dict] = {}


def _parse_lines(lines: Iterable[str], base: dict[str, dict], order: list[str],
                 pending: list[dict]) -> int:
    """Fold raw ledger lines into `base`/`order`; return the unreadable count."""
    unreadable = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            unreadable += 1
            continue
        if row.get("row_type") == "amendment":
            pending.append(row)
            continue
        cid = row.get("call_id", "")
        if cid in base:
            # With pid+microsecond in the id, a repeat is a replayed write of
            # the SAME call, and counting it twice would overstate spend.
            # Logged loudly all the same: if ids ever start colliding for
            # genuinely distinct calls, this line is the only warning that the
            # total has begun to understate.
            logger.warning("llm_telemetry: duplicate call_id %s — later row "
                           "ignored; if these were two DISTINCT calls the "
                           "reported spend is now understated", cid)
            continue
        base[cid] = row
        order.append(cid)
    return unreadable


def _apply_amendments(base: dict[str, dict], pending: list[dict]) -> None:
    """Apply what can be applied; KEEP what cannot, and retry it next read.

    A full parse saw every line before applying, so an amendment could never
    precede its base row. An incremental parse can end mid-pair — the amendment
    in this tail, its base row in the next. Dropping it there would silently
    lose the outputs a call claimed, so unapplied amendments stay pending and
    are retried. Only a full re-parse may declare one genuinely unattributable.
    """
    still: list[dict] = []
    for a in pending:
        tgt = base.get(a.get("call_id", ""))
        if tgt is None:
            still.append(a)
            continue
        for key in ("prediction_ids", "hypothesis_ids"):
            merged = list(dict.fromkeys(list(tgt.get(key) or [])
                                        + list(a.get(key) or [])))
            tgt[key] = merged
        if (a.get("meta") or {}).get("schema_valid_set"):
            tgt["schema_valid"] = bool(a.get("schema_valid"))
        if (a.get("meta") or {}).get("yield_resolved"):
            # Copy rather than mutate in place: `read_calls` hands out the parse
            # cache's own dicts, and a shared `meta` object would let one
            # amendment silently mark rows it was never about.
            tgt["meta"] = {**(tgt.get("meta") or {}), "yield_resolved": True}
    pending[:] = still


def read_calls(path: Path | None = None) -> list[dict]:
    """Read the ledger with amendments folded into their base rows.

    Unreadable lines are COUNTED and logged, never skipped in silence: a corrupt
    line is missing spend, and spend that quietly disappears is the one direction
    a cost ledger must not fail in.

    Append-only files are parsed INCREMENTALLY — see `_PARSE_CACHE`. The returned
    rows are the cache's own dicts and must be treated as READ-ONLY; `reprice()`
    already returns new dicts rather than mutating.
    """
    p = _resolve_path(path)
    if p is None or not p.exists():
        return []
    key = str(p.resolve())
    st = p.stat()
    c = _PARSE_CACHE.get(key)

    # "Grew" means: same file, no shorter, and if identical in size then also
    # untouched. Anything else — truncated, rewritten in place — invalidates the
    # cache, because a cache that trusted mtime alone would keep reporting spend
    # for rows that no longer exist.
    grew = (c is not None and st.st_size >= c["size"]
            and (st.st_size != c["size"] or st.st_mtime_ns == c["mtime_ns"]))
    full = not grew
    if full:
        c = {"size": 0, "mtime_ns": st.st_mtime_ns, "base": {}, "order": [],
             "pending": [], "unreadable": 0}
        _PARSE_CACHE[key] = c
    base, order, pending = c["base"], c["order"], c["pending"]
    unreadable = c["unreadable"]

    if st.st_size > c["size"]:
        with p.open("rb") as fh:
            fh.seek(c["size"])
            tail = fh.read()
        # The cut is found in BYTES, never in decoded text. Decoding with
        # errors="replace" turns each bad byte into U+FFFD, which re-encodes to
        # THREE bytes — so measuring the offset by re-encoding the decoded text
        # drifts by 2 bytes per damaged byte. Drift backwards re-reads rows
        # already parsed (a duplicate-call_id warning storm, which is how this
        # was caught); drift forwards SKIPS rows, and skipped rows are spend
        # that silently vanishes. This ledger already carries two torn lines.
        #
        # A partially-flushed final line is not corruption either — it is a line
        # still being written. Hold the remainder back and re-read it next time.
        # 24 concurrent writers tore two lines in LLM-SWARM-1; whether we happen
        # to be caching at that moment is not a property of the data.
        if tail.endswith(b"\n"):
            chunk, consumed = tail, c["size"] + len(tail)
        else:
            cut = tail.rfind(b"\n")
            chunk = tail[:cut + 1] if cut >= 0 else b""
            consumed = c["size"] + len(chunk)
        if chunk:
            unreadable += _parse_lines(
                chunk.decode("utf-8", errors="replace").splitlines(),
                base, order, pending)
        c["size"], c["mtime_ns"], c["unreadable"] = (consumed, st.st_mtime_ns,
                                                     unreadable)

    if full:
        # Only a complete parse can prove an amendment has no base row anywhere.
        _apply_amendments(base, pending)
        for a in pending:
            logger.warning("llm_telemetry: amendment for unknown call_id %s — "
                           "the outputs it claims are unattributable",
                           a.get("call_id"))
    return _finish(base, order, pending, unreadable)


def _finish(base: dict[str, dict], order: list[str], pending: list[dict],
            unreadable: int) -> list[dict]:
    _apply_amendments(base, pending)
    if unreadable:
        logger.warning("llm_telemetry: %d unreadable ledger line(s) — reported "
                       "spend and yield are both LOWER BOUNDS", unreadable)
    out = [base[c] for c in order]
    if unreadable and out:
        out[0].setdefault("_unreadable_lines", unreadable)
    return out


# ── information per dollar ──────────────────────────────────────────────────
def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _as_instant(v: Any) -> datetime | None:
    """`since` as a MOMENT, when the caller gave one. None when they gave a day.

    `_as_date` truncated every cutoff to its date, so `since="2026-08-15T18:00"`
    silently meant "since midnight". Two things depended on that being exact and
    neither said so:

      * the IIF-1 nightly USD ceiling, which then counted every unrelated call
        made earlier the same day against the night's own $12; and
      * `measured_cost_night_1` — the number the funding rule turns on — which
        a rehearsal reported as $0.115 on a night that made no vendor call at
        all. That is how this was found.

    A date-only `since` keeps date semantics, because a caller who passed a day
    meant a day. Naive timestamps are read as UTC, which is what every writer in
    this repo emits.
    """
    if v is None or isinstance(v, date) and not isinstance(v, datetime):
        return None
    if isinstance(v, datetime):
        dt = v
    else:
        s = str(v)
        # A bare "2026-08-15" is a DAY, not midnight: treating it as an instant
        # would be the same truncation bug pointing the other way.
        if len(s) <= 10:
            return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def row_cost(row: dict) -> float | None:
    """One row's cost at CURRENT list prices, from the tokens the vendor reported.

    The shared kernel of `reprice()` and `spend()`. `spend()` runs before every
    vendor request and must not allocate a dict per row to answer one float.
    """
    ti, to = row.get("tokens_in"), row.get("tokens_out")
    if ti is None and to is None:
        c = row.get("cost_usd")
        return None if c is None else float(c)
    return price_call(str(row.get("model") or ""), int(ti or 0), int(to or 0),
                      int(row.get("cached_tokens") or 0))


def reprice(rows: list[dict]) -> list[dict]:
    """Recompute `cost_usd` from the STORED TOKENS at CURRENT list prices.

    `cost_usd` is written into each row at call time, which makes every total
    a snapshot of whatever the price table said that day. On 2026-08-12 the
    table was found to be pricing two model names that no longer exist —
    `deepseek-chat` and `deepseek-reasoner` both resolve server-side to
    `deepseek-v4-flash` — at roughly 2.8x the real rate. Ten thousand rows had
    already been written at the wrong number, and the budget governor was
    gating on their sum.

    Tokens are the FACT the vendor reported; dollars are a reconstruction from
    a table that drifts. So the fact is stored and the reconstruction is
    recomputed on read. A row with no token counts keeps whatever it was
    written with, because there is nothing better to do with it than say so.

    Returns new dicts; the caller's rows are not mutated.
    """
    out: list[dict] = []
    for r in rows:
        if r.get("tokens_in") is None and r.get("tokens_out") is None:
            out.append(r)
            continue
        out.append({**r, "cost_usd": row_cost(r), "cost_repriced": True,
                    "cost_usd_as_written": r.get("cost_usd")})
    return out


def _gradeable(row: dict) -> bool:
    return bool(row.get("schema_valid")
                and (row.get("prediction_ids") or row.get("hypothesis_ids")))


#: How a row's gradeable output is accounted. Declared by the CALL SITE, in
#: `meta`, and defaulting to the strict per-call reading everything used before.
YIELD_UNIT_CALL = "call"
YIELD_UNIT_CHAIN = "chain"


def _yield_pending(row: dict) -> bool:
    """Is this row's yield not knowable YET, as opposed to known to be zero?

    A one-call-one-record campaign learns immediately whether a call minted
    anything. A microtask CHAIN does not: INTERNET-INVESTIGATOR-FWD-1 spends
    five calls per cell — extract, expectations, forecast, critic, tool plan —
    and mints nothing until every arm has finished, because the records are the
    cross-arm intersection and that set does not exist until the last arm ends.

    Read per call, every row of such a night is "spent money, learned nothing"
    until the moment it is not, and `research_budget` halted the night at 100%
    zero-yield after 50 calls. The gate was measuring WHEN minting happens, not
    whether the spend bought anything.

    So a chain row is PENDING until the chain resolves it — never silently
    excused. `investigator_night` amends every call of a finished chain: with
    the ids it minted, or with nothing, and a chain that minted nothing lands in
    the dead bucket exactly as a barren single call does. An unresolved pending
    row is a chain that never finished, and it stays visible as pending rather
    than being counted either way.
    """
    meta = row.get("meta") or {}
    if str(meta.get("yield_unit") or YIELD_UNIT_CALL) != YIELD_UNIT_CHAIN:
        return False
    if meta.get("yield_resolved"):
        return False
    return not (row.get("prediction_ids") or row.get("hypothesis_ids"))


def summary(since: Any = None, path: Path | None = None,
            predictions_path: Path | None = None) -> dict:
    """What the spend bought, sliced so the empty bucket cannot hide.

    Every ratio is printed beside its own count. A "schema-valid rate" over
    three calls is a description of three calls, and CANON §19's habit — print
    the n, always — applies to spend accounting for exactly the same reason it
    applies to a Brier score.
    """
    rows = reprice(read_calls(path))
    # A torn line is spend that vanished, and it makes the total a LOWER BOUND
    # for a completely different reason than an unpriced model does. Both
    # reasons now reach the reader; LLM-SWARM-1 produced two of these from 24
    # concurrent writers and only the warning log said so.
    unreadable = int(rows[0].get("_unreadable_lines", 0)) if rows else 0
    cutoff = _as_date(since)
    if cutoff is not None:
        rows = [r for r in rows
                if r.get("ts") and _as_date(r["ts"]) >= cutoff]

    base = {
        "n_calls": len(rows),
        "since": str(cutoff) if cutoff else None,
        "n_unreadable_ledger_lines": unreadable,
        "cost_is_estimate": True,
        "pricing_as_of": LLM_PRICE_AS_OF,
        "pricing_note": ("costs are reconstructed from point-in-time list "
                         "prices in config.LLM_PRICE_PER_MTOK, not from billed "
                         "amounts; if the rates have drifted the total is wrong "
                         "by that drift and by nothing else"),
    }
    if not rows:
        # A stated zero, not a crash and not a blank: "no calls in this window"
        # is a real answer, and it is the answer that means the LLM went dark.
        base.update({
            "total_cost_usd": 0.0, "n_unpriced_calls": 0,
            "total_is_lower_bound": False,
            "by_purpose": {}, "by_model": {},
            "schema_valid_rate": None, "n_schema_invalid": 0,
            "predictions_minted": 0, "hypotheses_minted": 0,
            "predictions_per_dollar": None,
            "zero_gradeable_output": {
                "n_calls": 0, "share_of_calls": None,
                "n_resolvable": 0, "n_yield_pending": 0,
                "share_of_resolvable": None,
                "cost_usd": 0.0, "share_of_spend": None},
            "resolution": {"n_prediction_ids_claimed": 0,
                           "reading": "no calls, so nothing to join"},
            "status": "EMPTY",
            "reading": ("no LLM call has been recorded in this window — either "
                        "nothing ran, or a call path is uninstrumented; both "
                        "are findings, and neither is zero spend"),
        })
        return base

    priced = [r for r in rows if r.get("cost_usd") is not None]
    unpriced = [r for r in rows if r.get("cost_usd") is None]
    total = round(sum(float(r["cost_usd"]) for r in priced), 6)

    def _bucket(rs: list[dict]) -> dict:
        p = [r for r in rs if r.get("cost_usd") is not None]
        return {
            "n": len(rs),
            "cost_usd": round(sum(float(r["cost_usd"]) for r in p), 6),
            "n_unpriced": len(rs) - len(p),
            "n_schema_invalid": sum(1 for r in rs if not r.get("schema_valid")),
            "n_zero_gradeable": sum(1 for r in rs if not _gradeable(r)),
            "predictions_minted": sum(len(r.get("prediction_ids") or [])
                                      for r in rs),
            "tokens_in": sum(int(r.get("tokens_in") or 0) for r in rs),
            "tokens_out": sum(int(r.get("tokens_out") or 0) for r in rs),
        }

    by_purpose: dict[str, list[dict]] = {}
    by_model: dict[str, list[dict]] = {}
    for r in rows:
        by_purpose.setdefault(str(r.get("purpose") or "?"), []).append(r)
        by_model.setdefault(str(r.get("model") or "?"), []).append(r)

    pending_rows = [r for r in rows if _yield_pending(r)]
    dead = [r for r in rows if not _gradeable(r) and not _yield_pending(r)]
    dead_cost = round(sum(float(r["cost_usd"]) for r in dead
                          if r.get("cost_usd") is not None), 6)
    n_valid = sum(1 for r in rows if r.get("schema_valid"))
    pred_ids: list[str] = []
    for r in rows:
        pred_ids.extend(r.get("prediction_ids") or [])
    hyp_ids = sum(len(r.get("hypothesis_ids") or []) for r in rows)

    base.update({
        "total_cost_usd": total,
        "n_unpriced_calls": len(unpriced),
        "total_is_lower_bound": bool(unpriced or unreadable),
        "unpriced_models": sorted({str(r.get("model")) for r in unpriced}),
        "by_purpose": {k: _bucket(v) for k, v in sorted(by_purpose.items())},
        "by_model": {k: _bucket(v) for k, v in sorted(by_model.items())},
        "schema_valid_rate": round(n_valid / len(rows), 4),
        "n_schema_invalid": len(rows) - n_valid,
        "n_errored": sum(1 for r in rows if r.get("error")),
        "predictions_minted": len(pred_ids),
        "distinct_predictions_minted": len(set(pred_ids)),
        "hypotheses_minted": hyp_ids,
        "predictions_per_dollar": (round(len(pred_ids) / total, 2)
                                   if total > 0 else None),
        "zero_gradeable_output": {
            "n_calls": len(dead),
            "share_of_calls": round(len(dead) / len(rows), 4),
            "n_resolvable": len(rows) - len(pending_rows),
            "n_yield_pending": len(pending_rows),
            "share_of_resolvable": (
                round(len(dead) / (len(rows) - len(pending_rows)), 4)
                if len(rows) - len(pending_rows) else None),
            "pending_cost_usd": round(sum(float(r["cost_usd"])
                                          for r in pending_rows
                                          if r.get("cost_usd") is not None), 6),
            "cost_usd": dead_cost,
            "share_of_spend": (round(dead_cost / total, 4)
                               if total > 0 else None),
            "reading": ("spend that produced no schema-valid, gradeable output "
                        "— the bucket this ledger exists to make visible. "
                        "`n_yield_pending` is spend on chain campaigns whose "
                        "yield is not knowable yet and is NOT in either bucket; "
                        "a pending count that never falls is a chain that never "
                        "resolved, which is its own finding"),
        },
        "resolution": _resolution_join(pred_ids, total, rows, predictions_path),
    })
    base["status"] = "ok"
    return base


def _resolution_join(pred_ids: list[str], total_cost: float,
                     rows: list[dict], predictions_path: Path | None) -> dict:
    """Join telemetry to the prediction ledger and report only what resolved.

    Two integrity numbers matter more than the metrics here. `n_not_found_in_
    prediction_ledger` counts rows claiming to have minted records that do not
    exist — a telemetry row that lies about its yield is worse than no row, so
    it is surfaced rather than quietly dropped from the denominator. And when
    nothing has resolved, the count is stated and NO metric is computed: a
    Brier over an empty set is not a small number, it is not a number.
    """
    from backend.services.belief_state import read_predictions

    claimed = list(dict.fromkeys(pred_ids))
    if not claimed:
        return {"n_prediction_ids_claimed": 0,
                "reading": ("no call in this window minted a PredictionRecord "
                            "— nothing to grade, and therefore no statement "
                            "about forecast quality is available")}
    try:
        ledger = {r["prediction_id"]: r
                  for r in read_predictions(predictions_path)}
    except Exception as exc:                              # noqa: BLE001
        logger.warning("llm_telemetry: could not read the prediction ledger "
                       "(%s: %s) — the join is unavailable, not empty",
                       type(exc).__name__, exc)
        return {"n_prediction_ids_claimed": len(claimed),
                "status": "DEGRADED",
                "reading": "the prediction ledger could not be read"}

    found = [ledger[p] for p in claimed if p in ledger]
    missing = [p for p in claimed if p not in ledger]
    if missing:
        logger.warning("llm_telemetry: %d claimed prediction_id(s) are absent "
                       "from the prediction ledger — a telemetry row claiming "
                       "yield it did not mint is worse than no row", len(missing))
    out = {
        "n_prediction_ids_claimed": len(claimed),
        "n_matched_in_prediction_ledger": len(found),
        "n_not_found_in_prediction_ledger": len(missing),
        "not_found_ids": missing[:10],
    }
    resolved = [r for r in found
                if r.get("outcome") is not None and not r.get("void_reason")]
    if not resolved:
        out["n_resolved"] = 0
        out["reading"] = (
            f"{len(found)} minted forecast(s) matched, 0 have resolved yet — "
            f"no Brier, no cost-per-informative-forecast, and no substitute "
            f"for them is computed on an empty set")
        return out

    briers = [float(r["brier"]) for r in resolved]
    base_rate = sum(int(r["outcome"]) for r in resolved) / len(resolved)
    climatology = base_rate * (1 - base_rate)
    informative = [r for r in resolved if float(r["brier"]) < climatology]
    out.update({
        "n_resolved": len(resolved),
        "mean_brier": round(sum(briers) / len(briers), 6),
        "base_rate": round(base_rate, 4),
        "climatology_brier": round(climatology, 6),
        "n_informative": len(informative),
        "cost_per_resolved_forecast_usd": (round(total_cost / len(resolved), 6)
                                           if total_cost > 0 else None),
        "cost_per_informative_forecast_usd": (
            round(total_cost / len(informative), 6)
            if (total_cost > 0 and informative) else None),
        "reading": ("cost-per-informative divides ALL spend in the window by "
                    "the forecasts that beat climatology — that is the point: "
                    "calls that taught nothing are charged to the ones that did"),
    })
    return out


def scan_integrity(path: Path | None = None) -> dict:
    """Every line the parser cannot read, WITH its line number.

    `read_calls` already counts torn lines and downgrades spend to a lower
    bound. A count is enough to know the total is wrong and not enough to do
    anything about it: it cannot say which calls vanished, when, or whether the
    damage is growing. This walks the raw file and returns addresses.

    Read-only and total: it never repairs, never rewrites, and never decides.
    `quarantine_unreadable` is the only thing that writes, and it only ever
    COPIES.
    """
    # The SAME resolution `read_calls` uses, deliberately: an integrity report
    # that read a different file from the one the totals came from would be
    # reassurance about the wrong ledger. Under pytest with no explicit path
    # that resolves to None, and this reports "no file" rather than reaching
    # into the real ledger from a test.
    p = _resolve_path(path)
    if p is None or not p.exists():
        return {"path": str(p) if p else None, "exists": False,
                "n_lines": 0, "n_unreadable": 0, "unreadable": []}
    bad: list[dict] = []
    n_lines = 0
    # errors="replace" rather than strict: a byte-level fault must arrive as a
    # readable complaint about a locatable line, not as a UnicodeDecodeError
    # that takes the whole integrity check down with it.
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for i, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            n_lines += 1
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                bad.append({"line_no": i, "reason": str(exc),
                            "n_chars": len(line),
                            # A torn line is a FRAGMENT of accounting data, not
                            # content: keeping it bounded stops one damaged
                            # megabyte from becoming a health report nobody can
                            # read, while the sidecar keeps the full text.
                            "excerpt": line[:200]})
    return {"path": str(p), "exists": True, "n_lines": n_lines,
            "n_unreadable": len(bad), "unreadable": bad}


def quarantine_unreadable(path: Path | None = None,
                          quarantine_path: Path | None = None) -> dict:
    """Copy every torn line to a sidecar. Copies; never deletes, never repairs.

    The ledger is append-only and stays byte-identical — rewriting it to drop
    two bad lines would destroy the only evidence that anything was lost, and
    "the file parses cleanly now" is exactly the reassurance that must not be
    manufacturable. The sidecar is the address book: line number, the parser's
    complaint, the raw text, and when it was noticed.

    Re-runnable. Lines already quarantined (same line number and text) are not
    written twice, so this can sit in a health check without growing forever.
    """
    scan = scan_integrity(path)
    p = Path(scan["path"]) if scan.get("path") else None
    if p is None or not scan["exists"]:
        return {**scan, "quarantine_path": None, "n_written": 0}
    q = quarantine_path or p.with_suffix(p.suffix + QUARANTINE_SUFFIX)

    seen: set[tuple[int, str]] = set()
    if q.exists():
        for line in q.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen.add((int(r.get("line_no", -1)), str(r.get("raw", ""))))

    raw_lines = p.read_text(encoding="utf-8",
                            errors="replace").split("\n")
    detected_at = _now()
    fresh = []
    for b in scan["unreadable"]:
        raw = raw_lines[b["line_no"] - 1].strip() if b["line_no"] - 1 < len(raw_lines) else ""
        if (b["line_no"], raw) in seen:
            continue
        fresh.append({"line_no": b["line_no"], "reason": b["reason"],
                      "raw": raw, "detected_at": detected_at,
                      "source": str(p),
                      "note": ("copied, not moved — the source ledger is "
                               "append-only and still holds this line")})
    if fresh:
        q.parent.mkdir(parents=True, exist_ok=True)
        with q.open("a", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r, ensure_ascii=False) + "\n"
                             for r in fresh))
    return {**scan, "quarantine_path": str(q), "n_written": len(fresh)}


def ledger_health(path: Path | None = None, *, max_quiet_days: int = 7,
                  today: date | None = None) -> dict:
    """Would anything say so if the ledger stopped growing?

    Same failure shape as `belief_state.ledger_health`: an accounting file fails
    by not being written to, and an empty append is indistinguishable from a
    quiet night unless something checks the clock.
    """
    today = today or date.today()
    rows = read_calls(path)
    if not rows:
        empty = scan_integrity(path)
        return {"status": "DEGRADED", "n_calls": 0,
                "n_unreadable_lines": empty["n_unreadable"],
                "unreadable_line_numbers": [b["line_no"]
                                            for b in empty["unreadable"]],
                "totals_are_lower_bounds": bool(empty["n_unreadable"]),
                "reason": ("the LLM ledger is empty — either no call has been "
                           "made, or a call path is uninstrumented and its "
                           "spend is invisible")}
    last = max(str(r.get("ts", ""))[:10] for r in rows)
    quiet = (today - date.fromisoformat(last)).days
    problems = []
    if quiet > max_quiet_days:
        problems.append(f"no LLM call recorded in {quiet} days")
    # A torn line is missing spend, and until now the count lived only in a
    # WARNING inside `read_calls` — logged once, into a log nobody reads on a
    # schedule, while every total silently stayed a lower bound. Health is the
    # surface that gets read, so the damage is reported HERE and it degrades the
    # status: an accounting file that has lost rows is not "ok".
    integ = scan_integrity(path)
    if integ["n_unreadable"]:
        problems.append(
            f"{integ['n_unreadable']} unreadable ledger line(s) at "
            f"{[b['line_no'] for b in integ['unreadable']][:10]} — every spend "
            f"and yield total below is a LOWER BOUND")
    n_dead = sum(1 for r in rows if not _gradeable(r))
    return {
        "status": "ok" if not problems else "DEGRADED",
        "problems": problems,
        "n_calls": len(rows),
        "n_unreadable_lines": integ["n_unreadable"],
        "unreadable_line_numbers": [b["line_no"] for b in integ["unreadable"]],
        "totals_are_lower_bounds": bool(integ["n_unreadable"]),
        "n_unpriced": sum(1 for r in rows if r.get("cost_usd") is None),
        "n_zero_gradeable": n_dead,
        "distinct_purposes": len({r.get("purpose") for r in rows}),
        "distinct_models": len({r.get("model") for r in rows}),
        "last_written": last,
        "days_quiet": quiet,
    }


def spend(since: Any = None, path: Path | None = None, *,
          purpose: str | None = None) -> dict:
    """The four numbers a budget governor actually decides on, and nothing else.

    `summary()` is the reporting surface and it joins every claimed
    prediction_id against the prediction ledger. That join is the right thing
    for a report and the wrong thing for a gate: at 8,000 telemetry rows and
    12,000 minted forecasts it costs ~0.31s, against ~0.05s for the counts
    below. A campaign that calls the governor before EVERY vendor request — as
    it must, because a governor consulted every hundredth call is not a
    governor — would spend twenty minutes of one core re-reading a 25MB ledger
    to answer a question that does not depend on it.

    The failure this prevents is not slowness. It is the pressure slowness
    creates to check LESS often, which is how a spend ceiling quietly becomes
    advisory. Same inputs, same decision, one join cheaper.

    Returns {} on failure, never a zero: `research_budget` reads an empty dict
    as "spend is UNKNOWN" and refuses, which is the only safe reading when the
    accounting is broken.
    """
    # NOT reprice(): that materialises a new dict per row, and this function is
    # called before EVERY vendor request. Same arithmetic, no allocation.
    rows = read_calls(path)
    instant = _as_instant(since)
    if instant is not None:
        rows = [r for r in rows if r.get("ts")
                and (_as_instant(r["ts"]) or instant) >= instant]
    else:
        cutoff = _as_date(since)
        if cutoff is not None:
            rows = [r for r in rows
                    if r.get("ts") and _as_date(r["ts"]) >= cutoff]
    if purpose is not None:
        # Scoping the MEASUREMENT is not the same as scoping the CEILING. A
        # ceiling should stay broad — belt and braces — but the number the
        # funding rule reads has to be this trial's own spend, or a diagnostic
        # run the same evening silently decides whether 40 nights are affordable.
        rows = [r for r in rows if r.get("purpose") == purpose]
    if not rows:
        return {"n_calls": 0, "total_cost_usd": 0.0,
                "total_is_lower_bound": False,
                "zero_gradeable_output": {"n_calls": 0, "share_of_calls": None},
                "cost_is_estimate": True}
    total, n_priced = 0.0, 0
    for r in rows:
        c = row_cost(r)
        if c is not None:
            total += c
            n_priced += 1
    pending = sum(1 for r in rows if _yield_pending(r))
    dead = sum(1 for r in rows if not _gradeable(r) and not _yield_pending(r))
    resolvable = len(rows) - pending
    return {
        "n_calls": len(rows),
        "total_cost_usd": round(total, 6),
        "total_is_lower_bound": n_priced < len(rows),
        "n_unpriced_calls": len(rows) - n_priced,
        "zero_gradeable_output": {
            "n_calls": dead,
            "share_of_calls": round(dead / len(rows), 4),
            # The denominator a governor must decide on. A pending row is not
            # evidence of zero yield, and dividing by it turns "the night has
            # not finished" into "this campaign is buying tokens".
            "n_resolvable": resolvable,
            "n_yield_pending": pending,
            "share_of_resolvable": (round(dead / resolvable, 4)
                                    if resolvable else None)},
        "cost_is_estimate": True,
    }
