"""The fundamental-law instrument, tested on worlds whose answer is known.

WHY THESE TESTS AND NOT OTHERS
==============================
`learner/fundamental_law.py` exists to say WHICH of three terms killed a book.
An instrument that reports the wrong term is worse than no instrument, because
it re-routes the whole programme: a real signal declared dead by a low IC gets
retired, while the same signal declared dead by a low transfer coefficient gets
REBUILT. So every test here plants a world where one term is known by
construction and checks that the module reads that term and not another.

Nothing here touches disk, the network, or any local-only data file: this whole
module runs identically on the Linux CI box and on the dev machine.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from learner import fundamental_law as FL


# ------------------------------------------------------------------- breadth

def test_equal_weight_k_names_has_effective_breadth_exactly_k():
    for k in (1, 3, 50, 300):
        w = [1.0 / k] * k
        assert FL.effective_breadth(w) == pytest.approx(float(k), rel=1e-12)


def test_one_name_at_full_weight_has_breadth_one_however_many_zeros_follow():
    assert FL.effective_breadth([1.0] + [0.0] * 99) == pytest.approx(1.0)


def test_a_concentrated_value_weighted_book_has_far_fewer_effective_names():
    """The S36 receipt in miniature: 50 names, cap-weighted, ~7 effective."""
    caps = np.array([1000.0] * 3 + [40.0] * 47)      # three mega-caps
    w = caps / caps.sum()
    eff = FL.effective_breadth(w)
    assert eff is not None and eff < 12.0, eff
    assert FL.effective_breadth([1.0 / 50] * 50) == pytest.approx(50.0)


def test_long_short_book_uses_absolute_weights_and_does_not_divide_by_zero():
    w = [0.1] * 5 + [-0.1] * 5                       # sums to exactly zero
    assert FL.effective_breadth(w) == pytest.approx(10.0)


def test_breadth_refuses_on_an_empty_or_all_zero_book():
    assert FL.effective_breadth([]) is None
    assert FL.effective_breadth([0.0, 0.0]) is None


# -------------------------------------------------------- transfer coefficient

def _signal(n: int, seed: int = 7) -> np.ndarray:
    return np.random.default_rng(seed).normal(size=n)


def test_weights_proportional_to_the_signal_transfer_it_perfectly():
    """The unconstrained book. TC must be 1 -- this is the calibration point."""
    n = 200
    s = _signal(n)
    z = (s - s.mean()) / s.std(ddof=1)
    w = 1.0 / n + z * 0.001                          # active part IS the signal
    tc = FL.transfer_coefficient(s, w)
    assert tc == pytest.approx(1.0, abs=1e-9), tc


def test_a_long_only_top_k_book_loses_most_of_the_transfer():
    """The whole thesis, as arithmetic: the SAME signal, two constructions."""
    n, k = 500, 50
    s = _signal(n, seed=11)
    order = np.argsort(-s)
    topk = np.zeros(n)
    topk[order[:k]] = 1.0 / k
    tc_topk = FL.transfer_coefficient(s, topk)

    z = (s - s.mean()) / s.std(ddof=1)
    unconstrained = 1.0 / n + z * 0.001
    tc_free = FL.transfer_coefficient(s, unconstrained)

    assert tc_free == pytest.approx(1.0, abs=1e-9)
    assert tc_topk is not None
    assert tc_topk < tc_free
    # It is not a rounding difference: the top-50-of-500 long-only book keeps
    # well under three quarters of the bet its own signal implies.
    assert tc_topk < 0.75, tc_topk


def test_a_broader_book_transfers_more_of_the_same_signal():
    """N1's claim, isolated: breadth is not free, it is also better TRANSFER."""
    n = 900
    s = _signal(n, seed=13)
    order = np.argsort(-s)
    tcs = {}
    for k in (50, 100, 300):
        w = np.zeros(n)
        w[order[:k]] = 1.0 / k
        tcs[k] = FL.transfer_coefficient(s, w)
    assert tcs[50] < tcs[100] < tcs[300], tcs


def test_an_inverted_book_has_a_negative_transfer_coefficient():
    n = 300
    s = _signal(n, seed=3)
    order = np.argsort(s)                            # buy the WORST 50
    w = np.zeros(n)
    w[order[:50]] = 1.0 / 50
    tc = FL.transfer_coefficient(s, w)
    assert tc is not None and tc < 0, tc


def test_tc_refuses_rather_than_reporting_zero_when_it_cannot_be_measured():
    """A term that could not be measured must not read as a term that is zero."""
    assert FL.transfer_coefficient([1.0] * 50, [0.02] * 50) is None      # constant signal
    assert FL.transfer_coefficient(_signal(5), [0.2] * 5) is None        # too few names
    assert FL.transfer_coefficient(_signal(50), [0.02] * 49) is None     # misaligned


# ------------------------------------------------------------------------ IC

def _planted_panel(n_months: int = 60, n_names: int = 120, ic: float = 0.10,
                   seed: int = 20260907) -> pd.DataFrame:
    """A panel whose cross-sectional IC is planted at `ic` by construction."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_months):
        m = f"{2010 + i // 12:04d}-{i % 12 + 1:02d}"
        sig = rng.normal(size=n_names)
        noise = rng.normal(size=n_names)
        y = ic * sig + math.sqrt(max(0.0, 1 - ic ** 2)) * noise
        rows.append(pd.DataFrame({
            "month": m,
            "permno": np.arange(n_names) + 10_000,
            "pred": sig,
            "fwd_1m": y * 0.05,
            "mkt_vw_1m": 0.004,
            "market_cap": rng.lognormal(mean=8.0, sigma=1.2, size=n_names),
        }))
    return pd.concat(rows, ignore_index=True)


def test_the_planted_ic_is_recovered_within_its_own_sampling_error():
    df = _planted_panel(ic=0.10)
    blk = FL.information_coefficient(df, "pred", "fwd_1m")
    # Spearman on a linear-Gaussian world is ~0.955 x Pearson; the planted 0.10
    # therefore reads ~0.095. The band is generous on purpose -- this test
    # exists to catch a sign flip or a factor of ten, not to pin a third digit.
    assert 0.05 < blk["ic"] < 0.15, blk
    assert blk["months"] == 60
    assert blk["t_ic"] is not None and blk["t_ic"] > 2


def test_a_null_signal_reads_an_ic_of_about_zero():
    df = _planted_panel(ic=0.0, seed=99)
    blk = FL.information_coefficient(df, "pred", "fwd_1m")
    assert abs(blk["ic"]) < 0.03, blk


# ------------------------------------------------------------------- identity

def test_implied_ir_is_the_identity_and_scales_as_the_identity_says():
    assert FL.implied_ir(0.05, 25.0, 1.0) == pytest.approx(
        0.05 * math.sqrt(25.0 * 12) * 1.0)
    # Halving TC halves the implied IR; quadrupling breadth doubles it.
    a = FL.implied_ir(0.08, 50.0, 0.8)
    assert FL.implied_ir(0.08, 50.0, 0.4) == pytest.approx(a / 2)
    assert FL.implied_ir(0.08, 200.0, 0.8) == pytest.approx(a * 2)
    assert FL.implied_ir(None, 50.0, 0.8) is None
    assert FL.implied_ir(0.08, 50.0, None) is None


def test_realised_ir_of_a_constant_series_refuses_rather_than_dividing_by_zero():
    assert FL.realised_ir([0.01] * 40) is None
    assert FL.realised_ir([0.0, 0.0]) is None
    ir = FL.realised_ir(np.random.default_rng(1).normal(0.01, 0.02, 240))
    assert ir is not None and 1.0 < ir < 3.0, ir


# -------------------------------------------------------------------- receipt

def _book_weights(df: pd.DataFrame, k: int, weight: str = "ew") -> dict:
    out = {}
    for m, g in df.groupby("month", sort=True):
        sel = g.sort_values("pred", ascending=False).head(k)
        if weight == "vw":
            w = sel["market_cap"] / sel["market_cap"].sum()
        else:
            w = pd.Series(1.0 / len(sel), index=sel.index)
        out[m] = dict(zip(sel["permno"].astype(int), w.to_numpy()))
    return out


def test_the_receipt_separates_a_construction_defect_from_a_dead_signal():
    """THE test. Same signal, two books; and a null signal in a good book."""
    df = _planted_panel(ic=0.10, n_names=300)
    narrow = FL.receipt(df, "pred", _book_weights(df, 5, "vw"))
    broad = FL.receipt(df, "pred", _book_weights(df, 150, "ew"))

    assert narrow["effective_breadth"]["mean_effective_names_per_month"] < 5.0
    assert broad["effective_breadth"]["mean_effective_names_per_month"] == pytest.approx(150.0)
    assert (narrow["transfer_coefficient"]["tc"]
            < broad["transfer_coefficient"]["tc"])
    assert narrow["construction_verdict"].startswith("CONSTRUCTION_DEFECT")
    assert broad["construction_verdict"].startswith("CONSTRUCTION_OK")
    # The IC is IDENTICAL in both -- it is a property of the forecast, and the
    # difference between the two books is construction alone.
    assert (narrow["information_coefficient"]["ic"]
            == broad["information_coefficient"]["ic"])
    assert broad["implied_ir_annual"] > narrow["implied_ir_annual"]


def test_a_dead_signal_in_a_good_construction_reads_construction_ok_and_no_ir():
    df = _planted_panel(ic=0.0, n_names=300, seed=5)
    blk = FL.receipt(df, "pred", _book_weights(df, 150, "ew"))
    assert blk["construction_verdict"].startswith("CONSTRUCTION_OK")
    assert abs(blk["information_coefficient"]["ic"]) < 0.03
    assert abs(blk["implied_ir_annual"]) < 0.3, blk["implied_ir_annual"]


def test_the_receipt_reports_none_with_a_reason_rather_than_a_zero_it_did_not_measure():
    df = _planted_panel(n_months=6, n_names=300)
    blk = FL.receipt(df, "pred", {})                 # no book at all
    assert blk["transfer_coefficient"]["tc"] is None
    assert "why_none" in blk["transfer_coefficient"]
    assert blk["construction_verdict"].startswith("CANNOT DETERMINE")
    assert blk["implied_ir_annual"] is None


def test_realised_and_implied_ir_are_both_carried_when_a_net_series_is_given():
    df = _planted_panel(ic=0.10, n_names=300)
    w = _book_weights(df, 100, "ew")
    months = sorted(w)
    rng = np.random.default_rng(2)
    net = pd.Series(rng.normal(0.008, 0.04, len(months)), index=months)
    bench = pd.Series(rng.normal(0.004, 0.04, len(months)), index=months)
    blk = FL.receipt(df, "pred", w, net=net, benchmark=bench, beta=0.93)
    assert blk["beta"] == 0.93
    assert blk["active_months"] == len(months)
    assert blk["realised_ir_annual"] is not None
    assert blk["realised_over_implied"] is not None
