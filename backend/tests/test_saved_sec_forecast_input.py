"""Offline contract tests; synthetic Apple-shaped row, not a native capture."""
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

from backend.services import saved_sec_forecast_input as S

CUTOFF = "2026-11-03T16:08:33Z"


def row(**changes):
    value = {
        "source": "sec_edgar_8k_ex99_body", "tickers": ["AAPL"],
        "title": "8-K - Apple Inc. (0000320193) (Filer) - EX-99.1",
        "url": "https://www.sec.gov/Archives/edgar/data/320193/"
               "000032019326000024/a8-kex991q4202609262026.htm",
        "raw_id": "0000320193-26-000024:a8-kex991q4202609262026.htm",
        "published_utc": "2026-11-02T21:30:23+00:00",
        "first_seen_utc": "2026-11-02T22:50:13+00:00",
        "body": "Apple reports fourth quarter results. Revenue $114.5 billion.",
    }
    value.update(changes)
    return (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8")


def build(raw=None, **kwargs):
    return S.build_saved_sec_input(row() if raw is None else raw,
                                  ticker=kwargs.pop("ticker", "AAPL"),
                                  cutoff_utc=kwargs.pop("cutoff_utc", CUTOFF), **kwargs)


def test_apple_clock_replay_and_exact_bytes():
    raw = row()
    packet = build(raw)
    assert packet["status"] == "EVIDENCE_ONLY"
    assert packet["runtime_authority"] == "NONE"
    assert packet["forecast_status"] == "NOT_GENERATED"
    evidence = packet["evidence"]
    assert evidence["accession"] == "0000320193-26-000024"
    assert evidence["source_row_utf8"].encode("utf-8") == raw
    assert evidence["row_sha256"] == hashlib.sha256(raw).hexdigest()
    for key in ("url", "body", "published_utc", "first_seen_utc"):
        assert evidence[key] == json.loads(raw)[key]
    unsigned = {k: v for k, v in packet.items() if k != "packet_sha256"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode()
    assert packet["packet_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert S.verify_saved_sec_input(packet, raw, ticker="AAPL", cutoff_utc=CUTOFF)


def test_before_first_seen_excluded_and_boundary_included():
    assert build(cutoff_utc="2026-11-02T22:50:12Z")["reason"] == "NOT_AVAILABLE_AT_CUTOFF"
    assert build(cutoff_utc="2026-11-02T22:50:13Z")["status"] == "EVIDENCE_ONLY"
    assert build(cutoff_utc="2026-11-02T21:30:22Z")["reason"] == "NOT_AVAILABLE_AT_CUTOFF"


def test_exact_duplicates_are_idempotent_and_order_independent():
    raw = row()
    other = row(tickers=["MSFT"])
    assert build(raw) == build(raw + raw) == build(other + raw) == build(raw + other)
    assert build(raw) == build(raw, cutoff_utc="2026-11-03T16:08:33+00:00")


@pytest.mark.parametrize("changed", [
    row(body="Altered report"), row().replace(b"\n", b"\r\n"), row().rstrip(b"\n"),
    row().replace(b'"source": ', b'"source":  '),
])
def test_altered_bytes_invalidate_original_packet(changed):
    original = build()
    updated = build(changed)
    assert updated["status"] == "EVIDENCE_ONLY"
    assert updated["packet_sha256"] != original["packet_sha256"]
    assert not S.verify_saved_sec_input(original, changed, ticker="AAPL", cutoff_utc=CUTOFF)
    assert build(row() + changed)["reason"] == "CONFLICTING_EVENT_BYTES"


def test_packet_tampering_and_changed_context_invalidate():
    packet = build()
    tampered = deepcopy(packet)
    tampered["evidence"]["body"] = "Altered"
    assert not S.verify_saved_sec_input(tampered, row(), ticker="AAPL", cutoff_utc=CUTOFF)
    assert not S.verify_saved_sec_input(packet, row(), ticker="MSFT", cutoff_utc=CUTOFF)
    assert not S.verify_saved_sec_input(packet, row(), ticker="AAPL",
                                       cutoff_utc="2026-11-03T16:08:34Z")
    refused = build(cutoff_utc="2026-11-01T00:00:00Z")
    assert not S.verify_saved_sec_input(refused, row(), ticker="AAPL",
                                       cutoff_utc="2026-11-01T00:00:00Z")


@pytest.mark.parametrize("cutoff", [None, "2026-11-03", "2026-11-03T16:08:33",
                                    "2026-11-03T16:08:33+08:00", "2026-02-30T00:00:00Z"])
def test_explicit_valid_utc_cutoff_required(cutoff):
    assert build(cutoff_utc=cutoff)["reason"] == "CUTOFF_INVALID"


@pytest.mark.parametrize("changes,reason", [
    ({"source": "other"}, "UNSUPPORTED_SOURCE_OR_TICKER_BINDING"),
    ({"tickers": ["AAPL", "MSFT"]}, "UNSUPPORTED_SOURCE_OR_TICKER_BINDING"),
    ({"title": "Apple headline"}, "SEC_IDENTITY_INVALID"),
    ({"raw_id": "0000000000-26-000024:x.htm"}, "SEC_IDENTITY_INVALID"),
    ({"url": "https://www.sec.gov.evil.test/Archives/x.htm"}, "SEC_IDENTITY_INVALID"),
    ({"url": "http://www.sec.gov/Archives/x.htm"}, "SEC_IDENTITY_INVALID"),
    ({"body": " "}, "BODY_MISSING"),
    ({"published_utc": None}, "SOURCE_CLOCK_INVALID"),
    ({"first_seen_utc": "2026-11-02T22:50:13"}, "SOURCE_CLOCK_INVALID"),
    ({"first_seen_utc": "2026-11-02T20:00:00Z"}, "SOURCE_CLOCK_ORDER_INVALID"),
])
def test_refusals(changes, reason):
    assert build(row(**changes))["reason"] == reason


def test_distinct_documents_ambiguous_and_future_version_excluded():
    later = row(raw_id="0000320193-26-000025:next.htm",
                url="https://www.sec.gov/Archives/edgar/data/320193/000032019326000025/next.htm")
    assert build(row() + later)["reason"] == "AMBIGUOUS_EVENT"
    future = row(body="Later version", first_seen_utc="2026-11-04T00:00:00Z")
    assert build(row() + future) == build()


@pytest.mark.parametrize("raw", [b"{", b"[]\n", b'{}\n', b'\xff\n',
                                b'{"tickers":[],"x":NaN}',
                                b'{"tickers":[],"tickers":["AAPL"]}'])
def test_bad_json_refuses(raw):
    assert build(raw)["status"] == "REFUSED"


def test_bounds_and_missing_event():
    assert build(b"")["reason"] == "INPUT_BYTES_INVALID_OR_TOO_LARGE"
    assert build(b" " * (S.MAX_BYTES + 1))["reason"] == "INPUT_BYTES_INVALID_OR_TOO_LARGE"
    assert build(row() * (S.MAX_ROWS + 1))["reason"] == "TOO_MANY_ROWS"
    assert build(row(tickers=["MSFT"]))["reason"] == "NO_MATCHING_EVENT"
    assert build(ticker="aapl")["reason"] == "TICKER_INVALID"
    assert build(bytearray(row()))["reason"] == "INPUT_BYTES_INVALID_OR_TOO_LARGE"


def test_zero_io_models_or_imported_runtime_dependencies():
    raw = row()
    expected = build(raw)
    original_import = builtins.__import__

    def denied(*args, **kwargs):
        raise AssertionError("adapter attempted IO/model/runtime access")

    def guarded_import(name, *args, **kwargs):
        if name.startswith(("backend", "scripts", "openai", "requests", "httpx")):
            denied()
        return original_import(name, *args, **kwargs)

    with (patch.object(builtins, "open", denied), patch.object(io, "open", denied),
          patch.object(Path, "open", denied), patch.object(socket.socket, "connect", denied),
          patch.object(socket, "create_connection", denied),
          patch.object(subprocess, "Popen", denied),
          patch.object(builtins, "__import__", guarded_import)):
        assert build(raw) == expected
        assert S.verify_saved_sec_input(expected, raw, ticker="AAPL", cutoff_utc=CUTOFF)
        assert build(b"bad")["status"] == "REFUSED"
    assert "backend.services.telegram_bridge" not in S.__dict__


def test_module_import_has_no_side_effects():
    # Execute only this module's source with a fresh namespace; reading it is
    # test setup, before the IO barrier. No application modules are imported.
    source = Path(S.__file__).read_text(encoding="utf-8")
    code = compile(source, S.__file__, "exec")
    namespace = {"__name__": "saved_sec_input_isolation_test"}

    def denied(*args, **kwargs):
        raise AssertionError("unexpected IO")

    with (patch.object(builtins, "open", denied), patch.object(io, "open", denied),
          patch.object(socket.socket, "connect", denied),
          patch.object(socket, "create_connection", denied),
          patch.object(subprocess, "Popen", denied)):
        exec(code, namespace)
    assert namespace["build_saved_sec_input"](row(), ticker="AAPL", cutoff_utc=CUTOFF) == build()


@pytest.mark.parametrize('mutation', [None, 'title', 'subject', 'directory', 'filename', 'ticker'])
def test_distinct_login_issuer_identity_contract(mutation):
    value = json.loads(row())
    value['raw_id'] = value['raw_id'].replace('0000320193-26', '0001193125-26')
    value['url'] = value['url'].replace('000032019326', '000119312526')
    if mutation == 'title':
        value['title'] = value['title'].replace('0000320193', '0000000002')
    elif mutation == 'subject':
        value['url'] = value['url'].replace('/320193/', '/2/')
    elif mutation == 'directory':
        value['url'] = value['url'].replace('26000024/', '26000025/')
    elif mutation == 'filename':
        value['raw_id'] = value['raw_id'].split(':')[0] + ':other.htm'
    elif mutation == 'ticker':
        value['tickers'] = ['AAPL', 'OTHER']
    packet = build((json.dumps(value) + '\n').encode())
    assert packet['status'] == ('EVIDENCE_ONLY' if mutation is None else 'REFUSED')
