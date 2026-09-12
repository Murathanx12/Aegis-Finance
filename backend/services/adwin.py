"""ADWIN2 -- adaptive windowing over an error stream, in this repo rather than a dependency.

Bifet & Gavalda, "Learning from Time-Changing Data with Adaptive Windowing",
Proc. 2007 SIAM International Conference on Data Mining, 443-448. The window
grows while the stream looks stationary and is CUT wherever two sub-windows'
means differ by more than a Hoeffding-style bound, which is what buys a
false-positive rate you can state instead of a window length you had to guess.

WHY NOT `river`. The spec's first choice is `river.drift.ADWIN` (BSD-3, PyPI),
and the decision rule it gives is "default to river unless its install is
refused". It was: this venv has no network for new packages and
`pip install --no-index river` reports *"Could not find a version that
satisfies the requirement river (from versions: none)"*. `river` is also a full
online-ML framework for a one-class need. So the fallback the spec provides is
taken, and this is it -- the ADWIN2 bucket-compression variant of the paper's
section 3, about 90 lines with the docstrings.

THE CUT TEST, exactly:

    m       = 1 / (1/n0 + 1/n1)          the harmonic mean of the two sides
    delta'  = delta / n                  n = the whole window's width
    eps_cut = sqrt( (2/m) * var * ln(2/delta') ) + (2 / (3m)) * ln(2/delta')

with `var` the whole window's variance. A cut is signalled when
`|mu0 - mu1| > eps_cut` for ANY split into an older W0 and a newer W1, and the
oldest bucket is then dropped and the test repeated until no split breaches.

BUCKETS. Exact windows cost memory linear in the window; ADWIN2 keeps
`max_buckets` buckets per size class, merging the two oldest of a full class
into one of the next size up. The window's length is then exact and its
CONTENTS are summarised, which is why `mean` is exact and individual
observations cannot be recovered.

THE STREAM MUST BE IN [0, 1], and this is not a style note. The Hoeffding-style
bound carries an additive `2/(3m) * ln(2/delta')` term that does NOT scale with
the data, so on a stream of magnitude 0.01 that term alone is several times any
real jump and the detector can never fire. Measured here: a clean 0.008 -> 0.052
step in mean absolute error produced ZERO detections, while the identical step
scaled into [0, 1] fired 55 observations later. `to_unit` is the one place that
scaling happens, and a caller that skips it gets a detector that is silent
rather than one that is wrong -- which is the worse failure of the two.

This module has no state beyond the detector object and touches nothing else in
the repo: it is given numbers and it says whether they changed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    total: float
    count: int
    variance: float = 0.0


@dataclass
class ADWIN:
    """`update(x) -> bool`. True on the update that signalled a change.

    `delta` is the confidence parameter: the paper's bound gives a false-positive
    rate below `delta` per cut test. Smaller means fewer, later alarms.
    """
    delta: float = 0.002
    max_buckets: int = 5
    min_clock: int = 32
    #: rows[i] holds buckets each summarising 2^i observations, oldest row first
    rows: list[list[_Bucket]] = field(default_factory=list)
    width: int = 0
    total: float = 0.0
    variance: float = 0.0
    _clock: int = 0
    n_detections: int = 0
    last_detection_at: int | None = None
    seen: int = 0

    # ---------------------------------------------------------------- state
    @property
    def mean(self) -> float:
        return self.total / self.width if self.width else 0.0

    def _all_buckets(self) -> list[_Bucket]:
        """Oldest first. rows[-1] holds the LARGEST (oldest) buckets."""
        out: list[_Bucket] = []
        for row in reversed(self.rows):
            out.extend(row)
        return out

    # --------------------------------------------------------------- insert
    def _insert(self, value: float) -> None:
        v = float(value)
        if self.width:
            incr = (v - self.mean) ** 2 * self.width / (self.width + 1)
        else:
            incr = 0.0
        if not self.rows:
            self.rows.append([])
        self.rows[0].insert(0, _Bucket(v, 1, 0.0))
        self.width += 1
        self.total += v
        self.variance += incr
        self._compress()

    def _compress(self) -> None:
        i = 0
        while i < len(self.rows):
            if len(self.rows[i]) <= self.max_buckets:
                break
            b1 = self.rows[i].pop()
            b2 = self.rows[i].pop()
            n1, n2 = b1.count, b2.count
            mu1 = b1.total / n1
            mu2 = b2.total / n2
            merged = _Bucket(
                b1.total + b2.total, n1 + n2,
                b1.variance + b2.variance + n1 * n2 * (mu1 - mu2) ** 2 / (n1 + n2))
            if i + 1 == len(self.rows):
                self.rows.append([])
            self.rows[i + 1].insert(0, merged)
            i += 1

    def _drop_oldest(self) -> None:
        for i in range(len(self.rows) - 1, -1, -1):
            if self.rows[i]:
                b = self.rows[i].pop()
                n = b.count
                mu = b.total / n
                rest = self.width - n
                if rest > 0:
                    mu_rest = (self.total - b.total) / rest
                    self.variance -= b.variance + n * rest * (mu - mu_rest) ** 2 / self.width
                else:
                    self.variance = 0.0
                self.width -= n
                self.total -= b.total
                self.variance = max(self.variance, 0.0)
                while self.rows and not self.rows[-1]:
                    self.rows.pop()
                return

    # ------------------------------------------------------------- the test
    def _eps_cut(self, n0: int, n1: int) -> float:
        m = 1.0 / (1.0 / n0 + 1.0 / n1)
        delta_prime = self.delta / max(self.width, 1)
        var = self.variance / self.width if self.width else 0.0
        ln = math.log(2.0 / delta_prime)
        return math.sqrt(2.0 / m * var * ln) + 2.0 / (3.0 * m) * ln

    def _detect(self) -> bool:
        """Drop the oldest bucket while ANY split breaches the bound."""
        changed = False
        shrinking = True
        while shrinking and self.width >= 2:
            shrinking = False
            buckets = self._all_buckets()          # oldest first
            n0 = 0
            t0 = 0.0
            for b in buckets[:-1]:                 # never split off the whole window
                n0 += b.count
                t0 += b.total
                n1 = self.width - n0
                if n0 < 5 or n1 < 5:
                    continue
                mu0 = t0 / n0
                mu1 = (self.total - t0) / n1
                if abs(mu0 - mu1) > self._eps_cut(n0, n1):
                    self._drop_oldest()
                    changed = True
                    shrinking = True
                    break
        return changed

    # ------------------------------------------------------------- the API
    def update(self, value: float) -> bool:
        """Feed one observation. True iff this update signalled a change.

        The detection test runs on a clock (`min_clock`) rather than on every
        observation, which is the paper's own cost reduction and does not change
        which changes are eventually found -- only how soon within `min_clock`
        steps. `seen` counts observations so a caller can report WHEN it fired.
        """
        self.seen += 1
        self._insert(value)
        self._clock += 1
        if self._clock < self.min_clock or self.width < 2 * 5:
            return False
        self._clock = 0
        fired = self._detect()
        if fired:
            self.n_detections += 1
            self.last_detection_at = self.seen
        return fired

    def state(self) -> dict:
        return {"width": self.width, "mean": round(self.mean, 8),
                "variance": round(self.variance / self.width, 10) if self.width else None,
                "n_detections": self.n_detections,
                "last_detection_at": self.last_detection_at,
                "delta": self.delta, "max_buckets": self.max_buckets,
                "min_clock": self.min_clock, "observations_seen": self.seen}


def unit_scale(values, factor: float = 4.0) -> float:
    """A frozen divisor that puts a positive stream inside [0, 1].

    `factor x median` rather than the max: one outlier setting the scale would
    compress every later observation towards zero and make the detector blind
    for the rest of the run. The scale is computed ONCE, from a calibration
    window, and frozen -- a rescaling that tracked the stream would absorb the
    very drift the detector is looking for.
    """
    v = [abs(float(x)) for x in values if x is not None and float(x) == float(x)]
    if not v:
        return 1.0
    v.sort()
    med = v[len(v) // 2]
    return float(max(med * float(factor), 1e-12))


def to_unit(value: float, scale: float) -> float:
    """`clip(|x| / scale, 0, 1)`. Values above the scale saturate, by design."""
    return float(min(max(abs(float(value)) / float(scale), 0.0), 1.0))


def declaration() -> dict:
    """What a receipt has to say about which ADWIN this was."""
    return {
        "module": "backend.services.adwin",
        "algorithm": "ADWIN2 (bucket-compressed adaptive windowing)",
        "citation": ("Bifet & Gavalda, Learning from Time-Changing Data with Adaptive "
                     "Windowing, SDM 2007, 443-448"),
        "library": "NONE -- implemented here",
        "why_not_river": ("the spec's first choice is river.drift.ADWIN (BSD-3). This venv "
                          "cannot install it offline: `pip install --no-index river` reports "
                          "'Could not find a version that satisfies the requirement river "
                          "(from versions: none)'. The spec's own fallback was taken so E4 is "
                          "not BLOCKED on a packaging decision."),
        "cut_test": ("|mu0 - mu1| > sqrt(2/m * var * ln(2/delta')) + 2/(3m) * ln(2/delta'), "
                     "m = 1/(1/n0 + 1/n1), delta' = delta/width"),
        "stream_domain": ("[0, 1] REQUIRED -- the bound's additive 2/(3m) ln(2/delta') term "
                          "does not scale with the data, so an unscaled 0.008 -> 0.052 error "
                          "step produced zero detections here while the same step scaled into "
                          "[0, 1] fired 55 observations later. `to_unit(x, scale)` with a "
                          "frozen `unit_scale` is the one place that scaling happens."),
    }
