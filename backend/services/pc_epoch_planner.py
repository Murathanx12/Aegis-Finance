"""Contract-valued PC-PAPER stock allocation after a verified epoch transition.

Inputs are explicit broker and selector evidence.  This planner never fetches
data or submits orders, so a fixture can exercise the same sizing that the
owning sim will use. Unknown prices, sigma, source membership or pending orders
block incremental risk instead of becoming zero.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

from backend.services import pc_broker as PB
from backend.services import pc_policy_epoch as PE
from backend.services import policy_state as PS


def _number(value: Any, name: str) -> float:
    result = float(PE._decimal(value, name))
    if not math.isfinite(result):
        raise PE.EpochRefused(f"{name} is not finite")
    return result


def plan_active(*, contract: dict, evidence: dict, selectors: dict,
                prices: dict[str, float], sigmas: dict[str, float]) -> dict:
    """Produce a stock-only, long-only book using the frozen epoch values."""
    content = contract["content"]
    alloc = content["allocation"]
    limits = content["binding_limits"]
    snap = PE._economic(evidence)
    equity = _number(snap["equity"], "equity")
    cash = _number(snap["cash"], "cash")
    held = {str(p["symbol"]): _number(p["qty"], "held quantity")
            for p in evidence["positions"]}
    held_weights = {str(p["symbol"]):
                    _number(p["market_value"], "held market value") / equity
                    for p in evidence["positions"]}
    if any(q < 0 for q in held.values()):
        raise PE.EpochRefused("short position in active book")
    if _number(held.get("SPY", 0), "SPY residual") >= 1:
        raise PE.EpochRefused("strategic index exit is not reconciled")
    if not isinstance(evidence.get("open_orders"), list):
        raise PE.EpochRefused("pending order evidence absent")
    pending = evidence["open_orders"]
    bars_fresh = selectors.get("bars_fresh") is True
    source_ok = selectors.get("revision_source_verified") is True
    members = list(content["revision_flow"]["members"])
    if len(members) != 20 or len(set(members)) != 20 or "SPY" in members:
        raise PE.EpochRefused("frozen revision membership invalid")
    ranking = selectors.get("ranking") or {}
    top = list(ranking.get("top") or [])[:18]
    er_names = ((selectors.get("er_view") or {}).get("names") or {})
    priced = []
    for item in top:
        sym = str(item.get("symbol") or "").upper()
        value = (er_names.get(sym) or {}).get("h21", {}).get("er")
        if value is not None:
            priced.append((item, _number(value, "expected return")))
    if priced:
        top = [item for item, value in sorted(priced, key=lambda x: -x[1])
               if value > 0][:18]
    complete_er = all(all(key in ((er_names.get(str(item.get("symbol") or "").upper())
                                   or {}).get("h21") or {})
                          for key in ("er", "er_equal", "x", "weights", "phi",
                                      "components_awake", "weights_source"))
                      for item in top)
    exploit_ok = (bars_fresh and selectors.get("blend_grade_may_trade") is True
                  and _number(ranking.get("top20_net_rel_21d") or 0,
                              "ranking grade") > 0 and bool(top)
                  and bool(priced) and selectors.get("er_view") is not None
                  and complete_er)
    probe_ok = bars_fresh and selectors.get("probe_grade_may_trade") is True
    probe_rows = list(selectors.get("probe_rows") or []) if probe_ok else []
    preference = selectors.get("probe_preference") or {}
    if preference.get("use") is True and selectors.get("er_view") is not None:
        probe_rows, _ = PS.probe_order(
            probe_rows, selectors["er_view"], preference.get("reputation_weights") or {},
            sigma=sigmas)
    probe_rows = probe_rows[:int(limits["probe_max_names"])]
    probe_names = []
    adv_inputs: dict[str, list[object]] = {}
    for sym, value in (selectors.get("adv_by_symbol") or {}).items():
        adv_inputs.setdefault(str(sym).upper(), []).append(value)
    for item in probe_rows:
        sym = str(item.get("ticker") or "").upper()
        if not sym or sym == "SPY" or sym in probe_names:
            raise PE.EpochRefused("PROBE name invalid or duplicated")
        probe_names.append(sym)
        if "median_dollar_vol" in item:
            adv_inputs.setdefault(sym, []).append(item["median_dollar_vol"])
    # A calibrated EXPLOIT gate needs its own pre-trade observations. These
    # candidates are graded virtually and never enter the allocation targets.
    shadow_exploit = []
    if (not exploit_ok and bars_fresh and bool(priced)
            and _number(ranking.get("top20_net_rel_21d") or 0,
                        "ranking grade") > 0):
        try:
            control_price = _number(prices.get("SPY"), "shadow control price")
        except PE.EpochRefused:
            control_price = 0.0
        if control_price > 0:
            for item in top:
                sym = str(item.get("symbol") or "").upper()
                if sym in set(probe_names) | {"SPY"}:
                    continue
                try:
                    candidate_price = _number(prices.get(sym), "shadow candidate price")
                except PE.EpochRefused:
                    continue
                if candidate_price > 0 and all(
                        key in ((er_names.get(sym) or {}).get("h21") or {})
                        for key in ("er", "er_equal", "x", "weights", "phi",
                                    "components_awake", "weights_source")):
                    shadow_exploit.append(sym)
    for item in top:
        sym = str(item.get("symbol") or "").upper()
        if sym and "median_dollar_vol" in item:
            adv_inputs.setdefault(sym, []).append(item["median_dollar_vol"])
    adv_by: dict[str, float] = {}
    invalid_adv: set[str] = set()
    for sym, values in adv_inputs.items():
        try:
            parsed = [_number(v, "median dollar volume") for v in values]
        except PE.EpochRefused:
            invalid_adv.add(sym)
            continue
        if not parsed or any(v <= 0 for v in parsed):
            invalid_adv.add(sym)
            continue
        adv_by[sym] = min(parsed)  # conflicting sources cannot expand capacity
    exploit_names = []
    if exploit_ok:
        for item in top:
            sym = str(item.get("symbol") or "").upper()
            if sym and sym != "SPY" and sym not in probe_names and sym not in exploit_names:
                exploit_names.append(sym)
    rf_names = ([s for s in members if s not in set(probe_names) | set(exploit_names)]
                if source_ok and bars_fresh else [])
    rf_weight = float(alloc["revision_flow_gross_cap"]) / len(members)
    probe_weights, weighting_meta = PS.probe_weights(
        probe_names, sigmas, (preference.get("probe_weighting") or "equal")
        if preference.get("use") is True else "equal",
        max_weight=float(limits["probe_max_weight"]),
        gross_cap=float(alloc["probe_gross_cap"]))
    weights: dict[str, float] = {}
    state: dict[str, str] = {}
    for sym in probe_names:
        weights[sym], state[sym] = probe_weights[sym], "PROBE"
    for sym in rf_names:
        weights[sym], state[sym] = rf_weight, "REVISION_FLOW"
    # A refused frozen book is held, never turned into a generic EXIT.  Its
    # market value remains in room and in the post-fill risk calculation.
    rf_hold = {s for s in members if s in held and s not in weights}
    other_held = {s for s in held if s not in weights and s != "SPY"}
    residual_gross = sum(_number(p.get("market_value"), "held market value") / equity
                         for p in evidence["positions"]
                         if p.get("symbol") in other_held)
    max_gross = min(float(alloc["gross_cap"]),
                    1.0 - float(alloc["minimum_cash_buffer"]))
    room = max(0.0, max_gross - sum(weights.values()) - residual_gross)
    if exploit_names:
        values = {s: (er_names.get(s) or {}).get("h21", {}).get("er")
                  for s in exploit_names}
        valid_priced = all(v is not None and _number(v, "expected return") > 0
                           for v in values.values())
        total_er = sum(_number(v, "expected return") for v in values.values()) if valid_priced else 0
        for sym in exploit_names:
            raw = (room * _number(values[sym], "expected return") / total_er
                   if valid_priced else room / len(exploit_names))
            scale = _number((er_names.get(sym) or {}).get("size_scale", 1.0),
                            "expected return scale")
            weights[sym] = min(float(limits["exploit_max_weight"]), raw) * min(1.0, max(0.0, scale))
            state[sym] = "EXPLOIT"
    targets = [PB.Target(symbol=s, weight=w, median_dollar_vol=adv_by.get(s),
                         reason=f"PC epoch {state[s]} {contract['content_sha256'][:12]}")
               for s, w in weights.items() if w > 0]
    exit_targets = [PB.Target(symbol=s, weight=0.0, median_dollar_vol=adv_by.get(s),
                              reason="PC epoch held exit")
                    for s in held if s not in weights and s != "SPY"]
    plans = PB.plan_orders(targets + exit_targets, equity=equity, held=held, prices=prices,
                           max_name_frac=float(alloc["non_core_name_cap"]),
                           max_invested_frac=max_gross,
                           min_order_usd=float(limits["min_order_usd"]),
                           max_adv_participation=float(limits["max_adv_participation"]),
                           rebalance_drift_frac=float(limits["rebalance_drift_frac"]))
    prior_probe = set(selectors.get("prior_probe_holdings") or [])
    # Unattributed legacy holdings consume the PROBE budget until custody is
    # proved. A rotated shortlist cannot treat a held name as free capacity.
    probe_custody = (set(probe_names) | prior_probe |
                     {s for s in held if s not in members and s not in exploit_names})
    sendable = []
    liquidity_blocks = []
    for plan in plans:
        if plan.qty <= 0 or plan.symbol == "SPY" or plan.symbol in rf_hold:
            continue
        st = state.get(plan.symbol)
        if st is None:
            st = "PROBE_EXIT" if plan.symbol in prior_probe else "EXIT"
        # Generic EXIT authority is the existing one, not widened by the
        # separate POLICY_EPOCH_EXIT_CORE transition.
        authority = (st == "REVISION_FLOW" and source_ok and bars_fresh
                     or st in {"PROBE", "PROBE_EXIT"} and probe_ok
                     or st in {"EXPLOIT", "EXIT"} and exploit_ok)
        if authority and (plan.symbol in invalid_adv or plan.symbol not in adv_by):
            liquidity_blocks.append(f"missing or invalid ADV for {plan.symbol}")
        elif authority:
            sendable.append((plan, st))
    # Existing open orders may be accepted but unresolved. Do not add any new
    # risk or queue duplicate sells until they finish and fresh evidence lands.
    if pending:
        sendable = []
    post = dict(held)
    for plan, _ in sendable:
        post[plan.symbol] = post.get(plan.symbol, 0.0) + (
            plan.qty if plan.side == "buy" else -plan.qty)
    if any(q < -1e-9 for q in post.values()):
        raise PE.EpochRefused("post-fill book would be short")
    unknown = [s for s, q in post.items() if q > 0 and
               (_number(prices.get(s) or 0, "price") <= 0
                or _number(sigmas.get(s) or 0, "daily sigma") <= 0)]
    incremental = any(plan.side == "buy" for plan, _ in sendable)
    gross, adverse = 0.0, 0.0
    if not unknown:
        for sym, qty in post.items():
            if qty <= 0:
                continue
            weight = qty * float(prices[sym]) / equity
            gross += weight
            adverse += weight * float(limits["worst_case_sigma_multiple"]) * float(sigmas[sym])
    rf_gross = (sum(post.get(s, 0.0) * float(prices.get(s) or 0) for s in members)
                / equity)
    rf_window_loss = rf_gross * float(limits["revision_21_session_adverse_return"])
    projected_cash = cash - sum((1 if p.side == "buy" else -1) * p.notional
                                for p, _ in sendable)
    blocks = []
    blocks.extend(liquidity_blocks)
    if pending:
        blocks.append("pending orders unresolved")
    if not bars_fresh:
        blocks.append("stale selector bars")
    if unknown:
        blocks.append("unknown price/sigma for held or post-fill names: " + ",".join(unknown))
    if gross > max_gross + 1e-9:
        blocks.append("post-fill gross exceeds policy cap/cash buffer")
    if adverse > float(limits["one_day_worst_case_loss_frac"]) + 1e-9:
        blocks.append("post-fill one-day scenario exceeds policy cap")
    if rf_window_loss > float(limits["revision_worst_21_session_loss_frac"]) + 1e-9:
        blocks.append("revision 21-session scenario exceeds policy cap")
    if projected_cash < equity * float(alloc["minimum_cash_buffer"]) - 1:
        blocks.append("projected cash below policy buffer")
    probe_post = sum(post.get(s, 0.0) * float(prices.get(s) or 0)
                     for s in probe_custody) / equity
    if probe_post > float(alloc["probe_gross_cap"]) + 1e-9:
        blocks.append("held plus planned PROBE/unattributed risk exceeds sleeve cap")
    if blocks and incremental:
        sendable = [(p, st) for p, st in sendable if p.side == "sell"]
    reserve = max(0.0, 1.0 - sum(weights.values()))
    return {"policy_epoch_sha256": contract["content_sha256"],
            "state": "ACTIVE", "equity_at_plan": equity, "cash_at_plan": cash,
            "held_quantities": {s: str(q) for s, q in held.items()},
            "targets": [asdict(t) for t in targets],
            "target_states": state, "held_weights": held_weights,
            "plans": [asdict(p) for p in plans],
            "sendable": [{**asdict(p), "state": st,
                          "median_dollar_vol": adv_by[p.symbol]}
                         for p, st in sendable],
            "probe_acting": probe_ok, "exploit_acting": exploit_ok,
            "shadow_exploit": shadow_exploit,
            "probe_custody_symbols": sorted(probe_custody),
            "risk_sigmas": {s: sigmas.get(s) for s in post if post[s] > 0},
            "revision_members": members,
            "revision_acting": source_ok and bars_fresh,
            "probe_weighting": weighting_meta,
            "er_priced_exploit": bool(priced),
            "rf_hold": sorted(rf_hold), "held_residual_gross": residual_gross,
            "post_fill_gross": gross if not unknown else None,
            "post_fill_scenario_frac": adverse if not unknown else None,
            "revision_21_session_scenario_frac": rf_window_loss,
            "projected_cash": projected_cash,
            "risk_blocks": blocks, "reserve_weight": reserve,
            "reserve_reason": alloc["cash_when_unqualified"] if reserve > 0 else None,
            "view_40000": _scaled_view(weights, prices, 40000.0)}


def _scaled_view(weights: dict[str, float], prices: dict[str, float], capital: float) -> dict:
    shares = {sym: math.floor(capital * w / float(prices[sym]))
              for sym, w in weights.items() if float(prices.get(sym) or 0) > 0}
    spent = sum(shares[s] * float(prices[s]) for s in shares)
    return {"capital_usd": capital, "shares": shares,
            "cash_usd": round(capital - spent, 2), "reporting_only": True}
