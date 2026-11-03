"""Synthetic offline calendar captures; none represents a provider verification."""

import builtins
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
from unittest.mock import patch

import pytest

from backend.services import saved_earnings_calendar_input as S

OBSERVED = "2026-11-03T20:00:00Z"
CUTOFF = "2026-11-03T21:00:00Z"


def event(**changes):
    row = {
        "symbol": "AAPL", "date": "2026-11-06", "hour": "amc",
        "quarter": 4, "year": 2026, "epsEstimate": 1.5,
        "revenueEstimate": 100000000000,
    }
    row.update(changes)
    return row


def response(*rows):
    return json.dumps({"earningsCalendar": list(rows)}, separators=(",", ":")).encode()


_DEFAULT = object()


def build(raw=_DEFAULT, **changes):
    args = {"ticker": "AAPL", "observed_utc": OBSERVED, "cutoff_utc": CUTOFF}
    args.update(changes)
    return S.build_saved_earnings_calendar_input(
        response(event()) if raw is _DEFAULT else raw, **args,
    )


def test_exact_bytes_identity_and_no_prediction():
    raw = response(event())
    packet = build(raw)
    assert packet["status"] == "EVIDENCE_ONLY"
    assert packet["event_date_et"] == "2026-11-06"
    assert packet["days_ahead"] == 3
    assert packet["event_time_status"] == "UNKNOWN"
    assert packet["forecast_status"] == "NOT_GENERATED"
    assert packet["runtime_authority"] == "NONE"
    assert packet["response_sha256"] == hashlib.sha256(raw).hexdigest()
    import base64

    assert base64.b64decode(packet["response_bytes_b64"]) == raw
    assert S.verify_saved_earnings_calendar_input(
        packet, raw, ticker="AAPL", observed_utc=OBSERVED, cutoff_utc=CUTOFF,
    )
    changed = raw.replace(b'"hour":"amc"', b'"hour":"bmo"')
    assert build(changed)["input_id"] != packet["input_id"]
    assert not S.verify_saved_earnings_calendar_input(
        packet, changed, ticker="AAPL", observed_utc=OBSERVED, cutoff_utc=CUTOFF,
    )
    tampered = deepcopy(packet)
    tampered["event_date_et"] = "2026-11-05"
    assert not S.verify_saved_earnings_calendar_input(
        tampered, raw, ticker="AAPL", observed_utc=OBSERVED, cutoff_utc=CUTOFF,
    )


def test_observation_cutoff_boundary_and_future_refusal():
    assert build(observed_utc=CUTOFF)["status"] == "EVIDENCE_ONLY"
    assert build(observed_utc="2026-11-03T21:00:01Z")["reason"] == (
        "OBSERVATION_AFTER_CUTOFF"
    )
    assert build(observed_utc="2026-11-02T21:00:00Z")["status"] == "EVIDENCE_ONLY"
    assert build(observed_utc="2026-11-02T20:59:59Z")["reason"] == "OBSERVATION_STALE"


def test_old_cache_observation_is_never_replaced_with_cache_hit_time():
    saved = response(event())
    assert build(saved, observed_utc="2026-11-02T20:59:59Z")["reason"] == (
        "OBSERVATION_STALE"
    )
    fresh = build(saved, observed_utc="2026-11-03T20:59:59Z")
    assert fresh["status"] == "EVIDENCE_ONLY"
    assert fresh["observed_utc"] == "2026-11-03T20:59:59+00:00"
    assert fresh["input_id"] != build(saved)["input_id"]


def test_date_only_new_york_boundary_and_seven_calendar_days():
    # 00:30 UTC is still the preceding New York date, independent of DST.
    before_midnight_et = "2026-11-04T00:30:00Z"
    assert build(response(event(date="2026-11-04")),
                 cutoff_utc=before_midnight_et)["days_ahead"] == 1
    assert build(response(event(date="2026-11-03")),
                 cutoff_utc=before_midnight_et)["reason"] == "NO_FUTURE_EVENT_IN_WINDOW"
    assert build(response(event(date="2026-11-10")))["days_ahead"] == 7
    assert build(response(event(date="2026-11-11")))["reason"] == (
        "NO_FUTURE_EVENT_IN_WINDOW"
    )
    # Spring DST transition still uses the New York calendar date.
    assert build(response(event(date="2027-03-14")),
                 observed_utc="2027-03-13T20:00:00Z",
                 cutoff_utc="2027-03-14T00:30:00Z")["days_ahead"] == 1


def test_duplicate_conflicting_and_multiple_future_rows_refuse():
    same = event()
    assert build(response(same, same))["reason"] == "AMBIGUOUS_EVENT"
    assert build(response(same, event(date="2026-11-07")))["reason"] == (
        "AMBIGUOUS_EVENT"
    )
    assert build(response(same, event(quarter=1, year=2027)))["reason"] == (
        "AMBIGUOUS_EVENT"
    )
    assert build(response(event(symbol="MSFT"), same))["status"] == "EVIDENCE_ONLY"


def test_later_revision_isolated_by_original_observation():
    old_raw = response(event(date="2026-11-06"))
    revised_raw = response(event(date="2026-11-07"))
    old = build(old_raw)
    assert old["event_date_et"] == "2026-11-06"
    assert build(revised_raw, observed_utc="2026-11-03T21:00:01Z")["reason"] == (
        "OBSERVATION_AFTER_CUTOFF"
    )
    later = build(revised_raw, observed_utc="2026-11-04T20:00:00Z",
                  cutoff_utc="2026-11-04T21:00:00Z")
    assert later["status"] == "EVIDENCE_ONLY"
    assert later["input_id"] != old["input_id"]
    assert build(old_raw) == old


@pytest.mark.parametrize("raw,reason", [
    (None, "INPUT_ABSENT"), (b"", "INPUT_ABSENT"),
    (response(), "CALENDAR_EMPTY"),
    (response(event(symbol="MSFT")), "NO_MATCHING_TICKER"),
    (b"{", "JSON_INVALID"),
    (b'{"earningsCalendar":[],"earningsCalendar":[]}', "JSON_INVALID"),
    (b'{"earningsCalendar":[{"x":NaN}]}', "JSON_INVALID"),
    (b'{"earningsCalendar":[{"x":1e999}]}', "JSON_INVALID"),
    (b'{"earningsCalendar":null}', "CALENDAR_SHAPE_INVALID"),
    (response(event(epsActual=2.0)), "ROW_FIELDS_INVALID"),
    (response(event(date="2026-02-30")), "EVENT_DATE_INVALID"),
    (response(event(quarter=True)), "FISCAL_PERIOD_INVALID"),
])
def test_explicit_missing_and_invalid_refusals(raw, reason):
    assert build(raw)["reason"] == reason


@pytest.mark.parametrize("clock,reason", [
    ({"observed_utc": None}, "OBSERVED_UTC_INVALID"),
    ({"observed_utc": "2026-11-03T20:00:00+08:00"}, "OBSERVED_UTC_INVALID"),
    ({"cutoff_utc": "2026-11-03"}, "CUTOFF_UTC_INVALID"),
    ({"cutoff_utc": "2026-11-03T21:00:00"}, "CUTOFF_UTC_INVALID"),
])
def test_utc_clocks_required(clock, reason):
    assert build(**clock)["reason"] == reason


def test_bounds():
    assert build(b" " * (S.MAX_BYTES + 1))["reason"] == "INPUT_BYTES_INVALID_OR_TOO_LARGE"
    assert build(response(*([event()] * (S.MAX_ROWS + 1))))["reason"] == "TOO_MANY_ROWS"
    nested = b'{"earningsCalendar":' + b"[" * 10 + b"0" + b"]" * 10 + b"}"
    assert build(nested)["reason"] == "JSON_DEPTH_EXCEEDED"
    assert build(bytearray(response(event())))["reason"] == "INPUT_BYTES_INVALID_OR_TOO_LARGE"
    assert build(ticker="aapl")["reason"] == "TICKER_INVALID"


def test_no_io_on_import_and_calls():
    source = Path(S.__file__).read_text(encoding="utf-8")
    code = compile(source, S.__file__, "exec")
    raw = response(event())
    expected = build(raw)

    def denied(*_args, **_kwargs):
        raise AssertionError("unexpected IO")

    with (patch.object(builtins, "open", denied), patch.object(io, "open", denied),
          patch.object(Path, "open", denied), patch.object(socket.socket, "connect", denied),
          patch.object(socket, "create_connection", denied),
          patch.object(subprocess, "Popen", denied)):
        namespace = {"__name__": "calendar_input_isolation_test"}
        exec(code, namespace)
        assert namespace["build_saved_earnings_calendar_input"](
            raw, ticker="AAPL", observed_utc=OBSERVED, cutoff_utc=CUTOFF,
        ) == expected
        assert build(raw) == expected
