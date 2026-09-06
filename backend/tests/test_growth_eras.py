"""THE ERA GRID MUST DESCRIBE THE PANEL IT WAS HANDED, OR SAY IT DOES NOT.

`learner/evaluate.ERAS` is 2016-2018 / 2019-2021 / 2022-2024 -- written for the
12-year panel and correct there. Graded against the 1999-2024 long panel it
described the last nine years and said nothing about the other seventeen: rows
before 2016 matched no window, fell out of the loop, and left a receipt that
looked complete (2026-09-07 Labor Day lab, lane B1, "queued, not done"). Silence
is not evidence, and a table that cannot cover its data is a broken table, not a
strict one.

These tests pin the repair AND the thing the repair must not break:

  * the 1999-2024 panel under the DEFAULT grid REFUSES, and the refusal names
    both what would have been described and what the data actually spans;
  * the same panel under `long_eras()` -- DERIVED from `learner.long_panel.ERAS`,
    so it follows that constant rather than restating it -- gives three buckets
    and zero rows outside;
  * a 2016-2024 panel under the default grid reproduces the PRE-FIX output
    exactly, bucket for bucket and number for number, with `_coverage` as the
    only added key. Sealed receipts still reproduce;
  * a panel entirely outside the grid raises, because a table computed on zero
    rows is worse than no table.

Every date here is derived from the era boundaries themselves; nothing is
anchored to `today` (CLAUDE.md session protocol #5).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from learner import evaluate as E

BOOK_KEYS = ("months", "terminal_wealth_net", "terminal_wealth_market_same_months",
             "annualised_excess", "t_stat_paired_vs_market")


# --------------------------------------------------------------- the fixture

def _panel(first_year: int, last_year: int, n_names: int = 40,
           seed: int = 20260907) -> pd.DataFrame:
    """A synthetic monthly panel carrying exactly the columns the grader reads.

    A weak real signal so `rank_ic` and `book` have something to grade; the
    numbers themselves are never asserted, only their INVARIANCE to the change.
    """
    rng = np.random.default_rng(seed)
    months = pd.period_range(f"{first_year}-01", f"{last_year}-12", freq="M")
    permnos = 10_000 + np.arange(n_names)
    rows = []
    for p in months:
        mkt = float(rng.normal(0.006, 0.04))
        entry = pd.Timestamp(p.start_time.date())
        for permno in permnos:
            pred = float(rng.normal())
            fwd = mkt + 0.02 * pred + float(rng.normal(0.0, 0.05))
            rows.append({
                "month": str(p),                       # "YYYY-MM"
                "entry_date": entry,
                "permno": int(permno),
                "pred": pred,
                "fwd_1m": fwd,
                "mkt_vw_1m": mkt,
                "market_cap": float(rng.lognormal(mean=7.0, sigma=1.2)) * 1e6,
            })
    df = pd.DataFrame(rows)
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["excess_vw_1m"] = df["fwd_1m"] - df["mkt_vw_1m"]
    return df


def _legacy_grade_by_era(df: pd.DataFrame, pred_col: str, horizon_months: int,
                         benchmark: str = "vw") -> dict:
    """`grade_by_era` EXACTLY as it stood before the coverage repair.

    Kept here rather than described, so "the sealed numbers still reproduce" is
    a comparison and not a claim.
    """
    y = f"excess_{benchmark}_{horizon_months}m"
    out = {}
    for era, (lo, hi) in E.ERAS.items():
        sub = df[(df["entry_date"].dt.year >= lo) & (df["entry_date"].dt.year <= hi)]
        if sub.empty:
            continue
        row = {"rank_ic": E.rank_ic(sub, pred_col, y)}
        if horizon_months == 1:
            b = E.book(sub, pred_col, k=50, weight="vw")
            row["book_top50_vw"] = {kk: b.get(kk) for kk in BOOK_KEYS}
        out[era] = row
    return out


# ---------------------------------------------------- the grid must be derived

def test_long_eras_is_derived_from_long_panel_not_restated():
    from learner.long_panel import ERAS as LONG_PANEL_ERAS
    expected = {str(name): (int(lo), int(hi)) for name, lo, hi in LONG_PANEL_ERAS}
    assert E.long_eras() == expected
    # If long_panel's constant ever moves, this test follows it rather than
    # pinning a second copy of the boundaries that could drift away from it.
    assert "long_eras" in E.__all__


# ----------------------------------------------- the defect, and the refusal

def test_1999_2024_panel_under_the_default_grid_refuses():
    lo = min(v[0] for v in E.long_eras().values())
    hi = max(v[1] for v in E.long_eras().values())
    df = _panel(lo, hi)

    out = E.grade_by_era(df, "pred", 1)

    # The era buckets are NOT returned as if they were the whole story.
    assert set(out) == {"_coverage"}
    cov = out["_coverage"]
    assert cov["verdict"].startswith("REFUSED")
    # It names what would have been described, and what the data actually spans.
    assert "2016-2024" in cov["verdict"]          # the default grid's own range
    assert f"{lo}-{hi}" in cov["verdict"]         # the data's range
    assert "eras=" in cov["verdict"]
    assert cov["data_year_range"] == [lo, hi]
    assert cov["rows_total"] == len(df)
    assert cov["rows_outside_every_era"] > 0
    assert cov["rows_in_an_era"] + cov["rows_outside_every_era"] == cov["rows_total"]
    assert cov["share_outside"] > E.ERA_COVERAGE_FLOOR
    # 1999-2015 is seventeen of twenty-six years.
    assert cov["share_outside"] == pytest.approx(17 / 26, abs=0.01)
    assert set(cov) == {"rows_total", "rows_in_an_era", "rows_outside_every_era",
                        "share_outside", "data_year_range", "eras_used", "verdict"}
    assert cov["eras_used"] == {k: [v[0], v[1]] for k, v in E.ERAS.items()}


def test_same_panel_under_long_eras_covers_everything():
    lo = min(v[0] for v in E.long_eras().values())
    hi = max(v[1] for v in E.long_eras().values())
    df = _panel(lo, hi)

    out = E.grade_by_era(df, "pred", 1, eras=E.long_eras())

    assert set(out) == {"_coverage"} | set(E.long_eras())
    cov = out["_coverage"]
    assert cov["share_outside"] == 0.0
    assert cov["rows_outside_every_era"] == 0
    assert cov["rows_in_an_era"] == len(df)
    assert not cov["verdict"].startswith("REFUSED")
    assert cov["verdict"].startswith("OK")
    for era in E.long_eras():
        assert set(out[era]) == {"rank_ic", "book_top50_vw"}
        assert out[era]["rank_ic"]["months"] > 0


# ------------------------------------------- the sealed receipts still hold

def test_2016_2024_panel_reproduces_the_pre_fix_output_plus_coverage():
    df = _panel(2016, 2024)

    out = E.grade_by_era(df, "pred", 1)
    legacy = _legacy_grade_by_era(df, "pred", 1)

    # THE KEY SET, PINNED EXPLICITLY.
    assert set(out) == {"_coverage", "2016-2018", "2019-2021", "2022-2024"}
    assert set(out) - {"_coverage"} == set(legacy)
    for era in legacy:
        assert set(out[era]) == {"rank_ic", "book_top50_vw"}
        assert set(out[era]["book_top50_vw"]) == set(BOOK_KEYS)
        # Byte for byte: the era numbers a sealed receipt carries are unmoved.
        assert out[era] == legacy[era]

    cov = out["_coverage"]
    assert cov["share_outside"] == 0.0
    assert cov["rows_outside_every_era"] == 0
    assert cov["data_year_range"] == [2016, 2024]
    assert not cov["verdict"].startswith("REFUSED")


def test_a_handful_of_rows_outside_is_below_the_floor_and_still_grades():
    df = _panel(2016, 2024)
    stragglers = df[df["entry_date"].dt.year == 2016].head(20).copy()
    stragglers["entry_date"] = stragglers["entry_date"] - pd.DateOffset(years=1)
    stragglers["month"] = "2015-01"
    df = pd.concat([stragglers, df], ignore_index=True)

    out = E.grade_by_era(df, "pred", 1)
    cov = out["_coverage"]

    assert 0.0 < cov["share_outside"] <= E.ERA_COVERAGE_FLOOR
    assert cov["verdict"].startswith("OK")
    assert set(out) == {"_coverage", "2016-2018", "2019-2021", "2022-2024"}


# ---------------------------------------------- zero rows in any era: raise

def test_a_panel_entirely_outside_the_grid_raises():
    df = _panel(1999, 2007)
    with pytest.raises(SystemExit) as exc:
        E.grade_by_era(df, "pred", 1)
    msg = str(exc.value)
    assert msg.startswith("REFUSED")
    assert "1999-2007" in msg          # the data's range
    assert "2016-2024" in msg          # the grid's range
    assert "100.00%" in msg


def test_era_coverage_is_callable_on_its_own_and_reports_the_grid_it_used():
    df = _panel(2016, 2018)
    cov = E.era_coverage(df, E.long_eras())
    assert cov["eras_used"] == {"1999-2007": [1999, 2007], "2008-2015": [2008, 2015],
                                "2016-2024": [2016, 2024]}
    assert cov["share_outside"] == 0.0
    assert E.era_coverage(df)["share_outside"] == 0.0
