"""Read-only current-cache consumer inspection; PRODUCT_EXPERIMENT, no activation.

BOUND_ONLY legacy interpretations are context, not a semantic quality pass.
News-to-E[r] remains BLOCKED until a reviewed production consumer wire exists.
Run in a fresh process with --runtime-root, --frozen-inputs and --out.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
from collections import Counter
from unittest.mock import patch


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, default=str), encoding="utf-8")


def known(value, cutoff: datetime) -> bool:
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.tzinfo is not None and stamp <= cutoff
    except (TypeError, ValueError):
        return False


def outcome_rows(rows: list[dict], cutoff: datetime) -> list[dict]:
    """Only dated, already resolved actual news outcomes may update trust.

    The legacy grader writes a calendar DAY, not an intraday availability
    timestamp. Admit only prior days, conservatively at their UTC day's end;
    same-day/undated outcomes remain unknown. This is receipt-time descriptive
    grading, not certification of historical intraday availability.
    """
    if cutoff.tzinfo is None:
        return []
    cutoff_utc = cutoff.astimezone(timezone.utc)

    def aware(value):
        try:
            stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return stamp if stamp.tzinfo is not None else None
        except (TypeError, ValueError):
            return None

    def resolved(value):
        if isinstance(value, str) and len(value) == 10:
            stamp = aware(value + "T23:59:59.999999+00:00")
            return stamp if stamp is not None and stamp.date() < cutoff_utc.date() else None
        return aware(value)

    admitted = []
    for row in rows:
        if not str(row.get("specialist", "")).startswith("news_digest:") or row.get("outcome") not in (0, 1):
            continue
        markers = ("void_reason", "voided_at", "voided_by", "voided", "quarantined",
                   "quarantine_reason", "quarantined_at")
        if any(row.get(k) for k in markers) or any(
                str(row.get(k) or "").strip().upper() in ("VOID", "VOIDED", "QUARANTINE", "QUARANTINED")
                for k in ("state", "status", "resolution_state")):
            continue
        made, resolved_at = aware(row.get("made_at")), resolved(row.get("resolved_at"))
        if made is not None and resolved_at is not None and made <= resolved_at <= cutoff_utc:
            admitted.append(row)
    return admitted


def denied(*args, **kwargs):
    raise RuntimeError("offline pipeline forbids network, model, subprocess and broker actions")


def run(runtime: Path, frozen: Path, output: Path, *, digest_name: str) -> dict:
    from ft_lab import budgeted_decision_trace as T
    runtime, frozen, output = runtime.resolve(), frozen.resolve(), output.resolve()
    if output == runtime or runtime in output.parents or output == frozen or frozen in output.parents:
        raise ValueError("output cannot be in read-only inputs")
    if output.exists() and any(output.iterdir()):
        raise ValueError("choose a fresh isolated output namespace")
    if Path(digest_name).name != digest_name or not digest_name.startswith("world_digest_"):
        raise ValueError("digest must be an explicit basename")
    T.protect_runtime(runtime)
    T.protect_runtime(frozen)
    os.environ["AEGIS_DATA_DIR"] = str(output / "isolated_data")
    from backend import config
    from backend.services import world_digest as WD, world_state as WS
    from backend.services import news_source_validation as NV, forecast_ledger as FL
    from backend.services import expected_return as ER, pc_broker as PB
    from scripts import sim_run as S
    import pandas as pd
    if output not in Path(config.OPTIMUS_LEDGER_DIR).resolve().parents:
        raise RuntimeError("consumer imported before store isolation")
    digest_path = runtime / "digest" / digest_name
    cache_file = WD.cache_path(runtime)
    ledger_path = runtime / "predictions.jsonl"
    if FL.backend_for(ledger_path).kind != "legacy":
        raise ValueError("current bounded snapshot supports only the verified legacy ledger")
    original_paths = (digest_path, cache_file, ledger_path)
    original_pins = {str(p): sha(p) for p in original_paths}
    copies = {}
    for path in original_paths:
        target = output / "frozen_originals" / path.relative_to(runtime)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        if sha(target) != original_pins[str(path)]:
            raise RuntimeError("input changed during immutable snapshot copy")
        copies[path] = target
    original = json.loads(copies[digest_path].read_text(encoding="utf-8"))
    ids = original["writes"]["prediction_ids"]
    ledger = FL.read_rows(copies[ledger_path])
    current = [r for r in ledger if r.get("prediction_id") in set(ids)]
    if len(current) != len(ids) or len(set(ids)) != len(ids):
        raise ValueError("current digest forecast identities missing or ambiguous")
    cutoff_text = max(r["made_at"] for r in current)
    cutoff = datetime.fromisoformat(cutoff_text)
    asof = cutoff.date().isoformat()
    learned = outcome_rows(ledger, cutoff)
    del ledger
    if any(r.get("outcome") is not None for r in current):
        raise ValueError("this pending-current-forecast trace refuses invented/late outcomes")
    collected = WD.collect(datetime.fromisoformat(original["window"]["since"]),
                           datetime.fromisoformat(original["window"]["until"]), root=runtime)
    write(output / "frozen_originals" / "collected_items.json", [asdict(item) for item in collected["items"]])
    cache = WD.read_cache(copies[cache_file])
    bindings, rejected, items = [], [], []
    for item in collected["items"]:
        cached = cache.get(WD.cache_key(item))
        if not cached:
            rejected.append({"item_id": item.item_id, "reason": "no_exact_cached_interpretation"})
            continue
        try:
            bindings.append(NV.validate_cached(item, cached, cutoff_utc=cutoff_text))
            items.append(item)
        except NV.SourceValidationError as exc:
            rejected.append({"item_id": item.item_id, "reason": str(exc)})
    urls = {}
    for binding in bindings:
        urls.setdefault(WD.norm_url(binding["source_url"]), []).append(binding["item_id"])
    forecast_bindings = [{"prediction_id": r["prediction_id"],
        "source_urls": [{"url": u, "bound_item_ids": urls.get(WD.norm_url(u), [])}
                        for u in (r.get("inputs_used") or {}).get("source_urls", [])],
        "quality": "BOUND_ONLY; source URL lineage is not semantic validation"} for r in current]
    with ExitStack() as guard:
        guard.enter_context(patch.object(socket.socket, "connect", denied))
        guard.enter_context(patch.object(socket, "create_connection", denied))
        meter = WD.Meter(0.0, llm=denied)
        extracted = WD.extract_items(items, meter, cache=cache, stage_cap=0.0,
                                     workers=1, cache_file=output / "unused_cache.jsonl", local_runner=denied)
        if meter.calls or meter.spent or extracted["n_new_single"] or extracted["n_new_headline_batches"]:
            raise RuntimeError("cache-only extraction acquired new work")
        grade = WD.grade(learned)
        grades_by_horizon = {str(h): WD.grade([r for r in learned if r.get("horizon_days") == h])
                             for h in sorted({r["horizon_days"] for r in learned})}
        no_outcomes = WD.grade([])
        mirrors = {}
        for variant, g in (("learned", grade), ("without_outcomes", no_outcomes)):
            mirror = output / variant
            # Preserve all original shadow metadata/flags; update only the
            # grade and its earned trust under the existing aggregate contract.
            shadow = {**original["shadow"], "grade": g,
                      "trust_dir": g["direction"]["trust"], "trust_size": g["size"]["trust"]}
            write(mirror / "digest" / digest_name, {**original, "shadow": shadow})
            mirrors[variant] = mirror
        snap_rows = [json.loads(x) for x in (frozen / "pc_book/2026-10-09/nav.jsonl").read_text().splitlines()]
        snapshot = max((r for r in snap_rows if known(r["t"], cutoff)), key=lambda r: r["t"])
        snapshot = {k: snapshot[k] for k in ("t", "equity", "cash", "n_positions", "positions")}
        symbols = [s["ticker"] for s in T.SPECS]
        bars = pd.read_parquet(frozen / "prices_2025_26/bars.parquet")
        bars = bars[pd.to_datetime(bars.date, utc=True) < pd.Timestamp(cutoff)]
        prices = {str(t): float(g.sort_values("date").iloc[-1].close) for t, g in bars.groupby("symbol")}
        if any(t not in prices for t in symbols + [p["symbol"] for p in snapshot["positions"]] + ["SPY"]):
            raise ValueError("stored price missing")
        revisions = pd.read_parquet(frozen / "analyst/target_revisions.parquet")
        revisions = revisions[pd.to_datetime(revisions.first_seen_utc, utc=True, errors="coerce") <= pd.Timestamp(cutoff)]
        sweep = json.loads((frozen / "analyst/revision_flow_sweep_2026-09-25.json").read_text())
        if not known(sweep["written_utc"], cutoff):
            raise ValueError("sweep not known at cutoff")
        guard.enter_context(patch.object(PB, "snapshot", lambda **kw: snapshot))
        guard.enter_context(patch.object(PB, "last_prices", lambda syms: {s: prices[s] for s in syms}))
        for method in ("submit", "clock", "orders"):
            guard.enter_context(patch.object(PB, method, denied))
        variants = {}
        for variant in ("full", "without_news", "without_analyst"):
            folder = output / variant
            predictions = [] if variant == "without_news" else current
            source = ER.Sources(label="beta_news_pipeline/" + variant,
                revisions=None if variant == "without_analyst" else revisions,
                sweep=None if variant == "without_analyst" else sweep,
                predictions=predictions, decision_rows=[],
                unavailable={"regime": "offline", "ranking": "inventory only", "ibes": "not loaded"})
            ranking = {"asof": asof, "model_version": "inventory_only_not_ranker",
                       "top20_net_rel_21d": None,
                       "top": [{"symbol": t, "rank": i + 1, "calibration_measured": False} for i, t in enumerate(symbols)]}
            source.ranking = ranking
            write(folder / "ranking.json", ranking)
            write(folder / "funnel.json", {"generated_at": cutoff_text,
                  "evidence_basis": {"ranked_by": ["frozen_source_inventory"]}, "candidates": []})
            forecast = ER.build(asof, symbols, source, out_dir=folder / "forecast")
            plan = S.u_plan(folder, "research", asof=asof, funnel_path=folder / "funnel.json",
                ledger_path=folder / "decision_ledger.jsonl", contracts_dir=folder / "contracts",
                er_sources=source, er_dir=folder / "planner_forecast", now_utc=cutoff)
            book = json.loads((folder / "intended_book.json").read_text())
            if book["sent"] or book["acting"] or plan.get("n_sent"):
                raise RuntimeError("isolated plan acquired execution authority")
            variants[variant] = {"forecast": forecast["names"], "book": book["book"],
                                 "plan": plan, "forecast_writers": forecast["forecast_writers"]}
        weights = original["shadow"]["base_weights"]
        subsequent = {v: WS.plan_news_tilt(weights, root=mirror) for v, mirror in mirrors.items()}
        for v, receipt in subsequent.items():
            if receipt["digest_file"] != digest_name:
                raise RuntimeError("subsequent consumer did not read the learned digest")
            write(output / v / "subsequent_consumer.json", receipt)
    # Actual stored failed local reply is rejected, never repaired/promoted.
    cacc_source = json.loads((frozen.parent / "sources.json").read_text())["documents"][-1]
    failed = json.loads((frozen.parent / "failed_reply_input.json").read_text())
    raw = next(iter(failed["rows"].values()))
    if hashlib.sha256(raw["raw_reply"].encode()).hexdigest() != raw["raw_sha256"]:
        raise ValueError("actual failed reply drift")
    try:
        NV.validate_article_facts(json.loads(raw["raw_reply"]), cacc_source["excerpt"],
                                  source_sha256=cacc_source["content_sha256"])
    except NV.SourceValidationError as exc:
        cacc_rejection = {"verdict": "REJECTED", "reason": str(exc), "raw_reply_sha256": raw["raw_sha256"],
                          "source_excerpt_sha256": cacc_source["content_sha256"],
                          "origin": "actual_stored_failed_p3_reply", "operative_event_date": None,
                          "reporting_date": cacc_source["reporting_date"]}
    else:
        raise RuntimeError("actual unsupported CACC date escaped validation")
    if any(sha(p) != original_pins[str(p)] for p in original_paths):
        raise RuntimeError("original input changed during consumer inspection; receipt refused")
    snapshot_pins = {str(p): sha(p) for p in [*copies.values(), output / "frozen_originals" / "collected_items.json"]}
    write(output / "frozen_originals" / "manifest.json", {"original_pins": original_pins,
          "snapshot_pins": snapshot_pins, "originals_unchanged_after_run": True,
          "scope": "exact original digest/cache/legacy-ledger bytes and exact collected Item inputs; not historical prefix certification"})
    result = {"licence": "PRODUCT_EXPERIMENT", "forecast_link": "BLOCKED_NEWS_NOT_READ_BY_DESIGN",
        "digest": digest_name, "digest_sha256": original_pins[str(digest_path)], "cutoff_utc": cutoff_text,
        "learning_selected_before_plan_asof": asof, "n_exact_current_forecasts": len(current),
        "current_outcomes": "PENDING", "current_forecast_ids": ids,
        "n_cached_source_bindings": len(bindings), "n_rejected_bindings": len(rejected),
        "binding_rejection_counts": dict(Counter(r["reason"] for r in rejected)),
        "cached_model_counts": dict(Counter(r["extract_model"] for r in bindings)),
        "interpretation_quality": "BOUND_ONLY; no held-out semantic quality pass",
        "cache_extraction": {k: v for k, v in extracted.items() if k != "rows"},
        "grade": grade, "grades_by_horizon": grades_by_horizon, "learned_consumers": subsequent,
        "news_forecast_equal": variants["full"]["forecast"] == variants["without_news"]["forecast"],
        "news_book_equal": variants["full"]["book"] == variants["without_news"]["book"],
        "analyst_forecast_equal": variants["full"]["forecast"] == variants["without_analyst"]["forecast"],
        "variants": variants, "critical_cacc_rejection": cacc_rejection,
        "new_paid_calls": 0, "model_starts": 0, "runtime_writes": 0,
        "hashes": original_pins, "immutable_original_pins": snapshot_pins,
        "limitations": ["Source binding is not semantic validation", "Sandbox planner explicitly does not read news tilt",
                        "Existing E[r] excludes news; no unsupported probability fabricated", "Today's outcomes not yet available",
                        "Aggregate trust contract preserved; no fitted model or new strategy",
                        "Legacy resolved_at day admitted at prior UTC day end; receipt-time descriptive context, not historical intraday PIT certification"]}
    write(output / "source_bindings.json", {"bindings": bindings, "rejected": rejected})
    write(output / "forecast_source_bindings.json", forecast_bindings)
    write(output / "learning_inputs.json", learned)
    write(output / "current_forecasts.json", current)
    write(output / "trace.json", result)
    return {k: v for k, v in result.items() if k not in ("variants", "learned_consumers", "grades_by_horizon", "current_forecast_ids", "hashes")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--frozen-inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--digest", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.runtime_root, args.frozen_inputs, args.out, digest_name=args.digest), sort_keys=True))
