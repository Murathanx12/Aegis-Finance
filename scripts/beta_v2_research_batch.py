"""Bounded existing-data qualification, not a research executor or return test.

Reads an existing catalogue and explicit local inputs. Prints a resumable
manifest to stdout; never writes a catalogue, database, trial, ledger or NAV.
Optional installed pyarrow supports bounded structural diagnostics only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "aegis-beta-v2-research-qualification/2"
DECOMPRESS_LIMIT = 16 * 1024 * 1024
BASE = "backend/data/optimus/"
# Explicit reuse targets, never a filesystem walk or an acquisition request.
INPUTS = (
    ("rf_series", "rf_nr", BASE + "crsp_rebuild/revision_tilt_series_RT_2026-09-29T1110Z_equal.parquet", ("date",), ("date",)),
    ("nr_series", "rf_nr", BASE + "crsp_rebuild/library_series_EVT_FLAT_2026-09-29T1105Z/net_raises_trend.parquet", ("__index_level_0__",), ("__index_level_0__",)),
    ("ibes_details", "rf_nr", BASE + "wrds/bulk/ibes__detusecd_xsepint.parquet", ("ticker", "analys", "anndats", "fpedats"), ("actdats", "anndats", "revdats", "fpedats")),
    ("news_panel", "news", BASE + "text_return_panel/news_returns_2025_26.parquet", ("uid", "symbol"), ("published_utc", "first_seen_utc", "pit_anchor_utc", "entry_date")),
    ("pit_universe", "news", BASE + "text_return_panel/pit_universe_vintage_2025_26.parquet", ("month", "symbol"), ("asof_session", "first_bar", "last_bar")),
    ("flow_13f", "public_flow", BASE + "wrds/tr13f_s34_1996.parquet", ("mgrno", "cusip", "rdate", "fdate"), ("rdate", "fdate")),
    ("monthly_prices", "rf_nr", BASE + "prices_deep/bars_raw_monthly.parquet", ("symbol", "date"), ("date",)),
    ("daily_delisted", "rf_nr", BASE + "prices_deep/bars_delisted_crsp.parquet", ("symbol", "date"), ("date",)),
    ("dated_supplier_edges", "supplier", None, ("supplier_id", "customer_id"), ("observed_at", "valid_from")),
    ("ciq_role_partitions", "transcripts", None, ("company_id", "call_id", "role"), ("published_at", "received_at")),
)
FAMILIES = {
    "rf_nr": {"arms": ["rf_static_control", "nr_static_control", "dynamic_rank", "event_exit", "reentry"],
              "inputs": ["rf_series", "nr_series", "ibes_details", "monthly_prices", "daily_delisted"],
              "failure_sections": ["62", "15"],
              "block": "Aggregate series cannot reconstruct point-in-time ranks or event trades. Need exact issuer/security links, availability clocks, unchanged controls and daily/event-ledger execution for exits/re-entry."},
    "news": {"arms": ["news_only", "rf_only_matched", "hybrid", "hybrid_without_news", "hybrid_without_rf"],
             "inputs": ["news_panel", "pit_universe", "ibes_details"], "failure_sections": ["64", "34"],
             "block": "Need exact same-entry RF/news joins, timezone/session-open verification, matured labels and fold-local equal-budget feature/ablation adapters. No text or labels are evaluated here."},
    "public_flow": {"arms": ["disclosure_only", "disclosure_plus_rf", "matched_no_flow"],
                    "inputs": ["flow_13f", "ibes_details"], "failure_sections": ["34"],
                    "block": "fdate/rdate are not independently verified public-receipt instants. Need actual disclosure availability, issuer mapping, reporting-lag exclusions and matched control dates."},
    "supplier": {"arms": ["direct_event", "dated_supplier_event", "permuted_edges"],
                 "inputs": ["dated_supplier_edges", "news_panel"], "failure_sections": ["12", "34"],
                 "block": "No explicit dated supplier-edge input qualified in this bounded selection. Reconcile TRIAL-THEME-SUPPLY before any new instrument; a new graph alone does not reopen the closed cell."},
    "transcripts": {"arms": ["full_call", "prepared_remarks", "management_answers", "analyst_questions", "novelty_placebo"],
                    "inputs": ["ciq_role_partitions"], "failure_sections": ["34", "64"],
                    "block": "No explicit CIQ role/question/promise partition qualified. Media transcripts are not substituted for entitled company calls. C05b must supply existing usable partitions."},
}
INTERFACES = {
    "backend/services/data_catalog.py": "inspect_parquet (read-only metadata); existing nightly task remains owner",
    "backend/services/research_daemon.py": "HypothesisJob, ResearchDaemon; do not submit qualification chores as p-value trials",
    "backend/services/research_executor.py": "JobAdapter.assert_matches, KIND_INSTRUMENT_AUDIT, Executor; later frozen universe/start/end adapters",
    "backend/services/portfolio_intelligence/trial_registry.py": "ensure_trial_registered writes SQL: NOT invoked",
    "backend/services/portfolio_intelligence/experiment_registry.py": "cumulative_trial_count initializes DB: NOT invoked; raw historical trial denominator unknown",
    "scripts/night_e1_news_return_panel.py": "_entry_session, _pit_verify; build/append writes panels: NOT invoked",
    "scripts/night_exit_rules.py": "walk_one/run_arm daily path execution; not invoked or re-run against closed cells",
}


def fingerprint(value: object) -> str:
    def temporal(item: object) -> str:
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        raise TypeError("unsupported fingerprint value")
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    default=temporal, allow_nan=False).encode()).hexdigest()


def strict_json(raw: bytes | str) -> object:
    def reject(token: str) -> None:
        raise ValueError("nonfinite JSON: " + token)
    def number(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            reject(token)
        return value
    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(raw, parse_constant=reject, parse_float=number, object_pairs_hook=pairs)


def is_hash(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is not None


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def local_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or any(c in relative for c in "*?[]:\x00"):
        raise ValueError("explicit relative dataset path required")
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or ".." in Path(relative).parts or not path.is_relative_to(root.resolve()):
        raise ValueError("dataset escapes runtime root")
    return path


def _clock(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo is not None else None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            if len(value) == 10:
                return date.fromisoformat(value).isoformat()
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo is not None else None
        except ValueError:
            return None
    return None


def structural_diagnostic(rows: list[dict], keys: tuple, clocks: tuple) -> dict:
    """Count structural defects only; never read or compute return statistics."""
    if not keys or any(not isinstance(k, str) or not k for k in (*keys, *clocks)):
        raise ValueError("explicit key/clock columns required")
    seen, duplicates, missing_keys, invalid_keys = set(), 0, 0, 0
    clock_summary = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("sample rows must be objects")
        values = tuple(row.get(k) for k in keys)
        if any(v is None or (isinstance(v, str) and not v.strip()) for v in values):
            missing_keys += 1
            continue
        if any(isinstance(v, bool) or not isinstance(v, (str, int, float, date, datetime)) or
               (isinstance(v, float) and not math.isfinite(v)) for v in values):
            invalid_keys += 1
            continue
        encoded = fingerprint(values)
        duplicates += int(encoded in seen)
        seen.add(encoded)
    for clock in clocks:
        vals = [_clock(r.get(clock)) for r in rows]
        good = [v for v in vals if v is not None]
        clock_summary[clock] = {"present": len(good), "missing_or_invalid": len(rows) - len(good),
                                "date_labels": sum(len(v) == 10 for v in good),
                                "aware_instants": sum(len(v) != 10 for v in good),
                                "timezone_policy": "naive datetimes unresolved; date labels are not availability instants",
                                "sample_min": min(good) if good and len({len(v) == 10 for v in good}) == 1 else None,
                                "sample_max": max(good) if good and len({len(v) == 10 for v in good}) == 1 else None}
    return {"kind": "data_integrity_baseline", "sampled_rows": len(rows),
            "missing_key_rows": missing_keys, "invalid_key_rows": invalid_keys, "duplicate_key_rows": duplicates,
            "defects_observed": bool(missing_keys or invalid_keys or duplicates or
                                     any(x["missing_or_invalid"] for x in clock_summary.values())),
            "clocks": clock_summary, "population_claim": False,
            "lookahead_validation": "not established by clock presence", "returns_evaluated": False}


def inspect_input(spec: tuple, catalog_row: dict | None, runtime: Path, *,
                  max_file_bytes: int, sample_rows: int, prior: dict | None = None) -> dict:
    if type(sample_rows) is not int or not 1 <= sample_rows <= 128 or type(max_file_bytes) is not int or not 1 <= max_file_bytes <= 64 * 1024**2:
        raise ValueError("bounded sample/file limits required")
    identifier, family, relative, keys, clocks = spec
    out = {"id": identifier, "family": family, "path": relative, "status": "blocked",
            "observed_sha256": None, "sampled_rows": 0, "pit_status": "unverified", "readiness": "unqualified"}
    def discard_diagnostic():
        if "diagnostic" in out:
            out["attempted_sample_rows"] = out["sampled_rows"]
            out["diagnostic_discarded"] = True
            out.pop("diagnostic")
            out.pop("sample_fraction_of_footer_rows", None)
            out["sampled_rows"] = 0
    if relative is None:
        out["reason"] = "No exact existing input bound; no acquisition or substitute selected."
        return out
    if catalog_row is None:
        out["reason"] = "Exact path absent from supplied catalogue; local discovery not attempted."
        return out
    out["catalogue"] = {k: catalog_row.get(k) for k in ("rows", "date_range", "schema_hash", "content", "provenance", "consumers")}
    try:
        path = local_path(runtime, relative)
        if not path.is_file():
            out["reason"] = "Catalogued input missing locally."
            return out
        size = path.stat().st_size
        out["bytes"] = size
        if size > max_file_bytes:
            out["reason"] = "Per-file read budget exceeded; no hash/sample attempted."
            return out
        # Hash twice around diagnostics, and refuse if the live file changes.
        observed = hash_file(path)
        out["observed_sha256"] = observed
        expected = catalog_row.get("content")
        if not isinstance(expected, dict) or expected.get("mode") != "full" or not is_hash(expected.get("sha256")):
            out["reason"] = "Catalogue has no exact full-content expected hash; sampled/listing hashes cannot qualify bytes."
            return out
        if observed != expected["sha256"]:
            out.update(status="changed", reason="Current bytes differ from dated catalogue; review a new explicit version before use.")
            return out
        if prior:
            # Never trust cached diagnostic values from a mutable JSON artifact.
            out["resume"] = "rehash_and_recompute_bounded_structure; prior diagnostic not trusted"
        import pyarrow.parquet as pq
        # Reuse the existing catalogue's read-only schema/clock inspector, NOT its task runner.
        from backend.services.data_catalog import inspect_parquet
        info = inspect_parquet(path)
        out["metadata"] = info
        pf = pq.ParquetFile(path)
        columns = list(pf.schema_arrow.names)
        if len(columns) != len(set(columns)):
            raise ValueError("duplicate parquet column names")
        missing = sorted((set(keys) | set(clocks)) - set(columns))
        out["missing_required_columns"] = missing
        if not is_hash(catalog_row.get("schema_hash"), 16) or info["schema_hash"] != catalog_row.get("schema_hash"):
            out["reason"] = "Current schema differs from catalogue or expected schema hash unknown."
        elif missing:
            out["reason"] = "Required key/clock columns absent; do not substitute a field silently."
        else:
            selected = list(dict.fromkeys((*keys, *clocks)))
            # Even iter_batches may decompress a full column chunk. Bound that first.
            md = pf.metadata
            positions = {md.schema.column(i).path: i for i in range(md.num_columns)}
            sizes = [md.row_group(0).column(positions[c]).total_uncompressed_size for c in selected] if md.num_row_groups else []
            if any(type(size) is not int or size < 0 for size in sizes):
                raise ValueError("unknown/invalid selected-column decompression bound")
            first_group_bytes = sum(sizes)
            out["selected_first_rowgroup_uncompressed_bytes"] = first_group_bytes
            out["selected_columns"] = selected
            out["sample_scope"] = "first row-group prefix only; not random or population coverage"
            if first_group_bytes > DECOMPRESS_LIMIT:
                out["reason"] = "Selected row-group columns exceed 16 MiB decompression budget; metadata only."
            else:
                batch = next(pf.iter_batches(batch_size=sample_rows, row_groups=[0], columns=selected, use_threads=False), None) if md.num_row_groups else None
                sample = batch.to_pylist() if batch is not None else []
                out["diagnostic"] = structural_diagnostic(sample, keys, clocks)
                out["sampled_rows"] = len(sample)
                out["sample_fraction_of_footer_rows"] = len(sample) / md.num_rows if md.num_rows else None
                out["status"] = "structure_checked" if sample else "blocked"
                out["reason"] = "Bounded first-batch integrity diagnostic only; PIT joins, calibration and strategy validity remain unqualified."
        if hash_file(path) != observed:
            out.update(status="changed", reason="Source changed during bounded qualification; discard diagnostic.")
            discard_diagnostic()
    except (OSError, ValueError, ImportError, KeyError, TypeError) as exc:
        out["status"] = "blocked"
        discard_diagnostic()
        out["reason"] = f"Inspection unavailable: {type(exc).__name__}: {exc}"
    return out


def arms(inputs: list[dict]) -> list[dict]:
    indexed = {x["id"]: x for x in inputs}
    output = []
    for family, declaration in FAMILIES.items():
        missing = [i for i in declaration["inputs"] if indexed[i]["status"] != "structure_checked"]
        for name in declaration["arms"]:
            output.append({"id": "P3:" + family + ":" + name, "family": family, "variant": name,
                           "status": "blocked_not_evaluated", "input_ids": declaration["inputs"],
                           "unqualified_structural_inputs": missing,
                           "blockers": [declaration["block"], "No new pre-registration committed or trial row inserted by this qualification.",
                                        "Per-arm null/injected-edge instrument calibration, maturity purge, power/effect bounds, fair net costs and borrow exclusions are not qualified."],
                           "prior_failure_refs": ["NEGATIVE_RESULTS.md §" + s for s in declaration["failure_sections"]],
                           "registration_id": None, "p_value": None, "observed_effect": None,
                           "next_consumer": "research_executor.JobAdapter / KIND_INSTRUMENT_AUDIT after source and instrument qualification"})
    return output


def build_manifest(catalogue: Path, runtime: Path, *, root: Path = ROOT, limit: int = 10,
                   sample_rows: int = 64, max_file_bytes: int = 64 * 1024 * 1024,
                   prior: dict | None = None) -> dict:
    if (any(type(x) is not int for x in (limit, sample_rows, max_file_bytes)) or
            not 1 <= limit <= len(INPUTS) or not 1 <= sample_rows <= 128 or not 1 <= max_file_bytes <= 64 * 1024 * 1024):
        raise ValueError("limits require 1..10 inputs, 1..128 rows, <=64 MiB/file")
    if catalogue.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("catalogue exceeds 16 MiB JSON bound")
    raw = catalogue.read_bytes()
    data = strict_json(raw)
    if not isinstance(data, dict) or data.get("schema_version") != "data_catalog/1" or not isinstance(data.get("rows"), list):
        raise ValueError("unsupported catalogue schema")
    stamp = _clock(data.get("utc"))
    if stamp is None or len(stamp) == 10 or datetime.fromisoformat(stamp) > datetime.now(timezone.utc):
        raise ValueError("catalogue requires a nonfuture aware run clock")
    catalog_hash = hashlib.sha256(raw).hexdigest()
    neg = root / "NEGATIVE_RESULTS.md"
    canon = root / "docs/CANON.md"
    code = Path(__file__)
    contract = {"catalogue_sha256": catalog_hash, "runtime_root": runtime.resolve().as_posix(),
                "negative_results_sha256": hash_file(neg), "canon_sha256": hash_file(canon),
                "tool_sha256": hash_file(code), "input_plan_sha256": fingerprint(INPUTS),
                "sample_rows": sample_rows, "max_file_bytes": max_file_bytes,
                "decompression_limit": DECOMPRESS_LIMIT, "family_plan_sha256": fingerprint(FAMILIES),
                "interface_hashes": {p: hash_file(root / p) if (root / p).is_file() else None for p in INTERFACES}}
    # No body reads or evaluation precede the mandatory negative-results inventory.
    negative_text = neg.read_text(encoding="utf-8")
    for number in sorted({s for f in FAMILIES.values() for s in f["failure_sections"]}):
        if "## " + number + "." not in negative_text:
            raise ValueError("required known-failure section missing: " + number)
    indexed = {}
    for row in data["rows"]:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str) or not row["path"]:
            raise ValueError("invalid catalogue row/path")
        if row.get("path") in indexed:
            raise ValueError("duplicate catalogue path: " + row["path"])
        indexed[row.get("path")] = row
    previous, offset = {}, 0
    if prior is not None:
        if not isinstance(prior, dict) or prior.get("schema") != SCHEMA or fingerprint(prior.get("contract")) != fingerprint(contract):
            raise ValueError("resume contract changed; keep prior receipt and start a reviewed fresh qualification")
        if (prior.get("readiness") != "unknown_not_qualified" or prior.get("activation_authorized") is not False or
                prior.get("status") != "qualification_only_research_blocked" or
                any(prior.get("denominators", {}).get(k) != 0 for k in
                    ("arm_evaluations_attempted", "research_results", "new_registered_trials"))):
            raise ValueError("unknown or promoted resume readiness")
        prior_clock = _clock(prior.get("observed_at"))
        if prior_clock is None or len(prior_clock) == 10 or datetime.fromisoformat(prior_clock) > datetime.now(timezone.utc):
            raise ValueError("invalid resume observation clock")
        offset = prior["checkpoint"]["next_offset"]
        if type(offset) is not int or not 0 <= offset <= len(INPUTS):
            raise ValueError("invalid resume cursor")
        if (prior["checkpoint"].get("total_inputs") != len(INPUTS) or
                prior["checkpoint"].get("qualification_pass_complete") is not (offset == len(INPUTS)) or
                prior["checkpoint"].get("research_complete") is not False):
            raise ValueError("inconsistent resume checkpoint")
        rows = prior.get("inputs")
        if not isinstance(rows, list) or [x.get("id") for x in rows if isinstance(x, dict)] != [s[0] for s in INPUTS]:
            raise ValueError("invalid resume input IDs/order")
        for position, (row, spec) in enumerate(zip(rows, INPUTS)):
            if (row.get("family") != spec[1] or row.get("path") != spec[2] or
                    row.get("pit_status") != "unverified" or row.get("readiness") != "unqualified" or
                    row.get("status") not in {"blocked", "changed", "structure_checked", "not_attempted"} or
                    (row["status"] == "not_attempted") != (position >= offset)):
                raise ValueError("invalid resume input state/cursor")
        previous = {x["id"]: x for x in prior["inputs"]}
    stop = min(len(INPUTS), offset + limit)
    results = []
    for position, spec in enumerate(INPUTS):
        if position < stop:
            results.append(inspect_input(spec, indexed.get(spec[2]), runtime,
                max_file_bytes=max_file_bytes, sample_rows=sample_rows, prior=previous.get(spec[0]) if position < offset else None))
        else:
            results.append({"id": spec[0], "family": spec[1], "path": spec[2], "status": "not_attempted", "pit_status": "unverified", "readiness": "unqualified"})
    plan = arms(results)
    families_attempted = sorted({r["family"] for r in results if r["status"] != "not_attempted"})
    diagnostic_families = sorted({r["family"] for r in results if r.get("diagnostic", {}).get("sampled_rows", 0)})
    interface_reads = []
    for path, role in INTERFACES.items():
        source = root / path
        interface_reads.append({"path": path, "role": role, "sha256": hash_file(source) if source.is_file() else None,
                                "status": "source_read" if source.is_file() else "missing"})
    if (hash_file(catalogue) != catalog_hash or hash_file(code) != contract["tool_sha256"] or
            hash_file(neg) != contract["negative_results_sha256"] or hash_file(canon) != contract["canon_sha256"] or
            any(hash_file(root / p) != h for p, h in contract["interface_hashes"].items() if h)):
        raise ValueError("catalogue/interface source changed during qualification")
    return {"schema": SCHEMA, "observed_at": datetime.now(timezone.utc).isoformat(),
            "readiness": "unknown_not_qualified",
            "status": "qualification_only_research_blocked", "runtime_status": "not_assessed", "activation_authorized": False,
            "contract": contract, "catalogue": {"path": catalogue.as_posix(), "run_id": data.get("run_id"), "utc": data.get("utc"),
                "listed_rows": len(data["rows"]), "scope": "catalogue metadata indexed; only selected inputs byte/schema/sample inspected; no population readiness claim"},
            "interfaces": interface_reads, "inputs": results, "arms": plan,
            "denominators": {"planned_families": len(FAMILIES), "planned_arms": len(plan), "input_slots": len(INPUTS),
                "qualification_families_attempted": families_attempted, "actual_diagnostic_families": diagnostic_families,
                "arm_evaluations_attempted": 0, "research_results": 0, "new_registered_trials": 0, "historical_cumulative_trials": None},
            "checkpoint": {"next_offset": stop, "total_inputs": len(INPUTS), "qualification_pass_complete": stop == len(INPUTS),
                           "research_complete": False, "resume_method": "Rehash and recompute bounded samples for prior prefix; no prior diagnostic values trusted. Limit counts new slots, rechecks can cover all 10 slots."},
            "acceptance_requirements": {"instrument": "Per-arm known-null and injected-edge calibration on the same data grade/segments/costs; report measured FPR, power and MDE before wins or kills.",
                "validation": "Freeze discovery/validation split, fit transformations within folds, purge label maturity plus embargo, preserve independent finalist replication.",
                "execution": "Same clocks/entries/costs; daily trade/event ledger for path dependence; borrow unavailable means excluded with denominator, not zero cost.",
                "denominator": "Retain every proposed, blocked, invalid and underpowered arm; raw cumulative historical trials stays unknown until existing read-only evidence binds it.",
                "controls": "Hash unchanged control inputs/configs; no tuning based on observed outcomes; scoped conditional results and revisit conditions.",
                "consumer": "This CLI reads catalogue and selected input bytes; no strategy evaluation or daemon submission occurred."}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--prior-manifest", type=Path)
    parser.add_argument("--prior-sha256", help="required exact file hash with --prior-manifest")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--sample-rows", type=int, default=64)
    args = parser.parse_args(argv)
    try:
        prior = None
        if args.prior_manifest:
            if not is_hash(args.prior_sha256) or args.prior_manifest.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("bounded prior manifest and explicit SHA256 required")
            prior_raw = args.prior_manifest.read_bytes()
            if hashlib.sha256(prior_raw).hexdigest() != args.prior_sha256:
                raise ValueError("prior manifest hash mismatch")
            prior = strict_json(prior_raw)
        elif args.prior_sha256:
            raise ValueError("prior hash requires explicit prior manifest")
        if args.prior_manifest and not isinstance(prior, dict):
            raise ValueError("prior manifest must be an object")
        result = build_manifest(args.catalogue, args.runtime_root, limit=args.limit, sample_rows=args.sample_rows, prior=prior)
        if args.prior_manifest:
            result["prior_manifest_ref"] = {"path": str(args.prior_manifest), "sha256": args.prior_sha256}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "refused", "error": str(exc), "activation_authorized": False}))
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    # 0 = readable qualification manifest; never runnable/research success.
    return 0


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
