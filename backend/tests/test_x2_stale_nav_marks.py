"""X2 — a lane NAV that was not re-marked at the close is EXCLUDED from beta.

WHAT HAPPENED. G7 read the website paper lanes and printed beta first, as the
product ruler requires — and the beta column was biased toward zero. The Dimson
lead/lag diagnostic said why: `conviction` loads **0.6072** on today's market
and **1.3990** on YESTERDAY'S (joint OLS; Dimson sum 1.9313, OLS beta 0.7163,
R2 vs SPY 0.05 on 41 observations). A book cannot respond to the market a day
late. Its PRICES can, and these do — the program caches prices with a TTL, so
a lane NAV can repeat the previous close on a session when the market moved.

That repeat is not an observation of a flat day. It is a fabricated zero
return, and it lands in the numerator of every covariance the row reports. The
amendment's rule is "beta is allowed, hidden beta is not"; a carried mark hides
it. Until now the diagnostic *reported* the problem and every number was
computed on the polluted series anyway.

X2 makes the diagnosis operative. `mark_freshness` stamps each session, and
`admissible_returns_from_nav` drops **two** sessions per carried mark:

  * the carried session itself, whose return is a fabricated 0.0%;
  * the session after it, whose return spans the gap — a multi-session return
    regressed on a one-session market. Keeping it MOVES the bias rather than
    removing it, and that is the mistake this file exists to prevent.

The known answer below is the roadmap's own test, on a world where the answer
is planted: the raw series reports a beta of 0.65 for a book whose true beta is
1.20 and puts a third of that loading on YESTERDAY'S market; after exclusion the
lagged loading falls to a twentieth of the contemporaneous one and beta comes
back to 1.18.

WHAT THIS DOES **NOT** REPAIR, said plainly rather than left for a reader to
discover. There are two physical failures and a (date, level) series can only
see one of them:

  * a CARRIED mark repeats the previous level -- visible, dropped, repaired;
  * a mark that is uniformly ONE SESSION OLD changes every day and repeats
    nothing. `test_a_uniformly_one_session_old_mark_is_reported_not_repaired`
    plants exactly that and shows the exclusion only partly helps (lag 0.84 ->
    0.74 against a contemporaneous 0.35 -> 0.45). For that case the row is
    stamped `beta_admissible_as_exposure = False` and the reader is told the
    OLS beta is not this book's exposure -- which is a REFUSAL, not a repair.
    Whether `conviction` is the first failure, the second, or both cannot be
    determined from the NAV series alone; it needs the marking timestamps,
    which the track-record snapshot does not carry.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import growth_g7_forward_lanes as G7


def _world(n: int = 500, beta: float = 1.20, stale_share: float = 0.50,
           seed: int = 20260907, mode: str = "carry"):
    """A daily world whose NAV is mis-marked on `stale_share` of the sessions.

    TWO MODES, because there are two physical failures and only one of them is
    visible in a (date, level) series:

      * `carry` -- the price cache returned the SAME level again, so the mark
        REPEATS. Detectable, and the one X2 repairs.
      * `oneday` -- every mis-marked session prices YESTERDAY'S close, so the
        level changes every day and nothing repeats. This is the `conviction`
        shape; it is detectable only by the lead/lag regression and it is NOT
        repairable by dropping rows. The test below says so out loud.

    Dates are a fixed historical span, never "today + k": a fixture that encodes
    a calendar moment fails the day after that moment passes (CLAUDE.md,
    session-start protocol item 5).
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-02", periods=n)
    spy = pd.Series(rng.normal(0.0004, 0.010, n), index=idx)
    book = beta * spy + pd.Series(rng.normal(0.0, 0.002, n), index=idx)

    true_nav = (1.0 + book).cumprod()

    stale = pd.Series(rng.random(n) < stale_share, index=idx)
    stale.iloc[0] = False                       # nothing to carry on day one
    marked = true_nav.to_numpy().copy()
    truth = true_nav.to_numpy()
    for i in range(1, n):
        if bool(stale.iloc[i]):
            marked[i] = truth[i - 1] if mode == "oneday" else marked[i - 1]
    return pd.Series(marked, index=idx), true_nav, spy, stale


def _lead_lag(returns: pd.Series, spy: pd.Series) -> dict:
    return G7.lead_lag_beta(returns, spy.reindex(returns.index).dropna())


# ------------------------------------------------------------ the stamping

def test_a_carried_mark_on_a_moving_day_is_stamped_stale():
    marked, _true, spy, stale = _world()
    fr = G7.mark_freshness(marked, spy)
    flagged = fr["stale"].fillna(False)
    planted = stale.reindex(fr.index).fillna(False)
    # every flagged session really was carried
    assert bool((planted[flagged]).all())
    # and nearly all carried sessions are caught -- the misses are the days the
    # market itself moved less than the floor, which are not evidence.
    caught = float(flagged[planted].mean())
    assert caught > 0.90, caught


def test_a_flat_book_on_a_flat_market_is_not_stale():
    """A book really can be flat on a flat day; calling that stale would
    delete real observations."""
    idx = pd.bdate_range("2024-01-02", periods=30)
    nav = pd.Series(100.0, index=idx)
    spy = pd.Series(0.0, index=idx)
    fr = G7.mark_freshness(nav, spy)
    assert not bool(fr["stale"].fillna(False).any())


def test_the_floor_is_declared_not_inline():
    assert G7.STALE_MARK_MARKET_MOVE == 0.0010


# ------------------------------------------------------------ the exclusion

def test_both_the_carried_session_and_the_one_after_it_are_dropped():
    idx = pd.bdate_range("2024-01-02", periods=5)
    nav = pd.Series([100.0, 101.0, 101.0, 103.0, 104.0], index=idx)
    spy = pd.Series([0.0, 0.01, 0.01, 0.01, 0.01], index=idx)
    kept, note = G7.admissible_returns_from_nav(nav, spy)
    assert note["stale_marks"] == 1
    assert note["returns_before_exclusion"] == 4
    assert note["returns_after_exclusion"] == 2
    assert list(kept.index) == [idx[1], idx[4]]


def test_the_note_counts_what_it_threw_away():
    marked, _true, spy, _stale = _world()
    _kept, note = G7.admissible_returns_from_nav(marked, spy)
    assert note["stale_marks"] > 0
    assert note["returns_excluded"] >= note["stale_marks"]
    assert 0.0 < note["share_stale"] < 1.0
    assert note["first_stale_mark"] and note["last_stale_mark"]
    assert "official close" in note["rule"]


# --------------------------------- THE KNOWN ANSWER: the Dimson lead/lag test

def test_carried_marks_hide_beta_and_exclusion_gives_it_back():
    """THE KNOWN ANSWER. Planted beta 1.20, half the marks carried.

    RAW:   beta is a LIE -- the contemporaneous loading collapses toward zero
           and a sixth of it reappears on YESTERDAY'S market.
    AFTER: the lagged loading falls to a small fraction of the contemporaneous
           one, and the contemporaneous one IS the planted beta.
    """
    marked, _true, spy, _stale = _world(beta=1.20, mode="carry")

    raw = G7.returns_from_nav(marked)
    before = _lead_lag(raw, spy)
    assert before["beta_contemporaneous_joint"] < 0.80, before   # 1.20 planted
    ratio_before = abs(before["beta_on_lagged_market_joint"]) / abs(
        before["beta_contemporaneous_joint"])
    assert ratio_before > 0.20, before

    kept, note = G7.admissible_returns_from_nav(marked, spy)
    after = _lead_lag(kept, spy)
    ratio_after = abs(after["beta_on_lagged_market_joint"]) / abs(
        after["beta_contemporaneous_joint"])

    # THE ROADMAP'S TEST: the lagged loading below the contemporaneous one --
    # and by an order of magnitude more than it was.
    assert abs(after["beta_on_lagged_market_joint"]) < abs(
        after["beta_contemporaneous_joint"]), after
    assert ratio_after < ratio_before / 3.0, (ratio_before, ratio_after)
    assert after["stale_marks_suspected"] is False, after
    assert after["beta_contemporaneous_joint"] == pytest.approx(1.20, abs=0.06)
    assert note["returns_excluded"] > 0


def test_a_uniformly_one_session_old_mark_is_reported_not_repaired():
    """THE OTHER KNOWN ANSWER, and the honest limit of X2.

    Every mis-marked session prices yesterday's close, so nothing repeats and
    nothing is droppable. This is the `conviction` shape -- the lagged loading
    EXCEEDS the contemporaneous one -- and the exclusion cannot repair it. What
    the row must do is REFUSE to call its OLS beta the exposure.
    """
    marked, _true, spy, _stale = _world(beta=1.20, stale_share=0.70,
                                        mode="oneday")
    raw = G7.returns_from_nav(marked)
    before = _lead_lag(raw, spy)
    assert before["stale_marks_suspected"] is True, before
    assert abs(before["beta_on_lagged_market_joint"]) > abs(
        before["beta_contemporaneous_joint"]), before

    kept, note = G7.admissible_returns_from_nav(marked, spy)
    after = _lead_lag(kept, spy)
    # still stale: the exclusion has nothing to remove that would fix this.
    assert after["stale_marks_suspected"] is True, after

    rf = pd.Series(0.0, index=spy.index)
    row = G7.lane_row("planted_one_session_old", kept, spy, rf,
                      source="unit test", cost_basis="none (synthetic)",
                      mark_note=note)
    assert row["beta_admissible_as_exposure"] is False
    assert "STALE MARKS" in row["headline"]


def test_the_clean_series_is_unharmed_by_the_exclusion():
    """A lane that WAS re-marked every session loses nothing."""
    _marked, true_nav, spy, _stale = _world()
    kept, note = G7.admissible_returns_from_nav(true_nav, spy)
    raw = G7.returns_from_nav(true_nav)
    assert note["stale_marks"] == 0
    assert note["returns_excluded"] == 0
    pd.testing.assert_series_equal(kept, raw)


# ------------------------------------------------------------- the row keys

def test_a_clean_row_declares_its_beta_admissible():
    _marked, true_nav, spy, _stale = _world(n=250)
    kept, note = G7.admissible_returns_from_nav(true_nav, spy)
    rf = pd.Series(0.0, index=spy.index)
    row = G7.lane_row("clean", kept, spy, rf, source="unit test",
                      cost_basis="none (synthetic)", mark_note=note)
    assert row["beta_admissible_as_exposure"] is True
    assert row["stale_marks_excluded"]["stale_marks"] == 0


def test_the_row_carries_the_exclusion_and_beta_is_still_first():
    marked, _true, spy, _stale = _world(n=200)
    kept, note = G7.admissible_returns_from_nav(marked, spy)
    rf = pd.Series(0.00002, index=spy.index)
    row = G7.lane_row("planted", kept, spy, rf, source="unit test",
                      cost_basis="none (synthetic)", mark_note=note)
    assert list(row)[0] == "beta"
    assert row["verdict"] == "OK"
    assert row["stale_marks_excluded"]["stale_marks"] == note["stale_marks"]
    assert row["n_obs"] == len(kept)


def test_returns_handed_in_directly_report_cannot_determine_not_zero():
    """`None` means freshness was never judged. That is a different statement
    from "no stale marks" and the row may not collapse them."""
    _marked, true_nav, spy, _stale = _world(n=200)
    rf = pd.Series(0.00002, index=spy.index)
    row = G7.lane_row("planted", G7.returns_from_nav(true_nav), spy, rf,
                      source="unit test", cost_basis="none (synthetic)")
    assert row["stale_marks_excluded"] is None


def test_a_refusal_row_also_carries_the_key_in_the_same_place():
    """A guard that only checks the happy path passes while the refusals
    reorder themselves -- the shape of guard this program has learned catches
    nothing (`test_growth_g7_lanes` docstring)."""
    idx = pd.bdate_range("2024-01-02", periods=6)
    short = pd.Series(np.linspace(0.001, 0.006, 6), index=idx)
    spy = pd.Series(0.001, index=idx)
    rf = pd.Series(0.0, index=idx)
    row = G7.lane_row("tiny", short, spy, rf, source="unit test",
                      cost_basis="none (synthetic)")
    assert row["verdict"] == "CANNOT DETERMINE"
    assert list(row)[0] == "beta"
    assert "stale_marks_excluded" in row
    assert "beta_admissible_as_exposure" in row
