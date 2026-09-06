"""N4_EVENT_TABLE -- the event-time table, 2015-> (Night Lab 2026-09-07, lane N4).

    python -m scripts.n4_event_table --build              # write event_table_v1.parquet
    python -m scripts.n4_event_table --coverage-only       # just the by-year receipt

WHY THIS EXISTS
================
`docs/NIGHT_LAB_2026-09-07_OPUS_PROMPT.md` lane N4: the research programme has
never owned a single dated tape of "things that happened, and when we could
have known them" spanning the CRSP-replayable window (2015 onward). This job
JOINS four things this repo already owns or can cheaply pull -- SEC 8-K item
codes, IBES EPS surprises, Alpaca/Benzinga + Finnhub news, and (thin) SEC
Schedule 13D/13G ownership filings -- into one parquet with a single PIT rule.

THE ONE PIT RULE
=================
`observed_at_utc` is when the row became AVAILABLE, never the event's own
timestamp. Concretely:
  - 8-K:        observed_at_utc = EDGAR `acceptance_datetime` (the only field
                that is actually an availability timestamp; `event_date` is
                what HAPPENED and is carried separately as `event_time_utc`).
  - IBES surprise: the announcement (`anndats`) both IS and reveals the fact
                (the actual EPS *is* the announcement) -- event_time_utc and
                observed_at_utc are the same value, DATE precision only (IBES
                does not carry announcement time-of-day in this table).
  - News (Alpaca/Benzinga/Finnhub, via `alpha.sources.corpus`): the corpus's
                own `observed_at` (publication instant) is used directly --
                that module already enforces this rule at write time; this
                job never reads `effective_at` as if it were observed_at.
  - Ownership (13D/13G): `filed_date` is the correct availability bound (EDGAR
                filings are public same-day); the collector's own `observed_at`
                field records when OUR pipeline fetched it (days later, in the
                one on-disk sample) and is NOT used as the PIT bound.

TWO CLOCKS, TWO BOUNDS (S24/CLAUDE.md) -- why `tense == "future"` is dropped
=============================================================================
The corpus stores both realized facts (`tense="past"`) and scheduled/forward
rows (`tense="future"`, e.g. a calendar earnings date). A backward news bound
(`observed_at <= as_of`) and a forward calendar bound (`effective_at <= some
future limit`) are two different constraints, and sharing one between them is
exactly the S24 defect ("a shuffled-date null was the calendar"). This job
builds a table of REALIZED events only and drops `tense=="future"` rows
outright rather than reusing the backward bound on a forward-looking row.

WHAT IS NOT HERE, AND WHY
==========================
- Form 4 (insider transactions): searched `backend/data/optimus/wrds/bulk/`
  and both repos' `state/`; the only insider-adjacent WRDS table on disk is
  `tfn__s34type*` (Thomson Reuters S34 = 13F INSTITUTIONAL manager holdings,
  not Form 3/4/5 insider transactions). No Form 4 tape is entitled or present.
  ABSENT, not fabricated.
- 13D/13G: `alpha/sources/edgar_ownership.py` (terminal repo) is a real
  collector, but its on-disk store (`state/research/ownership/*.jsonl`) holds
  exactly 7 days (2026-08-13..2026-08-20) from a smoke test -- essentially zero
  coverage of 2015-2024. A full daily-index backfill to 2015 is a per-CALENDAR-
  DAY job (1 index fetch + 1 header fetch per filing, ~4/s, some days 1,600+
  filings) -- roughly 4,000 index days -- which is a separate multi-day network
  job on its own and was NOT launched here; the mandate says "if present on
  disk", and what's present is joined, honestly labelled as thin.
- Price REACTION fields (the surprise x reaction books, PEAD, etc.): out of
  scope for this join -- see the coverage receipt / night-lab report for
  whether time allowed running them at all.

MEMORY
======
This job reads local parquet/jsonl only (no network calls of its own -- the
network pull is `scripts/news_backfill.py`, run separately and beforehand /
concurrently). Every heavy read passes explicit `columns=` and the CRSP
name-history file (46k rows) is the only thing joined by cross-merge; IBES and
8-K are read once, filtered, and interval-joined against the (tiny) CRSP names
table rather than the other way around. `w3_neural_floored.free_gb()` is
checked at start and logged in every receipt; the ~400MB long-panel training
table is deliberately NEVER loaded here (see `_listed_universe_by_year`).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as RP                # noqa: E402
from scripts.w3_neural_floored import free_gb                        # noqa: E402

# ------------------------------------------------------------------- paths

TERMINAL_REPO = Path(r"C:\Users\mrthn\aegis-alpha-terminal")          # sibling repo, READ ONLY
CORPUS_OBS_DIR = TERMINAL_REPO / "state" / "corpus" / "observations"
OWNERSHIP_DIR = TERMINAL_REPO / "state" / "research" / "ownership"

WRDS_BULK = REPO / "backend" / "data" / "optimus" / "wrds" / "bulk"
IBES_SURPSUMU = WRDS_BULK / "ibes__surpsumu.parquet"
CRSP_STOCKNAMES = WRDS_BULK / "crsp__stocknames.parquet"
EIGHTK_ITEMS = REPO / "backend" / "data" / "optimus" / "edgar_8k" / "eightk_items.parquet"

EVENTS_DIR = REPO / "backend" / "data" / "optimus" / "events"
EVENT_TABLE_PATH = EVENTS_DIR / "event_table_v1.parquet"
MANIFEST_PATH = EVENTS_DIR / "event_table_v1_manifest.json"

NIGHT_LAB_DIR = REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"

START_YEAR = 2015
#: as far as the entitlement / the pull reaches -- coverage receipt reports
#: whatever years actually have rows, this is just the reporting ceiling.
END_YEAR_CEILING = 2026

#: The columns of the unified table, in the order they are written. Every
#: source-writer function below returns a DataFrame with EXACTLY these columns
#: (nulls where the source has nothing) so `pd.concat` never silently upcasts
#: or reorders.
SCHEMA_COLUMNS = [
    "permno", "permno_link_method", "symbol",
    "event_type", "event_time_utc", "observed_at_utc", "observed_at_precision",
    "source", "title",
    "surprise_actual", "surprise_mean_estimate", "surprise_stdev", "surprise_suescore",
    "eightk_items",
    "ownership_form", "ownership_amendment",
    "independence_group",
    "year",
]

SCHEMA_NOTE = {
    "permno": "CRSP permno, float, nullable. Best-effort link -- see permno_link_method.",
    "permno_link_method": (
        "'native' (already carried by the source, e.g. eightk_items.parquet's own "
        "permno column), 'crsp_stocknames_interval' (ticker matched against "
        "crsp__stocknames.parquet with namedt<=event_date<=nameenddt, shrcd in "
        "(10,11) preferred), or 'unresolved'."),
    "symbol": "Upper-cased ticker as carried by the source. Always populated.",
    "event_type": "Coarse label: '8K:<item codes>', 'earnings_surprise', 'news', "
                   "'ownership:<SC 13D|SC 13G>[.amendment]'.",
    "event_time_utc": "When the thing HAPPENED (or, for IBES, when it became true "
                       "-- see observed_at_utc note). NOT safe to condition a "
                       "backtest on; use observed_at_utc.",
    "observed_at_utc": "When the row became AVAILABLE. The ONLY column safe to "
                        "filter a backtest on (observed_at_utc <= as_of).",
    "observed_at_precision": "'timestamp' (true time-of-day known) or 'date' "
                              "(only the calendar date is known; stamped 00:00 UTC).",
    "source": "'edgar_8k' | 'ibes_surpsumu' | 'alpaca:<wire>' | 'finnhub:<outlet>' | "
              "'sec_ownership'.",
    "title": "News headline. Null for non-news rows. Body text is deliberately "
              "NOT carried (memory; not needed for surprise/reaction grading).",
    "surprise_actual": "IBES actual EPS (surpsumu.actual). Null off earnings_surprise rows.",
    "surprise_mean_estimate": "IBES consensus mean estimate at announcement (surpmean).",
    "surprise_stdev": "IBES estimate dispersion (surpstdev).",
    "surprise_suescore": "Standardized unexpected earnings: (actual-mean)/stdev, "
                          "IBES's own computation (surpsumu.suescore).",
    "eightk_items": "Comma-joined 8-K item codes (e.g. '2.02,9.01'). Null off 8-K rows.",
    "ownership_form": "'SC 13D' | 'SC 13G' (normalised). Null off ownership rows.",
    "ownership_amendment": "bool. Null off ownership rows.",
    "independence_group": "Who is really speaking (news rows only; corpus.py's own field, "
                           "e.g. 'wire:benzinga'). Lets a consumer dedupe syndicated wires.",
    "year": "int16, derived from event_time_utc (or observed_at_utc if event_time_utc is "
            "null), for cheap year-partitioned coverage queries.",
}

PIT_RULE = (
    "observed_at_utc = the time the row became AVAILABLE, never the event's own "
    "timestamp. tense=='future' corpus rows (scheduled/forward) are DROPPED, not "
    "reused under the backward bound -- a shared bound between a backward news "
    "window and a forward calendar is the S24 defect this table refuses to repeat."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_receipt(name: str, receipt: dict, tracker: RP.InputTracker,
                   resolved_config: dict) -> Path:
    NIGHT_LAB_DIR.mkdir(parents=True, exist_ok=True)
    RP.attach(receipt, sys.argv, resolved_config, tracker)
    path = NIGHT_LAB_DIR / name
    path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8", newline="\n")
    return path


# --------------------------------------------------------- CRSP name linkage

def load_crsp_stocknames(tracker: RP.InputTracker) -> pd.DataFrame:
    df = pd.read_parquet(
        tracker.opened(CRSP_STOCKNAMES) and CRSP_STOCKNAMES,
        columns=["permno", "ticker", "namedt", "nameenddt", "shrcd"])
    df["ticker"] = df["ticker"].astype("string").str.upper()
    df["namedt"] = pd.to_datetime(df["namedt"], errors="coerce")
    df["nameenddt"] = pd.to_datetime(df["nameenddt"], errors="coerce")
    df = df.dropna(subset=["ticker", "namedt", "nameenddt"])
    return df


def link_permnos(df: pd.DataFrame, *, symbol_col: str, date_col: str,
                 names: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Best-effort (permno, method) for each row via a ticker+date-interval join.

    Merges on ticker (many-to-many; ~46k CRSP name rows over ~8-9k distinct
    tickers, so the blow-up per merge is small), filters to interval
    containment, prefers common stock (shrcd 10/11) on a tie, and keeps first.
    """
    if df.empty:
        return pd.Series(dtype="float64"), pd.Series(dtype="object")
    left = df[[symbol_col, date_col]].copy()
    left["_row"] = np.arange(len(left))
    left["_sym"] = left[symbol_col].astype("string").str.upper()
    left["_dt"] = pd.to_datetime(left[date_col], errors="coerce", utc=True).dt.tz_localize(None)
    merged = left.merge(names, left_on="_sym", right_on="ticker", how="left")
    ok = (merged["_dt"] >= merged["namedt"]) & (merged["_dt"] <= merged["nameenddt"])
    merged = merged[ok | merged["ticker"].isna()]
    merged["_pref"] = merged["shrcd"].isin([10, 11]).astype("int8")
    merged = merged.sort_values(["_row", "_pref"], ascending=[True, False])
    merged = merged.drop_duplicates(subset=["_row"], keep="first").sort_values("_row")
    permno = merged.set_index("_row")["permno"].reindex(left["_row"]).astype("float64")
    method = pd.Series(
        np.where(permno.notna().to_numpy(), "crsp_stocknames_interval", "unresolved"),
        index=permno.index)
    permno.index = df.index
    method.index = df.index
    return permno, method


# ----------------------------------------------------------------- 8-K tape

def load_8k(tracker: RP.InputTracker) -> pd.DataFrame:
    df = pd.read_parquet(
        tracker.opened(EIGHTK_ITEMS) and EIGHTK_ITEMS,
        columns=["cik", "ticker", "event_date", "filing_date", "acceptance_datetime",
                 "items_joined", "permno"])
    df["event_time_utc"] = pd.to_datetime(df["event_date"], errors="coerce", utc=True)
    df["observed_at_utc"] = pd.to_datetime(df["acceptance_datetime"], errors="coerce", utc=True)
    # A row whose acceptance timestamp failed to parse falls back to filing_date
    # at date precision -- filing_date is still a same-day-public bound, just
    # coarser than the true acceptance instant.
    fallback = pd.to_datetime(df["filing_date"], errors="coerce", utc=True)
    used_fallback = df["observed_at_utc"].isna() & fallback.notna()
    df.loc[used_fallback, "observed_at_utc"] = fallback[used_fallback]
    out = pd.DataFrame({
        "symbol": df["ticker"].astype("string").str.upper(),
        "event_type": "8K:" + df["items_joined"].astype("string").fillna(""),
        "event_time_utc": df["event_time_utc"],
        "observed_at_utc": df["observed_at_utc"],
        "observed_at_precision": np.where(used_fallback, "date", "timestamp"),
        "source": "edgar_8k",
        "eightk_items": df["items_joined"].astype("string"),
        "permno": df["permno"].astype("float64"),
        "permno_link_method": np.where(df["permno"].notna(), "native", "unresolved"),
    })
    out = out.dropna(subset=["event_time_utc", "observed_at_utc"])
    return out


# ------------------------------------------------------------- IBES surprise

def load_ibes_surprise(tracker: RP.InputTracker, names: pd.DataFrame) -> pd.DataFrame:
    df = pd.read_parquet(
        tracker.opened(IBES_SURPSUMU) and IBES_SURPSUMU,
        columns=["oftic", "measure", "anndats", "actual", "surpmean", "surpstdev", "suescore"])
    df = df[df["measure"] == "EPS"].copy()
    df = df.dropna(subset=["oftic", "anndats"])
    ts = pd.to_datetime(df["anndats"], errors="coerce", utc=True)
    out = pd.DataFrame({
        "symbol": df["oftic"].astype("string").str.upper(),
        "event_type": "earnings_surprise",
        "event_time_utc": ts,
        "observed_at_utc": ts,
        "observed_at_precision": "date",
        "source": "ibes_surpsumu",
        "surprise_actual": df["actual"].astype("float64"),
        "surprise_mean_estimate": df["surpmean"].astype("float64"),
        "surprise_stdev": df["surpstdev"].astype("float64"),
        "surprise_suescore": df["suescore"].astype("float64"),
    })
    out = out.dropna(subset=["event_time_utc"])
    permno, method = link_permnos(out, symbol_col="symbol", date_col="event_time_utc", names=names)
    out["permno"] = permno
    out["permno_link_method"] = method
    return out


# -------------------------------------------------------------- news corpus

def load_news_corpus(tracker: RP.InputTracker, *, start_year: int, end_year: int,
                     names: pd.DataFrame) -> pd.DataFrame:
    """Alpaca/Benzinga + Finnhub rows from `alpha.sources.corpus`'s own store.

    Reads shard files directly (no import of the terminal repo's package --
    this job only ever READS its jsonl store) and filters to
    kind=='news' AND tense=='past', which is exactly what `news_backfill.py`
    writes (both alpaca_history() and finnhub_history() tag kind='news',
    tense='past'). Body text is dropped on read to bound memory.
    """
    if not CORPUS_OBS_DIR.exists():
        return pd.DataFrame(columns=["symbol", "event_type", "event_time_utc",
                                     "observed_at_utc", "source", "title",
                                     "independence_group"])
    rows: list[dict] = []
    for shard in sorted(CORPUS_OBS_DIR.glob("*.jsonl")):
        try:
            y = int(shard.stem[:4])
        except ValueError:
            continue
        if y < start_year or y > end_year:
            continue
        tracker.opened(shard)
        for line in shard.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("kind") != "news" or r.get("tense") != "past":
                continue
            for sym in (r.get("symbols") or []):
                rows.append({
                    "symbol": str(sym).upper(),
                    "observed_at": r.get("observed_at"),
                    "effective_at": r.get("effective_at"),
                    "source": r.get("source"),
                    "title": r.get("title"),
                    "independence_group": r.get("independence_group"),
                })
    if not rows:
        return pd.DataFrame(columns=["symbol", "event_type", "event_time_utc",
                                     "observed_at_utc", "source", "title",
                                     "independence_group"])
    df = pd.DataFrame(rows)
    obs = pd.to_datetime(df["observed_at"], errors="coerce", utc=True)
    eff = pd.to_datetime(df["effective_at"], errors="coerce", utc=True)
    out = pd.DataFrame({
        "symbol": df["symbol"].astype("string"),
        "event_type": "news",
        "event_time_utc": eff.fillna(obs),
        "observed_at_utc": obs,
        "observed_at_precision": "timestamp",
        "source": df["source"].astype("string"),
        "title": df["title"].astype("string"),
        "independence_group": df["independence_group"].astype("string"),
    })
    out = out.dropna(subset=["observed_at_utc"])
    permno, method = link_permnos(out, symbol_col="symbol", date_col="event_time_utc", names=names)
    out["permno"] = permno
    out["permno_link_method"] = method
    return out


# -------------------------------------------------------------- ownership

def load_ownership(tracker: RP.InputTracker, names: pd.DataFrame) -> pd.DataFrame:
    if not OWNERSHIP_DIR.exists():
        return pd.DataFrame(columns=["symbol", "event_type", "event_time_utc",
                                     "observed_at_utc"])
    rows: list[dict] = []
    for shard in sorted(OWNERSHIP_DIR.glob("*.jsonl")):
        tracker.opened(shard)
        for line in shard.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            sym = r.get("subject_ticker")
            if not sym:
                continue
            rows.append({
                "symbol": str(sym).upper(),
                "filed_date": r.get("filed_date"),
                "form_normalised": r.get("form_normalised"),
                "amendment": r.get("amendment"),
            })
    if not rows:
        return pd.DataFrame(columns=["symbol", "event_type", "event_time_utc",
                                     "observed_at_utc"])
    df = pd.DataFrame(rows)
    ts = pd.to_datetime(df["filed_date"], errors="coerce", utc=True)
    out = pd.DataFrame({
        "symbol": df["symbol"].astype("string"),
        "event_type": "ownership:" + df["form_normalised"].astype("string").fillna("?")
                      + np.where(df["amendment"].fillna(False), ".amendment", ""),
        "event_time_utc": ts,
        "observed_at_utc": ts,          # EDGAR filing is public same-day (see docstring)
        "observed_at_precision": "date",
        "source": "sec_ownership",
        "ownership_form": df["form_normalised"].astype("string"),
        "ownership_amendment": df["amendment"].astype("boolean"),
    })
    out = out.dropna(subset=["event_time_utc"])
    permno, method = link_permnos(out, symbol_col="symbol", date_col="event_time_utc", names=names)
    out["permno"] = permno
    out["permno_link_method"] = method
    return out


# -------------------------------------------------- the true tradable universe (cheap proxy)

def listed_universe_by_year(names: pd.DataFrame, years: range) -> dict[int, int]:
    """Distinct permnos with a valid common-stock (shrcd 10/11) CRSP name record
    active at ANY point in the calendar year. A cheap, honest proxy for "the
    tradable universe" -- NOT the $3m/day liquidity-floored research universe
    (`learner.neural_long.tradable_universe`, ~400MB panel), which this job
    deliberately does not load (memory budget; see module docstring)."""
    common = names[names["shrcd"].isin([10, 11])]
    out = {}
    for y in years:
        y0 = pd.Timestamp(y, 1, 1)
        y1 = pd.Timestamp(y, 12, 31)
        mask = (common["namedt"] <= y1) & (common["nameenddt"] >= y0)
        out[y] = int(common.loc[mask, "permno"].nunique())
    return out


# --------------------------------------------------------------------- build

def build(*, start_year: int = START_YEAR, end_year: int = END_YEAR_CEILING) -> dict:
    t0 = time.perf_counter()
    tracker = RP.InputTracker()
    mem0 = free_gb()
    report: dict = {
        "job": "N4_event_table_build", "lane": "N4",
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
        "memory_free_gb_before": mem0,
        "pit_rule": PIT_RULE,
    }
    if mem0 is not None and mem0 < 2.0:
        report["status"] = "REFUSED"
        report["reasons"] = [f"free_gb={mem0} < 2.0 GB guard; refusing a heavy build"]
        report["wall_seconds"] = round(time.perf_counter() - t0, 1)
        return _finalize(report, tracker, start_year, end_year)

    names = load_crsp_stocknames(tracker)

    frames: list[pd.DataFrame] = []
    counts: dict[str, dict] = {}

    for label, fn in (
        ("edgar_8k", lambda: load_8k(tracker)),
        ("ibes_surpsumu", lambda: load_ibes_surprise(tracker, names)),
        ("news_corpus", lambda: load_news_corpus(tracker, start_year=start_year,
                                                  end_year=end_year, names=names)),
        ("sec_ownership", lambda: load_ownership(tracker, names)),
    ):
        try:
            df = fn()
            n_before = len(df)
            df = df[(df["event_time_utc"].dt.year >= start_year)
                    & (df["event_time_utc"].dt.year <= end_year)]
            counts[label] = {"rows_all_years": n_before, "rows_in_scope": len(df),
                             "status": "OK"}
            frames.append(df)
        except FileNotFoundError as exc:
            counts[label] = {"status": "ABSENT", "why": str(exc)}
        except Exception as exc:                                        # noqa: BLE001
            counts[label] = {"status": "CRASHED", "why": f"{type(exc).__name__}: {exc}",
                             "traceback": traceback.format_exc()[-2000:]}

    report["source_counts"] = counts

    if not frames or all(f.empty for f in frames):
        report["status"] = "REFUSED"
        report["reasons"] = ["every source empty or absent -- nothing to write"]
        report["wall_seconds"] = round(time.perf_counter() - t0, 1)
        return _finalize(report, tracker, start_year, end_year)

    table = pd.concat(frames, ignore_index=True, sort=False)
    for c in SCHEMA_COLUMNS:
        if c not in table.columns:
            table[c] = pd.Series([pd.NA] * len(table))
    table = table[SCHEMA_COLUMNS]
    table["year"] = table["event_time_utc"].dt.year.astype("Int16")
    table = table.sort_values(["event_time_utc", "symbol"]).reset_index(drop=True)

    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    table.to_parquet(EVENT_TABLE_PATH, index=False)

    permno_share = float(table["permno"].notna().mean()) if len(table) else None
    report["status"] = "OK"
    report["rows_written"] = int(len(table))
    report["distinct_symbols"] = int(table["symbol"].nunique())
    report["permno_link_share"] = round(permno_share, 4) if permno_share is not None else None
    report["by_source"] = {s: int(n) for s, n in table["source"].value_counts().items()}
    report["by_event_type_top20"] = {k: int(v) for k, v in
                                     table["event_type"].value_counts().head(20).items()}
    # Named *_output_path (not *_path) so the provenance checker's input-key
    # heuristic does not mistake a file this job WROTE for one it claims to
    # have read (backend/services/receipt_provenance.py's `_OUTPUT_HINTS`
    # matches on "output"; a bare "*_path" suffix reads as an input claim).
    report["event_table_output_path"] = str(EVENT_TABLE_PATH)
    report["manifest_output_path"] = str(MANIFEST_PATH)
    report["wall_seconds"] = round(time.perf_counter() - t0, 1)

    manifest = {
        "tape": "event_table_v1",
        "built_utc": _now(),
        "rows": int(len(table)),
        "distinct_symbols": int(table["symbol"].nunique()),
        "distinct_permnos_linked": int(table["permno"].dropna().nunique()),
        "permno_link_share": report["permno_link_share"],
        "by_source": report["by_source"],
        "year_range_requested": [start_year, end_year],
        "year_range_present": [int(table["year"].min()), int(table["year"].max())]
                              if len(table) else None,
        "pit_rule": PIT_RULE,
        "schema": SCHEMA_NOTE,
        "sources": {
            "edgar_8k": str(EIGHTK_ITEMS),
            "ibes_surpsumu": str(IBES_SURPSUMU),
            "crsp_stocknames_linkage": str(CRSP_STOCKNAMES),
            "news_corpus": str(CORPUS_OBS_DIR),
            "sec_ownership": str(OWNERSHIP_DIR),
        },
        "known_absences": [
            "Form 4 (insider transactions): no table entitled or on disk anywhere "
            "in either repo (searched backend/data/optimus/wrds/bulk and both "
            "repos' state/); tfn__s34type* is 13F institutional, not Form 4.",
            "13D/13G: present but thin -- 7 days (2026-08-13..2026-08-20) from a "
            "smoke test of alpha/sources/edgar_ownership.py; a full backfill to "
            "2015 is a separate ~4,000-calendar-day network job, not run here.",
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=1, default=str),
                             encoding="utf-8", newline="\n")

    return _finalize(report, tracker, start_year, end_year)


def _finalize(report: dict, tracker: RP.InputTracker, start_year: int, end_year: int) -> dict:
    report["memory_free_gb_after"] = free_gb()
    RP.attach(report, sys.argv,
             {"start_year": {"value": start_year, "source": "arg"},
              "end_year": {"value": end_year, "source": "arg"}},
             tracker)
    NIGHT_LAB_DIR.mkdir(parents=True, exist_ok=True)
    path = NIGHT_LAB_DIR / "N4_event_table_build_run01.json"
    path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8", newline="\n")
    report["_receipt_path"] = str(path)
    return report


# --------------------------------------------------------------- coverage by year

def coverage_receipt(*, start_year: int = START_YEAR, end_year: int = END_YEAR_CEILING) -> dict:
    tracker = RP.InputTracker()
    report: dict = {
        "job": "N4_coverage_by_year", "lane": "N4",
        "memory_free_gb_before": free_gb(),
    }
    if not EVENT_TABLE_PATH.exists():
        report["status"] = "SKIPPED"
        report["reasons"] = [f"{EVENT_TABLE_PATH} does not exist -- run --build first"]
        return _write_coverage(report, tracker, start_year, end_year)

    table = pd.read_parquet(tracker.opened(EVENT_TABLE_PATH) and EVENT_TABLE_PATH)
    names = load_crsp_stocknames(tracker)
    years = range(start_year, end_year + 1)
    universe = listed_universe_by_year(names, years)

    by_year: dict[str, dict] = {}
    for y in years:
        sub = table[table["year"] == y]
        n_names = int(sub["symbol"].nunique())
        n_permnos = int(sub["permno"].dropna().nunique())
        u = universe.get(y) or 0
        by_source = {s: int(n) for s, n in sub["source"].value_counts().items()}
        by_year[str(y)] = {
            "rows": int(len(sub)),
            "distinct_symbols": n_names,
            "distinct_permnos_linked": n_permnos,
            "listed_common_stock_universe_proxy": u,
            # PERMNO-based share only -- this is the well-defined subset
            # relationship (permno is CRSP's own key, so a linked permno is BY
            # CONSTRUCTION a member of the proxy universe). A raw SYMBOL-count
            # ratio is NOT well-defined here and was dropped: IBES alone covers
            # a broader security universe than CRSP common stock (OTC, ADRs,
            # multiple share classes, non-primary listings), so distinct_symbols
            # can and does exceed listed_common_stock_universe_proxy (measured
            # 2015: 16,140 symbols vs 3,997 proxy permnos) without that being a
            # coverage number at all.
            "share_of_universe_proxy_covered": (round(n_permnos / u, 4) if u else None),
            "by_source": by_source,
            "thin": bool(len(sub) < 100),
        }
    thin_years = [y for y, v in by_year.items() if v["thin"]]
    report["status"] = "OK"
    report["by_year"] = by_year
    report["thin_years"] = thin_years
    report["thin_years_why"] = (
        "A year is 'thin' (<100 rows) either because the news_backfill network "
        "pull had not reached that far back yet when this receipt was written "
        "(re-run after the pull progresses further -- it is resumable and "
        "append-only), or because a source structurally has no coverage there "
        "(13D/13G: everything before 2026-08-13; Form 4: everywhere -- see "
        "event_table_v1_manifest.json 'known_absences').")
    report["universe_proxy_note"] = (
        "'listed_common_stock_universe_proxy' = distinct CRSP permnos with "
        "shrcd in (10,11) and a name record active in that year -- an HONEST "
        "but LOOSE proxy for 'the tradable universe' (all listed common stock, "
        "not the $3m/day liquidity-floored research universe, which this job "
        "does not load to respect the RAM budget -- see module docstring). "
        "'share_of_universe_proxy_covered' is computed on LINKED PERMNOS, not "
        "raw symbol counts -- distinct_symbols routinely exceeds the proxy "
        "universe because IBES alone covers many securities CRSP common stock "
        "does not (OTC, ADRs, multiple share classes); that is not a coverage "
        "number and is reported separately for transparency, not as a share.")
    return _write_coverage(report, tracker, start_year, end_year)


def _write_coverage(report: dict, tracker: RP.InputTracker, start_year: int, end_year: int) -> dict:
    report["memory_free_gb_after"] = free_gb()
    RP.attach(report, sys.argv,
             {"start_year": {"value": start_year, "source": "arg"},
              "end_year": {"value": end_year, "source": "arg"}},
             tracker)
    NIGHT_LAB_DIR.mkdir(parents=True, exist_ok=True)
    path = NIGHT_LAB_DIR / "N4_coverage_by_year.json"
    path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8", newline="\n")
    report["_receipt_path"] = str(path)
    return report


# ------------------------------------------------------------------------ CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="build event_table_v1.parquet")
    ap.add_argument("--coverage-only", action="store_true",
                    help="just (re)write the by-year coverage receipt from the "
                         "existing parquet")
    ap.add_argument("--start-year", type=int, default=START_YEAR)
    ap.add_argument("--end-year", type=int, default=END_YEAR_CEILING)
    a = ap.parse_args(argv)

    if a.coverage_only:
        rec = coverage_receipt(start_year=a.start_year, end_year=a.end_year)
        print(json.dumps({k: v for k, v in rec.items() if k != "by_year"}, indent=1, default=str))
        return 0

    rec = build(start_year=a.start_year, end_year=a.end_year)
    print(json.dumps({k: v for k, v in rec.items() if k not in ("by_year",)},
                     indent=1, default=str))
    if rec.get("status") == "OK":
        cov = coverage_receipt(start_year=a.start_year, end_year=a.end_year)
        print(f"coverage receipt -> {cov.get('_receipt_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
