"""AEGIS-NET-PANEL-1 — the materializer's contract.

The properties tested are the ones whose failure would be silent: a feature
that reads the future, a dead name that vanishes from a complete-looking
table, a non-deterministic panel, an absent source that materializes as an
empty dataset instead of a refusal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import net_panel as NP


def _px(n_days=400, names=("AAA", "BBB", "CCC"), seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n_days)
    data = {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, n_days)))
            for t in names}
    return pd.DataFrame(data, index=idx)


# ── refusals ───────────────────────────────────────────────────────────────
def test_an_absent_price_source_refuses(tmp_path):
    with pytest.raises(NP.PanelRefused, match="absent"):
        NP.load_price_panel(tmp_path / "nope.parquet")


def test_a_shuffled_calendar_refuses(tmp_path):
    px = _px().sample(frac=1.0, random_state=1)      # shuffled index
    p = tmp_path / "shuffled.parquet"
    px.to_parquet(p)
    with pytest.raises(NP.PanelRefused, match="not sorted"):
        NP.load_price_panel(p)


def test_short_history_refuses_features():
    s = pd.Series(np.linspace(100, 110, NP.MIN_HISTORY - 1))
    with pytest.raises(NP.PanelRefused, match="rows"):
        NP.price_features(s)


# ── PIT: the features cannot see past t ────────────────────────────────────
def test_features_do_not_move_when_the_future_is_mutated():
    """The real leak test: recompute the panel after replacing every price
    AFTER each decision date with garbage. Features must be identical;
    only labels may change."""
    px = _px(n_days=320)
    res1 = NP.materialize(px, horizon_days=5)

    px2 = px.copy()
    # garbage the last 30 days — inside every label window, after most t's
    px2.iloc[-30:] = px2.iloc[-30:] * 7.7
    res2 = NP.materialize(px2, horizon_days=5)

    f1 = res1.rows.set_index(["date", "ticker"])[list(NP.FEATURE_COLUMNS)]
    f2 = res2.rows.set_index(["date", "ticker"])[list(NP.FEATURE_COLUMNS)]
    shared = f1.index.intersection(f2.index)
    # Decision dates before the mutated region must have byte-identical
    # features — any drift means a feature read the future.
    cutoff = px.index[-31]
    early = [i for i in shared if i[0] <= cutoff]
    assert early, "test needs at least one decision date before the mutation"
    pd.testing.assert_frame_equal(f1.loc[early], f2.loc[early])


# ── counting, never dropping ───────────────────────────────────────────────
def test_a_dead_name_is_named_in_coverage_not_silently_missing():
    px = _px()
    px["DEAD"] = np.nan
    res = NP.materialize(px, horizon_days=5)
    assert "DEAD" in res.coverage["dead_names"]
    assert "DEAD" not in set(res.rows["ticker"])


def test_a_late_ipo_is_excluded_for_a_counted_reason():
    px = _px(n_days=400)
    late = px["AAA"].copy()
    late.iloc[:300] = np.nan                       # lists 100 days of history
    px["LATE"] = late
    res = NP.materialize(px, horizon_days=5)
    assert res.coverage["excluded_name_dates"]["insufficient_history"] > 0
    assert "LATE" not in set(res.rows["ticker"])


# ── determinism and shape ──────────────────────────────────────────────────
def test_materialization_is_deterministic():
    px = _px()
    r1 = NP.materialize(px, horizon_days=5)
    r2 = NP.materialize(px, horizon_days=5)
    pd.testing.assert_frame_equal(r1.rows, r2.rows)


def test_rows_carry_features_and_every_label_head():
    px = _px()
    res = NP.materialize(px, horizon_days=5)
    cols = set(res.rows.columns)
    for f in NP.FEATURE_COLUMNS:
        assert f in cols
    for head in ("forward_return", "forward_max_drawdown",
                 "forward_realised_vol", "barrier_up20_down10",
                 "barrier_up20_down10_days", "abs_move_exceeds_3",
                 "cs_rank", "cs_decile"):
        assert head in cols, head


def test_decision_dates_are_month_ends_with_history():
    px = _px(n_days=500)
    dates = NP.decision_dates(px)
    assert all(d >= px.index[NP.MIN_HISTORY] for d in dates)
    # one per calendar month, each the month's last trading day
    periods = [d.to_period("M") for d in dates]
    assert len(periods) == len(set(periods))


def test_coverage_declares_absent_families_explicitly():
    """The ablation ladder must know its floor is the data's, not the
    world's — absence is stated, never implied."""
    px = _px()
    res = NP.materialize(px, horizon_days=5)
    fams = res.coverage["feature_families"]
    assert fams["numeric_price"].startswith("AVAILABLE")
    for absent in ("options", "expectations", "event_llm", "semantic_graph"):
        assert fams[absent].startswith("ABSENT")
