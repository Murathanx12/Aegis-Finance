"""Offline restart regressions; synthetic owner and isolated durable state only."""
import json

import pytest

from backend.services import telegram_bridge as TG


@pytest.fixture
def route(monkeypatch, tmp_path):
    monkeypatch.setattr(TG, "OFFSET_PATH", tmp_path / "offset.json")
    monkeypatch.setattr(TG, "INBOX_PATH", tmp_path / "inbox.jsonl")
    monkeypatch.setattr(TG, "owner_chat_id", lambda: "123")
    monkeypatch.setattr(TG, "_inbound_allowed", lambda who: True)
    monkeypatch.setattr(TG, "send", lambda *a, **k: None)
    batch = [{"update_id": n, "message": {"message_id": n,
             "chat": {"id": 123}, "text": "synthetic benign question"}}
             for n in (41, 42)]
    requests = []

    def transport(method, params, **kwargs):
        assert method == "getUpdates", "real transport/send forbidden"
        requests.append(params.get("offset"))
        return [u for u in batch if u["update_id"] >= (params.get("offset") or 0)]

    monkeypatch.setattr(TG, "_call", transport)
    return tmp_path, requests


def test_failed_inbox_admission_is_fetchable_after_restart(route, monkeypatch):
    original = TG._append
    monkeypatch.setattr(TG, "_append", lambda *a: (_ for _ in ()).throw(OSError("disk unavailable")))
    with pytest.raises(OSError):
        TG.poll({}, text_handler=lambda *a: pytest.fail("must not dispatch"))
    assert TG._offset() == 0
    monkeypatch.setattr(TG, "_append", original)
    admitted = []
    TG.poll({}, text_handler=lambda text, msg: admitted.append(msg["message_id"]))
    assert admitted == [41, 42]
    assert TG._offset() == 42
    assert route[1] == [None, None]


def test_handler_durable_failure_keeps_only_unprocessed_suffix(route):
    path = route[0] / "turns.json"

    def admit(text, msg):
        mid = msg["message_id"]
        if mid == 42:
            raise OSError("durable turn write failed")
        path.write_text(json.dumps([mid]), encoding="utf-8")

    with pytest.raises(OSError):
        TG.poll({}, text_handler=admit)
    assert TG._offset() == 41
    assert json.loads(path.read_text()) == [41]
    TG.poll({}, text_handler=lambda text, msg: path.write_text(
        json.dumps(json.loads(path.read_text()) + [msg["message_id"]])))
    assert json.loads(path.read_text()) == [41, 42]
    assert route[1] == [None, 42]
    assert TG._offset() == 42


def test_process_interruption_before_handler_return_replays(route):
    class Crash(BaseException):
        pass

    def interrupt(*args):
        raise Crash()

    with pytest.raises(Crash):
        TG.poll({}, text_handler=interrupt)
    assert TG._offset() == 0
    admitted = []
    TG.poll({}, text_handler=lambda text, msg: admitted.append(msg["message_id"]))
    assert admitted == [41, 42]


def test_legacy_updates_explicitly_advances(route):
    assert len(TG.updates()) == 2
    assert TG._offset() == 42
