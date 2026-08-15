"""Controls for a teacher event, built BEFORE any winner is interpreted.

WHY THIS EXISTS AHEAD OF THE FINDING
====================================
The tempting first result from a Teacher Library is a story: *a CEO bought after
a 40% drawdown and the stock doubled*. That sentence contains no comparison, so
it cannot be wrong, so it cannot be evidence. Built after such a story is found,
a control is chosen — however honestly — by someone who already knows which
control makes the story survive.

So the control engine is written first, its covariates are declared here, and
the placebo family is fixed before an event is scored.

WHAT A CONTROL HAS TO ANSWER
============================
Four different questions, and one control cannot serve all four:

  MATCHED_SECURITY   would a similar stock, with no insider event, have done the
                     same thing over the same window? (removes sector, size,
                     momentum, volatility, drawdown, liquidity)
  ACTOR_SHUFFLE      does WHO acted matter? Same events, actor labels permuted.
                     Kills actor-specific information, keeps timing and
                     selection intact.
  DATE_SHUFFLE       does WHEN they acted matter? Same actor and security, the
                     date moved elsewhere in the same regime. Kills timing,
                     keeps selection.
  SIGN_FLIP          are the sells informative too, or is the whole effect a
                     long-equity drift dressed as a signal?

Reporting one of these and calling it "controlled" is how a drift premium
becomes an insider edge.

BALANCE IS REPORTED, NOT ASSUMED
================================
A "matched" control that is not balanced on its covariates is worse than no
control, because it carries the authority of the word `matched`. Every match
returns the standardised mean difference achieved on each covariate, and
`is_balanced` is a fact on the result rather than a claim in a docstring.

AND EVERY COMPARISON PRINTS ITS MDE (§19)
=========================================
Teacher events are scarce and clustered. A comparison of 6 events against 30
controls cannot detect a 2pp effect, and reporting "no difference" from it would
be absence of evidence sold as evidence of absence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from backend.services.research_gym import power as PW

#: Covariates a matched control must balance on. DECLARED HERE, before any
#: event has been scored — adding one after seeing a result is choosing the
#: comparison that flatters, and the list is short enough to audit.
#:
#: `valuation` is deliberately ABSENT: it is unreliable across the universe this
#: library covers (financials, REITs, loss-makers), and a covariate that is
#: missing for a third of candidates silently restricts the pool to the
#: two-thirds where it exists.
COVARIATES = (
    "sector",              # exact match, not a distance
    "log_market_cap",
    "beta",
    "momentum_12m",
    "realised_vol_60d",
    "drawdown_pct",
    "log_dollar_volume",
    "days_to_next_earnings",
)

#: Matched exactly rather than by distance. A "nearby" sector is not a sector.
EXACT_COVARIATES = ("sector",)

#: |standardised mean difference| above which a covariate is NOT balanced. 0.10
#: is the conventional applied threshold and is declared rather than tuned.
MAX_ABS_SMD = 0.10

#: Below this many controls per event, a comparison is reported as unpowered
#: rather than as a null.
MIN_CONTROLS_PER_EVENT = 5

MATCHED_SECURITY = "matched_security"
ACTOR_SHUFFLE = "actor_shuffle"
DATE_SHUFFLE = "date_shuffle"
SIGN_FLIP = "sign_flip"
PLACEBO_FAMILY = (MATCHED_SECURITY, ACTOR_SHUFFLE, DATE_SHUFFLE, SIGN_FLIP)


class ControlRefused(ValueError):
    """The comparison cannot be made honestly, and why."""


@dataclass(frozen=True)
class Candidate:
    """One securityday, with its PIT covariates and its forward outcome.

    `forward_return_pct` is deliberately a separate field from the covariates:
    matching reads the covariates and must never read the outcome, and keeping
    them in one dict is how that stops being true.
    """
    key: str                      # "TICKER@YYYY-MM-DD"
    ticker: str
    date: str
    covariates: dict
    forward_return_pct: float | None = None
    has_event: bool = False
    actor_id: str = ""
    action_type: str = ""


@dataclass
class Balance:
    """How well the controls actually match, per covariate."""
    smd: dict[str, float] = field(default_factory=dict)
    unmeasurable: list[str] = field(default_factory=list)

    @property
    def worst(self) -> tuple[str, float] | None:
        if not self.smd:
            return None
        k = max(self.smd, key=lambda x: abs(self.smd[x]))
        return k, self.smd[k]

    @property
    def is_balanced(self) -> bool:
        return (not self.unmeasurable
                and all(abs(v) <= MAX_ABS_SMD for v in self.smd.values()))

    def as_dict(self) -> dict:
        w = self.worst
        return {"smd": {k: round(v, 4) for k, v in sorted(self.smd.items())},
                "unmeasurable": sorted(self.unmeasurable),
                "worst_covariate": None if w is None else w[0],
                "worst_smd": None if w is None else round(w[1], 4),
                "is_balanced": self.is_balanced,
                "threshold": MAX_ABS_SMD}


@dataclass
class ControlResult:
    """One event set against one control arm, with its own power."""
    arm: str
    n_events: int
    n_controls: int
    mean_event_pct: float | None
    mean_control_pct: float | None
    diff_pct: float | None
    se_pct: float | None
    t_stat: float | None
    mde_pct: float | None
    balance: Balance | None
    reason: str = ""

    @property
    def is_detectable(self) -> bool | None:
        if self.mde_pct is None or self.diff_pct is None:
            return None
        return abs(self.diff_pct) >= self.mde_pct

    @property
    def is_interpretable(self) -> bool:
        """False when the arm cannot support a conclusion in either direction."""
        if self.mde_pct is None or self.n_controls < MIN_CONTROLS_PER_EVENT:
            return False
        return self.balance is None or self.balance.is_balanced

    def as_dict(self) -> dict:
        return {
            "arm": self.arm, "n_events": self.n_events,
            "n_controls": self.n_controls,
            "mean_event_pct": _r(self.mean_event_pct),
            "mean_control_pct": _r(self.mean_control_pct),
            "diff_pct": _r(self.diff_pct), "se_pct": _r(self.se_pct),
            "t_stat": _r(self.t_stat), "mde_pct": _r(self.mde_pct),
            "detectable": self.is_detectable,
            "interpretable": self.is_interpretable,
            "balance": None if self.balance is None else self.balance.as_dict(),
            "reason": self.reason,
            "citable": False,
        }


def _r(v, n=3):
    return None if v is None else round(float(v), n)


# ── matching ────────────────────────────────────────────────────────────────

def _numeric_covariates(pool: Sequence[Candidate]) -> list[str]:
    out = []
    for c in COVARIATES:
        if c in EXACT_COVARIATES:
            continue
        vals = [x.covariates.get(c) for x in pool]
        if any(v is not None for v in vals):
            out.append(c)
    return out


def _scales(pool: Sequence[Candidate], names: Sequence[str]) -> dict[str, float]:
    """Per-covariate spread, for standardising distances and SMDs."""
    sc = {}
    for n in names:
        vals = [float(x.covariates[n]) for x in pool
                if x.covariates.get(n) is not None]
        if len(vals) > 1:
            m = sum(vals) / len(vals)
            var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
            sc[n] = math.sqrt(var) or 1.0
        else:
            sc[n] = 1.0
    return sc


def _distance(a: Candidate, b: Candidate, names: Sequence[str],
              scales: dict[str, float]) -> float | None:
    """Standardised Euclidean distance. None when a covariate is unmeasured.

    Returning None rather than skipping the term is the point: a candidate
    missing `beta` is not a close match on beta, it is an unknown one, and
    treating unknown as zero distance would preferentially select candidates
    with missing data.
    """
    total = 0.0
    for n in names:
        va, vb = a.covariates.get(n), b.covariates.get(n)
        if va is None or vb is None:
            return None
        total += ((float(va) - float(vb)) / scales[n]) ** 2
    return math.sqrt(total)


def match_controls(event: Candidate, pool: Iterable[Candidate], *,
                   k: int = 5,
                   exclude_events: bool = True) -> list[Candidate]:
    """`k` nearest control securities on the declared covariates, same date.

    Controls are drawn from the SAME DATE as the event. A control measured over
    a different window is a comparison against a different market, and the
    market moves further than any insider signal in the sample.
    """
    same_day = [c for c in pool
                if c.date == event.date and c.ticker != event.ticker
                and (not exclude_events or not c.has_event)]
    for ex in EXACT_COVARIATES:
        want = event.covariates.get(ex)
        same_day = [c for c in same_day if c.covariates.get(ex) == want]
    if not same_day:
        return []
    names = _numeric_covariates(same_day + [event])
    scales = _scales(same_day + [event], names)
    scored = []
    for c in same_day:
        d = _distance(event, c, names, scales)
        if d is not None:
            scored.append((d, c))
    scored.sort(key=lambda t: (t[0], t[1].key))
    return [c for _, c in scored[:k]]


def balance_of(events: Sequence[Candidate],
               controls: Sequence[Candidate]) -> Balance:
    """Standardised mean difference per covariate, after matching."""
    b = Balance()
    if not events or not controls:
        b.unmeasurable = list(COVARIATES)
        return b
    for n in COVARIATES:
        if n in EXACT_COVARIATES:
            # Exact match: balanced by construction, or the match was refused.
            ev = {e.covariates.get(n) for e in events}
            cv = {c.covariates.get(n) for c in controls}
            if ev != cv:
                b.unmeasurable.append(n)
            continue
        ev = [float(e.covariates[n]) for e in events
              if e.covariates.get(n) is not None]
        cv = [float(c.covariates[n]) for c in controls
              if c.covariates.get(n) is not None]
        if len(ev) < 2 or len(cv) < 2:
            b.unmeasurable.append(n)
            continue
        me, mc = sum(ev) / len(ev), sum(cv) / len(cv)
        ve = sum((v - me) ** 2 for v in ev) / (len(ev) - 1)
        vc = sum((v - mc) ** 2 for v in cv) / (len(cv) - 1)
        pooled = math.sqrt((ve + vc) / 2.0)
        b.smd[n] = 0.0 if pooled == 0 else (me - mc) / pooled
    return b


# ── the comparison, with its own SE and MDE ─────────────────────────────────

def _mean_sd(vals: Sequence[float]) -> tuple[float, float | None]:
    m = sum(vals) / len(vals)
    if len(vals) < 2:
        return m, None
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return m, math.sqrt(var)


def compare(events: Sequence[Candidate], controls: Sequence[Candidate], *,
            arm: str, balance: Balance | None = None,
            n_event_clusters: int | None = None) -> ControlResult:
    """Event outcomes against control outcomes, as a difference (§18).

    `n_event_clusters` shrinks the effective sample when the events are not
    independent — five insiders filing on the same issuer in the same week are
    one event, and counting them as five is the single easiest way to
    manufacture significance in this dataset.
    """
    ev = [e.forward_return_pct for e in events
          if e.forward_return_pct is not None]
    cv = [c.forward_return_pct for c in controls
          if c.forward_return_pct is not None]
    if not ev or not cv:
        return ControlResult(arm, len(ev), len(cv), None, None, None, None,
                             None, None, balance,
                             "no outcomes on one side — UNMEASURED, which is "
                             "not the same as no difference")
    me, sde = _mean_sd(ev)
    mc, sdc = _mean_sd(cv)
    diff = me - mc
    if sde is None or sdc is None:
        return ControlResult(arm, len(ev), len(cv), me, mc, diff, None, None,
                             None, balance,
                             "a single observation on one side carries no "
                             "dispersion, so the difference has no SE")

    n_ev = float(n_event_clusters or len(ev))
    se = math.sqrt(sde ** 2 / max(n_ev, 1.0) + sdc ** 2 / len(cv))
    # The smallest difference detectable at 80% power given THIS standard
    # error. Written out rather than reusing `mde_mean` on a single sd, because
    # the two-sample SE already carries both sides.
    #
    # `None` when se is 0: a degenerate sample cannot support an MDE, and
    # "unmeasurable" is a different answer from "not detectable".
    mde = (PW.Z_ALPHA_TWO_SIDED_05 + PW.Z_POWER_80) * se if se > 0 else None

    reason = ""
    if len(cv) < MIN_CONTROLS_PER_EVENT:
        reason = (f"{len(cv)} control(s) — below the {MIN_CONTROLS_PER_EVENT} "
                  f"floor; this arm is UNPOWERED and its null means nothing")
    elif balance is not None and not balance.is_balanced:
        w = balance.worst
        reason = (f"controls are NOT balanced"
                  + (f" (worst: {w[0]} SMD {w[1]:+.2f} vs {MAX_ABS_SMD})"
                     if w else "")
                  + " — a mismatched control carries the authority of the word "
                    "'matched' and none of its meaning")
    return ControlResult(arm, len(ev), len(cv), me, mc, diff, se,
                         (diff / se if se else None), mde, balance, reason)


# ── the placebo family, run together ────────────────────────────────────────

def run_control_family(events: Sequence[Candidate], pool: Sequence[Candidate],
                       *, k: int = 5, rng=None,
                       n_event_clusters: int | None = None,
                       arms: Sequence[str] = PLACEBO_FAMILY
                       ) -> dict[str, ControlResult]:
    """Every declared arm at once, so a caller cannot run only the kind one.

    `rng` must be a seeded `numpy.random.Generator` (this repo forbids the
    legacy API). Required rather than defaulted: a shuffle placebo whose seed
    nobody recorded cannot be reproduced, and an irreproducible placebo is a
    number rather than a control.
    """
    if rng is None:
        raise ControlRefused(
            "run_control_family requires a seeded rng — an unreproducible "
            "shuffle placebo is a number, not a control "
            "(use np.random.default_rng(seed))")

    out: dict[str, ControlResult] = {}
    ev = list(events)

    if MATCHED_SECURITY in arms:
        matched: list[Candidate] = []
        unmatched = 0
        for e in ev:
            m = match_controls(e, pool, k=k)
            if not m:
                unmatched += 1
            matched.extend(m)
        bal = balance_of(ev, matched)
        r = compare(ev, matched, arm=MATCHED_SECURITY, balance=bal,
                    n_event_clusters=n_event_clusters)
        if unmatched:
            # Named, never silent. Events that found no control are events the
            # comparison does not cover, and a mean over the rest is a mean
            # over a subset chosen by data availability.
            r.reason = (f"{unmatched} of {len(ev)} event(s) found NO matched "
                        f"control and are absent from this comparison"
                        + (f"; {r.reason}" if r.reason else ""))
        out[MATCHED_SECURITY] = r

    if ACTOR_SHUFFLE in arms:
        # Same events, actor labels permuted. Kills actor-specific information
        # and keeps timing and selection — so a result that survives here was
        # never about WHO acted.
        actors = [e.actor_id for e in ev]
        perm = list(rng.permutation(len(actors))) if len(actors) > 1 else [0]
        shuffled = [Candidate(**{**e.__dict__,
                                 "actor_id": actors[int(perm[i])]})
                    for i, e in enumerate(ev)]
        out[ACTOR_SHUFFLE] = compare(ev, shuffled, arm=ACTOR_SHUFFLE,
                                     n_event_clusters=n_event_clusters)

    if DATE_SHUFFLE in arms:
        # Same securities, dates drawn from the pool. Kills timing, keeps
        # selection: if this arm matches the events, the library is a stock
        # screen with a date attached.
        by_ticker: dict[str, list[Candidate]] = {}
        for c in pool:
            by_ticker.setdefault(c.ticker, []).append(c)
        moved: list[Candidate] = []
        for e in ev:
            cands = [c for c in by_ticker.get(e.ticker, [])
                     if c.date != e.date and c.forward_return_pct is not None]
            if cands:
                moved.append(cands[int(rng.integers(0, len(cands)))])
        out[DATE_SHUFFLE] = compare(ev, moved, arm=DATE_SHUFFLE,
                                    n_event_clusters=n_event_clusters)

    if SIGN_FLIP in arms:
        # BUY events against SELL events from the same library. If sells carry
        # no information while buys do, that asymmetry is the finding; if both
        # "work", the effect is long-equity drift wearing a signal's clothes.
        buys = [e for e in ev if e.action_type == "BUY"]
        sells = [e for e in ev if e.action_type == "SELL"]
        out[SIGN_FLIP] = compare(buys, sells, arm=SIGN_FLIP,
                                 n_event_clusters=n_event_clusters)

    return out


def summarise(results: dict[str, ControlResult]) -> dict:
    """One verdict over the family. Interpretable arms only, and it says which.

    An event set that beats its matched control while ALSO beating its own
    actor-shuffle placebo has not been controlled — it has found something the
    shuffle could not destroy, which usually means the comparison is picking up
    the market rather than the actor.
    """
    interpretable = {k: r for k, r in results.items() if r.is_interpretable}
    detectable = {k: r for k, r in interpretable.items() if r.is_detectable}
    return {
        "arms_run": sorted(results),
        "arms_interpretable": sorted(interpretable),
        "arms_uninterpretable": {k: r.reason for k, r in results.items()
                                 if not r.is_interpretable},
        "arms_detectable": sorted(detectable),
        "verdict": (
            "NO INTERPRETABLE ARM — this event set cannot be evaluated yet, "
            "which is not the same as evaluating to nothing"
            if not interpretable else
            "no detectable difference on any interpretable arm"
            if not detectable else
            "detectable on: " + ", ".join(sorted(detectable))),
        "results": {k: r.as_dict() for k, r in results.items()},
        "citable": False,
    }
