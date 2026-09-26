"""xs_ranker.top_k_backtest keys by-year / LOO on the period the money was HELD.

Review 2026-09-27 §4b (the factory defect, carried to xs_ranker by the
adjudication): a 21-session hold entered on the last session of a year earns its
whole return in the NEXT year, so it belongs to that year. The decision-keyed
tables ride along one release as `*_decision`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.services import xs_ranker as XR


def _oos(dates_and_rel: list[tuple[str, float]]) -> pd.DataFrame:
    rows = []
    for d, rel in dates_and_rel:
        for i, sym in enumerate(("AAA", "BBB")):
            rows.append({"symbol": sym, "date": pd.Timestamp(d), "score": float(1 - i),
                         "fwd_rel": rel if i == 0 else 0.0, "median_dollar_vol": 5e8})
    return pd.DataFrame(rows)


def test_hold_end_of_a_last_session_of_the_year_is_in_the_next_year():
    ends = XR.hold_end_dates(["2023-12-29", "2023-06-30"], 21)
    assert ends[0].year == 2024 and ends[0].month == 1
    assert ends[1].year == 2023


def test_a_21_session_hold_entered_on_the_last_session_lands_in_the_next_year():
    # the only paying date is the last session of 2023; everything else is flat
    rows = [("2023-12-29", 0.10)] + [(str(d.date()), 0.0)
                                     for d in pd.bdate_range("2023-03-01", "2023-10-31")]
    rows += [(str(d.date()), 0.0) for d in pd.bdate_range("2024-03-01", "2024-10-31")]
    bt = XR.top_k_backtest(_oos(rows), k=1, cost=False, horizon=21)
    # hold-keyed: the December-29 decision is a 2024 hold
    assert bt["by_year"]["2024"]["mean_net"] > 0
    assert bt["by_year"]["2023"]["mean_net"] == 0.0
    assert bt["by_year"]["2024"]["n_dates"] == bt["by_year_decision"]["2024"]["n_dates"] + 1
    # the deprecated decision key puts it in 2023
    assert bt["by_year_decision"]["2023"]["mean_net"] > 0
    assert bt["by_year_decision"]["2024"]["mean_net"] == 0.0
    # LOO: dropping 2024 removes the paying date under the hold key
    assert bt["loo_worst_dropped_year"] == "2024"
    assert bt["loo_worst_dropped_year_decision"] == "2023"
    assert bt["leave_one_year_out"]["2024"] == 0.0
    assert bt["share_of_total_by_year"]["2024"] == 1.0
    assert bt["share_of_total_by_year_decision"]["2023"] == 1.0
    assert bt["share_of_total_top1pct_decision_dates"][0] == "2023-12-29"
    assert bt["share_of_total_top1pct_hold_ends"][0].startswith("2024-01")
    assert "DEPRECATED" in bt["decision_key_status"]


def test_the_sweep_fields_keep_their_shape():
    """night_horizon_sweep reads by_year / loo_worst_mean_net / loo_worst_dropped_year."""
    rng = np.random.default_rng(3)
    rows = [(str(d.date()), float(rng.normal(0.001, 0.01)))
            for d in pd.bdate_range("2022-01-03", "2024-11-29")]
    bt = XR.top_k_backtest(_oos(rows), k=1, horizon=63)
    assert bt["hold_horizon_sessions"] == 63
    assert set(bt["by_year"]["2023"]) == {"mean_net", "n_dates"}
    assert isinstance(bt["loo_worst_mean_net"], float)
    assert bt["loo_worst_dropped_year"] in bt["by_year"]
    # a 63-session hold decided from October on ends in the next year
    assert bt["by_year"]["2025"]["n_dates"] > 0 and "2025" not in bt["by_year_decision"]
