"""The board's books endpoint: a book is never returned without its twins.

B3's acceptance criterion is a property of the PAYLOAD, not of the renderer. A
rule the page keeps is one refactor away from being gone; a rule the data keeps
survives the page being rewritten.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import book_cadence as BC
from backend.services import paper_books as PB
from backend.tests.book_helpers import make_strategy, seeded_db, synthetic_bars

client = TestClient(app)


@pytest.fixture()
def books_db(tmp_path, monkeypatch):
    """Point every default DB handle at a throwaway file with the lanes seeded.

    BOTH handles. `backend.db.DB_PATH` is what the routers read, and
    `paper_books._conn` is separately redirected by conftest's
    `_book_cadence_receipts_to_tmp` (so a Morning click in any test cannot mark
    the machine's real books). This fixture runs AFTER that autouse one, so
    patching `_conn` again here wins and points both at the same file -- which
    is the whole point: the route and the test must be looking at one database.
    """
    from backend import db as DB
    from backend.db import get_connection, init_db
    path = tmp_path / "aegis_pi.db"
    conn = seeded_db(path)
    monkeypatch.setattr(DB, "DB_PATH", path)
    monkeypatch.setattr(
        PB, "_conn",
        lambda db_path=None: (init_db(db_path or path)
                              or get_connection(db_path or path)))
    yield path, conn
    conn.close()


@pytest.fixture()
def bars():
    return synthetic_bars(n=300)


@pytest.fixture(autouse=True)
def _ledger_to_tmp(tmp_path, monkeypatch):
    from backend.services import belief_state as BS
    monkeypatch.setattr(BS, "PREDICTIONS", tmp_path / "predictions.jsonl")
    monkeypatch.setattr(BS, "_migrate_once", lambda: None)


def _seed(conn, bars, asof=None):
    asof = asof or BC.latest_bar_date(bars)
    return PB.create(make_strategy(), cadence="daily", origin="night_job",
                     origin_text="seeded by a test", bars=bars, asof=asof,
                     conn=conn)


def test_no_books_is_a_statement_not_an_error(books_db):
    body = client.get("/api/control/books").json()
    assert body["available"] is True
    assert body["books"] == []
    assert body["n_books"] == 0
    assert body["note"]


def test_every_book_carries_its_twins_inside_its_own_row(books_db, bars):
    path, conn = books_db
    book, twins = _seed(conn, bars)
    body = client.get("/api/control/books").json()
    assert body["n_books"] == 1
    row = body["books"][0]
    assert row["book_id"] == book.book_id
    assert len(row["twins"]) == len(twins) >= 1
    assert {t["book_id"] for t in row["twins"]} == {t.book_id for t in twins}
    for t in row["twins"]:
        assert t["kind"] and t["construction"] and t["present"] is True


def test_a_twin_is_never_a_top_level_row(books_db, bars):
    """A twin listed as a book of its own would be a control masquerading as a
    result, and would double the apparent number of independent books."""
    path, conn = books_db
    book, twins = _seed(conn, bars)
    body = client.get("/api/control/books").json()
    top = {r["book_id"] for r in body["books"]}
    assert top == {book.book_id}
    assert not (top & {t.book_id for t in twins})


def test_the_payload_has_no_shape_without_a_twin(books_db, bars):
    """The structural claim, stated as a test: `twins` is on every row."""
    path, conn = books_db
    _seed(conn, bars)
    for row in client.get("/api/control/books").json()["books"]:
        assert "twins" in row and isinstance(row["twins"], list) and row["twins"]


def test_an_unmarked_book_says_why_it_has_no_nav(books_db, bars):
    path, conn = books_db
    _seed(conn, bars)
    row = client.get("/api/control/books").json()["books"][0]
    assert row["nav"] is None
    assert "no cadence pass has marked this book yet" in row["why_no_nav"]
    assert row["n_marks"] == 0


def test_a_thin_series_is_reported_but_not_estimable(books_db, bars, tmp_path,
                                                     monkeypatch):
    path, conn = books_db
    monkeypatch.setattr(BC, "receipt_dir", lambda: tmp_path / "receipts")
    _seed(conn, bars)
    import pandas as pd
    days = sorted(pd.Timestamp(d).date() for d in bars["date"].unique())[-4:]
    for d in days:
        BC.run_pass("daily", conn=conn, bars=bars, today=d, write_receipt=False,
                    predictions_path=tmp_path / "predictions.jsonl")
    row = client.get("/api/control/books").json()["books"][0]
    assert row["nav"] is not None and row["n_marks"] >= 2
    vs = row["vs_twin"]
    assert vs["estimable"] is False
    assert vs["why_not_estimable"]
    assert vs["n_days"] < client.get("/api/control/books").json()["min_days_for_estimable"]
    # the standard error travels with the mean, in every state
    assert "se_daily_excess_pct" in vs


def test_the_engine_brier_is_returned_beside_the_base_rate_brier(books_db, bars):
    path, conn = books_db
    _seed(conn, bars)
    row = client.get("/api/control/books").json()["books"][0]
    f = row["forecasts"]
    assert "brier" in f and "base_rate_brier" in f, (
        "the engine's Brier alone says nothing: the whole question is whether "
        "it beats a forecaster that looked at nothing")


def test_the_worst_case_in_dollars_is_on_every_row(books_db, bars):
    path, conn = books_db
    _seed(conn, bars)
    row = client.get("/api/control/books").json()["books"][0]
    assert row["worst_case"]["verdict"]
    assert row["worst_case"]["gross_over_equity"] is not None


# ── create-from-contract ───────────────────────────────────────────────────


def test_create_is_control_plane_gated(books_db, monkeypatch):
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    r = client.post("/api/control/books/create-from-contract", json={})
    assert r.status_code == 403


def test_create_refuses_a_human_text_origin(books_db, monkeypatch):
    """B2's hold step is a human clicking, not a route being called."""
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    r = client.post("/api/control/books/create-from-contract",
                    json={"strategy": make_strategy().as_dict(),
                          "cadence": "daily", "origin": "human_text"})
    assert r.status_code == 422
    assert "human" in r.json()["detail"].lower()


def test_create_refuses_a_contract_with_an_unknown_field(books_db, monkeypatch):
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    bad = make_strategy().as_dict()
    bad["universe"]["a_field_that_does_not_exist"] = 1
    r = client.post("/api/control/books/create-from-contract",
                    json={"strategy": bad, "cadence": "daily"})
    assert r.status_code == 422
    assert "a_field_that_does_not_exist" in r.json()["detail"]


def test_create_refuses_a_bad_cadence(books_db, monkeypatch):
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    r = client.post("/api/control/books/create-from-contract",
                    json={"strategy": make_strategy().as_dict(),
                          "cadence": "hourly"})
    assert r.status_code == 422


def test_create_makes_a_book_with_its_twins(books_db, bars, monkeypatch):
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    monkeypatch.setattr(PB, "load_bars", lambda *a, **k: bars)
    r = client.post("/api/control/books/create-from-contract",
                    json={"strategy": make_strategy().as_dict(),
                          "cadence": "monthly", "origin": "night_job",
                          "origin_text": "the first night-job book"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True
    assert body["twins"], "a book was created without a control"
    assert body["book"]["cadence"] == "monthly"
    assert body["book"]["origin"] == "night_job"
    # and it shows up on the board, with its twins
    listed = client.get("/api/control/books").json()
    assert listed["n_books"] == 1
    assert listed["books"][0]["twins"]
