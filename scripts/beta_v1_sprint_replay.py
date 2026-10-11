"""Bounded, explicit-input Beta replay; no runtime discovery or store mutation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services import beta_v1_policy as policy
from backend.services import beta_v1_replay as replay


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _prices(manifest: dict, rows: list[dict]) -> pd.DataFrame:
    files = manifest.get("files") or []
    if not files or not manifest.get("price_basis") or len(files) > 3:
        raise ValueError("explicit small homogeneous price manifest required")
    symbols = sorted({str(r.get("ticker")) for r in rows if r.get("ticker")} |
                     {str(r.get("benchmark")) for r in rows if r.get("benchmark")})
    if len(symbols) > 5000 or not rows:
        raise ValueError("empty/oversized requested symbol cohort")
    minimum = min(pd.Timestamp(r["made_at"]).tz_convert("UTC").tz_localize(None).normalize() for r in rows)
    maximum = max(pd.Timestamp(r["resolved_at_date_only"])+pd.Timedelta(days=1) for r in rows)
    frames = []
    for source in files:
        path = Path(source["path"])
        if (source.get("price_basis") != manifest["price_basis"]
                or path.stat().st_size != source.get("bytes") or path.stat().st_size > 40*1024*1024):
            raise ValueError("price file basis/size contract mismatch")
        before = _file_hash(path)
        if before != source["sha256"]:
            raise ValueError("price file pin mismatch")
        import pyarrow.parquet as pq
        date_type = pq.ParquetFile(path).schema_arrow.field("date").type
        filter_min = minimum.tz_localize("UTC") if getattr(date_type, "tz", None) == "UTC" else minimum
        filter_max = maximum.tz_localize("UTC") if getattr(date_type, "tz", None) == "UTC" else maximum
        frame = pd.read_parquet(path, columns=["symbol", "date", "close"], filters=[
            ("symbol", "in", symbols), ("date", ">=", filter_min), ("date", "<", filter_max)])
        if _file_hash(path) != before:
            raise ValueError("price source changed during bounded read")
        if len(frame) > 500_000:
            raise ValueError("price projection exceeds row cap")
        frames.append(frame)
    joined = pd.concat(frames, ignore_index=True)
    joined["date"] = pd.to_datetime(joined["date"])
    if joined["date"].dt.tz is not None:
        if str(joined["date"].dt.tz) != "UTC" or not (joined["date"].dt.hour == 0).all():
            raise ValueError("daily index normalization allowed only for explicit UTC midnight dates")
        # Preserve the original UTC date-selection rule and all price values.
        # This is a documented index adapter, never adjustment/basis conversion.
        joined["date"] = joined["date"].dt.tz_localize(None)
    if joined.groupby(["symbol", "date"])["close"].nunique(dropna=False).gt(1).any():
        raise ValueError("conflicting price-source overlaps; refusing provider/order selection")
    joined = joined.drop_duplicates(["symbol", "date"]).sort_values(["date", "symbol"])
    return joined.pivot(index="date", columns="symbol", values="close")


def run(args) -> dict:
    budget = replay.RunBudget()
    execution_paths = (__file__, replay.__file__, policy.__file__, policy.kernels.__file__, replay.belief.__file__,
        replay.er.__file__, replay.er.fr.__file__, str(Path(__file__).resolve().parents[1]/"backend/services/forecast_grader.py"))
    source_pins = {str(p): _file_hash(Path(p)) for p in execution_paths}
    out = Path(args.output).resolve()
    if out.name != "beta_v1_sprint_replay.json":
        raise ValueError("output must be explicitly named beta_v1_sprint_replay.json")
    workspace = Path(__file__).resolve().parents[1]
    if out.is_relative_to(workspace):
        raise ValueError("private replay artifact must be outside the source/production checkout")
    budget.check("before input read")
    projection = replay.load_projection(args.projection, expected_sha256=args.projection_sha256)
    # No protected/source store discovery: caller must grant exact frozen files.
    manifest = json.loads(Path(args.price_manifest).read_text(encoding="utf-8-sig"))
    if "native_price_manifest" in manifest:
        manifest = manifest["native_price_manifest"]
    rows = projection["graded_projection_private"]
    budget.check("before price projection", records=len(rows))
    prices = _prices(manifest, rows)
    price_manifest = {**manifest, "source_hashes": {f["path"]: f["sha256"] for f in manifest["files"]}}
    joined = replay.reconstruct(rows, prices, price_manifest=price_manifest,
        projection_sha256=args.projection_sha256, allow_unknown_prior=args.allow_unknown_prior, budget=budget)
    original = replay.original_forward(projection)
    budget.accounting.update(original_graded_rows=original["graded_rows_in_projection"],
        original_unresolved_rows=original["unresolved_rows_in_projection"],
        original_gate_counts=original["original_projection_gate_counts"],
        grade_verification_counts=joined["verification_counts"],
        qualified_policy_rows=len(joined["records"]), original_loss_scorecards=original["cells"])
    # Full cumulative vintages are immutable sidecars stored once; the main
    # replay holds only compact references. No duplicate full replay in memory.
    def save_vintage(vintage):
        return str(policy.save(vintage, out.parent/"weight_vintages"))
    paired = replay.chronological_replay(joined, budget=budget, artifact_sink=save_vintage)
    repeat = replay.chronological_replay(joined, budget=budget, hash_only=True)
    if paired["artifact_hash"] != repeat["artifact_hash"]:
        raise ValueError("no-new-outcomes replay is not idempotent")
    if source_pins != {str(p): _file_hash(Path(p)) for p in execution_paths}:
        raise ValueError("executed source dependencies changed during run")
    payload = {"schema": "beta_v1_sprint_replay/1", "mode": "RETROSPECTIVE_DEVELOPMENT_ONLY",
        "projection_sha256": args.projection_sha256, "price_manifest_hash": policy.digest(price_manifest),
        "original_forward": original, "join": joined, "paired_replay": paired,
        "no_new_outcomes_rerun": {"identical": True, "artifact_hash": repeat["artifact_hash"]},
        "coverage": {"forecast_made_range": projection["forecast_aggregate"].get("forecast_made_date_range"),
            "forecast_resolved_range": projection["forecast_aggregate"].get("resolved_date_range"),
            "analyst_formation_availability": projection["analyst_revision_projection_private"].get("six_month_formation_availability"),
            "six_month_claim": "UNAVAILABLE: April-August authentic contemporaneous acquisition not present"},
        "current_portfolio": {"status": "UNAVAILABLE", "reason": "authentic current numerical features/quotes/mandate must be independently supplied"},
        "source_pins_before_after": source_pins,
        "source_reader_execution_pins": projection.get("source_pins", []),
        "source_reader_self_pin_status": "runner self hash absent from projection; postscan source hash is not execution proof",
        "source_reader_postscan_edits": "bool terminal mapping/compact array edits not rerun; projection remains original execution evidence",
        "resource_contract": budget.contract(),
        "price_index_adapter": "explicit UTC-midnight dates become naive same UTC dates for original grader; values unchanged",
        "production_activation": False}
    payload["artifact_hash"] = policy.digest(payload)
    budget.check("before final output", output_bytes=replay.json_bytes(payload))
    out.parent.mkdir(parents=True, exist_ok=True)
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
    if out.exists():
        expected = hashlib.sha256()
        for chunk in encoder.iterencode(payload):
            expected.update(chunk.encode("utf-8"))
        if _file_hash(out) != expected.hexdigest():
            raise ValueError("immutable output collision; select another private vintage directory")
    else:
        temporary = out.with_suffix(".incomplete")
        try:
            with temporary.open("x", encoding="utf-8", newline="") as handle:
                for chunk in encoder.iterencode(payload):
                    handle.write(chunk)
            budget.check("after output serialization", output_bytes=temporary.stat().st_size)
            temporary.replace(out)
        finally:
            if temporary.exists():
                temporary.unlink()
    # Aggregates only; original/private normalized rows never printed.
    return {"artifact_hash": payload["artifact_hash"], "output": str(out),
        "original_graded": original["graded_rows_in_projection"], "qualified_policy_rows": len(joined["records"]),
        "verification_counts": joined["verification_counts"], "paired_decisions": len(paired["decisions"]),
        "no_new_outcomes_identical": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projection", required=True)
    parser.add_argument("--projection-sha256", required=True)
    parser.add_argument("--price-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-unknown-prior", action="store_true",
                        help="Explicit owner-authorized conservative UNKNOWN-root PRIOR_ONLY mode")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), sort_keys=True))
    except replay.ReplayLimitExceeded as exc:
        # A refusal is not a partial success. Preserve source execution pins and
        # exact measured limit without writing an incomplete review artifact.
        receipt = {**exc.report, "completed": False, "projection_sha256": args.projection_sha256,
                   "source_pins": {str(p): _file_hash(Path(p)) for p in
                    (__file__, replay.__file__, policy.__file__, policy.kernels.__file__, replay.belief.__file__, replay.er.__file__, replay.er.fr.__file__)}}
        path = Path(args.output).with_suffix(".refused.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            json.dump(receipt, handle, sort_keys=True)
        print(json.dumps(receipt, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
