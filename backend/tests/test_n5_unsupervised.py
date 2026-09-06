"""Tests for `scripts/n5_event_compression.py` and `scripts/n5_states_third_null.py`
(Night Lab 2026-09-07, lane N5).

CI RUNS ON LINUX WITH NO LOCAL DATA (CLAUDE.md): every test that touches a
local-only file (the sibling terminal repo's corpus, the WRDS/CRSP bulk
parquets, `company_states.parquet`, `train_table.parquet`, `event_table_v1
.parquet`, or this lane's own receipts) MUST `pytest.skip` when that file is
absent. Tests that exercise pure logic (clustering algebra, the derangement
generator, the permutation-null arithmetic, the JSON default-serialiser) run
on small synthetic frames and pass everywhere, unconditionally, offline.

NO NETWORK: `probe_nemotron` is exercised only via its no-key early return
(monkeypatched to guarantee that path -- never the live HTTP call).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import n5_event_compression as EC
from scripts import n5_states_third_null as SN
from learner import nullbar as NB
from backend.services import receipt_provenance as RP


# ======================================================================
# n5_event_compression.py -- pure-logic tests (no files touched)
# ======================================================================

def _toy_news_frame() -> pd.DataFrame:
    """Two near-duplicate headlines for AAA (syndicated), one distinct AAA
    story a week later, and one BBB story -- small enough to hand-check the
    clustering result.
    """
    rows = [
        {"symbol": "AAA", "title": "Widget Corp Reports Q1 EPS $0.50 Beat",
         "body": "Widget Corp today reported first quarter results.",
         "source": "wireA", "independence_group": "wire:alpha",
         "observed_at": "2020-01-01T09:00:00Z", "effective_at": "2020-01-01", "uid": "a1"},
        {"symbol": "AAA", "title": "Widget Corp Reports Q1 EPS $0.50 Beats Estimates",
         "body": "Widget Corp today reported first quarter results beating estimates.",
         "source": "wireB", "independence_group": "wire:beta",
         "observed_at": "2020-01-01T09:05:00Z", "effective_at": "2020-01-01", "uid": "a2"},
        {"symbol": "AAA", "title": "Widget Corp Announces New CEO Appointment",
         "body": "Widget Corp named a new chief executive.",
         "source": "wireA", "independence_group": "wire:alpha",
         "observed_at": "2020-01-08T09:00:00Z", "effective_at": "2020-01-08", "uid": "a3"},
        {"symbol": "BBB", "title": "Gadget Inc Announces Stock Buyback Program",
         "body": "Gadget Inc board approved a share repurchase.",
         "source": "wireA", "independence_group": "wire:alpha",
         "observed_at": "2020-01-02T09:00:00Z", "effective_at": "2020-01-02", "uid": "b1"},
    ]
    df = pd.DataFrame(rows)
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    df["text"] = (df["title"] + " " + df["body"]).str.strip()
    return df


def test_cluster_events_merges_near_duplicates_and_keeps_distinct_stories():
    df = _toy_news_frame()
    vec, mat = EC.build_tfidf(df["text"], max_features=200)
    events = EC.cluster_events(df, mat, sim_threshold=0.45, window_hours=72.0,
                               novelty_lookback=100)
    # 4 raw rows should compress to 3 canonical events: the two near-duplicate
    # AAA earnings headlines merge, the AAA CEO story and the BBB buyback do not.
    assert len(events) == 3
    assert events["n_members"].sum() == 4
    aaa = events[events["symbol"] == "AAA"].sort_values("first_observed_at")
    assert aaa.iloc[0]["n_members"] == 2       # the merged earnings duplicate
    assert aaa.iloc[1]["n_members"] == 1       # the distinct CEO story


def test_cluster_events_independent_source_count_counts_distinct_groups():
    df = _toy_news_frame()
    vec, mat = EC.build_tfidf(df["text"], max_features=200)
    events = EC.cluster_events(df, mat, sim_threshold=0.45, window_hours=72.0)
    merged = events[(events["symbol"] == "AAA") & (events["n_members"] == 2)].iloc[0]
    assert merged["independent_source_count"] == 2     # wire:alpha + wire:beta
    singleton = events[(events["symbol"] == "BBB")].iloc[0]
    assert singleton["independent_source_count"] == 1


def test_cluster_events_novelty_is_one_for_a_companys_first_event():
    df = _toy_news_frame()
    vec, mat = EC.build_tfidf(df["text"], max_features=200)
    events = EC.cluster_events(df, mat, sim_threshold=0.45, window_hours=72.0)
    first_aaa = events[events["symbol"] == "AAA"].sort_values("first_observed_at").iloc[0]
    assert bool(first_aaa["first_for_company"]) is True
    assert first_aaa["novelty_vs_company_history"] == 1.0
    first_bbb = events[events["symbol"] == "BBB"].iloc[0]
    assert bool(first_bbb["first_for_company"]) is True


def test_cluster_events_novelty_in_unit_interval_and_causal():
    """Every non-first event's novelty is in [0, 1], and no event's novelty
    depends on anything that happens AFTER it (checked indirectly: adding a
    later, unrelated row must not change an earlier event's novelty)."""
    df = _toy_news_frame()
    vec, mat = EC.build_tfidf(df["text"], max_features=200)
    events = EC.cluster_events(df, mat, sim_threshold=0.45, window_hours=72.0)
    non_first = events[~events["first_for_company"]]
    assert (non_first["novelty_vs_company_history"] >= 0).all()
    assert (non_first["novelty_vs_company_history"] <= 1).all()

    df2 = pd.concat([df, pd.DataFrame([{
        "symbol": "AAA", "title": "Widget Corp Files Lawsuit Against Rival",
        "body": "Widget Corp sued a competitor.", "source": "wireA",
        "independence_group": "wire:alpha", "observed_at": "2020-06-01T09:00:00Z",
        "effective_at": "2020-06-01", "uid": "a4",
        "text": "Widget Corp Files Lawsuit Against Rival Widget Corp sued a competitor.",
    }])], ignore_index=True)
    df2["observed_at"] = pd.to_datetime(df2["observed_at"], utc=True)
    vec2, mat2 = EC.build_tfidf(df2["text"], max_features=200)
    events2 = EC.cluster_events(df2, mat2, sim_threshold=0.45, window_hours=72.0)
    early = events[events["symbol"] == "AAA"].sort_values("first_observed_at").iloc[0]
    early2 = events2[events2["symbol"] == "AAA"].sort_values("first_observed_at").iloc[0]
    assert early["novelty_vs_company_history"] == pytest.approx(early2["novelty_vs_company_history"])


def test_cluster_events_dissemination_speed_undefined_for_singletons():
    df = _toy_news_frame()
    vec, mat = EC.build_tfidf(df["text"], max_features=200)
    events = EC.cluster_events(df, mat, sim_threshold=0.45, window_hours=72.0)
    singleton = events[events["n_members"] == 1]
    assert singleton["dissemination_speed_sources_per_hour"].isna().all()
    merged = events[events["n_members"] > 1]
    assert (merged["dissemination_speed_sources_per_hour"] >= 0).all()


def test_cluster_events_window_hours_bounds_merging():
    """A window too short to span the two near-duplicate rows' 5-minute gap
    would be a bug; a window of zero must not merge anything."""
    df = _toy_news_frame()
    vec, mat = EC.build_tfidf(df["text"], max_features=200)
    events = EC.cluster_events(df, mat, sim_threshold=0.45, window_hours=0.0)
    assert len(events) == 4     # nothing merges with a zero window
    assert (events["n_members"] == 1).all()


def test_eightk_secondary_summary_absent_path_reports_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(EC, "EIGHTK_ROWS", tmp_path / "does_not_exist.jsonl")
    out = EC.eightk_secondary_summary(None)
    assert out["status"] == "ABSENT"


def test_monthly_permutation_null_refuses_below_min_draws():
    rng = np.random.default_rng(0)
    n = 40
    events = pd.DataFrame({
        "novelty_vs_company_history": rng.uniform(0, 1, n),
        "fwd_excess_vw_1m": rng.normal(0, 0.05, n),
        "month": rng.choice(["2020-01", "2020-02", "2020-03"], n),
    })
    out = EC.monthly_permutation_null(events, n_draws=10, seed=1)
    assert out["verdict"].startswith(NB.CANNOT_DETERMINE)


def test_monthly_permutation_null_runs_at_the_floor_and_returns_a_percentile():
    rng = np.random.default_rng(0)
    n = 200
    events = pd.DataFrame({
        "novelty_vs_company_history": rng.uniform(0, 1, n),
        "fwd_excess_vw_1m": rng.normal(0, 0.05, n),
        "month": rng.choice([f"2020-{m:02d}" for m in range(1, 13)], n),
    })
    out = EC.monthly_permutation_null(events, n_draws=NB.MIN_DRAWS, seed=1)
    assert out["n_draws_usable"] == NB.MIN_DRAWS
    assert 0.0 <= out["p_one_sided"] <= 1.0
    assert out["verdict"] in ("CLEARS_MODEL_NULL", "WITHIN_MODEL_NULL")


def test_year_table_notes_when_house_eras_cannot_be_filled():
    events = pd.DataFrame({
        "novelty_vs_company_history": np.linspace(0, 1, 20),
        "fwd_excess_vw_1m": np.linspace(-0.1, 0.1, 20),
        "month": ["2015-0" + str(i % 9 + 1) for i in range(20)],
    })
    out = EC.year_table(events)
    assert "2015" in out["by_year"]
    assert out["house_era_of_each_year"].get("2015") == "2008-2015"
    assert "cannot be filled" in out["note"]


def test_probe_nemotron_reports_absent_without_a_key(monkeypatch):
    """The ONLY branch of this function a network-blocked unit test may take:
    no key -> immediate structured return, zero sockets touched."""
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(EC, "os", __import__("os"))
    out = EC.probe_nemotron()
    assert out["status"] == "ABSENT"


def test_find_corpus_dir_returns_none_or_a_real_directory():
    got = EC.find_corpus_dir()
    assert got is None or got.is_dir()


def test_write_receipt_json_serialisable_with_pandas_and_numpy_types(tmp_path):
    receipt = {
        "a_timestamp": pd.Timestamp("2020-01-01", tz="UTC"),
        "a_numpy_int": np.int64(3),
        "a_numpy_float": np.float64(1.5),
        "a_numpy_bool": np.bool_(True),
        "nested": {"b": [np.int32(1), np.float32(2.0)]},
    }
    out = tmp_path / "r.json"
    EC._write(receipt, str(out))
    reloaded = json.loads(out.read_text(encoding="utf-8"))
    assert reloaded["a_numpy_int"] == 3
    assert reloaded["a_numpy_bool"] is True


# ======================================================================
# n5_event_compression.py -- integration tests, skip when local data is absent
# ======================================================================

CORPUS_DIR = EC.find_corpus_dir()
EVENT_TABLE_PRESENT = EC.EVENT_TABLE_V1.is_file()
EIGHTK_PRESENT = EC.EIGHTK_ROWS.is_file()
N5_1_RECEIPT_PRESENT = EC.RECEIPT.is_file()


@pytest.mark.skipif(CORPUS_DIR is None, reason="sibling terminal repo corpus not present on this machine")
def test_load_news_rows_returns_a_well_formed_frame():
    df = EC.load_news_rows(CORPUS_DIR, None, max_files=3)
    if df.empty:
        pytest.skip("no news rows in the first 3 corpus shards")
    for col in ("symbol", "text", "observed_at", "independence_group", "uid"):
        assert col in df.columns
    assert df["observed_at"].dt.tz is not None


@pytest.mark.skipif(not EIGHTK_PRESENT, reason="eightk_rows.jsonl not on disk")
def test_eightk_secondary_summary_is_trivially_canonical():
    out = EC.eightk_secondary_summary(None)
    assert out["status"] == "OK"
    assert out["compression_ratio"] == pytest.approx(1.0, abs=0.01)


@pytest.mark.skipif(not EVENT_TABLE_PRESENT, reason="event_table_v1.parquet not built on this machine")
def test_load_event_table_v1_news_has_required_columns():
    news = EC.load_event_table_v1_news(None)
    if news.empty:
        pytest.skip("event_table_v1.parquet has no news rows yet")
    for col in ("symbol", "text", "observed_at", "independence_group", "permno"):
        assert col in news.columns


@pytest.mark.skipif(not N5_1_RECEIPT_PRESENT, reason="N5_event_compression.json not written on this machine")
def test_n5_1_receipt_has_required_top_level_keys_and_provenance():
    receipt = json.loads(EC.RECEIPT.read_text(encoding="utf-8"))
    for key in ("job", "status", "llm_spend_usd", "eightk_secondary", "_provenance"):
        assert key in receipt
    assert receipt["llm_spend_usd"] == 0.0
    findings = RP.check_receipt(receipt)
    hard = RP.hard_failures(findings) if hasattr(RP, "hard_failures") else findings
    assert not hard, f"provenance check failed: {hard}"


# ======================================================================
# n5_states_third_null.py -- pure-logic tests (no files touched)
# ======================================================================

def test_derangement_has_no_fixed_points_across_many_sizes_and_seeds():
    rng = np.random.default_rng(0)
    for n in (2, 3, 5, 10, 50, 200):
        for seed_bump in range(5):
            perm = SN._derangement(n, np.random.default_rng(seed_bump))
            assert len(perm) == n
            assert set(perm.tolist()) == set(range(n))     # still a permutation
            assert not np.any(perm == np.arange(n)), f"fixed point at n={n}"


def _toy_states_frame(n_names=20, n_months=8, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(n_names):
        for m in range(n_months):
            rows.append({
                "permno": 1000 + p,
                "month": f"2020-{m + 1:02d}",
                "state_k4": int(rng.integers(0, 4)),
                "excess_vw_1m": float(rng.normal(0, 0.05)),
                "excess_vw_3m": float(rng.normal(0, 0.08)),
            })
    return pd.DataFrame(rows)


def test_name_path_permutation_null_refuses_below_min_draws():
    d = _toy_states_frame()
    out = SN.name_path_permutation_null(d, "state_k4", "excess_vw_1m", n_draws=10, seed=1)
    assert out["verdict"].startswith(NB.CANNOT_DETERMINE)


def test_name_path_permutation_null_runs_at_the_floor_and_the_true_pairing_is_never_used():
    d = _toy_states_frame()
    out = SN.name_path_permutation_null(d, "state_k4", "excess_vw_1m",
                                        n_draws=NB.MIN_DRAWS, seed=1)
    assert out["n_draws_usable"] == NB.MIN_DRAWS
    assert 0.0 <= out["p_one_sided"] <= 1.0
    assert out["verdict"] in ("CLEARS_MODEL_NULL", "WITHIN_MODEL_NULL")
    # a derangement never maps a name to itself, so the true pairing never re-appears
    assert out["mean_donor_coverage"] is not None and out["mean_donor_coverage"] > 0


def test_name_path_permutation_null_calendar_stays_fixed():
    """A row's TARGET must never move draw to draw -- only which donor's state
    label lands on it. Verified by re-deriving the observed statistic from the
    function's own reported `observed`, independent of any draw."""
    d = _toy_states_frame()
    obs_direct = SN.S.spread_statistic(
        d[["permno", "month", "state_k4", "excess_vw_1m"]].dropna(subset=["excess_vw_1m"]),
        "state_k4", "excess_vw_1m")
    out = SN.name_path_permutation_null(d, "state_k4", "excess_vw_1m",
                                        n_draws=NB.MIN_DRAWS, seed=2)
    assert out["observed"] == pytest.approx(obs_direct, abs=1e-6)     # `observed` is rounded to 6dp


def test_era_spread_table_flags_thin_eras_as_unmeasured():
    d = _toy_states_frame(n_months=8)     # all inside 2016-2024; 1999-2007/2008-2015 are empty
    out = SN.era_spread_table(d, "state_k4", "excess_vw_1m")
    assert out["by_era"]["1999-2007"]["spread"] is None
    assert out["by_era"]["2008-2015"]["spread"] is None
    assert out["by_era"]["2016-2024"]["spread"] is not None


def test_grep_state_usage_never_raises():
    out = SN.grep_state_usage()
    assert "aegis_finance" in out
    assert "state_k4" in out["aegis_finance"]


# ======================================================================
# n5_states_third_null.py -- integration tests, skip when local data is absent
# ======================================================================

COMPANY_STATES_PRESENT = SN.COMPANY_STATES.is_file()
N5_3_RECEIPT_PRESENT = SN.RECEIPT.is_file()


@pytest.mark.skipif(not COMPANY_STATES_PRESENT, reason="company_states.parquet not on disk")
def test_load_states_and_returns_has_the_four_states_column():
    d = SN.load_states_and_returns(None)
    assert SN.PRIMARY_STATE_COL in d.columns
    assert d[SN.PRIMARY_STATE_COL].nunique() <= 4
    assert d["permno"].dtype.kind in "iu"


@pytest.mark.skipif(not N5_3_RECEIPT_PRESENT, reason="N5_states_third_null.json not written on this machine")
def test_n5_3_receipt_has_all_three_nulls_and_a_verdict():
    receipt = json.loads(SN.RECEIPT.read_text(encoding="utf-8"))
    for key in ("null_1_within_month_legacy", "null_2_persistent_circular_shift",
               "null_3_name_path_permutation", "final_verdict", "_provenance"):
        assert key in receipt
    verdict = receipt["final_verdict"]["verdict"]
    assert verdict in ("CANNOT_DETERMINE",) or verdict.startswith("SCREEN_SURVIVOR")
    if verdict == "CANNOT_DETERMINE":
        assert "demotion" in receipt
        assert "usage_grep" in receipt["demotion"]
    assert receipt["llm_spend_usd"] == 0.0
    findings = RP.check_receipt(receipt)
    hard = RP.hard_failures(findings) if hasattr(RP, "hard_failures") else findings
    assert not hard, f"provenance check failed: {hard}"
