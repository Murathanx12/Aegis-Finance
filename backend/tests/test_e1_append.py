"""N-C — the nightly append: label sources only, PIT re-verify, or refuse.

Synthetic corpus + synthetic bars, entirely offline.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

from scripts import night_e1_news_return_panel as e1  # noqa: E402


def _bars(tmp_path, symbols=("NVDA", "SPY"), n=40):
    """n consecutive weekday sessions ending YESTERDAY, so entry days exist."""
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days = sorted(days)
    rows = []
    for sym in symbols:
        for i, day in enumerate(days):
            rows.append({
                "symbol": sym, "date": pd.Timestamp(day),
                "open": 100.0 + i, "close": 101.0 + i,
                "high": 102.0 + i, "low": 99.0 + i,
                # A rising volume ramp makes an off-by-one in pit_dv_21 visible.
                "volume": 1_000_000 + 10_000 * i,
            })
    p = tmp_path / "optimus" / "prices_2025_26"
    p.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p / "bars.parquet", index=False)
    return days


def _corpus(tmp_path, source: str, rows: list[dict]):
    d = tmp_path / "optimus" / "news_corpus" / source
    d.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).date().isoformat()
    with (d / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _row(raw_id: str, first_seen: datetime, source="sec_edgar_8k_current_atom", tickers=("NVDA",)):
    return {
        "source": source, "first_seen_utc": first_seen.isoformat(timespec="seconds"),
        "published_utc": (first_seen - timedelta(hours=1)).isoformat(timespec="seconds"),
        "tz_source": "UTC", "url": f"https://example.invalid/{raw_id}",
        "title": "Kroger beats on same-store sales", "body": "The company raised guidance.",
        "lang": "en", "tickers": list(tickers), "entity_tags": ["8-K:2.02"],
        "raw_id": raw_id, "pit_grade": "native_stamp",
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(e1, "_data_root", lambda: tmp_path / "optimus")
    import scripts.news_pull as np_
    monkeypatch.setattr(np_._config, "DATA_DIR", tmp_path, raising=False)
    return tmp_path


def test_a_labelled_row_is_appended_with_its_pit_dv(env):
    days = _bars(env)
    entry = days[-5]
    # 08:00 ET on the entry day, i.e. before the bell -> that day IS the entry.
    seen = datetime(entry.year, entry.month, entry.day, 12, 0, tzinfo=timezone.utc)
    _corpus(env, "sec_edgar_8k_current_atom", [_row("acc-1", seen)])

    rec = e1.E1_append()
    assert rec["verdict"] == "APPENDED", rec["headline"]
    assert rec["rows_appended"] == 1
    assert rec["pit_violations"] == 0

    df = pd.read_parquet(env / "optimus" / "text_return_panel" / "news_returns_2025_26.parquet")
    row = df.iloc[0]
    assert row["symbol"] == "NVDA"
    assert row["entry_date"] == entry.isoformat()
    assert row["first_seen_utc"] == seen.isoformat(timespec="seconds")
    assert pd.notna(row["pit_dv_21"])
    assert row["pit_dv_21"] < row["dollar_vol"], (
        "volume ramps upward, so a pit_dv_21 that included the entry session "
        "would sit at or above it — this is the off-by-one check"
    )


def test_index_state_sources_are_never_read(env):
    """Invariant 20: a Google News row may not label a return."""
    days = _bars(env)
    entry = days[-5]
    seen = datetime(entry.year, entry.month, entry.day, 12, 0, tzinfo=timezone.utc)
    _corpus(env, "google_news_rss_en_hk",
            [_row("gn-1", seen, source="google_news_rss_en_hk")])

    rec = e1.E1_append()
    assert rec["rows_appended"] == 0
    assert "google_news_rss_en_hk" not in rec["label_sources"]
    assert "google_news_rss_en_hk" in rec["skipped_index_state_sources"]
    assert rec["funnel"]["corpus_rows"] == 0, "the row was never even read"


def test_a_row_pulled_tonight_is_pending_not_dropped(env):
    """The normal outcome of a fresh pull, and it must not read as a breakage."""
    _bars(env)
    seen = datetime.now(timezone.utc) + timedelta(days=3)  # past the last session
    _corpus(env, "sec_edgar_8k_current_atom", [_row("acc-future", seen)])

    rec = e1.E1_append()
    assert rec["rows_appended"] == 0
    assert rec["funnel"]["pending_future_session"] == 1
    assert rec["verdict"] == "PENDING"
    assert "awaiting a session that has not happened yet" in rec["headline"]


def test_a_pit_violation_refuses_the_whole_append(env, monkeypatch):
    days = _bars(env)
    entry = days[-5]
    seen = datetime(entry.year, entry.month, entry.day, 12, 0, tzinfo=timezone.utc)
    _corpus(env, "sec_edgar_8k_current_atom", [_row("acc-1", seen), _row("acc-2", seen)])

    real = e1._entry_session

    def poisoned(observed_at, effective_at, sessions):
        """One row labelled at a session BEFORE it was seen — the look-ahead."""
        day, pos = real(observed_at, effective_at, sessions)
        return pd.Timestamp(days[-20]), pos

    monkeypatch.setattr(e1, "_entry_session", poisoned)
    rec = e1.E1_append()
    assert rec["verdict"] == "REFUSED"
    assert rec["pit_violations"] >= 1
    assert rec["rows_appended"] == 0
    assert not (env / "optimus" / "text_return_panel" / "news_returns_2025_26.parquet").exists(), \
        "a refused append must write NOTHING"
    assert "do NOT relax the check" in rec["next_test"]


def test_a_native_stamp_backfill_anchors_on_its_own_published_stamp(env):
    """Found on the live Alpaca backfill, 2026-09-11.

    The backfill starts at 2015-01-01, so every one of its rows carries
    `first_seen_utc = today`. Anchoring those on first_seen would date 2015
    news to tomorrow's open — not conservative, nonsense. `native_stamp` means
    the provider's own stamp is trustworthy, so it is the anchor.
    """
    days = _bars(env)
    entry = days[-5]
    published = datetime(entry.year, entry.month, entry.day, 12, 0, tzinfo=timezone.utc)
    row = _row("acc-backfill", datetime.now(timezone.utc))   # seen TODAY
    row["published_utc"] = published.isoformat(timespec="seconds")
    row["pit_grade"] = "native_stamp"
    _corpus(env, "sec_edgar_8k_current_atom", [row])

    rec = e1.E1_append()
    assert rec["rows_appended"] == 1, rec["headline"]
    assert rec["anchors_used"]["published_utc"] == 1
    df = pd.read_parquet(env / "optimus" / "text_return_panel" / "news_returns_2025_26.parquet")
    assert df.iloc[0]["entry_date"] == entry.isoformat()
    assert df.iloc[0]["pit_anchor_field"] == "published_utc"


def test_a_first_seen_only_row_still_anchors_on_our_own_stamp(env):
    """GDELT's `seendate` is a crawl time it may move; ours is not."""
    days = _bars(env)
    entry = days[-5]
    seen = datetime(entry.year, entry.month, entry.day, 12, 0, tzinfo=timezone.utc)
    row = _row("gdelt-1", seen, source="gdelt_doc_v2")
    row["published_utc"] = "2015-01-01T00:00:00+00:00"   # the provider's, not ours
    row["pit_grade"] = "first_seen_only"
    _corpus(env, "gdelt_doc_v2", [row])

    rec = e1.E1_append()
    assert rec["rows_appended"] == 1
    assert rec["anchors_used"]["first_seen_utc"] == 1
    df = pd.read_parquet(env / "optimus" / "text_return_panel" / "news_returns_2025_26.parquet")
    assert df.iloc[0]["entry_date"] == entry.isoformat(), \
        "the 2015 provider stamp must NOT have been used"


def test_a_publication_before_the_calendar_is_off_calendar_not_session_zero(env):
    """The ten-year look-ahead the backfill would have produced.

    `_entry_session` used `searchsorted`, which clamps a date before the first
    session to index 0 — so a 2015 headline with 2025-26 bars was labelled at
    the first 2025 session and counted as `kept`.
    """
    days = _bars(env)
    row = _row("acc-ancient", datetime.now(timezone.utc))
    row["published_utc"] = "2015-01-05T13:00:00+00:00"
    row["pit_grade"] = "native_stamp"
    _corpus(env, "sec_edgar_8k_current_atom", [row])

    rec = e1.E1_append()
    assert rec["rows_appended"] == 0, "a 2015 row must not be labelled on a 2026 bar"
    assert rec["funnel"]["pending_future_session"] == 1

    # ...and the primitive itself, stated directly.
    import numpy as np
    sessions = np.sort(np.array([pd.Timestamp(d) for d in days], dtype="datetime64[ns]"))
    assert e1._entry_session("2015-01-05T13:00:00+00:00", "", sessions) == (None, None)


def test_the_watermark_stops_a_second_append_from_duplicating(env):
    days = _bars(env)
    entry = days[-5]
    seen = datetime(entry.year, entry.month, entry.day, 12, 0, tzinfo=timezone.utc)
    _corpus(env, "sec_edgar_8k_current_atom", [_row("acc-1", seen)])

    first = e1.E1_append()
    second = e1.E1_append()
    assert first["rows_appended"] == 1
    assert second["rows_appended"] == 0
    assert second["watermark_first_seen_utc"] == seen.isoformat(timespec="seconds")
    df = pd.read_parquet(env / "optimus" / "text_return_panel" / "news_returns_2025_26.parquet")
    assert len(df) == 1


def test_missing_bars_refuse_with_the_path_named(env):
    _corpus(env, "sec_edgar_8k_current_atom", [_row("acc-1", datetime.now(timezone.utc))])
    rec = e1.E1_append()
    assert rec["verdict"] == "REFUSED"
    assert "bars.parquet" in rec["headline"]
    assert "P6_bars_and_regret" in rec["next_test"]


def test_every_receipt_carries_next_test(env):
    """The planner is starved without it (2026-09-10 §5)."""
    _bars(env)
    rec = e1.E1_append()
    assert rec["next_test"], "a receipt with no next_test starves the planner"
    assert rec["llm_spend_usd"] == 0.0


def test_the_job_is_registered_in_the_night_factory():
    from scripts import night_factory_jobs as jobs
    assert "E1_append" in jobs.JOBS
    assert callable(jobs.JOBS["E1_append"])
