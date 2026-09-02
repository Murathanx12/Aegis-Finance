"""The rulers. Nothing here learns anything; that is the point.

A neural network with no baseline is a number with no units. Every arm in
`learner/models.py` is scored against these four, in the same walk-forward
loop, on the same rows, at the same horizon:

* `constant`   -- the train-set base rate. Predicts the same excess return for
                  every name. Rank IC is exactly 0 by construction, so it is
                  the ruler for CALIBRATION and for terminal wealth (it buys
                  an arbitrary 50 names), never for ranking.
* `prior`      -- BAND_PRIOR v2 alone: four constants and a hygiene gate. This
                  is the INCUMBENT. It is what is running. A learner that does
                  not beat this has not earned a seat.
* `rank_upside`   -- sort by target/close. S33's receipt found the top target
                  quintile at **-7.51%/yr, t -2.09**, so this ruler is expected
                  to be NEGATIVE and is included precisely because a model that
                  merely rediscovers "high target = good" should score like it.
* `rank_consensus` -- sort by the 5=strong-buy analyst rating. The receipt has
                  it at +0.62%/yr, t 0.37: the street's own ordering, which is
                  approximately nothing.

The two `rank_*` rulers emit a CROSS-SECTIONAL PERCENTILE, not a return. They
can be ranked and they can build a book; they cannot be calibrated, and
`is_calibrated=False` says so rather than letting a decile table quietly
compare a percentile against a percentage.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Baseline:
    name: str
    #: False for rank-only rulers whose output is a percentile, not a return.
    is_calibrated: bool
    description: str


BASELINES: tuple[Baseline, ...] = (
    Baseline("constant", True, "train-set mean excess return, same for every name"),
    Baseline("prior", True, "BAND_PRIOR v2 alone -- the incumbent engine"),
    Baseline("rank_upside", False, "sort by ratio = target/close (expected NEGATIVE)"),
    Baseline("rank_consensus", False, "sort by the 5=strong-buy analyst rating"),
)

BASELINE_NAMES = tuple(b.name for b in BASELINES)


def predict(name: str, train: pd.DataFrame, test: pd.DataFrame,
            horizon_months: int, benchmark: str = "vw") -> np.ndarray:
    """Baseline predictions on `test`, fitted only on `train` where fitting
    is even involved."""
    h = horizon_months
    if name == "constant":
        mu = float(train[f"excess_{benchmark}_{h}m"].mean())
        return np.full(len(test), mu, dtype="float64")
    if name == "prior":
        # No fitting: the band constants are the model. They were measured on
        # the full 2013-2024 window, so this baseline is FLATTERED out of
        # sample -- stated in the receipt, not hidden.
        return test[f"prior_{h}m"].to_numpy(dtype="float64")
    if name == "rank_upside":
        return _xs_rank(test, "ratio")
    if name == "rank_consensus":
        return _xs_rank(test, "consensus")
    raise ValueError(f"unknown baseline {name!r}; known: {BASELINE_NAMES}")


def _xs_rank(test: pd.DataFrame, col: str) -> np.ndarray:
    """Within-month percentile of `col`. NaN stays NaN -- a name with no
    reading is not a name in the middle of the pack."""
    return test.groupby("month")[col].rank(pct=True).to_numpy(dtype="float64")


def is_calibrated(name: str) -> bool:
    for b in BASELINES:
        if b.name == name:
            return b.is_calibrated
    return True


def describe() -> list[dict]:
    return [{"name": b.name, "is_calibrated": b.is_calibrated,
             "description": b.description} for b in BASELINES]


__all__ = ["Baseline", "BASELINES", "BASELINE_NAMES", "predict", "is_calibrated", "describe"]
