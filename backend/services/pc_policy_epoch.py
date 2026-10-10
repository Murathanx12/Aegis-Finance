"""Frozen PC-PAPER no-index policy and durable transition journal.

The epoch has a selected orchestration path, but runtime activation is gated
off until independent review. No import or helper here contacts the broker.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ACTIVATION_ALLOWED = False
EXPECTED_CONTENT_SHA256 = "6a93d267b8a8d0e5b485c4f20488d6d90ca060082869085e21ab3e408ddbf587"
FROZEN_ACCOUNT_FINGERPRINT = "083ccc987a01685a7e5bb200ef6f5613d479c2bb72f02f234eec1e6d251f4898"
EXPECTED_ACCOUNT_FINGERPRINT = FROZEN_ACCOUNT_FINGERPRINT
EXPECTED_SOURCE_PATHS = frozenset({
    "backend/config.py",
    "backend/data/optimus/paper_accounts/fleet_manager/contracts/hack2_v2.json",
    "backend/services/decision_contract.py",
    "backend/services/decision_ledger.py",
    "backend/services/expected_return.py",
    "backend/services/investment_committee.py",
    "backend/services/pc_broker.py",
    "backend/services/pc_epoch_broker.py",
    "backend/services/pc_epoch_planner.py",
    "backend/services/pc_risk.py",
    "backend/services/pc_sleeves.py",
    "backend/services/policy_state.py",
    "backend/services/revision_flow.py",
    "backend/services/sim_session.py",
    "scripts/sim_run.py",
})
STATES = frozenset({"PREPARED", "EXIT_PENDING", "UNKNOWN", "DEGRADED",
                    "RECONCILED", "ACTIVE"})
PAPER_HOST = "https://paper-api.alpaca.markets"
EXPECTED_LIMITS = {
    "exploit_max_weight": 0.10,
    "gross_cap": 1.0,
    "leverage": 0.0,
    "max_adv_participation": 0.02,
    "max_orders_per_session": 120,
    "min_order_usd": 250.0,
    "one_day_worst_case_loss_frac": 0.10,
    "pending_orders_counted_as_risk": True,
    "probe_max_names": 10,
    "probe_max_weight": 0.02,
    "rebalance_drift_frac": 0.10,
    "revision_21_session_adverse_return": 0.3203,
    "revision_worst_21_session_loss_frac": 0.10,
    "rf_hold_counted_as_held_risk": True,
    "unknown_inputs": "block incremental risk, never zero",
    "worst_case_sigma_multiple": 3.0,
}


class EpochRefused(RuntimeError):
    """An epoch fact is missing, ambiguous, changed, or unsafe."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _source_sha(path: Path) -> str:
    """Hash source text independent of Git's Windows CRLF checkout setting."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise EpochRefused(f"{name} is unreadable") from exc
    if not result.is_finite():
        raise EpochRefused(f"{name} is not finite")
    return result


def _revision_row(root: Path, book_id: str) -> dict:
    path = root / "backend/data/optimus/llm_portfolio/books.jsonl"
    matches = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("book_id") == book_id:
            matches.append(row)
    if len(matches) != 1:
        raise EpochRefused("frozen revision book missing or duplicated")
    return matches[0]


def _load_contract(path: Path, *, root: Path, expected_hash: str,
                   strict_source_inventory: bool) -> dict:
    """Verify bytes, approved identity, frozen membership, sources and caps."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    content = raw.get("content")
    if not isinstance(content, dict) or raw.get("content_sha256") != _sha(content):
        raise EpochRefused("prepared policy content changed")
    if raw["content_sha256"] != expected_hash:
        raise EpochRefused("prepared policy identity is not the reviewed epoch")
    if content.get("schema") != "pc_paper_policy_epoch/v1":
        raise EpochRefused("unknown policy schema")
    if content.get("licence") != "PRODUCT_EXPERIMENT":
        raise EpochRefused("policy licence changed")
    if content.get("activation_allowed") is not False:
        raise EpochRefused("prepared epoch cannot activate")
    if content.get("strategic_index_target") is not None:
        raise EpochRefused("strategic index target must be absent")
    if content.get("epoch_id") != "PC_PAPER_NO_STRATEGIC_INDEX_2026_10_v1":
        raise EpochRefused("unexpected epoch identity")
    if content.get("excluded_strategic_index_symbols") != ["SPY"]:
        raise EpochRefused("index exclusion changed")
    if content.get("paper_account_fingerprint") != EXPECTED_ACCOUNT_FINGERPRINT:
        raise EpochRefused("approved paper account fingerprint changed")
    if strict_source_inventory and set(content.get("source_sha256") or {}) != EXPECTED_SOURCE_PATHS:
        raise EpochRefused("policy source inventory changed")
    if content.get("binding_limits") != EXPECTED_LIMITS:
        raise EpochRefused("binding risk limits changed")
    expiry = content.get("eligibility_and_expiry") or {}
    if (expiry.get("probe_horizons_sessions") != [5, 21, 63, 126]
            or expiry.get("revision_grade_horizons_sessions") != [1, 5, 21]
            or expiry.get("exploit_horizons_sessions") != [1, 5, 21]):
        raise EpochRefused("policy grading horizons changed")
    if (content.get("transition") or {}).get("not_before_utc") != "2026-10-12T13:30:00+00:00":
        raise EpochRefused("policy market gate changed")
    alloc = content.get("allocation") or {}
    if (alloc.get("revision_flow_gross_cap") != 0.30
            or alloc.get("probe_gross_cap") != 0.20
            or alloc.get("gross_cap") != 1.0
            or alloc.get("core_weight") != 0.0
            or alloc.get("non_core_name_cap") != 0.12
            or alloc.get("minimum_cash_buffer") != 0.01
            or alloc.get("cash_when_unqualified") != "RESERVE_NO_ELIGIBLE_RISK_CAPACITY"):
        raise EpochRefused("policy risk limits changed")
    revision = content.get("revision_flow") or {}
    row = _revision_row(Path(root), str(revision.get("book_id") or ""))
    names = [str(p.get("ticker") or "").upper() for p in row.get("positions") or []]
    if (len(names) != 20 or len(set(names)) != 20
            or sorted(names) != sorted(revision.get("members") or [])
            or _sha(row) != revision.get("book_row_sha256")):
        raise EpochRefused("revision membership or frozen row changed")
    for rel, expected in (content.get("source_sha256") or {}).items():
        source = (Path(root) / rel).resolve()
        if not source.is_relative_to(Path(root).resolve()):
            raise EpochRefused("source path escapes checkout")
        actual = _source_sha(source)
        if actual != expected:
            raise EpochRefused(f"policy source changed: {rel}")
    if not content.get("source_sha256"):
        raise EpochRefused("policy has no source manifest")
    return {"content": content, "content_sha256": raw["content_sha256"]}


def load_contract(path: Path, *, root: Path) -> dict:
    """Only the exact source-bound reviewed identity can enter the consumer."""
    selected = _load_contract(path, root=root, expected_hash=EXPECTED_CONTENT_SHA256,
                              strict_source_inventory=True)
    return {**selected, "path": str(Path(path).resolve())}


def account_fingerprint(account_number: str) -> str:
    if not account_number:
        raise EpochRefused("account number absent")
    return _sha({"host": PAPER_HOST, "account_number": str(account_number)})


def _identity(evidence: dict, *, session_id: str, nonce: str,
              fingerprint: str | None = None) -> str:
    """All later journal actions require a fresh, matching evidence bundle."""
    try:
        observed = datetime.fromisoformat(str(evidence["observed_utc"]))
        age = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
    except (KeyError, TypeError, ValueError) as exc:
        raise EpochRefused("broker evidence timestamp unreadable") from exc
    if observed.tzinfo is None or not -5 <= age <= 30:
        raise EpochRefused("broker evidence is stale or future-dated")
    lease = evidence.get("lease") or {}
    acct = evidence.get("account") or {}
    from backend.services import pc_broker as PB  # noqa: PLC0415
    birth = PB._process_birth_utc(os.getpid())
    if evidence.get("host") != PAPER_HOST:
        raise EpochRefused("paper host mismatch")
    if (not lease.get("open") or lease.get("owner") != f"sim_run {session_id}"
            or lease.get("session_nonce") != nonce or not nonce
            or lease.get("pid") != os.getpid()
            or not birth or lease.get("process_birth_utc") != birth
            or lease.get("account_number") != acct.get("account_number")):
        raise EpochRefused("session, nonce, process birth, account, or lease owner mismatch")
    fp = account_fingerprint(acct.get("account_number"))
    if fp != EXPECTED_ACCOUNT_FINGERPRINT:
        raise EpochRefused("account is not the approved PC paper account")
    if fingerprint is not None and fp != fingerprint:
        raise EpochRefused("account fingerprint changed")
    if evidence.get("orders_complete") is not True:
        raise EpochRefused("order history incomplete")
    if not isinstance(evidence.get("foreign_orders"), list):
        raise EpochRefused("foreign-order evidence absent")
    if evidence.get("foreign_orders"):
        raise EpochRefused("foreign or unresolved orders under the lease")
    _decimal(acct.get("equity"), "equity")
    _decimal(acct.get("cash"), "cash")
    return fp


def _economic(evidence: dict) -> dict:
    acct = evidence["account"]
    equity = _decimal(acct["equity"], "equity")
    cash = _decimal(acct["cash"], "cash")
    if equity <= 0 or cash < 0:
        raise EpochRefused("equity or cash invalid")
    if not isinstance(evidence.get("positions"), list):
        raise EpochRefused("position snapshot absent")
    gross = Decimal(0)
    spy = Decimal(0)
    symbols: set[str] = set()
    for p in evidence.get("positions") or []:
        sym = str(p.get("symbol") or "")
        if not sym or sym in symbols:
            raise EpochRefused("position symbol absent or duplicated")
        symbols.add(sym)
        qty = _decimal(p.get("qty"), "position quantity")
        mv = _decimal(p.get("market_value"), "position market value")
        if qty < 0 or mv < 0:
            raise EpochRefused("short or negative position")
        gross += mv
        if p.get("symbol") == "SPY":
            spy += qty
    if gross > equity + Decimal("0.01"):
        raise EpochRefused("gross exceeds equity")
    # Alpaca's equity and the sum of cash + marked long positions can differ
    # slightly during a quote update. A missing sale's proceeds are not a
    # quote tick: permit at most five basis points, and report the gap.
    gap = equity - (cash + gross)
    tolerance = max(Decimal("1"), equity * Decimal("0.0005"))
    if abs(gap) > tolerance:
        raise EpochRefused("cash plus positions does not reconcile to equity")
    return {"equity": str(equity), "cash": str(cash), "gross": str(gross),
            "economic_gap": str(gap), "economic_tolerance": str(tolerance),
            "spy_qty": str(spy), "spy_fractional_residual": str(spy % 1)}


def _pending_spy_sells(open_orders: list[dict]) -> Decimal:
    pending = Decimal(0)
    for order in open_orders:
        if order.get("symbol") != "SPY" or order.get("side") != "sell":
            continue
        qty = _decimal(order.get("qty"), "pending sell quantity")
        filled = _decimal(order.get("filled_qty"), "pending filled quantity")
        if qty < 0 or filled < 0 or filled > qty:
            raise EpochRefused("pending sell quantities invalid")
        pending += qty - filled
    return pending


@contextmanager
def _journal_mutex(path: Path):
    """The OS releases this lock on crash; a leftover file is harmless."""
    lock = path.with_name(path.name + ".lock")
    with lock.open("a+b") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(b"\0")
            fh.flush()
            os.fsync(fh.fileno())
        fh.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise EpochRefused("transition journal is owned by another writer") from exc
        try:
            yield
        finally:
            fh.seek(0)
            if os.name == "nt":
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _journal_mutex(path):
        expected = value.get("revision")
        if path.exists():
            current = json.loads(path.read_text(encoding="utf-8"))
            if expected != current.get("revision"):
                raise EpochRefused("transition journal changed concurrently")
        elif expected is not None:
            raise EpochRefused("transition journal disappeared")
        value["revision"] = (expected or 0) + 1
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(value, fh, sort_keys=True, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)


def _load(path: Path) -> dict:
    row = json.loads(path.read_text(encoding="utf-8"))
    if row.get("state") not in STATES or row.get("schema") != "pc_policy_transition/v1":
        raise EpochRefused("transition journal invalid")
    return row


def prepare(path: Path, *, contract: dict, evidence: dict,
            session_id: str, nonce: str, legacy_sources: dict,
            review_receipt: dict | None = None) -> dict:
    """Archive an observed legacy snapshot, not a retroactive policy freeze."""
    fp = _identity(evidence, session_id=session_id, nonce=nonce)
    economic = _economic(evidence)
    if not isinstance(evidence.get("open_orders"), list):
        raise EpochRefused("open-order snapshot absent")
    if path.exists():
        row = _load(path)
        if (row["content_sha256"] != contract["content_sha256"]
                or row["session_id"] != session_id or row["nonce"] != nonce
                or row["account_fingerprint"] != fp):
            raise EpochRefused("existing transition belongs to another epoch/session")
        return row
    if evidence.get("open_orders"):
        raise EpochRefused("open orders must reconcile before preparation")
    if not legacy_sources:
        raise EpochRefused("legacy observed source inventory missing")
    if review_receipt is not None and (
            review_receipt.get("approved") is not True
            or review_receipt.get("contract_sha256") != contract["content_sha256"]
            or not review_receipt.get("reviewed_utc")):
        raise EpochRefused("preparation review identity invalid")
    row = {"schema": "pc_policy_transition/v1", "state": "PREPARED",
           "transition_id": _sha({"content_sha256": contract["content_sha256"],
                                   "account": fp, "session_id": session_id,
                                   "nonce": nonce})[:24],
           "content_sha256": contract["content_sha256"], "session_id": session_id,
           "nonce": nonce, "account_fingerprint": fp,
           "selected_contract_path": contract.get("path"),
           "preparation_review": ({"approved": True,
                                   "contract_sha256": contract["content_sha256"],
                                   "reviewed_utc": review_receipt["reviewed_utc"]}
                                  if review_receipt is not None else None),
           "lease_pid": evidence["lease"]["pid"],
           "lease_birth_utc": evidence["lease"]["process_birth_utc"],
           "prepared_utc": _utc(),
           "legacy_observed_at": {"observed_utc": _utc(), "economic": economic,
                                  "positions": [
                                      {"symbol": p["symbol"], "qty": p["qty"],
                                       "market_value": p["market_value"]}
                                      for p in evidence["positions"]],
                                  "effective_sources": legacy_sources},
           "intent": None, "activation_allowed": False}
    _save(path, row)
    return row


def handoff(path: Path, *, contract: dict, old_closure: dict,
            old_session: dict, new_evidence: dict,
            new_session_id: str, new_nonce: str) -> dict:
    """Move custody after a clean stop; preserve transition and client IDs."""
    row = _load(path)
    if row["content_sha256"] != contract["content_sha256"]:
        raise EpochRefused("contract/journal mismatch")
    clean_end = old_session.get("state") in {"STOPPED", "COMPLETED"}
    recovered_end = (old_session.get("state") == "UNCLEAN"
                     and old_closure.get("recovered_from_unclean") is True
                     and old_closure.get("journal_revision") == row.get("revision")
                     and old_closure.get("journal_sha256") == _sha(row))
    if (old_session.get("id") != row["session_id"]
            or not (clean_end or recovered_end)
            or old_closure.get("open") is not False
            or old_closure.get("owner") != f"sim_run {row['session_id']}"
            or old_closure.get("session_nonce") != row["nonce"]
            or old_closure.get("pid") != row.get("lease_pid")
            or old_closure.get("process_birth_utc") != row.get("lease_birth_utc")
            or old_session.get("pid") != row.get("lease_pid")
            or account_fingerprint(old_closure.get("account_number"))
               != row["account_fingerprint"]
            or not old_closure.get("closed")):
        raise EpochRefused("prior session did not finish and release its lease")
    _identity(new_evidence, session_id=new_session_id, nonce=new_nonce,
              fingerprint=row["account_fingerprint"])
    _economic(new_evidence)
    old_id, old_nonce = row["session_id"], row["nonce"]
    row["session_id"], row["nonce"] = new_session_id, new_nonce
    row["lease_pid"] = new_evidence["lease"]["pid"]
    row["lease_birth_utc"] = new_evidence["lease"]["process_birth_utc"]
    row.setdefault("handoffs", []).append({"from_session": old_id,
                                             "from_nonce": old_nonce,
                                             "to_session": new_session_id,
                                             "to_nonce": new_nonce,
                                             "observed_utc": _utc(),
                                             "prior_state": old_session["state"]})
    _save(path, row)
    return row


def plan_core_exit(path: Path, *, contract: dict, evidence: dict) -> dict:
    """Persist the deterministic sell intent BEFORE any future broker send."""
    row = _load(path)
    if row["content_sha256"] != contract["content_sha256"]:
        raise EpochRefused("contract/journal mismatch")
    _identity(evidence, session_id=row["session_id"], nonce=row["nonce"],
              fingerprint=row["account_fingerprint"])
    if not isinstance(evidence.get("open_orders"), list):
        raise EpochRefused("open-order snapshot absent")
    if row["state"] == "EXIT_PENDING" and row.get("intent"):
        # The persisted body is evidence of the original attempt, NOT authority
        # to send it again. A restart must resolve the deterministic ID first.
        # Re-read economics and pending risk before reporting even this hold.
        snap = _economic(evidence)
        pending = _pending_spy_sells(evidence.get("open_orders"))
        capacity = _decimal(snap["spy_qty"], "SPY quantity") - pending
        if capacity < _decimal(row["intent"]["qty"], "intent quantity"):
            row["state"] = "UNKNOWN"
            row["reason"] = "cached intent exceeds fresh held-minus-pending capacity"
            _save(path, row)
        return row
    if row["state"] != "PREPARED":
        raise EpochRefused(f"cannot create exit intent in {row['state']}")
    snap = _economic(evidence)
    # Any unresolved order can change held risk or buying power.  Do not infer
    # it is harmless from a symbol, side, or shared client-ID prefix.
    if evidence.get("open_orders"):
        raise EpochRefused("pending orders require reconciliation")
    qty = _decimal(snap["spy_qty"], "SPY quantity")
    whole = math.floor(qty)
    if whole == 0:
        row["state"] = "RECONCILED"
        row["reconciled_utc"] = _utc()
        row["reconciled_economic"] = snap
        _save(path, row)
        return row
    client_id = "aegispc-e" + _sha({"transition_id": row["transition_id"],
                                    "leg": 1})[:20]
    row["state"] = "EXIT_PENDING"
    row["intent"] = {"client_order_id": client_id, "symbol": "SPY",
                     "side": "sell", "qty": str(whole),
                     "reason": "POLICY_EPOCH_EXIT_CORE",
                     "prepared_utc": _utc(), "submit_status": "NOT_SENT"}
    _save(path, row)
    return row


def seal_send_intent(path: Path, *, contract: dict, evidence: dict) -> dict:
    """The last recoverable boundary before a broker POST can be attempted."""
    row = _load(path)
    if row["content_sha256"] != contract["content_sha256"]:
        raise EpochRefused("contract/journal mismatch")
    _identity(evidence, session_id=row["session_id"], nonce=row["nonce"],
              fingerprint=row["account_fingerprint"])
    snap = _economic(evidence)
    intent = row.get("intent") or {}
    if (row["state"] != "EXIT_PENDING" or intent.get("submit_status") != "NOT_SENT"
            or evidence.get("open_orders")
            or _decimal(snap["spy_qty"], "SPY quantity")
               < _decimal(intent.get("qty"), "intent quantity")):
        raise EpochRefused("exit intent no longer has verified sell capacity")
    intent["submit_status"] = "SEND_INTENT_PERSISTED"
    intent["send_prepared_utc"] = _utc()
    _save(path, row)
    return row


def begin_post(path: Path, *, contract: dict, evidence: dict) -> dict:
    """Persist SUBMIT_UNKNOWN before crossing the network boundary."""
    row = _load(path)
    if row["content_sha256"] != contract["content_sha256"]:
        raise EpochRefused("contract/journal mismatch")
    _identity(evidence, session_id=row["session_id"], nonce=row["nonce"],
              fingerprint=row["account_fingerprint"])
    snap = _economic(evidence)
    intent = row.get("intent") or {}
    if (row["state"] != "EXIT_PENDING"
            or intent.get("submit_status") != "SEND_INTENT_PERSISTED"
            or evidence.get("open_orders")
            or _decimal(snap["spy_qty"], "SPY quantity")
               < _decimal(intent.get("qty"), "intent quantity")):
        raise EpochRefused("send boundary no longer has verified sell capacity")
    intent["submit_status"] = "SUBMIT_UNKNOWN"
    intent["post_boundary_utc"] = _utc()
    _save(path, row)
    return row


def acknowledge_post(path: Path, *, contract: dict, evidence: dict,
                     response: dict) -> dict:
    """An ACK annotates the same intent; it never creates a second one."""
    row = _load(path)
    intent = row.get("intent") or {}
    _identity(evidence, session_id=row["session_id"], nonce=row["nonce"],
              fingerprint=row["account_fingerprint"])
    if (row["content_sha256"] != contract["content_sha256"]
            or row["state"] != "EXIT_PENDING"
            or intent.get("submit_status") != "SUBMIT_UNKNOWN"):
        raise EpochRefused("acknowledgement has no matching submit boundary")
    if (response.get("client_order_id") != intent["client_order_id"]
            or response.get("symbol") != "SPY" or response.get("side") != "sell"
            or _decimal(response.get("qty"), "ack quantity")
               != _decimal(intent["qty"], "intent quantity")
            or not response.get("id")):
        row["state"] = "UNKNOWN"
        row["reason"] = "broker acknowledgement disagrees with intent"
    else:
        intent["submit_status"] = "ACKNOWLEDGED"
        intent["broker_order_id"] = response["id"]
    _save(path, row)
    return row


def observe_core_exit(path: Path, *, contract: dict, evidence: dict,
                      matched_order: dict | None,
                      fills: list[dict] | None = None) -> dict:
    """Reconcile one pre-recorded intent; absence/404 is UNKNOWN, never retry."""
    row = _load(path)
    if row["content_sha256"] != contract["content_sha256"]:
        raise EpochRefused("contract/journal mismatch")
    _identity(evidence, session_id=row["session_id"], nonce=row["nonce"],
              fingerprint=row["account_fingerprint"])
    if not isinstance(evidence.get("open_orders"), list):
        raise EpochRefused("open-order snapshot absent")
    if row["state"] not in {"EXIT_PENDING", "UNKNOWN", "DEGRADED", "RECONCILED"}:
        raise EpochRefused(f"cannot reconcile in {row['state']}")
    intent = row.get("intent")
    if not intent:
        raise EpochRefused("exit intent absent")
    if matched_order is None:
        row["state"] = "UNKNOWN"
        row["reason"] = "deterministic client order ID not resolved; no retry"
    elif (matched_order.get("client_order_id") != intent["client_order_id"]
          or matched_order.get("symbol") != "SPY"
          or matched_order.get("side") != "sell"
          or _decimal(matched_order.get("qty"), "order quantity")
          != _decimal(intent["qty"], "intent quantity")):
        row["state"] = "UNKNOWN"
        row["reason"] = "broker order and durable intent disagree"
    else:
        status = str(matched_order.get("status") or "").lower()
        filled_qty = _decimal(matched_order.get("filled_qty"), "filled quantity")
        if filled_qty < 0 or filled_qty > _decimal(intent["qty"], "intent quantity"):
            raise EpochRefused("broker fill quantity invalid")
        try:
            snap = _economic(evidence)
        except EpochRefused as exc:
            row["state"] = "DEGRADED"
            row["reason"] = f"economic reconciliation refused: {exc}"
            row["observed_utc"] = _utc()
            _save(path, row)
            return row
        open_orders = evidence.get("open_orders") or []
        if status in {"new", "accepted", "pending_new", "partially_filled"}:
            row["state"] = "EXIT_PENDING"
            row["reason"] = "core exit still pending"
        elif (status == "filled" and filled_qty == _decimal(intent["qty"], "intent quantity")
              and not open_orders and _decimal(
                  snap["spy_qty"], "SPY residual") < 1):
            try:
                if not isinstance(fills, list) or not fills or not matched_order.get("id"):
                    raise EpochRefused("broker fill activities absent")
                unique: set[str] = set()
                fill_qty, proceeds = Decimal(0), Decimal(0)
                for fill in fills:
                    fid = fill.get("id")
                    if (not fid or fid in unique or fill.get("order_id") != matched_order["id"]
                            or fill.get("symbol") != "SPY" or fill.get("side") != "sell"
                            or fill.get("activity_type") != "FILL"):
                        raise EpochRefused("fill identity or pagination ambiguous")
                    unique.add(fid)
                    q = _decimal(fill.get("qty"), "fill quantity")
                    px = _decimal(fill.get("price"), "fill price")
                    if q <= 0 or px <= 0:
                        raise EpochRefused("fill price or quantity invalid")
                    fill_qty += q
                    proceeds += q * px
                if fill_qty != filled_qty:
                    raise EpochRefused("fill activities do not match order quantity")
                starting_cash = _decimal(
                    row["legacy_observed_at"]["economic"]["cash"], "opening cash")
                cash_delta = _decimal(snap["cash"], "closing cash") - starting_cash
                tolerance = max(Decimal("0.01"), proceeds * Decimal("0.0001"))
                if abs(cash_delta - proceeds) > tolerance:
                    raise EpochRefused("measured sale proceeds do not reconcile to cash")
            except EpochRefused as exc:
                row["state"] = "DEGRADED"
                row["reason"] = f"fill reconciliation refused: {exc}"
            else:
                row["state"] = "RECONCILED"
                row["reason"] = "whole-share core removed; fractional residual recorded"
                row["reconciled_utc"] = _utc()
                row["reconciled_economic"] = snap
                row["fill_economic"] = {"qty": str(fill_qty), "proceeds": str(proceeds),
                                        "cash_delta": str(cash_delta)}
        else:
            row["state"] = "DEGRADED"
            row["reason"] = ("rejected/canceled/partial exit, residual whole shares, "
                             "or unresolved open orders")
    row["observed_utc"] = _utc()
    _save(path, row)
    return row


def transition_cycle(path: Path, *, contract: dict, broker: Any,
                     session_id: str, nonce: str,
                     legacy_sources: dict, may_submit: bool,
                     review_receipt: dict | None = None) -> dict:
    """One bounded owner cycle through evidence, durable intent and broker.

    A failed or timed-out POST is never retried. A later cycle resolves the
    deterministic client ID and broker fills. The caller decides whether the
    venue window permits submission; the guarded broker method checks again.
    """
    before = _load(path) if path.exists() else None
    known = stock_client_ids(before) if before else set()
    evidence = broker.evidence(known_client_ids=known)
    if before is None:
        row = prepare(path, contract=contract, evidence=evidence,
                      session_id=session_id, nonce=nonce,
                      legacy_sources=legacy_sources,
                      review_receipt=review_receipt)
    else:
        row = before
        _identity(evidence, session_id=row["session_id"], nonce=row["nonce"],
                  fingerprint=row["account_fingerprint"])
        if row["session_id"] != session_id or row["nonce"] != nonce:
            raise EpochRefused("transition requires a reviewed owner handoff")
    if row["state"] == "ACTIVE":
        return row
    if row["state"] == "PREPARED":
        row = plan_core_exit(path, contract=contract, evidence=evidence)
    if row["state"] == "RECONCILED":
        return row
    intent = row.get("intent")
    if not intent:
        return row
    # Resolve before any future send, including a fresh NOT_SENT row. A 404
    # after SUBMIT_UNKNOWN is UNKNOWN, not permission to retry.
    matched = broker.order_by_client_id(intent["client_order_id"])
    if matched is not None:
        if intent["submit_status"] in {"NOT_SENT", "SEND_INTENT_PERSISTED"}:
            row = _load(path)
            row["state"] = "UNKNOWN"
            row["reason"] = "broker order exists before authorized POST boundary"
            _save(path, row)
            return row
        fills = (broker.fills(matched["id"]) if matched.get("id")
                 and _decimal(matched.get("filled_qty") or 0, "filled quantity") > 0 else [])
        fresh = broker.evidence(known_client_ids={intent["client_order_id"]})
        return observe_core_exit(path, contract=contract, evidence=fresh,
                                 matched_order=matched, fills=fills)
    if intent["submit_status"] in {"SUBMIT_UNKNOWN", "ACKNOWLEDGED"}:
        return observe_core_exit(path, contract=contract, evidence=evidence,
                                 matched_order=None)
    if row["state"] != "EXIT_PENDING" or not may_submit:
        return row
    if intent["submit_status"] == "NOT_SENT":
        row = seal_send_intent(path, contract=contract, evidence=evidence)
    fresh = broker.evidence(known_client_ids={intent["client_order_id"]})
    row = begin_post(path, contract=contract, evidence=fresh)
    try:
        response = broker.submit_core_exit(intent=row["intent"], journal=row)
    except Exception as exc:  # noqa: BLE001 -- network outcome is unknown
        row = _load(path)
        row["reason"] = f"submit outcome UNKNOWN: {type(exc).__name__}: {str(exc)[:100]}"
        _save(path, row)
        return row
    fresh = broker.evidence(known_client_ids={intent["client_order_id"]})
    return acknowledge_post(path, contract=contract, evidence=fresh,
                            response=response)


def activate(path: Path, *, contract: dict, evidence: dict,
             review_receipt: dict | None, venue_open: bool,
             now_utc: datetime | None = None) -> dict:
    """Append actual inception only after review, venue and economic proof.

    The checked-in code gate is OFF. Offline tests may enable it in an isolated
    fixture; a later reviewed deployment must change that gate explicitly.
    """
    if not ACTIVATION_ALLOWED:
        raise EpochRefused("activation disabled pending independent review")
    row = _load(path)
    if row["content_sha256"] != contract["content_sha256"]:
        raise EpochRefused("contract/journal mismatch")
    if row["state"] == "ACTIVE":
        return row
    if row["state"] != "RECONCILED":
        raise EpochRefused("exit not economically reconciled")
    if (not isinstance(review_receipt, dict)
            or review_receipt.get("approved") is not True
            or review_receipt.get("contract_sha256") != contract["content_sha256"]
            or not review_receipt.get("reviewed_utc")):
        raise EpochRefused("independent activation review receipt absent")
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise EpochRefused("activation time lacks UTC zone")
    try:
        reviewed = datetime.fromisoformat(review_receipt["reviewed_utc"])
        not_before = datetime.fromisoformat(
            contract["content"]["transition"]["not_before_utc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EpochRefused("review or market gate timestamp invalid") from exc
    if (reviewed.tzinfo is None or not_before.tzinfo is None
            or reviewed > now or now < not_before or not venue_open):
        raise EpochRefused("review, not-before or paper venue gate unmet")
    _identity(evidence, session_id=row["session_id"], nonce=row["nonce"],
              fingerprint=row["account_fingerprint"])
    economic = _economic(evidence)
    if (evidence.get("open_orders") or _decimal(economic["spy_qty"], "SPY residual") >= 1
            or _decimal(economic["cash"], "cash")
               < _decimal(economic["equity"], "equity") * Decimal("0.01")):
        raise EpochRefused("pending orders, strategic SPY or cash buffer remain")
    if (_decimal(row["legacy_observed_at"]["economic"]["spy_qty"], "opening SPY") >= 1
            and not row.get("fill_economic")):
        raise EpochRefused("broker fill economics absent")
    row["state"] = "ACTIVE"
    row["activated_utc"] = now.astimezone(timezone.utc).isoformat(timespec="seconds")
    row["opening_economic"] = economic
    row["activation_review"] = {"approved": True,
                                "reviewed_utc": review_receipt["reviewed_utc"],
                                "contract_sha256": contract["content_sha256"]}
    _save(path, row)
    return row


def stock_client_ids(row: dict) -> set[str]:
    ids = {x["client_order_id"] for x in row.get("stock_intents") or []}
    if row.get("intent"):
        ids.add(row["intent"]["client_order_id"])
    return ids


def observed_legacy_shadow(row: dict, prices: dict[str, float]) -> dict:
    """Price the archived legacy holdings as a no-trade counterfactual.

    This is a free holdings shadow, not a simulation of the old dynamic policy
    or a cashflow-adjusted broker return. Unknown marks never become zero.
    """
    old = row["legacy_observed_at"]
    economic = old["economic"]
    base_equity = _decimal(economic["equity"], "legacy opening equity")
    value = _decimal(economic["cash"], "legacy opening cash")
    missing = []
    control = {"status": "CANNOT_DETERMINE", "reason": "opening SPY position absent"}
    for position in old.get("positions") or []:
        symbol = str(position["symbol"])
        qty = _decimal(position["qty"], "legacy held quantity")
        opening_value = _decimal(position["market_value"], "legacy market value")
        mark = prices.get(symbol)
        if mark is None or _decimal(mark, "legacy shadow price") <= 0:
            missing.append(symbol)
            continue
        current_value = qty * _decimal(mark, "legacy shadow price")
        value += current_value
        if symbol == "SPY" and qty > 0 and opening_value > 0:
            control = {"status": "PRICED", "symbol": "SPY",
                       "price_return": float(current_value / opening_value - 1),
                       "basis": "observed pre-transition SPY mark"}
    if missing:
        shadow = {"status": "CANNOT_DETERMINE", "missing_marks": sorted(missing)}
    else:
        shadow = {"status": "PRICED", "equity_usd": float(value),
                  "price_return": float(value / base_equity - 1),
                  "basis": "observed legacy holdings, no trades or funding"}
    return {"old_observed_holdings": shadow, "separate_spy_control": control,
            "reporting_only": True}


def execute_stock_cycle(path: Path, *, contract: dict, broker: Any,
                        plan: dict, may_submit: bool) -> dict:
    """Reconcile past stock intents, then at most one new contract-planned leg."""
    row = _load(path)
    if row["state"] != "ACTIVE" or row["content_sha256"] != contract["content_sha256"]:
        raise EpochRefused("stock cycle requires the active reviewed epoch")
    if plan.get("policy_epoch_sha256") != contract["content_sha256"]:
        raise EpochRefused("stock plan did not consume the active contract")
    evidence = broker.evidence(known_client_ids=stock_client_ids(row))
    _identity(evidence, session_id=row["session_id"], nonce=row["nonce"],
              fingerprint=row["account_fingerprint"])
    economic = _economic(evidence)
    intents = row.setdefault("stock_intents", [])
    resume_intent = None
    reconciled_any = False
    for intent in intents:
        if intent["status"] == "FILLED":
            continue
        if intent["status"] == "GUARD_REFUSED_NO_POST":
            if broker.order_by_client_id(intent["client_order_id"]) is not None:
                intent["status"] = "UNKNOWN"
                row["stock_block"] = "order appeared after proven no-POST guard refusal"
                _save(path, row)
                return {"status": "UNKNOWN", "intent": intent}
            continue
        matched = broker.order_by_client_id(intent["client_order_id"])
        if matched is None:
            if intent["status"] == "INTENT_PERSISTED":
                if intent is not intents[-1]:
                    raise EpochRefused("nonterminal stock intent precedes a later leg")
                resume_intent = intent
                break
            intent["status"] = "UNKNOWN"
            row["stock_block"] = "stock broker lookup absent/404; never retry"
            _save(path, row)
            return {"status": "UNKNOWN", "intent": intent}
        if intent["status"] == "INTENT_PERSISTED":
            intent["status"] = "UNKNOWN"
            row["stock_block"] = "stock order predates authorized POST boundary"
            _save(path, row)
            return {"status": "UNKNOWN", "intent": intent}
        if (matched.get("client_order_id") != intent["client_order_id"]
                or matched.get("symbol") != intent["symbol"]
                or matched.get("side") != intent["side"]
                or _decimal(matched.get("qty"), "stock order quantity")
                   != _decimal(intent["qty"], "stock intent quantity")):
            intent["status"] = "UNKNOWN"
            row["stock_block"] = "stock broker order differs from durable intent"
            _save(path, row)
            return {"status": "UNKNOWN", "intent": intent}
        status = str(matched.get("status") or "").lower()
        if status in {"new", "accepted", "pending_new", "partially_filled"}:
            return {"status": "PENDING_BROKER", "intent": intent}
        if status != "filled" or not matched.get("id"):
            intent["status"] = "DEGRADED"
            row["stock_block"] = "stock order rejected/canceled/ambiguous"
            _save(path, row)
            return {"status": "DEGRADED", "intent": intent}
        fills = broker.fills(matched["id"])
        total_qty, cash_flow, seen = Decimal(0), Decimal(0), set()
        for fill in fills:
            fid = fill.get("id")
            if (not fid or fid in seen or fill.get("order_id") != matched["id"]
                    or fill.get("symbol") != intent["symbol"]
                    or fill.get("side") != intent["side"]
                    or fill.get("activity_type") != "FILL"):
                raise EpochRefused("stock fill evidence ambiguous")
            seen.add(fid)
            q = _decimal(fill.get("qty"), "stock fill quantity")
            px = _decimal(fill.get("price"), "stock fill price")
            if q <= 0 or px <= 0:
                raise EpochRefused("stock fill price or quantity invalid")
            total_qty += q
            cash_flow += q * px * (1 if intent["side"] == "sell" else -1)
        current_qty = sum(_decimal(p["qty"], "current position")
                          for p in evidence["positions"]
                          if p.get("symbol") == intent["symbol"])
        expected_qty = (_decimal(intent["starting_qty"], "starting position")
                        + _decimal(intent["qty"], "stock intent quantity")
                          * (1 if intent["side"] == "buy" else -1))
        cash_delta = (_decimal(economic["cash"], "cash")
                      - _decimal(intent["starting_cash"], "starting cash"))
        tolerance = max(Decimal("0.01"), abs(cash_flow) * Decimal("0.0001"))
        if (total_qty != _decimal(intent["qty"], "stock intent quantity")
                or current_qty != expected_qty
                or abs(cash_delta - cash_flow) > tolerance):
            intent["status"] = "DEGRADED"
            row["stock_block"] = "stock fill, holdings or cash did not reconcile"
            _save(path, row)
            return {"status": "DEGRADED", "intent": intent}
        intent["status"] = "FILLED"
        intent["filled_utc"] = _utc()
        intent["measured_cash_flow"] = str(cash_flow)
        _save(path, row)
        row = _load(path)
        reconciled_any = True
    intents = row.setdefault("stock_intents", [])
    if reconciled_any:
        return {"status": "REPLAN_REQUIRED", "reason": "filled stock leg changed holdings"}
    if not may_submit or evidence["open_orders"] or not plan.get("sendable"):
        return {"status": "NO_NEW_ORDER", "reason": "venue/pending/no eligible order"}
    plan_sha = _sha(plan)
    if (resume_intent is None and intents
            and intents[-1].get("status") == "GUARD_REFUSED_NO_POST"
            and intents[-1].get("plan_sha256") == plan_sha):
        return {"status": "REPLAN_REQUIRED",
                "reason": "same plan was refused before POST; refresh risk and quote"}
    session_intents = [i for i in intents if i.get("session_id") == row["session_id"]
                       and i.get("status") != "GUARD_REFUSED_NO_POST"]
    if (resume_intent is None and len(session_intents)
            >= int(contract["content"]["binding_limits"]["max_orders_per_session"])):
        raise EpochRefused("epoch stock order count cap reached")
    if abs(_decimal(economic["equity"], "equity")
           - _decimal(plan["equity_at_plan"], "plan equity")) > (
              _decimal(economic["equity"], "equity") * Decimal("0.001")):
        raise EpochRefused("equity moved since stock sizing")
    chosen = plan["sendable"][0]  # broker planner sorts sells first
    if (chosen["symbol"] == "SPY" or chosen["qty"] <= 0
            or chosen["side"] not in {"buy", "sell"}):
        raise EpochRefused("stock plan contains forbidden order")
    starting_qty = sum(_decimal(p["qty"], "starting position")
                       for p in evidence["positions"] if p.get("symbol") == chosen["symbol"])
    starting_positions = {str(p["symbol"]): str(_decimal(p["qty"], "starting position").normalize())
                          for p in evidence["positions"]}
    if chosen["side"] == "sell" and starting_qty < chosen["qty"]:
        raise EpochRefused("stock sell exceeds fresh held shares")
    if resume_intent is not None:
        if (resume_intent["symbol"] != chosen["symbol"]
                or resume_intent["side"] != chosen["side"]
                or _decimal(resume_intent["qty"], "persisted stock quantity")
                   != _decimal(chosen["qty"], "current stock quantity")
                or _decimal(resume_intent["starting_qty"], "persisted holdings")
                   != starting_qty
                or _decimal(resume_intent["starting_cash"], "persisted cash")
                   != _decimal(economic["cash"], "current cash")
                or _decimal(resume_intent.get("median_dollar_vol"), "persisted ADV")
                   != _decimal(chosen.get("median_dollar_vol"), "current ADV")
                or _decimal(resume_intent.get("planned_price"), "persisted price")
                   != _decimal(chosen.get("price"), "current plan price")
                or resume_intent.get("state") != chosen.get("state")
                or resume_intent.get("risk_sigmas") != plan.get("risk_sigmas")
                or resume_intent.get("probe_custody_symbols")
                   != plan.get("probe_custody_symbols")
                or resume_intent.get("starting_positions") != starting_positions):
            return {"status": "PENDING_PRE_POST_BOUNDARY",
                    "reason": "current plan/economics differ from persisted intent"}
        intent = resume_intent
    else:
        client_id = "aegispc-s" + _sha({"transition_id": row["transition_id"],
                                        "leg": len(intents) + 1, "symbol": chosen["symbol"],
                                        "side": chosen["side"], "qty": chosen["qty"]})[:20]
        intent = {"client_order_id": client_id, "symbol": chosen["symbol"],
                  "side": chosen["side"], "qty": str(chosen["qty"]),
                  "state": chosen["state"],
                  "median_dollar_vol": str(chosen["median_dollar_vol"]),
                  "planned_price": str(chosen["price"]),
                  "session_id": row["session_id"],
                  "risk_sigmas": plan["risk_sigmas"],
                  "revision_members": plan["revision_members"],
                  "probe_custody_symbols": plan["probe_custody_symbols"],
                  "starting_qty": str(starting_qty), "starting_cash": economic["cash"],
                  "starting_positions": starting_positions,
                  "plan_sha256": plan_sha,
                  "policy_epoch_sha256": contract["content_sha256"],
                  "status": "INTENT_PERSISTED", "prepared_utc": _utc()}
        intents.append(intent)
        _save(path, row)
    client_id = intent["client_order_id"]
    # Nothing has crossed POST yet. Resolve the new ID and re-read the account
    # before durably entering the ambiguous network window.
    if broker.order_by_client_id(client_id) is not None:
        row = _load(path)
        row["stock_intents"][-1]["status"] = "UNKNOWN"
        row["stock_block"] = "stock client ID already exists before POST"
        _save(path, row)
        return {"status": "UNKNOWN", "intent": row["stock_intents"][-1]}
    fresh = broker.evidence(known_client_ids=stock_client_ids(row))
    _identity(fresh, session_id=row["session_id"], nonce=row["nonce"],
              fingerprint=row["account_fingerprint"])
    fresh_economic = _economic(fresh)
    fresh_qty = sum(_decimal(p["qty"], "fresh position")
                    for p in fresh["positions"] if p.get("symbol") == chosen["symbol"])
    fresh_positions = {str(p["symbol"]): str(_decimal(p["qty"], "fresh position").normalize())
                       for p in fresh["positions"]}
    if (fresh["open_orders"] or fresh_qty != starting_qty
            or fresh_positions != starting_positions
            or _decimal(fresh_economic["cash"], "fresh cash")
               != _decimal(economic["cash"], "plan cash")):
        return {"status": "PENDING_PRE_POST_BOUNDARY", "intent": intent}
    row = _load(path)
    row["stock_intents"][-1]["status"] = "SUBMIT_UNKNOWN"
    row["stock_intents"][-1]["post_boundary_utc"] = _utc()
    _save(path, row)
    from backend.services import pc_broker as PB  # noqa: PLC0415
    try:
        response = broker.submit_stock_order(
            intent=row["stock_intents"][-1], journal=row,
            minimum_cash_buffer=float(contract["content"]["allocation"]["minimum_cash_buffer"]),
            max_name_frac=float(contract["content"]["allocation"]["non_core_name_cap"]),
            max_adv_participation=float(
                contract["content"]["binding_limits"]["max_adv_participation"]))
    except PB.EpochPreSubmitRefused as exc:
        row = _load(path)
        row["stock_intents"][-1]["status"] = "GUARD_REFUSED_NO_POST"
        row["stock_intents"][-1]["guard_refused_utc"] = _utc()
        row["stock_block"] = f"pre-submit guard refused: {str(exc)[:100]}"
        _save(path, row)
        return {"status": "REPLAN_REQUIRED", "reason": row["stock_block"]}
    except Exception as exc:  # noqa: BLE001 -- POST outcome is ambiguous
        return {"status": "SUBMIT_UNKNOWN", "reason": f"{type(exc).__name__}: {str(exc)[:100]}"}
    if (response.get("client_order_id") != client_id
            or response.get("symbol") != chosen["symbol"]
            or response.get("side") != chosen["side"]
            or _decimal(response.get("qty"), "stock ack quantity")
               != _decimal(chosen["qty"], "stock plan quantity")
            or not response.get("id")):
        return {"status": "SUBMIT_UNKNOWN", "reason": "stock acknowledgement disagrees"}
    row = _load(path)
    row["stock_intents"][-1]["status"] = "ACKNOWLEDGED"
    row["stock_intents"][-1]["broker_order_id"] = response["id"]
    _save(path, row)
    return {"status": "ACKNOWLEDGED", "symbol": chosen["symbol"],
            "side": chosen["side"], "qty": chosen["qty"],
            "client_order_id": client_id}
