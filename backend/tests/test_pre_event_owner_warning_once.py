"""Offline integration of published calendar receipts, PC selection and journal."""

import base64
from datetime import datetime, timedelta, timezone
import json

import pytest

from backend.services import earnings_calendar_capture as capture
from backend.services import owner_event_warning as journal
from backend.services import telegram_bridge
from scripts import pre_event_owner_warning_once as runner

NOW = datetime(2026, 11, 3, 21, 1, tzinfo=timezone.utc)
ACCOUNT = "APPROVED_PC_PAPER_ACCOUNT"


@pytest.fixture
def case(tmp_path, monkeypatch):
    # Private identity is independently tested in the reviewed capture/journal suites.
    monkeypatch.setattr(journal, "_journal_identity", lambda _path: (1, 1))
    monkeypatch.setattr(capture, "_private_identity", lambda _path: (1, 1))
    receipt_dir = tmp_path / "captured"
    receipt_dir.mkdir()
    receipt_path = receipt_dir / ("earnings-calendar-" + "a" * 32 + ".json")
    row = {"symbol": "DDOG", "date": "2026-11-06", "hour": "amc",
           "quarter": 4, "year": 2026, "epsEstimate": 0.5,
           "epsActual": None, "revenueEstimate": 900000000,
           "revenueActual": None}

    def write_receipt(*, observed="2026-11-03T20:00:00+00:00", rows=None):
        response = json.dumps({"earningsCalendar": rows if rows is not None else [row]},
                              sort_keys=True, separators=(",", ":")).encode()
        from backend.services.saved_earnings_calendar_input import (
            build_saved_earnings_calendar_input,
        )
        packet = build_saved_earnings_calendar_input(
            response, ticker="DDOG", observed_utc=observed, cutoff_utc=observed)
        receipt = {"schema": capture._SCHEMA, "source": capture._SOURCE,
                   "ticker": "DDOG", "from": "2026-11-04", "to": "2026-11-10",
                   "request_utc": observed, "observed_utc": observed,
                   "cutoff_utc": observed, "response_sha256": runner.selector.sha(response),
                   "response_bytes_b64": base64.b64encode(response).decode(),
                   "input_id": packet["input_id"]}
        receipt["receipt_id"] = capture._seal(receipt)
        receipt_path.write_text(json.dumps(receipt))

    write_receipt()
    ledger = tmp_path / "ledger"
    root = ledger / "pc_book"
    root.mkdir(parents=True)
    snapshot_path = root / "state_latest.json"
    # Approved snapshot is newer than the sealed 20:00 capture, as in DDOG.
    snapshot = {"t": "2026-11-03T20:55:00Z", "tag": "sim_owner",
                "account_number": ACCOUNT, "equity": 2000, "cash": 1000,
                "long_market_value": 1000, "short_market_value": 0,
                "n_positions": 1, "positions": [{"symbol": "DDOG", "qty": 10,
                                               "market_value": 1000,
                                               "current_price": 100}]}
    snapshot_path.write_text(json.dumps(snapshot))
    private = tmp_path / "private_journal"
    private.mkdir()
    kwargs = {"receipt_path": receipt_path, "ledger_dir": ledger,
              "expected_account_sha256": runner.selector.sha(ACCOUNT.encode()),
              "journal_dir": private, "now": NOW}
    return kwargs, write_receipt, row, snapshot_path, private


def review(tmp_path):
    path = tmp_path / "independent-review.json"
    path.write_text(json.dumps({
        "schema": "pre-event-warning-review/1",
        "independent_exact_source_review": True, "reviewer": "independent-test-reviewer",
        "sha256": {name: runner.selector.sha(runner.selector.frozen_read(runner.ROOT / name))
                   for name in runner.SOURCE_PATHS},
    }))
    return path


def test_real_style_preview_has_no_transport_or_private_input(case, monkeypatch):
    kwargs, _, _, snapshot_path, private = case
    monkeypatch.setattr(telegram_bridge, "send_owner_once", lambda *_a, **_k: pytest.fail("sent"))
    code, result = runner.run(**kwargs)
    assert code == 0 and result["status"] == "PROVISIONAL"
    assert result["delivery"] == "PREVIEW"
    assert result["ticker"] == "DDOG" and result["event_time_status"] == "UNKNOWN"
    assert result["conditional_loss_usd"]["10_percent_decline"] == "100.00"
    assert result["forecast_status"] == "NO_CALIBRATED_EVENT_FORECAST"
    assert json.loads(snapshot_path.read_text())["t"] > "2026-11-03T20:00:00Z"
    original = json.loads(kwargs["receipt_path"].read_text())
    assert result["receipt_id"] == original["receipt_id"]
    assert result["capture_input_id"] == original["input_id"]
    assert result["receipt_sha256"] == runner.selector.sha(kwargs["receipt_path"].read_bytes())
    assert result["input_id"] != result["capture_input_id"]
    assert not list(private.iterdir())
    output = json.dumps(result)
    assert ACCOUNT not in output and "response_bytes_b64" not in output
    assert "earningsCalendar" not in output and "token" not in output.lower()


@pytest.mark.parametrize("change", ["stale", "future", "ambiguous", "wrong_account"])
def test_bad_evidence_never_sends(case, monkeypatch, change):
    kwargs, write_receipt, row, snapshot_path, _ = case
    if change == "stale":
        write_receipt(observed="2026-11-02T20:00:00+00:00")
    elif change == "future":
        write_receipt(observed="2026-11-03T22:00:00+00:00")
    elif change == "ambiguous":
        write_receipt(rows=[row, row])
    else:
        snapshot = json.loads(snapshot_path.read_text())
        snapshot["account_number"] = "OTHER_PRIVATE_ACCOUNT"
        snapshot_path.write_text(json.dumps(snapshot))
    monkeypatch.setattr(telegram_bridge, "send_owner_once", lambda *_a, **_k: pytest.fail("sent"))
    code, result = runner.run(**kwargs)
    assert code == 2 and result["status"] == "REFUSED"
    assert "OTHER_PRIVATE_ACCOUNT" not in json.dumps(result)


def test_review_mismatch_blocks_sender(case, monkeypatch, tmp_path):
    kwargs, _, _, _, private = case
    gate = review(tmp_path)
    document = json.loads(gate.read_text())
    document["sha256"][runner.SOURCE_PATHS[0]] = "0" * 64
    gate.write_text(json.dumps(document))
    monkeypatch.setattr(telegram_bridge, "send_owner_once", lambda *_a, **_k: pytest.fail("sent"))
    code, result = runner.run(**kwargs, send=True, review=gate)
    assert code == 2 and result["status"] == "REFUSED"
    assert not list(private.iterdir())


def test_review_must_pin_imported_config(case, monkeypatch, tmp_path):
    kwargs, _, _, _, private = case
    assert "backend/config.py" in runner.SOURCE_PATHS
    gate = review(tmp_path)
    document = json.loads(gate.read_text())
    del document["sha256"]["backend/config.py"]
    gate.write_text(json.dumps(document))
    monkeypatch.setattr(telegram_bridge, "send_owner_once", lambda *_a, **_k: pytest.fail("sent"))
    code, result = runner.run(**kwargs, send=True, review=gate)
    assert code == 2 and result["status"] == "REFUSED"
    assert not list(private.iterdir())


@pytest.mark.parametrize("field", ["receipt_id", "input_id"])
def test_tampered_sealed_receipt_refused(case, field):
    kwargs, _, _, _, private = case
    path = kwargs["receipt_path"]
    receipt = json.loads(path.read_text())
    receipt[field] = "0" * 64
    path.write_text(json.dumps(receipt))
    code, result = runner.run(**kwargs)
    assert code == 2 and result["status"] == "REFUSED"
    assert "receipt_id" not in result and not list(private.iterdir())


def test_exact_receipt_file_hash_follows_valid_reencoding(case):
    kwargs, _, _, _, _ = case
    first_code, first = runner.run(**kwargs)
    path = kwargs["receipt_path"]
    path.write_text(path.read_text() + "\n")
    second_code, second = runner.run(**kwargs)
    assert first_code == second_code == 0
    assert first["receipt_id"] == second["receipt_id"]
    assert first["capture_input_id"] == second["capture_input_id"]
    assert first["receipt_sha256"] != second["receipt_sha256"]


def test_no_independent_review_blocks_send(case, monkeypatch):
    kwargs, _, _, _, private = case
    monkeypatch.setattr(telegram_bridge, "send_owner_once", lambda *_a, **_k: pytest.fail("sent"))
    code, result = runner.run(**kwargs, send=True)
    assert code == 2 and result["status"] == "REFUSED"
    assert not list(private.iterdir())


def test_nonnumeric_owner_blocks_send(case, monkeypatch, tmp_path):
    kwargs, _, _, _, private = case
    monkeypatch.setattr(telegram_bridge, "owner_chat_id", lambda: "public-channel")
    monkeypatch.setattr(telegram_bridge, "send_owner_once", lambda *_a, **_k: pytest.fail("sent"))
    code, result = runner.run(**kwargs, send=True, review=review(tmp_path))
    assert code == 2 and result["status"] == "REFUSED"
    assert not list(private.iterdir())


@pytest.mark.parametrize("outcome", ["sent", "unknown", "bad_ack", "interrupt"])
def test_single_attempt_and_refreshed_snapshot_duplicate(case, monkeypatch, tmp_path, outcome):
    kwargs, _, _, snapshot_path, private = case
    gate = review(tmp_path)
    monkeypatch.setattr(telegram_bridge, "owner_chat_id", lambda: "123456")
    calls = []

    def sender(text, *, tag, expected_owner, until):
        calls.append(text)
        assert expected_owner == "123456" and until > runner.time.time()
        pending = json.loads(next(private.glob("*.json")).read_text())
        assert pending["state"] == "SENDING" and pending["tag_sha256"] == journal._digest({"tag": tag})
        receipt = json.loads(kwargs["receipt_path"].read_text())
        artifact = pending["artifact"]
        assert artifact["receipt_id"] == receipt["receipt_id"]
        assert artifact["capture_input_id"] == receipt["input_id"]
        assert artifact["receipt_sha256"] == runner.selector.sha(kwargs["receipt_path"].read_bytes())
        assert artifact["input_id"] != artifact["capture_input_id"]
        for key in ("receipt_id", "capture_input_id", "receipt_sha256", "input_id"):
            assert artifact[key] in text
        assert "Finnhub earnings calendar OBSERVED" in text
        assert "scheduled ET date" in text and "event time UNKNOWN" in text
        assert "No calibrated forecast, price direction, probability, or new allocation" in text
        assert ACCOUNT not in text and "earningsCalendar" not in text
        if outcome == "unknown":
            raise TimeoutError("simulated transport uncertainty")
        if outcome == "interrupt":
            raise KeyboardInterrupt("simulated interruption")
        ack = {"state": "SENT", "messages": 1, "native_ack_sha256": "f" * 64,
               "tag_sha256": journal._digest({"tag": tag}),
               "text_sha256": journal._hash(text)}
        ack["delivery_binding_sha256"] = journal._digest({
            key: ack[key] for key in journal._ACK_HASH_KEYS})
        if outcome == "bad_ack":
            ack["text_sha256"] = "0" * 64
        return ack

    monkeypatch.setattr(telegram_bridge, "send_owner_once", sender)
    if outcome == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            runner.run(**kwargs, send=True, review=gate)
    else:
        code, result = runner.run(**kwargs, send=True, review=gate)
        assert code == (0 if outcome == "sent" else 2)
        assert result["delivery"] == ("SENT" if outcome == "sent"
                                      else "UNKNOWN_RECONCILE_REQUIRED")
    snapshot = json.loads(snapshot_path.read_text())
    snapshot["t"] = "2026-11-03T20:56:00Z"
    snapshot_path.write_text(json.dumps(snapshot))
    kwargs["now"] += timedelta(minutes=1)
    code, result = runner.run(**kwargs, send=True, review=gate)
    assert code == (0 if outcome == "sent" else 2)
    assert result["delivery"] == ("ALREADY_SENT" if outcome == "sent"
                                  else "DUPLICATE_RECONCILE_REQUIRED")
    assert len(calls) == 1


def test_journal_receipt_identity_tamper_blocks_confirmed_replay(case, monkeypatch, tmp_path):
    kwargs, _, _, _, private = case
    monkeypatch.setattr(telegram_bridge, "owner_chat_id", lambda: "123456")
    calls = []

    def sender(text, *, tag, **_kwargs):
        calls.append(text)
        ack = {"state": "SENT", "messages": 1, "native_ack_sha256": "f" * 64,
               "tag_sha256": journal._digest({"tag": tag}),
               "text_sha256": journal._hash(text)}
        ack["delivery_binding_sha256"] = journal._digest({
            key: ack[key] for key in journal._ACK_HASH_KEYS})
        return ack

    monkeypatch.setattr(telegram_bridge, "send_owner_once", sender)
    gate = review(tmp_path)
    assert runner.run(**kwargs, send=True, review=gate)[1]["delivery"] == "SENT"
    path = next(path for path in private.glob("*.json") if not path.name.endswith(".result.json"))
    record = json.loads(path.read_text())
    record["artifact"]["receipt_id"] = "0" * 64
    path.write_text(json.dumps(record))
    code, result = runner.run(**kwargs, send=True, review=gate)
    assert code == 2 and result["delivery"] == "DUPLICATE_RECONCILE_REQUIRED"
    assert len(calls) == 1


@pytest.mark.parametrize("clock,allowed", [
    (datetime(2026, 11, 4, 8, 29, 59, tzinfo=timezone.utc), True),
    (datetime(2026, 11, 4, 8, 30, tzinfo=timezone.utc), False),
    (datetime(2026, 11, 4, 9, 4, 59, tzinfo=timezone.utc), False),
    (datetime(2026, 11, 4, 9, 5, tzinfo=timezone.utc), True),
])
def test_iif_boundary(clock, allowed):
    if allowed:
        assert runner._check_window(clock) > 0
    else:
        with pytest.raises(runner.Refused, match="IIF_WINDOW_DEFER"):
            runner._check_window(clock)
