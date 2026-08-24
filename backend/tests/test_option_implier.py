"""Inverting option prices under a DECLARED convention.

WHAT THIS MODULE IS FOR, in one line: `OPTIONS-CONVENTION-1` measured that
yfinance's `impliedVolatility` column is computed with **no discounting and no
dividend** — r = 0, q = 0 reproduces the vendor's put-call residual to 0.0009 —
and that this accounts for the entire 0.026 train/serve gap that blocked
`EVENT_RESPONSE_v1`. So the numbers below are not decoration: they are what
stops the feature quietly going back to reading somebody else's model.

The properties worth pinning are the ones a wrong implementation would still
pass a smoke test on:

  * round-trip: price -> IV -> price returns the price;
  * put-call parity holds for the EUROPEAN prices, so a same-strike residual is
    zero when the convention is right — which is exactly why the residual is
    such a sensitive probe of the convention being wrong;
  * the American price is never below the European one, so the approximation
    cannot manufacture an early-exercise premium;
  * an unpriceable quote returns None rather than a clamped boundary value;
  * `_phi` does not overflow at small sigma, which the live pass hit on its
    first name.
"""

from __future__ import annotations

import math

import pytest

from backend.services import option_implier as oi


# ── the inversion ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("is_call", [True, False])
@pytest.mark.parametrize("sigma", [0.12, 0.30, 0.85])
def test_round_trip_price_to_iv_to_price(is_call, sigma):
    s, k, t, r, q = 100.0, 105.0, 30 / 365, 0.0363, 0.008
    px = oi.bsm_price(s, k, t, r, q, sigma, is_call)
    got = oi.implied_vol(px, s, k, t, r, q, is_call)
    assert got == pytest.approx(sigma, abs=1e-5)


def test_european_prices_satisfy_put_call_parity():
    """C - P = S e^-qT - K e^-rT. This identity is the reason the same-strike
    IV residual is a near-pure statement about r and q: get them wrong and the
    residual absorbs the whole error, because the vol level cancels."""
    s, k, t, r, q, sig = 100.0, 100.0, 30 / 365, 0.0363, 0.008, 0.28
    c = oi.bsm_price(s, k, t, r, q, sig, True)
    p = oi.bsm_price(s, k, t, r, q, sig, False)
    assert c - p == pytest.approx(s * math.exp(-q * t) - k * math.exp(-r * t),
                                  abs=1e-9)


def test_the_same_strike_residual_is_zero_under_the_RIGHT_convention():
    """And nonzero under the wrong one, by an amount that is the convention
    error. Measured live: reading the vendor's column instead costs 0.026."""
    s, k, t, r, q, sig = 100.0, 100.0, 30 / 365, 0.0363, 0.008, 0.28
    c = oi.bsm_price(s, k, t, r, q, sig, True)
    p = oi.bsm_price(s, k, t, r, q, sig, False)

    right = (oi.implied_vol(p, s, k, t, r, q, False)
             - oi.implied_vol(c, s, k, t, r, q, True))
    assert right == pytest.approx(0.0, abs=1e-5)

    wrong = (oi.implied_vol(p, s, k, t, 0.0, 0.0, False)
             - oi.implied_vol(c, s, k, t, 0.0, 0.0, True))
    assert wrong < -0.01, "discounting nothing must show up as a NEGATIVE residual"


def test_an_unpriceable_quote_returns_None_not_a_clamp():
    """A clamped 500-vol print reads downstream exactly like a measured one."""
    s, k, t = 100.0, 100.0, 30 / 365
    below_intrinsic = 0.0001
    assert oi.implied_vol(below_intrinsic, s, k, t, 0.04, 0.0, True) is None
    assert oi.implied_vol(0.0, s, k, t, 0.04, 0.0, True) is None
    # A put cannot be worth more than the discounted strike. 50.0 is NOT such a
    # case -- it is a perfectly priceable 473% vol, which is what the first
    # version of this test got wrong.
    assert oi.implied_vol(50.0, s, k, t, 0.04, 0.0, False) is not None
    assert oi.implied_vol(99.9, s, k, t, 0.04, 0.0, False) is None


def test_the_price_basis_is_recorded_not_assumed():
    """OptionMetrics inverts the MIDPOINT. On a thin strike the last trade and
    the mid differ by more than the whole residual being measured, so which one
    was used has to travel with the number."""
    assert oi.quote_price({"bid": 1.0, "ask": 1.2, "lastPrice": 3.0}) == (
        1.1, "mid")
    assert oi.quote_price({"bid": 0, "ask": 0, "lastPrice": 3.0}) == (
        3.0, "last")
    assert oi.quote_price({"bid": 0, "ask": 0, "lastPrice": 0})[1] == "none"


# ── American exercise ───────────────────────────────────────────────────────


@pytest.mark.parametrize("q", [0.0, 0.008, 0.04])
@pytest.mark.parametrize("is_call", [True, False])
def test_american_is_never_below_european(q, is_call):
    """The approximation is a LOWER bound, which is what makes the numerical
    fallback safe: it can fail to find a premium, never invent one."""
    s, k, t, r, sig = 100.0, 100.0, 30 / 365, 0.0363, 0.30
    a = oi.american_price(s, k, t, r, q, sig, is_call)
    e = oi.bsm_price(s, k, t, r, q, sig, is_call)
    assert a >= e - 1e-9


def test_an_american_call_on_a_non_dividend_payer_is_european():
    """The textbook result, and a check that the carry branch is wired the
    right way round: with q = 0 early exercise is never optimal."""
    s, k, t, r, sig = 100.0, 100.0, 30 / 365, 0.0363, 0.30
    assert oi.american_price(s, k, t, r, 0.0, sig, True) == pytest.approx(
        oi.bsm_price(s, k, t, r, 0.0, sig, True), abs=1e-9)


def test_the_early_exercise_premium_is_SMALL_at_30_days_ATM():
    """Measured, because it is the number that ruled early exercise OUT as the
    explanation for the residue: it moves the residual by -0.0007, an order
    below the ~0.005 that remains, and in the wrong direction."""
    s, k, t, r, q, sig = 100.0, 100.0, 30 / 365, 0.0363, 0.008, 0.30
    prem = (oi.american_price(s, k, t, r, q, sig, False)
            - oi.bsm_price(s, k, t, r, q, sig, False))
    assert 0.0 <= prem < 0.02


def test_phi_does_not_overflow_at_small_sigma():
    """kappa = 2b/sigma^2 reaches ~3000 at a 0.5% vol, and the textbook form
    computes (X/S)**kappa * N(d2) as a product of an overflow and a zero. The
    live pass hit this on its FIRST name, because the bisection necessarily
    walks through tiny sigmas."""
    before = oi.PHI_FALLBACKS["n"]
    for sig in (0.005, 0.01, 0.02):
        v = oi.american_price(100.0, 100.0, 30 / 365, 0.0363, 0.008, sig, False)
        assert math.isfinite(v) and v >= 0
    assert oi.PHI_FALLBACKS["n"] == before, "log-space form should not fall back"


@pytest.mark.parametrize("is_call", [True, False])
def test_american_round_trip(is_call):
    s, k, t, r, q, sigma = 100.0, 100.0, 30 / 365, 0.0363, 0.02, 0.35
    px = oi.american_price(s, k, t, r, q, sigma, is_call)
    got = oi.implied_vol_american(px, s, k, t, r, q, is_call)
    assert got == pytest.approx(sigma, abs=1e-4)


def test_to_continuous_is_not_the_identity():
    """A 4% quote treated as continuous is a 0.08pp rate error. That is inside
    the noise here, and it is exactly the sort of thing that gets assumed."""
    assert oi.to_continuous(0.0425) == pytest.approx(0.041622, abs=1e-6)
    assert oi.to_continuous(0.0) == 0.0
