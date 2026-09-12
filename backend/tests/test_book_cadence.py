"""Lane B4: the cadence pass marks, decides, refuses by name, and says so.

The four properties that are worth a test rather than a comment:

1. a pass with nothing to do writes "nothing to do" (invariant 15);
2. a signal the selector cannot compute is a REFUSAL on the receipt, never a
   substituted ranking — a NAV from a different signal than the contract
   declares belongs to a strategy nobody wrote down;
3. a holding that cannot be priced stops the mark for that book entirely,
   because a NAV missing a position reports a loss the book did not take;
4. the pass never touches a reference lane's `paper_nav` row.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.services import book_cadence as BC
from backend.services import paper_books as PB
from backend.tests.test_paper_books import (REFERENCE_LANES, _lane_rows, db,  # noqa: F401
                                            make_strategy, synthetic_bars)
from backend.strategy.contract import Construction, Signal


@pytest.fixture()
def bars():
    return synthetic_bars(n=300)


@pytest.fixture()
def asof(bars):
    return BC.latest_bar_date(bars)


def _seed(conn, bars, asof, *, cadence="daily", signal="mom_21",
          rule="top_k", k=3, engine_params=None):
    s = make_strategy()
    s = s.with_(signal=Signal(name=signal, column=signal, direction=1),
                construction=Construction(rule=rule, k=k, weighting="ew",
                                          max_single_name=0.5),
                engine_params=dict(engine_params or {}))
    return PB.create(s, cadence=cadence, origin="night_job", bars=bars,
                     asof=asof, conn=conn)


# ── the pass ───────────────────────────────────────────────────────────────


def test_a_pass_with_no_books_says_nothing_to_do(db, bars, asof, tmp_path,
                                                 monkeypatch):
    path, conn = db
    monkeypatch.setattr(BC, "receipt_dir", lambda: tmp_path / "receipts")
    rep = BC.run_pass("daily", conn=conn, bars=bars, today=asof)
    assert rep["nothing_to_do"] is True
    assert rep["reason"]
    assert rep["books_considered"] == 0
    # the receipt exists even though nothing happened
    assert (tmp_path / "receipts").exists()
    assert rep["receipt_path"].endswith("_daily.json")


def test_a_pass_marks_every_book_and_its_twins(db, bars, asof, tmp_path,
                                               monkeypatch):
    path, conn = db
    monkeypatch.setattr(BC, "receipt_dir", lambda: tmp_path / "receipts")
    book, twins = _seed(conn, bars, asof)
    rep = BC.run_pass("daily", conn=conn, bars=bars, today=asof)
    marked = {m["book_id"] for m in rep["marked"]}
    assert book.book_id in marked
    assert {t.book_id for t in twins} <= marked
    assert rep["nothing_to_do"] is False
    series = PB.nav_series(conn=conn)
    assert book.book_id in series and series[book.book_id]


def test_the_book_and_its_twin_both_decide(db, bars, asof, tmp_path, monkeypatch):
    path, conn = db
    monkeypatch.setattr(BC, "receipt_dir", lambda: tmp_path / "receipts")
    book, twins = _seed(conn, bars, asof)
    rep = BC.run_pass("daily", conn=conn, bars=bars, today=asof)
    decided = {d["book_id"] for d in rep["decisions"]}
    assert book.book_id in decided
    random_twin = next(t for t in twins
                       if t.strategy.engine_params["twin"]["kind"] == "random_universe")
    assert random_twin.book_id in decided, (
        "a control that never decides is not a control, it is a flat line")


def test_costs_are_charged_on_every_decision(db, bars, asof, tmp_path, monkeypatch):
    path, conn = db
    monkeypatch.setattr(BC, "receipt_dir", lambda: tmp_path / "receipts")
    book, _ = _seed(conn, bars, asof)
    rep = BC.run_pass("daily", conn=conn, bars=bars, today=asof)
    row = next(d for d in rep["decisions"] if d["book_id"] == book.book_id)
    assert row["cost_rate_bps"] > 0
    assert row["cost_usd"] > 0
    assert row["traded_notional"] > 0


def test_an_unsupported_signal_is_refused_by_name_not_substituted(
        db, bars, asof, tmp_path, monkeypatch):
    path, conn = db
    monkeypatch.setattr(BC, "receipt_dir", lambda: tmp_path / "receipts")
    book, _ = _seed(conn, bars, asof, signal="a_signal_nobody_implemented")
    rep = BC.run_pass("daily", conn=conn, bars=bars, today=asof)
    refused = [r for r in rep["refused"] if r["book_id"] == book.book_id]
    assert refused, "the book should be refused at the decide stage"
    assert "a_signal_nobody_implemented" in refused[0]["reason"]
    assert not [d for d in rep["decisions"] if d["book_id"] == book.book_id]
    # and it IS still marked: a book that cannot decide still has a NAV
    assert [m for m in rep["marked"] if m["book_id"] == book.book_id]


def test_a_book_whose_holding_cannot_be_priced_is_not_marked_at_all(
        db, bars, asof, tmp_path, monkeypatch):
    path, conn = db
    monkeypatch.setattr(BC, "receipt_dir", lambda: tmp_path / "receipts")
    book, _ = _seed(conn, bars, asof)
    BC.run_pass("daily", conn=conn, bars=bars, today=asof)
    # plant a holding no panel can price
    conn.execute("INSERT INTO paper_positions "
                 "(portfolio_id, ticker, shares, cost_basis, opened_at, closed_at) "
                 "VALUES (?,?,?,?,?,NULL)",
                 (book.book_id, "NOSUCHTICKER", 10.0, 1.0, "2026-01-01"))
    conn.commit()
    nxt = asof + timedelta(days=1)
    rep = BC.run_pass("daily", conn=conn, bars=bars, today=nxt)
    refused = [r for r in rep["refused"]
               if r["book_id"] == book.book_id and r["stage"] == "mark"]
    assert refused and "NOSUCHTICKER" in refused[0]["reason"]
    assert not [m for m in rep["marked"] if m["book_id"] == book.book_id]


def test_the_pass_does_not_touch_a_reference_lane(db, bars, asof, tmp_path,
                                                  monkeypatch):
    path, conn = db
    monkeypatch.setattr(BC, "receipt_dir", lambda: tmp_path / "receipts")
    before = _lane_rows(conn)
    _seed(conn, bars, asof)
    BC.run_pass("daily", conn=conn, bars=bars, today=asof)
    assert _lane_rows(conn) == before


# ── the cadence clock ──────────────────────────────────────────────────────


@pytest.mark.parametrize("cadence,d0,d1,expect", [
    ("daily", date(2026, 3, 2), date(2026, 3, 2), False),
    ("daily", date(2026, 3, 2), date(2026, 3, 3), True),
    ("weekly", date(2026, 3, 2), date(2026, 3, 5), False),     # same ISO week
    ("weekly", date(2026, 3, 2), date(2026, 3, 9), True),
    ("monthly", date(2026, 3, 2), date(2026, 3, 31), False),
    ("monthly", date(2026, 3, 2), date(2026, 4, 1), True),
    ("quarterly", date(2026, 3, 2), date(2026, 3, 31), False),
    ("quarterly", date(2026, 3, 2), date(2026, 4, 1), True),
])
def test_the_period_key_decides_when_a_book_decides(cadence, d0, d1, expect):
    changed = BC._period_key(cadence, d0) != BC._period_key(cadence, d1)
    assert changed is expect


def test_a_monthly_book_marks_daily_but_decides_once(db, bars, asof, tmp_path,
                                                     monkeypatch):
    """B4's own wording: a quarterly book marks daily but DECIDES quarterly."""
    path, conn = db
    monkeypatch.setattr(BC, "receipt_dir", lambda: tmp_path / "receipts")
    book, _ = _seed(conn, bars, asof, cadence="monthly")
    first = BC.run_pass("monthly", conn=conn, bars=bars, today=asof)
    second = BC.run_pass("monthly", conn=conn, bars=bars, today=asof)
    assert [d for d in first["decisions"] if d["book_id"] == book.book_id]
    assert not [d for d in second["decisions"] if d["book_id"] == book.book_id]
    assert [m for m in second["marked"] if m["book_id"] == book.book_id]


# ── granularity is said, not assumed ───────────────────────────────────────


def test_a_30m_book_says_which_granularity_it_was_marked_at(db, bars, asof,
                                                            tmp_path, monkeypatch):
    path, conn = db
    monkeypatch.setattr(BC, "receipt_dir", lambda: tmp_path / "receipts")
    _seed(conn, bars, asof, cadence="30m")
    rep = BC.run_pass("30m", conn=conn, bars=bars, today=asof)
    assert rep["granularity"] == "daily_close"
    assert rep["intraday_bars_available"] is False
    assert "minute bars do not exist" in rep["granularity_note"]


def test_the_overnight_twin_is_marked_on_its_own_leg(db, bars, asof, tmp_path,
                                                     monkeypatch):
    """Running it through the close-to-close mark would silently turn it into
    buy-and-hold, which is the exact thing it exists to differ from."""
    path, conn = db
    monkeypatch.setattr(BC, "receipt_dir", lambda: tmp_path / "receipts")
    _, twins = _seed(conn, bars, asof, cadence="30m")
    overnight = next(t for t in twins
                     if t.strategy.engine_params["twin"]["kind"] == "overnight_only")
    rep = BC.run_pass("30m", conn=conn, bars=bars, today=asof)
    row = next(m for m in rep["marked"] if m["book_id"] == overnight.book_id)
    assert "overnight" in row["granularity"]
    assert "overnight_return" in row


# ── the abstention book ────────────────────────────────────────────────────


def test_threshold_coverage_abstains_to_cash_when_nothing_clears(db, bars, asof):
    path, conn = db
    book, _ = _seed(conn, bars, asof, rule="threshold_coverage",
                    engine_params={"abstain": {"min_signal": 99.0,
                                               "min_names": 1,
                                               "fallback": BC.CASH}})
    weights, detail = BC.decide_weights(book, bars, asof)
    assert weights == {}
    assert detail["abstained"] is True
    assert detail["n_cleared"] == 0


def test_threshold_coverage_acts_when_the_threshold_is_cleared(db, bars, asof):
    path, conn = db
    book, _ = _seed(conn, bars, asof, rule="threshold_coverage",
                    engine_params={"abstain": {"min_signal": -99.0,
                                               "min_names": 1,
                                               "fallback": BC.CASH}})
    weights, detail = BC.decide_weights(book, bars, asof)
    assert weights, "the book must act once names clear — otherwise the first "\
                    "test passes for the wrong reason"
    assert detail.get("abstained") is not True


def test_threshold_coverage_without_a_threshold_is_refused(db, bars, asof):
    path, conn = db
    book, _ = _seed(conn, bars, asof, rule="threshold_coverage")
    with pytest.raises(BC.UnsupportedSignal, match="min_signal"):
        BC.decide_weights(book, bars, asof)


# ── the selector honours the contract ──────────────────────────────────────


def test_the_selector_honours_k_and_the_single_name_cap(db, bars, asof):
    path, conn = db
    book, _ = _seed(conn, bars, asof, k=2)
    weights, _ = BC.decide_weights(book, bars, asof)
    assert len(weights) == 2
    assert max(weights.values()) <= book.strategy.construction.max_single_name + 1e-9
    assert abs(sum(weights.values()) - book.strategy.construction.gross_cap) < 1e-9


def test_direction_minus_one_buys_the_other_end(db, bars, asof):
    path, conn = db
    book, _ = _seed(conn, bars, asof, signal="mom_21", k=2)
    up, _ = BC.decide_weights(book, bars, asof)
    down_book = book.__class__(
        **{**book.__dict__,
           "strategy": book.strategy.with_(
               signal=Signal(name="mom_21", column="mom_21", direction=-1))})
    down, _ = BC.decide_weights(down_book, bars, asof)
    assert set(up) != set(down)
