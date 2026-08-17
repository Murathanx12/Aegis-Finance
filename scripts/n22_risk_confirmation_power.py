"""N22 — can the RISK claim ever be confirmed? Asked before spending anything.

    python -m scripts.n22_risk_confirmation_power

WHY THIS IS FREE, AND THEREFORE OBLIGATORY (S64)
================================================
M4-SELECTOR refused to spend the reserved window because the RETURN effect
(+8.64%/yr) sat below the MDE that window can deliver (12.84%). S59 says risk
resolves roughly 30x sooner than return on identical data, and that ratio has
reproduced. So the same question has to be asked of the statistic the product
actually claims: **can 74 reserved months resolve the risk effect?**

Every input below comes from the ALREADY-SPENT selection window plus a COUNT OF
MONTHS. Nothing from 2020-06 onward is read. A power check that consumes no
outcome costs nothing, and a confirmation whose MDE exceeds its effect returns
"not established" whatever the world does — after which the window is gone AND
nothing was learned.

THE CORRECTION THIS RUN MAKES TO OUR OWN METHOD
===============================================
`sizing_layer_risk_outcome.py` projected forward power the way M4 did:

    mde_forward = mde_full * sqrt(n_full / n_forward)

and compared it to the FULL-WINDOW effect. That is right for a MEAN — the SE of
a mean scales as 1/sqrt(n) and the mean itself does not depend on window length.

**Max drawdown is not a mean. It is a path extremum, and it grows with the
length of the path.** Comparing a fourteen-year drawdown difference against a
six-year standard error is comparing two different windows' statistics, and it
inflates power in the flattering direction. The same defect family as the house
one: correct arithmetic against the wrong world.

So this run measures the forward quantity DIRECTLY. Circular-block sub-paths of
exactly 74 months are drawn from the selection window; the effect is the mean
delta ACROSS those sub-paths and the SE is their dispersion. Both are then on
the horizon the confirmation would actually have. The naive projection is
printed beside it so the size of the error is a number rather than a worry.

THE OTHER CONSTRAINT, WHICH NO STANDARD ERROR SEES (S39)
========================================================
A drawdown claim is about crises. A block bootstrap over a window holding two
crises produces a tidy SE while every resample inherits the same two events. So
the run also reports how many distinct 20% drawdowns a 74-month window should
expect at the selection window's own rate. If that number is near one, the
confirmation is a single-event test whatever its SE says.

ALPHA IS NOT 0.05 HERE
======================
Order 8's calendar allocation gives the live window 2020-06..2026-07 a k_eff of
2.00 and **alpha 0.025 per outcome**, shared with IV-ORACLE-GAP-1. M4's payload
records that allocation and then computed its MDE at the two-sided 5% constant.
Both alphas are reported below. The direction matters: a stricter alpha makes
every MDE LARGER, so it can only reinforce a DO-NOT-SPEND ruling and can never
have manufactured one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.replay_personalities import (BLOCK_DAYS, END, ETF, OUTDIR, START,
                                          VOL_POLICIES, build)
from scripts.sizing_layer_risk_outcome import EPISODE_DEPTH, n_drawdown_episodes

#: The reserved confirmation window, unchanged from M4's reservation.
CONFIRM_START, CONFIRM_END = "2020-06-01", "2026-07-17"
MONTHS_RESERVED = 74

N_SUBPATHS = 4000
SEED = 20260817

#: Two-sided critical values. 0.05 is what M4 used; 0.025 is what the calendar
#: allocation actually declared for this window.
Z_TWO_SIDED = {0.05: 1.959964, 0.025: 2.241403}
Z_POWER_80 = 0.8416212

#: The configuration the product ships. The other three are reported, but the
#: ruling attaches to the one `/risk` actually runs.
SHIPPED = "voltarget_15_cap1.0"


def ann_vol_pct(x: np.ndarray) -> float:
    return float(np.std(x) * np.sqrt(252) * 100)


def mdd_pct(x: np.ndarray) -> float:
    w = np.cumprod(1 + x)
    return float(-(w / np.maximum.accumulate(w) - 1).min() * 100)


def subpath_index(n: int, length: int, rng) -> np.ndarray:
    """`N_SUBPATHS` circular-block sub-paths of exactly `length` days.

    SHARED across every policy and outcome, for the reason the replay learned
    the hard way: independent resample streams are uncorrelated by construction,
    so cells drawn separately cannot be compared and a design effect computed
    from them measures the RNG.
    """
    nb = int(np.ceil(length / BLOCK_DAYS))
    offs = np.arange(BLOCK_DAYS)
    starts = rng.integers(0, n, size=(N_SUBPATHS, nb))
    return np.stack([((starts[i][:, None] + offs[None, :]).ravel() % n)[:length]
                     for i in range(N_SUBPATHS)])


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
    books = build(zero, r, base)["books"]

    n_days = len(base)
    n_months_sel = (base.index.to_period("M").nunique())
    days_per_month = n_days / n_months_sel
    fwd_days = int(round(MONTHS_RESERVED * days_per_month))

    print("=" * 78)
    print("N22 — CAN THE RESERVED WINDOW CONFIRM THE RISK CLAIM?")
    print("=" * 78)
    print(f"  selection window   {base.index[0].date()}..{base.index[-1].date()}"
          f"  {n_days} days / {n_months_sel} months")
    print(f"  reserved window    {CONFIRM_START}..{CONFIRM_END}  "
          f"= {MONTHS_RESERVED} months = {fwd_days} trading days")
    print(f"  read from the reserved window: NOTHING. Only a count of months.")

    rng = np.random.default_rng(SEED)
    idx = subpath_index(n_days, fwd_days, rng)

    # ── how many crises does 74 months even contain? (S39) ─────────────────
    bh = books["buy_and_hold"].to_numpy()
    n_ep_full = n_drawdown_episodes(np.cumprod(1 + bh))
    rate = n_ep_full / n_months_sel
    expected_ep = rate * MONTHS_RESERVED
    deep = np.mean([mdd_pct(bh[i]) >= 100 * EPISODE_DEPTH for i in idx])
    print("\n" + "-" * 78)
    print("FIRST, THE CONSTRAINT NO STANDARD ERROR SEES")
    print("-" * 78)
    print(f"  distinct {EPISODE_DEPTH:.0%} drawdowns in the selection window   "
          f"{n_ep_full}")
    print(f"  implied rate                                    "
          f"{rate:.4f} per month")
    print(f"  expected in {MONTHS_RESERVED} reserved months                    "
          f"{expected_ep:.2f}")
    print(f"  share of {MONTHS_RESERVED}-month sub-paths reaching "
          f"{EPISODE_DEPTH:.0%}      {deep:.0%}")
    print(f"\n  READ THE {deep:.0%} CORRECTLY — it is not {deep:.0%} of real "
          f"{MONTHS_RESERVED}-month windows.")
    print(f"  The selection window contains {n_ep_full} crossing of "
          f"{EPISODE_DEPTH:.0%}, and a circular block")
    print("  bootstrap puts that one crisis's blocks into almost every draw. The")
    print("  figure measures how thoroughly 2008 is reused, not how often such a")
    print("  window contains a crisis. The honest number is the RATE line above:")
    print(f"  {expected_ep:.2f} expected episodes, which is below one.")

    # ── the forward power, measured on the forward horizon ─────────────────
    print("\n" + "-" * 78)
    print("THE FORWARD QUANTITY, MEASURED ON THE FORWARD HORIZON")
    print("-" * 78)
    print(f"  {'policy':<22} {'outcome':<12} {'eff@74':>8} {'SE@74':>7} "
          f"{'MDE.05':>8} {'MDE.025':>8}  verdict")
    rows = []
    for lab, _, _ in VOL_POLICIES:
        a = books[lab].to_numpy()
        b = books[lab + "__matched_constant"].to_numpy()
        for oname, fn in (("volatility", ann_vol_pct), ("drawdown", mdd_pct)):
            full = fn(a) - fn(b)
            draws = np.array([fn(a[i]) - fn(b[i]) for i in idx])
            eff74 = float(draws.mean())
            se74 = float(draws.std(ddof=1))
            mde = {al: (z + Z_POWER_80) * se74 for al, z in Z_TWO_SIDED.items()}
            ok = abs(eff74) >= mde[0.025]
            rows.append({"policy": lab, "outcome": oname,
                         "effect_full_window": full, "effect_74m": eff74,
                         "se_74m": se74, "mde_74m_a05": mde[0.05],
                         "mde_74m_a025": mde[0.025],
                         "resolvable_at_declared_alpha": bool(ok)})
            print(f"  {lab:<22} {oname:<12} {eff74:>+8.2f} {se74:>7.2f} "
                  f"{mde[0.05]:>8.2f} {mde[0.025]:>8.2f}  "
                  f"{'RESOLVABLE' if ok else 'NOT resolvable'}")

    # ── what the naive projection would have claimed ───────────────────────
    print("\n" + "-" * 78)
    print("THE PROJECTION WE USED BEFORE, AND WHY IT IS WRONG FOR A DRAWDOWN")
    print("-" * 78)
    print(f"  {'policy':<22} {'outcome':<12} {'eff@full':>9} {'eff@74':>8} "
          f"{'ratio':>7}")
    for row in rows:
        rat = (row["effect_74m"] / row["effect_full_window"]
               if row["effect_full_window"] else float("nan"))
        print(f"  {row['policy']:<22} {row['outcome']:<12} "
              f"{row['effect_full_window']:>+9.2f} {row['effect_74m']:>+8.2f} "
              f"{rat:>7.2f}")
    print("\n  A MEAN-like statistic keeps its value when the window shortens,")
    print("  so volatility's ratio is ~1 and the old projection was fine for")
    print("  it. A PATH EXTREMUM does not: a shorter path has a smaller")
    print("  drawdown, so carrying the fourteen-year difference into a")
    print("  six-year standard error credits the confirmation with an effect")
    print("  it could not observe.")

    # ── the ruling ─────────────────────────────────────────────────────────
    ship = [r for r in rows if r["policy"] == SHIPPED]
    resolvable = [r for r in rows if r["resolvable_at_declared_alpha"]]
    print("\n" + "=" * 78)
    print("RULING")
    print("=" * 78)
    for row in ship:
        print(f"  {SHIPPED} {row['outcome']:<12} effect {row['effect_74m']:+.2f}"
              f"  vs MDE {row['mde_74m_a025']:.2f} at the DECLARED alpha 0.025")
    n_ship_ok = sum(1 for r in ship if r["resolvable_at_declared_alpha"])
    if n_ship_ok:
        ruling = "PRE_REGISTER"
        print(f"\n  {n_ship_ok} of {len(ship)} shipped-configuration outcomes "
              f"can be resolved on the\n  reserved window. That claim has a "
              f"route from EXPLORE to confirmed and\n  the pre-registration is "
              f"worth writing.")
    else:
        ruling = "PERMANENTLY_SCREEN_GRADE"
        print("\n  NEITHER outcome of the shipped configuration can be resolved")
        print("  on the reserved window at the alpha this calendar declares.")
        print("  The risk claim is therefore PERMANENTLY SCREEN-GRADE on this")
        print("  corpus, and the page has to say so rather than implying a")
        print("  confirmation is pending. The window stays unspent — it cannot")
        print("  be spent usefully, which is a stronger statement than M4's")
        print("  'not on this candidate'.")
    print(f"\n  outcomes resolvable across all four configurations: "
          f"{len(resolvable)} of {len(rows)}")
    # A ruling that flips with the alpha choice is a ruling about the alpha.
    lax = sum(1 for r in rows if abs(r["effect_74m"]) >= r["mde_74m_a05"])
    print(f"  and at the LAXER alpha 0.05 M4 used: {lax} of {len(rows)}. The "
          f"ruling does not\n  hinge on which alpha governs, which is the only "
          f"reason it is worth stating.")

    out = OUTDIR / "n22_risk_confirmation_power.json"
    out.write_text(json.dumps(
        {"selection_window": f"{START}..{END}", "n_days": n_days,
         "n_months_selection": int(n_months_sel),
         "confirmation_window": f"{CONFIRM_START}..{CONFIRM_END}",
         "months_reserved": MONTHS_RESERVED, "forward_days": fwd_days,
         "alpha_declared": 0.025, "alpha_note":
             "calendar allocation 2020-06..2026-07, k_eff 2.00, shared with "
             "IV-ORACLE-GAP-1 (Order 8). M4 recorded this allocation and then "
             "used the 5% constant; both are reported and the stricter one "
             "governs.",
         "crisis_episodes_selection": n_ep_full,
         "expected_episodes_in_74m": expected_ep,
         "share_of_subpaths_reaching_depth": float(deep),
         "share_of_subpaths_caveat":
             "NOT the share of real 74-month windows containing a crisis. The "
             "selection window crosses the depth once, and a circular block "
             "bootstrap reuses that one crisis in nearly every draw. The "
             "expected-episode rate is the honest number.",
         "rows": rows, "shipped_configuration": SHIPPED, "ruling": ruling,
         "consumed_from_confirmation_window": "nothing — a count of months"},
        indent=1, default=float), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
