"""Portable copied bytes only: no private data, filesystem admission or native lookup."""
import builtins
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2] / "scripts" / "beta_v2_local_claim_copy.py"
spec = importlib.util.spec_from_file_location("local_claim_copy", SOURCE)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def raw(value):
    return json.dumps(value, ensure_ascii=True).encode()


def fixture(newline=b"\n", missing=False):
    # Same c91 TRACE field placement; every identifier/clock/path is synthetic.
    binding = dict(source_id="1" * 20, item_id="2" * 64, generation_id="3" * 64,
                   reader_source_sha256="4" * 64, pool_pid=123, text_sha256="5" * 64)
    clock = "2001-01-02T03:04:05Z"
    trace = {
        "schema": "one_body_trace/1", "status": "COPIED_BODY_FILE_CONSISTENT", "manifest_sha256": "6" * 64,
        **{k: v for k, v in binding.items() if k != "text_sha256"},
        "copy": dict(path="X:/synthetic/body.json", sha256="7" * 64, bytes=200,
                     full_file_hash_status="VERIFIED_COPY_BYTES", text_sha256=binding["text_sha256"],
                     text_chars=10, page_kind="article", duplicate=False),
        "native": dict(path="X:/declared-native/body.json", status="DECLARED_NOT_READ", bytes_read=0),
        "witness": dict(path="X:/synthetic/status.json", sha256="8" * 64, bytes=300,
                        observed_utc=clock, carry_observed_utc=clock, binding="SUPPLIED_FROZEN_STATUS_CONSISTENCY_ONLY"),
        "metadata": dict(declared_published_utc=None, declared_first_seen_utc=clock, storage_completion_utc=None),
        "body_to_claim": dict(status="ROW_LOCATOR_REQUIRED", edge="UNKNOWN", pointer=None),
        "actual_consumed_ids": None,
        "downstream": dict.fromkeys(("typed", "event", "forecast", "position"), "UNKNOWN"),
        "qualification": "FILE_CONSISTENCY_NOT_NATIVE_AUTHENTICITY_QUALITY_OR_FULLTEXT",
        "io": dict(distinct_inputs=3, input_bytes=900, integrity_reread_bytes=900,
                   claim_native_or_downstream_bytes_read=0),
    }
    row = dict(source_id="synthetic_column", article_sha=binding["source_id"],
               url="https://example.invalid/SYNTHETIC_PRIVATE_URL", first_seen_utc=clock,
               published_utc=None, pit_grade="first_seen_only", ticker="XYZ", direction="none",
               horizon_days_stated=63, magnitude_bucket="unstated", quote="SYNTHETIC_QUOTE",
               paraphrase="SYNTHETIC_PARAPHRASE")
    rr = raw(row) + newline
    manifest = dict(schema=M.SCHEMA, body_binding=binding,
                    trace=dict(copy_path="X:/synthetic/TRACE.json", sha256=M.sha(raw(trace)), bytes=len(raw(trace))),
                    claim_copy=None if missing else dict(copy_path="X:/synthetic/row.jsonl", sha256=M.sha(rr), bytes=len(rr)),
                    claim_pointer=None if missing else dict(path="X:/declared-native/claims.jsonl", offset=100,
                          length=len(rr), row_sha256=M.sha(rr), article_sha=binding["source_id"],
                          declared_prefix_sha256="9" * 64, prefix_end=2**62))
    return trace, manifest, row, None if missing else rr


def pack(trace, manifest, row_bytes):
    m = deepcopy(manifest)
    tr = raw(trace)
    m["trace"].update(sha256=M.sha(tr), bytes=len(tr))
    if row_bytes is not None:
        m["claim_copy"].update(sha256=M.sha(row_bytes), bytes=len(row_bytes))
        m["claim_pointer"].update(row_sha256=M.sha(row_bytes), length=len(row_bytes))
    mr = raw(m)
    return tr, mr, row_bytes


def check(trace, manifest, row_bytes):
    tr, mr, rr = pack(trace, manifest, row_bytes)
    return M.verify_local_claim_copy(tr, mr, rr, manifest_sha256=M.sha(mr))


class LocalClaimCopyTests(unittest.TestCase):
    def test_lf_crlf_and_nested_hash_profile_remain_copy_identity_only(self):
        for newline in (b"\n", b"\r\n"):
            with self.subTest(newline=newline):
                t, m, _, rr = fixture(newline)
                self.assertNotIn("text_sha256", t)
                result = check(t, m, rr)
                self.assertEqual(result["status"], "LOCAL_CLAIM_COPY_BODY_ID_MATCH_ONLY")
                self.assertIsNone(result["actual_consumed_ids"])
                self.assertEqual(set(result["downstream"].values()), {"UNKNOWN"})
                self.assertEqual(result["column_binding"], "UNKNOWN")
                self.assertEqual(result["semantic_grounding"], "UNKNOWN")
                self.assertEqual(result["native_pointer"]["prefix_hash_status"], "DECLARED_UPSTREAM_REFERENCE")
                self.assertEqual(result["native_pointer"]["row_hash_status"], "DECLARED_NOT_READ")
                rendered = json.dumps(result)
                for secret in ("SYNTHETIC_QUOTE", "SYNTHETIC_PARAPHRASE", "SYNTHETIC_PRIVATE_URL", "XYZ"):
                    self.assertNotIn(secret, rendered)

    def test_missing_pointer_is_unknown_not_absence(self):
        t, m, _, rr = fixture(missing=True)
        result = check(t, m, rr)
        self.assertEqual(result["status"], "ROW_LOCATOR_REQUIRED")
        self.assertEqual(result["body_to_claim_edge"], "UNKNOWN")
        self.assertIsNone(result["actual_consumed_ids"])

    def test_body_identity_domains_metadata_and_strict_types_even_after_honest_repin(self):
        for field, value in (("article_sha", "f" * 20), ("article_sha", "5" * 64),
                             ("article_sha", True), ("horizon_days_stated", True),
                             ("horizon_days_stated", None), ("quote", ""),
                             ("first_seen_utc", "2001-01-02T04:04:05Z"), ("direction", [])):
            with self.subTest(field=field, value_type=type(value).__name__):
                t, m, r, _ = fixture()
                r[field] = value
                with self.assertRaises(M.ClaimCopyRefused):
                    check(t, m, raw(r) + b"\n")

    def test_nested_sha_only_and_actual_profile_top_binding(self):
        for name in ("text_sha256", "source_id", "item_id", "generation_id", "reader_source_sha256", "pool_pid"):
            with self.subTest(field=name):
                t, m, _, rr = fixture()
                if name == "text_sha256":
                    t[name] = m["body_binding"][name]  # Fake top field cannot repair wrong nested hash.
                    t["copy"][name] = "f" * 64
                else:
                    t[name] = True if name == "pool_pid" else "f" * len(t[name])
                with self.assertRaises(M.ClaimCopyRefused):
                    check(t, m, rr)

    def test_clock_normalization_and_column_label_are_not_article_identity(self):
        t, m, r, _ = fixture()
        r.update(source_id="a_different_column", first_seen_utc="2001-01-02T05:04:05+02:00")
        self.assertEqual(check(t, m, raw(r) + b"\n")["column_binding"], "UNKNOWN")

    def test_malformed_lines_json_recursion_and_utf8_are_controlled_refusals(self):
        for label, corrupt in (
            ("truncated", b"{}"), ("multiple", b"{}\n{}\n"), ("duplicate", b'{"a":1,"a":2}\n'),
            ("nonfinite", b'{"a":1e999}\n'), ("utf8", b'\xff\n'), ("array", b'[]\n'),
            ("surrogate", b'{"\\ud800":1}\n'),
            ("recursion", b'{"a":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}\n'),
        ):
            with self.subTest(case=label):
                t, m, _, _ = fixture()
                with self.assertRaises(M.ClaimCopyRefused):
                    check(t, m, corrupt)

    def test_caps_and_digest_mismatch(self):
        t, m, _, rr = fixture()
        tr, mr, rr = pack(t, m, rr)
        for name, trace_raw, manifest_raw, row_raw, pin in (
            ("trace", b"x" * (M.OBJECT_CAP + 1), mr, rr, M.sha(mr)),
            ("manifest", tr, b"x" * (M.OBJECT_CAP + 1), rr, "0" * 64),
            ("row", tr, mr, b"x" * (M.ROW_CAP + 1), M.sha(mr)),
            ("pin", tr, mr, rr, "0" * 64),
        ):
            with self.subTest(case=name), self.assertRaises(M.ClaimCopyRefused):
                M.verify_local_claim_copy(trace_raw, manifest_raw, row_raw, manifest_sha256=pin)

    def test_nonbool_duplicate_and_trace_completion_or_consumption_claims_refuse(self):
        for field, value in (("duplicate", 0), ("duplicate", "false"), ("text_chars", True)):
            with self.subTest(field=field, value_type=type(value).__name__):
                t, m, _, rr = fixture()
                t["copy"][field] = value
                with self.assertRaises(M.ClaimCopyRefused):
                    check(t, m, rr)
        t, m, _, rr = fixture()
        t["actual_consumed_ids"] = []
        with self.assertRaises(M.ClaimCopyRefused):
            check(t, m, rr)

    def test_direct_shared_missing_input_guard_with_outside_effect_assertion(self):
        from backend.tests.guard_contract import assert_refuses_missing_input
        calls = []
        def forbidden(*args, **kwargs):
            calls.append("forbidden_effect")
            raise AssertionError("missing input attempted I/O")
        with patch.object(builtins, "open", forbidden), patch.object(io, "open", forbidden), \
                patch.object(os, "open", forbidden), patch.object(Path, "open", forbidden), \
                patch.object(Path, "resolve", forbidden), patch.object(Path, "mkdir", forbidden), \
                patch.object(socket, "create_connection", forbidden), patch.object(sqlite3, "connect", forbidden), \
                patch.object(subprocess, "Popen", forbidden):
            try:
                assert_refuses_missing_input(
                    lambda: M.verify_local_claim_copy(b"", b"", manifest_sha256="0" * 64),
                    exc=M.ClaimCopyRefused, what="no declared copied TRACE/manifest/row inputs")
            finally:
                self.assertEqual(calls, [])  # Outside shared helper and collector.

    def test_wrapper_missing_contract_refuses_before_any_path_io_without_root_patching(self):
        calls = []
        def forbidden(*args, **kwargs):
            calls.append("path_effect")
            raise AssertionError("preflight attempted I/O")
        with patch.object(Path, "resolve", forbidden), patch.object(Path, "open", forbidden), \
                patch.object(Path, "mkdir", forbidden):
            try:
                with self.assertRaises(M.ClaimCopyRefused):
                    M.audit_to_private(None, "0" * 64, None)
            finally:
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
