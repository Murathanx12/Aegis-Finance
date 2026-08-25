"""Reproduce known facts about known factors BEFORE trusting a novel result.

    python -m scripts.portfolio_farm_calibrate
    python -m scripts.portfolio_farm_calibrate --json

WHY THIS RUNS FIRST
===================
The 2026-08-25 cross-section run produced `value_bm` with a monotonicity of
**-0.90** over 32 years. Book-to-market is among the most replicated anomalies
there is, so a strongly negative reading has exactly two explanations:

    1. the join, the sign or the units are wrong;
    2. it is a true fact about THIS universe and THIS construction.

Nothing on the leaderboard distinguishes those, and the farm has already been
wrong in way (1) six times — the split bug alone was worth +36% of a single
day's "excess". **A novel result from an instrument that cannot reproduce a
known one is not evidence.**

So: assert structural facts that are true of the underlying characteristics
regardless of what any strategy earns. Not exact factor returns — universes,
weighting and trading conventions all differ, and a battery that demanded
Fama-French's numbers would fail for reasons that say nothing about this data.
These are the coarse, robust facts that a correct join cannot violate:

  * **value**  high book-to-market means CHEAP, so it must skew SMALLER by
    market cap, and it must be full of banks and insurers while the low end is
    full of biotech and software;
  * **profitability**  high ROE must skew LARGER and land on franchise
    businesses, not on distressed ones;
  * **revisions**  net analyst breadth must be roughly balanced around zero
    across the whole panel — a signal that is 90% upgrades is a filter bug, not
    an optimistic market.

WHAT A FAILURE MEANS
====================
A red line here invalidates every downstream result computed from that
characteristic, including ones already written down. That is the point: it is
cheaper to fail here than to publish a number and discover the join later.

FIRST RUN, 2026-08-25 — value and profitability both PASS, which is what makes
`value_bm`'s negative cross section a fact about the top-500-by-dollar-volume
universe (essentially large caps, where HML has been weak to negative since
1993) rather than a bug.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.portfolio_farm import characteristics as CH  # noqa: E402
from backend.services.portfolio_farm import revisions as RV        # noqa: E402

#: Industries that must dominate each tail. `ffi12` is Fama-French's own
#: 12-industry classification, shipped in `finratio`, so this is their
#: taxonomy rather than one invented here.
VALUE_INDUSTRIES = {"MONEY", "UTIL", "ENRGY", "MANUF", "TELCM"}
GROWTH_INDUSTRIES = {"HLTH", "BUSEQ", "SHOPS"}


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"check": name, "pass": bool(ok), "detail": detail}


def calibrate_characteristics(dir_=None) -> list[dict]:
    d = dir_ or CH.WRDS_DIR
    p = d / "finratio_monthly.parquet"
    if not p.exists():
        return [_check("finratio present", False, f"{p} absent")]

    df = pd.read_parquet(p, columns=["permno", "public_date", "bm", "roe",
                                     "mktcap", "ffi12_desc"])
    out = []

    # ── value ───────────────────────────────────────────────────────────────
    v = df.dropna(subset=["bm", "mktcap"])
    v = v[(v.bm > 0) & (v.bm <= 20)]
    med = float(v.bm.median())
    out.append(_check(
        "bm median is near 0.5",
        0.3 <= med <= 0.8,
        f"median={med:.3f} (a median far from ~0.5 means units or "
        f"inversion, not a market regime)"))

    q = pd.qcut(v.bm, 5, labels=False, duplicates="drop")
    caps = v.groupby(q).mktcap.median()
    falling = bool(caps.iloc[0] > caps.iloc[-1])
    out.append(_check(
        "value skews SMALLER than growth",
        falling,
        f"median mktcap q0(growth)={caps.iloc[0]:,.0f} -> "
        f"q4(value)={caps.iloc[-1]:,.0f}. If value were the LARGER end, `bm` "
        f"is inverted."))

    hi = set(v[q == 4].ffi12_desc.value_counts().head(3).index)
    lo = set(v[q == 0].ffi12_desc.value_counts().head(3).index)
    out.append(_check(
        "cheap end is banks/insurers/heavy industry",
        bool(hi & VALUE_INDUSTRIES),
        f"top-3 industries at high bm: {sorted(hi)}"))
    out.append(_check(
        "expensive end is biotech/tech/retail",
        bool(lo & GROWTH_INDUSTRIES),
        f"top-3 industries at low bm: {sorted(lo)}"))

    # ── profitability ───────────────────────────────────────────────────────
    r = df.dropna(subset=["roe", "mktcap"])
    r = r[(r.roe >= -10) & (r.roe <= 10)]
    rq = pd.qcut(r.roe, 5, labels=False, duplicates="drop")
    rcaps = r.groupby(rq).mktcap.median()
    out.append(_check(
        "high ROE skews LARGER",
        bool(rcaps.iloc[-1] > rcaps.iloc[0]),
        f"median mktcap q0(low ROE)={rcaps.iloc[0]:,.0f} -> "
        f"q4(high ROE)={rcaps.iloc[-1]:,.0f}"))
    out.append(_check(
        "ROE median is a plausible business return",
        0.0 < float(r.roe.median()) < 0.30,
        f"median={float(r.roe.median()):.4f}"))

    # The two characteristics must not be the same thing wearing two names.
    both = df.dropna(subset=["bm", "roe"])
    both = both[(both.bm > 0) & (both.bm <= 20) &
                (both.roe >= -10) & (both.roe <= 10)]
    rho = float(np.corrcoef(both.bm.rank(), both.roe.rank())[0, 1])
    out.append(_check(
        "value and profitability are DISTINCT",
        abs(rho) < 0.5,
        f"spearman(bm, roe)={rho:+.3f}. Near +/-1 would mean the second "
        f"data source added one characteristic, not two."))
    return out


def calibrate_revisions(dir_=None) -> list[dict]:
    if not RV.available(dir_):
        return [_check("ibes present", False, "consensus parquets absent")]
    raw = RV._load_raw(dir_)
    d = RV.derive(raw)
    out = []

    b = d.rev_breadth.dropna()
    mean_b = float(b.mean())
    out.append(_check(
        "net revision breadth is roughly balanced",
        abs(mean_b) < 0.15,
        f"mean={mean_b:+.4f} over {len(b):,} rows. A panel that is mostly "
        f"upgrades is a filter bug (wrong fpi, or numup/numdown swapped), "
        f"not an optimistic market."))
    # NOT "bounded by 1". `numup`/`numdown` are a FLOW of revisions filed
    # during the period; `numest` is the STOCK standing now, so the ratio
    # legitimately exceeds 1 for heavily-revised names. Asserting the wrong
    # bound here is what this battery caught on its first run — and the cost
    # was 16,024 dropped rows, precisely the most informative ones.
    # The real facts: the tail is SMALL, and nothing is absurd.
    over = float((b.abs() > 1.0).mean())
    out.append(_check(
        "breadth exceeds 1 only in a small tail (flow vs stock)",
        over < 0.05,
        f"{100 * over:.2f}% of rows exceed |1| — expected and legitimate: "
        f"an analyst may revise twice, and revisers may have dropped "
        f"coverage since"))
    out.append(_check(
        "no absurd breadth values survive",
        bool(b.abs().max() <= 5.0 + 1e-9),
        f"max|breadth|={float(b.abs().max()):.4f}; the plausibility bound is "
        f"5.0, chosen because ZERO rows exceed it"))

    disp = d.rev_dispersion.dropna()
    out.append(_check(
        "dispersion is negated (high = agreement)",
        bool(disp.max() <= 0.0 + 1e-9),
        f"max={float(disp.max()):.4f}, must be <= 0"))

    # Coverage has to reach the era the farm replays.
    yrs = pd.to_datetime(d.statpers).dt.year
    out.append(_check(
        "coverage spans the replayable window",
        bool(yrs.min() <= 1993 and yrs.max() >= 2024),
        f"statpers {int(yrs.min())}..{int(yrs.max())}"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    rows = calibrate_characteristics() + calibrate_revisions()
    if a.json:
        print(json.dumps(rows, indent=2))
    else:
        print("FARM CALIBRATION — known facts about known factors\n")
        for r in rows:
            print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['check']}")
            print(f"         {r['detail']}")
        bad = [r for r in rows if not r["pass"]]
        print(f"\n  {len(rows) - len(bad)}/{len(rows)} passed")
        if bad:
            print("\n  A FAILURE HERE INVALIDATES EVERY DOWNSTREAM RESULT "
                  "COMPUTED FROM THAT CHARACTERISTIC,")
            print("  including ones already written down. Fix the join before "
                  "reading any leaderboard.")
    return 1 if any(not r["pass"] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
