"""Guards for `learner.features_graph` -- the market-graph momentum family.

WHAT THESE TESTS ARE FOR
========================
Three failures are possible here and only one of them is visible without a
test:

1. **A silently empty graph.** A missing edge file that returns an empty frame
   produces all-NaN features, a clean join, and a confident negative result.
   The module must REFUSE, and the refusal must name the path it looked at.
2. **A guessed direction.** `customer/out` and `supplier/in` mean opposite
   things, and the reverse-implied edge (A's customer B means A is B's
   supplier) is where most of the coverage comes from. Getting the orientation
   backwards would not raise, would not change a row count, and would silently
   test the mirror image of the hypothesis.
3. **A leaky join.** The whole family is a lagged neighbourhood return. A
   forward-looking `merge_asof`, or a tolerance wide enough to carry a value
   forward across a quarter, would manufacture the effect the job is testing
   for.

Everything runs on synthetic frames, offline, in milliseconds. The two tests
that touch the real artefacts skip when the artefacts are absent -- a check
that did not run is reported as skipped, never as a pass.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from learner import features_graph as FG


# --------------------------------------------------------------- fixtures

def _edges() -> pd.DataFrame:
    """A hand-built edge frame covering every branch of the orientation map."""
    rows = [
        # A(1) says B(2) is our customer  -> B is A's cust, A is B's supp
        dict(subject_permno=1, counterparty_permno=2, type="customer", direction="out"),
        # C(3) says D(4) supplies us      -> D is C's supp, C is D's cust
        dict(subject_permno=3, counterparty_permno=4, type="supplier", direction="in"),
        # E(5) says F(6) is a competitor  -> symmetric
        dict(subject_permno=5, counterparty_permno=6, type="competitor", direction="mutual"),
        # G(7)/H(8) shared technology     -> symmetric, assoc
        dict(subject_permno=7, counterparty_permno=8, type="shared_technology",
             direction="mutual"),
        # UN-ORIENTABLE: a trade edge with no direction. Must be dropped, not guessed.
        dict(subject_permno=9, counterparty_permno=10, type="customer", direction="mutual"),
        # A self-loop that survived upstream: must not become a relation.
        dict(subject_permno=11, counterparty_permno=11, type="competitor",
             direction="mutual"),
    ]
    df = pd.DataFrame(rows)
    df["filing_date"] = pd.Timestamp("2016-02-15")
    df["date"] = pd.Timestamp("2016-06-30")
    df["confidence"] = 0.9
    df["same_sector"] = True
    return df


# ------------------------------------------------------------- the refusal

def test_missing_edge_file_refuses_and_names_the_path(tmp_path, monkeypatch):
    """No silent empty graph. The message must be actionable, not just angry."""
    missing = tmp_path / "nope" / "edge_instances.parquet"
    monkeypatch.setenv(FG.EDGE_SOURCE_ENV, str(missing))
    with pytest.raises(SystemExit) as ei:
        FG.load_edges()
    msg = str(ei.value)
    assert "REFUSED" in msg
    assert str(missing) in msg, "the refusal must name the path it actually looked at"
    assert FG.EDGE_SOURCE_ENV in msg, "the refusal must name the override"
    assert "MARKET-GRAPH-1" in msg, "absence of a local object is not evidence of absence"


def test_edge_source_honours_the_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv(FG.EDGE_SOURCE_ENV, str(tmp_path / "x.parquet"))
    assert FG.edge_source() == tmp_path / "x.parquet"
    monkeypatch.delenv(FG.EDGE_SOURCE_ENV)
    assert FG.edge_source() == FG.DEFAULT_EDGE_SOURCE


# ------------------------------------------------------------- orientation

def test_relation_table_orients_both_ways():
    """A's customer B means A is B's supplier. Both halves, or the ~100 permnos
    that never filed anything get no coverage at all."""
    rel, counts = FG.relation_table(_edges())
    got = {(int(r.subject), int(r.related), r.relation) for r in rel.itertuples()}
    assert (1, 2, "cust") in got, "B buys from A => B is A's customer"
    assert (2, 1, "supp") in got, "...therefore A is B's supplier"
    assert (3, 4, "supp") in got, "D supplies C => D is C's supplier"
    assert (4, 3, "cust") in got, "...therefore C is D's customer"
    # The mirror image must NOT be present -- that is the silent failure.
    assert (1, 2, "supp") not in got
    assert (2, 1, "cust") not in got


def test_symmetric_types_go_both_ways_and_into_the_right_class():
    rel, counts = FG.relation_table(_edges())
    got = {(int(r.subject), int(r.related), r.relation) for r in rel.itertuples()}
    assert (5, 6, "comp") in got and (6, 5, "comp") in got
    assert (7, 8, "assoc") in got and (8, 7, "assoc") in got


def test_unorientable_trade_edges_are_dropped_and_counted():
    """A guessed direction is the one error this family cannot detect later."""
    rel, counts = FG.relation_table(_edges())
    assert counts["unoriented_dropped"] == 1
    assert 9 not in set(rel["subject"]) and 10 not in set(rel["subject"])


def test_self_loops_never_become_relations():
    rel, _ = FG.relation_table(_edges())
    assert not (rel["subject"] == rel["related"]).any()


def test_relation_table_refuses_an_unmappable_vocabulary():
    e = _edges().iloc[:1].copy()
    e["type"] = "franchisee"
    e["direction"] = "sideways"
    with pytest.raises(SystemExit) as ei:
        FG.relation_table(e)
    assert "REFUSED" in str(ei.value)


# ----------------------------------------------------------------- the join

def _synthetic_features(dates, permnos) -> pd.DataFrame:
    idx = pd.MultiIndex.from_product([permnos, dates], names=["permno", "date"])
    f = pd.DataFrame(index=idx).reset_index()
    rng = np.random.default_rng(7)
    for c in FG.FEATURES:
        f[c] = rng.normal(size=len(f))
    for c in FG.COUNT_COLUMNS:
        f[c] = 3.0
    return f


def test_attach_is_backward_and_never_uses_a_future_row():
    """The one failure that would manufacture the effect being tested."""
    dates = pd.to_datetime(["2016-01-01", "2016-02-01", "2016-03-01"])
    feats = _synthetic_features(dates, [101])
    feats["graph_cust_mom_1m_ew"] = [10.0, 20.0, 30.0]
    panel = pd.DataFrame({
        "permno": [101, 101],
        "entry_date": pd.to_datetime(["2016-01-20", "2016-02-20"]),
    })
    joined, note = FG.attach(panel, feats)
    vals = joined.sort_values("entry_date")["graph_cust_mom_1m_ew"].tolist()
    assert vals == [10.0, 20.0], "a backward join takes the LAST row on or before entry_date"
    assert note["direction"].startswith("backward")


def test_attach_does_not_carry_a_stale_value_across_the_tolerance():
    dates = pd.to_datetime(["2016-01-01"])
    feats = _synthetic_features(dates, [101])
    panel = pd.DataFrame({"permno": [101], "entry_date": pd.to_datetime(["2016-06-15"])})
    joined, note = FG.attach(panel, feats)
    assert joined["graph_cust_mom_1m_ew"].isna().all(), (
        "a name whose graph went dark five months ago must get NaN, not a carry-forward")
    assert note["verdict"].startswith("THIN")


def test_attach_reports_a_match_rate_and_the_two_numbers_that_explain_it():
    """A 3% join and a 97% join produce the same shaped frame."""
    dates = pd.to_datetime(["2016-01-01", "2016-02-01"])
    feats = _synthetic_features(dates, [101, 102])
    panel = pd.DataFrame({
        "permno": [101, 102, 999, 999],
        "entry_date": pd.to_datetime(["2016-01-20", "2016-01-20",
                                      "2016-01-20", "2016-02-20"]),
    })
    joined, note = FG.attach(panel, feats)
    assert note["rows_in"] == note["rows_out"] == 4
    assert note["match_rate"]["graph_cust_mom_1m_ew"] == pytest.approx(0.5)
    # 999 is not in the graph at all: the ceiling has to say so.
    assert note["panel_share_on_a_permno_the_graph_covers"] == pytest.approx(0.5)
    assert note["panel_share_inside_the_graph_date_window"] == pytest.approx(1.0)
    assert note["ceiling"] == pytest.approx(0.5)


def test_attach_leaves_no_suffixed_columns_behind():
    dates = pd.to_datetime(["2016-01-01"])
    feats = _synthetic_features(dates, [101])
    panel = pd.DataFrame({"permno": [101], "entry_date": pd.to_datetime(["2016-01-20"]),
                          "date": pd.to_datetime(["2016-01-20"])})
    joined, _ = FG.attach(panel, feats)
    assert not [c for c in joined.columns if c.endswith("_gfeat")]


# ------------------------------------------------------------- bookkeeping

def test_features_and_families_agree():
    flat = [c for cols in FG.FAMILIES.values() for c in cols]
    assert list(FG.FEATURES) == flat
    assert len(set(flat)) == len(flat), "a column in two families would be ablated twice"
    for c in FG.FEATURES:
        assert FG.family_of(c) in FG.FAMILIES
    assert FG.family_of("not_a_feature") is None
    # The counts ride along on the join; they must never be TESTED as features.
    assert not set(FG.COUNT_COLUMNS) & set(FG.FEATURES)


def test_load_refuses_when_the_parquet_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(FG, "GRAPH_FEATURES", tmp_path / "absent.parquet")
    assert FG.available() is False
    with pytest.raises(SystemExit) as ei:
        FG.load()
    assert "REFUSED" in str(ei.value)


def test_sector_momentum_leaves_the_name_itself_out():
    panel = pd.DataFrame({
        "month": ["2016-01"] * 3,
        "sector": ["Tech"] * 3,
        "ret_1m": [0.10, 0.20, 0.30],
    })
    lto = FG._sector_momentum(panel)
    # Each row gets the mean of the OTHER two, never its own return.
    assert lto.tolist() == pytest.approx([0.25, 0.20, 0.15])


def test_sector_momentum_returns_nan_without_the_inputs():
    out = FG._sector_momentum(pd.DataFrame({"month": ["2016-01"]}))
    assert out.isna().all()


# ------------------------------------------- the real artefacts, if present

@pytest.mark.skipif(not FG.available(), reason="features_graph.parquet not built")
def test_built_table_is_point_in_time_and_non_empty():
    df = FG.load()
    assert len(df) > 0
    fm = pd.PeriodIndex(df["feature_month"].astype(str), freq="M")
    # The stamp is the day AFTER the aggregated month closes -- so the row can
    # never be read before the returns it summarises are realised.
    assert (pd.to_datetime(df["date"]) > fm.to_timestamp(how="end").normalize()
            - pd.Timedelta(days=1)).all()
    assert (pd.to_datetime(df["date"]) <= fm.to_timestamp(how="end").normalize()
            + pd.Timedelta(days=1)).all()
    for c in FG.FEATURES:
        assert df[c].notna().any(), f"{c} is empty on the built table"


@pytest.mark.skipif(not FG.available(), reason="features_graph receipt not built")
def test_receipt_carries_the_measured_coverage_window():
    """The roadmap said the edges 'reportedly' cover 2015-2024. A receipt that
    repeats the report is not a measurement."""
    rec = FG.receipt()
    cov = rec.get("coverage") or {}
    for k in ("filing_date_first", "filing_date_last", "feature_date_first",
              "feature_date_last", "feature_years", "long_panel_years",
              "edges_by_filing_year", "rows_by_year"):
        assert k in cov, f"the receipt must MEASURE {k}, not assert it"
    assert cov["feature_years"] < cov["long_panel_years"], (
        "a family that covers part of the panel must say so in its own receipt")
    assert rec.get("max_age_days") == FG.DEFAULT_MAX_AGE_DAYS
