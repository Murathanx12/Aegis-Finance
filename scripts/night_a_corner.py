"""A's CORNER — Book A's double sort re-measured at the $10M floor.

WHY THIS JOB EXISTS
===================
`B_first_books_replay` run 1 (2026-09-12) read the low-SI x high-turnover
double sort at **-0.5407%/month** over 417 monthly blocks against its
turnover-matched random twin, NW lag-2 t -2.2603. The book LOSES to a random
draw from its own liquidity band, and it loses at the $3M primary floor.

TRIAL-DRAFT-A §5 makes the $10M cell part of the rule rather than a curiosity:

    `PRODUCT_PROMISING` -- ... AND the same test at the $10M floor also clears.
    `FAILED_VARIANT`    -- 2011-2024 net block-mean <= 0, OR the $10M-floor
                           cell fails while the $3M-floor cell passes
                           (tradability killed it, TRIAL-H5's own lesson).

and §8 forbids quoting one floor without the other: "No quoting the $3M-floor
number as the result if the $10M-floor cell disagrees; both are printed or
neither is." So this job runs BOTH cells in one pass and prints both.

THE TWIN IS RE-DRAWN AT THE FLOOR, WHICH IS THE WHOLE POINT
===========================================================
TRIAL-H5's lesson is that a corner-dependent control must be RE-MEASURED at
every corner. `run_monthly(..., floor_usd=...)` moves the eligible band for the
book and for its turnover-matched twin together, so the $10M comparison is a
$10M book against a $10M control and not against a control drawn from a band
the book can no longer trade. A twin left at $3M would be a different null
wearing the same name.

The twin's per-month seed is Book A's own (`BOOK_A_SEED`, 0x1934) and is
carried on every cell, so the draw is reconstructible. The draw is NOT the same
names at both floors and must not be: the pool it is drawn from is different,
which is the corner moving.

THE CONTAMINATION CLAUSE RUNS BEFORE THE NUMBER
===============================================
§5: "If the panel's per-year join rate for any year in the confirm slice falls
below 0.50 (it is 0.62-0.82 today), that year is excluded and the exclusion is
reported before the number is." The join rate is measured here, per year, on
the cell's OWN eligible universe -- it is a different number at $10M than at
$3M, because the panel covers larger names better -- and an excluded year is
dropped from the book AND the twin by the selector, never from one of them.

    python -m scripts.night_factory_jobs A_corner --smoke
    python -m scripts.night_factory_jobs A_corner

TIME BOX, PROJECTED FROM A MEASURED RUN
=======================================
Run 1 of the whole replay was 829.3 s for four books, one of which was this
book at one floor, and the memory peak was Book B's wide daily frame which this
job never builds. Two monthly passes plus the join-rate pre-pass: projection
**8-15 minutes**, inside the 60-minute default box.
"""

from __future__ import annotations

import logging

from scripts.night_first_books_replay import (
    BOOK_A_K,
    BOOK_A_MIN_NAMES,
    BOOK_A_SEED,
    COST_BPS_PER_SIDE,
    COST_CURVE,
    FAMILY,
    FLOOR_USD,
    FULL_END,
    FULL_START,
    SMOKE_NAMES,
    BookAPanelUnavailable,
    book_a_panel,
    book_a_selector,
    by_era,
    eligible,
    load_monthly_panel,
    newey_west_t,
    run_monthly,
    two_sided_p,
)

logger = logging.getLogger("a_corner")

JOB = "A_corner"
BOOK = "si_low_turnover_high_v1"
BOOK_ID = "book:1934ec97aa4b1620"
PREREG = "TRIAL-DRAFT-A-si-low-turnover-high-v1 (UNSIGNED)"

#: The two floors TRIAL-DRAFT-A §6 freezes: "$3M primary and $10M secondary".
PRIMARY_FLOOR = FLOOR_USD
SECONDARY_FLOOR = 10_000_000.0

#: §2 and §4: 2011-2024 is the SOLE confirm slice and 1990-2010 is reported.
CONFIRM_SLICE = (2011, 2024)

#: §4's computed MDE and §4's declared effect. Both are quoted, because a
#: block-mean between them is a CONDITIONAL by §5 and not a pass.
DECLARED_MDE_MONTHLY = 0.00685
DECLARED_EFFECT_SIZE = 0.01

#: §5's contamination clause.
MIN_JOIN_RATE = 0.50

#: §5's thresholds, written once.
T_PASS = 2.0
T_CONDITIONAL_FLOOR = 1.0

SMOKE_START, SMOKE_END = 2011, 2024


def slice_stats(result: dict, lo: int, hi: int) -> dict:
    """The block series restricted to a year range, with its own NW t.

    The confirm slice is not an era: `by_era` reports four fixed windows and
    decides nothing, while THIS is the one window TRIAL-DRAFT-A §2 says decides.
    Computing it from the same block series means the two can never disagree
    about which months they covered.
    """
    import numpy as np
    import pandas as pd

    blocks, excess = result.get("blocks") or [], result.get("excess") or []
    vals = [e for b, e in zip(blocks, excess)
            if lo <= pd.Period(b, freq="M").year <= hi]
    if len(vals) < 3:
        return {"slice": f"{lo}-{hi}", "n_blocks": len(vals),
                "verdict": "too few blocks to report a mean"}
    t = newey_west_t(vals)
    return {"slice": f"{lo}-{hi}", "n_blocks": len(vals),
            "mean_excess_net_monthly": round(float(np.mean(vals)), 6),
            "nw_lag2_t": (round(t, 4) if t is not None else None),
            "p_two_sided": (round(two_sided_p(t), 6) if t is not None else None)}


def join_rate_by_year(panel, si, *, floor_usd: float) -> dict:
    """Share of the eligible universe carrying a PUBLISHED short-interest print.

    Measured on the cell's own universe, because the answer is different at
    $10M than at $3M -- the panel covers larger names better, so the corner
    that makes a book less tradable makes its data cleaner, and both effects
    belong on the receipt.
    """
    import numpy as np
    import pandas as pd

    seen = pd.to_datetime(si["observed_at"])
    per_year: dict = {}
    for ym, g in panel.groupby("ym", sort=True):
        pool = eligible(g, floor_usd=floor_usd)
        if pool.empty:
            continue
        asof = ym.to_timestamp(how="end")
        have = set(si.loc[seen <= asof, "permno"].astype("int64"))
        rate = len(set(int(p) for p in pool["permno"]) & have) / len(pool)
        per_year.setdefault(int(ym.year), []).append(float(rate))
    return {y: round(float(np.mean(v)), 4) for y, v in sorted(per_year.items())}


def excluded_years(rates: dict, *, lo: int, hi: int,
                   min_rate: float = MIN_JOIN_RATE) -> list:
    """Confirm-slice years the contamination clause excludes, in order."""
    return [y for y, r in sorted(rates.items())
            if lo <= y <= hi and r < float(min_rate)]


def run_cell(panel, si, *, floor_usd: float, skip_years, label: str) -> dict:
    """One floor's cell: the book, the twin re-drawn at that floor, both nets."""
    res = run_monthly(panel, book_a_selector(si, skip_years=skip_years),
                      k=BOOK_A_K, seed=BOOK_A_SEED, label=label,
                      floor_usd=floor_usd)
    return {
        "label": label,
        "floor_usd": float(floor_usd),
        "result": {k: v for k, v in res.items() if k not in ("blocks", "excess")},
        "confirm_slice": slice_stats(res, *CONFIRM_SLICE),
        "reported_slice_1990_2010": slice_stats(res, 1990, 2010),
        "by_era": by_era(res),
        "_series": res,
    }


def cell_passes(cell: dict) -> bool | None:
    """§5's `PRODUCT_PROMISING` arithmetic for ONE cell, on the confirm slice."""
    s = cell.get("confirm_slice") or {}
    mean, t = s.get("mean_excess_net_monthly"), s.get("nw_lag2_t")
    if mean is None or t is None:
        return None
    return bool(mean >= DECLARED_EFFECT_SIZE and t >= T_PASS)


def decide(primary: dict, secondary: dict) -> dict:
    """TRIAL-DRAFT-A §5, applied to the two cells. Both floors or neither."""
    p_pass, s_pass = cell_passes(primary), cell_passes(secondary)
    p = (primary.get("confirm_slice") or {})
    s = (secondary.get("confirm_slice") or {})
    p_mean, s_mean = p.get("mean_excess_net_monthly"), s.get("mean_excess_net_monthly")
    if p_mean is None or s_mean is None:
        return {"verdict": "CANNOT_DETERMINE",
                "why": ("one of the two cells produced no usable confirm-slice "
                        "block series, and §8 forbids quoting one floor "
                        "without the other: both are printed or neither is.")}
    if p_mean <= 0:
        return {"verdict": "FAILED_VARIANT",
                "clause": ("§5 FAILED_VARIANT clause 1: the 2011-2024 net "
                           "block-mean at the PRIMARY floor is <= 0"),
                "why": (f"{p_mean:+.6f}/month at the $3M floor over "
                        f"{p['n_blocks']} confirm-slice blocks (NW lag-2 t "
                        f"{p.get('nw_lag2_t')}); the $10M cell reads "
                        f"{s_mean:+.6f}/month (t {s.get('nw_lag2_t')}). The "
                        f"corner did not kill this book -- it was already "
                        f"below zero at the floor it was registered on, and "
                        f"the $10M cell is reported because §8 says both "
                        f"floors are printed or neither is.")}
    if p_pass and not s_pass:
        return {"verdict": "FAILED_VARIANT",
                "clause": ("§5 FAILED_VARIANT clause 2: the $10M-floor cell "
                           "fails while the $3M-floor cell passes -- "
                           "tradability killed it, TRIAL-H5's own lesson"),
                "why": (f"$3M {p_mean:+.6f}/month t {p.get('nw_lag2_t')}; "
                        f"$10M {s_mean:+.6f}/month t {s.get('nw_lag2_t')}")}
    if p_pass and s_pass:
        return {"verdict": "PRODUCT_PROMISING",
                "clause": "§5 PRODUCT_PROMISING: both floors clear",
                "why": (f"$3M {p_mean:+.6f}/month t {p.get('nw_lag2_t')}; "
                        f"$10M {s_mean:+.6f}/month t {s.get('nw_lag2_t')}; "
                        f"both >= the declared {DECLARED_EFFECT_SIZE:.4f} at "
                        f"t >= {T_PASS}")}
    return {"verdict": "CONDITIONAL",
            "clause": ("§5 CONDITIONAL: passes one floor and not the other, or "
                       "NW t in [1.0, 2.0), or the block-mean lands between 0 "
                       "and the MDE"),
            "why": (f"$3M {p_mean:+.6f}/month t {p.get('nw_lag2_t')}; "
                    f"$10M {s_mean:+.6f}/month t {s.get('nw_lag2_t')}; the MDE "
                    f"is {DECLARED_MDE_MONTHLY:.5f}/month and the declared "
                    f"effect {DECLARED_EFFECT_SIZE:.4f}/month")}


def A_corner(*, smoke: bool = False) -> dict:                     # noqa: N802
    """The night-factory entry point. Both floors, one receipt."""
    start = SMOKE_START if smoke else FULL_START
    end = SMOKE_END if smoke else FULL_END
    base = {
        "job": JOB, "family": FAMILY, "licence": "PRODUCT_EXPERIMENT",
        "book": BOOK, "book_id": BOOK_ID, "prereg": PREREG,
        "window": [start, end], "smoke": bool(smoke),
        "primary_metric": "net_monthly_excess_vs_random_twin",
        "confirm_slice": f"{CONFIRM_SLICE[0]}-{CONFIRM_SLICE[1]}",
        "floors_usd": {"primary": PRIMARY_FLOOR, "secondary": SECONDARY_FLOOR},
        "k": BOOK_A_K, "seed": BOOK_A_SEED, "min_names": BOOK_A_MIN_NAMES,
        "cost_curve": COST_CURVE, "cost_bps_per_side": COST_BPS_PER_SIDE,
        "declared_mde_monthly": DECLARED_MDE_MONTHLY,
        "declared_effect_size": DECLARED_EFFECT_SIZE,
        "question": ("Does the low-SI x high-turnover double sort behave the "
                     "same at the $10M floor as at the $3M floor, against a "
                     "twin RE-DRAWN at each floor?"),
        "caveats": [
            "COST: the flat 25 bps ruler is interim (chunk 5c's TAQ curve is "
            "pending). Book and twin both pay it and only DIFFERENCES are read.",
            "TURNOVER IS NOT VENUE-ADJUSTED (§8): Nasdaq double-counting "
            "(Anderson-Dyl 2005) is UNRESOLVED and every panel row carries "
            "`turnover_unadjusted_for_venue = True`. A cross-venue turnover "
            "sort is exactly what that bites, and raising the floor changes "
            "the venue mix of the universe, so the two cells do not share it.",
            "§8: neither floor may be quoted without the other.",
        ],
        "next_test": ("nothing further on THIS construction. §8 forbids "
                      "re-bucketing after the read, so a short-interest LEVEL "
                      "book that works would have to be a new registration "
                      "with its own corpse check -- and per EXPLORE DIRTY, "
                      "PROMOTE CLEAN, a failed implementation closes that "
                      "implementation and not the instrument."),
    }
    panel = load_monthly_panel(start, end,
                               max_names=SMOKE_NAMES if smoke else None)
    base["months_in_panel"] = int(panel["ym"].nunique())
    base["permnos_in_panel"] = int(panel["permno"].nunique())
    try:
        si = book_a_panel(panel)
    except BookAPanelUnavailable as exc:
        return {**base, "ran": False, "refused": str(exc),
                "headline": "A's corner cannot run without the short-interest panel",
                "verdict": "REFUSED: " + str(exc)}

    # THE CONTAMINATION CLAUSE, BEFORE THE NUMBER
    rates = {"primary": join_rate_by_year(panel, si, floor_usd=PRIMARY_FLOOR),
             "secondary": join_rate_by_year(panel, si, floor_usd=SECONDARY_FLOOR)}
    skip = {k: excluded_years(v, lo=CONFIRM_SLICE[0], hi=CONFIRM_SLICE[1])
            for k, v in rates.items()}
    base["contamination_clause"] = {
        "rule": ("TRIAL-DRAFT-A §5: a confirm-slice year whose panel join rate "
                 "falls below 0.50 is EXCLUDED and the exclusion is reported "
                 "BEFORE the number is."),
        "min_join_rate": MIN_JOIN_RATE,
        "join_rate_by_year": rates,
        "excluded_years": skip,
        "fired": bool(skip["primary"] or skip["secondary"]),
        "how_exclusion_works": ("the selector returns nothing for an excluded "
                               "month, so the book and its twin lose the same "
                               "months. Dropping one leg's months would be a "
                               "different comparison."),
    }

    primary = run_cell(panel, si, floor_usd=PRIMARY_FLOOR,
                       skip_years=set(skip["primary"]),
                       label="si_low_turnover_high_v1_floor3m")
    secondary = run_cell(panel, si, floor_usd=SECONDARY_FLOOR,
                         skip_years=set(skip["secondary"]),
                         label="si_low_turnover_high_v1_floor10m")
    base["universe_shrinkage"] = {
        "median_eligible_names_3m": _median_pool(panel, PRIMARY_FLOOR),
        "median_eligible_names_10m": _median_pool(panel, SECONDARY_FLOOR),
        "why": ("the corner is only a corner if it moves the universe. A "
                "$10M cell over the same names as the $3M cell would be the "
                "same test run twice."),
    }
    verdict = decide(primary, secondary)
    for cell in (primary, secondary):
        cell.pop("_series", None)
    p = primary["confirm_slice"]
    s = secondary["confirm_slice"]
    return {
        **base, "ran": True,
        "cell_primary_3m": primary,
        "cell_secondary_10m": secondary,
        "decision_rule": ("TRIAL-DRAFT-A §5, on the 2011-2024 confirm slice. "
                          "FAILED_VARIANT if the block-mean is <= 0, or if the "
                          "$10M cell fails while the $3M cell passes."),
        "headline": (
            f"$3M {p.get('mean_excess_net_monthly')}/month t "
            f"{p.get('nw_lag2_t')} over {p.get('n_blocks')} confirm blocks; "
            f"$10M {s.get('mean_excess_net_monthly')}/month t "
            f"{s.get('nw_lag2_t')} over {s.get('n_blocks')}; "
            f"{verdict['verdict']}"),
        "verdict": verdict["verdict"] + " — " + verdict["why"],
        "verdict_block": verdict,
    }


def _median_pool(panel, floor_usd: float) -> int:
    import numpy as np

    sizes = [len(eligible(g, floor_usd=floor_usd))
             for _, g in panel.groupby("ym", sort=False)]
    return int(np.median(sizes)) if sizes else 0


__all__ = ["A_corner", "cell_passes", "decide", "excluded_years",
           "join_rate_by_year", "run_cell", "slice_stats"]


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    print(json.dumps(A_corner(smoke=a.smoke), indent=1, default=str))
