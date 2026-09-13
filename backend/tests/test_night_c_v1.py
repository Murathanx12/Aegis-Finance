"""T4 — Book C v1: the same book, the conditioner the cited paper uses.

`announcement_window_sign` itself is already pinned by
`test_night_first_books_replay.py` (the three-session window, the KNOWABLE
month, the dropped off-tape window, the later of two announcements in a month).
What is new here is the JOIN that feeds it and the ASSEMBLY that reads it, and
each test below is a way one of those could be convincingly wrong:

  * an IBES ticker is REUSED across companies. A join that ignored
    `link_ibes_crsp`'s own `sdate`/`edate` window would put one company's
    earnings on another company's tape, and every downstream number would still
    be arithmetically correct;
  * `vs_v0` is REPORTED and never deciding, and must say so in the payload
    rather than only in a docstring;
  * the family Holm corrects against FOUR even when three of the four legs have
    no p-value on this checkout.

Every date is derived from `today`.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts import night_c_v1 as V1


def _write_ann(tmp_path, rows, links):
    """A synthetic IBES announcement table and its permno link, on disk."""
    d = tmp_path / "wrds"
    (d / "bulk").mkdir(parents=True)
    pd.DataFrame(rows, columns=["ticker", "anndats", "actdats", "pdicity",
                                "measure"]).to_parquet(
        d / "bulk" / "ibes__act_epsus.parquet")
    pd.DataFrame(links, columns=["ticker", "permno", "sdate", "edate",
                                 "ncusip", "score"]).to_parquet(
        d / "link_ibes_crsp.parquet")
    return d


def test_a_ticker_reused_across_companies_does_not_cross_the_link_window(
        tmp_path, monkeypatch):
    """The defect this test exists for is silent: the wrong permno's tape is
    still a tape, and the sign it produces is still a sign."""
    y = pd.Timestamp.today().year - 2
    d = _write_ann(
        tmp_path,
        [("AAA", pd.Timestamp(y, 3, 10), pd.Timestamp(y, 3, 10), "QTR", "EPS"),
         ("AAA", pd.Timestamp(y, 9, 10), pd.Timestamp(y, 9, 10), "QTR", "EPS")],
        [("AAA", 111, pd.Timestamp(y, 1, 1), pd.Timestamp(y, 6, 30), "x", 1.0),
         ("AAA", 222, pd.Timestamp(y, 7, 1), pd.Timestamp(y, 12, 31), "x", 1.0)])
    monkeypatch.setattr(V1, "wrds_dir", lambda: d)
    got = V1.load_announcement_dates(y, y)
    by_date = {pd.Timestamp(r.anndats): int(r.permno)
               for r in got.itertuples(index=False)}
    assert by_date == {pd.Timestamp(y, 3, 10): 111,
                       pd.Timestamp(y, 9, 10): 222}


def test_an_announcement_outside_every_link_row_is_dropped_not_nearest_matched(
        tmp_path, monkeypatch):
    y = pd.Timestamp.today().year - 2
    d = _write_ann(
        tmp_path,
        [("AAA", pd.Timestamp(y, 3, 10), pd.Timestamp(y, 3, 10), "QTR", "EPS")],
        [("AAA", 111, pd.Timestamp(y, 6, 1), pd.Timestamp(y, 12, 31), "x", 1.0)])
    monkeypatch.setattr(V1, "wrds_dir", lambda: d)
    assert len(V1.load_announcement_dates(y, y)) == 0


def test_only_quarterly_eps_announcements_are_read(tmp_path, monkeypatch):
    """The probe receipt names `pdicity == 'QTR'` and `measure == 'EPS'`. An
    ANNual row is the same company's same fiscal year and would double-count the
    quarter that closed it."""
    y = pd.Timestamp.today().year - 2
    d = _write_ann(
        tmp_path,
        [("AAA", pd.Timestamp(y, 3, 10), pd.Timestamp(y, 3, 10), "QTR", "EPS"),
         ("AAA", pd.Timestamp(y, 4, 10), pd.Timestamp(y, 4, 10), "ANN", "EPS"),
         ("AAA", pd.Timestamp(y, 5, 10), pd.Timestamp(y, 5, 10), "QTR", "EPSPAR")],
        [("AAA", 111, pd.Timestamp(y, 1, 1), pd.Timestamp(y, 12, 31), "x", 1.0)])
    monkeypatch.setattr(V1, "wrds_dir", lambda: d)
    got = V1.load_announcement_dates(y, y)
    assert len(got) == 1
    assert pd.Timestamp(got["anndats"].iloc[0]) == pd.Timestamp(y, 3, 10)


def test_the_loader_refuses_by_name_rather_than_falling_back_to_v0(tmp_path,
                                                                  monkeypatch):
    """A v1 read that quietly used v0's revision count would be §8's forbidden
    substitution, made invisible."""
    monkeypatch.setattr(V1, "wrds_dir", lambda: tmp_path / "nope")
    with pytest.raises(V1.AnnouncementDatesUnavailable, match="does NOT fall back"):
        V1.load_announcement_dates(2020, 2021)


def test_known_date_travels_because_the_pit_rule_needs_both_dates(tmp_path,
                                                                 monkeypatch):
    """`actdats - anndats` has a 95th percentile of 91 days. A loader that
    dropped `actdats` would make the tail of that lag invisible and the sign
    would land in a month nobody could have known it in."""
    y = pd.Timestamp.today().year - 2
    d = _write_ann(
        tmp_path,
        [("AAA", pd.Timestamp(y, 3, 10), pd.Timestamp(y, 6, 9), "QTR", "EPS")],
        [("AAA", 111, pd.Timestamp(y, 1, 1), pd.Timestamp(y, 12, 31), "x", 1.0)])
    monkeypatch.setattr(V1, "wrds_dir", lambda: d)
    got = V1.load_announcement_dates(y, y)
    assert list(got.columns) == ["permno", "anndats", "known_date"]
    assert pd.Timestamp(got["known_date"].iloc[0]) == pd.Timestamp(y, 6, 9)


def test_vs_v0_is_reported_never_deciding_and_carries_the_v0_receipt():
    cell = {"primary_registered_construction":
            {"result": {"mean_excess_net_monthly": 0.005, "nw_lag2_t": 2.5,
                        "n_blocks": 350}}}
    got = V1.vs_v0_block(cell, cell)
    assert got["status"] == "REPORTED_NEVER_DECIDING"
    assert got["v0_receipt"].endswith("C_floor10m_run02.json")
    assert got["primary_floor"]["v0_mean_excess_net_monthly"] == 0.002438
    assert got["primary_floor"]["delta_mean_v1_minus_v0"] == pytest.approx(0.002562)
    # The two reads cover different name-months, so the delta is a difference of
    # two reads and the payload has to say so rather than implying a paired test.
    assert "not a paired test" in got["why"]


def test_the_family_holm_corrects_against_four_with_no_efg_receipt(monkeypatch):
    from scripts import night_books_efg_replay as EFG

    monkeypatch.setattr(EFG, "find_run_receipt", lambda *, smoke=False: None)
    block = V1.family_holm_block(0.01)
    assert block["declared_family_size"] == 4
    assert block["per_leg"][V1.BOOK]["holm_alpha"] == pytest.approx(0.0125)
    assert sorted(block["legs_without"]) == [
        "forecast_dispersion_v0", "qmj_quality_tilt_v0", "seasonality_11_20_v0"]
    assert "still against four" in block["note_on_completeness"]


def test_c_v1_is_the_fourth_declared_member_of_the_09_13_family():
    from scripts.night_books_efg_replay import DECLARED_FAMILY, FAMILY

    assert V1.FAMILY == FAMILY == "NIGHT_JOB_BOOKS_2026_09_13"
    assert V1.BOOK in DECLARED_FAMILY
    assert len(DECLARED_FAMILY) == 4


def test_the_v1_book_id_and_floors_are_v0s_because_only_the_input_moved():
    from scripts.night_c_falsifiers import (
        BOOK_ID as V0_BOOK_ID, K as V0_K, SECONDARY_FLOOR_USD as V0_SECOND,
    )

    assert V1.BOOK_ID == V0_BOOK_ID
    assert V1.K == V0_K == 30
    assert V1.SECONDARY_FLOOR_USD == V0_SECOND == 10_000_000.0


def test_the_job_is_registered_in_the_night_factory():
    from scripts import night_factory_jobs as NFJ
    assert "C_v1" in NFJ.JOBS
    assert "B_books_efg_replay" in NFJ.JOBS
    # Neither checkpoints anything, so claiming either set would be a promise
    # the scripts do not keep.
    assert "C_v1" not in NFJ.RESUMABLE
    assert "B_books_efg_replay" not in NFJ.RESUMABLE


def test_the_three_new_drafts_declare_the_new_family():
    from pathlib import Path

    for name in ("TRIAL-DRAFT-E-quality-minus-junk-v0.md",
                 "TRIAL-DRAFT-F-calendar-seasonality-v0.md",
                 "TRIAL-DRAFT-G-forecast-dispersion-v0.md"):
        f = Path("docs/TRIALS") / name
        assert f.is_file(), name
        text = f.read_text(encoding="utf-8")
        assert V1.FAMILY in text, name
        # Every one of them carries the clause Book C had to add by amendment.
        assert "<= 0" in text, f"{name} does not carry the primary <= 0 clause"
