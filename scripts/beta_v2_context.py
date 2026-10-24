"""Read-only, stdlib context binding for explicit worker packets; stdout only.

No retrieval, discovery, subprocess, startup hook, dispatch or activation. A
bound receipt establishes byte/anchor agreement, never runtime freshness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "aegis-beta-v2-worker-context/1"
PACKET_SCHEMA = "aegis-beta-v2-task-packet/1"
DENIED_PARTS = {".git", ".ssh", ".aws", ".azure", ".gnupg", ".kube", ".codex",
                "secrets", "secret", "credentials", "credential", "tokens", "token"}
MAX_BYTES = 16 * 1024 * 1024


def strict_json(raw: bytes | str) -> object:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("nonfinite JSON number")
        return parsed

    return json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=number)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in {
        "unknown", "todo", "tbd", "unspecified", "n/a"}


def safe_path(value: str, root: Path, allowed_roots: list[Path]) -> Path:
    """Resolve only explicit local files within caller-selected roots, deny secrets."""
    if not _text(value) or any(c in value for c in "*?[]\x00") or value.startswith(("\\\\", "//")) or "://" in value:
        raise ValueError("explicit local path required; wildcards/URLs/UNC denied")
    if ":" in value[2:]:
        raise ValueError("alternate streams denied")
    raw = Path(value)
    path = (root / raw).resolve()
    for candidate in (raw, path):
        for part in candidate.parts:
            lower = part.lower()
            if (lower in DENIED_PARTS or lower.startswith(".env") or
                lower in {"id_rsa", "id_ed25519", "credentials.json", "credentials.jsonl", "users.json"} or
                lower.endswith((".pem", ".key", ".pfx", ".p12"))):
                raise ValueError("secret/configuration path denied")
    if not any(path.is_relative_to(r.resolve()) for r in allowed_roots):
        raise ValueError("path outside caller-selected source roots")
    return path


def _read(path: Path) -> bytes:
    with path.open("rb") as handle:
        value = handle.read(MAX_BYTES + 1)
    if len(value) > MAX_BYTES:
        raise ValueError("source exceeds 16 MiB bound; supply an explicit compact source")
    return value


def source_fingerprint(sources: list[dict]) -> str:
    return digest(sorted(({k: s.get(k) for k in ("id", "path", "observed_sha256", "status")}
                          for s in sources), key=lambda s: str(s["id"])))


def bind(packet: object, *, root: Path = ROOT, source_roots: list[Path] | None = None,
         prior: object = None) -> dict:
    """Re-read all declared sources on every call; prior receipts are comparison only."""
    receipt = {"schema": SCHEMA, "observed_at": datetime.now(timezone.utc).isoformat(),
               "context_status": "unknown", "runtime_status": "unknown",
               "activation_authorized": False, "errors": [], "sources": [], "prior_findings": [],
               "note": "Source agreement only. Unchanged bytes do not establish current runtime, owner authority or task completion."}
    errors = receipt["errors"]
    if not isinstance(packet, dict):
        errors.append("packet must be an object")
        return receipt
    receipt.update(task_id=packet.get("task_id"), objective=packet.get("objective"),
                   packet_fingerprint=digest(packet))
    if packet.get("schema") != PACKET_SCHEMA:
        errors.append("unknown packet schema")
    if packet.get("task_id") not in [f"C{i:02}" for i in range(16)] + ["B01"]:
        errors.append("unknown task_id")
    if not _text(packet.get("objective")):
        errors.append("objective required")
    authority = packet.get("authority_boundaries")
    if (not isinstance(authority, dict) or authority.get("activation_authorized") is not False or
        any(not isinstance(authority.get(k), list) or not authority[k] or
            any(not _text(x) for x in authority[k]) for k in ("permitted_actions", "forbidden_actions"))):
        errors.append("explicit authority boundaries required; activation_authorized must be false")
    else:
        receipt["authority_boundaries"] = authority
    requirements = packet.get("evidence_requirements")
    if not isinstance(requirements, list) or not requirements or any(not _text(x) for x in requirements):
        errors.append("explicit evidence_requirements required")
    else:
        receipt["evidence_requirements"] = requirements
    specifications = packet.get("sources")
    if not isinstance(specifications, list) or not specifications:
        errors.append("nonempty explicit sources required")
        specifications = []
    continuation = packet.get("continuation")
    if not isinstance(continuation, dict):
        errors.append("continuation path and expected_sha256 required")
        continuation = {}
    specifications = list(specifications) + [{**continuation, "id": "continuation"}]
    roots = [root.resolve()] + list(source_roots or [])
    seen, paths, contents = set(), set(), {}
    for spec in specifications:
        if not isinstance(spec, dict):
            errors.append("source specification must be an object")
            continue
        identifier = spec.get("id")
        result = {"id": identifier, "path": spec.get("path"),
                  "expected_sha256": spec.get("expected_sha256"), "observed_sha256": None, "status": "unknown"}
        receipt["sources"].append(result)
        try:
            if not _text(identifier) or identifier in seen:
                raise ValueError("unique nonblank source id required (continuation is reserved)")
            seen.add(identifier)
            expected = spec.get("expected_sha256")
            if not isinstance(expected, str) or not re.fullmatch("[0-9a-f]{64}", expected):
                raise ValueError("known lowercase expected_sha256 required")
            path = safe_path(spec.get("path"), root, roots)
            result["path"] = path.as_posix()
            if path in paths:
                raise ValueError("duplicate source path; reference its existing source id")
            paths.add(path)
            try:
                content = _read(path)
            except FileNotFoundError:
                result["status"] = "missing"
                raise ValueError("source missing") from None
            observed = hashlib.sha256(content).hexdigest()
            result.update(observed_sha256=observed, bytes=len(content),
                          status="matched" if observed == expected else "changed")
            if observed != expected:
                raise ValueError("source hash changed or expected hash wrong")
            contents[identifier] = content
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"source {identifier}: {exc}")
    findings = packet.get("prior_findings")
    if not isinstance(findings, list) or not findings:
        errors.append("explicit relevant prior_findings with expected anchors required")
        findings = []
    finding_ids = set()
    for finding in findings:
        result = {"status": "unknown"}
        receipt["prior_findings"].append(result)
        if not isinstance(finding, dict):
            errors.append("prior finding must be an object")
            continue
        identifier, source_id, anchor = (finding.get(k) for k in ("id", "source_id", "expected_anchor"))
        result.update(id=identifier, source_id=source_id)
        if not _text(identifier) or identifier in finding_ids or not _text(source_id) or not _text(anchor):
            errors.append("prior finding requires unique id, source_id and known expected_anchor")
            continue
        finding_ids.add(identifier)
        result["anchor_sha256"] = hashlib.sha256(anchor.encode("utf-8")).hexdigest()
        # Never emit the raw text: packets and receipts can stay in private evidence.
        if source_id not in contents:
            errors.append(f"prior finding {identifier}: source not bound")
        elif anchor.encode("utf-8") not in contents[source_id]:
            result["status"] = "missing_anchor"
            errors.append(f"prior finding {identifier}: expected anchor missing")
        else:
            result["status"] = "matched"
    receipt["source_fingerprint"] = source_fingerprint(receipt["sources"])
    if prior is not None:
        if (not isinstance(prior, dict) or prior.get("schema") != SCHEMA or
            prior.get("task_id") != packet.get("task_id") or
            not isinstance(prior.get("sources"), list) or
            any(not isinstance(s, dict) or not _text(s.get("id")) for s in prior.get("sources", [])) or
            prior.get("source_fingerprint") != source_fingerprint(prior.get("sources", []))):
            errors.append("invalid prior receipt/schema/task/source fingerprint")
        else:
            before = {s["id"]: s for s in prior["sources"]}
            after = {s["id"]: s for s in receipt["sources"]}
            delta = []
            for identifier in sorted(set(before) | set(after)):
                old, new = before.get(identifier), after.get(identifier)
                if old is None:
                    state = "added"
                elif new is None:
                    state = "removed"
                elif new["status"] != "matched":
                    state = "unbound_now"
                elif (old.get("path"), old.get("observed_sha256")) == (new["path"], new["observed_sha256"]):
                    state = "unchanged_bytes_reobserved"
                else:
                    state = "changed"
                delta.append({"id": identifier, "state": state,
                              "previous_sha256": old.get("observed_sha256") if old else None,
                              "observed_sha256": new["observed_sha256"] if new else None})
            receipt["delta"] = {"previous_source_fingerprint": prior["source_fingerprint"],
                                "packet_changed": prior.get("packet_fingerprint") != receipt["packet_fingerprint"],
                                "sources": delta}
    if not errors:
        receipt["context_status"] = "bound"
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True)
    parser.add_argument("--prior-receipt")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source-root", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    roots = [args.root] + args.source_root
    try:
        packet = strict_json(_read(safe_path(args.packet, args.root, roots)))
        prior = strict_json(_read(safe_path(args.prior_receipt, args.root, roots))) if args.prior_receipt else None
        if args.prior_receipt and not isinstance(prior, dict):
            raise ValueError("prior receipt must be an object")
        receipt = bind(packet, root=args.root, source_roots=args.source_root, prior=prior)
    except (OSError, ValueError, TypeError) as exc:
        receipt = {"schema": SCHEMA, "context_status": "unknown", "runtime_status": "unknown",
                   "activation_authorized": False, "errors": [f"input unavailable/invalid: {exc}"]}
    print(json.dumps(receipt, indent=2, ensure_ascii=True))
    return 0 if receipt["context_status"] == "bound" else 1


if __name__ == "__main__":
    raise SystemExit(main())
