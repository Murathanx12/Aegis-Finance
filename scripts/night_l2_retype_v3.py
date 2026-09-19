"""L2_retype_v3 -- re-read the corpus for the two ids the vocabulary just gained.

WHY THIS IS A SEPARATE JOB AND NOT A WIDER L2 RUN
=================================================
Vocabulary v3 (2026-09-19, chunk 19) added `foreign_entrant_capacity` and
`growth_constraint_cited`. Every row typed before today was typed against a
table that could not offer either id, so those rows are not WRONG -- they are
answers to a question that had two fewer options. `vocabulary_version` on each
row is what makes that legible, and re-typing the whole corpus to fix it would
cost the whole corpus again.

The two new ids are also rare by construction. A foreign entrant reaching
qualified parity, or an officer naming the input that is capping growth, are
not things most headlines are about. So this job re-reads **only the rows whose
text matches a cheap keyword prefilter**, the prefilter is DECLARED here and
printed on the receipt, and the receipt carries its own recall caveat: a
prefilter is a SCREEN, and the rows it did not pass were never asked.

WHAT IT REFUSES
===============
It reads with the LOCAL model and nothing else, so it costs compute and not
dollars. It NEVER starts or stops a server: with no reader answering it writes
`PENDING_MODEL` with the candidate list frozen and hashed, so the run that
happens when a server IS up asks the same question rather than a similar one.

    python -m scripts.night_factory_jobs L2_retype_v3 --smoke
    python -m scripts.night_factory_jobs L2_retype_v3

Registered in `config.LAB_IDLE_QUEUE` immediately after `L2_typed_events`, with
a 60-minute box: the backlog job runs first because every other item either
consumes its output or is orthogonal to it, and this one reads the same corpus
the backlog is still filling.

LICENCE: PRODUCT_EXPERIMENT. Nothing here orders, promotes or seeds.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from backend.services import event_extraction as ex
from backend.services import event_vocabulary as vocab
from scripts.night_l2_typed_events import (
    FLUSH_EVERY,
    TYPED,
    _append,
    _now,
    _probe,
    corpus_files,
    corpus_unit,
    panel_units,
    read_rows,
    refusal_record,
    typed_record,
    type_units,
)

logger = logging.getLogger("l2_retype_v3")

JOB = "L2_retype_v3"
LICENCE = "PRODUCT_EXPERIMENT"

#: Never a literal. An idle-queue job runs every day and must date its outputs
#: by the day (2026-09-18: three of them overwrote committed receipts three
#: nights running). Unset means TODAY; `NIGHT_RUN_DATE` reproduces a past night.
RUN_DATE = os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")

#: The ids this job exists for. Read from the vocabulary, not retyped: a list
#: here that drifted from `ENTITY_DIRECTION_PRIORS` would be a job re-reading
#: the corpus for ids nobody added.
TARGET_IDS: tuple[str, ...] = tuple(vocab.IDS_WITH_ENTITIES)

#: THE PREFILTER, DECLARED. Two groups, one per target id, matched
#: case-insensitively on word boundaries over `title + body`.
#:
#: It is a SCREEN and the receipt says so. Recall is unknown and unmeasured:
#: these terms were written from the two spec sections' own examples and the
#: vocabulary rows' definitions, BEFORE any row was read, and a document that
#: says "our ability to grow is gated by what we can get from our partner in
#: Taiwan" passes none of them. The alternative is re-reading 163,288 texts to
#: find a handful, which is the cost this job exists to avoid; the honest
#: version is to declare the terms, print them, and never quote a RATE from a
#: screened denominator.
PREFILTER: dict[str, tuple[str, ...]] = {
    "foreign_entrant_capacity": (
        "qualif", "certif", "compatib", "interoperab", "validated on",
        "capacity parity", "domestic alternative", "local supplier",
        "market share", "entrant", "new entrant", "chinese rival",
        "domestic rival", "state-backed", "import substitution",
        "yield parity", "mass production", "ramp capacity",
    ),
    "growth_constraint_cited": (
        "constraint", "constrained", "bottleneck", "supply limited",
        "capacity limited", "shortage", "allocation", "could ship more",
        "limited by", "held back by", "gating factor", "binding constraint",
        "we are short", "sold out", "lead time", "backlog we cannot",
        "if we could get", "waiting on",
    ),
}

#: Rows per flush. A killed run keeps every row it already read.
RETYPE_FLUSH_EVERY = FLUSH_EVERY

#: The default ceiling on one pass. The lab's box is 60 minutes and the local
#: reader manages roughly 20 rows a minute per worker, so this is the number a
#: box can actually finish rather than a number that guarantees a kill.
MAX_ROWS_PER_RUN = 1_000

SMOKE_ROWS = 4


def out_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / f"night_factory_{RUN_DATE}"


def typed_dir() -> Path:
    return TYPED


def output_path() -> Path:
    return typed_dir() / f"retype_v3_{RUN_DATE}.jsonl"


def _compiled() -> dict:
    return {k: [re.compile(re.escape(t), re.IGNORECASE) for t in terms]
            for k, terms in PREFILTER.items()}


def prefilter_hits(text: str, compiled: dict | None = None) -> list[str]:
    """Which target ids' term groups this text matches. `[]` means skip.

    Matched on the RAW text, lowercased by the pattern flag rather than by a
    transform, so an accented or CJK document is neither mangled nor silently
    excluded -- it simply does not match a Latin term, which is a coverage fact
    the receipt counts rather than a bug this function hides.
    """
    comp = compiled or _compiled()
    return [k for k, pats in comp.items() if any(p.search(text) for p in pats)]


def prefilter_declaration() -> dict:
    """What the receipt prints so a later reader can reproduce the screen."""
    payload = json.dumps({k: list(v) for k, v in PREFILTER.items()},
                         sort_keys=True, separators=(",", ":"))
    return {
        "terms": {k: list(v) for k, v in PREFILTER.items()},
        "n_terms": {k: len(v) for k, v in PREFILTER.items()},
        "match": "case-insensitive substring over title + body",
        "prefilter_sha256": hashlib.sha256(payload.encode()).hexdigest()[:16],
        "it_is_a_SCREEN": (
            "recall is UNKNOWN and unmeasured. The terms were written from the "
            "spec's own examples and the vocabulary rows' definitions BEFORE "
            "any row was read; a document that names its constraint in words "
            "none of them contain is never asked. No RATE may be quoted from "
            "this denominator -- only counts, and only of what was screened in."),
        "why_a_screen_at_all": (
            "both v3 ids are rare by construction and the corpus holds 163,288 "
            "distinct texts. Re-reading all of them for two ids is the cost "
            "this job exists to avoid."),
    }


# --------------------------------------------------------------------------
# what has already been re-read


def already_typed(path: Path | None = None) -> set[str]:
    """Every `text_sha256` this job has already asked, READ BACK FROM THE FILE.

    Not a watermark. `panel_typed_hashes`' reason applies here with more force:
    a prefilter picks a scattered subset by design, so a cursor that declared
    "everything before row N is done" would skip every text the screen let
    through after it. A set read from the rows on disk cannot disagree with the
    rows on disk.

    Refusals count: a text the reader refused was asked and read, and asking it
    again every night is the loop 2026-09-10's replay is the standing lesson
    about.
    """
    d = typed_dir()
    if not d.is_dir():
        return set()
    seen: set[str] = set()
    paths = [path] if path is not None else sorted(d.glob("retype_v3_*.jsonl"))
    for p in paths:
        if p is None or not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            h = row.get("text_sha256")
            if h:
                seen.add(str(h))
    return seen


# --------------------------------------------------------------------------
# the candidates


def candidate_units(*, max_rows: int = MAX_ROWS_PER_RUN,
                    corpus_rows=None, panel=None) -> dict:
    """Units from BOTH sources that pass the prefilter and were not read yet.

    `corpus_rows` and `panel` are injectable so the tests can drive the whole
    selection without a corpus on disk.
    """
    comp = _compiled()
    done = already_typed()
    units: list[dict] = []
    stats = {"corpus_rows": 0, "panel_units": 0, "screened_in": 0,
             "already_read": 0, "by_id": {k: 0 for k in TARGET_IDS}}

    rows = corpus_rows
    if rows is None:
        rows, _unreadable = read_rows(corpus_files())
    for row in rows:
        stats["corpus_rows"] += 1
        u = corpus_unit(row)
        hits = prefilter_hits(f"{u['title']} {u['body']}", comp)
        if not hits:
            continue
        if u["text_sha256"] in done:
            stats["already_read"] += 1
            continue
        stats["screened_in"] += 1
        for h in hits:
            stats["by_id"][h] += 1
        units.append({**u, "prefilter_hits": hits})

    try:
        p_units = panel_units() if panel is None else panel_units(panel)
    except FileNotFoundError:
        p_units = []
    for u in p_units:
        stats["panel_units"] += 1
        hits = prefilter_hits(f"{u.get('title') or ''} {u.get('body') or ''}",
                              comp)
        if not hits:
            continue
        if u.get("text_sha256") in done:
            stats["already_read"] += 1
            continue
        stats["screened_in"] += 1
        for h in hits:
            stats["by_id"][h] += 1
        units.append({**u, "prefilter_hits": hits})

    # Deterministic order so a frozen candidate list is reproducible and a
    # resumed run continues rather than re-shuffling.
    units.sort(key=lambda u: str(u.get("text_sha256") or ""))
    stats["candidates"] = len(units)
    stats["already_read_total"] = len(done)
    return {"units": units[: int(max_rows)], "stats": stats,
            "truncated_at": int(max_rows) if len(units) > int(max_rows) else None}


def units_fingerprint(units: list[dict]) -> dict:
    """The frozen candidate list, hashed. A PENDING_MODEL receipt is only
    reproducible if the run that follows it reads the same rows."""
    keys = sorted(str(u.get("text_sha256") or u.get("key") or "")
                  for u in units)
    payload = json.dumps(keys, separators=(",", ":"))
    return {"n_units": len(units),
            "sha256": hashlib.sha256(payload.encode()).hexdigest()[:16],
            "first": keys[:3], "last": keys[-3:]}


# --------------------------------------------------------------------------
# the job


def L2_retype_v3(*, smoke: bool = False, run: int = 1,           # noqa: N802
                 max_rows: int = MAX_ROWS_PER_RUN, workers: int = 1,
                 backend: str = ex.BACKEND, complete=None,
                 corpus_rows=None, panel=None) -> dict:
    """One receipt: the screen, the candidates, the rows typed, the refusals."""
    t0 = datetime.now(timezone.utc)
    base = {
        "job": JOB, "licence": LICENCE, "run": int(run), "run_date": RUN_DATE,
        "smoke": bool(smoke),
        "llm_spend_usd": 0.0,
        "spend_note": ("the LOCAL reader costs compute, not dollars. This job "
                       "takes no cloud backend and no --max-usd; if it ever "
                       "does, the spend comes from the call ledger like every "
                       "other job's."),
        "question": (
            "Vocabulary v3 added `foreign_entrant_capacity` and "
            "`growth_constraint_cited`. Every row typed before 2026-09-19 was "
            "answered against a table that could not offer either. Which of "
            "the rows a declared keyword screen lets through carry them?"),
        "target_ids": list(TARGET_IDS),
        "vocabulary": {"version": vocab.VOCABULARY_VERSION,
                       "hash": vocab.VOCABULARY_HASH,
                       "n_types": vocab.N_TYPES,
                       "previous_version": 2,
                       "previous_hash": vocab.VOCABULARY_HASH_V2},
        "prefilter": prefilter_declaration(),
        "backend": backend,
        "never_starts_or_stops_a_server": (
            "with no reader answering this job writes PENDING_MODEL and the "
            "frozen candidate hash, so the run that happens when a server IS "
            "up asks the same question rather than a similar one"),
        "output": str(output_path()),
    }

    plan = candidate_units(max_rows=SMOKE_ROWS if smoke else max_rows,
                           corpus_rows=corpus_rows, panel=panel)
    units = plan["units"]
    base["selection"] = plan["stats"]
    base["truncated_at"] = plan["truncated_at"]
    base["candidate_fingerprint"] = units_fingerprint(units)

    if complete is None:
        why = _probe(backend)
        if why:
            return {
                **base, "typed": 0, "refusals": {},
                "headline": (f"PENDING_MODEL: {len(units)} candidate text(s) "
                             f"frozen at "
                             f"{base['candidate_fingerprint']['sha256']}; "
                             f"no reader answering ({why})"),
                "verdict": (f"PENDING_MODEL -- {why}. This job never starts or "
                            f"stops a server; the candidate list is frozen and "
                            f"hashed so the next run asks the same question."),
                "elapsed_s": round((datetime.now(timezone.utc)
                                    - t0).total_seconds(), 1),
                "written_utc": _now(),
            }
        from backend.services.free_inference import complete as complete_
        complete = complete_

    if not units:
        return {**base, "typed": 0, "refusals": {},
                "headline": ("nothing to do: no unread text passed the "
                             "declared screen"),
                "verdict": ("NOTHING TO DO -- the screen let nothing new "
                            "through. A pass that did nothing says so "
                            "(invariant 15); it is not an empty success."),
                "elapsed_s": round((datetime.now(timezone.utc)
                                    - t0).total_seconds(), 1),
                "written_utc": _now()}

    path = output_path()
    pending: list[dict] = []
    written = {"typed": 0, "refused": 0, "on_target": 0}
    by_type: dict[str, int] = {}

    def _on_result(idx, unit, res, usage):
        model = usage.get("model") if isinstance(usage, dict) else None
        if isinstance(res, ex.Refusal):
            rec = refusal_record(unit.get("row") or {}, res, backend=backend,
                                 variant="A", model=model)
            rec.update({"job": JOB, "text_sha256": unit.get("text_sha256"),
                        "prefilter_hits": unit.get("prefilter_hits"),
                        "vocabulary_version": vocab.VOCABULARY_VERSION,
                        "vocabulary_hash": vocab.VOCABULARY_HASH})
            written["refused"] += 1
        else:
            rec = typed_record(unit.get("row") or {}, res, backend=backend,
                               variant="A", model=model)
            rec.update({"job": JOB, "text_sha256": unit.get("text_sha256"),
                        "prefilter_hits": unit.get("prefilter_hits"),
                        "scope": unit.get("scope"),
                        "scope_kind": unit.get("scope_kind"),
                        "document_date": unit.get("document_date")})
            by_type[res.event_type] = by_type.get(res.event_type, 0) + 1
            if res.event_type in TARGET_IDS:
                written["on_target"] += 1
            written["typed"] += 1
        pending.append(rec)

    def _flush():
        _append(path, pending)
        pending.clear()

    res = type_units(units, backend=backend, complete=complete, variant="A",
                     workers=int(workers), flush_every=RETYPE_FLUSH_EVERY,
                     on_result=_on_result, on_flush=_flush)
    _flush()

    on_target = written["on_target"]
    return {
        **base,
        "typed": written["typed"], "refused": written["refused"],
        "on_target_rows": on_target,
        "by_type": by_type,
        "refusals": {k: v for k, v in (res.get("counts") or {}).items() if v},
        "reader": {k: res.get(k) for k in
                   ("stopped", "stop_detail", "submitted", "collected",
                    "retries", "rate_limited_rows", "tokens_in", "tokens_out",
                    "discarded_after_the_failure", "workers")},
        "headline": (
            f"{written['typed']} text(s) re-read against v{vocab.VOCABULARY_VERSION} "
            f"({vocab.N_TYPES} ids), {on_target} carried one of "
            f"{list(TARGET_IDS)}, {written['refused']} refused; screen let "
            f"{plan['stats']['screened_in']} of "
            f"{plan['stats']['corpus_rows'] + plan['stats']['panel_units']} "
            f"through"),
        "next_test": (
            "an on-target count is a COUNT and not a rate: the prefilter's "
            "recall is unmeasured, so the denominator is the screen and not "
            "the corpus. TRIAL-DRAFT-FOREIGN-ENTRANT-IC-v0 §4's MDE is filled "
            "in from the event count this job produces, and it is filled in "
            "BEFORE any return is joined."),
        "verdict": ("SMOKE -- proves the job runs end to end on four texts; no "
                    "count may be read from it"
                    if smoke else
                    f"{on_target} row(s) carry a v3 id. The rows are typed "
                    f"and joined to nothing; this job writes features, never "
                    f"a signal."),
        "on_target_share_is_not_quotable": (
            "the denominator is the SCREEN. A share computed against it would "
            "describe the keyword list, not the corpus."),
        "elapsed_s": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
        "written_utc": _now(),
    }
