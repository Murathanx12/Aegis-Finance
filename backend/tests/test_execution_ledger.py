"""A ledger of fills makes captured edge look better than it was.

The outcomes that cost the most money are the ones that produce no fill: the
order that never filled, the half fill, the broker and the book disagreeing
about what was traded. A ledger built from fills contains none of them, and
every one of these tests exists because omission is the failure mode here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.services.portfolio_intelligence import execution_ledger as EL
from backend.services.portfolio_intelligence import paper_broker_targets as T

UTC = timezone.utc
TARGET = T.parse_target("arena:CURRENT_BEST_v1")


def _submit(tmp_path, trades, decided_for="2026-08-24", when=None):
    return EL.record_submission(
        TARGET, trades, decided_for=decided_for, basis="intent",
        submitted_at=when or datetime.now(UTC) - timedelta(days=1),
        root=tmp_path)


def _stub_broker(monkeypatch, orders):
    monkeypatch.setattr(EL, "_broker_orders", lambda target, since: orders)


def _stub_internal(monkeypatch, fills):
    monkeypatch.setattr(EL, "_internal_fills",
                        lambda book_id, dd, arena_root=None: fills)


# ── the record exists before the outcome does ──────────────────────────────


def test_a_submission_is_recorded_before_it_resolves(tmp_path):
    out = _submit(tmp_path, [{"symbol": "NVDA", "action": "open", "qty": 10}])
    assert out["written"] == 1
    rows = EL._read(TARGET.target_id, tmp_path)
    assert rows[0]["state"] == "PENDING"
    assert rows[0]["intended_qty"] == 10
    assert rows[0]["decided_for"] == "2026-08-24"


def test_the_pending_row_survives_reconciliation(tmp_path, monkeypatch):
    """Append-only: the intention stays on disk next to the outcome."""
    _submit(tmp_path, [{"symbol": "NVDA", "action": "open", "qty": 10}])
    _stub_broker(monkeypatch, {"NVDA": [{
        "id": "o1", "status": "filled", "filled_qty": "10",
        "filled_avg_price": "100.0", "filled_at": "2026-08-25T13:30:00Z"}]})
    _stub_internal(monkeypatch, {"NVDA": {
        "fill_price": 100.0, "fill_date": "2026-08-25", "cost_usd": 5.0,
        "cost_bps": 5, "slippage_bps": 5}})
    EL.reconcile(TARGET, root=tmp_path)
    states = [r["state"] for r in EL._read(TARGET.target_id, tmp_path)]
    assert states == ["PENDING", "FILLED"]


# ── the outcomes a fill-based ledger would lose ────────────────────────────


def test_an_order_that_never_filled_is_recorded_not_dropped(tmp_path,
                                                            monkeypatch):
    """The most expensive outcome there is, and it leaves no fill to record."""
    _submit(tmp_path, [{"symbol": "NVDA", "action": "open", "qty": 10}],
            when=datetime.now(UTC) - timedelta(days=EL.UNRESOLVED_AFTER_DAYS + 1))
    _stub_broker(monkeypatch, {})
    _stub_internal(monkeypatch, {})
    res = EL.reconcile(TARGET, root=tmp_path)
    assert res["n_never_filled"] == 1
    row = [r for r in EL._read(TARGET.target_id, tmp_path)
           if r["state"] == "NEVER_FILLED"][0]
    assert "never held" in row["note"]


def test_an_order_still_in_flight_is_left_pending(tmp_path, monkeypatch):
    """A day-old unfilled order is not yet a finding."""
    _submit(tmp_path, [{"symbol": "NVDA", "action": "open", "qty": 10}],
            when=datetime.now(UTC) - timedelta(hours=6))
    _stub_broker(monkeypatch, {})
    _stub_internal(monkeypatch, {})
    res = EL.reconcile(TARGET, root=tmp_path)
    assert res["status"] == "in_flight"
    assert all(r["state"] == "PENDING"
               for r in EL._read(TARGET.target_id, tmp_path))


def test_a_partial_fill_is_flagged_with_its_fraction(tmp_path, monkeypatch):
    _submit(tmp_path, [{"symbol": "NVDA", "action": "open", "qty": 10}])
    _stub_broker(monkeypatch, {"NVDA": [{
        "id": "o1", "status": "partially_filled", "filled_qty": "4",
        "filled_avg_price": "100.0", "filled_at": "2026-08-25T13:30:00Z"}]})
    _stub_internal(monkeypatch, {"NVDA": {
        "fill_price": 100.0, "fill_date": "2026-08-25", "cost_usd": 5.0,
        "cost_bps": 5, "slippage_bps": 5}})
    EL.reconcile(TARGET, root=tmp_path)
    row = [r for r in EL._read(TARGET.target_id, tmp_path)
           if r["state"] == "FILLED"][0]
    assert row["partial"] is True and row["fill_fraction"] == 0.4


def test_a_broker_fill_with_no_internal_fill_is_a_finding(tmp_path,
                                                          monkeypatch):
    """The two sides disagreeing about what was traded must not average away."""
    _submit(tmp_path, [{"symbol": "NVDA", "action": "open", "qty": 10}])
    _stub_broker(monkeypatch, {"NVDA": [{
        "id": "o1", "status": "filled", "filled_qty": "10",
        "filled_avg_price": "100.0", "filled_at": "2026-08-25T13:30:00Z"}]})
    _stub_internal(monkeypatch, {})
    EL.reconcile(TARGET, root=tmp_path)
    row = [r for r in EL._read(TARGET.target_id, tmp_path)
           if r["state"] == "FILLED"][0]
    assert row["internal_fill_price"] is None
    assert "disagree" in row["note"]


def test_an_unreadable_broker_is_not_an_execution_finding(tmp_path,
                                                          monkeypatch):
    """Otherwise a network outage writes a ledger full of missing fills."""
    _submit(tmp_path, [{"symbol": "NVDA", "action": "open", "qty": 10}])

    def _boom(target, since):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(EL, "_broker_orders", _boom)
    res = EL.reconcile(TARGET, root=tmp_path)
    assert res["status"] == "broker_unreadable"
    assert all(r["state"] == "PENDING"
               for r in EL._read(TARGET.target_id, tmp_path))


# ── the number the whole ledger exists to produce ──────────────────────────


def test_slippage_is_a_cost_when_positive_on_BOTH_sides():
    # bought above the assumed price -> cost
    assert EL._slippage_bps("open", 100.0, 101.0) == pytest.approx(100.0)
    # sold below the assumed price -> also a cost
    assert EL._slippage_bps("close", 100.0, 99.0) == pytest.approx(100.0)
    # bought below / sold above -> a gain, negative
    assert EL._slippage_bps("open", 100.0, 99.0) == pytest.approx(-100.0)
    assert EL._slippage_bps("close", 100.0, 101.0) == pytest.approx(-100.0)


def test_realized_slippage_is_compared_against_the_ASSUMED_cost(tmp_path,
                                                                monkeypatch):
    """The declared `cost_bps + slippage_bps` is an assumption with a number
    attached. This is the first thing in the repository that checks it."""
    _submit(tmp_path, [{"symbol": "NVDA", "action": "open", "qty": 10}])
    _stub_broker(monkeypatch, {"NVDA": [{
        "id": "o1", "status": "filled", "filled_qty": "10",
        "filled_avg_price": "100.30", "filled_at": "2026-08-25T13:30:00Z"}]})
    _stub_internal(monkeypatch, {"NVDA": {
        "fill_price": 100.0, "fill_date": "2026-08-25", "cost_usd": 5.0,
        "cost_bps": 5, "slippage_bps": 5}})   # assumed 10 bps all-in
    EL.reconcile(TARGET, root=tmp_path)
    row = [r for r in EL._read(TARGET.target_id, tmp_path)
           if r["state"] == "FILLED"][0]
    assert row["slippage_bps"] == pytest.approx(30.0)
    assert row["assumed_cost_bps"] == pytest.approx(10.0)
    # realized 30 vs assumed 10 -> the cost model was optimistic by 20 bps
    assert row["realized_vs_assumed_bps"] == pytest.approx(20.0)


def test_summary_reports_the_fill_rate_not_only_the_fills(tmp_path,
                                                          monkeypatch):
    old = datetime.now(UTC) - timedelta(days=EL.UNRESOLVED_AFTER_DAYS + 1)
    _submit(tmp_path, [{"symbol": "AAA", "action": "open", "qty": 10},
                       {"symbol": "BBB", "action": "open", "qty": 10}],
            when=old)
    _stub_broker(monkeypatch, {"AAA": [{
        "id": "o1", "status": "filled", "filled_qty": "10",
        "filled_avg_price": "101.0", "filled_at": "2026-08-25T13:30:00Z"}]})
    _stub_internal(monkeypatch, {"AAA": {
        "fill_price": 100.0, "fill_date": "2026-08-25", "cost_usd": 5.0,
        "cost_bps": 5, "slippage_bps": 5}})
    EL.reconcile(TARGET, root=tmp_path)
    s = EL.summary(TARGET.target_id, root=tmp_path)
    assert s["n_filled"] == 1 and s["n_never_filled"] == 1
    assert s["fill_rate"] == 0.5, (
        "captured edge computed over fills alone would ignore that half the "
        "orders never happened")


# ── health ─────────────────────────────────────────────────────────────────


def test_health_is_ABSENT_before_anything_is_submitted(tmp_path):
    assert EL.health(root=tmp_path / "nothing")["status"] == "ABSENT"


def test_health_is_DEGRADED_when_reconciliation_stops_running(tmp_path):
    _submit(tmp_path, [{"symbol": "NVDA", "action": "open", "qty": 10}],
            when=datetime.now(UTC) - timedelta(days=EL.UNRESOLVED_AFTER_DAYS + 2))
    h = EL.health(root=tmp_path)
    assert h["status"] == "DEGRADED"
    row = h["targets"][TARGET.target_id]
    assert row["n_stuck"] == 1 and "not running" in row["reason"]


# ── the bias guard ─────────────────────────────────────────────────────────
# Orders do not resolve at random. The ones that hang are the illiquid, the
# wide-spread and the never-filled, so a summary taken too early describes the
# easy subset and reads as GOOD execution precisely when execution was worst.


def test_captured_edge_is_refused_over_an_empty_ledger(tmp_path):
    with pytest.raises(EL.ExecutionLedgerRefused, match="empty"):
        EL.assert_captured_edge_reportable("arena:NOBODY", root=tmp_path)


def test_captured_edge_is_refused_while_nothing_has_resolved(tmp_path):
    _submit(tmp_path, [{"symbol": "NVDA", "action": "open", "qty": 10}])
    with pytest.raises(EL.ExecutionLedgerRefused, match="NONE"):
        EL.assert_captured_edge_reportable(TARGET.target_id, root=tmp_path)


def test_captured_edge_is_refused_while_too_many_hang(tmp_path, monkeypatch):
    old = datetime.now(UTC) - timedelta(days=EL.UNRESOLVED_AFTER_DAYS + 1)
    _submit(tmp_path, [{"symbol": "AAA", "action": "open", "qty": 10}], when=old)
    _stub_broker(monkeypatch, {"AAA": [{
        "id": "o1", "status": "filled", "filled_qty": "10",
        "filled_avg_price": "100.0", "filled_at": "2026-08-25T13:30:00Z"}]})
    _stub_internal(monkeypatch, {"AAA": {
        "fill_price": 100.0, "fill_date": "2026-08-25", "cost_usd": 5.0,
        "cost_bps": 5, "slippage_bps": 5}})
    EL.reconcile(TARGET, root=tmp_path)
    # now pile on unresolved submissions
    _submit(tmp_path, [{"symbol": f"X{i}", "action": "open", "qty": 1}
                       for i in range(8)])
    with pytest.raises(EL.ExecutionLedgerRefused, match="unresolved"):
        EL.assert_captured_edge_reportable(TARGET.target_id, root=tmp_path)


def test_captured_edge_reports_once_the_ledger_can_support_it(tmp_path,
                                                              monkeypatch):
    old = datetime.now(UTC) - timedelta(days=EL.UNRESOLVED_AFTER_DAYS + 1)
    _submit(tmp_path, [{"symbol": "AAA", "action": "open", "qty": 10}], when=old)
    _stub_broker(monkeypatch, {"AAA": [{
        "id": "o1", "status": "filled", "filled_qty": "10",
        "filled_avg_price": "100.20", "filled_at": "2026-08-25T13:30:00Z"}]})
    _stub_internal(monkeypatch, {"AAA": {
        "fill_price": 100.0, "fill_date": "2026-08-25", "cost_usd": 5.0,
        "cost_bps": 5, "slippage_bps": 5}})
    EL.reconcile(TARGET, root=tmp_path)
    got = EL.assert_captured_edge_reportable(TARGET.target_id, root=tmp_path)
    assert got["mean_slippage_bps"] == pytest.approx(20.0)
    assert got["mean_realized_minus_assumed_bps"] == pytest.approx(10.0)


def test_a_resolved_orders_pending_row_does_not_count_as_stuck(tmp_path,
                                                               monkeypatch):
    """The append-only bug: reconciliation leaves the PENDING row on disk, so
    counting rows-in-state-PENDING counts every resolved order forever. That
    made health go DEGRADED five days after the first successful reconcile and
    stay there, reporting a stuck pipeline that was working perfectly."""
    old = datetime.now(UTC) - timedelta(days=EL.UNRESOLVED_AFTER_DAYS + 3)
    _submit(tmp_path, [{"symbol": "AAA", "action": "open", "qty": 10}], when=old)
    _stub_broker(monkeypatch, {"AAA": [{
        "id": "o1", "status": "filled", "filled_qty": "10",
        "filled_avg_price": "100.0", "filled_at": "2026-08-25T13:30:00Z"}]})
    _stub_internal(monkeypatch, {"AAA": {
        "fill_price": 100.0, "fill_date": "2026-08-25", "cost_usd": 5.0,
        "cost_bps": 5, "slippage_bps": 5}})
    EL.reconcile(TARGET, root=tmp_path)

    h = EL.health(root=tmp_path)
    assert h["status"] == "ok", h["targets"][TARGET.target_id].get("reason")
    assert h["targets"][TARGET.target_id]["n_stuck"] == 0
    # and reconciling again must not re-resolve what is already resolved
    assert EL.reconcile(TARGET, root=tmp_path)["status"] == "nothing_pending"


def test_an_unconfigured_account_is_not_an_unreadable_broker(tmp_path,
                                                             monkeypatch):
    """Otherwise the nightly job logs an ERROR every pass while the account is
    simply not seeded yet, and a real outage is one line among many identical
    ones."""
    from backend.services.portfolio_intelligence import alpaca_mirror as AM

    _submit(tmp_path, [{"symbol": "NVDA", "action": "open", "qty": 10}])
    monkeypatch.setattr(AM, "alpaca_available", lambda *a, **k: False)

    def _never(*a, **k):
        raise AssertionError("the broker was called with no credentials")

    monkeypatch.setattr(EL, "_broker_orders", _never)
    res = EL.reconcile(TARGET, root=tmp_path)
    assert res["status"] == "not_configured" and res["n_pending"] == 1
