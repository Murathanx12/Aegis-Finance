"""VALIDATION of `learner.long_panel` -- the 1999-2024 panel's PIT invariants.

WHY THESE FOUR AND NOT A ROW COUNT
==================================
The long panel exists because the 12-year panel could not answer the question
it was asked: at the Sharpe the best learner cell showed, t = 2 needs 16.1 years
of out-of-sample months and the panel had 7.0. Extending the window buys the
missing years -- and it also multiplies by two the number of places a leak can
hide, because everything that was checked on 2013-2024 is now being asserted of
a window nobody has looked at.

Four invariants, each of which would silently inflate a result if it broke:

1. **No row trades before its consensus was published** (`entry_date >=
   vintage`). A single row the other way is information acted on before it was
   public -- the first of the four things that never relax.
2. **A 12-month target that could not have matured is NULL.** If the panel's own
   edge is inside the horizon and the target is filled anyway, the model is
   trained on the future. `dataset.build` nulls it via `_horizon_ok`; this
   asserts the result rather than the intention.
3. **`era` partitions the panel** with no `out_of_eras` rows. The weekend's
   verdict rule counts signs in eras; a row in no era is a row that no verdict
   sees, and `era_of` returns the string `"out_of_eras"` rather than raising.
4. **`ratio` is NULL wherever `hygiene_ok` is False.** `dataset.build` nulls
   ratio/upside/log_ratio on hygiene failure and keeps the raw value in
   `ratio_unhygienic` for audit only. A ratio that survived hygiene is a feature
   built on a number the panel has already declared unreadable.

SKIPPING, LOUDLY. The parquet is a 418 MB build artefact and is not in the
repo. Where it is absent every test here SKIPS with the reason printed -- a
check that did not run is not a check that passed, and the skip says so rather
than reporting green. Only named columns are read, so the file cost is a few
hundred milliseconds rather than the whole table.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from learner import long_panel as LP

pytestmark = pytest.mark.skipif(
    not LP.available(),
    reason=(f"the long panel is not built on this machine ({LP.LONG_TABLE}); "
            "these PIT invariants DID NOT RUN. Build it with "
            "`python -m learner.long_panel --build`."))


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    """Only the columns the invariants need."""
    cols = ["permno", "month", "vintage", "entry_date", "era", "hygiene_ok",
            "ratio", "ratio_unhygienic", "upside", "log_ratio",
            "mat_date_12m", "mat_date_1m", "excess_vw_12m", "excess_vw_1m",
            "fwd_12m", "fwd_1m"]
    import pyarrow.parquet as pq
    present = set(pq.ParquetFile(LP.LONG_TABLE).schema_arrow.names)
    missing = [c for c in cols if c not in present]
    assert not missing, f"the long panel is missing columns this test needs: {missing}"
    df = pd.read_parquet(LP.LONG_TABLE, columns=cols)
    df["vintage"] = pd.to_datetime(df["vintage"])
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    return df


# ------------------------------------------- 1. the trade cannot precede the
#                                                consensus it was made on


def test_no_row_trades_before_its_consensus_was_published(panel):
    """`entry_date >= vintage`, with no exceptions and no NaT on either side."""
    assert panel["vintage"].notna().all(), "a row carries no consensus date"
    assert panel["entry_date"].notna().all(), "a row carries no entry date"

    early = panel[panel["entry_date"] < panel["vintage"]]
    assert len(early) == 0, (
        f"{len(early):,} of {len(panel):,} rows trade BEFORE their consensus vintage. "
        f"worst gap {(early['vintage'] - early['entry_date']).max()}; "
        f"first offenders:\n{early.head(5)[['permno', 'vintage', 'entry_date']]}")


def test_the_publication_gap_is_short_and_forward(panel):
    """Not just non-negative: the entry must follow the vintage closely enough
    to be the same information state. A row entered a year after its consensus
    is a stale opinion, not a point-in-time one."""
    gap = (panel["entry_date"] - panel["vintage"]).dt.days
    assert gap.min() >= 0
    assert gap.max() <= 45, (
        f"a row entered {gap.max()} days after its consensus vintage; the panel's "
        "information state is monthly, so a gap beyond ~45 days is a join error")
    assert float(gap.median()) <= 7


# --------------------------- 2. an unmatured 12-month target must be missing


def test_a_twelve_month_target_that_could_not_have_matured_is_null(panel):
    """The panel's own data edge bounds every realised target.

    Derived from the panel, never written down: the last maturity date the table
    contains is the last day of tape the build could see. Any row whose entry is
    within twelve months of that edge cannot have a matured 12-month return, and
    must carry NULL rather than a number.
    """
    edge = panel["mat_date_12m"].max()
    assert pd.notna(edge), "the panel carries no 12-month maturity dates at all"

    matured = panel["excess_vw_12m"].notna()
    assert matured.any(), "no row has a 12-month target -- the column is dead"

    # every matured row must carry a maturity date, and it must be on the tape
    assert panel.loc[matured, "mat_date_12m"].notna().all(), (
        "a 12-month excess exists on a row with no maturity date -- the target was "
        "filled without a date to justify it")
    assert (panel.loc[matured, "mat_date_12m"] <= edge).all()
    assert (panel.loc[matured, "mat_date_12m"] > panel.loc[matured, "entry_date"]).all(), (
        "a 12-month target matured on or before the day the money moved")

    # and nothing inside the last twelve months of tape may be matured
    cutoff = edge - pd.DateOffset(months=12)
    inside = panel[panel["entry_date"] > cutoff]
    assert len(inside) > 0, (
        f"no rows within 12 months of the panel edge {edge.date()} -- this test would "
        "be vacuous")
    leaked = int(inside["excess_vw_12m"].notna().sum())
    assert leaked == 0, (
        f"{leaked:,} of {len(inside):,} rows entered after {cutoff.date()} carry a "
        f"12-month target, but the panel's tape ends {edge.date()}. That target was "
        "not observable and the model would be trained on the future.")


def test_the_maturity_gap_matches_the_horizon_it_claims(panel):
    """A `shift(-n)` moves n ROWS, not n sessions: a thinly traded name can
    advance years in twelve rows. Every matured 12-month row's realised gap must
    look like twelve months."""
    m = panel["excess_vw_12m"].notna()
    gap = (panel.loc[m, "mat_date_12m"] - panel.loc[m, "entry_date"]).dt.days
    assert gap.min() >= 1
    assert float(gap.median()) == pytest.approx(365, abs=45)
    assert gap.max() <= 550, (
        f"a 'twelve-month' target matured {gap.max()} days after entry -- that is the "
        "rows-vs-sessions trap, not a horizon")


def test_the_one_month_target_matures_sooner_than_the_twelve_month_one(panel):
    """A cheap consistency check that would catch a horizon swapped in the
    target block: the 1m maturity must never come AFTER the 12m one.

    Equality is legal and is not a bug: a name that dies inside the first month
    has both horizons filled at its delisting date (`dataset.build` lets a
    delisted row mature early, `gap_days >= 1`). So the invariant is `<=`, plus
    the requirement that every equality is explained by a delisting fill --
    which is the part that would actually catch a swapped horizon, since a
    swap would produce equalities on live names.
    """
    cols = ["mat_date_1m", "mat_date_12m", "delisting_filled_12m"]
    d = pd.read_parquet(LP.LONG_TABLE, columns=cols)
    both = d["mat_date_1m"].notna() & d["mat_date_12m"].notna()
    assert both.any()

    later = d.loc[both, "mat_date_1m"] > d.loc[both, "mat_date_12m"]
    assert not later.any(), (
        f"{int(later.sum()):,} rows have the ONE-month target maturing after the "
        "twelve-month one -- the horizons are swapped")

    same = d.loc[both, "mat_date_1m"] == d.loc[both, "mat_date_12m"]
    unexplained = int((same & ~d.loc[both, "delisting_filled_12m"].astype(bool)).sum())
    assert unexplained == 0, (
        f"{unexplained:,} rows share a maturity date across the 1m and 12m horizons "
        "WITHOUT a delisting fill to explain it -- a live name cannot mature both "
        "horizons on the same day")


# --------------------------------------------- 3. the era column partitions


def test_the_era_column_partitions_the_panel(panel):
    """Every row is in exactly one declared era; none is in `out_of_eras`."""
    labels = set(panel["era"].astype(str).unique())
    declared = {name for name, _lo, _hi in LP.ERAS}

    assert "out_of_eras" not in labels, (
        f"{int((panel['era'].astype(str) == 'out_of_eras').sum()):,} rows fall outside "
        f"{sorted(declared)} -- a row in no era is a row no verdict counts")
    assert labels <= declared, f"unexpected era labels: {sorted(labels - declared)}"
    assert labels == declared, f"an era has no rows at all: {sorted(declared - labels)}"
    assert panel["era"].notna().all()
    assert int(panel.groupby("era", observed=True).size().sum()) == len(panel)


def test_the_era_label_is_derived_from_entry_date_not_vintage(panel):
    """A row whose consensus is dated December and which trades in January
    belongs to the era it was EXPOSED in. Asserted by recomputing the label from
    `entry_date` for the whole panel."""
    want = pd.to_datetime(panel["entry_date"]).dt.year.map(LP.era_of)
    assert (panel["era"].astype(str) == want).all(), (
        f"{int((panel['era'].astype(str) != want).sum()):,} rows carry an era that is "
        "not the era of their entry_date")


def test_the_era_boundaries_are_contiguous_and_cover_the_window():
    """The declared eras themselves, independently of any data: no gap, no
    overlap, and they span the panel's window."""
    bounds = [(lo, hi) for _n, lo, hi in LP.ERAS]
    assert bounds == sorted(bounds)
    for (_lo1, hi1), (lo2, _hi2) in zip(bounds, bounds[1:]):
        assert lo2 == hi1 + 1, f"era boundary gap or overlap at {hi1}/{lo2}"
    assert bounds[0][0] == LP.LONG_START
    assert bounds[-1][1] == LP.LONG_END
    assert LP.era_of(LP.LONG_START - 1) == "out_of_eras"
    assert LP.era_of(LP.LONG_END + 1) == "out_of_eras"


def test_every_era_carries_real_tape(panel):
    """An era with a handful of rows is not an era the verdict rule can count a
    sign in. Print the counts rather than characterise them."""
    counts = panel.groupby("era", observed=True).agg(
        rows=("permno", "size"), permnos=("permno", "nunique"),
        months=("month", "nunique"))
    for era, row in counts.iterrows():
        assert row["months"] >= 60, f"{era} has only {row['months']} months of tape"
        assert row["permnos"] >= 500, f"{era} has only {row['permnos']} names"


# ------------------------- 4. ratio is NULL wherever hygiene_ok is False


def test_ratio_is_null_wherever_hygiene_failed(panel):
    """`dataset.build` nulls ratio/upside/log_ratio on hygiene failure. A
    surviving value is a feature built on a number the panel already declared
    unreadable -- the +400% stale-target band, back in the model."""
    bad = ~panel["hygiene_ok"].astype(bool)
    assert bad.any(), "no row fails hygiene -- this test would be vacuous"

    for col in ("ratio", "upside", "log_ratio"):
        if col not in panel.columns:
            continue
        survivors = int(panel.loc[bad, col].notna().sum())
        assert survivors == 0, (
            f"{survivors:,} of {int(bad.sum()):,} hygiene-failing rows carry a non-null "
            f"`{col}`")


def test_the_unhygienic_ratio_is_kept_for_audit_and_only_there(panel):
    """The mirror of the rule: the raw value must survive in
    `ratio_unhygienic` on exactly the failing rows and nowhere else. If it were
    populated on clean rows too, a coalesce would silently make it a feature."""
    bad = ~panel["hygiene_ok"].astype(bool)
    assert panel.loc[~bad, "ratio_unhygienic"].notna().sum() == 0, (
        "`ratio_unhygienic` is populated on rows that PASSED hygiene -- it is an audit "
        "column and must exist only where `ratio` does not")
    assert panel.loc[bad, "ratio_unhygienic"].notna().any(), (
        "`ratio_unhygienic` is empty on every failing row -- the audit trail the "
        "early-era share-basis gate reads does not exist")
    # and the two never coexist on one row
    assert int((panel["ratio"].notna() & panel["ratio_unhygienic"].notna()).sum()) == 0


def test_hygiene_passing_rows_do_carry_a_ratio(panel):
    """The other direction, so the invariant cannot be satisfied by nulling
    `ratio` everywhere."""
    ok = panel["hygiene_ok"].astype(bool)
    rate = float(panel.loc[ok, "ratio"].notna().mean())
    assert rate > 0.99, (
        f"only {rate:.1%} of hygiene-passing rows carry a ratio -- the column is being "
        "nulled by something other than hygiene")


# ------------------------------------------------ the panel is what it claims


def test_the_panel_covers_the_window_and_the_schema_it_declares(panel):
    """Window and size, derived from the table, not asserted from a handoff."""
    assert panel["entry_date"].min().year == LP.LONG_START
    assert panel["entry_date"].max().year == LP.LONG_END
    assert panel["month"].nunique() >= 12 * (LP.LONG_END - LP.LONG_START)
    assert len(panel) > 500_000


def test_coverage_by_year_reports_every_year_in_the_window(panel):
    """The receipt section that replaces the sentence "coverage is thinner
    pre-2004" with a number must actually have a row per year."""
    rows = LP.coverage_by_year(panel.assign(coverage=np.nan, close=np.nan))
    years = [r["year"] for r in rows]
    assert years == sorted(years)
    assert set(years) == set(range(LP.LONG_START, LP.LONG_END + 1)), (
        f"coverage_by_year skipped {sorted(set(range(LP.LONG_START, LP.LONG_END + 1)) - set(years))}")
    for r in rows:
        assert r["name_months"] > 0
        assert r["era"] != "out_of_eras"
        assert 0.0 <= r["hygiene_pass_rate"] <= 1.0
