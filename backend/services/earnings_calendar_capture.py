"""Explicit bounded calendar capture; no schedule or runtime wiring.

The existing private directory is trusted against same-user replacement during
capture. Identity checks detect observed swaps, but are not handle-bound locks.
"""

from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import uuid

from backend.config import api_keys
from backend.services.owner_event_warning import _journal_identity
from backend.services.saved_earnings_calendar_input import (
    MAX_BYTES,
    _new_york_date,
    build_saved_earnings_calendar_input,
)

_URL = "https://finnhub.io/api/v1/calendar/earnings"
_TICKER = re.compile(r"[A-Z]{1,5}(?:[.-][A-Z])?")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)")
_SCHEMA = "earnings-calendar-capture/3"
_SOURCE = "finnhub/calendar/earnings"
_FINAL_NAME = re.compile(r"earnings-calendar-[0-9a-f]{32}\.json")
_RECEIPT_KEYS = frozenset({
    "schema", "source", "ticker", "from", "to", "observed_utc", "cutoff_utc",
    "response_sha256", "response_bytes_b64", "input_id", "receipt_id",
})
_MAX_RECEIPT_BYTES = 4 * ((MAX_BYTES + 2) // 3) + 2048
_TOTAL_SECONDS = 15


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
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None:
        _refuse("DATE_INVALID")
    return parsed


def _cutoff(value: str) -> date:
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        _refuse("CUTOFF_UTC_INVALID")
    try:
        result = _new_york_date(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (ValueError, OverflowError):
        result = None
    if result is None:
        _refuse("CUTOFF_UTC_INVALID")
    return result


def _private_identity(directory: Path) -> tuple[int, int]:
    try:
        identity = _journal_identity(directory)
    except (OSError, ValueError, TypeError):
        identity = None
    if identity is None:
        _refuse("PRIVATE_DIRECTORY_REQUIRED")
    return identity


def _observed(clock) -> str:
    try:
        now = clock()
    except Exception:
        now = None
    if not isinstance(now, datetime) or now.utcoffset() != timedelta(0):
        _refuse("UTC_CLOCK_REQUIRED")
    return now.isoformat()


def _elapsed(monotonic, start: float) -> None:
    try:
        now = monotonic()
    except Exception:
        now = float("inf")
    if not isinstance(now, (float, int)) or not math.isfinite(now) or now < start:
        _refuse("ELAPSED_CLOCK_INVALID")
    if now - start > _TOTAL_SECONDS:
        _refuse("TOTAL_DEADLINE_EXCEEDED")


def _read_body(response, monotonic, start: float) -> bytes:
    body = bytearray()
    failed = False
    try:
        # One-byte reads keep a trickling response from withholding a large
        # chunk across the entire deadline. The socket read timeout still
        # bounds how late the next elapsed check can run.
        for chunk in response.iter_content(chunk_size=1):
            _elapsed(monotonic, start)
            if type(chunk) is not bytes:
                failed = True
                break
            if len(body) + len(chunk) > MAX_BYTES:
                failed = True
                break
            body.extend(chunk)
    except CaptureRefused:
        raise
    except Exception:
        failed = True
    if failed:
        _refuse("RESPONSE_BYTES_INVALID")
    return bytes(body)


def _echoes_token(raw: bytes, key: str) -> bool:
    if key.encode("utf-8") in raw:
        return True
    # JSON escapes can hide the literal token bytes while decoding to the key.
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        return False  # The adapter has already refused malformed JSON.
    pending = [payload]
    while pending:
        value = pending.pop()
        if isinstance(value, str) and key in value:
            return True
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return False


def _seal(receipt: dict) -> str:
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_id"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _valid_receipt(receipt: dict, raw: bytes) -> bool:
    if (type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS
            or any(type(value) is not str for value in receipt.values())
            or receipt["schema"] != _SCHEMA or receipt["source"] != _SOURCE
            or _TICKER.fullmatch(receipt["ticker"]) is None
            or type(raw) is not bytes or not raw or len(raw) > MAX_BYTES
            or receipt["response_sha256"] != hashlib.sha256(raw).hexdigest()
            or receipt["response_bytes_b64"] != base64.b64encode(raw).decode("ascii")):
        return False
    try:
        first, last = _date(receipt["from"]), _date(receipt["to"])
        decision = _cutoff(receipt["cutoff_utc"])
        if not (1 <= (first - decision).days <= (last - decision).days <= 7):
            return False
        return receipt["receipt_id"] == _seal(receipt)
    except (CaptureRefused, ValueError, TypeError, OverflowError):
        return False


def _receipt_bytes(*, ticker: str, start: str, end: str, observed: str, cutoff: str,
                   raw: bytes, packet: dict) -> bytes:
    receipt = {
        "schema": _SCHEMA,
        "source": _SOURCE,
        "ticker": ticker,
        "from": start,
        "to": end,
        "observed_utc": observed,
        "cutoff_utc": cutoff,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "response_bytes_b64": base64.b64encode(raw).decode("ascii"),
        "input_id": packet["input_id"],
    }
    receipt["receipt_id"] = _seal(receipt)
    return (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_new(directory: Path, raw: bytes, identity: tuple[int, int],
               monotonic, start_time: float) -> Path:
    """Write/fsync a temp file, then publish via atomic no-overwrite link."""
    nonce = uuid.uuid4().hex
    path = directory / f"earnings-calendar-{nonce}.json"
    temp = directory / f".earnings-calendar-{nonce}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = None
    created = False
    published = False
    failure = None
    try:
        fd = os.open(temp, flags, 0o600)
        created = True
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _elapsed(monotonic, start_time)
        if _private_identity(directory) != identity:
            failure = "PRIVATE_DIRECTORY_CHANGED"
        else:
            _elapsed(monotonic, start_time)
            os.link(temp, path)
            published = True
            _elapsed(monotonic, start_time)
    except FileExistsError:
        failure = "RECEIPT_EXISTS"
    except CaptureRefused as exc:
        failure = str(exc)
    except OSError:
        failure = failure or "RECEIPT_WRITE_FAILED"
    finally:
        if fd is not None:
            os.close(fd)
        if created:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                failure = failure or "RECEIPT_WRITE_FAILED"
        if failure and published:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    if failure:
        _refuse(failure)
    try:
        still_private = _private_identity(directory) == identity
    except CaptureRefused:
        still_private = False
    if not still_private:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        _refuse("PRIVATE_DIRECTORY_CHANGED")
    try:
        _elapsed(monotonic, start_time)
    except CaptureRefused as exc:
        failure = str(exc)
    if failure:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        _refuse(failure)
    return path


def capture_earnings_calendar(
    *, ticker: str, start: str, end: str, cutoff_utc: str,
    private_dir: Path, transport=None, clock=None, monotonic=None,
    api_key: str | None = None,
) -> dict:
    """Fetch once on explicit invocation; persist only a successful capture.

    Transport has the requests.get shape and must honor ``stream=True``.
    Observation time is sampled immediately after the full body arrives. The
    deadline is checked after each step; a blocking custom transport must honor
    the supplied connect/read timeouts itself.
    """
    if not isinstance(ticker, str) or not _TICKER.fullmatch(ticker):
        _refuse("TICKER_INVALID")
    first, last, decision = _date(start), _date(end), _cutoff(cutoff_utc)
    if not (1 <= (first - decision).days <= (last - decision).days <= 7):
        _refuse("DATE_RANGE_INVALID")
    key = api_keys.finnhub if api_key is None else api_key
    if not isinstance(key, str) or not key.strip() or "placeholder" in key.lower():
        _refuse("FINNHUB_KEY_ABSENT")
    try:
        directory = Path(private_dir)
    except (TypeError, ValueError):
        directory = None
    if directory is None:
        _refuse("PRIVATE_DIRECTORY_REQUIRED")
    identity = _private_identity(directory)
    if transport is None:
        import requests

        transport = requests.get
    clock = _utc_now if clock is None else clock
    monotonic = time.monotonic if monotonic is None else monotonic
    try:
        start_time = monotonic()
    except Exception:
        start_time = None
    if not isinstance(start_time, (float, int)) or not math.isfinite(start_time):
        _refuse("ELAPSED_CLOCK_INVALID")
    failed = False
    try:
        response = transport(
            _URL,
            params={"symbol": ticker, "from": start, "to": end, "token": key},
            timeout=(3, 5), stream=True,
        )
    except Exception:
        failed = True
    if failed:
        _refuse("FETCH_FAILED")
    try:
        _elapsed(monotonic, start_time)
        bad_metadata = False
        try:
            status = response.status_code
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        except Exception:
            bad_metadata = True
        if bad_metadata:
            _refuse("RESPONSE_INVALID")
        if status != 200:
            _refuse("HTTP_NON_200")
        if content_type != "application/json":
            _refuse("CONTENT_TYPE_INVALID")
        raw = _read_body(response, monotonic, start_time)
        observed = _observed(clock)
        _elapsed(monotonic, start_time)
    finally:
        try:
            response.close()
        except Exception:
            pass
    if not raw:
        _refuse("RESPONSE_BYTES_INVALID")
    _elapsed(monotonic, start_time)
    packet = build_saved_earnings_calendar_input(
        raw, ticker=ticker, observed_utc=observed, cutoff_utc=cutoff_utc,
    )
    _elapsed(monotonic, start_time)
    if packet["status"] != "EVIDENCE_ONLY":
        _refuse(packet["reason"])
    # Exact byte preservation and token exclusion cannot both hold if the
    # provider echoes the token. Refuse such a response before persistence.
    if _echoes_token(raw, key):
        _refuse("TOKEN_IN_RESPONSE")
    _elapsed(monotonic, start_time)
    if _private_identity(directory) != identity:
        _refuse("PRIVATE_DIRECTORY_CHANGED")
    receipt = _receipt_bytes(ticker=ticker, start=start, end=end,
                             observed=observed, cutoff=cutoff_utc, raw=raw, packet=packet)
    _elapsed(monotonic, start_time)
    path = _write_new(directory, receipt, identity, monotonic, start_time)
    return {"packet": packet, "receipt_path": path}


def evaluate_saved_capture(receipt: dict, response_bytes: bytes, *, cutoff_utc: str) -> dict:
    """Re-evaluate exact saved bytes with the original observation clock."""
    if not _valid_receipt(receipt, response_bytes):
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


def replay_earnings_calendar(receipt_path: Path, *, cutoff_utc: str) -> dict:
    """Replay after process exit from a bounded private on-disk envelope."""
    try:
        path = Path(receipt_path)
        if _FINAL_NAME.fullmatch(path.name) is None:
            _refuse("SAVED_CAPTURE_INVALID")
        identity = _private_identity(path.parent)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_RECEIPT_BYTES:
            _refuse("SAVED_CAPTURE_INVALID")
        with path.open("rb") as stream:
            encoded = stream.read(_MAX_RECEIPT_BYTES + 1)
        if len(encoded) > _MAX_RECEIPT_BYTES or _private_identity(path.parent) != identity:
            _refuse("SAVED_CAPTURE_INVALID")
        receipt = json.loads(encoded)
        raw = base64.b64decode(receipt["response_bytes_b64"], validate=True)
    except (OSError, ValueError, TypeError, KeyError):
        receipt = None
    if receipt is None:
        _refuse("SAVED_CAPTURE_INVALID")
    return evaluate_saved_capture(receipt, raw, cutoff_utc=cutoff_utc)
