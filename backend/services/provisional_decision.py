"""Offline provisional NO_NEW_BET assessments, kept OUT of the pinned contract file.

Ported from the runtime checkout (S65, CH-05 rescue R4). On the runtime these
lived at the bottom of `backend/services/decision_contract.py` (+244 lines) and
inside `scripts/daily_pass.py` (`_cost_refusal_assessment`). They are here, in a
sibling module, because `decision_contract.py` is byte-pinned by the prepared
PC policy epoch `backend/data/pc_policy_epochs/pc_paper_no_index_2026_10_v1.json`
(`source_sha256`): any edit to that file makes `pc_policy_epoch.verify_epoch`
refuse with `policy source changed: backend/services/decision_contract.py`,
which is a policy change, not a port. Nothing below changes how a decision
contract is built, sealed or sized; it only READS `_canonical`, `seal` and
`LICENCE` from the contract module so a provisional row is sealed the same way.

Two entry points, neither of which forecasts, sizes, stores or delivers:

* `provisional_contracts(request, prior_records=...)` appends an offline
  NO_NEW_BET assessment for one declared event to caller-owned history.
* `cost_refusal_assessment(ctx, exc, observed_clock=...)` describes a
  `CostModelRefused` build failure as a PROVISIONAL refusal row, so the daily
  pass can say "no new bet, and why" instead of only "refused".

Both set `orders_authorized: False`. Licence: PRODUCT_EXPERIMENT.
"""
from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from backend.services.decision_contract import LICENCE, _canonical, seal

__all__ = ["provisional_contracts", "cost_refusal_assessment"]



def _provisional_time(value: Any) -> datetime:
    """An explicit PIT instant; a date or naive timestamp is not an instant."""
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO string with timezone")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)

def _provisional_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if math.isfinite(value) and value >= 0 else None
    except (OverflowError, ValueError):
        return None

def provisional_contracts(request: dict, *,
                          prior_records: list[dict] | None = None) -> list[dict]:
    """Append an offline NO_NEW_BET assessment to caller-owned history.

    No forecast, sizing policy, storage or delivery is performed. Evidence must
    be available AND observed by this as-of. Repeated evidence is idempotent;
    later evidence produces a child while the first PIT and mandate stay fixed.
    The caller supplies the stable event identity, horizon and original mandate.
    """
    if not isinstance(request, dict):
        raise ValueError("provisional request must be an object")
    req = deepcopy(request)
    history = deepcopy(prior_records or [])
    for key in ("event_id", "ticker", "horizon"):
        if not isinstance(req.get(key), str) or not req[key].strip():
            raise ValueError(f"{key} must be a nonempty string")
    if not isinstance(req.get("mandate"), dict) or not req["mandate"]:
        raise ValueError("original mandate is required")
    asof = _provisional_time(req["asof"])
    deadline = _provisional_time(req["deadline"])
    deadline_status = "DUE" if asof >= deadline else "BEFORE_DEADLINE"
    # Free-text horizon is a display label, not an executable time boundary.
    horizon_end = (_provisional_time(req["horizon_end"])
                   if req.get("horizon_end") is not None else None)
    horizon_status = ("UNKNOWN" if horizon_end is None else
                      "EXPIRED" if asof >= horizon_end else "WITHIN_HORIZON")
    # A fully paid long can lose its full value, even without a quote. This is
    # a conditional payoff bound, never a stop, loss budget or NAV estimate.
    if req.get("exposure_kind") != "fully_paid_long":
        raise ValueError("unit-risk envelope requires declared fully_paid_long exposure")
    required = req.get("required_evidence")
    if not isinstance(required, list) or not all(
            isinstance(item, str) and item.strip() for item in required):
        raise ValueError("required_evidence must be a list of evidence IDs")
    versions: dict[str, dict[str, dict]] = {}
    for item in req.get("available_evidence", []):
        if not isinstance(item, dict) or not isinstance(item.get("evidence_id"), str):
            raise ValueError("each evidence item requires evidence_id")
        eid = item["evidence_id"]
        if not eid.strip():
            raise ValueError("evidence_id must be nonempty")
        if eid in {"price_usd", "shares", "equity_usd", "exposure_usd", "cash_usd"}:
            value = item.get("value")
            if _provisional_number(value) is None:
                item["value"] = None
                item["quality"] = "INVALID_NUMERIC_VALUE"
                item["qualification"] = "Missing, negative, nonnumeric or nonfinite input; not zero."
        # Strict serialization applies only to this new branch. Do not change
        # legacy seal semantics or silently rewrite an inherited mandate.
        json.dumps(item, allow_nan=False)
        versions.setdefault(eid, {})[_canonical(item)] = item
    evidence = {}
    for eid, variants in versions.items():
        ordered = [variants[key] for key in sorted(variants)]
        evidence[eid] = (ordered[0] if len(ordered) == 1 else
                         {"evidence_id": eid, "quality": "CONTRADICTORY", "versions": ordered})
    usable, unusable, warnings = [], [], []
    if horizon_end is None:
        warnings.append("horizon end unknown; no executable horizon or current-action qualification")
    elif horizon_status == "EXPIRED":
        warnings.append("declared horizon expired; review required, no investment action is qualified")
    for eid, item in sorted(evidence.items()):
        reason = None
        try:
            available = _provisional_time(item.get("available_at"))
            observed = _provisional_time(item.get("observed_at"))
            if available > observed or max(available, observed) > asof:
                reason = "outside PIT cut or availability after observation"
            if item.get("valid_until") is not None and asof > _provisional_time(item["valid_until"]):
                reason = "stale: caller-declared validity expired"
        except (ValueError, TypeError):
            reason = "missing or ambiguous availability/observation time"
        if item.get("quality") != "AVAILABLE":
            reason = f"quality {item.get('quality', 'UNKNOWN')}"
        source = item.get("source")
        version = item.get("source_sha256")
        if (not isinstance(source, str) or not source.strip()
                or not isinstance(version, str) or len(version) != 64
                or any(c not in "0123456789abcdefABCDEF" for c in version)):
            reason = ((reason + "; ") if reason else "") + "missing immutable source/version binding"
        if reason:
            unusable.append({"evidence": item, "reason": reason})
            warnings.append(f"{eid}: {reason}")
        else:
            usable.append(item)
    by_id = {item["evidence_id"]: item for item in usable}
    missing = sorted(set(required) - by_id.keys())
    try:
        event_time = _provisional_time(req.get("event_time")).isoformat()
    except (ValueError, TypeError):
        event_time = None
        warnings.append("event_time missing or ambiguous; no event-window timing claim")
    price = _provisional_number(by_id.get("price_usd", {}).get("value"))
    exposure = _provisional_number(by_id.get("exposure_usd", {}).get("value"))
    if price is None or price <= 0:
        price = None
        if exposure is None:
            missing = sorted(set(missing) | {"price_usd"})
    # Holdings and equity need the same PIT qualification as a quote/report;
    # unversioned top-level quantities cannot enter an exposure calculation.
    shares = _provisional_number(by_id.get("shares", {}).get("value"))
    equity = _provisional_number(by_id.get("equity_usd", {}).get("value"))
    if shares is None and exposure is None:
        missing = sorted(set(missing) | {"shares"})
    if equity is None or equity <= 0:
        equity = None
        missing = sorted(set(missing) | {"equity_usd"})
    delivery = deepcopy(req.get("delivery_status") or {"status": "NOT_ATTEMPTED"})
    if delivery.get("status") not in ("NOT_ATTEMPTED", "FAILED"):
        raise ValueError("offline delivery status must be NOT_ATTEMPTED or FAILED")
    if delivery.get("receipt") is not None:
        raise ValueError("offline assessment cannot assert a delivery receipt")
    delivery["receipt"] = None
    losses = req.get("conditional_loss_fractions", [])
    if not isinstance(losses, list) or any(
            _provisional_number(loss) is None or loss > 1 for loss in losses):
        raise ValueError("conditional loss fractions must be finite numbers in [0, 1]")
    shocks = req.get("conditional_return_fractions", [])
    if not isinstance(shocks, list) or any(
            isinstance(shock, bool) or not isinstance(shock, (int, float))
            or not math.isfinite(shock) or shock < -1 for shock in shocks):
        raise ValueError("conditional returns must be finite and at least -1 for a fully paid long")
    position = price * shares if price is not None and shares is not None else exposure
    if exposure is not None and position is not None and not math.isclose(exposure, position):
        position = None
        warnings.append("exposure_usd contradicts shares times price; only unit risk is usable")
    if position is not None and not math.isfinite(position):
        raise ValueError("supplied position value is not finite")
    def finite_derived(value):
        if value is not None and not math.isfinite(value):
            raise ValueError("conditional arithmetic is not finite")
        return value
    position_fraction = finite_derived(position / equity
        if position is not None and equity is not None else None)
    shock_rows = []
    for shock in sorted(set(shocks)):
        pnl = finite_derived(position * shock if position is not None else None)
        shock_rows.append({"return_fraction": shock, "pnl_per_unit_exposure": shock,
                           "pnl_usd": pnl, "equity_fraction": finite_derived(
                               pnl / equity if pnl is not None and equity is not None else None)})
    snapshot = {
        "available_evidence": usable, "unusable_evidence": unusable,
        "missing_evidence": missing, "event_time": event_time,
        "price_usd": price, "shares": shares, "equity_usd": equity,
        "exposure_usd": exposure,
        "conditional_loss_fractions": sorted(set(losses)),
        "conditional_return_fractions": sorted(set(shocks)),
        "delivery_status": delivery,
        "deadline_status": deadline_status,
        "horizon_end": horizon_end.isoformat() if horizon_end else None,
        "horizon_status": horizon_status,
    }
    # asof itself is not a new event. Crossing the original horizon must be a
    # new declared horizon, rather than making repeated scheduler reads new bets.
    fingerprint = hashlib.sha256(_canonical(snapshot).encode("utf-8")).hexdigest()
    related = [r for r in history if r.get("row_kind") == "PROVISIONAL_DECISION"
               and r.get("event_id") == req["event_id"] and r.get("ticker") == req["ticker"]]
    parent = related[-1] if related else None
    if parent:
        if any(r.get("artifact_sha256") != seal(r) for r in related):
            raise ValueError("prior record seal mismatch")
        for key in ("mandate", "horizon", "deadline", "exposure_kind"):
            if parent[key] != req[key]:
                raise ValueError(f"{key} cannot change within an event; declare a new event")
        if parent.get("horizon_end") != snapshot["horizon_end"]:
            raise ValueError("horizon_end cannot change within an event; declare a new event")
        if asof < _provisional_time(parent["asof"]):
            raise ValueError("an update cannot predate its parent")
        if parent["evidence_state_sha256"] == fingerprint:
            return history
    original_pit = deepcopy(parent["original_pit"] if parent else
                            {"asof": asof.isoformat(), "evidence": snapshot,
                             "mandate": req["mandate"]})
    action = "NO_NEW_BET"
    rationale = (
        "No automated position change is authorized by this assessment. "
        "No new event bet is supported by a measured directional edge at this seam. "
        "This does not recommend retaining every holding or confirm mandate compliance. "
        "Review existing exposure against the owner's verified loss budget; "
        "that budget and the investment action remain unresolved here. Continue evidence collection. "
        + ("Missing evidence: " + ", ".join(missing) + ". " if missing else "")
        + ("Data-quality warnings: " + "; ".join(warnings) + "." if warnings else ""))
    identity = {"event_id": req["event_id"], "ticker": req["ticker"],
                "original_pit": original_pit, "horizon": req["horizon"],
                "parent": parent["decision_id"] if parent else None,
                "evidence_state_sha256": fingerprint}
    row = {
        "row_kind": "PROVISIONAL_DECISION", "decision_status": "PROVISIONAL",
        "decision_id": hashlib.sha256(_canonical(identity).encode("utf-8")).hexdigest()[:16],
        "parent_decision_id": parent["decision_id"] if parent else None,
        "event_id": req["event_id"], "ticker": req["ticker"],
        "asof": asof.isoformat(), "deadline": req["deadline"],
        "horizon": req["horizon"], "exposure_kind": req["exposure_kind"],
        "mandate": req["mandate"], "original_pit": original_pit,
        "evidence_state_sha256": fingerprint, **snapshot,
        "data_quality_warnings": warnings,
        "conditional_risk": {
            "basis": "fully paid long, no leverage; conditional loss per USD 1 exposure",
            "maximum_loss_per_unit_exposure": 1.0,
            "scenarios": [{"loss_fraction": loss, "loss_per_unit_exposure": loss}
                          for loss in sorted(set(losses))],
            "hypothetical_shocks": shock_rows,
            "price_evidence": by_id.get("price_usd") if price is not None else None,
            "position_value_usd": position,
            "maximum_position_loss_usd": position,
            "portfolio_loss_fraction": position_fraction,
            "qualification": "Payoff envelope, not a forecast, stop, sizing instruction or loss budget.",
        },
        "probability_type": "NOT_CALIBRATED", "estimated_probability": None,
        "uncertainty": "No calibrated directional probability; conditional scenarios have no assigned odds.",
        "fallback": "Use qualified evidence and conditional unit risk; continue collecting absent inputs.",
        "direction": "REFUSED", "action": action, "rationale": rationale,
        "operational_action": "NO_AUTOMATED_CHANGE", "investment_action": "UNRESOLVED",
        "invalidating_evidence": ["Verified report changes the thesis or risk assumptions",
                                  "Corrected quote/holding or contradictory primary evidence",
                                  "Measured directional edge under the original mandate"],
        "update_trigger": ["Required evidence arrives with availability and observation timestamps",
                           "Quote/holdings or data quality changes", "Declared horizon expires",
                           "Delivery fails or is independently confirmed"],
        "licence": LICENCE, "orders_authorized": False,
    }
    json.dumps(row, allow_nan=False)
    row["artifact_sha256"] = seal(row)
    return history + [row]


def _cause(exc: BaseException, n: int = 400) -> str:
    """Same text as `scripts.daily_pass._trunc`, so the row and the step agree."""
    return f"{type(exc).__name__}: {exc}"[:n]


def cost_refusal_assessment(ctx: dict, exc: BaseException, *,
                            observed_clock: Callable[[], datetime] | None = None) -> dict:
    """Describe this observed failure, without inventing a market assessment.

    Ported from the runtime's `scripts.daily_pass._cost_refusal_assessment`.
    `ctx` is the daily pass context; only `ctx["date"]` (required) and an
    optional `ctx["mandate"]` are read.

    The pass date is a context cutoff label, never a historical PIT instant.
    No market data, storage, delivery, mandate derivation or sizing is called.
    """
    warnings = []
    try:
        observed = (observed_clock or (lambda: datetime.now(timezone.utc)))()
        if not isinstance(observed, datetime) or observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("observation clock requires an aware datetime")
        asof = observed.astimezone(timezone.utc).isoformat()
    except Exception:
        asof = None
        warnings.append("INVALID_OBSERVATION_CLOCK: no assessment timestamp was inferred")
    mandate = None
    mandate_status = "NOT_SUPPLIED"
    if "mandate" in ctx:
        try:
            if not isinstance(ctx["mandate"], dict):
                raise ValueError("mandate must be an object")
            json.dumps(ctx["mandate"], allow_nan=False)
            mandate = deepcopy(ctx["mandate"])
            mandate_status = "SUPPLIED_UNVERIFIED"
        except (TypeError, ValueError, OverflowError):
            mandate_status = "INVALID"
            warnings.append("INVALID_SUPPLIED_MANDATE: no replacement mandate was inferred")
    cause = _cause(exc)
    return {
        "row_kind": "PROVISIONAL_REFUSAL_ASSESSMENT",
        "decision_status": "PROVISIONAL" if asof else "PROVISIONAL_UNTIMED",
        "asof": asof, "asof_basis": ("ACTUAL_REFUSAL_OBSERVATION_CLOCK" if asof else
                                    "UNKNOWN_INVALID_OBSERVATION_CLOCK"),
        "context_cutoff": {"date": ctx["date"], "instant": None,
                           "qualification": "DATE_LABEL_ONLY_NOT_HISTORICAL_AVAILABILITY"},
        "horizon": "Until the cost-model refusal is resolved and inputs are revalidated",
        "horizon_end": None,
        "original_failure": {"type": type(exc).__name__, "cause": cause,
                             "source": "daily_pass.build_decision_contracts"},
        "available_evidence": [{"evidence_id": "typed_cost_model_refusal",
                                "kind": "OPERATIONAL_FAILURE_ONLY",
                                "observed_at": asof, "cause": cause}],
        "missing_evidence": ["usable_cost_model", "completed_decision_contract",
                             "qualified_market_prices", "verified_holdings_and_exposure",
                             "qualified_directional_evidence", "verified_mandate"],
        "market_assessment_status": "UNAVAILABLE_FROM_REFUSED_BUILD",
        "mandate": mandate, "mandate_status": mandate_status,
        "mandate_compliance": "NOT_ASSESSED",
        "price_usd": None, "exposure_usd": None, "equity_usd": None,
        "conditional_risk": {"status": "UNKNOWN_NO_EXPLICIT_EXPOSURE_ASSUMPTION",
                             "assumption": None, "loss_per_unit_exposure": None,
                             "loss_usd": None, "scenarios": []},
        "probability_type": "NOT_ESTIMATED", "estimated_probability": None,
        "uncertainty": "The failed build supplies no qualified market, exposure or directional estimate.",
        "action": "NO_NEW_BET", "operational_action": "NO_AUTOMATED_CHANGE",
        "investment_action": "UNRESOLVED", "orders_authorized": False,
        "rationale": "The cost model refused the build. No new bet or automated position change "
                     "is supported by this failed build. This is not a hold-every-position "
                     "recommendation or a mandate-compliance assessment.",
        "invalidating_evidence": ["Corrected cost inputs and a successfully rebuilt, qualified contract",
                                  "Verified market/holding evidence changes the assessment inputs"],
        "update_trigger": ["Resolve the recorded cost-model cause and rebuild with explicit costs",
                           "Revalidate evidence availability, holdings and the supplied mandate"],
        "delivery_status": {"status": "NOT_ATTEMPTED", "receipt": None},
        "data_quality_warnings": warnings,
    }
