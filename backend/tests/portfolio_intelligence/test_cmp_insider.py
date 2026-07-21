"""
Offline tests for TRIAL-CMP-INSIDER-IC: the CMP classifier mirror, the
panel-union-live score, the anti-false-zero staleness guard, and the forward
collector (stub fetch + stub artifact — no network, no bundled-artifact
dependency).
"""

import pytest

from backend.db import get_connection, get_series_observable, init_db
from backend.services.cmp_insider import (
    classify_buy, compute_cmp_insider_score,
)
from backend.services.insider_form4 import parse_form4_open_market_buys
from backend.services.portfolio_intelligence.cmp_insider_collector import (
    KEY_PREFIX, collect_cmp_insider_scores,
)

# Artifact fixture: insider 100 = classifiable, June-routine; 200 = classifiable
# opportunistic; 300 absent (unclassifiable). Panel ends 2026-03-31.
ARTIFACT = {
    "panel_end": "2026-03-31",
    "history": {
        "100": {"years": [2023, 2024, 2025],
                "year_months": ["2023-06", "2024-06", "2025-06"]},
        "200": {"years": [2023, 2024, 2025],
                "year_months": ["2023-01", "2024-11", "2025-03"]},
    },
    "recent_buys": [
        {"ticker": "AAA", "filing_date": "2026-02-10", "cik": "900"},
    ],
}


class TestClassifyBuy:
    def test_routine_same_month_three_prior_years(self):
        assert classify_buy("100", "2026-06-15", ARTIFACT) == "routine"

    def test_opportunistic_off_pattern_month(self):
        assert classify_buy("100", "2026-07-15", ARTIFACT) == "opportunistic"
        assert classify_buy("200", "2026-06-15", ARTIFACT) == "opportunistic"

    def test_no_three_year_history_unclassifiable(self):
        assert classify_buy("300", "2026-06-15", ARTIFACT) == "unclassifiable"

    def test_leading_zero_cik_normalised(self):
        assert classify_buy("000200", "2026-06-15", ARTIFACT) == "opportunistic"

    def test_malformed_inputs_unclassifiable_not_raise(self):
        assert classify_buy("100", "", ARTIFACT) == "unclassifiable"
        assert classify_buy("100", "junk-date", ARTIFACT) == "unclassifiable"
        assert classify_buy("", "2026-06-15", {}) == "unclassifiable"


def _live_buy(cik, filing_date, trans_date=None):
    return {"name": "X", "cik": cik, "shares": 100, "value": 1000,
            "date": trans_date or filing_date, "filing_date": filing_date, "type": "P"}


class TestScore:
    def test_unions_panel_and_live_distinct_ciks(self):
        buys = [_live_buy("200", "2026-06-01")]
        score, payload = compute_cmp_insider_score("AAA", buys, "2026-07-21", ARTIFACT)
        assert score == 2.0  # panel cik 900 + live cik 200
        assert payload["n_live_opportunistic"] == 1
        assert payload["degraded"] is False

    def test_live_buy_inside_panel_window_not_double_counted(self):
        buys = [_live_buy("900", "2026-02-10")]  # same buy the panel already has
        score, payload = compute_cmp_insider_score("AAA", buys, "2026-07-21", ARTIFACT)
        assert score == 1.0
        assert payload["n_live_opportunistic"] == 0

    def test_routine_and_unclassifiable_live_buyers_dropped(self):
        buys = [_live_buy("100", "2026-06-15"),   # June = routine for cik 100
                _live_buy("300", "2026-06-15")]   # no history
        score, payload = compute_cmp_insider_score("BBB", buys, "2026-07-21", ARTIFACT)
        assert score == 0.0
        assert payload["n_live_routine"] == 1
        assert payload["n_live_unclassifiable"] == 1

    def test_trailing_window_excludes_old_panel_buys(self):
        score, _ = compute_cmp_insider_score("AAA", [], "2027-06-01", ARTIFACT)
        assert score == 0.0  # panel buy 2026-02-10 outside trailing 365d

    def test_stale_artifact_flags_degraded_not_silent_zero(self):
        _, payload = compute_cmp_insider_score("AAA", [], "2026-12-01", ARTIFACT)
        assert payload["degraded"] is True  # 245d gap > 210d guard

    def test_empty_artifact_degraded(self):
        score, payload = compute_cmp_insider_score("AAA", [], "2026-07-21", {})
        assert score == 0.0 and payload["degraded"] is True


class TestParserCikExtraction:
    XML = """<?xml version="1.0"?>
    <ownershipDocument>
      <reportingOwner><reportingOwnerId>
        <rptOwnerCik>0001234567</rptOwnerCik><rptOwnerName>DOE JANE</rptOwnerName>
      </reportingOwnerId></reportingOwner>
      <nonDerivativeTable><nonDerivativeTransaction>
        <transactionDate><value>2026-06-15</value></transactionDate>
        <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
        <transactionAmounts>
          <transactionShares><value>1000</value></transactionShares>
          <transactionPricePerShare><value>12.5</value></transactionPricePerShare>
          <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
        </transactionAmounts>
      </nonDerivativeTransaction></nonDerivativeTable>
    </ownershipDocument>"""

    def test_cik_extracted_without_leading_zeros(self):
        buys = parse_form4_open_market_buys(self.XML)
        assert len(buys) == 1
        assert buys[0]["cik"] == "1234567"  # matches bulk-file RPTOWNERCIK form


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "cmp.db"
    init_db(p)
    return p


def _fetch_stub(buys_by_ticker):
    def _f(ticker):
        return {"ticker": ticker, "buys": buys_by_ticker.get(ticker, [])}
    return _f


class TestCollector:
    def test_writes_pit_rows_with_cmp_payload(self, db_path):
        fetch = _fetch_stub({"AAA": [_live_buy("200", "2026-06-01")]})
        res = collect_cmp_insider_scores(db_path=db_path, tickers=["AAA", "BBB"],
                                         fetch=fetch, artifact=ARTIFACT,
                                         as_of="2026-07-21")
        assert res["status"] == "collected"
        assert res["scores"]["AAA"] == 2.0  # panel 900 + live 200
        assert res["scores"]["BBB"] == 0.0
        conn = get_connection(db_path)
        try:
            series = get_series_observable(conn, KEY_PREFIX + "AAA")
        finally:
            conn.close()
        assert len(series) == 1
        assert series[0]["source"] == "sec_form4_cmp"

    def test_throttles_within_window(self, db_path):
        fetch = _fetch_stub({})
        collect_cmp_insider_scores(db_path=db_path, tickers=["AAA"], fetch=fetch,
                                   artifact=ARTIFACT, as_of="2026-07-21")
        res = collect_cmp_insider_scores(db_path=db_path, tickers=["AAA"],
                                         fetch=fetch, artifact=ARTIFACT,
                                         as_of="2026-07-23")
        assert res["status"] == "throttled"

    def test_fetch_failure_isolated_to_zero_score(self, db_path):
        def _boom(ticker):
            raise RuntimeError("SEC down")
        res = collect_cmp_insider_scores(db_path=db_path, tickers=["AAA"],
                                         fetch=_boom, artifact=ARTIFACT,
                                         as_of="2026-07-21")
        assert res["status"] == "collected"
        assert res["scores"]["AAA"] == 0.0


class TestArtifactContract:
    def test_malformed_artifact_degrades_loudly(self, tmp_path):
        import gzip, json
        from backend.services.cmp_insider import load_artifact
        p = tmp_path / "bad.json.gz"
        with gzip.open(p, "wt", encoding="utf-8") as f:
            json.dump({"panel_end": "2026-03-31", "insiders": {}}, f)  # renamed key
        load_artifact.cache_clear()
        try:
            assert load_artifact(str(p)) == {}  # -> every score flags degraded
        finally:
            load_artifact.cache_clear()

    def test_missing_file_degrades_not_raises(self, tmp_path):
        from backend.services.cmp_insider import load_artifact
        load_artifact.cache_clear()
        try:
            assert load_artifact(str(tmp_path / "absent.json.gz")) == {}
        finally:
            load_artifact.cache_clear()

    def test_real_bundled_artifact_passes_contract(self):
        from backend.services.cmp_insider import load_artifact
        load_artifact.cache_clear()
        art = load_artifact()
        assert art.get("panel_end") and art.get("history") and art.get("recent_buys")
