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
import concurrent.futures as _fut
import hashlib
import json
import os
import random
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
#: 2026-09-13: this was the LITERAL "2026-09-13", which is the same defect
#: `night_factory.py` carried for five days -- a stale default date reads
#: exactly like a chosen one, and two real receipts landed in a folder five
#: days in the past before anyone noticed. `NIGHT_RUN_DATE` is honoured so a
#: job files into the same night folder as the rest of the day; unset, it is
#: TODAY. Default-preserving on the day it was written and correct after it.
RUN_DATE = os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")

CORPUS = REPO / "backend" / "data" / "optimus" / "news_corpus"
TYPED = REPO / "backend" / "data" / "optimus" / "typed_events"
CURSOR_PATH = TYPED / "_cursor.json"
#: rows typed between two disk flushes; the cursor advances with every flush
FLUSH_EVERY = 100
MANIFEST_PATH = TYPED / "MANIFEST.json"
OUT_DIR = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"

# =========================================================================
# CHUNK 15a: THE PANEL IS A SOURCE, AND THE JOB IS CONCURRENT
# =========================================================================
#
# E1 run 2 read LLM-typed rows for the first time and 630 of 129,983 cells
# carried an event -- 0.48% -- because the typed corpus is two days old plus a
# 2015 backfill that lands outside the panel entirely. The NN's real input was
# never the corpus: it is the panel's OWN headline table, 340,465 rows over
# 163,288 distinct texts, on the same dates the labels live on.
#
# Two things follow, and they are this chunk:
#
#   `--source panel`   types the panel's texts, ONCE per distinct text, fanned
#                      back out to every (symbol, entry_date) row carrying it.
#   `--workers N`      types them concurrently, ordered-flushed, under a dollar
#                      cap read from the CALL LEDGER rather than from a local
#                      cost field that has printed $0.00 for a $2.38 run.

#: The panel E1 actually trains on. Named, not globbed: a second parquet in that
#: directory must be chosen deliberately, not by sort order.
PANEL_PARQUET = (REPO / "backend" / "data" / "optimus" / "text_return_panel"
                 / "news_returns_2025_26.parquet")
#: The `source` a panel-typed row carries. Deliberately NOT one of the news
#: registry's feed ids: these rows come from the panel builder's output, and a
#: reader that filtered them as `alpaca_benzinga_news` would be filtering on a
#: provenance the row does not have.
PANEL_SOURCE = "text_return_panel"
CURSOR_PANEL_PATH = TYPED / "_cursor_panel.json"
SOURCES = ("corpus", "panel")

#: Concurrency. 1 is the default and reproduces the sequential run row for row
#: and cursor for cursor -- `test_workers_do_not_change_the_rows_or_the_cursor`
#: pins that against a fake reader whose latency is randomised.
WORKERS = 1
#: A 429 is a request to wait, not an error to count. Exponential with FULL
#: jitter (`sleep = U(0, base * 2**attempt)`), which is the shape that stops N
#: workers retrying in lockstep after a shared rate limit.
RETRY_MAX = 4
RETRY_BASE_S = 1.0
#: Substrings that make a provider refusal a RATE LIMIT rather than a failure.
#: Matched on the message because `model_provider.complete` raises one class for
#: every transport failure and the HTTP code is in its text.
RATE_LIMIT_MARKERS = ("429", "rate limit", "rate_limit", "too many requests",
                      "overloaded", "capacity")

#: MEASURED 2026-09-13 from `backend/data/optimus/llm_calls_2026-09.jsonl`,
#: purpose `l2_event_extraction`, 7,565 DeepSeek rows between 07:02Z and 09:18Z.
#: This is the ledger's own arithmetic, not a receipt's claim -- the receipt for
#: that run printed $0.00 (see `spend_from_ledger`).
MEASURED = {
    "source": ("backend/data/optimus/llm_calls_2026-09.jsonl, purpose="
               "l2_event_extraction, 2026-09-13T07:02Z..09:18Z"),
    "rows": 7565,
    "cost_usd": 2.38436737,
    "usd_per_row": 0.00031518,
    "tokens_in_mean": 1482.67,
    "tokens_out_mean": 49.81,
    "cached_tokens_mean": 0.0,
    "latency_ms_mean": 1045.64,
    "rows_per_min_serial": 57.4,
    "model": "deepseek-chat",
    "caveat": ("`cached_tokens` was 0 on every one of the 7,565 rows, so the "
               "measured $/row credits NO prefix cache. It is therefore an "
               "UPPER bound for a run that gets one, and the reconciliation "
               "against the provider's balance stays scripts/llm_cost_audit.py"),
}
#: The brief's planning rate and the ledger's measured one, both carried. 20 is
#: the wall-clock figure a supervised run produced; 57.4 is what the per-call
#: latency in the ledger implies. A projection printed at one of them only would
#: be off by 2.9x in whichever direction the reader did not expect.
ROWS_PER_MIN_PER_WORKER = 20.0

#: DeepSeek list prices, per 1M tokens, `docs/research_notes/2026-09-13/
#: research_cloud_llm_readers.md` section 3 (scraped from
#: api-docs.deepseek.com/quick_start/pricing on 2026-09-13). PUBLISHED prices;
#: `config.LLM_PRICE_PER_MTOK` holds this repo's own DERIVED rates from the
#: balance ledger and is what telemetry actually bills at. The dry run prints
#: BOTH, because they disagree and the disagreement is the point: a projection
#: quoted at one table and reconciled against the other is a projection nobody
#: can check.
DEEPSEEK_PRICE_PER_MTOK = {
    "deepseek-v4-flash_offpeak": {"cached_in": 0.003, "in": 0.15, "out": 0.60},
    "deepseek-v4-flash_peak": {"cached_in": 0.006, "in": 0.30, "out": 1.20},
    "deepseek-v4-pro_offpeak": {"cached_in": 0.022, "in": 0.66, "out": 1.98},
    "deepseek-v4-pro_peak": {"cached_in": 0.044, "in": 1.32, "out": 3.96},
}
DEEPSEEK_PEAK_HOURS_UTC = ("01:00-04:00 and 06:00-10:00 UTC, Mon-Fri "
                           "(research_cloud_llm_readers.md section 3)")

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


# ------------------------------------------------------- what the ledger says

def spend_from_ledger(since_utc: str, *, purpose: str = ex.PURPOSE,
                      path: Path | None = None) -> dict:
    """Dollars spent on THIS PURPOSE since `since_utc`, from the CALL LEDGER.

    THE FIELD THIS REPLACES PRINTED $0.00 FOR A $2.38 RUN. `L2_typed_events`
    carried a literal `"llm_spend_usd": 0.0` and a literal `"cost_usd": 0.0` in
    its receipt, so the 2026-09-13 DeepSeek run -- 7,565 calls, $2.384 by the
    ledger's own arithmetic -- reported as free. A spend field that is a
    constant is not a measurement, and a reader who trusts it under-counts in
    the one direction a cost line must never fail in.

    The ledger is the only local object that knows: `free_inference.complete`
    writes one row per wire attempt through `llm_telemetry.record_call`,
    INCLUDING refused ones, priced from `config.LLM_PRICE_PER_MTOK`. It is still
    an ESTIMATE (list-price reconstruction, `cost_is_estimate=True` on every
    row); `scripts/llm_cost_audit.py` against the provider's own balance stays
    the ground truth. Estimate-from-the-ledger beats constant-zero; it does not
    beat the reconciliation.

    Timestamps are compared on their first 19 characters, which is
    `YYYY-MM-DDTHH:MM:SS` -- the ledger writes microseconds and `_now()` does
    not, and a full lexical compare would silently drop the first second of a
    run. Both are UTC (`+00:00`), which is what makes a text compare legitimate
    at all.
    """
    from backend.services import llm_telemetry as tel
    cut = str(since_utc or "")[:19]
    usd = tin = tout = cached = 0.0
    calls = 0
    for row in tel.read_calls(path=path):
        if str(row.get("purpose") or "") != purpose:
            continue
        if str(row.get("ts") or "")[:19] < cut:
            continue
        calls += 1
        usd += float(row.get("cost_usd") or 0.0)
        tin += float(row.get("tokens_in") or 0)
        tout += float(row.get("tokens_out") or 0)
        cached += float(row.get("cached_tokens") or 0)
    return {
        "usd": round(usd, 6), "calls": calls,
        "tokens_in": int(tin), "tokens_out": int(tout),
        "cached_tokens": int(cached),
        "since_utc": since_utc, "purpose": purpose,
        "source": "backend/services/llm_telemetry.read_calls()",
        "note": ("a list-price reconstruction from the call ledger, not a bill. "
                 "`scripts/llm_cost_audit.py --snapshot` reconciles against the "
                 "provider's own balance and is the ground truth"),
    }


class _RunCap:
    """A per-RUN dollar cap, checked BEFORE every submission.

    THE SAME SHAPE AS `lab_budget.guard`, deliberately, and not the same object:
    that one caps a UTC DAY across every lab caller at `config.
    LAB_DAILY_SPEND_CAP_USD` ($3.00). This one caps ONE INVOCATION at whatever
    `--max-usd` says, because the run Fable has to make is $8 and then $50 and a
    day cap that refused it would be a gate that cannot go green. Both can bind;
    neither replaces the other, and the receipt names which one was in force.

    Refuse BEFORE the call, never refund after -- a call that was made and then
    regretted has already been billed.

    THE CAP READS THE LEDGER THE WRITER WRITES (chunk 22c, 2026-09-21). This
    class takes `purpose` and it is NOT optional-by-accident: `refresh()` used
    to call `spend_from_ledger(self.since_utc, path=...)` with the function's
    DEFAULT purpose, which is L2's `l2_event_extraction`. L2 itself was never
    wrong -- its cap and its receipt both fell back to that same default, so the
    two agreed -- but N9 imported this class, passed its own `since_utc`, and
    inherited L2's purpose silently. N9 run 3 then spent **$10.0479 over 8,342
    calls under a $2.00 cap** whose `estimated_spend_at_stop_usd` read
    **$0.013238** after 167 reads, because it was summing whatever L2 rows
    happened to share the window. A default that is right for one caller and
    invisible to the next is the defect; `purpose` is now named at both call
    sites, and `agreement()` proves it at the first flush rather than trusting
    it.

    THE LEDGER IS READ PER FLUSH, NOT PER ROW. `read_calls()` is 1.4 s cold and
    0.02 s warm over 121,982 rows, and the filter is another ~30 ms; paying that
    per row would cost more than the row. Between reads the running total is the
    last ledger figure plus the measured $/row for what has been submitted
    since, so the check before EVERY submission is against a number that only
    ever over-states spend -- which is the safe direction for a cap.
    """

    def __init__(self, max_usd: float | None, *, backend: str, since_utc: str,
                 refresh_every: int = FLUSH_EVERY, ledger_path: Path | None = None,
                 purpose: str = ex.PURPOSE):
        from backend.services import lab_budget
        self.max_usd = None if max_usd is None else float(max_usd)
        self.backend = backend
        self.metered = backend not in lab_budget.UNMETERED_BACKENDS
        self.since_utc = since_utc
        self.refresh_every = max(1, int(refresh_every))
        self.ledger_path = ledger_path
        self.purpose = str(purpose)
        self.usd_per_row = float(MEASURED["usd_per_row"])
        self.usd_per_row_source = "MEASURED 2026-09-13 ledger mean"
        self.ledger_usd = 0.0
        self.ledger_calls = 0
        self.submitted_since_read = 0
        self.rows_submitted = 0
        self.reads = 0
        self.first_flush_agreement: dict | None = None
        if self.metered:
            self.refresh()

    def refresh(self) -> float:
        """Re-read the ledger and re-derive $/row from THIS RUN's own rows."""
        if not self.metered:
            return 0.0
        row = spend_from_ledger(self.since_utc, purpose=self.purpose,
                                path=self.ledger_path)
        self.ledger_usd = float(row["usd"])
        self.ledger_calls = int(row["calls"])
        self.reads += 1
        if row["calls"] >= 20 and row["usd"] > 0:
            self.usd_per_row = row["usd"] / row["calls"]
            self.usd_per_row_source = (f"THIS RUN's own ledger rows "
                                       f"({row['calls']} calls)")
        self.submitted_since_read = 0
        return self.ledger_usd

    def spend_now(self) -> float:
        return self.ledger_usd + self.submitted_since_read * self.usd_per_row

    def may_submit(self) -> bool:
        """True when one more row fits under the cap. Unmetered: always."""
        if not self.metered or self.max_usd is None:
            return True
        if self.submitted_since_read >= self.refresh_every:
            self.refresh()
        return (self.spend_now() + self.usd_per_row) <= self.max_usd

    def charge(self) -> None:
        self.submitted_since_read += 1
        self.rows_submitted += 1

    def agreement(self, receipt_row: dict | None) -> dict:
        """The CAP's read of the ledger beside the RECEIPT's, side by side.

        `receipt_row` is whatever the job's own receipt will print -- the
        caller's `spend_from_ledger(...)`, with the caller's own `since`,
        `purpose` and `path`. This method re-reads the ledger through the CAP's
        wiring and compares. The two are the same function over the same file;
        the only thing that can separate them is the ARGUMENTS, which is
        exactly the fault of 2026-09-21 (`cap_block` $0.013238 / 167 reads vs
        `spend` $10.047856 / 8,342 calls, same receipt, same file).

        Returns the block that goes on the receipt as
        `cap_block.first_flush_agreement`. The FIRST call's block is the one
        kept: a disagreement is a property of the wiring, so it is true at the
        first flush or not at all, and a later read cannot absolve it.

        An unmetered run returns `agree: True` with both reads at zero -- there
        is no bill for two readers to disagree about.
        """
        from backend import config as _cfg
        tol_usd = float(_cfg.CAP_READER_AGREEMENT_TOLERANCE_USD)
        tol_calls = int(_cfg.CAP_READER_AGREEMENT_TOLERANCE_CALLS)
        receipt_row = receipt_row or {}
        r_usd = float(receipt_row.get("usd") or 0.0)
        r_calls = int(receipt_row.get("calls") or 0)
        if self.metered:
            self.refresh()
        c_usd, c_calls = float(self.ledger_usd), int(self.ledger_calls)
        d_usd = abs(c_usd - r_usd)
        d_calls = abs(c_calls - r_calls)
        agree = (not self.metered) or (d_usd <= tol_usd and d_calls <= tol_calls)
        block = {
            "cap_usd": _r(c_usd, 6), "receipt_usd": _r(r_usd, 6),
            "cap_calls": c_calls, "receipt_calls": r_calls,
            "agree": bool(agree),
            "delta_usd": _r(d_usd, 6), "delta_calls": d_calls,
            "tolerance_usd": tol_usd, "tolerance_calls": tol_calls,
            "cap_purpose": self.purpose,
            "receipt_purpose": receipt_row.get("purpose"),
            "cap_since_utc": self.since_utc,
            "receipt_since_utc": receipt_row.get("since_utc"),
            "cap_ledger_path": (None if self.ledger_path is None
                                else str(self.ledger_path)),
            "metered": self.metered,
            "why": ("a dollar cap is only a cap if the number it compares is "
                    "the number the writer produces. Two readers of one file "
                    "that disagree by 8,000 rows is not a rounding error "
                    "(MUST NOT REGRESS §38)."),
        }
        if self.first_flush_agreement is None:
            self.first_flush_agreement = block
        return block

    def block(self) -> dict:
        return {
            "max_usd": self.max_usd,
            "backend": self.backend,
            "metered": self.metered,
            "purpose": self.purpose,
            "first_flush_agreement": self.first_flush_agreement,
            "first_flush_agreement_note": (
                "the cap's read and the receipt's read of the SAME ledger, "
                "printed side by side after the first flush of a metered run. "
                "`null` means the run never flushed under a metered backend."
                if self.first_flush_agreement is None else None),
            "estimated_spend_at_stop_usd": _r(self.spend_now(), 6),
            "usd_per_row_used": _r(self.usd_per_row, 8),
            "usd_per_row_source": self.usd_per_row_source,
            "ledger_reads": self.reads,
            "checked": ("before every submission, against the ledger total "
                        f"refreshed every {self.refresh_every} rows"),
            "also_in_force": ("lab_budget's UTC-DAY cap, but only on the "
                              "`--reader` path (lab_reader.resolve); a direct "
                              "`--backend deepseek` run is capped by --max-usd "
                              "alone"),
            "unmetered_note": (None if self.metered else
                               f"{self.backend} is local: it costs compute, not "
                               "dollars, so no dollar cap can bind"),
        }


# --------------------------------------------------------------- the panel

def panel_anchor(row: dict) -> tuple[str, str]:
    """The PIT anchor of one PANEL row, and the field it came from.

    THE PANEL'S OWN, NOT RE-DERIVED. `night_e1_news_return_panel` already ran
    `_anchor` when it built the table and wrote the answer into
    `pit_anchor_utc` / `pit_anchor_field`; where it did (808 of 340,465 rows)
    that value is taken verbatim. The other 339,657 rows predate those columns
    and carry `published_utc`, which for a wire feed IS the publisher's own
    first-publish stamp -- the same thing `_anchor` returns for a
    `native_stamp` row.

    This matters for the same reason it mattered in the corpus: an anchor taken
    from the day WE downloaded a 2015 article dates it to the wrong decade and
    stacks a whole backfill onto one session.
    """
    a = str(row.get("pit_anchor_utc") or "").strip()
    if a:
        return a, str(row.get("pit_anchor_field") or "pit_anchor_utc")
    pub = str(row.get("published_utc") or "").strip()
    if pub:
        return pub, "published_utc"
    return str(row.get("first_seen_utc") or "").strip(), "first_seen_utc"


def load_panel(path: Path | None = None):
    """The panel as a DataFrame, with every column this job needs present."""
    import pandas as pd
    p = Path(path or PANEL_PARQUET)
    if not p.exists():
        raise FileNotFoundError(
            f"REFUSED: {p} does not exist. `--source panel` types the panel's "
            "OWN headline table; without it there is nothing to type, and "
            "falling back to the corpus would silently answer a different "
            "question than the one asked.")
    df = pd.read_parquet(p)
    for col in ("uid", "symbol", "published_utc", "entry_date", "source",
                "title", "body", "pit_anchor_utc", "pit_anchor_field",
                "pit_grade", "first_seen_utc", "publish_position"):
        if col not in df.columns:
            df[col] = None
    return df


def symbol_frequency_buckets(df) -> dict:
    """Each symbol -> `Q1`..`Q4` by how many panel rows it carries.

    The stratifier's second axis. A subset drawn without it is a subset of the
    mega-caps: the panel's busiest symbol carries thousands of rows and its
    quietest carries one, so uniform sampling over ROWS buys the same few names
    over and over. Ranked before cutting (`method="first"`) so the heavy ties at
    one row a symbol do not collapse three of the four buckets.
    """
    import pandas as pd
    counts = df.groupby("symbol").size().sort_index()
    if counts.empty:
        return {}
    ranks = counts.rank(method="first")
    try:
        cut = pd.qcut(ranks, 4, labels=["Q1", "Q2", "Q3", "Q4"])
    except ValueError:                       # fewer symbols than buckets
        cut = pd.Series(["Q1"] * len(counts), index=counts.index)
    return {str(k): str(v) for k, v in cut.items()}


def panel_units(df=None, *, path: Path | None = None) -> list[dict]:
    """One unit per DISTINCT TEXT, carrying every panel cell that repeats it.

    THE UNIT OF TYPING IS THE TEXT, NOT THE ROW. The panel's 340,465 rows hold
    163,288 distinct texts: one wire story arrives once per tagged symbol. Typing
    per row would buy the same reading 2.08 times on average and bill for it --
    ~$107 at the measured rate against ~$51 for the texts.

    THE FAN-OUT IS CARRIED, NOT RE-DERIVED. `panel_cells` is every
    `(symbol, entry_date)` the text appears on, taken from the panel's OWN
    `entry_date` column, which the N-C join computed from the open time and the
    publish position. `learner.event_head.typed_events` emits one event row per
    carried cell; it never recomputes a session from a date, because
    `entry_date` for a pre-bell headline is the SAME day and the corpus path's
    "first session strictly after" rule would put it one session late.

    WHAT THE FAN-OUT COSTS, STATED: `scope` is the representative symbol (the
    first by `(published_utc, uid, symbol)`, deterministic), and `direction` was
    read relative to it. 116,247 of the 163,288 texts appear exactly once, so
    the question only arises for the 39,209 texts that span more than one
    symbol; for those the sign read for the scope entity is carried to the other
    tagged names unchanged, and the receipt counts them. The alternative is
    typing 340,465 rows at 2.08x the bill to ask the same document about each of
    its tickers separately -- a real experiment, and not this one.
    """
    if df is None:
        df = load_panel(path)
    if len(df) == 0:
        return []
    work = df.copy()
    work["title"] = work["title"].fillna("").astype(str)
    work["body"] = work["body"].fillna("").astype(str)
    work["published_utc"] = work["published_utc"].fillna("").astype(str)
    work["entry_date"] = work["entry_date"].astype(str).str.slice(0, 10)
    work["uid"] = work["uid"].fillna("").astype(str)
    work["symbol"] = work["symbol"].fillna("").astype(str)
    # Hash ONCE per distinct (title, body) pair rather than once per row.
    # `text_sha256` collapses whitespace over title-newline-body, so the join
    # and this join's space normalise to the same byte and the joined string
    # hashes identically to the pair -- pinned by
    # `test_the_joined_hash_equals_the_pair_hash`.
    pair = work["title"] + " " + work["body"]
    lookup = {k: ex.text_sha256(k, "") for k in pair.unique()}
    work["text_sha256"] = pair.map(lookup)
    buckets = symbol_frequency_buckets(work)
    work = work.sort_values(["text_sha256", "published_utc", "uid", "symbol"],
                            kind="mergesort")

    units: list[dict] = []
    for h, grp in work.groupby("text_sha256", sort=True):
        head = grp.iloc[0]
        row = {k: head.get(k) for k in
               ("uid", "symbol", "published_utc", "entry_date", "source",
                "pit_anchor_utc", "pit_anchor_field", "pit_grade",
                "first_seen_utc", "publish_position")}
        stamp, field = panel_anchor(row)
        cells = sorted({(str(s), str(d)) for s, d in
                        zip(grp["symbol"], grp["entry_date"])})
        units.append({
            "text_sha256": h,
            "title": str(head["title"]), "body": str(head["body"]),
            "scope": str(head["symbol"]) or "MARKET",
            "scope_kind": "ticker" if str(head["symbol"]) else "macro_topic",
            "document_date": str(stamp)[:10],
            "document_date_field": field,
            "source_feed": str(head.get("source") or ""),
            "panel_uid": str(head["uid"]),
            "panel_entry_date": str(head["entry_date"]),
            "panel_cells": [list(c) for c in cells],
            "panel_rows": int(len(grp)),
            "panel_symbols": int(grp["symbol"].nunique()),
            "month": str(stamp)[:7],
            "symbol_bucket": buckets.get(str(head["symbol"]), "Q1"),
        })
    units.sort(key=lambda u: (u["document_date"], u["panel_uid"], u["text_sha256"]))
    return units


def panel_typed_hashes(directory: Path | None = None) -> set[str]:
    """Every `text_sha256` already written, READ BACK FROM THE OUTPUT FILES.

    NOT from a cursor file, and that is a deliberate difference from the corpus
    path. The corpus cursor is a watermark over a total order and works because
    a corpus run always types the next N rows; `--stratified` picks a scattered
    subset by design, so a watermark would declare every text before the last
    sampled one "done" and skip 100,000 texts nobody read. A set read from the
    rows actually on disk cannot disagree with the rows actually on disk --
    which is the property a resume needs and the only one it needs.

    Refusal files count too: a text the reader refused was asked and billed, and
    re-asking it every night is the loop that 2026-09-10's replay is the
    standing lesson about.
    """
    d = Path(directory or TYPED)
    if not d.is_dir():
        return set()
    seen: set[str] = set()
    for path in sorted(d.glob("panel_*.jsonl")):
        for row in jio.iter_rows(path):
            h = row.get("text_sha256")
            if h:
                seen.add(str(h))
    return seen


def save_panel_cursor(*, typed_now: int, total_units: int, done: int,
                      run: int, stratified: int | None) -> None:
    """A RECEIPT beside the panel outputs, never the source of truth.

    `panel_typed_hashes` reads the rows themselves; this file exists so a human
    (and `MANIFEST.json`) can see where the panel stands without parsing
    163,288 rows. It says so in its own `note`, because a file called `_cursor_`
    that is not the cursor is exactly the sort of thing a later session trusts.
    """
    TYPED.mkdir(parents=True, exist_ok=True)
    prior = {}
    if CURSOR_PANEL_PATH.exists():
        try:
            prior = json.loads(CURSOR_PANEL_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prior = {}
    CURSOR_PANEL_PATH.write_text(json.dumps({
        "job": JOB, "source": "panel", "run": run,
        "panel": str(PANEL_PARQUET),
        "distinct_texts": int(total_units),
        "texts_typed_total": int(done),
        "texts_typed_this_run": int(typed_now),
        "rows_written_total": int(prior.get("rows_written_total", 0)) + int(typed_now),
        "runs": int(prior.get("runs", 0)) + 1,
        "stratified": stratified,
        "last_run_utc": _now(),
        "note": ("A RECEIPT, NOT THE RESUME. The resume is the set of "
                 "`text_sha256` values in `panel_*.jsonl` themselves "
                 "(`panel_typed_hashes`), because --stratified picks a "
                 "scattered subset and a watermark over a total order would "
                 "skip every text before the last one sampled."),
    }, indent=1, sort_keys=True), encoding="utf-8")


def stratified_pick(units: list[dict], k: int, *, seed: int = 0) -> list[dict]:
    """K texts, stratified by MONTH and by SYMBOL-FREQUENCY BUCKET, fixed seed.

    So a $7 subset is representative of the $51 whole rather than of January and
    the mega-caps. Allocation is proportional to each (month, bucket) cell's own
    population by LARGEST REMAINDER, so the parts sum to exactly K and a cell
    with 0.6 of a slot is not silently rounded out of the sample. A cell smaller
    than its allocation gives back what it cannot fill and the remainder is
    re-spread over the cells that can.

    `np.random.default_rng(seed)` (never `np.random.seed`), and the units are
    sorted by `text_sha256` inside a cell before drawing, so the draw is a
    function of the seed and the panel -- not of dict ordering.
    """
    if k <= 0 or k >= len(units):
        return list(units)
    rng = np.random.default_rng(seed)
    cells: dict[tuple, list[dict]] = {}
    for u in units:
        cells.setdefault((u["month"], u["symbol_bucket"]), []).append(u)
    keys = sorted(cells)
    sizes = np.array([len(cells[key]) for key in keys], dtype=float)
    exact = sizes / sizes.sum() * k
    take = np.floor(exact).astype(int)
    order = np.argsort(-(exact - take), kind="stable")
    for i in order[:int(k - take.sum())]:
        take[i] += 1
    take = np.minimum(take, sizes.astype(int))
    # re-spread what the small cells could not fill
    while take.sum() < k:
        room = sizes.astype(int) - take
        if not room.any():
            break
        for i in np.argsort(-room, kind="stable"):
            if take.sum() >= k:
                break
            if room[i] > 0:
                take[i] += 1
    picked: list[dict] = []
    for key, n in zip(keys, take):
        pool = sorted(cells[key], key=lambda u: u["text_sha256"])
        if n >= len(pool):
            picked.extend(pool)
            continue
        idx = rng.choice(len(pool), size=int(n), replace=False)
        picked.extend(pool[int(i)] for i in sorted(idx))
    picked.sort(key=lambda u: (u["document_date"], u["panel_uid"], u["text_sha256"]))
    return picked


def panel_typed_record(unit: dict, typed: ex.TypedEventRow, *, backend: str,
                       variant: str, model: str | None = None) -> dict:
    """One typed PANEL row, in the same shape `learner.event_head` already reads.

    `source_kind` is what keeps the two sources from double-counting a cell:
    `event_head.typed_events` keys on `(symbol, entry_date, text_sha256)` and
    keeps the first, so a headline that reached both the news corpus and the
    panel contributes ONE event to a cell rather than two.
    """
    return {
        "source": PANEL_SOURCE, "source_kind": "panel",
        "source_feed": unit.get("source_feed"),
        "panel_uid": unit.get("panel_uid"),
        "raw_id": unit.get("panel_uid"),
        "text_sha256": unit["text_sha256"],
        "document_date": unit["document_date"],
        "document_date_field": unit["document_date_field"],
        "published_utc": unit.get("published_utc"),
        "scope": unit["scope"], "scope_kind": unit["scope_kind"],
        "panel_entry_date": unit.get("panel_entry_date"),
        "panel_cells": unit.get("panel_cells") or [],
        "panel_rows": unit.get("panel_rows"),
        "panel_symbols": unit.get("panel_symbols"),
        **typed.as_dict(),
        "prompt_variant": variant, "backend": backend, "model": model,
        "typed_utc": _now(),
    }


def panel_refusal_record(unit: dict, refusal: ex.Refusal, *, backend: str,
                         variant: str, model: str | None = None) -> dict:
    return {
        "source": PANEL_SOURCE, "source_kind": "panel",
        "panel_uid": unit.get("panel_uid"),
        "text_sha256": unit["text_sha256"],
        "document_date": unit["document_date"],
        "scope": unit["scope"],
        "reason": refusal.reason, "detail": refusal.detail, "raw": refusal.raw,
        "prompt_variant": variant, "backend": backend, "model": model,
        "refused_utc": _now(),
    }


def corpus_unit(row: dict) -> dict:
    """A corpus row in the same shape the typing loop takes, so ONE loop serves
    both sources and a fix to the cursor, the cap or the retry cannot land on
    one of them only."""
    scope, kind = scope_of(row)
    return {
        "kind": "corpus", "row": row,
        "scope": scope, "scope_kind": kind,
        "document_date": document_date(row),
        "source_feed": str(row.get("source") or ""),
        "title": str(row.get("title") or ""), "body": str(row.get("body") or ""),
        "key": row_key(row),
        "text_sha256": ex.text_sha256(row.get("title") or "", row.get("body") or ""),
    }


# ------------------------------------------------------- the concurrent reader

def is_rate_limited(exc: BaseException) -> bool:
    """Is this refusal a request to WAIT rather than a failure to count?

    Matched on the message, because `model_provider.complete` raises one
    `ProviderRefusal` for every transport failure and puts the HTTP status in
    its text. A 429 answered by counting a refusal would throw away a row the
    provider was willing to serve a second later.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(m in text for m in RATE_LIMIT_MARKERS)


def extract_with_backoff(unit: dict, *, backend: str, variant: str, complete,
                         sleep=time.sleep, retries: int = RETRY_MAX,
                         jitter=None) -> tuple:
    """`ex.extract` with FULL-JITTER exponential backoff on a rate limit.

    `sleep = U(0, base * 2**attempt)` -- full jitter, not `base * 2**attempt`
    plus a little. With N workers sharing one rate limit, an unjittered backoff
    re-synchronises every worker onto the same retry instant and the second
    wave 429s exactly like the first.

    Returns `(row_or_refusal, usage, retries_used)`. Anything that is not a rate
    limit is raised: it is the run's state, not the document's, and the caller
    stops rather than billing the rest of the backlog into the same wall.
    """
    jitter = jitter or random.uniform
    attempt = 0
    while True:
        try:
            out, usage = ex.extract(
                scope=unit["scope"], scope_kind=unit["scope_kind"],
                document_date=unit["document_date"],
                source_feed=unit["source_feed"],
                title=unit["title"], body=unit["body"],
                backend=backend, variant=variant, complete=complete)
            return out, usage, attempt
        except Exception as exc:                              # noqa: BLE001
            if not is_rate_limited(exc) or attempt >= retries:
                raise
            sleep(jitter(0.0, RETRY_BASE_S * (2 ** attempt)))
            attempt += 1


def type_units(units: list[dict], *, backend: str, complete, variant: str = "A",
               workers: int = 1, flush_every: int | None = None,
               cap: "_RunCap | None" = None, on_result=None, on_flush=None,
               sleep=time.sleep, retries: int = RETRY_MAX) -> dict:
    """Type `units` concurrently, collecting and FLUSHING IN SUBMISSION ORDER.

    THE ORDER IS THE WHOLE POINT. A cursor is a claim that everything before it
    is on disk, so results may be written only in submission order: collecting
    out of order and flushing whatever finished first would advance a cursor
    past a row still in flight, and the row would never be typed again. The
    window of in-flight submissions is `2 x workers`, so the answers arrive at
    most that far out of order and the queue head is always the next row to
    write.

    THREE WAYS A RUN ENDS, and each is a different fact about the world:
      * `complete`     -- every unit was read.
      * `MAX_USD_CAP`  -- the cap refused the next submission. Everything
                          collected is flushed; nothing is lost.
      * `READER_ERROR` -- a row raised something that was not a rate limit.
                          Submission STOPS, rows strictly BEFORE it are flushed
                          and the cursor stops before it, so the next run
                          retries exactly that row. Counted as a refusal on the
                          receipt and NOT re-raised: a traceback with no receipt
                          is how a night produces nothing to read.

    `workers=1` reproduces the sequential run row for row and cursor for cursor.
    """
    flush_every = int(flush_every or FLUSH_EVERY)
    n = len(units)
    out = {
        "typed": [], "refusals": [], "counts": {c: 0 for c in ex.REFUSAL_CLASSES},
        "by_type": {}, "tokens_in": 0, "tokens_out": 0,
        "retries": 0, "rate_limited_rows": 0,
        "collected": 0, "submitted": 0,
        "discarded_after_the_failure": 0,
        "stopped": "complete", "stop_detail": None, "failed_index": None,
        "workers": int(workers),
    }
    if n == 0:
        return out
    counts = out["counts"]
    pending: list[tuple[int, dict, object]] = []
    window = max(2, int(workers) * 2)
    since_flush = 0
    nxt = 0
    stop = None

    def _task(unit):
        return extract_with_backoff(unit, backend=backend, variant=variant,
                                    complete=complete, sleep=sleep, retries=retries)

    def _flush():
        nonlocal since_flush
        if on_flush is not None:
            on_flush()
        since_flush = 0

    with _fut.ThreadPoolExecutor(max_workers=max(1, int(workers)),
                                 thread_name_prefix="l2type") as pool:
        while (nxt < n or pending) and stop is None:
            while nxt < n and len(pending) < window and stop is None:
                if cap is not None and not cap.may_submit():
                    stop = "MAX_USD_CAP"
                    out["stop_detail"] = (
                        f"the ${cap.max_usd:.2f} per-run cap refused the next "
                        f"submission at an estimated ${cap.spend_now():.4f} "
                        f"already spent on {out['submitted']:,} rows; "
                        f"{n - nxt:,} of {n:,} units were not submitted")
                    break
                pending.append((nxt, units[nxt], pool.submit(_task, units[nxt])))
                if cap is not None:
                    cap.charge()
                out["submitted"] += 1
                nxt += 1
            if not pending:
                break
            idx, unit, fut = pending.pop(0)
            try:
                res, usage, used = fut.result()
            except Exception as exc:                          # noqa: BLE001
                stop = "READER_ERROR"
                out["failed_index"] = idx
                out["stop_detail"] = f"{type(exc).__name__}: {exc}"
                counts["REFUSED_READER_ERROR"] = counts.get(
                    "REFUSED_READER_ERROR", 0) + 1
                break
            out["retries"] += int(used)
            out["rate_limited_rows"] += 1 if used else 0
            out["tokens_in"] += int(usage.get("tokens_in") or 0)
            out["tokens_out"] += int(usage.get("tokens_out") or 0)
            out["collected"] += 1
            since_flush += 1
            if on_result is not None:
                on_result(idx, unit, res, usage)
            if isinstance(res, ex.Refusal):
                counts[res.reason] = counts.get(res.reason, 0) + 1
            else:
                out["by_type"][res.event_type] = out["by_type"].get(res.event_type, 0) + 1
            if since_flush >= flush_every:
                _flush()
        # rows that other workers had already started past the failure point are
        # PAID FOR AND DISCARDED, because writing them would put the cursor past
        # the row that failed. The waste is bounded by the window and is counted
        # rather than hidden: at `2 x workers` it is 1 row at --workers 1.
        out["discarded_after_the_failure"] = len(pending)
        for _idx, _unit, fut in pending:
            fut.cancel()
    _flush()
    out["stopped"] = stop or "complete"
    return out


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

def typed_record(row: dict, typed: ex.TypedEventRow, *, backend: str, variant: str,
                 model: str | None = None) -> dict:
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
        "prompt_variant": variant, "backend": backend, "model": model, "typed_utc": _now(),
    }


def refusal_record(row: dict, refusal: ex.Refusal, *, backend: str, variant: str,
                   model: str | None = None) -> dict:
    return {
        "source": row.get("source"), "raw_id": row.get("raw_id"),
        "first_seen_utc": row.get("first_seen_utc"),
        "reason": refusal.reason, "detail": refusal.detail, "raw": refusal.raw,
        "prompt_variant": variant, "backend": backend, "model": model, "refused_utc": _now(),
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


def unit_key(unit: dict) -> tuple:
    """The identity of one unit of typing, whichever source produced it.

    Corpus: `(source, first_seen_utc, raw_id)` -- unchanged, it is the cursor's
    own ordering. Panel: `(text_return_panel, document_date, text_sha256)` --
    the TEXT, because the text is what is typed and 340,465 panel rows share
    163,288 of them.
    """
    if unit.get("kind") == "corpus":
        return row_key(unit["row"])
    return (PANEL_SOURCE, str(unit.get("document_date") or ""),
            str(unit.get("text_sha256") or ""))


def units_fingerprint(units: list[dict]) -> dict:
    """`inputs_fingerprint` over units rather than corpus rows. Same payload
    shape, so a corpus run's hash is unchanged."""
    payload = json.dumps([list(unit_key(u)) for u in units], separators=(",", ":"))
    return {"n_rows": len(units),
            "inputs_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()}


# ------------------------------------------------------------------ the estimate

def estimate(units: list[dict], *, workers: int = 1, max_usd: float | None = None,
             backend: str = "deepseek", variant: str = "A") -> dict:
    """What this run would cost and how long it would take. NO MODEL IS CALLED.

    Every number here names the table it was computed from, and the two tables
    DISAGREE: `config.LLM_PRICE_PER_MTOK` holds this repo's own rates derived
    from the provider's balance ledger (and is what telemetry actually bills
    at), while `research_cloud_llm_readers.md` section 3 holds DeepSeek's
    PUBLISHED list prices. Both are printed. A projection quoted at one table
    and reconciled against the other is a projection nobody can check.

    The third column is the one to trust: `measured_usd`, rows times the
    $0.00031518 the call ledger actually recorded per row on 2026-09-13. It is
    an UPPER bound here, because those were corpus documents with bodies and the
    panel's texts average 215 characters.
    """
    from backend import config as _cfg
    n = len(units)
    system_chars = len(ex.wire_system(variant))
    user_chars = 0
    for u in units:
        user_chars += len(ex.user_prompt(
            scope=u["scope"], scope_kind=u["scope_kind"],
            document_date=u["document_date"], source_feed=u["source_feed"],
            title=u["title"], body=u["body"]))
    denom = max(1, n)
    sys_tok = system_chars / CHARS_PER_TOKEN
    user_tok = user_chars / CHARS_PER_TOKEN
    out_tok = n * float(MEASURED["tokens_out_mean"])
    # two token accountings: the prefix charged per call, and charged once
    tok_in_nocache = user_tok + sys_tok * n
    tok_in_cached_miss = user_tok + sys_tok          # paid at the miss rate
    tok_in_cached_hit = sys_tok * max(0, n - 1)      # paid at the hit rate

    def _price(row: dict) -> dict:
        hit = float(row.get("cached_in", row.get("in", 0.0)))
        miss = float(row["in"])
        out_rate = float(row["out"])
        return {
            "input_cache_miss_per_mtok": miss,
            "input_cache_hit_per_mtok": hit,
            "output_per_mtok": out_rate,
            "usd_no_prefix_cache": _r((tok_in_nocache * miss + out_tok * out_rate) / 1e6, 4),
            "usd_with_prefix_cache": _r(
                (tok_in_cached_miss * miss + tok_in_cached_hit * hit
                 + out_tok * out_rate) / 1e6, 4),
        }

    published = {k: _price(v) for k, v in DEEPSEEK_PRICE_PER_MTOK.items()}
    repo_rates = {}
    for model in ("deepseek-chat", "deepseek-v4-flash", "deepseek-v4-pro"):
        row = _cfg.LLM_PRICE_PER_MTOK.get(model)
        if row:
            repo_rates[model] = _price(row)

    per_worker = max(1, int(workers))
    wall = {}
    for label, rpm in (("brief_planning_rate_20_per_min", ROWS_PER_MIN_PER_WORKER),
                       ("ledger_measured_57p4_per_min",
                        float(MEASURED["rows_per_min_serial"]))):
        hours = n / (rpm * per_worker) / 60.0
        wall[label] = {"rows_per_min_per_worker": rpm, "workers": per_worker,
                       "hours": _r(hours, 2), "minutes": _r(hours * 60, 1)}

    measured_usd = n * float(MEASURED["usd_per_row"])
    return {
        "no_model_was_called": True,
        "rows_to_type": n,
        "unique_texts": len({u.get("text_sha256") for u in units}),
        "panel_rows_covered": int(sum(int(u.get("panel_rows") or 0) for u in units)),
        "tokens": {
            "chars_per_token": CHARS_PER_TOKEN,
            "system_prompt_chars": system_chars,
            "system_prompt_tokens": _r(sys_tok, 1),
            "user_chars_mean": _r(user_chars / denom, 1),
            "prompt_tokens_per_row": _r((user_tok + sys_tok * n) / denom, 1),
            "prompt_tokens_total": int(tok_in_nocache),
            "prompt_tokens_charged_at_the_cache_MISS_rate": int(tok_in_cached_miss),
            "prompt_tokens_charged_at_the_cache_HIT_rate": int(tok_in_cached_hit),
            "prefix_cache_note": ("the SAME tokens are sent either way -- what a "
                                  "prefix cache changes is the RATE on the "
                                  f"{int(sys_tok)}-token system prefix, which is "
                                  "byte-identical across every call. The two cost "
                                  "columns are the same token count at two rates, "
                                  "not two token counts"),
            "output_tokens_per_row": float(MEASURED["tokens_out_mean"]),
            "output_tokens_total": int(out_tok),
            "output_tokens_source": "MEASURED, ledger mean over 7,565 rows",
            "calibration_against_the_ledger": {
                "estimated_prompt_tokens_per_row_here": _r((user_tok + sys_tok * n) / denom, 1),
                "measured_prompt_tokens_per_row_2026_09_13": MEASURED["tokens_in_mean"],
                "reading": ("the measured rows were CORPUS documents, whose bodies "
                            "run to the 2,000-char cap, and they still came in "
                            "BELOW this panel estimate -- so 4 chars/token "
                            "over-states the real tokenizer on this system prompt "
                            "and every cost column here is conservative"),
            },
            "caveat": (f"{CHARS_PER_TOKEN} chars/token is a CONVENTION, not a "
                       "tokenizer. The only honest anchor is the ledger, and it "
                       "is printed beside it"),
        },
        "cost": {
            "published_deepseek_list": published,
            "published_source": ("docs/research_notes/2026-09-13/"
                                 "research_cloud_llm_readers.md section 3, scraped "
                                 "from api-docs.deepseek.com on 2026-09-13"),
            "peak_hours_utc": DEEPSEEK_PEAK_HOURS_UTC,
            "repo_derived_rates": repo_rates,
            "repo_rates_source": ("backend/config.LLM_PRICE_PER_MTOK -- DERIVED "
                                  "from the provider's own balance ledger; this is "
                                  "what llm_telemetry bills every row at"),
            "measured_usd": _r(measured_usd, 2),
            "measured_usd_per_row": MEASURED["usd_per_row"],
            "measured_source": MEASURED["source"],
            "measured_caveat": MEASURED["caveat"],
        },
        "wall_time": wall,
        "cap": {"max_usd": max_usd, "backend": backend,
                "binds": (None if max_usd is None else
                          bool(measured_usd > float(max_usd))),
                "note": (None if max_usd is None else
                         f"at the measured $/row this run is ${measured_usd:,.2f} "
                         f"against a ${float(max_usd):,.2f} cap -- "
                         + ("the cap STOPS it early"
                            if measured_usd > float(max_usd)
                            else "the cap does not bind"))},
    }


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


def _corpus_plan(smoke: bool, max_rows: int) -> dict:
    """Everything the corpus source contributes: units, the block, the cursor."""
    sources = label_sources()
    files = corpus_files(sources)
    rows, unreadable = read_rows(files)
    cursor = load_cursor()
    waiting = pending(rows, cursor)
    n_waiting = len(waiting)
    if smoke:
        waiting = waiting[:8]
    elif max_rows:
        waiting = waiting[:int(max_rows)]
    return {
        "units": [corpus_unit(r) for r in waiting],
        "cursor": cursor,
        "cursor_file": str(CURSOR_PATH),
        "block": {
            "source": "corpus",
            "label_sources": sources,
            "files": len(files),
            "rows_on_disk": len(rows),
            "unreadable_lines": len(unreadable),
            "unreadable_examples": unreadable[:3],
            "rows_already_typed": len(rows) - n_waiting,
            "rows_waiting": n_waiting,
            "rows_this_run": len(waiting),
            "eligibility": ("news_registry.label_sources() only -- a row that cannot "
                            "label a return may not become a feature"),
        },
    }


def _panel_plan(smoke: bool, max_rows: int, stratified: int, seed: int,
                panel_path: Path | None) -> dict:
    """Everything the panel source contributes.

    THE ELIGIBILITY RULE IS DIFFERENT FROM THE CORPUS'S ON PURPOSE. A corpus row
    must come from a feed the registry marks `label_source: true`, because an
    `index_state` feed can be reordered under us. A panel row is already IN the
    labelled panel -- `night_e1_news_return_panel` applied that filter when it
    built the table, and re-applying a feed-name filter here would drop rows
    whose feed id the panel spells differently (`alpaca:benzinga`, not
    `alpaca_benzinga_news`) and silently type a third of what was asked.
    """
    units = panel_units(path=panel_path)
    total = len(units)
    done = panel_typed_hashes()
    fresh = [u for u in units if u["text_sha256"] not in done]
    n_waiting = len(fresh)
    picked = fresh
    if stratified:
        picked = stratified_pick(fresh, int(stratified), seed=seed)
    if smoke:
        picked = picked[:8]
    elif max_rows:
        picked = picked[:int(max_rows)]
    return {
        "units": picked,
        "cursor": {},
        "cursor_file": str(CURSOR_PANEL_PATH),
        "block": {
            "source": "panel",
            "panel": str(Path(panel_path or PANEL_PARQUET)),
            "panel_rows": int(sum(int(u.get("panel_rows") or 0) for u in units)),
            "distinct_texts": total,
            "texts_already_typed": total - n_waiting,
            "texts_waiting": n_waiting,
            "texts_this_run": len(picked),
            "panel_rows_this_run": int(sum(int(u.get("panel_rows") or 0)
                                           for u in picked)),
            "stratified": int(stratified) or None,
            "stratified_seed": int(seed) if stratified else None,
            "stratified_axes": ("month of the PIT anchor x symbol-frequency "
                                "quartile, largest-remainder allocation, "
                                "np.random.default_rng(seed)") if stratified else None,
            "dedupe": ("one typing per DISTINCT TEXT, fanned back out at join time "
                       "to every (symbol, entry_date) panel row carrying it; "
                       "340,465 rows over 163,288 texts is 2.08x"),
            "eligibility": ("every row the panel holds. The label-source filter is "
                            "the CORPUS's rule and was already applied by the panel "
                            "builder; re-applying it on the panel's own feed "
                            "spellings would drop rows silently"),
        },
    }


def L2_typed_events(backend: str = ex.BACKEND, max_rows: int = 0, run: int = 1,
                    smoke: bool = False, kappa_rows: int = KAPPA_ROWS,
                    complete=None, probe=None, reader: str | None = None,
                    source: str = "corpus", workers: int = WORKERS,
                    max_usd: float | None = None, stratified: int = 0,
                    seed: int = 0, dry_run: bool = False,
                    panel_path: Path | None = None, sleep=time.sleep,
                    ledger_path: Path | None = None) -> dict:
    """Type every waiting document. `complete`/`probe` are injectable so the
    tests pin the cursor, the counting and the refusal classes without a model
    -- and without ever starting one.

    `source` (chunk 15a) picks WHAT is typed: the news corpus, or the 2025-26
    return panel's own headline table. E1 run 2 read typed rows for the first
    time and found an event on 630 of 129,983 cells, because the corpus is two
    days old plus a 2015 backfill outside the panel. The panel is where the
    labels are.

    `workers` types them concurrently with ORDERED flushes; `max_usd` is a
    per-run dollar cap read from the call ledger; `dry_run` prints the estimate
    and calls nothing.

    `reader` (chunk 14) is the ALWAYS-ON LAB's hook and is None for every
    existing caller, which leaves `backend` in charge exactly as before.
    """
    t0 = time.time()
    started_utc = _now()
    reader_row: dict | None = None
    if source not in SOURCES:
        raise ValueError(f"REFUSED: --source must be one of {SOURCES}, not {source!r}")
    if reader is not None:
        from backend.services import lab_reader
        reader_row = lab_reader.resolve(rows_this_tick=int(max_rows or 0))
        if not reader_row.get("ok"):
            return {"job": JOB, "lane": "L", "licence": LICENCE, "run": run,
                    "stage": "features", "llm_spend_usd": 0.0,
                    "backend": None, "reader": reader_row,
                    "status": reader_row["refusal"],
                    "verdict": f"{reader_row['refusal']}: {reader_row['detail']}",
                    "headline": (f"{reader_row['refusal']} -- no model call was "
                                 f"made and no row was typed; $0.00"),
                    "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}
        backend = reader_row["backend"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    plan = (_corpus_plan(smoke, max_rows) if source == "corpus"
            else _panel_plan(smoke, max_rows, stratified, seed, panel_path))
    units = plan["units"]
    cursor = plan["cursor"]

    base = {
        "job": JOB, "lane": "L", "licence": LICENCE, "run": run, "smoke": bool(smoke),
        # stamped here as well as in `night_factory_jobs.JOB_STAGES`, so a direct
        # `python -m scripts.night_l2_typed_events` receipt is not an unstamped
        # row in the stage contract. L2 turns raw text into FEATURE rows; it
        # reads no price, no weight and no PnL.
        "stage": "features",
        "llm_spend_usd": 0.0, "backend": backend, "reader": reader_row,
        "source": source,
        "workers": int(workers),
        "started_utc": started_utc,
        "question": ("What typed event, if any, does each document carry, "
                     "as a row that is numeric by construction?"),
        "contract": ex.declaration(),
        "corpus": plan["block"],
        "cursor_file": plan["cursor_file"],
        "inputs_frozen": units_fingerprint(units),
        "projection": (projection([u["row"] for u in units])
                       if (units and source == "corpus") else {"rows": len(units)}),
        "estimate": estimate(units, workers=workers, max_usd=max_usd,
                             backend=backend) if units else {"rows_to_type": 0},
        "one_row_per_document": (
            "a document tagged with several tickers is scoped to the FIRST and "
            "carries the rest; fanning it into N rows would multiply one reading "
            "into N correlated ones"),
    }

    if dry_run:
        est = base["estimate"]
        return {**base, "status": "DRY_RUN", "dry_run": True,
                "verdict": (f"DRY RUN: {len(units):,} units would be typed from "
                            f"{source}; NO model call was made and nothing was "
                            "written"),
                "headline": (
                    f"{len(units):,} units / "
                    f"{est.get('panel_rows_covered', 0):,} panel rows; "
                    f"${est.get('cost', {}).get('measured_usd', 0.0):,.2f} at the "
                    f"measured $/row; "
                    f"{est.get('wall_time', {}).get('ledger_measured_57p4_per_min', {}).get('hours')} h "
                    f"at {workers} workers; cap "
                    f"{'none' if max_usd is None else f'${float(max_usd):,.2f}'}; $0.00 spent"),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    if not units:
        return {**base, "status": "done",
                "verdict": ("NOTHING TO DO: every eligible document from "
                            f"{source} is already typed"
                            + (f" at cursor {json.dumps(cursor, sort_keys=True)}"
                               if source == "corpus" else "")),
                "headline": f"0 units waiting from {source}",
                "manifest": write_manifest(),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    tag = "" if source == "corpus" else f"_{source}"
    frozen = OUT_DIR / f"{JOB}_run{run:02d}{tag}{'_smoke' if smoke else ''}_inputs.json"
    frozen.write_text(json.dumps(
        # `stage` on the sidecar as well as on the receipt: the stage-contract
        # test reads every *.json in the night directory, and an artefact of a
        # stamped job that carries no stage reads as an unstamped job.
        {"job": JOB, "run": run, "stage": "features", "source": source,
         **base["inputs_frozen"],
         "keys": [list(unit_key(u)) for u in units], "written_utc": _now()},
        indent=1), encoding="utf-8")
    base["inputs_frozen"]["file"] = str(frozen)

    refusal = (probe or _probe)(backend)
    if refusal is not None:
        est = base["estimate"]
        return {**base, "status": "PENDING_MODEL",
                "verdict": (
                    f"PENDING_MODEL: {len(units):,} eligible documents are frozen at "
                    f"sha256 {base['inputs_frozen']['inputs_sha256'][:12]} and NO model "
                    "call was made. The reader is not answering and this job does not "
                    f"start it. Probe said: {refusal}"),
                "headline": (
                    f"{len(units):,} units waiting from {source}; "
                    f"${est.get('cost', {}).get('measured_usd', 0.0):,.2f} at the "
                    f"measured $/row, "
                    f"{est.get('wall_time', {}).get('ledger_measured_57p4_per_min', {}).get('hours')} h "
                    f"at {workers} workers; $0.00"),
                "pending_when_the_reader_is_up": [
                    f"one call per unit: {len(units):,} at prompt hash {ex.PROMPT_HASH[:12]}",
                    f"a re-prompt of {kappa_rows} of them at hash {ex.PROMPT_HASH_B[:12]}, "
                    "kappa on event_type / direction / magnitude and MAD on confidence "
                    f"(the spec's own control is {KAPPA_ROWS_SPEC} rows)",
                    "refusals counted per class, never dropped; a no_event row is a "
                    "SUCCESS and is written",
                    f"one command: python -m scripts.night_l2_typed_events --source "
                    f"{source} --max-rows {max_rows or len(units)} --run {run}",
                ],
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    if complete is None:
        from backend.services.free_inference import complete as complete_
        complete = complete_

    day = f"{datetime.now(timezone.utc):%Y-%m-%d}"
    stem = day if source == "corpus" else f"panel_{day}"
    out_path = TYPED / f"{stem}.jsonl"
    ref_path = TYPED / f"{stem}_refusals.jsonl"
    typed_records: list[dict] = []
    refusal_records: list[dict] = []
    latest: dict[str, list[str]] = dict(cursor)
    # The kappa control re-prompts the FIRST `kappa_rows` successfully typed
    # units, so only those need holding. Keeping every row would carry 163,284
    # TypedEventRows through a full-panel run for the benefit of the first 50.
    first_pass: dict[tuple, ex.TypedEventRow] = {}
    keep_for_kappa = max(0, int(kappa_rows))
    state = {"flushed_t": 0, "flushed_r": 0}

    def _on_result(idx, unit, res, usage):
        model = usage.get("model")
        if unit.get("kind") == "corpus":
            row = unit["row"]
            if isinstance(res, ex.Refusal):
                refusal_records.append(refusal_record(row, res, backend=backend,
                                                      variant="A", model=model))
            else:
                rec = typed_record(row, res, backend=backend, variant="A", model=model)
                # chunk 15a: the text hash travels on EVERY typed row, corpus
                # rows included, so `event_head` can tell that a headline which
                # reached both the corpus and the panel is one event for a cell
                rec["text_sha256"] = unit["text_sha256"]
                rec["source_kind"] = "corpus"
                typed_records.append(rec)
                if len(first_pass) < keep_for_kappa:
                    first_pass[unit["key"]] = res
            # the cursor advances on a REFUSED row too: the document was read and
            # the reader refused it, and re-reading it every night would spend the
            # same tokens on the same failure for ever. The refusal file keeps it.
            src, seen, rid = unit["key"]
            latest[src] = [seen, rid]
        else:
            if isinstance(res, ex.Refusal):
                refusal_records.append(panel_refusal_record(
                    unit, res, backend=backend, variant="A", model=model))
            else:
                typed_records.append(panel_typed_record(
                    unit, res, backend=backend, variant="A", model=model))
                if len(first_pass) < keep_for_kappa:
                    first_pass[unit_key(unit)] = res

    def _on_flush():
        _append(out_path, typed_records[state["flushed_t"]:])
        _append(ref_path, refusal_records[state["flushed_r"]:])
        written = len(typed_records) - state["flushed_t"]
        if source == "corpus":
            save_cursor(latest, rows_written=written)
        state["flushed_t"] = len(typed_records)
        state["flushed_r"] = len(refusal_records)

    # NAMED, not defaulted. L2 does not have N9's 22c defect -- its cap and its
    # receipt (`spend_from_ledger(started_utc, path=ledger_path)` below) both
    # fell back to the same `ex.PURPOSE`, so the two reads always agreed -- but
    # the agreement rested on a shared default rather than on a stated
    # argument, and that is precisely what let N9 inherit the wrong purpose in
    # silence. Naming it here makes the equality checkable
    # (`test_cap_reader_agreement.py`) instead of coincidental.
    cap = _RunCap(max_usd, backend=backend, since_utc=started_utc,
                  ledger_path=ledger_path, purpose=ex.PURPOSE)
    work = type_units(units, backend=backend, complete=complete, variant="A",
                      workers=workers, cap=cap, on_result=_on_result,
                      on_flush=_on_flush, sleep=sleep)
    counts = work["counts"]
    by_type = work["by_type"]
    tin, tout = work["tokens_in"], work["tokens_out"]
    if work["stopped"] == "READER_ERROR" and work["failed_index"] is not None:
        bad = units[work["failed_index"]]
        rec = {"reason": "REFUSED_READER_ERROR", "detail": work["stop_detail"],
               "raw": "", "prompt_variant": "A", "backend": backend,
               "refused_utc": _now(), "source_kind": bad.get("kind"),
               "text_sha256": bad.get("text_sha256"),
               "document_date": bad.get("document_date"),
               "scope": bad.get("scope"),
               "note": ("the CURSOR STOPS BEFORE this unit: a reader error is a "
                        "property of the run, not of the document, so the next "
                        "run retries exactly this row")}
        _append(ref_path, [rec])
    if source == "panel":
        save_panel_cursor(typed_now=len(typed_records),
                          total_units=int(plan["block"]["distinct_texts"]),
                          done=int(plan["block"]["texts_already_typed"])
                          + len(typed_records),
                          run=run, stratified=int(stratified) or None)

    # ---- the inter-rater control: the SAME rows, the second prompt
    sample = [u for u in units if unit_key(u) in first_pass][:int(kappa_rows)]
    second: list[dict | None] = []
    firsts: list[dict | None] = []
    kappa_refusals = 0
    for unit in sample:
        try:
            out, usage = ex.extract(
                scope=unit["scope"], scope_kind=unit["scope_kind"],
                document_date=unit["document_date"], source_feed=unit["source_feed"],
                title=unit["title"], body=unit["body"],
                backend=backend, variant="B", complete=complete)
        except Exception as exc:                                  # noqa: BLE001
            # the control failing is not the run failing: the typed rows are on
            # disk and the cursor is past them, and a traceback here would throw
            # away a night that already produced its data
            kappa_refusals += 1
            work.setdefault("kappa_errors", []).append(f"{type(exc).__name__}: {exc}")
            continue
        tin += int(usage.get("tokens_in") or 0)
        tout += int(usage.get("tokens_out") or 0)
        if isinstance(out, ex.Refusal):
            kappa_refusals += 1
            continue
        second.append(out.as_dict())
        firsts.append(first_pass[unit_key(unit)].as_dict())

    inter = agreement(firsts, second)
    inter["refused_on_the_second_prompt"] = kappa_refusals
    inter["sample_size_asked_for"] = int(kappa_rows)
    inter["spec_control_size"] = KAPPA_ROWS_SPEC

    n_typed = len(typed_records)
    n_ref = sum(counts.values())
    rate = (n_ref / (n_typed + n_ref)) if (n_typed + n_ref) else None
    ledger = spend_from_ledger(started_utc, path=ledger_path)
    spend = float(ledger["usd"])
    status = "done" if work["stopped"] == "complete" else work["stopped"]
    return {
        **base,
        "status": status,
        "llm_spend_usd": _r(spend, 6),
        "results": {
            "rows_read": work["collected"],
            "rows_typed": n_typed,
            "units_submitted": work["submitted"],
            "units_offered": len(units),
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
            "panel_rows_covered": int(sum(len(r.get("panel_cells") or [])
                                          for r in typed_records)),
        },
        "concurrency": {
            "workers": work["workers"],
            "stopped": work["stopped"],
            "stop_detail": work["stop_detail"],
            "failed_index": work["failed_index"],
            "rate_limited_rows": work["rate_limited_rows"],
            "retries": work["retries"],
            "discarded_after_the_failure": work["discarded_after_the_failure"],
            "flush_every": FLUSH_EVERY,
            "order": ("results are collected and flushed in SUBMISSION order; the "
                      "cursor never passes a unit whose predecessors are unwritten"),
        },
        "cap": cap.block(),
        "inter_rater": inter,
        "usage": {"tokens_in": tin, "tokens_out": tout,
                  "cost_usd": _r(spend, 6),
                  "cost_source": "the CALL LEDGER, not a local cost field",
                  "ledger": ledger,
                  "purpose": ex.PURPOSE, "backend": backend},
        "manifest": write_manifest(),
        "verdict": (
            f"{n_typed:,} rows typed from {source}, {n_ref} refused "
            f"({', '.join(f'{k}={v}' for k, v in counts.items() if v) or 'none'}), "
            f"event_type kappa {inter.get('kappa_event_type')} on {inter.get('n')} "
            f"re-prompted rows; ${spend:.4f} by the ledger"
            + ("" if work["stopped"] == "complete"
               else f"; STOPPED: {work['stopped']} -- {work['stop_detail']}")),
        "headline": (
            f"{n_typed:,} typed / {work['collected']:,} read from {source} at "
            f"{work['workers']} workers; "
            f"{_r((by_type.get('no_event', 0) / n_typed) * 100, 1) if n_typed else None}% "
            f"no_event; refusal rate {_r(rate)}; ${spend:.2f}"),
        "next_test": (
            "E1 on these typed rows against E1 on the keyword proxy, same panel, "
            "same splits, same three controls -- the only changed variable being how "
            "the events were typed"),
        "elapsed_s": round(time.time() - t0, 1), "written_utc": _now(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="L2 -- type news text into the frozen vocabulary")
    ap.add_argument("--backend", default=ex.BACKEND)
    ap.add_argument("--source", default="corpus", choices=list(SOURCES),
                    help="corpus = the news corpus (the default, unchanged); "
                         "panel = the 2025-26 return panel's own headline table, "
                         "deduped to one typing per distinct text")
    ap.add_argument("--max-rows", type=int, default=0,
                    help="rows to type this run; 0 = every row after the cursor")
    ap.add_argument("--workers", type=int, default=WORKERS,
                    help="bounded thread pool over the SAME extract call; results "
                         "are flushed in submission order. 1 (default) is the "
                         "sequential run row for row")
    ap.add_argument("--max-usd", type=float, default=None,
                    help="per-RUN dollar cap, checked before every submission "
                         "against the call ledger's running total for this run")
    ap.add_argument("--stratified", type=int, default=0,
                    help="--source panel only: take K texts stratified by month "
                         "and symbol-frequency quartile, fixed seed")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the estimate -- rows, tokens, cost at both price "
                         "tables, wall time at N workers -- and call nothing")
    ap.add_argument("--panel", default=None, help="override the panel parquet path")
    ap.add_argument("--kappa-rows", type=int, default=KAPPA_ROWS)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    payload = L2_typed_events(backend=a.backend, max_rows=a.max_rows, run=a.run,
                              smoke=a.smoke, kappa_rows=a.kappa_rows,
                              source=a.source, workers=a.workers,
                              max_usd=a.max_usd, stratified=a.stratified,
                              seed=a.seed, dry_run=a.dry_run,
                              panel_path=Path(a.panel) if a.panel else None)
    payload["run"] = a.run
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = "" if a.source == "corpus" else f"_{a.source}"
    if a.dry_run:
        tag += "_dryrun"
    out = (Path(a.out) if a.out else
           OUT_DIR / f"{JOB}_run{a.run:02d}{tag}{'_smoke' if a.smoke else ''}.json")
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"\n{JOB}: {payload['headline']}\n  verdict: {payload['verdict']}\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
