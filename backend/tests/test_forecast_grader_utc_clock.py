"""The daily grader's default due-date clock is UTC, even on an SGT host."""

from datetime import date, datetime, timezone

import pandas as pd

from backend.services import forecast_grader as FG
from backend.services import ledger_resolver as LR
from backend.services.belief_state import (
    Observable, append, make_prediction, read_predictions,
)


def test_local_oct15_does_not_resolve_utc_oct15_forecast_on_utc_oct14(
        tmp_path, monkeypatch):
    class SingaporeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 15)

    class FrozenUtc(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = cls(2026, 10, 14, 16, 16, tzinfo=timezone.utc)
            return instant if tz is None else instant.astimezone(tz)

    monkeypatch.setattr(FG, "date", SingaporeDate)
    monkeypatch.setattr(FG, "datetime", FrozenUtc)
    monkeypatch.setattr(FG, "bars_source", lambda: {"available": True})
    monkeypatch.setattr(LR, "_load_frozen_csv", lambda: None)

    ledger = tmp_path / "predictions.jsonl"
    record = make_prediction(
        ticker="AAA", specialist="clock_fixture", observable=Observable.RETURN_SIGN,
        horizon_days=5, probability=0.6, thesis="t", counter_thesis="c",
        next_observable="n", model="fixture", model_version="1", prompt="p",
        input_snapshot={"ticker": "AAA"}, made_at="2026-10-05T01:57:49+00:00",
    )
    assert record.resolves_after == "2026-10-15"
    append([record], ledger)
    dates = pd.bdate_range("2026-10-05", periods=6)
    prices = pd.DataFrame({"AAA": [100, 101, 102, 103, 104, 105]}, index=dates)
    fetch = lambda tickers, start, end: prices[tickers]

    early = FG.grade_due(path=ledger, price_fetch=fetch, write=False)
    assert early["date"] == "2026-10-14"
    assert early["newly_resolved"] == 0
    assert read_predictions(ledger)[0]["outcome"] is None

    due = FG.grade_due(path=ledger, today=date(2026, 10, 15),
                       price_fetch=fetch, write=False)
    again = FG.grade_due(path=ledger, today=date(2026, 10, 15),
                         price_fetch=fetch, write=False)
    assert due["newly_resolved"] == 1
    assert read_predictions(ledger)[0]["resolved_at"] == "2026-10-15"
    assert again["newly_resolved"] == 0
