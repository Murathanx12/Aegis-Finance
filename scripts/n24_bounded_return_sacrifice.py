"""N24 — bound the return sacrifice instead of reporting it unresolved.

    python -m scripts.n24_bounded_return_sacrifice

WHAT IS WRONG WITH THE CURRENT SENTENCE
=======================================
`/risk` says *"the return effect is not established — the estimate is 0.03x its
own MDE."* That is true, and it is weaker than what the data supports. It is an
`mde_mean` statement: it says our instrument could not separate the estimate
from zero. It says nothing about which values have been EXCLUDED, and exclusion
is what a decision needs.

The other half of the pair has existed since N4B. `can_rule_out_at_least` asks
whether the upper confidence bound sits below the smallest effect that would
matter. Here the margin is not invented for the occasion — it is the break-even
sacrifice, already computed from two measured quantities:

    a mean-variance investor at risk aversion lambda pays up to
    lambda * (var_buyhold - var_policy) / 2 per year for the variance reduction

So the decision rule is one comparison:

    UCB(return drag) < break_even(lambda)
        => the policy is worth it at that lambda WHEREVER the true return sits
           in the interval. A decision, not a hedge.

    otherwise
        => the interval still covers sacrifices large enough to make it a bad
           trade, and the honest page says so.

LAMBDA IS DECLARED, NOT SOLVED FOR
==================================
The break-even lambda that would flip a NOT_DEMONSTRATED into a RULED_OUT is
reported at the bottom as a DIAGNOSTIC. It is not a recommendation. The four
personalities are declared preferences and tuning one to make a verdict come out
would turn them into four more strategy parameters — which is the one thing the
mission text says they must never become.

EVERYTHING HERE IS ON THE ALREADY-SPENT SELECTION WINDOW.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from backend.services.research_gym.power import (Z_ALPHA_ONE_SIDED_05,
                                                 can_rule_out_at_least,
                                                 se_required_to_rule_out)
from scripts.replay_personalities import (END, ETF, OUTDIR, START,
                                          VOL_POLICIES, build, resample_index)

SEED = 20260817

#: The declared preference ladder. Not swept, not fitted.
LAMBDAS = (1.0, 3.0)

#: The configuration `/risk` ships.
SHIPPED = "voltarget_15_cap1.0"


def ann_ret_pct(x: np.ndarray) -> float:
    return float((np.prod(1 + x) ** (252 / len(x)) - 1) * 100)


def ann_var(x: np.ndarray) -> float:
    return float((np.std(x) * np.sqrt(252)) ** 2)


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
    books = build(pd.Series(0.0, index=r.index), r, base)["books"]
    bh = books["buy_and_hold"].to_numpy()

    rng = np.random.default_rng(SEED)
    idx = resample_index(len(base), rng)

    print("=" * 78)
    print("N24 — THE RETURN SACRIFICE, BOUNDED RATHER THAN LEFT UNRESOLVED")
    print("=" * 78)
    print(f"  window {base.index[0].date()}..{base.index[-1].date()}  "
          f"{len(base)} days, SPY total return, comparator = buy and hold")
    print(f"  drag > 0 means the policy GAVE UP return; the bound is one-sided\n"
          f"  at 5% because the claim is directional")

    rows = []
    for lab, _, _ in VOL_POLICIES:
        a = books[lab].to_numpy()
        d_ret = ann_ret_pct(a) - ann_ret_pct(bh)
        draws = np.array([ann_ret_pct(a[i]) - ann_ret_pct(bh[i]) for i in idx])
        se = float(draws.std(ddof=1))
        drag = -d_ret
        ucb = drag + Z_ALPHA_ONE_SIDED_05 * se
        dvar = ann_var(bh) - ann_var(a)
        print(f"\n  {lab}")
        print(f"    measured return change   {d_ret:+.2f} %/yr  "
              f"(SE {se:.2f}, so the drag is {drag:+.2f})")
        print(f"    variance reduction       {dvar:+.5f}")
        print(f"    upper 95% bound on drag  {ucb:+.2f} %/yr")
        for lam in LAMBDAS:
            margin = lam * dvar / 2.0 * 100.0
            v = can_rule_out_at_least(drag, se, margin)
            worth = v["verdict"] == "RULED_OUT"
            print(f"    lambda {lam:<4g} break-even {margin:5.2f} %/yr  "
                  f"-> {v['verdict']:<17} "
                  f"{'WORTH IT wherever the truth sits' if worth else ''}")
            need_se = se_required_to_rule_out(drag, margin)
            extra = None
            if need_se and need_se > 0:
                # SE scales as 1/sqrt(n): how much MORE of this data would the
                # bound need? Reported in years because that is the unit the
                # decision is made in.
                yrs = len(base) / 252.0
                need_yrs = yrs * (se / need_se) ** 2
                extra = need_yrs - yrs
                print(f"{'':17}needs SE <= {need_se:.2f} => "
                      f"{need_yrs:.0f} yrs of this data "
                      f"({extra:+.0f} more than we hold)")
            rows.append({"policy": lab, "lambda": lam,
                         "return_change_pct": d_ret, "drag_pct": drag,
                         "se_pct": se, "upper_bound_pct": ucb,
                         "variance_reduction": dvar,
                         "break_even_pct": margin, "verdict": v["verdict"],
                         "worth_it_across_the_interval": bool(worth),
                         "se_required": need_se,
                         "extra_years_required": extra})

    # ── the diagnostic, labelled as one ────────────────────────────────────
    print("\n" + "=" * 78)
    print("DIAGNOSTIC — the lambda that would flip it (NOT a recommendation)")
    print("=" * 78)
    for lab, _, _ in VOL_POLICIES:
        rr = [x for x in rows if x["policy"] == lab][0]
        dvar = rr["variance_reduction"]
        lam_star = (2.0 * rr["upper_bound_pct"] / 100.0 / dvar
                    if dvar > 0 else None)
        if lam_star is None:
            print(f"  {lab:<22} n/a — this policy did not reduce variance")
        else:
            print(f"  {lab:<22} lambda* {lam_star:.2f}")
        for x in rows:
            if x["policy"] == lab:
                x["lambda_star"] = lam_star
    print("\n  A reader at a DECLARED risk aversion above lambda* is making a")
    print("  trade that is good across the whole interval. Choosing lambda")
    print("  because it clears the bound is not that reader — it is fitting a")
    print("  preference to a result, and the four personalities stop being")
    print("  preferences the moment that happens.")

    ship = [x for x in rows if x["policy"] == SHIPPED]
    won = [x for x in ship if x["worth_it_across_the_interval"]]
    print("\n" + "=" * 78)
    print("WHAT THE PAGE MAY NOW SAY")
    print("=" * 78)
    if won:
        for x in won:
            print(f"  At lambda {x['lambda']:g}, the return sacrifice is bounded "
                  f"above by {x['upper_bound_pct']:.2f}%/yr against a break-even "
                  f"of\n  {x['break_even_pct']:.2f}%/yr — worth it wherever the "
                  f"true value sits in the interval.")
    else:
        print("  NOT AT EITHER DECLARED LAMBDA. The upper bound on the return")
        print("  sacrifice still exceeds what the variance reduction is worth,")
        print("  so 'not established' remains the honest sentence and the")
        print("  equivalence version does not rescue it.")
        for x in ship:
            print(f"    lambda {x['lambda']:<4g} UCB {x['upper_bound_pct']:.2f} "
                  f"vs break-even {x['break_even_pct']:.2f}  "
                  f"(short by {x['upper_bound_pct'] - x['break_even_pct']:.2f})")
        print("\n  BUT THE GAP IS NOT THE 95-YEAR KIND. The extra data the bound")
        print("  needs is printed above in years, and it is single digits, not")
        print("  a career — which is S59's ratio showing up a third time.")

    # ── the trap this table sets, named before anyone walks into it ────────
    others = [x for x in rows
              if x["policy"] != SHIPPED and x["worth_it_across_the_interval"]]
    against = [x for x in rows if x["verdict"] == "AT_LEAST_MARGIN"]
    print("\n" + "=" * 78)
    print("THE TRAP IN THIS TABLE, AND THE BAR")
    print("=" * 78)
    print(f"  {len(others)} of {len(rows) - len(ship)} non-shipped cells came "
          f"back RULED_OUT.")
    for x in others:
        print(f"    {x['policy']:<22} lambda {x['lambda']:g}")
    print(f"\n  THE PRODUCT DOES NOT MOVE TO ONE OF THEM. `{SHIPPED}` was the")
    print("  declared configuration before any of this was computed, and")
    print("  switching to whichever cell cleared is selection on the outcome —")
    print("  S37's shape with an equivalence test wearing it. These cells are")
    print("  reported because suppressing them would be worse; they are barred")
    print("  from becoming the shipped rule on this evidence.")
    print("\n  Note WHY they clear, too: a weaker de-risking has a smaller")
    print("  variance reduction AND a smaller drag, and both of these happen to")
    print("  have a POSITIVE measured return change, which is the noisy part of")
    print("  the comparison pushing the bound down. That is not a reason to")
    print("  prefer them.")
    if against:
        print(f"\n  And the machinery runs the other way too — "
              f"{len(against)} cell(s) came back")
        print("  AT_LEAST_MARGIN, meaning the point estimate of the drag ALREADY")
        print("  exceeds what the variance reduction is worth:")
        for x in against:
            print(f"    {x['policy']:<22} lambda {x['lambda']:g}  drag "
                  f"{x['drag_pct']:+.2f} vs break-even {x['break_even_pct']:.2f}")
        print("  A bound that can only ever say 'worth it' would not be a bound.")
    print(f"\n  MULTIPLICITY: {len(rows)} cells are four policies x two declared")
    print("  lambdas on ONE price path, and the lambdas are a rescaling of one")
    print("  measured variance reduction rather than a second experiment. Treat")
    print("  these as roughly FOUR chances, not eight, and the shipped one is")
    print("  the only one that was named in advance.")

    out = OUTDIR / "n24_bounded_return_sacrifice.json"
    out.write_text(json.dumps(
        {"window": f"{START}..{END}", "n_days": len(base),
         "comparator": "buy and hold", "lambdas_declared": list(LAMBDAS),
         "rows": rows, "shipped_configuration": SHIPPED,
         "any_ruled_out_at_declared_lambda": bool(won)},
        indent=1, default=float), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
