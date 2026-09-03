"""The close mark could never see the close it was marking (2026-09-02).

P-day-2026-08-19a made `mark_lane_to_market` stamp the NAV row with the date of
the bar that PRICED it, "so NAV_t means close_t by construction". The intent was
right and the window was wrong: both price helpers ask for

    end = datetime.now().strftime("%Y-%m-%d")

and yfinance's `end` is EXCLUSIVE, so the newest bar either helper can ever
return is YESTERDAY'S. The 16:30 ET close mark therefore stamps the PREVIOUS
session, every single day, by construction — the one thing the change set out
to stop.

Observed in prod: on 2026-09-02 `pi_hourly_mtm` ran four times (20:32, 21:32,
22:32, 23:32 UTC), each writing a receipt reading `status: marked, n_marked: 10,
n_failed: 0` beside `expected_nav_date: 2026-09-02` — while all ten lanes' NAV
stayed at 2026-09-01. Nothing failed; the row was simply written to yesterday's
date, again, idempotently. `nav.all_fresh` was false and the whole deploy read
DEGRADED.

Because `_expected_nav_date` rolls to today at 17:00 ET, the arithmetic leaves
NAV "fresh" only between the 16:30 mark and 17:00 — roughly half an hour a day.

BOTH helpers are pinned here, and they must move together: stamping the row with
today's bar date while `_get_current_prices` still returns yesterday's close
would date a stale price as today's — worse than the bug.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from backend.services.portfolio_intelligence import reference_engine as RE


def _calendar_fetch(recorded: dict):
    """A fetch that honours yfinance's EXCLUSIVE `end`.

    Emits one bar per calendar day in [start, end), priced so the value encodes
    the day. Deliberately calendar-free — no weekday logic, no literal dates —
    so the test cannot rot when it is next run on a Monday.
    """

    def fetch_safe(ticker: str, start: str, end: str, name: str = ""):
        recorded["start"], recorded["end"] = start, end
        s, e = date.fromisoformat(start), date.fromisoformat(end)
        days = [s + timedelta(days=i) for i in range((e - s).days)]  # end EXCLUSIVE
        if not days:
            return None
        return pd.Series([100.0 + i for i in range(len(days))],
                         index=pd.to_datetime(days))

    return fetch_safe


class TestPriceWindowReachesTodaysBar:
    def test_latest_bar_date_can_be_today(self, monkeypatch):
        """The whole point of the bar-date stamp: the mark must be able to see
        the session it is marking. With an exclusive end pinned to today this
        returns yesterday and NAV is one session stale forever."""
        rec: dict = {}
        monkeypatch.setattr("backend.services.data_fetcher.fetch_safe",
                            _calendar_fetch(rec))
        got = RE._get_latest_bar_date(["AAA"])
        assert got == date.today(), (
            f"latest reachable bar was {got}, not today — the fetch window "
            f"[{rec.get('start')}, {rec.get('end')}) excludes the current "
            f"session, so every close mark stamps the previous one")

    def test_current_prices_move_with_the_bar_date(self, monkeypatch):
        """The two helpers must agree on the window. If only the bar date
        advances, a NAV row gets today's DATE and yesterday's PRICE."""
        rec: dict = {}
        monkeypatch.setattr("backend.services.data_fetcher.fetch_safe",
                            _calendar_fetch(rec))
        prices = RE._get_current_prices(["AAA"])
        bar = RE._get_latest_bar_date(["AAA"])
        span = (date.fromisoformat(rec["end"])
                - date.fromisoformat(rec["start"])).days
        assert bar == date.today()
        # the fake prices day i at 100+i, so today's close is 100+(span-1)
        assert prices["AAA"] == pytest.approx(100.0 + span - 1), (
            "the price returned is not the close of the bar the row is "
            "stamped with")

    def test_mark_stamps_todays_session(self, monkeypatch, tmp_path):
        """End to end: the persisted NAV row carries today's date."""
        from backend.db import get_connection, init_db

        db = tmp_path / "barwindow.db"
        init_db(db)
        conn = get_connection(db)
        try:
            conn.execute(
                "INSERT INTO paper_portfolios (id, inception_date, "
                "inception_value, config_version) VALUES (?, ?, ?, ?)",
                ("w-lane", date.today().isoformat(), 100_000.0, "cfg1"))
            conn.execute(
                "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
                "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
                ("w-lane", "AAA", 10.0, 100.0, date.today().isoformat()))
            conn.commit()
        finally:
            conn.close()

        monkeypatch.setattr("backend.services.data_fetcher.fetch_safe",
                            _calendar_fetch({}))
        nav = RE.mark_lane_to_market("w-lane", db_path=db)
        assert nav is not None

        conn = get_connection(db)
        try:
            row = conn.execute(
                "SELECT date FROM paper_nav WHERE portfolio_id = ? "
                "ORDER BY date DESC LIMIT 1", ("w-lane",)).fetchone()
        finally:
            conn.close()
        assert row["date"] == date.today().isoformat(), (
            "the close mark stamped a session it did not price")
