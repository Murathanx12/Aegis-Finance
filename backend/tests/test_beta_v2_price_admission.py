"""Admission and cooperative writer fixtures, entirely under pytest tmp paths."""
import hashlib
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from backend.services import global_price_admission as A
from backend.services import global_prices as GP


S = date(2026, 10, 23)
NOW = datetime(2026, 10, 25, 7, tzinfo=timezone.utc)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def stage(symbol="EVO.ST", day=S):
    return pd.DataFrame({"symbol": [symbol], "date": pd.to_datetime([day]),
                         "open": [10.], "high": [12.], "low": [9.], "close": [11.], "volume": [100.]})


def old_frame():
    frame = stage(day=S - timedelta(days=1))
    frame["source"] = "old_vendor"
    frame["pulled_utc"] = "2026-10-23T22:00:00+00:00"
    return frame[GP.COLUMNS]


def inputs(frame=None, operation="fixture-one"):
    frame = stage() if frame is None else frame
    targets = {s: pd.Timestamp(d).date().isoformat() for s, d in zip(frame.symbol, frame.date)}
    receipt = {"schema": "staged_ohlcv_receipt/1", "receipt_id": "verified-raw-fixture",
               "source": "fixture_original_vendor", "staged_sha256": A.staged_sha256(frame),
               "source_hashes": {"raw.json": digest(b"retained raw fixture bytes")},
               "auto_adjust": False, "fx_converted": False, "dividend_adjusted": False,
               "price_basis": "UNADJUSTED_LOCAL", "session_label_basis": "EXPLICIT_LOCAL_SESSION_DATE",
               "observed_at": NOW.isoformat(), "retrieved_at": NOW.isoformat(),
               "currency_by_symbol": dict.fromkeys(targets, "SEK"),
               "calendar_policy_sha256": "a" * 64,
               "completed_sessions": {s: {"symbol": s, "session": d, "calendar": "XSTO", "exchange_timezone": "Europe/Stockholm",
                   "close_at": d + "T15:30:00+00:00", "eligible_at": d + "T17:00:00+00:00"}
                   for s, d in targets.items()}}
    return {"staged": frame, "receipt": receipt, "receipt_sha256": digest(encoded(receipt)),
            "source_hashes": dict(receipt["source_hashes"]), "required_sessions": targets,
            "observed_at": NOW, "owner_context": {"workflow": "STAGED_PRICE_ADMISSION",
                "owner_id": "fixture-coordinator", "operation_id": operation}}


def refresh_receipt(arguments):
    arguments["receipt_sha256"] = digest(encoded(arguments["receipt"]))


def closure(plan):
    return {**plan.summary["owner"], "legacy_writers_closed": True, "exclusive_owner_verified": True,
            "source_adoption_verified": True, "ownership_receipt_sha256": "b" * 64,
            "source_adoption_sha256": "c" * 64, "admission_plan_sha256": plan.sha256,
            "cache_path": plan.summary["cache_path"]}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("native path/downloader forbidden")
    monkeypatch.setattr(GP, "cache_path", forbidden)
    monkeypatch.setattr(GP, "_yf_download", forbidden)
    path = tmp_path / "global.parquet"
    old_frame().to_parquet(path, index=False)
    GP._state_path(path).write_bytes(b'{"EVO.ST":"2026-10-25","UNRELATED":"2026-10-24"}')
    GP.receipt_path(NOW.date(), base=tmp_path).write_bytes(b'{"legacy":"receipt must not change"}')
    return path


def publish(plan, cache, **kwargs):
    return A.publish_admission(plan, cache_path=cache, audit_dir=cache.parent / "audit",
        expected_preimage_sha256=plan.summary["preimage_sha256"],
        owner_context=kwargs.pop("owner_context", closure(plan)), **kwargs)


def test_pure_plan_has_private_candidate_and_no_file_access(monkeypatch):
    args = inputs()
    before = old_frame()
    original = before.copy(deep=True)
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("pure plan read a file"))
    plan = A.plan_admission(**args, existing=before, preimage_sha256="d" * 64)
    assert plan.summary["new_rows"] == 1
    assert plan.summary["candidate_rows"] == 2
    assert plan.summary["candidate_sha256"] == digest(plan._candidate)
    pd.testing.assert_frame_equal(before, original)
    changed = plan.summary
    changed["new_rows"] = 999
    assert plan.summary["new_rows"] == 1


def test_prepare_no_arguments_is_the_genuine_shared_guard_case(monkeypatch):
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("missing input read a file"))
    monkeypatch.setattr(A, "_publish_locked", lambda *_: pytest.fail("missing input published"))
    with pytest.raises(A.AdmissionError, match="OWNER_CONTEXT_REQUIRED"):
        A.prepare_admission()
    with pytest.raises(A.AdmissionError, match="OWNER_CONTEXT_REQUIRED"):
        GP.prepare_staged_admission()


def test_publish_keeps_raw_predecessor_every_old_value_and_fetch_markers(cache):
    raw = cache.read_bytes()
    markers = GP._state_path(cache).read_bytes()
    legacy_receipt = GP.receipt_path(NOW.date(), base=cache.parent).read_bytes()
    old = pd.read_parquet(cache)
    plan = GP.prepare_staged_admission(cache_path=cache, **inputs())
    assert cache.read_bytes() == raw
    result = publish(plan, cache)
    assert result["status"] == "PUBLISHED"
    assert Path(result["predecessor_copy"]).read_bytes() == raw
    assert json.loads(Path(result["audit_receipt"]).read_text())["status"] == "PUBLISHED"
    after = pd.read_parquet(cache)
    pd.testing.assert_frame_equal(old, after.iloc[:1].reset_index(drop=True), check_exact=True)
    assert list(after.dtypes) == list(old.dtypes)
    assert after.iloc[1]["source"] == "fixture_original_vendor"
    assert GP._state_path(cache).read_bytes() == markers
    assert GP.receipt_path(NOW.date(), base=cache.parent).read_bytes() == legacy_receipt
    assert not list(cache.parent.glob(".price-admission-*.tmp"))


def test_identical_key_is_no_change_preserving_old_metadata_and_raw_bytes(cache):
    same = old_frame().iloc[:, :7]
    args = inputs(same)
    raw = cache.read_bytes()
    plan = A.prepare_admission(cache_path=cache, **args)
    assert plan.summary["new_rows"] == 0 and plan.summary["identical_skipped"] == 1
    assert publish(plan, cache)["status"] == "NO_CHANGE"
    assert cache.read_bytes() == raw
    assert not (cache.parent / "audit").exists()


def test_admit_then_reprepare_is_idempotent(cache):
    publish(A.prepare_admission(cache_path=cache, **inputs()), cache)
    raw = cache.read_bytes()
    second = A.prepare_admission(cache_path=cache, **inputs(operation="second"))
    assert second.summary["new_rows"] == 0
    assert publish(second, cache)["status"] == "NO_CHANGE"
    assert cache.read_bytes() == raw


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
def test_conflicting_overlap_refuses_whole_batch_without_files(cache, column):
    staged = pd.concat([stage(day=S - timedelta(days=1)), stage()], ignore_index=True)
    # A conflict alongside an otherwise valid new key must not partly admit.
    staged.loc[0, column] += .5 if column not in ("low",) else -.5
    if column == "open":
        staged.loc[0, "high"] = 13.
    args = inputs(staged)
    before = {p.name: p.read_bytes() for p in cache.parent.iterdir()}
    with pytest.raises(A.AdmissionError, match="INCOMPLETE_OR_MISMATCHED_TARGETS"):
        A.prepare_admission(cache_path=cache, **args)
    # One target per symbol is intentional. Test a different symbol for new key.
    staged.loc[1, "symbol"] = "RHM.DE"
    args = inputs(staged)
    with pytest.raises(A.AdmissionError, match="CONFLICTING_EXISTING_ROW"):
        A.prepare_admission(cache_path=cache, **args)
    assert {p.name: p.read_bytes() for p in cache.parent.iterdir()} == before


@pytest.mark.parametrize("missing", ["receipt", "receipt_sha256", "source_hashes", "required_sessions", "observed_at", "owner_context"])
def test_partial_authority_refuses_before_file_access(monkeypatch, missing):
    args = inputs()
    args[missing] = None
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("accessed file before input validation"))
    with pytest.raises(A.AdmissionError):
        A.prepare_admission(cache_path="must-not-access", **args)
    with pytest.raises(A.AdmissionError):
        A.plan_admission(existing=old_frame(), preimage_sha256="a" * 64, **args)


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1., True, "10"])
def test_invalid_numeric_marks_refuse_before_io(monkeypatch, column, bad):
    args = inputs()
    args["staged"][column] = args["staged"][column].astype(object)
    args["staged"].loc[0, column] = bad
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("invalid stage caused I/O"))
    with pytest.raises(A.AdmissionError):
        A.prepare_admission(cache_path="must-not-access", **args)


@pytest.mark.parametrize("column", ["open", "high", "low", "close"])
def test_zero_price_is_not_synthesized(cache, column):
    args = inputs()
    args["staged"].loc[0, column] = 0.
    with pytest.raises(A.AdmissionError, match="INVALID_OHLCV"):
        A.prepare_admission(cache_path=cache, **args)


def test_zero_volume_is_valid(cache):
    staged = stage()
    staged["volume"] = 0.
    assert A.prepare_admission(cache_path=cache, **inputs(staged)).summary["new_rows"] == 1


@pytest.mark.parametrize("change", ["duplicate", "timezone", "intraday", "wrong_target", "unknown_symbol", "missing_column", "low_above_close", "high_below_open"])
def test_bad_dates_keys_coverage_and_high_low_refuse(cache, change):
    args = inputs()
    if change == "duplicate":
        args["staged"] = pd.concat([args["staged"], args["staged"]], ignore_index=True)
    elif change == "timezone":
        args["staged"]["date"] = pd.to_datetime([S], utc=True)
    elif change == "intraday":
        args["staged"]["date"] += pd.Timedelta(hours=1)
    elif change == "wrong_target":
        args["required_sessions"]["EVO.ST"] = (S - timedelta(days=1)).isoformat()
    elif change == "unknown_symbol":
        args["staged"].loc[0, "symbol"] = "evo.st"
    elif change == "missing_column":
        args["staged"] = args["staged"].drop(columns="volume")
    elif change == "low_above_close":
        args["staged"].loc[0, "low"] = 12.
    else:
        args["staged"].loc[0, "high"] = 9.
    with pytest.raises(A.AdmissionError):
        A.prepare_admission(cache_path=cache, **args)


@pytest.mark.parametrize("field,value", [("auto_adjust", True), ("fx_converted", True), ("dividend_adjusted", True),
    ("price_basis", "ADJUSTED_USD"), ("session_label_basis", "UTC_INFERRED"), ("auto_adjust", 0)])
def test_adjustment_fx_and_inferred_date_flags_refuse(cache, field, value):
    args = inputs()
    args["receipt"][field] = value
    refresh_receipt(args)
    with pytest.raises(A.AdmissionError, match="UNADJUSTED_LOCAL_FLAGS_REQUIRED"):
        A.prepare_admission(cache_path=cache, **args)


@pytest.mark.parametrize("change", ["receipt", "source", "frame", "observation", "future_retrieval", "unclosed", "short_lag", "missing_proof", "naive_close"])
def test_receipt_source_and_completed_target_bindings(cache, change):
    args = inputs()
    if change == "receipt":
        args["receipt_sha256"] = "0" * 64
    elif change == "source":
        args["source_hashes"]["raw.json"] = "0" * 64
    elif change == "frame":
        args["receipt"]["staged_sha256"] = "0" * 64
    elif change == "observation":
        args["receipt"]["observed_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif change == "future_retrieval":
        args["receipt"]["retrieved_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif change == "unclosed":
        item = args["receipt"]["completed_sessions"]["EVO.ST"]
        item["close_at"] = (NOW + timedelta(days=1)).isoformat()
        item["eligible_at"] = (NOW + timedelta(days=1, minutes=90)).isoformat()
    elif change == "short_lag":
        args["receipt"]["completed_sessions"]["EVO.ST"]["eligible_at"] = S.isoformat() + "T16:59:00Z"
    elif change == "missing_proof":
        del args["receipt"]["completed_sessions"]["EVO.ST"]
    else:
        args["receipt"]["completed_sessions"]["EVO.ST"]["close_at"] = S.isoformat() + "T15:30:00"
    if change != "receipt":
        refresh_receipt(args)
    with pytest.raises(A.AdmissionError):
        A.prepare_admission(cache_path=cache, **args)


def test_dtype_preservation_refuses_lossy_integer_volume_cast(cache):
    before = old_frame()
    before["volume"] = before["volume"].astype("int64")
    before.to_parquet(cache, index=False)
    staged = stage()
    staged["volume"] = 100.5
    with pytest.raises(A.AdmissionError, match="LOSSY_NEW_ROW_CAST"):
        A.prepare_admission(cache_path=cache, **inputs(staged))


def test_integer_volume_above_float_precision_cannot_silently_round(cache):
    staged = stage()
    staged["volume"] = [2**53 + 1]
    with pytest.raises(A.AdmissionError, match="LOSSY_NEW_ROW_CAST"):
        A.prepare_admission(cache_path=cache, **inputs(staged))


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
def test_mixed_exact_integer_and_fraction_refuse_against_original_staged_values(column):
    big = 2**53 + 1
    staged = pd.DataFrame([
        ["AAA", S.isoformat(), 10., 12., 9., 11., 100.],
        ["BBB", S.isoformat(), 1., 3., 1., 2., 100.],
    ], columns=GP.COLUMNS[:7], dtype=object)
    staged[column] = pd.Series([big, 1.5], dtype=object)
    if column in ("open", "close"):
        staged["high"] = pd.Series([big + 1, 3.], dtype=object)
    elif column == "low":
        # Other first-row prices are exactly representable even integers: only
        # the tested low loses its least significant bit in a float64 inference.
        for name in ("open", "close"):
            staged[name] = pd.Series([big + 1, 2.], dtype=object)
        staged["high"] = pd.Series([big + 3, 3.], dtype=object)
    elif column == "high":
        staged["open"] = pd.Series([10., 1.], dtype=object)
        staged["close"] = pd.Series([11., 1.25], dtype=object)
    original = staged.copy(deep=True)
    args = inputs(staged)
    with pytest.raises(A.AdmissionError, match="LOSSY_NEW_ROW_CAST"):
        A.plan_admission(existing=old_frame(), preimage_sha256="d" * 64, **args)
    pd.testing.assert_frame_equal(staged, original, check_exact=True)
    assert staged.loc[0, column] == big


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
def test_exactly_representable_mixed_numeric_batch_is_not_blanket_refused(column):
    exact = 2**53 + 2
    staged = pd.concat([stage("AAA"), stage("BBB")], ignore_index=True).astype(object)
    for name in (GP.COLUMNS[2:6] if column != "volume" else ["volume"]):
        staged[name] = pd.Series([exact, 1.5], dtype=object)
    args = inputs(staged)
    plan = A.plan_admission(existing=old_frame(), preimage_sha256="d" * 64, **args)
    candidate = pd.read_parquet(io.BytesIO(plan._candidate))
    values = candidate.loc[candidate.symbol.isin(["AAA", "BBB"]), column].tolist()
    assert [v.as_integer_ratio() for v in values] == [(exact, 1), (3, 2)]
    assert plan.summary["staged_sha256"] == A.staged_sha256(staged)


def test_float32_price_cast_cannot_silently_round(cache):
    before = old_frame()
    before["open"] = before["open"].astype("float32")
    before.to_parquet(cache, index=False)
    staged = stage()
    staged["open"] = 10.1
    with pytest.raises(A.AdmissionError, match="LOSSY_NEW_ROW_CAST"):
        A.prepare_admission(cache_path=cache, **inputs(staged))


def test_unsorted_or_duplicate_preimage_is_not_repaired(cache):
    old = pd.concat([old_frame(), old_frame()], ignore_index=True)
    old.to_parquet(cache, index=False)
    raw = cache.read_bytes()
    with pytest.raises(A.AdmissionError, match="DUPLICATE_PREIMAGE_KEYS"):
        A.prepare_admission(cache_path=cache, **inputs())
    assert cache.read_bytes() == raw


def test_unsorted_preimage_order_is_not_rewritten(cache):
    frame = pd.concat([old_frame(), old_frame().assign(symbol="AAA")], ignore_index=True)
    frame.to_parquet(cache, index=False)
    raw = cache.read_bytes()
    with pytest.raises(A.AdmissionError, match="UNSORTED_PREIMAGE"):
        A.prepare_admission(cache_path=cache, **inputs())
    assert cache.read_bytes() == raw


@pytest.mark.parametrize("missing", ["legacy_writers_closed", "exclusive_owner_verified", "source_adoption_verified", "ownership_receipt_sha256", "source_adoption_sha256", "admission_plan_sha256"])
def test_publish_requires_owner_source_closure_before_any_file_access(cache, monkeypatch, missing):
    plan = A.prepare_admission(cache_path=cache, **inputs())
    context = closure(plan)
    del context[missing]
    monkeypatch.setattr(Path, "is_file", lambda *_: pytest.fail("owner rejection accessed cache"))
    with pytest.raises(A.AdmissionError, match="VERIFIED_OWNER_SOURCE_CLOSURE_REQUIRED"):
        publish(plan, cache, owner_context=context)


def test_old_process_absence_or_financial_token_is_not_owner_closure(cache):
    plan = A.prepare_admission(cache_path=cache, **inputs())
    context = {**plan.summary["owner"], "no_writer_process_observed": True, "R6_token": "irrelevant"}
    with pytest.raises(A.AdmissionError, match="VERIFIED_OWNER_SOURCE_CLOSURE_REQUIRED"):
        publish(plan, cache, owner_context=context)


def test_changed_preimage_refuses_before_backup_or_audit(cache):
    plan = A.prepare_admission(cache_path=cache, **inputs())
    altered = old_frame()
    altered["close"] = 10.5
    altered.to_parquet(cache, index=False)
    raw = cache.read_bytes()
    with pytest.raises(A.AdmissionError, match="PREIMAGE_CHANGED"):
        publish(plan, cache)
    assert cache.read_bytes() == raw
    assert not (cache.parent / "audit").exists()


def test_corrupt_private_candidate_cannot_publish(cache):
    plan = A.prepare_admission(cache_path=cache, **inputs())
    corrupted = replace(plan, _candidate=plan._candidate + b"bad")
    with pytest.raises(A.AdmissionError, match="PLAN_BINDING_MISMATCH"):
        publish(corrupted, cache)


def test_exclusive_audit_collision_refuses(cache):
    plan = A.prepare_admission(cache_path=cache, **inputs())
    audit = cache.parent / "audit"
    audit.mkdir()
    receipt = audit / "admission_fixture-one.json"
    receipt.write_bytes(b"another owner's evidence")
    raw = cache.read_bytes()
    with pytest.raises(A.AdmissionError, match="EXCLUSIVE_AUDIT_EXISTS"):
        publish(plan, cache)
    assert cache.read_bytes() == raw
    assert receipt.read_bytes() == b"another owner's evidence"
    assert not list(audit.glob("*.before.parquet"))


def test_uncooperative_mid_prepare_race_refuses_and_cleans_owned_candidate(cache, monkeypatch):
    plan = A.prepare_admission(cache_path=cache, **inputs())
    original = cache.read_bytes()
    writer = A._write
    changed = []
    def race(handle, raw):
        writer(handle, raw)
        if raw == plan._candidate and not changed:
            altered = old_frame()
            altered["volume"] = 999.
            altered.to_parquet(cache, index=False)
            changed.append(cache.read_bytes())
    monkeypatch.setattr(A, "_write", race)
    with pytest.raises(A.AdmissionError, match="PREIMAGE_CHANGED"):
        publish(plan, cache)
    assert cache.read_bytes() == changed[0]
    assert (cache.parent / "audit/admission_fixture-one.before.parquet").read_bytes() == original
    assert not list(cache.parent.glob(".price-admission-*.tmp"))
    assert json.loads((cache.parent / "audit/admission_fixture-one.json").read_text())["status"] == "REFUSED"


def test_atomic_replace_failure_keeps_original_and_failure_receipt(cache, monkeypatch):
    plan = A.prepare_admission(cache_path=cache, **inputs())
    original = cache.read_bytes()
    def failure(*_args):
        raise OSError("fixture replace failed")
    monkeypatch.setattr(A.os, "replace", failure)
    with pytest.raises(A.AdmissionError) as error:
        publish(plan, cache)
    assert error.value.published is False
    assert cache.read_bytes() == original
    assert not list(cache.parent.glob(".price-admission-*.tmp"))


def test_publish_failure_after_replace_is_explicit_without_automatic_rollback(cache, monkeypatch):
    plan = A.prepare_admission(cache_path=cache, **inputs())
    def audit_failure(*_args):
        raise OSError("fixture audit disk failure")
    monkeypatch.setattr(A, "_update_audit", audit_failure)
    with pytest.raises(A.AdmissionError, match="PUBLISHED_UNVERIFIED.*AUDIT_FINALIZATION_FAILED") as error:
        publish(plan, cache)
    assert error.value.published is True
    assert digest(cache.read_bytes()) == plan.summary["candidate_sha256"]
    assert not list(cache.parent.glob(".price-admission-*.tmp"))


def test_two_publishers_of_one_preimage_cannot_lose_a_winner(cache):
    first = A.prepare_admission(cache_path=cache, **inputs(operation="one"))
    second = A.prepare_admission(cache_path=cache, **inputs(stage("RHM.DE"), operation="two"))
    barrier = threading.Barrier(2)
    def run(plan):
        barrier.wait(timeout=5)
        try:
            return publish(plan, cache)["status"]
        except A.AdmissionError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, p) for p in (first, second)]
        results = [f.result(timeout=10) for f in futures]
    assert sorted(results) == ["PREIMAGE_CHANGED", "PUBLISHED"]
    assert len(pd.read_parquet(cache)) == 2
    assert len(list((cache.parent / "audit").glob("*.json"))) == 1


def test_ensure_serializes_with_admission_and_does_not_refetch_marked_day(cache):
    plan = A.prepare_admission(cache_path=cache, **inputs())
    entered, done = threading.Event(), threading.Event()
    def ensure():
        entered.set()
        out = GP.ensure(["EVO.ST"], path=cache, start=S - timedelta(days=1), today=NOW.date(),
                        write_receipt=False, downloader=lambda *_: pytest.fail("daily marker was reset"))
        done.set()
        return out
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        with GP.cache_lock(cache):
            future = pool.submit(ensure)
            assert entered.wait(2)
            assert not done.wait(.15)
            # Test native serialization without calling public publish recursively.
            result = A._publish_locked(plan, plan.summary, cache, cache.parent / "audit", closure(plan))
            assert result["status"] == "PUBLISHED"
        out = future.result(timeout=5)
    finally:
        pool.shutdown(wait=True)
    assert out.attrs["receipt"]["n_skipped_pulled_today"] == 1
    assert out.attrs["receipt"]["n_new_rows"] == 0
    assert len(out) == 2


def test_two_ensure_writers_preserve_both_appends_and_both_daily_markers(cache):
    first_in, release, second_started, second_download = (threading.Event() for _ in range(4))
    def first_dl(*_args):
        first_in.set()
        assert release.wait(5)
        return stage("AAA")
    def second_dl(*_args):
        second_download.set()
        return stage("ZZZ")
    def second():
        second_started.set()
        return GP.ensure(["ZZZ"], path=cache, start=S, today=NOW.date(),
                         downloader=second_dl, write_receipt=False)
    pool = ThreadPoolExecutor(max_workers=2)
    try:
        a = pool.submit(GP.ensure, ["AAA"], path=cache, start=S, today=NOW.date(),
                        downloader=first_dl, write_receipt=False)
        assert first_in.wait(2)
        b = pool.submit(second)
        assert second_started.wait(2)
        assert not second_download.wait(.15)
        release.set()
        a.result(timeout=5)
        b.result(timeout=5)
    finally:
        release.set()
        pool.shutdown(wait=True)
    assert set(pd.read_parquet(cache).symbol) == {"EVO.ST", "AAA", "ZZZ"}
    state = json.loads(GP._state_path(cache).read_text())
    assert state["AAA"] == state["ZZZ"] == state["EVO.ST"] == NOW.date().isoformat()


def test_lock_timeout_is_explicit_and_publishes_nothing(cache):
    plan = A.prepare_admission(cache_path=cache, **inputs())
    raw = cache.read_bytes()
    with GP.cache_lock(cache):
        with pytest.raises(A.AdmissionError, match="CACHE_LOCK_TIMEOUT"):
            publish(plan, cache, lock_timeout=.01)
    assert cache.read_bytes() == raw
    assert not (cache.parent / "audit").exists()


def test_owner_closure_and_plan_bind_exact_cache_path(cache):
    plan = A.prepare_admission(cache_path=cache, **inputs())
    other = cache.parent / "other.parquet"
    other.write_bytes(cache.read_bytes())
    with pytest.raises(A.AdmissionError, match="CACHE_OWNER_SCOPE_MISMATCH"):
        A.publish_admission(plan, cache_path=other, audit_dir=cache.parent / "audit",
            expected_preimage_sha256=plan.summary["preimage_sha256"], owner_context=closure(plan))
    assert other.read_bytes() == cache.read_bytes()


def test_old_unrelated_nan_values_and_sorted_subsequence_survive(cache):
    before = old_frame()
    before.loc[0, "high"] = float("nan")  # Admission never repairs legacy history.
    before.to_parquet(cache, index=False)
    plan = A.prepare_admission(cache_path=cache, **inputs(stage("AAA")))
    publish(plan, cache)
    after = pd.read_parquet(cache)
    assert after.symbol.tolist() == ["AAA", "EVO.ST"]
    pd.testing.assert_frame_equal(before, after.iloc[1:].reset_index(drop=True), check_exact=True)
