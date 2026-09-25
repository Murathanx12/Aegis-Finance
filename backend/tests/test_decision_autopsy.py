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


# ── the second benchmark: the universe's time-matched cross-sectional median ──

def _flat_spy_all_up_2pct(n_names: int = 9):
    days = pd.bdate_range("2026-09-14", periods=4)
    rows = []
    for d in days:
        rows.append({"symbol": "SPY", "date": d, "open": 100.0, "close": 100.0})    # flat
        for k in range(n_names):
            rows.append({"symbol": f"N{k}", "date": d, "open": 10.0, "close": 10.2})  # +2% each day
    bars = pd.DataFrame(rows)
    elig = pd.DataFrame([{"symbol": f"N{k}", "date": d, "eligible": True}
                         for d in days for k in range(n_names)])
    return bars, elig


def test_everything_up_2pct_is_zero_vs_the_universe_and_plus_2_vs_spy():
    bars, elig = _flat_spy_all_up_2pct()
    p = DA.Prices(bars, universe=DA.UniverseMedian(bars, elig, min_names=1))
    x = p.relative("N3", "2026-09-14", horizons=(1,))[1]
    assert x["status"] == "OK"
    assert x["rel"] == pytest.approx(0.02)            # size/market effect: +2 vs SPY
    assert x["rel_univ"] == pytest.approx(0.0)        # skill: none
    assert x["univ"] == pytest.approx(0.02) and x["univ_n"] == 9

    dec = [{"date": "2026-09-14", "ticker": "N1", "direction": "PROBE"},
           {"date": "2026-09-14", "ticker": "N2", "direction": "REFUSED"}]
    res = DA.autopsy(dec, [], p, horizons=(1,))
    t = res["by_direction"]["PROBE"]["1"]
    assert t["mean_rel"] == pytest.approx(0.02) and t["mean_rel_univ"] == pytest.approx(0.0)
    assert t["mean_spy"] == pytest.approx(0.0) and t["mean_univ"] == pytest.approx(0.02)
    h = res["headline"]["1"]
    assert h["pooled_vs_universe_median"] == pytest.approx(0.0)
    assert h["n_date_blocks"] == 1
    b = res["benchmarks_by_day"]["2026-09-14"]["1"]
    assert b["spy"] == pytest.approx(0.0) and b["universe_median"] == pytest.approx(0.02)


def test_universe_median_needs_min_names_and_uses_only_names_eligible_at_the_decision():
    bars, elig = _flat_spy_all_up_2pct(n_names=3)
    # N0 eligible only from 09-16: it cannot enter a benchmark for a 09-14 decision.
    elig = elig[~((elig["symbol"] == "N0") & (elig["date"] < "2026-09-16"))]
    bars.loc[bars["symbol"] == "N0", "close"] = 20.0                 # +100%: would move the median
    u = DA.UniverseMedian(bars, elig, min_names=1)
    w = u.window(pd.Timestamp("2026-09-15"), pd.Timestamp("2026-09-15"), "2026-09-14")
    assert w["n"] == 2 and w["median"] == pytest.approx(0.02)
    assert DA.UniverseMedian(bars, elig, min_names=5).window(
        pd.Timestamp("2026-09-15"), pd.Timestamp("2026-09-15"), "2026-09-14") is None
    p = DA.Prices(bars, universe=DA.UniverseMedian(bars, elig, min_names=5))
    x = p.relative("N1", "2026-09-14", horizons=(1,))[1]
    assert x["status"] == "OK" and x["rel_univ"] is None           # SPY still graded


def test_headline_day_matched_gap_is_benchmark_free():
    bars, elig = _flat_spy_all_up_2pct()
    bars.loc[bars["symbol"] == "N1", "close"] = 10.5                 # PROBE name +5%
    p = DA.Prices(bars, universe=DA.UniverseMedian(bars, elig, min_names=1))
    dec = [{"date": d, "ticker": "N1", "direction": "PROBE"} for d in ("2026-09-14", "2026-09-15")]
    dec += [{"date": d, "ticker": "N2", "direction": "REFUSED"} for d in ("2026-09-14", "2026-09-15")]
    h = DA.autopsy(dec, [], p, horizons=(1,))["headline"]["1"]
    assert h["n_date_blocks"] == 2
    assert h["day_matched_gap"] == pytest.approx(0.03)
    assert h["pooled_vs_universe_median"] == pytest.approx(0.03)
    assert h["pooled_vs_spy"] == pytest.approx(0.03)


def test_eligibility_reuses_xs_ranker_rule():
    days = pd.bdate_range("2025-01-01", periods=140)
    rows = [{"symbol": s, "date": d, "open": px, "close": px * (1 + 0.001 * (i % 3)),
             "volume": vol}
            for s, px, vol in (("LIQ", 50.0, 1e6), ("THIN", 50.0, 10.0), ("SPY", 500.0, 1e8))
            for i, d in enumerate(days)]
    e = DA.eligibility(pd.DataFrame(rows))
    last = e[e["date"] == days[-1]].set_index("symbol")["eligible"]
    assert bool(last["LIQ"]) and not bool(last["THIN"]) and not bool(last["SPY"])
    assert not e[e["date"] == days[100]]["eligible"].any()          # < 126 sessions seen
