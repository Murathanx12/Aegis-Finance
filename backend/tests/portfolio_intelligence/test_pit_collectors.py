"""
Tests for the point-in-time collectors (V3 data layer) — Chunk 2.

Fast tests mock the EDGAR HTTP layer (the fast suite is network-blocked). One
slow test hits live EDGAR to verify the real path + tracked CIKs.
"""

import time

import pytest

from backend.db import get_connection, get_latest_observable, get_revisions, init_db
from backend.services import edgar_events, pit_collectors
from backend.services.edgar_events import _RateLimiter


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test_pit_collectors.db"
    init_db(path)
    return path


@pytest.fixture
def conn(db_path):
    c = get_connection(db_path)
    yield c
    c.close()


def _subs(rows):
    """Build a synthetic EDGAR submissions dict.
    rows: list of (form, accession, filing_date, report_date, primary_doc)."""
    return {
        "filings": {
            "recent": {
                "form": [r[0] for r in rows],
                "accessionNumber": [r[1] for r in rows],
                "filingDate": [r[2] for r in rows],
                "reportDate": [r[3] for r in rows],
                "primaryDocument": [r[4] for r in rows],
            }
        }
    }


_BRK = _subs([
    ("8-K", "0000-24-1", "2026-05-01", "", "8k.htm"),
    ("13F-HR", "0000-24-2", "2026-05-15", "2026-03-31", "form13f.xml"),  # latest 13F
    ("13F-HR", "0000-24-0", "2026-02-14", "2025-12-31", "form13f.xml"),  # older 13F
])


# ── latest_13f_filing ────────────────────────────────────────────────────────


class TestLatest13F:
    def test_picks_most_recent_13f(self, monkeypatch):
        monkeypatch.setattr(edgar_events, "_fetch_submissions", lambda cik: _BRK)
        f = pit_collectors.latest_13f_filing(1067983)
        assert f is not None
        assert f["filing_date"] == "2026-05-15"
        assert f["report_date"] == "2026-03-31"
        assert f["form"] == "13F-HR"
        assert "form13f.xml" in f["primary_doc_url"]

    def test_none_when_no_13f(self, monkeypatch):
        only_8k = _subs([("8-K", "x", "2026-05-01", "", "8k.htm")])
        monkeypatch.setattr(edgar_events, "_fetch_submissions", lambda cik: only_8k)
        assert pit_collectors.latest_13f_filing(1) is None

    def test_none_when_fetch_empty(self, monkeypatch):
        monkeypatch.setattr(edgar_events, "_fetch_submissions", lambda cik: None)
        assert pit_collectors.latest_13f_filing(1) is None


# ── collect_institution_13f → PIT store ──────────────────────────────────────


class TestCollectInstitution:
    def test_writes_with_lag_captured(self, conn, monkeypatch):
        monkeypatch.setattr(edgar_events, "_fetch_submissions", lambda cik: _BRK)
        rid = pit_collectors.collect_institution_13f(conn, "Berkshire", 1067983)
        assert rid is not None
        revs = get_revisions(conn, "13f:1067983:filing", "2026-03-31")
        assert len(revs) == 1
        row = revs[0]
        # as_of = report period (Q1), observed_at = filing date — the 45-day lag.
        assert row["as_of"] == "2026-03-31"
        assert row["observed_at"] == "2026-05-15"
        assert row["source"] == "edgar"
        assert row["payload"]["institution"] == "Berkshire"
        assert row["payload"]["accession"] == "0000-24-2"

    def test_idempotent_second_run_is_noop(self, conn, monkeypatch):
        monkeypatch.setattr(edgar_events, "_fetch_submissions", lambda cik: _BRK)
        first = pit_collectors.collect_institution_13f(conn, "Berkshire", 1067983)
        second = pit_collectors.collect_institution_13f(conn, "Berkshire", 1067983)
        assert first is not None
        assert second is None  # unchanged filing → no duplicate row

    def test_leak_free_after_collect(self, conn, monkeypatch):
        monkeypatch.setattr(edgar_events, "_fetch_submissions", lambda cik: _BRK)
        pit_collectors.collect_institution_13f(conn, "Berkshire", 1067983)
        # Before the filing was public (2026-05-15) we could not have known it.
        assert get_latest_observable(conn, "13f:1067983:filing", "2026-04-01") is None
        seen = get_latest_observable(conn, "13f:1067983:filing", "2026-06-01")
        assert seen is not None and seen["as_of"] == "2026-03-31"


# ── collect_all_13f isolation ────────────────────────────────────────────────


class TestCollectAll:
    def test_one_failure_does_not_abort_batch(self, conn, monkeypatch):
        def fake(cik):
            if cik == 999:
                raise RuntimeError("EDGAR 503")
            return _BRK
        monkeypatch.setattr(edgar_events, "_fetch_submissions", fake)
        result = pit_collectors.collect_all_13f(
            conn, {"Good": 1067983, "Bad": 999}
        )
        assert result["recorded"] == ["Good"]
        assert len(result["errors"]) == 1
        assert result["errors"][0]["institution"] == "Bad"

    def test_unchanged_on_rerun(self, conn, monkeypatch):
        monkeypatch.setattr(edgar_events, "_fetch_submissions", lambda cik: _BRK)
        pit_collectors.collect_all_13f(conn, {"BRK": 1067983})
        result = pit_collectors.collect_all_13f(conn, {"BRK": 1067983})
        assert result["unchanged"] == ["BRK"]
        assert result["recorded"] == []


# ── Rate limiter ─────────────────────────────────────────────────────────────


class TestRateLimiter:
    def test_enforces_min_interval(self):
        # 100ms spacing — well above Windows' ~16ms timer quantization so the
        # measured elapsed is a reliable lower bound.
        rl = _RateLimiter(max_per_sec=10.0)
        rl.wait()  # first call: no wait
        t0 = time.monotonic()
        rl.wait()  # second call must be spaced ≥ ~100ms
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.07  # generous slack for timer granularity

    def test_first_call_does_not_block(self):
        rl = _RateLimiter(max_per_sec=1.0)  # 1s spacing
        t0 = time.monotonic()
        rl.wait()
        assert time.monotonic() - t0 < 0.5  # first call returns immediately


# ── Live integration (verifies real EDGAR path + CIKs) ───────────────────────


@pytest.mark.slow
def test_live_berkshire_13f(tmp_path):
    """Hits live EDGAR. Verifies Berkshire's CIK resolves and a 13F is found with
    a plausible report-before-filing lag."""
    path = tmp_path / "live.db"
    init_db(path)
    c = get_connection(path)
    try:
        rid = pit_collectors.collect_institution_13f(c, "Berkshire Hathaway", 1067983)
        assert rid is not None
        row = get_latest_observable(c, "13f:1067983:filing")
        assert row is not None
        assert row["as_of"] <= row["observed_at"]  # report period precedes filing
    finally:
        c.close()
