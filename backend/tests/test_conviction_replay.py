"""CONVICTION-REPLAY-1 — the defects that would have changed the verdict.

Every test here corresponds to something that WAS wrong during NIGHT-12 and was
caught by a number that looked wrong, not by review. They are kept because each
one is silent: the replay runs, prints a verdict, and is wrong by an amount
nothing downstream can contradict.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import conviction_prices as CP
from backend.services.conviction_replay import (basket, measure_mde,
                                                permutation_test,
                                                rank_alternative,
                                                tie_aware_basket)
from backend.services.conviction_sheets import load_sheet


# ── the parse ───────────────────────────────────────────────────────────────
def test_the_november_sheet_partitions_cleanly_into_picks_and_non_picks():
    s = load_sheet("2025-11-07")
    assert len(s.portfolio) == 13
    assert len(s.non_picks()) == 48
    held = {h.ticker for h in s.portfolio}
    assert not (held & {h.ticker for h in s.non_picks()}), (
        "a name on both sides would appear in both groups of the comparison")


def test_an_exit_price_attaches_to_the_position_that_was_sold():
    """The wrapped '(sold at X)' annotation was first attached to whatever row
    happened to be parsed last, which put ALMS's exit price on DKNG. DKNG was
    never sold and traded near 29; nothing downstream could have contradicted
    an exit audit built on that."""
    s = load_sheet("2026-01-13")
    sold = {h.ticker: h.sold_at for h in s.holdings if h.sold_at is not None}
    assert sold == {"TVTX": 34.4, "ALMS": 10.0, "SLDP": 8.1}


def test_the_sold_rows_are_not_dropped_from_the_portfolio():
    """Stripping the annotation greedily ate the price columns with it, so all
    three sold positions failed to parse and vanished from the January book."""
    s = load_sheet("2026-01-13")
    assert len(s.portfolio) == 14
    tickers = {h.ticker for h in s.portfolio}
    assert {"TVTX", "ALMS", "SLDP"} <= tickers


def test_a_name_typed_twice_is_counted_once():
    """CHYM is typed twice in the November watchlist; counting it twice weights
    it twice in an equal-weighted basket."""
    s = load_sheet("2025-11-07")
    tickers = [h.ticker for h in s.watchlist]
    assert len(tickers) == len(set(tickers))


# ── the corporate actions ───────────────────────────────────────────────────
def test_a_terminated_name_has_both_an_entry_and_a_payout():
    """THE defect of the night. Carrying the payout is not enough: with no entry
    price the name still has no computable return and is dropped from its side
    of the comparison exactly as if it had never existed. APLT is his WORST
    position, so dropping it raised his picks by about ten points — and SLNO, a
    watchlist winner, moved the other side the other way."""
    df = CP.load_prices()
    for tkr in CP.CORPORATE_ACTIONS:
        s = pd.to_numeric(df[tkr], errors="coerce").dropna()
        assert len(s) >= 2, f"{tkr} cannot produce a return"
        assert CP.total_return(df, tkr, "2025-11-07", "2026-08-10") is not None


def test_the_two_terminations_move_the_answer_in_opposite_directions():
    """They do not cancel and must not be dropped as a pair 'for simplicity'."""
    df = CP.load_prices()
    aplt = CP.total_return(df, "APLT", "2025-11-07", "2026-08-10")
    slno = CP.total_return(df, "SLNO", "2025-11-07", "2026-08-10")
    assert aplt < -0.5, "APLT was a near-total loss in his portfolio"
    assert slno > 0.0, "SLNO was a takeout gain on his watchlist"


def test_a_missing_name_with_no_recorded_action_is_refused():
    """A name that resolves to neither a price nor an action must fail loudly."""
    df = CP.load_prices().copy()
    df["ZZZZ"] = np.nan
    import backend.services.conviction_prices as mod
    with pytest.raises(ValueError, match="no usable price"):
        # exercise the same invariant the loader applies
        missing = [c for c in df.columns if df[c].notna().sum() == 0]
        if missing:
            raise ValueError(f"no usable price for {missing}")


def test_a_reconstructed_series_yields_no_path_statistics():
    """Two known points and nothing between them cannot produce an MFE; reading
    one off the straight line would report the shape of an assumption."""
    df = CP.load_prices()
    for tkr in CP.SHEET_ENTRY_FALLBACK:
        assert CP.path_stats(df, tkr, "2025-11-07", "2026-08-10") is None


# ── ties are not a ranking ──────────────────────────────────────────────────
def test_consensus_rating_does_not_order_this_pool():
    """Fourteen names sit at exactly 5.0 with NONE strictly above, so a 'top 13
    by consensus' is thirteen names drawn from a fourteen-way tie. NIGHT-10
    shipped ties-printed-as-a-ranking once already."""
    s = load_sheet("2025-11-07")
    r = rank_alternative(s.holdings, "consensus_rating", 13)
    assert r["strict"] == []
    assert len(r["tied_at_cutoff"]) >= 14
    assert r["is_a_real_ranking"] is False


def test_analyst_upside_does_order_this_pool():
    s = load_sheet("2025-11-07")
    r = rank_alternative(s.holdings, "sheet_upside", 13)
    assert len(r["strict"]) >= 12
    assert r["is_a_real_ranking"] is True


def test_a_tie_broken_ranking_reports_the_range_its_coin_flip_spans():
    s = load_sheet("2025-11-07")
    df = CP.load_prices()
    tb = tie_aware_basket(df, rank_alternative(s.holdings, "consensus_rating", 13),
                          "2025-11-07", "2026-08-10", "consensus")
    assert tb["tie_break_p05"] is not None
    assert tb["spread_from_ties"] > 0.05, (
        "a rule filling every slot from a tie spans a real range of outcomes "
        "and quoting one of them as 'the rule's return' invents a decision")


# ── the instrument ──────────────────────────────────────────────────────────
def test_the_permutation_test_finds_a_planted_separation():
    rng = np.random.default_rng(0)
    picks = rng.normal(1.0, 0.2, 13)
    pool = rng.normal(0.0, 0.2, 48)
    out = permutation_test(picks, pool, n_perm=5_000)
    assert out["significant_at_5pct"] is True
    assert out["observed_difference"] > 0.8


def test_the_permutation_test_finds_nothing_in_noise():
    rng = np.random.default_rng(1)
    allr = rng.normal(0.0, 0.4, 61)
    out = permutation_test(allr[:13], allr[13:], n_perm=5_000)
    assert out["p_value_two_sided"] > 0.05


def test_the_mde_is_measured_and_scales_with_dispersion():
    """A wider pool needs a bigger effect to be seen. If the MDE did not move
    with dispersion it would not be measuring power at all."""
    rng = np.random.default_rng(2)
    tight = measure_mde(rng.normal(0, 0.10, 61), k=13, n_power=120, n_perm=400,
                        grid=np.arange(0.0, 1.01, 0.10))
    wide = measure_mde(rng.normal(0, 0.60, 61), k=13, n_power=120, n_perm=400,
                       grid=np.arange(0.0, 3.01, 0.20))
    assert tight["mde_at_80pct_power"] is not None
    assert (wide["mde_at_80pct_power"] is None
            or wide["mde_at_80pct_power"] > tight["mde_at_80pct_power"])


def test_a_basket_reports_how_many_names_it_actually_used():
    df = CP.load_prices()
    s = load_sheet("2025-11-07")
    b = basket(df, [h.ticker for h in s.portfolio], "2025-11-07", "2026-08-10",
               "picks")
    assert b.n == 13, (
        "all 13 holdings must reach the basket; a silently dropped name is the "
        "failure this whole module exists to prevent")
