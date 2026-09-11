"""CALIBRATION ON THE BOARD (roadmap lane M, item M4).

A Brier score is one number that answers two questions at once, and the answers
point in opposite directions. Murphy (1973) splits it::

    Brier = Reliability - Resolution + Uncertainty

* **Reliability** — when this forecaster says 70%, does it happen 70% of the
  time? Lower is better; zero is perfect calibration.
* **Resolution** — does it say different things about different cases at all?
  HIGHER is better. A forecaster that always says the base rate is perfectly
  calibrated and completely useless, and a flat Brier cannot tell it from one
  that is genuinely informative.
* **Uncertainty** — the base-rate variance of the SAMPLE. A property of the
  question, not of the forecaster, and the reason two Brier scores from
  different periods are not comparable without it.

Why this is ~200 lines of numpy and not a dependency: `Metaculus/forecasting-
tools` was read in full (2026-09-09). Its scores are model-versus-CROWD
(`expected_baseline_score`, `deviation_points`), which Aegis has no crowd for;
its `CalibrationAdjuster.test()` computes a flat Brier mean and nothing else.
No Murphy decomposition, no reliability diagram, no grouping, no rolling window,
no persistence check — everything M4 actually asks for is absent, and adopting
it would add `sklearn` + `pandas` as hard imports for none of it.

TWO REFUSALS, BOTH DELIBERATE
=============================
1. **Bins.** Equal-COUNT (quantile) bins, not equal-width, and a hard minimum of
   `MIN_PER_BIN` forecasts per bin. Below `MIN_N_FOR_DECOMPOSITION` resolved
   records the decomposition is REFUSED and only the flat Brier is reported: a
   decomposition on tiny bins is noise dressed as diagnosis, the same family as
   "a Brier score on eleven resolved records is a description of eleven
   records".
2. **The base rate is PIT.** The base-rate forecaster's probability at record
   `i` is the outcome rate over records resolved BEFORE record `i` was made. A
   base rate computed over the whole sample leaks the future into the control
   itself, one layer below the hindsight leak M3 exists to prevent.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

import numpy as np

logger = logging.getLogger(__name__)

#: Target bins. Dropped when the sample cannot fill them.
DEFAULT_BINS = 10

#: No bin may hold fewer than this. A bin of three is a coin flip with a
#: decimal point.
MIN_PER_BIN = 15

#: Below this many resolved records, no decomposition at all -- three bins of
#: fifteen is the floor and 3 x 15 = 45.
MIN_N_FOR_DECOMPOSITION = 45

#: Rolling window defaults: the last N resolved records, or the last D days.
#: BOTH the rolling and the all-time number are always reported together; a
#: rolling-only report hides a mechanism that was briefly calibrated and drifted.
ROLLING_N = 200
ROLLING_DAYS = 90

#: Tetlock-style persistence needs consecutive quarters with enough in each.
MIN_PER_QUARTER = 20
MIN_QUARTER_PAIRS = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def brier_decomposition(p, o, n_bins: int = DEFAULT_BINS) -> dict:
    """Murphy's three-way split, with the identity checked rather than assumed.

    `p` are forecast probabilities, `o` binary outcomes. Returns the flat Brier
    always; the decomposition only when the sample can carry it, and
    `decomposition: "insufficient_n"` when it cannot.

    The identity `Reliability - Resolution + Uncertainty == brier_binned` is
    computed and its absolute error returned. It is an algebraic identity over a
    DISCRETE forecast, so a non-zero value is a BUG in this function and not a
    property of the data -- the cheapest possible self-test, which is why it is
    in the payload rather than only in a test. The RAW `brier` differs from the
    binned one by `binning_residual`; see the note where both are set.
    """
    p = np.asarray(p, dtype=float).ravel()
    o = np.asarray(o, dtype=float).ravel()
    if p.shape != o.shape:
        raise ValueError(f"{p.shape} forecasts and {o.shape} outcomes are not a pairing")
    ok = np.isfinite(p) & np.isfinite(o)
    p, o = p[ok], o[ok]
    n = int(p.size)
    base = float(o.mean()) if n else float("nan")
    brier = float(np.mean((p - o) ** 2)) if n else float("nan")
    out: dict[str, Any] = {
        "n": n, "brier": brier, "base_rate": base,
        "climatology_brier": (base * (1.0 - base)) if n else float("nan"),
    }
    if n < MIN_N_FOR_DECOMPOSITION:
        out["decomposition"] = "insufficient_n"
        out["reason"] = (f"{n} resolved records is below the {MIN_N_FOR_DECOMPOSITION} "
                         f"needed for {max(3, MIN_N_FOR_DECOMPOSITION // MIN_PER_BIN)} "
                         f"bins of {MIN_PER_BIN}. A decomposition on tiny bins is "
                         f"noise dressed as diagnosis.")
        out["bins"] = []
        return out

    k = int(max(3, min(n_bins, n // MIN_PER_BIN)))
    order = np.argsort(p, kind="mergesort")
    # TIES MAY NOT STRADDLE A BIN BOUNDARY.
    #
    # `array_split` on a sorted index cuts by POSITION, so a forecaster that
    # always says 0.5 gets split into ten bins of identical forecasts whose
    # outcome rates differ by sampling noise -- and the decomposition then
    # reports RESOLUTION for a forecaster that made one distinct statement in
    # its life. Merging any chunk whose first value equals the previous chunk's
    # last value makes the bin a set of EQUAL forecasts, which is what the
    # decomposition is defined over.
    chunks: list[np.ndarray] = []
    for idx in np.array_split(order, k):
        if idx.size == 0:
            continue
        if chunks and p[idx[0]] == p[chunks[-1][-1]]:
            chunks[-1] = np.concatenate([chunks[-1], idx])
        else:
            chunks.append(idx)
    bins = []
    reliability = 0.0
    resolution = 0.0
    binned = np.empty_like(p)
    for i, idx in enumerate(chunks):
        if idx.size == 0:
            continue
        binned[idx] = float(p[idx].mean())
        pk = float(p[idx].mean())
        ok_k = float(o[idx].mean())
        nk = int(idx.size)
        reliability += nk * (pk - ok_k) ** 2
        resolution += nk * (ok_k - base) ** 2
        bins.append({
            "bin_id": i, "p_lo": float(p[idx].min()), "p_hi": float(p[idx].max()),
            "n": nk, "mean_forecast": pk, "mean_outcome": ok_k,
            # every bin ships its own uncertainty: a headline without an n or an
            # SE is not trusted in this repository
            "outcome_se": float(math.sqrt(max(ok_k * (1.0 - ok_k), 0.0) / nk)),
            "overconfidence": pk - ok_k,
        })
    reliability /= n
    resolution /= n
    uncertainty = base * (1.0 - base)
    # THE IDENTITY IS ABOUT THE BINNED FORECAST, AND SAYING SO IS THE POINT.
    #
    # Murphy's split is defined over a DISCRETE forecast: every member of a bin
    # is treated as having said the bin's mean. With continuous probabilities the
    # raw Brier differs from the binned one, so `Rel - Res + Unc` equals the
    # BINNED Brier exactly and the raw one only approximately. Reporting
    # `identity_check_abs_error` against the raw Brier would make a correct
    # function look broken by an amount that is really a property of the binning.
    # Both numbers are here and their difference is named rather than absorbed.
    brier_binned = float(np.mean((binned - o) ** 2))
    out.update({
        "n_bins": len(bins),
        "reliability": reliability, "resolution": resolution,
        "uncertainty": uncertainty,
        "brier_binned": brier_binned,
        # `brier - brier_binned` = within-bin VARIANCE of the forecast minus
        # twice its within-bin COVARIANCE with the outcome. Its sign is not
        # constrained: a forecaster whose probabilities still discriminate
        # INSIDE a bin scores better raw than binned, and that is information
        # the binning threw away, not an error. Named, so nobody reads it as one.
        "binning_residual": brier - brier_binned,
        "identity_check_abs_error": abs((reliability - resolution + uncertainty)
                                        - brier_binned),
        "identity_note": ("Reliability - Resolution + Uncertainty == brier_binned "
                          "EXACTLY -- the decomposition is defined over a discrete "
                          "forecast. The raw `brier` differs by `binning_residual`, "
                          "a property of the binning rather than of the forecaster, "
                          "and its sign can go either way."),
        "beats_climatology": bool(brier < uncertainty),
        "bins": bins,
        "decomposition": "ok",
    })
    return out


# ===========================================================================
# THE LEDGER SIDE
# ===========================================================================


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def resolved_rows(rows: Iterable[dict]) -> list[dict]:
    """Graded, un-voided records with a usable probability. Nothing else."""
    out = []
    for r in rows:
        if r.get("void_reason") or r.get("outcome") is None:
            continue
        p = r.get("probability")
        if p is None or not math.isfinite(float(p)):
            continue
        out.append(r)
    return out


def base_rate_row(rows: Sequence[dict]) -> dict:
    """The control every forecaster is scored against, computed POINT-IN-TIME.

    At record `i` the base-rate forecaster says "the rate among everything
    resolved before this record was made". A base rate computed over the whole
    sample would leak the future into its own control -- the same defect as
    hindsight retrieval, one layer down -- and would make the control look
    better than any forecaster could have been at the time.

    Records made before ANYTHING had resolved get p = 0.5, which is the only
    honest answer available to a forecaster with no history, and they are
    counted separately so the row can be read for what it is.
    """
    ordered = sorted(rows, key=lambda r: str(r.get("made_at") or ""))
    ps, os_, n_no_history = [], [], 0
    history: list[tuple[date, float]] = []   # (resolved_at, outcome)
    for r in ordered:
        made = _as_date(r.get("made_at"))
        prior = [o for d, o in history if made is None or d <= made]
        if prior:
            ps.append(float(np.mean(prior)))
        else:
            ps.append(0.5)
            n_no_history += 1
        os_.append(float(r["outcome"]))
        rd = _as_date(r.get("resolved_at"))
        if rd is not None:
            history.append((rd, float(r["outcome"])))
    dec = brier_decomposition(ps, os_)
    dec.update({"model": "base_rate_forecaster", "n_no_history": n_no_history,
                "pit": True,
                "note": ("p at each record is the outcome rate among records "
                         "resolved BEFORE that record was made. A full-sample base "
                         "rate would leak the future into its own control.")})
    return dec


def _quarter(d: date | None) -> str | None:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}" if d else None


def persistence(rows: Sequence[dict]) -> dict:
    """Does last quarter's calibration predict this quarter's? (Tetlock)

    Pearson `r` of the Brier skill score across consecutive quarter pairs.
    REFUSES below `MIN_QUARTER_PAIRS`: a persistence correlation on one or two
    pairs is a coin flip reported as a coefficient, and this repository has a
    standing rule against gates that cannot go green being read as gates that
    failed.
    """
    by_q: dict[str, list[dict]] = {}
    for r in rows:
        q = _quarter(_as_date(r.get("resolved_at")))
        if q:
            by_q.setdefault(q, []).append(r)
    usable = {q: v for q, v in by_q.items() if len(v) >= MIN_PER_QUARTER}
    qs = sorted(usable)
    bss: dict[str, float] = {}
    for q in qs:
        p = [float(r["probability"]) for r in usable[q]]
        o = [float(r["outcome"]) for r in usable[q]]
        d = brier_decomposition(p, o)
        clim = d["climatology_brier"]
        if clim and math.isfinite(clim) and clim > 0:
            bss[q] = 1.0 - d["brier"] / clim
    pairs = [(bss[a], bss[b]) for a, b in zip(qs, qs[1:]) if a in bss and b in bss]
    if len(pairs) < MIN_QUARTER_PAIRS:
        return {"persistence": "insufficient_quarters", "n_pairs": len(pairs),
                "quarters_scored": len(bss), "min_pairs": MIN_QUARTER_PAIRS,
                "min_per_quarter": MIN_PER_QUARTER,
                "bss_by_quarter": {k: round(v, 4) for k, v in bss.items()}}
    x = np.array([a for a, _ in pairs], dtype=float)
    y = np.array([b for _, b in pairs], dtype=float)
    if x.std() == 0 or y.std() == 0:
        return {"persistence": "degenerate", "n_pairs": len(pairs),
                "reason": "a constant skill score has no correlation to report"}
    return {"persistence": "ok", "r": float(np.corrcoef(x, y)[0, 1]),
            "n_pairs": len(pairs),
            "bss_by_quarter": {k: round(v, 4) for k, v in bss.items()}}


def _rolling(rows: Sequence[dict], *, n: int, days: int) -> list[dict]:
    ordered = sorted(rows, key=lambda r: str(r.get("resolved_at") or ""))
    cutoff = date.today() - timedelta(days=int(days))
    recent = [r for r in ordered if (_as_date(r.get("resolved_at")) or date.min) >= cutoff]
    return (recent or ordered)[-int(n):]


def report(rows: Iterable[dict], *, by: str = "model",
           n_bins: int = DEFAULT_BINS, rolling_n: int = ROLLING_N,
           rolling_days: int = ROLLING_DAYS) -> dict:
    """The whole M4 payload: decomposition, diagram, groups, rolling, persistence.

    `by` is `model` (+ `model_version`) or `mechanism_id`. NOT `specialist`:
    that names the calling code path rather than the hypothesis family, and two
    specialists can share a mechanism. Grouping by mechanism is what lets a
    later distillation compare like with like.

    Pre-1.4.0 records carry no `mechanism_id`; they are grouped under
    `unstated (pre-1.4.0)` and the payload SAYS so, rather than being dropped
    (a group that vanishes is a group nobody notices is missing).
    """
    res = resolved_rows(rows)
    out: dict[str, Any] = {
        "as_of": _now(), "group_by": by,
        "n_resolved": len(res),
        "min_per_bin": MIN_PER_BIN,
        "min_n_for_decomposition": MIN_N_FOR_DECOMPOSITION,
    }
    if not res:
        out["overall"] = {"n": 0, "decomposition": "insufficient_n",
                          "reason": "nothing has resolved yet"}
        out["groups"] = {}
        out["base_rate_row"] = {"n": 0}
        out["persistence"] = {"persistence": "insufficient_quarters", "n_pairs": 0}
        return out

    p = [float(r["probability"]) for r in res]
    o = [float(r["outcome"]) for r in res]
    out["overall"] = brier_decomposition(p, o, n_bins)
    roll = _rolling(res, n=rolling_n, days=rolling_days)
    out["rolling"] = {
        "window": f"last {rolling_n} resolved, or the last {rolling_days} days",
        **brier_decomposition([float(r["probability"]) for r in roll],
                              [float(r["outcome"]) for r in roll], n_bins),
        "note": ("reported BESIDE the all-time number, never instead of it: a "
                 "rolling-only report hides a mechanism that was briefly "
                 "calibrated and has since drifted"),
    }
    out["base_rate_row"] = base_rate_row(res)
    out["persistence"] = persistence(res)

    def key_of(r: dict) -> str:
        if by == "mechanism_id":
            return str(r.get("mechanism_id") or "unstated (pre-1.4.0)")
        v = str(r.get("model") or "unstated")
        ver = r.get("model_version")
        return f"{v}@{ver}" if ver else v

    groups: dict[str, list[dict]] = {}
    for r in res:
        groups.setdefault(key_of(r), []).append(r)
    out["groups"] = {
        k: {"group_key": k,
            **brier_decomposition([float(r["probability"]) for r in v],
                                  [float(r["outcome"]) for r in v], n_bins)}
        for k, v in sorted(groups.items())
    }
    return out


def ledger_report(path=None, **kw) -> dict:
    """`report()` over the live prediction ledger. A read; never writes."""
    from backend.services import belief_state as BS

    try:
        rows = BS.read_predictions(path)
    except Exception as exc:                                       # noqa: BLE001
        return {"as_of": _now(), "available": False,
                "error": f"{type(exc).__name__}: {exc}"}
    out = report(rows, **kw)
    out["available"] = True
    out["path"] = str(path or BS.PREDICTIONS)
    return out
