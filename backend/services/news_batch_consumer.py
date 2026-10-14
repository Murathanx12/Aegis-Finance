"""Private admission audit and prospective batch preparation for current news.

Legacy World Digest interpretations remain context until exact source passages
and an independent current-context review exist. This module never calls a model.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import argparse
import csv
import json
import re
from pathlib import Path

from backend.services import belief_state as B
from backend.services import current_event_forecast_bridge as bridge
from backend.services import news_source_validation as NV
from backend.services import world_digest as WD


def _us_symbols(table: Path) -> set[str]:
    rows = list(csv.DictReader(table.read_text(encoding="utf-8-sig").splitlines()))
    counts = Counter(r.get("symbol") for r in rows if r.get("country") == "US")
    return {symbol for symbol, n in counts.items() if symbol and n == 1}


def propose_deterministic_context(*, item: WD.Item, typed_row: dict,
                                  ticker: str, observed_utc: str,
                                  issuer_table: Path = bridge.ISSUER_TABLE) -> dict:
    """Quote one exact source passage for review; do not claim semantic admission.

    This takes no model output as evidence. It does not infer an event date,
    market direction, expected return, or AEGIS hypothesis from article prose.
    The independent reviewer must assess the full item and any omitted claims.
    """
    if typed_row.get("item_id") != item.item_id or typed_row.get("url") != item.url:
        raise ValueError("typed row/source identity mismatch")
    if (item.kind != "article" or item.source != "sec_edgar_8k_ex99_body"
            or ticker not in typed_row.get("tickers", [])):
        raise ValueError("unsupported source or ticker")
    rows = [r for r in csv.DictReader(issuer_table.read_text(encoding="utf-8-sig").splitlines())
            if r.get("symbol") == ticker and r.get("country") == "US"]
    if len(rows) != 1 or not rows[0].get("primary_name"):
        raise ValueError("canonical US instrument absent")
    issuer = rows[0]["primary_name"]
    if issuer not in item.text:
        raise ValueError("canonical issuer not literally in source")
    NV.check_current_times(item, cutoff_utc=observed_utc)
    verbs = re.compile(r"\b(?:announced today|expects to report|has approved|reported|today announced)\b",
                       re.IGNORECASE)
    passage = None
    for match in verbs.finditer(item.text):
        start = item.text.rfind(issuer, 0, match.start())
        if start < 0 or match.start() - start > 250:
            continue
        end_match = re.search(r"\.(?:\s|$)", item.text[match.end():])
        if end_match is None:
            continue
        end = match.end() + end_match.end() - 1
        quote = item.text[start:end + 1]
        if 35 <= len(quote) <= 800 and quote in item.text:
            passage = quote
            break
    if passage is None:
        raise ValueError("no bounded literal action passage")
    passages = [passage]
    if re.search(r"\b(?:net income|revenue|earnings per share)\b", passage, re.IGNORECASE):
        tail = item.text[item.text.index(passage) + len(passage):]
        for _ in range(2):
            next_sentence = re.match(r"\s*(.{20,800}?\.(?:\s|$))", tail, re.DOTALL)
            if next_sentence is None:
                break
            extra = next_sentence.group(1).strip()
            if extra not in item.text:
                raise ValueError("adjacent actuals passage detached")
            passages.append(extra)
            tail = tail[next_sentence.end():]
    now = NV._time(observed_utc).astimezone(timezone.utc).isoformat()
    capture = {"schema": "current_news_context_capture/2",
               "cache_key": WD.context_cache_key(item),
               "extraction_identity": WD.context_extraction_identity(),
               "source_sha256": NV.content_sha256(item.title + "\n" + item.text),
               "source_item_sha256": NV.content_sha256(vars(item)),
               "started_utc": now, "completed_utc": now,
               "producer": {"kind": "DETERMINISTIC_ANNOTATION",
                            "actor": "news_batch_consumer.exact_passage_sampler_v1"},
               "annotation": {"facts": {"entity": issuer, "event_date": None,
                                        "date_precision": "unknown",
                                        "evidence_spans": passages, "numbers": [],
                                        "abstain": False},
                              "dates": [], "source_predictions": [],
                              "aegis_hypotheses": []}}
    return {"schema": "news_batch_context_proposal/1",
            "status": "EXACT_PASSAGE_CANDIDATE_NOT_SEMANTICALLY_ADMITTED",
            "item": vars(item), "ticker": ticker, "capture": capture,
            "legacy_source_claim_candidates": typed_row.get("forward_claims") or [],
            "semantic_review": None, "aegis_hypothesis": None,
            "review_required": ["full_row", "producer_origin", "date_roles",
                                "quantities_units_baselines",
                                "source_predictions_separate_from_aegis_hypotheses"]}


def audit_legacy_batch(*, items: list[WD.Item], typed_rows: list[dict],
                       cache: dict[str, dict], cutoff_utc: str,
                       issuer_table: Path = bridge.ISSUER_TABLE) -> dict:
    """Bind each cached interpretation to one raw item; grant no forecast authority.

    A legacy cache has no exact passage witnesses. Row text and issuer mentions
    cannot substitute for the independent current-context capture/review pair.
    """
    by_id = {item.item_id: item for item in items}
    if len(by_id) != len(items):
        raise ValueError("duplicate source item IDs")
    symbols = _us_symbols(issuer_table)
    seen: set[str] = set()
    audited = []
    for row in typed_rows:
        item_id = row.get("item_id")
        reasons = []
        if not isinstance(item_id, str) or item_id in seen:
            reasons.append("DUPLICATE_OR_INVALID_ITEM_ID")
        seen.add(item_id)
        item = by_id.get(item_id)
        source_hash = None
        bound = False
        if item is None:
            reasons.append("SOURCE_ITEM_MISSING")
        else:
            source_hash = NV.content_sha256(item.title + "\n" + item.text)
            if (item.kind != "article" or item.source != "sec_edgar_8k_ex99_body"
                    or row.get("url") != item.url or row.get("source") != item.source):
                reasons.append("SOURCE_IDENTITY_MISMATCH")
            cached = cache.get(WD.cache_key(item))
            if not cached or cached.get("row") != row:
                reasons.append("TYPED_CACHE_MISSING_OR_DRIFT")
            else:
                try:
                    NV.validate_cached(item, cached, cutoff_utc=cutoff_utc)
                    bound = True
                except NV.SourceValidationError as exc:
                    reasons.append(str(exc))
        names = row.get("tickers")
        if not isinstance(names, list) or len(names) != len(set(names)):
            reasons.append("TICKER_LIST_INVALID")
            names = []
        mapped = sorted(t for t in names if t in symbols)
        if not mapped:
            reasons.append("NO_CANONICAL_US_INSTRUMENT")
        if len(mapped) != len(names):
            reasons.append("UNMAPPED_TICKER_ABSTAIN")
        # The legacy extractor records neither exact quote spans nor a held-out
        # whole-row semantic review. Its claim labels remain source claims only.
        reasons.extend(("NO_EXACT_PASSAGE_WITNESS", "NO_INDEPENDENT_CONTEXT_REVIEW",
                        "NO_SEPARATELY_DECLARED_AEGIS_HYPOTHESIS"))
        audited.append({"item_id": item_id, "source_sha256": source_hash,
                        "first_seen_utc": item.first_seen_utc if item else None,
                        "published_utc": item.published_utc if item else None,
                        "cache_sha256": NV.content_sha256(cache.get(WD.cache_key(item)))
                        if item and cache.get(WD.cache_key(item)) else None,
                        "canonical_us_tickers": mapped,
                        "source_forward_claim_count": len(row.get("forward_claims") or []),
                        "legacy_cache_bound": bound,
                        "source_fact_admitted": False, "forecast_candidate": False,
                        "reasons": reasons})
    return {"schema": "news_batch_legacy_admission_audit/1",
            "cutoff_utc": cutoff_utc, "source_items": len(items),
            "typed_rows": len(typed_rows), "cases": audited,
            "bound_cache_rows": sum(c["legacy_cache_bound"] for c in audited),
            "source_admitted": 0, "forecast_candidates": 0}


def prepare_batch(*, cases: list[dict], seal_utc: str, entry_after_utc: str,
                  market: dict,
                  existing_predictions: list[dict]) -> dict:
    """One source-bound batch; delegate every case to the reviewed single-case seam.

    Only independently admitted context captures with separate AEGIS hypotheses
    can mint rows. The single-case bridge enforces fresh clocks, source quotes,
    canonical issuer and matching prior SPY/issuer price bars. No ledger write.
    """
    if not 1 <= len(cases) <= 20:
        raise ValueError("batch size out of bounds")
    source_ids, case_ids, prediction_ids = set(), set(), set()
    out = []
    for case in cases:
        if set(case) != {"item", "capture", "semantic_review", "hypothesis", "instrument"}:
            raise ValueError("case contract shape")
        item = case["item"]
        if not isinstance(item, WD.Item) or item.item_id in source_ids:
            raise ValueError("duplicate or invalid source item")
        if (item.kind != "article" or item.source != "sec_edgar_8k_ex99_body"
                or not WD.norm_url(item.url)
                or item.item_id != WD._sha(WD.norm_url(item.url))):
            raise ValueError("native SEC item ID/source URL mismatch")
        source_ids.add(item.item_id)
        result = bridge.prepare_candidate(**case, seal_utc=seal_utc,
                                          entry_after_utc=entry_after_utc,
                                          trusted_manifest_path=None,
                                          existing_predictions=existing_predictions,
                                          standalone=True,
                                          standalone_market=market)
        result["source_item_id"] = item.item_id
        result["source_item_sha256"] = case["capture"]["source_item_sha256"]
        result["source_witness"] = {"item": vars(item), "capture": case["capture"],
                                    "semantic_review": case["semantic_review"],
                                    "hypothesis": case["hypothesis"],
                                    "instrument": case["instrument"]}
        pid = result["prediction"]["prediction_id"]
        if result["case_id"] in case_ids or pid in prediction_ids:
            raise ValueError("duplicate case or prediction ID")
        case_ids.add(result["case_id"])
        prediction_ids.add(pid)
        out.append(result)
    return {"schema": "news_source_bound_candidate_batch/1",
            "status": "CANDIDATES_FOR_INDEPENDENT_REVIEW",
            "seal_utc": seal_utc, "entry_after_utc": entry_after_utc,
            "market": market,
            "candidates": out, "prediction_ids": sorted(prediction_ids),
            "source_item_ids": sorted(source_ids), "ledger_writes": 0}


def append_reviewed_batch(*, batch: dict, review: dict,
                          ledger_path: Path) -> dict:
    """Offer one reviewed prospective batch through B.append, then read it back.

    The independent review binds the *entire* candidate batch. Reviewers must
    inspect its source captures, fact references and separate hypotheses before
    approving. This function gives no authority to a legacy typed digest row.
    """
    now = datetime.now(timezone.utc)
    if (batch.get("schema") != "news_source_bound_candidate_batch/1"
            or batch.get("status") != "CANDIDATES_FOR_INDEPENDENT_REVIEW"):
        raise ValueError("candidate batch contract")
    candidates = batch.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 20:
        raise ValueError("candidate batch size")
    if (not isinstance(review, dict) or review.get("schema") != "independent_news_batch_review/1"
            or review.get("independent") is not True
            or review.get("decision") != "APPROVE_EXACT_SOURCE_BOUND_BATCH"
            or review.get("batch_sha256") != NV.content_sha256(batch)
            or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()):
        raise ValueError("independent exact-batch review missing or drifted")
    seal = NV._time(batch["seal_utc"])
    entry = NV._time(batch["entry_after_utc"])
    reviewed = NV._time(review["reviewed_utc"])
    if not seal <= reviewed <= now < entry:
        raise ValueError("review or prospective entry clock invalid")
    if ledger_path.resolve() != B.PREDICTIONS.resolve():
        raise ValueError("wrong campaign ledger path")
    case_ids, prediction_ids = set(), set()
    source_ids = set()
    records = []
    for candidate in candidates:
        if candidate.get("status") != "CANDIDATE_FOR_INDEPENDENT_REVIEW":
            raise ValueError("unminted or already sealed case in batch")
        row = candidate.get("prediction")
        if not isinstance(row, dict):
            raise ValueError("prediction row missing")
        inputs = row.get("inputs_used") or {}
        # input_snapshot is hashed by B.make_prediction, not retained on the
        # ledger row. The declared author is pinned in inputs_used instead.
        if (row.get("licence") != "PRODUCT_EXPERIMENT"
                or row.get("specialist") != bridge.STANDALONE_SPECIALIST
                or row.get("mechanism_id") != bridge.STANDALONE_MECHANISM
                or row.get("model_version") != bridge.STANDALONE_CONTRACT
                or row.get("policy_hash") != NV.content_sha256(bridge.STANDALONE_POLICY)
                or row.get("horizon_days") not in (5, 20)
                or row.get("observable") != B.Observable.BEATS_BENCHMARK.value
                or row.get("benchmark") != "SPY"
                or row.get("model") != "AEGIS_declared_hypothesis_no_model_call"
                or row.get("made_at") != seal.isoformat()
                or row.get("resolves_after") != B.PredictionRecord.resolution_date(
                    batch["entry_after_utc"], row.get("horizon_days"))
                or inputs.get("case_id") != candidate.get("case_id")
                or inputs.get("capture_sha256") != candidate.get("admission", {}).get("capture_sha256")
                or inputs.get("review_sha256") != candidate.get("admission", {}).get("review_sha256")
                or inputs.get("entry_after_utc") != batch["entry_after_utc"]
                or inputs.get("hypothesis_author") == review["reviewer"]):
            raise ValueError("candidate provenance or reviewer separation")
        source_id = candidate.get("source_item_id")
        source_sha = candidate.get("source_item_sha256")
        witness = candidate.get("source_witness")
        if not isinstance(witness, dict) or set(witness) != {
                "item", "capture", "semantic_review", "hypothesis", "instrument"}:
            raise ValueError("source witness missing")
        item = WD.Item(**witness["item"])
        if (item.kind != "article" or item.source != "sec_edgar_8k_ex99_body"
                or item.item_id != WD._sha(WD.norm_url(item.url))
                or item.item_id != source_id
                or NV.content_sha256(vars(item)) != source_sha
                or witness["capture"].get("source_item_sha256") != source_sha):
            raise ValueError("source item ID/hash join drift")
        replayed = bridge.prepare_candidate(
            item=item, capture=witness["capture"],
            semantic_review=witness["semantic_review"],
            hypothesis=witness["hypothesis"], instrument=witness["instrument"],
            seal_utc=batch["seal_utc"], entry_after_utc=batch["entry_after_utc"],
            trusted_manifest_path=None, existing_predictions=[row],
            standalone=True, standalone_market=batch["market"])
        hypothesis = witness["hypothesis"]
        if (replayed.get("status") != "ALREADY_SEALED"
                or replayed.get("case_id") != candidate.get("case_id")
                or replayed.get("admission") != candidate.get("admission")
                or row.get("probability") != hypothesis.get("probability_beats_spy")
                or row.get("raw_probability") != hypothesis.get("probability_beats_spy")
                or row.get("thesis") != hypothesis.get("thesis")
                or row.get("counter_thesis") != hypothesis.get("counter_thesis")
                or row.get("next_observable") != hypothesis.get("next_observable")):
            raise ValueError("source, price or hypothesis replay drift")
        if (not isinstance(source_id, str) or not source_id
                or not isinstance(source_sha, str) or len(source_sha) != 64
                or any(ch not in "0123456789abcdef" for ch in source_sha)
                or candidate.get("case_id") != NV.content_sha256({
                    "source_item_sha256": source_sha, "ticker": row.get("ticker"),
                    "horizon_sessions": row.get("horizon_days"),
                    "observable": "beats_benchmark",
                    "contract": bridge.STANDALONE_CONTRACT})):
            raise ValueError("source case binding drift")
        if candidate["case_id"] in case_ids or row.get("prediction_id") in prediction_ids:
            raise ValueError("duplicate case or prediction ID")
        if source_id in source_ids:
            raise ValueError("duplicate source item ID")
        case_ids.add(candidate["case_id"])
        prediction_ids.add(row["prediction_id"])
        source_ids.add(source_id)
        records.append(B.PredictionRecord(**row))
    if (sorted(prediction_ids) != batch.get("prediction_ids")
            or sorted(source_ids) != batch.get("source_item_ids")):
        raise ValueError("batch index drift")
    existing = B.read_predictions(ledger_path)
    if any((old.get("inputs_used") or {}).get("case_id") in case_ids
           or old.get("prediction_id") in prediction_ids for old in existing):
        raise ValueError("case or prediction already exists")
    B.append(records, path=ledger_path, population="campaign_forward")
    readback = B.read_predictions(ledger_path)
    if any(sum(row.get("prediction_id") == pid for row in readback) != 1
           for pid in prediction_ids):
        raise RuntimeError("batch append readback incomplete")
    return {"status": "EXACT_REVIEWED_BATCH_APPENDED", "prediction_ids": sorted(prediction_ids),
            "batch_sha256": NV.content_sha256(batch), "review_sha256": NV.content_sha256(review),
            "population": "campaign_forward", "ledger_path": str(ledger_path)}


def main() -> None:
    """One opt-in batch prepare or reviewed append; no model or broker calls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "append"))
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--ledger-path", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output already exists")
    packet = json.loads(args.packet.read_text(encoding="utf-8-sig"))
    if args.mode == "prepare":
        if args.review or args.ledger_path or set(packet) != {
                "cases", "seal_utc", "entry_after_utc", "market"}:
            raise ValueError("prepare packet contract")
        cases = []
        for raw in packet["cases"]:
            if not isinstance(raw, dict) or "item" not in raw:
                raise ValueError("case item missing")
            cases.append({**raw, "item": WD.Item(**raw["item"])})
        result = prepare_batch(cases=cases, seal_utc=packet["seal_utc"],
                               entry_after_utc=packet["entry_after_utc"],
                               market=packet["market"],
                               existing_predictions=B.read_predictions())
    else:
        if args.review is None or args.ledger_path is None:
            raise ValueError("append requires exact independent review and ledger")
        review = json.loads(args.review.read_text(encoding="utf-8-sig"))
        result = append_reviewed_batch(batch=packet, review=review,
                                       ledger_path=args.ledger_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
