"""Offline adversarial checks for the prepared, non-activatable PC epoch."""

import json
import os
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import pc_policy_epoch as PE
from backend.services import pc_broker as PB
from scripts import sim_run


@pytest.fixture(autouse=True)
def _approved_offline_account(monkeypatch):
    monkeypatch.setattr(PE, "EXPECTED_ACCOUNT_FINGERPRINT",
                        PE.account_fingerprint("offline-account"))


def test_committed_prepared_contract_verifies_its_actual_sources(monkeypatch):
    monkeypatch.setattr(PE, "EXPECTED_ACCOUNT_FINGERPRINT",
                        PE.FROZEN_ACCOUNT_FINGERPRINT)
    root = Path(__file__).resolve().parents[2]
    path = root / "backend/data/pc_policy_epochs/pc_paper_no_index_2026_10_v1.json"
    frozen = PE.load_contract(path, root=root)
    assert frozen["content"]["strategic_index_target"] is None
    assert frozen["content"]["allocation"]["revision_flow_gross_cap"] == 0.30
    assert frozen["content"]["allocation"]["probe_gross_cap"] == 0.20


def _contract(root: Path) -> tuple[Path, dict]:
    books = root / "backend/data/optimus/llm_portfolio"
    books.mkdir(parents=True)
    row = {"book_id": "test-book", "positions": [
        {"ticker": f"T{i:02d}", "weight": 0.05} for i in range(20)]}
    (books / "books.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    source = root / "backend/config.py"
    source.write_text("test source\n", encoding="utf-8")
    content = {
        "schema": "pc_paper_policy_epoch/v1", "licence": "PRODUCT_EXPERIMENT",
        "activation_allowed": False,
        "epoch_id": "PC_PAPER_NO_STRATEGIC_INDEX_2026_10_v1",
        "excluded_strategic_index_symbols": ["SPY"],
        "paper_account_fingerprint": PE.EXPECTED_ACCOUNT_FINGERPRINT,
        "binding_limits": dict(PE.EXPECTED_LIMITS),
        "transition": {"not_before_utc": "2026-10-12T13:30:00+00:00"},
        "eligibility_and_expiry": {"probe_horizons_sessions": [5, 21, 63, 126],
                                   "exploit_horizons_sessions": [1, 5, 21],
                                   "revision_grade_horizons_sessions": [1, 5, 21]},
        "strategic_index_target": None,
        "allocation": {"revision_flow_gross_cap": 0.30, "probe_gross_cap": 0.20,
                       "gross_cap": 1.0, "non_core_name_cap": 0.12,
                       "core_weight": 0.0,
                       "minimum_cash_buffer": 0.01,
                       "cash_when_unqualified": "RESERVE_NO_ELIGIBLE_RISK_CAPACITY"},
        "revision_flow": {"book_id": "test-book", "members": [
            f"T{i:02d}" for i in range(20)], "book_row_sha256": PE._sha(row)},
        "source_sha256": {"backend/config.py": PE._source_sha(source)},
    }
    wrapper = {"content": content, "content_sha256": PE._sha(content)}
    path = root / "prepared.json"
    path.write_text(json.dumps(wrapper), encoding="utf-8")
    return path, wrapper


def _fixture_load(path: Path, *, root: Path) -> dict:
    """Synthetic contracts exercise validator mechanics without approved ID."""
    wrapper = json.loads(path.read_text(encoding="utf-8"))
    return PE._load_contract(path, root=root,
                             expected_hash=wrapper["content_sha256"],
                             strict_source_inventory=False)


def _evidence(*, spy_qty="10.25", spy_value="1000", other_value="3000") -> dict:
    positions = [{"symbol": "RF_HOLD", "qty": "30", "market_value": other_value}]
    if spy_qty != "0":
        positions.append({"symbol": "SPY", "qty": spy_qty,
                          "market_value": spy_value})
    cash = 5000 - float(spy_value if spy_qty != "0" else 0) - float(other_value)
    return {"host": PE.PAPER_HOST,
            "observed_utc": datetime.now(timezone.utc).isoformat(),
            "account": {"account_number": "offline-account", "equity": "5000",
                        "cash": str(cash)},
            "lease": {"open": True, "owner": "sim_run offline-session",
                      "session_nonce": "offline-nonce", "pid": os.getpid(),
                      "process_birth_utc": PB._process_birth_utc(os.getpid()),
                      "account_number": "offline-account"},
            "orders_complete": True, "foreign_orders": [], "open_orders": [],
            "positions": positions}


def _prepared(tmp_path: Path, evidence: dict | None = None) -> tuple[Path, dict, dict]:
    contract_path, _ = _contract(tmp_path)
    contract = _fixture_load(contract_path, root=tmp_path)
    evidence = evidence or _evidence()
    journal = tmp_path / "transition.json"
    PE.prepare(journal, contract=contract, evidence=evidence,
               session_id="offline-session", nonce="offline-nonce",
               legacy_sources={"status": "LEGACY_OBSERVED_AT",
                               "config_sha256": "offline-source"})
    return journal, contract, evidence


def test_frozen_content_and_sources_detect_changed_bytes(tmp_path):
    path, wrapper = _contract(tmp_path)
    assert _fixture_load(path, root=tmp_path)["content_sha256"] == wrapper["content_sha256"]
    wrapper["content"]["allocation"]["probe_gross_cap"] = 0.30
    path.write_text(json.dumps(wrapper), encoding="utf-8")
    with pytest.raises(PE.EpochRefused, match="content changed"):
        _fixture_load(path, root=tmp_path)
    wrapper["content"]["allocation"]["probe_gross_cap"] = 0.20
    path.write_text(json.dumps(wrapper), encoding="utf-8")
    (tmp_path / "backend/config.py").write_text("changed source\n", encoding="utf-8")
    with pytest.raises(PE.EpochRefused, match="source changed"):
        _fixture_load(path, root=tmp_path)


def test_recomputed_content_hash_cannot_widen_binding_risk_limits(tmp_path):
    path, wrapper = _contract(tmp_path)
    limits = wrapper["content"]["binding_limits"]
    limits["one_day_worst_case_loss_frac"] = 1.0
    limits["revision_worst_21_session_loss_frac"] = 1.0
    wrapper["content_sha256"] = PE._sha(wrapper["content"])
    path.write_text(json.dumps(wrapper), encoding="utf-8")
    with pytest.raises(PE.EpochRefused, match="binding risk limits"):
        _fixture_load(path, root=tmp_path)


def test_frozen_revision_member_change_refuses(tmp_path):
    path, _ = _contract(tmp_path)
    books = tmp_path / "backend/data/optimus/llm_portfolio/books.jsonl"
    row = json.loads(books.read_text(encoding="utf-8"))
    row["positions"][0]["ticker"] = "DIFFERENT"
    books.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(PE.EpochRefused, match="membership"):
        _fixture_load(path, root=tmp_path)


def test_source_digest_ignores_only_checkout_line_endings(tmp_path):
    path, wrapper = _contract(tmp_path)
    source = tmp_path / "backend/config.py"
    source.write_bytes(b"test source\r\n")
    assert _fixture_load(path, root=tmp_path)["content_sha256"] == wrapper["content_sha256"]


def test_selected_epoch_refuses_before_stale_or_negative_selector_and_broker(tmp_path, monkeypatch):
    path, wrapper = _contract(tmp_path / "root")
    monkeypatch.setattr(PE, "EXPECTED_CONTENT_SHA256", wrapper["content_sha256"])
    monkeypatch.setattr(PE, "EXPECTED_SOURCE_PATHS", frozenset({"backend/config.py"}))
    out = tmp_path / "cycle"
    out.mkdir()
    (out / "ranking.json").write_text(json.dumps({
        "asof": "2020-01-01", "top20_net_rel_21d": -1,
        "top": [{"symbol": "SPY"}]}), encoding="utf-8")
    from backend.services import pc_broker
    def forbidden(*_args, **_kwargs):
        raise AssertionError("selected epoch must not call broker")
    for name in ("account", "positions", "orders", "clock", "submit"):
        monkeypatch.setattr(pc_broker, name, forbidden)
    result = sim_run.u_plan(out, "paper_profit", asof="2026-10-09",
                            policy_epoch_path=path, policy_epoch_root=tmp_path / "root")
    receipt = json.loads((out / "intended_book.json").read_text(encoding="utf-8"))
    assert result["refused"] == "POLICY_EPOCH_INACTIVE"
    assert receipt["policy_epoch_sha256"] == wrapper["content_sha256"]
    assert receipt["sent"] == [] and receipt["n_to_send"] == 0


def test_prepare_is_observed_legacy_and_same_transition_is_idempotent(tmp_path):
    journal, contract, evidence = _prepared(tmp_path)
    before = journal.read_bytes()
    same = PE.prepare(journal, contract=contract, evidence=evidence,
                      session_id="offline-session", nonce="offline-nonce",
                      legacy_sources={"status": "different"})
    assert journal.read_bytes() == before
    assert same["legacy_observed_at"]["effective_sources"]["status"] == "LEGACY_OBSERVED_AT"
    assert same["activation_allowed"] is False


@pytest.mark.parametrize("change", [
    lambda x: x["lease"].update(session_nonce="wrong"),
    lambda x: x["lease"].update(owner="sim_run other"),
    lambda x: x["lease"].update(pid=-1),
    lambda x: x["account"].update(account_number="another-account"),
    lambda x: x.update(host="https://api.alpaca.markets"),
    lambda x: x.update(orders_complete=False),
    lambda x: x.update(foreign_orders=[{"symbol": "SPY"}]),
])
def test_identity_or_incomplete_order_history_refuses(tmp_path, change):
    journal, contract, evidence = _prepared(tmp_path)
    changed = deepcopy(evidence)
    change(changed)
    with pytest.raises(PE.EpochRefused):
        PE.plan_core_exit(journal, contract=contract, evidence=changed)
    assert PE._load(journal)["state"] == "PREPARED"


def test_stale_broker_evidence_cannot_replay_transition(tmp_path):
    journal, contract, evidence = _prepared(tmp_path)
    stale = deepcopy(evidence)
    stale["observed_utc"] = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    with pytest.raises(PE.EpochRefused, match="stale"):
        PE.plan_core_exit(journal, contract=contract, evidence=stale)


def test_durable_whole_share_intent_and_restart_never_duplicate(tmp_path):
    journal, contract, evidence = _prepared(tmp_path)
    first = PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    before = journal.read_bytes()
    second = PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    assert first == second and journal.read_bytes() == before
    assert first["intent"]["qty"] == "10"
    assert first["intent"]["reason"] == "POLICY_EPOCH_EXIT_CORE"
    assert first["legacy_observed_at"]["economic"]["spy_fractional_residual"] == "0.25"


def test_cached_intent_does_not_authorize_more_than_fresh_capacity(tmp_path):
    journal, contract, evidence = _prepared(tmp_path)
    first = PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    changed = _evidence(spy_qty="5.25", spy_value="500")
    changed["open_orders"] = [{"symbol": "SPY", "side": "sell",
                               "qty": "5", "filled_qty": "0"}]
    result = PE.plan_core_exit(journal, contract=contract, evidence=changed)
    assert result["state"] == "UNKNOWN"
    assert result["intent"]["client_order_id"] == first["intent"]["client_order_id"]
    assert result["intent"]["qty"] == "10"  # historical intent, never a new authority


def test_missing_sale_proceeds_prevent_reconciliation(tmp_path):
    journal, contract, evidence = _prepared(tmp_path)
    row = PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    stale_cash = _evidence(spy_qty="0.25", spy_value="25")
    stale_cash["account"]["cash"] = "1000"  # should be 1975 after 10 shares sold
    order = {"client_order_id": row["intent"]["client_order_id"],
             "symbol": "SPY", "side": "sell", "qty": "10",
             "filled_qty": "10", "status": "filled"}
    result = PE.observe_core_exit(journal, contract=contract, evidence=stale_cash,
                                  matched_order=order)
    assert result["state"] == "DEGRADED"
    assert "cash plus positions" in result["reason"]


def test_pending_order_blocks_new_intent(tmp_path):
    journal, contract, evidence = _prepared(tmp_path)
    changed = deepcopy(evidence)
    changed["open_orders"] = [{"symbol": "SPY", "side": "sell", "qty": "10"}]
    with pytest.raises(PE.EpochRefused, match="pending orders"):
        PE.plan_core_exit(journal, contract=contract, evidence=changed)


def test_timeout_or_404_becomes_unknown_and_never_retries(tmp_path):
    journal, contract, evidence = _prepared(tmp_path)
    PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    unknown = PE.observe_core_exit(journal, contract=contract, evidence=evidence,
                                   matched_order=None)
    assert unknown["state"] == "UNKNOWN"
    with pytest.raises(PE.EpochRefused, match="UNKNOWN"):
        PE.plan_core_exit(journal, contract=contract, evidence=evidence)


def test_matching_client_id_with_wrong_quantity_is_unknown(tmp_path):
    journal, contract, evidence = _prepared(tmp_path)
    row = PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    wrong = {"client_order_id": row["intent"]["client_order_id"],
             "symbol": "SPY", "side": "sell", "qty": "20",
             "filled_qty": "0", "status": "new"}
    assert PE.observe_core_exit(journal, contract=contract, evidence=evidence,
                                matched_order=wrong)["state"] == "UNKNOWN"


def test_partial_fill_then_verified_fractional_residual(tmp_path):
    journal, contract, evidence = _prepared(tmp_path)
    row = PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    order = {"client_order_id": row["intent"]["client_order_id"],
             "id": "offline-order", "symbol": "SPY", "side": "sell", "qty": "10",
             "filled_qty": "5", "status": "partially_filled"}
    partial = _evidence(spy_qty="5.25", spy_value="500")
    partial["open_orders"] = [order]
    assert PE.observe_core_exit(journal, contract=contract, evidence=partial,
                                matched_order=order)["state"] == "EXIT_PENDING"
    filled = _evidence(spy_qty="0.25", spy_value="25")
    order["status"] = "filled"
    order["filled_qty"] = "10"
    done = PE.observe_core_exit(journal, contract=contract, evidence=filled,
                                matched_order=order, fills=[
        {"id": "offline-fill", "order_id": "offline-order", "symbol": "SPY",
         "side": "sell", "activity_type": "FILL", "qty": "10", "price": "97.5"}])
    assert done["state"] == "RECONCILED"
    assert done["reconciled_economic"]["spy_fractional_residual"] == "0.25"
    with pytest.raises(PE.EpochRefused, match="activation disabled"):
        PE.activate(journal, contract=contract, evidence=filled,
                    review_receipt=None, venue_open=False)


@pytest.mark.parametrize("status", ["rejected", "canceled", "filled"])
def test_failed_reconciliation_stays_degraded(tmp_path, status):
    journal, contract, evidence = _prepared(tmp_path)
    row = PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    order = {"client_order_id": row["intent"]["client_order_id"],
             "symbol": "SPY", "side": "sell", "qty": "10",
             "filled_qty": "10" if status == "filled" else "0", "status": status}
    assert PE.observe_core_exit(journal, contract=contract, evidence=evidence,
                                matched_order=order)["state"] == "DEGRADED"


def test_other_held_risk_is_counted_and_cash_only_reconciles(tmp_path):
    over = _evidence(other_value="4500")
    over["account"]["cash"] = "0"
    with pytest.raises(PE.EpochRefused, match="gross exceeds equity"):
        _prepared(tmp_path / "over", over)
    empty = _evidence(spy_qty="0", spy_value="0")
    journal, contract, evidence = _prepared(tmp_path / "empty", empty)
    row = PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    assert row["state"] == "RECONCILED" and row["intent"] is None
    assert row["reconciled_economic"]["spy_qty"] == "0"


class _ReplayEpochBroker:
    def __init__(self, *, lost_ack=False):
        self.current = _evidence()
        self.order = None
        self.n_post = 0
        self.lost_ack = lost_ack

    def evidence(self, *, known_client_ids):
        result = deepcopy(self.current)
        result["observed_utc"] = datetime.now(timezone.utc).isoformat()
        return result

    def venue_open(self):
        return True

    def order_by_client_id(self, client_id):
        return deepcopy(self.order) if self.order and self.order["client_order_id"] == client_id else None

    def fills(self, order_id):
        return [{"id": "offline-fill", "order_id": order_id, "symbol": "SPY",
                 "side": "sell", "activity_type": "FILL", "qty": "10", "price": "97.5"}]

    def submit_core_exit(self, *, intent, journal):
        assert intent["submit_status"] == "SUBMIT_UNKNOWN"
        self.n_post += 1
        self.order = {"id": "offline-order", "client_order_id": intent["client_order_id"],
                      "symbol": "SPY", "side": "sell", "qty": "10",
                      "filled_qty": "10", "status": "filled"}
        self.current = _evidence(spy_qty="0.25", spy_value="25")
        if self.lost_ack:
            raise TimeoutError("offline lost acknowledgement")
        return deepcopy(self.order)


@pytest.mark.parametrize("lost_ack", [False, True])
def test_real_transition_cycle_seam_reconciles_without_duplicate_post(tmp_path, lost_ack):
    contract_path, _ = _contract(tmp_path)
    contract = _fixture_load(contract_path, root=tmp_path)
    journal = tmp_path / "journal.json"
    broker = _ReplayEpochBroker(lost_ack=lost_ack)
    old = {"status": "LEGACY_OBSERVED_AT", "config_sha256": "offline-source"}
    first = PE.transition_cycle(journal, contract=contract, broker=broker,
                                session_id="offline-session", nonce="offline-nonce",
                                legacy_sources=old, may_submit=True)
    assert first["intent"]["submit_status"] == ("SUBMIT_UNKNOWN" if lost_ack
                                                   else "ACKNOWLEDGED")
    assert broker.n_post == 1
    second = PE.transition_cycle(journal, contract=contract, broker=broker,
                                 session_id="offline-session", nonce="offline-nonce",
                                 legacy_sources=old, may_submit=True)
    assert second["state"] == "RECONCILED"
    assert second["fill_economic"]["proceeds"] == "975.0"
    assert broker.n_post == 1
    third = PE.transition_cycle(journal, contract=contract, broker=broker,
                                session_id="offline-session", nonce="offline-nonce",
                                legacy_sources=old, may_submit=True)
    assert third["state"] == "RECONCILED" and broker.n_post == 1


def test_clean_owner_handoff_preserves_transition_and_intent(tmp_path):
    journal, contract, evidence = _prepared(tmp_path)
    first = PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    next_evidence = deepcopy(evidence)
    next_evidence["lease"].update(owner="sim_run successor", session_nonce="next-nonce")
    closure = {"open": False, "owner": "sim_run offline-session",
               "session_nonce": "offline-nonce", "pid": os.getpid(),
               "process_birth_utc": PB._process_birth_utc(os.getpid()),
               "account_number": "offline-account",
               "closed": datetime.now(timezone.utc).isoformat()}
    after = PE.handoff(journal, contract=contract, old_closure=closure,
                       old_session={"id": "offline-session", "state": "COMPLETED",
                                    "pid": os.getpid()},
                       new_evidence=next_evidence, new_session_id="successor",
                       new_nonce="next-nonce")
    assert after["transition_id"] == first["transition_id"]
    assert after["intent"]["client_order_id"] == first["intent"]["client_order_id"]
    assert after["session_id"] == "successor"


def test_unclean_handoff_and_concurrent_revision_refuse(tmp_path):
    journal, contract, evidence = _prepared(tmp_path)
    next_evidence = deepcopy(evidence)
    next_evidence["lease"].update(owner="sim_run successor", session_nonce="next-nonce")
    closure = {"open": False, "owner": "sim_run offline-session",
               "session_nonce": "offline-nonce", "pid": os.getpid(),
               "process_birth_utc": PB._process_birth_utc(os.getpid()),
               "account_number": "offline-account",
               "closed": datetime.now(timezone.utc).isoformat()}
    with pytest.raises(PE.EpochRefused, match="did not finish"):
        PE.handoff(journal, contract=contract, old_closure=closure,
                   old_session={"id": "offline-session", "state": "UNCLEAN"},
                   new_evidence=next_evidence, new_session_id="successor",
                   new_nonce="next-nonce")
    stale_copy = PE._load(journal)
    PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    stale_copy["reason"] = "stale writer"
    with pytest.raises(PE.EpochRefused, match="concurrently"):
        PE._save(journal, stale_copy)


def test_verified_unclean_handoff_requires_exact_journal_revision(tmp_path):
    journal, contract, evidence = _prepared(tmp_path)
    before = PE._load(journal)
    next_evidence = deepcopy(evidence)
    next_evidence["lease"].update(owner="sim_run successor", session_nonce="next-nonce")
    closure = {**evidence["lease"], "open": False,
               "closed": datetime.now(timezone.utc).isoformat(),
               "recovered_from_unclean": True,
               "journal_revision": before["revision"],
               "journal_sha256": PE._sha(before)}
    after = PE.handoff(journal, contract=contract, old_closure=closure,
                       old_session={"id": "offline-session", "state": "UNCLEAN",
                                    "pid": os.getpid()},
                       new_evidence=next_evidence, new_session_id="successor",
                       new_nonce="next-nonce")
    assert after["session_id"] == "successor"
    journal2, contract2, evidence2 = _prepared(tmp_path / "second")
    before2 = PE._load(journal2)
    closure["journal_revision"] = before2["revision"] + 1
    with pytest.raises(PE.EpochRefused, match="did not finish"):
        PE.handoff(journal2, contract=contract2, old_closure=closure,
                   old_session={"id": "offline-session", "state": "UNCLEAN",
                                "pid": os.getpid()},
                   new_evidence=next_evidence, new_session_id="successor",
                   new_nonce="next-nonce")


@pytest.mark.parametrize("recovered", [False, True])
def test_actual_session_seam_handoffs_only_after_closed_owned_lease(tmp_path,
                                                                     monkeypatch,
                                                                     recovered):
    from backend.services import pc_broker as PB
    old_nonce = "a" * 32
    new_nonce = "b" * 32
    path, _ = _contract(tmp_path / "root")
    contract = _fixture_load(path, root=tmp_path / "root")
    evidence = _evidence(spy_qty="0", spy_value="0")
    evidence["lease"]["session_nonce"] = old_nonce
    journal = tmp_path / "journal.json"
    original = PE.prepare(journal, contract=contract, evidence=evidence,
                          session_id="offline-session", nonce=old_nonce,
                          legacy_sources={"status": "LEGACY_OBSERVED_AT"})
    lease_dir = tmp_path / "broker" / "lease_history"
    lease_dir.mkdir(parents=True)
    closure = {**evidence["lease"], "open": False,
               "closed": datetime.now(timezone.utc).isoformat()}
    if recovered:
        closure.update(recovered_from_unclean=True,
                       journal_revision=original["revision"],
                       journal_sha256=PE._sha(original),
                       unclean_session={"id": "offline-session", "pid": os.getpid(),
                                        "state": "UNCLEAN"})
    (lease_dir / f"{old_nonce}.json").write_text(json.dumps(closure), encoding="utf-8")
    monkeypatch.setattr(PB, "STATE_DIR", tmp_path / "broker")
    monkeypatch.setattr(sim_run.SS, "history", lambda limit: [] if recovered else [
        {"id": "offline-session", "state": "COMPLETED", "pid": os.getpid(),
         "ended": datetime.now(timezone.utc).isoformat()}])
    current = deepcopy(evidence)
    current["lease"].update(owner="sim_run successor", session_nonce=new_nonce)

    class FakeBroker:
        def evidence(self, **_):
            return current

    sim_run._epoch_handoff_if_needed(journal, contract=contract,
                                      broker=FakeBroker(), session_id="successor",
                                      nonce=new_nonce)
    after = PE._load(journal)
    assert after["transition_id"] == original["transition_id"]
    assert after["session_id"] == "successor" and after["nonce"] == new_nonce


def test_actual_u_plan_epoch_seam_runs_transition_then_contract_grade_rows(tmp_path,
                                                                            monkeypatch):
    path, wrapper = _contract(tmp_path / "root")
    monkeypatch.setattr(PE, "EXPECTED_CONTENT_SHA256", wrapper["content_sha256"])
    monkeypatch.setattr(PE, "EXPECTED_SOURCE_PATHS", frozenset({"backend/config.py"}))
    from backend.services import pc_broker as PB
    monkeypatch.setattr(PB, "snapshot", lambda **_: (_ for _ in ()).throw(
        AssertionError("stale cached broker snapshot is not epoch authority")))
    broker = _ReplayEpochBroker()
    monkeypatch.setattr(PE, "ACTIVATION_ALLOWED", True)  # offline fixture only
    journal = tmp_path / "transition.json"
    out = tmp_path / "cycle"
    out.mkdir()
    (out / "nav.jsonl").write_text(json.dumps({
        "t": "2026-10-08T14:41:28+00:00", "equity": 100.0,
        "cash": 10.0}) + "\n", encoding="utf-8")
    common = dict(asof="2026-10-12", contracts_dir=tmp_path / "decisions",
                  ledger_path=tmp_path / "ledger.jsonl", policy_epoch_path=path,
                  policy_epoch_root=tmp_path / "root", policy_epoch_journal_path=journal,
                  policy_epoch_broker=broker, policy_epoch_session_id="offline-session",
                  policy_epoch_nonce="offline-nonce",
                  policy_epoch_review_receipt={"approved": True,
                      "contract_sha256": wrapper["content_sha256"],
                      "reviewed_utc": "2026-10-09T14:00:00+00:00"},
                  policy_epoch_selectors={"bars_fresh": True,
                      "revision_source_verified": True,
                      "adv_by_symbol": {f"T{i:02d}": 1_000_000.0 for i in range(20)},
                      "ranking": {"top20_net_rel_21d": -0.01, "top": []},
                      "blend_grade_may_trade": False, "probe_grade_may_trade": False,
                      "probe_rows": [], "prior_probe_holdings": []},
                  policy_epoch_prices={**{f"T{i:02d}": 10.0 for i in range(20)},
                                       "RF_HOLD": 100.0, "SPY": 100.0},
                  policy_epoch_sigmas={**{f"T{i:02d}": 0.02 for i in range(20)},
                                       "RF_HOLD": 0.02, "SPY": 0.007},
                  policy_epoch_now_utc=datetime(2026, 10, 12, 14,
                                                tzinfo=timezone.utc))
    first = sim_run.u_plan(out, "paper_profit", **common)
    assert first["policy_epoch_state"] == "EXIT_PENDING"
    assert broker.n_post == 1
    prepared = PE._load(journal)
    assert prepared["selected_contract_path"] == str(path.resolve())
    assert prepared["preparation_review"]["contract_sha256"] == wrapper["content_sha256"]
    second = sim_run.u_plan(out, "paper_profit", **common)
    assert second["policy_epoch_state"] == "ACTIVE"
    assert broker.n_post == 1
    receipt = json.loads((out / "intended_book.json").read_text(encoding="utf-8"))
    assert receipt["policy_epoch_sha256"] == wrapper["content_sha256"]
    assert receipt["activated_utc"] == "2026-10-12T14:00:00+00:00"
    assert receipt["since_epoch_return"] is None
    assert receipt["performance_status"] == "UNKNOWN_CASHFLOWS"
    assert receipt["shadow"]["separate_spy_control"]["status"] == "PRICED"
    assert receipt["plan"]["reserve_reason"] == "RESERVE_NO_ELIGIBLE_RISK_CAPACITY"
    assert receipt["plan"]["equity_at_plan"] == 5000.0
    assert PE._load(journal)["legacy_observed_at"]["effective_sources"][
        "last_reconcile_nav"]["equity"] == 100.0
    assert receipt["decisions"]["new_rows"] > 0
    decision_files = list((tmp_path / "decisions").glob("*.json"))
    assert decision_files
    rows = json.loads(decision_files[0].read_text(encoding="utf-8"))["rows"]
    assert all(row["policy_epoch_sha256"] == wrapper["content_sha256"] for row in rows)
    third = sim_run.u_plan(out, "paper_profit", **common)
    assert third["policy_epoch_state"] == "ACTIVE" and broker.n_post == 1
    # The real grader scores the epoch row and retains the frozen identity.
    from backend.services import decision_ledger as DL
    import pandas as pd
    selected = rows[0]
    frame = pd.DataFrame({selected["ticker"]: [100.0, 105.0],
                          "SPY": [100.0, 101.0]},
                         index=pd.to_datetime([selected["asof"], selected["expiry_utc"][:10]]))
    from backend import config
    monkeypatch.setattr(config, "DECISION_BENCHMARK_SYMBOL", "QQQ")
    scored = DL.score_due(today=date(2026, 11, 1), contracts=[selected],
                          price_fetch=lambda *_: frame,
                          path=common["ledger_path"])
    assert scored["newly_scored"] == 1
    grade_detail = DL.read(common["ledger_path"])[-1]["detail"]
    assert grade_detail["policy_epoch_sha256"] == wrapper["content_sha256"]
    assert grade_detail["benchmark_symbol"] == "SPY"


def test_epoch_probe_grade_and_prior_holdings_are_isolated(tmp_path, monkeypatch):
    from backend.services import decision_ledger as DL
    from backend import config
    ledger = tmp_path / "ledger.jsonl"
    epoch_hash = "offline-reviewed-epoch"
    for n in range(21):
        day = (date(2026, 1, 1) + timedelta(days=n)).isoformat()
        did = f"epoch-probe-{n}"
        DL.record(did, "DECIDED", by="offline", asof=day, path=ledger)
        DL.record(did, "SCORED", by="offline", asof=day, path=ledger,
                  detail={"policy_epoch_sha256": epoch_hash,
                          "grading_rule": DL.SCORING_RULE,
                          "hypothesis_id": "PC_EPOCH_PROBE", "sleeve": "PROBE",
                          "horizon_sessions": min(config.PROBE_HORIZONS_SESSIONS),
                          "excess_return": -0.01})
    assert sim_run._probe_grade(ledger, epoch_hash=epoch_hash)["may_trade"] is False
    assert sim_run._probe_grade(ledger)["n_days_scored"] == 0
    assert sim_run._probe_grade(ledger, epoch_hash="other")["n_days_scored"] == 0
    folder = tmp_path / "decisions"
    folder.mkdir()
    (folder / "2026-01-01.json").write_text(json.dumps({"rows": [
        {"ticker": "OLD", "sleeve": "PROBE", "direction": "BUY",
         "acting": True, "policy_epoch_sha256": epoch_hash},
        {"ticker": "LEGACY", "direction": "PROBE", "acting": True}]}),
        encoding="utf-8")
    assert sim_run._prior_probe_holdings(folder, "2026-01-02",
                                         epoch_hash=epoch_hash) == {"OLD"}
    assert sim_run._prior_probe_holdings(folder, "2026-01-02") == {"LEGACY"}
    from backend.services import investment_committee as IC
    from backend.services import pc_risk as PR
    from backend.services import pc_sleeves as SL
    from backend.services import policy_state as PS
    from backend.services import expected_return as ER
    monkeypatch.setattr(sim_run, "bars_gate", lambda *a, **k: {"stale": False})
    monkeypatch.setattr(sim_run, "_contract_view", lambda *a, **k: {"refused": {}})
    monkeypatch.setattr(IC, "shortlist", lambda *a, **k: [
        {"ticker": "NEW", "median_dollar_vol": 1_000_000}])
    monkeypatch.setattr(SL, "load_revision_flow", lambda **k: {
        "tickers": [f"T{i:02d}" for i in range(20)]})
    monkeypatch.setattr(PB, "last_prices", lambda names: {s: 100 for s in names})
    monkeypatch.setattr(PR, "panel_sigmas", lambda *a, **k: {})
    monkeypatch.setattr(PS, "plan_view", lambda *a, **k: {"use": False})
    monkeypatch.setattr(ER.Sources, "production", lambda **k: (_ for _ in ()).throw(
        RuntimeError("offline E[r] absent")))
    out = tmp_path / "cycle"
    out.mkdir()
    (out / "ranking.json").write_text(json.dumps({"asof": "2026-01-22", "top": []}),
                                       encoding="utf-8")
    contract = {"content_sha256": epoch_hash, "content": {"revision_flow": {
        "book_id": "offline", "members": [f"T{i:02d}" for i in range(20)]}}}
    selectors, _, _ = sim_run._epoch_selector_evidence(
        out, "2026-01-22", contract, {"OLD": "20"},
        funnel_path=None, bars_paths=None, now_utc=None, folder=folder,
        ledger_path=ledger)
    assert selectors["probe_grade_may_trade"] is False
    assert selectors["prior_probe_holdings"] == ["OLD"]


def test_epoch_probe_corruption_refuses_only_its_matching_cohort(tmp_path):
    from backend.services import decision_ledger as DL
    from backend import config
    ledger = tmp_path / "ledger.jsonl"
    h = min(config.PROBE_HORIZONS_SESSIONS)
    rows = []
    for epoch, excess in (("this-epoch", float("inf")),
                          ("other-epoch", float("inf"))):
        rows.append({"state": "SCORED", "asof": "2026-10-12", "detail": {
            "grading_rule": DL.SCORING_RULE, "policy_epoch_sha256": epoch,
            "hypothesis_id": "PC_EPOCH_PROBE", "sleeve": "PROBE",
            "horizon_sessions": h, "excess_return": excess}})
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    bad = sim_run._probe_grade(ledger, epoch_hash="this-epoch")
    assert bad["invalid_numeric_rows"] == 1
    assert bad["verdict"] == "MEASUREMENT_INVALID" and bad["may_trade"] is False
    absent = sim_run._probe_grade(ledger, epoch_hash="third-epoch")
    assert absent["invalid_numeric_rows"] == 0
    assert absent["verdict"] == "UNMEASURED_TRADE_SMALL" and absent["may_trade"] is True


def test_epoch_exploit_decomposition_reaches_real_writer_and_grader(tmp_path):
    from backend.services import decision_ledger as DL
    import pandas as pd
    contract = {"content_sha256": "reviewed-epoch", "content": {
        "epoch_id": "PC_PAPER_NO_STRATEGIC_INDEX_2026_10_v1",
        "eligibility_and_expiry": {"probe_horizons_sessions": [5, 21, 63, 126],
                                   "exploit_horizons_sessions": [1, 5, 21],
                                   "revision_grade_horizons_sessions": [1, 5, 21]}}}
    plan = {"targets": [{"symbol": "TEST", "weight": 0.1}],
            "target_states": {"TEST": "EXPLOIT"}, "held_weights": {"TEST": 0.1}}
    er_view = {"names": {"TEST": {"h21": {
        "er": 0.02, "er_equal": 0.01, "x": {}, "weights": {}, "phi": {},
        "components_awake": [], "weights_source": "offline"}}}}
    rows = sim_run._epoch_decision_rows(plan, contract=contract, asof="2026-10-12",
                                         mode="paper_profit", equity=100000,
                                         prices={"TEST": 100, "SPY": 100},
                                         er_view=er_view)
    selected = next(r for r in rows if r["horizon_sessions"] == 21)
    assert selected["er_total"] == 0.02
    ledger = tmp_path / "ledger.jsonl"
    sim_run._write_sleeve_decisions([selected], asof="2026-10-12",
                                    folder=tmp_path / "decisions", ledger_path=ledger)
    frame = pd.DataFrame({"TEST": [100.0, 99.0], "SPY": [100.0, 101.0]},
                         index=pd.to_datetime([selected["asof"], selected["expiry_utc"][:10]]))
    result = DL.score_due(today=date(2026, 11, 30), contracts=[selected],
                          price_fetch=lambda *_: frame, path=ledger)
    assert result["newly_scored"] == 1
    detail = DL.read(ledger)[-1]["detail"]
    assert detail["er_total"] == 0.02
    assert detail["policy_epoch_sha256"] == "reviewed-epoch"
    assert sim_run._blend_grade(ledger, epoch_hash="reviewed-epoch")["n_days_scored"] == 1
    assert sim_run._blend_grade(ledger)["n_days_scored"] == 0


@pytest.mark.parametrize("exit_price,may_trade", [(105.0, True), (95.0, False)])
def test_virtual_exploit_shadow_bootstraps_epoch_only_grade(tmp_path,
                                                           exit_price, may_trade):
    from backend.services import pc_epoch_planner as PL
    from backend.services import decision_ledger as DL
    from backend.tests.test_pc_epoch_planner import _selectors, _evidence
    import pandas as pd
    path, _ = _contract(tmp_path / "root")
    contract = _fixture_load(path, root=tmp_path / "root")
    cell = {"er": 0.05, "er_equal": 0.04, "x": {}, "weights": {},
            "phi": {}, "components_awake": [], "weights_source": "offline"}
    selectors = _selectors()
    selectors.update(revision_source_verified=False, blend_grade_may_trade=False,
                     ranking={"top20_net_rel_21d": 0.01,
                              "top": [{"symbol": "OTHER", "median_dollar_vol": 1_000_000}]},
                     er_view={"names": {"OTHER": {"h21": cell}}})
    prices = {"OTHER": 100.0, "SPY": 100.0}
    plan = PL.plan_active(contract=contract, evidence=_evidence(), selectors=selectors,
                          prices=prices, sigmas={"OTHER": 0.02})
    assert plan["shadow_exploit"] == ["OTHER"]
    assert plan["sendable"] == [] and "OTHER" not in plan["target_states"]
    unpriced = PL.plan_active(contract=contract, evidence=_evidence(), selectors=selectors,
                              prices={"OTHER": 100.0}, sigmas={"OTHER": 0.02})
    assert unpriced["shadow_exploit"] == []
    ledger = tmp_path / "ledger.jsonl"
    for i in range(21):
        asof = (date(2026, 10, 12) + timedelta(days=i)).isoformat()
        rows = sim_run._epoch_decision_rows(plan, contract=contract, asof=asof,
                                             mode="paper_profit", equity=100000,
                                             prices=prices, er_view=selectors["er_view"])
        shadow = next(r for r in rows if r["sleeve"] == "EXPLOIT"
                      and r["horizon_sessions"] == 21)
        assert shadow["virtual"] is True and shadow["acting"] is False
        sim_run._write_sleeve_decisions([shadow], asof=asof,
                                        folder=tmp_path / "decisions", ledger_path=ledger)
        frame = pd.DataFrame({"OTHER": [100.0, exit_price], "SPY": [100.0, 101.0]},
                             index=pd.to_datetime([asof, shadow["expiry_utc"][:10]]))
        assert DL.score_due(today=date(2027, 1, 2), contracts=[shadow],
                            price_fetch=lambda *_: frame, path=ledger)["newly_scored"] == 1
    grade = sim_run._blend_grade(ledger, epoch_hash=contract["content_sha256"])
    assert grade["n_days_scored"] == 21 and grade["may_trade"] is may_trade
    assert sim_run._blend_grade(ledger)["n_days_scored"] == 0
    selectors["blend_grade_may_trade"] = grade["may_trade"]
    acting = PL.plan_active(contract=contract, evidence=_evidence(),
                            selectors=selectors, prices=prices,
                            sigmas={"OTHER": 0.02})
    assert acting["exploit_acting"] is may_trade
    assert acting["shadow_exploit"] == ([] if may_trade else ["OTHER"])


def test_scheduled_successor_inherits_persisted_epoch_selector(tmp_path, monkeypatch):
    from backend.services import sim_session as SS
    from backend.services import disk_guard as DG
    from backend import config
    journal = tmp_path / "pc_book" / "policy_epoch_transition.json"
    journal.parent.mkdir()
    selected = tmp_path / "selected.json"
    selected.write_text("{}", encoding="utf-8")
    journal.write_text(json.dumps({
        "schema": "pc_policy_transition/v1", "state": "ACTIVE",
        "selected_contract_path": str(selected),
        "activation_review": {"approved": True, "contract_sha256": "frozen",
                              "reviewed_utc": "2026-10-09T14:00:00+00:00"}}),
        encoding="utf-8")
    monkeypatch.delenv("AEGIS_PC_EPOCH_CONTRACT", raising=False)
    monkeypatch.delenv("AEGIS_PC_EPOCH_REVIEW_RECEIPT", raising=False)
    monkeypatch.setattr(config, "OPTIMUS_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(SS, "status", lambda: {"session": {
        "id": "successor", "mode": "observe"}})
    monkeypatch.setattr(DG, "require_free", lambda *a, **k: None)
    received = {}
    def fake_loop(session_id, session, mode, **kwargs):
        received.update(kwargs)
        return 0
    monkeypatch.setattr(sim_run, "_run_loop", fake_loop)
    assert sim_run.run("successor") == 0
    assert received["policy_epoch_path"] == selected
    assert received["policy_epoch_review_receipt"]["contract_sha256"] == "frozen"
    row = json.loads(journal.read_text(encoding="utf-8"))
    row["state"] = "PREPARED"
    row["preparation_review"] = row.pop("activation_review")
    journal.write_text(json.dumps(row), encoding="utf-8")
    received.clear()
    assert sim_run.run("successor") == 0
    assert received["policy_epoch_review_receipt"]["approved"] is True
    row.pop("selected_contract_path")
    journal.write_text(json.dumps(row), encoding="utf-8")
    stopped = []
    monkeypatch.setattr(SS, "finish", lambda *a, **k: stopped.append(a))
    assert sim_run.run("successor") == 6
    assert stopped and stopped[0][0] == "STOPPED"


def test_selected_epoch_refuses_missing_current_broker_evidence(tmp_path, monkeypatch):
    path, wrapper = _contract(tmp_path / "root")
    monkeypatch.setattr(PE, "EXPECTED_CONTENT_SHA256", wrapper["content_sha256"])
    monkeypatch.setattr(PE, "EXPECTED_SOURCE_PATHS", frozenset({"backend/config.py"}))
    monkeypatch.setattr(PE, "ACTIVATION_ALLOWED", True)

    class MissingBroker:
        def venue_open(self):
            return True

        def evidence(self, **_):
            raise PE.EpochRefused("current account snapshot absent")

    out = tmp_path / "cycle"
    with pytest.raises(PE.EpochRefused, match="current account snapshot absent"):
        sim_run.u_plan(out, "paper_profit", asof="2026-10-12",
                       policy_epoch_path=path, policy_epoch_root=tmp_path / "root",
                       policy_epoch_journal_path=tmp_path / "journal.json",
                       policy_epoch_broker=MissingBroker(),
                       policy_epoch_session_id="offline-session",
                       policy_epoch_nonce="offline-nonce",
                       policy_epoch_review_receipt={"approved": True,
                           "contract_sha256": wrapper["content_sha256"],
                           "reviewed_utc": "2026-10-09T14:00:00+00:00"},
                       policy_epoch_now_utc=datetime(2026, 10, 12, 14,
                                                     tzinfo=timezone.utc))
    assert not (out / "intended_book.json").exists()


def test_selected_u_plan_uses_guarded_adapter_then_reconciles_stock_fill(tmp_path,
                                                                          monkeypatch):
    from backend.services import pc_broker as PB
    from backend.services.pc_epoch_broker import PaperEpochBroker
    path, wrapper = _contract(tmp_path / "root")
    monkeypatch.setattr(PE, "EXPECTED_CONTENT_SHA256", wrapper["content_sha256"])
    monkeypatch.setattr(PE, "EXPECTED_SOURCE_PATHS", frozenset({"backend/config.py"}))
    monkeypatch.setattr(PE, "ACTIVATION_ALLOWED", True)

    class Transport:
        LEASE_PATH = tmp_path / "lease.json"

        def __init__(self):
            self.LEASE_PATH.write_text(json.dumps({
                "open": True, "owner": "sim_run offline-session",
                "session_nonce": "offline-nonce", "pid": os.getpid(),
                "process_birth_utc": PB._process_birth_utc(os.getpid()),
                "account_number": "offline-account",
                "opened": "2026-10-12T13:59:00+00:00"}), encoding="utf-8")
            self.order = None
            self.filled = False
            self.n_post = 0

        def _host(self):
            return PE.PAPER_HOST

        def clock(self):
            return {"is_open": True}

        def account(self):
            return {"account_number": "offline-account", "equity": "100000",
                    "cash": "98500" if self.filled else "100000",
                    "long_market_value": "1500" if self.filled else "0"}

        def positions(self):
            return ([{"symbol": "T00", "qty": "15", "market_value": "1500"}]
                    if self.filled else [])

        def orders(self, *, status, limit, before_order_id=None):
            if status == "open":
                return [] if self.filled or self.order is None else [self.order]
            return [self.order] if self.order is not None and before_order_id is None else []

        def order_by_client_id(self, client_id):
            if self.order is None:
                raise PB.BrokerError("GET /v2/orders:by_client_order_id -> HTTP 404")
            return self.order

        def fill_activities(self, order_id, *, page_token=None):
            return ([{"id": "offline-fill", "order_id": order_id,
                      "activity_type": "FILL", "symbol": "T00", "side": "buy",
                      "qty": "15", "price": "100"}] if self.filled else [])

        def submit_epoch_stock(self, **kwargs):
            assert kwargs["minimum_cash_buffer"] == 0.01
            assert kwargs["session_nonce"] == "offline-nonce"
            self.n_post += 1
            self.order = {"id": "offline-stock-order",
                          "submitted_at": "2026-10-12T14:00:00+00:00",
                          "client_order_id": kwargs["client_order_id"],
                          "symbol": kwargs["symbol"], "side": kwargs["side"],
                          "qty": str(kwargs["qty"]),
                          "filled_qty": "0", "status": "new"}
            return self.order

    transport = Transport()
    common = dict(asof="2026-10-12", contracts_dir=tmp_path / "decisions",
                  ledger_path=tmp_path / "ledger.jsonl", policy_epoch_path=path,
                  policy_epoch_root=tmp_path / "root",
                  policy_epoch_journal_path=tmp_path / "journal.json",
                  policy_epoch_broker=PaperEpochBroker(transport),
                  policy_epoch_session_id="offline-session",
                  policy_epoch_nonce="offline-nonce",
                  policy_epoch_review_receipt={"approved": True,
                      "contract_sha256": wrapper["content_sha256"],
                      "reviewed_utc": "2026-10-09T14:00:00+00:00"},
                  policy_epoch_selectors={"bars_fresh": True,
                      "revision_source_verified": True,
                      "adv_by_symbol": {f"T{i:02d}": 1_000_000.0 for i in range(20)},
                      "ranking": {"top20_net_rel_21d": -0.01, "top": []},
                      "blend_grade_may_trade": False, "probe_grade_may_trade": False,
                      "probe_rows": [], "prior_probe_holdings": []},
                  policy_epoch_prices={f"T{i:02d}": 100.0 for i in range(20)},
                  policy_epoch_sigmas={f"T{i:02d}": 0.02 for i in range(20)},
                  policy_epoch_now_utc=datetime(2026, 10, 12, 14,
                                                tzinfo=timezone.utc))
    out = tmp_path / "cycle"
    first = sim_run.u_plan(out, "paper_profit", **common)
    assert first["policy_epoch_state"] == "ACTIVE" and transport.n_post == 1
    assert PE._load(common["policy_epoch_journal_path"])["stock_intents"][0]["status"] == "ACKNOWLEDGED"
    transport.filled = True
    transport.order.update(status="filled", filled_qty="15")
    second = sim_run.u_plan(out, "paper_profit", **common)
    assert second["policy_epoch_state"] == "ACTIVE" and transport.n_post == 1
    assert PE._load(common["policy_epoch_journal_path"])["stock_intents"][0]["status"] == "FILLED"
    assert json.loads((out / "intended_book.json").read_text(encoding="utf-8"))[
        "stock_action"]["status"] == "REPLAN_REQUIRED"


class _ReplayStockBroker:
    def __init__(self, *, lost_ack=False, no_order=False):
        self.hold = {}
        self.cash = 100000.0
        self.orders = {}
        self.n_post = 0
        self.lost_ack = lost_ack
        self.no_order = no_order

    def evidence(self, *, known_client_ids):
        positions = [{"symbol": s, "qty": str(q), "market_value": str(q * 100)}
                     for s, q in self.hold.items()]
        return {"host": PE.PAPER_HOST,
                "observed_utc": datetime.now(timezone.utc).isoformat(),
                "account": {"account_number": "offline-account", "equity": "100000",
                            "cash": str(self.cash)},
                "lease": {"open": True, "owner": "sim_run offline-session",
                          "session_nonce": "offline-nonce", "pid": os.getpid(),
                          "process_birth_utc": PB._process_birth_utc(os.getpid()),
                          "account_number": "offline-account"},
                "positions": positions, "open_orders": [], "orders_complete": True,
                "foreign_orders": []}

    def order_by_client_id(self, client_id):
        return deepcopy(self.orders.get(client_id))

    def fills(self, order_id):
        order = next(o for o in self.orders.values() if o["id"] == order_id)
        return [{"id": f"fill-{order_id}", "order_id": order_id,
                 "symbol": order["symbol"], "side": order["side"],
                 "activity_type": "FILL", "qty": order["qty"], "price": "100"}]

    def submit_stock_order(self, *, intent, journal, minimum_cash_buffer,
                           max_name_frac, max_adv_participation):
        assert intent["status"] == "SUBMIT_UNKNOWN"
        self.n_post += 1
        if not self.no_order:
            order = {"id": f"order-{self.n_post}",
                     "client_order_id": intent["client_order_id"],
                     "symbol": intent["symbol"], "side": intent["side"],
                     "qty": intent["qty"], "filled_qty": intent["qty"],
                     "status": "filled"}
            self.orders[intent["client_order_id"]] = order
            delta = int(intent["qty"]) * (1 if intent["side"] == "buy" else -1)
            self.hold[intent["symbol"]] = self.hold.get(intent["symbol"], 0) + delta
            self.cash -= delta * 100
        if self.lost_ack or self.no_order:
            raise TimeoutError("offline POST outcome lost")
        return deepcopy(order)


def _active_stock_fixture(tmp_path, monkeypatch):
    from backend.services import pc_epoch_planner as PL
    path, _ = _contract(tmp_path / "root")
    contract = _fixture_load(path, root=tmp_path / "root")
    broker = _ReplayStockBroker()
    evidence = broker.evidence(known_client_ids=set())
    journal = tmp_path / "active.json"
    PE.prepare(journal, contract=contract, evidence=evidence,
               session_id="offline-session", nonce="offline-nonce",
               legacy_sources={"status": "LEGACY_OBSERVED_AT"})
    PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    monkeypatch.setattr(PE, "ACTIVATION_ALLOWED", True)
    PE.activate(journal, contract=contract, evidence=evidence,
                review_receipt={"approved": True,
                                "contract_sha256": contract["content_sha256"],
                                "reviewed_utc": "2026-10-09T14:00:00+00:00"},
                venue_open=True,
                now_utc=datetime(2026, 10, 12, 14, tzinfo=timezone.utc))
    selectors = {"bars_fresh": True, "revision_source_verified": True,
                 "adv_by_symbol": {f"T{i:02d}": 1_000_000.0 for i in range(20)},
                 "ranking": {"top20_net_rel_21d": -0.01, "top": []},
                 "blend_grade_may_trade": False, "probe_grade_may_trade": False,
                 "probe_rows": [], "prior_probe_holdings": []}
    prices = {f"T{i:02d}": 100.0 for i in range(20)}
    sigmas = {f"T{i:02d}": 0.02 for i in range(20)}
    plan = PL.plan_active(contract=contract, evidence=evidence,
                          selectors=selectors, prices=prices, sigmas=sigmas)
    return journal, contract, broker, plan


@pytest.mark.parametrize("lost_ack", [False, True])
def test_active_stock_order_replays_fill_before_next_intent(tmp_path, monkeypatch,
                                                              lost_ack):
    journal, contract, broker, plan = _active_stock_fixture(tmp_path, monkeypatch)
    broker.lost_ack = lost_ack
    first = PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                                   plan=plan, may_submit=True)
    assert first["status"] == ("SUBMIT_UNKNOWN" if lost_ack else "ACKNOWLEDGED")
    assert broker.n_post == 1
    broker.lost_ack = False
    # The next cycle must resolve the first fill before any second POST.
    second = PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                                    plan=plan, may_submit=True)
    assert second["status"] == "REPLAN_REQUIRED"
    assert PE._load(journal)["stock_intents"][0]["status"] == "FILLED"
    assert broker.n_post == 1


def test_active_stock_404_after_post_is_unknown_without_retry(tmp_path, monkeypatch):
    journal, contract, broker, plan = _active_stock_fixture(tmp_path, monkeypatch)
    broker.no_order = True
    first = PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                                   plan=plan, may_submit=True)
    assert first["status"] == "SUBMIT_UNKNOWN" and broker.n_post == 1
    second = PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                                    plan=plan, may_submit=True)
    assert second["status"] == "UNKNOWN" and broker.n_post == 1


def test_proven_pre_submit_refusal_allows_only_changed_replan(tmp_path, monkeypatch):
    journal, contract, broker, plan = _active_stock_fixture(tmp_path, monkeypatch)
    calls = []
    def refused(**kwargs):
        calls.append(kwargs["intent"]["client_order_id"])
        raise PB.EpochPreSubmitRefused("arrival quote requires replan")
    broker.submit_stock_order = refused
    first = PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                                   plan=plan, may_submit=True)
    assert first["status"] == "REPLAN_REQUIRED" and broker.n_post == 0
    assert PE._load(journal)["stock_intents"][-1]["status"] == "GUARD_REFUSED_NO_POST"
    repeat = PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                                    plan=plan, may_submit=True)
    assert repeat["status"] == "REPLAN_REQUIRED" and len(calls) == 1
    changed = deepcopy(plan)
    changed["sendable"][0]["price"] = 101.0
    third = PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                                   plan=changed, may_submit=True)
    assert third["status"] == "REPLAN_REQUIRED" and len(calls) == 2
    assert len(set(calls)) == 2 and broker.n_post == 0


def test_order_circuit_breaker_counts_only_current_session(tmp_path, monkeypatch):
    journal, contract, broker, plan = _active_stock_fixture(tmp_path, monkeypatch)
    row = PE._load(journal)
    row["stock_intents"] = [{"client_order_id": f"old-{n}", "status": "FILLED",
                             "session_id": "prior-session"} for n in range(120)]
    PE._save(journal, row)
    result = PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                                    plan=plan, may_submit=True)
    assert result["status"] == "ACKNOWLEDGED" and broker.n_post == 1
    row = PE._load(journal)
    row["stock_intents"] = [{"client_order_id": f"current-{n}", "status": "FILLED",
                             "session_id": "offline-session"} for n in range(120)]
    PE._save(journal, row)
    with pytest.raises(PE.EpochRefused, match="order count cap"):
        PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                               plan=plan, may_submit=True)


def test_orphaned_unlocked_journal_lock_file_does_not_strand_revision(tmp_path):
    path = tmp_path / "epoch.json"
    path.with_name("epoch.json.lock").write_text("old dead writer", encoding="utf-8")
    row = {"schema": "pc_policy_transition/v1", "state": "PREPARED"}
    PE._save(path, row)
    assert PE._load(path)["revision"] == 1


def test_unclean_lease_recovery_requires_resolved_epoch_and_dead_birth(tmp_path,
                                                                       monkeypatch):
    from backend.services import sim_session as SS
    journal, contract, evidence = _prepared(tmp_path)
    monkeypatch.setattr(PE, "EXPECTED_CONTENT_SHA256", contract["content_sha256"])
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(evidence["lease"]), encoding="utf-8")
    monkeypatch.setattr(PB, "STATE_DIR", tmp_path)
    monkeypatch.setattr(PB, "LEASE_PATH", lease_path)
    monkeypatch.setattr(SS, "status", lambda: {"state": "UNCLEAN", "session": {
        "id": "offline-session", "pid": os.getpid(), "heartbeat": "old"}})
    class ReadOnlyBroker:
        def evidence(self, *, known_client_ids):
            assert known_client_ids == set()
            return evidence
        def order_by_client_id(self, _):
            raise AssertionError("prepared epoch has no prior POST")
    broker = ReadOnlyBroker()
    real_birth = PB._process_birth_utc
    with pytest.raises(PB.OwnershipConflict, match="may still be alive"):
        PB.recover_unclean_epoch_lease(journal_path=journal, broker=broker)
    monkeypatch.setattr(PB, "_process_birth_utc", lambda pid: None)
    monkeypatch.setattr(PB, "_pid_alive", lambda pid: False)
    receipt = PB.recover_unclean_epoch_lease(journal_path=journal, broker=broker)
    assert receipt["status"] == "RECOVERED_CLOSED"
    closure = json.loads(lease_path.read_text(encoding="utf-8"))
    assert closure["open"] is False and closure["recovered_from_unclean"] is True
    assert closure["journal_sha256"] == PE._sha(PE._load(journal))
    lease_path.write_text(json.dumps(evidence["lease"]), encoding="utf-8")
    monkeypatch.setattr(PB, "_process_birth_utc", real_birth)
    PE.plan_core_exit(journal, contract=contract, evidence=evidence)
    monkeypatch.setattr(PB, "_process_birth_utc", lambda pid: None)
    with pytest.raises(PB.OwnershipConflict, match="not fully resolved"):
        PB.recover_unclean_epoch_lease(journal_path=journal, broker=broker)


def test_unclean_active_recovery_requires_matching_order_and_fills(tmp_path,
                                                                   monkeypatch):
    from backend.services import sim_session as SS
    evidence = _evidence(spy_qty="0", spy_value="0")
    journal, contract, evidence = _prepared(tmp_path, evidence)
    monkeypatch.setattr(PE, "EXPECTED_CONTENT_SHA256", contract["content_sha256"])
    row = PE._load(journal)
    row["state"] = "ACTIVE"
    row["stock_intents"] = [{"client_order_id": "owned-order", "status": "FILLED",
                             "symbol": "T00", "side": "buy", "qty": "1"}]
    PE._save(journal, row)
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(evidence["lease"]), encoding="utf-8")
    monkeypatch.setattr(PB, "STATE_DIR", tmp_path)
    monkeypatch.setattr(PB, "LEASE_PATH", lease_path)
    monkeypatch.setattr(PB, "_process_birth_utc", lambda pid: None)
    monkeypatch.setattr(PB, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(SS, "status", lambda: {"state": "UNCLEAN", "session": {
        "id": "offline-session", "pid": os.getpid()}})
    class ReadOnlyBroker:
        matched = None
        def evidence(self, *, known_client_ids):
            assert known_client_ids == {"owned-order"}
            return evidence
        def order_by_client_id(self, coid):
            assert coid == "owned-order"
            return self.matched
        def fills(self, order_id):
            return [{"id": "fill", "order_id": order_id, "symbol": "T00",
                     "side": "buy", "activity_type": "FILL", "qty": "1",
                     "price": "100"}]
    broker = ReadOnlyBroker()
    with pytest.raises(PB.OwnershipConflict, match="known order unresolved"):
        PB.recover_unclean_epoch_lease(journal_path=journal, broker=broker)
    assert json.loads(lease_path.read_text(encoding="utf-8"))["open"] is True
    broker.matched = {"id": "order", "client_order_id": "owned-order",
                      "symbol": "T00", "side": "buy", "status": "filled",
                      "qty": "1"}
    assert PB.recover_unclean_epoch_lease(journal_path=journal, broker=broker)[
        "status"] == "RECOVERED_CLOSED"


def test_unclean_lost_ack_filled_recovery_requires_exact_economics(tmp_path,
                                                                    monkeypatch):
    from backend.services import sim_session as SS
    evidence = _evidence(spy_qty="0", spy_value="0")
    journal, contract, evidence = _prepared(tmp_path, evidence)
    monkeypatch.setattr(PE, "EXPECTED_CONTENT_SHA256", contract["content_sha256"])
    row = PE._load(journal)
    row["state"] = "ACTIVE"
    row["stock_intents"] = [{"client_order_id": "owned-lost-ack",
                             "status": "SUBMIT_UNKNOWN", "symbol": "T00",
                             "side": "buy", "qty": "1", "starting_qty": "0",
                             "starting_cash": "2000"}]
    PE._save(journal, row)
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(evidence["lease"]), encoding="utf-8")
    monkeypatch.setattr(PB, "STATE_DIR", tmp_path)
    monkeypatch.setattr(PB, "LEASE_PATH", lease_path)
    monkeypatch.setattr(PB, "_process_birth_utc", lambda pid: None)
    monkeypatch.setattr(PB, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(SS, "status", lambda: {"state": "UNCLEAN", "session": {
        "id": "offline-session", "pid": os.getpid()}})
    evidence["positions"].append({"symbol": "T00", "qty": "1", "market_value": "100"})
    evidence["account"]["cash"] = "1901"
    evidence["account"]["equity"] = "5001"
    class ReadOnlyBroker:
        lookup_count = 0
        order = None
        def evidence(self, *, known_client_ids):
            assert known_client_ids == {"owned-lost-ack"}
            return evidence
        def order_by_client_id(self, coid):
            assert coid == "owned-lost-ack"
            self.lookup_count += 1
            return self.order
        def fills(self, order_id):
            return [{"id": "fill", "order_id": order_id, "symbol": "T00",
                     "side": "buy", "activity_type": "FILL", "qty": "1",
                     "price": "100"}]
    broker = ReadOnlyBroker()
    with pytest.raises(PB.OwnershipConflict, match="known order unresolved"):
        PB.recover_unclean_epoch_lease(journal_path=journal, broker=broker)
    assert broker.lookup_count == 1
    broker.order = {"id": "order", "client_order_id": "owned-lost-ack",
                    "symbol": "T00", "side": "buy", "status": "filled", "qty": "1"}
    with pytest.raises(PB.OwnershipConflict, match="economics do not reconcile"):
        PB.recover_unclean_epoch_lease(journal_path=journal, broker=broker)
    assert PE._load(journal)["stock_intents"][0]["status"] == "SUBMIT_UNKNOWN"
    assert json.loads(lease_path.read_text(encoding="utf-8"))["open"] is True
    evidence["account"]["cash"] = "1900"
    evidence["account"]["equity"] = "5000"
    assert PB.recover_unclean_epoch_lease(journal_path=journal, broker=broker)[
        "status"] == "RECOVERED_CLOSED"
    assert PE._load(journal)["stock_intents"][0]["status"] == "FILLED"


def test_active_stock_crash_before_post_resumes_same_intent(tmp_path, monkeypatch):
    journal, contract, broker, plan = _active_stock_fixture(tmp_path, monkeypatch)
    original_evidence = broker.evidence
    calls = 0

    def interrupted_evidence(*, known_client_ids):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TimeoutError("offline crash before durable POST boundary")
        return original_evidence(known_client_ids=known_client_ids)

    broker.evidence = interrupted_evidence
    with pytest.raises(TimeoutError, match="before durable POST"):
        PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                               plan=plan, may_submit=True)
    before = PE._load(journal)["stock_intents"][0]
    assert before["status"] == "INTENT_PERSISTED" and broker.n_post == 0
    broker.evidence = original_evidence
    second = PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                                    plan=plan, may_submit=True)
    assert second["status"] == "ACKNOWLEDGED" and broker.n_post == 1
    assert PE._load(journal)["stock_intents"][0]["client_order_id"] == before["client_order_id"]


def test_active_stock_pre_post_intent_refuses_changed_capacity(tmp_path, monkeypatch):
    journal, contract, broker, plan = _active_stock_fixture(tmp_path, monkeypatch)
    original_evidence = broker.evidence
    calls = 0

    def interrupted_evidence(*, known_client_ids):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TimeoutError("offline crash before durable POST boundary")
        return original_evidence(known_client_ids=known_client_ids)

    broker.evidence = interrupted_evidence
    with pytest.raises(TimeoutError):
        PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                               plan=plan, may_submit=True)
    broker.evidence = original_evidence
    broker.cash -= 100
    broker.hold["OTHER"] = 1
    second = PE.execute_stock_cycle(journal, contract=contract, broker=broker,
                                    plan=plan, may_submit=True)
    assert second["status"] == "PENDING_PRE_POST_BOUNDARY" and broker.n_post == 0
