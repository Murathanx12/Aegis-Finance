"""Synthetic source, identity and seal controls; no ledger or model calls."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import sys

import numpy as np
import pandas as pd
import pytest

from backend.services import current_event_forecast_bridge as C
from backend.services import news_source_validation as NV
from backend.services import world_digest as WD


def case(monkeypatch, tmp_path):
    item = WD.Item("event-1", "article", "issuer",
                   "https://uk.finance.yahoo.com/news/issuer-release-123.html",
                   "Issuer release", "ASML reported revenue of EUR 12 billion.",
                   "2026-10-14T09:00:00+00:00", "2026-10-14T08:00:00+00:00",
                   ["ASML"])
    capture = {
        "schema": "current_news_context_capture/2",
        "cache_key": WD.context_cache_key(item),
        "extraction_identity": WD.context_extraction_identity(),
        "source_sha256": NV.content_sha256(item.title + "\n" + item.text),
        "source_item_sha256": NV.content_sha256(vars(item)),
        "started_utc": "2026-10-14T10:00:00+00:00",
        "completed_utc": "2026-10-14T10:01:00+00:00",
        "producer": {"kind": "DETERMINISTIC_ANNOTATION", "actor": "source annotator"},
        "annotation": {"facts": {"entity": "ASML", "event_date": None,
                                 "date_precision": "unknown", "abstain": False,
                                 "evidence_spans": [item.text], "numbers": ["12"]},
                       "dates": [], "source_predictions": [], "aegis_hypotheses": []},
    }
    review = {"schema": "current_news_context_review/2", "decision": "CONTEXT_ACCEPTED",
              "independent": True, "reviewer": "independent source reviewer",
              "capture_sha256": NV.current_binding(capture),
              "producer_kind": "DETERMINISTIC_ANNOTATION",
              "reviewed_utc": "2026-10-14T11:00:00+00:00",
              "checks": ["full_row", "producer_origin", "date_roles",
                         "quantities_units_baselines",
                         "source_predictions_separate_from_aegis_hypotheses"]}
    hypothesis = {"author": "AEGIS research", "declared_utc": "2026-10-14T12:00:00+00:00",
                  "ticker": "ASML", "direction": "up", "horizon_sessions": 5,
                  "probability_beats_spy": 0.53,
                  "thesis": "AEGIS thinks the stock may beat SPY after the report.",
                  "counter_thesis": "Sector selling persists despite reported revenue.",
                  "next_observable": "ASML relative close after five sessions.",
                  "source_fact_indices": [0]}
    table = tmp_path / "issuers.csv"
    table.write_text("symbol,primary_name,aliases,country,is_adr\nASML,ASML,ASML,US,\n")
    panel = tmp_path / "bars.parquet"
    panel.write_bytes(b"synthetic panel pin; closes returned by fixture")
    refresh = tmp_path / "bars_refresh"
    refresh.mkdir(exist_ok=True)
    refresh_receipt = refresh / "prior-session.json"
    refresh_receipt.write_text(json.dumps({"status": "ok", "pull": {"adjustment": "all"},
                                           "last_closed_session": "2026-10-13"}))
    monkeypatch.setattr(C, "ISSUER_TABLE", table)
    monkeypatch.setattr(C, "PRICE_PANEL", panel)
    instrument = {"ticker": "ASML",
                  "observed_utc": "2026-10-14T11:00:00+00:00",
                  "reviewed_utc": "2026-10-14T11:30:00+00:00",
                  "reviewer": "independent identity reviewer",
                  "issuer_table_sha256": hashlib.sha256(table.read_bytes()).hexdigest(),
                  "price_panel_sha256": hashlib.sha256(panel.read_bytes()).hexdigest(),
                  "price_panel_receipt_path": str(refresh_receipt),
                  "price_panel_receipt_sha256": hashlib.sha256(refresh_receipt.read_bytes()).hexdigest(),
                  "price_last_closed_session": "2026-10-13"}
    dates = pd.bdate_range(end="2026-10-13", periods=80)
    values = 100 + np.arange(80) * .1 + np.sin(np.arange(80))
    prices = pd.DataFrame({"ASML": values, "TSM": values * .7,
                           "SPY": values * .9}, index=dates)
    monkeypatch.setattr(WD, "load_closes", lambda: prices)
    virtual_path = tmp_path / "qualified-virtual.json"
    virtual_path.write_text(json.dumps({
        "schema": "virtual_v3_consumer_result/1",
        "consumed_at": "2026-10-14T12:30:00+00:00",
        "scheduled_entry_at": "2026-10-14T20:00:00+00:00",
        "prepared_semantic_sha256": "b" * 64,
        "result": {"status": "QUALIFIED_PROSPECTIVE_MECHANICS_ONLY",
                   "artifact_hash": "c" * 64,
                   "holdings": [{"ticker": "TSM", "weight": .4}]}},
        ), encoding="utf-8")
    virtual_hash = hashlib.sha256(virtual_path.read_bytes()).hexdigest()
    review_path = tmp_path / "independent-virtual-review.json"
    review_path.write_text(json.dumps({
        "schema": "independent_actual_private_virtual_consumer_review/1",
        "independent": True, "verdict": "PASS_ACTUAL_PRIVATE_VIRTUAL_CONSUMER_ONLY",
        "status": "QUALIFIED_PROSPECTIVE_MECHANICS_ONLY",
        "consumer_result_ref": {"path": str(virtual_path), "sha256": virtual_hash}}))
    manifest_path = tmp_path / "operator-manifest.json"
    manifest_path.write_text(json.dumps({
        "schema": "operator_approved_virtual_consumer_ref/1",
        "scope": "H21_PRIOR_ONLY_PAIRED_HOLD_NO_H5_H20_EXPECTED_RETURN_MAPPING",
        "consumer_result_path": str(virtual_path), "consumer_result_sha256": virtual_hash,
        "independent_review_path": str(review_path),
        "independent_review_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest()}))
    monkeypatch.setattr(C, "TRUSTED_MANIFEST_SHA256",
                        hashlib.sha256(manifest_path.read_bytes()).hexdigest())
    monkeypatch.setattr(C, "_now_utc", lambda: datetime(2026, 10, 14, 13, 0, 30,
                                                        tzinfo=timezone.utc))
    return dict(item=item, capture=capture, semantic_review=review,
                hypothesis=hypothesis, instrument=instrument,
                seal_utc="2026-10-14T13:00:00+00:00",
                entry_after_utc="2026-10-14T20:00:00+00:00",
                trusted_manifest_path=manifest_path,
                existing_predictions=[])


def test_benchmark_bar_must_exist_and_match_stock_cutoff(monkeypatch, tmp_path):
    args = case(monkeypatch, tmp_path)
    prices = WD.load_closes()
    monkeypatch.setattr(WD, "load_closes", lambda: prices.drop(columns="SPY"))
    with pytest.raises(ValueError, match="benchmark"):
        C.prepare_candidate(**args)
    stale = prices.copy()
    stale.loc[stale.index[-1], "SPY"] = float("nan")
    monkeypatch.setattr(WD, "load_closes", lambda: stale)
    with pytest.raises(ValueError, match="benchmark"):
        C.prepare_candidate(**args)


def test_source_bound_candidate_is_prospective_and_actual_shadow_holds(monkeypatch, tmp_path):
    args = case(monkeypatch, tmp_path)
    first = C.prepare_candidate(**args)
    assert first["status"] == "CANDIDATE_FOR_INDEPENDENT_REVIEW"
    row = first["prediction"]
    assert (row["licence"], row["horizon_days"], row["probability"]) == (
        "PRODUCT_EXPERIMENT", 5, .53)
    assert row["inputs_used"]["capture_sha256"] == first["admission"]["capture_sha256"]
    assert row["inputs_used"]["review_sha256"] == first["admission"]["review_sha256"]
    assert row["model"] == "AEGIS_declared_hypothesis_no_model_call"
    assert first["virtual"]["without_news"] == first["virtual"]["with_news"]
    assert first["virtual"]["decision"] == "HOLD"
    assert not first["virtual"]["news_signal_applied"]
    args["existing_predictions"] = [row]
    assert C.prepare_candidate(**args)["status"] == "ALREADY_SEALED"
    monkeypatch.setattr(C, "_now_utc", lambda: datetime(2026, 10, 14, 21, 0,
                                                        tzinfo=timezone.utc))
    assert C.prepare_candidate(**args)["status"] == "ALREADY_SEALED"
    args["hypothesis"] = deepcopy(args["hypothesis"])
    args["hypothesis"]["probability_beats_spy"] = .54
    with pytest.raises(ValueError, match="already sealed"):
        C.prepare_candidate(**args)


def test_source_tamper_and_lookalike_host_refuse_before_prediction(monkeypatch, tmp_path):
    args = case(monkeypatch, tmp_path)
    args["capture"]["annotation"]["facts"]["numbers"] = ["99"]
    with pytest.raises(ValueError, match="source context refused"):
        C.prepare_candidate(**args)
    args = case(monkeypatch, tmp_path)
    args["item"].url = "https://uk.finance.yahoo.com.evil.invalid/news/issuer-release"
    with pytest.raises(ValueError, match="exact HTTPS source host"):
        C.prepare_candidate(**args)


def test_future_seal_identity_drift_and_next_day_entry_refuse(monkeypatch, tmp_path):
    args = case(monkeypatch, tmp_path)
    args["seal_utc"] = "2099-10-14T15:00:00+00:00"
    with pytest.raises(ValueError, match="seal must be observed"):
        C.prepare_candidate(**args)
    args = case(monkeypatch, tmp_path)
    args["instrument"]["price_panel_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="price-panel witness"):
        C.prepare_candidate(**args)
    args = case(monkeypatch, tmp_path)
    args["entry_after_utc"] = "2026-10-15T20:00:00+00:00"
    with pytest.raises(ValueError, match="same UTC session"):
        C.prepare_candidate(**args)


def test_past_entry_cannot_mint_and_forged_baseline_cannot_self_qualify(monkeypatch, tmp_path):
    args = case(monkeypatch, tmp_path)
    monkeypatch.setattr(C, "_now_utc", lambda: datetime(2026, 10, 14, 13, 5,
                                                        tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="fresh observed seal and future entry"):
        C.prepare_candidate(**args)
    args = case(monkeypatch, tmp_path)
    monkeypatch.setattr(C, "_now_utc", lambda: datetime(2026, 10, 14, 20, 1,
                                                        tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="fresh observed seal and future entry"):
        C.prepare_candidate(**args)
    args = case(monkeypatch, tmp_path)
    forged = tmp_path / "forged-manifest.json"
    forged.write_text(json.dumps({"schema": "operator_approved_virtual_consumer_ref/1",
                                  "scope": "H21_PRIOR_ONLY_PAIRED_HOLD_NO_H5_H20_EXPECTED_RETURN_MAPPING"}))
    args["trusted_manifest_path"] = forged
    with pytest.raises(ValueError, match="operator-approved virtual manifest drift"):
        C.prepare_candidate(**args)


def test_actual_cli_seam_writes_one_candidate_only_after_admission(monkeypatch, tmp_path):
    args = case(monkeypatch, tmp_path)
    packet = {**args, "item": asdict(args["item"])}
    packet.pop("existing_predictions")
    trusted = packet.pop("trusted_manifest_path")
    inp, out = tmp_path / "packet.json", tmp_path / "candidate.json"
    inp.write_text(json.dumps(packet), encoding="utf-8")
    monkeypatch.setattr(C.B, "read_predictions", lambda: [])
    monkeypatch.setattr(C.B, "append", lambda *_a, **_k: pytest.fail("no ledger append"))
    monkeypatch.setattr(sys, "argv", ["bridge", "--packet", str(inp),
                                         "--trusted-manifest", str(trusted),
                                         "--output", str(out)])
    C.main()
    assert json.loads(out.read_text(encoding="utf-8"))["virtual"]["decision"] == "HOLD"
    with pytest.raises(FileExistsError):
        C.main()
