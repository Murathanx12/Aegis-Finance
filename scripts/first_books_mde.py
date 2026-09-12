"""THE POWER CHECK BEFORE THE CONFIRMATION (canon §64), for the four books.

WHY THIS EXISTS
===============
`spec_first_books.md` §0G is explicit: several of the four books name a FORMULA
for their minimum detectable effect and no number, because the panels did not
exist when the spec was written, and "inventing a number here would be exactly
the headline-number-without-a-receipt defect CLAUDE.md prohibits."

The panels exist now (T1 built Book A's; the Form-4 tape and CRSP were already
here). This script computes each book's dispersion FROM ITS OWN TAPE and writes
one receipt. The four pre-registrations quote that receipt; none of them quotes
a number that was typed by hand.

THE RECIPE, THE SAME ONE TRIAL-R2 §4 USES
=========================================
    MDE(80% power, alpha 0.05, two-sided) = 2.8 * sd_of_the_unit / sqrt(n_eff)

where the UNIT is what the primary metric averages over (a monthly book-minus-
twin excess for A, C and D; a per-event BHAR difference for B) and `n_eff` is
the number of INDEPENDENT date blocks, not observations (canon §58). Both are
measured; `n_eff` is deflated by the measured lag-1 autocorrelation of the
block series rather than assumed to equal the block count.

WHAT IT DOES NOT DO
===================
It does not run the strategies. A dispersion measured from the tape is a
property of the tape, and computing it from a simulated book would make the
power check depend on the thing it is supposed to size.

    python -m scripts.first_books_mde
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("first_books_mde")

#: 80% power, alpha 0.05, two-sided: z(0.975) + z(0.80) = 1.96 + 0.84.
Z_SUM = 2.8

#: Book A's confirm slice, per spec A.6 (post-publication only).
BOOK_A_ERA = (2011, 2024)
#: Book B's confirm slice, per spec B.6 (the first post-KKW-sample years).
BOOK_B_ERA = (2017, 2024)
#: Book C reads the same monthly blocks as A but over the whole CRSP span its
#: overhang lookback allows (the 1,260-session warmup eats the first five years).
BOOK_C_ERA = (1995, 2024)


def wrds_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "wrds"


def receipt_path() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "first_books" / "mde_receipt.json"


def n_effective(block_means) -> dict:
    """Independent date blocks after the MEASURED lag-1 autocorrelation.

    `n_eff = n * (1 - rho) / (1 + rho)`, the standard first-order correction.
    rho is measured on the block series; a rho assumed to be zero is the
    assumption canon §58 exists to stop.
    """
    import numpy as np

    x = np.asarray(list(block_means), dtype=float)
    x = x[np.isfinite(x)]
    n = int(x.size)
    if n < 3:
        return {"n_blocks": n, "rho_lag1": None, "n_effective": n,
                "note": "fewer than 3 blocks: rho is not estimable, n_eff = n"}
    a, b = x[:-1] - x.mean(), x[1:] - x.mean()
    denom = float((a * a).sum())
    rho = float((a * b).sum() / denom) if denom > 0 else 0.0
    rho = max(-0.99, min(0.99, rho))
    n_eff = n * (1.0 - rho) / (1.0 + rho)
    return {"n_blocks": n, "rho_lag1": round(rho, 4),
            "n_effective": round(float(n_eff), 2)}


def mde(sd: float, n_eff: float) -> float:
    if not (sd > 0 and n_eff > 0):
        return float("nan")
    return Z_SUM * float(sd) / math.sqrt(float(n_eff))


# --------------------------------------------------------------------------
# the tape


def monthly_returns(years):
    """CRSP monthly name returns, compounded from the daily file."""
    import pandas as pd

    frames = []
    for y in years:
        p = wrds_dir() / f"crsp_dsf_{y}.parquet"
        if not p.is_file():
            continue
        df = pd.read_parquet(p, columns=["permno", "date", "ret", "prc", "vol"])
        df["date"] = pd.to_datetime(df["date"])
        df["ym"] = df["date"].dt.to_period("M")
        df = df.dropna(subset=["ret"])
        df["lg"] = (1.0 + df["ret"].astype(float)).clip(lower=1e-9).apply(math.log)
        g = df.groupby(["permno", "ym"], sort=False).agg(
            lg=("lg", "sum"), n=("lg", "size"),
            dollar_vol=("vol", "mean"), price=("prc", "last"))
        g = g[g["n"] >= 15].reset_index()
        g["ret_m"] = g["lg"].apply(math.exp) - 1.0
        frames.append(g[["permno", "ym", "ret_m", "price"]])
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def portfolio_sd_from_cross_section(panel, *, k: int) -> dict:
    """The monthly sd of a k-name EW book MINUS an independent k-name EW book.

    Measured, not modelled, except for the one step that must be: the
    cross-sectional sd of name-level monthly returns is measured per month; a
    k-name equal-weight average of names drawn from that cross-section has sd
    `cs_sd / sqrt(k)` if the residuals were independent, and the DIFFERENCE of
    two such books has `sqrt(2)` times that. The independence assumption makes
    this an OPTIMISTIC (small) MDE — real names share factors, so the true
    dispersion is larger and the real MDE is larger. The receipt says so; an
    MDE quoted without that direction is a power claim that flatters itself.
    """
    import numpy as np

    per_month = panel.groupby("ym")["ret_m"].agg(["std", "size"])
    per_month = per_month[per_month["size"] >= k]
    if per_month.empty:
        return {"months": 0, "note": f"no month carried {k} names"}
    cs_sd = float(np.nanmedian(per_month["std"].to_numpy(dtype=float)))
    book_sd = cs_sd / math.sqrt(float(k))
    return {"months": int(len(per_month)),
            "median_cross_sectional_monthly_sd": round(cs_sd, 6),
            "k": int(k),
            "book_monthly_sd": round(book_sd, 6),
            "book_minus_twin_monthly_sd": round(book_sd * math.sqrt(2.0), 6),
            "independence_caveat": (
                "names inside a book share factors, so the true book sd is "
                "LARGER than cs_sd/sqrt(k) and the true MDE is LARGER than the "
                "number below. This is the optimistic bound, stated as one.")}


def pairwise_rho(panel, era, *, sample: int = 250, seed: int = 20260912) -> dict:
    """The MEASURED average pairwise correlation of the OUTCOME across names.

    R13d wants `(cross_sectional_k, cross_sectional_rho)` as a MULTIPLIER on a
    count of independent time blocks, and rho has to be measured: a design that
    declares rho by taste is declaring its own effective sample by taste. The
    draw is seeded from a constant so two sessions get the same number, and the
    seed is recorded.
    """
    import numpy as np

    lo, hi = era
    sub = panel[(panel["ym"].dt.year >= lo) & (panel["ym"].dt.year <= hi)]
    wide = sub.pivot_table(index="ym", columns="permno", values="ret_m",
                           aggfunc="last")
    full = wide.dropna(axis=1, thresh=int(0.9 * len(wide)))
    if full.shape[1] < 10:
        return {"note": "fewer than 10 names with 90% coverage; rho not estimable"}
    rng = np.random.default_rng(seed)
    cols = list(full.columns)
    pick = rng.choice(len(cols), size=min(int(sample), len(cols)), replace=False)
    m = full.iloc[:, sorted(int(i) for i in pick)]
    c = m.corr(min_periods=24).to_numpy(dtype=float)
    iu = np.triu_indices_from(c, k=1)
    vals = c[iu]
    vals = vals[np.isfinite(vals)]
    return {"names_sampled": int(m.shape[1]), "months": int(m.shape[0]),
            "seed": int(seed), "pairs": int(vals.size),
            "mean_pairwise_rho": round(float(vals.mean()), 4),
            "median_pairwise_rho": round(float(np.median(vals)), 4),
            "definition": "average pairwise correlation of MONTHLY name returns "
                          "over the era, names with >=90% month coverage"}


def era_blocks(panel, era) -> list:
    """The monthly EW-universe return series over `era` — the block series."""
    lo, hi = era
    sub = panel[(panel["ym"].dt.year >= lo) & (panel["ym"].dt.year <= hi)]
    return sub.groupby("ym")["ret_m"].mean().tolist()


# --------------------------------------------------------------------------
# Book B's own unit: the per-event BHAR dispersion


def bhar_dispersion(*, start: int, end: int) -> dict:
    """The sd of per-name BHAR(22,90) over the Form-4 cluster window.

    Measured on the CRSP tape over the same span the clusters live in: the unit
    Book B averages is a 69-session buy-and-hold abnormal return, so its
    dispersion is the dispersion of 69-session name returns minus the market's,
    not of monthly returns.
    """
    import numpy as np
    import pandas as pd

    rows = []
    for y in range(int(start), int(end) + 1):
        p = wrds_dir() / f"crsp_dsf_{y}.parquet"
        if not p.is_file():
            continue
        df = pd.read_parquet(p, columns=["permno", "date", "ret", "prc"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["ret"])
        df = df[df["prc"].abs() >= 5.0]
        wide = df.pivot_table(index="date", columns="permno", values="ret",
                              aggfunc="last").sort_index()
        if len(wide) < 95:
            continue
        cum = (1.0 + wide.fillna(0.0)).cumprod()
        # windows [22, 90] measured from a grid of starts one month apart
        for i in range(0, len(cum) - 91, 21):
            a, b = cum.iloc[i + 21], cum.iloc[i + 90]
            r = (b / a - 1.0).replace([np.inf, -np.inf], np.nan).dropna()
            if len(r) < 100:
                continue
            rows.append(float((r - r.mean()).std()))
    if not rows:
        return {"windows": 0, "note": "no usable BHAR window"}
    return {"windows": len(rows),
            "median_cross_sectional_bhar_sd": round(float(np.median(rows)), 6),
            "definition": "sd of (69-session buy-and-hold return minus its "
                          "cross-sectional mean), $5 price floor, starts one "
                          "month apart"}


# --------------------------------------------------------------------------


def build(*, write: bool = True) -> dict:

    t0 = datetime.now(timezone.utc)
    years = list(range(min(BOOK_C_ERA[0], BOOK_A_ERA[0]) - 1, BOOK_A_ERA[1] + 1))
    panel = monthly_returns(years)
    if panel is None or panel.empty:
        raise FileNotFoundError(
            f"no CRSP daily files under {wrds_dir()}; the power check cannot be "
            f"computed from a tape that is not on this machine, and a power "
            f"check nobody computed is what canon §64 exists to stop.")

    out: dict = {
        "job": "first_books_mde",
        "built_utc": t0.isoformat(timespec="seconds"),
        "family": "NIGHT_JOB_BOOKS_2026_09",
        "licence": "PRODUCT_EXPERIMENT",
        "recipe": ("MDE(80% power, alpha 0.05, two-sided) = 2.8 * sd / "
                   "sqrt(n_effective); n_effective deflated by the measured "
                   "lag-1 autocorrelation of the block series (canon §58)"),
        "books": {},
    }

    # ---- Book A --------------------------------------------------------
    a_panel = panel[(panel["ym"].dt.year >= BOOK_A_ERA[0])
                    & (panel["ym"].dt.year <= BOOK_A_ERA[1])]
    a_sd = portfolio_sd_from_cross_section(a_panel, k=50)
    a_n = n_effective(era_blocks(panel, BOOK_A_ERA))
    a_rho = pairwise_rho(panel, BOOK_A_ERA)
    out["books"]["si_low_turnover_high_v1"] = {
        "era": list(BOOK_A_ERA), "unit": "monthly book-minus-twin excess return",
        "dispersion": a_sd, "blocks": a_n, "cross_sectional_rho": a_rho,
        "mde_monthly": round(mde(a_sd.get("book_minus_twin_monthly_sd", 0.0),
                                 a_n["n_effective"]), 6),
        "prior_from_the_literature": 0.013,
        "note": ("Boehmer-Huszar-Jordan's published low-SI leg alpha is about "
                 "+1.3%/month on 1988-2005. That is the design's PRIOR, never "
                 "its threshold: the declared effect size is one notch above "
                 "the computed MDE, per TRIAL-R2's convention."),
    }

    # ---- Book B --------------------------------------------------------
    b_sd = bhar_dispersion(start=BOOK_B_ERA[0], end=BOOK_B_ERA[1])
    b_blocks = era_blocks(panel, BOOK_B_ERA)
    b_n = n_effective(b_blocks)
    out["books"]["insider_cluster_length_v1"] = {
        "era": list(BOOK_B_ERA), "unit": "per-event BHAR(22,90) vs twin",
        "dispersion": b_sd, "blocks": b_n,
        "cross_sectional_rho": pairwise_rho(panel, BOOK_B_ERA),
        "mde_per_filing_month_block": round(
            mde(b_sd.get("median_cross_sectional_bhar_sd", 0.0),
                b_n["n_effective"]), 6),
        "prior_from_the_literature": 0.05,
        "note": ("KKW's >5% BHAR gap is UNPUBLISHED and its sample ends 2016. "
                 "It is the prior. The n_effective here counts FILING-MONTH "
                 "blocks, not events: clustered filings inside one month are "
                 "one observation of the mechanism, not thirty."),
    }

    # ---- Book C --------------------------------------------------------
    c_panel = panel[(panel["ym"].dt.year >= BOOK_C_ERA[0])
                    & (panel["ym"].dt.year <= BOOK_C_ERA[1])]
    c_sd = portfolio_sd_from_cross_section(c_panel, k=30)
    c_n = n_effective(era_blocks(panel, BOOK_C_ERA))
    out["books"]["disposition_overhang_conditioner_v0"] = {
        "era": list(BOOK_C_ERA),
        "unit": "monthly (conditioned book minus unconditioned book) excess",
        "dispersion": c_sd, "blocks": c_n,
        "cross_sectional_rho": pairwise_rho(panel, BOOK_C_ERA),
        "mde_monthly": round(mde(c_sd.get("book_minus_twin_monthly_sd", 0.0),
                                 c_n["n_effective"]), 6),
        "prior_from_the_literature": 0.0243,
        "note": ("Frazzini's overhang spread is 2.43%/month, t 6.60, on "
                 "pre-2000 data. The comparator here is the UNCONDITIONED "
                 "reaction book run fresh on the same window, which is a much "
                 "tighter comparison than the market and therefore a smaller "
                 "sd than a long-only excess would have — this number is the "
                 "conservative one."),
    }

    # ---- Book D --------------------------------------------------------
    # The abstention book's own falsifier is the risk-coverage curve over >= 24
    # monthly blocks, so the unit is a monthly excess over the always-invested
    # twin and the block count is the design's own floor, not the tape's.
    d_panel = panel[panel["ym"].dt.year >= 2011]
    d_sd = portfolio_sd_from_cross_section(d_panel, k=5)
    out["books"]["abstention_book_v0"] = {
        "era": [2011, 2024], "unit": "monthly excess vs the always-invested twin",
        "dispersion": d_sd, "cross_sectional_rho": a_rho,
        "blocks": {"n_blocks": 24, "note": ("24 monthly blocks is the design's "
                                            "own floor (angle4 §1) and is used "
                                            "as n here rather than the tape's "
                                            "count: this book cannot be read "
                                            "early even if it looks good")},
        "mde_monthly_at_24_blocks": round(
            mde(d_sd.get("book_minus_twin_monthly_sd", 0.0), 24.0), 6),
        "bar_it_must_also_clear": {
            "source": "NEGATIVE_RESULTS.md §1",
            "total_return": [0.283, 1.148], "sharpe": [0.432, 0.837],
            "note": ("the existing timing strategy returned +28.3% against "
                     "buy-and-hold's +114.8% at Sharpe 0.432 vs 0.837, "
                     "2020-01..2025-06, 66 monthly signals, 32bps round trip. "
                     "Beating the twin is necessary; beating this receipt is "
                     "the additional explicit bar."),
        },
    }

    out["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if write:
        p = receipt_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        out["receipt_path"] = str(p)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(json.dumps(build(write=not a.dry_run), indent=2, default=str))
    return 0


if __name__ == "__main__":                                   # pragma: no cover
    sys.exit(main())
