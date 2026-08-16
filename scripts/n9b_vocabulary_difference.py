"""N9B's declared statistic: the DIFFERENCE between two confirmation medians.

    python -m scripts.n9b_vocabulary_difference

The prereg (`docs/TRIALS/PREREG_N9B_WIDER_VOCABULARY.md`) committed to this
before either number existed:

> The quantity is the **difference between two confirmation medians** — wide
> vocabulary minus narrow — because "1.42 is bigger than 1.271" is not a test
> (SS18).

Two point estimates in a sentence is the error this session spent the morning
correcting in N6, and it would have been very easy to commit here: the wide
run scores higher at both horizons and the temptation is to say so and stop.

WHY THE TWO RUNS ARE PAIRED
===========================
`_aggregate` seeds its own generator per call (`default_rng(SEED + H)`), and the
slice, block length and replicate count are identical between runs. So block
shift `i` in the narrow run is the SAME shift as block shift `i` in the wide
run. The two placebo series are therefore paired observation by observation,
and `wide_placebo[i] - narrow_placebo[i]` is a draw from the null distribution
of the difference under broken labels — which is the reference the observed
difference needs and the only thing that turns it into a test.

WHAT THIS CANNOT DO
===================
It cannot fix the fact that the confirmation slice has now been used TWICE. Any
third look at `DIA/XLV/XLI/XLP/XLU/XLB` is worth nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import power as PW

NARROW = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n9_mine_the_85.json"
WIDE = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n9b_wide_vocabulary.json"
OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n9b_difference.json"

#: N4B's break-even lift. Restated here only so the economic reading is printed
#: beside the statistical one and cannot be quoted without it.
L_MIN = {"20": 1.69, "60": 2.11}


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    if not (NARROW.exists() and WIDE.exists()):
        print("both runs must exist first")
        return 1
    nar = json.loads(NARROW.read_text(encoding="utf-8"))
    wid = json.loads(WIDE.read_text(encoding="utf-8"))

    rows = []
    print("N9B — wide vocabulary MINUS narrow, on the confirmation slice\n")
    print(f"{'H':>4} {'narrow':>7} {'wide':>7} {'diff':>7} {'null sd':>8} "
          f"{'MDE':>7} {'p(paired)':>10}  verdict")
    for H in ("20", "60"):
        hn, hw = nar["horizons"].get(H), wid["horizons"].get(H)
        if not hn or not hw:
            continue
        cn, cw = hn.get("confirm"), hw.get("confirm")
        if not cn or not cw or not cn.get("placebo_series") \
                or not cw.get("placebo_series"):
            print(f"{H:>4}  no persisted placebo series — re-run both")
            continue
        a = cn["placebo_series"]
        b = cw["placebo_series"]
        n = min(len(a), len(b))
        # Paired null: same block shift, both vocabularies.
        null = [b[i] - a[i] for i in range(n)]
        obs = cw["observed_median_lift"] - cn["observed_median_lift"]
        m = sum(null) / n
        sd = (sum((x - m) ** 2 for x in null) / max(n - 1, 1)) ** 0.5
        mde = PW.mde_from_se(sd) if sd > 0 else None
        # One-sided: the hypothesis is that the WIDER vocabulary reaches
        # further, so the alternative has a direction and the test follows it.
        p = (sum(1 for x in null if x >= obs) + 1) / (n + 1)
        det = mde is not None and abs(obs - m) >= mde
        verdict = ("VOCABULARY_BOUND" if (det and p < 0.05 and obs > 0)
                   else "NOT_DETECTABLE_IN_SCOPE")
        print(f"{H:>4} {cn['observed_median_lift']:>7.3f} "
              f"{cw['observed_median_lift']:>7.3f} {obs:>+7.3f} {sd:>8.3f} "
              f"{('-' if mde is None else f'{mde:7.3f}')} {p:>10.3f}  "
              f"{verdict}")
        econ = ("still below the break-even "
                f"{L_MIN[H]}" if cw["observed_median_lift"] < L_MIN[H]
                else f"ABOVE the break-even {L_MIN[H]}")
        print(f"      wide confirmation p = {cw['p_value']:.3f}; "
              f"narrow p = {cn['p_value']:.3f}; economically: {econ}")
        # AND THE EQUIVALENCE VERSION, which says more than the null does.
        # "Not detectable" leaves open whether these features moved the ceiling
        # by an amount that would have mattered. The amount that would have
        # mattered is exactly known: the gap from the narrow median to N4B's
        # break-even lift. If the difference's upper bound falls short of that
        # gap, these five features are RULED OUT as a route to a tradeable
        # rule — a powered negative rather than a shrug.
        gap = L_MIN[H] - cn["observed_median_lift"]
        eq = PW.can_rule_out_at_least(obs, sd, gap)
        print(f"      to reach break-even the difference had to be "
              f"+{gap:.3f}; upper bound {eq['upper_bound']:+.3f} -> "
              f"{eq['verdict']}")

        rows.append({"horizon": int(H),
                     "gap_to_break_even": gap,
                     "equivalence": eq,
                     "narrow_median": cn["observed_median_lift"],
                     "wide_median": cw["observed_median_lift"],
                     "difference": obs, "null_mean": m, "null_sd": sd,
                     "mde": mde, "p_paired": p, "n_paired": n,
                     "narrow_p": cn["p_value"], "wide_p": cw["p_value"],
                     "L_min": L_MIN[H],
                     "wide_clears_economic_bar":
                         cw["observed_median_lift"] >= L_MIN[H],
                     "verdict": verdict})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"rows": rows}, indent=2), encoding="utf-8")
    print(f"\nwritten  {OUT}")
    print("A higher median is not a wider reach until the difference has an "
          "interval. That is what this file is for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
