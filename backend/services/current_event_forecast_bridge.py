"""Opt-in, source-bound exploratory forecast candidate; never writes a ledger.

The source context is admitted by the existing independent-review contract.
The directional probability below is a separately declared AEGIS hypothesis,
not a prediction made by the article or a learned expected return.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

from backend.services import belief_state as B
from backend.services import news_source_validation as NV
from backend.services import world_digest as WD


CONTRACT = "current_source_direction_product_experiment/1"
SPECIALIST = "news_digest:source_context_v1"
MECHANISM = "source_context_direction_v1"
STANDALONE_CONTRACT = "current_source_direction_standalone_product_experiment/1"
STANDALONE_SPECIALIST = "news_digest:source_context_standalone_v1"
STANDALONE_MECHANISM = "source_context_direction_standalone_v1"
SOURCE_HOSTS = frozenset({"investor.asml.com", "uk.finance.yahoo.com", "www.sec.gov"})
ISSUER_TABLE = Path(__file__).resolve().parents[1] / "data" / "news_entities" / "issuers.csv"
PRICE_PANEL = WD.optimus() / "prices_2025_26" / "bars.parquet"
TRUSTED_MANIFEST_SHA256 = "7cc5792c787b7a589626247b12cde07b9fdae68972d505b53a5307cf594b504c"
POLICY = {"contract": CONTRACT, "allowed_horizons": [5, 20],
          "observable": "beats_benchmark", "benchmark": "SPY",
          "licence": "PRODUCT_EXPERIMENT", "entry": "after_seal_same_utc_date",
          "price": "prior_completed_bar", "virtual_consumer": "H21_prior_only_hold",
          "writer": "candidate_only"}
STANDALONE_POLICY = {**POLICY, "contract": STANDALONE_CONTRACT,
                     "virtual_consumer": "none_standalone_no_portfolio_authority",
                     "entry": "next_native_verified_US_session_after_closed_bar",
                     "price": "private_hash_bound_panel_global_history_plus_closed_SIP_bar"}


def _utc(value: str) -> datetime:
    stamp = NV._time(value)
    return stamp.astimezone(timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _trusted_virtual(manifest_path: Path) -> tuple[dict, str]:
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != TRUSTED_MANIFEST_SHA256:
        raise ValueError("operator-approved virtual manifest drift")
    manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    if (manifest.get("schema") != "operator_approved_virtual_consumer_ref/1"
            or manifest.get("scope") != "H21_PRIOR_ONLY_PAIRED_HOLD_NO_H5_H20_EXPECTED_RETURN_MAPPING"):
        raise ValueError("operator-approved virtual manifest contract")
    result_path = Path(manifest["consumer_result_path"])
    review_path = Path(manifest["independent_review_path"])
    result_bytes, review_bytes = result_path.read_bytes(), review_path.read_bytes()
    result_hash = hashlib.sha256(result_bytes).hexdigest()
    review_hash = hashlib.sha256(review_bytes).hexdigest()
    if (result_hash != manifest["consumer_result_sha256"]
            or review_hash != manifest["independent_review_sha256"]):
        raise ValueError("operator-approved consumer or review drift")
    result = json.loads(result_bytes.decode("utf-8-sig"))
    review = json.loads(review_bytes.decode("utf-8-sig"))
    ref = review.get("consumer_result_ref") or {}
    if (review.get("schema") != "independent_actual_private_virtual_consumer_review/1"
            or review.get("independent") is not True
            or review.get("verdict") != "PASS_ACTUAL_PRIVATE_VIRTUAL_CONSUMER_ONLY"
            or review.get("status") != "QUALIFIED_PROSPECTIVE_MECHANICS_ONLY"
            or Path(ref.get("path") or "").resolve() != result_path.resolve()
            or ref.get("sha256") != result_hash):
        raise ValueError("independent virtual consumer review not bound")
    return result, result_hash


def _https_host(url: str, allowed: frozenset[str]) -> None:
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in allowed
                or parsed.username or parsed.password or parsed.port
                or not parsed.path or parsed.fragment):
            raise ValueError("unapproved URL")
    except ValueError as exc:
        raise ValueError("unapproved exact HTTPS source host") from exc


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _standalone_prices(*, market: dict, instrument: dict, ticker: str,
                       seal: datetime, entry: datetime) -> tuple[pd.DataFrame, str, dict]:
    """Bind one fresh private close to unchanged native history and a closed clock."""
    required = {"private_panel_path", "private_panel_sha256", "base_panel_sha256",
                "clock_observation_path", "clock_observation_sha256"}
    if not isinstance(market, dict) or set(market) != required:
        raise ValueError("standalone market witness shape")
    panel = Path(market["private_panel_path"]).resolve()
    observation_path = Path(market["clock_observation_path"]).resolve()
    if (not panel.is_file() or not observation_path.is_file()
            or _sha_file(panel) != market["private_panel_sha256"]
            or _sha_file(PRICE_PANEL) != market["base_panel_sha256"]
            or _sha_file(observation_path) != market["clock_observation_sha256"]
            or instrument["price_panel_sha256"] != market["private_panel_sha256"]):
        raise ValueError("standalone private panel or clock source drift")
    observation = json.loads(observation_path.read_text(encoding="utf-8-sig"))
    clock_rows = [r for r in observation.get("requests", [])
                  if r.get("path") == "/v2/clock" and r.get("status") == 200]
    if (observation.get("schema") != "paper-session-observation/1"
            or observation.get("host") != "paper-api.alpaca.markets"
            or observation.get("writes_to_broker") != 0
            or len(clock_rows) != 1):
        raise ValueError("native paper clock witness invalid")
    clock_ref = clock_rows[0]
    clock_path = Path(clock_ref["private_file"]).resolve()
    if not clock_path.is_file() or _sha_file(clock_path) != clock_ref["sha256"]:
        raise ValueError("native paper clock body drift")
    clock = json.loads(clock_path.read_text(encoding="utf-8-sig"))
    stamp, next_open, next_close = (_utc(clock[k]) for k in
                                    ("timestamp", "next_open", "next_close"))
    if (clock.get("is_open") is not False or not stamp <= seal < next_open <= entry < next_close
            or (seal - stamp).total_seconds() > 6 * 3600
            or (entry - seal).total_seconds() > 24 * 3600):
        raise ValueError("next-session entry not bound to recent closed native clock")
    closed_day = stamp.date().isoformat()
    receipt_path = Path(instrument["price_panel_receipt_path"]).resolve()
    if not receipt_path.is_file() or _sha_file(receipt_path) != instrument["price_panel_receipt_sha256"]:
        raise ValueError("private SIP receipt drift")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    assets = {a.get("symbol"): a for a in receipt.get("assets", [])}
    if (receipt.get("schema") != "restricted_paper_us_assets_and_canonical_daily_bars/1"
            or receipt.get("asset_host") != "https://paper-api.alpaca.markets"
            or receipt.get("stock_data_host") != "https://data.alpaca.markets"
            or receipt.get("timeframe") != "1Day" or receipt.get("feed") != "sip"
            or receipt.get("adjustment") != "all"
            or receipt.get("last_complete_session") != closed_day
            or _utc(receipt.get("completed_at")) > seal
            or _utc(receipt.get("end_utc")) <= stamp
            or instrument["price_last_closed_session"] != closed_day
            or any(assets.get(symbol, {}).get("status") != "active"
                   or assets[symbol].get("tradable") is not True
                   or assets[symbol].get("class") != "us_equity"
                   for symbol in (ticker, "SPY"))):
        raise ValueError("private SIP asset or closed-bar receipt invalid")
    prices = WD.load_closes(path=panel)
    base = WD.load_closes(path=PRICE_PANEL)
    for symbol in (ticker, "SPY"):
        if symbol not in prices.columns or symbol not in base.columns:
            raise ValueError("private panel lacks native history")
        old = base[symbol].dropna()
        series = prices[symbol].dropna()
        if (old.empty or old.index[-1].date().isoformat() >= closed_day
                or not series.loc[old.index].equals(old)
                or len(series) != len(old) + 1
                or series.index[-1].date().isoformat() != closed_day):
            raise ValueError("private panel altered native history or missing closed bar")
        bars = receipt.get("bars", {}).get(symbol)
        if (not isinstance(bars, list) or len(bars) < 40
                or pd.Timestamp(bars[-1]["t"]).date().isoformat() != closed_day
                or float(bars[-1]["c"]) != float(series.iloc[-1])):
            raise ValueError("private close differs from SIP source")
        overlap = []
        dates = []
        for bar in bars:
            day = pd.Timestamp(bar["t"]).date().isoformat()
            close = float(bar["c"])
            if not math.isfinite(close) or close <= 0:
                raise ValueError("nonpositive or nonfinite SIP close")
            dates.append(day)
            if day != closed_day:
                prior = old.loc[pd.Timestamp(day)] if pd.Timestamp(day) in old.index else None
                if prior is None or abs(close / float(prior) - 1) > 1e-4:
                    raise ValueError("SIP/native adjusted overlap basis drift")
                overlap.append(day)
        if (dates != sorted(set(dates)) or len(overlap) != len(bars) - 1
                or len(overlap) < 39):
            raise ValueError("SIP/native overlap incomplete or duplicate")
    return prices, closed_day, {"clock_observation_sha256": market["clock_observation_sha256"],
                                "base_panel_sha256": market["base_panel_sha256"]}


def prepare_candidate(*, item: WD.Item, capture: dict, semantic_review: dict,
                      hypothesis: dict, instrument: dict,
                      seal_utc: str, entry_after_utc: str,
                      trusted_manifest_path: Path | None,
                      existing_predictions: list[dict],
                      standalone: bool = False,
                      standalone_market: dict | None = None) -> dict:
    """Return a frozen candidate and paired shadow; caller separately reviews/appends.

    `instrument` binds the existing US issuer mapping and adjusted US SIP price
    panel witness; neither an issuer mention nor price bars alone assign venue.
    The existing qualified H21 virtual consumer has no compatible H5/H20
    direction-to-expected-return mapping; its actual decision stays unchanged.
    """
    now = _now_utc()
    seal = _utc(seal_utc)
    entry = _utc(entry_after_utc)
    if seal > now or entry <= seal or (not standalone and entry.date() != seal.date()):
        raise ValueError("seal must be observed; entry must follow it in the same UTC session")
    _https_host(item.url, SOURCE_HOSTS)
    admitted = WD.extract_context_item(item, cache={}, cutoff_utc=seal_utc,
                                       capture=capture, semantic_review=semantic_review)
    if admitted["status"] != "CURRENT_CONTEXT_ADMITTED_ONLY":
        raise ValueError(f"source context refused: {admitted.get('reason')}")
    admission = admitted["admission"]
    if admission["status"] != "SOURCE_GROUNDED_CONTEXT_ONLY":
        raise ValueError("source context is not independently admitted")

    required = {"author", "declared_utc", "ticker", "direction", "horizon_sessions",
                "probability_beats_spy", "thesis", "counter_thesis", "next_observable",
                "source_fact_indices"}
    if not isinstance(hypothesis, dict) or set(hypothesis) != required:
        raise ValueError("AEGIS hypothesis contract shape")
    if not hypothesis["author"] or not all(
            isinstance(hypothesis[k], str) and hypothesis[k].strip()
            for k in ("thesis", "counter_thesis", "next_observable")):
        raise ValueError("AEGIS hypothesis text/author missing")
    declared = _utc(hypothesis["declared_utc"])
    if not _utc(semantic_review["reviewed_utc"]) <= declared <= seal:
        raise ValueError("AEGIS hypothesis was not declared after review before seal")
    ticker = hypothesis["ticker"]
    horizon = hypothesis["horizon_sessions"]
    probability = hypothesis["probability_beats_spy"]
    direction = hypothesis["direction"]
    if (not isinstance(ticker, str) or not ticker.isascii() or not ticker.isupper()
            or not ticker.isalnum() or not 1 <= len(ticker) <= 6
            or horizon not in (5, 20) or type(probability) not in (int, float)
            or not 0 <= probability <= 1
            or direction not in ("up", "down")
            or (direction == "up" and probability <= 0.5)
            or (direction == "down" and probability >= 0.5)):
        raise ValueError("unsupported ticker, horizon or directional probability")
    spans = capture["annotation"]["facts"]["evidence_spans"]
    indices = hypothesis["source_fact_indices"]
    if (not isinstance(indices, list) or not indices or
            any(type(i) is not int or i < 0 or i >= len(spans) for i in indices)
            or len(indices) != len(set(indices))):
        raise ValueError("source fact references missing or invalid")

    identity_fields = {"ticker", "observed_utc", "reviewer", "reviewed_utc",
                       "issuer_table_sha256", "price_panel_sha256",
                       "price_panel_receipt_path", "price_panel_receipt_sha256",
                       "price_last_closed_session"}
    if not isinstance(instrument, dict) or set(instrument) != identity_fields:
        raise ValueError("US instrument mapping and panel review missing")
    table_bytes = ISSUER_TABLE.read_bytes()
    table_hash = hashlib.sha256(table_bytes).hexdigest()
    panel_hash = (_sha_file(PRICE_PANEL) if not standalone else
                  instrument["price_panel_sha256"])
    receipt_path = Path(instrument["price_panel_receipt_path"]).resolve()
    if not standalone and receipt_path.parent != (PRICE_PANEL.parent / "bars_refresh").resolve():
        raise ValueError("price-panel receipt outside native refresh directory")
    receipt_bytes = receipt_path.read_bytes()
    receipt_hash = hashlib.sha256(receipt_bytes).hexdigest()
    receipt = json.loads(receipt_bytes.decode("utf-8-sig"))
    table_rows = [r for r in csv.DictReader(table_bytes.decode("utf-8-sig").splitlines())
                  if r.get("symbol") == ticker]
    if (instrument["ticker"] != ticker or instrument["issuer_table_sha256"] != table_hash
            or instrument["price_panel_sha256"] != panel_hash
            or instrument["price_panel_receipt_sha256"] != receipt_hash
            or (not standalone and (receipt.get("status") != "ok"
                or (receipt.get("pull") or {}).get("adjustment") != "all"
                or receipt.get("last_closed_session") != instrument["price_last_closed_session"]))
            or len(table_rows) != 1 or table_rows[0].get("country") != "US"
            or not instrument["reviewer"]
            or instrument["reviewer"] == hypothesis["author"]
            or any(not isinstance(instrument[k], str) or len(instrument[k]) != 64
                   or any(ch not in "0123456789abcdef" for ch in instrument[k])
                   for k in ("price_panel_sha256", "price_panel_receipt_sha256"))):
        raise ValueError("US issuer mapping or price-panel witness invalid")
    if not _utc(instrument["observed_utc"]) <= _utc(instrument["reviewed_utc"]) <= seal:
        raise ValueError("US mapping and panel review arrived after seal")
    if standalone:
        prices, closed_day, market_proof = _standalone_prices(
            market=standalone_market, instrument=instrument, ticker=ticker,
            seal=seal, entry=entry)
    else:
        if standalone_market is not None:
            raise ValueError("paired bridge cannot consume standalone market witness")
        prices, closed_day, market_proof = WD.load_closes(), seal.date().isoformat(), {}
    price_cutoff = entry.date().isoformat() if standalone else seal.date().isoformat()
    ps = WD.price_state(prices, ticker, asof=pd.Timestamp(price_cutoff))
    if (ps is None or ps["last_bar"] >= price_cutoff
            or instrument["price_last_closed_session"] != ps["last_bar"]):
        raise ValueError("prior completed price bar unavailable")
    benchmark = WD.price_state(prices, "SPY", asof=pd.Timestamp(entry.date() if standalone else seal.date()))
    if benchmark is None or benchmark["last_bar"] != ps["last_bar"]:
        raise ValueError("matching prior completed benchmark price bar unavailable")

    contract = STANDALONE_CONTRACT if standalone else CONTRACT
    policy = STANDALONE_POLICY if standalone else POLICY
    case_key = {"source_item_sha256": capture["source_item_sha256"],
                "ticker": ticker, "horizon_sessions": horizon,
                "observable": "beats_benchmark"}
    if standalone:
        case_key["contract"] = contract
    case_id = NV.content_sha256(case_key)
    policy_hash = NV.content_sha256(policy)
    snap = {"contract": contract, "policy_hash": policy_hash,
            "case_id": case_id,
            "source_item_sha256": capture["source_item_sha256"],
            "source_url": item.url, "source_first_seen_utc": item.first_seen_utc,
            "source_published_utc": item.published_utc,
            "capture_sha256": admission["capture_sha256"],
            "review_sha256": admission["review_sha256"],
            "source_fact_indices": indices,
            "issuer_table_sha256": table_hash,
            "price_panel_sha256": instrument["price_panel_sha256"],
            "price_panel_receipt_sha256": instrument["price_panel_receipt_sha256"],
            "price_panel_receipt_path": str(receipt_path),
            "price_bar": ps["last_bar"], "price_at_seal": ps["last_close"],
            "benchmark_price_bar": benchmark["last_bar"],
            "benchmark_price_at_seal": benchmark["last_close"],
            "hypothesis": hypothesis, "seal_utc": seal.isoformat(),
            "entry_after_utc": entry.isoformat()}
    if standalone:
        snap["market_proof"] = market_proof
    inputs = {"source": "independently_reviewed_current_context",
              "case_id": case_id, "source_url": item.url,
              "capture_sha256": admission["capture_sha256"],
              "review_sha256": admission["review_sha256"],
              "hypothesis_author": hypothesis["author"],
              "hypothesis_declared_utc": hypothesis["declared_utc"],
              "probability_basis": "AEGIS exploratory declared prior; unlearned",
              "issuer_table_sha256": table_hash,
              "price_panel_sha256": instrument["price_panel_sha256"],
              "price_panel_receipt_sha256": instrument["price_panel_receipt_sha256"],
              "price_panel_receipt_path": str(receipt_path),
              "price_bar": ps["last_bar"], "entry_after_utc": entry_after_utc}
    if standalone:
        inputs.update(market_proof)
    row = B.make_prediction(
        ticker=ticker, specialist=STANDALONE_SPECIALIST if standalone else SPECIALIST,
        observable=B.Observable.BEATS_BENCHMARK,
        benchmark="SPY", horizon_days=horizon, probability=float(probability),
        thesis=hypothesis["thesis"], counter_thesis=hypothesis["counter_thesis"],
        next_observable=hypothesis["next_observable"],
        model="AEGIS_declared_hypothesis_no_model_call", model_version=contract,
        prompt="NO_LLM_PROMPT:" + contract, input_snapshot=snap,
        made_at=seal.isoformat(),
        mechanism_id=STANDALONE_MECHANISM if standalone else MECHANISM,
        decision_date=seal.date().isoformat(), licence="PRODUCT_EXPERIMENT",
        policy_hash=policy_hash,
        inputs_used=inputs,
        raw_probability=float(probability),
        shrink_basis="none: declared exploratory prior, no fitted skill correction",
        notes_text="Prospective source-context experiment; attention, not an order")
    if standalone:
        # made_at remains the honest information seal. The resolver's first bar
        # and due date use the separately pinned future entry session.
        row.resolves_after = B.PredictionRecord.resolution_date(entry.isoformat(), horizon)
    already_sealed = None
    for old in existing_predictions:
        old_inputs = old.get("inputs_used") or {}
        if old_inputs.get("case_id") == case_id:
            if old.get("prediction_id") != row.prediction_id:
                raise ValueError("source case already sealed with different inputs")
            already_sealed = old

    if standalone:
        if trusted_manifest_path is not None:
            raise ValueError("standalone forecast cannot claim a virtual consumer")
        virtual_result = {"decision": "NO_PORTFOLIO_AUTHORITY",
                          "news_signal_applied": False,
                          "reason": "STANDALONE_H5_H20_HAS_NO_H21_EXPECTED_RETURN_MAPPING"}
    else:
        if trusted_manifest_path is None:
            raise ValueError("qualified virtual consumer manifest required")
        virtual, virtual_hash = _trusted_virtual(Path(trusted_manifest_path))
        result = virtual.get("result") or {}
        holdings = result.get("holdings") or []
        if (virtual.get("schema") != "virtual_v3_consumer_result/1"
                or result.get("status") != "QUALIFIED_PROSPECTIVE_MECHANICS_ONLY"
                or _utc(virtual.get("consumed_at")) > seal
                or _utc(virtual.get("scheduled_entry_at")) != entry
                or not holdings or any(not isinstance(h, dict)
                                       or not h.get("ticker") or not isinstance(h.get("weight"), (int, float))
                                       for h in holdings)):
            raise ValueError("qualified virtual consumer is absent or not same-entry")
        base = {h["ticker"]: h["weight"] for h in holdings}
        if len(base) != len(holdings):
            raise ValueError("qualified virtual consumer has duplicate holdings")
        virtual_result = {"receipt_sha256": virtual_hash,
                          "prepared_semantic_sha256": virtual.get("prepared_semantic_sha256"),
                          "result_artifact_hash": result.get("artifact_hash"),
                          "scheduled_entry_at": virtual["scheduled_entry_at"],
                          "horizon_sessions": 21,
                          "without_news": base, "with_news": base.copy(),
                          "news_signal_applied": False,
                          "reason": "H5_H20_DIRECTION_HAS_NO_QUALIFIED_H21_EXPECTED_RETURN_MAPPING",
                          "decision": "HOLD"}
    current = _now_utc()
    if not already_sealed and ((current - seal).total_seconds() > 120 or entry <= current):
        raise ValueError("fresh observed seal and future entry required before mint")
    return {"status": "ALREADY_SEALED" if already_sealed else "CANDIDATE_FOR_INDEPENDENT_REVIEW",
            "prediction": already_sealed or asdict(row),
            "admission": admission, "case_id": case_id,
            "virtual": virtual_result,
            "entry_after_utc": entry_after_utc}


def main() -> None:
    """One-case read/prepare operation; writes only the selected private receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--trusted-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8-sig"))
    required = {"item", "capture", "semantic_review", "hypothesis", "instrument",
                "seal_utc", "entry_after_utc"}
    if not isinstance(packet, dict) or set(packet) != required:
        raise ValueError("candidate packet contract shape")
    packet["item"] = WD.Item(**packet["item"])
    result = prepare_candidate(**packet, trusted_manifest_path=args.trusted_manifest,
                               existing_predictions=B.read_predictions())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
