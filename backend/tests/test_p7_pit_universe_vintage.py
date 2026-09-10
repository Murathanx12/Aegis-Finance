"""P7 -- the 2025-26 point-in-time universe vintage, pinned to its own receipt.

Same rule as `test_x9_day_run_numbers.py`: **the receipt wins.** Each test reads
a number out of `P7_pit_universe_vintage_run01.json` and then requires the
parquet to carry it, so a re-run that changes the membership goes red here
rather than quietly disagreeing with the receipt beside it.

The receipt and the parquet are large data artefacts and are not on every
checkout, so a missing file SKIPS. A file that is present and disagrees is a
FAILURE, which is the case that actually bites.

The last test is the one worth arguing about. A vintage is only worth building
if it is genuinely asymmetric in time -- some name must be IN an early month and
OUT of a later one -- and if no such pair exists the vintage repairs nothing and
the reader must be told that in the failure text, not left with a green tick.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RECEIPT = (REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-09"
           / "P7_pit_universe_vintage_run01.json")
PARQUET = (REPO / "backend" / "data" / "optimus" / "text_return_panel"
           / "pit_universe_vintage_2025_26.parquet")


def _receipt() -> dict:
    if not RECEIPT.is_file():
        pytest.skip(f"receipt absent on this machine: {RECEIPT}")
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def _vintage():
    pytest.importorskip("pyarrow")
    pd = pytest.importorskip("pandas")
    if not PARQUET.is_file():
        pytest.skip(f"vintage parquet absent on this machine: {PARQUET}")
    return pd.read_parquet(PARQUET)


def test_receipt_shape_is_a_night_receipt():
    r = _receipt()
    assert r["job"] == "P7_pit_universe_vintage"
    assert r["licence"] == "PRODUCT_EXPERIMENT"
    assert r["llm_spend_usd"] == 0.0
    assert r["written_utc"]
    assert r["state"] == "DONE", "a receipt still marked RUNNING means the job was killed"
    assert r["verdict"] and r["headline"]


def test_the_floor_is_the_repo_constant_not_a_literal():
    """A floor that exists twice is a floor that will disagree with itself."""
    from learner.evaluate import TRADABLE_DOLLAR_VOL

    from scripts.night_p7_pit_universe import _floor

    assert _floor() == TRADABLE_DOLLAR_VOL == 3_000_000.0
    r = _receipt()
    assert r["floor_median_dollar_volume"] == TRADABLE_DOLLAR_VOL
    assert r["floor_source"] == "learner.evaluate.TRADABLE_DOLLAR_VOL"


def test_parquet_columns_and_row_count_match_the_receipt():
    r = _receipt()
    v = _vintage()
    for col in ("month", "symbol", "first_bar", "last_bar",
                "median_dollar_vol_20d", "in_universe"):
        assert col in v.columns, f"the vintage is missing the {col!r} column"
    assert len(v) == r["parquet_rows"]
    assert v["symbol"].nunique() == r["symbols_considered"]
    assert v["month"].nunique() == r["months_total"]
    # one row per (month, symbol), no duplicates
    assert not v.duplicated(["month", "symbol"]).any()


def test_names_per_month_match_the_receipt():
    r = _receipt()
    v = _vintage()
    counts = v[v["in_universe"]].groupby("month")["symbol"].nunique().to_dict()
    for month, cell in r["per_month"].items():
        assert counts.get(month, 0) == cell["names"], (
            f"{month}: parquet has {counts.get(month, 0)} members, "
            f"receipt says {cell['names']}")


def test_enter_and_exit_counts_match_the_receipt():
    r = _receipt()
    v = _vintage()
    members = {m: set(g.loc[g["in_universe"], "symbol"])
               for m, g in v.groupby("month")}
    months = sorted(members)
    prev: set | None = None
    for m in months:
        cell = r["per_month"][m]
        cur = members[m]
        if prev is None:
            assert cell["entered"] == 0 and cell["exited"] == 0
        else:
            assert len(cur - prev) == cell["entered"], f"{m}: entered"
            assert len(prev - cur) == cell["exited"], f"{m}: exited"
        prev = cur


def test_the_liquidity_screen_is_read_before_the_month_it_governs():
    """PIT discipline: the as-of session is STRICTLY before the month's first."""
    r = _receipt()
    for month, cell in r["per_month"].items():
        asof = cell["liquidity_asof_session"]
        if asof is None:
            assert cell["names"] == 0, (
                f"{month} has {cell['names']} members with no liquidity history behind it")
            continue
        assert asof < cell["month_first_session"], (
            f"{month}: liquidity read on {asof}, which is not before "
            f"{cell['month_first_session']} -- that is a look-ahead")


def test_every_member_clears_the_floor_and_traded_through_its_month():
    r = _receipt()
    v = _vintage()
    floor = r["floor_median_dollar_volume"]
    inv = v[v["in_universe"]]
    assert (inv["median_dollar_vol_20d"] >= floor).all(), (
        "a member is below the floor it is supposed to have cleared")
    starts = {m: c["month_first_session"] for m, c in r["per_month"].items()}
    ends = {m: c["month_last_session"] for m, c in r["per_month"].items()}
    fb = inv["first_bar"].astype(str).str.slice(0, 10)
    lb = inv["last_bar"].astype(str).str.slice(0, 10)
    assert (fb <= inv["month"].map(starts)).all(), "a member was not listed yet"
    assert (lb >= inv["month"].map(ends)).all(), "a member had already stopped trading"


def test_headline_counts_are_in_the_headline():
    r = _receipt()
    s = r["survivorship"]
    head = r["headline"]
    for n in (r["parquet_rows"], r["symbols_considered"],
              r["names_first_gradable_month"], r["names_final_month"],
              s["in_first_vintage_absent_from_final"],
              r["symbols_that_stopped_trading_inside_the_window"]):
        assert f"{n:,}" in head or str(n) in head, (
            f"{n} is in the receipt body but not in its headline")


def test_survivorship_count_matches_the_membership_table():
    r = _receipt()
    v = _vintage()
    members = {m: set(g.loc[g["in_universe"], "symbol"])
               for m, g in v.groupby("month") if g["in_universe"].any()}
    months = sorted(members)
    first, final = months[0], months[-1]
    assert first == r["first_gradable_month"]
    assert final == r["final_month"]
    gone = members[first] - members[final]
    assert len(gone) == r["survivorship"]["in_first_vintage_absent_from_final"]
    ever = set().union(*members.values())
    assert len(ever - members[final]) == \
        r["survivorship"]["in_any_earlier_vintage_absent_from_final"]


def test_the_vintage_is_genuinely_point_in_time_in_at_least_one_pair():
    """IN an earlier month, OUT of a later one -- or the vintage repairs nothing.

    This is the whole point of the artefact. If it cannot be demonstrated the
    test REFUSES with the reason, because a green tick over a vintage that is
    the same 3,056 names every month would hide exactly the bias P6 refused to
    grade against.
    """
    v = _vintage()
    members = {m: set(g.loc[g["in_universe"], "symbol"])
               for m, g in v.groupby("month") if g["in_universe"].any()}
    months = sorted(members)
    if len(months) < 2:
        pytest.fail("REFUSED: fewer than two gradable vintages -- the membership "
                    "table cannot demonstrate any time asymmetry at all")
    pairs = [(a, b, s)
             for i, a in enumerate(months) for b in months[i + 1:]
             for s in (members[a] - members[b])]
    assert pairs, (
        "REFUSED: no symbol is in an earlier vintage and out of a later one. "
        "Every month holds the same names, which means the membership rule is "
        "inert and the bar source is itself survivor-screened -- the vintage "
        "does NOT fix the bias P6 refused to grade against.")
    a, b, sym = pairs[0]
    assert sym in members[a] and sym not in members[b]


def test_the_receipt_says_out_loud_whether_the_bar_source_is_survivor_screened():
    """A near-zero stopped-trading count is not a clean panel, it is a screened one."""
    r = _receipt()
    stopped = r["symbols_that_stopped_trading_inside_the_window"]
    n = r["symbols_considered"]
    expected = stopped <= max(3, 0.005 * n)
    assert r["bar_source_survivor_screened"] is expected, (
        f"{stopped} of {n} symbols stop trading inside the window, but the receipt "
        f"declares bar_source_survivor_screened={r['bar_source_survivor_screened']}")
    if r["bar_source_survivor_screened"]:
        assert "NOT repaired" in r["verdict"] or "UPPER bound" in r["verdict"], (
            "the receipt flags a survivor-screened bar source but its verdict does "
            "not warn the reader that survival bias remains")
