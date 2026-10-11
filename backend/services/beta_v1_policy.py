"""Isolated BETA_V1 shadow adapter over the existing reputation/blend engine.

No collectors, runtime stores, brokers, configuration or legacy promotion gates
are touched. Inputs are immutable normalized records plus an EXTERNAL adapter's
qualification manifest binding the entire record hash to a source hash/reference
and a reason. This is a provenance contract, not independent verification of
the source; the caller must qualify sources before invoking this module.

Tasks never share weights. Probability cannot be converted into expected return,
magnitude cannot become direction, and horizons are exact (no analyst 252->21).
Every output is retrospective/shadow evidence, never a forward skill claim.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import exchange_calendars as xcals

from backend.services import expected_return as er
from backend.services import forecast_reputation as fr
from backend.services import beta_v1_legacy_kernels as kernels

POLICY = "BETA_V1_SHADOW"
SCHEMA = 3
TASKS = ("expected_excess_return", "beats_benchmark")


def _calendar():
    return xcals.get_calendar("XNYS")


def _session_count(start: pd.Timestamp, end: pd.Timestamp) -> int:
    return len(_calendar().sessions_in_range(start.date().isoformat(), end.date().isoformat()))-1


def _interval_blocks(rows: list[dict]) -> list[list[dict]]:
    """Conservative overlap clusters over actual validated label intervals.

    A connected overlapping cluster gets one evidence vote, regardless of its
    number of dates/events. Touching close-to-close intervals do not overlap.
    """
    blocks, end = [], None
    for row in sorted(rows, key=lambda r: (r["_start"], r["_end"], r["record_hash"])):
        if end is None or row["_start"] >= end:
            blocks.append([])
        blocks[-1].append(row)
        end = max(end, row["_end"]) if end is not None else row["_end"]
    return blocks


def _return_ic(blocks: list[list[dict]]) -> float:
    flat = [r for b in blocks for r in b]
    x, y = np.array([r["x"] for r in flat]), np.array([r["y"] for r in flat])
    w = np.array([1/(len(blocks)*len(b)) for b in blocks for r in b])
    mx, my = float(np.sum(w*x)), float(np.sum(w*y))
    covariance = float(np.sum(w*(x-mx)*(y-my)))
    denominator = math.sqrt(float(np.sum(w*(x-mx)**2)*np.sum(w*(y-my)**2)))
    return covariance/denominator if denominator > 0 else float("nan")


def digest(value: Any) -> str:
    """Hash canonical JSON; reject nonfinite numbers rather than serialize NaN."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


def _clock(value: Any) -> pd.Timestamp:
    if not isinstance(value, str) or not value:
        raise ValueError("explicit dated timezone string required")
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError("explicit timezone required")
    return stamp.tz_convert("UTC")


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a numerical forecast")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("nonfinite value")
    return value


def _verify_record(row: dict, qualifications: dict, *, definitions: dict,
                   task: str, horizon: int, objective_version: str,
                   cutoff: pd.Timestamp, grade: bool) -> dict:
    rh = digest(row)
    q = qualifications.get(rh)
    if not isinstance(q, dict) or not all(q.get(k) for k in (
            "source_hash", "source_ref", "adapter_version", "qualification_reason")):
        raise ValueError("no external qualification bound to exact record hash")
    if (q["source_hash"] != row.get("source_hash")
            or not isinstance(q["source_hash"], str) or len(q["source_hash"]) != 64
            or any(c not in "0123456789abcdef" for c in q["source_hash"])):
        raise ValueError("source hash differs from qualification")
    c = row.get("component")
    if c not in definitions:
        raise ValueError("unknown component")
    definition = definitions[c]
    if (row.get("task") != task or row.get("horizon") != horizon
            or row.get("objective_version") != objective_version):
        raise ValueError("task/horizon/objective mismatch; no conversion permitted")
    if any(row.get(k) != definition[k] for k in ("model_version", "prompt_version")):
        raise ValueError("model/prompt version mismatch")
    if not row.get("forecast_id") or not row.get("root_event") or not row.get("ticker"):
        raise ValueError("missing forecast identity/root event/ticker")
    available, made = _clock(row.get("available_at")), _clock(row.get("forecast_at"))
    if not available <= made <= cutoff:
        raise ValueError("features/forecast unavailable at cutoff")
    x = _number(row.get("x"))
    if task == "beats_benchmark" and not 0 <= x <= 1:
        raise ValueError("probability outside [0,1]")
    if row.get("calendar") != "XNYS" or row.get("window_contract") != "session_close_to_close":
        raise ValueError("supported US XNYS session-close target/window contract required")
    start, end, valid = (_clock(row.get(k)) for k in ("label_start_at", "label_end_at", "valid_until_at"))
    calendar = _calendar()
    if (calendar.session_close(start.date().isoformat()) != start
            or calendar.session_close(end.date().isoformat()) != end
            or _session_count(start, end) != horizon):
        raise ValueError("actual label session duration differs from declared horizon")
    if not made <= valid <= start < end:
        raise ValueError("invalid forecast/entry/expiry target clocks")
    if not grade and cutoff > valid:
        raise ValueError("expired forecast cannot become a new current decision")
    result = {**row, "record_hash": rh, "_made": made, "_available": available,
              "_start": start, "_end": end, "_valid": valid,
              "x": x, "qualification": q}
    if grade:
        observed = _clock(row.get("outcome_at"))
        if not made < end <= observed <= cutoff:
            raise ValueError("label not matured/observable at cutoff")
        y = _number(row.get("y"))
        if task == "beats_benchmark" and y not in (0, 1):
            raise ValueError("binary outcome required")
        result.update(_end=end, _observed=observed, y=y)
    return result


def _admit(records: Iterable[dict], qualifications: dict, *, definitions: dict,
           task: str, horizon: int, objective_version: str, cutoff: pd.Timestamp,
           grade: bool) -> tuple[list[dict], list[dict], dict]:
    accepted, rejected = [], []
    for row in records:
        if not isinstance(row, dict):
            rejected.append({"forecast_id": None, "component": None,
                             "reason": "normalized record must be an object"})
            continue
        try:
            accepted.append(_verify_record(row, qualifications, definitions=definitions,
                task=task, horizon=horizon, objective_version=objective_version,
                cutoff=cutoff, grade=grade))
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            rejected.append({"forecast_id": row.get("forecast_id"),
                             "component": row.get("component"), "reason": str(exc)})
    # A root event can contribute once per component/cell. Exact duplicates are
    # ignored; different forecasts for the same root are quarantined, never
    # selected on their score, arrival order or revision timestamp.
    groups: dict[tuple, dict[str, dict]] = {}
    for row in accepted:
        key = (row["component"], row["root_event"])
        groups.setdefault(key, {})[row["record_hash"]] = row
    deduped, conflicts = [], 0
    for key in sorted(groups):
        rows = groups[key]
        if len(rows) > 1:
            conflicts += len(rows)
            rejected.extend({"forecast_id": r["forecast_id"], "component": r["component"],
                             "reason": "conflicting root-event duplicate quarantined"}
                            for r in rows.values())
        else:
            deduped.append(next(iter(rows.values())))
    return deduped, sorted(rejected, key=lambda r: json.dumps(r, sort_keys=True)), {
        "duplicate_count": len(accepted) - sum(len(v) for v in groups.values()),
        "quarantine_count": conflicts}


def _seal(artifact: dict) -> dict:
    return {**artifact, "artifact_hash": digest(artifact)}


def verify_artifact(artifact: dict) -> None:
    if artifact.get("policy") != POLICY or artifact.get("schema") != SCHEMA:
        raise ValueError("unsupported policy/schema")
    payload = {k: v for k, v in artifact.items() if k != "artifact_hash"}
    if artifact.get("artifact_hash") != digest(payload):
        raise ValueError("artifact hash mismatch")


def fit(records: Iterable[dict], *, qualifications: dict, definitions: dict,
        cutoff: str, task: str, horizon: int, objective_version: str,
        min_blocks: int = 30, k_prior: float = 30.0, gamma: float = 1.0,
        prior_share: float = 0.5, embargo_sessions: int | None = None) -> dict:
    """Fit a dated task/cell vintage, using mature externally qualified inputs.

    Later half of decision DATE blocks is the evaluation half. Earlier labels
    must be observable strictly before its start; an additional horizon-sized
    business-day embargo removes overlapping labels. Probability baseline is
    frozen from that purged earlier half. IC uses only return units. Shrink n
    counts nonoverlapping held-out date blocks, capped by distinct root events.
    No tuning, random splits, fitted decay or hindsight parameter selection.
    """
    if task not in TASKS or isinstance(horizon, bool) or horizon < 1:
        raise ValueError("unsupported task/horizon")
    if not objective_version or not definitions or min_blocks < 1:
        raise ValueError("objective, definitions and positive minimum required")
    if k_prior < 0 or gamma <= 0 or not 0 < prior_share <= 1:
        raise ValueError("invalid shrink parameters")
    embargo = horizon if embargo_sessions is None else embargo_sessions
    if embargo < horizon:
        raise ValueError("embargo must be at least the label horizon")
    for d in definitions.values():
        if not all(d.get(k) for k in ("source_family", "model_version", "prompt_version",
                                     "correlation_group")):
            raise ValueError("incomplete component definition")
    cut = _clock(cutoff)
    rows, rejected, counts = _admit(records, qualifications, definitions=definitions,
        task=task, horizon=horizon, objective_version=objective_version, cutoff=cut, grade=True)
    audits, skills = {}, {}
    for c in sorted(definitions):
        sub = sorted((r for r in rows if r["component"] == c),
                     key=lambda r: (r["_made"], r["record_hash"]))
        days = sorted({r["_made"].date().isoformat() for r in sub})
        test_days = days[len(days) // 2:] if len(days) >= 2 else []
        boundary = pd.Timestamp(test_days[0], tz="UTC") if test_days else None
        train = [r for r in sub if boundary is not None and r["_made"] < boundary
                 and r["_observed"] < boundary and r["_end"] < boundary
                 and _session_count(r["_made"], boundary) >= embargo]
        test = [r for r in sub if r["_made"].date().isoformat() in test_days]
        # The same root cannot occur in both train and test by admission above.
        blocks = _interval_blocks(test)
        n = len(blocks)
        skill, score, baseline, uncertainty = None, None, None, None
        if train and len(test) >= 3:
            if task == "beats_benchmark":
                base = float(np.mean([np.mean([r["y"] for r in b]) for b in _interval_blocks(train)]))
                losses = [float(np.mean([(r["x"]-r["y"])**2 for r in b])) for b in blocks]
                base_losses = [float(np.mean([(base-r["y"])**2 for r in b])) for b in blocks]
                score, baseline = float(np.mean(losses)), float(np.mean(base_losses))
                skill = 1 - score / baseline if baseline > 0 else None
                # Uncertainty of improvement by nonoverlapping date blocks.
                means = [b-l for b, l in zip(base_losses, losses)]
                if len(means) > 1:
                    uncertainty = float(np.std(means, ddof=1) / math.sqrt(len(means)))
            else:
                # Equal weight per independent interval block, then per event
                # within its block. Weighted Pearson IC keeps the estimand
                # consistent with shrink support rather than dense row dates.
                value = _return_ic(blocks)
                skill = float(value) if math.isfinite(value) else None
                score, baseline = skill, 0.0
                # IC uncertainty is deliberately unavailable: IID row Fisher SE
                # would overstate independence for overlapping event windows.
        learned = skill is not None and n >= min_blocks
        status = "LEARNED" if learned else ("SHRUNK_PRIOR" if sub else "UNAVAILABLE")
        reasons = [r["reason"] for r in rejected if r.get("component") == c]
        audits[c] = {**definitions[c], "component": c, "task": task, "horizon": horizon,
            "objective_version": objective_version, "training_cutoff": cut.isoformat(),
            "n_rows": len(sub), "n_dates": len(days), "n_root_events": len(sub),
            "heldout_independent_blocks": n, "n_train": len(train), "n_test": len(test),
            "purged_train_rows": len(sub)-len(test)-len(train),
            "train_record_hashes": sorted(r["record_hash"] for r in train),
            "test_record_hashes": sorted(r["record_hash"] for r in test),
            "train_decision_range": [min(r["forecast_at"] for r in train), max(r["forecast_at"] for r in train)] if train else None,
            "test_decision_range": [min(r["forecast_at"] for r in test), max(r["forecast_at"] for r in test)] if test else None,
            "independent_interval_blocks": [sorted(r["record_hash"] for r in b) for b in blocks],
            "largest_block_row_share": max((len(b)/len(test) for b in blocks), default=None),
            "estimand": "equal independent interval blocks; equal events within block",
            "latest_outcome_at": max((r["_observed"].isoformat() for r in sub), default=None),
            "feature_availability_range": [min(r["_available"].isoformat() for r in sub),
                max(r["_available"].isoformat() for r in sub)] if sub else None,
            "observed_score": score, "baseline_score": baseline, "skill": skill,
            "uncertainty_se": uncertainty, "decay": 1.0,
            "status": status, "reason": ("eligible held-out evidence" if learned else
                "thin/unsplittable evidence: frozen prior" if sub else "no eligible input"),
            "rejected_count": len(reasons), "rejection_reasons": sorted(set(reasons)),
            "prior": 0.0, "prior_eligible": not learned,
            "admissibility_multiplier": 1.0 if sub else 0.0}
        skills[c] = {"n": n, "skill": skill if learned else float("nan")}
    table = pd.DataFrame.from_dict(skills, orient="index")
    rep = kernels.weight_mass(table, k_prior=k_prior, gamma=gamma, floor=0.0)
    eligible_groups = {a["correlation_group"] for a in audits.values() if a["admissibility_multiplier"] > 0}
    raw = {}
    for c, a in audits.items():
        a["fitted_weight"] = float(rep[c])
        a["raw_shrunk_score"] = float(rep[c])
        a["prior"] = prior_share/len(eligible_groups) if a["admissibility_multiplier"] else 0.0
        raw[c] = (float(rep[c]) if a["status"] == "LEARNED" else a["prior"]) * a["admissibility_multiplier"]
    # Correlated component families share one influence budget, rather than
    # collecting extra weight by registering multiple models of the same story.
    groups: dict[str, list[str]] = {}
    for c in audits:
        if audits[c]["admissibility_multiplier"] > 0:
            groups.setdefault(audits[c]["correlation_group"], []).append(c)
    for cs in groups.values():
        for c in cs:
            raw[c] /= len(cs)
            audits[c]["eligible_group_members"] = cs
            audits[c]["group_divisor"] = len(cs)
    total = sum(raw.values())
    weights = {c: raw[c]/total if total else 0.0 for c in raw}
    for c in audits:
        audits[c]["effective_weight"] = weights[c]
        audits[c]["allocated_mass"] = raw[c]
    admitted = [{"record_hash": r["record_hash"], "forecast_id": r["forecast_id"],
                 "root_event": r["root_event"], "qualification": r["qualification"]}
                for r in sorted(rows, key=lambda r: r["record_hash"])]
    return _seal({"schema": SCHEMA, "policy": POLICY, "mode": "SHADOW_ONLY",
        "cutoff": cut.isoformat(), "task": task, "horizon": horizon,
        "objective_version": objective_version, "definitions": definitions,
        "parameters": {"min_blocks": min_blocks, "k_prior": k_prior, "gamma": gamma,
                       "prior_share": prior_share, "embargo_sessions": embargo},
        "status": "READY" if total else "UNAVAILABLE", "components": audits,
        "weights": weights, "admitted": admitted, "rejected": rejected, **counts,
        "qualification_hash": digest(qualifications),
        "code_hashes": {Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                        for p in (__file__, er.__file__, fr.__file__, kernels.__file__)},
        "calendar": "XNYS exchange sessions; exact session-close label intervals",
        "target_window_contract": "session_close_to_close",
        "score_support": "per-component chronological windows; not a paired same-window comparison",
        "claim": "retrospective experimental weights; no forward skill or activation"})


def save(artifact: dict, directory: Path | str) -> Path:
    """Content addressed, dated vintages; no wall-clock field changes reruns."""
    verify_artifact(artifact)
    path = Path(directory) / f"beta_v1_{artifact['cutoff'][:10]}_{artifact['artifact_hash']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(artifact, sort_keys=True, indent=2, allow_nan=False)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError("immutable vintage collision")
    else:
        # Exclusive creation also prevents another writer overwriting a vintage.
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
    return path


def load(path: Path | str) -> dict:
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    verify_artifact(artifact)
    return artifact


def forecast(artifact: dict, records: Iterable[dict], *, qualifications: dict,
             asof: str, variant: str = "adaptive", scheduled_entry_at: str | None = None) -> dict:
    """Consume a frozen vintage through er.blend/fr.pool; never read stores."""
    verify_artifact(artifact)
    if variant not in ("adaptive", "equal", "without_news", "without_analyst"):
        raise ValueError("unknown comparator")
    clock = _clock(asof)
    if _clock(artifact["cutoff"]) > clock:
        raise ValueError("future weight vintage")
    definitions = artifact["definitions"]
    rows, rejected, counts = _admit(records, qualifications, definitions=definitions,
        task=artifact["task"], horizon=artifact["horizon"],
        objective_version=artifact["objective_version"], cutoff=clock, grade=False)
    # Freeze target support BEFORE ablations, weighting or reading scores.
    # A cohort is one exact entry/exit target across every candidate, not merely
    # one horizon. Reject the entire incompatible cohort; do not choose a target
    # based on input order, model family, weight, prediction or outcome.
    scheduled = _clock(scheduled_entry_at) if scheduled_entry_at is not None else None
    targets = {(r["calendar"], r["window_contract"], r["_start"].isoformat(),
                r["_end"].isoformat()) for r in rows}
    target_contract, contract_hash, contract_error = None, None, None
    if len(targets) > 1:
        contract_error = "incompatible exact target windows: entire candidate cohort quarantined"
    elif targets:
        calendar, window, start, end = next(iter(targets))
        start_clock = _clock(start)
        if scheduled is not None and (scheduled != start_clock or scheduled < clock):
            contract_error = "scheduled decision differs from target entry or is in the past"
        elif scheduled is None and start_clock.date() != clock.date():
            contract_error = "future-entry target requires an explicitly scheduled decision"
        else:
            target_contract = {"calendar": calendar, "window_contract": window,
                "label_start_at": start, "label_end_at": end, "task": artifact["task"],
                "horizon": artifact["horizon"], "objective_version": artifact["objective_version"],
                "decision_at": clock.isoformat(),
                "scheduled_entry_at": scheduled.isoformat() if scheduled is not None else None}
            contract_hash = digest(target_contract)
    if contract_error:
        rejected.extend({"forecast_id": r["forecast_id"], "component": r["component"],
                         "reason": contract_error} for r in rows)
        rejected.sort(key=lambda r: json.dumps(r, sort_keys=True))
        counts["quarantine_count"] += len(rows)
        rows = []
    by_ticker: dict[str, dict] = {}
    for row in rows:
        by_ticker.setdefault(row["ticker"], {}).setdefault(row["component"], []).append(row)
    table = pd.DataFrame.from_dict({c: {"graded": a["status"] == "LEARNED"}
                                   for c, a in artifact["components"].items()}, orient="index")
    outputs = []
    for ticker, comp in sorted(by_ticker.items()):
        x, reasons, consumed, consumed_forecasts = {}, {}, [], []
        for c in sorted(definitions):
            candidates = comp.get(c, [])
            if candidates:
                latest = max(r["_made"] for r in candidates)
                newest = [r for r in candidates if r["_made"] == latest]
            else:
                newest = []
            family = definitions[c]["source_family"]
            ablated = (variant == "without_news" and family == "news") or (
                       variant == "without_analyst" and family == "analyst")
            if ablated or len(newest) != 1:
                x[c] = None
                reasons[c] = "ablation" if ablated else "missing/ambiguous latest qualified input"
            else:
                x[c] = newest[0]["x"]
                consumed.append(newest[0]["record_hash"])
                consumed_forecasts.append({k: newest[0][k] for k in ("record_hash", "forecast_id",
                    "forecast_at", "available_at", "valid_until_at", "label_start_at", "label_end_at",
                    "calendar", "window_contract", "source_hash", "qualification")})
        effective = artifact["weights"] if variant != "equal" else {c: 1.0 for c in definitions}
        view = kernels.blend(x, table, components=tuple(sorted(definitions)),
                        effective_weights=effective, asleep_reasons=reasons)
        prior_awake = [c for c in view["awake"] if artifact["components"][c]["prior_eligible"]]
        fallback = not view["reputation_defined"] and bool(prior_awake)
        fallback_groups = {}
        if fallback:
            for c in prior_awake:
                fallback_groups.setdefault(definitions[c]["correlation_group"], []).append(c)
            effective = {c: (1.0/len(fallback_groups[definitions[c]["correlation_group"]])
                         if c in prior_awake else 0.0) for c in definitions}
            view = kernels.blend(x, table, components=tuple(sorted(definitions)), effective_weights=effective,
                            asleep_reasons=reasons)
        weights = view["weights_reputation"]
        if artifact["task"] == "beats_benchmark":
            value = fr.pool({c: v for c, v in x.items() if v is not None},
                            pd.Series(weights, dtype=float), kappa=1.0)
        else:
            value = view["er_reputation"]
        outputs.append({"ticker": ticker, "value": value, "task": artifact["task"],
            "horizon": artifact["horizon"], "effective_weights": weights,
            "contributions": {c: weights[c]*x[c] for c in weights} if artifact["task"] ==
                "expected_excess_return" else None,
            "unavailable": view["asleep"], "equal_fallback": fallback,
            "prior_fallback_groups": fallback_groups,
            "target_contract": target_contract, "target_contract_hash": contract_hash,
            "consumed_record_hashes": sorted(consumed), "consumed_forecasts": consumed_forecasts,
            "status": "AVAILABLE" if value is not None else "ABSTAIN_NO_ADMISSIBLE_INFLUENCE"})
    return _seal({"schema": SCHEMA, "policy": POLICY, "mode": "SHADOW_ONLY",
        "asof": clock.isoformat(), "weight_artifact_hash": artifact["artifact_hash"],
        "qualification_hash": digest(qualifications), "task": artifact["task"],
        "horizon": artifact["horizon"], "objective_version": artifact["objective_version"],
        "target_contract": target_contract, "target_contract_hash": contract_hash,
        "variant": variant, "forecasts": outputs, "rejected": rejected, **counts})


def paper_plan_preview(view: dict, *, instruments: dict, equity: float,
                       issuer_cap: float, cash_floor: float, max_names: int,
                       round_trip_cost: float) -> dict:
    """Deterministic experimental plan only; no broker/fill or NAV mutation.

    Instruments must be independently qualified priced/admissible snapshots.
    Caller supplies mandate explicitly. Positive excess after same cost is
    proportional sized, capped per issuer with residual cash (no forced fill).
    """
    verify_artifact(view)
    if view.get("task") != "expected_excess_return":
        raise ValueError("probability/magnitude/analyst targets are not expected returns")
    if (not math.isfinite(equity) or equity <= 0 or not 0 < issuer_cap <= 1
            or not 0 <= cash_floor <= 1 or max_names < 1
            or not math.isfinite(round_trip_cost) or round_trip_cost < 0):
        raise ValueError("invalid declared mandate")
    ranked, refusals = [], []
    asof = _clock(view["asof"])
    contract = view.get("target_contract")
    if view["forecasts"]:
        if not isinstance(contract, dict) or view.get("target_contract_hash") != digest(contract):
            raise ValueError("missing/invalid common cohort target contract")
        if (any(contract.get(k) != view.get(k) for k in ("task", "horizon", "objective_version"))
                or contract.get("decision_at") != asof.isoformat()
                or contract.get("calendar") != "XNYS"
                or contract.get("window_contract") != "session_close_to_close"):
            raise ValueError("common target task/decision contract differs from preview")
        if any(r.get("target_contract") != contract or r.get("target_contract_hash") != digest(contract)
               for r in view["forecasts"]):
            raise ValueError("incompatible candidate target contracts; no plan permitted")
        for row in view["forecasts"]:
            for consumed in row.get("consumed_forecasts", []):
                if (consumed["calendar"] != contract["calendar"]
                        or consumed["window_contract"] != contract["window_contract"]
                        or _clock(consumed["label_start_at"]).isoformat() != contract["label_start_at"]
                        or _clock(consumed["label_end_at"]).isoformat() != contract["label_end_at"]):
                    raise ValueError("consumed forecast differs from common plan target contract")
    for row in view["forecasts"]:
        ticker, inst = row["ticker"], instruments.get(row["ticker"], {})
        try:
            if ticker.upper() == "SPY":
                raise ValueError("SPY is control only")
            if not row.get("consumed_forecasts") or any(
                    asof > _clock(r["valid_until_at"]) for r in row["consumed_forecasts"]):
                raise ValueError("forecast contract expired/unavailable for preview")
            if not all(inst.get(k) for k in ("venue", "currency", "issuer", "qualification_reason",
                                             "source_hash", "source_ref")):
                raise ValueError("unqualified instrument snapshot")
            if inst.get("admissible") is not True or inst.get("liquid") is not True:
                raise ValueError("instrument not admitted/liquid under declared mandate")
            price = _number(inst.get("price"))
            observed = _clock(inst.get("price_at"))
            if price <= 0 or observed > asof or (asof-observed).total_seconds() > 4*86400:
                raise ValueError("invalid/future/stale price")
            score = _number(row["value"]) - round_trip_cost
            if score <= 0:
                raise ValueError("nonpositive expected excess after cost")
            ranked.append((score, ticker, row, inst))
        except (ValueError, TypeError) as exc:
            refusals.append({"ticker": ticker, "reason": str(exc)})
    ranked.sort(key=lambda r: (-r[0], r[1]))
    selected = ranked[:max_names]
    for _, ticker, _, _ in ranked[max_names:]:
        refusals.append({"ticker": ticker, "reason": "below selected rank cutoff"})
    total = sum(r[0] for r in selected)
    issuer_used, holdings = {}, []
    for score, ticker, row, inst in selected:
        issuer = inst["issuer"]
        weight = min((1-cash_floor)*score/total, max(0.0, issuer_cap-issuer_used.get(issuer, 0.0)))
        issuer_used[issuer] = issuer_used.get(issuer, 0.0) + weight
        holdings.append({"ticker": ticker, "weight": weight, "notional": equity*weight,
            "venue": inst["venue"], "currency": inst["currency"], "issuer": issuer,
            "price": inst["price"], "price_at": inst["price_at"], "score_after_cost": score,
            "forecast": row, "instrument_snapshot_hash": digest(inst),
            "status": "PROPOSED_ONLY"})
    return _seal({"schema": SCHEMA, "policy": POLICY, "mode": "SHADOW_ONLY",
        "asof": view["asof"], "forecast_artifact_hash": view["artifact_hash"],
        "weight_artifact_hash": view["weight_artifact_hash"], "holdings": holdings,
        "target_contract": contract, "target_contract_hash": view.get("target_contract_hash"),
        "cash_weight": 1-sum(h["weight"] for h in holdings), "refusals": refusals,
        "mandate": {"equity": equity, "issuer_cap": issuer_cap, "cash_floor": cash_floor,
                    "max_names": max_names, "round_trip_cost": round_trip_cost},
        "activation": "owner review and existing Monday gates still required"})
