"""VALIDATION of `learner.features_price` -- the behavioural features' PIT and
split discipline.

THE TWO WAYS THIS FILE'S FEATURES CAN BE WRONG WITHOUT LOOKING WRONG
====================================================================
Both failure modes produce a fully populated, plausible column. Neither shows up
in a coverage receipt, and both would inflate a backtest.

1. **A window that contains its own observation.** `attention_z` is "today's
   dollar volume against its own trailing distribution". If the 60-session
   mean/sd window includes today, then the larger the event the more it inflates
   its own denominator -- the z-score is smallest exactly when the event is
   biggest, and, worse, the feature at date t is a function of the bar at date
   t in a way that no longer describes what was knowable before it. The module
   guards this with `shift(1)`; this file proves the guard fires, by computing
   both the correct and the incorrect window and asserting which one the module
   produced.

2. **A share basis that moves under the feature.** CRSP `vol` is a raw share
   count, so a 2:1 split doubles it overnight and a naive VWAP mixes pre- and
   post-split prices with pre- and post-split share counts. `reference_farm_split_adjustment`
   is the corpse this repo already paid for. The test constructs the SAME
   economic history twice -- once with a 2:1 split in the middle and once
   without -- and requires every feature to be identical. It then shows the
   naive construction DOES jump on the same data, so a passing test is evidence
   the code is right rather than evidence the split was too small to see.

Everything is offline: the CRSP directory is monkeypatched to a tmp_path holding
synthetic parquet files, and the module's real `build()` is run against them.
Dates are derived from `today`; no calendar moment is written down.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from learner import features_price as FP


N_SESSIONS = 420          # enough for the 252-session lookback plus tail
PERMNO_A = 90_001
PERMNO_B = 90_002


def _sessions(n: int = N_SESSIONS) -> pd.DatetimeIndex:
    """`n` business days ending a month before today. Derived, never written."""
    end = pd.Timestamp(dt.date.today()) - pd.Timedelta(days=30)
    return pd.bdate_range(end=end.normalize(), periods=n)


def _write_wrds(monkeypatch, tmp_path, df: pd.DataFrame) -> None:
    """Split `df` into `crsp_dsf_<year>.parquet` files and point the module at
    them. The module resolves `tib.WRDS` at call time, so patching the attribute
    is enough and nothing touches the real 1990-2024 archive."""
    from scripts import tracker_ibes_backtest as tib
    for year, g in df.groupby(df["date"].dt.year):
        g.to_parquet(tmp_path / f"crsp_dsf_{int(year)}.parquet", index=False)
    monkeypatch.setattr(tib, "WRDS", tmp_path)


def _years(df: pd.DataFrame) -> tuple[int, int]:
    return int(df["date"].dt.year.min()), int(df["date"].dt.year.max())


def _bars(permno: int, adj_price: np.ndarray, dollar_vol: np.ndarray,
          cfacpr: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Raw CRSP-shaped bars for a name whose ADJUSTED path and DOLLAR volume are
    given, expressed on whatever raw share basis `cfacpr` implies.

    This is the whole trick of the split test: the economics (`adj_price`,
    `dollar_vol`) are held fixed and only the reporting basis moves, so any
    feature that is a function of the economics alone must be unchanged.
    """
    prc = adj_price * cfacpr                      # raw close on that day's basis
    vol = dollar_vol / prc                        # raw share count
    ret = np.concatenate([[np.nan], adj_price[1:] / adj_price[:-1] - 1.0])
    return pd.DataFrame({"permno": permno, "date": dates, "prc": prc,
                         "ret": ret, "cfacpr": cfacpr, "vol": vol})


@pytest.fixture(scope="module")
def economics():
    """One adjusted price path and one dollar-volume path, shared by both runs."""
    rng = np.random.default_rng(20260906)
    dates = _sessions()
    adj = 50.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, len(dates))))
    dv = np.exp(rng.normal(np.log(4.0e6), 0.45, len(dates)))
    return dates, adj, dv


# ------------------------------------------------ 1. attention is point-in-time


def test_attention_z_excludes_todays_own_observation(monkeypatch, tmp_path, economics):
    """The decisive form: compute BOTH candidate windows and see which one the
    module produced.

    * correct   -- mean/sd of the 60 log dollar volumes ending at t-1
    * incorrect -- mean/sd of the 60 ending at t (today inside its own window)

    Asserting only the correct one would leave open that the two agree on this
    fixture; the second assertion refutes the incorrect one explicitly, so a
    pass means the guard fired rather than that the test could not tell.
    """
    dates, adj, dv = economics
    bars = _bars(PERMNO_A, adj, dv, np.ones(len(dates)), dates)
    _write_wrds(monkeypatch, tmp_path, bars)
    out, _ = FP.build(*_years(bars), verbose=False)
    out = out.sort_values("date").reset_index(drop=True)

    ldv = np.log1p(dv)
    prev = pd.Series(ldv).shift(1)
    mu_ok = prev.rolling(60, min_periods=20).mean()
    sd_ok = prev.rolling(60, min_periods=20).std()
    z_ok = (ldv - mu_ok) / sd_ok.where(sd_ok > 0)

    s = pd.Series(ldv)
    mu_bad = s.rolling(60, min_periods=20).mean()
    sd_bad = s.rolling(60, min_periods=20).std()
    z_bad = (ldv - mu_bad) / sd_bad.where(sd_bad > 0)

    got = out["attention_z"]
    live = got.notna() & z_ok.notna() & z_bad.notna()
    assert int(live.sum()) > 300, "too few comparable rows -- the test would be weak"

    np.testing.assert_allclose(got[live].to_numpy(), z_ok[live].to_numpy(),
                               rtol=1e-10, atol=1e-10,
                               err_msg="attention_z is not the shift(1) window")
    diff = float(np.abs(got[live].to_numpy() - z_bad[live].to_numpy()).max())
    assert diff > 1e-6, (
        "attention_z is indistinguishable from the window that CONTAINS today -- "
        "either the guard is absent or this fixture cannot tell the two apart")


def test_a_volume_spike_scales_the_z_linearly(monkeypatch, tmp_path, economics):
    """The same claim as a mechanism rather than a formula.

    If the window excluded today, `z_t = (ldv_t - mu)/sd` with `mu, sd` fixed, so
    doubling the log-excess doubles the z EXACTLY. If today were inside its own
    window, the spike would inflate `mu` and `sd` and the response would be
    damped and non-linear. Three runs differing only in one bar's volume.
    """
    dates, adj, dv = economics
    spike_at = len(dates) - 30
    zs = []
    for extra in (0.0, 1.0, 2.0):
        v = dv.copy()
        v[spike_at] = float(np.expm1(np.log1p(v[spike_at]) + extra))
        bars = _bars(PERMNO_A, adj, v, np.ones(len(dates)), dates)
        _write_wrds(monkeypatch, tmp_path, bars)
        out, _ = FP.build(*_years(bars), verbose=False)
        out = out.sort_values("date").reset_index(drop=True)
        zs.append(float(out["attention_z"].iloc[spike_at]))

    first, second = zs[1] - zs[0], zs[2] - zs[1]
    assert first > 0, "a larger volume did not raise the attention z-score"
    assert second == pytest.approx(first, rel=1e-6), (
        f"the z-score response to an equal log-volume step was {first:.6f} then "
        f"{second:.6f} -- a damped response means the spike is inflating its own "
        "mean/sd window")


def test_no_feature_at_t_changes_when_later_bars_are_added(monkeypatch, tmp_path,
                                                           economics):
    """The general PIT statement: truncating the tape must not move any feature
    on the surviving prefix. This catches a centred window or a backward fill in
    ANY of the six columns, not just the one that was thought about."""
    dates, adj, dv = economics
    cut = len(dates) - 40

    full = _bars(PERMNO_A, adj, dv, np.ones(len(dates)), dates)
    _write_wrds(monkeypatch, tmp_path, full)
    a, _ = FP.build(*_years(full), verbose=False)

    short = full.iloc[:cut].copy()
    _write_wrds(monkeypatch, tmp_path, short)
    b, _ = FP.build(*_years(short), verbose=False)

    a = a.sort_values("date").reset_index(drop=True).iloc[:cut]
    b = b.sort_values("date").reset_index(drop=True)
    assert len(a) == len(b) == cut
    for col in FP.FEATURES:
        np.testing.assert_allclose(
            a[col].to_numpy(dtype=float), b[col].to_numpy(dtype=float),
            rtol=1e-12, atol=1e-12, equal_nan=True,
            err_msg=f"`{col}` on the prefix moved when 40 later bars were added")


def test_the_attention_window_never_uses_a_future_bar_after_a_gap(monkeypatch,
                                                                 tmp_path, economics):
    """A name that stops trading and resumes must not have its gap bridged by a
    later bar: the rolling windows are positional, so the only requirement is
    that no value is computed from a row dated after it. Verified by comparing a
    gapped name against the same name truncated at the gap."""
    dates, adj, dv = economics
    keep = np.ones(len(dates), dtype=bool)
    keep[200:230] = False                       # a 30-session hole
    bars = _bars(PERMNO_A, adj, dv, np.ones(len(dates)), dates)[keep].reset_index(drop=True)
    _write_wrds(monkeypatch, tmp_path, bars)
    full, _ = FP.build(*_years(bars), verbose=False)

    at = 260
    short = bars.iloc[:at + 1].copy()
    _write_wrds(monkeypatch, tmp_path, short)
    trunc, _ = FP.build(*_years(short), verbose=False)

    full = full.sort_values("date").reset_index(drop=True)
    trunc = trunc.sort_values("date").reset_index(drop=True)
    for col in FP.FEATURES:
        assert full[col].iloc[at] == pytest.approx(
            trunc[col].iloc[at], nan_ok=True, rel=1e-12), (
            f"`{col}` on the last observable bar differed once later bars existed")


# ------------------------------------------------- 2. the split does not move it


def test_a_two_for_one_split_moves_no_feature(monkeypatch, tmp_path, economics):
    """THE SPLIT TEST. Identical economics, two reporting bases.

    Run A has no corporate action. Run B has a 2:1 split at the midpoint: the raw
    close halves, the raw share count doubles, `cfacpr` steps 2 -> 1. The
    adjusted price path and the dollar-volume path are identical by construction,
    so every feature in this module -- all of which are supposed to be functions
    of those two alone -- must come out identical.
    """
    dates, adj, dv = economics
    split_at = len(dates) // 2

    flat = _bars(PERMNO_A, adj, dv, np.ones(len(dates)), dates)
    _write_wrds(monkeypatch, tmp_path, flat)
    a, _ = FP.build(*_years(flat), verbose=False)

    cf = np.where(np.arange(len(dates)) < split_at, 2.0, 1.0)
    split = _bars(PERMNO_A, adj, dv, cf, dates)
    # sanity: the RAW tape really does jump, or the test proves nothing
    assert split["prc"].iloc[split_at] == pytest.approx(
        split["prc"].iloc[split_at - 1] * (adj[split_at] / adj[split_at - 1]) / 2.0)
    assert split["vol"].iloc[split_at] > 1.7 * split["vol"].iloc[split_at - 1]

    _write_wrds(monkeypatch, tmp_path, split)
    b, _ = FP.build(*_years(split), verbose=False)

    a = a.sort_values("date").reset_index(drop=True)
    b = b.sort_values("date").reset_index(drop=True)
    for col in FP.FEATURES:
        np.testing.assert_allclose(
            a[col].to_numpy(dtype=float), b[col].to_numpy(dtype=float),
            rtol=1e-9, atol=1e-9, equal_nan=True,
            err_msg=f"`{col}` moved across a pure 2:1 split -- the feature is being "
                    "computed on a share basis that the split changed")


def test_the_vwap_gap_does_not_jump_on_the_split_session(monkeypatch, tmp_path,
                                                         economics):
    """The named claim, checked locally rather than by whole-series equality: the
    one-session change in `vwap_60d_gap` across the split must look like every
    other session's change, not like a factor of two."""
    dates, adj, dv = economics
    split_at = len(dates) // 2
    cf = np.where(np.arange(len(dates)) < split_at, 2.0, 1.0)
    bars = _bars(PERMNO_A, adj, dv, cf, dates)
    _write_wrds(monkeypatch, tmp_path, bars)
    out, _ = FP.build(*_years(bars), verbose=False)
    out = out.sort_values("date").reset_index(drop=True)

    gap = out["vwap_60d_gap"]
    steps = gap.diff().abs().dropna()
    at_split = float(abs(gap.iloc[split_at] - gap.iloc[split_at - 1]))
    typical = float(steps.quantile(0.99))
    assert at_split <= typical, (
        f"`vwap_60d_gap` moved {at_split:.4f} across the split session against a 99th "
        f"percentile daily move of {typical:.4f} -- the split leaked into the anchor")
    assert np.isfinite(gap.iloc[split_at])


def test_the_naive_vwap_would_have_jumped_on_the_same_data(economics):
    """THE TEST'S OWN CONTROL. `sum(prc*vol)/sum(vol)` divided by today's
    `cfacpr` -- the construction the module's comment rejects -- must visibly
    break on this exact fixture. Without this, a green split test could mean the
    fixture was too gentle to detect anything.
    """
    dates, adj, dv = economics
    split_at = len(dates) // 2
    cf = np.where(np.arange(len(dates)) < split_at, 2.0, 1.0)
    bars = _bars(PERMNO_A, adj, dv, cf, dates)

    num = bars["prc"].mul(bars["vol"]).rolling(60, min_periods=20).sum()
    den = bars["vol"].rolling(60, min_periods=20).sum()
    naive_vwap = (num / den) / bars["cfacpr"]
    naive_gap = (adj / naive_vwap) - 1.0
    jump = float(abs(naive_gap.iloc[split_at] - naive_gap.iloc[split_at - 1]))
    baseline = float(naive_gap.diff().abs().quantile(0.99))
    assert jump > 5 * baseline, (
        "the naive VWAP did NOT break on this fixture, so the split test above is "
        f"not evidence of anything (jump {jump:.4f} vs 99th pct {baseline:.4f})")


def test_attention_is_built_on_dollars_and_so_ignores_the_split(monkeypatch,
                                                                tmp_path, economics):
    """The module's stated reason for using dollar volume: a share-count z-score
    would read a 2:1 split as a huge attention event. On the split session the
    dollar-volume z must be ordinary."""
    dates, adj, dv = economics
    split_at = len(dates) // 2
    cf = np.where(np.arange(len(dates)) < split_at, 2.0, 1.0)
    bars = _bars(PERMNO_A, adj, dv, cf, dates)
    _write_wrds(monkeypatch, tmp_path, bars)
    out, _ = FP.build(*_years(bars), verbose=False)
    out = out.sort_values("date").reset_index(drop=True)

    # The claim is comparative and RANK-based, not a magic sigma threshold: on
    # the share basis the split session must be the loudest bar in the series;
    # on the dollar basis it must be unremarkable.
    dollars = out["attention_z"].abs()
    z_dollars = float(dollars.iloc[split_at])
    assert z_dollars <= float(dollars.quantile(0.99)), (
        f"the split session scored {z_dollars:.2f} sigma on dollar volume, above the "
        f"99th percentile {float(dollars.quantile(0.99)):.2f} -- the split leaked in")

    lsh = np.log1p(bars["vol"])
    prev = lsh.shift(1)
    mu = prev.rolling(60, min_periods=20).mean()
    sd = prev.rolling(60, min_periods=20).std()
    shares = ((lsh - mu) / sd).abs()
    z_shares = float(shares.iloc[split_at])
    assert z_shares == pytest.approx(float(shares.max())), (
        "a share-count z-score did not make the split its single loudest session -- "
        "the fixture is not exercising the failure dollar volume exists to avoid")
    assert z_shares > z_dollars + 1.5, (
        f"share basis {z_shares:.2f} vs dollar basis {z_dollars:.2f} -- the two bases "
        "are not distinguishable on this fixture, so the test proves nothing")


# --------------------------------------------------- the module's own guards


def test_the_features_are_populated_and_named_by_family(monkeypatch, tmp_path,
                                                        economics):
    """A column that is NaN everywhere is a column that was never built. The
    module refuses on that; this asserts the refusal is not the only thing
    standing between the panel and an empty feature."""
    dates, adj, dv = economics
    bars = pd.concat([
        _bars(PERMNO_A, adj, dv, np.ones(len(dates)), dates),
        _bars(PERMNO_B, adj * 1.7, dv * 0.4, np.ones(len(dates)), dates),
    ], ignore_index=True)
    _write_wrds(monkeypatch, tmp_path, bars)
    out, receipt = FP.build(*_years(bars), verbose=False)

    assert set(out.columns) == {"permno", "date", *FP.FEATURES}
    assert out["permno"].nunique() == 2
    for col in FP.FEATURES:
        rate = receipt["non_null_rate"][col]
        assert rate > 0.0, f"`{col}` is empty on every row"
        assert FP.family_of(col) is not None, f"`{col}` belongs to no family"
    assert set(FP.FEATURES) == {c for cols in FP.FAMILIES.values() for c in cols}
    assert receipt["version"] == FP.VERSION
    assert receipt["permnos"] == 2


def test_the_features_do_not_bleed_between_names(monkeypatch, tmp_path, economics):
    """Every rolling window is grouped by permno. A second name with a wildly
    different volume level must not move the first name's attention z."""
    dates, adj, dv = economics
    alone = _bars(PERMNO_A, adj, dv, np.ones(len(dates)), dates)
    _write_wrds(monkeypatch, tmp_path, alone)
    a, _ = FP.build(*_years(alone), verbose=False)

    together = pd.concat([alone,
                          _bars(PERMNO_B, adj * 3.0, dv * 500.0,
                                np.ones(len(dates)), dates)], ignore_index=True)
    _write_wrds(monkeypatch, tmp_path, together)
    b, _ = FP.build(*_years(together), verbose=False)
    b = b[b["permno"] == PERMNO_A]

    a = a.sort_values("date").reset_index(drop=True)
    b = b.sort_values("date").reset_index(drop=True)
    for col in FP.FEATURES:
        np.testing.assert_allclose(
            a[col].to_numpy(dtype=float), b[col].to_numpy(dtype=float),
            rtol=1e-12, atol=1e-12, equal_nan=True,
            err_msg=f"`{col}` for one name changed when another name was added")


def test_the_52_week_high_proximity_is_bounded_and_meaningful(monkeypatch,
                                                              tmp_path, economics):
    """`adj_prc / max(adj_prc, 252d)` is at most 1 by construction, and must
    actually reach 1 on the days the name makes a new high -- otherwise the
    window is off by one and the feature never fires."""
    dates, adj, dv = economics
    bars = _bars(PERMNO_A, adj, dv, np.ones(len(dates)), dates)
    _write_wrds(monkeypatch, tmp_path, bars)
    out, _ = FP.build(*_years(bars), verbose=False)
    ph = out["prox_52w_high"].dropna()
    assert len(ph) > 200
    assert ph.max() == pytest.approx(1.0), "the feature never reaches its own high"
    assert ph.min() > 0.0 and ph.max() <= 1.0 + 1e-12
    assert (out["prox_52w_low"].dropna() >= -1e-12).all(), "prox_52w_low went negative"


def test_the_attach_join_is_backward_only(monkeypatch, tmp_path, economics):
    """`attach` must never hand the panel a bar dated AFTER the trade. A row
    whose entry precedes every bar must come back NaN, not forward-filled."""
    dates, adj, dv = economics
    bars = _bars(PERMNO_A, adj, dv, np.ones(len(dates)), dates)
    _write_wrds(monkeypatch, tmp_path, bars)
    feats, _ = FP.build(*_years(bars), verbose=False)

    panel = pd.DataFrame({
        "permno": [PERMNO_A, PERMNO_A],
        # one entry long before any bar, one on a real session near the end
        "entry_date": [dates[0] - pd.Timedelta(days=400), dates[-1]],
    })
    joined, note = FP.attach(panel, feats)
    joined = joined.sort_values("entry_date").reset_index(drop=True)

    assert joined.loc[0, list(FP.FEATURES)].isna().all(), (
        "a row entered before the first bar received feature values -- the join is "
        "not backward-only")
    assert joined.loc[1, "prox_52w_high"] == pytest.approx(
        float(feats.sort_values("date")["prox_52w_high"].iloc[-1]))
    assert note["direction"].startswith("backward")
    assert note["rows_in"] == note["rows_out"] == 2


def test_a_stale_bar_beyond_the_tolerance_is_not_carried_forward(monkeypatch,
                                                                 tmp_path, economics):
    """The 7-day tolerance: a trade a month after the last bar gets NaN, not a
    month-old value wearing today's date."""
    dates, adj, dv = economics
    bars = _bars(PERMNO_A, adj, dv, np.ones(len(dates)), dates)
    _write_wrds(monkeypatch, tmp_path, bars)
    feats, _ = FP.build(*_years(bars), verbose=False)

    panel = pd.DataFrame({"permno": [PERMNO_A],
                          "entry_date": [dates[-1] + pd.Timedelta(days=30)]})
    joined, _ = FP.attach(panel, feats)
    assert joined.loc[0, list(FP.FEATURES)].isna().all(), (
        "a bar 30 days stale was carried onto a trade with a 7-day tolerance")

    panel_ok = pd.DataFrame({"permno": [PERMNO_A],
                             "entry_date": [dates[-1] + pd.Timedelta(days=3)]})
    joined_ok, _ = FP.attach(panel_ok, feats)
    assert joined_ok.loc[0, "prox_52w_high"] == pytest.approx(
        float(feats.sort_values("date")["prox_52w_high"].iloc[-1])), (
        "a bar 3 days old was dropped -- the tolerance is not doing what it says")
