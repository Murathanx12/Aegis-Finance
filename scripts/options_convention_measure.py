"""OPTIONS-CONVENTION-1 — is the put-call residual a SIGNAL gap or a SOLVER gap?

DECLARED BEFORE THE NUMBERS EXIST. Arms, bars and decision rule below were
written and committed before a chain was pulled.

THE STANDING PROBLEM
====================
`EVENT_RESPONSE_v1` is fit on OptionMetrics `stdopd` and served on yfinance.
Three of four option features transfer. One does not:

    iv_put_minus_call_30d    live median -0.0237   stdopd median +0.0019
                             live 25% positive     stdopd 55% positive

Two routes are spent. A matched-strike residual moved the median only
-0.0254 -> -0.0237. A cross-sectional rank (`AMENDMENT-2`) passed exactly one
horizon per candidate arm, which is how a model gets chosen by whichever
horizon someone wrote down first.

WHAT BOTH ROUTES HELD FIXED
===========================
Both kept reading yfinance's `impliedVolatility` COLUMN — the output of Yahoo's
pricer under Yahoo's undisclosed assumptions about the risk-free rate, the
dividend, the exercise style and which price to invert. OptionMetrics inverts a
binomial American model against the bid/ask MIDPOINT with its own zero curve
and projected discrete dividends.

This feature is the one of the four where that matters most, and structurally
rather than by luck. By put-call parity a call and a put at the same strike are
tied, so a same-strike IV residual is close to a pure statement about the
pricer's r and q: it is a DIFFERENCE, so the level of volatility cancels and
the convention error does not. The other three are levels or same-side slopes,
where a shared bias largely cancels or is small beside the quantity.

That is why the matched-strike fix barely moved: it corrected WHICH strikes were
compared and left the disputed quantity — somebody else's implied vol —
completely intact.

THE ARMS
========
Every arm inverts the SAME chain at the SAME matched strike. Only the
convention changes.

  R0  vendor         yfinance `impliedVolatility`.  THE CONTROL — reproduces
                     the standing -0.0237.
  R1  own_r_q        our BSM inversion of the bid/ask MID, with a declared
                     continuous r from the Treasury curve and a declared
                     continuous q from trailing dividends. The candidate.
  R2  own_r_only     same, q = 0.  Isolates the DIVIDEND term.
  R3  own_zero       same, r = 0 and q = 0.  Isolates the RATE term — and it
                     is the diagnostic that identifies what Yahoo is assuming:
                     if R3 lands on R0, Yahoo is discounting nothing.
  R4  own_last       R1's convention inverted against the LAST TRADE instead of
                     the mid. Isolates the price basis, which on a thin strike
                     can move the residual by more than the whole gap.

Isolating one term per arm is the point. "Re-implied and it got better" is not
a diagnosis, and a fitted map that made the medians agree would be the thing
the rank route was chosen to avoid.

THE DECISION RULE, DECLARED
===========================
An arm TRANSFERS iff both:

  1. |median(arm) - median(stdopd)|      <= 0.005   (half a vol point)
  2. |pct_positive(arm) - pct_positive(stdopd)| <= 0.10

stdopd reference, from `train_serve_skew_receipt.json` (a committed file, not a
number retyped here): median +0.00194, 54.8% positive. R0 misses both by
0.0256 and 0.30.

If R1 transfers, the mismatch was a solver gap and the fix is to stop reading
the vendor's IV column — no calibration layer, nothing to drift.

If R1 does not transfer but moves most of the way, the receipt must say which
TERM carried it (R2 vs R3 vs R4) and the residue is named rather than fitted.

If R1 moves nothing, the difference is exercise style or discrete dividends —
the two things `option_implier` declares it does NOT model — and the honest
route is the review's fallback: ship the drop-feature arm as a labelled
PRODUCT_EXPERIMENT and say plainly it sits under its own MDE80.

NOT A CLAIM, and no forward return is touched. This is servability.

ROUND 2 - DECLARED AFTER ROUND 1'S NUMBERS, BEFORE ROUND 2'S
============================================================
Round 1 identified the mechanism and left one free parameter holding the
verdict. Both halves matter.

IDENTIFIED, and not by a fitted map: R3 (r=0, q=0) came back at -0.02335
against the vendor's -0.02428. **yfinance's `impliedVolatility` column is
computed with no discounting and no dividend.** That is the whole 0.026 gap,
and it was never a signal difference.

BUT THE RESIDUE IS A RATE I GUESSED. The residual is very nearly linear in
(r - q) - measured +0.0071 per percentage point of r - so the declared bar of
0.005 is cleared or missed by a rate choice of about seven tenths of a point:

    r = 0.0363 (FRED fed funds)   median -0.00338   gap -0.00532   MISSES
    r = 0.0400                    median -0.00082   gap -0.00276   passes
    r = 0.0425                    median +0.00090   gap -0.00104   passes

Choosing the rate that passes would be the same move this programme refuses
everywhere else, and fed funds effective is in any case the wrong instrument:
OptionMetrics discounts on a zero curve, and a 30-day zero is not the overnight
policy rate.

ROUND 2 REMOVES THE PARAMETER INSTEAD OF PICKING IT.
Put-call parity across TWO strikes at one expiry identifies the discount factor
exactly, with no model and no vendor assumption:

    (C1 - P1) - (C2 - P2) = -D (K1 - K2)   =>   D = e^{-rT} from the SLOPE in K

and - this is the part that makes it usable here rather than circular - the
borrow/parity violation the feature exists to measure lives in the FORWARD,
which is common across strikes, while r is identified by the slope. The two are
separately identified, so taking r from the market does NOT absorb the signal.
Taking the forward from parity as well WOULD: the residual would then be zero by
construction, which is why round 2 keeps q declared from trailing dividends.

  R5  own_parity_r    r solved from the cross-strike slope per expiry; q
                      declared as in R1; residual at the matched strike.

The bars and the reference are UNCHANGED and are not re-derived. R5 either
clears them or it does not, and the rate is no longer anybody's choice.

USAGE
    python -m scripts.options_convention_measure --names 40
    python -m scripts.options_convention_measure --from-cache
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "backend/data/optimus/options_pit"
RECEIPT = OUT / "convention_receipt.json"
REFERENCE = OUT / "train_serve_skew_receipt.json"

MEDIAN_BAR = 0.005
PCT_POS_BAR = 0.10

#: Declared conventions. `r` is the 1-month Treasury as a simple annual yield;
#: `q` is trailing-12-month dividends over spot. Both are converted to
#: continuous compounding at use. Recorded on every row so a later reader can
#: re-derive the number instead of trusting this docstring.
R_FALLBACK = 0.0425
TARGET_DAYS = 30
BAND = 0.06
#: Wider band for the parity solve ONLY: the discount factor comes from a
#: regression in K, and a slope estimated over a 6% window on a few strikes is
#: noise. It does not widen which strike the residual is measured at.
PARITY_BAND = 0.20


def stdopd_reference() -> dict:
    d = json.loads(REFERENCE.read_text(encoding="utf-8"))
    for row in d["distributions"]:
        if row["feature"] == "iv_put_minus_call_30d":
            return {"median": row["stdopd_median"],
                    "pct_positive": row["stdopd_pct_positive"],
                    "live_median_previously_measured": row["live_median"],
                    "live_pct_positive_previously_measured":
                        row["live_pct_positive"]}
    raise SystemExit("reference feature missing from the receipt")


def risk_free() -> tuple[float, str]:
    """1-month Treasury, simple annual. FRED if reachable, else declared."""
    try:
        from backend.services.data_fetcher import DataFetcher
        fred = DataFetcher().fetch_fred_data() or {}
        for key in ("fed_funds",):
            v = fred.get(key)
            # The payload carries pandas Series, not scalars or dicts. The
            # first version called .get("value") on one, which returns None and
            # then raises inside float() -- so the run silently fell back to a
            # DECLARED constant while printing a rate that decided the verdict.
            if v is None:
                continue
            try:
                val = float(v.iloc[-1]) if hasattr(v, "iloc") else float(v)
            except Exception:                                # noqa: BLE001
                continue
            if math.isfinite(val):
                return val / 100.0, f"FRED:{key}={val}"
    except Exception as e:                                   # noqa: BLE001
        print(f"  (FRED unavailable: {type(e).__name__}) ")
    return R_FALLBACK, "declared fallback"


def universe(n: int) -> list[str]:
    from backend.config import config
    names: list[str] = []
    for v in config["stock_universe"]["sector_stocks"].values():
        names.extend(v)
    return sorted(set(names))[:n]


def collect_quotes(ticker: str) -> dict | None:
    """The matched-strike QUOTES for one name, off ONE chain pull.

    Separated from scoring deliberately. The arms and the rate sweep are then
    pure functions of this cache, so every number in the receipt is
    re-derivable without touching the vendor again -- and an option chain, like
    the option state itself, has no history to go back for.
    """
    import pandas as pd
    import yfinance as yf

    from backend.services.option_implier import quote_price
    from backend.services.options_pit_store import _matched_strike_iv

    tk = yf.Ticker(ticker)
    hist = tk.history(period="1y", auto_adjust=False, actions=True)
    if hist is None or hist.empty:
        return None
    spot = float(hist["Close"].iloc[-1])
    if not spot or not math.isfinite(spot) or spot <= 0:
        return None
    divs = (float(hist["Dividends"].tail(252).sum())
            if "Dividends" in hist.columns else 0.0)

    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    points = []
    for e in list(tk.options or []):
        days = (pd.Timestamp(e).normalize() - today).days
        if days <= 0 or days > TARGET_DAYS + 45:
            continue
        try:
            ch = tk.option_chain(e)
        except Exception:                                    # noqa: BLE001
            continue
        calls, puts = ch.calls, ch.puts
        if calls is None or puts is None or calls.empty or puts.empty:
            continue
        cb = {float(x["strike"]): x for _, x in calls.iterrows()}
        pb = {float(x["strike"]): x for _, x in puts.iterrows()}

        def _f(row, col):
            try:
                v = float(row[col])
                return v if v > 0 and math.isfinite(v) else None
            except Exception:                                # noqa: BLE001
                return None

        chosen = None
        parity_rows = []
        for k in sorted(set(cb) & set(pb), key=lambda x: abs(x - spot)):
            if abs(k - spot) > spot * PARITY_BAND:
                break
            mc, bc = quote_price(cb[k])
            mp, bp = quote_price(pb[k])
            if mc is None or mp is None:
                continue
            # Every usable strike in the wider band is kept, because R5 solves
            # for the discount factor from the SLOPE of (C - P) in K and one
            # point has no slope. The matched-strike residual still uses only
            # the nearest strike, exactly as before.
            parity_rows.append({"strike": k, "call_mid": mc, "put_mid": mp})
            if chosen is None and abs(k - spot) <= spot * BAND:
                chosen = {
                    "days": float(days), "strike": k,
                    "call_mid": mc, "put_mid": mp,
                    "call_basis": bc, "put_basis": bp,
                    "call_last": _f(cb[k], "lastPrice"),
                    "put_last": _f(pb[k], "lastPrice"),
                }
        if chosen is None:
            continue
        chosen["parity_rows"] = parity_rows
        # The VENDOR arm keeps its ORIGINAL construction (options_pit_store's
        # matched-strike reader) so R0 reproduces the standing -0.0237 rather
        # than a near-miss of it. A control that does not reproduce the number
        # it controls for is not a control.
        vc, vp = _matched_strike_iv(calls, puts, spot)
        chosen["vendor_iv_call"] = vc
        chosen["vendor_iv_put"] = vp
        points.append(chosen)

    if not points:
        return None
    return {"ticker": ticker, "spot": spot,
            "q_simple": (divs / spot) if spot else 0.0,
            "points": points}


def _interp_resid(points):
    """A residual is a DIFFERENCE, so it interpolates LINEARLY in time.

    The total-variance rule the IV levels use does not apply to it, and
    applying it anyway would be a third convention nobody declared.
    """
    pts = sorted(points)
    if not pts:
        return None
    below = [p for p in pts if p[0] <= TARGET_DAYS]
    above = [p for p in pts if p[0] >= TARGET_DAYS]
    if below and above:
        d0, v0 = below[-1]
        d1, v1 = above[0]
        if d0 == d1:
            return v0
        return v0 + (v1 - v0) * (TARGET_DAYS - d0) / (d1 - d0)
    d, v = (below[-1] if below else above[0])
    return v if abs(d - TARGET_DAYS) <= 15 else None


def parity_implied_rate(point: dict, spot: float):
    """Solve e^{-rT} from the cross-strike slope of (C - P).

    Put-call parity says C(K) - P(K) = D*(F - K), so the slope of (C - P)
    against K is exactly -D. F - which carries the dividend AND the borrow - is
    the intercept and is deliberately NOT used: taking it from here would make
    the residual zero by construction and delete the feature.
    """
    rows = point.get("parity_rows") or []
    if len(rows) < 3:
        return None
    ks = np.asarray([r["strike"] for r in rows], dtype=float)
    cp = np.asarray([r["call_mid"] - r["put_mid"] for r in rows], dtype=float)
    if ks.max() - ks.min() < spot * 0.02:
        return None                    # too narrow a lever for a slope
    slope = float(np.polyfit(ks, cp, 1)[0])
    d = -slope
    if not (0.5 < d <= 1.0000001):     # a discount factor, not a fit artefact
        return None
    t = point["days"] / 365.0
    if t <= 0:
        return None
    r_cont = -math.log(min(d, 1.0)) / t
    return r_cont if -0.02 < r_cont < 0.20 else None


def residual(cache_row: dict, arm: str, r_simple: float):
    """One arm's 30-day residual for one name, from the cached quotes."""
    from backend.services.option_implier import implied_vol, to_continuous

    spot = cache_row["spot"]
    q = to_continuous(cache_row["q_simple"])
    r = to_continuous(r_simple)
    rr, qq, basis = {
        "R1_own_r_q": (r, q, "mid"),
        "R2_own_r_only": (r, 0.0, "mid"),
        "R3_own_zero": (0.0, 0.0, "mid"),
        "R4_own_last": (r, q, "last"),
        "R5_own_parity_r": (None, q, "mid"),      # r solved per expiry
    }.get(arm, (None, None, None))

    pts = []
    for p in cache_row["points"]:
        if arm == "R0_vendor":
            if p.get("vendor_iv_call") and p.get("vendor_iv_put"):
                pts.append((p["days"],
                            p["vendor_iv_put"] - p["vendor_iv_call"]))
            continue
        pc = p["call_mid"] if basis == "mid" else p.get("call_last")
        pp = p["put_mid"] if basis == "mid" else p.get("put_last")
        if not pc or not pp:
            continue
        t = p["days"] / 365.0
        r_use = rr
        if arm == "R5_own_parity_r":
            r_use = parity_implied_rate(p, spot)
            if r_use is None:
                continue
        ivc = implied_vol(pc, spot, p["strike"], t, r_use, qq, True)
        ivp = implied_vol(pp, spot, p["strike"], t, r_use, qq, False)
        if ivc and ivp:
            pts.append((p["days"], ivp - ivc))
    return _interp_resid(pts)


def summarise(cache, arm: str, r_simple: float, ref: dict) -> dict:
    vals = np.asarray([v for v in (residual(row, arm, r_simple)
                                   for row in cache) if v is not None],
                      dtype=float)
    if not vals.size:
        return {"n": 0}
    med, pos = float(np.median(vals)), float((vals > 0).mean())
    out = {
        "n": int(vals.size),
        "median": round(med, 5),
        "pct_positive": round(pos, 4),
        "p10": round(float(np.percentile(vals, 10)), 5),
        "p90": round(float(np.percentile(vals, 90)), 5),
        "median_gap_vs_stdopd": round(med - ref["median"], 5),
        "pct_pos_gap_vs_stdopd": round(pos - ref["pct_positive"], 4),
        "gate_median": bool(abs(med - ref["median"]) <= MEDIAN_BAR),
        "gate_pct_positive": bool(
            abs(pos - ref["pct_positive"]) <= PCT_POS_BAR),
    }
    out["transfers"] = bool(out["gate_median"] and out["gate_pct_positive"])
    return out


ARMS = ["R0_vendor", "R1_own_r_q", "R2_own_r_only", "R3_own_zero",
        "R4_own_last", "R5_own_parity_r"]

#: Rates the sweep reports R1 at. NOT a search for one that passes: the
#: DECIDING rate is whatever `risk_free()` returns from FRED. The sweep exists
#: because a wrong rate shifts every name by the SAME amount -- the exact kind
#: of offset this whole measurement is about -- so a verdict that moves across
#: this range is a verdict resting on a number nobody checked, and that has to
#: be visible in the receipt rather than discoverable later.
R_SWEEP = [0.0, 0.02, 0.03, 0.0363, 0.04, 0.0425, 0.045, 0.05]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", type=int, default=40)
    ap.add_argument("--from-cache", action="store_true")
    args = ap.parse_args()

    ref = stdopd_reference()
    r_simple, r_src = risk_free()
    print(f"r = {r_simple:.4f} ({r_src})")

    quote_cache = OUT / "convention_quotes.json"
    if args.from_cache and quote_cache.exists():
        cache = json.loads(quote_cache.read_text(encoding="utf-8"))["rows"]
        print(f"from cache: {len(cache)} names")
    else:
        cache = []
        names = universe(args.names)
        for i, t in enumerate(names, 1):
            try:
                row = collect_quotes(t)
            except Exception as e:                           # noqa: BLE001
                print(f"  {t}: {type(e).__name__}: {e}")
                continue
            if row:
                cache.append(row)
            if i % 10 == 0:
                print(f"  {i}/{len(names)}")
        OUT.mkdir(parents=True, exist_ok=True)
        quote_cache.write_text(json.dumps(
            {"n": len(cache), "rows": cache}, indent=1), encoding="utf-8")

    summary = {arm: summarise(cache, arm, r_simple, ref) for arm in ARMS}
    for arm in ARMS:
        s = summary[arm]
        if not s.get("n"):
            print(f"{arm:16s} n 0")
            continue
        print(f"{arm:16s} n {s['n']:3d}  median {s['median']:+.5f} "
              f"(gap {s['median_gap_vs_stdopd']:+.5f})  "
              f"pos {s['pct_positive']:.1%}  "
              f"{'TRANSFERS' if s['transfers'] else 'no'}")

    sweep = []
    for r in R_SWEEP:
        s = summarise(cache, "R1_own_r_q", r, ref)
        sweep.append({"r": r, "median": s.get("median"),
                      "pct_positive": s.get("pct_positive"),
                      "transfers": s.get("transfers")})
    print("")
    print("R1 sensitivity to the declared rate:")
    for row in sweep:
        print(f"  r={row['r']:.4f}  median {row['median']:+.5f}  "
              f"pos {row['pct_positive']:.1%}  "
              f"{'TRANSFERS' if row['transfers'] else 'no'}")

    RECEIPT.write_text(json.dumps({
        "measurement_id": "OPTIONS-CONVENTION-1",
        "licence": "PRODUCT_EXPERIMENT (servability - no IC, no forward "
                   "return, not evidence of alpha)",
        "declared_in": "scripts/options_convention_measure.py (this file)",
        "question": ("is the iv_put_minus_call_30d train/serve gap a SIGNAL "
                     "difference or an artefact of inverting the vendor's "
                     "implied-vol column instead of the prices?"),
        "stdopd_reference": ref,
        "conventions": {"r_simple": r_simple, "r_source": r_src,
                        "q": "trailing 12m dividends / spot, per name",
                        "model": "Black-Scholes-Merton, European",
                        "price": "bid/ask midpoint (R4 uses the last trade)",
                        "not_modelled": ["American early exercise",
                                         "discrete dividends"]},
        "bars": {"median": MEDIAN_BAR, "pct_positive": PCT_POS_BAR},
        "n_names_attempted": args.names,
        "n_names_measured": len(cache),
        "arms": summary,
        "rate_sensitivity": sweep,
        "quotes_cached_at": str(quote_cache),
    }, indent=1), encoding="utf-8")
    print("")
    print(f"receipt -> {RECEIPT}")


if __name__ == "__main__":
    main()
