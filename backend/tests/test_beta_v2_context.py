"""Context gate tests use local files only, including resume and stale-byte cases."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import beta_v2_context as C  # noqa: E402 - explicit checkout import


@pytest.fixture
def packet(tmp_path):
    (tmp_path / "canon.md").write_text("Known prior: gates need calibration.\n", encoding="utf-8")
    (tmp_path / "continuation.md").write_text("Dated continuation. Runtime unverified.\n", encoding="utf-8")
    def spec(path):
        return {"path": path, "expected_sha256": hashlib.sha256((tmp_path / path).read_bytes()).hexdigest()}
    return {"schema": C.PACKET_SCHEMA, "task_id": "C10", "objective": "Bind explicit census context before a worker.",
            "sources": [{"id": "canon", **spec("canon.md")}], "continuation": spec("continuation.md"),
            "authority_boundaries": {"activation_authorized": False,
                "permitted_actions": ["Read named sources and report mismatches."],
                "forbidden_actions": ["No activation, orders or NAV writes."]},
            "prior_findings": [{"id": "calibration", "source_id": "canon", "expected_anchor": "gates need calibration"}],
            "evidence_requirements": ["Exact source hash and anchor readback."]}


def test_exact_binding_is_not_runtime_or_activation_authority(packet, tmp_path):
    receipt = C.bind(packet, root=tmp_path)
    assert receipt["context_status"] == "bound"
    assert receipt["runtime_status"] == "unknown"
    assert receipt["activation_authorized"] is False
    assert all(s["status"] == "matched" for s in receipt["sources"])
    assert "gates need calibration" not in json.dumps(receipt)
    assert C.bind(packet, root=tmp_path)["source_fingerprint"] == receipt["source_fingerprint"]


@pytest.mark.parametrize("raw", ['{"hash":"a","hash":"b"}', '{"nested":{"x":1,"x":2}}',
                                '{"x":NaN}', '{"x":Infinity}', '{"x":1e9999}'])
def test_conflicting_or_nonfinite_json_refuses(raw):
    with pytest.raises(ValueError):
        C.strict_json(raw)


@pytest.mark.parametrize("target", ["packet", "prior"])
def test_cli_refuses_duplicate_packet_or_prior_fields(packet, tmp_path, capsys, target):
    packet_path = tmp_path / "packet.json"
    prior_path = tmp_path / "prior.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    prior_path.write_text(json.dumps(C.bind(packet, root=tmp_path)), encoding="utf-8")
    selected = packet_path if target == "packet" else prior_path
    selected.write_text('{"schema":"old","schema":"new"}', encoding="utf-8")
    assert C.main(["--packet", str(packet_path), "--prior-receipt", str(prior_path),
                   "--root", str(tmp_path)]) == 1
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["context_status"] == "unknown"
    assert receipt["activation_authorized"] is False
    assert "duplicate JSON key" in receipt["errors"][0]


def test_wrong_expected_hash_fails_closed(packet, tmp_path):
    packet["sources"][0]["expected_sha256"] = "0" * 64
    receipt = C.bind(packet, root=tmp_path)
    assert receipt["context_status"] == "unknown"
    assert receipt["sources"][0]["status"] == "changed"
    assert receipt["sources"][0]["observed_sha256"] != "0" * 64


def test_missing_source_reports_missing(packet, tmp_path):
    (tmp_path / "canon.md").unlink()
    receipt = C.bind(packet, root=tmp_path)
    assert receipt["context_status"] == "unknown"
    assert receipt["sources"][0]["status"] == "missing"


@pytest.mark.parametrize("expected", [None, "", "unknown", "sha256", "A" * 64, 7])
def test_unknown_expected_values_cannot_pass(packet, tmp_path, expected):
    packet["sources"][0]["expected_sha256"] = expected
    receipt = C.bind(packet, root=tmp_path)
    assert receipt["context_status"] == "unknown"
    assert receipt["sources"][0]["observed_sha256"] is None


def test_missing_expected_anchor_is_not_semantic_success(packet, tmp_path):
    packet["prior_findings"][0]["expected_anchor"] = "A different related page is not this anchor"
    receipt = C.bind(packet, root=tmp_path)
    assert receipt["context_status"] == "unknown"
    assert receipt["prior_findings"][0]["status"] == "missing_anchor"
    assert receipt["sources"][0]["status"] == "matched"


def test_anchor_in_unbound_source_cannot_pass(packet, tmp_path):
    packet["prior_findings"][0]["source_id"] = "not-listed"
    assert C.bind(packet, root=tmp_path)["context_status"] == "unknown"


def test_resume_rehashes_and_catches_changed_source_even_with_same_mtime(packet, tmp_path):
    prior = C.bind(packet, root=tmp_path)
    path = tmp_path / "canon.md"
    times = path.stat()
    path.write_text("Known prior: gates need calibration. Added change.\n", encoding="utf-8")
    os.utime(path, ns=(times.st_atime_ns, times.st_mtime_ns))
    current = C.bind(packet, root=tmp_path, prior=prior)
    assert current["context_status"] == "unknown"
    assert current["source_fingerprint"] != prior["source_fingerprint"]
    assert current["delta"]["sources"][0]["state"] == "unbound_now"


def test_updating_expectation_on_resume_still_reports_changed_bytes(packet, tmp_path):
    prior = C.bind(packet, root=tmp_path)
    path = tmp_path / "canon.md"
    path.write_text("Changed source, gates need calibration.\n", encoding="utf-8")
    packet["sources"][0]["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    current = C.bind(packet, root=tmp_path, prior=prior)
    assert current["context_status"] == "bound"
    assert current["delta"]["packet_changed"] is True
    assert current["delta"]["sources"][0]["state"] == "changed"


def test_unchanged_old_bytes_are_reobserved_but_never_live_runtime(packet, tmp_path):
    for name in ("canon.md", "continuation.md"):
        os.utime(tmp_path / name, (1, 1))
    prior = C.bind(packet, root=tmp_path)
    current = C.bind(packet, root=tmp_path, prior=prior)
    assert current["context_status"] == "bound"
    assert current["runtime_status"] == "unknown"
    assert all(s["state"] == "unchanged_bytes_reobserved" for s in current["delta"]["sources"])
    assert "mtime" not in json.dumps(current)


def test_mtime_only_change_cannot_change_source_version(packet, tmp_path):
    prior = C.bind(packet, root=tmp_path)
    os.utime(tmp_path / "canon.md", (123, 123))
    assert C.bind(packet, root=tmp_path)["source_fingerprint"] == prior["source_fingerprint"]


@pytest.mark.parametrize("field", ["objective", "task_id", "sources", "continuation", "authority_boundaries", "prior_findings", "evidence_requirements"])
def test_missing_required_packet_context_refuses(packet, tmp_path, field):
    del packet[field]
    assert C.bind(packet, root=tmp_path)["context_status"] == "unknown"


def test_packet_cannot_authorize_activation(packet, tmp_path):
    packet["authority_boundaries"]["activation_authorized"] = True
    receipt = C.bind(packet, root=tmp_path)
    assert receipt["context_status"] == "unknown"
    assert receipt["activation_authorized"] is False


@pytest.mark.parametrize("path", ["*.md", "docs/[ab].md", ".env", "secrets/file.md", ".ssh/id_rsa", "../escape.md", "https://example.com/file", "//host/share/file", "file.md:stream", "credentials.json"])
def test_paths_do_not_expand_or_read_secret_or_external_locations(packet, tmp_path, path):
    packet["sources"][0]["path"] = path
    receipt = C.bind(packet, root=tmp_path)
    assert receipt["context_status"] == "unknown"
    assert receipt["sources"][0]["observed_sha256"] is None


def test_external_root_requires_explicit_caller_allowance(packet, tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    for name in ("canon.md", "continuation.md"):
        (external / name).write_bytes((tmp_path / name).read_bytes())
    packet["sources"][0]["path"] = str(external / "canon.md")
    packet["continuation"]["path"] = str(external / "continuation.md")
    assert C.bind(packet, root=workspace)["context_status"] == "unknown"
    assert C.bind(packet, root=workspace, source_roots=[external])["context_status"] == "bound"


def test_duplicate_source_ids_and_paths_refused(packet, tmp_path):
    packet["sources"].append(copy.deepcopy(packet["sources"][0]))
    assert C.bind(packet, root=tmp_path)["context_status"] == "unknown"
    packet["sources"][-1]["id"] = "other"
    assert C.bind(packet, root=tmp_path)["context_status"] == "unknown"


def test_prior_receipt_for_another_task_refused(packet, tmp_path):
    prior = C.bind(packet, root=tmp_path)
    prior["task_id"] = "C01"
    assert C.bind(packet, root=tmp_path, prior=prior)["context_status"] == "unknown"


def test_prior_receipt_tampered_source_fingerprint_refused(packet, tmp_path):
    prior = C.bind(packet, root=tmp_path)
    prior["sources"][0]["observed_sha256"] = "0" * 64
    assert C.bind(packet, root=tmp_path, prior=prior)["context_status"] == "unknown"


def test_cli_stdout_receipt_and_nonzero_refusal(packet, tmp_path, capsys):
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    assert C.main(["--packet", str(path), "--root", str(tmp_path)]) == 0
    first = json.loads(capsys.readouterr().out)
    prior = tmp_path / "prior.json"
    prior.write_text(json.dumps(first), encoding="utf-8")
    (tmp_path / "continuation.md").write_text("Changed continuation", encoding="utf-8")
    assert C.main(["--packet", str(path), "--root", str(tmp_path), "--prior-receipt", str(prior)]) == 1
    assert json.loads(capsys.readouterr().out)["context_status"] == "unknown"


def test_invalid_packet_json_emits_unknown_receipt(tmp_path, capsys):
    path = tmp_path / "packet.json"
    path.write_text("{invalid", encoding="utf-8")
    assert C.main(["--packet", str(path), "--root", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["runtime_status"] == "unknown"


def test_explicit_null_prior_receipt_cannot_silently_become_first_run(packet, tmp_path, capsys):
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    prior = tmp_path / "prior.json"
    prior.write_text("null", encoding="utf-8")
    assert C.main(["--packet", str(path), "--root", str(tmp_path), "--prior-receipt", str(prior)]) == 1
    assert json.loads(capsys.readouterr().out)["context_status"] == "unknown"
