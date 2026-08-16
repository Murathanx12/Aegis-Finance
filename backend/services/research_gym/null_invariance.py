"""What must a placebo hold constant before its p-value means anything?

WHY THIS EXISTS (2026-08-16, from N21)
======================================
N21 pre-registered a matched-exposure placebo: for each security, de-risk the
*same number of days* as the real policy, in randomly placed windows of the
same length. Against it the real policy reduced max drawdown by 6.843pp per
block, p = 0.0312, which cleared the registered material floor.

It is a false positive, and the reason is structural rather than statistical.
Precursor fires **cluster** — they arrive in bursts, in volatile periods. Being
out of the market during a burst lowers drawdown whether or not the burst was
identified by anything. The registered placebo scattered its windows uniformly,
so it destroyed the clustering along with the alignment, and then attributed
the whole difference to alignment. A circular block shift of the *actual* fire
mask — same count, same run lengths, same autocorrelation, same seasonality,
only the alignment to outcomes destroyed — gives p = 0.3381 with a median
drawdown reduction LARGER than the observed one.

> A matched-EXPOSURE placebo is not a matched-CLUSTERING placebo.

THE CONTRACT
============
A null is a claim about which properties of the real treatment it holds fixed.
That claim is checkable, so it is checked: a `NullSpec` declares the invariants,
`verify` measures them on the real mask and on the placebo ensemble, and
`p_value` REFUSES to compute anything from an ensemble that violates its own
declaration. A null generator that has not been verified cannot produce a
p-value through this module.

Two things follow that are easy to miss:

* **Declaring nothing is a refusal, not a permissive default.** An empty
  `preserves` tuple raises. The failure mode being guarded against is a null
  that was never asked what it preserves, which is how N21's was written.
* **The tolerance is on the ENSEMBLE, not on one draw.** Any single placebo
  differs from the real mask by construction; what must match is the ensemble's
  central tendency. A generator that matches on average and has ten times the
  variance is a different problem, so dispersion is reported too.

WHAT THIS MODULE DOES NOT DO
============================
It cannot tell you which invariants matter for your outcome. That is economics:
clustering matters for drawdown because drawdown is path-dependent, and it may
not matter for a mean forward return. What it can do is stop the specific
failure where the invariant that mattered was never named — and make the
omission visible at registration rather than in the review of the result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

#: The properties a treatment mask can carry into an outcome on its own. Each
#: is measured by `summarise` under exactly this key.
#:
#: frequency            how often the treatment is on
#: turnover             how often it switches — the cost-bearing property
#: run_lengths          how long each spell lasts (mean and max)
#: clustering           autocorrelation of the mask; the N21 invariant
#: seasonality          calendar concentration (month-of-year shares)
#: cross_sectional_sync how often securities are treated on the same date
INVARIANTS = ("frequency", "turnover", "run_lengths", "clustering",
              "seasonality", "cross_sectional_sync")

#: Lags at which clustering is measured. Twenty covers a one-month spell, which
#: is the scale precursor policies in this programme act on.
CLUSTERING_LAGS = (1, 5, 10, 20)


class NullContractViolation(RuntimeError):
    """A placebo ensemble does not preserve what its specification declared."""


@dataclass(frozen=True)
class NullSpec:
    """What a null claims to hold fixed, and how closely.

    `rel_tolerance` applies to scalar invariants (frequency, turnover, run
    lengths). `abs_tolerance` applies to quantities already on a [-1, 1] or
    share scale (clustering autocorrelations, month shares, cross-sectional
    concordance), where a relative tolerance around a near-zero value is
    meaningless.
    """

    name: str
    preserves: tuple[str, ...]
    rel_tolerance: float = 0.15
    abs_tolerance: float = 0.05
    why: str = ""

    def __post_init__(self) -> None:
        if not self.preserves:
            raise ValueError(
                f"{self.name}: a null must declare what it preserves. An "
                "undeclared invariant is how N21's placebo matched exposure, "
                "destroyed clustering, and attributed the difference to "
                "timing. If the honest answer is 'only frequency', declare "
                "only frequency — and then the reader can see what the "
                "p-value is not controlling for.")
        bad = [p for p in self.preserves if p not in INVARIANTS]
        if bad:
            raise ValueError(f"{self.name}: unknown invariant(s) {bad}; "
                             f"declared: {INVARIANTS}")


# ── measurement ────────────────────────────────────────────────────────────

def _runs(mask: Sequence[bool]) -> list[int]:
    out, cur = [], 0
    for m in mask:
        if m:
            cur += 1
        elif cur:
            out.append(cur)
            cur = 0
    if cur:
        out.append(cur)
    return out


def _autocorr(x: Sequence[float], lag: int) -> float:
    n = len(x)
    if lag >= n:
        return 0.0
    mu = sum(x) / n
    num = sum((x[i] - mu) * (x[i + lag] - mu) for i in range(n - lag))
    den = sum((v - mu) ** 2 for v in x)
    if den <= 0:
        return 0.0
    return num / den


def _month_shares(mask: Sequence[bool], dates: Sequence) -> dict[str, float]:
    total = sum(1 for m in mask if m)
    if not total:
        return {f"{m:02d}": 0.0 for m in range(1, 13)}
    counts = {f"{m:02d}": 0 for m in range(1, 13)}
    for m, d in zip(mask, dates):
        if m:
            counts[str(d)[5:7]] += 1
    return {k: v / total for k, v in counts.items()}


def summarise(mask: Sequence[bool], *, dates: Sequence | None = None,
              panel: dict | None = None) -> dict:
    """Every invariant this module knows how to measure, on one mask.

    `panel` is `{security: mask}` over a shared date index and is required for
    `cross_sectional_sync`; a single series has no cross-section, and reporting
    a number for it would be inventing one.
    """
    mask = [bool(m) for m in mask]
    n = max(len(mask), 1)
    runs = _runs(mask)
    out: dict = {
        "n": len(mask),
        "frequency": sum(mask) / n,
        "turnover": sum(1 for i in range(1, len(mask))
                        if mask[i] != mask[i - 1]) / n,
        "run_lengths": {
            "mean": (sum(runs) / len(runs)) if runs else 0.0,
            "max": max(runs) if runs else 0,
            "n_runs": len(runs),
        },
        "clustering": {str(k): _autocorr([1.0 if m else 0.0 for m in mask], k)
                       for k in CLUSTERING_LAGS},
    }
    if dates is not None:
        out["seasonality"] = _month_shares(mask, dates)
    if panel:
        keys = sorted(panel)
        pairs, tot = 0, 0.0
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a = [bool(v) for v in panel[keys[i]]]
                b = [bool(v) for v in panel[keys[j]]]
                m = min(len(a), len(b))
                if not m:
                    continue
                both = sum(1 for k in range(m) if a[k] and b[k])
                either = sum(1 for k in range(m) if a[k] or b[k])
                tot += (both / either) if either else 0.0
                pairs += 1
        out["cross_sectional_sync"] = (tot / pairs) if pairs else 0.0
    return out


def _mean_summary(summaries: Sequence[dict]) -> dict:
    """Ensemble average of `summarise` outputs, key by key."""
    if not summaries:
        return {}
    out: dict = {}
    keys = set().union(*(set(s) for s in summaries))
    for k in keys:
        vals = [s[k] for s in summaries if k in s]
        if not vals:
            continue
        if isinstance(vals[0], dict):
            sub = set().union(*(set(v) for v in vals))
            out[k] = {kk: sum(v.get(kk, 0.0) for v in vals) / len(vals)
                      for kk in sub}
        elif isinstance(vals[0], (int, float)):
            out[k] = sum(float(v) for v in vals) / len(vals)
    return out


# ── verification ───────────────────────────────────────────────────────────

def _rel_dev(real: float, placebo: float) -> float:
    if real == 0 and placebo == 0:
        return 0.0
    denom = abs(real) if abs(real) > 1e-12 else abs(placebo)
    return abs(real - placebo) / denom


@dataclass(frozen=True)
class InvariantCheck:
    invariant: str
    detail: str
    real: float
    placebo_mean: float
    deviation: float
    tolerance: float
    scale: str          # "relative" | "absolute"

    @property
    def ok(self) -> bool:
        return self.deviation <= self.tolerance + 1e-12

    def as_dict(self) -> dict:
        return {"invariant": self.invariant, "detail": self.detail,
                "real": self.real, "placebo_mean": self.placebo_mean,
                "deviation": self.deviation, "tolerance": self.tolerance,
                "scale": self.scale, "ok": self.ok}


@dataclass(frozen=True)
class NullVerdict:
    spec: NullSpec
    checks: tuple[InvariantCheck, ...]
    n_placebo: int
    #: Invariants the spec did NOT declare. Reported rather than silently
    #: skipped: what a null leaves free is the list of alternative explanations
    #: its p-value cannot exclude, and it belongs beside the p-value.
    undeclared: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def as_dict(self) -> dict:
        return {"null": self.spec.name, "preserves": list(self.spec.preserves),
                "undeclared": list(self.undeclared),
                "n_placebo": self.n_placebo, "ok": self.ok,
                "checks": [c.as_dict() for c in self.checks]}

    def why(self) -> str:
        if self.ok:
            s = (f"null `{self.spec.name}` preserves what it declared "
                 f"({', '.join(self.spec.preserves)}) across {self.n_placebo} "
                 f"draws")
            if self.undeclared:
                s += (f". NOT held fixed: {', '.join(self.undeclared)} — any "
                      f"p-value from this null leaves those free as "
                      f"alternative explanations")
            return s
        bad = [c for c in self.checks if not c.ok]
        return (
            f"NULL CONTRACT VIOLATED — `{self.spec.name}` declares it "
            f"preserves {', '.join(self.spec.preserves)} and does not: "
            + "; ".join(
                f"{c.invariant}/{c.detail} real {c.real:.4f} vs placebo mean "
                f"{c.placebo_mean:.4f} ({c.scale} deviation {c.deviation:.3f} "
                f"> {c.tolerance:.3f})" for c in bad)
            + ". A p-value from this ensemble measures the violated property "
              "as much as the alignment being tested — which is how N21's "
              "matched-exposure placebo produced p = 0.031 for a policy whose "
              "clustering-preserving null gives p = 0.338.")


def _collect(spec: NullSpec, real: dict, ens: dict) -> list[InvariantCheck]:
    checks: list[InvariantCheck] = []
    for inv in spec.preserves:
        if inv not in real or inv not in ens:
            raise NullContractViolation(
                f"{spec.name} declares `{inv}` but it was not measured. "
                f"`seasonality` needs `dates=`, `cross_sectional_sync` needs "
                f"`panel=` — a declared invariant that nothing measured is the "
                f"same as no declaration at all.")
        r, p = real[inv], ens[inv]
        if inv == "run_lengths":
            for key in ("mean", "max"):
                checks.append(InvariantCheck(
                    inv, key, float(r[key]), float(p[key]),
                    _rel_dev(float(r[key]), float(p[key])),
                    spec.rel_tolerance, "relative"))
        elif inv in ("clustering", "seasonality"):
            for key in sorted(r):
                checks.append(InvariantCheck(
                    inv, key, float(r[key]), float(p.get(key, 0.0)),
                    abs(float(r[key]) - float(p.get(key, 0.0))),
                    spec.abs_tolerance, "absolute"))
        elif inv == "cross_sectional_sync":
            checks.append(InvariantCheck(
                inv, "mean_pairwise_concordance", float(r), float(p),
                abs(float(r) - float(p)), spec.abs_tolerance, "absolute"))
        else:
            checks.append(InvariantCheck(
                inv, inv, float(r), float(p), _rel_dev(float(r), float(p)),
                spec.rel_tolerance, "relative"))
    return checks


def verify(spec: NullSpec, real_summary: dict,
           placebo_summaries: Sequence[dict]) -> NullVerdict:
    """Measure the declared invariants on the real mask and the ensemble."""
    if not placebo_summaries:
        raise NullContractViolation(
            f"{spec.name}: no placebo draws to verify against")
    ens = _mean_summary(placebo_summaries)
    checks = _collect(spec, real_summary, ens)
    undeclared = tuple(i for i in INVARIANTS
                       if i not in spec.preserves and i in real_summary)
    return NullVerdict(spec=spec, checks=tuple(checks),
                       n_placebo=len(placebo_summaries), undeclared=undeclared)


def assert_verified(spec: NullSpec, real_summary: dict,
                    placebo_summaries: Sequence[dict]) -> NullVerdict:
    v = verify(spec, real_summary, placebo_summaries)
    if not v.ok:
        raise NullContractViolation(v.why())
    return v


def p_value(observed: float, placebo_stats: Sequence[float], *,
            spec: NullSpec, real_summary: dict,
            placebo_summaries: Sequence[dict],
            lower_is_better: bool = True) -> dict:
    """A one-sided p-value that cannot be computed from an unverified null.

    The verification runs FIRST and raises. There is deliberately no flag to
    skip it: a checker whose result can be ignored is a comment, and the whole
    point is that N21's placebo would not have reached this line.
    """
    verdict = assert_verified(spec, real_summary, placebo_summaries)
    stats = [float(s) for s in placebo_stats]
    if not stats:
        raise NullContractViolation("no placebo statistics")
    # +1 in both terms: the observed value is one of the possible arrangements
    # under the null, and omitting it can return p = 0.
    if lower_is_better:
        k = sum(1 for s in stats if s <= float(observed))
    else:
        k = sum(1 for s in stats if s >= float(observed))
    p = (k + 1) / (len(stats) + 1)
    ordered = sorted(stats)
    return {
        "p_value": p, "observed": float(observed), "n_placebo": len(stats),
        "placebo_median": ordered[len(ordered) // 2],
        "placebo_p05": ordered[max(int(0.05 * len(ordered)) - 1, 0)],
        "placebo_p95": ordered[min(int(0.95 * len(ordered)), len(ordered) - 1)],
        "lower_is_better": lower_is_better,
        "null_contract": verdict.as_dict(),
        "leaves_free": list(verdict.undeclared),
    }


# ── generators ─────────────────────────────────────────────────────────────

def circular_block_shift(mask: Sequence[bool], shift: int) -> list[bool]:
    """Rotate the real mask. Preserves everything except alignment.

    Count, run-length distribution and autocorrelation at every lag survive a
    rotation exactly, because the sequence is unchanged — only its origin
    moves. Seasonality does not survive exactly (a rotation moves spells across
    month boundaries) which is why `seasonality` must be declared to be
    checked, and will usually fail for a rotation of a strongly seasonal mask.
    """
    m = [bool(x) for x in mask]
    if not m:
        return m
    k = int(shift) % len(m)
    return m[-k:] + m[:-k] if k else m


def uniform_random_windows(n: int, n_windows: int, window: int,
                           rng) -> list[bool]:
    """N21's registered placebo: same exposure, windows scattered uniformly.

    Kept, and exported, because it is the counter-example the contract exists
    to catch — `test_null_invariance.py` asserts that it FAILS the clustering
    invariant on a clustered real mask. A guard whose failing case is not
    exercised has never been shown to fire.
    """
    out = [False] * int(n)
    for _ in range(int(n_windows)):
        s = int(rng.integers(0, max(int(n) - int(window), 1)))
        for i in range(s, min(s + int(window), int(n))):
            out[i] = True
    return out


def declared_invariants_for(outcome: str) -> tuple[str, ...]:
    """What a null for this OUTCOME has to hold fixed, from the outcome's shape.

    Not a lookup table of taste. A path-dependent outcome (drawdown, time under
    water) is moved by the arrangement of exposure, so a null for it must fix
    clustering and run lengths or it measures arrangement. A mean forward
    return is a sum and is not moved by arrangement, so frequency is the
    binding property. Turnover is declared whenever costs are charged, because
    the cost side is a function of switches and nothing else.
    """
    o = outcome.strip().lower()
    path_dependent = any(k in o for k in
                         ("drawdown", "underwater", "under water", "max_dd",
                          "path", "terminal", "growth", "wealth", "ruin"))
    if path_dependent:
        return ("frequency", "run_lengths", "clustering", "turnover")
    return ("frequency", "turnover")
