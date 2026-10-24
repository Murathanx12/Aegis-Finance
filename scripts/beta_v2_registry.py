"""Offline Beta V2 planning registry. No scheduler, broker, network or activation.

registry.json is authoritative; the roadmap and two JSON indexes are projections.
The explicit import command reads only normalized planning sheets from the owner
workbook, never its holdings, stock reference or private conversation archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("docs/beta_v2/registry.json")
SOURCE_BASELINE = Path("docs/beta_v2/source_baseline.json")
# Independent code pin; never take this expectation from the mutable registry.
SOURCE_BASELINE_SHA256 = "c86768ac85e5a1a4f68a190ce4a0b85a9b5536c9e2f912127b25107afcf64b26"
TASK_IDS = tuple(f"C{i:02}" for i in range(16)) + ("B01",)
REQUEST_IDS = tuple(f"R{i:03}" for i in range(1, 147))
HYPOTHESIS_IDS = tuple(f"H{i:02}" for i in range(1, 29))
# Reviewed administrative prerequisites, not workbook trial registration.
HYPOTHESIS_PREREQUISITES = ("C00", "C05")
STATUSES = {"proposed", "inherited-unverified", "deferred", "in-progress", "blocked", "completed"}
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def strict_json(text: str | bytes) -> object:
    """Reject conflicting duplicate keys and nonfinite numbers at every depth."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def floating(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("nonfinite JSON number")
        return parsed
    def constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    return json.loads(text, object_pairs_hook=pairs, parse_float=floating, parse_constant=constant)


def load_source_baseline() -> dict:
    raw = (ROOT / SOURCE_BASELINE).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_BASELINE_SHA256:
        raise ValueError("independent source baseline code pin mismatch")
    return strict_json(raw)


def workbook_binding(workbook: Path) -> dict:
    """Minimal immutable provenance; no portfolio or private narrative fields."""
    sheets = read_workbook(workbook)
    binding = {"tasks": [], "requests": [], "hypotheses": []}
    for row, identifier in enumerate(TASK_IDS, 5):
        c = sheets["Roadmap"][row]
        if c.get("A") != identifier:
            raise ValueError(f"Roadmap row {row}: expected {identifier}")
        binding["tasks"].append({"id": identifier, "source": _source("Roadmap", row),
                                 "dependencies": [] if c["D"] == "None" else c["D"].split(",")})
    for row, identifier in enumerate(REQUEST_IDS, 5):
        c = sheets["Requests"][row]
        if c.get("A") != identifier:
            raise ValueError(f"Requests row {row}: expected {identifier}")
        binding["requests"].append({"id": identifier, "source": _source("Requests", row), "task_id": c["B"]})
    for row, identifier in enumerate(HYPOTHESIS_IDS, 5):
        if sheets["Hypotheses"][row].get("A") != identifier:
            raise ValueError(f"Hypotheses row {row}: expected {identifier}")
        binding["hypotheses"].append({"id": identifier, "source": _source("Hypotheses", row)})
    return binding


def _reviewed_routing_override(entry: dict, root: Path) -> bool:
    """A routing change preserves original workbook ownership and reviewed proof."""
    override = entry.get("routing_override")
    if not isinstance(override, dict):
        return False
    try:
        if (override["source_task_id"] != entry["source_task_id"] or
            override["task_id"] != entry["task_id"] or
            any(not isinstance(override.get(k), str) or not override[k].strip()
                for k in ("rationale", "reviewed_by", "reviewed_at"))):
            return False
        if datetime.fromisoformat(override["reviewed_at"].replace("Z", "+00:00")).tzinfo is None:
            return False
        proof = override["evidence"]
        path = (root / proof["path"]).resolve()
        return (path.is_relative_to(root.resolve()) and path.is_file() and
                hashlib.sha256(path.read_bytes()).hexdigest() == proof["sha256"])
    except (KeyError, TypeError, ValueError, OSError):
        return False


def attest_sources(registry: dict, *, root: Path = ROOT, workbook: Path | None = None,
                   start: Path | None = None) -> dict:
    """Explicit archived-byte AND pinned workbook ownership attestation, read-only."""
    receipt = {"mode": "source-attestation", "source_status": "failed", "activation_authorized": False,
               "observed_at": datetime.now(timezone.utc).isoformat(),
               "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "baseline_sha256": SOURCE_BASELINE_SHA256, "archives": [], "errors": []}
    errors = receipt["errors"]
    errors.extend(validate(registry, root))
    if not isinstance(registry, dict):
        return receipt
    receipt["registry_normalized_sha256"] = hashlib.sha256(_json(registry).encode("utf-8")).hexdigest()
    try:
        baseline = load_source_baseline()
        missing = False
        failed = bool(errors)
        for key, override in (("owner-workbook", workbook), ("owner-start", start)):
            declared = registry.get("archives", {}).get(key, {})
            expected = baseline["archives"][key]
            if declared.get("sha256") != expected:
                errors.append(f"{key}: registry archive digest differs from independent baseline")
                failed = True
            path = override or Path(declared.get("path", ""))
            if not path.is_absolute():
                path = root / path
            record = {"id": key, "path": path.as_posix(), "expected_sha256": expected, "observed_sha256": None}
            receipt["archives"].append(record)
            try:
                observed = hashlib.sha256(path.read_bytes()).hexdigest()
                record["observed_sha256"] = observed
                if observed != expected:
                    errors.append(f"{key}: archived bytes do not match independent source pin")
                    failed = True
                elif key == "owner-workbook" and workbook_binding(path) != baseline["binding"]:
                    errors.append("archived workbook row/task binding differs from independent baseline")
                    failed = True
            except OSError:
                missing = True
                errors.append(f"{key}: archive unavailable; source attestation unverified")
        receipt["source_status"] = "failed" if failed else "unverified" if missing else "attested"
    except (KeyError, TypeError, ValueError, OSError, zipfile.BadZipFile) as exc:
        errors.append(f"source attestation refused: {exc}")
    return receipt


def read_workbook(path: Path) -> dict:
    """Read three named sheets using stdlib OOXML; preserve physical row numbers."""
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(x.itertext()) for x in
                       ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", NS)]
        relations = {x.attrib["Id"]: x.attrib["Target"] for x in
                     ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        sheets = {}
        for sheet in ET.fromstring(archive.read("xl/workbook.xml")).findall("s:sheets/s:sheet", NS):
            name = sheet.attrib["name"]
            if name not in {"Roadmap", "Requests", "Hypotheses"}:
                continue
            rel = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = relations[rel]
            member = target.lstrip("/") if target.startswith("/") else "xl/" + target
            rows = {}
            for row in ET.fromstring(archive.read(member)).findall("s:sheetData/s:row", NS):
                cells = {}
                for cell in row.findall("s:c", NS):
                    column = re.sub(r"\d", "", cell.attrib["r"])
                    kind = cell.attrib.get("t")
                    value = cell.findtext("s:v", "", NS)
                    if kind == "s":
                        value = strings[int(value)]
                    elif kind == "inlineStr":
                        value = "".join(cell.find("s:is", NS).itertext())
                    cells[column] = value
                rows[int(row.attrib["r"])] = cells
            sheets[name] = rows
    return sheets


def _source(sheet: str, row: int) -> dict:
    return {"archive": "owner-workbook", "sheet": sheet, "row": row}


def _base(identifier: str, owner: str, source: dict, acceptance: str) -> dict:
    return {"id": identifier, "owner": owner, "source": source,
            "status": "proposed", "dependencies": [], "evidence": [],
            "acceptance": [{"id": identifier + ":acceptance", "description": acceptance}],
            "revisit": "Reconcile current local evidence and unresolved predecessors before execution; review after dependency or evidence changes.",
            "legacy_aliases": [], "legacy_resolution": "inherited-unverified"}


def import_workbook(workbook: Path, start: Path) -> dict:
    sheets = read_workbook(workbook)
    tasks, requests, hypotheses = [], [], []
    for row, identifier in enumerate(TASK_IDS, 5):
        c = sheets["Roadmap"][row]
        if c.get("A") != identifier:
            raise ValueError(f"Roadmap row {row}: expected {identifier}")
        t = _base(identifier, c["E"], _source("Roadmap", row), c["H"])
        t.update(title=c["B"], wave=c["C"], deliverable=c["G"], source_status=c["F"],
                 dependencies=[] if c["D"] == "None" else c["D"].split(","))
        if identifier == "B01":
            t.update(status="deferred", revisit="Reopen only when the owner reactivates parked business work.")
        tasks.append(t)
    owners = {t["id"]: t["owner"] for t in tasks}
    dependencies = {t["id"]: t["dependencies"] for t in tasks}
    for row, identifier in enumerate(REQUEST_IDS, 5):
        c = sheets["Requests"][row]
        if c.get("A") != identifier:
            raise ValueError(f"Requests row {row}: expected {identifier}")
        r = _base(identifier, owners[c["B"]], _source("Requests", row),
                  "Demonstrate this request's summarized behavior with dated evidence and independent review: " + c["D"])
        r.update(task_id=c["B"], source_task_id=c["B"], title=c["C"], summary=c["D"],
                 dependencies=list(dependencies[c["B"]]),
                 priority=c["F"], source_basis=c["G"], source_status=c["E"],
                 source_legacy_id=c.get("J", ""), status="inherited-unverified")
        if c["E"] == "DEFERRED_OWNER":
            r.update(status="deferred", revisit="Owner reactivation of B01 and refreshed eligibility/evidence.")
        # RESOLVE_LOCALLY is an unresolved instruction, never an actual legacy ID.
        if c.get("J") and c["J"] != "RESOLVE_LOCALLY":
            r["legacy_aliases"] = [c["J"]]
        requests.append(r)
    for row, identifier in enumerate(HYPOTHESIS_IDS, 5):
        c = sheets["Hypotheses"][row]
        if c.get("A") != identifier:
            raise ValueError(f"Hypotheses row {row}: expected {identifier}")
        h = _base(identifier, owners["C09"], _source("Hypotheses", row),
                  "Reconcile prior trials and closed cells, pre-register an admissible design, calibrate the instrument, and record a scoped result including power and controls.")
        h.update(title=c["B"], first_comparison=c["C"], previous_report_state=c["D"],
                 source_status=c["E"], scope_note=c["F"], task_id="C09",
                   mapping_status="proposed", dependencies=list(HYPOTHESIS_PREREQUISITES),
                 status="inherited-unverified" if row < 23 else "proposed",
                 revisit="Check prior trial IDs, NEGATIVE_RESULTS and canon before registration; underpowered evidence alone cannot reopen a closed cell.")
        hypotheses.append(h)
    def archive(path: Path) -> dict:
        return {"path": path.as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return {"schema_version": 1, "as_of": "2026-10-25", "purpose": "Private planning; no activation or completion claim.",
            "archives": {"owner-workbook": archive(workbook), "owner-start": archive(start)},
            "integration": {
                "mode": "planning-only",
                "inspected": ["scripts/owner_queue.py", "scripts/task_keeper.py", "scripts/night_queue_plan.py", "backend/services/task_receipts.py"],
                "boundary": "Existing phone inbox, OS task registrations, receipt health and nightly research planner retain ownership. This registry neither dispatches nor rewrites them.",
                "legacy_policy": "Retain legacy IDs when verified; empty aliases plus inherited-unverified mean unresolved, not absent or retired. Coordinator must bind current continuation receipts; V1/V1.1 is not declared complete.",
                "hypothesis_mapping": "C09 is a proposed administrative home for all hypotheses, not a workbook claim or an experiment registration."},
            "tasks": tasks, "requests": requests, "hypotheses": hypotheses}


def validate(registry: dict, root: Path = ROOT) -> list[str]:
    """Offline structural validation; external archive attestation UNVERIFIED.

    Validation verifies evidence integrity and declared acceptance coverage, not
    the scientific truth or runtime effectiveness of a reviewer's conclusion.
    """
    errors = []
    if not isinstance(registry, dict):
        return ["registry must be an object"]
    try:
        baseline = load_source_baseline()
    except (OSError, ValueError) as exc:
        return [f"independent source baseline unavailable/invalid: {exc}"]
    original_tasks = {x["id"]: x for x in baseline["binding"]["tasks"]}
    original_requests = {x["id"]: x for x in baseline["binding"]["requests"]}
    if registry.get("schema_version") != 1:
        errors.append("unsupported schema_version")
    if not isinstance(registry.get("archives"), dict):
        errors.append("missing archives")
    else:
        for key in ("owner-workbook", "owner-start"):
            a = registry["archives"].get(key, {})
            if not a.get("path") or not re.fullmatch(r"[0-9a-f]{64}", str(a.get("sha256", ""))):
                errors.append(f"invalid archive {key}")
    groups = (("tasks", TASK_IDS, "Roadmap"), ("requests", REQUEST_IDS, "Requests"),
              ("hypotheses", HYPOTHESIS_IDS, "Hypotheses"))
    rows_by_group = {}
    for name, expected, sheet in groups:
        rows = registry.get(name, [])
        if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
            errors.append(f"{name}: expected list of objects")
            rows = []
        rows_by_group[name] = rows
        ids = [x.get("id") for x in rows]
        if len(set(str(i) for i in ids)) != len(ids):
            errors.append(f"{name}: duplicate IDs")
        if set(str(i) for i in ids) != set(expected):
            errors.append(f"{name}: missing/unexpected IDs: missing={sorted(set(expected)-set(str(i) for i in ids))}; unexpected={sorted(set(str(i) for i in ids)-set(expected))}")
        for entry in rows:
            identifier = entry.get("id", "<missing>")
            for field in ("owner", "revisit", "title", "legacy_resolution"):
                if not isinstance(entry.get(field), str) or not entry[field].strip():
                    errors.append(f"{identifier}: missing {field}")
            if not isinstance(entry.get("status"), str) or entry["status"] not in STATUSES:
                errors.append(f"{identifier}: unknown status")
            src = entry.get("source", {})
            expected_row = expected.index(identifier) + 5 if identifier in expected else -1
            if src != _source(sheet, expected_row):
                errors.append(f"{identifier}: invalid source sheet/row")
            for field in ("dependencies", "legacy_aliases", "evidence", "acceptance"):
                if not isinstance(entry.get(field), list):
                    errors.append(f"{identifier}: {field} must be a list")
            for field in ("dependencies", "legacy_aliases"):
                values = entry.get(field, [])
                if isinstance(values, list) and (any(not isinstance(v, str) or not v.strip() for v in values) or len(set(str(v) for v in values)) != len(values)):
                    errors.append(f"{identifier}: invalid {field}")
            acceptance = entry.get("acceptance", [])
            if not isinstance(acceptance, list) or not acceptance or any(
                not isinstance(a, dict) or any(not isinstance(a.get(k), str) or not a[k].strip()
                                              for k in ("id", "description")) for a in acceptance
            ):
                errors.append(f"{identifier}: missing acceptance criteria")
                acceptance = []
            criteria = {a["id"] for a in acceptance}
            if len(criteria) != len(acceptance):
                errors.append(f"{identifier}: duplicate acceptance IDs")
            evidence = entry.get("evidence", [])
            if not isinstance(evidence, list):
                evidence = []
            covered = set()
            for e in evidence:
                try:
                    if not isinstance(e, dict) or any(
                        not isinstance(e.get(k), str) or not e[k].strip()
                        for k in ("reviewer", "summary", "verified_at", "path", "sha256")
                    ):
                        raise ValueError("nonblank reviewer, summary, verified_at, path and sha256 required")
                    stamp = datetime.fromisoformat(e["verified_at"].replace("Z", "+00:00"))
                    if stamp.tzinfo is None:
                        raise ValueError("timezone required")
                    path = (root / e["path"]).resolve()
                    if not path.is_relative_to(root.resolve()) or not path.is_file():
                        raise ValueError("evidence must be an existing repository file")
                    if hashlib.sha256(path.read_bytes()).hexdigest() != e["sha256"]:
                        raise ValueError("evidence hash mismatch")
                    accepted = e["acceptance_ids"]
                    if not isinstance(accepted, list) or not accepted or any(not isinstance(a, str) for a in accepted) or not set(accepted) <= criteria:
                        raise ValueError("invalid evidence acceptance_ids")
                    covered.update(accepted)
                except (KeyError, TypeError, ValueError, OSError) as exc:
                    errors.append(f"{identifier}: invalid evidence: {exc}")
            if entry.get("status") == "completed" and (not criteria or covered != criteria):
                errors.append(f"{identifier}: completion without verified evidence for every acceptance criterion")
    tasks = {x.get("id"): x for x in rows_by_group["tasks"] if isinstance(x.get("id"), str)}
    for name in ("requests", "hypotheses"):
        for entry in rows_by_group[name]:
            if not isinstance(entry.get("task_id"), str) or entry["task_id"] not in tasks:
                errors.append(f"{entry.get('id')}: unmapped/unknown task_id")
            if name == "requests" and entry.get("task_id") != entry.get("source_task_id"):
                if not _reviewed_routing_override(entry, root):
                    errors.append(f"{entry.get('id')}: request mapping differs from source task without reviewed routing override")
            if name == "requests":
                original = original_requests.get(entry.get("id")) if isinstance(entry.get("id"), str) else None
                if original and entry.get("source_task_id") != original["task_id"]:
                    errors.append(f"{entry.get('id')}: original source task differs from independently pinned workbook mapping")
    # Effective graph derives immutable task prerequisites plus current extras.
    # Deleting a copied request edge or its parent task edge cannot waive it.
    task_dependencies = {}
    for identifier, task in tasks.items():
        declared = task.get("dependencies", [])
        effective = list(original_tasks.get(identifier, {}).get("dependencies", []))
        if isinstance(declared, list):
            effective += [d for d in declared if isinstance(d, str)]
        task_dependencies[identifier] = list(dict.fromkeys(effective))
    for name, rows in rows_by_group.items():
        for entry in rows:
            deps = entry.get("dependencies", [])
            if not isinstance(deps, list):
                continue
            deps = list(deps)
            if name == "tasks":
                deps += task_dependencies.get(entry.get("id"), [])
            elif name == "requests":
                parent = entry.get("task_id")
                if isinstance(parent, str):
                    deps += task_dependencies.get(parent, [])
                original = original_requests.get(entry.get("id")) if isinstance(entry.get("id"), str) else None
                if original:
                    deps += task_dependencies.get(original["task_id"], [])
            elif name == "hypotheses":
                deps += list(HYPOTHESIS_PREREQUISITES)
            for dep in deps:
                if not isinstance(dep, str) or dep not in tasks:
                    errors.append(f"{entry.get('id')}: unknown dependency {dep}")
                elif entry.get("status") == "completed" and tasks[dep].get("status") != "completed":
                    errors.append(f"{entry.get('id')}: completed with open dependency {dep}")
    visited, active = set(), set()
    def visit(identifier: str) -> None:
        if identifier in active:
            errors.append(f"dependency cycle at {identifier}")
            return
        if identifier in visited:
            return
        active.add(identifier)
        deps = task_dependencies[identifier]
        for dep in deps if isinstance(deps, list) else []:
            if isinstance(dep, str) and dep in tasks:
                visit(dep)
        active.remove(identifier)
        visited.add(identifier)
    for identifier in sorted(tasks):
        visit(identifier)
    for identifier, task in tasks.items():
        if task.get("status") == "completed":
            for name in ("requests", "hypotheses"):
                if any(e.get("task_id") == identifier and e.get("status") != "completed" for e in rows_by_group[name]):
                    errors.append(f"{identifier}: completed with open {name}")
    # Slices are advisory planning views until a scoped acceptance contract is
    # implemented. They cannot bypass parent admission by claiming completion.
    slices = registry.get("execution_slices", [])
    slice_map = {}
    if not isinstance(slices, list):
        errors.append("execution_slices must be a list")
        slices = []
    for item in slices:
        if not isinstance(item, dict):
            errors.append("execution slice must be an object")
            continue
        identifier, parent = item.get("id"), item.get("parent")
        if not isinstance(identifier, str) or not re.fullmatch(r"[CB]\d{2}[a-z]", identifier):
            errors.append("invalid execution slice ID")
            continue
        if identifier in slice_map:
            errors.append(f"duplicate execution slice {identifier}")
        slice_map[identifier] = item
        if not isinstance(parent, str) or parent not in tasks or identifier[:-1] != parent:
            errors.append(f"{identifier}: invalid slice parent")
        if not isinstance(item.get("status"), str) or item["status"] not in STATUSES - {"completed"}:
            errors.append(f"{identifier}: advisory slices cannot claim completion or unknown status")
        if not isinstance(item.get("scope"), str) or not item["scope"].strip():
            errors.append(f"{identifier}: missing slice scope")
    slice_deps = {}
    for identifier, item in slice_map.items():
        deps = item.get("depends_on")
        if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps):
            errors.append(f"{identifier}: invalid slice dependencies")
            continue
        slice_deps[identifier] = deps
        if len(set(deps)) != len(deps) or any(d not in tasks and d not in slice_map for d in deps):
            errors.append(f"{identifier}: unknown or duplicate slice dependency")
    slice_seen, slice_active = set(), set()
    def visit_slice(identifier):
        if identifier in slice_active:
            errors.append(f"execution slice dependency cycle at {identifier}")
            return
        if identifier in slice_seen:
            return
        slice_active.add(identifier)
        for dep in slice_deps.get(identifier, []):
            if dep in slice_map:
                visit_slice(dep)
        slice_active.remove(identifier)
        slice_seen.add(identifier)
    for identifier in slice_map:
        visit_slice(identifier)
    return errors


def _json(value: dict) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def render_markdown(registry: dict) -> str:
    def cell(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["# AEGIS Beta V2 roadmap", "", "Generated from `docs/beta_v2/registry.json` by `scripts/beta_v2_registry.py`; edit the registry, then render.", "",
             "Private planning baseline: 17 workstreams, 146 request mappings, 28 hypotheses. V1/V1.1 remains unverified; no runtime activation or investment acceptance is asserted.", "",
             "Source rows refer to the archived owner workbook. Blank evidence and legacy aliases mean unresolved, never completed or retired. Hypothesis assignment to C09 is proposed administrative ownership only.", "",
             "| ID | Workstream | Status | Owner | Dependencies | Requests | Source |",
             "|---|---|---|---|---|---|---|"]
    for t in registry["tasks"]:
        ids = [r["id"] for r in registry["requests"] if r["task_id"] == t["id"]]
        values = (t["id"], t["title"], t["status"], t["owner"], ", ".join(t["dependencies"]) or "None", ", ".join(ids), f"Roadmap row {t['source']['row']}")
        lines.append("| " + " | ".join(map(cell, values)) + " |")
    for t in registry["tasks"]:
        lines.extend(["", f"## {t['id']} — {t['title']}", "", "Deliverable: " + t["deliverable"], "",
                      "Acceptance: " + "; ".join(a["description"] for a in t["acceptance"]), "",
                      "Evidence: " + ("; ".join(e["path"] for e in t["evidence"]) or "None verified."), "",
                      "Revisit: " + t["revisit"], "", "Legacy aliases: " + (", ".join(t["legacy_aliases"]) or "Unresolved; inherited-unverified.")])
    lines.extend(["", "## Hypothesis register", "", "These are candidate questions, not registered trials or results. H01–H18 require inherited-trial reconciliation; H19–H28 are proposals.", "",
                  "| ID | Question | Status | Proposed task | Source |", "|---|---|---|---|---|"])
    for h in registry["hypotheses"]:
        lines.append("| " + " | ".join(map(cell, (h["id"], h["title"], h["status"], h["task_id"], f"Hypotheses row {h['source']['row']}"))) + " |")
    return "\n".join(lines) + "\n"


def projections(registry: dict) -> dict[Path, str]:
    digest = hashlib.sha256(_json(registry).encode()).hexdigest()
    common = {"generated_from": REGISTRY.as_posix(), "registry_sha256": digest}
    return {Path("docs/AEGIS_BETA_V2_ROADMAP.md"): render_markdown(registry),
            Path("docs/beta_v2/request_coverage.json"): _json({**common, "count": len(registry["requests"]), "requests": registry["requests"]}),
            Path("docs/beta_v2/hypotheses.json"): _json({**common, "count": len(registry["hypotheses"]), "hypotheses": registry["hypotheses"]})}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "attest", "render", "check", "import-workbook"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--workbook", type=Path)
    parser.add_argument("--start", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "import-workbook":
            if not args.workbook or not args.start:
                parser.error("import-workbook requires --workbook and --start")
            if (args.root / REGISTRY).exists():
                raise ValueError("registry already exists; import refuses to overwrite status/evidence history")
            registry = import_workbook(args.workbook, args.start)
        else:
            registry = strict_json((args.root / REGISTRY).read_bytes())
        if args.command == "attest":
            receipt = attest_sources(registry, root=args.root, workbook=args.workbook, start=args.start)
            print(_json(receipt), end="")
            return 0 if receipt["source_status"] == "attested" else 1
        errors = validate(registry, args.root)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        outputs = projections(registry)
        if args.command == "check":
            stale = [str(p) for p, content in outputs.items() if not (args.root / p).exists() or (args.root / p).read_text(encoding="utf-8") != content]
            if stale:
                print("stale projections: " + ", ".join(stale), file=sys.stderr)
                return 1
        if args.command in {"render", "import-workbook"}:
            if args.command == "import-workbook":
                outputs = {REGISTRY: _json(registry), **outputs}
            for path, content in outputs.items():
                dest = args.root / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8", newline="\n")
        print("OK structural: 17 workstreams; 146 requests mapped; 28 hypotheses; " + args.command +
              "; source_status=UNVERIFIED (external archives not attested; run attest)")
        return 0
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
        print(f"registry error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
