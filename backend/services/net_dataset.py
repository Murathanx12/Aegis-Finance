"""AEGIS-NET-DATASET-1 — the canonical labels, and the type that stops §65.

    from backend.services import net_dataset as ND
    labels = ND.build_labels(panel, decision_dates, horizon_days=20)

WHY THE TARGETS CHANGED (Order 16 adopted, Order 17 P0-R3)
==========================================================
Our own state vector reads AUC 0.4970-0.5092 on forward SIGN — indistinguishable
from a coin against an MDE of 0.034 — while magnitude reads 0.244 and volatility
0.622. Pointing a network at direction is pointing it at the one thing we have
measured to be absent. So the heads here are rank, quantiles, magnitude,
drawdown, continuation/reversal and competing barriers: the quantities our own
numbers say are learnable, plus the one that matches the objective.

THE BARRIER HEAD IS THE ONE THAT MATTERS FOR WEALTH
====================================================
`P(+20% before -10%)` is much closer to "which stock creates asymmetric wealth"
than "will tomorrow's return be positive". An 80%-accurate model of 1% moves can
be worth less than a 57%-accurate model of +60%/-15% situations, and only the
barrier head asks the second question.

§65 IS ENFORCED BY A TYPE, NOT BY A CONVENTION
===============================================
A path extremum does not scale like a mean. Measured forward, volatility keeps
**0.97** of its size while max drawdown keeps **0.32** — so `x * sqrt(n'/n)`,
which is right for a mean, is badly wrong for a maximum, a minimum or a
first-passage time. The rule "measure the forward quantity ON the forward
horizon" was written down and is exactly the kind of rule that gets forgotten by
someone who has a number at 20 days and needs one at 60.

So `PathStatistic` **refuses to be rescaled**. It carries its horizon and raises
if anyone tries to move it to another one. A mean can be scaled and says so;
a path statistic cannot and says that too.

POINT-IN-TIME IS A PARTITION, NOT A PROMISE
============================================
Features are strictly at or before the decision timestamp; labels are strictly
after it. `assert_pit_partition` checks the two index sets do not intersect,
because "we were careful about leakage" is the honour system and an off-by-one
on a forward window is invisible in every summary statistic.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger(__name__)

DATASET = "AEGIS-NET-DATASET-1"


class LabelRefused(RuntimeError):
    """A label was requested that cannot be computed honestly.

    The missing inputs, each of which has a matching refusal:

      * a forward window that runs off the end of the data — a truncated
        forward horizon silently changes the label's meaning, and a maximum
        over 4 days is not a maximum over 20;
      * a path statistic asked to move to a different horizon (§65);
      * features and labels whose index ranges intersect;
      * a cross-sectional rank over a single name, which is 0.5 by construction
        and carries no information at all.
    """


# ── §65, as a type ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PathStatistic:
    """A quantity read off a PATH. It knows its horizon and refuses to leave it.

    Max drawdown, first-passage time, whether a barrier was touched, the
    running maximum — none of these scale like a mean, and the failure is not
    small: forward, volatility retains 0.97 of its size and max drawdown 0.32.
    A caller who scales one is not making an approximation, they are computing
    a different quantity and labelling it with this one's name.
    """

    value: float
    horizon_days: int
    name: str

    def scale_to(self, horizon_days: int) -> "PathStatistic":
        raise LabelRefused(
            f"{self.name!r} is a PATH statistic measured over "
            f"{self.horizon_days} days and cannot be moved to {horizon_days}. "
            f"`x * sqrt(n'/n)` fits a MEAN; a path extremum does not scale that "
            f"way — forward, volatility keeps 0.97 of its size and max drawdown "
            f"0.32 (§65). Measure the forward quantity ON the forward horizon.")


@dataclass(frozen=True)
class MeanStatistic:
    """A quantity that DOES scale, and says so — the contrast that makes the
    refusal above meaningful rather than blanket caution."""

    value: float
    horizon_days: int
    name: str

    def scale_to(self, horizon_days: int) -> "MeanStatistic":
        if horizon_days < 1 or self.horizon_days < 1:
            raise LabelRefused("horizons must be at least one day")
        return MeanStatistic(
            value=self.value * math.sqrt(horizon_days / self.horizon_days),
            horizon_days=horizon_days, name=self.name)


# ── PIT partition ──────────────────────────────────────────────────────────
def assert_pit_partition(feature_idx: Sequence[int],
                         label_idx: Sequence[int]) -> dict:
    """Features at or before `t`; labels strictly after. No intersection.

    An off-by-one on a forward window is invisible in every summary statistic
    the model produces — the AUC simply comes out better — so this is checked
    rather than intended.
    """
    f, la = set(feature_idx), set(label_idx)
    overlap = sorted(f & la)
    if overlap:
        raise LabelRefused(
            f"{len(overlap)} index/indices appear in BOTH the feature and label "
            f"windows (first: {overlap[:5]}). A label that can see its own "
            f"features is a leak, and it shows up as a better AUC rather than "
            f"as an error.")
    if f and la and max(f) >= min(la):
        raise LabelRefused(
            f"the feature window reaches index {max(f)} while the label window "
            f"starts at {min(la)}. Features must be strictly BEFORE labels; "
            f"touching endpoints is the off-by-one this check exists for.")
    return {"n_feature": len(f), "n_label": len(la), "disjoint": True}


# ── the heads ──────────────────────────────────────────────────────────────
def _window(prices: Sequence[float], start: int, horizon_days: int
            ) -> list[float]:
    if horizon_days < 1:
        raise LabelRefused("horizon_days must be at least 1")
    end = start + horizon_days
    if start < 0 or end >= len(prices):
        raise LabelRefused(
            f"the forward window [{start}, {end}] runs off the end of a series "
            f"of length {len(prices)}. A truncated horizon silently changes the "
            f"label's meaning — a maximum over 4 days is not a maximum over "
            f"{horizon_days} — and a partial label looks exactly like a "
            f"complete one downstream.")
    return [float(p) for p in prices[start:end + 1]]


def forward_return(prices: Sequence[float], t: int, horizon_days: int) -> float:
    w = _window(prices, t, horizon_days)
    return w[-1] / w[0] - 1.0


def forward_max_drawdown(prices: Sequence[float], t: int,
                         horizon_days: int) -> PathStatistic:
    """Worst peak-to-trough INSIDE the forward window. A path statistic."""
    w = _window(prices, t, horizon_days)
    peak, worst = w[0], 0.0
    for p in w:
        peak = max(peak, p)
        worst = min(worst, p / peak - 1.0)
    return PathStatistic(value=worst, horizon_days=horizon_days,
                         name="forward_max_drawdown")


def forward_realised_vol(prices: Sequence[float], t: int,
                         horizon_days: int) -> MeanStatistic:
    """Daily realised volatility over the window. This one DOES scale."""
    w = _window(prices, t, horizon_days)
    r = [math.log(w[i] / w[i - 1]) for i in range(1, len(w))]
    if len(r) < 2:
        raise LabelRefused("need at least two forward returns for a volatility")
    mu = sum(r) / len(r)
    sd = math.sqrt(sum((x - mu) ** 2 for x in r) / (len(r) - 1))
    return MeanStatistic(value=sd, horizon_days=horizon_days,
                         name="forward_realised_vol")


def competing_barriers(prices: Sequence[float], t: int, *, up: float,
                       down: float, horizon_days: int) -> dict:
    """`P(+up before -down)` as a realised label, plus time to whichever hit.

    THE HEAD THAT MATCHES THE OBJECTIVE. Terminal wealth cares whether a
    position reaches +40% before it falls -20%, and that question is not
    recoverable from a horizon return: a name that touched +40% on day 3 and
    ended flat has the same 20-day return as one that never moved, and a very
    different meaning for a book that could have acted.

    `outcome` is one of `up`, `down`, `neither`. `neither` is a real answer and
    is kept as its own class rather than folded into `down` — collapsing it
    would make a quiet name look like a loser and put §16's non-winner
    denominator error into the labels themselves.
    """
    if up <= 0 or down <= 0:
        raise LabelRefused(
            f"barriers must be positive magnitudes (up={up}, down={down}); the "
            f"sign is supplied by the comparison, not by the caller.")
    w = _window(prices, t, horizon_days)
    p0 = w[0]
    for i, p in enumerate(w[1:], start=1):
        r = p / p0 - 1.0
        if r >= up:
            return {"outcome": "up", "days_to_barrier": i, "up": up,
                    "down": down, "horizon_days": horizon_days}
        if r <= -down:
            return {"outcome": "down", "days_to_barrier": i, "up": up,
                    "down": down, "horizon_days": horizon_days}
    return {"outcome": "neither", "days_to_barrier": None, "up": up,
            "down": down, "horizon_days": horizon_days}


def cross_sectional_rank(values: dict[str, float]) -> dict[str, float]:
    """Rank within a DATE, scaled to [0, 1]. The head Gu-Kelly-Xiu points at.

    Cross-sectional because that is where the affordable statistical power is:
    relative claims still add information as the cross-section grows, while a
    market-level directional claim is bounded by how many independent dates
    exist (§58).

    A single name is refused: its rank is 0.5 by construction, which is a fact
    about the arithmetic rather than about the security, and a panel that
    quietly emits 0.5 on thin dates teaches the network that thin dates are
    average.
    """
    if len(values) < 2:
        raise LabelRefused(
            f"a cross-sectional rank needs at least two names; got "
            f"{len(values)}. One name ranks 0.5 by construction — a fact about "
            f"the arithmetic, not about the security.")
    order = sorted(values.items(), key=lambda kv: kv[1])
    n = len(order)
    return {k: i / (n - 1) for i, (k, _v) in enumerate(order)}


def quantile_bucket(values: dict[str, float], n_buckets: int = 10
                    ) -> dict[str, int]:
    """Decile (or n-tile) within the date, from the rank."""
    if n_buckets < 2:
        raise LabelRefused("need at least two buckets")
    ranks = cross_sectional_rank(values)
    return {k: min(n_buckets - 1, int(r * n_buckets)) for k, r in ranks.items()}


def magnitude_exceeds(prices: Sequence[float], t: int, *, threshold: float,
                      horizon_days: int) -> int:
    """`|forward return| > threshold`. The observable IIF-1 already forecasts.

    Shared deliberately: a network head and the investigator campaign scoring
    the same observable means the two are comparable without a translation
    layer, and a translation layer is where a definition quietly drifts.
    """
    if threshold <= 0:
        raise LabelRefused("threshold must be positive")
    return int(abs(forward_return(prices, t, horizon_days)) > threshold)


def continuation_or_reversal(prices: Sequence[float], t: int, *,
                             event_move: float, horizon_days: int) -> str:
    """After a move of `event_move`, did the forward window extend or undo it?

    The Boudoukh et al. split, as a label: extreme moves tied to identifiable
    news tend to CONTINUE, and unexplained ones tend to REVERSE. The label here
    is only the outcome half — which of the two happened. Classifying the CAUSE
    is the rare-event library's job and it must not be inferred from the
    outcome, or the test becomes "did continuation continue".
    """
    if event_move == 0:
        raise LabelRefused("an event move of zero has no direction to continue")
    fwd = forward_return(prices, t, horizon_days)
    if fwd == 0:
        return "flat"
    return "continuation" if (fwd > 0) == (event_move > 0) else "reversal"


# ── assembling one row ─────────────────────────────────────────────────────
def label_row(prices: Sequence[float], t: int, *, horizon_days: int = 20,
              barriers: Sequence[tuple[float, float]] = ((0.20, 0.10),
                                                         (0.40, 0.20),
                                                         (0.75, 0.30)),
              magnitude_thresholds: Sequence[float] = (0.03, 0.05, 0.10)
              ) -> dict:
    """Every head for one (security, date). Refuses rather than truncating.

    All heads share ONE forward window. Letting each head choose its own would
    make the row a mixture of horizons that later gets summarised as though it
    were one, which is how a barrier label at 60 days ends up compared against
    a drawdown label at 20.
    """
    out: dict = {"t": t, "horizon_days": horizon_days,
                 "forward_return": forward_return(prices, t, horizon_days)}
    dd = forward_max_drawdown(prices, t, horizon_days)
    vol = forward_realised_vol(prices, t, horizon_days)
    out["forward_max_drawdown"] = dd.value
    out["forward_realised_vol"] = vol.value
    # The TYPES are kept alongside the numbers so a consumer that wants to
    # rescale has to go through the object that refuses.
    out["_path_statistics"] = {"forward_max_drawdown": dd}
    out["_mean_statistics"] = {"forward_realised_vol": vol}
    for up, down in barriers:
        b = competing_barriers(prices, t, up=up, down=down,
                               horizon_days=horizon_days)
        key = f"barrier_up{int(up * 100)}_down{int(down * 100)}"
        out[key] = b["outcome"]
        out[key + "_days"] = b["days_to_barrier"]
    for thr in magnitude_thresholds:
        out[f"abs_move_exceeds_{int(thr * 100)}"] = magnitude_exceeds(
            prices, t, threshold=thr, horizon_days=horizon_days)
    return out


def build_labels(panel: dict[str, Sequence[float]], t: int, *,
                 horizon_days: int = 20, **kw) -> dict:
    """Labels for every name on one date, plus the cross-sectional heads.

    Names whose forward window runs off the end are DROPPED AND COUNTED, never
    silently shortened — and the count is returned, because a cross-section
    that quietly lost its most recent names is a survivorship filter arriving
    through the back door.
    """
    rows, dropped = {}, {}
    for ticker, prices in panel.items():
        try:
            rows[ticker] = label_row(prices, t, horizon_days=horizon_days, **kw)
        except LabelRefused as e:
            dropped[ticker] = str(e)
    if not rows:
        raise LabelRefused(
            f"no name in the panel has a complete {horizon_days}-day forward "
            f"window at t={t}")
    fwd = {k: v["forward_return"] for k, v in rows.items()}
    try:
        ranks = cross_sectional_rank(fwd)
        buckets = quantile_bucket(fwd)
    except LabelRefused:
        # One surviving name is a real state and it is reported as one. A rank
        # of 0.5 emitted here would teach the network that thin dates are
        # average.
        ranks, buckets = {}, {}
    for k in rows:
        rows[k]["cs_rank"] = ranks.get(k)
        rows[k]["cs_decile"] = buckets.get(k)
    return {"dataset": DATASET, "t": t, "horizon_days": horizon_days,
            "rows": rows, "n_labelled": len(rows),
            "dropped": dropped, "n_dropped": len(dropped),
            "cross_section_available": bool(ranks)}
