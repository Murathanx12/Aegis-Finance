"""CH-05 rescue R3: global price admission, freshness diagnostic, cache lock.

Ported from the runtime checkout. Offline: every price frame is a fixture and
every path is under `tmp_path`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

import pandas as pd
import pytest

from backend.services import global_price_admission as GA
from backend.services import global_prices as GP

OWNER = {"workflow": "STAGED_PRICE_ADMISSION", "owner_id": "fixture-owner",
         "operation_id": "fixture-one"}
OBSERVED = "2026-11-05T12:00:00+00:00"


def _existing() -> pd.DataFrame:
    df = pd.DataFrame([["ABC", pd.Timestamp("2026-11-03"), 10.0, 11.0, 9.0, 10.5, 100.0,
                        "yfinance", "2026-11-04T00:00:00+00:00"]], columns=GP.COLUMNS)
    df["date"] = df["date"].astype("datetime64[ns]")
    return df


def _staged(close: float = 10.8) -> pd.DataFrame:
    return pd.DataFrame([["ABC", "2026-11-04", 10.5, 11.2, 10.1, close, 120.0]],
                        columns=GP.COLUMNS[:7])


def _receipt(staged: pd.DataFrame) -> tuple[dict, str]:
    close_at = pd.Timestamp("2026-11-04T21:00:00+00:00")
    receipt = {
        "schema": "staged_ohlcv_receipt/1", "receipt_id": "r1", "source": "fixture",
        "source_hashes": {"vendor.csv": "a" * 64},
        "auto_adjust": False, "fx_converted": False, "dividend_adjusted": False,
        "price_basis": "UNADJUSTED_LOCAL", "session_label_basis": "EXPLICIT_LOCAL_SESSION_DATE",
        "staged_sha256": GA.staged_sha256(staged),
        "observed_at": OBSERVED, "retrieved_at": "2026-11-05T01:00:00+00:00",
        "currency_by_symbol": {"ABC": "USD"}, "calendar_policy_sha256": "b" * 64,
        "completed_sessions": {"ABC": {
            "symbol": "ABC", "session": "2026-11-04", "calendar": "XNYS",
            "close_at": close_at.isoformat(),
            "eligible_at": (close_at + pd.Timedelta(minutes=90)).isoformat(),
            "exchange_timezone": "America/New_York"}},
    }
    raw = json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return receipt, hashlib.sha256(raw).hexdigest()


def _plan_kwargs(staged: pd.DataFrame) -> dict:
    receipt, sha = _receipt(staged)
    return dict(receipt=receipt, receipt_sha256=sha, source_hashes=receipt["source_hashes"],
                required_sessions={"ABC": "2026-11-04"}, observed_at=OBSERVED,
                owner_context=OWNER)


def test_plan_adds_only_new_keys_and_keeps_old_rows_exact():
    staged = _staged()
    plan = GA.plan_admission(staged, existing=_existing(), preimage_sha256="c" * 64,
                             **_plan_kwargs(staged))
    s = plan.summary
    assert s["new_rows"] == 1 and s["before_rows"] == 1 and s["candidate_rows"] == 2
    assert s["new_keys"] == [["ABC", "2026-11-04"]]
    assert len(plan.sha256) == 64


def test_a_conflicting_existing_row_refuses():
    existing = pd.concat([_existing(), pd.DataFrame(
        [["ABC", pd.Timestamp("2026-11-04"), 10.5, 11.2, 10.1, 99.0, 120.0, "yfinance", "x"]],
        columns=GP.COLUMNS)], ignore_index=True)
    existing["date"] = existing["date"].astype("datetime64[ns]")
    staged = _staged()
    with pytest.raises(GA.AdmissionError, match="CONFLICTING_EXISTING_ROW"):
        GA.plan_admission(staged, existing=existing, preimage_sha256="c" * 64,
                          **_plan_kwargs(staged))


def test_a_tampered_receipt_hash_refuses():
    staged = _staged()
    kwargs = _plan_kwargs(staged)
    kwargs["receipt_sha256"] = "0" * 64
    with pytest.raises(GA.AdmissionError, match="RECEIPT_HASH_MISMATCH"):
        GA.plan_admission(staged, existing=_existing(), preimage_sha256="c" * 64, **kwargs)


def test_publish_requires_verified_owner_closure_then_writes_audit(tmp_path):
    cache = tmp_path / "global_bars.parquet"
    _existing().to_parquet(cache, index=False)
    staged = _staged()
    plan = GA.prepare_admission(staged, cache_path=cache, **_plan_kwargs(staged))
    preimage = hashlib.sha256(cache.read_bytes()).hexdigest()
    with pytest.raises(GA.AdmissionError, match="VERIFIED_OWNER_SOURCE_CLOSURE_REQUIRED"):
        GA.publish_admission(plan, cache_path=cache, audit_dir=tmp_path / "audit",
                             expected_preimage_sha256=preimage, owner_context=OWNER)
    assert hashlib.sha256(cache.read_bytes()).hexdigest() == preimage
    closure = {**OWNER, "cache_path": str(cache.resolve()), "legacy_writers_closed": True,
               "exclusive_owner_verified": True, "source_adoption_verified": True,
               "ownership_receipt_sha256": "d" * 64, "source_adoption_sha256": "e" * 64,
               "admission_plan_sha256": plan.sha256}
    out = GA.publish_admission(plan, cache_path=cache, audit_dir=tmp_path / "audit",
                               expected_preimage_sha256=preimage, owner_context=closure)
    assert out["status"] == "PUBLISHED"
    after = pd.read_parquet(cache)
    assert len(after) == 2 and after["close"].tolist() == [10.5, 10.8]
    assert (tmp_path / "audit" / "admission_fixture-one.before.parquet").read_bytes()
    # A second publish of the same plan cannot reuse the exclusive audit slot.
    with pytest.raises(GA.AdmissionError):
        GA.publish_admission(plan, cache_path=cache, audit_dir=tmp_path / "audit",
                             expected_preimage_sha256=preimage, owner_context=closure)


def test_freshness_without_a_target_is_not_evaluated_never_fresh():
    bars = _existing()
    out = GP.freshness_diagnostic(bars, ["ABC"])
    assert out["status"] == "NOT_EVALUATED"
    assert out["symbols"][0]["status"] == "UNKNOWN_REQUIRED_SESSION"


def test_freshness_names_stale_and_fresh_against_an_explicit_session():
    bars = _existing()
    assert GP.freshness_diagnostic(bars, ["ABC"], required_session="2026-11-03")["status"] \
        == "COMPLETE_TARGET_COVERAGE"
    stale = GP.freshness_diagnostic(bars, ["ABC"], required_session=date(2026, 11, 4))
    assert stale["status"] == "INCOMPLETE_OR_UNKNOWN_TARGET_COVERAGE"
    assert stale["symbols"][0]["status"] == "STALE"
    with pytest.raises(ValueError, match="EXACT_SESSION_DATE_REQUIRED"):
        GP.freshness_diagnostic(bars, ["ABC"], required_session=datetime(2026, 11, 4))


def test_ensure_refuses_an_unknown_target_ticker_before_any_io(tmp_path):
    calls = []
    with pytest.raises(ValueError, match="UNKNOWN_OR_DUPLICATE_SESSION_TARGET_TICKER"):
        GP.ensure(["ABC"], start="2026-11-01", path=tmp_path / "g.parquet",
                  downloader=lambda *a: calls.append(a),
                  required_session={"XYZ": "2026-11-04"})
    assert calls == [] and not (tmp_path / "g.parquet").exists()


def test_ensure_holds_the_shared_cache_lock_while_it_writes(tmp_path):
    p = tmp_path / "g.parquet"
    seen = []

    def dl(tickers, start, end):
        lock = GP.cache_lock(p, timeout=0)
        try:
            lock.acquire()
            seen.append("acquired")
            lock.release()
        except Exception:                                          # noqa: BLE001
            seen.append("held")
        return pd.DataFrame([["ABC", pd.Timestamp("2026-11-03"), 1.0, 1.0, 1.0, 1.0, 1.0]],
                            columns=GP.COLUMNS[:7])

    out = GP.ensure(["ABC"], start="2026-11-01", path=p, today=date(2026, 11, 5),
                    downloader=dl, required_session="2026-11-03")
    # A second lock on the same cache cannot be taken while the fetch runs,
    # which is what serializes the daily fetch with a staged admission.
    assert seen == ["held"]
    assert out.attrs["receipt"]["freshness"]["status"] == "COMPLETE_TARGET_COVERAGE"
    assert out.attrs["receipt"]["n_ok_semantics"].startswith("HISTORICAL_PRESENCE")
