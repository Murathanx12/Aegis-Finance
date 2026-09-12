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
import math
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

#: Trading sessions in a year, for turning the panel's DAILY return stdev into
#: the ANNUALISED volatility the cost curve's impact term is calibrated in.
SESSIONS_PER_YEAR = 252.0

#: Dollar-volume cuts for the per-tercile cost breakdown on the receipt.
#: DECLARED, in round numbers, before any run was graded with them -- a cut
#: chosen after seeing which one flatters the split is not a cut.
LIQUIDITY_TERCILE_CUTS_USD = (1e7, 1e8)
LIQUIDITY_TERCILE_NAMES = ("under_10m", "10m_to_100m", "over_100m")


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


def eligible_at(panel, i: int, policy, liq: np.ndarray,
                px_c: np.ndarray | None = None) -> np.ndarray:
    """The universe a decision at row `i` may choose from. (N,) bool.

    THE ONE DEFINITION. `diagnostics` scores signals on exactly this set, and
    it has to be this set: a rank IC computed over every name in the panel,
    reported next to a book drawn from the top-500 by dollar volume, describes
    a universe the book never traded. Neither number would look wrong.

    `liq` is the trailing dollar-volume mean at row `i` — passed in rather than
    recomputed, because the caller has already built the whole matrix and the
    rolling window is the expensive part.
    """
    import numpy as _np

    if px_c is None:
        px_c = panel.close[i].astype(_np.float64)
    # `px_c` is SPLIT-ADJUSTED and is the right thing to mark with and the
    # wrong thing to screen with: a $5 floor is about the price that actually
    # changes hands. `close_raw` is that price.
    screen_px = (panel.close_raw[i].astype(_np.float64)
                 if getattr(panel, "close_raw", None) is not None else px_c)
    eligible = (panel.traded[i] & _np.isfinite(px_c)
                & (screen_px >= policy.min_price) & _np.isfinite(liq))
    if policy.universe_n and eligible.sum() > policy.universe_n:
        cand = _np.flatnonzero(eligible)
        keep = cand[_np.argsort(-liq[cand], kind="stable")[:policy.universe_n]]
        m = _np.zeros(panel.close.shape[1], dtype=bool)
        m[keep] = True
        eligible = m
    return eligible


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
    # A liquidity-reduced panel is only valid for the universe it was reduced
    # FOR. Running a deeper book on it would silently select from names that
    # happened to survive the reduction, which is a different universe wearing
    # the same policy hash — the failure class that has moved a farm answer
    # more than a strategy did four times. So it refuses.
    lim = getattr(panel, "universe_reduced_to", None)
    if lim is not None:
        if policy.universe_n and policy.universe_n > lim:
            raise ValueError(
                f"panel was liquidity-reduced to rank {lim}, but this policy "
                f"asks for a universe of {policy.universe_n}. The names beyond "
                f"rank {lim} are NOT in this panel, so the book would be drawn "
                f"from a truncated universe. Rebuild with "
                f"reduce_for_universe_n={policy.universe_n}, or load the full "
                f"panel.")
        floors = getattr(panel, "reduction_min_prices", ())
        if floors and policy.min_price not in floors:
            raise ValueError(
                f"panel was liquidity-reduced at min_price {list(floors)}, but "
                f"this policy uses {policy.min_price}. A different price floor "
                f"changes which names are eligible and therefore how deep the "
                f"top-{policy.universe_n} cut reaches, so the reduction is not "
                f"valid for it.")

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

    # THE CURVE, RESOLVED ONCE. Under `flat` nothing below this line runs and
    # the fee arithmetic is byte-identical to what it was, which is what makes
    # a re-grade under `flat` reproduce an archived net to the cent.
    use_curve = policy.curve != "flat"
    curve_fit = None
    if use_curve:
        from backend.services import cost_curve as CC
        if policy.curve == "retail_paper":
            raise ValueError(
                "curve='retail_paper' graded against a CRSP institutional "
                "replay is a REGIME MISMATCH, not a cost choice. Retail fills "
                "see IEX quotes and a partial-fill process this engine does "
                "not simulate; pricing them off the SIP-wide tape would "
                "understate them by construction. Grade a retail book on "
                "retail fills, or declare curve='taq_empirical'.")
        curve_fit = CC.load_regression()
        # The farm's CRSP panel carries PERMNOS, not tickers, so the measured
        # branch of the curve (which is keyed on ticker) is unreachable from
        # here and every fill is priced by the regression. Stated on the
        # receipt rather than left for a reader to infer from a provenance
        # count they did not expect.
        curve_b = CC.regression_coefficients(curve_fit)
        curve_eta = CC.ETA_SQRT_IMPACT

    pending: tuple[np.ndarray, np.ndarray] | None = None
    nav = np.full(T, np.nan)
    diag = {"n_decisions": 0, "n_fills": 0, "n_unfilled_names": 0,
            "n_delistings": 0, "delisting_cash": 0.0, "total_cost_usd": 0.0,
            "traded_notional_usd": 0.0, "days_holding_nothing": 0,
            "n_empty_selections": 0, "n_delist_measured": 0,
            "n_delist_assumed": 0, "stuck_capital_events": 0,
            "stuck_capital_usd": 0.0, "min_cash_usd": 0.0,
            "cost_curve": policy.curve}
    if use_curve:
        diag.update({
            "n_name_fills_priced_by_curve": 0,
            "n_name_fills_curve_unpriceable": 0,
            "cost_curve_spread_usd": 0.0,
            "cost_curve_impact_usd": 0.0,
            "tercile_notional_usd": [0.0, 0.0, 0.0],
            "tercile_cost_usd": [0.0, 0.0, 0.0],
        })

    def _rates(notional_vec, px_vec, dv_vec, volann_vec):
        """Per-fill ONE-WAY rate as a fraction, and the split that made it.

        Vectorised twin of `cost_curve.taq_empirical_one_way`'s regression
        branch; the scalar function is the readable one and
        `test_cost_curve.py` pins the two against each other. NaN where the
        regression has no answer -- the caller decides, and counts.
        """
        b0, b1, b2, b3 = curve_b
        ok = (np.isfinite(dv_vec) & (dv_vec > 0) & np.isfinite(px_vec)
              & (px_vec > 0) & np.isfinite(volann_vec) & (volann_vec >= 0))
        spread = np.where(
            ok, np.exp(b0 + b1 * np.log(np.where(ok, dv_vec, 1.0))
                       + b2 * np.log(np.where(ok, px_vec, 1.0))
                       + b3 * np.where(ok, volann_vec, 0.0)), np.nan)
        pov = np.where(ok, notional_vec / np.where(ok, dv_vec, 1.0), np.nan)
        impact = 1e4 * curve_eta * volann_vec * np.sqrt(np.where(ok, pov, 0.0))
        return spread, np.where(ok, impact, np.nan), ok

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
            if stuck_value:
                diag["stuck_capital_events"] += 1
                diag["stuck_capital_usd"] += stuck_value

            def _build_targets(alloc):
                t = np.zeros(N)
                if chosen.size:
                    okc = np.isfinite(px[chosen])
                    c_ok, w_ok = chosen[okc], weights[okc]
                    if c_ok.size and alloc > 0:
                        t[c_ok] = (w_ok * alloc) / px[c_ok]
                # A name we cannot price cannot be traded either way: keep it.
                t[unpriceable] = shares[unpriceable]
                d = t - shares
                return t, d, np.isfinite(px) & (d != 0)

            if chosen.size:
                diag["n_unfilled_names"] += int((~np.isfinite(px[chosen])).sum())

            reserve_rate = cost_rate
            if use_curve:
                # TWO PASSES, because the rate depends on the order size and
                # the order size depends on what is reserved for the rate. The
                # first pass prices a book sized at the DECLARED flat reserve
                # and takes the notional-weighted mean of the rates it finds;
                # the second reserves that instead. Under `flat` neither pass
                # runs and the arithmetic below is unchanged.
                _, d0, tr0 = _build_targets((cash + live_value) * (1.0 - 2.0 * cost_rate))
                if tr0.any():
                    n0 = np.abs(d0[tr0] * px[tr0])
                    sp0, im0, ok0 = _rates(n0, px[tr0], dolvol_ma[i][tr0],
                                           vol[i][tr0] * math.sqrt(SESSIONS_PER_YEAR))
                    r0 = np.where(ok0, (sp0 + im0) / 1e4, cost_rate)
                    tot = float(n0.sum())
                    if tot > 0:
                        reserve_rate = float((n0 * r0).sum() / tot)

            allocatable = (cash + live_value) * (1.0 - 2.0 * reserve_rate)
            target_sh, delta, tradable = _build_targets(allocatable)
            if tradable.any():
                notional_vec = np.abs(delta[tradable] * px[tradable])
                notional = notional_vec.sum()
                signed = float((delta[tradable] * px[tradable]).sum())
                if use_curve:
                    dv = dolvol_ma[i][tradable]
                    volann = vol[i][tradable] * math.sqrt(SESSIONS_PER_YEAR)
                    sp, im, okr = _rates(notional_vec, px[tradable], dv, volann)
                    # A fill the curve cannot price is charged the policy's OWN
                    # DECLARED flat rate and COUNTED. It is not charged an end
                    # of the declared band: `cost_model.resolve_band_by_picking`
                    # is a named refusal, and a loop is the last place to start
                    # quietly picking ends.
                    rates = np.where(okr, (sp + im) / 1e4, cost_rate)
                    fee = float((notional_vec * rates).sum())
                    diag["n_name_fills_priced_by_curve"] += int(okr.sum())
                    diag["n_name_fills_curve_unpriceable"] += int((~okr).sum())
                    diag["cost_curve_spread_usd"] += float(
                        (notional_vec * np.where(okr, sp, 0.0) / 1e4).sum())
                    diag["cost_curve_impact_usd"] += float(
                        (notional_vec * np.where(okr, im, 0.0) / 1e4).sum())
                    lo_cut, hi_cut = LIQUIDITY_TERCILE_CUTS_USD
                    band = np.where(dv >= hi_cut, 2, np.where(dv >= lo_cut, 1, 0))
                    costs_usd = notional_vec * rates
                    for b in (0, 1, 2):
                        m = band == b
                        if m.any():
                            diag["tercile_notional_usd"][b] += float(notional_vec[m].sum())
                            diag["tercile_cost_usd"][b] += float(costs_usd[m].sum())
                else:
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
            eligible = eligible_at(panel, i, policy, dolvol_ma[i], px_c)
            chosen, weights = _targets(sig[i], eligible, policy, vol[i],
                                       panel.mktcap[i].astype(np.float64))
            diag["n_decisions"] += 1
            if chosen.size == 0:
                diag["n_empty_selections"] += 1
            pending = (chosen, weights)

    diag["seconds"] = round(time.perf_counter() - t0, 3)
    diag["cost_drag_pct_of_start"] = round(
        100.0 * diag["total_cost_usd"] / policy.notional_usd, 4)
    # THE REALISED RATE, BETWEEN GROSS AND NET. A gross/net pair with no rate
    # between them is the C2 shape: a level with nothing to check it against.
    traded = float(diag["traded_notional_usd"])
    diag["mean_realised_cost_bps"] = (
        round(1e4 * diag["total_cost_usd"] / traded, 4) if traded > 0 else None)
    diag["cost_curve_provenance"] = (
        "flat_declared" if not use_curve else "EXTRAPOLATED_REGRESSION")
    if use_curve:
        n_ok = diag["n_name_fills_priced_by_curve"]
        n_no = diag["n_name_fills_curve_unpriceable"]
        n_all = n_ok + n_no
        # THE SPLIT IS THE REPORTABLE FACT. The CRSP panel carries permnos and
        # not tickers, so the ticker-keyed MEASURED branch of the curve is
        # structurally unreachable from this engine: every priced fill here is
        # an extrapolation, and saying "we used TAQ" would be false.
        diag["cost_curve_provenance_mix"] = {
            "EXTRAPOLATED_REGRESSION": n_ok,
            "DECLARED_CONSERVATIVE_policy_flat_fallback": n_no,
            "MEASURED_TAQ_EFFECTIVE": 0,
            "note": ("the farm's CRSP panel is keyed on PERMNO; the curve's "
                     "measured branch is keyed on TICKER and is therefore "
                     "unreachable from this engine. Every priced fill is the "
                     "regression."),
        }
        diag["curve_unpriceable_fraction"] = (
            round(n_no / n_all, 4) if n_all else None)
        # The same realised notional charged at the policy's DECLARED flat
        # rate: the counterfactual that makes the curve's effect readable
        # without a second full run.
        flat_cost = traded * cost_rate
        diag["total_cost_usd_if_flat"] = round(flat_cost, 2)
        diag["mean_flat_cost_bps"] = round(1e4 * cost_rate, 4)
        diag["cost_ratio_curve_over_flat"] = (
            round(diag["total_cost_usd"] / flat_cost, 4) if flat_cost > 0 else None)
        diag["cost_curve_spread_usd"] = round(diag["cost_curve_spread_usd"], 2)
        diag["cost_curve_impact_usd"] = round(diag["cost_curve_impact_usd"], 2)
        tn, tc = diag.pop("tercile_notional_usd"), diag.pop("tercile_cost_usd")
        diag["cost_bps_by_liquidity_tercile"] = {
            name: {"notional_usd": round(n, 2),
                   "cost_usd": round(c, 2),
                   "one_way_bps": round(1e4 * c / n, 4) if n > 0 else None}
            for name, n, c in zip(LIQUIDITY_TERCILE_NAMES, tn, tc, strict=True)}
        diag["liquidity_tercile_cuts_usd"] = list(LIQUIDITY_TERCILE_CUTS_USD)
    dates = list(panel.dates[w0:])
    series = nav[w0:]
    return FarmResult(policy=policy, dates=dates, nav=[float(x) for x in series],
                      metrics=summarise(dates, series, panel), diagnostics=diag)
