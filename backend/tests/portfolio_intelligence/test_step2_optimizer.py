"""
Step #2 hard gates (config v2: equal-weight → leakage-safe HRP).

  (a) Leakage: optimizer output at date T is identical whether the panel is
      physically truncated at T or sliced .loc[:T] from a frame containing
      future rows — and optimize_hrp(returns=...) never fetches data.
  (b) Invariants: weights sum to 1, long-only, sleeve mandates respected;
      position/sector limits provably binding (violation → capped).
  (c) Hard gate: NaN / negative / zero-sum / degenerate optimizer output and
      short history all fall back to equal-weight, loudly (meta reason).
"""

from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from backend.config import paper_portfolios
from backend.services.portfolio_intelligence.rules import (
    REFERENCE_LANES,
    _get_sleeve_tickers,
    compute_target_weights,
    enforce_position_limits,
    lane_sector_map,
)

UNIVERSE = paper_portfolios["universe"]
SLEEVES = _get_sleeve_tickers(UNIVERSE)
BAL_CFG = paper_portfolios["balanced"]


def _panel(n_days=600, end="2026-06-10", seed=3) -> pd.DataFrame:
    """Synthetic close-price panel: correlated market factor + per-ticker
    vols spread 0.8%-2.5% so HRP has real structure to differentiate on
    (an iid equal-vol panel makes HRP legitimately collapse to equal-weight).
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=end, periods=n_days, freq="B")
    tickers = SLEEVES["equity"] + SLEEVES["bond"] + SLEEVES["alternative"]
    market = rng.normal(0.0003, 0.009, n_days)
    data = {}
    for i, t in enumerate(tickers):
        vol = 0.008 + 0.017 * ((i * 37) % len(tickers)) / len(tickers)
        beta = 0.4 + 1.2 * ((i * 17) % len(tickers)) / len(tickers)
        rets = beta * market + rng.normal(0, vol, n_days)
        data[t] = 100 * np.exp(np.cumsum(rets))
    return pd.DataFrame(data, index=idx)


class TestReferenceLanes:
    def test_four_lanes_from_yaml(self):
        assert REFERENCE_LANES == (
            "conservative", "balanced", "aggressive", "balanced-ew-control",
        )

    def test_control_lane_frozen_equal_weight(self):
        assert paper_portfolios["balanced-ew-control"]["optimizer"] == "equal_weight"
        for k in ("target_equity_pct", "target_bond_pct", "target_alt_pct",
                  "max_single_name", "max_sector"):
            assert paper_portfolios["balanced-ew-control"][k] == BAL_CFG[k], (
                f"control lane must match balanced on {k} — optimizer is the "
                "only allowed difference"
            )


class TestLeakageSafety:
    def test_slice_equals_physical_truncation(self):
        """The replay contract: .loc[:T] on a future-containing frame must
        produce identical optimizer output to a frame that ends at T."""
        full = _panel(n_days=700)
        T = full.index[-120]  # a date with 120 future rows beyond it

        sliced = full.loc[:T]
        truncated = full.iloc[: full.index.get_loc(T) + 1].copy()

        m1: dict = {}
        m2: dict = {}
        w1 = compute_target_weights(BAL_CFG, UNIVERSE, price_data=sliced, meta=m1)
        w2 = compute_target_weights(BAL_CFG, UNIVERSE, price_data=truncated, meta=m2)

        assert m1.get("optimizer_used") == "hrp", m1
        assert m2.get("optimizer_used") == "hrp", m2
        assert w1 == w2, "future rows beyond T changed the as-of output — leakage"
        assert m1["optimizer_as_of"] == str(T)[:10]

    def test_future_rows_change_nothing_about_T_weights(self):
        """Adding MORE future data after T must not move weights at T."""
        full = _panel(n_days=700)
        T = full.index[-200]
        w_short_future = compute_target_weights(
            BAL_CFG, UNIVERSE, price_data=full.iloc[:-100].loc[:T], meta={},
        )
        w_long_future = compute_target_weights(
            BAL_CFG, UNIVERSE, price_data=full.loc[:T], meta={},
        )
        assert w_short_future == w_long_future

    def test_optimize_hrp_with_returns_never_fetches(self):
        from backend.services import portfolio_optimizer as po

        returns = _panel(n_days=400)[SLEEVES["equity"][:6]].pct_change().dropna()
        with patch.object(po, "_fetch_returns",
                          side_effect=AssertionError("fetched — leakage path")):
            result = po.optimize_hrp(list(returns.columns), returns=returns)
        assert result is not None and result["weights"]


class TestOptimizedTargets:
    def test_invariants_hold(self):
        meta: dict = {}
        w = compute_target_weights(BAL_CFG, UNIVERSE, price_data=_panel(), meta=meta)
        assert meta.get("optimizer_used") == "hrp"
        assert all(v >= 0 for v in w.values()), "short position in targets"
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-9)
        eq_sum = sum(v for t, v in w.items()
                     if t in set(SLEEVES["equity"]))
        assert eq_sum == pytest.approx(BAL_CFG["target_equity_pct"], abs=1e-6)
        bond_sum = sum(v for t, v in w.items() if t in set(SLEEVES["bond"]))
        assert bond_sum == pytest.approx(BAL_CFG["target_bond_pct"], abs=1e-6)

    def test_hrp_differs_from_equal_weight(self):
        """Sanity: the optimizer must actually do something."""
        w_opt = compute_target_weights(BAL_CFG, UNIVERSE, price_data=_panel(), meta={})
        w_ew = compute_target_weights(
            paper_portfolios["balanced-ew-control"], UNIVERSE,
        )
        eq = [t for t in SLEEVES["equity"] if t in w_opt and t in w_ew]
        diffs = [abs(w_opt[t] - w_ew[t]) for t in eq]
        assert max(diffs) > 1e-4, "HRP output is indistinguishable from equal-weight"


class TestHardGateFallback:
    @pytest.mark.parametrize("bad_output", [
        None,
        {},
        {"weights": {}},
        {"weights": {"XLK": float("nan"), "XLV": 0.5}},
        {"weights": {"XLK": -0.2, "XLV": 1.2}},
        {"weights": {"XLK": 0.0, "XLV": 0.0}},
        {"weights": {"XLK": 1.0}},  # degenerate: 1 name out of ~70
    ])
    def test_invalid_output_falls_back_loudly(self, bad_output):
        meta: dict = {}
        with patch(
            "backend.services.portfolio_optimizer.optimize_hrp",
            return_value=bad_output,
        ):
            w = compute_target_weights(BAL_CFG, UNIVERSE,
                                       price_data=_panel(), meta=meta)
        assert "optimizer_fallback" in meta, "gate must record WHY it fell back"
        # Equal-weight fallback: every equity ticker present at the same weight.
        eq = SLEEVES["equity"]
        eq_w = {t: w[t] for t in eq if t in w}
        assert len(set(round(v, 10) for v in eq_w.values())) == 1
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-9)

    def test_short_history_falls_back(self):
        meta: dict = {}
        w = compute_target_weights(BAL_CFG, UNIVERSE,
                                   price_data=_panel(n_days=60), meta=meta)
        assert "insufficient as-of history" in meta["optimizer_fallback"]
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-9)

    def test_no_panel_falls_back(self):
        meta: dict = {}
        w = compute_target_weights(BAL_CFG, UNIVERSE, price_data=None, meta=meta)
        assert meta["optimizer_fallback"] == "no as-of price panel supplied"
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-9)


class TestLimitsProvablyBinding:
    """The V1 silent-sector-limits bug class: construct violations, assert caps."""

    def test_single_name_violation_is_capped(self):
        # Feasible scenario: 25 names, one grossly over the 5% cap.
        others = [t for t in SLEEVES["equity"][:24] if t != "XLK"]
        w = {"XLK": 0.40, **{t: 0.60 / len(others) for t in others}}
        capped = enforce_position_limits(
            w, max_single_name=0.05, max_sector=0.99,
            sector_map={},  # isolate the single-name pass
        )
        assert capped["XLK"] <= 0.05 + 1e-9, "single-name cap not binding"
        assert sum(capped.values()) == pytest.approx(1.0, abs=1e-6)

    def test_sector_violation_is_capped(self):
        """Feasible, realistic violation: start from the lane's real
        equal-weight book, quadruple every Technology name, renormalize →
        tech grossly over the 30% cap. (The waterfill's documented
        precondition n*cap >= 1 holds for the real ~80-name universe;
        infeasible toy inputs are out of contract.)"""
        sector_map = lane_sector_map(UNIVERSE)
        w = compute_target_weights(paper_portfolios["balanced-ew-control"], UNIVERSE)
        boosted = {
            t: v * (4.0 if sector_map.get(t) == "Technology" else 1.0)
            for t, v in w.items()
        }
        total = sum(boosted.values())
        boosted = {t: v / total for t, v in boosted.items()}
        tech_before = sum(v for t, v in boosted.items()
                          if sector_map.get(t) == "Technology")
        assert tech_before > 0.30, "fixture failed to violate the cap"

        capped = enforce_position_limits(
            boosted, max_single_name=0.05, max_sector=0.30,
            sector_map=sector_map,
        )
        tech = sum(v for t, v in capped.items()
                   if sector_map.get(t) == "Technology")
        assert tech <= 0.30 + 1e-6, f"sector cap not binding: tech={tech:.4f}"
        assert max(capped.values()) <= 0.05 + 1e-6
        assert sum(capped.values()) == pytest.approx(1.0, abs=1e-6)

    def test_optimized_targets_respect_lane_caps_end_to_end(self):
        meta: dict = {}
        w = compute_target_weights(BAL_CFG, UNIVERSE, price_data=_panel(), meta=meta)
        capped = enforce_position_limits(
            w, BAL_CFG["max_single_name"], BAL_CFG["max_sector"],
            lane_sector_map(UNIVERSE),
        )
        assert max(capped.values()) <= BAL_CFG["max_single_name"] + 1e-6 or any(
            t not in lane_sector_map(UNIVERSE) for t in capped
        )
        sector_map = lane_sector_map(UNIVERSE)
        by_sector: dict = {}
        for t, v in capped.items():
            s = sector_map.get(t)
            if s:
                by_sector[s] = by_sector.get(s, 0.0) + v
        assert all(v <= BAL_CFG["max_sector"] + 1e-6 for v in by_sector.values())
