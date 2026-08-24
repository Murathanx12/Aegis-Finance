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
#: The American approximation's exercise boundary degenerates as sigma -> 0
#: (kappa = 2b/sigma^2), so its inversion uses a higher floor. Separate from
#: IV_LO so the European path is unchanged.
AM_SIGMA_FLOOR = 5e-3
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


# ── American exercise (Bjerksund-Stensland 1993) ────────────────────────────
#
# WHY THIS IS HERE AND NOT A CAVEAT. `OPTIONS-CONVENTION-1` established that
# yfinance's implied-vol column discounts NOTHING (r=0, q=0 reproduces it to
# 0.0009), which is the whole 0.026 train/serve gap on the put-call residual.
# Inverting the prices ourselves under a declared r and q closes 80% of it and
# leaves ~0.005. Round 2 then tried to solve the rate from the cross-strike
# parity slope and OVERSHOT to +0.023 while dropping 44% of names -- the
# signature of a slope contaminated by a STRIKE-DEPENDENT term. American puts
# carry an early-exercise premium that grows with strike, which steepens
# (C - P) in K exactly that way.
#
# So the residue is not noise and not a vendor mystery: it is the one term this
# module declared it did not model. OptionMetrics inverts a binomial American
# model, so matching its convention means pricing American options.
#
# Bjerksund-Stensland rather than a binomial because it is closed form. A
# 200-step lattice inside a bisection is ~20k lattice builds per name and this
# runs over a daily universe. The approximation's error for near-ATM 30-day
# options is well under a tenth of a vol point -- an order below the quantity
# being measured -- and it is a LOWER bound on the true American price, so it
# cannot manufacture an early-exercise premium that is not there.


def _phi(spot: float, t: float, gamma: float, h: float, x: float,
         r: float, b: float, sigma: float, log_prefactor: float = 0.0
         ) -> float:
    """The Bjerksund-Stensland phi, evaluated in LOG SPACE.

    The textbook form is `exp(lam) * S**gamma * (N(d) - (X/S)**kappa * N(d2))`,
    and it overflows in float as written: kappa = 2b/sigma^2 reaches ~3000 at
    a 0.5% vol, so `(X/S)**kappa` blows up while `N(d2)` collapses to zero and
    their product -- which is small and finite -- is never formed. The live
    pass hit this on its first name, because the inversion's bisection
    necessarily walks through tiny sigmas.

    Each factor is therefore accumulated as a logarithm and exponentiated once.
    """
    v2 = sigma * sigma
    lam = (-r + gamma * b + 0.5 * gamma * (gamma - 1.0) * v2) * t
    kappa = 2.0 * b / v2 + (2.0 * gamma - 1.0)
    sq = sigma * math.sqrt(t)
    d = -(math.log(spot / h) + (b + (gamma - 0.5) * v2) * t) / sq
    d2 = d - 2.0 * math.log(x / spot) / sq

    # log(prefactor * exp(lam) * S**gamma). The prefactor is folded in HERE
    # rather than multiplied afterwards because the two beta-power terms are
    # always scaled by alpha = (X - K) * X**-beta, and beta reaches ~2265 for
    # an American PUT at a 0.5% vol: S**beta overflows on its own while
    # alpha * S**beta = (X - K) * (S/X)**beta is a perfectly ordinary number.
    # Forming the two factors separately is what blew up; forming the product's
    # logarithm does not.
    head = log_prefactor + lam + gamma * math.log(spot)
    n_d, n_d2 = _norm_cdf(d), _norm_cdf(d2)

    def _safe_exp(z):
        return math.exp(z) if z < 700.0 else math.inf

    first = _safe_exp(head + math.log(n_d)) if n_d > 0.0 else 0.0
    second = (_safe_exp(head + kappa * math.log(x / spot) + math.log(n_d2))
              if n_d2 > 0.0 else 0.0)
    if first == math.inf or second == math.inf:
        raise _PhiDegenerate(f"phi overflowed at sigma={sigma:.5f}")
    return first - second


class _PhiDegenerate(ArithmeticError):
    """The approximation's exercise boundary is not evaluable at this sigma.

    Private and numerical, not a domain refusal: `american_call` answers with
    the European price, which is a hard LOWER bound, so the fallback can never
    invent an early-exercise premium. Counted, so a silent epidemic of it is
    visible rather than inferred."""


#: How often `_phi` degenerated. A numerical fallback nobody counts is
#: indistinguishable from one that never fires.
PHI_FALLBACKS = {"n": 0}


def american_call(spot: float, strike: float, t: float, r: float, b: float,
                  sigma: float) -> float:
    """Bjerksund-Stensland 1993. `b` is the cost of carry (r - q)."""
    if t <= 0 or sigma <= 0:
        return max(spot - strike, 0.0)
    if sigma < AM_SIGMA_FLOOR:
        # kappa = 2b/sigma^2 diverges as sigma -> 0 and (x/spot)**kappa
        # overflows. Below this floor the early-exercise boundary is not a
        # meaningful object anyway: the option is worth its European value to
        # within far less than a basis point. Found by the bisection walking
        # into IV_LO = 1e-4 on the first live pass.
        return max(bsm_price(spot, strike, t, r, r - b, sigma, True),
                   spot - strike, 0.0)
    if b >= r:
        # No early exercise is ever optimal, so the American call IS European.
        return bsm_price(spot, strike, t, r, r - b, sigma, True)
    v2 = sigma * sigma
    beta = (0.5 - b / v2) + math.sqrt((b / v2 - 0.5) ** 2 + 2.0 * r / v2)
    if beta <= 1.0 + 1e-12:
        return bsm_price(spot, strike, t, r, r - b, sigma, True)
    b_inf = beta / (beta - 1.0) * strike
    b_zero = max(strike, r / (r - b) * strike) if r != b else strike
    if b_inf <= b_zero:
        return bsm_price(spot, strike, t, r, r - b, sigma, True)
    h_t = -(b * t + 2.0 * sigma * math.sqrt(t)) * b_zero / (b_inf - b_zero)
    x = b_zero + (b_inf - b_zero) * (1.0 - math.exp(h_t))
    if spot >= x:
        return spot - strike
    if x <= strike:
        # The trigger price has collapsed to at or below the strike, so the
        # approximation's alpha is non-positive and its logarithm is undefined.
        # Nothing to exercise early into: answer with the European price, which
        # is the hard lower bound this whole branch is bounded by.
        return max(bsm_price(spot, strike, t, r, r - b, sigma, True),
                   spot - strike, 0.0)
    # alpha = (x - strike) * x**-beta, carried as a LOGARITHM so it can be
    # folded into the beta-power terms before either factor is formed.
    log_alpha = math.log(x - strike) - beta * math.log(x)
    try:
        val = ((x - strike) * (spot / x) ** beta
               - _phi(spot, t, beta, x, x, r, b, sigma, log_alpha)
               + _phi(spot, t, 1.0, x, x, r, b, sigma)
               - _phi(spot, t, 1.0, strike, x, r, b, sigma)
               - strike * _phi(spot, t, 0.0, x, x, r, b, sigma)
               + strike * _phi(spot, t, 0.0, strike, x, r, b, sigma))
    except (_PhiDegenerate, OverflowError, ValueError):
        PHI_FALLBACKS["n"] += 1
        val = -math.inf
    # The approximation is a lower bound; never let it fall under European or
    # under intrinsic, both of which are hard floors.
    euro = bsm_price(spot, strike, t, r, r - b, sigma, True)
    return max(val, euro, spot - strike, 0.0)


def american_price(spot: float, strike: float, t: float, r: float, q: float,
                   sigma: float, is_call: bool) -> float:
    """American option price. The put uses the standard transformation
    P(S,K,T,r,b) = C(K,S,T,r-b,-b), which is exact, not another approximation."""
    b = r - q
    if is_call:
        return american_call(spot, strike, t, r, b, sigma)
    return american_call(strike, spot, t, r - b, -b, sigma)


def implied_vol_american(price: float, spot: float, strike: float, t: float,
                         r: float, q: float, is_call: bool) -> Optional[float]:
    if not (price and price > 0) or spot <= 0 or strike <= 0 or t <= 0:
        return None
    lo_p = american_price(spot, strike, t, r, q, AM_SIGMA_FLOOR, is_call)
    hi_p = american_price(spot, strike, t, r, q, IV_HI, is_call)
    if price <= lo_p or price >= hi_p:
        return None
    lo, hi = AM_SIGMA_FLOOR, IV_HI
    for _ in range(BISECT_ITERS):
        mid = 0.5 * (lo + hi)
        pm = american_price(spot, strike, t, r, q, mid, is_call)
        if abs(pm - price) < TOL:
            return mid
        if pm > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


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
