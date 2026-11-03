"""Explicit, offline-by-default capture of one Finnhub earnings calendar response.

Only ``capture_earnings_calendar`` performs I/O. A receipt records the original
observation and byte identity, not the response body or the API token. Callers
must keep response bytes separately if they want to evaluate them again.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from backend.config import api_keys
from backend.services.owner_event_warning import _journal_identity
from backend.services.saved_earnings_calendar_input import (
    MAX_BYTES,
    build_saved_earnings_calendar_input,
)

_URL = "https://finnhub.io/api/v1/calendar/earnings"
_TICKER = re.compile(r"[A-Z]{1,5}(?:[.-][A-Z])?")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SCHEMA = "earnings-calendar-capture/1"


class CaptureRefused(ValueError):
    """A refusal with a fixed code; never includes provider or transport text."""


def _refuse(reason: str) -> None:
    raise CaptureRefused(reason)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _date(value: str) -> date:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        _refuse("DATE_INVALID")
    try:
        return date.fromisoformat(value)
    except ValueError:
        _refuse("DATE_INVALID")


def _private_identity(directory: Path) -> tuple[int, int]:
    try:
        return _journal_identity(directory)
    except (OSError, ValueError, TypeError):
        _refuse("PRIVATE_DIRECTORY_REQUIRED")


def _observed(clock) -> str:
    try:
        now = clock()
    except Exception:
        _refuse("CLOCK_FAILED")
    if not isinstance(now, datetime) or now.utcoffset() != timedelta(0):
        _refuse("UTC_CLOCK_REQUIRED")
    return now.isoformat()


def _receipt_bytes(*, ticker: str, start: str, end: str, observed: str, cutoff: str,
                   raw: bytes, packet: dict) -> bytes:
    receipt = {
        "schema": _SCHEMA,
        "source": "finnhub/calendar/earnings",
        "ticker": ticker,
        "from": start,
        "to": end,
        "observed_utc": observed,
        "cutoff_utc": cutoff,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "input_id": packet["input_id"],
    }
    return (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_new(directory: Path, raw: bytes) -> Path:
    path = directory / f"earnings-calendar-{uuid.uuid4().hex}.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = None
    created = False
    try:
        fd = os.open(path, flags, 0o600)
        created = True
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return path
    except FileExistsError:
        _refuse("RECEIPT_EXISTS")
    except OSError:
        if created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        _refuse("RECEIPT_WRITE_FAILED")
    finally:
        if fd is not None:
            os.close(fd)


def capture_earnings_calendar(
    *, ticker: str, start: str, end: str, cutoff_utc: str,
    private_dir: Path, transport=None, clock=None, api_key: str | None = None,
) -> dict:
    """Fetch once on explicit invocation; persist only a successful capture.

    ``transport`` has the ``requests.get(url, params=..., timeout=...)`` shape.
    The injected clock is called immediately after that call returns. No cache
    path can call this function implicitly or substitute a later timestamp.
    """
    if not isinstance(ticker, str) or not _TICKER.fullmatch(ticker):
        _refuse("TICKER_INVALID")
    first, last = _date(start), _date(end)
    if first > last:
        _refuse("DATE_RANGE_INVALID")
    key = api_keys.finnhub if api_key is None else api_key
    if not isinstance(key, str) or not key.strip() or "placeholder" in key.lower():
        _refuse("FINNHUB_KEY_ABSENT")
    try:
        directory = Path(private_dir)
    except (TypeError, ValueError):
        _refuse("PRIVATE_DIRECTORY_REQUIRED")
    identity = _private_identity(directory)
    if transport is None:
        import requests

        transport = requests.get
    if clock is None:
        clock = _utc_now
    try:
        response = transport(
            _URL,
            params={"symbol": ticker, "from": start, "to": end, "token": key},
            timeout=10,
        )
    except Exception:
        _refuse("FETCH_FAILED")
    observed = _observed(clock)
    try:
        status = response.status_code
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        raw = response.content
    except Exception:
        _refuse("RESPONSE_INVALID")
    if status != 200:
        _refuse("HTTP_NON_200")
    if content_type != "application/json":
        _refuse("CONTENT_TYPE_INVALID")
    if type(raw) is not bytes or not raw or len(raw) > MAX_BYTES:
        _refuse("RESPONSE_BYTES_INVALID")
    packet = build_saved_earnings_calendar_input(
        raw, ticker=ticker, observed_utc=observed, cutoff_utc=cutoff_utc,
    )
    if packet["status"] != "EVIDENCE_ONLY":
        _refuse(packet["reason"])
    if _private_identity(directory) != identity:
        _refuse("PRIVATE_DIRECTORY_CHANGED")
    receipt = _receipt_bytes(ticker=ticker, start=start, end=end,
                             observed=observed, cutoff=cutoff_utc, raw=raw, packet=packet)
    path = _write_new(directory, receipt)
    return {"packet": packet, "receipt_path": path}


def evaluate_saved_capture(receipt: dict, response_bytes: bytes, *, cutoff_utc: str) -> dict:
    """Re-evaluate exact saved bytes with the original observation clock."""
    if (type(receipt) is not dict or receipt.get("schema") != _SCHEMA
            or type(response_bytes) is not bytes
            or receipt.get("response_sha256") != hashlib.sha256(response_bytes).hexdigest()
            or not isinstance(receipt.get("ticker"), str)
            or not isinstance(receipt.get("observed_utc"), str)
            or not isinstance(receipt.get("cutoff_utc"), str)
            or not isinstance(receipt.get("input_id"), str)):
        _refuse("SAVED_CAPTURE_INVALID")
    original = build_saved_earnings_calendar_input(
        response_bytes, ticker=receipt["ticker"],
        observed_utc=receipt["observed_utc"], cutoff_utc=receipt["cutoff_utc"],
    )
    if original.get("input_id") != receipt["input_id"]:
        _refuse("SAVED_CAPTURE_INVALID")
    return build_saved_earnings_calendar_input(
        response_bytes, ticker=receipt["ticker"],
        observed_utc=receipt["observed_utc"], cutoff_utc=cutoff_utc,
    )
