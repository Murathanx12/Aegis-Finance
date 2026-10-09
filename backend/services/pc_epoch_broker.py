"""Read-only evidence and one guarded submission adapter for the PC epoch.

The adapter has no timer or autonomous entry point. The owning sim supplies a
persisted transition intent; tests inject a fake pc_broker so the whole path is
replayed without contacting an account.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services import pc_broker as PB
from backend.services import pc_policy_epoch as PE


class PaperEpochBroker:
    def __init__(self, broker: Any = PB):
        self.broker = broker

    def _lease(self) -> dict:
        return json.loads(Path(self.broker.LEASE_PATH).read_text(encoding="utf-8"))

    def venue_open(self) -> bool:
        return bool((self.broker.clock() or {}).get("is_open"))

    def _orders_since(self, opened: str) -> list[dict]:
        """Page by broker order ID; an incomplete page never means no order."""
        def when(value: str) -> datetime:
            try:
                stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError as exc:
                raise PE.EpochRefused("order timestamp unreadable") from exc
            if stamp.tzinfo is None:
                raise PE.EpochRefused("order timestamp lacks zone")
            return stamp.astimezone(timezone.utc)

        opened_at = when(opened)
        result: list[dict] = []
        seen: set[str] = set()
        before = None
        previous_at = None
        for _ in range(50):
            page = self.broker.orders(status="all", limit=500,
                                      before_order_id=before)
            if not isinstance(page, list):
                raise PE.EpochRefused("order history unreadable")
            if not page:
                return result
            for order in page:
                oid = order.get("id")
                stamp = order.get("submitted_at")
                if not oid or not stamp or oid in seen:
                    raise PE.EpochRefused("order pagination ambiguous")
                seen.add(oid)
                submitted = when(stamp)
                if previous_at is not None and submitted > previous_at:
                    raise PE.EpochRefused("order history is not newest first")
                previous_at = submitted
                if submitted < opened_at:
                    return result
                result.append(order)
            if len(page) < 500:
                return result
            before = page[-1]["id"]
        raise PE.EpochRefused("order history exceeds bounded pagination")

    def evidence(self, *, known_client_ids: set[str] | None = None) -> dict:
        broker = self.broker
        if broker._host() != PE.PAPER_HOST:
            raise PE.EpochRefused("paper host mismatch")
        lease = self._lease()
        opened = lease.get("opened")
        if not opened:
            raise PE.EpochRefused("lease opening time missing")
        first_account = broker.account()
        first_positions = broker.positions()
        open_orders = broker.orders(status="open", limit=500)
        if not isinstance(open_orders, list) or len(open_orders) >= 500:
            raise PE.EpochRefused("open-order snapshot incomplete")
        history = self._orders_since(opened)
        last_account = broker.account()
        last_positions = broker.positions()
        last_open_orders = broker.orders(status="open", limit=500)
        def position_state(rows: list[dict]) -> list[tuple]:
            return sorted((p.get("symbol"), p.get("qty"), p.get("market_value"),
                           p.get("current_price")) for p in rows)
        open_state = lambda rows: [(r.get("id"), r.get("status"), r.get("filled_qty"))
                                   for r in rows]
        if (not isinstance(last_open_orders, list) or len(last_open_orders) >= 500
                or open_state(open_orders) != open_state(last_open_orders)
                or first_account.get("account_number") != last_account.get("account_number")
                or first_account.get("cash") != last_account.get("cash")
                or first_account.get("equity") != last_account.get("equity")
                or first_account.get("long_market_value") != last_account.get("long_market_value")
                or first_account.get("short_market_value") != last_account.get("short_market_value")
                or position_state(first_positions) != position_state(last_positions)):
            raise PE.EpochRefused("broker snapshot raced a change; retry later")
        allowed = known_client_ids or set()
        foreign = [order for order in history
                   if order.get("client_order_id") not in allowed]
        return {"host": broker._host(), "observed_utc": datetime.now(
                    timezone.utc).isoformat(), "lease": lease,
                "account": last_account, "positions": last_positions,
                "open_orders": open_orders, "orders_complete": True,
                "foreign_orders": foreign, "order_history": history}

    def order_by_client_id(self, client_id: str) -> dict | None:
        try:
            return self.broker.order_by_client_id(client_id)
        except PB.BrokerError as exc:
            if "HTTP 404" in str(exc):
                return None  # UNKNOWN, never a no-order proof
            raise

    def fills(self, order_id: str) -> list[dict]:
        result: list[dict] = []
        seen: set[str] = set()
        token = None
        for _ in range(50):
            page = self.broker.fill_activities(order_id, page_token=token)
            if not isinstance(page, list):
                raise PE.EpochRefused("fill history unreadable")
            for row in page:
                rid = row.get("id")
                if (not rid or rid in seen or row.get("order_id") != order_id
                        or row.get("activity_type") != "FILL"):
                    raise PE.EpochRefused("fill pagination or order identity ambiguous")
                seen.add(rid)
                result.append(row)
            if len(page) < 100:
                return result
            token = page[-1].get("id")
            if not token:
                raise PE.EpochRefused("fill page token missing")
        raise PE.EpochRefused("fill history exceeds bounded pagination")

    def submit_core_exit(self, *, intent: dict, journal: dict) -> dict:
        if (journal.get("state") != "EXIT_PENDING"
                or intent != journal.get("intent")
                or intent.get("submit_status") != "SUBMIT_UNKNOWN"):
            raise PE.EpochRefused("durable submit boundary absent")
        return self.broker.submit_epoch_core_exit(
            qty=int(intent["qty"]), client_order_id=intent["client_order_id"],
            session_id=journal["session_id"], session_nonce=journal["nonce"],
            account_fingerprint=journal["account_fingerprint"])

    def submit_stock_order(self, *, intent: dict, journal: dict,
                           minimum_cash_buffer: float, max_name_frac: float,
                           max_adv_participation: float) -> dict:
        if (journal.get("state") != "ACTIVE"
                or intent.get("status") != "SUBMIT_UNKNOWN"
                or intent not in (journal.get("stock_intents") or [])
                or intent.get("policy_epoch_sha256") != journal.get("content_sha256")):
            raise PE.EpochRefused("stock order lacks durable epoch boundary")
        return self.broker.submit_epoch_stock(
            symbol=intent["symbol"], side=intent["side"],
            qty=int(intent["qty"]), client_order_id=intent["client_order_id"],
            session_id=journal["session_id"], session_nonce=journal["nonce"],
            account_fingerprint=journal["account_fingerprint"],
            minimum_cash_buffer=minimum_cash_buffer,
            median_dollar_vol=intent.get("median_dollar_vol"),
            planned_price=intent.get("planned_price"),
            max_name_frac=max_name_frac,
            max_adv_participation=max_adv_participation,
            sleeve=intent.get("state"),
            risk_sigmas=intent.get("risk_sigmas"),
            revision_members=intent.get("revision_members"),
            probe_custody_symbols=intent.get("probe_custody_symbols"),
            starting_positions=intent.get("starting_positions"))
