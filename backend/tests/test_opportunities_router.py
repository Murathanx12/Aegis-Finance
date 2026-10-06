"""The Opportunity Explorer router (C4, 2026-10-06): 404 / 422 / shape, offline.

Every receipt here is constructed in tmp_path; nothing reads the machine's
ledger. Dates are derived from `now`, never a calendar literal.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config as _config
from backend.routers import opportunities as R
from backend.services import opportunities as O


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)
    app = FastAPI()
    app.include_router(R.router)
    return TestClient(app), tmp_path


def _row(ticker: str, list_id: str, stamp: str) -> dict:
    return {"ticker": ticker, "company_name": None, "list_id": list_id, "weight": None,
            "move_score": {"label": "MAGNITUDE", "expected_abs_move_21s": 0.1},
            "direction": None, "last_update_utc": stamp,
            "missing_because": {"company_name": "no receipt", "direction": "no consensus",
                                "weight": "a ranked list"},
            "links": O.links(ticker)}


def _write(base, *, asof: str, run_id: str, lists: list[dict]) -> None:
    d = base / "opportunities"
    d.mkdir(parents=True, exist_ok=True)
    blob = {"schema": O.SCHEMA, "asof": asof, "run_id": run_id, "generated_utc": asof + "T00:00:00+00:00",
            "legend": {"move_score": "magnitude", "direction": "consensus + revisions"}, "lists": lists}
    (d / f"opportunities_{asof}_{run_id}.json").write_text(json.dumps(blob), encoding="utf-8")


def test_404_when_no_receipt(client):
    c, _ = client
    r = c.get("/api/opportunities/latest")
    assert r.status_code == 404
    assert "opportunities_build" in r.json()["detail"]
    assert c.get("/api/opportunities/roi_v3").status_code == 404


def test_422_on_a_bad_list_id(client):
    c, base = client
    _write(base, asof="2026-01-01", run_id="20260101T000000Z", lists=[])
    assert c.get("/api/opportunities/BAD%20ID!").status_code == 422
    assert c.get("/api/opportunities/" + "x" * 90).status_code == 422


def test_404_on_an_unknown_list(client):
    c, base = client
    now = datetime.now(timezone.utc)
    _write(base, asof=now.date().isoformat(), run_id=now.strftime("%Y%m%dT%H%M%SZ"),
           lists=[{"list_id": "roi_v3", "title": "t", "rows": [_row("AAA", "roi_v3", now.isoformat())]}])
    r = c.get("/api/opportunities/not_a_list")
    assert r.status_code == 404
    assert "roi_v3" in r.json()["detail"]


def test_latest_shape_and_serve_time_age(client):
    c, base = client
    now = datetime.now(timezone.utc)
    two_days_ago = (now - timedelta(days=2)).isoformat()
    lists = [{"list_id": "roi_v3", "title": "ROI", "kind": "ranking", "rows": [_row("AAA", "roi_v3", two_days_ago)]},
             {"list_id": "book_x", "title": "Book", "kind": "book", "label": "MAGNITUDE RANKING: not a long list",
              "rows": [_row("BBB", "book_x", now.isoformat()), _row("000660.KS", "book_x", now.isoformat())]}]
    _write(base, asof=now.date().isoformat(), run_id=now.strftime("%Y%m%dT%H%M%SZ"), lists=lists)

    body = c.get("/api/opportunities/latest").json()
    assert [x["list_id"] for x in body["lists"]] == ["roi_v3", "book_x"]
    assert all("rows" not in x for x in body["lists"])          # the switcher carries no rows
    assert [x["n_rows"] for x in body["lists"]] == [1, 2]
    assert body["list"]["list_id"] == "roi_v3"
    age = body["list"]["rows"][0]["last_update_age_days"]
    assert 1.9 < age < 2.1                                       # computed at serve time
    assert body["legend"]["move_score"]

    one = c.get("/api/opportunities/book_x").json()["list"]
    assert one["label"].startswith("MAGNITUDE RANKING")
    for r in one["rows"]:
        # a null field always carries its reason
        for k, v in r.items():
            if v is None and k in ("company_name", "direction", "weight"):
                assert k in r["missing_because"]


def test_newest_receipt_wins_by_name_and_unreadable_is_skipped(client):
    c, base = client
    _write(base, asof="2026-01-01", run_id="20260101T000000Z",
           lists=[{"list_id": "old", "title": "old", "rows": []}])
    _write(base, asof="2026-01-02", run_id="20260102T000000Z",
           lists=[{"list_id": "new", "title": "new", "rows": []}])
    (base / "opportunities" / "opportunities_2026-01-03_20260103T000000Z.json").write_text("{not json", encoding="utf-8")
    body = c.get("/api/opportunities/latest").json()
    assert body["receipt_file"] == "opportunities_2026-01-02_20260102T000000Z.json"
    assert body["skipped_receipts"][0]["file"].startswith("opportunities_2026-01-03")


def test_links_and_exchange_for_foreign_tickers():
    assert O.exchange_of("000660.KS") == ("Korea Exchange (KOSPI)", "KRW")
    assert O.exchange_of("VRT") == (None, None)
    assert O.exchange_of("ABC.ZZ") == (None, None)               # unmapped suffix: null, never a guess
    lk = O.links("6857.T")
    assert lk["yahoo"].endswith("/quote/6857.T") and lk["marketwatch"] is None
    us = O.links("VRT", cik="1674101")
    assert "CIK=0001674101" in us["edgar"] and us["benzinga"].endswith("/quote/VRT")


def test_router_is_registered_on_the_app():
    from backend.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/opportunities/latest" in paths
    assert "/api/opportunities/{list_id}" in paths


def test_public_site_origin_is_always_allowed():
    """2026-10-06: the backend echoed no CORS origin for the public site, so every
    browser call from it was blocked. An env list may ADD origins, never drop the site."""
    import backend.main as M
    assert "https://aegis-finance-six.vercel.app" in M._origins
