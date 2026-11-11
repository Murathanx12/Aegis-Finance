"""CH-05 rescue R3: the five frozen European constituents' daily marks.

Ported from the runtime checkout, where `scripts.pull_bars_refresh` has called
`frozen_constituent_prices.refresh_required_marks` since 2026-11-01. Offline:
calendars and the vendor are injected fakes, every path is under `tmp_path`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from backend.services import frozen_constituent_prices as FC
from backend.services import global_prices as GP

SESSION = date(2026, 10, 16)                      # a Friday after FROZEN_DATE
OBSERVED = datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc)
_TZ = {"XNYS": "America/New_York", "XSTO": "Europe/Stockholm",
       "XETR": "Europe/Berlin", "XOSL": "Europe/Oslo"}


class FakeCalendar:
    """Weekdays are sessions, minus declared holidays; fixed UTC closes."""

    def __init__(self, mic: str, holidays: tuple[str, ...] = ()):
        self.mic, self.tz, self.holidays = mic, _TZ[mic], set(holidays)

    def is_session(self, day: str) -> bool:
        d = date.fromisoformat(str(day)[:10])
        return d.weekday() < 5 and d.isoformat() not in self.holidays

    def session_close(self, day: str) -> pd.Timestamp:
        hour = 20 if self.mic == "XNYS" else 15
        return pd.Timestamp(f"{str(day)[:10]}T{hour:02d}:30:00+00:00")

    def sessions_in_range(self, lo: str, hi: str) -> pd.DatetimeIndex:
        days = pd.date_range(lo, hi, freq="D")
        return pd.DatetimeIndex([d for d in days if self.is_session(d.date().isoformat())])


def _loader(holidays: dict[str, tuple[str, ...]] | None = None):
    holidays = holidays or {}
    return lambda mic: FakeCalendar(mic, holidays.get(mic, ()))


def _vendor(skip: set[str] | None = None, calls: list | None = None):
    skip = skip or set()

    def download(tickers, start, end):
        (symbol,) = tickers
        if calls is not None:
            calls.append(symbol)
        rows = []
        d = pd.Timestamp(start).date()
        while d < pd.Timestamp(end).date():
            if d.weekday() < 5 and (symbol, d.isoformat()) not in skip:
                rows.append([symbol, pd.Timestamp(d), 10.0, 11.0, 9.0, 10.5, 1000.0])
            d += timedelta(days=1)
        return pd.DataFrame(rows, columns=GP.COLUMNS[:7])
    return download


def test_completed_plan_waits_for_every_listing_close():
    with pytest.raises(ValueError, match="WAIT_SESSION_COMPLETION"):
        FC.completed_plan(SESSION, datetime(2026, 10, 16, 16, 0, tzinfo=timezone.utc),
                          calendar_loader=_loader())
    _, proofs = FC.completed_plan(SESSION, OBSERVED, calendar_loader=_loader())
    assert set(proofs) == set(FC.CALENDARS)
    assert proofs["RHM.DE"]["calendar"] == "XETR"


def test_a_local_holiday_waits_instead_of_substituting_a_prior_session():
    with pytest.raises(ValueError, match="WAIT_EXACT_LISTING_SESSION:XOSL"):
        FC.completed_plan(SESSION, OBSERVED,
                          calendar_loader=_loader({"XOSL": (SESSION.isoformat(),)}))


def test_a_naive_or_pre_freeze_request_refuses():
    with pytest.raises(ValueError, match="AWARE_OBSERVATION_REQUIRED"):
        FC.completed_plan(SESSION, datetime(2026, 10, 17), calendar_loader=_loader())
    with pytest.raises(ValueError, match="EXACT_POST_FREEZE_SESSION_REQUIRED"):
        FC.completed_plan(date(2026, 10, 1), OBSERVED, calendar_loader=_loader())


def test_refresh_appends_every_exact_mark_and_reports_ok(tmp_path: Path):
    p = tmp_path / "global_bars.parquet"
    calls: list = []
    out = FC.refresh_required_marks(SESSION, observed_at=OBSERVED, path=p,
                                    downloader=_vendor(calls=calls),
                                    calendar_loader=_loader())
    assert out["status"] == "ok", out
    assert sorted(calls) == sorted(FC.CALENDARS)            # one singleton call each
    assert out["n_new_rows"] == 15                           # 3 sessions x 5 listings
    assert out["history_coverage"]["status"] == "COMPLETE"
    assert out["coverage"]["status"] == "COMPLETE_TARGET_COVERAGE"
    # The daily attempt marker is honoured: a second call the same day fetches nothing.
    again = FC.refresh_required_marks(SESSION, observed_at=OBSERVED, path=p,
                                      downloader=_vendor(calls=calls),
                                      calendar_loader=_loader())
    assert again["n_pulled_now"] == 0 and len(calls) == 5 and again["status"] == "ok"


def test_a_missing_exact_mark_refuses_and_adds_no_false_row(tmp_path: Path):
    p = tmp_path / "global_bars.parquet"
    out = FC.refresh_required_marks(
        SESSION, observed_at=OBSERVED, path=p,
        downloader=_vendor(skip={("KOG.OL", SESSION.isoformat())}),
        calendar_loader=_loader())
    assert out["status"] == "refused"
    assert out["reason"].startswith("WAIT_EXACT_FROZEN_MARKS")
    assert [e["symbol"] for e in out["errors"]] == ["KOG.OL"]
    assert "MISSING_EXACT_REQUIRED_MARK" in out["errors"][0]["error"]
    cached = GP.read_cache(p)
    assert "KOG.OL" not in set(cached["symbol"])             # no forward fill
    assert len(cached) == 12                                 # the other four, intact


def test_pull_bars_refresh_carries_the_stage_into_its_receipt(tmp_path: Path):
    """The scheduled refresh's receipt names the stage, and a refused stage
    makes the whole refresh refused (rc 2), never a quiet success."""
    from scripts import pull_bars_refresh as BR

    now = datetime.now(timezone.utc)
    last, _ = BR.last_closed_session(now)
    days, _ = BR._sessions(last - timedelta(days=60), last)
    panel = tmp_path / "b.parquet"
    pd.DataFrame([{"symbol": "AAA", "date": pd.Timestamp(d), "open": 10.0, "high": 10.0,
                   "low": 10.0, "close": 10.0, "volume": 1000, "vwap": 10.0, "trades": 10}
                  for d in days[-26:-1]]).to_parquet(panel, index=False)

    def no_new(symbols, start):
        return pd.DataFrame([{"symbol": "AAA", "date": pd.Timestamp(days[-1]), "open": 10.0,
                              "high": 10.0, "low": 10.0, "close": 10.0, "volume": 900,
                              "vwap": 10.0, "trades": 4}]), "fixture"

    seen = []

    def refused(session, *, observed_at):
        seen.append(session)
        return {"status": "refused", "reason": "WAIT_EXACT_FROZEN_MARKS; fixture",
                "n_new_rows": 0}

    rec = BR.refresh({"ranker_deep": panel}, now_utc=now, puller=no_new,
                     receipt_dir=tmp_path / "r", index=tmp_path / "r" / "i.jsonl",
                     required_mark_refresher=refused)
    assert seen == [last]
    assert rec["frozen_constituents"]["status"] == "refused"
    assert rec["status"] == "refused" and "frozen constituents" in rec["reason"]

    # A custom-panel caller that does not inject the stage stays isolated from it.
    iso = BR.refresh({"ranker_deep": panel}, now_utc=now, puller=no_new,
                     receipt_dir=tmp_path / "r2", index=tmp_path / "r2" / "i.jsonl")
    assert "frozen_constituents" not in iso
