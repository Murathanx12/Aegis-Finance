"""Bounded injected GET account -> positions -> account observation candidate.

No transport/credential default, persistence, retries, historical repair or send.
Bracket stability is an observation, not a cross-endpoint atomicity guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import math
import re
import time
from uuid import UUID, uuid4

from backend.services.owner_event_warning import (
    EQUITY_TOLERANCE_USD,
    HELD_MARK_TOLERANCE_USD,
    POSITION_SUM_TOLERANCE_FRACTION,
)

PAPER_HOST = "https://paper-api.alpaca.markets"
MAX_RESPONSE_BYTES = 1048576
MAX_POSITIONS = 512
MAX_WINDOW_SECONDS = 30
UNKNOWN = "UNKNOWN"


class CollectionRefused(ValueError):
    """Sanitized code; provider bodies and exception strings never enter receipts."""


def _require(value, code):
    if not value:
        raise CollectionRefused(code)


@dataclass(frozen=True)
class ReadRequest:
    attempt_id: str
    request_id: str
    method: str
    host: str
    path: str


@dataclass(frozen=True)
class ReadResponse:
    """Lossless body plus explicitly caller-bound transport provenance.

    account_scope_sha256 is SHA256 of the canonical account UUID, not a key or
    credential hash. Positions lacks its own account UUID: this binding is a
    transport attestation, NOT independent provider authentication.
    """

    attempt_id: str
    request_id: str
    host: str
    path: str
    account_scope_sha256: str
    status_code: int
    complete: bool
    body: bytes
    provider_asof_utc: str | None = None
    provider_clock_basis: str = UNKNOWN
    position_mark_asof_utc: dict[str, str] | None = None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _utc(value):
    _require(
        isinstance(value, datetime) and value.utcoffset() == timedelta(0), "UTC_CLOCK_REQUIRED"
    )
    return value.astimezone(timezone.utc)


def _provider_clock(value, received):
    if value is None:
        return UNKNOWN
    _require(
        type(value) is str
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value),
        "PROVIDER_CLOCK_INVALID",
    )
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CollectionRefused("PROVIDER_CLOCK_INVALID") from None
    _require(stamp <= received, "PROVIDER_CLOCK_FUTURE")
    return stamp.isoformat()


def _object(pairs):
    out = {}
    for key, value in pairs:
        _require(key not in out, "DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _parse(raw):
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object,
            parse_float=Decimal,
            parse_constant=lambda _: _require(False, "NONFINITE_JSON"),
        )
    except CollectionRefused:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise CollectionRefused("MALFORMED_JSON") from None


def _number(value):
    _require(type(value) in (str, int, Decimal), "MISSING_OR_INVALID_NUMBER")
    text = str(value)
    _require(
        len(text) <= 96 and re.fullmatch(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", text),
        "MISSING_OR_INVALID_NUMBER",
    )
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise CollectionRefused("MISSING_OR_INVALID_NUMBER") from None
    _require(
        number.is_finite()
        and len(number.as_tuple().digits) <= 64
        and -30 <= number.as_tuple().exponent <= 30
        and abs(number) <= Decimal("1e15"),
        "NUMBER_RANGE_OR_PRECISION",
    )
    return number


def account_scope(account_id):
    """Opaque identity handoff, never a hash of credentials."""
    try:
        _require(
            type(account_id) is str and str(UUID(account_id)) == account_id.lower(),
            "ACCOUNT_ID_REQUIRED",
        )
        return _sha(str(UUID(account_id)).encode("ascii"))
    except (ValueError, AttributeError):
        raise CollectionRefused("ACCOUNT_ID_REQUIRED") from None


def _account(value, expected_scope):
    _require(type(value) is dict, "ACCOUNT_OBJECT_REQUIRED")
    _require(account_scope(value.get("id")) == expected_scope, "ACCOUNT_IDENTITY_MISMATCH")
    _require(
        value.get("status") == "ACTIVE" and value.get("currency") == "USD", "UNSUPPORTED_ACCOUNT"
    )
    for key in ("trading_blocked", "account_blocked"):
        _require(
            type(value.get(key)) is bool and value[key] is False,
            "ACCOUNT_STATUS_UNKNOWN_OR_BLOCKED",
        )
    return {
        key: _number(value.get(key))
        for key in ("equity", "cash", "long_market_value", "short_market_value")
    }


def collect(
    *,
    read=None,
    expected_account_scope_sha256=None,
    utc_clock=None,
    monotonic_clock=None,
    max_seconds=5,
    max_positions=MAX_POSITIONS,
):
    """One attempt, at most three GETs. Injected transport MUST preserve JSON bytes.

    Missing transport/context is an API refusal. Attempt failures return an
    explicit REFUSED receipt and no snapshot; zero values are never substituted.
    Returned snapshots are PRIVATE candidate data; diagnostics omit all holdings.
    """
    _require(callable(read), "EXPLICIT_READ_TRANSPORT_REQUIRED")
    _require(
        type(expected_account_scope_sha256) is str
        and re.fullmatch("[0-9a-f]{64}", expected_account_scope_sha256),
        "EXPECTED_ACCOUNT_SCOPE_REQUIRED",
    )
    _require(
        type(max_seconds) in (int, float)
        and 0 < max_seconds <= MAX_WINDOW_SECONDS
        and math.isfinite(max_seconds),
        "INVALID_WINDOW",
    )
    _require(
        type(max_positions) is int and 1 <= max_positions <= MAX_POSITIONS, "INVALID_POSITION_CAP"
    )
    utc_clock = utc_clock or (lambda: datetime.now(timezone.utc))
    monotonic_clock = monotonic_clock or time.monotonic
    attempt = uuid4().hex
    observations = []
    diag = dict(
        account_bracket="UNKNOWN",
        positions_count=UNKNOWN,
        account_identity_residual_usd=UNKNOWN,
        reported_long_minus_position_sum_usd=UNKNOWN,
        position_sum_tolerance_usd=UNKNOWN,
        maximum_qty_price_residual_usd=UNKNOWN,
        equity_identity_tolerance_usd=str(EQUITY_TOLERANCE_USD),
        held_mark_tolerance_usd=str(HELD_MARK_TOLERANCE_USD),
        position_sum_tolerance_fraction=str(POSITION_SUM_TOLERANCE_FRACTION),
        acquisition_span_seconds=UNKNOWN,
        classification="UNKNOWN",
        valuation_clock_alignment="UNKNOWN",
        atomicity="NOT_PROVEN",
        completeness="UNKNOWN",
    )
    started = None
    last_mono = None
    last_utc = None
    values = []
    replies = []

    def tick():
        nonlocal last_mono
        try:
            value = monotonic_clock()
        except Exception:
            raise CollectionRefused("MONOTONIC_CLOCK_INVALID") from None
        _require(type(value) in (int, float) and math.isfinite(value), "MONOTONIC_CLOCK_INVALID")
        _require(last_mono is None or value >= last_mono, "MONOTONIC_CLOCK_REVERSED")
        last_mono = value
        if started is not None:
            _require(value - started <= max_seconds, "ACQUISITION_WINDOW_EXCEEDED")
        return value

    def wall():
        nonlocal last_utc
        try:
            raw = utc_clock()
        except Exception:
            raise CollectionRefused("UTC_CLOCK_INVALID") from None
        value = _utc(raw)
        _require(last_utc is None or value >= last_utc, "UTC_CLOCK_REVERSED")
        if observations:
            first = datetime.fromisoformat(observations[0]["request_utc"])
            _require(
                (value - first).total_seconds() <= max_seconds, "UTC_ACQUISITION_WINDOW_EXCEEDED"
            )
        last_utc = value
        return value

    def result(status, reason, snapshot=None):
        if observations and observations[-1]["receipt_utc"] != UNKNOWN:
            span = datetime.fromisoformat(observations[-1]["receipt_utc"]) - datetime.fromisoformat(
                observations[0]["request_utc"]
            )
            if span.total_seconds() >= 0:
                diag["acquisition_span_seconds"] = str(span.total_seconds())
        receipt = dict(
            schema="clocked-pc-paper-collection/1",
            attempt_id=attempt,
            status=status,
            reason=reason,
            observations=observations,
            diagnostics=diag,
            request_count=len(observations),
            authority=dict(
                adopted=False,
                warning="NONE",
                delivery="NOT_ATTEMPTED",
                forecast_writes=0,
                portfolio_action="NONE",
                provider_origin="CALLER_BOUND_TRANSPORT",
            ),
        )
        receipt["receipt_sha256"] = _sha(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        )
        return dict(receipt=receipt, snapshot=snapshot)

    try:
        started = tick()
        for index, (label, endpoint) in enumerate(
            (
                ("account_before", "/v2/account"),
                ("positions", "/v2/positions"),
                ("account_after", "/v2/account"),
            )
        ):
            remaining = max_seconds - (tick() - started)
            _require(remaining > 0, "ACQUISITION_WINDOW_EXCEEDED")
            request = ReadRequest(attempt, uuid4().hex, "GET", PAPER_HOST, endpoint)
            requested = wall()
            node = dict(
                component=label,
                request_id=request.request_id,
                request_utc=requested.isoformat(),
                receipt_utc=UNKNOWN,
                response_sha256=UNKNOWN,
                response_bytes=UNKNOWN,
                provider_asof_utc=UNKNOWN,
                provider_clock_basis=UNKNOWN,
                outcome="REQUESTED",
            )
            observations.append(node)
            try:
                reply = read(request, timeout=remaining, max_bytes=MAX_RESPONSE_BYTES)
            except Exception:
                node["outcome"] = "TRANSPORT_REFUSED"
                node["receipt_utc"] = wall().isoformat()
                tick()
                raise CollectionRefused("TRANSPORT_REFUSED") from None
            received = wall()
            node["receipt_utc"] = received.isoformat()
            tick()
            _require(type(reply) is ReadResponse, "LOSSLESS_RESPONSE_REQUIRED")
            _require(
                (reply.attempt_id, reply.request_id, reply.host, reply.path)
                == (attempt, request.request_id, PAPER_HOST, endpoint),
                "RESPONSE_ATTEMPT_OR_ENDPOINT_MISMATCH",
            )
            _require(
                type(reply.account_scope_sha256) is str
                and reply.account_scope_sha256 == expected_account_scope_sha256,
                "RESPONSE_ACCOUNT_SCOPE_MISMATCH",
            )
            _require(
                type(reply.status_code) is int and reply.status_code == 200, "HTTP_RESPONSE_REFUSED"
            )
            _require(reply.complete is True, "INCOMPLETE_RESPONSE")
            _require(
                type(reply.body) is bytes and 0 < len(reply.body) <= MAX_RESPONSE_BYTES,
                "RESPONSE_BYTE_CAP_OR_EMPTY",
            )
            node.update(response_sha256=_sha(reply.body), response_bytes=len(reply.body))
            _require(
                (reply.provider_asof_utc is None and reply.provider_clock_basis == UNKNOWN)
                or (
                    reply.provider_asof_utc is not None
                    and reply.provider_clock_basis == "VALUATION_AS_OF"
                ),
                "PROVIDER_CLOCK_BASIS_REQUIRED",
            )
            node.update(
                provider_asof_utc=_provider_clock(reply.provider_asof_utc, received),
                provider_clock_basis=reply.provider_clock_basis,
            )
            value = _parse(reply.body)
            node["outcome"] = "RECEIVED"
            values.append(value)
            replies.append(reply)
            if index in (0, 2):
                _account(value, expected_account_scope_sha256)
                _require(reply.position_mark_asof_utc is None, "ACCOUNT_POSITION_CLOCK_FIELDS")
        diag["acquisition_span_seconds"] = str(
            (last_utc - datetime.fromisoformat(observations[0]["request_utc"])).total_seconds()
        )
        _require(
            Decimal(diag["acquisition_span_seconds"]) <= Decimal(str(max_seconds)),
            "UTC_ACQUISITION_WINDOW_EXCEEDED",
        )
        # Entire decoded account objects must agree. No cherry-picked economic
        # subset or latest-account substitution can hide a bracket movement.
        diag["account_bracket"] = (
            "CHANGED" if values[0] != values[2] else "IDENTICAL_DECODED_ACCOUNT_RESPONSES"
        )
        _require(values[0] == values[2], "ACCOUNT_BRACKET_CHANGED")
        diag["account_bracket"] = "IDENTICAL_DECODED_ACCOUNT_RESPONSES"
        _require(
            type(values[1]) is list and len(values[1]) <= max_positions, "POSITIONS_LIST_OR_CAP"
        )
        diag["positions_count"] = len(values[1])
        diag["completeness"] = "TRANSPORT_ATTESTED_FULL_ENDPOINT_RESPONSE_NOT_INDEPENDENTLY_PROVEN"
        with localcontext() as context:
            context.prec = 96
            account = _account(values[0], expected_account_scope_sha256)
            equity, cash, long, short = (
                account[k] for k in ("equity", "cash", "long_market_value", "short_market_value")
            )
            identity_residual = cash + long - short - equity
            diag["account_identity_residual_usd"] = str(identity_residual)
            _require(
                equity > 0 and cash >= 0 and long >= 0 and short == 0,
                "UNSUPPORTED_ACCOUNT_EXPOSURE",
            )
            _require(abs(identity_residual) <= EQUITY_TOLERANCE_USD, "ACCOUNT_EQUITY_IDENTITY")
            rows = []
            symbols = set()
            asset_ids = set()
            asset_identities = set()
            maximum_mark_residual = Decimal(0)
            unknown_leverage = False
            marks = replies[1].position_mark_asof_utc
            _require(marks is None or type(marks) is dict, "POSITION_CLOCK_MAP_INVALID")
            known_clocks = [
                n["provider_asof_utc"] for n in observations if n["provider_asof_utc"] != UNKNOWN
            ]
            for p in values[1]:
                _require(type(p) is dict, "INVALID_POSITION")
                symbol = p.get("symbol")
                _require(
                    type(symbol) is str and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,15}", symbol),
                    "INVALID_POSITION_SYMBOL",
                )
                aid = p.get("asset_id")
                try:
                    identity = account_scope(aid)  # canonical UUID shape, never reported
                except CollectionRefused:
                    raise CollectionRefused("POSITION_ASSET_ID_REQUIRED") from None
                _require(
                    symbol not in symbols and identity not in asset_identities, "DUPLICATE_POSITION"
                )
                symbols.add(symbol)
                asset_ids.add(aid)
                asset_identities.add(identity)
                _require(
                    p.get("side") == "long" and p.get("asset_class") == "us_equity",
                    "POSITION_CLASSIFICATION_REFUSED",
                )
                qty, value, price = (
                    _number(p.get(k)) for k in ("qty", "market_value", "current_price")
                )
                _require(min(qty, value, price) > 0, "NONPOSITIVE_POSITION")
                residual = value - qty * price
                maximum_mark_residual = max(maximum_mark_residual, abs(residual))
                _require(abs(residual) <= HELD_MARK_TOLERANCE_USD, "POSITION_MARK_RECONCILIATION")
                # Marginability/account buying-power multiplier are not leverage proof.
                leverage = UNKNOWN
                if "leverage" in p and p["leverage"] is not None:
                    declared = _number(p["leverage"])
                    _require(declared == 1, "POSITION_LEVERAGE_REFUSED")
                    leverage = str(declared)
                else:
                    unknown_leverage = True
                mark = _provider_clock(
                    marks.get(aid) if marks else None,
                    datetime.fromisoformat(observations[1]["receipt_utc"]),
                )
                if mark != UNKNOWN:
                    known_clocks.append(mark)
                rows.append(
                    dict(
                        symbol=symbol,
                        qty=str(qty),
                        market_value=str(value),
                        current_price=str(price),
                        side=p["side"],
                        asset_class=p["asset_class"],
                        instrument="equity",
                        leverage=leverage,
                        classification_basis="EXPLICIT_PROVIDER_FIELDS_NOT_INDEPENDENT_SECURITY_PROOF",
                        provider_mark_asof_utc=mark,
                    )
                )
            _require(marks is None or set(marks) <= asset_ids, "POSITION_CLOCK_IDENTITY_MISMATCH")
            _require(len(set(known_clocks)) <= 1, "PROVIDER_VALUATION_CLOCK_MISMATCH")
            if len(known_clocks) == 3 + len(rows):
                diag["valuation_clock_alignment"] = (
                    "PROVIDER_REPORTED_COMMON_ASOF_NOT_ATOMICITY_PROOF"
                )
            diag["maximum_qty_price_residual_usd"] = str(maximum_mark_residual)
            position_sum = sum((_number(p["market_value"]) for p in rows), Decimal(0))
            residual = long - position_sum
            allowed = max(Decimal("1.00"), equity * POSITION_SUM_TOLERANCE_FRACTION)
            diag["reported_long_minus_position_sum_usd"] = str(residual)
            diag["position_sum_tolerance_usd"] = str(allowed)
            _require(abs(residual) <= allowed, "POSITION_SUM_RECONCILIATION")
            diag["classification"] = (
                "LEVERAGE_UNKNOWN" if unknown_leverage else "EXPLICIT_FIELDS_CALLER_ATTESTED"
            )
            snapshot = dict(
                schema="clocked-pc-paper-snapshot/1",
                t=observations[1]["receipt_utc"],
                t_basis="POSITIONS_RECEIPT_NOT_ATOMIC_VALUATION",
                equity=str(equity),
                cash=str(cash),
                long_market_value=str(long),
                short_market_value=str(short),
                n_positions=len(rows),
                positions=rows,
                component_clocks=[dict(n) for n in observations],
                attempt_id=attempt,
                atomicity="NOT_PROVEN",
                valuation_clock_alignment=diag["valuation_clock_alignment"],
                classification_status=diag["classification"],
                warning_authority="NONE",
            )
        tick()
        # The observation may be numerically coherent while leverage remains
        # unknown. Explicit UNKNOWN prevents the legacy warning's absent-field
        # default-to-one. This is NOT a warning-ready/accepted result.
        status = (
            "COHERENT_CLASSIFICATION_UNRESOLVED" if unknown_leverage else "COHERENT_OBSERVATION"
        )
        return result(
            status,
            "LEVERAGE_UNKNOWN" if unknown_leverage else "STABLE_BRACKET_RECONCILED",
            snapshot,
        )
    except CollectionRefused as exc:
        if observations:
            observations[-1]["outcome"] = "REFUSED"
        return result("REFUSED", str(exc))
    except Exception:
        return result("REFUSED", "INPUT_CLOCK_OR_TRANSPORT_INVALID")
