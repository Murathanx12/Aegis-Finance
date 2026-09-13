"""THE MACRO CALENDAR (chunk 14, loop 4) — no key read, no request made.

Two refusals and one shortcut are pinned:

* **no FRED key is `FRED_KEY_ABSENT`, never an empty list.** `market_sensor.py`
  already draws that line for `VIXCLS` and this reuses it: a calendar that
  returned `[]` because nobody set a key is indistinguishable from a quiet
  quarter, and a reader would plan around the wrong one.
* **the FOMC table ships EMPTY and says exactly how to seed it.** Eight
  invented meeting dates would produce a calendar that looks complete and is
  wrong, and a wrong scheduled date is worse than an absent one.
* **every entry's `engine_probability` is null with `AWAITING_L2`.** X3 is not
  wired; a fabricated number attached to a real date is the failure nobody
  would notice for months.

Dates are derived from `date.today()`. The FRED fetch is injected, so no test
needs a key or a socket.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from backend import config as _config
from backend.services import macro_calendar as MC


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "DATA_DIR", tmp_path)
    return tmp_path


def fake_fred(dates):
    """A FRED `release/dates` payload carrying exactly `dates`."""
    def _fetch(path, params):
        assert path == "release/dates"
        assert params["include_release_dates_with_no_data"] == "true", (
            "without this flag FRED answers only for releases that already have "
            "data — i.e. the past — and a forward calendar of history is not one")
        return {"release_dates": [{"release_id": params["release_id"], "date": d}
                                  for d in dates]}
    return _fetch


# --------------------------------------------------------------------------
# FRED


def test_no_fred_key_is_a_named_refusal_not_an_empty_calendar(data_dir, monkeypatch):
    monkeypatch.setattr(_config.api_keys, "fred", "")
    with pytest.raises(MC.MacroRefused) as exc:
        MC.release_dates("CPI")
    assert "FRED_KEY_ABSENT" in str(exc.value)
    assert "FRED_API_KEY" in str(exc.value)
    assert "UNOBSERVED" in str(exc.value)


def test_release_dates_returns_only_future_dates_with_provenance(data_dir):
    today = date.today()
    past = (today - timedelta(days=10)).isoformat()
    soon = (today + timedelta(days=11)).isoformat()
    rows = MC.release_dates("CPI", fetch=fake_fred([past, soon]))
    assert [r["event_time"] for r in rows] == [soon]
    r = rows[0]
    assert r["kind"] == "CPI"
    assert r["source"] == "fred_release_dates"
    assert r["detail"]["release_id"] == MC.FRED_RELEASES["CPI"]["release_id"]
    assert r["days_away"] == 11
    assert r["engine_probability"] is None
    assert r["probability_status"] == "AWAITING_L2"


def test_an_unknown_release_refuses_rather_than_guessing_an_id(data_dir):
    with pytest.raises(MC.MacroRefused) as exc:
        MC.release_dates("PCE")
    assert "UNKNOWN_RELEASE" in str(exc.value)


def test_both_declared_releases_are_cpi_and_nfp(data_dir):
    assert set(MC.FRED_RELEASES) == {"CPI", "NFP"}
    for spec in MC.FRED_RELEASES.values():
        assert isinstance(spec["release_id"], int)
        assert spec["what"]


# --------------------------------------------------------------------------
# the FOMC table


def test_the_fomc_table_ships_unseeded_and_says_how_to_seed_it(data_dir):
    table = MC.fomc_table()
    assert table["status"] == "FOMC_SCHEDULE_NOT_SEEDED"
    assert table["dates"] == []
    assert MC.FOMC_SOURCE_URL in table["how_to_seed"]
    assert "NOT invented here" in table["how_to_seed"]
    assert MC.fomc_events() == []


def test_a_seeded_table_is_served_and_dated(data_dir):
    today = date.today()
    soon = (today + timedelta(days=20)).isoformat()
    far = (today + timedelta(days=400)).isoformat()
    MC.fomc_path().write_text(json.dumps(
        {"verified_on": today.isoformat(), "source_url": MC.FOMC_SOURCE_URL,
         "dates": [soon, far]}), encoding="utf-8")
    table = MC.fomc_table()
    assert table["status"] == "ok" and table["age_days"] == 0
    events = MC.fomc_events()
    assert [e["event_time"] for e in events] == [soon], "the 400-day date is beyond the horizon"
    assert events[0]["source"] == "fed_schedule_static"


def test_a_year_old_table_is_stale_and_still_served(data_dir):
    """An old meeting list is better than none, PROVIDED the reader is told."""
    today = date.today()
    old = (today - timedelta(days=MC.STALE_AFTER_DAYS + 5)).isoformat()
    soon = (today + timedelta(days=10)).isoformat()
    MC.fomc_path().write_text(json.dumps(
        {"verified_on": old, "dates": [soon]}), encoding="utf-8")
    table = MC.fomc_table()
    assert table["status"] == "FOMC_SCHEDULE_STALE"
    assert len(MC.fomc_events()) == 1


def test_an_undated_table_is_named_rather_than_trusted(data_dir):
    soon = (date.today() + timedelta(days=10)).isoformat()
    MC.fomc_path().write_text(json.dumps({"dates": [soon]}), encoding="utf-8")
    assert MC.fomc_table()["status"] == "FOMC_SCHEDULE_UNDATED"


def test_an_unreadable_table_is_named_rather_than_crashing(data_dir):
    MC.fomc_path().write_text("{not json", encoding="utf-8")
    table = MC.fomc_table()
    assert table["status"] == "FOMC_SCHEDULE_UNREADABLE"
    assert table["dates"] == []


# --------------------------------------------------------------------------
# the block


def test_the_block_never_raises_and_names_every_refused_leg(data_dir, monkeypatch):
    monkeypatch.setattr(_config.api_keys, "fred", "")
    block = MC.macro_block()
    assert block["macro"] == []
    kinds = {r["kind"] for r in block["refusals"]}
    assert kinds == {"CPI", "NFP", "FOMC"}
    assert block["legs"]["CPI"] == "REFUSED"
    assert "FOMC_SCHEDULE_NOT_SEEDED" in block["legs"]["FOMC"]
    assert block["uncovered"], "the gaps are named, not implied"


def test_the_block_sorts_by_date_and_keeps_the_earnings_half_alive(data_dir, monkeypatch):
    """A macro leg that refused must not take the per-ticker half down."""
    today = date.today()
    d1 = (today + timedelta(days=5)).isoformat()
    d2 = (today + timedelta(days=25)).isoformat()

    def _fetch(path, params):
        want = {MC.FRED_RELEASES["CPI"]["release_id"]: d2,
                MC.FRED_RELEASES["NFP"]["release_id"]: d1}
        return {"release_dates": [{"date": want[params["release_id"]]}]}

    block = MC.macro_block(fetch=_fetch)
    assert [e["event_time"] for e in block["macro"]] == [d1, d2]
    assert [e["kind"] for e in block["macro"]] == ["NFP", "CPI"]


def test_calendar_extended_calls_the_per_ticker_half_rather_than_rebuilding_it(
        data_dir, monkeypatch):
    seen: dict = {}

    def _cal(tickers, positions=None):
        seen["tickers"] = list(tickers)
        return {"0_7d": [], "events_found": 0, "coverage": {"grade": "v0"}}

    from backend.services import pm_catalysts
    monkeypatch.setattr(pm_catalysts, "calendar", _cal)
    monkeypatch.setattr(_config.api_keys, "fred", "")
    out = MC.calendar_extended(["NVDA", "AMD"])
    assert seen["tickers"] == ["NVDA", "AMD"]
    assert "macro" in out and "0_7d" in out
    assert out["coverage"]["grade"] == "v0", "the existing coverage card survives"
    assert out["coverage"]["macro_legs"]["CPI"] == "REFUSED"
