"""TRIAL-PREDMARKET-1/-2 collectors — the failure contract IS the test surface.

The claims under test: per-venue scope filters hold; a fetch failure raises
BEFORE any write (no false-zero snapshots) and one venue's outage cannot
cost the other venue's day; an empty day is a named receipt, not silence;
truncated pagination is recorded; snapshots are idempotent per day per
source; the API surface reads disk only and carries the descriptive-context
banner. Nothing here tests a return claim — there isn't one.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend import config
from backend.services import prediction_markets as pm

NOW = datetime(2026, 8, 21, 21, 55, tzinfo=timezone.utc)


def _event(category="Economics", close="2026-11-30T15:00:00Z", oi="100",
           status="active", prefix="KXCPI", **mkt):
    m = {"ticker": f"{prefix}-M0", "title": "market title", "status": status,
         "close_time": close, "open_interest_fp": oi,
         "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.44",
         "last_price_dollars": "0.42", "volume_fp": "10",
         "volume_24h_fp": "1", "market_type": "binary",
         "yes_sub_title": "strike"}
    m.update(mkt)
    return {"category": category, "series_ticker": prefix,
            "event_ticker": f"{prefix}-EV", "title": "event title",
            "markets": [m]}


def _pmarket(slug="fed-hike-september", close="2026-11-30T15:00:00Z",
             accepting=True, vol24="500", **over):
    m = {"slug": slug, "question": "Fed hike in September?",
         "conditionId": "0xabc", "endDate": close,
         "acceptingOrders": accepting, "bestBid": 0.40, "bestAsk": 0.44,
         "lastTradePrice": 0.42, "liquidityNum": 5000.0,
         "volumeNum": 100000.0, "volume24hr": vol24, "spread": 0.04,
         "feeSchedule": {"rate": 0.04, "takerOnly": True},
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.42", "0.58"]',
         "events": [{"ticker": "fed-september", "title": "Fed September"}]}
    m.update(over)
    return m


@pytest.fixture
def pm_dir(tmp_path, monkeypatch):
    d = tmp_path / "pmkt"
    monkeypatch.setattr(config, "PREDICTION_MARKET_DIR", d)
    monkeypatch.setattr(pm, "_PAGE_SLEEP_S", 0)
    return d


def _serve(monkeypatch, responder):
    """responder(url, params) -> page body. Tracks calls."""
    calls: list[tuple[str, dict]] = []

    def fake(url, params):
        calls.append((url, dict(params)))
        return responder(url, dict(params))

    monkeypatch.setattr(pm, "_get_json", fake)
    return calls


def _serve_both(monkeypatch, kalshi_events=None, polymarkets=None):
    def responder(url, params):
        if "kalshi" in url:
            return {"cursor": "", "events": kalshi_events or []}
        return polymarkets if params.get("offset", 0) == 0 else []

    return _serve(monkeypatch, responder)


# ── kalshi scope ────────────────────────────────────────────────────────────
class TestKalshiScope:
    def test_only_watched_categories_within_scope_survive(self, pm_dir,
                                                          monkeypatch):
        _serve_both(monkeypatch, kalshi_events=[
            _event("Economics"),
            _event("Sports", prefix="KXNFL"),          # unwatched category
            _event("Companies", prefix="KXTSLA", oi="0"),   # dead book
            _event("Financials", prefix="KXFAR",
                   close="2099-01-01T00:00:00Z"),      # beyond close horizon
            _event("Economics", prefix="KXSET", status="settled"),
        ])
        out = pm.fetch_open_markets(now=NOW)
        assert [r["ticker"] for r in out["rows"]] == ["KXCPI-M0"]
        row = out["rows"][0]
        assert row["mid"] == pytest.approx(0.42)
        assert row["source"] == "kalshi"
        assert out["pages_truncated"] is False

    def test_one_sided_book_keeps_the_row_without_a_mid(self, pm_dir,
                                                        monkeypatch):
        _serve_both(monkeypatch, kalshi_events=[
            _event("Economics", yes_ask_dollars="")])
        rows = pm.fetch_open_markets(now=NOW)["rows"]
        assert len(rows) == 1
        assert rows[0]["mid"] is None
        assert rows[0]["last_price"] == pytest.approx(0.42)

    def test_pagination_cap_is_recorded_not_silent(self, pm_dir, monkeypatch):
        monkeypatch.setattr(config, "PREDICTION_MARKET_MAX_PAGES", 2)
        _serve(monkeypatch, lambda url, params: {
            "cursor": "more", "events": [_event("Economics")]})
        out = pm.fetch_open_markets(now=NOW)
        assert out["pages"] == 2
        assert out["pages_truncated"] is True


# ── polymarket scope ────────────────────────────────────────────────────────
class TestPolymarketScope:
    def test_scope_filters_and_row_mapping(self, pm_dir, monkeypatch):
        _serve_both(monkeypatch, polymarkets=[
            _pmarket(),
            _pmarket(slug="closed-orders", accepting=False),
            _pmarket(slug="far-future", close="2099-01-01T00:00:00Z"),
            _pmarket(slug="dead-volume", vol24="0"),
        ])
        out = pm.fetch_polymarket_markets(now=NOW)
        assert [r["ticker"] for r in out["rows"]] == ["fed-hike-september"]
        row = out["rows"][0]
        assert row["source"] == "polymarket"
        assert row["mid"] == pytest.approx(0.42)
        assert row["fee_rate"] == pytest.approx(0.04)
        assert row["liquidity"] == pytest.approx(5000.0)
        assert row["event_ticker"] == "fed-september"

    def test_offset_pagination_ends_on_empty_page_not_short_page(
            self, pm_dir, monkeypatch):
        """Gamma caps pages at 100 regardless of the requested limit, so a
        short page is NORMAL — only an empty page means done. Ending on
        short pages silently dropped everything after page 1 (caught by the
        live smoke, 2 rows from a 6k universe)."""
        calls = _serve(monkeypatch, lambda url, params: (
            [_pmarket(slug=f"m{params['offset']}")]
            if params["offset"] == 0 else []))
        out = pm.fetch_polymarket_markets(now=NOW)
        # short first page -> a second request proves we did NOT stop early;
        # its empty reply ends the loop
        assert len(calls) == 2
        assert calls[1][1]["offset"] == pm._POLYMARKET_PAGE_LIMIT
        assert len(out["rows"]) == 1
        assert out["pages_truncated"] is False

    def test_liquidity_floor_is_requested_server_side(self, pm_dir,
                                                      monkeypatch):
        calls = _serve_both(monkeypatch, polymarkets=[_pmarket()])
        pm.fetch_polymarket_markets(now=NOW)
        poly_calls = [p for (u, p) in calls if "polymarket" in u]
        assert poly_calls[0]["liquidity_num_min"] == \
            config.POLYMARKET_MIN_LIQUIDITY


# ── snapshot contract ───────────────────────────────────────────────────────
class TestSnapshotContract:
    def test_total_fetch_failure_writes_nothing(self, pm_dir, monkeypatch):
        def boom(url, params):
            raise RuntimeError("edge reset")
        monkeypatch.setattr(pm, "_get_json", boom)
        res = pm.snapshot_daily(now=NOW)
        assert res["any_error"] is True
        assert all(s["status"] == "error" for s in res["sources"].values())
        # No day files, no receipts: the missing receipt IS the evidence.
        assert not pm_dir.exists() or not list(pm_dir.rglob("*.json*"))

    def test_one_venue_outage_does_not_cost_the_other_day(self, pm_dir,
                                                          monkeypatch):
        def responder(url, params):
            if "polymarket" in url:
                raise RuntimeError("gamma down")
            return {"cursor": "", "events": [_event("Economics")]}
        _serve(monkeypatch, responder)
        res = pm.snapshot_daily(now=NOW)
        assert res["any_error"] is True
        assert res["sources"]["kalshi"]["status"] == "ok"
        assert res["sources"]["polymarket"]["status"] == "error"
        assert (pm_dir / "snapshots" / "2026-08-21.kalshi.jsonl").exists()
        assert not (pm_dir / "snapshots"
                    / "2026-08-21.polymarket.jsonl").exists()
        assert not (pm_dir / "receipts"
                    / "2026-08-21.polymarket.json").exists()

    def test_snapshot_writes_per_source_files_and_receipts(self, pm_dir,
                                                           monkeypatch):
        _serve_both(monkeypatch, kalshi_events=[_event("Economics")],
                    polymarkets=[_pmarket()])
        res = pm.snapshot_daily(now=NOW)
        assert res["any_error"] is False
        for source in ("kalshi", "polymarket"):
            assert res["sources"][source]["status"] == "ok"
            df = pm_dir / "snapshots" / f"2026-08-21.{source}.jsonl"
            assert df.exists()
            receipt = json.loads((pm_dir / "receipts"
                                  / f"2026-08-21.{source}.json"
                                  ).read_text("utf-8"))
            assert receipt["status"] == "ok"
            assert "never a signal" in receipt["banner"]
        # each trial is stamped on its own venue's receipt
        k = json.loads((pm_dir / "receipts" / "2026-08-21.kalshi.json"
                        ).read_text("utf-8"))
        p = json.loads((pm_dir / "receipts" / "2026-08-21.polymarket.json"
                        ).read_text("utf-8"))
        assert k["trial"] == "TRIAL-PREDMARKET-1"
        assert p["trial"] == "TRIAL-PREDMARKET-2"

    def test_second_run_same_day_does_not_refetch(self, pm_dir, monkeypatch):
        _serve_both(monkeypatch, kalshi_events=[_event("Economics")],
                    polymarkets=[_pmarket()])
        assert pm.snapshot_daily(now=NOW)["any_error"] is False

        def boom(url, params):  # a re-fetch would blow up here
            raise AssertionError("refetched on an already-written day")
        monkeypatch.setattr(pm, "_get_json", boom)
        res = pm.snapshot_daily(now=NOW)
        assert res["sources"]["kalshi"]["status"] == "already_written"
        assert res["sources"]["polymarket"]["status"] == "already_written"

    def test_zero_in_scope_markets_is_a_named_receipt(self, pm_dir,
                                                      monkeypatch):
        _serve_both(monkeypatch,
                    kalshi_events=[_event("Sports", prefix="KXNFL")],
                    polymarkets=[])
        res = pm.snapshot_daily(now=NOW)
        assert res["sources"]["kalshi"]["status"] == "ok_empty"
        assert res["sources"]["polymarket"]["status"] == "ok_empty"
        assert (pm_dir / "receipts" / "2026-08-21.kalshi.json").exists()
        assert not (pm_dir / "snapshots" / "2026-08-21.kalshi.jsonl").exists()


# ── the API surface ─────────────────────────────────────────────────────────
class TestSurface:
    def test_latest_summary_before_any_snapshot_is_ok_empty(self, pm_dir):
        out = pm.latest_summary()
        assert out["status"] == "OK_EMPTY"
        assert "pi_prediction_markets" in out["reason"]

    def test_latest_summary_aggregates_the_newest_day_across_sources(
            self, pm_dir, monkeypatch):
        _serve_both(monkeypatch,
                    kalshi_events=[_event("Economics"),
                                   _event("Financials", prefix="KXFED")],
                    polymarkets=[_pmarket()])
        pm.snapshot_daily(now=NOW)
        out = pm.latest_summary()
        assert out["status"] == "ok"
        assert out["snapshot_date"] == "2026-08-21"
        assert out["n_markets"] == 3
        assert out["by_source"] == {"kalshi": 2, "polymarket": 1}
        assert out["by_category"] == {"Economics": 1, "Financials": 1,
                                      "uncategorised": 1}
        assert out["receipts"]["kalshi"]["status"] == "ok"
        assert out["receipts"]["polymarket"]["status"] == "ok"
        assert "never a signal" in out["banner"]

    def test_route_and_job_are_registered(self):
        from backend.routers.prediction_markets import router
        assert any(r.path == "/api/prediction-markets" for r in router.routes)
        from backend.services.portfolio_intelligence import scheduler as sched
        assert "pi_prediction_markets" in sched.EXPECTED_JOB_IDS
