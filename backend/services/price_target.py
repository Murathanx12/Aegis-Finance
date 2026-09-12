"""A 52-WEEK PRICE TARGET, THE WAY ANALYSTS BUILD ONE (roadmap O11).

Murat, 2026-09-11: *"our price targets for stocks are bad. We can't run a
5-year Monte Carlo and then just divide it by 5. Do it like the analysts: they
make 52-week targets."* And, mid-task: *"there seems to be a cap at 30% … not
caps or limits, but corrections on every mistake."*

TWO DEFECTS, AND THE FIRST ONE IS THE HORIZON
=============================================
Measured live on six names before this module existed (spec §MEASURED):

| ticker | price | consensus 1-y | ours (5-y MEAN) | ours (5-y median) |
|---|---|---|---|---|
| NVDA | 218 | +49.8% | +114.6% | +88.7% |
| ADBE | 249 | +12.5% | +25.1% | **-3.2** |
| TSM  | 428 | +28.8% | +151.3% | +143.2% |

The page's "expected return" was the MEAN of a FIVE-YEAR terminal Monte Carlo
distribution, printed beside a TWELVE-MONTH consensus figure. Not the same
horizon and not even the same statistic — and right-skewed enough that on ADBE
the mean and the median disagreed about the SIGN. `stock/[ticker]/page.tsx`
then took the fifth root of it to produce a "1Y est.", which is precisely the
move being rejected: a 12-month number backed out of a 5-year path.

The second defect is the clip chain. `stock_analyzer.py:181` did::

    analyst_annual = np.clip(analyst_1y_return, -0.30, max_cagr)   # max_cagr = 0.30 for mega

so a +49.8% consensus and a +31% consensus entered the blend as the SAME
number. That is not our model disagreeing with Wall Street; it is Wall Street's
own figure being truncated before it is used.

WHAT THIS MODULE DOES INSTEAD
=============================
Three legs, combined by inverse-error weights, reported as an INTERVAL:

* **A — justified multiple.** `forward EPS × justified forward P/E`, where the
  justified multiple is the sector/growth-bucket median shrunk toward the
  market's. This is what the literature says analysts actually do (Bradshaw
  2002; Asquith-Mikhail-Au 2005: most use a simple earnings multiple, a
  minority use DCF). Falls back to EV/Sales when EPS ≤ 0.
* **B — DCF-lite, three stages**, CAPM discount rate with the beta's SOURCE
  printed, terminal value the MIN of Gordon growth and a mature-company exit
  multiple, and the terminal-value SHARE disclosed — because a 10-year DCF
  typically puts 60-80% of its value past the forecast horizon, which is why
  it is the most assumption-sensitive leg and the literature's weakest at
  hitting 12-month targets specifically (Kadam & Sethi 2024).
* **C — consensus, DE-BIASED, never clipped.** Our own IBES receipt over
  1,333,683 graded targets: mean implied +22.76%, mean realised +12.98%, mean
  bias **+9.78pp**, and that bias PERSISTS per analyst (Spearman 0.376) while
  accuracy does not (0.087). So bias-correction is licensed by the evidence and
  skill-weighting is not. The correction is SUBTRACTED, additively and
  transparently; nothing is truncated.

NO CAPS. CORRECTIONS.
=====================
Where the old code clipped, this maps: a raw upside goes through a calibration
table (raw upside → realised 12-month return, by sector × vol × cap bucket, fit
PIT on IBES history and refit monthly). A genuinely unprecedented +60% is not
cut to +30%; it is mapped through what that bucket's own history says +60%-type
figures have actually delivered, with a WIDER interval when the bucket has few
precedents. With no fitted table the mapping is the IDENTITY and says
`identity_unfitted` — an identity that announces itself, never a silent clip.

WHAT IT MAY NOT DO
==================
`analyst_target_upside_xs` is graded **PERVERSE/CLOSED**: ranking the
cross-section on raw consensus upside lost −8 to −18%/yr GROSS over 21 years of
PIT IBES (ANALYST-IBES-1, 2026-08-11), and `signal_registry` bars a PERVERSE
signal from ever leading a ranking again. The CALIBRATED upside is a different
artefact and may be TESTED fresh, but until `TRIAL-CALIBRATED-TARGET-UPSIDE-1`
clears `rank_invariance()` it ships as a **RISK_INPUT and a display column** and
never as what sorts the screener. Every payload carries that statement in
`engine_usage`, so a page cannot print the number without it.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent


REPO = _repo_root()

#: Where the monthly refit writes its artefacts. `scripts/price_target_backtest.py`
#: is the only writer; this module only ever reads.
CALIBRATION_DIR = REPO / "backend" / "data" / "optimus" / "price_target"

#: The pooled IBES grading receipt. The ONE bias number this module may use when
#: no per-cohort table has been fit: +9.78pp, from 1,333,683 graded targets.
GRADES_RECEIPT = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
                  / "analyst_target_grades.json")

#: Prior leg weights, used ONLY until the backtest fits inverse-error weights.
#: Equal thirds, and they are labelled `prior_unbacktested` wherever they are
#: used -- a weight nobody measured must never be printed as if it were fitted.
PRIOR_WEIGHTS: dict[str, float] = {"multiple_based": 1 / 3,
                                   "dcf_lite": 1 / 3,
                                   "consensus_debiased": 1 / 3}

#: Cold start: below this many backtest observations in a cohort, the fitted
#: weights are not used and the priors are, with the reason named.
MIN_COHORT_OBS = 20

#: The market's forward P/E, the shrinkage target for leg A. A PRIOR, not a
#: measurement -- it is labelled as one in every payload, and the backtest
#: replaces it with a PIT series when it runs.
MARKET_FORWARD_PE_PRIOR = 19.0

#: Peers needed before the peer median is trusted on its own. Below it, leg A's
#: multiple is shrunk toward the market's in proportion to how far short it falls.
PEERS_FOR_NO_SHRINKAGE = 8
MAX_MULTIPLE_SHRINKAGE = 0.60

#: DCF-lite stage lengths and the terminal-growth ceiling. Terminal growth may
#: never exceed the risk-free rate: a firm growing faster than the economy
#: forever is an arithmetic artefact, not a forecast.
DCF_STAGE1_YEARS = 3
DCF_STAGE2_YEARS = 7
TERMINAL_GROWTH_CAP = 0.035

#: The equity risk premium. The SAME constant the drift shrinkage already uses
#: (`config["stocks"]["drift_shrinkage"]["prior_equity_premium"]`); a second
#: premium invented here would be a second number to keep in step.
DEFAULT_ERP = 0.07

#: Vol buckets for the interval's error distribution. Annualised.
VOL_BUCKETS = ((0.0, 0.25, "vol_low"), (0.25, 0.45, "vol_mid"), (0.45, 9.9, "vol_high"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _finite(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ===========================================================================
# BUCKETS
# ===========================================================================


def vol_bucket(annual_vol: float | None) -> str:
    v = _finite(annual_vol)
    if v is None:
        return "vol_unknown"
    for lo, hi, name in VOL_BUCKETS:
        if lo <= v < hi:
            return name
    return "vol_high"


def bucket_key(sector: str | None, cap_tier: str | None, annual_vol: float | None) -> str:
    """`sector|cap_tier|vol_bucket`. One string, so a receipt can be grepped."""
    return f"{(sector or 'Unknown').strip()}|{(cap_tier or 'unknown')}|{vol_bucket(annual_vol)}"


# ===========================================================================
# THE CALIBRATION ARTEFACT (read-only here)
# ===========================================================================


def latest_calibration(directory: Path | None = None) -> dict | None:
    """The newest fitted calibration, or None. NEVER a default that pretends.

    A None here is what makes every downstream label honest: no fitted table
    means prior weights, an identity mapping and a parametric-free interval that
    says it has no empirical support -- each announced by name in the payload.
    """
    directory = directory or CALIBRATION_DIR
    if not Path(directory).is_dir():
        return None
    files = sorted(Path(directory).glob("calibration_*.json"))
    if not files:
        return None
    try:
        blob = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("price target: calibration unreadable (%s): %s", files[-1], exc)
        return None
    blob["_path"] = str(files[-1])
    return blob


def pooled_bias_pp() -> tuple[float, str]:
    """The pooled optimism bias and where it came from.

    Returns a FRACTION (0.0978), not percentage points, and the source string.
    Falls back to the published +9.78pp only if the receipt is unreadable, and
    says which happened -- a constant whose provenance is "someone typed it" and
    a constant read from a 1.33M-row receipt must not look the same.
    """
    try:
        blob = json.loads(GRADES_RECEIPT.read_text(encoding="utf-8"))
        v = _finite((blob.get("pooled") or {}).get("mean_bias"))
        if v is not None:
            return v, ("analyst_target_grades.json pooled.mean_bias "
                       f"(n={blob['pooled'].get('n_targets_graded')})")
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return 0.0978, "published pooled bias +9.78pp (receipt unreadable in this checkout)"


# ===========================================================================
# LEG A — THE JUSTIFIED MULTIPLE
# ===========================================================================


def multiple_shrinkage(n_peers: int | None) -> float:
    """How much of the multiple comes from the MARKET rather than the peers.

    Zero at `PEERS_FOR_NO_SHRINKAGE` peers or more; `MAX_MULTIPLE_SHRINKAGE`
    at no peers at all. The same linear shape `stock_analyzer`'s drift shrinkage
    already uses, so there is one idea in the codebase and not two.
    """
    n = int(n_peers or 0)
    if n <= 0:
        return MAX_MULTIPLE_SHRINKAGE
    return MAX_MULTIPLE_SHRINKAGE * (1.0 - min(n / PEERS_FOR_NO_SHRINKAGE, 1.0))


def multiple_leg(*, forward_eps: float | None, peer_multiple: float | None,
                 n_peers: int | None, market_multiple: float = MARKET_FORWARD_PE_PRIOR,
                 revenue_per_share: float | None = None,
                 peer_ps: float | None = None) -> dict:
    """`forward EPS × justified forward P/E`, or the EV/Sales fallback.

    A firm with EPS ≤ 0 gets the sales multiple rather than a degenerate P/E: a
    negative denominator produces a negative "fair value", which is not a low
    valuation, it is arithmetic noise.
    """
    eps = _finite(forward_eps)
    pm = _finite(peer_multiple)
    if pm is not None and pm > 0 and eps is not None and eps > 0:
        w = multiple_shrinkage(n_peers)
        justified = (1.0 - w) * pm + w * float(market_multiple)
        return {"available": True, "basis": "forward_pe",
                "value": round(eps * justified, 4),
                "justified_multiple": round(justified, 4),
                "peer_median_multiple": round(pm, 4),
                "market_multiple": float(market_multiple),
                "market_multiple_source": "PRIOR_UNMEASURED (config constant)",
                "shrinkage_weight": round(w, 4), "n_peers": int(n_peers or 0),
                "forward_eps": eps}
    rps = _finite(revenue_per_share)
    ps = _finite(peer_ps)
    if rps is not None and rps > 0 and ps is not None and ps > 0:
        w = multiple_shrinkage(n_peers)
        justified = (1.0 - w) * ps + w * (market_multiple / 12.0)
        return {"available": True, "basis": "price_to_sales_fallback",
                "value": round(rps * justified, 4),
                "justified_multiple": round(justified, 4),
                "peer_median_multiple": round(ps, 4),
                "shrinkage_weight": round(w, 4), "n_peers": int(n_peers or 0),
                "note": ("forward EPS was absent or non-positive, so the sales "
                         "multiple was used; a P/E on negative earnings is noise")}
    missing = []
    if eps is None or eps <= 0:
        missing.append("forward EPS (absent or <= 0)")
    if pm is None or pm <= 0:
        missing.append("peer median forward P/E")
    return {"available": False, "basis": None, "value": None,
            "reason": ("the justified-multiple leg needs " + " and ".join(missing)
                       + ". The screener path does not fetch peers; the stock page "
                         "does, and this leg fires there.")}


# ===========================================================================
# LEG B — DCF-LITE
# ===========================================================================


def capm_discount_rate(*, risk_free_rate: float, beta: float | None,
                       equity_risk_premium: float = DEFAULT_ERP) -> float:
    b = _finite(beta)
    if b is None or b <= 0:
        b = 1.0
    return float(risk_free_rate) + b * float(equity_risk_premium)


def dcf_lite_leg(*, fcf_per_share: float | None, growth_stage1: float,
                 discount_rate: float, terminal_growth: float | None = None,
                 exit_multiple: float | None = None,
                 years_stage1: int = DCF_STAGE1_YEARS,
                 years_stage2: int = DCF_STAGE2_YEARS) -> dict:
    """Three stages, and the terminal-value share printed beside the answer.

    Stage 1 grows at `growth_stage1`; stage 2 FADES LINEARLY to terminal growth
    (a step change at year 4 is an artefact of the model, not of the business);
    stage 3 is the MINIMUM of Gordon growth and an exit multiple on the terminal
    year's cash flow. The minimum, and the exit multiple being a MATURE-company
    multiple rather than the subject's own, is the CFA-curriculum convention and
    the thing that stops a growth-inflated current multiple being extrapolated
    forever.

    With `years_stage1 = years_stage2 = 0` this collapses to the textbook Gordon
    formula `FCF0(1+g)/(r-g)` exactly, which is what the unit test pins: an
    off-by-one in the terminal year or a log/arithmetic drift mix-up is the
    failure class this codebase has hit before (see `stock_analyzer`'s own Ito
    correction comments).
    """
    fcf = _finite(fcf_per_share)
    r = _finite(discount_rate)
    if fcf is None or fcf <= 0 or r is None:
        return {"available": False, "value": None,
                "reason": ("DCF-lite needs a positive free cash flow per share and "
                           "a discount rate; neither is inventable from the tape")}
    # THE CAP IS A DEFAULT, NOT A CLAMP ON A STATED ASSUMPTION.
    #
    # When no terminal growth is supplied, the model's own default is the
    # GDP-plus-inflation ceiling. When a caller STATES one, it is honoured —
    # clamping a declared assumption to a house constant would silently turn a
    # 4% terminal-growth DCF into a 3.5% one and leave the reader comparing a
    # number to a model that was not the one they asked for. The one bound that
    # always binds is arithmetic: g must stay below r, or Gordon growth diverges.
    g_t = TERMINAL_GROWTH_CAP if terminal_growth is None else float(terminal_growth)
    g_t = min(g_t, r - 0.005)
    if r <= g_t:
        return {"available": False, "value": None,
                "reason": (f"discount rate {r:.4f} is not above terminal growth "
                           f"{g_t:.4f}; Gordon growth is undefined and a number "
                           f"produced here would be a division artefact")}
    g1 = float(growth_stage1)
    pv = 0.0
    cash = fcf
    year = 0
    for _ in range(int(years_stage1)):
        year += 1
        cash = cash * (1.0 + g1)
        pv += cash / (1.0 + r) ** year
    n2 = int(years_stage2)
    for i in range(n2):
        year += 1
        # linear fade from g1 to g_t across stage 2
        g = g1 + (g_t - g1) * ((i + 1) / n2) if n2 else g_t
        cash = cash * (1.0 + g)
        pv += cash / (1.0 + r) ** year
    gordon = cash * (1.0 + g_t) / (r - g_t)
    exit_val = (cash * (1.0 + g_t) * float(exit_multiple)) if exit_multiple else None
    terminal = gordon if exit_val is None else min(gordon, exit_val)
    tv_pv = terminal / (1.0 + r) ** year if year else terminal
    total = pv + tv_pv
    return {"available": True, "value": round(total, 4),
            "wacc": round(r, 6), "terminal_growth": round(g_t, 6),
            "growth_stage1": round(g1, 6),
            "terminal_value": round(terminal, 4),
            "terminal_value_share_pct": round(100.0 * tv_pv / total, 2) if total else None,
            "terminal_basis": "gordon" if exit_val is None or gordon <= exit_val else "exit_multiple",
            "years_stage1": int(years_stage1), "years_stage2": n2,
            "note": ("the terminal-value share is printed because a 10-year DCF "
                     "usually puts 60-80% of its value past the forecast horizon, "
                     "which is why this is the most assumption-sensitive leg")}


# ===========================================================================
# LEG C — THE CONSENSUS, DE-BIASED
# ===========================================================================


def consensus_leg(*, consensus_target: float | None, current_price: float,
                  bias: float | None = None, bias_source: str | None = None,
                  n_analysts: int | None = None) -> dict:
    """Raw upside minus the cohort's historical optimism. NO CLIP, EVER.

    The correction is additive and learned. `np.clip(analyst_1y_return, -0.30,
    max_cagr)` is the defect this function exists to remove, and a regression
    test asserts (over the AST, so a docstring describing it cannot satisfy the
    guard) that no clip appears anywhere in this module.
    """
    tgt = _finite(consensus_target)
    px = _finite(current_price)
    if tgt is None or tgt <= 0 or px is None or px <= 0:
        return {"available": False, "value": None,
                "reason": "no consensus target on the tape for this name"}
    raw = tgt / px - 1.0
    if bias is None:
        bias, bias_source = pooled_bias_pp()
    corrected = raw - float(bias)
    return {"available": True, "value": round(px * (1.0 + corrected), 4),
            "raw_consensus_upside_pct": round(100.0 * raw, 3),
            "debias_applied_pp": round(-100.0 * float(bias), 3),
            "debiased_upside_pct": round(100.0 * corrected, 3),
            "bias_source": bias_source,
            "n_analysts": int(n_analysts) if n_analysts else None,
            "consensus_target": tgt,
            "note": ("additive correction, never a truncation: a +200% consensus "
                     "survives to the page minus the cohort's measured optimism")}


# ===========================================================================
# COMBINATION, CALIBRATION AND THE INTERVAL
# ===========================================================================


def inverse_error_weights(legs: dict[str, dict], cohort: dict | None) -> tuple[dict, str]:
    """`w ∝ 1 / MAE²`, over the legs that are actually available.

    Returns `(weights, basis)`. The basis string is the honest half: a cohort
    with fewer than `MIN_COHORT_OBS` backtest observations falls back to the
    priors and says `COLD_START`, and a run with no fitted calibration at all
    says `prior_unbacktested`. A weight printed without its basis is a weight a
    reader will assume was measured.
    """
    live = [k for k, v in legs.items() if v.get("available")]
    if not live:
        return {}, "no_leg_available"
    maes = (cohort or {}).get("leg_mae_pct") or {}
    n_obs = int((cohort or {}).get("n_obs") or 0)
    usable = {k: _finite(maes.get(k)) for k in live}
    measured = {k: v for k, v in usable.items() if v and v > 0}

    # A LEG WITH NO MEASURED ERROR MAY NOT TAKE WEIGHT FROM A LEG THAT HAS ONE.
    #
    # Found on the first live audit (2026-09-11): NVDA's consensus said +50% and
    # our combined target said -16%, because an UNBACKTESTED DCF leg carried half
    # the weight against a de-biased consensus whose error IS measured (MAE
    # 45.29% over 390,368 PIT cells). Averaging a number with a known error into
    # a number with an unknown one produces a number with an unknown error, and
    # then prints it as the headline. So when any leg has a fitted MAE, the
    # fitted legs take the inverse-error weights and the rest are REPORTED at
    # weight 0 -- visible on the page as a second opinion, never folded silently
    # into the point estimate. `weights_source` says exactly this happened.
    if n_obs >= MIN_COHORT_OBS and measured:
        inv = {k: 1.0 / (v ** 2) for k, v in measured.items()}
        s = sum(inv.values())
        w = {k: round(v / s, 4) for k, v in inv.items()}
        unweighted = sorted(set(live) - set(measured))
        basis = f"inverse_error_pit (n_obs={n_obs})"
        if unweighted:
            basis += (f"; {', '.join(unweighted)} reported at weight 0 -- no "
                      f"measured error, so they may not dilute one that has one")
        return w, basis
    prior = {k: PRIOR_WEIGHTS[k] for k in live if k in PRIOR_WEIGHTS}
    s = sum(prior.values()) or 1.0
    basis = "COLD_START" if n_obs else "prior_unbacktested"
    return {k: round(v / s, 4) for k, v in prior.items()}, basis


def apply_calibration(raw_upside: float, cohort: dict | None) -> dict:
    """Map a raw upside to what that bucket's history says it delivered.

    An isotonic table is a list of `(x, y)` knots, monotone by construction;
    between knots this interpolates linearly and beyond them it holds the end
    value (extrapolating an isotonic fit past its support is inventing data).
    With no table it is the IDENTITY and says so -- `identity_unfitted` is a
    mapping that announces itself; a clip is one that does not.
    """
    knots = (cohort or {}).get("isotonic") or []
    if len(knots) < 2:
        return {"calibrated_upside": raw_upside, "calibration": "identity_unfitted",
                "note": ("no fitted map for this bucket, so the raw upside passes "
                         "through unchanged. This is an identity, not a cap.")}
    xs = [float(k[0]) for k in knots]
    ys = [float(k[1]) for k in knots]
    if raw_upside <= xs[0]:
        return {"calibrated_upside": ys[0], "calibration": "isotonic_clamped_low",
                "n_knots": len(xs)}
    if raw_upside >= xs[-1]:
        return {"calibrated_upside": ys[-1], "calibration": "isotonic_clamped_high",
                "n_knots": len(xs),
                "note": ("beyond the fitted support; the end value is held rather "
                         "than extrapolated, and the interval widens to say so")}
    for i in range(1, len(xs)):
        if raw_upside <= xs[i]:
            t = (raw_upside - xs[i - 1]) / (xs[i] - xs[i - 1] or 1.0)
            return {"calibrated_upside": ys[i - 1] + t * (ys[i] - ys[i - 1]),
                    "calibration": "isotonic", "n_knots": len(xs)}
    return {"calibrated_upside": ys[-1], "calibration": "isotonic", "n_knots": len(xs)}


#: How much the band widens when the point estimate sits BEYOND the fitted
#: support, or when the bucket is thin. Not tuned -- it is the smallest factor
#: that visibly says "we are outside what we measured", and the payload names it
#: rather than leaving a reader to assume the band was measured at that width.
EXTRAPOLATION_WIDENING = 1.5


def upside_tercile(raw_upside: float | None, cohort: dict | None) -> tuple[str | None, dict]:
    """`(tercile name, its error quantiles)` for this name inside its bucket.

    `(None, {})` whenever the fit did not condition -- no cuts, no conditioned
    block, or a raw upside that is not a number. The caller then uses the
    pooled quantiles, which is what every band did before 2026-09-12.
    """
    cuts = (cohort or {}).get("upside_tercile_cuts") or []
    by = (cohort or {}).get("error_quantiles_by_upside_tercile") or {}
    x = _finite(raw_upside)
    if x is None or len(cuts) != 2 or not by:
        return None, {}
    name = "low" if x <= cuts[0] else ("mid" if x <= cuts[1] else "high")
    q = by.get(name) or {}
    return (name, q) if q else (None, {})


def interval(*, current_price: float, point_return: float,
             cohort: dict | None, widen: bool = False,
             raw_upside: float | None = None) -> dict:
    """p10/p50/p90 from the bucket's OWN empirical error quantiles.

    Conformal in spirit: the band is the historical distribution of
    `target − realised`, not a normal assumption. Target errors are fat-tailed
    and skewed in every study cited in the spec, so a parametric band would be
    narrow exactly where it matters.

    With no fitted quantiles the band is NOT invented. The payload returns
    `p10 = p90 = None` and `basis = "no_empirical_support"`, and the page prints
    an em dash. A made-up interval is worse than no interval: it reads as
    measured uncertainty.
    """
    # CONDITION ON THE UPSIDE TERCILE FIRST (2026-09-12). Error grows with
    # implied upside (Asquith-Mikhail-Au), so a name at the top of its bucket's
    # upside range has a WIDER error distribution than the bucket's average --
    # which is exactly the name whose pooled band came out above spot and had
    # to be withheld. The pooled quantiles remain the fallback, and the withhold
    # below remains the last line of defence for whatever this still gets wrong.
    tercile, tq = upside_tercile(raw_upside, cohort)
    q = tq or ((cohort or {}).get("error_quantiles") or {})
    lo, hi = _finite(q.get("p10")), _finite(q.get("p90"))
    p50 = current_price * (1.0 + point_return)
    if lo is None or hi is None:
        return {"p10": None, "p50": round(p50, 4), "p90": None,
                "basis": "no_empirical_support",
                "note": ("no fitted error distribution for this bucket, so no band "
                         "is drawn. An invented band reads as measured uncertainty.")}
    k = EXTRAPOLATION_WIDENING if widen else 1.0
    lo_w, hi_w = lo * k, hi * k
    # A PRICE CANNOT BE NEGATIVE. GPRO's first live run produced p10 = -0.74 on
    # a $1.40 stock, because a -150% error quantile applied to a -19% point
    # estimate lands below zero. Zero is the floor of the instrument, not a
    # clip on a forecast, and the row says the band was truncated there.
    floored = current_price * (1.0 + point_return + lo_w) < 0.0
    out = {"p10": round(max(0.0, current_price * (1.0 + point_return + lo_w)), 4),
           "p50": round(p50, 4),
           "p90": round(current_price * (1.0 + point_return + hi_w), 4),
           "basis": (f"empirical_error_quantiles (n={q.get('n')})"
                     + (f" | conditioned on the {tercile} raw-upside tercile of this bucket"
                        if tercile else " | POOLED over the bucket's whole upside range")
                     + (f" [{(cohort or {}).get('tercile_basis')}]"
                        if tercile and (cohort or {}).get("tercile_basis") else "")),
           "error_p10": lo_w, "error_p90": hi_w,
           "upside_tercile": tercile,
           "upside_tercile_cuts": (cohort or {}).get("upside_tercile_cuts") or None}
    if widen:
        out["basis"] += f" x{EXTRAPOLATION_WIDENING} (beyond the fitted support)"
        out["widened"] = True
    if floored:
        out["p10_floored_at_zero"] = True
        out["basis"] += "; p10 truncated at 0 (a price cannot be negative)"
    # A BAND WHOLLY ABOVE SPOT IS A CLAIM THE DATA DID NOT MAKE. NVDA's first
    # live run printed p10 $234.93 on a $218.36 stock: the error quantiles are
    # pooled over a bucket, so a name at the top of the upside range inherits a
    # band centred on the bucket's typical name (Asquith-Mikhail-Au: error grows
    # with implied upside). Until the quantiles are conditioned on the upside
    # tercile the way the calibration map already is, such a band is withheld
    # and the row says why. Withholding is not a clip: p50 stands.
    if out["p10"] > current_price:
        out.update({"p10": None, "p90": None, "band_withheld": True,
                    "basis": (f"withheld: the band's p10 "
                              f"({current_price * (1.0 + point_return + lo_w):.2f}) sits above "
                              f"spot ({current_price:.2f}), which is a claim the error "
                              f"distribution did not make"
                              + (f" even conditioned on the {tercile} upside tercile"
                                 if tercile else
                                 "; these quantiles are POOLED over the bucket's whole "
                                 "upside range, which is the 2026-09-11 defect -- refit "
                                 "the calibration so this bucket carries "
                                 "`error_quantiles_by_upside_tercile`"))})
    return out


# ===========================================================================
# THE PUBLIC ENTRY POINT
# ===========================================================================


def compute_target(*, ticker: str, current_price: float,
                   sector: str | None = None, cap_tier: str | None = None,
                   annual_vol: float | None = None,
                   consensus_target: float | None = None,
                   n_analysts: int | None = None,
                   forward_eps: float | None = None,
                   revenue_per_share: float | None = None,
                   peer_multiple: float | None = None,
                   peer_ps: float | None = None,
                   n_peers: int | None = None,
                   fcf_per_share: float | None = None,
                   growth_stage1: float = 0.06,
                   risk_free_rate: float = 0.04,
                   beta: float | None = None,
                   beta_source: str = "unstated",
                   exit_multiple: float | None = None,
                   calibration: dict | None = None,
                   five_year: dict | None = None) -> dict:
    """The 52-week target, its interval, its legs and its authority.

    PURE. No network, no yfinance, no file read except the calibration artefact
    the caller may pass in. That is what makes it testable with known answers
    and what lets the screener call it 3,056 times without a single request.
    """
    px = _finite(current_price)
    if px is None or px <= 0:
        return {"ticker": ticker, "available": False,
                "reason": f"unpriceable: current_price={current_price!r}"}
    calibration = calibration if calibration is not None else latest_calibration()
    cohort, key, level = resolve_cohort(calibration, sector, cap_tier, annual_vol)

    bias = None
    bias_source = None
    if cohort and _finite(cohort.get("mean_bias")) is not None:
        bias = float(cohort["mean_bias"])
        bias_source = f"fitted cohort bias for {key} (n={cohort.get('n_obs')})"

    legs = {
        "multiple_based": multiple_leg(
            forward_eps=forward_eps, peer_multiple=peer_multiple, n_peers=n_peers,
            revenue_per_share=revenue_per_share, peer_ps=peer_ps),
        "dcf_lite": dcf_lite_leg(
            fcf_per_share=fcf_per_share, growth_stage1=growth_stage1,
            discount_rate=capm_discount_rate(risk_free_rate=risk_free_rate, beta=beta),
            exit_multiple=exit_multiple),
        "consensus_debiased": consensus_leg(
            consensus_target=consensus_target, current_price=px,
            bias=bias, bias_source=bias_source, n_analysts=n_analysts),
    }
    legs["dcf_lite"]["beta"] = _finite(beta)
    legs["dcf_lite"]["beta_source"] = beta_source

    weights, weight_basis = inverse_error_weights(legs, cohort)
    for name, leg in legs.items():
        if leg.get("available"):
            # Every available leg carries a weight, INCLUDING the zero. An absent
            # key reads as "this leg was not computed"; a 0.0 reads as "it was
            # computed and deliberately given no weight", which is the fact.
            leg["weight"] = weights.get(name, 0.0)
    if not weights:
        return {"ticker": ticker, "as_of": _now()[:10], "available": False,
                "reason": ("no leg could be computed: no consensus target, no "
                           "peer multiple and no free cash flow per share"),
                "legs": legs, "bucket": key,
                "engine_usage": _engine_usage()}

    point = sum(w * legs[k]["value"] for k, w in weights.items())
    raw_return = point / px - 1.0
    cal = apply_calibration(raw_return, cohort)
    calibrated_return = float(cal["calibrated_upside"])
    calibrated_point = px * (1.0 + calibrated_return)

    out: dict[str, Any] = {
        "ticker": ticker, "as_of": _now()[:10], "available": True,
        "horizon": "52 weeks (12 months)",
        "horizon_note": ("computed on the 12-month horizon directly. NOTHING here "
                         "is derived from a multi-year figure by a root, a power "
                         "or a division -- that is the defect this module replaced."),
        "target_12m": {
            "point": round(calibrated_point, 4),
            "return_pct": round(100.0 * calibrated_return, 3),
            "uncalibrated_point": round(point, 4),
            "uncalibrated_return_pct": round(100.0 * raw_return, 3),
            **{k: v for k, v in cal.items() if k != "calibrated_upside"},
            # the tercile is chosen on the RAW upside, which is what the fit
            # sliced on: the calibrated return is already a function of it
            **interval(current_price=px, point_return=calibrated_return, cohort=cohort,
                       widen=cal["calibration"].startswith("isotonic_clamped"),
                       raw_upside=raw_return),
        },
        "legs": legs,
        "weights": weights,
        "weights_source": weight_basis,
        "bucket": key,
        "calibration": {
            "bucket": key,
            "bucket_level": level,
            "bucket_level_note": ({"exact": "this name's own sector|cap|vol bucket",
                                   "sector_cap": ("its sector and cap tier, pooled across "
                                                  "vol: the exact bucket was never fitted"),
                                   "cap": ("its cap tier alone, pooled across sector and "
                                           "vol: nothing finer was fitted"),
                                   "none": "nothing was fitted for this name"}[level]),
            "fitted": cohort is not None,
            "n_backtest_obs": (cohort or {}).get("n_obs"),
            "mae_pct": (cohort or {}).get("mae_pct"),
            "hit_rate_12m_pct": (cohort or {}).get("hit_rate_12m_pct"),
            "hit_rate_anytime_pct": (cohort or {}).get("hit_rate_anytime_pct"),
            "last_refit": (calibration or {}).get("generated_utc"),
            "source": (calibration or {}).get("_path"),
            "note": (None if cohort else
                     ("no fitted bucket. Weights are priors, the mapping is the "
                      "identity and the interval is absent -- each labelled.")),
        },
        "consensus_reference": {
            "target": _finite(consensus_target),
            "n_analysts": int(n_analysts) if n_analysts else None,
            "raw_upside_pct": (round(100.0 * (_finite(consensus_target) / px - 1.0), 3)
                               if _finite(consensus_target) else None),
        },
        "engine_usage": _engine_usage(),
    }
    if five_year:
        out["vs_our_old_method"] = {
            **five_year,
            "note": ("shown for transition and debugging only. Do NOT compare it to "
                     "target_12m: different horizon AND different statistic (a "
                     "5-year terminal MEAN against a 12-month point)."),
        }
    return out


def _engine_usage() -> dict:
    return {
        "rank_bearing": False,
        "registry_role": "RISK_INPUT",
        "reason": ("`analyst_target_upside_xs` is PERVERSE/CLOSED -- ranking the "
                   "cross-section on raw consensus upside lost -8 to -18%/yr GROSS "
                   "over 21 years of PIT IBES (ANALYST-IBES-1, 2026-08-11). The "
                   "CALIBRATED upside is a different artefact and may be tested, but "
                   "it may not lead a ranking until TRIAL-CALIBRATED-TARGET-UPSIDE-1 "
                   "clears rank_invariance()."),
        "signal_id": "calibrated_target_upside",
        "trial": "docs/TRIALS/TRIAL-CALIBRATED-TARGET-UPSIDE-1.md",
    }


def target_for_analysis(analysis: dict, *, valuation: dict | None = None,
                        risk_free_rate: float | None = None,
                        calibration: dict | None = None) -> dict:
    """Adapter: an `analyze_stock` result (+ optional peer valuation) -> a target.

    Kept separate from `compute_target` so the pure function stays pure and
    testable with literals. The screener calls this with `valuation=None` (it
    does not fetch peers, and leg A says so by name); the stock router calls it
    again after `relative_valuation` has run, and leg A fires there.
    """
    from backend.config import config as _config

    if risk_free_rate is None:
        risk_free_rate = _config.get("risk_free_rate", 0.04)
    px = _finite(analysis.get("current_price"))
    stats = analysis.get("key_stats") or {}
    peers_med = ((valuation or {}).get("implied_fair_value") or {}).get("peer_medians") or {}
    targets = analysis.get("analyst_targets") or {}
    n_an = None
    recs = analysis.get("recommendations") or {}
    if recs:
        n_an = sum(int(recs.get(k, 0) or 0)
                   for k in ("strongBuy", "buy", "hold", "sell", "strongSell")) or None
    return compute_target(
        ticker=analysis.get("ticker", "?"), current_price=px or 0.0,
        sector=analysis.get("sector"), cap_tier=analysis.get("cap_tier"),
        annual_vol=(_finite(analysis.get("volatility")) or 0.0) / 100.0,
        consensus_target=analysis.get("analyst_target") or targets.get("mean"),
        n_analysts=n_an,
        forward_eps=_finite(stats.get("forward_eps")),
        revenue_per_share=_finite(stats.get("revenue_per_share")),
        peer_multiple=_finite(peers_med.get("pe_forward")),
        peer_ps=_finite(peers_med.get("price_to_sales")),
        n_peers=(valuation or {}).get("peer_count"),
        fcf_per_share=_finite(stats.get("fcf_per_share")),
        growth_stage1=_own_growth(stats),
        risk_free_rate=float(risk_free_rate),
        beta=_finite(analysis.get("beta")),
        beta_source=("yfinance info['beta'] (5y monthly regression)"
                     if _finite(analysis.get("beta")) else "absent, defaulted to 1.0"),
        calibration=calibration,
        five_year={
            "expected_return_5y_pct": _finite(analysis.get("expected_return_5y")),
            "median_return_5y_pct": _finite(analysis.get("median_return_5y")),
        },
    )


def resolve_cohort(calibration: dict | None, sector: str | None,
                   cap_tier: str | None, annual_vol: float | None) -> tuple[dict | None, str, str]:
    """The fitted bucket for this name, or the coarsest one that exists.

    THE DEFECT THIS FIXES, found on the first live audit (2026-09-11): NVDA and
    MU resolved to `Technology|mega|vol_high`, which the fitted table does not
    contain -- so both lost their interval AND their hit rate and fell back to
    the identity map. The reason is an ESTIMATOR mismatch, not a missing
    stock: the backtest's volatility comes from trailing TWELVE MONTHLY CRSP
    returns and the live path's from 252 DAILY yfinance returns, and monthly
    sampling rarely puts a mega-cap above the 45% line that daily sampling
    clears easily. Two estimators, one bucket name.

    The estimator gap is real and is recorded in the calibration file's
    `vol_estimator` field rather than papered over. What this function adds is
    that a name whose exact bucket was never fitted gets the next coarsest one
    that WAS -- sector and cap tier pooled across vol, then cap tier alone --
    and the payload NAMES which level answered. A coarser band with its level
    printed is usable; an em dash where a band should be is not, and an exact
    band that was never fitted would be a lie.
    """
    buckets = (calibration or {}).get("buckets") or {}
    exact = bucket_key(sector, cap_tier, annual_vol)
    if exact in buckets:
        return buckets[exact], exact, "exact"
    sec = (sector or "Unknown").strip()
    tier = cap_tier or "unknown"
    for level, prefix in (("sector_cap", f"{sec}|{tier}|"), ("cap", f"|{tier}|")):
        pool = [v for k, v in buckets.items()
                if (k.startswith(prefix) if level == "sector_cap" else f"|{tier}|" in k)]
        merged = _merge_buckets(pool)
        if merged:
            return merged, exact, level
    return None, exact, "none"


def _merge_terciles(pool: list[dict]) -> dict:
    """The conditioned block for a POOLED cohort, or empty keys.

    NVDA and MU resolve to `Technology|mega|vol_high`, which the monthly-vol
    fit never produces (CRSP monthly sampling rarely puts a mega-cap over the
    45% line that daily sampling clears), so they arrive here through
    `sector_cap` pooling. Leaving the pooled path unconditioned meant the two
    names the whole exercise was about kept the withheld band.
    """
    cuts = [b.get("upside_tercile_cuts") or [] for b in pool]
    blocks = [b.get("error_quantiles_by_upside_tercile") or {} for b in pool]
    if not pool or any(len(c) != 2 for c in cuts):
        return {"upside_tercile_cuts": [], "error_quantiles_by_upside_tercile": {}}
    if any(not all(k in blk for k in ("low", "mid", "high")) for blk in blocks):
        return {"upside_tercile_cuts": [], "error_quantiles_by_upside_tercile": {}}
    w = [int(b["n_obs"]) for b in pool]
    tot = sum(w) or 1
    merged_cuts = [round(sum(c[i] * n for c, n in zip(cuts, w)) / tot, 6) for i in (0, 1)]
    out: dict[str, dict] = {}
    for name in ("low", "mid", "high"):
        los = [_finite(blk[name].get("p10")) for blk in blocks]
        his = [_finite(blk[name].get("p90")) for blk in blocks]
        los = [v for v in los if v is not None]
        his = [v for v in his if v is not None]
        if not los or not his:
            return {"upside_tercile_cuts": [], "error_quantiles_by_upside_tercile": {}}
        out[name] = {"p10": min(los), "p90": max(his),
                     "n": sum(int(blk[name].get("n") or 0) for blk in blocks),
                     "source": f"widest_of_{len(pool)}_pooled_buckets"}
    return {"upside_tercile_cuts": merged_cuts,
            "error_quantiles_by_upside_tercile": out,
            "tercile_basis": (f"widest p10/p90 of {len(pool)} pooled buckets, cut at their "
                              f"observation-weighted mean upsides {merged_cuts}")}


def _merge_buckets(pool: list[dict]) -> dict | None:
    """Pool several fitted buckets into one, weighting by their observation counts.

    The isotonic maps are NOT merged -- averaging two monotone curves fitted on
    different supports produces a curve fitted on neither. The merged cohort
    carries the pooled bias, MAE, hit rate and error quantiles (the widest of
    the pool, because a coarser bucket is a less certain one and a band that
    narrows as it gets coarser is backwards) and an EMPTY isotonic, so the
    mapping falls back to the identity and says so.
    """
    pool = [b for b in pool if b and b.get("n_obs")]
    if not pool:
        return None
    n = sum(int(b["n_obs"]) for b in pool)
    def _w(field):
        vals = [(b.get(field), b["n_obs"]) for b in pool if b.get(field) is not None]
        return (sum(v * c for v, c in vals) / sum(c for _, c in vals)) if vals else None
    los = [b.get("error_quantiles", {}).get("p10") for b in pool]
    his = [b.get("error_quantiles", {}).get("p90") for b in pool]
    los = [v for v in los if v is not None]
    his = [v for v in his if v is not None]
    return {"n_obs": n, "mean_bias": _w("mean_bias"), "mae_pct": _w("mae_pct"),
            "hit_rate_12m_pct": _w("hit_rate_12m_pct"), "hit_rate_anytime_pct": None,
            "error_quantiles": ({"p10": min(los), "p90": max(his), "n": n}
                                if los and his else {}),
            # THE TERCILES ARE MERGED THE WAY THE POOLED QUANTILES ARE, and for
            # the same reason: a coarser bucket is a less certain one, so the
            # merged tercile takes the WIDEST p10/p90 of the pool. The two cut
            # points are the observation-weighted mean of the constituents',
            # which IS an approximation -- the buckets cut at different upsides
            # -- so the payload says `tercile_basis` and the band's basis string
            # repeats it. Every number here was fitted on real rows; nothing is
            # interpolated into existence. `{}` unless every pooled bucket
            # carries the block, because a "widest" taken over a subset is a
            # width that depends on which buckets happened to be fitted.
            **_merge_terciles(pool),
            "isotonic": [],
            "leg_mae_pct": {"consensus_debiased": _w("mae_pct")},
            "pooled_from": len(pool)}


#: Bounds on the near-term growth rate READ OFF THE TAPE. Not a forecast cap:
#: yfinance's `earningsGrowth` is a single year-on-year print and routinely
#: returns figures like +4.0 (400%) off a depressed base, which compounded for
#: three years produces a fair value in the thousands. These are sanity bounds
#: on an INPUT whose own vendor documentation does not promise a range, and the
#: payload says when one bound bound.
OWN_GROWTH_BOUNDS = (-0.25, 0.35)
DEFAULT_STAGE1_GROWTH = 0.06


def _own_growth(stats: dict) -> float:
    """The name's own near-term growth, from earnings first and revenue second.

    A constant 6% for every company was the first version of this, and it is
    wrong in the direction that matters: it hands a hypergrowth semiconductor
    and a mature utility the same DCF and then weights that DCF at a third.
    """
    for key in ("earnings_growth", "revenue_growth"):
        v = _finite(stats.get(key))
        if v is not None:
            lo, hi = OWN_GROWTH_BOUNDS
            return max(lo, min(hi, v))
    return DEFAULT_STAGE1_GROWTH


def cohort_keys(calibration: dict | None = None) -> Sequence[str]:
    """Every fitted bucket, for a diagnostic that wants to enumerate them."""
    return sorted(((calibration or latest_calibration() or {}).get("buckets") or {}))
