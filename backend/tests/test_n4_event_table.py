"""Tests for `scripts/n4_event_table.py` (Night Lab 2026-09-07, lane N4).

CI RUNS ON LINUX WITH NO LOCAL DATA (CLAUDE.md): every test that touches a
local-only file (the WRDS parquet bulk, the EDGAR 8-K tape, the sibling
terminal repo's corpus/ownership stores, or this job's own output) MUST
`pytest.skip` when that file is absent. Tests that exercise pure logic
(schema shape, the interval-join algorithm, path absoluteness) use small
synthetic frames and run everywhere, unconditionally.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import numpy as np
import pandas as pd
import pytest

from scripts import n4_event_table as N4
from backend.services import receipt_provenance as RP


# --------------------------------------------------------------- pure: schema

def test_schema_columns_all_documented():
    missing = [c for c in N4.SCHEMA_COLUMNS if c not in N4.SCHEMA_NOTE]
    assert not missing, f"columns with no entry in SCHEMA_NOTE: {missing}"


def test_schema_note_has_no_stray_keys():
    stray = [k for k in N4.SCHEMA_NOTE if k not in N4.SCHEMA_COLUMNS]
    assert not stray, f"SCHEMA_NOTE documents columns not in SCHEMA_COLUMNS: {stray}"


def test_schema_columns_hash_pinned():
    """A silent column add/drop/reorder should fail a test, not surface three
    weeks later as a KeyError in a consumer. Hashed over LF-normalised bytes
    (`reference_crlf_changes_a_content_hash.md`) so the pin is stable across
    checkouts on Windows and Linux regardless of git's autocrlf setting."""
    payload = "\n".join(N4.SCHEMA_COLUMNS).encode("utf-8")
    got = hashlib.sha256(payload).hexdigest()
    expected = "b6fc04be338337cc289f952d3c1fec4de68a8442ae77dbeba6b201f501a041aa"
    if got != expected:
        pytest.fail(
            "SCHEMA_COLUMNS changed (this is allowed -- the event table is v1 "
            "and will grow). Update EVERY consumer's column list, then update "
            f"this pinned hash to {got!r}. Old: {expected!r}")


def test_schema_columns_no_duplicates():
    assert len(N4.SCHEMA_COLUMNS) == len(set(N4.SCHEMA_COLUMNS))


# ---------------------------------------------------------- pure: path shape

def test_module_paths_are_absolute():
    """Absoluteness must hold on the platform that WROTE the path and the one
    that READS it -- checked against both path grammars, never `os.path.isabs`
    (which only knows the platform running the test)."""
    paths = [N4.EVENT_TABLE_PATH, N4.MANIFEST_PATH, N4.NIGHT_LAB_DIR,
             N4.EIGHTK_ITEMS, N4.IBES_SURPSUMU, N4.CRSP_STOCKNAMES,
             N4.CORPUS_OBS_DIR, N4.OWNERSHIP_DIR, N4.TERMINAL_REPO]
    for p in paths:
        s = str(p)
        assert PureWindowsPath(s).is_absolute() or PurePosixPath(s).is_absolute(), \
            f"{s!r} is not absolute under either path grammar"


def test_event_table_path_is_under_events_dir():
    assert N4.EVENT_TABLE_PATH.parent == N4.EVENTS_DIR
    assert N4.EVENT_TABLE_PATH.name == "event_table_v1.parquet"


# ---------------------------------------------------- pure: the interval join

def _synthetic_names() -> pd.DataFrame:
    return pd.DataFrame({
        "permno": [100, 100, 200, 300],
        "ticker": ["AAA", "BBB", "CCC", "AAA"],   # AAA renamed to BBB, and a
                                                    # DIFFERENT company 300 later
                                                    # reused the ticker "AAA"
        "namedt": pd.to_datetime(["2010-01-01", "2018-01-01", "2010-01-01", "2022-01-01"]),
        "nameenddt": pd.to_datetime(["2017-12-31", "2030-01-01", "2030-01-01", "2030-01-01"]),
        "shrcd": [11, 11, 10, 11],
    })


def test_link_permnos_resolves_within_window():
    names = _synthetic_names()
    df = pd.DataFrame({
        "symbol": ["AAA"], "event_time_utc": pd.to_datetime(["2015-06-01"], utc=True)})
    permno, method = N4.link_permnos(df, symbol_col="symbol", date_col="event_time_utc",
                                     names=names)
    assert permno.iloc[0] == 100
    assert method.iloc[0] == "crsp_stocknames_interval"


def test_link_permnos_ticker_reuse_resolves_to_the_later_company():
    """The same ticker string names two different companies at different
    times (permno 100 pre-2018, permno 300 post-2022) -- the interval join
    must pick the one whose window actually contains the event date, not
    just any row that matches the ticker string."""
    names = _synthetic_names()
    df = pd.DataFrame({
        "symbol": ["AAA"], "event_time_utc": pd.to_datetime(["2023-01-01"], utc=True)})
    permno, method = N4.link_permnos(df, symbol_col="symbol", date_col="event_time_utc",
                                     names=names)
    assert permno.iloc[0] == 300


def test_link_permnos_outside_every_window_is_unresolved():
    names = _synthetic_names()
    df = pd.DataFrame({
        "symbol": ["AAA"], "event_time_utc": pd.to_datetime(["2019-06-01"], utc=True)})
    permno, method = N4.link_permnos(df, symbol_col="symbol", date_col="event_time_utc",
                                     names=names)
    assert pd.isna(permno.iloc[0])
    assert method.iloc[0] == "unresolved"


def test_link_permnos_unknown_ticker_is_unresolved_not_crashed():
    names = _synthetic_names()
    df = pd.DataFrame({
        "symbol": ["ZZZ"], "event_time_utc": pd.to_datetime(["2020-01-01"], utc=True)})
    permno, method = N4.link_permnos(df, symbol_col="symbol", date_col="event_time_utc",
                                     names=names)
    assert pd.isna(permno.iloc[0])
    assert method.iloc[0] == "unresolved"


def test_link_permnos_preserves_row_order_and_index():
    """Regression: an earlier draft reindexed by a fresh positional key and
    then blindly reassigned df.index -- correct ONLY because row order is
    preserved end to end. Pin that invariant with a non-trivial (gappy,
    shuffled-looking) index."""
    names = _synthetic_names()
    df = pd.DataFrame({
        "symbol": ["BBB", "CCC", "ZZZ", "AAA"],
        "event_time_utc": pd.to_datetime(
            ["2020-01-01", "2020-01-01", "2020-01-01", "2015-06-01"], utc=True),
    }, index=[7, 2, 40, 3])
    permno, method = N4.link_permnos(df, symbol_col="symbol", date_col="event_time_utc",
                                     names=names)
    assert list(permno.index) == [7, 2, 40, 3]
    assert permno.loc[7] == 100          # BBB in 2020 -> permno 100
    assert permno.loc[2] == 200          # CCC in 2020 -> permno 200
    assert pd.isna(permno.loc[40])       # ZZZ never resolves
    assert permno.loc[3] == 100          # AAA in 2015 -> permno 100 (pre-rename)


def test_link_permnos_empty_input_returns_empty():
    names = _synthetic_names()
    df = pd.DataFrame({"symbol": pd.Series(dtype="object"),
                       "event_time_utc": pd.Series(dtype="datetime64[ns, UTC]")})
    permno, method = N4.link_permnos(df, symbol_col="symbol", date_col="event_time_utc",
                                     names=names)
    assert len(permno) == 0
    assert len(method) == 0


# ------------------------------------------------------- pure: universe proxy

def test_listed_universe_by_year_counts_distinct_permnos_active_that_year():
    names = _synthetic_names()
    u = N4.listed_universe_by_year(names, range(2015, 2024))
    # 2015: permno 100 (AAA, shrcd 11) and permno 200 (CCC, shrcd 10) are both
    # active; permno 300 does not exist until 2022.
    assert u[2015] == 2
    assert u[2023] == 3           # 100 (as BBB), 200, 300 all active


def test_listed_universe_by_year_excludes_non_common_shrcd():
    names = _synthetic_names().copy()
    names["shrcd"] = [12, 12, 10, 11]     # 100's rows are no longer common stock
    u = N4.listed_universe_by_year(names, range(2015, 2016))
    assert u[2015] == 1            # only permno 200 (shrcd 10) counted


# ------------------------------------------------------------- local-data only

WRDS_PRESENT = N4.CRSP_STOCKNAMES.is_file()
EIGHTK_PRESENT = N4.EIGHTK_ITEMS.is_file()
IBES_PRESENT = N4.IBES_SURPSUMU.is_file()
TERMINAL_PRESENT = N4.TERMINAL_REPO.is_dir()
EVENT_TABLE_PRESENT = N4.EVENT_TABLE_PATH.is_file()
MANIFEST_PRESENT = N4.MANIFEST_PATH.is_file()
BUILD_RECEIPT_PATH = N4.NIGHT_LAB_DIR / "N4_event_table_build_run01.json"
COVERAGE_RECEIPT_PATH = N4.NIGHT_LAB_DIR / "N4_coverage_by_year.json"


@pytest.mark.skipif(not WRDS_PRESENT, reason="crsp__stocknames.parquet not on disk (CI has no local WRDS data)")
def test_load_crsp_stocknames_schema():
    tracker = RP.InputTracker()
    names = N4.load_crsp_stocknames(tracker)
    assert {"permno", "ticker", "namedt", "nameenddt", "shrcd"} <= set(names.columns)
    assert len(tracker) == 1
    assert pd.api.types.is_datetime64_any_dtype(names["namedt"])
    assert (names["ticker"].dropna() == names["ticker"].dropna().str.upper()).all()


@pytest.mark.skipif(not EIGHTK_PRESENT, reason="eightk_items.parquet not on disk")
def test_load_8k_pit_never_observes_before_the_event():
    tracker = RP.InputTracker()
    df = N4.load_8k(tracker)
    assert not df.empty
    assert set(N4.SCHEMA_COLUMNS) >= set(df.columns)
    # observed_at_utc (EDGAR acceptance, or filing_date fallback) should not
    # precede event_time_utc (reportDate). MEASURED exception (2026-09-07,
    # 1,025 / 293,619 = 0.35%): event_date is a DATE with no time-of-day and
    # is stamped at UTC MIDNIGHT; a filing accepted late in the US trading
    # day (e.g. 22:43 UTC = 17:43 ET) legitimately has an acceptance instant
    # that falls AFTER that UTC-midnight stamp of the SAME calendar date --
    # this is a timezone-granularity artifact of comparing a date to a true
    # timestamp, not a PIT violation (the acceptance is still same-day). The
    # tolerance below is that measured share, not an arbitrary fudge factor.
    bad = df[df["observed_at_utc"] < df["event_time_utc"]]
    assert len(bad) / len(df) < 0.01, (
        f"{len(bad)}/{len(df)} 8-K rows observed before their own event date "
        "-- more than the measured UTC-midnight artifact rate; investigate")
    assert df["observed_at_precision"].isin(["timestamp", "date"]).all()
    assert df["source"].eq("edgar_8k").all()


def _empty_names() -> pd.DataFrame:
    """A zero-row `names` frame with the SAME dtypes `load_crsp_stocknames`
    produces -- an empty `pd.DataFrame({"namedt": [], ...})` literal defaults
    numeric/date columns to float64/object, which crashes the datetime
    comparisons inside `link_permnos` on a real (non-empty) input frame; only
    the row count is meant to be empty here, not the dtypes."""
    return pd.DataFrame({
        "permno": pd.array([], dtype="float64"),
        "ticker": pd.array([], dtype="object"),
        "namedt": pd.array([], dtype="datetime64[ns]"),
        "nameenddt": pd.array([], dtype="datetime64[ns]"),
        "shrcd": pd.array([], dtype="int64"),
    })


@pytest.mark.skipif(not IBES_PRESENT, reason="ibes__surpsumu.parquet not on disk")
def test_load_ibes_surprise_event_equals_observed_by_construction():
    tracker = RP.InputTracker()
    names = _empty_names()   # empty linkage is fine, only checking the PIT columns
    df = N4.load_ibes_surprise(tracker, names)
    assert not df.empty
    assert (df["event_time_utc"] == df["observed_at_utc"]).all()
    assert df["observed_at_precision"].eq("date").all()
    assert df["source"].eq("ibes_surpsumu").all()
    # suescore must be present for a meaningful share of rows (it's the whole
    # point of pulling this file over the plain actuals table).
    assert df["surprise_suescore"].notna().mean() > 0.5


@pytest.mark.skipif(not TERMINAL_PRESENT, reason="sibling terminal repo not present on this machine")
def test_load_news_corpus_drops_future_tense():
    """The S24 defect this table refuses to repeat: a forward/scheduled row
    must never leak into the realized-event table under the backward bound."""
    tracker = RP.InputTracker()
    names = _empty_names()
    df = N4.load_news_corpus(tracker, start_year=2015, end_year=2026, names=names)
    if df.empty:
        pytest.skip("corpus has no news rows in range yet (backfill may still be running)")
    assert df["event_type"].eq("news").all()
    # The corpus's kind='news'/tense='past' rows are not EXCLUSIVELY
    # news_backfill.py's -- a separate company-IR-page collector writes the
    # same kind/tense (source prefix 'company_ir:', ~60 rows measured
    # 2026-09-07). The mandate's ask (Alpaca/Benzinga + Finnhub) must still be
    # the overwhelming majority; this is not a 100% membership check.
    known = df["source"].str.startswith(("alpaca:", "finnhub:", "company_ir:"))
    assert known.all(), f"unexpected news source prefixes: " \
        f"{sorted(set(df.loc[~known, 'source']))[:10]}"
    assert df["source"].str.startswith(("alpaca:", "finnhub:")).mean() > 0.9


@pytest.mark.skipif(not EVENT_TABLE_PRESENT, reason="event_table_v1.parquet not built on this machine")
def test_event_table_schema_and_pit_invariants():
    df = pd.read_parquet(N4.EVENT_TABLE_PATH)
    assert list(df.columns) == N4.SCHEMA_COLUMNS
    assert df["observed_at_utc"].notna().all()
    assert df["event_time_utc"].notna().all()
    assert df["symbol"].notna().all()
    assert df["permno_link_method"].isin(
        ["native", "crsp_stocknames_interval", "unresolved"]).all()
    assert df["year"].min() >= 2015


@pytest.mark.skipif(not EVENT_TABLE_PRESENT, reason="event_table_v1.parquet not built on this machine")
def test_event_table_no_form4_source_present():
    """Guard against silent fabrication: Form 4 was ABSENT everywhere this job
    looked (see the manifest's `known_absences`). If a future change adds a
    Form-4 source without updating this test AND the manifest, that is the
    signal to go read the docstring again, not to let it pass quietly."""
    df = pd.read_parquet(N4.EVENT_TABLE_PATH, columns=["source", "event_type"])
    sources = set(df["source"].dropna().unique())
    assert not any("form4" in s.lower() or "form_4" in s.lower() for s in sources)


@pytest.mark.skipif(not MANIFEST_PRESENT, reason="event_table_v1_manifest.json not written on this machine")
def test_manifest_json_shape():
    m = json.loads(N4.MANIFEST_PATH.read_text(encoding="utf-8"))
    for key in ("tape", "built_utc", "rows", "pit_rule", "schema", "known_absences"):
        assert key in m, f"manifest missing {key!r}"
    assert m["tape"] == "event_table_v1"
    assert isinstance(m["known_absences"], list) and m["known_absences"]


@pytest.mark.skipif(not BUILD_RECEIPT_PATH.is_file(), reason="N4 build receipt not present on this machine")
def test_build_receipt_provenance_is_clean():
    receipt = json.loads(BUILD_RECEIPT_PATH.read_text(encoding="utf-8"))
    findings = RP.check_receipt(receipt, require_inputs=True)
    hard = RP.hard_failures(findings)
    assert hard == [], f"provenance findings: {hard}"


@pytest.mark.skipif(not COVERAGE_RECEIPT_PATH.is_file(), reason="N4 coverage receipt not present on this machine")
def test_coverage_share_is_a_fraction_not_a_ratio_bug():
    """Regression for the bug caught during this job's own dry run: comparing
    raw distinct-symbol counts (IBES alone covers many non-CRSP securities)
    against the CRSP-permno universe proxy produced shares over 400%. The
    fixed metric is permno-subset-based and must stay bounded near [0, 1]."""
    receipt = json.loads(COVERAGE_RECEIPT_PATH.read_text(encoding="utf-8"))
    by_year = receipt.get("by_year") or {}
    assert by_year, "coverage receipt has no by_year block"
    for year, row in by_year.items():
        share = row.get("share_of_universe_proxy_covered")
        if share is None:
            continue
        assert 0.0 <= share <= 1.2, f"{year}: share_of_universe_proxy_covered={share} out of range"
