"""Lane A3 — the daily review: the row is written BEFORE the call is shown.

Spec: `docs/research_notes/2026-09-12/spec_agency_intake.md` §3 and test T4.

The ordering is the whole section. A call whose `PredictionRecord` is not
already on disk, with an earlier `made_at` and a hash a reader can recompute,
is a call nobody can grade — so the review writes, reads back, hashes, and
only then returns. A holding whose row could not be written gets NO call.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.services import agency as A
from backend.services import belief_state as BS
from backend.services import book_cadence as BC
from backend.services import paper_books as PB
from backend.tests.book_helpers import make_strategy, seeded_db, synthetic_bars

ANSWERS = [3, 3, 2, 3, 2, 2, 1, 2]


@pytest.fixture()
def bars():
    return synthetic_bars(n=300)


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    p = tmp_path / "predictions.jsonl"
    monkeypatch.setattr(BS, "PREDICTIONS", p)
    monkeypatch.setattr(BS, "_migrate_once", lambda: None)
    monkeypatch.setattr(A, "DEFAULT_LEDGER", p)
    return p


@pytest.fixture()
def db(tmp_path, monkeypatch):
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


def held_book(conn, bars, *, origin="human_text", weights=None, nav=None):
    """A book with real positions, so the review has something to review."""
    asof = BC.latest_bar_date(bars)
    book, twins = PB.create(make_strategy(), cadence="daily", origin=origin,
                            origin_text="a sentence a human typed here",
                            ips_hash="a" * 16, bars=bars, asof=asof, conn=conn)
    symbols = sorted((weights or {"AAA": 0.5, "BBB": 0.5}))
    prices, _ = BC.latest_prices(bars, symbols, asof)
    equity = nav or 100_000.0
    shares = {s: (weights or {"AAA": 0.5, "BBB": 0.5})[s] * equity / prices[s]
              for s in symbols if s in prices}
    BC._write_positions(conn, book.book_id, shares, prices, "2026-01-01T00:00:00+00:00")
    return book, twins, asof


def mark(conn, book_id, rows):
    for d, nav in rows:
        conn.execute("INSERT OR REPLACE INTO paper_nav VALUES (?,?,?,?,?)",
                     (book_id, d, nav, "cfg", "now"))
    conn.commit()


# ------------------------------------------------------------ the vocabulary


def test_the_vocabulary_is_exactly_four_words():
    assert A.DECISIONS == ("hold", "sell", "buy_more", "trim")


@pytest.mark.parametrize("p,weight,expected", [
    (0.20, 0.05, "sell"),
    (0.50, 0.05, "hold"),
    (0.75, 0.05, "buy_more"),
    (0.75, 0.50, "trim"),
    (0.50, 0.50, "trim"),
    (0.10, 0.50, "sell"),      # a sell beats an overweight: it leaves entirely
])
def test_the_label_is_derived_from_the_probability_and_the_size(p, weight,
                                                                expected):
    got, why = A.decide_label(p, weight=weight, max_single_name=0.34)
    assert got == expected
    assert why


def test_a_sell_label_on_a_high_probability_is_refused():
    """§3.1: two numbers called 'the call' is a contract violation."""
    with pytest.raises(A.AgencyError, match="sell"):
        A._check_label("sell", 0.62, weight=0.05, max_single_name=0.34)


def test_a_trim_label_on_a_position_inside_its_cap_is_refused():
    with pytest.raises(A.AgencyError, match="OVERWEIGHT"):
        A._check_label("trim", 0.55, weight=0.05, max_single_name=0.34)


def test_a_buy_more_label_on_a_capped_position_is_refused():
    with pytest.raises(A.AgencyError):
        A._check_label("buy_more", 0.90, weight=0.80, max_single_name=0.34)


# ------------------------------------------------------- the five terms


def test_every_term_is_reported_including_the_zero_ones():
    out = A.probability_terms(ticker="AAA", price_path=[], twin_path=[],
                              drawdown_state={})
    names = [t["term"] for t in out["terms"]]
    assert names == ["trailing_ir_vs_twin", "calibrated_target_interval",
                     "book_drawdown_state", "typed_events",
                     "market_sensor_regime"]
    assert all(t["basis"] for t in out["terms"])


def test_with_no_inputs_the_probability_is_a_half():
    out = A.probability_terms(ticker="AAA", price_path=[], twin_path=[],
                              drawdown_state={})
    assert out["probability"] == pytest.approx(0.5, abs=1e-9)
    assert "CANNOT DETERMINE" in out["terms"][0]["basis"]


def test_the_typed_event_term_is_zero_by_declaration_not_by_omission():
    out = A.probability_terms(ticker="AAA", price_path=[], twin_path=[],
                              drawdown_state={}, n_typed_events=7)
    ev = next(t for t in out["terms"] if t["term"] == "typed_events")
    assert ev["n_events"] == 7
    assert ev["z"] == 0.0
    assert "ZERO BY DECLARATION" in ev["basis"]


def test_a_book_past_half_its_budget_tilts_the_call_down():
    state = {"drawdown": -0.15, "drawdown_budget": -0.20}
    out = A.probability_terms(ticker="AAA", price_path=[], twin_path=[],
                              drawdown_state=state)
    dd = next(t for t in out["terms"] if t["term"] == "book_drawdown_state")
    assert dd["z"] == A.DRAWDOWN_TILT_Z
    assert out["probability"] < 0.5


def test_no_llm_is_reachable_from_the_probability():
    """The number is Phi of declared terms. Nothing here calls a model."""
    import ast
    import inspect
    src = inspect.getsource(A.probability_terms)
    tree = ast.parse(src.lstrip())
    calls = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "complete" not in calls


# ------------------------------------------------------ the drawdown state


def test_no_marks_is_not_a_drawdown_of_zero(db, bars):
    path, conn = db
    book, _t, _a = held_book(conn, bars)
    state = A.drawdown_state(book, conn=conn)
    assert state["drawdown"] is None
    assert "not a drawdown of zero" in state["why"]


def test_the_peak_is_the_running_maximum(db, bars):
    path, conn = db
    book, _t, _a = held_book(conn, bars)
    mark(conn, book.book_id, [("2026-01-01", 100_000.0),
                              ("2026-01-02", 120_000.0),
                              ("2026-01-03", 108_000.0)])
    state = A.drawdown_state(book, conn=conn)
    assert state["peak_nav"] == 120_000.0
    assert state["peak_date"] == "2026-01-02"
    assert state["drawdown"] == pytest.approx(-0.1)
    assert state["breach"] is False          # the test book's budget is -0.25


# --------------------------------------------------- T4: the ordering rule


def test_the_row_is_written_and_readable_before_the_call_is_returned(
        db, bars, ledger):
    path, conn = db
    book, _t, asof = held_book(conn, bars)
    before = datetime.now().astimezone()
    calls = A.review(book, bars=bars, asof=asof, conn=conn, path=ledger)
    assert calls, "a book with two priced holdings owes two calls"
    rows = {r["prediction_id"]: r for r in BS.read_predictions(ledger)}
    for call in calls:
        assert call["prediction_id"] in rows, "the call has no row on disk"
        made = datetime.fromisoformat(call["row_made_at"])
        shown = datetime.fromisoformat(call["displayed_after_utc"])
        assert made <= shown, "the row must precede the display"
        assert made >= before.astimezone(made.tzinfo).replace(microsecond=0)


def test_the_row_hash_is_independently_recomputable(db, bars, ledger):
    """T4's second half: the persisted row IS the row the display used."""
    path, conn = db
    book, _t, asof = held_book(conn, bars)
    calls = A.review(book, bars=bars, asof=asof, conn=conn, path=ledger)
    rows = {r["prediction_id"]: r for r in BS.read_predictions(ledger)}
    for call in calls:
        assert A.row_hash(rows[call["prediction_id"]]) == call["row_hash"]


def test_a_holding_whose_row_refuses_gets_no_call(db, bars, ledger,
                                                  monkeypatch):
    """T4's third half: a refusal, not a silently ungraded display."""
    path, conn = db
    book, _t, asof = held_book(conn, bars)

    def _boom(**kw):
        raise ValueError("probability 1.7 is not a probability")

    monkeypatch.setattr(BS, "make_prediction", _boom)
    out = A.review_book(book, bars=bars, asof=asof, conn=conn, path=ledger)
    assert out["calls"] == []
    assert len(out["refused"]) >= 1
    assert all(r["shown"] is False for r in out["refused"])
    assert BS.read_predictions(ledger) == []


def test_a_book_with_no_twin_produces_no_call(db, bars, ledger):
    """B3, at the review: there is nothing for the probability to be ABOUT."""
    path, conn = db
    book, _t, asof = held_book(conn, bars)
    naked = PB.PaperBook(
        book_id=book.book_id, strategy=book.strategy, cadence=book.cadence,
        created_utc=book.created_utc, origin=book.origin,
        control_twin_ids=(), ips_hash=book.ips_hash)
    out = A.review_book(naked, bars=bars, asof=asof, conn=conn, path=ledger)
    assert out["calls"] == []
    assert any("twin" in r["reason"] for r in out["refused"])


def test_every_call_names_its_benchmark_twin(db, bars, ledger):
    path, conn = db
    book, twins, asof = held_book(conn, bars)
    for call in A.review(book, bars=bars, asof=asof, conn=conn, path=ledger):
        assert call["benchmark_twin"] == twins[0].book_id


def test_the_second_review_carries_the_belief_change(db, bars, ledger):
    path, conn = db
    book, _t, asof = held_book(conn, bars)
    first = A.review(book, bars=bars, asof=asof, conn=conn, path=ledger)
    assert all(c["prior"] is None for c in first)
    assert all("first review" in c["prior_basis"] for c in first)
    mark(conn, book.book_id, [("2026-01-01", 100_000.0)])
    second = A.review(book, bars=bars, asof=asof, conn=conn, path=ledger)
    assert second, "the second pass still owes a call per holding"
    assert all(c["prior"] is not None for c in second)
    assert all(c["belief_change"] is not None for c in second)


def test_the_rows_carry_the_cost_rate_and_the_licence(db, bars, ledger):
    path, conn = db
    book, _t, asof = held_book(conn, bars)
    A.review(book, bars=bars, asof=asof, conn=conn, path=ledger)
    for r in BS.read_predictions(ledger):
        assert r["costs_charged"] is True
        assert r["cost_rate_bps"] == pytest.approx(6.0)
        assert r["licence"] == "PRODUCT_EXPERIMENT"
        assert r["mechanism_id"] == A.REVIEW_MECHANISM
        assert r["control_twin_id"] and r["control_construction"]


def test_the_horizon_is_a_declared_one(db, bars, ledger):
    path, conn = db
    book, _t, asof = held_book(conn, bars)
    A.review(book, bars=bars, asof=asof, conn=conn, path=ledger)
    for r in BS.read_predictions(ledger):
        assert r["horizon_days"] in BS.HORIZONS


# ------------------------------------------------------------ review_all


def test_only_the_books_a_human_holds_are_reviewed(db, bars, ledger):
    path, conn = db
    held_book(conn, bars, origin="human_text")
    out = A.review_all(bars=bars, asof=BC.latest_bar_date(bars), conn=conn,
                       path=ledger)
    assert out["n_books"] == 1
    assert out["reviewed_origins"] == ["human_text"]
    assert out["limits"]


def test_a_night_job_book_is_not_reviewed(db, bars, ledger):
    path, conn = db
    held_book(conn, bars, origin="night_job")
    out = A.review_all(bars=bars, asof=BC.latest_bar_date(bars), conn=conn,
                       path=ledger)
    assert out["n_books"] == 0
    assert out["n_calls"] == 0


# ------------------------------------------------------ the morning step


def test_the_step_is_declared_with_a_handler():
    from backend.services import morning as M
    assert "agency_review" in [s for s, _ in M.STEPS]
    assert "agency_review" in M._HANDLERS
    steps = [s for s, _ in M.STEPS]
    assert steps.index("agency_review") > steps.index("mark_books")
    assert steps.index("agency_review") < steps.index("grade")


def test_the_step_names_every_call_and_its_row_id(db, bars, ledger, tmp_path,
                                                  monkeypatch):
    from backend.services import morning as M
    path, conn = db
    held_book(conn, bars)
    monkeypatch.setattr(PB, "load_bars", lambda *a, **k: bars)
    receipt = M.run_morning(today=BC.latest_bar_date(bars), do_network=False,
                            predictions_path=ledger, out_dir=tmp_path / "m")
    row = next(s for s in receipt["steps"] if s["step"] == "agency_review")
    assert row["status"] == "ok", row
    assert row["n_calls"] >= 1
    ids = {r["prediction_id"] for r in row["calls"]}
    written = {r["prediction_id"] for r in BS.read_predictions(ledger)
               if r["specialist"] == A.SPECIALIST}
    assert ids and ids <= written


def test_no_held_book_is_nothing_to_do_and_says_why(db, bars, ledger, tmp_path,
                                                    monkeypatch):
    from backend.services import morning as M
    monkeypatch.setattr(PB, "load_bars", lambda *a, **k: bars)
    receipt = M.run_morning(today=date.today(), do_network=False,
                            predictions_path=ledger, out_dir=tmp_path / "m")
    row = next(s for s in receipt["steps"] if s["step"] == "agency_review")
    assert row["status"] == "nothing_to_do"
    assert "human_text" in row["reason"]


def test_absent_bars_are_a_refusal_naming_the_input(db, ledger, tmp_path,
                                                    monkeypatch):
    from backend.services import morning as M

    def _no_bars(*a, **k):
        raise PB.BookError("no local bars at backend/data/.../bars.parquet")

    monkeypatch.setattr(PB, "load_bars", _no_bars)
    receipt = M.run_morning(today=date.today(), do_network=False,
                            predictions_path=ledger, out_dir=tmp_path / "m")
    row = next(s for s in receipt["steps"] if s["step"] == "agency_review")
    assert row["status"] == "refused"
    assert "bars" in row["reason"]


# ---------------------------------------------------------------- the route


def test_the_review_route_reads_the_receipt_rather_than_recomputing(
        db, bars, ledger, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.services import morning as M
    path, conn = db
    held_book(conn, bars)
    monkeypatch.setattr(PB, "load_bars", lambda *a, **k: bars)
    out_dir = tmp_path / "m"
    monkeypatch.setattr(M, "MORNING_DIR", out_dir)
    day = BC.latest_bar_date(bars)
    M.run_morning(today=day, do_network=False, predictions_path=ledger,
                  out_dir=out_dir)
    body = TestClient(app).get(f"/api/control/agency/review?day={day}").json()
    assert body["ran"] is True
    assert body["n_calls"] >= 1
    assert body["vocabulary"] == list(A.DECISIONS)
    assert body["limits"]


def test_the_route_says_the_morning_has_not_run_rather_than_404(tmp_path,
                                                                monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.services import morning as M
    monkeypatch.setattr(M, "MORNING_DIR", tmp_path / "empty")
    r = TestClient(app).get("/api/control/agency/review?day=2026-01-01")
    assert r.status_code == 200
    assert r.json()["ran"] is False
