"""Explicit-pin protected-first original decision projection, private output."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services import beta_v1_decision_projection as projection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.name != "beta_v1_original_decision_projection.json" or output.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError("private explicitly named output outside checkout required")
    services = Path(projection.__file__).parent
    dependencies = (__file__, projection.__file__, services/"decision_ledger.py", services/"beta_v1_replay.py")
    pins = {str(p): projection._hash(p) for p in dependencies}
    result = projection.project_file(args.source, expected_sha256=args.source_sha256, cutoff=args.cutoff)
    if pins != {str(p): projection._hash(p) for p in dependencies}:
        raise ValueError("projection execution source changed")
    payload = {"projection": result, "source_pins_before_after": pins, "activation": False}
    encoded = projection.canonical_bytes(payload)
    if len(encoded) > 4*1024*1024:
        raise projection.ProjectionRefusal("complete private serialized envelope exceeds 4MiB output cap")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(encoded)
    print(json.dumps({"artifact_hash": result["artifact_hash"], "counts": result["counts"],
        "eligible_h21_training_rows": result["eligible_h21_training_rows"], "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
