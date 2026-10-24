"""Pure census fixtures; no runtime, grading, execution or provider imports."""
import unittest
from copy import deepcopy

from scripts.beta_v2_population_census import (
    cohort_census, digest, exact_join, policy_census, strict_json,
)


def book(ident="a", asof="2026-10-15"):
    return {"schema": "llm_portfolio/1", "asof": asof, "book_id": ident,
            "frozen_utc": "2026-10-15T14:40:58+00:00",
            "horizon_days": [63],
            "source": {"type": "prospective_population1000", "manifest_sha256": "manifest",
                       "historical_nav_inherited": False, "policy_id": "p" + ident}}


def grade(ident="a"):
    return {"book_id": ident, "asof": "2026-10-15", "status": "OK", "entry_session": "2026-10-16",
            "grade_rule_version": 2, "benchmark_missing": False, "weight_in_market": 0.95,
            "to_date": {"status": "OK", "as_of": "2026-10-23", "gross": 0.0, "net": 0.0,
                        "nav_usd": 1000000.0, "benchmark_return": 0.0, "vs_benchmark": 0.0,
                        "weight_priced": 1.0, "sessions": 6},
            "horizons": {"63": {"status": "PENDING", "why": "needs 63 sessions, has 6"}}}


def census(books=None, grades=None):
    if grades is not None:
        grades = deepcopy(grades)
        grades.setdefault("closed_session", "2026-10-23")
        grades.setdefault("observed_at", "2026-10-24T16:15:00+00:00")
    return cohort_census(books or [book()], asof="2026-10-15", expected_count=1,
                         manifest_sha="manifest", grade_doc=grades)


class CensusTests(unittest.TestCase):
    def test_dropped_id_is_explicit(self):
        value = exact_join(["a", "b"], [{"book_id": "a"}])
        self.assertEqual(value["status"], "REFUSED")
        self.assertEqual(value["missing_ids"], ["b"])

    def test_equal_count_duplicate_cannot_hide_dropped_id(self):
        value = exact_join(["a", "b"], [{"book_id": "a"}, {"book_id": "a"}])
        self.assertEqual(value["duplicate_ids"], {"a": 2})
        self.assertEqual(value["missing_ids"], ["b"])
        self.assertEqual(value["status"], "REFUSED")

    def test_same_count_wrong_cohort_ids(self):
        value = exact_join(["a"], [{"book_id": "foreign"}])
        self.assertEqual(value["missing_ids"], ["a"])
        self.assertEqual(value["extra_ids"], ["foreign"])

    def test_wrong_cohort_date_refuses(self):
        with self.assertRaisesRegex(ValueError, "WRONG_COHORT"):
            census([book(asof="2026-10-14")])

    def test_wrong_manifest_refuses(self):
        row = book()
        row["source"]["manifest_sha256"] = "other"
        with self.assertRaisesRegex(ValueError, "WRONG_POPULATION_MANIFEST"):
            census([row])

    def test_duplicate_frozen_rows_refuse(self):
        with self.assertRaises(ValueError):
            cohort_census([book(), book()], asof="2026-10-15", expected_count=2)

    def test_dropped_frozen_row_refuses(self):
        with self.assertRaisesRegex(ValueError, "COHORT_COUNT_MISMATCH"):
            cohort_census([book()], asof="2026-10-15", expected_count=2)

    def test_missing_grades_are_unknown_not_zero(self):
        self.assertIsNone(census()["marked"])

    def test_dropped_grade_is_unknown_with_gap(self):
        value = census(grades={"grades": []})
        self.assertIsNone(value["marked"])
        self.assertEqual(value["grade_join"]["missing_ids"], ["a"])

    def test_duplicate_grade_refuses_aggregate(self):
        value = census(grades={"grades": [grade(), grade()]})
        self.assertIsNone(value["marked"])
        self.assertEqual(value["grade_join"]["status"], "REFUSED")

    def test_wrong_grade_cohort_refuses(self):
        row = grade()
        row["asof"] = "2026-10-14"
        with self.assertRaisesRegex(ValueError, "WRONG_GRADE_COHORT"):
            census(grades={"grades": [row]})

    def test_real_zero_net_is_mark_not_missing(self):
        value = census(grades={"grades": [grade()]})
        self.assertEqual((value["entered"], value["marked"], value["matured_books"]), (1, 1, 0))

    def test_ok_label_without_numbers_is_not_a_mark(self):
        row = grade()
        del row["to_date"]["nav_usd"]
        self.assertIsNone(census(grades={"grades": [row]})["marked"])

    def test_false_and_nan_are_not_prices(self):
        for invalid in (False, float("nan")):
            row = grade()
            row["to_date"]["net"] = invalid
            self.assertIsNone(census(grades={"grades": [row]})["marked"])

    def test_missing_horizons_are_unknown_not_zero_maturities(self):
        row = grade()
        del row["horizons"]
        self.assertIsNone(census(grades={"grades": [row]})["matured_books"])

    def test_refused_horizon_does_not_become_zero_maturities(self):
        row = grade()
        row["horizons"]["63"]["status"] = "REFUSED"
        self.assertIsNone(census(grades={"grades": [row]})["matured_books"])

    def test_missing_entry_on_ok_grade_is_unknown(self):
        row = grade()
        del row["entry_session"]
        self.assertIsNone(census(grades={"grades": [row]})["entered"])

    def test_policy_wait_cannot_be_dropped(self):
        specs = {"specifications": [{"policy_id": "pa", "control_role": "treatment"},
                                    {"policy_id": "pb", "control_role": "treatment"}]}
        operation = {"states": {"pa": "OK"}, "grades": [grade()]}
        with self.assertRaisesRegex(ValueError, "COHORT_ID_JOIN_REFUSED"):
            policy_census(specs, [book()], operation)

    def test_policy_wait_is_distinct_from_zero_mark(self):
        specs = {"specifications": [{"policy_id": "pa", "control_role": "treatment"},
                                    {"policy_id": "pb", "control_role": "treatment"}]}
        operation = {"states": {"pa": "OK", "pb": "WAIT_INPUT"}, "grades": [grade()]}
        value = policy_census(specs, [book()], operation)
        self.assertEqual(value["unfrozen"], 1)
        self.assertEqual(value["wait_counts"], {"WAIT_INPUT": 1})

    def test_frozen_policy_cannot_belong_to_other_spec(self):
        with self.assertRaisesRegex(ValueError, "FOREIGN_POLICY"):
            policy_census({"specifications": [{"policy_id": "foreign"}]}, [book()], {})

    def test_duplicate_policy_refuses(self):
        rows = [book("a"), book("b")]
        rows[1]["source"]["policy_id"] = "pa"
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_FOREIGN_POLICY"):
            policy_census({"specifications": [{"policy_id": "pa"}]}, rows, {})

    def test_pin_is_on_ids_not_only_count(self):
        with self.assertRaisesRegex(ValueError, "COHORT_ID_PIN_MISMATCH"):
            cohort_census([book()], asof="2026-10-15", expected_count=1,
                          expected_ids_sha=digest(["different"]))

    def test_duplicate_json_state_key_refuses(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            strict_json('{"states":{"a":"OK","a":"WAIT_INPUT"}}')

    def test_nonfinite_json_refuses(self):
        with self.assertRaisesRegex(ValueError, "NONFINITE_JSON"):
            strict_json('{"net":NaN}')

    def test_overflowing_json_numbers_refuse_at_any_depth(self):
        for raw in ('{"net":1e9999}', '{"nested":[{"gross":-1e9999}]}', '[1e309]'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "NONFINITE_JSON"):
                strict_json(raw)

    def test_finite_exponents_and_zero_are_preserved(self):
        self.assertEqual(strict_json('{"small":1e-20,"zero":0.0}'), {"small": 1e-20, "zero": 0.0})

    def test_malformed_clock_counterexample_refuses_entry_and_mark(self):
        row = grade()
        row["entry_session"] = "not-a-date"
        row["to_date"].update(as_of="yesterday", sessions=-10)
        value = census(grades={"grades": [row]})
        self.assertIsNone(value["entered"])
        self.assertIsNone(value["marked"])
        self.assertTrue(value["rows"][0]["validation_errors"])

    def test_entry_after_mark_cannot_count(self):
        row = grade()
        row["entry_session"] = "2026-10-26"
        value = census(grades={"grades": [row]})
        self.assertIsNone(value["entered"])
        self.assertIsNone(value["marked"])

    def test_entry_on_frozen_day_cannot_count(self):
        row = grade()
        row["entry_session"] = "2026-10-15"
        self.assertIsNone(census(grades={"grades": [row]})["entered"])

    def test_future_mark_relative_to_data_bound_is_not_rescued_by_generation_time(self):
        row = grade()
        row["to_date"]["as_of"] = "2026-10-24"
        value = census(grades={"grades": [row], "observed_at": "2026-10-30T00:00:00Z"})
        self.assertIsNone(value["marked"])
        self.assertEqual(value["data_upper_bound"], "2026-10-23")

    def test_invalid_mark_date_and_timestamp_in_date_field_refuse(self):
        for label in ("2026-02-30", "2026-10-23T00:00:00Z", "20261023", None):
            row = grade()
            row["to_date"]["as_of"] = label
            with self.subTest(label=label):
                self.assertIsNone(census(grades={"grades": [row]})["marked"])

    def test_missing_negative_fractional_boolean_and_zero_sessions_refuse(self):
        for count in (None, -10, 0, 1.5, 6.0, True, "6"):
            row = grade()
            row["to_date"]["sessions"] = count
            with self.subTest(count=count):
                self.assertIsNone(census(grades={"grades": [row]})["marked"])

    def test_impossible_session_count_refuses_without_calendar_invention(self):
        row = grade()
        row["to_date"]["sessions"] = 100
        self.assertIsNone(census(grades={"grades": [row]})["marked"])

    def test_invalid_freeze_and_receipt_clocks_refuse(self):
        frozen = book()
        frozen["frozen_utc"] = "2026-10-15T14:40:58"
        self.assertIsNone(census([frozen], {"grades": [grade()]})["marked"])
        self.assertIsNone(census(grades={"grades": [grade()], "closed_session": "yesterday"})["marked"])
        self.assertIsNone(census(grades={"grades": [grade()], "observed_at": "2026-10-24"})["marked"])

    def test_missing_upper_data_clock_is_unknown(self):
        value = cohort_census([book()], asof="2026-10-15", expected_count=1,
                              grade_doc={"grades": [grade()], "observed_at": "2026-10-24T00:00:00Z"})
        self.assertIsNone(value["marked"])

    def test_each_additional_data_clock_also_bounds_mark(self):
        self.assertIsNone(census(grades={"grades": [grade()], "bars_through": "2026-10-22"})["marked"])

    def test_missing_two_declared_horizons_are_unknown_not_zero(self):
        frozen = book()
        frozen["horizon_days"] = [21, 63, 126]
        row = grade()
        row["horizons"] = {"21": {"status": "PENDING", "why": "needs 21 sessions, has 6"}}
        value = census([frozen], {"grades": [row]})
        self.assertIsNone(value["matured_books"])
        self.assertEqual(value["unknown_horizon_count"], 1)

    def test_foreign_substituted_horizon_cannot_complete(self):
        row = grade()
        row["horizons"] = {"21": {"status": "PENDING", "why": "needs 21"}}
        self.assertIsNone(census(grades={"grades": [row]})["matured_books"])

    def test_unexpected_horizon_cannot_complete(self):
        row = grade()
        row["horizons"]["126"] = {"status": "PENDING", "why": "needs 126"}
        self.assertIsNone(census(grades={"grades": [row]})["matured_books"])

    def test_premature_126_ok_label_cannot_mature(self):
        frozen = book()
        frozen["horizon_days"] = [126]
        row = grade()
        row["horizons"] = {"126": {"status": "OK"}}
        self.assertIsNone(census([frozen], {"grades": [row]})["matured_books"])

    def test_supported_mature_horizon_fixture(self):
        frozen, row = book(), grade()
        frozen["horizon_days"] = [6]
        cell = deepcopy(row["to_date"])
        del cell["sessions"]
        row["horizons"] = {"6": cell}
        self.assertEqual(census([frozen], {"grades": [row]})["matured_books"], 1)

    def test_refused_top_grade_cannot_promote_an_ok_horizon(self):
        frozen, row = book(), grade()
        frozen["horizon_days"] = [6]
        row["horizons"] = {"6": {k: v for k, v in row["to_date"].items() if k != "sessions"}}
        row["status"] = "REFUSED"
        value = census([frozen], {"grades": [row]})
        self.assertIsNone(value["matured_books"])
        self.assertIsNone(value["marked"])

    def test_mature_horizon_requires_finite_outcome_fields(self):
        for field in ("gross", "net", "nav_usd", "benchmark_return", "vs_benchmark", "weight_priced"):
            frozen, row = book(), grade()
            frozen["horizon_days"] = [6]
            cell = deepcopy(row["to_date"])
            cell.pop("sessions")
            cell[field] = float("inf")
            row["horizons"] = {"6": cell}
            with self.subTest(field=field):
                self.assertIsNone(census([frozen], {"grades": [row]})["matured_books"])

    def test_maturity_date_after_final_mark_or_before_entry_refuses(self):
        for end in ("2026-10-24", "2026-10-15", "not-a-date", "2026-10-22"):
            frozen, row = book(), grade()
            frozen["horizon_days"] = [6]
            cell = {k: v for k, v in row["to_date"].items() if k != "sessions"}
            cell["as_of"] = end
            row["horizons"] = {"6": cell}
            with self.subTest(end=end):
                self.assertIsNone(census([frozen], {"grades": [row]})["matured_books"])

    def test_pending_label_after_declared_maturity_refuses(self):
        frozen = book()
        frozen["horizon_days"] = [6]
        row = grade()
        row["horizons"] = {"6": {"status": "PENDING", "why": "inconsistent"}}
        self.assertIsNone(census([frozen], {"grades": [row]})["matured_books"])

    def test_pending_requires_reason_and_object_schema(self):
        for cell in ({"status": "PENDING"}, [], "PENDING"):
            row = grade()
            row["horizons"]["63"] = cell
            with self.subTest(cell=cell):
                self.assertIsNone(census(grades={"grades": [row]})["matured_books"])

    def test_declared_horizon_schema_refuses_duplicates_and_boolean(self):
        for declared in ([63, 63], [True], [0], ["63"], []):
            frozen = book()
            frozen["horizon_days"] = declared
            with self.subTest(declared=declared), self.assertRaisesRegex(ValueError, "INVALID_DECLARED_HORIZONS"):
                census([frozen], {"grades": [grade()]})

    def test_cash_only_grade_still_has_entry_but_not_positive_exposure(self):
        row = grade()
        row["weight_in_market"] = 0.0
        value = census(grades={"grades": [row]})
        self.assertEqual((value["entered"], value["marked"], value["positive_market_exposure"], value["zero_market_exposure"]),
                         (1, 1, 0, 1))

    def test_positive_exposure_requires_successful_mark_and_finite_weight(self):
        for weight in (None, float("inf"), -0.1, True):
            row = grade()
            row["weight_in_market"] = weight
            with self.subTest(weight=weight):
                value = census(grades={"grades": [row]})
                self.assertIsNone(value["positive_market_exposure"])
                self.assertIsNone(value["zero_market_exposure"])

    def test_unknown_grader_version_cannot_validate(self):
        for version in (None, True, "2", 99):
            row = grade()
            row["grade_rule_version"] = version
            with self.subTest(version=version):
                self.assertIsNone(census(grades={"grades": [row]})["marked"])

    def test_all_success_outcome_fields_are_required(self):
        for field in ("gross", "net", "nav_usd", "benchmark_return", "vs_benchmark", "weight_priced"):
            row = grade()
            del row["to_date"][field]
            with self.subTest(field=field):
                self.assertIsNone(census(grades={"grades": [row]})["marked"])

    def test_receipt_upper_bound_cannot_claim_future_closed_session(self):
        value = census(grades={"grades": [grade()], "closed_session": "2026-10-30"})
        self.assertIsNone(value["marked"])

    def test_absent_generation_clock_cannot_validate(self):
        value = cohort_census([book()], asof="2026-10-15", expected_count=1,
                              grade_doc={"grades": [grade()], "closed_session": "2026-10-23"})
        self.assertIsNone(value["marked"])


if __name__ == "__main__":
    unittest.main()
