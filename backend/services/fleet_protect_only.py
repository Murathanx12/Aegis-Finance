"""One-shot protection of a late fleet fill; no entry, exit, cancel or rebaseline."""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from backend.services import fleet_manager as FM

RESTING_STOP_STATUSES = frozenset({"new", "accepted", "partially_filled", "held"})


def _number(value: Any, name: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool):
        raise FM.FleetRefusal(f"{name}: boolean is not a broker quantity")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise FM.FleetRefusal(f"{name}: unreadable") from exc
    if not math.isfinite(result) or result < minimum:
        raise FM.FleetRefusal(f"{name}: nonfinite or negative")
    return result


def _ledger_rows(base: Path) -> list[dict]:
    path = FM.decisions_path(base)
    if not path.exists():
        return []
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    except (OSError, ValueError) as exc:
        raise FM.FleetRefusal("decision/outcome ledger unreadable; prior POST unknown") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise FM.FleetRefusal("decision/outcome ledger malformed; prior POST unknown")
    return rows


def _accepted_orders(role: str, base: Path) -> dict[str, dict]:
    """Exact accepted local order evidence, never prefix-only ownership."""
    decisions: dict[tuple[str, str], dict] = {}
    outcomes: dict[tuple[str, str], dict] = {}
    for row in _ledger_rows(base):
        if row.get("role") != role or not row.get("run_id") or not row.get("coid"):
            continue
        key = (str(row["run_id"]), str(row["coid"]))
        if row.get("row") == "decision" and row.get("mode") == "LIVE" and not row.get("refused"):
            if key in decisions:
                raise FM.FleetRefusal("duplicate LIVE order decision identity")
            decisions[key] = row
        elif row.get("row") == "outcome" and str(row.get("outcome") or "").startswith("submitted "):
            if key in outcomes:
                raise FM.FleetRefusal("duplicate accepted order outcome identity")
            outcomes[key] = row
    by_id: dict[str, dict] = {}
    for key, outcome in outcomes.items():
        if key not in decisions or not outcome.get("order_id"):
            raise FM.FleetRefusal("accepted outcome has no exact LIVE decision/order id")
        decision = decisions[key]
        if (decision.get("type") not in (*FM.STOP_TYPES, "limit")
                or decision.get("side") not in {"buy", "sell"}
                or not decision.get("symbol")):
            raise FM.FleetRefusal("accepted order decision shape unknown")
        qty = _number(decision.get("qty"), "accepted order quantity", minimum=0.000001)
        oid = str(outcome["order_id"])
        if oid in by_id:
            raise FM.FleetRefusal("broker order id has conflicting accepted outcomes")
        by_id[oid] = {"coid": key[1], "symbol": decision["symbol"],
                      "side": decision["side"], "type": decision["type"], "qty": qty,
                      "tif": decision.get("tif"), "stop_price": decision.get("stop_price")}
    return by_id


def _snapshot(venue, symbol: str) -> tuple[dict, list[dict], list[dict]]:
    account, positions, orders = venue.account(), venue.positions(), venue.open_orders()
    if not isinstance(account, dict) or not isinstance(positions, list) or not isinstance(orders, list):
        raise FM.FleetRefusal("broker account/position/order snapshot incomplete")
    if len(orders) >= 500:
        raise FM.FleetRefusal("open-order page at 500; reservation inventory incomplete")
    equity = _number(account.get("equity"), "equity", minimum=0.01)
    cash = _number(account.get("cash"), "cash")
    gross = 0.0
    seen: set[str] = set()
    for p in positions:
        sym = p.get("symbol") if isinstance(p, dict) else None
        if not isinstance(sym, str) or not sym or sym in seen:
            raise FM.FleetRefusal("position symbol absent or duplicated")
        seen.add(sym)
        _number(p.get("qty"), f"{sym} held quantity")
        _number(p.get("current_price"), f"{sym} quote", minimum=0.0001)
        gross += _number(p.get("market_value"), f"{sym} market value")
    if abs(equity - cash - gross) > max(1.0, equity * 0.0005):
        raise FM.FleetRefusal("account cash plus marked long holdings disagrees with equity")
    ids: set[str] = set()
    for o in orders:
        if (not isinstance(o, dict) or not isinstance(o.get("id"), str)
                or not o["id"] or o["id"] in ids
                or not isinstance(o.get("symbol"), str) or not o["symbol"]):
            raise FM.FleetRefusal("open order identity absent or duplicated")
        ids.add(o["id"])
        if o.get("symbol") == symbol and o.get("legs"):
            raise FM.FleetRefusal("nested order on target: sell reservation unknown")
    return account, positions, orders


def _capacity(symbol: str, positions: list[dict], orders: list[dict]) -> tuple[float, float, float]:
    held = sum(_number(p["qty"], "held quantity") for p in positions if p["symbol"] == symbol)
    quote = next((_number(p["current_price"], "current price", minimum=0.0001)
                  for p in positions if p["symbol"] == symbol), None)
    stop_reserved = other_reserved = 0.0
    for o in orders:
        if o.get("symbol") != symbol:
            continue
        if o.get("side") != "sell":
            raise FM.FleetRefusal("pending target buy or unknown side can alter held capacity")
        qty = _number(o.get("qty"), "open sell quantity")
        filled = _number(o.get("filled_qty"), "open sell filled quantity")
        if filled > qty:
            raise FM.FleetRefusal("open sell filled quantity exceeds order")
        if o.get("type") in FM.STOP_TYPES:
            if o.get("status") not in RESTING_STOP_STATUSES:
                raise FM.FleetRefusal("target stop is not proven resting")
            if o.get("time_in_force") != "gtc":
                raise FM.FleetRefusal("target stop is not GTC protection")
            stop_price = _number(o.get("stop_price"), "resting stop price", minimum=0.0001)
            if quote is None or stop_price >= quote:
                raise FM.FleetRefusal("resting stop price is not below current market")
            if o.get("type") == "stop_limit":
                _number(o.get("limit_price"), "resting stop-limit price", minimum=0.0001)
            stop_reserved += qty - filled
        else:
            other_reserved += qty - filled
    if stop_reserved + other_reserved > held + 1e-6:
        raise FM.FleetRefusal("open sells reserve more shares than held")
    return held, stop_reserved, other_reserved


def _owner_state(role: str, account: dict, contract: dict, base: Path) -> dict:
    path = FM.state_path(role, base)
    if not path.exists():
        raise FM.FleetRefusal("no prior owning manager state")
    state = json.loads(path.read_text(encoding="utf-8"))
    run_id = state.get("run_id")
    receipt_path = FM.root(base) / "runs" / f"run_{run_id}.json"
    if not run_id or not receipt_path.exists():
        raise FM.FleetRefusal("prior owning manager receipt absent")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    owners = [r for r in receipt.get("accounts") or [] if r.get("role") == role]
    account_number = account.get("account_number")
    if (not isinstance(account_number, str) or not account_number
            or receipt.get("run_id") != run_id
            or len(owners) != 1 or owners[0].get("status") != "ok"
            or owners[0].get("state_written") != state.get("t")
            or owners[0].get("account_number") != account_number
            or owners[0].get("contract_active", {}).get("policy_hash") != contract["policy_hash"]
            or state.get("policy_hash") != contract["policy_hash"]
            or state.get("contract") != contract["version"]):
        raise FM.FleetRefusal("broker account, frozen contract and owning run disagree")
    return state


def _reconciled(venue, role: str, state: dict, positions: list[dict], base: Path) -> dict:
    since = state.get("t")
    if not since or not isinstance(state.get("positions"), dict):
        raise FM.FleetRefusal("owning state lacks reconciliation basis")
    try:
        state_time = datetime.fromisoformat(str(since).replace("Z", "+00:00"))
        if state_time.tzinfo is None:
            raise ValueError("naive state timestamp")
    except ValueError as exc:
        raise FM.FleetRefusal("owning state timestamp invalid") from exc
    fills = venue.fills(after=since)
    orders = venue.orders_since(since)
    if not isinstance(fills, list) or len(fills) >= 1000 or not isinstance(orders, list) or len(orders) >= 500:
        raise FM.FleetRefusal("fills/orders history incomplete")
    for f in fills:
        if f.get("side") not in {"buy", "sell"} or not f.get("symbol"):
            raise FM.FleetRefusal("fill side or symbol unknown")
        _number(f.get("qty"), "fill quantity", minimum=0.000001)
    accepted_ids = _accepted_orders(role, base)
    fill_ids: set[str] = set()
    filled_by_order: dict[str, float] = {}
    for fill in fills:
        fid = fill.get("id")
        oid = fill.get("order_id")
        if (not fid or fid in fill_ids or fill.get("activity_type") != "FILL"
                or oid not in accepted_ids):
            raise FM.FleetRefusal("fill identity duplicate, incomplete or not accepted-owned")
        fill_ids.add(fid)
        try:
            filled_at = datetime.fromisoformat(
                str(fill.get("transaction_time") or "").replace("Z", "+00:00"))
            if filled_at.tzinfo is None or filled_at <= state_time:
                raise ValueError("fill not after owner state")
        except ValueError as exc:
            raise FM.FleetRefusal("fill timestamp is not after owning state") from exc
        accepted = accepted_ids[oid]
        if (fill.get("symbol") != accepted["symbol"]
                or fill.get("side") != accepted["side"]):
            raise FM.FleetRefusal("fill symbol/side disagrees with accepted order")
        filled_by_order[oid] = filled_by_order.get(oid, 0.0) + _number(
            fill.get("qty"), "fill quantity", minimum=0.000001)
        if filled_by_order[oid] > accepted["qty"] + 1e-6:
            raise FM.FleetRefusal("fills exceed accepted order quantity")
    for order in orders:
        accepted = accepted_ids.get(order.get("id")) if isinstance(order, dict) else None
        if (not accepted or order.get("symbol") != accepted["symbol"]
                or order.get("side") != accepted["side"]
                or order.get("type") != accepted["type"]
                or order.get("client_order_id") != accepted["coid"]
                or _number(order.get("qty"), "owned order quantity") != accepted["qty"]):
            raise FM.FleetRefusal("post-state order has no matching accepted owned decision/outcome")
    rec = FM.reconcile({k: _number(v, "prior held quantity") for k, v in state["positions"].items()},
                       fills, FM.signed_positions(positions), orders)
    if rec.get("ok") is not True:
        raise FM.FleetRefusal(f"broker ownership reconciliation {rec.get('status')}")
    return rec


def _unresolved_stop_intents(role: str, symbol: str, coid: str, base: Path) -> list[str]:
    rows = _ledger_rows(base)
    outcomes: dict[str, list[dict]] = {}
    unresolved: list[str] = []
    for row in rows:
        if row.get("row") == "outcome" and row.get("role") == role:
            outcomes.setdefault(str(row.get("coid") or ""), []).append(row)
    for row in rows:
        if (row.get("row") != "decision" or row.get("mode") != "LIVE"
                or row.get("role") != role or row.get("symbol") != symbol
                or row.get("kind") not in {"stop_new", "stop_renew"}):
            continue
        prior_coid = str(row.get("coid") or "")
        prior_outcomes = outcomes.get(prior_coid) or []
        if (prior_coid == coid or len(prior_outcomes) != 1
                or not str(prior_outcomes[0].get("outcome") or "").startswith("submitted ")
                or not prior_outcomes[0].get("order_id")
                or (row.get("pass") == "protect_only"
                    and prior_outcomes[0].get("verification") != "PROTECTED")):
            unresolved.append(hashlib.sha256(json.dumps(
                row, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
    return unresolved


def _prior_intent(role: str, symbol: str, coid: str, base: Path) -> bool:
    return bool(_unresolved_stop_intents(role, symbol, coid, base))


def _verified_covered_noop(role: str, symbol: str, orders: list[dict], base: Path,
                           held: float, stops: float, other: float) -> None:
    """Prove a no-action sweep result; never resolves an earlier POST intent."""
    if (held <= 0 or abs(held - round(held)) > 1e-6
            or abs(stops - held) > 1e-6 or other != 0):
        raise FM.FleetRefusal("target is not wholly covered by resting GTC stops")
    accepted = _accepted_orders(role, base)
    target_orders = [o for o in orders if o.get("symbol") == symbol]
    if not target_orders:
        raise FM.FleetRefusal("covered target has no resting stop evidence")
    for order in target_orders:
        owned = accepted.get(order.get("id"))
        if (order.get("side") != "sell" or order.get("type") != "stop"
                or order.get("time_in_force") != "gtc"
                or order.get("status") not in {"new", "accepted", "partially_filled"}
                or not owned or owned["symbol"] != symbol or owned["side"] != "sell"
                or owned["type"] != "stop" or owned["tif"] != "gtc"
                or order.get("client_order_id") != owned["coid"]
                or _number(order.get("qty"), "covered stop quantity") != owned["qty"]
                or _number(order.get("qty"), "covered stop quantity")
                <= _number(order.get("filled_qty"), "covered stop filled quantity")
                or _number(order.get("stop_price"), "covered stop price", minimum=0.0001)
                != _number(owned["stop_price"], "accepted stop price", minimum=0.0001)):
            raise FM.FleetRefusal("resting stop lacks exact accepted owned identity")


def _append_durable(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _market_ok(clock: dict, now: datetime) -> bool:
    if not isinstance(clock, dict) or clock.get("is_open") is not True:
        return False
    try:
        stamp = datetime.fromisoformat(str(clock.get("timestamp") or "").replace("Z", "+00:00"))
        close = datetime.fromisoformat(str(clock.get("next_close") or "").replace("Z", "+00:00"))
    except ValueError:
        return False
    return (stamp.tzinfo is not None and close.tzinfo is not None
            and abs((now - stamp).total_seconds()) <= 30
            and (close - now).total_seconds() / 60
            >= FM._cfg.FLEET_MANAGER_MIN_MINUTES_TO_CLOSE)


def _exact_stop(row: Any, action: FM.Action, *, resting: bool = False) -> bool:
    if not isinstance(row, dict):
        return False
    try:
        same = (bool(row.get("id")) and row.get("client_order_id") == action.coid
                and row.get("symbol") == action.symbol and row.get("side") == "sell"
                and row.get("type") == "stop" and row.get("time_in_force") == "gtc"
                and _number(row.get("qty"), "accepted stop quantity") == action.qty
                and abs(_number(row.get("stop_price"), "accepted stop price")
                        - action.stop_price) <= 1e-6)
    except FM.FleetRefusal:
        return False
    return bool(same and (not resting or row.get("status") in RESTING_STOP_STATUSES))


def protect_once(role: str, symbol: str, venue, modes: dict, sigma: dict,
                 *, live: bool = False, base: Path | None = None,
                 now: datetime | None = None, sweep_owner: dict | None = None,
                 sweep_budget: SweepBudget | None = None) -> dict:
    """Plan one missing stop and optionally submit it, under the shared role lock."""
    now = now or datetime.now(timezone.utc)
    base = FM.root(base)
    with FM.role_writer_lock(role, base):
        if not FM._EQUITY_TICKER.fullmatch(symbol):
            raise FM.FleetRefusal("protection target is not a plain equity ticker")
        if FM.stop_file(base).exists():
            raise FM.FleetRefusal("fleet STOP file present")
        mode = modes.get(role) or {}
        version = mode.get("contract")
        if (mode.get("skip") or mode.get("maintenance") != "LIVE"
                or version not in {"v1", "v2"}):
            raise FM.FleetRefusal("role has no active LIVE maintenance authority")
        not_before = mode.get("not_before_utc")
        if not_before and now < datetime.fromisoformat(str(not_before).replace("Z", "+00:00")):
            raise FM.FleetRefusal("role maintenance not yet authorized")
        contract = FM.load_contract(role, version, base)
        clock = venue.clock()
        if not isinstance(clock, dict) or not isinstance(clock.get("timestamp"), str):
            raise FM.FleetRefusal("broker clock incomplete")
        day = date.fromisoformat(clock["timestamp"][:10])
        market_ok = _market_ok(clock, now)
        if live and not market_ok:
            raise FM.FleetRefusal("venue closed or inside the frozen close buffer")
        acct, positions, orders = _snapshot(venue, symbol)
        state = _owner_state(role, acct, contract, base)
        rec = _reconciled(venue, role, state, positions, base)
        if sweep_owner is not None:
            _automatic_owner_guard(role, symbol, venue, acct, positions, orders,
                                   state, contract, base, sweep_owner, sweep_budget)
        if _prior_intent(role, symbol, "", base):
            raise FM.FleetRefusal("prior LIVE stop intent exists; unresolved POST requires attended recovery")
        held, stops, other = _capacity(symbol, positions, orders)
        # The maintenance planner counts full stop quantities; give it the
        # unfilled remainder so partial fills cannot hide uncovered shares.
        planning_orders = [dict(o, qty=str(_number(o.get("qty"), "stop qty")
                           - _number(o.get("filled_qty"), "stop filled")), filled_qty="0")
                           if o.get("symbol") == symbol and o.get("type") in FM.STOP_TYPES
                           else o for o in orders]
        proposed, flags, _ = FM.plan_maintenance(role, positions, planning_orders,
                                                  sigma, contract, day.isoformat(), day)
        candidates = [a for a in proposed if a.kind == "stop_new" and a.symbol == symbol]
        if len(candidates) > 1:
            raise FM.FleetRefusal("multiple new protective stops for one target")
        if not candidates:
            return {"status": "ALREADY_COVERED" if held - stops - other < 1 else "NO_STOP_PLAN",
                    "role": role, "symbol": symbol, "held": held, "stop_reserved": stops,
                    "other_sell_reserved": other, "flags": flags, "reconcile": rec["status"]}
        action = candidates[0]
        free = int(math.floor(held - stops - other + 1e-9))
        if free <= 0:
            raise FM.FleetRefusal("no unreserved long shares for a protective stop")
        if action.qty > free:
            action.qty = free
            action.coid = FM.client_order_id(role, day.isoformat(), "stop", symbol,
                                              contract["policy_hash"], str(free))
            action.reason += "; reduced to held minus all resting sell reservations"
        quote = next(_number(p["current_price"], "target quote", minimum=0.0001)
                     for p in positions if p["symbol"] == symbol)
        maximum = _number(contract["stop_rule"]["max_frac"], "frozen stop cap")
        if (not math.isfinite(float(action.stop_price or float("nan")))
                or action.stop_price <= 0 or action.stop_price >= quote
                or (quote - action.stop_price) / quote > maximum + 0.0001):
            raise FM.FleetRefusal("planned stop invalid against fresh quote/frozen cap")
        gctx = FM.GateCtx(equity=_number(acct["equity"], "equity", minimum=0.01),
                          cash=_number(acct["cash"], "cash"),
                          held=FM.signed_positions(positions),
                          mv={p["symbol"]: _number(p["market_value"], "market value") for p in positions},
                          gross=sum(_number(p["market_value"], "market value") for p in positions),
                          contract=contract, today=day, stop_file_present=False,
                          credential_ok=True, reconciliation_ok=True,
                          reconciliation_status=rec["status"], market_ok=market_ok,
                          turnover_left=contract["caps"]["daily_turnover_frac"] * float(acct["equity"]),
                          stopped_out={})
        trace = FM.run_gates(action, gctx, mode="LIVE" if live else "DRY")
        result = {"status": "REFUSED" if action.refused else "DRY_PLAN",
                  "role": role, "symbol": symbol, "held": held,
                  "stop_reserved": stops, "other_sell_reserved": other,
                  "qty": action.qty, "stop_price": action.stop_price,
                  "policy_hash": contract["policy_hash"], "gates": trace,
                  "refused": action.refused, "reconcile": rec["status"]}
        if not live or action.refused:
            return result
        if _prior_intent(role, symbol, action.coid, base):
            raise FM.FleetRefusal("prior LIVE stop intent exists; unresolved POST cannot be retried")
        if venue.order_by_coid(action.coid) is not None:
            raise FM.FleetRefusal("exact protective client id already exists at broker")
        fresh_acct, fresh_pos, fresh_orders = _snapshot(venue, symbol)
        fresh_held, fresh_stops, fresh_other = _capacity(symbol, fresh_pos, fresh_orders)
        if (fresh_acct.get("account_number") != acct.get("account_number")
                or fresh_held != held or fresh_stops != stops or fresh_other != other
                or {o["id"] for o in fresh_orders} != {o["id"] for o in orders}
                or action.qty > int(math.floor(fresh_held - fresh_stops - fresh_other + 1e-9))):
            raise FM.FleetRefusal("held quantity or sell reservations changed before POST")
        fresh_quote = next(_number(p["current_price"], "fresh quote", minimum=0.0001)
                           for p in fresh_pos if p["symbol"] == symbol)
        # Reprice from the same frozen stop rule on the latest broker mark;
        # a harmless quote tick is not an identity or holdings race.
        fresh_stop = FM.stop_price_for(fresh_quote,
                                       _number(action.inputs["stop_frac"], "frozen stop distance"))
        if (not math.isfinite(fresh_stop) or fresh_stop <= 0 or fresh_stop >= fresh_quote
                or (fresh_quote - fresh_stop) / fresh_quote > maximum + 0.0001):
            raise FM.FleetRefusal("stop no longer valid against fresh quote")
        action.stop_price = fresh_stop
        prior_qty = action.qty
        gctx.equity = _number(fresh_acct["equity"], "fresh equity", minimum=0.01)
        gctx.cash = _number(fresh_acct["cash"], "fresh cash")
        gctx.held = FM.signed_positions(fresh_pos)
        gctx.mv = {p["symbol"]: _number(p["market_value"], "fresh market value")
                   for p in fresh_pos}
        gctx.gross = sum(gctx.mv.values())
        gctx.orders_used = 0
        trace = FM.run_gates(action, gctx, mode="LIVE")
        if action.refused or action.qty != prior_qty:
            raise FM.FleetRefusal(f"fresh protective stop gate refused: {action.refused or 'quantity changed'}")
        result.update(stop_price=fresh_stop, gates=trace)
        modes_path = FM.modes_path(base)
        if (not modes_path.exists()
                or (json.loads(modes_path.read_text(encoding="utf-8")).get(role) or {}) != mode
                or FM.load_contract(role, version, base)["policy_hash"] != contract["policy_hash"]):
            raise FM.FleetRefusal("maintenance mode or frozen contract changed before POST")
        if FM.stop_file(base).exists() or not _market_ok(venue.clock(), datetime.now(timezone.utc)):
            raise FM.FleetRefusal("STOP file or closed venue appeared before POST")
        if sweep_owner is not None:
            _automatic_owner_guard(role, symbol, venue, fresh_acct, fresh_pos, fresh_orders,
                                   state, contract, base, sweep_owner, sweep_budget)
        run_id = now.strftime("%Y%m%dT%H%M%SZ") + "-protect-" + uuid.uuid4().hex[:6]
        decision = {"row": "decision", "run_id": run_id, "t": FM._now_iso(),
                    "session": day.isoformat(), "pass": "protect_only", "role": role,
                    "contract_version": contract["version"], "policy_hash": contract["policy_hash"],
                    "kind": action.kind, "symbol": symbol, "side": "sell", "qty": action.qty,
                    "type": "stop", "tif": "gtc", "stop_price": action.stop_price,
                    "protective": True, "reason": action.reason, "inputs": action.inputs,
                    "coid": action.coid, "mode": "LIVE", "refused": None,
                    "licence": FM.LICENCE, "story_id": FM.story_id(role, day.isoformat(),
                                                            "protect_only", action.coid),
                    "gates": trace, "gates_hash": FM.gates_config()["hash"]}
        _append_durable(FM.decisions_path(base), decision)
        try:
            submitted = FM.submit_once(venue, action, strict_new=True)
            outcome = submitted["outcome"]
            order_id = submitted.get("order_id")
            if (outcome.startswith("submitted ")
                    and (not _exact_stop(submitted.get("ack"), action)
                         or submitted["ack"].get("id") != order_id)):
                outcome = "SUBMIT_UNKNOWN: broker acknowledgement disagrees with durable stop intent"
        except Exception as exc:  # POST may have reached the broker
            outcome, order_id = f"SUBMIT_UNKNOWN: {type(exc).__name__}", None
        result.update(status="SUBMIT_UNKNOWN", outcome=outcome)
        if outcome.startswith("submitted ") and order_id:
            try:
                confirmed = venue.order_by_coid(action.coid)
                after_acct, after_pos, after_orders = _snapshot(venue, symbol)
                qty_after, coverage, after_other = _capacity(symbol, after_pos, after_orders)
                exact_open = [o for o in after_orders if o.get("id") == order_id]
                if (after_acct.get("account_number") == acct.get("account_number")
                        and _exact_stop(confirmed, action, resting=True)
                        and confirmed.get("id") == order_id
                        and len(exact_open) == 1 and _exact_stop(exact_open[0], action, resting=True)
                        and qty_after == held and after_other == other
                        and coverage >= held - other - 1e-6):
                    result.update(status="PROTECTED", stop_reserved=coverage)
            except Exception:  # a failed verification is UNKNOWN, never proof of cover
                pass
        if result["status"] != "PROTECTED" and outcome.startswith("submitted "):
            outcome = "SUBMIT_UNKNOWN: post-submit resting proof incomplete"
            result["outcome"] = outcome
        # One durable outcome after verification. A crash before it leaves the
        # pre-POST decision unresolved, and a failed verification stays UNKNOWN
        # across day/coid changes until an attended exact recovery.
        _append_durable(FM.decisions_path(base), {"row": "outcome", "run_id": run_id,
                        "t": FM._now_iso(), "role": role, "coid": action.coid,
                        "outcome": outcome, "order_id": order_id,
                        "verification": result["status"]})
        return result


class SweepBudget:
    """Conservative HTTP-call upper bound, including ten possible FILL pages."""

    def __init__(self, *, seconds: float = 90, requests: int = 180) -> None:
        self.until = time.monotonic() + seconds
        self.limit = requests
        self.used = 0
        self.http_times: list[float] = []
        self.http_total = 0
        self.history_warnings: list[dict] = []

    def charge(self, units: int = 1) -> None:
        if time.monotonic() >= self.until or self.used + units > self.limit:
            raise FM.FleetRefusal("sweep time/request budget exhausted; inventory incomplete")
        self.used += units

    def charge_http(self) -> None:
        """Absolute per-process cap; 429 is a refusal, never a retry storm."""
        self.charge(0)
        now = time.monotonic()
        self.http_times = [t for t in self.http_times if now - t < 60]
        if len(self.http_times) >= 120:
            raise FM.FleetRefusal("sweep HTTP rate cap reached; no automatic retry")
        self.http_times.append(now)
        self.http_total += 1


class _CountedVenue:
    def __init__(self, venue, budget: SweepBudget) -> None:
        self.venue, self.budget = venue, budget

    def __getattr__(self, name):
        value = getattr(self.venue, name)
        if not callable(value):
            return value
        def counted(*args, **kwargs):
            # Venue.fills may paginate ten 100-row pages; daily_closes may
            # paginate twenty bar pages. Reserve their worst case up front.
            self.budget.charge({"fills": 10, "daily_closes": 20}.get(name, 1))
            result = value(*args, **kwargs)
            self.budget.charge(0)
            return result
        return counted


def _sweep_clock(clock: dict, now: datetime) -> str:
    if not _market_ok(clock, now):
        raise FM.FleetRefusal("sweep venue closed, clock stale, or inside frozen close buffer")
    eastern = now.astimezone(ZoneInfo("America/New_York"))
    # The installed preclose task is fixed at 03:30 SGT (19:30 UTC), not
    # timezone-adjusted with New York DST. Stop before BOTH boundaries.
    utc = now.astimezone(timezone.utc)
    if (eastern.weekday() >= 5 or (eastern.hour, eastern.minute) >= (15, 15)
            or (utc.hour, utc.minute) >= (19, 15)):
        raise FM.FleetRefusal("sweep outside weekday preclose safety window")
    return eastern.date().isoformat()


def _fresh_sweep_boundary(venue, budget: SweepBudget, day: str) -> None:
    """A successful no-action/pass receipt needs a valid clock after its proof."""
    budget.charge(0)
    observed = _sweep_clock(venue.clock(), datetime.now(timezone.utc))
    budget.charge(0)
    if observed != day:
        raise FM.FleetRefusal("sweep session changed before completed receipt")


def _completed_open_owner(role: str, account: dict, base: Path, day: str,
                          now: datetime) -> tuple[dict, dict]:
    modes = json.loads(FM.modes_path(base).read_text(encoding="utf-8"))
    version = (modes.get(role) or {}).get("contract")
    contract = FM.load_contract(role, version, base)
    state = _owner_state(role, account, contract, base)
    receipt = json.loads((FM.root(base) / "runs" / f"run_{state['run_id']}.json").read_text(encoding="utf-8"))
    try:
        stamp = datetime.fromisoformat(str(receipt["finished_utc"]).replace("Z", "+00:00"))
        state_stamp = datetime.fromisoformat(str(state["t"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None or state_stamp.tzinfo is None:
            raise ValueError("naive owner time")
    except (KeyError, ValueError) as exc:
        raise FM.FleetRefusal("completed OPEN owner time absent or invalid") from exc
    if (receipt.get("pass") != "open" or receipt.get("live_flag") is not True
            or stamp.astimezone(ZoneInfo("America/New_York")).date().isoformat() != day
            or state_stamp > stamp or stamp > now):
        raise FM.FleetRefusal("no completed current-session OPEN owner")
    return state, contract


def _new_owned_evidence(role: str, symbol: str, venue, state: dict, base: Path) -> dict:
    """Exact accepted post-state fill identities behind a flat-to-long holding."""
    since = state["t"]
    state_time = datetime.fromisoformat(str(since).replace("Z", "+00:00"))
    fills = venue.fills(after=since)
    if not isinstance(fills, list) or len(fills) >= 1000:
        raise FM.FleetRefusal("late-fill page history incomplete")
    accepted = _accepted_orders(role, base)
    seen: set[str] = set()
    net = 0.0
    identities: list[tuple[str, str, str, float, str]] = []
    for f in fills:
        if not isinstance(f, dict) or not f.get("id") or f["id"] in seen:
            raise FM.FleetRefusal("late-fill identity missing or duplicated")
        seen.add(f["id"])
        if f.get("activity_type") != "FILL" or f.get("order_id") not in accepted:
            raise FM.FleetRefusal("late fill is not accepted-owned")
        owned = accepted[f["order_id"]]
        if f.get("symbol") != owned["symbol"] or f.get("side") != owned["side"]:
            raise FM.FleetRefusal("late fill disagrees with accepted order")
        if f["symbol"] == symbol and f["side"] == "buy" and owned["type"] != "limit":
            raise FM.FleetRefusal("late buy is not an accepted entry limit")
        try:
            filled_at = datetime.fromisoformat(str(f.get("transaction_time") or "").replace("Z", "+00:00"))
            if filled_at.tzinfo is None or filled_at <= state_time:
                raise ValueError("not after owner")
        except ValueError as exc:
            raise FM.FleetRefusal("late fill timestamp not after owner state") from exc
        if f["symbol"] == symbol:
            qty = _number(f.get("qty"), "late fill quantity", minimum=0.000001)
            net += qty * (1 if f["side"] == "buy" else -1)
            identities.append((str(f["id"]), str(f["order_id"]), f["side"], qty,
                               filled_at.isoformat()))
    return {"net": net, "fills": tuple(sorted(identities))}


def _automatic_owner_guard(role: str, symbol: str, venue, account: dict,
                           positions: list[dict], orders: list[dict], state: dict,
                           contract: dict, base: Path, expected: dict,
                           budget: SweepBudget | None) -> None:
    """Sweep-only eligibility under the same role lock held through the POST."""
    if budget is None:
        raise FM.FleetRefusal("automatic protection budget absent")
    budget.charge(0)
    session = _sweep_clock(venue.clock(), datetime.now(timezone.utc))
    latest, current_contract = _completed_open_owner(role, account, base, session,
                                                      datetime.now(timezone.utc))
    identity = {"run_id": latest.get("run_id"), "state_t": latest.get("t"),
                "account_number": account.get("account_number"),
                "policy_hash": current_contract.get("policy_hash"),
                "contract_version": current_contract.get("version"), "session": session}
    if (not isinstance(latest.get("positions"), dict)
            or identity != {key: expected.get(key) for key in identity}
            or state.get("run_id") != latest.get("run_id") or state.get("t") != latest.get("t")
            or contract.get("policy_hash") != current_contract.get("policy_hash")
            or _number(latest["positions"].get(symbol, 0), "automatic prior held") != 0):
        raise FM.FleetRefusal("automatic selected OPEN owner or zero-prior basis changed")
    _reconciled(venue, role, latest, positions, base)
    held, stops, other = _capacity(symbol, positions, orders)
    if (held, stops, other) != expected.get("capacity"):
        raise FM.FleetRefusal("automatic held or sell-reservation evidence changed")
    evidence = _new_owned_evidence(role, symbol, venue, latest, base)
    if evidence != expected.get("fills") or abs(evidence["net"] - held) > 1e-6:
        raise FM.FleetRefusal("automatic accepted late-fill evidence changed")
    budget.charge(0)


def sweep_once(venues: dict, modes: dict, sigma_for, *, live: bool = False,
               base: Path | None = None, now: datetime | None = None,
               budget: SweepBudget | None = None) -> dict:
    """One bounded discovery pass; only protect_once may authorize a POST."""
    base = FM.root(base)
    now = now or datetime.now(timezone.utc)
    budget = budget or SweepBudget()
    if any(r not in modes for r in FM._cfg.FLEET_MANAGER_ROLES):
        raise FM.FleetRefusal("fleet role modes inventory incomplete")
    active = [r for r in FM._cfg.FLEET_MANAGER_ROLES if not (modes.get(r) or {}).get("skip")]
    if len(active) > 5 or set(active) - set(venues):
        raise FM.FleetRefusal("active role/credential inventory incomplete or over five")
    if FM.stop_file(base).exists() or not FM.modes_path(base).exists():
        raise FM.FleetRefusal("fleet STOP or modes missing")
    if not active:
        raise FM.FleetRefusal("no active fleet roles")
    counted = {r: _CountedVenue(venues[r], budget) for r in active}
    day = _sweep_clock(counted[active[0]].clock(), now)
    candidates: list[tuple[str, str, dict]] = []
    report: list[dict] = []
    history_warnings = budget.history_warnings
    for role in active:
        budget.charge(0)
        mode = modes.get(role) or {}
        if mode.get("maintenance") != "LIVE" or mode.get("contract") not in {"v1", "v2"}:
            raise FM.FleetRefusal(f"{role}: maintenance authority absent")
        venue = counted[role]
        with FM.role_writer_lock(role, base):
            account, positions, orders = _snapshot(venue, "")
            if len(positions) > 64:
                raise FM.FleetRefusal(f"{role}: holdings bound exceeded")
            state, contract = _completed_open_owner(role, account, base, day, now)
            if contract["policy_hash"] != FM.load_contract(role, mode["contract"], base)["policy_hash"]:
                raise FM.FleetRefusal(f"{role}: active frozen contract changed")
            if not isinstance(state.get("positions"), dict):
                raise FM.FleetRefusal(f"{role}: owner position basis missing")
            if any(o.get("legs") for o in orders if o.get("symbol") in {p["symbol"] for p in positions}):
                raise FM.FleetRefusal(f"{role}: nested order on held symbol")
            uncovered: list[str] = []
            reconciled = False
            for p in positions:
                symbol = p["symbol"]
                unresolved = _unresolved_stop_intents(role, symbol, "", base)
                for digest in unresolved:
                    history_warnings.append({
                        "role": role, "symbol": symbol,
                        "code": "UNRESOLVED_PRIOR_STOP_INTENT",
                        "identity_sha256": digest})
                held, stops, other = _capacity(symbol, positions, orders)
                free = held - stops - other
                if free <= 1e-6:
                    if not reconciled:
                        _reconciled(venue, role, state, positions, base)
                        reconciled = True
                    _verified_covered_noop(role, symbol, orders, base, held, stops, other)
                    continue
                if unresolved:
                    raise FM.FleetRefusal(f"{role}: unresolved prior stop intent requires attended recovery")
                if free < 1 - 1e-6 or abs(free - round(free)) > 1e-6:
                    raise FM.FleetRefusal(f"{role}: fractional uncovered shares require attended repair")
                if _number(state["positions"].get(symbol, 0), "prior held") != 0:
                    raise FM.FleetRefusal(f"{role}: pre-existing holding/top-up is not automatic late-fill evidence")
                uncovered.append(symbol)
            if uncovered:
                # The entire role history must reconcile, including other symbols.
                if not reconciled:
                    _reconciled(venue, role, state, positions, base)
                for symbol in uncovered:
                    held, stops, other = _capacity(symbol, positions, orders)
                    evidence = _new_owned_evidence(role, symbol, venue, state, base)
                    if abs(evidence["net"] - held) > 1e-6:
                        raise FM.FleetRefusal(f"{role}: fresh held shares not fully explained by accepted fills")
                    candidates.append((role, symbol, {
                        "run_id": state["run_id"], "state_t": state["t"],
                        "account_number": account["account_number"],
                        "policy_hash": contract["policy_hash"],
                        "contract_version": contract["version"], "session": day,
                        "capacity": (held, stops, other), "fills": evidence}))
                    if len(candidates) > 3:
                        raise FM.FleetRefusal("three-candidate sweep bound exceeded")
            report.append({"role": role, "status": "CANDIDATE" if uncovered else "ALREADY_COVERED",
                           "held_symbols": len(positions), "candidates": len(uncovered)})
            _fresh_sweep_boundary(venue, budget, day)
    if not candidates:
        _fresh_sweep_boundary(counted[active[0]], budget, day)
        return {"status": "ALREADY_COVERED", "roles": report,
                "history_warnings": history_warnings, "requests_upper_bound": budget.used}
    results = []
    acted: set[str] = set()
    for role, symbol, expected in candidates:
        if role in acted:
            results.append({"role": role, "symbol": symbol, "status": "DEFERRED_ROLE_POST_CAP"})
            continue
        acted.add(role)
        try:
            result = protect_once(role, symbol, counted[role], modes, sigma_for(role, symbol, counted[role]),
                                  live=live, base=base, now=now, sweep_owner=expected,
                                  sweep_budget=budget)
            results.append({"role": role, "symbol": symbol, "status": result["status"]})
        except FM.FleetRefusal as exc:
            results.append({"role": role, "symbol": symbol, "status": "REFUSED", "why": str(exc)[:180]})
    statuses = {r["status"] for r in results}
    status = ("INCOMPLETE" if statuses & {"REFUSED", "DEFERRED_ROLE_POST_CAP", "SUBMIT_UNKNOWN", "NO_STOP_PLAN"}
              else "PROTECTED" if live and statuses == {"PROTECTED"}
              else "ALREADY_COVERED" if statuses == {"ALREADY_COVERED"} else "DRY_PLAN")
    if status in {"PROTECTED", "ALREADY_COVERED", "DRY_PLAN"}:
        _fresh_sweep_boundary(counted[active[0]], budget, day)
    return {"status": status, "roles": report, "candidates": results,
            "history_warnings": history_warnings,
            "requests_upper_bound": budget.used}
