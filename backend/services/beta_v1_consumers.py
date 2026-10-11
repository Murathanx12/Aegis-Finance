"""Separated retrospective probability/return consumers and inactive H21 draft.

Injected reviewed artifacts only. No runtime discovery, models, broker or NAV.
H5 return calibration reuses the existing past-only ER adapter; it never turns
an H1 probability, magnitude or 12-month analyst target into a return forecast.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backend.services import beta_v1_policy as policy
from backend.services import beta_v1_replay as replay

VERSION = "beta_v1_consumers/2"


def _seal(value):
    return {**value, "artifact_hash": policy.digest(value)}


def separated_probability_metrics(replay_result: dict) -> dict:
    """Report identical-question pairs by exact semantic target, never pooled H."""
    cells = defaultdict(list)
    for decision in replay_result["paired_replay"]["decisions"]:
        if "variants" not in decision:
            continue
        cells[(decision["task"], decision["horizon"], decision["objective_version"],
               decision.get("costs_charged"), decision.get("cost_rate_bps"))].append(decision)
    results = []
    for key, rows in sorted(cells.items(), key=lambda item: str(item[0])):
        metrics = []
        for variant in replay.GRID:
            paired = [r for r in rows if r["variants"].get(variant, {}).get("brier") is not None
                      and r["variants"].get("equal", {}).get("brier") is not None]
            metrics.append({"variant": variant, "n_same_question_pairs": len(paired),
                "n_abstain_or_unavailable": len(rows)-len(paired),
                "mean_brier": float(np.mean([r["variants"][variant]["brier"] for r in paired])) if paired else None,
                "mean_log_loss": float(np.mean([r["variants"][variant]["log_loss"] for r in paired])) if paired else None,
                "brier_difference_vs_equal": float(np.mean([r["variants"][variant]["brier"]-
                    r["variants"]["equal"]["brier"] for r in paired])) if paired else None,
                "status": "RETROSPECTIVE_PROPER_LOSS" if paired else "UNAVAILABLE",
                "interpretation": "abstention is missing, never p=0; without_analyst identity alone does not prove analyst consumption"})
        results.append({"task": key[0], "horizon": key[1], "objective_version": key[2],
            "benchmark_contract": key[2], "original_costs_charged": key[3], "original_cost_rate_bps": key[4],
            "n_questions": len(rows), "n_dates": len({r["decision_at"][:10] for r in rows}), "variants": metrics})
    return _seal({"schema": VERSION, "lane": "SEPARATED_PROBABILITY_REPLAY", "contracts": results,
        "source_replay_artifact_hash": replay_result["artifact_hash"],
        "pooled_cross_horizon_metrics": "DISABLED", "claim": "proper losses, not portfolio return/fill evidence"})


def _mandate(protocol):
    mandate = protocol["portfolio_preview_mandate"]
    if mandate.get("equity") != "Normalized unit; no account balance or fills invented":
        raise ValueError("normalized declared mandate required")
    return {"equity": 1.0, "issuer_cap": mandate["issuer_cap"], "cash_floor": mandate["cash_floor"],
        "max_names": mandate["max_names"], "round_trip_cost": protocol["new_simulated_costs"]["round_trip_bps"]/10000}


def derived_h5_return_trace(replay_result: dict, protocol: dict, *, budget=None, artifact_sink=None) -> dict:
    """Actual prior-trained H5 expected price-excess forecasts; no executed book.

    Every derived historical x has its own earlier calibration vintage. The
    price-excess labels are gross arithmetic from the original grader, despite
    any original cost flags. Newly proposed equity scores charge frozen cost
    once; original probabilities and grades are never rewritten.
    """
    budget = budget or replay.RunBudget()
    joined = replay_result["join"]
    originals = sorted({policy.digest(r): r for r in joined["records"]
                        if r["task"] == "beats_benchmark" and r["horizon"] == 5}.values(),
                       key=lambda r: (r["forecast_at"], r["forecast_id"]))
    budget.check("H5 consumer input", records=len(originals))
    derived, qualifications, definitions, unavailable, derivations = [], {}, {}, [], {}
    algorithm_hash = hashlib.sha256(Path(replay.__file__).read_bytes()).hexdigest()
    for original in originals:
        budget.check("past-only H5 calibration")
        cutoff = pd.Timestamp(original["forecast_at"])
        # Future rows cannot create a conflicting root or alter the roster at
        # an earlier decision. Admission must precede ER bin support/counts.
        past = [r for r in originals if r["objective_version"] == original["objective_version"]
                and pd.Timestamp(r["forecast_at"]) <= cutoff
                and pd.Timestamp(r["outcome_at"]) <= cutoff]
        admitted, excluded, _ = policy._admit(past, joined["qualifications"],
            definitions=joined["definitions"], task="beats_benchmark", horizon=5,
            objective_version=original["objective_version"], cutoff=cutoff, grade=True)
        by_hash = {policy.digest(r): r for r in past}
        training = [by_hash[r["record_hash"]] for r in admitted]
        outputs, provenance = replay.calibrated_return_inputs({**joined, "records": training},
            [original], cutoff=original["forecast_at"])
        unavailable.extend({**entry, "calibration_admission": {
            "accepted_root_cells": len(admitted), "exclusions": excluded}}
            for entry in provenance["unavailable"])
        if not outputs:
            continue
        output = outputs[0]
        calibration = provenance["available"][policy.digest(output)]
        calibration = {**calibration, "admission": {
            "method": "frozen policy._admit before calibration; exact semantic cell and mature cutoff",
            "accepted_root_cells": len(admitted), "accepted_dates": len({r["forecast_at"][:10] for r in training}),
            "root_independence": "UNKNOWN_DEPENDENCY_CELLS" if any(r.get("root_independence") == "UNKNOWN" for r in training) else "DECLARED_ROOTS",
            "exclusions": excluded}}
        component = "calibrated_return:"+original["component"]
        definition = {**joined["definitions"][original["component"]],
            "model_version": "ER_CALIBRATION:"+algorithm_hash+":"+original["model_version"]}
        record = {**output, "component": component, "model_version": definition["model_version"],
            "derivation": calibration, "original_probability_record_hash": policy.digest(original),
            "return_cost_basis": "GROSS_NATIVE_PRICE_CLOSE_EXCESS", "price_adjustment_status": "UNKNOWN"}
        definitions[component] = definition
        q = {**joined["qualifications"][policy.digest(original)],
            "adapter_version": VERSION, "qualification_reason":
                "retrospective H5 numerical calibration of archived probability; every training outcome observable before decision; "
                "gross native price-close excess; source interpretation/adjustment remain UNKNOWN",
            "calibration_hash": calibration["calibration_hash"], "calibration_cutoff": original["forecast_at"],
            "training_record_hashes": calibration["training_record_hashes"],
            "original_probability_record_hash": policy.digest(original), "return_cost_basis": record["return_cost_basis"]}
        qualifications[policy.digest(record)] = q
        derivations[policy.digest(record)] = calibration
        derived.append(record)
    cohorts = defaultdict(list)
    for record in derived:
        cohorts[(record["forecast_at"], record["objective_version"], record["label_start_at"],
                 record["label_end_at"], record["ticker"])].append(record)
    traces, vintage_index, artifact_bytes = [], {}, 0
    for key, current in sorted(cohorts.items()):
        budget.check("H5 return decision", cohorts=len(traces)+1)
        available = [r for r in derived if r["objective_version"] == key[1] and pd.Timestamp(r["forecast_at"]) <= pd.Timestamp(key[0])]
        past = [r for r in available if pd.Timestamp(r["outcome_at"]) <= pd.Timestamp(key[0])]
        defs = {c: definitions[c] for c in sorted({r["component"] for r in available})}
        prior = any(r["root_independence"] == "UNKNOWN" for r in available)
        vintage = policy.fit(past, qualifications={policy.digest(r): qualifications[policy.digest(r)] for r in past},
            definitions=defs, cutoff=key[0], task="expected_excess_return", horizon=5, objective_version=key[1],
            min_blocks=replay.PRIOR_ONLY_MIN_BLOCKS if prior else 30)
        if vintage["artifact_hash"] not in vintage_index:
            artifact_bytes += replay.json_bytes(vintage)
            budget.check("H5 vintage storage", vintages=len(vintage_index)+1, artifact_bytes=artifact_bytes)
            reference = artifact_sink(vintage) if artifact_sink else None
            vintage_index[vintage["artifact_hash"]] = {"reference": reference, "cutoff": key[0],
                "weights": vintage["weights"], "parameters": vintage["parameters"],
                "root_independence": "UNKNOWN_DEPENDENCY_CELLS" if prior else "DECLARED_ROOTS",
                "components": {c: {k: a[k] for k in ("status", "n_rows", "n_dates", "n_root_events",
                    "heldout_independent_blocks", "skill", "effective_weight", "raw_shrunk_score", "prior",
                    "allocated_mass", "admissibility_multiplier", "latest_outcome_at")} for c, a in vintage["components"].items()}}
        variants = {}
        for variant in replay.GRID[2:]:
            budget.check("H5 return consumer")
            forecast = policy.forecast(vintage, current,
                qualifications={policy.digest(r): qualifications[policy.digest(r)] for r in current}, asof=key[0], variant=variant,
                scheduled_entry_at=key[2] if pd.Timestamp(key[2]).date() != pd.Timestamp(key[0]).date() else None)
            # Historical issuer/security/venue/liquidity metadata is not in this
            # authorized source. This must refuse holdings, even when x > 0.
            plan = policy.paper_plan_preview(forecast, instruments={}, **_mandate(protocol))
            variants[variant] = {"forecast": forecast, "plan": plan,
                "weight_artifact_hash": vintage["artifact_hash"], "cost_once_round_trip_bps": protocol["new_simulated_costs"]["round_trip_bps"]}
        traces.append({"decision_at": key[0], "objective_version": key[1], "horizon": 5,
            "ticker": key[4], "label_start_at": key[2], "label_end_at": key[3],
            "derived_record_hashes": sorted(policy.digest(r) for r in current), "variants": variants})
    result = {"schema": VERSION, "lane": "RETROSPECTIVE_DERIVED_H5_EXPECTED_RETURN", "horizon": 5,
        "source_replay_artifact_hash": replay_result["artifact_hash"], "original_h5_rows": len(originals),
        "derived_rows": len(derived), "unavailable": unavailable, "derivations": derivations,
        "qualified_derived_records": derived, "qualification_manifest": qualifications,
        "vintages": vintage_index, "traces": traces,
        "excluded_horizons": "H1 and H21 are not converted to H5; H5 does not replace primary H21",
        "price_basis": "PRICE_RETURN_NOT_TOTAL_RETURN; native corporate-action/adjustment UNKNOWN",
        "original_costs": "preserved unchanged in source; new return arithmetic is explicit gross close-excess",
        "executed_return_metrics": "UNAVAILABLE: no qualified historical instruments or fills",
        "full_qualifications_hash": policy.digest(qualifications)}
    budget.check("H5 result output", output_bytes=replay.json_bytes(result))
    return _seal(result)




def _current_decision_status(forecast, instruments, plan, *, horizon, input_count, candidate_count):
    """Describe evidence admission separately from residual preview arithmetic.

    Use the actual frozen planner's outcomes to classify instrument admission;
    no second price/risk engine or missing-return-to-zero conversion is added.
    """
    valid = {r["ticker"] for r in forecast["forecasts"]
        if r.get("task") == "expected_excess_return" and r.get("horizon") == horizon
        and r.get("consumed_forecasts") and not isinstance(r.get("value"), bool)
        and isinstance(r.get("value"), (int, float)) and np.isfinite(r["value"])}
    for row in plan["holdings"]:
        weight = row.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not np.isfinite(weight) or weight < 0:
            raise ValueError("invalid planner holding weight; no decision status can be certified")
    positive_holdings = [r for r in plan["holdings"] if r["weight"] > 0]
    # Keep all valid selected rows as instrument-admission evidence, including
    # zero-weight rows caused by mandate/issuer caps. Exposure counts only >0.
    held = {r["ticker"] for r in plan["holdings"]}
    refused = defaultdict(set)
    for row in plan["refusals"]:
        refused[row["ticker"]].add(row["reason"])
    economic_reasons = {"nonpositive expected excess after cost", "below selected rank cutoff"}
    admitted = {ticker for ticker in valid if ticker in instruments and
        (ticker in held or (refused[ticker] and refused[ticker] <= economic_reasons))}
    counts = {"provided_return_records": input_count, "candidate_rows": candidate_count,
        "valid_admitted_return_forecast_tickers": len(valid),
        "consumer_screened_instrument_tickers": len(instruments),
        "planner_admitted_instrument_tickers": len(admitted),
        "valid_forecast_tickers_without_admitted_instruments": len(valid-admitted),
        "proposed_holdings": len(positive_holdings),
        "partial_admitted_universe": len(admitted) < len(valid) or len(valid) < candidate_count}
    if positive_holdings:
        decision, reason = "INACTIVE_PROPOSED_ONLY", "Qualified forecasts and instruments produced inactive proposed holdings."
    elif not valid:
        decision, reason = "RETURN_INPUTS_UNAVAILABLE", "No finite qualified same-task/horizon return forecasts admitted; missing returns are unavailable, not zero or an investment cash decision."
    elif not admitted:
        decision, reason = "INSTRUMENT_INPUTS_UNAVAILABLE", "Valid return forecasts exist, but no instruments pass the unchanged source/price/liquidity/mandate gates; no investment cash decision."
    else:
        decision, reason = "CASH_100_PERCENT", "Within the explicitly admitted preview subset, the engine chose no positive exposure under the declared mandate/costs/signals; excluded candidates are unavailable, not zero."
    return {"decision": decision, "decision_reason": reason, "decision_counts": counts,
        "investment_cash_decision": decision == "CASH_100_PERCENT",
        "plan_cash_weight_interpretation": "Unallocated inactive-preview arithmetic; no investment cash decision when inputs are unavailable."}


def _qualified_current_vintage(artifact, qualification, *, definitions, objective, horizon, asof):
    """Admit an explicitly supplied, independently reviewed weight vintage.

    This is an offline caller contract, not a claim that a hash authenticates a
    reviewer. The caller supplies the independent qualification; this function
    binds it to the exact vintage and refuses incompatible or future evidence.
    It never discovers files, fits on current outcomes, or converts units.
    """
    if not isinstance(artifact, dict) or not isinstance(qualification, dict):
        raise ValueError("explicit weight artifact and independent qualification required")
    policy.verify_artifact(artifact)
    if qualification.get("schema") != "beta_v1_weight_qualification/1" or qualification.get("verdict") != "PASS_INDEPENDENT_WEIGHT_VINTAGE":
        raise ValueError("unsupported weight qualification")
    if (qualification.get("source_hash_kind") != "CANONICAL_ARTIFACT_WITH_SEAL"
            or qualification.get("review_hash_kind") != "CANONICAL_REVIEW_JSON"):
        raise ValueError("explicit canonical hash domains required; no file-byte claim")
    if (qualification.get("artifact_hash") != artifact["artifact_hash"]
            or qualification.get("source_hash") != policy.digest(artifact)):
        raise ValueError("weight qualification does not bind exact artifact")
    for key in ("source_ref", "review_ref", "qualification_reason"):
        if not isinstance(qualification.get(key), str) or not qualification[key].strip():
            raise ValueError("weight source/review provenance unavailable")
    review_hash = qualification.get("review_sha256")
    if not isinstance(review_hash, str) or len(review_hash) != 64 or any(c not in "0123456789abcdef" for c in review_hash):
        raise ValueError("independent weight review hash unavailable")
    review = qualification.get("reviewed_vintage")
    if (not isinstance(review, dict) or review.get("schema") != "beta_v1_independent_weight_review/1"
            or review.get("verdict") != "PASS_SCOPED_WEIGHT_VINTAGE" or policy.digest(review) != review_hash):
        raise ValueError("exact independent reviewed-vintage receipt required")
    approved = {"artifact_hash": artifact["artifact_hash"], "source_hash": policy.digest(artifact),
        "definitions_hash": policy.digest(definitions), "weights_hash": policy.digest(artifact.get("weights")),
        "components_hash": policy.digest(artifact.get("components")), "parameters": artifact.get("parameters"),
        "code_hashes": artifact.get("code_hashes")}
    if any(review.get(k) != v for k, v in approved.items()):
        raise ValueError("weight vintage differs from independently reviewed fit")
    provenance = ("source_ref", "review_ref", "qualification_reason", "available_at",
                  "source_observed_at", "qualified_at", "valid_until_at", "freshness_rule")
    if any(qualification.get(k) != review.get(k) for k in provenance):
        raise ValueError("weight provenance differs from independent review")
    if qualification.get("freshness_rule") != "REVIEWED_VALID_UNTIL":
        raise ValueError("explicit reviewed weight freshness rule required")
    cutoff = policy._clock(artifact.get("cutoff"))
    available, observed, reviewed, decision = (policy._clock(value) for value in (
        qualification.get("available_at"), qualification.get("source_observed_at"),
        qualification.get("qualified_at"), asof))
    if not cutoff <= available <= observed <= reviewed <= decision:
        raise ValueError("weight vintage or independent qualification unavailable at decision")
    expires = policy._clock(qualification.get("valid_until_at"))
    if expires < reviewed or decision > expires:
        raise ValueError("independently reviewed weight vintage expired")
    if (artifact.get("mode") != "SHADOW_ONLY" or artifact.get("task") != "expected_excess_return"
            or artifact.get("horizon") != horizon or artifact.get("objective_version") != objective
            or artifact.get("definitions") != definitions):
        raise ValueError("exact current weight task/horizon/objective/definitions mismatch")
    expected_parameters = {"min_blocks": 30, "k_prior": 30.0, "gamma": 1.0,
                           "prior_share": 0.5, "embargo_sessions": horizon}
    parameters, components = artifact.get("parameters"), artifact.get("components")
    if not isinstance(parameters, dict) or not isinstance(components, dict) or not isinstance(artifact.get("weights"), dict):
        raise ValueError("weight parameters/components/mass must be objects")
    # Existing unknown-root replay vintages deliberately prohibit graduation.
    # Accept that stricter frozen branch without relaxing the normal k/minimum.
    if (parameters.get("min_blocks") == replay.PRIOR_ONLY_MIN_BLOCKS
            and all(isinstance(a, dict) and a.get("status") in {"SHRUNK_PRIOR", "UNAVAILABLE"}
                    for a in components.values())):
        expected_parameters["min_blocks"] = replay.PRIOR_ONLY_MIN_BLOCKS
    if (artifact.get("parameters") != expected_parameters
            or any(isinstance(v, bool) for v in artifact["parameters"].values())):
        raise ValueError("weight parameters differ from frozen Beta policy")
    current_code = {Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in (policy.__file__, policy.er.__file__, policy.fr.__file__, policy.kernels.__file__)}
    if artifact.get("code_hashes") != current_code:
        raise ValueError("weight constructor code differs from current reviewed fit")
    if set(artifact.get("weights", {})) != set(definitions) or set(artifact.get("components", {})) != set(definitions):
        raise ValueError("weight component support differs from definitions")
    mass = []
    for name, definition in definitions.items():
        value = artifact["weights"][name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value < 0:
            raise ValueError("invalid effective weight")
        mass.append(value)
        audit = artifact["components"][name]
        if not isinstance(audit, dict) or any(audit.get(k) != v for k, v in definition.items()):
            raise ValueError("weight audit definition mismatch")
        if (audit.get("task") != "expected_excess_return" or audit.get("horizon") != horizon
                or audit.get("objective_version") != objective or policy._clock(audit.get("training_cutoff")) != cutoff
                or audit.get("effective_weight") != value):
            raise ValueError("weight audit cell/cutoff/mass mismatch")
        for clock in (audit.get("latest_outcome_at"), *(audit.get("feature_availability_range") or [])):
            if clock is not None and policy._clock(clock) > cutoff:
                raise ValueError("future evidence inside weight vintage")
    total = sum(mass)
    if not (total == 0.0 or np.isclose(total, 1.0, rtol=0, atol=1e-12)):
        raise ValueError("effective weight mass is not normalized")
    # The returned preview must not alias a mutable caller vintage.
    return json.loads(json.dumps(artifact, allow_nan=False))


def current_draft(current: dict, protocol: dict, *, source_hash: str, horizon: int = 21,
                  weight_artifact: dict | None = None, weight_qualification: dict | None = None,
                  variant: str = "adaptive") -> dict:
    """An inactive preview; unavailable inputs are not a cash decision.

    Descriptive revision scores/analyst target upside are not return forecasts.
    Only externally qualified normalized return records can enter this route;
    this supplied descriptive artifact currently declares no such records.
    """
    if horizon not in (protocol["primary_portfolio_horizon_sessions"], protocol["separate_secondary_horizon_sessions"]):
        raise ValueError("undeclared horizon")
    records = current.get("qualified_return_records") or []
    qualifications = current.get("qualified_return_qualifications") or {}
    defs = current.get("qualified_return_definitions") or {
        "ranker": {"source_family": "numerical", "model_version": "ER_CURRENT_RETURN_UNAVAILABLE", "prompt_version": "none", "correlation_group": "numerical"},
        "revision_flow": {"source_family": "analyst", "model_version": "RF_CURRENT_RETURN_UNAVAILABLE", "prompt_version": "none", "correlation_group": "analyst"},
        "news": {"source_family": "news", "model_version": "QUALIFIED_CURRENT_NEWS_UNAVAILABLE", "prompt_version": "none", "correlation_group": "news"}}
    input_refusals = []
    eligible_records = []
    for r in records:
        if r.get("horizon") != horizon or r.get("task") != "expected_excess_return":
            input_refusals.append({"forecast_id": r.get("forecast_id"), "reason": "exact current task/horizon mismatch; no conversion"})
        elif r.get("return_cost_basis") != "GROSS_NATIVE_PRICE_CLOSE_EXCESS":
            input_refusals.append({"forecast_id": r.get("forecast_id"), "reason": "gross cost basis not qualified; net/unknown inputs excluded to prevent double charge"})
        else:
            eligible_records.append(r)
    records = eligible_records
    objective = "CURRENT_NATIVE_PRICE_EXCESS_H"+str(horizon)
    if records:
        objectives = {r["objective_version"] for r in records}
        if len(objectives) != 1:
            raise ValueError("mixed current return objectives")
        objective = next(iter(objectives))
    asof = current["asof_utc"]
    # No historical return evidence is fabricated from a descriptive score.
    if weight_artifact is None:
        if weight_qualification is not None:
            raise ValueError("weight qualification supplied without a weight artifact")
        vintage = policy.fit([], qualifications={}, definitions=defs, cutoff=asof,
            task="expected_excess_return", horizon=horizon, objective_version=objective)
    else:
        vintage = _qualified_current_vintage(weight_artifact, weight_qualification,
            definitions=defs, objective=objective, horizon=horizon, asof=asof)
        weight_qualification = json.loads(json.dumps(weight_qualification, allow_nan=False))
    forecast = policy.forecast(vintage, records, qualifications=qualifications, asof=asof,
        scheduled_entry_at=current.get("qualified_scheduled_entry_at"), variant=variant)
    instruments, rejected = {}, []
    mandate = protocol["portfolio_preview_mandate"]
    for row in current.get("records", []):
        reasons = []
        if row.get("ticker", "").upper() == "SPY":
            reasons.append("SPY control only")
        actual_forecast = next((f for f in forecast["forecasts"] if f["ticker"] == row.get("ticker")
                                and f.get("task") == "expected_excess_return" and f.get("horizon") == horizon
                                and f.get("value") is not None and f.get("consumed_forecasts")), None)
        if actual_forecast is None:
            reasons.append("qualified H"+str(horizon)+" expected return unavailable; revision score not converted")
        if not isinstance(row.get("issuer_identity"), dict) or not row["issuer_identity"].get("qualified"):
            reasons.append("issuer identity unavailable")
        if not isinstance(row.get("currency_identity"), dict) or not row["currency_identity"].get("qualified"):
            reasons.append("currency identity unavailable")
        if row.get("allocation_eligible") is not True:
            reasons.append("full security/venue/liquidity eligibility unavailable")
        # Instrument admission needs its own explicit qualified snapshot.
        snapshot = row.get("qualified_instrument_snapshot")
        if isinstance(snapshot, dict):
            try:
                for field, floor in (("price", mandate["minimum_price"]),
                        ("trailing20_median_dollar_volume", mandate["minimum_trailing20_median_dollar_volume"])):
                    value = snapshot.get(field)
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0 or value < floor:
                        raise ValueError("snapshot price/ADV floor unavailable or failed")
                observed = pd.Timestamp(snapshot["price_at"])
                if observed.tzinfo is None or observed > pd.Timestamp(asof) or (pd.Timestamp(asof)-observed).total_seconds() > 4*86400:
                    raise ValueError("snapshot price clock invalid/future/stale")
                adv_at = pd.Timestamp(snapshot["trailing20_median_dollar_volume_at"])
                if adv_at.tzinfo is None or adv_at != observed:
                    raise ValueError("snapshot ADV clock not bound to price snapshot")
                if not all(snapshot.get(k) for k in ("source_ref", "qualification_reason")) or not isinstance(snapshot.get("source_hash"), str) or len(snapshot["source_hash"]) != 64 or any(c not in "0123456789abcdef" for c in snapshot["source_hash"]):
                    raise ValueError("snapshot hash/provenance unavailable")
                prices = row.get("prices") or {}
                for field in ("price", "trailing20_median_dollar_volume"):
                    if field in prices and (isinstance(prices[field], bool) or prices[field] != snapshot[field]):
                        raise ValueError("descriptor/snapshot price or ADV mismatch")
                if "price_at_session_close_utc" in prices and pd.Timestamp(prices["price_at_session_close_utc"]) != observed:
                    raise ValueError("descriptor/snapshot clock mismatch")
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                reasons.append(str(exc))
        if not reasons and isinstance(snapshot, dict):
            instruments[row["ticker"]] = snapshot
        else:
            if not snapshot:
                reasons.append("qualified instrument snapshot unavailable")
            rejected.append({"ticker": row.get("ticker"), "reasons": reasons})
    plan = policy.paper_plan_preview(forecast, instruments=instruments, **_mandate(protocol))
    sensitivities = []
    for bps in protocol["new_simulated_costs"]["sensitivity_round_trip_bps"]:
        sensitivity = policy.paper_plan_preview(forecast, instruments=instruments,
            **{**_mandate(protocol), "round_trip_cost": bps/10000})
        sensitivities.append({"round_trip_bps": bps, "cash_weight": sensitivity["cash_weight"],
                              "plan_artifact_hash": sensitivity["artifact_hash"]})
    return _seal({"schema": VERSION, "role": "PRIMARY_H21" if horizon == 21 else "SEPARATE_SECONDARY_H5",
        "horizon": horizon, "asof": asof, "source_features_hash": source_hash, "vintage": vintage,
        "forecast": forecast, "plan": plan, "cost_sensitivity": sensitivities,
        "candidate_count": len(current.get("records", [])), "refusals": rejected,
        "return_input_refusals": input_refusals,
        "refusal_counts": dict(Counter(reason for r in rejected for reason in r["reasons"])),
        **_current_decision_status(forecast, instruments, plan, horizon=horizon,
            input_count=len(current.get("qualified_return_records") or []), candidate_count=len(current.get("records", []))),
        **({"weight_input": {"artifact_hash": vintage["artifact_hash"],
            "qualification_hash": policy.digest(weight_qualification),
            "qualification": weight_qualification}} if weight_artifact is not None else {}),
        "claim": "new inactive preview; unavailable inputs are not an investment cash decision; no activation, fills, or fabricated returns"})
