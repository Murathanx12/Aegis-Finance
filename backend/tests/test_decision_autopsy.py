"""decision_autopsy: grade the calls the decision contract made, vs SPY."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts import decision_autopsy as DA


def _bars():
    days = pd.bdate_range("2026-09-14", periods=8)          # Mon 14 .. Wed 23
    rows = []
    for i, d in enumerate(days):
        rows.append({"symbol": "SPY", "date": d, "open": 100.0, "close": 100.0 + i})   # SPY drifts up
        rows.append({"symbol": "UP", "date": d, "open": 10.0, "close": 10.0 * (1.1 ** (i + 1))})
        rows.append({"symbol": "DOWN", "date": d, "open": 10.0, "close": 9.0})
    return pd.DataFrame(rows)


def test_entry_is_the_open_after_the_decision_day_and_relative_to_spy():
    p = DA.Prices(_bars())
    r = p.relative("DOWN", "2026-09-14", horizons=(1, 5))
    # entry 2026-09-15 open (100 / 10), 1d exit 2026-09-15 close (101 / 9)
    assert r[1]["entry"] == "2026-09-15" and r[1]["exit"] == "2026-09-15"
    assert r[1]["rel"] == pytest.approx((9 / 10 - 1) - (101 / 100 - 1))
    assert r[5]["exit"] == "2026-09-21"


def test_a_horizon_not_yet_elapsed_is_pending_not_zero():
    p = DA.Prices(_bars())
    r = p.relative("UP", "2026-09-21", horizons=(1, 5, 21))
    assert r[1]["status"] == "OK"
    assert r[5]["status"] == "PENDING" and r[21]["status"] == "PENDING"


def test_unknown_ticker_is_unpriced():
    p = DA.Prices(_bars())
    assert p.relative("NOPE", "2026-09-14", horizons=(1,))[1]["status"] == "UNPRICED"


def test_autopsy_lists_refused_that_rose_and_bought_that_fell():
    p = DA.Prices(_bars())
    dec = [{"date": "2026-09-14", "ticker": "UP", "direction": "REFUSED", "terminal_state": "NEGATIVE_EV"},
           {"date": "2026-09-14", "ticker": "DOWN", "direction": "BUY"},
           {"date": "2026-09-15", "ticker": "UP", "direction": "BUY"}]
    pred = [{"date": "2026-09-14", "ticker": "UP", "specialist": "investigator:x",
             "horizon_days": 1, "probability": 0.7},
            {"date": "2026-09-14", "ticker": "DOWN", "specialist": "investigator:x",
             "horizon_days": 1, "probability": 0.8}]
    res = DA.autopsy(dec, pred, p, horizons=(1, 5))
    assert [r["ticker"] for r in res["refused_but_rose"]] == ["UP"]
    assert res["refused_but_rose"][0]["horizon"] == 5          # longest resolved horizon
    assert [r["ticker"] for r in res["bought_but_fell"]] == ["DOWN"]
    assert res["by_direction"]["BUY"]["1"]["n"] == 2
    s = res["predictions_by_specialist"]["investigator:x"]
    assert s["n_graded_at_own_horizon"] == 2
    assert s["own_horizon_hit"] == pytest.approx(0.5)          # UP right, DOWN wrong
    assert s["own_horizon_brier"] == pytest.approx(((0.7 - 1) ** 2 + (0.8 - 0) ** 2) / 2)


def test_load_decisions_dedupes_virtual_probe_rows(tmp_path):
    rows = [{"ticker": "AAA", "direction": "PROBE", "horizon_sessions": h} for h in (5, 21, 63)]
    rows += [{"ticker": "BBB", "direction": "REFUSED"}, {"ticker": None, "direction": "BUY"},
             {"ticker": "CCC", "direction": "NONSENSE"}]
    (tmp_path / "2026-09-24.json").write_text(json.dumps({"date": "2026-09-24", "rows": rows}))
    (tmp_path / "autopsy_2026-09-25.json").write_text("{}")
    got = DA.load_decisions(tmp_path)
    assert sorted((r["ticker"], r["direction"]) for r in got) == [("AAA", "PROBE"), ("BBB", "REFUSED")]


def test_load_predictions_filters_by_made_at(tmp_path):
    p = tmp_path / "predictions.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in [
        {"ticker": "OLD", "made_at": "2026-09-01T00:00:00+00:00", "specialist": "a"},
        {"ticker": "NEW", "made_at": "2026-09-24T15:00:00+00:00", "decision_date": "2026-09-24",
         "specialist": "b", "horizon_days": 1, "probability": 0.6},
    ]) + "\nnot json\n")
    got = DA.load_predictions(p, since="2026-09-11")
    assert [r["ticker"] for r in got] == ["NEW"] and got[0]["date"] == "2026-09-24"


def test_book_level_rows_are_counted_apart_not_graded_as_unpriced_tickers(tmp_path):
    """`AGENCY_BOOK:balanced` is a BOOK proposal (instrument_kind 'book'), not a
    ticker: grading it as a BUY made 18 of 23 BUY rows 'UNPRICED' on 09-25."""
    rows = [{"ticker": "AGENCY_BOOK:balanced", "direction": "BUY", "instrument_kind": "book"},
            {"ticker": "CVLG", "direction": "BUY"}]
    (tmp_path / "2026-09-24.json").write_text(json.dumps({"date": "2026-09-24", "rows": rows}))
    skipped: dict = {}
    got = DA.load_decisions(tmp_path, skipped=skipped)
    assert [r["ticker"] for r in got] == ["CVLG"]
    assert skipped == {"book:BUY": 1}
