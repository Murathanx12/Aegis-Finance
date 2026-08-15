"""Was the forecast unlucky, or wrong in a way our own data already knew?

THE DISTINCTION THE FIRST TAXONOMY COLLAPSED
============================================
The first run of dataset zero classified all five de-risking failures as
`forecast_failure` — and that was partly an artefact. A SELL followed by a rally
can barely classify as anything else once "forecast failure" is defined as
"expected down, went up". The label was true and useless.

Murat's directive is more precise than the label. It says:

    "Stress detection itself was correct. The failure came from mapping high
     stress -> zero exposure."

Which separates three layers the taxonomy had squashed into two:

    PERCEPTION   what is the state of the world?      VIX 57 — CORRECT, measured
    INFERENCE    what follows from that state?        "expect down" — the error
    ACTION       what do we do about it?              sell

The engine's perception was not wrong. VIX really was above 25. What was wrong
was the INFERENCE from that state to an expected return — and unlike bad luck,
that is learnable, because the state's own historical base rate disagreed with
it at the time.

SO THE TEST IS AGAINST THE BASE RATE, NOT AGAINST THE OUTCOME
=============================================================
One episode's outcome cannot tell you whether a forecast was reasonable. The
conditional base rate can:

  * the engine expected DOWN in a state where similar states were followed by UP
    two thirds of the time -> the inference contradicted the evidence available
    before the fact. `state_to_forecast_failure`: systematic and fixable.

  * the engine expected DOWN in a state where similar states really were
    followed by DOWN, and this one went up -> an unlucky draw.
    `forecast_failure`: nothing to fix, and pretending otherwise is how a
    project fits noise.

THE BASE RATE MUST NOT COME FROM THE EPISODES BEING JUDGED
==========================================================
`conditional_base_rate` is computed from long price history, not from the
handful of decisions under examination. Judging five sells against a base rate
estimated from those same five sells would be circular, and the circularity
would be invisible — the numbers would look fine.

It is still Gym material. A base rate computed over history this project has
studied for months is not a clean out-of-sample quantity, and R8 says so.

AND `n` IS NOT `n_effective` (G2, 2026-08-15)
=============================================
The first version of this table printed `n=353` for VIX>=35 and `min_n=30`
passed comfortably. Those are 353 daily observations of a 63-day window
covering 19 distinct episodes: an effective sample of **5.6**. Every row now
carries `power` -- n_obs, n_episodes, n_effective, and the 80%-power MDE -- and
`assess` reports how strong the disagreement evidence actually is instead of
returning a bare True that reads identically at n_eff 5.6 and n_eff 44.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from backend.services.research_gym import power as PW

#: Evidence strengths for "the state's own history contradicted the view".
#: The middle one is the honest home for most of this table: the point estimate
#: disagrees, and the sample cannot establish it.
ESTABLISHED = "established"      # CI at n_effective excludes a coin flip
SUGGESTIVE = "suggestive"        # point estimate disagrees, n_eff cannot confirm
TOO_THIN = "too_thin"            # nothing can be said either way


@dataclass(frozen=True)
class BaseRate:
    """What historically followed states like this one."""
    state_key: str
    n: int
    p_up: float | None
    mean_forward_return_pct: float | None
    median_forward_return_pct: float | None
    horizon_days: int
    #: Below this the base rate is not an estimate of anything and attribution
    #: must decline to use it rather than lean on eight observations.
    min_n: int = 30
    #: Standard deviation of the forward returns in this bucket. Needed for the
    #: MDE; a row without it can state a mean it cannot bound.
    sd_forward_return_pct: float | None = None
    power: PW.Power | None = None

    @property
    def is_usable(self) -> bool:
        return self.n >= self.min_n and self.p_up is not None

    @property
    def n_effective(self) -> float | None:
        return None if self.power is None else self.power.n_effective

    def as_dict(self) -> dict:
        return {
            "state_key": self.state_key,
            "n": self.n,
            "p_up": self.p_up,
            "mean_forward_return_pct": self.mean_forward_return_pct,
            "median_forward_return_pct": self.median_forward_return_pct,
            "sd_forward_return_pct": self.sd_forward_return_pct,
            "horizon_days": self.horizon_days,
            # SS19: a row without an MDE is not publishable, including in the Gym.
            "power": None if self.power is None else self.power.as_dict(),
        }


def vix_bucket(vix: float) -> str:
    """Coarse, fixed, declared in advance.

    Deliberately not tuned. A bucketing chosen after looking at which cut makes
    the finding strongest is a search, and an unledgered one. These are the
    conventional levels — calm, normal, elevated, stressed, panic — and they are
    frozen here so the conditioning cannot quietly become the result.
    """
    v = float(vix)
    if v < 15:
        return "vix<15"
    if v < 20:
        return "vix15-20"
    if v < 25:
        return "vix20-25"
    if v < 35:
        return "vix25-35"
    return "vix>=35"


def base_rate_from_mask(state_key: str, mask, price_series, *,
                        horizon_days: int = 63, min_n: int = 30) -> BaseRate:
    """The same measurement for an arbitrary boolean condition on the dates.

    Exists so a CONTROL can be built from exactly the machinery that produced
    the finding. A control computed by different code is a second experiment,
    and the difference between the two is then partly the code.
    """
    import numpy as np

    px = price_series.dropna()
    common = px.index.intersection(mask.index)
    px, m = px.loc[common], mask.loc[common].astype(bool)
    if len(px) <= horizon_days + 1:
        return BaseRate(state_key, 0, None, None, None, horizon_days, min_n)
    fwd = (px.shift(-horizon_days) / px - 1.0) * 100.0
    sel = fwd[m].dropna()
    if sel.empty:
        return BaseRate(state_key, 0, None, None, None, horizon_days, min_n)
    pos = [int(px.index.get_loc(ts)) for ts in sel.index]
    sd = float(sel.std(ddof=1)) if len(sel) > 1 else None
    return BaseRate(
        state_key=state_key, n=int(len(sel)), p_up=float((sel > 0).mean()),
        mean_forward_return_pct=float(sel.mean()),
        median_forward_return_pct=float(np.median(sel)),
        horizon_days=horizon_days, min_n=min_n, sd_forward_return_pct=sd,
        power=PW.power_for(n_obs=int(len(sel)), horizon_days=horizon_days,
                           sd=sd, n_episodes=PW.count_episodes(pos)))


def drawdown_series(price_series, lookback: int = 252):
    """Percent below the trailing `lookback`-day high, as a negative number."""
    px = price_series.dropna()
    peak = px.rolling(lookback, min_periods=20).max()
    return (px / peak - 1.0) * 100.0


def drawdown_matched_control(vix_series, price_series, *,
                             vix_threshold: float = 35.0,
                             drawdown_pct: float = -15.0,
                             horizon_days: int = 63) -> dict[str, BaseRate]:
    """Does extreme VIX say anything the drawdown had not already said?

    THE CONFOUND THIS MEASURES, NAMED RATHER THAN NOTED
    ---------------------------------------------------
    VIX>=35 essentially never occurs except after a large fall. So the +6.97%
    that follows it is partly rebound from a depressed price and only partly
    information carried by the volatility itself. A table that reports the
    +6.97% without this split invites the reading that the VIX level is the
    signal, when the drawdown alone may be doing all of the work.

    Three cells, one condition apart:

      deep_drawdown_only  fell hard, VIX stayed below the threshold  <- CONTROL
      deep_drawdown_and_panic   fell hard AND VIX above it
      panic_only          VIX above it without the fall (usually rare)

    If the first two are indistinguishable, the panic reading adds nothing to
    the drawdown, and any re-entry mechanism built on VIX is really a
    buy-the-dip rule wearing a volatility costume.
    """
    px = price_series.dropna()
    vx = vix_series.dropna()
    common = px.index.intersection(vx.index)
    px, vx = px.loc[common], vx.loc[common]
    dd = drawdown_series(px).reindex(px.index)

    panic = vx >= vix_threshold
    deep = dd <= drawdown_pct
    cells = {
        "deep_drawdown_only": (deep & ~panic),
        "deep_drawdown_and_panic": (deep & panic),
        "panic_only": (panic & ~deep),
    }
    return {k: base_rate_from_mask(k, m.fillna(False), px,
                                   horizon_days=horizon_days)
            for k, m in cells.items()}


def conditional_base_rate(bucket: str, vix_series, price_series, *,
                          horizon_days: int = 63,
                          min_n: int = 30) -> BaseRate:
    """P(up) and mean forward return following every historical day in `bucket`.

    Uses long history, deliberately overlapping. Overlapping windows inflate
    apparent significance, which is why this returns a base rate and never a
    p-value: it is here to say "what usually happened", not to test anything.
    """
    import numpy as np
    import pandas as pd

    px = price_series.dropna()
    vx = vix_series.dropna()
    common = px.index.intersection(vx.index)
    px, vx = px.loc[common], vx.loc[common]
    if len(px) <= horizon_days + 1:
        return BaseRate(bucket, 0, None, None, None, horizon_days, min_n)

    fwd = (px.shift(-horizon_days) / px - 1.0) * 100.0
    mask = pd.Series([vix_bucket(v) == bucket for v in vx], index=vx.index)
    sel = fwd[mask].dropna()
    if sel.empty:
        return BaseRate(bucket, 0, None, None, None, horizon_days, min_n)

    # Integer positions in the underlying daily series, so `count_episodes` can
    # see that sixty consecutive days above VIX 35 are one crisis and not sixty
    # draws. Using dates here would work too; positions keep it calendar-free.
    pos = [int(px.index.get_loc(ts)) for ts in sel.index]
    sd = float(sel.std(ddof=1)) if len(sel) > 1 else None
    return BaseRate(
        state_key=bucket,
        n=int(len(sel)),
        p_up=float((sel > 0).mean()),
        mean_forward_return_pct=float(sel.mean()),
        median_forward_return_pct=float(np.median(sel)),
        horizon_days=horizon_days,
        min_n=min_n,
        sd_forward_return_pct=sd,
        power=PW.power_for(n_obs=int(len(sel)), horizon_days=horizon_days,
                           sd=sd, n_episodes=PW.count_episodes(pos)),
    )


def build_base_rates(vix_series, price_series, *, horizon_days: int = 63,
                     min_n: int = 30) -> dict[str, BaseRate]:
    """Every bucket at once, so a caller cannot compute only the flattering one."""
    buckets = ("vix<15", "vix15-20", "vix20-25", "vix25-35", "vix>=35")
    return {b: conditional_base_rate(b, vix_series, price_series,
                                     horizon_days=horizon_days, min_n=min_n)
            for b in buckets}


@dataclass(frozen=True)
class BucketDifference:
    """One bucket's mean forward return minus another's, with its own SE.

    SS18 in this project's canon: *an agreement claim is tested as a DIFFERENCE
    with its own SE.* The U-shape is exactly such a claim -- it says the middle
    bucket is LOWER THAN the extremes -- and nothing in the first version of
    this table tested it that way. Five means were printed, the eye supplied
    the curve, and each individual mean turned out to sit below its own MDE.

    Two means each too weak to be distinguished from zero can still differ from
    each other, so this is not a formality; it is the only test the shape claim
    has ever been given.
    """
    a_key: str
    b_key: str
    diff_pct: float
    se_pct: float | None
    t_stat: float | None
    mde_pct: float | None
    n_effective_a: float | None
    n_effective_b: float | None

    @property
    def is_detectable(self) -> bool | None:
        if self.mde_pct is None:
            return None
        return abs(self.diff_pct) >= self.mde_pct

    def as_dict(self) -> dict:
        return {"a": self.a_key, "b": self.b_key,
                "diff_pct": round(self.diff_pct, 3),
                "se_pct": None if self.se_pct is None else round(self.se_pct, 3),
                "t_stat": None if self.t_stat is None else round(self.t_stat, 3),
                "mde_pct": (None if self.mde_pct is None
                            else round(self.mde_pct, 3)),
                "n_effective_a": self.n_effective_a,
                "n_effective_b": self.n_effective_b,
                "detectable": self.is_detectable}


def bucket_difference(a: BaseRate, b: BaseRate) -> BucketDifference:
    """`a.mean - b.mean`, with the standard error the comparison actually has.

    Both standard errors are taken at n_EFFECTIVE, not at n. Using the raw
    daily counts here would shrink the SE by roughly sqrt(63) and turn a shape
    nobody has established into a significant one.
    """
    import math

    da = None if a.mean_forward_return_pct is None else a.mean_forward_return_pct
    db = None if b.mean_forward_return_pct is None else b.mean_forward_return_pct
    if da is None or db is None:
        return BucketDifference(a.state_key, b.state_key, float("nan"), None,
                                None, None, a.n_effective, b.n_effective)
    diff = da - db
    na, nb = a.n_effective, b.n_effective
    if (a.sd_forward_return_pct is None or b.sd_forward_return_pct is None
            or na is None or nb is None or na < 2 or nb < 2):
        return BucketDifference(a.state_key, b.state_key, diff, None, None,
                                None, na, nb)
    var = (a.sd_forward_return_pct ** 2) / na + (b.sd_forward_return_pct ** 2) / nb
    se = math.sqrt(var)
    return BucketDifference(
        a_key=a.state_key, b_key=b.state_key, diff_pct=diff, se_pct=se,
        t_stat=(diff / se if se > 0 else None),
        mde_pct=(PW.Z_ALPHA_TWO_SIDED_05 + PW.Z_POWER_80) * se,
        n_effective_a=na, n_effective_b=nb)


@dataclass(frozen=True)
class Assessment:
    """Whether the view contradicted the state's history, AND how firmly."""
    disagrees: bool | None
    strength: str
    p_up_believed: float
    p_up_historical: float | None
    n_effective: float | None
    mde_proportion: float | None
    detail: str


def assess(p_up_believed: float, br: BaseRate,
           margin: float = 0.10) -> Assessment:
    """Grade the disagreement instead of asserting it.

    THE DEFECT THIS REPLACES
    ------------------------
    The previous version returned a bare `True` whenever the historical P(up)
    sat more than `margin` on the other side of a coin flip. That answer read
    identically whether the bucket held 44 effective observations or 5.6 -- so
    an inference convicted on the VIX>=35 row, whose whole sample is about six
    independent crises, looked exactly as settled as one convicted on 2,785
    ordinary days.

    Now the same question is answered in three grades:

      ESTABLISHED  the historical tendency is distinguishable from a coin flip
                   at the EFFECTIVE sample size -- the disagreement is a
                   measurement.
      SUGGESTIVE   the point estimate disagrees, and this bucket does not have
                   the independent observations to establish it. Still the
                   right DIRECTION to record; not a number to act on.
      TOO_THIN     nothing can be said either way.

    Kept as a direction plus a grade rather than collapsed to "no finding",
    because a bucket that cannot reach significance is not thereby evidence of
    agreement, and treating it as such would be the same error upside down.
    """
    def _mk(disagrees, strength, detail):
        return Assessment(disagrees=disagrees, strength=strength,
                          p_up_believed=float(p_up_believed),
                          p_up_historical=br.p_up,
                          n_effective=br.n_effective,
                          mde_proportion=(None if br.power is None
                                          else br.power.mde_proportion),
                          detail=detail)

    if not br.is_usable or br.p_up is None:
        return _mk(None, TOO_THIN,
                   f"base rate for {br.state_key} has n={br.n} (min {br.min_n})"
                   f" — too thin to judge, which is NOT the same as agreement")

    believed_up = p_up_believed > 0.5
    if br.p_up > 0.5 + margin:
        disagrees = not believed_up
    elif br.p_up < 0.5 - margin:
        disagrees = believed_up
    else:
        return _mk(False, ESTABLISHED,
                   f"P(up | {br.state_key}) = {br.p_up:.2f} is within "
                   f"{margin:.2f} of a coin flip; it convicts nobody")

    mde = None if br.power is None else br.power.mde_proportion
    n_eff = br.n_effective
    if mde is None:
        return _mk(disagrees, SUGGESTIVE,
                   f"P(up | {br.state_key}) = {br.p_up:.2f} vs believed "
                   f"{p_up_believed:.2f}; this row carries no MDE, so the "
                   f"strength of the disagreement is unknown")
    if abs(br.p_up - 0.5) >= mde:
        return _mk(disagrees, ESTABLISHED,
                   f"P(up | {br.state_key}) = {br.p_up:.2f} departs from a "
                   f"coin flip by {abs(br.p_up - 0.5):.2f}, at or above the "
                   f"80%-power MDE of {mde:.2f} for n_effective "
                   f"{n_eff:.1f}")
    return _mk(disagrees, SUGGESTIVE,
               f"P(up | {br.state_key}) = {br.p_up:.2f} departs from a coin "
               f"flip by {abs(br.p_up - 0.5):.2f}, BELOW the 80%-power MDE of "
               f"{mde:.2f} for n_effective {n_eff:.1f} ({br.n} overlapping "
               f"daily observations). The direction is recorded; the sample "
               f"cannot establish it")


def disagrees_with_base_rate(p_up_believed: float, br: BaseRate,
                             margin: float = 0.10) -> bool | None:
    """Did the engine's directional view contradict the state's own history?

    Thin wrapper over `assess` kept because the tri-state answer is what the
    attribution layer branches on. Callers that need to know HOW FIRMLY should
    call `assess` — a bare True here does not mean the disagreement is
    established, and since G2 it usually is not.
    """
    return assess(p_up_believed, br, margin=margin).disagrees
