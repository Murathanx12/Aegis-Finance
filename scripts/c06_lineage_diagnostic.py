"""Read-only C06 diagnostic. A saved subject path is never native lineage proof."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

LIMIT_BYTES = 8 * 1024 * 1024


def _pairs(items: list) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("NONFINITE_JSON")
    return number


def _constant(value: str) -> None:
    raise ValueError("NONFINITE_JSON")


def _clock(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("INVALID_OR_UNZONED_CLOCK")
    return stamp


def probe(raw: bytes, *, expected_sha256: str, as_of: str,
          source: str, decision: str) -> dict:
    """Inspect exact saved bytes only; never open paths embedded in the view.

    This fallback cannot qualify a native producer contract. Even an explicit
    edge is an unqualified saved assertion, not an end-to-end PASS.
    """
    digest = hashlib.sha256(raw).hexdigest()
    result = {"schema": "c06_lineage_diagnostic/1", "status": "REFUSED",
              "lineage_proven": False, "paths": [], "view_sha256": digest,
              "requested_as_of": as_of, "source": source, "decision": decision,
              "source_refs": [], "mode": "SAVED_VIEW_DIAGNOSTIC_ONLY"}

    def refuse(reason: str) -> dict:
        return {**result, "reason": reason}

    if len(raw) > LIMIT_BYTES:
        return refuse("VIEW_SIZE_LIMIT")
    if digest != expected_sha256:
        return refuse("SAVED_VIEW_HASH_MISMATCH")
    try:
        view = json.loads(raw, object_pairs_hook=_pairs, parse_float=_float,
                          parse_constant=_constant)
        if view["schema"] != "beta_v2_atlas_view/1":
            return refuse("UNSUPPORTED_VIEW_SCHEMA")
        # Bound output nesting too: pretty-printing has a lower recursion budget
        # than decoding. Check before retaining any untrusted nested payload.
        pending = [(view, 0)]
        while pending:
            value, depth = pending.pop()
            if depth > 32:
                return refuse("VIEW_NESTING_LIMIT")
            if isinstance(value, dict):
                pending.extend((child, depth + 1) for child in value.values())
            elif isinstance(value, list):
                pending.extend((child, depth + 1) for child in value)
        result["source_refs"] = view["source_refs"]
        result["saved_as_of"] = view["as_of"]
        cutoff = _clock(as_of)
        if as_of != view["as_of"]:
            return refuse("EXACT_SAVED_ASOF_REQUIRED")
        nodes = view["nodes"]
        edges = view["edges"]
        if len(nodes) > 2500 or len(edges) > 5000:
            return refuse("BOUNDED_VIEW_LIMIT")
        ids = [node["id"] for node in nodes]
        if len(set(ids)) != len(ids):
            return refuse("AMBIGUOUS_NATIVE_IDENTITY")
        index = {node["id"]: node for node in nodes}
        if not source.startswith("economic:source:") or not decision.startswith("economic:decision:"):
            return refuse("TYPED_SOURCE_AND_DECISION_REQUIRED")
        if source not in index or decision not in index:
            return refuse("NATIVE_ENDPOINT_NOT_AVAILABLE")
        result["endpoint_facts"] = {source: index[source]["facts"],
                                    decision: index[decision]["facts"]}
        for node in nodes:
            if node["kind"] in {"thesis", "decision"} and len(node["facts"]) != 1:
                return refuse("AMBIGUOUS_NATIVE_IDENTITY")
        # Fail closed on conflicting saved identity facts or any ineligible fact.
        # Conservative whole-view check: this is a diagnostic, not graph traversal.
        for item in [*nodes, *edges]:
            facts = item["facts"]
            if not facts:
                return refuse("MISSING_NATIVE_FACT")
            for fact in facts:
                times = fact["clocks"]
                if not times.get("available_at"):
                    return refuse("UNKNOWN_AVAILABILITY")
                if _clock(times["available_at"]) > cutoff:
                    return refuse("FUTURE_AVAILABILITY")
                if times.get("effective_at") and _clock(times["effective_at"]) > cutoff:
                    return refuse("NOT_YET_EFFECTIVE")
                if times.get("expires_at") and _clock(times["expires_at"]) <= cutoff:
                    return refuse("EXPIRED")
        incoming = [e for e in edges if e["to"] == decision
                    and e["relation"] == "explicit_thesis_ref"]
        if not incoming:
            missing = any(g["owner"] == decision and
                          g["reason"] == "MISSING_THESIS_ID_NO_LINEAGE_INFERRED"
                          for g in view["unresolved"])
            return refuse("MISSING_NATIVE_THESIS_ID" if missing else
                          "NATIVE_THESIS_DECISION_LINK_NOT_AVAILABLE")
        if len(incoming) != 1 or incoming[0]["from"] not in index:
            return refuse("AMBIGUOUS_OR_MISSING_NATIVE_THESIS")
        return refuse("NATIVE_PRODUCER_CONTRACT_NOT_QUALIFIED")
    except (KeyError, TypeError, AttributeError, ValueError, RecursionError) as exc:
        reason = str(exc) if str(exc) in {"DUPLICATE_JSON_KEY", "NONFINITE_JSON",
                                        "INVALID_OR_UNZONED_CLOCK"} else "MALFORMED_SAVED_VIEW"
        return refuse(reason)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--decision", required=True)
    args = parser.parse_args()
    with args.view.open("rb") as handle:
        raw = handle.read(LIMIT_BYTES + 1)
    result = probe(raw, expected_sha256=args.expected_sha256, as_of=args.as_of,
                   source=args.source, decision=args.decision)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 2  # A diagnostic refusal is never a successful lineage check.


if __name__ == "__main__":
    raise SystemExit(main())
