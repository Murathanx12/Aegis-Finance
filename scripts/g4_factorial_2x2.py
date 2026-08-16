"""Does knowing the EXPECTATION add anything, or was that just a tighter filter?

    python -m scripts.g4_factorial_2x2

WHY THIS EXISTS — MY OWN HEADLINE WAS CONFOUNDED
================================================
G4 V1 reported:

    positive EPS  (51,384 events)  ->  +0.25%
    beat by >1σ   (28,010 events)  ->  +1.88%

and called it "seven times the signal from knowing what was expected". Two
reviewers caught the same defect independently, and they are right: **those are
overlapping sets and the second is a strictly tighter selection.** Any tighter
conditioning on a variable correlated with the outcome produces a larger
conditional mean. That comparison is nested-set arithmetic and it is evidence of
nothing.

The test that actually decides it is the FACTORIAL, because it breaks the
nesting:

                        surprise > 0        surprise <= 0
    EPS > 0             cell A              cell B
    EPS <= 0            cell C              cell D

If expectations carry information beyond the announcement, then **C > D** and
**B < A** — the surprise moves the outcome WITHIN a fixed level of the raw
announcement. The decisive cell is **C: a company that lost money and still beat
expectations.** If that is positive, "what was expected" is doing work that "what
happened" cannot do. If C ≈ D, the expectation layer is re-ranking on something
already in the EPS sign and the honest report is that it adds nothing.

INFERENCE, BECAUSE THIS IS THE FIRST CANDIDATE POSITIVE SINCE N9 WAS WITHDRAWN
=============================================================================
§37 applies with full force: a new instrument's first positive is the one that
looks like it working.

* **The unit is the announcement DATE, never the row.** Earnings cluster into
  ~4 weeks a quarter and every firm reporting on one day shares that day's
  market move. Treating 58,066 rows as 58,066 observations is the §58 error.
  Standard errors come from a block bootstrap over dates.
* **Reported raw AND date-demeaned.** Demeaning within the announcement date
  removes any common factor that day exactly, which turns the 2x2 into a purely
  cross-sectional statement and cannot be gamed by a rising market.
* **Differences carry their own SE** (§18), rather than two intervals being
  eyeballed for overlap.
* **The MDE is printed whatever the result** (§19), so a null here is a
  statement about the world rather than about the sample.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

DATA = Path(r"C:\Users\mrthn\Aegis module\data\g4\earnings_v1")

#: Bootstrap resamples over announcement dates. Fixed a priori.
N_BOOT = 2000

#: The seed is declared, not chosen after looking at the answer. `default_rng`
#: per house rule, never the legacy global.
SEED = 20260816


def load() -> list[dict]:
    rows: list[dict] = []
    for f in sorted(DATA.glob("*.jsonl")):
        with f.open(encoding="utf-8") as fh:
            rows += [json.loads(l) for l in fh]
    return rows


def _date_of(r: dict) -> str:
    return str(r["first_public_ts"])[:10]


def block_bootstrap(dates: np.ndarray, values: np.ndarray, labels: np.ndarray,
                    n_cells: int, rng) -> np.ndarray:
    """Resample DATES with replacement; recompute every cell mean each draw.

    Resampling dates rather than rows is the whole point: it preserves the fact
    that one day's announcements move together, which is exactly the dependence
    a row-level bootstrap would erase and then not tell you about.
    """
    uniq = np.unique(dates)
    idx_by_date = {d: np.flatnonzero(dates == d) for d in uniq}
    out = np.full((N_BOOT, n_cells), np.nan)
    for b in range(N_BOOT):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        sel = np.concatenate([idx_by_date[d] for d in pick])
        lab, val = labels[sel], values[sel]
        for c in range(n_cells):
            m = lab == c
            if m.sum():
                out[b, c] = val[m].mean()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sigma", type=float, default=0.0,
                    help="surprise threshold in sd of analyst disagreement "
                         "(0.0 = plain sign, the pre-declared primary)")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    rows = load()
    ok = [r for r in rows
          if r.get("numeric_surprise") is not None
          and r.get("market_reaction") is not None
          and r.get("actual") is not None]
    print(f"records {len(rows):,} -> usable {len(ok):,} "
          f"(surprise AND reaction AND actual)")

    dates = np.array([_date_of(r) for r in ok])
    react = np.array([float(r["market_reaction"]) for r in ok])
    eps = np.array([float(r["actual"]) for r in ok])
    surp = np.array([float(r["numeric_surprise"]) for r in ok])

    # Date-demeaned reaction: removes that day's common move exactly. A day on
    # which only ONE firm announces demeans to zero and carries no information,
    # so those rows are dropped from the demeaned panel and COUNTED.
    dem = np.full_like(react, np.nan)
    singleton = 0
    for d in np.unique(dates):
        m = dates == d
        if m.sum() < 2:
            singleton += int(m.sum())
            continue
        dem[m] = react[m] - react[m].mean()
    have_dem = ~np.isnan(dem)
    print(f"distinct announcement dates: {len(np.unique(dates)):,}  "
          f"(the inference unit, §58)")
    print(f"rows on single-announcement dates, dropped from the demeaned "
          f"panel: {singleton:,}")

    # cell 0 = A (EPS>0, surprise>t) 1 = B (EPS>0, surprise<=t)
    # cell 2 = C (EPS<=0, surprise>t) 3 = D (EPS<=0, surprise<=t)
    t = a.sigma
    lab = np.where(eps > 0,
                   np.where(surp > t, 0, 1),
                   np.where(surp > t, 2, 3))
    names = {0: "A  EPS>0  surprise>t ", 1: "B  EPS>0  surprise<=t",
             2: "C  EPS<=0 surprise>t ", 3: "D  EPS<=0 surprise<=t"}

    rng = np.random.default_rng(SEED)

    for tag, vals, mask in (("RAW next-session reaction", react,
                             np.ones(len(react), bool)),
                            ("DATE-DEMEANED (market removed exactly)", dem,
                             have_dem)):
        print("\n" + "=" * 70)
        print(f"{tag}   threshold t = {t:g} sd")
        print("=" * 70)
        v, l, d_ = vals[mask], lab[mask], dates[mask]
        boot = block_bootstrap(d_, v, l, 4, rng)

        cells = {}
        for c in range(4):
            m = l == c
            mean = v[m].mean() if m.sum() else float("nan")
            se = np.nanstd(boot[:, c], ddof=1)
            cells[c] = (int(m.sum()), mean, se)
            print(f"  {names[c]}   n {m.sum():>6,}   "
                  f"mean {100*mean:+6.2f}%   SE {100*se:.2f}pp")

        def diff(c1: int, c2: int, what: str) -> None:
            d = cells[c1][1] - cells[c2][1]
            bd = boot[:, c1] - boot[:, c2]
            se = np.nanstd(bd, ddof=1)
            lo, hi = np.nanpercentile(bd, [2.5, 97.5])
            z = d / se if se > 0 else float("nan")
            # 80%-power MDE for THIS comparison, printed whatever the verdict.
            mde = (1.959964 + 0.8416212) * se
            print(f"\n  {what}")
            print(f"    {100*d:+.2f}pp   SE {100*se:.2f}pp   z {z:+.2f}   "
                  f"95% CI [{100*lo:+.2f}, {100*hi:+.2f}]pp")
            print(f"    80%-power MDE {100*mde:.2f}pp  "
                  f"({'RESOLVABLE' if abs(d) >= mde else 'below MDE — not detectable'})")

        print("\n  --- does the EXPECTATION add anything, holding the "
              "announcement fixed? ---")
        diff(0, 1, "A - B : surprise sign WITHIN positive EPS")
        diff(2, 3, "C - D : surprise sign WITHIN negative EPS  <- the "
                   "non-nested test")
        diff(2, 1, "C - B : lost money but BEAT  vs  made money but MISSED")

        # THE MIRROR, and it is the harder question. The comparisons above show
        # the expectation adds information given the announcement. This asks the
        # reverse: given the surprise, does knowing whether the company actually
        # MADE MONEY add anything? If A ~ C and B ~ D, the raw announcement is
        # redundant once the expectation is known — which is a much stronger
        # statement than "expectations help", and it is the one that says the
        # factory must be given the expectation or it will learn the wrong
        # variable.
        print("\n  --- MIRROR: does the ANNOUNCEMENT add anything, holding "
              "the expectation fixed? ---")
        diff(0, 2, "A - C : EPS sign WITHIN a beat")
        diff(1, 3, "B - D : EPS sign WITHIN a miss")

        # The interaction: is the surprise effect the same in both strata? If it
        # is, one number describes it; if not, the layer is conditional and the
        # factory must be told which stratum it is in.
        inter = (cells[0][1] - cells[1][1]) - (cells[2][1] - cells[3][1])
        bi = (boot[:, 0] - boot[:, 1]) - (boot[:, 2] - boot[:, 3])
        sei = np.nanstd(bi, ddof=1)
        print(f"\n  INTERACTION (A-B) - (C-D): {100*inter:+.2f}pp   "
              f"SE {100*sei:.2f}pp   z {inter/sei:+.2f}")

        # And the arithmetic that started this, shown as the nesting it is.
        pos = v[eps[mask] > 0]
        big = v[(surp[mask] > 1)]
        print(f"\n  the NESTED comparison that was reported as a finding:")
        print(f"    EPS>0        n {len(pos):>6,}  mean {100*pos.mean():+.2f}%")
        print(f"    surprise>1sd n {len(big):>6,}  mean {100*big.mean():+.2f}%")
        print(f"    -> overlapping sets, the second strictly tighter. NOT a "
              f"statement about expectations.")

    print("\nNo verdict is registered from this script: G4 is a data layer and "
          "this is its plumbing test. A tradable claim needs a "
          "pre-registration, a reserved window and a cost model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
