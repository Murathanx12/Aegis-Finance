"""Implied volatility under a DECLARED convention, instead of the vendor's.

WHY THIS EXISTS
===============
`EVENT_RESPONSE_v1` is fit on OptionMetrics `stdopd` and would be served on
yfinance chains. Three of its four option features transfer. One does not:

    iv_put_minus_call_30d   live median -0.0237   stdopd median +0.0019
                            live 25% positive     stdopd 55% positive

A gradient-boosted tree splits on absolute thresholds, so a 2.6-vol-point
offset does not degrade gracefully — it moves every split that touches the
column. Two routes were tried and are spent: a matched-strike residual (moved
the median -0.0254 -> -0.0237) and a cross-sectional rank (`AMENDMENT-2`: each
candidate passed exactly one horizon, which is how you get two different models
depending on which horizon someone wrote down first).

THE ROUTE NEITHER OF THEM TOOK
==============================
Both arms kept reading yfinance's `impliedVolatility` COLUMN. That column is
the output of Yahoo's pricer under Yahoo's undisclosed assumptions about the
risk-free rate, the dividend, the exercise style, and which price to invert
(last trade or mid). OptionMetrics inverts a binomial American model against
the bid/ask MIDPOINT with its own zero curve and projected discrete dividends.

`iv_put_minus_call_30d` is the ONE feature of the four where that matters most,
and the reason is structural rather than bad luck. By put-call parity a call and
a put at the same strike and expiry are linked, so a same-strike IV residual is
almost entirely a statement about the pricer's r and q — it is a DIFFERENCE, so
the level of volatility cancels and the convention error does not. The other
three features are levels or same-side slopes, where a shared bias largely
cancels or is small relative to the quantity.

That is why the matched-strike fix barely moved the number: it corrected which
strikes were compared while leaving the disputed quantity — the vol implied by
somebody else's model — completely intact.

So: invert the prices ourselves, under a convention we declare and can match to
the research side. The residual then measures what the feature is supposed to
measure (the parity violation from borrow cost and hard-to-borrow demand)
instead of the gap between two vendors' solvers.

WHAT IS DECLARED, AND WHAT IS NOT MODELLED
==========================================
DECLARED: continuous risk-free rate from the Treasury curve at the matching
tenor; continuous dividend yield; European Black-Scholes-Merton; inversion
against the bid/ask midpoint, with a recorded fallback to the last trade.

NOT MODELLED, and named rather than hidden: American early exercise, and
discrete rather than continuous dividends. Both are real differences from
`stdopd`'s binomial. They are second-order for 30-day near-ATM options on
large caps and they bias the PUT leg upward, so if a residual gap survives
this module in the positive direction, early exercise is the next suspect and
this docstring is where that lead is recorded.

NOTHING HERE IS A CLAIM. This is a servability instrument.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

#: Inversion bounds. A quoted price outside the no-arbitrage band, or one that
#: implies a vol beyond these, is refused rather than clamped — a clamped
#: 500-vol print is indistinguishable from a real one downstream.
IV_LO, IV_HI = 1e-4, 5.0
BISECT_ITERS = 100
TOL = 1e-8

#: Continuous-compounding conversion for a quoted (annualised, simple) yield.
#: Named because a 4% quote treated as continuous is a ~0.08% rate error, which
#: is well inside the noise here but is exactly the sort of thing that is
#: assumed rather than written down.


@dataclass(frozen=True)
class ImpliedPoint:
    strike: float
    days: float
    iv_call: Optional[float]
    iv_put: Optional[float]
    price_basis: str          # "mid" | "last" | "mixed"
    r: float
    q: float


def to_continuous(simple_annual_rate: float) -> float:
    """A quoted annual yield -> the continuously compounded equivalent."""
    return math.log1p(float(simple_annual_rate))


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bsm_price(spot: float, strike: float, t: float, r: float, q: float,
              sigma: float, is_call: bool) -> float:
    """Black-Scholes-Merton with a continuous dividend yield."""
    if t <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        fwd = spot * math.exp(-q * max(t, 0.0)) - strike * math.exp(-r * max(t, 0.0))
        return max(fwd, 0.0) if is_call else max(-fwd, 0.0)
    sq = sigma * math.sqrt(t)
    d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma * sigma) * t) / sq
    d2 = d1 - sq
    df_s = spot * math.exp(-q * t)
    df_k = strike * math.exp(-r * t)
    if is_call:
        return df_s * _norm_cdf(d1) - df_k * _norm_cdf(d2)
    return df_k * _norm_cdf(-d2) - df_s * _norm_cdf(-d1)


def implied_vol(price: float, spot: float, strike: float, t: float,
                r: float, q: float, is_call: bool) -> Optional[float]:
    """Invert `bsm_price` by bisection. `None` when the quote is unpriceable.

    Bisection rather than Newton deliberately: vega collapses for deep options
    and a Newton step there walks off into a nonsense root. This is called a
    few thousand times a day, so the extra iterations cost nothing that matters.
    """
    if not (price and price > 0) or spot <= 0 or strike <= 0 or t <= 0:
        return None
    lo_p = bsm_price(spot, strike, t, r, q, IV_LO, is_call)
    hi_p = bsm_price(spot, strike, t, r, q, IV_HI, is_call)
    if price <= lo_p or price >= hi_p:
        # Below intrinsic (stale/crossed quote) or above the 500-vol price.
        # Both are refusals: a clamp here would manufacture a boundary value
        # that reads downstream exactly like a measured one.
        return None
    lo, hi = IV_LO, IV_HI
    for _ in range(BISECT_ITERS):
        mid = 0.5 * (lo + hi)
        pm = bsm_price(spot, strike, t, r, q, mid, is_call)
        if abs(pm - price) < TOL:
            return mid
        if pm > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def quote_price(row) -> tuple[Optional[float], str]:
    """Mid of bid/ask, falling back to the last trade — and SAYING which.

    OptionMetrics inverts the midpoint. The last trade can be hours old and
    off-market, and on a thin strike the two differ by more than the entire
    residual being measured, so which one was used is recorded on every point
    rather than assumed.
    """
    def _f(k):
        try:
            v = float(row[k])
            return v if v > 0 and math.isfinite(v) else None
        except Exception:                                    # noqa: BLE001
            return None

    bid, ask = _f("bid"), _f("ask")
    if bid is not None and ask is not None and ask >= bid:
        return 0.5 * (bid + ask), "mid"
    last = _f("lastPrice")
    if last is not None:
        return last, "last"
    return None, "none"


def imply_matched_strike(calls, puts, spot: float, days: float,
                         r: float, q: float,
                         band: float = 0.06) -> Optional[ImpliedPoint]:
    """Call and put IV at the SAME strike, both implied under OUR convention.

    The strike is the listed one nearest spot that carries a usable quote on
    both sides. Returning `None` rather than a one-sided point is deliberate:
    a residual computed from two different strikes is a different feature.
    """
    if calls is None or puts is None:
        return None
    if not hasattr(calls, "empty") or calls.empty or puts.empty:
        return None
    t = float(days) / 365.0
    if t <= 0:
        return None

    cbys = {float(row["strike"]): row for _, row in calls.iterrows()}
    pbys = {float(row["strike"]): row for _, row in puts.iterrows()}
    common = sorted(set(cbys) & set(pbys))
    if not common:
        return None

    for k in sorted(common, key=lambda x: abs(x - spot)):
        if abs(k - spot) > spot * band:
            break
        pc, bc = quote_price(cbys[k])
        pp, bp = quote_price(pbys[k])
        if pc is None or pp is None:
            continue
        ivc = implied_vol(pc, spot, k, t, r, q, True)
        ivp = implied_vol(pp, spot, k, t, r, q, False)
        if ivc is None or ivp is None:
            continue
        return ImpliedPoint(strike=k, days=float(days), iv_call=ivc,
                            iv_put=ivp,
                            price_basis=(bc if bc == bp else "mixed"),
                            r=r, q=q)
    return None
