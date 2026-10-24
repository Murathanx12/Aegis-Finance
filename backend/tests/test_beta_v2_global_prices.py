"""Offline exact-session diagnostics; fixture cache writes only under tmp_path."""
from datetime import date, timedelta

import pandas as pd
import pytest

from backend.services import global_prices as GP


def bars(symbol: str, day: date, price: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame({"symbol": [symbol], "date": pd.to_datetime([day]),
                         "open": [price], "high": [price], "low": [price],
                         "close": [price], "volume": [1000]})


def target() -> date:
    # Explicit historical fixture label; no assertion that today is a session.
    return date.today() - timedelta(days=3)


def test_historical_presence_is_not_freshness(tmp_path):
    day = target()
    result = GP.ensure(["EVO.ST"], start=day - timedelta(days=30), path=tmp_path / "g.parquet",
                       today=day + timedelta(days=1), required_session=day,
                       downloader=lambda *_: bars("EVO.ST", day - timedelta(days=1)))
    receipt = result.attrs["receipt"]
    assert receipt["n_ok"] == 1 and receipt["n_failed"] == 0
    assert receipt["freshness"]["n_fresh"] == 0
    assert receipt["freshness"]["symbols"][0]["status"] == "STALE"


def test_unspecified_target_is_unknown_even_when_new_rows_arrive(tmp_path):
    day = target()
    result = GP.ensure(["A.ST"], start=day, path=tmp_path / "g.parquet", today=day + timedelta(days=1),
                       downloader=lambda *_: bars("A.ST", day))
    assert result.attrs["receipt"]["freshness"]["status"] == "NOT_EVALUATED"
    assert result.attrs["receipt"]["freshness"]["n_fresh"] is None


def test_same_day_skip_cannot_hide_stale_target(tmp_path):
    day = target()
    calls = []

    def download(*args):
        calls.append(args)
        return bars("A.ST", day - timedelta(days=1))

    kwargs = dict(start=day - timedelta(days=10), today=day + timedelta(days=1),
                  path=tmp_path / "g.parquet", downloader=download, required_session=day)
    GP.ensure(["A.ST"], **kwargs)
    result = GP.ensure(["A.ST"], **kwargs)
    receipt = result.attrs["receipt"]
    assert len(calls) == 1 and receipt["n_skipped_pulled_today"] == 1
    assert receipt["freshness"]["n_fresh"] == 0
    assert receipt["freshness"]["n_latest_advanced"] == 0


def test_actual_advancement_and_exact_target_are_separate():
    day = target()
    before = bars("A.ST", day - timedelta(days=2))
    after = pd.concat([before, bars("A.ST", day - timedelta(days=1))])
    result = GP.freshness_diagnostic(after, ["A.ST"], required_session=day, previous_bars=before)
    assert result["n_latest_advanced"] == 1 and result["n_fresh"] == 0
    assert result["symbols"][0]["new_session_dates"] == 1


def test_market_specific_completed_targets_allow_different_holidays():
    day = target()
    frame = pd.concat([bars("A.ST", day), bars("B.DE", day - timedelta(days=1))])
    result = GP.freshness_diagnostic(frame, ["A.ST", "B.DE"],
                                    required_session={"A.ST": day, "B.DE": day - timedelta(days=1)})
    assert result["n_fresh"] == 2 and result["status"] == "COMPLETE_TARGET_COVERAGE"


def test_unmapped_market_target_is_unknown():
    day = target()
    frame = pd.concat([bars("A.ST", day), bars("B.DE", day)])
    result = GP.freshness_diagnostic(frame, ["A.ST", "B.DE"], required_session={"A.ST": day})
    assert result["n_fresh"] == 1 and result["n_unknown_target"] == 1
    assert result["status"] != "COMPLETE_TARGET_COVERAGE"


def test_future_rows_cannot_replace_missing_exact_target():
    day = target()
    result = GP.freshness_diagnostic(bars("A.ST", day + timedelta(days=1)), ["A.ST"], required_session=day)
    assert result["symbols"][0]["status"] == "MISSING_EXACT_TARGET"


def test_duplicate_target_rows_are_not_fresh():
    frame = pd.concat([bars("A.ST", target()), bars("A.ST", target())])
    result = GP.freshness_diagnostic(frame, ["A.ST"], required_session=target())
    assert result["symbols"][0]["status"] == "DUPLICATE_TARGET_ROWS"


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf"), True, "bad"])
def test_failed_target_mark_is_not_filled_or_zero_substituted(value):
    frame = bars("A.ST", target())
    frame["close"] = value
    original = frame.copy(deep=True)
    result = GP.freshness_diagnostic(frame, ["A.ST"], required_session=target())
    assert result["symbols"][0]["status"] == "INVALID_TARGET_MARK"
    pd.testing.assert_frame_equal(frame, original)


def test_missing_history_is_distinct_from_stale():
    result = GP.freshness_diagnostic(pd.DataFrame(), ["A.ST"], required_session=target())
    assert result["symbols"][0]["status"] == "MISSING_HISTORY"
    assert result["symbols"][0]["latest_date"] is None


def test_no_previous_snapshot_means_progress_unknown():
    result = GP.freshness_diagnostic(bars("A.ST", target()), ["A.ST"], required_session=target())
    assert result["n_latest_advanced"] is None


def test_diagnostic_and_ensure_preserve_historical_cache_rows(tmp_path):
    day = target()
    path = tmp_path / "g.parquet"
    first = GP.ensure(["A.ST"], start=day - timedelta(days=10), path=path, today=day,
                      downloader=lambda *_: bars("A.ST", day - timedelta(days=1), 10.0))
    original = first.copy(deep=True)
    second = GP.ensure(["A.ST"], start=day - timedelta(days=10), path=path, today=day + timedelta(days=1),
                       required_session=day, downloader=lambda *_: pd.concat([
                           bars("A.ST", day - timedelta(days=1), 99.0), bars("A.ST", day, 11.0)]))
    old = second[second["date"] < pd.Timestamp(day)].reset_index(drop=True)
    pd.testing.assert_frame_equal(old, original)
    assert second.attrs["receipt"]["freshness"]["n_fresh"] == 1


def test_failed_download_preserves_history_but_does_not_claim_fresh(tmp_path):
    day = target()
    path = tmp_path / "g.parquet"
    GP.ensure(["A.ST"], start=day - timedelta(days=10), path=path, today=day,
              downloader=lambda *_: bars("A.ST", day - timedelta(days=1)))

    def failure(*_args):
        raise RuntimeError("offline fixture failure")

    result = GP.ensure(["A.ST"], start=day - timedelta(days=10), path=path, today=day + timedelta(days=1),
                       required_session=day, downloader=failure)
    assert result.attrs["receipt"]["n_ok"] == 1
    assert result.attrs["receipt"]["freshness"]["n_fresh"] == 0
    assert result.attrs["receipt"]["errors"]


@pytest.mark.parametrize("target_value", ["not-a-date", "2026-10-23T00:00:00Z", {"OTHER": "2026-10-23"}])
def test_invalid_target_refuses_before_any_download(target_value, tmp_path):
    def forbidden(*_args):
        raise AssertionError("download must not run")

    with pytest.raises(ValueError):
        GP.ensure(["A.ST"], start=target(), path=tmp_path / "g.parquet", downloader=forbidden,
                  required_session=target_value)
    assert not list(tmp_path.iterdir())


def _golden_symbol(symbol, *, rows=0, latest=None, required=None, target_rows=None,
                   status="UNKNOWN_REQUIRED_SESSION", before=None, advanced=None, new_dates=None):
    """Explicit full-receipt oracle; no grouping/date-selection implementation."""
    return {"symbol": symbol, "historical_rows": rows, "latest_date": latest,
            "required_session": required, "target_rows": target_rows, "status": status,
            "latest_before": before, "latest_advanced": advanced, "new_session_dates": new_dates}


def _golden_receipt(rows, *, status, fresh=None, not_fresh=None, unknown=0,
                    progress=False, advanced=None):
    return {"schema": "global_prices_freshness/1", "status": status,
            "target_authority": "CALLER_SUPPLIED_COMPLETED_SESSION; NO_CALENDAR_INFERRED",
            "n_requested": len(rows), "n_fresh": fresh, "n_not_fresh": not_fresh,
            "n_unknown_target": unknown, "progress_evaluated": progress,
            "n_latest_advanced": advanced, "symbols": rows}


@pytest.fixture
def gp1_interleaved_frames():
    # Fixed past labels, not assumptions about a live exchange calendar.
    # Nonunique, nonmonotonic index labels make positional selection material.
    after = pd.DataFrame({"symbol": ["A.ST", "b.de", "A.ST", "UNREQUESTED", "b.de"],
                          "date": ["2026-10-01", "2026-10-01", "2026-10-03", "2026-10-03", "2026-10-02"],
                          "open": [10., 20., 12., 200., 21.], "close": [10., 20., 12., 200., 21.]},
                         index=[17, 17, -1, 8, 8])
    before = after.iloc[[0, 1]].copy()
    want = ["b.de", "A.ST", "A.ST", "CASH", "missing", " "]
    return after, before, want


@pytest.mark.parametrize("schema", ["full", "symbol_date_close_only"])
def test_gp1_default_progress_full_receipt_equivalence(gp1_interleaved_frames, schema):
    after, before, want = gp1_interleaved_frames
    if schema == "symbol_date_close_only":
        after, before = after.drop(columns="open"), before.drop(columns="open")
    saved_after, saved_before = after.copy(deep=True), before.copy(deep=True)
    expected = _golden_receipt([
        _golden_symbol("A.ST", rows=2, latest="2026-10-03", before="2026-10-01", advanced=True, new_dates=1),
        _golden_symbol("B.DE", rows=2, latest="2026-10-02", before="2026-10-01", advanced=True, new_dates=1),
        _golden_symbol("MISSING", advanced=False, new_dates=0)],
        status="NOT_EVALUATED", unknown=3, progress=True, advanced=2)
    assert GP.freshness_diagnostic(after, want, previous_bars=before) == expected
    pd.testing.assert_frame_equal(after, saved_after)
    pd.testing.assert_frame_equal(before, saved_before)


@pytest.mark.parametrize("variant", ["explicit", "partial", "duplicate", "invalid_date", "invalid_mark"])
def test_gp1_exact_target_and_partial_mapping_full_receipt_equivalence(gp1_interleaved_frames, variant):
    after, before, want = gp1_interleaved_frames
    required = {"A.ST": "2026-10-03"} if variant == "partial" else "2026-10-03"
    a_status, a_rows, a_targets = "FRESH_AT_REQUIRED_SESSION", 2, 1
    if variant == "duplicate":
        after = pd.concat([after, after.iloc[[2]]])
        a_status, a_rows, a_targets = "DUPLICATE_TARGET_ROWS", 3, 2
    elif variant == "invalid_date":
        after = after.copy()
        after.iloc[0, after.columns.get_loc("date")] = "invalid_cached_date"
        a_status = "INVALID_CACHED_DATES"
    elif variant == "invalid_mark":
        after = after.copy()
        after.iloc[2, after.columns.get_loc("close")] = 0.0
        a_status = "INVALID_TARGET_MARK"
    partial = variant == "partial"
    expected = _golden_receipt([
        _golden_symbol("A.ST", rows=a_rows, latest="2026-10-03", required="2026-10-03", target_rows=a_targets,
                       status=a_status, before="2026-10-01", advanced=True, new_dates=1),
        _golden_symbol("B.DE", rows=2, latest="2026-10-02", required=None if partial else "2026-10-03",
                       target_rows=None if partial else 0, status="UNKNOWN_REQUIRED_SESSION" if partial else "STALE",
                       before="2026-10-01", advanced=True, new_dates=1),
        _golden_symbol("MISSING", required=None if partial else "2026-10-03", target_rows=None if partial else 0,
                       status="UNKNOWN_REQUIRED_SESSION" if partial else "MISSING_HISTORY", advanced=False, new_dates=0)],
        status="INCOMPLETE_OR_UNKNOWN_TARGET_COVERAGE", fresh=1 if variant in ("explicit", "partial") else 0,
        not_fresh=0 if partial else 2 if variant == "explicit" else 3,
        unknown=2 if partial else 0, progress=True, advanced=2)
    saved_after, saved_before = after.copy(deep=True), before.copy(deep=True)
    assert GP.freshness_diagnostic(after, want, required_session=required, previous_bars=before) == expected
    pd.testing.assert_frame_equal(after, saved_after)
    pd.testing.assert_frame_equal(before, saved_before)


def test_gp1_no_previous_snapshot_preserves_unknown_progress(gp1_interleaved_frames):
    after, before, want = gp1_interleaved_frames
    expected = _golden_receipt([
        _golden_symbol("A.ST", rows=2, latest="2026-10-03"),
        _golden_symbol("B.DE", rows=2, latest="2026-10-02"), _golden_symbol("MISSING")],
        status="NOT_EVALUATED", unknown=3)
    assert GP.freshness_diagnostic(after, want) == expected


@pytest.mark.parametrize("required", [None, "2026-10-03"])
def test_gp1_empty_frame_and_missing_symbols_full_receipt(required):
    explicit = required is not None
    expected = _golden_receipt([
        _golden_symbol("MISSING", required=required, target_rows=0 if explicit else None,
                       status="MISSING_HISTORY" if explicit else "UNKNOWN_REQUIRED_SESSION", advanced=False, new_dates=0)],
        status="INCOMPLETE_OR_UNKNOWN_TARGET_COVERAGE" if explicit else "NOT_EVALUATED",
        fresh=0 if explicit else None, not_fresh=1 if explicit else None,
        unknown=0 if explicit else 1, progress=True, advanced=0)
    assert GP.freshness_diagnostic(pd.DataFrame(), ["missing"], required_session=required,
                                   previous_bars=pd.DataFrame()) == expected


def test_gp1_unchanged_dates_and_duplicate_prior_rows_do_not_invent_progress():
    frame = pd.DataFrame({"symbol": ["A.ST", "A.ST"], "date": ["2026-10-01", "2026-10-01"], "close": [10., 10.]})
    expected = _golden_receipt([
        _golden_symbol("A.ST", rows=2, latest="2026-10-01", before="2026-10-01", advanced=False, new_dates=0)],
        status="NOT_EVALUATED", unknown=1, progress=True, advanced=0)
    assert GP.freshness_diagnostic(frame, ["A.ST"], previous_bars=frame.copy()) == expected


def test_gp1_groups_each_normalized_frame_once_without_per_ticker_symbol_scans(monkeypatch):
    symbols = [f"S{i:03}.ST" for i in range(24)]
    frame = pd.DataFrame({"symbol": [s for s in symbols for _ in range(4)],
                          "date": list(pd.date_range("2026-01-01", periods=4)) * 24,
                          "close": 100.})
    grouped, scans = [], []
    original_groupby, original_eq = pd.DataFrame.groupby, pd.Series.__eq__

    def groupby(value, *args, **kwargs):
        if (args and args[0] == "symbol") or kwargs.get("by") == "symbol":
            grouped.append(len(value))
        return original_groupby(value, *args, **kwargs)

    def equal(value, other):
        if value.name == "symbol" and isinstance(other, str) and other in symbols:
            scans.append(len(value))
        return original_eq(value, other)

    monkeypatch.setattr(pd.DataFrame, "groupby", groupby)
    monkeypatch.setattr(pd.Series, "__eq__", equal)
    result = GP.freshness_diagnostic(frame, symbols, previous_bars=frame)
    assert result["n_requested"] == 24 and result["n_latest_advanced"] == 0
    assert grouped == [96, 96]
    assert scans == []  # structural scaling assertion; never a timing threshold
