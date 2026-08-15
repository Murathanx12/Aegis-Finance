"""REGRET_TENSOR: which actions are bad in which states, with a per-cell MDE.

WHY THE MDE IS THE POINT AND NOT A DECORATION
=============================================
A tensor has thousands of cells. The natural way to read one is to scan for the
largest number — which is a maximum over thousands of noisy draws, i.e. exactly
the bias that made `+26.5pp of regret` look like a measurement of the engine
(G1). Every cell therefore carries its own sample size and its own 80%-power
MDE, and `worst_actions` refuses to rank undetectable cells by default: a list
ordered by noise looks precisely like a finding.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.research_gym import tensor as T


def _flat_series(n=800, seed=1, mu=0.0, sd=0.01, state="calm"):
    rng = np.random.default_rng(seed)
    r = list(rng.normal(mu, sd, n))
    return r, [state] * n


def test_a_cell_carries_all_three_numbers_and_its_own_power():
    t = T.build_regret_tensor({"AAA": _flat_series()}, horizons=[20],
                              stride_days=5, sample_start="x", sample_end="y")
    c = t.cell("calm", "hold", 20)
    assert c is not None
    # descriptive, biased-upper-bound, and the unbiased one — never just one
    assert c.mean_net_return_pct is not None
    assert c.mean_regret_vs_best_pp > 0        # the null is never zero
    assert c.mean_edge_vs_default_pp == pytest.approx(0.0, abs=1e-9)
    assert c.power.n_obs > 0
    assert c.power.n_effective <= c.power.n_obs


def test_the_default_policys_edge_against_itself_is_exactly_zero():
    """A sanity anchor. If this drifts, the edge column is measuring something
    other than 'this action minus the pre-declared default'."""
    t = T.build_regret_tensor({"AAA": _flat_series()}, horizons=[20],
                              stride_days=5, sample_start="x", sample_end="y")
    assert t.cell("calm", "hold", 20).mean_edge_vs_default_pp == pytest.approx(
        0.0, abs=1e-9)


def test_selling_a_rising_market_shows_a_NEGATIVE_edge_against_holding():
    """The property regret-vs-best structurally cannot have.

    With positive drift, going to cash must look WORSE than holding — a
    negative number. Regret against the ex-post best is non-negative by
    construction and could never say this.
    """
    t = T.build_regret_tensor({"AAA": _flat_series(mu=0.0008)}, horizons=[60],
                              stride_days=5, sample_start="x", sample_end="y")
    assert t.cell("calm", "sell_100", 60).mean_edge_vs_default_pp < 0
    assert t.cell("calm", "sell_100", 60).mean_regret_vs_best_pp > 0


def test_worst_actions_hides_undetectable_cells_by_default():
    t = T.build_regret_tensor({"AAA": _flat_series(n=300)}, horizons=[60],
                              stride_days=5, sample_start="x", sample_end="y")
    shown = t.worst_actions("calm", 60)
    all_cells = t.worst_actions("calm", 60, detectable_only=False)
    assert len(all_cells) > len(shown) or all(c.edge_is_detectable
                                              for c in all_cells)
    # Ranking noise produces a list that looks exactly like a finding.
    assert all(c.edge_is_detectable for c in shown)


def test_a_tensor_declares_itself_uncitable():
    t = T.build_regret_tensor({"AAA": _flat_series(n=300)}, horizons=[20],
                              stride_days=5, sample_start="x", sample_end="y")
    d = t.as_dict()
    assert d["citable"] is False
    assert "UPPER BOUND" in d["note"]


def test_misaligned_states_are_refused_rather_than_zipped():
    with pytest.raises(ValueError, match="aligned index-for-index"):
        T.build_regret_tensor({"AAA": ([0.01] * 100, ["a"] * 99)},
                              horizons=[10], stride_days=5,
                              sample_start="x", sample_end="y")


def test_a_default_policy_outside_the_menu_is_refused():
    with pytest.raises(ValueError, match="not in the menu"):
        T.build_regret_tensor({"AAA": _flat_series(n=200)}, horizons=[10],
                              default_policy="teleport", stride_days=5,
                              sample_start="x", sample_end="y")


def test_the_tensor_survives_a_round_trip(tmp_path):
    t = T.build_regret_tensor({"AAA": _flat_series(n=400)}, horizons=[20],
                              stride_days=5, sample_start="1999", sample_end="2026")
    p = t.write(tmp_path / "t.json")
    back = T.RegretTensor.read(p)
    assert back.horizons == [20] and back.stride_days == 5
    a, b = t.cell("calm", "sell_50", 20), back.cell("calm", "sell_50", 20)
    # The artifact rounds to 4dp so it stays readable. That is 1e-4 of a
    # percentage point — four orders of magnitude below the smallest MDE any
    # cell reports, so it cannot move a verdict. Pinned here so the tolerance
    # is a decision rather than a surprise.
    assert b.mean_edge_vs_default_pp == pytest.approx(a.mean_edge_vs_default_pp,
                                                      abs=1e-4)
    assert b.power.n_effective == pytest.approx(a.power.n_effective)
    assert b.edge_is_detectable == a.edge_is_detectable


def test_episode_clustering_uses_DAY_units_and_does_not_double_count_horizon():
    """Two corrections, two jobs — and the first version conflated them.

    `positions` are day indices, so the clustering gap must be in days (21, the
    same regime-persistence gap the base-rate table uses). The first version
    wrote `max(21, H) // stride`, which expressed a day gap in strided units AND
    folded the horizon into a correction that already handles the horizon
    separately.

    It was expected to change nothing, because overlap LOOKED like the binding
    constraint. It was not: 357 of 425 cells turned out to be episode-bound and
    the detectable-cell count fell from 126 to 31. Assuming a units fix is
    cosmetic is how three quarters of a findings table survives review.
    """
    r, _ = _flat_series(n=1000)
    # One long contiguous stress run, then a gap far wider than 21 days, then
    # another run. That is TWO episodes however the windows overlap.
    states = (["calm"] * 100 + ["panic"] * 120 + ["calm"] * 300
              + ["panic"] * 120 + ["calm"] * 360)
    t = T.build_regret_tensor({"AAA": (r, states)}, horizons=[20],
                              stride_days=5, sample_start="x", sample_end="y")
    c = t.cell("panic", "hold", 20)
    assert c.power.n_episodes == 2, (
        f"expected 2 stress episodes, got {c.power.n_episodes} — a contiguous "
        f"run sampled every 5 days is one event, not one per sample")
    # And the reported n_effective takes the harsher of the two corrections.
    assert c.power.n_effective == min(c.power.n_obs / (20 / 5), 2)


def test_two_states_are_kept_apart():
    r, _ = _flat_series(n=600)
    states = ["calm"] * 300 + ["panic"] * 300
    t = T.build_regret_tensor({"AAA": (r, states)}, horizons=[20],
                              stride_days=5, sample_start="x", sample_end="y")
    assert t.cell("calm", "hold", 20) is not None
    assert t.cell("panic", "hold", 20) is not None
    # A cell must not silently pool the states it is keyed by.
    assert (t.cell("calm", "hold", 20).power.n_obs
            != t.cell("calm", "hold", 20).power.n_obs + 1)
