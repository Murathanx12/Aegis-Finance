"""BAND_PRIOR v2 -- the ENGINE's expected excess return, as a function.

WHY THIS FILE EXISTS SEPARATELY
==============================
The learner does not learn the market from scratch. It learns the ENGINE'S
RESIDUALS: the part of realised excess return that the band prior did not
already claim. That makes the prior a first-class object -- it is the offset in
the residual arm, a feature in the raw arm, and the incumbent baseline every
model has to beat -- so it lives in one file with one set of constants, read
from the committed receipt's numbers rather than retyped at three call sites.

THE UNIT, NAMED
===============
`ratio = mean_target / close`.  `upside = ratio - 1`.  They are NOT the same
number and a session lost time to that in S33b. Every function here takes
`ratio` and says so in its signature; `upside_to_ratio` is the only conversion.

THE NUMBERS
===========
`backend/data/optimus/tracker_backtest/exp_return_cross_section.json`,
`q2_books`, 143 months of IBES+CRSP 2013-2024, ANNUALISED EXCESS over the
equal-weighted market of the same months, costed:

    ratio < 1.5    +2.41%/yr   t 1.30   (285,173 name-months)
    1.5 <= r < 3   +5.74%/yr   t 1.85   ( 48,289)
    3 <= r < 5    +16.55%/yr   t 2.20   (  5,888)
    r >= 5        -37.77%/yr   t -7.75  ( 24,358)

HYGIENE IS NOT A BAND
=====================
`close >= $2` and `coverage >= 2` are admission to having an opinion at all,
not a band. Below $2 the band prior is UNINFORMATIVE (t 0.39, S30b), and the
house rule from that receipt is to say "no opinion", never "historically bad".
So a row failing hygiene gets prior 0.0 and `has_opinion=False` -- which is a
different statement from "the prior is zero because the band says so".

THESE ARE IN-SAMPLE NUMBERS, AND THE LEARNER IS SCORED AGAINST THEM ANYWAY
=========================================================================
The band constants were fitted on the whole 2013-2024 window. Used as an
out-of-sample baseline they are therefore FLATTERED -- the prior arm gets to
know the future that the ML arms are denied. That is deliberate: it makes
"engine+residual beats the engine" a HARD test rather than an easy one, and it
is stated in the receipt header so no reader mistakes the prior's OOS numbers
for honest OOS numbers. The alternative (refitting bands per split) is offered
by `band_constants_from_frame` for the sensitivity check.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

#: (lo, hi, label, annualised_excess). Half-open [lo, hi).
BAND_PRIOR_V2: tuple[tuple[float, float, str, float], ...] = (
    (-np.inf, 1.5, "lt_1_5", 0.0241),
    (1.5, 3.0, "b_1_5_3", 0.0574),
    (3.0, 5.0, "b_3_5", 0.1655),
    (5.0, np.inf, "toxic_ge_5", -0.3777),
)

#: Hygiene. Not a band -- admission to having an opinion.
MIN_PRICE = 2.0
MIN_COVERAGE = 2

#: The receipt's "admissible region": upside 0.5 .. 4.0, i.e. ratio 1.5 .. 5.0.
#: This is the exact region in which S33's six simple features were EMPTY
#: (all Fama-MacBeth |t| < 1.5 over 143 months), so it is the region in which
#: "does ML add anything the constants do not" is the honest question.
ADMISSIBLE_RATIO_LO = 1.5
ADMISSIBLE_RATIO_HI = 5.0

BAND_LABELS = tuple(b[2] for b in BAND_PRIOR_V2)
#: `no_opinion` is its own label so it can never be silently merged into a band.
ALL_BAND_LABELS = ("no_opinion",) + BAND_LABELS

#: sha-ish version tag; bump when any constant above changes.
PRIOR_VERSION = "band_prior_v2/2026-09-01"


def upside_to_ratio(upside):
    """`upside` is ratio - 1. This is the ONLY place the conversion happens."""
    return np.asarray(upside, dtype="float64") + 1.0


def band_label(ratio) -> pd.Series:
    """Band label per row from the ratio ALONE (hygiene applied separately)."""
    r = pd.Series(np.asarray(ratio, dtype="float64"))
    out = pd.Series(np.full(len(r), "no_opinion", dtype=object), index=r.index)
    for lo, hi, label, _ in BAND_PRIOR_V2:
        out[(r >= lo) & (r < hi)] = label
    out[r.isna()] = "no_opinion"
    return out


def has_opinion(close, coverage) -> pd.Series:
    """Hygiene gate: a real price and at least two people covering it."""
    c = pd.Series(np.asarray(close, dtype="float64"))
    n = pd.Series(np.asarray(coverage, dtype="float64"), index=c.index)
    return (c >= MIN_PRICE) & (n >= MIN_COVERAGE) & c.notna() & n.notna()


def annualised_prior(ratio, close, coverage) -> pd.Series:
    """ANNUALISED expected EXCESS return, per row. 0.0 where hygiene fails."""
    lab = band_label(ratio)
    ok = has_opinion(close, coverage)
    lookup = {b[2]: b[3] for b in BAND_PRIOR_V2}
    out = lab.map(lookup).astype("float64")
    out[~ok.values] = 0.0
    return out.fillna(0.0)


def horizon_prior(ratio, close, coverage, horizon_months: int) -> pd.Series:
    """Expected EXCESS return over `horizon_months`, compounded from the
    annualised band constant: (1 + a) ** (h / 12) - 1.

    Compounded rather than scaled linearly because -37.77%/yr scaled linearly
    to 12 months is -37.77% but to 1 month is -3.15%, whereas compounding gives
    -3.83% -- and the toxic band is exactly where the difference matters.
    """
    a = annualised_prior(ratio, close, coverage)
    return np.power(1.0 + a, horizon_months / 12.0) - 1.0


def effective_band(ratio, close, coverage) -> pd.Series:
    """Band label AFTER hygiene: hygiene failures become `no_opinion`."""
    lab = band_label(ratio)
    ok = has_opinion(close, coverage)
    lab = lab.copy()
    lab[~ok.values] = "no_opinion"
    return lab


def in_admissible_region(ratio, close, coverage) -> pd.Series:
    """The S33 region: ratio in [1.5, 5.0) AND hygiene passed."""
    r = pd.Series(np.asarray(ratio, dtype="float64"))
    ok = has_opinion(close, coverage)
    return (r >= ADMISSIBLE_RATIO_LO) & (r < ADMISSIBLE_RATIO_HI) & ok.values


def band_constants_from_frame(df: pd.DataFrame, ratio_col: str, close_col: str,
                              cov_col: str, excess_col: str,
                              month_col: str = "month") -> dict:
    """Refit the band constants on a frame -- the sensitivity check that
    answers "how much of the prior's OOS score is its in-sample fitting?".

    Returns annualised excess per band, computed the same way the receipt did:
    equal-weighted monthly mean excess within band, averaged across months,
    annualised by (1 + m) ** 12 - 1.
    """
    lab = effective_band(df[ratio_col], df[close_col], df[cov_col])
    out: dict[str, float] = {}
    for label in ALL_BAND_LABELS:
        sel = df[lab.values == label]
        if sel.empty:
            out[label] = float("nan")
            continue
        m = sel.groupby(month_col)[excess_col].mean().mean()
        out[label] = float((1.0 + m) ** 12 - 1.0) if pd.notna(m) else float("nan")
    return out


def describe() -> dict:
    """The prior, as a receipt block."""
    return {
        "version": PRIOR_VERSION,
        "source_receipt": "backend/data/optimus/tracker_backtest/exp_return_cross_section.json",
        "unit_note": "ratio = mean_target / close; upside = ratio - 1. Bands are on RATIO.",
        "value_note": "annualised EXCESS over the equal-weighted market, 143 months 2013-2024",
        "hygiene": {"min_price": MIN_PRICE, "min_coverage": MIN_COVERAGE,
                    "on_failure": "prior 0.0 and has_opinion=False -- NO OPINION, not a bearish call"},
        "bands": [{"lo": (None if np.isinf(lo) else lo),
                   "hi": (None if np.isinf(hi) else hi),
                   "label": lab, "annualised_excess": v}
                  for lo, hi, lab, v in BAND_PRIOR_V2],
        "in_sample_warning": (
            "The band constants were fitted on 2013-2024 in full. As an OOS baseline the "
            "prior is FLATTERED -- it knows the test years. Beating it is therefore a hard "
            "test, not an easy one."),
    }


__all__: Iterable[str] = [
    "BAND_PRIOR_V2", "MIN_PRICE", "MIN_COVERAGE", "PRIOR_VERSION",
    "ALL_BAND_LABELS", "ADMISSIBLE_RATIO_LO", "ADMISSIBLE_RATIO_HI",
    "upside_to_ratio", "band_label", "has_opinion", "annualised_prior",
    "horizon_prior", "effective_band", "in_admissible_region",
    "band_constants_from_frame", "describe",
]
