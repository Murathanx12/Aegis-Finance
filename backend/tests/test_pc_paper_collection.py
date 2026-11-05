"""Synthetic lossless bracket observations, with all network paths denied."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import ast
import json
from pathlib import Path
import socket
import pytest

from backend.services import pc_paper_collection as C
from backend.services import pc_broker as B, owner_event_warning as W

NOW = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
ACCOUNT = "11111111-1111-4111-8111-111111111111"
ASSET = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SCOPE = C.account_scope(ACCOUNT)


def account():
    return dict(
        id=ACCOUNT,
        status="ACTIVE",
        currency="USD",
        trading_blocked=False,
        account_blocked=False,
        equity="100000",
        cash="80000",
        long_market_value="20000",
        short_market_value="0",
        account_number="PRIVATE_ACCOUNT_NUMBER",
        credential="SECRET_DO_NOT_LOG",
    )


def position():
    return dict(
        asset_id=ASSET,
        symbol="ACME",
        qty="200",
        current_price="100",
        market_value="20000",
        side="long",
        asset_class="us_equity",
        leverage="1",
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kw):
        pytest.fail("NETWORK_OR_LIVE_BROKER_REACHED")

    for obj, name in [
        (socket.socket, "connect"),
        (socket.socket, "connect_ex"),
        (socket, "create_connection"),
        (B, "_call"),
        (B, "credentials"),
        (B, "snapshot"),
        (W, "_deliver"),
    ]:
        monkeypatch.setattr(obj, name, denied)


class Clock:
    def __init__(self):
        self.count = 0

    def utc(self):
        stamp = NOW + timedelta(milliseconds=100 * self.count)
        self.count += 1
        return stamp

    def mono(self):
        return self.count / 10


class Transport:
    def __init__(self, values=None, mutate=None):
        self.values = values if values is not None else [account(), [position()], account()]
        self.calls = []
        self.mutate = mutate

    def __call__(self, request, *, timeout, max_bytes):
        index = len(self.calls)
        self.calls.append((request, timeout))
        assert (
            request.method == "GET"
            and request.host == C.PAPER_HOST
            and timeout > 0
            and max_bytes == C.MAX_RESPONSE_BYTES
        )
        raw = self.values[index]
        body = raw if type(raw) is bytes else json.dumps(raw, separators=(",", ":")).encode()
        reply = C.ReadResponse(
            request.attempt_id,
            request.request_id,
            request.host,
            request.path,
            SCOPE,
            200,
            True,
            body,
        )
        return self.mutate(index, reply) if self.mutate else reply


def run(values=None, mutate=None, **kwargs):
    transport = Transport(values, mutate)
    clock = Clock()
    result = C.collect(
        read=transport,
        expected_account_scope_sha256=SCOPE,
        utc_clock=kwargs.pop("utc_clock", clock.utc),
        monotonic_clock=kwargs.pop("monotonic_clock", clock.mono),
        **kwargs,
    )
    return result, transport


def reason(result):
    return result["receipt"]["reason"]


def test_stable_bracket_precise_clocks_and_sanitized_diagnostics():
    result, transport = run()
    r, s = result["receipt"], result["snapshot"]
    assert r["status"] == "COHERENT_OBSERVATION"
    assert [req.path for req, _ in transport.calls] == [
        "/v2/account",
        "/v2/positions",
        "/v2/account",
    ]
    assert len({req.attempt_id for req, _ in transport.calls}) == 1
    assert len({req.request_id for req, _ in transport.calls}) == 3
    assert len({o[k] for o in r["observations"] for k in ("request_utc", "receipt_utc")}) == 6
    assert all(o["provider_asof_utc"] == "UNKNOWN" for o in r["observations"])
    assert s["t"] == r["observations"][1]["receipt_utc"]
    assert s["atomicity"] == "NOT_PROVEN" and s["valuation_clock_alignment"] == "UNKNOWN"
    assert s["positions"][0]["provider_mark_asof_utc"] == "UNKNOWN"
    assert s["positions"][0]["side"] == "long" and s["positions"][0]["asset_class"] == "us_equity"
    assert s["positions"][0]["leverage"] == "1"
    assert r["diagnostics"]["reported_long_minus_position_sum_usd"] == "0"
    assert r["diagnostics"]["position_sum_tolerance_usd"] == "10.0000"
    public = json.dumps(r)
    for private in (ACCOUNT, ASSET, "ACME", "PRIVATE_ACCOUNT_NUMBER", "SECRET_DO_NOT_LOG"):
        assert private not in public
    assert "account_number" not in s
    assert (
        C._sha(
            json.dumps(
                {k: v for k, v in r.items() if k != "receipt_sha256"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
        == r["receipt_sha256"]
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("cash", "80000.00000001"),
        ("long_market_value", "20000.01"),
        ("buying_power", "1000"),
        ("status", "ACCOUNT_UPDATED"),
    ],
)
def test_any_account_bracket_move_refuses_without_splice(key, value):
    after = account()
    after[key] = value
    result, transport = run([account(), [position()], after])
    assert result["receipt"]["status"] == "REFUSED" and result["snapshot"] is None
    assert reason(result) in ("ACCOUNT_BRACKET_CHANGED", "UNSUPPORTED_ACCOUNT")
    assert len(transport.calls) == 3


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize(
    "attack", ["attempt", "nonce", "scope", "path", "host", "http", "partial", "bool_complete"]
)
def test_request_scope_and_complete_body_binding(index, attack):
    def mutate(i, reply):
        if i != index:
            return reply
        return replace(
            reply,
            **{
                "attempt": dict(attempt_id="previous-attempt"),
                "nonce": dict(request_id="other-request"),
                "scope": dict(account_scope_sha256="f" * 64),
                "path": dict(path="/v2/orders"),
                "host": dict(host="https://api.alpaca.markets"),
                "http": dict(status_code=500),
                "partial": dict(complete=False),
                "bool_complete": dict(complete=1),
            }[attack],
        )

    result, transport = run(mutate=mutate)
    assert result["receipt"]["status"] == "REFUSED" and result["snapshot"] is None
    assert len(transport.calls) == index + 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("asset_id", None),
        ("side", None),
        ("side", "short"),
        ("asset_class", None),
        ("asset_class", "crypto"),
        ("asset_class", "us_option"),
        ("leverage", "2"),
        ("qty", 0),
        ("qty", "-1"),
        ("current_price", None),
        ("market_value", "NaN"),
        ("qty", True),
        ("market_value", float("inf")),
    ],
)
def test_unsupported_missing_negative_boolean_or_nonfinite_fields_refuse(field, value):
    p = position()
    p[field] = value
    result, _ = run([account(), [p], account()])
    assert result["receipt"]["status"] == "REFUSED" and result["snapshot"] is None


def test_missing_leverage_is_unknown_not_silently_defaulted_from_marginability():
    p = position()
    del p["leverage"]
    p["asset_marginable"] = False
    a = account()
    a["multiplier"] = "1"
    result, _ = run([a, [p], deepcopy(a)])
    assert result["receipt"]["status"] == "COHERENT_CLASSIFICATION_UNRESOLVED"
    assert result["snapshot"]["positions"][0]["leverage"] == "UNKNOWN"
    assert result["receipt"]["diagnostics"]["classification"] == "LEVERAGE_UNKNOWN"
    native_source = dict(
        source="sec_edgar_8k_ex99_body",
        tickers=["ACME"],
        title="8-K - Acme (0000000001) (Filer) EX-99.1",
        url="https://www.sec.gov/Archives/edgar/data/1/000000000126000001/results.htm",
        raw_id="0000000001-26-000001:results.htm",
        body="Quarterly financial results.",
        first_seen_utc=(NOW - timedelta(minutes=1)).isoformat(),
        published_utc=(NOW - timedelta(minutes=2)).isoformat(),
    )
    out = W.build_saved_warning_bytes(
        source_bytes=(json.dumps(native_source) + "\n").encode(),
        snapshot_bytes=json.dumps(result["snapshot"]).encode(),
        ticker="ACME",
        now=NOW + timedelta(seconds=1),
    )
    assert out["status"] == "REFUSED" and out["reason"] == "BAD_EQUITY_OR_EXPOSURE"


@pytest.mark.parametrize(
    "residual,accepted",
    [("-10.0001", False), ("-10.0000", True), ("0", True), ("10.0000", True), ("10.0001", False)],
)
def test_both_position_sum_boundaries_remain_exact(residual, accepted):
    p = position()
    p["market_value"] = str(Decimal("20000") - Decimal(residual))
    p["current_price"] = str(Decimal(p["market_value"]) / Decimal(p["qty"]))
    result, _ = run([account(), [p], account()])
    assert (result["receipt"]["status"] == "COHERENT_OBSERVATION") is accepted
    assert result["receipt"]["diagnostics"]["reported_long_minus_position_sum_usd"] == str(
        Decimal(residual)
    )


@pytest.mark.parametrize(
    "residual,accepted",
    [
        ("0.0100000000000000000000001", False),
        ("0.01", True),
        ("-0.01", True),
        ("-0.0100000000000000000000001", False),
    ],
)
def test_equity_identity_uses_unchanged_cent_threshold_and_source_precision(residual, accepted):
    from decimal import localcontext

    with localcontext() as context:
        context.prec = 96
        a = account()
        a["cash"] = str(Decimal("80000") + Decimal(residual))
    result, _ = run([a, [position()], deepcopy(a)])
    assert (result["receipt"]["status"] == "COHERENT_OBSERVATION") is accepted
    assert Decimal(result["receipt"]["diagnostics"]["account_identity_residual_usd"]) == Decimal(
        residual
    )


def test_duplicate_asset_uuid_case_alias_and_symbol_refuse():
    p = position()
    other = deepcopy(p)
    other["symbol"] = "OTHER"
    other["asset_id"] = ASSET.upper()
    for rows in ([p, deepcopy(p)], [p, other]):
        result, _ = run([account(), rows, account()])
        assert reason(result) == "DUPLICATE_POSITION" and result["snapshot"] is None


def test_provider_mark_clocks_are_distinct_from_receipt_and_unknown_by_default():
    mark = (NOW - timedelta(seconds=1)).isoformat()

    def metadata(i, r):
        return replace(
            r,
            provider_asof_utc=mark,
            provider_clock_basis="VALUATION_AS_OF",
            position_mark_asof_utc={ASSET: mark} if i == 1 else None,
        )

    result, _ = run(mutate=metadata)
    assert result["receipt"]["status"] == "COHERENT_OBSERVATION"
    assert result["snapshot"]["positions"][0]["provider_mark_asof_utc"] == mark
    assert (
        result["snapshot"]["valuation_clock_alignment"]
        == "PROVIDER_REPORTED_COMMON_ASOF_NOT_ATOMICITY_PROOF"
    )
    assert result["snapshot"]["t"] != mark


@pytest.mark.parametrize(
    "attack", ["basis", "future", "different", "foreign_asset", "naive", "header_date"]
)
def test_mixed_ambiguous_or_future_provider_clocks_refuse(attack):
    mark = (NOW - timedelta(seconds=1)).isoformat()

    def mutate(i, r):
        if attack == "basis":
            return replace(r, provider_asof_utc=mark)
        if attack == "header_date":
            return replace(r, provider_asof_utc=mark, provider_clock_basis="HTTP_DATE")
        if attack == "future":
            return replace(
                r, provider_asof_utc="2099-01-01T00:00:00Z", provider_clock_basis="VALUATION_AS_OF"
            )
        if attack == "naive":
            return replace(
                r, provider_asof_utc="2026-11-06T00:00:00", provider_clock_basis="VALUATION_AS_OF"
            )
        if attack == "foreign_asset" and i == 1:
            return replace(r, position_mark_asof_utc={ACCOUNT: mark})
        if attack == "different":
            return replace(
                r,
                provider_asof_utc=(NOW - timedelta(seconds=i + 1)).isoformat(),
                provider_clock_basis="VALUATION_AS_OF",
            )
        return r

    result, _ = run(mutate=mutate)
    assert result["receipt"]["status"] == "REFUSED" and result["snapshot"] is None


@pytest.mark.parametrize(
    "body",
    [
        b"null",
        b"",
        b"{bad}",
        b'[{"qty":NaN}]',
        b'{"id":"a","id":"b"}',
        b'{"id":"a","\\u0069d":"b"}',
        b" " * 1048577,
    ],
    ids=["null", "empty", "malformed", "nonfinite", "duplicate", "escaped_duplicate", "oversized"],
)
def test_invalid_json_no_data_duplicate_keys_and_byte_cap_refuse(body):
    result, transport = run([body, [position()], account()])
    assert result["receipt"]["status"] == "REFUSED" and result["snapshot"] is None
    assert len(transport.calls) == 1


def test_empty_complete_list_is_not_failed_fetch_default_zero():
    a = account()
    a.update(cash=a["equity"], long_market_value="0")
    good, _ = run([a, [], deepcopy(a)])
    assert (
        good["receipt"]["status"] == "COHERENT_OBSERVATION" and good["snapshot"]["n_positions"] == 0
    )
    bad, _ = run([a, None, deepcopy(a)])
    assert bad["receipt"]["status"] == "REFUSED" and bad["snapshot"] is None


def test_time_budget_and_clock_reversal_are_visible_no_retry():
    class Slow(Clock):
        def mono(self):
            return self.count * 10.0

    slow = Slow()
    result, transport = run(utc_clock=slow.utc, monotonic_clock=slow.mono)
    assert reason(result) == "ACQUISITION_WINDOW_EXCEEDED" and len(transport.calls) == 1
    stamps = iter([NOW, NOW - timedelta(seconds=1)])
    result, transport = run(utc_clock=lambda: next(stamps))
    assert reason(result) == "UTC_CLOCK_REVERSED" and len(transport.calls) == 1
    result, transport = run(utc_clock=lambda: datetime(2026, 11, 6))
    assert reason(result) == "UTC_CLOCK_REQUIRED" and not transport.calls


def test_transport_exception_is_redacted_and_three_read_budget_is_not_retried():
    def broken(req, timeout, max_bytes):
        raise RuntimeError("SECRET_DO_NOT_LOG PRIVATE_ACCOUNT_NUMBER")

    result = C.collect(read=broken, expected_account_scope_sha256=SCOPE)
    assert result["receipt"]["status"] == "REFUSED" and result["snapshot"] is None
    assert result["receipt"]["request_count"] == 1 and reason(result) == "TRANSPORT_REFUSED"
    assert "SECRET_DO_NOT_LOG" not in json.dumps(result)


def test_missing_transport_scope_and_invalid_bounds_refuse_before_any_call():
    with pytest.raises(C.CollectionRefused, match="EXPLICIT_READ_TRANSPORT_REQUIRED"):
        C.collect()
    with pytest.raises(C.CollectionRefused, match="EXPECTED_ACCOUNT_SCOPE_REQUIRED"):
        C.collect(read=lambda *a: None)
    for value in (True, 0, -1, float("nan"), float("inf"), 31, 10**1000):
        with pytest.raises(C.CollectionRefused, match="INVALID_WINDOW"):
            C.collect(
                read=lambda *a: pytest.fail("called"),
                expected_account_scope_sha256=SCOPE,
                max_seconds=value,
            )


def test_lossless_raw_json_precision_survives_to_snapshot():
    body = (
        json.dumps(account(), separators=(",", ":"))
        .replace('"80000"', "80000.0000000000000000000000000000")
        .encode()
    )
    result, _ = run([body, [position()], body])
    assert result["receipt"]["status"] == "COHERENT_OBSERVATION"
    assert result["snapshot"]["cash"] == "80000.0000000000000000000000000000"


def test_position_cap_and_failed_parse_cannot_leave_partial_snapshot():
    result, _ = run(
        [account(), [position(), dict(position(), symbol="OTHER", asset_id=ACCOUNT)], account()],
        max_positions=1,
    )
    assert reason(result) == "POSITIONS_LIST_OR_CAP" and result["snapshot"] is None
    result, _ = run(
        [
            account(),
            [position(), dict(position(), symbol="OTHER", asset_id=ACCOUNT, qty=None)],
            account(),
        ]
    )
    assert result["snapshot"] is None


def test_original_snapshot_writer_and_warning_thresholds_unchanged():
    assert W.EQUITY_TOLERANCE_USD == C.EQUITY_TOLERANCE_USD == Decimal("0.01")
    assert W.HELD_MARK_TOLERANCE_USD == C.HELD_MARK_TOLERANCE_USD == Decimal("0.01")
    assert (
        W.POSITION_SUM_TOLERANCE_FRACTION == C.POSITION_SUM_TOLERANCE_FRACTION == Decimal("0.0001")
    )
    tree = ast.parse(Path(C.__file__).read_bytes())
    assert not any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr
        in ("write_text", "write_bytes", "open", "snapshot", "submit", "send_owner_once")
        for n in ast.walk(tree)
    )


def source_row():
    return dict(
        source="sec_edgar_8k_ex99_body",
        tickers=["ACME"],
        title="8-K - Acme (0000000001) (Filer) EX-99.1",
        url="https://www.sec.gov/Archives/edgar/data/1/000000000126000001/results.htm",
        raw_id="0000000001-26-000001:results.htm",
        body="Quarterly financial results.",
        first_seen_utc=(NOW - timedelta(minutes=1)).isoformat(),
        published_utc=(NOW - timedelta(minutes=2)).isoformat(),
    )


def test_coherent_explicit_synthetic_classification_passes_existing_byte_only_gate():
    result, _ = run()
    out = W.build_saved_warning_bytes(
        source_bytes=(json.dumps(source_row()) + "\n").encode(),
        snapshot_bytes=json.dumps(result["snapshot"]).encode(),
        ticker="ACME",
        now=NOW + timedelta(seconds=1),
    )
    assert out["status"] == "PROVISIONAL"
    assert out["reconciliation"]["position_sum_tolerance_usd"] == "10.0000"
    assert out["reconciliation"]["equity_identity_tolerance_usd"] == "0.01"
    assert out["reconciliation"]["held_mark_tolerance_usd"] == "0.01"


def test_sequential_mismatch_pattern_is_not_repaired_or_rounded_away():
    p = position()
    p["market_value"] = "20225.9679"
    p["current_price"] = str(Decimal(p["market_value"]) / Decimal(p["qty"]))
    result, _ = run([account(), [p], account()])
    assert (
        result["receipt"]["status"] == "REFUSED" and reason(result) == "POSITION_SUM_RECONCILIATION"
    )
    assert result["receipt"]["diagnostics"]["reported_long_minus_position_sum_usd"] == "-225.9679"
    assert result["snapshot"] is None


def test_monotonic_or_utc_jump_stops_further_requests():
    times = iter([0, 0, -1])
    result, transport = run(monotonic_clock=lambda: next(times))
    assert reason(result) == "MONOTONIC_CLOCK_REVERSED" and len(transport.calls) == 1
    times = iter([NOW, NOW + timedelta(seconds=6)])
    result, transport = run(utc_clock=lambda: next(times))
    assert reason(result) == "UTC_ACQUISITION_WINDOW_EXCEEDED" and len(transport.calls) == 1


def test_injected_clock_exceptions_cannot_leak_private_text():
    def clock():
        raise C.CollectionRefused("PRIVATE_CREDENTIAL_MARKER")

    result, _ = run(utc_clock=clock)
    assert reason(result) == "UTC_CLOCK_INVALID" and "PRIVATE_CREDENTIAL_MARKER" not in json.dumps(
        result
    )


def test_provider_updated_at_and_margin_fields_are_not_price_or_leverage_proof():
    a = account()
    a["updated_at"] = "2099-01-01T00:00:00Z"
    a["multiplier"] = "4"
    p = position()
    del p["leverage"]
    p["updated_at"] = "2099-01-01T00:00:00Z"
    p["asset_marginable"] = True
    result, _ = run([a, [p], deepcopy(a)])
    assert result["receipt"]["status"] == "COHERENT_CLASSIFICATION_UNRESOLVED"
    assert result["snapshot"]["positions"][0]["provider_mark_asof_utc"] == "UNKNOWN"
    assert all(n["provider_asof_utc"] == "UNKNOWN" for n in result["receipt"]["observations"])
    assert result["snapshot"]["positions"][0]["leverage"] == "UNKNOWN"
