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

ONE MISSING-NAME RULE, VERSIONED (adjudicated 2026-09-27). A book whose entry
session is on or after `config.LLM_BOOK_GRADE_RULE_V2_FROM` (2026-09-28) is
graded under version 2: a halted name and a NaN open are the SAME case -- the
name enters at its next valid open and sits in cash at 0% until then, never
re-weighted onto the others -- and a book under half priced after 5 sessions is
`REFUSED_UNDER_PRICED`. A book that entered earlier keeps version 1 exactly
(the halted/NaN/cash tests below run it on a 09-18 entry).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import llm_portfolio as LP

DAYS = pd.bdate_range("2026-08-03", "2026-10-02")
ENTRY = pd.Timestamp("2026-09-28")
NEXT = pd.Timestamp("2026-09-29")
# a version-1 book: frozen 09-17, entered 09-18 (before the rule change)
V1_ASOF = "2026-09-17"
V1_ENTRY = pd.Timestamp("2026-09-18")
V1_NEXT = pd.Timestamp("2026-09-21")


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


def test_v1_a_halted_name_is_a_named_deferred_entry():
    bars = _bars("SPY", "AAA", "HLT")
    bars = bars[~((bars.symbol == "HLT") & (bars.date == V1_ENTRY))]
    book = _book([("AAA", 0.5), ("HLT", 0.5)], asof=V1_ASOF)
    # entry evening: the halted name has no bar on or after entry -> named, not entered
    mon = LP.grade(book, bars[bars.date <= V1_ENTRY], today=V1_ENTRY)
    assert mon["grade_rule_version"] == 1
    assert mon["unpriceable_why"]["HLT"].startswith("NO_BAR_ON_OR_AFTER_ENTRY")
    assert mon["deferred_entry"] == []
    # the same grade on the full panel with today=entry: identical (no peeking)
    full_mon = LP.grade(book, bars, today=V1_ENTRY)
    assert full_mon["unpriceable_why"] == mon["unpriceable_why"]
    assert full_mon["to_date"]["net"] == pytest.approx(mon["to_date"]["net"])
    # next session: entered at ITS first open, and the grade says so
    tue = LP.grade(book, bars, today=V1_NEXT)
    assert tue["n_unpriceable"] == 0
    (d,) = tue["deferred_entry"]
    assert d["ticker"] == "HLT" and d["entry_session"] == "2026-09-18"
    assert d["entered_at_open_of"] == "2026-09-21"
    # held flat at its weight on the entry session: h=1 is AAA's day at half weight
    a = bars[(bars.symbol == "AAA") & (bars.date == V1_ENTRY)].iloc[0]
    assert tue["horizons"][1]["gross"] == pytest.approx(0.5 * (a.close / a.open - 1.0))


def test_v1_a_nan_entry_open_is_named_and_never_priced_at_zero_or_the_prior_close():
    bars = _bars("SPY", "AAA", "NAN", NAN={"drift": 0.01})
    bars.loc[(bars.symbol == "NAN") & (bars.date == V1_ENTRY), "open"] = np.nan
    g = LP.grade(_book([("AAA", 0.5), ("NAN", 0.5)], asof=V1_ASOF), bars, today=V1_NEXT)
    assert g["grade_rule_version"] == 1
    assert g["unpriceable"] == ["NAN"]
    assert g["unpriceable_why"]["NAN"].startswith("ENTRY_OPEN_NOT_FINITE on 2026-09-18")
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


@pytest.mark.parametrize("asof,today,ver", [(V1_ASOF, V1_NEXT, 1), ("2026-09-25", NEXT, 2)])
def test_a_book_left_with_only_cash_is_refused_not_graded_as_cash(asof, today, ver):
    bars = _bars("SPY")
    g = LP.grade(_book([("XBI", 0.9), ("CASH", 0.1)], asof=asof), bars, today=today)
    assert g["status"] == "REFUSED" and g["grade_rule_version"] == ver
    assert g["unpriceable_why"] == {"XBI": "NO_BARS"}
    # a book FROZEN as cash is still graded (nothing was missing)
    c = LP.grade(_book([("CASH", 1.0)], asof=asof), bars, today=today)
    assert c["status"] == "OK" and c["to_date"]["gross"] == pytest.approx(0.0)
    assert c["grade_rule_version"] == ver


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


# ─────────────────── rule version 2: one missing-name rule from 2026-09-28 ───

def _day(bars, sym, day):
    return bars[(bars.symbol == sym) & (bars.date == day)].iloc[0]


def test_v2_halt_and_nan_open_are_one_rule_deferred_to_the_next_valid_open():
    bars = _bars("SPY", "AAA", "HLT", "NAN", AAA={"drift": 0.004},
                 HLT={"drift": 0.01}, NAN={"drift": 0.01})
    bars = bars[~((bars.symbol == "HLT") & (bars.date == ENTRY))].copy()   # halted
    bars.loc[(bars.symbol == "NAN") & (bars.date == ENTRY), "open"] = np.nan  # NaN open
    halt = _book([("AAA", 0.5), ("HLT", 0.5)], name="halt", book_id="h")
    nan = _book([("AAA", 0.5), ("NAN", 0.5)], name="nan", book_id="n")
    # Monday evening: neither has entered; both wait in cash, both named
    for b, t in ((halt, "HLT"), (nan, "NAN")):
        g = LP.grade(b, bars, today=ENTRY)
        assert g["status"] == "OK" and g["grade_rule_version"] == 2
        (d,) = g["deferred_entry"]
        assert d["ticker"] == t and d["entered_at_open_of"] is None
        assert t in g["unpriceable_why"]
        assert g["weight_priced"] == pytest.approx(0.5)
        assert g["weight_in_market"] == pytest.approx(0.5)
    assert "NO_BAR_ON_ENTRY_SESSION" in LP.grade(halt, bars, today=ENTRY)["unpriceable_why"]["HLT"]
    assert "ENTRY_OPEN_NOT_FINITE on 2026-09-28" in \
        LP.grade(nan, bars, today=ENTRY)["unpriceable_why"]["NAN"]
    # Tuesday: BOTH entered at the 09-29 open -- the same rule for both cases
    gh, gn = LP.grade(halt, bars, today=NEXT), LP.grade(nan, bars, today=NEXT)
    for g, t in ((gh, "HLT"), (gn, "NAN")):
        (d,) = g["deferred_entry"]
        assert d["ticker"] == t and d["entered_at_open_of"] == "2026-09-29"
        assert g["n_unpriceable"] == 0 and g["weight_priced"] == pytest.approx(1.0)
        a0, a1, x1 = _day(bars, "AAA", ENTRY), _day(bars, "AAA", NEXT), _day(bars, t, NEXT)
        # h=1: AAA's day at HALF weight (the other half in cash at 0%, NOT re-weighted)
        assert g["horizons"][1]["gross"] == pytest.approx(0.5 * (a0.close / a0.open - 1.0))
        assert g["horizons"][1]["weight_priced"] == pytest.approx(0.5)
        # to date: AAA from the 09-28 open, the deferred name from ITS 09-29 open
        assert g["to_date"]["gross"] == pytest.approx(
            0.5 * a1.close / a0.open + 0.5 * x1.close / x1.open - 1.0)
    assert gh["to_date"]["gross"] == pytest.approx(gn["to_date"]["gross"])


def test_v2_cash_is_not_reweighted_where_v1_would_scale_the_remnant():
    bars = _bars("SPY", "AAA", AAA={"drift": 0.01})
    v2 = LP.grade(_book([("AAA", 0.4), ("XBI", 0.6)]), bars, today=NEXT)
    a0, a1 = _day(bars, "AAA", ENTRY), _day(bars, "AAA", NEXT)
    r = a1.close / a0.open - 1.0
    assert v2["grade_rule_version"] == 2 and v2["status"] == "OK"
    assert v2["to_date"]["gross"] == pytest.approx(0.4 * r)          # 60% in cash at 0%
    assert v2["weight_priced"] == pytest.approx(0.4)
    assert v2["unpriceable_why"] == {"XBI": "NO_BARS"}
    # the same book entered 09-18 keeps v1: the remnant scaled to 100%
    v1 = LP.grade(_book([("AAA", 0.4), ("XBI", 0.6)], asof=V1_ASOF), bars, today=V1_NEXT)
    b0, b1 = _day(bars, "AAA", V1_ENTRY), _day(bars, "AAA", V1_NEXT)
    assert v1["grade_rule_version"] == 1
    assert v1["to_date"]["gross"] == pytest.approx(b1.close / b0.open - 1.0)
    assert v1["weight_priced"] == pytest.approx(0.4)


def test_v2_under_priced_after_five_sessions_is_refused_not_graded_on_a_remnant():
    bars = _bars("SPY", "AAA")
    book = _book([("AAA", 0.4), ("XBI", 0.6)])
    four = LP.grade(book, bars, today=pd.Timestamp("2026-10-01"))
    assert four["status"] == "OK" and four["to_date"]["sessions"] == 4
    five = LP.grade(book, bars, today=pd.Timestamp("2026-10-02"))
    assert five["status"] == "REFUSED_UNDER_PRICED" and five["sessions"] == 5
    assert five["weight_priced"] == pytest.approx(0.4) and "to_date" not in five
    assert "weight_priced 0.400 < 0.5" in five["why"]
    # declared cash is priced as frozen: a 60%-cash book is never under-priced
    cashy = LP.grade(_book([("AAA", 0.4), ("CASH", 0.6)]), bars,
                     today=pd.Timestamp("2026-10-02"))
    assert cashy["status"] == "OK" and cashy["weight_priced"] == pytest.approx(1.0)
    assert cashy["weight_in_market"] == pytest.approx(0.4)
    lb = LP.leaderboard([book], bars, today=pd.Timestamp("2026-10-02"), voided=[])
    assert lb["status_counts"] == {"REFUSED_UNDER_PRICED": 1}
    assert lb["refused"][0]["status"] == "REFUSED_UNDER_PRICED"
    assert lb["books"][0]["weight_priced"] == pytest.approx(0.4)


def test_v1_under_priced_book_is_still_graded_exactly_as_published():
    """No v1 number moves: a pre-09-28 book under half priced stays OK, scaled."""
    bars = _bars("SPY", "AAA", AAA={"drift": 0.002})
    g = LP.grade(_book([("AAA", 0.3), ("XBI", 0.7)], asof=V1_ASOF), bars,
                 today=pd.Timestamp("2026-10-02"))
    assert g["status"] == "OK" and g["grade_rule_version"] == 1
    a0 = _day(bars, "AAA", V1_ENTRY)
    a1 = _day(bars, "AAA", pd.Timestamp("2026-10-02"))
    assert g["to_date"]["gross"] == pytest.approx(a1.close / a0.open - 1.0)


def test_every_grade_row_carries_its_rule_version():
    bars = _bars("SPY", "AAA")
    books = [_book([("AAA", 1.0)], name="v1", book_id="a", asof=V1_ASOF),
             _book([("AAA", 1.0)], name="v2", book_id="b"),
             _book([("AAA", 1.0)], name="later", book_id="c", asof="2026-10-02")]
    lb = LP.leaderboard(books, bars, today=NEXT, voided=[])
    by = {r["name"]: r for r in lb["books"]}
    assert by["v1"]["grade_rule_version"] == 1 and by["v2"]["grade_rule_version"] == 2
    assert by["later"]["status"] == "PENDING"
    assert by["later"]["grade_rule_version"] in (2, None)       # None only without a calendar
    assert lb["grade_rule_versions"]["1"] == 1 and lb["grade_rule_versions"]["2"] >= 1
