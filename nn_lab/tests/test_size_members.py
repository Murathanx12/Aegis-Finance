"""Tests for nn_lab.size_members and nn_lab.universe_filter (2026-09-30). Synthetic data,
dates derived from today, no network, no GPU."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from nn_lab import size_members as SM


def _cal(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp(date.today()) - pd.offsets.BDay(1), periods=n)


def _ed(ticker: str, days: list[pd.Timestamp], lag_days: int = 1) -> pd.DataFrame:
    d = pd.DatetimeIndex(days)
    return pd.DataFrame({"ticker": ticker, "event_day": d, "known_day": d + pd.Timedelta(days=lag_days)})


def test_a_release_one_year_ago_projects_into_the_window_and_counts_only_if_known():
    cal = _cal(600)
    t = cal[500]
    # last year's release 364 days before a day three sessions after t
    ev = cal[503] - pd.Timedelta(days=364)
    rows = pd.DataFrame({"symbol": ["AAA", "BBB"], "date": [t, t]})
    ee = SM.expected_earnings(rows, cal, _ed("AAA", [ev]), horizons=(5,))
    assert ee.loc[0, "earn_exp_5"] == 1.0
    assert ee.loc[1, "earn_exp_5"] == 0.0          # no history: nothing expected, not "missing"


def test_the_realised_release_is_graded_but_never_leaks_into_the_expectation():
    cal = _cal(300)
    t = cal[250]
    real = cal[253]                                 # happens inside the window, no history before
    rows = pd.DataFrame({"symbol": ["AAA"], "date": [t]})
    ee = SM.expected_earnings(rows, cal, _ed("AAA", [real]), horizons=(5,))
    assert ee.loc[0, "earn_real_5"] == 1.0
    assert ee.loc[0, "earn_exp_5"] == 0.0


def test_quarterly_cadence_uses_only_releases_filed_before_t():
    cal = _cal(300)
    t = cal[250]
    last = t - pd.Timedelta(days=89)                # +91 lands 2 days after t: inside h=5
    rows = pd.DataFrame({"symbol": ["AAA"], "date": [t]})
    ee = SM.expected_earnings(rows, cal, _ed("AAA", [last]), horizons=(5,))
    assert ee.loc[0, "earn_exp_5"] == 1.0
    # the same release, but filed ON t (not strictly before): unusable
    ed = pd.DataFrame({"ticker": ["AAA"], "event_day": [last], "known_day": [t]})
    ee2 = SM.expected_earnings(rows, cal, ed, horizons=(5,))
    assert ee2.loc[0, "earn_exp_5"] == 0.0


def test_a_renamed_dead_segment_never_inherits_the_living_filers_calendar():
    cal = _cal(600)
    t = cal[500]
    ev = cal[503] - pd.Timedelta(days=364)
    rows = pd.DataFrame({"symbol": ["AAA#1"], "date": [t]})
    ee = SM.expected_earnings(rows, cal, _ed("AAA", [ev]), horizons=(5,))
    assert ee.loc[0, "earn_exp_5"] == 0.0


def test_text_aggregation_uses_cells_entered_up_to_t_and_nan_without_news():
    t = pd.Timestamp(date.today()).normalize() - pd.Timedelta(days=30)
    scored = pd.DataFrame({"symbol": ["AAA", "AAA", "AAA"],
                           "entry_date": [t - pd.Timedelta(days=2), t, t + pd.Timedelta(days=1)],
                           "text_resid": [0.2, 0.4, 9.0]})
    rows = pd.DataFrame({"symbol": ["AAA", "BBB"], "date": [t, t]})
    v = SM.aggregate_text(rows, scored)
    assert abs(v[0] - 0.3) < 1e-6                   # the cell entering t+1 is not used
    assert np.isnan(v[1])


def test_text_scoring_never_fits_on_a_cell_it_scores():
    rng = np.random.default_rng(0)
    start = pd.Timestamp(date.today()).normalize() - pd.Timedelta(days=500)
    days = pd.bdate_range(start, periods=400)
    n = 12000
    ed = rng.choice(days, n)
    words = np.array(["beat", "miss", "guidance", "merger", "lawsuit", "dividend", "quiet", "update"])
    cells = pd.DataFrame({"symbol": rng.choice(["A", "B", "C", "D"], n),
                          "entry_date": pd.DatetimeIndex(ed).strftime("%Y-%m-%d"),
                          "text": [" ".join(rng.choice(words, 6)) for _ in range(n)]})
    for c in SM.PRIOR_TRAILING + SM.META:
        cells[c] = rng.normal(size=n)
    cells["ly"] = cells["l_vol21_absx"] + 0.5 * cells["text"].str.contains("merger") + rng.normal(0, 1, n)
    cuts = SM.text_cutoffs(cells["entry_date"], every_months=6, min_months=5)
    seen = {}
    orig = SM.fit_text_model

    def spy(c, mask, **kw):
        seen.setdefault("last_fit", []).append(pd.to_datetime(c.loc[mask, "entry_date"]).max())
        return orig(c, mask, max_features=500)
    SM.text_model_cache = spy
    try:
        sc, info = SM.scored_cells(cells, cuts)
    finally:
        SM.text_model_cache = lambda c, m: SM.fit_text_model(c, m)
    for f, last in zip(info, seen["last_fit"]):
        assert last < pd.Timestamp(f["cutoff"]) - pd.Timedelta(days=SM.TEXT_EMBARGO_DAYS - 1)
    scored_dates = pd.to_datetime(sc.loc[sc["text_resid"].notna(), "entry_date"])
    assert scored_dates.min() >= pd.Timestamp(info[0]["cutoff"])


def test_log_member_recovers_an_earnings_multiplier():
    rng = np.random.default_rng(1)
    n = 20000
    lv = rng.normal(-3.5, 0.4, n)
    e = (rng.random(n) < 0.2).astype(float)
    y = np.exp(lv + 0.3 * e + rng.normal(0, 0.5, n))
    b = SM.fit_log_member(lv, e, y)
    assert abs(b[2] - 0.3) < 0.05
    p = SM.predict_log_member(b, lv, np.full(n, np.nan))   # NaN extra reads as 0 (no view)
    assert np.all(np.isfinite(p))


def test_nightly_members_fit_on_labelled_rows_and_score_the_live_date(tmp_path, monkeypatch):
    from nn_lab import config as C
    cal = _cal(400)
    rng = np.random.default_rng(3)
    grid = cal[::5]
    rows = []
    for d in grid:
        for s in range(60):
            e = float(rng.random() < 0.2)
            v = np.exp(rng.normal(-1, 0.3))
            rows.append({"date": d, "symbol": f"S{s}", "on_grid": True, "vol_63": v,
                         "y_5": np.exp(np.log(v) - 3 + 0.3 * e + rng.normal(0, 0.5)) * rng.choice([-1, 1]),
                         "y_21": np.exp(np.log(v) - 2 + 0.2 * e + rng.normal(0, 0.5)), "e": e})
    tab = pd.DataFrame(rows)
    tp = tmp_path / "t.parquet"
    tab.drop(columns=["e"]).to_parquet(tp)
    pd.DataFrame({"date": cal}).to_parquet(tmp_path / "calendar.parquet")
    side = tab[["date", "symbol"]].assign(earn_exp_5=tab["e"], earn_exp_21=tab["e"], text_resid_7d=np.nan)
    sp = tmp_path / "side.parquet"
    side.to_parquet(sp)
    monkeypatch.setattr(C, "SIZE_MEMBERS_NIGHTLY", True)
    monkeypatch.setattr(C, "SIZE_MEMBER_ROSTER", ("vol_earn", "vol_text"))
    live = tab[tab["date"] == grid[-1]][["symbol", "date", "vol_63"]]
    out = SM.nightly_member_predictions(live, table_path=tp, sidecar=sp)
    assert 0.2 < out["_coef"]["vol_earn_h5"][2] < 0.4
    assert np.all(np.isfinite(out["vol_earn"][5])) and len(out["vol_earn"][5]) == len(live)
    assert np.all(np.isnan(out["vol_text"][5]))        # no news anywhere: no view, never a number
    monkeypatch.setattr(C, "SIZE_MEMBERS_NIGHTLY", False)
    assert SM.member_roster() == ()
