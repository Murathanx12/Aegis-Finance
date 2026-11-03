"""Offline, pure owner warning from frozen calendar evidence and PC-PAPER bytes.

The calendar provider and account path are caller attestations. This candidate
does not fetch, deliver, journal, trade, or claim a calibrated event forecast.
"""

from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re

SCHEMA = "saved-earnings-calendar-input/1"
SOURCE = "finnhub/calendar/earnings"
MAX_AGE = timedelta(hours=24)
TICKER = re.compile(r"[A-Z]{1,5}(?:[.-][A-Z])?")
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)")
ROW_KEYS = {"symbol", "date", "hour", "quarter", "year", "epsEstimate", "revenueEstimate"}
ACTUAL_KEYS = {"epsActual", "revenueActual"}


class _Refused(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise _Refused("JSON_INVALID")
        result[key] = value
    return result


def _bad_constant(_value: str) -> None:
    raise _Refused("JSON_INVALID")


def _float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise _Refused("JSON_INVALID")
    return result


def _object(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                           parse_constant=_bad_constant, parse_float=_float)
    except (UnicodeError, ValueError, RecursionError):
        raise _Refused("JSON_INVALID") from None
    if type(value) is not dict:
        raise _Refused("JSON_INVALID")
    return value


def _bounded_depth(value: object, depth: int = 0) -> None:
    if depth > 8:
        raise _Refused("JSON_DEPTH_EXCEEDED")
    if isinstance(value, dict):
        for nested in value.values():
            _bounded_depth(nested, depth + 1)
    elif isinstance(value, list):
        for nested in value:
            _bounded_depth(nested, depth + 1)


def _utc(value: str) -> datetime:
    if type(value) is not str or UTC.fullmatch(value) is None:
        raise _Refused("UTC_INVALID")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _Refused("UTC_INVALID") from None


def _et_date(cutoff: datetime) -> date:
    # Mirrors the packet producer's bounded 2007+ US DST civil-date rule.
    year = cutoff.year
    if not 2007 <= year <= 2099:
        raise _Refused("ET_RULE_ERA_UNSUPPORTED")

    def first_sunday(month: int) -> int:
        return 1 + (6 - date(year, month, 1).weekday()) % 7

    start = datetime(year, 3, first_sunday(3) + 7, 7, tzinfo=timezone.utc)
    end = datetime(year, 11, first_sunday(11), 6, tzinfo=timezone.utc)
    return (cutoff + timedelta(hours=-4 if start <= cutoff < end else -5)).date()


def _number(value: object) -> Decimal:
    if type(value) not in (str, int, float):
        raise _Refused("BAD_EQUITY_OR_EXPOSURE")
    result = Decimal(str(value))
    if not result.is_finite():
        raise _Refused("BAD_EQUITY_OR_EXPOSURE")
    return result


def _calendar(packet: dict, response: bytes, cutoff: datetime,
              now: datetime) -> tuple[str, date]:
    """Rebuild the producer packet from raw response; compare exact canonical bytes."""
    if type(packet) is not dict or type(response) is not bytes or not 0 < len(response) <= 256 * 1024:
        raise _Refused("PACKET_OR_RESPONSE_INVALID")
    ticker = packet.get("ticker")
    if type(ticker) is not str or TICKER.fullmatch(ticker) is None:
        raise _Refused("TICKER_INVALID")
    observed = _utc(packet.get("observed_utc"))
    packet_cutoff = _utc(packet.get("cutoff_utc"))
    if packet_cutoff != cutoff:
        raise _Refused("CUTOFF_MISMATCH")
    if observed > cutoff:
        raise _Refused("OBSERVATION_AFTER_CUTOFF")
    if cutoff - observed > MAX_AGE:
        raise _Refused("OBSERVATION_STALE")
    if now - observed > MAX_AGE:
        raise _Refused("OBSERVATION_STALE_AT_NOW")
    payload = _object(response)
    _bounded_depth(payload)
    if set(payload) != {"earningsCalendar"} or type(payload["earningsCalendar"]) is not list:
        raise _Refused("CALENDAR_SHAPE_INVALID")
    rows = payload["earningsCalendar"]
    if not 0 < len(rows) <= 128 or any(type(row) is not dict for row in rows):
        raise _Refused("CALENDAR_SHAPE_INVALID")
    decision_date = _et_date(cutoff)
    matching = [row for row in rows if row.get("symbol") == ticker]
    # The source producer collapses byte-identical duplicates; this owner
    # candidate refuses them because issuer selection is no longer unique.
    if len(matching) != 1:
        raise _Refused("ISSUER_SELECTION_AMBIGUOUS")
    row = matching[0]
    if not ROW_KEYS <= row.keys() or row.keys() - ROW_KEYS - ACTUAL_KEYS:
        raise _Refused("ROW_FIELDS_INVALID")
    if type(row["date"]) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date"]) is None:
        raise _Refused("EVENT_DATE_INVALID")
    try:
        event_date = date.fromisoformat(row["date"])
    except ValueError:
        raise _Refused("EVENT_DATE_INVALID") from None
    days = (event_date - decision_date).days
    if not 1 <= days <= 7:
        raise _Refused("EVENT_OUTSIDE_WINDOW")
    if _et_date(now) >= event_date:
        raise _Refused("EVENT_DATE_STARTED_ET")
    if any(row.get(key) is not None for key in ACTUAL_KEYS):
        raise _Refused("FUTURE_ACTUAL_PRESENT")
    if (type(row["year"]) is not int or not 2000 <= row["year"] <= 9999
            or type(row["quarter"]) is not int or row["quarter"] not in (1, 2, 3, 4)
            or row["hour"] is not None and type(row["hour"]) is not str
            or any(row[key] is not None and type(row[key]) not in (int, float)
                   for key in ("epsEstimate", "revenueEstimate"))):
        raise _Refused("ROW_FIELDS_INVALID")
    rebuilt = {
        "schema": SCHEMA, "status": "EVIDENCE_ONLY", "source": SOURCE,
        "ticker": ticker, "observed_utc": observed.isoformat(),
        "cutoff_utc": cutoff.isoformat(), "decision_date_et": decision_date.isoformat(),
        "event_date_et": event_date.isoformat(), "days_ahead": days,
        "fiscal_year": row["year"], "fiscal_quarter": row["quarter"],
        "event_time_status": "UNKNOWN", "response_sha256": _sha(response),
        "response_bytes_b64": base64.b64encode(response).decode("ascii"),
        "forecast_status": "NOT_GENERATED", "runtime_authority": "NONE",
        "qualification": "Injected saved response; provider authenticity unverified.",
    }
    rebuilt["input_id"] = _sha(_canonical(rebuilt))
    if _canonical(packet) != _canonical(rebuilt):
        raise _Refused("PACKET_RECOMPUTATION_MISMATCH")
    return ticker, event_date


def _exposure(snapshot_bytes: bytes, expected_snapshot_sha256: str,
              expected_account_sha256: str, ticker: str, cutoff: datetime,
              now: datetime) -> tuple[Decimal, Decimal, datetime, Decimal, Decimal]:
    if (type(snapshot_bytes) is not bytes or type(expected_snapshot_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_snapshot_sha256) is None
            or _sha(snapshot_bytes) != expected_snapshot_sha256):
        raise _Refused("SNAPSHOT_SHA256_MISMATCH")
    if (type(expected_account_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_account_sha256) is None):
        raise _Refused("EXPECTED_ACCOUNT_HASH_REQUIRED")
    snap = _object(snapshot_bytes)
    account = snap.get("account_number")
    if type(account) is not str or not account or account != account.strip():
        raise _Refused("ACCOUNT_REQUIRED")
    if _sha(account.encode("utf-8")) != expected_account_sha256:
        raise _Refused("ACCOUNT_MISMATCH")
    as_of = _utc(snap.get("t"))
    if as_of > cutoff:
        raise _Refused("SNAPSHOT_AFTER_CUTOFF")
    if cutoff - as_of > MAX_AGE:
        raise _Refused("SNAPSHOT_STALE")
    if now - as_of > MAX_AGE:
        raise _Refused("SNAPSHOT_STALE_AT_NOW")
    positions = snap.get("positions")
    if type(positions) is not list or type(snap.get("n_positions")) is not int:
        raise _Refused("BAD_EQUITY_OR_EXPOSURE")
    equity = _number(snap.get("equity"))
    cash = _number(snap.get("cash"))
    reported_long = _number(snap.get("long_market_value"))
    reported_short = _number(snap.get("short_market_value"))
    if (equity <= 0 or cash < 0 or reported_long < 0 or reported_short != 0
            or snap["n_positions"] != len(positions)
            or abs(cash + reported_long - equity) > Decimal("0.01")
            or any(key in snap for key in ("margin", "margin_debt", "margin_used", "margin_enabled"))
            or "leverage" in snap and _number(snap["leverage"]) != 1):
        raise _Refused("BAD_EQUITY_OR_EXPOSURE")
    total = Decimal(0)
    held = None
    held_residual = None
    seen = set()
    for pos in positions:
        if type(pos) is not dict:
            raise _Refused("BAD_EQUITY_OR_EXPOSURE")
        symbol = pos.get("symbol")
        if (type(symbol) is not str or TICKER.fullmatch(symbol) is None
                or symbol in seen or pos.get("side", "long") != "long"
                or pos.get("asset_class", "us_equity") != "us_equity"
                or _number(pos.get("leverage", 1)) != 1):
            raise _Refused("BAD_EQUITY_OR_EXPOSURE")
        seen.add(symbol)
        qty = _number(pos.get("qty"))
        value = _number(pos.get("market_value"))
        if qty <= 0 or value <= 0:
            raise _Refused("BAD_EQUITY_OR_EXPOSURE")
        total += value
        if symbol == ticker:
            held = value
            held_residual = value - qty * _number(pos.get("current_price"))
            if abs(held_residual) > Decimal("0.01"):
                raise _Refused("HELD_MARK_MISMATCH")
    residual = reported_long - total
    allowed = max(Decimal("1.00"), equity * Decimal("0.0001"))
    if abs(residual) > allowed or total > equity:
        raise _Refused("BAD_EQUITY_OR_EXPOSURE")
    if held is None:
        raise _Refused("NOT_HELD")
    return held, equity, as_of, residual, held_residual


def build_pre_event_warning_bytes(*, packet: dict, response_bytes: bytes,
                                  snapshot_bytes: bytes, expected_snapshot_sha256: str,
                                  expected_account_sha256: str,
                                  cutoff_utc: str, now_utc: str) -> dict:
    """Build a dated, deterministic candidate from caller-frozen bytes only."""
    artifact = {"schema": "pre-event-owner-warning/1", "status": "REFUSED",
                "reason": "INPUT_INVALID", "forecast_status": "NO_CALIBRATED_EVENT_FORECAST",
                "runtime_authority": "NONE"}
    try:
        cutoff, now = _utc(cutoff_utc), _utc(now_utc)
        artifact["at_utc"] = now.isoformat()
        if now < cutoff:
            raise _Refused("NOW_BEFORE_CUTOFF")
        ticker, event_date = _calendar(packet, response_bytes, cutoff, now)
        held, equity, as_of, residual, mark_residual = _exposure(
            snapshot_bytes, expected_snapshot_sha256, expected_account_sha256,
            ticker, cutoff, now)
        event_id = _sha(_canonical({"source": SOURCE, "ticker": ticker,
                                   "event_date_et": event_date.isoformat(),
                                   "fiscal_year": packet["fiscal_year"],
                                   "fiscal_quarter": packet["fiscal_quarter"]}))
        decision_id = _sha(_canonical({"event_id": event_id, "input_id": packet["input_id"],
                                      "snapshot_sha256": expected_snapshot_sha256,
                                      "account_pin_sha256": expected_account_sha256,
                                      "cutoff_utc": cutoff.isoformat()}))
        artifact.update({
            "status": "PROVISIONAL", "reason": "SAVED_EVIDENCE_ONLY", "ticker": ticker,
            "at_utc": now.isoformat(), "cutoff_utc": cutoff.isoformat(),
            "event_date_et": event_date.isoformat(), "days_ahead_et": packet["days_ahead"],
            "event_time_status": "UNKNOWN", "observed_utc": packet["observed_utc"],
            "snapshot_as_of_utc": as_of.isoformat(), "response_sha256": packet["response_sha256"],
            "snapshot_sha256": expected_snapshot_sha256, "input_id": packet["input_id"],
            "event_id": event_id, "decision_id": decision_id,
            "saved_exposure_usd": str(held), "equity_usd": str(equity),
            "exposure_weight": str(held / equity),
            "conditional_loss_usd": {"5_percent_decline": str(held * Decimal("0.05")),
                                     "10_percent_decline": str(held * Decimal("0.10"))},
            "reconciliation": {"reported_long_minus_positions_usd": str(residual),
                               "held_qty_price_residual_usd": str(mark_residual)},
            "stress_basis": "Conditional dollar arithmetic on saved exposure; no probability or forecast.",
            "paper_decision": ["HOLD_EXISTING", "NO_NEW_BET", "REVIEW_NEW_EVIDENCE"],
            "interpretation": "No beat/miss, return, or price direction inferred. Owner loss budget UNKNOWN.",
            "next_update_trigger": "Fresh verified event evidence and reconciled PC-PAPER snapshot.",
        })
    except (_Refused, KeyError, TypeError, ValueError, InvalidOperation,
            OverflowError, RecursionError, UnicodeError) as exc:
        artifact["reason"] = str(exc) if isinstance(exc, _Refused) else "INPUT_INVALID"
    return artifact
