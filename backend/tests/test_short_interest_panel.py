"""T1 — Book A's short-interest x turnover panel, on SYNTHETIC frames only.

Nothing here reads the 10M-row WRDS panel: a unit test that needs a
multi-gigabyte vendor pull on disk is a test that is green on one machine. What
is pinned is the four things the build can get wrong silently — the interval
join, the overlap dedupe, the PIT stamp, and the volume unit.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts import short_interest_panel as SIP


# --------------------------------------------------------------------------
# synthetic frames


def _si(rows):
    return pd.DataFrame(rows, columns=["gvkey", "iid", "shortint", "shortintadj",
                                       "datadate", "splitadjdate"])


def _links(rows):
    return pd.DataFrame(rows, columns=["gvkey", "permno", "linktype", "linkprim",
                                       "linkdt", "linkenddt"])


# --------------------------------------------------------------------------
# the dedupe


def test_overlap_dedupes_to_one_row_per_key_and_prefers_current():
    cur = _si([("001", "01", 100.0, 100.0, "2010-01-15", "2010-01-15")])
    leg = _si([("001", "01", 999.0, 999.0, "2010-01-15", "2010-01-15"),
               ("001", "01", 50.0, 50.0, "1980-01-15", "1980-01-15")])
    out, stats = SIP.dedupe_shortint(cur, leg)
    assert len(out) == 2
    assert stats["overlap_rows_dropped"] == 1
    on_overlap = out[out["datadate"] == pd.Timestamp("2010-01-15")]
    assert float(on_overlap["shortint"].iloc[0]) == 100.0
    assert on_overlap["source_file"].iloc[0] == "current"
    # and the pre-overlap legacy row survives -- the dedupe is not a filter
    assert float(out[out["datadate"] == pd.Timestamp("1980-01-15")]
                 ["shortint"].iloc[0]) == 50.0


def test_primary_issue_keeps_the_lowest_numeric_iid_and_counts_the_rest():
    df, _ = SIP.dedupe_shortint(
        _si([("001", "90", 7.0, 7.0, "2010-01-15", "2010-01-15"),
             ("001", "01", 3.0, 3.0, "2010-01-15", "2010-01-15"),
             ("002", "01", 5.0, 5.0, "2010-01-15", "2010-01-15")]),
        _si([]))
    kept, stats = SIP.pick_primary_issue(df)
    assert len(kept) == 2
    assert set(kept["iid"]) == {"01"}
    assert stats["gvkey_date_cells_with_multiple_issues"] == 1
    assert stats["dropped_non_primary_issues"] == 1


# --------------------------------------------------------------------------
# the interval join


def test_interval_join_respects_linkdt_and_linkenddt():
    si, _ = SIP.dedupe_shortint(
        _si([("001", "01", 10.0, 10.0, "1979-06-30", "1979-06-30"),   # inside
             ("001", "01", 10.0, 10.0, "1990-06-30", "1990-06-30")]),  # after
        _si([]))
    link = _links([("001", 10001.0, "LC", "P", "1978-01-01", "1980-12-31")])
    out, stats = SIP.link_permno(si, link)
    assert len(out) == 1
    assert out["permno"].iloc[0] == 10001
    assert stats["rows_unlinked_dropped"] == 1
    assert stats["match_rate"] == 0.5


def test_a_null_linkenddt_is_an_open_link():
    si, _ = SIP.dedupe_shortint(
        _si([("001", "01", 10.0, 10.0, "2024-06-30", "2024-06-30")]), _si([]))
    link = _links([("001", 10001.0, "LU", "P", "1978-01-01", None)])
    out, _ = SIP.link_permno(si, link)
    assert len(out) == 1 and out["permno"].iloc[0] == 10001


def test_non_link_types_are_excluded_by_name():
    si, _ = SIP.dedupe_shortint(
        _si([("001", "01", 10.0, 10.0, "2010-06-30", "2010-06-30")]), _si([]))
    link = _links([("001", 10001.0, "NR", "P", "1978-01-01", None)])
    out, stats = SIP.link_permno(si, link)
    assert len(out) == 0
    assert stats["rows_unlinked_dropped"] == 1


def test_a_primary_link_wins_over_a_co_link_on_the_same_interval():
    si, _ = SIP.dedupe_shortint(
        _si([("001", "01", 10.0, 10.0, "2010-06-30", "2010-06-30")]), _si([]))
    link = _links([("001", 20002.0, "LC", "C", "1978-01-01", None),
                   ("001", 10001.0, "LC", "P", "1978-01-01", None)])
    out, _ = SIP.link_permno(si, link)
    assert len(out) == 1 and out["permno"].iloc[0] == 10001


# --------------------------------------------------------------------------
# PIT


def test_observed_at_is_strictly_after_datadate_by_the_measured_lag():
    dd = pd.Series(pd.to_datetime(["2010-01-15", "2010-06-30"]))
    obs = SIP.observed_at(dd)
    assert (obs > dd).all()
    assert (obs - dd).dt.days.tolist() == [SIP.PUBLICATION_LAG_DAYS] * 2


def test_the_built_frame_carries_a_pit_stamp_after_every_settlement_date():
    dates = pd.bdate_range("2019-11-01", "2020-01-31")
    dsf = pd.DataFrame({
        "permno": 10001, "date": dates, "prc": 10.0,
        "vol": 1_000.0, "shrout": 1_000.0,
    })
    si, _ = SIP.dedupe_shortint(
        _si([("001", "01", 50_000.0, 50_000.0, "2020-01-15", "2020-01-15")]),
        _si([]))
    si["permno"] = 10001
    frame = SIP.build_frame(si, SIP.crsp_features(dsf))
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["observed_at"] > row["datadate"]
    # 50,000 short / (1,000 * 1,000 shares) = 5%
    assert row["si_ratio"] == pytest.approx(0.05)
    # 21 sessions x 1,000 shares / 1,000,000 shares = 2.1%
    assert row["turnover_21d"] == pytest.approx(0.021)
    assert bool(row["turnover_unadjusted_for_venue"]) is True


def test_a_settlement_date_with_no_nearby_session_is_dropped_not_stale_joined():
    dates = pd.bdate_range("2019-01-01", "2019-03-31")
    dsf = pd.DataFrame({"permno": 10001, "date": dates, "prc": 10.0,
                        "vol": 1_000.0, "shrout": 1_000.0})
    si, _ = SIP.dedupe_shortint(
        _si([("001", "01", 50_000.0, 50_000.0, "2020-01-15", "2020-01-15")]),
        _si([]))
    si["permno"] = 10001
    assert SIP.build_frame(si, SIP.crsp_features(dsf)).empty


def test_a_partial_window_produces_no_turnover_rather_than_a_small_one():
    dates = pd.bdate_range("2020-01-02", "2020-01-10")        # 7 sessions < 21
    dsf = pd.DataFrame({"permno": 10001, "date": dates, "prc": 10.0,
                        "vol": 1_000.0, "shrout": 1_000.0})
    si, _ = SIP.dedupe_shortint(
        _si([("001", "01", 50_000.0, 50_000.0, "2020-01-10", "2020-01-10")]),
        _si([]))
    si["permno"] = 10001
    assert SIP.build_frame(si, SIP.crsp_features(dsf)).empty


# --------------------------------------------------------------------------
# the unit


def test_the_volume_unit_check_accepts_raw_shares():
    dsf = pd.DataFrame({"permno": 1, "date": pd.bdate_range("2020-01-01", periods=50),
                        "vol": 5_000.0, "shrout": 1_000.0})   # 0.5%/day
    v = SIP.verify_volume_unit(dsf)
    assert v["unit"] == "raw shares"
    assert v["median_daily_turnover"] == pytest.approx(0.005)


def test_the_volume_unit_check_refuses_round_lots():
    dsf = pd.DataFrame({"permno": 1, "date": pd.bdate_range("2020-01-01", periods=50),
                        "vol": 500_000.0, "shrout": 1_000.0})  # 50%/day
    v = SIP.verify_volume_unit(dsf)
    assert v["unit"] == "UNKNOWN"
    assert "REFUSED" in v["verdict"]


def test_winsorise_clips_the_low_float_outlier():
    s = pd.Series([0.1] * 98 + [0.001, 40.0])
    w = SIP.winsorise(s)
    assert float(w.max()) < 40.0
    assert float(w.min()) > 0.001


def test_the_build_refuses_when_the_vendor_panel_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(SIP, "wrds_dir", lambda: tmp_path)
    with pytest.raises(FileNotFoundError, match="not on this machine"):
        SIP.build(start=2020, end=2020, out=tmp_path / "out", write=False)
