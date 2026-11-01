"""Portable frozen-input consistency tests; no native body or output authority override."""
import ast
import builtins
import copy
import importlib.util
import io
import json
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import unittest
from unittest.mock import patch

B = Path(__file__).resolve().parents[2] / "scripts"
spec = importlib.util.spec_from_file_location("one_body_candidate", B / "beta_v2_one_body_trace.py")
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)


def raw(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def fixture(root=None):
    root = root or Path("C:/synthetic-private")
    text = "SYNTHETIC BODY SECRET\n  evidence Ω\n"
    source = T.sha(re.sub(r"\s+", " ", text).strip().encode())[:20]
    body = {"sha": source, "page_kind": "article", "text": text, "chars": len(text),
            "published_utc": None, "first_seen_utc": "2026-10-25T13:58:40Z",
            "title": "SECRET TITLE MUST NOT APPEAR"}
    generation = {"schema": "reader_pool_generation/1", "status": "NATIVE_SELF", "pid": 123,
                  "generation_id": "a" * 64, "reader_source_sha256": "b" * 64}
    witness = {"status": "ACTUAL_BODY_FILE_READ_BACK", "item_id": "c" * 64,
               "source_id": source, "path": "C:/declared-native/not-read.json",
               "file_sha256": T.sha(raw(body)), "body_sha256": T.sha(text.encode()),
               "body_chars": len(text), "duplicate": False}
    status = {"t": "2026-10-25T13:59:16Z", "pid": 123, "generation": generation,
              "carry_lineage": {"schema": "native_pool_carry_lineage/2", "generation": generation,
                                "observed_utc": "2026-10-25T13:59:16.100000Z",
                                "body_history_truncated": False, "body_evidence_total": 1,
                                "body_evidence": [witness]}}
    manifest = {"schema": T.SCHEMA, "body": {"copy_path": str(root / "copy.json"),
                "native_path": witness["path"], "sha256": T.sha(raw(body)), "bytes": len(raw(body))},
                "status": {"path": str(root / "status.json"), "sha256": T.sha(raw(status)), "bytes": len(raw(status))},
                "generation_id": "a" * 64, "reader_source_sha256": "b" * 64, "pool_pid": 123,
                "item_id": "c" * 64, "source_id": source, "text_sha256": T.sha(text.encode()),
                "text_chars": len(text), "published_utc": None, "first_seen_utc": body["first_seen_utc"],
                "witness_observed_utc": status["t"], "claim_pointer": None}
    return manifest, body, status


def pack(m, b, s):
    # Honest file pins after synthetic metadata mutations; semantic guards still apply.
    braw, sraw = raw(b), raw(s)
    m["body"].update(sha256=T.sha(braw), bytes=len(braw))
    m["status"].update(sha256=T.sha(sraw), bytes=len(sraw))
    mraw = raw(m)
    return (mraw, braw, sraw), T.sha(mraw)


def check(m, b, s):
    bundle, pin = pack(m, b, s)
    return T.validate_bundle(*bundle, manifest_sha256=pin)


def claim(m):
    return {"path": "C:/NEVER_READ/claim.jsonl", "offset": 100, "length": 80,
            "row_sha256": "d" * 64, "article_sha": m["source_id"],
            "declared_prefix_sha256": "e" * 64, "prefix_end": 1024**3}


class PureTests(unittest.TestCase):
    def test_copy_consistency_has_unknown_edges_and_no_completion_or_body(self):
        m, b, s = fixture()
        result = check(m, b, s)
        self.assertNotEqual(m["source_id"], m["text_sha256"][:20])
        self.assertEqual(result["copy"]["text_sha256"], m["text_sha256"])
        self.assertEqual(result["body_to_claim"], {"status": "ROW_LOCATOR_REQUIRED", "edge": "UNKNOWN", "pointer": None})
        self.assertIsNone(result["actual_consumed_ids"])
        self.assertIsNone(result["metadata"]["storage_completion_utc"])
        self.assertEqual(result["witness"]["observed_utc"], "2026-10-25T13:59:16+00:00")
        encoded = json.dumps(result)
        for secret in (b["text"], b["title"], "TYPED_BOUND", "CONSUMED", "VERIFIED_PREFIX_BYTES"):
            self.assertNotIn(secret, encoded)

    def test_pointer_prefix_stays_declared_and_no_effects_even_when_it_exists(self):
        m, b, s = fixture()
        m["claim_pointer"] = claim(m)
        args, pin = pack(m, b, s)
        calls = []

        def forbidden(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("forbidden effect")

        try:
            with patch.object(builtins, "open", forbidden), patch.object(io, "open", forbidden), \
                    patch.object(Path, "open", forbidden), patch.object(builtins, "__import__", forbidden), \
                    patch.object(socket, "socket", forbidden), patch.object(sqlite3, "connect", forbidden), \
                    patch.object(subprocess, "Popen", forbidden):
                result = T.validate_bundle(*args, manifest_sha256=pin)
        finally:
            self.assertEqual(calls, [])  # Observable outside validator exception handling.
        pointer = result["body_to_claim"]["pointer"]
        self.assertEqual(pointer["status"], "DECLARED_NOT_READ")
        self.assertEqual(pointer["prefix_hash_status"], "DECLARED_UPSTREAM_REFERENCE")
        self.assertEqual(pointer["bytes_read"], 0)
        self.assertIsNone(result["actual_consumed_ids"])

    def test_missing_manifest_fields_and_wrong_strict_types_refuse(self):
        for field in fixture()[0]:
            with self.subTest(missing=field):
                m, b, s = fixture()
                del m[field]
                with self.assertRaises(T.TraceRefused):
                    # Do not pack after deleting a descriptor.
                    T.validate_bundle(raw(m), raw(b), raw(s), manifest_sha256=T.sha(raw(m)))
        for field, value in (("text_chars", True), ("pool_pid", "123"), ("item_id", []),
                             ("source_id", None), ("claim_pointer", False), ("schema", 1)):
            with self.subTest(field=field, value=value):
                m, b, s = fixture()
                m[field] = value
                with self.assertRaises(T.TraceRefused):
                    check(m, b, s)

    def test_malformed_deep_duplicate_nonfinite_and_nonobject_json(self):
        bad = [b'{a:1}', b'{"a":1,}', b'{/*x*/"a":1}', b'{"x":1,"x":2}', b'[]',
               b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e9999}', b'\xff', b'{',
               b'{"x":' + b'[' * 70 + b'0' + b']' * 70 + b'}',
               b'{"x":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}']
        for value in bad:
            with self.subTest(size=len(value), prefix=value[:20]):
                with self.assertRaises(T.TraceRefused):
                    T.document(value, T.OBJECT_CAP)
        for value in (None, "{}", [], b""):
            with self.assertRaises(T.TraceRefused):
                T.parse_manifest(value, "a" * 64)

    def test_pins_counts_caps_and_invalid_utf8_text_refuse(self):
        m, b, s = fixture()
        args, pin = pack(m, b, s)
        for index in (0, 1, 2):
            changed = list(args)
            changed[index] += b" "
            with self.assertRaises(T.TraceRefused):
                T.validate_bundle(*changed, manifest_sha256=pin)
        for cap in (T.BODY_CAP, T.OBJECT_CAP):
            with self.assertRaises(T.TraceRefused):
                T.document(b" " * (cap + 1), cap)
        for field, value in (("chars", True), ("chars", len(b["text"]) + 1), ("text", "\ud800")):
            m, b, s = fixture()
            b[field] = value
            with self.assertRaises(T.TraceRefused):
                # ensure_ascii allows an isolated surrogate in the JSON bytes.
                br = json.dumps(b).encode()
                m["body"].update(bytes=len(br), sha256=T.sha(br))
                T.validate_bundle(raw(m), br, raw(s), manifest_sha256=T.sha(raw(m)))

    def test_body_kind_missing_metadata_and_clock_mismatches(self):
        for field, value in (("page_kind", "front"), ("page_kind", "stock_text"),
                             ("sha", "f" * 20), ("first_seen_utc", "2026-10-25T13:58:40"),
                             ("published_utc", True), ("first_seen_utc", "2026-10-25T12:00:00Z")):
            with self.subTest(field=field, value=value):
                m, b, s = fixture()
                b[field] = value
                with self.assertRaises(T.TraceRefused):
                    check(m, b, s)
        for name in ("sha", "chars", "text", "page_kind", "published_utc", "first_seen_utc"):
            m, b, s = fixture()
            del b[name]
            with self.assertRaises(T.TraceRefused):
                check(m, b, s)

    def test_generation_source_pid_and_lineage_mismatch(self):
        for name, value in (("generation_id", "f" * 64), ("reader_source_sha256", "f" * 64),
                             ("status", "NATIVE_QUERY_UNAVAILABLE"), ("pid", True), ("schema", None)):
            m, b, s = fixture()
            s["generation"][name] = value
            with self.assertRaises(T.TraceRefused):
                check(m, b, s)
        for name, value in (("pid", "123"), ("t", "2026-10-25T14:00:00Z"), ("generation", None)):
            m, b, s = fixture()
            s[name] = value
            with self.assertRaises(T.TraceRefused):
                check(m, b, s)
        m, b, s = fixture()
        s["carry_lineage"]["generation"] = {"generation_id": "f" * 64}
        with self.assertRaises(T.TraceRefused):
            check(m, b, s)

    def test_missing_duplicate_conflicting_truncated_and_typed_witnesses(self):
        for field, value in (("duplicate", True), ("duplicate", 0), ("duplicate", "false"),
                             ("body_chars", True), ("body_chars", 0), ("item_id", "f" * 64),
                             ("source_id", "f" * 20), ("path", "C:/other.json"),
                             ("file_sha256", "f" * 64), ("body_sha256", "f" * 64),
                             ("status", "BODY_PERSISTENCE_UNPROVED")):
            with self.subTest(field=field, value=value):
                m, b, s = fixture()
                s["carry_lineage"]["body_evidence"][0][field] = value
                with self.assertRaises(T.TraceRefused):
                    check(m, b, s)
        for mode in ("missing", "duplicate", "conflict", "truncated", "boolcount", "arraytype"):
            m, b, s = fixture()
            line = s["carry_lineage"]
            if mode == "missing":
                line.update(body_evidence=[], body_evidence_total=0)
            elif mode in ("duplicate", "conflict"):
                extra = copy.deepcopy(line["body_evidence"][0])
                if mode == "conflict":
                    extra["file_sha256"] = "f" * 64
                line["body_evidence"].append(extra)
                line["body_evidence_total"] = 2
            elif mode == "truncated":
                line["body_history_truncated"] = True
            elif mode == "boolcount":
                line["body_evidence_total"] = True
            else:
                line["body_evidence"] = {}
            with self.subTest(mode=mode), self.assertRaises(T.TraceRefused):
                check(m, b, s)

    def test_pointer_types_binding_and_prefix_refusal(self):
        for name, value in (("path", "relative.jsonl"), ("offset", True), ("length", 0),
                             ("length", 256 * 1024 + 1), ("row_sha256", "invalid"),
                             ("article_sha", "f" * 20), ("prefix_end", 10), ("prefix_end", "10000")):
            m, b, s = fixture()
            m["claim_pointer"] = claim(m)
            m["claim_pointer"][name] = value
            with self.subTest(name=name), self.assertRaises(T.TraceRefused):
                check(m, b, s)
        m, b, s = fixture()
        m["body"]["copy_path"] = m["body"]["native_path"]
        with self.assertRaises(T.TraceRefused):
            check(m, b, s)

    def test_import_surface_is_stdlib_only_no_dynamic_execution(self):
        tree = ast.parse((B / "beta_v2_one_body_trace.py").read_bytes())
        allowed = {"__future__", "argparse", "hashlib", "json", "ntpath", "os", "pathlib", "re", "stat", "sys", "datetime"}
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"exec", "eval", "compile", "__import__"})
        self.assertLessEqual(imports, allowed)


def missing_input_contract_case():
    """Scripts guard adapter: direct shared contract, no service exemption."""
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("forbidden missing-input effect")

    def missing():
        try:
            with patch.object(builtins, "open", forbidden), patch.object(io, "open", forbidden), \
                    patch.object(Path, "open", forbidden), patch.object(Path, "mkdir", forbidden), \
                    patch.object(socket, "socket", forbidden), patch.object(sqlite3, "connect", forbidden), \
                    patch.object(subprocess, "Popen", forbidden):
                T.validate_bundle(b"{}", b"{}", b"{}", manifest_sha256=T.sha(b"{}"))
        finally:
            assert calls == []  # Outside collector/helper exception handling.

    return missing, T.TraceRefused, "body audit without declared manifest/body/witness inputs"


class PortableEffects(unittest.TestCase):
    def test_missing_input_uses_existing_shared_guard_contract(self):
        from backend.tests.guard_contract import assert_refuses_missing_input
        call, exc, what = missing_input_contract_case()
        assert_refuses_missing_input(call, exc=exc, what=what)

    def test_default_and_outside_root_refuse_without_content_or_writer_effects(self):
        calls = []

        def forbidden(*args, **kwargs):
            calls.append(True)
            raise AssertionError("refusal performed file content/writer effect")

        # Never replace PRIVATE_ROOT, Path.resolve or the scope predicate.
        # On unsupported hosts a missing fixed root refuses; on the approved
        # host its parent is outside the fixed allowlist and must also refuse.
        outside = str(T.PRIVATE_ROOT.parent)
        manifest = str(B / "DO_NOT_READ_absent_manifest.json")
        output = str(B / "DO_NOT_CREATE_audit_output")
        try:
            with patch.object(T, "read_once", forbidden), patch.object(Path, "open", forbidden), \
                    patch.object(Path, "mkdir", forbidden):
                with self.assertRaises(T.TraceRefused):
                    T.audit_to_private(manifest, "a" * 64, output, private_root=outside)
                with io.StringIO() as out, patch.object(T.sys, "stdout", out):
                    code = T.main(["--manifest", manifest, "--manifest-sha256", "a" * 64,
                                   "--output-dir", output])
                    result = json.loads(out.getvalue())
                    self.assertEqual(code, 2)
                    self.assertEqual(result["status"], "REFUSED")
                    self.assertRegex(result["code"], r"^[a-z0-9_]+$")
        finally:
            self.assertEqual(calls, [])

    def test_cli_projection_argument_refusal_and_external_error_redaction(self):
        with io.StringIO() as out, patch.object(T.sys, "stdout", out):
            self.assertEqual(T.main(["--UNKNOWN_SECRET"]), 2)
            self.assertEqual(json.loads(out.getvalue()), {"status": "REFUSED", "code": "invalid_arguments"})
        # This tests CLI projection only, not filesystem authority/admission.
        with io.StringIO() as out, patch.object(T.sys, "stdout", out), \
                patch.object(T, "audit_to_private", return_value={"status": "COPIED_BODY_FILE_CONSISTENT", "report_sha256": "a" * 64}) as boundary:
            args = ["--manifest", "DECLARED_INPUT", "--manifest-sha256", "PIN", "--output-dir", "NEW_PRIVATE_OUTPUT"]
            self.assertEqual(T.main(args), 0)
            boundary.assert_called_once_with("DECLARED_INPUT", "PIN", "NEW_PRIVATE_OUTPUT")
            self.assertEqual(json.loads(out.getvalue())["report_sha256"], "a" * 64)
        with io.StringIO() as out, patch.object(T.sys, "stdout", out), \
                patch.object(T, "audit_to_private", side_effect=OSError("SECRET URL TITLE BODY TOKEN")):
            self.assertEqual(T.main(args), 2)
            self.assertEqual(json.loads(out.getvalue()), {"status": "REFUSED", "code": "internal_error"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
