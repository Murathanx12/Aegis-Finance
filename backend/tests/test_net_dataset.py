"""The labels' contract: a path statistic cannot leave its horizon, and a
truncated forward window is refused rather than shortened.

Both are failures that show up as BETTER numbers rather than as errors — a
rescaled drawdown looks like a drawdown, and a partial forward window looks like
a complete one — so each is tested against the specific way it would slip
through.
"""

from __future__ import annotations

import math

import pytest

from backend.services import net_dataset as ND


def _ramp(n=120, step=0.01):
    p, out = 100.0, []
    for _ in range(n):
        out.append(p)
        p *= (1.0 + step)
    return out


def _flat(n=120, price=100.0):
    return [price] * n


def _path(moves):
    p, out = 100.0, [100.0]
    for m in moves:
        p *= (1.0 + m)
        out.append(p)
    return out


# ── §65 as a type ──────────────────────────────────────────────────────────
def test_a_path_statistic_refuses_to_be_rescaled():
    """The rule that gets forgotten by someone who has a number at 20 days and
    needs one at 60. `x*sqrt(n'/n)` fits a MEAN; forward, volatility keeps 0.97
    of its size and max drawdown 0.32."""
    dd = ND.forward_max_drawdown(_ramp(), 0, 20)
    with pytest.raises(ND.LabelRefused, match="PATH statistic"):
        dd.scale_to(60)


def test_a_mean_statistic_scales_and_says_so():
    """The contrast that makes the refusal meaningful rather than blanket
    caution: some quantities really do scale, and this one reports that."""
    v = ND.forward_realised_vol(_path([0.01, -0.02, 0.015, -0.005] * 10), 0, 20)
    scaled = v.scale_to(80)
    assert scaled.value == pytest.approx(v.value * 2.0, rel=1e-9)
    assert scaled.horizon_days == 80


def test_the_drawdown_label_carries_its_horizon():
    dd = ND.forward_max_drawdown(_ramp(), 0, 30)
    assert dd.horizon_days == 30 and dd.name == "forward_max_drawdown"


# ── truncated forward windows are refused, not shortened ───────────────────
def test_a_forward_window_running_off_the_end_is_refused():
    """A maximum over 4 days is not a maximum over 20, and a partial label
    looks exactly like a complete one downstream."""
    prices = _ramp(n=30)
    with pytest.raises(ND.LabelRefused, match="runs off the end"):
        ND.forward_max_drawdown(prices, 25, 20)


def test_names_without_a_full_window_are_dropped_and_COUNTED():
    """A cross-section that quietly lost its most recent names is a
    survivorship filter arriving through the back door."""
    panel = {"LONG": _ramp(120), "SHORT": _ramp(25)}
    out = ND.build_labels(panel, t=10, horizon_days=20)
    assert out["n_labelled"] == 1 and out["n_dropped"] == 1
    assert "SHORT" in out["dropped"]


# ── the barrier head ───────────────────────────────────────────────────────
def test_the_up_barrier_is_recorded_with_the_day_it_was_touched():
    prices = _path([0.05] * 6 + [0.0] * 30)     # +5%/day: crosses +20% by day 4
    b = ND.competing_barriers(prices, 0, up=0.20, down=0.10, horizon_days=20)
    assert b["outcome"] == "up" and b["days_to_barrier"] == 4


def test_whichever_barrier_comes_FIRST_is_the_label():
    """The whole point of a competing-barrier head: a name that touched +40% on
    day 3 and ended flat has the same horizon return as one that never moved,
    and a very different meaning for a book that could have acted."""
    prices = _path([0.25, -0.40] + [0.0] * 30)
    b = ND.competing_barriers(prices, 0, up=0.20, down=0.10, horizon_days=20)
    assert b["outcome"] == "up" and b["days_to_barrier"] == 1
    # And the horizon return is deeply negative, which is the point.
    assert ND.forward_return(prices, 0, 20) < -0.2


def test_neither_is_its_own_class_and_is_not_folded_into_down():
    """Collapsing `neither` into `down` would make a quiet name look like a
    loser and put §16's non-winner denominator error into the labels."""
    b = ND.competing_barriers(_flat(), 0, up=0.20, down=0.10, horizon_days=20)
    assert b["outcome"] == "neither" and b["days_to_barrier"] is None


def test_barriers_must_be_positive_magnitudes():
    with pytest.raises(ND.LabelRefused, match="positive magnitudes"):
        ND.competing_barriers(_ramp(), 0, up=0.2, down=-0.1, horizon_days=20)


# ── cross-sectional heads ──────────────────────────────────────────────────
def test_a_rank_over_one_name_is_refused_not_reported_as_a_half():
    """0.5 is a fact about the arithmetic, not about the security, and a panel
    that quietly emits it teaches the network that thin dates are average."""
    with pytest.raises(ND.LabelRefused, match="at least two names"):
        ND.cross_sectional_rank({"ONLY": 0.1})


def test_ranks_span_zero_to_one_and_order_correctly():
    r = ND.cross_sectional_rank({"A": -0.1, "B": 0.0, "C": 0.3})
    assert r["A"] == 0.0 and r["C"] == 1.0 and 0 < r["B"] < 1


def test_deciles_follow_the_ranks():
    vals = {f"T{i}": i / 100.0 for i in range(100)}
    b = ND.quantile_bucket(vals, n_buckets=10)
    assert b["T0"] == 0 and b["T99"] == 9
    assert len(set(b.values())) == 10


def test_a_thin_date_reports_no_cross_section_rather_than_a_fake_one():
    panel = {"ONLY": _ramp(120), "SHORT": _ramp(25)}
    out = ND.build_labels(panel, t=10, horizon_days=20)
    assert out["cross_section_available"] is False
    assert out["rows"]["ONLY"]["cs_rank"] is None


# ── PIT partition ──────────────────────────────────────────────────────────
def test_overlapping_feature_and_label_windows_are_refused():
    """A label that can see its own features shows up as a better AUC rather
    than as an error."""
    with pytest.raises(ND.LabelRefused, match="BOTH"):
        ND.assert_pit_partition([1, 2, 3, 4], [4, 5, 6])


def test_interleaved_windows_are_refused_even_though_they_never_intersect():
    """The subtler leak, and the reason the second check exists.

    Features at {1, 5} and labels at {3, 4} share no index at all, so a
    set-intersection test passes them — and yet the feature at 5 is drawn from
    after the labels begin. Disjointness is necessary and not sufficient; the
    ordering is the property that matters.
    """
    with pytest.raises(ND.LabelRefused, match="strictly BEFORE"):
        ND.assert_pit_partition([1, 5], [3, 4])


def test_a_clean_partition_passes():
    out = ND.assert_pit_partition([1, 2, 3], [4, 5, 6])
    assert out["disjoint"] is True and out["n_feature"] == 3


# ── continuation vs reversal ───────────────────────────────────────────────
def test_continuation_and_reversal_are_read_off_the_forward_window():
    up = _path([0.02] * 30)
    assert ND.continuation_or_reversal(up, 0, event_move=0.15,
                                       horizon_days=20) == "continuation"
    assert ND.continuation_or_reversal(up, 0, event_move=-0.15,
                                       horizon_days=20) == "reversal"


def test_an_event_move_of_zero_has_no_direction_to_continue():
    with pytest.raises(ND.LabelRefused, match="no direction"):
        ND.continuation_or_reversal(_ramp(), 0, event_move=0.0,
                                    horizon_days=20)


# ── the assembled row ──────────────────────────────────────────────────────
def test_every_head_shares_ONE_forward_window():
    """Per-head horizons would make the row a mixture that later gets
    summarised as though it were one."""
    row = ND.label_row(_ramp(), 0, horizon_days=20)
    assert row["horizon_days"] == 20
    assert row["_path_statistics"]["forward_max_drawdown"].horizon_days == 20
    assert row["_mean_statistics"]["forward_realised_vol"].horizon_days == 20


def test_the_row_carries_every_registered_head():
    row = ND.label_row(_path([0.03, -0.01] * 40), 0, horizon_days=20)
    for key in ("forward_return", "forward_max_drawdown",
                "forward_realised_vol", "barrier_up20_down10",
                "barrier_up40_down20", "barrier_up75_down30",
                "abs_move_exceeds_3", "abs_move_exceeds_5",
                "abs_move_exceeds_10"):
        assert key in row, f"missing head {key}"


def test_the_path_statistic_in_a_row_still_refuses_to_rescale():
    """The types are kept alongside the numbers so a consumer that wants to
    rescale has to go through the object that refuses."""
    row = ND.label_row(_ramp(), 0, horizon_days=20)
    with pytest.raises(ND.LabelRefused):
        row["_path_statistics"]["forward_max_drawdown"].scale_to(60)


def test_a_rising_series_has_no_drawdown_and_a_falling_one_does():
    assert ND.forward_max_drawdown(_ramp(), 0, 20).value == pytest.approx(0.0)
    down = _path([-0.02] * 40)
    assert ND.forward_max_drawdown(down, 0, 20).value < -0.3


def test_magnitude_head_matches_the_iif1_observable():
    """Shared deliberately: a network head and the investigator campaign
    scoring the same observable are comparable without a translation layer,
    and a translation layer is where a definition quietly drifts."""
    flat = _flat()
    assert ND.magnitude_exceeds(flat, 0, threshold=0.03, horizon_days=20) == 0
    up = _path([0.01] * 40)
    assert ND.magnitude_exceeds(up, 0, threshold=0.05, horizon_days=20) == 1


def test_build_labels_refuses_when_no_name_has_a_full_window():
    panel = {"A": _ramp(25), "B": _ramp(24)}
    with pytest.raises(ND.LabelRefused, match="no name in the panel"):
        ND.build_labels(panel, t=10, horizon_days=20)


def test_the_dataset_is_deterministic():
    """No RNG anywhere in the label path — a label that moves between runs is
    a label nobody can audit."""
    p = _path([0.01, -0.02, 0.03, -0.01] * 20)
    assert ND.label_row(p, 0, horizon_days=20) == ND.label_row(
        p, 0, horizon_days=20)


def test_forward_volatility_is_finite_and_positive_on_a_moving_series():
    v = ND.forward_realised_vol(_path([0.01, -0.01] * 30), 0, 20)
    assert math.isfinite(v.value) and v.value > 0
