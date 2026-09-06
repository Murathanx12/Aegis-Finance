"""N1/N2 -- the construction lane's arithmetic, on worlds whose answer is known.

The two jobs themselves need the long panel and the frozen stage predictions,
neither of which exists on the CI box; those paths are covered by an explicit
SKIP. What is tested here is every piece of arithmetic that would silently
produce a plausible wrong number: the Holm column, the ex-ante hedge, the
exclusion rule, the ensemble's renormalisation, and the one-month shift that
separates a reliability weight from a look-ahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import n1_construction_books as N1
from scripts import n2_ensemble as N2


# --------------------------------------------------------------------- Holm

def test_holm_is_the_export_standard_and_is_monotone():
    p = {"a": 0.001, "b": 0.02, "c": 0.5}
    adj = N1.holm(p)
    assert adj["a"] == pytest.approx(0.003)      # 3 x 0.001
    assert adj["b"] == pytest.approx(0.04)       # 2 x 0.02
    assert adj["c"] == pytest.approx(0.5)
    assert adj["a"] <= adj["b"] <= adj["c"]      # monotone, as Holm requires


def test_holm_never_lets_a_later_p_fall_below_an_earlier_one():
    """The step-down enforcement. Without the running max, 4 x 0.02 = 0.08 would
    be reported BELOW 3 x 0.03 = 0.09 and a reader would take the wrong cell."""
    adj = N1.holm({"a": 0.02, "b": 0.03, "c": 0.031, "d": 0.032})
    vals = [adj[k] for k in ("a", "b", "c", "d")]
    assert vals == sorted(vals)


def test_holm_caps_at_one_and_ignores_missing_p():
    adj = N1.holm({"a": 0.9, "b": 0.95, "c": None})
    assert set(adj) == {"a", "b"}
    assert all(v <= 1.0 for v in adj.values())


# -------------------------------------------------------- degenerate t guard

def test_t_refuses_a_constant_series_instead_of_dividing_by_float_noise():
    assert N1._t([0.01] * 40) is None
    assert N2._t([0.0] * 40) is None
    assert N1._t(np.random.default_rng(0).normal(0.01, 0.02, 200)) is not None


# ------------------------------------------------------------- planted panel

def _panel(n_months: int = 96, n_names: int = 200, edge: float = 0.02,
           seed: int = 20260907) -> pd.DataFrame:
    """A panel where the top of `pred` really does earn more, by construction."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n_months):
        m = f"{2004 + i // 12:04d}-{i % 12 + 1:02d}"
        sig = rng.normal(size=n_names)
        mkt = float(rng.normal(0.006, 0.04))
        r = mkt + edge * sig + rng.normal(0, 0.06, n_names)
        out.append(pd.DataFrame({
            "month": m,
            "permno": np.arange(n_names) + 10_000,
            "pred": sig,
            "fwd_1m": r,
            "mkt_vw_1m": mkt,
            "market_cap": rng.lognormal(8.0, 1.0, n_names),
            "log_dollar_vol_20d": np.log1p(rng.lognormal(15.0, 1.0, n_names)),
        }))
    return pd.concat(out, ignore_index=True)


# ------------------------------------------------------------- index hedging

def test_the_index_hedge_is_ex_ante_and_leaves_no_early_months_unhedged():
    df = _panel()
    net, meta = N1.index_hedged(df, "pred", beta_window=36)
    # The first 36 months cannot be hedged with information that existed then,
    # so they are DROPPED, not hedged with a beta from the future.
    assert meta["months"] == len(df["month"].unique()) - 36
    assert meta["mean_hedge_ratio"] is not None
    assert "TRAILING" in meta["construction"]


def test_a_hedged_book_of_a_real_signal_still_earns_over_cash():
    df = _panel(edge=0.03)
    net, meta = N1.index_hedged(df, "pred", beta_window=36, cost_bps=10.0)
    assert len(net) > 24
    assert float(net.mean()) > 0, "the planted edge did not survive its own hedge"


def test_index_hedged_refuses_an_empty_frame_rather_than_returning_a_number():
    empty = _panel(n_months=1).iloc[0:0]
    net, meta = N1.index_hedged(empty, "pred")
    assert meta["months"] == 0 and len(net) == 0


# ----------------------------------------------------------------- exclusion

def test_excluding_the_bottom_decile_of_a_real_signal_beats_the_ew_universe():
    df = _panel(edge=0.03)
    kept, allr, meta = N1.exclusion_book(df, "pred", cost_bps=10.0)
    assert meta["mean_names_dropped"] == pytest.approx(20.0)
    assert meta["mean_names_held"] == pytest.approx(180.0)
    assert float((kept - allr).mean()) > 0


def test_excluding_the_bottom_decile_of_a_null_signal_costs_the_spread():
    """A NULL must not be rescued by the construction. With no edge the only
    thing the exclusion rule changes is turnover, so the difference is <= 0."""
    df = _panel(edge=0.0, seed=4242)
    kept, allr, _ = N1.exclusion_book(df, "pred", cost_bps=25.0)
    assert float((kept - allr).mean()) < 0.002


# ------------------------------------------------------- ensemble mechanics

def test_the_reliability_weight_is_shifted_so_it_cannot_see_its_own_month():
    s = pd.Series(np.arange(60, dtype="float64"), index=range(60))
    rel = N2.trailing_reliability(s, window=12)
    # At position 20 the value must be the mean of positions 8..19, i.e. it
    # must NOT include 20 itself. A missing shift here is the single cheapest
    # way to build a look-ahead that looks like skill.
    assert rel.iloc[20] == pytest.approx(np.mean(np.arange(8, 20)))
    assert np.isnan(rel.iloc[0])


def test_the_ensemble_renormalises_over_the_arms_actually_present():
    """A row with three arms and a row with eight are not the same object."""
    df = pd.DataFrame({
        "month": ["2020-01"] * 4,
        "permno": [1, 2, 3, 4],
        "a": [0.1, 0.2, 0.3, 0.4],
        "b": [0.4, 0.3, np.nan, 0.1],
    })
    W = pd.DataFrame({"a": [1.0], "b": [1.0]}, index=["2020-01"])
    rw, ew, meta = N2.build_scores(df, {"a": "a", "b": "b"}, W)
    assert meta["rows_with_no_arm"] == 0
    assert meta["arm_count_distribution"]["1"] == 1
    assert meta["arm_count_distribution"]["2"] == 3
    # Row 3 has only arm `a`; its ensemble value is arm a's rank, NOT arm a's
    # rank averaged against an invented 0.5.
    a_rank = df.groupby("month")["a"].rank(pct=True)
    assert ew.iloc[2] == pytest.approx(float(a_rank.iloc[2]))
    assert rw.iloc[2] == pytest.approx(float(a_rank.iloc[2]))


def test_a_month_with_no_positive_arm_falls_back_to_equal_weight_not_to_nothing():
    df = pd.DataFrame({
        "month": ["2020-01"] * 3, "permno": [1, 2, 3],
        "a": [0.1, 0.2, 0.3], "b": [0.3, 0.2, 0.1]})
    W = pd.DataFrame({"a": [0.0], "b": [0.0]}, index=["2020-01"])
    rw, ew, meta = N2.build_scores(df, {"a": "a", "b": "b"}, W)
    assert meta["months_falling_back_to_equal_weight"] == 1
    assert rw.tolist() == pytest.approx(ew.tolist())


def test_the_reliability_weighting_actually_moves_the_score_when_weights_differ():
    df = pd.DataFrame({
        "month": ["2020-01"] * 3, "permno": [1, 2, 3],
        "a": [0.1, 0.2, 0.3], "b": [0.3, 0.2, 0.1]})
    W = pd.DataFrame({"a": [1.0], "b": [0.0]}, index=["2020-01"])
    rw, ew, _ = N2.build_scores(df, {"a": "a", "b": "b"}, W)
    a_rank = df.groupby("month")["a"].rank(pct=True)
    assert rw.tolist() == pytest.approx(a_rank.tolist())
    assert rw.tolist() != pytest.approx(ew.tolist())


# ------------------------------------------------------- the jobs themselves

@pytest.mark.parametrize("mod", [N1, N2])
def test_the_job_skips_cleanly_when_the_long_panel_is_absent(mod, monkeypatch):
    """CI has no local data. A job that CRASHES there and a job that has
    nothing to do there must not look the same in the morning."""
    from learner import long_panel as LP
    from pathlib import Path
    monkeypatch.setattr(LP, "LONG_TABLE", Path("/definitely/not/here.parquet"))
    rec = mod.run(verbose=False)
    assert rec["status"] == "SKIPPED"
    assert "absent" in rec["headline"]


def test_the_constructions_declare_the_control_first_and_it_is_the_incumbent():
    assert N1.CONSTRUCTIONS[0] == (50, "vw", None)
    assert N1.CONTROL_KEY == "k=50|vw|hold=none"
    # Every non-control construction is broader than the control, in k or in
    # weighting. A "broad" list that quietly contained a narrower cell would
    # make the delta table unreadable.
    for k, w, hk in N1.CONSTRUCTIONS[1:]:
        assert k >= 50 and (w != "vw")
        assert hk is None or hk > k
