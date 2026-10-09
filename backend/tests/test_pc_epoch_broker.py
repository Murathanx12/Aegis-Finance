"""Offline transport checks for the PC epoch's actual broker adapter."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import pc_broker as PB
from backend.services import pc_policy_epoch as PE
from backend.services.pc_epoch_broker import PaperEpochBroker


@pytest.fixture(autouse=True)
def _approved_offline_account(monkeypatch):
    monkeypatch.setattr(PE, "EXPECTED_ACCOUNT_FINGERPRINT",
                        PE.account_fingerprint("offline-account"))


class FakeTransport:
    BrokerError = PB.BrokerError

    def __init__(self, tmp_path: Path):
        self.LEASE_PATH = tmp_path / "lease.json"
        opened = datetime.now(timezone.utc) - timedelta(minutes=2)
        self.LEASE_PATH.write_text(json.dumps({
            "open": True, "owner": "sim_run offline-session",
            "session_nonce": "offline-nonce", "pid": os.getpid(),
            "process_birth_utc": PB._process_birth_utc(os.getpid()),
            "account_number": "offline-account", "opened": opened.isoformat(),
        }), encoding="utf-8")
        self.equity = "100000"
        self.cash = "100000"
        self.position_rows = []
        self.open_rows = []
        self.history = []
        self.lookup = None
        self.stock_post = 0

    def _host(self):
        return PE.PAPER_HOST

    def account(self):
        return {"account_number": "offline-account", "equity": self.equity,
                "cash": self.cash, "long_market_value": "0"}

    def positions(self):
        return list(self.position_rows)

    def orders(self, *, status, limit, before_order_id=None):
        if status == "open":
            return list(self.open_rows)
        if before_order_id is None:
            return list(self.history[:limit])
        index = next(i for i, o in enumerate(self.history)
                     if o["id"] == before_order_id)
        return list(self.history[index + 1:index + 1 + limit])

    def order_by_client_id(self, client_id):
        if self.lookup is None:
            raise PB.BrokerError("GET /v2/orders:by_client_order_id -> HTTP 404")
        return self.lookup

    def clock(self):
        return {"is_open": True}

    def fill_activities(self, order_id, *, page_token=None):
        return []

    def submit_epoch_stock(self, **kwargs):
        self.stock_post += 1
        return {"id": "offline-order", **kwargs}


def test_adapter_404_is_unknown_and_foreign_history_is_visible(tmp_path):
    fake = FakeTransport(tmp_path)
    adapter = PaperEpochBroker(fake)
    assert adapter.order_by_client_id("absent") is None
    newer = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    fake.history = [{"id": "foreign-order", "client_order_id": "foreign",
                     "submitted_at": newer}]
    evidence = adapter.evidence(known_client_ids={"known"})
    assert len(evidence["foreign_orders"]) == 1
    with pytest.raises(PE.EpochRefused, match="foreign"):
        PE._identity(evidence, session_id="offline-session", nonce="offline-nonce")


def test_adapter_rejects_snapshot_race_and_missing_durable_boundary(tmp_path):
    fake = FakeTransport(tmp_path)
    adapter = PaperEpochBroker(fake)
    original = fake.orders
    calls = 0

    def racing_orders(**kwargs):
        nonlocal calls
        if kwargs["status"] == "open":
            calls += 1
            if calls == 2:
                return [{"id": "late", "status": "new", "filled_qty": "0"}]
        return original(**kwargs)

    fake.orders = racing_orders
    with pytest.raises(PE.EpochRefused, match="snapshot raced"):
        adapter.evidence(known_client_ids=set())
    fake.orders = original
    intent = {"status": "INTENT_PERSISTED", "policy_epoch_sha256": "epoch"}
    journal = {"state": "ACTIVE", "content_sha256": "epoch",
               "stock_intents": [intent]}
    with pytest.raises(PE.EpochRefused, match="durable epoch boundary"):
        adapter.submit_stock_order(intent=intent, journal=journal,
                                   minimum_cash_buffer=0.01, max_name_frac=0.12,
                                   max_adv_participation=0.02)
    assert fake.stock_post == 0
    intent.update(status="SUBMIT_UNKNOWN", symbol="T00", side="buy", qty="1",
                  client_order_id="aegispc-s" + "0" * 20,
                  median_dollar_vol="1000000")
    journal.update(session_id="offline-session", nonce="offline-nonce",
                   account_fingerprint=PE.account_fingerprint("offline-account"))
    response = adapter.submit_stock_order(intent=intent, journal=journal,
                                          minimum_cash_buffer=0.01,
                                          max_name_frac=0.12,
                                          max_adv_participation=0.02)
    assert response["id"] == "offline-order" and fake.stock_post == 1


@pytest.mark.parametrize("quote,qty,sigma", [
    (1000.0, 15, 0.02), (float("nan"), 15, 0.02),
    (float("inf"), 15, 0.02), (True, 15, 0.02),
    (100.0, 100, 0.4),
])
def test_final_stock_boundary_rejects_jump_and_nonfinite_quote(tmp_path, monkeypatch,
                                                                quote, qty, sigma):
    lease = {"open": True, "owner": "sim_run offline-session",
             "session_nonce": "offline-nonce", "pid": os.getpid(),
             "process_birth_utc": PB._process_birth_utc(os.getpid()),
             "account_number": "offline-account"}
    path = tmp_path / "lease.json"
    path.write_text(json.dumps(lease), encoding="utf-8")
    monkeypatch.setattr(PB, "LEASE_PATH", path)
    monkeypatch.setattr(PB, "STATE_DIR", tmp_path)
    monkeypatch.setattr(PB, "_host", lambda: PE.PAPER_HOST)
    monkeypatch.setattr(PB, "account", lambda: {
        "account_number": "offline-account", "equity": "100000",
        "cash": "100000", "long_market_value": "0"})
    monkeypatch.setattr(PB, "positions", lambda: [])
    monkeypatch.setattr(PB, "orders", lambda **_: [])
    monkeypatch.setattr(PB, "last_prices", lambda _: {"T00": quote})
    monkeypatch.setattr(PB, "clock", lambda: {"is_open": True})
    posts = []
    monkeypatch.setattr(PB, "_call", lambda *a, **k: posts.append(k) or {"id": "fake"})
    with pytest.raises(PB.BrokerError):
        PB.submit_epoch_stock(
            symbol="T00", side="buy", qty=qty,
            client_order_id="aegispc-s" + "1" * 20,
            session_id="offline-session", session_nonce="offline-nonce",
            account_fingerprint=PE.account_fingerprint("offline-account"),
            minimum_cash_buffer=0.01, median_dollar_vol=1_000_000,
            planned_price=1000.0 if quote == 1000.0 else 100.0,
            max_name_frac=0.12, max_adv_participation=0.02,
            sleeve="REVISION_FLOW", risk_sigmas={"T00": sigma},
            revision_members=[f"T{i:02d}" for i in range(20)],
            probe_custody_symbols=[], starting_positions={})
    assert posts == []


def test_final_stock_boundary_rejects_other_position_race(tmp_path, monkeypatch):
    lease = {"open": True, "owner": "sim_run offline-session",
             "session_nonce": "offline-nonce", "pid": os.getpid(),
             "process_birth_utc": PB._process_birth_utc(os.getpid()),
             "account_number": "offline-account"}
    path = tmp_path / "lease.json"
    path.write_text(json.dumps(lease), encoding="utf-8")
    monkeypatch.setattr(PB, "LEASE_PATH", path)
    monkeypatch.setattr(PB, "STATE_DIR", tmp_path)
    monkeypatch.setattr(PB, "_host", lambda: PE.PAPER_HOST)
    monkeypatch.setattr(PB, "account", lambda: {
        "account_number": "offline-account", "equity": "100000",
        "cash": "99000", "long_market_value": "1000"})
    monkeypatch.setattr(PB, "positions", lambda: [
        {"symbol": "T01", "qty": "10", "market_value": "1000"}])
    monkeypatch.setattr(PB, "orders", lambda **_: [])
    monkeypatch.setattr(PB, "last_prices", lambda _: {"T00": 100.0})
    monkeypatch.setattr(PB, "clock", lambda: {"is_open": True})
    posts = []
    monkeypatch.setattr(PB, "_call", lambda *a, **k: posts.append(k) or {"id": "fake"})
    with pytest.raises(PB.BrokerError, match="holdings changed"):
        PB.submit_epoch_stock(
            symbol="T00", side="buy", qty=1,
            client_order_id="aegispc-s" + "1" * 20,
            session_id="offline-session", session_nonce="offline-nonce",
            account_fingerprint=PE.account_fingerprint("offline-account"),
            minimum_cash_buffer=0.01, median_dollar_vol=1_000_000,
            planned_price=100, max_name_frac=0.12, max_adv_participation=0.02,
            sleeve="REVISION_FLOW", risk_sigmas={"T00": 0.02, "T01": 0.02},
            revision_members=[f"T{i:02d}" for i in range(20)],
            probe_custody_symbols=[], starting_positions={})
    assert posts == []


@pytest.mark.parametrize("spy_qty,spy_value,cash,is_open", [
    ("NaN", "1000", "99000", True),
    (True, "1000", "99000", True),
    ("10", "NaN", "99000", True),
    ("10", "1000", "NaN", True),
    ("10", "1000", "99000", "true"),
])
def test_final_core_boundary_refuses_ambiguous_capacity_without_post(
        tmp_path, monkeypatch, spy_qty, spy_value, cash, is_open):
    lease = {"open": True, "owner": "sim_run offline-session",
             "session_nonce": "offline-nonce", "pid": os.getpid(),
             "process_birth_utc": PB._process_birth_utc(os.getpid()),
             "account_number": "offline-account"}
    path = tmp_path / "lease.json"
    path.write_text(json.dumps(lease), encoding="utf-8")
    monkeypatch.setattr(PB, "LEASE_PATH", path)
    monkeypatch.setattr(PB, "STATE_DIR", tmp_path)
    monkeypatch.setattr(PB, "_host", lambda: PE.PAPER_HOST)
    monkeypatch.setattr(PB, "account", lambda: {
        "account_number": "offline-account", "equity": "100000",
        "cash": cash, "long_market_value": "1000"})
    monkeypatch.setattr(PB, "positions", lambda: [
        {"symbol": "SPY", "qty": spy_qty, "market_value": spy_value}])
    monkeypatch.setattr(PB, "orders", lambda **_: [])
    monkeypatch.setattr(PB, "clock", lambda: {"is_open": is_open})
    posts = []
    monkeypatch.setattr(PB, "_call", lambda *a, **k: posts.append(k) or {"id": "fake"})
    with pytest.raises(PB.BrokerError):
        PB.submit_epoch_core_exit(
            qty=10, client_order_id="aegispc-e" + "1" * 20,
            session_id="offline-session", session_nonce="offline-nonce",
            account_fingerprint=PE.account_fingerprint("offline-account"))
    assert posts == []


def test_wrong_initial_account_and_process_birth_refuse_before_transition(monkeypatch):
    from backend.tests.test_pc_policy_epoch_prepared import _evidence
    evidence = _evidence()
    evidence["account"]["account_number"] = "foreign-account"
    evidence["lease"]["account_number"] = "foreign-account"
    with pytest.raises(PE.EpochRefused, match="approved PC paper account"):
        PE._identity(evidence, session_id="offline-session", nonce="offline-nonce")
    evidence = _evidence()
    evidence["lease"]["process_birth_utc"] = "1900-01-01T00:00:00+00:00"
    with pytest.raises(PE.EpochRefused, match="process birth"):
        PE._identity(evidence, session_id="offline-session", nonce="offline-nonce")


def test_racing_lease_claims_have_one_winner(tmp_path, monkeypatch):
    monkeypatch.setattr(PB, "STATE_DIR", tmp_path)
    monkeypatch.setattr(PB, "LEASE_PATH", tmp_path / "lease.json")
    monkeypatch.setattr(PB, "account", lambda: {
        "account_number": "offline-account", "equity": "100000"})
    def claim(_):
        try:
            return PB.open_lease(owner="sim_run offline")
        except PB.OwnershipConflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(claim, range(2)))
    assert len([row for row in outcomes if row is not None]) == 1
    assert PB.LEASE_PATH.exists()
    PB.close_lease(expected_nonce=next(row["session_nonce"] for row in outcomes if row))


def test_orphaned_unlocked_lease_lock_file_is_not_ownership(tmp_path, monkeypatch):
    monkeypatch.setattr(PB, "STATE_DIR", tmp_path)
    monkeypatch.setattr(PB, "LEASE_PATH", tmp_path / "lease.json")
    PB.LEASE_PATH.with_name("lease.json.lock").write_text("old dead writer",
                                                         encoding="utf-8")
    monkeypatch.setattr(PB, "account", lambda: {
        "account_number": "offline-account", "equity": "100000"})
    row = PB.open_lease(owner="sim_run offline")
    assert row["open"] is True
    PB.close_lease(expected_nonce=row["session_nonce"])


def test_post_window_serializes_lease_close(tmp_path, monkeypatch):
    monkeypatch.setattr(PB, "STATE_DIR", tmp_path)
    monkeypatch.setattr(PB, "LEASE_PATH", tmp_path / "lease.json")
    entered, release = Event(), Event()
    def blocked_post(**kwargs):
        entered.set()
        assert release.wait(3)
        return {"id": "offline"}
    monkeypatch.setattr(PB, "_submit_epoch_stock_locked", blocked_post)
    monkeypatch.setattr(PB, "_call", lambda *a, **k: {"id": "offline"})
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(PB.submit_epoch_stock, symbol="T00", side="buy", qty=1,
                             client_order_id="aegispc-s" + "1" * 20,
                             session_id="offline-session", session_nonce="nonce",
                             account_fingerprint="offline", minimum_cash_buffer=0.01,
                             median_dollar_vol=1_000_000, planned_price=100,
                             max_name_frac=0.12, max_adv_participation=0.02,
                             sleeve="PROBE", risk_sigmas={"T00": 0.02},
                             revision_members=[f"T{i:02d}" for i in range(20)],
                             probe_custody_symbols=["T00"],
                             starting_positions={})
        assert entered.wait(3)
        with pytest.raises(PB.OwnershipConflict, match="mutation already"):
            PB.close_lease(expected_nonce="nonce")
        release.set()
        assert future.result(timeout=3)["id"] == "offline"


def test_evidence_rejects_mark_only_double_read_race(tmp_path):
    fake = FakeTransport(tmp_path)
    calls = 0
    def account():
        nonlocal calls
        calls += 1
        return {"account_number": "offline-account", "equity": "100000" if calls == 1 else "90000",
                "cash": "100000" if calls == 1 else "90000", "long_market_value": "0"}
    fake.account = account
    with pytest.raises(PE.EpochRefused, match="snapshot raced"):
        PaperEpochBroker(fake).evidence(known_client_ids=set())
