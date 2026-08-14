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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


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

    @property
    def is_usable(self) -> bool:
        return self.n >= self.min_n and self.p_up is not None


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
    return BaseRate(
        state_key=bucket,
        n=int(len(sel)),
        p_up=float((sel > 0).mean()),
        mean_forward_return_pct=float(sel.mean()),
        median_forward_return_pct=float(np.median(sel)),
        horizon_days=horizon_days,
        min_n=min_n,
    )


def build_base_rates(vix_series, price_series, *, horizon_days: int = 63,
                     min_n: int = 30) -> dict[str, BaseRate]:
    """Every bucket at once, so a caller cannot compute only the flattering one."""
    buckets = ("vix<15", "vix15-20", "vix20-25", "vix25-35", "vix>=35")
    return {b: conditional_base_rate(b, vix_series, price_series,
                                     horizon_days=horizon_days, min_n=min_n)
            for b in buckets}


def disagrees_with_base_rate(p_up_believed: float, br: BaseRate,
                             margin: float = 0.10) -> bool | None:
    """Did the engine's directional view contradict the state's own history?

    `margin` keeps a base rate of 0.52 from convicting a forecast of 0.48. The
    question is whether the view was on the wrong side of a CLEAR historical
    tendency, not whether it differed from a coin flip by a rounding error.

    Returns None when the base rate is too thin to judge — which is a real
    answer and must not be read as "no disagreement".
    """
    if not br.is_usable or br.p_up is None:
        return None
    believed_up = p_up_believed > 0.5
    if br.p_up > 0.5 + margin:
        return not believed_up
    if br.p_up < 0.5 - margin:
        return believed_up
    return False
