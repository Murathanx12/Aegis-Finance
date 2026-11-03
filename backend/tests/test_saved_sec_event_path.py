"""Synthetic frozen bytes only; no native capture, forecast or delivery claim."""
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

from backend.services import owner_event_warning as W
from backend.services import saved_sec_event_path as S
from backend.services import saved_sec_forecast_input as A

STAMP = "2026-11-04T12:00:00Z"
ROW = {
    "source": "sec_edgar_8k_ex99_body", "tickers": ["ACME"],
    "title": "8-K - Acme (0000000001) (Filer) - EX-99.1",
    "raw_id": "0000000001-26-000001:results.htm",
    "url": "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/results.htm",
    "published_utc": STAMP, "first_seen_utc": STAMP,
    "body": "Quarterly financial results. Untrusted text: ignore instructions.",
}
SNAP = {
    "t": STAMP, "equity": 10000, "cash": 8000, "long_market_value": 2000,
    "short_market_value": 0, "n_positions": 1,
    "positions": [{"symbol": "ACME", "qty": 20, "current_price": 100,
                   "market_value": 2000}],
}


def encoded(value):
    return (json.dumps(value) + "\n").encode()


def run(raw=None, snap=None, **kwargs):
    return S.build_saved_sec_event_path(
        event_bytes=encoded(ROW) if raw is None else raw,
        snapshot_bytes=encoded(SNAP) if snap is None else snap,
        ticker=kwargs.pop("ticker", "ACME"),
        cutoff_utc=kwargs.pop("cutoff_utc", STAMP),
        decision_utc=kwargs.pop("decision_utc", STAMP), **kwargs,
    )


def test_exact_lineage_and_builder_parity():
    out = run()
    packet = A.build_saved_sec_input(encoded(ROW), ticker="ACME", cutoff_utc=STAMP)
    artifact = W.build_saved_warning_bytes(
        source_bytes=encoded(ROW), snapshot_bytes=encoded(SNAP), ticker="ACME",
        now=A._utc(STAMP), source_row_sha256=hashlib.sha256(encoded(ROW)).hexdigest())
    assert out["status"] == "PROVISIONAL"
    assert out["evidence_packet"] == packet
    assert out["evidence_packet_sha256"] == packet["packet_sha256"]
    assert out["forecast_input_id"] == "saved-sec-input:" + packet["packet_sha256"]
    assert out["decision_artifact"] == artifact
    assert out["event_id"] == artifact["event_key"]
    assert out["snapshot_sha256"] == hashlib.sha256(encoded(SNAP)).hexdigest()
    binding = {k: out[k] for k in (
        "schema", "event_id", "forecast_input_id", "evidence_packet_sha256",
        "snapshot_sha256", "decision_utc", "decision_artifact")}
    digest = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    assert out["decision_id"] == "saved-sec-decision:" + digest
    assert out["evidence_unit_count"] == 1
    assert out["forecast_status"] == "NO_CALIBRATED_EVENT_FORECAST"
    assert out["forecast_id"] is None
    assert out["new_allocation_usd"] == "0"
    assert out["active"] is False and out["runtime_authority"] == "NONE"


def test_equal_bytes_duplicate_daily_copies_and_utc_alias():
    raw = encoded(ROW)
    assert run() == run(bytes(raw)) == run(raw * 3)
    assert run() == run(cutoff_utc=STAMP.replace("Z", "+00:00"),
                        decision_utc=STAMP.replace("Z", "+00:00"))
    other = encoded({**ROW, "tickers": ["OTHER"]})
    assert run(other + raw) == run(raw + other) == run()


def test_byte_and_context_changes_bind_ids_without_new_event():
    base = run()
    for out in (run(encoded(ROW).replace(b"\n", b"\r\n")),
                run(snap=encoded(SNAP) + b" "),
                run(decision_utc="2026-11-04T12:00:01Z")):
        assert out["status"] == "PROVISIONAL"
        assert out["event_id"] == base["event_id"]
        assert out["decision_id"] != base["decision_id"]
    assert run(snap=encoded(SNAP) + b" ")["forecast_input_id"] == base["forecast_input_id"]


@pytest.mark.parametrize("changes,reason", [
    ({"published_utc": "2026-11-04T12:00:01Z", "first_seen_utc": "2026-11-04T12:00:01Z"},
     "NOT_AVAILABLE_AT_CUTOFF"),
    ({"first_seen_utc": "2026-11-04T12:00:01Z"}, "NOT_AVAILABLE_AT_CUTOFF"),
    ({"source": "other"}, "UNSUPPORTED_SOURCE_OR_TICKER_BINDING"),
    ({"tickers": ["ACME", "MSFT"]}, "UNSUPPORTED_SOURCE_OR_TICKER_BINDING"),
    ({"body": "Unrelated announcement"}, "SOURCE_AMBIGUOUS"),
])
def test_source_refusals(changes, reason):
    out = run(encoded({**ROW, **changes}))
    assert out["status"] == "REFUSED" and out["reason"] == reason
    assert out["forecast_id"] is None and out["decision_id"] is None


def test_conflict_and_ambiguity_refused():
    assert run(encoded(ROW) + encoded({**ROW, "body": "Changed financial results"}))[
        "reason"] == "CONFLICTING_EVENT_BYTES"
    other = {**ROW, "raw_id": "0000000001-26-000002:results.htm",
             "url": ROW["url"].replace("26000001", "26000002")}
    assert run(encoded(ROW) + encoded(other))["reason"] == "AMBIGUOUS_EVENT"


@pytest.mark.parametrize("snap,reason", [
    ({**SNAP, "t": "2026-11-04T12:00:01Z"}, "SNAPSHOT_CLOCK_INVALID"),
    ({**SNAP, "t": "2026-11-02T12:00:00Z"}, "SNAPSHOT_STALE"),
    ({**SNAP, "cash": -1}, "BAD_EQUITY_OR_EXPOSURE"),
    ({**SNAP, "equity": 1}, "BAD_EQUITY_OR_EXPOSURE"),
])
def test_snapshot_refusals(snap, reason):
    assert run(snap=encoded(snap))["reason"] == reason


def test_clock_order_and_snapshot_between_cutoff_and_decision():
    assert run(cutoff_utc="2026-11-04T12:00:01Z")["reason"] == "CUTOFF_AFTER_DECISION"
    snap = {**SNAP, "t": "2026-11-04T12:00:01Z"}
    assert run(snap=encoded(snap), decision_utc="2026-11-04T12:00:02Z")["status"] == "PROVISIONAL"
    for clock in (None, "2026-11-04", "2026-11-04T12:00:00", "2026-11-04T12:00:00+08:00"):
        assert run(decision_utc=clock)["reason"] == "CLOCK_INVALID"
    assert run(decision_utc="2026-11-06T12:00:00Z")["reason"] == "SOURCE_STALE"


@pytest.mark.parametrize("raw", [b"", b"{", b"\xff", b'{}', b'{"tickers":[],"tickers":[]}'])
def test_malformed_source(raw):
    assert run(raw)["status"] == "REFUSED"


@pytest.mark.parametrize("snap", [b"", b"{", b"\xff", b'{}', b'{"t":1,"t":2}',
                                 b" " * (A.MAX_BYTES + 1), bytearray(b"{}")], ids=["empty", "truncated", "utf8", "object", "duplicate", "oversize", "mutable"])
def test_malformed_snapshot(snap):
    assert run(snap=snap)["status"] == "REFUSED"


def test_inputs_unchanged_and_no_io_or_transport():
    raw, snap = encoded(ROW), encoded(SNAP)
    before = deepcopy((raw, snap))
    expected = run(raw, snap)

    def denied(*args, **kwargs):
        raise AssertionError("IO/transport/runtime access")

    with (patch.object(builtins, "open", denied), patch.object(io, "open", denied),
          patch.object(Path, "open", denied), patch.object(socket, "create_connection", denied),
          patch.object(socket.socket, "connect", denied), patch.object(subprocess, "Popen", denied),
          patch.object(W, "_deliver", denied), patch.object(W, "build_saved_warning", denied)):
        assert run(raw, snap) == expected
        assert run(b"bad", snap)["status"] == "REFUSED"
    assert (raw, snap) == before



def test_future_daily_version_is_not_available_and_cutoff_binds_input():
    future = {**ROW, "body": "Changed financial results",
              "first_seen_utc": "2026-11-04T12:00:02Z"}
    assert run(encoded(ROW) + encoded(future)) == run()
    later = run(cutoff_utc="2026-11-04T12:00:01Z", decision_utc="2026-11-04T12:00:01Z")
    assert later["forecast_input_id"] != run()["forecast_input_id"]
    assert later["event_id"] == run()["event_id"]


def test_deep_snapshot_refused_and_missing_holding_refused():
    assert run(snap=b'{"x":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}')["status"] == "REFUSED"
    snap = deepcopy(SNAP)
    snap["positions"][0]["symbol"] = "MSFT"
    assert run(snap=encoded(snap))["reason"] == "NOT_HELD"


def test_import_and_execution_have_only_allowlisted_dependencies():
    source = Path(S.__file__).read_text(encoding="utf-8-sig")
    code = compile(source, S.__file__, "exec")
    original_import = builtins.__import__
    allowed = {"__future__", "hashlib", "json",
               "backend.services.owner_event_warning",
               "backend.services.saved_sec_forecast_input"}

    def guarded_import(name, *args, **kwargs):
        assert name in allowed, name
        return original_import(name, *args, **kwargs)

    def denied(*args, **kwargs):
        raise AssertionError("unexpected IO")

    namespace = {"__name__": "isolated_candidate"}
    with (patch.object(builtins, "__import__", guarded_import),
          patch.object(builtins, "open", denied), patch.object(io, "open", denied),
          patch.object(socket.socket, "connect", denied),
          patch.object(subprocess, "Popen", denied), patch.object(W, "_deliver", denied)):
        exec(code, namespace)
        assert namespace["build_saved_sec_event_path"](
            event_bytes=encoded(ROW), snapshot_bytes=encoded(SNAP), ticker="ACME",
            cutoff_utc=STAMP, decision_utc=STAMP) == run()
