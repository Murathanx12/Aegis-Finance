"""Lane B5: a book decision mints a graded forecast, and so does its control.

The end-to-end property: run a synthetic book and its twin over five sessions,
and at the end there are rows in the ledger, they have outcomes, and a Brier was
computed against the twin's own realised mark — not against a number invented at
reporting time.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from backend.services import book_cadence as BC
from backend.services import book_forecasts as BF
from backend.services import paper_books as PB
from backend.services.belief_state import (Observable, SCHEMA_VERSION,
                                           read_predictions, resolve_all)
from backend.tests.book_helpers import make_strategy, seeded_db, synthetic_bars
from backend.strategy.contract import Construction, Signal


@pytest.fixture()
def db(tmp_path):
    conn = seeded_db(tmp_path / "aegis_pi.db")
    yield tmp_path / "aegis_pi.db", conn
    conn.close()


@pytest.fixture()
def bars():
    return synthetic_bars(n=300)


@pytest.fixture()
def ledger(tmp_path):
    return tmp_path / "predictions.jsonl"


@pytest.fixture(autouse=True)
def _no_migration(monkeypatch):
    from backend.services import belief_state as BS
    monkeypatch.setattr(BS, "_migrate_once", lambda: None)


def _seed(conn, bars, asof, cadence="daily"):
    s = make_strategy().with_(
        signal=Signal(name="mom_21", column="mom_21", direction=1),
        construction=Construction(rule="top_k", k=3, weighting="ew",
                                  max_single_name=0.5))
    return PB.create(s, cadence=cadence, origin="night_job",
                     origin_text="a synthetic book", bars=bars, asof=asof,
                     conn=conn)


# ── the probability convention ─────────────────────────────────────────────


def test_no_history_means_the_base_rate_exactly():
    """A book that has never been marked has no measured confidence, and 0.5
    is the honest number rather than a small edge invented from nothing."""
    ir, n = BF.trailing_ir([], [])
    assert ir is None and n == 0
    assert BF.probability_from_ir(ir) == BF.BASE_RATE


def test_one_paired_day_is_still_the_base_rate():
    """An IR from one observation has no sampling distribution behind it."""
    ir, n = BF.trailing_ir([("2026-03-02", 100.0), ("2026-03-03", 101.0)],
                           [("2026-03-02", 100.0), ("2026-03-03", 100.5)])
    assert ir is None
    assert BF.probability_from_ir(ir) == BF.BASE_RATE


def test_a_book_that_beat_its_twin_every_day_gets_a_probability_above_half():
    book = [("2026-03-0%d" % d, 100.0 * (1.01 ** (d - 1))) for d in range(1, 6)]
    twin = [("2026-03-0%d" % d, 100.0 * (1.00 ** (d - 1))) for d in range(1, 6)]
    ir, n = BF.trailing_ir(book, twin)
    assert n == 4 and ir is not None
    p = BF.probability_from_ir(ir)
    assert 0.5 < p <= 0.98
    # and the mirror: the twin's own row is 0.5 whatever the book did
    assert BF.probability_from_ir(BF.trailing_ir(twin, book)[0]) < 0.5


def test_the_probability_is_clipped_at_both_ends():
    assert BF.probability_from_ir(50.0) <= 0.98
    assert BF.probability_from_ir(-50.0) >= 0.02


# ── the rows ───────────────────────────────────────────────────────────────


def test_a_decision_writes_a_book_row_and_a_base_rate_row(db, bars, ledger):
    path, conn = db
    asof = BC.latest_bar_date(bars)
    book, twins = _seed(conn, bars, asof)
    rep = BC.run_pass("daily", conn=conn, bars=bars, today=asof,
                      write_receipt=False, predictions_path=ledger)
    assert rep["forecasts"]["n_rows"] == 2, rep["forecasts"]
    rows = read_predictions(ledger)
    assert len(rows) == 2
    engine = next(r for r in rows if r["specialist"].startswith("book:"))
    base = next(r for r in rows if r["specialist"] == "base_rate")

    assert engine["ticker"] == book.book_id
    assert engine["observable"] == Observable.BEATS_BENCHMARK.value
    assert engine["benchmark"] == twins[0].book_id
    assert engine["control_twin_id"] == twins[0].book_id
    assert engine["control_construction"]
    assert engine["model"] == "engine"
    assert engine["policy_hash"] == book.strategy.fingerprint
    assert engine["mechanism_id"] == BF.MECHANISM_ID
    assert engine["licence"] == "PRODUCT_EXPERIMENT"
    assert engine["horizon_days"] == PB.CADENCE_SESSIONS["daily"]
    assert engine["schema_version"] == SCHEMA_VERSION
    assert engine["era_tag"]
    assert base["probability"] == 0.5


def test_every_book_row_charges_costs_and_names_the_rate(db, bars, ledger):
    path, conn = db
    asof = BC.latest_bar_date(bars)
    book, _ = _seed(conn, bars, asof)
    BC.run_pass("daily", conn=conn, bars=bars, today=asof, write_receipt=False,
                predictions_path=ledger)
    for r in read_predictions(ledger):
        assert r["costs_charged"] is True
        assert r["cost_rate_bps"] == (book.strategy.costs.transaction_cost_bps
                                      + book.strategy.costs.slippage_bps)


def test_a_book_that_only_marked_mints_no_forecast(db, bars, ledger):
    """A decision nobody took must not accrue calibration."""
    path, conn = db
    asof = BC.latest_bar_date(bars)
    _seed(conn, bars, asof)
    BC.run_pass("daily", conn=conn, bars=bars, today=asof, write_receipt=False,
                predictions_path=ledger)
    n_first = len(read_predictions(ledger))
    rep = BC.run_pass("daily", conn=conn, bars=bars, today=asof,
                      write_receipt=False, predictions_path=ledger)
    assert not rep["decisions"]
    assert len(read_predictions(ledger)) == n_first


def test_a_twin_never_gets_its_own_book_row(db, bars, ledger):
    """A twin is a control, not a second book: giving it its own
    `beats_benchmark` row against a twin-of-a-twin would double-count it."""
    path, conn = db
    asof = BC.latest_bar_date(bars)
    _, twins = _seed(conn, bars, asof)
    BC.run_pass("daily", conn=conn, bars=bars, today=asof, write_receipt=False,
                predictions_path=ledger)
    tickers = {r["ticker"] for r in read_predictions(ledger)}
    assert not (tickers & {t.book_id for t in twins})


# ── the grading loop ───────────────────────────────────────────────────────


def test_five_sessions_end_in_a_graded_row_with_a_brier(db, bars, ledger):
    """The whole loop: mark, decide, forecast, mark again, grade."""
    import pandas as pd

    path, conn = db
    days = sorted(pd.Timestamp(d).date() for d in bars["date"].unique())[-5:]
    for d in days:
        BC.run_pass("daily", conn=conn, bars=bars, today=d, write_receipt=False,
                    predictions_path=ledger)
        if d == days[0]:
            _seed(conn, bars, d)          # created after the first empty pass
    rows = read_predictions(ledger)
    assert rows, "five daily passes over a live book should have minted rows"

    # the price frame is the books' own marked NAV -- neither id is a security
    series = PB.nav_series(conn=conn)
    frame = pd.DataFrame({
        k: pd.Series({pd.Timestamp(d): v for d, v in vals})
        for k, vals in series.items()}).sort_index()
    report = resolve_all(frame, ledger, today=days[-1] + timedelta(days=30))
    assert report["newly_resolved"] > 0, report

    graded = [r for r in read_predictions(ledger) if r.get("outcome") is not None]
    assert graded
    for r in graded:
        assert r["brier"] is not None
        assert 0.0 <= r["brier"] <= 1.0
        assert r["calibration_bucket"] is not None
        assert r["outcome"] in (0, 1)
    # vs_control was computed against the twin's own realised mark
    with_control = [r for r in graded if r.get("vs_control") is not None]
    assert with_control, [r.get("resolution_detail") for r in graded]
    r = with_control[0]
    assert r["vs_benchmark"] is not None
    assert abs(r["vs_control"] - r["vs_benchmark"]) < 1e-9, (
        "for a book row the benchmark IS the control twin; if these two "
        "differ the resolver priced two different series")


def test_an_absent_control_is_named_rather_than_left_null(ledger):
    """`vs_control` null because nothing was declared and `vs_control` null
    because the control could not be priced are different facts.

    Built directly rather than through a pass: a book row's `benchmark` IS its
    control twin, so an unpriceable twin stops the grade entirely (the benchmark
    leg refuses first) and this branch is unreachable from there. The branch
    that matters is a record whose control is a SEPARATE series from its
    benchmark — a scenario row, a rule row, anything M1 grades against a
    constructed control — and that is what this builds.
    """
    import pandas as pd

    from backend.services.belief_state import append, make_prediction

    made = "2026-03-02T21:00:00+00:00"
    rec = make_prediction(
        ticker="AAA", specialist="unit", observable=Observable.RETURN_SIGN,
        horizon_days=1, probability=0.6, thesis="t", counter_thesis="c",
        next_observable="n", model="engine", model_version="v",
        prompt="p", input_snapshot={}, made_at=made,
        control_twin_id="a_control_nobody_priced",
        control_construction="a control that exists only as a declaration")
    append([rec], ledger)

    idx = pd.date_range(start="2026-03-02", periods=10)
    frame = pd.DataFrame({"AAA": [100.0 + i for i in range(10)]}, index=idx)
    resolve_all(frame, ledger, today=pd.Timestamp("2026-04-02").date())

    graded = [r for r in read_predictions(ledger) if r.get("outcome") is not None]
    assert graded, "the record itself must still grade; only the comparison fails"
    row = graded[0]
    assert row["vs_control"] is None
    assert "vs_control" in row["resolution_detail"].get("control_note", "")
    assert "a_control_nobody_priced" in row["resolution_detail"]["control_note"]


def test_the_thesis_and_counter_thesis_are_written(db, bars, ledger):
    path, conn = db
    asof = BC.latest_bar_date(bars)
    book, twins = _seed(conn, bars, asof)
    BC.run_pass("daily", conn=conn, bars=bars, today=asof, write_receipt=False,
                predictions_path=ledger)
    engine = next(r for r in read_predictions(ledger)
                  if r["specialist"].startswith("book:"))
    assert book.book_id in engine["thesis"]
    assert twins[0].book_id in engine["counter_thesis"]
    assert json.loads(json.dumps(engine))          # the row is JSON, end to end
