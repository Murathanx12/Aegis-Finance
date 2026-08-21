"""TRIAL-PREDMARKET-1 collector — the failure contract IS the test surface.

The claims under test: watched-category/scope filters hold; a fetch failure
raises BEFORE any write (no false-zero snapshots); an empty day is a named
receipt, not silence; truncated pagination is recorded; the snapshot is
idempotent per day; the API surface reads disk only and carries the
descriptive-context banner. Nothing here tests a return claim — there isn't
one.
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


@pytest.fixture
def pm_dir(tmp_path, monkeypatch):
    d = tmp_path / "pmkt"
    monkeypatch.setattr(config, "PREDICTION_MARKET_DIR", d)
    monkeypatch.setattr(pm, "_PAGE_SLEEP_S", 0)
    return d


def _serve(monkeypatch, pages):
    """Serve canned pages; repeats the last page if paginated further."""
    calls: list[dict] = []

    def fake(url, params):
        calls.append(dict(params))
        return pages[min(len(calls) - 1, len(pages) - 1)]

    monkeypatch.setattr(pm, "_get_json", fake)
    return calls


class TestScopeFilters:
    def test_only_watched_categories_within_scope_survive(self, pm_dir,
                                                          monkeypatch):
        _serve(monkeypatch, [{"cursor": "", "events": [
            _event("Economics"),
            _event("Sports", prefix="KXNFL"),          # unwatched category
            _event("Companies", prefix="KXTSLA", oi="0"),   # dead book
            _event("Financials", prefix="KXFAR",
                   close="2099-01-01T00:00:00Z"),      # beyond close horizon
            _event("Economics", prefix="KXSET", status="settled"),
        ]}])
        out = pm.fetch_open_markets(now=NOW)
        assert [r["ticker"] for r in out["rows"]] == ["KXCPI-M0"]
        row = out["rows"][0]
        assert row["mid"] == pytest.approx(0.42)
        assert row["snapshot_date"] == "2026-08-21"
        assert out["pages_truncated"] is False

    def test_one_sided_book_keeps_the_row_without_a_mid(self, pm_dir,
                                                        monkeypatch):
        _serve(monkeypatch, [{"cursor": "", "events": [
            _event("Economics", yes_ask_dollars=""),
        ]}])
        rows = pm.fetch_open_markets(now=NOW)["rows"]
        assert len(rows) == 1
        assert rows[0]["mid"] is None
        assert rows[0]["last_price"] == pytest.approx(0.42)

    def test_pagination_cap_is_recorded_not_silent(self, pm_dir, monkeypatch):
        monkeypatch.setattr(config, "PREDICTION_MARKET_MAX_PAGES", 2)
        _serve(monkeypatch, [
            {"cursor": "more", "events": [_event("Economics")]},
        ])
        out = pm.fetch_open_markets(now=NOW)
        assert out["pages"] == 2
        assert out["pages_truncated"] is True


class TestSnapshotContract:
    def test_fetch_failure_writes_nothing(self, pm_dir, monkeypatch):
        def boom(url, params):
            raise RuntimeError("edge reset")
        monkeypatch.setattr(pm, "_get_json", boom)
        with pytest.raises(pm.PredictionMarketFetchError):
            pm.snapshot_daily(now=NOW)
        # No day file, no receipt: the missing receipt IS the evidence.
        assert not pm_dir.exists() or not list(pm_dir.rglob("*"))

    def test_snapshot_writes_day_file_and_receipt(self, pm_dir, monkeypatch):
        _serve(monkeypatch, [{"cursor": "", "events": [_event("Economics")]}])
        res = pm.snapshot_daily(now=NOW)
        assert res["status"] == "ok"
        day_file = pm_dir / "snapshots" / "2026-08-21.jsonl"
        assert day_file.exists()
        lines = [json.loads(l) for l in
                 day_file.read_text(encoding="utf-8").splitlines() if l]
        assert len(lines) == 1
        receipt = json.loads(
            (pm_dir / "receipts" / "2026-08-21.json").read_text("utf-8"))
        assert receipt["status"] == "ok"
        assert receipt["trial"] == "TRIAL-PREDMARKET-1"
        assert "never a signal" in receipt["banner"]
        assert receipt["filters"]["categories"] == sorted(
            config.PREDICTION_MARKET_CATEGORIES)

    def test_second_run_same_day_does_not_refetch(self, pm_dir, monkeypatch):
        _serve(monkeypatch, [{"cursor": "", "events": [_event("Economics")]}])
        assert pm.snapshot_daily(now=NOW)["status"] == "ok"

        def boom(url, params):  # a re-fetch would blow up here
            raise AssertionError("refetched on an already-written day")
        monkeypatch.setattr(pm, "_get_json", boom)
        res = pm.snapshot_daily(now=NOW)
        assert res["status"] == "already_written"
        assert res["rows"] == 1

    def test_zero_in_scope_markets_is_a_named_receipt(self, pm_dir,
                                                      monkeypatch):
        _serve(monkeypatch, [{"cursor": "", "events": [
            _event("Sports", prefix="KXNFL")]}])
        res = pm.snapshot_daily(now=NOW)
        assert res["status"] == "ok_empty"
        assert (pm_dir / "receipts" / "2026-08-21.json").exists()
        assert not (pm_dir / "snapshots" / "2026-08-21.jsonl").exists()


class TestSurface:
    def test_latest_summary_before_any_snapshot_is_ok_empty(self, pm_dir):
        out = pm.latest_summary()
        assert out["status"] == "OK_EMPTY"
        assert "pi_prediction_markets" in out["reason"]

    def test_latest_summary_reads_newest_snapshot_from_disk(self, pm_dir,
                                                            monkeypatch):
        _serve(monkeypatch, [{"cursor": "", "events": [
            _event("Economics"), _event("Financials", prefix="KXFED")]}])
        pm.snapshot_daily(now=NOW)
        out = pm.latest_summary()
        assert out["status"] == "ok"
        assert out["snapshot_date"] == "2026-08-21"
        assert out["n_markets"] == 2
        assert out["by_category"] == {"Economics": 1, "Financials": 1}
        assert out["top_by_open_interest"][0]["mid"] == pytest.approx(0.42)
        assert "never a signal" in out["banner"]

    def test_route_and_job_are_registered(self):
        from backend.routers.prediction_markets import router
        assert any(r.path == "/api/prediction-markets" for r in router.routes)
        from backend.services.portfolio_intelligence import scheduler as sched
        assert "pi_prediction_markets" in sched.EXPECTED_JOB_IDS
