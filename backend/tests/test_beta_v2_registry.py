"""Offline contract tests: source coverage, dependency safety and evidence gates."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import beta_v2_registry as R  # noqa: E402 - explicit checkout import


@pytest.fixture
def registry():
    return json.loads((REPO / R.REGISTRY).read_text(encoding="utf-8"))


def test_real_registry_and_generated_views_are_consistent(registry):
    assert R.validate(registry) == []
    assert len(registry["tasks"]) == 17
    assert len(registry["requests"]) == 146
    assert len(registry["hypotheses"]) == 28
    assert R.main(["check", "--root", str(REPO)]) == 0


@pytest.mark.parametrize("group", ["tasks", "requests", "hypotheses"])
def test_missing_id_cannot_be_hidden_by_correct_total(registry, group):
    registry[group][-1] = copy.deepcopy(registry[group][0])
    errors = R.validate(registry)
    assert any("duplicate IDs" in e for e in errors)
    assert any("missing/unexpected IDs" in e for e in errors)


@pytest.mark.parametrize("group", ["tasks", "requests", "hypotheses"])
def test_missing_record_refused(registry, group):
    registry[group].pop()
    assert any("missing/unexpected IDs" in e for e in R.validate(registry))


@pytest.mark.parametrize("mapping", [None, "C99", "", "T03"])
def test_unmapped_or_unknown_request_task_refused(registry, mapping):
    registry["requests"][0]["task_id"] = mapping
    assert any("unmapped/unknown task_id" in e for e in R.validate(registry))


def test_silent_reassignment_from_workbook_refused(registry):
    registry["requests"][0]["task_id"] = "C01"
    assert any("differs from source task" in e for e in R.validate(registry))


def test_unknown_hypothesis_owner_task_refused(registry):
    registry["hypotheses"][0]["task_id"] = "C99"
    assert any("unmapped/unknown task_id" in e for e in R.validate(registry))


@pytest.mark.parametrize("group", ["tasks", "requests", "hypotheses"])
def test_source_row_tampering_refused(registry, group):
    registry[group][0]["source"]["row"] = 999
    assert any("invalid source sheet/row" in e for e in R.validate(registry))


def test_dependency_cycle_across_multiple_tasks(registry):
    # C03 -> C01 -> C00 -> C03, not merely a self-link.
    registry["tasks"][0]["dependencies"] = ["C03"]
    assert any("dependency cycle" in e for e in R.validate(registry))


def test_unknown_dependency_refused(registry):
    registry["tasks"][0]["dependencies"] = ["missing"]
    assert any("unknown dependency" in e for e in R.validate(registry))


@pytest.mark.parametrize("group", ["tasks", "requests", "hypotheses"])
def test_completion_without_evidence_fails(registry, group):
    registry[group][0]["status"] = "completed"
    assert any("completion without verified evidence" in e for e in R.validate(registry))


def _evidence(entry, root):
    path = root / "receipt.txt"
    path.write_text("Focused behavior reviewed; this fixture makes no runtime claim.\n", encoding="utf-8")
    return {"path": "receipt.txt", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "reviewer": "independent-fixture-reviewer", "summary": "Verified fixture criterion.",
            "verified_at": "2026-10-25T12:00:00Z",
            "acceptance_ids": [a["id"] for a in entry["acceptance"]]}


def test_valid_dated_hashed_reviewed_evidence_can_complete_one_request(registry, tmp_path):
    entry = registry["requests"][0]
    entry.update(status="completed", evidence=[_evidence(entry, tmp_path)])
    assert R.validate(registry, tmp_path) == []


@pytest.mark.parametrize("defect", ["absent", "hash", "reviewer", "date", "coverage", "outside"])
def test_false_completion_receipts_refused(registry, tmp_path, defect):
    entry = registry["requests"][0]
    evidence = _evidence(entry, tmp_path)
    entry.update(status="completed", evidence=[evidence])
    if defect == "absent":
        evidence["path"] = "does-not-exist.txt"
    elif defect == "hash":
        (tmp_path / "receipt.txt").write_text("Altered after review", encoding="utf-8")
    elif defect == "reviewer":
        evidence["reviewer"] = ""
    elif defect == "date":
        evidence["verified_at"] = "2026-10-25T12:00:00"  # timezone absent
    elif defect == "coverage":
        evidence["acceptance_ids"] = ["another-request:acceptance"]
    else:
        evidence["path"] = "../receipt.txt"
    errors = R.validate(registry, tmp_path)
    assert any("invalid evidence" in e for e in errors)
    assert any("completion without verified evidence" in e for e in errors)


def test_partial_acceptance_evidence_cannot_complete(registry, tmp_path):
    entry = registry["requests"][0]
    evidence = _evidence(entry, tmp_path)
    entry["acceptance"].append({"id": "second", "description": "A separate required behavior."})
    entry.update(status="completed", evidence=[evidence])
    assert any("completion without verified evidence" in e for e in R.validate(registry, tmp_path))


def test_task_receipt_cannot_hide_open_requests(registry, tmp_path):
    task = registry["tasks"][0]
    task.update(status="completed", evidence=[_evidence(task, tmp_path)])
    assert any("completed with open requests" in e for e in R.validate(registry, tmp_path))


def test_complete_entry_cannot_skip_dependency(registry, tmp_path):
    entry = registry["requests"][0]
    entry.update(status="completed", dependencies=["C02"], evidence=[_evidence(entry, tmp_path)])
    assert any("completed with open dependency C02" in e for e in R.validate(registry, tmp_path))


def test_unknown_green_status_is_not_accepted(registry):
    registry["tasks"][0]["status"] = "DONE"
    assert any("unknown status" in e for e in R.validate(registry))


@pytest.mark.parametrize("field,value", [("status", []), ("acceptance", [{"id": [], "description": "bad"}]), ("dependencies", "C01"), ("evidence", "receipt.txt")])
def test_malformed_entry_fields_fail_loud_without_crashing(registry, field, value):
    registry["tasks"][0][field] = value
    assert R.validate(registry)


def test_non_object_registry_refused():
    assert R.validate([]) == ["registry must be an object"]


def test_requests_inherit_workstream_prerequisites(registry):
    tasks = {t["id"]: t for t in registry["tasks"]}
    for request in registry["requests"]:
        assert set(tasks[request["task_id"]]["dependencies"]) <= set(request["dependencies"])


def test_renderer_escapes_table_pipes_and_is_deterministic(registry):
    registry["tasks"][0]["title"] = "First | second\nline"
    first = R.render_markdown(registry)
    assert "First \\| second line" in first
    assert first == R.render_markdown(registry)


def test_check_detects_drift_without_rewriting_and_render_repairs(registry, tmp_path):
    canonical = tmp_path / R.REGISTRY
    canonical.parent.mkdir(parents=True)
    canonical.write_text(json.dumps(registry), encoding="utf-8")
    assert R.main(["render", "--root", str(tmp_path)]) == 0
    output = tmp_path / "docs/AEGIS_BETA_V2_ROADMAP.md"
    output.write_text("stale\n", encoding="utf-8")
    assert R.main(["check", "--root", str(tmp_path)]) == 1
    assert output.read_text() == "stale\n"
    assert R.main(["render", "--root", str(tmp_path)]) == 0
    assert R.main(["check", "--root", str(tmp_path)]) == 0


def test_invalid_registry_render_writes_nothing(registry, tmp_path):
    registry["tasks"][0]["dependencies"] = ["C01"]
    canonical = tmp_path / R.REGISTRY
    canonical.parent.mkdir(parents=True)
    canonical.write_text(json.dumps(registry), encoding="utf-8")
    assert R.main(["render", "--root", str(tmp_path)]) == 1
    assert not (tmp_path / "docs/AEGIS_BETA_V2_ROADMAP.md").exists()


def test_import_does_not_overwrite_registry(registry, tmp_path):
    canonical = tmp_path / R.REGISTRY
    canonical.parent.mkdir(parents=True)
    original = json.dumps(registry)
    canonical.write_text(original, encoding="utf-8")
    assert R.main(["import-workbook", "--root", str(tmp_path), "--workbook", "missing.xlsx", "--start", "missing.md"]) == 1
    assert canonical.read_text(encoding="utf-8") == original


def test_workbook_reader_limits_sheets_and_preserves_row_numbers(tmp_path):
    path = tmp_path / "sample.xlsx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="' + R.NS["s"] + '" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Roadmap" sheetId="1" r:id="r1"/><sheet name="Holding reference" sheetId="2" r:id="r2"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="r1" Target="/xl/worksheets/sheet1.xml"/><Relationship Id="r2" Target="worksheets/private.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="' + R.NS["s"] + '"><sheetData><row r="5"><c r="A5" t="inlineStr"><is><t>C00</t></is></c></row></sheetData></worksheet>')
        # Private sheet deliberately has no member: reading it would fail.
    assert R.read_workbook(path) == {"Roadmap": {5: {"A": "C00"}}}


def test_deleted_copied_request_prerequisite_cannot_complete_with_valid_evidence(registry, tmp_path):
    request = next(r for r in registry["requests"] if r["id"] == "R009")
    request.update(status="completed", dependencies=[], evidence=[_evidence(request, tmp_path)])
    assert any("R009: completed with open dependency C00" in e for e in R.validate(registry, tmp_path))


def test_deleting_parent_edge_as_well_does_not_waive_workbook_prerequisite(registry, tmp_path):
    request = next(r for r in registry["requests"] if r["id"] == "R009")
    next(t for t in registry["tasks"] if t["id"] == "C01")["dependencies"] = []
    request.update(status="completed", dependencies=[], evidence=[_evidence(request, tmp_path)])
    assert any("R009: completed with open dependency C00" in e for e in R.validate(registry, tmp_path))


def test_legitimately_closed_parent_prerequisites_allow_scoped_request_completion(registry, tmp_path):
    for request in registry["requests"]:
        if request["task_id"] == "C00":
            request.update(status="completed", evidence=[_evidence(request, tmp_path)])
    task = next(t for t in registry["tasks"] if t["id"] == "C00")
    task.update(status="completed", evidence=[_evidence(task, tmp_path)])
    request = next(r for r in registry["requests"] if r["id"] == "R009")
    request.update(status="completed", dependencies=[], evidence=[_evidence(request, tmp_path)])
    assert R.validate(registry, tmp_path) == []
    assert next(t for t in registry["tasks"] if t["id"] == "C01")["status"] != "completed"


def test_extra_request_specific_prerequisite_survives_derivation(registry, tmp_path):
    request = registry["requests"][0]
    request.update(status="completed", dependencies=["C12"], evidence=[_evidence(request, tmp_path)])
    assert any("completed with open dependency C12" in e for e in R.validate(registry, tmp_path))


def test_joint_mutable_mapping_edits_fail_independent_baseline(registry, tmp_path):
    registry["requests"][0].update(task_id="C01", source_task_id="C01")
    errors = R.validate(registry, tmp_path)
    assert any("independently pinned workbook mapping" in e for e in errors)
    assert R.attest_sources(registry, root=tmp_path)["source_status"] != "attested"


def test_reviewed_routing_override_retains_original_source_owner(registry, tmp_path):
    request = registry["requests"][0]
    evidence = _evidence(request, tmp_path)
    request["task_id"] = "C01"
    request["routing_override"] = {"source_task_id": "C00", "task_id": "C01",
        "rationale": "Reviewed scoped routing exception; original source ownership retained.",
        "reviewed_by": "independent-fixture-reviewer", "reviewed_at": "2026-10-25T12:00:00Z",
        "evidence": {"path": evidence["path"], "sha256": evidence["sha256"]}}
    assert R.validate(registry, tmp_path) == []
    request["source_task_id"] = "C01"
    assert any("independently pinned workbook mapping" in e for e in R.validate(registry, tmp_path))


def test_unreviewed_routing_override_does_not_silently_change_owner(registry, tmp_path):
    request = registry["requests"][0]
    request.update(task_id="C01", routing_override={"rationale": "just do it"})
    assert any("without reviewed routing override" in e for e in R.validate(registry, tmp_path))


def test_valid_syntax_bogus_archive_digest_is_not_source_attestation(registry):
    registry["archives"]["owner-workbook"]["sha256"] = "0" * 64
    result = R.attest_sources(registry)
    assert result["source_status"] != "attested"
    assert any("archive digest differs from independent baseline" in e for e in result["errors"])


def test_wrong_archived_bytes_fail_even_if_registry_hash_is_changed_to_match(registry, tmp_path):
    workbook = tmp_path / "tampered.xlsx"
    workbook.write_bytes(b"arbitrary altered workbook bytes")
    registry["archives"]["owner-workbook"].update(path=str(workbook), sha256=hashlib.sha256(workbook.read_bytes()).hexdigest())
    result = R.attest_sources(registry)
    assert result["source_status"] != "attested"
    assert any("archived bytes do not match independent source pin" in e for e in result["errors"])


def test_unavailable_archives_are_explicitly_unverified_not_attested(registry, tmp_path):
    result = R.attest_sources(registry, workbook=tmp_path / "missing.xlsx", start=tmp_path / "missing.md")
    assert result["source_status"] == "unverified"
    assert result["activation_authorized"] is False


def test_baseline_cannot_be_replaced_with_self_declared_mapping(monkeypatch, tmp_path):
    baseline = R.load_source_baseline()
    baseline["binding"]["requests"][0]["task_id"] = "C01"
    path = tmp_path / R.SOURCE_BASELINE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(baseline), encoding="utf-8")
    monkeypatch.setattr(R, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="code pin mismatch"):
        R.load_source_baseline()


@pytest.mark.parametrize("text", ['{"status":"proposed","status":"completed"}', '{"source":{"row":5,"row":6}}', '{"archives":{"owner-workbook":{"sha256":"a","sha256":"b"}}}'])
def test_duplicate_json_keys_are_rejected_at_any_depth(text):
    with pytest.raises(ValueError, match="duplicate JSON key"):
        R.strict_json(text)


@pytest.mark.parametrize("text", ['{"value":NaN}', '{"value":Infinity}', '{"value":1e9999}'])
def test_nonfinite_json_numbers_refused(text):
    with pytest.raises(ValueError, match="nonfinite"):
        R.strict_json(text)


def test_cli_refuses_duplicate_authoritative_registry_keys(registry, tmp_path, capsys):
    path = tmp_path / R.REGISTRY
    path.parent.mkdir(parents=True)
    text = json.dumps(registry).replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1', 1)
    path.write_text(text, encoding="utf-8")
    assert R.main(["validate", "--root", str(tmp_path)]) == 1
    assert "duplicate JSON key" in capsys.readouterr().err


def test_offline_ci_structural_success_never_claims_archive_attestation(registry, tmp_path, capsys):
    path = tmp_path / R.REGISTRY
    path.parent.mkdir(parents=True)
    registry["archives"]["owner-workbook"]["path"] = "absent-private-source.xlsx"
    registry["archives"]["owner-start"]["path"] = "absent-private-start.md"
    path.write_text(json.dumps(registry), encoding="utf-8")
    assert R.main(["validate", "--root", str(tmp_path)]) == 0
    assert "source_status=UNVERIFIED" in capsys.readouterr().out


def test_hypothesis_cannot_delete_administrative_prerequisites(registry, tmp_path):
    hypothesis = registry["hypotheses"][0]
    hypothesis.update(status="completed", dependencies=[], evidence=[_evidence(hypothesis, tmp_path)])
    errors = R.validate(registry, tmp_path)
    assert any("H01: completed with open dependency C00" in e for e in errors)
    assert any("H01: completed with open dependency C05" in e for e in errors)


def test_hypothesis_can_complete_with_closed_prerequisites_without_parent_cycle(registry, tmp_path):
    for task_id in ("C00", "C01", "C05"):
        for entry in registry["requests"] + registry["tasks"]:
            if entry.get("task_id", entry["id"]) == task_id:
                entry.update(status="completed", evidence=[_evidence(entry, tmp_path)])
    hypothesis = registry["hypotheses"][0]
    hypothesis.update(status="completed", dependencies=[], evidence=[_evidence(hypothesis, tmp_path)])
    assert R.validate(registry, tmp_path) == []
    assert next(t for t in registry["tasks"] if t["id"] == "C09")["status"] != "completed"


@pytest.mark.parametrize("change", [
    {"status": "completed"}, {"status": "done"}, {"status": []},
    {"parent": "C00"}, {"id": "C15"}, {"depends_on": ["absent"]},
    {"depends_on": ["C10", "C10"]}, {"depends_on": [1]}, {"scope": ""},
])
def test_advisory_slices_cannot_bypass_acceptance(registry, tmp_path, change):
    item = {"id": "C15b", "parent": "C15", "scope": "Full population and fleet release",
            "depends_on": ["C10", "C13"], "status": "proposed"}
    item.update(change)
    registry["execution_slices"] = [item]
    assert R.validate(registry, tmp_path)


def test_slice_cycle_and_duplicate_ids_refuse(registry, tmp_path):
    a = {"id": "C05a", "parent": "C05", "scope": "existing", "depends_on": ["C05b"], "status": "proposed"}
    b = {"id": "C05b", "parent": "C05", "scope": "authenticated", "depends_on": ["C05a"], "status": "proposed"}
    registry["execution_slices"] = [a, b]
    assert any("slice dependency cycle" in e for e in R.validate(registry, tmp_path))
    registry["execution_slices"] = [a, a]
    assert any("duplicate execution slice" in e for e in R.validate(registry, tmp_path))


def test_valid_advisory_slices_allow_independent_open_parent_work(registry, tmp_path):
    registry["execution_slices"] = [
        {"id": "C05a", "parent": "C05", "scope": "existing-data readiness", "depends_on": ["C00"], "status": "in-progress"},
        {"id": "C05b", "parent": "C05", "scope": "authenticated acquisition", "depends_on": ["C05a"], "status": "blocked"}]
    assert R.validate(registry, tmp_path) == []
