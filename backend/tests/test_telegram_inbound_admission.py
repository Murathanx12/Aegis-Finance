"""Offline restart regressions; synthetic owner and isolated durable state only."""
import json

import pytest

from backend.services import telegram_bridge as TG


@pytest.fixture
def route(monkeypatch, tmp_path):
    monkeypatch.setattr(TG, "OFFSET_PATH", tmp_path / "offset.json")
    monkeypatch.setattr(TG, "INBOX_PATH", tmp_path / "inbox.jsonl")
    monkeypatch.setattr(TG, "owner_chat_id", lambda: "123")
    monkeypatch.setattr(TG, "_INBOUND_TIMES", {"owner": [], "stranger": []})
    monkeypatch.setattr(TG, "_SUPPRESSED_NOTED_HOUR", {})
    monkeypatch.setattr(TG, "INBOUND_ROWS_SUPPRESSED", {"owner": 0, "stranger": 0})
    monkeypatch.setattr(TG._cfg, "TELEGRAM_INBOUND_MAX_ROWS_PER_H_OWNER", 120)
    monkeypatch.setattr(TG, "send", lambda *a, **k: None)
    batch = [{"update_id": n, "message": {"message_id": n,
             "chat": {"id": 123}, "text": "synthetic benign question"}}
             for n in (41, 42)]
    requests = []

    def transport(method, params, **kwargs):
        if method == "answerCallbackQuery":
            return {}
        assert method == "getUpdates", "real transport/send forbidden"
        requests.append(params.get("offset"))
        return [u for u in batch if u["update_id"] >= (params.get("offset") or 0)]

    monkeypatch.setattr(TG, "_call", transport)
    return tmp_path, requests, batch


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


def test_130_failed_inbox_attempts_do_not_exhaust_owner_quota(route, monkeypatch):
    original = TG._append
    monkeypatch.setattr(TG, "_append", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    for _ in range(130):
        with pytest.raises(OSError):
            TG.poll({})
    assert TG._offset() == 0
    assert len(TG._INBOUND_TIMES["owner"]) == 0
    monkeypatch.setattr(TG, "_append", original)
    accepted = []
    TG.poll({}, text_handler=lambda text, msg: accepted.append(msg["message_id"]))
    assert accepted == [41, 42]


def test_130_failed_turn_attempts_reuse_durable_inbox_admission(route):
    def fail(*args):
        raise OSError("turn admission")

    for _ in range(130):
        with pytest.raises(OSError):
            TG.poll({}, text_handler=fail)
    assert TG._offset() == 0
    assert len(TG._INBOUND_TIMES["owner"]) == 1
    assert len(TG.INBOX_PATH.read_text().splitlines()) == 1
    # A process restart loses in-memory quota state, not durable admission.
    TG._INBOUND_TIMES["owner"].clear()
    accepted = []
    TG.poll({}, text_handler=lambda text, msg: accepted.append(msg["message_id"]))
    assert accepted == [41, 42]
    assert len(TG.INBOX_PATH.read_text().splitlines()) == 2


def side_effect_route(route, kind):
    batch = route[2]
    del batch[1:]
    if kind == "command":
        batch[0]["message"]["text"] = "/effect"
    else:
        batch[0] = {"update_id": 41, "callback_query": {
            "id": "synthetic", "data": "effect", "from": {"id": 123},
            "message": {"chat": {"id": 123}}}}


@pytest.mark.parametrize("kind", ["command", "callback"])
def test_reply_failure_cannot_replay_side_effect(route, monkeypatch, kind):
    side_effect_route(route, kind)
    effects = []

    def effect(*args):
        effects.append("done")
        return "reply"

    monkeypatch.setattr(TG, "_send_reply", lambda *a, **k: (_ for _ in ()).throw(OSError("send")))
    with pytest.raises(OSError):
        TG.poll({"effect": effect}, callback_handler=effect)
    TG.poll({"effect": effect}, callback_handler=effect)
    assert effects == ["done"]
    assert TG._offset() == 41


@pytest.mark.parametrize("kind", ["command", "callback"])
def test_command_callback_inbox_failure_not_acknowledged(route, monkeypatch, kind):
    side_effect_route(route, kind)
    effects = []
    original = TG._append
    monkeypatch.setattr(TG, "_append", lambda *a: (_ for _ in ()).throw(OSError("admission")))
    with pytest.raises(OSError):
        TG.poll({"effect": lambda *a: effects.append(1)},
                callback_handler=lambda *a: effects.append(1))
    assert TG._offset() == 0 and effects == []
    monkeypatch.setattr(TG, "_append", original)
    TG.poll({"effect": lambda *a: effects.append(1)},
            callback_handler=lambda *a: effects.append(1))
    assert TG._offset() == 41 and effects == [1]


@pytest.mark.parametrize("kind", ["command", "callback"])
def test_ambiguous_handler_io_error_is_guarded_not_silently_replayed(route, kind):
    side_effect_route(route, kind)
    effects = []

    def effect(*args):
        effects.append("possibly executed")
        raise OSError("ambiguous failure after effect")

    # Preserve legacy at-most-once commands; transport admission is durable
    # before execution. An effect's own OSError cannot safely be retried.
    with pytest.raises(OSError):
        TG.poll({"effect": effect}, callback_handler=effect)
    TG.poll({"effect": effect}, callback_handler=effect)
    assert effects == ["possibly executed"]
    assert TG._offset() == 41


@pytest.mark.parametrize("boundary", ["fsync", "replace"])
def test_offset_publication_failure_preserves_previous_cursor(route, monkeypatch, boundary):
    TG._set_offset(40)
    original = TG.OFFSET_PATH.read_bytes()

    def fail(*args):
        raise OSError("offset publication")

    monkeypatch.setattr(TG.os, boundary, fail)
    with pytest.raises(OSError):
        TG._set_offset(41)
    assert TG.OFFSET_PATH.read_bytes() == original
    assert TG._offset() == 40


def test_inbox_fsync_failure_prevents_dispatch_and_ack(route, monkeypatch):
    calls = []

    def fail(fd):
        raise OSError("inbox sync")

    monkeypatch.setattr(TG.os, "fsync", fail)
    with pytest.raises(OSError):
        TG.poll({}, text_handler=lambda *a: calls.append(1))
    assert calls == [] and not TG.OFFSET_PATH.exists()


def test_corrupt_offset_fails_closed_instead_of_replaying_commands(route):
    TG.OFFSET_PATH.write_text('{"offset":')
    with pytest.raises(TG.TelegramRefused, match="OFFSET"):
        TG.poll({})
    assert route[1] == []


def test_expired_quota_entries_do_not_prevent_failed_reservation_rollback(route, monkeypatch):
    TG._INBOUND_TIMES["owner"] = [0.0] * 120
    monkeypatch.setattr(TG, "_append", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        TG.poll({})
    assert TG._INBOUND_TIMES["owner"] == []


@pytest.mark.parametrize("kind", ["command", "callback"])
@pytest.mark.parametrize("boundary", ["marker", "cursor"])
def test_no_effect_when_durable_dispatch_guard_cannot_be_published(route, monkeypatch, kind, boundary):
    side_effect_route(route, kind)
    original = TG._atomic_json
    effects = []

    def publish(path, row):
        if (path == TG.OFFSET_PATH) == (boundary == "cursor"):
            raise OSError("guard publication failed")
        return original(path, row)

    monkeypatch.setattr(TG, "_atomic_json", publish)
    with pytest.raises(OSError):
        TG.poll({"effect": lambda *a: effects.append(1)},
                callback_handler=lambda *a: effects.append(1))
    assert TG._offset() == 0 and effects == []
    monkeypatch.setattr(TG, "_atomic_json", original)
    TG.poll({"effect": lambda *a: effects.append(1)},
            callback_handler=lambda *a: effects.append(1))
    assert effects == [1] and TG._offset() == 41


def test_offset_sync_precedes_atomic_replace_with_complete_bytes(route, monkeypatch):
    TG._set_offset(40)
    previous = TG.OFFSET_PATH.read_bytes()
    events = []
    sync, replace = TG.os.fsync, TG.os.replace

    def flushed(fd):
        assert TG.OFFSET_PATH.read_bytes() == previous
        sync(fd)
        events.append("synced")

    def publish(source, target):
        assert events == ["synced"]
        assert json.loads(source.read_text())["offset"] == 41
        assert target.read_bytes() == previous
        replace(source, target)
        events.append("published")

    monkeypatch.setattr(TG.os, "fsync", flushed)
    monkeypatch.setattr(TG.os, "replace", publish)
    TG._set_offset(41)
    assert events == ["synced", "published"] and TG._offset() == 41


def test_retry_payload_mismatch_fails_closed(route):
    def fail(*args):
        raise OSError("turn admission")

    with pytest.raises(OSError):
        TG.poll({}, text_handler=fail)
    route[2][0]["message"]["text"] = "different synthetic payload"
    with pytest.raises(TG.TelegramRefused, match="MISMATCH"):
        TG.poll({}, text_handler=lambda *a: pytest.fail("must not dispatch"))
    assert TG._offset() == 0


def test_plain_text_reply_failure_does_not_repeat_successful_admission(route, monkeypatch):
    admitted = []
    del route[2][1:]
    monkeypatch.setattr(TG, "_send_reply", lambda *a, **k: (_ for _ in ()).throw(OSError("reply")))
    with pytest.raises(OSError):
        TG.poll({}, text_handler=lambda text, msg: admitted.append(msg["message_id"]) or "answer")
    TG.poll({}, text_handler=lambda text, msg: admitted.append(msg["message_id"]))
    assert admitted == [41] and TG._offset() == 41


def test_successful_durable_turn_deduplicates_after_cursor_failure(route, monkeypatch):
    del route[2][1:]
    path = route[0] / "durable-turns.json"
    path.write_text("[]")
    calls = []

    def admit(text, msg):
        calls.append(msg["message_id"])
        turns = json.loads(path.read_text())
        if msg["message_id"] not in turns:
            turns.append(msg["message_id"])
            path.write_text(json.dumps(turns))
        return "accepted"

    original = TG._set_offset
    monkeypatch.setattr(TG, "_set_offset", lambda *a: (_ for _ in ()).throw(OSError("cursor")))
    with pytest.raises(OSError):
        TG.poll({}, text_handler=admit)
    assert TG._offset() == 0
    monkeypatch.setattr(TG, "_set_offset", original)
    TG._INBOUND_TIMES["owner"].clear()  # Simulated restart, durable state retained.
    TG.poll({}, text_handler=admit)
    assert calls == [41, 41] and json.loads(path.read_text()) == [41]
    assert len(TG.INBOX_PATH.read_text().splitlines()) == 1
    assert TG._offset() == 41


def test_real_owner_quota_limit_remains_an_explicit_rejection(route):
    import time

    TG._INBOUND_TIMES["owner"] = [time.time()] * 120
    TG.poll({}, text_handler=lambda *a: pytest.fail("quota must still bind"))
    assert TG._offset() == 42
    assert TG.INBOUND_ROWS_SUPPRESSED["owner"] == 2
    assert json.loads(TG.INBOX_PATH.read_text())["suppressed_rows"] == "owner"
