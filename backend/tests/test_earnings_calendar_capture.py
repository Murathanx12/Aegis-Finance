"""All transport responses are synthetic; no test contacts Finnhub."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback

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
        self.raw = raw
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.closed = False

    def iter_content(self, chunk_size):
        for start in range(0, len(self.raw), chunk_size):
            yield self.raw[start:start + chunk_size]

    def close(self):
        self.closed = True


def private_dir(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    return directory


def capture(directory, transport, clock=lambda: NOW, **changes):
    arguments = dict(ticker="AAPL", start="2026-11-04", end="2026-11-10",
                     cutoff_utc="2026-11-03T19:59:00Z", private_dir=directory,
                     transport=transport, clock=clock, api_key=TOKEN)
    arguments.update(changes)
    return C.capture_earnings_calendar(**arguments)


def test_only_explicit_call_fetches_once_and_freezes_receipt(tmp_path, caplog):
    directory = private_dir(tmp_path)
    calls = []
    sequence = []

    def transport(url, *, params, timeout, stream):
        calls.append((url, params, timeout, stream))
        sequence.append("response")
        return Response()

    def clock():
        sequence.append("clock")
        return NOW

    assert calls == []
    result = capture(directory, transport, clock)
    assert len(calls) == 1
    assert calls[0] == ("https://finnhub.io/api/v1/calendar/earnings",
                        {"symbol": "AAPL", "from": "2026-11-04",
                         "to": "2026-11-10", "token": TOKEN}, (3, 5), True)
    assert sequence == ["response", "clock"]
    packet = result["packet"]
    receipt = json.loads(result["receipt_path"].read_bytes())
    assert packet["status"] == "EVIDENCE_ONLY"
    assert receipt["observed_utc"] == packet["observed_utc"] == NOW.isoformat()
    assert receipt["request_utc"] == "2026-11-03T19:59:00Z"
    assert receipt["cutoff_utc"] == packet["cutoff_utc"] == NOW.isoformat()
    assert receipt["response_sha256"] == hashlib.sha256(RAW).hexdigest()
    assert receipt["input_id"] == packet["input_id"]
    assert base64.b64decode(receipt["response_bytes_b64"]) == RAW
    assert TOKEN not in result["receipt_path"].read_text()
    assert TOKEN not in caplog.text

    # A later read uses the same original clock; no network or clock is involved.
    cached = C.evaluate_saved_capture(receipt, RAW, cutoff_utc="2026-11-04T21:00:01Z")
    assert cached["status"] == "REFUSED"
    assert cached["reason"] == "OBSERVATION_STALE"
    assert receipt["observed_utc"] == NOW.isoformat()
    assert len(calls) == 1
    assert C.replay_earnings_calendar(
        result["receipt_path"], cutoff_utc="2026-11-04T21:00:01Z",
    )["reason"] == "OBSERVATION_STALE"


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
    assert error.value.__context__ is None
    formatted = "".join(traceback.format_exception(error.value))
    assert TOKEN not in str(error.value) + caplog.text + formatted
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


@pytest.mark.parametrize("start,end,cutoff", [
    ("2026-11-03", "2026-11-10", "2026-11-03T21:00:00Z"),
    ("2026-11-04", "2026-11-11", "2026-11-03T21:00:00Z"),
    ("2026-11-04", "2026-11-10", "2026-11-04T05:00:00Z"),
])
def test_date_window_refuses_before_network(tmp_path, start, end, cutoff):
    directory = private_dir(tmp_path)
    calls = []
    with pytest.raises(C.CaptureRefused, match="^DATE_RANGE_INVALID$"):
        capture(directory, lambda *_a, **_k: calls.append(1),
                start=start, end=end, cutoff_utc=cutoff)
    assert not calls and not list(directory.iterdir())


def test_stream_deadline_and_oversize_leave_no_receipt(tmp_path):
    directory = private_dir(tmp_path)
    ticks = iter((0, 16))
    with pytest.raises(C.CaptureRefused, match="^TOTAL_DEADLINE_EXCEEDED$"):
        capture(directory, lambda *_a, **_k: Response(), monotonic=lambda: next(ticks))
    assert list(directory.iterdir()) == []
    with pytest.raises(C.CaptureRefused, match="^RESPONSE_BYTES_INVALID$"):
        capture(directory, lambda *_a, **_k: Response(raw=b"x" * (MAX_BYTES + 8192)))
    assert list(directory.iterdir()) == []


def test_partial_write_is_removed_before_publish(tmp_path, monkeypatch):
    directory = private_dir(tmp_path)

    def fail_fsync(_fd):
        raise OSError("disk failed")

    monkeypatch.setattr(C.os, "fsync", fail_fsync)
    with pytest.raises(C.CaptureRefused, match="^RECEIPT_WRITE_FAILED$"):
        capture(directory, lambda *_a, **_k: Response())
    assert list(directory.iterdir()) == []


def test_observed_private_dir_swap_refuses_before_publish(tmp_path, monkeypatch):
    directory = private_dir(tmp_path)
    original = C._private_identity
    checks = 0

    def swapped(path):
        nonlocal checks
        checks += 1
        identity = original(path)
        return identity if checks < 3 else (identity[0], identity[1] + 1)

    monkeypatch.setattr(C, "_private_identity", swapped)
    with pytest.raises(C.CaptureRefused, match="^PRIVATE_DIRECTORY_CHANGED$"):
        capture(directory, lambda *_a, **_k: Response())
    assert checks >= 3
    assert list(directory.iterdir()) == []


def test_replay_in_fresh_process_needs_only_receipt_path(tmp_path):
    directory = private_dir(tmp_path)
    path = capture(directory, lambda *_a, **_k: Response())["receipt_path"]
    script = ("import sys; from backend.services.earnings_calendar_capture "
              "import replay_earnings_calendar; "
              "print(replay_earnings_calendar(sys.argv[1], "
              "cutoff_utc='2026-11-04T21:00:01Z')['reason'])")
    result = subprocess.run([sys.executable, "-c", script, str(path)],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "OBSERVATION_STALE"


def test_token_echo_is_refused_without_receipt(tmp_path):
    directory = private_dir(tmp_path)
    payload = json.loads(RAW)
    payload["earningsCalendar"].append({"symbol": "MSFT", "note": TOKEN})
    raw = json.dumps(payload).encode()
    with pytest.raises(C.CaptureRefused, match="^TOKEN_IN_RESPONSE$"):
        capture(directory, lambda *_a, **_k: Response(raw=raw))
    assert list(directory.iterdir()) == []


def test_observation_follows_last_body_byte_and_stream_error_is_sanitized(tmp_path):
    directory = private_dir(tmp_path)
    order = []

    class TracedResponse(Response):
        def iter_content(self, chunk_size):
            yield from super().iter_content(chunk_size)
            order.append("body_complete")

    def clock():
        order.append("observed")
        return NOW

    capture(directory, lambda *_a, **_k: TracedResponse(), clock=clock)
    assert order == ["body_complete", "observed"]

    class FailingResponse(Response):
        def iter_content(self, chunk_size):
            yield b"{"
            raise RuntimeError(f"URL ?token={TOKEN} stream broke")

    with pytest.raises(C.CaptureRefused) as error:
        capture(directory, lambda *_a, **_k: FailingResponse())
    assert error.value.__context__ is None
    assert TOKEN not in "".join(traceback.format_exception(error.value))
    assert len(list(directory.glob("*.json"))) == 1


@pytest.mark.parametrize("field,value", [
    ("source", "other/calendar/earnings"),
    ("from", "2026-11-05"),  # Still inside the allowed window.
    ("to", "2026-11-09"),
    ("request_utc", "2026-11-03T19:58:00Z"),
    ("cutoff_utc", "2026-11-03T20:00:01+00:00"),
])
def test_replay_rejects_metadata_tampering(tmp_path, field, value):
    directory = private_dir(tmp_path)
    path = capture(directory, lambda *_a, **_k: Response())["receipt_path"]
    receipt = json.loads(path.read_bytes())
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(C.CaptureRefused, match="^SAVED_CAPTURE_INVALID$"):
        C.replay_earnings_calendar(path, cutoff_utc="2026-11-03T21:00:00Z")


@pytest.mark.parametrize("field,value", [
    ("source", "other/calendar/earnings"),
    ("from", "2026-11-03"),  # Same-day ET is outside the allowed range.
    ("to", "2026-11-11"),
    ("request_utc", "2026-11-03T20:00:01Z"),
    ("cutoff_utc", "2026-11-03T20:00:01+00:00"),
])
def test_replay_enforces_source_and_range_even_with_recomputed_seal(
    tmp_path, field, value,
):
    directory = private_dir(tmp_path)
    path = capture(directory, lambda *_a, **_k: Response())["receipt_path"]
    receipt = json.loads(path.read_bytes())
    receipt[field] = value
    receipt["receipt_id"] = C._seal(receipt)
    path.write_text(json.dumps(receipt))
    with pytest.raises(C.CaptureRefused, match="^SAVED_CAPTURE_INVALID$"):
        C.replay_earnings_calendar(path, cutoff_utc="2026-11-03T21:00:00Z")


def test_complete_unpublished_temp_is_not_replayable(tmp_path):
    directory = private_dir(tmp_path)
    path = capture(directory, lambda *_a, **_k: Response())["receipt_path"]
    temp = directory / path.name.replace("earnings-calendar-", ".earnings-calendar-")
    temp = temp.with_suffix(".tmp")
    temp.write_bytes(path.read_bytes())
    with pytest.raises(C.CaptureRefused, match="^SAVED_CAPTURE_INVALID$"):
        C.replay_earnings_calendar(temp, cutoff_utc="2026-11-03T21:00:00Z")
    assert C.replay_earnings_calendar(path, cutoff_utc="2026-11-03T21:00:00Z")["status"] == (
        "EVIDENCE_ONLY"
    )


@pytest.mark.parametrize("stage", ["adapter", "fsync", "publish"])
def test_deadline_during_validation_or_write_never_leaves_receipt(
    tmp_path, monkeypatch, stage,
):
    directory = private_dir(tmp_path)
    elapsed = [0.0]
    if stage == "adapter":
        original = C.build_saved_earnings_calendar_input

        def late_adapter(*args, **kwargs):
            result = original(*args, **kwargs)
            elapsed[0] = 16.0
            return result

        monkeypatch.setattr(C, "build_saved_earnings_calendar_input", late_adapter)
    elif stage == "fsync":
        original = C.os.fsync

        def late_fsync(fd):
            original(fd)
            elapsed[0] = 16.0

        monkeypatch.setattr(C.os, "fsync", late_fsync)
    else:
        original = C.os.link

        def late_link(source, target):
            original(source, target)
            elapsed[0] = 16.0

        monkeypatch.setattr(C.os, "link", late_link)
    with pytest.raises(C.CaptureRefused, match="^TOTAL_DEADLINE_EXCEEDED$"):
        capture(directory, lambda *_a, **_k: Response(), monotonic=lambda: elapsed[0])
    assert list(directory.iterdir()) == []


def test_delayed_body_uses_actual_observation_as_first_packet_cutoff(tmp_path):
    directory = private_dir(tmp_path)
    request = datetime(2026, 11, 3, 19, 59, 59, tzinfo=timezone.utc)
    observed = request + timedelta(seconds=4)
    wall = [request]
    calls = []

    class DelayedResponse(Response):
        def iter_content(self, chunk_size):
            yield from super().iter_content(chunk_size)
            wall[0] = observed

    def transport(_url, *, params, timeout, stream):
        calls.append((params["symbol"], timeout, stream))
        return DelayedResponse()

    result = capture(directory, transport, clock=lambda: wall[0],
                     cutoff_utc=request.isoformat())
    receipt = json.loads(result["receipt_path"].read_bytes())
    assert calls == [("AAPL", (3, 5), True)]
    assert receipt["request_utc"] == request.isoformat()
    assert receipt["observed_utc"] == observed.isoformat()
    assert receipt["cutoff_utc"] == result["packet"]["cutoff_utc"] == observed.isoformat()
    assert result["packet"]["status"] == "EVIDENCE_ONLY"
    assert C.replay_earnings_calendar(
        result["receipt_path"], cutoff_utc=request.isoformat(),
    )["reason"] == "OBSERVATION_AFTER_CUTOFF"
    assert C.replay_earnings_calendar(
        result["receipt_path"], cutoff_utc=(observed + timedelta(minutes=1)).isoformat(),
    )["status"] == "EVIDENCE_ONLY"


def test_et_midnight_crossing_refuses_without_receipt(tmp_path):
    directory = private_dir(tmp_path)
    request = datetime(2026, 11, 4, 4, 59, 59, tzinfo=timezone.utc)
    observed = request + timedelta(seconds=2)
    with pytest.raises(C.CaptureRefused, match="^ET_DATE_CHANGED_DURING_CAPTURE$"):
        capture(directory, lambda *_a, **_k: Response(),
                cutoff_utc=request.isoformat(), clock=lambda: observed)
    assert list(directory.iterdir()) == []


def test_request_clock_after_observation_refuses_without_receipt(tmp_path):
    directory = private_dir(tmp_path)
    request = NOW + timedelta(seconds=1)
    with pytest.raises(C.CaptureRefused, match="^REQUEST_AFTER_OBSERVATION$"):
        capture(directory, lambda *_a, **_k: Response(), cutoff_utc=request.isoformat())
    assert list(directory.iterdir()) == []
