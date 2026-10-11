"""Small synthetic consumer fixtures, never performance evidence."""
import copy
import json

import exchange_calendars as xcals
import pandas as pd
import pytest

from backend.services import beta_v1_policy as policy
from backend.services import beta_v1_consumers as consumer


def protocol():
    return {"primary_portfolio_horizon_sessions": 21, "separate_secondary_horizon_sessions": 5,
        "new_simulated_costs": {"round_trip_bps": 50, "sensitivity_round_trip_bps": [20, 50, 100]},
        "portfolio_preview_mandate": {"equity": "Normalized unit; no account balance or fills invented",
            "issuer_cap": .1, "cash_floor": .7, "max_names": 10, "minimum_price": 5,
            "minimum_trailing20_median_dollar_volume": 20_000_000}}


def history():
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2025-01-02", "2025-05-30")
    records, qualifications = [], {}
    for i in range(10):
        start, end = calendar.session_close(sessions[i*6]), calendar.session_close(sessions[i*6+5])
        made = start-pd.Timedelta(hours=5)
        row = {"forecast_id": f"fx-{i}", "component": "news_model", "ticker": "AAA",
            "root_event": "UNKNOWN_DATE_TICKER:"+str(i), "root_independence": "UNKNOWN",
            "source_hash": policy.digest({"source": i}), "forecast_at": made.isoformat(),
            "available_at": made.isoformat(), "label_start_at": start.isoformat(),
            "label_end_at": end.isoformat(), "valid_until_at": start.isoformat(), "calendar": "XNYS",
            "window_contract": "session_close_to_close", "outcome_at": (end+pd.Timedelta(hours=1)).isoformat(),
            "task": "beats_benchmark", "horizon": 5, "objective_version": "beats_benchmark:SPY:NATIVE_PRICE_CLOSE_UNKNOWN_ADJUSTMENT",
            "model_version": "fixture-v1", "prompt_version": "v1", "x": .8 if i%2 == 0 else .2,
            "y": 1 if i%2 == 0 else 0, "rel_return": .03 if i%2 == 0 else -.02,
            "costs_charged": None, "cost_rate_bps": None}
        records.append(row)
        qualifications[policy.digest(row)] = {"source_hash": row["source_hash"], "source_ref": "fixture://original",
            "adapter_version": "fixture", "qualification_reason": "synthetic original archived probability"}
    return {"artifact_hash": "fixture-real-replay-hash", "join": {"records": records, "qualifications": qualifications,
        "definitions": {"news_model": {"source_family": "news", "model_version": "fixture-v1", "prompt_version": "v1",
            "correlation_group": "news", "model_version_status": "RECORDED"}}}}


def test_probability_report_keeps_horizons_objectives_costs_and_abstentions_separate():
    variants = {name: {"brier": .04, "log_loss": .2} for name in ("equal", "adaptive", "without_analyst")}
    variants["without_news"] = {"brier": None, "log_loss": None}
    decisions = [{"task": "beats_benchmark", "horizon": h, "objective_version": o,
        "decision_at": "2025-01-02T14:00:00Z", "costs_charged": None, "cost_rate_bps": None,
        "variants": variants} for h, o in ((1, "SPY:H1"), (5, "SPY:H5"), (5, "QQQ:H5"))]
    result = consumer.separated_probability_metrics({"artifact_hash": "sourcehash", "paired_replay": {"decisions": decisions}})
    assert len(result["contracts"]) == 3
    assert result["pooled_cross_horizon_metrics"] == "DISABLED"
    for cell in result["contracts"]:
        news = next(v for v in cell["variants"] if v["variant"] == "without_news")
        assert news["mean_brier"] is None and news["n_abstain_or_unavailable"] == 1
        assert cell["variants"][0]["status"] == "UNAVAILABLE"


def test_real_chain_fixture_h5_calibration_weights_forecast_plan_refusal_and_reload():
    source = history()
    trace = consumer.derived_h5_return_trace(source, protocol())
    assert 0 < trace["derived_rows"] < trace["original_h5_rows"]
    assert trace["traces"]
    for row in trace["traces"]:
        adaptive = row["variants"]["adaptive"]
        assert adaptive["forecast"]["weight_artifact_hash"] == adaptive["weight_artifact_hash"]
        assert adaptive["forecast"]["forecasts"][0]["task"] == "expected_excess_return"
        assert adaptive["plan"]["cash_weight"] == 1
        assert not adaptive["plan"]["holdings"]
        assert adaptive["plan"]["refusals"]
        assert row["variants"]["without_news"]["forecast"]["forecasts"][0]["value"] is None
        assert adaptive["cost_once_round_trip_bps"] == 50
    assert consumer.derived_h5_return_trace(json.loads(json.dumps(source)), protocol()) == trace


def test_h5_derivation_training_cutoffs_and_future_grade_mutation_do_not_change_earlier_trace():
    source = history()
    before = consumer.derived_h5_return_trace(source, protocol())
    changed = copy.deepcopy(source)
    original_qualification = changed["join"]["qualifications"][policy.digest(changed["join"]["records"][-1])]
    changed["join"]["records"][-1]["rel_return"] = .9
    changed["join"]["qualifications"][policy.digest(changed["join"]["records"][-1])] = original_qualification
    after = consumer.derived_h5_return_trace(changed, protocol())
    assert before["traces"][:-1] == after["traces"][:-1]
    by_hash = {policy.digest(r): r for r in source["join"]["records"]}
    for derivation in before["derivations"].values():
        assert all(pd.Timestamp(by_hash[h]["outcome_at"]) <= pd.Timestamp(derivation["cutoff"])
                   for h in derivation["training_record_hashes"])


def test_h1_not_aliased_and_original_forecasts_not_rewritten():
    source = history()
    original = copy.deepcopy(source)
    for row in source["join"]["records"]:
        row["horizon"] = 1
    result = consumer.derived_h5_return_trace(source, protocol())
    assert result["derived_rows"] == 0 and not result["traces"]
    untouched = history()
    consumer.derived_h5_return_trace(untouched, protocol())
    assert untouched == original


def test_current_primary_measured_all_cash_and_secondary_separate_idempotent():
    current = {"asof_utc": "2025-06-01T15:00:00Z", "records": [{"ticker": "AAA", "expected_return": None,
        "issuer_identity": "UNKNOWN", "currency_identity": "UNKNOWN", "allocation_eligible": False,
        "prices": {"price": 10, "trailing20_median_dollar_volume": 30_000_000}, "fixed_revision_flow_score": 42}]}
    primary = consumer.current_draft(current, protocol(), source_hash="featureshash")
    secondary = consumer.current_draft(current, protocol(), source_hash="featureshash", horizon=5)
    assert primary["decision"] == "RETURN_INPUTS_UNAVAILABLE"
    assert primary["horizon"] == 21 and secondary["horizon"] == 5
    assert primary["plan"]["cash_weight"] == 1 and not primary["forecast"]["forecasts"]
    assert primary == consumer.current_draft(json.loads(json.dumps(current)), protocol(), source_hash="featureshash")
    assert len(primary["cost_sensitivity"]) == 3


def test_current_net_unknown_inputs_not_double_charged_or_horizon_converted():
    source = history()
    current = {"asof_utc": "2025-06-01T15:00:00Z", "records": [],
        "qualified_return_records": [{**source["join"]["records"][0], "horizon": 21,
            "task": "expected_excess_return", "return_cost_basis": "NET_50BPS"}, source["join"]["records"][1]]}
    result = consumer.current_draft(current, protocol(), source_hash="featureshash")
    assert len(result["return_input_refusals"]) == 2
    assert result["plan"]["cash_weight"] == 1


def qualified_current():
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2025-01-02", "2025-05-30")
    start, end = calendar.session_close(sessions[30]), calendar.session_close(sessions[51])
    made = start-pd.Timedelta(hours=5)
    original = history()["join"]["records"][0]
    row = {**original, "forecast_id": "current-h21", "forecast_at": made.isoformat(),
        "available_at": made.isoformat(), "label_start_at": start.isoformat(), "label_end_at": end.isoformat(),
        "valid_until_at": start.isoformat(), "outcome_at": (end+pd.Timedelta(hours=1)).isoformat(),
        "task": "expected_excess_return", "horizon": 21, "objective_version": "CURRENT_NATIVE_PRICE_EXCESS_H21",
        "x": .03, "y": .02, "return_cost_basis": "GROSS_NATIVE_PRICE_CLOSE_EXCESS"}
    snapshot = {"venue": "NYSE", "currency": "USD", "issuer": "AAA-fixture",
        "qualification_reason": "synthetic qualified snapshot", "source_ref": "fixture://instrument",
        "source_hash": policy.digest({"instrument": "AAA"}), "admissible": True, "liquid": True,
        "price": 10, "price_at": made.isoformat(), "trailing20_median_dollar_volume": 30_000_000,
        "trailing20_median_dollar_volume_at": made.isoformat()}
    return {"asof_utc": made.isoformat(), "qualified_return_records": [row],
        "qualified_return_definitions": history()["join"]["definitions"],
        "qualified_return_qualifications": {policy.digest(row): {"source_hash": row["source_hash"],
            "source_ref": "fixture://current", "adapter_version": "fixture", "qualification_reason": "synthetic H21 return"}},
        "records": [{"ticker": "AAA", "expected_return": None, "issuer_identity": {"qualified": True},
            "currency_identity": {"qualified": True}, "allocation_eligible": True,
            "prices": {"price": 10, "trailing20_median_dollar_volume": 30_000_000},
            "qualified_instrument_snapshot": snapshot}]}


def test_positive_qualified_h21_uses_forecast_not_descriptor_and_cost_once():
    current = qualified_current()
    result = consumer.current_draft(current, protocol(), source_hash="fixture")
    assert result["forecast"]["forecasts"][0]["value"] == pytest.approx(.03)
    assert result["plan"]["holdings"][0]["weight"] == pytest.approx(.1)
    assert result["plan"]["holdings"][0]["score_after_cost"] == pytest.approx(.025)
    assert result["decision"] == "INACTIVE_PROPOSED_ONLY"
    assert result == consumer.current_draft(json.loads(json.dumps(current)), protocol(), source_hash="fixture")
    current["qualified_return_records"] = []
    current["records"][0]["expected_return"] = .99
    assert consumer.current_draft(current, protocol(), source_hash="fixture")["plan"]["cash_weight"] == 1


@pytest.mark.parametrize("field,value", [("price", 2), ("price", None), ("price", float("nan")),
    ("price", float("inf")), ("trailing20_median_dollar_volume", 1),
    ("trailing20_median_dollar_volume", None), ("trailing20_median_dollar_volume", float("nan")),
    ("trailing20_median_dollar_volume", float("inf")), ("price_at", "2025-01-01"),
    ("source_hash", "unbound"), ("trailing20_median_dollar_volume_at", "2025-01-01T00:00:00Z")])
def test_actual_instrument_snapshot_must_pass_floors_clocks_and_provenance(field, value):
    current = qualified_current()
    current["records"][0]["qualified_instrument_snapshot"][field] = value
    result = consumer.current_draft(current, protocol(), source_hash="fixture")
    assert result["plan"]["cash_weight"] == 1 and not result["plan"]["holdings"]
    assert result["refusals"]


def test_descriptor_snapshot_mismatch_refused_even_above_floor():
    current = qualified_current()
    current["records"][0]["prices"]["price"] = 11
    assert not consumer.current_draft(current, protocol(), source_hash="fixture")["plan"]["holdings"]


def test_identical_calibration_duplicate_changes_no_derived_output_or_hash():
    source = history()
    before = consumer.derived_h5_return_trace(source, protocol())
    source["join"]["records"].append(copy.deepcopy(source["join"]["records"][0]))
    assert consumer.derived_h5_return_trace(source, protocol()) == before


def test_conflicting_root_quarantined_before_calibration_and_future_append_invariant():
    source = history()
    before = consumer.derived_h5_return_trace(source, protocol())
    conflict = {**source["join"]["records"][0], "forecast_id": "related-duplicate"}
    source["join"]["records"].append(conflict)
    source["join"]["qualifications"][policy.digest(conflict)] = source["join"]["qualifications"][policy.digest(source["join"]["records"][0])]
    after = consumer.derived_h5_return_trace(source, protocol())
    conflict_hashes = {policy.digest(conflict), policy.digest(source["join"]["records"][0])}
    for derivation in after["derivations"].values():
        assert not conflict_hashes.intersection(derivation["training_record_hashes"])
        assert derivation["admission"]["exclusions"]
    assert after == consumer.derived_h5_return_trace(json.loads(json.dumps(source)), protocol())
    future = copy.deepcopy(source["join"]["records"][9])
    future["forecast_id"] = "future-related"
    source["join"]["records"].append(future)
    source["join"]["qualifications"][policy.digest(future)] = source["join"]["qualifications"][policy.digest(source["join"]["records"][9])]
    future_trace = consumer.derived_h5_return_trace(source, protocol())
    last_made = future["forecast_at"]
    assert [t for t in future_trace["traces"] if t["decision_at"] < last_made] == [t for t in after["traces"] if t["decision_at"] < last_made]
    assert before["traces"] != after["traces"]



def replace_return(current, value):
    row = current["qualified_return_records"][0]
    qualification = current["qualified_return_qualifications"].pop(policy.digest(row))
    row["x"] = value
    current["qualified_return_qualifications"][policy.digest(row)] = qualification


def test_unavailable_return_is_not_an_investment_cash_decision():
    current = qualified_current()
    current["qualified_return_records"] = []
    result = consumer.current_draft(current, protocol(), source_hash="fixture")
    assert result["decision"] == "RETURN_INPUTS_UNAVAILABLE"
    assert result["plan"]["cash_weight"] == 1 and not result["investment_cash_decision"]
    assert result["decision_counts"]["valid_admitted_return_forecast_tickers"] == 0
    assert result == consumer.current_draft(json.loads(json.dumps(current)), protocol(), source_hash="fixture")


@pytest.mark.parametrize("failure", ["unknown_issuer", "price_floor", "planner_liquid_false", "missing_venue", "independent_clock_parked"])
def test_actual_return_but_unqualified_instruments_are_instrument_unavailable(failure):
    current = qualified_current()
    row = current["records"][0]
    snapshot = row["qualified_instrument_snapshot"]
    if failure == "unknown_issuer": row["issuer_identity"] = "UNKNOWN"
    elif failure == "price_floor": snapshot["price"] = 2
    elif failure == "planner_liquid_false": snapshot["liquid"] = False
    elif failure == "missing_venue": snapshot.pop("venue")
    elif failure == "independent_clock_parked": snapshot["trailing20_median_dollar_volume_at"] = (pd.Timestamp(snapshot["price_at"])-pd.Timedelta(minutes=1)).isoformat()
    result = consumer.current_draft(current, protocol(), source_hash="fixture")
    assert result["decision"] == "INSTRUMENT_INPUTS_UNAVAILABLE"
    assert result["decision_counts"]["valid_admitted_return_forecast_tickers"] == 1
    assert result["decision_counts"]["planner_admitted_instrument_tickers"] == 0
    assert result["plan"]["cash_weight"] == 1 and not result["investment_cash_decision"]


@pytest.mark.parametrize("gross_return", [-.01, .001])
def test_cash_is_real_engine_choice_only_with_admitted_inputs(gross_return):
    current = qualified_current()
    replace_return(current, gross_return)
    result = consumer.current_draft(current, protocol(), source_hash="fixture")
    assert result["decision"] == "CASH_100_PERCENT" and result["investment_cash_decision"]
    assert result["decision_counts"]["valid_admitted_return_forecast_tickers"] == 1
    assert result["decision_counts"]["planner_admitted_instrument_tickers"] == 1
    assert not result["plan"]["holdings"] and result["plan"]["cash_weight"] == 1
    assert result == consumer.current_draft(json.loads(json.dumps(current)), protocol(), source_hash="fixture")


def test_holdings_keep_existing_plan_arithmetic_and_disclose_partial_universe():
    current = qualified_current()
    original = current["qualified_return_records"][0]
    other = {**original, "ticker": "BBB", "forecast_id": "fixture-BBB", "root_event": "fixture-BBB-root"}
    current["qualified_return_records"].append(other)
    current["qualified_return_qualifications"][policy.digest(other)] = current["qualified_return_qualifications"][policy.digest(original)]
    missing = copy.deepcopy(current["records"][0])
    missing["ticker"] = "BBB"
    missing.pop("qualified_instrument_snapshot")
    current["records"].append(missing)
    result = consumer.current_draft(current, protocol(), source_hash="fixture")
    assert result["decision"] == "INACTIVE_PROPOSED_ONLY"
    assert result["plan"]["holdings"][0]["weight"] == pytest.approx(.1)
    assert result["plan"]["holdings"][0]["score_after_cost"] == pytest.approx(.025)
    assert result["decision_counts"]["valid_admitted_return_forecast_tickers"] == 2
    assert result["decision_counts"]["planner_admitted_instrument_tickers"] == 1
    assert result["decision_counts"]["valid_forecast_tickers_without_admitted_instruments"] == 1
    assert result["decision_counts"]["partial_admitted_universe"]


def test_rejected_basis_task_or_horizon_cannot_be_called_cash():
    current = qualified_current()
    current["qualified_return_records"][0]["return_cost_basis"] = "NET_50BPS"
    current["qualified_return_records"].append({**current["qualified_return_records"][0], "task": "beats_benchmark"})
    current["qualified_return_records"].append({**current["qualified_return_records"][0], "horizon": 5})
    result = consumer.current_draft(current, protocol(), source_hash="fixture")
    assert result["decision"] == "RETURN_INPUTS_UNAVAILABLE"
    assert len(result["return_input_refusals"]) == 3 and not result["investment_cash_decision"]


def test_cli_status_summary_does_not_call_unavailable_preview_cash():
    from scripts import beta_v1_consumer_trace as cli
    current = qualified_current()
    current["qualified_return_records"] = []
    result = consumer.current_draft(current, protocol(), source_hash="fixture")
    summary = cli.current_status_summary(result)
    assert summary["primary_h21_decision"] == "RETURN_INPUTS_UNAVAILABLE"
    assert summary["primary_cash"] is None and summary["primary_cash_weight_preview"] == 1
    assert not summary["primary_investment_cash_decision"]



def test_declared_all_cash_mandate_counts_no_positive_exposure():
    current = qualified_current()
    rules = protocol()
    rules["portfolio_preview_mandate"]["cash_floor"] = 1.0
    result = consumer.current_draft(current, rules, source_hash="fixture")
    assert result["plan"]["holdings"] and result["plan"]["holdings"][0]["weight"] == 0
    assert result["plan"]["cash_weight"] == 1
    assert result["decision"] == "CASH_100_PERCENT" and result["investment_cash_decision"]
    assert result["decision_counts"]["proposed_holdings"] == 0
    assert result["decision_counts"]["planner_admitted_instrument_tickers"] == 1
    assert result == consumer.current_draft(json.loads(json.dumps(current)), rules, source_hash="fixture")


def test_same_issuer_cap_exhaustion_counts_only_positive_holdings():
    current = qualified_current()
    first = current["qualified_return_records"][0]
    other = {**first, "ticker": "BBB", "forecast_id": "same-issuer-BBB", "root_event": "same-issuer-BBB-root"}
    current["qualified_return_records"].append(other)
    current["qualified_return_qualifications"][policy.digest(other)] = current["qualified_return_qualifications"][policy.digest(first)]
    row = copy.deepcopy(current["records"][0])
    row["ticker"] = "BBB"
    current["records"].append(row)
    result = consumer.current_draft(current, protocol(), source_hash="fixture")
    assert len(result["plan"]["holdings"]) == 2
    assert sorted(h["weight"] for h in result["plan"]["holdings"]) == [0, pytest.approx(.1)]
    assert result["decision_counts"]["proposed_holdings"] == 1
    assert result["decision_counts"]["planner_admitted_instrument_tickers"] == 2
    assert result["decision"] == "INACTIVE_PROPOSED_ONLY"


@pytest.mark.parametrize("weight", [True, False, float("nan"), -.1, float("inf")])
def test_invalid_planner_weights_fail_loud_not_a_cash_certificate(weight):
    current = qualified_current()
    result = consumer.current_draft(current, protocol(), source_hash="fixture")
    plan = copy.deepcopy(result["plan"])
    plan["holdings"][0]["weight"] = weight
    instruments = {"AAA": current["records"][0]["qualified_instrument_snapshot"]}
    with pytest.raises(ValueError, match="invalid planner holding weight"):
        consumer._current_decision_status(result["forecast"], instruments, plan,
            horizon=21, input_count=1, candidate_count=1)
