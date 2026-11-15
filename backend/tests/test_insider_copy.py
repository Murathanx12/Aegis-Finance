"""CH-47 insider copy book: the four honesty rules on synthetic data.

1. a planted future-outcome leak is caught;
2. the prior record ignores windows not closed at the filing date;
3. entry never precedes the filing's public bound;
4. zero cost is refused.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import insider_copy as IC


def _sessions(n: int = 400, holiday_every: int = 37) -> np.ndarray:
    """A synthetic weekday calendar with a holiday every ``holiday_every`` weekdays."""
    base = np.datetime64("2001-01-01")            # a Monday, far in the past
    days = base + np.arange(int(n * 1.6))
    wk = days[np.is_busday(days)]
    keep = np.ones(len(wk), dtype=bool)
    keep[holiday_every::holiday_every] = False
    return wk[keep][:n]


# ── 4. zero cost refused ──────────────────────────────────────────────────

def test_zero_cost_is_refused():
    with pytest.raises(IC.InsiderCopyRefused):
        IC.require_costs([(1e9, 10.0), (0.0, 0.0)])
    with pytest.raises(IC.InsiderCopyRefused):
        IC.require_costs([])
    with pytest.raises(IC.InsiderCopyRefused):
        IC.require_costs(None)
    with pytest.raises(IC.InsiderCopyRefused):
        IC.require_costs([(1e9, 10.0), (1e6, 20.0)])          # no floor band
    c = IC.round_trip_cost(np.array([5e9, 5e7, 10.0, np.nan]), [(1e9, 10.0), (2e7, 40.0), (0.0, 200.0)])
    assert np.allclose(c, [0.001, 0.004, 0.02, 0.02])
    assert (c > 0).all()


def test_shipped_cost_schedule_is_positive():
    from backend import config
    sched = IC.require_costs(config.INSIDER_COPY_COST_BANDS)
    assert all(b > 0 for _, b in sched)


# ── 3. entry never precedes the public bound ─────────────────────────────

def test_entry_is_strictly_after_the_filing_date():
    s = _sessions()
    on_session = s[10]
    friday = s[np.flatnonzero(s.astype("datetime64[D]").view("int64") % 7 == 1)[2]]  # 1970-01-02 was a Friday
    filings = np.array([on_session, friday, s[36], s[-1]], dtype="datetime64[D]")
    idx = IC.entry_session_index(filings, s)
    assert s[idx[0]] > on_session and idx[0] == 11
    assert s[idx[1]] > friday and (s[idx[1]] - friday) >= np.timedelta64(1, "D")
    assert idx[3] == -1                                # no session after the last
    assert IC.assert_entry_after_public(filings, s, idx) == 3
    tampered = idx.copy()
    tampered[0] = 10                                   # the filing-day print
    with pytest.raises(IC.InsiderCopyRefused):
        IC.assert_entry_after_public(filings, s, tampered)


def test_holiday_filing_enters_the_next_session():
    s = _sessions(holiday_every=5)
    gap = np.flatnonzero(np.diff(s).astype(int) > 1)
    k = int(gap[0])
    missing_day = s[k] + np.timedelta64(1, "D")
    if np.is_busday(missing_day):                      # a synthetic holiday
        idx = IC.entry_session_index(np.array([missing_day]), s)
        assert idx[0] == k + 1


def test_open_entry_uses_the_open_and_missing_open_enters_later():
    T, N = 30, 2
    R = np.full((T, N), 0.01)
    C = IC.cumulative_log(R)
    G = np.full((T, N), np.log(1.02))
    G[5, 1] = np.nan
    w = IC.window_returns(np.array([5, 5]), np.array([0, 1]), 3, C, G, "next_open")
    assert np.isclose(w["r"][0], 1.02 * 1.01 ** 2 - 1)
    assert np.isclose(w["r"][1], 1.01 ** 2 - 1)        # entered at the close of session 5
    assert w["open_missing"].tolist() == [False, True]
    wc = IC.window_returns(np.array([5]), np.array([0]), 3, C, None, "next_close")
    assert np.isclose(wc["r"][0], 1.01 ** 3 - 1)
    late = IC.window_returns(np.array([T - 1]), np.array([0]), 3, C, G, "next_open")
    assert not late["valid"][0] and np.isnan(late["r"][0])


# ── 2. the prior record ignores unclosed windows ─────────────────────────

def test_prior_record_ignores_unclosed_windows():
    d0 = np.datetime64("2001-03-01")
    filing = np.array([d0, d0 + 20, d0 + 31, d0 + 30, d0 + 5], dtype="datetime64[D]")
    exit_ = np.array([d0 + 30, d0 + 50, d0 + 60, d0 + 70, d0 + 9], dtype="datetime64[D]")
    ins = np.array(["A", "A", "A", "A", "B"])
    x = np.array([0.5, 0.1, 0.2, 0.3, 9.0])
    rec = IC.prior_record(ins, filing, exit_, x)
    assert rec["n_prior"].tolist() == [0, 0, 1, 0, 0]
    assert rec.loc[2, "sum_prior"] == pytest.approx(0.5)
    # an exit ON the filing date does not count (strict), and B's record never leaks into A
    assert rec.loc[3, "n_prior"] == 0
    IC.audit_prior_record(ins, filing, exit_, x, rec)


def test_vectorised_record_matches_the_reference_loop():
    rng = np.random.default_rng(3)
    n = 600
    ins = rng.choice([f"i{k}" for k in range(40)], size=n)
    filing = np.datetime64("2002-01-01") + rng.integers(0, 2000, size=n)
    exit_ = filing + rng.integers(20, 200, size=n)
    x = rng.normal(0, 0.1, size=n)
    x[rng.choice(n, 30, replace=False)] = np.nan
    rec = IC.prior_record(ins, filing, exit_, x)
    ref = IC.prior_record_slow(ins, filing, exit_, x, np.arange(n))
    assert (rec["n_prior"].to_numpy() == ref["n_prior"].to_numpy()).all()
    assert np.allclose(rec["sum_prior"].to_numpy(), ref["sum_prior"].to_numpy())
    assert (rec["hits_prior"].to_numpy() == ref["hits_prior"].to_numpy()).all()


# ── 1. a planted future-outcome leak is caught ───────────────────────────

def _leaky_record(ins, filing, exit_, x) -> pd.DataFrame:
    """Counts every EARLIER-FILED trade, closed or not: the classic peek."""
    fd = filing.astype("int64")
    ex = exit_.astype("int64")
    rows = []
    for r in range(len(ins)):
        m = (ins == ins[r]) & (fd < fd[r]) & np.isfinite(x)
        rows.append((int(m.sum()), float(x[m].sum()), int((x[m] > 0).sum()),
                     int(ex[m].max()) if m.any() else np.iinfo(np.int64).min))
    return pd.DataFrame(rows, columns=["n_prior", "sum_prior", "hits_prior", "max_used_exit"])


def test_a_planted_future_outcome_leak_is_refused():
    rng = np.random.default_rng(11)
    n = 300
    ins = rng.choice([f"i{k}" for k in range(15)], size=n)
    filing = (np.datetime64("2003-01-01") + rng.integers(0, 900, size=n)).astype("datetime64[D]")
    exit_ = filing + 126
    x = rng.normal(0, 0.2, size=n)
    leak = _leaky_record(ins, filing, exit_, x)
    with pytest.raises(IC.InsiderCopyRefused):
        IC.audit_prior_record(ins, filing, exit_, x, leak)
    # the same leak with its exit stamps scrubbed is still caught by the reference loop
    scrubbed = leak.copy()
    scrubbed["max_used_exit"] = np.iinfo(np.int64).min
    with pytest.raises(IC.InsiderCopyRefused):
        IC.audit_prior_record(ins, filing, exit_, x, scrubbed)
    honest = IC.prior_record(ins, filing, exit_, x)
    out = IC.audit_prior_record(ins, filing, exit_, x, honest)
    assert out["violations"] == 0


def test_in_a_noise_world_the_honest_ranking_finds_nothing_and_a_leak_does():
    """Returns are pure noise but persistent within a short window per insider:
    the leak (reading still-open outcomes of trades filed days earlier) ranks
    on the CURRENT shock; the honest record cannot."""
    rng = np.random.default_rng(5)
    n_ins, per, grp = 200, 24, 3
    ins = np.repeat([f"i{k}" for k in range(n_ins)], per)
    t = np.tile(np.arange(per) * 30, n_ins) + np.repeat(rng.integers(0, 3000, n_ins), per)
    filing = (np.datetime64("2004-01-01") + t).astype("datetime64[D]")
    exit_ = filing + 126
    # a shock shared by an insider's trades filed within 90 days: visible only
    # through windows that are still OPEN at the next filing
    shock = rng.normal(0, 0.2, size=(n_ins, per // grp))
    x = shock[np.repeat(np.arange(n_ins), per), np.tile(np.arange(per) // grp, n_ins)] + rng.normal(0, 0.05, n_ins * per)
    honest = IC.score(IC.prior_record(ins, filing, exit_, x), "shrunk_mean", 3.0, 3)
    leaky = IC.score(_leaky_record(ins, filing, exit_, x), "shrunk_mean", 3.0, 3)

    def spread(sc):
        m = np.isfinite(sc)
        hi, lo = np.nanpercentile(sc, 80), np.nanpercentile(sc, 20)
        return x[m & (sc >= hi)].mean() - x[m & (sc <= lo)].mean()

    assert spread(leaky) > 0.06           # measured 0.099 at this seed
    assert abs(spread(honest)) < 0.03     # measured -0.005


# ── ranking, controls, statistics ────────────────────────────────────────

def test_cutoffs_use_only_scores_filed_before_the_month():
    d = pd.to_datetime(["2005-01-10"] * 60 + ["2005-02-10"] * 60).to_numpy()
    s = np.r_[np.linspace(0, 1, 60), np.linspace(100, 101, 60)]
    lab = IC.rank_labels(d, s, 80, 20, 365, 50)
    assert set(lab[:60]) == {"no_cutoff"}             # nothing filed before January
    assert set(lab[60:]) == {"top"}                    # February's cutoffs are January's
    lab2 = IC.rank_labels(d, np.r_[s[:60], -s[60:]], 80, 20, 365, 50)
    assert set(lab2[60:]) == {"poor"}


def test_controls_are_same_bucket_alive_and_never_the_issuer():
    T, N = 5, 50
    bucket = np.tile((np.arange(N) % 5), (T, 1)).astype(np.int8)
    alive = np.ones((T, N), dtype=bool)
    alive[3, 0:10] = False
    ctrl = IC.sample_controls(np.array([3, 3, 4]), np.array([12, 0, 7]), bucket, alive, 4, seed=1)
    for row, c in zip(ctrl, [12, 0, 7]):
        assert (row >= 0).all()
        assert c not in row
        assert (bucket[0, row] == bucket[0, c]).all()
    assert not np.isin(ctrl[:2], np.arange(10)).any()  # dead on the entry session
    again = IC.sample_controls(np.array([3, 3, 4]), np.array([12, 0, 7]), bucket, alive, 4, seed=1)
    assert (again == ctrl).all()


def test_non_overlap_t_and_mde():
    rng = np.random.default_rng(0)
    idx = np.repeat(np.arange(0, 21 * 40, 21), 5)
    v = rng.normal(0.01, 0.05, len(idx))
    st = IC.stats(v, idx, 21)
    assert st["n_blocks"] == 40 and st["n_blocks_nonoverlap"] == 20
    assert st["mde_nonoverlap"] == pytest.approx(2.8 * st["se_nonoverlap"])
    loo = IC.leave_one_year_out(v, idx, np.repeat(np.arange(8), 25), 21)
    assert loo["worst_year_dropped"] in range(8)
    cc = IC.concentration(np.array([1.0, 1.0, 2.0]), np.array(["a", "a", "b"]), np.array(["x", "y", "y"]))
    assert cc["top_date_share"] == pytest.approx(0.5) and cc["top_name_share"] == pytest.approx(0.75)


def test_aggregate_trades_labels_and_refuses_empty():
    b = pd.DataFrame({"insider_cik": ["1", "1", "2"], "permno": [10, 10, 10],
                      "filing_date": ["2006-03-01", "2006-03-01", "2006-03-01"],
                      "cmp_class": ["routine", "opportunistic", "unclassifiable"],
                      "cluster_buyers": [3, 3, 1], "is_officer": [True, False, False],
                      "is_director": [False, False, True], "is_tenpercent": [False, False, False],
                      "dollar_value": [100.0, 50.0, 10.0]})
    t = IC.aggregate_trades(b)
    assert len(t) == 2
    assert t.loc[t.insider_cik == "1", "cmp_class"].item() == "opportunistic"
    assert bool(t.loc[t.insider_cik == "1", "cluster"].item()) is True
    with pytest.raises(IC.InsiderCopyRefused):
        IC.aggregate_trades(b.iloc[0:0])


def test_verdict_vocabulary():
    pos = {"mean_block": 0.01, "t_nonoverlap": 3.0, "mean_nonoverlap": 0.01}
    neg = {"mean_block": -0.01, "t_nonoverlap": -3.0, "mean_nonoverlap": -0.01}
    flat = {"mean_block": 0.001, "t_nonoverlap": 0.5, "mean_nonoverlap": 0.001}
    assert IC.verdict(pos, pos, pos, 0.005, 0.7) == "OBSERVED"
    assert IC.verdict(pos, pos, pos, -0.001, 0.7) == "CANNOT_DISTINGUISH"
    assert IC.verdict(flat, flat, neg, 0.0, 0.3) == "FAILED_VARIANT"
    assert IC.verdict(flat, flat, flat, 0.0, 0.5) == "CANNOT_DISTINGUISH"


# ── review round (2026-11-15): weighting, both parities, NW t, robustness ──

def test_group_weighting_counts_one_decision_once():
    idx = np.array([0, 0, 0, 0])
    v = np.array([1.0, 1.0, 1.0, 0.0])
    g = np.array(["firmA", "firmA", "firmA", "firmB"])     # one filing by three entities
    assert IC.block_means(v, idx, 21).iloc[0] == pytest.approx(0.75)
    assert IC.block_means(v, idx, 21, g).iloc[0] == pytest.approx(0.5)


def test_declared_mean_belongs_to_its_t_and_both_parities_are_reported():
    rng = np.random.default_rng(2)
    idx = np.arange(0, 21 * 60, 21)
    v = rng.normal(0.01, 0.05, len(idx))
    st = IC.stats(v, idx, 21)
    k = st["declared_parity"]
    par = st["parity"][k]
    assert st["mean_nonoverlap"] == pytest.approx(par["mean"])
    assert st["t_nonoverlap"] == pytest.approx(par["t"])
    assert {p["parity"] for p in st["parity"]} == {0, 1}
    assert np.isfinite(st["t_nw1_all_blocks"])


def test_newey_west_t_equals_plain_t_shape_without_autocorrelation():
    x = np.array([1.0, -1.0] * 50) + 0.1
    # strongly negative lag-1 autocorrelation shrinks the variance -> NW t above the naive t
    naive = x.mean() / (x.std(ddof=0) / np.sqrt(len(x)))
    assert IC.newey_west_t(x, 1) > naive


def test_robustness_drops_the_largest_names_and_winsorises():
    idx = np.repeat(np.arange(0, 21 * 10, 21), 3)
    v = np.full(len(idx), 0.01)
    names = np.array(["N%d" % (i % 7) for i in range(len(idx))])
    v[names == "N3"] = 5.0
    r = IC.robustness(v, idx, 21, names)
    assert r["drop_top1"]["dropped"] == ["N3"]
    assert r["drop_top1"]["mean_block"] == pytest.approx(0.01)
    assert r["winsor_1_99"]["mean_block"] <= r["full"]["mean_block"]
