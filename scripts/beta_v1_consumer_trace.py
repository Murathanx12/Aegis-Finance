"""Pinned reviewed artifact consumers only; never discovers runtime inputs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services import beta_v1_consumers as consumer
from backend.services import beta_v1_policy as policy
from backend.services import beta_v1_replay as replay


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path, expected):
    path = Path(path)
    if path.stat().st_size > 16*1024*1024 or _hash(path) != expected:
        raise ValueError("input size/hash qualification mismatch")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run(args):
    budget = replay.RunBudget()
    output = Path(args.output).resolve()
    if output.name != "beta_v1_consumer_trace.json" or output.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError("explicit private beta_v1_consumer_trace.json required outside checkout")
    paths = {name: getattr(args, name) for name in ("replay", "current", "protocol", "rf_coverage")}
    expected = {name: getattr(args, name+"_sha256") for name in paths}
    source_paths = (__file__, consumer.__file__, replay.__file__, policy.__file__,
                    policy.kernels.__file__, replay.er.__file__, replay.er.fr.__file__)
    source_pins = {str(p): _hash(p) for p in source_paths}
    budget.check("before consumer input read")
    inputs = {name: _read(path, expected[name]) for name, path in paths.items()}
    budget.check("consumer inputs loaded")
    historical = inputs["replay"]
    payload = {k: v for k, v in historical.items() if k != "artifact_hash"}
    if policy.digest(payload) != historical["artifact_hash"]:
        raise ValueError("reviewed replay logical artifact hash mismatch")
    probability = consumer.separated_probability_metrics(historical)
    def sink(vintage):
        return str(policy.save(vintage, output.parent/"derived_h5_weight_vintages"))
    derived = consumer.derived_h5_return_trace(historical, inputs["protocol"], budget=budget, artifact_sink=sink)
    # Current descriptive inputs are run through the actual isolated policy,
    # Missing return inputs remain unavailable, distinct from a cash decision.
    primary = consumer.current_draft(inputs["current"], inputs["protocol"], source_hash=expected["current"], horizon=21)
    secondary = consumer.current_draft(inputs["current"], inputs["protocol"], source_hash=expected["current"], horizon=5)
    primary_repeat = consumer.current_draft(json.loads(json.dumps(inputs["current"])), inputs["protocol"],
                                            source_hash=expected["current"], horizon=21)
    if primary_repeat != primary:
        raise ValueError("no-new-outcomes/current JSON reload not idempotent")
    del primary_repeat
    result = {"schema": consumer.VERSION, "probability": probability, "derived_h5": derived,
        "primary_h21": primary, "secondary_h5": secondary, "input_hashes": expected,
        "no_new_outcomes_current_reload": {"identical": True, "primary_artifact_hash": primary["artifact_hash"]},
        "source_pins": source_pins, "rf_formation_context_hash": policy.digest(inputs["rf_coverage"]),
        "context_manifest": {"source_artifacts": paths, "numeric_panels_to_llm": False,
            "return_basis": "PRICE_RETURN_NOT_TOTAL_RETURN; adjustment UNKNOWN",
            "qualified_current_return_status": inputs["current"].get("return_estimation_status"),
            "rf_scores": "descriptive features; not automatically calibrated return or historical paired control",
            "claims": "retrospective derivation + inactive draft; no fills, activation, six-month PIT or alpha claim"}}
    if source_pins != {str(p): _hash(p) for p in source_paths} or expected != {name: _hash(path) for name, path in paths.items()}:
        raise ValueError("input/execution dependency changed during consumer run")
    result["artifact_hash"] = policy.digest(result)
    budget.check("consumer output", output_bytes=replay.json_bytes(result))
    output.parent.mkdir(parents=True, exist_ok=True)
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
    if output.exists():
        raise ValueError("immutable consumer output already exists; select a new private vintage")
    temporary = output.with_suffix(".incomplete")
    try:
        with temporary.open("x", encoding="utf-8", newline="") as handle:
            for chunk in encoder.iterencode(result):
                handle.write(chunk)
        budget.check("consumer serialized output", output_bytes=temporary.stat().st_size)
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"artifact_hash": result["artifact_hash"], "output": str(output),
        "probability_contracts": len(probability["contracts"]), "derived_h5_rows": derived["derived_rows"],
        "derived_h5_decisions": len(derived["traces"]), **current_status_summary(primary), "secondary_horizon": secondary["horizon"]}




def current_status_summary(primary):
    """Keep residual plan arithmetic distinct from unavailable input evidence."""
    available = primary["decision"] in ("CASH_100_PERCENT", "INACTIVE_PROPOSED_ONLY")
    return {"primary_h21_decision": primary["decision"],
        "primary_cash": primary["plan"]["cash_weight"] if available else None,
        "primary_cash_weight_preview": primary["plan"]["cash_weight"],
        "primary_investment_cash_decision": primary["investment_cash_decision"],
        "primary_decision_reason": primary["decision_reason"], "primary_decision_counts": primary["decision_counts"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("replay", "current", "protocol", "rf-coverage"):
        parser.add_argument("--"+name, required=True)
        parser.add_argument("--"+name+"-sha256", required=True)
    parser.add_argument("--output", required=True)
    print(json.dumps(run(parser.parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
