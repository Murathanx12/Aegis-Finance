"""Explicit, injected price-coverage receipts. No acquisition defaults or promotion.

This module never calls the production funnel, provider SDKs, or caches. Bounds
count callback invocations/batches/requested symbols, not HTTP, spend, time or RSS.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Callable


@dataclass(frozen=True)
class Limits:
    batch_size: int
    max_logical_calls: int
    max_batches: int
    max_symbols: int


class CoverageRefused(ValueError):
    """No full artifact was produced; report retains every supplied ticker."""

    def __init__(self, report: dict):
        self.report = deepcopy(report)
        super().__init__("price coverage refused: " + "; ".join(report["errors"]))


class _Invalid(ValueError):
    """Controlled reason safe to include in a refusal report."""


@dataclass(frozen=True)
class PriceCoverage:
    """Immutable canonical receipt bytes; report returns a detached copy."""

    payload: bytes

    @property
    def report(self) -> dict:
        return json.loads(self.payload)


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def membership_sha256(tickers: list[str] | tuple[str, ...]) -> str:
    """SHA-256 of sorted JSON ticker list, ASCII, compact separators; no dedup."""
    return hashlib.sha256(_encode(sorted(tickers))).hexdigest()


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _date(value: str) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise _Invalid("invalid_date_window")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise _Invalid("invalid_date_window")
    return parsed


def _provenance(value: dict) -> dict:
    source, fetched = value["source"], value["fetched_at"]
    if not isinstance(source, str) or not source.strip() or not isinstance(fetched, str):
        raise _Invalid("invalid_provenance")
    stamp = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise _Invalid("fetched_at_requires_timezone")
    if stamp > datetime.now(timezone.utc):
        raise _Invalid("fetched_at_in_future")
    cache = value["cache_provenance"]
    if (cache["mode"] not in ("injected", "cache", "uncached")
            or not isinstance(cache["identity"], str) or not cache["identity"].strip()
            or not isinstance(cache["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", cache["sha256"])):
        raise _Invalid("invalid_cache_provenance")
    return json.loads(_encode({"source": source, "fetched_at": fetched,
                              "cache_provenance": cache}))


def _validate_universe(u: dict) -> None:
    tickers = u["tickers"]
    if (not isinstance(tickers, list) or not tickers
            or any(not isinstance(t, str) or not re.fullmatch(r"[A-Z0-9-]{1,5}", t)
                   or not t.replace("-", "") for t in tickers)):
        raise _Invalid("invalid_tickers")
    if len(set(tickers)) != len(tickers):
        raise _Invalid("duplicate_universe_symbols")
    if not _positive_int(u["n"]) or u["n"] != len(tickers):
        raise _Invalid("universe_count_mismatch")
    if u["membership_sha256"] != membership_sha256(tickers):
        raise _Invalid("universe_membership_hash_mismatch")
    if u["truncated"] is not False:
        raise _Invalid("truncated_universe")
    exclusions = u["exclusions"]
    if (not isinstance(exclusions, dict) or not exclusions
            or any(not isinstance(k, str) or not k or type(v) is not int or v < 0
                   for k, v in exclusions.items())):
        raise _Invalid("invalid_exclusions")
    _provenance(u)


def _refuse(report: dict, reason: str) -> None:
    _accounting(report)
    report["full_coverage"] = False
    report["errors"].append(reason)
    raise CoverageRefused(report)


def _accounting(report: dict) -> None:
    counts = dict(Counter(row["status"] for row in report["outcomes"]))
    report["outcome_counts"] = counts
    report["screened"] = report.get("usage", {}).get("symbols", 0)
    report["accounting_complete"] = bool(report["outcomes"]) and not counts.get("not_attempted")


def _frame(frame: object, start: date, end: date, min_rows: int) -> dict:
    import numpy as np
    import pandas as pd
    from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype

    if (not isinstance(frame, pd.DataFrame) or frame.columns.has_duplicates
            or set(frame.columns) != {"Close", "Volume"}):
        return {"status": "invalid_schema"}
    if frame.empty:
        return {"status": "missing", "reason": "empty_frame"}
    idx = frame.index
    if (not isinstance(idx, pd.DatetimeIndex) or idx.hasnans or not idx.is_unique
            or not idx.is_monotonic_increasing or not idx.equals(idx.normalize())):
        return {"status": "invalid_date"}
    dates = [d.date() for d in idx]
    if (len(set(dates)) != len(dates) or dates[0] != start or dates[-1] != end
            or len(frame) < min_rows):
        return {"status": "invalid_date", "reason": "window_or_min_rows"}
    for col in ("Close", "Volume"):
        dtype = frame[col].dtype
        if not is_numeric_dtype(dtype) or is_bool_dtype(dtype) or is_complex_dtype(dtype):
            return {"status": "invalid_schema", "reason": col}
    values = frame[["Close", "Volume"]].to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all():
        return {"status": "nonfinite"}
    close, volume = values[:, 0], values[:, 1]
    if (close <= 0).any():
        return {"status": "invalid_price"}
    if (volume < 0).any() or (volume % 1 != 0).any():
        return {"status": "invalid_volume"}
    bars = [[d.isoformat(), float(c), float(v)] for d, c, v in zip(dates, close, volume)]
    return {"status": "valid", "schema": ["date", "Close", "Volume"],
            "rows": len(bars), "first_date": dates[0].isoformat(),
            "last_date": dates[-1].isoformat(), "last_close": float(close[-1]),
            "last_volume": float(volume[-1]),
            "prices_sha256": hashlib.sha256(_encode(bars)).hexdigest()}


def collect_price_coverage(*, universe: dict, provider: Callable, limits: Limits,
                           start_date: str, end_date: str, min_rows: int) -> PriceCoverage:
    """Validate a pinned domain and invoke the supplied callback once per batch.

    Callback(batch_id, ticker_tuple) returns provenance plus `prices`, a list of
    (ticker, daily Close/Volume DataFrame) pairs. Missing/duplicate/unexpected
    symbols or any invalid batch/frame refuse full coverage after all planned
    batches are accounted for. Exceptions are recorded by type, without secrets.
    """
    u = deepcopy(universe)
    tickers = u.get("tickers", []) if isinstance(u, dict) else []
    outcomes = [{"ticker": t, "ordinal": i, "status": "not_attempted", "batch_ids": []}
                for i, t in enumerate(tickers if isinstance(tickers, list) else [])]
    report = {"artifact_kind": "admitted_universe_price_coverage_v1",
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "full_coverage": False, "universe": u, "outcomes": outcomes,
              "accounting_complete": False, "usable_price_coverage_complete": False,
              "promotion_eligible": False,
              "downstream": {"stage3_enrichment": "not_evaluated", "ranking": "not_evaluated"},
              "batches": [], "errors": [],
              "usage": {"logical_calls": 0, "batches": 0, "symbols": 0},
              "claims": {"ranking": False, "eligibility": False,
                         "ic_acceptance": False, "parent_completion": False}}
    try:
        _validate_universe(u)
        _encode(u)  # refuse unserializable/nonfinite provenance before callbacks
        start, end = _date(start_date), _date(end_date)
        if (start > end or not _positive_int(min_rows)
                or min_rows > (end - start).days + 1 or not callable(provider)):
            raise _Invalid("invalid_window_or_provider")
        if not isinstance(limits, Limits) or not all(_positive_int(v) for v in asdict(limits).values()):
            raise _Invalid("invalid_limits")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        reason = str(exc) if isinstance(exc, _Invalid) else type(exc).__name__
        _refuse(report, "preflight_validation:" + reason)
    report["limits"] = asdict(limits)
    report["window"] = {"start_date": start_date, "end_date": end_date, "min_rows": min_rows}
    n_batches = (len(tickers) + limits.batch_size - 1) // limits.batch_size
    if (len(tickers) > limits.max_symbols or n_batches > limits.max_batches
            or n_batches > limits.max_logical_calls):
        _refuse(report, "full_domain_exceeds_logical_limits")

    for offset in range(0, len(tickers), limits.batch_size):
        chunk = tuple(tickers[offset:offset + limits.batch_size])
        batch_id = f"B{len(report['batches']) + 1:06d}"
        rows = outcomes[offset:offset + len(chunk)]
        for row in rows:
            row["batch_ids"].append(batch_id)
        batch = {"batch_id": batch_id, "tickers": list(chunk)}
        report["batches"].append(batch)
        report["usage"]["logical_calls"] += 1
        report["usage"]["batches"] += 1
        report["usage"]["symbols"] += len(chunk)
        try:
            response = provider(batch_id, chunk)
        except Exception as exc:  # explicit failure; no retry or raw provider text
            batch["error"] = "provider_exception:" + type(exc).__name__
        else:
            try:
                batch["provenance"] = _provenance(response)
                fetched = datetime.fromisoformat(response["fetched_at"].replace("Z", "+00:00"))
                if fetched.date() < end:
                    raise _Invalid("prices_postdate_fetch")
                pairs = response["prices"]
                if (not isinstance(pairs, list)
                        or any(not isinstance(p, (list, tuple)) or len(p) != 2
                               or not isinstance(p[0], str) for p in pairs)):
                    raise _Invalid("invalid_price_pairs")
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                reason = str(exc) if isinstance(exc, _Invalid) else type(exc).__name__
                batch["error"] = "invalid_response_or_provenance:" + reason
        if "error" in batch:
            report["errors"].append(batch_id + ":" + batch["error"])
            for row in rows:
                row.update(status="error", reason=batch["error"])
            continue
        counts = Counter(t for t, _ in pairs)
        batch["returned_symbols"] = [t for t, _ in pairs]
        unexpected = sorted(set(counts) - set(chunk))
        if unexpected:
            batch["unexpected_symbols"] = unexpected
            report["errors"].append(batch_id + ":unexpected_symbols")
        frames = dict(pairs)
        for row in rows:
            t = row["ticker"]
            if not counts[t]:
                row.update(status="missing", reason="symbol_absent")
            elif counts[t] != 1:
                row.update(status="error", reason="duplicate_symbol")
            else:
                try:
                    row.update(_frame(frames[t], start, end, min_rows))
                except Exception as exc:  # malformed injected frame remains accounted for
                    row.update(status="error", reason="frame_validation:" + type(exc).__name__)
            if row["status"] != "valid":
                report["errors"].append(batch_id + ":" + t + ":" + row["status"])
    _accounting(report)
    if report["errors"]:
        _refuse(report, "unresolved_price_coverage")
    report["usable_price_coverage_complete"] = True
    report["full_coverage"] = True
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    return PriceCoverage(_encode(report))


def _staging_directory(staging_dir: Path) -> Path:
    """Resolve and reject protected roots AND aliases before any creation."""
    raw = Path(staging_dir).absolute()
    for component in (raw, *raw.parents):
        if component.is_symlink() or component.is_junction():
            raise _Invalid("staging_alias_refused")
    resolved = raw.resolve(strict=True)
    blocked = {"data", "cache", ".cache", "history", "funnel_cache", "funnel_history",
               "production", "prod", ".git"}
    if (raw.name != "funnel-price-staging" or not resolved.is_dir()
            or blocked.intersection(p.lower() for p in (*raw.parts, *resolved.parts))):
        raise _Invalid("not_a_separate_staging_directory")
    roots = {Path(__file__).resolve().parents[2]}
    if os.getenv("AEGIS_REPO_ROOT"):
        roots.add(Path(os.environ["AEGIS_REPO_ROOT"]).resolve())
    protected = [root / "backend" for root in roots]
    if os.getenv("AEGIS_DATA_DIR"):
        protected.append(Path(os.environ["AEGIS_DATA_DIR"]).resolve())
    if any(resolved == p or p in resolved.parents for p in protected):
        raise _Invalid("protected_destination")
    return resolved


def _validate_receipt(report: dict) -> None:
    """Recheck coverage accounting at the explicit write boundary."""
    u = report["universe"]
    _validate_universe(u)
    limits = Limits(**report["limits"])
    window = report["window"]
    start, end = _date(window["start_date"]), _date(window["end_date"])
    minimum = window["min_rows"]
    if (not all(_positive_int(v) for v in asdict(limits).values())
            or start > end or not _positive_int(minimum)
            or report["artifact_kind"] != "admitted_universe_price_coverage_v1"
            or report["full_coverage"] is not True or report["errors"]
            or report["accounting_complete"] is not True
            or report["usable_price_coverage_complete"] is not True
            or report["promotion_eligible"] is not False
            or report["downstream"] != {"stage3_enrichment": "not_evaluated", "ranking": "not_evaluated"}
            or "candidates" in report
            or report["claims"] != {"ranking": False, "eligibility": False,
                                    "ic_acceptance": False, "parent_completion": False}):
        raise _Invalid("invalid_coverage_receipt")
    tickers = u["tickers"]
    chunks = [tickers[i:i + limits.batch_size] for i in range(0, len(tickers), limits.batch_size)]
    usage = {"logical_calls": len(chunks), "batches": len(chunks), "symbols": len(tickers)}
    if (report["usage"] != usage or report["screened"] != len(tickers)
            or report["outcome_counts"] != {"valid": len(tickers)}
            or len(chunks) > limits.max_logical_calls
            or len(chunks) > limits.max_batches or len(tickers) > limits.max_symbols
            or len(report["batches"]) != len(chunks)
            or len(report["outcomes"]) != len(tickers)):
        raise _Invalid("invalid_coverage_accounting")
    for i, (chunk, batch) in enumerate(zip(chunks, report["batches"]), 1):
        if (batch["batch_id"] != f"B{i:06d}" or batch["tickers"] != chunk
                or Counter(batch["returned_symbols"]) != Counter(chunk) or "error" in batch):
            raise _Invalid("invalid_batch_accounting")
        _provenance(batch["provenance"])
    for i, (ticker, row) in enumerate(zip(tickers, report["outcomes"])):
        if (row["ticker"] != ticker or row["ordinal"] != i or row["status"] != "valid"
                or row["batch_ids"] != [f"B{i // limits.batch_size + 1:06d}"]
                or row["schema"] != ["date", "Close", "Volume"]
                or not _positive_int(row["rows"]) or row["rows"] < minimum
                or row["rows"] > (end - start).days + 1
                or row["first_date"] != window["start_date"]
                or row["last_date"] != window["end_date"]
                or not isinstance(row["prices_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["prices_sha256"])
                or type(row["last_close"]) not in (float, int)
                or type(row["last_volume"]) not in (float, int)
                or not math.isfinite(row["last_close"]) or row["last_close"] <= 0
                or not math.isfinite(row["last_volume"]) or row["last_volume"] < 0
                or row["last_volume"] % 1 != 0):
            raise _Invalid("invalid_symbol_accounting")


def write_price_coverage(receipt: PriceCoverage, *, staging_dir: Path) -> Path:
    """Exclusive new receipt in an existing explicitly named staging directory.

    No overwrite, mkdir, history, cache write, candidate snapshot or promotion.
    Immutability is this API's create-only contract, not an OS tamper-proof seal.
    """
    if not isinstance(receipt, PriceCoverage):
        report = receipt if isinstance(receipt, dict) else {"outcomes": []}
        report = {**deepcopy(report), "errors": [], "full_coverage": False}
        _refuse(report, "writer_requires_successful_price_coverage_receipt")
    report = receipt.report
    try:
        _validate_receipt(report)
        directory = _staging_directory(staging_dir)
        digest = hashlib.sha256(receipt.payload).hexdigest()
        destination = directory / f"price-coverage-{digest}.json"
        with destination.open("xb") as stream:
            try:
                stream.write(receipt.payload)
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                stream.close()
                destination.unlink()  # only this invocation's exclusive new file
                raise
    except (ValueError, TypeError, KeyError, OSError) as exc:
        reason = str(exc) if isinstance(exc, _Invalid) else type(exc).__name__
        _refuse(report, "staging_write_refused:" + reason)
    return destination
