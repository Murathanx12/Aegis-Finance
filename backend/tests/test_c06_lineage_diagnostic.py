"""Focused refusal tests using synthetic saved views; no producer imports."""
import copy
import hashlib
import io
import json
import unittest
from unittest.mock import patch

from scripts import c06_lineage_diagnostic as diagnostic

from scripts.c06_lineage_diagnostic import probe

AS_OF = "2026-10-24T17:38:41.445928+00:00"
PAST = "2026-10-23T12:00:00+00:00"
SOURCE = "economic:source:https://example.test/a"
DECISION = "economic:decision:d"
THESIS = "economic:thesis:t"
COMPANY = "economic:company:ABC"


def fixture():
    fact = {"data": {}, "clocks": {"available_at": PAST, "source_at": None,
            "effective_at": None, "expires_at": None},
            "ref": {"path": "never-open-this.json", "sha256": "a" * 64,
                    "read_at": AS_OF, "locator": "/rows/0"}}
    nodes = [{"id": ident, "kind": kind, "facts": [copy.deepcopy(fact)]}
             for ident, kind in [(SOURCE, "source"), (COMPANY, "company"),
                                 (THESIS, "thesis"), (DECISION, "decision")]]
    edges = [{"from": src, "to": dst, "relation": relation, "facts": [copy.deepcopy(fact)]}
             for src, dst, relation in [(SOURCE, COMPANY, "cited_for_company"),
                                       (COMPANY, THESIS, "subject_of"),
                                       (COMPANY, DECISION, "subject_of")]]
    return {"schema": "beta_v2_atlas_view/1", "as_of": AS_OF, "nodes": nodes,
            "edges": edges, "source_refs": [fact["ref"]], "excluded": [],
            "unresolved": [{"owner": DECISION,
                            "reason": "MISSING_THESIS_ID_NO_LINEAGE_INFERRED"}]}


def run(view, **kwargs):
    raw = json.dumps(view).encode()
    result = probe(raw, expected_sha256=hashlib.sha256(raw).hexdigest(),
                 as_of=kwargs.get("as_of", AS_OF), source=SOURCE, decision=DECISION)
    assert result["status"] == "REFUSED"
    assert result["lineage_proven"] is False
    assert result["paths"] == []
    return result


class LineageDiagnosticTests(unittest.TestCase):
    def test_shared_ticker_never_proves_lineage(self):
        result = run(fixture())
        self.assertEqual(result["reason"], "MISSING_NATIVE_THESIS_ID")
        self.assertFalse(result["lineage_proven"])
        self.assertEqual(result["paths"], [])

    def test_exact_refs_and_clocks_preserved(self):
        view = fixture()
        result = run(view)
        self.assertEqual(result["source_refs"], view["source_refs"])
        self.assertEqual(result["saved_as_of"], AS_OF)
        self.assertEqual(view, fixture())

    def test_missing_unresolved_record_does_not_guess_id(self):
        view = fixture()
        view["unresolved"] = []
        self.assertEqual(run(view)["reason"], "NATIVE_THESIS_DECISION_LINK_NOT_AVAILABLE")

    def test_even_explicit_edge_cannot_qualify_missing_producer_contract(self):
        view = fixture()
        view["edges"].append({"from": THESIS, "to": DECISION,
                              "relation": "explicit_thesis_ref",
                              "facts": copy.deepcopy(view["nodes"][0]["facts"])})
        self.assertEqual(run(view)["reason"], "NATIVE_PRODUCER_CONTRACT_NOT_QUALIFIED")

    def test_future_or_ambiguous_identity_refuses(self):
        for change, reason in [("future", "FUTURE_AVAILABILITY"),
                               ("duplicate", "AMBIGUOUS_NATIVE_IDENTITY"),
                               ("facts", "AMBIGUOUS_NATIVE_IDENTITY")]:
            with self.subTest(change=change):
                view = fixture()
                if change == "future":
                    view["nodes"][2]["facts"][0]["clocks"]["available_at"] = "2099-01-01T00:00:00Z"
                elif change == "duplicate":
                    view["nodes"].append(copy.deepcopy(view["nodes"][2]))
                else:
                    view["nodes"][2]["facts"] *= 2
                self.assertEqual(run(view)["reason"], reason)

    def test_missing_unzoned_effective_expired_clocks(self):
        for field, value, reason in [
            ("available_at", None, "UNKNOWN_AVAILABILITY"),
            ("available_at", "2026-10-23T12:00:00", "INVALID_OR_UNZONED_CLOCK"),
            ("effective_at", "2099-01-01T00:00:00Z", "NOT_YET_EFFECTIVE"),
            ("expires_at", PAST, "EXPIRED"),
        ]:
            with self.subTest(field=field, value=value):
                view = fixture()
                view["nodes"][2]["facts"][0]["clocks"][field] = value
                self.assertEqual(run(view)["reason"], reason)

    def test_clock_spelling_must_match_saved_exactly(self):
        self.assertEqual(run(fixture(), as_of=AS_OF.replace("+00:00", "Z"))["reason"],
                         "EXACT_SAVED_ASOF_REQUIRED")

    def test_wrong_hash_refuses_before_parse(self):
        result = probe(b"bad json", expected_sha256="0" * 64,
                       as_of=AS_OF, source=SOURCE, decision=DECISION)
        self.assertEqual(result["reason"], "SAVED_VIEW_HASH_MISMATCH")

    def test_strict_json(self):
        for raw, reason in [(b'{"a":1,"a":2}', "DUPLICATE_JSON_KEY"),
                            (b'{"a":NaN}', "NONFINITE_JSON"),
                            (b'{"a":1e9999}', "NONFINITE_JSON"),
                            (b'{}', "MALFORMED_SAVED_VIEW"),
                            (b'[' * 10000 + b'0' + b']' * 10000, "MALFORMED_SAVED_VIEW")]:
            with self.subTest(raw=raw):
                result = probe(raw, expected_sha256=hashlib.sha256(raw).hexdigest(),
                               as_of=AS_OF, source=SOURCE, decision=DECISION)
                self.assertEqual(result["reason"], reason)

    def test_absent_endpoint(self):
        view = fixture()
        view["nodes"].pop()
        self.assertEqual(run(view)["reason"], "NATIVE_ENDPOINT_NOT_AVAILABLE")

    def test_cli_refuses_and_does_not_open_embedded_refs(self):
        raw = json.dumps(fixture()).encode()
        argv = ["probe", "--view", "saved.json", "--expected-sha256",
                hashlib.sha256(raw).hexdigest(), "--as-of", AS_OF,
                "--source", SOURCE, "--decision", DECISION]
        output = io.StringIO()
        with patch("sys.argv", argv), patch("sys.stdout", output), patch.object(
                diagnostic.Path, "open", return_value=io.BytesIO(raw)) as opened:
            self.assertEqual(diagnostic.main(), 2)
        self.assertEqual(opened.call_count, 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "REFUSED")
        self.assertFalse(result["lineage_proven"])
        self.assertEqual(result["paths"], [])

    def test_library_probe_opens_no_files(self):
        with patch.object(diagnostic.Path, "open", side_effect=AssertionError("file read")):
            result = run(fixture())
        self.assertEqual(result["status"], "REFUSED")
        self.assertEqual(result["endpoint_facts"][DECISION], fixture()["nodes"][3]["facts"])

    def test_nested_endpoint_payload_refuses_before_retaining_for_cli(self):
        view = fixture()
        value = 0
        for _ in range(80):
            value = [value]
        view["nodes"][0]["facts"][0]["data"] = value
        result = run(view)
        self.assertEqual(result["status"], "REFUSED")
        self.assertEqual(result["reason"], "VIEW_NESTING_LIMIT")
        self.assertNotIn("endpoint_facts", result)
        json.dumps(result, indent=2)
