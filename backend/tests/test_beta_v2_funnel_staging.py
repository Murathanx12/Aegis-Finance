"""Offline price coverage only: no funnel runner, caches, or real providers."""
import hashlib
import json
import os
from dataclasses import replace

import pandas as pd
import pytest

from backend.services import funnel_staging as S
from backend.services import opportunity_funnel as F


def provenance():
    return {"source": "tiny injected fixture", "fetched_at": "2026-10-23T12:00:00+00:00",
            "cache_provenance": {"mode": "injected", "identity": "fixture-v1",
                                 "sha256": "a" * 64}}


def manifest(tickers=("AAA", "BBB", "CCC")):
    return {**provenance(), "tickers": list(tickers), "n": len(tickers),
            "membership_sha256": S.membership_sha256(tickers), "truncated": False,
            "exclusions": {"venue": 2, "type": 1, "symbol": 0}}


def bars():
    return pd.DataFrame({"Close": [10.0, 11.0], "Volume": [100, 200]},
                        index=pd.to_datetime(["2026-10-22", "2026-10-23"]))


@pytest.fixture
def limits():
    return S.Limits(batch_size=2, max_logical_calls=2, max_batches=2, max_symbols=3)


def collect(limits, provider, universe=None):
    return F.stage_price_coverage(
        universe=manifest() if universe is None else universe, provider=provider,
        limits=limits, start_date="2026-10-22", end_date="2026-10-23", min_rows=2)


def provider(batch_id, tickers):
    return {**provenance(), "prices": [(t, bars()) for t in tickers]}


def test_exact_membership_hash():
    expected = hashlib.sha256(b'["AAA","BBB","CCC"]').hexdigest()
    assert S.membership_sha256(["CCC", "AAA", "BBB"]) == expected
    assert S.membership_sha256(["AAA", "BBB"]) != expected


def test_full_success_is_coverage_only_and_pins_inputs(limits):
    calls = []
    u = manifest()

    def injected(batch_id, tickers):
        calls.append((batch_id, tickers))
        u["source"] = "mutated after invocation"
        return provider(batch_id, tickers)

    receipt = collect(limits, injected, u)
    report = receipt.report
    assert calls == [("B000001", ("AAA", "BBB")), ("B000002", ("CCC",))]
    assert report["artifact_kind"] == "admitted_universe_price_coverage_v1"
    assert report["full_coverage"] is True
    assert report["universe"]["source"] == "tiny injected fixture"
    assert report["universe"]["membership_sha256"] == manifest()["membership_sha256"]
    assert report["usage"] == {"logical_calls": 2, "batches": 2, "symbols": 3}
    assert report["claims"] == {"ranking": False, "eligibility": False,
                                "ic_acceptance": False, "parent_completion": False}
    assert "candidates" not in report
    assert [r["ticker"] for r in report["outcomes"]] == manifest()["tickers"]
    for row in report["outcomes"]:
        assert row["status"] == "valid"
        assert row["batch_ids"]
        assert row["rows"] == 2
        assert row["first_date"] == "2026-10-22"
        assert row["last_date"] == "2026-10-23"
        assert len(row["prices_sha256"]) == 64
    assert report["batches"][0]["provenance"] == provenance()
    report["full_coverage"] = False
    assert receipt.report["full_coverage"] is True  # immutable receipt bytes


@pytest.mark.parametrize("change", [
    {"n": 4}, {"n": True}, {"membership_sha256": "0" * 64}, {"truncated": True},
    {"tickers": ["AAA", "AAA", "CCC"]}, {"tickers": ["AAA", "BBB"]},
    {"tickers": ["aaa", "BBB", "CCC"]}, {"fetched_at": "yesterday"},
    {"exclusions": {"venue": -1}}, {"cache_provenance": {}}, {"source": ""},
])
def test_universe_refusal_before_any_calls(limits, change):
    calls = []
    u = {**manifest(), **change}
    with pytest.raises(S.CoverageRefused) as exc:
        collect(limits, lambda *a: calls.append(a), u)
    assert not calls
    report = exc.value.report
    assert report["full_coverage"] is False
    assert len(report["outcomes"]) == len(u["tickers"])
    assert all(r["status"] == "not_attempted" and not r["batch_ids"]
               for r in report["outcomes"])


def test_hash_mismatch_has_specific_reason(limits):
    with pytest.raises(S.CoverageRefused, match="universe_membership_hash_mismatch"):
        collect(limits, provider, {**manifest(), "membership_sha256": "0" * 64})


@pytest.mark.parametrize("change", [{"start_date": "bad"}, {"start_date": "2026-W43-4"},
                                    {"end_date": "2026-10-21"},
                                    {"min_rows": 3}, {"min_rows": True}])
def test_invalid_window_refuses_before_calls(limits, change):
    calls = []
    args = {"universe": manifest(), "provider": lambda *a: calls.append(a),
            "limits": limits, "start_date": "2026-10-22", "end_date": "2026-10-23",
            "min_rows": 2, **change}
    with pytest.raises(S.CoverageRefused):
        F.stage_price_coverage(**args)
    assert not calls


@pytest.mark.parametrize("change", [
    {"max_logical_calls": 1}, {"max_batches": 1}, {"max_symbols": 2},
    {"batch_size": 0}, {"batch_size": True}, {"max_symbols": -1},
])
def test_full_domain_over_budget_refuses_before_calls(limits, change):
    calls = []
    with pytest.raises(S.CoverageRefused) as exc:
        collect(replace(limits, **change), lambda *a: calls.append(a))
    assert not calls
    assert len(exc.value.report["outcomes"]) == 3
    assert exc.value.report["usage"]["logical_calls"] == 0


def broken_frame(kind):
    df = bars()
    if kind == "nonfinite":
        df.loc[df.index[0], "Close"] = float("nan")
    elif kind == "infinite_volume":
        df["Volume"] = [float("inf"), 200]
    elif kind == "negative_volume":
        df["Volume"] = [-1, 200]
    elif kind == "fractional_volume":
        df["Volume"] = [1.5, 200]
    elif kind == "zero_price":
        df["Close"] = [0, 11]
    elif kind == "string_price":
        df["Close"] = ["10", "11"]
    elif kind == "bool_price":
        df["Close"] = [True, False]
    elif kind == "duplicate_date":
        df.index = pd.to_datetime(["2026-10-22", "2026-10-22"])
    elif kind == "nat":
        df.index = pd.to_datetime(["2026-10-22", None])
    elif kind == "string_index":
        df.index = ["2026-10-22", "2026-10-23"]
    elif kind == "unsorted":
        df = df.iloc[::-1]
    elif kind == "future":
        df.index = df.index + pd.Timedelta(days=1)
    elif kind == "stale":
        df.index = df.index - pd.Timedelta(days=1)
    elif kind == "intraday":
        df.index = df.index + pd.Timedelta(hours=1)
    elif kind == "schema":
        df = df.drop(columns="Volume")
    elif kind == "duplicate_column":
        df.columns = ["Close", "Close"]
    elif kind == "short":
        df = df.iloc[:1]
    elif kind == "empty":
        df = df.iloc[:0]
    return df


@pytest.mark.parametrize("kind", [
    "exception", "empty_batch", "missing", "duplicate_symbol", "unexpected_symbol",
    "nonfinite", "infinite_volume", "negative_volume", "fractional_volume",
    "zero_price", "string_price", "bool_price", "duplicate_date", "nat",
    "string_index", "unsorted", "future", "stale", "intraday", "schema",
    "duplicate_column", "short", "empty", "bad_provenance", "bad_response",
])
def test_partial_failures_account_for_every_ticker_without_retry(limits, kind, tmp_path):
    calls = []

    def injected(batch_id, tickers):
        calls.append(batch_id)
        if batch_id == "B000002":
            return provider(batch_id, tickers)
        if kind == "exception":
            raise RuntimeError("failure with potentially private details")
        response = provider(batch_id, tickers)
        if kind == "empty_batch":
            response["prices"] = []
        elif kind == "missing":
            response["prices"] = response["prices"][:1]
        elif kind == "duplicate_symbol":
            response["prices"].append(("AAA", bars()))
        elif kind == "unexpected_symbol":
            response["prices"].append(("ZZZ", bars()))
        elif kind == "bad_provenance":
            response["fetched_at"] = "invalid"
        elif kind == "bad_response":
            return None
        else:
            response["prices"][0] = ("AAA", broken_frame(kind))
        return response

    with pytest.raises(S.CoverageRefused) as exc:
        collect(limits, injected)
    report = exc.value.report
    assert report["full_coverage"] is False
    assert calls == ["B000001", "B000002"]
    assert len(report["outcomes"]) == 3
    assert report["outcomes"][-1]["status"] == "valid"
    assert all(r["batch_ids"] for r in report["outcomes"])
    assert report["errors"]
    if kind in ("nonfinite", "infinite_volume"):
        assert report["outcomes"][0]["status"] == "nonfinite"
    if kind == "missing":
        assert report["outcomes"][0]["status"] == "valid"
        assert report["outcomes"][1]["status"] == "missing"
    if kind == "duplicate_symbol":
        assert report["outcomes"][0]["reason"] == "duplicate_symbol"
    if kind == "unexpected_symbol":
        assert report["batches"][0]["unexpected_symbols"] == ["ZZZ"]
    assert "potentially private" not in json.dumps(report)
    with pytest.raises(S.CoverageRefused):
        S.write_price_coverage(report, staging_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_immutable_exclusive_staging_writer(limits, tmp_path):
    receipt = collect(limits, provider)
    staging = tmp_path / "funnel-price-staging"
    staging.mkdir()
    destination = S.write_price_coverage(receipt, staging_dir=staging)
    original = destination.read_bytes()
    assert json.loads(original) == receipt.report
    assert destination.name.startswith("price-coverage-")
    with pytest.raises(S.CoverageRefused) as exc:
        S.write_price_coverage(receipt, staging_dir=staging)
    assert exc.value.report["outcomes"] == receipt.report["outcomes"]
    assert destination.read_bytes() == original
    assert len(list(staging.iterdir())) == 1


@pytest.mark.parametrize("field,value", [
    ("status", "missing"), ("batch_ids", []), ("rows", 0), ("last_date", "2026-10-22"),
    ("last_close", -1), ("last_volume", 1.5), ("prices_sha256", "bad"),
    ("schema", ["Close"]),
])
def test_writer_revalidates_symbol_accounting(limits, tmp_path, field, value):
    report = collect(limits, provider).report
    report["outcomes"][0][field] = value
    modified = S.PriceCoverage(json.dumps(report).encode())
    staging = tmp_path / "funnel-price-staging"
    staging.mkdir()
    with pytest.raises(S.CoverageRefused):
        S.write_price_coverage(modified, staging_dir=staging)
    assert not list(staging.iterdir())


def test_writer_revalidates_batch_accounting(limits, tmp_path):
    report = collect(limits, provider).report
    report["batches"][0]["returned_symbols"].append("ZZZ")
    modified = S.PriceCoverage(json.dumps(report).encode())
    staging = tmp_path / "funnel-price-staging"
    staging.mkdir()
    with pytest.raises(S.CoverageRefused, match="invalid_batch_accounting"):
        S.write_price_coverage(modified, staging_dir=staging)
    assert not list(staging.iterdir())


@pytest.mark.parametrize("parent", ["production", "cache", ".cache", "history",
                                          "funnel_cache", "funnel_history", "data"])
def test_refuse_production_cache_history_destinations(limits, tmp_path, parent):
    staging = tmp_path / parent / "funnel-price-staging"
    staging.mkdir(parents=True)
    with pytest.raises(S.CoverageRefused):
        S.write_price_coverage(collect(limits, provider), staging_dir=staging)
    assert not list(staging.iterdir())


def test_refuse_undesignated_destination(limits, tmp_path):
    with pytest.raises(S.CoverageRefused):
        S.write_price_coverage(collect(limits, provider), staging_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_refuse_symlink_alias_to_production(limits, tmp_path):
    production = tmp_path / "production"
    production.mkdir()
    alias = tmp_path / "funnel-price-staging"
    try:
        alias.symlink_to(production, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("OS does not permit symlinks")
        import _winapi
        _winapi.CreateJunction(str(production), str(alias))
    with pytest.raises(S.CoverageRefused):
        S.write_price_coverage(collect(limits, provider), staging_dir=alias)
    assert not list(production.iterdir())


def test_refuse_staging_nested_in_configured_data_root(limits, tmp_path, monkeypatch):
    staging = tmp_path / "volume" / "funnel-price-staging"
    staging.mkdir(parents=True)
    monkeypatch.setenv("AEGIS_DATA_DIR", str(staging.parent))
    with pytest.raises(S.CoverageRefused, match="protected_destination"):
        S.write_price_coverage(collect(limits, provider), staging_dir=staging)
    assert not list(staging.iterdir())


def test_failed_write_removes_only_its_new_file(limits, tmp_path, monkeypatch):
    staging = tmp_path / "funnel-price-staging"
    staging.mkdir()
    previous = staging / "previous-receipt.json"
    previous.write_bytes(b"untouched")
    def broken_fsync(fd):
        raise OSError("disk failure")
    monkeypatch.setattr(S.os, "fsync", broken_fsync)
    with pytest.raises(S.CoverageRefused) as exc:
        S.write_price_coverage(collect(limits, provider), staging_dir=staging)
    assert len(exc.value.report["outcomes"]) == 3
    assert list(staging.iterdir()) == [previous]
    assert previous.read_bytes() == b"untouched"


def test_wrapper_never_calls_existing_production_path(limits, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("production path invoked")
    for name in ("run", "universe", "_batch_history", "_write_snapshot"):
        monkeypatch.setattr(F, name, forbidden)
    assert collect(limits, provider).report["full_coverage"]


def test_complete_prices_leave_enrichment_ranking_and_promotion_unqualified(limits):
    report = collect(limits, provider).report
    assert report["accounting_complete"] is True
    assert report["usable_price_coverage_complete"] is True
    assert report["screened"] == report["universe"]["n"] == 3
    assert report["outcome_counts"] == {"valid": 3}
    assert report["downstream"] == {"stage3_enrichment": "not_evaluated",
                                     "ranking": "not_evaluated"}
    assert report["promotion_eligible"] is False


def test_missing_prices_are_fully_accounted_but_not_usable_or_promotable(limits):
    def missing(batch_id, tickers):
        response = provider(batch_id, tickers)
        response["prices"] = [(t, df) for t, df in response["prices"] if t != "BBB"]
        return response
    with pytest.raises(S.CoverageRefused) as exc:
        collect(limits, missing)
    report = exc.value.report
    assert report["accounting_complete"] is True
    assert report["usable_price_coverage_complete"] is False
    assert report["full_coverage"] is False
    assert report["screened"] == 3
    assert report["outcome_counts"] == {"valid": 2, "missing": 1}
    assert report["promotion_eligible"] is False


def test_preflight_refusal_does_not_claim_completed_acquisition_accounting(limits):
    with pytest.raises(S.CoverageRefused) as exc:
        collect(replace(limits, max_symbols=2), provider)
    assert exc.value.report["accounting_complete"] is False
    assert exc.value.report["usable_price_coverage_complete"] is False
    assert exc.value.report["outcome_counts"] == {"not_attempted": 3}
