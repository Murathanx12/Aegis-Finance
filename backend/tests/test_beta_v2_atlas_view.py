"""Pure bounded fixtures; no world-state, inference, DB or execution imports."""
import unittest
from pathlib import Path

from scripts.beta_v2_atlas_view import Projection, query

NOW = "2026-10-24T18:00:00+00:00"
PAST = "2026-10-23T12:00:00+00:00"
FUTURE = "2026-10-25T12:00:00+00:00"
ROOT = Path(__file__).resolve().parents[2]


def document(kind: str, value: object, name: str = "sample.json") -> dict:
    return {"kind": kind, "value": value, "ref": {"path": str(ROOT / name),
            "sha256": "a" * 64, "read_at": PAST, "bytes": 100}}


def event(observation: str = "sighting", root: str = "root") -> dict:
    return {"observation_hash": observation, "canonical_hash": root,
            "url": "https://example.test/source", "tickers": ["ABC"],
            "ingested_at": PAST, "source_at": "2026-10-01T00:00:00+00:00"}


def beliefs() -> dict:
    return {"schema": "world_state/v2", "as_of": PAST, "beliefs": {
        "a": {"last_updated": PAST, "evidence_ids": ["root:r", "root:r"],
              "confidence": 0.9, "co_mention_edges": [{"to": "b", "sign": "+", "support": 20}],
              "contradictions": [{"at": PAST, "prior_direction": "up", "evidence_ids": ["root:r"]}]},
        "b": {"last_updated": PAST}}}


def project(*docs: dict) -> dict:
    return Projection(list(docs), NOW, ROOT).build()


class AtlasTests(unittest.TestCase):
    def test_future_ingestion_excluded_even_with_old_publisher_clock(self):
        row = event()
        row["ingested_at"] = FUTURE
        view = project(document("event", row))
        self.assertEqual(view["nodes"], [])
        self.assertEqual(view["excluded"][0]["reason"], "FUTURE_AVAILABILITY")

    def test_publisher_clock_cannot_replace_missing_ingestion(self):
        row = event()
        del row["ingested_at"]
        view = project(document("event", row))
        self.assertEqual(view["excluded"][0]["reason"], "UNKNOWN_AVAILABILITY")

    def test_native_event_store_field_mapping_without_entity_type_guess(self):
        row = {"observation_hash": "o", "canonical_hash": "r", "ingested_at": PAST,
               "source_url": "https://publisher.test/news", "source_timestamp": "2026-10-01",
               "entities": ["macro:oil"]}
        view = project(document("event", row))
        self.assertIn("economic:source:https://publisher.test/news", {n["id"] for n in view["nodes"]})
        self.assertFalse(any(n["kind"] == "company" for n in view["nodes"]))
        self.assertEqual(view["nodes"][0]["facts"][0]["clocks"]["source_at"], "2026-10-01")
        self.assertTrue(any(g["reason"] == "ENTITY_COMPANY_TYPE_NOT_ESTABLISHED" for g in view["unresolved"]))

    def test_future_snapshot_not_reconstructed_from_old_first_seen(self):
        b = beliefs()
        b["as_of"] = FUTURE
        b["beliefs"]["a"]["first_seen"] = PAST
        self.assertEqual(project(document("beliefs", b))["nodes"], [])

    def test_future_belief_update_excluded(self):
        b = beliefs()
        b["beliefs"]["a"]["last_updated"] = FUTURE
        view = project(document("beliefs", b))
        self.assertNotIn("economic:belief:a", {n["id"] for n in view["nodes"]})

    def test_future_effective_and_expired_are_distinct(self):
        for field, stamp, reason in (("effective_at", FUTURE, "NOT_YET_EFFECTIVE"),
                                     ("expires_at", PAST, "EXPIRED")):
            row = event()
            row[field] = stamp
            self.assertEqual(project(document("event", row))["excluded"][0]["reason"], reason)

    def test_clock_fields_remain_separate(self):
        row = event()
        row.update(effective_at=PAST, expires_at=FUTURE)
        times = project(document("event", row))["nodes"][0]["facts"][0]["clocks"]
        self.assertEqual(times, {"available_at": PAST, "source_at": row["source_at"],
                                 "effective_at": PAST, "expires_at": FUTURE})

    def test_comention_never_upgraded_to_causality(self):
        view = project(document("beliefs", beliefs()))
        edges = [e for e in view["edges"] if e["relation"] == "co_mention"]
        self.assertEqual(len(edges), 1)
        self.assertIsNone(edges[0]["polarity"])
        self.assertFalse(any("causal" in e["relation"] for e in view["edges"]))

    def test_scenario_chain_is_label_hypothesis_not_causal_edge(self):
        doc = {"schema": "macro_scenarios/v2", "as_of": PAST,
               "scenarios": [{"scenario_id": "s", "causal_chain": "a -> ABC", "leading_indicators": []}]}
        view = project(document("scenarios", doc))
        self.assertEqual(view["edges"], [])
        self.assertEqual(view["nodes"][0]["facts"][0]["data"]["causal_chain_type"], "DECLARED_HYPOTHESIS_LABEL_ONLY")

    def test_namespaces_cannot_collide(self):
        row = event()
        row["tickers"] = ["C06"]
        registry = {"schema_version": 1, "tasks": [{"id": "C06", "evidence": []}]}
        view = project(document("event", row), document("registry", registry, "registry.json"))
        ids = {n["id"] for n in view["nodes"]}
        self.assertIn("economic:company:C06", ids)
        self.assertIn("operational:task:C06", ids)

    def test_scenario_row_clocks_cannot_hide_behind_old_snapshot(self):
        for field, stamp, reason in (
            ("last_updated", FUTURE, "FUTURE_AVAILABILITY"),
            ("effective_at", FUTURE, "NOT_YET_EFFECTIVE"),
            ("expires_at", PAST, "EXPIRED"),
            ("last_updated", "not-a-clock", "INVALID_OR_UNZONED_CLOCK"),
            ("last_updated", None, "UNKNOWN_AVAILABILITY"),
        ):
            with self.subTest(field=field, stamp=stamp):
                doc = {"schema": "macro_scenarios/v2", "as_of": PAST,
                       "scenarios": [{"scenario_id": "s", field: stamp}]}
                view = project(document("scenarios", doc))
                self.assertEqual(view["nodes"], [])
                self.assertEqual(view["excluded"][0]["reason"], reason)

    def test_scenario_row_clocks_preserved_on_node_and_indicator(self):
        stamp = "2026-10-24T12:00:00+00:00"
        doc = {"schema": "macro_scenarios/v2", "as_of": PAST, "scenarios": [{
            "scenario_id": "s", "last_updated": stamp, "effective_at": stamp,
            "expires_at": FUTURE, "leading_indicators": [{"topic": "a"}]}]}
        view = project(document("beliefs", beliefs()), document("scenarios", doc))
        expected = {"available_at": stamp, "effective_at": stamp, "expires_at": FUTURE, "source_at": None}
        node = next(n for n in view["nodes"] if n["kind"] == "scenario")
        edge = next(e for e in view["edges"] if e["relation"] == "scenario_indicator_hypothesis")
        self.assertEqual(node["facts"][0]["clocks"], expected)
        self.assertEqual(edge["facts"][0]["clocks"], expected)

    def test_contradiction_uses_its_own_eligibility_clocks(self):
        doc = beliefs()
        stamp = "2026-10-24T12:00:00+00:00"
        doc["beliefs"]["a"]["contradictions"][0].update(at=stamp, effective_at=stamp, expires_at=FUTURE)
        view = project(document("beliefs", doc))
        edge = next(e for e in view["edges"] if e["relation"] == "contradicts_prior_belief")
        self.assertEqual(edge["facts"][0]["clocks"], {
            "available_at": stamp, "effective_at": stamp, "expires_at": FUTURE, "source_at": None})

    def test_prerequisite_evidence_does_not_prove_requested_task(self):
        proof = {"path": "proof.json", "sha256": "a" * 64, "verified_at": PAST}
        doc = {"schema_version": 1, "tasks": [
            {"id": "C00", "evidence": [proof]},
            {"id": "C06", "dependencies": ["C00"], "evidence": []}]}
        view = project(document("registry", doc), document("receipt", None, "proof.json"))
        result = query(view, "operational:task:C06", "evidence")
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertEqual(result["paths"], [])
        self.assertEqual(len(result["dependency_paths"]), 1)
        self.assertEqual(result["dependency_evidence_status"], "REACHABLE_PREREQUISITE_EVIDENCE_ONLY")
        self.assertTrue(any(g["reason"] == "NO_REGISTERED_EVIDENCE" for g in result["unresolved"]))
        doc["tasks"][1]["evidence"] = [proof]
        direct = query(project(document("registry", doc), document("receipt", None, "proof.json")),
                       "operational:task:C06", "evidence")
        self.assertEqual(direct["status"], "MATCHED")
        self.assertEqual(len(direct["paths"]), 1)
        self.assertEqual(len(direct["paths"][0]), 1)
        self.assertEqual(len(direct["dependency_paths"]), 1)

    def test_duplicate_root_keeps_one_event_and_two_sightings(self):
        docs = [document("event", event("one"), "one.json"),
                document("event", event("two"), "two.json")]
        docs[1]["ref"]["sha256"] = "b" * 64
        view = project(*docs)
        self.assertEqual(sum(n["kind"] == "event" for n in view["nodes"]), 1)
        self.assertEqual(sum(n["kind"] == "observation" for n in view["nodes"]), 2)

    def test_duplicate_input_is_not_double_applied(self):
        doc = document("beliefs", beliefs())
        one, two = project(doc), project(doc, doc)
        self.assertEqual(one["nodes"], two["nodes"])
        self.assertEqual(one["edges"], two["edges"])

    def test_duplicate_reference_roots_are_single_nodes(self):
        view = project(document("beliefs", beliefs()))
        self.assertEqual(sum(n["kind"] == "evidence_ref" for n in view["nodes"]), 1)
        self.assertTrue(any(g["reason"] == "UNDERLYING_SOURCE_RECORD_NOT_SUPPLIED" for g in view["unresolved"]))
        self.assertFalse(any(n["kind"] == "source" for n in view["nodes"]))

    def test_missing_referenced_topic_is_unresolved_not_fake_node(self):
        doc = beliefs()
        del doc["beliefs"]["b"]
        view = project(document("beliefs", doc))
        self.assertFalse(any(n["id"] == "economic:belief:b" for n in view["nodes"]))
        self.assertTrue(any(g["reason"] == "MISSING_REFERENCED_NODE" for g in view["unresolved"]))

    def test_registry_missing_evidence_not_fabricated(self):
        doc = {"schema_version": 1, "tasks": [{"id": "C06", "evidence": [
            {"path": "missing.json", "sha256": "b" * 64, "verified_at": PAST}]}]}
        view = project(document("registry", doc))
        result = query(view, "operational:task:C06", "evidence")
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertEqual(result["unresolved"][0]["reason"], "EVIDENCE_NOT_SUPPLIED_OR_HASH_MISMATCH")

    def test_registry_exact_receipt_link(self):
        doc = {"schema_version": 1, "tasks": [{"id": "C06", "evidence": [
            {"path": "proof.json", "sha256": "a" * 64, "verified_at": PAST}]}]}
        view = project(document("registry", doc), document("receipt", None, "proof.json"))
        self.assertEqual(query(view, "operational:task:C06", "evidence")["status"], "MATCHED")

    def test_registry_hash_mismatch_is_unresolved(self):
        doc = {"schema_version": 1, "tasks": [{"id": "C06", "evidence": [
            {"path": "proof.json", "sha256": "b" * 64, "verified_at": PAST}]}]}
        view = project(document("registry", doc), document("receipt", None, "proof.json"))
        self.assertFalse(any(e["relation"] == "registered_evidence" for e in view["edges"]))

    def test_reliability_exposure_and_weight_never_blend(self):
        row = {"decision_id": "d", "built_utc": PAST, "ticker": "ABC", "evidence_reliability": 0.7,
               "economic_exposure": 0.2, "target_weight": 0.05}
        view = project(document("decisions", {"rows": [row]}))
        facts = next(n for n in view["nodes"] if n["kind"] == "decision")["facts"][0]["data"]
        self.assertEqual((facts["evidence_reliability"], facts["economic_exposure"], facts["portfolio_weight"]),
                         (0.7, 0.2, {"target_weight": 0.05}))

    def test_position_budget_is_not_a_holding_weight(self):
        row = {"decision_id": "d", "built_utc": PAST, "ticker": "ABC", "position_budget": {"dollars": 100}}
        view = project(document("decisions", {"rows": [row]}))
        facts = next(n for n in view["nodes"] if n["kind"] == "decision")["facts"][0]["data"]
        self.assertIsNone(facts["portfolio_weight"])
        self.assertEqual(facts["position_budget"], {"dollars": 100})

    def test_explicit_contrary_filter_does_not_use_comention_sign(self):
        view = project(document("beliefs", beliefs()))
        start = "economic:evidence_ref:root:r"
        contrary = query(view, start, "belief", polarity="contrary")
        supportive = query(view, start, "belief", polarity="supportive")
        self.assertEqual(contrary["status"], "MATCHED")
        self.assertTrue(all(p[0]["polarity"] == "contrary" for p in contrary["paths"]))
        self.assertEqual(supportive["status"], "UNRESOLVED")

    def test_query_cannot_backdate_current_snapshot(self):
        view = project(document("beliefs", beliefs()))
        with self.assertRaisesRegex(ValueError, "EXACT_VIEW_ASOF"):
            query(view, "economic:belief:a", "belief", as_of=PAST)

    def test_supportive_filter_requires_an_explicit_reference(self):
        row = {"decision_id": "d", "built_utc": PAST, "ticker": "ABC", "supportive_evidence_ids": ["root:r"]}
        view = project(document("beliefs", beliefs()), document("decisions", {"rows": [row]}, "decision.json"))
        result = query(view, "economic:evidence_ref:root:r", "decision", polarity="supportive")
        self.assertEqual(result["status"], "MATCHED")
        self.assertTrue(all(p[0]["polarity"] == "supportive" for p in result["paths"]))

    def test_shared_company_not_thesis_decision_lineage(self):
        thesis = {"card_hash": "t", "run_utc": PAST, "ticker": "ABC", "sources": ["url:source"]}
        decision = {"decision_id": "d", "built_utc": PAST, "ticker": "ABC"}
        view = project(document("thesis", thesis), document("decisions", {"rows": [decision]}, "d.json"))
        self.assertFalse(any(e["relation"] == "explicit_thesis_ref" for e in view["edges"]))
        self.assertEqual(query(view, "economic:source:url:source", "decision")["status"], "MATCHED")
        self.assertEqual(query(view, "economic:thesis:t", "decision")["status"], "UNRESOLVED")

    def test_registry_planning_date_cannot_backdate_availability(self):
        doc = document("registry", {"schema_version": 1, "as_of": "2000-01-01", "tasks": [{"id": "C06"}]})
        doc["ref"]["read_at"] = FUTURE
        self.assertEqual(project(doc)["nodes"], [])


if __name__ == "__main__":
    unittest.main()
