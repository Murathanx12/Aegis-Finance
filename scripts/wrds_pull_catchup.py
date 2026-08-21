"""WRDS-PULL-CATCHUP — finish the pull that reported itself finished.

WHAT WENT WRONG (measured 2026-08-20, not inferred)
===================================================
`wrds_pull_everything` wrote `completed_at` with **281 tables pulled and 1,127
failed** out of 1,327 planned, and the session handoff recorded the PLAN count
as the result. 79% of the substrate was missing and the record said done.

The failures are not entitlement. Taxonomy of the 1,127:

    727  statement timeout          <- self-inflicted, see below
    245  connection dropped         <- same cause, downstream
    125  permission denied          <- REAL: not entitled
     28  relation does not exist    <- REAL: catalogue lists what is not there
      2  conflict with recovery     <- read-replica lag, retryable

`PER_TABLE_TIMEOUT_S = 90` was a local decision, defended in a comment as
protecting a scarce connection. **The server's own `statement_timeout` is
2 days.** Nothing upstream asked for 90 seconds. Re-pulled by hand with the
cap lifted, the four representative "timeouts" look like this:

    crsp.contact_info      329,280 rows x  11 cols    18.1s
    optionm.distrd         743,101 rows x  15 cols    30.3s
    comp.aco_indsta         59,293 rows x 886 cols    91.3s   <- missed by 1.3s
    ibes.act_epsint      3,457,713 rows x  14 cols   162.5s

A 329k-row table that takes 18 seconds alone did not need 90; it lost them to
five workers competing for the same link. So the cap did not protect
throughput, it converted slow tables into absent ones — and because the
manifest counted a timeout as a `failed` entry rather than as an incomplete
run, the pull could report completion having skipped four fifths of its plan.

WHAT THIS DOES DIFFERENTLY
==========================
  * per-table timeout raised to `--timeout-s` (default 900) and set ONCE per
    connection, not per query;
  * fewer workers by default (3), because contention was the real limit;
  * dropped connections are RECONNECTED and retried with backoff instead of
    counted as a table that does not exist;
  * PERMISSION DENIED and DOES NOT EXIST are separated out as TERMINAL and
    never retried — they are entitlement findings and belong in the
    entitlement map, not in a failure count that looks like a bug;
  * the run refuses to write `completed_at` while any retryable table remains
    (`--max-seconds` chunking sets `partial_at` instead). A run that stopped
    early says so.

Resumable: a table whose parquet exists is skipped. Safe to kill.

    python -m scripts.wrds_pull_catchup --dry-run
    python -m scripts.wrds_pull_catchup --max-seconds 21600
"""

from __future__ import annotations

import argparse
import json
import queue
import re
import sys
import threading
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.wrds_pull_everything import (BULK, MANIFEST,  # noqa: E402
                                          MAX_ROWS, DISK_BUDGET_GB)
from scripts.wrds_training_pull import (OUT, _all_permnos,  # noqa: E402
                                        _conn, _date_ranges)

CATCHUP_LOG = OUT / "pull_catchup_log.jsonl"
TERMINAL_MAP = OUT / "pull_terminal_failures.json"

#: Errors that will never succeed on retry. Each is a FINDING about what this
#: account is entitled to see, not a transport failure.
TERMINAL_PATTERNS = (
    (re.compile(r"permission denied", re.I), "NOT_ENTITLED"),
    (re.compile(r"does not exist", re.I), "ABSENT_FROM_SERVER"),
)

#: Errors caused by how the query was asked, not by whether it may be asked.
RETRYABLE_PATTERNS = (
    (re.compile(r"statement timeout", re.I), "TIMEOUT"),
    (re.compile(r"conflict with recovery", re.I), "REPLICA_RECOVERY"),
    # 235 of the original 1,127 "failures" were this: the laptop lost DNS for
    # a stretch mid-run. A puller that books a network outage as a per-table
    # failure converts a transient outage into a permanent hole in the
    # substrate — and then reports the hole as a completed pull.
    (re.compile(r"could not translate host name|Name or service not known|"
                r"Temporary failure in name resolution|getaddrinfo", re.I),
     "NETWORK_DNS"),
    (re.compile(r"server closed the connection|could not receive|"
                r"SSL|EOF detected|connection", re.I), "CONNECTION"),
    (re.compile(r"out of memory|MemoryError", re.I), "MEMORY"),
)

DEFAULT_TIMEOUT_S = 900
DEFAULT_WORKERS = 3
MAX_ATTEMPTS = 3


#: Streaming is chunked by CELLS, not rows. A 200,000-row chunk is 2.2 MB of
#: an 11-column table and ~1.4 GB of an 886-column one, and Compustat is full
#: of the latter — four workers on wide tables took the process to 10 GB with
#: the server-side cursor already in place, because the cursor bounds what the
#: SERVER sends per round trip and not what pandas/Arrow materialise per
#: chunk. Rows per chunk are therefore derived from the table's own width.
CHUNK_CELLS = 16_000_000
CHUNK_ROWS_MAX = 200_000
CHUNK_ROWS_MIN = 5_000


def _chunk_rows(n_cols: int | None) -> int:
    if not n_cols or n_cols < 1:
        return CHUNK_ROWS_MIN     # unknown width: assume the expensive case
    return max(CHUNK_ROWS_MIN, min(CHUNK_ROWS_MAX, CHUNK_CELLS // n_cols))

#: Above this row count a table is STREAMED through a server-side cursor
#: (bounded memory, ~2x slower); at or below it the plain client-side read is
#: used (fast, buffers the whole result). Measured 2026-08-20:
#:   ibes.act_epsint  3.46M rows   162s buffered / 301s streamed, RSS 79 MB
#:   crsp.contact_info  329k rows    18s buffered /  28s streamed
#: Six workers each buffering a multi-million-row wide frame is how a night's
#: pull becomes an OOM; paying 2x on the few tables that can cause that, and
#: nothing on the many that cannot, is the trade this threshold makes.
STREAM_ABOVE_ROWS = 500_000

#: ...and the same correction as the chunk size: 500,000 rows is a small read
#: at 11 columns and a 3.5 GB one at 886. A table goes down the buffered path
#: only if it is small on BOTH axes.
BUFFER_MAX_CELLS = 8_000_000


def _use_buffered(n_rows: int | None, n_cols: int | None) -> bool:
    if n_rows is None:
        return False              # unknown size -> stream, never buffer
    if n_rows > STREAM_ABOVE_ROWS:
        return False
    return n_rows * max(int(n_cols or 1), 1) <= BUFFER_MAX_CELLS

#: `count(*)` costs ~0.5s and is the only honest way to route: est_rows is 0
#: for every table WRDS has never ANALYZEd, which is most of the plan — that
#: same stale estimate is why Compustat GLOBAL tables slipped past the
#: original size cap.
COUNT_TIMEOUT_MS = 60_000


#: Postgres data_type -> the pandas dtype we coerce to before handing a chunk
#: to Arrow. Inferring per chunk does not work: a column that is entirely NULL
#: in chunk 1 becomes Arrow type `null`, and chunk 5 arriving with doubles then
#: fails "Unsupported cast from double to null". Deriving the type from the
#: DATABASE instead of from the first 4,514 rows makes every chunk agree by
#: construction. It also fixes "Decimal value does not fit in precision 6",
#: because Compustat `numeric` columns become float64 rather than Arrow
#: decimals with a width guessed from one chunk.
_PG_TO_PANDAS = {
    "numeric": "float64", "decimal": "float64", "double precision": "float64",
    "real": "float64", "money": "float64",
    "integer": "Int64", "bigint": "Int64", "smallint": "Int64",
    "boolean": "boolean",
    "date": "datetime64[ns]", "timestamp without time zone": "datetime64[ns]",
    "timestamp with time zone": "datetime64[ns]",
}


def _pg_types(conn, schema: str, table: str) -> dict:
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position", (schema, table))
        out = {c: t for c, t in cur.fetchall()}
        cur.close()
        return out
    except Exception:                                           # noqa: BLE001
        try:
            conn.rollback()
        except Exception:                                       # noqa: BLE001
            pass
        return {}


def _coerce(df, pgtypes: dict):
    """Force each column to the dtype its POSTGRES type implies.

    Anything not in the map (text, varchar, char, and every exotic type) goes
    to pandas `string`, whose all-NA case is still Arrow `string` rather than
    Arrow `null` — which is the whole point.
    """
    for col in df.columns:
        want = _PG_TO_PANDAS.get(str(pgtypes.get(col, "")).lower())
        try:
            if want in ("float64",):
                df[col] = pd.to_numeric(df[col], errors="coerce").astype(
                    "float64")
            elif want == "Int64":
                df[col] = pd.to_numeric(df[col], errors="coerce").astype(
                    "Int64")
            elif want == "boolean":
                df[col] = df[col].astype("boolean")
            elif want == "datetime64[ns]":
                df[col] = pd.to_datetime(df[col], errors="coerce")
            else:
                df[col] = df[col].astype("string")
        except Exception:                                       # noqa: BLE001
            df[col] = df[col].astype("string")
    return df


def _stream_to_parquet(conn, sql, params, fn, *, chunk: int,
                       pgtypes: dict | None = None) -> tuple:
    """Server-side cursor -> parquet, a chunk at a time. Returns (rows, ranges).

    `pd.read_sql(..., chunksize=)` does NOT bound memory on psycopg2: the
    default cursor is CLIENT-side, so the whole result is buffered before the
    first chunk is yielded. Six workers each holding a multi-million-row wide
    frame is how a night's pull turns into an OOM. A NAMED cursor is
    server-side and streams — but psycopg2 refuses one in autocommit mode, so
    the connection is taken out of autocommit for the duration and put back.

    Date ranges are accumulated across chunks rather than computed from a
    whole frame, because there is no whole frame any more.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    was_auto = conn.autocommit
    conn.autocommit = False
    writer = None
    schema = None
    total = 0
    ranges: dict[str, list] = {}
    name = f"arena_catchup_{abs(hash(fn.name)) % 10**9}"
    try:
        cur = conn.cursor(name=name)
        cur.itersize = chunk
        cur.execute(sql, params)
        cols = None
        while True:
            rows = cur.fetchmany(chunk)
            if not rows:
                break
            if cols is None:
                cols = [d[0] for d in cur.description]
            df = pd.DataFrame(rows, columns=cols)
            if pgtypes:
                df = _coerce(df, pgtypes)
            for c in df.columns:
                lc = c.lower()
                if not any(k in lc for k in ("date", "dat", "eom", "public",
                                             "statpers", "rdq")):
                    continue
                try:
                    s = pd.to_datetime(df[c], errors="coerce").dropna()
                except Exception:                               # noqa: BLE001
                    continue
                if len(s):
                    lo, hi = str(s.min())[:10], str(s.max())[:10]
                    cur_r = ranges.get(c)
                    ranges[c] = ([min(cur_r[0], lo), max(cur_r[1], hi)]
                                 if cur_r else [lo, hi])
            tbl = pa.Table.from_pandas(df, preserve_index=False)
            if writer is None:
                schema = tbl.schema
                writer = pq.ParquetWriter(fn, schema)
            elif not tbl.schema.equals(schema):
                # With _coerce driving dtypes from the database this should
                # not happen; if it still does, casting is the last resort
                # before failing the table, and failing is correct — a
                # parquet whose columns mean two different things is worse
                # than an absent one.
                tbl = tbl.cast(schema)
            writer.write_table(tbl)
            total += len(df)
        cur.close()
        return total, ranges
    finally:
        if writer is not None:
            writer.close()
        try:
            conn.rollback()
        finally:
            conn.autocommit = was_auto


#: A table whose MEASURED row count exceeds MAX_ROWS is not pulled at all.
#:
#: `SELECT * FROM t LIMIT 8000000` with no ORDER BY returns an ARBITRARY
#: 8,000,000 rows — not a prefix, not a sample with a definition, and not the
#: same set twice. The original pull never met this because every large table
#: died on the 90-second timeout; fixing the timeout made the big tables
#: succeed for the first time and exposed it. Measured:
#:
#:   crsp.daily_nav_ret  186,442,964 true rows -> 8,000,000 kept =  4.3%
#:   comp.aco_transa      47,158,539 true rows -> 8,000,000 kept = 17.0%
#:   optionm.hvold2013    12,853,308 true rows -> 8,000,000 kept = 62.2%
#:
#: A file named `crsp__daily_nav_ret.parquet` holding 4.3% of the table, with
#: nothing recording that, is worse than an absent file: it joins cleanly and
#: silently drops 96% of the data. The plan already skips tables whose
#: est_rows exceed the cap — that rule simply never fired, because est_rows is
#: 0 for anything WRDS has not ANALYZEd. This applies the SAME rule to the
#: measured count, and records the true size so the cap can be revisited as a
#: declared decision rather than discovered as a hole.
OVER_CAP_REASON = "measured rows > MAX_ROWS; an unordered LIMIT is an " \
                  "arbitrary subset, so nothing is written"


def _row_count(conn, p: dict, where: str, params) -> int | None:
    """Rows this pull will actually move, or None if counting failed.

    None routes to the STREAMING path: not knowing the size is exactly the
    case where an unbounded buffered read is the dangerous choice.
    """
    try:
        cur = conn.cursor()
        cur.execute(f"SET statement_timeout = {COUNT_TIMEOUT_MS}")
        cur.execute(f'SELECT count(*) FROM {p["schema"]}.{p["table"]}{where}',
                    params)
        n = int(cur.fetchone()[0])
        cur.close()
        return n
    except Exception:                                           # noqa: BLE001
        try:
            conn.rollback()
        except Exception:                                       # noqa: BLE001
            pass
        return None


def _write_frame(df, fn) -> None:
    """Parquet, with the object-column fallback the buffered path needs."""
    try:
        df.to_parquet(fn, index=False)
    except Exception:                                           # noqa: BLE001
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str)
        df.to_parquet(fn, index=False)


def classify(error: str) -> tuple[str, str]:
    """(verdict, reason). Unknown errors are RETRYABLE by default and named,
    because silently treating an unrecognised error as terminal is how a
    transport bug becomes a permanent hole in the substrate."""
    for pat, reason in TERMINAL_PATTERNS:
        if pat.search(error or ""):
            return "TERMINAL", reason
    for pat, reason in RETRYABLE_PATTERNS:
        if pat.search(error or ""):
            return "RETRYABLE", reason
    return "RETRYABLE", "UNCLASSIFIED"


def _planned_names() -> set:
    """Names the CURRENT plan intends to pull. Empty set if unreadable, and
    an empty set disables the filter rather than silently dropping the whole
    retry list — refusing everything is not the safe default here."""
    from scripts.wrds_pull_everything import PLAN_CACHE
    try:
        plan = json.loads(PLAN_CACHE.read_text(encoding="utf-8"))
        return {p["name"] for p in plan.get("plan", [])}
    except Exception as exc:                                    # noqa: BLE001
        print(f"  (plan cache unreadable: {exc}; out-of-plan filter OFF)")
        return set()


def _flush_manifest(new_pulled, new_failed, new_over_cap, terminal, *,
                    partial: bool, extra: dict | None = None) -> None:
    """Merge this run's results into the manifest. Idempotent by name, so a
    periodic flush and the final one cannot double-count the same table."""
    man = _load_manifest()
    seen_p = {p.get("name") for p in man.get("pulled") or []}
    seen_f = {(f.get("name"), f.get("error")) for f in man.get("failed") or []}
    seen_o = {o.get("name") for o in man.get("over_cap") or []}
    man["pulled"] = (man.get("pulled") or []) + [
        r for r in new_pulled if r["name"] not in seen_p]
    man["failed"] = (man.get("failed") or []) + [
        r for r in new_failed if (r["name"], r.get("error")) not in seen_f]
    man["over_cap"] = (man.get("over_cap") or []) + [
        r for r in new_over_cap if r["name"] not in seen_o]
    man["n_terminal_not_entitled"] = len(terminal)
    if partial:
        man.pop("completed_at", None)
        man["partial_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds")
    man.update(extra or {})
    MANIFEST.write_text(json.dumps(man, indent=2, default=str),
                        encoding="utf-8")


def _load_manifest() -> dict:
    if not MANIFEST.exists():
        raise SystemExit(f"no manifest at {MANIFEST}; run wrds_pull_everything "
                         f"first — this script finishes a pull, it does not "
                         f"plan one")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _log(rows: list[dict]) -> None:
    CATCHUP_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CATCHUP_LOG, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                       # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--timeout-s", type=int, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--max-tables", type=int, default=100000)
    ap.add_argument("--max-seconds", type=float, default=0.0)
    a = ap.parse_args()

    man = _load_manifest()
    BULK.mkdir(parents=True, exist_ok=True)

    have = {p.stem for p in BULK.glob("*.parquet")}
    # Dedupe: the manifest appends, so one table can appear in `failed` more
    # than once across runs. Counting those twice would overstate the hole.
    by_name: dict[str, dict] = {}
    for f in man.get("failed", []):
        by_name[f["name"]] = f

    # THE MANIFEST OUTLIVES THE PLAN. `failed` accumulates across runs, and
    # the first run of 2026-08-20 predates the NON_US exclusion — so the
    # failure list still names 24 Compustat GLOBAL tables (`comp.g_*`) that
    # the CURRENT plan deliberately excludes because they cannot join a US
    # CRSP PERMNO universe. They are 539 columns wide, ~2 GB each, and the
    # catch-up was about to spend the night on them. A retry list is only
    # meaningful against the plan in force NOW.
    planned = _planned_names()
    # Tables already measured as over-cap. Re-counting them costs ~0.5s each
    # at the head of EVERY run — 221 of them is two minutes of every session
    # spent rediscovering the same fact.
    #
    # Keyed on the CAP THEY WERE MEASURED AGAINST. If MAX_ROWS is raised (the
    # open decision in the handoff), a table recorded over-cap at 8,000,000 is
    # no longer known to be over-cap, and it must go back in the queue rather
    # than inherit a skip from a rule that no longer applies.
    known_over_cap = {o["name"]: o for o in (man.get("over_cap") or [])
                      if o.get("cap") == MAX_ROWS}
    terminal, retry, unplanned, skipped_over_cap = [], [], [], []
    for name, f in sorted(by_name.items()):
        stem = f"{f['schema']}__{f['table']}"
        if stem in have:
            continue                       # landed on a later attempt already
        verdict, reason = classify(str(f.get("error", "")))
        if verdict != "TERMINAL" and name in known_over_cap:
            skipped_over_cap.append(known_over_cap[name])
            continue
        if verdict != "TERMINAL" and planned and name not in planned:
            unplanned.append({**f, "verdict": "OUT_OF_PLAN",
                              "reason": "not in the current plan"})
            continue
        (terminal if verdict == "TERMINAL" else retry).append(
            {**f, "verdict": verdict, "reason": reason})

    # RESEARCH PRIORITY, not alphabetical. The first catch-up run iterated
    # sorted-by-name and therefore spent its opening ten minutes on
    # `audit.*` and `boardex.*` — tier 2, the least useful tables in the
    # plan — while crsp/comp/ibes/optionm waited. `wrds_pull_everything`
    # already sorts its plan (tier, est_rows) for exactly this reason; a
    # catch-up that drops the ordering re-introduces the problem it exists
    # to solve, because a run that is interrupted keeps whatever it banked
    # first. Small-first inside a tier banks many cheap tables before
    # risking an expensive one.
    # Within a tier, NARROW tables first. est_rows is 0 for most of the plan
    # (never ANALYZEd), so it cannot order anything — but n_cols is known and
    # is what actually drives cost here: comp.co_afnddc1 is 494,873 rows x 539
    # columns = 267M cells, about 2 GB on the wire, while a 7-column table of
    # 2.6M rows is 18M cells. Sorting by width banks hundreds of cheap tier-0
    # tables before the run spends hours on Compustat footnote descriptors,
    # which matters because an interrupted run keeps whatever it banked first.
    retry.sort(key=lambda p: (p.get("tier", 9), p.get("n_cols") or 9999,
                              p.get("est_rows") or 0, p["name"]))

    from collections import Counter
    print(f"manifest: {len(man.get('pulled', [])):,} pulled, "
          f"{len(man.get('failed', [])):,} failure rows "
          f"({len(by_name):,} distinct tables)")
    print(f"already on disk: {len(have):,} parquet files")
    print(f"\nTERMINAL (never retried): {len(terminal):,}")
    for k, v in Counter(t["reason"] for t in terminal).most_common():
        print(f"    {v:>6,}  {k}")
    if unplanned:
        print(f"OUT OF PLAN (not retried): {len(unplanned):,} — in the failure "
              f"list from an earlier plan, excluded by the current one")
        print(f"    e.g. {[u['name'] for u in unplanned[:5]]}")
    if skipped_over_cap:
        print(f"OVER CAP (already measured, not re-counted): "
              f"{len(skipped_over_cap):,} at cap {MAX_ROWS:,}")
        print(f"    raising MAX_ROWS puts these back in the queue "
              f"automatically")
    print(f"RETRYABLE:                {len(retry):,}")
    for k, v in Counter(t["reason"] for t in retry).most_common():
        print(f"    {v:>6,}  {k}")

    TERMINAL_MAP.write_text(json.dumps({
        "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": ("Tables this account cannot read, or that the catalogue "
                 "lists and the server does not have. These are ENTITLEMENT "
                 "FACTS, not pull failures — they must never be retried as if "
                 "the transport were at fault, and the catalogue is not "
                 "entitlement (canon)."),
        "n_terminal": len(terminal),
        "n_out_of_plan": len(unplanned),
        "out_of_plan": unplanned,
        "by_reason": dict(Counter(t["reason"] for t in terminal)),
        "tables": terminal,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nterminal map -> {TERMINAL_MAP}")

    if a.dry_run:
        print("\ndry run — nothing pulled")
        return 0
    todo = retry[:a.max_tables]
    if not todo:
        print("\nnothing retryable outstanding")
        return 0

    permnos = sorted(_all_permnos())
    work: "queue.Queue[dict]" = queue.Queue()
    for p in todo:
        work.put(p)
    lock = threading.Lock()
    t_start = time.time()
    state = {"gb": sum(f.stat().st_size for f in BULK.rglob("*.parquet")) / 2**30,
             "done": 0, "failed": 0, "over_cap": 0, "stop": False}
    new_pulled, new_failed, new_over_cap = [], [], []
    print(f"\npulling {len(todo):,} tables · {a.workers} workers · "
          f"timeout {a.timeout_s}s · disk now {state['gb']:.1f} GB")

    def worker(wid: int):
        c = None
        while not state["stop"]:
            try:
                p = work.get_nowait()
            except queue.Empty:
                break
            fn = BULK / f"{p['schema']}__{p['table']}.parquet"
            if fn.exists():
                continue
            if a.max_seconds and (time.time() - t_start) > a.max_seconds:
                state["stop"] = True
                break
            with lock:
                if state["gb"] >= DISK_BUDGET_GB:
                    print("  STOP: disk budget reached", flush=True)
                    state["stop"] = True
                    break
            where, params = "", None
            if p.get("id_col") in ("permno", "lpermno", "permco"):
                where = f' WHERE "{p["id_col"]}" = ANY(%(p)s)'
                params = {"p": permnos}
            sql = (f'SELECT * FROM {p["schema"]}.{p["table"]}{where} '
                   f'LIMIT {MAX_ROWS}')

            n_rows, ranges, err, over_cap = None, {}, None, None
            for attempt in range(1, MAX_ATTEMPTS + 1):
                t0 = time.time()
                try:
                    if c is None:
                        c = _conn()
                        cc = c.cursor()
                        # ONCE per connection. The old code re-set it per
                        # query, which is harmless, but it set it to 90s.
                        cc.execute(f"SET statement_timeout = "
                                   f"{a.timeout_s * 1000}")
                    n_est = _row_count(c, p, where, params)
                    pgt = _pg_types(c, p["schema"], p["table"])
                    # _row_count set its own (shorter) timeout on this
                    # connection; put the pull's back before the real query.
                    cc = c.cursor()
                    cc.execute(f"SET statement_timeout = {a.timeout_s * 1000}")
                    cc.close()
                    if n_est is not None and n_est > MAX_ROWS:
                        over_cap = {**p, "true_rows": int(n_est),
                                    "cap": MAX_ROWS,
                                    "would_have_kept_pct": round(
                                        100.0 * MAX_ROWS / n_est, 2),
                                    "reason": OVER_CAP_REASON}
                        break
                    if _use_buffered(n_est, p.get("n_cols")):
                        df = pd.read_sql(sql, c, params=params)
                        n_rows = len(df)
                        if n_rows:
                            ranges = _date_ranges(df)
                            _write_frame(_coerce(df, pgt) if pgt else df, fn)
                        del df
                    else:
                        n_rows, ranges = _stream_to_parquet(
                            c, sql, params, fn,
                            chunk=_chunk_rows(p.get("n_cols")), pgtypes=pgt)
                    err = None
                    break
                except Exception as e:                          # noqa: BLE001
                    # A partial parquet is worse than none: resumability keys
                    # off file existence, so a truncated file would be read
                    # forever as a completed table.
                    if fn.exists():
                        try:
                            fn.unlink()
                        except OSError:
                            pass
                    err = f"{type(e).__name__}: {str(e)[:200]}"
                    verdict, reason = classify(err)
                    if verdict == "TERMINAL":
                        break
                    # A dropped connection is not a fact about the table.
                    try:
                        c.rollback()
                    except Exception:                           # noqa: BLE001
                        try:
                            c.close()
                        except Exception:                       # noqa: BLE001
                            pass
                        c = None
                    if attempt < MAX_ATTEMPTS:
                        time.sleep(min(30, 3 * 2 ** (attempt - 1)))
                        print(f"  retry {attempt + 1}/{MAX_ATTEMPTS} "
                              f"{p['name']} ({reason}, "
                              f"{time.time() - t0:.0f}s)", flush=True)
            if over_cap is not None:
                with lock:
                    state["over_cap"] += 1
                    new_over_cap.append(over_cap)
                    print(f"  OVER-CAP {p['name']:<38s} "
                          f"{over_cap['true_rows']:>13,} rows > "
                          f"{MAX_ROWS:,} — NOT written "
                          f"({over_cap['would_have_kept_pct']}% would have "
                          f"been an arbitrary subset)", flush=True)
                _log([{"ts": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"), "name": p["name"],
                    "result": "over_cap",
                    "true_rows": over_cap["true_rows"]}])
                continue
            if err is not None or n_rows is None:
                with lock:
                    state["failed"] += 1
                    new_failed.append({**p, "error": err,
                                       "attempts": MAX_ATTEMPTS})
                    print(f"  FAIL {p['name']:<46s} {str(err)[:70]}",
                          flush=True)
                _log([{"ts": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"), "name": p["name"],
                    "result": "failed", "error": err}])
                continue
            if not n_rows:
                # An empty table writes no parquet at all (the writer never
                # opened), so record it as pulled-and-empty rather than
                # leaving it to look outstanding on the next pass.
                if fn.exists():
                    try:
                        fn.unlink()
                    except OSError:
                        pass
                with lock:
                    new_pulled.append({**p, "rows": 0,
                                       "note": "0 rows — table is empty"})
                _log([{"ts": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"), "name": p["name"],
                    "result": "empty"}])
                continue
            sz = fn.stat().st_size / 2**30 if fn.exists() else 0.0
            with lock:
                state["gb"] += sz
                state["done"] += 1
                row = {**p, "rows": int(n_rows), "gb": round(sz, 4),
                       "cells": int(n_rows) * int(p.get("n_cols") or 1),
                       "mb_per_s": round(
                           (sz * 1024) / max(time.time() - t0, 0.001), 2),
                       "date_ranges": ranges,
                       "seconds": round(time.time() - t0, 1),
                       "universe_filtered": bool(where),
                       "pulled_by": "catchup_streamed"}
                new_pulled.append(row)
                el = time.time() - t_start
                rate = state["done"] / el * 3600 if el > 0 else 0
                # Flush the manifest as we go. Writing it only at the end
                # means a killed run loses ALL of its bookkeeping: the
                # parquets survive (resumability keys off file existence) but
                # nothing records what they are, their row counts, or their
                # date ranges. `wrds_pull_everything` carries a comment about
                # learning this exact lesson; this file had to learn it too.
                if state["done"] % 5 == 0:
                    _flush_manifest(new_pulled, new_failed, new_over_cap,
                                    terminal, partial=True)
                print(f"  [{state['done']}/{len(todo)}] {p['name']:<44s} "
                      f"{n_rows:>9,} rows {time.time() - t0:>6.1f}s "
                      f"{state['gb']:.1f}GB  {rate:>5.0f}/h "
                      f"({state['failed']} fail)", flush=True)
            _log([{"ts": datetime.now(timezone.utc).isoformat(
                timespec="seconds"), "name": p["name"], "result": "pulled",
                "rows": int(n_rows), "seconds": round(time.time() - t0, 1)}])
        if c is not None:
            try:
                c.close()
            except Exception:                                   # noqa: BLE001
                pass

    threads = [threading.Thread(target=worker, args=(i,), daemon=True)
               for i in range(a.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    _flush_manifest(new_pulled, new_failed, new_over_cap, terminal,
                    partial=True)
    man = _load_manifest()          # re-read: another pass may have appended
    man["catchup_runs"] = (man.get("catchup_runs") or []) + [{
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "workers": a.workers, "timeout_s": a.timeout_s,
        "attempted": len(todo), "pulled": len(new_pulled),
        "failed": len(new_failed),
        "seconds": round(time.time() - t_start, 1)}]

    remaining = (len(todo) - state["done"] - state["failed"]
                 - state["over_cap"])
    stamp = "completed_at" if remaining <= 0 else "partial_at"
    if remaining > 0:
        # Refuse to say "completed" while work is outstanding. This is the
        # exact sentence the first run got wrong.
        man.pop("completed_at", None)
        man["incomplete_reason"] = (
            f"{remaining} retryable table(s) not attempted this run "
            f"(--max-seconds / --max-tables / disk budget)")
    man[stamp] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    man["disk_used_gb"] = round(state["gb"], 3)
    MANIFEST.write_text(json.dumps(man, indent=2, default=str),
                        encoding="utf-8")

    print(f"\ncatchup: {state['done']:,} pulled, {state['failed']:,} failed, "
          f"{state['over_cap']:,} over-cap (NOT written), "
          f"{remaining:,} not attempted · {state['gb']:.1f} GB")
    print(f"manifest -> {MANIFEST}   ({stamp})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
