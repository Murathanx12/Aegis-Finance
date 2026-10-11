"""Synthetic offline vintage-consumer regressions, never investment evidence."""
import copy
import json

import exchange_calendars as xcals
import pandas as pd
import pytest

from backend.services import beta_v1_consumers as consumer
from backend.services import beta_v1_policy as policy
from backend.services import beta_v1_replay as replay
from backend.tests.test_beta_v1_consumers import protocol, qualified_current


@pytest.fixture(autouse=True)
def no_panel_reads(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("vintage fixtures must not read an analytical panel")
    monkeypatch.setattr(pd, "read_parquet", refused)
    monkeypatch.setattr(pd, "read_csv", refused)


def qualify(vintage, cutoff, current):
    q = {"schema": "beta_v1_weight_qualification/1", "verdict": "PASS_INDEPENDENT_WEIGHT_VINTAGE",
        "artifact_hash": vintage["artifact_hash"], "source_hash": policy.digest(vintage),
        "source_hash_kind": "CANONICAL_ARTIFACT_WITH_SEAL", "review_hash_kind": "CANONICAL_REVIEW_JSON",
        "source_ref": "fixture://vintage", "review_ref": "fixture://independent-review",
        "qualification_reason": "synthetic independently reviewed binding",
        "available_at": cutoff.isoformat(), "source_observed_at": (cutoff+pd.Timedelta(minutes=1)).isoformat(),
        "qualified_at": (cutoff+pd.Timedelta(minutes=2)).isoformat(),
        "valid_until_at": (pd.Timestamp(current["asof_utc"])+pd.Timedelta(days=1)).isoformat(),
        "freshness_rule": "REVIEWED_VALID_UNTIL"}
    approved = {"schema": "beta_v1_independent_weight_review/1", "verdict": "PASS_SCOPED_WEIGHT_VINTAGE",
        "artifact_hash": vintage["artifact_hash"], "source_hash": policy.digest(vintage),
        "definitions_hash": policy.digest(vintage["definitions"]), "weights_hash": policy.digest(vintage["weights"]),
        "components_hash": policy.digest(vintage["components"]), "parameters": vintage["parameters"],
        "code_hashes": vintage["code_hashes"], **{k: q[k] for k in ("source_ref", "review_ref",
            "qualification_reason", "available_at", "source_observed_at", "qualified_at", "valid_until_at", "freshness_rule")}}
    q.update(reviewed_vintage=approved, review_sha256=policy.digest(approved))
    return q


def supplied_vintage(*, min_blocks=30):
    current = qualified_current()
    row = copy.deepcopy(current["qualified_return_records"][0])
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2024-11-01", "2025-02-28")
    start, end = calendar.session_close(sessions[0]), calendar.session_close(sessions[21])
    made = start-pd.Timedelta(hours=5)
    row.update(forecast_id="synthetic-prior-vintage", root_event="UNKNOWN_DATE_TICKER:prior",
        forecast_at=made.isoformat(), available_at=made.isoformat(),
        label_start_at=start.isoformat(), label_end_at=end.isoformat(), valid_until_at=start.isoformat(),
        outcome_at=(end+pd.Timedelta(hours=1)).isoformat())
    qualifications = {policy.digest(row): {"source_hash": row["source_hash"],
        "source_ref": "fixture://history", "adapter_version": "fixture",
        "qualification_reason": "synthetic matured return, not a converted probability"}}
    cutoff = pd.Timestamp(current["asof_utc"])-pd.Timedelta(days=1)
    vintage = policy.fit([row], qualifications=qualifications,
        definitions=current["qualified_return_definitions"], cutoff=cutoff.isoformat(),
        task="expected_excess_return", horizon=21, objective_version=row["objective_version"], min_blocks=min_blocks)
    q = qualify(vintage, cutoff, current)
    return current, vintage, q


def preview(current, vintage, qualification, **kw):
    return consumer.current_draft(current, protocol(), source_hash="fixture://features",
        weight_artifact=vintage, weight_qualification=qualification, **kw)


def test_supplied_prior_vintage_reaches_forecast_plan_cost_twins_and_reload():
    current, vintage, q = supplied_vintage()
    originals = copy.deepcopy((current, vintage, q))
    result = preview(current, vintage, q)
    assert result["vintage"] == vintage
    assert result["vintage"]["components"]["news_model"]["n_rows"] == 1
    assert result["vintage"]["components"]["news_model"]["status"] == "SHRUNK_PRIOR"
    assert result["forecast"]["weight_artifact_hash"] == vintage["artifact_hash"]
    assert result["plan"]["weight_artifact_hash"] == vintage["artifact_hash"]
    assert result["weight_input"]["qualification_hash"] == policy.digest(q)
    assert result["forecast"]["forecasts"][0]["value"] == pytest.approx(.03)
    assert result["plan"]["holdings"][0]["score_after_cost"] == pytest.approx(.025)
    assert len(result["cost_sensitivity"]) == 3
    assert preview(*json.loads(json.dumps([current, vintage, q]))) == result
    assert (current, vintage, q) == originals


def test_optional_seam_default_is_unchanged_and_does_not_infer_a_vintage():
    current, vintage, q = supplied_vintage()
    implicit = consumer.current_draft(current, protocol(), source_hash="fixture://features")
    explicit = consumer.current_draft(current, protocol(), source_hash="fixture://features",
        weight_artifact=None, weight_qualification=None, variant="adaptive")
    assert implicit == explicit and "weight_input" not in implicit
    assert implicit["vintage"]["artifact_hash"] != vintage["artifact_hash"]
    assert implicit["vintage"]["components"]["news_model"]["n_rows"] == 0
    with pytest.raises(ValueError, match="without a weight artifact"):
        consumer.current_draft(current, protocol(), source_hash="fixture", weight_qualification=q)


def test_actual_typed_news_ablation_removes_influence_not_just_provenance():
    current, vintage, q = supplied_vintage()
    with_news = preview(current, vintage, q)
    without_news = preview(current, vintage, q, variant="without_news")
    assert with_news["forecast"]["forecasts"][0]["value"] == pytest.approx(.03)
    assert without_news["forecast"]["forecasts"][0]["value"] is None
    assert with_news["plan"]["holdings"] and not without_news["plan"]["holdings"]
    assert without_news["forecast"]["weight_artifact_hash"] == vintage["artifact_hash"]
    without_analyst = preview(current, vintage, q, variant="without_analyst")["plan"]
    for key in ("holdings", "cash_weight", "refusals", "weight_artifact_hash"):
        assert without_analyst[key] == with_news["plan"][key]
    # Variant identity remains in provenance even when numerical decisions agree.
    assert without_analyst["forecast_artifact_hash"] != with_news["plan"]["forecast_artifact_hash"]


@pytest.mark.parametrize("field,value", [
    ("schema", "unsupported"), ("verdict", "PASS"), ("artifact_hash", "b"*64),
    ("source_hash", "b"*64), ("source_ref", ""), ("review_ref", None),
    ("review_sha256", "not-a-hash"), ("qualification_reason", ""),
    ("available_at", "2025-01-01"), ("source_observed_at", None),
    ("qualified_at", "2030-01-01T00:00:00Z")])
def test_unqualified_or_future_vintage_refused(field, value):
    current, vintage, q = supplied_vintage()
    q[field] = value
    if field in q["reviewed_vintage"] and field not in {"artifact_hash", "source_hash"}:
        q["reviewed_vintage"][field] = value
        q["review_sha256"] = policy.digest(q["reviewed_vintage"])
    with pytest.raises((ValueError, TypeError)):
        preview(current, vintage, q)


@pytest.mark.parametrize("field,value", [
    ("task", "beats_benchmark"), ("horizon", 5), ("objective_version", "OTHER_BENCHMARK"),
    ("definitions", {}), ("mode", "LIVE"), ("parameters", {}),
    ("weights", {"news_model": .2})])
def test_even_rehashed_incompatible_artifact_refused(field, value):
    current, vintage, q = supplied_vintage()
    vintage[field] = value
    vintage["artifact_hash"] = policy.digest({k: v for k, v in vintage.items() if k != "artifact_hash"})
    q = qualify(vintage, pd.Timestamp(vintage["cutoff"]), current)
    with pytest.raises(ValueError):
        preview(current, vintage, q)


def test_artifact_mutation_cannot_reuse_earlier_review_binding():
    current, vintage, q = supplied_vintage()
    vintage["claim"] = "modified after independent review"
    vintage["artifact_hash"] = policy.digest({k: v for k, v in vintage.items() if k != "artifact_hash"})
    with pytest.raises(ValueError, match="bind exact artifact"):
        preview(current, vintage, q)


def test_future_outcome_inside_rehashed_vintage_refused():
    current, vintage, q = supplied_vintage()
    vintage["components"]["news_model"]["latest_outcome_at"] = "2030-01-01T00:00:00Z"
    vintage["artifact_hash"] = policy.digest({k: v for k, v in vintage.items() if k != "artifact_hash"})
    q = qualify(vintage, pd.Timestamp(vintage["cutoff"]), current)
    with pytest.raises(ValueError, match="future evidence"):
        preview(current, vintage, q)


def test_reviewed_weight_expiry_refuses_without_empty_vintage_fallback():
    current, vintage, q = supplied_vintage()
    q["valid_until_at"] = (pd.Timestamp(current["asof_utc"])-pd.Timedelta(seconds=1)).isoformat()
    q["reviewed_vintage"]["valid_until_at"] = q["valid_until_at"]
    q["review_sha256"] = policy.digest(q["reviewed_vintage"])
    with pytest.raises(ValueError, match="expired"):
        preview(current, vintage, q)


def test_rehashed_weight_cannot_claim_an_earlier_independent_approval():
    current, vintage, q = supplied_vintage()
    vintage["weights"]["news_model"] = 0.0
    vintage["components"]["news_model"]["effective_weight"] = 0.0
    vintage["artifact_hash"] = policy.digest({k: v for k, v in vintage.items() if k != "artifact_hash"})
    q.update(artifact_hash=vintage["artifact_hash"], source_hash=policy.digest(vintage))
    with pytest.raises(ValueError, match="independently reviewed fit"):
        preview(current, vintage, q)


@pytest.mark.parametrize("field,value", [
    ("code_hashes", {}), ("parameters", {"min_blocks": 30, "k_prior": 30.0,
        "gamma": True, "prior_share": .5, "embargo_sessions": 21}),
    ("weights", {"news_model": True})])
def test_wrong_constructor_or_boolean_parameters_and_weights_refused(field, value):
    current, vintage, q = supplied_vintage()
    vintage[field] = value
    vintage["artifact_hash"] = policy.digest({k: v for k, v in vintage.items() if k != "artifact_hash"})
    q = qualify(vintage, pd.Timestamp(vintage["cutoff"]), current)
    with pytest.raises(ValueError):
        preview(current, vintage, q)


def test_admitted_negative_return_remains_cash_decision_and_absence_unavailable():
    current, vintage, q = supplied_vintage()
    row = current["qualified_return_records"][0]
    prior_q = current["qualified_return_qualifications"][policy.digest(row)]
    row["x"] = -.03
    current["qualified_return_qualifications"] = {policy.digest(row): prior_q}
    negative = preview(current, vintage, q)
    assert not negative["plan"]["holdings"] and negative["plan"]["cash_weight"] == 1
    assert negative["decision_counts"]["valid_admitted_return_forecast_tickers"] == 1
    assert negative["decision"] == "CASH_100_PERCENT" and negative["investment_cash_decision"]
    current["qualified_return_records"] = []
    absent = preview(current, vintage, q)
    assert absent["decision"] == "RETURN_INPUTS_UNAVAILABLE"


def test_preview_does_not_alias_caller_vintage_or_review():
    current, vintage, q = supplied_vintage()
    result = preview(current, vintage, q)
    sealed = json.loads(json.dumps(result))
    vintage["components"]["news_model"]["n_rows"] = 999
    q["reviewed_vintage"]["weights_hash"] = "changed later"
    assert result == sealed


def test_existing_stricter_unknown_root_prior_vintage_can_be_consumed():
    current, vintage, q = supplied_vintage(min_blocks=replay.PRIOR_ONLY_MIN_BLOCKS)
    # This stricter branch is an existing frozen guard, never a lower threshold.
    result = preview(current, vintage, q)
    assert result["vintage"]["parameters"]["min_blocks"] == replay.PRIOR_ONLY_MIN_BLOCKS
    assert result["vintage"]["components"]["news_model"]["status"] == "SHRUNK_PRIOR"
    assert result["forecast"]["weight_artifact_hash"] == vintage["artifact_hash"]


def test_unknown_root_prior_guard_cannot_claim_graduated_weights():
    current, vintage, q = supplied_vintage()
    vintage["parameters"]["min_blocks"] = replay.PRIOR_ONLY_MIN_BLOCKS
    vintage["components"]["news_model"]["status"] = "LEARNED"
    vintage["artifact_hash"] = policy.digest({k: v for k, v in vintage.items() if k != "artifact_hash"})
    q = qualify(vintage, pd.Timestamp(vintage["cutoff"]), current)
    with pytest.raises(ValueError, match="frozen Beta policy"):
        preview(current, vintage, q)


def test_real_fitter_fixture_unequal_weights_changes_forecast_and_plan_vs_equal():
    current = qualified_current()
    defs = copy.deepcopy(current["qualified_return_definitions"])
    defs["analyst_model"] = {**defs["news_model"], "source_family": "analyst", "correlation_group": "analyst"}
    current["qualified_return_definitions"] = defs
    extra = {**current["qualified_return_records"][0], "component": "analyst_model",
        "forecast_id": "synthetic-current-analyst", "x": -.03}
    current["qualified_return_records"].append(extra)
    current["qualified_return_qualifications"][policy.digest(extra)] = {
        "source_hash": extra["source_hash"], "source_ref": "fixture://current",
        "adapter_version": "fixture", "qualification_reason": "synthetic return comparator"}
    sessions = xcals.get_calendar("XNYS").sessions_in_range("2018-01-02", "2024-12-31")
    calendar = xcals.get_calendar("XNYS")
    history, qualifications = [], {}
    for i in range(66):
        start, end = calendar.session_close(sessions[i*22]), calendar.session_close(sessions[i*22+21])
        made = start-pd.Timedelta(hours=5)
        actual = .03 if i % 2 else -.03
        for component, prediction in (("news_model", actual), ("analyst_model", -actual)):
            row = {**extra, "component": component, "forecast_id": f"synthetic-{component}-{i}",
                "root_event": f"synthetic-event-{i}", "forecast_at": made.isoformat(), "available_at": made.isoformat(),
                "label_start_at": start.isoformat(), "label_end_at": end.isoformat(), "valid_until_at": start.isoformat(),
                "outcome_at": (end+pd.Timedelta(hours=1)).isoformat(), "x": prediction, "y": actual}
            history.append(row)
            qualifications[policy.digest(row)] = {"source_hash": row["source_hash"], "source_ref": "fixture://history",
                "adapter_version": "fixture", "qualification_reason": "synthetic nonoverlapping fitter evidence"}
    cutoff = pd.Timestamp(current["asof_utc"])-pd.Timedelta(days=1)
    vintage = policy.fit(history, qualifications=qualifications, definitions=defs, cutoff=cutoff.isoformat(),
        task="expected_excess_return", horizon=21, objective_version=extra["objective_version"])
    q = qualify(vintage, cutoff, current)
    adaptive, equal = preview(current, vintage, q), preview(current, vintage, q, variant="equal")
    assert vintage["weights"]["news_model"] == pytest.approx(1.0)
    assert vintage["weights"]["analyst_model"] == pytest.approx(0.0)
    assert adaptive["forecast"]["forecasts"][0]["value"] == pytest.approx(.03)
    assert equal["forecast"]["forecasts"][0]["value"] == pytest.approx(0.0)
    assert adaptive["plan"]["holdings"] and not equal["plan"]["holdings"]
    assert adaptive["forecast"]["weight_artifact_hash"] == equal["forecast"]["weight_artifact_hash"]
