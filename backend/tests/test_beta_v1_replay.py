"""Pure adapter fixtures: never runtime data or performance evidence."""
import copy

import numpy as np
import pandas as pd
import pytest
import exchange_calendars as xcals

from backend.services import beta_v1_policy as policy
from backend.services import beta_v1_replay as replay


def fixture():
    sessions = xcals.get_calendar("XNYS").sessions_in_range("2025-01-02", "2025-02-21")
    prices = pd.DataFrame({"AAA": 100*np.cumprod(1+np.where(np.arange(len(sessions))%2, -.01, .02)),
                           "SPY": np.repeat(100., len(sessions))}, index=sessions)
    rows = []
    for i in range(12):
        day = sessions[i]
        ret = float(prices.AAA.iloc[i+1]/prices.AAA.iloc[i]-1)
        stamp = day.tz_localize("UTC")+pd.Timedelta(hours=14)
        rows.append({"prediction_id": f"fx-{i}", "source_full_row_sha256": policy.digest({"row": i}),
            "immutable_record_hash": policy.digest({"identity": i}), "ticker": "AAA", "benchmark": "SPY",
            "observable": "beats_benchmark", "threshold": None, "horizon_days": 1,
            "probability": .8 if ret > 0 else .2, "outcome": int(ret > 0),
            "made_at": stamp.isoformat(), "resolves_after": (day+pd.Timedelta(days=4)).date().isoformat(),
            "resolved_at_date_only": (day+pd.Timedelta(days=6)).date().isoformat(),
            "resolution_numeric": {"realised_return": ret, "vs_benchmark": ret, "benchmark_return": 0},
            "specialist": "source:fixture", "mechanism_id": "", "model": "fixture-model", "model_version": "v1",
            "prompt_version": "v1", "dependency_group": {"kind": "unknown_date_ticker_cell", "key_sha256": "not-genuine-root"},
            "source_refs_sha256": {}, "costs_charged": False, "cost_rate_bps": None})
    manifest = {"price_basis": "PRICE_RETURN_NOT_TOTAL_RETURN", "source_hashes": {"fixture://prices": "a"*64}}
    return rows, prices, manifest


def join(rows=None, prices=None, allow=True):
    original, panel, manifest = fixture()
    return replay.reconstruct(original if rows is None else rows, panel if prices is None else prices,
        price_manifest=manifest, projection_sha256="b"*64, allow_unknown_prior=allow)


def test_original_grade_verified_without_inventing_source_roots():
    result = join()
    assert len(result["records"]) == 12
    assert all(r["root_independence"] == "UNKNOWN" for r in result["records"])
    assert all(r["root_event"].startswith("UNKNOWN_DATE_TICKER:") for r in result["records"])
    assert all(q["source_reference_status"] == "UNKNOWN" for q in result["qualifications"].values())
    assert not join(allow=False)["records"]


def test_bad_grade_and_mismatched_benchmark_windows_are_not_regraded():
    rows, prices, _ = fixture()
    rows[0]["resolution_numeric"]["realised_return"] = .99
    result = join(rows=rows)
    assert result["verification"][0]["reason"].startswith("archived numeric grade mismatch")
    assert len(result["records"]) == 11
    rows, prices, _ = fixture()
    prices.loc[prices.index[0], "SPY"] = np.nan
    result = join(rows=rows, prices=prices)
    assert any("actual target windows differ" in r["reason"] for r in result["verification"] if r["reason"])


def test_unknown_model_version_and_prompt_are_zero_admissibility():
    rows, _, _ = fixture()
    rows[0]["model_version"] = ""
    rows[1]["prompt_version"] = ""
    result = join(rows=rows)
    assert len(result["records"]) == 10
    assert sum("UNRECORDED" in (r["reason"] or "") for r in result["verification"]) == 2


def test_conservative_gradeclock_and_future_leakage():
    rows, _, _ = fixture()
    assert replay.outcome_clock(rows[0]) == "2025-01-09T00:00:00+00:00"
    joined = join()
    result = replay.chronological_replay(joined)
    for vintage in result["weight_artifacts"].values():
        assert all(a["latest_outcome_at"] is None or pd.Timestamp(a["latest_outcome_at"]) <= pd.Timestamp(vintage["cutoff"])
                   for a in vintage["components"].values())
        assert all(a["status"] != "LEARNED" for a in vintage["components"].values())
        assert vintage["parameters"]["min_blocks"] == replay.PRIOR_ONLY_MIN_BLOCKS


def test_replay_same_target_pairs_fixed_missing_controls_and_idempotence():
    joined = join()
    result = replay.chronological_replay(joined)
    assert result == replay.chronological_replay(joined)
    reversed_join = {**joined, "records": list(reversed(joined["records"]))}
    assert result == replay.chronological_replay(reversed_join)
    assert result["grid"] == list(replay.GRID)
    assert result["paired_results"][0]["status"] == "UNAVAILABLE"
    assert result["paired_results"][1]["status"] == "UNAVAILABLE"
    assert result["paired_results"][2]["n_same_question_pairs"] == 12
    assert result["portfolio_metrics"]["status"] == "UNAVAILABLE"


def test_original_scores_include_losses_and_unsupported_tasks_and_pending_counts():
    rows, _, _ = fixture()
    rows[0]["observable"] = "abs_move_exceeds"
    rows[0]["threshold"] = .05
    projection = {"graded_projection_private": rows, "unresolved_compact_private": [{"identity": "not-scored"}],
                  "protected_stream_gate": {"counts": {"invalid_terminal_rows": 5}}}
    result = replay.original_forward(projection)
    assert len(result["cells"]) == 2
    assert sum(c["negative_labels"] for c in result["cells"]) > 0
    assert result["unresolved_rows_in_projection"] == 1
    assert result["original_projection_gate_counts"]["invalid_terminal_rows"] == 5


def test_calibration_no_future_data_and_horizon_alias_not_faked():
    joined = join()
    # Existing ER calibration has no h1 alias; availability must remain absent.
    output, provenance = replay.calibrated_return_inputs(joined, joined["records"][-1:], cutoff="2025-01-31T00:00:00Z")
    assert not output and not provenance["available"]
    assert "exact horizon/task" in provenance["unavailable"][0]["reason"]
    output, _ = replay.calibrated_return_inputs(joined, joined["records"][:1], cutoff="2025-01-02T14:00:00Z")
    assert not output


def test_projection_hash_and_protected_gate(tmp_path):
    import hashlib
    import json
    value = {"schema": "protected_first_stream_projection_v2/1", "protected_stream_gate": {
        "end_prefix_verified": True, "marker_present": False}}
    p = tmp_path/"projection.json"
    p.write_text(json.dumps(value), encoding="utf-8")
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    assert replay.load_projection(p, expected_sha256=sha)["_projection_sha256"] == sha
    with pytest.raises(ValueError, match="pin mismatch"):
        replay.load_projection(p, expected_sha256="a"*64)


def test_future_roster_root_and_family_cannot_change_earlier_vintages():
    joined = join()
    # Original known-root fixture, then append a future UNKNOWN source/family.
    updated = []
    quals = {}
    for old in joined["records"]:
        r = {**old, "root_independence": "DECLARED", "root_event": "declared:"+old["source_hash"]}
        updated.append(r)
        quals[policy.digest(r)] = joined["qualifications"][policy.digest(old)]
    joined = {**joined, "records": updated, "qualifications": quals}
    before = replay.chronological_replay(joined, minimum_blocks=2)
    future = {**updated[-1], "forecast_id": "future-new-model", "component": "new-analyst-model",
        "model_version": "v2", "root_independence": "UNKNOWN", "root_event": "UNKNOWN_DATE_TICKER:future",
        "forecast_at": "2025-02-20T14:00:00Z", "available_at": "2025-02-20T14:00:00Z",
        "label_start_at": "2025-02-20T21:00:00Z", "label_end_at": "2025-02-21T21:00:00Z",
        "valid_until_at": "2025-02-20T21:00:00Z", "outcome_at": "2025-02-24T00:00:00Z"}
    new_def = {**next(iter(joined["definitions"].values())), "source_family": "analyst",
               "correlation_group": "analyst", "model_version": "v2"}
    after = replay.chronological_replay({**joined, "records": updated+[future],
        "definitions": {**joined["definitions"], future["component"]: new_def},
        "qualifications": {**quals, policy.digest(future): next(iter(quals.values()))}}, minimum_blocks=2)
    assert after["decisions"][:-1] == before["decisions"]
    assert {k: after["weight_artifacts"][k] for k in before["weight_artifacts"]} == before["weight_artifacts"]
    assert after["decisions"][-1]["prior_only"] is True
    assert all(v["parameters"]["min_blocks"] == replay.PRIOR_ONLY_MIN_BLOCKS for v in
               replay.chronological_replay(joined, force_prior_only=True)["weight_artifacts"].values())


@pytest.mark.parametrize("writer,fam,variant", [("source:fixture", "news", "without_news"),
    ("news_digest:fixture", "news", "without_news"),
    ("analyst:fixture", "analyst", "without_analyst"),
    ("revision_flow:fixture", "analyst", "without_analyst")])
def test_authenticated_writer_lineage_survives_arbitrary_mechanism(writer, fam, variant):
    rows, _, _ = fixture()
    for row in rows:
        row.update(specialist=writer, mechanism_id="fixture_unrelated_numerical_mechanism")
    joined = join(rows=rows)
    definition = next(iter(joined["definitions"].values()))
    assert definition["source_family"] == fam
    assert definition["original_writer"] == writer
    assert "original_mechanism_id" not in definition
    assert all(r["original_mechanism_id"] == "fixture_unrelated_numerical_mechanism" for r in joined["records"])
    result = replay.chronological_replay(joined)
    assert all(d["variants"][variant]["probability"] is None for d in result["decisions"])
    assert all(d["variants"]["equal"]["probability"] is not None for d in result["decisions"])


@pytest.mark.parametrize("cap,resource", [("max_records", "records"), ("max_cohorts", "cohorts"),
    ("max_vintages", "vintages"), ("max_artifact_bytes", "artifact_bytes"), ("max_output_bytes", "output_bytes")])
def test_small_caps_refuse_instead_of_partial_success(cap, resource):
    joined = join()
    limits = replay.RunBudget(**{cap: 1})
    with pytest.raises(replay.ReplayLimitExceeded) as caught:
        replay.chronological_replay(joined, budget=limits)
    assert caught.value.report["resource"] == resource
    assert caught.value.report["measured"] > caught.value.report["limit"]
    assert caught.value.report["status"] == "REFUSED_RESOURCE_LIMIT"


def test_compact_hash_only_rerun_and_single_vintage_cache_reuse():
    joined = join()
    extra = {**joined["records"][0], "forecast_id": "same-cutoff-other-ticker", "ticker": "BBB",
             "root_event": "UNKNOWN_DATE_TICKER:BBB"}
    joined["records"].append(extra)
    joined["qualifications"][policy.digest(extra)] = next(iter(joined["qualifications"].values()))
    normal = replay.chronological_replay(joined)
    compact = replay.chronological_replay(joined, hash_only=True)
    assert compact == {"artifact_hash": normal["artifact_hash"], "n_decisions": len(normal["decisions"])}
    assert normal["cache_hits"] == 1
    assert all("admitted" not in v and "qualifications" not in v for v in normal["weight_artifacts"].values())
    assert all("view" not in d["variants"]["adaptive"] for d in normal["decisions"])


def test_future_same_component_mechanism_preserves_every_earlier_decision_and_hash():
    rows, prices, _ = fixture()
    for row in rows:
        row["mechanism_id"] = "earlier_recorded_mechanism"
    before_join = join(rows=rows)
    before = replay.chronological_replay(before_join)
    future = copy.deepcopy(rows[-1])
    entry, exit_ = pd.Timestamp("2025-02-20"), pd.Timestamp("2025-02-21")
    value = float(prices.loc[exit_, "AAA"]/prices.loc[entry, "AAA"]-1)
    future.update(prediction_id="zz-future-same-component", mechanism_id="later_different_mechanism",
        made_at="2025-02-20T14:00:00Z", resolves_after="2025-02-24", resolved_at_date_only="2025-02-26",
        source_full_row_sha256=policy.digest({"future-original-row": 1}),
        immutable_record_hash=policy.digest({"future-original-identity": 1}),
        outcome=int(value > 0), probability=.8 if value > 0 else .2,
        resolution_numeric={"realised_return": value, "vs_benchmark": value, "benchmark_return": 0})
    after_join = join(rows=rows+[future])
    assert after_join["definitions"] == before_join["definitions"]
    assert len(after_join["definitions"]) == 1
    assert after_join["records"][-1]["original_mechanism_id"] == "later_different_mechanism"
    assert all(r["original_mechanism_id"] == "earlier_recorded_mechanism" for r in after_join["records"][:-1])
    assert after_join["qualifications"][policy.digest(after_join["records"][-1])]["original_mechanism_id"] == "later_different_mechanism"
    after = replay.chronological_replay(after_join)
    assert after["decisions"][:-1] == before["decisions"]
    assert after["decision_hashes"][:-1] == before["decision_hashes"]
    assert {k: after["weight_artifacts"][k] for k in before["weight_artifacts"]} == before["weight_artifacts"]
    assert [d["variants"]["adaptive"]["forecast_artifact_hash"] for d in after["decisions"][:-1]] == [
        d["variants"]["adaptive"]["forecast_artifact_hash"] for d in before["decisions"]]


def test_terminal_state_reporting_requires_external_exact_metadata_supplement():
    score = replay.original_forward({"graded_projection_private": [], "unresolved_compact_private": [],
        "protected_stream_gate": {"counts": {"invalid_terminal_rows": 5}}})
    assert "pending_original_bool_terminal_types" not in score
    assert "UNKNOWN" in score["pending_original_terminal_states"]
    assert score["original_projection_gate_counts"]["invalid_terminal_rows"] == 5
