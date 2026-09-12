"""Lane B1/B3: a book is a frozen contract with a twin, and the lanes are untouched.

The two properties worth a test rather than a convention:

1. **A book cannot exist without a control.** `create()` refuses, at creation,
   before the book has a number — because a twin built after a number is known
   is a twin chosen to flatter it.
2. **The four reference lanes' `paper_nav` rows are byte-identical before and
   after a book is created and marked.** The write path is sacred (CANON §5);
   the book namespace is additive and this is the test that says so rather than
   the comment that claims it.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from backend.services import paper_books as PB
from backend.tests.book_helpers import (lane_rows, make_strategy,
                                        seeded_db, synthetic_bars)

@pytest.fixture()
def db(tmp_path):
    conn = seeded_db(tmp_path / "aegis_pi.db")
    yield tmp_path / "aegis_pi.db", conn
    conn.close()


# ── B1 ─────────────────────────────────────────────────────────────────────


def test_book_id_is_the_fingerprint():
    s = make_strategy()
    assert PB.book_id_for(s) == f"book:{s.fingerprint}"
    assert PB.is_book_id(PB.book_id_for(s))
    assert not PB.is_book_id("balanced")


def test_create_refuses_a_zero_cost_diagnostic(db):
    path, conn = db
    with pytest.raises(PB.BookError, match="ZERO-COST"):
        PB.create(make_strategy(zero_cost=True), cadence="daily",
                  origin="night_job", bars=synthetic_bars(), conn=conn)


def test_create_refuses_an_unknown_origin(db):
    path, conn = db
    with pytest.raises(PB.BookError, match="origin"):
        PB.create(make_strategy(), cadence="daily", origin="whatever",
                  bars=synthetic_bars(), conn=conn)


def test_create_refuses_an_unknown_cadence(db):
    path, conn = db
    with pytest.raises(PB.BookError, match="cadence"):
        PB.create(make_strategy(), cadence="fortnightly", origin="night_job",
                  bars=synthetic_bars(), conn=conn)


def test_monthly_is_a_cadence():
    """spec_first_books §0C: three of the first four books rebalance monthly."""
    assert "monthly" in PB.CADENCES
    assert PB.CADENCE_SESSIONS["monthly"] == 20
    from backend.services.belief_state import HORIZONS
    for c, h in PB.CADENCE_SESSIONS.items():
        assert h in HORIZONS, f"cadence {c} maps to horizon {h}, not in HORIZONS"


def test_threshold_coverage_is_a_declared_construction():
    """The abstention book (spec_first_books §D.3) without a contract field."""
    from backend.strategy.contract import KNOWN_CONSTRUCTION
    assert "threshold_coverage" in KNOWN_CONSTRUCTION
    s = make_strategy(rule="threshold_coverage")
    assert s.construction.rule == "threshold_coverage"


def test_adding_the_rule_did_not_change_an_existing_fingerprint():
    """A new ALLOWED VALUE is additive; a new FIELD would not have been.

    If `threshold_coverage` had arrived as a `Construction` field, every book
    ever written would have a different fingerprint and no two sessions could
    agree they were looking at the same strategy. This pins the distinction.
    """
    s = make_strategy()
    assert s.fingerprint == make_strategy().fingerprint
    assert "threshold_coverage" not in json.dumps(s.as_dict())


def test_create_persists_and_round_trips(db):
    path, conn = db
    s = make_strategy()
    book, twins = PB.create(s, cadence="weekly", origin="human_text",
                            origin_text="buy the strong ones",
                            bars=synthetic_bars(), conn=conn)
    assert book.book_id == PB.book_id_for(s)
    assert book.origin_text == "buy the strong ones"
    got = PB.get(book.book_id, conn=conn)
    assert got is not None
    assert got.strategy.fingerprint == s.fingerprint
    assert got.control_twin_ids == tuple(t.book_id for t in twins)
    assert got.cadence == "weekly"
    # the contract survives the round trip completely, costs included
    assert got.strategy.as_dict() == s.as_dict()


def test_a_book_carries_its_worst_case_in_dollars(db):
    path, conn = db
    book, _ = PB.create(make_strategy(), cadence="daily", origin="night_job",
                        bars=synthetic_bars(), conn=conn)
    wc = PB.worst_case(book, equity_usd=100_000.0)
    assert wc["worst_case_usd"] is not None and wc["worst_case_usd"] < 0
    assert "gross" in wc["verdict"]


# ── B3 ─────────────────────────────────────────────────────────────────────


def test_every_book_gets_a_twin_and_the_twin_is_itself_a_book(db):
    path, conn = db
    book, twins = PB.create(make_strategy(), cadence="daily", origin="night_job",
                            bars=synthetic_bars(), conn=conn)
    assert twins, "a book with no twin must never be created"
    for t in twins:
        assert t.is_twin and t.parent_id == book.book_id
        assert t.cadence == book.cadence
        assert t.strategy.costs.as_row() == book.strategy.costs.as_row()
        assert PB.get(t.book_id, conn=conn) is not None
    assert book.control_construction


def test_a_long_only_book_gets_a_beta_matched_twin(db):
    path, conn = db
    _, twins = PB.create(make_strategy(), cadence="daily", origin="night_job",
                         bars=synthetic_bars(), conn=conn)
    kinds = {t.strategy.engine_params["twin"]["kind"] for t in twins}
    assert "random_universe" in kinds
    assert "beta_matched" in kinds


def test_a_30m_book_gets_the_overnight_only_twin(db):
    """Lane D's systems check against a known answer."""
    path, conn = db
    _, twins = PB.create(make_strategy(), cadence="30m", origin="night_job",
                         bars=synthetic_bars(), conn=conn)
    kinds = {t.strategy.engine_params["twin"]["kind"] for t in twins}
    assert "overnight_only" in kinds


def test_the_random_twins_draw_is_deterministic_and_recorded():
    bars = synthetic_bars()
    s = make_strategy()
    a = PB.make_twins(s, cadence="daily", bars=bars, asof=date.today())
    b = PB.make_twins(s, cadence="daily", bars=bars, asof=date.today())
    ra = next(t for t in a if t.strategy.engine_params["twin"]["kind"] == "random_universe")
    rb = next(t for t in b if t.strategy.engine_params["twin"]["kind"] == "random_universe")
    assert ra.book_id == rb.book_id
    assert ra.strategy.engine_params["twin"]["seed"] == rb.strategy.engine_params["twin"]["seed"]
    assert ra.strategy.engine_params["symbols"] == rb.strategy.engine_params["symbols"]


def test_a_beta_twin_that_could_not_be_matched_says_so():
    """The failure that must never be silent: a random draw reported as the
    stricter control."""
    bars = synthetic_bars(n=20)          # far fewer than BETA_MIN_SESSIONS
    twins = PB.make_twins(make_strategy(), cadence="daily", bars=bars,
                          asof=date.today())
    beta = next(t for t in twins
                if t.strategy.engine_params["twin"]["kind"] == "beta_matched")
    assert "UNMATCHED" in beta.strategy.engine_params["twin"]
    assert "NOT MATCHED" in beta.control_construction


# ── the write path is sacred ───────────────────────────────────────────────


def test_the_reference_lanes_rows_are_byte_identical_before_and_after(db):
    path, conn = db
    before = lane_rows(conn)
    assert len(before) == 4 * 3
    book, twins = PB.create(make_strategy(), cadence="daily", origin="night_job",
                            bars=synthetic_bars(), conn=conn)
    # and a mark, under the namespaced portfolio_id
    from backend.db import insert_nav
    for b in [book, *twins]:
        insert_nav(conn, b.book_id, date.today().isoformat(), 100_000.0,
                   b.strategy.fingerprint,
                   datetime.now(timezone.utc).isoformat(timespec="seconds"))
    after = lane_rows(conn)
    assert after == before, "a book touched a reference lane's NAV rows"
    # the book's own rows exist, in their own namespace
    ns = PB.nav_series(conn=conn)
    assert set(ns) == {b.book_id for b in [book, *twins]}
    assert all(k.startswith("book:") for k in ns)


def test_the_fleet_endpoint_does_not_render_books_as_lanes():
    """A book is never shown without its twin (B3), and /fleet has no twin
    column — so the book namespace is excluded there BY NAME."""
    import inspect

    from backend.routers import control
    src = inspect.getsource(control._nav_series)
    assert "is_book_id" in src or "BOOK_PREFIX" in src, (
        "control._nav_series reads every paper_nav row; without an explicit "
        "exclusion a book would appear on the fleet table with no twin beside it")
