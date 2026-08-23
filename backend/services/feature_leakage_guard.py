"""A feature that is the target in disguise, refused before it is a result.

WHAT THIS EXISTS TO STOP, AND IT IS NOT HYPOTHETICAL
====================================================
2026-08-24, RELATIVE-VALUE-NN-1. The screen returned out-of-sample rank IC of
**0.97-0.99** with t-statistics over 1,000, and reported that the pairwise
signal was licensed. It was not. `net_panel_v1` carries a column called
`cs_rank`, and the name reads like a cross-sectional rank of some state
variable. It is the cross-sectional rank **of the forward return**:

    cs_rank    mean within-date rank IC vs forward_return = +1.0000
    cs_decile  mean within-date rank IC vs forward_return = +0.9950
    mom_252    mean within-date rank IC vs forward_return = +0.0115
    vol_63     mean within-date rank IC vs forward_return = +0.0271

The script's own docstring said "everything else in the panel is a FORWARD
quantity and would be the answer, not a feature" -- and then included `cs_rank`,
because the NAME sounded like state. A property of the data was asserted from
its column name rather than measured, which is this programme's named house
failure mode.

WHY A THRESHOLD, AND WHY THIS ONE
=================================
`MAX_ABS_IC = 0.5` is not tuned and is not close to any real value. In equity
cross-sections no point-in-time state feature has ever had half-perfect rank
agreement with a forward return; the strongest honest predictors in this
repository sit near 0.02-0.03. The bar exists to separate "a feature" from "the
answer wearing a feature's name", and anything above it is the second thing.

`WARN_ABS_IC = 0.2` is reported and not refused: it is far beyond anything this
programme has measured, but it is conceivable for a mechanically-related
control, and a guard that refuses what it cannot justify refusing gets disabled.

THE UNIT IS THE BLOCK
=====================
IC is computed WITHIN each date block and then averaged, never pooled. A feature
pooled across dates can correlate with a target purely through shared time
trend, which would make this guard fire on innocent features and miss the guilty
ones inside a date.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: Above this, the "feature" is the target in disguise. Declared, not tuned.
MAX_ABS_IC = 0.5

#: Reported, never refused.
WARN_ABS_IC = 0.2

#: Below this many usable rows a block says nothing and is skipped.
MIN_ROWS_PER_BLOCK = 30

#: Below this many scored blocks the probe itself is uninformative and REFUSES
#: rather than certifying on almost no evidence.
MIN_BLOCKS = 5


class FeatureLeaksTarget(RuntimeError):
    """A feature carries the answer. Refusing before it becomes a result."""


class LeakageUnknowable(RuntimeError):
    """The probe could not see enough to certify anything."""


def _block_ic(x: pd.Series, y: pd.Series) -> float | None:
    ok = x.notna() & y.notna()
    if ok.sum() < MIN_ROWS_PER_BLOCK:
        return None
    a, b = x[ok], y[ok]
    if a.nunique() < 2 or b.nunique() < 2:
        return None
    return float(np.corrcoef(a.rank(), b.rank())[0, 1])


def target_agreement(frame: pd.DataFrame, features: list[str], target: str,
                     block: str) -> dict[str, dict]:
    """Mean within-block rank IC of every feature against the target."""
    out: dict[str, dict] = {}
    for f in features:
        if f not in frame.columns:
            out[f] = {"status": "ABSENT"}
            continue
        ics = [ic for _, g in frame.groupby(block)
               if (ic := _block_ic(g[f], g[target])) is not None]
        if not ics:
            out[f] = {"status": "UNSCORED", "n_blocks": 0}
            continue
        m = float(np.mean(ics))
        out[f] = {"status": "ok", "n_blocks": len(ics),
                  "mean_rank_ic": round(m, 6), "abs": round(abs(m), 6)}
    return out


def assert_no_target_leakage(frame: pd.DataFrame, *, features: list[str],
                             target: str, block: str,
                             max_abs_ic: float = MAX_ABS_IC) -> dict:
    """Refuse a feature set containing the answer. Returns the full ranking.

    Refuses FIRST on not being able to see enough blocks: a probe that scored
    two dates and found nothing has not cleared anything, and reporting that as
    a pass would be this guard committing the bug it exists to catch.
    """
    agree = target_agreement(frame, features, target, block)
    scored = {f: v for f, v in agree.items() if v.get("status") == "ok"}
    if not scored:
        raise LeakageUnknowable(
            f"no feature could be scored against {target!r} over blocks of "
            f"{block!r} — the probe saw nothing, which is not the same as "
            f"finding nothing")
    n_blocks = max(v["n_blocks"] for v in scored.values())
    if n_blocks < MIN_BLOCKS:
        raise LeakageUnknowable(
            f"only {n_blocks} block(s) were scoreable (floor {MIN_BLOCKS}). "
            f"Certifying a feature set on that is a statement about an almost "
            f"empty sample.")

    guilty = {f: v for f, v in scored.items() if v["abs"] >= max_abs_ic}
    if guilty:
        lines = [f"  {f}: mean within-block rank IC {v['mean_rank_ic']:+.4f} "
                 f"over {v['n_blocks']} blocks" for f, v in
                 sorted(guilty.items(), key=lambda kv: -kv[1]["abs"])]
        raise FeatureLeaksTarget(
            f"these features agree with {target!r} far beyond anything a "
            f"point-in-time state variable can (bar {max_abs_ic}):\n"
            + "\n".join(lines)
            + "\n\nThat is the answer wearing a feature's name. Drop them, or "
              "explain in the spec why a state variable ranks the outcome "
              "almost perfectly.")

    warn = {f: v for f, v in scored.items() if v["abs"] >= WARN_ABS_IC}
    for f, v in warn.items():
        logger.warning("feature_leakage_guard: %s agrees with %s at rank IC "
                       "%+.4f — far above anything measured in this "
                       "repository, worth explaining", f, target,
                       v["mean_rank_ic"])
    return {"status": "ok", "n_blocks": n_blocks, "bar": max_abs_ic,
            "warned": sorted(warn), "features": agree,
            "ranked": sorted(((v["abs"], f) for f, v in scored.items()),
                             reverse=True)[:5]}
