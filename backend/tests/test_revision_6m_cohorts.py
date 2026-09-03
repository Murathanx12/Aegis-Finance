"""Offline mechanics tests for the Revision-6M cohort engines.

What is pinned (build-queue #7, docs/REVIEW_2026-09-03 PART B design):
  * a name admitted in month m is OUT of the book after the sleeve that
    bought it reforms at m+6 — a 6-month hold means six months, not seven;
  * the six overlapping sleeves plus cash always sum to <= 1 unit of
    capital (no leverage can appear from the cohort arithmetic);
  * a falsifier exit removes the name immediately, parks the proceeds, and
    the slot is recycled at the sleeve's next reform.

Everything is synthetic and offline: three names, zero costs, hand-built
return matrix. No parquet, no network.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.revision_6m_cohorts_run import run_cohort_falsifier, run_fullreb

H = 6
PERMS = (100, 101, 102)          # X (the probe), A, B


def _mkt(spikes: dict[int, dict[int, float]] | None = None):
    """A tiny market: business days 2020-2023, 3 names, zero returns except
    `spikes[day_index][col] = ret`."""
    dates = pd.bdate_range("2020-01-02", "2023-12-29")
    n_days, n_perm = len(dates), len(PERMS)
    R = np.zeros((n_days, n_perm), dtype=np.float32)
    for t, cols in (spikes or {}).items():
        for c, r in cols.items():
            R[t, c] = r
    d_ix = {d: i for i, d in enumerate(dates)}
    return {"dates": dates, "perms": np.array(PERMS), "d_ix": d_ix,
            "p_ix": {p: i for i, p in enumerate(PERMS)},
            "R": R, "LIVE": np.ones((n_days, n_perm), dtype=bool),
            "mkt": np.zeros(n_days), "mkt_ew": np.zeros(n_days),
            "n_days": n_days, "n_perm": n_perm}


def _vintages(mkt):
    """Monthly rebalance day indices: first business day of each month."""
    dates = mkt["dates"]
    firsts = pd.Series(dates, index=dates).resample("MS").first().dropna()
    return [mkt["d_ix"][d] for d in firsts]


def _panel(mkt, rb_days, ratios: dict[int, dict[int, float]] | None = None):
    """A minimal vintage panel for the falsifier engine: every name carries a
    ratio of 3.0 (mid-band) at every vintage unless overridden via
    `ratios[rebalance_index][permno] = ratio`."""
    rows = []
    for i, t in enumerate(rb_days):
        for p in PERMS:
            r = (ratios or {}).get(i, {}).get(p, 3.0)
            rows.append({"month": pd.Timestamp(mkt["dates"][t]).strftime("%Y-%m"),
                         "entry_date": mkt["dates"][t], "permno": p, "ratio": r})
    return pd.DataFrame(rows)


def _run(mkt, rb_days, members, panel=None, **kw):
    # score from the first vintage at which ALL six sleeves are live — the
    # real run's WARMUP boundary; before it the book is still ramping 1/6
    # sleeve at a time and a wealth ratio against it reads as leverage.
    mkt["_start_day"] = rb_days[H]
    if panel is None:
        panel = _panel(mkt, rb_days)
    defaults = dict(cost_bps=0.0, stop_pct=None, exit_toxic=False,
                    exit_left_band=False, park="market")
    defaults.update(kw)
    return run_cohort_falsifier(mkt, panel, mkt["p_ix"], mkt["d_ix"],
                                rb_days, members, **defaults)


def test_admitted_name_leaves_at_month_plus_6():
    """X is in ONE month's cohort. A +100% X-day inside the 6-month hold
    moves the book; the same spike after the sleeve reforms at m+6 does not."""
    base = _mkt()
    rb = _vintages(base)
    m = 8                                     # all six sleeves live by then
    members = [np.array([1, 2]) for _ in rb]
    members[m] = np.array([0, 1, 2])

    inside = _mkt({rb[m + 3] + 2: {0: 1.0}})   # during the hold
    after = _mkt({rb[m + H] + 2: {0: 1.0}})    # after the m+6 reform
    tw_inside = _run(inside, rb, members)["terminal_wealth"]
    tw_after = _run(after, rb, members)["terminal_wealth"]

    assert tw_inside > 1.0 + 1e-6, "the held name must move the book"
    assert tw_after == pytest.approx(1.0, abs=1e-9), \
        "a name admitted at m must be gone once its sleeve reforms at m+6"


def test_overlapping_sleeves_sum_to_at_most_one():
    """Zero returns, zero costs: the book conserves exactly one unit of
    capital; and once all sleeves are live a +100% day on EVERY name doubles
    the book exactly — i.e. total invested weight is exactly 1, never more."""
    base = _mkt()
    rb = _vintages(base)
    members = [np.array([0, 1, 2]) for _ in rb]
    assert _run(base, rb, members)["terminal_wealth"] == pytest.approx(1.0, abs=1e-9)

    spike_all = _mkt({rb[10] + 2: {0: 1.0, 1: 1.0, 2: 1.0}})
    tw = _run(spike_all, rb, members)["terminal_wealth"]
    assert tw == pytest.approx(2.0, abs=1e-9), \
        "fully-live overlapping sleeves must sum to exactly 1.0 of capital"


def test_falsifier_exit_frees_the_slot_and_parks_proceeds():
    """X turns toxic (ratio >= 5) at vintage m+2 while held: the exit fires,
    a later X spike no longer reaches the book, capital is conserved (parked
    at the market's 0% here), and the trigger count is recorded."""
    base = _mkt()
    rb = _vintages(base)
    m = 8
    members = [np.array([1, 2]) for _ in rb]
    members[m] = np.array([0, 1, 2])
    ratios = {m + 2: {100: 5.5}}              # X toxic at vintage m+2

    spike_late = _mkt({rb[m + 3] + 2: {0: 1.0}})   # inside the hold, AFTER exit
    panel = _panel(spike_late, rb, ratios)
    res = _run(spike_late, rb, members, panel=panel, exit_toxic=True)

    assert res["triggers_fired"]["toxic"] >= 1, "the falsifier must fire"
    assert res["terminal_wealth"] == pytest.approx(1.0, abs=1e-9), \
        "after the exit the name is out of the book and proceeds are parked"

    # control: without the falsifier the same spike DOES move the book
    ctrl = _run(spike_late, rb, members, panel=_panel(spike_late, rb, ratios),
                exit_toxic=False)
    assert ctrl["terminal_wealth"] > 1.0 + 1e-6


def test_fullreb_only_trades_on_its_phase():
    """The naive book reforms every 6th vintage: a name added to the cohort
    on an off-phase month is never bought."""
    base = _mkt()
    rb = _vintages(base)
    members = [np.array([1, 2]) for _ in rb]
    m = 9                                      # phase-0 book never forms here
    members[m] = np.array([0, 1, 2])
    spiked = _mkt({rb[m] + 2: {0: 1.0}})
    spiked["_start_day"] = rb[0]
    res = run_fullreb(spiked, rb, members, cost_bps=0.0, phase=0)
    assert res["terminal_wealth"] == pytest.approx(1.0, abs=1e-9), \
        "an off-phase cohort change must not reach the naive book"

    spiked2 = _mkt({rb[m] + 2: {0: 1.0}})
    spiked2["_start_day"] = rb[0]
    members2 = [np.array([1, 2]) for _ in rb]
    for i in range(len(rb)):
        if i % H == 3:
            members2[i] = np.array([0, 1, 2])
    res2 = run_fullreb(spiked2, rb, members2, cost_bps=0.0, phase=3)
    assert res2["terminal_wealth"] > 1.0 + 1e-6, \
        "the on-phase formation must be bought and held"


def test_fullreb_refuses_bad_phase():
    base = _mkt()
    rb = _vintages(base)
    members = [np.array([0, 1, 2]) for _ in rb]
    base["_start_day"] = rb[0]
    with pytest.raises(SystemExit):
        run_fullreb(base, rb, members, cost_bps=0.0, phase=6)
