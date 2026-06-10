"""
Aegis Finance — Bond Analytics
================================

Per-bond analytics that institutional terminals (Bloomberg YAS, FactSet
Fixed Income Calculation API) charge for. Closes the OpenBB / Koyfin gap
on the fixed-income side: those platforms ship the *data* (yield curve,
spreads) but not the *calculator* (per-CUSIP YTM / duration / convexity /
key-rate durations / OAS-adjacent diagnostics).

Public surface
--------------
- ``CashFlow`` & ``Bond``                   structured inputs
- ``solve_ytm(cashflows, price)``           Newton solve for yield-to-maturity
- ``modified_duration(...)``                duration in years
- ``convexity(...)``                        convexity in years²
- ``bond_analytics(bond, price)``           full analytics for one bond
- ``key_rate_durations(bond, price, ...)``  KRDs at 2y / 5y / 10y / 30y
- ``treasury_curve()``                      current US Treasury par curve (FRED)
- ``ladder_analytics(positions)``           portfolio-level YTM / duration / convexity

Inputs are deliberately simple — a list of (time_years, cashflow) pairs.
That keeps the module agnostic to data source and lets us back it with the
existing FRED yield curve (no paid CUSIP data feed required).

References
----------
- Fabozzi, *Bond Markets, Analysis, and Strategies* (8e), ch. 4 (duration,
  convexity), ch. 18 (key-rate duration).
- Tuckman & Serrat, *Fixed Income Securities* (3e), ch. 5–6.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)


# ── Data structures ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CashFlow:
    """A single bond cashflow."""

    t_years: float       # time-to-payment in years (e.g. 0.5, 1.0, 1.5 ...)
    amount: float        # cashflow amount (coupon + principal)


@dataclass(frozen=True)
class Bond:
    """Vanilla fixed-coupon bond.

    Coupons paid semi-annually at coupon_rate / 2 of face value. Principal
    repaid at maturity. Use ``Bond.cashflows()`` to materialise the schedule.
    """

    face: float = 100.0
    coupon_rate: float = 0.0      # annual coupon as decimal (0.045 = 4.5%)
    maturity_years: float = 10.0  # years to maturity (must be > 0)
    freq: int = 2                 # coupons per year (1=annual, 2=semi, 4=quarterly)

    def cashflows(self) -> list[CashFlow]:
        if self.maturity_years <= 0:
            return []
        if self.freq < 1:
            raise ValueError("freq must be >= 1")
        n_periods = max(1, int(round(self.maturity_years * self.freq)))
        coupon = self.face * self.coupon_rate / self.freq
        out: list[CashFlow] = []
        for i in range(1, n_periods + 1):
            t = i / self.freq
            amt = coupon + (self.face if i == n_periods else 0.0)
            out.append(CashFlow(t_years=t, amount=amt))
        return out


# ── Core math ───────────────────────────────────────────────────────────────


def present_value(cashflows: Sequence[CashFlow], ytm: float, *, freq: int = 2) -> float:
    """Discount a stream of cashflows at a constant yield.

    ``ytm`` is the bond-equivalent yield (annualised, compounded ``freq``
    times per year). Matches the standard institutional convention.
    """
    if freq < 1:
        raise ValueError("freq must be >= 1")
    per_period = ytm / freq
    pv = 0.0
    for cf in cashflows:
        n = cf.t_years * freq
        if 1.0 + per_period <= 0:
            return float("nan")
        pv += cf.amount / (1.0 + per_period) ** n
    return pv


def solve_ytm(
    cashflows: Sequence[CashFlow],
    price: float,
    *,
    freq: int = 2,
    max_iter: int = 100,
    tol: float = 1e-8,
) -> Optional[float]:
    """Newton-Raphson yield-to-maturity solver with bisection fallback.

    Returns the annualised YTM consistent with the given clean price, or
    ``None`` if the solver fails (e.g. arbitrage-free region collapses).
    """
    if not cashflows or price <= 0:
        return None
    if freq < 1:
        raise ValueError("freq must be >= 1")

    # Initial guess: current yield as a starting point
    coupon_total = sum(cf.amount for cf in cashflows[:-1]) if len(cashflows) > 1 else 0.0
    last_period = cashflows[-1].t_years
    avg_coupon = coupon_total / max(last_period, 1.0)
    y = max(0.0001, avg_coupon / max(price, 1.0))

    # Newton iterations
    for _ in range(max_iter):
        per_period = y / freq
        if 1.0 + per_period <= 0:
            break
        pv = 0.0
        dpv = 0.0  # derivative dPV/dy
        for cf in cashflows:
            n = cf.t_years * freq
            disc = (1.0 + per_period) ** n
            pv += cf.amount / disc
            dpv += -cf.amount * n / freq / (disc * (1.0 + per_period))
        diff = pv - price
        if abs(diff) < tol:
            return float(y)
        if dpv == 0:
            break
        y_new = y - diff / dpv
        # Keep yield in a sane range
        if y_new <= -0.99 or y_new > 5.0 or not math.isfinite(y_new):
            break
        if abs(y_new - y) < tol:
            return float(y_new)
        y = y_new

    # Bisection fallback over a wide bracket
    lo, hi = -0.5, 2.0
    f_lo = present_value(cashflows, lo, freq=freq) - price
    f_hi = present_value(cashflows, hi, freq=freq) - price
    if not (math.isfinite(f_lo) and math.isfinite(f_hi)) or f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        f_mid = present_value(cashflows, mid, freq=freq) - price
        if abs(f_mid) < tol or (hi - lo) < tol:
            return float(mid)
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return float(0.5 * (lo + hi))


def macaulay_duration(
    cashflows: Sequence[CashFlow], ytm: float, *, freq: int = 2
) -> float:
    """Macaulay duration (in years)."""
    pv = present_value(cashflows, ytm, freq=freq)
    if pv <= 0 or not math.isfinite(pv):
        return float("nan")
    per_period = ytm / freq
    weighted = 0.0
    for cf in cashflows:
        n = cf.t_years * freq
        disc = (1.0 + per_period) ** n
        weighted += cf.t_years * cf.amount / disc
    return weighted / pv


def modified_duration(
    cashflows: Sequence[CashFlow], ytm: float, *, freq: int = 2
) -> float:
    """Modified duration: Macaulay / (1 + y/freq)."""
    mac = macaulay_duration(cashflows, ytm, freq=freq)
    return mac / (1.0 + ytm / freq)


def convexity(cashflows: Sequence[CashFlow], ytm: float, *, freq: int = 2) -> float:
    """Convexity in years² (textbook definition)."""
    pv = present_value(cashflows, ytm, freq=freq)
    if pv <= 0 or not math.isfinite(pv):
        return float("nan")
    per_period = ytm / freq
    s = 0.0
    for cf in cashflows:
        n = cf.t_years * freq
        disc = (1.0 + per_period) ** n
        s += cf.t_years * (cf.t_years + 1.0 / freq) * cf.amount / disc
    return s / pv / (1.0 + per_period) ** 2


def estimate_price_change(
    duration: float, conv: float, dyield_bp: float
) -> float:
    """Second-order price change estimate from duration + convexity.

    Returns the percentage change in price for a parallel shift of
    ``dyield_bp`` basis points.
    """
    dy = dyield_bp / 10000.0
    return -duration * dy + 0.5 * conv * dy * dy


# ── Per-bond analytics (full report) ────────────────────────────────────────


def bond_analytics(
    bond: Bond, price: float, *, freq: Optional[int] = None
) -> dict:
    """Compute a full analytics block for one bond at a given clean price."""
    f = freq or bond.freq
    cfs = bond.cashflows()
    if not cfs:
        return {"error": "bond has no cashflows", "bond": _bond_to_dict(bond)}

    y = solve_ytm(cfs, price, freq=f)
    if y is None:
        return {
            "error": "YTM solver did not converge",
            "bond": _bond_to_dict(bond),
            "price": price,
        }

    dur_mod = modified_duration(cfs, y, freq=f)
    dur_mac = macaulay_duration(cfs, y, freq=f)
    conv = convexity(cfs, y, freq=f)

    # +/- 100bp shock estimates
    shocks_bp = [-200, -100, -50, -25, 25, 50, 100, 200]
    shocks = {
        f"{bp:+d}bp": round(estimate_price_change(dur_mod, conv, bp) * 100, 4)
        for bp in shocks_bp
    }
    # Interest-rate sensitivity in dollars per 1bp move (DV01)
    dv01 = abs(estimate_price_change(dur_mod, conv, 1.0)) * price

    return {
        "bond": _bond_to_dict(bond),
        "price": round(price, 4),
        "ytm_pct": round(y * 100, 4),
        "current_yield_pct": round(
            (bond.face * bond.coupon_rate) / price * 100, 4
        ),
        "macaulay_duration_years": round(dur_mac, 4),
        "modified_duration_years": round(dur_mod, 4),
        "convexity_years2": round(conv, 4),
        "dv01_dollars_per_100": round(dv01, 6),
        "price_shock_pct": shocks,
        "n_cashflows": len(cfs),
    }


def _bond_to_dict(bond: Bond) -> dict:
    return {
        "face": bond.face,
        "coupon_rate_pct": round(bond.coupon_rate * 100, 4),
        "maturity_years": bond.maturity_years,
        "freq": bond.freq,
    }


# ── Key-rate durations ───────────────────────────────────────────────────────

KEY_TENORS_YEARS = (2.0, 5.0, 10.0, 30.0)


def _shifted_curve_yield(
    base_yield: float, t: float, key_tenor: float, shock_bp: float, *, half_width: float = 5.0
) -> float:
    """Triangular hat-function shift centred at ``key_tenor``.

    Each key-rate shock perturbs the yield curve only around the chosen
    tenor; the perturbation linearly tapers to zero at the neighbouring
    keys (Tuckman, Fabozzi). Outside the band the bond's discount rate is
    unchanged.
    """
    distance = abs(t - key_tenor)
    if distance >= half_width:
        return base_yield
    weight = max(0.0, 1.0 - distance / half_width)
    return base_yield + (shock_bp / 10000.0) * weight


def key_rate_durations(
    bond: Bond,
    price: float,
    *,
    freq: Optional[int] = None,
    shock_bp: float = 25.0,
    tenors: Iterable[float] = KEY_TENORS_YEARS,
) -> dict:
    """Bucketed durations against shocks at each KEY_TENOR.

    Computed by repricing the bond under a triangular ±shock at each tenor
    and converting the price change to a sensitivity (years per unit
    shock). Accumulated KRDs sum approximately to modified duration when
    the curve is reasonably smooth.
    """
    f = freq or bond.freq
    cfs = bond.cashflows()
    if not cfs:
        return {"error": "no cashflows"}
    base_y = solve_ytm(cfs, price, freq=f)
    if base_y is None:
        return {"error": "base YTM did not converge"}

    krds: dict[str, float] = {}
    base_pv = present_value(cfs, base_y, freq=f)
    for tenor in tenors:
        # Reprice under +shock: each cashflow discounted at its perturbed yield
        def _pv(shock):
            pv = 0.0
            for cf in cfs:
                y_t = _shifted_curve_yield(base_y, cf.t_years, tenor, shock)
                per = y_t / f
                if 1.0 + per <= 0:
                    return float("nan")
                pv += cf.amount / (1.0 + per) ** (cf.t_years * f)
            return pv

        pv_up = _pv(+shock_bp)
        pv_dn = _pv(-shock_bp)
        if not (math.isfinite(pv_up) and math.isfinite(pv_dn)):
            krds[f"{int(tenor)}y"] = float("nan")
            continue
        # Effective duration for this bucket
        krd = -(pv_up - pv_dn) / (2.0 * base_pv * (shock_bp / 10000.0))
        krds[f"{int(tenor)}y"] = round(krd, 4)

    krd_sum = sum(v for v in krds.values() if math.isfinite(v))
    return {
        "shock_bp": shock_bp,
        "key_rate_durations": krds,
        "sum_krd": round(krd_sum, 4),
        "modified_duration_years": round(modified_duration(cfs, base_y, freq=f), 4),
    }


# ── Ladder / portfolio analytics ────────────────────────────────────────────


def ladder_analytics(positions: Sequence[dict]) -> dict:
    """Portfolio-level fixed-income analytics from a list of bond positions.

    Each position dict requires at least ``maturity_years`` and ``coupon_rate``.
    Optional: ``face`` (default 100), ``freq`` (default 2), ``price``
    (default = par if absent), ``weight`` (defaults to equal weight if absent).
    """
    if not positions:
        return {"error": "no positions"}

    enriched: list[dict] = []
    weights = []
    for p in positions:
        bond = Bond(
            face=float(p.get("face", 100.0)),
            coupon_rate=float(p.get("coupon_rate", 0.0)),
            maturity_years=float(p["maturity_years"]),
            freq=int(p.get("freq", 2)),
        )
        price = float(p.get("price", bond.face))
        a = bond_analytics(bond, price)
        if "error" in a:
            return {"error": f"position failed: {a['error']}"}
        enriched.append(a)
        weights.append(float(p.get("weight", 1.0)))

    w = np.array(weights, dtype=float)
    if w.sum() <= 0:
        return {"error": "weights sum to zero"}
    w = w / w.sum()

    ytms = np.array([a["ytm_pct"] for a in enriched])
    durs = np.array([a["modified_duration_years"] for a in enriched])
    convs = np.array([a["convexity_years2"] for a in enriched])
    mats = np.array([a["bond"]["maturity_years"] for a in enriched])

    return {
        "n_positions": len(enriched),
        "weighted_ytm_pct": round(float((w * ytms).sum()), 4),
        "weighted_modified_duration": round(float((w * durs).sum()), 4),
        "weighted_convexity": round(float((w * convs).sum()), 4),
        "weighted_avg_maturity_years": round(float((w * mats).sum()), 4),
        "ladder_dispersion_years": round(float(mats.std()), 4),
        "positions": [
            {**a, "weight": round(float(weight), 6)}
            for a, weight in zip(enriched, w)
        ],
    }


# ── Treasury curve fetcher ──────────────────────────────────────────────────


_TREASURY_TENORS = {
    "1m": "DGS1MO",
    "3m": "DGS3MO",
    "6m": "DGS6MO",
    "1y": "DGS1",
    "2y": "DGS2",
    "3y": "DGS3",
    "5y": "DGS5",
    "7y": "DGS7",
    "10y": "DGS10",
    "20y": "DGS20",
    "30y": "DGS30",
}


def treasury_curve() -> dict:
    """Current US Treasury par curve from FRED.

    Returns par yields (in percent) at the standard CMT tenors plus the
    classic 10y-2y and 10y-3m slope spreads. Used by the ladder builder
    UI as a default coupon assumption.
    """
    try:
        from backend.services.providers import registry
    except ImportError:
        return {"error": "providers registry not available"}

    yields: dict[str, float] = {}
    last_dates: dict[str, str] = {}
    for tenor, series_id in _TREASURY_TENORS.items():
        s = registry.get_macro_series(series_id)
        if s is None or len(s) == 0:
            continue
        s = s.dropna() if hasattr(s, "dropna") else s
        if len(s) == 0:
            continue
        yields[tenor] = round(float(s.iloc[-1]), 4)
        try:
            last_dates[tenor] = str(s.index[-1].date())
        except Exception:
            pass

    if not yields:
        return {"error": "no Treasury data available (FRED unkeyed?)"}

    spreads = {}
    if "10y" in yields and "2y" in yields:
        spreads["10y_2y_bp"] = round((yields["10y"] - yields["2y"]) * 100, 1)
    if "10y" in yields and "3m" in yields:
        spreads["10y_3m_bp"] = round((yields["10y"] - yields["3m"]) * 100, 1)
    if "30y" in yields and "10y" in yields:
        spreads["30y_10y_bp"] = round((yields["30y"] - yields["10y"]) * 100, 1)

    inverted = bool(
        ("10y" in yields and "2y" in yields and yields["10y"] < yields["2y"])
    )

    return {
        "yields_pct": yields,
        "last_dates": last_dates,
        "spreads_bp": spreads,
        "inverted": inverted,
        "interpretation": (
            "Inverted curve — historically a recession signal within 6-18 months."
            if inverted
            else "Normal curve — long rates above short rates."
        ),
    }
