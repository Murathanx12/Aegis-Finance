"""Private, pure C02 artifact verification and original eligibility-input export.

No paths are opened, no providers are called, and no funnel stage is executed.
The explicit manifest is a caller-approved trust anchor, not an authenticity seal.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import re

from backend.services import funnel_staging as S


class PriceBridgeRefused(ValueError):
    """Sanitized reason plus full-domain diagnostics; never a complete export."""

    def __init__(self, report: dict):
        self.report = deepcopy(report)
        super().__init__("verified price bridge refused: " + ";".join(report["errors"]))


@dataclass(frozen=True)
class VerifiedPriceStage:
    payload: bytes

    @property
    def report(self) -> dict:
        return json.loads(self.payload)


class _Invalid(ValueError):
    """Only controlled reasons may appear in diagnostic receipts."""


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise _Invalid(reason)


def _date(value: str) -> date:
    result = date.fromisoformat(value)
    _require(result.isoformat() == value, "noncanonical_date")
    return result


def _pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def _decode(data: bytes) -> object:
    # Bound nesting before the recursive JSON parser; ignore delimiters in strings.
    depth, quoted, escaped = 0, False, False
    for byte in data:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            _require(depth <= 64, "json_nesting_limit")
        elif byte in (93, 125):
            depth -= 1
            _require(depth >= 0, "malformed_json")

    def invalid(value):
        raise ValueError("nonfinite_json")
    return json.loads(data, object_pairs_hook=_pairs, parse_constant=invalid)


def validate_manifest(manifest: dict) -> None:
    """Missing-input guard: explicit domain, calendar, pins and size limits; no I/O."""
    try:
        _decode(_encode(manifest))
        _require(manifest["schema"] == "verified_price_manifest_v1", "manifest_schema")
        S._validate_universe(manifest["universe"])
        sessions = manifest["required_sessions"]
        _require(isinstance(sessions, list) and bool(sessions), "sessions_required")
        _require([_date(s).isoformat() for s in sessions] == sorted(set(sessions)),
                 "sessions_order_or_duplicates")
        calendar = manifest["calendar_provenance"]
        _require(isinstance(calendar["source"], str) and bool(calendar["source"].strip())
                 and bool(re.fullmatch("[0-9a-f]{64}", calendar["sha256"])), "calendar_provenance")
        pins = manifest["source_pins"]
        _require(isinstance(pins, dict) and bool(pins)
                 and all(isinstance(k, str) and isinstance(v, str)
                         and re.fullmatch("[0-9a-f]{64}", v) for k, v in pins.items()),
                 "source_pins_required")
        limits = manifest["limits"]
        _require(set(limits) == {"max_input_bytes", "max_artifacts", "max_rows", "max_symbols"}
                 and all(type(v) is int and v > 0 for v in limits.values()), "size_limits")
        _require(len(sessions) <= limits["max_rows"]
                 and manifest["universe"]["n"] <= limits["max_symbols"], "manifest_size_cap")
        descriptor = manifest["acquisition"]
        _require(isinstance(descriptor["file"], str) and bool(descriptor["file"])
                 and bool(re.fullmatch("[0-9a-f]{64}", descriptor["sha256"])), "acquisition_pin")
        _encode(manifest)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise PriceBridgeRefused({"errors": ["invalid_or_missing_manifest"],
                                  "accounting_complete": False, "complete": False}) from None


def _history(raw: dict, max_rows: int):
    import pandas as pd

    _require(raw["adjustment"] == "unadjusted; auto_adjust=False, back_adjust=False, repair=False",
             "adjustment_basis")
    columns, rows, labels = raw["columns"], raw["data"], raw["original_session_dates"]
    _require(isinstance(columns, list) and all(isinstance(c, str) for c in columns)
             and len(set(columns)) == len(columns) and {"Close", "Volume"} <= set(columns),
             "raw_columns")
    _require(isinstance(rows, list) and 0 < len(rows) <= max_rows
             and len(rows) == len(labels) == len(raw["index"])
             and all(isinstance(r, list) and len(r) == len(columns) for r in rows), "raw_rows")
    zone = raw["index_timezone"]
    if zone is None:
        idx = pd.DatetimeIndex(raw["index"])
        _require(idx.tz is None, "timezone_missing")
    else:
        _require(isinstance(zone, str) and bool(zone), "timezone_invalid")
        _require(all(pd.Timestamp(s).tzinfo is not None for s in raw["index"]), "index_offset_missing")
        idx = pd.to_datetime(raw["index"], utc=True).tz_convert(zone)
    _require([t.isoformat() for t in idx] == raw["index"]
             and [t.date().isoformat() for t in idx] == labels, "original_session_label_mismatch")
    cv_positions = [columns.index(c) for c in ("Close", "Volume")]
    _require(all(type(r[i]) in (int, float) for r in rows for i in cv_positions), "cv_numeric_required")
    frame = pd.DataFrame(rows, columns=columns, index=idx)[["Close", "Volume"]]
    frame.index = frame.index.tz_localize(None)
    result = S._frame(frame, _date(labels[0]), _date(labels[-1]), 1)
    _require(result["status"] == "valid", "invalid_raw_close_volume")
    return frame, result


def stage_verified_prices(*, manifest: dict, artifacts: dict[str, bytes]) -> VerifiedPriceStage:
    """Verify one full_us acquisition and export original, unranked CV/raw inputs.

    Size limits bound supplied bytes/artifact/row counts, not wall time or RSS.
    Missing sessions and short histories refuse, rather than excluding symbols.
    """
    validate_manifest(manifest)
    m = deepcopy(manifest)
    names = m["universe"]["tickers"]
    report = {"artifact_kind": "verified_funnel_price_inputs_v1", "universe": m["universe"],
              "manifest_sha256": _sha(_encode(m)), "source_pins": m["source_pins"],
              "calendar_provenance": m["calendar_provenance"],
              "required_sessions": m["required_sessions"], "errors": [], "complete": False,
              "accounting_complete": False, "usable_price_coverage_complete": False,
              "declared_history_coverage_complete": False, "eligibility": "not_evaluated",
              "enrichment": "not_evaluated", "ranking": "not_evaluated",
              "promotion_eligible": False, "outcomes": [], "inputs": {}}
    try:
        limits = m["limits"]
        _require(isinstance(artifacts, dict) and 0 < len(artifacts) <= limits["max_artifacts"]
                 and all(isinstance(k, str) and type(v) is bytes for k, v in artifacts.items()),
                 "artifact_map_required")
        _require(sum(len(v) for v in artifacts.values()) <= limits["max_input_bytes"], "input_byte_cap")
        report["input_artifact_sha256s"] = {k: _sha(v) for k, v in artifacts.items()}
        seen = set()

        def load(descriptor):
            name = descriptor["file"]
            data = artifacts[name]
            _require(_sha(data) == descriptor["sha256"], "artifact_hash_mismatch")
            if "bytes" in descriptor:
                _require(len(data) == descriptor["bytes"], "artifact_byte_count_mismatch")
            _require(name not in seen, "duplicate_artifact_reference")
            seen.add(name)
            return _decode(data)

        acq = load(m["acquisition"])
        _require(acq["mode"] == "full_us" and acq["source_pins"] == m["source_pins"]
                 and acq["universe"] == m["universe"], "full_domain_or_source_mismatch")
        _require(acq["promotion_eligible"] is False, "unexpected_promotion_claim")
        report["acquisition_complete"] = acq["status"] == "COMPLETE" and acq["transport_failure"] is None
        raw_universe = load(acq["raw_universe"])
        u = m["universe"]
        _require(isinstance(raw_universe, list) and len(raw_universe) == u["raw_rows_count"]
                 and acq["raw_universe"]["sha256"] == u["raw_rows_sha256"]
                 == u["cache_provenance"]["sha256"], "raw_universe_lineage")
        # Reuse the reviewed deterministic admission filter, never its provider path.
        from backend.services.funnel_acquisition import _universe
        rebuilt = _universe(raw_universe, u["extras_lineage"]["requested"],
                            u["raw_rows_sha256"], u["fetched_at"],
                            {"max_raw_rows": limits["max_rows"], "max_symbols": limits["max_symbols"],
                             "max_transport_attempts": 1 + limits["max_symbols"]})
        _require(rebuilt == u, "raw_universe_admission_mismatch")
        hs, he = (_date(acq["history_window"][key]) for key in ("history_start", "history_end"))
        sessions = m["required_sessions"]
        _require(hs <= _date(sessions[0]) <= _date(sessions[-1]) <= he, "history_window_mismatch")
        cw = acq["coverage_window"]
        report["history_window"] = acq["history_window"]
        report["coverage_window"] = cw
        _require(cw["coverage_end"] == sessions[-1], "latest_session_mismatch")
        raw_prices = {}
        raw_locations = {}
        plan_seen = False
        for desc in acq["artifacts"]:
            content = load(desc)
            if desc["file"] == "plan.json":
                plan_seen = True
                _require(content["mode"] == "full_us" and content["symbols"] == names
                         and content["history_window"] == [hs.isoformat(), he.isoformat()]
                         and content["coverage_window"] == [cw["coverage_start"], cw["coverage_end"]],
                         "plan_mismatch")
            else:
                _require(bool(re.fullmatch(r"history-B[0-9]{6}\.json", desc["file"]))
                         and isinstance(content, dict), "unexpected_history_artifact")
                _require(not set(content) & set(raw_prices), "duplicate_history_symbol")
                raw_prices.update(content)
                raw_locations.update({s: desc["file"] for s in content})
        _require(plan_seen, "missing_acquisition_plan")
        _require(set(raw_prices) <= set(names), "unexpected_history_symbol")
        coverage = None
        if "price_coverage" in acq:
            coverage = load(acq["price_coverage"])
            S._validate_receipt(coverage)
            _require(coverage["universe"] == u
                     and coverage["window"] == {"start_date": cw["coverage_start"],
                                                "end_date": cw["coverage_end"],
                                                "min_rows": cw["coverage_min_rows"]}, "coverage_mismatch")
            batches = {b["batch_id"]: b for b in coverage["batches"]}
            by_ticker = {row["ticker"]: row for row in coverage["outcomes"]}
        _require(seen == set(artifacts), "unreferenced_artifacts")
        _require(set(acq["symbol_outcomes"]) == set(names), "symbol_accounting_mismatch")
        from backend.services.opportunity_funnel import MIN_HISTORY_DAYS
        report["eligibility_min_history_rows"] = MIN_HISTORY_DAYS
        for symbol in names:
            row = {"ticker": symbol, "status": "unknown", "reasons": []}
            report["outcomes"].append(row)
            try:
                _require(symbol in raw_prices, "missing_raw_history")
                _require(acq["symbol_outcomes"][symbol]["status"] == "history_returned",
                         "acquisition_symbol_failed")
                frame, summary = _history(raw_prices[symbol], limits["max_rows"])
                row.update(observed_rows=len(frame), first_date=summary["first_date"],
                           last_date=summary["last_date"], usable_price_coverage=False)
                if coverage is not None:
                    selected = frame.loc[cw["coverage_start"]:cw["coverage_end"]]
                    check = S._frame(selected, _date(cw["coverage_start"]),
                                     _date(cw["coverage_end"]), cw["coverage_min_rows"])
                    receipt_row = by_ticker[symbol]
                    provenance = batches[receipt_row["batch_ids"][0]]["provenance"]
                    _require(check["status"] == "valid" and all(
                        check[k] == receipt_row[k] for k in check), "coverage_raw_price_mismatch")
                    _require(provenance["cache_provenance"]["identity"] == raw_locations[symbol]
                             and provenance["cache_provenance"]["sha256"]
                             == report["input_artifact_sha256s"][raw_locations[symbol]],
                             "coverage_raw_lineage")
                    row["usable_price_coverage"] = True
                else:
                    row["reasons"].append("missing_verified_price_coverage")
                if raw_prices[symbol]["original_session_dates"] != sessions:
                    row["reasons"].append("missing_or_unexpected_history_sessions")
                if len(frame) < MIN_HISTORY_DAYS:
                    row["reasons"].append("short_history_unknown_not_ineligible")
                if not row["reasons"]:
                    row["status"] = "verified_inputs"
                report["inputs"][symbol] = {
                    "raw_artifact": raw_locations[symbol],
                    "raw_artifact_sha256": report["input_artifact_sha256s"][raw_locations[symbol]],
                    "raw_history": raw_prices[symbol],
                    "close_volume": {"dates": raw_prices[symbol]["original_session_dates"],
                                     "Close": frame["Close"].tolist(), "Volume": frame["Volume"].tolist()},
                    "missing_raw_ohlcv_fields": sorted(
                        {"Open", "High", "Low", "Close", "Volume"} - set(raw_prices[symbol]["columns"])),
                    "ohlcv_grade_admission": "not_evaluated"}
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
                row["reasons"].append(str(exc) if isinstance(exc, _Invalid)
                                      else "invalid_or_unverified_symbol_inputs")
        report["accounting_complete"] = True
        report["usable_price_coverage_complete"] = all(
            r.get("usable_price_coverage") is True for r in report["outcomes"])
        report["declared_history_coverage_complete"] = all(
            r["status"] == "verified_inputs" for r in report["outcomes"])
        _require(report["acquisition_complete"] and report["usable_price_coverage_complete"]
                 and report["declared_history_coverage_complete"], "incomplete_price_inputs")
        report["complete"] = True
        return VerifiedPriceStage(_encode(report))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
        report["errors"].append(str(exc) if isinstance(exc, _Invalid)
                                else "invalid_or_incomplete_verified_price_inputs")
        if not report["accounting_complete"]:
            report["outcomes"] = [{"ticker": s, "status": "unknown",
                                   "reasons": ["artifact_validation_failed"]} for s in names]
        raise PriceBridgeRefused(report) from None
