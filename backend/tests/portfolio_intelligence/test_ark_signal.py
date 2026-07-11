"""
Offline tests for the ARK holdings collector (TRIAL-ARK-IC): CSV parsing
(fail-loud on drift), the frozen flow score, raw-shares PIT writes, the
score's accrual guard (no false-neutral zeros before the baseline exists),
and all-funds-failed loudness.
"""

import pytest

from backend.db import get_connection, get_series_observable, init_db
from backend.services.ark_holdings import compute_ark_scores, fetch_fund_holdings
from backend.services.portfolio_intelligence.ark_collector import (
    SCORE_PREFIX, SHARES_PREFIX, collect_ark_holdings, ensure_ark_trial,
)


class TestParse:
    def _mock_resp(self, monkeypatch, text: str):
        class _R:
            def __init__(self, t): self.text = t
            def raise_for_status(self): pass
        import backend.services.ark_holdings as ah
        monkeypatch.setattr(ah.requests, "get", lambda *a, **kw: _R(text))

    CSV = ('date,fund,company,ticker,cusip,shares,market value ($),weight (%)\n'
           '07/10/2026,ARKK,TESLA INC,TSLA,88160R101,"1,720,360","$699,412,358.00",10.21%\n'
           '07/10/2026,ARKK,CASH,,,,"$1,000.00",0.1%\n')

    def test_parses_and_excludes_cash(self, monkeypatch):
        self._mock_resp(monkeypatch, self.CSV)
        rows = fetch_fund_holdings("ARKK")
        assert len(rows) == 1
        r = rows[0]
        assert r["ticker"] == "TSLA" and r["shares"] == 1720360.0
        assert r["date"] == "2026-07-10" and r["weight_pct"] == 10.21

    def test_header_drift_raises(self, monkeypatch):
        self._mock_resp(monkeypatch,
                        "day,fund,name,symbol,qty\n07/10/2026,ARKK,X,TSLA,5\n")
        with pytest.raises(ValueError, match="header drift"):
            fetch_fund_holdings("ARKK")

    def test_zero_holdings_raises(self, monkeypatch):
        self._mock_resp(monkeypatch,
                        "date,fund,company,ticker,cusip,shares,market value ($),weight (%)\n")
        with pytest.raises(ValueError, match="zero holdings"):
            fetch_fund_holdings("ARKK")

    def test_unknown_fund_raises(self):
        with pytest.raises(ValueError, match="unknown ARK fund"):
            fetch_fund_holdings("SPY")


class TestScore:
    def test_net_change_clipped_per_fund(self):
        cur = {"ARKK": {"TSLA": 150.0}, "ARKW": {"TSLA": 300.0}}
        base = {"ARKK": {"TSLA": 100.0}, "ARKW": {"TSLA": 100.0}}
        score, payload = compute_ark_scores(cur, base)["TSLA"]
        # ARKK +50% = 0.5; ARKW +200% clips to +1.0
        assert score == pytest.approx(1.5)
        assert payload["n_funds"] == 2

    def test_new_position_and_full_exit(self):
        cur = {"ARKK": {"NEW": 10.0}}
        base = {"ARKK": {"GONE": 10.0}}
        s = compute_ark_scores(cur, base)
        assert s["NEW"][0] == 1.0
        assert s["GONE"][0] == -1.0

    def test_unchanged_is_zero(self):
        cur = {"ARKK": {"TSLA": 100.0}}
        base = {"ARKK": {"TSLA": 100.0}}
        assert compute_ark_scores(cur, base)["TSLA"][0] == 0.0


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "ark.db"
    init_db(p)
    return p


def _fetch_stub(date_iso: str, shares_by_fund: dict):
    def fetch(fund):
        holdings = shares_by_fund.get(fund)
        if holdings is None:
            raise RuntimeError(f"{fund} down")
        return [{"fund": fund, "date": date_iso, "ticker": t,
                 "shares": s, "weight_pct": 1.0} for t, s in holdings.items()]
    return fetch


class TestCollector:
    def test_writes_raw_shares(self, db_path):
        res = collect_ark_holdings(
            db_path=db_path,
            fetch=_fetch_stub("2026-07-10", {"ARKK": {"TSLA": 100.0}}))
        assert res["status"] == "collected"
        assert res["shares_written"] == 1
        assert res["score_status"] == "accruing_baseline"
        conn = get_connection(db_path)
        try:
            series = get_series_observable(conn, SHARES_PREFIX + "ARKK:TSLA")
        finally:
            conn.close()
        assert len(series) == 1 and series[0]["value"] == 100.0

    def test_no_score_before_baseline(self, db_path):
        collect_ark_holdings(
            db_path=db_path,
            fetch=_fetch_stub("2026-07-10", {"ARKK": {"TSLA": 100.0}}))
        conn = get_connection(db_path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM pit_observations WHERE key LIKE ?",
                (SCORE_PREFIX + "%",)).fetchone()["n"]
        finally:
            conn.close()
        assert n == 0

    def test_score_written_after_baseline(self, db_path):
        # 22 sessions of accrual, shares doubling on the last day
        for i in range(22):
            day = f"2026-06-{i + 1:02d}"
            collect_ark_holdings(
                db_path=db_path,
                fetch=_fetch_stub(day, {"ARKK": {"TSLA": 100.0}}))
        res = collect_ark_holdings(
            db_path=db_path,
            fetch=_fetch_stub("2026-06-23", {"ARKK": {"TSLA": 200.0}}))
        assert res["score_status"] == "scored"
        conn = get_connection(db_path)
        try:
            series = get_series_observable(conn, SCORE_PREFIX + "TSLA")
        finally:
            conn.close()
        latest = max(series, key=lambda r: r["as_of"])
        assert latest["as_of"] == "2026-06-23"
        assert latest["value"] == pytest.approx(1.0)  # +100% clips to +1

    def test_single_fund_failure_isolated(self, db_path):
        fetch = _fetch_stub("2026-07-10", {"ARKK": {"TSLA": 100.0}})
        res = collect_ark_holdings(db_path=db_path, fetch=fetch)
        assert res["status"] == "collected"
        assert "ARKW" in res["funds_failed"]

    def test_all_funds_failed_raises(self, db_path):
        def broken(fund):
            raise RuntimeError("ark down")
        with pytest.raises(ValueError, match="ALL funds failed"):
            collect_ark_holdings(db_path=db_path, fetch=broken)


class TestTrialRegistration:
    def test_ensure_ark_trial_idempotent(self, db_path):
        assert ensure_ark_trial(db_path=db_path) == ensure_ark_trial(db_path=db_path)
