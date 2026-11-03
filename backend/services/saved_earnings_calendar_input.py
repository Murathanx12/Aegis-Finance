"""Pure point-in-time adapter for one injected Finnhub earnings-calendar response.

The caller asserts the original provider observation clock. A cache read or this
function's execution time cannot replace it. Hashes prove byte identity only,
not provider authenticity, calendar correctness, or a forecast.
"""

from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import re

SCHEMA = "saved-earnings-calendar-input/1"
SOURCE = "finnhub/calendar/earnings"
MAX_BYTES = 256 * 1024
MAX_ROWS = 128
MAX_DEPTH = 8
MAX_AGE = timedelta(hours=24)
MAX_DAYS_AHEAD = 7
_ROW_KEYS = frozenset({
    "symbol", "date", "hour", "quarter", "year", "epsEstimate", "revenueEstimate",
})
_ACTUAL_KEYS = frozenset({"epsActual", "revenueActual"})
_UTC_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)"
)
_TICKER_PATTERN = re.compile(r"[A-Z]{1,5}(?:[.-][A-Z])?")
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


class _Refused(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _utc(value: str, reason: str) -> datetime:
    if not isinstance(value, str) or _UTC_PATTERN.fullmatch(value) is None:
        raise _Refused(reason)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _Refused(reason) from None


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise _Refused("JSON_INVALID")
        result[key] = value
    return result


def _constant(_value: str) -> None:
    raise _Refused("JSON_INVALID")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _Refused("JSON_INVALID")
    return parsed


def _bounded_depth(value: object, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise _Refused("JSON_DEPTH_EXCEEDED")
    if isinstance(value, dict):
        for nested in value.values():
            _bounded_depth(nested, depth + 1)
    elif isinstance(value, list):
        for nested in value:
            _bounded_depth(nested, depth + 1)


def _parse(raw: bytes) -> list[dict]:
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                             parse_constant=_constant, parse_float=_finite_float)
    except (UnicodeError, ValueError, RecursionError):
        raise _Refused("JSON_INVALID") from None
    _bounded_depth(payload)
    if not isinstance(payload, dict) or set(payload) != {"earningsCalendar"}:
        raise _Refused("CALENDAR_SHAPE_INVALID")
    rows = payload["earningsCalendar"]
    if not isinstance(rows, list):
        raise _Refused("CALENDAR_SHAPE_INVALID")
    if len(rows) > MAX_ROWS:
        raise _Refused("TOO_MANY_ROWS")
    if not rows:
        raise _Refused("CALENDAR_EMPTY")
    if any(not isinstance(row, dict) for row in rows):
        raise _Refused("CALENDAR_SHAPE_INVALID")
    return rows


def _event_date(row: dict, ticker: str) -> date | None:
    if row.get("symbol") != ticker:
        return None
    if not _ROW_KEYS <= row.keys() or row.keys() - _ROW_KEYS - _ACTUAL_KEYS:
        raise _Refused("ROW_FIELDS_INVALID")
    value = row["date"]
    if not isinstance(value, str) or _DATE_PATTERN.fullmatch(value) is None:
        raise _Refused("EVENT_DATE_INVALID")
    try:
        event_date = date.fromisoformat(value)
    except ValueError:
        raise _Refused("EVENT_DATE_INVALID") from None
    if (type(row["year"]) is not int or row["year"] < 2000
            or row["year"] > 9999 or type(row["quarter"]) is not int
            or row["quarter"] not in (1, 2, 3, 4)):
        raise _Refused("FISCAL_PERIOD_INVALID")
    if row["hour"] is not None and not isinstance(row["hour"], str):
        raise _Refused("ROW_FIELDS_INVALID")
    for key in ("epsEstimate", "revenueEstimate"):
        if row[key] is not None and (type(row[key]) not in (int, float)
                                     or isinstance(row[key], bool)):
            raise _Refused("ROW_FIELDS_INVALID")
    return event_date


def _first_sunday(year: int, month: int) -> int:
    first = date(year, month, 1)
    return 1 + (6 - first.weekday()) % 7


def _new_york_date(cutoff: datetime) -> date:
    """Modern America/New_York civil date without loading a timezone file.

    US DST rules from 2007: second Sunday in March at 07:00 UTC to first
    Sunday in November at 06:00 UTC. Refuse years outside the bounded rule era.
    """
    year = cutoff.year
    if not 2007 <= year <= 2099:
        raise _Refused("ET_RULE_ERA_UNSUPPORTED")
    march_sunday = _first_sunday(year, 3) + 7
    november_sunday = _first_sunday(year, 11)
    start = datetime(year, 3, march_sunday, 7, tzinfo=timezone.utc)
    end = datetime(year, 11, november_sunday, 6, tzinfo=timezone.utc)
    offset = timedelta(hours=-4 if start <= cutoff < end else -5)
    return (cutoff + offset).date()


def build_saved_earnings_calendar_input(
    response_bytes: bytes | None, *, ticker: str, observed_utc: str,
    cutoff_utc: str,
) -> dict:
    """Return one conservative warning input or an explicit refusal.

    Exactly one matching event must be 1..7 New York calendar days after the
    decision date. ``hour`` is preserved in raw bytes but supplies no verified
    time mapping; no same-day event qualifies. Staleness is measured from the
    asserted original observation, never a cache-hit timestamp.
    """
    artifact = {"schema": SCHEMA, "status": "REFUSED", "ticker": ticker}
    if type(response_bytes) is bytes:
        artifact["response_sha256"] = _sha(response_bytes)
    try:
        if not isinstance(ticker, str) or _TICKER_PATTERN.fullmatch(ticker) is None:
            raise _Refused("TICKER_INVALID")
        observed = _utc(observed_utc, "OBSERVED_UTC_INVALID")
        cutoff = _utc(cutoff_utc, "CUTOFF_UTC_INVALID")
        artifact["observed_utc"] = observed.isoformat()
        artifact["cutoff_utc"] = cutoff.isoformat()
        if observed > cutoff:
            raise _Refused("OBSERVATION_AFTER_CUTOFF")
        if cutoff - observed > MAX_AGE:
            raise _Refused("OBSERVATION_STALE")
        if response_bytes is None or response_bytes == b"":
            raise _Refused("INPUT_ABSENT")
        if type(response_bytes) is not bytes or len(response_bytes) > MAX_BYTES:
            raise _Refused("INPUT_BYTES_INVALID_OR_TOO_LARGE")
        rows = _parse(response_bytes)
        decision_date = _new_york_date(cutoff)
        eligible: list[dict] = []
        matching = False
        for row in rows:
            event_date = _event_date(row, ticker)
            if event_date is None:
                continue
            matching = True
            days_ahead = (event_date - decision_date).days
            if 1 <= days_ahead <= MAX_DAYS_AHEAD:
                eligible.append(row)
        if not eligible:
            raise _Refused("NO_FUTURE_EVENT_IN_WINDOW" if matching else "NO_MATCHING_TICKER")
        if len(eligible) != 1:
            raise _Refused("AMBIGUOUS_EVENT")
        event = eligible[0]
        if any(event.get(key) is not None for key in _ACTUAL_KEYS):
            raise _Refused("FUTURE_ACTUAL_PRESENT")
        packet = {
            "schema": SCHEMA, "status": "EVIDENCE_ONLY", "source": SOURCE,
            "ticker": ticker, "observed_utc": observed.isoformat(),
            "cutoff_utc": cutoff.isoformat(), "decision_date_et": decision_date.isoformat(),
            "event_date_et": event["date"], "days_ahead":
                (date.fromisoformat(event["date"]) - decision_date).days,
            "fiscal_year": event["year"], "fiscal_quarter": event["quarter"],
            "event_time_status": "UNKNOWN", "response_sha256": _sha(response_bytes),
            "response_bytes_b64": base64.b64encode(response_bytes).decode("ascii"),
            "forecast_status": "NOT_GENERATED", "runtime_authority": "NONE",
            "qualification": "Injected saved response; provider authenticity unverified.",
        }
        packet["input_id"] = _sha(_canonical(packet))
        return packet
    except _Refused as exc:
        artifact["reason"] = str(exc)
        return artifact
    except (TypeError, ValueError, OverflowError, RecursionError):
        artifact["reason"] = "INPUT_INVALID"
        return artifact


def verify_saved_earnings_calendar_input(
    packet: dict, response_bytes: bytes | None, *, ticker: str,
    observed_utc: str, cutoff_utc: str,
) -> bool:
    """Rebuild and compare exactly; this checks integrity, not authenticity."""
    rebuilt = build_saved_earnings_calendar_input(
        response_bytes, ticker=ticker, observed_utc=observed_utc, cutoff_utc=cutoff_utc,
    )
    return rebuilt["status"] == "EVIDENCE_ONLY" and packet == rebuilt
