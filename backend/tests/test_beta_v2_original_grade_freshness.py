"""Original247 consumer fixtures: injected clock/calendars, tmp cache, mocked writer."""
import hashlib
import io
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from backend.services import global_prices as GP
from scripts import local_branching as LB
from scripts import local_branching_grade_child as child


# Historical labels only: these fake calendars make no live-session claim.
S = date(2026, 10, 23)
NOW = datetime(2026, 10, 23, 22, tzinfo=timezone.utc)
FIVE = {"EVO.ST", "SAAB-B.ST", "HAG.DE", "RHM.DE", "KOG.OL"}
NAMES = FIVE | {"SPY", "NVDA"}


class Calendar:
    def __init__(self, hour=20, minute=0, holiday=False):
        self.close = pd.Timestamp(S).tz_localize("UTC") + pd.Timedelta(hours=hour, minutes=minute)
        self.holiday = holiday
        self.requests = []

    def sessions_in_range(self, start, end):
        return pd.DatetimeIndex([pd.Timestamp(S)])

    def is_session(self, session):
        self.requests.append(session)
        return session == S.isoformat() and not self.holiday

    def session_close(self, session):
        assert pd.Timestamp(session).date() == S
        return self.close


def frame(names, day=S, price=10.0):
    return pd.DataFrame([{"symbol": s, "date": pd.Timestamp(day), "open": price,
                          "close": price, "volume": 100} for s in sorted(names)])


@pytest.fixture
def consumer(tmp_path, monkeypatch):
    source = tmp_path / "source"
    paths = (source / "prices_2025_26" / "bars.parquet",
             source / "llm_portfolio" / "global_bars.parquet")
    for p in paths:
        p.parent.mkdir(parents=True)
    out = tmp_path / "private"
    daydir = out / LB.FROZEN_COHORT.isoformat()
    daydir.mkdir(parents=True)
    # No native books are read. Only the ID pin is replaced for synthetic books;
    # the production prior_valid_grade and grade_once paths remain exercised.
    books = [{"book_id": f"fixture-{i:03}", "positions": [
        {"ticker": s, "weight": 1 / len(NAMES)} for s in sorted(NAMES)]}
             for i in range(247)]
    ids_hash = hashlib.sha256(json.dumps(sorted(b["book_id"] for b in books),
                                       separators=(",", ":")).encode()).hexdigest()
    monkeypatch.setattr(LB, "FROZEN_IDS_SHA256", ids_hash)
    monkeypatch.setattr(LB, "SOURCE_ROOT", source)
    monkeypatch.setattr(LB, "OUT", out)
    monkeypatch.setattr(LB, "verified_frozen_books", lambda *_: books)
    cached = LB.cached_bars
    monkeypatch.setattr(LB, "cached_bars", lambda names: cached(names, root=source))
    writer = Mock(side_effect=AssertionError("real writer forbidden in fixture"))
    monkeypatch.setattr(LB, "execute", writer)
    for attr in ("ensure", "_yf_download", "resolve"):
        monkeypatch.setattr(GP, attr, Mock(side_effect=AssertionError("fetch forbidden")))
    calendars = {"XNYS": Calendar(), "XSTO": Calendar(15, 30),
                 "XETR": Calendar(15, 30), "XOSL": Calendar(14, 20)}

    def save(us=None, glob=None):
        for p, data in zip(paths, (frame({"SPY", "NVDA"}) if us is None else us,
                                   frame(FIVE) if glob is None else glob)):
            data.to_parquet(p, index=False)
            os.utime(p, (NOW.timestamp(), NOW.timestamp()))

    def run(**kwargs):
        monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"G")))
        return child.run_original(now=kwargs.pop("now", NOW),
                                  calendar_loader=kwargs.pop("calendar_loader", calendars.__getitem__),
                                  listing_calendars=kwargs.pop("listing_calendars", {
                                      "SPY": "XNYS", "NVDA": "XNYS", **child.REVIEWED_FOREIGN_CALENDARS}),
                                  **kwargs)

    def allow_writer():
        writer.side_effect = None
        writer.return_value = {"n_books": 247, "n_twins": 0, "bars_through": S.isoformat(),
                               "benchmark_last_bar": S.isoformat(), "grade_receipt": "mock-only"}

    save()
    yield SimpleNamespace(paths=paths, daydir=daydir, books=books, calendars=calendars,
                          save=save, run=run, writer=writer, allow_writer=allow_writer)
    for attr in ("ensure", "_yf_download", "resolve"):
        getattr(GP, attr).assert_not_called()


def assert_wait(env, result):
    assert result["action"] == "WAIT_CONSTITUENT_MARKS"
    env.writer.assert_not_called()
    assert not list(env.daydir.glob("grade_*.json"))


def test_stale_five_wait_without_writer(consumer):
    consumer.save(glob=frame(FIVE, S - timedelta(days=1)))
    result = consumer.run()
    assert_wait(consumer, result)
    assert set(result["missing_or_duplicate"]) == FIVE
    assert set(result["reasons"]) == FIVE
    assert all(r["freshness"] == "STALE" for r in result["reasons"].values())
    assert result["freshness_diagnostic"]["n_fresh"] == 2
    assert result["completed_session_targets"]["required_sessions"] == dict.fromkeys(sorted(NAMES), S.isoformat())


def test_completed_same_session_dispatches_only_mock_writer_with_provenance(consumer):
    consumer.allow_writer()
    result = consumer.run()
    assert result["action"] == "GRADED"
    args, kwargs = consumer.writer.call_args
    assert args == ("grade", LB.FROZEN_COHORT)
    assert kwargs["expected_session"] == S
    evidence = kwargs["grade_evidence"]
    assert evidence["freshness_diagnostic"]["n_fresh"] == len(NAMES)
    assert evidence["all_constituents_mark_session"] == S.isoformat()
    assert len(evidence["bar_inputs_sha256"]) == 2
    assert evidence["bar_inputs_sha256"] == {
        p.name + ":" + p.parent.name: LB.digest(p) for p in consumer.paths}
    assert evidence["symbol_panel_identity"] == {s: "global_bars" if s in FIVE else "prices_2025_26" for s in NAMES}
    proof = evidence["completed_session_targets"]
    assert proof["observed_at"] == NOW.isoformat()
    assert proof["completion_lag_minutes"] == 90
    assert len(proof["listing_calendars_sha256"]) == 64
    assert proof["symbols"]["EVO.ST"]["calendar"] == "XSTO"
    assert proof["symbols"]["EVO.ST"]["close_at"] == "2026-10-23T15:30:00+00:00"
    assert set(pd.to_datetime(kwargs["bars_override"]["date"]).dt.date) == {S}
    consumer.writer.assert_called_once()
    assert not list(consumer.daydir.glob("grade_*.json"))


@pytest.mark.parametrize("calendar,status", [
    (Calendar(holiday=True), "LOCAL_NON_SESSION"),
    (Calendar(23), "SESSION_UNCLOSED"),
    (Calendar(21), "WAIT_CLOSE_LAG"),
    (None, "CALENDAR_UNAVAILABLE"),
])
def test_local_calendar_refusal_despite_valid_marks(consumer, calendar, status):
    consumer.calendars["XSTO"] = calendar
    result = consumer.run()
    assert_wait(consumer, result)
    for symbol in ("EVO.ST", "SAAB-B.ST"):
        assert result["reasons"][symbol] == {"freshness": "UNKNOWN_REQUIRED_SESSION", "target": status}
        assert result["completed_session_targets"]["required_sessions"][symbol] is None


@pytest.mark.parametrize("seconds,ready", [(-1, False), (0, True), (1, True)])
def test_foreign_close_lag_boundary(consumer, seconds, ready):
    consumer.calendars["XSTO"] = Calendar(20, 30)
    if ready:
        consumer.allow_writer()
    result = consumer.run(now=NOW + timedelta(seconds=seconds))
    assert result["action"] == ("GRADED" if ready else "WAIT_CONSTITUENT_MARKS")
    if not ready:
        consumer.writer.assert_not_called()


@pytest.mark.parametrize("minutes,ready", [(89, False), (90, True)])
def test_original_xnys_session_eligibility_keeps_ninety_minutes(consumer, minutes, ready):
    if ready:
        consumer.allow_writer()
    result = consumer.run(now=datetime(2026, 10, 23, 20, tzinfo=timezone.utc) + timedelta(minutes=minutes))
    assert result["action"] == ("GRADED" if ready else "WAIT_ENTRY")
    if not ready:
        consumer.writer.assert_not_called()


def test_xnys_calendar_unavailable_has_explicit_wait(consumer):
    def unavailable(_):
        raise RuntimeError("fixture offline calendar failure")
    result = consumer.run(calendar_loader=unavailable)
    assert_wait(consumer, result)
    assert result["reason"] == "XNYS_CALENDAR_UNAVAILABLE"


@pytest.mark.parametrize("unknown", ["UNREVIEWED", "OTHER.ST", "2330.TW", "ASML.AS"])
def test_suffix_or_unsuffixed_name_never_invents_identity(consumer, unknown):
    for book in consumer.books:
        book["positions"].append({"ticker": unknown, "weight": 0})
    consumer.save(glob=pd.concat([frame(FIVE), frame({unknown})], ignore_index=True))
    result = consumer.run()
    assert_wait(consumer, result)
    assert result["reasons"][unknown]["target"] == "UNKNOWN_LISTING_IDENTITY"


def test_partial_reviewed_identity_mapping_stays_unknown(consumer):
    result = consumer.run(listing_calendars={"SPY": "XNYS"})
    assert_wait(consumer, result)
    assert result["freshness_diagnostic"]["n_fresh"] == 1
    assert result["freshness_diagnostic"]["n_unknown_target"] == len(NAMES) - 1


@pytest.mark.parametrize("change", ["partial", "different_target", "missing_proof"])
def test_injected_target_adapter_cannot_change_common_session(consumer, change):
    def adapter(*args, **kwargs):
        result = child.completed_session_targets(*args, **kwargs)
        if change == "partial":
            del result["required_sessions"]["EVO.ST"]
        elif change == "different_target":
            result["required_sessions"]["EVO.ST"] = (S - timedelta(days=1)).isoformat()
        else:
            del result["symbols"]["EVO.ST"]
        return result
    result = consumer.run(target_adapter=adapter)
    assert_wait(consumer, result)
    assert result["freshness_diagnostic"]["n_unknown_target"] == 1
    if change == "different_target":
        assert result["reasons"]["EVO.ST"]["target"] == "DIFFERENT_COMMON_SESSION"


@pytest.mark.parametrize("mutation,expected", [
    ("missing", "MISSING_HISTORY"), ("duplicate", "DUPLICATE_TARGET_ROWS"),
    ("nan", "INVALID_TARGET_MARK"), ("inf", "INVALID_TARGET_MARK"),
    ("zero", "INVALID_TARGET_MARK"), ("negative", "INVALID_TARGET_MARK"),
    ("bool", "INVALID_TARGET_MARK"),
])
@pytest.mark.parametrize("column", ["open", "close"])
def test_invalid_exact_target_refuses(consumer, monkeypatch, mutation, expected, column):
    # In-memory union fixture preserves bool types that parquet would coerce.
    bars = pd.concat([frame(NAMES)], ignore_index=True)
    if mutation == "missing":
        bars = bars[bars.symbol != "EVO.ST"]
    elif mutation == "duplicate":
        bars = pd.concat([bars, frame({"EVO.ST"})], ignore_index=True)
    else:
        values = {"nan": float("nan"), "inf": float("inf"), "zero": 0.0,
                  "negative": -1.0, "bool": True}
        bars[column] = bars[column].astype(object)
        bars.loc[bars.symbol == "EVO.ST", column] = values[mutation]
    original = bars.copy(deep=True)
    monkeypatch.setattr(LB, "cached_bars", lambda _: bars)
    result = consumer.run()
    assert_wait(consumer, result)
    assert result["reasons"]["EVO.ST"]["freshness"] == expected
    pd.testing.assert_frame_equal(bars, original)


@pytest.mark.parametrize("column", ["symbol", "date", "open", "close"])
def test_absent_price_columns_wait(consumer, monkeypatch, column):
    monkeypatch.setattr(LB, "cached_bars", lambda _: frame(NAMES).drop(columns=column))
    result = consumer.run()
    assert_wait(consumer, result)
    assert result["reason"] == "INVALID_PRICE_SNAPSHOT"
    assert result["detail"] == "PRICE_DIAGNOSTIC_COLUMNS_REQUIRED"


@pytest.mark.parametrize("bad_date", [None, "not-a-date"])
def test_invalid_cached_date_is_not_silently_dropped(consumer, monkeypatch, bad_date):
    bars = frame(NAMES)
    bars["date"] = bars["date"].astype(object)
    bars.loc[0, "date"] = bad_date
    monkeypatch.setattr(LB, "cached_bars", lambda _: bars)
    result = consumer.run()
    assert_wait(consumer, result)
    assert result["reason"] == "INVALID_PRICE_SNAPSHOT"


def test_all_stale_snapshot_reports_stale_instead_of_raising(consumer):
    consumer.save(us=frame({"SPY", "NVDA"}, S - timedelta(days=1)),
                  glob=frame(FIVE, S - timedelta(days=1)))
    result = consumer.run()
    assert_wait(consumer, result)
    assert result["freshness_diagnostic"]["n_fresh"] == 0
    assert all(r["freshness"] == "STALE" for r in result["reasons"].values())


def test_newer_rows_bounded_before_diagnostic_and_mock_writer(consumer, monkeypatch):
    newer = S + timedelta(days=1)
    consumer.save(glob=pd.concat([frame(FIVE), frame(FIVE, newer, 99.0)]))
    diagnostic = Mock(wraps=GP.freshness_diagnostic)
    monkeypatch.setattr(GP, "freshness_diagnostic", diagnostic)
    consumer.allow_writer()
    result = consumer.run()
    assert result["action"] == "GRADED"
    passed = diagnostic.call_args.args[0]
    assert set(pd.to_datetime(passed.date).dt.date) == {S}
    written = consumer.writer.call_args.kwargs["bars_override"]
    pd.testing.assert_frame_equal(passed, written)
    assert all(row["latest_date"] == S.isoformat() for row in result["grade_evidence"]["freshness_diagnostic"]["symbols"])


def test_newer_series_wins_shared_union_even_when_it_lacks_s(consumer):
    # A valid US row cannot fill the global winner's gap at S.
    consumer.save(us=pd.concat([frame({"SPY", "NVDA"}), frame({"EVO.ST"})]),
                  glob=pd.concat([frame(FIVE - {"EVO.ST"}), frame({"EVO.ST"}, S + timedelta(days=1))]))
    result = consumer.run()
    assert_wait(consumer, result)
    assert result["reasons"]["EVO.ST"]["freshness"] == "MISSING_HISTORY"


def test_shared_union_tie_keeps_us_whole_series_identity(consumer):
    consumer.save(us=pd.concat([frame({"SPY", "NVDA"}), frame({"EVO.ST"}, price=25)]))
    consumer.allow_writer()
    result = consumer.run()
    assert result["grade_evidence"]["symbol_panel_identity"]["EVO.ST"] == "prices_2025_26"
    snapshot = consumer.writer.call_args.kwargs["bars_override"]
    assert snapshot.loc[snapshot.symbol == "EVO.ST", "close"].tolist() == [25.0]


def test_source_mutation_while_read_refuses_mock_writer(consumer, monkeypatch):
    cached = LB.cached_bars
    def mutate(names):
        bars = cached(names)
        p = consumer.paths[1]
        os.utime(p, ns=(p.stat().st_atime_ns, p.stat().st_mtime_ns + 1_000_000))
        return bars
    monkeypatch.setattr(LB, "cached_bars", mutate)
    result = consumer.run()
    assert result["action"] == "WAIT_SHARED_REFRESH"
    assert "changed while read" in result["reason"]
    consumer.writer.assert_not_called()


def test_source_bytes_mutation_during_hashing_refuses(consumer, monkeypatch):
    digest = LB.digest
    original = consumer.paths[0].read_bytes()
    def mutate(path):
        result = digest(path)
        if path == consumer.paths[0]:
            path.write_bytes(original + b"fixture mutation after read")
        return result
    monkeypatch.setattr(LB, "digest", mutate)
    result = consumer.run()
    assert result["action"] == "WAIT_SHARED_REFRESH"
    assert consumer.paths[0].read_bytes() != original
    consumer.writer.assert_not_called()


def test_panel_identity_mismatch_still_refuses(consumer, monkeypatch):
    # Keep S present so freshness can pass, but lie about the selected series.
    bars = pd.concat([frame(NAMES), frame(NAMES, S + timedelta(days=1))])
    monkeypatch.setattr(LB, "cached_bars", lambda _: bars)
    with pytest.raises(ValueError, match="shared union changed source identity"):
        consumer.run()
    consumer.writer.assert_not_called()


def saved_receipt(env):
    panels = {s: "global_bars" if s in FIVE else "prices_2025_26" for s in NAMES}
    return {"grade_day": S.isoformat(), "licence": "PRODUCT_EXPERIMENT",
            "source_ledger_sha256": LB.FROZEN_LEDGER_SHA256,
            "freeze_receipt_sha256": LB.FROZEN_RECEIPT_SHA256,
            "bars_through": S.isoformat(), "benchmark_last_bar": S.isoformat(),
            "n_books": 247, "n_twins": 0, "books": [{"book_id": b["book_id"]} for b in env.books],
            "grade_evidence": {"all_constituents_mark_session": S.isoformat(),
                               "n_constituents_including_spy": len(NAMES),
                               "symbol_panel_identity": panels,
                               "bar_inputs_sha256": {"us": "a" * 64, "global": "b" * 64}}}


def test_existing_same_session_receipt_is_reused_without_retrofit(consumer, monkeypatch):
    receipt = consumer.daydir / "grade_fixture.json"
    receipt.write_text(json.dumps(saved_receipt(consumer)), encoding="utf-8")
    original = receipt.read_bytes()
    for p in consumer.paths:
        p.unlink()
    monkeypatch.setattr(LB, "cached_bars", Mock(side_effect=AssertionError("must reuse receipt first")))
    result = consumer.run()
    assert result["action"] == "ALREADY_GRADED"
    assert result["grade_receipt"] == str(receipt)
    assert receipt.read_bytes() == original
    consumer.writer.assert_not_called()
    LB.cached_bars.assert_not_called()


@pytest.mark.parametrize("change", ["dropped", "duplicate", "wrong"])
def test_existing_receipt_requires_exact_frozen_ids(consumer, change):
    row = saved_receipt(consumer)
    if change == "dropped":
        row["books"].pop()
    else:
        row["books"][-1]["book_id"] = row["books"][0]["book_id"] if change == "duplicate" else "foreign-id"
    (consumer.daydir / "grade_fixture.json").write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match="fails frozen proof"):
        consumer.run()
    consumer.writer.assert_not_called()


@pytest.mark.parametrize("change", ["dropped", "duplicate", "wrong"])
def test_frozen_cohort_ids_cannot_drift_before_freshness(consumer, change):
    if change == "dropped":
        consumer.books.pop()
    else:
        consumer.books[-1]["book_id"] = consumer.books[0]["book_id"] if change == "duplicate" else "foreign-id"
    with pytest.raises(ValueError, match="frozen books differ"):
        consumer.run()
    consumer.writer.assert_not_called()


def test_default_stdin_g_gate_is_preserved(monkeypatch):
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"X")))
    with pytest.raises(ValueError, match="owned parent did not authorize"):
        child.run_original()


def test_default_reviewed_identity_policy_is_exact():
    requested = {"SPY", "NVDA", "ASML", "UNREVIEWED", "OTHER.ST", "2330.TW"} | FIVE
    calls = []
    def load(mic):
        calls.append(mic)
        return Calendar(15)
    proof = child.completed_session_targets(requested, S, NOW + timedelta(days=2), calendar_loader=load)
    assert proof["required_sessions"]["SPY"] == S.isoformat()
    assert proof["symbols"]["SPY"]["calendar"] == "XNYS"
    assert {s: proof["symbols"][s]["calendar"] for s in FIVE} == {
        "EVO.ST": "XSTO", "SAAB-B.ST": "XSTO", "HAG.DE": "XETR", "RHM.DE": "XETR", "KOG.OL": "XOSL"}
    for symbol in ("UNREVIEWED", "OTHER.ST"):
        assert proof["required_sessions"][symbol] is None
    for symbol in ("2330.TW", "ASML", "NVDA"):
        assert proof["required_sessions"][symbol] == S.isoformat()
    assert set(calls) == {"XASX", "XETR", "XKRX", "XNYS", "XOSL", "XSTO", "XTAI", "XTKS"}


def test_default_consumer_requires_complete_frozen_identity_binding(consumer):
    result = consumer.run(listing_calendars=None)
    assert_wait(consumer, result)
    assert result["reason"] == "FROZEN_IDENTITY_SET_MISMATCH"


@pytest.mark.parametrize("field,value", [
    ("calendar", None), ("close_at", None), ("eligible_at", None),
    ("listing_identity", "OTHER.ST"), ("common_session", "2026-10-22"),
    ("eligible_at", "2026-10-24T23:00:00+00:00"),
    ("symbol", "SAAB-B.ST"), ("calendar", "XETR"),
    ("close_at", "2026-10-23T15:30:00"),
    ("eligible_at", "2026-10-23T17:00:00"),
    ("close_at", "NaT"), ("eligible_at", "not-a-timestamp"),
    ("eligible_at", "2026-10-23T16:59:00+00:00"),
    ("eligible_at", "2026-10-23T17:01:00+00:00"),
])
def test_r1_symbol_proof_must_match_consumer_identity_calendar_and_times(consumer, field, value):
    def adapter(*args, **kwargs):
        proof = child.completed_session_targets(*args, **kwargs)
        row = proof["symbols"]["EVO.ST"]
        if value is None:
            row.pop(field)
        else:
            row[field] = value
        return proof
    consumer.allow_writer()  # Refusal must block an otherwise dispatchable mock.
    result = consumer.run(target_adapter=adapter)
    assert_wait(consumer, result)
    assert result["completion_proof_validation"]["status"] == "INVALID"
    assert set(result["completion_proof_validation"]["errors"]) == {"EVO.ST"}
    assert result["freshness_diagnostic"]["n_unknown_target"] == 1
    assert "proof_validation" in result["reasons"]["EVO.ST"]


@pytest.mark.parametrize("field,value", [
    ("observed_at", "2026-10-24T23:00:00+00:00"),
    ("observed_at", "2026-10-23T21:59:59+00:00"),
    ("observed_at", "2026-10-23T22:00:00"), ("observed_at", "NaT"),
    ("observed_at", None), ("common_session", "2026-10-22"),
    ("policy", "some-other-policy"), ("listing_calendars_sha256", "a" * 64),
    ("identity_authority", "adapter says all names are reviewed"),
    ("completion_lag_minutes", 89), ("completion_lag_minutes", 91),
    ("completion_lag_minutes", 90.0), ("completion_lag_minutes", True),
])
def test_r1_header_provenance_must_match_consumer_clock_and_mapping(consumer, field, value):
    def adapter(*args, **kwargs):
        proof = child.completed_session_targets(*args, **kwargs)
        if value is None:
            proof.pop(field)
        else:
            proof[field] = value
        return proof
    consumer.allow_writer()
    result = consumer.run(target_adapter=adapter)
    assert_wait(consumer, result)
    assert set(result["completion_proof_validation"]["errors"]) == NAMES
    assert result["freshness_diagnostic"]["n_unknown_target"] == len(NAMES)


def test_r1_self_consistent_ninety_minute_pair_cannot_invent_calendar_close(consumer):
    def adapter(*args, **kwargs):
        proof = child.completed_session_targets(*args, **kwargs)
        row = proof["symbols"]["EVO.ST"]
        # Completed and exactly 90 minutes apart, but not XSTO's injected S close.
        row["close_at"] = "2026-10-23T14:30:00+00:00"
        row["eligible_at"] = "2026-10-23T16:00:00+00:00"
        return proof
    consumer.allow_writer()
    result = consumer.run(target_adapter=adapter)
    assert_wait(consumer, result)
    assert result["completion_proof_validation"]["errors"]["EVO.ST"] == "TARGET_TIME_MISMATCH:close_at"


def test_r1_equivalent_aware_offsets_preserve_success(consumer):
    def adapter(*args, **kwargs):
        proof = child.completed_session_targets(*args, **kwargs)
        proof["observed_at"] = "2026-10-24T06:00:00+08:00"
        row = proof["symbols"]["EVO.ST"]
        row["close_at"] = "2026-10-23T17:30:00+02:00"
        row["eligible_at"] = "2026-10-23T19:00:00+02:00"
        return proof
    consumer.allow_writer()
    result = consumer.run(target_adapter=adapter)
    assert result["action"] == "GRADED"
    assert result["grade_evidence"]["completion_proof_validation"] == {"status": "VALID", "errors": {}}
    consumer.writer.assert_called_once()


def test_r1_adapter_cannot_promote_unreviewed_default_identity(consumer):
    # The expanded manifest admits NVDA; an unregistered exact key still cannot
    # be promoted by an adapter label or by copying another instrument's proof.
    names = NAMES | {"UNREVIEWED"}
    now = NOW + timedelta(days=2)
    reference = child.completed_session_targets(names, S, now, calendar_loader=consumer.calendars.__getitem__)
    import copy
    proof = copy.deepcopy(reference)
    proof["symbols"]["UNREVIEWED"] = dict(proof["symbols"]["SPY"], symbol="UNREVIEWED", listing_identity="UNREVIEWED")
    proof["required_sessions"]["UNREVIEWED"] = S.isoformat()
    targets, errors = child.validate_completion_proofs(proof, reference, names, S, now)
    assert targets["UNREVIEWED"] is None
    assert "UNREVIEWED" in errors
    consumer.writer.assert_not_called()


@pytest.mark.parametrize("shape", ["not_object", "bad_targets", "bad_proofs", "bad_symbol_proof", "extra_symbol"])
def test_r1_malformed_proof_shapes_refuse_before_writer(consumer, shape):
    def adapter(*args, **kwargs):
        proof = child.completed_session_targets(*args, **kwargs)
        if shape == "not_object":
            return []
        if shape == "bad_targets":
            proof["required_sessions"] = []
        elif shape == "bad_proofs":
            proof["symbols"] = None
        elif shape == "bad_symbol_proof":
            proof["symbols"]["EVO.ST"] = "COMPLETED_COMMON_SESSION"
        else:
            proof["symbols"]["UNREQUESTED"] = dict(proof["symbols"]["SPY"])
            proof["required_sessions"]["UNREQUESTED"] = S.isoformat()
        return proof
    consumer.allow_writer()
    result = consumer.run(target_adapter=adapter)
    assert_wait(consumer, result)
    assert result["completion_proof_validation"]["status"] == "INVALID"


def test_r1_reviewed_mapping_input_is_snapshotted_before_adapter(consumer):
    def adapter(*args, **kwargs):
        kwargs["listing_calendars"]["EVO.ST"] = "XETR"
        return child.completed_session_targets(*args, **kwargs)
    consumer.allow_writer()
    result = consumer.run(target_adapter=adapter)
    assert_wait(consumer, result)
    assert result["completion_proof_validation"]["status"] == "INVALID"
