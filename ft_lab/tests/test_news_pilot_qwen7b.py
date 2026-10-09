"""Current local article pilot: all calls are fakes; no model/GPU/network."""
import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from ft_lab import news_pilot_qwen7b as P


def _manifest():
    docs = []
    for i in range(40):
        excerpt = f"Example {i} reported revenue of $12 million on October 9, 2026."
        docs.append({"id": f"source-{i}", "split": "dev" if i % 2 == 0 else "heldout",
                     "excerpt": excerpt, "content_sha256": P.digest(excerpt.encode()),
                     "gold": {"entity_aliases": [f"Example {i}"], "event_type": "earnings_report",
                              "event_date": None, "date_source_span": None,
                              "required_numbers": ["$12 million"], "evidence_spans": ["reported revenue"]}})
    m = {"schema": P.SCHEMA, "acceptance": {"event_correct": 18, "entity_correct": 19,
         "date_correct": 19, "numbers_correct": 19, "evidence_correct": 19,
         "maximum_abstentions": 2, "maximum_critical_errors": 0}, "documents": docs}
    m["freeze_sha256"] = P.digest(P.canonical(m))
    return m


def _prediction(doc):
    return {"entity": doc["gold"]["entity_aliases"][0], "event_type": "earnings_report",
            "event_date": None, "date_precision": "unknown", "numbers": ["$12 million"],
            "evidence_spans": ["reported revenue"], "abstain": False}


def test_private_manifest_freeze_rejects_changed_gold(tmp_path):
    m = _manifest()
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(m), encoding="utf-8")
    assert P.freeze_manifest(path)["freeze_sha256"] == m["freeze_sha256"]
    m["documents"][0]["gold"]["event_type"] = "no_event"
    path.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ValueError, match="freeze"):
        P.freeze_manifest(path)


def test_schema_refuses_extra_keys_nan_and_unsupported_spans():
    excerpt = "Example reports $12 million."
    good = {"entity": "Example", "event_type": "earnings_report", "event_date": None,
            "date_precision": "unknown", "numbers": ["$12 million"],
            "evidence_spans": ["reports"], "abstain": False}
    assert P.parse_reply(json.dumps(good), excerpt) == good
    for bad in (dict(good, tool_call="shell"), dict(good, numbers=["$13 million"]),
                dict(good, numbers=[float("nan")]), dict(good, event_date="2026-02-30")):
        with pytest.raises((ValueError, TypeError)):
            P.parse_reply(json.dumps(bad), excerpt)
    with pytest.raises(P.PilotValidationError, match="malformed_json"):
        P.parse_reply(json.dumps(good)[:-1] + ',"entity":"Other"}', excerpt)
    exact = dict(good, evidence_spans=["Example reports", "$12 million"])
    assert P.parse_reply(json.dumps(exact), excerpt)["evidence_spans"] == exact["evidence_spans"]
    with pytest.raises(P.PilotValidationError, match="unsupported_span"):
        P.parse_reply(json.dumps(dict(good, evidence_spans=["A" * 181])), "Example " + "A" * 181)


def test_result_key_and_score_bind_every_version_and_id():
    m = _manifest(); h = "a" * 64
    rows = {}
    for d in m["documents"]:
        key = P.row_key(d, manifest_hash=m["freeze_sha256"], model_hash=h)
        rows[key] = {"id": d["id"], "split": d["split"], "model_sha256": h,
                     "prompt_version": P.PROMPT_VERSION, "schema": P.SCHEMA,
                     "manifest_sha256": m["freeze_sha256"], "content_sha256": d["content_sha256"],
                     "status": "OK", "raw_reply": json.dumps(_prediction(d)),
                     "raw_sha256": P.digest(json.dumps(_prediction(d)).encode()),
                     "prediction": _prediction(d)}
    state = {"freeze_sha256": m["freeze_sha256"], "model_sha256": h,
             "prompt_version": P.PROMPT_VERSION, "schema": P.SCHEMA, "rows": rows}
    assert P.score(m, state, split="heldout", model_hash=h)["pilot_quality_pass"] is True
    mixed = copy.deepcopy(state)
    mixed["rows"][next(iter(mixed["rows"]))]["model_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="provenance"):
        P.score(m, mixed, split="heldout", model_hash=h)
    duplicate = copy.deepcopy(state)
    duplicate["rows"]["unexpected"] = copy.deepcopy(next(iter(rows.values())))
    with pytest.raises(ValueError, match="identity"):
        P.score(m, duplicate, split="heldout", model_hash=h)
    wrong_split = copy.deepcopy(state)
    wrong_split["rows"][next(iter(rows))]["split"] = "heldout"
    with pytest.raises(ValueError, match="provenance"):
        P.score(m, wrong_split, split="heldout", model_hash=h)
    invented = copy.deepcopy(state)
    first_heldout = next(k for k, d in ((P.row_key(d, manifest_hash=m["freeze_sha256"], model_hash=h), d)
                                  for d in m["documents"] if d["split"] == "heldout"))
    bad = dict(_prediction(next(d for d in m["documents"] if d["id"] == invented["rows"][first_heldout]["id"])),
               entity="Invented", abstain=True)
    invented["rows"][first_heldout].update(status="INVALID_OUTPUT", prediction=None,
        raw_reply=json.dumps(bad), raw_sha256=P.digest(json.dumps(bad).encode()),
        validation_category="unsupported_entity")
    scored = P.score(m, invented, split="heldout", model_hash=h)
    assert scored["critical_errors"] == 1 and scored["pilot_quality_pass"] is False
    precision = copy.deepcopy(state)
    pred = dict(precision["rows"][first_heldout]["prediction"], date_precision="month")
    precision["rows"][first_heldout].update(prediction=pred, raw_reply=json.dumps(pred),
                                               raw_sha256=P.digest(json.dumps(pred).encode()))
    assert P.score(m, precision, split="heldout", model_hash=h)["date_correct"] == 19


def test_one_owned_model_lifetime_and_atomic_resume(tmp_path, monkeypatch):
    m = _manifest(); model = tmp_path / "Qwen2.5-7B-test.gguf"; model.write_bytes(b"fake")
    calls = []

    class Life:
        LLAMA_MODEL = model
        LLAMA_HOST = "127.0.0.1"
        LLAMA_PORT = 8080
        live = False
        token = None
        @staticmethod
        def hold_path(): return tmp_path / "hold"
        @staticmethod
        def hold_path(): return tmp_path / "hold"
        @staticmethod
        def status(): return {"listening": Life.live, "pid": 123 if Life.live else None}
        @staticmethod
        def _read_owner(): return {"pid": 123 if Life.live else None, "owner_pid": __import__("os").getpid(),
                                   "attempt_token": Life.token, "process_created_ts": 1.0}
        @staticmethod
        def pid_alive(pid): return Life.live

        @staticmethod
        def start(*args, **kwargs):
            calls.append("start"); Life.token = kwargs["attempt_token"]; Life.live = True
            return {"ok": True, "action": "started", "pid": 123}

        @staticmethod
        def owning_instance(owner=None):
            return {"is_me": True}

        @staticmethod
        def stop_if_owned():
            calls.append("stop"); Life.live = False; return {"action": "stopped"}

    monkeypatch.setattr(P, "served_model_id", lambda ls: "Qwen2.5-7B-test.gguf")
    monkeypatch.setattr(P, "process_birth", lambda pid: 1.0 if Life.live else None)

    def fake_complete(_name, prompt, **kwargs):
        calls.append("infer")
        assert "at most 180 characters" in kwargs["system"]
        assert "exact contiguous substring" in kwargs["system"]
        assert "multiple short spans" in kwargs["system"]
        d = next(d for d in m["documents"] if d["excerpt"] in prompt)
        pred = _prediction(d)
        if d["id"] == "source-2":
            pred = dict(pred, evidence_spans=["not in source"])
        return SimpleNamespace(text=json.dumps(pred), model="local", latency_s=0.1,
                               prompt_tokens=50, completion_tokens=30)

    out = tmp_path / "results.json"
    reservation = {"test": True}
    probe = lambda *args, **kwargs: {"test": True}
    P.run(m, out=out, split="dev", limit=2, complete=fake_complete, lifecycle=Life,
          reservation=reservation, preflight_probe=probe, memory_probe=lambda: 3.5)
    P.run(m, out=out, split="dev", limit=2, complete=fake_complete, lifecycle=Life,
          reservation=reservation, preflight_probe=probe, memory_probe=lambda: 3.5)
    assert calls == ["start", "infer", "infer", "stop"]
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["paid_calls"] == 0 and len(saved["rows"]) == 2
    assert saved["cleanup"]["confirmed"] is True
    invalid = next(r for r in saved["rows"].values() if r["id"] == "source-2")
    assert invalid["status"] == "INVALID_OUTPUT"
    assert invalid["validation_error"] == {"type": "PilotValidationError", "category": "unsupported_span"}
    assert invalid["served_model"] == "Qwen2.5-7B-test.gguf" and invalid["reply_model"] == "local"
    assert (invalid["latency_s"], invalid["tokens_in"], invalid["tokens_out"]) == (0.1, 50, 30)
    assert invalid["raw_sha256"] == P.digest(invalid["raw_reply"].encode())
    assert P.score(m, saved, split="dev", model_hash=saved["model_sha256"])["critical_errors"] == 1


def test_preflight_refuses_low_ram_hold_listener_and_protected_window(tmp_path):
    now = datetime(2026, 10, 9, 2, 0, tzinfo=timezone.utc)
    class Life:
        @staticmethod
        def hold_path(): return tmp_path / "HOLD"
        @staticmethod
        def status(): return {"listening": False}
    r = {"start_utc": (now - timedelta(minutes=1)).isoformat(),
         "end_utc": (now + timedelta(hours=1)).isoformat(),
         "manifest_sha256": "abc", "operator": "operator", "reviewed_commit": "reviewed",
         "max_documents": 2}
    kw = dict(manifest_hash="abc", limit=2, ls=Life, now=now,
              ram_probe=lambda: 12, gpu_probe=lambda: {"used_mib": 100, "total_mib": 12000},
              code_revision="reviewed")
    assert P.preflight(r, **kw)["hold_clear"]
    with pytest.raises(RuntimeError, match="RAM"):
        P.preflight(r, **(kw | {"ram_probe": lambda: 2.85}))
    Life.hold_path().touch()
    with pytest.raises(RuntimeError, match="HOLD"):
        P.preflight(r, **kw)
    Life.hold_path().unlink()
    Life.status = staticmethod(lambda: {"listening": True})
    with pytest.raises(RuntimeError, match="preexisting"):
        P.preflight(r, **kw)
    Life.status = staticmethod(lambda: {"listening": False})
    protected = datetime(2026, 10, 9, 8, 35, tzinfo=timezone.utc)
    r["start_utc"] = (protected - timedelta(minutes=1)).isoformat()
    r["end_utc"] = (protected + timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError, match="protected"):
        P.preflight(r, **(kw | {"now": protected}))


@pytest.mark.parametrize("mode", ["timeout", "model_mismatch", "cleanup_failure", "interrupted"])
def test_lifecycle_failure_paths_and_checkpoint(tmp_path, monkeypatch, mode):
    m = _manifest(); model = tmp_path / "Qwen2.5-7B-test.gguf"; model.write_bytes(b"fake")
    class Life:
        LLAMA_MODEL = model
        LLAMA_HOST = "127.0.0.1"
        LLAMA_PORT = 8080
        live = False
        token = None
        @staticmethod
        def hold_path(): return tmp_path / "hold"
        @staticmethod
        def _read_owner(): return {"pid": 456 if Life.live else None, "owner_pid": os.getpid(),
                                   "attempt_token": Life.token, "process_created_ts": 1.0}
        @staticmethod
        def owning_instance(owner=None): return {"is_me": True}
        @staticmethod
        def status(): return {"listening": Life.live and mode != "timeout",
                              "pid": 456 if Life.live and mode != "timeout" else None}
        @staticmethod
        def pid_alive(pid): return Life.live
        @staticmethod
        def start(*args, **kwargs):
            Life.token = kwargs["attempt_token"]; Life.live = True
            return {"ok": mode != "timeout", "action": "timeout" if mode == "timeout" else "started", "pid": 456}
        @staticmethod
        def stop_if_owned():
            if mode != "cleanup_failure": Life.live = False
            return {"action": "stopped" if not Life.live else "failed"}
    monkeypatch.setattr(P, "served_model_id", lambda ls: (_ for _ in ()).throw(RuntimeError("model mismatch"))
                        if mode == "model_mismatch" else "Qwen2.5-7B-test.gguf")
    monkeypatch.setattr(P, "process_birth", lambda pid: 1.0 if Life.live else None)
    if mode == "timeout":
        def fake_kill(args, **kwargs):
            assert args == ["taskkill", "/PID", "456", "/F"]
            Life.live = False
            return SimpleNamespace(returncode=0)
        monkeypatch.setattr(P.qsp, "run", fake_kill)
    calls = []
    def complete(_name, prompt, **kwargs):
        calls.append(1)
        if mode == "interrupted" and len(calls) == 2: raise KeyboardInterrupt()
        d = next(d for d in m["documents"] if d["excerpt"] in prompt)
        return SimpleNamespace(text=json.dumps(_prediction(d)), latency_s=.1,
                               prompt_tokens=10, completion_tokens=10)
    out = tmp_path / "private.json"
    with pytest.raises((RuntimeError, KeyboardInterrupt)):
        P.run(m, out=out, split="dev", limit=2, lifecycle=Life, complete=complete,
              reservation={"test": True}, preflight_probe=lambda *a, **k: {"test": True},
              memory_probe=lambda: 3.5)
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert not out.with_suffix(".lock").exists()
    if mode == "cleanup_failure":
        assert saved["cleanup"]["confirmed"] is False
    else:
        assert saved["cleanup"]["confirmed"] is True and not Life.live
    if mode == "interrupted":
        assert len(saved["rows"]) == 1
        Life.live = False
        P.run(m, out=out, split="dev", limit=2, lifecycle=Life, complete=complete,
              reservation={"test": True}, preflight_probe=lambda *a, **k: {"test": True},
              memory_probe=lambda: 3.5)
        assert len(json.loads(out.read_text(encoding="utf-8"))["rows"]) == 2


def test_gold_date_span_missing_is_value_error(tmp_path):
    m = _manifest(); m["documents"][0]["gold"]["event_date"] = "2026-10-10"
    m["freeze_sha256"] = P.digest(P.canonical({k: v for k, v in m.items() if k != "freeze_sha256"}))
    path = tmp_path / "gold.json"; path.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ValueError, match="date has no source span"):
        P.freeze_manifest(path)


def test_listener_race_never_adopts_or_stops_foreign_server(tmp_path, monkeypatch):
    m = _manifest(); model = tmp_path / "Qwen2.5-7B-test.gguf"; model.write_bytes(b"fake")
    class Life:
        LLAMA_MODEL = model; LLAMA_HOST = "127.0.0.1"; LLAMA_PORT = 8080
        stopped = False
        @staticmethod
        def hold_path(): return tmp_path / "hold"
        @staticmethod
        def status(): return {"listening": True, "pid": 777}
        @staticmethod
        def _read_owner(): return {"pid": 777, "owner_pid": os.getpid(),
                                   "attempt_token": "another-attempt", "process_created_ts": 1.0}
        @staticmethod
        def owning_instance(owner=None): return {"is_me": True}
        @staticmethod
        def start(*args, **kwargs): raise AssertionError("listener should block before start")
        @staticmethod
        def stop_if_owned(): Life.stopped = True
    with pytest.raises(RuntimeError, match="new listener"):
        P.run(m, out=tmp_path / "private.json", split="dev", limit=1, lifecycle=Life,
              reservation={}, preflight_probe=lambda *a, **k: {"clear_at_probe": True})
    assert not Life.stopped


def test_reused_adopted_action_is_never_cleanup_candidate(tmp_path):
    m = _manifest(); model = tmp_path / "Qwen2.5-7B-test.gguf"; model.write_bytes(b"fake")
    class Life:
        LLAMA_MODEL = model; LLAMA_HOST = "127.0.0.1"; LLAMA_PORT = 8080
        calls = 0; stopped = False; token = None
        @staticmethod
        def hold_path(): return tmp_path / "hold"
        @staticmethod
        def status():
            Life.calls += 1
            return {"listening": Life.calls > 1, "pid": 777 if Life.calls > 1 else None}
        @staticmethod
        def _read_owner(): return {"pid": 777, "owner_pid": os.getpid(),
                                   "attempt_token": Life.token, "process_created_ts": 1.0}
        @staticmethod
        def owning_instance(owner=None): return {"is_me": True}
        @staticmethod
        def start(*args, **kwargs):
            Life.token = kwargs["attempt_token"]  # deliberately simulate adopted owner metadata
            return {"ok": True, "action": "reused", "pid": 777}
        @staticmethod
        def stop_if_owned(): Life.stopped = True
    out = tmp_path / "private.json"
    with pytest.raises(RuntimeError, match="cleanup unconfirmed"):
        P.run(m, out=out, split="dev", limit=1, lifecycle=Life,
              reservation={}, preflight_probe=lambda *a, **k: {"clear": True})
    assert not Life.stopped
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["execution"]["launch"] is None and saved["cleanup"]["confirmed"] is False


@pytest.mark.parametrize("receipt", ["missing", "stale", "running", "mismatched_pid"])
def test_completed_checkpoint_requires_matching_cleanup(tmp_path, receipt):
    m = _manifest(); model = tmp_path / "Qwen2.5-7B-test.gguf"; model.write_bytes(b"fake")
    h = P.model_file_hash(model)
    class Life:
        LLAMA_MODEL = model; LLAMA_HOST = "127.0.0.1"; LLAMA_PORT = 8080
        @staticmethod
        def status(): return {"listening": False}
        @staticmethod
        def pid_alive(pid): return False
        @staticmethod
        def start(*args, **kwargs): raise AssertionError("must not start")
    rows = {}
    for d in m["documents"]:
        if d["split"] == "dev":
            rows[P.row_key(d, manifest_hash=m["freeze_sha256"], model_hash=h)] = {
                "id": d["id"], "split": "dev", "model_sha256": h,
                "prompt_version": P.PROMPT_VERSION, "schema": P.SCHEMA,
                "manifest_sha256": m["freeze_sha256"], "content_sha256": d["content_sha256"],
                "status": "OK", "prediction": _prediction(d), "raw_reply": json.dumps(_prediction(d)),
                "raw_sha256": P.digest(json.dumps(_prediction(d)).encode())}
    state = {"freeze_sha256": m["freeze_sha256"], "model_sha256": h,
             "prompt_version": P.PROMPT_VERSION, "schema": P.SCHEMA, "rows": rows}
    if receipt != "missing":
        launch = {"pid": 999, "process_created_ts": 1.0, "attempt_id": "attempt-a"}
        state["execution"] = {"attempt_id": "attempt-a", "status": "CLEANUP_CONFIRMED",
                              "manifest_sha256": m["freeze_sha256"], "model_sha256": h,
                              "prompt_version": P.PROMPT_VERSION, "schema": P.SCHEMA, "launch": launch}
        state["cleanup"] = {"confirmed": True, **launch}
        if receipt == "stale": state["cleanup"]["attempt_id"] = "older-attempt"
        if receipt == "running": state["execution"]["status"] = "RUNNING"
        if receipt == "mismatched_pid": state["cleanup"]["pid"] = 123
    out = tmp_path / "private.json"; out.write_text(json.dumps(state), encoding="utf-8")
    assert P.score(m, state, split="dev", model_hash=h)["pilot_quality_pass"]
    with pytest.raises(RuntimeError, match="cleanup|provenance"):
        P.run(m, out=out, split="dev", limit=20, lifecycle=Life, reservation=None)


def test_new_attempt_invalidates_prior_cleanup_before_start(tmp_path, monkeypatch):
    m = _manifest(); model = tmp_path / "Qwen2.5-7B-test.gguf"; model.write_bytes(b"fake")
    h = P.model_file_hash(model)
    class Life:
        LLAMA_MODEL = model; LLAMA_HOST = "127.0.0.1"; LLAMA_PORT = 8080
        @staticmethod
        def hold_path(): return tmp_path / "hold"
        @staticmethod
        def status(): return {"listening": False}
        @staticmethod
        def pid_alive(pid): return False
        @staticmethod
        def start(*args, **kwargs): raise KeyboardInterrupt()
        @staticmethod
        def _read_owner(): return {}
    d = next(d for d in m["documents"] if d["split"] == "dev")
    key = P.row_key(d, manifest_hash=m["freeze_sha256"], model_hash=h)
    launch = {"pid": 999, "process_created_ts": 1.0, "attempt_id": "old"}
    state = {"freeze_sha256": m["freeze_sha256"], "model_sha256": h,
             "prompt_version": P.PROMPT_VERSION, "schema": P.SCHEMA,
             "rows": {key: {"id": d["id"], "split": "dev", "model_sha256": h,
                            "prompt_version": P.PROMPT_VERSION, "schema": P.SCHEMA,
                            "manifest_sha256": m["freeze_sha256"], "content_sha256": d["content_sha256"],
                            "status": "OK", "prediction": _prediction(d), "raw_reply": json.dumps(_prediction(d)),
                            "raw_sha256": P.digest(json.dumps(_prediction(d)).encode())}},
             "execution": {"attempt_id": "old", "status": "CLEANUP_CONFIRMED",
                           "manifest_sha256": m["freeze_sha256"], "model_sha256": h,
                           "prompt_version": P.PROMPT_VERSION, "schema": P.SCHEMA, "launch": launch},
             "cleanup": {"confirmed": True, **launch}}
    out = tmp_path / "private.json"; out.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(RuntimeError, match="cleanup unconfirmed"):
        P.run(m, out=out, split="dev", limit=2, lifecycle=Life, reservation={},
              preflight_probe=lambda *a, **k: {"clear": True})
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["execution"]["attempt_id"] != "old"
    assert saved["cleanup"]["confirmed"] is False


def test_final_cleanup_receipt_write_failure_blocks_completed_resume(tmp_path, monkeypatch):
    m = _manifest(); model = tmp_path / "Qwen2.5-7B-test.gguf"; model.write_bytes(b"fake")
    class Life:
        LLAMA_MODEL = model; LLAMA_HOST = "127.0.0.1"; LLAMA_PORT = 8080
        live = False; token = None
        @staticmethod
        def hold_path(): return tmp_path / "hold"
        @staticmethod
        def status(): return {"listening": Life.live, "pid": 555 if Life.live else None}
        @staticmethod
        def pid_alive(pid): return Life.live
        @staticmethod
        def _read_owner(): return {"pid": 555 if Life.live else None, "owner_pid": os.getpid(),
                                   "attempt_token": Life.token, "process_created_ts": 1.0}
        @staticmethod
        def owning_instance(owner=None): return {"is_me": True}
        @staticmethod
        def start(*args, **kwargs):
            Life.token = kwargs["attempt_token"]; Life.live = True
            return {"ok": True, "action": "started", "pid": 555}
        @staticmethod
        def stop_if_owned(): Life.live = False; return {"action": "stopped"}
    monkeypatch.setattr(P, "process_birth", lambda pid: 1.0 if Life.live else None)
    monkeypatch.setattr(P, "served_model_id", lambda ls: "Qwen2.5-7B-test.gguf")
    real_write = P.atomic_write
    def fail_final_write(path, state):
        if state.get("execution", {}).get("status") == "CLEANUP_CONFIRMED":
            raise OSError("simulated checkpoint interruption")
        real_write(path, state)
    monkeypatch.setattr(P, "atomic_write", fail_final_write)
    d = next(d for d in m["documents"] if d["split"] == "dev")
    reply = SimpleNamespace(text=json.dumps(_prediction(d)), latency_s=.1,
                            prompt_tokens=10, completion_tokens=10)
    out = tmp_path / "private.json"
    with pytest.raises(OSError, match="simulated"):
        P.run(m, out=out, split="dev", limit=1, lifecycle=Life,
              complete=lambda *a, **k: reply, reservation={},
              preflight_probe=lambda *a, **k: {"clear": True}, memory_probe=lambda: 3.5)
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["rows"]) == 1 and saved["execution"]["status"] == "RUNNING"
    assert saved["cleanup"] is None and not Life.live
    with pytest.raises(RuntimeError, match="cleanup"):
        P.run(m, out=out, split="dev", limit=1, lifecycle=Life, reservation=None)


def test_missing_live_process_birth_never_stops_pid(monkeypatch):
    class Life:
        stopped = False
        @staticmethod
        def _read_owner(): return {"pid": 123, "owner_pid": os.getpid(),
                                   "attempt_token": "fresh", "process_created_ts": 1.0}
        @staticmethod
        def owning_instance(owner=None): return {"is_me": True}
        @staticmethod
        def pid_alive(pid): return True
        @staticmethod
        def status(): return {"listening": True, "pid": 123}
        @staticmethod
        def stop_if_owned(): Life.stopped = True
    monkeypatch.setattr(P, "process_birth", lambda pid: None)
    result = P.cleanup_owned(Life, {"pid": 123, "process_created_ts": 1.0, "attempt_id": "fresh"})
    assert result["confirmed"] is False and not Life.stopped


def test_timeout_unproven_launch_receipt_is_unknown(tmp_path):
    m = _manifest(); model = tmp_path / "Qwen2.5-7B-test.gguf"; model.write_bytes(b"fake")
    class Life:
        LLAMA_MODEL = model; LLAMA_HOST = "127.0.0.1"; LLAMA_PORT = 8080
        live = False; token = None; stopped = False
        @staticmethod
        def hold_path(): return tmp_path / "hold"
        @staticmethod
        def status(): return {"listening": False, "pid": None}
        @staticmethod
        def pid_alive(pid): return Life.live
        @staticmethod
        def _read_owner(): return {"pid": 456 if Life.live else None,
                                   "owner_pid": os.getpid(), "attempt_token": Life.token,
                                   "process_created_ts": None}
        @staticmethod
        def owning_instance(owner=None): return {"is_me": True}
        @staticmethod
        def start(*args, **kwargs):
            Life.token = kwargs["attempt_token"]; Life.live = True
            return {"ok": False, "action": "timeout", "pid": 456}
        @staticmethod
        def stop_if_owned(): Life.stopped = True
    out = tmp_path / "private.json"
    with pytest.raises(RuntimeError, match="cleanup unconfirmed"):
        P.run(m, out=out, split="dev", limit=1, lifecycle=Life, reservation={},
              preflight_probe=lambda *a, **k: {"clear": True})
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert Life.live and not Life.stopped
    assert saved["execution"]["status"] == "CLEANUP_UNKNOWN"
    assert saved["cleanup"]["confirmed"] is False and saved["cleanup"]["pid"] == 456


def test_preflight_refusal_precedes_model_hash(tmp_path, monkeypatch):
    m = _manifest(); model = tmp_path / "Qwen2.5-7B-test.gguf"; model.write_bytes(b"fake")
    class Life:
        LLAMA_MODEL = model; LLAMA_HOST = "127.0.0.1"; LLAMA_PORT = 8080
    monkeypatch.setattr(P, "model_file_hash", lambda path: (_ for _ in ()).throw(AssertionError("hash ran")))
    with pytest.raises(RuntimeError, match="resource refusal"):
        P.run(m, out=tmp_path / "private.json", split="dev", limit=1, lifecycle=Life,
              reservation={}, preflight_probe=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("resource refusal")))
