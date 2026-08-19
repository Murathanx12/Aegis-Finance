"""CONVEXITY-EPISODES-1 — detector, arm accounting, matching, no aggregates.

The failure modes tested are the quiet ones: a crossing found on the wrong
day, a stop that charges no cost, a matching distance built on future
prices, and an aggregate verdict sneaking into what is registered as
dataset construction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import convexity_episodes as CE
from backend.services import net_panel as NP


def _px_single(path: list[float], name="AAA", start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(path))
    return pd.DataFrame({name: path}, index=idx)


# ── detection ──────────────────────────────────────────────────────────────
def test_first_touch_crossing_is_found_on_the_right_day():
    path = [100.0] * 5 + [110.0, 121.0, 115.0, 130.0, 100.0]
    px = _px_single(path)
    eps = CE.detect_episodes(px, [px.index[0]])
    twenty = [e for e in eps if e.threshold == 0.20]
    assert len(twenty) == 1
    # +20% is first touched at 121.0, index 6 → 6 days after entry
    assert twenty[0].days_to_crossing == 6
    assert twenty[0].crossing_date == str(px.index[6].date())


def test_a_path_that_never_crosses_produces_no_episode():
    px = _px_single([100.0 + i * 0.01 for i in range(300)])
    assert CE.detect_episodes(px, [px.index[0]]) == []


def test_a_crossing_beyond_the_search_bound_is_not_an_episode():
    n = CE.MAX_CROSSING_DAYS + 50
    path = [100.0] * (CE.MAX_CROSSING_DAYS + 10) + [130.0] * (n - CE.MAX_CROSSING_DAYS - 10)
    px = _px_single(path)
    eps = CE.detect_episodes(px, [px.index[0]])
    assert eps == [], "a crossing after MAX_CROSSING_DAYS studies the index, " \
                      "not the management decision"


# ── arm accounting (per-dollar, costs on traded fraction) ──────────────────
def test_hold_and_exit_and_trims_have_exact_arithmetic():
    path = np.array([100.0, 110.0, 120.0])
    rate = 10.0 / 1e4
    hold = CE.arm_outcome(path, "hold", cost_one_way_bps=10.0,
                          ann_vol_at_crossing=0.3)
    assert hold["terminal_wealth"] == pytest.approx(1.2)
    exit_ = CE.arm_outcome(path, "exit_full", cost_one_way_bps=10.0,
                           ann_vol_at_crossing=0.3)
    assert exit_["terminal_wealth"] == pytest.approx(1 - rate)
    trim = CE.arm_outcome(path, "trim_25", cost_one_way_bps=10.0,
                          ann_vol_at_crossing=0.3)
    assert trim["terminal_wealth"] == pytest.approx(
        0.75 * 1.2 + 0.25 * (1 - rate))


def test_the_trailing_stop_fires_at_the_right_day_and_pays_its_cost():
    #        peak 130 at i=2; 20% stop level = 104; i=4 hits 100 → fires
    path = np.array([100.0, 120.0, 130.0, 110.0, 100.0, 150.0])
    out = CE.arm_outcome(path, "trail_stop_20", cost_one_way_bps=10.0,
                         ann_vol_at_crossing=0.3)
    assert out["fired_day"] == 4
    assert out["terminal_wealth"] == pytest.approx(1.0 * (1 - 10.0 / 1e4))
    # and it MISSES the later recovery to 150 — that asymmetry is the
    # entire research question, so the arithmetic must show it
    hold = CE.arm_outcome(path, "hold", cost_one_way_bps=10.0,
                          ann_vol_at_crossing=0.3)
    assert hold["terminal_wealth"] == pytest.approx(1.5)


def test_a_stop_that_never_fires_equals_hold():
    path = np.array([100.0, 105.0, 111.0, 118.0])
    out = CE.arm_outcome(path, "trail_stop_20", cost_one_way_bps=10.0,
                         ann_vol_at_crossing=0.3)
    assert out["fired_day"] is None
    assert out["terminal_wealth"] == pytest.approx(1.18)


def test_unknown_arm_and_short_path_refuse():
    with pytest.raises(CE.EpisodeRefused, match="unknown arm"):
        CE.arm_outcome(np.array([100.0, 101.0]), "yolo",
                       cost_one_way_bps=5.0, ann_vol_at_crossing=0.3)
    with pytest.raises(CE.EpisodeRefused, match="two prices"):
        CE.arm_outcome(np.array([100.0]), "hold",
                       cost_one_way_bps=5.0, ann_vol_at_crossing=0.3)


# ── matching (§16), and its PIT clock ──────────────────────────────────────
def _ep(month_day="2020-06-10"):
    return CE.Episode(ticker="WIN", entry_date="2020-05-29",
                      crossing_date=month_day, threshold=0.20,
                      days_to_crossing=8, gain_at_crossing=0.21)


def _feats(names):
    return pd.DataFrame(
        {n: {"mom_252": 0.1, "vol_63": 0.3, "drawdown_252": -0.1}
         for n in names}).T


def test_matching_reads_the_month_end_BEFORE_the_crossing_month():
    """A crossing on June 10 matched on June-30 features would be a leak
    wearing a caliper. Only the May month-end grid may serve it."""
    ep = _ep("2020-06-10")
    only_june = {"2020-06": _feats(["WIN", "CTL"])}
    out = CE.match_control(ep, only_june, {})
    assert out["control"] is None
    assert "pre-crossing month" in out["reason"]

    only_may = {"2020-05": _feats(["WIN", "CTL"])}
    out = CE.match_control(ep, only_may, {})
    assert out["control"] == "CTL"


def test_same_month_crossers_are_excluded_from_the_control_pool():
    ep = _ep()
    feats = {"2020-05": _feats(["WIN", "CTL", "ALSO"])}
    out = CE.match_control(ep, feats, {"2020-06": {"ALSO"}})
    assert out["control"] == "CTL"


def test_a_control_beyond_the_caliper_is_refused_not_accepted():
    ep = _ep()
    frame = _feats(["WIN", "FAR", "MID"])
    frame.loc["FAR"] = {"mom_252": 9.0, "vol_63": 9.0, "drawdown_252": -0.9}
    frame.loc["MID"] = {"mom_252": 4.0, "vol_63": 4.0, "drawdown_252": -0.5}
    out = CE.match_control(ep, {"2020-05": frame}, {})
    assert out["control"] is None
    assert "caliper" in out["reason"]


# ── materialization: construction only, never a verdict ────────────────────
def _panel(seed=11, n_days=700, n_names=8):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-01", periods=n_days)
    data = {f"T{i}": 100.0 * np.exp(np.cumsum(
        rng.normal(0.0008, 0.025, n_days))) for i in range(n_names)}
    return pd.DataFrame(data, index=idx)


def test_materialize_emits_arms_controls_and_no_aggregates():
    px = _panel()
    res = CE.materialize(px)
    df, meta = res["rows"], res["meta"]
    assert len(df) > 0
    for arm in CE.ARMS:
        assert f"tw_{arm}" in df.columns
    assert "control" in df.columns
    assert "no_aggregates_note" in meta
    # the meta must not contain any cross-arm comparison
    assert not any("beats" in str(v).lower() or "wins" in str(v).lower()
                   for v in meta.values())


def test_materialize_is_deterministic():
    px = _panel()
    a = CE.materialize(px)["rows"]
    b = CE.materialize(px)["rows"]
    pd.testing.assert_frame_equal(a, b)
