"""Bounded read-only projection of explicitly supplied existing receipts.

Stdlib only: no world_state/decision/registry producer imports or DB access.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

KINDS = {"beliefs", "scenarios", "event", "thesis", "decisions", "registry", "receipt"}
LIMIT_BYTES = 2 * 1024**2
LIMIT_ROWS = 500


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def clock(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("AWARE_TIMESTAMP_REQUIRED")
    return stamp.astimezone(timezone.utc)


def strict_json(raw: bytes | str) -> object:
    def reject(value: str) -> None:
        raise ValueError("NONFINITE_JSON: " + value)

    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY: " + key)
            result[key] = value
        return result
    return json.loads(raw, parse_constant=reject, object_pairs_hook=pairs)


def read_inputs(receipts: list[str]) -> list[dict]:
    if not receipts or len(receipts) > 16:
        raise ValueError("SUPPLY_1_TO_16_EXPLICIT_RECEIPTS")
    documents = []
    for spec in receipts:
        kind, path = spec.split("=", 1)
        if kind not in KINDS:
            raise ValueError("UNSUPPORTED_RECEIPT_KIND")
        path = Path(path).resolve(strict=True)
        if path.stat().st_size > LIMIT_BYTES:
            raise ValueError("RECEIPT_TOO_LARGE_SELECT_A_BOUNDED_EXPORT")
        raw = path.read_bytes()
        value = (None if kind == "receipt" else
                 [strict_json(line) for line in raw.splitlines()] if path.suffix == ".jsonl" else strict_json(raw))
        if isinstance(value, list) and len(value) > LIMIT_ROWS:
            raise ValueError("RECEIPT_ROW_LIMIT")
        if sha(path.read_bytes()) != sha(raw):
            raise ValueError("SOURCE_CHANGED_DURING_READ")
        documents.append({"kind": kind, "value": value, "ref": {
            "path": str(path), "sha256": sha(raw), "bytes": len(raw),
            "read_at": datetime.now(timezone.utc).isoformat()}})
    return documents


def node_id(namespace: str, kind: str, native_id: str) -> str:
    if namespace not in {"economic", "operational"} or not isinstance(native_id, str) or not native_id:
        raise ValueError("TYPED_NATIVE_ID_REQUIRED")
    return f"{namespace}:{kind}:{native_id}"


def clocks(row: dict, availability: str | None) -> dict:
    return {"available_at": availability,
            "source_at": row.get("source_at", row.get("source_timestamp", row.get("published_utc"))),
            "effective_at": row.get("effective_at"),
            "expires_at": row.get("expires_at", row.get("expiry_utc"))}


class Projection:
    def __init__(self, documents: list[dict], as_of: str, registry_root: Path) -> None:
        self.as_of, self.cutoff = as_of, clock(as_of)
        self.documents, self.registry_root = documents, registry_root.resolve()
        self.nodes, self.edges = {}, {}
        self.unresolved, self.excluded = [], []
        self.by_path = {str(Path(d["ref"]["path"]).resolve()): d for d in documents}

    def gap(self, owner: str, reference: object, reason: str, ref: dict) -> None:
        self.unresolved.append({"owner": owner, "reference": reference, "reason": reason, "ref": ref})

    def eligible(self, owner: str, times: dict, ref: dict) -> bool:
        reason = None
        try:
            if not times["available_at"]:
                reason = "UNKNOWN_AVAILABILITY"
            elif clock(times["available_at"]) > self.cutoff:
                reason = "FUTURE_AVAILABILITY"
            elif times["effective_at"] and clock(times["effective_at"]) > self.cutoff:
                reason = "NOT_YET_EFFECTIVE"
            elif times["expires_at"] and clock(times["expires_at"]) <= self.cutoff:
                reason = "EXPIRED"
        except (ValueError, TypeError, AttributeError):
            reason = "INVALID_OR_UNZONED_CLOCK"
        if reason:
            self.excluded.append({"owner": owner, "reason": reason, "clocks": times, "ref": ref})
        return reason is None

    def node(self, namespace: str, kind: str, ident: str, data: dict, times: dict, ref: dict) -> str:
        key = node_id(namespace, kind, ident)
        item = self.nodes.setdefault(key, {"id": key, "namespace": namespace, "kind": kind,
                                           "native_id": ident, "facts": []})
        fact = {"data": data, "clocks": times, "ref": ref}
        if fact not in item["facts"]:
            item["facts"].append(fact)
        return key

    def edge(self, src: str, dst: str, relation: str, times: dict, ref: dict,
             *, polarity: str | None = None, data: dict | None = None) -> None:
        if polarity not in {None, "supportive", "contrary", "unclassified"}:
            raise ValueError("EXPLICIT_POLARITY_REQUIRED")
        key = (src, dst, relation, polarity)
        item = self.edges.setdefault(key, {"from": src, "to": dst, "relation": relation,
                                           "polarity": polarity, "facts": []})
        fact = {"data": data or {}, "clocks": times, "ref": ref}
        if fact not in item["facts"]:
            item["facts"].append(fact)

    def company(self, ticker: str, times: dict, ref: dict) -> str:
        return self.node("economic", "company", ticker, {"ticker": ticker}, times, ref)

    def beliefs(self, value: dict, ref: dict) -> None:
        if value.get("schema") != "world_state/v2":
            raise ValueError("EXPECTED_WORLD_STATE_V2")
        times = clocks(value, value.get("as_of"))
        if not self.eligible("belief_snapshot", times, ref):
            return
        for topic, b in value["beliefs"].items():
            loc = {**ref, "locator": "/beliefs/" + topic}
            bt = clocks(b, b.get("last_updated", times["available_at"]))
            if not self.eligible(topic, bt, loc):
                continue
            key = self.node("economic", "belief", topic, {k: b.get(k) for k in (
                "direction", "confidence", "provenance", "provenance_basis", "half_life_days")}, bt, loc)
            for ticker in b.get("affected_entities", {}).get("tickers", []):
                self.edge(key, self.company(ticker, bt, loc), "names_affected_entity", bt, loc,
                          data={"economic_exposure": None, "portfolio_weight": None})
            for eid in dict.fromkeys(b.get("evidence_ids", [])):
                root = self.node("economic", "evidence_ref", eid, {"resolution": "REFERENCE_ONLY"}, bt, loc)
                self.edge(root, key, "cited_evidence", bt, loc, polarity="unclassified")
                self.gap(root, eid, "UNDERLYING_SOURCE_RECORD_NOT_SUPPLIED", loc)
            for contradiction in b.get("contradictions", []):
                ct = clocks(contradiction, contradiction.get("at"))
                if self.eligible(key, ct, loc):
                    for eid in dict.fromkeys(contradiction.get("evidence_ids", [])):
                        root = self.node("economic", "evidence_ref", eid, {"resolution": "REFERENCE_ONLY"}, ct, loc)
                        self.edge(root, key, "contradicts_prior_belief", ct, loc, polarity="contrary",
                                  data={"at": contradiction.get("at"), "prior_direction": contradiction.get("prior_direction")})
                        self.gap(root, eid, "UNDERLYING_SOURCE_RECORD_NOT_SUPPLIED", loc)
            for e in b.get("co_mention_edges", []):
                target = node_id("economic", "belief", e["to"])
                # No causal promotion and no conversion of support counts to reliability.
                self.edge(key, target, "co_mention", bt, loc, data=e)

    def scenarios(self, value: dict, ref: dict) -> None:
        if value.get("schema") != "macro_scenarios/v2":
            raise ValueError("EXPECTED_MACRO_SCENARIOS_V2")
        times = clocks(value, value.get("as_of"))
        if not self.eligible("scenario_snapshot", times, ref):
            return
        for s in value["scenarios"]:
            loc = {**ref, "locator": "/scenarios/" + s["scenario_id"]}
            # Absent row availability inherits the producer snapshot; an explicit
            # invalid/future row update must never fall back to older evidence.
            row_times = clocks(s, s.get("last_updated", times["available_at"]))
            if not self.eligible(s["scenario_id"], row_times, loc):
                continue
            key = self.node("economic", "scenario", s["scenario_id"], {k: s.get(k) for k in (
                "name", "causal_chain", "assumptions", "falsifiers", "use")} |
                {"causal_chain_type": "DECLARED_HYPOTHESIS_LABEL_ONLY"}, row_times, loc)
            # A declared prose chain stays a hypothesis; it is not parsed into causal facts.
            for indicator in s.get("leading_indicators", []):
                self.edge(node_id("economic", "belief", indicator["topic"]), key,
                          "scenario_indicator_hypothesis", row_times, loc,
                          data={"indicator_weight": indicator.get("weight"), "direction": indicator.get("direction"),
                                "economic_exposure": None, "portfolio_weight": None})

    def economic_record(self, kind: str, row: dict, ref: dict, parent: dict) -> None:
        if kind == "event":
            ident = row.get("observation_hash")
            available = row.get("ingested_at", row.get("accepted_at"))
            nk = "observation"
        elif kind == "thesis":
            ident, available, nk = row.get("thesis_id", row.get("card_hash")), row.get("run_utc"), "thesis"
        else:
            ident, nk = row.get("decision_id"), "decision"
            available = row.get("built_utc", parent.get("written_utc"))
        if not ident:
            self.gap(kind, None, "MISSING_NATIVE_ID", ref)
            return
        times = clocks(row, available)
        if not self.eligible(ident, times, ref):
            return
        data = {k: row.get(k) for k in ("verdict", "direction", "source_at", "asof", "ingest_clock",
                                      "information_cutoff_utc", "evidence_grade")}
        data.update(evidence_reliability=row.get("evidence_reliability"),
                    economic_exposure=row.get("economic_exposure"),
                    portfolio_weight={k: row[k] for k in ("weight", "target_weight") if k in row} or None,
                    position_budget=row.get("position_budget"))
        key = self.node("economic", nk, ident, data, times, ref)
        tickers = row.get("tickers", []) if kind == "event" else [row["ticker"]] if row.get("ticker") else []
        sources = row.get("sources", []) if kind == "thesis" else []
        if kind == "event":
            sid = row.get("source_id") or row.get("source_url") or row.get("url")
            if sid:
                sources = [sid]
            root_id = row.get("canonical_hash")
            if root_id:
                root = self.node("economic", "event", root_id, {"canonical_hash": root_id}, times, ref)
                self.edge(key, root, "observes_event", times, ref)
            # Native event-store entities can be a generic scope. Preserve them
            # as entities rather than guessing that every string is a ticker.
            for entity in row.get("entities", []):
                entity_key = self.node("economic", "entity", entity, {"entity": entity}, times, ref)
                self.edge(key, entity_key, "names_entity", times, ref)
                if entity not in tickers:
                    self.gap(entity_key, entity, "ENTITY_COMPANY_TYPE_NOT_ESTABLISHED", ref)
        for sid in sources:
            if not isinstance(sid, str) or not sid:
                self.gap(key, sid, "UNSUPPORTED_SOURCE_ID", ref)
                continue
            source = self.node("economic", "source", sid, {"evidence_reliability": None}, times, ref)
            self.edge(source, key, "cited_by" if kind == "thesis" else "reported_as", times, ref, polarity="unclassified")
            for ticker in tickers:
                self.edge(source, self.company(ticker, times, ref), "cited_for_company", times, ref,
                          polarity="unclassified", data={"basis": "explicit source plus ticker in same native record; not causal attribution"})
        for ticker in tickers:
            self.edge(self.company(ticker, times, ref), key, "subject_of", times, ref)
        if kind == "decisions":
            thesis_id = row.get("thesis_id")
            if thesis_id:
                self.edge(node_id("economic", "thesis", thesis_id), key, "explicit_thesis_ref", times, ref)
            else:
                self.gap(key, None, "MISSING_THESIS_ID_NO_LINEAGE_INFERRED", ref)
        for field, polarity in (("supportive_evidence_ids", "supportive"), ("contrary_evidence_ids", "contrary")):
            for eid in row.get(field, []):
                self.edge(node_id("economic", "evidence_ref", eid), key, "explicit_evidence_ref", times, ref, polarity=polarity)

    def registry(self, value: dict, ref: dict) -> None:
        if value.get("schema_version") != 1:
            raise ValueError("EXPECTED_V2_REGISTRY_SCHEMA_1")
        # Registry as_of is a planning date, not proof of availability at midnight.
        times = clocks({}, ref["read_at"])
        if not self.eligible("current_registry", times, ref):
            return
        for group, kind in (("tasks", "task"), ("requests", "request"), ("hypotheses", "hypothesis")):
            rows = value.get(group, [])
            if len(rows) > LIMIT_ROWS or len({r["id"] for r in rows}) != len(rows):
                raise ValueError("DUPLICATE_OR_OVERSIZE_REGISTRY_IDS")
            for row in rows:
                loc = {**ref, "locator": f"/{group}/{row['id']}"}
                key = self.node("operational", kind, row["id"], {k: row.get(k) for k in (
                    "title", "status", "source", "acceptance", "legacy_resolution")}, times, loc)
                for dep in row.get("dependencies", []):
                    self.edge(key, node_id("operational", "task", dep), "depends_on", times, loc)
                if row.get("task_id"):
                    self.edge(key, node_id("operational", "task", row["task_id"]), "belongs_to", times, loc)
                if not row.get("evidence"):
                    self.gap(key, None, "NO_REGISTERED_EVIDENCE", loc)
                for e in row.get("evidence", []):
                    path = str((self.registry_root / e["path"]).resolve())
                    supplied = self.by_path.get(path)
                    if supplied is None or supplied["ref"]["sha256"] != e.get("sha256"):
                        self.gap(key, e, "EVIDENCE_NOT_SUPPLIED_OR_HASH_MISMATCH", loc)
                        continue
                    et = clocks({}, e.get("verified_at"))
                    if not self.eligible(key, et, loc):
                        continue
                    evidence = self.node("operational", "evidence", e["sha256"],
                                         {"path": path, "reviewer": e.get("reviewer"), "acceptance_ids": e.get("acceptance_ids")}, times, supplied["ref"])
                    self.edge(key, evidence, "registered_evidence", times, loc)

    def build(self) -> dict:
        seen = set()
        for doc in self.documents:
            kind, value, ref = doc["kind"], doc["value"], doc["ref"]
            if (kind, ref["sha256"]) in seen:
                continue
            seen.add((kind, ref["sha256"]))
            if kind in {"beliefs", "scenarios", "registry"}:
                getattr(self, kind)(value, ref)
            elif kind != "receipt":
                rows = value if isinstance(value, list) else value.get("rows", []) if kind == "decisions" else [value]
                if len(rows) > LIMIT_ROWS:
                    raise ValueError("RECEIPT_ROW_LIMIT")
                for i, row in enumerate(rows):
                    self.economic_record(kind, row, {**ref, "locator": f"/rows/{i}" if kind == "decisions" else f"/{i}"}, value if isinstance(value, dict) else {})
        edges = []
        for edge in self.edges.values():
            if edge["from"] not in self.nodes or edge["to"] not in self.nodes:
                self.gap(edge["from"], edge["to"], "MISSING_REFERENCED_NODE", edge["facts"][0]["ref"])
            else:
                edges.append(edge)
        if len(self.nodes) > 2500 or len(edges) > 5000 or len(self.unresolved) > 5000:
            raise ValueError("BOUNDED_PROJECTION_LIMIT")
        return {"schema": "beta_v2_atlas_view/1", "as_of": self.as_of,
                "mode": "READ_ONLY_SAVED_RECEIPTS", "nodes": list(self.nodes.values()), "edges": edges,
                "unresolved": self.unresolved, "excluded": self.excluded,
                "source_refs": [d["ref"] for d in self.documents],
                "limitations": ["No causal inference or new exposure/weight calculation",
                                "Snapshot clocks are embedded producer assertions, not historical archive certification",
                                "Registry is current-read planning state; its date alone cannot establish historical availability",
                                "Source citation and shared company do not establish thesis-to-decision lineage"]}


def query(view: dict, start: str, target_kind: str, *, polarity: str = "all",
          as_of: str | None = None, max_depth: int = 3) -> dict:
    if view.get("schema") != "beta_v2_atlas_view/1" or not 1 <= max_depth <= 4:
        raise ValueError("BOUNDED_ATLAS_QUERY_REQUIRED")
    if polarity not in {"all", "supportive", "contrary", "unclassified"}:
        raise ValueError("UNKNOWN_POLARITY")
    cutoff = clock(as_of or view["as_of"])
    if cutoff != clock(view["as_of"]):
        raise ValueError("QUERY_REQUIRES_EXACT_VIEW_ASOF_REBUILD_FOR_ANOTHER_TIME")
    nodes = {n["id"]: n for n in view["nodes"]}
    queue = deque([(start, [])])
    paths = []
    while queue:
        current, path = queue.popleft()
        if len(path) == max_depth:
            continue
        for edge in view["edges"]:
            if edge["from"] != current or (polarity != "all" and edge["polarity"] not in (None, polarity)):
                continue
            if edge["to"] in {start, *(e["from"] for e in path)}:
                continue
            next_path = path + [edge]
            if nodes[edge["to"]]["kind"] == target_kind:
                paths.append(next_path)
            else:
                queue.append((edge["to"], next_path))
            if len(paths) + len(queue) > 1000:
                raise ValueError("QUERY_PATH_LIMIT")
    direct_task_evidence = nodes.get(start, {}).get("namespace") == "operational" and nodes[start]["kind"] == "task" and target_kind == "evidence"
    dependency_paths = []
    if direct_task_evidence:
        dependency_paths = [p for p in paths if not (len(p) == 1 and p[0]["relation"] == "registered_evidence")]
        paths = [p for p in paths if len(p) == 1 and p[0]["relation"] == "registered_evidence"]
    return {"schema": "beta_v2_atlas_query/1", "as_of": view["as_of"], "from": start,
            "target_kind": target_kind, "polarity": polarity, "paths": paths,
            "query_scope": "DIRECT_TASK_EVIDENCE" if direct_task_evidence else "REACHABLE_TYPED_PATHS",
            "dependency_paths": dependency_paths,
            "dependency_evidence_status": "REACHABLE_PREREQUISITE_EVIDENCE_ONLY" if dependency_paths else "NONE",
            "status": "MATCHED" if paths else "UNRESOLVED",
            "unresolved": [g for g in view["unresolved"] if g["owner"] == start],
            "source_refs": view["source_refs"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    build = sub.add_parser("build")
    build.add_argument("--receipt", action="append", required=True, metavar="KIND=PATH")
    build.add_argument("--registry-root", type=Path, default=Path(__file__).resolve().parents[1])
    build.add_argument("--as-of", required=True, help="timezone-aware instant, or now for actual current readback")
    ask = sub.add_parser("query")
    ask.add_argument("--view", type=Path, required=True)
    ask.add_argument("--from-node", required=True)
    ask.add_argument("--target-kind", required=True)
    ask.add_argument("--polarity", choices=("all", "supportive", "contrary", "unclassified"), default="all")
    ask.add_argument("--as-of")
    ask.add_argument("--max-depth", type=int, default=3)
    for item in (build, ask):
        item.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "build":
        docs = read_inputs(args.receipt)
        as_of = datetime.now(timezone.utc).isoformat() if args.as_of == "now" else args.as_of
        result = Projection(docs, as_of, args.registry_root).build()
        for doc in docs:
            if sha(Path(doc["ref"]["path"]).read_bytes()) != doc["ref"]["sha256"]:
                raise ValueError("SOURCE_CHANGED_DURING_PROJECTION")
    else:
        raw = args.view.read_bytes()
        result = query(strict_json(raw), args.from_node, args.target_kind, polarity=args.polarity,
                       as_of=args.as_of, max_depth=args.max_depth)
        result["view_ref"] = {"path": str(args.view.resolve()), "sha256": sha(raw)}
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"output": str(args.output), "sha256": sha(args.output.read_bytes()),
                      "nodes": len(result.get("nodes", [])), "edges": len(result.get("edges", [])),
                      "paths": len(result.get("paths", [])), "status": result.get("status", "PROJECTED")}))


if __name__ == "__main__":
    main()
