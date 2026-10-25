"""Bounded staged OHLCV admission. No fetch, FX, adjustment, marker reset or operator."""
from __future__ import annotations

import hashlib
import io
import json
import math
import numbers
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
from filelock import Timeout

from backend.services import global_prices as GP


class AdmissionError(ValueError):
    def __init__(self, code, *, published=False):
        super().__init__(code)
        self.published = published


def _require(ok, code):
    if not ok:
        raise AdmissionError(code)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _owner(context, *, publishing=False):
    _require(isinstance(context, dict), "OWNER_CONTEXT_REQUIRED")
    _require(context.get("workflow") == "STAGED_PRICE_ADMISSION" and
             _text(context.get("owner_id")) and isinstance(context.get("operation_id"), str) and
             re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", context["operation_id"]), "INVALID_OWNER_CONTEXT")
    if publishing:
        _require(_text(context.get("cache_path")), "VERIFIED_OWNER_SOURCE_CLOSURE_REQUIRED")
        for key in ("legacy_writers_closed", "exclusive_owner_verified", "source_adoption_verified"):
            _require(context.get(key) is True, "VERIFIED_OWNER_SOURCE_CLOSURE_REQUIRED")
        for key in ("ownership_receipt_sha256", "source_adoption_sha256", "admission_plan_sha256"):
            _require(_hash(context.get(key)), "VERIFIED_OWNER_SOURCE_CLOSURE_REQUIRED")
    return {k: context[k] for k in ("workflow", "owner_id", "operation_id")}


def _aware(value):
    try:
        result = pd.Timestamp(value)
        _require(pd.notna(result) and result.tzinfo is not None, "AWARE_OBSERVATION_REQUIRED")
        return result.tz_convert("UTC")
    except (TypeError, ValueError, OverflowError) as exc:
        if isinstance(exc, AdmissionError):
            raise
        raise AdmissionError("AWARE_OBSERVATION_REQUIRED") from exc


def _day(value):
    # Session labels must already be local dates, never silently converted from UTC.
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            result = date.fromisoformat(value)
            _require(result.isoformat() == value, "EXACT_LOCAL_SESSION_DATE_REQUIRED")
            return result
        except ValueError as exc:
            raise AdmissionError("EXACT_LOCAL_SESSION_DATE_REQUIRED") from exc
    if isinstance(value, (datetime, pd.Timestamp)):
        stamp = pd.Timestamp(value)
        _require(pd.notna(stamp) and stamp.tzinfo is None and stamp == stamp.normalize(),
                 "EXACT_LOCAL_SESSION_DATE_REQUIRED")
        return stamp.date()
    raise AdmissionError("EXACT_LOCAL_SESSION_DATE_REQUIRED")


def _number(value):
    _require(isinstance(value, numbers.Real) and not isinstance(value, (bool,)) and
             not pd.api.types.is_bool_dtype(type(value)) and math.isfinite(float(value)), "INVALID_OHLCV")
    return int(value) if isinstance(value, numbers.Integral) else float(value)


def _ratio(value):
    value = _number(value)
    return (value, 1) if isinstance(value, int) else value.as_integer_ratio()


def _equal_number(a, b):
    try:
        return _ratio(a) == _ratio(b)
    except AdmissionError:
        return False


def _staged(frame):
    _require(isinstance(frame, pd.DataFrame) and 0 < len(frame) <= 256 and
             list(frame.columns) == GP.COLUMNS[:7], "EXPLICIT_STAGED_OHLCV_REQUIRED")
    rows = []
    for row in frame.itertuples(index=False, name=None):
        symbol = row[0]
        _require(isinstance(symbol, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9.^=-]{0,31}", symbol) and
                 symbol != "CASH", "EXACT_VENDOR_SYMBOL_REQUIRED")
        values = [_number(v) for v in row[2:]]
        opened, high, low, closed, volume = values
        _require(min(opened, high, low, closed) > 0 and volume >= 0, "INVALID_OHLCV")
        _require(low <= min(opened, closed) <= max(opened, closed) <= high, "INCONSISTENT_HIGH_LOW")
        rows.append([symbol, _day(row[1]).isoformat(), *values])
    _require(len({(r[0], r[1]) for r in rows}) == len(rows), "DUPLICATE_STAGED_KEYS")
    return rows


def staged_sha256(frame):
    """Pure logical hash of exact seven-column normalized OHLCV; does no I/O."""
    return _sha(_json(_staged(frame)))


def _inputs(staged, receipt, receipt_sha256, source_hashes, required_sessions, observed_at, owner_context):
    owner = _owner(owner_context)
    _require(isinstance(receipt, dict) and bool(receipt), "VERIFIED_RECEIPT_REQUIRED")
    _require(isinstance(required_sessions, dict) and bool(required_sessions), "EXACT_COMPLETED_TARGETS_REQUIRED")
    _require(_hash(receipt_sha256), "VERIFIED_RECEIPT_HASH_REQUIRED")
    try:
        _require(_sha(_json(receipt)) == receipt_sha256, "RECEIPT_HASH_MISMATCH")
    except (TypeError, ValueError, RecursionError) as exc:
        if isinstance(exc, AdmissionError):
            raise
        raise AdmissionError("INVALID_RECEIPT_JSON") from exc
    _require(receipt.get("schema") == "staged_ohlcv_receipt/1" and _text(receipt.get("receipt_id")) and
             _text(receipt.get("source")), "INVALID_RECEIPT")
    _require(isinstance(source_hashes, dict) and bool(source_hashes) and
             all(_text(k) and _hash(v) for k, v in source_hashes.items()) and
             receipt.get("source_hashes") == source_hashes, "SOURCE_HASH_BINDING_REQUIRED")
    _require(receipt.get("auto_adjust") is False and receipt.get("fx_converted") is False and
             receipt.get("dividend_adjusted") is False and receipt.get("price_basis") == "UNADJUSTED_LOCAL" and
             receipt.get("session_label_basis") == "EXPLICIT_LOCAL_SESSION_DATE", "UNADJUSTED_LOCAL_FLAGS_REQUIRED")
    rows = _staged(staged)
    _require(receipt.get("staged_sha256") == _sha(_json(rows)), "STAGED_HASH_MISMATCH")
    targets = {s: _day(d).isoformat() for s, d in required_sessions.items()}
    symbols = {r[0] for r in rows}
    _require(set(targets) == symbols and len(rows) == len(symbols) and
             all(targets[r[0]] == r[1] for r in rows), "INCOMPLETE_OR_MISMATCHED_TARGETS")
    now = _aware(observed_at)
    _require(_aware(receipt.get("observed_at")) == now, "OBSERVATION_BINDING_MISMATCH")
    retrieved = _aware(receipt.get("retrieved_at"))
    _require(retrieved <= now, "FUTURE_SOURCE_OBSERVATION")
    proof = receipt.get("completed_sessions")
    currencies = receipt.get("currency_by_symbol")
    _require(isinstance(proof, dict) and set(proof) == symbols and
             isinstance(currencies, dict) and set(currencies) == symbols and
             _hash(receipt.get("calendar_policy_sha256")), "COMPLETION_PROVENANCE_REQUIRED")
    for s in symbols:
        item = proof[s]
        _require(isinstance(item, dict) and item.get("symbol") == s and item.get("session") == targets[s] and
                 isinstance(item.get("calendar"), str) and re.fullmatch(r"[A-Z0-9]{4}", item["calendar"]) and
                 isinstance(currencies[s], str) and re.fullmatch(r"[A-Z]{3}", currencies[s]), "COMPLETION_PROVENANCE_REQUIRED")
        close, eligible = _aware(item.get("close_at")), _aware(item.get("eligible_at"))
        try:
            _require(_text(item.get("exchange_timezone")), "EXCHANGE_TIMEZONE_REQUIRED")
            zone = ZoneInfo(item["exchange_timezone"])
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            if isinstance(exc, AdmissionError):
                raise
            raise AdmissionError("EXCHANGE_TIMEZONE_REQUIRED") from exc
        _require(eligible == close + pd.Timedelta(minutes=90) and eligible <= retrieved <= now and
                 close.tz_convert(zone).date().isoformat() == targets[s] and
                 _day(targets[s]) <= now.date(), "SESSION_NOT_COMPLETED")
    return rows, targets, now, retrieved, owner


def _existing(frame):
    _require(isinstance(frame, pd.DataFrame) and list(frame.columns) == GP.COLUMNS and
             str(frame["date"].dtype) == "datetime64[ns]", "INCOMPATIBLE_PREIMAGE_SCHEMA")
    _require(not frame[["symbol", "date"]].duplicated().any(), "DUPLICATE_PREIMAGE_KEYS")
    for symbol, day in zip(frame["symbol"], frame["date"]):
        _require(isinstance(symbol, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9.^=-]{0,31}", symbol) and
                 _day(day).isoformat() == day.date().isoformat(), "INVALID_PREIMAGE_KEYS")
    ordered = frame.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)
    _require(frame.reset_index(drop=True).equals(ordered), "UNSORTED_PREIMAGE")


def _preserved(before, after):
    _existing(before)
    _existing(after)
    keys = set(zip(before["symbol"], before["date"]))
    retained = after.loc[[(s, d) in keys for s, d in zip(after["symbol"], after["date"])]].reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(before.reset_index(drop=True), retained, check_exact=True, check_dtype=True)
        _require(list(before.dtypes) == list(after.dtypes), "PREIMAGE_DTYPE_CHANGED")
    except AssertionError as exc:
        raise AdmissionError("PREIMAGE_ROWS_CHANGED") from exc


@dataclass(frozen=True)
class AdmissionPlan:
    _record: bytes = field(repr=False)
    _candidate: bytes = field(repr=False)

    @property
    def summary(self):
        try:
            result = json.loads(self._record)
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise AdmissionError("INVALID_PLAN_RECORD") from exc
        _require(isinstance(result, dict), "INVALID_PLAN_RECORD")
        return result

    @property
    def sha256(self):
        return _sha(self._record)


def plan_admission(staged=None, *, existing=None, preimage_sha256=None, receipt=None,
                   receipt_sha256=None, source_hashes=None, required_sessions=None,
                   observed_at=None, owner_context=None):
    """Pure private candidate in memory. Existing rows/metadata are never restated."""
    rows, targets, now, retrieved, owner = _inputs(staged, receipt, receipt_sha256, source_hashes,
                                                required_sessions, observed_at, owner_context)
    _require(_hash(preimage_sha256), "PREIMAGE_HASH_REQUIRED")
    _existing(existing)
    seen = {(s, d.date().isoformat()): i for i, (s, d) in enumerate(zip(existing["symbol"], existing["date"]))}
    additions, skipped = [], 0
    for row in rows:
        key = tuple(row[:2])
        if key in seen:
            old = existing.iloc[seen[key]]
            _require(all(_equal_number(old[col], value) for col, value in zip(GP.COLUMNS[2:7], row[2:])),
                     "CONFLICTING_EXISTING_ROW")
            skipped += 1
        else:
            additions.append([row[0], pd.Timestamp(row[1]), *row[2:], receipt["source"], retrieved.isoformat()])
    # Preserve exact normalized scalars through construction. Inference on a
    # mixed int/float column can round an integer before astype ever sees it.
    new = pd.DataFrame(additions, columns=GP.COLUMNS, dtype=object)
    if additions:
        try:
            new = new.astype(existing.dtypes.to_dict())
        except (ValueError, TypeError, OverflowError) as exc:
            raise AdmissionError("INCOMPATIBLE_NEW_ROW_DTYPES") from exc
        for index, col in enumerate(GP.COLUMNS[2:7], start=2):
            _require(all(_equal_number(row[index], value) for row, value in zip(additions, new[col])),
                     "LOSSY_NEW_ROW_CAST")
        for col in ("symbol", "date", "source", "pulled_utc"):
            index = GP.COLUMNS.index(col)
            _require([row[index] for row in additions] == new[col].tolist(), "LOSSY_NEW_ROW_CAST")
        candidate = pd.concat([existing, new], ignore_index=True).sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)
    else:
        candidate = existing.copy(deep=True).reset_index(drop=True)
    _preserved(existing, candidate)
    buffer = io.BytesIO()
    candidate.to_parquet(buffer, index=False)
    raw = buffer.getvalue()
    roundtrip = pd.read_parquet(io.BytesIO(raw))
    _preserved(existing, roundtrip)
    pd.testing.assert_frame_equal(candidate, roundtrip, check_exact=True, check_dtype=True)
    record = {"schema": "global_price_admission_plan/1", "owner": owner, "cache_path": None,
              "preimage_sha256": preimage_sha256, "candidate_sha256": _sha(raw),
              "before_rows": len(existing), "candidate_rows": len(candidate),
              "new_rows": len(additions), "identical_skipped": skipped,
              "new_keys": [[r[0], r[1].date().isoformat()] for r in additions],
              "receipt_sha256": receipt_sha256, "source_hashes": dict(source_hashes),
              "staged_sha256": receipt["staged_sha256"], "required_sessions": targets,
              "observed_at": now.isoformat(), "retrieved_at": retrieved.isoformat(),
              "source": receipt["source"], "currency_by_symbol": receipt["currency_by_symbol"],
              "calendar_policy_sha256": receipt["calendar_policy_sha256"],
              "completed_sessions": receipt["completed_sessions"],
              "basis": "UNADJUSTED_LOCAL; NO_FX; NEW_KEYS_ONLY",
              "preservation": "exact old rows/dtypes and stable sorted subsequence; parquet index=False"}
    return AdmissionPlan(_json(record), raw)


def prepare_admission(staged=None, *, cache_path=None, receipt=None, receipt_sha256=None,
                      source_hashes=None, required_sessions=None, observed_at=None, owner_context=None):
    """Read one explicit preimage only after all staged authority inputs validate."""
    _inputs(staged, receipt, receipt_sha256, source_hashes, required_sessions, observed_at, owner_context)
    _require(cache_path is not None, "EXPLICIT_CACHE_PATH_REQUIRED")
    path = Path(cache_path)
    try:
        raw = path.read_bytes()
        existing = pd.read_parquet(io.BytesIO(raw))
    except (OSError, ValueError) as exc:
        raise AdmissionError("PREIMAGE_UNAVAILABLE") from exc
    plan = plan_admission(staged, existing=existing, preimage_sha256=_sha(raw), receipt=receipt,
                           receipt_sha256=receipt_sha256, source_hashes=source_hashes,
                           required_sessions=required_sessions, observed_at=observed_at, owner_context=owner_context)
    record = plan.summary
    record["cache_path"] = str(path.resolve())
    return AdmissionPlan(_json(record), plan._candidate)


def _write(handle, raw):
    handle.write(raw)
    handle.flush()
    os.fsync(handle.fileno())


def publish_admission(plan=None, *, cache_path=None, audit_dir=None, expected_preimage_sha256=None,
                      owner_context=None, lock_timeout=60):
    """Explicit publish entry: attested owner/source closure PLUS cooperative lock.

    Closure must be independently verified by the coordinator. This lock cannot
    protect against legacy already-imported GP writers that do not honor it.
    """
    owner = _owner(owner_context, publishing=True)
    _require(isinstance(plan, AdmissionPlan), "ADMISSION_PLAN_REQUIRED")
    record = plan.summary
    _require(record.get("schema") == "global_price_admission_plan/1" and record.get("owner") == owner and
             owner_context["admission_plan_sha256"] == plan.sha256 and
             _hash(expected_preimage_sha256) and record.get("preimage_sha256") == expected_preimage_sha256 and
             _sha(plan._candidate) == record.get("candidate_sha256"), "PLAN_BINDING_MISMATCH")
    _require(cache_path is not None and audit_dir is not None, "EXPLICIT_PUBLISH_PATHS_REQUIRED")
    path = Path(cache_path)
    _require(record.get("cache_path") == str(path.resolve()) == owner_context["cache_path"], "CACHE_OWNER_SCOPE_MISMATCH")
    _require(not path.is_symlink() and path.is_file(), "REGULAR_PREIMAGE_REQUIRED")
    try:
        with GP.cache_lock(path, timeout=lock_timeout):
            return _publish_locked(plan, record, path, Path(audit_dir), owner_context)
    except Timeout as exc:
        raise AdmissionError("CACHE_LOCK_TIMEOUT") from exc


def _publish_locked(plan, record, path, audit_dir, owner_context):
    raw = path.read_bytes()
    _require(_sha(raw) == record["preimage_sha256"], "PREIMAGE_CHANGED")
    old = pd.read_parquet(io.BytesIO(raw))
    candidate = pd.read_parquet(io.BytesIO(plan._candidate))
    _preserved(old, candidate)
    _require(len(old) == record["before_rows"] and len(candidate) == record["candidate_rows"] and
             len(candidate) - len(old) == record["new_rows"], "PLAN_ROW_COUNT_MISMATCH")
    old_keys = set(zip(old["symbol"], old["date"]))
    new_keys = [[s, d.date().isoformat()] for s, d in zip(candidate["symbol"], candidate["date"]) if (s, d) not in old_keys]
    _require(sorted(new_keys) == sorted(record["new_keys"]), "PLAN_KEY_MISMATCH")
    if not record["new_rows"]:
        return {"status": "NO_CHANGE", "cache_sha256": _sha(raw), "plan": record}
    audit_dir.mkdir(parents=True, exist_ok=True)
    stem = "admission_" + record["owner"]["operation_id"]
    receipt_path = audit_dir / (stem + ".json")
    backup_path = audit_dir / (stem + ".before.parquet")
    _require(not backup_path.exists(), "EXCLUSIVE_BACKUP_EXISTS")
    try:
        audit = receipt_path.open("xb")
    except FileExistsError as exc:
        raise AdmissionError("EXCLUSIVE_AUDIT_EXISTS") from exc
    temporary = None
    published = False
    result = {"schema": "global_price_admission_audit/1", "status": "PREPARED", "plan": record,
              "owner_closure": dict(owner_context), "cache": str(path.resolve()),
              "predecessor_copy": str(backup_path.resolve()), "audit_receipt": str(receipt_path.resolve())}
    try:
        _write(audit, _json(result))
        with backup_path.open("xb") as backup:
            _write(backup, raw)
        _require(_sha(backup_path.read_bytes()) == record["preimage_sha256"], "BACKUP_HASH_MISMATCH")
        fd, temporary = tempfile.mkstemp(prefix=".price-admission-", suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "wb") as handle:
            _write(handle, plan._candidate)
        _require(_sha(Path(temporary).read_bytes()) == record["candidate_sha256"], "CANDIDATE_HASH_MISMATCH")
        _require(_sha(path.read_bytes()) == record["preimage_sha256"], "PREIMAGE_CHANGED")
        os.replace(temporary, path)
        temporary = None
        published = True
        _require(_sha(path.read_bytes()) == record["candidate_sha256"], "PUBLISHED_HASH_MISMATCH")
        result.update(status="PUBLISHED", cache_sha256=record["candidate_sha256"])
        _update_audit(audit, result)
        return result
    except Exception as exc:
        result.update(status="PUBLISHED_UNVERIFIED" if published else "REFUSED", error=type(exc).__name__)
        code = "PUBLISHED_UNVERIFIED" if published else str(exc)
        try:
            _update_audit(audit, result)
        except OSError as audit_exc:
            code += ";AUDIT_FINALIZATION_FAILED:" + type(audit_exc).__name__
        raise AdmissionError(code, published=published) from exc
    finally:
        audit.close()
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def _update_audit(handle, result):
    handle.seek(0)
    handle.write(_json(result))
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())
