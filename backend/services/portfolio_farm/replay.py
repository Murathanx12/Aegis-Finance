"""ASOF_REPLAY — walk the history forward, one decision at a time, paying costs.

THE CONVENTION, STATED ONCE
===========================
    decide at the CLOSE of day i  ->  fill at the OPEN of day i+1

That is the arena's own convention (`arena_books_v1.yaml`: "decisions freeze
after close; fills at next open") and it is the reason this package needed
CRSP's `openprc` rather than a close-to-close approximation. A close-to-close
simulator books the overnight gap that follows its own signal, which on a
momentum strategy is a systematic gift.

WHAT IS SIMULATED, AND WHAT IS NOT
==================================
Simulated: share counts (not weights), dividends as CASH, per-trade costs and
slippage on the traded notional, a per-name weight cap, a formation-time
liquidity screen with trailing data only, failed fills when a name has no open
price, and an explicit delisting assumption when a holding leaves the file.

NOT simulated: shorting, leverage, borrow cost, intraday execution, market
impact beyond the flat slippage, taxes, or a cash yield. The first four are
CHUNK-G work; the absence of a cash yield is CONSERVATIVE (idle cash earns 0),
which is the right direction for an unfinished simulator to be wrong in.

THE PIT ENFORCEMENT IS STRUCTURAL, NOT POLITE
=============================================
`run` never passes a full-panel row index into anything that could look
forward. The signal grid is precomputed by `signals.matrix`, whose every
formula is a trailing window; the decision at row `i` reads `sig[i]`; the fill
reads `open_[i+1]` and happens on day `i+1`, after the decision is already
frozen in `pending`. `test_portfolio_farm_pit.py` plants a column equal to the
NEXT day's return and asserts the engine's result is unchanged — the only kind
of proof that survives a refactor.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from backend.services.portfolio_farm import signals as SIG
from backend.services.portfolio_farm.metrics import summarise
from backend.services.portfolio_farm.policy import FarmResult, Policy

logger = logging.getLogger(__name__)

#: A held name absent this many consecutive sessions is treated as DELISTED and
#: resolved at `policy.delisting_return`. Deliberately a COUNTER and not a
#: lookup of "does this permno ever appear again": the second is a fact about
#: the future, and using it — even only for accounting — would put a
#: forward-looking quantity inside the loop. Five sessions is a week.
DELIST_AFTER_MISSING_SESSIONS = 5

#: Rows before which no decision is taken, so every trailing window is full.
DEFAULT_WARMUP = SIG.YEAR + SIG.MONTH


def _cap_weights(w: np.ndarray, cap: float) -> np.ndarray:
    """Weights under a per-name cap. May sum to LESS than 1 — that is the point.

    THE BUG THIS REPLACED, AND WHY IT MATTERED. The first version capped and
    then renormalised unconditionally, three times. With 3 names under a 20%
    cap that converges to 33% each — every position OVER the cap it was asked
    to respect, silently, with no error and a fully invested book. A cap that
    quietly stops applying at the concentrations where it matters most is worse
    than no cap, because the receipt still says `max_single_name: 0.20`.

    So there are now two regimes, and which one applied is visible in the sum:

      * FEASIBLE (`n * cap >= 1`) — water-filling. Capped names are held at the
        cap and their excess is redistributed pro-rata among the uncapped, which
        can push those over the cap, so it iterates. The book ends fully
        invested and every weight is <= cap.
      * INFEASIBLE (`n * cap < 1`) — every name sits at the cap and the
        remainder is CASH. This is a legitimate policy ("at most 20% each, at
        most 3 names"), not an error, and it is the same rule the arena's
        ce_kelly sizing already follows: capped conviction becomes cash, never
        a forced bet on the next name.
    """
    if cap <= 0 or cap >= 1:
        s = w.sum()
        return w / s if s > 0 else w
    n = len(w)
    if n == 0:
        return w
    if n * cap < 1.0:
        return np.full(n, float(cap))
    s = w.sum()
    w = (w / s) if s > 0 else np.full(n, 1.0 / n)
    for _ in range(50):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w = w.copy()
        w[over] = cap
        under = ~over
        room = w[under]
        if not under.any() or room.sum() <= 0:
            break
        w[under] = room + excess * (room / room.sum())
    return np.minimum(w, cap)


def _targets(sig_row: np.ndarray, eligible: np.ndarray, policy: Policy,
             vol_row: np.ndarray, cap_row: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(indices, weights) for one formation date. Empty when nothing qualifies."""
    idx = np.flatnonzero(eligible & np.isfinite(sig_row))
    if idx.size == 0:
        return idx, np.zeros(0)
    order = idx[np.argsort(-sig_row[idx], kind="stable")]
    chosen = order[:policy.top_k]
    if policy.sizing == "equal_weight":
        w = np.ones(chosen.size)
    elif policy.sizing == "inverse_vol":
        v = vol_row[chosen]
        # Missing vol makes a name ineligible for THIS sizing — missing is
        # missing, never "average". Same rule the arena's policies layer uses.
        w = np.where(np.isfinite(v) & (v > 0), 1.0 / np.maximum(v, 1e-8), 0.0)
        if w.sum() <= 0:
            w = np.ones(chosen.size)
    else:                                                    # cap_weight
        c = cap_row[chosen]
        w = np.where(np.isfinite(c) & (c > 0), c, 0.0)
        if w.sum() <= 0:
            w = np.ones(chosen.size)
    w = w / w.sum()
    return chosen, _cap_weights(w, policy.max_single_name)


def run(panel, policy: Policy, *, sig: np.ndarray | None = None,
        dolvol_ma: np.ndarray | None = None, vol: np.ndarray | None = None,
        warmup: int | None = None) -> FarmResult:
    """Replay one policy over the whole panel. Returns NAV, metrics, diagnostics.

    The three precomputed grids are optional arguments rather than internals
    because the farm runs hundreds of policies over ONE panel: computing the
    momentum grid six hundred times is six hundred times the work and exactly
    the same numbers. `farm.run_many` computes each grid once and passes it in.
    """
    T, N = panel.close.shape
    sig = SIG.matrix(panel, policy.signal) if sig is None else sig
    if dolvol_ma is None:
        dolvol_ma = SIG._roll_mean(panel.dolvol.astype(np.float64), SIG.MONTH, 5)
    if vol is None:
        vol = SIG._vol_matrix(panel)
    w0 = DEFAULT_WARMUP if warmup is None else int(warmup)
    if w0 >= T - 2:
        raise ValueError(f"panel has {T} rows, warmup needs {w0 + 3}")

    # NO whole-matrix float64 conversion. On a fifteen-year panel each of these
    # is ~200 MB in float32 and ~400 MB in float64, and `run` is called once per
    # POLICY — six hundred times, allocating and freeing gigabytes for numbers
    # that never changed. Rows are widened instead, N floats at a time, which is
    # free. Measured: the whole-matrix version made a 300-policy run
    # memory-bound rather than compute-bound.
    close, open_, ret, retx = panel.close, panel.open_, panel.ret, panel.retx

    shares = np.zeros(N)
    last_px = np.zeros(N)               # last price at which a name was marked
    missing = np.zeros(N, dtype=np.int32)
    cash = float(policy.notional_usd)
    cost_rate = 0.0 if policy.zero_cost_diagnostic else (
        (policy.transaction_cost_bps + policy.slippage_bps) / 10_000.0)

    pending: tuple[np.ndarray, np.ndarray] | None = None
    nav = np.full(T, np.nan)
    diag = {"n_decisions": 0, "n_fills": 0, "n_unfilled_names": 0,
            "n_delistings": 0, "delisting_cash": 0.0, "total_cost_usd": 0.0,
            "traded_notional_usd": 0.0, "days_holding_nothing": 0,
            "n_empty_selections": 0, "n_delist_measured": 0,
            "n_delist_assumed": 0, "stuck_capital_events": 0,
            "stuck_capital_usd": 0.0, "min_cash_usd": 0.0}
    t0 = time.perf_counter()

    for i in range(w0, T):
        held = shares != 0

        # 1. DIVIDENDS on yesterday's book, as cash. `ret - retx` is what the
        #    holder actually received; assuming free reinvestment at the close
        #    is a small free lunch and small free lunches compound.
        if held.any() and i > 0:
            d = ((ret[i].astype(np.float64) - retx[i].astype(np.float64))
                 * close[i - 1].astype(np.float64))
            d = np.where(np.isfinite(d), d, 0.0)
            cash += float((shares * d)[held].sum())

        # 2. DELISTING. A held name with no bar for a week is resolved at the
        #    last price it was marked at, times the declared assumption.
        gone = held & ~np.isfinite(close[i])
        missing = np.where(gone, missing + 1, 0)
        dead = gone & (missing >= DELIST_AFTER_MISSING_SESSIONS)
        if dead.any():
            # MEASURED where CRSP has it, DECLARED where it does not — and the
            # split is counted, because the sensitivity sweep showed this one
            # assumption is worth an 18x swing in terminal wealth. A run that
            # fell back on most of its exits is a run whose headline is still
            # an assumption, and the receipt must be able to say so.
            j = np.flatnonzero(dead)
            dl = (panel.delist_ret[j] if panel.delist_ret is not None
                  else np.full(j.size, np.nan))
            known = np.isfinite(dl)
            rate = np.where(known, dl, policy.delisting_return)
            proceeds = float((shares[j] * last_px[j] * (1.0 + rate)).sum())
            cash += proceeds
            diag["n_delistings"] += int(j.size)
            diag["n_delist_measured"] += int(known.sum())
            diag["n_delist_assumed"] += int((~known).sum())
            diag["delisting_cash"] += proceeds
            shares[dead] = 0.0
            held = shares != 0

        # 3. FILL yesterday's decision at TODAY'S OPEN.
        if pending is not None:
            chosen, weights = pending
            pending = None
            o = open_[i].astype(np.float64)
            px = np.where(np.isfinite(o) & (o > 0), o, np.nan)
            unpriceable = ~np.isfinite(px)

            # ALLOCATABLE, not EQUITY. A held name with no open price today
            # cannot be sold, so the capital sitting inside it cannot be
            # redeployed — and allocating against total equity anyway buys the
            # new book with money that is still in the old position. That is
            # implicit LEVERAGE: cash goes negative by exactly the stuck value,
            # silently, with no borrow cost.
            #
            # It is not a rare edge. `openprc` is missing on ~2.2% of CRSP daily
            # rows, so a twelve-name book meets one roughly every fourth
            # rebalance. Caught by self-review after the first leaderboard, and
            # pinned by `test_cash_never_goes_negative_...`; `min_cash_usd` is
            # on every receipt so the class cannot come back unnoticed.
            stuck = shares != 0
            stuck &= unpriceable
            stuck_value = float((shares[stuck] * last_px[stuck]).sum())
            live_value = float((shares * px)[np.isfinite(px) & (shares != 0)].sum())
            # A book cannot be 100.00% invested AND pay its commission. The
            # residual after the stuck-capital fix was exactly the fee: -$6.00
            # on a $10,000 book at 6 bps, because the targets consumed every
            # dollar and the fee then came out of nothing. Reserving the
            # ROUND-TRIP rate covers the worst case (sell everything, buy
            # everything) and costs 12 bps of deployment — smaller than the
            # thing it prevents, which is silent leverage.
            allocatable = (cash + live_value) * (1.0 - 2.0 * cost_rate)
            if stuck_value:
                diag["stuck_capital_events"] += 1
                diag["stuck_capital_usd"] += stuck_value

            target_sh = np.zeros(N)
            if chosen.size:
                ok = np.isfinite(px[chosen])
                diag["n_unfilled_names"] += int((~ok).sum())
                c_ok, w_ok = chosen[ok], weights[ok]
                if c_ok.size and allocatable > 0:
                    target_sh[c_ok] = (w_ok * allocatable) / px[c_ok]
            # A name we cannot price cannot be traded either way: keep it.
            target_sh[unpriceable] = shares[unpriceable]
            delta = target_sh - shares
            tradable = np.isfinite(px) & (delta != 0)
            if tradable.any():
                notional = np.abs(delta[tradable] * px[tradable]).sum()
                signed = float((delta[tradable] * px[tradable]).sum())
                fee = float(notional) * cost_rate
                cash -= signed + fee
                shares = np.where(tradable, target_sh, shares)
                diag["total_cost_usd"] += fee
                diag["traded_notional_usd"] += float(notional)
                diag["n_fills"] += 1

        # 4. MARK at the close.
        px_c = close[i].astype(np.float64)
        fresh = np.isfinite(px_c)
        last_px = np.where(fresh, px_c, last_px)
        pos = shares != 0
        nav[i] = cash + float((shares * last_px)[pos].sum())
        if cash < diag["min_cash_usd"]:
            diag["min_cash_usd"] = round(float(cash), 2)
        if not pos.any():
            diag["days_holding_nothing"] += 1

        # 5. DECIDE, at the close, for tomorrow's open.
        first = w0 + (policy.phase_offset % policy.holding_days)
        if (i >= first and (i - first) % policy.holding_days == 0
                and i < T - 1):
            liq = dolvol_ma[i]
            eligible = (panel.traded[i] & np.isfinite(px_c)
                        & (px_c >= policy.min_price) & np.isfinite(liq))
            if policy.universe_n and eligible.sum() > policy.universe_n:
                cand = np.flatnonzero(eligible)
                keep = cand[np.argsort(-liq[cand], kind="stable")[
                    :policy.universe_n]]
                m = np.zeros(N, dtype=bool)
                m[keep] = True
                eligible = m
            chosen, weights = _targets(sig[i], eligible, policy, vol[i],
                                       panel.mktcap[i].astype(np.float64))
            diag["n_decisions"] += 1
            if chosen.size == 0:
                diag["n_empty_selections"] += 1
            pending = (chosen, weights)

    diag["seconds"] = round(time.perf_counter() - t0, 3)
    diag["cost_drag_pct_of_start"] = round(
        100.0 * diag["total_cost_usd"] / policy.notional_usd, 4)
    dates = list(panel.dates[w0:])
    series = nav[w0:]
    return FarmResult(policy=policy, dates=dates, nav=[float(x) for x in series],
                      metrics=summarise(dates, series, panel), diagnostics=diag)
