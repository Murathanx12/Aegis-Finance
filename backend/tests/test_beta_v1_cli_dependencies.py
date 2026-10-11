"""Dependency-drift sentinels using tiny injected records, never native data."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.services import beta_v1_policy as policy
from backend.services import beta_v1_replay as replay


@pytest.mark.parametrize("kind", ["consumer", "replay"])
@pytest.mark.parametrize("drift", [False, True])
def test_cli_binds_kernel_before_and_after_execution(tmp_path, monkeypatch, kind, drift):
    monkeypatch.setattr(replay, "_rss_bytes", lambda: 32*1024*1024)
    helper = Path(policy.kernels.__file__).resolve()
    reads = []
    if kind == "consumer":
        from scripts import beta_v1_consumer_trace as cli
        documents = {"replay": {"artifact_hash": policy.digest({})}, "current": {},
                     "protocol": {}, "rf_coverage": {}}
        values = {}
        for name, payload in documents.items():
            path = tmp_path/(name+".json")
            path.write_text(json.dumps(payload), encoding="utf-8")
            values[name] = str(path)
            values[name+"_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        values["output"] = str(tmp_path/"beta_v1_consumer_trace.json")
        monkeypatch.setattr(cli.consumer, "separated_probability_metrics", lambda value: {"contracts": []})
        monkeypatch.setattr(cli.consumer, "derived_h5_return_trace", lambda *a, **k: {"derived_rows": 0, "traces": []})
        monkeypatch.setattr(cli.consumer, "current_draft", lambda *a, **k: {
            "artifact_hash": "fixture", "horizon": k["horizon"], "decision": "RETURN_INPUTS_UNAVAILABLE",
            "decision_reason": "synthetic missing returns", "decision_counts": {},
            "investment_cash_decision": False, "plan": {"cash_weight": 1}})
        hash_name = "_hash"
    else:
        from scripts import beta_v1_sprint_replay as cli
        manifest = tmp_path/"manifest.json"
        manifest.write_text(json.dumps({"files": [], "price_basis": "FIXTURE"}), encoding="utf-8")
        values = {"projection": str(tmp_path/"injected-not-read.json"), "projection_sha256": "a"*64,
            "price_manifest": str(manifest), "output": str(tmp_path/"beta_v1_sprint_replay.json"),
            "allow_unknown_prior": True}
        monkeypatch.setattr(replay, "load_projection", lambda *a, **k: {
            "graded_projection_private": [], "forecast_aggregate": {},
            "analyst_revision_projection_private": {}})
        monkeypatch.setattr(cli, "_prices", lambda *a: None)
        monkeypatch.setattr(replay, "reconstruct", lambda *a, **k: {"verification_counts": {}, "records": []})
        monkeypatch.setattr(replay, "original_forward", lambda *a: {
            "graded_rows_in_projection": 0, "unresolved_rows_in_projection": 0,
            "original_projection_gate_counts": {}, "cells": []})
        monkeypatch.setattr(replay, "chronological_replay", lambda *a, **k: {"artifact_hash": "fixture", "decisions": []})
        hash_name = "_file_hash"
    original_hash = getattr(cli, hash_name)

    def observed_hash(path):
        value = original_hash(path)
        if Path(path).resolve() == helper:
            reads.append(value)
            if drift and len(reads) > 1:
                return "0"*64
        return value

    monkeypatch.setattr(cli, hash_name, observed_hash)
    if drift:
        with pytest.raises(ValueError, match="dependenc.*changed"):
            cli.run(SimpleNamespace(**values))
        assert not Path(values["output"]).exists()
    else:
        cli.run(SimpleNamespace(**values))
        result = json.loads(Path(values["output"]).read_text(encoding="utf-8"))
        pins = result["source_pins"] if kind == "consumer" else result["source_pins_before_after"]
        assert pins[str(policy.kernels.__file__)] == hashlib.sha256(helper.read_bytes()).hexdigest()
    assert len(reads) == 2


def test_numerical_manifest_binds_actual_policy_math(monkeypatch):
    from backend.services import beta_v1_numerical as numerical
    paths = []
    def fingerprint(path):
        paths.append(Path(path).resolve())
        return "a"*64
    monkeypatch.setattr(numerical, "sha256", fingerprint)
    pins = numerical.code_pins()
    for module in (policy.kernels, policy.er, policy.fr):
        assert Path(module.__file__).resolve() in paths
        assert Path(module.__file__).name in pins
