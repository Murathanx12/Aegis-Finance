"""Deterministic fixtures, not real performance evidence or broker tests."""
import copy

import pandas as pd
import pytest
import exchange_calendars as xcals

from backend.services import beta_v1_policy as beta
from backend.services import expected_return as er


DEFINITIONS = {
    "ranker": {"source_family": "numerical", "model_version": "fixture-v1",
               "prompt_version": "none", "correlation_group": "numerical"},
    "news": {"source_family": "news", "model_version": "fixture-v1",
             "prompt_version": "none", "correlation_group": "news"},
    "analyst": {"source_family": "analyst", "model_version": "fixture-v1",
                "prompt_version": "none", "correlation_group": "analyst"},
    "magnitude": {"source_family": "magnitude", "model_version": "fixture-v1",
                  "prompt_version": "none", "correlation_group": "magnitude"},
}


def qualify(rows):
    return {beta.digest(r): {"source_hash": r["source_hash"],
        "source_ref": "fixture://immutable-records", "adapter_version": "fixture-adapter-v1",
        "qualification_reason": "synthetic fixture with verified clocks and target semantics"}
        for r in rows}


def evidence():
    rows = []
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2025-01-02", "2025-05-01")
    for i in range(16):
        start = calendar.session_close(sessions[i*3])
        end = calendar.session_close(sessions[i*3+1])
        day = start-pd.Timedelta(hours=6)
        y = (-1 if i % 2 else 1) * (0.01+i/1000)
        for c in ("ranker", "news"):
            rows.append({"forecast_id": f"{c}-{i}", "component": c, "ticker": "AAA",
                "root_event": f"event-{i}", "forecast_at": day.isoformat(),
                "available_at": (day-pd.Timedelta(hours=1)).isoformat(),
                "label_start_at": start.isoformat(), "label_end_at": end.isoformat(),
                "valid_until_at": start.isoformat(), "calendar": "XNYS",
                "window_contract": "session_close_to_close",
                "outcome_at": (end+pd.Timedelta(hours=1)).isoformat(),
                "x": y if c == "ranker" else -y, "y": y,
                "task": "expected_excess_return", "horizon": 1,
                "objective_version": "excess-cost-v1", "model_version": "fixture-v1",
                "prompt_version": "none", "source_hash": beta.digest({"source": i, "c": c})})
    return rows


def fit(rows=None, **changes):
    rows = evidence() if rows is None else rows
    args = dict(qualifications=qualify(rows), definitions=DEFINITIONS,
                cutoff="2025-06-01T00:00:00Z", task="expected_excess_return", horizon=1,
                objective_version="excess-cost-v1", min_blocks=2)
    args.update(changes)
    return beta.fit(rows, **args)


def fresh(ticker="AAA", component="ranker", x=.03):
    row = evidence()[0].copy()
    row.update(forecast_id=f"current-{ticker}-{component}", root_event=f"current-{ticker}",
        ticker=ticker, component=component, x=x, forecast_at="2025-06-02T14:00:00Z",
        available_at="2025-06-02T13:00:00Z", label_start_at="2025-06-02T20:00:00Z",
        label_end_at="2025-06-03T20:00:00Z", valid_until_at="2025-06-02T20:00:00Z")
    for k in ("y", "outcome_at"):
        row.pop(k)
    return row


def test_maturity_features_and_qualification_are_bound_to_record_hash():
    rows = evidence()
    late = copy.deepcopy(rows[0])
    late.update(forecast_id="future-outcome", root_event="future-outcome",
                outcome_at="2026-01-01T00:00:00Z")
    late_feature = copy.deepcopy(rows[1])
    late_feature.update(forecast_id="late-feature", root_event="late-feature",
                        available_at="2025-08-01T00:00:00Z")
    base = fit(rows)
    artifact = fit(rows+[late, late_feature])
    assert artifact["weights"] == base["weights"]
    assert len(artifact["rejected"]) == 2
    tampered = copy.deepcopy(rows)
    tampered[0]["x"] = .5
    artifact = fit(tampered, qualifications=qualify(rows))
    assert any("exact record hash" in r["reason"] for r in artifact["rejected"])


def test_event_dedup_conflict_quarantine_and_input_order_idempotence():
    rows = evidence()
    artifact = fit(rows+rows)
    assert artifact["weights"] == fit(rows)["weights"]
    assert artifact["duplicate_count"] == len(rows)
    assert fit(rows) == fit(list(reversed(rows)))
    conflict = copy.deepcopy(rows[0])
    conflict.update(forecast_id="duplicate-story", x=.25)
    artifact = fit(rows+[conflict])
    assert artifact["quarantine_count"] == 2
    assert len(artifact["rejected"]) == 2


def test_chronological_label_purge_changes_training_baseline():
    rows = evidence()
    # Earlier forecast, but label resolves during the held-out half: must not
    # enter its probability baseline even though mature at final fit cutoff.
    for row in rows:
        row.update(task="beats_benchmark", x=.9 if row["y"] > 0 else .1,
                   y=1 if row["y"] > 0 else 0)
    original = fit(rows, task="beats_benchmark")
    delayed = copy.deepcopy(rows)
    delayed[0].update(outcome_at=delayed[-1]["outcome_at"])
    artifact = fit(delayed, task="beats_benchmark")
    assert artifact["components"]["ranker"]["n_train"] == original["components"]["ranker"]["n_train"]-1
    assert artifact["components"]["ranker"]["purged_train_rows"] == 1
    assert artifact["components"]["ranker"]["baseline_score"] != original["components"]["ranker"]["baseline_score"]


def test_weights_normalize_disable_unsupported_and_consumer_changes(tmp_path):
    artifact = fit()
    assert sum(artifact["weights"].values()) == pytest.approx(1)
    assert artifact["weights"]["ranker"] > artifact["weights"]["news"]
    assert artifact["weights"]["analyst"] == artifact["weights"]["magnitude"] == 0
    path = beta.save(artifact, tmp_path)
    assert beta.save(artifact, tmp_path) == path
    assert beta.load(path) == artifact
    rows = [fresh(x=.04), fresh(component="news", x=-.04)]
    kw = dict(qualifications=qualify(rows), asof="2025-06-02T15:00:00Z")
    adaptive = beta.forecast(artifact, rows, **kw)
    equal = beta.forecast(artifact, rows, variant="equal", **kw)
    no_news = beta.forecast(artifact, rows, variant="without_news", **kw)
    assert adaptive["forecasts"][0]["value"] > equal["forecasts"][0]["value"]
    assert no_news["forecasts"][0]["value"] == pytest.approx(.04)
    assert beta.forecast(beta.load(path), rows, **kw) == adaptive
    corrupt = copy.deepcopy(artifact)
    corrupt["weights"]["ranker"] = 0
    with pytest.raises(ValueError, match="hash mismatch"):
        beta.forecast(corrupt, rows, **kw)


def test_exact_tasks_horizons_and_future_vintage():
    artifact = fit()
    wrong = fresh(component="magnitude", x=.95)
    wrong["task"] = "abs_move_exceeds"
    analyst = fresh(component="analyst", x=.5)
    analyst["horizon"] = 252
    rows = [wrong, analyst]
    view = beta.forecast(artifact, rows, qualifications=qualify(rows), asof="2025-06-02T15:00:00Z")
    assert not view["forecasts"] and len(view["rejected"]) == 2
    with pytest.raises(ValueError, match="future weight"):
        beta.forecast(artifact, [], qualifications={}, asof="2025-05-01T00:00:00Z")


def test_equal_fallback_and_thin_priors_are_explicit():
    artifact = fit([])
    rows = [fresh(x=-.04), fresh(component="news", x=.02)]
    view = beta.forecast(artifact, rows, qualifications=qualify(rows), asof="2025-06-02T15:00:00Z")
    assert view["forecasts"][0]["equal_fallback"] is True
    assert view["forecasts"][0]["value"] == pytest.approx(-.01)
    prior = fit(evidence()[:4])
    assert prior["components"]["ranker"]["status"] == "SHRUNK_PRIOR"
    assert prior["weights"]["ranker"] == prior["weights"]["news"] == .5


def test_plan_consumes_forecast_preserves_cash_caps_and_refuses_prices():
    artifact = fit()
    rows = [fresh(x=.04), fresh(component="news", x=-.04), fresh("BBB", x=.01),
            fresh("SPY", x=.5), fresh("BAD", x=.03)]
    kw = dict(qualifications=qualify(rows), asof="2025-06-02T15:00:00Z")
    view = beta.forecast(artifact, rows, **kw)
    instruments = {t: dict(venue="NYSE", currency="USD", issuer=t, price=10,
        price_at="2025-06-02T14:30:00Z", source_ref="fixture://quotes", source_hash="a"*64,
        admissible=True, liquid=True, qualification_reason="fixture admissibility") for t in
        ("AAA", "BBB", "SPY", "BAD")}
    instruments["BAD"]["price"] = 0
    plan_args = dict(instruments=instruments, equity=10000, issuer_cap=.3,
                     cash_floor=.2, max_names=3, round_trip_cost=.001)
    plan = beta.paper_plan_preview(view, **plan_args)
    assert plan["weight_artifact_hash"] == artifact["artifact_hash"]
    assert plan["cash_weight"] >= .2
    assert all(h["weight"] <= .3 for h in plan["holdings"])
    assert all(h["ticker"] not in ("SPY", "BAD") for h in plan["holdings"])
    equal = beta.forecast(artifact, rows, variant="equal", **kw)
    equal_plan = beta.paper_plan_preview(equal, **plan_args)
    assert [h["ticker"] for h in plan["holdings"]] != [h["ticker"] for h in equal_plan["holdings"]]
    assert beta.paper_plan_preview(view, **plan_args) == plan


def test_legacy_blend_default_is_preserved():
    table = pd.DataFrame({"graded": [False]*len(er.COMPONENTS)}, index=er.COMPONENTS)
    view = er.blend({"ranker": .04, "revision_flow": -.02}, table)
    assert view["er_reputation"] == pytest.approx(.01)
    assert view["weights_reputation"] == {"ranker": .5, "revision_flow": .5}


def test_learned_zero_only_awake_abstains_equal_is_separate():
    artifact = fit()
    rows = [fresh(component="news", x=.08)]
    kw = dict(qualifications=qualify(rows), asof="2025-06-02T15:00:00Z")
    adaptive = beta.forecast(artifact, rows, **kw)["forecasts"][0]
    assert artifact["components"]["news"]["status"] == "LEARNED"
    assert adaptive["value"] is None
    assert adaptive["effective_weights"]["news"] == 0
    assert adaptive["equal_fallback"] is False
    assert beta.forecast(artifact, rows, variant="equal", **kw)["forecasts"][0]["value"] == .08


def test_actual_long_labels_and_holiday_off_by_one_are_rejected():
    rows = evidence()
    for r in rows:
        r["label_end_at"] = "2026-06-01T20:00:00Z"
        r["outcome_at"] = "2026-06-01T21:00:00Z"
    artifact = fit(rows, cutoff="2026-06-02T00:00:00Z")
    assert len(artifact["rejected"]) == len(rows)
    assert artifact["components"]["ranker"]["heldout_independent_blocks"] == 0
    r = evidence()[0].copy()
    # MLK Monday is not an XNYS session: Friday->Tuesday is one session.
    r.update(forecast_at="2025-01-17T14:00:00Z", available_at="2025-01-17T13:00:00Z",
        label_start_at="2025-01-17T21:00:00Z", label_end_at="2025-01-21T21:00:00Z",
        valid_until_at="2025-01-17T21:00:00Z", outcome_at="2025-01-21T22:00:00Z")
    assert fit([r])["components"]["ranker"]["n_rows"] == 1
    r["label_end_at"] = "2025-01-20T21:00:00Z"
    assert len(fit([r])["rejected"]) == 1


def test_expiry_future_entry_and_forecast_provenance():
    artifact = fit()
    old = evidence()[0]
    view = beta.forecast(artifact, [old], qualifications=qualify([old]), asof="2025-06-02T15:00:00Z")
    assert not view["forecasts"] and "expired" in view["rejected"][0]["reason"]
    row = fresh()
    kw = dict(qualifications=qualify([row]))
    accepted = beta.forecast(artifact, [row], asof="2025-06-02T20:00:00Z", **kw)
    assert accepted["forecasts"][0]["consumed_forecasts"][0]["valid_until_at"] == row["valid_until_at"]
    assert not beta.forecast(artifact, [row], asof="2025-06-02T20:00:01Z", **kw)["forecasts"]
    assert not beta.forecast(artifact, [row], asof="2025-06-02T13:59:59Z", **kw)["forecasts"]


def test_shrink_strength_and_n_compete_with_prior_without_cancellation(monkeypatch):
    rows = [r for r in evidence() if r["component"] == "ranker"] + evidence()[1:2]
    monkeypatch.setattr(beta, "_return_ic", lambda blocks: .00001)
    tiny = fit(rows)
    assert 0 < tiny["weights"]["ranker"] < .001
    monkeypatch.setattr(beta, "_return_ic", lambda blocks: .1)
    stronger = fit(rows)
    assert stronger["weights"]["ranker"] > tiny["weights"]["ranker"]
    fewer = fit(rows[:8]+rows[-1:])
    assert fewer["weights"]["ranker"] < stronger["weights"]["ranker"]
    assert tiny["components"]["ranker"]["raw_shrunk_score"] < .00001


def test_unavailable_and_admitted_correlation_clones_do_not_inflate_group():
    rows = evidence()[:4]
    base = fit(rows)
    defs = copy.deepcopy(DEFINITIONS)
    defs["clone"] = copy.deepcopy(DEFINITIONS["ranker"])
    absent = fit(rows, definitions=defs)
    assert absent["weights"]["ranker"] == base["weights"]["ranker"]
    assert absent["weights"]["news"] == base["weights"]["news"]
    clones = [{**r, "component": "clone", "forecast_id": "clone-"+r["forecast_id"]}
              for r in rows if r["component"] == "ranker"]
    admitted = fit(rows+clones, definitions=defs)
    assert admitted["weights"]["ranker"]+admitted["weights"]["clone"] == base["weights"]["ranker"]
    assert admitted["weights"]["news"] == base["weights"]["news"]


@pytest.mark.parametrize("task", ["expected_excess_return", "beats_benchmark"])
def test_cold_prior_group_budget_clone_reload_and_reversal(task, tmp_path):
    definitions = copy.deepcopy(DEFINITIONS)
    definitions["clone"] = copy.deepcopy(definitions["ranker"])
    base = fit([], task=task)
    artifact = fit([], definitions=definitions, task=task)
    values = (.04, -.02) if task == "expected_excess_return" else (.8, .2)
    rows = [fresh(x=values[0]), fresh(component="news", x=values[1])]
    for r in rows:
        r["task"] = task
    clone = {**rows[0], "component": "clone", "forecast_id": "clone-current"}
    kwargs = dict(asof="2025-06-02T15:00:00Z")
    before = beta.forecast(base, rows, qualifications=qualify(rows), **kwargs)
    after = beta.forecast(artifact, rows+[clone], qualifications=qualify(rows+[clone]), **kwargs)
    b, a = before["forecasts"][0], after["forecasts"][0]
    assert a["value"] == pytest.approx(b["value"])
    assert a["effective_weights"]["ranker"]+a["effective_weights"]["clone"] == .5
    assert a["effective_weights"]["news"] == .5
    loaded = beta.load(beta.save(artifact, tmp_path))
    assert beta.forecast(loaded, list(reversed(rows+[clone])), qualifications=qualify(rows+[clone]), **kwargs) == after
    if task == "expected_excess_return":
        plan_args = _plan_args()
        old_plan, new_plan = beta.paper_plan_preview(before, **plan_args), beta.paper_plan_preview(after, **plan_args)
        assert [h["ticker"] for h in old_plan["holdings"]] == [h["ticker"] for h in new_plan["holdings"]]
        for before_holding, after_holding in zip(old_plan["holdings"], new_plan["holdings"]):
            for key in ("weight", "notional", "score_after_cost"):
                assert before_holding[key] == pytest.approx(after_holding[key])


def test_learned_zero_remains_zero_in_grouped_prior_fallback():
    artifact = fit()
    definitions = copy.deepcopy(DEFINITIONS)
    definitions["clone"] = copy.deepcopy(definitions["analyst"])
    artifact = fit(definitions=definitions)
    rows = [fresh(component="analyst", x=.04), fresh(component="clone", x=.04),
            fresh(component="magnitude", x=-.04), fresh(component="news", x=.08)]
    output = beta.forecast(artifact, rows, qualifications=qualify(rows),
                           asof="2025-06-02T15:00:00Z")["forecasts"][0]
    assert output["equal_fallback"] is True
    assert output["effective_weights"]["news"] == 0
    assert output["effective_weights"]["analyst"]+output["effective_weights"]["clone"] == .5
    assert output["effective_weights"]["magnitude"] == .5


@pytest.mark.parametrize("task", ["expected_excess_return", "beats_benchmark"])
@pytest.mark.parametrize("variant", ["adaptive", "equal", "without_news", "without_analyst"])
def test_common_exact_window_frozen_across_variants_and_universe(task, variant):
    artifact = fit([], task=task)
    first, other = fresh(x=.04), fresh(component="news", x=.08)
    for r in (first, other):
        r["task"] = task
    other.update(label_start_at="2025-06-03T20:00:00Z", label_end_at="2025-06-04T20:00:00Z")
    rows = [first, other]
    args = dict(qualifications=qualify(rows), asof="2025-06-02T15:00:00Z", variant=variant)
    view = beta.forecast(artifact, rows, **args)
    assert not view["forecasts"]
    assert view["target_contract"] is None
    assert len(view["rejected"]) == 2
    assert beta.forecast(artifact, list(reversed(rows)), **args) == view
    # Same exact mismatch across tickers must not create a ranked cohort either.
    other["ticker"] = "BBB"
    view = beta.forecast(artifact, rows, qualifications=qualify(rows), asof=args["asof"], variant=variant)
    assert not view["forecasts"]


def test_matching_common_contract_hashes_and_scheduled_entry(tmp_path):
    artifact = fit([])
    rows = [fresh(), fresh(component="news", x=.02)]
    args = dict(qualifications=qualify(rows), asof="2025-06-02T15:00:00Z")
    view = beta.forecast(artifact, rows, **args)
    assert view["target_contract_hash"] == beta.digest(view["target_contract"])
    assert view["forecasts"][0]["target_contract"] == view["target_contract"]
    assert view["forecasts"][0]["target_contract_hash"] == view["target_contract_hash"]
    assert view["target_contract"]["label_start_at"] == "2025-06-02T20:00:00+00:00"
    assert beta.forecast(beta.load(beta.save(artifact, tmp_path)), rows, **args) == view
    for r in rows:
        r.update(label_start_at="2025-06-03T20:00:00Z", label_end_at="2025-06-04T20:00:00Z")
    args["qualifications"] = qualify(rows)
    assert not beta.forecast(artifact, rows, **args)["forecasts"]
    scheduled = beta.forecast(artifact, rows, scheduled_entry_at="2025-06-03T20:00:00Z", **args)
    assert len(scheduled["forecasts"]) == 1
    assert scheduled["target_contract"]["scheduled_entry_at"] == "2025-06-03T20:00:00+00:00"


def _plan_args():
    return dict(instruments={"AAA": dict(venue="NYSE", currency="USD", issuer="AAA", price=10,
        price_at="2025-06-02T14:30:00Z", source_ref="fixture://quotes", source_hash="a"*64,
        admissible=True, liquid=True, qualification_reason="fixture admissibility")},
        equity=10000, issuer_cap=.3, cash_floor=.2, max_names=3, round_trip_cost=.001)


def test_plan_carries_common_contract_and_rejects_forged_mixed_cohort():
    artifact = fit([])
    rows = [fresh(), fresh(component="news", x=.02)]
    view = beta.forecast(artifact, rows, qualifications=qualify(rows), asof="2025-06-02T15:00:00Z")
    plan = beta.paper_plan_preview(view, **_plan_args())
    assert plan["target_contract"] == view["target_contract"]
    assert plan["target_contract_hash"] == view["target_contract_hash"]
    altered = copy.deepcopy(view)
    altered["forecasts"][0]["consumed_forecasts"][1]["label_end_at"] = "2025-06-04T20:00:00Z"
    altered.pop("artifact_hash")
    altered = beta._seal(altered)
    with pytest.raises(ValueError, match="common plan target"):
        beta.paper_plan_preview(altered, **_plan_args())
    mismatched = copy.deepcopy(rows)
    mismatched[1].update(label_start_at="2025-06-03T20:00:00Z", label_end_at="2025-06-04T20:00:00Z")
    rejected = beta.forecast(artifact, mismatched, qualifications=qualify(mismatched), asof=view["asof"])
    assert not beta.paper_plan_preview(rejected, **_plan_args())["holdings"]
