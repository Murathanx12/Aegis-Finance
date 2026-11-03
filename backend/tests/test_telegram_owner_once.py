"""Offline contract tests for the bounded owner delivery sidecar."""
import hashlib
import json
from unittest.mock import Mock

import pytest

from backend.services import telegram_bridge as bridge


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv(bridge.OWNER_ENV, "123456")
    monkeypatch.setattr(bridge, "OUTBOX_PATH", tmp_path / "outbox.jsonl")
    call = Mock(return_value={"message_id": 7, "chat": {"id": 123456, "type": "private"}})
    monkeypatch.setattr(bridge, "_call", call)
    monkeypatch.setattr(bridge.urllib.request, "urlopen", Mock(side_effect=AssertionError("network forbidden")))
    return call


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_success_redacts_binds_and_durably_records(isolated, monkeypatch):
    sync = Mock()
    monkeypatch.setattr(bridge.os, "fsync", sync)
    text = "API_TOKEN=synthetic-placeholder"
    ack = bridge.send_owner_once(text, tag="event:one", expected_owner="123456")
    isolated.assert_called_once_with("sendMessage", {
        "chat_id": "123456", "text": bridge.redact(text), "disable_web_page_preview": True,
    }, timeout=30.0)
    assert ack["native_ack_sha256"] == digest({"schema": "telegram-native-ack/1", "owner": "123456", "message_id": 7})
    assert ack["tag_sha256"] == digest({"tag": "event:one"})
    assert ack["text_sha256"] == hashlib.sha256(bridge.redact(text).encode()).hexdigest()
    assert ack["delivery_binding_sha256"] == digest({k: ack[k] for k in (
        "native_ack_sha256", "tag_sha256", "text_sha256")})
    raw = bridge.OUTBOX_PATH.read_text()
    row = json.loads(raw)
    assert row == {"t": row["t"], "chat": "owner", "chars": len(bridge.redact(text)), **ack}
    assert "123456" not in raw and "synthetic-placeholder" not in raw and "event:one" not in raw
    sync.assert_called_once()


@pytest.mark.parametrize("owner", ["", "-123", "0", "@owner", "\uff11\uff12\uff13", "00123"])
def test_invalid_owner_never_sends(owner, monkeypatch, isolated):
    monkeypatch.setenv(bridge.OWNER_ENV, owner)
    with pytest.raises(bridge.TelegramRefused, match="NUMERIC_PRIVATE_OWNER_REQUIRED"):
        bridge.send_owner_once("hello")
    isolated.assert_not_called()


@pytest.mark.parametrize("kwargs,reason", [
    ({"expected_owner": "999"}, "OWNER_CHANGED"),
    ({"tag": "bad tag"}, "OPAQUE_DELIVERY_TAG"),
    ({"tag": "x" * 129}, "OPAQUE_DELIVERY_TAG"),
    ({"until": 10, "clock": lambda: 10}, "HARD_DEADLINE"),
])
def test_preflight_refusals(kwargs, reason, isolated):
    with pytest.raises(bridge.TelegramRefused, match=reason):
        bridge.send_owner_once("hello", **kwargs)
    isolated.assert_not_called()


@pytest.mark.parametrize("text", ["", "x" * (bridge.MAX_LEN + 1)])
def test_no_splitting(text, isolated):
    with pytest.raises(bridge.TelegramRefused, match="LENGTH_INVALID"):
        bridge.send_owner_once(text)
    isolated.assert_not_called()


@pytest.mark.parametrize("result", [
    None, [], {}, {"message_id": True, "chat": {"id": 123456, "type": "private"}},
    {"message_id": 0, "chat": {"id": 123456, "type": "private"}},
    {"message_id": 7, "chat": {"id": "123456", "type": "private"}},
    {"message_id": 7, "chat": {"id": 999, "type": "private"}},
    {"message_id": 7, "chat": {"id": 123456, "type": "group"}},
])
def test_unverified_ack_never_retries_or_records_success(result, isolated):
    isolated.return_value = result
    with pytest.raises(bridge.TelegramRefused, match="ACK_UNVERIFIED"):
        bridge.send_owner_once("hello")
    isolated.assert_called_once()
    assert not bridge.OUTBOX_PATH.exists()


@pytest.mark.parametrize("error", [TimeoutError("private transport detail"), bridge.TelegramRefused("private API detail")])
def test_ambiguous_transport_is_sanitized_and_not_retried(error, isolated):
    isolated.side_effect = error
    with pytest.raises(bridge.TelegramRefused) as exc:
        bridge.send_owner_once("hello")
    assert str(exc.value) == "OWNER_DELIVERY_UNKNOWN_RECONCILE_REQUIRED"
    assert exc.value.__suppress_context__
    isolated.assert_called_once()
    assert not bridge.OUTBOX_PATH.exists()


def test_late_ack_is_not_success(isolated):
    times = iter([1, 2, 10])
    with pytest.raises(bridge.TelegramRefused, match="ACK_AFTER_DEADLINE"):
        bridge.send_owner_once("hello", until=10, clock=lambda: next(times))
    assert isolated.call_args.kwargs["timeout"] == 8
    isolated.assert_called_once()
    assert not bridge.OUTBOX_PATH.exists()


def test_deadline_passes_before_transport(isolated):
    times = iter([1, 10])
    with pytest.raises(bridge.TelegramRefused, match="HELD_HARD_DEADLINE"):
        bridge.send_owner_once("hello", until=10, clock=lambda: next(times))
    isolated.assert_not_called()


def test_persistence_failure_is_ambiguous_not_retried(monkeypatch, isolated):
    monkeypatch.setattr(bridge.os, "fsync", Mock(side_effect=OSError("private disk detail")))
    with pytest.raises(bridge.TelegramRefused) as exc:
        bridge.send_owner_once("hello")
    assert str(exc.value) == "OWNER_DELIVERY_RECEIPT_PERSISTENCE_UNKNOWN"
    isolated.assert_called_once()


def test_existing_send_retains_markdown_fallback(isolated):
    isolated.side_effect = [bridge.TelegramRefused("format error"), {"message_id": 7}]
    assert bridge.send("hello") == [{"message_id": 7}]
    assert isolated.call_count == 2
