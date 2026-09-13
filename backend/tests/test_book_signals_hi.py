"""T2 — Books H and I's signals, on synthetic frames only.

Nothing here reads a parquet, a panel or a receipt. Every frame is built in the
test, and every date is derived from `today`, because a literal quarter in a
fixture is a fixture that fails the day after it passes.

What is pinned, and why each of them is a way the signal could be convincingly
wrong while every number in it was arithmetically right:

  1. Book H's QUALIFYING CONDITION is a conjunction, not a difference. A pair
     with two positive means and a big spread is a momentum name; the
     registration excludes it and this file proves the code does too.
  2. Book H aggregates to the issuer by the MEDIAN of its qualifying insiders,
     so one extreme insider cannot carry an issuer into the tercile.
  3. Book I's four legs are four different selections out of ONE function, so
     the falsifier "the divergence must beat either leg alone" cannot differ
     from the book by which code path ran it.
  4. `sell_intensity == 0` is the SIGNAL and `NaN` is a refusal. A caller that
     confused them would trade a different universe silently.
  5. Both signals REFUSE BY NAME on a missing column and on a thin
     cross-section, rather than returning an empty dict that reads as "no name
     qualified this period".
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.services import book_signals as BS


# --------------------------------------------------------------------------
# BOOK H


def _pairs(rows):
    """Pair-level rows: (permno, owner, mean_pre, mean_post, n_prior)."""
    return pd.DataFrame(
        [{"permno": p, "owner_cik": o, "mean_pre": pre, "mean_post": post,
          "n_prior_grants": n} for p, o, pre, post, n in rows])


def test_h_needs_the_conjunction_not_just_a_big_spread():
    """A pair whose pre AND post means are both POSITIVE has a large
    `post - pre` and is a momentum name, not an opportunistically timed grant.
    The registration's qualifying condition excludes it."""
    frame = _pairs([
        (10, "a", -0.05, 0.05, 4),     # qualifies: down into, up out of
        (11, "b", 0.40, 0.90, 4),      # spread 0.50, both positive -> excluded
        (12, "c", -0.02, 0.01, 4),     # qualifies, small
        (13, "d", -0.30, -0.10, 4),    # post negative -> excluded
    ])
    scores = BS.option_grant_timing_score(frame, min_names=1, tercile=0.0)
    assert set(scores) == {10, 12}, (
        "only the pre<0 AND post>0 pairs may carry a score; 11 has the biggest "
        "spread in the frame and must not appear")


def test_h_drops_a_pair_with_too_little_history_rather_than_imputing_one():
    frame = _pairs([
        (20, "a", -0.05, 0.05, BS.MIN_PRIOR_GRANTS),
        (21, "b", -0.90, 0.90, BS.MIN_PRIOR_GRANTS - 1),
    ])
    scores = BS.option_grant_timing_score(frame, min_names=1, tercile=0.0)
    assert set(scores) == {20}
    assert BS.MIN_PRIOR_GRANTS == 3


def test_h_aggregates_an_issuer_by_the_MEDIAN_of_its_insiders():
    """One insider with an extreme pair may not carry an issuer into the cut.
    Issuer 30 has three qualifying insiders at 0.02/0.03/9.00 (median 0.03);
    issuer 31 has one at 0.50. The median rule ranks 31 above 30; a MEAN would
    rank 30 above 31 on the same rows."""
    frame = _pairs([
        (30, "a", -0.01, 0.01, 4),     # 0.02
        (30, "b", -0.01, 0.02, 4),     # 0.03
        (30, "c", -4.00, 5.00, 4),     # 9.00, the outlier
        (31, "d", -0.20, 0.30, 4),     # 0.50
        (32, "e", -0.001, 0.001, 4),   # 0.002
    ])
    scores = BS.option_grant_timing_score(frame, min_names=1, tercile=0.0)
    assert scores[31] > scores[30] > scores[32], (
        "the median of issuer 30's insiders is 0.03, below issuer 31's 0.50; a "
        "mean would be 3.02 and would invert this ordering")


def test_h_refuses_by_name_on_a_missing_column():
    frame = _pairs([(40, "a", -0.05, 0.05, 4)]).drop(columns=["mean_post"])
    with pytest.raises(BS.SignalUnavailable) as exc:
        BS.option_grant_timing_score(frame, min_names=1)
    assert "mean_post" in str(exc.value)
    assert "REFUSAL" in str(exc.value)


def test_h_refuses_a_tercile_over_a_thin_cross_section():
    frame = _pairs([(50 + i, "a", -0.05, 0.05, 4) for i in range(3)])
    with pytest.raises(BS.SignalUnavailable) as exc:
        BS.option_grant_timing_score(frame, min_names=20)
    assert "cut of" in str(exc.value) and "survivors" in str(exc.value)


def test_h_returns_a_strictly_ordered_score_best_first():
    frame = _pairs([(60 + i, "a", -0.01 * (i + 1), 0.01 * (i + 1), 4)
                    for i in range(9)])
    scores = BS.option_grant_timing_score(frame, min_names=1, tercile=0.0)
    order = [p for p, _ in sorted(scores.items(), key=lambda kv: -kv[1])]
    assert order == [68, 67, 66, 65, 64, 63, 62, 61, 60]
    assert len(set(scores.values())) == len(scores), "no two names may tie"


# --------------------------------------------------------------------------
# BOOK I


def _band(rows):
    """(permno, buyback_flag, buyback_intensity, sell_intensity)."""
    return pd.DataFrame(
        [{"permno": p, "buyback_flag": f, "buyback_intensity": bi,
          "sell_intensity": si} for p, f, bi, si in rows])


def _wide_band(n=30, *, flag=True):
    """`n` covered names: intensities spread, selling zero for the first half."""
    return _band([(100 + i, flag, 0.001 * (i + 1),
                   0.0 if i < n // 2 else 0.01 * (i - n // 2 + 1))
                  for i in range(n)])


def test_i_the_divergence_leg_needs_BOTH_conditions():
    """A name that repurchased but is in the top selling tercile is not in the
    book, and a name with no selling that did not repurchase is not either."""
    band = _band([
        (200, True, 0.05, 0.00),    # both -> in
        (201, True, 0.04, 0.90),    # buyback, heavy selling -> out
        (202, False, 0.00, 0.00),   # no buyback -> out
        (203, True, 0.03, 0.01),
        (204, True, 0.02, 0.80),
        (205, True, 0.01, 0.70),
    ])
    div = BS.buyback_insider_divergence(band, leg="divergence", min_names=1)
    assert 202 not in div, "a name without a buyback is not in the conjunction"
    assert 201 not in div and 204 not in div
    assert set(div) == {200, 203}


def test_i_the_divergence_breaks_ties_on_the_BUYBACK_and_not_on_permno():
    """Most covered names sell nothing, so the tie-break is what actually
    orders the book. The registration freezes it as buyback intensity
    DESCENDING -- the purest instance of the conjunction first."""
    band = _band([
        (300, True, 0.01, 0.0),
        (301, True, 0.09, 0.0),   # the biggest buyback, the lowest permno rank
        (302, True, 0.05, 0.0),
    ])
    div = BS.buyback_insider_divergence(band, leg="divergence", min_names=1,
                                        tercile=0.0)
    order = [p for p, _ in sorted(div.items(), key=lambda kv: -kv[1])]
    assert order == [301, 302, 300]


def test_i_zero_selling_is_the_SIGNAL_and_nan_is_a_dropped_row():
    band = _band([
        (400, True, 0.05, 0.0),
        (401, True, 0.05, float("nan")),
        (402, True, 0.04, 0.0),
    ])
    div = BS.buyback_insider_divergence(band, leg="divergence", min_names=1,
                                        tercile=0.0)
    assert 400 in div and 402 in div
    assert 401 not in div, ("a NaN sell intensity is a row this function could "
                            "not score; a zero is a name nobody sold")


def test_i_the_bearish_leg_is_the_MIRROR_of_the_book_and_never_overlaps_it():
    band = _wide_band(30)
    div = BS.buyback_insider_divergence(band, leg="divergence", min_names=1)
    bear = BS.buyback_insider_divergence(band, leg="bearish_divergence",
                                         min_names=1)
    assert div and bear
    assert not (set(div) & set(bear)), (
        "the held tercile and the reported agency-conflict tercile are "
        "disjoint cuts of one variable")


def test_i_the_single_leg_controls_are_DIFFERENT_selections_from_one_function():
    """Section 5 clause 2 compares the divergence against each leg alone. The
    controls must come out of the same function as the book, or the falsifier
    is comparing two implementations."""
    band = _band([
        (500, True, 0.09, 0.50),    # big buyback, heavy selling
        (501, True, 0.01, 0.00),    # small buyback, no selling
        (502, False, 0.00, 0.00),   # no buyback, no selling
        (503, True, 0.05, 0.40),
        (504, True, 0.02, 0.60),
        (505, False, 0.00, 0.70),
    ])
    div = BS.buyback_insider_divergence(band, leg="divergence", min_names=1)
    bb = BS.buyback_insider_divergence(band, leg="buyback_only", min_names=1)
    ls = BS.buyback_insider_divergence(band, leg="low_selling_only",
                                       min_names=1, seed=11)
    assert 502 not in div and 502 not in bb, "both need the buyback flag"
    assert 502 in ls, "the low-selling control ignores the buyback flag"
    assert 500 in bb, "the biggest buyback leads the buyback-only control"
    assert 500 not in div, "it sells heavily, so the conjunction excludes it"


def test_i_the_low_selling_control_does_not_collapse_onto_the_lowest_permnos():
    """Most names have `sell_intensity == 0`, so a permno tie-break would
    return the same names every block -- a size-and-age bet dressed as a
    control. The seeded shuffle is what stops it."""
    band = _band([(600 + i, False, 0.0, 0.0) for i in range(30)])
    a = BS.buyback_insider_divergence(band, leg="low_selling_only",
                                      min_names=1, seed=1)
    b = BS.buyback_insider_divergence(band, leg="low_selling_only",
                                      min_names=1, seed=2)
    top_a = [p for p, _ in sorted(a.items(), key=lambda kv: -kv[1])][:5]
    top_b = [p for p, _ in sorted(b.items(), key=lambda kv: -kv[1])][:5]
    assert top_a != top_b, "two seeds must not draw the same five names"
    assert top_a != sorted(band["permno"])[:5], (
        "and neither may be the five lowest permnos, which is what a permno "
        "tie-break over an all-zero column returns")

    again = BS.buyback_insider_divergence(band, leg="low_selling_only",
                                          min_names=1, seed=1)
    assert again == a, "the same seed must reconstruct the same control"


def test_i_refuses_an_unknown_leg_rather_than_defaulting_to_the_primary():
    with pytest.raises(BS.SignalUnavailable) as exc:
        BS.buyback_insider_divergence(_wide_band(30), leg="whatever",
                                      min_names=1)
    assert "whatever" in str(exc.value)
    assert "defaulted" in str(exc.value)


def test_i_refuses_by_name_on_a_missing_column():
    band = _wide_band(30).drop(columns=["buyback_intensity"])
    with pytest.raises(BS.SignalUnavailable) as exc:
        BS.buyback_insider_divergence(band, min_names=1)
    assert "buyback_intensity" in str(exc.value)


def test_i_refuses_a_tercile_over_a_thin_cross_section():
    with pytest.raises(BS.SignalUnavailable) as exc:
        BS.buyback_insider_divergence(_wide_band(6), min_names=20)
    assert "survivors" in str(exc.value)


def test_i_refuses_when_no_name_carries_the_legs_requirement():
    band = _band([(700 + i, False, 0.0, 0.0) for i in range(5)])
    with pytest.raises(BS.SignalUnavailable) as exc:
        BS.buyback_insider_divergence(band, leg="divergence", min_names=1)
    assert "divergence" in str(exc.value)


def test_both_signals_are_exported_and_their_columns_are_declared():
    assert BS.GRANT_TIMING_COLUMNS == ("permno", "owner_cik", "mean_pre",
                                       "mean_post", "n_prior_grants")
    assert BS.BUYBACK_DIVERGENCE_COLUMNS == ("permno", "buyback_flag",
                                             "buyback_intensity",
                                             "sell_intensity")
    assert BS.BUYBACK_DIVERGENCE_LEGS[0] == "divergence", (
        "the primary must be first; the receipt reads the tuple in order")
