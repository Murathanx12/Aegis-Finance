"""Read-only fake-data replay through the real daily-pass decision caller.

Run directly with python -B -I; no pytest, conftest, database or runtime input.
An audit hook rejects file mutations, runtime reads, SQL, network and processes
before project imports. Caller dependencies are real, with unsafe seams trapped.
"""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
os.environ["AEGIS_IGNORE_DOTENV"] = "1"
os.environ["AEGIS_REPO_ROOT"] = str(ROOT)
FORBIDDEN = []


def read_only_guard(event, args):
    forbidden = (event.startswith(("socket.", "sqlite3.", "subprocess."))
                 or event in {"os.system", "os.mkdir", "os.remove", "os.rename",
                              "os.rmdir", "os.truncate", "os.chmod", "os.link",
                              "os.symlink", "os.startfile", "os.spawn"})
    if event == "open":
        path, mode, flags = args
        parts = str(path).lower().replace("/", "\\").split("\\")
        forbidden = (any(letter in str(mode) for letter in "wax+")
                     or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
                     or ("aegis-finance" in parts and ".venv" not in parts))
    if forbidden:
        FORBIDDEN.append(event)
        raise AssertionError(f"read-only replay rejected {event}")


sys.addaudithook(read_only_guard)
from backend.services import decision_contract as DC
from scripts import daily_pass as DP


def fixture():
    return {
        "event_id": "FAKE-earnings-event", "ticker": "FAKE",
        "asof": "2030-01-02T01:00:00Z", "deadline": "2030-01-02T01:00:00Z",
        "event_time": "2030-01-02T20:00:00Z", "horizon": "next three trading sessions",
        "horizon_end": "2030-01-07T21:00:00Z",
        "mandate": {"policy_id": "FAKE-existing-mandate", "policy_version": "frozen-1",
                    "objective": "existing owner utility", "new_orders": False},
        "exposure_kind": "fully_paid_long",
        "required_evidence": ["analyst_report", "price_usd"],
        "available_evidence": [{"evidence_id": "price_usd", "value": 100,
                                "source": "FAKE timestamped quote snapshot", "source_sha256": "a" * 64,
                                "available_at": "2030-01-02T00:55:00Z",
                                "observed_at": "2030-01-02T00:56:00Z",
                                "valid_until": "2030-01-02T02:00:00Z", "quality": "AVAILABLE"},
                               {"evidence_id": "shares", "value": 10, "source": "FAKE holding snapshot", "source_sha256": "b" * 64,
                                "available_at": "2030-01-02T00:55:00Z",
                                "observed_at": "2030-01-02T00:56:00Z", "quality": "AVAILABLE"},
                               {"evidence_id": "equity_usd", "value": 10000, "source": "FAKE account snapshot", "source_sha256": "c" * 64,
                                "available_at": "2030-01-02T00:55:00Z",
                                "observed_at": "2030-01-02T00:56:00Z", "quality": "AVAILABLE"}],
        "conditional_loss_fractions": [0.02, 0.10],
    }


def call(request=None, history=None):
    # These traps establish that we traversed the REAL caller and composition
    # while bypassing its live dependencies, not a copied implementation.
    with patch.object(DC, "_capital_from_broker", side_effect=AssertionError("broker read")), \
         patch.object(DC, "funnel_state", side_effect=AssertionError("funnel read")), \
         patch.object(DC, "agency_options", side_effect=AssertionError("agency read")), \
         patch.object(DC, "write_contracts", side_effect=AssertionError("contract write")), \
         patch.object(DC, "latest", side_effect=AssertionError("live file read")), \
         patch.object(DP, "record_decided", side_effect=AssertionError("ledger write")):
        return DP.step_decision_contract({"offline": True,
                                          "provisional_request": request or fixture(),
                                          "prior_records": history or []})


class Regressions(unittest.TestCase):
    def tearDown(self):
        self.assertEqual(FORBIDDEN, [], "forbidden side effect attempted")

    def test_missing_report_produces_rendered_hold_at_deadline(self):
        result = call()
        row = result["contracts"][-1]
        self.assertEqual(row["action"], "NO_NEW_BET")
        self.assertEqual(row["missing_evidence"], ["analyst_report"])
        self.assertEqual(row["deadline_status"], "DUE")
        self.assertEqual(row["delivery_status"], {"status": "NOT_ATTEMPTED", "receipt": None})
        self.assertFalse(result["runtime_requirement_fulfilled"])
        self.assertIsNone(result["receipt"])
        for text in ("NO_NEW_BET FAKE", "analyst_report", "Invalidation:", "Update:", "NOT_CALIBRATED"):
            self.assertIn(text, result["answer"])
        for key in ("asof", "horizon", "conditional_risk", "probability_type", "action",
                    "rationale", "invalidating_evidence", "update_trigger", "delivery_status"):
            self.assertIn(key, row)
        self.assertEqual(row["artifact_sha256"], DC.seal(row))

    def test_missing_price_never_becomes_zero_nav_or_zero_risk(self):
        req = fixture()
        req["available_evidence"] = []
        row = call(req)["contracts"][-1]
        self.assertIn("price_usd", row["missing_evidence"])
        risk = row["conditional_risk"]
        self.assertIsNone(risk["position_value_usd"])
        self.assertIsNone(risk["maximum_position_loss_usd"])
        self.assertEqual(risk["maximum_loss_per_unit_exposure"], 1.0)
        self.assertEqual(risk["scenarios"][1]["loss_per_unit_exposure"], 0.10)

    def test_unknown_shares_and_equity_keep_conditional_unit_risk(self):
        req = fixture()
        req["available_evidence"] = [e for e in req["available_evidence"] if e["evidence_id"] == "price_usd"]
        row = call(req)["contracts"][-1]
        self.assertEqual(row["action"], "NO_NEW_BET")
        self.assertIsNone(row["conditional_risk"]["portfolio_loss_fraction"])
        self.assertIsNone(row["conditional_risk"]["position_value_usd"])
        self.assertEqual(row["conditional_risk"]["maximum_loss_per_unit_exposure"], 1)

    def test_unknown_equity_with_known_holding_does_not_invent_nav(self):
        req = fixture()
        req["available_evidence"] = [e for e in req["available_evidence"] if e["evidence_id"] != "equity_usd"]
        risk = call(req)["contracts"][-1]["conditional_risk"]
        self.assertEqual(risk["position_value_usd"], 1000)
        self.assertIsNone(risk["portfolio_loss_fraction"])

    def test_duplicate_event_and_evidence_reordering_are_idempotent(self):
        first = call()["contracts"]
        req = fixture()
        req["available_evidence"] *= 2
        req["asof"] = "2030-01-02T01:05:00Z"
        repeated = call(req, first)
        self.assertEqual(repeated["new_records"], 0)
        self.assertEqual(repeated["contracts"], first)

    def test_post_event_evidence_adds_child_and_preserves_prior_pit(self):
        req = fixture()
        first = call(req)["contracts"]
        frozen = copy.deepcopy(first)
        req["asof"] = "2030-01-02T21:00:00Z"
        req["available_evidence"].append({"evidence_id": "analyst_report", "source": "FAKE report v2",
                                          "summary": "new primary evidence after event",
                                          "available_at": "2030-01-02T20:30:00Z",
                                          "observed_at": "2030-01-02T20:45:00Z", "quality": "AVAILABLE"})
        updated = call(req, first)["contracts"]
        self.assertEqual(len(updated), 2)
        self.assertEqual(first, frozen)
        self.assertEqual(updated[0], frozen[0])
        self.assertEqual(updated[1]["parent_decision_id"], updated[0]["decision_id"])
        self.assertEqual(updated[1]["original_pit"], updated[0]["original_pit"])
        self.assertEqual(updated[1]["mandate"], req["mandate"])
        self.assertNotEqual(updated[1]["decision_id"], updated[0]["decision_id"])

    def test_future_or_ambiguous_evidence_cannot_enter_original_pit(self):
        for stamp in ("2030-01-03T00:00:00Z", "2030-01-02", None):
            req = fixture()
            req["available_evidence"][0]["observed_at"] = stamp
            row = call(req)["contracts"][-1]
            self.assertNotIn("price_usd", [e["evidence_id"] for e in row["available_evidence"]])
            self.assertIn("price_usd", row["missing_evidence"])
            self.assertTrue(row["unusable_evidence"])

    def test_missing_or_ambiguous_event_time_is_visible(self):
        for stamp in (None, "2030-01-02"):
            req = fixture()
            req["event_time"] = stamp
            row = call(req)["contracts"][-1]
            self.assertIsNone(row["event_time"])
            self.assertTrue(any("event_time" in w for w in row["data_quality_warnings"]))

    def test_stale_or_contradictory_evidence_excluded_and_rendered(self):
        for quality in ("STALE", "CONTRADICTORY"):
            req = fixture()
            req["available_evidence"][0]["quality"] = quality
            result = call(req)
            self.assertIsNone(result["contracts"][-1]["price_usd"])
            self.assertIn(quality, result["answer"])
        req = fixture()
        req["asof"] = "2030-01-02T02:01:00Z"
        self.assertIn("stale:", call(req)["contracts"][-1]["unusable_evidence"][0]["reason"])

    def test_failed_delivery_is_update_without_fake_receipt(self):
        first = call()["contracts"]
        req = fixture()
        req["delivery_status"] = {"status": "FAILED", "detail": "FAKE channel unavailable"}
        result = call(req, first)
        row = result["contracts"][-1]
        self.assertEqual(len(result["contracts"]), 2)
        self.assertEqual(row["delivery_status"]["status"], "FAILED")
        self.assertIsNone(row["delivery_status"]["receipt"])
        self.assertEqual(row["original_pit"], first[0]["original_pit"])
        self.assertIn("FAILED", result["answer"])

    def test_conflicting_duplicate_evidence_produces_visible_assessment(self):
        req = fixture()
        other = copy.deepcopy(req["available_evidence"][0])
        other["value"] = 125
        req["available_evidence"].append(other)
        result = call(req)
        self.assertIn("CONTRADICTORY", result["answer"])
        self.assertIsNone(result["contracts"][-1]["conditional_risk"]["position_value_usd"])
        req["available_evidence"].reverse()
        self.assertEqual(call(req, result["contracts"])["new_records"], 0)

    def test_portfolio_snapshot_exposure_supports_signed_hypothetical_shocks(self):
        req = fixture()
        req["available_evidence"] = [req["available_evidence"][-1], {
            "evidence_id": "exposure_usd", "value": 1000, "quality": "AVAILABLE",
            "source": "FAKE aggregate holdings", "source_sha256": "d" * 64, "available_at": "2030-01-02T00:55:00Z",
            "observed_at": "2030-01-02T00:56:00Z"}]
        req["required_evidence"] = ["analyst_report"]
        req["conditional_return_fractions"] = [-0.1, -0.05, 0.05, 0.1]
        result = call(req)
        row = result["contracts"][-1]
        self.assertEqual(row["action"], "NO_NEW_BET")
        self.assertEqual(row["missing_evidence"], ["analyst_report"])
        self.assertIsNone(row["price_usd"])
        self.assertIsNone(row["shares"])
        self.assertEqual([s["pnl_usd"] for s in row["conditional_risk"]["hypothetical_shocks"]],
                         [-100, -50, 50, 100])
        self.assertIn("assumptions, no odds", result["answer"])

    def test_conflicting_exposure_and_bad_shocks_do_not_make_false_dollar_risk(self):
        req = fixture()
        exposure = copy.deepcopy(req["available_evidence"][0])
        exposure.update(evidence_id="exposure_usd", value=2000)
        req["available_evidence"].append(exposure)
        self.assertIsNone(call(req)["contracts"][-1]["conditional_risk"]["position_value_usd"])
        for shock in (True, float("nan"), -1.1):
            req["conditional_return_fractions"] = [shock]
            with self.assertRaises(ValueError):
                call(req)

    def test_no_directional_edge_does_not_force_order_even_when_report_available(self):
        req = fixture()
        req["required_evidence"] = ["price_usd"]
        row = call(req)["contracts"][-1]
        self.assertEqual(row["missing_evidence"], [])
        self.assertEqual(row["action"], "NO_NEW_BET")
        self.assertFalse(row["orders_authorized"])
        self.assertIsNone(row["estimated_probability"])
        self.assertEqual(row["probability_type"], "NOT_CALIBRATED")
        self.assertIn("No new event bet", row["rationale"])

    def test_unreconciled_mandate_does_not_become_holding_advice(self):
        req = fixture()
        req["mandate"]["status"] = "UNRECONCILED"
        result = call(req)
        self.assertEqual(result["contracts"][-1]["investment_action"], "UNRESOLVED")
        self.assertIn("No automated position change", result["answer"])
        self.assertNotIn("Maintain the declared mandate", result["answer"])

    def test_typed_horizon_expiry_appends_review_state_and_preserves_history(self):
        req = fixture()
        old = call(req)["contracts"]
        req["asof"] = req["horizon_end"]
        new = call(req, old)["contracts"]
        self.assertEqual(new[0], old[0])
        self.assertEqual(len(new), 2)
        self.assertEqual(new[-1]["horizon_status"], "EXPIRED")
        self.assertIn("expired", " ".join(new[-1]["data_quality_warnings"]))
        req["horizon_end"] = "2030-01-08T21:00:00Z"
        with self.assertRaises(ValueError):
            call(req, new)

    def test_unknown_horizon_is_visible_not_inferred_from_prose(self):
        req = fixture()
        req.pop("horizon_end")
        row = call(req)["contracts"][-1]
        self.assertEqual(row["horizon_status"], "UNKNOWN")
        self.assertEqual(row["investment_action"], "UNRESOLVED")

    def test_unversioned_evidence_is_not_usable(self):
        req = fixture()
        req["available_evidence"][0].pop("source_sha256")
        row = call(req)["contracts"][-1]
        self.assertIsNone(row["price_usd"])
        self.assertIn("immutable source/version", " ".join(row["data_quality_warnings"]))

    def test_finite_inputs_cannot_seal_infinite_products_or_ratios(self):
        req = fixture()
        req["available_evidence"][0]["value"] = 1e307
        req["conditional_return_fractions"] = [10.0]
        with self.assertRaisesRegex(ValueError, "not finite"):
            call(req)
        req = fixture()
        req["available_evidence"][-1]["value"] = 1e-310
        with self.assertRaisesRegex(ValueError, "not finite"):
            call(req)

    def test_render_does_not_acknowledge_delivery(self):
        rows = call()["contracts"]
        recorded = []
        answer = DC.summarise_for_reader({"rows": rows}, record=recorded.append)
        self.assertEqual(recorded, [])
        self.assertIn("delivery unconfirmed", answer)

    def test_invalid_prices_and_quantities_remain_unknown(self):
        for value in (0, -1, float("nan"), float("inf"), True, "bad"):
            req = fixture()
            req["available_evidence"][0]["value"] = value
            self.assertIsNone(call(req)["contracts"][-1]["price_usd"])

    def test_input_and_prior_record_mutation_are_rejected(self):
        original = fixture()
        before = copy.deepcopy(original)
        first = call(original)["contracts"]
        self.assertEqual(original, before)
        for key, value in (("mandate", {"policy_id": "other"}), ("horizon", "other"),
                           ("deadline", "2030-01-02T02:00:00Z"),
                           ("asof", "2030-01-02T00:59:00Z")):
            req = fixture()
            req[key] = value
            with self.assertRaises(ValueError):
                call(req, first)
        first[0]["action"] = "BUY"
        with self.assertRaisesRegex(ValueError, "seal mismatch"):
            call(fixture(), first)

    def test_offline_guard_rejects_writes_and_live_caller_mode(self):
        with self.assertRaisesRegex(ValueError, "write=False"):
            DC.build_daily_contracts(provisional_request=fixture())
        with self.assertRaisesRegex(ValueError, "offline=True"):
            DP.step_decision_contract({"provisional_request": fixture()})
        with self.assertRaises(ValueError):
            DC.build_daily_contracts(write=False, prior_records=[])

    def test_reject_false_delivery_and_undeclared_instrument(self):
        for updates in ({"delivery_status": {"status": "DELIVERED"}},
                        {"delivery_status": {"status": "FAILED", "receipt": "invented"}},
                        {"exposure_kind": "leveraged"},
                        {"conditional_loss_fractions": [float("nan")]},
                        {"conditional_loss_fractions": [1.01]},
                        {"asof": "2030-01-02"}):
            req = fixture()
            req.update(updates)
            with self.assertRaises(ValueError):
                call(req)

    def test_crossing_deadline_adds_due_record_without_rewriting_early_record(self):
        req = fixture()
        req["asof"] = "2030-01-02T00:59:00Z"
        early = call(req)["contracts"]
        self.assertEqual(early[0]["deadline_status"], "BEFORE_DEADLINE")
        due = call(fixture(), early)["contracts"]
        self.assertEqual(len(due), 2)
        self.assertEqual(due[1]["deadline_status"], "DUE")
        self.assertEqual(due[1]["original_pit"], due[0]["original_pit"])

    def test_late_holding_and_equity_cannot_change_pit_exposure(self):
        req = fixture()
        for e in req["available_evidence"]:
            if e["evidence_id"] in ("shares", "equity_usd"):
                e["observed_at"] = "2030-01-03T00:00:00Z"
        req["shares"] = 999  # Unversioned fields must not override PIT evidence.
        req["equity_usd"] = 1
        row = call(req)["contracts"][-1]
        self.assertEqual(row["action"], "NO_NEW_BET")
        self.assertIsNone(row["conditional_risk"]["position_value_usd"])
        self.assertIsNone(row["conditional_risk"]["portfolio_loss_fraction"])

    def test_default_daily_pass_path_keeps_existing_builder_and_ledger_flow(self):
        from datetime import date
        with patch.object(DP, "build_decision_contracts", return_value=[]) as build, \
             patch.object(DP, "record_decided", return_value={}) as ledger, \
             patch.object(DC, "latest", return_value={}):
            result = DP.step_decision_contract({"date_obj": date(2030, 1, 2), "date": "2030-01-02"})
        build.assert_called_once_with(asof=date(2030, 1, 2))
        ledger.assert_called_once_with([], "2030-01-02")
        self.assertEqual(result["status"], "nothing_to_do")
        self.assertNotIn("mode", result)


if __name__ == "__main__":
    sample = "--sample" in sys.argv
    if sample:
        sys.argv.remove("--sample")
    result = unittest.main(verbosity=2, exit=False).result
    if sample and result.wasSuccessful():
        print(json.dumps({"fixture_only": True, "result": call(),
                          "forbidden_side_effect_attempts": FORBIDDEN}, indent=2))
    sys.exit(0 if result.wasSuccessful() else 1)
