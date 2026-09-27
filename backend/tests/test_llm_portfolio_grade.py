"""`llm_portfolio.grade` on the awkward first session (Monday rehearsal 2026-09-28).

`docs/REHEARSAL_2026-09-28_MONDAY_ENTRY.md`. About 300 frozen books entered at
one open for the first time; the rehearsal ran the grader on a copy of the real
panels with two synthetic sessions and three awkward names. What it found and
what these pin, all synthetic and offline:

* a HALTED name (no bar on the entry session) entered at its next open with
  nothing on the grade -> now a named `deferred_entry`;
* a NaN open was one more ticker in `unpriceable` -> now a named reason, and it
  never enters at zero or at the previous close;
* an UNADJUSTED 2-for-1 split after entry graded as a -50% day with nothing said
  -> now `suspect_splits` names it (the number is not rewritten);
* a benchmark absent from the panel (URTH under `grade --no-pull`) left
  `vs_benchmark` None on an `OK` grade -> now `benchmark_missing` + `why`;
* 307 grades took 126 s because every call re-grouped ~2M rows -> memoised;
* `leaderboard(today=X)` printed the panel's newest date as `bars_through`.

Dates are fixed on purpose: the entry session is the regression, and `today`
is passed on every call.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import llm_portfolio as LP

DAYS = pd.bdate_range("2026-08-03", "2026-10-02")
ENTRY = pd.Timestamp("2026-09-28")
NEXT = pd.Timestamp("2026-09-29")


def _series(sym, *, px=100.0, drift=0.0, gap=0.0):
    rows = []
    c = px
    for d in DAYS:
        o = c * (1 + gap)
        c = o * (1 + drift)
        rows.append({"symbol": sym, "date": d, "open": o, "high": max(o, c), "low": min(o, c),
                     "close": c, "volume": 1e6})
    return pd.DataFrame(rows)


def _bars(*syms, **kw):
    return pd.concat([_series(s, **kw.get(s, {})) for s in syms], ignore_index=True)


def _book(positions, *, benchmark="SPY", name="b", book_id="b1", asof="2026-09-25"):
    return {"schema": LP.SCHEMA_VERSION, "name": name, "book_id": book_id, "kind": "personal",
            "asof": asof, "objective": "x", "n_positions": len(positions),
            "horizon_days": [1, 5], "benchmark": benchmark,
            "positions": [{"ticker": t, "weight": w} for t, w in positions]}


def test_entry_is_the_entry_session_open_not_the_previous_close():
    bars = _bars("SPY", "AAA", AAA={"gap": 0.01, "drift": 0.002})
    g = LP.grade(_book([("AAA", 1.0)]), bars, today=ENTRY)
    assert g["status"] == "OK" and g["entry_session"] == "2026-09-28"
    row = bars[(bars.symbol == "AAA") & (bars.date == ENTRY)].iloc[0]
    assert g["horizons"][1]["gross"] == pytest.approx(row.close / row.open - 1.0)
    assert g["deferred_entry"] == [] and g["suspect_splits"] == []


def test_a_halted_name_is_a_named_deferred_entry():
    bars = _bars("SPY", "AAA", "HLT")
    bars = bars[~((bars.symbol == "HLT") & (bars.date == ENTRY))]
    book = _book([("AAA", 0.5), ("HLT", 0.5)])
    # Monday evening: the halted name has no bar on or after entry -> named, not entered
    mon = LP.grade(book, bars[bars.date <= ENTRY], today=ENTRY)
    assert mon["unpriceable_why"]["HLT"].startswith("NO_BAR_ON_OR_AFTER_ENTRY")
    assert mon["deferred_entry"] == []
    # the same grade on the full panel with today=Monday: identical (no peeking)
    full_mon = LP.grade(book, bars, today=ENTRY)
    assert full_mon["unpriceable_why"] == mon["unpriceable_why"]
    assert full_mon["to_date"]["net"] == pytest.approx(mon["to_date"]["net"])
    # Tuesday: entered at ITS first open, and the grade says so
    tue = LP.grade(book, bars, today=NEXT)
    assert tue["n_unpriceable"] == 0
    (d,) = tue["deferred_entry"]
    assert d["ticker"] == "HLT" and d["entry_session"] == "2026-09-28"
    assert d["entered_at_open_of"] == "2026-09-29"
    # held flat at its weight on the entry session: h=1 is AAA's day at half weight
    a = bars[(bars.symbol == "AAA") & (bars.date == ENTRY)].iloc[0]
    assert tue["horizons"][1]["gross"] == pytest.approx(0.5 * (a.close / a.open - 1.0))


def test_a_nan_entry_open_is_named_and_never_priced_at_zero_or_the_prior_close():
    bars = _bars("SPY", "AAA", "NAN", NAN={"drift": 0.01})
    bars.loc[(bars.symbol == "NAN") & (bars.date == ENTRY), "open"] = np.nan
    g = LP.grade(_book([("AAA", 0.5), ("NAN", 0.5)]), bars, today=NEXT)
    assert g["unpriceable"] == ["NAN"]
    assert g["unpriceable_why"]["NAN"].startswith("ENTRY_OPEN_NOT_FINITE on 2026-09-28")
    assert g["weight_priced"] == pytest.approx(0.5)
    assert all(np.isfinite(c["net"]) for c in g["horizons"].values() if c["status"] == "OK")
    assert np.isfinite(g["to_date"]["net"])


def test_an_unadjusted_split_after_entry_is_named_not_silent():
    bars = _bars("SPY", "SPL")
    m = (bars.symbol == "SPL") & (bars.date >= NEXT)
    for c in ("open", "high", "low", "close"):
        bars.loc[m, c] = bars.loc[m, c] * 0.5
    g = LP.grade(_book([("SPL", 1.0)]), bars, today=NEXT)
    (s,) = g["suspect_splits"]
    assert s["ticker"] == "SPL" and s["date"] == "2026-09-29"
    assert s["looks_like"] == "2-for-1 split"
    # NAMED, not rewritten: the number is still what the panel says
    assert g["to_date"]["gross"] == pytest.approx(-0.5)
    lb = LP.leaderboard([_book([("SPL", 1.0)])], bars, today=NEXT, voided=[])
    assert lb["suspect_splits"][0]["ticker"] == "SPL" and lb["books"][0]["n_suspect_splits"] == 1


def test_an_adjusted_split_is_not_a_suspect():
    """What `pull_bars_refresh` writes (adjustment=all): the whole history re-based."""
    bars = _bars("SPY", "SPL")
    g = LP.grade(_book([("SPL", 1.0)]), bars, today=NEXT)
    assert g["suspect_splits"] == [] and g["to_date"]["gross"] == pytest.approx(0.0)


def test_a_missing_benchmark_is_said_on_the_grade_and_counted():
    bars = _bars("SPY", "AAA")
    g = LP.grade(_book([("AAA", 1.0)], benchmark="URTH"), bars, today=NEXT)
    assert g["status"] == "OK" and g["benchmark_missing"] is True
    assert "URTH has no bars" in g["why"]
    assert g["to_date"]["vs_benchmark"] is None
    ok = LP.grade(_book([("AAA", 1.0)]), bars, today=NEXT)
    assert ok["benchmark_missing"] is False and "why" not in ok
    lb = LP.leaderboard([_book([("AAA", 1.0)], benchmark="URTH")], bars, today=NEXT, voided=[])
    assert lb["n_benchmark_missing"] == 1 and lb["benchmark_missing_symbols"] == ["URTH"]


def test_a_book_left_with_only_cash_is_refused_not_graded_as_cash():
    bars = _bars("SPY")
    g = LP.grade(_book([("XBI", 0.9), ("CASH", 0.1)]), bars, today=NEXT)
    assert g["status"] == "REFUSED" and g["unpriceable_why"] == {"XBI": "NO_BARS"}
    # a book FROZEN as cash is still graded (nothing was missing)
    c = LP.grade(_book([("CASH", 1.0)]), bars, today=NEXT)
    assert c["status"] == "OK" and c["to_date"]["gross"] == pytest.approx(0.0)


def test_the_grouping_memo_is_invisible():
    bars = _bars("SPY", "AAA", "BBB", AAA={"drift": 0.003}, BBB={"drift": -0.002})
    book = _book([("AAA", 0.6), ("BBB", 0.4)])
    a = LP.grade(book, bars, today=NEXT)
    b = LP.grade(book, bars, today=NEXT)                   # memo hit
    c = LP.grade(book, bars.copy(), today=NEXT)            # a different frame
    for x in (b, c):
        assert x["to_date"]["net"] == pytest.approx(a["to_date"]["net"])
        assert x["horizons"][1]["net"] == pytest.approx(a["horizons"][1]["net"])
    other = bars.copy()
    other.loc[other.symbol == "AAA", ["open", "close"]] *= 1.0   # same values, new object
    other = pd.concat([other, _series("CCC")], ignore_index=True)
    d = LP.grade(_book([("CCC", 1.0)]), other, today=NEXT)
    assert d["status"] == "OK"                              # not served from the old frame


def test_leaderboard_counts_every_status_and_bars_through_honours_today():
    bars = _bars("SPY", "AAA")
    books = [_book([("AAA", 1.0)]), _book([("XBI", 1.0)], name="etf", book_id="b2"),
             _book([("AAA", 1.0)], name="later", book_id="b3", asof="2026-09-29")]
    lb = LP.leaderboard(books, bars, today=ENTRY, voided=[])
    assert lb["bars_through"] == "2026-09-28"
    assert lb["status_counts"] == {"OK": 1, "REFUSED": 1, "PENDING": 1}
    assert [r["name"] for r in lb["refused"]] == ["etf"]
