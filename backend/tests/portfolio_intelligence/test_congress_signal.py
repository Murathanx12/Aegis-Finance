"""
Offline tests for the congressional-trading signal (TRIAL-CONGRESS-IC):
the pure scorer (distinct-member net purchases, PIT by disclosureDate,
stock-only), the dynamic universe cap, the fail-loud fetch contract, and the
forward collector (injected fetch → PIT store via the generic engine).
"""

import pytest

from backend.db import get_connection, get_series_observable, init_db
from backend.services.congress_trades import (
    active_universe, compute_congress_scores,
)
from backend.services.portfolio_intelligence.congress_collector import (
    KEY_PREFIX, collect_congress_scores, ensure_congress_trial,
)


def _t(symbol, member, ttype="Purchase", disclosed="2026-07-01",
       transacted="2026-06-01", asset_type="Stock", chamber="senate"):
    return {"chamber": chamber, "member_id": member, "symbol": symbol,
            "asset_type": asset_type, "type": ttype,
            "amount": "$1,001 - $15,000", "transaction_date": transacted,
            "disclosure_date": disclosed}


AS_OF = "2026-07-11"


class TestCongressScore:
    def test_net_distinct_members(self):
        trades = [_t("AAA", "m1"), _t("AAA", "m2"),
                  _t("AAA", "m3", ttype="Sale (Full)")]
        s = compute_congress_scores(trades, as_of=AS_OF)
        score, payload = s["AAA"]
        assert score == 1.0
        assert payload["n_buy_members"] == 2 and payload["n_sell_members"] == 1

    def test_one_member_many_trades_counts_once(self):
        # cluster effect: a member splitting an order is NOT conviction
        trades = [_t("AAA", "m1"), _t("AAA", "m1"), _t("AAA", "m1")]
        score, payload = compute_congress_scores(trades, as_of=AS_OF)["AAA"]
        assert score == 1.0 and payload["n_trades"] == 3

    def test_pit_by_disclosure_date_not_transaction_date(self):
        # transacted in-window but disclosed AFTER as_of → must not count
        trades = [_t("AAA", "m1", disclosed="2026-07-20", transacted="2026-06-20")]
        assert "AAA" not in compute_congress_scores(trades, as_of=AS_OF)

    def test_window_excludes_old_disclosures(self):
        trades = [_t("AAA", "m1", disclosed="2026-03-01"),  # >90d before as_of
                  _t("AAA", "m2", disclosed="2026-07-01")]
        score, payload = compute_congress_scores(trades, as_of=AS_OF)["AAA"]
        assert score == 1.0 and payload["n_buy_members"] == 1

    def test_non_stock_excluded_from_score_counted_in_payload(self):
        trades = [_t("AAA", "m1", asset_type="Corporate Bond"),
                  _t("AAA", "m2", asset_type="ETF"),
                  _t("AAA", "m3", asset_type="Stock Option"),
                  _t("AAA", "m4")]
        score, payload = compute_congress_scores(trades, as_of=AS_OF)["AAA"]
        assert score == 1.0
        assert payload["n_nonstock"] == 3 and payload["n_trades"] == 1

    def test_only_nonstock_yields_no_headline_score(self):
        trades = [_t("AAA", "m1", asset_type="ETF")]
        assert "AAA" not in compute_congress_scores(trades, as_of=AS_OF)

    def test_empty(self):
        assert compute_congress_scores([], as_of=AS_OF) == {}


class TestActiveUniverse:
    def test_cap_by_activity_deterministic(self):
        trades = ([_t("HOT", f"m{i}") for i in range(5)]
                  + [_t("MID", "m1"), _t("MID", "m2")]
                  + [_t("COLD", "m1")])
        scores = compute_congress_scores(trades, as_of=AS_OF)
        assert active_universe(scores, cap=2) == ["HOT", "MID"]
        assert active_universe(scores, cap=10) == ["HOT", "MID", "COLD"]


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "congress.db"
    init_db(p)
    return p


class TestCongressCollector:
    def test_writes_pit_rows_dynamic_universe(self, db_path):
        trades = [_t("AAA", "m1"), _t("AAA", "m2"),
                  _t("BBB", "m3", ttype="Sale (Partial)")]
        res = collect_congress_scores(db_path=db_path,
                                      fetch=lambda **kw: trades, as_of=AS_OF)
        assert res["status"] == "collected"
        assert res["scores"]["AAA"] == 2.0
        assert res["scores"]["BBB"] == -1.0
        assert res["nonzero"] == 2

    def test_value_lands_in_pit_store(self, db_path):
        trades = [_t("AAA", "m1")]
        collect_congress_scores(db_path=db_path, fetch=lambda **kw: trades,
                                as_of=AS_OF)
        conn = get_connection(db_path)
        try:
            series = get_series_observable(conn, KEY_PREFIX + "AAA")
        finally:
            conn.close()
        assert len(series) == 1 and series[0]["value"] == 1.0
        assert series[0]["source"] == "fmp_congress"

    def test_throttle_skips_within_window(self, db_path):
        trades = [_t("AAA", "m1")]
        collect_congress_scores(db_path=db_path, fetch=lambda **kw: trades,
                                as_of=AS_OF)
        res = collect_congress_scores(db_path=db_path,
                                      fetch=lambda **kw: trades,
                                      as_of="2026-07-13")
        assert res["status"] == "throttled"

    def test_source_failure_raises_before_any_pit_write(self, db_path):
        # the house failure mode: a dead source must NOT write false zeros
        def broken(**kw):
            raise ValueError("FMP senate-latest page 0 empty")
        with pytest.raises(ValueError):
            collect_congress_scores(db_path=db_path, fetch=broken, as_of=AS_OF)
        conn = get_connection(db_path)
        try:
            rows = conn.execute(
                "SELECT COUNT(*) AS n FROM pit_observations WHERE key LIKE ?",
                (KEY_PREFIX + "%",),
            ).fetchone()
        finally:
            conn.close()
        assert rows["n"] == 0


class TestFetchContractGuards:
    def test_rows_present_but_none_parse_raises(self, monkeypatch):
        # field rename (disclosureDate gone) must be LOUD, not a quiet week
        from backend.services import congress_trades as ct
        monkeypatch.setattr(ct, "_fmp_get",
                            lambda ep, page, limit:
                            [{"symbol": "AAA", "type": "Purchase"}]
                            if page == 0 else [])
        with pytest.raises(ValueError, match="contract drift"):
            ct.fetch_congress_trades(as_of=AS_OF)

    def test_page0_empty_raises(self, monkeypatch):
        from backend.services import congress_trades as ct
        monkeypatch.setattr(ct, "_fmp_get", lambda ep, page, limit: [])
        with pytest.raises(ValueError, match="page 0 empty"):
            ct.fetch_congress_trades(as_of=AS_OF)


class TestFmpErrorHygiene:
    """The 2026-07-16 prod incident: FMP 402 (quota) raised an HTTPError whose
    message embedded the full request URL — apikey included — and the
    scheduler logged it. Errors must be loud but secret-free."""

    class _Resp:
        def __init__(self, status_code, url):
            self.status_code = status_code
            self.url = url

        def raise_for_status(self):
            import requests
            if self.status_code >= 400:
                raise requests.HTTPError(
                    f"{self.status_code} Client Error for url: {self.url}",
                    response=self)

        def json(self):
            return []

    def test_402_maps_to_quota_message_without_key(self, monkeypatch):
        from backend.services import congress_trades as ct
        monkeypatch.setattr(ct.api_keys, "fmp", "SENTINEL_KEY_123")
        monkeypatch.setattr(
            ct.requests, "get",
            lambda url, **kw: self._Resp(402, f"{url}?apikey=SENTINEL_KEY_123"))
        with pytest.raises(RuntimeError, match="402") as exc:
            ct._fmp_get("senate-latest", 0, 250)
        assert "SENTINEL_KEY_123" not in str(exc.value)
        assert "quota" in str(exc.value)

    def test_http_error_message_is_redacted(self, monkeypatch):
        import requests
        from backend.services import congress_trades as ct
        monkeypatch.setattr(ct.api_keys, "fmp", "SENTINEL_KEY_123")
        monkeypatch.setattr(
            ct.requests, "get",
            lambda url, **kw: self._Resp(500, f"{url}?apikey=SENTINEL_KEY_123"))
        with pytest.raises(requests.HTTPError) as exc:
            ct._fmp_get("senate-latest", 0, 250)
        assert "SENTINEL_KEY_123" not in str(exc.value)
        assert "***" in str(exc.value)

    def test_redact_strips_every_configured_key(self):
        from backend.config import APIKeys
        keys = APIKeys(fred="FREDK", fmp="FMPK", finnhub="FINN")
        out = keys.redact("url?apikey=FMPK&other=FREDK plain FINN")
        assert "FMPK" not in out and "FREDK" not in out and "FINN" not in out

    def test_redact_noop_when_keys_unset(self):
        from backend.config import APIKeys
        assert APIKeys().redact("nothing to hide") == "nothing to hide"


class TestTrialRegistration:
    def test_ensure_congress_trial_idempotent(self, db_path):
        id1 = ensure_congress_trial(db_path=db_path)
        id2 = ensure_congress_trial(db_path=db_path)
        assert id1 == id2
        conn = get_connection(db_path)
        try:
            rows = conn.execute(
                "SELECT COUNT(*) AS n FROM rule_experiments WHERE param = ?",
                ("congress-ic-signal",),
            ).fetchone()
        finally:
            conn.close()
        assert rows["n"] == 1
