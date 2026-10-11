"""Synthetic owner alarm checks; no process, network or runtime ledger reads."""
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from backend.services import system_health as SH
from backend.services import task_receipts as TR


@pytest.fixture(autouse=True)
def curated_fixture_services(monkeypatch):
    # These source-owned IDs model a real curated registry, never row-derived IDs.
    names = ("fixture", "missing_service", "owner_paused", "refused_service", "dead_service",
             "fine_failed", "fine_unknown", "verified_pause", "computed_missing")
    existing = {p.name for p in SH.PROBES}
    extra = [SH.Probe(name, "pc", timedelta(days=1), "synthetic source-owned ID", lambda ctx: None)
             for name in names if name not in existing]
    monkeypatch.setattr(SH, "PROBES", (*SH.PROBES, *extra))


def row(verdict="ALIVE", state=None, **kw):
    return {"name": "fixture", "verdict": verdict, "state": state or verdict,
            "evidence_utc": None, "age_s": None, "proof": "fixture producer proof",
            "detail": "fixture", **kw}


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "on_railway", lambda: False)
    SH._API_CACHE.clear()
    ctx = SH.ProbeCtx(optimus_dir=tmp_path, now=datetime.now(timezone.utc), allow_proc=False)
    yield ctx
    SH._API_CACHE.clear()


@pytest.mark.parametrize("state", ["ALIVE", "ALIVE_PROGRESSING", "ALIVE_IDLE_EXPECTED", "ALIVE_OBSERVE_ONLY"])
def test_supported_evidence_backed_alive_contracts(state):
    indicator = SH.row_alarm(row(state=state))
    assert indicator["light"] == "GREEN" and indicator["healthy"]
    assert not indicator["attention_required"]


def test_timestamp_or_existing_static_proof_supported_but_neither_is_unknown():
    stamped = row(proof="", evidence_utc=datetime.now(timezone.utc).isoformat(), age_s=0, cadence_s=300)
    assert SH.row_alarm(stamped)["light"] == "GREEN"
    assert SH.row_alarm(row())["light"] == "GREEN"  # existing static proof, no fake heartbeat
    assert SH.row_alarm(row(proof="", evidence_utc=None))["light"] == "AMBER"


def test_api_cache_requalifies_deadline_without_refreshing_observation(context, monkeypatch):
    observed = context.now
    evidence = row(evidence_utc=observed.isoformat(), evidence_mode="DYNAMIC",
                   valid_until_utc=(observed + timedelta(seconds=1)).isoformat(), age_s=0)
    cached = {"generated_utc": observed.isoformat(), "source": "pc_request", "rows": [evidence]}
    monkeypatch.setattr(SH.time, "time", lambda: 101.0)
    monkeypatch.setattr(SH, "_utcnow", lambda: observed + timedelta(seconds=2))
    monkeypatch.setattr(SH, "run", lambda **kw: pytest.fail("cache must not rerun probes"))
    SH._API_CACHE["v"] = (100.0, cached)
    result = SH.api_block()
    assert result["generated_utc"] == cached["generated_utc"]
    assert result["alarm"]["light"] == "RED"
    assert result["rows"][0]["age_s_now"] == 2
    assert cached["rows"][0] == evidence  # cache inputs stay immutable


@pytest.mark.parametrize("age", [float("nan"), float("inf"), -1, True, "fresh"])
def test_invalid_evidence_age_cannot_read_green(age):
    assert SH.row_alarm(row(age_s=age))["light"] == "AMBER"


@pytest.mark.parametrize("verdict,state", [("DEAD", "DEAD"), ("STALE", "STALE"),
    ("REFUSED", "REFUSED"), ("ALIVE", "DEGRADED"), ("STOPPED_BY_OPERATOR", "DEGRADED")])
def test_failed_coarse_or_fine_state_has_red_precedence(verdict, state):
    assert SH.row_alarm(row(verdict, state))["light"] == "RED"


def test_mixed_unknown_keeps_legacy_exit_code_but_not_healthy():
    rows = [row(), row("UNKNOWN", proof="")]
    assert SH.exit_code(rows) == 0
    indicator = SH.alarm(rows)
    assert indicator["light"] == "AMBER" and not indicator["healthy"]
    assert indicator["light_counts"] == {"RED": 0, "AMBER": 1, "BLUE": 0, "GREEN": 1}


@pytest.mark.parametrize("state", ["STOPPED_BY_OPERATOR", "UNREGISTERED"])
def test_verified_inactive_is_blue_not_broken_or_green(state):
    indicator = SH.alarm([row(), row("STOPPED_BY_OPERATOR", state)])
    assert indicator["light"] == "BLUE" and indicator["status"] == "PAUSED"
    assert not indicator["healthy"] and not indicator["attention_required"]


def test_marker_like_detail_does_not_create_stop_or_healthy_evidence():
    indicator = SH.row_alarm(row("UNKNOWN", proof="", detail="MODEL_SERVER_HOLD exists"))
    assert indicator["light"] == "AMBER"


def test_empty_surface_not_green_and_exit_code_unchanged():
    assert SH.exit_code([]) == 0
    assert SH.alarm([])["reason"] == "EMPTY_SURFACE"
    assert not SH.alarm([])["healthy"]


def fixture_probe(fn, *, needs_proc=False):
    return SH.Probe("fixture", "pc", timedelta(minutes=5), "fixture evidence", fn, needs_proc)


@pytest.mark.parametrize("offset", [-SH.RECEIPT_MAX_AGE_S-1, 60])
def test_old_or_future_pc_health_receipt_cannot_replay_green(context, monkeypatch, offset):
    monkeypatch.setattr(SH, "PROBES", [fixture_probe(lambda ctx: None, needs_proc=True)])
    receipt = {"generated_utc": SH._iso(context.now+timedelta(seconds=offset)),
               "rows": [{**row(), "probe": "fixture"}]}
    rows = SH.run_probes(context, receipt=receipt)
    assert rows[0]["verdict"] == "UNKNOWN" and rows[0]["alarm"]["light"] == "AMBER"


def test_probe_read_exception_alarm_is_attention_without_new_detail_leak(context, monkeypatch):
    def broken(ctx):
        raise OSError("private exception fixture")
    monkeypatch.setattr(SH, "PROBES", [fixture_probe(broken)])
    out = SH.run(ctx=context)
    assert out["alarm"]["light"] == "AMBER"
    assert "private exception fixture" not in json.dumps(out["alarm"])
    assert "private exception fixture" not in json.dumps(out["rows"][0]["alarm"])
    assert "private exception fixture" not in json.dumps(out)


@pytest.mark.parametrize("idle,expected", [(None, "RED"), ("producer declares no new items expected", "GREEN")])
def test_fresh_heartbeat_frozen_substance_surfaces_task_judgement(context, idle, expected):
    name = "FixtureWriter"
    substance = "unchanged real output"
    context.prev_state = {"progress": {name: {"hash": hashlib.sha256(substance.encode()).hexdigest()[:16],
        "first_seen_utc": SH._iso(context.now-timedelta(days=4)), "n_same": 10}}}
    spec = TR.TaskSpec(lambda ctx, task: TR.Reading(stamp=ctx.now-timedelta(minutes=1),
        status="OK", substance=substance, proof="producer receipt", idle_reason=idle), "fixture receipt")
    task = {"Scheduled Task State": "Enabled", "Last Run Time": "-"}
    j = TR.judge(context, name, task, spec)
    indicator = SH.row_alarm(row(j.verdict, j.state, evidence_utc=SH._iso(j.stamp),
        age_s=SH._age(j.stamp, context.now), proof=j.proof))
    assert indicator["light"] == expected
    assert j.state == ("ALIVE_IDLE_EXPECTED" if idle else "STALE")


def test_api_and_render_share_alarm_contract(context, monkeypatch):
    monkeypatch.setattr(SH, "PROBES", [fixture_probe(lambda ctx: SH.ProbeResult(
        "ALIVE", None, None, "static configuration verified", proof="fixture configuration"))])
    monkeypatch.setattr(SH, "make_ctx", lambda **kw: context)
    out = SH.run(ctx=context)
    api = SH.api_block(ttl_s=0)
    assert api["alarm"] == out["alarm"] and api["alarm"]["schema"] == "health_alarm/1"
    assert api["rows"][0]["alarm"] == out["rows"][0]["alarm"]
    assert "alarm GREEN (HEALTHY)" in SH.render_table(out)
    assert "alarm GREEN (HEALTHY)" in SH.render_md(out)
    assert "| GREEN | ALIVE |" in SH.render_md(out)


def test_api_computation_error_never_green_and_does_not_echo_exception(context, monkeypatch):
    def broken(**kw):
        raise OSError("secret-shaped-private-detail")
    monkeypatch.setattr(SH, "make_ctx", broken)
    out = SH.api_block(ttl_s=0)
    assert out["alarm"]["light"] == "AMBER" and out["exit_code"] is None
    assert out["alarm"]["reason"] == "HEALTH_COMPUTATION_UNAVAILABLE"
    assert out["error"] == "OSError" and "secret-shaped" not in json.dumps(out)


def test_api_empty_successful_computation_not_green(context, monkeypatch):
    monkeypatch.setattr(SH, "PROBES", [])
    monkeypatch.setattr(SH, "make_ctx", lambda **kw: context)
    out = SH.api_block(ttl_s=0)
    assert out["rows"] == [] and out["alarm"]["light"] == "AMBER"


def test_unknown_state_does_not_use_green_coarse_verdict():
    assert SH.row_alarm(row(state="UNRECOGNIZED_STATE"))["light"] == "AMBER"


@pytest.mark.parametrize("malformed", [None, {"verdict": []}, {"verdict": "ALIVE", "state": {}, "proof": "fixture"}])
def test_malformed_row_not_green(malformed):
    assert SH.row_alarm(malformed)["light"] == "AMBER"


def test_snapshot_unknown_cannot_green_or_hide_known_red():
    assert SH.alarm([row()], unavailable_reason="STALE_HEALTH_RECEIPT")["light"] == "AMBER"
    indicator = SH.alarm([row("DEAD")], unavailable_reason="STALE_HEALTH_RECEIPT")
    assert indicator["light"] == "RED" and indicator["reason"] == "STALE_HEALTH_RECEIPT"


def test_local_brief_names_unknown_after_faults_and_excludes_verified_pause(context, monkeypatch):
    rows = [row(), row("UNKNOWN", name="missing_service", detail="probe raised OSError: secret-shaped-private-detail"),
            row("STOPPED_BY_OPERATOR", name="owner_paused"), row("REFUSED", name="refused_service"),
            row("DEAD", name="dead_service")]
    monkeypatch.setattr(SH, "newest_receipt", lambda: {"generated_utc": SH._iso(context.now), "rows": rows})
    monkeypatch.setattr(SH, "_utcnow", lambda: context.now)
    monkeypatch.setattr(SH, "disk_status", lambda: {"verdict": "ALIVE", "line": "disk fixture"})
    lines = SH.non_alive_lines(limit=3)
    assert lines[1].startswith("- DEAD dead_service")
    assert lines[2].startswith("- REFUSED refused_service")
    assert lines[3].startswith("- UNKNOWN missing_service -- service evidence unavailable; consult private receipt")
    assert "secret-shaped" not in "\n".join(lines) and "owner_paused" not in "\n".join(lines)


def test_future_receipt_not_used_by_local_brief(context, monkeypatch):
    monkeypatch.setattr(SH, "newest_receipt", lambda: {"generated_utc": SH._iso(context.now+timedelta(minutes=1)), "rows": [row()]})
    monkeypatch.setattr(SH, "_utcnow", lambda: context.now)
    monkeypatch.setattr(SH, "make_ctx", lambda **kw: context)
    monkeypatch.setattr(SH, "run", lambda **kw: {"rows": [row("UNKNOWN", name="computed_missing")]})
    monkeypatch.setattr(SH, "disk_status", lambda: {"verdict": "ALIVE", "line": "disk fixture"})
    assert any("computed_missing" in line for line in SH.non_alive_lines())


@pytest.mark.parametrize("offset,expected", [(86400, "AMBER"), (.001, "AMBER"), (-3600, "RED"), (-30, "GREEN")])
def test_dynamic_evidence_uses_current_clock_not_stored_age(context, offset, expected):
    dynamic = row(evidence_utc=(context.now+timedelta(seconds=offset)).isoformat(),
                  age_s=0, cadence_s=300)
    assert SH.row_alarm(dynamic, now=context.now)["light"] == expected
    assert SH.alarm([dynamic], now=context.now)["light"] == expected


def test_missing_dynamic_expiry_is_attention_but_static_and_idle_preserved(context):
    dynamic = row(evidence_utc=SH._iso(context.now-timedelta(minutes=1)), age_s=0)
    assert SH.row_alarm(dynamic, now=context.now)["reason"] == "EVIDENCE_EXPIRY_UNAVAILABLE"
    assert SH.row_alarm(row(), now=context.now)["light"] == "GREEN"
    assert SH.row_alarm(row(state="ALIVE_IDLE_EXPECTED"), now=context.now)["light"] == "GREEN"


def test_exact_producer_deadline_beats_generic_probe_cadence(context):
    dynamic = row(evidence_utc=SH._iso(context.now-timedelta(hours=1)), age_s=0,
        cadence_s=86400, evidence_mode="DYNAMIC", valid_until_utc=SH._iso(context.now-timedelta(minutes=30)))
    assert SH.row_alarm(dynamic, now=context.now)["reason"] == "EVIDENCE_EXPIRED"


def test_session_contract_preserves_last_closed_data(context):
    last = SH.last_closed_session(context.now)
    evidence = datetime.combine(last, datetime.min.time(), timezone.utc)
    calendar = row(probe="bars_panel", evidence_utc=SH._iso(evidence), age_s=0,
        cadence_s=300, evidence_mode="SESSION_DATA")
    assert SH.row_alarm(calendar, now=context.now)["light"] == "GREEN"


def test_fresh_pc_receipt_recomputes_old_dynamic_age(context, monkeypatch):
    monkeypatch.setattr(SH, "PROBES", [fixture_probe(lambda ctx: None, needs_proc=True)])
    receipt = {"generated_utc": SH._iso(context.now), "rows": [{**row(probe="fixture",
        evidence_utc=SH._iso(context.now-timedelta(hours=1)), age_s=0, cadence_s=300)}]}
    rows = SH.run_probes(context, receipt=receipt)
    assert rows[0]["age_s"] >= 3600 and rows[0]["age_s_now"] >= 3600
    assert rows[0]["alarm"]["light"] == "RED"


def test_task_reader_exception_sanitised_before_full_row_collection(context, monkeypatch):
    def broken(ctx, task):raise OSError("private-shaped task reader exception")
    spec = TR.TaskSpec(broken, "fixture receipt")
    monkeypatch.setattr(TR, "TASK_RECEIPT", {"FixtureWriter": spec})
    monkeypatch.setattr(SH, "_schtasks", lambda ctx: {"FixtureWriter": {"Scheduled Task State": "Enabled"}})
    result = SH.p_scheduled_tasks(context)["FixtureWriter"]
    row_value = SH._row(fixture_probe(lambda ctx: result), "task:FixtureWriter", result)
    assert "private-shaped" not in json.dumps(row_value)
    assert row_value["error_type"] == "OSError"
    assert TR.TASK_RECEIPT["FixtureWriter"] is spec  # no registry mutation


def test_fine_state_failure_and_unsupported_state_named_in_local_brief(context, monkeypatch):
    rows = [row(state="DEGRADED", name="fine_failed"), row(state="UNRECOGNIZED", name="fine_unknown"),
            row("STOPPED_BY_OPERATOR", name="verified_pause")]
    monkeypatch.setattr(SH, "newest_receipt", lambda: {"generated_utc": SH._iso(context.now), "rows": rows})
    monkeypatch.setattr(SH, "_utcnow", lambda: context.now)
    monkeypatch.setattr(SH, "disk_status", lambda: {"verdict": "ALIVE", "line": "disk fixture"})
    text = "\n".join(SH.non_alive_lines())
    assert "DEGRADED fine_failed" in text and "AMBER fine_unknown" in text
    assert "verified_pause" not in text
    faults = SH.fault_rows(rows, now=context.now)
    assert [r["name"] for r in faults] == ["fine_failed", "fine_unknown"]
    assert faults[0]["alarm"]["reason"] == "PROBE_FAILURE"


def test_naive_observation_and_contradictory_deadline_cannot_green(context):
    assert SH.row_alarm(row(), now=context.now.replace(tzinfo=None))["light"] == "AMBER"
    dynamic = row(evidence_utc=SH._iso(context.now), valid_until_utc=SH._iso(context.now-timedelta(hours=1)), cadence_s=300)
    assert SH.row_alarm(dynamic, now=context.now)["light"] == "AMBER"


def test_alarm_publishes_effective_cadence_deadline_and_static_mode(context):
    value = row(evidence_utc=SH._iso(context.now), cadence_s=60)
    indicator = SH.row_alarm(value, now=context.now)
    assert indicator["evidence_mode"] == "DYNAMIC"
    assert indicator["valid_until_utc"] == SH._iso(SH._ts(value["evidence_utc"])+timedelta(seconds=60*(1+SH.GRACE)))
    static = SH.row_alarm(row(), now=context.now)
    assert static["evidence_mode"] == "STATIC_PROOF" and static["valid_until_utc"] is None
    assert value.get("evidence_mode") is None  # qualification does not mutate observations


def test_sim_idle_window_expires_at_next_real_open_and_discloses_calendar(context, monkeypatch):
    opening = datetime(2026, 10, 12, 13, 30, tzinfo=timezone.utc)
    days = [opening.date(), (opening+timedelta(days=1)).date()]
    monkeypatch.setattr(SH, "_sessions", lambda lo, hi: ([d for d in days if lo <= d <= hi], "XNYS"))
    before = opening-timedelta(minutes=1)
    idle = row(state="ALIVE_IDLE_EXPECTED", probe="sim_session", evidence_mode="DECLARED_IDLE",
               evidence_utc=SH._iso(before-timedelta(hours=1)))
    admitted = SH.row_alarm(idle, now=before)
    assert admitted["light"] == "GREEN" and admitted["valid_until_utc"] == SH._iso(opening)
    assert admitted["evidence_calendar"] == "XNYS"
    assert SH.row_alarm(idle, now=opening)["light"] == "RED"
    explicit = {**idle, "valid_until_utc": admitted["valid_until_utc"]}
    assert SH.row_alarm(explicit, now=opening+timedelta(hours=8))["light"] == "RED"
    assert SH.row_alarm(row("STOPPED_BY_OPERATOR", probe="sim_session"), now=opening)["light"] == "BLUE"
    monkeypatch.setattr(SH, "_sessions", lambda lo, hi: ([d for d in days if lo <= d <= hi], "WEEKDAY_APPROX"))
    assert SH.row_alarm(idle, now=before)["evidence_calendar"] == "WEEKDAY_APPROX"


def test_sim_idle_producer_adds_exact_open_deadline(context, monkeypatch):
    opening = context.now+timedelta(hours=2)
    monkeypatch.setattr(SH, "_read_json", lambda path: {"state": "DONE", "ended": SH._iso(context.now-timedelta(hours=1))})
    monkeypatch.setattr(SH, "_sim_owner_row", lambda ctx: (None, None))
    monkeypatch.setattr(SH, "in_session_hours", lambda now: False)
    monkeypatch.setattr(SH, "_next_session_open", lambda now: (opening, "XNYS"))
    value = SH.p_sim_session(context)
    assert value.verdict == "ALIVE" and value.state == "ALIVE_IDLE_EXPECTED"
    assert value.valid_until_utc == SH._iso(opening)


@pytest.mark.parametrize("legacy", ["probe raised OSError: private-fixture", "receipt reader raised ValueError: private-fixture"])
def test_public_legacy_projection_clears_all_exception_payload_fields(legacy):
    original = row("UNKNOWN", detail=legacy, proof="private-fixture", delta="private-fixture")
    safe = SH.public_row(original)
    assert "private-fixture" not in json.dumps(safe)
    assert safe["proof"] == "" and safe["delta"] is None
    assert "private-fixture" in json.dumps(original)  # immutable source remains intact
    assert SH.public_row(safe) == safe
    assert "private-fixture" not in json.dumps(SH.fault_rows([original]))


def test_public_projection_withholds_ordinary_unknown_text_uniformly():
    original = row("UNKNOWN", detail="required writer receipt absent", proof="writer receipt path")
    safe = SH.public_row(original)
    assert safe["detail"] == "service evidence unavailable; consult private receipt"
    assert safe["proof"] == "" and "error_type" not in safe
    assert original["detail"] == "required writer receipt absent"


def test_legacy_copied_receipt_and_api_cache_never_expose_payload(context, monkeypatch):
    original = row("UNKNOWN", probe="fixture", detail="probe raised OSError: private-fixture",
                   proof="private-fixture", delta="private-fixture")
    monkeypatch.setattr(SH, "PROBES", [fixture_probe(lambda ctx: None, needs_proc=True)])
    receipt = {"generated_utc": SH._iso(context.now), "rows": [original]}
    copied = SH.run_probes(context, receipt=receipt)
    assert "private-fixture" not in json.dumps(copied)
    monkeypatch.setattr(SH, "make_ctx", lambda **kw: context)
    monkeypatch.setattr(SH, "_utcnow", lambda: context.now)
    monkeypatch.setattr(SH, "run", lambda **kw: {"generated_utc": SH._iso(context.now), "rows": [original], "counts": {"UNKNOWN": 1}, "exit_code": 3})
    fresh = SH.api_block()
    assert "private-fixture" not in json.dumps(fresh)
    # A pre-existing cache may itself predate the sanitization code.
    SH._API_CACHE["v"] = (SH.time.time(), {**fresh, "rows": [original]})
    assert "private-fixture" not in json.dumps(SH.api_block())
    assert "private-fixture" in json.dumps(receipt)


def test_api_session_identity_survives_cache_and_actual_expiry(context, monkeypatch):
    observed = context.now
    session = observed.date()-timedelta(days=1)
    monkeypatch.setattr(SH, "last_closed_session", lambda now: session if now == observed else session+timedelta(days=1))
    value = row(probe="live_market_loop", evidence_mode="SESSION_DATA", evidence_utc=session.isoformat(), age_s=0)
    monkeypatch.setattr(SH, "make_ctx", lambda **kw: context)
    monkeypatch.setattr(SH, "_utcnow", lambda: observed)
    monkeypatch.setattr(SH, "run", lambda **kw: {"generated_utc": SH._iso(observed), "rows": [value], "counts": {"ALIVE": 1}, "exit_code": 0})
    fresh = SH.api_block()
    assert fresh["rows"][0]["probe"] == "live_market_loop" and fresh["alarm"]["light"] == "GREEN"
    assert SH.api_block()["alarm"]["light"] == "GREEN"
    monkeypatch.setattr(SH, "_utcnow", lambda: observed+timedelta(seconds=1))
    expired = SH.api_block()
    assert expired["alarm"]["light"] == "RED" and expired["generated_utc"] == fresh["generated_utc"]


@pytest.mark.parametrize("verdict,state", [("UNKNOWN", "UNKNOWN"), ("DEAD", "DEAD"),
    ("STALE", "STALE"), ("REFUSED", "REFUSED"), ("ALIVE", "DEGRADED"),
    ("ALIVE", "UNSUPPORTED-MARKER"), ("UNSUPPORTED-MARKER", "UNSUPPORTED-MARKER")])
def test_strict_failed_view_has_no_untrusted_text_or_nested_escape(context, verdict, state):
    marker = "UNSUPPORTED-MARKER"
    original = row(verdict, state, name=marker, probe=marker, detail=marker, proof=marker,
        delta={"nested": marker}, error_type=marker, evidence_mode=marker,
        evidence_utc=marker, valid_until_utc=marker, cadence_s=marker,
        extra={"reason": marker}, alarm={"light": marker, "reason": marker}, progressing=marker)
    before = json.dumps(original, sort_keys=True)
    original_alarm = SH.row_alarm(original, now=context.now)
    safe = SH.public_row(original, now=context.now)
    assert marker not in json.dumps(safe)
    assert safe["name"] == "unidentified_service" and safe["probe"] is None
    assert "error_type" not in safe and "extra" not in safe and "progressing" not in safe
    assert safe["alarm"] == original_alarm
    assert SH.public_row(safe, now=context.now) == safe
    assert SH.row_alarm(safe, now=context.now) == original_alarm
    assert json.dumps(original, sort_keys=True) == before


@pytest.mark.parametrize("probe,verdict,detail", [
    ("bars_panel", "UNKNOWN", "bars panel unreadable (OSError: ARBITRARY-PAYLOAD)"),
    ("llama_server", "DEAD", "owner note exists but health does not answer (OSError: ARBITRARY-PAYLOAD)"),
    ("railway_backend", "DEAD", "GET failed: OSError: ARBITRARY-PAYLOAD"),
    ("fred_macro_inputs", "DEAD", "GET failed: URLError: ARBITRARY-PAYLOAD")])
def test_known_error_lineage_uses_classification_not_format(context, probe, verdict, detail):
    original = row(verdict, name=probe, probe=probe, detail=detail,
                   proof="ARBITRARY-PAYLOAD", delta="ARBITRARY-PAYLOAD")
    safe = SH.public_row(original, now=context.now)
    assert "ARBITRARY-PAYLOAD" not in json.dumps(safe)
    assert safe["name"] == probe and safe["probe"] == probe
    assert safe["alarm"]["light"] == ("AMBER" if verdict == "UNKNOWN" else "RED")


def test_projection_preserves_existing_typed_flags_without_parsing_text(context):
    original = row("STALE", detail="same output for 30 h", same_output=True, progressing=False)
    safe = SH.public_row(original, now=context.now)
    assert safe["same_output"] is True and safe["progressing"] is False
    assert "same output for" not in safe["detail"]
    assert "same_output" not in SH.public_row(row("STALE", detail="same output for 30 h"), now=context.now)


def test_frozen_qualifier_parity_for_light_mode_expiry_and_pause(context, monkeypatch):
    import ast
    import __future__
    from pathlib import Path

    # Portable immutable reference: only the two reviewed function ASTs, never
    # a module import or a machine-specific receipt/history lookup.
    fixture_path = Path(__file__).parent / "fixtures" / "system_health_qualifier_cc3ea807.json"
    fixture_bytes = fixture_path.read_bytes()
    assert hashlib.sha256(fixture_bytes).hexdigest() == "2a8536bbc601203e4695fe032aa6e999fef5d7dbd7982e83fe19f12172d620f6"
    fixture = json.loads(fixture_bytes)
    assert fixture["schema"] == "frozen_alarm_qualifier_functions/1"
    assert fixture["source_origin"] == "reactor-final-repair2-parked/source/backend/services/system_health.py"
    assert fixture["original_source_sha256"] == "cc3ea807b63d75f8f5ccfa82ee49b5d3ca7e2b802c07831167e822df3159d5c6"
    frozen = fixture["functions_source"]
    expected_source_sha = "cd2c1c30978cdd883a61d7c6da47976e2c7f73fed18525d4a2902f912ce81d38"
    assert fixture["functions_sha256"] == expected_source_sha
    assert hashlib.sha256(frozen.encode("utf-8")).hexdigest() == expected_source_sha
    reference_tree = ast.parse(frozen)
    assert len(reference_tree.body) == 2
    assert all(isinstance(node, ast.FunctionDef) for node in reference_tree.body)
    assert [node.name for node in reference_tree.body] == ["public_row", "row_alarm"]
    current_functions = (SH.public_row, SH.row_alarm)
    dependencies = ("re", "math", "datetime", "timedelta", "GRACE", "_bars_limit",
                    "_iso", "_next_session_open", "_ts", "_utcnow", "in_session_hours",
                    "last_closed_session", "sessions_behind")
    namespace = {name: getattr(SH, name) for name in dependencies}
    exec(compile(reference_tree, "frozen_alarm_qualifier_cc3ea807", "exec",
                 flags=__future__.annotations.compiler_flag, dont_inherit=True), namespace)
    assert (SH.public_row, SH.row_alarm) == current_functions
    assert namespace["public_row"] is not SH.public_row
    assert namespace["row_alarm"] is not SH.row_alarm
    old = namespace["row_alarm"]
    values = [row(), row(state="ALIVE_IDLE_EXPECTED"), row("STOPPED_BY_OPERATOR"),
        row("UNKNOWN"), row("DEAD"), row(state="DEGRADED"), row(state="UNSUPPORTED"),
        row(evidence_utc=SH._iso(context.now), cadence_s=60),
        row(evidence_utc=SH._iso(context.now-timedelta(hours=1)), cadence_s=60),
        row(evidence_utc=SH._iso(context.now+timedelta(hours=1)), cadence_s=60)]
    for value in values:
        expected = old(value, now=context.now)
        assert SH.row_alarm(value, now=context.now) == expected
        assert SH.row_alarm(SH.public_row(value, now=context.now), now=context.now) == expected
        if expected["light"] in {"GREEN", "BLUE"}:
            assert SH.public_row(value, now=context.now) == value


def test_projected_unknown_does_not_become_red_from_cleared_proof_or_elapsed_clock(context):
    value = row("UNKNOWN", evidence_utc=SH._iso(context.now), cadence_s=1)
    safe = SH.public_row(value, now=context.now)
    later = context.now+timedelta(hours=1)
    assert SH.row_alarm(value, now=later)["light"] == "AMBER"
    assert SH.row_alarm(safe, now=later)["light"] == "AMBER"
    assert SH.public_row(safe, now=later)["alarm"]["reason"] == "EVIDENCE_UNKNOWN"



def test_failed_deadline_and_mode_are_not_reinferred_from_cleared_fragment(context):
    values = [row("ALIVE", evidence_utc=SH._iso(context.now), cadence_s=60, valid_until_utc="invalid-payload"),
              row("ALIVE", evidence_utc=SH._iso(context.now), cadence_s=60, evidence_mode="invalid-payload")]
    for value in values:
        original_alarm = SH.row_alarm(value, now=context.now)
        safe = SH.public_row(value, now=context.now)
        assert safe["alarm"] == original_alarm
        assert SH.row_alarm(safe, now=context.now) == original_alarm
        assert SH.public_row(safe, now=context.now) == safe


def test_disk_failure_public_line_uses_fixed_message_not_exception_format(context):
    def unavailable(path):raise OSError("ARBITRARY-DISK-PAYLOAD")
    projected = SH.disk_status(optimus_dir=context.optimus_dir, disk_usage=unavailable)
    assert projected["verdict"] == "UNKNOWN" and projected["free_gb"] is None
    assert "ARBITRARY-DISK-PAYLOAD" not in json.dumps(projected)
    assert "service evidence unavailable" in projected["detail"]



def test_view_marker_cannot_downgrade_red_or_authorize_cached_green(context):
    bogus = {"light": "AMBER", "reason": "EVIDENCE_UNKNOWN", "evidence_mode": "STATIC_PROOF", "valid_until_utc": None}
    failed = row("DEAD", public_view=SH.PUBLIC_FAILURE_VIEW, alarm=bogus)
    assert SH.row_alarm(failed, now=context.now)["light"] == "RED"
    assert SH.public_row(failed, now=context.now)["alarm"]["light"] == "RED"
    future = row(evidence_utc=SH._iso(context.now+timedelta(hours=1)), cadence_s=60,
                 public_view=SH.PUBLIC_FAILURE_VIEW, alarm={"light": "GREEN", "reason": "VERIFIED_ALIVE"})
    assert SH.row_alarm(future, now=context.now)["light"] == "AMBER"
    assert SH.public_row(future, now=context.now)["alarm"]["light"] == "AMBER"


@pytest.mark.parametrize("verdict", ["ALIVE", "STOPPED_BY_OPERATOR"])
def test_contradictory_error_flag_cannot_certify_positive_or_pause(context, verdict):
    value = row(verdict, error_type="ARBITRARY-CLASS-PAYLOAD")
    safe = SH.public_row(value, now=context.now)
    assert safe["alarm"]["light"] == "AMBER"
    assert "ARBITRARY-CLASS-PAYLOAD" not in json.dumps(safe)
    assert "error_type" not in safe



@pytest.mark.parametrize('substance,idle,expected_same',[('unchanged fixture',None,True),
    ('changed fixture',None,None),(None,None,None),('unchanged fixture','no work expected',None)])
def test_actual_task_judge_probe_public_and_api_preserve_typed_stall_lineage(context,monkeypatch,substance,idle,expected_same):
    name='AegisDailyPass';context.repo=context.optimus_dir
    context.prev_state={'progress':{name:{'hash':hashlib.sha256(b'unchanged fixture').hexdigest()[:16],
        'first_seen_utc':SH._iso(context.now-timedelta(days=4)),'n_same':10}}}
    # Deliberately stall-looking prose in all cases: prose is not the flag source.
    spec=TR.TaskSpec(lambda ctx,task:TR.Reading(stamp=ctx.now-timedelta(minutes=1),status='OK',
        substance=substance,proof='synthetic receipt',detail='same output for ages',idle_reason=idle),'synthetic.json')
    task={'Scheduled Task State':'Enabled','Last Run Time':'-'}
    monkeypatch.setattr(TR,'TASK_RECEIPT',{name:spec})
    monkeypatch.setattr(SH,'_schtasks',lambda ctx:{name:task})
    judged=TR.judge(context,name,task,spec)
    context.new_state={}  # p_scheduled_tasks performs its own real judge call
    produced=SH.p_scheduled_tasks(context)[name]
    assert produced.same_output is expected_same
    assert produced.progressing is (False if expected_same else None)
    if expected_same:assert judged.extra['same_hash_probes']>=2 and judged.state=='STALE'
    else:assert 'same_hash_probes' not in judged.extra
    probe=next(p for p in SH.PROBES if p.name=='task')
    raw=SH._row(probe,'task:'+name,produced);before=json.loads(json.dumps(raw))
    safe=SH.public_row(raw,now=context.now)
    assert raw==before
    if expected_same:
        assert safe['same_output'] is True and safe['progressing'] is False
        assert safe['proof']=='' and safe['alarm']['light']=='RED'
    else:assert safe.get('same_output') is None
    monkeypatch.setattr(SH,'run',lambda **kw:{'generated_utc':SH._iso(context.now),'counts':{produced.verdict:1},
        'state_counts':{produced.state:1},'exit_code':SH.exit_code([safe]),'rows':[safe]})
    monkeypatch.setattr(SH,'make_ctx',lambda **kw:context);monkeypatch.setattr(SH,'_utcnow',lambda:context.now)
    SH._API_CACHE.clear();api=SH.api_block(ttl_s=0)
    assert api['rows'][0]['same_output'] is expected_same
    assert api['rows'][0]['progressing'] is (False if expected_same else None)
    if expected_same:assert api['rows'][0]['alarm']['light']=='RED'
    elif idle:assert api['rows'][0]['alarm']['light']=='GREEN'
