"""FACTORIAL-PM-1 — the defects that would silently change a matrix cell.

Fast and offline: every test runs on small synthetic price frames (plus the
frozen local CSV where book identity itself is under test). Each test guards
one way a cell could be wrong with nothing downstream to contradict it:
seeds that drift, an exposure path that peeks one day ahead, an audit that
invents rules instead of refusing, and B3 collapsing to a single draw.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import factorial_pm as F


# ── synthetic panel helpers ─────────────────────────────────────────────────

def _panel(n_names: int = 6, n_days: int = 220, seed: int = 7,
           start: str = "2025-10-27") -> pd.DataFrame:
    """A wide close-price frame spanning warm-up + the trial window."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n_days)
    # per-name daily vol 5% -> an IID 6-name book runs ~30% annualized, so
    # the M2 vol-target actually bites (exposure < 1) in these tests
    rets = rng.normal(0.0005, 0.05, size=(n_days, n_names))
    px = 50 * np.exp(np.cumsum(rets, axis=0))
    return pd.DataFrame(px, index=idx,
                        columns=[f"T{i}" for i in range(n_names)])


# ── reproducibility under the registered seed ───────────────────────────────

def test_matrix_cells_reproducible_under_seed():
    panel = _panel()
    tickers = list(panel.columns)
    for fn in (F.m1_cell, F.m2_cell, F.m4_cell):
        a, b = fn(panel, tickers), fn(panel, tickers)
        assert a["terminal_wealth"] == b["terminal_wealth"]
    p1 = F.paired_terminal_diff(F.m2_cell(panel, tickers)["daily_returns"],
                                F.m1_cell(panel, tickers)["daily_returns"],
                                n_boot=200, seed=123)
    p2 = F.paired_terminal_diff(F.m2_cell(panel, tickers)["daily_returns"],
                                F.m1_cell(panel, tickers)["daily_returns"],
                                n_boot=200, seed=123)
    assert p1 == p2


def test_b3_draws_reproducible_and_registered_seed():
    pool = [f"N{i:02d}" for i in range(61)]
    a = F.b3_draws(pool, n_draws=5)
    b = F.b3_draws(pool, n_draws=5)
    assert a == b, "the B3 cell is a seeded distribution; a drifting seed " \
                   "silently changes the null the matrix is compared to"
    assert all(len(d) == 13 and len(set(d)) == 13 for d in a)


# ── M2: the one-day lag is load-bearing (leak check) ────────────────────────

def test_m2_exposure_lags_returns_by_one_day():
    """Perturbing day T+1's returns must NEVER change the exposure applied on
    day T+1 — that decision was made at close of day T. If this fails, the
    vol-target is trading on information it does not have yet."""
    panel = _panel(seed=11)
    tickers = list(panel.columns)
    base = F.m2_cell(panel, tickers)
    w_base = base["exposure_path"]

    t_perturb = 40                       # a mid-window return day
    day = w_base.index[t_perturb]
    panel2 = panel.copy()
    # a violent shock on `day` (the return ending that day)
    panel2.loc[day:, :] = panel2.loc[day:, :] * 0.80
    w_pert = F.m2_cell(panel2, tickers)["exposure_path"]

    # exposure decided at T (applied to the perturbed day itself): unchanged
    assert w_pert.iloc[:t_perturb + 1].equals(w_base.iloc[:t_perturb + 1]), \
        "exposure on the shock day (and before) must not see the shock"
    # ...and the shock IS allowed to move exposure afterwards (sanity that the
    # perturbation reached the sigma estimator at all)
    assert not np.allclose(w_pert.iloc[t_perturb + 1:],
                           w_base.iloc[t_perturb + 1:])


def test_m2_exposure_is_capped_at_one_and_nonnegative():
    panel = _panel(seed=3)
    c = F.m2_cell(panel, list(panel.columns))
    w = c["exposure_path"]
    assert float(w.max()) <= 1.0 + 1e-12 and float(w.min()) >= 0.0


# ── M3: the audit refuses; it never invents rules ───────────────────────────

UNMECHANIZABLE = {
    "A": {"text": "cash runway falls below 12 months", "provenance": "x"},
    "B": {"text": "consensus target falls below entry", "provenance": "x"},
    "C": {"text": "narrative rotation; dilution at these levels",
          "provenance": "x"},
    "D": {"text": "", "provenance": ""},
}


def test_m3_audit_refuses_unmechanizable_conditions():
    audit = F.m3_audit(["A", "B", "C", "D"], conditions=UNMECHANIZABLE)
    assert audit["status"] == "REFUSED_NOT_MECHANIZABLE"
    assert audit["n_checkable"] == 0
    reasons = {r["ticker"]: r["reason"] for r in audit["per_name"]}
    assert "fundamentals" in reasons["A"]
    assert "analyst" in reasons["B"]
    assert "no kill condition on record" in reasons["D"]
    # and no row was silently converted into a rule
    assert all(not r["checkable"] for r in audit["per_name"])


def test_m3_audit_only_explicit_price_rules_are_checkable():
    conds = {
        "P": {"text": "exit if the close falls below 5.00", "provenance": "x"},
        "Q": {"text": "exit if revenue misses two quarters", "provenance": "x"},
    }
    audit = F.m3_audit(["P", "Q"], conditions=conds)
    rows = {r["ticker"]: r for r in audit["per_name"]}
    assert rows["P"]["checkable"] and rows["P"]["required_feeds"] == [
        "price_history"]
    assert not rows["Q"]["checkable"]
    assert audit["fraction_checkable"] == 0.5    # >= 50% -> not refused
    assert audit["status"] == "CHECKABLE"


def test_m3_real_books_are_refused_on_the_frozen_data():
    """On the data actually on hand, no book reaches 50% checkable — the
    expected finding, asserted so a future silent 'improvement' that starts
    inventing rules gets caught."""
    books = F.load_books()
    for bk in ("B1", "B2"):
        audit = F.m3_audit(books[bk])
        assert audit["status"] == "REFUSED_NOT_MECHANIZABLE", (bk, audit)


# ── B3 is a distribution, never one draw ────────────────────────────────────

def test_b3_never_collapsed_to_a_single_draw():
    pool = [f"N{i:02d}" for i in range(61)]
    with pytest.raises(ValueError, match="DISTRIBUTION"):
        F.b3_draws(pool, n_draws=1)
    with pytest.raises(ValueError, match="DISTRIBUTION"):
        F.b3_draws(pool, n_draws=0)


def test_b3_draws_vary_across_the_distribution():
    pool = [f"N{i:02d}" for i in range(61)]
    draws = F.b3_draws(pool, n_draws=50)
    assert len({tuple(d) for d in draws}) > 45, \
        "50 random 13-of-61 draws collapsing to few distinct sets means the " \
        "rng is not advancing — the 'distribution' would be one draw in " \
        "disguise"


# ── book identity (frozen data) ─────────────────────────────────────────────

def test_books_are_13_48_61_or_the_trial_voids():
    books = F.load_books()
    assert len(books["B1"]) == 13
    assert len(books["B2"]) == 48
    assert len(books["pool"]) == 61
    assert not set(books["B1"]) & set(books["B2"])


# ── managements agree where they must ───────────────────────────────────────

def test_m1_terminal_equals_mean_of_name_returns():
    panel = _panel(seed=5)
    tickers = list(panel.columns)
    c = F.m1_cell(panel, tickers)
    px = panel.loc[F.WINDOW_START:F.WINDOW_END, tickers]
    expected = float((px.iloc[-1] / px.iloc[0]).mean())
    assert abs(c["terminal_wealth"] - expected) < 1e-12


def test_m2_at_infinite_target_would_be_m1():
    """With the vol target far above realized vol the exposure pins at 1.0
    and M2's path must reproduce M1's exactly (costs included: zero)."""
    panel = _panel(seed=13)
    tickers = list(panel.columns)
    old = F.M2_VOL_TARGET
    try:
        F.M2_VOL_TARGET = 50.0
        c2 = F.m2_cell(panel, tickers)
    finally:
        F.M2_VOL_TARGET = old
    c1 = F.m1_cell(panel, tickers)
    assert abs(c2["terminal_wealth"] - c1["terminal_wealth"]) < 1e-9
    assert c2["total_cost_paid_pts"] == 0.0


def test_m4_hrp_gate_cannot_pass_on_a_short_panel_and_says_so():
    panel = _panel(n_days=220)     # < 252 obs, like the frozen 197-bar panel
    c = F.m4_cell(panel, list(panel.columns))
    assert c["hrp_ever_passed_its_gate"] is False
    assert all("fallback" in r["optimizer"] or r["reason"] == "initialization"
               for r in c["rebalances"])


def test_m4_single_name_cap_waterfill():
    # n * cap must be >= 1.0 for the cap to be satisfiable (engine invariant)
    w = F._enforce_single_name_cap(
        {"A": 0.6, "B": 0.1, "C": 0.1, "D": 0.1, "E": 0.1}, 0.25)
    assert w["A"] == pytest.approx(0.25)
    assert sum(w.values()) == pytest.approx(1.0)
    assert all(v <= 0.25 + 1e-9 for v in w.values())


# ── the bootstrap machinery ─────────────────────────────────────────────────

def test_circular_block_sums_match_bruteforce():
    x = np.arange(10.0)
    s = F._circ_roll_sums(x, 3)
    brute = np.array([x[np.arange(i, i + 3) % 10].sum() for i in range(10)])
    assert np.allclose(s, brute)


def test_paired_diff_of_identical_legs_is_zero_with_zero_se():
    panel = _panel(seed=17)
    r = F.m1_cell(panel, list(panel.columns))["daily_returns"]
    res = F.paired_terminal_diff(r, r, n_boot=100, seed=1)
    assert res["difference_pts"] == 0.0
    assert res["se_pts"] == 0.0
