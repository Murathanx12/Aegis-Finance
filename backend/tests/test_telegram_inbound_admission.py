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


def test_handler_failure_is_not_automatically_retried(route):
    calls = []

    def effect(text, msg):
        calls.append(msg["message_id"])
        raise OSError("unknown side effect outcome")

    with pytest.raises(OSError):
        TG.poll({}, text_handler=effect)
    assert TG._offset() == 41
    TG.poll({}, text_handler=lambda text, msg: calls.append(msg["message_id"]))
    assert calls == [41, 42]
    assert TG._offset() == 42


def test_process_interruption_does_not_replay_handler(route):
    class Crash(BaseException):
        pass

    def interrupt(*args):
        raise Crash()

    with pytest.raises(Crash):
        TG.poll({}, text_handler=interrupt)
    assert TG._offset() == 41
    admitted = []
    TG.poll({}, text_handler=lambda text, msg: admitted.append(msg["message_id"]))
    assert admitted == [42]


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


def test_130_failed_cursor_attempts_reuse_durable_inbox_admission(route, monkeypatch):
    original = TG._set_offset
    monkeypatch.setattr(TG, "_set_offset", lambda *a: (_ for _ in ()).throw(OSError("cursor")))
    for _ in range(130):
        with pytest.raises(OSError):
            TG.poll({}, text_handler=lambda *a: pytest.fail("must not dispatch"))
    assert TG._offset() == 0
    assert len(TG._INBOUND_TIMES["owner"]) == 1
    assert len(TG.INBOX_PATH.read_text().splitlines()) == 1
    TG._INBOUND_TIMES["owner"].clear()  # Restart; inbox survives.
    monkeypatch.setattr(TG, "_set_offset", original)
    accepted = []
    TG.poll({}, text_handler=lambda text, msg: accepted.append(msg["message_id"]))
    assert accepted == [41, 42]
    assert len(TG.INBOX_PATH.read_text().splitlines()) == 2


def side_effect_route(route, kind):
    batch = route[2]
    del batch[1:]
    if kind == "text":
        return
    if kind == "command":
        batch[0]["message"]["text"] = "/effect"
    else:
        batch[0] = {"update_id": 41, "callback_query": {
            "id": "synthetic", "data": "effect", "from": {"id": 123},
            "message": {"message_id": 41, "chat": {"id": 123}}}}


@pytest.mark.parametrize("kind", ["text", "command", "callback"])
def test_reply_failure_cannot_replay_side_effect(route, monkeypatch, kind):
    side_effect_route(route, kind)
    effects = []

    def effect(*args):
        effects.append("done")
        return "reply"

    monkeypatch.setattr(TG, "_send_reply", lambda *a, **k: (_ for _ in ()).throw(OSError("send")))
    with pytest.raises(OSError):
        TG.poll({"effect": effect}, callback_handler=effect, text_handler=effect)
    TG.poll({"effect": effect}, callback_handler=effect, text_handler=effect)
    assert effects == ["done"]
    assert TG._offset() == 41


@pytest.mark.parametrize("kind", ["text", "command", "callback"])
def test_command_callback_inbox_failure_not_acknowledged(route, monkeypatch, kind):
    side_effect_route(route, kind)
    effects = []
    original = TG._append
    monkeypatch.setattr(TG, "_append", lambda *a: (_ for _ in ()).throw(OSError("admission")))
    with pytest.raises(OSError):
        TG.poll({"effect": lambda *a: effects.append(1)},
                callback_handler=lambda *a: effects.append(1),
                text_handler=lambda *a: effects.append(1))
    assert TG._offset() == 0 and effects == []
    monkeypatch.setattr(TG, "_append", original)
    TG.poll({"effect": lambda *a: effects.append(1)},
            callback_handler=lambda *a: effects.append(1),
                text_handler=lambda *a: effects.append(1))
    assert TG._offset() == 41 and effects == [1]


@pytest.mark.parametrize("kind", ["text", "command", "callback"])
def test_ambiguous_handler_io_error_is_guarded_not_silently_replayed(route, kind):
    side_effect_route(route, kind)
    effects = []

    def effect(*args):
        effects.append("possibly executed")
        raise OSError("ambiguous failure after effect")

    # Preserve legacy at-most-once commands; transport admission is durable
    # before execution. An effect's own OSError cannot safely be retried.
    with pytest.raises(OSError):
        TG.poll({"effect": effect}, callback_handler=effect, text_handler=effect)
    TG.poll({"effect": effect}, callback_handler=effect, text_handler=effect)
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


@pytest.mark.parametrize("kind", ["text", "command", "callback"])
@pytest.mark.parametrize("boundary", ["inbox", "cursor"])
def test_no_effect_when_durable_dispatch_guard_cannot_be_published(route, monkeypatch, kind, boundary):
    side_effect_route(route, kind)
    original_append, original_offset = TG._append, TG._set_offset
    effects = []

    def append_then_fail(*args):
        original_append(*args)
        raise OSError("interruption after inbox publication")

    if boundary == "inbox":
        monkeypatch.setattr(TG, "_append", append_then_fail)
    else:
        monkeypatch.setattr(TG, "_set_offset", lambda *a: (_ for _ in ()).throw(OSError("cursor")))
    with pytest.raises(OSError):
        TG.poll({"effect": lambda *a: effects.append(1)},
                callback_handler=lambda *a: effects.append(1),
                text_handler=lambda *a: effects.append(1))
    assert TG._offset() == 0 and effects == []
    assert len(TG.INBOX_PATH.read_text().splitlines()) == 1
    monkeypatch.setattr(TG, "_append", original_append)
    monkeypatch.setattr(TG, "_set_offset", original_offset)
    TG._INBOUND_TIMES["owner"].clear()
    TG.poll({"effect": lambda *a: effects.append(1)},
            callback_handler=lambda *a: effects.append(1),
            text_handler=lambda *a: effects.append(1))
    assert effects == [1] and TG._offset() == 41
    rows = [json.loads(line) for line in TG.INBOX_PATH.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["update_id"] == 41
    assert rows[0]["message_id"] == 41



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


def test_retry_payload_mismatch_fails_closed(route, monkeypatch):
    original = TG._set_offset
    monkeypatch.setattr(TG, "_set_offset", lambda *a: (_ for _ in ()).throw(OSError("cursor")))
    with pytest.raises(OSError):
        TG.poll({})
    monkeypatch.setattr(TG, "_set_offset", original)
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


def test_non_idempotent_plain_text_runs_only_after_cursor_publication(route, monkeypatch):
    del route[2][1:]
    effects = []
    original = TG._set_offset
    monkeypatch.setattr(TG, "_set_offset", lambda *a: (_ for _ in ()).throw(OSError("cursor")))
    with pytest.raises(OSError):
        TG.poll({}, text_handler=lambda *a: effects.append("ask/digest side effect"))
    assert TG._offset() == 0 and effects == []
    monkeypatch.setattr(TG, "_set_offset", original)
    TG._INBOUND_TIMES["owner"].clear()
    TG.poll({}, text_handler=lambda *a: effects.append("ask/digest side effect"))
    TG.poll({}, text_handler=lambda *a: effects.append("ask/digest side effect"))
    assert effects == ["ask/digest side effect"]
    assert len(TG.INBOX_PATH.read_text().splitlines()) == 1
    assert TG._offset() == 41


def test_real_owner_quota_limit_remains_an_explicit_rejection(route):
    import time

    TG._INBOUND_TIMES["owner"] = [time.time()] * 120
    TG.poll({}, text_handler=lambda *a: pytest.fail("quota must still bind"))
    assert TG._offset() == 42
    assert TG.INBOUND_ROWS_SUPPRESSED["owner"] == 2
    assert json.loads(TG.INBOX_PATH.read_text())["suppressed_rows"] == "owner"


@pytest.mark.parametrize("tail", [b'{"update_id":41', b'not-json\n'])
def test_torn_inbox_tail_stops_before_cursor_and_handler(route, tail):
    TG.INBOX_PATH.write_bytes(tail)
    with pytest.raises(TG.TelegramRefused, match="TAIL_INVALID"):
        TG.poll({}, text_handler=lambda *a: pytest.fail("must not dispatch"))
    assert TG._offset() == 0
    assert TG.INBOX_PATH.read_bytes() == tail


def test_recovered_inbox_is_resynced_before_cursor_and_handler(route, monkeypatch):
    original = TG._set_offset
    monkeypatch.setattr(TG, "_set_offset", lambda *a: (_ for _ in ()).throw(OSError("cursor")))
    with pytest.raises(OSError):
        TG.poll({})
    monkeypatch.setattr(TG, "_set_offset", original)
    monkeypatch.setattr(TG.os, "fsync", lambda *a: (_ for _ in ()).throw(OSError("resync")))
    with pytest.raises(OSError):
        TG.poll({}, text_handler=lambda *a: pytest.fail("must not dispatch"))
    assert TG._offset() == 0
    assert len(TG.INBOX_PATH.read_text().splitlines()) == 1


@pytest.mark.parametrize("kind", ["text", "command", "callback"])
def test_cursor_published_then_interrupted_is_not_handler_acceptance(route, monkeypatch, kind):
    side_effect_route(route, kind)
    original = TG._set_offset
    effects = []

    def published_then_interrupted(value):
        original(value)
        raise OSError("interrupted after cursor publication, before dispatch")

    monkeypatch.setattr(TG, "_set_offset", published_then_interrupted)
    with pytest.raises(OSError):
        TG.poll({"effect": lambda *a: effects.append(1)},
                callback_handler=lambda *a: effects.append(1),
                text_handler=lambda *a: effects.append(1))
    assert TG._offset() == 41 and effects == []
    monkeypatch.setattr(TG, "_set_offset", original)
    TG.poll({"effect": lambda *a: effects.append(1)},
            callback_handler=lambda *a: effects.append(1),
            text_handler=lambda *a: effects.append(1))
    assert effects == []  # At-most-once deliberately does not recover execution.
    assert len(TG.INBOX_PATH.read_text().splitlines()) == 1
