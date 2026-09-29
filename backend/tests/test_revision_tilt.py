"""Offline tests for the revision-flow tilt construction (backend/services/revision_tilt.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import revision_tilt as RT


def _universe(n: int = 800, seed: int = 7):
    rng = np.random.default_rng(seed)
    dv = rng.lognormal(17, 1.5, n)
    mc = dv * rng.lognormal(3, 0.5, n)
    el = rng.random(n) > 0.05
    sec = rng.integers(10, 21, n).astype(float)
    score = rng.normal(0, 3, n)
    score[rng.random(n) < 0.15] = np.nan
    return dv, mc, el, sec, score


@pytest.mark.parametrize("scheme", ["cap", "equal"])
def test_base_weights_sum_to_one_and_pick_top_n_by_dollar_volume(scheme):
    dv, mc, el, _, _ = _universe()
    w = RT.base_weights(dv, el, mc, n=500, scheme=scheme)
    assert w.sum() == pytest.approx(1.0)
    assert (w > 0).sum() == 500
    assert not np.any(w[~el] > 0)
    cut = np.sort(dv[el])[-500]
    assert np.all(dv[w > 0] >= cut)


@pytest.mark.parametrize("share", [0.10, 0.20, 0.30])
@pytest.mark.parametrize("scheme", ["cap", "equal"])
def test_target_active_caps_zero_sum_sector_neutral(share, scheme):
    dv, mc, el, sec, score = _universe()
    b = RT.base_weights(dv, el, mc, n=500, scheme=scheme)
    a = RT.target_active(score, b, active_share=share, cap=0.005, sector=sec)
    assert a.sum() == pytest.approx(0.0, abs=1e-12)
    assert np.all(np.abs(a) <= 0.005 + 1e-12)
    assert np.all(b + a >= -1e-12)
    assert not np.any(a[b == 0] != 0)
    for g in np.unique(sec):
        assert a[sec == g].sum() == pytest.approx(0.0, abs=1e-12)
    assert 0.5 * np.abs(a).sum() <= share + 1e-6
    w = b + a
    assert w.sum() == pytest.approx(1.0)


def test_target_active_direction_follows_signal():
    dv, mc, el, sec, score = _universe()
    b = RT.base_weights(dv, el, mc, n=500, scheme="equal")
    a = RT.target_active(score, b, active_share=0.2, cap=0.005, sector=None)
    inb = (b > 0) & np.isfinite(score)
    assert np.corrcoef(score[inb], a[inb])[0, 1] > 0.8
    assert np.all(a[(b > 0) & ~np.isfinite(score)] == 0)       # no view -> no active weight


def test_step_active_respects_band_budget_and_caps():
    dv, mc, el, sec, score = _universe()
    b = RT.base_weights(dv, el, mc, n=500, scheme="equal")
    a_t = RT.target_active(score, b, active_share=0.3, cap=0.005, sector=sec)
    a0 = np.zeros(len(b))
    a1, turn = RT.step_active(a0, a_t, b, cap=0.005, band=0.001, budget=0.15)
    assert turn <= 0.15 + 0.02          # budget binds the move; the zero-sum projection may add a little
    assert a1.sum() == pytest.approx(0.0, abs=1e-12)
    assert np.all(np.abs(a1) <= 0.005 + 1e-12) and np.all(b + a1 >= -1e-12)
    # a second step from a1 toward the same target moves nothing inside the band
    a2, _ = RT.step_active(a1, a_t, b, cap=0.005, band=0.001, budget=0.15)
    small = np.abs(a_t - a1) < 0.001
    inb = b > 0
    moved = np.abs(a2 - a1) > 1e-12
    # the zero-sum projection may shave within-band names pro rata, but never grow them away from a1's sign
    assert np.all(np.sign(a2[small & inb & moved]) * np.sign(a1[small & inb & moved]) >= 0)


def test_step_active_forces_exit_outside_base():
    b = np.array([0.5, 0.5, 0.0])
    a_prev = np.array([-0.1, 0.0, 0.1])       # the third name left the base while held
    a, _ = RT.step_active(a_prev, np.zeros(3), b, cap=0.2, band=0.5, budget=1.0)
    assert a[2] == 0.0
    assert (b + a).sum() == pytest.approx(1.0)


def test_signals_use_only_same_row_columns_no_future():
    df = pd.DataFrame({"net_raises": [3, -2, np.nan, 0], "n_firms": [3, 4, 0, 0], "ear_last": [0.05, np.nan, -0.02, 0.0],
                       "fwd_ret": [9.0, -9.0, 9.0, -9.0]})
    base = {s: RT.signal_score(df, s) for s in RT.SIGNALS}
    df2 = df.assign(fwd_ret=-df["fwd_ret"])                  # the future changes; scores must not
    for s in RT.SIGNALS:
        np.testing.assert_array_equal(np.nan_to_num(base[s], nan=-99), np.nan_to_num(RT.signal_score(df2, s), nan=-99))
    assert base["breadth"][0] == pytest.approx(1.0) and base["breadth"][1] == pytest.approx(-0.5)
    assert np.isnan(base["breadth"][2])


def test_simulation_uses_no_future_signal(monkeypatch):
    """Scrambling fwd_ret of FUTURE dates must not change weights chosen at earlier dates."""
    from scripts import revision_tilt_on_crsp as S
    rng = np.random.default_rng(3)
    dates = pd.date_range("2000-01-31", periods=6, freq="ME")
    rows = []
    for d in dates:
        for p in range(60):
            rows.append({"date": d, "symbol": f"{p:06d}", "permno": p, "eligible": True,
                         "median_dollar_vol": 1e7 * (1 + p), "mcap": 1e9 * (1 + p % 7), "fwd_ret": rng.normal(0, .05),
                         "net_raises": float(rng.integers(-3, 4)), "n_firms": 3.0, "ear_last": rng.normal(0, .03),
                         "gsector": float(10 + p % 3), "cs_spread": 0.004, "delisted_in_period": False})
    P = pd.DataFrame(rows)
    r1 = S.simulate(P, signal="net_raises", active_share=0.2, band=0.0005, n=40)["series"]
    P2 = P.copy()
    late = P2["date"] >= dates[3]
    P2.loc[late, "fwd_ret"] = rng.normal(0, .2, late.sum())
    r2 = S.simulate(P2, signal="net_raises", active_share=0.2, band=0.0005, n=40)["series"]
    early = r1.index < dates[3]
    pd.testing.assert_series_equal(r1.loc[early, "book_net"], r2.loc[early, "book_net"])
    assert (r1["turnover_active"] <= 0.15 + 0.02).all()
    assert (r1["max_abs_active"] <= 0.005 + 1e-12).all()


def test_kill_line_false_kill_rate():
    k = RT.kill_line(0.01, 6.0)
    assert k["false_kill_rate"] == pytest.approx(0.05, abs=1e-3)
    assert k["kill_at"] < 0


# ── rank band (2026-09-29 evening): ranks 501-1500 as a new optional parameter ──

def _old_top_n(dv, el, mc, n, scheme):
    """The pre-2026-09-29 base_weights body, verbatim, as the reference."""
    d = np.where(el & np.isfinite(dv), dv, -np.inf)
    order = np.argsort(-d, kind="stable")
    k = int(min(n, np.isfinite(d).sum()))
    pick = order[:k]
    w = np.zeros(len(d))
    if scheme == "equal":
        w[pick] = 1.0 / k
        return w
    m = np.asarray(mc, dtype=float)[pick]
    fill = np.nanmedian(m) if np.isfinite(m).any() else 1.0
    m = np.where(np.isfinite(m) & (m > 0), m, fill)
    w[pick] = m / m.sum()
    return w


@pytest.mark.parametrize("scheme", ["cap", "equal"])
@pytest.mark.parametrize("n", [10, 500, 5000])
def test_default_rank_lo_reproduces_the_old_base_exactly(scheme, n):
    dv, mc, el, _, _ = _universe()
    np.testing.assert_array_equal(RT.base_weights(dv, el, mc, n=n, scheme=scheme),
                                  _old_top_n(dv, el, mc, n, scheme))
    np.testing.assert_array_equal(RT.base_weights(dv, el, mc, n=n, scheme=scheme, rank_lo=0),
                                  _old_top_n(dv, el, mc, n, scheme))


def test_rank_band_picks_ranks_501_to_1500():
    rng = np.random.default_rng(11)
    n = 2000
    dv = rng.permutation(np.arange(1, n + 1).astype(float))
    el = np.ones(n, dtype=bool)
    w = RT.base_weights(dv, el, None, n=1000, scheme="equal", rank_lo=500)
    rank = n - dv + 1                                   # rank 1 = largest dollar volume
    assert set(rank[w > 0].astype(int)) == set(range(501, 1501))
    assert w.sum() == pytest.approx(1.0) and np.allclose(w[w > 0], 1e-3)


def test_rank_band_shrinks_when_the_universe_is_short_and_refuses_a_negative_offset():
    dv = np.arange(1, 701).astype(float)
    el = np.ones(700, dtype=bool)
    w = RT.base_weights(dv, el, None, n=1000, scheme="equal", rank_lo=500)
    assert (w > 0).sum() == 200 and w.sum() == pytest.approx(1.0)
    assert RT.base_weights(dv, el, None, n=10, scheme="equal", rank_lo=900).sum() == 0.0
    with pytest.raises(ValueError):
        RT.base_weights(dv, el, None, rank_lo=-1)


def test_the_default_profile_reproduces_the_original_declaration_hash():
    """The existing receipts must still validate: the code refuses on hash mismatch."""
    from scripts import revision_tilt_on_crsp as S
    assert S.ACTIVE["profile"] == "top500"
    assert S._sha(S.declaration()) == "0f0939b893b2754e"


def test_the_midcap_profile_declares_a_different_hash_and_the_new_search_count(monkeypatch):
    from scripts import revision_tilt_on_crsp as S
    monkeypatch.setitem(S.ACTIVE, "profile", "mid501_1500")
    d = S.declaration()
    assert S._sha(d) != "0f0939b893b2754e"
    assert d["fixed"]["base_rank_lo"] == 500 and d["fixed"]["base_n"] == 1000
    assert d["fixed"]["base_scheme"] == "equal" and d["fixed"]["cap_per_name"] == 0.01
    assert d["search_count"]["prior"] == 42_397
    assert d["search_count"]["total_for_deflation"] == 42_397 + 18 + 1
