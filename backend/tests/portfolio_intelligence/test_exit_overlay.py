"""
Offline tests for the ATR exit-overlay decision core (TRIAL-EXIT, checklist item
1). Deterministic price paths exercise the hold/exit decision and the vol cap.
"""

import numpy as np
import pandas as pd

from backend.services.portfolio_intelligence.exit_overlay import (
    evaluate_exit_overlay, vol_capped_weights,
)


def _series(vals, start="2026-01-02"):
    idx = pd.bdate_range(start=start, periods=len(vals))
    return pd.Series(vals, index=idx, dtype=float)


class TestExitDecision:
    def test_monotonic_winner_is_held(self):
        # steadily rising → stop never fires → hold (let the winner run)
        prices = {"WIN": _series([10 + 0.5 * i for i in range(60)])}
        out = evaluate_exit_overlay({"WIN": {}}, prices, atr_multiple=3.0)
        assert out["WIN"]["action"] == "hold"
        assert out["WIN"]["reason"] == "end_of_data"

    def test_rollover_winner_is_stopped_out(self):
        # rise to a peak then crash → trailing stop fires → exit, with a positive
        # max-favorable (it WAS a winner before rolling over)
        up = [10 + i for i in range(40)]
        down = [50 - 3 * i for i in range(20)]
        out = evaluate_exit_overlay({"X": {}}, {"X": _series(up + down)}, atr_multiple=3.0)
        assert out["X"]["action"] == "exit"
        assert out["X"]["reason"] == "trailing_stop"
        assert out["X"]["max_favorable_pct"] > 0

    def test_insufficient_data_holds(self):
        assert evaluate_exit_overlay({"A": {}}, {"A": _series([10.0])})["A"]["action"] == "hold"
        assert evaluate_exit_overlay({"A": {}}, {})["A"]["action"] == "hold"

    def test_entry_date_alignment(self):
        # crash happens BEFORE the entry date → from entry it only rises → hold
        vals = [50 - 3 * i for i in range(15)] + [5 + i for i in range(45)]
        s = _series(vals)
        entry = s.index[15].date().isoformat()
        out = evaluate_exit_overlay({"A": {"entry_date": entry}}, {"A": s}, atr_multiple=3.0)
        assert out["A"]["action"] == "hold"


class TestVolCap:
    def test_violent_name_trimmed_and_renormalised(self):
        rng = np.random.default_rng(0)
        calm = list(rng.normal(0, 0.002, 80))     # low vol
        wild = list(rng.normal(0, 0.06, 80))      # high vol → should be capped
        base = {"CALM": 0.5, "WILD": 0.5}
        out = vol_capped_weights(base, {"CALM": calm, "WILD": wild},
                                 target_vol=0.20, max_weight=0.30)
        assert out["WILD"] < out["CALM"]                  # violent name trimmed
        assert abs(sum(out.values()) - 1.0) < 1e-6        # renormalised to total

    def test_zero_total_is_safe(self):
        assert vol_capped_weights({}, {}) == {}
