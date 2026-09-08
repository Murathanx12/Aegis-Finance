"""TWO MODEL-FREE LEAK DETECTORS -- S3.

Neither reads the strategy's source. Both are *differential*: they run the
feature builder twice on different views of the same data and report the
columns whose answers disagree. That is why they catch leaks no reviewer spots
-- a reviewer reads the code that was written, and these read the code that
ran.

PROVENANCE AND LICENCE
=====================
freqtrade (`freqtrade/optimize/analysis/{lookahead,recursive}.py`) is
**GPL-3.0** and is NOT copied, imported, adapted or consulted line-by-line.
What was taken is the DESIGN, which is not copyrightable, and it was taken
from a written English specification -- reproduced verbatim below and in
`docs/BUILD_2026-09-08_R5_STRATEGY_PORTS.md` section S3 -- written before this
file existed. Names, signatures, data structures, tolerances, refusal
semantics and the warm-up/lookahead disambiguation are Aegis's own and differ
from upstream's.

THE SPEC (written first; this module implements exactly it)
===========================================================

(a) LOOKAHEAD ANALYSIS
    Given a pure builder `compute(frame) -> DataFrame` and a raw `frame`
    indexed by time:
      1. baseline: `full = compute(frame)`.
      2. for each checkpoint t (a signal timestamp): `cut = compute(frame up
         to and including t)`; every row strictly after t is DELETED, not
         masked -- masking leaves the future in the object and a builder that
         reads `.values` still sees it.
      3. for every column present in both, compare `full.loc[:t, col]` with
         `cut.loc[:t, col]`, NaN-aware, to `atol`/`rtol`.
      4. a column that differs is READING THE FUTURE. Report it BY NAME, with
         the first checkpoint at which it moved and the largest |delta|.
    Disambiguation, which upstream does not make and which is the whole
    difference between a useful report and a noisy one: a column that is
    entirely NaN in the cut frame over the compared span has not leaked, it
    has not WARMED UP. That is `INSUFFICIENT_WARMUP`, reported separately, and
    it is a `CANNOT DETERMINE` for that column at that checkpoint rather than
    a pass or a fail.
    Refusals: no checkpoints, an empty frame, a builder that returns no
    columns, or a builder that raises on the cut frame. Each is a named
    refusal, never a clean bill of health.

(b) RECURSIVE ANALYSIS (warm-up drift)
    Same builder. For each warm-up length n in a declared ladder, compute the
    features on the LAST `n` rows only and read the value of the final row.
    Compare each against the value from the LONGEST warm-up, which is the
    reference. A column whose relative deviation at the strategy's declared
    warm-up exceeds `tolerance` has not converged: the replay's number is a
    function of how much history the replay happened to load, so it cannot be
    reproduced live and nobody will know why.
    Refusals: a frame shorter than a rung is `CANNOT DETERMINE` for that rung
    and is named; a reference value of exactly zero makes the relative
    deviation undefined, and that column reports the ABSOLUTE deviation with
    `relative: null` rather than dividing.

WHAT NEITHER DETECTOR PROVES
============================
Upstream's own caveat is the honest one and is repeated here as canon: a
negative result does not prove there is no leak. These are helpers that catch
the two classes Aegis keeps re-deriving by hand (target leakage; replay-vs-live
drift), not a proof of PIT correctness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

CANNOT_DETERMINE = "CANNOT DETERMINE"

#: freqtrade's published ladder, used because it is the one every reader of
#: that documentation will recognise; the values are data, not code.
DEFAULT_WARMUP_LADDER: tuple[int, ...] = (20, 40, 80, 100, 150, 300, 999)

#: Default numerical tolerances. `atol` is deliberately tight: a leak that
#: moves a feature by 1e-9 is still a leak, and a builder that is genuinely
#: deterministic reproduces to the bit.
DEFAULT_ATOL = 1e-12
DEFAULT_RTOL = 1e-9

#: A feature whose last-row value moves by more than this fraction between
#: warm-up lengths is not converged.
DEFAULT_DRIFT_TOLERANCE = 0.01


class LeakAnalysisRefused(RuntimeError):
    """The analysis could not be run. A refusal is a finding, not a pass."""


@dataclass(frozen=True)
class ColumnFinding:
    column: str
    status: str                     # LOOKAHEAD | CLEAN | INSUFFICIENT_WARMUP
    first_checkpoint: Any = None
    max_abs_delta: float | None = None
    n_checkpoints_differing: int = 0
    note: str = ""

    def as_dict(self) -> dict:
        return {"column": self.column, "status": self.status,
                "first_checkpoint": self.first_checkpoint,
                "max_abs_delta": self.max_abs_delta,
                "n_checkpoints_differing": self.n_checkpoints_differing,
                "note": self.note}


@dataclass(frozen=True)
class LookaheadReport:
    biased_columns: tuple[str, ...]
    findings: tuple[ColumnFinding, ...]
    n_checkpoints: int
    n_columns: int
    verdict: str
    unavailable_columns: tuple[str, ...] = ()
    note: str = ""

    def as_dict(self) -> dict:
        return {"detector": "lookahead_analysis",
                "verdict": self.verdict,
                "biased_columns": list(self.biased_columns),
                "unavailable_columns": list(self.unavailable_columns),
                "n_checkpoints": self.n_checkpoints,
                "n_columns": self.n_columns,
                "findings": [f.as_dict() for f in self.findings],
                "note": self.note,
                "caveat": ("a negative result does not prove there is no leak; "
                           "this is a helper for the common classes, not a "
                           "proof of PIT correctness")}


@dataclass(frozen=True)
class RecursiveReport:
    drifting_columns: tuple[str, ...]
    per_column: Mapping[str, Mapping[str, Any]]
    ladder: tuple[int, ...]
    reference_warmup: int
    declared_warmup: int | None
    tolerance: float
    verdict: str
    refused_rungs: Mapping[int, str] = field(default_factory=dict)
    note: str = ""

    def as_dict(self) -> dict:
        return {"detector": "recursive_analysis",
                "verdict": self.verdict,
                "drifting_columns": list(self.drifting_columns),
                "ladder": list(self.ladder),
                "reference_warmup": self.reference_warmup,
                "declared_warmup": self.declared_warmup,
                "tolerance": self.tolerance,
                "refused_rungs": {str(k): v for k, v in self.refused_rungs.items()},
                "per_column": {k: dict(v) for k, v in self.per_column.items()},
                "note": self.note,
                "caveat": ("a negative result does not prove convergence at "
                           "every future data length; it proves it over this "
                           "ladder on this frame")}


# --------------------------------------------------------------------------
# (a) lookahead analysis


def _series_differs(a: pd.Series, b: pd.Series, *, atol: float, rtol: float
                    ) -> tuple[bool, float]:
    """NaN-aware comparison. NaN vs NaN agrees; NaN vs a number differs."""
    av = pd.to_numeric(a, errors="coerce").to_numpy(dtype=float)
    bv = pd.to_numeric(b, errors="coerce").to_numpy(dtype=float)
    if av.shape != bv.shape:
        return True, float("inf")
    both_nan = np.isnan(av) & np.isnan(bv)
    one_nan = np.isnan(av) ^ np.isnan(bv)
    if one_nan.any():
        return True, float("inf")
    comparable = ~both_nan
    if not comparable.any():
        return False, 0.0
    delta = np.abs(av[comparable] - bv[comparable])
    tol = atol + rtol * np.abs(bv[comparable])
    if bool((delta > tol).any()):
        return True, float(np.nanmax(delta))
    return False, float(np.nanmax(delta)) if delta.size else 0.0


def lookahead_analysis(compute: Callable[[pd.DataFrame], pd.DataFrame],
                       frame: pd.DataFrame,
                       checkpoints: Sequence[Any] | None = None,
                       *,
                       atol: float = DEFAULT_ATOL,
                       rtol: float = DEFAULT_RTOL,
                       max_checkpoints: int = 25) -> LookaheadReport:
    """Cut the frame before each checkpoint and diff the columns.

    `compute` must be PURE: same input frame, same output. A builder that
    reads a clock, a file or a global is not testable by this method, and its
    findings would be noise -- so a column that differs is reported as
    `LOOKAHEAD` and it is the caller's job to know their builder is pure.
    """
    if frame is None or len(frame) == 0:
        raise LeakAnalysisRefused(
            "REFUSED: empty frame. A lookahead analysis over no rows would "
            "report zero biased columns, which reads identically to a pass.")

    if checkpoints is None:
        idx = list(frame.index)
        # Evenly spaced interior checkpoints; the first and last are useless
        # (nothing to cut / nothing cut).
        lo, hi = max(1, len(idx) // 10), len(idx) - 1
        step = max(1, (hi - lo) // max(1, max_checkpoints))
        checkpoints = idx[lo:hi:step][:max_checkpoints]
    checkpoints = [c for c in checkpoints if c in set(frame.index)]
    if not checkpoints:
        raise LeakAnalysisRefused(
            "REFUSED: no checkpoint is present in the frame's index. There is "
            "nothing to cut before, so nothing was tested.")
    checkpoints = list(checkpoints)[:max_checkpoints]

    full = compute(frame)
    if full is None or getattr(full, "empty", True):
        raise LeakAnalysisRefused(
            "REFUSED: the builder returned no columns on the full frame.")
    full = pd.DataFrame(full)

    differing: dict[str, dict] = {}
    unwarmed: dict[str, int] = {}
    compared: dict[str, int] = {}
    n_seen: dict[str, int] = {}

    for t in checkpoints:
        pos = frame.index.get_loc(t)
        if isinstance(pos, slice):                     # duplicate index labels
            pos = pos.stop - 1
        cut_frame = frame.iloc[: int(pos) + 1]
        try:
            cut = pd.DataFrame(compute(cut_frame))
        except Exception as exc:                       # noqa: BLE001
            raise LeakAnalysisRefused(
                f"REFUSED: the builder raised on the frame cut at {t!r}: "
                f"{type(exc).__name__}: {exc}. A builder that cannot run on a "
                f"prefix of its own data cannot be shown leak-free, and a "
                f"swallowed exception here would report a clean run.") from exc

        common = [c for c in full.columns if c in cut.columns]
        span = full.index[: int(pos) + 1]
        for col in common:
            a = full.loc[span, col]
            b = cut.reindex(span)[col]
            n_seen[col] = n_seen.get(col, 0) + 1
            b_num = pd.to_numeric(b, errors="coerce")
            # NOTHING WAS COMPARED is not agreement. A column that is all-NaN
            # on the cut frame over this span has not warmed up, whether or
            # not the full frame also has nothing there; either way this
            # checkpoint tested it zero times.
            if len(b_num) > 0 and bool(b_num.isna().all()):
                unwarmed[col] = unwarmed.get(col, 0) + 1
                continue
            compared[col] = compared.get(col, 0) + 1
            diff, mx = _series_differs(a, b, atol=atol, rtol=rtol)
            if diff:
                rec = differing.setdefault(
                    col, {"first": t, "max": 0.0, "n": 0})
                rec["n"] += 1
                if np.isfinite(mx):
                    rec["max"] = max(rec["max"], mx)
                else:
                    rec["max"] = float("inf")

    findings: list[ColumnFinding] = []
    for col in full.columns:
        if col in differing:
            r = differing[col]
            findings.append(ColumnFinding(
                column=str(col), status="LOOKAHEAD", first_checkpoint=r["first"],
                max_abs_delta=r["max"], n_checkpoints_differing=r["n"],
                note=("this column's value at time t CHANGED when rows after t "
                      "were deleted, so its value at t is a function of the "
                      "future")))
        elif col in unwarmed and not compared.get(col):
            findings.append(ColumnFinding(
                column=str(col), status="INSUFFICIENT_WARMUP",
                n_checkpoints_differing=unwarmed[col],
                note=(f"{CANNOT_DETERMINE}: all-NaN on the cut frame at "
                      f"{unwarmed[col]} checkpoint(s). Not a leak and not a "
                      f"pass -- the column never got enough history to be "
                      f"compared. Declare a warmup and re-run, or widen the "
                      f"cut")))
        elif col in n_seen:
            findings.append(ColumnFinding(
                column=str(col), status="CLEAN",
                note=(f"compared at {compared.get(col, 0)} checkpoint(s); "
                      f"{unwarmed.get(col, 0)} skipped for want of warm-up")))

    biased = tuple(f.column for f in findings if f.status == "LOOKAHEAD")
    unavailable = tuple(f.column for f in findings
                        if f.status == "INSUFFICIENT_WARMUP")
    if biased:
        verdict = "LOOKAHEAD_DETECTED"
    elif unavailable and len(unavailable) == len(findings):
        verdict = CANNOT_DETERMINE
    else:
        verdict = "NO_LOOKAHEAD_FOUND"
    return LookaheadReport(
        biased_columns=biased, findings=tuple(findings),
        n_checkpoints=len(checkpoints), n_columns=int(full.shape[1]),
        unavailable_columns=unavailable, verdict=verdict,
        note=(f"{len(checkpoints)} checkpoint(s), {full.shape[1]} column(s); "
              f"atol {atol:g} rtol {rtol:g}"))


# --------------------------------------------------------------------------
# (b) recursive analysis -- warm-up drift


def recursive_analysis(compute: Callable[[pd.DataFrame], pd.DataFrame],
                       frame: pd.DataFrame,
                       *,
                       ladder: Sequence[int] = DEFAULT_WARMUP_LADDER,
                       declared_warmup: int | None = None,
                       tolerance: float = DEFAULT_DRIFT_TOLERANCE
                       ) -> RecursiveReport:
    """Recompute at several warm-up lengths and table the drift of the last row.

    The reference is the LONGEST rung that the frame can actually supply. A
    rung longer than the frame is refused BY NAME rather than silently
    clamped -- a clamped rung would agree with the reference by construction
    and would read as convergence.
    """
    if frame is None or len(frame) == 0:
        raise LeakAnalysisRefused("REFUSED: empty frame.")
    rungs = sorted({int(n) for n in ladder if int(n) > 0})
    if len(rungs) < 2:
        raise LeakAnalysisRefused(
            "REFUSED: a drift ladder needs at least two rungs; one rung has "
            "nothing to be compared against.")

    refused: dict[int, str] = {}
    values: dict[int, pd.Series] = {}
    for n in rungs:
        if n > len(frame):
            refused[n] = (f"{CANNOT_DETERMINE}: the frame has {len(frame)} rows, "
                          f"fewer than this rung's {n}. NOT clamped to the frame "
                          f"length -- a clamped rung agrees with the reference by "
                          f"construction and would read as convergence.")
            continue
        out = pd.DataFrame(compute(frame.iloc[-n:]))
        if out.empty:
            refused[n] = f"{CANNOT_DETERMINE}: the builder returned no rows."
            continue
        values[n] = pd.to_numeric(out.iloc[-1], errors="coerce")

    if len(values) < 2:
        raise LeakAnalysisRefused(
            f"REFUSED: only {len(values)} usable rung(s) out of {len(rungs)}. "
            f"Refusals: {refused}")

    ref_n = max(values)
    ref = values[ref_n]

    per_column: dict[str, dict[str, Any]] = {}
    drifting: list[str] = []
    for col in ref.index:
        rv = float(ref[col]) if pd.notna(ref[col]) else np.nan
        rows: dict[str, Any] = {}
        worst_rel = 0.0
        for n, v in sorted(values.items()):
            if n == ref_n:
                continue
            cv = float(v.get(col, np.nan))
            if np.isnan(cv) or np.isnan(rv):
                rows[str(n)] = {"value": None if np.isnan(cv) else cv,
                                "abs": None, "relative": None,
                                "note": f"{CANNOT_DETERMINE}: NaN at this rung"}
                continue
            ad = abs(cv - rv)
            rel = None if rv == 0.0 else ad / abs(rv)
            rows[str(n)] = {"value": cv, "abs": ad, "relative": rel}
            if rel is not None:
                worst_rel = max(worst_rel, rel)
        target = declared_warmup if declared_warmup is not None else min(values)
        at_declared = rows.get(str(target))
        rel_at_declared = (at_declared or {}).get("relative")
        drifts = (rel_at_declared is not None and rel_at_declared > tolerance)
        per_column[str(col)] = {
            "reference_value": None if np.isnan(rv) else rv,
            "reference_warmup": ref_n,
            "worst_relative_deviation": worst_rel,
            "relative_deviation_at_declared_warmup": rel_at_declared,
            "status": "WARMUP_DRIFT" if drifts else (
                CANNOT_DETERMINE if rel_at_declared is None else "CONVERGED"),
            "by_warmup": rows,
        }
        if drifts:
            drifting.append(str(col))

    verdict = "WARMUP_DRIFT_DETECTED" if drifting else "CONVERGED"
    if not drifting and all(v["status"] == CANNOT_DETERMINE
                            for v in per_column.values()):
        verdict = CANNOT_DETERMINE
    return RecursiveReport(
        drifting_columns=tuple(drifting), per_column=per_column,
        ladder=tuple(rungs), reference_warmup=ref_n,
        declared_warmup=declared_warmup, tolerance=float(tolerance),
        refused_rungs=refused, verdict=verdict,
        note=(f"reference rung {ref_n}; {len(values)} rung(s) ran, "
              f"{len(refused)} refused"))


__all__ = ["CANNOT_DETERMINE", "ColumnFinding", "DEFAULT_ATOL",
           "DEFAULT_DRIFT_TOLERANCE", "DEFAULT_RTOL", "DEFAULT_WARMUP_LADDER",
           "LeakAnalysisRefused", "LookaheadReport", "RecursiveReport",
           "lookahead_analysis", "recursive_analysis"]
