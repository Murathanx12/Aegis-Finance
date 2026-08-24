"""A book that carries SHARE COUNTS must carry them across a split.

WHAT WENT WRONG, MEASURED
=========================
`replay` holds share counts and marks them at `panel.close`. `panel.close` was
raw `abs(prc)`. A share count is not invariant across a corporate action, so
every split in the sample was booked as a return:

  * a 1-for-4 REVERSE split quadruples the raw price -> the book marks +300%
  * a 2-for-1 FORWARD split halves it -> the book marks -50%

Found on permno 85035, 2015-01-02:

    prc      16.59 -> 70.40
    cfacpr    0.25 -> 1.00
    ret              +6.088%        <- CRSP's own, correct
    the farm booked            +324% on the position

That single event was worth **+36.34% of one-day "excess"** on
`mom_12_1 / h5 / k10 / inverse_vol` — a quarter of its entire 13.4%/yr headline
— and it was the largest single day in the twelve-year series for BOTH momentum
signals, which is what gave it away: an identical extreme on the same date for
two different rules is an instrument, not a strategy.

CRSP's identity, which is what the fix restores:

    (prc / cfacpr)_t / (prc / cfacpr)_{t-1} - 1  ==  ret_t   (ex-dividend part)

WHAT IT COST IN AGGREGATE, AND WHY THAT NUMBER UNDERSTATES IT
=============================================================
Net, the bug was worth about -0.3%/yr to the leading momentum policy (its
terminal median went 77,002 -> 85,482 once fixed): reverse splits gave and
forward splits took, and they roughly cancelled.

The DISTRIBUTIONAL damage was far larger than the mean damage, and that is the
lesson. Forward splits are far more common among large, liquid, appreciating
names, so the bug was a systematic tax on exactly those books. Fixing it moved
the `liquid` signal from t=0.26 to **t=2.55** and made it the best row in the
signal grid. A bug worth a third of a percent a year had been hiding the most
promising independent selector on the board.

`ret` and therefore `tri` and therefore every SIGNAL were always correct — CRSP
adjusts them. Only the P&L path was wrong, which is why nothing looked broken.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio_farm import panel as P
from backend.services.portfolio_farm import replay as R
from backend.services.portfolio_farm.policy import Policy

pytest.importorskip("pyarrow")


def _year(dir_, year: int, *, split_on: int | None = None,
          split_factor: float = 4.0, n_permno: int = 12,
          n_days: int = 80) -> None:
    """A flat year in which one name does a reverse split on day `split_on`.

    Prices are otherwise constant, so ANY nonzero P&L in a book holding the
    splitting name is the artefact and nothing else.
    """
    dates = pd.bdate_range(f"{year}-01-01", periods=n_days).astype(str)
    rows = []
    for j in range(n_permno):
        splits = j == 0 and split_on is not None
        for i, d in enumerate(dates):
            after = splits and i >= split_on
            cf = 1.0 if after else (1.0 / split_factor if splits else 1.0)
            px = 20.0 * (split_factor if after else 1.0)
            rows.append({"permno": 10000 + j, "date": d, "prc": px,
                         "ret": 0.0, "retx": 0.0, "vol": 1e6 * (n_permno - j),
                         "shrout": 1e5, "openprc": px, "cfacpr": cf})
    pd.DataFrame(rows).to_parquet(dir_ / f"crsp_dsf_{year}.parquet", index=False)


def test_the_adjusted_series_reproduces_CRSPs_own_return(tmp_path):
    """The identity the fix rests on, on synthetic data with a known answer."""
    _year(tmp_path, 2000, split_on=40, split_factor=4.0)
    pan = P.load_panel(2000, 2000, dir_=tmp_path)
    j = int(np.flatnonzero(pan.permnos == 10000)[0])
    move = float(pan.close[40][j] / pan.close[39][j] - 1.0)
    assert move == pytest.approx(0.0, abs=1e-9), (
        f"a 1-for-4 reverse split moved the adjusted price by {move:.4f}; "
        f"CRSP's `ret` for that day is 0.0")
    # the RAW price really did quadruple — the fixture is not a no-op
    assert pan.close_raw[40][j] / pan.close_raw[39][j] == pytest.approx(4.0)


def test_a_split_does_not_move_the_NAV(tmp_path):
    """End to end. Every price is flat, so a nonzero return IS the bug."""
    # ONE year, so the split is the only price event. Spanning two years with
    # this fixture made the post-split name revert to its pre-split RAW price
    # at the boundary, which is a fixture bug that reads exactly like the code
    # bug — a -15% NAV step. The fixture has to be self-consistent for the
    # assertion to mean anything.
    _year(tmp_path, 2000, split_on=120, split_factor=4.0, n_days=200)
    pol = Policy(signal="liquid", holding_days=5, top_k=3,
                 sizing="equal_weight", universe_n=12, min_price=5.0,
                 transaction_cost_bps=0.0, slippage_bps=0.0,
                 zero_cost_diagnostic=True)
    res = R.run(P.load_panel(2000, 2000, dir_=tmp_path), pol, warmup=30)
    # `liquid` ranks by dollar volume, and permno 10000 has the highest, so the
    # splitting name is guaranteed to be held across the event.
    nav = np.asarray(res.nav, dtype=float)
    assert np.nanmax(nav) / np.nanmin(nav) < 1.01, (
        f"NAV moved {np.nanmax(nav)/np.nanmin(nav):.3f}x on a panel where "
        f"every price is flat — a corporate action was booked as a return")


def test_a_FORWARD_split_is_not_a_loss_either(tmp_path):
    """The symmetric case, which is the common one among large liquid names and
    is why the bug read as a tax on exactly the book that turned out to matter."""
    _year(tmp_path, 2000, split_on=40, split_factor=0.5)
    pan = P.load_panel(2000, 2000, dir_=tmp_path)
    j = int(np.flatnonzero(pan.permnos == 10000)[0])
    assert float(pan.close[40][j] / pan.close[39][j] - 1.0) == pytest.approx(
        0.0, abs=1e-9)
    assert pan.close_raw[40][j] / pan.close_raw[39][j] == pytest.approx(0.5)


def test_the_price_screen_uses_the_RAW_price(tmp_path):
    """A $5 floor is about what actually changes hands. A name trading at $2
    after four forward splits must not pass because it was $32 before them."""
    dates = pd.bdate_range("2000-01-03", periods=60).astype(str)
    rows = []
    for j in range(6):
        # $0.50 rising 2%/day reaches only $1.64 in 60 sessions, so the
        # raw price never crosses the $5 floor inside the fixture. At
        # $2.00 it crossed on day ~47 and the "screened" book started
        # buying it legitimately, which made the assertion untestable.
        px = 0.5 if j == 0 else 50.0
        for i, d in enumerate(dates):
            cheap = j == 0
            # The penny name RISES 2% a day and nothing else moves, so holding
            # it is the only way the NAV can grow. That makes the assertion
            # about the SCREEN and not about arithmetic that happens to agree.
            if cheap:
                px *= 1.02
            rows.append({"permno": 10000 + j, "date": d, "prc": px,
                         "ret": 0.02 if cheap else 0.0,
                         "retx": 0.02 if cheap else 0.0,
                         "vol": 1e9 if cheap else 1e6,
                         "shrout": 1e5, "openprc": px,
                         # adjusted price starts at 0.5/0.0625 = $8
                         "cfacpr": 0.0625 if cheap else 1.0})
    pd.DataFrame(rows).to_parquet(tmp_path / "crsp_dsf_2000.parquet",
                                  index=False)
    pan = P.load_panel(2000, 2000, dir_=tmp_path)
    j = int(np.flatnonzero(pan.permnos == 10000)[0])
    # day 0 is already one 2% step in, hence 2.04 raw / 32.64 adjusted
    assert pan.close[0][j] > 5.0                      # adjusted, above the floor
    assert pan.close_raw[0][j] < 5.0                  # raw, below it
    assert pan.close[0][j] == pytest.approx(
        pan.close_raw[0][j] / 0.0625, rel=1e-5)

    kw = dict(signal="liquid", holding_days=5, top_k=1,
              sizing="equal_weight", universe_n=6,
              transaction_cost_bps=0.0, slippage_bps=0.0,
              zero_cost_diagnostic=True)
    # the penny name has by far the highest dollar volume, so it is the top
    # `liquid` pick on every date it is eligible at all.
    kept = R.run(pan, Policy(min_price=0.0, **kw), warmup=30)
    screened = R.run(pan, Policy(min_price=5.0, **kw), warmup=30)
    assert kept.metrics["terminal_usd"] > 10_000 * 1.05, (
        "the fixture cannot detect the screen: the penny name is not being "
        "held even with no price floor")
    assert screened.metrics["terminal_usd"] == pytest.approx(10_000.0, rel=1e-6), (
        f"a $5 floor let through a name trading at $2 — the screen is reading "
        f"the SPLIT-ADJUSTED price (${pan.close[0][j]:.0f}) instead of the raw "
        f"one (${pan.close_raw[0][j]:.0f})")


def test_a_missing_or_zero_cfacpr_does_not_delete_the_name(tmp_path):
    """A zero factor would divide to infinity and silently remove a holding
    from every book. It is treated as 1.0 — no adjustment — instead."""
    dates = pd.bdate_range("2000-01-03", periods=30).astype(str)
    rows = [{"permno": 10001, "date": d, "prc": 10.0, "ret": 0.0, "retx": 0.0,
             "vol": 1e6, "shrout": 1e5, "openprc": 10.0,
             "cfacpr": 0.0 if i % 2 else np.nan}
            for i, d in enumerate(dates)]
    pd.DataFrame(rows).to_parquet(tmp_path / "crsp_dsf_2000.parquet",
                                  index=False)
    pan = P.load_panel(2000, 2000, dir_=tmp_path)
    assert np.isfinite(pan.close).all()
    assert float(np.nanmax(pan.close)) == pytest.approx(10.0)


def test_cfacpr_is_required_and_its_absence_is_named(tmp_path):
    """Without it the simulator is a different simulator, so it is refused with
    the other three rather than defaulted to 1.0 across a whole year."""
    dates = pd.bdate_range("2000-01-03", periods=30).astype(str)
    pd.DataFrame([{"permno": 10001, "date": d, "prc": 10.0, "ret": 0.0,
                   "retx": 0.0, "vol": 1e6, "shrout": 1e5, "openprc": 10.0}
                  for d in dates]).to_parquet(
        tmp_path / "crsp_dsf_2000.parquet", index=False)
    assert "cfacpr" in P.REQUIRED_COLUMNS
    assert P.replayable_years(tmp_path) == []
    with pytest.raises(P.PanelUnavailable, match="cfacpr"):
        P.load_panel(2000, 2000, dir_=tmp_path)


def test_the_live_panel_matches_CRSP_ret_through_a_real_split():
    """The measured case, on the real files, so the fixture cannot drift from
    what CRSP actually contains."""
    try:
        pan = P.load_panel(2014, 2015)
    except P.PanelUnavailable:
        pytest.skip("CRSP parquets not present on this machine")
    d = np.asarray([str(x) for x in pan.dates])
    hit = np.flatnonzero(d == "2015-01-02")
    if not hit.size or 85035 not in set(pan.permnos.tolist()):
        pytest.skip("the audited event is not in this panel")
    i = int(hit[0])
    j = int(np.flatnonzero(pan.permnos == 85035)[0])
    implied = float(pan.close[i][j] / pan.close[i - 1][j] - 1.0)
    assert implied == pytest.approx(float(pan.ret[i][j]), abs=1e-4)
    assert pan.close_raw[i][j] / pan.close_raw[i - 1][j] > 4.0


def test_the_whole_panel_reproduces_CRSP_retx_not_just_the_audited_event():
    """The GENERAL invariant, which is stronger than the one event that found
    the bug: for every name on every session, the split-adjusted price move
    must equal CRSP's EX-DIVIDEND return.

    Against `retx`, not `ret` — `ret` includes the dividend, which `replay`
    credits separately as cash, so checking against it would show a spurious
    gap on every distribution date. Measured 2021-03-09 over 3,950 names, the
    two comparisons differ by exactly that much:

        vs ret    max 0.098892   (the largest dividend that day)
        vs retx   max 0.000001

    Any future change to how prices are built has to keep the second column.
    """
    try:
        pan = P.load_panel(2021, 2021)
    except P.PanelUnavailable:
        pytest.skip("CRSP parquets not present on this machine")
    # a handful of sessions spread through the year, not just one
    worst = 0.0
    for i in range(60, pan.shape[0], 40):
        mv = pan.close[i] / pan.close[i - 1] - 1.0
        rx = pan.retx[i]
        m = np.isfinite(mv) & np.isfinite(rx)
        if m.sum() < 100:
            continue
        worst = max(worst, float(np.abs(mv[m] - rx[m]).max()))
    assert worst < 1e-3, (
        f"split-adjusted price moves disagree with CRSP `retx` by up to "
        f"{worst:.6f}; the price series and the return series are describing "
        f"different securities")
