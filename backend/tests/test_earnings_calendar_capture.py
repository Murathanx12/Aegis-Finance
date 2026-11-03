"""All transport responses are synthetic; no test contacts Finnhub."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from backend.services import earnings_calendar_capture as C
from backend.services.saved_earnings_calendar_input import MAX_BYTES

TOKEN = "secret-finnhub-token"
RAW = json.dumps({"earningsCalendar": [{
    "symbol": "AAPL", "date": "2026-11-06", "hour": "amc",
    "quarter": 4, "year": 2026, "epsEstimate": 1.5,
    "revenueEstimate": 1000,
}]}).encode()
NOW = datetime(2026, 11, 3, 20, tzinfo=timezone.utc)


class Response:
    def __init__(self, raw=RAW, status=200, content_type="application/json"):
        self.content = raw
        self.status_code = status
        self.headers = {"Content-Type": content_type}


def private_dir(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    return directory


def capture(directory, transport, clock=lambda: NOW, **changes):
    arguments = dict(ticker="AAPL", start="2026-11-03", end="2026-11-10",
                     cutoff_utc="2026-11-03T21:00:00Z", private_dir=directory,
                     transport=transport, clock=clock, api_key=TOKEN)
    arguments.update(changes)
    return C.capture_earnings_calendar(**arguments)


def test_only_explicit_call_fetches_once_and_freezes_receipt(tmp_path, caplog):
    directory = private_dir(tmp_path)
    calls = []
    sequence = []

    def transport(url, *, params, timeout):
        calls.append((url, params, timeout))
        sequence.append("response")
        return Response()

    def clock():
        sequence.append("clock")
        return NOW

    assert calls == []
    result = capture(directory, transport, clock)
    assert len(calls) == 1
    assert calls[0] == ("https://finnhub.io/api/v1/calendar/earnings",
                        {"symbol": "AAPL", "from": "2026-11-03",
                         "to": "2026-11-10", "token": TOKEN}, 10)
    assert sequence == ["response", "clock"]
    packet = result["packet"]
    receipt = json.loads(result["receipt_path"].read_bytes())
    assert packet["status"] == "EVIDENCE_ONLY"
    assert receipt["observed_utc"] == packet["observed_utc"] == NOW.isoformat()
    assert receipt["response_sha256"] == hashlib.sha256(RAW).hexdigest()
    assert receipt["input_id"] == packet["input_id"]
    assert TOKEN not in result["receipt_path"].read_text()
    assert RAW not in result["receipt_path"].read_bytes()
    assert TOKEN not in caplog.text

    # A later read uses the same original clock; no network or clock is involved.
    cached = C.evaluate_saved_capture(receipt, RAW, cutoff_utc="2026-11-04T21:00:01Z")
    assert cached["status"] == "REFUSED"
    assert cached["reason"] == "OBSERVATION_STALE"
    assert receipt["observed_utc"] == NOW.isoformat()
    assert len(calls) == 1


@pytest.mark.parametrize("response,reason", [
    (Response(status=429), "HTTP_NON_200"),
    (Response(content_type="text/html"), "CONTENT_TYPE_INVALID"),
    (Response(raw=b""), "RESPONSE_BYTES_INVALID"),
    (Response(raw=b"x" * (MAX_BYTES + 1)), "RESPONSE_BYTES_INVALID"),
    (Response(raw=b"{"), "JSON_INVALID"),
    (Response(raw=b'{"earningsCalendar":[]}'), "CALENDAR_EMPTY"),
    (Response(raw=b'{"earningsCalendar":[{"symbol":"MSFT"}]}'), "NO_MATCHING_TICKER"),
    (Response(raw=json.dumps({"earningsCalendar": [
        {"symbol": "AAPL", "date": "2026-11-06", "hour": "amc",
         "quarter": 4, "year": 2026, "epsEstimate": 1, "revenueEstimate": 2},
        {"symbol": "AAPL", "date": "2026-11-07", "hour": "amc",
         "quarter": 1, "year": 2027, "epsEstimate": 1, "revenueEstimate": 2},
    ]}).encode()), "AMBIGUOUS_EVENT"),
])
def test_response_refusals_leave_no_success_receipt(tmp_path, response, reason):
    directory = private_dir(tmp_path)
    with pytest.raises(C.CaptureRefused, match=f"^{reason}$"):
        capture(directory, lambda *_args, **_kwargs: response)
    assert list(directory.iterdir()) == []


def test_key_directory_and_transport_fail_closed_without_secret(tmp_path, caplog):
    directory = private_dir(tmp_path)
    calls = []

    def transport(*_args, **_kwargs):
        calls.append(1)
        raise RuntimeError(f"URL ?token={TOKEN} failed")

    with pytest.raises(C.CaptureRefused, match="^FINNHUB_KEY_ABSENT$"):
        capture(directory, transport, api_key="")
    assert not calls
    with pytest.raises(C.CaptureRefused, match="^PRIVATE_DIRECTORY_REQUIRED$"):
        capture(tmp_path / "missing", transport)
    assert not calls
    with pytest.raises(C.CaptureRefused) as error:
        capture(directory, transport)
    assert str(error.value) == "FETCH_FAILED"
    assert TOKEN not in str(error.value) + caplog.text
    assert list(directory.iterdir()) == []


def test_private_directory_rejection_precedes_network(tmp_path, monkeypatch):
    directory = private_dir(tmp_path)
    calls = []

    def rejected(_path):
        raise OSError("insecure ACL")

    monkeypatch.setattr(C, "_journal_identity", rejected)
    with pytest.raises(C.CaptureRefused, match="^PRIVATE_DIRECTORY_REQUIRED$"):
        capture(directory, lambda *_args, **_kwargs: calls.append(1))
    assert calls == []
    assert list(directory.iterdir()) == []


def test_existing_name_is_never_overwritten(tmp_path, monkeypatch):
    directory = private_dir(tmp_path)
    class FixedId:
        hex = "same"

    monkeypatch.setattr(C.uuid, "uuid4", lambda: FixedId())
    first = capture(directory, lambda *_args, **_kwargs: Response())
    path = first["receipt_path"]
    before = path.read_bytes()
    with pytest.raises(C.CaptureRefused, match="^RECEIPT_EXISTS$"):
        capture(directory, lambda *_args, **_kwargs: Response())
    assert path.read_bytes() == before
    assert list(directory.iterdir()) == [path]


def test_saved_bytes_cannot_be_substituted(tmp_path):
    directory = private_dir(tmp_path)
    path = capture(directory, lambda *_args, **_kwargs: Response())["receipt_path"]
    receipt = json.loads(Path(path).read_text())
    with pytest.raises(C.CaptureRefused, match="^SAVED_CAPTURE_INVALID$"):
        C.evaluate_saved_capture(receipt, RAW + b" ", cutoff_utc="2026-11-03T21:00:00Z")
    receipt["observed_utc"] = "2026-11-03T20:59:59+00:00"
    with pytest.raises(C.CaptureRefused, match="^SAVED_CAPTURE_INVALID$"):
        C.evaluate_saved_capture(receipt, RAW, cutoff_utc="2026-11-03T21:00:00Z")
