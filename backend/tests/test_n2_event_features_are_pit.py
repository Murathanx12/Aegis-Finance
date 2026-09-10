"""N2's event features must not see their own month (roadmap section 10.6).

`scripts/night_n2_learner_v3` attaches, to every (permno, month) row of the
monthly panel, what that company's most recent earnings PRINT did. Two ways
that goes wrong silently, both of which have already cost this repo a result:

* attaching an announcement dated ON the panel row's entry date -- the print
  may land after the close the panel enters at, so it is not knowable;
* ranking a reaction against the full sample or the calendar month it sits in,
  which is the look-ahead that halved R4's spread when it was corrected on
  2026-09-08 (`feedback_a_within_month_rank_is_a_look_ahead...`).

These are unit tests over synthetic frames, so they run offline in the fast
suite and do not need the CRSP or IBES parquets on the checkout.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

n2 = pytest.importorskip("scripts.night_n2_learner_v3")


def test_trailing_percentile_uses_only_the_past():
    """A value's percentile must not move when a LATER value is appended."""
    rng = np.random.default_rng(7)
    dates = pd.to_datetime(pd.date_range("2010-01-01", periods=200, freq="D")).to_numpy()
    vals = rng.normal(size=200)
    full = n2.trailing_pct(dates, vals, days=90)
    half = n2.trailing_pct(dates[:120], vals[:120], days=90)
    a, b = full[:120], half
    both = np.isfinite(a) & np.isfinite(b)
    assert both.sum() > 30, "the fixture must produce enough graded rows to test"
    assert np.allclose(a[both], b[both]), "a percentile changed when future rows were added"


def test_trailing_percentile_refuses_a_thin_pool():
    """Fewer than 30 prints in the window is not a percentile; it must be NaN."""
    dates = pd.to_datetime(pd.date_range("2010-01-01", periods=10, freq="D")).to_numpy()
    out = n2.trailing_pct(dates, np.arange(10, dtype="float64"), days=90)
    assert np.isnan(out).all()


def _tiny_tape(tmp_path, name: str, days: list[str]):
    ev = pd.DataFrame({"permno": [1] * len(days),
                       "anndats": pd.to_datetime(days),
                       "reaction_01": np.linspace(-0.1, 0.1, len(days)),
                       "suescore": np.linspace(-2, 2, len(days))})
    p = tmp_path / name
    ev.to_parquet(p, index=False)
    return p


def test_an_announcement_on_the_entry_date_is_not_attached(tmp_path):
    """`allow_exact_matches=False`: a print on the entry date is not knowable."""
    tape = _tiny_tape(tmp_path, "ev.parquet", ["2010-01-20", "2010-02-15"])
    panel = pd.DataFrame({"permno": [1, 1], "month": ["2010-01", "2010-02"],
                          "entry_date": pd.to_datetime(["2010-01-20", "2010-02-20"])})
    out = n2.build_event_features(tape, panel, "test",
                                  ["permno", "anndats", "reaction_01", "suescore"])
    row_jan = out[out["month"] == "2010-01"].iloc[0]
    row_feb = out[out["month"] == "2010-02"].iloc[0]
    assert pd.isna(row_jan["ev_reaction"]), "the 01-20 print was attached to the 01-20 entry"
    assert not pd.isna(row_feb["ev_reaction"]), "the 02-15 print should reach the 02-20 entry"
    assert row_feb["ev_days_since"] == 5


def test_a_future_announcement_is_never_attached(tmp_path):
    tape = _tiny_tape(tmp_path, "ev2.parquet", ["2010-06-01"])
    panel = pd.DataFrame({"permno": [1], "month": ["2010-03"],
                          "entry_date": pd.to_datetime(["2010-03-15"])})
    out = n2.build_event_features(tape, panel, "test",
                                  ["permno", "anndats", "reaction_01", "suescore"])
    assert pd.isna(out.iloc[0]["ev_reaction"]), "a June print reached a March row"


def test_a_stale_print_is_blanked_not_carried(tmp_path):
    """A print older than 400 days is not news, and must not be learned as one."""
    tape = _tiny_tape(tmp_path, "ev3.parquet", ["2008-01-10"])
    panel = pd.DataFrame({"permno": [1], "month": ["2010-03"],
                          "entry_date": pd.to_datetime(["2010-03-15"])})
    out = n2.build_event_features(tape, panel, "test",
                                  ["permno", "anndats", "reaction_01", "suescore"])
    assert pd.isna(out.iloc[0]["ev_reaction"])
    assert out.iloc[0]["ev_days_since"] > 400, "staleness itself stays readable"


def test_the_control_carries_the_same_columns_as_the_treatment(tmp_path, monkeypatch):
    """`v3 - control` must measure the earnings print, not the column count."""
    a = _tiny_tape(tmp_path, "a.parquet", ["2010-01-10"])
    b = _tiny_tape(tmp_path, "b.parquet", ["2010-01-10"])
    # give the treatment tape one EXTRA column the control does not have
    ev = pd.read_parquet(a)
    ev["gap"] = 1.0
    ev.to_parquet(a, index=False)
    monkeypatch.setattr(n2, "EVENTS", a)
    monkeypatch.setattr(n2, "PLACEBO", b)
    keep = n2.common_event_columns()
    assert "gap" not in keep, "a column present on only one tape must be dropped from BOTH"
