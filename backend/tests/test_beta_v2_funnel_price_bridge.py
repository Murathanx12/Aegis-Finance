"""Small offline C02-format artifacts; no native provenance or calendar claim."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pandas as pd
import pytest

from backend.services import funnel_acquisition as A
from backend.services import funnel_price_bridge as B
from backend.services import funnel_staging as S
from backend.services import opportunity_funnel as F


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def descriptor(name, data):
    return {"file": name, "sha256": sha(data), "bytes": len(data)}


@pytest.fixture
def bundle():
    end = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    idx = pd.bdate_range(end=end, periods=F.MIN_HISTORY_DAYS, tz="Europe/Stockholm")
    dates = [t.date().isoformat() for t in idx]
    frame = pd.DataFrame({"Open": 10.0, "High": 12.0, "Low": 9.0,
                          "Close": 11.0, "Volume": 300000}, index=idx)
    raw, readiness = A._raw_history_payload(frame)
    raw_universe = [{"symbol": t, "mic": "XNAS", "type": "Common Stock"} for t in ("AAA", "BBB")]
    files = {"universe_response.json": encode(raw_universe),
             "history-B000001.json": encode({t: raw for t in ("AAA", "BBB")})}
    stamp = datetime.now(timezone.utc).isoformat()
    u = A._universe(raw_universe, [], sha(files["universe_response.json"]), stamp,
                    {"max_raw_rows": 1000, "max_symbols": 2, "max_transport_attempts": 3})
    history_window = {"history_start": dates[0], "history_end": dates[-1]}
    coverage_window = {"coverage_start": dates[-1], "coverage_end": dates[-1], "coverage_min_rows": 1}
    plan = {"mode": "full_us", "symbols": u["tickers"],
            "history_window": list(history_window.values()),
            "coverage_window": [dates[-1], dates[-1]], "promotion_eligible": False}
    files["plan.json"] = encode(plan)
    cv = frame[["Close", "Volume"]].iloc[-1:].copy()
    cv.index = cv.index.tz_localize(None)

    def provider(batch, names):
        return {"source": "mock C02 history", "fetched_at": stamp,
                "cache_provenance": {"mode": "uncached", "identity": "history-B000001.json",
                                     "sha256": sha(files["history-B000001.json"])},
                "prices": [(t, cv) for t in names]}

    receipt = F.stage_price_coverage(universe=u, provider=provider,
                                    limits=S.Limits(2, 1, 1, 2),
                                    start_date=dates[-1], end_date=dates[-1], min_rows=1)
    files["funnel-price-staging/price.json"] = receipt.payload
    pins = {name: "a" * 64 for name in ("funnel_acquisition.py", "funnel_staging.py", "worker.py")}
    acq = {"mode": "full_us", "status": "COMPLETE", "transport_failure": None,
           "source_pins": pins, "universe": u, "promotion_eligible": False,
           "raw_universe": descriptor("universe_response.json", files["universe_response.json"]),
           "artifacts": [descriptor(k, files[k]) for k in ("plan.json", "history-B000001.json")],
           "price_coverage": descriptor("funnel-price-staging/price.json", receipt.payload),
           "symbol_outcomes": {t: {"status": "history_returned"} for t in u["tickers"]},
           "raw_history": {t: {"rows": len(frame), **readiness} for t in u["tickers"]},
           "history_window": history_window, "coverage_window": coverage_window}
    files["acquisition.json"] = encode(acq)
    manifest = {"schema": "verified_price_manifest_v1", "universe": u,
                "source_pins": pins, "acquisition": descriptor("acquisition.json", files["acquisition.json"]),
                "required_sessions": dates,
                "calendar_provenance": {"source": "explicit test calendar, not an exchange claim",
                                        "sha256": sha(encode(dates))},
                "limits": {"max_input_bytes": 1000000, "max_artifacts": 5,
                           "max_rows": 1000, "max_symbols": 2}}
    return manifest, files


def reseal(manifest, files, *, acquisition=None):
    """Repin deliberately modified inputs so tests exercise semantic verification."""
    acq = json.loads(files["acquisition.json"]) if acquisition is None else acquisition
    acq["raw_universe"] = descriptor("universe_response.json", files["universe_response.json"])
    acq["artifacts"] = [descriptor(d["file"], files[d["file"]]) for d in acq["artifacts"]]
    if "price_coverage" in acq:
        name = acq["price_coverage"]["file"]
        coverage = json.loads(files[name])
        for batch in coverage["batches"]:
            provenance = batch["provenance"]["cache_provenance"]
            provenance["sha256"] = sha(files[provenance["identity"]])
        files[name] = encode(coverage)
        acq["price_coverage"] = descriptor(name, files[name])
    files["acquisition.json"] = encode(acq)
    manifest["acquisition"] = descriptor("acquisition.json", files["acquisition.json"])


def refused(manifest, files):
    with pytest.raises(B.PriceBridgeRefused) as caught:
        B.stage_verified_prices(manifest=manifest, artifacts=files)
    report = caught.value.report
    assert not report["complete"]
    assert not report["promotion_eligible"]
    return report


def test_original_eligibility_inputs_timezone_and_immutable_receipt(bundle):
    manifest, files = bundle
    before = deepcopy((manifest, files))
    result = B.stage_verified_prices(manifest=manifest, artifacts=files)
    report = result.report
    assert report["complete"] and report["accounting_complete"]
    assert report["usable_price_coverage_complete"] and report["declared_history_coverage_complete"]
    assert report["universe"] == manifest["universe"]
    assert set(report["inputs"]) == {"AAA", "BBB"}
    exported = report["inputs"]["AAA"]
    original = json.loads(files["history-B000001.json"])["AAA"]
    assert exported["raw_history"] == original
    assert exported["close_volume"] == {"dates": manifest["required_sessions"],
                                         "Close": [11.0] * F.MIN_HISTORY_DAYS,
                                         "Volume": [300000] * F.MIN_HISTORY_DAYS}
    assert original["index_timezone"] == "Europe/Stockholm"
    assert all(s[:10] == d for s, d in zip(original["index"], manifest["required_sessions"]))
    assert report["eligibility"] == report["enrichment"] == report["ranking"] == "not_evaluated"
    assert not report["promotion_eligible"]
    assert (manifest, files) == before
    report["complete"] = False
    manifest["universe"]["tickers"].clear()
    files.clear()
    assert result.report["complete"]
    assert len(result.report["universe"]["tickers"]) == 2


def test_bridge_and_missing_guard_perform_no_io_or_provider_calls(bundle, monkeypatch):
    import builtins
    import io
    from pathlib import Path
    import subprocess

    manifest, files = bundle
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("forbidden operation")

    with monkeypatch.context() as patch:
        for obj, attr in [(builtins, "open"), (io, "open"), (Path, "open"),
                          (subprocess, "Popen"), (F, "run"), (F, "_batch_history"), (A, "_collect")]:
            patch.setattr(obj, attr, forbidden)
        try:
            with pytest.raises(B.PriceBridgeRefused):
                B.validate_manifest({})
            assert B.stage_verified_prices(manifest=manifest, artifacts=files).report["complete"]
        finally:
            assert calls == []  # Outside bridge: a caught AssertionError cannot hide a call.


@pytest.mark.parametrize("change", ["missing_pin", "wrong_hash", "duplicate_universe", "truncated",
                                    "wrong_membership", "empty_calendar", "duplicate_calendar"])
def test_manifest_refuses_before_export(bundle, change):
    m, files = bundle
    if change == "missing_pin":
        del m["source_pins"]
    elif change == "wrong_hash":
        m["acquisition"]["sha256"] = "0" * 64
    elif change == "duplicate_universe":
        m["universe"]["tickers"].append("AAA")
    elif change == "truncated":
        m["universe"]["truncated"] = True
    elif change == "wrong_membership":
        m["universe"]["membership_sha256"] = "0" * 64
    elif change == "empty_calendar":
        m["required_sessions"] = []
    else:
        m["required_sessions"].append(m["required_sessions"][-1])
    with pytest.raises(B.PriceBridgeRefused):
        B.stage_verified_prices(manifest=m, artifacts=files)


@pytest.mark.parametrize("field", ["max_input_bytes", "max_artifacts", "max_rows", "max_symbols"])
def test_explicit_size_caps_refuse(bundle, field):
    m, files = bundle
    m["limits"][field] = 1
    with pytest.raises(B.PriceBridgeRefused):
        B.stage_verified_prices(manifest=m, artifacts=files)


@pytest.mark.parametrize("bad", [None, True, -1.0, "11", float("inf")])
def test_bad_raw_close_cannot_hide_behind_valid_single_session_receipt(bundle, bad):
    m, files = bundle
    raw = json.loads(files["history-B000001.json"])
    raw["AAA"]["data"][0][raw["AAA"]["columns"].index("Close")] = bad
    # Deliberate nonstandard JSON too: decoder must refuse Infinity, not accept it.
    files["history-B000001.json"] = json.dumps(raw).encode()
    reseal(m, files)
    refused(m, files)


@pytest.mark.parametrize("change", ["missing_symbol", "short_history", "missing_middle", "wrong_local_date",
                                    "duplicate_date", "wrong_adjustment", "unexpected_symbol"])
def test_history_gaps_and_raw_schema_are_never_inferred_ineligible(bundle, change):
    m, files = bundle
    raw = json.loads(files["history-B000001.json"])
    frame = raw["AAA"]
    if change == "missing_symbol":
        del raw["AAA"]
    elif change in ("short_history", "missing_middle"):
        index = 0 if change == "short_history" else 100
        for field in ("index", "data", "original_session_dates"):
            del frame[field][index]
    elif change == "wrong_local_date":
        frame["original_session_dates"][0] = "2000-01-01"
    elif change == "duplicate_date":
        frame["index"][1] = frame["index"][0]
        frame["original_session_dates"][1] = frame["original_session_dates"][0]
    elif change == "wrong_adjustment":
        frame["adjustment"] = "adjusted"
    else:
        raw["UNEXPECTED"] = deepcopy(frame)
    files["history-B000001.json"] = encode(raw)
    reseal(m, files)
    report = refused(m, files)
    assert {r["ticker"] for r in report["outcomes"]} == {"AAA", "BBB"}
    assert "ineligible" not in {r["status"] for r in report["outcomes"]}
    if change in ("short_history", "missing_middle"):
        assert report["accounting_complete"]
        assert report["usable_price_coverage_complete"]
        assert not report["declared_history_coverage_complete"]


@pytest.mark.parametrize("change", ["partial", "transport_failure", "five_only", "wrong_domain",
                                    "wrong_source_pins", "missing_coverage", "failed_symbol"])
def test_acquisition_and_receipt_scope_cannot_be_promoted(bundle, change):
    m, files = bundle
    acq = json.loads(files["acquisition.json"])
    if change == "partial":
        acq["status"] = "REFUSED"
    elif change == "transport_failure":
        acq["transport_failure"] = "cap"
    elif change == "five_only":
        acq["mode"] = "frozen_five"
    elif change == "wrong_domain":
        acq["universe"]["tickers"].pop()
    elif change == "wrong_source_pins":
        acq["source_pins"]["worker.py"] = "b" * 64
    elif change == "missing_coverage":
        name = acq.pop("price_coverage")["file"]
        del files[name]
    else:
        acq["symbol_outcomes"]["AAA"]["status"] = "history_error"
    reseal(m, files, acquisition=acq)
    report = refused(m, files)
    if change == "missing_coverage":
        assert report["accounting_complete"]
        assert not report["usable_price_coverage_complete"]


def test_missing_ohlc_remains_explicit_without_fabrication(bundle):
    m, files = bundle
    raw = json.loads(files["history-B000001.json"])
    for frame in raw.values():
        indices = [frame["columns"].index(c) for c in ("Close", "Volume")]
        frame["data"] = [[r[i] for i in indices] for r in frame["data"]]
        frame["columns"] = ["Close", "Volume"]
    files["history-B000001.json"] = encode(raw)
    reseal(m, files)
    report = B.stage_verified_prices(manifest=m, artifacts=files).report
    assert report["complete"]  # Only the declared CV/history input scope.
    for inputs in report["inputs"].values():
        assert inputs["missing_raw_ohlcv_fields"] == ["High", "Low", "Open"]
        assert inputs["ohlcv_grade_admission"] == "not_evaluated"
        assert inputs["raw_history"]["columns"] == ["Close", "Volume"]


@pytest.mark.parametrize("change", ["raw_admission", "duplicate_json", "extra_file", "wrong_receipt"])
def test_artifact_lineage_and_duplicate_keys_are_revalidated(bundle, change):
    m, files = bundle
    if change == "raw_admission":
        raw = json.loads(files["universe_response.json"])
        raw[0]["mic"] = "OTC"
        files["universe_response.json"] = encode(raw)
    elif change == "duplicate_json":
        files["plan.json"] = b'{"mode":"full_us","mode":"full_us"}'
    elif change == "extra_file":
        files["unrelated.json"] = b'{}'
        m["limits"]["max_artifacts"] += 1
    else:
        coverage = json.loads(files["funnel-price-staging/price.json"])
        coverage["outcomes"][0]["prices_sha256"] = "0" * 64
        files["funnel-price-staging/price.json"] = encode(coverage)
    reseal(m, files)
    refused(m, files)


def test_actual_reviewed_collector_artifacts_feed_bridge_without_sdk_or_native_job(bundle, tmp_path):
    from types import SimpleNamespace
    from backend.tests.test_beta_v2_funnel_acquisition import full_request

    m, files = bundle
    raw = json.loads(files["history-B000001.json"])["AAA"]
    idx = pd.to_datetime(raw["index"], utc=True).tz_convert(raw["index_timezone"])
    frame = pd.DataFrame(raw["data"], columns=raw["columns"], index=idx)
    request = full_request(tmp_path, history_start=m["required_sessions"][0],
                           history_end=m["required_sessions"][-1],
                           coverage_start=m["required_sessions"][-1],
                           coverage_end=m["required_sessions"][-1])
    meter = A.AttemptMeter(request["limits"], 100, tmp_path, clock=lambda: 0)

    class Session:
        def get(self, url, **kwargs):
            meter.perform(lambda: None, "mock universe")
            return SimpleNamespace(status_code=200, content=files["universe_response.json"])

    def history(symbol, **kwargs):
        meter.perform(lambda: None, "mock chart")
        return frame.copy()

    (tmp_path / "funnel-price-staging").mkdir()
    acq = A._collect(request, tmp_path, meter, Session(), history, finnhub_key="fixture-only-secret")
    assert acq["status"] == "COMPLETE"
    refs = [acq["raw_universe"], acq["price_coverage"], *acq["artifacts"]]
    actual = {d["file"]: (tmp_path / d["file"]).read_bytes() for d in refs}
    actual["acquisition.json"] = (tmp_path / "acquisition.json").read_bytes()
    m.update(universe=acq["universe"], source_pins=acq["source_pins"],
             acquisition=descriptor("acquisition.json", actual["acquisition.json"]))
    result = B.stage_verified_prices(manifest=m, artifacts=actual)
    assert result.report["complete"]
    assert result.report["inputs"]["AAA"]["raw_history"] == raw


@pytest.mark.parametrize("body", [b'{bad', b'"unterminated', b'\xff',
                                  b'[' * 2000 + b'0' + b']' * 2000])
def test_malformed_or_deep_json_fails_closed_as_custom_refusal(bundle, body):
    m, files = bundle
    files["plan.json"] = body
    reseal(m, files)
    report = refused(m, files)
    assert not report["accounting_complete"]
    assert {r["ticker"] for r in report["outcomes"]} == {"AAA", "BBB"}


@pytest.mark.parametrize("depth", [70, 2000])
def test_deep_manifest_and_recursion_failure_use_custom_refusal(bundle, depth):
    m, files = bundle
    nested = []
    for _ in range(depth):
        nested = [nested]
    m["extra"] = nested
    with pytest.raises(B.PriceBridgeRefused):
        B.stage_verified_prices(manifest=m, artifacts=files)


def test_parser_recursion_error_cannot_escape_bridge(bundle, monkeypatch):
    m, files = bundle
    original = B._decode

    def recurse_only_on_artifact(data):
        if data == files["plan.json"]:
            raise RecursionError("private parser context must not appear")
        return original(data)

    monkeypatch.setattr(B, "_decode", recurse_only_on_artifact)
    report = refused(m, files)
    assert "private parser context" not in str(report)


def test_json_depth_guard_ignores_escaped_quotes_and_brackets_in_strings(bundle):
    m, files = bundle
    plan = json.loads(files["plan.json"])
    plan["note"] = 'escaped "quotes" and \\ paths: ' + '[' * 200 + ']' * 200
    files["plan.json"] = encode(plan)
    reseal(m, files)
    assert B.stage_verified_prices(manifest=m, artifacts=files).report["complete"]


def test_coverage_cannot_bind_forged_plan_even_when_all_hashes_agree(bundle):
    m, files = bundle
    plan = json.loads(files["plan.json"])
    plan.update(AAA=True, BBB=True)
    files["plan.json"] = encode(plan)
    coverage = json.loads(files["funnel-price-staging/price.json"])
    for batch in coverage["batches"]:
        batch["provenance"]["cache_provenance"]["identity"] = "plan.json"
    files["funnel-price-staging/price.json"] = encode(coverage)
    reseal(m, files)  # Including the wrong object's valid digest: not a hash-only test.
    report = refused(m, files)
    assert report["accounting_complete"]
    assert not report["usable_price_coverage_complete"]
    assert all("coverage_raw_lineage" in r["reasons"] for r in report["outcomes"])


def test_coverage_exact_history_identity_still_requires_its_actual_digest(bundle):
    m, files = bundle
    coverage = json.loads(files["funnel-price-staging/price.json"])
    coverage["batches"][0]["provenance"]["cache_provenance"]["sha256"] = "0" * 64
    files["funnel-price-staging/price.json"] = encode(coverage)
    acq = json.loads(files["acquisition.json"])
    acq["price_coverage"] = descriptor("funnel-price-staging/price.json",
                                       files["funnel-price-staging/price.json"])
    files["acquisition.json"] = encode(acq)
    m["acquisition"] = descriptor("acquisition.json", files["acquisition.json"])
    report = refused(m, files)
    assert all("coverage_raw_lineage" in r["reasons"] for r in report["outcomes"])


def test_exact_lineage_supports_distinct_history_batches(bundle):
    m, files = bundle
    raw = json.loads(files["history-B000001.json"])
    files["history-B000001.json"] = encode({"AAA": raw["AAA"]})
    files["history-B000002.json"] = encode({"BBB": raw["BBB"]})
    acq = json.loads(files["acquisition.json"])
    acq["artifacts"].append(descriptor("history-B000002.json", files["history-B000002.json"]))
    coverage = json.loads(files["funnel-price-staging/price.json"])
    first = deepcopy(coverage["batches"][0])
    coverage["batches"] = []
    for i, symbol in enumerate(("AAA", "BBB"), 1):
        batch_id = f"B{i:06d}"
        batch = deepcopy(first)
        batch.update(batch_id=batch_id, tickers=[symbol], returned_symbols=[symbol])
        batch["provenance"]["cache_provenance"]["identity"] = f"history-{batch_id}.json"
        coverage["batches"].append(batch)
        coverage["outcomes"][i - 1]["batch_ids"] = [batch_id]
    coverage["limits"].update(batch_size=1, max_logical_calls=2, max_batches=2)
    coverage["usage"].update(logical_calls=2, batches=2)
    files["funnel-price-staging/price.json"] = encode(coverage)
    m["limits"]["max_artifacts"] = 6
    reseal(m, files, acquisition=acq)
    report = B.stage_verified_prices(manifest=m, artifacts=files).report
    assert report["complete"]
    assert report["inputs"]["AAA"]["raw_artifact"] == "history-B000001.json"
    assert report["inputs"]["BBB"]["raw_artifact"] == "history-B000002.json"
