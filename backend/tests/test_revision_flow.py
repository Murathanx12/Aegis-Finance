"""revision_flow: the analyst-revision FLOW feature, PIT-strict.

The first three tests are chunk C2's, verbatim in intent
(docs/HANDOFF_2026-09-25_FABLE_TO_OPUS_BUILD_PLAN.md). The function lives in
`revision_flow` rather than `analyst_ledger` because `analyst_ledger` reads a
different store (`analyst_snapshots.jsonl`), not the parquet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services.revision_flow import (FLOW_COLUMNS, compute,
                                            compute_panel, rule_score)


def _rev(rows):
    return pd.DataFrame(rows, columns=["ticker", "event_date", "firm", "target_action",
                                       "prior_target", "current_target",
                                       "target_change", "pit_safe"])


def test_flow_is_strictly_before_asof():
    asof = pd.Timestamp("2026-09-24")
    df = _rev([
        ["AAA", pd.Timestamp("2026-09-24"), "F1", "raise", 10, 12, 2, True],   # same day: excluded
        ["AAA", pd.Timestamp("2026-09-20"), "F2", "raise", 10, 11, 1, True],
        ["AAA", pd.Timestamp("2026-09-01"), "F3", "lower", 10, 9, -1, True],
    ])
    out = compute(df, asof=asof, window_days=90)
    assert out.loc["AAA", "net_raises"] == 0            # +1 raise, -1 lower
    assert out.loc["AAA", "n_firms"] == 2


def test_not_pit_safe_rows_are_refused_not_dropped_silently():
    df = _rev([["AAA", pd.Timestamp("2026-09-20"), "F1", "raise", 10, 11, 1, False]])
    with pytest.raises(ValueError, match="pit_safe"):
        compute(df, asof=pd.Timestamp("2026-09-24"))


def test_missing_pit_safe_column_is_refused():
    df = _rev([["AAA", pd.Timestamp("2026-09-20"), "F1", "raise", 10, 11, 1, True]])
    with pytest.raises(ValueError, match="pit_safe"):
        compute(df.drop(columns=["pit_safe"]), asof=pd.Timestamp("2026-09-24"))


def test_window_excludes_old_events():
    df = _rev([["AAA", pd.Timestamp("2026-01-01"), "F1", "raise", 10, 11, 1, True]])
    out = compute(df, asof=pd.Timestamp("2026-09-24"), window_days=90)
    assert "AAA" not in out.index


def test_real_vocabulary_and_columns():
    """The parquet spells actions `Raises`/`Lowers` (and a few `LOwers`)."""
    asof = pd.Timestamp("2026-09-24")
    df = _rev([
        ["AAA", "2026-09-10 13:00:00", "F1", "Raises", 100, 120, 0.2, True],
        ["AAA", "2026-09-11 13:00:00", "F2", "Raises", 100, 110, 0.1, True],
        ["AAA", "2026-09-12 13:00:00", "F2", "LOwers", 110, 99, -0.1, True],
        ["AAA", "2026-09-13 13:00:00", "F3", "Maintains", 50, 50, 0.0, True],
        ["BBB", "2026-09-20 13:00:00", "F9", "Lowers", 20, 10, -0.5, True],
    ])
    out = compute(df, asof=asof)
    assert list(out.columns) == list(FLOW_COLUMNS)
    a = out.loc["AAA"]
    assert a["net_raises"] == 1
    assert a["n_firms"] == 3
    assert a["n_events"] == 4
    # median of +20%, +10%, -10%, 0%  -> +5%
    assert a["median_target_change"] == pytest.approx(0.05)
    assert a["days_since_last"] == pytest.approx((asof - pd.Timestamp("2026-09-13 13:00")).total_seconds() / 86400)
    assert out.loc["BBB", "net_raises"] == -1


def test_median_uses_current_over_prior_not_the_stored_change():
    """`target_change` is already a fraction in the parquet; the C2 fixture used
    dollars. current/prior - 1 agrees with both and cannot be mis-scaled."""
    df = _rev([["AAA", "2026-09-20", "F1", "Raises", 10, 12, 2, True]])
    out = compute(df, asof=pd.Timestamp("2026-09-24"))
    assert out.loc["AAA", "median_target_change"] == pytest.approx(0.2)


def test_panel_matches_pointwise_compute():
    rng = np.random.default_rng(7)
    n = 400
    base = pd.Timestamp("2025-01-01")
    df = pd.DataFrame({
        "ticker": rng.choice(["A", "B", "C", "D"], n),
        "event_date": [base + pd.Timedelta(hours=int(h)) for h in rng.integers(0, 24 * 500, n)],
        "firm": rng.choice([f"F{i}" for i in range(9)], n),
        "target_action": rng.choice(["Raises", "Lowers", "Maintains", ""], n),
        "prior_target": rng.uniform(10, 20, n),
        "current_target": rng.uniform(10, 20, n),
        "target_change": 0.0,
        "pit_safe": True,
    })
    dates = [pd.Timestamp("2025-03-31"), pd.Timestamp("2025-09-30"), pd.Timestamp("2026-05-01")]
    panel = compute_panel(df, dates, window_days=90)
    for d in dates:
        one = compute(df, asof=d, window_days=90)
        got = panel[panel["date"] == d].set_index("ticker")[list(FLOW_COLUMNS)]
        got = got.loc[one.index]
        pd.testing.assert_frame_equal(got.astype(float), one.astype(float),
                                      check_names=False)


def test_panel_refuses_not_pit_safe_too():
    df = _rev([["AAA", pd.Timestamp("2026-09-20"), "F1", "raise", 10, 11, 1, False]])
    with pytest.raises(ValueError, match="pit_safe"):
        compute_panel(df, [pd.Timestamp("2026-09-24")])


def test_rule_score_requires_three_firms():
    flow = pd.DataFrame({"net_raises": [5, 10, -2], "n_firms": [3, 2, 4],
                         "median_target_change": [0.1, 0.2, -0.1],
                         "days_since_last": [1, 1, 1], "n_events": [5, 10, 4]},
                        index=pd.Index(["A", "B", "C"], name="ticker"))
    s = rule_score(flow, min_firms=3)
    assert "B" not in s.index                       # 2 firms: not ranked
    assert s.loc["A"] == 15 and s.loc["C"] == -8
