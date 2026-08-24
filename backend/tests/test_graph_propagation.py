"""GRAPH_PROPAGATION_v1 — the licensed signal, and the ways it can lie.

The signal itself is arithmetic and the arithmetic is easy. What is worth
testing is everything around it:

  * `peer_eq` is EQUAL-weighted over distinct peers. The screen's first
    implementation silently computed the shared-count-weighted mean instead,
    which would have reported one arm as two.
  * A truncated vendor feed must REFUSE, not return an empty peer set. META's
    action history stops 2024-09-30 while 62 analysts rate it today; a graph
    that trusts that drops a mega-cap out of the ranking in silence.
  * A decimated universe must refuse rather than rank thinly.
  * The contract is frozen, so its hash must move when a RULE moves.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.services import graph_propagation as gp


# ── the signal ──────────────────────────────────────────────────────────────


def test_peer_eq_is_equal_weighted_not_shared_count_weighted():
    # A and B share THREE brokers; A and C share ONE. Under the equal-weighted
    # definition B and C count once each, so A scores the plain mean (0.0).
    # Under a shared-count weighting B would count three times and A would
    # score +0.05. That difference is the whole distinction between two arms
    # the screen reported separately.
    coverage = {
        "A": frozenset({"f1", "f2", "f3", "f4"}),
        "B": frozenset({"f1", "f2", "f3"}),
        "C": frozenset({"f4"}),
    }
    returns = {"A": 0.0, "B": 0.10, "C": -0.10}
    scores, n_peers = gp.peer_scores(coverage, returns, min_peers=2)
    assert n_peers["A"] == 2
    assert scores["A"] == pytest.approx(0.0)


def test_a_name_below_min_peers_is_unranked_not_zero():
    coverage = {"A": frozenset({"f1"}), "B": frozenset({"f1"})}
    scores, n_peers = gp.peer_scores(coverage, {"A": 0.1, "B": 0.2},
                                     min_peers=3)
    assert n_peers["A"] == 1
    assert "A" not in scores, "a thin name must be absent, never scored 0.0"


def test_a_name_never_scores_off_its_own_return():
    coverage = {t: frozenset({"f1"}) for t in "ABCD"}
    returns = {"A": 1.0, "B": 0.0, "C": 0.0, "D": 0.0}
    scores, _ = gp.peer_scores(coverage, returns, min_peers=3)
    assert scores["A"] == pytest.approx(0.0)
    # ...and A's own +1.0 does show up in everyone else's score.
    assert scores["B"] == pytest.approx(1.0 / 3)


def test_min_shared_raises_the_bar_for_an_edge():
    coverage = {"A": frozenset({"f1", "f2"}), "B": frozenset({"f1", "f2"}),
                "C": frozenset({"f1"})}
    returns = {"A": 0.0, "B": 0.0, "C": 0.0}
    _, n1 = gp.peer_scores(coverage, returns, min_shared=1, min_peers=1)
    _, n2 = gp.peer_scores(coverage, returns, min_shared=2, min_peers=1)
    assert n1["A"] == 2 and n2["A"] == 1


# ── the vendor lying by omission ────────────────────────────────────────────


def _frame(dates, firm="Goldman"):
    return pd.DataFrame(
        {"GradeDate": pd.to_datetime(dates, utc=True),
         "Firm": [firm] * len(dates)}).set_index("GradeDate")


def _reader(frames):
    def read(ticker, as_of, window_months=None):
        import backend.services.graph_propagation as m
        real = m.read_coverage

        class _T:
            def __init__(self, df): self.upgrades_downgrades = df
        import types
        fake = types.SimpleNamespace(Ticker=lambda t: _T(frames.get(t)))
        import sys
        prev = sys.modules.get("yfinance")
        sys.modules["yfinance"] = fake
        try:
            return real(ticker, as_of, window_months)
        finally:
            if prev is None:
                sys.modules.pop("yfinance", None)
            else:
                sys.modules["yfinance"] = prev
    return read


def test_a_truncated_feed_is_STALE_not_empty():
    """META's case. Coverage did not cease; the vendor stopped reporting."""
    read = _reader({"META": _frame(["2024-09-30"])})
    row = read("META", "2026-08-21")
    assert row.status == "STALE"
    assert row.stale_days > 600
    assert row.firms == frozenset(), "a stale feed contributes no edges"
    assert "stopped reporting" in row.detail


def test_a_merely_quiet_name_is_still_OK():
    read = _reader({"PEP": _frame(["2026-07-21"])})
    row = read("PEP", "2026-08-21")
    assert row.status == "OK"
    assert row.firms == frozenset({"Goldman"})


def test_actions_after_as_of_cannot_inform_the_decision():
    read = _reader({"X": _frame(["2026-07-01", "2026-09-30"])})
    row = read("X", "2026-08-21")
    assert row.newest_action == "2026-07-01", "PIT violated: saw the future"


def test_actions_before_the_window_are_outside_the_graph():
    read = _reader({"X": _frame(["2024-01-01", "2026-08-01"])})
    row = read("X", "2026-08-21", window_months=12)
    assert row.status == "OK" and row.firms == frozenset({"Goldman"})


def test_an_empty_vendor_frame_is_EMPTY_not_an_exception():
    read = _reader({"X": pd.DataFrame()})
    assert read("X", "2026-08-21").status == "EMPTY"


# ── refusing a decimated universe ───────────────────────────────────────────


def _cov_reader(mapping):
    def read(ticker, as_of, window_months=None):
        firms = mapping.get(ticker)
        if firms is None:
            return gp.CoverageRow(ticker, frozenset(), None, None, "EMPTY", "")
        return gp.CoverageRow(ticker, frozenset(firms), "2026-08-01", 20, "OK")
    return read


def test_a_healthy_cross_section_ranks():
    uni = [f"T{i}" for i in range(10)]
    cov = {t: {"f1", "f2"} for t in uni}
    sig = gp.build_signal(uni, {t: 0.01 * i for i, t in enumerate(uni)},
                          "2026-08-21", coverage_reader=_cov_reader(cov))
    assert len(sig.scores) == 10
    assert sig.usable_fraction == 1.0
    assert sig.contract_hash == gp.contract_hash()


def test_a_decimated_universe_REFUSES_rather_than_ranking_thinly():
    uni = [f"T{i}" for i in range(10)]
    cov = {t: {"f1", "f2"} for t in uni[:5]}          # half the names vanish
    with pytest.raises(gp.GraphUnavailable) as e:
        gp.build_signal(uni, {t: 0.0 for t in uni}, "2026-08-21",
                        coverage_reader=_cov_reader(cov))
    assert "DIFFERENT universe" in str(e.value)


def test_the_receipt_names_why_each_name_was_dropped():
    uni = [f"T{i}" for i in range(10)]
    cov = {t: {"f1", "f2"} for t in uni[:9]}
    sig = gp.build_signal(uni, {t: 0.0 for t in uni}, "2026-08-21",
                          coverage_reader=_cov_reader(cov))
    r = sig.to_receipt()
    assert r["ranked_n"] == 9 and r["universe_n"] == 10
    assert "T9" in r["excluded"]
    assert r["contract_hash"] == gp.contract_hash()


# ── the frozen contract ─────────────────────────────────────────────────────


def test_the_contract_hash_moves_when_a_RULE_moves():
    before = gp.contract_hash()
    original = gp.CONTRACT["min_peers"]
    try:
        gp.CONTRACT["min_peers"] = original + 1
        assert gp.contract_hash() != before
    finally:
        gp.CONTRACT["min_peers"] = original
    assert gp.contract_hash() == before


def test_the_contract_carries_what_licensed_it():
    lic = gp.CONTRACT["licensed_by"]
    assert lic["spec_hash"] == "0e1578bd0410653b"
    assert "MONTHS" in lic["n_effective"], "n_effective must be DATE BLOCKS"
    # The screen was under-powered by its own design and the contract must not
    # quietly round that away into a claim.
    assert lic["primary_ic"] < lic["mde80"]
    assert "never a claim" in lic["power_note"]


def test_health_names_the_REAL_blocker_first():
    """Two things block registration and they are not equally important.

    The sequencing wait (seeds migrate on the next arena pass) has a date and
    resolves itself. The universe being too dense does not resolve with time —
    it says the mechanism cannot work here at all. Health must lead with the
    one that is not going to fix itself."""
    h = gp.health()
    assert h["status"] == "BLOCKED_UNIVERSE_TOO_DENSE"
    assert "SELECTIVE" in h["reason"]
    assert h["measured"]["corr_peer_eq_with_own_return"] == -1.0
    assert "assert_config_current" in h["also_blocked_by"]


def test_an_isolated_name_does_not_divide_by_zero():
    """`min_peers=0` is a legitimate input — it is what a caller measuring raw
    graph structure passes. `0 < 0` is False, so an isolated name fell straight
    through the guard into `sum(...) / 0`. Found by measuring live graph
    density, not by a test."""
    coverage = {"A": frozenset({"f1"}), "B": frozenset({"f2"})}
    scores, n_peers = gp.peer_scores(coverage, {"A": 0.1, "B": 0.2},
                                     min_peers=0)
    assert n_peers == {"A": 0, "B": 0}
    assert scores == {}, "an isolated name has no peer return, not 0.0"


# ── the degeneracy that the screen's universe could not show ────────────────
#
# On the live 179-name universe the co-coverage graph is 100% dense, because
# every major bank covers every mega-cap. peer_eq then equals (S - r_i)/(n-1),
# a strictly decreasing function of own return: measured corr -1.0000, sd
# 0.0000 over 200 draws. That is short-horizon reversal, which this programme
# has Holm-surviving evidence AGAINST — so the module must refuse it.


def _complete_graph(n=20):
    return {f"T{i}": frozenset({"Goldman"}) for i in range(n)}


def test_a_complete_graph_is_REFUSED_not_ranked():
    cov = _complete_graph()
    rets = {t: (i - 10) / 10 for i, t in enumerate(sorted(cov))}
    scores, _ = gp.peer_scores(cov, rets)
    with pytest.raises(gp.GraphDegenerate) as e:
        gp.assert_graph_informative(cov, scores, rets)
    assert "density" in str(e.value)


def test_the_complete_graph_really_is_minus_own_return():
    """The arithmetic behind the refusal, asserted rather than asserted about."""
    cov = _complete_graph(12)
    rets = {t: float(i) for i, t in enumerate(sorted(cov))}
    scores, _ = gp.peer_scores(cov, rets)
    total = sum(rets.values())
    n = len(cov)
    for t, sc in scores.items():
        assert sc == pytest.approx((total - rets[t]) / (n - 1))
    xs = [scores[t] for t in sorted(scores)]
    ys = [rets[t] for t in sorted(scores)]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = sum((a - mx) ** 2 for a in xs) ** 0.5
    dy = sum((b - my) ** 2 for b in ys) ** 0.5
    assert num / (dx * dy) == pytest.approx(-1.0)


def test_a_sparse_graph_PASSES_the_same_check():
    """Disjoint clusters: dense inside, no edges between.

    Returns come from a SEEDED generator. The first version used `hash(t)`,
    which Python salts per process, so the correlation moved run to run and the
    test failed only under some interpreter starts — a nondeterministic input
    in a test asserting a threshold.

    With several clusters and independent returns the covariance of `peer_eq`
    with own return is zero in expectation: Cov(S_c - r_i, r_i) = Var(r_i) -
    Var(r_i) = 0. The complete graph is the degenerate case precisely because
    ONE cluster makes S constant across the cross-section, leaving -r_i alone.
    """
    import numpy as np

    rng = np.random.default_rng(20260824)
    cov, rets = {}, {}
    for c in range(12):
        for j in range(8):
            t = f"C{c}N{j}"
            cov[t] = frozenset({f"broker{c}"})
            rets[t] = float(rng.normal())
    scores, _ = gp.peer_scores(cov, rets, min_peers=2)
    rep = gp.assert_graph_informative(cov, scores, rets)
    assert rep["edge_density"] < gp.MAX_EDGE_DENSITY
    assert abs(rep["corr_with_own_return"]) < gp.MAX_ABS_OWN_RETURN_CORR


def test_the_guard_refuses_a_graph_too_small_to_judge():
    with pytest.raises(gp.GraphDegenerate):
        gp.assert_graph_informative({"A": frozenset({"f"})}, {}, {})
