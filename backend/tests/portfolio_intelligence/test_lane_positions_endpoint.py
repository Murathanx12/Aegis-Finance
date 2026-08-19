"""GET /api/pi/lane/{lane_id}/positions — the one-command positions read.

Built for the 14-point-gap reconciliation (2026-08-19): the conviction NAV
tracks neither the YAML seed nor the prod decision log, and only the
positions table says what the lane actually marks. These tests pin the
endpoint to verbatim rows, read-only semantics, and honest 404s.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def _seeded_db(tmp_path, monkeypatch):
    from backend import db as db_module
    from backend.config import book_lanes, paper_portfolios
    from backend.services.portfolio_intelligence.reference_engine import (
        initialize_lane, seed_book_lane,
    )
    from backend.services.portfolio_intelligence.rules import (
        _get_sleeve_tickers,
    )

    fresh_db = tmp_path / "pos.db"
    monkeypatch.setattr(db_module, "DB_PATH", fresh_db)
    db_module.init_db(fresh_db)

    sleeves = _get_sleeve_tickers(paper_portfolios["universe"])
    ref_prices = {t: 100.0 for t in
                  sleeves["equity"] + sleeves["bond"] + sleeves["alternative"]}
    initialize_lane("balanced", db_path=fresh_db, prices=ref_prices)

    book_prices = {t: 50.0 for t in (book_lanes.get("holdings") or {})}
    seed_book_lane("mirror", db_path=fresh_db, prices=book_prices)
    return fresh_db


def test_positions_returns_verbatim_rows(tmp_path, monkeypatch):
    _seeded_db(tmp_path, monkeypatch)
    body = client.get("/api/pi/lane/mirror/positions").json()
    assert body["lane_id"] == "mirror"
    assert body["read_only"] is True
    assert body["positions"], "seeded mirror lane must expose its positions"
    for p in body["positions"]:
        assert set(p) == {"ticker", "shares", "cost_basis"}
        assert p["shares"] > 0
    assert isinstance(body["rebalance_events"], list)


def test_positions_covers_reference_lanes_too(tmp_path, monkeypatch):
    _seeded_db(tmp_path, monkeypatch)
    body = client.get("/api/pi/lane/balanced/positions").json()
    assert body["positions"]
    assert body["inception_value"] is not None


def test_unknown_lane_404s(tmp_path, monkeypatch):
    _seeded_db(tmp_path, monkeypatch)
    r = client.get("/api/pi/lane/not-a-lane/positions")
    assert r.status_code == 404


def test_unseeded_lane_returns_empty_not_invented(tmp_path, monkeypatch):
    _seeded_db(tmp_path, monkeypatch)   # conviction NOT seeded here
    body = client.get("/api/pi/lane/conviction/positions").json()
    assert body["positions"] == []
    assert body["inception_date"] is None, (
        "an unseeded lane must read as absent, never as a default book")
