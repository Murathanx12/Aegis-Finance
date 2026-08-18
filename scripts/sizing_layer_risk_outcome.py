"""M4 said no window can confirm a return effect this size. Try the other exit.

    python -m scripts.sizing_layer_risk_outcome

WHY THIS RUNS RIGHT AFTER THE M4 RULING
=======================================
M4-SELECTOR selected one candidate from 206 and then refused to spend the
reserved window on it: +8.64%/yr against an MDE of 12.84% over 74 months. Every
effect in the measured library is of a size that needs fourteen years or more,
so a six-year forward window cannot confirm ANY of them.

S59 named the two exits. This tests the first one, on our own data, before
committing to it:

    max drawdown resolves in about 4 years where terminal return needs ~95.

If that holds here, the sizing layer is the only part of this system that can
be certified on the window we actually hold, and the roadmap should say so. If
it does not hold, the claim that risk is cheaper to measure than return is
something we have been repeating rather than checking.

WHAT IS BEING MEASURED
======================
Volatility targeting: scale exposure inversely to recent realised volatility.
It is a SIZING rule, not a selection rule — which is why the strategy library
REFUSED to score it alongside the decile spreads. It has no cross-section to
sort; it wraps whatever it is applied to.

DECLARED BEFORE RUNNING, so none of it can be tuned to the answer:
  * base asset         SPY total return, daily
  * window             2006-01-01..2019-12-31 (the same EXPLORE window as the
                       library, so no new slice is consumed)
  * volatility estimate 60 trading days of daily returns, annualised
  * target             15% annualised — a conventional number, not a fitted one
  * cap                1.0 (long only, no leverage: what could actually be run)
                       and 1.5 reported beside it
  * rebalance          monthly, on the last trading day
  * cost               10bp per unit of notional traded, same as the library
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ETF = Path(r"C:\Users\mrthn\Aegis module\data\etf\etf_adjusted_close.parquet")
OUTDIR = Path(r"C:\Users\mrthn\Aegis module\data\library")

START, END = "2006-01-01", "2019-12-31"
LOOKBACK_DAYS = 60
TARGET_VOL = 0.15
CAPS = (1.0, 1.5)
COST_BPS_ONE_WAY = 10.0
N_BOOT = 2000
BLOCK_DAYS = 21              # one month of trading days
SEED = 20260817

#: The reserved forward window, for the same power question M4 asked.
MONTHS_RESERVED = 74


#: A drawdown episode has to reach this depth to count as an event.
EPISODE_DEPTH = 0.20


def max_drawdown(wealth: np.ndarray) -> float:
    peak = np.maximum.accumulate(wealth)
    return float((wealth / peak - 1.0).min())


def n_drawdown_episodes(wealth: np.ndarray, depth: float = EPISODE_DEPTH) -> int:
    """How many DISTINCT crises the window actually contains.

    The number that decides whether a max-drawdown comparison means anything.
    A block bootstrap over a window holding ONE crisis produces a tidy standard
    error while every resample that includes the crash inherits the same event
    — the bootstrap measures the sampling variation of a statistic, not the
    variation across crises, and only the second is what a drawdown claim is
    about. S39: a window is only a window if something measured fits in it.
    """
    peak = np.maximum.accumulate(wealth)
    dd = wealth / peak - 1.0
    n, inside = 0, False
    for v in dd:
        if v < -depth and not inside:
            n, inside = n + 1, True
        elif inside and v > -0.001:
            inside = False
    return n


def run(ret: pd.Series, cap: float) -> dict:
    """Vol-targeted exposure, rebalanced monthly, costed on what it trades."""
    vol = ret.rolling(LOOKBACK_DAYS).std() * np.sqrt(252)
    # The weight for month m is set from volatility through the LAST DAY of
    # month m-1 and held all month. Nothing inside the month informs it.
    month = ret.index.to_period("M")
    w_month = (TARGET_VOL / vol).clip(upper=cap).groupby(month).last().shift(1)
    w = pd.Series(w_month.reindex(month).to_numpy(), index=ret.index)
    w = w.ffill().fillna(0.0)
    traded = w.groupby(month).first().diff().abs().fillna(0.0)
    cost_by_month = traded * COST_BPS_ONE_WAY / 1e4
    strat = w * ret
    # Charge the rebalance on the first day of each month it happens.
    firsts = pd.Series(ret.index).groupby(month.to_numpy()).first()
    charge = pd.Series(0.0, index=ret.index)
    for m, d in firsts.items():
        if m in cost_by_month.index:
            charge.loc[d] = cost_by_month.loc[m]
    strat = strat - charge
    return {"w": w, "ret": strat}


def stats(r: pd.Series) -> dict:
    wealth = (1 + r).cumprod().to_numpy()
    n = len(r)
    return {
        "annual_return": float(wealth[-1] ** (252 / n) - 1),
        "annual_vol": float(r.std() * np.sqrt(252)),
        "max_drawdown": max_drawdown(wealth),
        "sharpe": float(r.mean() / r.std() * np.sqrt(252)),
        "n_days": n,
    }


def block_boot_delta(a: np.ndarray, b: np.ndarray, fn, rng) -> float:
    """SE of `fn(a) - fn(b)` under a shared circular block resample.

    Shared, not independent: the two series are the same asset on the same days
    and resampling them separately would break that pairing and inflate the SE
    of a difference whose whole point is that the days are common.
    """
    n = len(a)
    nb = int(np.ceil(n / BLOCK_DAYS))
    offs = np.arange(BLOCK_DAYS)
    out = np.empty(N_BOOT)
    starts = rng.integers(0, n, size=(N_BOOT, nb))
    for i in range(N_BOOT):
        idx = ((starts[i][:, None] + offs[None, :]).ravel() % n)[:n]
        out[i] = fn(a[idx]) - fn(b[idx])
    return float(np.std(out, ddof=1))


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    px = pd.read_parquet(ETF)["SPY"].dropna()
    px.index = pd.to_datetime(px.index)
    r_all = px.pct_change().dropna()
    # Lookback comes from BEFORE the window so the first month is not special.
    r = r_all.loc[pd.Timestamp(START) - pd.Timedelta(days=200):
                  pd.Timestamp(END)]
    base = r.loc[START:END]
    print(f"SPY daily {base.index[0].date()}..{base.index[-1].date()}  "
          f"{len(base)} days")

    rng = np.random.default_rng(SEED)
    ann_vol = lambda x: float(np.std(x) * np.sqrt(252))          # noqa: E731
    ann_ret = lambda x: float(np.prod(1 + x) ** (252 / len(x)) - 1)  # noqa: E731

    def mdd(x):
        w = np.cumprod(1 + x)
        return max_drawdown(w)

    b = stats(base)
    print(f"\n{'':22} {'buy&hold':>10}", end="")
    results = {"buy_and_hold": b, "caps": {}}
    runs = {}
    for cap in CAPS:
        runs[cap] = run(r, cap)["ret"].loc[START:END]
        print(f" {'cap ' + str(cap):>10}", end="")
    print()
    for k, lab in (("annual_return", "annual return"),
                   ("annual_vol", "annual volatility"),
                   ("max_drawdown", "max drawdown"),
                   ("sharpe", "sharpe")):
        print(f"  {lab:<20}", end="")
        print(f" {b[k]:>10.4f}", end="")
        for cap in CAPS:
            print(f" {stats(runs[cap])[k]:>10.4f}", end="")
        print()

    print("\n" + "=" * 74)
    print("THE DIFFERENCES, EACH AGAINST ITS OWN MDE (S19, S59)")
    print("=" * 74)
    n_ep = n_drawdown_episodes(np.cumprod(1 + base.to_numpy()))
    results["n_crisis_episodes"] = n_ep
    print(f"  distinct drawdowns reaching {EPISODE_DEPTH:.0%} in this window: "
          f"{n_ep}\n")
    print(f"  {'outcome':<18} {'cap':>4} {'delta':>10} {'SE':>9} {'MDE':>9} "
          f"{'MDE@74mo':>10}  verdict")
    # 74 months of daily data, for the same forward question M4 asked.
    n_fwd_days = int(MONTHS_RESERVED * 21)
    for cap in CAPS:
        s_arr = runs[cap].to_numpy()
        b_arr = base.to_numpy()
        for lab, fn in (("annual volatility", ann_vol),
                        ("max drawdown", mdd),
                        ("annual return", ann_ret)):
            d = fn(s_arr) - fn(b_arr)
            se = block_boot_delta(s_arr, b_arr, fn, rng)
            mde = (1.959964 + 0.8416212) * se
            mde_fwd = mde * np.sqrt(len(b_arr) / n_fwd_days)
            v = ("RESOLVABLE on the reserved window" if abs(d) >= mde_fwd
                 else "not resolvable there")
            here = "" if abs(d) >= mde else "  [below MDE even here]"
            if lab == "max drawdown":
                # The bootstrap SE is not the binding constraint here and
                # printing it alone would be the more flattering half.
                v = (f"rests on {n_ep} crisis episode"
                     f"{'s' if n_ep != 1 else ''} — SE understates it")
            print(f"  {lab:<18} {cap:>4} {d:>+10.4f} {se:>9.4f} {mde:>9.4f} "
                  f"{mde_fwd:>10.4f}  {v}{here}")
            results["caps"].setdefault(str(cap), {})[lab] = {
                "delta": d, "se": se, "mde": mde, "mde_forward_74mo": mde_fwd,
                "detectable_in_sample": bool(abs(d) >= mde),
                "resolvable_forward": bool(abs(d) >= mde_fwd),
                **({"n_crisis_episodes": n_ep,
                    "se_caveat": ("a block bootstrap over a window holding "
                                  f"{n_ep} crisis measures sampling variation, "
                                  "not variation across crises")}
                   if lab == "max drawdown" else {})}

    # ── the S59 ceiling, made concrete ─────────────────────────────────────
    print("\n" + "=" * 74)
    print("THE BREAK-EVEN RETURN SACRIFICE")
    print("=" * 74)
    print("  S59's ceiling is 'risk reduced; return effect not established'.")
    print("  The way past a ceiling is to price it: how much annual return")
    print("  would you give up before the risk reduction stopped being worth")
    print("  it, at a declared risk aversion?")
    for cap in CAPS:
        c = results["caps"][str(cap)]
        dv = c["annual volatility"]["delta"]
        dr = c["annual return"]["delta"]
        # Mean-variance at lambda: indifference when dR = lambda * d(variance).
        v_b = b["annual_vol"] ** 2
        v_s = (b["annual_vol"] + dv) ** 2
        for lam in (1.0, 3.0):
            be = lam * (v_s - v_b) / 2.0
            print(f"    cap {cap}, lambda {lam}: variance falls "
                  f"{v_b - v_s:+.5f}, so a mean-variance investor pays up to "
                  f"{-be:+.4%}/yr for it; measured return change {dr:+.4%}/yr")
    print("\n  lambda PRICES a trade-off between two MEASURED quantities and")
    print("  cannot supply a missing return estimate. Both numbers above are")
    print("  measured; neither is imputed.")

    out = OUTDIR / "sizing_layer_risk.json"
    out.write_text(json.dumps(
        {"declared": {"base": "SPY total return daily (EODHD adjusted_close)",
                      "window": f"{START}..{END}", "target_vol": TARGET_VOL,
                      "lookback_days": LOOKBACK_DAYS, "caps": list(CAPS),
                      "rebalance": "monthly, weight set from data through the "
                                   "last day of the prior month",
                      "cost_bps": COST_BPS_ONE_WAY, "block_days": BLOCK_DAYS},
         "results": results, "months_reserved": MONTHS_RESERVED},
        indent=1, default=float), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
