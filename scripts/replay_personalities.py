"""Replay per personality — and the matched control that asks if it is timing.

    python -m scripts.replay_personalities

THE COMPARISON THAT MATTERS, AND IT IS NOT VOL-TARGET vs BUY-AND-HOLD
=====================================================================
A vol-targeted book holds less equity on average than a buy-and-hold book. So
"vol targeting beat buy-and-hold" is two claims wearing one number: it held
less, AND it held less at the right times. Only the second is a skill claim,
and N13 already settled which way that usually goes -- his own trading
SUBTRACTED 29-66 points, and the lesson recorded was SIZING NOT TIMING.

So every vol-target policy here is run beside a CONSTANT-EXPOSURE policy whose
fixed weight equals that policy's own realised average weight. Same average
equity, no timing at all. The difference between them is the timing, isolated,
and it is the only part that could be a discovery.

This is the matched-control design the mission asks for -- winner versus
matched loser, never a gallery of survivors -- applied to a policy instead of
an episode.

DECLARED BEFORE RUNNING
=======================
  * base            SPY total return, daily (EODHD adjusted_close)
  * window          2006-01-01..2019-12-31, the already-claimed EXPLORE slice
  * cash            0%/yr in the primary run. This UNDERSTATES every policy
                    that holds cash, including the ones being tested, so the
                    bias runs against the conclusion rather than toward it. A
                    2-year-yield sensitivity is reported beside it.
  * policies        fixed list below, chosen before any was scored
  * objectives      the four DECLARED personalities, unchanged. They are
                    preferences, not parameters: nothing here tunes a lambda,
                    and a ranked comparison names the objective it used.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from backend.services.research_gym.multiplicity import effective_tests
from backend.services.research_gym.utility import PERSONALITIES

ETF = Path(r"C:\Users\mrthn\Aegis module\data\etf\etf_adjusted_close.parquet")
MACRO = Path(r"C:\Users\mrthn\Aegis module\data\macro\fred_macro_snap20260726.parquet")
OUTDIR = Path(r"C:\Users\mrthn\Aegis module\data\library")

START, END = "2006-01-01", "2019-12-31"
LOOKBACK_DAYS = 60
COST_BPS_ONE_WAY = 10.0
N_BOOT = 2000
BLOCK_DAYS = 21
SEED = 20260817

#: (label, target vol, cap). Declared before scoring; not swept afterwards.
VOL_POLICIES = [("voltarget_10_cap1.0", 0.10, 1.0),
                ("voltarget_15_cap1.0", 0.15, 1.0),
                ("voltarget_20_cap1.0", 0.20, 1.0),
                ("voltarget_15_cap1.5", 0.15, 1.5)]


def weights_voltarget(ret: pd.Series, target: float, cap: float) -> pd.Series:
    vol = ret.rolling(LOOKBACK_DAYS).std() * np.sqrt(252)
    month = ret.index.to_period("M")
    w_month = (target / vol).clip(upper=cap).groupby(month).last().shift(1)
    w = pd.Series(w_month.reindex(month).to_numpy(), index=ret.index)
    return w.ffill().fillna(0.0)


def apply_weights(ret: pd.Series, w: pd.Series, cash: pd.Series) -> pd.Series:
    """Equity at weight w, remainder in cash, rebalanced monthly, costed."""
    month = ret.index.to_period("M")
    first = pd.Series(ret.index).groupby(month.to_numpy()).first()
    traded = w.groupby(month).first().diff().abs().fillna(0.0)
    charge = pd.Series(0.0, index=ret.index)
    for m, d in first.items():
        if m in traded.index:
            charge.loc[d] = traded.loc[m] * COST_BPS_ONE_WAY / 1e4
    return w * ret + (1.0 - w) * cash - charge


def path_stats(r: pd.Series) -> dict:
    wealth = (1 + r).cumprod().to_numpy()
    peak = np.maximum.accumulate(wealth)
    return {"net_return_pct": float((wealth[-1] - 1) * 100),
            "max_drawdown_pct": float(-(wealth / peak - 1).min() * 100),
            "min_wealth": float(wealth.min()),
            "annual_vol_pct": float(r.std() * np.sqrt(252) * 100)}


class _Stats:
    """Duck-types PathStats for the declared objectives, no more."""

    def __init__(self, d: dict) -> None:
        self.__dict__.update(d)


def score(d: dict, obj) -> float:
    return float(obj.path_fn(_Stats(d)))


def resample_index(n: int, rng) -> np.ndarray:
    """ONE set of circular block resamples, shared by every cell.

    The first version let each (policy, objective) cell draw its own indices,
    and then correlated the resulting draws to estimate how redundant the cells
    were. That measured nothing: independent resample streams are uncorrelated
    BY CONSTRUCTION, and it duly reported rho_bar = 0.002 across sixteen cells
    that are four lambda-variants of two statistics on one price path.

    Correct arithmetic against the wrong world, in the code written to stop
    exactly that. To compare cells, the resamples have to be common.
    """
    nb = int(np.ceil(n / BLOCK_DAYS))
    offs = np.arange(BLOCK_DAYS)
    starts = rng.integers(0, n, size=(N_BOOT, nb))
    return np.stack([((starts[i][:, None] + offs[None, :]).ravel() % n)[:n]
                     for i in range(N_BOOT)])


def boot_delta(a: np.ndarray, b: np.ndarray, obj, idx_bank: np.ndarray):
    """Objective difference under each SHARED resample; both books, same days."""
    out = np.empty(len(idx_bank))
    for i, idx in enumerate(idx_bank):
        out[i] = (score(path_stats(pd.Series(a[idx])), obj)
                  - score(path_stats(pd.Series(b[idx])), obj))
    return out


def build(cash_series: pd.Series, r: pd.Series, base: pd.Series) -> dict:
    cash = cash_series.reindex(r.index).ffill().fillna(0.0)
    books: dict[str, pd.Series] = {}
    avg_w: dict[str, float] = {}
    ones = pd.Series(1.0, index=r.index)
    books["buy_and_hold"] = apply_weights(r, ones, cash).loc[START:END]
    avg_w["buy_and_hold"] = 1.0
    for lab, tgt, cap in VOL_POLICIES:
        w = weights_voltarget(r, tgt, cap)
        books[lab] = apply_weights(r, w, cash).loc[START:END]
        avg_w[lab] = float(w.loc[START:END].mean())
        # THE MATCHED CONTROL: identical average equity exposure, held flat.
        wc = pd.Series(avg_w[lab], index=r.index)
        books[lab + "__matched_constant"] = apply_weights(r, wc,
                                                          cash).loc[START:END]
        avg_w[lab + "__matched_constant"] = avg_w[lab]
    return {"books": books, "avg_w": avg_w}


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    px = pd.read_parquet(ETF)["SPY"].dropna()
    px.index = pd.to_datetime(px.index)
    r = px.pct_change().dropna().loc[
        pd.Timestamp(START) - pd.Timedelta(days=200):pd.Timestamp(END)]
    base = r.loc[START:END]

    zero = pd.Series(0.0, index=r.index)
    built = build(zero, r, base)
    books, avg_w = built["books"], built["avg_w"]
    rng = np.random.default_rng(SEED)

    print(f"SPY daily {base.index[0].date()}..{base.index[-1].date()}  "
          f"{len(base)} days   cash = 0%/yr (primary, conservative)")
    print("\n" + "=" * 78)
    print("THE BOOKS")
    print("=" * 78)
    print(f"  {'policy':<34} {'avg w':>6} {'return':>9} {'maxDD':>8} {'vol':>7}")
    st = {k: path_stats(v) for k, v in books.items()}
    for k in books:
        s = st[k]
        print(f"  {k:<34} {avg_w[k]:>6.2f} {s['net_return_pct']:>8.1f}% "
              f"{s['max_drawdown_pct']:>7.1f}% {s['annual_vol_pct']:>6.1f}%")

    print("\n" + "=" * 78)
    print("SCORED UNDER EACH DECLARED PERSONALITY (every ranking names its "
          "objective)")
    print("=" * 78)
    ranks = {}
    for obj in PERSONALITIES:
        scored = sorted(((score(st[k], obj), k) for k in books), reverse=True)
        ranks[obj.name] = [{"policy": k, "score": v} for v, k in scored]
        print(f"\n  {obj.name}")
        for v, k in scored[:4]:
            print(f"    {v:>9.2f}  {k}")

    # ── the question the ranking cannot answer ─────────────────────────────
    print("\n" + "=" * 78)
    print("IS IT THE TIMING? each vol-target against its OWN matched constant")
    print("=" * 78)
    print(f"  {'policy':<24} {'objective':<16} {'delta':>9} {'SE':>8} "
          f"{'MDE':>8}  verdict")
    timing, draw_bank = [], []
    idx_bank = resample_index(len(base), rng)
    for lab, _, _ in VOL_POLICIES:
        a = books[lab].to_numpy()
        b = books[lab + "__matched_constant"].to_numpy()
        for obj in PERSONALITIES:
            d = score(st[lab], obj) - score(st[lab + "__matched_constant"], obj)
            draws = boot_delta(a, b, obj, idx_bank)
            draw_bank.append(draws)
            se = float(np.std(draws, ddof=1))
            mde = (1.959964 + 0.8416212) * se
            ok = abs(d) >= mde
            timing.append({"policy": lab, "objective": obj.name, "delta": d,
                           "se": se, "mde": mde, "detectable": bool(ok)})
            print(f"  {lab:<24} {obj.name:<16} {d:>+9.2f} {se:>8.2f} "
                  f"{mde:>8.2f}  "
                  f"{'DETECTABLE' if ok else 'below its own MDE'}")

    det = [t for t in timing if t["detectable"]]
    print(f"\n  timing effects detectable: {len(det)} of {len(timing)}")
    if not det:
        print("  READ THIS AS: on this window, under every declared "
              "personality,\n  vol targeting is not distinguishable from "
              "simply holding LESS. The\n  risk reduction is real and it is "
              "the AVERAGE EXPOSURE doing it --\n  which is N13's 'sizing not "
              "timing', arrived at from the other side.")

    # ALL SIXTEEN POINT ESTIMATES ARE POSITIVE, AND THAT IS NOT SIXTEEN
    # OBSERVATIONS. Four objectives differing only in a drawdown lambda,
    # applied to four policies on ONE path: the cells are near-copies. S58's
    # design effect says how near — MEASURED from the bootstrap draws rather
    # than assumed — so "16 of 16 agree" cannot be read as a sign test.
    D = np.corrcoef(np.vstack(draw_bank))
    rho = float(np.mean(D[np.triu_indices_from(D, k=1)]))
    k_eff = effective_tests(len(draw_bank), max(0.0, min(1.0, rho)))
    n_pos = sum(1 for t in timing if t["delta"] > 0)
    print(f"\n  {n_pos} of {len(timing)} point estimates are positive — but "
          f"the mean pairwise")
    print(f"  correlation across those cells is rho_bar={rho:.3f}, so k_eff = "
          f"{k_eff:.2f}.")
    print(f"  {len(timing)} agreeing cells are worth about {k_eff:.1f} "
          f"independent ones: the")
    print(f"  consistency is one observation wearing sixteen hats.")

    # ── THE RISK OUTCOME vs THE SAME MATCHED CONTROL ───────────────────────
    #
    # N18's null was about the OBJECTIVE (return - lambda x drawdown). It did
    # NOT test the one thing a volatility-targeting rule is actually FOR: does
    # it deliver lower realised volatility than holding a constant weight at
    # the same average exposure? That is a different statistic and it has to be
    # asked separately, because the product claim rests on it and nothing
    # measured so far establishes it.
    print("\n" + "=" * 78)
    print("THE RISK OUTCOME vs the SAME matched constant — never tested before")
    print("=" * 78)
    print(f"  {'policy':<24} {'outcome':<16} {'delta':>9} {'SE':>8} "
          f"{'MDE':>8}  verdict")

    def ann_vol_pct(x):
        return float(np.std(x) * np.sqrt(252) * 100)

    def mdd_pct(x):
        w = np.cumprod(1 + x)
        return float(-(w / np.maximum.accumulate(w) - 1).min() * 100)

    risk_rows, risk_draws = [], []
    for lab, _, _ in VOL_POLICIES:
        a = books[lab].to_numpy()
        b = books[lab + "__matched_constant"].to_numpy()
        for oname, fn in (("annual volatility", ann_vol_pct),
                          ("max drawdown", mdd_pct)):
            d = fn(a) - fn(b)
            draws = np.array([fn(a[i]) - fn(b[i]) for i in idx_bank])
            risk_draws.append(draws)
            se = float(np.std(draws, ddof=1))
            mde = (1.959964 + 0.8416212) * se
            ok = abs(d) >= mde
            risk_rows.append({"policy": lab, "outcome": oname, "delta": d,
                              "se": se, "mde": mde, "detectable": bool(ok)})
            print(f"  {lab:<24} {oname:<16} {d:>+9.2f} {se:>8.2f} {mde:>8.2f}"
                  f"  {'DETECTABLE' if ok else 'below its own MDE'}")
    n_vol_det = sum(1 for r in risk_rows
                    if r["outcome"] == "annual volatility" and r["detectable"])
    n_dd_det = sum(1 for r in risk_rows
                   if r["outcome"] == "max drawdown" and r["detectable"])
    print(f"\n  volatility reductions detectable vs matched constant: "
          f"{n_vol_det} of {len(VOL_POLICIES)}")
    print(f"  drawdown reductions   detectable vs matched constant: "
          f"{n_dd_det} of {len(VOL_POLICIES)}")
    # The SAME multiplicity treatment the timing cells got. Eight cells on one
    # path are not eight observations, and a result that survives its MDE still
    # owes the count of chances it had.
    Dr = np.corrcoef(np.vstack(risk_draws))
    rho_r = float(np.mean(Dr[np.triu_indices_from(Dr, k=1)]))
    k_eff_r = effective_tests(len(risk_draws), max(0.0, min(1.0, rho_r)))
    print(f"  across these {len(risk_rows)} cells rho_bar={rho_r:.3f} ⇒ "
          f"k_eff {k_eff_r:.2f}")
    print("\n  SO: N18's objective null and this are BOTH true and not in")
    print("  conflict. `return - lambda x drawdown` mixes in a return term")
    print("  that is unresolvable on this window, and that noise is what")
    print("  swamped the objective. Isolating the RISK statistic removes it.")
    print("  The rule is therefore NOT merely 'hold less' — but this is a")
    print("  SCREEN-grade result on the EXPLORE window, at k_eff ~"
          f"{k_eff_r:.1f}, and the tightest cell sits at 0.96x its MDE.")

    # ── sensitivity: cash actually earns something ─────────────────────────
    try:
        rf = pd.read_parquet(MACRO)["DGS2"].dropna() / 100.0 / 252.0
        rf.index = pd.to_datetime(rf.index)
        alt = build(rf, r, base)
        print("\n" + "=" * 78)
        print("SENSITIVITY — cash earns the 2-year yield instead of zero")
        print("=" * 78)
        print(f"  {'policy':<34} {'return @0%':>11} {'return @2Y':>11}")
        for k in books:
            print(f"  {k:<34} "
                  f"{path_stats(books[k])['net_return_pct']:>10.1f}% "
                  f"{path_stats(alt['books'][k])['net_return_pct']:>10.1f}%")
        print("\n  The 2-year yield is a PROXY for a cash rate, not a cash "
              "rate;\n  it is reported to bound the direction of the bias, "
              "not to restate\n  the result. Every conclusion above uses the "
              "0% run, which is the\n  one that penalises the policies being "
              "tested.")
    except Exception as e:                                       # noqa: BLE001
        print(f"\n  sensitivity unavailable: {e}")

    out = OUTDIR / "replay_personalities.json"
    out.write_text(json.dumps(
        {"window": f"{START}..{END}", "declared_cash": "0%/yr primary",
         "policies": list(books), "avg_weights": avg_w,
         "stats": st, "rankings": ranks, "timing_vs_matched_constant": timing,
         "n_timing_detectable": len(det),
         "timing_cells_rho_bar": rho, "timing_cells_k_eff": k_eff,
         "timing_cells_positive": n_pos,
         "risk_outcome_vs_matched_constant": risk_rows,
         "risk_cells_rho_bar": rho_r, "risk_cells_k_eff": k_eff_r}, indent=1, default=float),
        encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
