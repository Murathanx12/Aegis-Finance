"""Read-only compact-input qualification and paired BETA_V1 replay.

No runtime paths, collectors, model calls, broker or original-ledger writes.
The original grader's first h+1 non-null bars are reconstructed from explicitly
injected frozen prices and checked through belief_state.resolve_one. Actual
bar dates, not declared horizons, establish entry/exit. Unknown source roots
are conservative dependency cells under owner-authorized PRIOR_ONLY mode.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from backend.services import beta_v1_policy as policy
from backend.services import belief_state as belief
from backend.services import expected_return as er

ADAPTER_VERSION = "beta_v1_compact_replay/3"
GRID = ("fixed_revision_flow", "net_raises", "equal", "adaptive", "without_news", "without_analyst")
PRIOR_ONLY_MIN_BLOCKS = 1_000_000


class ReplayLimitExceeded(RuntimeError):
    def __init__(self, resource: str, measured: float, limit: float, stage: str):
        self.report = {"status": "REFUSED_RESOURCE_LIMIT", "resource": resource,
                       "measured": measured, "limit": limit, "stage": stage}
        super().__init__(json.dumps(self.report, sort_keys=True))


def _rss_bytes() -> int:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)]+[
                (name, ctypes.c_size_t) for name in ("peak_rss", "rss", "peak_paged", "paged",
                    "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
        value = Counters()
        value.cb = ctypes.sizeof(value)
        fn = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
        fn.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        fn.restype = wintypes.BOOL
        if not fn(wintypes.HANDLE(-1), ctypes.byref(value), value.cb):
            raise RuntimeError("RSS monitor unavailable; bounded replay refused")
        return int(value.peak_rss)
    import resource
    import sys
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform == "darwin" else 1024)


@dataclass
class RunBudget:
    max_seconds: float = 110.0
    max_rss_bytes: int = 1536*1024*1024
    max_records: int = 6000
    max_cohorts: int = 2000
    max_vintages: int = 1024
    max_artifact_bytes: int = 48*1024*1024
    max_output_bytes: int = 32*1024*1024

    def __post_init__(self):
        self.started = time.monotonic()
        self.accounting = {}

    def check(self, stage: str, **sizes: int):
        rss = _rss_bytes()
        if type(rss) is not int or rss <= 0:
            raise RuntimeError("RSS monitor invalid; bounded replay refused")
        if "rss_bytes" in sizes or "seconds" in sizes:
            raise ValueError("measured resource fields cannot be overridden")
        observed = {"seconds": time.monotonic()-self.started, "rss_bytes": rss, **sizes}
        for resource, measured in observed.items():
            limit = getattr(self, "max_"+resource)
            if measured > limit:
                error = ReplayLimitExceeded(resource, measured, limit, stage)
                error.report["accounting"] = self.accounting.copy()
                raise error

    def contract(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def json_bytes(value: Any) -> int:
    # Iterate chunks instead of retaining another full serialized object.
    return sum(len(s.encode("utf-8")) for s in json.JSONEncoder(sort_keys=True,
        separators=(",", ":"), allow_nan=False).iterencode(value))


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    return float(value) if math.isfinite(value) else None


def _clock(value: str) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError("explicit timezone required")
    return stamp.tz_convert("UTC")


def outcome_clock(row: dict) -> str:
    """Date-only resolution is not an exact early-day availability timestamp."""
    raw = row.get("resolved_at_date_only")
    if not isinstance(raw, str) or len(raw) != 10:
        raise ValueError("missing original date-only resolution stamp")
    return pd.Timestamp(date.fromisoformat(raw)+timedelta(days=1), tz="UTC").isoformat()


def family(row: dict) -> str:
    # Mechanism identity is interpretation metadata; writer lineage determines
    # source admission and news/analyst ablations regardless of that tag.
    name = str(row.get("specialist") or "UNKNOWN")
    return name.split(":", 1)[0]


def load_projection(path: Path | str, *, expected_sha256: str) -> dict:
    """Only an explicitly pinned <=20 MiB private numeric projection."""
    path = Path(path)
    if not expected_sha256 or path.stat().st_size > 20*1024*1024:
        raise ValueError("missing pin or projection exceeds bounded size")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("projection pin mismatch")
    blob = json.loads(raw)
    gate = blob.get("protected_stream_gate") or {}
    if (blob.get("schema") != "protected_first_stream_projection_v2/1"
            or gate.get("end_prefix_verified") is not True
            or gate.get("marker_present") is not False):
        raise ValueError("unqualified protected-first projection schema/gate")
    blob["_projection_sha256"] = expected_sha256
    return blob


def original_forward(projection: dict) -> dict:
    """Original recorded labels and proper loss; no retrading/alpha claims.

    All four canonical observable types remain separate. Price-close returns
    and unknown original cost/adjustment treatment never become net wealth.
    Identity and grade-integrity validation are reported separately by join.
    """
    cells, invalid = defaultdict(list), []
    for row in projection.get("graded_projection_private", []):
        p, y = _num(row.get("probability")), row.get("outcome")
        if p is None or not 0 <= p <= 1 or type(y) is not int or y not in (0, 1):
            invalid.append({"prediction_id": row.get("prediction_id"), "reason": "invalid probability/outcome type"})
            continue
        key = (family(row), row.get("observable"), row.get("horizon_days"),
               row.get("benchmark"), row.get("threshold"))
        cells[key].append(row)
    summaries = []
    for key, rows in sorted(cells.items(), key=lambda kv: str(kv[0])):
        probabilities = np.array([r["probability"] for r in rows], dtype=float)
        outcomes = np.array([r["outcome"] for r in rows], dtype=float)
        clipped = np.clip(probabilities, 1e-12, 1-1e-12)
        returns = [_num((r.get("resolution_numeric") or {}).get("realised_return")) for r in rows]
        observed = [v for v in returns if v is not None]
        summaries.append({"family": key[0], "observable": key[1], "horizon": key[2],
            "benchmark": key[3], "threshold": key[4], "n": len(rows),
            "positive_labels": int(outcomes.sum()), "negative_labels": int(len(rows)-outcomes.sum()),
            "brier": float(np.mean((probabilities-outcomes)**2)),
            "log_loss": float(np.mean(-outcomes*np.log(clipped)-(1-outcomes)*np.log(1-clipped))),
            "log_loss_clip": 1e-12, "mean_probability": float(probabilities.mean()),
            "base_rate_descriptive_only": float(outcomes.mean()),
            "n_dates": len({str(r.get("made_at", ""))[:10] for r in rows}),
            "known_root_count": len({r["dependency_group"]["key_sha256"] for r in rows
                if (r.get("dependency_group") or {}).get("kind") == "declared_root_event_hash"}),
            "unknown_root_rows": sum((r.get("dependency_group") or {}).get("kind") != "declared_root_event_hash" for r in rows),
            "price_close_returns_present": len(observed), "negative_price_close_returns": sum(v < 0 for v in observed),
            "mean_price_close_return": float(np.mean(observed)) if observed else None,
            "cost_states": dict(Counter("charged_with_rate" if r.get("costs_charged") is True and
                _num(r.get("cost_rate_bps")) is not None else "not_charged" if r.get("costs_charged") is False else
                "unknown" for r in rows)), "grade_integrity": "JOIN_VALIDATION_REPORTED_SEPARATELY"})
    return {"lane": "ORIGINAL_FORWARD", "cells": summaries, "invalid_projected_rows": invalid,
        "graded_rows_in_projection": len(projection.get("graded_projection_private", [])),
        "unresolved_rows_in_projection": len(projection.get("unresolved_compact_private", [])),
        "original_projection_gate_counts": (projection.get("protected_stream_gate") or {}).get("counts", {}),
        "pending_original_terminal_states": "UNKNOWN from projection alone; exact metadata supplement required; original projection preserved",
        "return_basis": "archived price-close returns; adjustment/cost basis not independently verified",
        "claim": "proper-loss description of original forecasts, not a new forward track record"}


def _component(row: dict) -> tuple[str, dict]:
    fam = family(row)
    version = row.get("model_version") or "UNRECORDED"
    prompt = row.get("prompt_version") or row.get("prompt_hash") or "UNRECORDED"
    # Stable recorded identity, not forecast ID disguised as a source event.
    name = fam+":"+policy.digest([row.get("specialist"), row.get("model"), version, prompt])[:16]
    source_family = "news" if fam in ("source", "news_digest") else "analyst" if "analyst" in fam or "revision" in fam else "numerical"
    return name, {"source_family": source_family, "model_version": version, "prompt_version": prompt,
        "correlation_group": source_family, "original_model": row.get("model") or "UNRECORDED",
        "original_writer": row.get("specialist") or "UNKNOWN",
        "original_family": fam, "model_version_status": "RECORDED" if row.get("model_version") else "UNKNOWN"}


def reconstruct(rows: list[dict], prices: pd.DataFrame, *, price_manifest: dict,
                projection_sha256: str, allow_unknown_prior: bool, budget: RunBudget | None = None) -> dict:
    """Qualify original label windows using injected immutable daily-close data.

    price_manifest must name its hashes and homogeneous basis. A mismatch with
    archived numbers is retained as a failed verification, never regraded over.
    Unknown event roots or model versions force the whole downstream cohort
    into explicit prior-only mode. Other observables remain original-score only.
    """
    if not price_manifest.get("source_hashes") or not price_manifest.get("price_basis"):
        raise ValueError("explicit frozen price source hashes/basis required")
    if not isinstance(prices.index, pd.DatetimeIndex) or prices.index.tz is not None:
        raise ValueError("original grader requires naive daily bar-date index")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("price dates must be unique and sorted")
    records, qualifications, definitions, verification = [], {}, {}, []
    budget = budget or RunBudget()
    budget.check("reconstruction input", records=len(rows))
    calendar = xcals.get_calendar("XNYS")
    for row in sorted(rows, key=lambda r: str(r.get("prediction_id"))):
        budget.check("original grade reconstruction")
        result = {"prediction_id": row.get("prediction_id"), "source_full_row_sha256": row.get("source_full_row_sha256"),
                  "status": "UNAVAILABLE", "reason": None}
        try:
            made = _clock(row["made_at"])
            h = row.get("horizon_days")
            if type(h) is not int or h < 1 or not row.get("ticker"):
                raise ValueError("missing target/horizon")
            ticker = row["ticker"]
            if ticker not in prices:
                raise ValueError("ticker prices unavailable")
            s = prices[ticker].loc[made.date().isoformat():].dropna().iloc[:h+1]
            if len(s) != h+1 or not np.isfinite(s.to_numpy(float)).all() or (s <= 0).any():
                raise ValueError("incomplete/invalid original ticker window")
            entry, exit_ = s.index[0], s.index[-1]
            result.update(entry_date=entry.date().isoformat(), exit_date=exit_.date().isoformat())
            original = {"prediction_id": row["prediction_id"], "ticker": ticker,
                "made_at": row["made_at"], "resolves_after": row["resolves_after"], "horizon_days": h,
                "observable": row["observable"], "benchmark": row.get("benchmark"),
                "threshold": row.get("threshold"), "probability": row["probability"], "outcome": None}
            observed = outcome_clock(row)
            check = belief.resolve_one(original, prices, today=date.fromisoformat(row["resolved_at_date_only"]))
            if check is None:
                raise ValueError("original grader cannot reproduce terminal row on frozen panel")
            p, y = _num(row.get("probability")), row.get("outcome")
            if p is None or not 0 <= p <= 1 or type(y) is not int or y not in (0, 1):
                raise ValueError("invalid original probability/outcome")
            if check["outcome"] != y:
                raise ValueError("archived outcome differs from original grader reproduction")
            archived = row.get("resolution_numeric") or {}
            for field in ("realised_return", "benchmark_return", "vs_benchmark", "max_drawdown"):
                value = _num(archived.get(field))
                if value is not None and not math.isclose(value, check["resolution_detail"].get(field, float("nan")),
                                                         rel_tol=1e-7, abs_tol=1e-8):
                    raise ValueError("archived numeric grade mismatch: "+field)
            result["status"] = "ORIGINAL_GRADE_VERIFIED"
            if row["observable"] != "beats_benchmark":
                raise ValueError("original grade verified; frozen policy supports beats_benchmark only")
            benchmark = row.get("benchmark")
            b = prices[benchmark].loc[made.date().isoformat():].dropna().iloc[:h+1]
            if list(b.index) != list(s.index):
                raise ValueError("original ticker/benchmark actual target windows differ")
            start, end = calendar.session_close(entry.date().isoformat()), calendar.session_close(exit_.date().isoformat())
            if len(calendar.sessions_in_range(entry, exit_))-1 != h or made > start:
                raise ValueError("actual XNYS duration mismatch or forecast after original entry close")
            if _clock(observed) < end:
                raise ValueError("recorded resolution clock precedes label end")
            if not row.get("model_version") or not (row.get("prompt_version") or row.get("prompt_hash")):
                raise ValueError("original grade verified; model/prompt provenance UNRECORDED, policy admissibility zero")
            dep = row.get("dependency_group") or {}
            root_known = dep.get("kind") == "declared_root_event_hash" and bool(dep.get("key_sha256"))
            if not root_known and not allow_unknown_prior:
                raise ValueError("unknown source root not authorized for prior-only admission")
            root = "declared:"+dep["key_sha256"] if root_known else "UNKNOWN_DATE_TICKER:"+policy.digest([made.date().isoformat(), ticker])
            component, definition = _component(row)
            definitions[component] = definition
            objective = "beats_benchmark:"+str(benchmark)+":"+price_manifest["price_basis"]
            normalized = {"forecast_id": row["prediction_id"], "component": component, "ticker": ticker,
                "root_event": root, "root_independence": "DECLARED" if root_known else "UNKNOWN",
                "source_hash": row["source_full_row_sha256"], "forecast_at": made.isoformat(),
                "available_at": made.isoformat(), "feature_clock_status": "original frozen forecast availability; upstream clocks unknown",
                "label_start_at": start.isoformat(), "label_end_at": end.isoformat(), "valid_until_at": start.isoformat(),
                "calendar": "XNYS", "window_contract": "session_close_to_close", "outcome_at": observed,
                "task": "beats_benchmark", "horizon": h, "objective_version": objective,
                "model_version": definition["model_version"], "prompt_version": definition["prompt_version"],
                "x": p, "y": y, "rel_return": check["resolution_detail"]["vs_benchmark"],
                "costs_charged": row.get("costs_charged"), "cost_rate_bps": row.get("cost_rate_bps"),
                "original_record_hash": row.get("immutable_record_hash"), "source_refs_sha256": row.get("source_refs_sha256", {})}
            normalized["original_writer"] = row.get("specialist") or "UNKNOWN"
            normalized["original_mechanism_id"] = row.get("mechanism_id") or "UNRECORDED"
            rh = policy.digest(normalized)
            qualifications[rh] = {"source_hash": normalized["source_hash"],
                "source_ref": "compact-projection-sha256:"+projection_sha256+"/original-row-sha256:"+normalized["source_hash"],
                "adapter_version": ADAPTER_VERSION, "qualification_reason":
                    "original grader numeric/label reproduced on pinned homogeneous closes; date-only outcome upper bound; "
                    +( "declared root" if root_known else "UNKNOWN root; conservative date/ticker overcluster; PRIOR_ONLY"),
                "price_manifest_hash": policy.digest(price_manifest), "root_independence": normalized["root_independence"],
                "original_writer": normalized["original_writer"],
                "original_mechanism_id": normalized["original_mechanism_id"],
                "source_reference_status": "DECLARED_HASHES" if normalized["source_refs_sha256"] else "UNKNOWN"}
            records.append(normalized)
            result.update(status="QUALIFIED_POLICY_INPUT", reason="prior-only if unknown root/model provenance")
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            result["reason"] = str(exc)
        verification.append(result)
    return {"adapter_version": ADAPTER_VERSION, "records": records, "qualifications": qualifications,
        "definitions": definitions, "verification": verification,
        "verification_counts": dict(Counter(r["status"] for r in verification)),
        "projection_sha256": projection_sha256, "price_manifest": price_manifest,
        "outcome_clock": "date-only resolved_at + next calendar day 00:00 UTC",
        "price_basis": price_manifest["price_basis"]}


def _prior_mode(records: list[dict], definitions: dict) -> bool:
    return any(r.get("root_independence") == "UNKNOWN" or
        definitions[r["component"]].get("model_version_status") != "RECORDED" for r in records)


def chronological_replay(joined: dict, *, minimum_blocks: int = 30,
                         budget: RunBudget | None = None, artifact_sink=None,
                         hash_only: bool = False, force_prior_only: bool = False) -> dict:
    """Expanding PIT vintages on matching exact original questions/windows.

    Binary proper-loss replay only. Six slots frozen; unavailable numerical
    revision controls are named. Costs remain the ORIGINAL recorded contract,
    not inferred net returns or fabricated executions. No random splits.
    """
    records, defs, quals = joined["records"], joined["definitions"], joined["qualifications"]
    budget = budget or RunBudget()
    budget.check("replay input", records=len(records))
    cells = defaultdict(list)
    for r in records:
        cells[(r["task"], r["horizon"], r["objective_version"])].append(r)
    artifacts, decisions, decision_hashes = {}, [], []
    aggregates = {name: {"loss": [], "difference": []} for name in GRID}
    artifact_bytes, cache_hits = 0, 0
    def add_decision(decision):
        decision_hashes.append(policy.digest(decision))
        if not hash_only:
            decisions.append(decision)
        budget.accounting["decisions_completed"] = len(decision_hashes)
        budget.accounting["loss_pair_counts"] = {k: len(v["loss"]) for k, v in aggregates.items()}
        for name in GRID:
            variant = decision.get("variants", {}).get(name, {})
            equal = decision.get("variants", {}).get("equal", {})
            if variant.get("brier") is not None and equal.get("brier") is not None:
                aggregates[name]["loss"].append(variant["brier"])
                aggregates[name]["difference"].append(variant["brier"]-equal["brier"])
        budget.check("replay decision accounting", cohorts=len(decision_hashes))
    for cell, rows in sorted(cells.items(), key=lambda item: str(item[0])):
        last_key, last_vintage = None, None
        cohort_groups = defaultdict(list)
        for row in rows:
            # Original frozen forecasts at one decision may pool only one exact
            # question/cost/window. Multiple questions are separate paired units.
            cohort_groups[(row["forecast_at"], row["label_start_at"], row["label_end_at"],
                row["ticker"], row["costs_charged"], row["cost_rate_bps"])].append(row)
        for key, current in sorted(cohort_groups.items(), key=lambda item: str(item[0])):
            cutoff = key[0]
            budget.check("before chronological fit", cohorts=len(decision_hashes)+1)
            available = [r for r in rows if _clock(r["forecast_at"]) <= _clock(cutoff)]
            past = [r for r in rows if _clock(r["outcome_at"]) <= _clock(cutoff)]
            active_definitions = {c: defs[c] for c in sorted({r["component"] for r in available})}
            prior_only = force_prior_only or _prior_mode(available, active_definitions)
            past_quals = {policy.digest(r): quals[policy.digest(r)] for r in past}
            current_quals = {policy.digest(r): quals[policy.digest(r)] for r in current}
            cache_key = (cell, cutoff)
            if cache_key != last_key:
                budget.check("new weight vintage", vintages=len(artifacts)+1)
                last_vintage = policy.fit(past, qualifications=past_quals,
                    definitions=active_definitions, cutoff=cutoff, task=cell[0], horizon=cell[1],
                    objective_version=cell[2], min_blocks=PRIOR_ONLY_MIN_BLOCKS if prior_only else minimum_blocks)
                last_key = cache_key
                artifact_bytes += json_bytes(last_vintage)
                budget.check("weight vintage bytes", artifact_bytes=artifact_bytes)
                reference = artifact_sink(last_vintage) if artifact_sink and not hash_only else None
                artifacts[last_vintage["artifact_hash"]] = {"artifact_hash": last_vintage["artifact_hash"],
                    "cutoff": cutoff, "parameters": last_vintage["parameters"], "reference": reference,
                    "available_roster": sorted(active_definitions), "prior_only": prior_only,
                    "components": {c: {k: a[k] for k in ("status", "latest_outcome_at", "effective_weight", "skill",
                        "n_rows", "heldout_independent_blocks")} for c, a in last_vintage["components"].items()}}
            else:
                cache_hits += 1
            vintage = last_vintage
            labels = {r["y"] for r in current}
            if len(labels) != 1:
                add_decision({"decision_at": cutoff, "ticker": key[3], "status": "QUARANTINED_CONFLICTING_TARGET_LABELS"})
                continue
            actual = next(iter(labels))
            variants = {name: {"status": "UNAVAILABLE", "reason": "authentic aligned revision feature/control snapshot absent"}
                        for name in GRID[:2]}
            for name in GRID[2:]:
                budget.check("forecast variant")
                view = policy.forecast(vintage, current, qualifications=current_quals, asof=cutoff,
                    variant=name, scheduled_entry_at=key[1] if _clock(key[1]).date() != _clock(cutoff).date() else None)
                forecast = view["forecasts"][0]["value"] if len(view["forecasts"]) == 1 else None
                clipped = min(max(forecast, 1e-12), 1-1e-12) if forecast is not None else None
                variants[name] = {"status": "AVAILABLE" if forecast is not None else "ABSTAIN",
                    "probability": forecast, "brier": (forecast-actual)**2 if forecast is not None else None,
                    "log_loss": -actual*math.log(clipped)-(1-actual)*math.log(1-clipped) if clipped is not None else None,
                    "forecast_artifact_hash": view["artifact_hash"],
                    "qualification_hash": view["qualification_hash"], "target_contract_hash": view["target_contract_hash"],
                    "consumed_forecasts": [{"effective_weights": f["effective_weights"],
                        "consumed_record_hashes": f["consumed_record_hashes"], "status": f["status"]} for f in view["forecasts"]],
                    "rejected": view["rejected"], "quarantine_count": view["quarantine_count"]}
            add_decision({"decision_at": cutoff, "ticker": key[3], "task": cell[0], "horizon": cell[1],
                "objective_version": cell[2], "label_start_at": key[1], "label_end_at": key[2],
                "original_forecast_ids": sorted(r["forecast_id"] for r in current), "y": actual,
                "costs_charged": key[4], "cost_rate_bps": key[5], "prior_only": prior_only,
                "weight_artifact_hash": vintage["artifact_hash"], "variants": variants})
    paired = []
    for name in GRID:
        ready = aggregates[name]
        paired.append({"variant": name, "n_same_question_pairs": len(ready["loss"]),
            "mean_brier": float(np.mean(ready["loss"])) if ready["loss"] else None,
            "mean_brier_difference_vs_equal": float(np.mean(ready["difference"])) if ready["difference"] else None,
            "status": "RETROSPECTIVE_PROPER_LOSS" if ready["loss"] else "UNAVAILABLE"})
    semantic = {"adapter_version": ADAPTER_VERSION, "grid": list(GRID), "paired_results": paired,
        "decision_hashes": decision_hashes, "weight_artifact_hashes": sorted(artifacts),
        "force_prior_only": force_prior_only, "minimum_blocks": minimum_blocks}
    semantic_hash = policy.digest(semantic)
    if hash_only:
        return {"artifact_hash": semantic_hash, "n_decisions": len(decision_hashes)}
    result = {"lane": "CURRENT_POLICY_PIT_REPLAY", "grid": list(GRID), "paired_results": paired,
        "decisions": decisions, "weight_artifacts": artifacts,
        "decision_hashes": decision_hashes, "cache_hits": cache_hits,
        "resource_contract": budget.contract(), "force_prior_only": force_prior_only,
        "original_policy_replay": {"status": "UNAVAILABLE", "reason": "frozen action/decision records not in compact projection"},
        "portfolio_metrics": {"status": "UNAVAILABLE", "reason": "probability forecasts are not executed return portfolio plans"},
        "claim": "retrospective original-output replay; no new forward skill/activation", "adapter_version": ADAPTER_VERSION}
    budget.check("compact replay output", output_bytes=json_bytes(result))
    return {**result, "artifact_hash": semantic_hash}


def calibrated_return_inputs(joined: dict, current: list[dict], *, cutoff: str) -> tuple[list[dict], dict]:
    """Reuse existing expected_return calibration fitted ONLY on prior labels.

    This is an optional authenticated return-unit adapter, never an automatic
    claim that p or analyst target upside equals h-session expected return.
    """
    past = [r for r in joined["records"] if _clock(r["outcome_at"]) <= _clock(cutoff)]
    output, provenance = [], {"available": {}, "unavailable": []}
    for row in current:
        training = [r for r in past if all(r[k] == row[k] for k in ("component", "horizon", "objective_version"))]
        if len(training) < 2 or len({r["forecast_at"][:10] for r in training}) < 2:
            provenance["unavailable"].append({"forecast_id": row["forecast_id"], "reason": "fewer than two eligible prior outcome dates"})
            continue
        frame = pd.DataFrame({"arm": ["investigator:adapter"]*len(training), "observable": ["beats_benchmark"]*len(training),
            "p": [r["x"] for r in training], "rel_ret": [r["rel_return"] for r in training],
            "horizon_days": [row["horizon"]]*len(training), "made_day": [r["forecast_at"][:10] for r in training]})
        cal = er._calibration(frame).get("investigator_dir", {}).get(row["horizon"])
        if not cal or not cal.get("bins"):
            provenance["unavailable"].append({"forecast_id": row["forecast_id"], "reason": "existing expected_return calibration unavailable for exact horizon/task"})
            continue
        value, count = er._calib_lookup(cal, row["x"])
        record = {**row, "task": "expected_excess_return", "x": value,
                  "objective_version": "train_only_return_calibration:"+row["objective_version"]}
        if row.get("rel_return") is not None:
            record["y"] = row["rel_return"]
        output.append(record)
        provenance["available"][policy.digest(record)] = {"calibration_hash": policy.digest(cal),
            "training_record_hashes": sorted(policy.digest(r) for r in training), "cutoff": cutoff,
            "original_component": row["component"],
            "compatibility_view": "investigator:adapter is a numerical API shim, not original investigator evidence",
            "bin_count": count, "method": "existing expected_return._calibration/_calib_lookup; price-close excess units"}
    return output, provenance
