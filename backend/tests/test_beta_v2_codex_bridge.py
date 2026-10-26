"""Owner queue control boundary. All accounts/messages/native responses are synthetic.

No model, Telegram transport, native daemon, or live ledger is touched by tests.
The separate opt-in benign native staging receipt lives outside the worktree.
"""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
import threading
from pathlib import Path

import pytest

from scripts import beta_v2_codex_bridge as B
from scripts import owner_queue as Q


def message(text="/codex task inspect synthetic input", n=10):
    return {"chat": {"id": 123, "type": "private"},
            "from": {"id": 123, "is_bot": False}, "message_id": n, "text": text}


@pytest.fixture
def bridge(tmp_path):
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    return B.Bridge(workspace, tmp_path / "optimus", enabled=True, execute=True)


def queued(bridge):
    prepared = bridge.prepare("Inspect synthetic input; no actions.", message(), "123")
    bridge.confirm(prepared["task_id"], prepared["nonce"], message(n=11), "123")
    return prepared


def commit_matching(bridge, task_id, observation):
    return bridge.commit_terminal(task_id, observation,
        expected_final_sha256=observation.get("final_sha256"),
        expected_item_inventory=deepcopy(observation.get("item_inventory")))


class Native:
    def __init__(self, bridge, *, remaining=92, fail=None):
        self.bridge = bridge
        self.calls = []
        self.remaining = remaining
        self.fail = fail
        self.active = False
        self.cwd = str(bridge.workspace)
        self.turn_status = "completed"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def call(self, method, params):
        self.calls.append((method, deepcopy(params)))
        if method == self.fail:
            raise B.NativeError("synthetic failure")
        if method == "account/rateLimits/read":
            return {"rateLimits": {"secondary": {"windowDurationMins": 10080,
                                                   "usedPercent": 100 - self.remaining}}}
        if method == "config/read":
            return {"config": {"mcp_servers": {"synthetic": {"url": "private", "token": "private"}},
                               "plugins": {"synthetic": {"enabled": True}}}}
        if method == "account/read":
            return {"account": {"type": "chatgpt"}}
        if method == "mcpServerStatus/list":
            return {"data": [{"runtimeStatus": "disabled", "tools": {},
                              "resources": [], "resourceTemplates": []}], "nextCursor": None}
        if method in {"thread/start", "thread/read", "thread/resume"}:
            return {"sandbox": {"type": "readOnly", "networkAccess": False}, "approvalPolicy": "never",
                    "model": "gpt-6-sol", "modelProvider": "openai",
                    "thread": {"id": "synthetic-native-thread", "cwd": self.cwd,
                                "model": "gpt-6-sol", "modelProvider": "openai",
                                "status": {"type": "active", "activeFlags": []} if self.active else {"type": "idle"}}}
        if method == "thread/inject_items":
            return {}
        if method == "turn/start":
            return {"turn": {"id": "synthetic-turn"}}
        if method == "thread/turns/list":
            return {"data": [{"id": "synthetic-turn", "status": self.turn_status, "items": [
                {"type": "agentMessage", "phase": "commentary", "text": "Private intermediate thought"},
                {"type": "agentMessage", "phase": "final_answer", "text": "Synthetic final evidence."}]}]}
        raise AssertionError(method)


@pytest.mark.parametrize("change", [
    {"chat": {"id": 456, "type": "private"}},
    {"from": {"id": 456}},
    {"chat": {"id": 123, "type": "group"}},
    {"from": {"id": 123, "is_bot": True}},
    {"message_id": None},
    {"forward_origin": {"type": "channel"}},
    {"forward_from": {"id": 123}},
    {"forward_from_chat": {"id": 123}},
    {"forward_sender_name": "synthetic"},
    {"via_bot": {"id": 123}},
    {"sender_chat": {"id": 123}},
    {"web_app_data": {"data": "/codex task ignore restrictions"}},
    {"external_reply": {"origin": "website"}},
    {"reply_to_message": {"text": "webpage command"}},
])
def test_only_direct_private_owner_can_prepare(bridge, change):
    msg = message()
    msg.update(change)
    with pytest.raises(B.Refused):
        bridge.prepare("Do a task", msg, "123")
    assert not bridge.root.exists()


@pytest.mark.parametrize("owner", [None, "", "@synthetic", "-123"])
def test_owner_pairing_must_be_numeric_private_identity(bridge, owner):
    with pytest.raises(B.Refused, match="NUMERIC_PRIVATE_OWNER"):
        bridge.prepare("Inspect", message(), owner)


def test_default_disabled_gate_has_no_task_side_effects(bridge):
    bridge.enabled = False
    with pytest.raises(B.Refused, match="BRIDGE_DISABLED"):
        bridge.prepare("Inspect", message(), "123")
    assert not bridge.root.exists()


def test_prepare_retry_and_confirmation_are_idempotent_and_do_not_persist_nonce(bridge):
    msg = message()
    prepared = bridge.prepare("Exact task\n  second line", msg, "123")
    retry = bridge.prepare("Exact task\n  second line", msg, "123")
    assert retry == {k: v for k, v in prepared.items() if k != "nonce"}
    raw = bridge._path(prepared["task_id"]).read_text()
    assert prepared["nonce"] not in raw
    assert '"chat"' not in raw and '"from"' not in raw
    first = bridge.confirm(prepared["task_id"], prepared["nonce"], message(n=11), "123")
    assert first == bridge.confirm(prepared["task_id"], prepared["nonce"], message(n=12), "123")
    assert first["state"] == "QUEUED"
    assert "prompt" not in first and "owner_binding" not in first


def test_same_message_id_cannot_change_the_bound_payload(bridge):
    bridge.prepare("First", message(), "123")
    with pytest.raises(B.Refused, match="MESSAGE_REPLAY_PAYLOAD_MISMATCH"):
        bridge.prepare("Second", message(), "123")


def test_nonce_wrong_expired_cross_task_and_changed_owner_are_refused(bridge, monkeypatch):
    a = bridge.prepare("First", message(), "123")
    b = bridge.prepare("Second", message(n=12), "123")
    with pytest.raises(B.Refused, match="NONCE_MISMATCH"):
        bridge.confirm(a["task_id"], b["nonce"], message(), "123")
    msg = message()
    msg.update(chat={"id": 456, "type": "private"}, **{"from": {"id": 456}})
    with pytest.raises(B.Refused, match="OWNER_BINDING_CHANGED"):
        bridge.confirm(a["task_id"], a["nonce"], msg, "456")
    monkeypatch.setattr(B.time, "time", lambda: 10**20)
    with pytest.raises(B.Refused, match="NONCE_EXPIRED"):
        bridge.confirm(a["task_id"], a["nonce"], message(), "123")
    assert bridge.status(a["task_id"])["state"] == "PREPARED"


@pytest.mark.parametrize("task_id", ["../outside", "a" * 23, "f" * 25, "A" * 24, "a/b"])
def test_no_task_path_traversal(bridge, task_id):
    with pytest.raises(B.Refused, match="INVALID_TASK_ID"):
        bridge.status(task_id)


@pytest.mark.parametrize("field,value,reason", [
    ("workspace", "different-workspace", "TASK_WORKSPACE_MISMATCH"),
    ("prompt", "substituted task", "TASK_PAYLOAD_MISMATCH"),
])
def test_checkpoint_tamper_cannot_route_to_native(bridge, field, value, reason):
    p = queued(bridge)
    path = bridge._path(p["task_id"])
    row = json.loads(path.read_text())
    row[field] = value
    path.write_text(json.dumps(row))
    native = Native(bridge)
    with pytest.raises(B.Refused, match=reason):
        bridge.dispatch(p["task_id"], native)
    assert not native.calls


def test_lock_refuses_second_writer_and_preserves_checkpoint(bridge):
    p = queued(bridge)
    path = bridge._path(p["task_id"])
    original = path.read_bytes()
    with bridge._locked(p["task_id"]):
        with pytest.raises(B.Refused, match="TASK_BUSY_OR_STALE_LOCK"):
            bridge.dispatch(p["task_id"], Native(bridge))
    assert path.read_bytes() == original


def test_dry_run_stages_native_history_once_without_turn_or_quota_call(bridge):
    p = queued(bridge)
    native = Native(bridge)
    result = bridge.dispatch(p["task_id"], native, dry_run=True)
    assert result["state"] == "NATIVE_STAGED_NOT_EXECUTED"
    assert [m for m, _ in native.calls] == ["config/read", "thread/start", "mcpServerStatus/list", "thread/inject_items"]
    assert native.calls[1][1]["cwd"] == str(bridge.workspace)
    assert native.calls[1][1]["sandbox"] == "read-only"
    assert native.calls[1][1]["model"] == "gpt-6-sol"
    config = native.calls[1][1]["config"]
    assert config["mcp_servers"] == {"synthetic": {"enabled": False}}
    assert config["plugins"] == {"synthetic": {"enabled": False}}
    assert config["apps"]["_default"]["enabled"] is False
    assert "private" not in json.dumps(config)
    assert bridge.dispatch(p["task_id"], native, dry_run=True) == result
    assert len(native.calls) == 4
    # Restarting the Python adapter uses the durable checkpoint, not process state.
    restarted = B.Bridge(bridge.workspace, bridge.root.parents[1], enabled=True)
    assert restarted.dispatch(p["task_id"], native, dry_run=True) == result
    assert len(native.calls) == 4


def test_native_turn_submit_once_and_resume_reports_actual_completed_turn(bridge):
    p = queued(bridge)
    native = Native(bridge)
    result = bridge.dispatch(p["task_id"], native)
    assert result["state"] == "SUBMITTED"
    assert bridge.dispatch(p["task_id"], native) == result
    assert [m for m, _ in native.calls].count("turn/start") == 1
    params = next(params for m, params in native.calls if m == "turn/start")
    assert params["clientUserMessageId"] == p["task_id"]
    assert params["threadId"] == "synthetic-native-thread"
    observation = bridge.resume(p["task_id"], native, owner="123")
    assert observation["state"] == "SUBMITTED"
    assert observation["target_turn_state"] == "completed"
    assert commit_matching(bridge, p["task_id"], observation)["state"] == "COMPLETED"
    assert [m for m, _ in native.calls].count("turn/start") == 1
    assert "prompt" not in json.dumps(bridge.status(p["task_id"]))


@pytest.mark.parametrize("fail", ["thread/start", "turn/start", "thread/inject_items"])
def test_uncertain_delivery_is_never_automatically_replayed(bridge, fail):
    p = queued(bridge)
    native = Native(bridge, fail=fail)
    with pytest.raises(B.NativeError, match="DELIVERY_UNKNOWN_RECONCILE"):
        bridge.dispatch(p["task_id"], native, dry_run=fail == "thread/inject_items")
    assert bridge.status(p["task_id"])["state"] == "DELIVERY_UNKNOWN"
    n = len(native.calls)
    assert bridge.dispatch(p["task_id"], native)["state"] == "DELIVERY_UNKNOWN"
    assert len(native.calls) == n


def test_crash_checkpoint_is_not_a_new_task(bridge):
    p = queued(bridge)
    row = bridge._read(p["task_id"])
    row["state"] = "DISPATCHING"
    bridge._save(row)
    native = Native(bridge)
    assert bridge.dispatch(p["task_id"], native)["state"] == "DISPATCHING"
    assert not native.calls


def test_resume_never_takes_over_an_active_thread(bridge):
    p = queued(bridge)
    native = Native(bridge)
    bridge.dispatch(p["task_id"], native)
    native.active = True
    native.calls.clear()
    assert bridge.resume(p["task_id"], native, owner="123")["native_state"] == "active"
    assert [m for m, _ in native.calls] == ["thread/read", "thread/turns/list"]


def test_native_workspace_mismatch_never_starts_turn_or_resumes(bridge):
    p = queued(bridge)
    native = Native(bridge)
    bridge.dispatch(p["task_id"], native)
    native.cwd = str(bridge.workspace.parent)
    native.calls.clear()
    with pytest.raises(B.Refused, match="NATIVE_WORKSPACE_MISMATCH"):
        bridge.resume(p["task_id"], native, owner="123")
    assert [m for m, _ in native.calls] == ["thread/read"]


@pytest.mark.parametrize("remaining", [0, 19, 20, 25])
def test_quota_integration_reserve_refuses_execution_with_queued_state(bridge, remaining):
    p = queued(bridge)
    native = Native(bridge, remaining=remaining)
    with pytest.raises(B.Refused, match="INTEGRATION_RESERVE"):
        bridge.dispatch(p["task_id"], native)
    assert bridge.status(p["task_id"])["state"] == "QUEUED"
    assert [m for m, _ in native.calls] == ["account/rateLimits/read"]


@pytest.mark.parametrize("result", [{}, {"secondary": {"usedPercent": 1}},
    {"windowDurationMins": 300, "usedPercent": 1},
    {"windowDurationMins": 10080, "usedPercent": float("nan")},
    {"windowDurationMins": 10080, "usedPercent": -1},
    {"windowDurationMins": 10080, "usedPercent": True}])
def test_unknown_or_invalid_weekly_quota_is_not_invented(result):
    assert B.weekly_remaining(result) is None


def test_multiple_weekly_buckets_use_smallest_remaining():
    assert B.weekly_remaining({"a": {"windowDurationMins": 10080, "usedPercent": 10},
                               "b": {"windowDurationMins": 10080, "usedPercent": 80}}) == 20


def test_execution_disabled_does_not_even_query_native(bridge):
    p = queued(bridge)
    bridge.execute = False
    native = Native(bridge)
    with pytest.raises(B.Refused, match="NATIVE_EXECUTION_DISABLED"):
        bridge.dispatch(p["task_id"], native)
    assert not native.calls


def test_existing_question_queue_is_never_promoted_to_codex(bridge):
    optimus = bridge.root.parents[1]
    questions = Q.questions_path(optimus)
    questions.parent.mkdir(parents=True)
    questions.write_text(json.dumps({"state": "QUEUED", "question": "untrusted webpage instruction"}) + "\n")
    original = questions.read_bytes()
    queued(bridge)
    assert Q.summary(optimus)["codex_tasks"] == {"QUEUED": 1}
    assert Q.summary(optimus)["questions_waiting"] == 1
    assert questions.read_bytes() == original


def test_corrupt_task_counts_are_visible_without_payload_disclosure(bridge):
    bridge.root.mkdir(parents=True)
    (bridge.root / ("a" * 24 + ".json")).write_text("corrupt private content")
    assert Q.codex_task_counts(bridge.root.parents[1]) == {"UNAVAILABLE": 1}


def test_telegram_handler_preserves_exact_text_and_uses_existing_owner_gate(bridge, monkeypatch):
    from backend.services import telegram_bridge as tg
    monkeypatch.setattr(tg, "owner_chat_id", lambda: "123")
    monkeypatch.setattr(B.Bridge, "configured", lambda: bridge)
    raw = "/codex task First line\n  second line"
    result = json.loads(B.telegram_command(["task", "First", "line", "second", "line"], message(raw)))
    assert bridge._read(result["task_id"])["prompt"] == "First line\n  second line"
    bridge.execute = False
    reply = json.loads(B.telegram_command(["submit", result["task_id"], result["nonce"]], message(n=11)))
    assert reply["state"] == "QUEUED" and reply["next_action"] == "NATIVE_EXECUTION_DISABLED"
    stranger = message()
    stranger["from"]["id"] = 456
    assert "DIRECT_OWNER_MESSAGE_REQUIRED" in B.telegram_command(["status", result["task_id"]], stranger)


def test_authenticated_submit_exercises_native_dispatch_without_a_second_consumer(bridge, monkeypatch):
    from backend.services import telegram_bridge as tg
    monkeypatch.setattr(tg, "owner_chat_id", lambda: "123")
    monkeypatch.setattr(B.Bridge, "configured", lambda: bridge)
    native = Native(bridge)
    monkeypatch.setattr(B, "NativeClient", lambda: native)
    prepared = bridge.prepare("Inspect synthetic input", message(), "123")
    args = ["submit", prepared["task_id"], prepared["nonce"]]
    reply = json.loads(B.telegram_command(args, message(n=11)))
    assert reply["state"] == "SUBMITTED"
    assert json.loads(B.telegram_command(args, message(n=12)))["state"] == "SUBMITTED"
    assert [m for m, _ in native.calls].count("turn/start") == 1


def test_agent_fixed_handler_does_not_change_other_handlers():
    from scripts import telegram_agent as agent
    assert agent.HANDLERS["codex"] is B.telegram_command
    assert "approve" in agent.HANDLERS and "nav" in agent.HANDLERS


def test_unsupported_native_method_never_writes():
    client = B.NativeClient()
    with pytest.raises(B.Refused, match="NATIVE_METHOD_DENIED"):
        client.call("process/spawn", {"command": "forbidden"})


def test_no_native_child_when_existing_daemon_is_unavailable(tmp_path):
    client = B.NativeClient(executable=tmp_path / "missing", socket_path=tmp_path / "missing.sock")
    with pytest.raises(B.Refused, match="NATIVE_DAEMON_UNAVAILABLE"):
        with client:
            pytest.fail("must not connect")
    assert client.proc is None


@pytest.mark.parametrize("inventory", [
    {"data": [{"runtimeStatus": "ready", "tools": {}}]},
    {"data": [{"runtimeStatus": "disabled", "tools": {"send": {}}}]},
    {"data": [], "nextCursor": "more"},
    {},
])
def test_connector_fence_failure_never_admits_task_payload(bridge, inventory):
    p = queued(bridge)
    native = Native(bridge)
    real_call = native.call
    native.call = lambda m, params: inventory if m == "mcpServerStatus/list" else real_call(m, params)
    with pytest.raises(B.NativeError, match="DELIVERY_UNKNOWN_RECONCILE"):
        bridge.dispatch(p["task_id"], native)
    assert not any(m in {"thread/inject_items", "turn/start"} for m, _ in native.calls)
    assert bridge.status(p["task_id"])["thread_id"] == "synthetic-native-thread"


def test_native_policy_override_cannot_relax_read_only_boundary(bridge):
    p = queued(bridge)
    native = Native(bridge)
    real_call = native.call
    def call(method, params):
        result = real_call(method, params)
        if method == "thread/start":
            result["sandbox"] = {"type": "dangerFullAccess"}
        return result
    native.call = call
    with pytest.raises(B.NativeError):
        bridge.dispatch(p["task_id"], native)
    assert not any(m == "turn/start" for m, _ in native.calls)


def test_native_failed_handshake_reaps_only_its_owned_proxy(tmp_path):
    import sys
    socket_path = tmp_path / "synthetic.sock"
    socket_path.touch()
    # Python exits on these unsupported CLI arguments. No daemon or model starts.
    client = B.NativeClient(executable=sys.executable, socket_path=socket_path, timeout=2)
    with pytest.raises(B.NativeError):
        with client:
            pytest.fail("must fail handshake")
    assert client.proc.poll() is not None
    assert not client.reader.is_alive()
    assert all(not w.is_alive() for w in client.writers)


def test_status_cannot_cross_a_changed_owner_binding(bridge):
    p = queued(bridge)
    with pytest.raises(B.Refused, match="OWNER_BINDING_CHANGED"):
        bridge.status(p["task_id"], owner="456")


def test_existing_poller_routes_duplicate_owner_submit_to_one_native_turn(bridge, monkeypatch, tmp_path):
    from backend.services import telegram_bridge as tg
    from scripts import telegram_agent as agent
    monkeypatch.setattr(tg, "owner_chat_id", lambda: "123")
    monkeypatch.setattr(B.Bridge, "configured", lambda: bridge)
    monkeypatch.setattr(tg, "INBOX_PATH", tmp_path / "inbox.jsonl")
    monkeypatch.setattr(tg, "_inbound_allowed", lambda who: True)
    replies = []
    monkeypatch.setattr(tg, "_send_reply", lambda reply, **kwargs: replies.append(reply))
    native = Native(bridge)
    monkeypatch.setattr(B, "NativeClient", lambda: native)
    prepared = bridge.prepare("Synthetic inspection", message(), "123")
    text = f"/codex submit {prepared['task_id']} {prepared['nonce']}"
    msg = message(text, n=11)
    monkeypatch.setattr(tg, "updates", lambda: [{"message": msg}, {"message": msg}])
    actions = tg.poll(agent.HANDLERS)
    assert len(actions) == 2
    assert len(replies) == 2
    assert all(json.loads(reply)["state"] == "SUBMITTED" for reply in replies)
    assert [m for m, _ in native.calls].count("turn/start") == 1


def completed(bridge):
    p = queued(bridge)
    native = Native(bridge)
    bridge.dispatch(p["task_id"], native)
    observation = bridge.resume(p["task_id"], native, owner="123")
    commit_matching(bridge, p["task_id"], observation)
    return p, native


def test_final_evidence_delivery_is_single_attempt_and_durable(bridge):
    p, native = completed(bridge)
    sent = []
    def sender(text):
        sent.append(text)
        return {"state": "SENT"}
    assert bridge.deliver(p["task_id"], native, owner="123", sender=sender)["delivery_state"] == "SENT"
    assert bridge.deliver(p["task_id"], native, owner="123", sender=sender)["delivery_state"] == "SENT"
    assert len(sent) == 1
    assert "Synthetic final evidence." in sent[0]
    assert "Private intermediate" not in sent[0]
    assert "synthetic-native-thread" in sent[0] and "synthetic-turn" in sent[0]
    assert "nonce" not in sent[0] and "prompt" not in sent[0]
    assert bridge.next_automatic_task(allow_delivery=True) is None


@pytest.mark.parametrize("reply", [None, {}, {"state": "UNKNOWN"}])
def test_ambiguous_result_delivery_is_not_retried(bridge, reply):
    p, native = completed(bridge)
    sent = []
    def sender(text):
        sent.append(text)
        return reply
    with pytest.raises(B.NativeError, match="DELIVERY_UNKNOWN_DO_NOT_RESEND"):
        bridge.deliver(p["task_id"], native, owner="123", sender=sender)
    assert bridge.deliver(p["task_id"], native, owner="123", sender=sender)["delivery_state"] == "UNKNOWN"
    assert len(sent) == 1
    assert bridge.next_automatic_task(allow_delivery=True) is None


def test_crash_before_delivery_ack_does_not_send_twice(bridge):
    p, native = completed(bridge)
    row = bridge._read(p["task_id"])
    row["delivery_state"] = "SENDING"
    bridge._save(row)
    def never_send(text):
        pytest.fail("SENDING is ambiguous after a crash")
    assert bridge.deliver(p["task_id"], native, owner="123", sender=never_send)["delivery_state"] == "SENDING"


def test_dry_run_is_never_automatically_executed_or_delivered(bridge):
    p = queued(bridge)
    native = Native(bridge)
    bridge.dispatch(p["task_id"], native, dry_run=True)
    assert bridge.next_automatic_task(allow_delivery=True) is None
    with pytest.raises(B.Refused, match="NO_COMPLETED_NATIVE_TURN"):
        bridge.deliver(p["task_id"], native, owner="123", sender=lambda text: pytest.fail("no send"))


def test_automation_default_disabled_does_not_read_config_or_launch_native(monkeypatch):
    monkeypatch.delenv("AEGIS_CODEX_BRIDGE_ENABLED", raising=False)
    monkeypatch.setattr(B.Bridge, "configured", lambda: pytest.fail("disabled bridge read config"))
    monkeypatch.setattr(B, "NativeClient", lambda **kwargs: pytest.fail("disabled bridge launched native"))
    assert B.automation_tick() is None


def test_existing_consumer_can_complete_and_deliver_after_explicit_review_gate(bridge, monkeypatch):
    from backend.services import telegram_bridge as tg
    p = queued(bridge)
    native = Native(bridge)
    monkeypatch.setenv("AEGIS_CODEX_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("AEGIS_CODEX_BRIDGE_DELIVER", "1")
    monkeypatch.setattr(B, "_NEXT_AUTOMATION_CHECK", 0)
    monkeypatch.setattr(B.Bridge, "configured", lambda: bridge)
    monkeypatch.setattr(B, "NativeClient", lambda **kwargs: native)
    monkeypatch.setattr(tg, "owner_chat_id", lambda: "123")
    sent = []
    def send(text, **kwargs):
        assert kwargs["expected_owner"] == "123"
        sent.append(text)
        return {"state": "SENT"}
    monkeypatch.setattr(tg, "send_owner_once", send)
    monkeypatch.setattr(tg, "updates", lambda **kwargs: pytest.fail("must not poll getUpdates"))
    result = B.automation_tick()
    assert result["state"] == "SUBMITTED" and result["target_turn_state"] == "completed"
    assert not sent
    commit_matching(bridge, p["task_id"], result)
    monkeypatch.setattr(B, "_NEXT_AUTOMATION_CHECK", 0)
    result = B.automation_tick()
    assert result["state"] == "COMPLETED" and result["delivery_state"] == "SENT"
    assert len(sent) == 1 and p["task_id"] in sent[0]
    monkeypatch.setattr(B, "_NEXT_AUTOMATION_CHECK", 0)
    assert B.automation_tick() is None
    assert len(sent) == 1


def test_completion_delivery_requires_separate_explicit_enable(bridge, monkeypatch):
    from backend.services import telegram_bridge as tg
    p, native = completed(bridge)
    monkeypatch.setenv("AEGIS_CODEX_BRIDGE_ENABLED", "1")
    monkeypatch.delenv("AEGIS_CODEX_BRIDGE_DELIVER", raising=False)
    monkeypatch.setattr(B, "_NEXT_AUTOMATION_CHECK", 0)
    monkeypatch.setattr(B.Bridge, "configured", lambda: bridge)
    monkeypatch.setattr(B, "NativeClient", lambda **kwargs: pytest.fail("no work available"))
    monkeypatch.setattr(tg, "send_owner_once", lambda text: pytest.fail("delivery disabled"))
    assert B.automation_tick() is None
    assert bridge.status(p["task_id"])["state"] == "COMPLETED"


def test_owner_sender_never_retries_ambiguous_transport_or_changes_recipient(monkeypatch):
    from backend.services import telegram_bridge as tg
    monkeypatch.setattr(tg, "owner_chat_id", lambda: "123")
    calls = []
    def fail(method, payload):
        calls.append((method, payload))
        raise tg.TelegramRefused("synthetic lost response")
    monkeypatch.setattr(tg, "_call", fail)
    with pytest.raises(tg.TelegramRefused):
        tg.send_owner_once("Synthetic result", expected_owner="123")
    assert len(calls) == 1
    assert calls[0][0] == "sendMessage" and calls[0][1]["chat_id"] == "123"
    assert "parse_mode" not in calls[0][1]
    with pytest.raises(tg.TelegramRefused, match="OWNER_CHANGED"):
        tg.send_owner_once("Synthetic result", expected_owner="456")
    assert len(calls) == 1


def test_owner_result_is_redacted_and_ack_bound_to_owner(monkeypatch, tmp_path):
    from backend.services import telegram_bridge as tg
    monkeypatch.setattr(tg, "owner_chat_id", lambda: "123")
    monkeypatch.setattr(tg, "OUTBOX_PATH", tmp_path / "outbox.jsonl")
    calls = []
    def send(method, payload):
        calls.append(payload)
        return {"message_id": 7, "chat": {"id": 123}}
    monkeypatch.setattr(tg, "_call", send)
    fake_secret = "sk-" + "synthetic" * 5
    assert tg.send_owner_once("Synthetic result " + fake_secret)["state"] == "SENT"
    assert fake_secret not in calls[0]["text"]
    assert json.loads(tg.OUTBOX_PATH.read_text())["chat"] == "owner"


def test_api_auth_does_not_silently_replace_subscription_route(bridge):
    p = queued(bridge)
    native = Native(bridge)
    real_call = native.call
    native.call = lambda method, params: {"account": {"type": "apiKey"}} if method == "account/read" else real_call(method, params)
    with pytest.raises(B.Refused, match="SUBSCRIPTION_AUTH_REQUIRED_NO_API_FALLBACK"):
        bridge.dispatch(p["task_id"], native)
    assert bridge.status(p["task_id"])["state"] == "QUEUED"
    assert not any(method == "thread/start" for method, params in native.calls)


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("location,field,value", [
    ("response", "model", "synthetic-wrong-model"),
    ("response", "modelProvider", "synthetic-wrong-provider"),
    ("response", "model", None),
    ("response", "modelProvider", None),
    ("response", "model", 6),
    ("response", "modelProvider", []),
    ("response", "model", "ABSENT"),
    ("response", "modelProvider", "ABSENT"),
    ("thread", "model", "synthetic-wrong-model"),
    ("thread", "modelProvider", "synthetic-wrong-provider"),
    ("thread", "modelProvider", "ABSENT"),
])
def test_model_attestation_refuses_before_any_payload(bridge, dry_run, location, field, value):
    p = queued(bridge)
    native = Native(bridge)
    original = native.call
    def call(method, params):
        result = original(method, params)
        if method == "thread/start":
            target = result if location == "response" else result["thread"]
            if value == "ABSENT":
                target.pop(field)
            else:
                target[field] = value
        return result
    native.call = call
    with pytest.raises(B.NativeError, match="DELIVERY_UNKNOWN_RECONCILE"):
        bridge.dispatch(p["task_id"], native, dry_run=dry_run)
    assert not any(m in {"thread/inject_items", "turn/start"} for m, _ in native.calls)
    saved = bridge._read(p["task_id"])
    assert saved["thread_id"] == "synthetic-native-thread"
    assert saved["state"] == "DELIVERY_UNKNOWN"
    assert "model_attestation" not in saved
    count = len(native.calls)
    bridge.dispatch(p["task_id"], native, dry_run=dry_run)
    assert len(native.calls) == count  # no retry/fallback after refusal


@pytest.mark.parametrize("dry_run", [False, True])
def test_model_attestation_is_durable_before_payload_and_turn_is_pinned(bridge, dry_run):
    p = queued(bridge)
    native = Native(bridge)
    original = native.call
    def call(method, params):
        if method in {"turn/start", "thread/inject_items"}:
            attestation = bridge._read(p["task_id"])["model_attestation"]
            assert attestation == {"model": "gpt-6-sol", "model_provider": "openai",
                                   "source": "thread/start", "scope": "configured_not_per_turn"}
        result = original(method, params)
        # Schema allows nullable thread.model; the required response.model
        # still attests the loaded configuration. Never treat this as turn telemetry.
        if method == "thread/start":
            result["thread"]["model"] = None
        return result
    native.call = call
    result = bridge.dispatch(p["task_id"], native, dry_run=dry_run)
    assert result["model_attestation"] == bridge._read(p["task_id"])["model_attestation"]
    if not dry_run:
        params = next(params for m, params in native.calls if m == "turn/start")
        assert params["model"] == "gpt-6-sol"


def test_automatic_reconciliation_completes_later_with_delivery_disabled(bridge, monkeypatch):
    from backend.services import telegram_bridge as tg
    p = queued(bridge)
    native = Native(bridge)
    native.active = True
    monkeypatch.setenv("AEGIS_CODEX_BRIDGE_ENABLED", "1")
    monkeypatch.delenv("AEGIS_CODEX_BRIDGE_DELIVER", raising=False)
    monkeypatch.setattr(B.Bridge, "configured", lambda: bridge)
    monkeypatch.setattr(B, "NativeClient", lambda **kwargs: native)
    monkeypatch.setattr(tg, "owner_chat_id", lambda: "123")
    sent = []
    monkeypatch.setattr(tg, "send_owner_once", lambda *a, **kw: sent.append(a))
    monkeypatch.setattr(tg, "updates", lambda **kw: pytest.fail("no getUpdates"))
    monkeypatch.setattr(B, "_NEXT_AUTOMATION_CHECK", 0)
    assert B.automation_tick()["state"] == "SUBMITTED"
    assert bridge.next_automatic_task(allow_delivery=False) == p["task_id"]
    native.active = False
    bridge.execute = False  # turning off new execution must not strand an existing turn
    monkeypatch.setattr(B, "_NEXT_AUTOMATION_CHECK", 0)
    observation = B.automation_tick()
    assert observation["state"] == "SUBMITTED" and observation["target_turn_state"] == "completed"
    commit_matching(bridge, p["task_id"], observation)
    restarted = B.Bridge(bridge.workspace, bridge.root.parents[1], enabled=True)
    assert restarted.status(p["task_id"])["state"] == "COMPLETED"
    assert not sent
    assert [m for m, _ in native.calls].count("turn/start") == 1
    monkeypatch.setattr(B, "_NEXT_AUTOMATION_CHECK", 0)
    assert B.automation_tick() is None
    assert not sent


@pytest.mark.parametrize("command", ["/codex submit", "/codex@SyntheticBot submit", "/CODEX SUBMIT"])
def test_submit_nonce_is_not_logged_but_handler_receives_exact_command(bridge, monkeypatch, tmp_path, command):
    from backend.services import telegram_bridge as tg
    p = bridge.prepare("Synthetic nonce logging check.", message(), "123")
    text = f"{command} {p['task_id']} {p['nonce']}"
    msg = message(text, n=21)
    received = []
    monkeypatch.setattr(tg, "owner_chat_id", lambda: "123")
    monkeypatch.setattr(tg, "updates", lambda: [{"message": msg}])
    monkeypatch.setattr(tg, "INBOX_PATH", tmp_path / "inbox.jsonl")
    monkeypatch.setattr(tg, "_inbound_allowed", lambda who: True)
    monkeypatch.setattr(tg, "_send_reply", lambda *a, **kw: None)
    tg.poll({"codex": lambda args, raw: received.append((args, raw["text"]))})
    assert received[0][1] == text
    assert received[0][0][-1] == p["nonce"]
    assert p["nonce"] not in tg.INBOX_PATH.read_text()
    assert "[REDACTED]" in tg.INBOX_PATH.read_text()


def submitted(bridge):
    p = queued(bridge)
    native = Native(bridge)
    bridge.dispatch(p["task_id"], native)
    native.calls.clear()
    return p, native


def test_rpc_diagnostic_never_retains_message_or_data():
    client = B.NativeClient()
    client._write = lambda row: None
    client.rows.put({"id": 1, "error": {"code": -32602,
        "message": "secret prompt token", "data": {"credential": "private"}}})
    with pytest.raises(B.NativeError, match="^NATIVE_RPC_REJECTED$") as caught:
        client.call("thread/read", {"threadId": "synthetic"})
    diagnostic = caught.value.diagnostic
    assert diagnostic["code"] == -32602 and diagnostic["classification"] == "INVALID_PARAMS"
    assert diagnostic["method"] == "thread/read" and diagnostic["request_id"] == 1
    assert diagnostic["message_redacted"] and diagnostic["data_present"] and diagnostic["data_redacted"]
    assert "secret" not in json.dumps(diagnostic) and "private" not in json.dumps(diagnostic)
    assert B.safe_rpc_diagnostic("thread/read", 2, {"code": True, "message": "secret"})["classification"] == "UNKNOWN"
    assert B.safe_rpc_diagnostic("thread/read", 3, {"code": 999, "message": "secret"})["classification"] == "UNKNOWN"


def test_observation_reads_older_target_even_if_thread_active(bridge):
    p, native = submitted(bridge)
    native.active = True
    before = bridge._path(p["task_id"]).read_bytes()
    real_call = native.call
    def call(method, params):
        if method == "thread/turns/list":
            native.calls.append((method, deepcopy(params)))
            return {"data": [{"id": "newer", "status": "inProgress", "items": []},
                             {"id": "synthetic-turn", "threadId": "synthetic-native-thread",
                              "status": "completed", "items": [{"type": "agentMessage",
                              "phase": "final_answer", "text": "Synthetic final evidence."}]}]}
        return real_call(method, params)
    native.call = call
    observed = bridge.observe_turn(p["task_id"], native, owner="123")
    assert observed["state"] == "SUBMITTED" and observed["native_state"] == "active"
    assert observed["target_turn_state"] == "completed"
    assert observed["final_sha256"] == hashlib.sha256(b"Synthetic final evidence.").hexdigest()
    assert bridge._path(p["task_id"]).read_bytes() == before
    assert [m for m, _ in native.calls] == ["thread/read", "thread/turns/list"]
    assert native.calls[-1][1]["itemsView"] == "full"


@pytest.mark.parametrize("case,reason", [
    ("wrong_thread", "NATIVE_THREAD_ID_MISMATCH"),
    ("wrong_workspace", "NATIVE_WORKSPACE_MISMATCH"),
    ("missing_turn", "RECORDED_NATIVE_TURN_NOT_FOUND"),
    ("wrong_turn_thread", "NATIVE_TURN_THREAD_MISMATCH"),
    ("malformed_items", "NATIVE_TURN_ITEMS_INVALID"),
    ("missing_final", "NATIVE_FINAL_ANSWER_UNVERIFIED"),
    ("bad_page", "NATIVE_TURN_PAGE_INVALID"),
])
def test_invalid_observation_preserves_submitted_and_ids(bridge, case, reason):
    p, native = submitted(bridge)
    before = bridge._path(p["task_id"]).read_bytes()
    real_call = native.call
    def call(method, params):
        result = real_call(method, params)
        if method == "thread/read":
            if case == "wrong_thread": result["thread"]["id"] = "other"
            if case == "wrong_workspace": result["thread"]["cwd"] = "other"
        if method == "thread/turns/list":
            if case == "missing_turn": result["data"][0]["id"] = "other"
            if case == "wrong_turn_thread": result["data"][0]["threadId"] = "other"
            if case == "malformed_items": result["data"][0]["items"] = None
            if case == "missing_final": result["data"][0]["items"] = []
            if case == "bad_page": result["data"] = "private"
        return result
    native.call = call
    with pytest.raises(B.Refused, match=reason):
        bridge.observe_turn(p["task_id"], native, owner="123")
    assert bridge._path(p["task_id"]).read_bytes() == before
    assert not any(m in {"thread/resume", "thread/start", "turn/start", "thread/inject_items"} for m, _ in native.calls)


@pytest.mark.parametrize("status", ["inProgress", "failed", "interrupted"])
def test_active_or_failed_target_does_not_commit(bridge, status):
    p, native = submitted(bridge)
    native.turn_status = status
    before = bridge._path(p["task_id"]).read_bytes()
    observed = bridge.observe_turn(p["task_id"], native, owner="123")
    assert observed["state"] == "SUBMITTED"
    with pytest.raises(B.Refused, match="TERMINAL_OBSERVATION_REQUIRED"):
        commit_matching(bridge, p["task_id"], observed)
    assert bridge._path(p["task_id"]).read_bytes() == before


def test_paginated_exact_turn_and_bounded_missing_target(bridge):
    p, native = submitted(bridge)
    real_call = native.call
    def call(method, params):
        if method == "thread/turns/list":
            native.calls.append((method, deepcopy(params)))
            if params.get("cursor") == "next":
                return {"data": [{"id": "synthetic-turn", "status": "completed", "items": [
                    {"type": "agentMessage", "phase": "final_answer", "text": "Synthetic final evidence."}]}]}
            return {"data": [{"id": "newer", "status": "completed", "items": []}], "nextCursor": "next"}
        return real_call(method, params)
    native.call = call
    assert bridge.observe_turn(p["task_id"], native, owner="123")["target_turn_state"] == "completed"
    assert native.calls[-1][1]["cursor"] == "next"
    native.calls.clear()
    def endless(method, params):
        if method == "thread/turns/list":
            native.calls.append((method, deepcopy(params)))
            n = len([m for m, _ in native.calls if m == method])
            return {"data": [{"id": f"other-{n}"}], "nextCursor": f"cursor-{n}"}
        return real_call(method, params)
    native.call = endless
    with pytest.raises(B.Refused, match="RECORDED_NATIVE_TURN_NOT_FOUND_WITHIN_LIMIT"):
        bridge.observe_turn(p["task_id"], native, owner="123")
    assert [m for m, _ in native.calls].count("thread/turns/list") == 5
    assert bridge.status(p["task_id"])["state"] == "SUBMITTED"


def test_read_rejection_stops_first_and_preserves_checkpoint(bridge):
    p, native = submitted(bridge)
    native.fail = "thread/read"
    before = bridge._path(p["task_id"]).read_bytes()
    with pytest.raises(B.NativeError):
        bridge.observe_turn(p["task_id"], native, owner="123")
    assert [m for m, _ in native.calls] == ["thread/read"]
    assert bridge._path(p["task_id"]).read_bytes() == before


def test_commit_is_explicit_idempotent_and_lock_guarded(bridge):
    p, native = submitted(bridge)
    observation = bridge.observe_turn(p["task_id"], native, owner="123")
    with bridge._locked(p["task_id"]):
        with pytest.raises(B.Refused, match="TASK_BUSY_OR_STALE_LOCK"):
            commit_matching(bridge, p["task_id"], observation)
    assert bridge.status(p["task_id"])["state"] == "SUBMITTED"
    tampered = deepcopy(observation)
    tampered["item_inventory"].append({"type": "UNKNOWN", "phase": None})
    with pytest.raises(B.Refused, match="TERMINAL_OBSERVATION_REQUIRED"):
        commit_matching(bridge, p["task_id"], tampered)
    with pytest.raises(B.Refused, match="TERMINAL_EVIDENCE_COMPARISON_FAILED"):
        bridge.commit_terminal(p["task_id"], observation,
            expected_final_sha256="0" * 64,
            expected_item_inventory=observation["item_inventory"])
    first = commit_matching(bridge, p["task_id"], observation)
    assert commit_matching(bridge, p["task_id"], observation) == first
    assert bridge.status(p["task_id"])["state"] == "COMPLETED"
    assert not any(m in {"thread/resume", "thread/start", "turn/start", "thread/inject_items"} for m, _ in native.calls)


@pytest.mark.parametrize("mutation", ["final_hash", "all_fields"])
def test_commit_uses_retained_snapshot_after_public_mutation(bridge, monkeypatch, mutation):
    p, native = submitted(bridge)
    task = p["task_id"]
    obs = bridge.observe_turn(task, native, owner="123")
    accepted = deepcopy(obs)
    retained = bridge._terminal_observations[task]
    expected_hash = hashlib.sha256(b"Synthetic final evidence.").hexdigest()
    expected_inventory = [{"type": "agentMessage", "phase": "commentary"},
                          {"type": "agentMessage", "phase": "final_answer"}]
    checked, release = threading.Event(), threading.Event()
    original_read = bridge._read_checkpoint
    outcome = []

    def paused_read(task_id):
        if threading.current_thread().name == "r4-commit":
            checked.set()
            assert release.wait(3)
        return original_read(task_id)

    monkeypatch.setattr(bridge, "_read_checkpoint", paused_read)

    def commit():
        try:
            outcome.append(bridge.commit_terminal(task, obs,
                expected_final_sha256=expected_hash,
                expected_item_inventory=expected_inventory))
        except Exception as exc:
            outcome.append(exc)

    worker = threading.Thread(target=commit, name="r4-commit")
    worker.start()
    try:
        assert checked.wait(3)
        # Commit has validated the evidence and holds the task lock. The
        # caller can still mutate its exported dict and its nested inventory.
        obs["final_sha256"] = "0" * 64
        if mutation == "all_fields":
            obs.update(task_id="0" * 24, state="FAILED", target_turn_state="failed",
                       native_state="systemError", thread_id="other", turn_id="other")
            obs["item_inventory"][0].update(type="commandExecution", phase="commentary")
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive() and len(outcome) == 1
    assert not isinstance(outcome[0], Exception), outcome
    row = bridge._read(task)
    assert outcome[0]["state"] == row["state"] == "COMPLETED"
    assert row["result_sha256"] == expected_hash
    assert row["terminal_evidence_sha256"] == retained.evidence_sha256
    assert row["terminal_checkpoint_sha256"] == retained.checkpoint_sha256
    assert retained.public_json == B._canonical(accepted)
    committed = bridge._path(task).read_bytes()
    # Repeating the original accepted observation remains byte-preserving.
    assert bridge.commit_terminal(task, accepted,
        expected_final_sha256=expected_hash,
        expected_item_inventory=expected_inventory) == outcome[0]
    assert bridge._path(task).read_bytes() == committed


@pytest.mark.parametrize("owner", [None, "", "bad", "456"])
def test_observation_checks_expected_owner_before_any_rpc(bridge, owner):
    p, native = submitted(bridge)
    before = bridge._path(p["task_id"]).read_bytes()
    with pytest.raises(B.Refused):
        bridge.observe_turn(p["task_id"], native, owner=owner)
    assert native.calls == []
    assert bridge._path(p["task_id"]).read_bytes() == before


@pytest.mark.parametrize("change", ["owner_binding", "payload", "updated_utc", "extra", "whitespace"])
def test_observation_is_bound_to_exact_checkpoint_revision(bridge, change):
    p, native = submitted(bridge)
    obs = bridge.observe_turn(p["task_id"], native, owner="123")
    with bridge._locked(p["task_id"]):
        row = bridge._read(p["task_id"])
        if change == "payload":
            row.update(prompt="different synthetic prompt",
                       prompt_sha256=hashlib.sha256(b"different synthetic prompt").hexdigest())
        elif change == "whitespace":
            bridge._path(p["task_id"]).write_bytes(bridge._path(p["task_id"]).read_bytes() + b"\n")
        else:
            row[change] = "different"
        if change != "whitespace":
            bridge._save(row)
    before = bridge._path(p["task_id"]).read_bytes()
    with pytest.raises(B.Refused, match="TERMINAL_CHECKPOINT_CHANGED"):
        commit_matching(bridge, p["task_id"], obs)
    assert bridge._path(p["task_id"]).read_bytes() == before
    assert "owner_binding" not in obs and "prompt_sha256" not in obs and "prompt" not in obs


@pytest.mark.parametrize("invalidation", ["owner", "rpc", "metadata", "state"])
def test_commit_rechecks_retained_observation_after_lock_wait(bridge, monkeypatch, invalidation):
    p, native = submitted(bridge)
    obs = bridge.observe_turn(p["task_id"], native, owner="123")
    entered, release = threading.Event(), threading.Event()
    original_lock = bridge._locked
    outcome = []
    @contextmanager
    def waiting_lock(task):
        if threading.current_thread().name == "r3-commit":
            entered.set()
            assert release.wait(3)
        with original_lock(task):
            yield
    monkeypatch.setattr(bridge, "_locked", waiting_lock)
    def commit():
        try:
            commit_matching(bridge, p["task_id"], obs)
            outcome.append("accepted")
        except B.Refused:
            outcome.append("refused")
    worker = threading.Thread(target=commit, name="r3-commit")
    worker.start()
    try:
        assert entered.wait(3)
        owner = "456" if invalidation == "owner" else "123"
        if invalidation == "rpc":
            native.fail = "thread/read"
        if invalidation == "metadata":
            real_call = native.call
            def malformed(method, params):
                result = real_call(method, params)
                if method == "thread/read":
                    result["thread"]["status"] = None
                return result
            native.call = malformed
        if invalidation == "state":
            with bridge._locked(p["task_id"]):
                row = bridge._read(p["task_id"])
                row["state"] = "FAILED"
                bridge._save(row)
            assert bridge.observe_turn(p["task_id"], native, owner=owner)["state"] == "FAILED"
        else:
            with pytest.raises((B.Refused, B.NativeError)):
                bridge.observe_turn(p["task_id"], native, owner=owner)
        assert p["task_id"] not in bridge._terminal_observations
        before = bridge._path(p["task_id"]).read_bytes()
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive() and outcome == ["refused"]
    assert bridge._path(p["task_id"]).read_bytes() == before


@pytest.mark.parametrize("field", ["result_sha256", "terminal_evidence_sha256",
                                  "terminal_checkpoint_sha256", "owner_binding", "updated_utc"])
def test_conflicting_recommit_preserves_completed_bytes(bridge, field):
    p, native = submitted(bridge)
    obs = bridge.observe_turn(p["task_id"], native, owner="123")
    commit_matching(bridge, p["task_id"], obs)
    committed = bridge._path(p["task_id"]).read_bytes()
    assert commit_matching(bridge, p["task_id"], obs)["state"] == "COMPLETED"
    assert bridge._path(p["task_id"]).read_bytes() == committed
    with bridge._locked(p["task_id"]):
        row = bridge._read(p["task_id"])
        row[field] = "conflicting"
        bridge._save(row)
    before = bridge._path(p["task_id"]).read_bytes()
    with pytest.raises(B.Refused, match="TERMINAL_COMPLETION_CONFLICT"):
        commit_matching(bridge, p["task_id"], obs)
    assert bridge._path(p["task_id"]).read_bytes() == before


@pytest.mark.parametrize("status", [None, "active", {}, {"type": ""}, {"type": "unknown"},
    {"type": []}, {"type": "active"}, {"type": "active", "activeFlags": None},
    {"type": "active", "activeFlags": ["unknown"]},
    {"type": "active", "activeFlags": [{}]}, {"type": "systemError"}])
def test_malformed_or_unreadable_thread_status_stops_without_commit(bridge, status):
    p, native = submitted(bridge)
    before = bridge._path(p["task_id"]).read_bytes()
    real_call = native.call
    def call(method, params):
        result = real_call(method, params)
        if method == "thread/read":
            result["thread"]["status"] = status
        return result
    native.call = call
    with pytest.raises(B.Refused, match="NATIVE_THREAD_"):
        bridge.observe_turn(p["task_id"], native, owner="123")
    assert [m for m, _ in native.calls] == ["thread/read"]
    assert bridge._path(p["task_id"]).read_bytes() == before
    assert p["task_id"] not in bridge._terminal_observations


@pytest.mark.parametrize("phase", ["unknown-secret-phase", "", 1, False, {}, []])
def test_unknown_phase_is_refused_without_exporting_arbitrary_value(bridge, phase):
    p, native = submitted(bridge)
    real_call = native.call
    def call(method, params):
        result = real_call(method, params)
        if method == "thread/turns/list":
            result["data"][0]["items"].insert(0, {"type": "reasoning", "phase": phase})
        return result
    native.call = call
    before = bridge._path(p["task_id"]).read_bytes()
    with pytest.raises(B.Refused, match="^NATIVE_ITEM_PHASE_INVALID$"):
        bridge.observe_turn(p["task_id"], native, owner="123")
    assert bridge._path(p["task_id"]).read_bytes() == before
    assert p["task_id"] not in bridge._terminal_observations


@pytest.mark.parametrize("phase_present", [True, False])
def test_absent_or_null_phase_is_preserved_and_final_hash_trims_utf8(bridge, phase_present):
    p, native = submitted(bridge)
    real_call = native.call
    def call(method, params):
        result = real_call(method, params)
        if method == "thread/turns/list":
            reasoning = {"type": "reasoning"}
            if phase_present:
                reasoning["phase"] = None
            result["data"][0]["items"] = [reasoning, {"type": "agentMessage",
                "phase": "final_answer", "text": " \nC03_READONLY_OK\t "}]
        return result
    native.call = call
    obs = bridge.observe_turn(p["task_id"], native, owner="123")
    assert obs["item_inventory"] == [{"type": "reasoning", "phase": None},
                                    {"type": "agentMessage", "phase": "final_answer"}]
    result = bridge.commit_terminal(p["task_id"], obs,
        expected_final_sha256=hashlib.sha256(b"C03_READONLY_OK").hexdigest(),
        expected_item_inventory=[{"type": "reasoning", "phase": None},
                                 {"type": "agentMessage", "phase": "final_answer"}])
    assert result["state"] == "COMPLETED"


@pytest.mark.parametrize("method", ["thread/read", "thread/turns/list"])
def test_first_rpc_rejection_retains_safe_diagnostic_and_never_retries(bridge, method):
    p, native = submitted(bridge)
    # Seed a successful observation, then prove that uncertainty invalidates it.
    bridge.observe_turn(p["task_id"], native, owner="123")
    native.calls.clear()
    real_call = native.call
    attempts = []
    diagnostic = B.safe_rpc_diagnostic(method, 7, {"code": -32602,
        "message": "synthetic secret", "data": {"secret": "synthetic secret"}})
    def reject_once(m, params):
        attempts.append(m)
        if m == method and attempts.count(m) == 1:
            raise B.NativeError("NATIVE_RPC_REJECTED", diagnostic=diagnostic)
        return real_call(m, params)
    native.call = reject_once
    before = bridge._path(p["task_id"]).read_bytes()
    with pytest.raises(B.NativeError) as caught:
        bridge.observe_turn(p["task_id"], native, owner="123")
    assert caught.value.diagnostic == diagnostic
    assert "secret" not in json.dumps(caught.value.diagnostic)
    assert attempts == (["thread/read"] if method == "thread/read" else ["thread/read", method])
    assert bridge._path(p["task_id"]).read_bytes() == before
    assert p["task_id"] not in bridge._terminal_observations


def test_exported_observation_cannot_reconstruct_private_capability(bridge):
    p, native = submitted(bridge)
    obs = bridge.observe_turn(p["task_id"], native, owner="123")
    restarted = B.Bridge(bridge.workspace, bridge.root.parents[1], enabled=True)
    with pytest.raises(B.Refused, match="TERMINAL_OBSERVATION_REQUIRED"):
        commit_matching(restarted, p["task_id"], json.loads(json.dumps(obs)))
    assert bridge.status(p["task_id"])["state"] == "SUBMITTED"


def stored_thread_native(native, *, status=None, thread_changes=None):
    """Synthetic stored history; never resume/load a native thread.

    r5 intentionally replaces r4's valid-notLoaded refusal expectation, per
    C03/metadata-diagnostic-r1/actual-review/INDEPENDENT_REVIEW.md and the
    retained 20261027 ThreadStatus/ThreadRead/ThreadTurnsList native schemas.
    """
    real_call = native.call
    def call(method, params):
        result = real_call(method, params)
        if method == "thread/read":
            result["thread"]["status"] = deepcopy(status if status is not None else {"type": "notLoaded"})
            result["thread"].update(deepcopy(thread_changes or {}))
        return result
    native.call = call


def test_stored_thread_not_loaded_completed_target_uses_existing_pagination(bridge):
    p, native = submitted(bridge)
    stored_thread_native(native)
    real_call = native.call
    def call(method, params):
        result = real_call(method, params)
        if method == "thread/turns/list" and "cursor" not in params:
            return {"data": [{"id": "newer-turn", "status": "inProgress"}], "nextCursor": "older"}
        return result
    native.call = call
    before = bridge._path(p["task_id"]).read_bytes()
    obs = bridge.observe_turn(p["task_id"], native, owner="123")
    assert obs["native_state"] == "notLoaded" and obs["target_turn_state"] == "completed"
    assert obs["state"] == "SUBMITTED"
    assert obs["final_sha256"] == hashlib.sha256(b"Synthetic final evidence.").hexdigest()
    assert obs["item_inventory"] == [{"type": "agentMessage", "phase": "commentary"},
                                      {"type": "agentMessage", "phase": "final_answer"}]
    assert "Synthetic final evidence." not in json.dumps(obs)
    assert native.calls == [
        ("thread/read", {"threadId": "synthetic-native-thread", "includeTurns": False}),
        ("thread/turns/list", {"threadId": "synthetic-native-thread", "limit": 20,
                               "itemsView": "full", "sortDirection": "desc"}),
        ("thread/turns/list", {"threadId": "synthetic-native-thread", "limit": 20,
                               "itemsView": "full", "sortDirection": "desc", "cursor": "older"})]
    assert bridge._path(p["task_id"]).read_bytes() == before
    assert p["task_id"] in bridge._terminal_observations


@pytest.mark.parametrize("target_status", ["inProgress", "failed", "interrupted"])
def test_stored_thread_not_loaded_noncompleted_target_cannot_commit(bridge, target_status):
    p, native = submitted(bridge)
    bridge.observe_turn(p["task_id"], native, owner="123")
    native.calls.clear()
    stored_thread_native(native)
    native.turn_status = target_status
    before = bridge._path(p["task_id"]).read_bytes()
    obs = bridge.observe_turn(p["task_id"], native, owner="123")
    assert obs["state"] == "SUBMITTED" and obs["native_state"] == "notLoaded"
    assert obs["target_turn_state"] == ("active" if target_status == "inProgress" else target_status)
    assert p["task_id"] not in bridge._terminal_observations
    with pytest.raises(B.Refused, match="^TERMINAL_OBSERVATION_REQUIRED$"):
        commit_matching(bridge, p["task_id"], obs)
    assert [m for m, _ in native.calls] == ["thread/read", "thread/turns/list"]
    assert bridge._path(p["task_id"]).read_bytes() == before


def test_stored_thread_system_error_refuses_before_paging_with_safe_subtype(bridge, capsys):
    p, native = submitted(bridge)
    bridge.observe_turn(p["task_id"], native, owner="123")
    native.calls.clear()
    stored_thread_native(native, status={"type": "systemError", "message": "SYNTHETIC_PRIVATE_BODY"},
                         thread_changes={"preview": "SYNTHETIC_PRIVATE_BODY"})
    before = bridge._path(p["task_id"]).read_bytes()
    with pytest.raises(B.Refused, match="^NATIVE_THREAD_NOT_READABLE$") as caught:
        bridge.observe_turn(p["task_id"], native, owner="123")
    assert caught.value.diagnostic == {"status_type": "systemError"}
    safe = str(caught.value) + repr(caught.value) + json.dumps(caught.value.diagnostic)
    assert "SYNTHETIC_PRIVATE_BODY" not in safe
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert [m for m, _ in native.calls] == ["thread/read"]
    assert p["task_id"] not in bridge._terminal_observations
    assert bridge._path(p["task_id"]).read_bytes() == before


@pytest.mark.parametrize("changes,reason", [
    ({"id": "wrong-thread"}, "NATIVE_THREAD_ID_MISMATCH"),
    ({"id": None}, "NATIVE_THREAD_ID_MISMATCH"),
    ({"id": []}, "NATIVE_THREAD_ID_MISMATCH"),
    ({"cwd": "wrong-workspace"}, "NATIVE_WORKSPACE_MISMATCH"),
    ({"status": {"type": "SYNTHETIC_PRIVATE_BODY"}}, "NATIVE_THREAD_STATUS_INVALID"),
    ({"status": {"type": []}}, "NATIVE_THREAD_STATUS_INVALID"),
    ({"status": {"type": "active"}}, "NATIVE_THREAD_STATUS_INVALID"),
    ({"status": {"type": "active", "activeFlags": "waitingOnApproval"}}, "NATIVE_THREAD_STATUS_INVALID"),
    ({"status": {"type": "active", "activeFlags": [True]}}, "NATIVE_THREAD_STATUS_INVALID"),
    ({"status": {"type": "active", "activeFlags": ["SYNTHETIC_PRIVATE_BODY"]}}, "NATIVE_THREAD_STATUS_INVALID"),
])
def test_stored_thread_invalid_metadata_not_classified_or_paged(bridge, changes, reason):
    p, native = submitted(bridge)
    bridge.observe_turn(p["task_id"], native, owner="123")
    native.calls.clear()
    stored_thread_native(native, thread_changes=changes)
    before = bridge._path(p["task_id"]).read_bytes()
    with pytest.raises(B.Refused, match="^" + reason + "$") as caught:
        bridge.observe_turn(p["task_id"], native, owner="123")
    assert caught.value.diagnostic is None
    assert [m for m, _ in native.calls] == ["thread/read"]
    assert bridge._path(p["task_id"]).read_bytes() == before
    assert p["task_id"] not in bridge._terminal_observations


@pytest.mark.parametrize("change,reason", [
    ("missing", "RECORDED_NATIVE_TURN_NOT_FOUND_WITHIN_LIMIT"),
    ("wrong_thread", "NATIVE_TURN_THREAD_MISMATCH"),
    ("bad_status", "NATIVE_TURN_STATUS_INVALID"),
    ("bad_items", "NATIVE_TURN_ITEMS_INVALID"),
    ("bad_phase", "NATIVE_ITEM_PHASE_INVALID"),
    ("missing_final", "NATIVE_FINAL_ANSWER_UNVERIFIED"),
    ("bad_page", "NATIVE_TURN_PAGE_INVALID"),
])
@pytest.mark.parametrize("native_state", ["notLoaded", "idle", "active"])
def test_stored_thread_target_validation_retains_only_validated_subtype(bridge, change, reason, native_state):
    p, native = submitted(bridge)
    bridge.observe_turn(p["task_id"], native, owner="123")
    native.calls.clear()
    status = {"type": native_state}
    if native_state == "active":
        status["activeFlags"] = ["waitingOnUserInput"]
    stored_thread_native(native, status=status)
    real_call = native.call
    def call(method, params):
        result = real_call(method, params)
        if method == "thread/turns/list":
            turn = result["data"][0]
            if change == "missing":
                turn["id"] = "other-turn"
            elif change == "wrong_thread":
                turn["threadId"] = "wrong-thread"
            elif change == "bad_status":
                turn["status"] = "SYNTHETIC_PRIVATE_BODY"
            elif change == "bad_items":
                turn["items"] = None
            elif change == "bad_phase":
                turn["items"][0]["phase"] = "SYNTHETIC_PRIVATE_BODY"
            elif change == "missing_final":
                turn["items"] = []
            else:
                result["data"] = None
        return result
    native.call = call
    before = bridge._path(p["task_id"]).read_bytes()
    with pytest.raises(B.Refused, match="^" + reason + "$") as caught:
        bridge.observe_turn(p["task_id"], native, owner="123")
    assert caught.value.diagnostic == {"status_type": native_state}
    assert "SYNTHETIC_PRIVATE_BODY" not in json.dumps(caught.value.diagnostic)
    assert [m for m, _ in native.calls] == ["thread/read", "thread/turns/list"]
    assert bridge._path(p["task_id"]).read_bytes() == before
    assert p["task_id"] not in bridge._terminal_observations


def test_stored_thread_missing_target_still_stops_after_five_pages(bridge):
    p, native = submitted(bridge)
    stored_thread_native(native)
    real_call = native.call
    def call(method, params):
        result = real_call(method, params)
        if method == "thread/turns/list":
            count = sum(m == method for m, _ in native.calls)
            return {"data": [{"id": f"other-{count}"}], "nextCursor": f"cursor-{count}"}
        return result
    native.call = call
    before = bridge._path(p["task_id"]).read_bytes()
    with pytest.raises(B.Refused, match="^RECORDED_NATIVE_TURN_NOT_FOUND_WITHIN_LIMIT$") as caught:
        bridge.observe_turn(p["task_id"], native, owner="123")
    assert caught.value.diagnostic == {"status_type": "notLoaded"}
    assert [m for m, _ in native.calls] == ["thread/read"] + ["thread/turns/list"] * 5
    assert all(params.get("limit") == 20 for m, params in native.calls if m == "thread/turns/list")
    assert bridge._path(p["task_id"]).read_bytes() == before
    assert p["task_id"] not in bridge._terminal_observations


@pytest.mark.parametrize("method", ["thread/read", "thread/turns/list"])
def test_stored_thread_first_rpc_error_identity_and_diagnostic_unchanged(bridge, method):
    p, native = submitted(bridge)
    bridge.observe_turn(p["task_id"], native, owner="123")
    stored_thread_native(native)
    native.calls.clear()
    real_call = native.call
    attempts = []
    diagnostic = B.safe_rpc_diagnostic(method, 19, {"code": -32602, "message": "SYNTHETIC_PRIVATE_BODY"})
    error = B.NativeError("NATIVE_RPC_REJECTED", diagnostic=diagnostic)
    def call(m, params):
        attempts.append(m)
        if m == method:
            raise error
        return real_call(m, params)
    native.call = call
    before = bridge._path(p["task_id"]).read_bytes()
    with pytest.raises(B.NativeError) as caught:
        bridge.observe_turn(p["task_id"], native, owner="123")
    assert caught.value is error and caught.value.diagnostic is diagnostic
    assert attempts == (["thread/read"] if method == "thread/read" else ["thread/read", method])
    assert bridge._path(p["task_id"]).read_bytes() == before
    assert p["task_id"] not in bridge._terminal_observations


@pytest.mark.parametrize("status", ["notLoaded", "idle", "active", "systemError",
                                  None, "SYNTHETIC_PRIVATE_BODY", [], {}, True])
def test_stored_thread_refusal_diagnostic_accepts_only_enum(status):
    error = B.Refused("FIXED_REASON", native_state=status)
    expected = {"status_type": status} if isinstance(status, str) and status in {
        "notLoaded", "idle", "active", "systemError"} else None
    assert error.diagnostic == expected
    assert str(error) == "FIXED_REASON" and error.args == ("FIXED_REASON",)
    assert "SYNTHETIC_PRIVATE_BODY" not in repr(error) + json.dumps(error.diagnostic)
