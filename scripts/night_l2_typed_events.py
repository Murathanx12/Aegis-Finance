"""L2_typed_events -- the local reader types the news corpus, one row per document.

    python -m scripts.night_l2_typed_events --max-rows 200 --run 1
    python -m scripts.night_factory_jobs L2_typed_events --run 1

WHAT THIS PRODUCES
==================
`backend/data/optimus/typed_events/<YYYY-MM-DD>.jsonl`: one typed row per corpus
document -- `{event_type, direction, magnitude_bucket, confidence,
evidence_span}` from the frozen 40-id vocabulary, plus the provenance that makes
it re-checkable (`prompt_hash`, `vocabulary_hash`, the corpus key it came from).
Numeric by construction: E1's feature builder reads it without parsing a word of
English. The `.jsonl` files are DATA and are gitignored; `MANIFEST.json` beside
them is tracked, so a checkout without the corpus still carries the shape, the
row count and the hashes.

THE CURSOR IS THE RESUME
========================
Every run continues from `typed_events/_cursor.json`, which holds the last
`(first_seen_utc, raw_id)` typed per source. There is no other mode: a job that
could silently re-type 6,020 rows would burn GPU hours to write duplicates, and
2026-09-10's replay is the standing lesson about a night that repeated itself and
could not tell. `--resume` is accepted by the factory and is a no-op here for
that reason.

WHICH ROWS ARE ELIGIBLE
=======================
Only sources the registry marks `label_source: true`. Anything typed here can
become an E1 feature, and `news_registry` is where that decision lives -- an
`index_state` feed can be reordered under us, so a row from one may never label a
return. A source outside that list is not filtered quietly; the run refuses.

WHAT A TYPED ROW IS NOT
=======================
A feature. `direction` is a sign relative to the named scope entity, never a
position; nothing here sizes, ranks or orders anything. Invariant 5.

THE READER IS NOT STARTED BY THIS JOB
=====================================
`llama_server` is probed, never started and never stopped. With the server down
the job writes `PENDING_MODEL` with the input list frozen and hashed and the
projected wall time stated, so the run that happens when the server is up asks
exactly these documents rather than similar ones.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import event_extraction as ex                     # noqa: E402
from backend.services import jsonl_io as jio                            # noqa: E402
from backend.services import event_vocabulary as vocab                  # noqa: E402
from backend.services import news_registry as nr                        # noqa: E402

JOB = "L2_typed_events"
LICENCE = "PRODUCT_EXPERIMENT"
RUN_DATE = "2026-09-13"

CORPUS = REPO / "backend" / "data" / "optimus" / "news_corpus"
TYPED = REPO / "backend" / "data" / "optimus" / "typed_events"
CURSOR_PATH = TYPED / "_cursor.json"
MANIFEST_PATH = TYPED / "MANIFEST.json"
OUT_DIR = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"

#: The inter-rater control (roadmap L2: "a second prompt hash on a 500-row
#: sample, kappa printed"). 50 is what a first real run can afford in wall time;
#: the receipt states the spec's own 500 beside it so nobody reads 50 as the
#: control being complete.
KAPPA_ROWS = 50
KAPPA_ROWS_SPEC = 500

#: Output tokens per row, for the projection only. The schema's five fields are
#: ~20 tokens; the <=400-character evidence span dominates at ~100. Named as an
#: ESTIMATE because no L2 row has been generated yet -- the first real run
#: replaces it with `usage.tokens_out / rows`.
EST_OUT_TOKENS_PER_ROW = 120

#: chars -> tokens, for the prefill estimate. The convention is stated rather
#: than hidden: the real number arrives with the first run's own usage block.
CHARS_PER_TOKEN = 4.0

#: MEASURED rates, both from `night_factory_2026-09-13/L4_qwen3_measure_run01.json`
#: (`contended_measurement_being_superseded`), which is itself flagged a LOWER
#: BOUND -- all 20 cores were saturated by a PyInstaller build when it was taken.
RATES = {
    "qwen3_30b_a3b_contended": {"generation_tok_s": 19.8, "prompt_eval_tok_s": 5.6},
    "qwen2_5_7b_incumbent": {"generation_tok_s": 41.4, "prompt_eval_tok_s": 5.6},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(x, n=4):
    return None if x is None else round(float(x), n)


# --------------------------------------------------------------------- corpus

def label_sources() -> list[str]:
    """The registry's own answer. Never a literal list here: a source promoted or
    demoted in the registry must move this without a code change."""
    return list(nr.label_sources())


def corpus_files(sources: list[str] | None = None) -> list[Path]:
    want = set(sources or label_sources())
    out = []
    for d in sorted(CORPUS.glob("*")):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        if d.name not in want:
            continue
        out.extend(sorted(d.glob("*.jsonl")))
    return out


def read_rows(files: list[Path]) -> tuple[list[dict], list[str]]:
    """Every corpus row in the given files, plus the lines that did not parse.

    Through `jsonl_io`, NOT `str.splitlines()`: nine Benzinga bodies carry a
    literal U+2028, which `splitlines()` breaks on and JSONL does not, and a
    reader that splits there loses the row in two unparseable halves. The
    problems list is returned rather than swallowed -- an empty list and an
    unread list read identically in a receipt.
    """
    rows: list[dict] = []
    problems: list[str] = []
    allowed = set(label_sources())
    for path in files:
        got, bad = jio.read_rows(path)
        problems.extend(bad)
        for row in got:
            src = str(row.get("source") or path.parent.name)
            if src not in allowed:
                raise ValueError(
                    f"REFUSED: {path} carries source {src!r}, which the news registry "
                    f"does not mark `label_source: true`. A row that cannot label a "
                    f"return must not become a feature. Registry says: {sorted(allowed)}")
            row["source"] = src
            rows.append(row)
    return rows, problems


def row_key(row: dict) -> tuple[str, str, str]:
    """`(source, first_seen_utc, raw_id)` -- the cursor's ordering and the typed
    row's identity. `first_seen_utc` is the stamp WE wrote when the row arrived,
    not the publisher's, which is what makes the ordering ours to trust."""
    return (str(row.get("source") or ""), str(row.get("first_seen_utc") or ""),
            str(row.get("raw_id") or ""))


def load_cursor() -> dict:
    if not CURSOR_PATH.exists():
        return {}
    try:
        return json.loads(CURSOR_PATH.read_text(encoding="utf-8")).get("per_source", {})
    except (json.JSONDecodeError, OSError):
        # A corrupt cursor is not licence to re-type the corpus. Refuse loudly.
        raise ValueError(
            f"REFUSED: {CURSOR_PATH} exists and is not readable JSON. Repair or "
            "delete it deliberately -- starting from scratch silently would "
            "duplicate every row already typed.") from None


def save_cursor(per_source: dict, *, rows_written: int) -> None:
    """The cursor, with the running totals CARRIED not reset.

    A total that restarted every run would read as "L2 has typed 200 rows" after
    a night that typed 200 of 6,020.
    """
    TYPED.mkdir(parents=True, exist_ok=True)
    prior = {}
    if CURSOR_PATH.exists():
        try:
            prior = json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prior = {}
    CURSOR_PATH.write_text(json.dumps({
        "job": JOB,
        "per_source": per_source,
        "rows_written_total": int(prior.get("rows_written_total", 0)) + int(rows_written),
        "runs": int(prior.get("runs", 0)) + 1,
        "last_run_utc": _now(),
        "note": ("the last (first_seen_utc, raw_id) typed per source. A run types "
                 "rows strictly after it; there is no other mode."),
    }, indent=1, sort_keys=True), encoding="utf-8")


def pending(rows: list[dict], cursor: dict) -> list[dict]:
    """Rows strictly after the cursor, in `(source, first_seen_utc, raw_id)` order."""
    out = []
    for row in rows:
        src, seen, rid = row_key(row)
        mark = cursor.get(src)
        if mark is not None and [seen, rid] <= list(mark):
            continue
        out.append(row)
    return sorted(out, key=row_key)


def scope_of(row: dict) -> tuple[str, str]:
    """The entity the direction is relative to.

    One row per document (spec section 2.4), so a document tagged with several
    tickers is scoped to the FIRST and carries the rest in `tickers` -- fanning
    one document into N per-ticker rows would multiply one reading into N
    correlated ones and make every count a function of tagging density. A
    document with no ticker is a macro document, scoped to `MARKET`.
    """
    tickers = [str(t).strip().upper() for t in (row.get("tickers") or []) if str(t).strip()]
    if tickers:
        return tickers[0], "ticker"
    return "MARKET", "macro_topic"


def document_date(row: dict) -> str:
    """The PIT anchor shown to the model -- the N-C join's OWN rule, imported.

    `night_e1_news_return_panel._anchor`: a `native_stamp` row is anchored on
    `published_utc` and everything else on `first_seen_utc`. Re-deriving it here
    would have been wrong in the expensive direction: the Alpaca backfill's
    3,799 rows were all first seen on 2026-09-11 and published from 2015-01-01
    on, so anchoring them on `first_seen_utc` would date a 2015 article to the
    day we downloaded it, show the model the wrong decade, and stack every typed
    row of the backfill onto one session. That function's own docstring calls it
    nonsense, which is how this was caught before the first call was paid for.

    A typed row therefore carries the SAME date the E1 panel gives the same
    document; `test_l2_typed_events.py` pins the two against each other.
    """
    from scripts.night_e1_news_return_panel import _anchor
    stamp, _field = _anchor(row)
    return str(stamp or "")[:10]


def anchor_field(row: dict) -> str:
    """Which field `document_date` came from -- `published_utc` or
    `first_seen_utc`. On the row, because a date whose provenance is implicit is
    a date somebody will re-derive incorrectly."""
    from scripts.night_e1_news_return_panel import _anchor
    return _anchor(row)[1]


def prompt_for(row: dict) -> str:
    scope, kind = scope_of(row)
    return ex.user_prompt(scope=scope, scope_kind=kind, document_date=document_date(row),
                          source_feed=str(row.get("source") or ""),
                          title=str(row.get("title") or ""),
                          body=str(row.get("body") or ""))


def inputs_fingerprint(rows: list[dict]) -> dict:
    """A hash of the exact document list, so the run that happens when the reader
    is up can prove it asked these documents and not similar ones."""
    payload = json.dumps([list(row_key(r)) for r in rows], separators=(",", ":"))
    return {"n_rows": len(rows),
            "inputs_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()}


# ------------------------------------------------------------------ projection

def projection(rows: list[dict]) -> dict:
    """Wall time for `rows`, three ways, with what each assumes stated.

    Prefill is not a rounding term: at L4's contended 5.6 tok/s prompt-eval rate
    it is 96% of the naive total, which is exactly what that receipt found for
    panel B (25.6 days against the incumbent's 3.9 hours). But the system prompt
    is BYTE-IDENTICAL across all 6,020 calls, and llama.cpp reuses a cached
    common prefix, so the naive figure charges ~725 tokens per row that the
    server pays once. Both are given, and so is the only EMPIRICAL anchor this
    repo has -- R2 panel A's own usage block, 15,433 calls in 5,854.2 s on the
    incumbent 7B. A single number here would be a guess wearing two decimals.
    """
    system_chars = len(ex.SYSTEM_PROMPT)
    user_chars = sum(len(prompt_for(r)) for r in rows)
    n = max(1, len(rows))
    naive_prompt_tokens = (user_chars + system_chars * len(rows)) / CHARS_PER_TOKEN
    cached_prompt_tokens = (user_chars + system_chars) / CHARS_PER_TOKEN
    out_tokens = len(rows) * EST_OUT_TOKENS_PER_ROW
    per_rate = {}
    for name, rate in RATES.items():
        gen_s = out_tokens / rate["generation_tok_s"]
        naive_s = naive_prompt_tokens / rate["prompt_eval_tok_s"]
        cached_s = cached_prompt_tokens / rate["prompt_eval_tok_s"]
        per_rate[name] = {
            "prompt_eval_tok_s": rate["prompt_eval_tok_s"],
            "generation_tok_s": rate["generation_tok_s"],
            "generation_hours": _r(gen_s / 3600, 2),
            "prefill_hours_no_prefix_cache": _r(naive_s / 3600, 2),
            "prefill_hours_system_prefix_cached_once": _r(cached_s / 3600, 2),
            "total_hours_no_prefix_cache": _r((naive_s + gen_s) / 3600, 2),
            "total_hours_with_prefix_cache": _r((cached_s + gen_s) / 3600, 2),
            "seconds_per_row_no_prefix_cache": _r((naive_s + gen_s) / n, 2),
        }
    # R2 panel A, MEASURED: 0.379 s per call at mean 330.4 prompt / 14.0
    # completion tokens on the incumbent. L2 asks for ~120 completion tokens, so
    # the extra generation is added at the incumbent's own measured rate.
    r2_s_per_call = 0.379
    empirical_s = len(rows) * (r2_s_per_call +
                               max(0, EST_OUT_TOKENS_PER_ROW - 14) /
                               RATES["qwen2_5_7b_incumbent"]["generation_tok_s"])
    return {
        "rows": len(rows),
        "estimated_prompt_tokens_no_prefix_cache": int(naive_prompt_tokens),
        "estimated_prompt_tokens_with_prefix_cache": int(cached_prompt_tokens),
        "estimated_output_tokens_total": int(out_tokens),
        "assumptions": {
            "chars_per_token": CHARS_PER_TOKEN,
            "output_tokens_per_row": EST_OUT_TOKENS_PER_ROW,
            "system_prompt_chars": system_chars,
            "rates_source": ("night_factory_2026-09-13/L4_qwen3_measure_run01.json, "
                             "`contended_measurement_being_superseded` -- itself a "
                             "LOWER BOUND (20 cores saturated when it was taken)"),
            "prefix_cache": ("the system prompt is byte-identical across every call, so "
                             "llama.cpp pays it once; the no-cache column charges it "
                             "per row and is the pessimistic bound"),
        },
        "per_rate": per_rate,
        "generation_only_at_20_tok_s_hours": _r(out_tokens / 20.0 / 3600, 2),
        "empirical_anchor_r2_panelA": {
            "source": ("L4 receipt `wall_time.source`: R2 panel A's own usage block, "
                       "15,433 calls in 5,854.2 s, mean 330.4 prompt / 14.0 completion "
                       "tokens on Qwen2.5-7B"),
            "measured_seconds_per_call": r2_s_per_call,
            "l2_hours": _r(empirical_s / 3600, 2),
            "caveat": ("R2's completions are 14 tokens and L2's are ~120, so only the "
                       "prefill half of this transfers; the generation half is added at "
                       "the incumbent's measured 41.4 tok/s"),
        },
    }


# ----------------------------------------------------------------------- kappa

def cohens_kappa(a, b) -> float | None:
    """Unweighted Cohen's kappa over a categorical pair. `None` when undefined."""
    a, b = list(a), list(b)
    if len(a) != len(b) or not a:
        return None
    cats = sorted(set(a) | set(b))
    idx = {c: i for i, c in enumerate(cats)}
    n = len(a)
    m = np.zeros((len(cats), len(cats)), dtype=float)
    for x, y in zip(a, b):
        m[idx[x], idx[y]] += 1
    po = float(np.trace(m)) / n
    pe = float((m.sum(axis=0) * m.sum(axis=1)).sum()) / (n * n)
    if pe == 1.0:
        return None
    return (po - pe) / (1.0 - pe)


def weighted_kappa(a, b, categories) -> float | None:
    """Linearly weighted kappa over an ORDINAL scale (`direction`, the buckets).

    Linear, not quadratic: the spec names linear weights, and quadratic would
    make one two-bucket disagreement cost four times a one-bucket one, which is
    a claim about the scale nobody has made.
    """
    a, b = list(a), list(b)
    if len(a) != len(b) or not a:
        return None
    order = {c: i for i, c in enumerate(categories)}
    if any(x not in order for x in a + b):
        return None
    k = len(categories)
    n = len(a)
    obs = np.zeros((k, k), dtype=float)
    for x, y in zip(a, b):
        obs[order[x], order[y]] += 1
    w = np.abs(np.subtract.outer(np.arange(k), np.arange(k))).astype(float) / (k - 1)
    exp = np.outer(obs.sum(axis=1), obs.sum(axis=0)) / n
    den = float((w * exp).sum())
    if den == 0:
        return None
    return 1.0 - float((w * obs).sum()) / den


def agreement(rows_a: list[dict], rows_b: list[dict]) -> dict:
    """The inter-rater block: kappa on the three enums, MAD on confidence."""
    pairs = [(a, b) for a, b in zip(rows_a, rows_b) if a is not None and b is not None]
    if not pairs:
        return {"n": 0, "note": "no row was typed by both prompts"}
    ta = [a["event_type"] for a, _ in pairs]
    tb = [b["event_type"] for _, b in pairs]
    da = [a["direction"] for a, _ in pairs]
    db = [b["direction"] for _, b in pairs]
    ma = [a["magnitude_bucket"] for a, _ in pairs]
    mb = [b["magnitude_bucket"] for _, b in pairs]
    ca = np.array([float(a["confidence"]) for a, _ in pairs])
    cb = np.array([float(b["confidence"]) for _, b in pairs])
    return {
        "n": len(pairs),
        "kappa_event_type": _r(cohens_kappa(ta, tb)),
        "kappa_direction_linear": _r(weighted_kappa(da, db, list(vocab.DIRECTIONS))),
        "kappa_magnitude_linear": _r(weighted_kappa(ma, mb, list(vocab.MAGNITUDE_BUCKETS))),
        "confidence_mean_abs_difference": _r(float(np.abs(ca - cb).mean())),
        "raw_agreement_event_type": _r(float(np.mean([x == y for x, y in zip(ta, tb)]))),
        "protocol": vocab.KAPPA_PROTOCOL,
    }


# ------------------------------------------------------------------- the writer

def typed_record(row: dict, typed: ex.TypedEventRow, *, backend: str, variant: str) -> dict:
    scope, kind = scope_of(row)
    return {
        "source": row.get("source"), "raw_id": row.get("raw_id"),
        "first_seen_utc": row.get("first_seen_utc"),
        "published_utc": row.get("published_utc"),
        "pit_grade": row.get("pit_grade"),
        "document_date": document_date(row),
        "document_date_field": anchor_field(row),
        "scope": scope, "scope_kind": kind,
        "tickers": list(row.get("tickers") or []),
        "url": row.get("url"),
        **typed.as_dict(),
        "prompt_variant": variant, "backend": backend, "typed_utc": _now(),
    }


def refusal_record(row: dict, refusal: ex.Refusal, *, backend: str, variant: str) -> dict:
    return {
        "source": row.get("source"), "raw_id": row.get("raw_id"),
        "first_seen_utc": row.get("first_seen_utc"),
        "reason": refusal.reason, "detail": refusal.detail, "raw": refusal.raw,
        "prompt_variant": variant, "backend": backend, "refused_utc": _now(),
    }


def _append(path: Path, records: list[dict]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_manifest() -> dict:
    """MANIFEST.json -- tracked, beside gitignored data. Shape, counts, hashes."""
    TYPED.mkdir(parents=True, exist_ok=True)
    files = []
    total = 0
    for path in sorted(TYPED.glob("*.jsonl")):
        n = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        files.append({"file": path.name, "rows": n,
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        if not path.name.endswith("_refusals.jsonl"):
            total += n
    payload = {
        "job": JOB,
        "what": ("one typed row per corpus document, L2's frozen vocabulary. The "
                 ".jsonl files are DATA and are gitignored; this manifest is tracked."),
        "typed_rows_total": total,
        "files": files,
        "vocabulary_hash": vocab.VOCABULARY_HASH,
        "prompt_hash_A": ex.PROMPT_HASH,
        "prompt_hash_B": ex.PROMPT_HASH_B,
        "schema": "aegis://schemas/typed_event_row.json",
        "rebuild": "python -m scripts.night_l2_typed_events --max-rows 0",
        "written_utc": _now(),
    }
    MANIFEST_PATH.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return payload


# ------------------------------------------------------------------- the job

def _probe(backend: str) -> str | None:
    """Is the reader answering? Never starts it, never stops it."""
    from backend.services.free_inference import complete
    from backend.services.model_provider import LanguageRefused, ProviderRefusal
    try:
        complete(backend, "Answer with the single word OK.",
                 system="Answer in English.", max_tokens=4, temperature=0.0,
                 purpose="L2_probe")
        return None
    except (ProviderRefusal, LanguageRefused) as exc:
        return f"{type(exc).__name__}: {exc}"


def L2_typed_events(backend: str = ex.BACKEND, max_rows: int = 0, run: int = 1,
                    smoke: bool = False, kappa_rows: int = KAPPA_ROWS,
                    complete=None, probe=None) -> dict:
    """Type every corpus row after the cursor. `complete`/`probe` are injectable
    so the tests pin the cursor, the counting and the refusal classes without a
    model -- and without ever starting one."""
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sources = label_sources()
    files = corpus_files(sources)
    rows, unreadable = read_rows(files)
    cursor = load_cursor()
    waiting = pending(rows, cursor)
    if smoke:
        waiting = waiting[:8]
    elif max_rows:
        waiting = waiting[:int(max_rows)]

    base = {
        "job": JOB, "lane": "L", "licence": LICENCE, "run": run, "smoke": bool(smoke),
        "llm_spend_usd": 0.0, "backend": backend,
        "question": ("What typed event, if any, does each corpus document carry, "
                     "as a row that is numeric by construction?"),
        "contract": ex.declaration(),
        "corpus": {
            "label_sources": sources,
            "files": len(files),
            "rows_on_disk": len(rows),
            "unreadable_lines": len(unreadable),
            "unreadable_examples": unreadable[:3],
            "rows_already_typed": len(rows) - len(pending(rows, cursor)),
            "rows_waiting": len(pending(rows, cursor)),
            "rows_this_run": len(waiting),
            "eligibility": ("news_registry.label_sources() only -- a row that cannot "
                            "label a return may not become a feature"),
        },
        "cursor_file": str(CURSOR_PATH),
        "inputs_frozen": inputs_fingerprint(waiting),
        "projection": projection(waiting) if waiting else {"rows": 0},
        "one_row_per_document": (
            "a document tagged with several tickers is scoped to the FIRST and "
            "carries the rest; fanning it into N rows would multiply one reading "
            "into N correlated ones"),
    }

    if not waiting:
        return {**base, "status": "done",
                "verdict": ("NOTHING TO DO: every eligible corpus row is already typed "
                            f"at cursor {json.dumps(cursor, sort_keys=True)}"),
                "headline": f"0 rows waiting of {len(rows):,} on disk",
                "manifest": write_manifest(),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    frozen = OUT_DIR / f"{JOB}_run{run:02d}{'_smoke' if smoke else ''}_inputs.json"
    frozen.write_text(json.dumps(
        {"job": JOB, "run": run, **base["inputs_frozen"],
         "keys": [list(row_key(r)) for r in waiting], "written_utc": _now()},
        indent=1), encoding="utf-8")
    base["inputs_frozen"]["file"] = str(frozen)

    refusal = (probe or _probe)(backend)
    if refusal is not None:
        proj = base["projection"]["per_rate"]["qwen3_30b_a3b_contended"]
        emp = base["projection"]["empirical_anchor_r2_panelA"]
        return {**base, "status": "PENDING_MODEL",
                "verdict": (
                    f"PENDING_MODEL: {len(waiting):,} eligible corpus rows are frozen at "
                    f"sha256 {base['inputs_frozen']['inputs_sha256'][:12]} and NO model "
                    "call was made. The reader is not answering and this job does not "
                    f"start it. Probe said: {refusal}"),
                "headline": (
                    f"{len(waiting):,} rows waiting from {len(sources)} label sources; "
                    f"{base['projection']['generation_only_at_20_tok_s_hours']} h of "
                    "generation alone at 20 tok/s, "
                    f"{proj['total_hours_with_prefix_cache']} h with the system prefix "
                    f"cached and {proj['total_hours_no_prefix_cache']} h without, "
                    f"{emp['l2_hours']} h at R2's own measured throughput; $0.00"),
                "pending_when_the_reader_is_up": [
                    f"one call per row: {len(waiting):,} at prompt hash {ex.PROMPT_HASH[:12]}",
                    f"a re-prompt of {kappa_rows} of them at hash {ex.PROMPT_HASH_B[:12]}, "
                    "kappa on event_type / direction / magnitude and MAD on confidence "
                    f"(the spec's own control is {KAPPA_ROWS_SPEC} rows)",
                    "refusals counted per class, never dropped; a no_event row is a "
                    "SUCCESS and is written",
                    f"one command: python -m scripts.night_l2_typed_events --max-rows "
                    f"{max_rows or len(waiting)} --run {run}",
                ],
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    if complete is None:
        from backend.services.free_inference import complete as complete_
        complete = complete_

    out_path = TYPED / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
    ref_path = TYPED / f"{datetime.now(timezone.utc):%Y-%m-%d}_refusals.jsonl"
    typed_records: list[dict] = []
    refusal_records: list[dict] = []
    counts = {c: 0 for c in ex.REFUSAL_CLASSES}
    by_type: dict[str, int] = {}
    tin = tout = 0
    latest: dict[str, list[str]] = dict(cursor)
    first_pass: dict[tuple, ex.TypedEventRow] = {}

    for row in waiting:
        scope, kind = scope_of(row)
        out, usage = ex.extract(scope=scope, scope_kind=kind,
                                document_date=document_date(row),
                                source_feed=str(row.get("source") or ""),
                                title=str(row.get("title") or ""),
                                body=str(row.get("body") or ""),
                                backend=backend, complete=complete)
        tin += int(usage.get("tokens_in") or 0)
        tout += int(usage.get("tokens_out") or 0)
        src, seen, rid = row_key(row)
        if isinstance(out, ex.Refusal):
            counts[out.reason] = counts.get(out.reason, 0) + 1
            refusal_records.append(refusal_record(row, out, backend=backend, variant="A"))
        else:
            by_type[out.event_type] = by_type.get(out.event_type, 0) + 1
            typed_records.append(typed_record(row, out, backend=backend, variant="A"))
            first_pass[(src, seen, rid)] = out
        # the cursor advances on a REFUSED row too: the document was read and the
        # reader refused it, and re-reading it every night would spend the same
        # tokens on the same failure for ever. The refusal file keeps the row.
        latest[src] = [seen, rid]

    _append(out_path, typed_records)
    _append(ref_path, refusal_records)
    save_cursor(latest, rows_written=len(typed_records))

    # ---- the inter-rater control: the SAME rows, the second prompt
    sample = [r for r in waiting if row_key(r) in first_pass][:int(kappa_rows)]
    second: list[dict | None] = []
    firsts: list[dict | None] = []
    kappa_refusals = 0
    for row in sample:
        scope, kind = scope_of(row)
        out, usage = ex.extract(scope=scope, scope_kind=kind,
                                document_date=document_date(row),
                                source_feed=str(row.get("source") or ""),
                                title=str(row.get("title") or ""),
                                body=str(row.get("body") or ""),
                                backend=backend, variant="B", complete=complete)
        tin += int(usage.get("tokens_in") or 0)
        tout += int(usage.get("tokens_out") or 0)
        if isinstance(out, ex.Refusal):
            kappa_refusals += 1
            continue
        second.append(out.as_dict())
        firsts.append(first_pass[row_key(row)].as_dict())

    inter = agreement(firsts, second)
    inter["refused_on_the_second_prompt"] = kappa_refusals
    inter["sample_size_asked_for"] = int(kappa_rows)
    inter["spec_control_size"] = KAPPA_ROWS_SPEC

    n_typed = len(typed_records)
    n_ref = sum(counts.values())
    rate = (n_ref / (n_typed + n_ref)) if (n_typed + n_ref) else None
    return {
        **base,
        "status": "done",
        "results": {
            "rows_read": len(waiting),
            "rows_typed": n_typed,
            "refused": counts,
            "refusal_rate": _r(rate),
            "by_event_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
            "no_event_rows": by_type.get("no_event", 0),
            "no_event_share": _r(by_type.get("no_event", 0) / n_typed) if n_typed else None,
            "evidence_span_verbatim_rate": _r(
                float(np.mean([bool(r["evidence_span_verbatim"]) for r in typed_records]))
            ) if typed_records else None,
            "output_file": str(out_path),
            "refusal_file": str(ref_path) if refusal_records else None,
        },
        "inter_rater": inter,
        "usage": {"tokens_in": tin, "tokens_out": tout, "cost_usd": 0.0,
                  "purpose": ex.PURPOSE, "backend": backend},
        "manifest": write_manifest(),
        "verdict": (
            f"{n_typed:,} rows typed, {n_ref} refused "
            f"({', '.join(f'{k}={v}' for k, v in counts.items() if v)} or none), "
            f"event_type kappa {inter.get('kappa_event_type')} on {inter.get('n')} "
            "re-prompted rows"),
        "headline": (
            f"{n_typed:,} typed / {len(waiting):,} read; "
            f"{_r((by_type.get('no_event', 0) / n_typed) * 100, 1) if n_typed else None}% "
            f"no_event; refusal rate {_r(rate)}; $0.00"),
        "next_test": (
            "E1 on these typed rows against E1 on the keyword proxy, same panel, "
            "same splits, same three controls -- the only changed variable being how "
            "the events were typed"),
        "elapsed_s": round(time.time() - t0, 1), "written_utc": _now(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="L2 -- type the news corpus into the frozen vocabulary")
    ap.add_argument("--backend", default=ex.BACKEND)
    ap.add_argument("--max-rows", type=int, default=0,
                    help="rows to type this run; 0 = every row after the cursor")
    ap.add_argument("--kappa-rows", type=int, default=KAPPA_ROWS)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    payload = L2_typed_events(backend=a.backend, max_rows=a.max_rows, run=a.run,
                              smoke=a.smoke, kappa_rows=a.kappa_rows)
    payload["run"] = a.run
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT_DIR / f"{JOB}_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"\n{JOB}: {payload['headline']}\n  verdict: {payload['verdict']}\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
