"""G1 — the product ruler, on PLANTED worlds where the answer is known.

`ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` §2.2: "a book that wins only by
borrowing beta must say so in its first line; it may still win."

The two planted worlds below are the whole test of that sentence:

* **pure beta** — `b = rf + 1.5*(spy - rf)`. Its leverage-neutral form is
  ALGEBRAICALLY SPY: scaling by vs/vb = 2/3 and parking the third in cash gives
  `(2/3)rf + (spy-rf) + (1/3)rf = spy`, exactly. So a correct ruler must show
  intercept ~ 0, a raw TW win in a rising market, and a leverage-neutral TW
  equal to SPY's to floating point. If the module ever charges financing on a
  DE-levered book, or forgets that unused cash earns RF, this test goes red --
  which is why the identity is used rather than a tolerance band.
* **planted intercept** — the same book plus a constant 0.4%/month. Its
  volatility is unchanged, so the leverage-neutral scale is the same 2/3, and
  the levered-down book must beat SPY by exactly (2/3) of the planted alpha
  compounded. This is the "may still win" half.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from learner import growth as G


def _world(n=240, seed=20260907, alpha=0.0, beta=1.5):
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2000-01", periods=n, freq="M").astype(str)
    spy = pd.Series(rng.normal(0.008, 0.042, n), index=idx)
    rf = pd.Series(np.full(n, 0.0018), index=idx)
    book = rf + beta * (spy - rf) + alpha
    return book, spy, rf


# ------------------------------------------------------------------ mechanics

def test_max_drawdown_is_on_the_compounded_path_not_the_sum():
    r = pd.Series([-0.5, 0.5])
    # sum says zero; wealth says -25%, and the drawdown is measured from the
    # opening dollar (the first peak), which a cumprod alone does not contain.
    assert G.max_drawdown(r) == pytest.approx(-0.5)
    assert G.terminal_wealth(r) == pytest.approx(0.75)


def test_a_first_month_loss_is_a_drawdown_even_though_it_is_also_the_maximum():
    assert G.max_drawdown(pd.Series([-0.30, 0.10, 0.10])) == pytest.approx(-0.30)


def test_cvar_takes_at_least_one_month_on_a_short_sample():
    r = pd.Series([0.01] * 12 + [-0.30])
    assert G.cvar(r, 0.05) == pytest.approx(-0.30)


def test_lever_below_one_parks_the_rest_in_rf_not_in_free_cash():
    b = pd.Series([0.02, -0.01, 0.03])
    rf = pd.Series([0.001, 0.001, 0.001])
    got = G.lever(b, rf, 0.5)
    assert got.tolist() == pytest.approx([0.0105, -0.0045, 0.0155])


def test_lever_above_one_charges_financing_on_the_borrowed_part_only():
    b = pd.Series([0.02, 0.02])
    rf = pd.Series([0.001, 0.001])
    got = G.lever(b, rf, 2.0, financing_bps=120.0)
    spread = 120.0 / 10_000.0 / 12.0
    assert got.tolist() == pytest.approx([2 * 0.02 - (0.001 + spread)] * 2)


def test_cost_bps_is_required():
    b, s, rf = _world(60)
    with pytest.raises(ValueError):
        G.evaluate_growth(b, s, rf, cost_bps=None)


def test_the_ruler_refuses_below_twelve_aligned_months():
    b, s, rf = _world(240)
    got = G.evaluate_growth(b.iloc[:8], s, rf, cost_bps=10.0)
    assert got["verdict"] == "CANNOT DETERMINE"
    assert got["months"] == 8


def test_beta_is_the_first_reported_key_after_the_frame():
    b, s, rf = _world()
    got = G.evaluate_growth(b, s, rf, cost_bps=10.0)
    keys = list(got)
    assert "beta" in keys
    assert keys.index("beta") < keys.index("book"), \
        "beta must be reported before any wealth number (amendment 2.2)"
    assert got["headline"].startswith("beta ")


# ------------------------------------------------------------- planted worlds

def test_pure_beta_book_shows_no_intercept_and_wins_only_on_raw_terminal_wealth():
    b, s, rf = _world(alpha=0.0, beta=1.5)
    got = G.evaluate_growth(b, s, rf, cost_bps=10.0, n_boot=200)

    assert got["beta"] == pytest.approx(1.5, abs=1e-6)
    assert abs(got["market_model"]["intercept_annualised_pct"]) < 1e-6
    # a rising planted market: the levered book wins RAW
    assert got["book"]["terminal_wealth"] > got["spy"]["terminal_wealth"]
    # ... and its leverage-neutral form IS SPY, to floating point
    ln = got["leverage_neutral"]
    assert ln["scale"] == pytest.approx(2.0 / 3.0, abs=1e-4)   # reported to 4 dp
    assert ln["terminal_wealth"] == pytest.approx(got["spy"]["terminal_wealth"],
                                                  rel=1e-6)
    assert ln["beats_spy"] is False


def test_a_planted_intercept_wins_LEVERAGE_NEUTRAL_which_is_the_whole_point():
    b0, s, rf = _world(alpha=0.0, beta=1.5)
    b1, _, _ = _world(alpha=0.004, beta=1.5)

    r0 = G.evaluate_growth(b0, s, rf, cost_bps=10.0, n_boot=200)
    r1 = G.evaluate_growth(b1, s, rf, cost_bps=10.0, n_boot=200)

    assert r1["market_model"]["intercept_annualised_pct"] == pytest.approx(4.8, abs=1e-6)
    assert r1["market_model"]["intercept_t_hac"] > 5.0
    # same volatility => same neutralising scale as the pure-beta twin
    assert r1["leverage_neutral"]["scale"] == pytest.approx(
        r0["leverage_neutral"]["scale"], abs=1e-9)
    assert r1["leverage_neutral"]["beats_spy"] is True
    assert (r1["leverage_neutral"]["terminal_wealth"]
            > r0["leverage_neutral"]["terminal_wealth"])


def test_the_drawdown_budget_is_computed_from_SPYs_own_drawdown():
    b, s, rf = _world(beta=1.5)
    got = G.evaluate_growth(b, s, rf, cost_bps=25.0, n_boot=200)
    c = got["constraints"]
    assert c["maxdd_budget"] == pytest.approx(
        got["spy"]["max_drawdown"] * G.DRAWDOWN_BUDGET_MULT, abs=1e-6)
    # a 1.5x book against a 1.25x budget must FAIL the drawdown constraint
    assert c["maxdd_ok"] is False
    assert c["passes"] is False


def test_admissible_leverage_is_the_largest_size_inside_the_budget():
    b, s, rf = _world(beta=1.5)
    adm = G.admissible_leverage(b, rf, s)
    L = adm["leverage"]
    assert 0.0 < L < 1.0                       # a 1.5-beta book must be cut back
    inside = G.max_drawdown(G.lever(b, rf, L))
    outside = G.max_drawdown(G.lever(b, rf, min(G.GROSS_CAP, L + 0.02)))
    assert abs(inside) <= abs(adm["budget_maxdd"]) + 1e-9
    assert abs(outside) > abs(adm["budget_maxdd"])


def test_admissible_leverage_returns_the_gross_cap_when_the_cap_binds():
    _, s, rf = _world()
    quiet = 0.2 * (s - rf) + rf              # a very low-beta book
    adm = G.admissible_leverage(quiet, rf, s)
    assert adm["leverage"] == pytest.approx(G.GROSS_CAP)
    assert adm["binding"] == "GROSS_CAP"


def test_p_ruin_refuses_a_short_series_rather_than_guessing():
    b, _, _ = _world(10)
    assert G.p_ruin(b)["p_ruin"] is None


def test_p_ruin_is_higher_for_the_more_levered_book_and_is_reproducible():
    b, s, rf = _world(beta=1.0)
    lo = G.p_ruin(G.lever(b, rf, 0.5), n_boot=400, seed=7)["p_ruin"]
    hi = G.p_ruin(G.lever(b, rf, 2.0), n_boot=400, seed=7)["p_ruin"]
    assert hi >= lo
    again = G.p_ruin(G.lever(b, rf, 2.0), n_boot=400, seed=7)["p_ruin"]
    assert again == hi


def test_alignment_is_an_intersection_and_the_count_is_reported():
    b, s, rf = _world(240)
    got = G.evaluate_growth(b, s.iloc[:100], rf, cost_bps=10.0, n_boot=100)
    assert got["months"] == 100
    assert got["window"][0] == s.index[0]
    assert got["window"][1] == s.index[99]


def test_the_levered_spy_rival_is_reported_beside_the_book():
    b, s, rf = _world(beta=1.2)
    got = G.evaluate_growth(b, s, rf, cost_bps=25.0, n_boot=100)
    ls = got["levered_spy_at_budget"]
    assert ls["leverage"] == pytest.approx(G.DRAWDOWN_BUDGET_MULT, rel=0.05), \
        "levering SPY to 1.25x its own drawdown is ~1.25x SPY"
    assert "terminal_wealth" in ls


def test_objective_string_names_every_declared_constraint():
    for token in ("1.25", "1.5", "-40%", "2.0x", "100 bps"):
        assert token in G.OBJECTIVE
