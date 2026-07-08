"""
Fragility candidate collectors (Branch 1 item 3) — offline tests.

The invariants that matter:
- candidates are snapshotted into the PIT store under fragility_candidate:*,
  weekly-throttled, per-candidate failure isolated;
- an errored candidate reads back as not_collected, never as a real 0;
- NOTHING here touches compute_fragility_index's composite (grep-guard).
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.db import get_connection, init_db
from backend.services.portfolio_intelligence import fragility_candidates as fc


@pytest.fixture()
def db(tmp_path):
    p = tmp_path / "pit.db"
    init_db(p)
    return p


def _patch_all(monkeypatch, ipo=42.0, conc=0.05, narr=1.3):
    monkeypatch.setitem(fc._CANDIDATES, "ipo_issuance",
                        lambda: (ipo, {"s1_count": 30, "424b4_count": 12}))
    monkeypatch.setitem(fc._CANDIDATES, "mega_cap_concentration",
                        lambda: (conc, {"spy_return": 0.12, "rsp_return": 0.07}))
    monkeypatch.setitem(fc._CANDIDATES, "crash_narrative",
                        lambda: (narr, {"avg_tone": -2.1}))


class TestCollector:
    def test_collects_all_three_into_pit(self, db, monkeypatch):
        _patch_all(monkeypatch)
        out = fc.collect_fragility_candidates(db_path=db, as_of="2026-07-08")
        assert out["status"] == "collected"
        assert out["n"] == 3 and out["written"] == 3
        conn = get_connection(db)
        try:
            rows = conn.execute(
                "SELECT key, value FROM pit_observations WHERE key LIKE 'fragility_candidate:%'"
            ).fetchall()
        finally:
            conn.close()
        got = {r["key"]: r["value"] for r in rows}
        assert got["fragility_candidate:ipo_issuance"] == 42.0
        assert got["fragility_candidate:mega_cap_concentration"] == pytest.approx(0.05)
        assert got["fragility_candidate:crash_narrative"] == pytest.approx(1.3)

    def test_weekly_throttle(self, db, monkeypatch):
        _patch_all(monkeypatch)
        fc.collect_fragility_candidates(db_path=db, as_of="2026-07-08")
        out = fc.collect_fragility_candidates(db_path=db, as_of="2026-07-10")
        assert out["status"] == "throttled"

    def test_one_failure_does_not_break_the_rest(self, db, monkeypatch):
        _patch_all(monkeypatch)
        def _boom():
            raise RuntimeError("EDGAR down")
        monkeypatch.setitem(fc._CANDIDATES, "ipo_issuance", _boom)
        out = fc.collect_fragility_candidates(db_path=db, as_of="2026-07-08")
        assert out["status"] == "collected"
        assert out["scores"]["mega_cap_concentration"] == pytest.approx(0.05)
        assert out["scores"]["ipo_issuance"] == 0.0  # error row, flagged in payload


class TestReader:
    def test_reads_back_collected_values(self, db, monkeypatch):
        _patch_all(monkeypatch)
        fc.collect_fragility_candidates(db_path=db, as_of="2026-07-08")
        r = fc.latest_candidate_readings(db_path=db)
        assert r["ipo_issuance"]["status"] == "collected"
        assert r["ipo_issuance"]["value"] == 42.0
        assert "NOT in the fragility" in r["ipo_issuance"]["label"]

    def test_error_row_reads_as_not_collected_never_zero(self, db, monkeypatch):
        """The T9 false-zero lesson: an errored run must not read as a real 0."""
        _patch_all(monkeypatch)
        def _boom():
            raise RuntimeError("GDELT down")
        monkeypatch.setitem(fc._CANDIDATES, "crash_narrative", _boom)
        fc.collect_fragility_candidates(db_path=db, as_of="2026-07-08")
        r = fc.latest_candidate_readings(db_path=db)
        assert r["crash_narrative"]["status"] == "not_collected"
        assert r["crash_narrative"]["value"] is None

    def test_empty_store_reports_not_collected(self, db):
        r = fc.latest_candidate_readings(db_path=db)
        assert all(v["status"] == "not_collected" for v in r.values())


class TestComputeFunctions:
    def test_ipo_issuance_sums_form_counts(self, monkeypatch):
        monkeypatch.setattr(fc, "_edgar_form_count",
                            lambda form, s, e: {"S-1": 30, "424B4": 12}[form])
        v, payload = fc.compute_ipo_issuance(as_of="2026-07-08")
        assert v == 42.0
        assert payload["s1_count"] == 30 and payload["424b4_count"] == 12

    def test_crash_narrative_raises_on_gdelt_failure(self):
        with patch("backend.services.news_intelligence.fetch_gdelt_signals",
                   return_value={"success": False, "reason": "timeout"}):
            with pytest.raises(ValueError, match="GDELT unavailable"):
                fc.compute_crash_narrative()

    def test_crash_narrative_returns_volume_zscore(self):
        with patch("backend.services.news_intelligence.fetch_gdelt_signals",
                   return_value={"success": True, "volume_zscore": 2.4,
                                 "avg_tone": -3.0, "tone_trend": -0.5}):
            v, payload = fc.compute_crash_narrative()
        assert v == pytest.approx(2.4)
        assert payload["avg_tone"] == -3.0


def test_composite_decision_path_never_imports_candidates():
    """Grep-guard (same discipline as the fragility never-arm pin): the composite
    and the lane decision path must not reference the candidate module — the
    TRIAL-CRASH metric stays byte-identical to its pre-registration."""
    base = Path(__file__).resolve().parents[3] / "backend" / "services" / "portfolio_intelligence"
    for fname in ("fragility.py", "rules.py", "reference_engine.py", "book_management.py"):
        text = (base / fname).read_text(encoding="utf-8", errors="replace")
        assert "fragility_candidates" not in text, (
            f"{fname} references fragility_candidates — candidates must not "
            f"reach the composite or any decision path without a registered trial"
        )
