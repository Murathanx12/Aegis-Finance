"""What `learner/features_options.py` must not be allowed to do quietly.

Three failures are possible here and none of them raises on its own:

1. **A same-day surface used for a same-day trade.** The 30-day surface is an
   END-OF-DAY object and the pull manifest says to treat it as known at t+1.
   `merge_asof(direction="backward")` with default settings would happily match
   a surface dated exactly on `entry_date`, and the resulting leak is invisible:
   the frame has the same shape, the same match rate, and a slightly better IC.
2. **A "one-month change" that spans a two-year hole.** `shift(21)` returns a
   finite number for a name that stopped having a surface in 2003 and started
   again in 2005, and calls it a one-month move.
3. **A column of NaN wearing the name of a feature.** Both the build and the
   join must report a rate rather than a shape, because a 3% join and a 97% join
   produce the same shaped frame.

The synthetic fixtures below are built from `today` and from PROPERTIES, never
from a calendar moment or a named ticker (CLAUDE.md session protocol #5). The
tests that touch the real 16m-row artefact SKIP when it is absent rather than
fail -- the artefact is a build output, not a repo file -- but they check its
receipt hard when it is there.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from learner import features_options as FO


# --------------------------------------------------------- declaration hygiene

def test_families_and_features_agree():
    flat = [c for cols in FO.FAMILIES.values() for c in cols]
    assert list(FO.FEATURES) == flat
    assert len(set(flat)) == len(flat), "a column may belong to exactly one family"
    for col in FO.FEATURES:
        assert FO.family_of(col) in FO.FAMILIES
    assert FO.family_of("not_a_column") is None


def test_every_feature_carries_a_written_definition():
    """A sign convention that lives only in the code is a sign convention the
    next reader guesses. `skew_25d_30d` is put-minus-call and there is no way to
    tell that from the name."""
    assert set(FO.DEFINITIONS) == set(FO.FEATURES)
    for col, text in FO.DEFINITIONS.items():
        assert len(text) > 20, f"{col} has a placeholder definition"


def test_variants_all_have_a_declared_horizon():
    """The Newey-West lag count is derived from this map. A target missing from
    it would raise a KeyError in `job` -- which is the correct behaviour, and
    this test is what makes it a decision rather than an accident."""
    for target in FO.VARIANTS:
        assert FO.HORIZON_MONTHS[target] >= 1


# ------------------------------------------------------------- the lag guard

def _straight_series(n: int, start: str = "2020-01-01") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"secid": 1, "date": dates,
                         "atm_iv_30d": np.linspace(0.20, 0.20 + 0.01 * n, n)})


def test_lagged_change_is_the_plain_difference_when_the_tape_is_continuous():
    df = _straight_series(60)
    chg, voided = FO.lagged_change(df, "atm_iv_30d")
    assert voided == 0
    # The first LAG_SESSIONS rows have no lag at all.
    assert chg.iloc[: FO.LAG_SESSIONS].isna().all()
    expected = df["atm_iv_30d"].iloc[FO.LAG_SESSIONS] - df["atm_iv_30d"].iloc[0]
    assert chg.iloc[FO.LAG_SESSIONS] == pytest.approx(expected)


def test_lagged_change_voids_a_lag_that_spans_a_hole():
    """THE FAILURE THIS EXISTS FOR. A name with a two-year gap in its surface
    still has a 21st-previous row, and `shift(21)` alone would difference across
    the hole and label the result a one-month change."""
    early = _straight_series(30, "2018-01-01")
    late = _straight_series(30, "2020-01-01")
    late["atm_iv_30d"] = late["atm_iv_30d"] + 5.0
    df = pd.concat([early, late], ignore_index=True).sort_values(["secid", "date"])
    df = df.reset_index(drop=True)
    chg, voided = FO.lagged_change(df, "atm_iv_30d")
    assert voided > 0, "a two-year hole must void at least one lag"
    # No surviving change may come from a pair of dates further apart than the
    # guard allows -- stated as a PROPERTY, so it cannot rot with the fixture.
    lag_d = df.groupby("secid", sort=False)["date"].shift(FO.LAG_SESSIONS)
    gaps = (df["date"] - lag_d).dt.days[chg.notna()]
    assert (gaps <= FO.MAX_LAG_GAP_DAYS).all()
    # ...and nothing absurd survived: the +5.0 jump across the hole is gone.
    assert chg.dropna().abs().max() < 5.0


def test_lagged_change_does_not_cross_names():
    a = _straight_series(30)
    b = _straight_series(30)
    b["secid"] = 2
    b["atm_iv_30d"] = b["atm_iv_30d"] + 3.0
    df = pd.concat([a, b], ignore_index=True)
    chg, _ = FO.lagged_change(df, "atm_iv_30d")
    first_of_b = chg.iloc[len(a): len(a) + FO.LAG_SESSIONS]
    assert first_of_b.isna().all(), "secid 2 must not borrow secid 1's history"


# ------------------------------------------------------------- the year pivot

def _write_surface(tmp_path, secid=1001, n_days=5, drop_coord=None):
    dates = pd.bdate_range("2020-06-01", periods=n_days)
    rows = []
    coords = [("C", 25.0, 0.31), ("C", 50.0, 0.28),
              ("P", -25.0, 0.35), ("P", -50.0, 0.29)]
    for d in dates:
        for cp, delta, iv in coords:
            if drop_coord is not None and (cp, delta) == drop_coord:
                continue
            rows.append({"secid": float(secid), "date": d.date(), "days": 30.0,
                         "delta": delta, "impl_volatility": iv, "cp_flag": cp,
                         "dispersion": 0.01})
    f = tmp_path / "surface.parquet"
    pd.DataFrame(rows).to_parquet(f, index=False)
    return f


def test_surface_year_pivots_to_one_row_per_secid_date(tmp_path):
    w = FO._surface_year(_write_surface(tmp_path, n_days=5))
    assert len(w) == 5
    assert list(w.columns) == ["secid", "date", "C25", "C50", "P25", "P50"]
    assert not w.duplicated(["secid", "date"]).any()
    assert w[["C25", "C50", "P25", "P50"]].notna().all().all()


def test_surface_year_keeps_the_row_when_one_coordinate_is_missing(tmp_path):
    """A (secid, date) whose put wing OptionMetrics could not fit must survive
    with a NaN in that wing. Dropping the row instead would make the coverage
    line in the receipt a tautology -- it would only ever measure rows that were
    already complete."""
    w = FO._surface_year(_write_surface(tmp_path, n_days=4, drop_coord=("P", -25.0)))
    assert len(w) == 4
    assert w["P25"].isna().all()
    assert w["C50"].notna().all()


def test_surface_year_survives_an_empty_file(tmp_path):
    f = tmp_path / "empty.parquet"
    pd.DataFrame({"secid": pd.Series(dtype="float64"),
                  "date": pd.Series(dtype="datetime64[ns]"),
                  "delta": pd.Series(dtype="float64"),
                  "impl_volatility": pd.Series(dtype="float64"),
                  "cp_flag": pd.Series(dtype="object")}).to_parquet(f, index=False)
    w = FO._surface_year(f)
    assert len(w) == 0
    assert set(["C25", "C50", "P25", "P50"]).issubset(w.columns)


# ------------------------------------------------------- the point-in-time join

def _tiny_feats(dates, permno=10001):
    n = len(dates)
    return pd.DataFrame({
        "permno": permno, "date": pd.to_datetime(dates),
        "atm_iv_30d": np.linspace(0.3, 0.4, n),
        "atm_iv_chg_1m": np.linspace(-0.01, 0.01, n),
        "cp_iv_spread_30d": np.linspace(-0.005, 0.005, n),
        "skew_25d_30d": np.linspace(0.02, 0.04, n),
        "iv_minus_rv_21d": np.linspace(0.05, 0.07, n),
    })


def test_attach_refuses_the_same_day_surface():
    """THE LEAK THIS FILE EXISTS TO PREVENT. The surface dated ON the trade date
    is an end-of-day object; the trade is not. `attach` must reach back to the
    prior session and must NOT take the same-day value."""
    trade = pd.Timestamp("2020-06-10")
    feats = _tiny_feats([trade - pd.Timedelta(days=1), trade])
    panel = pd.DataFrame({"permno": [10001], "entry_date": [trade]})
    joined, note = FO.attach(panel, feats)
    assert note["allow_same_day"] is False
    assert joined["date"].iloc[0] == trade - pd.Timedelta(days=1)
    assert joined["atm_iv_30d"].iloc[0] == pytest.approx(feats["atm_iv_30d"].iloc[0])
    # The diagnostic switch must actually change the answer, or the test above
    # is proving nothing about the default.
    joined2, note2 = FO.attach(panel, feats, allow_same_day=True)
    assert note2["allow_same_day"] is True
    assert joined2["date"].iloc[0] == trade


def test_attach_never_uses_a_surface_dated_after_the_trade():
    trade = pd.Timestamp("2020-06-10")
    feats = _tiny_feats([trade + pd.Timedelta(days=1), trade + pd.Timedelta(days=2)])
    panel = pd.DataFrame({"permno": [10001], "entry_date": [trade]})
    joined, note = FO.attach(panel, feats)
    assert joined[list(FO.FEATURES)].isna().all().all()
    assert max(note["match_rate"].values()) == 0.0


def test_attach_lets_a_stale_surface_go_nan_rather_than_carrying_it_forward():
    trade = pd.Timestamp("2020-06-10")
    stale = trade - pd.Timedelta(days=40)
    feats = _tiny_feats([stale])
    panel = pd.DataFrame({"permno": [10001], "entry_date": [trade]})
    joined, _ = FO.attach(panel, feats, tolerance_days=7)
    assert joined["atm_iv_30d"].isna().all()


def test_attach_reports_a_rate_and_not_only_a_shape():
    """A 3% join and a 97% join produce the same shaped frame."""
    trade = pd.Timestamp("2020-06-10")
    feats = _tiny_feats([trade - pd.Timedelta(days=1)], permno=10001)
    panel = pd.DataFrame({"permno": [10001, 10002, 10003, 10004],
                          "entry_date": [trade] * 4})
    joined, note = FO.attach(panel, feats)
    assert note["rows_in"] == 4 and note["rows_out"] == 4
    assert set(note["match_rate"]) == set(FO.FEATURES)
    assert note["match_rate"]["atm_iv_30d"] == pytest.approx(0.25)
    assert note["verdict"].startswith("THIN")
    assert note["median_lag_days"] == pytest.approx(1.0)


def test_attach_does_not_mix_names_up():
    trade = pd.Timestamp("2020-06-10")
    a = _tiny_feats([trade - pd.Timedelta(days=1)], permno=10001)
    b = _tiny_feats([trade - pd.Timedelta(days=1)], permno=10002)
    b["skew_25d_30d"] = 99.0
    feats = pd.concat([a, b], ignore_index=True)
    panel = pd.DataFrame({"permno": [10001, 10002], "entry_date": [trade, trade]})
    joined, _ = FO.attach(panel, feats)
    got = joined.set_index("permno")["skew_25d_30d"]
    assert got.loc[10002] == pytest.approx(99.0)
    assert got.loc[10001] != pytest.approx(99.0)


# ------------------------------------------------------------- loud refusals

def test_load_refuses_loudly_when_the_artefact_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(FO, "OPTION_FEATURES", tmp_path / "nope.parquet")
    with pytest.raises(SystemExit) as e:
        FO.load()
    assert "REFUSED" in str(e.value)
    assert FO.available() is False


def test_link_loader_refuses_loudly_when_the_link_is_absent(tmp_path, monkeypatch):
    """Inventing a secid->permno mapping here would create a second copy that
    drifts from the one the rest of the repo joins on."""
    monkeypatch.setattr(FO, "LINK_FILE", tmp_path / "nope.parquet")
    with pytest.raises(SystemExit) as e:
        FO.load_link()
    assert "REFUSED" in str(e.value)


def test_build_refuses_a_window_with_no_surface_file(monkeypatch):
    monkeypatch.setattr(FO, "surface_files", lambda: {2013: FO.WRDS / "x.parquet"})
    monkeypatch.setattr(FO, "coverage_on_disk",
                        lambda: {"years_present": [2013], "measured_window": ["a", "b"],
                                 "n_files": 1, "total_rows": 1})
    with pytest.raises(SystemExit) as e:
        FO.build(1990, 1991, verbose=False)
    assert "REFUSED" in str(e.value)


def test_job_defers_rather_than_crashing_when_nothing_is_built(monkeypatch):
    """A stub that raised would burn the runner's two strikes and remove W5 from
    the weekend queue; DEFERRED costs a leaderboard line and keeps the slot."""
    monkeypatch.setattr(FO, "available", lambda: False)
    out = FO.job(0)
    assert out["verdict"] == "DEFERRED"


# --------------------------------------- the real artefact, when it is on disk

@pytest.mark.skipif(not FO.surface_files(), reason="no OptionMetrics surface on this machine")
def test_coverage_is_measured_from_the_bytes_not_asserted():
    cov = FO.coverage_on_disk()
    assert cov["n_files"] == len(cov["years_present"])
    assert cov["total_rows"] > 0
    lo, hi = cov["measured_window"]
    assert lo < hi
    # Every per-year entry must carry its own measured range, so a reader can
    # check the window claim against the years it is made of.
    for row in cov["by_year"]:
        assert row["first_date"] <= row["last_date"]
        assert str(row["year"]) in row["first_date"]


@pytest.mark.skipif(not FO.OPTION_RECEIPT.exists(), reason="features_options not built here")
def test_the_receipt_carries_the_numbers_a_reader_would_otherwise_have_to_trust():
    r = json.loads(FO.OPTION_RECEIPT.read_text(encoding="utf-8"))
    assert r["version"] == FO.VERSION
    # Coverage per column, not "it built fine".
    assert set(r["non_null_rate"]) == set(FO.FEATURES)
    assert min(r["non_null_rate"].values()) > 0.0
    # The link match rate, and the caveat that the rate restates the pull filter.
    assert 0.0 < r["link"]["match_rate"] <= 1.0
    assert "pull" in r["link"]["why_the_rate_is_high"].lower()
    # Realised vol actually matched something.
    assert r["realised_vol"]["match_rate_on_linked_rows"] > 0.5
    # The sign a reader can falsify from memory: equity 25-delta skew is
    # normally POSITIVE (crash insurance is dear). A negative median here would
    # mean the two legs were subtracted the wrong way round.
    assert r["summary_stats"]["skew_25d_30d"]["median"] > 0
    # ...and the variance risk premium is normally positive too.
    assert r["summary_stats"]["iv_minus_rv_21d"]["median"] > 0


@pytest.mark.skipif(not FO.available(), reason="features_options not built here")
@pytest.mark.slow
def test_the_built_frame_has_one_row_per_permno_date():
    df = FO.load()
    head = df.head(2_000_000)
    assert not head.duplicated(["permno", "date"]).any()
    assert set(FO.FEATURES).issubset(df.columns)
