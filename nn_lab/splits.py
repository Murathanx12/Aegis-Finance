"""Walk-forward splits with an embargo measured in SESSIONS.

train | embargo | validation | embargo | test, rolled forward one test year at a
time on an expanding train window. The embargo is the longest label horizon
(63 sessions), so no training label's forward window reaches the validation
block, and no validation label's window reaches the test block.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from nn_lab import config as C


@dataclass
class Fold:
    name: str
    train: pd.DatetimeIndex
    val: pd.DatetimeIndex
    test: pd.DatetimeIndex


def _pos(cal: pd.DatetimeIndex, d) -> np.ndarray:
    return np.searchsorted(cal.values, pd.DatetimeIndex(d).values)


def walk_forward_folds(dates, cal: pd.DatetimeIndex, *, test_years=C.TEST_YEARS,
                       val_n: int = C.VAL_GRID_DATES, embargo: int = C.EMBARGO_SESSIONS,
                       min_train_dates: int = 52) -> list[Fold]:
    dates = pd.DatetimeIndex(np.sort(pd.unique(pd.DatetimeIndex(dates))))
    pos = _pos(cal, dates)
    folds = []
    for y in test_years:
        te = dates[dates.year == y]
        if len(te) == 0:
            continue
        p0 = _pos(cal, te[:1])[0]
        val_pool = dates[pos < p0 - embargo]
        if len(val_pool) < val_n + min_train_dates:
            continue
        va = val_pool[-val_n:]
        pv = _pos(cal, va[:1])[0]
        tr = dates[pos < pv - embargo]
        if len(tr) < min_train_dates:
            continue
        folds.append(Fold(str(y), tr, va, te))
    return folds


def latest_split(labelled_dates, cal: pd.DatetimeIndex, *, val_n: int = C.VAL_GRID_DATES,
                 embargo: int = C.EMBARGO_SESSIONS) -> Fold:
    """The nightly split: validation = the most recent `val_n` labelled dates;
    train = every date at least `embargo` sessions before the validation block."""
    dates = pd.DatetimeIndex(np.sort(pd.unique(pd.DatetimeIndex(labelled_dates))))
    va = dates[-val_n:]
    pv = _pos(cal, va[:1])[0]
    tr = dates[_pos(cal, dates) < pv - embargo]
    return Fold("latest", tr, va, pd.DatetimeIndex([]))


def check_fold(f: Fold, cal: pd.DatetimeIndex, embargo: int = C.EMBARGO_SESSIONS) -> None:
    """Raise if blocks overlap or the embargo is violated."""
    a, b, c = set(f.train), set(f.val), set(f.test)
    if a & b or b & c or a & c:
        raise AssertionError(f"fold {f.name}: blocks overlap")
    if len(f.train) and len(f.val):
        gap = _pos(cal, f.val[:1])[0] - _pos(cal, f.train[-1:])[0]
        if gap <= embargo:
            raise AssertionError(f"fold {f.name}: train->val gap {gap} <= embargo {embargo}")
    if len(f.val) and len(f.test):
        gap = _pos(cal, f.test[:1])[0] - _pos(cal, f.val[-1:])[0]
        if gap <= embargo:
            raise AssertionError(f"fold {f.name}: val->test gap {gap} <= embargo {embargo}")
