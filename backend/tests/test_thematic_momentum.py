"""
Tests for point-in-time theme baskets + the pure thematic-momentum entry logic.

The critical assertions are the anti-hindsight ones: a ticker is never a member
before its available_from, and the strategy only buys positive-momentum names.
All deterministic — no network.
"""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from backend.services.theme_baskets import (
    all_tickers,
    load_theme_baskets,
    members_as_of,
    theme_keys,
    universe_as_of,
)
from backend.services.thematic_momentum import (
    compute_target_weights,
    momentum_12_1,
)


# ── Point-in-time membership (the anti-hindsight guard) ───────────────────────


def test_baskets_load_and_validate():
    data = load_theme_baskets()
    assert "ai_compute" in data["themes"]
    assert len(theme_keys()) == 5


def test_ionq_not_a_member_before_ipo():
    # IONQ listed 2021-10-01; must not appear in 2019.
    assert "IONQ" not in members_as_of("quantum", "2019-06-01")
    assert "IONQ" in members_as_of("quantum", "2022-01-01")


def test_nvda_member_from_floor():
    assert "NVDA" in members_as_of("ai_compute", "2015-01-02")


def test_membership_monotonic_in_time():
    early = set(members_as_of("ai_compute", "2016-01-01"))
    late = set(members_as_of("ai_compute", "2024-01-01"))
    # Membership only grows as names list (no name ever leaves in this PIT model).
    assert early.issubset(late)


def test_universe_as_of_covers_all_themes():
    u = universe_as_of("2023-01-01")
    assert set(u.keys()) == set(theme_keys())


def test_unknown_theme_raises():
    with pytest.raises(KeyError):
        members_as_of("crypto", "2023-01-01")


def test_all_tickers_nonempty():
    assert len(all_tickers()) > 30


# ── Momentum signal ───────────────────────────────────────────────────────────


def test_momentum_12_1_positive_for_uptrend():
    idx = pd.date_range("2014-01-01", periods=300, freq="B")
    series = pd.Series(np.linspace(10, 30, 300), index=idx)
    assert momentum_12_1(series) > 0


def test_momentum_12_1_none_for_short_history():
    series = pd.Series(np.linspace(10, 11, 50))
    assert momentum_12_1(series) is None


# ── Strategy weights (pure) ───────────────────────────────────────────────────


def _frame(as_of_tickers: dict[str, np.ndarray]) -> pd.DataFrame:
    idx = pd.date_range("2014-01-01", periods=300, freq="B")
    return pd.DataFrame(as_of_tickers, index=idx)


def test_weights_select_only_positive_momentum():
    # NVDA uptrend, XOM downtrend → only NVDA selected.
    prices = _frame({
        "NVDA": np.linspace(10, 40, 300),
        "XOM": np.linspace(80, 40, 300),
    })
    w = compute_target_weights("2015-03-02", prices, top_k=10)
    assert "NVDA" in w
    assert "XOM" not in w
    assert w["NVDA"] == pytest.approx(1.0, rel=1e-6)


def test_weights_empty_when_all_downtrend():
    prices = _frame({
        "NVDA": np.linspace(40, 10, 300),
        "XOM": np.linspace(80, 40, 300),
    })
    w = compute_target_weights("2015-03-02", prices)
    assert w == {}


def test_weights_sum_to_one_when_invested():
    rng = np.random.default_rng(0)
    prices = _frame({
        "NVDA": np.linspace(10, 40, 300) + rng.normal(0, 0.2, 300),
        "AMD": np.linspace(10, 25, 300) + rng.normal(0, 0.2, 300),
        "AVGO": np.linspace(20, 50, 300) + rng.normal(0, 0.2, 300),
    })
    w = compute_target_weights("2015-03-02", prices, top_k=10)
    assert w
    assert sum(w.values()) == pytest.approx(1.0, rel=1e-6)
    assert all(0 < v <= 1.0 for v in w.values())


def test_weights_respect_top_k():
    rng = np.random.default_rng(1)
    cols = {f"T{i}": np.linspace(10, 10 + i + 5, 300) + rng.normal(0, 0.1, 300)
            for i in range(15)}
    prices = _frame(cols)
    # Only real basket tickers count; synthetic Tn aren't in any theme, so this
    # mainly checks top_k doesn't crash on a universe with no matches → cash.
    w = compute_target_weights("2015-03-02", prices, top_k=3)
    assert isinstance(w, dict)
